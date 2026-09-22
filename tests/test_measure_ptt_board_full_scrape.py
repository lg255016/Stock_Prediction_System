# -*- coding: utf-8 -*-
"""§0.5 #40 段 B2 腳本的回歸鎖定：置底排除必須逐頁比較，不是相對全體最新。

複核第二輪（2026-09-21）發現：`measure_ptt_board_full_scrape.py` v1 自己另寫
一份 `_exclude_pinned_outliers()`，用「比全體最新早超過 7 天」當置底判準——
B2 要回溯 263 天，這個判準會把 09-14 以前的**每一篇真文章**都判成離群值
排除掉。修法：刪掉 B2 自己的版本，直接 import B1
（`measure_ptt_board_page_rate_probe._exclude_pinned_outliers`），逐頁相對
**該頁最新一篇**比較。

本檔驗證 B2 實際會呼叫到的版本（透過 import，不是重新測 B1 自己的邏輯）在
一個跨 30 天、含置底文的合成場景下，行為正確。
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify.measure_ptt_board_full_scrape import _exclude_pinned_outliers

_TZ = timezone(timedelta(hours=8))


def _entry(page_index, title, ts, url_suffix):
    return {
        "page_index": page_index,
        "title": title,
        "url": f"https://www.ptt.cc/bbs/Stock/M.{ts}.A.{url_suffix}.html",
        "date": " 9/05",
    }


class B2PinnedExclusionMustBePerPageNotGlobal(unittest.TestCase):
    """**什麼輸入會讓它 FAIL**：v1 的「相對全體最新」版本——30 天前的真文章
    會被誤判成離群值排除，`oldest_post_time` 因此不會落在它身上。
    """

    def test_thirty_day_old_real_article_on_last_page_is_not_excluded(self):
        now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=_TZ)
        pinned_ts = int(datetime(2026, 1, 21, 2, 46, 39, tzinfo=_TZ).timestamp())
        page0_recent_ts = int(now.timestamp())
        # 最後一頁（page_index=29）的一篇真文章，30 天前——這是「有沒有回溯
        # 到位」報告要看的關鍵欄位，不得被誤判成離群值。
        last_page_ts = int((now - timedelta(days=30)).timestamp())

        entries = [
            _entry(0, "[標的] 台積電", page0_recent_ts, "001"),
            _entry(0, "[公告] 4-6-1罰則將在1/22開始到年底加重至30天", pinned_ts, "002"),
            _entry(29, "[新聞] 30天前的真文章", last_page_ts, "003"),
        ]
        post_times = [
            datetime.fromtimestamp(page0_recent_ts, _TZ).replace(tzinfo=None),
            datetime.fromtimestamp(pinned_ts, _TZ).replace(tzinfo=None),
            datetime.fromtimestamp(last_page_ts, _TZ).replace(tzinfo=None),
        ]

        clean, pinned = _exclude_pinned_outliers(entries, post_times)

        self.assertEqual(len(pinned), 1, "只有置底公告該被排除")
        self.assertEqual(pinned[0]["title"], "[公告] 4-6-1罰則將在1/22開始到年底加重至30天")

        expected_oldest = datetime.fromtimestamp(last_page_ts, _TZ).replace(tzinfo=None)
        self.assertEqual(
            min(clean), expected_oldest,
            "30 天前的真文章必須被保留，成為 oldest_post_time 的依據——"
            "v1 的「相對全體最新」版本會把它也判成離群值排除掉",
        )


if __name__ == "__main__":
    unittest.main()
