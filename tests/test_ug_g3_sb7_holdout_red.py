# -*- coding: utf-8 -*-
"""UG-G3-SB7 紅測（RED）——Holdout 最終驗證管線尚不存在，全部測試預期
`ImportError`／`AttributeError`。依 `doc/upgrade/gates/UG_G3_SB7_GATE_A_PROPOSAL.md`
v2 §5 六個場景與 PO 追加的十項必含測試設計，全部使用合成資料，不讀取任何
真實 parquet 或真實 SB6 evidence 檔（`CLAUDE.md` §13.4 測試封閉性；本 SB
更嚴格——不得碰真正的折 33-42，連測試資料都用合成的）。

新函式清單（本次紅測鎖定的介面）：
- `src.ml.stacking.iter_holdout_folds(splitter, panel, holdout_start_date)`
  ——`iter_oof_folds()` 的互補迭代器，`test_start_date >= boundary` 才 yield
  （**訂正 1**：v1 提案誤用 `test_end_date >=`，會把跨界折整個納入 Holdout）。
- `src.ml.gating.assert_holdout_only(fold_id, trade_date)`——`assert_holdout_isolation()`
  的反向版本，任何一列不在 Holdout 範圍內即拋 `GatingHoldoutViolation`。
- `scripts.verify.ug_g3_sb7_holdout_report`（新檔）：
  `compute_folds_excluded_by_both()`、`extract_sb6_reference()`、
  `assert_frozen_value_matches()`、`_is_holdout_already_consumed()`、
  `_should_write_holdout()`、`evaluate_gate_rule()`、`build_per_fold_stability()`、
  `build_baseline_comparison()`、`build_up_down_observational_auc()`、
  `run_report()`、`VOL_COVERAGE_MATCHED_CUTPOINT` 常數。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd


def _synthetic_panel(n_days=200):
    """比照 `tests/test_ug_g3_sb4_stacking_red.py::HoldoutFoldsNeverIteratedTests`
    既有慣例。"""
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    rows = []
    for d in dates:
        for s in ("A", "B", "C"):
            rows.append({"stock_id": s, "trade_date": d, "target_triple_barrier": 0})
    return pd.DataFrame(rows)


# ==============================================================================
# 訂正 1：iter_holdout_folds() 邊界改用 test_start_date，防跨界折雙重排除卻無人揭露
# ==============================================================================

class IterHoldoutFoldsTests(unittest.TestCase):
    """對應 PO 必含項 1。GREEN 階段的 known-FAIL 突變體之一：把納入條件
    暫時改回 `test_end_date >= boundary`，`test_straddling_fold_excluded_by_both_iterators`
    必須 FAIL（跨界折會被誤納入 Holdout）。"""

    def test_yields_only_folds_starting_at_or_after_boundary(self):
        from src.ml.time_series_split import WalkForwardSplitter
        from src.ml.stacking import iter_holdout_folds

        panel = _synthetic_panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        boundary = panel["trade_date"].max() - pd.Timedelta(days=40)

        folds = list(iter_holdout_folds(splitter, panel, boundary))
        self.assertGreater(len(folds), 0, "邊界設定應至少產出一折，測試才有意義")
        for _, test_idx, _ in folds:
            test_dates = panel.loc[test_idx, "trade_date"]
            self.assertGreaterEqual(test_dates.min(), boundary,
                                     "iter_holdout_folds() 產出的每折測試窗起點都必須 >= boundary")

    def test_straddling_fold_excluded_by_both_iterators(self):
        """訂正 1 核心案例：合成一個測試窗恰好橫跨邊界的折，`iter_oof_folds()`
        與 `iter_holdout_folds()` 都不得 yield 它——兩者的排除條件互補
        （`test_end_date >= boundary` 排除 vs `test_start_date < boundary` 排除），
        對跨界折達成一致排除，不是誤入其中一邊。"""
        from src.ml.time_series_split import WalkForwardSplitter
        from src.ml.stacking import iter_oof_folds, iter_holdout_folds

        panel = _synthetic_panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")

        all_folds = list(splitter.split(panel))
        target_fold_idx = 5
        _, target_test_idx, target_meta = all_folds[target_fold_idx]
        target_test_dates = panel.loc[target_test_idx, "trade_date"]
        straddle_boundary = target_test_dates.min() + (
            (target_test_dates.max() - target_test_dates.min()) / 2)
        self.assertGreater(straddle_boundary, target_test_dates.min())
        self.assertLess(straddle_boundary, target_test_dates.max())

        oof_folds = list(iter_oof_folds(splitter, panel, straddle_boundary))
        holdout_folds = list(iter_holdout_folds(splitter, panel, straddle_boundary))

        oof_fold_nums = {meta["fold"] for _, _, meta in oof_folds}
        holdout_fold_nums = {meta["fold"] for _, _, meta in holdout_folds}
        target_fold_num = target_meta["fold"]

        self.assertNotIn(target_fold_num, oof_fold_nums,
                          "跨界折不得被 iter_oof_folds() 納入")
        self.assertNotIn(target_fold_num, holdout_fold_nums,
                          "跨界折不得被 iter_holdout_folds() 納入")

    def test_union_and_intersection_with_iter_oof_folds_when_no_straddle(self):
        """無跨界折時（邊界恰好落在兩折交界），並集覆蓋全部折、交集為空——
        訂正 1 之前 v1 的「巧合成立」在此正控制案例應仍然成立。"""
        from src.ml.time_series_split import WalkForwardSplitter
        from src.ml.stacking import iter_oof_folds, iter_holdout_folds

        panel = _synthetic_panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        all_folds = list(splitter.split(panel))
        all_fold_nums = {meta["fold"] for _, _, meta in all_folds}

        boundary_fold_idx = 6
        _, boundary_test_idx, _ = all_folds[boundary_fold_idx]
        boundary = panel.loc[boundary_test_idx, "trade_date"].min()

        oof_fold_nums = {meta["fold"] for _, _, meta in iter_oof_folds(splitter, panel, boundary)}
        holdout_fold_nums = {meta["fold"] for _, _, meta in iter_holdout_folds(splitter, panel, boundary)}

        self.assertEqual(oof_fold_nums | holdout_fold_nums, all_fold_nums)
        self.assertEqual(oof_fold_nums & holdout_fold_nums, set())


class FoldsExcludedByBothTests(unittest.TestCase):
    """對應 PO 必含項 1 的揭露欄位：`folds_excluded_by_both_iterators` 必須
    機械記錄，不得靜默假設現行資料沒有跨界折。"""

    def test_returns_empty_when_no_straddle(self):
        from src.ml.time_series_split import WalkForwardSplitter
        from scripts.verify.ug_g3_sb7_holdout_report import compute_folds_excluded_by_both

        panel = _synthetic_panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        all_folds = list(splitter.split(panel))
        boundary = panel.loc[all_folds[6][1], "trade_date"].min()

        excluded = compute_folds_excluded_by_both(splitter, panel, boundary)
        self.assertEqual(excluded, [])

    def test_returns_straddling_fold_number(self):
        from src.ml.time_series_split import WalkForwardSplitter
        from scripts.verify.ug_g3_sb7_holdout_report import compute_folds_excluded_by_both

        panel = _synthetic_panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        all_folds = list(splitter.split(panel))
        _, target_test_idx, target_meta = all_folds[5]
        target_test_dates = panel.loc[target_test_idx, "trade_date"]
        straddle_boundary = target_test_dates.min() + (
            (target_test_dates.max() - target_test_dates.min()) / 2)

        excluded = compute_folds_excluded_by_both(splitter, panel, straddle_boundary)
        self.assertEqual(excluded, [target_meta["fold"]])


# ==============================================================================
# 訂正無編號（PO 必含項 2）：逆向隔離守衛
# ==============================================================================

class AssertHoldoutOnlyTests(unittest.TestCase):
    """`assert_holdout_only()`：`assert_holdout_isolation()` 的反向版本，
    新產生的 Holdout OOF 必須全部落在 Holdout 範圍內，任何一列漏出即拋錯。"""

    def test_accepts_rows_fully_within_holdout(self):
        from src.ml.gating import assert_holdout_only

        fold_id = np.array([33, 35, 40, 42])
        trade_date = pd.to_datetime(["2025-10-23", "2025-11-01", "2026-03-01", "2026-08-20"])
        assert_holdout_only(fold_id, trade_date)  # 不得拋出

    def test_rejects_row_from_fold_32(self):
        """known-FAIL：混入一列折 32（非 Holdout）。"""
        from src.ml.gating import assert_holdout_only, GatingHoldoutViolation

        fold_id = np.array([32, 33, 35])
        trade_date = pd.to_datetime(["2025-10-22", "2025-10-23", "2025-11-01"])
        with self.assertRaises(GatingHoldoutViolation):
            assert_holdout_only(fold_id, trade_date)

    def test_rejects_date_before_holdout_start(self):
        from src.ml.gating import assert_holdout_only, GatingHoldoutViolation

        fold_id = np.array([33, 33])
        trade_date = pd.to_datetime(["2025-10-22", "2025-10-23"])
        with self.assertRaises(GatingHoldoutViolation):
            assert_holdout_only(fold_id, trade_date)


# ==============================================================================
# 訂正 5：--write 時 holdout_start_date 必須等於常數；訂正 4：無繞過旗標
# ==============================================================================

class ShouldWriteHoldoutTests(unittest.TestCase):
    """對應 PO 必含項 3、4。"""

    def test_refuses_when_holdout_start_date_not_default(self):
        from scripts.verify.ug_g3_sb7_holdout_report import _should_write_holdout
        from src.ml.stacking import META_EVAL_START_DATE

        should_write, reason = _should_write_holdout(
            write_flag=True, holdout_start_date=META_EVAL_START_DATE,
            script_dirty=False, already_consumed=False,
        )
        self.assertFalse(should_write)

    def test_refuses_when_script_dirty(self):
        from scripts.verify.ug_g3_sb7_holdout_report import _should_write_holdout
        from src.ml.stacking import HOLDOUT_START_DATE

        should_write, reason = _should_write_holdout(
            write_flag=True, holdout_start_date=HOLDOUT_START_DATE,
            script_dirty=True, already_consumed=False,
        )
        self.assertFalse(should_write)

    def test_refuses_when_already_consumed(self):
        """對應必含項 4：第二次 `--write`（`holdout_consumed_at` 已存在）一律
        拒絕——本函式簽章沒有任何「繞過」參數可傳，訂正 4 移除
        `--force-reconsume` 後的直接結果。"""
        from scripts.verify.ug_g3_sb7_holdout_report import _should_write_holdout
        from src.ml.stacking import HOLDOUT_START_DATE

        should_write, reason = _should_write_holdout(
            write_flag=True, holdout_start_date=HOLDOUT_START_DATE,
            script_dirty=False, already_consumed=True,
        )
        self.assertFalse(should_write)

    def test_proceeds_when_all_conditions_met(self):
        """正控制：四項條件同時成立才允許寫入。"""
        from scripts.verify.ug_g3_sb7_holdout_report import _should_write_holdout
        from src.ml.stacking import HOLDOUT_START_DATE

        should_write, reason = _should_write_holdout(
            write_flag=True, holdout_start_date=HOLDOUT_START_DATE,
            script_dirty=False, already_consumed=False,
        )
        self.assertTrue(should_write)

    def test_no_bypass_parameter_exists(self):
        """訂正 4 的結構性保證：函式簽章裡沒有任何名稱含 force／bypass／
        override 的參數。"""
        import inspect
        from scripts.verify.ug_g3_sb7_holdout_report import _should_write_holdout

        params = set(inspect.signature(_should_write_holdout).parameters)
        forbidden = {p for p in params if any(
            kw in p.lower() for kw in ("force", "bypass", "override", "reconsume"))}
        self.assertEqual(forbidden, set())


class AlreadyConsumedDetectionTests(unittest.TestCase):
    """`_is_holdout_already_consumed()`：讀取既有 evidence JSON 是否已含
    `holdout_consumed_at`。"""

    def test_false_when_file_absent(self):
        from scripts.verify.ug_g3_sb7_holdout_report import _is_holdout_already_consumed

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "does_not_exist.json"
            self.assertFalse(_is_holdout_already_consumed(path))

    def test_true_when_consumed_at_present(self):
        from scripts.verify.ug_g3_sb7_holdout_report import _is_holdout_already_consumed

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "evidence.json"
            path.write_text(json.dumps({"holdout_consumed_at": "2026-09-17T00:00:00+00:00"}))
            self.assertTrue(_is_holdout_already_consumed(path))

    def test_false_when_file_exists_without_consumed_at(self):
        from scripts.verify.ug_g3_sb7_holdout_report import _is_holdout_already_consumed

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "evidence.json"
            path.write_text(json.dumps({"some_other_field": 1}))
            self.assertFalse(_is_holdout_already_consumed(path))


# ==============================================================================
# 訂正 3：凍結值（θ*、regime 切點、覆蓋率對齊切點）必須從既有來源讀取，不得重算
# ==============================================================================

class ExtractSb6ReferenceTests(unittest.TestCase):
    """逐字仿真實 `UG_G3_SB6_gating_report.json` 結構（PM 本次會期已逐一核對
    過真實檔案，非杜撰——比照 `feedback-fixture-must-mirror-real-evidence-structure`
    教訓，鍵名與巢狀結構逐字對照過）。"""

    def _make_sb6_json_fixture(self):
        return {
            "selected_theta": {
                "feasible": True,
                "theta": 0.06907452098250194,
                "gate_pct": 0.19999999999999996,
                "coverage": 0.8,
                "precision": 0.1956390066626287,
                "lift": 4.151670951156812,
                "recall": 0.8303341902313625,
                "rule": "max_recall_tiebreak_precision",
            },
            "regime_diagnostic": [
                {"label": "low", "cutpoint_lower": None, "cutpoint_upper": 0.30421394224025783},
                {"label": "mid", "cutpoint_lower": 0.30421394224025783, "cutpoint_upper": 0.48111676232087386},
                {"label": "high", "cutpoint_lower": 0.48111676232087386, "cutpoint_upper": None},
            ],
        }

    def test_extract_theta_star_and_rule(self):
        from scripts.verify.ug_g3_sb7_holdout_report import extract_sb6_reference

        ref = extract_sb6_reference(self._make_sb6_json_fixture())
        self.assertAlmostEqual(ref["theta_star"], 0.06907452098250194)
        self.assertEqual(ref["rule"], "max_recall_tiebreak_precision")

    def test_extract_tercile_cutpoints(self):
        from scripts.verify.ug_g3_sb7_holdout_report import extract_sb6_reference

        ref = extract_sb6_reference(self._make_sb6_json_fixture())
        self.assertAlmostEqual(ref["tercile_low_cutpoint"], 0.30421394224025783)
        self.assertAlmostEqual(ref["tercile_mid_cutpoint"], 0.48111676232087386)


class VolCoverageMatchedConstantTests(unittest.TestCase):
    """覆蓋率對齊切點是本輪（Gate A v2）新算並凍結的值，寫死為模組常數，
    Holdout 上沿用、不重算。"""

    def test_constant_pinned(self):
        from scripts.verify.ug_g3_sb7_holdout_report import VOL_COVERAGE_MATCHED_CUTPOINT
        self.assertAlmostEqual(VOL_COVERAGE_MATCHED_CUTPOINT, 0.23116970731839864)


class AssertFrozenValueMatchesTests(unittest.TestCase):
    """任何凍結值（θ*、regime 切點、覆蓋率對齊切點）在報告腳本內使用前
    都要過這道守衛，防止意外重算後悄悄使用了不同的數字。"""

    def test_accepts_equal_value(self):
        from scripts.verify.ug_g3_sb7_holdout_report import assert_frozen_value_matches

        assert_frozen_value_matches(0.30421394224025783, 0.30421394224025783, "tercile_low")

    def test_rejects_distorted_value(self):
        """known-FAIL：模擬報告腳本意外用 Holdout 資料自己的分位數重算切點，
        與凍結值不符。"""
        from scripts.verify.ug_g3_sb7_holdout_report import assert_frozen_value_matches
        from src.ml.gating import GatingContractError

        with self.assertRaises(GatingContractError):
            assert_frozen_value_matches(0.31, 0.30421394224025783, "tercile_low")


# ==============================================================================
# 核心指標函式（供 baseline 比較、逐折穩定性共用）
# ==============================================================================

class EvaluateGateRuleTests(unittest.TestCase):
    """`evaluate_gate_rule(gated_mask, y_true, base_rate)`：給定任意布林
    `gated_mask`（True=觀望），計算 precision／coverage／recall／lift。
    Timeout=class 0，與 `src.ml.gating.compute_gating_metrics()` 的定義一致，
    但輸入是任意來源的 mask（不限於 `P₀>=theta`），供波動率基線與 Timeout
    gating 共用同一套指標計算。"""

    def test_precision_coverage_recall_lift_hand_computed(self):
        from scripts.verify.ug_g3_sb7_holdout_report import evaluate_gate_rule

        # 10 列，class 0（Timeout）4 列，gated 3 列（前 3 列皆為真 Timeout，
        # 第 4 個 Timeout 列刻意不 gate，驗證 recall < 1.0 的一般情況）
        y_true = np.array([0, 0, 0, 0, 1, 1, -1, -1, 1, -1])
        gated_mask = np.array([True, True, True, False, False, False, False, False, False, False])
        base_rate = 0.4  # 4/10

        result = evaluate_gate_rule(gated_mask, y_true, base_rate)
        self.assertEqual(result["n"], 10)
        self.assertEqual(result["n_timeout"], 4)
        self.assertEqual(result["n_gated"], 3)
        self.assertAlmostEqual(result["coverage"], 0.7)
        self.assertAlmostEqual(result["precision"], 3 / 3)
        self.assertAlmostEqual(result["recall"], 3 / 4)
        self.assertAlmostEqual(result["lift"], 1.0 / 0.4)

    def test_empty_gate_precision_and_lift_null(self):
        """訂正 5（`UG-G3-SB6` 既有慣例延續）：`gated` 為空集時 `precision`／
        `lift` 必須是 `None`，不得回傳 `0` 或基期。"""
        from scripts.verify.ug_g3_sb7_holdout_report import evaluate_gate_rule

        y_true = np.array([0, 1, -1])
        gated_mask = np.array([False, False, False])
        result = evaluate_gate_rule(gated_mask, y_true, base_rate=0.3)
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["lift"])
        self.assertAlmostEqual(result["coverage"], 1.0)
        self.assertAlmostEqual(result["recall"], 0.0)


class VolatilityBaselineRuleTests(unittest.TestCase):
    """對應 PO 必含項 9：波動率基線 (i)(ii) 各一個手算夾具。"""

    def test_tercile_rule_hand_computed(self):
        from scripts.verify.ug_g3_sb7_holdout_report import evaluate_gate_rule

        volatility = np.array([0.1, 0.2, 0.5, 0.6])
        cutpoint = 0.30421394224025783
        gated_mask = volatility <= cutpoint
        np.testing.assert_array_equal(gated_mask, [True, True, False, False])

        y_true = np.array([0, 1, -1, 0])
        result = evaluate_gate_rule(gated_mask, y_true, base_rate=0.5)
        self.assertEqual(result["n_gated"], 2)
        self.assertAlmostEqual(result["precision"], 0.5)  # 1 個 Timeout / 2 gated

    def test_coverage_matched_rule_hand_computed(self):
        from scripts.verify.ug_g3_sb7_holdout_report import (
            evaluate_gate_rule, VOL_COVERAGE_MATCHED_CUTPOINT)

        volatility = np.array([0.1, 0.15, 0.2, 0.5])
        gated_mask = volatility <= VOL_COVERAGE_MATCHED_CUTPOINT
        np.testing.assert_array_equal(gated_mask, [True, True, True, False])

        y_true = np.array([0, 0, -1, 1])
        result = evaluate_gate_rule(gated_mask, y_true, base_rate=0.5)
        self.assertEqual(result["n_gated"], 3)
        self.assertAlmostEqual(result["precision"], 2 / 3)

    def test_coverage_matched_gate_ratio_matches_percentile_on_synthetic_data(self):
        """驗證覆蓋率對齊切點的定義本身——對一批合成 `volatility_20d`
        重新取第 20 百分位，套用後 gate 比例應與 `np.percentile` 的定義
        一致（不要求恰為 0.2000，合成資料量小時允許些微誤差，只驗證
        「切點來自第 20 百分位」這個關係本身）。"""
        rng = np.random.RandomState(7)
        volatility = rng.uniform(0, 1, 500)
        p20 = np.percentile(volatility, 20)
        gated_mask = volatility <= p20
        self.assertAlmostEqual(gated_mask.mean(), 0.20, delta=0.02)


class PerFoldStabilityTests(unittest.TestCase):
    """對應 PO 必含項 7：逐折表含 `n`／`n_timeout`／`n_gated`，`n_gated=0`
    時 `precision` 為 `null`，且不設逐折通過門檻。"""

    def test_fields_present_per_fold(self):
        from scripts.verify.ug_g3_sb7_holdout_report import build_per_fold_stability

        fold_id = np.array([33, 33, 34, 34, 34])
        p0 = np.array([0.9, 0.1, 0.9, 0.9, 0.1])
        y_true = np.array([0, -1, 0, 1, -1])
        theta_star = 0.5

        rows = build_per_fold_stability(fold_id, p0, y_true, theta_star)
        self.assertEqual({r["fold_id"] for r in rows}, {33, 34})
        for r in rows:
            for key in ("n", "n_timeout", "n_gated", "coverage", "precision", "recall", "lift"):
                self.assertIn(key, r)

    def test_zero_gated_fold_precision_is_null(self):
        from scripts.verify.ug_g3_sb7_holdout_report import build_per_fold_stability

        fold_id = np.array([33, 33])
        p0 = np.array([0.1, 0.2])  # 全部低於門檻，該折無列被 gate
        y_true = np.array([-1, 1])
        theta_star = 0.9

        rows = build_per_fold_stability(fold_id, p0, y_true, theta_star)
        row33 = next(r for r in rows if r["fold_id"] == 33)
        self.assertEqual(row33["n_gated"], 0)
        self.assertIsNone(row33["precision"])

    def test_no_pass_fail_threshold_field(self):
        """逐折表不得帶有任何「通過／失敗」判定欄位——只描述數字，不下結論。"""
        from scripts.verify.ug_g3_sb7_holdout_report import build_per_fold_stability

        fold_id = np.array([33, 34])
        p0 = np.array([0.9, 0.9])
        y_true = np.array([0, 0])
        rows = build_per_fold_stability(fold_id, p0, y_true, theta_star=0.5)
        for r in rows:
            for forbidden_key in ("passed", "failed", "pass_fail", "status"):
                self.assertNotIn(forbidden_key, r)


# ==============================================================================
# PO 必含項 8：target_up_down 觀察用 AUC，不進任何判準函式
# ==============================================================================

class UpDownObservationalTests(unittest.TestCase):

    def test_observational_flag_present(self):
        from scripts.verify.ug_g3_sb7_holdout_report import build_up_down_observational_auc

        y_true = np.array([1, 0, 1, 0, 1])
        scores = {
            "lr": np.array([0.9, 0.1, 0.8, 0.2, 0.7]),
            "rf": np.array([0.6, 0.4, 0.6, 0.4, 0.6]),
        }
        result = build_up_down_observational_auc(scores, y_true)
        self.assertTrue(result.get("observational"))
        self.assertIn("lr", result)
        self.assertIn("rf", result)

    def test_observational_auc_rejected_by_criterion_function(self):
        """mutant：若程式碼意外把觀察用 AUC 字典餵進 gating 判準函式
        （`select_theta_star()` 預期 `curve_rows`：帶 `theta`／`precision`
        等鍵的 list），結構性型別不符必須拋錯——不是新設計的旗標保護，
        是資料形狀本來就不相容。"""
        from scripts.verify.ug_g3_sb7_holdout_report import build_up_down_observational_auc
        from src.ml.gating import select_theta_star

        y_true = np.array([1, 0, 1, 0])
        scores = {"lr": np.array([0.9, 0.1, 0.8, 0.2])}
        observational_auc = build_up_down_observational_auc(scores, y_true)

        with self.assertRaises((TypeError, KeyError, AttributeError, IndexError)):
            select_theta_star(observational_auc, base_rate=0.05)


# ==============================================================================
# PO 必含項 6：Meta(A)／校準器比對守衛直接複用既有函式
# ==============================================================================

class ReuseExistingGuardsTests(unittest.TestCase):
    """確認既有函式可被 SB7 報告腳本直接複用（不是重新設計），並各附一個
    扭曲 known-FAIL——這兩個函式本身已在 `UG-G3-SB5`／`SB6` 有完整測試覆蓋，
    本處只驗證 import 路徑與呼叫介面對 SB7 的使用方式成立。"""

    def test_assert_matches_sb4_report_importable_and_rejects_distortion(self):
        from scripts.verify.ug_g3_sb5_calibration_report import assert_matches_sb4_report
        from scripts.verify.ug_g3_sb5_calibration_report import CalibrationReportError

        actual = {"LogisticRegression": 0.318}
        sb4_evidence = {"meta_a": {"LogisticRegression": {"macro_f1_meta_eval": 0.500}}}
        with self.assertRaises(CalibrationReportError):
            assert_matches_sb4_report(actual, sb4_evidence)

    def test_assert_calibrator_matches_sb5_importable_and_rejects_distortion(self):
        from src.ml.gating import assert_calibrator_matches_sb5, GatingCalibratorMismatchError

        rebuilt = {"brier_after": 0.5196138852147298, "auc_before": 0.9045026037019825,
                   "auc_after": 0.9045026037019825, "platt_slope": 1.216430131756554,
                   "platt_intercept": -0.9222457511653753, "auc_calib_fit_raw_class0": 0.8295208545881081}
        sb5_reference = dict(rebuilt)
        sb5_reference["platt_slope"] = 9.99  # 扭曲

        with self.assertRaises(GatingCalibratorMismatchError):
            assert_calibrator_matches_sb5(rebuilt, sb5_reference)


# ==============================================================================
# PO 必含項 10：全合成資料紀律；完整 run_report() 接線交給乾跑驗收
# ==============================================================================

class RunReportSignatureTests(unittest.TestCase):
    """`run_report()` 的完整接線正確性由乾跑階段驗收（PO 裁決：偽 Holdout
    跑折 30-32，數字須與 `UG-G3-SB6` evidence 逐位相符——「接線正確性的
    免費驗收」），本處只鎖定函式介面存在且可用關鍵字呼叫，不在紅測階段
    對 `run_report()` 做大量 mock 的接線測試（避免为一個尚未定案到每個
    內部步驟的函式寫出脆弱的過度 mock 測試）。"""

    def test_run_report_has_expected_keyword_parameters(self):
        import inspect
        from scripts.verify.ug_g3_sb7_holdout_report import run_report

        params = set(inspect.signature(run_report).parameters)
        for required in ("oof_generation_evidence_path", "sb6_reference_path", "holdout_start_date"):
            self.assertIn(required, params)

    def test_run_report_rejects_up_down_only_for_gating_not_for_observational_auc(self):
        """`_validate_target_column()`（`UG-G3-SB6` 既有函式）鎖定 gating
        主管線只接受 `target_triple_barrier`；`target_up_down` 的觀察用
        AUC 路徑是本 SB 新增的**例外**，不經過這道守衛——這裡只鎖定
        `_validate_target_column` 本身的既有行為不受 SB7 影響，避免
        SB7 不小心把它也套用到觀察用路徑上導致 up_down 觀察功能失效。"""
        from src.ml.gating import _validate_target_column, GatingTargetColumnError

        with self.assertRaises(GatingTargetColumnError):
            _validate_target_column("target_up_down")
        _validate_target_column("target_triple_barrier")  # 不得拋出


# ==============================================================================
# PO 複核 GREEN 發現：retained_direction_shift 算錯對象（用了 target_up_down
# 而非 target_triple_barrier），改直接複用 src.ml.gating.compute_gating_metrics()
# ==============================================================================

class BuildRetainedDirectionShiftTests(unittest.TestCase):
    """`build_retained_direction_shift(p0, y_true, theta_star)` 必須直接複用
    `compute_gating_metrics()`（`UG-G3-SB6` 既有函式，已有自己的測試覆蓋），
    不得自行手寫一份等義邏輯——且 `y_true` 必須是 `target_triple_barrier`
    的 {-1,0,1} 值域，不是 `target_up_down` 的 {0,1}（PO 複核 GREEN `ac73432`
    發現的真實缺陷：原實作誤用 up_down 標籤，導致 retained_minus1_rate
    恆為 0）。"""

    def test_matches_compute_gating_metrics_and_uses_triple_barrier_labels(self):
        from scripts.verify.ug_g3_sb7_holdout_report import build_retained_direction_shift
        from src.ml.gating import compute_gating_metrics

        p0 = np.array([0.9, 0.9, 0.1, 0.1, 0.1, 0.1])
        y_true = np.array([0, 0, -1, -1, -1, 1])  # target_triple_barrier 值域，含 -1
        theta_star = 0.5

        result = build_retained_direction_shift(p0, y_true, theta_star)
        expected = compute_gating_metrics(p0, y_true, theta_star)

        for key in ("retained_minus1_rate", "retained_plus1_rate", "shift_minus1", "shift_plus1"):
            self.assertIn(key, result)
            self.assertAlmostEqual(result[key], expected[key])

        # 核心斷言：保留集裡有真實 -1 列，比例不得是 0（demonstrates 用對了
        # target_triple_barrier 的值域，不是恆為 0/1 的 up_down 值域）。
        self.assertGreater(result["retained_minus1_rate"], 0.0)


# ==============================================================================
# PO 複核 GREEN 發現：Specialist OOF 重生比對要寫進 JSON，不能只在腳本外算
# ==============================================================================

class AssertRegeneratedOofMatchesSb4Tests(unittest.TestCase):
    """`assert_regenerated_oof_matches_sb4()`：以 `(stock_id, trade_date,
    fold_id)` 對齊本次重新產生的 Specialist OOF 與真實 SB4 OOF parquet
    的重疊列，逐欄比對最大絕對差，寫入可稽核的診斷字典。"""

    def _make_new_oof(self):
        return pd.DataFrame({
            "stock_id": ["A", "B"],
            "trade_date": pd.to_datetime(["2025-08-01", "2025-08-01"]),
            "fold_id": [30, 30],
            "lr_A_p0": [0.5, 0.6],
        })

    def test_matches_within_tolerance(self):
        from scripts.verify.ug_g3_sb7_holdout_report import assert_regenerated_oof_matches_sb4

        new_oof = self._make_new_oof()
        with tempfile.TemporaryDirectory() as tmpdir:
            sb4_path = Path(tmpdir) / "sb4_oof.parquet"
            sb4_oof = new_oof.copy()  # 逐位相同，代表「真的對上了」
            sb4_oof.to_parquet(sb4_path)

            result = assert_regenerated_oof_matches_sb4(new_oof, sb4_path)
        self.assertEqual(result["n_rows_compared"], 2)
        self.assertLessEqual(result["max_abs_diff"], 1e-9)

    def test_no_overlap_returns_zero_rows_not_error(self):
        """正式消費（折 33-42）與 SB4 OOF（僅折 0-32）通常無重疊——這不是
        錯誤，回傳 `n_rows_compared=0` 的診斷字典並附原因說明。"""
        from scripts.verify.ug_g3_sb7_holdout_report import assert_regenerated_oof_matches_sb4

        new_oof = self._make_new_oof()
        new_oof["fold_id"] = [33, 33]
        with tempfile.TemporaryDirectory() as tmpdir:
            sb4_path = Path(tmpdir) / "sb4_oof.parquet"
            self._make_new_oof().to_parquet(sb4_path)  # 只有折 30

            result = assert_regenerated_oof_matches_sb4(new_oof, sb4_path)
        self.assertEqual(result["n_rows_compared"], 0)

    def test_distorted_value_raises(self):
        """known-FAIL：重新產生的機率欄與 SB4 parquet 同一列的值明顯不同。"""
        from scripts.verify.ug_g3_sb7_holdout_report import assert_regenerated_oof_matches_sb4
        from src.ml.gating import GatingContractError

        new_oof = self._make_new_oof()
        with tempfile.TemporaryDirectory() as tmpdir:
            sb4_path = Path(tmpdir) / "sb4_oof.parquet"
            sb4_oof = new_oof.copy()
            sb4_oof["lr_A_p0"] = [0.99, 0.99]  # 扭曲
            sb4_oof.to_parquet(sb4_path)

            with self.assertRaises(GatingContractError):
                assert_regenerated_oof_matches_sb4(new_oof, sb4_path)


# ==============================================================================
# 正式消費實測發現：_compute_up_down_observational_auc_holdout() 無條件
# 截斷面板到 HOLDOUT_START_DATE 之前，對正式消費（折 33-42）會把自己
# 要處理的資料全部截掉，導致 iter_holdout_folds() 產不出任何折。
# ==============================================================================

class ComputeUpDownObservationalAucHoldoutTruncationTests(unittest.TestCase):
    """`_compute_up_down_observational_auc_holdout()` 的面板截斷必須只在
    乾跑（`is_real_consumption=False`）時套用；正式消費時不得截斷，否則
    折 33-42 的資料在還沒跑到 `iter_holdout_folds()` 之前就已經被自己
    的安全網濾掉——這不是「安全」，是把函式自己的輸入資料刪光。"""

    def test_real_consumption_does_not_truncate_panel(self):
        """正式消費（`is_real_consumption=True`）：面板不得被截斷到
        `HOLDOUT_START_DATE` 之前——用一個所有列都 >= `HOLDOUT_START_DATE`
        的合成面板，若函式錯誤地一律截斷，`iter_holdout_folds()` 會拿到
        空面板而找不到任何折，此測試必須能偵測到這個情況。"""
        import scripts.verify.ug_g3_sb7_holdout_report as report_module
        from src.ml.stacking import HOLDOUT_START_DATE

        dates = pd.bdate_range(HOLDOUT_START_DATE, periods=120)
        rows = []
        for d in dates:
            for s in ("A", "B", "C"):
                rows.append({"stock_id": s, "trade_date": d, "target_up_down": 0})
        panel = pd.DataFrame(rows)

        captured = {}

        def fake_verify_panel_sha256(path, target):
            return "fakesha"

        def fake_read_parquet(path):
            return panel.copy()

        def fake_build_holdout_specialist_oof(panel_arg, splitter, boundary, *, target_column):
            captured["panel_rows"] = len(panel_arg)
            captured["panel_min_date"] = panel_arg["trade_date"].min() if len(panel_arg) else None
            raise RuntimeError("stop-here-after-capturing")  # 不需要真的跑完 Specialist 訓練

        with mock.patch.object(report_module, "verify_panel_sha256", side_effect=fake_verify_panel_sha256), \
             mock.patch.object(report_module.pd, "read_parquet", side_effect=fake_read_parquet), \
             mock.patch.object(report_module, "build_splitter", return_value=object()), \
             mock.patch.object(report_module, "_build_holdout_specialist_oof", side_effect=fake_build_holdout_specialist_oof):
            with self.assertRaises(RuntimeError):
                report_module._compute_up_down_observational_auc_holdout(
                    Path("dummy_up_down.parquet"), HOLDOUT_START_DATE, is_real_consumption=True)

        self.assertEqual(captured.get("panel_rows"), len(panel))
        self.assertIsNotNone(captured.get("panel_min_date"))
        self.assertGreaterEqual(captured["panel_min_date"], HOLDOUT_START_DATE)


if __name__ == "__main__":
    unittest.main()
