# -*- coding: utf-8 -*-
"""§0.5 #40 段 B2：`PttScraper.scrape_ptt_board_pages_capture_all()`（新方法）。

Gate A 提案：doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md §3.3
（extra_page_delay 一節：PO 裁決 2026-09-21 的段 B2 補段）。

================================================================================
先 RED 後 GREEN——本檔在實作之前寫
================================================================================
對應提案 §4 的 5 個測項，逐項展開為 10 條實際斷言（部分測項的「頁數/停止
時機」「延遲區間」等需要多條斷言才能完整核對，不是一項一條硬性對應）。
**全數鎖定新方法**，對現行程式碼皆為 `AttributeError`（方法不存在）——
紅測 FAIL 數＝10，與新增測試數一致（`TEAM_PLAYBOOK.md` A13，逐條核對見下方
執行輸出）。

`scrape_ptt_board_pages()`（既有方法）的行為金標**不在本檔**，放在
`tests/test_ptt_board_pages.py` 第 19 條（V19）——它鎖定的是未修改的舊方法，
引入時即為 PASS，不是紅測證據，混進本檔會讓「紅 FAIL 數＝新增測試數」不成立。
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from tests.test_ptt_board_pages import board_page_html


class CaptureAllReturnsEveryTitleUnfiltered(unittest.TestCase):
    """**測項 1**：不接受 `keywords` 參數，回傳全部標題，不受任何過濾。

    **什麼輸入會讓它 FAIL**：對現行程式碼 `AttributeError`（方法不存在）。
    """

    def test_returns_all_titles_no_keyword_filter(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1789900000, "a"),
             ("[心得] 完全不相關的閒聊", 1789900100, "b"),
             ("[新聞] 隨便一則新聞", 1789900200, "c")],
            has_prev=False))
        df, outcome = s.scrape_ptt_board_pages_capture_all()

        self.assertEqual(len(df), 3, "不接受 keywords，理論上應該回傳全部標題")
        self.assertEqual(outcome, "OK")

    def test_signature_has_no_keywords_parameter(self):
        import inspect

        from src.extractors.ptt_scraper import PttScraper

        sig = inspect.signature(PttScraper.scrape_ptt_board_pages_capture_all)
        self.assertNotIn("keywords", sig.parameters,
                         "本方法的用途就是捕捉全部標題，不做關鍵字過濾")

    def test_rows_carry_their_own_page_index(self):
        """複核發現：B2 腳本的置底排除邏輯需要逐頁比較，前提是每列知道自己
        屬於哪一頁——這個欄位本次一併補上。"""
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(side_effect=[
            board_page_html([("[標的] 台積電", 1789900000, "a")], has_prev=True),
            board_page_html([("[新聞] 聯發科", 1789800000, "b")], has_prev=False),
        ])
        df, outcome = s.scrape_ptt_board_pages_capture_all(page_budget=5)

        self.assertEqual(df.iloc[0]["page_index"], 0)
        self.assertEqual(df.iloc[1]["page_index"], 1,
                         "第二頁抓到的列必須標記 page_index==1，"
                         "供量測腳本逐頁（非逐全體）判定置底／離群值")


class CaptureAllOnlyGoesThroughSharedFetchPage(unittest.TestCase):
    """**測項 2**：唯一請求出口不變——只透過 `self._fetch_page`。

    比照既有 `V9MustGoThroughTheSharedFetchPage` 的構造法。
    **什麼輸入會讓它 FAIL**：對現行程式碼 `AttributeError`。
    """

    def test_no_direct_requests_get(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1789900000, "a")], has_prev=False))
        with patch("src.extractors.ptt_scraper.requests.get") as mock_get:
            s.scrape_ptt_board_pages_capture_all()
        mock_get.assert_not_called()
        self.assertEqual(s._fetch_page.call_count, 1)


class CaptureAllStopLogicMatchesExistingMethod(unittest.TestCase):
    """**測項 3**：`page_budget`／`since_timestamp` 的停止邏輯與
    `scrape_ptt_board_pages()` 行為一致（複用既有 V8/V10 合成頁面 fixture）。

    **什麼輸入會讓它 FAIL**：對現行程式碼 `AttributeError`。
    """

    def test_budget_is_enforced(self):
        from src.extractors.ptt_scraper import BOARD_PAGE_BUDGET, PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[新聞] x", 1757000000, "u")], has_prev=True))
        df, outcome = s.scrape_ptt_board_pages_capture_all(since_timestamp=1)
        self.assertEqual(s._fetch_page.call_count, BOARD_PAGE_BUDGET)
        self.assertEqual(outcome, "SOURCE_DEGRADED")

    def test_stops_early_when_reaching_since_timestamp(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 台積電", 1000, "u")], has_prev=True))
        df, outcome = s.scrape_ptt_board_pages_capture_all(since_timestamp=2000)
        self.assertEqual(s._fetch_page.call_count, 1)
        self.assertEqual(outcome, "OK")

    def test_explicit_page_budget_honored(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[新聞] x", 1757000000, "u")], has_prev=True))
        df, outcome = s.scrape_ptt_board_pages_capture_all(page_budget=3)
        self.assertEqual(s._fetch_page.call_count, 3)


class CaptureAllFailureSemantics(unittest.TestCase):
    """**測項 4**：第一頁失敗 → `PttSourceUnavailableError`；後續頁失敗 →
    保留已收集資料、`SOURCE_DEGRADED`。

    **什麼輸入會讓它 FAIL**：對現行程式碼 `AttributeError`。
    """

    def test_first_page_failure_raises_source_unavailable(self):
        from src.extractors.ptt_scraper import PttScraper, PttSourceUnavailableError

        s = PttScraper()
        s._fetch_page = MagicMock(side_effect=RuntimeError("boom"))
        with self.assertRaises(PttSourceUnavailableError):
            s.scrape_ptt_board_pages_capture_all()

    def test_later_page_failure_keeps_collected_rows_and_degrades(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(side_effect=[
            board_page_html(
                [("[標的] 台積電", 1789900000, "a")], has_prev=True),
            RuntimeError("boom"),
        ])
        df, outcome = s.scrape_ptt_board_pages_capture_all()
        self.assertEqual(len(df), 1, "第一頁已收集的資料必須保留")
        self.assertEqual(outcome, "SOURCE_DEGRADED")


class CaptureAllExtraPageDelay(unittest.TestCase):
    """**測項 5**：`extra_page_delay`——PO 裁決 2026-09-21 段 B2 補段。

    延遲加倍**不修改 `_fetch_page()`**（DEC-032：唯一請求出口，不得修改）——
    改由新方法在每頁之間**另加**一段 `random.uniform(1.0, 2.5)` 秒等待，
    合計每頁 2.0～5.0 秒。`extra_page_delay` 預設 `0`（生產路徑與一般呼叫
    不受影響），只有 B2 腳本明確傳入非零值才啟用。

    **什麼輸入會讓它 FAIL**：把預設值改成非 0（對現行程式碼：`AttributeError`，
    方法尚不存在；方法存在後若把預設改為非零，本測項 1 會偵測到）。
    """

    def test_default_zero_does_not_sleep(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 台積電", 1789900000, "a")], has_prev=False))
        with patch("src.extractors.ptt_scraper.time.sleep") as mock_sleep:
            s.scrape_ptt_board_pages_capture_all()
        mock_sleep.assert_not_called()

    def test_positive_delay_sleeps_once_per_page_with_correct_range(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(side_effect=[
            board_page_html([("[標的] 台積電", 1789900000, "a")], has_prev=True),
            board_page_html([("[新聞] 聯發科", 1789800000, "b")], has_prev=False),
        ])
        with patch("src.extractors.ptt_scraper.time.sleep") as mock_sleep, \
             patch("src.extractors.ptt_scraper.random.uniform",
                   return_value=1.5) as mock_uniform:
            s.scrape_ptt_board_pages_capture_all(extra_page_delay=1, page_budget=5)

        self.assertEqual(mock_sleep.call_count, 2, "兩頁各恰一次額外延遲")
        for call in mock_uniform.call_args_list:
            self.assertEqual(call.args, (1.0, 2.5),
                             "額外延遲的區間必須是 1.0～2.5 秒，"
                             "與 _fetch_page() 既有延遲的區間相同（PO 裁決：延遲加倍）")


if __name__ == "__main__":
    unittest.main()
