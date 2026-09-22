# -*- coding: utf-8 -*-
"""`UG-G3-SB5` 機率校準（Probability Calibration）。

對 `UG-G3-SB4` 已核准結案的 Meta-Learner（`LogisticRegression`／
`RidgeClassifier`）輸出的 `decision_function()` 原始分數做後驗校準，
不重新訓練 Meta-Learner 本身（見 Gate A 提案 §2.3「校準對象是哪個
Meta-Learner」的範圍界定）。

**手動實作 Isotonic／Platt，不用 `sklearn.calibration.CalibratedClassifierCV`**
——容器內 sklearn 1.9.0 已移除 `cv="prefit"`，且 `FrozenEstimator` 內部
行為不透明、難以構造 known-FAIL 案例（Gate A 提案 §4.2 訂正記錄）。

**校準資料集**：`CALIB_FIT_FOLDS`（折 27-29，Meta-Eval 前半）擬合校準器，
`CALIB_EVAL_FOLDS`（折 30-32，Meta-Eval 後半）評估校準品質，兩者不重疊、
皆不是 Meta-Learner 本身的訓練資料（Meta-Train，折 0-26），詳見 Gate A
提案 §4.1「Alternatives Considered」。

**AUC／排序保持判準依方法分流**（Gate A 提案 §4.5／§4.6／§6 訂正，
2026-09-15，紅測階段審查方發現）：Isotonic 是階梯函數，會把大量原始
分數壓成相同輸出值（ties），AUC 對 ties 敏感，校準前後出現非零差值是
方法本身的性質，不是實作缺陷。因此：

- Platt：AUC／PR-AUC 校準前後須「保留」或「鏡射」（`1-AUC`，對應
  `Calib-fit` 擬合出負斜率的合法情況，見 `assert_auc_preserved()`
  2026-09-15 訂正記錄）之一，兩者皆不成立才拋
  `CalibrationRankingViolationError`。
- Isotonic：不檢查 AUC 相等，AUC 差值只計算、只揭露
  （`evaluate_calibration_quality()` 回傳的 `auc_before`／`auc_after`）；
  排序保持改用配對序檢查（`assert_calibration_monotonic()`——對任意
  `raw_score_i < raw_score_j` 必須 `calibrated_i <= calibrated_j`，
  允許相等只禁反轉，違反拋 `CalibrationMonotonicityError`）。

  **PO 2026-09-15 設計提醒落地**：`assert_calibration_monotonic()` 不分
  Platt／Isotonic、不接受 `strict_ranking` 之類的旗標——對純量分數而言
  「非遞減」與「無配對反轉」本來就是同一件事，用旗標區分成兩種例外是
  多餘的。本函式一律拋 `CalibrationMonotonicityError`；
  `CalibrationRankingViolationError` 專屬 Platt 的 AUC 相等判準
  （`assert_auc_preserved()`），兩者職責不重疊。
"""
from __future__ import annotations

from typing import Any, Dict, List, Union

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from src.ml.stacking import TARGET_CLASS_DOMAINS


class CalibrationFoldIsolationError(RuntimeError):
    """`fit()`／`evaluate()` 收到落在允許折集合之外的 `fold_id`；或
    `CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS` 本身重疊。"""


class CalibrationMonotonicityError(RuntimeError):
    """校準機率（正規化前）違反配對序保持（`raw_i < raw_j` 卻
    `calibrated_i > calibrated_j`）。"""


class CalibrationRankingViolationError(RuntimeError):
    """Platt 校準前後 AUC／PR-AUC 不相等——只適用於 Platt，Isotonic 的
    排序保持走 `CalibrationMonotonicityError`（見模組 docstring）。"""


class CalibrationMethodError(RuntimeError):
    """`target_column` 與 `method` 的組合不在 `CALIBRATION_METHOD_BY_TARGET`
    宣告的允許清單內。"""


