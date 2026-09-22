# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 2 基準比對腳本（`scripts/verify/ug_g3_sb2a_stage2_baseline_comparison.py`）
的純邏輯單元測試（PO 2026-09-11 複核要求）。

只測 `_values_differ()`／`compare_columns()` 兩個不觸網、不連 DB 的
pure-pandas 函式——本腳本其餘函式皆為唯讀 SQL 讀取，不在本檔測試範圍
（與 `tests/test_sb2a_stock_prices_backfill.py` 對段 1 寫入腳本的測試
範圍劃分一致：邏輯測邏輯，真實庫互動另外唯讀驗證）。
"""
import datetime as dt
import decimal
import inspect
import unittest

import pandas as pd

import scripts.verify.ug_g3_sb2a_stage2_baseline_comparison as baseline_comparison_mod
from scripts.verify.ug_g3_sb2a_stage2_baseline_comparison import (
    compare_columns,
    compute_expected_new_keys,
    split_allowed_diffs,
    _values_differ,
)
from scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap import GAP_TRADE_DATES


class ValuesDifferTests(unittest.TestCase):

    def test_nan_vs_nan_is_not_a_difference(self):
        self.assertFalse(_values_differ(float("nan"), float("nan")))
        self.assertFalse(_values_differ(None, float("nan")))

    def test_nan_vs_non_nan_is_a_difference(self):
        self.assertTrue(_values_differ(float("nan"), 1.0))
        self.assertTrue(_values_differ(1.0, float("nan")))

    def test_numeric_within_tolerance_is_not_a_difference(self):
        self.assertFalse(_values_differ(100.5, 100.5000001))

    def test_numeric_beyond_tolerance_is_a_difference(self):
        self.assertTrue(_values_differ(100.5, 100.6))

    def test_string_equal_is_not_a_difference(self):
        self.assertFalse(_values_differ("SUCCESS", "SUCCESS"))

    def test_string_unequal_is_a_difference(self):
        self.assertTrue(_values_differ("SUCCESS", "SUCCESS_EMPTY"))

    def test_decimal_and_float_same_value_is_not_a_difference(self):
        """審查員 2026-09-11 複核回報：`psycopg2.cursor.fetchone()` 對
        NUMERIC 欄回傳原生 `decimal.Decimal`，原本的 `isinstance(a,
        (int, float))` 判斷漏接，落到字串比較。"""
        self.assertFalse(_values_differ(603.0, decimal.Decimal("603.00")))

    def test_decimal_scientific_notation_and_float_is_not_a_difference(self):
        """極小值（<1e-4）是實際會撞到的案例——Python `float` repr 用科學
        記號、`Decimal` 不用，字串比較會誤判為差異。`daily_ml_features`
        現表就有 2 個這種值（審查員 dry-run 期間查得）。"""
        self.assertFalse(_values_differ(1.5e-05, decimal.Decimal("1.5E-5")))

    def test_decimal_handling_is_load_bearing(self):
        """**known-FAIL 案例**：把 `_values_differ` 的 numeric-type 判斷
        還原成修正前的 `isinstance(a, (int, float))`（不含 `Decimal`），
        證明審查員回報的誤判確實會發生——修正前這兩個案例會被誤判為
        「不同」，不是通過的外觀。手法比照
        `tests/test_sb2a_backfill_candidate_prices_gap.py` 的
        `test_stopping_is_load_bearing`：`inspect.getsource()` 取出本體、
        只動一個判斷式、`exec` 成獨立函式後跑同一套斷言。"""
        source = inspect.getsource(baseline_comparison_mod._values_differ)
        self.assertIn(
            "isinstance(a, _NUMERIC_TYPES) and isinstance(b, _NUMERIC_TYPES)",
            source, "前提：原始碼裡確實用 _NUMERIC_TYPES 判斷可供變異")
        mutated_source = source.replace(
            "isinstance(a, _NUMERIC_TYPES) and isinstance(b, _NUMERIC_TYPES)",
            "isinstance(a, (int, float)) and isinstance(b, (int, float))",
            1,
        )
        self.assertNotEqual(mutated_source, source)

        namespace = dict(vars(baseline_comparison_mod))
        exec(compile(mutated_source, "<mutated_values_differ>", "exec"), namespace)
        mutated_values_differ = namespace["_values_differ"]

        self.assertTrue(
            mutated_values_differ(603.0, decimal.Decimal("603.00")),
            "變異版本（修正前判斷）對 Decimal 會落到字串比較，"
            "誤判 603.0 與 Decimal('603.00') 不同——這正是審查員回報的 bug")
        self.assertTrue(
            mutated_values_differ(1.5e-05, decimal.Decimal("1.5E-5")),
            "變異版本對極小值的誤判同樣會發生（科學記號 vs 一般記號字串不同）")


class CompareColumnsTests(unittest.TestCase):
    """**known-FAIL 要求（PO 2026-09-11）**：一個「永遠不會 FAIL」的比對函式
    不是檢查（`CLAUDE.md` §9A.1）。以下用會被改動的欄位證明它真的抓得到。
    """

    def _mk_frame(self, close_price=100.0, article_count=5):
        return pd.DataFrame([{
            "trade_date": dt.date(2026, 9, 1), "stock_id": "2330",
            "close_price": close_price, "article_count": article_count,
        }])

    def test_identical_frames_produce_no_diff(self):
        df = self._mk_frame()
        diffs = compare_columns(df, df.copy(), ["close_price", "article_count"])
        self.assertEqual(diffs, {})

    def test_changed_value_is_detected(self):
        """**known-FAIL 案例本體**：`df_existing` 的 `close_price` 被改動
        一個位元，`compare_columns` 必須把它列進回傳的差異字典——這正是
        RISK-027 修正前後拿來區分「零差異」與「有差異」的同一套邏輯，
        必須先證明它真的會動。"""
        df_recomputed = self._mk_frame(close_price=100.0)
        df_existing = self._mk_frame(close_price=999.0)  # 刻意改動

        diffs = compare_columns(df_recomputed, df_existing, ["close_price"])

        self.assertIn("close_price", diffs)
        row = diffs["close_price"].iloc[0]
        self.assertEqual(row["recomputed"], 100.0)
        self.assertEqual(row["existing"], 999.0)

    def test_unchanged_column_alongside_changed_column_is_not_flagged(self):
        """只有真的被改動的欄位才出現在回傳字典裡——確認比對是逐欄獨立的，
        不會因為某一欄有差異就連帶誤報其他欄。"""
        df_recomputed = self._mk_frame(close_price=100.0, article_count=5)
        df_existing = self._mk_frame(close_price=999.0, article_count=5)  # 只改 close_price

        diffs = compare_columns(
            df_recomputed, df_existing, ["close_price", "article_count"])

        self.assertIn("close_price", diffs)
        self.assertNotIn("article_count", diffs)

    def test_nan_column_matching_is_not_flagged(self):
        df_recomputed = pd.DataFrame([{
            "trade_date": dt.date(2026, 9, 1), "stock_id": "2330",
            "source_status": float("nan"),
        }])
        df_existing = pd.DataFrame([{
            "trade_date": dt.date(2026, 9, 1), "stock_id": "2330",
            "source_status": float("nan"),
        }])
        diffs = compare_columns(df_recomputed, df_existing, ["source_status"])
        self.assertEqual(diffs, {})

    def test_right_only_key_is_an_orphan_and_reported_separately(self):
        """`daily_ml_features` 有、重算生不出對應列——孤兒列，回傳在
        `__right_only__` 底下（PO 2026-09-11 複核：這永遠是異常，
        與「重算多出的新鍵」不同類，不得混在一起）。"""
        df_recomputed = self._mk_frame()  # 2026-09-01
        df_existing = pd.DataFrame([{
            "trade_date": dt.date(2026, 9, 2),  # 只存在於 daily_ml_features
            "stock_id": "2330", "close_price": 100.0, "article_count": 5,
        }])

        diffs = compare_columns(
            df_recomputed, df_existing, ["close_price", "article_count"])

        self.assertIn("__right_only__", diffs)
        self.assertEqual(len(diffs["__right_only__"]), 1)
        self.assertEqual(diffs["__right_only__"].iloc[0]["trade_date"],
                         dt.date(2026, 9, 2))

    def test_left_only_key_is_a_new_key_and_reported_separately(self):
        """重算有、`daily_ml_features` 沒有——新鍵，回傳在 `__left_only__`
        底下，與孤兒列分開，不阻斷（是否合理由呼叫端對照預期集合判斷）。"""
        df_recomputed = self._mk_frame()  # 2026-09-01，daily_ml_features 沒有
        df_existing = pd.DataFrame(columns=[
            "trade_date", "stock_id", "close_price", "article_count"])

        diffs = compare_columns(
            df_recomputed, df_existing, ["close_price", "article_count"])

        self.assertIn("__left_only__", diffs)
        self.assertNotIn("__right_only__", diffs)
        self.assertEqual(len(diffs["__left_only__"]), 1)


class SplitAllowedDiffsTests(unittest.TestCase):
    """`split_allowed_diffs()`：候選池缺口回補後重跑基線，允許既有台股
    3 檔在 2026-08-21 之後的差異——但**兩個條件都要成立**，只滿足其一
    仍算不允許（PO 2026-09-11 要求：範圍外的差異必須被抓）。
    """

    def _mk_diff_df(self, rows):
        return pd.DataFrame(rows, columns=[
            "trade_date", "stock_id", "recomputed", "existing"])

    def test_allowed_when_both_conditions_met(self):
        df = self._mk_diff_df([
            {"trade_date": dt.date(2026, 8, 22), "stock_id": "2330",
             "recomputed": 1.0, "existing": 2.0},
        ])
        allowed, disallowed = split_allowed_diffs(
            df, dt.date(2026, 8, 21), ("2330", "2382", "6488"))
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(disallowed), 0)

    def test_not_allowed_when_stock_not_in_allow_set(self):
        """**known-FAIL 要求**：日期符合，但股票不在允許集合（例如
        NVDA——那 8 天本來就在美股日曆裡，不該有差異）——仍須判定不允許。
        """
        df = self._mk_diff_df([
            {"trade_date": dt.date(2026, 8, 22), "stock_id": "NVDA",
             "recomputed": 1.0, "existing": 2.0},
        ])
        allowed, disallowed = split_allowed_diffs(
            df, dt.date(2026, 8, 21), ("2330", "2382", "6488"))
        self.assertEqual(len(allowed), 0)
        self.assertEqual(len(disallowed), 1,
                         "股票不在允許集合——即使日期符合，仍須判定不允許")

    def test_not_allowed_when_date_before_cutoff(self):
        """**known-FAIL 要求**：股票在允許集合，但日期早於 `allow_diff_after`
        （例如缺口回補前既有資料的差異）——仍須判定不允許。"""
        df = self._mk_diff_df([
            {"trade_date": dt.date(2026, 8, 20), "stock_id": "2330",
             "recomputed": 1.0, "existing": 2.0},
        ])
        allowed, disallowed = split_allowed_diffs(
            df, dt.date(2026, 8, 21), ("2330", "2382", "6488"))
        self.assertEqual(len(allowed), 0)
        self.assertEqual(len(disallowed), 1,
                         "日期早於允許基準——即使股票符合，仍須判定不允許")

    def test_boundary_date_is_allowed_inclusive(self):
        """`allow_diff_after` 當天（含）本身即為允許範圍下界。"""
        df = self._mk_diff_df([
            {"trade_date": dt.date(2026, 8, 21), "stock_id": "2330",
             "recomputed": 1.0, "existing": 2.0},
        ])
        allowed, disallowed = split_allowed_diffs(
            df, dt.date(2026, 8, 21), ("2330",))
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(disallowed), 0)

    def test_no_allow_params_means_nothing_allowed(self):
        """未提供 `--allow-diff-after`／`--allow-diff-stocks` 時（皆為
        `None`），一律視為不允許——不得因為忘記傳參數就悄悄放行差異。"""
        df = self._mk_diff_df([
            {"trade_date": dt.date(2026, 8, 22), "stock_id": "2330",
             "recomputed": 1.0, "existing": 2.0},
        ])
        allowed, disallowed = split_allowed_diffs(df, None, None)
        self.assertEqual(len(allowed), 0)
        self.assertEqual(len(disallowed), 1)

    def test_mixed_rows_partition_correctly(self):
        """混合列：允許、股票不符、日期不符三種各一列，確認 `split_allowed_diffs`
        逐列獨立判定，不會因為批次裡有一列允許就連帶放行其他列。"""
        df = self._mk_diff_df([
            {"trade_date": dt.date(2026, 8, 22), "stock_id": "2330",
             "recomputed": 1.0, "existing": 2.0},   # 允許
            {"trade_date": dt.date(2026, 8, 22), "stock_id": "NVDA",
             "recomputed": 1.0, "existing": 2.0},   # 股票不符
            {"trade_date": dt.date(2026, 8, 19), "stock_id": "2382",
             "recomputed": 1.0, "existing": 2.0},   # 日期不符
        ])
        allowed, disallowed = split_allowed_diffs(
            df, dt.date(2026, 8, 21), ("2330", "2382", "6488"))
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(disallowed), 2)


class ComputeExpectedNewKeysTests(unittest.TestCase):
    """`compute_expected_new_keys()`：段 1 先於段 2 執行時，重算比
    `daily_ml_features` 多出的鍵應恰好等於「比對股票子集 × 缺口交易日，
    扣掉既有鍵」（PO 2026-09-11 要求）。"""

    def _mk_existing(self, rows):
        return pd.DataFrame(rows, columns=["trade_date", "stock_id"])

    def test_expected_new_keys_is_gap_dates_when_existing_has_none(self):
        df_existing = self._mk_existing([])
        expected = compute_expected_new_keys(("2330",), df_existing)
        gap_dates = {dt.date.fromisoformat(d) for d in GAP_TRADE_DATES}
        self.assertEqual(expected, {("2330", d) for d in gap_dates})

    def test_existing_gap_date_is_excluded_from_expected(self):
        """2330／2382 的 2026-09-01／09-02 在缺口回補前就已存在（§3.2 登記
        的既知批次覆蓋缺口）——那兩天不是「新鍵」，必須從預期集合排除。"""
        existing_date = dt.date.fromisoformat(GAP_TRADE_DATES[-2])  # 2026-09-01
        df_existing = self._mk_existing([
            {"trade_date": existing_date, "stock_id": "2330"},
        ])
        expected = compute_expected_new_keys(("2330",), df_existing)
        self.assertNotIn(("2330", existing_date), expected)
        self.assertEqual(len(expected), len(GAP_TRADE_DATES) - 1)

    def test_actual_left_only_matching_expected_has_no_mismatch(self):
        """整合情境：`compare_columns()` 的 `__left_only__` 恰好等於
        `compute_expected_new_keys()` 算出的集合時，missing／extra 皆為
        空——這是 main() 用來判斷是否放行的邏輯，這裡直接重跑同一套判斷。
        """
        gap_dates = [dt.date.fromisoformat(d) for d in GAP_TRADE_DATES]
        df_recomputed = pd.DataFrame([
            {"trade_date": d, "stock_id": "2330", "close_price": 100.0}
            for d in gap_dates
        ])
        df_existing = pd.DataFrame(
            columns=["trade_date", "stock_id", "close_price"])

        diffs = compare_columns(df_recomputed, df_existing, ["close_price"])
        expected = compute_expected_new_keys(("2330",), df_existing)
        actual = set(zip(diffs["__left_only__"]["stock_id"],
                         diffs["__left_only__"]["trade_date"]))

        self.assertEqual(actual, expected)
        self.assertEqual(expected - actual, set())
        self.assertEqual(actual - expected, set())

    def test_extra_left_only_key_outside_expected_is_detected(self):
        """**known-FAIL 案例（PO 2026-09-11 要求）**：重算多出一個不在缺口
        清單內的日期（例如 08-22，非缺口日）——代表比對方法或資料本身
        有問題，`extra`（main() 據此阻斷）必須非空，不得被放行。"""
        gap_dates = [dt.date.fromisoformat(d) for d in GAP_TRADE_DATES]
        extra_date = dt.date(2026, 8, 22)  # 不在 GAP_TRADE_DATES 內
        df_recomputed = pd.DataFrame([
            {"trade_date": d, "stock_id": "2330", "close_price": 100.0}
            for d in gap_dates + [extra_date]
        ])
        df_existing = pd.DataFrame(
            columns=["trade_date", "stock_id", "close_price"])

        diffs = compare_columns(df_recomputed, df_existing, ["close_price"])
        expected = compute_expected_new_keys(("2330",), df_existing)
        actual = set(zip(diffs["__left_only__"]["stock_id"],
                         diffs["__left_only__"]["trade_date"]))

        extra = actual - expected
        self.assertEqual(
            extra, {("2330", extra_date)},
            "多出的 08-22 必須被判定為「預期沒有」，main() 才會據此阻斷")


if __name__ == "__main__":
    unittest.main()
