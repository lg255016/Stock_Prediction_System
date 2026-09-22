# -*- coding: utf-8 -*-
"""UG-G3-SB6 紅測（RED）——`src/ml/gating.py` 與
`scripts/verify/ug_g3_sb6_gating_report.py` 尚不存在，全部測試預期
`ImportError`／`ModuleNotFoundError`。

依已核准 Gate A 提案（`doc/upgrade/gates/UG_G3_SB6_GATE_A_PROPOSAL.md`，
commit `83749de`）§5 全部 8 個場景設計，紅測清單經審查方兩輪複核
（v1→v2：三個結構缺口＋七處補強；v2→RED 授權：兩個夾具細節）。

比照 `UG-G3-SB4`／`UG-G3-SB5` 先例：全部測試使用合成資料（`numpy`／
`pandas` 手造），不讀取任何真實 OOF parquet（`CLAUDE.md` §13.4 測試封閉性；
`CalibratorMatchTests` 的參考數字為抄自已 commit 的
`UG_G3_SB5_calibration_report_target_triple_barrier.json` 的純數字常數，
非讀檔）。

`Class 6: FeasibleRegionTests::test_each_criterion_excludes_independently`
夾具依審查方要求：A／B／C 三個候選點的召回分別為 0.90／0.85／0.80，
互不相同且皆高於基準點 D 的 0.70，確保翻轉任一判準後該點必定以召回
勝出取代 D（若召回低於 D，即使該判準變可行也不會被選中，測不出
「該判準是否真的被檢查」）。
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd


# ==============================================================================
# 共用合成資料建構工具
# ==============================================================================

def _make_sb5_like_curve_rows():
    """依 UG-G3-SB5 Gate A §2.5 實測 LR 曲線形狀構造的合成 curve_rows
    （數值取自該表四捨五入，非即時查詢）。可行集（coverage>=0.80,
    lift>=4.0, recall>=0.60）應恰為 gate=15%／20% 兩點，其中 20% 召回較高。
    """
    return [
        {"theta": 0.293, "gate_pct": 0.01, "coverage": 0.99, "precision": 0.506, "lift": 10.7, "recall": 0.108},
        {"theta": 0.187, "gate_pct": 0.05, "coverage": 0.95, "precision": 0.383, "lift": 8.1, "recall": 0.406},
        {"theta": 0.121, "gate_pct": 0.10, "coverage": 0.90, "precision": 0.281, "lift": 6.0, "recall": 0.596},
        {"theta": 0.091, "gate_pct": 0.15, "coverage": 0.85, "precision": 0.222, "lift": 4.7, "recall": 0.707},
        {"theta": 0.069, "gate_pct": 0.20, "coverage": 0.80, "precision": 0.196, "lift": 4.2, "recall": 0.830},
        {"theta": 0.041, "gate_pct": 0.30, "coverage": 0.70, "precision": 0.143, "lift": 3.0, "recall": 0.910},
        {"theta": 0.015, "gate_pct": 0.50, "coverage": 0.50, "precision": 0.092, "lift": 2.0, "recall": 0.979},
    ]


def _make_regime_fixture(n_per_group=40, seed=0):
    rng = np.random.RandomState(seed)
    vol = np.concatenate([
        rng.uniform(0.0, 0.3, n_per_group),
        rng.uniform(0.3, 0.6, n_per_group),
        rng.uniform(0.6, 1.0, n_per_group),
    ])
    p0 = rng.uniform(0.0, 1.0, n_per_group * 3)
    y = rng.choice([-1, 0, 1], size=n_per_group * 3, p=[0.45, 0.10, 0.45])
    return vol, p0, y


def _make_p0_source_fixture(n=60, seed=3):
    rng = np.random.RandomState(seed)
    raw_scores = rng.normal(loc=0.0, scale=1.0, size=(n, 3))
    raw_scores = np.where(raw_scores == 0, 0.01, raw_scores)  # 確保三欄皆非零
    y = rng.choice([-1, 0, 1], size=n)
    fold_id = np.full(n, 27)  # 全在 CALIB_FIT_FOLDS
    return raw_scores, y, fold_id


# ==============================================================================
# 1. TargetColumnRejectionTests（§5 場景 1）
# ==============================================================================

class TargetColumnRejectionTests(unittest.TestCase):
    """對應紅測清單 #1-3。"""

    def test_up_down_raises_target_column_error(self):
        from src.ml.gating import _validate_target_column, GatingTargetColumnError
        with self.assertRaises(GatingTargetColumnError) as ctx:
            _validate_target_column("target_up_down")
        self.assertIsInstance(ctx.exception, ValueError)
        self.assertIn("RISK-030", str(ctx.exception))

    def test_triple_barrier_accepted(self):
        from src.ml.gating import _validate_target_column
        _validate_target_column("target_triple_barrier")  # 不拋即通過

    def test_unknown_target_column_also_rejected(self):
        from src.ml.gating import _validate_target_column, GatingTargetColumnError
        with self.assertRaises(GatingTargetColumnError):
            _validate_target_column("target_foo")


