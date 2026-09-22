"""
tests/test_real_articles_pipeline.py — 真實社群輿情文章讀取與三階查詢引擎測試 (SB-ART1 ~ SB-ART3)
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.ui.data_loader import _fetch_real_stock_articles_from_db, load_stock_articles, DataMode


class RealArticlesPipelineTests(unittest.TestCase):
    """測試三重階梯式真實社群文章查詢引擎"""

    def test_fetch_real_articles_with_entity_and_theme_and_title(self):
        """測試同時透過個股、題材與標題關鍵字查詢真實文章"""
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect") as mock_connect, \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer = mock_writer_cls.return_value
            mock_writer.db_config = {"database": "test", "user": "u", "password": "<test>"}
            mock_conn = mock_connect.return_value
            mock_cur = mock_conn.cursor.return_value.__enter__.return_value

            # 1. 模擬 entity_mapping 回傳
            mock_cur.fetchall.side_effect = [
                [("聯亞",)],  # entity_mapping
                [("矽光子", "聯亞")]  # theme_stock_mapping
            ]

            # 2. 模擬 market_articles 查詢回傳
            df_db_arts = pd.DataFrame([
                {
                    "publish_time": "2026-08-20 14:30",
                    "stock_id": "3081",
                    "title": "[新聞] 聯亞矽光子出貨動能強勁",
                    "sentiment_score": 0.82,
                    "sentiment_label": "看多",
                    "push_count": 45,
                    "source": "ptt_stock",
                    "url": "https://ptt.cc/1"
                },
                {
                    "publish_time": "2026-08-20 11:15",
                    "stock_id": "3081",
                    "title": "[標的] 3081 破底翻 多",
                    "sentiment_score": 0.75,
                    "sentiment_label": "看多",
                    "push_count": 30,
                    "source": "ptt_stock",
                    "url": "https://ptt.cc/2"
                }
            ])
            mock_read_sql.return_value = df_db_arts

            df_res = _fetch_real_stock_articles_from_db("3081", limit=20)
            self.assertIsNotNone(df_res)
            self.assertEqual(len(df_res), 2)
            self.assertEqual(df_res.iloc[0]["title"], "[新聞] 聯亞矽光子出貨動能強勁")
            self.assertIn("url", df_res.columns)

    def test_fetch_real_articles_empty_returns_dataframe_with_contract(self):
        """測試資料庫查無文章時，安全回傳符合欄位契約之空 DataFrame (非 None)"""
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect") as mock_connect, \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer = mock_writer_cls.return_value
            mock_writer.db_config = {"database": "test", "user": "u", "password": "<test>"}
            mock_conn = mock_connect.return_value
            mock_cur = mock_conn.cursor.return_value.__enter__.return_value

            mock_cur.fetchall.side_effect = [
                [],  # entity_mapping empty
                []   # theme_stock_mapping empty
            ]
            mock_read_sql.return_value = pd.DataFrame()

            df_res = _fetch_real_stock_articles_from_db("9999", limit=20)
            self.assertIsNotNone(df_res)
            self.assertTrue(df_res.empty)
            expected_cols = ['publish_time', 'stock_id', 'title', 'sentiment_score', 'sentiment_label', 'push_count', 'source', 'url']
            for c in expected_cols:
                self.assertIn(c, df_res.columns)

    def test_fetch_real_articles_deduplication(self):
        """測試同標題與時間之文章正確去重"""
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect") as mock_connect, \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer = mock_writer_cls.return_value
            mock_writer.db_config = {"database": "test", "user": "u", "password": "<test>"}
            mock_conn = mock_connect.return_value
            mock_cur = mock_conn.cursor.return_value.__enter__.return_value

            mock_cur.fetchall.side_effect = [
                [("台積電",)],
                [("CoWoS", "台積電")]
            ]
            # 模擬包含重複項之查詢結果
            df_duplicate_arts = pd.DataFrame([
                {
                    "publish_time": "2026-08-20 10:00",
                    "stock_id": "2330",
                    "title": "[新聞] 台積電先進製程擴產",
                    "sentiment_score": 0.88,
                    "sentiment_label": "看多",
                    "push_count": 50,
                    "source": "ptt_stock",
                    "url": "https://ptt.cc/1"
                },
                {
                    "publish_time": "2026-08-20 10:00",
                    "stock_id": "2330",
                    "title": "[新聞] 台積電先進製程擴產",
                    "sentiment_score": 0.88,
                    "sentiment_label": "看多",
                    "push_count": 50,
                    "source": "ptt_stock",
                    "url": "https://ptt.cc/1"
                }
            ])
            mock_read_sql.return_value = df_duplicate_arts

            df_res = _fetch_real_stock_articles_from_db("2330", limit=10)
            self.assertIsNotNone(df_res)
            self.assertEqual(len(df_res), 1)

    def test_load_stock_articles_returns_clean_contract(self):
        """
        HERM-02 修復：測試 load_stock_articles 公開介面（含 DataMode）在 REAL 模式下
        回傳符合規範之 DataFrame。mock DB 使結果具確定性，不依賴真實 DB 內容。
        """
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect") as mock_connect, \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer = mock_writer_cls.return_value
            mock_writer.db_config = {"database": "test", "user": "u", "password": "<test>"}
            mock_conn = mock_connect.return_value
            mock_cur = mock_conn.cursor.return_value.__enter__.return_value
            mock_cur.fetchall.side_effect = [[("台積電",)], [("CoWoS", "台積電")]]
            mock_read_sql.return_value = pd.DataFrame([{
                "publish_time": "2026-08-20 10:00",
                "stock_id": "2330",
                "title": "[新聞] 台積電先進製程擴產",
                "sentiment_score": 0.88,
                "sentiment_label": "看多",
                "push_count": 50,
                "source": "ptt_stock",
                "url": "https://ptt.cc/1"
            }])

            df_articles, mode = load_stock_articles("2330", limit=10)

        self.assertEqual(mode, DataMode.REAL)
        self.assertIsInstance(df_articles, pd.DataFrame)
        expected_cols = ['publish_time', 'stock_id', 'title', 'sentiment_score', 'sentiment_label', 'push_count', 'source', 'url']
        for c in expected_cols:
            self.assertIn(c, df_articles.columns)


if __name__ == "__main__":
    unittest.main()
