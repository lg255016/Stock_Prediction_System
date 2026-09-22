# -*- coding: utf-8 -*-
"""`UG-G3-SB4` 段級報告產生器（PO 2026-09-15 核准進入腳本階段）。

**僅限 dev container 內執行**（依賴 sklearn，見 `CLAUDE.md` §13.0）。

**唯讀，結構上不可能連 DB**：只讀取 `ug_g3_sb4_oof_generation.py` 產生的
OOF parquet，只寫一份報告 JSON；不匯入任何資料庫驅動程式。

讀入 OOF 矩陣後：
1. `select_best_specialist()`（Meta-Train 段挑選、Meta-Eval 段報告）——
   Meta-Train 段的硬預測（各 Specialist 機率欄 `argmax`）先組成長格式，
   選出最佳單一 Specialist。
2. `Meta(A)`——`LogisticRegression` 與 `RidgeClassifier` 各自在
   `build_meta_learner_input()` 產生的 Meta-Train 矩陣上訓練，
   在 Meta-Eval 矩陣上評估。
3. 三者（`Meta(A)-LR`／`Meta(A)-Ridge`／`Best Single Specialist`）皆在
   Meta-Eval 段以 macro F1 並列報告（Gate A §3.1，PO 2026-09-15 核准的
   兩者並列設計——Arm B 已排除，不產出 `Meta(A+B)`）。

腳本層守衛（任一不符即 abort）：
1. OOF parquet sha256 必須等於同批 `ug_g3_sb4_oof_generation.py` 輸出的
   `UG_G3_SB4_oof_generation_<target>.json` 記載值。
2. `split_segment` 值域只能是 `{"meta_train", "meta_eval", "purged"}`。
3. 三段列數（`meta_train`／`meta_eval`／`purged`）與 OOF 產生階段的證據
   JSON 記載值一致（防禦性重驗，不只信任讀到的檔案本身沒被動過）。
4. 讀取端呼叫 `reject_rows_at_or_after()` 二次確認零 Holdout 列。
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

from src.ml.stacking import (
    EXPECTED_MODEL_NAMES,
    HOLDOUT_START_DATE,
    SELECTION_METRIC,
    TARGET_CLASS_DOMAINS,
    build_meta_learner_input,
    reject_rows_at_or_after,
    select_best_specialist,
)


class MetaLearnerReportError(RuntimeError):
    """OOF 矩陣／守衛失敗——結構性 abort，不降級、不跳過。"""


DEFAULT_OOF_DIR = Path("/workspaces/Database_Backups/Stock_Prediction_System2/ml_panels")
DEFAULT_EVIDENCE_DIR = Path("doc/upgrade/gates/evidence")

_REPORT_OUTPUT_PATH_RE = re.compile(
    r"^doc/upgrade/gates/evidence/UG_G3_SB4_meta_learner_report_.*\.json$")


def _is_report_output_path(path: str) -> bool:
    return bool(_REPORT_OUTPUT_PATH_RE.match(path.replace("\\", "/")))


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_script_commit_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """比照 `ug_g3_sb4_oof_generation.py::get_script_commit_info()`。"""
    root = repo_root or Path(__file__).resolve().parents[2]
    git_common_opts = ["-c", f"safe.directory={root}", "-c", "core.autocrlf=true"]
    try:
        commit_hash = subprocess.run(
            ["git", *git_common_opts, "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise MetaLearnerReportError(
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


def _class_token_local(target_column: str, cls: int) -> str:
    """與 `src.ml.stacking._class_token()` 邏輯一致的本地鏡射版本
    （該函式為私有實作細節，不對外匯出；本腳本組欄名需要同一套規則，
    刻意保持與其定義同步而非改私有函式為公開——變更 stacking.py 的
    公開介面需另一輪紅測複核，本腳本層級的小鏡射比較輕）。"""
    if target_column == "target_triple_barrier":
        mapping = {-1: "m1", 0: "0", 1: "p1"}
        return mapping[cls]
    return str(int(cls))


def verify_oof_sha256(oof_path: Path, oof_generation_evidence_path: Path) -> str:
    """守衛 1：OOF parquet sha256 必須等於 OOF 產生階段證據 JSON 記載值。"""
    with open(oof_generation_evidence_path, "r", encoding="utf-8") as f:
        gen_evidence = json.load(f)
    expected = gen_evidence["oof_parquet_sha256"]
    actual = compute_file_sha256(oof_path)
    if actual != expected:
        raise MetaLearnerReportError(
            f"OOF parquet sha256 不符 OOF 產生階段記載值——"
            f"expected={expected} actual={actual}（{oof_path}）。"
            "拒絕對未經複核的 OOF 矩陣產出報告。"
        )
    return actual, gen_evidence


def assert_segment_value_domain(oof_df: pd.DataFrame) -> None:
    """守衛 2：`split_segment` 值域只能是三者之一。"""
    bad = set(oof_df["split_segment"].unique()) - {"meta_train", "meta_eval", "purged"}
    if bad:
        raise MetaLearnerReportError(
            f"split_segment 出現非預期值：{sorted(bad)}——拒絕產出報告。"
        )


def assert_row_counts_match_generation(oof_df: pd.DataFrame, gen_evidence: Dict[str, Any]) -> None:
    """守衛 3：三段列數須與 OOF 產生階段證據 JSON 記載值一致（防禦性
    重驗，不只信任讀到的檔案本身沒被動過）。"""
    actual = {
        "total": len(oof_df),
        "meta_train": int((oof_df["split_segment"] == "meta_train").sum()),
        "meta_eval": int((oof_df["split_segment"] == "meta_eval").sum()),
        "purged": int((oof_df["split_segment"] == "purged").sum()),
    }
    expected = gen_evidence["row_counts"]
    if actual != expected:
        raise MetaLearnerReportError(
            f"三段列數與 OOF 產生階段記載值不符——expected={expected} "
            f"actual={actual}。拒絕產出報告。"
        )


def build_long_format_for_selection(
    oof_df: pd.DataFrame,
    target_column: str,
    segment: str,
    return_exclusion_counts: bool = False,
):
    """把寬格式 OOF 矩陣（一列一樣本、欄為 model×class 機率）轉成
    `select_best_specialist()` 需要的長格式（一列一 (model, 樣本)，
    含 `model_name`／`y_true`／`y_pred`／`split_segment`）。`y_pred` 由
    該模型機率欄的 `argmax` 反推類別（`class_token` 的反向對照）。

    2026-09-15 訂正：缺席類別欄是 `NaN`（T5 設計，見
    `src/ml/stacking.py`），`np.argmax` 對含 `NaN` 的列有未定義／誤導性
    行為（`NaN` 在比較中通常表現得像「最大」，會讓 `argmax` 指向缺席
    類別本身）——該 (model, 列) 組合須整列排除，不得帶著錯誤的 `y_pred`
    進入 `select_best_specialist()`。`return_exclusion_counts=True` 時
    額外回傳逐模型排除數的字典。"""
    domain = TARGET_CLASS_DOMAINS[target_column]
    sub = oof_df.loc[oof_df["split_segment"] == segment]

    rows = []
    exclusion_counts: Dict[str, int] = {}
    for model in sorted(EXPECTED_MODEL_NAMES):
        prob_cols = [f"{model}_A_p{_class_token_local(target_column, cls)}" for cls in domain]
        probs = sub[prob_cols].to_numpy()
        valid_mask = ~np.isnan(probs).any(axis=1)
        n_excluded = int((~valid_mask).sum())
        if n_excluded:
            exclusion_counts[model] = n_excluded

        pred_idx = np.argmax(probs[valid_mask], axis=1)
        y_pred = np.array([domain[i] for i in pred_idx])
        rows.append(pd.DataFrame({
            "model_name": model,
            "y_true": sub.loc[valid_mask, target_column].to_numpy(),
            "y_pred": y_pred,
            "split_segment": segment,
        }))
    long_df = pd.concat(rows, ignore_index=True)

    if return_exclusion_counts:
        return long_df, exclusion_counts
    return long_df


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


# Gate A §2.5（`VERIFIED THIS SESSION`）：Holdout 段（折 33～42）的
# `sentiment_mean` 非 NULL 列數，**引用既有登記值，不得讀取 Holdout 列
# 重新計算**（本腳本結構上也讀不到 Holdout 列——OOF 矩陣本來就不含它，
# 見 `iter_oof_folds()`）。僅供對照，說明折 0～32 為何是 0／0。
HOLDOUT_SENTIMENT_SIGNAL_ROWS_CITED = 630


def compute_majority_baseline_predictions(y_train: np.ndarray, n_test: int) -> np.ndarray:
    """訓練集多數類基線：對測試集全部預測訓練集裡最常見的類別（比照
    `ug_g3_sb3_specialist_report.py` 的既定寫法，票數並列時取數值最小者，
    `np.unique` 遞增排序＋`argmax` 取第一個最大值，確保可重現）。"""
    values, counts = np.unique(np.asarray(list(y_train)), return_counts=True)
    majority_class = values[np.argmax(counts)]
    return np.full(n_test, majority_class)


def run_report(
    target: str,
    oof_path: Path,
    oof_generation_evidence_path: Path,
) -> Dict[str, Any]:
    import warnings

    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.metrics import f1_score
    from sklearn.preprocessing import StandardScaler

    from src.ml.specialist_training import compute_per_class_metrics

    sha256, gen_evidence = verify_oof_sha256(oof_path, oof_generation_evidence_path)
    oof_df = pd.read_parquet(oof_path)
    assert_segment_value_domain(oof_df)
    assert_row_counts_match_generation(oof_df, gen_evidence)
    reject_rows_at_or_after(oof_df, "trade_date", HOLDOUT_START_DATE)

    labels = TARGET_CLASS_DOMAINS[target]

    # ---- 0. 三段訊號列數揭露（審查方第二節第 5 點要求） ----
    # 讀原始凍結面板（sha256 已在 OOF 產生階段驗證，這裡信任同一份
    # panel_sha256 記載，不重複驗證），只為了這一項診斷用的
    # sentiment_mean 計數——刻意不併入 OOF parquet 本身（那會讓
    # build_meta_learner_input() 的欄位允許清單檢查多一項要處理）。
    panel = pd.read_parquet(gen_evidence["panel_path"])
    panel_key = panel[["stock_id", "trade_date", "sentiment_mean"]].drop_duplicates(
        subset=["stock_id", "trade_date"])
    panel_key["trade_date"] = pd.to_datetime(panel_key["trade_date"])
    oof_keyed = oof_df.merge(panel_key, on=["stock_id", "trade_date"], how="left")
    signal_row_counts = {
        "meta_train": int(oof_keyed.loc[
            oof_keyed["split_segment"] == "meta_train", "sentiment_mean"].notna().sum()),
        "meta_eval": int(oof_keyed.loc[
            oof_keyed["split_segment"] == "meta_eval", "sentiment_mean"].notna().sum()),
        "holdout_cited_from_gate_a_2_5": HOLDOUT_SENTIMENT_SIGNAL_ROWS_CITED,
    }

    # ---- 1. Best Single Specialist（Meta-Train 選、Meta-Eval 報，§3.4） ----
    long_meta_train, train_selection_exclusions = build_long_format_for_selection(
        oof_df, target, "meta_train", return_exclusion_counts=True)
    best_model, ranking_df = select_best_specialist(long_meta_train, target_column=target)

    long_meta_eval, eval_selection_exclusions = build_long_format_for_selection(
        oof_df, target, "meta_eval", return_exclusion_counts=True)
    best_eval_rows = long_meta_eval[long_meta_eval["model_name"] == best_model]
    best_specialist_per_class = compute_per_class_metrics(
        best_eval_rows["y_true"], best_eval_rows["y_pred"], labels=labels)

    # ---- 2. Meta(A)：LogisticRegression 與 RidgeClassifier ----
    # P8（stacking.py 契約小擴張）：用 build_meta_learner_input() 自己
    # 回傳的 retained_index 精確對齊 y，取代獨立重算兩層遮罩（審查方
    # 指出後者本身是風險：長度相等不保證同一批列）。
    X_train, train_exclusions, train_idx = build_meta_learner_input(
        oof_df, segment="meta_train", target_column=target, return_retained_index=True)
    y_train = oof_df.loc[train_idx, target].to_numpy()
    X_eval, eval_exclusions, eval_idx = build_meta_learner_input(
        oof_df, segment="meta_eval", target_column=target, return_retained_index=True)
    y_eval = oof_df.loc[eval_idx, target].to_numpy()

    # 機率欄本身已落在 [0,1]，但 regime 欄尺度不同（比照 UG-G3-SB3 對
    # LogisticRegression 的既有紀律：train-only fit 的縮放，避免尺度
    # 差過大的欄主導距離計算）。與 SB3 的 create_scaler("robust") 不同
    # ——這裡用 StandardScaler，因機率欄無極端離群值，明寫 scaler_type
    # 供證據 JSON 稽核，不得含糊。
    scaler = StandardScaler()
    scaler_type = "standard"
    X_train_scaled = scaler.fit_transform(X_train)
    X_eval_scaled = scaler.transform(X_eval)

    majority_pred_eval = compute_majority_baseline_predictions(y_train, len(y_eval))
    majority_baseline_per_class = compute_per_class_metrics(y_eval, majority_pred_eval, labels=labels)

    meta_results: Dict[str, Any] = {}
    for name, ModelCls in (("LogisticRegression", LogisticRegression), ("RidgeClassifier", RidgeClassifier)):
        fit_kwargs = {"random_state": 42}
        if name == "LogisticRegression":
            # 與 UG-G3-SB3 的 PureTechnicalModelFactory 工廠一致的
            # max_iter（非正則化參數，純粹避免未收斂），比照該工廠既有
            # 紀律追蹤 n_iter_ 與 ConvergenceWarning。
            fit_kwargs["max_iter"] = 500

        model = ModelCls(**fit_kwargs)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model.fit(X_train_scaled, y_train)
            conv_warnings = [w for w in caught if issubclass(w.category, ConvergenceWarning)]

        y_pred_eval = model.predict(X_eval_scaled)
        per_class = compute_per_class_metrics(y_eval, y_pred_eval, labels=labels)
        n_iter_attr = getattr(model, "n_iter_", None)
        n_iter_ = int(np.asarray(n_iter_attr).max()) if n_iter_attr is not None else None

        meta_results[name] = {
            "macro_f1_meta_eval": per_class["macro_f1"],
            "per_class_meta_eval": per_class,
            "n_train": len(y_train),
            "n_eval": len(y_eval),
            "n_iter_": n_iter_,
            "n_convergence_warnings": len(conv_warnings),
            "scaler_type": scaler_type,
        }

    return {
        "target": target,
        "oof_path": str(oof_path),
        "oof_sha256": sha256,
        "row_counts": gen_evidence["row_counts"],
        "signal_row_counts": signal_row_counts,
        "best_single_specialist": {
            "ranking_df": ranking_df.to_dict(orient="records"),
            "selected_model": best_model,
            "macro_f1_meta_eval": best_specialist_per_class["macro_f1"],
            "per_class_meta_eval": best_specialist_per_class,
            "selection_metric": SELECTION_METRIC,
            "selection_exclusions": {
                "meta_train": train_selection_exclusions,
                "meta_eval": eval_selection_exclusions,
            },
        },
        "majority_baseline_meta_eval": {
            "per_class": majority_baseline_per_class,
            "n_eval": len(y_eval),
        },
        "meta_a": meta_results,
        "train_exclusions": train_exclusions,
        "eval_exclusions": eval_exclusions,
        "comparison_meta_eval_macro_f1": {
            "Majority Baseline": majority_baseline_per_class["macro_f1"],
            "Meta(A)-LogisticRegression": meta_results["LogisticRegression"]["macro_f1_meta_eval"],
            "Meta(A)-RidgeClassifier": meta_results["RidgeClassifier"]["macro_f1_meta_eval"],
            "Best Single Specialist": best_specialist_per_class["macro_f1"],
        },
    }


def main(target: str, oof_path: Path, oof_generation_evidence_path: Path, output_dir: Path) -> Path:
    if not oof_path.exists():
        raise MetaLearnerReportError(f"OOF parquet 不存在：{oof_path}")
    print(f"target={target} oof_path={oof_path}")

    t0 = time.perf_counter()
    report = run_report(target, oof_path, oof_generation_evidence_path)
    elapsed = time.perf_counter() - t0
    report["total_elapsed_seconds"] = elapsed

    print(f"comparison_meta_eval_macro_f1={report['comparison_meta_eval_macro_f1']}")
    print(f"total_elapsed_seconds={elapsed:.2f}")

    commit_info = get_script_commit_info()
    report["script_commit"] = commit_info["commit"]
    report["script_dirty"] = commit_info["dirty"]
    report["script_dirty_paths"] = commit_info["dirty_paths"]
    report["script_untracked_paths"] = commit_info["untracked_paths"]
    report["run_timestamp"] = datetime.now(timezone.utc).isoformat()
    print(f"script_commit={report['script_commit']} dirty={report['script_dirty']}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"UG_G3_SB4_meta_learner_report_{target}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"output={output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGET_CLASS_DOMAINS))
    parser.add_argument("--oof-path", required=True)
    parser.add_argument("--oof-generation-evidence", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_EVIDENCE_DIR))
    args = parser.parse_args()

    main(
        target=args.target,
        oof_path=Path(args.oof_path),
        oof_generation_evidence_path=Path(args.oof_generation_evidence),
        output_dir=Path(args.output_dir),
    )
