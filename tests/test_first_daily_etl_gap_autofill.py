# tests/test_first_daily_etl_gap_autofill.py
"""
首次每日 ETL 缺口自動追補——Gate A 提案紅測（`bug-fix-protocol` 步驟一）。

見 `doc/upgrade/gates/FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`。

本檔測試的是**尚未實作**的行為，撰寫時全部預期 FAIL（`CLAUDE.md` §9A.2）：
- `compute_gap_backfill_dates()`／`BackfillWindowExceededError`／`MissingBackfillOriginError`
  （新函式與例外，計劃放 `src/extractors/market_report_fetcher.py`）
- `DBWriter.fetch_candidate_prices_max_date_by_market()`（新方法，`src/loaders/db_writer.py`）
- `recompute_tail_labels(..., tail_window=...)`（既有函式新增參數，`src/ml/triple_barrier.py`）
- `run_all_daily_tasks()` 批次階段／逐股階段改為多日迴圈，並把追補天數 n 傳進尾端掛點
  （`main_etl_pipeline.py`）

全部合成資料，不連真實庫、不觸發任何網路請求。
"""
import datetime as _dt
import unittest
from unittest.mock import MagicMock, patch


# ============================================================
# 1/2/5：compute_gap_backfill_dates() —— 純函式，缺口日期序列計算
# ============================================================
class ComputeGapBackfillDatesSequence(unittest.TestCase):
    """對應提案 §6 測項 1、5：日期序列正確、跳過週末、超過上界拒絕。"""

    def test_sequence_skips_weekends(self):
        """`last_date` 次日起到 `target_date`（含）為止，跳過週六日。

        `last_date`=2026-09-04（週五），`target_date`=2026-09-08（週二）——
        中間 09-05／06 為週末，應只回傳 [09-07, 09-08]。
        """
        from src.extractors.market_report_fetcher import compute_gap_backfill_dates

        result = compute_gap_backfill_dates(
            last_date=_dt.date(2026, 9, 4),
            target_date=_dt.date(2026, 9, 8),
        )
        self.assertEqual(result, [_dt.date(2026, 9, 7), _dt.date(2026, 9, 8)])

    def test_no_gap_returns_empty_list(self):
        """`last_date` 已經等於 `target_date` 時，序列為空（不重複抓已有的那天）。"""
        from src.extractors.market_report_fetcher import compute_gap_backfill_dates

        result = compute_gap_backfill_dates(
            last_date=_dt.date(2026, 9, 8),
            target_date=_dt.date(2026, 9, 8),
        )
        self.assertEqual(result, [])

    def test_upper_bound_rejects_without_partial_result(self):
        """**known-FAIL 對象本身**：缺口超過 30 個平日必須整個拒絕，

        不得回傳被截斷的部分序列（那會讓呼叫端誤用不完整的回補當成完整）。
        """
        from src.extractors.market_report_fetcher import (
            compute_gap_backfill_dates, BackfillWindowExceededError,
        )

        # 2026-09-04（週五）到 2026-11-04（週三）之間平日數遠超過 30。
        with self.assertRaises(BackfillWindowExceededError) as ctx:
            compute_gap_backfill_dates(
                last_date=_dt.date(2026, 9, 4),
                target_date=_dt.date(2026, 11, 4),
                max_days=30,
            )
        self.assertGreater(ctx.exception.gap_days, 30)
        self.assertEqual(ctx.exception.max_days, 30)

    def test_upper_bound_boundary_exactly_30_is_allowed(self):
        """恰好等於上界（30 個平日）應該放行，不是「超過」。"""
        from src.extractors.market_report_fetcher import compute_gap_backfill_dates

        # 6 個完整平日週 = 30 個平日。
        result = compute_gap_backfill_dates(
            last_date=_dt.date(2026, 9, 4),   # 週五
            target_date=_dt.date(2026, 10, 16),  # 週五，+30 個平日
            max_days=30,
        )
        self.assertEqual(len(result), 30)


