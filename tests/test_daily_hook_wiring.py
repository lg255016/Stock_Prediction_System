# -*- coding: utf-8 -*-
"""
UG-G3-SB2 §3.1 每日尾端重算掛點啟用測試。

PO 2026-09-10 binding confirmation：`run_all_daily_tasks()` 加一行呼叫
`self.run_triple_barrier_tail_recompute()`，位置緊接
`run_feature_engineering_pipeline()` 之後。**僅授權接線本身**——`main_etl_pipeline.py`
一行 + 本檔測試；`run_all_daily_tasks()` 實際執行仍受
`doc/governance/PROJECT_STATUS.md` §0.5 #20 閘門限制（`UG-G3-SB2a` Gate B
通過前不得執行），本檔全程使用 MagicMock，不建立任何真實連線、不觸網。

三項斷言（PO 指定）：
1. 呼叫順序：`run_feature_engineering_pipeline` 先、`run_triple_barrier_tail_recompute` 後。
2. 掛點回傳 `n_updated != len(tail)` 時，WARNING 訊息被印出（`contextlib.redirect_stdout` 抓）。
3. 全程不建立真實連線（`psycopg2.connect` 未被呼叫）。
"""
import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

if "psycopg2" not in sys.modules:
    _psycopg2_stub = types.ModuleType("psycopg2")
    _psycopg2_stub.connect = MagicMock()
    _psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    _psycopg2_extras_stub.execute_values = MagicMock()
    _psycopg2_stub.extras = _psycopg2_extras_stub
    sys.modules["psycopg2"] = _psycopg2_stub
    sys.modules["psycopg2.extras"] = _psycopg2_extras_stub

import pandas as pd

from main_etl_pipeline import ETLPipelineManager


def _mk_pipeline_with_mocks():
    """比照 tests/test_operational_ux.py::test_pipeline_dynamic_targets_and_keywords
    的既有隔離慣例——在 instance 上逐一替換方法，全程不觸網、不連真實 DB。
    只設定一檔 TWSE 標的，避開 TPEX／US 分支需要的額外 mock。"""
    pipeline = ETLPipelineManager.__new__(ETLPipelineManager)
    mock_db = MagicMock()
    mock_db.fetch_active_stock_targets.return_value = [
        {"stock_id": "2330", "market": "TWSE"},
    ]
    mock_db.fetch_active_keywords.return_value = ["台積電"]
    # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
    # n_lag（供尾端掛點視窗使用）——本檔原未設定此 mock，Stage A 測試套件
    # 執行時發現 MagicMock 預設回傳值不支援 `>` 比較而 TypeError（不在 PO
    # 原先指名的既有四個測試檔之列，屬同一機制的必然連帶影響，僅補 mock，
    # 不改動任何既有斷言）。固定退化成 n_lag=1，等同修改前
    # tail_window=holding_period+1 的既有行為。
    mock_db.fetch_feature_lag.return_value = {
        "feature_max_date": None,
        "price_max_date": None,
        "n_lag": 1,
    }
    pipeline.db_writer = mock_db
    pipeline.trend_discover = MagicMock()
    # §0.5 #31：同上方 fetch_feature_lag() 註解，run_all_daily_tasks() 探索段
    # 新增 fetch_last_discovery_probed_date() 查詢與 run_discovery() 回傳值解包，
    # 僅補 mock，不改動任何既有斷言。
    mock_db.fetch_last_discovery_probed_date.return_value = None
    pipeline.trend_discover.run_discovery.return_value = ("OK", None)
    pipeline.run_twse_pipeline_from_candidate_prices = MagicMock(return_value="OK")
    pipeline.run_us_stock_pipeline = MagicMock()
    pipeline.run_ptt_board_pipeline = MagicMock(
        return_value={"台積電": ("OK", None)})
    pipeline.run_nlp_sentiment_pipeline = MagicMock()
    pipeline.run_price_batch = MagicMock(return_value={
        "OK": 1, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
        "total": 1, "outcomes_by_item": {"twse": "OK", "tpex": "OK"}})
    pipeline._run_log_writer = lambda: None
    return pipeline, mock_db


class DailyHookCallOrderTests(unittest.TestCase):

    def test_tail_recompute_called_after_feature_engineering(self):
        pipeline, _mock_db = _mk_pipeline_with_mocks()
        call_order = []
        pipeline.run_feature_engineering_pipeline = MagicMock(
            side_effect=lambda: call_order.append("feature_engineering"))
        # §0.5 #30 後 tail_window 可能被帶入呼叫（本檔固定 n_lag=1 時會傳
        # tail_window=6）——side_effect 需接受任意關鍵字引數，呼叫順序斷言
        # 本身不變。
        pipeline.run_triple_barrier_tail_recompute = MagicMock(
            side_effect=lambda **kw: call_order.append("tail_recompute"))

        pipeline.run_all_daily_tasks()

        pipeline.run_feature_engineering_pipeline.assert_called_once()
        pipeline.run_triple_barrier_tail_recompute.assert_called_once()
        self.assertEqual(call_order, ["feature_engineering", "tail_recompute"])


class DailyHookWarningTests(unittest.TestCase):
    """直接呼叫 `run_triple_barrier_tail_recompute()`（非經 `run_all_daily_tasks()`），
    驗證 n_updated != len(tail) 時的既有 WARNING 行為（本方法既有邏輯，本測試
    只釘住接線後仍然成立，不是新增行為）。"""

    def test_prints_warning_when_update_count_mismatches_expected(self):
        n = 10
        dates = pd.bdate_range("2026-01-01", periods=n).strftime("%Y-%m-%d")
        df_prices = pd.DataFrame({
            "stock_id": ["A"] * n,
            "trade_date": dates,
            "open_price": [100] * n,
            "high_price": [101] * n,
            "low_price": [99] * n,
        })
        pipeline, mock_db = _mk_pipeline_with_mocks()
        mock_db.fetch_data.return_value = df_prices
        mock_db.update_triple_barrier_tail_labels.return_value = 3  # 應為 6（holding_period+1=5+1），刻意不符

        buf = io.StringIO()
        with redirect_stdout(buf):
            pipeline.run_triple_barrier_tail_recompute()

        output = buf.getvalue()
        self.assertIn(
            "[WARNING] Triple-Barrier 尾端重算：實際影響列數 3 != 預期 6", output,
        )


class DailyHookNoRealConnectionTests(unittest.TestCase):

    def test_no_real_db_connection_established_during_daily_tasks(self):
        pipeline, _mock_db = _mk_pipeline_with_mocks()
        pipeline.run_feature_engineering_pipeline = MagicMock()
        pipeline.run_triple_barrier_tail_recompute = MagicMock()

        with patch("psycopg2.connect") as mock_connect:
            pipeline.run_all_daily_tasks()

        mock_connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
