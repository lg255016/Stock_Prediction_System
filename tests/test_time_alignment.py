import io
import sys
import types
import unittest
from datetime import datetime, date, time
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

# 為測試環境隔離提供輕量 Stub（防止單元測試依賴外部套件或網路）
if "tenacity" not in sys.modules:
    tenacity = types.ModuleType("tenacity")
    tenacity.retry = lambda *a, **k: (lambda f: f)
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

if "psycopg2" not in sys.modules:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock()
    psycopg2_extras = types.ModuleType("psycopg2.extras")
    psycopg2_extras.execute_values = MagicMock()
    psycopg2.extras = psycopg2_extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2_extras

import pandas as pd

from src.transform.data_cleaner import DataCleaner, parse_ptt_datetime
from src.transform.feature_aggregator import (
    FeatureAggregator,
    map_timestamp_to_trading_day,
    assign_trading_days_to_articles
)


class PttDatetimeParsingTests(unittest.TestCase):
    """測試 PTT 日期與時間解析器（含完整時間戳記、ISO 格式與跨年智慧推論）"""

    def test_parse_standard_ptt_header_format(self):
        dt = parse_ptt_datetime("Wed Aug 20 14:25:36 2026")
        self.assertEqual(dt, datetime(2026, 8, 20, 14, 25, 36))

        dt_single_space = parse_ptt_datetime("Wed Aug  5 09:10:00 2026")
        self.assertEqual(dt_single_space, datetime(2026, 8, 5, 9, 10, 0))

    def test_parse_iso_formats(self):
        self.assertEqual(parse_ptt_datetime("2026-08-20 14:25:36"), datetime(2026, 8, 20, 14, 25, 36))
        self.assertEqual(parse_ptt_datetime("2026/08/20 09:15:00"), datetime(2026, 8, 20, 9, 15, 0))
        self.assertEqual(parse_ptt_datetime("2026-08-20T14:25:36"), datetime(2026, 8, 20, 14, 25, 36))
        self.assertEqual(parse_ptt_datetime("2026-08-20"), datetime(2026, 8, 20, 0, 0, 0))

    def test_parse_short_date_same_year(self):
        ref_time = datetime(2026, 8, 20, 10, 0, 0)
        dt = parse_ptt_datetime("8/20", reference_time=ref_time)
        self.assertEqual(dt, datetime(2026, 8, 20, 12, 0, 0))

        dt_space = parse_ptt_datetime(" 8/20 ", reference_time=ref_time)
        self.assertEqual(dt_space, datetime(2026, 8, 20, 12, 0, 0))

    def test_parse_short_date_cross_year_smart_inference(self):
        # 模擬 2026 年 1 月 5 日執行爬蟲，抓到 12/31 的文章
        ref_time = datetime(2026, 1, 5, 10, 0, 0)
        dt_dec = parse_ptt_datetime("12/31", reference_time=ref_time)
        self.assertEqual(dt_dec, datetime(2025, 12, 31, 12, 0, 0))

        dt_nov = parse_ptt_datetime("11/15", reference_time=ref_time)
        self.assertEqual(dt_nov, datetime(2025, 11, 15, 12, 0, 0))

    def test_parse_invalid_and_empty_fallback(self):
        ref_time = datetime(2026, 8, 20, 10, 0, 0)
        self.assertEqual(parse_ptt_datetime(None, reference_time=ref_time), ref_time)
        self.assertEqual(parse_ptt_datetime("", reference_time=ref_time), ref_time)
        self.assertEqual(parse_ptt_datetime("   ", reference_time=ref_time), ref_time)
        self.assertEqual(parse_ptt_datetime("invalid_date", reference_time=ref_time), ref_time)

    def test_data_cleaner_clean_ptt_data_integration(self):
        cleaner = DataCleaner(reference_time=datetime(2026, 1, 5, 10, 0, 0))
        raw_df = pd.DataFrame({
            "source": ["ptt_stock", "ptt_stock", "ptt_stock"],
            "fetch_keyword": ["台積電", "台積電", "台積電"],
            "date": ["Wed Aug 20 14:25:36 2026", "12/31", "1/2"],
            "title": ["台積電衝千元", "跨年封關展望", "新年開紅盤"],
            "push_count": ["爆", "15", "X1"],
            "author": ["user1", "user2", "user3"],
            "url": ["http://ptt/1", "http://ptt/2", "http://ptt/3"]
        })
        clean_df = cleaner.clean_ptt_data(raw_df)
        self.assertEqual(len(clean_df), 3)
        self.assertEqual(clean_df['engagement_metric'].tolist(), [100, 15, -10])
        self.assertEqual(clean_df['post_time'].iloc[0], datetime(2026, 8, 20, 14, 25, 36))
        self.assertEqual(clean_df['post_time'].iloc[1], datetime(2025, 12, 31, 12, 0, 0))
        self.assertEqual(clean_df['post_time'].iloc[2], datetime(2026, 1, 2, 12, 0, 0))