# ============================================================
# 6：Triple-Barrier 尾端視窗加寬 —— 持有期窗口本身不變
# ============================================================
class TailWindowWidensWithoutChangingHoldingPeriod(unittest.TestCase):
    """對應提案 §3.6／§6 測項 6、7：`tail_window` 是獨立於 `holding_period` 的新參數。"""

    def _synthetic_prices(self, n_days=40):
        import pandas as pd
        dates = pd.bdate_range("2026-07-01", periods=n_days)
        return pd.DataFrame({
            "stock_id": ["2330"] * n_days,
            "trade_date": dates,
            "open_price": [100.0 + i * 0.1 for i in range(n_days)],
            "high_price": [101.0 + i * 0.1 for i in range(n_days)],
            "low_price": [99.0 + i * 0.1 for i in range(n_days)],
        })

    def test_default_tail_window_matches_existing_behavior(self):
        """`tail_window` 未傳入時（`None`）＝現行 `holding_period+1` 行為，逐位相同。

        既有呼叫端（`run_triple_barrier_tail_recompute()` 目前的呼叫）不得因本次
        修改而變化——這條測試就是那個回歸保護。
        """
        from src.ml.triple_barrier import recompute_tail_labels

        df = self._synthetic_prices()
        without_param = recompute_tail_labels(df, holding_period=5)
        with_none = recompute_tail_labels(df, holding_period=5, tail_window=None)
        import pandas as pd
        pd.testing.assert_frame_equal(
            without_param.reset_index(drop=True),
            with_none.reset_index(drop=True),
        )

    def test_tail_window_widens_selected_rows(self):
        """`tail_window=holding_period+n` 時，選取列數＝該值，不是固定 6。"""
        from src.ml.triple_barrier import recompute_tail_labels

        df = self._synthetic_prices()
        n = 3
        result = recompute_tail_labels(df, holding_period=5, tail_window=5 + n)
        self.assertEqual(len(result), 5 + n)

    def test_tail_window_does_not_change_barrier_calc_itself(self):
        """**核心斷言（防止字面誤植 §3.6 的問題再度發生）**：

        `tail_window` 只改變「選取範圍」，Triple-Barrier 本身的持有期窗口
        （進場後最多看幾天）必須維持 `holding_period=5` 不變——用寬視窗選出的
        重疊列，其 `target_triple_barrier`／`label_reason` 必須與窄視窗選出的
        同一列逐值相同（同一套 `generate_triple_barrier_labels(holding_period=5)`
        算出來的，只是選取範圍不同）。
        """
        from src.ml.triple_barrier import recompute_tail_labels

        df = self._synthetic_prices()
        narrow = recompute_tail_labels(df, holding_period=5, tail_window=6)
        wide = recompute_tail_labels(df, holding_period=5, tail_window=9)

        narrow_keyed = narrow.set_index("trade_date")
        wide_keyed = wide.set_index("trade_date")
        overlap = narrow_keyed.index.intersection(wide_keyed.index)
        self.assertTrue(len(overlap) > 0, "寬窄視窗選取範圍應有重疊，測試前提才成立")
        import pandas as pd
        for col in ("target_triple_barrier", "label_reason"):
            for idx in overlap:
                a, b = narrow_keyed.loc[idx, col], wide_keyed.loc[idx, col]
                # NaN != NaN 在 Python／NumPy 是常態——兩者皆 NaN 也算「相同」，
                # 不能直接 assertEqual（那是本測試自己的 bug，不是實作的 bug）。
                if pd.isna(a) and pd.isna(b):
                    continue
                self.assertEqual(
                    a, b,
                    f"{idx} 的 {col} 在窄／寬視窗下必須相同——"
                    "若不同，代表 tail_window 誤動了 barrier 計算窗口本身",
                )


