import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch
from datetime import datetime

# 為測試環境隔離提供輕量 Stub（防止單元測試依賴外部套件或網路）

# UG-G2-SB7：本區塊原為 `if "tenacity" not in sys.modules` —— 與下方 requests 那段
# 在 UG-G2-SB5 決策點 5 修掉的**是同一個缺陷**，只是當時沒有一併改。
# 後果在本 SB 具體發生：DEC-032 的修正使生產程式碼 import `retry_if_exception`，
# 而這個 stub 只定義四個名字。`unittest discover` 是同一個 process 且依字母序載入，
# 本檔排在前段，於是 stub **永久取代**真實 tenacity，
# 導致其後 5 個測試模組 ImportError、測試數由 353 掉到 312。
# **改用已確立的正確寫法：真實套件存在就用真實的，只有缺席時才 stub。**
try:
    import tenacity  # noqa: F401
except ModuleNotFoundError:
    tenacity = types.ModuleType("tenacity")
    tenacity.retry = lambda *a, **k: (lambda f: f)
    tenacity.retry_if_exception = MagicMock()
    tenacity.stop_after_attempt = MagicMock()
    tenacity.wait_fixed = MagicMock()
    tenacity.wait_exponential = MagicMock()
    sys.modules["tenacity"] = tenacity

if "yfinance" not in sys.modules:
    yfinance = types.ModuleType("yfinance")
    yfinance.Ticker = MagicMock()
    sys.modules["yfinance"] = yfinance

# UG-G2-SB5 決策點 5：原本是 `if "requests" not in sys.modules` —— 「已安裝」不等於
# 「已被 import」，因此這個判斷在容器裡幾乎必然成立，stub 會**永久取代**真實 requests，
# 影響同一個 process 內後續所有測試模組（`unittest discover` 是同一個 process）。
# 改用本檔對 bs4 已經在用的正確寫法：真實套件存在就用真實的，只有缺席時才 stub。
# 這與 UG-G2-SB2 修掉的 4 個 bs4 stub 隔離缺陷是同一類問題。
try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests = types.ModuleType("requests")
    requests.get = MagicMock()
    sys.modules["requests"] = requests

try:
    import bs4  # noqa: F401
except ModuleNotFoundError:
    bs4 = types.ModuleType("bs4")
    bs4.BeautifulSoup = MagicMock()
    sys.modules["bs4"] = bs4

if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = MagicMock()
    sys.modules["dotenv"] = dotenv

if "snownlp" not in sys.modules:
    snownlp = types.ModuleType("snownlp")
    snownlp.SnowNLP = MagicMock()
    sys.modules["snownlp"] = snownlp

if "jieba" not in sys.modules:
    jieba = types.ModuleType("jieba")
    jieba.cut = MagicMock()
    jieba.add_word = MagicMock()
    sys.modules["jieba"] = jieba
else:
    if not hasattr(sys.modules["jieba"], "add_word"):
        sys.modules["jieba"].add_word = MagicMock()

if "google.generativeai" not in sys.modules:
    google = types.ModuleType("google")
    generativeai = types.ModuleType("google.generativeai")
    generativeai.configure = MagicMock()
    generativeai.GenerativeModel = MagicMock()
    generativeai.GenerationConfig = MagicMock()
    google.generativeai = generativeai
    sys.modules["google"] = google
    sys.modules["google.generativeai"] = generativeai

# UG-G2-SB7：與上方 tenacity 同一個缺陷。**本 SB 必須修這一個**——
# SB7 要建 `etl_run_log` 並宣稱「失敗的 outcome 持久化，不是 print」，
# 而若測試期間 `psycopg2` 是 MagicMock，**那些測試對真實 DB 互動一無所證**，
# 也就無法支撐那個宣稱。
# ⚠ 其餘五個 stub（yfinance／dotenv／snownlp／jieba／google.generativeai）
#   **刻意不動** —— 屬另案稽核（複查方 2026-09-04 裁決）。
try:
    import psycopg2  # noqa: F401
    import psycopg2.extras  # noqa: F401
except ModuleNotFoundError:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock()
    psycopg2_extras = types.ModuleType("psycopg2.extras")
    psycopg2_extras.execute_values = MagicMock()
    psycopg2.extras = psycopg2_extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2_extras

import pandas as pd

from src.transform.data_cleaner import DataCleaner, format_provider_symbol
from src.transform.feature_aggregator import FeatureAggregator
from main_etl_pipeline import ETLPipelineManager


