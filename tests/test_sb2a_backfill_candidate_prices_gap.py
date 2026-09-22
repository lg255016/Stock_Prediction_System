# -*- coding: utf-8 -*-
"""
`scripts/verify/ug_g3_sb2a_backfill_candidate_prices_gap.py` 的
`run_gap_backfill()` 單元測試（PO 2026-09-11 複核要求）。

只測 DEC-032 停止語意本身（mock `manager`，不觸網、不連 DB）。
`verify_gap_filled()`／`preview_gap()` 皆為唯讀 SQL 查詢，不在本檔測試
範圍——與段 1、段 2 基線比對腳本的測試範圍劃分一致：純邏輯測邏輯，
真實庫互動另外唯讀驗證（見 binding confirmation 證據）。
"""
import unittest
from unittest.mock import MagicMock

from scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap import (
    GAP_TRADE_DATES,
    run_gap_backfill,
    _validate_dates_subset,
    _validate_markets_subset,
)
from src.extractors.market_report_fetcher import ServiceRefusedError


class RunGapBackfillTests(unittest.TestCase):

    def test_service_refused_on_third_day_stops_immediately(self):
        """**known-FAIL 要求（DEC-032）**：第 3 天遇到 `ServiceRefusedError`
        時，`completed` 必須只有前 2 天，第 3 天以後**完全不呼叫**
        `run_price_batch`——不是「記錄失敗後繼續」，是「立即停止」。
        """
        manager = MagicMock()
        call_log = []

        def side_effect(trade_date, **kwargs):
            call_log.append(trade_date)
            if len(call_log) == 3:
                raise ServiceRefusedError("HTTP 429（模擬）")
            return {"OK": 2, "total": 2}

        manager.run_price_batch = MagicMock(side_effect=side_effect)

        completed, refused_at = run_gap_backfill(manager, run_log_writer=None)

        self.assertEqual(len(completed), 2,
                         "第 3 天被拒前只有前 2 天成功——不得多也不得少")
        self.assertEqual(refused_at, GAP_TRADE_DATES[2])
        self.assertEqual(
            manager.run_price_batch.call_count, 3,
            "呼叫到第 3 天（觸發拒絕）為止，第 4 天以後完全不得呼叫")

    def test_all_eight_days_succeed_returns_no_refusal(self):
        """8 天全數成功時，`completed` 含全部 8 天，`refused_at` 為
        `None`——對照組，確認「正常路徑」與「DEC-032 中止路徑」的回傳
        形狀不同，呼叫端才能用 `if refused_at:` 正確分流。
        """
        manager = MagicMock()
        manager.run_price_batch = MagicMock(return_value={"OK": 2, "total": 2})

        completed, refused_at = run_gap_backfill(manager, run_log_writer=None)

        self.assertEqual(len(completed), len(GAP_TRADE_DATES))
        self.assertIsNone(refused_at)
        self.assertEqual(manager.run_price_batch.call_count, len(GAP_TRADE_DATES))

    def test_stopping_is_load_bearing(self):
        """**known-FAIL 案例（PO 2026-09-11 要求）**：把 `run_gap_backfill`
        原始碼裡的 `break`（立即停止）改成 `continue`（記錄後繼續），
        用 `test_service_refused_on_third_day_stops_immediately` 的同一套
        斷言重跑**那個變異版本**——必須 FAIL。**不是在測試檔外重寫一段
        相似邏輯**（那證明不了 `run_gap_backfill` 本體的行為），是真的用
        `inspect.getsource()` 取出本體原始碼、只動一個關鍵字、`exec` 成
        獨立函式後跑同一套斷言。
        """
        import inspect
        import scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap as mod

        source = inspect.getsource(mod.run_gap_backfill)
        self.assertIn("break", source, "前提：原始碼裡確實有 break 可供變異")
        mutated_source = source.replace("break", "continue", 1)
        self.assertNotEqual(mutated_source, source)

        namespace = dict(vars(mod))
        exec(compile(mutated_source, "<mutated_run_gap_backfill>", "exec"), namespace)
        mutated_run_gap_backfill = namespace["run_gap_backfill"]

        manager = MagicMock()
        call_log = []

        def side_effect(trade_date, **kwargs):
            call_log.append(trade_date)
            if len(call_log) == 3:
                raise ServiceRefusedError("HTTP 429（模擬）")
            return {"OK": 2, "total": 2}

        manager.run_price_batch = MagicMock(side_effect=side_effect)

        completed, refused_at = mutated_run_gap_backfill(manager, run_log_writer=None)

        # 變異版本（continue）會處理全部 8 天，只有觸發例外的第 3 天沒有
        # 進入 completed（成功清單），其餘 7 天（含被拒之後的第 4~8 天，
        # 正確版本完全不會呼叫到）照樣成功——與正確版本（只完成前 2 天）
        # 不同，用這個差異證明測試真的有偵測力，不是巧合通過。
        self.assertNotEqual(
            len(completed), 2,
            "變異版本（continue）不應該只完成 2 天——若這裡也是 2 天，"
            "代表變異沒有真的改到行為，測試本身沒有偵測力")
        self.assertEqual(
            len(completed), len(GAP_TRADE_DATES) - 1,
            "continue 版本吞掉第 3 天的例外後繼續，8 天中只有第 3 天"
            "沒有進入 completed，其餘 7 天（含第 4~8 天）照常執行")
        self.assertEqual(manager.run_price_batch.call_count, len(GAP_TRADE_DATES),
                         "continue 版本會呼叫到全部 8 天，不會提早停止")


