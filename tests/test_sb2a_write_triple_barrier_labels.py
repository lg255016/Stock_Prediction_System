# -*- coding: utf-8 -*-
"""
`scripts/verify/ug_g3_sb2a_write_triple_barrier_labels.py` 的單元測試
（PO 2026-09-11 複核要求：合成缺口的 known-FAIL、NVDA 對照組、批次失敗
即停、commit 前三道檢查、預覽零寫入、常數過期守衛）。

純邏輯測邏輯，不連真實庫、不觸網——與段 2 的測試範圍劃分一致。
"""
import contextlib
import datetime as dt
import inspect
import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from scripts.verify.ug_g3_sb2a_write_triple_barrier_labels import (
    _label_key,
    reconstruct_pre_rerun_prices,
    compute_expected_relabel_impact,
    split_into_batches,
    assert_batch_stock_subset,
    write_one_batch,
    verify_batch_after_write,
    run_labels_backfill,
    check_label_consistency_invariant,
    check_full_table_recompute_equality,
    check_impact_subset_and_complement,
    check_total_row_count,
    check_existing_label_counts,
    compute_risk025_table,
    compute_label_reconciliation,
    HOLDING_PERIOD,
    TOTAL_ROWS_EXPECTED,
    EXISTING_LABEL_COUNTS_BEFORE,
    COMPARE_STOCK_IDS,
    CONTROL_STOCK_ID,
)


class LabelKeyTests(unittest.TestCase):

    def test_both_nan_normalize_to_none_none(self):
        self.assertEqual(_label_key(float("nan"), float("nan")), (None, None))

    def test_real_value_normalizes_tb_to_int(self):
        self.assertEqual(_label_key(1.0, None), (1, None))
        self.assertEqual(_label_key(-1.0, None), (-1, None))
        self.assertEqual(_label_key(0.0, None), (0, None))

    def test_reason_string_preserved(self):
        self.assertEqual(_label_key(float("nan"), "no_entry"), (None, "no_entry"))


class ReconstructPreRerunPricesTests(unittest.TestCase):

    def _mk_df(self):
        return pd.DataFrame({
            "stock_id": ["2330", "2330", "6488", "NVDA"],
            "trade_date": [dt.date(2026, 8, 24), dt.date(2026, 8, 20),
                            dt.date(2026, 8, 24), dt.date(2026, 8, 24)],
            "created_at": [
                pd.Timestamp("2026-09-11 08:00"),  # 2330 今日新插入
                pd.Timestamp("2026-09-01 08:00"),  # 2330 舊列
                pd.Timestamp("2026-09-11 08:00"),  # 6488 今日新插入
                pd.Timestamp("2026-08-24 08:00"),  # NVDA 不受影響，非目標股票
            ],
        })

    def test_excludes_only_target_stocks_new_rows(self):
        df = self._mk_df()
        result = reconstruct_pre_rerun_prices(df, stock_ids=("2330", "6488"))
        # 2330 的新列（08-24）被排除，舊列（08-20）保留；6488 新列被排除；
        # NVDA 不是目標股票，即使 created_at 落在同一天也不排除。
        kept_keys = set(zip(result["stock_id"], result["trade_date"]))
        self.assertNotIn(("2330", dt.date(2026, 8, 24)), kept_keys)
        self.assertIn(("2330", dt.date(2026, 8, 20)), kept_keys)
        self.assertNotIn(("6488", dt.date(2026, 8, 24)), kept_keys)
        self.assertIn(("NVDA", dt.date(2026, 8, 24)), kept_keys)


