# -*- coding: utf-8 -*-
"""§0.5 #40 段 B1 探測腳本的回歸鎖定：一篇置底公告不得污染「最舊文章」判斷。

複核第一輪（2026-09-21）發現：`measure_ptt_board_page_rate_probe.py` v1 用
`min(全部條目的時間戳)` 當「內容涵蓋的最舊時間」，被 PTT 置底公告（只出現在
最新一頁、時間戳卻很舊）污染，`pages_per_day` 因此低估約 20 倍。

這是 `tests/test_ptt_board_pages.py` V13（`scrape_ptt_board_pages()` 用 `max`
判斷回溯進度、不用 `min`）同一個坑的第三次出現：2026-09-05 受控執行 →
`ptt_scraper.py` E3 修正 → 本次。本檔補上第三次的專屬 known-FAIL，防第四次。
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify.measure_ptt_board_page_rate_probe import (
    PINNED_POST_OUTLIER_DAYS,
    build_report,
)

_TZ = timezone(timedelta(hours=8))


def _entry(page_index, title, ts, date_str=" 9/05"):
    return {
        "page_index": page_index,
        "title": title,
        "url": f"https://www.ptt.cc/bbs/Stock/M.{ts}.A.001.html",
        "date": date_str,
        "author": "u",
        "push_count": "10",
        "url_timestamp": ts,
    }


def _make_probe(entries, pages_fetched=1, stop_reason="page_budget_exhausted"):
    return {
        "pages_fetched": pages_fetched,
        "per_page_title_counts": [len(entries)],
        "all_entries": entries,
        "n_deleted_skipped": 0,
        "n_distinct_urls": len(entries),
        "stop_reason": stop_reason,
        "exception_message": None,
    }


class PinnedPostMustNotSkewOldestPostTime(unittest.TestCase):
    """**什麼輸入會讓它 FAIL**：v1 的 `min(全部條目)`——這裡真實重現這個場景，
    對「用 min 判斷」的舊實作，`oldest_post_time` 會被拉到 8 個月前。
    """

    # 三篇近期文章（同一頁，時間相近）+ 一篇 8 個月前的置底公告——
    # 比照 tests/test_ptt_board_pages.py V13 的既有樣本時間戳（1768934799 = 2026-01-21）。
    PINNED_TS = 1768934799  # 2026-01-21（生產 E3 修正記錄的同一個真實置底公告）
    RECENT_TS = [1789977891, 1789977955, 1789970453]  # 2026-09 前後三天內

    def test_oldest_post_time_excludes_the_pinned_post(self):
        entries = [
            _entry(0, "[標的] 2330 台積電", self.RECENT_TS[0]),
            _entry(0, "[新聞] 法說會", self.RECENT_TS[1]),
            _entry(0, "[請益] 資金配置", self.RECENT_TS[2]),
            _entry(0, "[公告] 4-6-1罰則將在1/22開始到年底加重至30天", self.PINNED_TS),
        ]
        probe = _make_probe(entries)
        report = build_report(probe, total_wall_seconds=10.0)

        recent_min = datetime.fromtimestamp(min(self.RECENT_TS), _TZ).replace(tzinfo=None)
        oldest = datetime.fromisoformat(report["date_range"]["oldest_post_time"])

        self.assertEqual(
            oldest, recent_min,
            "置底公告（8 個月前）不得成為 oldest_post_time 的依據——"
            "它會讓 pages_per_day 被嚴重低估，正是本案複核第一輪抓到的缺陷",
        )

    def test_pinned_post_is_listed_not_silently_dropped(self):
        entries = [
            _entry(0, "[標的] 2330 台積電", self.RECENT_TS[0]),
            _entry(0, "[公告] 板規", self.PINNED_TS),
        ]
        probe = _make_probe(entries)
        report = build_report(probe, total_wall_seconds=10.0)

        self.assertEqual(len(report["pinned_posts_excluded"]), 1)
        self.assertEqual(report["pinned_posts_excluded"][0]["title"], "[公告] 板規")

    def test_no_pinned_post_all_entries_count_toward_oldest(self):
        """反向釘子：沒有離群值時，排除清單必須是空的——不能為了防置底文，
        連正常的舊文章也一起濾掉。"""
        entries = [
            _entry(0, "[標的] 台積電", self.RECENT_TS[0]),
            _entry(0, "[新聞] 財報", self.RECENT_TS[1]),
        ]
        probe = _make_probe(entries)
        report = build_report(probe, total_wall_seconds=10.0)

        self.assertEqual(report["pinned_posts_excluded"], [])
        expected_oldest = datetime.fromtimestamp(
            min(self.RECENT_TS[:2]), _TZ
        ).replace(tzinfo=None)
        self.assertEqual(
            datetime.fromisoformat(report["date_range"]["oldest_post_time"]), expected_oldest
        )

    def test_boundary_just_under_threshold_not_excluded(self):
        """離群判準是「比該頁最新一篇早超過 PINNED_POST_OUTLIER_DAYS」——
        剛好等於門檻不算離群（嚴格大於），確認邊界不是差一天就整個邏輯翻面。
        """
        newest_ts = self.RECENT_TS[0]
        just_under_ts = newest_ts - int(
            timedelta(days=PINNED_POST_OUTLIER_DAYS).total_seconds()
        ) + 60  # 差門檻 1 分鐘，明確在門檻內
        entries = [
            _entry(0, "[標的] 台積電", newest_ts),
            _entry(0, "[舊文] 剛好在門檻內", just_under_ts),
        ]
        probe = _make_probe(entries)
        report = build_report(probe, total_wall_seconds=10.0)

        self.assertEqual(
            report["pinned_posts_excluded"], [],
            "剛好在 7 天門檻內的舊文章不該被當成離群值排除",
        )


if __name__ == "__main__":
    unittest.main()
