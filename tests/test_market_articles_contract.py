"""
tests/test_market_articles_contract.py — UG-G2-SB3 market_articles 13 欄寫入契約專項測試

涵蓋：DBWriter.ARTICLE_COLUMNS 契約完整性、四個留言計數欄未解析時維持 NULL 而非 0
（DB_MIGRATION_PLAN.md §4.3：0 代表「已解析且確實零則留言」，NULL 代表「尚未解析」，
兩者語意不可混淆）、provider_article_id 格式（MULTI_SOURCE_DATA_CONTRACT.md §3.1）、
以及 NaN→None 轉換迴歸（DEC-023 剩餘風險欄登記之未稽核寫法，本 SB 一併修正）。
"""

import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

if "psycopg2" not in sys.modules:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock()
    psycopg2_extras = types.ModuleType("psycopg2.extras")
    psycopg2_extras.execute_values = MagicMock()
    psycopg2.extras = psycopg2_extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2_extras

import pandas as pd

from src.loaders.db_writer import DBWriter
from src.transform.data_cleaner import build_ptt_provider_article_id

MIGRATION_003 = Path(__file__).resolve().parents[1] / "database" / "migrations" / "003_expand_articles.sql"
COMMENT_COUNT_COLS = ["push_count", "boo_count", "neutral_count", "total_comments"]


class ArticleColumnContractTests(unittest.TestCase):
    """market_articles 13 欄寫入契約（不含 article_id／created_at 兩個自動欄位）"""

    def test_article_columns_contract_is_13(self):
        self.assertEqual(len(DBWriter.ARTICLE_COLUMNS), 13)
        self.assertEqual(len(DBWriter.ARTICLE_COLUMNS), len(set(DBWriter.ARTICLE_COLUMNS)))
        # 自動欄位不得出現在手動寫入清單中
        self.assertNotIn("article_id", DBWriter.ARTICLE_COLUMNS)
        self.assertNotIn("created_at", DBWriter.ARTICLE_COLUMNS)
        for col in COMMENT_COUNT_COLS + ["provider_article_id"]:
            self.assertIn(col, DBWriter.ARTICLE_COLUMNS)

    def test_upsert_keeps_on_conflict_do_nothing(self):
        """MULTI_SOURCE_DATA_CONTRACT.md §2.3：初次寫入維持 DO NOTHING，
        留言計數回填走獨立 UPDATE 路徑，不得混入 upsert。"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()
        writer.upsert_to_market_articles(pd.DataFrame([{
            "source": "ptt_stock", "post_time": datetime(2026, 8, 27),
            "title": "t", "url": "https://www.ptt.cc/bbs/Stock/M.1.A.1.html",
        }]))

        query, _ = writer._execute_batch.call_args[0]
        self.assertIn("ON CONFLICT (url) DO NOTHING", query)
        self.assertNotIn("DO UPDATE", query)


class UnparsedCommentCountsStayNullTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_article_push_boo_write"""

    def test_upsert_null_not_zero_for_unparsed_comment_counts(self):
        """DataFrame 未提供留言計數欄時（列表頁爬取的既有流程），必須寫入 NULL，
        不得補 0——0 會讓 comment_polarization 算出 1.0「最大分歧」的偽造強訊號。"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        # 模擬 clean_ptt_data() 現行輸出（無留言計數欄）
        writer.upsert_to_market_articles(pd.DataFrame([{
            "source": "ptt_stock", "fetch_keyword": "台積電",
            "post_time": datetime(2026, 8, 27), "title": "測試標題",
            "url": "https://www.ptt.cc/bbs/Stock/M.1.A.1.html", "author": "u1",
            "engagement_metric": 5, "sentiment_score": None,
            "provider_article_id": "ptt_Stock_M.1.A.1",
        }]))

        _, records = writer._execute_batch.call_args[0]
        for col in COMMENT_COUNT_COLS:
            idx = DBWriter.ARTICLE_COLUMNS.index(col)
            self.assertIsNone(records[0][idx], f"{col} 未解析時必須為 NULL，不得為 0")

    def test_zero_comments_written_as_zero_not_null(self):
        """已解析且確實零則留言時，必須寫入 0（不是 NULL）——這是與上一個測試
        互補的另一半：兩種狀態都要能正確表達，否則區分就沒有意義。"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        writer.upsert_to_market_articles(pd.DataFrame([{
            "source": "ptt_stock", "post_time": datetime(2026, 8, 27), "title": "t",
            "url": "https://www.ptt.cc/bbs/Stock/M.2.A.2.html",
            "push_count": 0, "boo_count": 0, "neutral_count": 0, "total_comments": 0,
        }]))

        _, records = writer._execute_batch.call_args[0]
        for col in COMMENT_COUNT_COLS:
            idx = DBWriter.ARTICLE_COLUMNS.index(col)
            self.assertEqual(records[0][idx], 0, f"{col} 已解析為零則留言時必須是 0，不得為 NULL")

    def test_upsert_converts_nan_to_none_in_pure_numeric_columns(self):
        """迴歸測試（DEC-023 剩餘風險欄登記之未稽核寫法）：留言計數欄是 INTEGER
        且必須能寫 NULL，若沿用 `DataFrame.where(pd.notnull(df), None)`，純數值欄位
        的 None 會被折回 NaN，送進 INTEGER 欄位觸發 NumericValueOutOfRange。
        Known-FAIL 案例：暫時還原舊寫法時，本測試最後一列的 push_count 會是 nan 而非 None。"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        # 兩列皆有 push_count 欄，但第二列為 NaN（部分文章已解析、部分未解析的混合情境）
        writer.upsert_to_market_articles(pd.DataFrame({
            "source": ["ptt_stock", "ptt_stock"],
            "post_time": [datetime(2026, 8, 26), datetime(2026, 8, 27)],
            "title": ["a", "b"],
            "url": ["https://www.ptt.cc/bbs/Stock/M.1.A.1.html",
                    "https://www.ptt.cc/bbs/Stock/M.2.A.2.html"],
            "push_count": [12.0, float("nan")],
            "total_comments": [20.0, float("nan")],
        }))

        _, records = writer._execute_batch.call_args[0]
        push_idx = DBWriter.ARTICLE_COLUMNS.index("push_count")
        self.assertEqual(records[0][push_idx], 12.0)
        self.assertIsNone(
            records[1][push_idx],
            f"NaN 必須轉為 Python None 才能安全寫入 INTEGER 欄位，"
            f"實際為 {records[1][push_idx]!r}（型態 {type(records[1][push_idx])}）",
        )


class ProviderArticleIdTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱 test_provider_article_id_unique 之修正版
    （見 G2_SB3_GATE_A_PROPOSAL.md §1.4：DB 層無 UNIQUE 約束，去重主鍵仍是 url，
    本測試驗證的是格式與解析邏輯正確性，非 DB constraint）"""

    def test_provider_article_id_format(self):
        self.assertEqual(
            build_ptt_provider_article_id("https://www.ptt.cc/bbs/Stock/M.1724567890.A.123.html"),
            "ptt_Stock_M.1724567890.A.123",
        )

    def test_provider_article_id_distinct_for_distinct_articles(self):
        a = build_ptt_provider_article_id("https://www.ptt.cc/bbs/Stock/M.1.A.1.html")
        b = build_ptt_provider_article_id("https://www.ptt.cc/bbs/Stock/M.2.A.2.html")
        self.assertNotEqual(a, b)

    def test_provider_article_id_none_for_unparseable_url(self):
        """無法解析時回傳 None，不得回傳部分猜測值——格式錯誤的 ID 比沒有更糟，
        會被誤當成有效識別碼跨平台比對。"""
        for bad in [None, "", "not-a-url", "https://www.ptt.cc/bbs/Stock/", 12345]:
            self.assertIsNone(build_ptt_provider_article_id(bad), f"輸入 {bad!r} 應回傳 None")


