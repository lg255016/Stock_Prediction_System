# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 1（`stock_prices` ← `candidate_prices` 回補）腳本的單元測試。

規格來源：`doc/upgrade/gates/UG_G3_SB2a_GATE_A_PROPOSAL.md` §3.2／§3.4／§6；
PO 2026-09-10 對段 1 腳本的五項明確要求（含事後複核追加的「必補測試」）。
對應實作：`scripts/verify/ug_g3_sb2a_backfill_stock_prices.py`。

比照 `tests/test_entity_mapping_backfill.py` 既有模式。

================================================================================
`ExecuteWriteAndVerifyCheck3RegressionTests`——核對 3 的 known-FAIL 案例
================================================================================
`sps_project_reviewer` 2026-09-10 拋棄式庫全量 `--write` dry-run 實測發現：
核對 3 原設計「插入後逐股列數 == `candidate_prices` 該股列數」對 2330／2382
必然 FAIL——這兩檔因 `UG-G3-SB2a` 提案 §3.2 登記的 2026-09-01／09-02 批次
覆蓋缺口，`stock_prices` 987 列多於 `candidate_prices` 985 列，插入前就已經
不相等，跟本次回補有沒有正確執行無關。

`test_2330_shape_would_fail_under_old_formula_but_passes_under_new_one` 直接
重現這個形狀（`before=987, candidate=985, missing=0`），呼叫**現行**
`execute_write_and_verify` 驗證不會 raise、正常 commit。