# ==============================================================================
# 2. HoldoutIsolationTests（§5 場景 2，§3.4 訂正 2）
# ==============================================================================

class HoldoutIsolationTests(unittest.TestCase):
    """對應紅測清單 #4-8。"""

    def test_fold_33_injection_raises(self):
        from src.ml.gating import assert_holdout_isolation, GatingHoldoutViolation
        fold_id = np.array([27, 28, 29, 30, 31, 32, 33])
        trade_date = pd.to_datetime(["2025-05-05"] * 6 + ["2025-10-24"])
        with self.assertRaises(GatingHoldoutViolation):
            assert_holdout_isolation(fold_id, trade_date)

    def test_clean_input_passes(self):
        from src.ml.gating import assert_holdout_isolation
        fold_id = np.array([27, 28, 29, 30, 31, 32])
        trade_date = pd.to_datetime(["2025-05-05"] * 6)
        assert_holdout_isolation(fold_id, trade_date)  # 不拋即通過

    def test_trade_date_violation_without_fold_violation_raises(self):
        from src.ml.gating import assert_holdout_isolation, GatingHoldoutViolation
        fold_id = np.array([27, 28, 29, 30, 31, 32])  # 全部 <=32
        trade_date = pd.to_datetime(["2025-05-05"] * 5 + ["2025-10-25"])  # 混入超界日期
        with self.assertRaises(GatingHoldoutViolation):
            assert_holdout_isolation(fold_id, trade_date)

    def test_fold_32_and_day_before_holdout_passes(self):
        from src.ml.gating import assert_holdout_isolation
        fold_id = np.array([32])
        trade_date = pd.to_datetime(["2025-10-22"])
        assert_holdout_isolation(fold_id, trade_date)  # 不拋即通過（上界正控制）

    def test_trade_date_equal_to_holdout_start_raises(self):
        from src.ml.gating import assert_holdout_isolation, GatingHoldoutViolation
        fold_id = np.array([32])
        trade_date = pd.to_datetime(["2025-10-23"])  # 恰等於 HOLDOUT_START_DATE
        with self.assertRaises(GatingHoldoutViolation):
            assert_holdout_isolation(fold_id, trade_date)


# ==============================================================================
# 3. GatingMetricsTests（§5 場景 3，§3.3／§3.5 訂正 5，缺口 1）
# ==============================================================================

class GatingMetricsTests(unittest.TestCase):
    """對應紅測清單 #9-13。"""

    def test_theta_above_max_p0_precision_is_none(self):
        from src.ml.gating import compute_gating_metrics
        p0 = np.array([0.1, 0.2, 0.3])
        y = np.array([0, 1, -1])
        result = compute_gating_metrics(p0, y, theta=0.99)
        self.assertIsNone(result["precision"])

    def test_empty_gated_coverage_and_recall_still_defined(self):
        from src.ml.gating import compute_gating_metrics
        p0 = np.array([0.1, 0.2, 0.3])
        y = np.array([0, 1, -1])
        result = compute_gating_metrics(p0, y, theta=0.99)
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["recall"], 0.0)

    def test_theta_at_minimum_gates_everything(self):
        from src.ml.gating import compute_gating_metrics
        p0 = np.array([0.1, 0.2, 0.3])
        y = np.array([0, 1, -1])
        result = compute_gating_metrics(p0, y, theta=0.0)
        self.assertEqual(result["coverage"], 0.0)
        self.assertAlmostEqual(result["precision"], 1 / 3)

    def test_metrics_on_mixed_fixture(self):
        """10 列手算夾具：3 個 Timeout（y=0）、7 個非 Timeout。θ=0.60 使
        4 列被 gate（2 Timeout／2 非 Timeout），含「被 gate 的非 Timeout」
        與「沒被 gate 的 Timeout」兩種負條件列。"""
        from src.ml.gating import compute_gating_metrics
        p0 = np.array([0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.05])
        y = np.array([0, 1, 0, -1, 1, -1, 1, 0, -1, 1])
        result = compute_gating_metrics(p0, y, theta=0.60)
        self.assertAlmostEqual(result["precision"], 0.5)
        self.assertAlmostEqual(result["coverage"], 0.6)
        self.assertAlmostEqual(result["recall"], 2 / 3)
        # retained（p0<0.60）：indices 4-9，y=[1,-1,1,0,-1,1] → -1 佔 2/6、+1 佔 3/6
        self.assertAlmostEqual(result["retained_minus1_rate"], 2 / 6)
        self.assertAlmostEqual(result["retained_plus1_rate"], 3 / 6)
        # 全體基期：-1 佔 3/10（idx3,5,8）、+1 佔 4/10（idx1,4,6,9）
        self.assertAlmostEqual(result["shift_minus1"], 2 / 6 - 3 / 10, places=6)
        self.assertAlmostEqual(result["shift_plus1"], 3 / 6 - 4 / 10, places=6)

    def test_gate_is_inclusive_at_theta(self):
        """一列 P₀ 恰等於 θ 必須被納入 gated（>=，非 >）。"""
        from src.ml.gating import compute_gating_metrics
        p0 = np.array([0.5, 0.3])
        y = np.array([0, 1])
        result = compute_gating_metrics(p0, y, theta=0.5)
        self.assertAlmostEqual(result["coverage"], 0.5)
        self.assertAlmostEqual(result["precision"], 1.0)


