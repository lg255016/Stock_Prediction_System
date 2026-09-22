# -*- coding: utf-8 -*-
"""UG-G2-SB7 §5 的 V4：**批次路徑不得使用逐股取數器**。

================================================================================
本檔刻意在接線**之前**寫，並先於修正 commit
================================================================================
複查方 2026-09-04：

> **V4 先寫**（逐股路徑不得用於每日增量）——它釘住 §0.2 的邊界，
> **在接線之前寫才有意義**；接完再補，它只會描述已經發生的事。

且依 DEC-033 §Decision 第 6 條的類推（複查方同一輪指出）：
**先 commit 會紅的測試，再 commit 修正** —— 那時紅是歷史事實，不是從 diff 推導。

**因此本檔在 `run_price_batch` 尚不存在時就會 FAIL，那是預期的。**

================================================================================
V4 釘住的是什麼
================================================================================
提案 §0.2 的裁決是：逐股路徑（`STOCK_DAY`）**限縮但不刪除**。

| 用途 | 路徑 | 理由 |
|------|------|------|
| **每日增量** | 全市場報表 | 1 個請求 vs 150 個 |
| **單檔歷史回補** | `STOCK_DAY` | `MI_INDEX` 一次只給一天；補一檔一年要 240 個請求，`STOCK_DAY` 只要 12 個 |

> **兩個端點的形狀本來就相反**，所以逐股路徑有它真實的用途。
> **但職責邊界若只存在於某個人的理解裡，它就會在下一次被違反** ——
> 有人「順手」把 `fetch_twse_stock_data` 接回每日迴圈，
> **請求量會回到 150 個而沒有任何東西會叫**。

⚠ **V4 的已知限制**（提案 §8 第 2 項）：它只檢查**批次路徑**，
不檢查所有可能的呼叫端。有人從別處呼叫 `fetch_twse_stock_data`，V4 抓不到。

================================================================================
⚠⚠ 標題修正（2026-09-04，複查方指出）
================================================================================
本檔原名「**逐股路徑不得用於每日增量**」，**那個名字說的比它量的多**。

**舊的逐股迴圈今天仍然每日在用**，而且兩條路徑寫的是不同的表：

| 路徑 | 寫入 | 對象 |
|------|------|------|
| 逐股迴圈（`UG-G3-SB2a` 方案 B：複製 `candidate_prices`） | `stock_prices` | 4 檔追蹤標的 |
| `run_price_batch` | `candidate_prices` | 全市場 |

決策點 2 已裁決**不**把 150 檔 universe 寫進 `stock_prices`，
**所以舊迴圈仍有它自己的職責，不是待淘汰的東西。**

本判準實際斷言的是「`run_price_batch` 不呼叫 `TwseScraper`」——
**它不能被拿來當成「每日執行已經批次化」的證據**。
**判準的名字說的比它量的多，正是本 SB 一路在拆的那種東西。**
"""
import datetime as _dt
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class V4BatchPathMustNotUsePerStockFetcher(unittest.TestCase):
    """**V4**：`run_price_batch` 對 `TwseScraper.fetch_twse_stock_data` 零呼叫。

    **什麼輸入會讓它 FAIL**：把逐股取價接進批次路徑 —— 呼叫次數 > 0。

    ⚠ **範圍**：只管批次路徑。**舊逐股迴圈為 `stock_prices` 服務，
    不在本判準範圍內**（見模組 docstring 的標題修正）。
    """

    def _make_manager(self):
        """建立 pipeline，但**不建立任何真實連線**。

        `ETLPipelineManager.__init__` 會實例化 `DBWriter`，而後者在缺少環境變數時
        `raise RuntimeError`。此處以 patch 隔離，使本測試**不依賴環境**
        （`CLAUDE.md` §13.4：測試封閉性）。
        """
        import main_etl_pipeline as mep
        with patch.object(mep, "DBWriter", MagicMock()), \
             patch.object(mep, "TrendDiscover", MagicMock()), \
             patch.object(mep, "NLPProcessor", MagicMock()), \
             patch.object(mep, "FeatureAggregator", MagicMock()):
            return mep.ETLPipelineManager()

    def test_v4_run_price_batch_exists(self):
        """每日批次必須有一個**專屬入口**，而不是散在 `run_all_daily_tasks` 裡。

        沒有專屬入口，V4 就沒有可以斷言的對象 ——
        **那會讓這條判準退化成「讀程式碼確認」，而那不是檢查。**
        """
        import main_etl_pipeline as mep
        self.assertTrue(
            hasattr(mep.ETLPipelineManager, "run_price_batch"),
            "每日增量取價需要一個專屬入口 `run_price_batch`；"
            "V4 才有可斷言的對象")

    def test_v4_batch_path_never_calls_per_stock_fetch(self):
        """**核心斷言**：`run_price_batch` 執行期間，逐股取價**零呼叫**。

        **TwseScraper 去留裁決（PO 2026-09-12）後訂正**：`manager.twse_scraper`
        自 `138bfc8`（方案 B）起，`ETLPipelineManager` 已不再設置這個屬性、
        `main_etl_pipeline` 模組層級也已不再匯入 `TwseScraper`——原本
        「手動塞一個 mock 上去，再斷言它零呼叫」對現行程式碼是**結構上不可能
        FAIL** 的斷言（`CLAUDE.md` §9A.1）：production 已經沒有任何路徑會去碰
        這個屬性，不論測試怎麼寫都會是 0。改斷言「屬性／類別根本不存在」——
        連呼叫的對象都沒有，比斷言「呼叫次數為 0」更貼近 V4 實際要保證的事。
        """
        import main_etl_pipeline as mep
        manager = self._make_manager()
        manager.yf_api = MagicMock()

        fake_fetch = MagicMock(side_effect=self._fake_market_report)
        with patch("main_etl_pipeline.fetch_market_report", fake_fetch):
            manager.run_price_batch(_dt.date(2026, 9, 3))

        self.assertFalse(
            hasattr(manager, "twse_scraper"),
            "批次路徑必須走全市場報表（1 個請求／市場），不是逐股路徑"
            "（150 個請求）——提案 §0.2；逐股取數器連屬性都不該存在")
        self.assertFalse(
            hasattr(mep, "TwseScraper"),
            "main_etl_pipeline 模組層級不應再匯入 TwseScraper")
        self.assertEqual(
            manager.yf_api.fetch_yfinance_data.call_count, 0,
            "批次路徑的台股取價不得落 yfinance 備援——"
            "上櫃已由 tpex 市場報表供應（提案 §0.1a）。"
            "⚠ 這**不**表示 yfinance 已退出台股——舊逐股迴圈仍會用它")

    def test_v4_batch_uses_one_logical_request_per_market(self):
        """請求量的宣稱要被釘住，不只是寫在提案裡。"""
        fake_fetch = MagicMock(side_effect=self._fake_market_report)
        manager = self._make_manager()
        with patch("main_etl_pipeline.fetch_market_report", fake_fetch):
            manager.run_price_batch(_dt.date(2026, 9, 3))
        markets = [c.args[0] if c.args else c.kwargs.get("market")
                   for c in fake_fetch.call_args_list]
        self.assertEqual(sorted(markets), ["tpex", "twse"],
                         "每個市場恰好一次邏輯請求")

    @staticmethod
    def _fake_market_report(market, trade_date, **kwargs):
        """不觸網的假回應：兩檔普通股。"""
        from src.extractors.market_report_fetcher import FetchResult
        records = [{"stock_id": "2330", "trade_date": trade_date,
                    "turnover_amount": 1_000_000, "volume": 100},
                   {"stock_id": "6488", "trade_date": trade_date,
                    "turnover_amount": 2_000_000, "volume": 200}]
        stats = {"rows_common_stock": 2, "rows_total": 2}
        return FetchResult(market, trade_date, records, stats,
                           logical_requests=1, http_attempts=1)


