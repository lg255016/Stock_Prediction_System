# -*- coding: utf-8 -*-
"""`UG-G3-SB6` Timeout Gating 段級報告腳本。

依已核准 Gate A 提案 §3.7 與 GREEN 複核意見（`09bcba9`、`23e2039`、
`81def57` 三輪）實作完整管線：讀取 `UG-G3-SB4` OOF parquet → Holdout
隔離守衛 → 重建 Meta(A)-LR／Ridge（設定逐字同 `UG-G3-SB5` 報告腳本）
→ `fit_calibrator()` 於 Calib-fit → 與 `UG-G3-SB5` 已核准證據比對
（`assert_calibrator_matches_sb5()`）→ `_build_dual_curves()` 對兩個
模型**各自的**校準器與**各自的**原始分數組雙軌 `θ` 網格曲線（LR 主、
Ridge 對照，2026-09-16 訂正：v1 誤用單一共用 `raw_eval`，詳見
`_build_dual_curves()` docstring）→ `select_theta_star()` →
`regime_diagnostic()` → 寫證據 JSON（`script_dirty=True` 時拒寫，
`CLAUDE.md` §9A.2）。

比照既有 `scripts/verify/*.py` 慣例：模組層級**無任何讀檔／寫檔／
網路存取副作用**，所有動作限定在 `run_report()`／`main()` 內。
"""
from __future__ import annotations

import json
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

from src.ml.stacking import HOLDOUT_START_DATE, TARGET_CLASS_DOMAINS, build_meta_learner_input
from src.ml.calibration import CALIB_EVAL_FOLDS, CALIB_FIT_FOLDS, apply_calibrator, evaluate_calibration_quality, fit_calibrator
from src.ml.gating import (
    GatingContractError,
    GatingTargetColumnError,
    _validate_target_column,
    assemble_curve_row,
    assert_calibrator_matches_sb5,
    assert_holdout_isolation,
    build_theta_grid,
    calibrated_timeout_probability,
    random_baseline_precision,
    regime_diagnostic,
    select_theta_star,
)
from scripts.verify.ug_g3_sb5_calibration_report import _json_default  # 重用，不另寫（審查方要求）

DEFAULT_EVIDENCE_DIR = Path("doc/upgrade/gates/evidence")
_REPORT_OUTPUT_PATH_RE = __import__("re").compile(r"^doc/upgrade/gates/evidence/UG_G3_SB6_gating_report(_.*)?\.json$")


def _is_report_output_path(path: str) -> bool:
    return bool(_REPORT_OUTPUT_PATH_RE.match(path.replace("\\", "/")))


