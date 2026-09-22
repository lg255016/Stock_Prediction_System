"""
tests/test_thematic_feature_spillover.py — 題材情緒溢出特徵引擎專項測試 (SB-TH2)

測試範疇：
1. 題材情緒 100% 溢出補位驗證 (無直接個股討論時，享受所屬題材熱度與情緒)。
2. 動態加權融合演算法驗證 (有直接個股討論時，70% 直接 + 30% 題材加權融合)。
3. 嚴格維持 18 欄位特徵契約與型態不變性。
4. 與 ML 冠軍模型 (RandomForest) 與推論引擎 (StockTrendPredictor) 的端到端相容性。
"""

import datetime
import unittest
import numpy as np
import pandas as pd

from src.transform.feature_aggregator import FeatureAggregator
from src.ml.model_trainer import ALL_MULTIMODAL_FEATURE_COLS, MultiModalTrainer
from src.ml.predictor import StockTrendPredictor


class ThematicFeatureSpilloverTests(unittest.TestCase):
    """測試題材情緒溢出特徵工程與動態加權演算法"""

    def setUp(self):
        self.aggregator = FeatureAggregator()
        self.trade_dates = [
            datetime.date(2026, 8, 1),
            datetime.date(2026, 8, 2),
            datetime.date(2026, 8, 3),
            datetime.date(2026, 8, 4),
            datetime.date(2026, 8, 5),
        ]

    def _create_dummy_prices(self, stock_id: str = "3081") -> pd.DataFrame:
        records = []
        base_price = 100.0
        for d in self.trade_dates:
            records.append({
                "trade_date": d,
                "stock_id": stock_id,
                "open_price": base_price,
                "high_price": base_price + 2.0,
                "low_price": base_price - 1.0,
                "close_price": base_price + 1.0,
                "volume": 50000,
            })
            base_price += 2.0
        return pd.DataFrame(records)

    def test_thematic_spillover_pure_theme_fallback_when_no_direct_articles(self):
        """測試無個股直接文章時，題材情緒 100% 溢出補位"""
        df_prices = self._create_dummy_prices("3081")

        # 僅有「矽光子」題材文章，無「聯亞」直接文章
        df_articles = pd.DataFrame([
            {
                "article_id": 1,
                "source": "ptt_stock",
                "fetch_keyword": "矽光子",
                "post_time": pd.Timestamp("2026-08-01 10:00:00"),
                "sentiment_score": 0.80,
                "title": "[新聞] 矽光子概念股買盤湧入"
            },
            {
                "article_id": 2,
                "source": "ptt_stock",
                "fetch_keyword": "矽光子",
                "post_time": pd.Timestamp("2026-08-01 11:30:00"),
                "sentiment_score": 0.90,
                "title": "[標的] 矽光子大軍 多"
            },
        ])

        df_mapping = pd.DataFrame([
            {"keyword": "聯亞", "stock_id": "3081"}
        ])

        df_theme_mapping = pd.DataFrame([
            {"theme_keyword": "矽光子", "stock_id": "3081", "relevance_weight": 1.0}
        ])

        df_features = self.aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame()
        )

        row_aug1 = df_features[df_features["trade_date"] == datetime.date(2026, 8, 1)].iloc[0]
        # 題材情緒平均 = (0.80 + 0.90) / 2 = 0.85
        self.assertEqual(row_aug1["article_count"], 2)
        self.assertAlmostEqual(row_aug1["sentiment_mean"], 0.85, places=4)
        # 驗證看多指數因題材正面而大於 0
        self.assertGreater(row_aug1["bullishness_index"], 0.0)

    def test_thematic_spillover_dynamic_fusion_70_30_when_both_exist(self):
        """測試個股與題材兼備時，精確執行 70% 直接 + 30% 題材加權融合"""
        df_prices = self._create_dummy_prices("2330")

        # 包含台積電直接文章 (0.60) 與 CoWoS 題材文章 (0.90)
        df_articles = pd.DataFrame([
            {
                "article_id": 1,
                "source": "ptt_stock",
                "fetch_keyword": "台積電",
                "post_time": pd.Timestamp("2026-08-01 10:00:00"),
                "sentiment_score": 0.60,
                "title": "[標的] 2330 台積電 穩健多"
            },
            {
                "article_id": 2,
                "source": "ptt_stock",
                "fetch_keyword": "CoWoS",
                "post_time": pd.Timestamp("2026-08-01 14:00:00"),
                "sentiment_score": 0.90,
                "title": "[新聞] CoWoS 產能吃緊 概念股全面大漲"
            },
        ])

        df_mapping = pd.DataFrame([
            {"keyword": "台積電", "stock_id": "2330"}
        ])

        df_theme_mapping = pd.DataFrame([
            {"theme_keyword": "CoWoS", "stock_id": "2330", "relevance_weight": 1.0}
        ])

        df_features = self.aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame()
        )

        row_aug1 = df_features[df_features["trade_date"] == datetime.date(2026, 8, 1)].iloc[0]
        # 理論融合值 = 0.70 * 0.60 + 0.30 * 0.90 = 0.42 + 0.27 = 0.69
        self.assertEqual(row_aug1["article_count"], 2)
        self.assertAlmostEqual(row_aug1["sentiment_mean"], 0.69, places=4)

    def test_thematic_spillover_exact_18_columns_and_type_invariant(self):
        """測試題材溢出特徵計算後，18 欄位契約與型態 100% 保持不變"""
        df_prices = self._create_dummy_prices("6488")
        df_articles = pd.DataFrame([
            {
                "article_id": 1,
                "source": "ptt_stock",
                "fetch_keyword": "矽光子",
                "post_time": pd.Timestamp("2026-08-02 09:30:00"),
                "sentiment_score": 0.75,
                "title": "[新聞] 矽光子材料出貨大增"
            }
        ])
        df_mapping = pd.DataFrame([{"keyword": "環球晶", "stock_id": "6488"}])
        df_theme_mapping = pd.DataFrame([{"theme_keyword": "矽光子", "stock_id": "6488", "relevance_weight": 0.8}])

        df_features = self.aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame()
        )

        # 1. 驗證欄位完整性
        for col in ALL_MULTIMODAL_FEATURE_COLS:
            self.assertIn(col, df_features.columns)

        # 2. 驗證「型態不變」的正確意涵（2026-09-08，`PRE-G3-04`／D5 落地後修正）：
        #    18 欄契約仍全部存在；不受 D5 U 分支影響的欄位仍應全數有值。
        #    ⚠ 舊斷言是「isna().sum().sum() == 0」，建立在「空日一律填 0.5」
        #    的舊行為上——D5 之後，本 fixture 的 5 個交易日僅 1 日（08-02）
        #    有直接文章，其餘 4 日為 SUCCESS_EMPTY（article_count==0）。
        #    這些日子的 sentiment_mean 及其四個衍生欄，除落在序列前 1~2 列
        #    的真暖機期外，保持 NULL 是 D5 裁決要求的正確行為（成因 U，
        #    見 FEATURE_REGISTRY.md §5A.2），不是型態被破壞。
        u_affected_cols = {
            "sentiment_mean", "sentiment_3d_ma", "sentiment_5d_ma",
            "sentiment_lag_1", "sentiment_lag_2",
        }
        non_u_cols = [c for c in ALL_MULTIMODAL_FEATURE_COLS
                     if c not in u_affected_cols]
        self.assertEqual(
            df_features[non_u_cols].isna().sum().sum(), 0,
            "18 欄契約中，不受 D5 U 分支影響的欄位仍應全數有值")
        self.assertGreater(
            df_features[list(u_affected_cols)].isna().sum().sum(), 0,
            "本 fixture 刻意含 4 個空日，理應在 U 分支欄位上出現 NULL —— "
            "若此處為 0，代表 D5 的 NULL 化沒有生效")

    def test_thematic_spillover_ml_predictor_inference_compatibility(self):
        """測試題材特徵注入後，ML 模型訓練與即時推論零誤差相容"""
        df_prices = self._create_dummy_prices("2382")
        df_articles = pd.DataFrame([
            {
                "article_id": 1,
                "source": "ptt_stock",
                "fetch_keyword": "AI伺服器",
                "post_time": pd.Timestamp("2026-08-01 10:00:00"),
                "sentiment_score": 0.88,
                "title": "[新聞] AI 伺服器出貨量暴增"
            }
        ])
        df_mapping = pd.DataFrame([{"keyword": "廣達", "stock_id": "2382"}])
        df_theme_mapping = pd.DataFrame([{"theme_keyword": "AI伺服器", "stock_id": "2382", "relevance_weight": 1.0}])

        df_features = self.aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame()
        )
        df_features = self.aggregator.generate_target_labels(df_features)

        # 使用隨機森林訓練器擬合並推論
        trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust", random_state=42)
        trainer.train_and_predict_fold(df_features, df_features)
        predictor = StockTrendPredictor(trainer=trainer)

        res = predictor.predict_latest(df_features)
        self.assertEqual(res["stock_id"], "2382")
        self.assertIn(res["predicted_direction"], ("UP", "DOWN"))
    def test_thematic_spillover_decimal_type_safety(self):
        """測試真實 PostgreSQL 讀取之 Decimal 物件輸入時，特徵融合與運算零錯誤 (CHAL-008 防回歸)"""
        from decimal import Decimal
        df_prices = self._create_dummy_prices("3081")
        # 模擬 PostgreSQL 撈出之 Decimal 物件
        df_articles = pd.DataFrame([
            {
                "article_id": 1,
                "source": "ptt_stock",
                "fetch_keyword": "聯亞",
                "post_time": pd.Timestamp("2026-08-01 10:00:00"),
                "sentiment_score": Decimal("0.6500"),
                "title": "[新聞] 聯亞營收創高"
            },
            {
                "article_id": 2,
                "source": "ptt_stock",
                "fetch_keyword": "矽光子",
                "post_time": pd.Timestamp("2026-08-01 11:00:00"),
                "sentiment_score": Decimal("0.8500"),
                "title": "[情報] 矽光子聯盟大擴產"
            }
        ])
        df_mapping = pd.DataFrame([{"keyword": "聯亞", "stock_id": "3081"}])
        df_theme_mapping = pd.DataFrame([
            {"theme_keyword": "矽光子", "stock_id": "3081", "relevance_weight": Decimal("1.00")}
        ])

        # 執行特徵聚合，驗證絕不拋出 TypeError: unsupported operand type(s) for *: 'float' and 'decimal.Decimal'
        df_features = self.aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame()
        )

        row_aug1 = df_features[df_features["trade_date"] == datetime.date(2026, 8, 1)].iloc[0]
        # 預期 0.70 * 0.65 + 0.30 * 0.85 = 0.455 + 0.255 = 0.71
        self.assertAlmostEqual(row_aug1["sentiment_mean"], 0.71, places=4)
        self.assertIsInstance(row_aug1["sentiment_mean"], (float, np.floating))


if __name__ == "__main__":
    unittest.main()
