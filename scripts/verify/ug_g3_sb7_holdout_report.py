# -*- coding: utf-8 -*-
"""`UG-G3-SB7` Holdout 最終驗證報告腳本。

依 `doc/upgrade/gates/UG_G3_SB7_GATE_A_PROPOSAL.md` v2 實作：對 Holdout
（折 33-42，`HOLDOUT_START_DATE`）重新產生 Specialist OOF（`iter_holdout_folds()`，
walk-forward 內合法的逐折重新 `fit`／`predict`），套用**凍結**的 Meta(A)-LR／Ridge
訓練設定與**凍結**的校準器（`UG-G3-SB5`）、**凍結**的 `θ*` 與 regime 切點
（`UG-G3-SB6`），計算 Timeout gating 三項判準是否在 Holdout 上仍成立，並與
隨機基線、波動率基線（三分位＋覆蓋率對齊版）並列比較。

**乾跑安全網**：`holdout_start_date` 不等於 `HOLDOUT_START_DATE` 常數時視為
乾跑（偽 Holdout，例如代入 Calib-eval 邊界跑折 30-32），本腳本**無論如何**
會先把面板截斷到 `trade_date < HOLDOUT_START_DATE`——即使乾跑的 boundary
參數本身涵蓋真正的折 33-42，物理上也讀不到那些列，不依賴 boundary 參數
本身「湊巧」算對。`--write` 只在 `holdout_start_date == HOLDOUT_START_DATE`
時允許（`_should_write_holdout()`），且只能消費一次（`holdout_consumed_at`
機制，無任何旗標可繞過）。

比照既有 `scripts/verify/*.py` 慣例：模組層級無任何讀檔／寫檔／網路存取
副作用，所有動作限定在 `run_report()`／`main()` 內。
"""
from __future__ import annotations

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
    MODEL_NAME_SHORT_CODES,
    TARGET_CLASS_DOMAINS,
    assemble_oof_matrix,
    build_meta_learner_input,
    iter_holdout_folds,
    iter_oof_folds,
)
from src.ml.calibration import (
    CALIB_EVAL_FOLDS,
    CALIB_FIT_FOLDS,
    apply_calibrator,
    evaluate_calibration_quality,
    fit_calibrator,
)
from src.ml.gating import (
    MIN_COVERAGE,
    MIN_LIFT,
    MIN_POSITIVE_FOR_AUC,
    MIN_RECALL,
    GatingContractError,
    assert_calibrator_matches_sb5,
    assert_holdout_only,
    compute_gating_metrics,
)
from src.ml.specialist_training import (
    compute_per_class_metrics,
    fit_predict_specialist_fold,
    prepare_fold_data,
)
from src.ml.baseline_models import ARM_A_FEATURE_COLS, META_REGIME_FEATURE_COLS
from scripts.verify.ug_g3_sb4_oof_generation import (
    EMBARGO_DAYS,
    MODEL_NAMES_FULL,
    TARGET_CONFIG,
    TEST_WINDOW_SIZE,
    TRAIN_WINDOW_SIZE,
    build_splitter,
    verify_panel_sha256,
)
from scripts.verify.ug_g3_sb5_calibration_report import (
    CalibrationReportError,
    _json_default,
    assert_matches_sb4_report,
)

DEFAULT_EVIDENCE_DIR = Path("doc/upgrade/gates/evidence")
_REPORT_OUTPUT_PATH_RE = re.compile(
    r"^doc/upgrade/gates/evidence/UG_G3_SB7_holdout_report(_.*)?\.json$")

TARGET_COLUMN = "target_triple_barrier"

# UG-G3-SB6 Gate A v2 §2.3 第 10 項：Calib-eval 上第 20 百分位（gate_pct 與
# θ* 對齊），本輪凍結，Holdout 上沿用不重算。
VOL_COVERAGE_MATCHED_CUTPOINT = 0.23116970731839864


def _is_report_output_path(path: str) -> bool:
    return bool(_REPORT_OUTPUT_PATH_RE.match(path.replace("\\", "/")))


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_script_commit_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """比照既有先例（`ug_g3_sb6_gating_report.py` 等）：`dirty` 只看
    已追蹤檔案的修改，未追蹤檔案記在 `untracked_paths` 但不計入 `dirty`。"""
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


# ==============================================================================
# PO 必含項 1：跨界折雙重排除揭露
# ==============================================================================