def compute_file_sha256(path: Path) -> str:
    import hashlib
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_script_commit_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """比照 `ug_g3_sb5_calibration_report.py::get_script_commit_info()`——
    `dirty` 只看**已追蹤檔案**的修改（`git status --porcelain` 的非
    `??` 列，排除本腳本自己的輸出路徑），未追蹤檔案記在
    `untracked_paths` 但不計入 `dirty`（既有先例的既定行為，非本輪
    新增）。"""
    root = repo_root or Path(__file__).resolve().parents[2]
    git_common_opts = ["-c", f"safe.directory={root}", "-c", "core.autocrlf=true"]
    try:
        commit_hash = subprocess.run(
            ["git", *git_common_opts, "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise GatingContractError(f"無法取得 git commit hash（{root}）：{exc}") from exc

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


def verify_oof_sha256(oof_path: Path, oof_generation_evidence_path: Path) -> Tuple[str, Dict[str, Any]]:
    with open(oof_generation_evidence_path, "r", encoding="utf-8") as f:
        gen_evidence = json.load(f)
    actual_sha256 = compute_file_sha256(oof_path)
    expected_sha256 = gen_evidence["oof_parquet_sha256"]
    if actual_sha256 != expected_sha256:
        raise GatingContractError(
            f"OOF parquet sha256 不符：實際={actual_sha256}，期望={expected_sha256}"
        )
    return actual_sha256, gen_evidence


def extract_sb5_reference(sb5_json: Dict[str, Any], model_name: str) -> Dict[str, float]:
    """從真實 `UG_G3_SB5_calibration_report_target_triple_barrier.json`
    的巢狀結構（`calibration_results` → `<model>__sigmoid` →
    `per_class_quality` → `"0"`，類別鍵為字串）抽出六個比對數字：
    模型層級 `brier_after`；`per_class_quality["0"]` 底下的
    `auc_before`／`auc_after`／`platt_slope`／`platt_intercept`；以及
    頂層 `auc_calib_fit_raw["0"]`（**Calib-fit** 段的原始 AUC，與
    `per_class_quality` 的 `auc_before`／`auc_after`——**Calib-eval**
    段——是不同時間段，兩者都比對才能證明「校準器的擬合輸入與評估
    輸出皆相同」，PO 2026-09-15 要求新增）。"""
    try:
        entry = sb5_json["calibration_results"][model_name]
    except KeyError as exc:
        raise GatingContractError(
            f"SB5 證據 JSON 的 calibration_results 內找不到模型 {model_name!r}"
        ) from exc
    class0 = entry["per_class_quality"]["0"]
    return {
        "brier_after": entry["brier_after"],
        "auc_before": class0["auc_before"],
        "auc_after": class0["auc_after"],
        "platt_slope": class0["platt_slope"],
        "platt_intercept": class0["platt_intercept"],
        "auc_calib_fit_raw_class0": entry["auc_calib_fit_raw"]["0"],
    }


def _build_holdout_guard(fold_id, trade_date) -> Dict[str, Any]:
    """記錄 Holdout 隔離守衛的實際比較值，供證據 JSON 稽核（Gate A
    §3.7）。純記錄，不做驗證——驗證由呼叫端另行呼叫
    `assert_holdout_isolation()`。"""
    fold_id = np.asarray(fold_id)
    trade_date = pd.to_datetime(trade_date)
    return {
        "fold_id_max": int(fold_id.max()),
        "trade_date_max": str(trade_date.max().date()),
        "holdout_start_date": str(HOLDOUT_START_DATE.date()),
    }


def assert_report_baseline_consistent(report_dict: Dict[str, float], y_true) -> None:
    """比對報告已記錄的 `random_baseline_precision` 與對 `y_true`
    獨立重算的基期是否一致——任一竄改或計算錯誤即拋
    `GatingContractError`，不得靜默接受。"""
    y_true = np.asarray(y_true)
    actual = float((y_true == 0).sum() / len(y_true))
    reported = report_dict["random_baseline_precision"]
    if abs(actual - reported) > 1e-9:
        raise GatingContractError(
            f"random_baseline_precision 不符：報告值={reported!r}，"
            f"獨立重算值={actual!r}"
        )


def _select_and_diagnose(
    curve_rows: List[Dict[str, Any]],
    *,
    base_rate: float,
    volatility,
    p0,
    y_true,
    min_positive_for_auc: int = 10,
) -> Dict[str, Any]:
    """包裝 `select_theta_star()` ＋ `regime_diagnostic()`——可行區間
    為空時，`regime_diagnostic` 欄記 `None`，**不對不存在的 `θ*`
    硬跑 regime 診斷**（會 `KeyError`）。"""
    selected = select_theta_star(curve_rows, base_rate=base_rate)
    if not selected["feasible"]:
        return {"selected_theta": selected, "regime_diagnostic": None}
    regime = regime_diagnostic(
        volatility, p0, y_true, theta=selected["theta"],
        min_positive_for_auc=min_positive_for_auc,
    )
    return {"selected_theta": selected, "regime_diagnostic": regime}


def _should_write(*, write_flag: bool, max_rows: Optional[int], script_dirty: bool) -> Tuple[bool, str]:
    """三條件交集才允許寫入 evidence JSON：`--write` 給了、
    `--max-rows` 沒給（探測模式的結果不得寫入正式證據）、工作樹乾淨。
    任一條件不成立即拒絕並附理由。"""
    if not write_flag:
        return False, "write_flag 為 False（未帶 --write）"
    if max_rows is not None:
        return False, f"max_rows={max_rows} 已設定（探測模式），探測結果不得寫入 evidence"
    if script_dirty:
        return False, "工作樹不乾淨（script_dirty=True），拒絕寫入"
    return True, "write_flag=True 且 max_rows=None 且 script_dirty=False"


def _build_dual_curves(
    lr_calibrator,
    lr_raw_eval,
    ridge_calibrator,
    ridge_raw_eval,
    theta_grid: List[float],
    y_calib_eval,
    *,
    base_rate: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """對 LR／Ridge**各自的**校準器與**各自的**原始分數組門檻曲線——
    2026-09-16 訂正：v1 簽章只接受單一 `raw_eval` 同時套給兩個校準器，
    不反映真實管線兩者 `decision_function()` 輸出本來就不同的事實
    （GREEN `81def57` 複核發現，`CLAUDE.md` §9A.1 第二個實例——當時的
    測試覆蓋的是被替換掉、未接入主管線的空殼）。每列直接由
    `assemble_curve_row()` 產生，回傳的 `precision`／`lift`／`recall`
    是真正計算出的數值，不是佔位符。"""
    lr_p0 = calibrated_timeout_probability(lr_calibrator, lr_raw_eval)
    ridge_p0 = calibrated_timeout_probability(ridge_calibrator, ridge_raw_eval)
    curve_lr = [assemble_curve_row(theta, lr_p0, y_calib_eval, base_rate) for theta in theta_grid]
    curve_ridge = [assemble_curve_row(theta, ridge_p0, y_calib_eval, base_rate) for theta in theta_grid]
    return curve_lr, curve_ridge


def run_report(
    oof_path: Path,
    oof_generation_evidence_path: Path,
    sb5_reference_path: Path,
    *,
    target_column: str = "target_triple_barrier",
    max_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """完整報告管線。`_validate_target_column()` 是**第一行**——
    任何檔案存取（包含 `oof_path` 是否存在）之前先驗證，證明
    `target_up_down` 依 `RISK-030` 全面排除是結構性的，不是「反正
    也讀不到檔案」的巧合（紅測
    `test_run_report_rejects_up_down_before_file_access` 鎖定此順序）。
    """
    _validate_target_column(target_column)
    _run_report_start_time = time.monotonic()

    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler
    from src.ml.calibration import brier_score_multiclass

    sha256, gen_evidence = verify_oof_sha256(oof_path, oof_generation_evidence_path)
    oof_df = pd.read_parquet(oof_path)

    with open(sb5_reference_path, "r", encoding="utf-8") as f:
        sb5_json = json.load(f)

    labels = TARGET_CLASS_DOMAINS[target_column]

    X_train, _, train_idx = build_meta_learner_input(
        oof_df, segment="meta_train", target_column=target_column, return_retained_index=True)
    y_train = oof_df.loc[train_idx, target_column].to_numpy()
    X_eval, _, eval_idx = build_meta_learner_input(
        oof_df, segment="meta_eval", target_column=target_column, return_retained_index=True)
    y_eval = oof_df.loc[eval_idx, target_column].to_numpy()
    fold_id_eval = oof_df.loc[eval_idx, "fold_id"].to_numpy()
    trade_date_eval = oof_df.loc[eval_idx, "trade_date"].to_numpy()
    volatility_eval = X_eval["volatility_20d"].to_numpy()

    assert_holdout_isolation(fold_id_eval, trade_date_eval)
    holdout_guard = _build_holdout_guard(fold_id_eval, trade_date_eval)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_eval_scaled = scaler.transform(X_eval)

    fitted_models: Dict[str, Any] = {}
    for name, ModelCls in (("LogisticRegression", LogisticRegression), ("RidgeClassifier", RidgeClassifier)):
        fit_kwargs: Dict[str, Any] = {"random_state": 42}
        if name == "LogisticRegression":
            fit_kwargs["max_iter"] = 500
        model = ModelCls(**fit_kwargs)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            model.fit(X_train_scaled, y_train)
        fitted_models[name] = model

    if max_rows is not None:
        rng = np.random.RandomState(0)
        keep = np.sort(rng.choice(len(y_eval), size=min(max_rows, len(y_eval)), replace=False))
        X_eval_scaled = X_eval_scaled[keep]
        y_eval = y_eval[keep]
        fold_id_eval = fold_id_eval[keep]
        volatility_eval = volatility_eval[keep]

    calib_fit_mask = np.isin(fold_id_eval, CALIB_FIT_FOLDS)
    calib_eval_mask = np.isin(fold_id_eval, CALIB_EVAL_FOLDS)
    y_calib_eval = y_eval[calib_eval_mask]
    volatility_calib_eval = volatility_eval[calib_eval_mask]
    base_rate = random_baseline_precision(y_calib_eval)

    fitted_calibrators: Dict[str, Any] = {}
    fitted_raw_eval: Dict[str, Any] = {}
    quality_by_model: Dict[str, Any] = {}
    for name, model in fitted_models.items():
        raw_scores_all = model.decision_function(X_eval_scaled)
        raw_fit = raw_scores_all[calib_fit_mask]
        raw_eval_scores = raw_scores_all[calib_eval_mask]
        y_fit = y_eval[calib_fit_mask]
        fold_fit = fold_id_eval[calib_fit_mask]
        fold_calib_eval = fold_id_eval[calib_eval_mask]

        calibrator = fit_calibrator(
            raw_fit, y_fit, fold_id=fold_fit, method="sigmoid", target_column=target_column)
        quality = evaluate_calibration_quality(
            calibrator, raw_eval_scores, y_calib_eval, fold_id=fold_calib_eval, method="sigmoid")
        class0_quality = quality[0]
        calibrated_probs = apply_calibrator(calibrator, raw_eval_scores)
        brier_after = brier_score_multiclass(y_calib_eval, calibrated_probs, class_order=labels)
        auc_calib_fit_raw = {
            str(cls): float(roc_auc_score((y_fit == cls).astype(int), raw_fit[:, i]))
            for i, cls in enumerate(labels)
        }

        rebuilt_quality = {
            "brier_after": brier_after,
            "auc_before": class0_quality["auc_before"],
            "auc_after": class0_quality["auc_after"],
            "platt_slope": class0_quality["platt_slope"],
            "platt_intercept": class0_quality["platt_intercept"],
            "auc_calib_fit_raw_class0": auc_calib_fit_raw["0"],
        }
        sb5_model_key = f"{name}__sigmoid"
        sb5_reference = extract_sb5_reference(sb5_json, sb5_model_key)
        assert_calibrator_matches_sb5(rebuilt_quality, sb5_reference)

        fitted_calibrators[name] = calibrator
        fitted_raw_eval[name] = raw_eval_scores
        quality_by_model[name] = rebuilt_quality

    lr_p0_for_grid = calibrated_timeout_probability(
        fitted_calibrators["LogisticRegression"], fitted_raw_eval["LogisticRegression"])
    grid = build_theta_grid(lr_p0_for_grid)
    all_theta = sorted(set(grid["fine"]) | set(grid["quantile"]))

    curve_lr, curve_ridge = _build_dual_curves(
        fitted_calibrators["LogisticRegression"], fitted_raw_eval["LogisticRegression"],
        fitted_calibrators["RidgeClassifier"], fitted_raw_eval["RidgeClassifier"],
        all_theta, y_calib_eval, base_rate=base_rate,
    )

    selection = _select_and_diagnose(
        curve_lr, base_rate=base_rate, volatility=volatility_calib_eval,
        p0=lr_p0_for_grid, y_true=y_calib_eval,
    )

    calib_fit_class_distribution = {
        str(cls): int((y_fit == cls).sum()) for cls in labels
    }
    calib_eval_class_distribution = {
        str(cls): int((y_calib_eval == cls).sum()) for cls in labels
    }

    report_dict: Dict[str, Any] = {
        "target": target_column,
        "oof_sha256": sha256,
        "holdout_guard": holdout_guard,
        "calib_fit_folds": list(CALIB_FIT_FOLDS),
        "calib_eval_folds": list(CALIB_EVAL_FOLDS),
        "calib_fit_row_count": int(calib_fit_mask.sum()),
        "calib_eval_row_count": int(calib_eval_mask.sum()),
        "calib_fit_class_distribution": calib_fit_class_distribution,
        "calib_eval_class_distribution": calib_eval_class_distribution,
        "random_baseline_precision": base_rate,
        "theta_grid": grid,
        "lr_curve": curve_lr,
        "lr_quality": quality_by_model["LogisticRegression"],
        "ridge_curve": curve_ridge,
        "ridge_quality": quality_by_model["RidgeClassifier"],
        "selected_theta": selection["selected_theta"],
        "regime_diagnostic": selection["regime_diagnostic"],
        "max_rows_used": max_rows,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    assert_report_baseline_consistent(report_dict, y_calib_eval)
    report_dict["total_elapsed_seconds"] = time.monotonic() - _run_report_start_time
    return report_dict


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--oof-path", type=Path, required=False)
    parser.add_argument("--oof-generation-evidence-path", type=Path, required=False)
    parser.add_argument("--sb5-reference-path", type=Path, required=False)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    commit_info = get_script_commit_info()

    if args.write:
        should_write, reason = _should_write(
            write_flag=args.write, max_rows=args.max_rows, script_dirty=commit_info["dirty"])
        if not should_write:
            print(f"REFUSED: {reason}", file=sys.stderr)
            return 1

    if args.oof_path is None:
        print("尚未提供 --oof-path 等參數，僅供 main() 早期守衛的獨立驗證。", file=sys.stderr)
        return 1

    report_dict = run_report(
        args.oof_path, args.oof_generation_evidence_path, args.sb5_reference_path,
        max_rows=args.max_rows,
    )
    report_dict["script_commit"] = commit_info["commit"]
    report_dict["script_dirty"] = commit_info["dirty"]
    report_dict["script_dirty_paths"] = commit_info["dirty_paths"]
    report_dict["script_untracked_paths"] = commit_info["untracked_paths"]

    if args.write:
        DEFAULT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEFAULT_EVIDENCE_DIR / "UG_G3_SB6_gating_report.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, default=_json_default, ensure_ascii=False, indent=2)
        print(f"寫入 {out_path}")
    else:
        print(json.dumps(report_dict, default=_json_default, ensure_ascii=False, indent=2)[:2000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