class Migration003ShapeTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_migration_003_idempotent
    （靜態檢查 SQL 形狀；真實冪等性由隔離臨時 DB 的 E2E 驗證確認）"""

    def setUp(self):
        self.sql = MIGRATION_003.read_text(encoding="utf-8")

    def test_migration_003_uses_idempotent_ddl(self):
        for col in COMMENT_COUNT_COLS + ["provider_article_id"]:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {col}", self.sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_articles_provider_id", self.sql)
        self.assertIn("ON CONFLICT (version) DO NOTHING", self.sql)
        # CHECK constraint 需以 pg_constraint 存在性包住（PostgreSQL 無 ADD CONSTRAINT IF NOT EXISTS）
        self.assertIn("SELECT 1 FROM pg_constraint WHERE conname = 'chk_comment_counts_nonneg'", self.sql)

    def test_migration_003_comment_count_columns_have_no_default(self):
        """四個留言計數欄嚴禁 DEFAULT 0（DB_MIGRATION_PLAN.md §4.3）。"""
        for col in COMMENT_COUNT_COLS:
            for line in self.sql.splitlines():
                if f"ADD COLUMN IF NOT EXISTS {col}" in line:
                    self.assertNotIn("DEFAULT", line.upper(), f"{col} 不得有 DEFAULT：{line.strip()}")

    def test_migration_003_provider_index_is_not_unique(self):
        """MULTI_SOURCE_DATA_CONTRACT.md §2.3：provider_article_id 為輔助索引，
        不取代 url 的 UNIQUE 約束——誤建成 UNIQUE 會讓解析失敗回傳的多筆 NULL
        以外的重複值意外互斥。"""
        self.assertNotIn("CREATE UNIQUE INDEX", self.sql.upper())


if __name__ == "__main__":
    unittest.main()
