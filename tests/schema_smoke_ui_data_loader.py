"""
tests/schema_smoke_ui_data_loader.py — UG-G1-SB2 §5.1 Schema Smoke Test

性質：獨立於正式 mock 測試套件（檔名刻意不含 test_ 前綴，`python -m unittest
discover -s tests -p "test_*.py"` 不會自動撿到它）。§4 把 HERM-01~09 全部改成
mock 之後，schema 相容性不再有任何測試在守——mock 只驗證「程式碼假設的欄位名稱」，
驗證不了「這些欄位名稱在真實 schema 裡還存不存在」。本檔針對
stock_prices／entity_mapping／theme_stock_mapping／market_articles 四張表各挑一個
欄位數最多的代表查詢（見 doc/upgrade/gates/closed/SB2_GATE_A_PROPOSAL.md §5.1.1），對臨時 PostgreSQL
（已套用 database/schema.sql，可為空表）直接執行，只斷言「查詢不拋錯、欄位對得上」，
不斷言任何具體數值。

**執行時機（UG-G2-SB4 補上）**：凡是已經為了 E2E 驗證啟動隔離臨時 DB 的 SB
——動到 database/schema.sql、新增 migration、或變更 db_writer 讀寫欄位者——
都應在同一個臨時 DB 內順帶執行本檔一次。

⚠ 已知缺口：本檔自 UG-G1-SB2（commit 414fcc81）執行過一次後，UG-G2-SB1／SB3／SB4
三次臨時 DB E2E 均未執行它，而那三次都動了 schema（migration 002／003／004）與
db_writer 的讀寫欄位——正是本檔最該發揮作用的時機。本檔不是設計上不該跑，
而是先前沒有任何機制觸發它；上述「執行時機」即為補救。
（見 doc/governance/PROJECT_STATUS.md §0.4）

執行方式（比照 SB1 隔離臨時 DB 機制，需先建立臨時 DB 並完成綁定確認）：

    MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \\
      -e DB_HOST=localhost -e DB_PORT=<temp_port> -e POSTGRES_DB=<temp_db> \\
      -e POSTGRES_USER=<temp_user> -e POSTGRES_PASSWORD=<temp_password> \\
      stock_prediction_system2_devcontainer-app-1 \\
      python -m unittest tests.schema_smoke_ui_data_loader -v
"""

import unittest

import pandas as pd
import psycopg2

from src.loaders.db_writer import DBWriter


class UIDataLoaderSchemaSmokeTests(unittest.TestCase):
    """
    逐表驗證 src/ui/data_loader.py 內對應查詢與真實 schema.sql 的欄位相容性。
    連線設定一律透過 DBWriter().db_config 取得，不手寫連線字串（RISK-013 控制措施）。
    """

    @classmethod
    def setUpClass(cls):
        cls.conn = psycopg2.connect(**DBWriter().db_config)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_stock_prices_query_executes_and_columns_match(self):
        """代表查詢來源：_fetch_real_stock_features_from_db 的 price_query"""
        query = """
            SELECT trade_date, stock_id, open_price, high_price, low_price, close_price, volume
            FROM stock_prices
            WHERE stock_id = %s
            ORDER BY trade_date ASC;
        """
        df = pd.read_sql(query, self.conn, params=("__SMOKE_TEST_NONEXISTENT__",))
        expected_cols = ["trade_date", "stock_id", "open_price", "high_price", "low_price", "close_price", "volume"]
        for c in expected_cols:
            self.assertIn(c, df.columns)

    def test_entity_mapping_query_executes_and_columns_match(self):
        """代表查詢來源：_fetch_real_stock_features_from_db 的 mapping_query"""
        query = """
            SELECT keyword, stock_id
            FROM entity_mapping
            WHERE stock_id = %s;
        """
        df = pd.read_sql(query, self.conn, params=("__SMOKE_TEST_NONEXISTENT__",))
        for c in ["keyword", "stock_id"]:
            self.assertIn(c, df.columns)

    def test_theme_stock_mapping_query_executes_and_columns_match(self):
        """代表查詢來源：load_thematic_radar_data 的 mapping_query（欄位數最多的版本）"""
        query = """
            SELECT theme_keyword, stock_id, stock_name, relevance_weight
            FROM theme_stock_mapping
            ORDER BY theme_keyword, relevance_weight DESC;
        """
        df = pd.read_sql(query, self.conn)
        for c in ["theme_keyword", "stock_id", "stock_name", "relevance_weight"]:
            self.assertIn(c, df.columns)

    def test_market_articles_query_executes_and_columns_match(self):
        """代表查詢來源：_fetch_real_stock_features_from_db 的 articles_query"""
        query = """
            SELECT article_id, source, fetch_keyword, post_time, title, url, author, engagement_metric, sentiment_score
            FROM market_articles
            WHERE fetch_keyword IN %s
            ORDER BY post_time ASC;
        """
        df = pd.read_sql(query, self.conn, params=(("__SMOKE_TEST_NONEXISTENT__",),))
        expected_cols = ["article_id", "source", "fetch_keyword", "post_time", "title", "url", "author", "engagement_metric", "sentiment_score"]
        for c in expected_cols:
            self.assertIn(c, df.columns)


if __name__ == "__main__":
    unittest.main()
