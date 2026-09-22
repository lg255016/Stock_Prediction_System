import io
import sys
import types
import unittest
from datetime import datetime, date
from contextlib import redirect_stdout
from unittest.mock import MagicMock

# 模組輕量隔離 Stub
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

from src.transform.feature_aggregator import (
    FeatureAggregator,
    compute_bullishness_index,
    compute_agreement_index,
    compute_rsi,
    compute_rolling_volatility
)


class AntweilerMetricsUnitTests(unittest.TestCase):
    """測試 Antweiler & Frank (2004) 輿情量化純函式的數學精確性與邊界防護"""

    def test_bullishness_index_pure_math_and_laplace_smoothing(self):
        # 1. 多頭佔優: Pos=5, Neg=2 -> ln((1+5)/(1+2)) = ln(6/3) = ln(2)
        self.assertAlmostEqual(compute_bullishness_index(5, 2), np.log(2.0))

        # 2. 空頭佔優: Pos=0, Neg=3 -> ln((1+0)/(1+3)) = ln(1/4) = -ln(4)
        self.assertAlmostEqual(compute_bullishness_index(0, 3), np.log(0.25))

        # 3. 多空勢均力敵: Pos=4, Neg=4 -> ln((1+4)/(1+4)) = ln(1) = 0.0
        self.assertAlmostEqual(compute_bullishness_index(4, 4), 0.0)

        # 4. 零文章邊界防護: Pos=0, Neg=0 -> ln((1+0)/(1+0)) = ln(1) = 0.0 (無異常)
        self.assertAlmostEqual(compute_bullishness_index(0, 0), 0.0)

        # 5. Pandas Series 向量化支援
        s_pos = pd.Series([5, 0, 4, 0])
        s_neg = pd.Series([2, 3, 4, 0])
        s_res = compute_bullishness_index(s_pos, s_neg)
        self.assertListEqual(
            [round(x, 4) for x in s_res.tolist()],
            [round(np.log(2.0), 4), round(np.log(0.25), 4), 0.0, 0.0]
        )

    def test_agreement_index_pure_math_and_extreme_consensus(self):
        # 1. 完全多頭共識: Pos=10, Neg=0 -> ratio=1.0 -> 1 - sqrt(1 - 1) = 1.0
        self.assertAlmostEqual(compute_agreement_index(10, 0), 1.0)

        # 2. 完全空頭共識: Pos=0, Neg=8 -> ratio=-1.0 -> 1 - sqrt(1 - 1) = 1.0
        self.assertAlmostEqual(compute_agreement_index(0, 8), 1.0)

        # 3. 最大分歧 (多空各半): Pos=5, Neg=5 -> ratio=0.0 -> 1 - sqrt(1 - 0) = 0.0
        self.assertAlmostEqual(compute_agreement_index(5, 5), 0.0)

        # 4. 零文章邊界: Pos=0, Neg=0 -> total=0 -> 定義為 0.0 (無共識)
        self.assertAlmostEqual(compute_agreement_index(0, 0), 0.0)

        # 5. 部分共識: Pos=3, Neg=1 -> ratio=(3-1)/4=0.5 -> 1 - sqrt(1 - 0.25) = 1 - sqrt(0.75)
        expected = 1.0 - np.sqrt(0.75)
        self.assertAlmostEqual(compute_agreement_index(3, 1), expected)

        # 6. Pandas Series 向量化支援
        s_pos = pd.Series([10, 0, 5, 0, 3])
        s_neg = pd.Series([0, 8, 5, 0, 1])
        s_res = compute_agreement_index(s_pos, s_neg)
        self.assertListEqual(
            [round(x, 4) for x in s_res.tolist()],
            [1.0, 1.0, 0.0, 0.0, round(expected, 4)]
        )


class TechnicalAndRiskMetricsUnitTests(unittest.TestCase):
    """測試 RSI-14 與滾動歷史波動率純函式之數學精確性與 Warm-up 補值"""

    def test_compute_rsi_pure_math_and_neutral_warmup(self):
        # 1. 超短序列 (長度 < 2): 補中立值 50.0
        s_short = pd.Series([100.0])
        self.assertListEqual(compute_rsi(s_short).tolist(), [50.0])

        # 2. 持平價格 (無漲無跌): RSI 維持中立 50.0
        s_flat = pd.Series([100.0] * 15)
        res_flat = compute_rsi(s_flat, period=14)
        self.assertTrue((res_flat == 50.0).all())

        # 3. 連續大漲 (只有 Gain 沒有 Loss): RSI = 100.0
        s_up = pd.Series([100.0 + i * 5.0 for i in range(20)])
        res_up = compute_rsi(s_up, period=14)
        # 前 13 天為 Warm-up (50.0), 第 14 天起因為 avg_loss=0 且 avg_gain>0 轉為 100.0
        self.assertEqual(res_up.iloc[14], 100.0)
        self.assertEqual(res_up.iloc[-1], 100.0)

        # 4. 連續大跌 (只有 Loss 沒有 Gain): RSI = 0.0
        s_down = pd.Series([200.0 - i * 5.0 for i in range(20)])
        res_down = compute_rsi(s_down, period=14)
        self.assertEqual(res_down.iloc[14], 0.0)
        self.assertEqual(res_down.iloc[-1], 0.0)

    def test_compute_rolling_volatility_annualization_and_warmup(self):
        # 1. 樣本數 < 2: 補 0.0
        s_single = pd.Series([0.05])
        self.assertEqual(compute_rolling_volatility(s_single, window=5).iloc[0], 0.0)

        # 2. 波動率為零 (報酬率完全相同): 滾動標準差為 0.0
        s_const = pd.Series([0.01] * 10)
        res_const = compute_rolling_volatility(s_const, window=5, annualize=True)
        self.assertAlmostEqual(res_const.iloc[-1], 0.0)

        # 3. 常態波動序列年化計算驗證
        returns = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02, 0.005, -0.008])
        res_vol = compute_rolling_volatility(returns, window=5, annualize=True)
        # 驗證最後一筆: 過去 5 天 returns[2:7] 的標準差 * sqrt(252)
        expected_std = returns.iloc[2:7].std() * np.sqrt(252.0)
        self.assertAlmostEqual(res_vol.iloc[-1], expected_std)


