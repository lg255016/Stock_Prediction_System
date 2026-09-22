# -*- coding: utf-8 -*-
"""
`scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py` 的單元測試。

純邏輯測試為主（不連真實庫）：差異集攤平／相等斷言／向量化鍵篩選／
寫入 record 轉型／前置守衛。`LoadOldFeatureAggregatorClassTests` 例外
——它是本檔案設計核心的驗證對象本身（「舊版真的是舊版」），刻意用真實
`git show` 對本 repo 既有的兩個 commit（RED 測試 commit 與修復 commit）
做整合測試，不用 mock 取代（mock 掉 git 或 exec 會讓這條測試失去意義：
它要驗證的正是「載入路徑指向哪個 commit，行為就對應哪個 commit」）。
"""
import datetime as dt
import unittest
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from scripts.verify.ug_g3_sb2a_stage2_rerun_risk027 import (
    COMMENT_COLUMNS,
    EXISTING_LABEL_COUNTS,
    OLD_FEATURE_AGGREGATOR_COMMIT,
    PRICE_DERIVED_COLUMNS,
    SENTIMENT_WRITE_COLUMNS,
    TOTAL_ROWS_EXPECTED,
    assert_expected_equals_actual,
    build_write_records,
    check_label_counts,
    check_total_row_count,
    compute_actual_diff,
    compute_expected_impact,
    diff_keys_and_columns,
    load_old_feature_aggregator_class,
    select_by_keys,
)


class ConstantsTests(unittest.TestCase):

    def test_column_split_matches_25_column_contract(self):
        self.assertEqual(len(PRICE_DERIVED_COLUMNS), 13)
        self.assertEqual(len(SENTIMENT_WRITE_COLUMNS), 12)
        self.assertTrue(set(COMMENT_COLUMNS) <= set(SENTIMENT_WRITE_COLUMNS))
        self.assertEqual(
            set(PRICE_DERIVED_COLUMNS) & set(SENTIMENT_WRITE_COLUMNS), set())


class DiffKeysAndColumnsTests(unittest.TestCase):

    def _diffs(self, rows_by_col):
        """建構 `compare_columns()` 風格的輸出：
        `rows_by_col = {"colA": [("2330", d1), ("6488", d2)], ...}`。"""
        diffs = {}
        for col, keys in rows_by_col.items():
            diffs[col] = pd.DataFrame({
                "stock_id": [k[0] for k in keys],
                "trade_date": [k[1] for k in keys],
                "recomputed": [1] * len(keys),
                "existing": [0] * len(keys),
            })
        return diffs

    def test_flattens_to_key_to_columns_mapping(self):
        d1, d2 = dt.date(2026, 2, 23), dt.date(2026, 3, 2)
        diffs = self._diffs({
            "article_count": [("2330", d1)],
            "sentiment_mean": [("2330", d1), ("NVDA", d2)],
        })
        result = diff_keys_and_columns(diffs, ("article_count", "sentiment_mean"))
        self.assertEqual(result, {
            ("2330", d1): frozenset({"article_count", "sentiment_mean"}),
            ("NVDA", d2): frozenset({"sentiment_mean"}),
        })

    def test_empty_diffs_yields_empty_mapping(self):
        self.assertEqual(diff_keys_and_columns({}, ("article_count",)), {})

    def test_ignores_columns_not_requested(self):
        d1 = dt.date(2026, 2, 23)
        diffs = self._diffs({"article_count": [("2330", d1)]})
        result = diff_keys_and_columns(diffs, ("sentiment_mean",))
        self.assertEqual(result, {})


class AssertExpectedEqualsActualTests(unittest.TestCase):

    def test_identical_mappings_pass(self):
        m = {("2330", dt.date(2026, 2, 23)): frozenset({"article_count"})}
        ok, detail = assert_expected_equals_actual(m, dict(m))
        self.assertTrue(ok)
        self.assertEqual(detail["only_in_expected"], set())
        self.assertEqual(detail["only_in_actual"], set())
        self.assertEqual(detail["column_mismatches"], {})

    def test_key_only_in_expected_fails(self):
        k = ("2330", dt.date(2026, 2, 23))
        expected = {k: frozenset({"article_count"})}
        actual = {}
        ok, detail = assert_expected_equals_actual(expected, actual)
        self.assertFalse(ok)
        self.assertEqual(detail["only_in_expected"], {k})
        self.assertEqual(detail["only_in_actual"], set())

    def test_key_only_in_actual_fails(self):
        k = ("2330", dt.date(2026, 2, 23))
        expected = {}
        actual = {k: frozenset({"article_count"})}
        ok, detail = assert_expected_equals_actual(expected, actual)
        self.assertFalse(ok)
        self.assertEqual(detail["only_in_actual"], {k})

    def test_same_key_different_columns_fails(self):
        k = ("2330", dt.date(2026, 2, 23))
        expected = {k: frozenset({"article_count", "sentiment_mean"})}
        actual = {k: frozenset({"article_count"})}
        ok, detail = assert_expected_equals_actual(expected, actual)
        self.assertFalse(ok)
        self.assertIn(k, detail["column_mismatches"])
        self.assertEqual(
            detail["column_mismatches"][k],
            (frozenset({"article_count", "sentiment_mean"}), frozenset({"article_count"})))

    def test_both_empty_passes(self):
        ok, detail = assert_expected_equals_actual({}, {})
        self.assertTrue(ok)