class MarketMappingStrategyTests(unittest.TestCase):
    """測試不同市場代碼映射至 Data Provider (如 yfinance) 的正確性"""

    def test_twse_market_mapping(self):
        self.assertEqual(format_provider_symbol("2330", "TWSE"), "2330.TW")

    def test_tpex_market_mapping(self):
        self.assertEqual(format_provider_symbol("6488", "TPEX"), "6488.TWO")

    def test_otc_market_mapping(self):
        self.assertEqual(format_provider_symbol("6488", "OTC"), "6488.TWO")

    def test_us_market_mapping(self):
        self.assertEqual(format_provider_symbol("NVDA", "US"), "NVDA")

    def test_case_insensitivity_and_whitespace(self):
        self.assertEqual(format_provider_symbol("2330", " twse "), "2330.TW")
        self.assertEqual(format_provider_symbol("6488", "tpex"), "6488.TWO")
        self.assertEqual(format_provider_symbol("6488", "otc"), "6488.TWO")
        self.assertEqual(format_provider_symbol("AAPL", "us"), "AAPL")

    def test_unsupported_market_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            format_provider_symbol("2330", "UNKNOWN")
        self.assertIn("Unsupported market: UNKNOWN", str(ctx.exception))

        with self.assertRaises(ValueError):
            format_provider_symbol("2330", "CRYPTO")

        with self.assertRaises(ValueError):
            format_provider_symbol("2330", "")

        with self.assertRaises(ValueError):
            format_provider_symbol("2330", None)


class DataCleanerCanonicalStockIdTests(unittest.TestCase):
    """測試 DataCleaner 清洗時對 Canonical Stock ID 的保證"""

    def setUp(self):
        self.cleaner = DataCleaner()

    def test_clean_twse_stock_data_guarantees_canonical_id(self):
        raw_df = pd.DataFrame({
            "date": ["2026-08-01"],
            "open": [100.0],
            "high": [105.0],
            "low": [98.0],
            "close": [103.0],
            "volume": [10000]
        })
        clean_df = self.cleaner.clean_twse_stock_data(raw_df, "2330")
        self.assertEqual(clean_df["stock_id"].iloc[0], "2330")
        self.assertNotIn(".TW", clean_df["stock_id"].iloc[0])

    def test_clean_yfinance_stock_data_overwrites_provider_symbol_with_canonical_id(self):
        # 模擬 yfinance 抓回來的 raw data (可能由 6488.TWO 抓取)
        raw_df = pd.DataFrame({
            "Date": [pd.Timestamp("2026-08-01")],
            "Open": [500.0],
            "High": [510.0],
            "Low": [495.0],
            "Close": [505.0],
            "Volume": [50000]
        })
        # 傳入 Canonical ID "6488"
        clean_df = self.cleaner.clean_yfinance_stock_data(raw_df, "6488")
        self.assertEqual(clean_df["stock_id"].iloc[0], "6488")
        self.assertNotIn(".TWO", clean_df["stock_id"].iloc[0])

    def test_clean_yfinance_stock_data_us_stock(self):
        raw_df = pd.DataFrame({
            "Date": [pd.Timestamp("2026-08-01")],
            "Open": [120.0],
            "High": [125.0],
            "Low": [119.0],
            "Close": [124.0],
            "Volume": [1000000]
        })
        clean_df = self.cleaner.clean_yfinance_stock_data(raw_df, "NVDA")
        self.assertEqual(clean_df["stock_id"].iloc[0], "NVDA")

    def test_clean_empty_and_none_dataframes(self):
        self.assertTrue(self.cleaner.clean_twse_stock_data(pd.DataFrame(), "2330").empty)
        self.assertIsNone(self.cleaner.clean_twse_stock_data(None, "2330"))
        self.assertTrue(self.cleaner.clean_yfinance_stock_data(pd.DataFrame(), "NVDA").empty)
        self.assertIsNone(self.cleaner.clean_yfinance_stock_data(None, "NVDA"))


