"""
tests/test_gemini_quota_discipline.py — §0.5 #31＋#33 Gemini 用量縮減／探索不改
既有權重（GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md v3，PO 2026-09-18 核准）。

測試範疇（提案 §4＋複核 GREEN 後突變測試追加的 3b，本檔 12 個測試函式，對應
提案編號 1（含 3 子案例）／1b／2／3／3b／4／5（含 5b 子案例）／6（含第二子案例）／
6b／6c／7／9；編號 8 在 tests/test_thematic_mapping.py 以「改寫既有測試」方式延續，
不算新增。**精確計數：本檔 12 個新增測試函式；test_thematic_mapping.py 1 個既有
測試改寫**（`TEAM_PLAYBOOK.md` A13 的「紅數＝新增測試數」不含改寫項）。

- 1／1b：探索頻率判準（`fetch_last_discovery_probed_date` + `DISCOVERY_INTERVAL_DAYS`）
- 2：`run_discovery=False` 時呼叫端關閉探索
- 3／3b：`GeminiDailyQuotaExhausted` 的判斷順序（`PerDay` 必須先於一般 `quota`
  判斷）——3 測 `NLPProcessor._generate_content_with_retry`，3b（複核 GREEN 後
  突變測試發現的存活突變追加）測 `TrendDiscover._generate_with_retry` 同一段
  分類邏輯，兩者不可互相取代：3b 前若只丟已分類好的 `GeminiDailyQuotaExhausted`
  例外（如 6 原本的作法），分類邏輯本身從未被真正執行過
- 4：一般 429（不含 `PerDay`）仍照舊重試
- 5：NLP 撞每日配額 → `nlp_gemini/daily_quota/REFUSED`，流程繼續到特徵階段
  （含 5b 子案例：`run_log_writer`／`started_at`／`batch_key` 缺任一項時拋 `ValueError`）
- 6（含第二子案例）／6b／6c：探索的四態回傳（`REFUSED`／`FETCH_FAILED`／`NO_DATA`）
  ——6 的主案例改用原始未分類訊息（驗證分類路徑），第二子案例保留原本已分類例外
  的 fixture（驗證 `run_discovery()` 對已分類例外也能正確接住）
- 7：兩處模型名同一常數
- 9：非配額例外仍中止（僅適用 NLP 路徑）
"""

import datetime as _dt
import unittest
from unittest.mock import MagicMock, patch

from src.loaders.etl_run_log import FETCH_FAILED, NO_DATA, OK, REFUSED

# doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_log.txt
# 第 404～426 行原文（quota_id 含 "PerDay"）——未分類的原始例外訊息，供測項
# 3／3b／6 共用，驗證的是「分類邏輯真的被執行到」，不是丟已分類好的例外類別。
REAL_DAILY_QUOTA_ERROR_TEXT = (
    "429 You exceeded your current quota, please check your plan and billing "
    "details. For more information on this error, head to: "
    "https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current "
    "usage, head to: https://ai.dev/rate-limit. \n"
    "* Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash\n"
    "Please retry in 53.170503096s. [links {\n"
    "  description: \"Learn more about Gemini API quotas\"\n"
    "  url: \"https://ai.google.dev/gemini-api/docs/rate-limits\"\n"
    "}\n"
    ", violations {\n"
    "  quota_metric: \"generativelanguage.googleapis.com/generate_content_free_tier_requests\"\n"
    "  quota_id: \"GenerateRequestsPerDayPerProjectPerModel-FreeTier\"\n"
    "  quota_dimensions {\n"
    "    key: \"model\"\n"
    "    value: \"gemini-3.8-flash\"\n"
    "  }\n"
    "  quota_dimensions {\n"
    "    key: \"location\"\n"
    "    value: \"global\"\n"
    "  }\n"
    "  quota_value: 20\n"
    "}\n"
    ", retry_delay {\n"
    "  seconds: 53\n"
    "}\n"
    "])"
)