class SelectByKeysTests(unittest.TestCase):

    def _mk_df(self):
        return pd.DataFrame({
            "stock_id": ["2330", "2330", "NVDA"],
            "trade_date": [dt.date(2026, 2, 23), dt.date(2026, 2, 24), dt.date(2026, 1, 20)],
            "value": [1, 2, 3],
        })

    def test_filters_to_matching_keys_only(self):
        df = self._mk_df()
        keys = {("2330", dt.date(2026, 2, 23)), ("NVDA", dt.date(2026, 1, 20))}
        result = select_by_keys(df, keys)
        self.assertEqual(sorted(result["value"].tolist()), [1, 3])

    def test_empty_keys_yields_empty_result(self):
        df = self._mk_df()
        result = select_by_keys(df, set())
        self.assertTrue(result.empty)

    def test_no_matches_yields_empty_result(self):
        df = self._mk_df()
        result = select_by_keys(df, {("6488", dt.date(2099, 1, 1))})
        self.assertTrue(result.empty)


class BuildWriteRecordsTests(unittest.TestCase):

    def _mk_df_new(self):
        return pd.DataFrame({
            "stock_id": ["2330", "NVDA", "6488"],
            "trade_date": [dt.date(2026, 2, 23), dt.date(2026, 1, 20), dt.date(2026, 3, 2)],
            "article_count": [1, np.nan, 2],
            "sentiment_mean": [0.8, np.nan, 0.6],
            "sentiment_3d_ma": [0.75, np.nan, 0.6],
            "sentiment_5d_ma": [0.7, np.nan, 0.6],
            "sentiment_lag_1": [0.5, np.nan, 0.5],
            "sentiment_lag_2": [0.5, np.nan, 0.5],
            "bullishness_index": [0.1, np.nan, 0.05],
            "agreement_index": [0.2, np.nan, 0.1],
            "comment_volume_ratio": [np.nan, np.nan, np.nan],
            "comment_polarization": [np.nan, np.nan, np.nan],
            "net_push_momentum": [np.nan, np.nan, np.nan],
            "source_status": ["SUCCESS", "SUCCESS_EMPTY", "SUCCESS"],
        })

    def test_only_impact_keys_included(self):
        df = self._mk_df_new()
        keys = {("2330", dt.date(2026, 2, 23))}
        records = build_write_records(df, keys)
        self.assertEqual(len(records), 1)

    def test_field_order_matches_sentiment_write_columns(self):
        df = self._mk_df_new()
        keys = {("2330", dt.date(2026, 2, 23))}
        records = build_write_records(df, keys)
        rec = records[0]
        self.assertEqual(rec[0], "2330")
        self.assertEqual(rec[1], dt.date(2026, 2, 23))
        # article_count 為第 3 個欄位（index 2），轉為 python int
        self.assertEqual(rec[2], 1)
        self.assertIsInstance(rec[2], int)
        # sentiment_mean 為第 4 個欄位（index 3）
        self.assertAlmostEqual(rec[3], 0.8)
        # source_status 為最後一個欄位
        self.assertEqual(rec[-1], "SUCCESS")

    def test_nan_converted_to_none_for_all_columns(self):
        df = self._mk_df_new()
        keys = {("NVDA", dt.date(2026, 1, 20))}
        records = build_write_records(df, keys)
        rec = records[0]
        # article_count（NaN）→ None，不是 float('nan')
        self.assertIsNone(rec[2])
        # 9 個數值欄（sentiment_mean ... net_push_momentum）皆為 NaN → 全部 None；
        # source_status（最後一欄）本列是真值 "SUCCESS_EMPTY"，不是 NaN，不應被轉成 None。
        for v in rec[3:-1]:
            self.assertIsNone(v)
        self.assertEqual(rec[-1], "SUCCESS_EMPTY")

    def test_multiple_keys_preserve_each_rows_own_values(self):
        df = self._mk_df_new()
        keys = {("2330", dt.date(2026, 2, 23)), ("6488", dt.date(2026, 3, 2))}
        records = build_write_records(df, keys)
        self.assertEqual(len(records), 2)
        by_stock = {r[0]: r for r in records}
        self.assertAlmostEqual(by_stock["2330"][3], 0.8)
        self.assertAlmostEqual(by_stock["6488"][3], 0.6)


