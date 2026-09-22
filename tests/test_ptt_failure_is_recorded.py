# -*- coding: utf-8 -*-
"""UG-G2-SB7 A 輪（§0.3 的鏈第 2 段）：PTT 來源不可達必須留下紀錄。

================================================================================
鏈的現況：四段修了一段
================================================================================
`UG-G2-SB7` 的 Gate A 找出一條完整的鏈，說明「一次 PTT 抓取失敗最終會呈現為
`source_status = SUCCESS_EMPTY` + `sentiment_mean = 0.5`」：

    鏈 1  逐股迴圈無 try/except              → 已修（接線那輪）
    鏈 2  main_etl_pipeline.py:285-287        → **本檔要修的**
    鏈 3  feature_aggregator.py:451-455 兩態  → B 輪
    鏈 4  feature_aggregator.py:441 fillna(0.5) → B 輪

**診斷完整、處置未做** —— 本檔是處置的第一段。

================================================================================
為什麼鏈 2 必須先修
================================================================================
`feature_aggregator.py:451` 的註解自己寫著：

> `SOURCE_DEGRADED`／`SOURCE_FAILED` 兩態依 Gate 0 契約
> **需 `UG-G2-SB2` 的 pipeline 例外傳播才可能產生**

**而鏈 2 正是那個「例外傳播」被 `print + return` 攔掉的地方。**

> **鏈 2 不修，鏈 3 改成四態也產不出第三、四態** ——
> 那會變成一個**永遠只走兩態的四態欄位**，比現在更糟：
> 現在至少誠實地只宣稱兩態。

================================================================================
現況（本檔撰寫時）
================================================================================
`main_etl_pipeline.py:285-287`：

    except PttSourceUnavailableError as e:
        print(f"[WARNING] PTT 來源不可達，跳過關鍵字 [{keyword}]：{e}")
        return

**失敗只被 `print`，沒有進入任何資料。** 而 `ptt_scraper.py:12-13` 的
例外類別 docstring 逐字寫著：

> 此例外必須被拋出，**呼叫端不得將其誤判為「查無資料」而回傳空 DataFrame**
> （`CLAUDE.md` §7.1：DB Error != Empty Result）。

**禁令就寫在被 catch 的那個類別上，而 pipeline 在兩個檔案之外做了它明文禁止的事。**

且關鍵字迴圈（`:527-528`）**完全沒有 try/except，也沒有任何 outcome 記錄** ——
與逐股迴圈修正前是同一個形狀。
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PttSourceFailureMustLeaveARecord(unittest.TestCase):
    """**known-FAIL**：來源不可達時該關鍵字必須有一筆 outcome，而非靜默 return。"""

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

    def _run(self, mep, manager, keywords, ptt_side_effect):
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = []
        manager.db_writer.fetch_active_keywords.return_value = keywords
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用）——本檔原未設定此 mock，Stage A 測試套件
        # 執行時發現 MagicMock 預設回傳值不支援 `>` 比較而 TypeError（不在 PO
        # 原先指名的既有四個測試檔之列，屬同一機制的必然連帶影響，僅補 mock，
        # 不改動任何既有斷言）。固定退化成 n_lag=1，等同修改前
        # tail_window=holding_period+1 的既有行為。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": None,
            "price_max_date": None,
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": {"twse": "OK", "tpex": "OK"}})
        # ⚠⚠ **接縫由 `run_ptt_pipeline` 改為 `scrape_ptt_board_pages`**
        # （UG-G2-SB7 第 5 項，2026-09-05）。每日任務不再逐關鍵字呼叫，
        # 而是**一次看板抓取**。
        #
        # **§0.5 #17 的第五次表現**，而且這次是最貴的一次：
        # 改動的是 `run_all_daily_tasks` 的取數方式，
        # 需要編輯的是三個**不測試取數方式**的測試檔。
        manager.ptt_scraper = MagicMock()
        manager.ptt_scraper.scrape_ptt_board_pages.side_effect = ptt_side_effect
        manager.cleaner = MagicMock()
        manager.backfill_ptt_comment_counts = MagicMock()
        writer = MagicMock()
        with patch.object(mep.ETLPipelineManager, "_run_log_writer",
                          lambda self: writer):
            manager.run_all_daily_tasks()
        return writer

    def test_unavailable_source_produces_a_fetch_failed_entry(self):
        """來源不可達 → **每一個關鍵字都要有 `FETCH_FAILED`**。

        **什麼輸入會讓它 FAIL**：`print` 之後 `return`（A 輪修正前的現況）——
        run log 裡不會有那些筆。

        ================================================================
        ⚠ 本測試在第 5 項改變了它斷言的東西 —— 這裡說明改了什麼
        ================================================================
        A 輪：三個關鍵字各一次搜尋，`廣達` 失敗而 `台積電`／`AI` 仍為 `OK`。
        第 5 項：**一次看板抓取供應全部關鍵字**，第一頁失敗時
        **我們對每一個關鍵字都一無所知** —— 三筆全部 `FETCH_FAILED`。

        > **逐關鍵字失敗隔離在批次模式下真的消失了，本測試照實記錄。**
        > 保留的是**性質**（失敗必須逐關鍵字留下紀錄、不得靜默）；
        > 消失的是**機制**（各自請求，因此互不影響）。

        **為什麼不用「失敗時回退逐關鍵字模式」把隔離救回來**：
        那等於在站方拒絕我們之後再送 25 個請求 ——
        **正是 DEC-032 硬停紀律要防的行為**。
        隔離的代價比它換到的東西貴。
        """
        import main_etl_pipeline as mep
        from src.extractors.ptt_scraper import PttSourceUnavailableError
        from src.loaders.etl_run_log import FETCH_FAILED

        def boom(*a, **k):
            raise PttSourceUnavailableError("PTT 完全不可達（模擬）")

        manager = self._manager(mep)
        writer = self._run(mep, manager, ["台積電", "廣達", "AI"], boom)

        ptt = [e for call in writer.write.call_args_list
               for e in call.args[0] if e.source == mep.SOURCE_PTT]
        self.assertEqual(len(ptt), 3,
                         "三個關鍵字都必須有 outcome —— "
                         "總數取自迴圈前的清單長度，不得由記錄反推")
        by_kw = dict((e.item_key, e.outcome) for e in ptt)
        for kw in ("台積電", "廣達", "AI"):
            self.assertEqual(by_kw[kw], FETCH_FAILED,
                             "來源不可達是 SOURCE_FAILED，**不是「查無資料」** —— "
                             "禁令就寫在 PttSourceUnavailableError 自己的 "
                             "docstring 上")

    def test_batch_failure_does_not_abort_the_run(self):
        """**取數失敗不得中止整個每日任務。**

        A 輪的同名測試釘的是「一個關鍵字失敗不中止其餘關鍵字」；
        批次模式下沒有「其餘關鍵字」可言，**但「不中止整個執行」仍然成立**，
        且仍然是那一版真正要保護的東西 —— 下游的 NLP 與特徵工程階段
        不該因為社群取數失敗而不跑。

        **什麼輸入會讓它 FAIL**：批次呼叫外層沒有 try/except。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import FETCH_FAILED

        def boom(*a, **k):
            raise RuntimeError("非 PttSourceUnavailableError 的失敗")

        manager = self._manager(mep)
        writer = self._run(mep, manager, ["台積電", "廣達", "AI"], boom)

        manager.run_nlp_sentiment_pipeline.assert_called()
        manager.run_feature_engineering_pipeline.assert_called()
        ptt = [e for call in writer.write.call_args_list
               for e in call.args[0] if e.source == mep.SOURCE_PTT]
        self.assertEqual(len(ptt), 3)
        self.assertTrue(all(e.outcome == FETCH_FAILED for e in ptt))

    def test_degraded_batch_makes_a_miss_fetch_failed_not_no_data(self):
        """**降級批次下的「沒命中」是 `FETCH_FAILED`，不是 `NO_DATA`。**

        預算用盡而未回溯到目標時間時，我們**分不出**
        「這個關鍵字這幾天沒人討論」與「有人討論，但在沒抓到的那幾頁裡」。

        **什麼輸入會讓它 FAIL**：把沒命中的一律記成 `NO_DATA` ——
        那是 `CLAUDE.md` §7.1 禁止的「失敗偽裝成沒有資料」，只是換了一個粒度。
        """
        import main_etl_pipeline as mep
        import pandas as pd
        from src.loaders.etl_run_log import FETCH_FAILED, OK

        df = pd.DataFrame([{
            "source": "ptt_board_pages", "fetch_keyword": "台積電",
            "date": "9/05", "title": "[標的] 台積電", "push_count": "10",
            "author": "u", "url": "https://www.ptt.cc/bbs/Stock/M.1.A.001.html",
        }])

        manager = self._manager(mep)
        writer = self._run(mep, manager, ["台積電", "廣達"],
                           lambda *a, **k: (df, "SOURCE_DEGRADED"))

        ptt = [e for call in writer.write.call_args_list
               for e in call.args[0] if e.source == mep.SOURCE_PTT]
        by_kw = dict((e.item_key, e.outcome) for e in ptt)
        self.assertEqual(by_kw["台積電"], OK)
        self.assertEqual(by_kw["廣達"], FETCH_FAILED,
                         "降級批次下沒命中 ≠ 沒有資料")

    def test_clean_batch_miss_is_no_data(self):
        """**反向釘子**：批次正常時，沒命中就是 `NO_DATA`。

        不要為了讓上面那條過，就把所有沒命中都記成失敗 ——
        **那會反過來把「真的沒人討論」偽裝成故障**，
        而 RISK-015 的覆蓋率量測正是靠這個區別。
        """
        import main_etl_pipeline as mep
        import pandas as pd
        from src.loaders.etl_run_log import NO_DATA, OK

        df = pd.DataFrame([{
            "source": "ptt_board_pages", "fetch_keyword": "台積電",
            "date": "9/05", "title": "[標的] 台積電", "push_count": "10",
            "author": "u", "url": "https://www.ptt.cc/bbs/Stock/M.1.A.001.html",
        }])

        manager = self._manager(mep)
        writer = self._run(mep, manager, ["台積電", "廣達"],
                           lambda *a, **k: (df, "OK"))

        ptt = [e for call in writer.write.call_args_list
               for e in call.args[0] if e.source == mep.SOURCE_PTT]
        by_kw = dict((e.item_key, e.outcome) for e in ptt)
        self.assertEqual(by_kw["台積電"], OK)
        self.assertEqual(by_kw["廣達"], NO_DATA)

    def test_detail_records_an_observable_fact(self):
        """`FETCH_FAILED` 的 `detail` 必須是可觀測的事實，不是推論。

        同 `universe_snapshots.exclusion_reason` 與 `etl_run_log` 的紀律。
        """
        import main_etl_pipeline as mep
        from src.extractors.ptt_scraper import PttSourceUnavailableError
        from src.loaders.etl_run_log import FETCH_FAILED

        def boom(*a, **k):
            raise PttSourceUnavailableError("connection refused（模擬）")

        manager = self._manager(mep)
        writer = self._run(mep, manager, ["廣達"], boom)
        ptt = [e for call in writer.write.call_args_list
               for e in call.args[0] if e.source == mep.SOURCE_PTT]
        self.assertEqual(ptt[0].outcome, FETCH_FAILED)
        self.assertIn("PttSourceUnavailableError", ptt[0].detail,
                      "要看得出是哪一種失敗——例外型別本身就是可觀測的事實")
        self.assertIn("connection refused", ptt[0].detail)

    def test_run_ptt_pipeline_no_longer_swallows_the_exception(self):
        """**例外必須傳播出 `run_ptt_pipeline`。**

        `feature_aggregator.py:451` 的註解說 `SOURCE_FAILED` 需要
        「pipeline 例外傳播」才可能產生 —— **而那個傳播就是在這裡被攔掉的**。
        B 輪要讓四態可達，**前提是這個例外真的走得出去**。
        """
        import main_etl_pipeline as mep
        from src.extractors.ptt_scraper import PttSourceUnavailableError

        manager = self._manager(mep)
        manager.ptt_scraper = MagicMock()
        manager.ptt_scraper.scrape_ptt_stock_by_keyword.side_effect = \
            PttSourceUnavailableError("PTT 完全不可達（模擬）")
        manager.db_writer = MagicMock()
        with self.assertRaises(PttSourceUnavailableError):
            manager.run_ptt_pipeline("廣達")


if __name__ == "__main__":
    unittest.main()
