# -*- coding: utf-8 -*-
"""`UG-G3-SB4` OOF 矩陣產生器（PO 2026-09-15 核准進入腳本階段）。

**僅限 dev container 內執行**（依賴 sklearn，見 `CLAUDE.md` §13.0）。

**唯讀，結構上不可能連 DB**：只讀取已凍結的 parquet 面板，只寫兩份 OOF
parquet（逐 target）與一份證據 JSON；不匯入任何資料庫驅動程式。

對折 0～32（`src.ml.stacking.iter_oof_folds()` 已排除 Holdout）重新執行
Purged Walk-Forward 訓練迴圈，僅 **Arm A** 四個 Specialist
（LogisticRegression／RandomForest／LightGBM／XGBoost），`return_proba=True`
取得機率輸出，經 `assemble_oof_matrix()` 組成寬格式矩陣，依折序號標記
`split_segment`（折 0～26 `meta_train`、折 27～32 `meta_eval`），再經
`apply_second_stage_purge()` 把 Meta-Train 中標籤結算日期晚於或等於
Meta-Eval 起點的列改標 `purged`。

六項腳本層守衛（任一不符即 abort，比照 `UG-G3-SB3`
`ug_g3_sb3_specialist_report.py` 的既定紀律，不降級、不警告帶過）：

1. parquet sha256 必須等於 `PANEL_SHA256`（Gate A §2.5／`DEC-040` 記載值）。
2. 折 27／33 的測試窗起日必須恰為 `META_EVAL_START_DATE`／
   `HOLDOUT_START_DATE`（對凍結面板重新跑一次 `WalkForwardSplitter` 驗證，
   不只信任模組常數本身）。
3. `iter_oof_folds()` 的輸出經 `reject_rows_at_or_after()` 二次確認零
   Holdout 列（防禦性重驗，結構上不應觸發）。
4. 二階 Purge 排除列數必須等於 `EXPECTED_PURGE_COUNTS[target]`
   （`target_up_down`=150、`target_triple_barrier`=680，審查方對凍結
   面板重算、PM 獨立重現相符的**保留列**基準——不是折測試窗的原始列數。
   這項迴歸原本設計要放在單元測試，因依賴真實凍結面板違反
   `CLAUDE.md` §13.4 測試封閉性，改放在此腳本層守衛，見
   `tests/test_ug_g3_sb4_oof_scripts.py` 檔頭說明）。
5. `meta_train`／`meta_eval`（二階 Purge **之前**）列數必須等於
   `EXPECTED_SEGMENT_COUNTS[target]`（`target_up_down`
   80,968／17,949；`target_triple_barrier` 74,394／16,730——同樣是
   `prepare_fold_data()` 規則 (a)(b) 之後的保留列數，逐 target 各自
   核對，不是單一全域常數）。
6. 每個 Fold 的 `purge_mode` 必須為 `"exact"`（防禦性重驗）。

**2026-09-15 訂正**：折 0～32 共 **33 折**（folds 0-26 為 meta_train、
27-32 為 meta_eval），先前文件誤稱「全量（43 折）」——43 折是凍結面板
的總折數，本 SB 只跑其中 33 折，折 33～42（Holdout）全程不迭代。

固定參數（`UG_G3_SB4_GATE_A_PROPOSAL.md` §4.1／§4.4，PO 已核准，不對外
開放調整）：`train_window_size=60, test_window_size=20, mode="rolling",
embargo_days=0`；`target_up_down` 用 `label_horizon=1,
label_end_date_col="label_end_date"`；`target_triple_barrier` 用
`label_horizon=5, label_end_date_col="label_end_date_tb"`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

try:
    import sklearn  # noqa: F401
except ImportError as exc:  # pragma: no cover - 環境檢查
    raise RuntimeError(
        "本腳本依賴 sklearn，僅能在 dev container 內執行（見 CLAUDE.md §13.0）。"
    ) from exc

from src.ml.baseline_models import ARM_A_FEATURE_COLS, META_REGIME_FEATURE_COLS
from src.ml.specialist_training import fit_predict_specialist_fold, prepare_fold_data
from src.ml.stacking import (
    HOLDOUT_START_DATE,
    META_EVAL_START_DATE,
    MODEL_NAME_SHORT_CODES,
    assemble_oof_matrix,
    apply_second_stage_purge,
    iter_oof_folds,
    reject_rows_at_or_after,
)
from src.ml.time_series_split import WalkForwardSplitter


class OofGenerationError(RuntimeError):
    """面板／切分器／守衛失敗——結構性 abort，不降級、不跳過。"""


TARGET_CONFIG: Dict[str, Dict[str, Any]] = {
    "target_up_down": {"label_horizon": 1, "label_end_date_col": "label_end_date"},
    "target_triple_barrier": {"label_horizon": 5, "label_end_date_col": "label_end_date_tb"},
}

TRAIN_WINDOW_SIZE = 60
TEST_WINDOW_SIZE = 20
EMBARGO_DAYS = 0
LAST_META_TRAIN_FOLD = 26  # 折 0～26 為 meta_train，折 27～32 為 meta_eval

# Gate A §2.5（`VERIFIED THIS SESSION`，對 UG-G3-SB3 凍結面板重跑
# WalkForwardSplitter 實測），DEC-040 登記值。
PANEL_SHA256 = {
    "target_up_down": "39dc6b8e6160add20f39a7265bad04de50c76199fa7ab81b979a7aabeabbd014",
    "target_triple_barrier": "4c4657c4e7e36b227fef01d2f6f667b8e613b23587db40f2907d024db9b3f729",
}
# 2026-09-15 訂正（審查方對凍結面板重算，PM 獨立重現相符）：這些是
# `prepare_fold_data()` 規則 (a)(b) 之後的**保留列數**，不是折測試窗的
# 原始列數——OOF 矩陣只含保留列，兩者不同。TB 的 purge 數原本誤寫為
# 750（那是原始列數上的迴歸基準），保留列上的正確值是 680。
EXPECTED_PURGE_COUNTS = {"target_up_down": 150, "target_triple_barrier": 680}
EXPECTED_SEGMENT_COUNTS = {
    "target_up_down": {"meta_train": 80968, "meta_eval": 17949},
    "target_triple_barrier": {"meta_train": 74394, "meta_eval": 16730},
}

DEFAULT_PANEL_DIR = Path("/workspaces/Database_Backups/Stock_Prediction_System2/ml_panels")
DEFAULT_OOF_OUTPUT_DIR = DEFAULT_PANEL_DIR
DEFAULT_EVIDENCE_OUTPUT_DIR = Path("doc/upgrade/gates/evidence")

MODEL_NAMES_FULL = ("logistic_regression", "random_forest", "lightgbm", "xgboost")

_REPORT_OUTPUT_PATH_RE = re.compile(
    r"^doc/upgrade/gates/evidence/UG_G3_SB4_oof_generation_.*\.json$")


def _is_report_output_path(path: str) -> bool:
    return bool(_REPORT_OUTPUT_PATH_RE.match(path.replace("\\", "/")))


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_script_commit_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """比照 `ug_g3_sb3_specialist_report.py::get_script_commit_info()`
    ——兩個容器內既有環境坑（dubious ownership／CRLF 誤判）用逐次 `-c`
    授權處理，不動全域／本機設定。"""
    root = repo_root or Path(__file__).resolve().parents[2]
    git_common_opts = ["-c", f"safe.directory={root}", "-c", "core.autocrlf=true"]

    try:
        commit_hash = subprocess.run(
            ["git", *git_common_opts, "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise OofGenerationError(
            f"無法取得 git commit hash（{root}）：{exc}——版本不明的輸出不得產出。"
        ) from exc

    status_output = subprocess.run(
        ["git", *git_common_opts, "status", "--porcelain"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout

    tracked_modified: List[str] = []
    untracked: List[str] = []
    for line in status_output.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:].strip()
        (untracked if code == "??" else tracked_modified).append(path)

    dirty_paths = [p for p in tracked_modified if not _is_report_output_path(p)]
    return {
        "commit": commit_hash,
        "dirty": bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "untracked_paths": untracked,
    }


def verify_panel_sha256(panel_path: Path, target: str) -> str:
    """守衛 1：parquet 實際 sha256 必須等於 `PANEL_SHA256[target]`。"""
    expected = PANEL_SHA256[target]
    actual = compute_file_sha256(panel_path)
    if actual != expected:
        raise OofGenerationError(
            f"parquet sha256 不符登記值——expected={expected} actual={actual}"
            f"（{panel_path}）。拒絕對未經複核的面板產生 OOF。"
        )
    return actual


def build_splitter(target: str) -> WalkForwardSplitter:
    cfg = TARGET_CONFIG[target]
    return WalkForwardSplitter(
        train_window_size=TRAIN_WINDOW_SIZE,
        test_window_size=TEST_WINDOW_SIZE,
        mode="rolling",
        embargo_days=EMBARGO_DAYS,
        label_horizon=cfg["label_horizon"],
        label_end_date_col=cfg["label_end_date_col"],
        require_label_end_date=True,
    )


def assert_fold_boundaries(panel: pd.DataFrame, splitter: WalkForwardSplitter) -> None:
    """守衛 2：折 27／33 的測試窗起日必須恰為 `META_EVAL_START_DATE`／
    `HOLDOUT_START_DATE`——對凍結面板重新跑一次完整切分驗證，不只信任
    模組常數本身（常數可能與面板實際內容不同步）。"""
    fold_27_start = None
    fold_33_start = None
    for train_idx, test_idx, fold_meta in splitter.split(panel):
        if fold_meta.get("purge_mode") != "exact":
            raise OofGenerationError(
                f"折 {fold_meta.get('fold')} 的 purge_mode="
                f"{fold_meta.get('purge_mode')!r}，非 'exact'——拒絕產出。"
            )
        fold_id = fold_meta["fold"]
        if fold_id == 27:
            fold_27_start = panel.loc[test_idx, "trade_date"].min()
        elif fold_id == 33:
            fold_33_start = panel.loc[test_idx, "trade_date"].min()

    if fold_27_start != META_EVAL_START_DATE:
        raise OofGenerationError(
            f"折 27 測試窗起日 {fold_27_start} 與 META_EVAL_START_DATE "
            f"{META_EVAL_START_DATE} 不符——面板可能已變動，拒絕產出。"
        )
    if fold_33_start != HOLDOUT_START_DATE:
        raise OofGenerationError(
            f"折 33 測試窗起日 {fold_33_start} 與 HOLDOUT_START_DATE "
            f"{HOLDOUT_START_DATE} 不符——面板可能已變動，拒絕產出。"
        )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def generate_oof_for_target(
    target: str,
    panel_path: Path,
    max_folds: Optional[int] = None,
) -> Dict[str, Any]:
    """單一 target 的 OOF 產生全流程。`max_folds` 供單折探測使用
    （限制實際訓練的折數，不影響守衛 2 的完整邊界驗證，該項一律對全部
    折執行）。"""
    if target not in TARGET_CONFIG:
        raise ValueError(f"不支援的 target: {target!r}")
    cfg = TARGET_CONFIG[target]
    label_end_col = cfg["label_end_date_col"]

    sha256 = verify_panel_sha256(panel_path, target)
    panel = pd.read_parquet(panel_path).reset_index(drop=True)

    splitter = build_splitter(target)
    assert_fold_boundaries(panel, splitter)

    fold_results: List[Dict[str, Any]] = []
    fold_timings: List[Dict[str, Any]] = []
    n_folds_processed = 0
    n_target_null_excluded_total = 0
    n_feature_null_excluded_total = 0

    # 2026-09-15 訂正：直接迭代 iter_oof_folds() 的輸出，不得手動重寫
    # 等義的 Holdout 排除邏輯——那正是 test_straddling_fold_is_excluded_
    # entirely 要保護的函式，繞過它會讓那條紅測的保護力對本腳本失效
    # （先前的手動 continue 判斷式與 iter_oof_folds() 內部邏輯幾乎相同，
    # 但「幾乎相同」不是「同一份程式碼」，任何一邊未來修改都可能悄悄
    # 分岔）。
    for train_idx, test_idx, fold_meta in iter_oof_folds(splitter, panel, HOLDOUT_START_DATE):
        if max_folds is not None and n_folds_processed >= max_folds:
            break
        fold_id = fold_meta["fold"]
        n_folds_processed += 1

        t0 = time.perf_counter()
        train_prepared = prepare_fold_data(
            panel, train_idx, ARM_A_FEATURE_COLS, [], target_col="target", arm="A")
        test_prepared = prepare_fold_data(
            panel, test_idx, ARM_A_FEATURE_COLS, [], target_col="target", arm="A")
        # 只計 test 窗——OOF 矩陣的列來自測試窗預測，EXPECTED_SEGMENT_COUNTS
        # 也是以測試窗保留列數為準，train 窗的排除數不影響 OOF 矩陣列數，
        # 混進來會讓這個揭露數字對不上 row_counts，故意不計。
        n_target_null_excluded_total += test_prepared["n_target_null_excluded"]
        n_feature_null_excluded_total += test_prepared["n_feature_null_excluded"]
        stock_ids_test = panel.loc[test_prepared["retained_index"], "stock_id"].to_numpy()

        for model_name in MODEL_NAMES_FULL:
            fit_result = fit_predict_specialist_fold(
                model_name, train_prepared, test_prepared, return_proba=True)
            fold_results.append({
                "model_name": MODEL_NAME_SHORT_CODES[model_name],
                "arm": "A",
                "fold_id": fold_id,
                "stock_id": stock_ids_test.tolist(),
                "trade_date": list(test_prepared["trade_date"]),
                "y_proba": fit_result["y_proba"],
                "proba_classes": fit_result["proba_classes"],
            })
        elapsed = time.perf_counter() - t0
        n_test = len(test_prepared["y"])
        fold_timings.append({"fold": fold_id, "elapsed_seconds": elapsed, "n_test": n_test})
        print(f"  fold={fold_id} n_test={n_test} elapsed={elapsed:.2f}s")

    oof_matrix = assemble_oof_matrix(fold_results, target_column=target)
    oof_matrix["trade_date"] = pd.to_datetime(oof_matrix["trade_date"])

    reject_rows_at_or_after(oof_matrix, "trade_date", HOLDOUT_START_DATE)  # 守衛 3

    oof_matrix["split_segment"] = np.where(
        oof_matrix["fold_id"] <= LAST_META_TRAIN_FOLD, "meta_train", "meta_eval")

    if max_folds is None:
        expected_segments = EXPECTED_SEGMENT_COUNTS[target]
        n_meta_train_pre_purge = int((oof_matrix["split_segment"] == "meta_train").sum())
        n_meta_eval = int((oof_matrix["split_segment"] == "meta_eval").sum())
        if n_meta_train_pre_purge != expected_segments["meta_train"]:
            raise OofGenerationError(
                f"[{target}] meta_train 列數（二階 Purge 前）{n_meta_train_pre_purge} "
                f"與預期 {expected_segments['meta_train']} 不符——拒絕產出。"
            )
        if n_meta_eval != expected_segments["meta_eval"]:
            raise OofGenerationError(
                f"[{target}] meta_eval 列數 {n_meta_eval} 與預期 "
                f"{expected_segments['meta_eval']} 不符——拒絕產出。"
            )

    # 合併回 label_end_col（二階 Purge 需要）與兩個原始標籤欄
    # target_up_down／target_triple_barrier（Gate A §4.6：「對應 target
    # 的原始標籤，兩欄皆保留，不論本次以哪個 target 為準」——本面板本身
    # 只會有一欄非 NULL，另一欄結構上不存在於這份面板的 target 定義，
    # 但欄位本身仍照文件約定保留，供 Meta-Learner 監督式訓練與
    # select_best_specialist() 使用）。assemble_oof_matrix() 的輸出刻意
    # 不含這些（它只管機率欄組裝），面板專屬的補充由呼叫端（本腳本）
    # 負責，保持 stacking.py 的契約穩定、不用因為下游需要而反覆擴張。
    # 同時合併 META_REGIME_FEATURE_COLS——build_meta_learner_input() 的
    # P1 守衛（2026-09-15 補件）要求這兩欄必須存在，缺一即結構性拒絕；
    # 少了這步會讓下游報告腳本在讀取階段就 abort（已用真實面板實測
    # 確認過這個順序：先漏了這兩欄，P1 守衛立即攔下，證明守衛本身有效）。
    lookup_cols = [
        "stock_id", "trade_date", label_end_col,
        "target_up_down", "target_triple_barrier",
        *META_REGIME_FEATURE_COLS,
    ]
    label_lookup = panel[lookup_cols].drop_duplicates()
    label_lookup["trade_date"] = pd.to_datetime(label_lookup["trade_date"])
    before_merge = len(oof_matrix)
    oof_matrix = oof_matrix.merge(label_lookup, on=["stock_id", "trade_date"], how="left")
    if len(oof_matrix) != before_merge:
        raise OofGenerationError(
            f"合併 {label_end_col}／標籤欄／regime 欄後列數由 {before_merge} 變為 "
            f"{len(oof_matrix)}——label_lookup 出現重複鍵，拒絕產出。"
        )
    must_not_be_null = [label_end_col, target, *META_REGIME_FEATURE_COLS]
    still_null = [c for c in must_not_be_null if oof_matrix[c].isna().any()]
    if still_null:
        raise OofGenerationError(
            f"合併後仍有列缺以下欄位：{still_null}——"
            "(stock_id, trade_date) 對不上面板，拒絕產出。"
        )
    oof_matrix[target] = oof_matrix[target].astype(int)

    oof_matrix = apply_second_stage_purge(
        oof_matrix, META_EVAL_START_DATE, label_end_col=label_end_col)

    n_purged = int((oof_matrix["split_segment"] == "purged").sum())
    if max_folds is None and n_purged != EXPECTED_PURGE_COUNTS[target]:
        raise OofGenerationError(
            f"二階 Purge 排除列數 {n_purged} 與預期 {EXPECTED_PURGE_COUNTS[target]} "
            "不符——拒絕產出。"
        )

    return {
        "target": target,
        "panel_path": str(panel_path),
        "panel_sha256": sha256,
        "holdout_start_date": HOLDOUT_START_DATE.isoformat(),
        "meta_eval_start_date": META_EVAL_START_DATE.isoformat(),
        "splitter_config": {
            "train_window_size": TRAIN_WINDOW_SIZE,
            "test_window_size": TEST_WINDOW_SIZE,
            "embargo_days": EMBARGO_DAYS,
            "label_horizon": cfg["label_horizon"],
            "label_end_date_col": label_end_col,
            "require_label_end_date": True,
        },
        "n_folds_processed": n_folds_processed,
        "max_folds": max_folds,
        "fold_timings": fold_timings,
        "oof_matrix": oof_matrix,
        "row_counts": {
            "total": len(oof_matrix),
            "meta_train": int((oof_matrix["split_segment"] == "meta_train").sum()),
            "meta_eval": int((oof_matrix["split_segment"] == "meta_eval").sum()),
            "purged": n_purged,
        },
        # prepare_fold_data() 規則 (a)(b) 的排除列數（僅測試窗，見上方
        # 迴圈內註解）——解釋「折測試窗原始列數」與 row_counts 之間的
        # 落差，供證據 JSON 稽核（審查方第二節第 1 點要求）。
        "test_window_exclusions": {
            "rule_a_target_null": n_target_null_excluded_total,
            "rule_b_feature_null": n_feature_null_excluded_total,
        },
    }


def main(
    target: str,
    panel_path: Path,
    output_dir: Path,
    evidence_dir: Path,
    max_folds: Optional[int] = None,
) -> Path:
    if not panel_path.exists():
        raise OofGenerationError(f"parquet 檔案不存在：{panel_path}")
    print(f"target={target} panel_path={panel_path} max_folds={max_folds}")

    t0 = time.perf_counter()
    result = generate_oof_for_target(target, panel_path, max_folds=max_folds)
    total_elapsed = time.perf_counter() - t0

    oof_matrix = result.pop("oof_matrix")
    print(f"row_counts={result['row_counts']}")
    print(f"total_elapsed_seconds={total_elapsed:.2f}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = f"_probe{max_folds}folds" if max_folds is not None else ""
    output_path = output_dir / f"oof_{target}_{timestamp}{suffix}.parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    oof_matrix.to_parquet(output_path, index=False)
    print(f"oof_parquet={output_path}")

    result["oof_parquet_path"] = str(output_path)
    result["oof_parquet_sha256"] = compute_file_sha256(output_path)
    result["oof_row_count"] = len(oof_matrix)
    result["total_elapsed_seconds"] = total_elapsed

    commit_info = get_script_commit_info()
    result["script_commit"] = commit_info["commit"]
    result["script_dirty"] = commit_info["dirty"]
    result["script_dirty_paths"] = commit_info["dirty_paths"]
    result["script_untracked_paths"] = commit_info["untracked_paths"]
    result["run_timestamp"] = datetime.now(timezone.utc).isoformat()
    print(f"script_commit={result['script_commit']} dirty={result['script_dirty']}")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"UG_G3_SB4_oof_generation_{target}{suffix}.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"evidence_json={evidence_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGET_CONFIG))
    parser.add_argument("--panel-path", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OOF_OUTPUT_DIR))
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_OUTPUT_DIR))
    parser.add_argument("--max-folds", type=int, default=None,
                         help="限制實際訓練的折數，供單折探測使用（不影響守衛 2 的完整"
                              "邊界驗證與守衛 4/5 的迴歸基準比對，探測模式下後兩者自動略過）")
    args = parser.parse_args()

    arg_panel_path = (
        Path(args.panel_path) if args.panel_path
        else DEFAULT_PANEL_DIR / f"panel_{args.target}_20260912.parquet"
    )

    main(
        target=args.target,
        panel_path=arg_panel_path,
        output_dir=Path(args.output_dir),
        evidence_dir=Path(args.evidence_dir),
        max_folds=args.max_folds,
    )
