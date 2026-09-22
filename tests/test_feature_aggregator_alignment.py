import io
import sys
import types
import unittest
from datetime import datetime, date, time
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

# 為測試環境隔離提供輕量 Stub
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
import numpy as np

from src.transform.feature_aggregator import FeatureAggregator


class TimeSeriesFeatureAndLagTests(unittest.TestCase):
    """測試多日滾動與滯後特徵 (Rolling & Lagged Features) 的數學正確性與隔離性"""

    def setUp(self):
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def test_multi_day_rolling_and_lags_single_stock(self):
        with redirect_stdout(io.StringIO()):
            df_prices = pd.DataFrame({
                "trade_date": ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"],
                "stock_id": ["2330"] * 5,
                "close_price": [100.0, 105.0, 102.0, 108.0, 110.0],
                "volume": [1000] * 5
            })
            df_articles = pd.DataFrame({
                "article_id": [1, 2, 3, 4, 5],
                "fetch_keyword": ["台積電"] * 5,
                "post_time": [
                    "2026-08-03 10:00:00",
                    "2026-08-04 10:00:00",
                    "2026-08-05 10:00:00",
                    "2026-08-06 10:00:00",
                    "2026-08-07 10:00:00"
                ],
                "sentiment_score": [0.6, 0.8, 0.4, 0.9, 0.5]
            })
            df_mapping = pd.DataFrame({
                "keyword": ["台積電"],
                "stock_id": ["2330"],
                "market": ["TWSE"],
                "description": ["中文全稱"]
            })

            df_feat = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            self.assertEqual(len(df_feat), 5)

            # 驗證 sentiment_mean 序列
            self.assertListEqual(df_feat["sentiment_mean"].round(4).tolist(), [0.6, 0.8, 0.4, 0.9, 0.5])

            # 驗證 sentiment_3d_ma: [0.6, (0.6+0.8)/2=0.7, (0.6+0.8+0.4)/3=0.6, (0.8+0.4+0.9)/3=0.7, (0.4+0.9+0.5)/3=0.6]
            self.assertListEqual(df_feat["sentiment_3d_ma"].round(4).tolist(), [0.6, 0.7, 0.6, 0.7, 0.6])

            # 驗證 sentiment_lag_1: [0.5(補值), 0.6, 0.8, 0.4, 0.9]
            self.assertListEqual(df_feat["sentiment_lag_1"].round(4).tolist(), [0.5, 0.6, 0.8, 0.4, 0.9])

            # 驗證 sentiment_lag_2: [0.5(補值), 0.5(補值), 0.6, 0.8, 0.4]
            self.assertListEqual(df_feat["sentiment_lag_2"].round(4).tolist(), [0.5, 0.5, 0.6, 0.8, 0.4])

            # 驗證 return_1d (歷史報酬率): 第一天為 0.0, 第二天 ln(105/100)
            self.assertAlmostEqual(df_feat["return_1d"].iloc[0], 0.0)
            self.assertAlmostEqual(df_feat["return_1d"].iloc[1], np.log(105.0 / 100.0))

    def test_multi_stock_isolation_prevents_lag_cross_contamination(self):
        with redirect_stdout(io.StringIO()):
            # 兩檔股票: 2330 與 NVDA
            df_prices = pd.DataFrame({
                "trade_date": ["2026-08-03", "2026-08-04", "2026-08-03", "2026-08-04"],
                "stock_id": ["2330", "2330", "NVDA", "NVDA"],
                "close_price": [1000.0, 1020.0, 120.0, 130.0],
                "volume": [10000, 12000, 50000, 60000]
            })
            df_articles = pd.DataFrame({
                "article_id": [1, 2, 3, 4],
                "fetch_keyword": ["台積電", "台積電", "輝達", "輝達"],
                "post_time": [
                    "2026-08-03 10:00:00", "2026-08-04 10:00:00",
                    "2026-08-03 10:00:00", "2026-08-04 10:00:00"
                ],
                "sentiment_score": [0.8, 0.9, 0.2, 0.3]
            })
            df_mapping = pd.DataFrame({
                "keyword": ["台積電", "輝達"],
                "stock_id": ["2330", "NVDA"],
                "market": ["TWSE", "US"],
                "description": ["台積電", "輝達"]
            })

            df_feat = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            
            # 檢查 2330 的特徵
            df_2330 = df_feat[df_feat["stock_id"] == "2330"].sort_values("trade_date")
            self.assertListEqual(df_2330["sentiment_lag_1"].tolist(), [0.5, 0.8])

            # 檢查 NVDA 的特徵：第一天絕對不可取到 2330 的值，必須是 NVDA 自身初始補值 0.5
            df_nvda = df_feat[df_feat["stock_id"] == "NVDA"].sort_values("trade_date")
            self.assertListEqual(df_nvda["sentiment_lag_1"].tolist(), [0.5, 0.2])