# ==============================================================================
# 4. RandomBaselineTests（§5 場景 4，§3.5 訂正 3）
# ==============================================================================

class RandomBaselineTests(unittest.TestCase):
    """對應紅測清單 #14-15。"""

    def test_baseline_equals_analytic_timeout_rate(self):
        from src.ml.gating import random_baseline_precision
        y = np.array([0, 0, 1, -1, 1, -1, 0, 1])
        result = random_baseline_precision(y)
        self.assertAlmostEqual(result, 3 / 8)

    def test_report_baseline_mismatch_raises(self):
        from scripts.verify.ug_g3_sb6_gating_report import assert_report_baseline_consistent
        from src.ml.gating import GatingContractError
        y = np.array([0, 0, 1, -1, 1, -1, 0, 1])  # 真實基期 3/8=0.375
        report_dict = {"random_baseline_precision": 0.5}  # 竄改
        with self.assertRaises(GatingContractError):
            assert_report_baseline_consistent(report_dict, y)


# ==============================================================================
# 5. CalibratorMatchTests（§5 場景 5，比照 SB5 sb4_model_match，補強 3）
# ==============================================================================

class CalibratorMatchTests(unittest.TestCase):
    """對應紅測清單 #16-19（2026-09-15 訂正：鍵名改為真實
    `UG_G3_SB5_calibration_report_target_triple_barrier.json` 結構——
    `LogisticRegression__sigmoid.per_class_quality["0"]` 的
    `auc_before`／`auc_after`／`platt_slope`／`platt_intercept`，加
    模型層級的 `brier_after`。原本用的 `auc_calib_fit_raw` 單一鍵是
    設計時未核對真實巢狀結構的產物——該鍵在真實 JSON 裡其實存在，
    但值是 `{class: float}` 的字典（三類 OvR），不是單一浮點數，
    直接拿來當浮點數比較在真實資料上會撞到型別錯誤。`auc_before`／
    `auc_after` 才是 `per_class_quality` 底下逐類別、已經是單一浮點數
    的正確比對對象（審查方複核發現，PM 對照真實 JSON 結構獨立驗證
    確認：`auc_calib_fit_raw` 鍵確實存在但為巢狀字典，審查方原始
    措辭「這個鍵不存在」不夠精確，已訂正為「型別不符」）。純數字
    常數，非讀檔。"""

    SB5_LR_REFERENCE = {
        "auc_before": 0.9045026037019825,
        "auc_after": 0.9045026037019825,
        "platt_slope": 1.216430131756554,
        "platt_intercept": -0.9222457511653753,
        "brier_after": 0.5196138852147298,
    }

    def test_calibrator_quality_matches_sb5_evidence(self):
        from src.ml.gating import assert_calibrator_matches_sb5
        quality = dict(self.SB5_LR_REFERENCE)
        assert_calibrator_matches_sb5(quality, self.SB5_LR_REFERENCE)  # 不拋即通過

    def test_distorted_auc_raises(self):
        from src.ml.gating import assert_calibrator_matches_sb5, GatingCalibratorMismatchError
        quality = dict(self.SB5_LR_REFERENCE)
        quality["auc_after"] = 0.5
        with self.assertRaises(GatingCalibratorMismatchError):
            assert_calibrator_matches_sb5(quality, self.SB5_LR_REFERENCE)

    def test_distorted_slope_raises(self):
        from src.ml.gating import assert_calibrator_matches_sb5, GatingCalibratorMismatchError
        quality = dict(self.SB5_LR_REFERENCE)
        quality["platt_slope"] = quality["platt_slope"] * 1.01
        with self.assertRaises(GatingCalibratorMismatchError):
            assert_calibrator_matches_sb5(quality, self.SB5_LR_REFERENCE)

    def test_distorted_brier_raises(self):
        from src.ml.gating import assert_calibrator_matches_sb5, GatingCalibratorMismatchError
        quality = dict(self.SB5_LR_REFERENCE)
        quality["brier_after"] = quality["brier_after"] + 0.05
        with self.assertRaises(GatingCalibratorMismatchError):
            assert_calibrator_matches_sb5(quality, self.SB5_LR_REFERENCE)

    def test_distorted_intercept_raises(self):
        """新增：`platt_intercept` 是訂正後才加入比對的鍵，原本四項
        known-FAIL 沒有覆蓋到它，補上避免它成為沒人守的欄位。"""
        from src.ml.gating import assert_calibrator_matches_sb5, GatingCalibratorMismatchError
        quality = dict(self.SB5_LR_REFERENCE)
        quality["platt_intercept"] = quality["platt_intercept"] * 1.5
        with self.assertRaises(GatingCalibratorMismatchError):
            assert_calibrator_matches_sb5(quality, self.SB5_LR_REFERENCE)

    def test_extra_key_in_quality_ignored(self):
        """`assert_calibrator_matches_sb5()` 改為「比對 reference 內的
        全部鍵」（不寫死鍵名）後，`quality_dict` 若多出 reference 沒有
        的鍵（例如重建端額外算了 `n_unique_calibrated_values`），不應
        因此被拒絕——只比對 reference 有的鍵。"""
        from src.ml.gating import assert_calibrator_matches_sb5
        quality = dict(self.SB5_LR_REFERENCE)
        quality["n_unique_calibrated_values"] = 8255
        assert_calibrator_matches_sb5(quality, self.SB5_LR_REFERENCE)  # 不拋即通過


