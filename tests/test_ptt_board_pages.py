# -*- coding: utf-8 -*-
"""UG-G2-SB7 第 5 項：看板固定頁面抓取 + 記憶體比對（V6~V11）。

================================================================================
本檔在實作之前寫，並先於修正 commit
================================================================================
沿用本 SB 已用五次的紀律：**先 commit 會紅的測試，再 commit 修正** ——
那時紅是 git 歷史裡的事實，不是從 diff 推導（DEC-033 §Decision 第 6 條的類推）。

================================================================================
三個條件各有釘住它的檢查（複查方 2026-09-05）
================================================================================
| 條件 | 檢查 |
|------|------|
| 2（`source` 值要跟著改） | V6、V7 |
| 3（請求量與 DEC-032） | V8、V9、V10 |
| §0（記憶體比對的鍵） | V11 |

**V6、V8、V10 為 known-FAIL 主體。**
"""
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(REPO, "doc", "upgrade", "contracts",
                        "MULTI_SOURCE_DATA_CONTRACT.md")


def board_page_html(entries, has_prev=True):
    """造一頁看板索引 HTML。

    `entries`：`(title, ts, author)` —— `ts` 為 PTT URL 內嵌的 unix 時間戳。
    **刻意用 URL 的時間戳而非畫面上的日期**：後者形如 `9/05`，
    **沒有年份、沒有時刻**，跨年時無法比較。URL 的 `M.<ts>.A.<n>` 是精確值。
    """
    rows = []
    for title, ts, author in entries:
        rows.append(
            '<div class="r-ent">'
            '<div class="nrec"><span>10</span></div>'
            '<div class="title"><a href="/bbs/Stock/M.%d.A.001.html">%s</a></div>'
            '<div class="author">%s</div>'
            '<div class="date"> 9/05</div>'
            '</div>' % (ts, title, author))
    prev = ('<a class="btn wide" href="/bbs/Stock/index100.html">&lsaquo; 上頁</a>'
            if has_prev else '<a class="btn wide disabled">&lsaquo; 上頁</a>')
    return ('<html><body>%s'
            '<div class="btn-group btn-group-paging">'
            '<a class="btn wide">最舊</a>%s'
            '</div></body></html>' % ("".join(rows), prev))


class V6NewModeUsesItsOwnSourceValue(unittest.TestCase):
    """**V6**：新模式寫入的列 `source == 'ptt_board_pages'`。

    **什麼輸入會讓它 FAIL**：沿用 `'ptt_stock'`。

    > 先例是本專案自己的：`source` 用 `tpex_daily_quotes` 而不是 `tpex` ——
    > **來源標記要指向「哪一份報表」，不是「哪個機構」。**
    > **逐關鍵字搜尋與固定頁面抓取，是兩份不同的「報表」。**
    """

    def test_board_mode_rows_carry_the_new_source(self):
        from src.extractors.ptt_scraper import PttScraper, SOURCE_BOARD_PAGES
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1757000000, "userA")], has_prev=False))
        df, outcome = s.scrape_ptt_board_pages(["台積電"])
        self.assertGreater(len(df), 0)
        self.assertTrue((df["source"] == SOURCE_BOARD_PAGES).all())
        self.assertEqual(SOURCE_BOARD_PAGES, "ptt_board_pages")

    def test_the_three_source_values_are_distinct(self):
        from src.extractors.ptt_scraper import (
            SOURCE_BOARD_PAGES, SOURCE_KEYWORD_SEARCH, SOURCE_LEGACY)
        vals = [SOURCE_LEGACY, SOURCE_KEYWORD_SEARCH, SOURCE_BOARD_PAGES]
        self.assertEqual(len(set(vals)), 3)
        for v in vals:
            self.assertLessEqual(len(v), 20,
                                 "`market_articles.source` 是 VARCHAR(20)")


class V7TheMappingMustLiveInTheContractNotTheProposal(unittest.TestCase):
    """**V7**：三個 `source` 值的對應關係必須寫在 `MULTI_SOURCE_DATA_CONTRACT.md`。

    **什麼輸入會讓它 FAIL**：只寫在提案裡。

    > **提案通過 Gate B 後會移入 `closed/`（§16.3）** ——
    > **一份會被歸檔的文件，不能是某個對應關係的唯一記載處。**
    """

    def test_contract_documents_all_three_values(self):
        text = io.open(CONTRACT, encoding="utf-8").read()
        from src.extractors.ptt_scraper import (
            SOURCE_BOARD_PAGES, SOURCE_KEYWORD_SEARCH, SOURCE_LEGACY)
        for v in (SOURCE_LEGACY, SOURCE_KEYWORD_SEARCH, SOURCE_BOARD_PAGES):
            self.assertIn(v, text,
                          "`%s` 的意義必須寫在契約文件裡，**不能只寫在提案裡** —— "
                          "提案會移入 closed/" % v)


