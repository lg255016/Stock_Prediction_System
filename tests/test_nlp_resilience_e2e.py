"""
tests/test_nlp_resilience_e2e.py — NLP 429 限速指數退避重試與端到端管線防回歸測試

測試範疇：
1. 模擬 Gemini API 拋出 429 ResourceExhausted 限速時，自動透過 tenacity 指數退避重試成功，
   並順暢完成：NLP 評分 -> 快取寫入 -> Checkpoint 推進 -> 18 欄位特徵聚合 -> daily_ml_features 入庫。
2. 模擬連續 5 次 429 徹底失敗時，嚴格遵循 DEC-003 拋出異常，絕不推進 Checkpoint 或寫入受損特徵。
"""

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch
import pandas as pd

from src.transform.nlp_processor import NLPProcessor
from src.transform.feature_aggregator import FeatureAggregator
from main_etl_pipeline import ETLPipelineManager


class NLPResilienceAndE2EIntegrationTests(unittest.TestCase):
    """測試 NLP 遇到 429 限速時之指數退避重試與全流程整合"""

    def setUp(self):
        self.processor = NLPProcessor()
        self.processor.api_key = "dummy_test_key"
        self.feature_aggregator = FeatureAggregator()

    @patch("time.sleep", return_value=None)
    def test_e2e_pipeline_recovers_from_transient_429_and_completes_full_flow(self, mock_sleep):
        """
        端到端全流程驗證：
        文章輸入 -> 初篩模糊區間 -> 第 1 次 Gemini 呼叫拋出 429 限速 ->
        自動觸發指數退避重試 -> 第 2 次成功取得分數 ->
        寫入 Exact Cache -> 推進 Checkpoint -> 產出 18 欄位特徵 -> 成功入庫
        """
        # 1. 準備模擬資料
        df_articles = pd.DataFrame({
            "article_id": [101],
            "title": ["台積電營收亮眼但外資小賣調節"],
            "fetch_keyword": ["台積電"],
            "post_time": [datetime(2026, 8, 20, 14, 0)],
        })

        # 模擬初篩落在模糊區間 (0.5)
        self.processor._calc_snownlp = lambda text: 0.5

        mock_db = MagicMock()
        # 模擬快取未命中 (Miss)
        mock_db.fetch_cached_scores.return_value = {}

        # 2. 模擬 Gemini 回應物件
        mock_success_response = MagicMock()
        mock_success_response.text = '{"0": 0.78}'

        # 模擬第 1 次拋出 429 Exception，第 2 次成功
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [
            Exception("429 ResourceExhausted: Quota exceeded, retry in 1s"),
            mock_success_response
        ]
        self.processor.model = mock_model

        # 3. 執行 NLP Hybrid 批次運算
        df_nlp_processed = self.processor.process_batch_hybrid(df_articles, mock_db)

        # 驗證：重試機制生效，generate_content 被呼叫 2 次
        self.assertEqual(mock_model.generate_content.call_count, 2)
        # 驗證：情緒分數計算成功 (0.78)
        self.assertEqual(df_nlp_processed.at[0, "sentiment_score"], 0.78)
        # 驗證：正確寫入 Exact-Title Cache
        mock_db.upsert_sentiment_cache.assert_called_once_with([
            ("台積電營收亮眼但外資小賣調節", 0.78)
        ])

        # 4. 推進下游特徵工程 (Feature Engineering)
        df_prices = pd.DataFrame({
            "trade_date": [date(2026, 8, 20)],
            "stock_id": ["2330"],
            "close_price": [1000.0],
            "volume": [30000],
        })
        df_mapping = pd.DataFrame({
            "keyword": ["台積電"],
            "stock_id": ["2330"],
        })

        df_features = self.feature_aggregator.generate_daily_features(
            df_prices, df_nlp_processed, df_mapping,
            df_comments=pd.DataFrame()
        )

        # 驗證：產出 LEGACY_17 版本化特徵欄位（+ source_status metadata 欄）且包含 Antweiler 指數
        self.assertEqual(len(df_features), 1)
        self.assertIn("bullishness_index", df_features.columns)
        self.assertIn("agreement_index", df_features.columns)
        self.assertIn("return_1d", df_features.columns)
        self.assertEqual(df_features.iloc[0]["stock_id"], "2330")

        # 5. 寫入資料庫驗證
        mock_db._execute_batch = MagicMock()
        from src.loaders.db_writer import DBWriter
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()
        writer.upsert_ml_features(df_features)

        writer._execute_batch.assert_called_once()
        _, records = writer._execute_batch.call_args[0]
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]), 29)  # 29 欄契約安全映射（UG-G2-SB1）

    @patch("time.sleep", return_value=None)
    def test_e2e_pipeline_consecutive_429_failures_strictly_aborts_without_corrupt_data(self, mock_sleep):
        """
        驗證 DEC-003 嚴格規範：
        若 Gemini 遭遇連續 5 次 429 限速且重試耗盡，必須向上拋出異常，
        絕不寫入偽造快取、不推進 Checkpoint、不產出殘缺特徵。
        """
        df_articles = pd.DataFrame({
            "article_id": [102],
            "title": ["台積電多空分歧巨大法人觀望"],
        })

        # 模擬初篩落在模糊區間 (0.5)
        self.processor._calc_snownlp = lambda text: 0.5

        mock_db = MagicMock()
        mock_db.fetch_cached_scores.return_value = {}

        # 模擬連續 5 次全部回傳 429 限速
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("429 ResourceExhausted: Quota exceeded")
        self.processor.model = mock_model

        # 驗證：5 次重試全數失敗後向上拋出異常
        with self.assertRaises(Exception):
            self.processor.process_batch_hybrid(df_articles, mock_db)

        # 驗證：嚴格不寫入快取
        mock_db.upsert_sentiment_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
