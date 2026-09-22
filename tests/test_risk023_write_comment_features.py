# -*- coding: utf-8 -*-
"""
`scripts/verify/risk023_write_comment_features.py` 的單元測試。

純邏輯測試為主（不連真實庫）：差異集攤平／相等斷言／向量化鍵篩選／寫入
record 轉型／前置守衛／`suspect`與落界則數的獨立重算。
`LoadOldFeatureAggregatorClassTests` 例外——它是本腳本設計核心的驗證對象
本身（「舊版真的是 DEC-039 修法前」），刻意用真實 `git show` 對本 repo
既有的 RED 測試 commit 做整合測試，不用 mock 取代（比照
`tests/test_sb2a_stage2_rerun_risk027.py` 同一設計理由）。

真實庫寫入本身（`--write` 路徑）的驗證見拋棄式容器乾跑紀錄
（`RISK-023_write_dryrun_report.md`），不在本檔案範圍——本檔案只測純邏輯。
"""
import datetime as dt
import unittest
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from scripts.verify.risk023_write_comment_features import (
    COMMENT_WRITE_COLUMNS,
    EXISTING_LABEL_COUNTS,
    EXPECTED_OUT_OF_BOUNDS_COUNT,
    EXPECTED_SUSPECT_COUNT,
    GUARD_ZERO_DIFF_COLUMNS,
    OLD_FEATURE_AGGREGATOR_COMMIT,
    OTHER_SENTIMENT_COLUMNS,
    PRICE_DERIVED_COLUMNS,
    TOTAL_ROWS_EXPECTED,
    assert_expected_equals_actual,
    build_write_records,
    check_label_counts,
    check_total_row_count,
    compute_actual_diff,
    compute_expected_impact,
    compute_suspect_and_out_of_bounds_counts,
    diff_keys_and_columns,
    load_old_feature_aggregator_class,
    select_by_keys,
)


class ConstantsTests(unittest.TestCase):

    def test_column_split_matches_22_plus_3_contract(self):
        self.assertEqual(len(COMMENT_WRITE_COLUMNS), 3)
        self.assertEqual(len(PRICE_DERIVED_COLUMNS), 13)
        self.assertEqual(len(OTHER_SENTIMENT_COLUMNS), 9)
        self.assertEqual(len(GUARD_ZERO_DIFF_COLUMNS), 22)
        self.assertEqual(set(COMMENT_WRITE_COLUMNS) & set(GUARD_ZERO_DIFF_COLUMNS), set())

    def test_expected_real_db_constants_are_plain_numbers(self):
        """對照診斷與 DECISIONS.md DEC-039 記載的真實庫實測數字，非佔位符。"""
        self.assertEqual(EXPECTED_SUSPECT_COUNT, 2)
        self.assertEqual(EXPECTED_OUT_OF_BOUNDS_COUNT, 13)


class DiffKeysAndColumnsTests(unittest.TestCase):

    def _diffs(self, rows_by_col):
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
            "comment_volume_ratio": [("2330", d1)],
            "comment_polarization": [("2330", d1), ("NVDA", d2)],
        })
        result = diff_keys_and_columns(diffs, COMMENT_WRITE_COLUMNS)
        self.assertEqual(result, {
            ("2330", d1): frozenset({"comment_volume_ratio", "comment_polarization"}),
            ("NVDA", d2): frozenset({"comment_polarization"}),
        })

    def test_empty_diffs_yields_empty_mapping(self):
        self.assertEqual(diff_keys_and_columns({}, COMMENT_WRITE_COLUMNS), {})


class AssertExpectedEqualsActualTests(unittest.TestCase):

    def test_identical_mappings_pass(self):
        m = {("2330", dt.date(2026, 2, 23)): frozenset({"comment_polarization"})}
        ok, detail = assert_expected_equals_actual(m, dict(m))
        self.assertTrue(ok)

    def test_key_only_in_expected_fails(self):
        k = ("2330", dt.date(2026, 2, 23))
        ok, detail = assert_expected_equals_actual({k: frozenset({"comment_polarization"})}, {})
        self.assertFalse(ok)
        self.assertEqual(detail["only_in_expected"], {k})

    def test_key_only_in_actual_fails(self):
        k = ("2330", dt.date(2026, 2, 23))
        ok, detail = assert_expected_equals_actual({}, {k: frozenset({"comment_polarization"})})
        self.assertFalse(ok)
        self.assertEqual(detail["only_in_actual"], {k})

    def test_same_key_different_columns_fails(self):
        k = ("2330", dt.date(2026, 2, 23))
        expected = {k: frozenset({"comment_volume_ratio", "comment_polarization"})}
        actual = {k: frozenset({"comment_polarization"})}
        ok, detail = assert_expected_equals_actual(expected, actual)
        self.assertFalse(ok)
        self.assertIn(k, detail["column_mismatches"])


