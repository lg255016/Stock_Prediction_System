# main_etl_pipeline.py
import time
from datetime import datetime

# 時區政策：本專案「現在」的唯一入口（容器是 UTC，業務基準是台北時間）。
# 見 `src/common/clock.py`，由 `tests/test_timezone_policy.py` 的 AST 掃描強制。
from src.common.clock import now_taipei, to_taipei, today_taipei

# ====== 匯入收集層 (Extractors) ======
# UG-G2-SB7：每日增量改走全市場報表（1 個請求／市場）。
# UG-G3-SB2a 方案 B：TWSE／TPEX 逐股路徑統一為複製 candidate_prices，
# 舊版逐股爬蟲（`TwseScraper`）自本 SB 起不再被本檔使用或匯入——
# 模組本身（`src/extractors/twse_scraper.py`）保留供未來單檔歷史回補腳本
# 直接匯入，去留由 PO 另案決定。
from src.extractors.market_report_fetcher import (
    SOURCE_BY_MARKET, FetchFailedError, ServiceRefusedError, fetch_market_report,
    previous_business_day,
    # 首次每日 ETL 缺口自動追補（FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md）：
    BackfillWindowExceededError, MissingBackfillOriginError,
    compute_gap_backfill_dates,
)
from src.extractors.yfinance_api import YFinanceAPI
from src.extractors.ptt_scraper import PttScraper, PttSourceUnavailableError
from src.extractors.trend_discover import TrendDiscover

# ====== 匯入轉換層 (Transform) ======
from src.transform.comment_timeline import (
    infer_comment_times, validate_comment_bounds,
)
from src.transform.data_cleaner import DataCleaner
from src.transform.nlp_processor import NLPProcessor, GeminiDailyQuotaExhausted
from src.transform.feature_aggregator import FeatureAggregator
from src.ml.triple_barrier import recompute_tail_labels

# ====== 匯入載入層 (Loaders) ======
from src.loaders.db_writer import DBWriter 
from src.loaders.etl_run_log import (
    FETCH_FAILED, NO_DATA, OK, REFUSED, EtlRunLogWriter, RunLogEntry,
    assert_complete, format_summary, summarize,
)


# UG-G2-SB7：逐股追蹤標的的每日取價，其 run log 來源標記。
# **與 `candidate_prices` 的兩個來源分開** —— 它們寫不同的表、服務不同的對象。
SOURCE_TRACKED_DAILY = "tracked_stocks_daily"
# UG-G2-SB7 A 輪：PTT 取數的 run log 來源標記。
SOURCE_PTT = "ptt"
# §0.5 #31：AI 熱門詞探索／NLP 每日配額耗盡的 run log 來源標記。
SOURCE_AI_DISCOVERY = "ai_discovery"
SOURCE_NLP_GEMINI = "nlp_gemini"

# §0.5 #31：探索頻率上限——距上次「有問過」（OK／NO_DATA）不足這個天數就跳過
# （規則性跳過不寫列，A4 裁決）。`ENGINEERING JUDGMENT`：與免費層每日配額週期
# 對齊的保守值，非從觀測推導的最適門檻。
DISCOVERY_INTERVAL_DAYS = 7

# 看板頁面模式的回溯天數（UG-G2-SB7 第 5 項）。
#
# `ENGINEERING JUDGMENT`：每日任務**每天**跑，1 天即足夠；取 2 天是
# **為「昨天那一次沒跑成」留一天重疊**。不是從觀測推導的門檻。
#
# ⚠ 它**不是**請求量的上限 —— 上限是 `BOARD_PAGE_BUDGET`。
# 看板動得太快而 2 天回溯不完時，結果是 `SOURCE_DEGRADED`，**不是靜默截斷**。
BOARD_LOOKBACK_DAYS = 2

# Triple-Barrier 持有期窗口（業務常數，DEC-040／DEC-041 相關）——
# `run_triple_barrier_tail_recompute()` 的預設值與缺口自動追補案呼叫端的
# `tail_window` 計算都引用這一個常數，不各自硬寫字面 `5`（審查方段 B 複核要求，
# 2026-09-16）：哪天有人改動這個業務常數，兩處會一起變，不會有一處被漏改而
# 靜默少算尾端重算視窗。
TRIPLE_BARRIER_HOLDING_PERIOD = 5


def _anchor_from_url(url):
    """由 PTT 網址內嵌的 unix 時間戳取發文時間（台北 naive）。

    **刻意不讀 DB 的 `market_articles.post_time`** ——
    舊批 331 列中 **76 列的年份是錯的**（`MULTI_SOURCE_DATA_CONTRACT.md` §3.6A），
    **拿它當錨點會讓整篇的逐則時間軸整體位移**。
    網址時間戳是 §3.6A 指定的權威來源。

    取不到（網址不是 `M.<unix>.A.<n>` 形態）→ 回傳 `None`，
    該篇**不做逐則時間軸**：**沒有錨點就不推論，不猜一個。**
    """
    import re as _re
    m = _re.search(r"/M\.(\d+)\.A\.", url or "")
    return to_taipei(int(m.group(1))) if m else None