# ==============================================================================
# 6. FeasibleRegionTests（§5 場景 6，裁決 (a)，缺口 2）
# ==============================================================================

class FeasibleRegionTests(unittest.TestCase):
    """對應紅測清單 #20-27。"""

    def test_feasible_region_found_and_theta_star_selected(self):
        from src.ml.gating import select_theta_star
        rows = _make_sb5_like_curve_rows()
        result = select_theta_star(rows, base_rate=0.0471)
        self.assertTrue(result["feasible"])
        self.assertAlmostEqual(result["theta"], 0.069)  # gate=20%，可行集內召回最高

    def test_infeasible_region_reports_explicitly(self):
        """覆蓋率全部達標，但倍數全部不足 4x。"""
        from src.ml.gating import select_theta_star
        rows = [
            {"theta": 0.5, "gate_pct": 0.05, "coverage": 0.95, "precision": 0.10, "lift": 2.0, "recall": 0.30},
            {"theta": 0.3, "gate_pct": 0.10, "coverage": 0.90, "precision": 0.12, "lift": 2.5, "recall": 0.55},
            {"theta": 0.1, "gate_pct": 0.20, "coverage": 0.80, "precision": 0.15, "lift": 3.5, "recall": 0.85},
        ]
        result = select_theta_star(rows, base_rate=0.05)
        self.assertFalse(result["feasible"])

    def test_infeasible_region_recall_shape(self):
        """覆蓋率與倍數皆達標，但召回全部不足 60%。"""
        from src.ml.gating import select_theta_star
        rows = [
            {"theta": 0.5, "gate_pct": 0.05, "coverage": 0.95, "precision": 0.50, "lift": 10.0, "recall": 0.10},
            {"theta": 0.3, "gate_pct": 0.10, "coverage": 0.90, "precision": 0.40, "lift": 8.0, "recall": 0.30},
            {"theta": 0.1, "gate_pct": 0.15, "coverage": 0.85, "precision": 0.30, "lift": 6.0, "recall": 0.50},
        ]
        result = select_theta_star(rows, base_rate=0.05)
        self.assertFalse(result["feasible"])

    def test_tie_break_by_precision(self):
        from src.ml.gating import select_theta_star
        rows = [
            {"theta": 0.2, "gate_pct": 0.15, "coverage": 0.85, "precision": 0.30, "lift": 6.0, "recall": 0.70},
            {"theta": 0.1, "gate_pct": 0.20, "coverage": 0.80, "precision": 0.35, "lift": 7.0, "recall": 0.70},
        ]
        result = select_theta_star(rows, base_rate=0.05)
        self.assertTrue(result["feasible"])
        self.assertAlmostEqual(result["theta"], 0.1)
        self.assertAlmostEqual(result["precision"], 0.35)

    def test_each_criterion_excludes_independently(self):
        """四點夾具：D 基準（三項皆達標，召回 0.70）；A/B/C 分別只違反
        覆蓋率／倍數／召回一項，翻轉後召回依序為 0.90/0.85/0.80，皆高於
        D 的 0.70——確保翻轉後該點必定以召回勝出取代 D。

        **對偵測力的誠實訂正（PO 2026-09-15，GREEN 授權時指出）**：
        本測試對「覆蓋率」與「倍數」兩項判準有真實偵測力——若實作漏檢查
        其中一項，A 或 B 翻轉後選擇結果不會改變，測試會 FAIL。**但對
        「召回」這一項，本測試結構上無法失敗（`CLAUDE.md` §9A.1）**：
        選點規則本身就是「可行集中取召回最高者」，C 要違反召回下限必須
        `<0.60`，而基準點 D 合格必須 `>=0.60`，C 在違反狀態下永遠不可能
        召回高於 D，因此不管實作有沒有真的檢查召回下限，C_fail 版本的
        選擇結果都是 D——這個判準是否被檢查，本測試看不出來。**召回下限
        唯一能被觀測到的情境是「全部候選點召回皆不足」，由
        `test_infeasible_region_recall_shape` 承擔**（該測試的合成資料
        覆蓋率與倍數皆達標、召回全部 `<0.60`，若實作漏檢查召回下限，
        會誤判為可行）。兩項測試互補，合起來對三項判準才有完整偵測力，
        本測試單獨存在**不足以**證明召回下限有被檢查。"""
        from src.ml.gating import select_theta_star
        base_rate = 0.10

        def make(theta, coverage, lift, recall):
            return {"theta": theta, "gate_pct": 0.20, "coverage": coverage,
                     "precision": lift * base_rate, "lift": lift, "recall": recall}

        D = make(0.10, coverage=0.85, lift=5.0, recall=0.70)
        A_fail = make(0.20, coverage=0.75, lift=5.0, recall=0.90)
        A_ok = make(0.20, coverage=0.85, lift=5.0, recall=0.90)
        B_fail = make(0.30, coverage=0.85, lift=3.5, recall=0.85)
        B_ok = make(0.30, coverage=0.85, lift=4.5, recall=0.85)
        C_fail = make(0.40, coverage=0.85, lift=5.0, recall=0.55)
        C_ok = make(0.40, coverage=0.85, lift=5.0, recall=0.80)

        base_result = select_theta_star([D, A_fail, B_fail, C_fail], base_rate=base_rate)
        self.assertTrue(base_result["feasible"])
        self.assertAlmostEqual(base_result["theta"], D["theta"])

        result_a = select_theta_star([D, A_ok, B_fail, C_fail], base_rate=base_rate)
        self.assertAlmostEqual(result_a["theta"], A_ok["theta"])

        result_b = select_theta_star([D, A_fail, B_ok, C_fail], base_rate=base_rate)
        self.assertAlmostEqual(result_b["theta"], B_ok["theta"])

        result_c = select_theta_star([D, A_fail, B_fail, C_ok], base_rate=base_rate)
        self.assertAlmostEqual(result_c["theta"], C_ok["theta"])

    def test_boundary_values_are_feasible(self):
        from src.ml.gating import select_theta_star
        row = {"theta": 0.1, "gate_pct": 0.20, "coverage": 0.80, "precision": 0.40, "lift": 4.0, "recall": 0.60}
        result = select_theta_star([row], base_rate=0.10)
        self.assertTrue(result["feasible"])

    def test_rows_with_null_precision_are_skipped(self):
        from src.ml.gating import select_theta_star
        empty_row = {"theta": 0.99, "gate_pct": 0.001, "coverage": 0.999, "precision": None, "lift": None, "recall": 0.01}
        good_row = {"theta": 0.1, "gate_pct": 0.20, "coverage": 0.80, "precision": 0.40, "lift": 4.0, "recall": 0.60}
        result = select_theta_star([empty_row, good_row], base_rate=0.10)
        self.assertTrue(result["feasible"])
        self.assertAlmostEqual(result["theta"], good_row["theta"])

    def test_feasible_result_fields_complete(self):
        from src.ml.gating import select_theta_star
        row = {"theta": 0.1, "gate_pct": 0.20, "coverage": 0.85, "precision": 0.42, "lift": 4.2, "recall": 0.65}
        result = select_theta_star([row], base_rate=0.10)
        self.assertTrue(result["feasible"])
        for key in ("theta", "gate_pct", "coverage", "precision", "lift", "recall", "rule"):
            self.assertIn(key, result)
        self.assertAlmostEqual(result["theta"], 0.1)
        self.assertAlmostEqual(result["gate_pct"], 0.20)
        self.assertAlmostEqual(result["coverage"], 0.85)
        self.assertAlmostEqual(result["precision"], 0.42)
        self.assertAlmostEqual(result["lift"], 4.2)
        self.assertAlmostEqual(result["recall"], 0.65)
        self.assertEqual(result["rule"], "max_recall_tiebreak_precision")