class SelectByKeysTests(unittest.TestCase):

    def test_filters_to_matching_keys_only(self):
        df = pd.DataFrame({
            "stock_id": ["2330", "2330", "NVDA"],
            "trade_date": [dt.date(2026, 2, 23), dt.date(2026, 2, 24), dt.date(2026, 1, 20)],
            "value": [1, 2, 3],
        })
        result = select_by_keys(df, {("2330", dt.date(2026, 2, 23)), ("NVDA", dt.date(2026, 1, 20))})
        self.assertEqual(sorted(result["value"].tolist()), [1, 3])

    def test_empty_keys_yields_empty_result(self):
        df = pd.DataFrame({"stock_id": ["2330"], "trade_date": [dt.date(2026, 2, 23)], "value": [1]})
        self.assertTrue(select_by_keys(df, set()).empty)


class BuildWriteRecordsTests(unittest.TestCase):

    def _mk_df_new(self):
        return pd.DataFrame({
            "stock_id": ["2330", "NVDA"],
            "trade_date": [dt.date(2026, 2, 23), dt.date(2026, 1, 20)],
            "comment_volume_ratio": [0.5, np.nan],
            "comment_polarization": [0.3, np.nan],
            "net_push_momentum": [np.nan, np.nan],
        })

    def test_only_impact_keys_included(self):
        df = self._mk_df_new()
        records = build_write_records(df, {("2330", dt.date(2026, 2, 23))})
        self.assertEqual(len(records), 1)

    def test_field_order_and_nan_to_none(self):
        df = self._mk_df_new()
        records = build_write_records(df, {("2330", dt.date(2026, 2, 23))})
        rec = records[0]
        self.assertEqual(rec[0], "2330")
        self.assertEqual(rec[1], dt.date(2026, 2, 23))
        self.assertAlmostEqual(rec[2], 0.5)
        self.assertAlmostEqual(rec[3], 0.3)
        self.assertIsNone(rec[4])  # net_push_momentum 為 NaN → None

    def test_all_nan_row_converted_fully(self):
        df = self._mk_df_new()
        records = build_write_records(df, {("NVDA", dt.date(2026, 1, 20))})
        rec = records[0]
        self.assertIsNone(rec[2])
        self.assertIsNone(rec[3])
        self.assertIsNone(rec[4])


class CheckTotalRowCountTests(unittest.TestCase):

    def _mk_conn(self, value):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = (value,)
        conn.cursor.return_value.__enter__.return_value = cur
        return conn

    def test_matches_expected(self):
        ok, n = check_total_row_count(self._mk_conn(TOTAL_ROWS_EXPECTED))
        self.assertTrue(ok)

    def test_known_fail_when_row_count_differs(self):
        ok, n = check_total_row_count(self._mk_conn(TOTAL_ROWS_EXPECTED - 1))
        self.assertFalse(ok)


class CheckLabelCountsTests(unittest.TestCase):

    def _mk_conn(self, value):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = value
        conn.cursor.return_value.__enter__.return_value = cur
        return conn

    def test_matches_expected(self):
        ok, counts = check_label_counts(self._mk_conn(EXISTING_LABEL_COUNTS))
        self.assertTrue(ok)

    def test_known_fail_when_label_counts_drifted(self):
        ok, counts = check_label_counts(
            self._mk_conn((EXISTING_LABEL_COUNTS[0] + 1, EXISTING_LABEL_COUNTS[1])))
        self.assertFalse(ok)


class ComputeExpectedImpactAndActualDiffTests(unittest.TestCase):
    """純用合成 DataFrame 測試比對邏輯本身，不觸碰真實 FeatureAggregator 或資料庫。"""

    def _mk_df(self, overrides=None):
        base = pd.DataFrame({
            "stock_id": ["2330", "NVDA"],
            "trade_date": [dt.date(2026, 2, 23), dt.date(2026, 1, 20)],
            "comment_volume_ratio": [np.nan, np.nan],
            "comment_polarization": [np.nan, np.nan],
            "net_push_momentum": [np.nan, np.nan],
        })
        if overrides:
            for col, values in overrides.items():
                base[col] = values
        return base

    def test_no_difference_yields_empty_expected_impact(self):
        result = compute_expected_impact(self._mk_df(), self._mk_df())
        self.assertEqual(result, {})

    def test_difference_on_one_column_one_row(self):
        df_new = self._mk_df(overrides={"comment_polarization": [0.4, np.nan]})
        df_old = self._mk_df()
        result = compute_expected_impact(df_new, df_old)
        self.assertEqual(
            result, {("2330", dt.date(2026, 2, 23)): frozenset({"comment_polarization"})})

    def test_mismatched_keys_between_old_and_new_raises(self):
        df_new = self._mk_df()
        df_old = self._mk_df().iloc[[0]].reset_index(drop=True)
        with self.assertRaises(AssertionError):
            compute_expected_impact(df_new, df_old)

    def test_actual_diff_against_existing_db_snapshot(self):
        df_new = self._mk_df(overrides={"comment_volume_ratio": [0.5, np.nan]})
        df_existing = self._mk_df()
        result = compute_actual_diff(df_new, df_existing)
        self.assertEqual(
            result, {("2330", dt.date(2026, 2, 23)): frozenset({"comment_volume_ratio"})})