class V8V10RequestBudget(unittest.TestCase):
    """**V8／V10**：請求預算與用盡時的處置。

    **V8 的 FAIL 輸入**：移除預算或改為無上限。
    **V10 的 FAIL 輸入**：用盡後繼續請求。

    > 預算 **25** 不是「25 頁是對的」，是**「25 是我們已經在用的量，
    > 不因換模式而增加」**（現行 25 個啟用關鍵字 × 1 頁）。
    > **那是一個約束，不是一個門檻 —— 約束不需要從觀測推導，它只需要有理由。**
    """

    def test_v8_budget_is_twenty_five_and_enforced(self):
        from src.extractors.ptt_scraper import BOARD_PAGE_BUDGET, PttScraper
        self.assertEqual(BOARD_PAGE_BUDGET, 25)
        s = PttScraper()
        # 每頁都比 since 新 → 永遠不會自然停止，只能靠預算擋下
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[新聞] x", 1757000000, "u")], has_prev=True))
        df, outcome = s.scrape_ptt_board_pages(["x"], since_timestamp=1)
        self.assertEqual(s._fetch_page.call_count, BOARD_PAGE_BUDGET,
                         "請求數不得超過預算 —— 沒有上限的回溯是無界的")

    def test_v10_exhausted_budget_is_source_degraded(self):
        """用盡預算而未回溯到目標時間 → `SOURCE_DEGRADED`，**且不繼續請求**。"""
        from src.extractors.ptt_scraper import BOARD_PAGE_BUDGET, PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[新聞] x", 1757000000, "u")], has_prev=True))
        df, outcome = s.scrape_ptt_board_pages(["x"], since_timestamp=1)
        self.assertEqual(outcome, "SOURCE_DEGRADED",
                         "**未回溯到目標時間就停下來，是部分成功，不是成功** —— "
                         "把它記成 OK 會讓「少抓了幾天」變得看不見")
        self.assertLessEqual(s._fetch_page.call_count, BOARD_PAGE_BUDGET)

    def test_stops_early_when_reaching_since_timestamp(self):
        """回溯到目標時間即停 —— **預期實際用量遠低於上界**。"""
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 台積電", 1000, "u")], has_prev=True))
        df, outcome = s.scrape_ptt_board_pages(["台積電"], since_timestamp=2000)
        self.assertEqual(s._fetch_page.call_count, 1)
        self.assertEqual(outcome, "OK")

    def test_first_page_failure_is_source_unavailable(self):
        """首頁即失敗 → `PttSourceUnavailableError`（沿用既有 failure semantics）。"""
        from src.extractors.ptt_scraper import (
            PttScraper, PttSourceUnavailableError)
        s = PttScraper()
        s._fetch_page = MagicMock(side_effect=RuntimeError("boom"))
        with self.assertRaises(PttSourceUnavailableError):
            s.scrape_ptt_board_pages(["台積電"])


class V9MustGoThroughTheSharedFetchPage(unittest.TestCase):
    """**V9**：新路徑必須走同一個 `_fetch_page`，不得另開 HTTP 入口。

    **什麼輸入會讓它 FAIL**：直接呼叫 `requests.get`。

    > `_fetch_page` 是 DEC-032 判別式的落點（`0047d98`）。
    > **一個修好的東西，最可能的回退方式不是被改回去，是被繞過去。**
    """

    def test_no_direct_requests_get_in_the_new_path(self):
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 台積電", 1757000000, "u")], has_prev=False))
        with patch("src.extractors.ptt_scraper.requests.get") as direct:
            s.scrape_ptt_board_pages(["台積電"])
        self.assertEqual(direct.call_count, 0,
                         "另開 HTTP 入口會繞過 DEC-032 的 403/429 硬停判別")
        self.assertGreater(s._fetch_page.call_count, 0)