class ComputeExpectedRelabelImpactTests(unittest.TestCase):
    """合成一個人工缺口，手算 H=5 下的正確受影響集合，驗證函式輸出恰好
    相符；known-FAIL 把缺口位置移一格，集合必須改變（PO 2026-09-11
    複核明確要求）。"""

    def _build_synthetic_prices(self, gap_positions):
        """14 個交易日（2026-01-01～01-14，位置 0~13）。除位置 7
        （01-08）外全部平盤（open=high=low=100，anchor 內不觸線）；
        位置 7 的 high_price=200（尖峰，必定觸上界）。`gap_positions`
        （2 個位置）標記為「今日新插入」（created_at 落在 cutoff 之後），
        其餘標記為舊列。"""
        dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(14)]
        rows = []
        for pos, d in enumerate(dates):
            high = 200.0 if pos == 7 else 100.0
            created = (pd.Timestamp("2026-09-11 08:00") if pos in gap_positions
                       else pd.Timestamp("2026-09-01 08:00"))
            rows.append({
                "stock_id": "TEST", "trade_date": d,
                "open_price": 100.0, "high_price": high, "low_price": 100.0,
                "created_at": created,
            })
        return pd.DataFrame(rows)

    def test_synthetic_gap_impact_set_matches_hand_computed_expectation(self):
        """缺口在位置 5、6（01-06、01-07）。手算結果（見測試檔內文推導）：
        OLD（12 列，缺口排除）序列裡，尖峰落在 old-position 5，使 old-
        position 0~4（對應 01-01~01-05）都因窗口含尖峰而標 +1；NEW（14
        列）序列裡，尖峰在 position 7，使 position 2~6（對應 01-03~01-07）
        標 +1。兩邊在 01-01／01-02 的標籤不同（OLD +1 vs NEW Timeout），
        01-03/04/05 兩邊剛好都是 +1（窗口內容不同但結果巧合相同，正確
        不該被判為差異——這正是「子集不是相等」的證明），01-06／01-07
        只在 NEW 存在（新列，自動算差異）。"""
        df_prices = self._build_synthetic_prices(gap_positions={5, 6})
        impact = compute_expected_relabel_impact(df_prices, stock_ids=("TEST",))

        expected = {
            ("TEST", dt.date(2026, 1, 1)),
            ("TEST", dt.date(2026, 1, 2)),
            ("TEST", dt.date(2026, 1, 6)),
            ("TEST", dt.date(2026, 1, 7)),
        }
        self.assertEqual(impact, expected)
        # 明確驗證「窗口變了但結果巧合相同」的三天沒有被誤判為差異——
        # 這是子集關係設計最容易寫錯成「凡窗口改變就算差異」的地方。
        for d in (dt.date(2026, 1, 3), dt.date(2026, 1, 4), dt.date(2026, 1, 5)):
            self.assertNotIn(("TEST", d), impact,
                              f"{d}：兩邊窗口都含尖峰、結果巧合相同 +1，不該被判為差異")

    def test_known_fail_shifting_gap_by_one_position_changes_impact_set(self):
        """**known-FAIL 案例**：把缺口位置從 {5,6} 移一格到 {6,7}——尖峰
        （position 7）原本在缺口內，位移後缺口涵蓋了尖峰本身，受影響
        集合必須不同（不是巧合相同的另一組數字）。"""
        df_original = self._build_synthetic_prices(gap_positions={5, 6})
        df_shifted = self._build_synthetic_prices(gap_positions={6, 7})

        impact_original = compute_expected_relabel_impact(df_original, stock_ids=("TEST",))
        impact_shifted = compute_expected_relabel_impact(df_shifted, stock_ids=("TEST",))

        self.assertNotEqual(
            impact_original, impact_shifted,
            "缺口位置位移一格後，受影響集合必須改變——若相同，代表"
            "compute_expected_relabel_impact 對缺口位置不敏感，是假通過")