class CheckTotalRowCountTests(unittest.TestCase):

    def _mk_conn(self, fetchone_value):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = (fetchone_value,)
        conn.cursor.return_value.__enter__.return_value = cur
        return conn

    def test_matches_expected(self):
        conn = self._mk_conn(TOTAL_ROWS_EXPECTED)
        ok, n = check_total_row_count(conn)
        self.assertTrue(ok)
        self.assertEqual(n, TOTAL_ROWS_EXPECTED)

    def test_known_fail_when_row_count_differs(self):
        conn = self._mk_conn(TOTAL_ROWS_EXPECTED - 1)
        ok, n = check_total_row_count(conn)
        self.assertFalse(ok)


class CheckLabelCountsTests(unittest.TestCase):

    def _mk_conn(self, fetchone_value):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = fetchone_value
        conn.cursor.return_value.__enter__.return_value = cur
        return conn

    def test_matches_expected(self):
        conn = self._mk_conn(EXISTING_LABEL_COUNTS)
        ok, counts = check_label_counts(conn)
        self.assertTrue(ok)
        self.assertEqual(counts, EXISTING_LABEL_COUNTS)

    def test_known_fail_when_label_counts_drifted(self):
        """若標籤欄計數與常數不符，代表段 2 重跑期間有其他寫入介入
        （例如段 3 或每日 ETL 意外跑了）——必須 FAIL，不得放行。"""
        conn = self._mk_conn((EXISTING_LABEL_COUNTS[0] + 1, EXISTING_LABEL_COUNTS[1]))
        ok, counts = check_label_counts(conn)
        self.assertFalse(ok)


class ComputeExpectedImpactAndActualDiffTests(unittest.TestCase):
    """純用合成 DataFrame 測試 `compute_expected_impact`／`compute_actual_diff`
    的比對邏輯本身，不觸碰真實 FeatureAggregator 或資料庫。"""

    def _mk_df(self, overrides=None):
        base = pd.DataFrame({
            "stock_id": ["2330", "NVDA"],
            "trade_date": [dt.date(2026, 2, 23), dt.date(2026, 1, 20)],
            "article_count": [1, 1],
            "sentiment_mean": [0.8, 0.6],
            "sentiment_3d_ma": [0.8, 0.6],
            "sentiment_5d_ma": [0.8, 0.6],
            "sentiment_lag_1": [0.5, 0.5],
            "sentiment_lag_2": [0.5, 0.5],
            "bullishness_index": [0.1, 0.1],
            "agreement_index": [0.2, 0.2],
            "comment_volume_ratio": [np.nan, np.nan],
            "comment_polarization": [np.nan, np.nan],
            "net_push_momentum": [np.nan, np.nan],
            "source_status": ["SUCCESS", "SUCCESS"],
        })
        if overrides:
            for col, values in overrides.items():
                base[col] = values
        return base

    def test_no_difference_yields_empty_expected_impact(self):
        df_new = self._mk_df()
        df_old = self._mk_df()
        result = compute_expected_impact(df_new, df_old)
        self.assertEqual(result, {})

    def test_difference_on_one_column_one_row(self):
        df_new = self._mk_df()
        df_old = self._mk_df(overrides={"article_count": [0, 1]})
        result = compute_expected_impact(df_new, df_old)
        self.assertEqual(
            result, {("2330", dt.date(2026, 2, 23)): frozenset({"article_count"})})

    def test_mismatched_keys_between_old_and_new_raises(self):
        df_new = self._mk_df()
        df_old = self._mk_df().iloc[[0]].reset_index(drop=True)  # 缺 NVDA 那列
        with self.assertRaises(AssertionError):
            compute_expected_impact(df_new, df_old)

    def test_actual_diff_against_existing_db_snapshot(self):
        df_new = self._mk_df()
        df_existing = self._mk_df(overrides={"sentiment_mean": [0.5, 0.6]})
        result = compute_actual_diff(df_new, df_existing)
        self.assertEqual(
            result, {("2330", dt.date(2026, 2, 23)): frozenset({"sentiment_mean"})})