class TradingDayRollForwardMappingTests(unittest.TestCase):
    """測試次一交易日歸併法（Roll-Forward Mapping）與雙模式 Cutoff"""

    def setUp(self):
        # 定義 2026 年 8 月中旬的交易日曆 (週五 8/14, 週一 8/17, 週二 8/18, 週三 8/19, 週五 8/21 - 假設 8/20 為國定假日)
        self.trading_days = [
            date(2026, 8, 14), # 週五
            date(2026, 8, 17), # 週一
            date(2026, 8, 18), # 週二
            date(2026, 8, 19), # 週三
            date(2026, 8, 21), # 週五 (8/20 休市)
        ]

    def test_post_market_cutoff_same_day_trading(self):
        # 盤後模式 (Cutoff: 15:30:00)
        # 週五 10:00 與 15:30 -> 歸入週五 8/14
        self.assertEqual(map_timestamp_to_trading_day("2026-08-14 10:00:00", self.trading_days), date(2026, 8, 14))
        self.assertEqual(map_timestamp_to_trading_day("2026-08-14 15:30:00", self.trading_days), date(2026, 8, 14))

    def test_post_market_cutoff_rolls_to_next_trading_day(self):
        # 週五 15:30:01 與 20:00 -> 超過 Cutoff，滾動歸入下週一 8/17
        self.assertEqual(map_timestamp_to_trading_day("2026-08-14 15:30:01", self.trading_days), date(2026, 8, 17))
        self.assertEqual(map_timestamp_to_trading_day("2026-08-14 20:00:00", self.trading_days), date(2026, 8, 17))

    def test_weekend_articles_roll_to_monday(self):
        # 週六 10:00 與 週日 23:00 -> 滾動歸入下週一 8/17
        self.assertEqual(map_timestamp_to_trading_day("2026-08-15 10:00:00", self.trading_days), date(2026, 8, 17))
        self.assertEqual(map_timestamp_to_trading_day("2026-08-16 23:00:00", self.trading_days), date(2026, 8, 17))
        # 週一 08:00 與 週一 15:00 -> 歸入週一 8/17
        self.assertEqual(map_timestamp_to_trading_day("2026-08-17 08:00:00", self.trading_days), date(2026, 8, 17))
        self.assertEqual(map_timestamp_to_trading_day("2026-08-17 15:00:00", self.trading_days), date(2026, 8, 17))
        # 週一 16:00 -> 滾動歸入週二 8/18
        self.assertEqual(map_timestamp_to_trading_day("2026-08-17 16:00:00", self.trading_days), date(2026, 8, 18))

    def test_holiday_roll_forward(self):
        # 8/20 為休假日
        # 週三 8/19 16:00 (超過 15:30) -> 滾動歸入週五 8/21
        self.assertEqual(map_timestamp_to_trading_day("2026-08-19 16:00:00", self.trading_days), date(2026, 8, 21))
        # 週四 8/20 12:00 (休假日) -> 滾動歸入週五 8/21
        self.assertEqual(map_timestamp_to_trading_day("2026-08-20 12:00:00", self.trading_days), date(2026, 8, 21))

    def test_pre_market_cutoff_mode(self):
        # 盤前即時反應模式 (Cutoff: 08:30:00)
        # 週一 08:00 (<= 08:30) -> 歸入週一 8/17 (作為 8/17 開盤前特徵)
        self.assertEqual(
            map_timestamp_to_trading_day("2026-08-17 08:00:00", self.trading_days, cutoff_time="08:30:00"),
            date(2026, 8, 17)
        )
        # 週一 08:35 (> 08:30) -> 盤前特徵窗口已截止，滾動歸入週二 8/18
        self.assertEqual(
            map_timestamp_to_trading_day("2026-08-17 08:35:00", self.trading_days, cutoff_time="08:30:00"),
            date(2026, 8, 18)
        )

    def test_out_of_range_and_empty_calendar_handling(self):
        # 超出日曆最大範圍
        self.assertIsNone(map_timestamp_to_trading_day("2026-08-22 10:00:00", self.trading_days))
        # 空交易日曆
        self.assertIsNone(map_timestamp_to_trading_day("2026-08-14 10:00:00", []))
        # 空 timestamp
        self.assertIsNone(map_timestamp_to_trading_day(None, self.trading_days))