# ============================================================================
# 1／1b：探索頻率判準
# ============================================================================
class DiscoveryFrequencyGateTests(unittest.TestCase):
    """§4 測項 1／1b：`run_all_daily_tasks()` 只在「距上次有問過（OK／NO_DATA）
    達 DISCOVERY_INTERVAL_DAYS 天」時才呼叫 `run_discovery()`；跳過時（A4 裁決）
    不寫任何 `ai_discovery` 列。"""

    def _manager(self, mep, today):
        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            manager = mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": today, "tpex": today}
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": None, "price_max_date": None, "n_lag": 0}
        manager.trend_discover = MagicMock()
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()
        return manager

    def _run(self, mep, today, probed_date):
        """
        §13.4 教訓（複核第三輪，2026-09-19 追加）：`run_all_daily_tasks()`
        內部的「距上次有問過幾天」判準用的是**沒被 patch 的**
        `now_taipei()`——只 patch `previous_business_day` 不夠，`today`
        這個 fixture 變數與生產碼實際讀到的時鐘是兩個獨立來源。v3 首次
        commit 的版本沒 patch `now_taipei`，09-18 執行當天巧合通過（因為
        `probed_date=today-6` 距真實系統時鐘也剛好 <7 天），09-19 起
        `now_taipei()` 已推進，距今變成 7 天，子案例 a（應跳過）反而執行，
        斷言 FAIL——這正是本檔自己就示範了「涉及『距今 N 天』的測試，
        時鐘必須被 patch，fixture 日期從同一個 patch 值推導」這條規則。
        """
        manager = self._manager(mep, today)
        manager.db_writer.fetch_last_discovery_probed_date.return_value = probed_date
        manager.trend_discover.run_discovery.return_value = (OK, None)
        writer = MagicMock()
        fixed_now = _dt.datetime.combine(today, _dt.time(15, 0, 0))
        with patch.object(mep, "previous_business_day", return_value=today), \
             patch.object(mep, "now_taipei", return_value=fixed_now), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: writer):
            manager.run_all_daily_tasks()
        return manager, writer

    def test_1_discovery_frequency_gate_skip_and_run(self):
        """1：三個子案例——距上次 OK 6 天跳過／7 天以上執行／從未探索過執行。

        known-FAIL：現行碼無此判準，`run_discovery()` 一律被無條件呼叫——
        子案例 a（應跳過）會斷言 FAIL；子案例 b／c 現行碼雖然也會呼叫，但
        `run_log_writer.write` 收到的列現行碼記法不成立（尚未有 `SOURCE_
        AI_DISCOVERY`／`OK` 的正確寫法），需配合子案例 a 一起看才有偵測力
        （單獨看 b／c 在「現行碼一律呼叫」下不會 FAIL，這是刻意的配對設計，
        非測試本身弱）。
        """
        import main_etl_pipeline as mep

        today = _dt.date(2026, 9, 18)

        # 子案例 a：距上次 OK 6 天 → 跳過，不呼叫、不寫列（A4）。
        manager_a, writer_a = self._run(mep, today, probed_date=today - _dt.timedelta(days=6))
        manager_a.trend_discover.run_discovery.assert_not_called()
        for call in writer_a.write.call_args_list:
            entries = call.args[0]
            self.assertFalse(
                any(e.source == "ai_discovery" for e in entries),
                "距上次 OK 不足 7 天時，etl_run_log 不應出現 ai_discovery 列（A4）")

        # 子案例 b：恰好 7 天（邊界含）→ 執行。
        manager_b, _writer_b = self._run(mep, today, probed_date=today - _dt.timedelta(days=7))
        manager_b.trend_discover.run_discovery.assert_called_once()

        # 子案例 c：從未探索過（`None`）→ 執行。
        manager_c, _writer_c = self._run(mep, today, probed_date=None)
        manager_c.trend_discover.run_discovery.assert_called_once()

    def test_1b_no_data_counts_as_probed_fetch_failed_does_not(self):
        """1b：最近一列 `NO_DATA` 距今 6 天 → 跳過；最近一列 `FETCH_FAILED`
        距今 1 天 → 執行（`NO_DATA` 算「有問過」，`FETCH_FAILED` 不算）。

        本測試直接測 `fetch_last_discovery_probed_date()` 的 SQL 查詢邏輯
        （只認 outcome IN ('OK','NO_DATA')），不透過完整 `run_all_daily_tasks()`。

        known-FAIL：`fetch_last_discovery_probed_date()` 尚未存在 → AttributeError；
        若改成只認 `outcome='OK'`（不含 `NO_DATA`），`NO_DATA` 距今 6 天的案例
        會被誤判成「從未問過」而不跳過 → 斷言 FAIL。
        """
        from src.loaders.db_writer import DBWriter

        writer = DBWriter.__new__(DBWriter)
        writer.db_config = {}

        # 案例 a：最近一列 NO_DATA，batch_key 距今 6 天。
        mock_cursor_a = MagicMock()
        mock_cursor_a.fetchone.return_value = ("2026-09-12",)
        mock_conn_a = MagicMock()
        mock_conn_a.cursor.return_value.__enter__.return_value = mock_cursor_a
        with patch("psycopg2.connect", return_value=mock_conn_a):
            result_a = writer.fetch_last_discovery_probed_date()
        self.assertEqual(result_a, _dt.date(2026, 9, 12))
        sql_a = mock_cursor_a.execute.call_args[0][0]
        self.assertIn("'OK'", sql_a)
        self.assertIn("'NO_DATA'", sql_a)
        self.assertNotIn("'FETCH_FAILED'", sql_a)
        self.assertNotIn("'REFUSED'", sql_a)