class LoadOldFeatureAggregatorClassTests(unittest.TestCase):
    """驗證「舊版真的是舊版」——這是本腳本正確性的地基：若載入路徑指向
    錯誤的 commit，`compute_expected_impact` 會算出錯的預期影響集而不自知。
    刻意用真實 `git show` 對本 repo 既有兩個 commit 做整合測試。
    """

    TW_STOCK, US_STOCK = "2330", "NVDA"

    def _cross_market_scenario(self):
        """與 `tests/test_risk027_cross_market_calendar.py` 相同的合成情境：
        2330（TWSE，8/14、8/18 有交易，8/17 休市）＋ NVDA（US，8/14、8/17、
        8/18 皆有交易），文章發於 8/17（台股假日、美股交易日）。"""
        df_prices = pd.DataFrame({
            "trade_date": ["2026-08-14", "2026-08-18",
                           "2026-08-14", "2026-08-17", "2026-08-18"],
            "stock_id": ["2330", "2330", "NVDA", "NVDA", "NVDA"],
            "close_price": [1000.0, 1010.0, 120.0, 121.0, 122.0],
            "volume": [10_000, 10_500, 5_000_000, 5_100_000, 5_200_000],
        })
        df_mapping = pd.DataFrame({
            "keyword": ["台積電", "NVDA"], "stock_id": ["2330", "NVDA"],
        })
        df_articles = pd.DataFrame({
            "article_id": [1, 2],
            "fetch_keyword": ["台積電", "NVDA"],
            "post_time": ["2026-08-17 09:00:00", "2026-08-17 09:00:00"],
            "sentiment_score": [0.8, 0.6],
        })
        return df_prices, df_articles, df_mapping

    def _tw_article_count(self, FeatureAggregatorClass):
        import io
        from contextlib import redirect_stdout
        df_prices, df_articles, df_mapping = self._cross_market_scenario()
        with redirect_stdout(io.StringIO()):
            agg = FeatureAggregatorClass()
            df = agg.generate_daily_features(df_prices, df_articles, df_mapping)
        row = df[(df["stock_id"] == "2330")
                 & (df["trade_date"] == dt.date(2026, 8, 18))]
        self.assertEqual(len(row), 1)
        return row.iloc[0]["article_count"]

    def test_red_commit_reproduces_known_bug(self):
        """RED 測試 commit（`0da87d9`）的 feature_aggregator.py 與 RISK-027
        修復前完全相同——該 commit 只新增測試檔，未觸碰程式碼。2330 的文章
        必須因跨市場撞期而流失（article_count == 0），這正是 RISK-027 的
        根因現象。"""
        OldClass = load_old_feature_aggregator_class(OLD_FEATURE_AGGREGATOR_COMMIT)
        count = self._tw_article_count(OldClass)
        self.assertEqual(count, 0)

    def test_known_fail_fix_commit_does_not_reproduce_bug(self):
        """known-FAIL 對照：若載入路徑誤指向修復 commit（`e21d3c6`），
        `test_red_commit_reproduces_known_bug` 的斷言（article_count == 0）
        會 FAIL——因為修復後 2330 的文章正確滾到 8/18（article_count == 1）。
        本測試證明載入路徑對 commit 的選擇是有鑑別力的，不是不論指向哪個
        commit 都得到相同結果。"""
        FixedClass = load_old_feature_aggregator_class("e21d3c6")
        count = self._tw_article_count(FixedClass)
        self.assertEqual(count, 1)
        self.assertNotEqual(count, 0)  # 與上一項測試的斷言互斥，證明有鑑別力

    def test_invalid_commit_raises(self):
        with self.assertRaises(RuntimeError):
            load_old_feature_aggregator_class("0000000deadbeef")

    def test_does_not_mutate_sys_path_or_real_module(self):
        """載入舊版不得插入或修改 `sys.path`，也不得替換掉正式模組——
        兩者必須能在同一個 process 內同時被 import 且互不干擾。"""
        import sys
        path_before = list(sys.path)
        import src.transform.feature_aggregator as real_module
        real_class_before = real_module.FeatureAggregator

        load_old_feature_aggregator_class(OLD_FEATURE_AGGREGATOR_COMMIT)

        self.assertEqual(sys.path, path_before)
        self.assertIs(real_module.FeatureAggregator, real_class_before)


if __name__ == "__main__":
    unittest.main()