class V11InMemoryMatchUsesUrlAsTheKey(unittest.TestCase):
    """**V11**：去重以 `url` 為鍵，不以標題或作者。

    **什麼輸入會讓它 FAIL**：以標題比對 —— **同名不同篇會被誤判為重複**。
    """

    def test_same_title_different_url_are_both_kept(self):
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1757000000, "userA"),
             ("[標的] 2330 台積電", 1757000001, "userB")], has_prev=False))
        df, _ = s.scrape_ptt_board_pages(["台積電"])
        self.assertEqual(len(df), 2,
                         "**同名不同篇不是重複** —— 以標題比對會把它們合成一筆")
        self.assertEqual(df["url"].nunique(), 2)

    def test_same_url_seen_twice_is_deduplicated(self):
        """同一 URL 在兩頁都出現（PTT 分頁邊界）→ 只保留一筆。"""
        from src.extractors.ptt_scraper import PttScraper
        page = board_page_html([("[標的] 台積電", 1757000000, "u")], has_prev=True)
        s = PttScraper()
        s._fetch_page = MagicMock(side_effect=[page, page.replace(
            "index100", "index99")])
        df, _ = s.scrape_ptt_board_pages(["台積電"], since_timestamp=1,
                                         page_budget=2)
        self.assertEqual(len(df), 1)


class InMemoryKeywordFiltering(unittest.TestCase):
    """記憶體比對本身：只保留標題含追蹤關鍵字者。"""

    def test_only_matching_titles_are_kept(self):
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1757000000, "a"),
             ("[閒聊] 今天天氣", 1757000001, "b"),
             ("[新聞] 聯發科法說", 1757000002, "c")], has_prev=False))
        df, _ = s.scrape_ptt_board_pages(["台積電", "聯發科"])
        self.assertEqual(len(df), 2)
        self.assertEqual(set(df["fetch_keyword"]), {"台積電", "聯發科"})

    def test_no_match_is_no_data_not_failure(self):
        """一篇都沒中 → `NO_DATA`，**不是失敗**。"""
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[閒聊] 今天天氣", 1757000000, "b")], has_prev=False))
        df, outcome = s.scrape_ptt_board_pages(["台積電"])
        self.assertEqual(len(df), 0)
        self.assertEqual(outcome, "NO_DATA",
                         "抓到了頁面、只是沒有命中 —— 那是有效觀測")


class V12ChangingSourceMustNotSilentlyDisableACapability(unittest.TestCase):
    """**V12**：換掉 `source` 值不得讓下游的能力宣告悄悄失效。

    **本項不在核准的六項檢查內** —— 是施工時發現的、由本次變更引入的缺陷，
    依 §9A.1 的判準（「有哪一種輸入會讓它 FAIL？」）補上。

    ================================================================================
    缺陷長什麼樣
    ================================================================================
    `src/transform/source_capabilities.py` 的 `COMMENT_DIRECTION_SOURCES`
    原本是 `frozenset({"ptt_stock"})`。新模式寫入的列 `source` 是
    `ptt_board_pages` —— **不在集合裡**，於是
    `provides_comment_direction()` 對**每一列新資料**回傳 `False`，
    `comment_polarization` 與 `net_push_momentum` 全部變 `NULL`。

    > **而那兩個特徵用的是同一批 PTT 內頁，方向能力一點都沒少。**

    ================================================================================
    為什麼它不會自己被發現
    ================================================================================
    該模組的預設方向是**刻意 fail-safe** 的（模組 docstring 逐字：
    「漏登錄的後果 → 方向類特徵為 `NULL`（**誠實地少**）」）。
    **那個設計是對的，而它也正是這個缺陷不會報錯的原因** ——
    少掉的特徵不會拋例外、不會讓測試變紅，只會讓兩欄安靜地全空。

    **一個 fail-safe 的預設，讓漏登錄變成一件不痛的事。**
    所以它需要一個檢查，而不是靠記得。

    **什麼輸入會讓它 FAIL**：新增一個 PTT 取數模式而忘了登錄。
    """

    def test_every_ptt_source_value_provides_comment_direction(self):
        from src.extractors import ptt_scraper as ps
        from src.transform.source_capabilities import (
            COMMENT_DIRECTION_SOURCES, provides_comment_direction)
        for v in (ps.SOURCE_LEGACY, ps.SOURCE_KEYWORD_SEARCH,
                  ps.SOURCE_BOARD_PAGES):
            self.assertIn(v, COMMENT_DIRECTION_SOURCES,
                          "`%s` 是 PTT 的取數模式之一，**推／噓標記一點都沒少** —— "
                          "沒登錄會讓 comment_polarization 與 net_push_momentum "
                          "對每一列新資料安靜地變 NULL" % v)
            self.assertTrue(provides_comment_direction(v))

    def test_a_non_ptt_source_still_has_no_direction(self):
        """**反向釘子**：不要為了讓上面那條過，就把集合改成「全部都算」。"""
        from src.transform.source_capabilities import provides_comment_direction
        self.assertFalse(provides_comment_direction("dcard"))
        self.assertFalse(provides_comment_direction("threads"))