class CalibrationNormalizationError(RuntimeError):
    """多類別（TB）逐列 One-vs-Rest 校準機率正規化前，三者總和趨近 0
    （會導致除以 0 產生 `NaN`／`Inf`）。"""


#: Meta-Eval（折 27-32）依時間序切分，擬合折在前、評估折在後。
CALIB_FIT_FOLDS = (27, 28, 29)
CALIB_EVAL_FOLDS = (30, 31, 32)

#: Isotonic 需要每個類別至少這麼多樣本，否則階梯函數容易在小樣本下
#: 過擬合（Gate A 提案 §2.4：TB 的 Timeout 類別在 Calib-fit 僅 297 列，
#: 低於此門檻，結構性排除）。
MIN_MINORITY_SAMPLES_FOR_ISOTONIC = 500

#: Platt scaling 的定義是對 `decision_function` 分數做**未正則化**的
#: 一維 logistic 最大概似擬合。`LogisticRegression()` 預設 `C=1.0`
#: （L2 懲罰）對小尺度分數（`UG-G3-SB4` Meta-Learner 的 `decision_function`
#: 正是此情況）會嚴重壓扁擬合斜率、把校準機率拉向 0.5——那是正則化的
#: 副作用，不是校準（PO 2026-09-15 發現，PM 獨立重現：合成資料 C=1.0
#: 擬合斜率 13.95、C=1e6 擬合 39.29，真實斜率 40）。用大 `C` 值逼近
#: 未正則化擬合（sklearn 的 `LogisticRegression` 無 `penalty=None` 搭配
#: `lbfgs` 的穩定組合疑慮，改用極大 `C` 更直接）。
PLATT_C = 1e6

#: 逐 target 允許的校準方法——TB 結構性不含 `"isotonic"`（宣告層級常數，
#: 不是執行期動態判斷，見 Gate A 提案 §4.3）。
CALIBRATION_METHOD_BY_TARGET: Dict[str, List[str]] = {
    "target_up_down": ["isotonic", "sigmoid"],
    "target_triple_barrier": ["sigmoid"],
}

#: Reliability 分桶數（等寬，`[0,0.1) ... [0.9,1.0]`）。
RELIABILITY_N_BINS = 10


def assert_fold_sets_disjoint(fit_folds, eval_folds) -> None:
    """`CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS` 不得重疊——模組載入時對真實
    常數呼叫一次，測試可另外傳入合成折集合驗證此函式本身。"""
    overlap = set(fit_folds) & set(eval_folds)
    if overlap:
        raise CalibrationFoldIsolationError(
            f"CALIB_FIT_FOLDS 與 CALIB_EVAL_FOLDS 不得重疊，發現重疊折號: "
            f"{sorted(overlap)}"
        )


# 模組載入期即驗證真實常數本身沒有設計缺陷。
assert_fold_sets_disjoint(CALIB_FIT_FOLDS, CALIB_EVAL_FOLDS)


class _PlattCalibrator:
    """包一層 `LogisticRegression`（單一輸入特徵＝`decision_function`
    分數），讓 `.predict()` 回傳**校準後機率**（`predict_proba` 的正類欄），
    而不是 `LogisticRegression.predict()` 原生的硬分類標籤——避免呼叫端
    誤用。**Platt 為未正則化擬合**（`C=PLATT_C`，見該常數註解），不是
    `LogisticRegression()` 的預設 L2 正則化。"""

    def __init__(self, model: LogisticRegression):
        self._model = model

    def predict(self, raw_scores) -> np.ndarray:
        raw_scores = np.asarray(raw_scores, dtype=float).reshape(-1, 1)
        return self._model.predict_proba(raw_scores)[:, 1]


def _apply_single(calibrator, raw_scores: np.ndarray) -> np.ndarray:
    raw_scores = np.asarray(raw_scores, dtype=float)
    if hasattr(calibrator, "predict"):
        return np.asarray(calibrator.predict(raw_scores), dtype=float)
    return np.asarray(calibrator(raw_scores), dtype=float)