# ============================================================
# 3/4/8/9：run_all_daily_tasks() 多日迴圈整合行為
# ============================================================
class DailyTasksBackfillLoopIntegration(unittest.TestCase):
    """對應提案 §6 測項 3、4、8、9：批次／逐股階段改為多日迴圈後的整合行為。

    沿用 `tests/test_batch_etl_boundary.py` 既有的 mock 模式
    （`DailyTasksWireInTheBatchAndToleratePerStockFailure`），
    因為本案改動的正是同一段編排邏輯。
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

    def test_run_price_batch_called_once_per_backfill_date(self):
        """缺口 3 天時，`run_price_batch` 應被呼叫 3 次，日期各不相同。

        **尚未實作**：現行 `run_all_daily_tasks()` 只呼叫 `run_price_batch` 一次
        （`previous_business_day()` 那一天），本測試預期先 FAIL。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        # ⚠ 刻意用非空清單——`fetch_active_stock_targets()`／`fetch_active_keywords()`
        # 回傳 `[]` 會觸發 `run_all_daily_tasks()` 的預設 fallback 清單（含 NVDA／
        # 6 個關鍵字），若同時忘記 mock 對應的下游方法，會真的打出網路請求
        # （PTT／yfinance）。本檔第一版就撞過這個坑，已修正，不再重蹈。
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        # candidate_prices 現況：twse／tpex 都停在 09-04，previous_business_day()
        # 若為 09-08（週二），缺口應為 [09-07, 09-08] 兩天——用月初小缺口即可驗證
        # 迴圈行為，不需要真的構造大缺口。
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 4), "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        # `run_all_daily_tasks()` 實際呼叫的是 `run_ptt_board_pipeline`（批次版），
        # 不是 `run_ptt_pipeline`（單一關鍵字版、未被呼叫）——mock 錯名字不會報錯，
        # 只會讓真正的方法照跑，是本檔第一版網路外洩的直接成因。
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": {"twse": OK, "tpex": OK}})

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        self.assertEqual(
            manager.run_price_batch.call_count, 2,
            "缺口 [09-07, 09-08] 兩天，run_price_batch 應各跑一次，"
            "不是只跑 previous_business_day() 那一天",
        )
        called_dates = sorted(
            c.args[0] for c in manager.run_price_batch.call_args_list)
        self.assertEqual(
            called_dates, [_dt.date(2026, 9, 7), _dt.date(2026, 9, 8)])

    def test_refused_market_stops_only_that_market_for_later_dates(self):
        """TPEX 於追補第 1 天 REFUSED，TWSE 後續日期不受影響、TPEX 後續日期不再嘗試。

        對應提案 §3.2：REFUSED「停該市場，不停整批」。
        """
        import main_etl_pipeline as mep
        from src.extractors.market_report_fetcher import ServiceRefusedError
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 4), "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()

        call_log = []

        def batch_side_effect(trade_date, markets=("twse", "tpex"), **kw):
            call_log.append((trade_date, tuple(markets)))
            if trade_date == _dt.date(2026, 9, 7) and "tpex" in markets:
                exc = ServiceRefusedError("tpex 429")
                exc.outcomes_by_item = {"twse": OK, "tpex": "REFUSED"}
                raise exc
            return {"OK": len(markets), "NO_DATA": 0, "FETCH_FAILED": 0,
                    "REFUSED": 0, "total": len(markets),
                    "outcomes_by_item": {m: OK for m in markets}}

        manager.run_price_batch = MagicMock(side_effect=batch_side_effect)

        # §3.2「最後統一 raise」（deferred，同既有單日 run_price_batch() 語意）——
        # run_all_daily_tasks() 全部階段跑完才 raise ServiceRefusedError，不是吞掉。
        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            with self.assertRaises(ServiceRefusedError):
                manager.run_all_daily_tasks()

        # 09-07：twse+tpex 一起試（tpex 被拒）；09-08：只剩 twse。
        # ⚠ markets 集合內的排序不是本測試關心的語意（呼叫端可能用任何穩定排序），
        # 用 set() 比對，不鎖死順序。
        self.assertEqual(call_log[0][0], _dt.date(2026, 9, 7))
        self.assertEqual(set(call_log[0][1]), {"twse", "tpex"})
        self.assertEqual(
            call_log[1], (_dt.date(2026, 9, 8), ("twse",)),
            "tpex 於 09-07 被 REFUSED 後，09-08 不應再嘗試 tpex",
        )

    def test_batch_key_separated_per_backfill_date(self):
        """逐股階段對多個追補日期執行後，`etl_run_log` 的 `batch_key` 逐日分開。"""
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        stocks = [{"stock_id": "2330", "market": "TWSE"}]
        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = stocks
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 4), "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": {"twse": OK, "tpex": OK}})
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(
            return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(
            return_value=OK)

        writer = MagicMock()
        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: writer):
            manager.run_all_daily_tasks()

        tracked = [e for call in writer.write.call_args_list
                   for e in call.args[0]
                   if e.source == mep.SOURCE_TRACKED_DAILY]
        batch_keys = sorted({e.batch_key for e in tracked})
        self.assertEqual(
            batch_keys, ["2026-09-07", "2026-09-08"],
            "逐股階段兩個追補日期的 batch_key 必須分開，不得合併成一筆",
        )

    def test_holiday_no_data_day_does_not_interrupt_sequence(self):
        """對應提案 §6 測項 2：追補序列中某日為 `NO_DATA`（假日），不中斷，繼續下一天。"""
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK, NO_DATA

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 4), "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()

        # 09-07（例如國定假日）兩市場皆 NO_DATA；09-08 正常 OK。
        manager.run_price_batch = MagicMock(side_effect=[
            {"OK": 0, "NO_DATA": 2, "FETCH_FAILED": 0, "REFUSED": 0, "total": 2,
             "outcomes_by_item": {"twse": NO_DATA, "tpex": NO_DATA}},
            {"OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0, "total": 2,
             "outcomes_by_item": {"twse": OK, "tpex": OK}},
        ])

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        self.assertEqual(
            manager.run_price_batch.call_count, 2,
            "09-07 為 NO_DATA 不得中斷序列，09-08 仍須被嘗試",
        )

    def test_fetch_failed_day_does_not_interrupt_sequence(self):
        """對應提案 §6 測項 3：某日 `FETCH_FAILED`（非 REFUSED）不得中斷後續日期。

        `run_price_batch()` 對 `FetchFailedError` 是內部捕捉、轉記
        `RunLogEntry(FETCH_FAILED)` 後正常 return（不 raise）——故從呼叫端角度，
        FETCH_FAILED 的那天不需要任何特殊分支，迴圈天然會繼續。本測試把這個
        「天然繼續」釘成迴歸保護，避免日後有人誤加了「FETCH_FAILED 也中止」的邏輯。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK, FETCH_FAILED

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 4), "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()

        manager.run_price_batch = MagicMock(side_effect=[
            {"OK": 1, "NO_DATA": 0, "FETCH_FAILED": 1, "REFUSED": 0, "total": 2,
             "outcomes_by_item": {"twse": OK, "tpex": FETCH_FAILED}},
            {"OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0, "total": 2,
             "outcomes_by_item": {"twse": OK, "tpex": OK}},
        ])

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        self.assertEqual(
            manager.run_price_batch.call_count, 2,
            "09-07 tpex FETCH_FAILED 不得中斷序列，09-08 仍須被嘗試，"
            "且 09-08 仍應嘗試 tpex（FETCH_FAILED 不像 REFUSED 那樣停該市場）",
        )
        second_call_markets = manager.run_price_batch.call_args_list[1].kwargs.get(
            "markets", manager.run_price_batch.call_args_list[1].args[1:2])
        # 只斷言 tpex 仍在第二天的嘗試清單中（FETCH_FAILED 不移除市場，只有 REFUSED 才移除）。
        self.assertIn("tpex", manager.run_price_batch.call_args_list[1].args[1]
                       if len(manager.run_price_batch.call_args_list[1].args) > 1
                       else manager.run_price_batch.call_args_list[1].kwargs["markets"])

    def test_refused_market_propagates_batch_outcome_to_per_stock_stage(self):
        """對應提案 §3.5 補充（訂正版）／§6 測項 9：某日某市場被 REFUSED 時，該日該市場的

        追蹤標的在逐股階段應收到能反映『上游被拒』的 `batch_outcome`
        （傳給 `run_tpex_pipeline_from_candidate_prices` 的 `batch_outcome` 參數），
        不得因為多日迴圈而遺漏、退化成預設值（那會被誤判為『當日無資料』）。

        ⚠ 訂正（審查方指出提案 §3.5 原文誤植）：正確結果是 `REFUSED`，
        **不是** `FETCH_FAILED`——本測試名稱曾誤植為 `..._marks_fetch_failed`，
        斷言本身一直是對的（`REFUSED`），只有函式名字誤導，已改名。

        ⚠ **自我糾正（§9A.1 案例）**：第一版把 `previous_business_day()` 直接設成
        REFUSED 發生的那一天（單一缺口日），結果舊的單日程式碼**剛好**也會在那天
        呼叫到 `run_price_batch`、也剛好把同一個 `batch_outcome` 傳給逐股階段——
        測試在舊程式碼（多日迴圈尚未實作）上**意外通過**，是一個結構上量不到
        「新邏輯有沒有真的接上」的假紅測。改為 tpex 缺口兩天（09-07 REFUSED、
        09-08 是 `previous_business_day()`），斷言改成「呼叫記錄裡存在 `trade_date=09-07`
        且 `batch_outcome=REFUSED` 的那一筆」——舊程式碼只會用 `previous_business_day()`
        單一日期（09-08）呼叫一次，根本不會產生 `trade_date=09-07` 的呼叫，
        斷言因此對舊程式碼確實 FAIL。
        """
        import main_etl_pipeline as mep
        from src.extractors.market_report_fetcher import ServiceRefusedError
        from src.loaders.etl_run_log import OK, REFUSED

        stocks = [{"stock_id": "6488", "market": "TPEX"}]
        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = stocks
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        # twse 已追到 previous_business_day()（零缺口）；tpex 缺兩天 [09-07, 09-08]，
        # 09-07 被 REFUSED（依 §3.2 停該市場後續日期，09-08 起 tpex 不再嘗試）。
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 8), "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()

        def batch_side_effect(trade_date, markets=("twse", "tpex"), **kw):
            if trade_date == _dt.date(2026, 9, 7) and "tpex" in markets:
                exc = ServiceRefusedError("tpex 429")
                exc.outcomes_by_item = {"tpex": REFUSED}
                raise exc
            return {"OK": len(markets), "NO_DATA": 0, "FETCH_FAILED": 0,
                    "REFUSED": 0, "total": len(markets),
                    "outcomes_by_item": {m: OK for m in markets}}

        manager.run_price_batch = MagicMock(side_effect=batch_side_effect)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            with self.assertRaises(ServiceRefusedError):
                manager.run_all_daily_tasks()

        matching_calls = [
            c for c in manager.run_tpex_pipeline_from_candidate_prices.call_args_list
            if (c.args[1] if len(c.args) > 1 else c.kwargs.get("trade_date"))
            == _dt.date(2026, 9, 7)
            and c.kwargs.get("batch_outcome") == REFUSED
        ]
        self.assertEqual(
            len(matching_calls), 1,
            "逐股階段對 6488 在 09-07（被 REFUSED 的那天）必須恰好被呼叫一次、"
            "batch_outcome=REFUSED；舊的單日程式碼只會用 previous_business_day()"
            "（09-08）呼叫一次，永遠不會產生 09-07 這筆呼叫——本斷言就是用來區分兩者",
        )

    def test_tail_recompute_receives_n_lag_as_tail_window(self):
        """§0.5 #30 必修：known-FAIL 用現在真實庫的形狀。

        價格缺口 0（`candidate_prices`／`stock_prices` 已補到 `previous_business_day()`，
        2026-09-17 首次真實執行後的真實現況）、`daily_ml_features` 仍停在 09-04，
        `stock_prices` 在 F 之後有 8 個交易日——`run_triple_barrier_tail_recompute()`
        應以 `tail_window=TRIPLE_BARRIER_HOLDING_PERIOD(5)+8=13` 被呼叫。

        這條測試就是 §0.5 #30 要修的那個缺陷本身：舊邏輯用價格缺口（此處=0）算
        `tail_window`，會漏傳（退化成預設的 6），蓋不到累積下來的 8 天特徵落後——
        現行程式碼（修好前）必須讓這條斷言 FAIL。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        # 價格缺口 0：twse／tpex 皆已等於 previous_business_day()。
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 16), "tpex": _dt.date(2026, 9, 16),
        }
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 8,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 16)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        self.assertEqual(
            manager.run_price_batch.call_count, 0,
            "價格缺口為 0，批次階段不應被呼叫——本測試的前提是「只有特徵表落後」")
        call = manager.run_triple_barrier_tail_recompute.call_args
        self.assertEqual(
            call.kwargs.get("tail_window"), 5 + 8,
            "n_lag=8（daily_ml_features 落後 stock_prices 8 個交易日），"
            "tail_window 必須是 holding_period(5)+8=13，不得沿用價格缺口（此處=0）",
        )

    def test_tail_recompute_ignores_price_gap_when_feature_table_synced(self):
        """§0.5 #30 紅測項 2：n 不再跟著價格缺口走。

        價格缺口 3 天，但 `daily_ml_features` 已經跟 `stock_prices` 同步（F=P）——
        `n_lag=0`，`tail_window` 不應被傳入（退化為預設 6）。這條證明尾端視窗
        現在完全依 n_lag 決定，價格缺口大小不再影響它。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        # 價格缺口 3 天（09-14/15/16），但特徵表已同步到 09-16（=P）。
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 11), "tpex": _dt.date(2026, 9, 11),
        }
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 16),
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 0,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0, "total": 2,
            "outcomes_by_item": {"twse": OK, "tpex": OK}})

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 16)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        self.assertEqual(
            manager.run_price_batch.call_count, 3,
            "價格缺口 3 天，批次階段仍應照常追補（與特徵表是否同步無關）")
        call = manager.run_triple_barrier_tail_recompute.call_args
        self.assertNotIn(
            "tail_window", call.kwargs,
            "n_lag=0（特徵表已與股價表同步）時不應傳 tail_window，"
            "退化為 run_triple_barrier_tail_recompute() 自身的預設值",
        )

    def test_tail_recompute_handles_empty_feature_table(self):
        """§0.5 #30 紅測項 3：特徵表全空（F=None）時不拋錯、不傳 tail_window。

        ⚠ **誠實揭露（§9A.1）**：本測試的價格缺口也剛好是 0，舊的
        `n_new_days` 邏輯在這個場景下同樣不會傳 `tail_window`（兩版程式碼
        巧合同答案）——**這條測試單獨對舊code不具偵測力，修法前後皆綠**，
        不能算作 known-FAIL。它是編排層的正面迴歸防護（確保
        `run_all_daily_tasks()` 真的不拋錯、真的不傳 tail_window），
        真正驗證 F=None 短路邏輯本身的 known-FAIL 案例在
        `FetchFeatureLagMethodTests.test_empty_feature_table_short_circuits_third_query`
        （直接單元測試 `fetch_feature_lag()`，斷言只執行 2 次查詢）。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 16), "tpex": _dt.date(2026, 9, 16),
        }
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": None,
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 0,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 16)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()  # 不得拋錯

        call = manager.run_triple_barrier_tail_recompute.call_args
        self.assertNotIn(
            "tail_window", call.kwargs,
            "特徵表全空（F=None）時 n_lag=0，不應傳 tail_window",
        )

    def test_feature_lag_measured_after_per_stock_stage(self):
        """§0.5 #30 呼叫時機釘住（審查方複核要求，突變 M3）。

        `fetch_feature_lag()` 必須排在逐股階段最後一次管線呼叫與其
        `run_log_writer.write()` 之後、AI 熱門詞探索之前——量早了的話，
        `stock_prices` 還不是本次執行後的最終狀態，`n_lag` 會少算。這與
        #30 原本要修的錯誤是同一種形狀，只是換了觸發條件：本次示範用單日
        追補讓迴圈確實呼叫一次逐股管線，藉由呼叫順序而非日期數字本身釘住
        這個時機約束。

        **known-FAIL**：commit body 附上把 `fetch_feature_lag()` 呼叫搬到
        逐股迴圈之前重跑本測試的 FAIL 輸出（突變已還原，不留在程式碼裡）。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        # 價格缺口 1 天（09-15→09-16），確保逐股迴圈確實跑一次，
        # 才有一個「最後一次逐股呼叫」可供本測試釘住順序。
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 15), "tpex": _dt.date(2026, 9, 15),
        }
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 8,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0, "total": 2,
            "outcomes_by_item": {"twse": OK, "tpex": OK}})

        writer = MagicMock()
        parent = MagicMock()
        parent.attach_mock(manager.db_writer.fetch_feature_lag, "fetch_feature_lag")
        parent.attach_mock(
            manager.run_twse_pipeline_from_candidate_prices, "run_twse")
        parent.attach_mock(writer.write, "writer_write")
        parent.attach_mock(manager.trend_discover.run_discovery, "run_discovery")

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 16)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: writer):
            manager.run_all_daily_tasks()

        names = [c[0] for c in parent.mock_calls]
        for required in ("run_twse", "writer_write",
                          "fetch_feature_lag", "run_discovery"):
            self.assertIn(required, names,
                          "%s 未被呼叫，無法比較呼叫順序" % required)

        idx_run_twse_last = max(i for i, n in enumerate(names) if n == "run_twse")
        idx_writer_write_first = names.index("writer_write")
        idx_fetch_feature_lag = names.index("fetch_feature_lag")
        idx_run_discovery = names.index("run_discovery")

        self.assertLess(
            idx_run_twse_last, idx_fetch_feature_lag,
            "fetch_feature_lag() 必須排在最後一次逐股管線呼叫之後")
        self.assertLess(
            idx_writer_write_first, idx_fetch_feature_lag,
            "fetch_feature_lag() 必須排在逐股階段 run_log_writer.write() 之後")
        self.assertLess(
            idx_fetch_feature_lag, idx_run_discovery,
            "fetch_feature_lag() 必須排在 AI 熱門詞探索之前")

    def test_missing_backfill_origin_rejects_execution(self):
        """對應審查方段 A 複核要求的補測項 2（後半）：某市場在 candidate_prices

        沒有任何既有列（`fetch_candidate_prices_max_date_by_market()` 回傳 `None`）時，
        必須整個拒絕執行，零請求送出，不得預設成任何日期後靜默只跑單日。
        """
        import main_etl_pipeline as mep
        from src.extractors.market_report_fetcher import MissingBackfillOriginError

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": None, "tpex": _dt.date(2026, 9, 4),
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_price_batch = MagicMock()

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 8)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            with self.assertRaises(MissingBackfillOriginError):
                manager.run_all_daily_tasks()

        self.assertEqual(
            manager.run_price_batch.call_count, 0,
            "twse 沒有起點時必須零請求送出，不得先跑 tpex 或任何一天",
        )

    def test_same_day_rerun_skips_batch_but_runs_rest(self):
        """對應審查方段 A 複核要求的補測項 3：`max(trade_date)` 已等於

        `previous_business_day()`（同日重跑）時，`run_price_batch` 零呼叫，
        但 PTT／NLP／特徵／尾端掛點照常執行——`test_no_gap_returns_empty_list`
        只測了純函式本身，沒測編排層是否真的照這個結果跳過批次階段。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        same_day = _dt.date(2026, 9, 8)
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": same_day, "tpex": same_day,
        }
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 4),
            "n_lag": 1,
        }
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_nlp_sentiment_pipeline = MagicMock()
        manager.run_feature_engineering_pipeline = MagicMock()
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()

        with patch.object(mep, "previous_business_day", return_value=same_day), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        self.assertEqual(manager.run_price_batch.call_count, 0,
                         "缺口為空時 run_price_batch 不應被呼叫")
        manager.run_nlp_sentiment_pipeline.assert_called_once()
        manager.run_feature_engineering_pipeline.assert_called_once()
        manager.run_triple_barrier_tail_recompute.assert_called_once()


