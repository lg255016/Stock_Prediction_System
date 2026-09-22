import io
import math
import sys
import types
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import MagicMock, patch


try:
    import pandas as pd
except ModuleNotFoundError:
    pd = types.ModuleType("pandas")

    class DataFrame:
        def __init__(self, data=None, columns=None):
            self.data = [] if data is None else data
            self.columns = columns

        @property
        def empty(self):
            return len(self.data) == 0

    pd.DataFrame = DataFrame
    sys.modules["pandas"] = pd

try:
    import psycopg2  # noqa: F401
except ModuleNotFoundError:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock(name="unconfigured_psycopg2_connect")
    psycopg2_extras = types.ModuleType("psycopg2.extras")
    psycopg2_extras.execute_values = MagicMock(name="execute_values")
    psycopg2.extras = psycopg2_extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2_extras

from src.loaders.db_writer import DBWriter


def pipeline_dependency_stub(module_name, class_name):
    module = types.ModuleType(module_name)
    setattr(module, class_name, type(class_name, (), {}))
    return module


pipeline_stubs = {
    "src.extractors.twse_scraper": pipeline_dependency_stub(
        "src.extractors.twse_scraper", "TwseScraper"
    ),
    "src.extractors.yfinance_api": pipeline_dependency_stub(
        "src.extractors.yfinance_api", "YFinanceAPI"
    ),
    "src.extractors.ptt_scraper": pipeline_dependency_stub(
        "src.extractors.ptt_scraper", "PttScraper"
    ),  # PttSourceUnavailableError 屬性於下方補上（UG-G2-SB2）
    "src.extractors.trend_discover": pipeline_dependency_stub(
        "src.extractors.trend_discover", "TrendDiscover"
    ),
    "src.transform.data_cleaner": pipeline_dependency_stub(
        "src.transform.data_cleaner", "DataCleaner"
    ),
    "src.transform.nlp_processor": pipeline_dependency_stub(
        "src.transform.nlp_processor", "NLPProcessor"
    ),
    "src.transform.feature_aggregator": pipeline_dependency_stub(
        "src.transform.feature_aggregator", "FeatureAggregator"
    ),
}
# main_etl_pipeline.py 自 UG-G2-SB2 起額外 import PttSourceUnavailableError；
# 上方 ptt_scraper 隔離 stub 只建立了 PttScraper，這裡補上同名例外類別。
pipeline_stubs["src.extractors.ptt_scraper"].PttSourceUnavailableError = type(
    "PttSourceUnavailableError", (Exception,), {}
)
# §0.5 #31：main_etl_pipeline.py 額外 import GeminiDailyQuotaExhausted；
# 上方 nlp_processor 隔離 stub 只建立了 NLPProcessor，這裡補上同名例外類別。
pipeline_stubs["src.transform.nlp_processor"].GeminiDailyQuotaExhausted = type(
    "GeminiDailyQuotaExhausted", (RuntimeError,), {}
)

with patch.dict(sys.modules, pipeline_stubs):
    sys.modules.pop("main_etl_pipeline", None)
    from main_etl_pipeline import ETLPipelineManager


class DBReadTestCase(unittest.TestCase):
    def setUp(self):
        self.writer = DBWriter(
            {
                "host": "unused.test",
                "port": 5432,
                "database": "unused",
                "user": "unused",
                "password": "<test>",
            }
        )

    @staticmethod
    def direct_connection(rows=()):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = list(rows)
        return connection, cursor


class FetchDataTests(DBReadTestCase):
    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_successful_zero_rows_returns_empty_dataframe_and_closes_connection(
        self, connect
    ):
        connection, _ = self.direct_connection()
        connect.return_value = connection

        result = self.writer.fetch_data("SELECT article_id FROM market_articles")

        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)
        connection.close.assert_called_once_with()

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_connection_failure_propagates(self, connect):
        connect.side_effect = RuntimeError("connection failed")

        with self.assertRaisesRegex(RuntimeError, "connection failed"):
            self.writer.fetch_data("SELECT 1")

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_execute_failure_propagates_and_closes_connection(self, connect):
        connection, cursor = self.direct_connection()
        cursor.execute.side_effect = RuntimeError("execute failed")
        connect.return_value = connection

        with self.assertRaisesRegex(RuntimeError, "execute failed"):
            self.writer.fetch_data("SELECT 1")

        connection.close.assert_called_once_with()