class KeywordSearchModeMustCarryItsOwnSourceValue(unittest.TestCase):
    """`scrape_ptt_stock_by_keyword` 依 §3.5A 寫入 `ptt_keyword_search`。

    **什麼輸入會讓它 FAIL**：留在 `ptt_stock`。

    ⚠ **既有 331 列不回填**（複查方 2026-09-05 核准）：
    `ptt_stock` 與 `ptt_keyword_search` 在資訊量上等價（該模式是本專案
    唯一存在過的 PTT 取數方式），而回填要改寫既有歷史資料。
    **改寫歷史資料換取一個零資訊增益的整齊，不划算。**
    """

    def test_keyword_mode_rows_carry_ptt_keyword_search(self):
        from src.extractors.ptt_scraper import PttScraper, SOURCE_KEYWORD_SEARCH
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1757000000, "userA")], has_prev=False))
        df = s.scrape_ptt_stock_by_keyword("台積電", max_pages=1)
        self.assertGreater(len(df), 0)
        self.assertTrue((df["source"] == SOURCE_KEYWORD_SEARCH).all())


class V13APinnedPostMustNotTruncateTheBacktrack(unittest.TestCase):
    """**V13**：一篇時間戳很舊的置底文，不得讓回溯在第一頁就停下來。

    ================================================================================
    這是生產實測抓到的，不是設計時想到的
    ================================================================================
    2026-09-05 的受控執行（`evidence/G2_SB7_controlled_run_results.json`）：

    ```
    [Extract] 已回溯至 1768934799 <= 1788414806，停止翻頁。
    [Extract] 看板頁面模式完成：1 頁請求，1 筆命中，outcome=OK
    ```

    `1768934799` = **2026-01-21**，而那是看板**最新**的一頁。
    PTT 的置底公告附在最新一頁上、時間戳很舊，
    而停止條件用的是 `min(全頁時間戳)` —— **被置底文一次擊沉。**

    ================================================================================
    ⚠ 它出錯的方式，正是本 SB 從頭在防的形狀
    ================================================================================
    > **它讓被截斷的抓取看起來像成功的回溯。**
    > outcome 回報 `OK` 而不是 `SOURCE_DEGRADED`，因為程式相信自己已回溯到目標時間。
    > 於是 25 個關鍵字拿到 `NO_DATA`，在 run log 裡宣稱「那天沒有討論」——
    > **實際上是我們只看了一頁。**

    E3 的界寫的是 1~25 頁，實測 1 頁**落在界內** ——
    **而落在界內不等於對。一個區間判準通過，不代表被量的東西是對的。**

    ================================================================================
    為什麼是 `max` 而不是「取第一個 r-ent」
    ================================================================================
    「取第一個 `r-ent`」依賴**兩個推論**：頁內由舊到新排列、置底文附加在末端。
    **那需要一次線上抓取才能查證。**

    `max` 不需要任何排序假設：

    > **置底文的時間戳是「舊」的 —— 它拉低 `min`，永遠不會拉高 `max`。**

    語意也正確且保守：「這一頁**最新**的一篇都比目標舊」
    ⟹ 這一頁與所有更舊的頁都在目標之前 ⟹ 可以停。

    **它只可能多抓一頁，不可能少抓** —— 而**少抓是危險的方向**（靜默截斷），
    多抓的代價是一個請求。

    **什麼輸入會讓它 FAIL**：用 `min(全頁時間戳)` 當停止依據（即修正前的實作）。
    """

    # 近期三篇 + 一篇 2026-01-21 的置底公告（實測樣本的時間戳）
    PINNED_TS = 1768934799
    RECENT = [("[標的] 2330 台積電", 1788600000, "a"),
              ("[新聞] 台積電法說", 1788600100, "b"),
              ("[請益] 台積電", 1788600200, "c")]
    PINNED = [("[公告] 板規", PINNED_TS, "moderator")]

    def test_pinned_post_does_not_stop_paging_on_page_one(self):
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            self.RECENT + self.PINNED, has_prev=True))
        # 目標時間比三篇近期文都舊 → **不該停**；而置底文比它舊。
        df, outcome = s.scrape_ptt_board_pages(
            ["台積電"], since_timestamp=1788500000, page_budget=3)
        self.assertEqual(s._fetch_page.call_count, 3,
                         "置底文的舊時間戳不得成為「已經回溯夠了」的依據 —— "
                         "**它讓被截斷的抓取看起來像成功的回溯**")

    def test_truncated_backtrack_is_degraded_not_ok(self):
        """截斷時 outcome 必須是 `SOURCE_DEGRADED`，**不是 `OK`**。

        生產實測那次回報的正是 `OK` —— **那個 `OK` 是本項要防的東西。**
        """
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            self.RECENT + self.PINNED, has_prev=True))
        df, outcome = s.scrape_ptt_board_pages(
            ["台積電"], since_timestamp=1788500000, page_budget=3)
        self.assertEqual(outcome, "SOURCE_DEGRADED")

    def test_stops_when_the_newest_entry_is_older_than_the_target(self):
        """**反向釘子**：整頁都比目標舊時仍須停 —— 否則會一路翻到預算用盡。

        不要為了讓上面兩條過，就把停止條件整個拿掉。
        """
        from src.extractors.ptt_scraper import PttScraper
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 台積電", 1000, "a"), ("[公告] 板規", 500, "m")],
            has_prev=True))
        df, outcome = s.scrape_ptt_board_pages(
            ["台積電"], since_timestamp=2000, page_budget=5)
        self.assertEqual(s._fetch_page.call_count, 1)
        self.assertEqual(outcome, "OK")