class FetchCandidatePricesMaxDateByMarket(unittest.TestCase):
    """對應審查方段 A 複核要求的補測項 2（前半）：新 `DBWriter` 方法的單元測試。

    沿用 `tests/test_db_read_semantics.py` 既有的 `psycopg2.connect` mock 模式。
    """

    def _mock_cursor(self, rows):
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchall.return_value = rows
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        return conn

    def test_maps_source_to_market(self):
        """`source` 值域（`twse_mi_index`／`tpex_daily_quotes`）正確對映到 `twse`／`tpex`。"""
        from src.loaders.db_writer import DBWriter

        writer = DBWriter(db_config={"database": "d", "user": "u", "password": "<test>"})
        conn = self._mock_cursor([
            ("twse_mi_index", _dt.date(2026, 9, 4)),
            ("tpex_daily_quotes", _dt.date(2026, 9, 3)),
        ])
        with patch("src.loaders.db_writer.psycopg2.connect", return_value=conn):
            result = writer.fetch_candidate_prices_max_date_by_market()

        self.assertEqual(result, {
            "twse": _dt.date(2026, 9, 4), "tpex": _dt.date(2026, 9, 3),
        })

    def test_missing_market_is_none_not_absent_key(self):
        """某市場在 `candidate_prices` 沒有任何列時，回傳字典中該市場的值為 `None`，

        **不是缺鍵**（呼叫端才能用 `dict[market] is None` 判斷，不需要 `.get()` 猜測）。
        """
        from src.loaders.db_writer import DBWriter

        writer = DBWriter(db_config={"database": "d", "user": "u", "password": "<test>"})
        conn = self._mock_cursor([("twse_mi_index", _dt.date(2026, 9, 4))])
        with patch("src.loaders.db_writer.psycopg2.connect", return_value=conn):
            result = writer.fetch_candidate_prices_max_date_by_market()

        self.assertIn("tpex", result)
        self.assertIsNone(result["tpex"])
        self.assertEqual(result["twse"], _dt.date(2026, 9, 4))