class ControlStockZeroDiffTests(unittest.TestCase):
    """NVDA 對照組：不在 COMPARE_STOCK_IDS 內，`compute_expected_relabel_impact`
    的預期集合不含任何 NVDA 鍵；`check_impact_subset_and_complement` 的
    互補集合檢查必須把 NVDA 全部納入零差異範圍。"""

    def test_control_stock_never_in_expected_impact_keys(self):
        df_prices = pd.DataFrame({
            "stock_id": ["NVDA"] * 3,
            "trade_date": [dt.date(2026, 1, 1), dt.date(2026, 1, 2), dt.date(2026, 1, 3)],
            "open_price": [100.0] * 3, "high_price": [100.0] * 3, "low_price": [100.0] * 3,
            "created_at": [pd.Timestamp("2026-09-11 08:00")] * 3,
        })
        impact = compute_expected_relabel_impact(df_prices, stock_ids=COMPARE_STOCK_IDS)
        self.assertEqual(impact, set(), "NVDA 不在 COMPARE_STOCK_IDS，不應出現在預期受影響集合")

    def test_complement_check_flags_nvda_label_change_as_violation(self):
        """known-FAIL：若 NVDA（不在預期集合內）標籤在寫入前後有變動，
        `check_impact_subset_and_complement` 必須判為互補集合違規。"""
        before = {("NVDA", dt.date(2026, 1, 1)): (0, None)}
        after = {("NVDA", dt.date(2026, 1, 1)): (1, None)}  # 不該變但變了
        expected_impact_keys = set()  # NVDA 從不在預期集合
        four_stock_keys = {("NVDA", dt.date(2026, 1, 1))}

        ok, actual_diff, outside_expected, complement_violations, missing, is_equal = (
            check_impact_subset_and_complement(
                before, after, expected_impact_keys, four_stock_keys))

        self.assertFalse(ok)
        self.assertIn(("NVDA", dt.date(2026, 1, 1)), complement_violations)

    def test_complement_check_passes_when_only_expected_keys_change(self):
        before = {
            ("2330", dt.date(2026, 1, 1)): (0, None),
            ("NVDA", dt.date(2026, 1, 1)): (1, None),
        }
        after = {
            ("2330", dt.date(2026, 1, 1)): (1, None),  # 在預期集合內，允許變
            ("NVDA", dt.date(2026, 1, 1)): (1, None),  # 不變
        }
        expected_impact_keys = {("2330", dt.date(2026, 1, 1))}
        four_stock_keys = set(before.keys())

        ok, actual_diff, outside_expected, complement_violations, missing, is_equal = (
            check_impact_subset_and_complement(
                before, after, expected_impact_keys, four_stock_keys))

        self.assertTrue(ok)
        self.assertTrue(is_equal)
        self.assertEqual(outside_expected, set())
        self.assertEqual(missing, set())
        self.assertEqual(complement_violations, set())

    def test_known_fail_strict_subset_without_equality_now_fails(self):
        """**known-FAIL 案例（PO 2026-09-11 複核第二輪收緊）**：實際差異
        是預期集合的**真子集**（沒有範圍外差異、也沒有互補違規）——舊版
        邏輯（只查子集＋互補）會判定 PASS，但新版要求相等，必須 FAIL，
        因為這代表「預期會變但實際沒變」的鍵存在，那本身就是需要被發現
        的異常（可能是 SB1 當時的標籤來源與本次重算邏輯不一致）。"""
        before = {
            ("2330", dt.date(2026, 1, 1)): (0, None),
            ("2330", dt.date(2026, 1, 2)): (0, None),
        }
        after = {
            ("2330", dt.date(2026, 1, 1)): (1, None),  # 有變
            ("2330", dt.date(2026, 1, 2)): (0, None),  # 預期會變，但沒變
        }
        expected_impact_keys = {
            ("2330", dt.date(2026, 1, 1)), ("2330", dt.date(2026, 1, 2)),
        }
        four_stock_keys = set(before.keys())

        ok, actual_diff, outside_expected, complement_violations, missing, is_equal = (
            check_impact_subset_and_complement(
                before, after, expected_impact_keys, four_stock_keys))

        self.assertEqual(outside_expected, set(), "前提：確實沒有範圍外差異（純子集情境）")
        self.assertEqual(complement_violations, set(), "前提：確實沒有互補違規")
        self.assertFalse(is_equal)
        self.assertIn(("2330", dt.date(2026, 1, 2)), missing)
        self.assertFalse(ok, "純子集（不相等）在新版邏輯下必須 FAIL，不能被子集關係吞掉")


class SplitIntoBatchesTests(unittest.TestCase):

    def test_disjoint_and_covers_all(self):
        ids = [str(i) for i in range(459)]
        batches = split_into_batches(ids, batch_size=50)
        flat = [s for b in batches for s in b]
        self.assertEqual(sorted(flat), sorted(ids))
        self.assertEqual(len(flat), len(set(flat)))

    def test_batch_count_459_stocks(self):
        ids = [str(i) for i in range(459)]
        batches = split_into_batches(ids, batch_size=50)
        self.assertEqual(len(batches), 10)
        self.assertEqual(len(batches[-1]), 9)


class AssertBatchStockSubsetTests(unittest.TestCase):

    def test_passes_when_subset(self):
        df = pd.DataFrame({"stock_id": ["2330", "2330"]})
        assert_batch_stock_subset(df, ["2330", "2382"])

    def test_fails_on_foreign_stock(self):
        df = pd.DataFrame({"stock_id": ["2330", "9999"]})
        with self.assertRaises(AssertionError):
            assert_batch_stock_subset(df, ["2330"])


