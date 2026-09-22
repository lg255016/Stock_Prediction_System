import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import random
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.extractors.retry_policy import is_retriable

# ==========================================================================
# UG-G2-SB7 第 5 項：`market_articles.source` 的三個值
# ==========================================================================
# **對應關係的權威在 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5A，不在這裡** ——
# 這裡只是那份契約的程式落點。`tests/test_ptt_board_pages.py` 的 V7
# 會驗證三個值都出現在該文件中。
#
# > 為什麼不能只寫在提案裡：提案通過 Gate B 後會移入 `closed/`（`CLAUDE.md` §16.3）。
# > **一份會被歸檔的文件，不能是某個對應關係的唯一記載處。**
SOURCE_LEGACY = "ptt_stock"                     # 切換前既有的 331 列，**不回填**
SOURCE_KEYWORD_SEARCH = "ptt_keyword_search"    # 逐關鍵字 /search?q=
SOURCE_BOARD_PAGES = "ptt_board_pages"          # 看板固定頁面 + 記憶體比對

# 一次執行的頁面請求上限。
#
# **25 不是「25 頁是對的」，是「25 是我們已經在用的量，不因換模式而增加」** ——
# 現行 25 個啟用關鍵字 x 每關鍵字 1 頁。
# **那是一個約束，不是一個門檻；約束不需要從觀測推導，它只需要有理由。**
BOARD_PAGE_BUDGET = 25

BOARD_INDEX_PATH = "/bbs/Stock/index.html"

# PTT 文章網址內嵌的 unix 時間戳：`/bbs/Stock/M.1724567890.A.123.html`
#
# **刻意用它而不是索引頁上的日期欄** —— 後者形如 `9/05`，
# **沒有年份、沒有時刻**，跨年時無法比較大小。
# 同一個時間戳也是 `data_cleaner.build_ptt_provider_article_id` 的取值來源。
_URL_TIMESTAMP_RE = re.compile(r"/M\.(\d+)\.A\.")


def _url_timestamp(url):
    """取出文章網址的 unix 時間戳；取不到回傳 `None`。

    ⚠ **取不到時回傳 `None` 而非 0** —— 0 會被讀成「1970 年，比任何 since 都舊」，
    於是回溯**當場停止**。**一個解析失敗會偽裝成「已經抓夠了」。**
    """
    m = _URL_TIMESTAMP_RE.search(url or "")
    return int(m.group(1)) if m else None


class PttSourceUnavailableError(Exception):
    """PTT 來源完全不可達（連線失敗、認證失效、重試耗盡且尚無任何已收集資料）。

    依 MULTI_SOURCE_DATA_CONTRACT.md §3.5：此例外必須被拋出，呼叫端不得將其
    誤判為「查無資料」而回傳空 DataFrame（CLAUDE.md §7.1：DB Error != Empty Result）。
    """
    pass