# ============================================================================
# 2：run_discovery=False
# ============================================================================
class DiscoveryCallerOptOutTests(unittest.TestCase):
    """§4 測項 2：`run_all_daily_tasks(run_discovery=False)` 不呼叫
    `run_discovery()`，也不寫任何列（與距上次探索天數無關）。

    known-FAIL：現行 `run_all_daily_tasks()` 無此參數 → TypeError（多餘關鍵字引數）。
    """

    def test_run_discovery_false_skips_unconditionally(self):
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
            manager = mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        today = _dt.date(2026, 9, 18)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": today, "tpex": today}
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": None, "price_max_date": None, "n_lag": 0}
        # 從未探索過——即使如此，run_discovery=False 也不得呼叫。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover = MagicMock()
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()

        writer = MagicMock()
        with patch.object(mep, "previous_business_day", return_value=today), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: writer):
            manager.run_all_daily_tasks(run_discovery=False)

        manager.trend_discover.run_discovery.assert_not_called()
        for call in writer.write.call_args_list:
            entries = call.args[0]
            self.assertFalse(any(e.source == "ai_discovery" for e in entries))


# ============================================================================
# 3／4：GeminiDailyQuotaExhausted 判斷順序
# ============================================================================
class DailyQuotaExceptionClassificationTests(unittest.TestCase):
    """§4 測項 3／4：`PerDay` 訊息必須判成每日配額耗盡（不重試），一般 429／
    分鐘限速仍照舊重試。

    紅測 fixture 使用 09-17 真實 log 原文（複核意見陷阱 2），不得自行編寫。
    """

    def _processor(self):
        from src.transform.nlp_processor import NLPProcessor

        processor = NLPProcessor.__new__(NLPProcessor)
        processor.model = MagicMock()
        return processor

    def test_3_per_day_message_raises_once_without_retry(self):
        """3：含 `PerDay` 的訊息只呼叫 `generate_content` 一次即拋
        `GeminiDailyQuotaExhausted`，不重試。

        known-FAIL：`GeminiDailyQuotaExhausted` 與判斷函式尚未存在 → ImportError。
        """
        from src.transform.nlp_processor import GeminiDailyQuotaExhausted

        processor = self._processor()
        processor.model.generate_content.side_effect = Exception(
            REAL_DAILY_QUOTA_ERROR_TEXT)

        with self.assertRaises(GeminiDailyQuotaExhausted):
            processor._generate_content_with_retry("prompt")

        self.assertEqual(processor.model.generate_content.call_count, 1,
                          "每日配額耗盡不應重試")

    def test_3b_discovery_retry_classifies_raw_per_day_message(self):
        """3b（複核第二輪 GREEN 後突變測試發現的存活突變追加，獨立補測）：
        `TrendDiscover._generate_with_retry()` 的 `PerDay` 分類邏輯必須真的
        被執行到——用**未分類**的原始 09-17 log 訊息餵給 `generate_content`，
        不是像測項 6 原本那樣直接丟已經分類好的 `GeminiDailyQuotaExhausted`
        例外（那樣會繞過 `_generate_with_retry` 內部的 `is_daily_quota_
        exhausted` 判斷，走 `run_discovery()` 既有的 `except
        GeminiDailyQuotaExhausted: raise`，分類邏輯本身從未被驗證過）。

        known-FAIL：刪除 `trend_discover._generate_with_retry()` 裡
        `if is_daily_quota_exhausted(exc): raise GeminiDailyQuotaExhausted
        (...) from exc` 兩行，12 條（含本條之前的 11 條）原本全綠——此突變
        在審查方複核中存活。刪除後原始 429 訊息會被 `_is_transient_
        exception` 判成暫態，重試 5 次（2+4+8+16+16=46 秒）後落到
        `run_discovery()` 既有的 `except Exception` 分支，記成
        `FETCH_FAILED` 而非 `REFUSED`，且 `call_count` 變成 5 而非 1——
        兩者都是本測試要斷言、且要防的事。`time.sleep` 需 patch 掉，
        避免突變存活時測試實際等待 46 秒。
        """
        from src.extractors.trend_discover import TrendDiscover

        discover = TrendDiscover.__new__(TrendDiscover)
        discover.api_key = "dummy_key"
        discover.model = MagicMock()
        discover._fetch_recent_hot_titles = MagicMock(return_value=["[新聞] 熱門標題"])
        discover.model.generate_content.side_effect = Exception(
            REAL_DAILY_QUOTA_ERROR_TEXT)

        mock_db = MagicMock()
        with patch("time.sleep"):
            outcome, detail = discover.run_discovery(mock_db, max_new_keywords=3)

        self.assertEqual(outcome, REFUSED)
        self.assertIsNotNone(detail)
        self.assertEqual(discover.model.generate_content.call_count, 1,
                          "每日配額耗盡不應重試")
        mock_db.insert_discovered_keywords.assert_not_called()

    def test_4_per_minute_429_without_per_day_still_retries(self):
        """4：一般 429（不含 `PerDay`）仍照舊指數退避重試至 `max_retries` 次。"""
        processor = self._processor()
        processor.model.generate_content.side_effect = Exception(
            "429 You exceeded your current quota. "
            "quota_id: \"GenerateRequestsPerMinutePerProjectPerModel-FreeTier\"")

        with patch("time.sleep"):
            with self.assertRaises(Exception):
                processor._generate_content_with_retry("prompt", max_retries=3)

        self.assertEqual(processor.model.generate_content.call_count, 3,
                          "一般每分鐘限速應照舊重試 max_retries 次")


