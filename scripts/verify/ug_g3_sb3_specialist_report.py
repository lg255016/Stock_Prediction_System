# -*- coding: utf-8 -*-
"""`UG-G3-SB3` 段級報告產生器（PO 2026-09-13 核准命名／參數／守衛）。

**僅限 dev container 內執行**（依賴 sklearn／lightgbm／xgboost，見
`CLAUDE.md` §13.0）——host 環境走 fallback 實作，任何模型行為宣稱皆無效。

**唯讀，結構上不可能連 DB**：只讀取已凍結的 parquet 面板與
`doc/upgrade/gates/evidence/UG_G3_SB3_panel_export.json`，只寫一份輸出
JSON；不匯入任何資料庫驅動程式，不讀取任何資料庫連線環境變數
（`tests/test_ug_g3_sb3_specialist_report.py` 的 `NoDatabaseImportTests`
直接掃描本檔原始碼字面，確認未提及那些名稱——本段落連提都不提，
避免說明文字本身讓那條結構檢查失去意義）。

四項守衛（任一不符即 abort，不降級、不警告帶過）：
1. parquet sha256 必須等於 evidence JSON 記載值（`verify_panel_sha256`）。
2. `WalkForwardSplitter` 一律以 `require_label_end_date=True` 建構
   （`build_splitter`）——建構時就拒絕 fallback，不是事後才發現。
3. 面板必須同時具備 `label_end_date`／`label_end_date_tb` 兩欄
   （`assert_required_columns`）。
4. 每個 Fold 的 `purge_mode` 必須為 `"exact"`（`assert_purge_mode_exact`）
   ——防禦性重驗：守衛 2 已保證這件事恆成立，本檢查沒有不修改
   `WalkForwardSplitter` 內部邏輯就能構造出的端到端 known-FAIL 案例，
   比照 `prepare_fold_data()` 規則 (c) 防禦性斷言的既有處理方式，誠實
   揭露而非硬湊一個。

固定參數（`UG_G3_SB3_GATE_A_PROPOSAL.md` §2.3 既定值，不對外開放調整）：
`train_window_size=60, test_window_size=20, step_size=20（預設）,
embargo_days=0`；`target_triple_barrier` 用
`label_horizon=5, label_end_date_col="label_end_date_tb"`；
`target_up_down` 用 `label_horizon=1, label_end_date_col="label_end_date"`。

情緒子集股票（供 B 臂額外揭露）現場從**這次實際載入的面板**計算
（`sentiment_mean` 非 NULL 的相異 `stock_id`），不複製
`UG_G3_SB3_panel_export.json` 既有的 20/458 清單——避免同一個數字在兩處
各自維護、其中一處日後漂移而沒人發現。
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
from typing import Any, Dict, Iterable, List, Optional

# 讓 `python scripts/verify/ug_g3_sb3_specialist_report.py` 可從任何工作目錄
# 直接執行（不依賴 cwd 或 -m 呼叫方式）——比照既有
# `scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py` 的既定慣例。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

try:
    import sklearn  # noqa: F401
except ImportError as exc:  # pragma: no cover - 環境檢查，不計入覆蓋率
    raise RuntimeError(
        "本腳本依賴 sklearn／lightgbm／xgboost，僅能在 dev container 內"
        "執行（見 CLAUDE.md §13.0）。host 環境缺少這些套件，任何模型行為"
        "宣稱皆無效。"
    ) from exc

from src.ml.baseline_models import ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS
from src.ml.specialist_training import (
    compute_boundary_interior_metrics,
    compute_per_class_metrics,
    fit_predict_specialist_fold,
    iter_model_arm_pairs,
    run_fold_for_arms,
    summarize_leakage_diagnosis,
)
from src.ml.time_series_split import WalkForwardSplitter


class PanelIntegrityError(RuntimeError):
    """面板／切分器守衛失敗——結構性 abort，不降級、不跳過。"""


# 兩個 target 的固定切分參數（Gate A 提案 §2.3，PO 已核准，不對外開放調整）。
TARGET_CONFIG: Dict[str, Dict[str, Any]] = {
    "target_up_down": {
        "label_horizon": 1,
        "label_end_date_col": "label_end_date",
        "labels": [0, 1],
    },
    "target_triple_barrier": {
        "label_horizon": 5,
        "label_end_date_col": "label_end_date_tb",
        "labels": [-1, 0, 1],
    },
}

TRAIN_WINDOW_SIZE = 60
TEST_WINDOW_SIZE = 20
EMBARGO_DAYS = 0

DEFAULT_PANEL_DIR = Path("/workspaces/Database_Backups/Stock_Prediction_System2/ml_panels")
DEFAULT_EVIDENCE_JSON = Path("doc/upgrade/gates/evidence/UG_G3_SB3_panel_export.json")
DEFAULT_OUTPUT_DIR = Path("doc/upgrade/gates/evidence")


def compute_file_sha256(path: Path) -> str:
    """串流計算檔案 sha256，避免大檔一次讀進記憶體。"""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# 本腳本自身輸出的報告 JSON——覆蓋它不算「工作樹髒」（PO 2026-09-13：
# 否則每次全量重跑覆蓋同一份輸出檔，都會讓 script_dirty 自我宣告 True，
# 這個欄位就沒有資訊量）。
_REPORT_OUTPUT_PATH_RE = re.compile(r"^doc/upgrade/gates/evidence/UG_G3_SB3_report_.*\.json$")


def _is_report_output_path(path: str) -> bool:
    return bool(_REPORT_OUTPUT_PATH_RE.match(path.replace("\\", "/")))


def get_script_commit_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """執行時的腳本 commit hash 與工作樹清潔狀態（PO 2026-09-13 要求），
    供輸出 JSON 記錄——全量跑完覆蓋同一檔時，回報須能追溯是哪個版本
    產出的。

    容器內 git 有兩個既有環境坑，皆用**逐次 `-c` 授權、不動全域／本機
    設定**處理（比照既有 `scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py`
    的 `load_old_feature_aggregator_class()` 慣例）：

    1. bind mount 造成 `dubious ownership`——`-c safe.directory=<root>`。
    2. 容器未設 `core.autocrlf`，主機 CRLF 工作副本在容器內會被 git 算成
       整檔修改（VERIFIED THIS SESSION：不加此參數時 `status --porcelain`
       回 43 行，加了立即降到與主機一致的 6 行）——`-c core.autocrlf=true`。

    `dirty` 只看**追蹤檔案**的修改，且排除本腳本自身輸出的報告 JSON；
    未追蹤檔案（如本機 `.claude/settings.local.json`）不計入 `dirty`，
    另列 `untracked_paths` 供資訊揭露。`git rev-parse` 失敗時直接拋
    `PanelIntegrityError`，不得把 `commit` 寫成 `None`——版本不明的報告
    不得產出。
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    git_common_opts = ["-c", f"safe.directory={root}", "-c", "core.autocrlf=true"]

    try:
        commit_hash = subprocess.run(
            ["git", *git_common_opts, "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise PanelIntegrityError(
            f"無法取得 git commit hash（{root}）：{exc}——版本不明的報告不得產出。"
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
    dirty = bool(dirty_paths)
    if dirty:
        print(
            "WARNING: 工作樹有未 commit 的追蹤檔變更（已排除本腳本自身輸出的 "
            f"report JSON）——script_commit 不能保證對應實際執行的程式碼："
            f"{dirty_paths}"
        )
    return {
        "commit": commit_hash,
        "dirty": dirty,
        "dirty_paths": dirty_paths,
        "untracked_paths": untracked,
    }


def verify_panel_sha256(panel_path: Path, target: str, evidence_json_path: Path) -> str:
    """守衛 1：parquet 實際 sha256 必須等於 evidence JSON 記載值，不符即 abort。"""
    with open(evidence_json_path, "r", encoding="utf-8") as f:
        evidence = json.load(f)
    try:
        expected = evidence["part_B_panel_export"]["targets"][target]["sha256"]
    except KeyError as exc:
        raise PanelIntegrityError(
            f"evidence JSON（{evidence_json_path}）沒有 target={target!r} 的 sha256 記載——"
            "無法驗證面板來源，拒絕產出報告。"
        ) from exc

    actual = compute_file_sha256(panel_path)
    if actual != expected:
        raise PanelIntegrityError(
            f"parquet sha256 不符 evidence JSON 記載值——"
            f"expected={expected} actual={actual}（{panel_path}）。"
            "拒絕對未經複核的面板產出報告。"
        )
    return actual


def build_splitter(target: str, mode: str) -> WalkForwardSplitter:
    """守衛 2：一律以 `require_label_end_date=True` 建構——建構時就拒絕
    fallback，不是事後才發現。"""
    cfg = TARGET_CONFIG[target]
    return WalkForwardSplitter(
        train_window_size=TRAIN_WINDOW_SIZE,
        test_window_size=TEST_WINDOW_SIZE,
        mode=mode,
        embargo_days=EMBARGO_DAYS,
        label_horizon=cfg["label_horizon"],
        label_end_date_col=cfg["label_end_date_col"],
        require_label_end_date=True,
    )


def assert_required_columns(panel: pd.DataFrame, required: Iterable[str]) -> None:
    """守衛 3：面板必須同時具備所有必要欄位，缺一即 abort。"""
    missing = [col for col in required if col not in panel.columns]
    if missing:
        raise PanelIntegrityError(
            f"面板缺少必要欄位：{missing}——拒絕產出報告。"
        )


def assert_purge_mode_exact(fold_meta: Dict[str, Any]) -> None:
    """守衛 4（防禦性重驗）：每個 Fold 的 `purge_mode` 必須為 `"exact"`。"""
    if fold_meta.get("purge_mode") != "exact":
        raise PanelIntegrityError(
            f"Fold {fold_meta.get('fold')} 的 purge_mode="
            f"{fold_meta.get('purge_mode')!r}，非 'exact'——拒絕產出報告"
            "（防禦性重驗，不只信任建構參數）。"
        )


def assert_panel_has_rangeindex(panel: pd.DataFrame) -> None:
    """面板索引必須是預設 `RangeIndex`（PO 2026-09-13 指出）：
    `prepare_fold_data()` 回傳的 `retained_index` 是 `sub.index`（pandas
    索引標籤），本腳本拿它對 `panel` 做 `.loc` 取股票代號（情緒子集
    遮罩）——這個假設只有在面板索引標籤與整數位置一致（即讀 parquet
    後未經任何列過濾的預設 RangeIndex）時才成立。若日後有呼叫端先對
    面板做過濾再傳進來，索引標籤與位置不再一致，`.loc` 會取到錯誤的
    列且不會報錯——因此在這裡明確斷言，不留給下游默默算錯。"""
    if not panel.index.equals(pd.RangeIndex(len(panel))):
        raise PanelIntegrityError(
            "面板索引不是預設 RangeIndex（可能已被過濾或重新索引）——"
            "情緒子集判定依賴 retained_index 對應 panel 的整數位置，"
            "非 RangeIndex 時這個假設不成立，拒絕產出報告。"
        )


def determine_sentiment_subset_stock_ids(panel: pd.DataFrame) -> List[str]:
    """情緒子集股票：面板現場計算 `sentiment_mean` 非 NULL 的相異
    `stock_id`，不複製 evidence JSON 既有清單。"""
    if "sentiment_mean" not in panel.columns:
        return []
    subset = panel.loc[panel["sentiment_mean"].notna(), "stock_id"].unique().tolist()
    return sorted(subset)


# 兩種子集口徑並列，各自的定義寫進輸出 JSON 的 `subset_definitions`
# （PO 2026-09-13 要求，不只留在原始碼裡）：
# - sentiment_subset：股票子集——「這支股票在面板任何時點曾有情緒訊號」。
# - signal_rows_subset：列子集——「這一列本身真的有情緒訊號」。前者較寬
#   （同一檔股票的其他日期即使沒訊號也算在子集內），後者才是 B 臂在本
#   面板上唯一真的「多出資訊」的列（面板整體 sentiment_mean 覆蓋率僅
#   0.49%，其餘列的情緒衍生欄是聚合層補的 0.0 常數，對模型沒有資訊）。
SUBSET_DEFINITIONS = {
    "sentiment_subset": "股票子集：面板中曾出現過非 NULL sentiment_mean 的股票，取其全部列",
    "signal_rows_subset": "列子集：article_count>0 或 sentiment_5d_ma 非 NULL 的列本身"
                           "（B 臂在本面板上唯一真的多出資訊的列）",
}


def determine_signal_row_mask(panel: pd.DataFrame) -> pd.Series:
    """訊號列遮罩：`article_count>0` 或 `sentiment_5d_ma` 非 NULL 的列
    （PO 2026-09-13 要求）。與 `determine_sentiment_subset_stock_ids()`
    的差別：後者是「股票」子集（同一檔股票的其他日期即使沒訊號也算在
    子集內），本函式是「列」子集——只挑真的帶有情緒訊號的那些列。

    Returns:
        與 `panel` 等長、索引相同的布林 Series；兩個必要欄位缺一即回傳
        全 `False`（不報錯，比照 `determine_sentiment_subset_stock_ids()`
        對缺欄的處理方式）。
    """
    if "article_count" not in panel.columns or "sentiment_5d_ma" not in panel.columns:
        return pd.Series(False, index=panel.index)
    return (panel["article_count"] > 0) | (panel["sentiment_5d_ma"].notna())


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# `PureTechnicalModelFactory.create_model("logistic_regression")` 硬編碼的
# max_iter（src/ml/baseline_models.py）——這裡鏡射同一個值，只用於彙總
# 「撞滿 max_iter 的 Fold 數」，非重新定義該常數的權威來源。
LR_MAX_ITER = 500


def _aggregate_per_class_group(
    per_class_entries: List[Optional[Dict[str, Any]]],
    n_values: List[int],
    labels: List[Any],
) -> Dict[str, Any]:
    """對一組（每 Fold 一個）per-class 字典彙總：macro F1 的
    中位數／平均／最小／最大、逐類別平均 recall／f1（只在該 Fold 該類別
    `support>0` 時列入，避免類別缺席的 Fold 把平均拉向 0，並揭露列入
    的 Fold 數）、`n` 總和。

    `per_class_entries[i]` 為 `None` 或不含 `"macro_f1"` 時，該 Fold 不
    計入 macro F1 分布（比照 `summarize_leakage_diagnosis()` 略過
    `None` 的既有慣例）。
    """
    macro_f1_values = [
        pc["macro_f1"] for pc in per_class_entries
        if pc is not None and pc.get("macro_f1") is not None
    ]

    per_label: Dict[str, Any] = {}
    for label in labels:
        label_key = str(label)
        recalls, f1s = [], []
        for pc in per_class_entries:
            if pc is None or label_key not in pc:
                continue
            entry = pc[label_key]
            if entry.get("support", 0) > 0:
                recalls.append(entry["recall"])
                f1s.append(entry["f1"])
        per_label[label_key] = {
            "mean_recall": float(np.mean(recalls)) if recalls else None,
            "mean_f1": float(np.mean(f1s)) if f1s else None,
            "n_folds_with_support": len(recalls),
        }

    return {
        "macro_f1_median": float(np.median(macro_f1_values)) if macro_f1_values else None,
        "macro_f1_mean": float(np.mean(macro_f1_values)) if macro_f1_values else None,
        "macro_f1_min": float(np.min(macro_f1_values)) if macro_f1_values else None,
        "macro_f1_max": float(np.max(macro_f1_values)) if macro_f1_values else None,
        "n_folds_with_data": len(macro_f1_values),
        "n_total": int(sum(n_values)),
        "per_label": per_label,
    }


# 供 docstring 與輸出 JSON（`aggregate.majority_baseline.rule`）共用同一份
# 文字——規則本身是讀者判讀報告時需要的資訊，不能只留在原始碼裡
# （PO 2026-09-13 要求）。
MAJORITY_BASELINE_RULE = "訓練集多數類；票數並列時取數值最小者"


def compute_majority_baseline_predictions(y_train: Iterable[Any], n_test: int) -> np.ndarray:
    """訓練集多數類基線：對測試集全部預測訓練集裡最常見的類別，供
    Gate B 讀者判斷模型的 macro F1 是不是雜訊（PO 2026-09-13 要求）。
    票數並列時取數值最小者（`np.unique` 回傳遞增排序、`argmax` 取第一個
    最大值），確保可重現、不依賴任意 tie-break——即 `MAJORITY_BASELINE_RULE`。"""
    values, counts = np.unique(np.asarray(list(y_train)), return_counts=True)
    majority_class = values[np.argmax(counts)]
    return np.full(n_test, majority_class)


def compute_pair_aggregate(
    fold_records: List[Dict[str, Any]],
    labels: List[Any],
    model_name: str,
) -> Dict[str, Any]:
    """對一個 (model, arm) 的全部 Fold 紀錄，彙總全宇宙、情緒子集（股票）、
    訊號列子集（列，PO 2026-09-13 要求）各一組統計量，另加多數類基線
    （`majority_baseline`，全宇宙／情緒子集各一組）與 LR 撞滿 `max_iter`
    的 Fold 數（非 LR 恆為 0）。"""
    full = _aggregate_per_class_group(
        [f["per_class"] for f in fold_records],
        [f["n_test"] for f in fold_records],
        labels,
    )
    sentiment_subset = _aggregate_per_class_group(
        [f.get("sentiment_subset") for f in fold_records],
        [f.get("sentiment_subset", {}).get("n", 0) for f in fold_records],
        labels,
    )
    signal_rows_subset = _aggregate_per_class_group(
        [f.get("signal_rows_subset") for f in fold_records],
        [f.get("signal_rows_subset", {}).get("n", 0) for f in fold_records],
        labels,
    )
    majority_baseline_full = _aggregate_per_class_group(
        [f.get("majority_baseline", {}).get("full") for f in fold_records],
        [f["n_test"] for f in fold_records],
        labels,
    )
    majority_baseline_subset = _aggregate_per_class_group(
        [f.get("majority_baseline", {}).get("sentiment_subset") for f in fold_records],
        [f.get("sentiment_subset", {}).get("n", 0) for f in fold_records],
        labels,
    )
    n_lr_max_iter_hits = (
        sum(
            1 for f in fold_records
            if f.get("n_iter_") is not None and f["n_iter_"] >= LR_MAX_ITER
        )
        if model_name == "logistic_regression" else 0
    )
    return {
        "full": full,
        "sentiment_subset": sentiment_subset,
        "signal_rows_subset": signal_rows_subset,
        "majority_baseline": {
            "full": majority_baseline_full,
            "sentiment_subset": majority_baseline_subset,
            "rule": MAJORITY_BASELINE_RULE,
        },
        "n_lr_max_iter_hits": n_lr_max_iter_hits,
    }


def run_single_configuration(
    target: str,
    mode: str,
    models: List[str],
    arms: List[str],
    panel_path: Path,
    evidence_json_path: Path,
) -> Dict[str, Any]:
    """執行單一 (target, mode) 設定下、指定 models×arms 組合的全 Fold 報告。

    四項守衛依序執行（任一不符即 abort）：sha256 → 必要欄位 → 逐 Fold
    purge_mode。
    """
    if target not in TARGET_CONFIG:
        raise ValueError(f"不支援的 target: {target!r}，支援: {sorted(TARGET_CONFIG)}")
    cfg = TARGET_CONFIG[target]

    sha256 = verify_panel_sha256(panel_path, target, evidence_json_path)
    panel = pd.read_parquet(panel_path)
    assert_panel_has_rangeindex(panel)
    assert_required_columns(panel, ("label_end_date", "label_end_date_tb"))

    sentiment_subset_stock_ids = determine_sentiment_subset_stock_ids(panel)
    signal_row_mask = determine_signal_row_mask(panel)

    splitter = build_splitter(target, mode)

    requested_pairs = [
        (model_name, arm) for model_name, arm in iter_model_arm_pairs()
        if model_name in models and arm in arms
    ]
    if not requested_pairs:
        raise ValueError(
            f"models={models} 與 arms={arms} 組合出的合法 (model, arm) 配對為空——"
            "檢查是否誤把 LogisticRegression 指定給 B 臂。"
        )

    per_pair_folds: Dict[str, List[Dict[str, Any]]] = {
        f"{m}__{a}": [] for m, a in requested_pairs
    }
    per_pair_elapsed: Dict[str, float] = {f"{m}__{a}": 0.0 for m, a in requested_pairs}

    n_folds = 0
    for train_idx, test_idx, fold_meta in splitter.split(panel):
        assert_purge_mode_exact(fold_meta)
        n_folds += 1

        arm_data = run_fold_for_arms(
            panel, train_idx, test_idx,
            ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS,
        )

        for model_name, arm in requested_pairs:
            key = f"{model_name}__{arm}"
            train_prepared = arm_data[arm]["train"]
            test_prepared = arm_data[arm]["test"]

            t0 = time.perf_counter()
            fit_result = fit_predict_specialist_fold(model_name, train_prepared, test_prepared)
            elapsed = time.perf_counter() - t0
            per_pair_elapsed[key] += elapsed

            per_class = compute_per_class_metrics(
                fit_result["y_true"], fit_result["y_pred"], labels=cfg["labels"])
            boundary_interior = compute_boundary_interior_metrics(
                fit_result["trade_date"], fit_result["y_true"], fit_result["y_pred"],
                holding_period=cfg["label_horizon"])

            fold_record: Dict[str, Any] = {
                "fold": fold_meta["fold"],
                "purge_mode": fold_meta["purge_mode"],
                "n_train": fit_result["n_train"],
                "n_test": fit_result["n_test"],
                "n_target_null_excluded": {
                    "train": train_prepared["n_target_null_excluded"],
                    "test": test_prepared["n_target_null_excluded"],
                },
                "n_feature_null_excluded": {
                    "train": train_prepared["n_feature_null_excluded"],
                    "test": test_prepared["n_feature_null_excluded"],
                },
                "per_class": per_class,
                "boundary_interior": boundary_interior,
                "n_iter_": fit_result["n_iter_"],
                "elapsed_seconds": elapsed,
            }

            # 情緒子集對照（PO 2026-09-13 訂正）：提案 §3.4 要的是「限定在
            # 20 檔情緒子集的 A/B 對照」，兩臂都要算，不只 B 臂——沒有 A
            # 臂在同一批子集列上的數字，B 臂的子集分數就沒有可比對象。
            # 兩臂剔除後保留列相等（`run_fold_for_arms` 已保證），子集
            # 遮罩對兩臂相同。子集遮罩另供多數類基線（下方）共用。
            if sentiment_subset_stock_ids:
                stock_ids_test = panel.loc[fit_result["retained_index"], "stock_id"].to_numpy()
                subset_mask = np.isin(stock_ids_test, sentiment_subset_stock_ids)
                n_subset = int(subset_mask.sum())
            else:
                subset_mask = np.zeros(len(fit_result["y_true"]), dtype=bool)
                n_subset = 0

            if n_subset > 0:
                subset_metrics = compute_per_class_metrics(
                    fit_result["y_true"][subset_mask], fit_result["y_pred"][subset_mask],
                    labels=cfg["labels"])
            else:
                subset_metrics = {"macro_f1": None}
            subset_metrics["n"] = n_subset
            fold_record["sentiment_subset"] = subset_metrics

            # 多數類基線（PO 2026-09-13 要求）：訓練集多數類對測試集全量
            # 預測，供 Gate B 讀者判斷模型的 macro F1 是不是雜訊。全宇宙
            # 與情緒子集（沿用同一個 subset_mask）各算一組。
            majority_pred = compute_majority_baseline_predictions(
                train_prepared["y"], len(fit_result["y_true"]))
            majority_baseline_full = compute_per_class_metrics(
                fit_result["y_true"], majority_pred, labels=cfg["labels"])
            if n_subset > 0:
                majority_baseline_subset = compute_per_class_metrics(
                    fit_result["y_true"][subset_mask], majority_pred[subset_mask],
                    labels=cfg["labels"])
            else:
                majority_baseline_subset = {"macro_f1": None}
            majority_baseline_subset["n"] = n_subset
            fold_record["majority_baseline"] = {
                "full": majority_baseline_full,
                "sentiment_subset": majority_baseline_subset,
            }

            # 訊號列子集（PO 2026-09-13 要求）：面板 sentiment_mean 覆蓋率
            # 僅 0.49%，article_count>0／sentiment_5d_ma 非 NULL 的列才是
            # B 臂真的多出資訊的列——這是「覆蓋率不足」這句話的量化依據，
            # 樣本小到沒有統計力也要印出來，不能只讀到 A/B 差 ±0.01。
            signal_row_mask_test = signal_row_mask.loc[fit_result["retained_index"]].to_numpy()
            n_signal = int(signal_row_mask_test.sum())
            if n_signal > 0:
                signal_metrics = compute_per_class_metrics(
                    fit_result["y_true"][signal_row_mask_test],
                    fit_result["y_pred"][signal_row_mask_test],
                    labels=cfg["labels"])
            else:
                signal_metrics = {"macro_f1": None}
            signal_metrics["n"] = n_signal
            fold_record["signal_rows_subset"] = signal_metrics

            per_pair_folds[key].append(fold_record)

    results: Dict[str, Any] = {}
    for model_name, arm in requested_pairs:
        key = f"{model_name}__{arm}"
        results[key] = {
            "model": model_name,
            "arm": arm,
            "folds": per_pair_folds[key],
            "leakage_summary": summarize_leakage_diagnosis(
                [f["boundary_interior"] for f in per_pair_folds[key]]
            ),
            "aggregate": compute_pair_aggregate(per_pair_folds[key], cfg["labels"], model_name),
            "total_elapsed_seconds": per_pair_elapsed[key],
        }

    return {
        "target": target,
        "mode": mode,
        "panel_path": str(panel_path),
        "panel_sha256": sha256,
        "evidence_json": str(evidence_json_path),
        "splitter_config": {
            "train_window_size": TRAIN_WINDOW_SIZE,
            "test_window_size": TEST_WINDOW_SIZE,
            "embargo_days": EMBARGO_DAYS,
            "label_horizon": cfg["label_horizon"],
            "label_end_date_col": cfg["label_end_date_col"],
            "require_label_end_date": True,
        },
        "labels": cfg["labels"],
        "sentiment_subset_stock_ids": sentiment_subset_stock_ids,
        "subset_definitions": SUBSET_DEFINITIONS,
        "n_folds": n_folds,
        "results": results,
    }


def main(
    target: str,
    mode: str,
    models: List[str],
    arms: List[str],
    panel_path: Path,
    evidence_json_path: Path,
    output_path: Path,
) -> Path:
    if not panel_path.exists():
        raise PanelIntegrityError(f"parquet 檔案不存在：{panel_path}")
    print(f"panel_path={panel_path}")

    report = run_single_configuration(target, mode, models, arms, panel_path, evidence_json_path)
    print(f"panel_sha256={report['panel_sha256']}")
    print(f"n_folds={report['n_folds']}")
    print(f"sentiment_subset_stock_ids={report['sentiment_subset_stock_ids']}")

    commit_info = get_script_commit_info()
    report["script_commit"] = commit_info["commit"]
    report["script_dirty"] = commit_info["dirty"]
    report["script_dirty_paths"] = commit_info["dirty_paths"]
    report["script_untracked_paths"] = commit_info["untracked_paths"]
    report["run_timestamp"] = datetime.now(timezone.utc).isoformat()
    print(f"script_commit={report['script_commit']} dirty={report['script_dirty']}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"output={output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGET_CONFIG))
    parser.add_argument("--mode", default="rolling", choices=["rolling", "expanding"])
    parser.add_argument("--models", default=",".join(
        sorted({m for m, _ in iter_model_arm_pairs()})))
    parser.add_argument("--arms", default="A,B")
    parser.add_argument("--panel-path", default=None)
    parser.add_argument("--evidence-json", default=str(DEFAULT_EVIDENCE_JSON))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    arg_models = [m.strip() for m in args.models.split(",") if m.strip()]
    arg_arms = [a.strip() for a in args.arms.split(",") if a.strip()]

    arg_panel_path = (
        Path(args.panel_path) if args.panel_path
        else DEFAULT_PANEL_DIR / f"panel_{args.target}_20260912.parquet"
    )
    arg_output_path = (
        Path(args.output) if args.output
        else DEFAULT_OUTPUT_DIR / f"UG_G3_SB3_report_{args.target}_{args.mode}.json"
    )

    main(
        target=args.target,
        mode=args.mode,
        models=arg_models,
        arms=arg_arms,
        panel_path=arg_panel_path,
        evidence_json_path=Path(args.evidence_json),
        output_path=arg_output_path,
    )