# ==============================================================================
# 7. RegimeDiagnosticTests（§5 場景 7，裁決 (b)，缺口 3）
# ==============================================================================

class RegimeDiagnosticTests(unittest.TestCase):
    """對應紅測清單 #28-32。"""

    def test_low_positive_count_suppresses_auc(self):
        from src.ml.gating import regime_diagnostic
        n = 30
        vol = np.concatenate([np.full(n, 0.1), np.full(n, 0.5), np.full(n, 0.9)])
        p0 = np.linspace(0, 1, n * 3)
        y = np.full(n * 3, -1)
        y[-1] = 0  # 最後一列 vol=0.9（高波動組），全組僅此 1 個 Timeout 正例
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        high = [g for g in result if g["label"] == "high"][0]
        self.assertEqual(high["n_positive"], 1)
        self.assertIsNone(high["auc"])

    def test_sufficient_positive_count_reports_auc(self):
        from src.ml.gating import regime_diagnostic
        vol, p0, y = _make_regime_fixture(n_per_group=40, seed=1)
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        for g in result:
            if g["n_positive"] >= 10:
                self.assertIsNotNone(g["auc"])

    def test_tertile_boundaries_use_actual_quantiles(self):
        from src.ml.gating import regime_diagnostic
        vol, p0, y = _make_regime_fixture(n_per_group=40, seed=2)
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        expected_q1, expected_q2 = np.quantile(vol, [1 / 3, 2 / 3])
        low = [g for g in result if g["label"] == "low"][0]
        self.assertAlmostEqual(low["cutpoint_upper"], expected_q1, places=6)

    def test_group_metrics_use_group_denominator(self):
        """三組**等大小**（各 10 列，避免不等大小夾具讓分位數邊界落在
        某一群集內部——已實測驗證：10/90/10 的不等分組會讓 1/3、2/3
        分位數雙雙落在中間那組內部，導致「低波動組」意外吸收了 90 個
        中波動列，本測試因此曾誤判；改為等大小後 tertile 邊界精確落在
        三組之間，見夾具下方數值查證）。低波動組全部 P₀>=θ（全被 gate），
        若誤用全體列數當分母，coverage 會算錯（非 0）。"""
        from src.ml.gating import regime_diagnostic
        n = 10
        vol = np.concatenate([np.full(n, 0.1), np.full(n, 0.5), np.full(n, 0.9)])
        p0 = np.concatenate([np.full(n, 0.9), np.full(n, 0.1), np.full(n, 0.9)])
        y = np.concatenate([np.zeros(n), -np.ones(n), np.zeros(n)])
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        low = [g for g in result if g["label"] == "low"][0]
        self.assertEqual(low["n"], n)
        self.assertAlmostEqual(low["coverage"], 0.0)

    def test_nan_volatility_raises(self):
        from src.ml.gating import regime_diagnostic, GatingContractError
        vol = np.array([0.1, np.nan, 0.5])
        p0 = np.array([0.2, 0.3, 0.4])
        y = np.array([0, 1, -1])
        with self.assertRaises(GatingContractError):
            regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)

    def test_regime_diagnostic_includes_shift_fields(self):
        """GREEN 複核發現的真缺陷：`compute_gating_metrics()` 內部已經
        算出 `retained_minus1_rate`／`retained_plus1_rate`／
        `shift_minus1`／`shift_plus1`，但 `regime_diagnostic()` 組裝
        每組結果字典時漏了這四個鍵，直接被丟掉——現況會 `KeyError`，
        真 RED。"""
        from src.ml.gating import regime_diagnostic
        vol, p0, y = _make_regime_fixture(n_per_group=40, seed=5)
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        for group in result:
            for key in ("retained_minus1_rate", "retained_plus1_rate", "shift_minus1", "shift_plus1"):
                self.assertIn(key, group)

    def test_regime_shift_relative_to_group_baseline(self):
        """`shift` 的基準是**組內**全體比例，不是全段比例——夾具刻意讓
        低波動組 `y=-1` 占多數、高波動組 `y=+1` 占多數，兩組的全體
        `-1`／`+1` 比例明顯不同，才測得出「不小心拿全段基期當分母」
        的錯誤版本。"""
        from src.ml.gating import regime_diagnostic
        n = 30
        vol = np.concatenate([np.full(n, 0.1), np.full(n, 0.5), np.full(n, 0.9)])
        # 低波動組：25 個 -1、5 個 +1（組內 -1 比例 0.833）
        # 高波動組：5 個 -1、25 個 +1（組內 -1 比例 0.167）
        y_low = np.array([-1] * 25 + [1] * 5)
        y_mid = np.array([-1] * 15 + [1] * 15)
        y_high = np.array([-1] * 5 + [1] * 25)
        y = np.concatenate([y_low, y_mid, y_high])
        p0 = np.full(n * 3, 0.1)  # 全部 P₀ 極低，theta=0.5 時無人被 gate（保留集＝全組）
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        low = [g for g in result if g["label"] == "low"][0]
        # theta 高於全體 P₀，保留集＝該組全體，故 retained_minus1_rate 應等於組內 -1 比例
        self.assertAlmostEqual(low["retained_minus1_rate"], 25 / 30, places=6)
        # shift 為保留集比例減組內全體比例；此夾具下保留集＝全體，shift 應為 0
        self.assertAlmostEqual(low["shift_minus1"], 0.0, places=6)

    def test_min_positive_boundary_exactly_at_threshold(self):
        """`min_positive_for_auc` 邊界覆蓋率補強（現況程式碼已是
        `>=`，獨立核對過非 bug；本測試單獨存在不算 RED，是防止
        `>` 版本的錯誤實作未來被靜默引入的迴歸守衛）。"""
        from src.ml.gating import regime_diagnostic
        n = 30
        vol = np.concatenate([np.full(n, 0.1), np.full(n, 0.5), np.full(n, 0.9)])
        rng = np.random.RandomState(7)
        p0 = rng.uniform(0, 1, n * 3)
        y_low = np.array([0] * 10 + [-1] * 20)  # 恰 10 個正例
        y = np.concatenate([y_low, np.full(n, -1), np.full(n, -1)])
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        low = [g for g in result if g["label"] == "low"][0]
        self.assertEqual(low["n_positive"], 10)
        self.assertIsInstance(low["auc"], float)

    def test_min_positive_boundary_just_below_threshold(self):
        from src.ml.gating import regime_diagnostic
        n = 30
        vol = np.concatenate([np.full(n, 0.1), np.full(n, 0.5), np.full(n, 0.9)])
        rng = np.random.RandomState(8)
        p0 = rng.uniform(0, 1, n * 3)
        y_low = np.array([0] * 9 + [-1] * 21)  # 恰 9 個正例
        y = np.concatenate([y_low, np.full(n, -1), np.full(n, -1)])
        result = regime_diagnostic(vol, p0, y, theta=0.5, min_positive_for_auc=10)
        low = [g for g in result if g["label"] == "low"][0]
        self.assertEqual(low["n_positive"], 9)
        self.assertIsNone(low["auc"])


