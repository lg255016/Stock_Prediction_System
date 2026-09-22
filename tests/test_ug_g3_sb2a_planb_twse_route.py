# -*- coding: utf-8 -*-
"""`UG-G3-SB2a` 方案 B：TWSE 逐股路徑改走 `candidate_prices` 複製（紅色測試）。

================================================================================
本檔在實作之前寫，依 `UG-G3-SB2a` Gate A 提案（`f668503`）§3.1 條件 (a)：
「紅色測試先行、綠色實作後行，各自獨立 commit，不得併成一個 red+green commit」
================================================================================

PO 核准方案 B（2026-09-10）：`main_etl_pipeline.py` 的 TWSE 逐股路徑
（現行 `run_twse_pipeline`，自建爬蟲 `STOCK_DAY` 優先、失敗落 yfinance
還原價備援）改為比照既有的 `run_tpex_pipeline_from_candidate_prices`
（`main_etl_pipeline.py:260-309`），複製當日已由批次階段（`UG-G2-SB7`）
寫入的 `candidate_prices` 列，不再觸網。

**本檔對應提案 §6「方案 B 紅色測試清單」五項（#3 拆兩案，共六個測試）**：

| 提案項次 | 測試 |
|---|---|
| 1 | `test_twse_route_copies_candidate_prices_row_verbatim` |
| 2 | `test_source_domain_converges_for_twse_route_us_route_unaffected` |
| 3(i) | `test_twse_batch_ok_no_row_returns_no_data_without_yfinance` |
| 3(ii) | `test_twse_batch_failed_no_row_raises_with_upstream_outcome_without_yfinance` |
| 4 | `test_run_twse_pipeline_removed_no_residual_references` |
| 5 | `test_source_check_constraint_domain_not_narrowed` |
| （迴圈接線，`sps_project_reviewer` 2026-09-10 複核追加） | `TwsePerStockLoopRoutesToCandidatePrices` 三個測試 |

**設計決策（本檔動工前先定案，非既有裁決）**：新函式命名為
`run_twse_pipeline_from_candidate_prices`，與 `run_tpex_pipeline_from_candidate_prices`
同名式樣、同簽章（`stock_id, trade_date, batch_outcome=None`）、同回傳契約
（`OK`／`NO_DATA`，或帶 `upstream_outcome` 的例外）——**完全沿用**該函式已
證明過的批次 outcome 三態歸因語意（提案 §3.1 條件 (b)），不重新發明。
此設計決策由本次紅色測試 commit 提出，待 PO 確認測試為真實 RED 後生效，
實作 commit 依此進行。

================================================================================
⚠ 測試 5（CHECK 約束未收窄）的性質與其餘五項不同，如實揭露
================================================================================
測試 1～4 要求的是**尚不存在的新行為**，在未修改的 `main_etl_pipeline.py`
上執行**必然 FAIL**（`AttributeError` 或呼叫次數不符）。

**測試 5 不是這樣**：它斷言的是「本專案的 migration 對 `chk_stock_prices_source`
的定義仍含 `twse_stock_day`／`yfinance_auto_adjusted`」——這件事**現在就是真的**
（方案 B 尚未觸碰 schema），因此**測試 5 對未修改的程式碼會 PASS，不是 RED**。
這不是本檔的缺陷，是它本質上是一個**回歸防護**（防止未來有人以新增 migration
的方式收窄值域——`DB_MIGRATION_PLAN.md` §5.2 規定已套用的 migration 不可改，
**收窄的真實路徑是新增一個 migration 重寫該約束**，故測試 5 掃描
`database/migrations/*.sql` 全部檔案，不只 009），不是一個「新功能尚未實作」
的紅燈。

================================================================================
⚠ known-FAIL 案例的正確做法（`sps_project_reviewer` 2026-09-10 複核修正）
================================================================================
**`AttributeError`（函式不存在）本身是弱紅燈**——它只證明「函式還不存在」，
證明不了斷言抓得到「錯的實作」。同理，回歸防護類測試的 known-FAIL **必須
實際跑這個測試方法本體**（monkeypatch／暫存目錄／暫改路徑皆可），
**不是在測試檔外重寫一段相似邏輯讓它失敗**——後者證明的是「這段邏輯看起來
正確」，不是「這個測試會擋下錯的實作」，兩者是不同的宣稱。本檔測試 5 與
迴圈接線測試的 known-FAIL 證據見送審報告，做法為 monkeypatch 本檔的類別
屬性／實際呼叫測試方法，不修改任何 repo 內的真實檔案。
"""
import datetime as _dt
import glob
import os
import re
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_THIS_FILE = os.path.abspath(__file__)


