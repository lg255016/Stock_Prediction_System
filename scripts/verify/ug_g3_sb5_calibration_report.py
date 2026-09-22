# -*- coding: utf-8 -*-
"""`UG-G3-SB5` 段級報告產生器（PO 2026-09-15 核准進入腳本階段）。

**僅限 dev container 內執行**（依賴 sklearn，見 `CLAUDE.md` §13.0）。

**唯讀，結構上不可能連 DB**：只讀取 `UG-G3-SB4` 已產生的 OOF parquet 與
證據 JSON，只寫一份報告 JSON；不匯入任何資料庫驅動程式。

流程：
1. 讀入 OOF 矩陣（守衛 1-4，比照 `ug_g3_sb4_meta_learner_report.py`）。
2. 重建 `UG-G3-SB4` 的 `LogisticRegression`／`RidgeClassifier` Meta-Learner
   （設定逐字相同：`build_meta_learner_input(..., return_retained_index=True)`、
   `StandardScaler` train-only、`LogisticRegression(max_iter=500,
   random_state=42)`、`RidgeClassifier(random_state=42)`），斷言其
   Meta-Eval 硬預測 macro F1 與 `UG_G3_SB4_meta_learner_report_<target>.json`
   記載值逐位相同（容差 1e-9，守衛 5）——這是「校準的是同一個模型」的
   證明，不符即 abort。
3. 取 `decision_function()` 分數，依 `fold_id` 切 `CALIB_FIT_FOLDS`
   （折 27-29）／`CALIB_EVAL_FOLDS`（折 30-32），`src.ml.calibration` 的
   `fit_calibrator()`／`evaluate_calibration_quality()` 各自帶
   `fold_id` 守衛。up_down 產 `isotonic`+`sigmoid` 兩版，TB 只產
   `sigmoid`（`CALIBRATION_METHOD_BY_TARGET`）。
4. 「校準前」基準 = 原始分數的**未擬合**（naive）sigmoid 轉換（二分類
   直接 `1/(1+e^-s)`；TB 逐類別 `1/(1+e^-s)` 後逐列正規化，與
   `apply_calibrator()` 的正規化步驟一致，確保前後可比）——這與
   `LogisticRegression` 原生 `predict_proba`（另有一項獨立揭露）是
   兩個不同的「未校準」參照點：前者對 LR／Ridge 都適用（Ridge 沒有
   `predict_proba`），後者只有 LR 才有。

腳本層守衛（任一不符即 abort，不降級、不跳過）：
1. OOF parquet sha256 必須等於 `UG_G3_SB4_oof_generation_<target>.json` 記載值。
2. `split_segment` 值域只能是 `{"meta_train", "meta_eval", "purged"}`。
3. 三段列數與 OOF 產生階段證據 JSON 記載值一致。
4. 讀取端呼叫 `reject_rows_at_or_after()` 二次確認零 Holdout 列。
5. 重建的 Meta-Learner，其 Meta-Eval 硬預測 macro F1 與
   `UG_G3_SB4_meta_learner_report_<target>.json` 記載值逐位相同
   （容差 1e-9）。
6. Meta-Eval 段全部 `fold_id` 必須落在 `CALIB_FIT_FOLDS ∪ CALIB_EVAL_FOLDS`
   （即折 27-32）內。
7. `model.classes_` 順序必須等於 `TARGET_CLASS_DOMAINS[target]`——
   `decision_function()` 的欄序假設不得只憑經驗信任。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    HOLDOUT_START_DATE,
    TARGET_CLASS_DOMAINS,
    build_meta_learner_input,
    reject_rows_at_or_after,
)
from src.ml.calibration import (
    CALIB_EVAL_FOLDS,
    CALIB_FIT_FOLDS,
    CALIBRATION_METHOD_BY_TARGET,
    PLATT_C,
    RELIABILITY_N_BINS,
    apply_calibrator,
    evaluate_calibration_quality,
    fit_calibrator,
    reliability_table,
)


class CalibrationReportError(RuntimeError):
    """OOF 矩陣／守衛失敗——結構性 abort，不降級、不跳過。"""


DEFAULT_OOF_DIR = Path("/workspaces/Database_Backups/Stock_Prediction_System2/ml_panels")
DEFAULT_EVIDENCE_DIR = Path("doc/upgrade/gates/evidence")

_REPORT_OUTPUT_PATH_RE = re.compile(
    r"^doc/upgrade/gates/evidence/UG_G3_SB5_calibration_report_.*\.json$")


def _is_report_output_path(path: str) -> bool:
    return bool(_REPORT_OUTPUT_PATH_RE.match(path.replace("\\", "/")))


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_script_commit_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """比照 `ug_g3_sb4_meta_learner_report.py::get_script_commit_info()`。"""
    root = repo_root or Path(__file__).resolve().parents[2]
    git_common_opts = ["-c", f"safe.directory={root}", "-c", "core.autocrlf=true"]
    try:
        commit_hash = subprocess.run(
            ["git", *git_common_opts, "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise CalibrationReportError(
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


# ==============================================================================
# 守衛 1-4（OOF 讀取端，鏡射 ug_g3_sb4_meta_learner_report.py 既有邏輯）
# ==============================================================================

def verify_oof_sha256(oof_path: Path, oof_generation_evidence_path: Path) -> Tuple[str, Dict[str, Any]]:
    """守衛 1。"""
    with open(oof_generation_evidence_path, "r", encoding="utf-8") as f:
        gen_evidence = json.load(f)
    expected = gen_evidence["oof_parquet_sha256"]
    actual = compute_file_sha256(oof_path)
    if actual != expected:
        raise CalibrationReportError(
            f"OOF parquet sha256 不符 OOF 產生階段記載值——"
            f"expected={expected} actual={actual}（{oof_path}）。"
            "拒絕對未經複核的 OOF 矩陣產出報告。"
        )
    return actual, gen_evidence


def assert_segment_value_domain(oof_df: pd.DataFrame) -> None:
    """守衛 2。"""
    bad = set(oof_df["split_segment"].unique()) - {"meta_train", "meta_eval", "purged"}
    if bad:
        raise CalibrationReportError(
            f"split_segment 出現非預期值：{sorted(bad)}——拒絕產出報告。"
        )


def assert_row_counts_match_generation(oof_df: pd.DataFrame, gen_evidence: Dict[str, Any]) -> None:
    """守衛 3。"""
    actual = {
        "total": len(oof_df),
        "meta_train": int((oof_df["split_segment"] == "meta_train").sum()),
        "meta_eval": int((oof_df["split_segment"] == "meta_eval").sum()),
        "purged": int((oof_df["split_segment"] == "purged").sum()),
    }
    expected = gen_evidence["row_counts"]
    if actual != expected:
        raise CalibrationReportError(
            f"三段列數與 OOF 產生階段記載值不符——expected={expected} "
            f"actual={actual}。拒絕產出報告。"
        )


# ==============================================================================
# 守衛 5：重建的 Meta-Learner 必須與 UG-G3-SB4 已核准報告逐位相同
# ==============================================================================

def assert_matches_sb4_report(
    actual_macro_f1: Dict[str, float],
    sb4_report_evidence: Dict[str, Any],
    tol: float = 1e-9,
) -> None:
    """守衛 5——不符即 abort，這是「校準的是同一個模型」的證明，不是
    信任聲明。"""
    for model_name, actual_value in actual_macro_f1.items():
        expected_value = sb4_report_evidence["meta_a"][model_name]["macro_f1_meta_eval"]
        if abs(actual_value - expected_value) > tol:
            raise CalibrationReportError(
                f"重建的 {model_name} Meta-Eval macro F1（{actual_value:.12f}）"
                f"與 UG-G3-SB4 已核准報告記載值（{expected_value:.12f}）不符"
                f"（差值 {abs(actual_value - expected_value):.2e} > 容差 {tol}）——"
                "拒絕產出報告：這代表本腳本重建的不是同一個 Meta-Learner。"
            )


# ==============================================================================
# 守衛 6：Meta-Eval 段全部 fold_id 必須落在 CALIB_FIT_FOLDS ∪ CALIB_EVAL_FOLDS
# ==============================================================================

def assert_meta_eval_folds_expected(fold_id: np.ndarray) -> None:
    """守衛 6。"""
    allowed = set(CALIB_FIT_FOLDS) | set(CALIB_EVAL_FOLDS)
    bad = sorted(set(np.asarray(fold_id).tolist()) - allowed)
    if bad:
        raise CalibrationReportError(
            f"Meta-Eval 段出現非預期折號：{bad}（允許範圍 {sorted(allowed)}）——"
            "拒絕產出報告。"
        )


# ==============================================================================
# 守衛 7：decision_function() 欄序須等於 TARGET_CLASS_DOMAINS
# ==============================================================================

def assert_classes_match_domain(model_classes: np.ndarray, target_column: str) -> None:
    """守衛 7。"""
    expected = TARGET_CLASS_DOMAINS[target_column]
    actual = [int(c) for c in model_classes]
    if actual != expected:
        raise CalibrationReportError(
            f"{target_column} 的模型 classes_ 順序 {actual} 與 "
            f"TARGET_CLASS_DOMAINS 記載順序 {expected} 不符——"
            "decision_function() 的欄序假設不成立，拒絕產出報告。"
        )


# ==============================================================================
# 純函式：naive（未擬合）sigmoid 基準、固定門檻硬預測
# ==============================================================================

def naive_calibration_probabilities(raw_scores: np.ndarray, target_column: str) -> np.ndarray:
    """「校準前」基準：原始分數的**未擬合**sigmoid 轉換。二分類回傳一維
    （class 1 機率）；TB 逐類別轉換後逐列正規化（與 `apply_calibrator()`
    的正規化步驟一致，確保前後可比），回傳 `(n, 3)`。"""
    if target_column == "target_triple_barrier":
        raw_scores = np.asarray(raw_scores, dtype=float)
        sig = 1.0 / (1.0 + np.exp(-raw_scores))
        row_sums = sig.sum(axis=1)
        row_sums = np.where(row_sums < 1e-9, 1e-9, row_sums)
        return sig / row_sums[:, None]
    raw_scores = np.asarray(raw_scores, dtype=float)
    return 1.0 / (1.0 + np.exp(-raw_scores))


def fixed_threshold_predictions(probs: np.ndarray, target_column: str) -> np.ndarray:
    """固定門檻硬預測：二分類 0.5 門檻；TB 取 argmax（依
    `TARGET_CLASS_DOMAINS` 欄序）。"""
    domain = TARGET_CLASS_DOMAINS[target_column]
    if target_column == "target_triple_barrier":
        idx = np.argmax(np.asarray(probs), axis=1)
        return np.array([domain[i] for i in idx])
    return np.where(np.asarray(probs) >= 0.5, domain[1], domain[0])


def to_two_column(probs_1d: np.ndarray) -> np.ndarray:
    """二分類的一維 class-1 機率 → `(n, 2)`（`[1-p, p]`），供
    `brier_score_multiclass()`／`log_loss()` 使用。"""
    probs_1d = np.asarray(probs_1d, dtype=float)
    return np.column_stack([1.0 - probs_1d, probs_1d])


# ==============================================================================
# 主流程
# ==============================================================================

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


def run_report(
    target: str,
    oof_path: Path,
    oof_generation_evidence_path: Path,
    sb4_report_evidence_path: Path,
    max_rows: Optional[int] = None,
) -> Dict[str, Any]:
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.metrics import log_loss, roc_auc_score
    from sklearn.preprocessing import StandardScaler

    from src.ml.calibration import brier_score_multiclass
    from src.ml.specialist_training import compute_per_class_metrics

    # ---- 守衛 1-4 ----
    sha256, gen_evidence = verify_oof_sha256(oof_path, oof_generation_evidence_path)
    oof_df = pd.read_parquet(oof_path)
    assert_segment_value_domain(oof_df)
    assert_row_counts_match_generation(oof_df, gen_evidence)
    reject_rows_at_or_after(oof_df, "trade_date", HOLDOUT_START_DATE)

    with open(sb4_report_evidence_path, "r", encoding="utf-8") as f:
        sb4_report_evidence = json.load(f)

    labels = TARGET_CLASS_DOMAINS[target]

    # ---- 重建 UG-G3-SB4 的 Meta-Learner（設定逐字相同） ----
    X_train, _, train_idx = build_meta_learner_input(
        oof_df, segment="meta_train", target_column=target, return_retained_index=True)
    y_train = oof_df.loc[train_idx, target].to_numpy()
    X_eval, _, eval_idx = build_meta_learner_input(
        oof_df, segment="meta_eval", target_column=target, return_retained_index=True)
    y_eval = oof_df.loc[eval_idx, target].to_numpy()
    fold_id_eval = oof_df.loc[eval_idx, "fold_id"].to_numpy()

    # 守衛 6：Meta-Eval 折號範圍。
    assert_meta_eval_folds_expected(fold_id_eval)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_eval_scaled = scaler.transform(X_eval)

    fitted_models: Dict[str, Any] = {}
    actual_macro_f1: Dict[str, float] = {}
    for name, ModelCls in (("LogisticRegression", LogisticRegression), ("RidgeClassifier", RidgeClassifier)):
        fit_kwargs = {"random_state": 42}
        if name == "LogisticRegression":
            fit_kwargs["max_iter"] = 500
        model = ModelCls(**fit_kwargs)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            model.fit(X_train_scaled, y_train)
        assert_classes_match_domain(model.classes_, target)  # 守衛 7
        y_pred_eval = model.predict(X_eval_scaled)
        per_class = compute_per_class_metrics(y_eval, y_pred_eval, labels=labels)
        actual_macro_f1[name] = per_class["macro_f1"]
        fitted_models[name] = model

    # 守衛 5：與 UG-G3-SB4 已核准報告逐位核對。
    assert_matches_sb4_report(actual_macro_f1, sb4_report_evidence)

    # ---- 取樣（僅供小探測用，全量時 max_rows=None） ----
    if max_rows is not None:
        rng = np.random.RandomState(0)
        keep = rng.choice(len(y_eval), size=min(max_rows, len(y_eval)), replace=False)
        keep = np.sort(keep)
        X_eval_scaled_used = X_eval_scaled[keep]
        y_eval_used = y_eval[keep]
        fold_id_eval_used = fold_id_eval[keep]
    else:
        X_eval_scaled_used = X_eval_scaled
        y_eval_used = y_eval
        fold_id_eval_used = fold_id_eval

    calib_fit_mask = np.isin(fold_id_eval_used, CALIB_FIT_FOLDS)
    calib_eval_mask = np.isin(fold_id_eval_used, CALIB_EVAL_FOLDS)

    calib_fit_class_dist = {
        str(cls): int((y_eval_used[calib_fit_mask] == cls).sum()) for cls in labels
    }
    calib_eval_class_dist = {
        str(cls): int((y_eval_used[calib_eval_mask] == cls).sum()) for cls in labels
    }

    calibration_results: Dict[str, Any] = {}
    lr_native_brier: Optional[float] = None

    for model_name, model in fitted_models.items():
        raw_scores_all = model.decision_function(X_eval_scaled_used)
        raw_fit = raw_scores_all[calib_fit_mask]
        raw_eval = raw_scores_all[calib_eval_mask]
        y_fit = y_eval_used[calib_fit_mask]
        y_eval_sub = y_eval_used[calib_eval_mask]
        fold_fit = fold_id_eval_used[calib_fit_mask]
        fold_eval_sub = fold_id_eval_used[calib_eval_mask]

        if model_name == "LogisticRegression":
            native_proba = model.predict_proba(X_eval_scaled_used[calib_eval_mask])
            lr_native_brier = brier_score_multiclass(y_eval_sub, native_proba, class_order=labels)

        naive_probs_eval = naive_calibration_probabilities(raw_eval, target)

        # 「校準前」診斷基準：Calib-fit 原始分數自己的 AUC（OvR 逐類，
        # 供 calibration_not_meaningful 判定的脈絡揭露；審查方 2026-09-15
        # 對此表逐一重算，見 §2.3 對照）。
        if target == "target_triple_barrier":
            auc_calib_fit_raw = {
                str(cls): float(roc_auc_score((y_fit == cls).astype(int), raw_fit[:, i]))
                for i, cls in enumerate(labels)
            }
        else:
            auc_calib_fit_raw = float(roc_auc_score(y_fit, raw_fit))

        for method in CALIBRATION_METHOD_BY_TARGET[target]:
            calibrator = fit_calibrator(
                raw_fit, y_fit, fold_id=fold_fit, method=method, target_column=target)
            quality = evaluate_calibration_quality(
                calibrator, raw_eval, y_eval_sub, fold_id=fold_eval_sub, method=method)
            calibrated_probs = apply_calibrator(calibrator, raw_eval)

            if target == "target_triple_barrier":
                naive_2col_or_3col = naive_probs_eval
                calibrated_2col_or_3col = calibrated_probs
                # quality 為 {類別: 結果字典}（2026-09-15 補件：多類別逐類別
                # OvR 各自獨立評估，見 evaluate_calibration_quality() docstring）。
                per_class_quality = {str(cls): quality[cls] for cls in labels}
                auc_calib_fit_values = list(auc_calib_fit_raw.values())
            else:
                naive_2col_or_3col = to_two_column(naive_probs_eval)
                calibrated_2col_or_3col = to_two_column(calibrated_probs)
                per_class_quality = {str(labels[1]): quality}
                auc_calib_fit_values = [auc_calib_fit_raw]

            # 訂正（PO 2026-09-15 複核）：判準依據是「Calib-fit 原始分數
            # AUC < 0.5（任一 OvR 類別）」，與校準方法無關——isotonic 條目
            # 同樣可能無意義（up_down 的兩個 isotonic 條目 auc_calib_fit_raw
            # ≈0.4959，同樣該標）。原設計誤把旗標限定在 sigmoid（只依斜率
            # 正負號判斷），已訂正為每個條目（含 isotonic）皆有此鍵。
            calibration_not_meaningful = any(v < 0.5 for v in auc_calib_fit_values)

            brier_before = brier_score_multiclass(y_eval_sub, naive_2col_or_3col, class_order=labels)
            brier_after = brier_score_multiclass(y_eval_sub, calibrated_2col_or_3col, class_order=labels)
            logloss_before = float(log_loss(y_eval_sub, naive_2col_or_3col, labels=labels))
            logloss_after = float(log_loss(y_eval_sub, calibrated_2col_or_3col, labels=labels))

            pred_before = fixed_threshold_predictions(naive_probs_eval, target)
            pred_after = fixed_threshold_predictions(calibrated_probs, target)
            per_class_before = compute_per_class_metrics(y_eval_sub, pred_before, labels=labels)
            per_class_after = compute_per_class_metrics(y_eval_sub, pred_after, labels=labels)

            if target == "target_triple_barrier":
                reliability_before = [
                    reliability_table(naive_probs_eval[:, i], (y_eval_sub == cls).astype(int))
                    for i, cls in enumerate(labels)
                ]
                reliability_after = [
                    reliability_table(calibrated_probs[:, i], (y_eval_sub == cls).astype(int))
                    for i, cls in enumerate(labels)
                ]
            else:
                reliability_before = reliability_table(naive_probs_eval, y_eval_sub)
                reliability_after = reliability_table(calibrated_probs, y_eval_sub)

            entry = {
                "model_name": model_name,
                "method": method,
                "auc_calib_fit_raw": auc_calib_fit_raw,
                "per_class_quality": per_class_quality,
                "n_unique_calibrated_values": (
                    {str(cls): quality[cls]["n_unique_calibrated_values"] for cls in labels}
                    if target == "target_triple_barrier"
                    else quality["n_unique_calibrated_values"]
                ),
                "brier_before": brier_before,
                "brier_after": brier_after,
                "log_loss_before": logloss_before,
                "log_loss_after": logloss_after,
                "fixed_threshold_rule": (
                    "argmax（三類別）" if target == "target_triple_barrier" else "0.5 門檻（二分類）"
                ),
                "fixed_threshold_macro_f1_before": per_class_before["macro_f1"],
                "fixed_threshold_macro_f1_after": per_class_after["macro_f1"],
                "fixed_threshold_per_class_before": per_class_before,
                "fixed_threshold_per_class_after": per_class_after,
                "reliability_before": reliability_before,
                "reliability_after": reliability_after,
            }
            # 2026-09-15 訂正（PO 複核）：每個條目（含 isotonic）皆有此鍵，
            # 判準只看 Calib-fit 原始分數 AUC，與方法無關。sigmoid 另附
            # 斜率脈絡——負斜率是合法結果（Calib-fit 折數少、底層訊號趨近
            # 零時，斜率正負號本身是雜訊），不是排序被破壞（見
            # src/ml/calibration.py::assert_auc_preserved() 訂正記錄）。
            # 標記供 Gate B 判讀，不代表本次校準本身失敗或有 bug。
            entry["calibration_not_meaningful"] = calibration_not_meaningful
            if calibration_not_meaningful:
                reason = (
                    "Calib-fit 原始分數 AUC < 0.5（至少一個 OvR 類別，見本條目 "
                    f"auc_calib_fit_raw={auc_calib_fit_raw!r}）——底層訊號趨近零，"
                    "校準器沒有真實排序訊號可學"
                )
                if method == "sigmoid":
                    slopes = (
                        {str(cls): per_class_quality[str(cls)]["platt_slope"] for cls in labels}
                        if target == "target_triple_barrier"
                        else {str(labels[1]): per_class_quality[str(labels[1])]["platt_slope"]}
                    )
                    reason += f"；Platt 擬合斜率（正負號本身即為雜訊）：{slopes!r}"
                entry["calibration_not_meaningful_reason"] = reason

            calibration_results[f"{model_name}__{method}"] = entry

    # ---- 逐 Specialist 的原始 AUC 診斷（OvR 逐類，Meta-Train／Calib-fit／
    # Calib-eval 三段；PO 2026-09-15 要求，供上述 calibration_not_meaningful
    # 判定與 RISK-030 的數字直接從證據重現，不需另外查 Gate B 對話紀錄） ----
    meta_train_df = oof_df[oof_df["split_segment"] == "meta_train"]
    meta_eval_df = oof_df.loc[eval_idx].copy()
    meta_eval_df["fold_id"] = fold_id_eval
    calib_fit_df = meta_eval_df[meta_eval_df["fold_id"].isin(CALIB_FIT_FOLDS)]
    calib_eval_df = meta_eval_df[meta_eval_df["fold_id"].isin(CALIB_EVAL_FOLDS)]

    def _prob_col(model: str, cls: int) -> str:
        token = {-1: "m1", 0: "0", 1: "p1"}[cls] if target == "target_triple_barrier" else str(int(cls))
        return f"{model}_A_p{token}"

    specialist_raw_auc: Dict[str, Any] = {}
    for model in ("lr", "rf", "lgbm", "xgb"):
        specialist_raw_auc[model] = {}
        for cls in labels:
            col = _prob_col(model, cls)
            y_bin_train = (meta_train_df[target] == cls).astype(int)
            y_bin_fit = (calib_fit_df[target] == cls).astype(int)
            y_bin_eval = (calib_eval_df[target] == cls).astype(int)
            specialist_raw_auc[model][str(cls)] = {
                "meta_train_auc": float(roc_auc_score(y_bin_train, meta_train_df[col])),
                "calib_fit_auc": float(roc_auc_score(y_bin_fit, calib_fit_df[col])),
                "calib_eval_auc": float(roc_auc_score(y_bin_eval, calib_eval_df[col])),
            }

    specialist_raw_auc_note = (
        "target_up_down 二分類：兩個類別（0／1）的 AUC 數值理論上必然相同"
        "（class-1 機率的排序能力與 class-0 機率的排序能力是同一個排序問題"
        "的兩面，AUC(class=0, score=p0) == AUC(class=1, score=p1) 恆成立），"
        "非重複計算錯誤，保留兩欄僅為與 target_triple_barrier 的欄位結構一致。"
        if target == "target_up_down" else None
    )

    return {
        "target": target,
        "oof_path": str(oof_path),
        "oof_sha256": sha256,
        "sb4_report_evidence_path": str(sb4_report_evidence_path),
        "sb4_model_match": {
            "actual_macro_f1_meta_eval": actual_macro_f1,
            "matched_within_tolerance": 1e-9,
        },
        "calib_fit_folds": list(CALIB_FIT_FOLDS),
        "calib_eval_folds": list(CALIB_EVAL_FOLDS),
        "calib_fit_row_count": int(calib_fit_mask.sum()),
        "calib_eval_row_count": int(calib_eval_mask.sum()),
        "calib_fit_class_distribution": calib_fit_class_dist,
        "calib_eval_class_distribution": calib_eval_class_dist,
        "lr_native_proba_brier_calib_eval": lr_native_brier,
        "calibration_results": calibration_results,
        "specialist_raw_auc": specialist_raw_auc,
        "specialist_raw_auc_note": specialist_raw_auc_note,
        "platt_c": PLATT_C,
        "reliability_n_bins": RELIABILITY_N_BINS,
        "max_rows_used": max_rows,
    }


def main(
    target: str,
    oof_path: Path,
    oof_generation_evidence_path: Path,
    sb4_report_evidence_path: Path,
    output_dir: Path,
    max_rows: Optional[int] = None,
) -> Path:
    if not oof_path.exists():
        raise CalibrationReportError(f"OOF parquet 不存在：{oof_path}")
    print(f"target={target} oof_path={oof_path} max_rows={max_rows}")

    t0 = time.perf_counter()
    report = run_report(target, oof_path, oof_generation_evidence_path,
                         sb4_report_evidence_path, max_rows=max_rows)
    elapsed = time.perf_counter() - t0
    report["total_elapsed_seconds"] = elapsed

    print(f"calib_fit_row_count={report['calib_fit_row_count']} "
          f"calib_eval_row_count={report['calib_eval_row_count']}")
    print(f"total_elapsed_seconds={elapsed:.2f}")

    commit_info = get_script_commit_info()
    report["script_commit"] = commit_info["commit"]
    report["script_dirty"] = commit_info["dirty"]
    report["script_dirty_paths"] = commit_info["dirty_paths"]
    report["script_untracked_paths"] = commit_info["untracked_paths"]
    report["run_timestamp"] = datetime.now(timezone.utc).isoformat()
    print(f"script_commit={report['script_commit']} dirty={report['script_dirty']}")

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_probe{max_rows}rows" if max_rows is not None else ""
    output_path = output_dir / f"UG_G3_SB5_calibration_report_{target}{suffix}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"output={output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGET_CLASS_DOMAINS))
    parser.add_argument("--oof-path", required=True)
    parser.add_argument("--oof-generation-evidence", required=True)
    parser.add_argument("--sb4-report-evidence", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--max-rows", type=int, default=None,
                         help="限制 Meta-Eval 抽樣列數，供小探測使用；省略即全量")
    args = parser.parse_args()

    main(
        target=args.target,
        oof_path=Path(args.oof_path),
        oof_generation_evidence_path=Path(args.oof_generation_evidence),
        sb4_report_evidence_path=Path(args.sb4_report_evidence),
        output_dir=Path(args.output_dir),
        max_rows=args.max_rows,
    )