class DatesAndMarketsSubsetValidationTests(unittest.TestCase):
    """`--dates`／`--markets` 參數驗證（PO 2026-09-11 要求，08-25／08-26
    TPEX 重試場景）：本腳本是**重試工具**，不是任意日期批次抓取器，
    範圍外的輸入一律拒絕，不得默默接受。"""

    def test_date_outside_gap_trade_dates_is_rejected(self):
        with self.assertRaises(SystemExit):
            _validate_dates_subset("2026-08-25,2026-09-10")  # 09-10 不在清單內

    def test_date_subset_within_gap_trade_dates_is_accepted(self):
        result = _validate_dates_subset("2026-08-25,2026-08-26")
        self.assertEqual(result, ["2026-08-25", "2026-08-26"])

    def test_none_dates_defaults_to_full_gap_list(self):
        self.assertEqual(_validate_dates_subset(None), list(GAP_TRADE_DATES))

    def test_market_outside_allowed_set_is_rejected(self):
        with self.assertRaises(SystemExit):
            _validate_markets_subset("twse,nyse")  # nyse 不支援

    def test_market_subset_is_accepted(self):
        self.assertEqual(_validate_markets_subset("tpex"), ("tpex",))

    def test_none_markets_defaults_to_both(self):
        self.assertEqual(_validate_markets_subset(None), ("twse", "tpex"))


class RunGapBackfillMarketsParamTests(unittest.TestCase):
    """**known-FAIL 要求**：`--markets tpex` 必須讓 `run_price_batch` 只收到
    `markets=("tpex",)`——不得悄悄還是兩個市場都打（08-25／08-26 的 TWSE
    端已經成功，重試不該再打一次）。"""

    def test_markets_tpex_only_calls_run_price_batch_with_tpex(self):
        manager = MagicMock()
        manager.run_price_batch = MagicMock(return_value={"OK": 1, "total": 1})

        run_gap_backfill(
            manager, run_log_writer=None,
            gap_dates=["2026-08-25", "2026-08-26"], markets=("tpex",))

        self.assertEqual(manager.run_price_batch.call_count, 2)
        for call in manager.run_price_batch.call_args_list:
            self.assertEqual(
                call.kwargs.get("markets"), ("tpex",),
                "markets 引數必須原樣傳給 run_price_batch，不得悄悄變回兩個市場")

    def test_default_markets_still_calls_both(self):
        """對照組：不指定 `markets` 時維持原行為（兩個市場皆呼叫）——
        確認新增參數沒有改變既有預設路徑。"""
        manager = MagicMock()
        manager.run_price_batch = MagicMock(return_value={"OK": 2, "total": 2})

        run_gap_backfill(
            manager, run_log_writer=None, gap_dates=["2026-08-24"])

        call = manager.run_price_batch.call_args_list[0]
        self.assertEqual(call.kwargs.get("markets"), ("twse", "tpex"))


if __name__ == "__main__":
    unittest.main()