# ============================================================================
# 5（含 5b）：NLP 撞每日配額
# ============================================================================
class NlpDailyQuotaHandlingTests(unittest.TestCase):
    """§4 測項 5：NLP 撞配額 → `etl_run_log` 有
    `nlp_gemini/daily_quota/REFUSED`，流程繼續到 `generate_daily_features`，
    `fetch_failed_source_keys` 在其後被呼叫。

    5b 子案例（複核指示，維持測試數不變、折進本函式）：
    `run_log_writer`／`started_at`／`batch_key` 任一為 `None` 時撞配額 →
    拋 `ValueError`（而非靜默吞掉不落地）。
    """

    def test_5_nlp_quota_exhaustion_writes_refused_and_continues(self):
        """known-FAIL：現行 `run_nlp_sentiment_pipeline()` 完全沒有 try/except，
        例外直接穿透 → `run_all_daily_tasks()` 中止，`attach_mock` 斷言不到後續呼叫。
        """
        import main_etl_pipeline as mep
        from src.transform.nlp_processor import GeminiDailyQuotaExhausted

        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            manager = mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        today = _dt.date(2026, 9, 18)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": today, "tpex": today}
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": None, "price_max_date": None, "n_lag": 0}
        manager.db_writer.fetch_last_discovery_probed_date.return_value = today
        manager.db_writer.fetch_failed_source_keys.return_value = set()
        manager.db_writer.fetch_all_for_features.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        # NLP 撞每日配額：df_raw 非空 → 進入 process_batch_hybrid → 拋例外。
        import pandas as pd
        manager.db_writer.fetch_data.return_value = pd.DataFrame(
            {"article_id": [1], "title": ["t"]})
        manager.db_writer.fetch_data = MagicMock(
            return_value=pd.DataFrame({"article_id": [1], "title": ["t"]}))
        # COUNT(*) 剩餘篇數查詢——用 side_effect 依序回應兩種不同查詢。
        remaining_df = pd.DataFrame({"n": [42]})

        def _fetch_data_side_effect(query, *a, **kw):
            if "COUNT(*)" in query:
                return remaining_df
            return pd.DataFrame({"article_id": [1], "title": ["t"]})

        manager.db_writer.fetch_data.side_effect = _fetch_data_side_effect

        manager.trend_discover = MagicMock()
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()
        manager.feature_aggregator = MagicMock()
        manager.nlp_processor = MagicMock()
        manager.nlp_processor.process_batch_hybrid.side_effect = GeminiDailyQuotaExhausted(
            "每日配額耗盡（測試）")

        writer = MagicMock()
        parent = MagicMock()
        parent.attach_mock(manager.db_writer.fetch_failed_source_keys, "fetch_failed")
        parent.attach_mock(manager.feature_aggregator.generate_daily_features, "gen_features")

        # §13.4：now_taipei() 需與 today 綁在同一個 patch 值，否則本測試會在
        # 真實系統時鐘與 today 相差 ≥7 天時意外觸發探索（同 test 1 的教訓，
        # 複核第三輪，2026-09-19）。
        fixed_now = _dt.datetime.combine(today, _dt.time(15, 0, 0))
        with patch.object(mep, "previous_business_day", return_value=today), \
             patch.object(mep, "now_taipei", return_value=fixed_now), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: writer):
            manager.run_all_daily_tasks()

        written_entries = [e for call in writer.write.call_args_list
                            for e in call.args[0]]
        nlp_entries = [e for e in written_entries if e.source == "nlp_gemini"]
        self.assertEqual(len(nlp_entries), 1)
        self.assertEqual(nlp_entries[0].outcome, REFUSED)
        self.assertEqual(nlp_entries[0].item_key, "daily_quota")
        self.assertIsNotNone(nlp_entries[0].detail)

        names = [c[0] for c in parent.mock_calls]
        self.assertIn("gen_features", names,
                       "配額耗盡後流程必須繼續到 generate_daily_features")
        self.assertIn("fetch_failed", names)

        # --- 5b 子案例（折進本函式，維持測試數不變）：run_log_writer／
        # started_at／batch_key 任一為 None 時撞配額 → 拋 ValueError（而非
        # 靜默吞掉不落地）。known-FAIL：若改成靜默略過（pass）而非拋出，
        # 本斷言 FAIL。
        bare_manager = mep.ETLPipelineManager.__new__(mep.ETLPipelineManager)
        bare_manager.db_writer = MagicMock()
        bare_manager.db_writer.fetch_data.return_value = pd.DataFrame(
            {"article_id": [1], "title": ["t"]})
        bare_manager.nlp_processor = MagicMock()
        bare_manager.nlp_processor.process_batch_hybrid.side_effect = (
            GeminiDailyQuotaExhausted("每日配額耗盡（測試）"))

        with self.assertRaises(ValueError):
            bare_manager.run_nlp_sentiment_pipeline(
                batch_size=500, run_log_writer=None, started_at=None, batch_key=None)