class ETLPipelineManagerCanonicalDispatchTests(unittest.TestCase):
    """測試 ETLPipelineManager 調度時各模組之間的 Canonical Stock ID 傳遞"""

    # ⚠ `UG-G3-SB2a` 方案 B（2026-09-10）：以下三個測試（原
    # `test_twse_primary_success_does_not_call_yfinance`／
    # `test_twse_fallback_to_yfinance_twse_market`／
    # `test_tpex_fallback_to_yfinance_tpex_market`）驗的是舊版逐股爬蟲＋
    # yfinance 備援機制（爬蟲優先成功不落 yfinance／爬蟲失敗落 yfinance
    # 備援／經 market="TPEX" 呼叫同一支函式落 yfinance）——該機制已刪除，
    # TWSE／TPEX 逐股路徑統一為複製 `candidate_prices`（見
    # `test_batch_etl_boundary.py` 的 `TwseStockPricesComeFromCandidatePrices`
    # 家族與 `tests/test_ug_g3_sb2a_planb_twse_route.py`）。三者共同附帶
    # 斷言的「Canonical ID 寫入 stock_prices」在新路徑下由 SELECT 直接
    # 帶出 `candidate_prices` 原欄位，不經任何 provider symbol 轉換
    # （`.TW`／`.TWO`），沒有對應風險需要獨立覆蓋。歷史行為見 git log，
    # 不在測試碼內保留已刪除的函式名。

    @patch("main_etl_pipeline.DBWriter")
    @patch("main_etl_pipeline.YFinanceAPI")
    def test_us_stock_pipeline_uses_canonical_id(self, mock_yf, mock_db):
        with redirect_stdout(io.StringIO()):
            manager = ETLPipelineManager()
            raw_yf_df = pd.DataFrame({
                "Date": [pd.Timestamp("2026-08-01")],
                "Open": [120.0],
                "High": [125.0],
                "Low": [119.0],
                "Close": [124.0],
                "Volume": [1000000]
            })
            manager.yf_api.fetch_yfinance_data.return_value = raw_yf_df

            manager.run_us_stock_pipeline("NVDA", period="1mo")

            manager.yf_api.fetch_yfinance_data.assert_called_once_with("NVDA", "1mo")
            self.assertEqual(manager.db_writer.upsert_to_stock_prices.call_count, 1)
            saved_df = manager.db_writer.upsert_to_stock_prices.call_args[0][0]
            self.assertEqual(saved_df["stock_id"].iloc[0], "NVDA")

    # ⚠ `UG-G3-SB2a` 方案 B（2026-09-10）：`test_yfinance_fallback_empty_data_
    # does_not_upsert`（原驗「爬蟲與 yfinance 皆空 → 不寫入」）連同上面三個
    # 一併刪除——同一個已刪除機制的第四個案例，歷史行為見 git log。

    @patch("main_etl_pipeline.DBWriter")
    def test_format_provider_symbol_unknown_market_raises_value_error(self, mock_db):
        """`UG-G3-SB2a` 方案 B（2026-09-10）：原經由已刪除的舊版 TWSE 專屬管線
        函式間接觸發 `ValueError`——那個間接路徑不存在了，但
        `format_provider_symbol`（`src/transform/data_cleaner.py:33-58`）本身
        「不支援的市場值必須 raise」這個契約仍然活著（`run_us_stock_pipeline`
        仍呼叫它），改為直接測這一層。
        """
        with redirect_stdout(io.StringIO()):
            manager = ETLPipelineManager()

            with self.assertRaises(ValueError) as ctx:
                manager.format_provider_symbol("9999", "INVALID_MARKET")
            self.assertIn("Unsupported market: INVALID_MARKET", str(ctx.exception))
            manager.db_writer.upsert_to_stock_prices.assert_not_called()


class FeatureAggregatorMultiMarketJoinTests(unittest.TestCase):
    """測試 FeatureAggregator 在多市場 (TWSE, TPEX, US) 標的下透過 Canonical ID Join 的精準度"""

    def setUp(self):
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def test_multi_market_features_join_on_canonical_ids_without_suffix(self):
        with redirect_stdout(io.StringIO()):
            # 1. 股價表：包含 TWSE(2330), TPEX(6488), US(NVDA)，皆為 Bare Canonical ID
            df_prices = pd.DataFrame({
                "trade_date": ["2026-08-01", "2026-08-01", "2026-08-01"],
                "stock_id": ["2330", "6488", "NVDA"],
                "close_price": [1000.0, 500.0, 120.0],
                "volume": [10000, 5000, 1000000]
            })

            # 2. 輿情文章表：包含不同 keyword
            df_articles = pd.DataFrame({
                "article_id": [1, 2, 3, 4],
                "fetch_keyword": ["台積電", "台積電", "環球晶", "輝達"],
                "post_time": ["2026-08-01 10:00:00", "2026-08-01 14:00:00", "2026-08-01 11:00:00", "2026-08-01 15:00:00"],
                "sentiment_score": [0.8, 0.6, 0.2, 0.9]
            })

            # 3. 實體映射表：定義 keyword 到 Canonical stock_id
            df_mapping = pd.DataFrame({
                "keyword": ["台積電", "環球晶", "輝達"],
                "stock_id": ["2330", "6488", "NVDA"],
                "market": ["TWSE", "TPEX", "US"],
                "description": ["中文全稱", "中文全稱", "中文全稱"]
            })

            df_features = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())

            # 驗證結果
            self.assertEqual(len(df_features), 3)
            self.assertListEqual(sorted(df_features["stock_id"].tolist()), ["2330", "6488", "NVDA"])

            # 驗證台積電 (2330): 文章數 2, 平均情緒 (0.8 + 0.6) / 2 = 0.7
            row_2330 = df_features[df_features["stock_id"] == "2330"].iloc[0]
            self.assertEqual(row_2330["article_count"], 2)
            self.assertAlmostEqual(row_2330["sentiment_mean"], 0.7)

            # 驗證環球晶 (6488): 文章數 1, 平均情緒 0.2
            row_6488 = df_features[df_features["stock_id"] == "6488"].iloc[0]
            self.assertEqual(row_6488["article_count"], 1)
            self.assertAlmostEqual(row_6488["sentiment_mean"], 0.2)

            # 驗證輝達 (NVDA): 文章數 1, 平均情緒 0.9
            row_nvda = df_features[df_features["stock_id"] == "NVDA"].iloc[0]
            self.assertEqual(row_nvda["article_count"], 1)
            self.assertAlmostEqual(row_nvda["sentiment_mean"], 0.9)


if __name__ == "__main__":
    unittest.main()