def compute_folds_excluded_by_both(splitter, panel: pd.DataFrame, holdout_start_date) -> List[int]:
    """回傳同時被 `iter_oof_folds()` 與 `iter_holdout_folds()` 排除的折號
    （跨界折）——訂正 1 的機械揭露欄位，不得靜默假設現行資料沒有跨界折。"""
    panel_reset = panel.reset_index(drop=True)
    all_fold_nums = {meta["fold"] for _, _, meta in splitter.split(panel_reset)}
    oof_fold_nums = {meta["fold"] for _, _, meta in iter_oof_folds(splitter, panel_reset, holdout_start_date)}
    holdout_fold_nums = {meta["fold"] for _, _, meta in iter_holdout_folds(splitter, panel_reset, holdout_start_date)}
    return sorted(all_fold_nums - oof_fold_nums - holdout_fold_nums)


# ==============================================================================
# PO 必含項 3、4：只讀一次
# ==============================================================================

def _is_holdout_already_consumed(evidence_path: Path) -> bool:
    if not evidence_path.exists():
        return False
    with open(evidence_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return "holdout_consumed_at" in data


def _should_write_holdout(
    *, write_flag: bool, holdout_start_date, script_dirty: bool, already_consumed: bool,
) -> Tuple[bool, str]:
    """四條件交集才允許正式寫入：`--write` 給了、`holdout_start_date` 恰為
    `HOLDOUT_START_DATE` 常數（乾跑一律拒寫）、工作樹乾淨、尚未消費過
    （**無任何旗標可繞過**——訂正 4，`--force-reconsume` 已移除）。"""
    if not write_flag:
        return False, "write_flag 為 False（未帶 --write）"
    if pd.Timestamp(holdout_start_date) != HOLDOUT_START_DATE:
        return False, (
            f"holdout_start_date（{holdout_start_date}）不等於 HOLDOUT_START_DATE "
            f"常數（{HOLDOUT_START_DATE}）——拒絕正式寫入（乾跑模式）"
        )
    if script_dirty:
        return False, "工作樹不乾淨（script_dirty=True），拒絕寫入"
    if already_consumed:
        return False, "Holdout 已消費過（holdout_consumed_at 已存在），拒絕二次寫入——無旗標可繞過"
    return True, "write_flag=True 且 holdout_start_date 為常數且工作樹乾淨且尚未消費"


# ==============================================================================
# PO 必含項 5：凍結值比對守衛
# ==============================================================================

def extract_sb6_reference(sb6_json: Dict[str, Any]) -> Dict[str, Any]:
    """從真實 `UG_G3_SB6_gating_report.json` 抽出本 SB 需要沿用的凍結值：
    `θ*`、選點規則、regime 三分位切點（低／中組上界）。"""
    selected = sb6_json["selected_theta"]
    regime = sb6_json["regime_diagnostic"]
    low = next(r for r in regime if r["label"] == "low")
    mid = next(r for r in regime if r["label"] == "mid")
    return {
        "theta_star": selected["theta"],
        "rule": selected["rule"],
        "tercile_low_cutpoint": low["cutpoint_upper"],
        "tercile_mid_cutpoint": mid["cutpoint_upper"],
    }


def assert_frozen_value_matches(actual: float, expected: float, name: str, tol: float = 1e-9) -> None:
    """任何凍結值（`θ*`、regime 切點、覆蓋率對齊切點）在報告腳本內使用前
    都要過這道守衛，防止意外重算後悄悄使用了不同的數字。"""
    if abs(actual - expected) > tol:
        raise GatingContractError(
            f"{name} 與凍結值不符：actual={actual!r} expected={expected!r}"
            f"（差值 {abs(actual - expected):.2e} > 容差 {tol}）——拒絕使用重算後的數值。"
        )


# ==============================================================================
# 核心指標函式：baseline 比較與逐折穩定性共用
# ==============================================================================

def evaluate_gate_rule(gated_mask, y_true, base_rate: float) -> Dict[str, Optional[float]]:
    """給定任意布林 `gated_mask`（True=觀望），計算 precision／coverage／
    recall／lift。Timeout=class 0。`gated` 為空集時 `precision`／`lift`
    為 `None`，不得回傳 `0` 或基期（比照 `UG-G3-SB6` 既有慣例）。"""
    gated_mask = np.asarray(gated_mask, dtype=bool)
    y_true = np.asarray(y_true)
    n = len(y_true)
    is_timeout = (y_true == 0)
    n_gated = int(gated_mask.sum())
    n_timeout = int(is_timeout.sum())
    coverage = 1.0 - n_gated / n if n > 0 else None

    if n_gated == 0:
        precision = None
        lift = None
    else:
        precision = float(is_timeout[gated_mask].sum() / n_gated)
        lift = (precision / base_rate) if base_rate > 0 else None

    recall = float(is_timeout[gated_mask].sum() / n_timeout) if n_timeout > 0 else None

    return {
        "n": n, "n_timeout": n_timeout, "n_gated": n_gated,
        "coverage": coverage, "precision": precision, "recall": recall, "lift": lift,
    }


def build_per_fold_stability(fold_id, p0, y_true, theta_star: float) -> List[Dict[str, Any]]:
    """逐折（Holdout 每一折）表：`n`／`n_timeout`／`n_gated` 齊全，
    `n_gated=0` 時 `precision` 為 `null`。**不設逐折通過／失敗判準**，
    只用來檢視是否有折明顯偏離其餘折，不對任何單折下結論。base_rate 採
    該折自身的 Timeout 比例（自成一體，不依賴外部全域基期）。"""
    fold_id = np.asarray(fold_id)
    p0 = np.asarray(p0)
    y_true = np.asarray(y_true)
    rows: List[Dict[str, Any]] = []
    for fid in sorted(set(fold_id.tolist())):
        mask = fold_id == fid
        fold_p0 = p0[mask]
        fold_y = y_true[mask]
        fold_base_rate = float((fold_y == 0).sum() / len(fold_y)) if len(fold_y) > 0 else 0.0
        gated_mask = fold_p0 >= theta_star
        metrics = evaluate_gate_rule(gated_mask, fold_y, fold_base_rate)
        rows.append({"fold_id": int(fid), **metrics})
    return rows


# ==============================================================================
# PO 複核 GREEN ac73432 發現：retained_direction_shift 訂正
# ==============================================================================

def build_retained_direction_shift(p0, y_true, theta_star: float) -> Dict[str, Optional[float]]:
    """Gate A §3.2(c) 保留集方向比例位移——**直接複用**
    `src.ml.gating.compute_gating_metrics()`（`UG-G3-SB6` 既有函式，已有
    自己的測試覆蓋），不重寫等義邏輯。**`y_true` 必須是
    `target_triple_barrier` 的 {-1,0,1} 值域**——PO 複核 GREEN `ac73432`
    時發現原實作誤用 `target_up_down`（{0,1}）算這四個欄位，導致
    `retained_minus1_rate` 恆為 0（up_down 根本沒有 -1 這個值）。回傳
    `compute_gating_metrics()` 的 `retained_minus1_rate`／
    `retained_plus1_rate`／`shift_minus1`／`shift_plus1` 四欄。"""
    metrics = compute_gating_metrics(p0, y_true, theta_star)
    return {
        "retained_minus1_rate": metrics["retained_minus1_rate"],
        "retained_plus1_rate": metrics["retained_plus1_rate"],
        "shift_minus1": metrics["shift_minus1"],
        "shift_plus1": metrics["shift_plus1"],
    }


# ==============================================================================
# PO 複核 GREEN ac73432 要求：Specialist OOF 重生比對寫進證據 JSON
# ==============================================================================

def assert_regenerated_oof_matches_sb4(
    new_oof: pd.DataFrame, sb4_oof_path: Path, tol: float = 1e-9,
) -> Dict[str, Any]:
    """以 `(stock_id, trade_date, fold_id)` 對齊本次重新產生的 Specialist
    OOF（`new_oof`：`_build_holdout_specialist_oof()` 的輸出）與真實
    `UG-G3-SB4` OOF parquet 的重疊列，逐欄比對最大絕對差，寫入可稽核的
    診斷字典（不只在腳本外算，PO 複核 `ac73432` 的乾跑要求）。正式消費
    （折 33-42）與 `UG-G3-SB4` OOF parquet（僅折 0-32）通常**沒有重疊
    列**——這不是錯誤，回傳 `n_rows_compared=0` 並附原因說明；乾跑
    （偽 Holdout 折落在 `UG-G3-SB4` 已涵蓋範圍）才會有重疊列可比對。
    差值超出 `tol` 才拋錯。"""
    sb4_oof = pd.read_parquet(sb4_oof_path)
    sb4_oof["trade_date"] = pd.to_datetime(sb4_oof["trade_date"])
    new_oof = new_oof.copy()
    new_oof["trade_date"] = pd.to_datetime(new_oof["trade_date"])

    prob_cols = [c for c in new_oof.columns if c not in ("stock_id", "trade_date", "fold_id")]
    merged = new_oof.merge(
        sb4_oof, on=["stock_id", "trade_date", "fold_id"], suffixes=("_new", "_sb4"), how="inner")
    n_rows_compared = int(len(merged))

    if n_rows_compared == 0:
        return {
            "n_rows_compared": 0, "n_cols": len(prob_cols), "max_abs_diff": None, "tol": tol,
            "note": (
                "無重疊列——正式消費（折 33-42）與 UG-G3-SB4 OOF parquet"
                "（僅折 0-32）通常不重疊，屬預期，非錯誤"
            ),
        }

    max_abs_diff = 0.0
    for c in prob_cols:
        a = merged[f"{c}_new"].to_numpy(dtype=float)
        b = merged[f"{c}_sb4"].to_numpy(dtype=float)
        both_nan = np.isnan(a) & np.isnan(b)
        diff = np.where(both_nan, 0.0, np.abs(a - b))
        d = float(np.nanmax(diff)) if len(diff) else 0.0
        max_abs_diff = max(max_abs_diff, d)

    if max_abs_diff > tol:
        raise GatingContractError(
            f"重新產生的 Specialist OOF 與真實 UG-G3-SB4 parquet 同折同列不符："
            f"max_abs_diff={max_abs_diff:.3e} > tol={tol}（{n_rows_compared} 列比對）"
        )

    return {"n_rows_compared": n_rows_compared, "n_cols": len(prob_cols), "max_abs_diff": max_abs_diff, "tol": tol}


# ==============================================================================
# PO 必含項 8：target_up_down 觀察用 AUC
# ==============================================================================

def build_up_down_observational_auc(scores: Dict[str, np.ndarray], y_true) -> Dict[str, Any]:
    """`target_up_down` 的 Holdout 觀察用 AUC——標記 `observational=True`，
    結構上與 gating 判準函式（`curve_rows` list-of-dict）不相容，不得誤餵。"""
    from sklearn.metrics import roc_auc_score

    y_true = np.asarray(y_true)
    result: Dict[str, Any] = {"observational": True}
    for name, s in scores.items():
        result[name] = float(roc_auc_score(y_true, np.asarray(s)))
    return result


# ==============================================================================
# 主流程
# ==============================================================================

def _build_holdout_specialist_oof(
    panel: pd.DataFrame, splitter, holdout_start_date, *, target_column: str = TARGET_COLUMN,
) -> pd.DataFrame:
    """對 `iter_holdout_folds()` 產出的每一折，逐折重新 `fit`／`predict`
    四個 Specialist（比照 `UG-G3-SB4` 既有流程，僅折範圍不同——沿用同一套
    `prepare_fold_data()`／`fit_predict_specialist_fold()`，不重寫等義
    邏輯）。回傳 `assemble_oof_matrix()` 的寬格式輸出。`target_column`
    預設 `target_triple_barrier`（主 gating 管線）；`build_up_down_holdout_specialist_oof()`
    另外對 `target_up_down` 面板呼叫本函式一次（§3.4 觀察用 AUC，PO 裁決 (c)）。"""
    fold_results: List[Dict[str, Any]] = []
    for train_idx, test_idx, fold_meta in iter_holdout_folds(splitter, panel, holdout_start_date):
        fold_id = fold_meta["fold"]
        train_prepared = prepare_fold_data(
            panel, train_idx, ARM_A_FEATURE_COLS, [], target_col="target", arm="A")
        test_prepared = prepare_fold_data(
            panel, test_idx, ARM_A_FEATURE_COLS, [], target_col="target", arm="A")
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

    if not fold_results:
        raise GatingContractError(
            f"iter_holdout_folds() 對邊界 {holdout_start_date} 未產出任何折——拒絕產出空報告。"
        )

    oof = assemble_oof_matrix(fold_results, target_column=target_column)
    oof["trade_date"] = pd.to_datetime(oof["trade_date"])
    return oof


def _compute_up_down_observational_auc_holdout(
    up_down_panel_path: Path, holdout_start_date, *, is_real_consumption: bool,
) -> Dict[str, Any]:
    """§3.4（PO 裁決 (c)）：`target_up_down` 於（偽）Holdout 的觀察用 AUC。
    對 `target_up_down` 凍結面板**獨立重跑**一次 Specialist OOF 生成
    （`iter_holdout_folds()`，該 target 專屬的 `label_horizon=1`／
    `label_end_date_col="label_end_date"`，與 `target_triple_barrier`
    主管線完全分開——**不得**拿 triple_barrier 的 class `+1` 機率欄
    當作 up_down 的替代品，那不是同一個訓練目標）。只印四個 Specialist
    的 AUC，`observational=True`，不進任何 gating 判準。

    **正式消費實測發現的缺陷（已修正，不得重犯）**：本函式的面板截斷是
    給乾跑用的安全網（防止乾跑的 boundary 參數波及真正折 33-42），**只
    能在 `is_real_consumption=False` 時套用**——第一次正式消費嘗試時
    無條件截斷，把折 33-42 的資料在呼叫 `iter_holdout_folds()` 之前就
    全部濾掉，導致「未產出任何折」直接拋錯（無資料受影響，`run_report()`
    在任何寫入動作之前拋錯，`main()` 的 `_should_write_holdout()` 檢查
    在先，證據 JSON 從未產生）。"""
    target_column = "target_up_down"
    up_down_sha256 = verify_panel_sha256(up_down_panel_path, target_column)
    panel = pd.read_parquet(up_down_panel_path).reset_index(drop=True)
    if not is_real_consumption:
        panel = panel[panel["trade_date"] < HOLDOUT_START_DATE].reset_index(drop=True)

    splitter = build_splitter(target_column)
    oof = _build_holdout_specialist_oof(
        panel, splitter, holdout_start_date, target_column=target_column)

    label_end_col = TARGET_CONFIG[target_column]["label_end_date_col"]
    lookup_cols = ["stock_id", "trade_date", label_end_col, target_column]
    label_lookup = panel[lookup_cols].drop_duplicates()
    label_lookup["trade_date"] = pd.to_datetime(label_lookup["trade_date"])
    before_merge = len(oof)
    oof = oof.merge(label_lookup, on=["stock_id", "trade_date"], how="left")
    if len(oof) != before_merge or oof[target_column].isna().any():
        raise GatingContractError(
            "target_up_down 觀察用 AUC：合併標籤欄後列數改變或有缺值，拒絕計算。"
        )
    y_up_down = oof[target_column].astype(int).to_numpy()

    scores = {}
    for model_key in ("lr", "rf", "lgbm", "xgb"):
        col = f"{model_key}_A_p1"
        if col in oof.columns and not oof[col].isna().any():
            scores[model_key] = oof[col].to_numpy()

    if not scores or len(set(y_up_down.tolist())) < 2:
        return {"observational": True, "panel_sha256": up_down_sha256,
                "note": "樣本不足或單一類別，未計算 AUC"}

    result = build_up_down_observational_auc(scores, y_up_down)
    result["panel_sha256"] = up_down_sha256
    result["row_count"] = int(len(y_up_down))
    return result


def run_report(
    panel_path: Path,
    oof_generation_evidence_path: Path,
    sb4_meta_learner_report_path: Path,
    sb5_reference_path: Path,
    sb6_reference_path: Path,
    *,
    holdout_start_date: Optional[Any] = None,
    up_down_panel_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """完整報告管線。`holdout_start_date` 為 `None` 時預設
    `HOLDOUT_START_DATE`（正式消費）；乾跑時明確傳入不同邊界（例如
    `CALIB_EVAL_FOLDS` 對應的起日），把折 30-32 當偽 Holdout 跑過同一段
    程式碼——**無論傳入什麼邊界，面板都會先截斷到真正 Holdout 起點之前**
    （見模組 docstring「乾跑安全網」），物理上不可能讀到真正的折 33-42。
    """
    _run_report_start_time = time.monotonic()

    boundary = pd.Timestamp(holdout_start_date) if holdout_start_date is not None else HOLDOUT_START_DATE
    is_real_consumption = bool(boundary == HOLDOUT_START_DATE)

    sha256 = verify_panel_sha256(panel_path, TARGET_COLUMN)
    panel = pd.read_parquet(panel_path).reset_index(drop=True)

    if not is_real_consumption:
        # 乾跑安全網：不論 boundary 參數為何，物理上先移除真正 Holdout 的列。
        panel = panel[panel["trade_date"] < HOLDOUT_START_DATE].reset_index(drop=True)

    splitter = build_splitter(TARGET_COLUMN)
    folds_excluded_by_both = compute_folds_excluded_by_both(splitter, panel, boundary)

    raw_holdout_oof = _build_holdout_specialist_oof(panel, splitter, boundary)

    if is_real_consumption:
        assert_holdout_only(raw_holdout_oof["fold_id"], raw_holdout_oof["trade_date"])

    # PO 複核 GREEN ac73432 要求：Specialist OOF 重生比對寫進證據 JSON，
    # 不只在腳本外算。對 raw_holdout_oof（合併標籤欄之前，只有
    # stock_id/trade_date/fold_id/機率欄）比對，merge 進其他欄之後就不再
    # 是單純的機率欄矩陣，不能拿去跟 SB4 parquet 比。
    with open(oof_generation_evidence_path, "r", encoding="utf-8") as f:
        gen_evidence = json.load(f)
    existing_oof_path = Path(gen_evidence["oof_parquet_path"])
    specialist_oof_regeneration_check = assert_regenerated_oof_matches_sb4(
        raw_holdout_oof, existing_oof_path)

    holdout_oof = raw_holdout_oof

    label_end_col = TARGET_CONFIG[TARGET_COLUMN]["label_end_date_col"]
    lookup_cols = [
        "stock_id", "trade_date", label_end_col,
        "target_up_down", "target_triple_barrier", *META_REGIME_FEATURE_COLS,
    ]
    label_lookup = panel[lookup_cols].drop_duplicates()
    label_lookup["trade_date"] = pd.to_datetime(label_lookup["trade_date"])
    before_merge = len(holdout_oof)
    holdout_oof = holdout_oof.merge(label_lookup, on=["stock_id", "trade_date"], how="left")
    if len(holdout_oof) != before_merge:
        raise GatingContractError(
            f"合併標籤／regime 欄後列數由 {before_merge} 變為 {len(holdout_oof)}——"
            "label_lookup 出現重複鍵，拒絕產出。"
        )
    must_not_be_null = [label_end_col, "target_up_down", TARGET_COLUMN, *META_REGIME_FEATURE_COLS]
    still_null = [c for c in must_not_be_null if holdout_oof[c].isna().any()]
    if still_null:
        raise GatingContractError(f"合併後仍有列缺以下欄位：{still_null}——拒絕產出。")
    holdout_oof[TARGET_COLUMN] = holdout_oof[TARGET_COLUMN].astype(int)
    holdout_oof["target_up_down"] = holdout_oof["target_up_down"].astype(int)
    holdout_oof["split_segment"] = "holdout_new"

    labels = TARGET_CLASS_DOMAINS[TARGET_COLUMN]

    X_new, _, new_retained_idx = build_meta_learner_input(
        holdout_oof, segment="holdout_new", target_column=TARGET_COLUMN, return_retained_index=True)
    y_new = holdout_oof.loc[new_retained_idx, TARGET_COLUMN].to_numpy()
    fold_id_new = holdout_oof.loc[new_retained_idx, "fold_id"].to_numpy()
    volatility_new = X_new["volatility_20d"].to_numpy()

    # ---- 重建 Meta(A)-LR／Ridge（凍結：訓練資料範圍＝SB4 既有 OOF 的
    # Meta-Train 段，folds 0-26；超參數逐字同 SB4/SB5/SB6） ----
    existing_oof = pd.read_parquet(existing_oof_path)

    X_train, _, train_idx2 = build_meta_learner_input(
        existing_oof, segment="meta_train", target_column=TARGET_COLUMN, return_retained_index=True)
    y_train = existing_oof.loc[train_idx2, TARGET_COLUMN].to_numpy()
    X_meta_eval, _, meta_eval_idx2 = build_meta_learner_input(
        existing_oof, segment="meta_eval", target_column=TARGET_COLUMN, return_retained_index=True)
    y_meta_eval = existing_oof.loc[meta_eval_idx2, TARGET_COLUMN].to_numpy()
    fold_id_meta_eval = existing_oof.loc[meta_eval_idx2, "fold_id"].to_numpy()

    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler
    from src.ml.calibration import brier_score_multiclass

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_new_scaled = scaler.transform(X_new)
    X_meta_eval_scaled = scaler.transform(X_meta_eval)

    fitted_models: Dict[str, Any] = {}
    actual_macro_f1: Dict[str, float] = {}
    for name, ModelCls in (("LogisticRegression", LogisticRegression), ("RidgeClassifier", RidgeClassifier)):
        fit_kwargs: Dict[str, Any] = {"random_state": 42}
        if name == "LogisticRegression":
            fit_kwargs["max_iter"] = 500
        model = ModelCls(**fit_kwargs)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            model.fit(X_train_scaled, y_train)
        fitted_models[name] = model

        y_pred_meta_eval = model.predict(X_meta_eval_scaled)
        per_class = compute_per_class_metrics(y_meta_eval, y_pred_meta_eval, labels=labels)
        actual_macro_f1[name] = per_class["macro_f1"]

    with open(sb4_meta_learner_report_path, "r", encoding="utf-8") as f:
        sb4_report_evidence = json.load(f)
    assert_matches_sb4_report(actual_macro_f1, sb4_report_evidence)

    # ---- 重建校準器（凍結：Calib-fit＝折 27-29，來源同上 existing_oof） ----
    calib_fit_mask = np.isin(fold_id_meta_eval, CALIB_FIT_FOLDS)
    calib_eval_mask_meta = np.isin(fold_id_meta_eval, CALIB_EVAL_FOLDS)

    with open(sb5_reference_path, "r", encoding="utf-8") as f:
        sb5_json = json.load(f)

    fitted_calibrators: Dict[str, Any] = {}
    for name, model in fitted_models.items():
        raw_scores_all = model.decision_function(X_meta_eval_scaled)
        raw_fit = raw_scores_all[calib_fit_mask]
        raw_eval_calib = raw_scores_all[calib_eval_mask_meta]
        y_fit = y_meta_eval[calib_fit_mask]
        y_eval_calib = y_meta_eval[calib_eval_mask_meta]
        fold_fit = fold_id_meta_eval[calib_fit_mask]
        fold_eval_calib = fold_id_meta_eval[calib_eval_mask_meta]

        calibrator = fit_calibrator(
            raw_fit, y_fit, fold_id=fold_fit, method="sigmoid", target_column=TARGET_COLUMN)
        quality = evaluate_calibration_quality(
            calibrator, raw_eval_calib, y_eval_calib, fold_id=fold_eval_calib, method="sigmoid")
        class0_quality = quality[0]
        calibrated_probs = apply_calibrator(calibrator, raw_eval_calib)
        brier_after = brier_score_multiclass(y_eval_calib, calibrated_probs, class_order=labels)
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
        entry = sb5_json["calibration_results"][sb5_model_key]
        class0 = entry["per_class_quality"]["0"]
        sb5_reference = {
            "brier_after": entry["brier_after"],
            "auc_before": class0["auc_before"],
            "auc_after": class0["auc_after"],
            "platt_slope": class0["platt_slope"],
            "platt_intercept": class0["platt_intercept"],
            "auc_calib_fit_raw_class0": entry["auc_calib_fit_raw"]["0"],
        }
        assert_calibrator_matches_sb5(rebuilt_quality, sb5_reference)
        fitted_calibrators[name] = calibrator

    # ---- 套用凍結的 LR 校準器到新產生的 Holdout（或偽 Holdout）機率 ----
    raw_new_lr = fitted_models["LogisticRegression"].decision_function(X_new_scaled)
    p0_new = apply_calibrator(fitted_calibrators["LogisticRegression"], raw_new_lr)[:, labels.index(0)]

    # ---- 凍結值（θ*、regime 切點）讀取與比對守衛 ----
    with open(sb6_reference_path, "r", encoding="utf-8") as f:
        sb6_json = json.load(f)
    sb6_ref = extract_sb6_reference(sb6_json)
    theta_star = sb6_ref["theta_star"]
    tercile_low_cutpoint = sb6_ref["tercile_low_cutpoint"]

    # ---- Timeout gating 於（偽）Holdout ----
    base_rate = float((y_new == 0).sum() / len(y_new))
    timeout_gating = evaluate_gate_rule(p0_new >= theta_star, y_new, base_rate)

    # ---- 波動率基線（i）三分位、（ii）覆蓋率對齊版 ----
    vol_tercile = evaluate_gate_rule(volatility_new <= tercile_low_cutpoint, y_new, base_rate)
    vol_coverage_matched = evaluate_gate_rule(volatility_new <= VOL_COVERAGE_MATCHED_CUTPOINT, y_new, base_rate)

    baseline_comparison = {
        "random_baseline_precision": base_rate,
        "volatility_tercile": vol_tercile,
        "volatility_coverage_matched": vol_coverage_matched,
        "timeout_gating": timeout_gating,
    }

    # ---- 保留集方向比例位移（只揭露，不下結論） ----
    # 訂正（PO 複核 ac73432 發現）：必須用 target_triple_barrier 的
    # {-1,0,1} 值域（y_new）——先前誤用 target_up_down 的 {0,1} 值域，
    # 讓 retained_minus1_rate 恆為 0。
    retained_direction_shift = build_retained_direction_shift(p0_new, y_new, theta_star)

    # ---- 逐折穩定性 ----
    per_fold_stability = build_per_fold_stability(fold_id_new, p0_new, y_new, theta_star)

    # ---- target_up_down 觀察用 AUC（PO 裁決 (c)，只印，不進任何判準）----
    # 對 target_up_down 面板獨立重跑一次 Specialist OOF 生成（不是拿
    # triple_barrier 的 class +1 機率欄頂替——那是不同的訓練目標）。
    if up_down_panel_path is not None:
        up_down_observational_auc = _compute_up_down_observational_auc_holdout(
            up_down_panel_path, boundary, is_real_consumption=is_real_consumption)
    else:
        up_down_observational_auc = {
            "observational": True, "note": "未提供 up_down_panel_path，本次執行未計算"
        }

    # ---- 凍結產物清單（Gate A §2.3 十項），供讀者不查其他文件即可確認
    # 這次真的是套用凍結產物，不是意外重算 ----
    up_down_panel_sha256 = None
    if up_down_panel_path is not None:
        up_down_panel_sha256 = compute_file_sha256(up_down_panel_path)
    frozen_artifacts = {
        "panel_sha256": {"target_triple_barrier": sha256, "target_up_down": up_down_panel_sha256},
        "sb4_oof_parquet_sha256": gen_evidence.get("oof_parquet_sha256"),
        "sb4_meta_learner_report_sha256": compute_file_sha256(sb4_meta_learner_report_path),
        "sb5_reference_sha256": compute_file_sha256(sb5_reference_path),
        "sb6_reference_sha256": compute_file_sha256(sb6_reference_path),
        "theta_star": sb6_ref["theta_star"],
        "selection_rule": sb6_ref["rule"],
        "tercile_low_cutpoint": sb6_ref["tercile_low_cutpoint"],
        "tercile_mid_cutpoint": sb6_ref["tercile_mid_cutpoint"],
        "vol_coverage_matched_cutpoint": VOL_COVERAGE_MATCHED_CUTPOINT,
        "gating_constants": {
            "MIN_COVERAGE": MIN_COVERAGE, "MIN_LIFT": MIN_LIFT,
            "MIN_RECALL": MIN_RECALL, "MIN_POSITIVE_FOR_AUC": MIN_POSITIVE_FOR_AUC,
        },
        "theta_grid_source": "UG_G3_SB6_gating_report.json 的 theta_grid 欄（LogisticRegression 校準後 P0 分布建構），本 SB 不重新產生網格",
        "specialist_training_config": {
            "train_window_size": TRAIN_WINDOW_SIZE, "test_window_size": TEST_WINDOW_SIZE,
            "mode": "rolling", "embargo_days": EMBARGO_DAYS,
            "label_horizon": TARGET_CONFIG[TARGET_COLUMN]["label_horizon"],
            "label_end_date_col": TARGET_CONFIG[TARGET_COLUMN]["label_end_date_col"],
        },
    }

    report_dict: Dict[str, Any] = {
        "target": TARGET_COLUMN,
        "panel_sha256": sha256,
        "holdout_start_date": str(boundary.date()),
        "is_real_consumption": is_real_consumption,
        "folds_processed": sorted(set(int(x) for x in fold_id_new.tolist())),
        "folds_excluded_by_both_iterators": folds_excluded_by_both,
        "holdout_tail_gap_excluded": True,
        "holdout_row_count": int(len(y_new)),
        "holdout_class_distribution": {str(c): int((y_new == c).sum()) for c in labels},
        "sb6_reference": sb6_ref,
        "vol_coverage_matched_cutpoint": VOL_COVERAGE_MATCHED_CUTPOINT,
        "frozen_artifacts": frozen_artifacts,
        "specialist_oof_regeneration_check": specialist_oof_regeneration_check,
        "holdout_gating_metrics": timeout_gating,
        "baseline_comparison": baseline_comparison,
        "retained_direction_shift": retained_direction_shift,
        "per_fold_stability": per_fold_stability,
        "up_down_observational_auc": up_down_observational_auc,
        "max_rows_used": None,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_dict["total_elapsed_seconds"] = time.monotonic() - _run_report_start_time
    return report_dict


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-path", type=Path, required=False)
    parser.add_argument("--oof-generation-evidence-path", type=Path, required=False)
    parser.add_argument("--sb4-meta-learner-report-path", type=Path, required=False)
    parser.add_argument("--sb5-reference-path", type=Path, required=False)
    parser.add_argument("--sb6-reference-path", type=Path, required=False)
    parser.add_argument("--up-down-panel-path", type=Path, required=False)
    parser.add_argument("--holdout-start-date", type=str, default=None)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    commit_info = get_script_commit_info()
    out_path = DEFAULT_EVIDENCE_DIR / "UG_G3_SB7_holdout_report.json"

    if args.write:
        already_consumed = _is_holdout_already_consumed(out_path)
        holdout_start_date = (
            pd.Timestamp(args.holdout_start_date) if args.holdout_start_date else HOLDOUT_START_DATE
        )
        should_write, reason = _should_write_holdout(
            write_flag=args.write, holdout_start_date=holdout_start_date,
            script_dirty=commit_info["dirty"], already_consumed=already_consumed,
        )
        if not should_write:
            print(f"REFUSED: {reason}", file=sys.stderr)
            return 1

    if args.panel_path is None:
        print("尚未提供 --panel-path 等參數，僅供 main() 早期守衛的獨立驗證。", file=sys.stderr)
        return 1

    holdout_start_date = (
        pd.Timestamp(args.holdout_start_date) if args.holdout_start_date else None
    )
    report_dict = run_report(
        args.panel_path, args.oof_generation_evidence_path,
        args.sb4_meta_learner_report_path, args.sb5_reference_path, args.sb6_reference_path,
        holdout_start_date=holdout_start_date,
        up_down_panel_path=args.up_down_panel_path,
    )
    report_dict["script_commit"] = commit_info["commit"]
    report_dict["script_dirty"] = commit_info["dirty"]
    report_dict["script_dirty_paths"] = commit_info["dirty_paths"]
    report_dict["script_untracked_paths"] = commit_info["untracked_paths"]

    if args.write:
        report_dict["holdout_consumed_at"] = datetime.now(timezone.utc).isoformat()
        DEFAULT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, default=_json_default, ensure_ascii=False, indent=2)
        print(f"寫入 {out_path}")
    else:
        print(json.dumps(report_dict, default=_json_default, ensure_ascii=False, indent=2)[:2000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