class FetchFeatureLagMethodTests(unittest.TestCase):
    """`DBWriter.fetch_feature_lag()` 本身的單元測試（§0.5 #30）。

    `test_tail_recompute_handles_empty_feature_table`（走
    `run_all_daily_tasks()` 全流程、mock 掉 `fetch_feature_lag` 本身）在修法前
    就已經通過——本次價格缺口剛好也是 0，舊的 `n_new_days` 邏輯同樣不傳
    `tail_window`，兩版程式碼巧合同答案，**該測試對 F=None 這個分支不具
    偵測力**（§9A.1）。真正會被 F=None 短路邏輯改變行為的地方是
    `fetch_feature_lag()` 內部本身，因此在這裡直接單元測試它：F=None 時
    只執行 2 次查詢（不含第三條 COUNT），若有人刪掉短路改成一律執行
    第三條查詢，`execute.call_count` 會從 2 變 3，這裡會 FAIL。
    """

    def _mock_cursor(self, fetchone_values):
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchone.side_effect = [(v,) for v in fetchone_values]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_empty_feature_table_short_circuits_third_query(self):
        from src.loaders.db_writer import DBWriter

        writer = DBWriter(db_config={"database": "d", "user": "u", "password": "<test>"})
        # 第一次 fetchone → F=None；第二次 fetchone → P=2026-09-16。
        # 短路生效時不會有第三次 fetchone。
        conn, cursor = self._mock_cursor([None, _dt.date(2026, 9, 16)])
        with patch("src.loaders.db_writer.psycopg2.connect", return_value=conn):
            result = writer.fetch_feature_lag()

        self.assertEqual(result, {
            "feature_max_date": None,
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 0,
        })
        self.assertEqual(
            cursor.execute.call_count, 2,
            "F=None 時應短路，只執行 F／P 兩條 MAX 查詢，不執行第三條 COUNT",
        )

    def test_non_empty_feature_table_runs_count_query(self):
        from src.loaders.db_writer import DBWriter

        writer = DBWriter(db_config={"database": "d", "user": "u", "password": "<test>"})
        conn, cursor = self._mock_cursor(
            [_dt.date(2026, 9, 4), _dt.date(2026, 9, 16), 8])
        with patch("src.loaders.db_writer.psycopg2.connect", return_value=conn):
            result = writer.fetch_feature_lag()

        self.assertEqual(result, {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 8,
        })
        self.assertEqual(cursor.execute.call_count, 3)
        third_call_sql = cursor.execute.call_args_list[2].args[0]
        self.assertIn("COUNT(DISTINCT trade_date)", third_call_sql)


if __name__ == "__main__":
    unittest.main()