class TargetLabelGenerationTests(unittest.TestCase):
    """測試機器學習目標標籤 (Target Labels) 生成合約與無未來資料處理"""

    def setUp(self):
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def test_target_label_next_day_returns_and_binary_classification(self):
        df_features = pd.DataFrame({
            "trade_date": [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)],
            "stock_id": ["2330", "2330", "2330"],
            "close_price": [100.0, 110.0, 105.0],  # 8/3->8/4 上漲 (+10%), 8/4->8/5 下跌 (-4.5%)
            "volume": [1000, 1200, 1100],
            "sentiment_mean": [0.7, 0.8, 0.3]
        })

        df_target = self.aggregator.generate_target_labels(df_features)

        # 8/3 (Day 1): 預測目標為 8/4 收盤價 110.0, 報酬率 ln(110/100) > 0, 標籤為 1 (上漲)
        row_1 = df_target.iloc[0]
        self.assertEqual(row_1["target_next_close"], 110.0)
        self.assertAlmostEqual(row_1["target_return_1d"], np.log(110.0 / 100.0))
        self.assertEqual(row_1["target_up_down"], 1)

        # 8/4 (Day 2): 預測目標為 8/5 收盤價 105.0, 報酬率 ln(105/110) < 0, 標籤為 0 (下跌)
        row_2 = df_target.iloc[1]
        self.assertEqual(row_2["target_next_close"], 105.0)
        self.assertAlmostEqual(row_2["target_return_1d"], np.log(105.0 / 110.0))
        self.assertEqual(row_2["target_up_down"], 0)

        # 8/5 (Day 3 - 最後一天): 未來股價尚未發生，目標一律為 NaN
        row_3 = df_target.iloc[2]
        self.assertTrue(pd.isna(row_3["target_next_close"]))
        self.assertTrue(pd.isna(row_3["target_return_1d"]))
        self.assertTrue(pd.isna(row_3["target_up_down"]))

    def test_label_end_date_defaults_to_t_plus_1(self):
        """UG-G1-SB1：預設 label_horizon=1 時，label_end_date 應等於個股下一交易日"""
        df_features = pd.DataFrame({
            "trade_date": [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)],
            "stock_id": ["2330", "2330", "2330"],
            "close_price": [100.0, 110.0, 105.0],
            "volume": [1000, 1200, 1100],
            "sentiment_mean": [0.7, 0.8, 0.3]
        })

        df_target = self.aggregator.generate_target_labels(df_features)

        self.assertEqual(df_target.iloc[0]["label_end_date"], date(2026, 8, 4))
        self.assertEqual(df_target.iloc[1]["label_end_date"], date(2026, 8, 5))
        self.assertTrue(pd.isna(df_target.iloc[2]["label_end_date"]))

    def test_label_end_date_respects_explicit_label_horizon(self):
        """UG-G1-SB1：label_horizon=2 時，label_end_date 應為 T+2 交易日；供 Purge/Triple-Barrier 對齊"""
        df_features = pd.DataFrame({
            "trade_date": [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6)],
            "stock_id": ["2330"] * 4,
            "close_price": [100.0, 110.0, 105.0, 108.0],
            "volume": [1000, 1200, 1100, 1300],
            "sentiment_mean": [0.7, 0.8, 0.3, 0.5]
        })

        df_target = self.aggregator.generate_target_labels(df_features, label_horizon=2)

        self.assertEqual(df_target.iloc[0]["label_end_date"], date(2026, 8, 5))
        self.assertEqual(df_target.iloc[1]["label_end_date"], date(2026, 8, 6))
        self.assertTrue(pd.isna(df_target.iloc[2]["label_end_date"]))
        self.assertTrue(pd.isna(df_target.iloc[3]["label_end_date"]))

        with self.assertRaises(ValueError):
            self.aggregator.generate_target_labels(df_features, label_horizon=0)

    def test_label_end_date_computed_per_stock_calendar(self):
        """UG-G1-SB1：多股票時 label_end_date 依各股自身交易日序列計算，不互相干擾"""
        df_features = pd.DataFrame({
            "trade_date": [
                date(2026, 8, 3), date(2026, 8, 4),
                date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)
            ],
            "stock_id": ["2330", "2330", "2382", "2382", "2382"],
            "close_price": [100.0, 110.0, 50.0, 52.0, 51.0],
            "volume": [1000, 1200, 800, 850, 900],
            "sentiment_mean": [0.7, 0.8, 0.6, 0.5, 0.4]
        })

        df_target = self.aggregator.generate_target_labels(df_features)

        row_2330 = df_target[(df_target["stock_id"] == "2330") & (df_target["trade_date"] == date(2026, 8, 3))].iloc[0]
        self.assertEqual(row_2330["label_end_date"], date(2026, 8, 4))

        row_2382 = df_target[(df_target["stock_id"] == "2382") & (df_target["trade_date"] == date(2026, 8, 4))].iloc[0]
        self.assertEqual(row_2382["label_end_date"], date(2026, 8, 5))