class V2ItemCountComesFromBeforeTheLoop(unittest.TestCase):
    """**複查方 2026-09-04 條件 1**：`item_count` 取自迴圈**開始前**的固定清單。

    > 若 `item_count` 來自結果（例如 `len(fetched)` 或迴圈跑完才算），
    > **它會恆等，而且看起來完全正常。**

    **什麼輸入會讓它 FAIL**：把 `item_count` 改成由記錄反推 ——
    下方「其中一個市場整個失敗」的案例會變成通過，因為和永遠等於記錄數。
    """

    def test_v2_one_market_failing_still_accounts_for_both(self):
        """一個市場 `FETCH_FAILED`，另一個 `OK` —— **總數仍須是 2**。"""
        import datetime as dt
        import main_etl_pipeline as mep
        from src.extractors.market_report_fetcher import FetchFailedError, FetchResult

        def half_broken(market, trade_date, **kwargs):
            if market == "tpex":
                raise FetchFailedError("HTTP 500")
            return FetchResult(market, trade_date,
                               [{"stock_id": "2330", "trade_date": trade_date,
                                 "turnover_amount": 1, "volume": 1}],
                               {"rows_common_stock": 1},
                               logical_requests=1, http_attempts=1)

        with patch.object(mep, "DBWriter", MagicMock()), \
             patch.object(mep, "TrendDiscover", MagicMock()), \
             patch.object(mep, "NLPProcessor", MagicMock()), \
             patch.object(mep, "FeatureAggregator", MagicMock()):
            manager = mep.ETLPipelineManager()
        with patch("main_etl_pipeline.fetch_market_report", half_broken):
            counts = manager.run_price_batch(dt.date(2026, 9, 3))

        self.assertEqual(counts["total"], 2,
                         "兩個市場都必須有 outcome —— 失敗的那個不得被靜默略過")
        self.assertEqual(counts["FETCH_FAILED"], 1)
        self.assertEqual(counts["OK"], 1)