# ============================================================================
# 6／6b／6c：探索的四態回傳
# ============================================================================
class DiscoveryFourStateOutcomeTests(unittest.TestCase):
    """§4 測項 6／6b／6c：`run_discovery()` 依四態回傳 `(outcome, detail)`，
    呼叫端據此記錄 `etl_run_log`，流程皆繼續（探索為非關鍵階段）。
    """

    def _discover(self):
        from src.extractors.trend_discover import TrendDiscover

        discover = TrendDiscover.__new__(TrendDiscover)
        discover.api_key = "dummy_key"
        discover.model = MagicMock()
        return discover

    def test_6_quota_exhausted_returns_refused(self):
        """6：探索撞配額 → `run_discovery()` 回傳 `("REFUSED", detail)`，
        不拋出例外（例外不跨越函式邊界）。

        known-FAIL：現行碼配額例外會被第 173 行既有 `except Exception` 生吞，
        呼叫端只會看到隱式 `None`，解包會 `TypeError`——本測試直接呼叫
        `run_discovery()` 檢查回傳值，現行碼回傳 `None` 導致
        `outcome, detail = None` 拋 `TypeError`。

        主案例改用**未分類**的原始 09-17 log 訊息（複核第二輪要求）——
        這樣才會真的走過 `_generate_with_retry()` 內部的 `is_daily_quota_
        exhausted` 分類邏輯，而不是像本測試 v3 版本那樣直接丟已分類好的
        `GeminiDailyQuotaExhausted`（那個路徑另外由 3b 專門驗證）。
        """
        discover = self._discover()
        discover._fetch_recent_hot_titles = MagicMock(return_value=["[新聞] 熱門標題"])
        discover.model.generate_content.side_effect = Exception(
            REAL_DAILY_QUOTA_ERROR_TEXT)

        mock_db = MagicMock()
        with patch("time.sleep"):
            outcome, detail = discover.run_discovery(mock_db, max_new_keywords=3)

        self.assertEqual(outcome, REFUSED)
        self.assertIsNotNone(detail)
        self.assertEqual(discover.model.generate_content.call_count, 1,
                          "每日配額耗盡不應重試")
        mock_db.insert_discovered_keywords.assert_not_called()

        # --- 第二子案例（折進本函式，v3 原本的 fixture 移到這裡）：
        # run_discovery() 對「已經是分類好的 GeminiDailyQuotaExhausted」也要
        # 能正確接住——這條路徑由 run_discovery() 自身的
        # `except GeminiDailyQuotaExhausted: return "REFUSED", ...` 負責，
        # 與 3b 驗證的「分類邏輯本身」是不同層級，兩者都要顧到。
        from src.transform.nlp_processor import GeminiDailyQuotaExhausted

        discover2 = self._discover()
        discover2._fetch_recent_hot_titles = MagicMock(return_value=["[新聞] 熱門標題"])
        discover2.model.generate_content.side_effect = GeminiDailyQuotaExhausted(
            "每日配額耗盡（測試，已分類）")

        mock_db2 = MagicMock()
        outcome2, detail2 = discover2.run_discovery(mock_db2, max_new_keywords=3)

        self.assertEqual(outcome2, REFUSED)
        self.assertIsNotNone(detail2)
        mock_db2.insert_discovered_keywords.assert_not_called()

    def test_6b_non_quota_failure_returns_fetch_failed(self):
        """6b：探索非配額失敗（`_fetch_recent_hot_titles` 回 `None`，代表掃頁
        出錯）→ `run_discovery()` 回傳 `("FETCH_FAILED", detail)`，`detail` 非空。

        known-FAIL：現行碼此情況靜默 `return`（隱式 `None`），呼叫端會誤記成
        `OK`——本測試直接檢查回傳值，現行碼回傳 `None` 導致解包 `TypeError`。
        """
        discover = self._discover()
        discover._fetch_recent_hot_titles = MagicMock(return_value=None)

        mock_db = MagicMock()
        outcome, detail = discover.run_discovery(mock_db, max_new_keywords=3)

        self.assertEqual(outcome, FETCH_FAILED)
        self.assertIsNotNone(detail)
        mock_db.insert_discovered_keywords.assert_not_called()

    def test_6c_valid_but_empty_response_returns_no_data(self):
        """6c：Gemini 回答有效但沒有可新增的詞 → `run_discovery()` 回傳
        `("NO_DATA", None)`。

        known-FAIL：現行碼靜默 `return`（隱式 `None`），解包 `TypeError`。
        """
        discover = self._discover()
        discover._fetch_recent_hot_titles = MagicMock(return_value=["[新聞] 熱門標題"])
        mock_response = MagicMock()
        mock_response.text = '{"trends": []}'
        discover.model.generate_content.return_value = mock_response

        mock_db = MagicMock()
        outcome, detail = discover.run_discovery(mock_db, max_new_keywords=3)

        self.assertEqual(outcome, NO_DATA)
        self.assertIsNone(detail)
        mock_db.insert_discovered_keywords.assert_not_called()