class FeatureAggregatorResearchIntegrationTests(unittest.TestCase):
    """測試 FeatureAggregator 整合產出 18 欄位特徵契約與跨股票分組隔離"""

    def setUp(self):
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def test_feature_aggregator_full_pipeline_contract_18_columns(self):
        with redirect_stdout(io.StringIO()):
            # 建立 15 天股價序列以驗證 RSI-14 與 Volatility-5D
            dates = pd.date_range("2026-08-01", periods=16, freq="D")
            prices = [100.0, 102.0, 101.0, 103.0, 105.0, 104.0, 106.0, 108.0,
                      107.0, 109.0, 111.0, 110.0, 112.0, 115.0, 114.0, 116.0]
            df_prices = pd.DataFrame({
                "trade_date": dates.strftime("%Y-%m-%d"),
                "stock_id": ["2330"] * 16,
                "close_price": prices,
                "volume": [1000] * 16
            })
            df_articles = pd.DataFrame({
                "article_id": [1, 2],
                "fetch_keyword": ["台積電", "台積電"],
                "post_time": ["2026-08-01 10:00:00", "2026-08-02 10:00:00"],
                "sentiment_score": [0.80, 0.20]
            })
            df_mapping = pd.DataFrame({
                "keyword": ["台積電"],
                "stock_id": ["2330"],
                "market": ["TWSE"],
                "description": ["台積電"]
            })

            df_feat = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            self.assertEqual(len(df_feat), 16)

            # 驗證輸出包含所有 16 項標準特徵欄位
            expected_cols = [
                'trade_date', 'stock_id', 'close_price', 'volume',
                'return_1d', 'rsi_14', 'volatility_5d', 'volatility_20d',
                'article_count', 'sentiment_mean', 'bullishness_index', 'agreement_index',
                'sentiment_3d_ma', 'sentiment_5d_ma', 'sentiment_lag_1', 'sentiment_lag_2'
            ]
            for col in expected_cols:
                self.assertIn(col, df_feat.columns, f"缺少契約特徵欄位: {col}")

            # 驗證前 13 天 RSI 為 50.0 (Warm-up), 第 14 天起 RSI 正常計算
            self.assertEqual(df_feat["rsi_14"].iloc[0], 50.0)
            self.assertGreater(df_feat["rsi_14"].iloc[14], 50.0)

            # 驗證 volatility_5d 在第 5 天起正常計算
            self.assertGreater(df_feat["volatility_5d"].iloc[5], 0.0)

    def test_multi_stock_isolation_full_research_features(self):
        with redirect_stdout(io.StringIO()):
            # 2330 (大漲) vs NVDA (大跌)
            dates = ["2026-08-01", "2026-08-02", "2026-08-03"]
            df_prices = pd.DataFrame({
                "trade_date": dates * 2,
                "stock_id": ["2330"] * 3 + ["NVDA"] * 3,
                "close_price": [100.0, 110.0, 120.0, 100.0, 90.0, 80.0],
                "volume": [1000] * 6
            })
            df_articles = pd.DataFrame({
                "article_id": [1, 2],
                "fetch_keyword": ["台積電", "輝達"],
                "post_time": ["2026-08-01 10:00:00", "2026-08-01 10:00:00"],
                "sentiment_score": [0.90, 0.10]
            })
            df_mapping = pd.DataFrame({
                "keyword": ["台積電", "輝達"],
                "stock_id": ["2330", "NVDA"],
                "market": ["TWSE", "US"],
                "description": ["台積電", "輝達"]
            })

            df_feat = self.aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            
            df_2330 = df_feat[df_feat["stock_id"] == "2330"].sort_values("trade_date")
            df_nvda = df_feat[df_feat["stock_id"] == "NVDA"].sort_values("trade_date")

            # 2330 報酬率均為正: ln(110/100) > 0
            self.assertGreater(df_2330["return_1d"].iloc[1], 0.0)
            self.assertAlmostEqual(df_2330["bullishness_index"].iloc[0], np.log(2.0))

            # NVDA 報酬率均為負: ln(90/100) < 0
            self.assertLess(df_nvda["return_1d"].iloc[1], 0.0)
            self.assertAlmostEqual(df_nvda["bullishness_index"].iloc[0], np.log(0.5))


if __name__ == "__main__":
    unittest.main()