class RefusalStillLeavesAnAuditTrail(unittest.TestCase):
    """**複查方 2026-09-04 第二、三節**：一次 429 不得讓整批的 run log 消失。

    修正前的行為：`except ServiceRefusedError: raise` **直接離開函式**，
    於是 `assert_complete()` 與 `run_log_writer.write()` 都被跳過 ——
    **而迴圈內已經 `upsert_to_candidate_prices()` 過了**。

    > **side effect 留下了，稽核紀錄沒有。**
    > 那與 §0.3 要修的病是同一個，只是換了形狀：
    > 那邊是「失敗被吞掉、沒進任何資料」，這裡是「成功被寫進去、也沒進任何資料」。
    """

    def _manager(self):
        import main_etl_pipeline as mep
        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            return mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

    @staticmethod
    def _first_ok_second_refused(market, trade_date, **kwargs):
        """TWSE 成功（且會寫進 DB）、TPEx 被拒 —— **兩台不同的主機**。"""
        from src.extractors.market_report_fetcher import (
            FetchResult, ServiceRefusedError)
        if market == "tpex":
            raise ServiceRefusedError("HTTP 429（服務拒絕）—— 硬停，一次都不重試")
        return FetchResult(market, trade_date,
                           [{"stock_id": "2330", "trade_date": trade_date,
                             "turnover_amount": 1, "volume": 1}],
                           {"rows_common_stock": 1},
                           logical_requests=1, http_attempts=1)

    def test_run_log_is_written_before_the_raise(self):
        """**known-FAIL**：修正前 `write()` 零呼叫；修正後必須有兩列。"""
        import datetime as dt
        import main_etl_pipeline as mep
        from src.extractors.market_report_fetcher import ServiceRefusedError
        from src.loaders.etl_run_log import OK, REFUSED

        manager = self._manager()
        writer = MagicMock()
        with patch("main_etl_pipeline.fetch_market_report",
                   self._first_ok_second_refused):
            with self.assertRaises(ServiceRefusedError):
                manager.run_price_batch(dt.date(2026, 9, 3),
                                        run_log_writer=writer)

        self.assertEqual(writer.write.call_count, 1,
                         "run log 必須在 raise 之前寫 —— "
                         "否則已寫進 candidate_prices 的資料沒有對應的稽核紀錄")
        entries = writer.write.call_args.args[0]
        self.assertEqual(len(entries), 2, "兩個市場都要有 outcome")
        by_item = dict((e.item_key, e.outcome) for e in entries)
        self.assertEqual(by_item["twse"], OK)
        self.assertEqual(by_item["tpex"], REFUSED)

    def test_refusal_does_not_abort_the_other_market(self):
        """TWSE 的 429 **對 TPEx 那台主機什麼都沒說** —— 另一個市場仍須被嘗試。

        ⚠ **被拒的市場必須排在第一個。**

        本測試的第一版讓 `tpex`（第二個）被拒，而那個版本
        **在修正前也會通過** —— 因為 `twse` 排在前面，它本來就已經跑過了。
        **一個「兩個市場都被呼叫」的斷言，在被拒者排最後時無法失敗**（§9A.1）。
        受控演示（2026-09-04）抓到了這件事：修正前三項中只有兩項變紅，
        **這一項是那個不會紅的**。
        """
        import datetime as dt
        from src.extractors.market_report_fetcher import (
            FetchResult, ServiceRefusedError)

        def first_refused(market, trade_date, **kwargs):
            if market == "twse":                    # ← **第一個就被拒**
                raise ServiceRefusedError("HTTP 429（服務拒絕）")
            return FetchResult(market, trade_date,
                               [{"stock_id": "6488", "trade_date": trade_date,
                                 "turnover_amount": 1, "volume": 1}],
                               {"rows_common_stock": 1},
                               logical_requests=1, http_attempts=1)

        manager = self._manager()
        fake = MagicMock(side_effect=first_refused)
        with patch("main_etl_pipeline.fetch_market_report", fake):
            with self.assertRaises(ServiceRefusedError):
                manager.run_price_batch(dt.date(2026, 9, 3))
        markets = [c.args[0] for c in fake.call_args_list]
        self.assertEqual(sorted(markets), ["tpex", "twse"],
                         "因一邊拒絕而放棄另一邊，當天兩個市場都沒有資料——"
                         "那是一個資料缺口，換來的不是任何安全")

    def test_refused_is_not_recorded_as_fetch_failed(self):
        """**詞彙要跟例外型別一樣分得開。**

        兩者處置相反；若 outcome 欄裡分不開，
        run log 就回答不了「那天是被拒絕，還是抓失敗」。
        """
        import datetime as dt
        from src.extractors.market_report_fetcher import ServiceRefusedError
        from src.loaders.etl_run_log import FETCH_FAILED, REFUSED

        manager = self._manager()
        writer = MagicMock()
        with patch("main_etl_pipeline.fetch_market_report",
                   self._first_ok_second_refused):
            with self.assertRaises(ServiceRefusedError):
                manager.run_price_batch(dt.date(2026, 9, 3), run_log_writer=writer)
        outcomes = [e.outcome for e in writer.write.call_args.args[0]]
        self.assertIn(REFUSED, outcomes)
        self.assertNotIn(FETCH_FAILED, outcomes)


class PerSourceSummaryIsNotATautology(unittest.TestCase):
    """**複查方 2026-09-04 第四節**：逐來源摘要不得用檢查函式做格式化。

    修正前那三行是 `assert_complete(X, len-of-X)` —— **永遠通過**，
    而警告就寫在 `assert_complete` 自己的 docstring 裡，
    **離上面那個正確的呼叫只有三行**。
    """

    def test_summarize_is_used_for_formatting_not_assert_complete(self):
        """`summarize()` 只彙總不檢查；把它拿去當檢查會是空的。"""
        from src.loaders.etl_run_log import (
            FETCH_FAILED, OK, RunLogEntry, assert_complete, summarize)
        entries = [RunLogEntry("s", "b", "i1", OK),
                   RunLogEntry("s", "b", "i2", FETCH_FAILED, detail="HTTP 500")]
        # summarize 對任何輸入都成立——**它不是檢查**
        self.assertEqual(summarize(entries)["total"], 2)
        # 而 assert_complete 用 len(entries) 當分母時同樣永遠成立
        assert_complete(entries, len(entries))          # 不會 raise —— 這正是問題
        # 用「跑之前就決定的」分母才抓得到
        with self.assertRaises(Exception):
            assert_complete(entries, 3)