def _fit_single(raw_scores: np.ndarray, y_binary: np.ndarray, method: str):
    raw_scores = np.asarray(raw_scores, dtype=float)
    y_binary = np.asarray(y_binary)
    if method == "isotonic":
        model = IsotonicRegression(out_of_bounds="clip")
        model.fit(raw_scores, y_binary)
        return model
    if method == "sigmoid":
        lr = LogisticRegression(C=PLATT_C, max_iter=500)
        lr.fit(raw_scores.reshape(-1, 1), y_binary)
        return _PlattCalibrator(lr)
    raise CalibrationMethodError(f"未知的校準方法: {method!r}（只接受 'isotonic'／'sigmoid'）")


def fit_calibrator(
    raw_scores,
    y_true,
    *,
    fold_id,
    method: str,
    target_column: str,
) -> Union[Any, Dict[int, Any]]:
    """在 `CALIB_FIT_FOLDS` 範圍內擬合校準器。`fold_id` 為必填關鍵字參數
    （無預設值，省略即 `TypeError`）——這是 §6「校準器 `fit()` 收到列必須
    可核對折別」的介面層落地。

    - `target_column="target_up_down"`：`raw_scores`／`y_true` 皆一維，
      回傳單一校準器物件。
    - `target_column="target_triple_barrier"`：`raw_scores` 為
      `(n, 3)`（依 `TARGET_CLASS_DOMAINS["target_triple_barrier"]`
      順序：`-1, 0, 1`），`y_true` 為對應的原始類別值（非已二值化）；
      逐類別 One-vs-Rest 各自擬合，回傳 `{-1: 校準器, 0: 校準器,
      1: 校準器}`。

    Raises:
        CalibrationFoldIsolationError: `fold_id` 不是全部落在
            `CALIB_FIT_FOLDS` 內。
        CalibrationMethodError: `target_column` 未知，或 `method` 不在
            該 `target_column` 允許清單內（`CALIBRATION_METHOD_BY_TARGET`）
            ——此檢查在讀取 `raw_scores` 結構之前執行，故 TB 誤用
            `isotonic` 時即使 `raw_scores` 維度不合預期也會先拋出這個
            例外，不會先撞到形狀錯誤。
    """
    fold_id = np.asarray(fold_id)
    if not np.all(np.isin(fold_id, CALIB_FIT_FOLDS)):
        bad = sorted(set(fold_id.tolist()) - set(CALIB_FIT_FOLDS))
        raise CalibrationFoldIsolationError(
            f"fit_calibrator() 只接受 CALIB_FIT_FOLDS={CALIB_FIT_FOLDS} 內的折，"
            f"收到超出範圍的 fold_id: {bad}"
        )
    if target_column not in CALIBRATION_METHOD_BY_TARGET:
        raise CalibrationMethodError(f"未知的 target_column: {target_column!r}")
    if method not in CALIBRATION_METHOD_BY_TARGET[target_column]:
        raise CalibrationMethodError(
            f"target_column={target_column!r} 不允許 method={method!r}；"
            f"允許值：{CALIBRATION_METHOD_BY_TARGET[target_column]}"
        )

    if target_column == "target_triple_barrier":
        raw_scores = np.asarray(raw_scores, dtype=float)
        y_true = np.asarray(y_true)
        class_domain = TARGET_CLASS_DOMAINS[target_column]
        calibrators: Dict[int, Any] = {}
        for i, cls in enumerate(class_domain):
            y_binary = (y_true == cls).astype(int)
            calibrators[cls] = _fit_single(raw_scores[:, i], y_binary, method)
        return calibrators

    return _fit_single(np.asarray(raw_scores, dtype=float), np.asarray(y_true), method)


