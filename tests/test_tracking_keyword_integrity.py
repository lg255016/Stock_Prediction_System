import io
import importlib
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch


try:
    import pandas  # noqa: F401
except ModuleNotFoundError:
    pandas = types.ModuleType("pandas")
    pandas.DataFrame = type("DataFrame", (), {})
    pandas.notnull = MagicMock(name="notnull")
    sys.modules["pandas"] = pandas

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

dependency_stubs = {}
if "requests" not in sys.modules:
    requests = types.ModuleType("requests")
    requests.get = MagicMock(name="unconfigured_requests_get")
    dependency_stubs["requests"] = requests
if "bs4" not in sys.modules:
    bs4 = types.ModuleType("bs4")
    bs4.BeautifulSoup = MagicMock(name="BeautifulSoup")
    dependency_stubs["bs4"] = bs4
if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = MagicMock(name="load_dotenv")
    dependency_stubs["dotenv"] = dotenv
if "google.generativeai" not in sys.modules:
    google = types.ModuleType("google")
    generativeai = types.ModuleType("google.generativeai")
    generativeai.configure = MagicMock(name="configure")
    generativeai.GenerativeModel = MagicMock(name="GenerativeModel")
    generativeai.GenerationConfig = MagicMock(name="GenerationConfig")
    google.generativeai = generativeai
    dependency_stubs["google"] = google
    dependency_stubs["google.generativeai"] = generativeai

with patch.dict(sys.modules, dependency_stubs):
    trend_discover_module = importlib.import_module("src.extractors.trend_discover")
    TrendDiscover = trend_discover_module.TrendDiscover
from src.loaders.db_writer import DBWriter


class TrackingKeywordWriteContractTests(unittest.TestCase):
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
        self.writer._execute_batch = MagicMock()

    def assert_insert_only_contract(self):
        self.writer.insert_discovered_keywords(["台積電"])

        self.writer._execute_batch.assert_called_once()
        query, records = self.writer._execute_batch.call_args.args
        normalized_query = " ".join(query.split()).upper()
        self.assertIn("ON CONFLICT (KEYWORD) DO NOTHING", normalized_query)
        self.assertNotIn("DO UPDATE", normalized_query)
        self.assertEqual([("台積電", "ai_discovered", True)], records)

    def test_inactive_core_stock_is_not_reactivated_or_recategorized(self):
        self.assert_insert_only_contract()

    def test_active_core_stock_is_not_recategorized_or_timestamp_touched(self):
        self.assert_insert_only_contract()

    def test_new_ai_keyword_is_inserted_active_with_ai_category_in_one_batch(self):
        self.writer.insert_discovered_keywords(["台積電", "矽光子"])

        self.writer._execute_batch.assert_called_once()
        _, records = self.writer._execute_batch.call_args.args
        self.assertEqual(
            [
                ("台積電", "ai_discovered", True),
                ("矽光子", "ai_discovered", True),
            ],
            records,
        )

    def test_empty_discovery_batch_does_not_write(self):
        self.writer.insert_discovered_keywords([])

        self.writer._execute_batch.assert_not_called()

    def test_disable_existing_keyword_updates_only_lifecycle_fields(self):
        self.writer.disable_tracking_keyword("台積電")

        self.writer._execute_batch.assert_called_once()
        query, records = self.writer._execute_batch.call_args.args
        normalized_query = " ".join(query.split()).upper()
        self.assertIn("UPDATE TRACKING_KEYWORDS", normalized_query)
        self.assertIn("SET IS_ACTIVE = FALSE", normalized_query)
        self.assertIn("UPDATED_AT = CURRENT_TIMESTAMP", normalized_query)
        self.assertIn("WHERE TRACKING_KEYWORDS.KEYWORD = DATA.KEYWORD", normalized_query)
        self.assertNotIn("INSERT", normalized_query)
        self.assertNotIn("CATEGORY =", normalized_query)
        self.assertEqual([("台積電",)], records)

    def test_disable_missing_keyword_is_update_only_and_cannot_insert(self):
        self.writer.disable_tracking_keyword("不存在")

        query, _ = self.writer._execute_batch.call_args.args
        self.assertNotIn("INSERT", query.upper())

    def test_hard_delete_method_is_not_used_by_soft_delete(self):
        self.writer.delete_tracking_keyword = MagicMock()

        self.writer.disable_tracking_keyword("台積電")

        self.writer.delete_tracking_keyword.assert_not_called()