class ETLPipelineManager:
    def __init__(self):
        """
        總指揮官初始化：實例化各個處理模組，統一管理資源。
        """
        self.yf_api = YFinanceAPI()
        self.ptt_scraper = PttScraper()
        self.trend_discover = TrendDiscover()

        self.cleaner = DataCleaner()
        self.nlp_processor = NLPProcessor()
        self.feature_aggregator = FeatureAggregator()

        self.db_writer = DBWriter()

    # ==================================================================
    # UG-G2-SB7：每日增量的批次取價
    # ==================================================================
    def run_price_batch(self, trade_date, markets=("twse", "tpex"),
                        throttle=True, run_log_writer=None):
        """一個交易日、全部市場的批次取價。**每個市場一個邏輯請求。**

        Args:
            trade_date: `datetime.date`。
            markets: 本批的市場清單——**這就是「項目」的定義**。
            throttle: 取數後是否延遲（測試關閉）。
            run_log_writer: `EtlRunLogWriter`；`None` 時只在記憶體中彙總。

        Returns:
            各態計數，另含 `outcomes_by_item`：`{市場: outcome}`。

            ⚠ **`outcomes_by_item` 是 (iii) 需要的** —— 逐股迴圈要能分辨
            「上櫃標的今天在 `candidate_prices` 裡沒有列」是因為
            **本日批次失敗**（`FETCH_FAILED`）還是**該股真的沒有交易**
            （`NO_DATA`）。**兩者在「沒有列」上長得一樣**，而處置相反。

        Raises:
            ServiceRefusedError: 403／429 —— **停止並請示，不自行續行**（DEC-032）。
            IncompleteBatchError: 記錄數與項目數不符——有項目被靜默略過。
        """
        # 稽核紀錄的時間基準必須是台北時間 —— 容器是 UTC。
        started_at = now_taipei()
        batch_key = trade_date.isoformat()

        # ⚠⚠ **item_count 取自迴圈開始前就固定的清單**（複查方 2026-09-04 條件 1）。
        # **不得由記錄反推**（例如 `len(entries)` 或迴圈跑完才算）——
        # 那樣它會恆等，而且看起來完全正常，
        # `assert_complete()` 就成了一個結構上無法失敗的檢查（§9A.1）。
        items = tuple(markets)
        item_count = len(items)

        entries = []
        refusals = []
        for market in items:
            source = SOURCE_BY_MARKET[market]
            try:
                result = fetch_market_report(market, trade_date, throttle=throttle)
            except ServiceRefusedError as exc:
                # **「該停手」停的是「繼續打那個拒絕我們的服務」，不是「整批中止」**
                # （複查方 2026-09-04 裁決）。
                #
                # TWSE 的 429 是我們與 TWSE 那台主機的關係，**對 TPEx 那台主機什麼都沒說**。
                # 因一邊拒絕而放棄另一邊，當天兩個市場都沒有資料 ——
                # **那是一個資料缺口，換來的不是任何安全。**
                #
                # 故：記為 `REFUSED`（**不是 `FETCH_FAILED`** —— 兩者處置相反，
                # 詞彙必須跟例外型別一樣分得開），繼續其餘市場，
                # 最後在寫完 run log **之後**才 raise。
                refusals.append(exc)
                entries.append(RunLogEntry(
                    source, batch_key, market, REFUSED, detail=str(exc)[:500]))
                print("  [%s] %s REFUSED：%s" % (batch_key, market, exc))
                continue
            except FetchFailedError as exc:
                entries.append(RunLogEntry(
                    source, batch_key, market, FETCH_FAILED,
                    detail=str(exc)[:500]))
                print("  [%s] %s FETCH_FAILED：%s" % (batch_key, market, exc))
                continue

            entries.append(RunLogEntry(
                source, batch_key, market, result.outcome,
                http_attempts=result.http_attempts))
            if result.records:
                self.db_writer.upsert_to_candidate_prices(result.records)
            print("  [%s] %s %s｜列數 %d｜HTTP 嘗試 %d"
                  % (batch_key, market, result.outcome,
                     len(result.records), result.http_attempts))

        # ⚠ **run log 必須在任何 raise 之前寫。**
        # 迴圈內已經執行過 `upsert_to_candidate_prices()` ——
        # 若在寫 log 之前離開，**side effect 留下了、稽核紀錄沒有**，
        # 而那與 §0.3 要修的病是同一個，只是換了形狀：
        # 那邊是「失敗被吞掉、沒進任何資料」，這裡是「成功被寫進去、也沒進任何資料」。
        # **共同點是事後無法回答「那天到底跑了什麼」。**（複查方 2026-09-04）
        counts = assert_complete(entries, item_count)
        counts["outcomes_by_item"] = dict(
            (e.item_key, e.outcome) for e in entries)
        if run_log_writer is not None:
            run_log_writer.write(entries, started_at)

        # ⚠⚠ **這裡刻意用 `summarize()` 而不是 `assert_complete()`。**
        # 本段只是印摘要，而分母若從同一份 `entries` 數出來，
        # `assert_complete(X, len(X))` **永遠通過** ——
        # 那正是該函式自己 docstring 裡的警告。
        # **2026-09-04 本段確實那樣寫過一次，離上面那個正確的呼叫只有三行。**
        # 用一個檢查函式做格式化，會誘使呼叫端把分母寫成長度。
        for source in sorted({e.source for e in entries}):
            print(format_summary(
                source, batch_key,
                summarize([e for e in entries if e.source == source])))

        if refusals:
            # 寫完 log 之後才 raise：讓本次執行以非零結束、操作者被通知，
            # **但稽核紀錄已經落地**。
            #
            # ⚠ **把 `outcomes_by_item` 帶過去**（2026-09-04 修正）：
            # 先前這裡直接 `raise refusals[0]`，於是上面算好的逐項 outcome
            # **隨著 return 被跳過而整個丟掉**，下游只能把上櫃標的記成
            # `FETCH_FAILED` —— 而那對 (iii) 之後的路徑是**雙重誤述**：
            # 它根本不 fetch，且失敗原因是上游被拒。
            refusals[0].outcomes_by_item = counts["outcomes_by_item"]
            raise refusals[0]
        return counts

    def _run_log_writer(self):
        """建立 run log 寫入端；**失敗時回 None 而不是讓整個 ETL 掛掉**。

        ⚠ **但那個失敗必須被看見** —— 若 `etl_run_log` 不可用，
        本次執行的稽核紀錄會缺席，**而那件事本身要印出來**，
        否則「沒有紀錄」與「跑得很順」在輸出上一樣。
        """
        try:
            return EtlRunLogWriter()
        except Exception as exc:      # noqa: BLE001
            print("[WARNING] 無法建立 etl_run_log 寫入端，"
                  "**本次執行不會留下稽核紀錄**：%s" % exc)
            return None

    def format_provider_symbol(self, stock_id: str, market: str) -> str:
        """格式化 Provider Symbol"""
        return self.cleaner.format_provider_symbol(stock_id, market)

    # ==================================================================
    # UG-G2-SB7 (iii) → UG-G3-SB2a 方案 B：逐股標的的 stock_prices
    # 改由 candidate_prices 供應（TWSE／TPEX 共用同一份實作）
    # ==================================================================
    # **為什麼**：舊版逐股路徑曾先試 TWSE 的 `STOCK_DAY`、抓不到才落 yfinance
    # 備援，而 `STOCK_DAY` 不供應上櫃 —— 所以上櫃標的每一次都走 yfinance
    # （提案 §0.1a，並由真實庫資料證實：6488 的區間跨月，`STOCK_DAY` 結構上給不出）。
    # `UG-G3-SB2a` 方案 B 進一步發現：即使是上市標的，舊路徑的 yfinance 備援
    # 也是**還原價**，與 `candidate_prices`／原始交易所價基準不同——
    # 同一支股票的時間序列裡混入不同基準，檔數一多，問題規模線性放大。
    #
    # 批次階段（`UG-G2-SB7`）已經把全市場（上市＋上櫃）寫進 `candidate_prices`，
    # **同一份資料沒有理由再抓第二次**，而且逐股再抓的是一個**拿不到
    # `status_code`、無法套用 DEC-032 判別依據**的來源。
    #
    # ⚠ **這不會讓 yfinance 的 DEC-032 問題消失，只會把它縮到 NVDA 一條路徑**
    #   （美股逐股路徑 `run_us_stock_pipeline`，不在本方案範圍）。
    SELECT_CANDIDATE_FOR_STOCK_PRICES = """
    SELECT stock_id, trade_date, open_price, high_price, low_price,
           close_price, volume, source
    FROM candidate_prices
    WHERE stock_id = %s AND trade_date = %s;
    """

    def run_tpex_pipeline_from_candidate_prices(self, stock_id, trade_date,
                                                batch_outcome=None):
        """把 `candidate_prices` 的當日列複製到 `stock_prices`。

        **TWSE／TPEX 共用同一份實作**（`UG-G3-SB2a` 方案 B）——SQL 只認
        `stock_id`／`trade_date`，不分市場，故無需為 TWSE 另寫一份。
        `run_twse_pipeline_from_candidate_prices` 是本方法的別名，
        兩個名字綁同一個函式物件（見本方法定義之後的別名指派）。

        Args:
            stock_id: 標的代號（上市或上櫃）。
            trade_date: `datetime.date`，即本日批次的 `batch_key`。
            batch_outcome: 本日**該市場批次**的 outcome（`OK`／`NO_DATA`／
                `FETCH_FAILED`／`REFUSED`）。**沒有列時用它歸因。**

        Returns:
            `OK`／`NO_DATA`

        Raises:
            RuntimeError: 沒有列**且**本日批次未成功 —— 呼叫端記為 `FETCH_FAILED`。

        ⚠ **欄位對映刻意只取 `stock_prices` 已有的七欄**
        （`stock_id`／`trade_date`／OHLC／`volume`）。
        **`candidate_prices` 的 `turnover_amount` 不帶過去** ——
        `stock_prices` 沒有那一欄，而決策點 2 的邊界是「不擴充 `stock_prices` 的 schema」。
        順手加欄位會讓 RISK-022 面向一（該表無 `source` 欄、權值基準不可知）
        的處置範圍在無人裁決的情況下變大。
        """
        print("\n========== 逐股標的由 candidate_prices 供應 [%s %s] =========="
              % (stock_id, trade_date))
        df = self.db_writer.fetch_data(
            self.SELECT_CANDIDATE_FOR_STOCK_PRICES, (stock_id, trade_date))
        if df is None or df.empty:
            if batch_outcome != OK:
                # **不得靜默略過**（複查方 2026-09-04 要求 2）：
                # 「批次失敗所以沒有列」與「該股今天真的沒交易」在
                # 「沒有列」上長得一樣，**而 §7.1 要求兩者可區分**。
                exc = RuntimeError(
                    "candidate_prices 無 %s@%s 的列，且本日批次 outcome=%s"
                    " —— **這是上游取數未成功的後果，不是「那天沒有資料」**"
                    % (stock_id, trade_date, batch_outcome))
                # **把上游的 outcome 帶給呼叫端** —— 被拒與抓失敗的處置不同，
                # 而呼叫端只看得到這個例外。
                exc.upstream_outcome = (
                    REFUSED if batch_outcome == REFUSED else FETCH_FAILED)
                raise exc
            print("  [%s] %s 本日無列，而批次為 OK —— 視為 NO_DATA（該股當日未出現於報表）"
                  % (trade_date, stock_id))
            return NO_DATA
        # ⚠ `source` **帶 candidate_prices 那一列的原值過來，不是寫 'candidate_prices'**：
        # RISK-022 要分辨的是調整基準，而基準由**原始報表**決定，不由中繼表決定。
        # 寫中繼表的名字等於把血緣停在中繼站。SELECT 已含該欄。
        self.db_writer.upsert_to_stock_prices(df)
        return OK

    # `UG-G3-SB2a` 方案 B：TWSE 逐股路徑改走同一份實作（一份實作、兩個名字）。
    # 舊版逐股爬蟲＋yfinance 路徑已刪除，不再有獨立的 TWSE 專屬函式。
    run_twse_pipeline_from_candidate_prices = run_tpex_pipeline_from_candidate_prices

    def run_us_stock_pipeline(self, stock_id: str, period: str = "1mo"):
        """執行美股 ETL"""
        print(f"\n========== 開始執行美股 ETL 管線 [{stock_id}] ==========")
        yf_symbol = self.format_provider_symbol(stock_id, "US")
        raw_df = self.yf_api.fetch_yfinance_data(yf_symbol, period)
        if raw_df is not None and not raw_df.empty:
            clean_df = self.cleaner.clean_yfinance_stock_data(raw_df, stock_id)
            # 美股唯一路徑：yfinance，auto_adjust=True（還原價）。
            clean_df["source"] = "yfinance_auto_adjusted"
            self.db_writer.upsert_to_stock_prices(clean_df)

    def run_ptt_board_pipeline(self, keywords, since_timestamp=None):
        """看板固定頁面模式的每日取數（UG-G2-SB7 第 5 項）。

        **一次取回同一批看板頁面，在記憶體中比對全部關鍵字** ——
        取代「每個關鍵字各打一次 `/search?q=`」。

        Returns:
            `{keyword: (outcome, detail)}`，outcome 為
            `OK`／`NO_DATA`／`FETCH_FAILED`；`detail` 在非失敗時為 `None`。

            **detail 一起回傳，不由呼叫端重建** —— `RunLogEntry` 要求
            `FETCH_FAILED` 必須附可觀測的 detail（`etl_run_log.py:74`），
            而「為什麼失敗」只有這一層知道。

        ================================================================
        逐關鍵字 outcome 的判定，與批次 outcome 的關係
        ================================================================
        | 批次 outcome | 有命中的關鍵字 | **沒命中的關鍵字** |
        |--------------|---------------|-------------------|
        | `OK`／`NO_DATA` | `OK` | `NO_DATA` |
        | `SOURCE_DEGRADED` | `OK` | **`FETCH_FAILED`** |

        > **降級批次下的「沒命中」不是 `NO_DATA`。**
        > 我們沒有回溯到目標時間，因此**分不出「這個關鍵字這幾天沒人討論」
        > 與「有人討論，但在我們沒抓到的那幾頁裡」** ——
        > 記成 `NO_DATA` 就是 `CLAUDE.md` §7.1 禁止的
        > 「把失敗偽裝成沒有資料」，只是換了一個粒度。

        第一頁即失敗（`PttSourceUnavailableError`）由呼叫端捕捉，
        **全部關鍵字記 `FETCH_FAILED`** —— 那一次我們對每個關鍵字都一無所知。
        """
        raw_df, batch_outcome = self.ptt_scraper.scrape_ptt_board_pages(
            keywords, since_timestamp=since_timestamp)

        if raw_df is not None and not raw_df.empty:
            clean_df = self.cleaner.clean_ptt_data(raw_df)
            self.db_writer.upsert_to_market_articles(clean_df)
            self.backfill_ptt_comment_counts(clean_df["url"].tolist())
            hit = set(raw_df["fetch_keyword"].astype(str))
        else:
            hit = set()

        if batch_outcome == "SOURCE_DEGRADED":
            miss = (FETCH_FAILED,
                    "看板批次 outcome=SOURCE_DEGRADED（未回溯到目標時間），"
                    "本關鍵字在已抓取的頁面中無命中——"
                    "**無法判定是沒人討論還是在未抓取的頁面裡**")
        else:
            miss = (NO_DATA, None)
        return {kw: ((OK, None) if kw in hit else miss) for kw in keywords}

    def run_ptt_pipeline(self, keyword: str, max_pages: int = 1):
        """執行 PTT 輿情 ETL

        MULTI_SOURCE_DATA_CONTRACT.md §3.5 明文要求：「下游 pipeline 應捕獲此例外後
        記錄並跳過該來源」——PttSourceUnavailableError 在此捕捉並記錄，不中斷其餘
        關鍵字的 PTT 爬取，也不中斷 daily pipeline 後續的 NLP／特徵工程步驟
        （UG-G2-SB2，PO 2026-08-27 核准：契約必要項，非範圍擴充）。
        """
        print(f"\n========== 開始執行 PTT ETL 管線 [關鍵字: {keyword}] ==========")
        # ⚠⚠ **例外不再被吞掉**（UG-G2-SB7 A 輪，2026-09-04）。
        #
        # 先前是：
        #     except PttSourceUnavailableError as e:
        #         print(f"[WARNING] PTT 來源不可達，跳過關鍵字 [{keyword}]：{e}")
        #         return
        #
        # **失敗只被 print，沒有進入任何資料** —— 而禁令**就寫在被 catch 的
        # 那個類別上**（`ptt_scraper.py:12-13`）：
        #   「此例外必須被拋出，**呼叫端不得將其誤判為『查無資料』**」。
        # `UG-G2-SB2` 把 extractor 端做對了，**而 pipeline 在兩個檔案之外
        # 做了它明文禁止的事。**
        #
        # 契約 §3.5 要求呼叫端「**捕獲此例外後記錄並跳過該來源**」——
        # **「記錄」是持久化，不是 print**。捕獲與記錄改到
        # `run_all_daily_tasks` 的關鍵字迴圈（與逐股迴圈同一形狀），
        # 讓本函式的例外真的傳播出去。
        #
        # **那個傳播是 B 輪讓 `SOURCE_FAILED` 可達的前提**：
        # `feature_aggregator.py:451` 的註解逐字寫著該態
        # 「需 UG-G2-SB2 的 pipeline 例外傳播才可能產生」。
        raw_df = self.ptt_scraper.scrape_ptt_stock_by_keyword(keyword, max_pages)
        if raw_df is not None and not raw_df.empty:
            clean_df = self.cleaner.clean_ptt_data(raw_df)
            self.db_writer.upsert_to_market_articles(clean_df)
            self.backfill_ptt_comment_counts(clean_df["url"].tolist())
            return OK
        # **查詢成功但沒有文章** —— 那是有效觀測（`SUCCESS_EMPTY` 的來源），
        # **與「來源不可達」不是同一件事**。
        return NO_DATA

    def backfill_ptt_comment_counts(self, urls: list):
        """回填 PTT 內頁留言計數（UG-G2-SB4 接線）。

        MULTI_SOURCE_DATA_CONTRACT.md §2.3：走獨立 UPDATE 路徑，不與初次 upsert 混合。
        DEC-024：write-once——只回填 total_comments 仍為 NULL 的文章。

        兩層請求量控制（UG-G2-SB4 決策點 4，PO 2026-08-28）：
        (a) URL 去重——同一篇文章會出現在多個關鍵字的搜尋結果裡（「台積電」與「AI」
            可能撈到同一篇），不去重會對同一頁重複發出內頁請求。
        (b) 跳過已有計數者——穩定期每天只需抓新文章，請求量因此大幅下降。
            （反正寫回去也會被 write-once 的 AND total_comments IS NULL 擋掉。）

        單篇內頁請求失敗視為 SOURCE_DEGRADED（決策點 3）：該篇留言計數保持 NULL、
        文章本身已寫入不受影響，繼續處理其餘文章，不中斷整批。
        """
        if not urls:
            return

        unique_urls = list(dict.fromkeys(u for u in urls if u))  # (a) 去重，保留原順序
        pending = self.db_writer.fetch_articles_missing_comment_counts(unique_urls)  # (b)
        skipped = len(unique_urls) - len(pending)
        if skipped:
            print(f"[Extract] 留言計數已存在，跳過 {skipped} 篇（write-once，DEC-024）。")
        if not pending:
            return

        print(f"[Extract] 準備解析 {len(pending)} 篇文章內頁留言...")
        records, degraded = [], 0
        comment_rows = []
        # `PRE-G3-01`：邊界違反的紀錄。**必須可觀測** ——
        # 靜默丟棄與「那篇沒有留言」在輸出上長得一樣。
        self.last_comment_bound_violations = []
        for url in unique_urls:
            if url not in pending:
                continue
            try:
                counts = self.ptt_scraper.parse_article_comments(url)
            except Exception as e:
                # SOURCE_DEGRADED：該篇留言計數保持 NULL，不影響其他文章
                degraded += 1
                print(f"[WARNING] 內頁留言解析失敗，該篇留言計數保持 NULL：{url}：{e}")
                continue

            # ==============================================================
            # `PRE-G3-01`：逐則時間軸 + 閉區間夾擠
            # ==============================================================
            # 錨點取**網址內嵌的 unix 時間戳**（§3.6A 的權威來源）——
            # **不用 DB 裡的 `post_time`**：舊批 331 列中 76 列的年份是錯的，
            # 拿它當錨點會讓整篇整體位移。
            scraped_at = now_taipei()
            # `parse_ptt_post_time(url, None)`：網址有時間戳就用它（§3.6A），
            # 取不到則回退 —— 而回退需要一個 `date_str`，這裡沒有，
            # 故取不到時 anchor 為 None，該篇**不做逐則時間軸**（見下）。
            anchor = _anchor_from_url(url)
            entries = counts.get("comment_entries") or []
            resolved = infer_comment_times(anchor, entries) if anchor else []
            bad = validate_comment_bounds(resolved, anchor, scraped_at) if anchor else []

            if bad:
                # ⚠ **拒寫整篇，不是丟掉違反的那幾則。**
                # `infer_comment_times` 的 `year` 跨迭代累積 ——
                # **一則異常污染的是整條尾巴**，
                # 丟掉那幾則丟掉的是症狀、留下的是原因：
                # 剩下的列看起來乾淨，而它們的年份是同一個錯誤推論鏈算出來的。
                #
                # ⚠ **也不截斷成上界** —— 那會把「不知道它是什麼時候」
                # 變成一個看起來精確的值。
                degraded += 1
                for b in bad:
                    self.last_comment_bound_violations.append(dict(b, url=url))
                print(f"[WARNING] 留言時間軸邊界違反 {len(bad)} 則，"
                      f"**整篇拒寫**（留言計數與逐則皆不寫入）：{url}")
                continue

            comment_rows.extend(
                (url, r["seq"], r["tag"], r["comment_time"], r["year_inferred"])
                for r in resolved)

            records.append((
                counts["push_count"], counts["boo_count"], counts["neutral_count"],
                # ⚠ `comments_scraped_at` **會被 DEC-024 的時點有效性判準拿去比較**
                # （`feature_aggregator`：`<= trade_date + 15:30`，台北收盤）。
                # 用 UTC 會讓它早 8 小時 → **比應該的更容易通過那個過濾**，
                # 而那條過濾存在的唯一理由就是防前視（§7.4）。
                counts["total_comments"], now_taipei(), url,
            ))

        if degraded:
            print(f"[WARNING] 共 {degraded} 篇內頁解析失敗或邊界違反（SOURCE_DEGRADED），"
                  f"其留言計數維持 NULL。")
        if self.last_comment_bound_violations:
            print(f"[WARNING] 邊界違反共 {len(self.last_comment_bound_violations)} 則 —— "
                  f"前三筆：{self.last_comment_bound_violations[:3]}")
        # **兩者同進退**：被拒的那篇既不在 records 也不在 comment_rows。
        self.db_writer.update_comment_counts(records)
        self.db_writer.upsert_article_comments(comment_rows)

    def run_nlp_sentiment_pipeline(self, batch_size: int = 500, run_log_writer=None,
                                    started_at=None, batch_key=None):
        """
        執行 Phase 2: NLP 情緒分數計算 
        (💡 具備 Batch Checkpointing 斷點續傳機制)

        §0.5 #31：`run_log_writer`／`started_at`／`batch_key` 三個參數皆預設
        `None`，只在真正撞到每日配額耗盡時才驗證是否齊備——既有測試檔呼叫端
        不必先改（見 GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.2）。
        `batch_key` 由呼叫端傳入（生產路徑傳 `run_all_daily_tasks()` 既有的
        `tracked_batch_key`），不在本方法內自行用 `started_at` 反推——時間衍生值
        只能有一個計算點（同 §0.5 #32 起算點的教訓）。
        """
        print(f"\n========== 開始執行 NLP 情緒運算管線 (Batch Checkpointing 模式) ==========")
        total_processed = 0
        
        while True:
            # 1. 撈取斷點：只抓取 sentiment_score 是 NULL 的資料
            query = f"""
                SELECT article_id, title 
                FROM market_articles 
                WHERE sentiment_score IS NULL 
                LIMIT {batch_size};
            """
            
            df_raw = self.db_writer.fetch_data(query) 
            
            # 2. 中止條件：如果回傳的資料為空，代表所有文章都已經算完，跳出迴圈
            if df_raw is None or df_raw.empty:
                print(f"🎉 所有文章情緒分數計算完畢！本次總共處理了 {total_processed} 筆資料。")
                break
                
            print(f"⏳ 撈取 {len(df_raw)} 筆待處理資料，啟動 Hybrid 管線...")
            
            # 【關鍵修改】：呼叫新的混合方法，並傳入 db_writer 作為快取連線工具
            try:
                df_processed = self.nlp_processor.process_batch_hybrid(df_raw, self.db_writer)
            except GeminiDailyQuotaExhausted as exc:
                if run_log_writer is None or started_at is None or batch_key is None:
                    # 生產路徑一定會傳這三項；缺任一項代表接線沒做完——
                    # 靜默不落地比拋錯更危險（配額耗盡會被誤讀成「今天沒新文章」）。
                    raise ValueError(
                        "run_nlp_sentiment_pipeline() 撞到每日配額耗盡，但呼叫端未傳 "
                        "run_log_writer／started_at／batch_key，無法落地稽核紀錄——"
                        "生產路徑必須完整傳入這三項。"
                    ) from exc
                remaining = self.db_writer.fetch_data(
                    "SELECT COUNT(*) AS n FROM market_articles WHERE sentiment_score IS NULL;"
                )
                n_remaining = int(remaining.iloc[0]["n"]) if remaining is not None and not remaining.empty else -1
                run_log_writer.write(
                    [RunLogEntry(SOURCE_NLP_GEMINI, batch_key, "daily_quota", REFUSED,
                                 detail=f"剩餘 {n_remaining} 篇未評分，每日配額耗盡：{exc}"[:500])],
                    started_at)
                print(f"[WARNING] NLP 每日配額耗盡，本次停止，剩餘 {n_remaining} 篇留待下次：{exc}")
                return
            
            # 4. 批次寫回資料庫 (Checkpoint 推進)
            # 一旦更新成功，這些文章的分數就不再是 NULL，下次迴圈不會再撈到
            self.db_writer.update_sentiment_scores(df_processed)
            
            total_processed += len(df_processed)
            print(f"✅ 本批次完成，累積已處理 {total_processed} 筆。繼續下一批...")

    def run_feature_engineering_pipeline(self):
        print("\n========== 啟動 ML 特徵工程管線 ==========")
        # 1. 從資料庫撈出股價、文章、個股映射與題材映射表
        res = self.db_writer.fetch_all_for_features()
        if len(res) == 5:
            df_prices, df_articles, df_mapping, df_theme_mapping, df_comments = res
        elif len(res) == 4:
            df_prices, df_articles, df_mapping, df_theme_mapping = res
            df_comments = None
        else:
            df_prices, df_articles, df_mapping = res[:3]
            df_theme_mapping = None
            df_comments = None

        # §0.5 #32 成因 F 接線：PTT 覆蓋缺口／NLP 未完成的 (股票, 日期) 集合，
        # 每次都從資料庫重新推導（不是本次執行記憶體裡的 outcome）——daily_ml_features
        # 每次全歷史重算，只用本次 outcome 會把先前標記的 SOURCE_FAILED 洗回
        # SUCCESS_EMPTY（見 Gate A 提案 §3.1）。必須排在 NLP 階段（run_nlp_sentiment_
        # pipeline()）之後——否則本次剛評完分的文章仍會被算成未完成；本方法本身就是
        # run_feature_engineering_pipeline() 的一部分，而後者在 run_all_daily_tasks()
        # 裡已排在 NLP 之後（見「3. 執行NLP情緒運算管線」到「4. 執行特徵工程管線」的
        # 既有順序），滿足這個時機要求。
        failed_source_keys = self.db_writer.fetch_failed_source_keys()

        # 2. 進行特徵聚合與時間序列運算 (支援題材情緒溢出加權)
        # DEC-039：df_comments 必須傳入（不得省略後靜默退回舊的文章層級
        # comments_scraped_at 過濾）——見 generate_daily_features() docstring。
        df_features = self.feature_aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=df_comments, failed_source_keys=failed_source_keys,
        )

        # 2.5 附加監督式學習目標標籤 (target_next_close / target_return_1d / target_up_down)
        #     UG-G2-SB1 之前，此函式從未在正式 ETL 管線中被呼叫，這三欄從未進入資料庫。
        df_features = self.feature_aggregator.generate_target_labels(df_features)

        # 3. 寫回資料庫
        self.db_writer.upsert_ml_features(df_features)

    def run_triple_barrier_tail_recompute(self, holding_period: int = TRIPLE_BARRIER_HOLDING_PERIOD,
                                          tail_window: int = None):
        """
        UG-G3-SB2 §3.1：每日尾端重算掛點——對每檔股票尾端 `tail_window` 列
        （預設 `holding_period + 1`）重跑 Triple-Barrier 標籤，寫回
        `daily_ml_features` 的 `target_triple_barrier`／`label_reason` 兩欄。
        不是全量重算，是對 `stock_prices` **全部股票**（非僅追蹤中的標的）尾端
        少數列重算，成本可忽略。

        執行順序：須排在 `run_feature_engineering_pipeline()`（當日特徵列
        寫入）之後——本方法依賴 `daily_ml_features` 已有當日基底列可供
        `UPDATE`；不依賴當日情緒／技術特徵是否已計算完成（Triple-Barrier
        只讀 `stock_prices` 的價格，不讀其餘特徵）。

        ⚠⚠ **已接線（2026-09-10，PO binding confirmation）**——
        `run_all_daily_tasks()` 呼叫本方法。**但 `run_all_daily_tasks()`
        本身仍受 `doc/governance/PROJECT_STATUS.md` §0.5 #20 每日 ETL
        執行閘門限制，`UG-G3-SB2a`（價格基準政策）Gate B 通過前不得執行**
        ——接線（程式碼／測試）與啟用執行（實際觸發每日排程）是兩個不同
        層級的動作，本次授權僅前者。§0.5 #20 已於 `UG-G3-SB2a` Gate B
        （`f479e14`，2026-09-11）解除；首次真正執行走另一輪 binding
        confirmation，見缺口自動追補案。

        Args:
            tail_window: 首次每日 ETL 缺口自動追補案新增——**與 `holding_period`
                是兩個獨立的概念，不得共用同一個值**（見
                `FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md` §3.6）：
                `holding_period` 是 Triple-Barrier 本身的持有期窗口（業務常數，
                不因追補天數改變）；`tail_window` 只決定「重算範圍」。呼叫端
                （`run_all_daily_tasks()`）在一次追補 n 個新交易日時傳入
                `tail_window=holding_period+n`；預設 `None` 時傳給
                `recompute_tail_labels()` 也是 `None`，退化為現行的
                `holding_period+1`，行為與本參數新增前逐位相同。
        """
        print("\n========== UG-G3-SB2 每日尾端重算掛點 ==========")
        df_prices = self.db_writer.fetch_data(
            "SELECT stock_id, trade_date, open_price, high_price, low_price "
            "FROM stock_prices ORDER BY stock_id, trade_date"
        )
        if df_prices is None or df_prices.empty:
            print("[WARNING] stock_prices 無資料，跳過每日尾端重算。")
            return 0

        tail = recompute_tail_labels(df_prices, holding_period=holding_period,
                                     tail_window=tail_window)
        n_updated = self.db_writer.update_triple_barrier_tail_labels(tail)

        if n_updated != len(tail):
            print(
                f"[WARNING] Triple-Barrier 尾端重算：實際影響列數 {n_updated} != "
                f"預期 {len(tail)}——可能有股票的 daily_ml_features 尾端列尚未"
                f"由 run_feature_engineering_pipeline() 建立（執行順序前提未成立）。"
            )
        return n_updated

    def run_all_daily_tasks(self, run_discovery: bool = True):
        """
        統整所有每日例行任務 (動態時序與啟用清單驅動)。

        Args:
            run_discovery: §0.5 #31——是否允許本次執行探索 AI 熱門詞（即使允許，
                仍受距上次「有問過」是否達 `DISCOVERY_INTERVAL_DAYS` 天限制，
                見 `run_all_daily_tasks()` 內的判準邏輯）。`False` 時本次執行
                完全不查、不呼叫、不寫列——供未來的 08:30 雙時點觸發案傳入。
        """
        from datetime import datetime

        now = now_taipei()
        started_at = now
        run_log_writer = self._run_log_writer()
        refusal = None

        # ==================================================================
        # 0. UG-G2-SB7：全市場批次取價（**每市場 1 個邏輯請求／日**）
        #    + 首次每日 ETL 缺口自動追補
        #    （`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`）：
        #    偵測每市場 candidate_prices 現有最新日期，逐日推進到
        #    previous_business_day()，不是只抓一天——中斷任意長度的時間後
        #    再執行都能自行補齊，不需另開回補腳本。
        # ==================================================================
        # ⚠ **這一段與下面的逐股迴圈並存，不是取代它**（複查方 2026-09-04）：
        # 兩者寫的是**不同的表** —— 本段寫 `candidate_prices`（全市場，供 universe
        # 排名），下面的迴圈寫 `stock_prices`（4 檔追蹤標的，供特徵管線）。
        # 決策點 2 已裁決**不**把 150 檔 universe 寫進 `stock_prices`，
        # **故舊迴圈仍有它自己的職責，不是待淘汰的東西。**
        print("\n========== UG-G2-SB7 全市場批次取價 ==========")
        target_date = previous_business_day()

        last_dates_by_market = self.db_writer.fetch_candidate_prices_max_date_by_market()
        _missing_origin = [m for m, d in last_dates_by_market.items() if d is None]
        if _missing_origin:
            # 沒有起點就不能追補——不得預設成任何日期後靜默只跑單日
            # （提案 §3.1 補充）。零請求送出。
            raise MissingBackfillOriginError(_missing_origin[0])

        # 各市場各自算缺口序列——分開偵測，因為 TPEX 常態性單邊失敗（RISK-028），
        # 不能因為 TWSE 補到了就當 TPEX 那天也補完（提案 §3.1）。
        backfill_dates_by_market = {
            market: compute_gap_backfill_dates(last_date, target_date)
            for market, last_date in last_dates_by_market.items()
        }
        all_backfill_dates = sorted(set().union(*backfill_dates_by_market.values()))

        active_markets = set(backfill_dates_by_market.keys())
        batch_outcomes_by_date = {}
        # 逐市場、實際被嘗試（未被 REFUSED 停掉）的日期——逐股階段只處理這些
        # 日期，不對已停掉的市場在無資料可複製的日期硬跑。
        dates_attempted_by_market = {m: [] for m in active_markets}

        for trade_date in all_backfill_dates:
            markets_today = tuple(sorted(
                m for m in active_markets if trade_date in backfill_dates_by_market[m]))
            if not markets_today:
                continue
            try:
                batch_counts = self.run_price_batch(
                    trade_date, markets=markets_today, run_log_writer=run_log_writer)
                outcomes = (batch_counts or {}).get("outcomes_by_item")
            except ServiceRefusedError as exc:
                # **一個服務叫我們停，不代表其餘來源也要停** ——
                # PTT 與 Gemini 是完全不同的服務。
                # run log 已在 `run_price_batch` 內寫完（**在 raise 之前**），
                # 此處記下並在**所有階段跑完之後**才 raise，
                # 讓本次執行以非零結束、操作者被通知。
                print("[WARNING] 批次取價被服務拒絕，其餘來源繼續：%s" % exc)
                refusal = exc
                # **例外把逐項 outcome 帶過來了** —— 上櫃標的因此被記為 `REFUSED`，
                # 不是 `FETCH_FAILED`。**那個為此存在的第四態要被用上。**
                outcomes = exc.outcomes_by_item
                # 被拒的市場自本日起停止對後續追補日期的嘗試（§3.2）。
                for m in list(active_markets):
                    if outcomes.get(m) == REFUSED:
                        active_markets.discard(m)

            # ⚠ **空字典曾同時代表三件事**：批次被拒／`batch_counts` 為 None／
            # 批次回傳空的 outcomes，而舊規則把三者處置成同一件事。
            # 被拒那一項已由上面的例外攜帶處理，**其餘兩項現在明確地不可能** ——
            # 讓它們 raise，而不是與「被拒」共用同一個表示。
            if not isinstance(outcomes, dict):
                raise RuntimeError(
                    "run_price_batch 未回傳 outcomes_by_item（實得 %r）—— "
                    "逐股階段無法歸因『上櫃標的沒有列』的成因，**不得繼續**"
                    % (outcomes,))

            batch_outcomes_by_date[trade_date] = outcomes
            for m in markets_today:
                dates_attempted_by_market[m].append(trade_date)

        # 1. 執行股價管線 (動態讀取啟用標的)
        print("\n========== 正在載入追蹤股票標的清單 ==========")
        try:
            active_stocks = self.db_writer.fetch_active_stock_targets()
        except Exception as e:
            print(f"[WARNING] 載入股票標的清單異常，啟用預設清單: {e}")
            active_stocks = []

        if not active_stocks:
            active_stocks = [
                {"stock_id": "2330", "market": "TWSE"},
                {"stock_id": "2382", "market": "TWSE"},
                {"stock_id": "6488", "market": "TPEX"},
                {"stock_id": "NVDA", "market": "US"},
            ]

        print(f"[INFO] 取得 {len(active_stocks)} 檔啟用標的: {[s['stock_id'] for s in active_stocks]}")

        tracked_items = tuple(active_stocks)
        # ⚠⚠ **item_count 取自迴圈開始前就固定的清單與日期序列**（同
        # `run_price_batch`）。不得由記錄反推 —— 那樣它會恆等，`assert_complete`
        # 就成了空檢查（§9A.1）。US 標的不參與缺口迴圈（§3.7 不動的東西），
        # 每次執行只跑一次；TWSE／TPEX 標的各自依其市場實際被嘗試的日期數計。
        tracked_count = sum(
            1 if stock.get("market", "TWSE").upper() == "US"
            else len(dates_attempted_by_market.get(
                stock.get("market", "TWSE").upper().lower(), []))
            for stock in tracked_items
        )
        tracked_entries = []
        # PTT 階段（稍後）沿用既有的單一「今天」batch_key，與上面逐日的
        # stock_batch_key 是不同概念——PTT 不參與缺口自動追補迴圈（§3.7）。
        tracked_batch_key = now.date().isoformat()

        for stock in tracked_items:
            sid = stock["stock_id"]
            mkt = stock.get("market", "TWSE").upper()

            if mkt == "US":
                try:
                    self.run_us_stock_pipeline(sid, period="3mo")
                    outcome = OK
                except Exception as exc:      # noqa: BLE001
                    tracked_entries.append(RunLogEntry(
                        SOURCE_TRACKED_DAILY, now.date().isoformat(), sid,
                        FETCH_FAILED,
                        detail=("%s: %s" % (type(exc).__name__, exc))[:500]))
                    print("  [%s] %s FETCH_FAILED：%s"
                          % (now.date().isoformat(), sid, exc))
                    continue
                tracked_entries.append(RunLogEntry(
                    SOURCE_TRACKED_DAILY, now.date().isoformat(), sid, outcome))
                continue

            # TWSE／TPEX：對本市場本次實際被嘗試的每一個追補日期各跑一次
            # （提案 §3.5）——`etl_run_log` 的 `batch_key` 逐日分開。
            # ⚠ 變數刻意命名為 `stock_batch_key`，不是 `tracked_batch_key`——
            # 後者是本方法稍後（PTT 階段）已在使用的既有變數名，代表「本次
            # 執行的今天」，語意不同，不得混用（曾撞名過一次，UnboundLocalError）。
            for trade_date in dates_attempted_by_market.get(mkt.lower(), []):
                outcome = OK
                stock_batch_key = trade_date.isoformat()
                try:
                    if mkt == "TPEX":
                        # (iii)：上櫃改由 candidate_prices 供應，不再落 yfinance 備援。
                        # **這使本迴圈依賴批次階段已先跑過該日** ——
                        # 順序由 `test_batch_stage_runs_before_per_stock_stage` 釘住，
                        # **不是靠「批次剛好寫在前面」這個巧合**。
                        outcome = self.run_tpex_pipeline_from_candidate_prices(
                            sid, trade_date,
                            batch_outcome=batch_outcomes_by_date[trade_date].get("tpex"))
                    elif mkt == "TWSE":
                        # `UG-G3-SB2a` 方案 B：TWSE 比照上櫃，改由 candidate_prices
                        # 供應（同一份實作，見 run_twse_pipeline_from_candidate_prices
                        # 的別名指派）。舊版逐股爬蟲＋yfinance 路徑已刪除。
                        outcome = self.run_twse_pipeline_from_candidate_prices(
                            sid, trade_date,
                            batch_outcome=batch_outcomes_by_date[trade_date].get("twse"))
                except Exception as exc:      # noqa: BLE001
                    # **「單一失敗不阻塞」在這裡實作成「記錄後繼續」，不是「略過」。**
                    # 本迴圈修正前**完全沒有 try/except** —— 一檔失敗會中止全部；
                    # 而加上 try 卻不記錄的話，那一檔就長得像「那天沒資料」（§7.1）。
                    #
                    # ⚠ **上游被拒時記 `REFUSED` 而非 `FETCH_FAILED`**：
                    # 後者對 (iii) 之後的上櫃路徑是雙重誤述 —— 它根本不 fetch，
                    # 且失敗原因是上游被拒。例外自己帶著上游的 outcome 過來。
                    upstream = getattr(exc, "upstream_outcome", None)
                    failure_outcome = (upstream if upstream in (REFUSED, FETCH_FAILED)
                                       else FETCH_FAILED)
                    tracked_entries.append(RunLogEntry(
                        SOURCE_TRACKED_DAILY, stock_batch_key, sid, failure_outcome,
                        detail=("%s: %s" % (type(exc).__name__, exc))[:500]))
                    print("  [%s] %s FETCH_FAILED：%s" % (stock_batch_key, sid, exc))
                    continue
                tracked_entries.append(RunLogEntry(
                    SOURCE_TRACKED_DAILY, stock_batch_key, sid, outcome))

        tracked_counts = assert_complete(tracked_entries, tracked_count)
        if run_log_writer is not None:
            run_log_writer.write(tracked_entries, started_at)
        print(format_summary(SOURCE_TRACKED_DAILY,
                             (all_backfill_dates[-1].isoformat()
                              if all_backfill_dates else now.date().isoformat()),
                             tracked_counts))

        # §0.5 #30 必修：n 來源改為「daily_ml_features 落後 stock_prices 的交易日數」
        # （n_lag），取代原本錯誤地取自 candidate_prices 價格缺口的做法——本次執行
        # 自己就會把價格缺口補齊，若沿用價格缺口當 n，下次執行時它已歸零，
        # 尾端視窗會誤退回預設的 holding_period+1，蓋不到累積下來的特徵落後天數。
        # 必須排在逐股階段之後（stock_prices 已是本次最終狀態）、特徵階段之前
        # （daily_ml_features 還是寫入前的舊狀態）——此刻兩者的 MAX(trade_date)
        # 差距才是特徵階段即將新增的交易日數。
        feature_lag = self.db_writer.fetch_feature_lag()
        n_lag = feature_lag["n_lag"]
        print("[INFO] 特徵表落後股價表：daily_ml_features.max=%s，"
              "stock_prices.max=%s，n_lag=%d 個交易日"
              % (feature_lag["feature_max_date"], feature_lag["price_max_date"], n_lag))

        # --- 【新增】AI 動態探索熱門詞 ---
        # §0.5 #31：探索頻率改每週一次，判準見
        # GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.1。`run_discovery()`
        # 現在回傳 (outcome, detail) 四態，例外不跨越函式邊界，本段不再需要
        # try/except——若未來出現本設計未預期的例外，應讓它自然中止，
        # 不得另外加一層吞掉（否則又會重蹈「不落地」的覆轍）。
        print("\n========== 啟動 AI 熱門趨勢探索 ==========")
        should_run_discovery = False
        if run_discovery:
            last_probed = self.db_writer.fetch_last_discovery_probed_date()
            should_run_discovery = (
                last_probed is None
                or (now.date() - last_probed).days >= DISCOVERY_INTERVAL_DAYS
            )

        if should_run_discovery:
            outcome, detail = self.trend_discover.run_discovery(
                self.db_writer, max_new_keywords=3)
            kwargs = {"detail": detail} if outcome in (FETCH_FAILED, REFUSED) else {}
            discovery_entries = [RunLogEntry(
                SOURCE_AI_DISCOVERY, tracked_batch_key, "discovery", outcome, **kwargs)]
            if run_log_writer is not None:
                run_log_writer.write(discovery_entries, started_at)
        # else（A4 裁決）：run_discovery=False 或距上次「有問過」不足
        # DISCOVERY_INTERVAL_DAYS 天——不寫任何列。跳過與探索前中止的事後
        # 區分方式見 GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.1。

        # 2. 執行輿情管線 (Phase 1)
        print("\n========== 正在載入追蹤關鍵字清單 ==========")
        active_keywords = self.db_writer.fetch_active_keywords()
        if not active_keywords:
            active_keywords = ["台積電", "廣達", "環球晶", "NVDA", "降息", "AI"]

        print(f"[INFO] 取得 {len(active_keywords)} 個追蹤關鍵字：{active_keywords}")

        # ⚠⚠ **item_count 取自迴圈開始前就固定的清單**（同 `run_price_batch`
        # 與逐股迴圈）。不得由記錄反推 —— 那樣它會恆等（§9A.1）。
        keyword_items = tuple(active_keywords)
        keyword_count = len(keyword_items)
        keyword_entries = []

        # ⚠⚠ **由「每個關鍵字各一次搜尋」改為「一次看板抓取」**
        # （UG-G2-SB7 第 5 項）。請求數由 `len(keywords)` 次搜尋
        # 變成**至多 `BOARD_PAGE_BUDGET` 次**頁面請求，與關鍵字數脫鉤。
        #
        # **run log 仍逐關鍵字記錄** —— 同 `run_price_batch`：
        # 一次請求、逐項記錄。那個粒度是 RISK-015 覆蓋率量測的依據，
        # **不能因為請求變成一次就跟著塌掉**。
        since_ts = time.time() - BOARD_LOOKBACK_DAYS * 86400
        try:
            kw_outcomes = self.run_ptt_board_pipeline(
                list(keyword_items), since_timestamp=since_ts)
        except Exception as exc:      # noqa: BLE001
            # 契約 §3.5：「捕獲此例外後**記錄**並跳過該來源」——
            # **記錄是持久化，不是 print**。
            #
            # ⚠ 批次模式下，一次失敗影響的是**全部**關鍵字 ——
            # 那是本次變更的取捨（見 Gate B 報告），
            # **必須逐關鍵字落地，不得只記一列**：
            # 少記的那些會在覆蓋率量測裡長得像「那天沒有資料」。
            detail = ("%s: %s" % (type(exc).__name__, exc))[:500]
            for kw in keyword_items:
                keyword_entries.append(RunLogEntry(
                    SOURCE_PTT, tracked_batch_key, kw, FETCH_FAILED,
                    detail=detail))
            print("  [%s] 看板批次 FETCH_FAILED（%d 個關鍵字全部受影響）：%s"
                  % (tracked_batch_key, keyword_count, exc))
            kw_outcomes = None

        if kw_outcomes is not None:
            for kw in keyword_items:
                kw_outcome, kw_detail = kw_outcomes.get(
                    kw, (FETCH_FAILED, "看板批次未回報此關鍵字的 outcome"))
                keyword_entries.append(RunLogEntry(
                    SOURCE_PTT, tracked_batch_key, kw, kw_outcome,
                    detail=kw_detail))

        keyword_counts = assert_complete(keyword_entries, keyword_count)
        if run_log_writer is not None:
            run_log_writer.write(keyword_entries, started_at)
        print(format_summary(SOURCE_PTT, tracked_batch_key, keyword_counts))
            
        # 3. 執行 NLP 情緒運算管線 (Phase 2)
        # §0.5 #31：傳入 run_log_writer／started_at／batch_key，供撞到每日
        # 配額耗盡時落地 REFUSED 列——batch_key 沿用本方法既有的
        # tracked_batch_key，不重新推導（同上方探索段的理由）。
        self.run_nlp_sentiment_pipeline(batch_size=500, run_log_writer=run_log_writer,
                                         started_at=started_at, batch_key=tracked_batch_key)

        # 4. 執行特徵工程管線 (將股價與情緒合併)
        self.run_feature_engineering_pipeline()

        # 5. UG-G3-SB2 §3.1：每日尾端重算掛點（PO 2026-09-10 binding confirmation，
        #    僅接線本身；run_all_daily_tasks() 實際執行仍受 PROJECT_STATUS.md
        #    §0.5 #20 閘門限制，UG-G3-SB2a Gate B 通過前不得執行；閘門已於
        #    f479e14 解除，首次真正執行見缺口自動追補案）。
        #    必須排在 run_feature_engineering_pipeline() 之後——本方法依賴
        #    daily_ml_features 已有當日基底列可供 UPDATE。
        # §0.5 #30 必修（訂正版）：尾端重算範圍依 n_lag（daily_ml_features 落後
        # stock_prices 的交易日數，逐股階段後、特徵階段前算好，見上方）加寬為
        # TRIPLE_BARRIER_HOLDING_PERIOD+n_lag（與 run_triple_barrier_tail_recompute()
        # 自身的 holding_period 預設值引用同一個模組常數，不各自硬寫字面 5）。
        # **原本用 n_new_days（candidate_prices 價格缺口）的版本已移除**——那個來源
        # 在本次執行把價格缺口補齊後就會歸零，即使 daily_ml_features 仍嚴重落後，
        # 會讓尾端視窗誤退回預設值，蓋不到累積下來的特徵落後天數（真實案例：
        # 2026-09-17 首次真實執行因 Gemini 配額中止，價格已補到 09-16 但
        # daily_ml_features 仍停在 09-04，若沿用舊邏輯，下次執行 n_new_days=0）。
        # n_lag=0（特徵表已與股價表同步）時不傳 tail_window，退化為現行的
        # holding_period+1，行為與本次修改前逐位相同。
        if n_lag > 0:
            self.run_triple_barrier_tail_recompute(
                tail_window=TRIPLE_BARRIER_HOLDING_PERIOD + n_lag)
        else:
            self.run_triple_barrier_tail_recompute()
            
        print("\n========== 所有 ETL 任務執行完畢 ==========")
        if refusal is not None:
            # **稽核紀錄已落地，最後才讓執行以非零結束。**
            raise refusal


if __name__ == "__main__":
    # 只需要把 Orchestrator 實例化，然後呼叫每日任務方法即可
    pipeline = ETLPipelineManager()
    pipeline.run_all_daily_tasks()