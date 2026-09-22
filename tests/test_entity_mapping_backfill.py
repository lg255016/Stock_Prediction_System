# -*- coding: utf-8 -*-
"""
UG-G3-SB2 路由子項（`entity_mapping` 補齊 455 檔）紅色測試。

規格來源：`doc/upgrade/gates/UG_G3_SB2_GATE_A_PROPOSAL.md` §5/§5.1（PO 2026-09-09
四項設計裁決）。對應實作：`scripts/verify/ug_g3_sb2_backfill_entity_mapping.py`。

本檔在該腳本存在前撰寫（`CLAUDE.md` §14 先寫紅、後寫綠）。

**設計契約（供綠色實作對照，PO 2026-09-09 裁決）**：
- `derive_market(source)`：封閉映射，僅認 `twse_mi_index`→`TWSE`、
  `tpex_daily_quotes`→`TPEX`，其餘一律 `raise ValueError`，不得預設。
- `clean_keyword(name)`：只移除任意位置的 `*`（資料品質標記），`-KY`／`-DR`
  （公司簡稱本體）原樣保留。
- `compute_routing_rows(df_candidate)`：`df_candidate` 已預先排除既路由股票；
  每個 `stock_id` 的 `market` 取 `trade_date` 最大那一列的 `source` 映射；
  對清理後 `security_name` 去重，每個相異結果各一列；`trade_date` 最大那列
  對應的清理後名稱視為「現名」（`DESC_CURRENT`），其餘為「舊名」
  （`DESC_OLD_TMPL`）。
- `exclude_already_routed_stock_ids(df_candidate, df_existing)`：以
  **`stock_id`** 明確排除，不靠 keyword 層級隱式去重。
- `check_keyword_collisions(df_new_rows, df_existing, df_non_universe)`：
  (a) 新增列彼此撞名、(b) 對既有 `entity_mapping` 撞名、(c) 對宇宙外
  `candidate_prices` 股票撞名，任一非零即 `raise ValueError`。
- `write_routing_rows(conn, df_rows)`：純 `INSERT`（**不用 `ON CONFLICT`**），
  不 commit（呼叫端於讀回核對通過後才 commit，比照
  `scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py` 既有模式）；
  任何例外 `conn.rollback()` 後重新拋出。
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

try:
    import psycopg2  # noqa: F401  能 import 就是真的裝了，直接用，不覆蓋
except ImportError:
    _psycopg2_stub = types.ModuleType("psycopg2")
    _psycopg2_stub.connect = MagicMock()
    _psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    _psycopg2_extras_stub.execute_values = MagicMock()
    _psycopg2_stub.extras = _psycopg2_extras_stub
    sys.modules["psycopg2"] = _psycopg2_stub
    sys.modules["psycopg2.extras"] = _psycopg2_extras_stub

import pandas as pd

from scripts.verify.ug_g3_sb2_backfill_entity_mapping import (
    DESC_CURRENT,
    DESC_OLD_TMPL,
    check_keyword_collisions,
    clean_keyword,
    compute_routing_rows,
    derive_market,
    exclude_already_routed_stock_ids,
    execute_write_and_verify,
    write_routing_rows,
)


def _mk_candidate(rows):
    """rows: list[dict]，每個 dict 含 stock_id, security_name, source, trade_date。"""
    return pd.DataFrame(rows)


class CleanKeywordTests(unittest.TestCase):

    def test_clean_keyword_strips_asterisk_anywhere(self):
        # * 不一定在尾端：矽力*-KY、材料*-KY 是真實庫觀測到的中段案例
        self.assertEqual(clean_keyword("矽力*-KY"), "矽力-KY")
        self.assertEqual(clean_keyword("智通*"), "智通")
        self.assertEqual(clean_keyword("國巨*"), "國巨")

    def test_clean_keyword_preserves_ky_and_dr_suffix(self):
        # -KY（開曼註冊）、-DR（存託憑證）是公司簡稱本體，不是標記，不得剝除
        self.assertEqual(clean_keyword("世芯-KY"), "世芯-KY")
        self.assertEqual(clean_keyword("泰金寶-DR"), "泰金寶-DR")

    def test_clean_keyword_noop_on_plain_name(self):
        self.assertEqual(clean_keyword("台積電"), "台積電")


class DeriveMarketTests(unittest.TestCase):

    def test_derive_market_known_sources(self):
        self.assertEqual(derive_market("twse_mi_index"), "TWSE")
        self.assertEqual(derive_market("tpex_daily_quotes"), "TPEX")

    def test_derive_market_closed_mapping_raises_on_unknown_source(self):
        """映射表封閉，不得對未知來源猜測或給預設值（PO 2026-09-09 裁決 1）。"""
        with self.assertRaises(ValueError):
            derive_market("some_new_source_not_yet_known")


class ComputeRoutingRowsTests(unittest.TestCase):

    def test_uses_latest_trade_date_row_for_market_not_first_row(self):
        """6446 型測資：早期 TPEX、晚期 TWSE（上櫃轉上市）。market 必須取最新一列，
        取第一列或任一列會拿到過期市場別（PO 2026-09-09 裁決 1，已在真實庫驗證
        6446/6472/6589 三檔）。"""
        df = _mk_candidate([
            {"stock_id": "6446", "security_name": "藥華藥", "source": "tpex_daily_quotes", "trade_date": "2022-08-03"},
            {"stock_id": "6446", "security_name": "藥華藥", "source": "twse_mi_index", "trade_date": "2024-01-25"},
            {"stock_id": "6446", "security_name": "藥華藥", "source": "twse_mi_index", "trade_date": "2026-09-04"},
        ])
        result = compute_routing_rows(df)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["market"], "TWSE")

    def test_genuine_rename_produces_two_keywords_with_current_and_old_descriptions(self):
        """6111 型測資：真改名（大宇資→光聚晶電）。兩個相異 keyword，各自對映正確
        的 description（現名 vs 舊名，PO 2026-09-09 裁決 3）。"""
        df = _mk_candidate([
            {"stock_id": "6111", "security_name": "大宇資", "source": "tpex_daily_quotes", "trade_date": "2022-08-03"},
            {"stock_id": "6111", "security_name": "光聚晶電", "source": "tpex_daily_quotes", "trade_date": "2026-03-12"},
        ])
        result = compute_routing_rows(df)

        self.assertEqual(len(result), 2)
        keywords = set(result["keyword"])
        self.assertEqual(keywords, {"大宇資", "光聚晶電"})
        self.assertTrue((result["stock_id"] == "6111").all())
        self.assertTrue((result["market"] == "TPEX").all())

        current_row = result.loc[result["keyword"] == "光聚晶電"].iloc[0]
        old_row = result.loc[result["keyword"] == "大宇資"].iloc[0]
        self.assertEqual(current_row["description"], DESC_CURRENT)
        self.assertEqual(old_row["description"], DESC_OLD_TMPL.format(current_name="光聚晶電"))

    def test_asterisk_only_variant_collapses_to_one_keyword(self):
        """5314 型測資：只差 `*`（世紀／世紀*），清理後應合併為 1 個 keyword，
        不是 2 個（PO 2026-09-09 裁決 2）。"""
        df = _mk_candidate([
            {"stock_id": "5314", "security_name": "世紀", "source": "tpex_daily_quotes", "trade_date": "2022-08-03"},
            {"stock_id": "5314", "security_name": "世紀*", "source": "tpex_daily_quotes", "trade_date": "2025-03-31"},
        ])
        result = compute_routing_rows(df)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["keyword"], "世紀")
        self.assertEqual(result.iloc[0]["description"], DESC_CURRENT)

    def test_market_migration_with_identical_name_produces_one_keyword(self):
        """6446/6472/6589 型：名稱在兩個 source 下完全相同，不是改名，只是上櫃轉
        上市，應合併為 1 個 keyword（不得因 source 不同就誤判為兩個名稱）。"""
        df = _mk_candidate([
            {"stock_id": "6472", "security_name": "保瑞", "source": "tpex_daily_quotes", "trade_date": "2022-08-03"},
            {"stock_id": "6472", "security_name": "保瑞", "source": "twse_mi_index", "trade_date": "2026-09-04"},
        ])
        result = compute_routing_rows(df)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["keyword"], "保瑞")
        self.assertEqual(result.iloc[0]["market"], "TWSE")

    def test_empty_input_returns_empty_frame_with_expected_columns(self):
        result = compute_routing_rows(pd.DataFrame(columns=["stock_id", "security_name", "source", "trade_date"]))
        self.assertEqual(len(result), 0)
        self.assertEqual(list(result.columns), ["keyword", "stock_id", "market", "description"])


class ExcludeAlreadyRoutedStockIdsTests(unittest.TestCase):

    def test_excludes_by_stock_id_not_by_keyword(self):
        """既有 3 檔（2330/2382/6488）要整檔排除，不是只排除撞到相同 keyword 的
        那一列——即使該股票在 candidate_prices 還有其他歷史名稱，也不該被
        自動路由第二個 keyword（PO 2026-09-09 裁決 4：以 stock_id 排除，不靠
        keyword 層級隱式去重）。"""
        df_candidate = _mk_candidate([
            {"stock_id": "2330", "security_name": "台積電", "source": "twse_mi_index", "trade_date": "2026-01-01"},
            {"stock_id": "6111", "security_name": "光聚晶電", "source": "tpex_daily_quotes", "trade_date": "2026-01-01"},
        ])
        df_existing = pd.DataFrame([
            {"keyword": "台積電", "stock_id": "2330", "market": "TWSE", "description": "中文全稱"},
        ])

        result = exclude_already_routed_stock_ids(df_candidate, df_existing)

        self.assertNotIn("2330", set(result["stock_id"]))
        self.assertIn("6111", set(result["stock_id"]))

    def test_empty_existing_returns_input_unchanged(self):
        df_candidate = _mk_candidate([
            {"stock_id": "6111", "security_name": "光聚晶電", "source": "tpex_daily_quotes", "trade_date": "2026-01-01"},
        ])
        result = exclude_already_routed_stock_ids(df_candidate, pd.DataFrame(columns=["keyword", "stock_id"]))
        self.assertEqual(len(result), 1)


class CheckKeywordCollisionsTests(unittest.TestCase):

    def _mk_new_rows(self, rows):
        return pd.DataFrame(rows, columns=["keyword", "stock_id", "market", "description"])

    def test_passes_when_clean(self):
        new_rows = self._mk_new_rows([
            ("光聚晶電", "6111", "TPEX", DESC_CURRENT),
            ("智通", "8932", "TPEX", DESC_CURRENT),
        ])
        existing = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])
        non_universe = pd.DataFrame(columns=["stock_id", "security_name"])
        # 不應拋出
        check_keyword_collisions(new_rows, existing, non_universe)

    def test_raises_on_cross_new_stock_collision(self):
        """新增的 457 筆彼此之間撞名（同一 keyword 對到不同 stock_id）。"""
        new_rows = self._mk_new_rows([
            ("重複名", "1111", "TWSE", DESC_CURRENT),
            ("重複名", "2222", "TWSE", DESC_CURRENT),
        ])
        with self.assertRaises(ValueError):
            check_keyword_collisions(new_rows, pd.DataFrame(columns=["keyword", "stock_id"]),
                                      pd.DataFrame(columns=["stock_id", "security_name"]))

    def test_raises_on_collision_with_existing_entity_mapping(self):
        new_rows = self._mk_new_rows([("台積電", "9999", "TWSE", DESC_CURRENT)])
        existing = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])
        with self.assertRaises(ValueError):
            check_keyword_collisions(new_rows, existing, pd.DataFrame(columns=["stock_id", "security_name"]))

    def test_raises_on_collision_with_non_universe_candidate(self):
        new_rows = self._mk_new_rows([("某某公司", "6111", "TPEX", DESC_CURRENT)])
        non_universe = pd.DataFrame([{"stock_id": "7777", "security_name": "某某公司*"}])
        with self.assertRaises(ValueError):
            check_keyword_collisions(new_rows, pd.DataFrame(columns=["keyword", "stock_id"]), non_universe)

    def test_does_not_raise_when_existing_keyword_matches_same_stock_id(self):
        """同一 keyword、同一 stock_id 不算撞名（自己對自己）——只有『同一 keyword
        對到不同 stock_id』才是真正的撞名。"""
        new_rows = self._mk_new_rows([("台積電", "2330", "TWSE", DESC_CURRENT)])
        existing = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])
        check_keyword_collisions(new_rows, existing, pd.DataFrame(columns=["stock_id", "security_name"]))


def _mk_mock_conn(rowcount=1):
    cur = MagicMock()
    cur.rowcount = rowcount
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    return conn, cur


class WriteRoutingRowsTests(unittest.TestCase):
    """`write_routing_rows()` 契約測試：純 INSERT、不 commit、例外 rollback+reraise。"""

    def _mk_rows(self, n=1):
        return pd.DataFrame({
            "keyword": [f"kw{i}" for i in range(n)],
            "stock_id": [f"s{i}" for i in range(n)],
            "market": ["TWSE"] * n,
            "description": [DESC_CURRENT] * n,
        })

    def test_uses_plain_insert_not_on_conflict(self):
        conn, cur = _mk_mock_conn(rowcount=1)
        n = write_routing_rows(conn, self._mk_rows(1))

        sql = cur.execute.call_args[0][0]
        self.assertIn("INSERT", sql.upper())
        self.assertNotIn("ON CONFLICT", sql.upper())
        self.assertEqual(n, 1)
        conn.commit.assert_not_called()  # commit 由呼叫端在讀回核對通過後執行

    def test_returns_rowcount_sum_across_rows(self):
        conn, cur = _mk_mock_conn(rowcount=1)
        n = write_routing_rows(conn, self._mk_rows(3))
        self.assertEqual(cur.execute.call_count, 3)
        self.assertEqual(n, 3)

    def test_rolls_back_and_reraises_on_error(self):
        conn, cur = _mk_mock_conn()
        cur.execute.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            write_routing_rows(conn, self._mk_rows(1))

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_empty_df_is_noop(self):
        conn, cur = _mk_mock_conn()
        n = write_routing_rows(conn, pd.DataFrame(columns=["keyword", "stock_id", "market", "description"]))
        self.assertEqual(n, 0)
        conn.cursor.assert_not_called()


class ExecuteWriteAndVerifyTests(unittest.TestCase):
    """`execute_write_and_verify()`：寫入＋commit 前核對的核心邏輯（PO 2026-09-09
    複審發現兩個真實缺陷後追加，見 doc/upgrade/gates/UG_G3_SB2_GATE_A_PROPOSAL.md §5.1）。

    缺陷 1：`df_new_rows` 為空時，舊版用 `.equals()` 比較兩個空 DataFrame，因
    dtype 不同而誤判不相符，把「無事可做」回報成「失敗」（§7.1 反方向的同一
    種錯：訊號與事實不符）——修法為提前 return，不呼叫 `write_routing_rows`、
    不呼叫 `rollback()`。

    缺陷 2：既有列核對＋新增列核對看不到「多了一列不在兩個集合內」的情形，
    補一道 entity_mapping 總列數核對（`len(existing) + len(new) == 讀回總數`）。
    """

    def _mk_existing(self, rows=None):
        if rows is None:
            rows = [{"keyword": "台積電", "stock_id": "2330", "market": "TWSE", "description": "中文全稱"}]
        return pd.DataFrame(rows, columns=["keyword", "stock_id", "market", "description"])

    def _mk_new(self, rows=None):
        if rows is None:
            rows = [{"keyword": "光聚晶電", "stock_id": "6111", "market": "TPEX", "description": DESC_CURRENT}]
        return pd.DataFrame(rows, columns=["keyword", "stock_id", "market", "description"])

    def test_zero_new_rows_returns_zero_without_insert_or_rollback(self):
        """所有宇宙股票皆已路由時（真實庫第二次執行會踩到），必須乾淨地回報
        「無事可做」，不得誤判為失敗（known-FAIL：修正前版本，見送審報告）。"""
        conn, cur = _mk_mock_conn()
        df_existing = self._mk_existing()
        df_new_rows = pd.DataFrame(columns=["keyword", "stock_id", "market", "description"])

        n = execute_write_and_verify(conn, df_existing, df_new_rows)

        self.assertEqual(n, 0)
        conn.cursor.assert_not_called()
        conn.rollback.assert_not_called()
        conn.commit.assert_not_called()

    def test_commits_and_returns_count_when_all_checks_pass(self):
        conn, cur = _mk_mock_conn(rowcount=1)
        df_existing = self._mk_existing()
        df_new_rows = self._mk_new()
        cur.fetchall.side_effect = [
            [("台積電", "2330", "TWSE", "中文全稱")],       # 既有列讀回
            [("光聚晶電", "6111", "TPEX", DESC_CURRENT)],   # 新增列讀回
        ]
        cur.fetchone.side_effect = [(2,)]  # 總列數 = 1 既有 + 1 新增

        n = execute_write_and_verify(conn, df_existing, df_new_rows)

        self.assertEqual(n, 1)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_raises_and_rolls_back_when_insert_count_mismatch(self):
        conn, cur = _mk_mock_conn(rowcount=0)  # INSERT 完全沒影響到任何列
        with self.assertRaises(RuntimeError):
            execute_write_and_verify(conn, self._mk_existing(), self._mk_new())
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_and_rolls_back_when_existing_rows_changed(self):
        """既有列讀回與寫入前不同（本次寫入意外動到既有列）。"""
        conn, cur = _mk_mock_conn(rowcount=1)
        cur.fetchall.side_effect = [
            [("台積電", "9999", "TWSE", "中文全稱")],       # stock_id 被改動
            [("光聚晶電", "6111", "TPEX", DESC_CURRENT)],
        ]
        cur.fetchone.side_effect = [(2,)]

        with self.assertRaises(RuntimeError):
            execute_write_and_verify(conn, self._mk_existing(), self._mk_new())

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_and_rolls_back_when_new_rows_mismatch(self):
        conn, cur = _mk_mock_conn(rowcount=1)
        cur.fetchall.side_effect = [
            [("台積電", "2330", "TWSE", "中文全稱")],
            [("光聚晶電", "6111", "TWSE", DESC_CURRENT)],  # market 錯了
        ]
        cur.fetchone.side_effect = [(2,)]

        with self.assertRaises(RuntimeError):
            execute_write_and_verify(conn, self._mk_existing(), self._mk_new())

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_and_rolls_back_when_total_count_does_not_match_existing_plus_new(self):
        """既有列核對、新增列核對皆通過，但 entity_mapping 總列數多了一列不在
        兩個集合內——前兩道核對看不到，靠總數核對抓（PO 2026-09-09 複審追加，
        缺陷 2）。"""
        conn, cur = _mk_mock_conn(rowcount=1)
        cur.fetchall.side_effect = [
            [("台積電", "2330", "TWSE", "中文全稱")],
            [("光聚晶電", "6111", "TPEX", DESC_CURRENT)],
        ]
        cur.fetchone.side_effect = [(3,)]  # 應為 2，卻是 3——多了一列不在任何集合內

        with self.assertRaises(RuntimeError):
            execute_write_and_verify(conn, self._mk_existing(), self._mk_new())

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