def _normalize_ovr_probabilities(ovr: np.ndarray) -> np.ndarray:
    """逐列正規化 One-vs-Rest 校準機率，使三欄和為 1。任一列三者總和
    趨近 0（< 1e-9）即拋出，不得讓除法產出 `NaN`／`Inf`。"""
    ovr = np.asarray(ovr, dtype=float)
    row_sums = ovr.sum(axis=1)
    if np.any(row_sums < 1e-9):
        bad_rows = np.where(row_sums < 1e-9)[0]
        raise CalibrationNormalizationError(
            f"{len(bad_rows)} 列的 One-vs-Rest 校準機率總和趨近 0（<1e-9），"
            "正規化前必須攔下，避免除以 0 產生 NaN/Inf"
        )
    return ovr / row_sums[:, None]


def apply_calibrator(calibrator, raw_scores) -> np.ndarray:
    """套用已擬合的校準器。`calibrator` 為 `fit_calibrator()` 的回傳值
    ——單一物件（二分類）或 `{類別: 校準器}` 字典（TB，多類別）。

    多類別時 `raw_scores` 須為 `(n, 3)`，依字典鍵順序（即
    `TARGET_CLASS_DOMAINS` 順序）逐欄套用，**正規化前**得到三欄
    Un-normalized 機率，再逐列正規化（`_normalize_ovr_probabilities`）
    回傳 `(n, 3)`。
    """
    if isinstance(calibrator, dict):
        raw_scores = np.asarray(raw_scores, dtype=float)
        cols = [
            _apply_single(cal, raw_scores[:, i])
            for i, cal in enumerate(calibrator.values())
        ]
        ovr = np.column_stack(cols)
        return _normalize_ovr_probabilities(ovr)
    return _apply_single(calibrator, raw_scores)


def assert_calibration_monotonic(raw_scores, calibrated_probs, method: str = None) -> None:
    """檢查**正規化前**的「單一類別 `raw_score` → 校準機率」配對，排序
    後須非遞減（允許相等，只禁止反轉）。`method` 參數保留供呼叫端記錄
    脈絡，不影響本函式的檢查邏輯本身——Platt／Isotonic 用同一套配對序
    判準（見模組 docstring「PO 2026-09-15 設計提醒落地」）。

    Raises:
        CalibrationMonotonicityError: 排序後任兩相鄰值出現下降。
    """
    raw_scores = np.asarray(raw_scores, dtype=float)
    calibrated_probs = np.asarray(calibrated_probs, dtype=float)
    order = np.argsort(raw_scores)
    sorted_calibrated = calibrated_probs[order]
    diffs = np.diff(sorted_calibrated)
    violation_idx = np.where(diffs < -1e-12)[0]
    if violation_idx.size > 0:
        i = int(violation_idx[0])
        raise CalibrationMonotonicityError(
            f"校準機率違反非遞減（排序後相鄰值下降）：索引 {i} 處 "
            f"{sorted_calibrated[i]:.6f} → {sorted_calibrated[i + 1]:.6f}"
        )