class V19ScrapeBoardPagesBehaviorGoldenLockForCaptureAllIntroduction(unittest.TestCase):
    """**V19**：`scrape_ptt_board_pages()` 的行為金標——§0.5 #40 段 B2 新增
    `scrape_ptt_board_pages_capture_all()` 時的回歸鎖定。

    ================================================================================
    這條測試在引入時即為綠燈，不是紅測證據
    ================================================================================
    它鎖定的是**既有、未修改**的 `scrape_ptt_board_pages()`，在現行程式碼上
    引入時就會 PASS——`TEAM_PLAYBOOK.md` A13：紅測 FAIL 數必須等於新增測試數，
    這條不計入 `tests/test_ptt_board_pages_capture_all.py` 的紅測清單（見該檔
    docstring），改放在既有檔案裡，docstring 明寫其偵測力來源。

    **偵測力不由紅測階段證明，而由 `PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_
    PROPOSAL.md` §4 記錄的突變測試證明**：把比對邏輯 `if kw not in title:
    continue`（子字串包含）改成 `if kw != title: continue`（完全相等），對
    同一組合成 fixture 重跑，回傳列數從 2 降為 0、`outcome` 從 `OK` 轉為
    `NO_DATA`——已在容器內 `/tmp` 拋棄式 mirror 實際構造並執行（提案送審前，
    非本次），復原後確認回到 2 列／`OK`，mirror 事後整個刪除。

    **什麼輸入會讓它 FAIL**：`scrape_ptt_board_pages()` 的比對邏輯、去重鍵、
    停止條件三者任一被意外修改。
    """

    def test_scrape_ptt_board_pages_behavior_unchanged(self):
        from src.extractors.ptt_scraper import PttScraper

        s = PttScraper()
        s._fetch_page = MagicMock(return_value=board_page_html(
            [("[標的] 2330 台積電", 1789900000, "a"),
             ("[新聞] 聯發科法說", 1789900100, "b"),
             ("[請益] 大盤走勢", 1789900200, "c")],
            has_prev=False))
        df, outcome = s.scrape_ptt_board_pages(["台積電", "聯發科"])

        self.assertEqual(len(df), 2)
        self.assertEqual(set(df["fetch_keyword"]), {"台積電", "聯發科"})
        self.assertEqual(outcome, "OK")


if __name__ == "__main__":
    unittest.main()