class TwseRouteCopiesFromCandidatePrices(unittest.TestCase):
    """提案 §6 項次 1／2／3(i)／3(ii)：新函式 `run_twse_pipeline_from_candidate_prices`
    的行為契約。直接呼叫該函式——**它現在不存在，呼叫即 `AttributeError`**。
    """

    def _manager(self, mep):
        from unittest.mock import patch
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

    # ---- 項次 1：複製邏輯正確性 ----
    def test_twse_route_copies_candidate_prices_row_verbatim(self):
        """`candidate_prices` 當日有列時，`stock_prices` 寫入值須與來源逐欄一致，
        `source` 沿用原值（`twse_mi_index`），且**不觸網**（爬蟲／yfinance 皆不呼叫）。

        **什麼輸入會讓它 FAIL**：若複製路徑漏欄、改值，或仍呼叫
        `twse_scraper.fetch_twse_stock_data`／`yf_api.fetch_yfinance_data`。
        """
        import pandas as pd
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        candidate_row = pd.DataFrame([{
            "stock_id": "2330", "trade_date": _dt.date(2026, 9, 3),
            "open_price": 600.0, "high_price": 605.0, "low_price": 598.0,
            "close_price": 603.0, "volume": 12345, "source": "twse_mi_index",
        }])
        manager.db_writer.fetch_data.return_value = candidate_row
        manager.yf_api = MagicMock()

        result = manager.run_twse_pipeline_from_candidate_prices(
            "2330", _dt.date(2026, 9, 3), batch_outcome=OK)

        self.assertEqual(result, OK)
        # TwseScraper 去留裁決（PO 2026-09-12）後訂正：不再手動塞
        # `manager.twse_scraper`（結構上不可能失敗的斷言，見
        # test_batch_etl_boundary.py 同一訂正的完整理由），改斷言
        # 屬性／類別根本不存在。
        self.assertFalse(hasattr(manager, "twse_scraper"))
        self.assertFalse(hasattr(mep, "TwseScraper"))
        self.assertEqual(manager.yf_api.fetch_yfinance_data.call_count, 0)
        self.assertEqual(manager.db_writer.upsert_to_stock_prices.call_count, 1)
        written = manager.db_writer.upsert_to_stock_prices.call_args[0][0]
        self.assertEqual(written["source"].iloc[0], "twse_mi_index")
        self.assertEqual(written["close_price"].iloc[0], 603.0)
        self.assertEqual(written["volume"].iloc[0], 12345)

    # ---- 項次 2：source 值域收斂（限定台股逐股路徑）＋ NVDA 不受影響 ----
    def test_source_domain_converges_for_twse_route_us_route_unaffected(self):
        """新寫入列的 `source` 只會是 `twse_mi_index`／`tpex_daily_quotes`
        （由 `candidate_prices` 原值帶入），不再產生 `twse_stock_day`。

        同時斷言 `run_us_stock_pipeline`（NVDA）**不在方案 B 範圍內、不受影響**——
        它是獨立的美股路徑，本方案只動 TWSE／TPEX 逐股路徑。
        """
        import pandas as pd
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame([{
            "stock_id": "2382", "trade_date": _dt.date(2026, 9, 3),
            "open_price": 100.0, "high_price": 101.0, "low_price": 99.0,
            "close_price": 100.5, "volume": 500, "source": "twse_mi_index",
        }])

        manager.run_twse_pipeline_from_candidate_prices(
            "2382", _dt.date(2026, 9, 3), batch_outcome=OK)
        written = manager.db_writer.upsert_to_stock_prices.call_args[0][0]
        self.assertIn(written["source"].iloc[0],
                       ("twse_mi_index", "tpex_daily_quotes"))
        self.assertNotEqual(written["source"].iloc[0], "twse_stock_day")

        # NVDA／run_us_stock_pipeline 不受影響：獨立驗證其寫入邏輯與 source 未變。
        manager.yf_api = MagicMock()
        manager.yf_api.fetch_yfinance_data.return_value = pd.DataFrame(
            [{"date": _dt.date(2026, 9, 3), "close": 120.0}])
        manager.cleaner = MagicMock()
        manager.cleaner.clean_yfinance_stock_data.return_value = pd.DataFrame(
            [{"stock_id": "NVDA", "trade_date": _dt.date(2026, 9, 3),
              "close_price": 120.0}])
        manager.db_writer.reset_mock()
        manager.run_us_stock_pipeline("NVDA", period="3mo")
        us_written = manager.db_writer.upsert_to_stock_prices.call_args[0][0]
        self.assertEqual(us_written["source"].iloc[0], "yfinance_auto_adjusted")

    # ---- 項次 3(i)：批次 OK 但無列 → NO_DATA，不落 yfinance ----
    def test_twse_batch_ok_no_row_returns_no_data_without_yfinance(self):
        """完全沿用 `run_tpex_pipeline_from_candidate_prices` 既有語意：
        批次 `OK` 但當日該股無列 → `NO_DATA`（真的沒有資料，非失敗）。

        **核心新增條件**：即使沒有列，也**不得**落回 yfinance 補值。
        """
        import pandas as pd
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import NO_DATA, OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame()
        manager.yf_api = MagicMock()

        result = manager.run_twse_pipeline_from_candidate_prices(
            "2330", _dt.date(2026, 9, 3), batch_outcome=OK)

        self.assertEqual(result, NO_DATA)
        self.assertEqual(manager.yf_api.fetch_yfinance_data.call_count, 0)
        # TwseScraper 去留裁決（PO 2026-09-12）後訂正，理由同本檔其他訂正處。
        self.assertFalse(hasattr(manager, "twse_scraper"))
        self.assertFalse(hasattr(mep, "TwseScraper"))
        self.assertEqual(manager.db_writer.upsert_to_stock_prices.call_count, 0)

    # ---- 項次 3(ii)：批次未成功且無列 → 例外帶上游 outcome，不落 yfinance ----
    def test_twse_batch_failed_no_row_raises_with_upstream_outcome_without_yfinance(self):
        """批次 `REFUSED`／`FETCH_FAILED` 且當日該股無列 → 拋例外並帶上游 outcome
        （呼叫端據此記為 `REFUSED` 或 `FETCH_FAILED`，不得誤記為「那天沒資料」）。

        **核心新增條件**：拋例外前**不得**先落 yfinance 試補值。
        """
        import pandas as pd
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import FETCH_FAILED, REFUSED

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame()
        manager.yf_api = MagicMock()

        with self.assertRaises(RuntimeError) as ctx:
            manager.run_twse_pipeline_from_candidate_prices(
                "2330", _dt.date(2026, 9, 3), batch_outcome=FETCH_FAILED)
        self.assertEqual(getattr(ctx.exception, "upstream_outcome", None),
                          FETCH_FAILED)
        self.assertEqual(manager.yf_api.fetch_yfinance_data.call_count, 0)

        with self.assertRaises(RuntimeError) as ctx2:
            manager.run_twse_pipeline_from_candidate_prices(
                "2330", _dt.date(2026, 9, 3), batch_outcome=REFUSED)
        self.assertEqual(getattr(ctx2.exception, "upstream_outcome", None),
                          REFUSED)
        self.assertEqual(manager.yf_api.fetch_yfinance_data.call_count, 0)
        # TwseScraper 去留裁決（PO 2026-09-12）後訂正，理由同本檔其他訂正處。
        self.assertFalse(hasattr(manager, "twse_scraper"))
        self.assertFalse(hasattr(mep, "TwseScraper"))


