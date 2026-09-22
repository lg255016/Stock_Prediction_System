# -*- coding: utf-8 -*-
"""UG-G2-SB7 收尾：哪些取樣 regime 進入特徵，用**允許清單**決定。

================================================================================
為什麼是排除，不是修正
================================================================================
舊批 331 篇有 76 列 `post_time` 錯誤（年份差 +1~+7）。
**但就算日期修對了，那 331 篇仍然是另一種取樣**：

- 舊批：**逐關鍵字搜尋，橫跨七年**
- 新批：**看板固定頁面，只涵蓋最近幾頁**

> **修正日期只解決「哪一天」，不解決「怎麼取到的」。**

一批日期正確、但取樣方式不同的資料混進特徵，
**仍然會讓 RISK-015 的覆蓋率量測失真** —— 而那正是條件 1 要量的東西。

**兩件事分開**（PO 2026-09-05）：

| | 是什麼 | 現在做嗎 |
|---|--------|---------|
| **修正** `post_time` | **資料完整性** —— 把 2019 記成 2026 是缺陷，修它永遠是對的 | **否** —— 押到「決定要用那批資料」的時候 |
| **排除** | **特徵組成的決定** —— 要不要讓另一種取樣 regime 進訓練資料 | **是** —— 零 DB 操作、可逆 |

**若「要用那批資料」那一天不會來，那次對真實庫的授權寫入就永遠不必發生。**

================================================================================
為什麼是允許清單，不是排除清單
================================================================================
**兩種寫法的失效方向相反：**

| 寫法 | 日後新增一個來源而忘了登錄 |
|------|--------------------------|
| 排除清單 `source <> 'ptt_stock'` | **自動進入特徵** —— 未經檢視的資料靜默混入 |
| **允許清單** `source IN (...)` | **不會進入** —— 資料誠實地少 |

依據是這個專案自己已經決定過的同一類問題 ——
`source_capabilities.py` 的 docstring 逐字：

> **漏登錄的後果 → NULL（誠實地少）；反過來 → 偽造訊號（安靜地錯）。**

**同一條判準在這裡適用。** 而且允許清單**自我說明**：
它直接寫出哪些 regime 在特徵集裡。
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TheAllowlistItself(unittest.TestCase):
    """**known-FAIL 主體**：目前沒有任何過濾，`ptt_stock` 會進特徵。"""

    def test_old_batch_does_not_enter_features(self):
        from src.transform.source_capabilities import source_enters_features
        self.assertFalse(source_enters_features("ptt_stock"),
                         "舊批是**逐關鍵字搜尋橫跨七年**的取樣，"
                         "與新批不是同一個 regime")

    def test_current_regimes_do_enter(self):
        from src.transform.source_capabilities import source_enters_features
        self.assertTrue(source_enters_features("ptt_board_pages"))
        self.assertTrue(source_enters_features("ptt_keyword_search"))

    def test_an_unregistered_source_does_not_enter(self):
        """**這一條才是允許清單與排除清單的差別所在。**

        **什麼輸入會讓它 FAIL**：寫成 `source <> 'ptt_stock'` ——
        那樣任何**沒被想到**的來源都會自動進入特徵。

        > 一個沒有人檢視過的取樣 regime 靜默混入訓練資料，
        > **不會報錯，只會讓模型學到我們沒打算給它的東西。**
        """
        from src.transform.source_capabilities import source_enters_features
        for unknown in ("dcard", "threads", "ptt_something_new_2027", "", None):
            self.assertFalse(source_enters_features(unknown),
                             "未登錄的來源一律不得進入特徵 —— "
                             "**允許清單的失效方向是「誠實地少」**")


class TheTwoDeclarationsAnswerDifferentQuestions(unittest.TestCase):
    """⚠ **能力宣告**與**特徵組成**是兩個不同的問題，不得混為一談。

    本專案至今抓到的多數缺陷都是「兩個東西看起來是同一個」，
    而這兩張表就住在同一個模組裡 —— **所以要有一條測試釘住它們的差別。**

    **`ptt_stock` 同時是**：
    - `COMMENT_DIRECTION_SOURCES` 的成員（它**確實**提供推／噓標記）
    - **不在** `FEATURE_SOURCE_ALLOWLIST`（它的取樣 regime 不同）

    > **「這個來源能不能提供某項資料」與「要不要讓它進訓練資料」，
    > 是兩個獨立的判斷。** 那一列同時為真與為假，正好證明它們不是同一張表。
    """

    def test_ptt_stock_has_direction_but_is_excluded_from_features(self):
        from src.transform.source_capabilities import (
            provides_comment_direction, source_enters_features)
        self.assertTrue(provides_comment_direction("ptt_stock"),
                        "它**確實**提供推／噓標記 —— 排除的理由不是能力不足")
        self.assertFalse(source_enters_features("ptt_stock"),
                         "排除的理由是**取樣 regime 不同**，不是資料錯誤")

    def test_the_two_sets_are_not_the_same_object(self):
        from src.transform.source_capabilities import (
            COMMENT_DIRECTION_SOURCES, FEATURE_SOURCE_ALLOWLIST)
        self.assertNotEqual(set(COMMENT_DIRECTION_SOURCES),
                            set(FEATURE_SOURCE_ALLOWLIST),
                            "**兩張表不同** —— 相同會讓下一個人以為只有一張")


class TheFetchSqlMustUseTheAllowlist(unittest.TestCase):
    """取數 SQL 必須用允許清單過濾，**不得用排除清單**。

    `db_writer.py` 的取數 SQL **一直都有 SELECT `source`，只是沒拿它過濾**
    —— 同 UG-G2-SB5 決策點 5 的形狀：欄位在、讀取端沒用。
    """

    def _sql(self):
        from src.loaders.db_writer import DBWriter
        w = DBWriter.__new__(DBWriter)
        seen = []

        def fake(sql, *a, **k):
            seen.append(sql)
            return pd.DataFrame()

        w.fetch_data = fake
        DBWriter.fetch_all_for_features(w)
        return [s for s in seen if "market_articles" in s][0]

    def test_articles_query_filters_by_the_allowlist(self):
        from src.transform.source_capabilities import FEATURE_SOURCE_ALLOWLIST
        sql = self._sql()
        self.assertIn("source IN", sql,
                      "**必須是允許清單** —— `source <> ...` 的失效方向是"
                      "「未登錄的自動進入」")
        for s in FEATURE_SOURCE_ALLOWLIST:
            self.assertIn("'%s'" % s, sql)

    def test_the_excluded_source_is_not_named_as_an_exclusion(self):
        """**反向釘子**：不得改回排除清單。

        **什麼輸入會讓它 FAIL**：`WHERE source <> 'ptt_stock'`。
        """
        sql = self._sql()
        self.assertNotIn("<>", sql)
        self.assertNotIn("!=", sql)
        self.assertNotIn("NOT IN", sql.upper())

    def test_the_existing_sentiment_condition_is_kept(self):
        """**反向釘子**：既有的 `sentiment_score IS NOT NULL` 不得被順手拿掉。"""
        self.assertIn("sentiment_score IS NOT NULL", self._sql())


if __name__ == "__main__":
    unittest.main()