# ============================================================================
# 7：模型名常數
# ============================================================================
class ModelNameConstantTests(unittest.TestCase):
    """§4 測項 7：兩處模型名引用同一常數、不含 'latest'。

    known-FAIL：`src/config.py` 尚未定義 `GEMINI_MODEL_NAME` 供兩處引用
    （即使常數已建檔，兩處目前仍硬寫 'gemini-flash-latest'）→ ImportError 或
    字串不相等 → FAIL。
    """

    def test_model_name_shared_constant_and_not_latest_alias(self):
        from src.config import GEMINI_MODEL_NAME

        self.assertNotIn("latest", GEMINI_MODEL_NAME)

        with patch("google.generativeai.GenerativeModel") as mock_model, \
             patch("google.generativeai.configure"):
            from src.transform.nlp_processor import NLPProcessor
            from src.extractors.trend_discover import TrendDiscover

            with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy"}):
                NLPProcessor()
                TrendDiscover()

        model_names_used = [c.args[0] for c in mock_model.call_args_list if c.args]
        self.assertTrue(len(model_names_used) >= 2)
        for name in model_names_used:
            self.assertEqual(name, GEMINI_MODEL_NAME)


# ============================================================================
# 9：非配額例外仍中止（僅 NLP 路徑）
# ============================================================================
class NonQuotaExceptionStillAbortsTests(unittest.TestCase):
    """§4 測項 9：`run_nlp_sentiment_pipeline()` 遇到非 `GeminiDailyQuotaExhausted`
    的例外仍必須向上傳遞、中止執行——只有每日配額耗盡才被特別接住。

    known-FAIL：若把 `except GeminiDailyQuotaExhausted` 誤改成裸
    `except Exception`，非配額例外也會被吞掉 → 斷言「應向上傳遞」FAIL。
    """

    def test_non_quota_exception_propagates(self):
        import pandas as pd
        from main_etl_pipeline import ETLPipelineManager

        manager = ETLPipelineManager.__new__(ETLPipelineManager)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_data.return_value = pd.DataFrame(
            {"article_id": [1], "title": ["t"]})
        manager.nlp_processor = MagicMock()
        manager.nlp_processor.process_batch_hybrid.side_effect = RuntimeError(
            "非配額的意外錯誤")

        with self.assertRaises(RuntimeError):
            manager.run_nlp_sentiment_pipeline(batch_size=500)


if __name__ == "__main__":
    unittest.main()
