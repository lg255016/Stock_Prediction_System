# -*- coding: utf-8 -*-
"""UG-G2-SB7 §5 的 V2／V3：批次總結與三態的守衛。

**本檔不連資料庫**（純函式），理由同 `test_universe_builder.py`：
`CLAUDE.md` §13.4 記載本專案有 9 個測試其行為取決於環境是否具備 DB，
而「失敗不得被偽裝成沒有資料」是本 SB 的核心宣稱，**它的測試不能是那種測試**。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.loaders.etl_run_log import (  # noqa: E402
    FETCH_FAILED, IncompleteBatchError, NO_DATA, OK, RunLogEntry,
    assert_complete, format_summary, summarize,
)


def entry(item, outcome, detail=None, attempts=1):
    return RunLogEntry("twse_mi_index", "2026-09-03", item, outcome,
                       detail=detail, http_attempts=attempts)


class V2BatchSummaryIsComplete(unittest.TestCase):
    """**V2**：三態之和必須等於本批的項目數。

    **這條專門抓靜默略過** —— 一個被 `except: continue` 吞掉的項目
    在三態裡哪一格都不會出現，**而三個數字看起來都很正常**。
    """

    def test_v2_complete_batch_passes(self):
        entries = [entry("2330", OK), entry("2382", NO_DATA),
                   entry("6488", FETCH_FAILED, detail="HTTP 500")]
        counts = assert_complete(entries, item_count=3)
        self.assertEqual(counts["total"], 3)
        self.assertEqual((counts[OK], counts[NO_DATA], counts[FETCH_FAILED]),
                         (1, 1, 1))

    def test_v2_silently_skipped_item_fails(self):
        """**known-FAIL**：三項只記了兩項 —— 第三項被吞掉了。

        若把判準寫成「三態都有記錄」或「和 == len(entries)」，
        **這個案例會通過**，因為它永遠相等。
        判準必須拿**跑之前就決定的項目數**去比。
        """
        entries = [entry("2330", OK), entry("2382", NO_DATA)]
        with self.assertRaises(IncompleteBatchError) as ctx:
            assert_complete(entries, item_count=3)
        self.assertIn("靜默略過", str(ctx.exception))

    def test_v2_zero_items_is_still_checked(self):
        """空批次也要對得上 —— 「一項都沒跑」與「跑了但全被吞掉」不是同一件事。"""
        assert_complete([], item_count=0)
        with self.assertRaises(IncompleteBatchError):
            assert_complete([], item_count=1)

    def test_summary_prints_all_three_numbers(self):
        """只印失敗數時，「0 個失敗」與「一項都沒跑」看起來一樣。"""
        counts = summarize([entry("2330", OK)])
        line = format_summary("twse_mi_index", "2026-09-03", counts)
        for token in ("OK 1", "NO_DATA 0", "FETCH_FAILED 0", "合計 1"):
            self.assertIn(token, line)


class V3FailureIsNotNoData(unittest.TestCase):
    """**V3**：`FETCH_FAILED` 不得被寫成 `NO_DATA`，且必須說得出理由。

    `CLAUDE.md` §7.1：**失敗與「真的沒有資料」必須可區分。**
    """

    def test_v3_fetch_failed_requires_observable_detail(self):
        """**known-FAIL**：失敗但說不出為什麼 → 在寫入資料庫之前就擋下。

        對應 migration 007 的 `chk_etl_run_log_detail`，**在程式層先擋一次** ——
        兩道都在，是因為第一道失效時第二道才有機會發現。
        """
        with self.assertRaises(ValueError):
            entry("6488", FETCH_FAILED)          # 沒有 detail

    def test_v3_success_must_not_carry_a_reason(self):
        """雙向約束：一列 `OK` 卻寫著理由，會被讀成失敗。"""
        with self.assertRaises(ValueError):
            entry("2330", OK, detail="HTTP 500")
        with self.assertRaises(ValueError):
            entry("2330", NO_DATA, detail="假日")

    def test_v3_unknown_outcome_is_rejected(self):
        """**窮舉在此是刻意的** —— 讓它自由文字化，下一個人就會寫出 `SKIPPED`。"""
        with self.assertRaises(ValueError):
            entry("2330", "SKIPPED")
        with self.assertRaises(ValueError):
            entry("2330", "SUCCESS")             # 與 source_status 的態名混用

    def test_v3_no_data_and_fetch_failed_are_distinguishable(self):
        """兩者在「這一項沒有列」上長得一樣，**而下游處置完全相反**。"""
        holiday = entry("2330", NO_DATA)                       # 假日的空報表
        refused = entry("2330", FETCH_FAILED, detail="HTTP 429")
        self.assertNotEqual(holiday.outcome, refused.outcome)
        self.assertIsNone(holiday.detail)
        self.assertEqual(refused.detail, "HTTP 429")
        counts = summarize([holiday, refused])
        self.assertEqual(counts[NO_DATA], 1)
        self.assertEqual(counts[FETCH_FAILED], 1)

    def test_v3_row_carries_target_database_not_caller_assumption(self):
        """`as_row` 的 `target_database` 由寫入端填入，**不是呼叫端的假設**。"""
        row = entry("2330", OK).as_row("2026-09-03T00:00:00", "postgres")
        self.assertEqual(row[6], "postgres")
        self.assertEqual(row[4], OK)


if __name__ == "__main__":
    unittest.main()