# ==============================================================================
# 8. P0SourceTests（§5 場景 8，§2.5／§3.3 教訓落地）
# ==============================================================================

class P0SourceTests(unittest.TestCase):
    """對應紅測清單 #33-34。"""

    def test_p0_equals_apply_calibrator_output(self):
        from src.ml.calibration import fit_calibrator, apply_calibrator
        from src.ml.gating import calibrated_timeout_probability
        raw_scores, y, fold_id = _make_p0_source_fixture()
        calibrator = fit_calibrator(
            raw_scores, y, fold_id=fold_id, method="sigmoid", target_column="target_triple_barrier")
        official = apply_calibrator(calibrator, raw_scores)[:, 1]
        via_gating = calibrated_timeout_probability(calibrator, raw_scores)
        self.assertTrue(np.array_equal(via_gating, official))

    def test_unnormalized_p0_mutant_detected(self):
        from src.ml.calibration import fit_calibrator, apply_calibrator
        raw_scores, y, fold_id = _make_p0_source_fixture()
        calibrator = fit_calibrator(
            raw_scores, y, fold_id=fold_id, method="sigmoid", target_column="target_triple_barrier")
        official = apply_calibrator(calibrator, raw_scores)[:, 1]
        single_calibrator = calibrator[0]  # 只對 class 0 做單一 Platt，未正規化
        mutant_p0 = single_calibrator.predict(raw_scores[:, 1])
        max_diff = float(np.max(np.abs(mutant_p0 - official)))
        self.assertGreater(max_diff, 0.01)  # 容忍度 <0.01，差異需超過此值才算偵測到