class ComputeSuspectAndOutOfBoundsCountsTests(unittest.TestCase):
    """獨立於 `_aggregate_direct_comment_counts()` 內部實作，純用合成資料
    測試 `suspect` 篇數與落界則數的獨立重算邏輯本身。"""

    def _articles(self, rows):
        return pd.DataFrame(rows)

    def _comments(self, rows):
        return pd.DataFrame(rows)

    def test_clean_article_contributes_neither(self):
        articles = self._articles([{
            "article_id": 1, "total_comments": 2,
            "post_time": dt.datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": dt.datetime(2026, 8, 24, 14, 0),
        }])
        comments = self._comments([
            {"article_id": 1, "comment_seq": 1, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 8, 24, 10, 5)},
            {"article_id": 1, "comment_seq": 2, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 8, 24, 10, 6)},
        ])
        suspects, oob = compute_suspect_and_out_of_bounds_counts(articles, comments)
        self.assertEqual(suspects, [])
        self.assertEqual(oob, 0)

    def test_time_reset_article_counted_as_suspect(self):
        articles = self._articles([{
            "article_id": 1815, "total_comments": 2,
            "post_time": dt.datetime(2026, 7, 3, 12, 0),
            "comments_scraped_at": dt.datetime(2026, 9, 7, 14, 0),
        }])
        comments = self._comments([
            {"article_id": 1815, "comment_seq": 1, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 7, 3, 12, 19)},
            {"article_id": 1815, "comment_seq": 2, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 7, 3, 12, 9)},  # 回退
        ])
        suspects, oob = compute_suspect_and_out_of_bounds_counts(articles, comments)
        self.assertEqual(suspects, [1815])
        self.assertEqual(oob, 0, "suspect 篇的留言不應同時被算進落界則數（提早 continue）")

    def test_out_of_bounds_comment_counted_once(self):
        articles = self._articles([{
            "article_id": 1495, "total_comments": 2,
            "post_time": dt.datetime(2026, 9, 5, 8, 0),
            "comments_scraped_at": dt.datetime(2026, 9, 5, 13, 53, 32),
        }])
        comments = self._comments([
            {"article_id": 1495, "comment_seq": 1, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 9, 5, 9, 0)},  # 合法
            {"article_id": 1495, "comment_seq": 2, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 9, 5, 15, 39)},  # 落界
        ])
        suspects, oob = compute_suspect_and_out_of_bounds_counts(articles, comments)
        self.assertEqual(suspects, [])
        self.assertEqual(oob, 1)

    def test_unfetched_article_ignored(self):
        """`total_comments` 為 NaN（未擷取）的文章即使出現在 df_comments
        （不應該發生，但若發生），不計入 suspect 或落界——這條防線不是
        本函式的職責，只是確保它不會對不該處理的輸入報錯或誤算。"""
        articles = self._articles([{
            "article_id": 999, "total_comments": np.nan,
            "post_time": dt.datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": None,
        }])
        comments = self._comments([
            {"article_id": 999, "comment_seq": 1, "comment_tag": "推",
             "comment_time": dt.datetime(2026, 8, 24, 10, 5)},
        ])
        suspects, oob = compute_suspect_and_out_of_bounds_counts(articles, comments)
        self.assertEqual(suspects, [])
        self.assertEqual(oob, 0)

    def test_empty_comments_yields_zero_zero(self):
        articles = self._articles([{
            "article_id": 1, "total_comments": 0,
            "post_time": dt.datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": dt.datetime(2026, 8, 24, 14, 0),
        }])
        suspects, oob = compute_suspect_and_out_of_bounds_counts(articles, pd.DataFrame())
        self.assertEqual(suspects, [])
        self.assertEqual(oob, 0)