class DailyTasksWireInTheBatchAndToleratePerStockFailure(unittest.TestCase):
    """`run_all_daily_tasks` 必須呼叫 `run_price_batch`，**且舊迴圈不得因單檔失敗而中止**。

    ⚠ **兩條路徑並存，不是取代**（複查方 2026-09-04）：
    批次寫 `candidate_prices`（全市場），舊迴圈寫 `stock_prices`（4 檔追蹤標的）。
    決策點 2 已裁決不把 150 檔 universe 寫進 `stock_prices`。
    """

    def _manager(self, mep):
        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            return mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

    def _run(self, mep, manager, stocks, twse_side_effect=None):
        """跑 `run_all_daily_tasks`，把所有會觸網／觸 LLM 的階段換掉。"""
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = stocks
        manager.db_writer.fetch_active_keywords.return_value = []
        # 首次每日 ETL 缺口自動追補（FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md）：
        # run_all_daily_tasks() 現在會先查每市場現有最新日期算缺口——固定成
        # 「昨天」，缺口序列剛好是 [previous_business_day()] 一天，等同本檔
        # 修改前的單日語意，既有測試斷言不必改。
        _one_day_ago = mep.previous_business_day() - _dt.timedelta(days=1)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _one_day_ago, "tpex": _one_day_ago}
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _one_day_ago,
            "price_max_date": _one_day_ago,
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：run_all_daily_tasks() 探索段新增 fetch_last_discovery_probed_date()
        # 查詢與 run_discovery() 回傳值解包——本檔原未設定，屬與 §0.5 #30
        # fetch_feature_lag() 同一機制的必然連帶影響（見 test_daily_hook_wiring.py
        # 同型註解），僅補 mock，不改動任何既有斷言。None 保留原本每次都會探索的
        # 既有行為；("OK", None) 避免 unpack 崩潰。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        # UG-G2-SB7 A 輪：`run_ptt_pipeline` 現在回傳 outcome（OK／NO_DATA），
        # **mock 必須符合那個契約** —— 回傳 MagicMock 會被 RunLogEntry 的窮舉擋下。
        # ⚠ 這是 §0.5 #17 的第四次表現：改動 `run_all_daily_tasks` 的契約時，
        #   需要編輯不測試它的檔案。**耦合才是缺陷，mock 不完整只是表現形式。**
        manager.run_ptt_pipeline = MagicMock(return_value="OK")
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": {"twse": "OK", "tpex": "OK"}})
        # `UG-G3-SB2a` 方案 B：呼叫端現在會採用回傳值，`return_value="OK"`
        # 是預設（`side_effect` 未提供時的行為）；有提供 `side_effect` 時
        # 由呼叫端自行決定回傳值（見 `boom()`）。
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(
            return_value="OK", side_effect=twse_side_effect)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(
            return_value="OK")
        manager.run_us_stock_pipeline = MagicMock()
        writer = MagicMock()
        with patch.object(mep.ETLPipelineManager, "_run_log_writer",
                          lambda self: writer):
            manager.run_all_daily_tasks()
        return writer

    def test_daily_tasks_call_run_price_batch(self):
        """**沒有這條，`run_price_batch` 只是一個沒人呼叫的函式。**

        V4 綠**不代表**每日執行已經批次化 —— V4 斷言的是
        「`run_price_batch` 不呼叫 `TwseScraper`」，
        而每日排程有沒有走 `run_price_batch` 是另一件事。
        """
        import main_etl_pipeline as mep
        manager = self._manager(mep)
        self._run(mep, manager, [{"stock_id": "2330", "market": "TWSE"}])
        self.assertEqual(manager.run_price_batch.call_count, 1)

    def test_per_stock_failure_is_recorded_and_does_not_block(self):
        """**known-FAIL**：修正前該迴圈**完全沒有 try/except**，一檔失敗會中止全部。

        且**加了 try 卻不記錄**的話，那一檔會長得像「那天沒資料」（§7.1）——
        故同時斷言「其餘標的仍被處理」與「失敗有 outcome」。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import FETCH_FAILED, OK

        stocks = [{"stock_id": "2330", "market": "TWSE"},
                  {"stock_id": "2382", "market": "TWSE"},
                  {"stock_id": "6488", "market": "TPEX"}]

        def boom(sid, *a, **k):
            if sid == "2382":
                raise RuntimeError("simulated fetch failure")
            # `UG-G3-SB2a` 方案 B：呼叫端現在會採用回傳值
            # （`outcome = self.run_twse_pipeline_from_candidate_prices(...)`），
            # 不像舊函式那樣回傳值被忽略——side_effect 必須明確回傳 OK。
            return OK

        manager = self._manager(mep)
        writer = self._run(mep, manager, stocks, twse_side_effect=boom)

        # ⚠ **2 而非 3**：UG-G2-SB7 (iii) 之後，上櫃標的（6488）改走
        # `run_tpex_pipeline_from_candidate_prices`，不再經過逐股迴圈的
        # TWSE 分支（`UG-G3-SB2a` 方案 B 之後，TWSE 分支改走
        # `run_twse_pipeline_from_candidate_prices`，與 TPEX 共用同一份實作，
        # 但呼叫端仍分開計數）。**這個數字的改變是 (iii) 的正確後果，不是回歸。**
        self.assertEqual(manager.run_twse_pipeline_from_candidate_prices.call_count, 2,
                         "兩檔上市標的都要被處理——一檔失敗不得中止其餘標的")
        self.assertEqual(
            manager.run_tpex_pipeline_from_candidate_prices.call_count, 1,
            "上櫃標的走 candidate_prices 那條路徑")
        tracked = [e for call in writer.write.call_args_list
                   for e in call.args[0]
                   if e.source == mep.SOURCE_TRACKED_DAILY]
        self.assertEqual(len(tracked), 3, "三檔都必須有 outcome，總數 = 迴圈前的清單長度")
        by_id = dict((e.item_key, e.outcome) for e in tracked)
        self.assertEqual(by_id["2382"], FETCH_FAILED)
        self.assertEqual(by_id["2330"], OK)
        self.assertEqual(by_id["6488"], OK)
        self.assertIn("simulated fetch failure",
                      [e.detail for e in tracked if e.outcome == FETCH_FAILED][0])


class TpexStockPricesComeFromCandidatePrices(unittest.TestCase):
    """UG-G2-SB7 (iii)：上櫃標的的 `stock_prices` 改由 `candidate_prices` 供應。

    **為什麼**：舊版逐股路徑曾先試 `STOCK_DAY`、抓不到才落 yfinance，
    而 `STOCK_DAY` 不供應上櫃 —— **上櫃標的每一次都走 yfinance**（提案 §0.1a）。
    批次階段已把上櫃全市場寫進 `candidate_prices`，**同一份資料再抓一次沒有道理**。

    ⚠ **這不會讓 yfinance 的 DEC-032 問題消失，只會把它縮到 NVDA 一條路徑**
    （複查方 2026-09-04 自我更正）。

    ⚠⚠ **`UG-G3-SB2a` 方案 B（2026-09-10）**：TWSE 逐股路徑後來也比照同一
    邏輯，改為複製 `candidate_prices`（`run_twse_pipeline_from_candidate_prices`，
    與本類別測的 `run_tpex_pipeline_from_candidate_prices` 同一份實作，
    兩個名字）——本類別的測試維持只用 TPEX 案例，不重複。
    """

    def _manager(self, mep):
        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            return mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

    # ---- 要求 1：順序 ----
    def test_batch_stage_runs_before_per_stock_stage(self):
        """**批次階段必須在逐股階段之前。**

        (iii) 使逐股迴圈**依賴批次已先跑過該日**。
        目前的順序是對的，**但那是巧合造成的正確，不是被釘住的正確**
        （複查方 2026-09-04 要求 1）。

        **什麼輸入會讓它 FAIL**：把批次那一段移到迴圈之後。
        """
        import main_etl_pipeline as mep
        manager = self._manager(mep)
        order = []

        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = []
        _one_day_ago = mep.previous_business_day() - _dt.timedelta(days=1)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _one_day_ago, "tpex": _one_day_ago}
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _one_day_ago,
            "price_max_date": _one_day_ago,
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：run_all_daily_tasks() 探索段新增 fetch_last_discovery_probed_date()
        # 查詢與 run_discovery() 回傳值解包——本檔原未設定，屬與 §0.5 #30
        # fetch_feature_lag() 同一機制的必然連帶影響（見 test_daily_hook_wiring.py
        # 同型註解），僅補 mock，不改動任何既有斷言。None 保留原本每次都會探索的
        # 既有行為；("OK", None) 避免 unpack 崩潰。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        # UG-G2-SB7 A 輪：`run_ptt_pipeline` 現在回傳 outcome（OK／NO_DATA），
        # **mock 必須符合那個契約** —— 回傳 MagicMock 會被 RunLogEntry 的窮舉擋下。
        # ⚠ 這是 §0.5 #17 的第四次表現：改動 `run_all_daily_tasks` 的契約時，
        #   需要編輯不測試它的檔案。**耦合才是缺陷，mock 不完整只是表現形式。**
        manager.run_ptt_pipeline = MagicMock(return_value="OK")
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_price_batch = MagicMock(
            side_effect=lambda *a, **k: order.append("batch") or {
                "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
                "total": 2, "outcomes_by_item": {"twse": "OK", "tpex": "OK"}})
        # `UG-G3-SB2a` 方案 B：呼叫端現在會採用回傳值，side_effect 必須明確
        # 回傳合法 outcome（"OK"），不能只回傳 `order.append()` 的 `None`。
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(
            side_effect=lambda *a, **k: (order.append("per_stock"), "OK")[1])
        with patch.object(mep.ETLPipelineManager, "_run_log_writer",
                          lambda self: None):
            manager.run_all_daily_tasks()

        self.assertEqual(order, ["batch", "per_stock"],
                         "逐股階段依賴批次已先跑過該日 —— 順序不得顛倒")

    # ---- 要求 2：批次失敗時不得靜默略過 ----
    def test_tpex_not_silently_skipped_when_batch_failed(self):
        """**known-FAIL**：批次失敗 ⇒ `candidate_prices` 無列 ⇒ 若靜默 return，
        該標的就長得像「那天沒資料」（§7.1）。

        本測試要求它 **raise**，讓呼叫端記為 `FETCH_FAILED`。
        """
        import datetime as dt
        import main_etl_pipeline as mep
        import pandas as pd
        from src.loaders.etl_run_log import FETCH_FAILED, NO_DATA, OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame()

        with self.assertRaises(RuntimeError) as ctx:
            manager.run_tpex_pipeline_from_candidate_prices(
                "6488", dt.date(2026, 9, 3), batch_outcome=FETCH_FAILED)
        self.assertIn("不是「那天沒有資料」", str(ctx.exception))
        self.assertEqual(manager.db_writer.upsert_to_stock_prices.call_count, 0)

        # 對照：批次 OK 而該股無列 —— 那才是真的 NO_DATA
        self.assertEqual(
            manager.run_tpex_pipeline_from_candidate_prices(
                "6488", dt.date(2026, 9, 3), batch_outcome=OK),
            NO_DATA)

    def test_refused_batch_also_prevents_silent_skip(self):
        """批次被拒（`REFUSED`）時同樣不得靜默略過 —— `batch_outcomes` 會是空的。"""
        import datetime as dt
        import main_etl_pipeline as mep
        import pandas as pd

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame()
        with self.assertRaises(RuntimeError):
            manager.run_tpex_pipeline_from_candidate_prices(
                "6488", dt.date(2026, 9, 3), batch_outcome=None)

    # ---- 要求 3：欄位對映不擴充 schema ----
    def test_only_columns_stock_prices_already_has(self):
        """**`turnover_amount` 不得被帶過去** —— `stock_prices` 沒有那一欄。

        決策點 2 的邊界是「不擴充 `stock_prices` 的 schema」。
        順手加欄位會讓 RISK-022 面向一的處置範圍在無人裁決的情況下變大。

        **什麼輸入會讓它 FAIL**：把 `SELECT *` 或多選一欄寫進查詢。

        ⚠⚠ **2026-09-07 修訂（PRE-G3-03 DP1）**：`source` 原本在禁止清單裡，
        理由逐字是「不在 `stock_prices` 的欄位裡」。**那個前提已經改變** ——
        migration 009 加了該欄，且 PO 於 2026-09-07 裁決 DP1。

        > **這一項當時擋下了正確的東西**：本次接線第一次跑全套時它就 FAIL，
        > 因為「在無人裁決的情況下擴充 schema」正是它要防的事。
        > **現在有人裁決了，所以前提消失，不是守衛失效。**

        **同時改掉它的形狀**：原本比對一份**硬編清單**，
        而硬編清單正是這次必須手動修改的原因。
        改為與 `DBWriter.STOCK_PRICE_COLUMNS`（寫入契約的唯一權威）逐欄比對 ——
        **日後寫入契約增減欄位，本項自動跟上，不需要記得改。**
        """
        import main_etl_pipeline as mep
        from src.loaders.db_writer import DBWriter
        sql = mep.ETLPipelineManager.SELECT_CANDIDATE_FOR_STOCK_PRICES

        # SELECT 撈的欄位集合，必須**恰好等於**寫入契約的欄位集合。
        select_body = sql.split("FROM")[0]
        picked = {c.strip() for c in select_body.replace("SELECT", "").split(",")
                  if c.strip()}
        self.assertEqual(
            picked, set(DBWriter.STOCK_PRICE_COLUMNS),
            "SELECT 的欄位與 stock_prices 寫入契約不一致；"
            "多撈等於擴充 schema，少撈等於寫入端拿不到必要欄位")

        # 讀得懂的保險：這些是 candidate_prices 獨有、stock_prices 沒有的欄位。
        for forbidden in ("turnover_amount", "security_name",
                          "pe_ratio", "best_bid", "best_ask", "transactions",
                          "SELECT *"):
            self.assertNotIn(forbidden, sql,
                             "%s 不在 stock_prices 的欄位裡；"
                             "帶過去等於在無人裁決的情況下擴充 schema" % forbidden)

    def test_tpex_route_does_not_use_yfinance(self):
        """(iii) 的重點：上櫃不再落 yfinance 備援。

        **TwseScraper 去留裁決（PO 2026-09-12）後訂正**：不再手動塞
        `manager.twse_scraper` 這個結構上不可能失敗的斷言對象（見
        `test_v4_batch_path_never_calls_per_stock_fetch` 同一訂正的完整理由），
        改斷言屬性／類別根本不存在。
        """
        import datetime as dt
        import main_etl_pipeline as mep
        import pandas as pd
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame(
            [{"stock_id": "6488", "trade_date": dt.date(2026, 9, 3),
              "open_price": 1, "high_price": 2, "low_price": 1,
              "close_price": 2, "volume": 10}])
        manager.yf_api = MagicMock()

        result = manager.run_tpex_pipeline_from_candidate_prices(
            "6488", dt.date(2026, 9, 3), batch_outcome=OK)

        self.assertEqual(result, OK)
        self.assertEqual(manager.yf_api.fetch_yfinance_data.call_count, 0)
        self.assertFalse(hasattr(manager, "twse_scraper"))
        self.assertFalse(hasattr(mep, "TwseScraper"))
        self.assertEqual(manager.db_writer.upsert_to_stock_prices.call_count, 1)


class RefusalMustNotBeDowngradedToFetchFailed(unittest.TestCase):
    """**複查方 2026-09-04 第三節**：`REFUSED` 的資訊不得在傳遞途中被丟掉。

    `run_price_batch` 算對了 —— 被拒時 `counts["outcomes_by_item"]` 含
    `{"tpex": "REFUSED"}`，run log 也寫進去了。**然後 raise 把整個 counts 丟掉**，
    於是逐股階段拿到空字典，把 6488 記成 `FETCH_FAILED`。

    > 我當初把 `ServiceRefusedError` 與 `FetchFailedError` 分成兩個型別，理由是
    > 「兩者處置完全相反，**合成同一個型別，呼叫端就分不出來了**」。
    > **那句話在這裡逐字成立，只是換了一層** ——
    > 型別上分開了，**outcome 欄上又合回去**。

    而 `FETCH_FAILED` 對 6488 是**雙重誤述**：(iii) 之後那條路徑**根本不 fetch**
    （它從 `candidate_prices` 讀），而失敗的原因是**上游被拒**，不是取數失敗。

    **`etl_run_log` 的 CHECK 允許四態，而逐股階段當時只產得出三態** ——
    **第四態在例外路徑上遺失了。**
    """

    def _manager(self, mep):
        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            return mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

    def test_refused_batch_records_refused_for_tpex_stock(self):
        """**known-FAIL**：現行程式碼會把 6488 記成 `FETCH_FAILED`。

        正確答案是 `REFUSED` —— **那個為此存在的第四態要被用上**。
        """
        import main_etl_pipeline as mep
        import pandas as pd
        from src.extractors.market_report_fetcher import ServiceRefusedError
        from src.loaders.etl_run_log import FETCH_FAILED, REFUSED

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "6488", "market": "TPEX"}]
        manager.db_writer.fetch_active_keywords.return_value = []
        manager.db_writer.fetch_data.return_value = pd.DataFrame()
        _one_day_ago = mep.previous_business_day() - _dt.timedelta(days=1)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _one_day_ago, "tpex": _one_day_ago}
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _one_day_ago,
            "price_max_date": _one_day_ago,
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：run_all_daily_tasks() 探索段新增 fetch_last_discovery_probed_date()
        # 查詢與 run_discovery() 回傳值解包——本檔原未設定，屬與 §0.5 #30
        # fetch_feature_lag() 同一機制的必然連帶影響（見 test_daily_hook_wiring.py
        # 同型註解），僅補 mock，不改動任何既有斷言。None 保留原本每次都會探索的
        # 既有行為；("OK", None) 避免 unpack 崩潰。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        # UG-G2-SB7 A 輪：`run_ptt_pipeline` 現在回傳 outcome（OK／NO_DATA），
        # **mock 必須符合那個契約** —— 回傳 MagicMock 會被 RunLogEntry 的窮舉擋下。
        # ⚠ 這是 §0.5 #17 的第四次表現：改動 `run_all_daily_tasks` 的契約時，
        #   需要編輯不測試它的檔案。**耦合才是缺陷，mock 不完整只是表現形式。**
        manager.run_ptt_pipeline = MagicMock(return_value="OK")
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()

        def refused(*a, **k):
            raise ServiceRefusedError(
                "HTTP 429（服務拒絕）",
                outcomes_by_item={"twse": "OK", "tpex": REFUSED})

        manager.run_price_batch = MagicMock(side_effect=refused)
        writer = MagicMock()
        with patch.object(mep.ETLPipelineManager, "_run_log_writer",
                          lambda self: writer):
            with self.assertRaises(ServiceRefusedError):
                manager.run_all_daily_tasks()

        tracked = [e for call in writer.write.call_args_list
                   for e in call.args[0]
                   if e.source == mep.SOURCE_TRACKED_DAILY]
        self.assertEqual(len(tracked), 1)
        self.assertEqual(
            tracked[0].outcome, REFUSED,
            "上游被拒時，逐股階段必須記 REFUSED —— "
            "記成 FETCH_FAILED 是雙重誤述：(iii) 之後該路徑根本不 fetch，"
            "而失敗原因是上游被拒")
        self.assertNotEqual(tracked[0].outcome, FETCH_FAILED)

    def test_service_refused_error_carries_the_outcomes(self):
        """例外必須帶著資訊過去，否則呼叫端只能猜。"""
        from src.extractors.market_report_fetcher import ServiceRefusedError
        exc = ServiceRefusedError("HTTP 429", outcomes_by_item={"tpex": "REFUSED"})
        self.assertEqual(exc.outcomes_by_item, {"tpex": "REFUSED"})
        # 不帶時預設為空 dict，**不是 None** —— 呼叫端不必再分辨一種形態
        self.assertEqual(ServiceRefusedError("x").outcomes_by_item, {})

    def test_missing_outcomes_is_an_explicit_error_not_a_silent_fallback(self):
        """空字典曾同時代表三件事，**修好被拒那一項後，其餘兩項應明確地不可能**。

        `run_price_batch` 回傳缺少 `outcomes_by_item` → **raise 明確的內部錯誤**，
        而不是與「被拒」共用同一個表示。
        """
        import main_etl_pipeline as mep
        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = []
        _one_day_ago = mep.previous_business_day() - _dt.timedelta(days=1)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _one_day_ago, "tpex": _one_day_ago}
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _one_day_ago,
            "price_max_date": _one_day_ago,
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：run_all_daily_tasks() 探索段新增 fetch_last_discovery_probed_date()
        # 查詢與 run_discovery() 回傳值解包——本檔原未設定，屬與 §0.5 #30
        # fetch_feature_lag() 同一機制的必然連帶影響（見 test_daily_hook_wiring.py
        # 同型註解），僅補 mock，不改動任何既有斷言。None 保留原本每次都會探索的
        # 既有行為；("OK", None) 避免 unpack 崩潰。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        # UG-G2-SB7 A 輪：`run_ptt_pipeline` 現在回傳 outcome（OK／NO_DATA），
        # **mock 必須符合那個契約** —— 回傳 MagicMock 會被 RunLogEntry 的窮舉擋下。
        # ⚠ 這是 §0.5 #17 的第四次表現：改動 `run_all_daily_tasks` 的契約時，
        #   需要編輯不測試它的檔案。**耦合才是缺陷，mock 不完整只是表現形式。**
        manager.run_ptt_pipeline = MagicMock(return_value="OK")
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_price_batch = MagicMock(return_value={"OK": 2, "total": 2})
        with patch.object(mep.ETLPipelineManager, "_run_log_writer",
                          lambda self: None):
            with self.assertRaises(RuntimeError) as ctx:
                manager.run_all_daily_tasks()
        self.assertIn("outcomes_by_item", str(ctx.exception))


class FieldPatternsMustMatchTheMarket(unittest.TestCase):
    """**2026-09-04 STEP 1 抓到的缺陷的回歸守衛。**

    建立 `market_report_table` 時我把 `FIELD_PATTERNS`（TWSE）搬了過來，
    **卻把 `TPEX_FIELD_PATTERNS` 留在 `scripts/verify/tpex_endpoint_check.py`**。
    於是生產路徑用 TWSE 的欄名樣式去對 TPEx 的表 ——
    表**找到了**（`tables[0].fields/data`），**只是欄名沒對上**，
    `find_market_table` 回 `None`，最終呈現為 `FETCH_FAILED`。

    > **搬一半比不搬更危險**：不搬時兩邊各自完整；
    > 搬一半時生產端**看起來有**那個能力，實際用的是另一個市場的樣式。

    欄名逐字取自 `tests/test_tpex_market_report.py` 的實測 fixture。
    """

    TPEX_FIELDS = ['代號', '名稱', '收盤 ', '漲跌', '開盤 ', '最高 ', '最低',
                   '成交股數  ', ' 成交金額(元)', ' 成交筆數 ', '最後買價',
                   '最後買量<br>(張數)', '最後賣價', '最後賣量<br>(張數)',
                   '發行股數 ', '次日漲停價 ', '次日跌停價']
    TPEX_ROWS = [['6488', '環球晶', '935.00', '-58.00', '990.00', '992.00',
                  '930.00', '1,000', '935,000', '10', '934.00', '1',
                  '936.00', '1', '435,000,000', '1,028.00', '842.00']]

    def _payload(self):
        return {"tables": [{"title": "上櫃股票每日收盤行情(不含定價)",
                            "fields": self.TPEX_FIELDS,
                            "data": self.TPEX_ROWS}]}

    def test_tpex_patterns_locate_the_table(self):
        from src.extractors.market_report_table import (
            TPEX_FIELD_PATTERNS, _find_market_table)
        fields, rows, diag = _find_market_table(self._payload(), TPEX_FIELD_PATTERNS)
        self.assertIsNotNone(fields, "TPEx 樣式必須對得上 TPEx 的欄名；診斷：%s" % diag)
        self.assertEqual(len(rows), 1)

    def test_known_fail_twse_patterns_do_not_locate_the_tpex_table(self):
        """**known-FAIL**：用錯市場的樣式 → 表找不到。

        **這正是 2026-09-04 實際發生的事**，且它的輸出
        （`FETCH_FAILED` + 診斷）與「端點沒有資料」長得不一樣 ——
        **診斷裡的 `table_titles` 有值而 `shape` 為 None，就是這個形態的指紋。**
        """
        from src.extractors.market_report_table import _find_market_table
        fields, rows, diag = _find_market_table(self._payload())   # TWSE 樣式
        self.assertIsNone(fields)
        self.assertIsNone(diag.get("shape"))
        self.assertEqual(diag.get("table_titles"), ["上櫃股票每日收盤行情(不含定價)"],
                         "表是找到的——分不出來的話會誤判成端點問題")

    def test_fetcher_passes_market_specific_patterns(self):
        """取數器必須依市場傳樣式，而不是永遠用預設。"""
        import datetime as dt
        from unittest.mock import patch as _patch
        import src.extractors.market_report_fetcher as mrf

        seen = {}

        def spy(payload, patterns=None, **kwargs):
            seen["patterns_is_tpex"] = patterns is mrf.TPEX_FIELD_PATTERNS
            return self.TPEX_FIELDS, self.TPEX_ROWS, {"shape": "tables[0]"}

        with _patch.object(mrf, "_fetch_payload", lambda *a, **k: self._payload()), \
             _patch.object(mrf, "_find_market_table", spy), \
             _patch.object(mrf, "_sleep", lambda s: None):
            mrf.fetch_market_report("tpex", dt.date(2026, 8, 21), throttle=False)
        self.assertTrue(seen.get("patterns_is_tpex"),
                        "TPEx 必須傳 TPEX_FIELD_PATTERNS")


if __name__ == "__main__":
    unittest.main()
