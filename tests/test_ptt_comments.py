"""
tests/test_ptt_comments.py — UG-G2-SB2 PTT 內頁留言解析專項測試

涵蓋：parse_article_comments() 的推/噓/→ 計數與完整時間戳記解析、
scrape_ptt_stock_by_keyword() 依 MULTI_SOURCE_DATA_CONTRACT.md §3.5 拆分後的
Failure Semantics（單篇解析失敗＝SOURCE_DEGRADED，續爬；來源完全不可達＝
SOURCE_FAILED，拋出 PttSourceUnavailableError，不回傳空 DataFrame）。
"""

import sys
import types
import unittest
from unittest.mock import patch, MagicMock

if "tenacity" not in sys.modules:
    tenacity = types.ModuleType("tenacity")
    tenacity.retry = lambda *a, **k: (lambda f: f)
    tenacity.stop_after_attempt = MagicMock()
    tenacity.wait_exponential = MagicMock()
    sys.modules["tenacity"] = tenacity

from src.extractors.ptt_scraper import PttScraper, PttSourceUnavailableError


ARTICLE_PAGE_HTML = """
<html><body>
<div class="article-metaline">
  <span class="article-meta-tag">作者</span>
  <span class="article-meta-value">test_user (Tester)</span>
</div>
<div class="article-metaline">
  <span class="article-meta-tag">標題</span>
  <span class="article-meta-value">[新聞] 測試標題</span>
</div>
<div class="article-metaline">
  <span class="article-meta-tag">時間</span>
  <span class="article-meta-value">Wed Aug 26 14:25:36 2026</span>
</div>
<div class="push"><span class="push-tag">推 </span><span class="push-userid">a</span><span class="push-content">: 好</span></div>
<div class="push"><span class="push-tag">推 </span><span class="push-userid">b</span><span class="push-content">: 讚</span></div>
<div class="push"><span class="push-tag">噓 </span><span class="push-userid">c</span><span class="push-content">: 差</span></div>
<div class="push"><span class="push-tag">→ </span><span class="push-userid">d</span><span class="push-content">: 路過</span></div>
</body></html>
"""

LIST_PAGE_HTML_TEMPLATE = """
<html><body>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/{filename}.html">{title}</a></div>
  <div class="date">{date}</div>
  <div class="author">{author}</div>
  <div class="nrec">{nrec}</div>
</div>
<div class="btn-group btn-group-paging"><a>下頁</a><a>下頁</a></div>
</body></html>
"""

MALFORMED_ENTRY_HTML = """
<html><body>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.1.A.1.html">第一篇正常文章</a></div>
  <div class="date"> 8/26</div>
  <div class="author">ok_user_1</div>
  <div class="nrec">5</div>
</div>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.2.A.2.html">缺少 date 欄位的文章</a></div>
  <div class="author">broken_user</div>
</div>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.3.A.3.html">第三篇正常文章</a></div>
  <div class="date"> 8/27</div>
  <div class="author">ok_user_3</div>
  <div class="nrec">2</div>
</div>
<div class="btn-group btn-group-paging"><a>下頁</a></div>
</body></html>
"""


class ParseArticleCommentsTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_parse_push / test_parse_boo / test_parse_neutral"""

    def setUp(self):
        self.scraper = PttScraper()

    @patch("time.sleep", return_value=None)
    @patch.object(PttScraper, "_fetch_page", return_value=ARTICLE_PAGE_HTML)
    def test_parse_push_boo_neutral_counts(self, mock_fetch, mock_sleep):
        result = self.scraper.parse_article_comments("https://www.ptt.cc/bbs/Stock/M.1.A.1.html")

        self.assertEqual(result["push_count"], 2)
        self.assertEqual(result["boo_count"], 1)
        self.assertEqual(result["neutral_count"], 1)
        self.assertEqual(result["total_comments"], 4)
        self.assertEqual(result["engagement_metric"], 1)  # push - boo = 2 - 1

    @patch("time.sleep", return_value=None)
    @patch.object(PttScraper, "_fetch_page", return_value=ARTICLE_PAGE_HTML)
    def test_full_datetime_from_inner_page_meta(self, mock_fetch, mock_sleep):
        result = self.scraper.parse_article_comments("https://www.ptt.cc/bbs/Stock/M.1.A.1.html")
        self.assertEqual(result["full_datetime"], "Wed Aug 26 14:25:36 2026")

    @patch("time.sleep", return_value=None)
    @patch.object(PttScraper, "_fetch_page", return_value="<html><body>沒有時間欄位</body></html>")
    def test_full_datetime_none_when_meta_missing(self, mock_fetch, mock_sleep):
        """內頁缺少時間欄位時 full_datetime 應為 None，供呼叫端 fallback 回列表頁 MM/DD，
        不得偽造一個時間值。"""
        result = self.scraper.parse_article_comments("https://www.ptt.cc/bbs/Stock/M.1.A.1.html")
        self.assertIsNone(result["full_datetime"])


class ScrapeFailureSemanticsTests(unittest.TestCase):
    """對應 MULTI_SOURCE_DATA_CONTRACT.md §3.5：SOURCE_DEGRADED / SOURCE_FAILED 區分"""

    def setUp(self):
        self.scraper = PttScraper()

    @patch("time.sleep", return_value=None)
    @patch.object(PttScraper, "_fetch_page", return_value=MALFORMED_ENTRY_HTML)
    def test_source_degraded_on_single_article_failure_continues_others(self, mock_fetch, mock_sleep):
        """Known-FAIL 案例：三篇文章，中間那篇缺少 date 欄位，讓
        entry.find("div", class_="date").text 丟出 AttributeError。

        這個 fixture 必須是三篇（正常/缺欄位/正常），不能只有兩篇且缺欄位那篇排最後——
        後者無法區分新舊行為：舊版第一篇早在崩潰前就已 append，`except: break` 剛好
        「順便」保住它，兩篇版 fixture 下新舊程式碼會得到一模一樣的 len=1 結果，
        測試本身結構上不可能失敗（CLAUDE.md §9A.1，PO 2026-08-27 實測發現並指出）。

        三篇版才有真正的偵測力：修正前（單一 except Exception: break）在第二篇崩潰時
        直接跳出整個分頁迴圈，第三篇永遠不會被處理到，結果只剩第一篇（len=1）；
        修正後應跳過第二篇、繼續處理第三篇，保留第一篇與第三篇（len=2）。"""
        df = self.scraper.scrape_ptt_stock_by_keyword("台積電", max_pages=1)

        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["title"], "第一篇正常文章")
        self.assertEqual(df.iloc[1]["title"], "第三篇正常文章")

    @patch("time.sleep", return_value=None)
    @patch.object(PttScraper, "_fetch_page", side_effect=Exception("Connection refused"))
    def test_source_failed_raises_exception_not_empty_dataframe(self, mock_fetch, mock_sleep):
        """Known-FAIL 案例：第一頁即抓取失敗（已收集資料為空），修正前會回傳空 DataFrame，
        使呼叫端無法區分「PTT 不可達」與「這個關鍵字真的沒有文章」（CLAUDE.md §7.1）。
        修正後應拋出 PttSourceUnavailableError，不回傳任何 DataFrame。"""
        with self.assertRaises(PttSourceUnavailableError):
            self.scraper.scrape_ptt_stock_by_keyword("台積電", max_pages=1)

    @patch("time.sleep", return_value=None)
    def test_source_degraded_when_later_page_fails_after_partial_success(self, mock_sleep):
        """第一頁成功、第二頁抓取失敗（重試耗盡）：已收集之第一頁資料應保留，
        不應因第二頁失敗而拋出例外或整批清空（SOURCE_DEGRADED，非 SOURCE_FAILED）。"""
        page1_html = LIST_PAGE_HTML_TEMPLATE.format(
            filename="M.1.A.1", title="第一頁文章", date=" 8/26", author="u1", nrec="3"
        )

        with patch.object(PttScraper, "_fetch_page", side_effect=[page1_html, Exception("timeout")]):
            df = self.scraper.scrape_ptt_stock_by_keyword("台積電", max_pages=2)

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["title"], "第一頁文章")


if __name__ == "__main__":
    unittest.main()
