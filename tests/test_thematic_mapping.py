"""
tests/test_thematic_mapping.py — 題材-成分股知識庫與 AI 自動映射專項測試 (SB-TH1)

測試範疇：
1. 資料庫 Schema 與種子資料契約 (theme_stock_mapping & 4 大核心題材種子)。
2. DBWriter 題材映射表寫入 (upsert_theme_stock_mapping) 與籃子查詢 (fetch_all_theme_baskets)。
3. TrendDiscover 現代結構 (trends + stocks) 解析與雙寫入驗證。
4. TrendDiscover 傳統結構 (keywords) 向下相容驗證。
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from src.extractors.trend_discover import TrendDiscover
from src.loaders.db_writer import DBWriter


class ThematicMappingDatabaseContractTests(unittest.TestCase):
    """測試 theme_stock_mapping 資料表與種子資料契約"""

    def test_theme_stock_mapping_schema_and_seed_data_contract(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_content = f.read()

        # 1. 驗證 theme_stock_mapping 建表語法
        self.assertIn("CREATE TABLE IF NOT EXISTS theme_stock_mapping", schema_content)
        self.assertIn("theme_keyword VARCHAR(50) NOT NULL", schema_content)
        self.assertIn("stock_id VARCHAR(20) NOT NULL", schema_content)
        self.assertIn("relevance_weight NUMERIC(3, 2)", schema_content)
        self.assertIn("PRIMARY KEY (theme_keyword, stock_id)", schema_content)

        # 2. 驗證 4 大核心題材種子資料存在
        core_themes = ["矽光子", "散熱模組", "CoWoS", "AI伺服器"]
        for theme in core_themes:
            self.assertIn(f"('{theme}'", schema_content)

        # 3. 驗證核心概念成分股代號存在
        sample_stocks = ["3081", "6442", "3324", "3017", "3131", "2382", "2330", "NVDA"]
        for s in sample_stocks:
            self.assertIn(f"'{s}'", schema_content)


class DBWriterThematicOperationsTests(unittest.TestCase):
    """測試 DBWriter 題材成分股映射表操作"""

    def test_upsert_theme_stock_mapping_does_not_overwrite_existing_rows(self):
        """§0.5 #33（GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.4，PO 2026-09-18
        核准）：既有映射的 `relevance_weight`／`stock_name`／`updated_at` 不得被
        AI 探索的重複發現覆寫——`ON CONFLICT` 改 `DO NOTHING`，新配對仍正常插入。

        known-FAIL：現行碼是 `DO UPDATE SET`，本斷言直接 FAIL。
        """
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        # 同一批同時含「既有配對重複發現」與「全新配對」兩種列，
        # 驗證 DO NOTHING 不分區塊、對整批一視同仁。
        records = [
            ("矽光子", "3081", "聯亞", 1.0),
            ("矽光子", "6442", "光聖", 1.0),
            ("散熱模組", "3324", "雙鴻", 1.0),
        ]
        writer.upsert_theme_stock_mapping(records)

        writer._execute_batch.assert_called_once()
        query, passed_records = writer._execute_batch.call_args[0]
        self.assertIn("INSERT INTO theme_stock_mapping", query)
        self.assertIn("ON CONFLICT (theme_keyword, stock_id)", query)
        self.assertIn("DO NOTHING", query)
        self.assertNotIn("DO UPDATE SET", query)
        self.assertEqual(len(passed_records), 3)

    def test_fetch_all_theme_baskets_parsing(self):
        writer = DBWriter.__new__(DBWriter)
        writer.db_config = {}

        mock_rows = [
            ("矽光子", "3081", "聯亞", 1.0),
            ("矽光子", "6442", "光聖", 0.9),
            ("散熱模組", "3324", "雙鴻", 1.0),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("psycopg2.connect", return_value=mock_conn):
            baskets = writer.fetch_all_theme_baskets()

        self.assertIn("矽光子", baskets)
        self.assertIn("散熱模組", baskets)
        self.assertEqual(len(baskets["矽光子"]), 2)
        self.assertEqual(baskets["矽光子"][0]["stock_id"], "3081")
        self.assertEqual(baskets["矽光子"][0]["stock_name"], "聯亞")
        self.assertEqual(baskets["矽光子"][0]["relevance_weight"], 1.0)


class TrendDiscoverThematicExtractionTests(unittest.TestCase):
    """測試 TrendDiscover 提取題材與成分股之解析邏輯"""

    def setUp(self):
        self.discover = TrendDiscover.__new__(TrendDiscover)
        self.discover.api_key = "dummy_key"
        self.discover.model = MagicMock()

    def test_trend_discover_modern_json_payload_parsing_and_writes(self):
        # 1. 模擬 PTT 標題爬取成功
        self.discover._fetch_recent_hot_titles = MagicMock(return_value=[
            "[新聞] 矽光子概念股強勢飆升",
            "[討論] 散熱大廠獲利再創新高"
        ])

        # 2. 模擬 Gemini 回傳現代 trends + stocks 結構
        mock_response = MagicMock()
        mock_response.text = '''{
            "trends": [
                {
                    "theme": "矽光子",
                    "stocks": [
                        {"stock_id": "3081", "name": "聯亞", "weight": 1.0},
                        {"stock_id": "6442", "name": "光聖", "weight": 1.0}
                    ]
                },
                {
                    "theme": "散熱模組",
                    "stocks": [
                        {"stock_id": "3324", "name": "雙鴻", "weight": 1.0}
                    ]
                }
            ]
        }'''
        self.discover.model.generate_content.return_value = mock_response

        # 3. 執行探索
        mock_db = MagicMock()
        self.discover.run_discovery(mock_db, max_new_keywords=2)

        # 驗證寫入 tracking_keywords
        mock_db.insert_discovered_keywords.assert_called_once_with(["矽光子", "散熱模組"])

        # 驗證寫入 theme_stock_mapping
        mock_db.upsert_theme_stock_mapping.assert_called_once_with([
            ("矽光子", "3081", "聯亞", 1.0),
            ("矽光子", "6442", "光聖", 1.0),
            ("散熱模組", "3324", "雙鴻", 1.0),
        ])

    def test_trend_discover_legacy_keywords_json_fallback_compatibility(self):
        self.discover._fetch_recent_hot_titles = MagicMock(return_value=["[新聞] 機器人概念題材發燒"])

        # 模擬 Gemini 回傳傳統 keywords 結構
        mock_response = MagicMock()
        mock_response.text = '{"keywords": ["人形機器人", "ASIC"]}'
        self.discover.model.generate_content.return_value = mock_response

        mock_db = MagicMock()
        self.discover.run_discovery(mock_db, max_new_keywords=2)

        # 驗證正常寫入 tracking_keywords
        mock_db.insert_discovered_keywords.assert_called_once_with(["人形機器人", "ASIC"])
        # 傳統結構無股票成分股，不呼叫 upsert_theme_stock_mapping
        mock_db.upsert_theme_stock_mapping.assert_not_called()


if __name__ == "__main__":
    unittest.main()