⚠⚠ **PO 2026-09-10 複核修正**：初版本測試另外還有一段 (a)——在測試方法
內自己重建「舊公式」的算式（`assert after == candidate`）並用
`assertRaises(AssertionError)` 包住，用來「證明舊公式必然錯判」。**那段是
套套邏輯（§9A.1）**：它斷言的是測試自己寫的那行算式必然失敗，跟
`ug_g3_sb2a_backfill_stock_prices.py` 現在怎麼寫完全無關——不管腳本改成
什麼樣子，這段都會通過，因為它從未呼叫腳本裡的任何程式碼。已刪除。
真正具備偵測力的 known-FAIL 案例是**變異測試**：把腳本的核對 3 改回舊公式
（`after == candidate` 而非 `after == before + missing`）後，本測試方法
本體會 FAIL（`逐股列數核對不符：1 檔`）——這才是「呼叫了會變的程式碼、
且真的會因為程式碼改變而改變結果」的證據，證據見送審報告。
"""
import datetime as dt
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

from scripts.verify.ug_g3_sb2a_backfill_stock_prices import (
    STOCK_PRICE_COLUMNS,
    _build_spot_check_sample,
    _check_backup_or_exit,
    _spot_check_rows,
    compute_missing_rows,
    execute_write_and_verify,
    write_missing_rows,
)

_MODULE = "scripts.verify.ug_g3_sb2a_backfill_stock_prices"


def _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3),
                       open_price=100.0, high_price=101.0, low_price=99.0,
                       close_price=100.5, volume=1000, source="twse_mi_index"):
    return {
        "stock_id": stock_id, "trade_date": trade_date,
        "open_price": open_price, "high_price": high_price,
        "low_price": low_price, "close_price": close_price,
        "volume": volume, "source": source,
    }


def _mk_mock_conn(fetchone_seq=None, fetchall_seq=None):
    """比照 `tests/test_entity_mapping_backfill.py::_mk_mock_conn`：`cur` 是
    單一共用 MagicMock，`conn.cursor()` 的每次呼叫（含 `with` 區塊）都回傳
    同一個 `cur`，故 `fetchone`／`fetchall` 的 `side_effect` 佇列橫跨整個
    呼叫序列，依實際呼叫順序消耗。"""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    if fetchone_seq is not None:
        cur.fetchone.side_effect = list(fetchone_seq)
    if fetchall_seq is not None:
        cur.fetchall.side_effect = list(fetchall_seq)
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    return conn, cur


class ComputeMissingRowsTests(unittest.TestCase):
    """`compute_missing_rows()`：`MultiIndex` 差集，只補缺席日期。"""

    def test_excludes_existing_keys(self):
        df_candidate = pd.DataFrame([
            _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 1)),
            _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 2)),
        ])
        df_existing = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 9, 1)],
        })
        out = compute_missing_rows(df_candidate, df_existing)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["trade_date"], dt.date(2026, 9, 2))

    def test_stock_prices_only_dates_not_in_candidate_do_not_affect_result(self):
        """`stock_prices` 有、`candidate_prices` 沒有的日期（如 2330 的
        2026-09-01／09-02 批次覆蓋缺口）不影響結果——輸出永遠是
        `df_candidate` 的子集，這類「既有但候選池沒有」的日期根本不在
        `df_candidate` 裡，不可能被排除或殘留。"""
        df_candidate = pd.DataFrame([
            _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 8, 30)),
        ])
        df_existing = pd.DataFrame({
            "stock_id": ["2330", "2330"],
            "trade_date": [dt.date(2026, 9, 1), dt.date(2026, 9, 2)],
        })
        out = compute_missing_rows(df_candidate, df_existing)
        # 既有集合裡的兩個日期都不在候選池——不影響候選池那一列被判定為缺席。
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["trade_date"], dt.date(2026, 8, 30))

    def test_all_missing_when_existing_empty(self):
        df_candidate = pd.DataFrame([
            _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 1)),
            _mk_candidate_row(stock_id="6488", trade_date=dt.date(2026, 9, 1)),
        ])
        df_existing = pd.DataFrame(columns=["stock_id", "trade_date"])
        out = compute_missing_rows(df_candidate, df_existing)
        self.assertEqual(len(out), 2)


class WriteMissingRowsTests(unittest.TestCase):
    """`write_missing_rows()`：純 INSERT（不用 ON CONFLICT）、RETURNING 計數、
    不 commit、例外 rollback+reraise。"""

    def _mk_rows(self, n=1):
        return pd.DataFrame([_mk_candidate_row(stock_id=f"s{i}",
                                                 trade_date=dt.date(2026, 9, 1 + i))
                              for i in range(n)])

    def test_uses_plain_insert_not_on_conflict(self):
        conn, cur = _mk_mock_conn()
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("s0",)]
            n = write_missing_rows(conn, self._mk_rows(1))

        sql = mock_ev.call_args[0][1]
        self.assertIn("INSERT", sql.upper())
        self.assertNotIn("ON CONFLICT", sql.upper())
        self.assertIn("RETURNING", sql.upper())
        self.assertEqual(n, 1)
        conn.commit.assert_not_called()  # commit 由呼叫端在讀回核對通過後執行

    def test_returns_count_from_returning_not_rowcount(self):
        """**已知會 FAIL 的錯法**：若改用 `cur.rowcount`，`page_size` 小於
        總筆數時只反映最後一批——本測試斷言的是 `execute_values` 的
        `RETURNING` 回傳值長度，不是 `cur.rowcount`。"""
        conn, cur = _mk_mock_conn()
        cur.rowcount = 999  # 刻意設一個錯誤值，證明程式沒有讀它
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("s0",), ("s1",), ("s2",)]
            n = write_missing_rows(conn, self._mk_rows(3))
        self.assertEqual(n, 3)

    def test_null_price_columns_become_python_none_not_nan(self):
        """SQL NULL 價格列（§3.3）傳給 `execute_values` 前，`NaN` 必須轉成
        `None`——psycopg2 不接受 `float('nan')` 當成 SQL NULL 寫入。"""
        row = _mk_candidate_row(open_price=float("nan"), high_price=float("nan"),
                                 low_price=float("nan"), close_price=float("nan"),
                                 volume=0)
        df = pd.DataFrame([row])
        conn, cur = _mk_mock_conn()
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("2330",)]
            write_missing_rows(conn, df)
        values_arg = mock_ev.call_args[0][2]
        self.assertEqual(len(values_arg), 1)
        row_tuple = values_arg[0]
        self.assertIsNone(row_tuple[2])  # open_price
        self.assertIsNone(row_tuple[3])  # high_price
        self.assertIsNone(row_tuple[4])  # low_price
        self.assertIsNone(row_tuple[5])  # close_price

    def test_rolls_back_and_reraises_on_error(self):
        conn, cur = _mk_mock_conn()
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.side_effect = RuntimeError("boom")
            with self.assertRaises(RuntimeError):
                write_missing_rows(conn, self._mk_rows(1))
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_empty_df_is_noop(self):
        conn, cur = _mk_mock_conn()
        n = write_missing_rows(conn, pd.DataFrame(columns=STOCK_PRICE_COLUMNS))
        self.assertEqual(n, 0)
        conn.cursor.assert_not_called()


class SpotCheckRowsTests(unittest.TestCase):
    """`_spot_check_rows()`／`_build_spot_check_sample()`：NaN-safe、型別
    比對、全部 NULL 價格列必被涵蓋。"""

    def test_build_sample_includes_all_null_price_rows(self):
        df = pd.DataFrame([
            _mk_candidate_row(stock_id="A", open_price=1.0),
            _mk_candidate_row(stock_id="B", open_price=float("nan")),
            _mk_candidate_row(stock_id="C", close_price=float("nan")),
        ])
        sample = _build_spot_check_sample(df, sample_size=1)
        # sample_size=1 只隨機抽 1 檔正常列，但兩個 NULL 列必須都在
        self.assertIn("B", sample["stock_id"].tolist())
        self.assertIn("C", sample["stock_id"].tolist())

    def test_null_matches_null_passes(self):
        df = pd.DataFrame([_mk_candidate_row(stock_id="2330",
                                              open_price=float("nan"))])
        cur = MagicMock()
        cur.fetchone.return_value = (None, 101.0, 99.0, 100.5, 1000,
                                      "twse_mi_index")
        _spot_check_rows(cur, df, sample_size=10)  # 不 raise 即通過

    def test_null_vs_non_null_raises(self):
        df = pd.DataFrame([_mk_candidate_row(stock_id="2330",
                                              open_price=float("nan"))])
        cur = MagicMock()
        cur.fetchone.return_value = (999.0, 101.0, 99.0, 100.5, 1000,
                                      "twse_mi_index")
        with self.assertRaises(RuntimeError):
            _spot_check_rows(cur, df, sample_size=10)

    def test_volume_mismatch_raises(self):
        df = pd.DataFrame([_mk_candidate_row(stock_id="2330", volume=1000)])
        cur = MagicMock()
        cur.fetchone.return_value = (100.0, 101.0, 99.0, 100.5, 999,
                                      "twse_mi_index")
        with self.assertRaises(RuntimeError):
            _spot_check_rows(cur, df, sample_size=10)

    def test_price_diff_within_tolerance_passes(self):
        df = pd.DataFrame([_mk_candidate_row(stock_id="2330", close_price=100.5)])
        cur = MagicMock()
        cur.fetchone.return_value = (100.0, 101.0, 99.0, 100.5000001, 1000,
                                      "twse_mi_index")
        _spot_check_rows(cur, df, sample_size=10)

    def test_price_diff_beyond_tolerance_raises(self):
        df = pd.DataFrame([_mk_candidate_row(stock_id="2330", close_price=100.5)])
        cur = MagicMock()
        cur.fetchone.return_value = (100.0, 101.0, 99.0, 100.6, 1000,
                                      "twse_mi_index")
        with self.assertRaises(RuntimeError):
            _spot_check_rows(cur, df, sample_size=10)

    def test_row_not_found_raises(self):
        df = pd.DataFrame([_mk_candidate_row(stock_id="2330")])
        cur = MagicMock()
        cur.fetchone.return_value = None
        with self.assertRaises(RuntimeError):
            _spot_check_rows(cur, df, sample_size=10)


class CheckBackupOrExitTests(unittest.TestCase):
    """`_check_backup_or_exit()`：三種不合格情況皆 `SystemExit`。"""

    def test_missing_file_exits(self):
        with self.assertRaises(SystemExit):
            _check_backup_or_exit("/tmp/does-not-exist-sb2a.dump")

    def test_zero_byte_file_exits(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".dump") as f:
            with self.assertRaises(SystemExit):
                _check_backup_or_exit(f.name)

    def test_stale_file_exits(self):
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as f:
            f.write(b"not empty")
            path = f.name
        try:
            old_time = 0  # 1970-01-01，遠超過 24 小時
            os.utime(path, (old_time, old_time))
            with self.assertRaises(SystemExit):
                _check_backup_or_exit(path)
        finally:
            os.remove(path)

    def test_fresh_nonempty_file_does_not_exit(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".dump") as f:
            f.write(b"not empty")
            f.flush()
            _check_backup_or_exit(f.name)  # 不 raise 即通過


class ExecuteWriteAndVerifyTests(unittest.TestCase):
    """`execute_write_and_verify()`：寫入＋commit 前四項核對的核心邏輯。"""

    def _mk_candidate(self, rows):
        return pd.DataFrame(rows)

    def test_zero_missing_rows_returns_zero_without_insert_or_rollback(self):
        conn, cur = _mk_mock_conn()
        df_candidate = self._mk_candidate([_mk_candidate_row()])
        df_existing_keys = pd.DataFrame({"stock_id": ["2330"],
                                          "trade_date": [dt.date(2026, 9, 3)]})
        df_missing = pd.DataFrame(columns=STOCK_PRICE_COLUMNS)

        n = execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)

        self.assertEqual(n, 0)
        conn.cursor.assert_not_called()
        conn.rollback.assert_not_called()
        conn.commit.assert_not_called()

    def test_commits_and_returns_count_when_all_checks_pass(self):
        row = _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3))
        df_candidate = self._mk_candidate([row])
        df_existing_keys = pd.DataFrame(columns=["stock_id", "trade_date"])
        df_missing = pd.DataFrame([row])

        conn, cur = _mk_mock_conn(
            fetchone_seq=[
                (0,),                                      # total_before
                (1,),                                       # total_after
                (100.0, 101.0, 99.0, 100.5, 1000, "twse_mi_index"),  # spot check
            ],
            fetchall_seq=[
                [],                    # before_counts（2330 尚無列）
                [("2330", 1)],         # after_counts
            ],
        )
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("2330",)]
            n = execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)

        self.assertEqual(n, 1)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_raises_and_rolls_back_when_insert_count_mismatch(self):
        row = _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3))
        df_candidate = self._mk_candidate([row])
        df_existing_keys = pd.DataFrame(columns=["stock_id", "trade_date"])
        df_missing = pd.DataFrame([row])

        conn, cur = _mk_mock_conn(fetchone_seq=[(0,)], fetchall_seq=[[]])
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = []  # 預期插入 1 列，實際 0 列被 RETURNING
            with self.assertRaises(RuntimeError):
                execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_and_rolls_back_when_total_count_mismatch(self):
        row = _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3))
        df_candidate = self._mk_candidate([row])
        df_existing_keys = pd.DataFrame(columns=["stock_id", "trade_date"])
        df_missing = pd.DataFrame([row])

        conn, cur = _mk_mock_conn(
            fetchone_seq=[(0,), (5,)],  # total_after 應為 1，卻回報 5
            fetchall_seq=[[]],
        )
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("2330",)]
            with self.assertRaises(RuntimeError):
                execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_and_rolls_back_when_per_stock_count_mismatch(self):
        row = _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3))
        df_candidate = self._mk_candidate([row])
        df_existing_keys = pd.DataFrame(columns=["stock_id", "trade_date"])
        df_missing = pd.DataFrame([row])

        conn, cur = _mk_mock_conn(
            fetchone_seq=[(0,), (1,)],
            fetchall_seq=[[], [("2330", 2)]],  # 應為 0+1=1，卻回報 2
        )
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("2330",)]
            with self.assertRaises(RuntimeError):
                execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_and_rolls_back_when_spot_check_mismatch(self):
        row = _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3),
                                 close_price=100.5)
        df_candidate = self._mk_candidate([row])
        df_existing_keys = pd.DataFrame(columns=["stock_id", "trade_date"])
        df_missing = pd.DataFrame([row])

        conn, cur = _mk_mock_conn(
            fetchone_seq=[
                (0,), (1,),
                (100.0, 101.0, 99.0, 999.0, 1000, "twse_mi_index"),  # close_price 錯
            ],
            fetchall_seq=[[], [("2330", 1)]],
        )
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("2330",)]
            with self.assertRaises(RuntimeError):
                execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()


class ExecuteWriteAndVerifyCheck3RegressionTests(unittest.TestCase):
    """核對 3 的 known-FAIL 案例——重現 `sps_project_reviewer` 拋棄式庫
    dry-run 抓到的 2330 形狀：`before=987, candidate=985, missing=0`。"""

    def test_2330_shape_would_fail_under_old_formula_but_passes_under_new_one(self):
        """PO 2026-09-10 複核修正：初版本測試另有一段在測試內自己重建舊公式
        算式並斷言其失敗——那是套套邏輯（§9A.1，與腳本程式碼無關，不管
        腳本怎麼改都會通過），已刪除。真正的 known-FAIL 證據是變異測試：
        把腳本核對 3 的公式改回舊版（`after == candidate` 而非
        `after == before + missing`）後，本測試方法本體會 FAIL（真實錯誤
        訊息：`逐股列數核對不符：1 檔`），因為 2330 的 before=987 與
        candidate=985 不相等——這就是本測試要證明「新公式正確、可安全套用
        於這個真實踩過的形狀」的意義（見送審報告的變異測試記錄）。
        """
        before = 987  # 2330 在 stock_prices 既有列數（重現真實形狀）
        row_2330 = _mk_candidate_row(stock_id="2330", trade_date=dt.date(2026, 9, 3))
        # 6488 帶一筆真正待插入的列，確保 df_missing 非空（df_missing 全空
        # 會走「無事可做」的提前 return，測不到核對 3 的邏輯本身）。
        row_6488 = _mk_candidate_row(stock_id="6488", trade_date=dt.date(2026, 9, 4))

        df_candidate = pd.DataFrame([row_2330, row_6488])
        df_existing_keys = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": [dt.date(2026, 9, 3)],
        })  # 2330 這個日期已存在 → 不在 df_missing 內
        df_missing = pd.DataFrame([row_6488])  # 只有 6488 那筆待插入

        conn, cur = _mk_mock_conn(
            fetchone_seq=[
                (before + 10,),   # total_before（10 是陪襯的其他股票列數，任意值）
                (before + 10 + 1,),  # total_after = before_total + 1（6488 那筆）
                (100.0, 101.0, 99.0, 100.5, 1000, "twse_mi_index"),  # 6488 抽樣核對
            ],
            fetchall_seq=[
                [("2330", before), ("6488", 0)],       # before_counts
                [("2330", before), ("6488", 1)],        # after_counts：2330 沒變、6488 +1
            ],
        )
        with patch(f"{_MODULE}.execute_values") as mock_ev:
            mock_ev.return_value = [("6488",)]
            n = execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)

        self.assertEqual(n, 1)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