def assert_auc_preserved(raw_scores, calibrated_probs, y_true, method: str) -> Dict[str, float]:
    """Platt：校準前後 AUC 須符合「保留」（`auc_after≈auc_before`）或
    「鏡射」（`auc_after≈1-auc_before`，容差皆 1e-9）**其中之一**，兩者
    皆不成立才拋 `CalibrationRankingViolationError`。Isotonic：不檢查
    （見模組 docstring），僅計算並回傳供揭露。

    **訂正（PO 2026-09-15，真實資料發現）**：原設計只接受「保留」，
    但 Platt 是對 `decision_function` 分數做未正則化的一維 logistic
    擬合——當底層訊號趨近於零（`UG-G3-SB4`／`UG-G3-SB5` 已多次確認
    `target_up_down` 的 Meta-Learner 判別力極弱），`Calib-fit`（僅
    3 折）擬合出的斜率**正負號本身是雜訊**，擬合出負斜率是合法結果，
    不是排序被破壞。負斜率的 sigmoid 是單調**遞減**轉換，數學上精確把
    排序鏡射（`auc_after = 1 - auc_before`），不是弄亂——PM 獨立以純
    雜訊玩具案例驗證：正斜率時 `auc_before`／`auc_after` 逐位相同
    （`VERIFIED THIS SESSION`）。真正的排序被破壞（例如局部打亂、只
    對調一兩個點）**既不滿足保留也不滿足鏡射**，仍會被此檢查攔下——
    `test_platt_broken_calibrator_changes_auc_raises`（對調首尾兩點）
    保留不動，即為此案例的既有 known-FAIL。"""
    raw_scores = np.asarray(raw_scores, dtype=float)
    calibrated_probs = np.asarray(calibrated_probs, dtype=float)
    y_true = np.asarray(y_true)
    auc_before = float(roc_auc_score(y_true, raw_scores))
    auc_after = float(roc_auc_score(y_true, calibrated_probs))
    if method == "sigmoid":
        preserved = abs(auc_before - auc_after) <= 1e-9
        mirrored = abs(auc_after - (1.0 - auc_before)) <= 1e-9
        if not (preserved or mirrored):
            raise CalibrationRankingViolationError(
                f"Platt 校準前後 AUC 應相等或精確鏡射（1-AUC），實測 "
                f"{auc_before:.9f} → {auc_after:.9f}（1-before={1-auc_before:.9f}），"
                "兩者皆不成立，排序可能已被破壞"
            )
    return {"auc_before": auc_before, "auc_after": auc_after}


def _evaluate_single(calibrator, raw_scores: np.ndarray, y_true: np.ndarray, method: str) -> Dict[str, Any]:
    calibrated = _apply_single(calibrator, raw_scores)
    auc_result = assert_auc_preserved(raw_scores, calibrated, y_true, method)
    platt_slope = None
    platt_intercept = None
    if method == "sigmoid" and hasattr(calibrator, "_model"):
        platt_slope = float(calibrator._model.coef_[0][0])
        platt_intercept = float(calibrator._model.intercept_[0])
    return {
        "auc_before": auc_result["auc_before"],
        "auc_after": auc_result["auc_after"],
        "n_unique_calibrated_values": int(len(np.unique(calibrated))),
        "platt_slope": platt_slope,
        "platt_intercept": platt_intercept,
    }


def evaluate_calibration_quality(
    calibrator, raw_scores, y_true, *, fold_id, method: str
) -> Dict[str, Any]:
    """在 `CALIB_EVAL_FOLDS` 範圍內評估校準品質。`fold_id` 為必填關鍵字
    參數（無預設值，省略即 `TypeError`）。

    - 二分類（`calibrator` 為單一物件）：回傳單一結果字典，含
      `auc_before`／`auc_after`／`n_unique_calibrated_values`／
      `platt_slope`／`platt_intercept`（後兩者僅 `method="sigmoid"`
      有值）。
    - 多類別（`calibrator` 為 `{類別: 校準器}` 字典，TB）：**逐類別
      One-vs-Rest 各自獨立評估**（`VERIFIED THIS SESSION` 自我發現：
      `roc_auc_score()` 對未正規化的多欄 `decision_function` 分數直接
      呼叫在數學上不成立，AUC 保留／鏡射的判準本來就是針對**單一類別
      的原始分數**才有意義——正規化步驟會把多個類別的資訊混在一起，
      「保留」或「鏡射」這兩個性質在正規化後不再乾淨成立）。回傳
      `{類別: 單一結果字典}`，鍵序與 `calibrator` 一致（即
      `TARGET_CLASS_DOMAINS` 順序）。

    Raises:
        CalibrationFoldIsolationError: `fold_id` 不是全部落在
            `CALIB_EVAL_FOLDS` 內——涵蓋「校準器在 Meta-Train（模型本身
            訓練資料）上被評估」的循環驗證情境（Gate A 提案 §4.1
            方案 2 已否決的理由）。
        CalibrationRankingViolationError: 經 `assert_auc_preserved()`
            傳遞，Platt 校準前後 AUC 既非保留也非鏡射時拋出（多類別時
            任一類別觸發即拋出，中止整體評估）。
    """
    fold_id = np.asarray(fold_id)
    if not np.all(np.isin(fold_id, CALIB_EVAL_FOLDS)):
        bad = sorted(set(fold_id.tolist()) - set(CALIB_EVAL_FOLDS))
        raise CalibrationFoldIsolationError(
            f"evaluate_calibration_quality() 只接受 CALIB_EVAL_FOLDS={CALIB_EVAL_FOLDS} "
            f"內的折，收到超出範圍的 fold_id: {bad}"
        )

    if isinstance(calibrator, dict):
        raw_scores = np.asarray(raw_scores, dtype=float)
        y_true = np.asarray(y_true)
        results: Dict[int, Dict[str, Any]] = {}
        for i, (cls, cal) in enumerate(calibrator.items()):
            y_binary = (y_true == cls).astype(int)
            results[cls] = _evaluate_single(cal, raw_scores[:, i], y_binary, method)
        return results

    return _evaluate_single(calibrator, np.asarray(raw_scores, dtype=float), np.asarray(y_true), method)


