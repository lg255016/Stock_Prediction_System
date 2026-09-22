import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from scheduler import is_trading_weekday, get_next_run_time, TARGET_HOUR, TARGET_MINUTE
from src.ui.data_loader import get_available_stocks, load_ai_discovered_keywords, DataMode
from src.ui.components import render_ai_trend_discovery_badge
from main_etl_pipeline import ETLPipelineManager


class SchedulerUnitTests(unittest.TestCase):
    """測試定時排程器之交易日與觸發時間計算"""

    def test_is_trading_weekday(self):
        # 2026-08-17 (週一) -> True
        mon = datetime(2026, 8, 17, 10, 0)
        self.assertTrue(is_trading_weekday(mon))

        # 2026-08-21 (週五) -> True
        fri = datetime(2026, 8, 21, 15, 30)
        self.assertTrue(is_trading_weekday(fri))

        # 2026-08-22 (週六) -> False
        sat = datetime(2026, 8, 22, 12, 0)
        self.assertFalse(is_trading_weekday(sat))

        # 2026-08-23 (週日) -> False
        sun = datetime(2026, 8, 23, 12, 0)
        self.assertFalse(is_trading_weekday(sun))

    def test_get_next_run_time_same_day_morning(self):
        # 週二早上 10:00 -> 當天 15:35
        tue_morning = datetime(2026, 8, 18, 10, 0)
        next_run = get_next_run_time(tue_morning, target_hour=15, target_minute=35)
        self.assertEqual(next_run, datetime(2026, 8, 18, 15, 35))

    def test_get_next_run_time_same_day_evening_rolls_to_tomorrow(self):
        # 週二晚上 18:00 -> 週三 15:35
        tue_evening = datetime(2026, 8, 18, 18, 0)
        next_run = get_next_run_time(tue_evening, target_hour=15, target_minute=35)
        self.assertEqual(next_run, datetime(2026, 8, 19, 15, 35))

    def test_get_next_run_time_friday_evening_rolls_to_monday(self):
        # 週五晚上 18:00 -> 週一 15:35
        fri_evening = datetime(2026, 8, 21, 18, 0)
        next_run = get_next_run_time(fri_evening, target_hour=15, target_minute=35)
        self.assertEqual(next_run, datetime(2026, 8, 24, 15, 35))

    def test_get_next_run_time_weekend_rolls_to_monday(self):
        # 週六 -> 週一 15:35
        sat = datetime(2026, 8, 22, 14, 0)
        next_run = get_next_run_time(sat, target_hour=15, target_minute=35)
        self.assertEqual(next_run, datetime(2026, 8, 24, 15, 35))