# ==============================================================================
# 9. ThetaGridTests（§3.3 訂正 1，補強 6）
# ==============================================================================

class ThetaGridTests(unittest.TestCase):
    """對應紅測清單 #35-36。"""

    def test_fine_grid_covers_expected_range(self):
        from src.ml.gating import build_theta_grid
        p0 = np.linspace(0, 1, 1000)
        grid = build_theta_grid(p0)
        fine = grid["fine"]
        self.assertAlmostEqual(min(fine), 0.0, places=6)
        self.assertAlmostEqual(max(fine), 0.60, places=6)
        self.assertEqual(len(fine), 121)

    def test_quantile_grid_dedup_monotonic_and_nonempty(self):
        from src.ml.gating import build_theta_grid
        rng = np.random.RandomState(4)
        p0 = rng.uniform(0, 1, 500)
        grid = build_theta_grid(p0)
        quantile = list(grid["quantile"])
        self.assertEqual(quantile, sorted(quantile))
        self.assertEqual(len(quantile), len(set(quantile)))
        for theta in quantile:
            gated_count = int((p0 >= theta).sum())
            self.assertGreater(gated_count, 0)


# ==============================================================================
# 10. GatingConstantsPinnedTests（比照 SB4／SB5 先例，補強 2）
# ==============================================================================