class WriteOneBatchTests(unittest.TestCase):

    def _mk_result(self):
        return pd.DataFrame({
            "stock_id": ["2330", "2330"],
            "trade_date": [dt.date(2026, 1, 1), dt.date(2026, 1, 2)],
            "target_triple_barrier": [1.0, np.nan],
            "label_reason": [np.nan, "no_entry"],
        })

    def test_execute_values_called_with_returning_and_count_matches(self):
        result = self._mk_result()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor

        with patch(
            "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.execute_values",
            return_value=[("2330",), ("2330",)],
        ) as mock_ev:
            n = write_one_batch(conn, ["2330"], result)

        self.assertEqual(n, 2)
        self.assertTrue(mock_ev.called)
        _, kwargs = mock_ev.call_args
        self.assertTrue(kwargs.get("fetch"), "必須用 fetch=True 才能拿到 RETURNING 結果")

    def test_assertion_failure_prevents_execute_values_call(self):
        """known-FAIL：批次含未授權股票時，寫入前斷言必須先擋下，
        `execute_values` 完全不得被呼叫。"""
        result = pd.DataFrame({
            "stock_id": ["9999"], "trade_date": [dt.date(2026, 1, 1)],
            "target_triple_barrier": [1.0], "label_reason": [np.nan],
        })
        conn = MagicMock()
        with patch(
            "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.execute_values"
        ) as mock_ev:
            with self.assertRaises(AssertionError):
                write_one_batch(conn, ["2330"], result)
        mock_ev.assert_not_called()


class VerifyBatchAfterWriteTests(unittest.TestCase):

    def _mk_result(self):
        return pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 1, 1)],
            "target_triple_barrier": [1.0], "label_reason": [np.nan],
        })

    def test_returning_count_mismatch_is_fail(self):
        """known-FAIL：(a) RETURNING 計數與批次列數不符時必須立即 FAIL，
        不得往下做 (b)(c)。"""
        result = self._mk_result()
        conn = MagicMock()
        ok, detail = verify_batch_after_write(conn, ["2330"], result, n_updated_returned=0)
        self.assertFalse(ok)
        self.assertIn("(a)", detail)

    def test_all_three_checks_pass(self):
        result = self._mk_result()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        # (b) 分布快篩：(stock_id, reason_or___LABELED__) -> count
        # (c) 逐列讀回：stock_id, trade_date, tb, reason
        cursor.fetchall.side_effect = [
            [("2330", "__LABELED__", 1)],
            [("2330", dt.date(2026, 1, 1), 1, None)],
        ]
        ok, detail = verify_batch_after_write(conn, ["2330"], result, n_updated_returned=1)
        self.assertTrue(ok)
        self.assertEqual(detail, "OK")

    def test_exact_row_mismatch_is_fail(self):
        """known-FAIL：(a)(b) 皆通過，但 (c) 逐列比對的實際值與預期不符
        （target_triple_barrier 對調成 -1）時必須 FAIL，且說明指出是 (c)。"""
        result = self._mk_result()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            [("2330", "__LABELED__", 1)],
            [("2330", dt.date(2026, 1, 1), -1, None)],  # 應為 1，寫錯成 -1
        ]
        ok, detail = verify_batch_after_write(conn, ["2330"], result, n_updated_returned=1)
        self.assertFalse(ok)
        self.assertIn("(c)", detail)


class RunLabelsBackfillTests(unittest.TestCase):

    def _mk_df(self, stock_ids):
        return pd.DataFrame({
            "stock_id": stock_ids,
            "trade_date": [dt.date(2026, 1, 1)] * len(stock_ids),
            "target_triple_barrier": [1.0] * len(stock_ids),
            "label_reason": [np.nan] * len(stock_ids),
        })

    def test_batch_failure_rolls_back_and_stops(self):
        """**known-FAIL 要求**：批次 2 核對失敗時，(1) 該批 rollback
        (2) 批次 3 完全不得被 `write_one_batch` 呼叫。"""
        conn = MagicMock()
        batches = [["A"], ["B"], ["C"]]
        df = self._mk_df(["A", "B", "C"])

        write_calls = []

        def fake_write(conn_, batch_ids, batch_df):
            write_calls.append(batch_ids[0])
            return len(batch_df)

        results = {"A": (True, "OK"), "B": (False, "(c) 不符"), "C": (True, "OK")}

        def fake_verify(conn_, batch_ids, batch_df, n):
            return results[batch_ids[0]]

        with patch(
            "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.write_one_batch",
            side_effect=fake_write,
        ), patch(
            "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.verify_batch_after_write",
            side_effect=fake_verify,
        ):
            completed, failed_at = run_labels_backfill(conn, batches, df)

        self.assertEqual(completed, [1])
        self.assertEqual(failed_at, 2)
        self.assertEqual(write_calls, ["A", "B"], "批次 3 不得被呼叫")
        conn.rollback.assert_called_once()
        self.assertEqual(conn.commit.call_count, 1, "只有批次 1 該 commit")

    def test_all_batches_succeed_commits_each(self):
        conn = MagicMock()
        batches = [["A"], ["B"]]
        df = self._mk_df(["A", "B"])

        with patch(
            "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.write_one_batch",
            return_value=1,
        ), patch(
            "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.verify_batch_after_write",
            return_value=(True, "OK"),
        ):
            completed, failed_at = run_labels_backfill(conn, batches, df)

        self.assertEqual(completed, [1, 2])
        self.assertIsNone(failed_at)
        self.assertEqual(conn.commit.call_count, 2)
        conn.rollback.assert_not_called()