class CustomStockAndTrendDiscoveryUITests(unittest.TestCase):
    """測試 UI 自選股管理與 AI 熱門探索詞載入"""

    def test_get_available_stocks_with_custom_stocks(self):
        # 1. 預設清單
        default_stocks = get_available_stocks()
        self.assertIn("2330", default_stocks)
        self.assertIn("NVDA", default_stocks)

        # 2. 加入使用者自選股
        custom = {"2454": "聯發科 (2454)", "TSLA": "特斯拉 (TSLA)"}
        all_stocks = get_available_stocks(custom)
        self.assertIn("2454", all_stocks)
        self.assertIn("TSLA", all_stocks)
        self.assertIn("2330", all_stocks)
        self.assertEqual(all_stocks["2454"], "聯發科 (2454)")

    def test_load_ai_discovered_keywords_returns_real_mode_when_db_has_data(self):
        """
        HERM-01／HERM-B 修復：mock DBWriter 使測試真正命中 REAL 路徑（有真實資料）。
        原測試名稱宣稱測 fallback，但未 mock 時測到的路徑隨環境而定——若 DB 剛好有資料，
        測到的根本不是 fallback。拆成本測試（REAL）與下一個測試（ERROR fallback），
        兩者都是確定性的。
        """
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
            mock_writer_cls.return_value.fetch_ai_discovered_keywords.return_value = ["矽光子", "散熱模組"]
            keywords, mode = load_ai_discovered_keywords(limit=6)

        self.assertEqual(mode, DataMode.REAL)
        self.assertEqual(keywords, ["矽光子", "散熱模組"])

    def test_load_ai_discovered_keywords_falls_back_when_db_fails(self):
        """
        HERM-01／HERM-B 修復：mock DBWriter 拋出例外，確定性地測到 fallback 路徑本身。
        DEC-012 方案 B：ERROR 不自動退回展示詞，回傳空清單與 DataMode.ERROR。
        """
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
            mock_writer_cls.return_value.fetch_ai_discovered_keywords.side_effect = ConnectionError("db down")
            keywords, mode = load_ai_discovered_keywords(limit=6)

        self.assertEqual(mode, DataMode.ERROR)
        self.assertEqual(keywords, [])

    def test_load_ai_discovered_keywords_empty_result_is_empty_mode(self):
        """DB 連線成功但查無關鍵字時，回傳 DataMode.EMPTY，與 ERROR 明確區分。"""
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
            mock_writer_cls.return_value.fetch_ai_discovered_keywords.return_value = []
            keywords, mode = load_ai_discovered_keywords(limit=6)

        self.assertEqual(mode, DataMode.EMPTY)
        self.assertEqual(keywords, [])

    def test_load_ai_discovered_keywords_demo_mode_bypasses_db(self):
        """demo=True 是 DataMode.DEMO 的唯一合法入口，完全不觸及 DBWriter。"""
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
            keywords, mode = load_ai_discovered_keywords(limit=6, demo=True)
            mock_writer_cls.assert_not_called()

        self.assertEqual(mode, DataMode.DEMO)
        self.assertGreaterEqual(len(keywords), 1)

    def test_render_ai_trend_discovery_badge(self):
        # 驗證在輕量環境下安全調用無異常
        render_ai_trend_discovery_badge(["矽光子", "散熱模組", "CoWoS"], mode=DataMode.REAL)