class LoadOldFeatureAggregatorClassTests(unittest.TestCase):
    """驗證「舊版真的是 DEC-039 修法前」——這是本腳本正確性的地基：若載入
    路徑指向錯誤的 commit，`compute_expected_impact` 會算出錯的預期影響集
    而不自知。刻意用真實 `git show` 對本 repo 既有的 RED 測試 commit 做
    整合測試（比照 RISK-027 段 2 重跑腳本的同一設計理由）。
    """

    def test_old_commit_has_no_df_comments_parameter(self):
        """66114c2（RED 測試 commit）的 `generate_daily_features()` 不接受
        `df_comments`——這是「舊版」定義本身：傳了會是 TypeError。"""
        import inspect
        OldClass = load_old_feature_aggregator_class(OLD_FEATURE_AGGREGATOR_COMMIT)
        sig = inspect.signature(OldClass.generate_daily_features)
        self.assertNotIn("df_comments", sig.parameters)

    def test_old_commit_reproduces_article_level_filter_bug(self):
        """RED 測試 commit 的 `feature_aggregator.py` 與 DEC-039 修法前完全
        相同——該 commit 只新增測試檔，未觸碰生產程式碼行為。用一篇「文章
        擷取完成時刻遠晚於決策點，但留言本身早於決策點」的合成案例：
        舊版（文章層級過濾）必須把它排除為 NULL，這正是 RISK-023 的根因
        現象。"""
        import io
        from contextlib import redirect_stdout
        OldClass = load_old_feature_aggregator_class(OLD_FEATURE_AGGREGATOR_COMMIT)

        df_prices = pd.DataFrame({
            "trade_date": ["2026-08-24", "2026-08-25", "2026-08-26"],
            "stock_id": ["2330"] * 3, "close_price": [100.0, 101.0, 102.0],
            "volume": [1000, 1100, 1200],
        })
        df_mapping = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])
        df_articles = pd.DataFrame([{
            "article_id": 1, "source": "ptt_stock", "fetch_keyword": "台積電",
            "post_time": "2026-08-24 10:00:00", "sentiment_score": 0.6,
            "push_count": 1, "boo_count": 0, "neutral_count": 0, "total_comments": 1,
            "comments_scraped_at": dt.datetime(2026, 11, 22, 9, 0),  # 回填期，遠晚於決策點
        }])
        with redirect_stdout(io.StringIO()):
            agg = OldClass()
            df = agg.generate_daily_features(df_prices, df_articles, df_mapping)
        row = df[df["trade_date"] == dt.date(2026, 8, 24)].iloc[0]
        self.assertTrue(pd.isna(row["comment_polarization"]),
                         "舊版（文章層級過濾）必須把回填期文章排除為 NULL")

    def test_known_fail_current_head_does_not_reproduce_bug(self):
        """known-FAIL 對照：用現行（HEAD）程式碼跑同一情境（傳入對應的
        `df_comments`），必須**不會**排除為 NULL——證明
        `test_old_commit_reproduces_article_level_filter_bug` 的斷言有鑑別力，
        不是不論版本都得到相同結果。"""
        import io
        from contextlib import redirect_stdout
        from src.transform.feature_aggregator import FeatureAggregator

        df_prices = pd.DataFrame({
            "trade_date": ["2026-08-24", "2026-08-25", "2026-08-26"],
            "stock_id": ["2330"] * 3, "close_price": [100.0, 101.0, 102.0],
            "volume": [1000, 1100, 1200],
        })
        df_mapping = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])
        df_articles = pd.DataFrame([{
            "article_id": 1, "source": "ptt_stock", "fetch_keyword": "台積電",
            "post_time": "2026-08-24 10:00:00", "sentiment_score": 0.6,
            "push_count": 1, "boo_count": 0, "neutral_count": 0, "total_comments": 1,
            "comments_scraped_at": dt.datetime(2026, 11, 22, 9, 0),
        }])
        df_comments = pd.DataFrame([{
            "article_id": 1, "comment_seq": 1, "comment_tag": "推",
            "comment_time": dt.datetime(2026, 8, 24, 11, 0),  # 早於決策點，合法可見
        }])
        with redirect_stdout(io.StringIO()):
            agg = FeatureAggregator()
            df = agg.generate_daily_features(df_prices, df_articles, df_mapping,
                                              df_comments=df_comments)
        row = df[df["trade_date"] == dt.date(2026, 8, 24)].iloc[0]
        self.assertFalse(pd.isna(row["comment_polarization"]),
                          "現行版本應收錄決策點前的留言，不因文章層級擷取時刻晚而排除")

    def test_invalid_commit_raises(self):
        with self.assertRaises(RuntimeError):
            load_old_feature_aggregator_class("0000000deadbeef")

    def test_does_not_mutate_sys_path_or_real_module(self):
        import sys
        path_before = list(sys.path)
        import src.transform.feature_aggregator as real_module
        real_class_before = real_module.FeatureAggregator

        load_old_feature_aggregator_class(OLD_FEATURE_AGGREGATOR_COMMIT)

        self.assertEqual(sys.path, path_before)
        self.assertIs(real_module.FeatureAggregator, real_class_before)


if __name__ == "__main__":
    unittest.main()