class RunTwsePipelineRemoved(unittest.TestCase):
    """提案 §6 項次 4：`run_twse_pipeline` 移除後，程式碼內零殘留引用。

    ⚠ 正規表示式用負向前瞻排除新函式 `run_twse_pipeline_from_candidate_prices`
    自身的名字，避免把新函式的存在誤判為舊函式的殘留引用。
    """

    _PATTERN = re.compile(r"run_twse_pipeline(?!_from_candidate_prices)")

    def test_run_twse_pipeline_removed_no_residual_references(self):
        hits = []
        for path in glob.glob(os.path.join(_REPO_ROOT, "**", "*.py"),
                               recursive=True):
            abspath = os.path.abspath(path)
            if abspath == _THIS_FILE:
                continue
            if (os.sep + ".git" + os.sep) in abspath:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if self._PATTERN.search(line):
                    hits.append("%s:%d" % (
                        os.path.relpath(path, _REPO_ROOT), lineno))
        self.assertEqual(
            hits, [],
            "run_twse_pipeline（不含 _from_candidate_prices 後綴）"
            "不得再出現於任何 .py 檔案；找到殘留：%s" % hits)

    def test_run_us_stock_pipeline_not_accidentally_removed(self):
        """條件 (c)：只刪 `run_twse_pipeline`，`run_us_stock_pipeline` 不動。

        本測試現在就會 PASS（`run_us_stock_pipeline` 尚未被動過）——
        它是**移除 `run_twse_pipeline` 這個動作本身的回歸防護**，
        防止實作時誤刪或誤改到相鄰的美股路徑。
        """
        import main_etl_pipeline as mep
        self.assertTrue(
            hasattr(mep.ETLPipelineManager, "run_us_stock_pipeline"),
            "run_us_stock_pipeline 不得被移除或改名")


