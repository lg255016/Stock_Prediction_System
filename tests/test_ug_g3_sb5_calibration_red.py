# -*- coding: utf-8 -*-
"""UG-G3-SB5 紅測（RED）——`src/ml/calibration.py` 尚不存在，全部測試預期
`ImportError`／`ModuleNotFoundError`。

比照 `UG-G3-SB4` 先例：全部測試使用合成資料（`numpy`／`pandas` 手造），
不讀取任何真實 OOF parquet、不 import 任何真實面板路徑常數（`CLAUDE.md`
§13.4 測試封閉性；凍結面板只在之後的
`scripts/verify/ug_g3_sb5_calibration_report.py` 腳本層讀取）。

Gate A 提案訂正記錄（2026-09-15，紅測階段審查方發現，見
`doc/upgrade/gates/UG_G3_SB5_GATE_A_PROPOSAL.md` §4.5／§4.6／§6 訂正段）：
原設計「校準前後 AUC 須相等」對 Platt 成立、對 Isotonic 不成立——Isotonic
是階梯函數，會把大量不同的原始分數壓成同一輸出值（ties），AUC 對 ties
敏感，前後出現非零差值是方法本身的性質，不是實作缺陷。本檔的
`CalibrationRankingViolationTests` 依此分流：Platt 走「AUC 相等」判準，
Isotonic 走「配對序不反轉」判準，AUC 差值只計算揭露。
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd


# ==============================================================================
# 共用合成資料建構工具（純數值，不依賴任何真實面板）
# ==============================================================================

def _make_separable_binary_scores(n=600, seed=0):
    """建構一批與真實標籤有真實關聯（可分性良好）的合成二分類分數，
    供正面對照（校準器應保留排序訊號）使用。"""
    rng = np.random.RandomState(seed)
    raw_scores = rng.normal(size=n)
    prob = 1.0 / (1.0 + np.exp(-1.5 * raw_scores))
    y_true = (rng.rand(n) < prob).astype(int)
    return raw_scores, y_true


def _make_tb_scores(n=600, seed=1):
    """建構 TB（三分類 {-1,0,1}）合成資料：三欄各自的 decision_function
    分數（任意實數，非 [0,1]），與對應的真實標籤。"""
    rng = np.random.RandomState(seed)
    score_m1 = rng.normal(loc=-0.5, scale=2.0, size=n)
    score_0 = rng.normal(loc=0.0, scale=2.0, size=n)
    score_p1 = rng.normal(loc=0.5, scale=2.0, size=n)
    scores = np.column_stack([score_m1, score_0, score_p1])
    y_true = np.array([-1, 0, 1])[np.argmax(scores + rng.normal(scale=1.0, size=scores.shape), axis=1)]
    return scores, y_true


def _make_fold_frame(fold_ids, n_per_fold=20, seed=2):
    """建構帶 `fold_id` 欄的合成 DataFrame，`raw_score`／`y` 皆為合理範圍
    的合成值。"""
    rng = np.random.RandomState(seed)
    rows = []
    for fold in fold_ids:
        for _ in range(n_per_fold):
            rows.append({
                "fold_id": fold,
                "raw_score": rng.normal(),
                "y": int(rng.rand() < 0.5),
            })
    return pd.DataFrame(rows)


# ==============================================================================
# Group A: CalibrationDataIsolationTests（§6 列 1、列 3）
# ==============================================================================

class CalibrationDataIsolationTests(unittest.TestCase):
    def test_fit_rejects_rows_outside_calib_fit_folds(self):
        from src.ml.calibration import fit_calibrator, CalibrationFoldIsolationError
        df = _make_fold_frame([26, 27, 28, 30])  # 26=Meta-Train, 30=CALIB_EVAL_FOLDS
        with self.assertRaises(CalibrationFoldIsolationError):
            fit_calibrator(
                df["raw_score"].to_numpy(), df["y"].to_numpy(),
                fold_id=df["fold_id"].to_numpy(),
                method="sigmoid", target_column="target_up_down",
            )

    def test_fit_accepts_rows_strictly_within_calib_fit_folds(self):
        from src.ml.calibration import fit_calibrator
        df = _make_fold_frame([27, 28, 29], n_per_fold=40)
        calibrator = fit_calibrator(
            df["raw_score"].to_numpy(), df["y"].to_numpy(),
            fold_id=df["fold_id"].to_numpy(),
            method="sigmoid", target_column="target_up_down",
        )
        self.assertIsNotNone(calibrator)

    def test_calib_fit_and_eval_folds_are_disjoint(self):
        from src.ml.calibration import (
            CALIB_FIT_FOLDS, CALIB_EVAL_FOLDS,
            assert_fold_sets_disjoint, CalibrationFoldIsolationError,
        )
        # 正面對照：真實常數必須通過
        assert_fold_sets_disjoint(CALIB_FIT_FOLDS, CALIB_EVAL_FOLDS)
        # known-FAIL：刻意重疊的合成折集合必拋
        with self.assertRaises(CalibrationFoldIsolationError):
            assert_fold_sets_disjoint((27, 28, 29), (29, 30, 31))


# ==============================================================================
# Group B: CalibrationNotInTrainTests（§6 列 2，PO 2026-09-15 定案版本）
# ==============================================================================

class CalibrationNotInTrainTests(unittest.TestCase):
    def test_evaluate_rejects_rows_outside_calib_eval_folds(self):
        from src.ml.calibration import evaluate_calibration_quality, CalibrationFoldIsolationError, fit_calibrator
        fit_df = _make_fold_frame([27, 28, 29], n_per_fold=40)
        calibrator = fit_calibrator(
            fit_df["raw_score"].to_numpy(), fit_df["y"].to_numpy(),
            fold_id=fit_df["fold_id"].to_numpy(),
            method="sigmoid", target_column="target_up_down",
        )
        bad_eval_df = _make_fold_frame([15, 27])  # 15=Meta-Train, 27=CALIB_FIT_FOLDS
        with self.assertRaises(CalibrationFoldIsolationError):
            evaluate_calibration_quality(
                calibrator, bad_eval_df["raw_score"].to_numpy(), bad_eval_df["y"].to_numpy(),
                fold_id=bad_eval_df["fold_id"].to_numpy(), method="sigmoid",
            )

    def test_evaluate_accepts_rows_strictly_within_calib_eval_folds(self):
        from src.ml.calibration import evaluate_calibration_quality, fit_calibrator
        fit_df = _make_fold_frame([27, 28, 29], n_per_fold=40)
        calibrator = fit_calibrator(
            fit_df["raw_score"].to_numpy(), fit_df["y"].to_numpy(),
            fold_id=fit_df["fold_id"].to_numpy(),
            method="sigmoid", target_column="target_up_down",
        )
        eval_df = _make_fold_frame([30, 31, 32], n_per_fold=40)
        result = evaluate_calibration_quality(
            calibrator, eval_df["raw_score"].to_numpy(), eval_df["y"].to_numpy(),
            fold_id=eval_df["fold_id"].to_numpy(), method="sigmoid",
        )
        self.assertIsNotNone(result)

    def test_fit_and_evaluate_require_fold_id(self):
        from src.ml.calibration import fit_calibrator, evaluate_calibration_quality
        df = _make_fold_frame([27, 28, 29], n_per_fold=10)
        with self.assertRaises(TypeError):
            fit_calibrator(df["raw_score"].to_numpy(), df["y"].to_numpy(),
                            method="sigmoid", target_column="target_up_down")
        with self.assertRaises(TypeError):
            evaluate_calibration_quality(None, df["raw_score"].to_numpy(), df["y"].to_numpy(),
                                          method="sigmoid")


# ==============================================================================
# Group C: CalibrationMonotonicityTests（§6 列 4）
# ==============================================================================

class CalibrationMonotonicityTests(unittest.TestCase):
    def test_real_calibrator_is_monotonic(self):
        from src.ml.calibration import fit_calibrator, assert_calibration_monotonic
        raw_scores, y_true = _make_separable_binary_scores(n=400)
        fold_id = np.array([27] * 400)
        calibrator = fit_calibrator(raw_scores, y_true, fold_id=fold_id,
                                     method="isotonic", target_column="target_up_down")
        calibrated = calibrator.predict(raw_scores) if hasattr(calibrator, "predict") else calibrator(raw_scores)
        assert_calibration_monotonic(raw_scores, calibrated, method="isotonic")

    def test_broken_calibrator_raises(self):
        from src.ml.calibration import assert_calibration_monotonic, CalibrationMonotonicityError
        raw_scores = np.sort(np.random.RandomState(3).normal(size=200))
        calibrated = np.linspace(0.1, 0.9, 200)
        # 刻意在中段打亂：把第 100 個值設得比第 50 個還低
        calibrated[100] = calibrated[50] - 0.05
        with self.assertRaises(CalibrationMonotonicityError):
            assert_calibration_monotonic(raw_scores, calibrated, method="isotonic")


# ==============================================================================
# Group D: CalibrationRankingViolationTests（§6 列 5，Platt／Isotonic 分流，
# 訂正版）
# ==============================================================================

class CalibrationRankingViolationTests(unittest.TestCase):
    def test_platt_preserves_auc(self):
        from src.ml.calibration import fit_calibrator, evaluate_calibration_quality
        from sklearn.metrics import roc_auc_score
        raw_scores, y_true = _make_separable_binary_scores(n=600, seed=10)
        fold_id_fit = np.array([27] * 600)
        calibrator = fit_calibrator(raw_scores, y_true, fold_id=fold_id_fit,
                                     method="sigmoid", target_column="target_up_down")
        result = evaluate_calibration_quality(
            calibrator, raw_scores, y_true, fold_id=np.array([30] * 600), method="sigmoid")
        self.assertAlmostEqual(result["auc_before"], result["auc_after"], places=9)

    def test_platt_broken_calibrator_changes_auc_raises(self):
        from src.ml.calibration import assert_auc_preserved, CalibrationRankingViolationError
        raw_scores, y_true = _make_separable_binary_scores(n=300, seed=11)
        # 假校準器：把最高分與最低分的校準輸出對調——既非保留也非鏡射
        # （局部兩點對調，AUC 只有微小變化，離「保留」與「1-AUC 鏡射」
        # 兩者都差很遠），訂正後的「保留或鏡射」判準仍應攔下這個案例。
        order = np.argsort(raw_scores)
        calibrated = raw_scores.copy()
        calibrated[order[0]], calibrated[order[-1]] = calibrated[order[-1]], calibrated[order[0]]
        with self.assertRaises(CalibrationRankingViolationError):
            assert_auc_preserved(raw_scores, calibrated, y_true, method="sigmoid")

    def test_negative_slope_mirror_does_not_raise(self):
        """訂正（PO 2026-09-15，真實資料發現）：`Calib-fit` 擬合出負斜率
        是合法結果（底層訊號趨近零時，斜率正負號本身是雜訊），不是排序
        被破壞——負斜率的 sigmoid 精確把排序鏡射（`auc_after=1-auc_before`），
        不應拋出。用強負相關（斜率=-3）構造，確保擬合出的斜率穩定為負
        （不像真實資料的近零訊號那樣正負號隨機），測試才不會 flaky。"""
        from src.ml.calibration import fit_calibrator, evaluate_calibration_quality
        rng = np.random.RandomState(80)
        n = 1000
        raw_fit = rng.normal(size=n)
        logit_fit = -3.0 * raw_fit  # 分數越高，y=1 機率越低（負相關）
        p_fit = 1.0 / (1.0 + np.exp(-logit_fit))
        y_fit = (rng.rand(n) < p_fit).astype(int)

        raw_eval = rng.normal(size=n)
        logit_eval = -3.0 * raw_eval
        p_eval = 1.0 / (1.0 + np.exp(-logit_eval))
        y_eval = (rng.rand(n) < p_eval).astype(int)

        calibrator = fit_calibrator(raw_fit, y_fit, fold_id=np.array([27] * n),
                                     method="sigmoid", target_column="target_up_down")
        self.assertLess(calibrator._model.coef_[0][0], 0, "本測試前提：擬合出的斜率必須是負的")

        result = evaluate_calibration_quality(
            calibrator, raw_eval, y_eval, fold_id=np.array([30] * n), method="sigmoid")
        self.assertLess(result["platt_slope"], 0)
        self.assertAlmostEqual(result["auc_after"], 1.0 - result["auc_before"], places=9)

    def test_isotonic_auc_difference_is_disclosed_not_enforced(self):
        """訂正版正面對照：Isotonic 產生的 AUC 差值不觸發例外，只回傳供揭露。"""
        from src.ml.calibration import fit_calibrator, evaluate_calibration_quality
        raw_scores, y_true = _make_separable_binary_scores(n=600, seed=12)
        calibrator = fit_calibrator(raw_scores, y_true, fold_id=np.array([27] * 600),
                                     method="isotonic", target_column="target_up_down")
        result = evaluate_calibration_quality(
            calibrator, raw_scores, y_true, fold_id=np.array([30] * 600), method="isotonic")
        self.assertIn("auc_before", result)
        self.assertIn("auc_after", result)
        self.assertIn("n_unique_calibrated_values", result)
        # 不要求相等——這正是訂正的重點：Isotonic 允許 AUC 有差值
        self.assertLess(result["n_unique_calibrated_values"], 600)

    def test_isotonic_preserves_pairwise_order(self):
        from src.ml.calibration import fit_calibrator, assert_calibration_monotonic
        raw_scores, y_true = _make_separable_binary_scores(n=600, seed=13)
        calibrator = fit_calibrator(raw_scores, y_true, fold_id=np.array([27] * 600),
                                     method="isotonic", target_column="target_up_down")
        calibrated = calibrator.predict(raw_scores) if hasattr(calibrator, "predict") else calibrator(raw_scores)
        # 允許相等（ties），只禁止反轉——assert_calibration_monotonic 不拋即為通過
        assert_calibration_monotonic(raw_scores, calibrated, method="isotonic")

    def test_isotonic_reversed_pair_raises(self):
        """訂正（GREEN 階段，PO 2026-09-15 設計提醒）：對純量分數而言
        「非遞減」與「無配對反轉」是同一件事，`assert_calibration_monotonic()`
        不分 Platt／Isotonic、不接受 `strict_ranking` 旗標，一律拋
        `CalibrationMonotonicityError`；`CalibrationRankingViolationError`
        專屬 Platt 的 AUC 相等判準。本測試的期望例外與呼叫方式為本輪
        GREEN 實作唯一調整的斷言，其餘 29 項斷言維持紅測 commit
        （`22f685e`）原樣。"""
        from src.ml.calibration import assert_calibration_monotonic, CalibrationMonotonicityError
        raw_scores = np.array([0.1, 0.5, 0.9, 1.3])
        calibrated = np.array([0.2, 0.6, 0.4, 0.8])  # 0.9→0.4 反轉 0.5→0.6
        with self.assertRaises(CalibrationMonotonicityError):
            assert_calibration_monotonic(raw_scores, calibrated, method="isotonic")


# ==============================================================================
# Group E: CalibrationMethodRestrictionTests（§6 列 6）
# ==============================================================================

class CalibrationMethodRestrictionTests(unittest.TestCase):
    def test_up_down_isotonic_allowed(self):
        from src.ml.calibration import fit_calibrator
        raw_scores, y_true = _make_separable_binary_scores(n=200, seed=20)
        calibrator = fit_calibrator(raw_scores, y_true, fold_id=np.array([27] * 200),
                                     method="isotonic", target_column="target_up_down")
        self.assertIsNotNone(calibrator)

    def test_tb_isotonic_rejected(self):
        from src.ml.calibration import fit_calibrator, CalibrationMethodError
        scores, y_true = _make_tb_scores(n=200, seed=21)
        with self.assertRaises(CalibrationMethodError):
            fit_calibrator(scores[:, 2], (y_true == 1).astype(int), fold_id=np.array([27] * 200),
                            method="isotonic", target_column="target_triple_barrier")

    def test_tb_sigmoid_allowed(self):
        """訂正（GREEN 階段，PM 自我發現的紅測參數錯誤）：TB 的 `sigmoid`
        不像 `isotonic` 那樣在方法檢查階段就短路拒絕，會實際往下處理
        `raw_scores` 的形狀——原斷言誤傳單欄一維分數（`scores[:, 2]`）
        搭配已二值化的 `y_true`，但 `fit_calibrator()` 對
        `target_column="target_triple_barrier"` 一律預期完整
        `(n, 3)` 分數矩陣與原始 `{-1,0,1}` 標籤（比照
        `CalibrationNormalizationTests`／`TBCalibratorStructureTests`
        既有用法），已訂正為傳入完整矩陣。"""
        from src.ml.calibration import fit_calibrator
        scores, y_true = _make_tb_scores(n=200, seed=22)
        calibrators = fit_calibrator(scores, y_true, fold_id=np.array([27] * 200),
                                      method="sigmoid", target_column="target_triple_barrier")
        self.assertIsNotNone(calibrators)
        self.assertEqual(list(calibrators.keys()), [-1, 0, 1])


# ==============================================================================
# Group F: CalibrationNormalizationTests（§6 列 7）
# ==============================================================================

class CalibrationNormalizationTests(unittest.TestCase):
    def test_normalized_probabilities_sum_to_one(self):
        from src.ml.calibration import fit_calibrator, apply_calibrator
        scores, y_true = _make_tb_scores(n=400, seed=30)
        fold_id = np.array([27] * 400)
        calibrators = fit_calibrator(scores, y_true, fold_id=fold_id,
                                      method="sigmoid", target_column="target_triple_barrier")
        calibrated = apply_calibrator(calibrators, scores)
        row_sums = calibrated.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-9)

    def test_all_near_zero_ovr_raises(self):
        from src.ml.calibration import _normalize_ovr_probabilities, CalibrationNormalizationError
        ovr = np.array([[1e-13, 1e-13, 1e-13], [0.3, 0.3, 0.4]])
        with self.assertRaises(CalibrationNormalizationError):
            _normalize_ovr_probabilities(ovr)


# ==============================================================================
# Group G: IsotonicOutOfBoundsTests（PO 補件 1）
# ==============================================================================

class IsotonicOutOfBoundsTests(unittest.TestCase):
    def test_isotonic_clip_returns_finite_value_beyond_training_range(self):
        from src.ml.calibration import fit_calibrator
        raw_scores, y_true = _make_separable_binary_scores(n=300, seed=40)
        calibrator = fit_calibrator(raw_scores, y_true, fold_id=np.array([27] * 300),
                                     method="isotonic", target_column="target_up_down")
        far_beyond = np.array([raw_scores.max() + 50.0, raw_scores.min() - 50.0])
        predicted = calibrator.predict(far_beyond)
        self.assertTrue(np.all(np.isfinite(predicted)))
        self.assertTrue(np.all((predicted >= 0.0) & (predicted <= 1.0)))

    def test_isotonic_without_clip_would_produce_nan(self):
        """known-FAIL 示範（非本模組程式碼——直接示範 sklearn 預設行為，
        佐證 §4.2 選用 out_of_bounds='clip' 不是多餘的防禦）。"""
        from sklearn.isotonic import IsotonicRegression
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        y = np.array([0, 0, 1, 1, 1])
        iso_default = IsotonicRegression()  # 未指定 out_of_bounds
        iso_default.fit(x, y)
        predicted = iso_default.predict([100.0])
        self.assertTrue(np.isnan(predicted[0]))


# ==============================================================================
# Group H: CalibrationConstantsPinnedTests（PO 補件 2）
# ==============================================================================

class CalibrationConstantsPinnedTests(unittest.TestCase):
    def test_fold_constants_pinned(self):
        from src.ml.calibration import CALIB_FIT_FOLDS, CALIB_EVAL_FOLDS
        self.assertEqual(tuple(CALIB_FIT_FOLDS), (27, 28, 29))
        self.assertEqual(tuple(CALIB_EVAL_FOLDS), (30, 31, 32))
        # 折序須早於 Holdout 起始折（DEC-040：折 33-42 為 Holdout）
        self.assertLess(max(CALIB_EVAL_FOLDS), 33)

    def test_method_and_threshold_constants_pinned(self):
        from src.ml.calibration import (
            MIN_MINORITY_SAMPLES_FOR_ISOTONIC, CALIBRATION_METHOD_BY_TARGET, RELIABILITY_N_BINS,
        )
        self.assertEqual(MIN_MINORITY_SAMPLES_FOR_ISOTONIC, 500)
        self.assertEqual(
            CALIBRATION_METHOD_BY_TARGET["target_up_down"], ["isotonic", "sigmoid"])
        self.assertEqual(
            CALIBRATION_METHOD_BY_TARGET["target_triple_barrier"], ["sigmoid"])
        self.assertEqual(RELIABILITY_N_BINS, 10)


# ==============================================================================
# Group I: BrierScoreTests（PO 補件 3，指標函式進模組）
# ==============================================================================

class BrierScoreTests(unittest.TestCase):
    def test_perfect_prediction_is_zero(self):
        from src.ml.calibration import brier_score_multiclass
        y_true = np.array([-1, 0, 1, -1])
        calibrated = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
        ])
        score = brier_score_multiclass(y_true, calibrated, class_order=(-1, 0, 1))
        self.assertAlmostEqual(score, 0.0, places=9)

    def test_completely_wrong_prediction_is_two(self):
        from src.ml.calibration import brier_score_multiclass
        y_true = np.array([-1])
        calibrated = np.array([[0.0, 0.0, 1.0]])  # 真實是 -1，機率全押在 +1
        score = brier_score_multiclass(y_true, calibrated, class_order=(-1, 0, 1))
        self.assertAlmostEqual(score, 2.0, places=9)

    def test_binary_degenerates_to_standard_formula(self):
        """訂正（GREEN 階段，PM 自我發現的紅測斷言錯誤）：逐一 one-hot
        加總的多類別 Brier 定義，對二分類展開後是單一機率標準公式的
        **2 倍**（`p0=1-p1`、`o0=1-o1` 時 `(p0-o0)^2=(p1-o1)^2`，兩項
        相加即 `2*(p1-y)^2`），不是代數相等——容器內獨立驗證
        `multiclass=0.150`／`standard=0.075`、比值恰為 2（`VERIFIED
        THIS SESSION`）。原斷言 `multiclass_score == standard_score`
        對任何非退化輸入必定失敗，是紅測 commit 本身寫錯的斷言，非
        審查方或 PO 指出，GREEN 階段自行發現並訂正。"""
        from src.ml.calibration import brier_score_multiclass
        y_true = np.array([0, 1, 1, 0])
        p1 = np.array([0.3, 0.8, 0.6, 0.1])
        calibrated = np.column_stack([1 - p1, p1])
        multiclass_score = brier_score_multiclass(y_true, calibrated, class_order=(0, 1))
        standard_score = np.mean((p1 - y_true) ** 2)
        self.assertAlmostEqual(multiclass_score, 2 * standard_score, places=9)


# ==============================================================================
# Group J: ReliabilityTableTests（PO 補件 3）
# ==============================================================================

class ReliabilityTableTests(unittest.TestCase):
    def test_bin_count_matches_constant(self):
        from src.ml.calibration import reliability_table, RELIABILITY_N_BINS
        raw_scores, y_true = _make_separable_binary_scores(n=500, seed=50)
        table = reliability_table(raw_scores, y_true)
        self.assertEqual(len(table["bin_counts"]), RELIABILITY_N_BINS)

    def test_bin_counts_sum_to_n_rows(self):
        from src.ml.calibration import reliability_table
        raw_scores, y_true = _make_separable_binary_scores(n=777, seed=51)
        table = reliability_table(raw_scores, y_true)
        self.assertEqual(sum(table["bin_counts"]), 777)


# ==============================================================================
# Group K: TBCalibratorStructureTests（PO 補件 4）
# ==============================================================================

class TBCalibratorStructureTests(unittest.TestCase):
    def test_returns_three_per_class_calibrators_in_domain_order(self):
        from src.ml.calibration import fit_calibrator
        scores, y_true = _make_tb_scores(n=400, seed=60)
        calibrators = fit_calibrator(scores, y_true, fold_id=np.array([27] * 400),
                                      method="sigmoid", target_column="target_triple_barrier")
        self.assertEqual(list(calibrators.keys()), [-1, 0, 1])

    def test_apply_calibrator_output_shape(self):
        from src.ml.calibration import fit_calibrator, apply_calibrator
        scores, y_true = _make_tb_scores(n=400, seed=61)
        calibrators = fit_calibrator(scores, y_true, fold_id=np.array([27] * 400),
                                      method="sigmoid", target_column="target_triple_barrier")
        eval_scores, _ = _make_tb_scores(n=150, seed=62)
        calibrated = apply_calibrator(calibrators, eval_scores)
        self.assertEqual(calibrated.shape, (150, 3))

    def test_evaluate_calibration_quality_returns_per_class_dict(self):
        """自我發現（GREEN 補件，非 PO/審查方指出）：`roc_auc_score()`
        對未正規化的多欄 `decision_function` 分數直接呼叫在數學上不
        成立——`evaluate_calibration_quality()` 對多類別（TB）逐類別
        One-vs-Rest 各自獨立評估，回傳 `{類別: 結果字典}`，鍵序與
        `TARGET_CLASS_DOMAINS["target_triple_barrier"]` 一致。"""
        from src.ml.calibration import fit_calibrator, evaluate_calibration_quality
        fit_scores, fit_y = _make_tb_scores(n=400, seed=63)
        calibrators = fit_calibrator(fit_scores, fit_y, fold_id=np.array([27] * 400),
                                      method="sigmoid", target_column="target_triple_barrier")
        eval_scores, eval_y = _make_tb_scores(n=150, seed=64)
        result = evaluate_calibration_quality(
            calibrators, eval_scores, eval_y, fold_id=np.array([30] * 150), method="sigmoid")
        self.assertEqual(list(result.keys()), [-1, 0, 1])
        for cls in (-1, 0, 1):
            self.assertIn("auc_before", result[cls])
            self.assertIn("auc_after", result[cls])
            self.assertIn("platt_slope", result[cls])

    def test_accepts_arbitrary_real_scores_not_clipped_to_unit_interval(self):
        """known-FAIL 對照：若實作內部誤把輸入 clip 到 [0,1]（誤把
        decision_function 分數當成已經是機率），Platt 擬合結果會與
        不 clip 的版本不同——用此差異偵測該類突變。"""
        from src.ml.calibration import fit_calibrator
        rng = np.random.RandomState(63)
        raw_scores = rng.normal(loc=0.0, scale=5.0, size=300)  # 遠超 [0,1] 範圍
        y_true = (rng.rand(300) < 1 / (1 + np.exp(-raw_scores / 3))).astype(int)
        fold_id = np.array([27] * 300)

        calibrator = fit_calibrator(raw_scores, y_true, fold_id=fold_id,
                                     method="sigmoid", target_column="target_up_down")
        clipped_scores = np.clip(raw_scores, 0.0, 1.0)
        calibrator_if_clipped = fit_calibrator(clipped_scores, y_true, fold_id=fold_id,
                                                method="sigmoid", target_column="target_up_down")
        pred_real = calibrator.predict(raw_scores[:5]) if hasattr(calibrator, "predict") else calibrator(raw_scores[:5])
        pred_if_clipped = (calibrator_if_clipped.predict(raw_scores[:5])
                            if hasattr(calibrator_if_clipped, "predict") else calibrator_if_clipped(raw_scores[:5]))
        self.assertFalse(np.allclose(pred_real, pred_if_clipped),
                          "輸入是否被誤 clip 到 [0,1] 必須造成可偵測的差異")


# ==============================================================================
# Group L: PlattUnregularizedFitTests（PO 2026-09-15 審查方發現，紅→綠）
# ==============================================================================

class PlattUnregularizedFitTests(unittest.TestCase):
    """Platt scaling 定義為對 `decision_function` 分數做**未正則化**的一維
    logistic 最大概似擬合。`LogisticRegression()` 預設 `C=1.0`（L2 懲罰）
    對小尺度分數（SB4 Meta-Learner 的 `decision_function` 正是此情況，
    up_down 的 `p1` 73% 落在 0.45～0.55，對應 logit 約 ±0.2）會嚴重壓扁
    擬合斜率，把校準機率拉向 0.5——那是正則化的副作用，不是校準。"""

    def test_platt_fit_recovers_true_slope_within_tolerance(self):
        """known-FAIL：`LogisticRegression()` 預設 `C=1.0` 對此合成資料
        （分數 std=0.05、真實 logit 斜率 40）必定失敗此斷言——PM 獨立
        重現審查方探針：C=1.0 擬合斜率 13.95、C=1e6 擬合 39.29（審查方
        原始數字 14.11／38.98，質性結論一致，`VERIFIED THIS SESSION`）。"""
        from src.ml.calibration import fit_calibrator
        rng = np.random.RandomState(70)
        n = 2000
        raw_scores = rng.normal(scale=0.05, size=n)
        true_slope = 40.0
        logit = true_slope * raw_scores
        p = 1.0 / (1.0 + np.exp(-logit))
        y_true = (rng.rand(n) < p).astype(int)

        calibrator = fit_calibrator(raw_scores, y_true, fold_id=np.array([27] * n),
                                     method="sigmoid", target_column="target_up_down")
        fitted_slope = calibrator._model.coef_[0][0]
        self.assertGreater(fitted_slope, true_slope * 0.85,
                            "擬合斜率被正則化壓扁——Platt 必須是未正則化擬合")
        self.assertLess(fitted_slope, true_slope * 1.15)

    def test_platt_c_constant_pinned(self):
        from src.ml.calibration import PLATT_C
        self.assertGreaterEqual(PLATT_C, 1e6)


if __name__ == "__main__":
    unittest.main()