class FetchCachedScoresTests(DBReadTestCase):
    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_empty_input_returns_empty_dict_without_connection(self, connect):
        self.assertEqual(self.writer.fetch_cached_scores([]), {})
        connect.assert_not_called()

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_successful_zero_rows_returns_empty_dict(self, connect):
        connection, _ = self.direct_connection()
        connect.return_value = connection

        self.assertEqual(self.writer.fetch_cached_scores(["missing"]), {})
        connection.close.assert_called_once_with()

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_connection_failure_propagates(self, connect):
        connect.side_effect = RuntimeError("cache connection failed")

        with self.assertRaisesRegex(RuntimeError, "cache connection failed"):
            self.writer.fetch_cached_scores(["title"])

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_execute_failure_propagates_and_closes_connection(self, connect):
        connection, cursor = self.direct_connection()
        cursor.execute.side_effect = RuntimeError("cache execute failed")
        connect.return_value = connection

        with self.assertRaisesRegex(RuntimeError, "cache execute failed"):
            self.writer.fetch_cached_scores(["title"])

        connection.close.assert_called_once_with()

    def test_invalid_cache_values_raise_instead_of_becoming_cache_misses(self):
        invalid_values = (
            "not-a-number",
            "0.5",
            None,
            math.nan,
            math.inf,
            -math.inf,
            -0.01,
            1.01,
        )

        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                connection, _ = self.direct_connection([("title", invalid_value)])
                with patch(
                    "src.loaders.db_writer.psycopg2.connect",
                    return_value=connection,
                ):
                    with self.assertRaises((TypeError, ValueError)):
                        self.writer.fetch_cached_scores(["title"])
                connection.close.assert_called_once_with()

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_valid_boundary_cache_values_are_returned(self, connect):
        connection, _ = self.direct_connection(
            [("zero", 0), ("neutral", Decimal("0.5")), ("one", 1)]
        )
        connect.return_value = connection

        self.assertEqual(
            self.writer.fetch_cached_scores(["zero", "neutral", "one"]),
            {"zero": 0.0, "neutral": 0.5, "one": 1.0},
        )
        connection.close.assert_called_once_with()


class FetchActiveKeywordsTests(DBReadTestCase):
    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_successful_zero_rows_returns_empty_list(self, connect):
        connection, _ = self.direct_connection()
        connect.return_value = connection

        self.assertEqual(self.writer.fetch_active_keywords(), [])
        connection.close.assert_called_once_with()

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_connection_failure_propagates(self, connect):
        connect.side_effect = RuntimeError("keyword connection failed")

        with self.assertRaisesRegex(RuntimeError, "keyword connection failed"):
            self.writer.fetch_active_keywords()

    @patch("src.loaders.db_writer.psycopg2.connect")
    def test_execute_failure_propagates_and_closes_connection(self, connect):
        connection, cursor = self.direct_connection()
        cursor.execute.side_effect = RuntimeError("keyword execute failed")
        connect.return_value = connection

        with self.assertRaisesRegex(RuntimeError, "keyword execute failed"):
            self.writer.fetch_active_keywords()

        connection.close.assert_called_once_with()


class PipelineReadFailureTests(unittest.TestCase):
    def test_nlp_read_failure_stops_without_write_or_fake_success(self):
        pipeline = ETLPipelineManager.__new__(ETLPipelineManager)
        pipeline.db_writer = MagicMock()
        pipeline.nlp_processor = MagicMock()
        pipeline.db_writer.fetch_data.side_effect = RuntimeError("NLP read failed")
        output = io.StringIO()

        with redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "NLP read failed"):
                pipeline.run_nlp_sentiment_pipeline()

        pipeline.nlp_processor.process_batch_hybrid.assert_not_called()
        pipeline.db_writer.update_sentiment_scores.assert_not_called()
        self.assertNotIn("所有文章情緒分數計算完畢", output.getvalue())

    def test_keyword_read_failure_stops_later_steps_without_fake_success(self):
        pipeline = ETLPipelineManager.__new__(ETLPipelineManager)
        pipeline.db_writer = MagicMock()
        pipeline.db_writer.fetch_active_keywords.side_effect = RuntimeError(
            "keyword read failed"
        )
        pipeline.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        pipeline.db_writer.fetch_last_discovery_probed_date.return_value = None
        pipeline.trend_discover.run_discovery.return_value = ("OK", None)
        pipeline.run_twse_pipeline_from_candidate_prices = MagicMock(return_value="OK")
        pipeline.run_us_stock_pipeline = MagicMock()
        pipeline.run_ptt_pipeline = MagicMock(return_value="OK")
        pipeline.run_nlp_sentiment_pipeline = MagicMock()
        pipeline.run_feature_engineering_pipeline = MagicMock()
        # UG-G2-SB7：`run_all_daily_tasks` 新增了「全市場批次取價」階段，
        # **它會觸網**。本測試沿用本檔既有的隔離慣例（在 instance 上替換方法），
        # 把該階段一併換掉 —— **否則單元測試會對政府單位的服務發出請求**。
        # 回傳值必須符合 `run_price_batch` 的契約（含 `outcomes_by_item`）——
        # 少了它，`run_all_daily_tasks` 會 raise。
        # ⚠ **那個 raise 是刻意的**：逐股階段需要用批次的 outcome 歸因
        #   「上櫃標的沒有列」，缺了它就只能猜（UG-G2-SB7，2026-09-04）。
        pipeline.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": {"twse": "OK", "tpex": "OK"}})
        # run log 寫入端同屬外部相依（比照 db_writer 一併隔離）。
        # 回 None = 「本次不寫稽核紀錄」，`run_all_daily_tasks` 已處理該情形。
        # ⚠ **生產行為刻意不同**：那裡若寫不進 `etl_run_log`，例外會往上傳、
        #   讓執行失敗 —— **稽核紀錄靜默缺席，比執行失敗更糟**。
        pipeline._run_log_writer = lambda: None
        output = io.StringIO()

        with redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "keyword read failed"):
                pipeline.run_all_daily_tasks()

        pipeline.run_ptt_pipeline.assert_not_called()
        pipeline.run_nlp_sentiment_pipeline.assert_not_called()
        pipeline.run_feature_engineering_pipeline.assert_not_called()
        self.assertNotIn("取得 0 個追蹤關鍵字", output.getvalue())
        self.assertNotIn("所有 ETL 任務執行完畢", output.getvalue())


if __name__ == "__main__":
    unittest.main()
