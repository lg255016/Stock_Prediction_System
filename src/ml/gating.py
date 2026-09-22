# -*- coding: utf-8 -*-
"""`UG-G3-SB6` Timeout Gating（原「Selective Inference & Regime Gating」）。

依 `DEC-041`（`UG-G3-SB5` Gate B 裁決）：`target_up_down` 在折 27-32
全線無可偵測排序訊號（`RISK-030`），本 SB 對其**全面停做**——不跑、不
產出任何門檻或報告列。改以 `target_triple_barrier` Timeout 類（class 0）
經 `src/ml/calibration.py::fit_calibrator()`／`apply_calibrator()` 校準後
的機率為 gating 對象，產品形態定位為「何時不交易」而非「往哪個方向
交易」（Gate A 提案 `doc/upgrade/gates/UG_G3_SB6_GATE_A_PROPOSAL.md`，
commit `83749de`）。

**本模組唯讀複用 `src/ml/calibration.py`／`src/ml/stacking.py`，不修改
兩者**——`calibrated_timeout_probability()` 是本模組取得校準後機率的
唯一函式，內部呼叫既有 `apply_calibrator()`，class 0 的欄位索引依
`TARGET_CLASS_DOMAINS["target_triple_barrier"]`（`[-1, 0, 1]`）動態推導，
不寫死索引——定義域順序一旦改變，寫死的索引會靜默錯欄（Gate A 提案
「實作提醒」）。

**gating 對象事前宣告（Gate A 裁決 (c)）**：Meta(A)-LogisticRegression
為唯一 gating 來源，不在 Calib-eval 上與 Ridge 比較後選定——理由是
`UG-G3-SB4` TB 段排名 LR 已是最佳、`UG-G3-SB5` 校準品質兩者相當、探測
曲線幾乎重合，若再拿 Calib-eval（僅 389 個 Timeout 正例）多選一次
校準器，等於對同一批小樣本雜訊多擬合一次——這正是門檻選定只准用
Calib-eval（不得重用 Calib-fit）要避免的事。

**`P₀` 的定義（§2.5 教訓）**：`P₀` 必須是 `apply_calibrator()`
**正規化後**（三類 OvR 機率和為 1）的 class 0 輸出，不得對 class 0
另外做一次未正規化的單一 Platt 擬合——兩者在稀疏尾端可有超過 0.09 的
系統性差距，會讓門檻的絕對數值失真（雖然 precision／recall 本身受
影響有限，`gate_pct` 相同時兩者幾乎一致，但 `θ` 的絕對值不可互換）。

**Gate A 裁決 (a)：Timeout gating 三項量化判準**——選定的 `θ*` 須同時
滿足 `coverage>=0.80`、`lift>=4.0`、`recall>=0.60`；在滿足三項的候選
集中取召回最高者，同召回取精準度較高者（`rule="max_recall_tiebreak_precision"`）。
**這三項判準是看過 Calib-eval 實測曲線之後訂的事後目標**，不宣稱在
未來資料（例如 `UG-G3-SB7` 的 Holdout）上會穩定重現——樣本外檢驗
留給 `UG-G3-SB7`。

**Gate A 裁決 (b)：regime 診斷為必做**——`volatility_20d`（不含
`ma20_bias_ratio`，後者不在 OOF parquet 內）三分位分組，各組在 `θ`
下報 `compute_gating_metrics()` 的四項指標；正例數 `<10` 的組不報
AUC（統計上無意義），只報 `timeout_rate`。這是唯讀事後分組診斷，
驗證 `UG-G3-SB5` Gate B §4 的 `INFERENCE`（Timeout 訊號大半是波動率
水準本身），不訓練任何新模型。

**Gate A 裁決 (d)：`src/ml/predictor.py`／`src/ml/evaluator.py` 明列
Out of Scope**——gating 決策是否接入既有預測輸出路徑，留給
`UG-G3-SB7`／Gate-4 決定，本模組不觸及。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.ml.stacking import HOLDOUT_START_DATE, TARGET_CLASS_DOMAINS
from src.ml.calibration import apply_calibrator


class GatingContractError(Exception):
    """本模組所有契約違反的共同基底類別。"""


class GatingTargetColumnError(GatingContractError, ValueError):
    """`target_column` 不是 `"target_triple_barrier"`。刻意同時繼承
    `ValueError`（Gate A 提案 §3.1 明寫「拋 `ValueError`」）與
    `GatingContractError`（供本模組統一以基底類別捕捉）。"""


class GatingHoldoutViolation(GatingContractError):
    """輸入含 Holdout 範圍的折序號或交易日期（`DEC-040`）。"""


class GatingCalibratorMismatchError(GatingContractError):
    """重建的校準器品質數字與 `UG-G3-SB5` 已核准證據不符。"""


#: Gate A 裁決 (a) 三項量化判準（Calib-eval 實測曲線核對後訂定，
#: 提案 §3.5；不宣稱未來資料穩定重現）。
MIN_COVERAGE = 0.80
MIN_LIFT = 4.0
MIN_RECALL = 0.60

#: Gate A 裁決 (b)：regime 診斷組內正例數低於此值不報 AUC。
MIN_POSITIVE_FOR_AUC = 10

#: Gate A 裁決 (b)：regime 診斷唯一使用的市場機制欄，不含
#: `ma20_bias_ratio`（不在 OOF parquet 內）。
REGIME_COL = "volatility_20d"

#: `θ` 等距細網格範圍（提案 §3.3 訂正 1：校準後 `P₀` 中位數僅 0.014、
#: p90 為 0.13、p99 為 0.39，原提案 `{0.05,...,0.95}` 網格 0.30 以上
#: 全為空集合）。
THETA_FINE_STEP = 0.005
THETA_FINE_MAX = 0.60


def _validate_target_column(target_column: str) -> None:
    """只允許 `"target_triple_barrier"`。`target_up_down` 依 `RISK-030`
    全面排除——折 27-32 全線無可偵測排序訊號，繼續對其做門檻選擇等於
    對雜訊擬合。"""
    if target_column != "target_triple_barrier":
        raise GatingTargetColumnError(
            f"target_column={target_column!r} 不允許；"
            "target_up_down 已依 RISK-030 全面排除，本模組只接受 "
            "target_triple_barrier"
        )


def assert_holdout_isolation(fold_id, trade_date) -> None:
    """`fold_id` 全部 `<=32` 且 `trade_date` 全部嚴格早於
    `HOLDOUT_START_DATE`（`2025-10-23`，常數取自 `src.ml.stacking`，
    不另抄一份日期字串）。任一違反皆拋 `GatingHoldoutViolation`。"""
    fold_id = np.asarray(fold_id)
    trade_date = pd.to_datetime(trade_date)
    if fold_id.max() > 32:
        raise GatingHoldoutViolation(
            f"fold_id 超出 Meta-Eval 範圍（Holdout 起自折 33）：max={fold_id.max()}"
        )
    if (trade_date >= HOLDOUT_START_DATE).any():
        raise GatingHoldoutViolation(
            f"trade_date 進入 Holdout 範圍（>= {HOLDOUT_START_DATE.date()}）"
        )


def assert_holdout_only(fold_id, trade_date) -> None:
    """`assert_holdout_isolation()` 的反向版本（`UG-G3-SB7`）——新產生的
    Holdout OOF 必須**全部**落在 Holdout 範圍內：`fold_id` 全部 `>=33`
    且 `trade_date` 全部不早於 `HOLDOUT_START_DATE`。任一列漏出（例如
    不小心混進 Meta-Eval／Calib-eval 段的列）即拋 `GatingHoldoutViolation`。
    """
    fold_id = np.asarray(fold_id)
    trade_date = pd.to_datetime(trade_date)
    if fold_id.min() < 33:
        raise GatingHoldoutViolation(
            f"fold_id 出現非 Holdout 折：min={fold_id.min()}（Holdout 起自折 33）"
        )
    if (trade_date < HOLDOUT_START_DATE).any():
        raise GatingHoldoutViolation(
            f"trade_date 早於 Holdout 起點（< {HOLDOUT_START_DATE.date()}）"
        )


def compute_gating_metrics(p0, y_true, theta: float) -> Dict[str, Optional[float]]:
    """在給定門檻 `theta` 下計算四項 gating 指標。`gated = {row: P₀(row)
    >= theta}`（**含 `=`**——恰等於門檻的列視為觀望）。

    Returns:
        `precision`：`gated` 內真正是 Timeout（`y=0`）的比例；`gated`
            為空集時為 `None`（**不得**回傳 `0` 或基期，兩者都是對
            「未定義」的錯誤偽裝，提案 §3.5 訂正 5）。
        `coverage`：`1 - len(gated)/n`，未被 gate 掉、保留給下游策略
            判斷的列比例。`gated` 為空集（沒有任何列被 gate）時恆為
            `1.0`（不受訂正 5 影響——訂正 5 管的是 `precision`）。
        `recall`：`gated` 內 Timeout 列數 / 全體 Timeout 列數；全體
            無 Timeout 時為 `0.0`。
        `retained_minus1_rate`／`retained_plus1_rate`：保留集（未被
            gate 掉）內 `y=-1`／`y=1` 的比例。
        `shift_minus1`／`shift_plus1`：保留集比例減去全體基期比例
            （不宣稱「勝率」，方向本身不可預測，`RISK-030`；只揭露
            位移量供人工核對）。
    """
    p0 = np.asarray(p0, dtype=float)
    y_true = np.asarray(y_true)
    gated_mask = p0 >= theta
    n = len(p0)
    n_gated = int(gated_mask.sum())
    total_timeout = int((y_true == 0).sum())

    coverage = 1 - n_gated / n
    if n_gated == 0:
        precision: Optional[float] = None
    else:
        precision = float((y_true[gated_mask] == 0).sum() / n_gated)
    recall = float((y_true[gated_mask] == 0).sum() / total_timeout) if total_timeout > 0 else 0.0

    retained_mask = ~gated_mask
    n_retained = int(retained_mask.sum())
    if n_retained > 0:
        retained_minus1_rate: Optional[float] = float((y_true[retained_mask] == -1).sum() / n_retained)
        retained_plus1_rate: Optional[float] = float((y_true[retained_mask] == 1).sum() / n_retained)
    else:
        retained_minus1_rate = None
        retained_plus1_rate = None

    overall_minus1_rate = float((y_true == -1).sum() / n)
    overall_plus1_rate = float((y_true == 1).sum() / n)
    shift_minus1 = (retained_minus1_rate - overall_minus1_rate) if retained_minus1_rate is not None else None
    shift_plus1 = (retained_plus1_rate - overall_plus1_rate) if retained_plus1_rate is not None else None

    return {
        "precision": precision,
        "coverage": coverage,
        "recall": recall,
        "retained_minus1_rate": retained_minus1_rate,
        "retained_plus1_rate": retained_plus1_rate,
        "shift_minus1": shift_minus1,
        "shift_plus1": shift_plus1,
    }


def build_theta_grid(p0) -> Dict[str, List[float]]:
    """雙軌 `θ` 網格（提案 §3.3 訂正 1）：

    - `"fine"`：`0` 到 `THETA_FINE_MAX`，步進 `THETA_FINE_STEP` 的等距
      網格（涵蓋校準後 `P₀` 99% 以上的實際範圍）。
    - `"quantile"`：`P₀` 的第 1～100 百分位、去重後排序——確保每個
      網格點都落在資料實際分布內，不重現原提案在稀疏尾端出現空段
      的問題。
    """
    p0 = np.asarray(p0, dtype=float)
    fine = list(np.round(np.arange(0.0, THETA_FINE_MAX + THETA_FINE_STEP / 2, THETA_FINE_STEP), 6))
    percentiles = np.percentile(p0, np.arange(1, 101))
    quantile = sorted(set(percentiles.tolist()))
    return {"fine": fine, "quantile": quantile}


def random_baseline_precision(y_true) -> float:
    """隨機 gating 基線的解析值——在任意覆蓋率下隨機抽樣，Timeout
    精準度的期望值恆等於全段 Timeout 基期（隨機抽樣不改變子集類別
    比例的期望），不需要蒙地卡羅模擬（提案 §3.5 訂正 3）。"""
    y_true = np.asarray(y_true)
    return float((y_true == 0).sum() / len(y_true))


def assemble_curve_row(theta: float, p0, y_true, base_rate: float) -> Dict[str, Optional[float]]:
    """組裝一列門檻曲線資料——`select_theta_star()` 本身不重算
    `lift`／`gate_pct`，兩者的正確性只能在這裡驗證。`lift = precision
    / base_rate`；`precision=None`（`gated` 為空集）時 `lift` 亦為
    `None`，不得回傳除以 `base_rate` 的任何數值。"""
    metrics = compute_gating_metrics(p0, y_true, theta)
    precision = metrics["precision"]
    lift = (precision / base_rate) if precision is not None else None
    return {
        "theta": theta,
        "gate_pct": 1 - metrics["coverage"],
        "coverage": metrics["coverage"],
        "precision": precision,
        "lift": lift,
        "recall": metrics["recall"],
    }


def select_theta_star(
    curve_rows: Sequence[Dict[str, Any]],
    *,
    min_coverage: float = MIN_COVERAGE,
    min_lift: float = MIN_LIFT,
    min_recall: float = MIN_RECALL,
    base_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """在門檻曲線（`curve_rows`，每列至少含 `theta`／`gate_pct`／
    `coverage`／`precision`／`lift`／`recall`）中，依 Gate A 裁決 (a)
    的三項判準（`>=`，含邊界）篩出可行集，取召回最高者、同召回取
    精準度較高者。`precision` 為 `None` 的列（門檻使 gated 為空集）
    一律跳過，不參與可行性判斷。

    無可行解時**誠實回報**，不拋例外、不靜默選一個不合格的 `θ`
    （提案 §5「可行區間為空」場景）。

    Args:
        base_rate: Calib-eval 全段 Timeout 基期，供呼叫端記錄／對照
            用（`curve_rows` 本身已內含 `lift`，本函式不用 `base_rate`
            重新計算 `lift`，避免 `curve_rows` 的四捨五入誤差與重算
            結果不一致）。選填，本函式不驗證亦不使用其數值。
    """
    feasible = [
        row for row in curve_rows
        if row["precision"] is not None
        and row["coverage"] >= min_coverage
        and row["lift"] >= min_lift
        and row["recall"] >= min_recall
    ]
    if not feasible:
        return {
            "feasible": False,
            "reason": "no theta satisfies coverage/lift/recall simultaneously",
        }
    best = max(feasible, key=lambda row: (row["recall"], row["precision"]))
    return {
        "feasible": True,
        "theta": best["theta"],
        "gate_pct": best["gate_pct"],
        "coverage": best["coverage"],
        "precision": best["precision"],
        "lift": best["lift"],
        "recall": best["recall"],
        "rule": "max_recall_tiebreak_precision",
    }


def calibrated_timeout_probability(calibrator, raw_scores) -> np.ndarray:
    """本模組取得 Timeout 類（class 0）校準後機率的唯一途徑——呼叫
    既有 `apply_calibrator()`（正規化後的 OvR 輸出），依
    `TARGET_CLASS_DOMAINS["target_triple_barrier"]` 動態推導 class 0
    的欄位索引，不寫死。**不得**另行對 class 0 做單一 Platt 擬合當
    作 `P₀` 的來源（§2.5 教訓：未正規化版本在稀疏尾端與正規化版本
    可相差 0.09 以上）。
    """
    idx = TARGET_CLASS_DOMAINS["target_triple_barrier"].index(0)
    return apply_calibrator(calibrator, raw_scores)[:, idx]


def regime_diagnostic(
    volatility,
    p0,
    y_true,
    theta: float,
    *,
    min_positive_for_auc: int = MIN_POSITIVE_FOR_AUC,
) -> List[Dict[str, Any]]:
    """`volatility_20d` 三分位分組診斷（Gate A 裁決 (b)，必做）。各組
    在 `theta` 下複用 `compute_gating_metrics()` 的**全部七項**指標
    （`precision`／`coverage`／`recall`／`retained_minus1_rate`／
    `retained_plus1_rate`／`shift_minus1`／`shift_plus1`，分母皆為
    **組內**列數，非全體），另加 `n`／`n_positive`／`timeout_rate`／
    `auc`（組內正例數 `< min_positive_for_auc` 時為 `None`，不報一個
    統計上無意義的數字）。

    **`shift` 的基準是組內、不是全段**（2026-09-15 GREEN 訂正落地）：
    `compute_gating_metrics(p0_grp, y_grp, theta)` 傳入的 `y_true`
    參數本來就是**該組自己的** `y_grp`，函式內部計算的
    `overall_minus1_rate`／`overall_plus1_rate` 因此天然是組內全體
    比例，不是全段——這個語意由呼叫方式決定，不是額外邏輯；先前版本
    只是組裝結果字典時把這四個鍵漏掉，不是語意本身有問題。

    `volatility` 含 `NaN` 時拋 `GatingContractError`——契約違反，不得
    用 `nanquantile` 靜默略過。
    """
    volatility = np.asarray(volatility, dtype=float)
    p0 = np.asarray(p0, dtype=float)
    y_true = np.asarray(y_true)
    if np.isnan(volatility).any():
        raise GatingContractError("volatility 含 NaN，拒絕靜默以 nanquantile 處理")

    q1, q2 = np.quantile(volatility, [1 / 3, 2 / 3])
    labels = np.where(volatility <= q1, "low", np.where(volatility <= q2, "mid", "high"))

    results: List[Dict[str, Any]] = []
    for label, lower, upper in [("low", None, q1), ("mid", q1, q2), ("high", q2, None)]:
        mask = labels == label
        n = int(mask.sum())
        y_grp = y_true[mask]
        p0_grp = p0[mask]
        n_positive = int((y_grp == 0).sum())
        timeout_rate = float(n_positive / n) if n > 0 else None

        if n_positive >= min_positive_for_auc:
            y_bin = (y_grp == 0).astype(int)
            ranks = pd.Series(p0_grp).rank().values
            n_pos = int(y_bin.sum())
            n_neg = len(y_bin) - n_pos
            auc = (
                float((ranks[y_bin == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))
                if n_neg > 0 else None
            )
        else:
            auc = None

        if n > 0:
            metrics = compute_gating_metrics(p0_grp, y_grp, theta)
        else:
            metrics = {
                "precision": None, "coverage": None, "recall": None,
                "retained_minus1_rate": None, "retained_plus1_rate": None,
                "shift_minus1": None, "shift_plus1": None,
            }

        results.append({
            "label": label,
            "cutpoint_lower": lower,
            "cutpoint_upper": upper,
            "n": n,
            "n_positive": n_positive,
            "timeout_rate": timeout_rate,
            "auc": auc,
            "coverage": metrics["coverage"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "retained_minus1_rate": metrics["retained_minus1_rate"],
            "retained_plus1_rate": metrics["retained_plus1_rate"],
            "shift_minus1": metrics["shift_minus1"],
            "shift_plus1": metrics["shift_plus1"],
        })
    return results


def assert_calibrator_matches_sb5(
    quality_dict: Dict[str, float],
    sb5_reference_dict: Dict[str, float],
    *,
    tol: float = 1e-9,
) -> None:
    """比對 `sb5_reference_dict` 內**全部鍵**（不寫死鍵名）與重建的
    `quality_dict` 對應欄位——任一欄不符即拋 `GatingCalibratorMismatchError`，
    證明「同一個校準器」（比照 `ug_g3_sb5_calibration_report.py`
    `assert_matches_sb4_report()` 的精神）。`quality_dict` 若含
    `sb5_reference_dict` 沒有的額外鍵，不影響比對結果（只比對
    reference 有的鍵；2026-09-15 GREEN 訂正——原設計寫死
    `("auc_calib_fit_raw", "platt_slope", "brier_after")` 三個鍵名，
    但真實 `UG-G3-SB5` TB 證據 JSON 裡 `auc_calib_fit_raw` 是
    `{class: float}` 的巢狀字典（三類 OvR），不是單一浮點數，直接
    比較在真實資料上會撞到 `TypeError`；正確的比對對象是
    `per_class_quality["0"]` 底下逐類別、已是單一浮點數的
    `auc_before`／`auc_after`／`platt_slope`／`platt_intercept`，加
    模型層級 `brier_after`，由呼叫端的 `extract_sb5_reference()`
    負責從真實巢狀結構抽出，本函式不需要知道鍵名清單）。"""
    for key in sb5_reference_dict:
        if abs(quality_dict[key] - sb5_reference_dict[key]) > tol:
            raise GatingCalibratorMismatchError(
                f"{key} 不符：重建={quality_dict[key]!r}，"
                f"UG-G3-SB5 證據={sb5_reference_dict[key]!r}"
            )