class SourceCheckConstraintDomainNotNarrowed(unittest.TestCase):
    """提案 §6 項次 5：`stock_prices.source` 的 CHECK 約束值域不得收窄。

    ⚠ **這是回歸防護，不是「新功能尚未實作」的紅燈**——
    見本檔頂端說明。對未修改的 migrations 執行，本測試現在就會 PASS。

    ⚠⚠ **2026-09-10 複核修正（`sps_project_reviewer`）**：初版只讀
    `009_stock_prices_source.sql` 一份檔案——**結構性盲點**：已套用的
    migration 依 `DB_MIGRATION_PLAN.md` §5.2 不可改，收窄值域的真實路徑是
    **新增一個 migration 重寫 `chk_stock_prices_source`**，那條路初版完全
    看不見（「什麼輸入會讓它 FAIL？」答案只有「去改一個不該改的檔」，
    違反 `CLAUDE.md` §9A.1）。**改為掃描 `database/migrations/*.sql`
    全部檔案**：凡找到 `chk_stock_prices_source` 的 `CHECK (... IN (...))`
    定義區塊，每一個都必須含兩個既有歷史值；**一個區塊都找不到**
    （約束定義本身從所有 migration 消失，也是一種收窄）**同樣 FAIL**。
    """

    _MIGRATIONS_DIR = os.path.join(_REPO_ROOT, "database", "migrations")
    _BLOCK_PATTERN = re.compile(
        r"chk_stock_prices_source.*?CHECK\s*\([^)]*?IN\s*\((.*?)\)\s*\)",
        re.DOTALL | re.IGNORECASE)

    def _find_domain_blocks(self):
        """回傳 `[(相對路徑, CHECK...IN(...) 區塊內容), ...]`。

        設計成獨立方法而非寫死在測試方法內——**這是 known-FAIL 的掛勾**：
        對真實 migration 目錄跑會 PASS；把 `_MIGRATIONS_DIR` monkeypatch 到
        一個暫存目錄（放一份被收窄的假 migration）後再跑**同一個測試方法**，
        會 FAIL。不是在測試檔外重寫一段相似邏輯。
        """
        blocks = []
        for path in sorted(glob.glob(os.path.join(self._MIGRATIONS_DIR, "*.sql"))):
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            for m in self._BLOCK_PATTERN.finditer(sql):
                blocks.append((os.path.relpath(path, _REPO_ROOT), m.group(1)))
        return blocks

    def test_source_check_constraint_domain_not_narrowed(self):
        blocks = self._find_domain_blocks()
        self.assertTrue(
            blocks,
            "所有 migration 檔皆找不到 chk_stock_prices_source 的 "
            "CHECK (... IN (...)) 定義區塊——約束定義本身消失也是一種收窄")
        for path, domain_block in blocks:
            for legacy_value in ("twse_stock_day", "yfinance_auto_adjusted"):
                self.assertIn(
                    "'%s'" % legacy_value, domain_block,
                    "%s 的 chk_stock_prices_source 定義未含既有歷史值 %s"
                    "——不得收窄值域" % (path, legacy_value))
            for current_value in ("twse_mi_index", "tpex_daily_quotes"):
                self.assertIn("'%s'" % current_value, domain_block,
                              "%s 的定義未含現行值 %s" % (path, current_value))