class TrendDiscoveryFailureSemanticsTests(unittest.TestCase):
    def make_discoverer(self, response_text='{"keywords": ["台積電", "矽光子"]}'):
        discoverer = TrendDiscover.__new__(TrendDiscover)
        discoverer.api_key = "test-key-not-real"
        discoverer.model = MagicMock()
        discoverer.model.generate_content.return_value = types.SimpleNamespace(
            text=response_text
        )
        discoverer._fetch_recent_hot_titles = MagicMock(return_value=["熱門標題"])
        return discoverer

    def test_valid_keywords_use_one_batch_database_operation(self):
        discoverer = self.make_discoverer()
        writer = MagicMock()

        discoverer.run_discovery(writer, max_new_keywords=3)

        writer.insert_discovered_keywords.assert_called_once_with(["台積電", "矽光子"])
        writer.upsert_tracking_keyword.assert_not_called()

    def test_database_write_failure_propagates(self):
        discoverer = self.make_discoverer()
        writer = MagicMock()
        writer.insert_discovered_keywords.side_effect = RuntimeError("db write failed")

        with self.assertRaisesRegex(RuntimeError, "db write failed"):
            discoverer.run_discovery(writer)

    def test_missing_api_key_is_observable_and_does_not_write(self):
        discoverer = self.make_discoverer()
        discoverer.api_key = None
        writer = MagicMock()
        output = io.StringIO()

        with redirect_stdout(output):
            discoverer.run_discovery(writer)

        self.assertIn("API", output.getvalue())
        writer.insert_discovered_keywords.assert_not_called()

    def test_title_fetch_failure_is_observable_and_does_not_write(self):
        discoverer = self.make_discoverer()
        discoverer._fetch_recent_hot_titles.return_value = None
        writer = MagicMock()
        output = io.StringIO()

        with redirect_stdout(output):
            discoverer.run_discovery(writer)

        self.assertIn("失敗", output.getvalue())
        writer.insert_discovered_keywords.assert_not_called()

    def test_ptt_request_failure_returns_failure_signal_and_is_observable(self):
        discoverer = TrendDiscover.__new__(TrendDiscover)
        discoverer.base_url = "https://unused.test"
        discoverer.headers = {}
        discoverer.cookies = {}
        output = io.StringIO()

        with patch.object(
            trend_discover_module.requests,
            "get",
            side_effect=RuntimeError("ptt unavailable"),
        ), redirect_stdout(output):
            titles = discoverer._fetch_recent_hot_titles(pages=1)

        self.assertIsNone(titles)
        self.assertIn("錯誤", output.getvalue())

    def test_gemini_failure_is_observable_and_does_not_write(self):
        discoverer = self.make_discoverer()
        discoverer.model.generate_content.side_effect = RuntimeError("gemini unavailable")
        writer = MagicMock()
        output = io.StringIO()

        with redirect_stdout(output):
            discoverer.run_discovery(writer)

        self.assertIn("失敗", output.getvalue())
        writer.insert_discovered_keywords.assert_not_called()

    def test_malformed_json_is_observable_and_does_not_write(self):
        discoverer = self.make_discoverer("not-json")
        writer = MagicMock()
        output = io.StringIO()

        with redirect_stdout(output):
            discoverer.run_discovery(writer)

        self.assertIn("失敗", output.getvalue())
        writer.insert_discovered_keywords.assert_not_called()

    def test_invalid_keyword_payload_is_observable_and_does_not_write(self):
        discoverer = self.make_discoverer('{"keywords": "台積電"}')
        writer = MagicMock()
        output = io.StringIO()

        with redirect_stdout(output):
            discoverer.run_discovery(writer)

        self.assertIn("失敗", output.getvalue())
        writer.insert_discovered_keywords.assert_not_called()


if __name__ == "__main__":
    unittest.main()