class CheckLabelConsistencyInvariantTests(unittest.TestCase):

    def test_zero_violations_passes(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = (0,)
        ok, n = check_label_consistency_invariant(conn)
        self.assertTrue(ok)
        self.assertEqual(n, 0)

    def test_nonzero_violations_fails(self):
        """known-FAIL：查到違規列時必須回傳 False。"""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = (3,)
        ok, n = check_label_consistency_invariant(conn)
        self.assertFalse(ok)
        self.assertEqual(n, 3)


class CheckFullTableRecomputeEqualityTests(unittest.TestCase):

    def test_matching_tables_pass(self):
        df_result = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 1, 1)],
            "target_triple_barrier": [1.0], "label_reason": [np.nan],
        })
        conn = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 1, 1)],
            "target_triple_barrier": [1], "label_reason": [None],
        })):
            ok, mismatches = check_full_table_recompute_equality(conn, df_result)
        self.assertTrue(ok)
        self.assertEqual(mismatches, [])

    def test_mismatched_value_detected(self):
        """known-FAIL：庫內值與重算不符時必須列出該鍵。"""
        df_result = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 1, 1)],
            "target_triple_barrier": [1.0], "label_reason": [np.nan],
        })
        conn = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 1, 1)],
            "target_triple_barrier": [-1], "label_reason": [None],  # 應為 1
        })):
            ok, mismatches = check_full_table_recompute_equality(conn, df_result)
        self.assertFalse(ok)
        self.assertIn(("2330", dt.date(2026, 1, 1)), mismatches)


class ComputeLabelReconciliationTests(unittest.TestCase):
    """對帳基準值（只揭露不把關）的算術正確性——PO 2026-09-11 複核第二輪
    要求。用一檔乾淨序列（無 NaN 價格）驗證 `no_entry`／`insufficient_data`
    基準恰好等於「1 檔 × 對應筆數」，沒有多算或漏算。"""

    def test_clean_single_stock_matches_tail_baseline_exactly(self):
        n = 10  # 10 列，足夠有 holding_period=5 的尾端結構
        dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(n)]
        df_prices = pd.DataFrame({
            "stock_id": ["TEST"] * n, "trade_date": dates,
            "open_price": [100.0] * n, "high_price": [100.0] * n,
            "low_price": [100.0] * n,
        })
        from src.ml.triple_barrier import generate_triple_barrier_labels
        df_result = generate_triple_barrier_labels(df_prices)

        recon = compute_label_reconciliation(df_prices, df_result)

        self.assertEqual(recon["n_stocks"], 1)
        # 乾淨序列無 NaN anchor，no_entry 應恰好等於基準（1 檔 × 1 尾列）
        self.assertEqual(recon["actual_no_entry"], recon["expected_no_entry_baseline"])
        self.assertEqual(recon["expected_no_entry_baseline"], 1)
        # 無窗口 NaN，insufficient_data 應恰好等於尾端基準（1 檔 × (H-1) 列）
        self.assertEqual(recon["actual_insufficient_data"],
                          recon["expected_insufficient_tail_baseline"])
        self.assertEqual(recon["expected_insufficient_tail_baseline"], HOLDING_PERIOD - 1)
        self.assertEqual(recon["window_nan_caused_insufficient"], 0)