def brier_score_multiclass(y_true, calibrated_probs, class_order) -> float:
    """逐列 `sum_c (p_c - onehot_c)^2`，再對全部列取平均（Gate A 提案
    §4.8）。**二分類不是此公式的代數等值特例，而是恰好 2 倍**——
    `sum_c (p_c-o_c)^2` 對兩個互補類別展開後等於 `2*(p_1-y)^2`
    （`p_0=1-p_1`、`o_0=1-o_1` 時 `(p_0-o_0)^2=(p_1-o_1)^2`），與單一
    機率的標準 Brier 公式 `(p_1-y)^2` 相差一個 2 倍常數，不是代數相等
    ——本函式一律採用完整 one-hot 加總的定義，不因二分類而省略這個
    倍數，呼叫端若要與單一機率公式比較須自行乘以（或除以）2。"""
    y_true = np.asarray(y_true)
    calibrated_probs = np.asarray(calibrated_probs, dtype=float)
    class_order = list(class_order)
    onehot = np.zeros_like(calibrated_probs)
    for i, cls in enumerate(class_order):
        onehot[:, i] = (y_true == cls).astype(float)
    return float(np.mean(np.sum((calibrated_probs - onehot) ** 2, axis=1)))


def reliability_table(raw_scores_or_probs, y_true, n_bins: int = RELIABILITY_N_BINS) -> Dict[str, Any]:
    """把輸入依 `[0, 1]` 等寬分成 `n_bins` 桶（超出範圍者截斷至邊界，
    純屬分桶用途，不是校準本身），回傳每桶列數（`bin_counts`）、平均
    預測值（`mean_predicted`）與實際發生頻率（`observed_frequency`）。"""
    values = np.clip(np.asarray(raw_scores_or_probs, dtype=float), 0.0, 1.0 - 1e-12)
    y_true = np.asarray(y_true, dtype=float)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(values, bin_edges[1:-1], right=False)

    bin_counts: List[int] = []
    mean_predicted: List[float] = []
    observed_frequency: List[float] = []
    for b in range(n_bins):
        mask = bin_indices == b
        count = int(mask.sum())
        bin_counts.append(count)
        if count > 0:
            mean_predicted.append(float(values[mask].mean()))
            observed_frequency.append(float(y_true[mask].mean()))
        else:
            mean_predicted.append(float("nan"))
            observed_frequency.append(float("nan"))

    return {
        "bin_counts": bin_counts,
        "mean_predicted": mean_predicted,
        "observed_frequency": observed_frequency,
    }