class PttScraper:
    def __init__(self):
        # PTT 的基礎設定與突破 18 歲年齡限制的核心 Cookie
        self.base_url = "https://www.ptt.cc"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.cookies = {"over18": "1"}

    # DEC-032（`APPROVED`）：**403／429 硬停**。
    # PTT 是社群網站——**對一個叫我們停的 429 做三次指數退避，
    # 正是那條紀律要防的行為**。
    @retry(retry=retry_if_exception(is_retriable),
           stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=10),
           reraise=True)
    def _fetch_page(self, url: str) -> str:
        """
        封裝 HTTP 請求，具備 Rate Limiting 與有界重試機制。

        重試紀律依 DEC-032：**傳輸層失敗與 5xx 才重試（退避 2s／4s／8s，上限 3 次）；
        4xx（含 403／429）一次都不重試。**

        > 本 docstring 的前一版逐字寫著「遇到 429 或 500 等錯誤會自動等待
        > 2s, 4s, 8s 重試」——**那是 DEC-032 禁止的行為，而程式自己記載了它**。
        > 保留這句話的紀錄，因為它說明了缺陷是可被讀出來的，只是沒有人回頭讀。
        """
        response = requests.get(url, headers=self.headers, cookies=self.cookies)
        response.raise_for_status()

        # 成功後加上隨機禮貌性延遲，模擬人類瀏覽
        time.sleep(random.uniform(1.0, 2.5))
        return response.text

    def scrape_ptt_stock_by_keyword(self, keyword: str, max_pages: int = 1) -> pd.DataFrame:
        """策略 A：基於目標關鍵字的推下過濾 (Pushdown Filtering) 爬蟲

        Failure Semantics（MULTI_SOURCE_DATA_CONTRACT.md §3.5）：
        - 單篇文章解析失敗（entry 缺欄位等）→ 跳過該篇，記錄 warning，繼續下一篇（SOURCE_DEGRADED）。
        - 整頁抓取失敗且此前已收集到資料 → 停止分頁，回傳已收集的部分資料 + log warning（SOURCE_DEGRADED）。
        - 整頁抓取失敗且尚無任何已收集資料（通常是第一頁就失敗）→ 視為來源完全不可達，
          拋出 PttSourceUnavailableError，不回傳空 DataFrame（SOURCE_FAILED）。
        """
        print(f"\n[Extract] 啟動爬蟲：搜尋 PTT 股板關鍵字 [{keyword}]，預計爬取 {max_pages} 頁...")

        search_url = f"{self.base_url}/bbs/Stock/search?q={keyword}"
        articles_data = []
        current_url = search_url

        for page in range(max_pages):
            print(f"[Extract] 正在抓取第 {page + 1} 頁: {current_url}")

            try:
                # 改用封裝好的 _fetch_page 取得 HTML（tenacity 已在此函式內重試 3 次）
                html_text = self._fetch_page(current_url)
            except Exception as e:
                if articles_data:
                    print(f"⚠️ [Extract] 第 {page + 1} 頁抓取失敗（已重試耗盡），保留先前已收集的 {len(articles_data)} 筆資料，停止分頁：{e}")
                    break
                print(f"❌ [Extract] 第一頁即抓取失敗（已重試耗盡），視為來源不可達：{e}")
                raise PttSourceUnavailableError(
                    f"PTT 來源不可達（關鍵字：{keyword}，URL：{current_url}）：{e}"
                ) from e

            soup = BeautifulSoup(html_text, "html.parser")
            entries = soup.find_all("div", class_="r-ent")

            for entry in entries:
                try:
                    title_tag = entry.find("div", class_="title").find("a")

                    if title_tag:
                        title = title_tag.text.strip()
                        link = self.base_url + title_tag["href"]
                        date = entry.find("div", class_="date").text.strip()
                        author = entry.find("div", class_="author").text.strip()

                        push_tag = entry.find("div", class_="nrec").text.strip()
                        push_count = push_tag if push_tag else "0"

                        articles_data.append({
                            "source": SOURCE_KEYWORD_SEARCH,
                            "fetch_keyword": keyword,
                            "date": date,
                            "title": title,
                            "push_count": push_count,
                            "author": author,
                            "url": link
                        })
                except Exception as e:
                    # 單篇文章解析失敗：跳過該篇，不影響其他文章（SOURCE_DEGRADED）
                    print(f"⚠️ [Extract] 單篇文章解析失敗，已跳過：{e}")
                    continue

            try:
                paging_div = soup.find("div", class_="btn-group btn-group-paging")
                prev_page_tag = paging_div.find_all("a")[1]

                if "href" in prev_page_tag.attrs:
                    current_url = self.base_url + prev_page_tag["href"]
                else:
                    print("[Extract] 已經沒有上一頁了。")
                    break
            except Exception as e:
                print(f"⚠️ [Extract] 分頁導覽解析失敗，停止分頁：{e}")
                break

        return pd.DataFrame(articles_data)

    def scrape_ptt_board_pages(self, keywords, since_timestamp=None,
                               page_budget=BOARD_PAGE_BUDGET):
        """策略 B：抓看板固定頁面，**在記憶體中**比對追蹤關鍵字。

        取代「逐關鍵字打 `/search?q=`」——後者的請求數隨關鍵字數線性成長，
        且每個關鍵字都對站方送出一次搜尋。本模式把 N 次搜尋換成
        「取回同一批看板頁面、在本地過濾」。

        Args:
            keywords: 追蹤關鍵字。比對的是**標題**，命中即收錄。
            since_timestamp: 回溯目標（unix 秒）。**頁面上最新一篇**的時間戳
                `<=` 此值即停止翻頁。`None` = 不設目標，只受 `page_budget` 約束。

                ⚠ **是「最新」不是「最舊」** —— PTT 的置底公告時間戳很舊，
                用「最舊」會被它一次擊沉（見迴圈內的註解與 V13）。
            page_budget: 本次執行的頁面請求上限。

        Returns:
            `(DataFrame, outcome)`，`outcome` 為
            `"OK"` / `"NO_DATA"` / `"SOURCE_DEGRADED"`。

        Failure Semantics（`MULTI_SOURCE_DATA_CONTRACT.md` §3.5、§7.2）:
            - **第一頁即失敗** → `PttSourceUnavailableError`（`SOURCE_FAILED`）。
              沿用 `scrape_ptt_stock_by_keyword` 的既有語意：
              **不得回傳空 DataFrame**（`CLAUDE.md` §7.1）。
            - 第二頁以後失敗 → 保留已收集資料、停止翻頁，`SOURCE_DEGRADED`。
            - **預算用盡而未回溯到 `since_timestamp`** → `SOURCE_DEGRADED`。
              **未達成目標就停下來，是部分成功，不是成功** ——
              記成 `OK` 會讓「少抓了幾天」變得看不見。
            - 頁面抓到了、只是一篇都沒命中 → `NO_DATA`。**那是有效觀測。**

            ⚠ `since_timestamp is None` 時，預算用盡回報 `OK` 而非 `SOURCE_DEGRADED`：
            **沒有目標時間，就沒有「少抓了」這回事** ——
            `SOURCE_DEGRADED` 需要一個沒被達成的目標。

        DEC-032:
            本方法**只透過 `self._fetch_page` 送出請求**，不另開 HTTP 入口。
            403／429 的硬停判別落在 `_fetch_page` 的 `@retry` 條件上；
            **繞過它，就等於把 `0047d98` 修好的東西悄悄退回去。**
            `tests/test_ptt_board_pages.py` 的 V9 釘住這一點。
        """
        keywords = [k for k in (keywords or []) if k]
        current_url = self.base_url + BOARD_INDEX_PATH
        rows = []
        seen = set()
        pages = 0
        outcome = "OK"

        print(f"\n[Extract] 看板頁面模式：{len(keywords)} 個關鍵字，"
              f"預算 {page_budget} 頁，回溯至 {since_timestamp}")

        while pages < page_budget:
            try:
                html_text = self._fetch_page(current_url)
            except Exception as e:
                if pages == 0:
                    print(f"[Extract] 第一頁即抓取失敗，視為來源不可達：{e}")
                    raise PttSourceUnavailableError(
                        f"PTT 看板不可達（URL：{current_url}）：{e}") from e
                print(f"[Extract] 第 {pages + 1} 頁抓取失敗，"
                      f"保留已收集的 {len(rows)} 筆，停止翻頁：{e}")
                outcome = "SOURCE_DEGRADED"
                break

            pages += 1
            soup = BeautifulSoup(html_text, "html.parser")

            # ⚠⚠ **取這一頁「最新」的一篇，不是「最舊」的**（E3 修正，2026-09-05）。
            #
            # 前一版取 `min(全頁時間戳)`，而 **PTT 的置底公告附在最新一頁上、
            # 時間戳很舊** —— 2026-09-05 的受控執行因此在第 1 頁就停下來
            # （`已回溯至 1768934799`＝2026-01-21，而那是最新的一頁），
            # **25 個關鍵字拿到 `NO_DATA`，宣稱「那天沒有討論」，
            # 實際上是我們只看了一頁**。
            #
            # **置底文的時間戳是「舊」的：它拉低 `min`，永遠不會拉高 `max`。**
            # 用 `max` 完全繞開它，**不必知道它在哪，也不必知道頁內怎麼排**
            # ——「取第一個 `r-ent`」那個版本則要先查證 PTT 的頁內排序。
            #
            # 語意也正確且保守：「這一頁**最新**的一篇都比目標舊」
            # ⟹ 這一頁與所有更舊的頁都在目標之前 ⟹ 可以停。
            # **它只可能多抓一頁，不可能少抓** —— 而少抓是危險的方向。
            page_newest = None
            for entry in soup.find_all("div", class_="r-ent"):
                try:
                    title_tag = entry.find("div", class_="title").find("a")
                    if not title_tag:
                        # 已刪除的文章沒有連結——**跳過，不計入時間戳**
                        continue
                    title = title_tag.text.strip()
                    link = self.base_url + title_tag["href"]

                    ts = _url_timestamp(link)
                    if ts is not None and (page_newest is None or ts > page_newest):
                        page_newest = ts

                    # ---- 記憶體比對：以標題命中追蹤關鍵字 ----
                    for kw in keywords:
                        if kw not in title:
                            continue
                        # **去重鍵是 `(url, 關鍵字)`，不是標題。**
                        # 標題相同不代表是同一篇（同名不同篇會被合掉）；
                        # 而同一篇命中兩個關鍵字**不是重複**，是兩筆
                        # (文章, 關鍵字) 觀測——逐關鍵字搜尋模式本來也會產生兩筆。
                        key = (link, kw)
                        if key in seen:
                            continue
                        seen.add(key)
                        rows.append({
                            "source": SOURCE_BOARD_PAGES,
                            "fetch_keyword": kw,
                            "date": entry.find("div", class_="date").text.strip(),
                            "title": title,
                            "push_count": entry.find(
                                "div", class_="nrec").text.strip() or "0",
                            "author": entry.find(
                                "div", class_="author").text.strip(),
                            "url": link,
                        })
                except Exception as e:
                    print(f"[Extract] 單篇解析失敗，已跳過：{e}")
                    continue

            # ---- 是否已回溯到目標時間 ----
            if (since_timestamp is not None and page_newest is not None
                    and page_newest <= since_timestamp):
                print(f"[Extract] 本頁最新一篇 {page_newest} <= {since_timestamp}，"
                      f"已回溯到目標時間，停止翻頁。")
                break

            # ---- 上一頁 ----
            try:
                paging_div = soup.find("div", class_="btn-group btn-group-paging")
                prev_tag = paging_div.find_all("a")[1]
                if "href" not in prev_tag.attrs:
                    print("[Extract] 已經沒有上一頁了。")
                    break
                current_url = self.base_url + prev_tag["href"]
            except Exception as e:
                print(f"[Extract] 分頁導覽解析失敗，停止翻頁：{e}")
                outcome = "SOURCE_DEGRADED"
                break
        else:
            # **`while...else` 只在條件為假時執行，`break` 不會進來** ——
            # 也就是「預算用盡」這一種離開方式，與其他離開方式在這裡被分開。
            if since_timestamp is not None:
                print(f"[Extract] {page_budget} 頁預算用盡，仍未回溯至 "
                      f"{since_timestamp} —— 部分成功。")
                outcome = "SOURCE_DEGRADED"

        if not rows and outcome == "OK":
            # **抓到了頁面、只是沒有命中——那是有效觀測，不是失敗。**
            outcome = "NO_DATA"

        print(f"[Extract] 看板頁面模式完成：{pages} 頁請求，{len(rows)} 筆命中，"
              f"outcome={outcome}")
        return pd.DataFrame(rows, columns=[
            "source", "fetch_keyword", "date", "title",
            "push_count", "author", "url"]), outcome

    def scrape_ptt_board_pages_capture_all(self, since_timestamp=None,
                                            page_budget=BOARD_PAGE_BUDGET,
                                            extra_page_delay=0):
        """§0.5 #40 段 B2：抓看板固定頁面，**無條件記錄全部標題**，不做關鍵字比對。

        與 `scrape_ptt_board_pages()` 並列的獨立方法——**不修改、不共用該方法
        本體一個字元**，只複製其翻頁／停止／例外分類骨架。用途是一次性量測
        PTT 情緒覆蓋率上限（`PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_
        PROPOSAL.md`），不接關鍵字追蹤，不是生產路徑。

        Args:
            since_timestamp: 回溯目標（unix 秒），語意與 `scrape_ptt_board_pages()`
                相同——本頁**最新**一篇 `<=` 此值即停止翻頁。
            page_budget: 本次執行的頁面請求上限。
            extra_page_delay: **PO 裁決（2026-09-21，段 B2 一次跑完、延遲加倍）**。
                預設 `0`：不額外等待，行為與既有節奏一致。非零時，每頁處理完
                後**另加**一段 `random.uniform(1.0, 2.5)` 秒等待，與 `_fetch_
                page()` 既有延遲的區間相同、獨立疊加，合計每頁延遲 2.0～5.0
                秒。**這個等待住在本方法，不是 `_fetch_page()`——DEC-032 規定
                後者是唯一請求出口且不得修改。**

        Returns:
            `(DataFrame, outcome)`，`outcome` 為 `"OK"` / `"NO_DATA"` /
            `"SOURCE_DEGRADED"`，語意與 `scrape_ptt_board_pages()` 相同。

        Failure Semantics：與 `scrape_ptt_board_pages()` 逐條相同（第一頁失敗
        → `PttSourceUnavailableError`；後續頁失敗 → 保留已收集資料、
        `SOURCE_DEGRADED`；預算用盡未達 `since_timestamp` → `SOURCE_
        DEGRADED`）。

        DEC-032：本方法**只透過 `self._fetch_page` 送出請求**，不另開 HTTP 入口。
        """
        current_url = self.base_url + BOARD_INDEX_PATH
        rows = []
        seen_urls = set()
        pages = 0
        outcome = "OK"

        print(f"\n[Extract] 看板全量捕捉模式：預算 {page_budget} 頁，"
              f"回溯至 {since_timestamp}，extra_page_delay={extra_page_delay}")

        while pages < page_budget:
            try:
                html_text = self._fetch_page(current_url)
            except Exception as e:
                if pages == 0:
                    print(f"[Extract] 第一頁即抓取失敗，視為來源不可達：{e}")
                    raise PttSourceUnavailableError(
                        f"PTT 看板不可達（URL：{current_url}）：{e}") from e
                print(f"[Extract] 第 {pages + 1} 頁抓取失敗，"
                      f"保留已收集的 {len(rows)} 筆，停止翻頁：{e}")
                outcome = "SOURCE_DEGRADED"
                break

            pages += 1
            soup = BeautifulSoup(html_text, "html.parser")

            # 停止判斷同 scrape_ptt_board_pages()：取本頁「最新」一篇，不是「最舊」。
            page_newest = None
            for entry in soup.find_all("div", class_="r-ent"):
                try:
                    title_tag = entry.find("div", class_="title").find("a")
                    if not title_tag:
                        # 已刪除的文章沒有連結——跳過，不計入時間戳
                        continue
                    title = title_tag.text.strip()
                    link = self.base_url + title_tag["href"]

                    ts = _url_timestamp(link)
                    if ts is not None and (page_newest is None or ts > page_newest):
                        page_newest = ts

                    # ---- 無條件記錄，不做關鍵字比對 ----
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)
                    rows.append({
                        "source": SOURCE_BOARD_PAGES,
                        "date": entry.find("div", class_="date").text.strip(),
                        "title": title,
                        "push_count": entry.find(
                            "div", class_="nrec").text.strip() or "0",
                        "author": entry.find(
                            "div", class_="author").text.strip(),
                        "url": link,
                        # 供量測腳本逐頁判定置底／離群值（同頁相對比較，
                        # 不是相對全體最新——見 measure_ptt_board_page_rate_
                        # probe.py 的 _exclude_pinned_outliers()）。
                        "page_index": pages - 1,
                    })
                except Exception as e:
                    print(f"[Extract] 單篇解析失敗，已跳過：{e}")
                    continue

            if extra_page_delay:
                time.sleep(random.uniform(1.0, 2.5))

            # ---- 是否已回溯到目標時間 ----
            if (since_timestamp is not None and page_newest is not None
                    and page_newest <= since_timestamp):
                print(f"[Extract] 本頁最新一篇 {page_newest} <= {since_timestamp}，"
                      f"已回溯到目標時間，停止翻頁。")
                break

            # ---- 上一頁 ----
            try:
                paging_div = soup.find("div", class_="btn-group btn-group-paging")
                prev_tag = paging_div.find_all("a")[1]
                if "href" not in prev_tag.attrs:
                    print("[Extract] 已經沒有上一頁了。")
                    break
                current_url = self.base_url + prev_tag["href"]
            except Exception as e:
                print(f"[Extract] 分頁導覽解析失敗，停止翻頁：{e}")
                outcome = "SOURCE_DEGRADED"
                break
        else:
            if since_timestamp is not None:
                print(f"[Extract] {page_budget} 頁預算用盡，仍未回溯至 "
                      f"{since_timestamp} —— 部分成功。")
                outcome = "SOURCE_DEGRADED"

        if not rows and outcome == "OK":
            outcome = "NO_DATA"

        print(f"[Extract] 看板全量捕捉模式完成：{pages} 頁請求，{len(rows)} 筆，"
              f"outcome={outcome}")
        return pd.DataFrame(rows, columns=[
            "source", "date", "title",
            "push_count", "author", "url", "page_index"]), outcome

    def parse_article_comments(self, article_url: str) -> dict:
        """進入 PTT 文章內頁，解析推/噓/→ 留言計數與完整發文時間戳記。

        MULTI_SOURCE_DATA_CONTRACT.md §3.3：
        - push-tag 含「推」→ push_count；含「噓」→ boo_count；含「→」→ neutral_count
        - total_comments = push_count + boo_count + neutral_count
        - engagement_metric（向後相容）= push_count - boo_count

        §3.6：優先使用內頁完整時間戳記（article-meta-value 的發文時間欄），
        解析失敗時回傳 full_datetime=None，呼叫端應 fallback 回列表頁 MM/DD。

        `PRE-G3-01`（2026-09-06）：**額外回傳 `comment_entries`** ——
        逐則的 `(seq, tag, raw_time)`。`raw_time` 是頁面原文（如 `08/15 16:49`，
        **沒有年份**），**年份推論由 `comment_timeline.infer_comment_times()` 負責**。

        > **彙總計數是逐則資料的函數，反之不成立。**
        > 只存彙總，任一 cutoff 下的重算就永遠做不到 —— 而 cutoff 是一個
        > 尚未定案的參數（`CLAUDE.md` §7.4 的 Prediction Time Convention 未定義）。

        單篇文章的內頁請求失敗（含重試耗盡）視為 SOURCE_DEGRADED，交由呼叫端決定是否
        跳過此篇——本方法本身不吞例外，讓呼叫端統一處理（與 scrape_ptt_stock_by_keyword
        的分工一致：本方法只負責解析單一篇文章，不負責決定「跳過 vs 中止整體爬取」）。
        """
        html_text = self._fetch_page(article_url)
        # 內頁請求與列表頁共用節流延遲；額外加一段更保守的延遲，降低短時間內大量內頁
        # 請求觸發 PTT 封鎖的機率（RISK-002，OBSERVED，PO 2026-08-27 核准）
        time.sleep(random.uniform(1.5, 3.5))

        soup = BeautifulSoup(html_text, "html.parser")

        push_count = 0
        boo_count = 0
        neutral_count = 0
        # `PRE-G3-01` 決策點 1：**逐則帶出 `(seq, tag, raw_time)`**。
        #
        # ⚠ **本方法只做 HTML 解析，不做年份推論** ——
        # 那是 `src/transform/comment_timeline.infer_comment_times()` 的事，
        # 它需要「文章發文年份」這個錨點，而那屬於 transform 層的知識。
        # **分開的好處是年份推論可以完全離線測試，不需要任何 HTML。**
        comment_entries = []

        for push_div in soup.find_all("div", class_="push"):
            tag_el = push_div.find("span", class_="push-tag")
            if not tag_el:
                continue
            tag_text = tag_el.text.strip()
            if "推" in tag_text:
                push_count += 1
            elif "噓" in tag_text:
                boo_count += 1
            elif "→" in tag_text:
                neutral_count += 1
            else:
                # 不認得的 tag **不計數也不收錄** —— 維持 W4 的相等關係。
                continue

            # 逐則時間戳。實測（2026-09-06，`article_id=169`，281 則）
            # 承載它的是 `span.push-ipdatetime`，格式 `08/15 16:49`
            # —— **沒有年份**，故 `raw_time` 原樣帶出，不在此處解讀。
            dt_el = push_div.find("span", class_="push-ipdatetime")
            comment_entries.append({
                "seq": len(comment_entries) + 1,
                "tag": tag_text,
                "raw_time": dt_el.text.strip() if dt_el else "",
            })

        total_comments = push_count + boo_count + neutral_count
        engagement_metric = push_count - boo_count

        full_datetime = None
        for meta in soup.find_all("span", class_="article-meta-tag"):
            if meta.text.strip() == "時間":
                value_el = meta.find_next_sibling("span", class_="article-meta-value")
                if value_el:
                    full_datetime = value_el.text.strip()
                break

        return {
            "push_count": push_count,
            "boo_count": boo_count,
            "neutral_count": neutral_count,
            "total_comments": total_comments,
            "engagement_metric": engagement_metric,
            "full_datetime": full_datetime,
            # `PRE-G3-01`：逐則原始資料。**彙總計數是它的函數，反之不成立** ——
            # 只回傳彙總，任一 cutoff 下的重算就永遠做不到
            # （`comment_timeline.counts_as_of()`，測試 W5）。
            "comment_entries": comment_entries,
        }