class GatingConstantsPinnedTests(unittest.TestCase):
    """對應紅測清單 #37-38。"""

    def test_criteria_and_regime_constants_pinned(self):
        from src.ml.gating import (
            MIN_COVERAGE, MIN_LIFT, MIN_RECALL, MIN_POSITIVE_FOR_AUC,
            REGIME_COL, THETA_FINE_STEP, THETA_FINE_MAX,
        )
        self.assertEqual(MIN_COVERAGE, 0.80)
        self.assertEqual(MIN_LIFT, 4.0)
        self.assertEqual(MIN_RECALL, 0.60)
        self.assertEqual(MIN_POSITIVE_FOR_AUC, 10)
        self.assertEqual(REGIME_COL, "volatility_20d")
        self.assertEqual(THETA_FINE_STEP, 0.005)
        self.assertEqual(THETA_FINE_MAX, 0.60)

    def test_holdout_start_date_shared_with_stacking(self):
        from src.ml import gating
        from src.ml import stacking
        self.assertIs(gating.HOLDOUT_START_DATE, stacking.HOLDOUT_START_DATE)


# ==============================================================================
# 11. CurveRowAssemblyTests（審查方複核 GREEN `09bcba9` 時追加，報告腳本
# 全量執行階段第 5 項——新函式，現況不存在，真 RED）
# ==============================================================================

class CurveRowAssemblyTests(unittest.TestCase):
    """`select_theta_star()` 不重算 `lift`／`gate_pct`，兩者的正確性
    只能在組裝曲線列的地方驗證——新函式 `assemble_curve_row()`，現況
    不存在於 `src/ml/gating.py`，真 RED。"""

    def test_curve_row_construction(self):
        from src.ml.gating import assemble_curve_row
        # 10 列夾具，3 個 Timeout，θ=0.6 使 4 列被 gate（2 Timeout），
        # 與 GatingMetricsTests.test_metrics_on_mixed_fixture 同一組數字。
        p0 = np.array([0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.05])
        y = np.array([0, 1, 0, -1, 1, -1, 1, 0, -1, 1])
        base_rate = 0.3  # 全體 10 列中 3 個 Timeout
        row = assemble_curve_row(theta=0.6, p0=p0, y_true=y, base_rate=base_rate)
        self.assertAlmostEqual(row["theta"], 0.6)
        self.assertAlmostEqual(row["coverage"], 0.6)
        self.assertAlmostEqual(row["gate_pct"], 1 - 0.6)
        self.assertAlmostEqual(row["precision"], 0.5)
        self.assertAlmostEqual(row["lift"], 0.5 / 0.3)
        self.assertAlmostEqual(row["recall"], 2 / 3)

    def test_curve_row_lift_is_none_when_precision_none(self):
        from src.ml.gating import assemble_curve_row
        p0 = np.array([0.1, 0.2, 0.3])
        y = np.array([0, 1, -1])
        row = assemble_curve_row(theta=0.99, p0=p0, y_true=y, base_rate=0.3)
        self.assertIsNone(row["precision"])
        self.assertIsNone(row["lift"])


if __name__ == "__main__":
    unittest.main()