class ZeroLookAheadBiasStrictVerificationTests(unittest.TestCase):
    """嚴格驗證零前視偏誤 (Zero Look-ahead Bias: 修改未來資料對當日特徵完全無影響)"""

    def setUp(self):
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def test_future_data_mutation_does_not_alter_past_features(self):
        with redirect_stdout(io.StringIO()):
            df_mapping = pd.DataFrame({
                "keyword": ["台積電"],
                "stock_id": ["2330"],
                "market": ["TWSE"],
                "description": ["台積電"]
            })

            # 基準資料集: Day 1 (8/3) 與 Day 2 (8/4)
            df_prices_base = pd.DataFrame({
                "trade_date": ["2026-08-03", "2026-08-04"],
                "stock_id": ["2330", "2330"],
                "close_price": [100.0, 105.0],
                "volume": [1000, 1200]
            })
            df_articles_base = pd.DataFrame({
                "article_id": [1, 2],
                "fetch_keyword": ["台積電", "台積電"],
                "post_time": ["2026-08-03 10:00:00", "2026-08-04 10:00:00"],
                "sentiment_score": [0.6, 0.8]
            })
            df_feat_base = self.aggregator.generate_daily_features(df_prices_base, df_articles_base, df_mapping, df_comments=pd.DataFrame())
            day1_feat_base = df_feat_base[df_feat_base["trade_date"] == date(2026, 8, 3)].iloc[0].to_dict()

            # 劇烈修改未來的資料 (將 Day 2 股價改為 99999.0, 情緒改為 0.001, 並新增 Day 3 極端文章)
            df_prices_mutated = pd.DataFrame({
                "trade_date": ["2026-08-03", "2026-08-04", "2026-08-05"],
                "stock_id": ["2330", "2330", "2330"],
                "close_price": [100.0, 99999.0, 1.0],
                "volume": [1000, 9999999, 1]
            })
            df_articles_mutated = pd.DataFrame({
                "article_id": [1, 2, 3],
                "fetch_keyword": ["台積電", "台積電", "台積電"],
                "post_time": ["2026-08-03 10:00:00", "2026-08-04 10:00:00", "2026-08-05 10:00:00"],
                "sentiment_score": [0.6, 0.001, 0.0]
            })
            df_feat_mutated = self.aggregator.generate_daily_features(df_prices_mutated, df_articles_mutated, df_mapping, df_comments=pd.DataFrame())
            day1_feat_mutated = df_feat_mutated[df_feat_mutated["trade_date"] == date(2026, 8, 3)].iloc[0].to_dict()

            # 驗證: 無論未來如何劇烈變動，Day 1 (8/3) 的所有特徵值完全一模一樣！(Zero Look-ahead Bias)
            #
            # NaN 的比較必須特別處理：UG-G2-SB4 起，三個留言特徵在無留言資料時
            # 合法地為 NaN（FEATURE_REGISTRY.md §5A.5），而 NaN != NaN，
            # 直接用 assertEqual 會把「兩邊都正確地是 NULL」誤判為洩漏。
            # 兩邊皆 NaN 代表該欄位未受未來資料影響，是通過而非失敗。
            for k in day1_feat_base:
                base_val, mutated_val = day1_feat_base[k], day1_feat_mutated[k]
                if pd.isna(base_val) and pd.isna(mutated_val):
                    continue
                self.assertEqual(
                    base_val,
                    mutated_val,
                    f"特徵欄位 {k} 受到未來資料影響，發生 Look-ahead Bias 洩漏！"
                )

    def test_post_market_articles_strictly_isolated_from_same_day_features(self):
        with redirect_stdout(io.StringIO()):
            # 測試當天 16:00 (盤後) 發布的文章，絕對不會出現在當天特徵中，而是嚴格留至隔天
            df_prices = pd.DataFrame({
                "trade_date": ["2026-08-03", "2026-08-04"],
                "stock_id": ["2330", "2330"],
                "close_price": [100.0, 102.0],
                "volume": [1000, 1100]
            })
            df_articles = pd.DataFrame({
                "article_id": [1, 2],
                "fetch_keyword": ["台積電", "台積電"],
                "post_time": [
                    "2026-08-03 10:00:00",  # Day 1 盤中 (納入 Day 1)
                    "2026-08-03 16:00:00",  # Day 1 盤後 (>15:30，必須隔離並推至 Day 2)
                ],
                "sentiment_score": [0.8, 0.2]
            })
            df_mapping = pd.DataFrame({
                "keyword": ["台積電"],
                "stock_id": ["2330"],
                "market": ["TWSE"],
                "description": ["台積電"]
            })

            df_feat = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            
            # Day 1 (8/3) 特徵: 只包含第 1 篇 (score: 0.8), 文章數為 1
            row_day1 = df_feat[df_feat["trade_date"] == date(2026, 8, 3)].iloc[0]
            self.assertEqual(row_day1["article_count"], 1)
            self.assertAlmostEqual(row_day1["sentiment_mean"], 0.8)

            # Day 2 (8/4) 特徵: 包含第 2 篇 (score: 0.2), 文章數為 1
            row_day2 = df_feat[df_feat["trade_date"] == date(2026, 8, 4)].iloc[0]
            self.assertEqual(row_day2["article_count"], 1)
            self.assertAlmostEqual(row_day2["sentiment_mean"], 0.2)


if __name__ == "__main__":
    unittest.main()