class ComputeRisk025TableTests(unittest.TestCase):
    """吃 DataFrame，不吃 DB 連線——唯讀預覽才能看到『將會怎樣』而不是
    寫入前的舊值（PO 2026-09-11 複核期間，真實 dry-run 才發現：若吃
    conn 查 DB，預覽階段 455 檔新股 labeled_n=0，這張表看起來只有 3～4
    檔有標籤，證明不了任何事）。"""

    def test_timeout_ratio_computed_per_stock(self):
        df = pd.DataFrame({
            "stock_id": ["A", "A", "A", "A", "B", "B"],
            "target_triple_barrier": [0, 0, 1, -1, 1, -1],  # A: 2/4=0.5, B: 0/2=0.0
        })
        full, below = compute_risk025_table(df, threshold=0.05)
        a_ratio = full.loc[full["stock_id"] == "A", "timeout_ratio"].iloc[0]
        b_ratio = full.loc[full["stock_id"] == "B", "timeout_ratio"].iloc[0]
        self.assertAlmostEqual(a_ratio, 0.5)
        self.assertAlmostEqual(b_ratio, 0.0)
        self.assertIn("B", set(below["stock_id"]))
        self.assertNotIn("A", set(below["stock_id"]))

    def test_unlabeled_stock_excluded_not_divide_by_zero(self):
        """known-FAIL 對照：全 NaN（未標籤新股）的 `labeled_n=0`，
        不該讓 ratio 變成 0（那會被誤判為『全部觸線，Timeout 比例 0%』，
        結構上跟『這檔根本沒標籤』是完全不同的事）。"""
        df = pd.DataFrame({
            "stock_id": ["C", "C"],
            "target_triple_barrier": [np.nan, np.nan],
        })
        full, below = compute_risk025_table(df, threshold=0.05)
        ratio = full.loc[full["stock_id"] == "C", "timeout_ratio"].iloc[0]
        self.assertTrue(pd.isna(ratio), "labeled_n=0 時 ratio 必須是 NaN，不是 0")
        self.assertNotIn("C", set(below["stock_id"]), "NaN ratio 不該被 < threshold 誤判為 True")


class PreviewZeroWriteTests(unittest.TestCase):
    """唯讀預覽模式的零寫入保證——`main()` 的 `if not write: ...; return`
    必須在任何 `run_labels_backfill` 呼叫之前。"""

    class _SentinelWriteCalled(Exception):
        pass

    def _run_with_mocks(self, write, mutate=False):
        import scripts.verify.ug_g3_sb2a_write_triple_barrier_labels as mod

        df_prices_fake = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 1, 1)],
            "open_price": [100.0], "high_price": [100.0], "low_price": [100.0],
            "created_at": [pd.Timestamp("2026-01-01")],
        })

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "POSTGRES_DB": "testdb", "POSTGRES_USER": "u", "POSTGRES_PASSWORD": "<test>",
            }))
            mock_psycopg2 = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels.psycopg2"))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels."
                "fetch_all_prices_with_created_at", return_value=df_prices_fake))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels."
                "compute_expected_relabel_impact", return_value=set()))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels."
                "preview_labels_backfill"))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels."
                "check_total_row_count", return_value=(True, TOTAL_ROWS_EXPECTED)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels."
                "check_existing_label_counts",
                return_value=(True, EXISTING_LABEL_COUNTS_BEFORE)))
            stack.enter_context(patch("builtins.input", return_value="testdb"))
            mock_run_backfill = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_write_triple_barrier_labels."
                "run_labels_backfill", side_effect=self._SentinelWriteCalled))

            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            mock_conn.cursor.return_value.fetchone.return_value = ("testdb", "u", 5432)

            if mutate:
                source = inspect.getsource(mod.main)
                assert "if not write:" in source
                mutated_source = source.replace("if not write:", "if False:", 1)
                assert mutated_source != source
                namespace = dict(vars(mod))
                exec(compile(mutated_source, "<mutated_main>", "exec"), namespace)
                main_func = namespace["main"]
            else:
                main_func = mod.main

            reached_write_path = False
            try:
                main_func(write=write, backup_path=None)
            except self._SentinelWriteCalled:
                reached_write_path = True

            return reached_write_path, mock_run_backfill

    def test_preview_mode_never_reaches_write_path(self):
        reached, mock_run_backfill = self._run_with_mocks(write=False, mutate=False)
        self.assertFalse(reached)
        mock_run_backfill.assert_not_called()

    def test_guard_removed_is_load_bearing(self):
        """**known-FAIL 案例**：把 `if not write:` 改成 `if False:`，
        證明 guard 移除後即使 write=False 也會進入 run_labels_backfill。"""
        reached, _ = self._run_with_mocks(write=False, mutate=True)
        self.assertTrue(reached)


if __name__ == "__main__":
    unittest.main()