class DynamicPipelineUnitTests(unittest.TestCase):
    """測試主 ETL 流程之動態日期與標的載入"""

    def test_pipeline_dynamic_targets_and_keywords(self):
        pipeline = ETLPipelineManager.__new__(ETLPipelineManager)
        mock_db = MagicMock()
        mock_db.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"},
            {"stock_id": "NVDA", "market": "US"}
        ]
        mock_db.fetch_active_keywords.return_value = ["台積電", "AI"]
        # 首次每日 ETL 缺口自動追補（FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md）：
        # run_all_daily_tasks() 現在會先查每市場現有最新日期算缺口——固定成
        # 「昨天」，缺口序列剛好是 [previous_business_day()] 一天，等同本檔
        # 修改前的單日語意，既有測試斷言不必改。
        from main_etl_pipeline import previous_business_day as _pbd
        _one_day_ago = _pbd() - timedelta(days=1)
        mock_db.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _one_day_ago, "tpex": _one_day_ago}
        # §0.5 #30：run_all_daily_tasks() 逐股階段後會查 fetch_feature_lag() 算
        # n_lag（供尾端掛點視窗使用），與這裡的價格缺口 mock 是兩個獨立的來源——
        # 固定退化成 n_lag=1，等同修改前 tail_window=holding_period+1 的既有行為，
        # 不影響本測試原有斷言。
        mock_db.fetch_feature_lag.return_value = {
            "feature_max_date": _one_day_ago,
            "price_max_date": _one_day_ago,
            "n_lag": 1,
        }
        pipeline.db_writer = mock_db
        pipeline.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        pipeline.db_writer.fetch_last_discovery_probed_date.return_value = None
        pipeline.trend_discover.run_discovery.return_value = ("OK", None)
        pipeline.run_twse_pipeline_from_candidate_prices = MagicMock(return_value="OK")
        pipeline.run_us_stock_pipeline = MagicMock()
        # UG-G2-SB7 第 5 項：每日任務改走**一次看板抓取**，
        # 接縫由 `run_ptt_pipeline` 變成 `run_ptt_board_pipeline`。
        # mock 必須回傳 `{keyword: outcome}` —— 回傳 MagicMock 會被
        # RunLogEntry 的窮舉擋下。
        # ⚠ 這是 §0.5 #17 的**第五次**表現，也是最貴的一次：
        #   改動 `run_all_daily_tasks` 的取數方式時，
        #   需要編輯三個**不測試取數方式**的檔案。
        #   **耦合才是缺陷，mock 不完整只是表現形式。**
        pipeline.run_ptt_board_pipeline = MagicMock(
            return_value={"台積電": ("OK", None), "AI": ("OK", None)})
        pipeline.run_nlp_sentiment_pipeline = MagicMock()
        pipeline.run_feature_engineering_pipeline = MagicMock()
        # UG-G2-SB7：`run_all_daily_tasks` 新增了「全市場批次取價」階段，
        # **它會觸網**。本測試沿用本檔既有的隔離慣例（在 instance 上替換方法），
        # 把該階段一併換掉 —— **否則單元測試會對政府單位的服務發出請求**。
        # 回傳值必須符合 `run_price_batch` 的契約（含 `outcomes_by_item`）——
        # 少了它，`run_all_daily_tasks` 會 raise。
        # ⚠ **那個 raise 是刻意的**：逐股階段需要用批次的 outcome 歸因
        #   「上櫃標的沒有列」，缺了它就只能猜（UG-G2-SB7，2026-09-04）。
        pipeline.run_price_batch = MagicMock(return_value={
            "OK": 2, "NO_DATA": 0, "FETCH_FAILED": 0, "REFUSED": 0,
            "total": 2, "outcomes_by_item": {"twse": "OK", "tpex": "OK"}})
        # run log 寫入端同屬外部相依（比照 db_writer 一併隔離）。
        # 回 None = 「本次不寫稽核紀錄」，`run_all_daily_tasks` 已處理該情形。
        # ⚠ **生產行為刻意不同**：那裡若寫不進 `etl_run_log`，例外會往上傳、
        #   讓執行失敗 —— **稽核紀錄靜默缺席，比執行失敗更糟**。
        pipeline._run_log_writer = lambda: None

        pipeline.run_all_daily_tasks()

        # 驗證有針對動態股票標的呼叫對應管線
        pipeline.run_twse_pipeline_from_candidate_prices.assert_called()
        pipeline.run_us_stock_pipeline.assert_called()
        pipeline.run_ptt_board_pipeline.assert_called()

    def test_upsert_ml_features_handles_date_objects_and_pads_missing_columns_to_29(self):
        """驗證 upsert_ml_features 能處理 datetime.date 物件，並將未提供的欄位補 NULL 至 29 欄契約（UG-G2-SB1）"""
        from datetime import date
        import pandas as pd
        from src.loaders.db_writer import DBWriter

        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        # 建立僅具備部分特徵欄位、trade_date 為 datetime.date 的 DataFrame
        # （刻意不包含 CORE_16／留言／target_triple_barrier／label_reason 等尚未實作的欄位）
        df_partial_features = pd.DataFrame({
            "trade_date": [date(2026, 8, 19), date(2026, 8, 20)],
            "stock_id": ["2330", "2330"],
            "close_price": [1000.0, 1020.0],
            "volume": [30000, 35000],
            "article_count": [10, 15],
            "sentiment_mean": [0.65, 0.72],
            "sentiment_3d_ma": [0.60, 0.68],
            "return_1d": [0.01, 0.02],
            "bullishness_index": [0.35, 0.45],
            "agreement_index": [0.80, 0.85],
            "rsi_14": [55.0, 60.0],
            "volatility_20d": [0.18, 0.19],
            "source_status": ["SUCCESS", "SUCCESS"],
        })

        writer.upsert_ml_features(df_partial_features)

        writer._execute_batch.assert_called_once()
        query, records = writer._execute_batch.call_args[0]

        # 驗證傳入 SQL 的每一筆 tuple 恰好有 29 個元素 (符合 daily_ml_features 29 欄契約)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(records[0]), 29)
        self.assertEqual(records[0][0], "2026-08-19")
        self.assertEqual(records[0][1], "2330")
        # 未提供的欄位（如 amplitude_ratio、label_reason）必須是 None，不得被補 0 或中立值
        amplitude_ratio_idx = DBWriter.ML_FEATURE_COLUMNS.index("amplitude_ratio")
        label_reason_idx = DBWriter.ML_FEATURE_COLUMNS.index("label_reason")
        self.assertIsNone(records[0][amplitude_ratio_idx])
        self.assertIsNone(records[0][label_reason_idx])


if __name__ == "__main__":
    unittest.main()

