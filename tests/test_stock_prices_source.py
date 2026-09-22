# -*- coding: utf-8 -*-
"""`stock_prices.source` 的寫入契約（migration 009／PRE-G3-03 DP1）。

**本檔的存在理由**：欄位加了而寫入端沒接線，`NULL` 的語意會在上線當天開始被稀釋 ——
「migration 前寫入，血緣不可考」與「migration 後寫入，只是沒人填」
**在資料上完全相同**，而且每過一天多一列，沒有任何告警。

因此這裡的每一項都必須能回答「什麼輸入會讓它 FAIL？」（`CLAUDE.md` §9A.1）。
"""
import io
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.loaders.db_writer import DBWriter  # noqa: E402

MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "database", "migrations",
    "009_stock_prices_source.sql")


def _row(**over):
    base = {
        "stock_id": "2330", "trade_date": "2026-09-04",
        "open_price": 1000.0, "high_price": 1010.0, "low_price": 990.0,
        "close_price": 1005.0, "volume": 12345,
        "source": "twse_stock_day",
    }
    base.update(over)
    return pd.DataFrame([base])


class StockPriceSourceIsRequired(unittest.TestCase):
    """S1／S2：寫入端強制 —— schema 管值域，管不住「誰該填」。"""

    def setUp(self):
        self.w = DBWriter.__new__(DBWriter)
        self.w._execute_batch = MagicMock()

    def test_S1_missing_source_column_raises(self):
        """**known-FAIL 的正例**：沒有 `source` 欄必須報錯，不得靜默寫 NULL。

        ⚠ 這一項若被移除，四個呼叫點任一漏接線都不會有人發現 ——
        它們會照常寫入，只是每一列的血緣都是 NULL。
        """
        df = _row().drop(columns=["source"])
        with self.assertRaises(ValueError) as ctx:
            self.w.upsert_to_stock_prices(df)
        self.assertIn("source", str(ctx.exception))
        self.w._execute_batch.assert_not_called()   # **沒有寫進去**

    def test_S2_unknown_source_value_raises(self):
        """值域外的字串必須報錯。

        `'yfinance'` 與 `'yFinance'` 沒有約束就會安靜地變成兩個來源。
        """
        for bad in ("yfinance", "yFinance", "candidate_prices", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.w.upsert_to_stock_prices(_row(source=bad))
        self.w._execute_batch.assert_not_called()

    def test_S2b_null_source_value_raises(self):
        """欄位在、值是 NULL/NaN —— 同樣必須報錯。

        ⚠ 這與 S1 是**不同的漏法**：呼叫端可能建了欄位卻沒填值。
        """
        with self.assertRaises(ValueError):
            self.w.upsert_to_stock_prices(_row(source=None))
        self.w._execute_batch.assert_not_called()

    def test_S2c_valid_source_writes(self):
        """反向對照：合法值必須寫得進去 —— 否則上面三項可能只是「永遠報錯」。"""
        for ok in DBWriter.STOCK_PRICE_SOURCES:
            with self.subTest(ok=ok):
                self.w._execute_batch.reset_mock()
                self.w.upsert_to_stock_prices(_row(source=ok))
                self.w._execute_batch.assert_called_once()
                sql, records = self.w._execute_batch.call_args[0]
                self.assertIn("source", sql)
                self.assertEqual(records[0][-1], ok)   # source 在最後一欄


class PythonAndSqlDefinitionsMustAgree(unittest.TestCase):
    """S3：`CLAUDE.md` §7.1 —— 不得同時維護兩套互相不一致的定義。"""

    def test_S3_python_tuple_matches_sql_check(self):
        """`STOCK_PRICE_SOURCES` 必須與 migration 009 的 CHECK 逐值相同。

        **known-FAIL**：在任一側增刪一個值，本項立刻 FAIL。
        這正是它存在的理由 —— 兩份副本不會自己保持一致。
        """
        with io.open(MIGRATION, encoding="utf-8") as fh:
            sql = fh.read()
        m = re.search(r"CHECK\s*\(\s*source IS NULL OR source IN \((.*?)\)\s*\)",
                      sql, re.S)
        self.assertIsNotNone(m, "migration 009 的 CHECK 約束找不到")
        in_sql = set(re.findall(r"'([^']+)'", m.group(1)))
        self.assertEqual(in_sql, set(DBWriter.STOCK_PRICE_SOURCES))


class ColumnOrderIsExplicit(unittest.TestCase):
    """S4：欄位順序不得由呼叫端的 DataFrame 決定。"""

    def test_S4_shuffled_input_columns_still_write_correctly(self):
        """**known-FAIL 的正例**：欄位順序打亂後仍須寫對。

        ⚠ 舊實作用 `df.to_numpy()`，順序錯了會把 high 寫進 low，
        **而且不會有任何錯誤** —— 這一項是那個沉默失敗的偵測器。
        """
        w = DBWriter.__new__(DBWriter)
        w._execute_batch = MagicMock()
        df = _row()[["source", "volume", "close_price", "low_price",
                     "high_price", "open_price", "trade_date", "stock_id"]]
        w.upsert_to_stock_prices(df)
        _, records = w._execute_batch.call_args[0]
        self.assertEqual(
            list(records[0]),
            ["2330", "2026-09-04", 1000.0, 1010.0, 990.0, 1005.0, 12345,
             "twse_stock_day"])


class EveryCallSiteSuppliesSource(unittest.TestCase):
    """S5：四個呼叫點都必須傳來源 —— 反查法，不是逐個列舉。

    ⚠ **不用 grep 判斷**：靜態掃描分不出「有寫這個字串」與「真的傳進去了」
    （`CLAUDE.md` §9A.1 記載過同型錯誤）。這裡直接跑那四條路徑。
    """

    def _pipeline(self):
        import main_etl_pipeline as mep
        p = mep.ETLPipelineManager.__new__(mep.ETLPipelineManager)
        p.db_writer = MagicMock()
        p.cleaner = MagicMock()
        p.yf_api = MagicMock()
        return p, mep

    def _captured_source(self, p):
        p.db_writer.upsert_to_stock_prices.assert_called_once()
        df = p.db_writer.upsert_to_stock_prices.call_args[0][0]
        self.assertIn("source", df.columns, "該呼叫點沒有帶 source")
        return set(df["source"].unique())

    # ⚠ `UG-G3-SB2a` 方案 B（2026-09-10）：舊版 S5a／S5b 分別驗「TWSE 自建
    # 爬蟲成功寫 twse_stock_day」與「爬蟲失敗落 yfinance 寫 yfinance_
    # auto_adjusted」——兩者驗的都是舊版逐股爬蟲＋yfinance 備援機制本身的
    # 行為，該機制已隨方案 B 刪除，TWSE 逐股路徑改為與 TPEX 共用
    # `run_tpex_pipeline_from_candidate_prices`（見下方 S5d，同一份邏輯，
    # 不分市場），不再需要獨立的 TWSE 案例。歷史行為見 git log，
    # 不在測試碼內保留已刪除的函式名。

    def test_S5c_us_pipeline(self):
        p, _ = self._pipeline()
        p.format_provider_symbol = lambda sid, mkt: sid
        p.yf_api.fetch_yfinance_data.return_value = _row()
        p.cleaner.clean_yfinance_stock_data.return_value = _row().drop(
            columns=["source"])
        p.run_us_stock_pipeline("NVDA", period="3mo")
        self.assertEqual(self._captured_source(p), {"yfinance_auto_adjusted"})

    def test_S5d_candidate_prices_passes_through_original_report_name(self):
        """⚠ 上櫃路徑必須帶**原始報表名**，不是中繼表名。

        **known-FAIL**：若把它改成寫 `'candidate_prices'`，本項 FAIL ——
        因為 RISK-022 要分辨的是調整基準，而基準由原始報表決定。
        """
        import datetime
        p, mep = self._pipeline()
        p.db_writer.fetch_data.return_value = _row(
            stock_id="6488", source="tpex_daily_quotes")
        out = p.run_tpex_pipeline_from_candidate_prices(
            "6488", datetime.date(2026, 9, 4), batch_outcome=mep.OK)
        self.assertEqual(out, mep.OK)
        self.assertEqual(self._captured_source(p), {"tpex_daily_quotes"})

    def test_S5e_candidate_select_includes_source(self):
        """SELECT 沒撈 `source`，S5d 就不可能通過 —— 但這一項讓成因直接可讀。"""
        import main_etl_pipeline as mep
        self.assertIn(
            "source", mep.ETLPipelineManager.SELECT_CANDIDATE_FOR_STOCK_PRICES)


if __name__ == "__main__":
    unittest.main()