class FeatureAggregatorRollForwardIntegrationTests(unittest.TestCase):
    """測試 FeatureAggregator 整合 Roll-Forward 時週末情緒無損聚合與防洩漏"""

    def setUp(self):
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def test_weekend_articles_accumulated_into_monday_features(self):
        with redirect_stdout(io.StringIO()):
            # 股價表：只有週五 8/14 與 週一 8/17
            df_prices = pd.DataFrame({
                "trade_date": ["2026-08-14", "2026-08-17"],
                "stock_id": ["2330", "2330"],
                "close_price": [1000.0, 1020.0],
                "volume": [10000, 15000]
            })

            # 文章表：包含週五盤前、週五盤後、週六、週日、週一盤中
            df_articles = pd.DataFrame({
                "article_id": [1, 2, 3, 4, 5],
                "fetch_keyword": ["台積電", "台積電", "台積電", "台積電", "台積電"],
                "post_time": [
                    "2026-08-14 10:00:00", # 週五盤中 -> 歸 8/14
                    "2026-08-14 18:00:00", # 週五盤後 -> 滾動歸 8/17
                    "2026-08-15 11:00:00", # 週六全天 -> 滾動歸 8/17
                    "2026-08-16 20:00:00", # 週日全天 -> 滾動歸 8/17
                    "2026-08-17 09:30:00", # 週一盤中 -> 歸 8/17
                ],
                "sentiment_score": [0.8, 0.6, 0.7, 0.9, 0.8]
            })

            df_mapping = pd.DataFrame({
                "keyword": ["台積電"],
                "stock_id": ["2330"],
                "market": ["TWSE"],
                "description": ["中文全稱"]
            })

            df_features = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())

            # 驗證結果
            self.assertEqual(len(df_features), 2)
            
            # 週五 8/14：只有 1 篇 (第 1 篇，分數 0.8)
            row_fri = df_features[df_features["trade_date"] == date(2026, 8, 14)].iloc[0]
            self.assertEqual(row_fri["article_count"], 1)
            self.assertAlmostEqual(row_fri["sentiment_mean"], 0.8)

            # 週一 8/17：成功聚合 4 篇 (第 2, 3, 4, 5 篇，週末全部無損歸併)
            # 平均情緒 = (0.6 + 0.7 + 0.9 + 0.8) / 4 = 3.0 / 4 = 0.75
            row_mon = df_features[df_features["trade_date"] == date(2026, 8, 17)].iloc[0]
            self.assertEqual(row_mon["article_count"], 4)
            self.assertAlmostEqual(row_mon["sentiment_mean"], 0.75)


if __name__ == "__main__":
    unittest.main()