class TwsePerStockLoopRoutesToCandidatePrices(unittest.TestCase):
    """迴圈接線層級驗證（`sps_project_reviewer` 2026-09-10 複核追加）。

    ⚠ **只直接呼叫新函式不夠**：那證明不了 `run_all_daily_tasks()` 的
    逐股迴圈真的把 TWSE 標的送過去、傳對了 `batch_outcome`，也證明不了
    `run_twse_pipeline`（舊函式）已經不再被迴圈呼叫。「新函式寫好了但
    `main_etl_pipeline.py:697` 仍呼叫舊函式」「傳成
    `batch_outcomes.get('tpex')`」「回傳的 `NO_DATA` 沒記進 run log」——
    這些缺陷只直接呼叫新函式的測試（`TwseRouteCopiesFromCandidatePrices`）
    完全抓不到，比照 `test_batch_etl_boundary.py` 的
    `test_tpex_route_does_not_use_yfinance`／
    `test_refused_batch_records_refused_for_tpex_stock` 補上這一層。
    """

    def _manager(self, mep):
        from unittest.mock import patch
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

    def _run(self, mep, manager, stocks, outcomes_by_item,
              twse_candidate_return=None, twse_candidate_side_effect=None):
        from unittest.mock import patch
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
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_pipeline = MagicMock(return_value="OK")
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": outcomes_by_item})
        # 新函式：若實作缺席，這個 mock 屬性不會被迴圈呼叫到——call_count 停在 0。
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(
            return_value=twse_candidate_return,
            side_effect=twse_candidate_side_effect)
        # 舊函式：若迴圈仍呼叫它，這裡會露餡（call_count > 0）。
        manager.run_twse_pipeline = MagicMock()
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(
            return_value="OK")
        manager.run_us_stock_pipeline = MagicMock()
        manager.yf_api = MagicMock()
        writer = MagicMock()
        with patch.object(mep.ETLPipelineManager, "_run_log_writer",
                          lambda self: writer):
            manager.run_all_daily_tasks()
        return writer

    def test_twse_stock_routed_to_new_function_with_correct_batch_outcome(self):
        """(i) 新函式被呼叫一次，引數為 `(sid, batch_date, batch_outcome=…)`；
        (ii) 舊函式 `run_twse_pipeline` 零呼叫；(iii) `yf_api`／`twse_scraper` 零呼叫。

        **什麼輸入會讓它 FAIL**：迴圈仍走舊函式（現狀）、或新函式傳對了
        `stock_id` 卻傳錯 `batch_outcome`（例如寫成 `.get("tpex")`）。
        """
        import datetime as dt
        import main_etl_pipeline as mep

        manager = self._manager(mep)
        # ⚠ **twse／tpex 兩值刻意不同**（`sps_project_reviewer` 2026-09-10 複核指出）：
        # 若兩值相同（例如都是 "OK"），傳成 `.get("tpex")` 會巧合得到同一個值，
        # 下方 `batch_outcome` 斷言照樣通過——**抓不到「傳錯鍵」這個錯誤**。
        # 兩值不同時，傳錯鍵會得到 "REFUSED"，斷言才會真的 FAIL。
        writer = self._run(
            mep, manager, [{"stock_id": "2330", "market": "TWSE"}],
            outcomes_by_item={"twse": "OK", "tpex": "REFUSED"},
            twse_candidate_return="OK")

        self.assertEqual(
            manager.run_twse_pipeline_from_candidate_prices.call_count, 1,
            "TWSE 追蹤標的必須被送到新函式，而不是繼續走舊函式")
        self.assertEqual(manager.run_twse_pipeline.call_count, 0,
                         "舊函式 run_twse_pipeline 不得再被迴圈呼叫")
        args, kwargs = manager.run_twse_pipeline_from_candidate_prices.call_args
        self.assertEqual(args[0], "2330")
        self.assertIsInstance(args[1], dt.date,
                              "第二個位置引數應是 batch_date（date 物件），"
                              "不是舊呼叫用的 current_date_str（字串）")
        self.assertEqual(
            kwargs.get("batch_outcome"), "OK",
            "須傳 outcomes_by_item.get('twse')，不是 'tpex' 或漏傳"
            "——twse／tpex 兩值刻意不同，傳錯鍵會得到 'REFUSED'")
        self.assertEqual(manager.yf_api.fetch_yfinance_data.call_count, 0)
        # TwseScraper 去留裁決（PO 2026-09-12）後訂正，理由同本檔其他訂正處。
        self.assertFalse(hasattr(manager, "twse_scraper"))
        self.assertFalse(hasattr(mep, "TwseScraper"))
        del writer  # 本測試不檢查 run log 內容，僅呼叫層級

    def test_no_data_outcome_from_new_function_lands_in_run_log(self):
        """新函式回傳 `NO_DATA` 時，run log 對該股記的 outcome 必須是 `NO_DATA`
        （不是預設值 `OK`）——**驗證回傳值真的被迴圈採用，不是被丟棄**。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import NO_DATA

        manager = self._manager(mep)
        writer = self._run(
            mep, manager, [{"stock_id": "2330", "market": "TWSE"}],
            outcomes_by_item={"twse": "OK", "tpex": "OK"},
            twse_candidate_return=NO_DATA)

        tracked = [e for call in writer.write.call_args_list
                   for e in call.args[0]
                   if e.source == mep.SOURCE_TRACKED_DAILY]
        by_id = dict((e.item_key, e.outcome) for e in tracked)
        self.assertEqual(by_id.get("2330"), NO_DATA)

    def test_refused_upstream_outcome_from_new_function_lands_in_run_log(self):
        """新函式拋出帶 `upstream_outcome=REFUSED` 的例外時，run log 對該股
        記的 outcome 必須是 `REFUSED`，**不得被雙重誤述成 `FETCH_FAILED`**
        （同 `test_refused_batch_records_refused_for_tpex_stock` 的道理，
        換到 TWSE 路徑）。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import FETCH_FAILED, REFUSED

        def boom(*a, **k):
            exc = RuntimeError("批次被拒，candidate_prices 無列")
            exc.upstream_outcome = REFUSED
            raise exc

        manager = self._manager(mep)
        writer = self._run(
            mep, manager, [{"stock_id": "2330", "market": "TWSE"}],
            outcomes_by_item={"twse": "REFUSED", "tpex": "OK"},
            twse_candidate_side_effect=boom)

        tracked = [e for call in writer.write.call_args_list
                   for e in call.args[0]
                   if e.source == mep.SOURCE_TRACKED_DAILY]
        by_id = dict((e.item_key, e.outcome) for e in tracked)
        self.assertEqual(by_id.get("2330"), REFUSED)
        self.assertNotEqual(by_id.get("2330"), FETCH_FAILED)


if __name__ == "__main__":
    unittest.main()
