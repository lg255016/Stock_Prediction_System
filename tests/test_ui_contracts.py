import json
import os
import tempfile
import unittest
import numpy as np
import pandas as pd

from src.ml.model_trainer import ALL_MULTIMODAL_FEATURE_COLS
from src.ui.styles import (
    get_market_colors,
    render_kpi_card_html,
    COLOR_TAIWAN_UP,
    COLOR_TAIWAN_DOWN,
    COLOR_US_UP,
    COLOR_US_DOWN,
)
from src.ui.data_loader import (
    get_available_stocks,
    load_stock_features,
    load_stock_articles,
    get_champion_predictor,
    load_thematic_radar_data,
    load_tournament_results,
    _fetch_real_stock_features_from_db,
    generate_mock_ptt_articles,
    DataMode,
    DataSourceError,
)
from src.ui.charts import (
    render_price_sentiment_candlestick_chart,
    render_pnl_equity_curve_chart,
    render_feature_importance_bar_chart,
)
from src.ui.components import (
    FEATURE_DISPLAY_NAMES,
    render_thematic_radar,
    render_raw_article_table,
    render_tournament_leaderboard,
)


def _valid_tournament_payload():
    """建立一份符合 load_tournament_results 契約的最小合法 artifact 內容，供測試共用。"""
    row_template = {
        "experiment_id": "EXP-RF-MM", "model_name": "random_forest", "feature_set": "MultiModal (18 Feat)",
        "macro_f1": 0.58, "accuracy": 0.6, "roc_auc": 0.61, "directional_hit_ratio": 0.58,
        "cumulative_return": 0.08, "sharpe_ratio": 1.1, "max_drawdown": 0.05,
    }
    return {
        "leaderboard": [row_template],
        "alpha_attribution": {"random_forest": {"delta_macro_f1": 0.05, "delta_cumulative_return": 0.03, "delta_hit_ratio": 0.02, "sentiment_effective": True}},
        "champion_model_name": "random_forest",
        "champion_score": 0.58,
    }


class StylesAndThemeTests(unittest.TestCase):
    """測試深色金融終端樣式與市場色彩語彙"""

    def test_get_market_colors_taiwan_and_us(self):
        # 1. 台股紅漲綠跌
        tw_colors = get_market_colors("TW")
        self.assertEqual(tw_colors["up"], COLOR_TAIWAN_UP)
        self.assertEqual(tw_colors["down"], COLOR_TAIWAN_DOWN)

        # 2. 美股綠漲紅跌
        us_colors = get_market_colors("US")
        self.assertEqual(us_colors["up"], COLOR_US_UP)
        self.assertEqual(us_colors["down"], COLOR_US_DOWN)

    def test_render_kpi_card_html_contains_expected_elements(self):
        html = render_kpi_card_html(
            title="收盤價",
            value="$1,000",
            delta="+2.5%",
            is_positive=True,
            icon="📈",
            badge="盤後",
            market="TW"
        )
        self.assertIn("kpi-card", html)
        self.assertIn("收盤價", html)
        self.assertIn("$1,000", html)
        self.assertIn("+2.5%", html)
        self.assertIn("badge-tag", html)


class DataLoaderContractTests(unittest.TestCase):
    """測試 UI 快取資料載入器與離線 Fallback 資料契約"""

    def test_get_available_stocks(self):
        stocks = get_available_stocks()
        self.assertIn("2330", stocks)
        self.assertIn("2382", stocks)
        self.assertIn("NVDA", stocks)
        self.assertIn("6488", stocks)

    def test_load_stock_features_returns_real_mode_with_mocked_db(self):
        """
        HERM-03 修復：以 mock DB 產生確定性資料，驗證 REAL 模式與欄位契約。
        原斷言 len(df)==30 對 live 資料硬編碼，真實 DB 若當日不足 30 筆即失敗，
        且無法區分「程式壞了」與「當日資料不足」——改為「mock 回傳幾列，就該回傳幾列」。
        """
        from unittest.mock import patch
        n_rows = 5
        df_mock_prices = pd.DataFrame({
            "trade_date": pd.date_range("2026-08-01", periods=n_rows),
            "stock_id": ["2330"] * n_rows,
            "open_price": [100.0] * n_rows,
            "high_price": [105.0] * n_rows,
            "low_price": [95.0] * n_rows,
            "close_price": [102.0] * n_rows,
            "volume": [10000] * n_rows,
        })
        df_mock_mapping = pd.DataFrame({"keyword": ["台積電"], "stock_id": ["2330"]})
        df_mock_theme = pd.DataFrame(columns=["theme_keyword", "stock_id", "relevance_weight"])
        df_mock_articles = pd.DataFrame(columns=[
            "article_id", "source", "fetch_keyword", "post_time",
            "title", "url", "author", "engagement_metric", "sentiment_score"
        ])

        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect"), \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "<test>"}
            mock_read_sql.side_effect = [df_mock_prices, df_mock_mapping, df_mock_theme, df_mock_articles]

            df, mode = load_stock_features("2330", days=30)

        self.assertEqual(mode, DataMode.REAL)
        self.assertEqual(len(df), n_rows)
        for col in ALL_MULTIMODAL_FEATURE_COLS:
            self.assertIn(col, df.columns)
        self.assertIn("target_return_1d", df.columns)
        self.assertIn("target_up_down", df.columns)

    def test_load_stock_features_returns_error_mode_when_db_fails(self):
        """
        HERM-03／HERM-E 修復：DB 連線失敗時回傳 DataMode.ERROR 與符合欄位契約的空表，
        不自動退回模擬資料（DEC-012 方案 B：連線失敗不得以假資料撐場面）。
        """
        from unittest.mock import patch
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect", side_effect=ConnectionError("db down")):
            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "<test>"}
            df, mode = load_stock_features("2330", days=30)

        self.assertEqual(mode, DataMode.ERROR)
        self.assertTrue(df.empty)
        for col in ALL_MULTIMODAL_FEATURE_COLS:
            self.assertIn(col, df.columns)  # 空表仍保有正確欄位契約，呼叫端可安全檢查 .columns

    def test_load_stock_features_demo_mode_bypasses_db_entirely(self):
        """demo=True 是 DataMode.DEMO 的唯一合法入口，且完全不觸及 DB。"""
        from unittest.mock import patch
        with patch("psycopg2.connect") as mock_connect:
            df, mode = load_stock_features("2330", days=10, demo=True)
            mock_connect.assert_not_called()

        self.assertEqual(mode, DataMode.DEMO)
        self.assertEqual(len(df), 10)

    def test_load_stock_articles_returns_expected_columns(self):
        """HERM-04 修復：mock DB 驗證 REAL 模式下的欄位契約，不依賴真實 DB 內容。"""
        from unittest.mock import patch
        df_mock_arts = pd.DataFrame({
            "publish_time": ["2026-08-01 10:00"],
            "stock_id": ["2330"],
            "title": ["台積電營收亮眼"],
            "sentiment_score": [0.8],
            "sentiment_label": ["看多"],
            "push_count": [10],
            "source": ["ptt_stock"],
            "url": ["https://ptt.cc/1"],
        })
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect") as mock_connect, \
             patch("pandas.read_sql", return_value=df_mock_arts):
            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "<test>"}
            mock_conn = mock_connect.return_value
            mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []

            df_articles, mode = load_stock_articles("2330", limit=10)

        self.assertEqual(mode, DataMode.REAL)
        self.assertIsInstance(df_articles, pd.DataFrame)
        expected_cols = ["publish_time", "stock_id", "title", "sentiment_score", "sentiment_label", "push_count", "source", "url"]
        for c in expected_cols:
            self.assertIn(c, df_articles.columns)

    def test_load_stock_articles_returns_error_mode_when_db_fails(self):
        """HERM-02／HERM-04／HERM-E 修復：DB 失敗回傳 DataMode.ERROR，不隱藏於「查無文章」的空表外觀之後。"""
        from unittest.mock import patch
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect", side_effect=ConnectionError("db down")):
            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "<test>"}
            df_articles, mode = load_stock_articles("2330", limit=10)

        self.assertEqual(mode, DataMode.ERROR)
        self.assertTrue(df_articles.empty)

    def test_get_champion_predictor_inference(self):
        """
        HERM-05 修復：以 demo=True 取得確定性合成特徵矩陣，測試目的是驗證 predictor 本身，
        不是 DB 層——demo 模式完全不觸及 DB，是這個測試目的最貼切、最單純的資料來源。
        """
        df_features, mode = load_stock_features("2330", days=40, demo=True)
        self.assertEqual(mode, DataMode.DEMO)
        predictor = get_champion_predictor(df_features)

        pred_res = predictor.predict_latest(df_features)
        self.assertEqual(pred_res["stock_id"], "2330")
        self.assertIn(pred_res["predicted_direction"], ("UP", "DOWN"))
        self.assertTrue(0.0 <= pred_res["confidence_score"] <= 1.0)
        self.assertGreaterEqual(len(pred_res["top_drivers"]), 1)

    def test_fetch_real_stock_features_without_name_error(self):
        """驗證 _fetch_real_stock_features_from_db 在無資料庫連線或各類情境下零 NameError 崩潰"""
        from unittest.mock import patch, MagicMock
        import pandas as pd
        # 測試在 Mock DB 下正常運作
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect") as mock_connect, \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer = mock_writer_cls.return_value
            mock_writer.db_config = {"database": "test", "user": "u", "password": "<test>"}
            mock_conn = mock_connect.return_value
            
            # 模擬 4 次 read_sql 呼叫：1. prices, 2. mapping, 3. theme_mapping, 4. articles
            df_mock_prices = pd.DataFrame({
                "trade_date": [pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-02")],
                "stock_id": ["2330", "2330"],
                "open_price": [1000.0, 1010.0],
                "high_price": [1020.0, 1030.0],
                "low_price": [990.0, 1000.0],
                "close_price": [1015.0, 1025.0],
                "volume": [30000, 35000]
            })
            df_mock_mapping = pd.DataFrame({"keyword": ["台積電", "2330"], "stock_id": ["2330", "2330"]})
            df_mock_theme = pd.DataFrame({"theme_keyword": ["矽光子"], "stock_id": ["2330"], "relevance_weight": [1.0]})
            df_mock_articles = pd.DataFrame({
                "article_id": [1],
                "source": ["ptt_stock"],
                "fetch_keyword": ["台積電"],
                "post_time": [pd.Timestamp("2026-08-01 10:00:00")],
                "title": ["台積電營收亮眼"],
                "url": ["https://ptt.cc/1"],
                "author": ["user1"],
                "engagement_metric": [10],
                "sentiment_score": [0.8]
            })

            mock_read_sql.side_effect = [df_mock_prices, df_mock_mapping, df_mock_theme, df_mock_articles]

            df_res = _fetch_real_stock_features_from_db("2330", days=30)
            self.assertIsNotNone(df_res)
            self.assertFalse(df_res.empty)
            self.assertIn("sentiment_mean", df_res.columns)
            self.assertIn("bullishness_index", df_res.columns)
            self.assertEqual(len(df_res), 2)
            self.assertEqual(df_res.iloc[-1]["close_price"], 1025.0)

    def test_load_thematic_radar_data_structure(self):
        """HERM-06 修復：mock DB 產生確定性題材資料，驗證 REAL 模式與結構契約。"""
        from unittest.mock import patch
        df_mock_mappings = pd.DataFrame({
            "theme_keyword": ["矽光子", "矽光子"],
            "stock_id": ["3081", "6442"],
            "stock_name": ["聯亞", "光聖"],
            "relevance_weight": [1.0, 0.9],
        })
        df_mock_stats = pd.DataFrame({
            "fetch_keyword": ["矽光子"],
            "article_count": [10],
            "pos_cnt": [7],
            "neg_cnt": [1],
        })
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect"), \
             patch("pandas.read_sql") as mock_read_sql:
            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "<test>"}
            mock_read_sql.side_effect = [df_mock_mappings, df_mock_stats]

            radar, mode = load_thematic_radar_data()

        self.assertEqual(mode, DataMode.REAL)
        self.assertIsInstance(radar, list)
        self.assertGreaterEqual(len(radar), 1)

        for theme in radar:
            self.assertIn("theme", theme)
            self.assertIn("article_count", theme)
            self.assertIn("bullishness", theme)
            self.assertIn("sentiment_label", theme)
            self.assertIn("stocks", theme)
            self.assertIsInstance(theme["stocks"], list)
            self.assertGreaterEqual(len(theme["stocks"]), 1)
            for s in theme["stocks"]:
                self.assertIn("stock_id", s)
                self.assertIn("name", s)
                self.assertIn("display", s)

    def test_load_thematic_radar_data_returns_error_mode_when_db_fails(self):
        """HERM-06／HERM-E 修復：DB 失敗回傳 DataMode.ERROR，不自動退回精選展示題材。"""
        from unittest.mock import patch
        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
             patch("psycopg2.connect", side_effect=ConnectionError("db down")):
            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "<test>"}
            radar, mode = load_thematic_radar_data()

        self.assertEqual(mode, DataMode.ERROR)
        self.assertEqual(radar, [])

    def test_load_tournament_results_empty_when_no_artifact(self):
        """artifact 檔案不存在 → EMPTY，不得回傳假排行榜資料。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "nonexistent.json")
            data, mode = load_tournament_results(artifact_path=missing_path)
        self.assertIsNone(data)
        self.assertEqual(mode, DataMode.EMPTY)

    def test_load_tournament_results_error_on_malformed_missing_keys(self):
        """artifact 存在但缺少必要頂層欄位（如 champion_model_name）→ ERROR。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "malformed.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"leaderboard": [_valid_tournament_payload()["leaderboard"][0]]}, f)
            data, mode = load_tournament_results(artifact_path=path)
        self.assertIsNone(data)
        self.assertEqual(mode, DataMode.ERROR)

    def test_load_tournament_results_error_on_leaderboard_row_missing_field(self):
        """artifact 頂層欄位齊全，但 leaderboard 列缺少必要欄位（如 macro_f1）→ ERROR。"""
        payload = _valid_tournament_payload()
        del payload["leaderboard"][0]["macro_f1"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bad_row.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            data, mode = load_tournament_results(artifact_path=path)
        self.assertIsNone(data)
        self.assertEqual(mode, DataMode.ERROR)

    def test_load_tournament_results_error_on_invalid_json(self):
        """artifact 存在但不是合法 JSON → ERROR，不得拋出未捕捉例外。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "not_json.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{this is not valid json")
            data, mode = load_tournament_results(artifact_path=path)
        self.assertIsNone(data)
        self.assertEqual(mode, DataMode.ERROR)

    def test_load_tournament_results_real_from_valid_artifact(self):
        """合法 artifact → REAL，且回傳內容原樣保留供 UI 層渲染。"""
        payload = _valid_tournament_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "valid.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            data, mode = load_tournament_results(artifact_path=path)
        self.assertEqual(mode, DataMode.REAL)
        self.assertEqual(data["champion_model_name"], "random_forest")
        self.assertEqual(len(data["leaderboard"]), 1)


class InteractiveChartsTests(unittest.TestCase):
    """測試 Plotly 雙 Y 軸互動圖表與策略曲線產生器"""

    def test_render_price_sentiment_candlestick_chart_structure(self):
        """HERM-07 修復：demo=True 取得確定性合成資料，測試目的是圖表結構，不是 DB 層。"""
        df, mode = load_stock_features("2330", days=30, demo=True)
        fig = render_price_sentiment_candlestick_chart(df, stock_title="2330 台積電", market="TW", mode=mode)
        self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))

    def test_render_pnl_equity_curve_chart_structure(self):
        """HERM-08 修復：demo=True 取得確定性合成資料，測試目的是圖表結構，不是 DB 層。"""
        df, mode = load_stock_features("2330", days=30, demo=True)
        fig = render_pnl_equity_curve_chart(df, market="TW", mode=mode)
        self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))

    def test_render_price_sentiment_candlestick_chart_error_mode_is_placeholder(self):
        """ERROR／EMPTY 模式回傳不含任何數值的佔位圖表，不嘗試對空 df 繪圖。"""
        empty_df = pd.DataFrame()
        fig = render_price_sentiment_candlestick_chart(empty_df, mode=DataMode.ERROR)
        self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))

    def test_render_feature_importance_bar_chart_structure(self):
        imp = {"bullishness_index": 0.35, "rsi_14": 0.25, "sentiment_3d_ma": 0.20}
        fig = render_feature_importance_bar_chart(imp)
        self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))


class UIComponentsTests(unittest.TestCase):
    """測試 AI 決策面板、可解釋性對照表、題材雷達與輿情明細表篩選邏輯"""

    def test_feature_display_names_mapping(self):
        self.assertIn("bullishness_index", FEATURE_DISPLAY_NAMES)
        self.assertIn("agreement_index", FEATURE_DISPLAY_NAMES)
        self.assertIn("rsi_14", FEATURE_DISPLAY_NAMES)
        self.assertIn("volatility_5d", FEATURE_DISPLAY_NAMES)
        self.assertIn("sentiment_mean", FEATURE_DISPLAY_NAMES)

    def test_article_table_filtering_logic(self):
        df_articles = generate_mock_ptt_articles("2330", limit=20)
        # 1. 依標籤篩選
        df_bull = df_articles[df_articles["sentiment_label"] == "看多"]
        if not df_bull.empty:
            self.assertTrue((df_bull["sentiment_label"] == "看多").all())

        # 2. 依關鍵字搜尋
        df_keyword = df_articles[df_articles["title"].str.contains("2330", case=False, na=False)]
        for t in df_keyword["title"]:
            self.assertIn("2330", t)

    def test_render_raw_article_table_empty_state_and_with_data(self):
        """測試輿情文章明細表在空資料與有資料時均零崩潰正常渲染"""
        # 1. 空資料測試 (驗證 Empty State 正常渲染不拋錯)
        render_raw_article_table(pd.DataFrame())
        render_raw_article_table(None)

        # 2. 有資料測試
        df_articles = generate_mock_ptt_articles("2330", limit=5)
        render_raw_article_table(df_articles)

    def test_render_thematic_radar_component_structure(self):
        """HERM-09 修復：demo=True 取得確定性展示題材，測試目的是元件渲染，不是 DB 層。"""
        radar_data, mode = load_thematic_radar_data(demo=True)
        res = render_thematic_radar(radar_data, mode=mode)
        # 離線環境無按鈕點擊應安全回傳 None
        self.assertIsNone(res)

        # 空資料安全不崩潰
        self.assertIsNone(render_thematic_radar([], mode=DataMode.EMPTY))

    def test_render_thematic_radar_error_mode_shows_banner_not_crash(self):
        """mode=ERROR 時安全渲染錯誤橫幅並回傳 None，不嘗試渲染空清單。"""
        self.assertIsNone(render_thematic_radar([], mode=DataMode.ERROR))

    def test_render_tournament_leaderboard_empty_mode_no_crash(self):
        """無 artifact（EMPTY）時安全顯示佔位說明，不嘗試對 None 資料建表。"""
        self.assertIsNone(render_tournament_leaderboard(None, mode=DataMode.EMPTY))

    def test_render_tournament_leaderboard_error_mode_no_crash(self):
        """artifact 格式錯誤（ERROR）時安全顯示錯誤橫幅，不嘗試對 None 資料建表。"""
        self.assertIsNone(render_tournament_leaderboard(None, mode=DataMode.ERROR))

    def test_render_tournament_leaderboard_real_mode_structure(self):
        """REAL 模式下對合法 payload 正常渲染，不拋出例外。"""
        payload = {
            "leaderboard": [
                {"experiment_id": "EXP-RF-MM", "model_name": "random_forest", "feature_set": "MultiModal (18 Feat)",
                 "macro_f1": 0.58, "accuracy": 0.6, "roc_auc": 0.61, "directional_hit_ratio": 0.58,
                 "cumulative_return": 0.08, "sharpe_ratio": 1.1, "max_drawdown": 0.05},
                {"experiment_id": "EXP-RF-TECH", "model_name": "random_forest", "feature_set": "PureTechnical (9 Feat)",
                 "macro_f1": 0.53, "accuracy": 0.55, "roc_auc": 0.54, "directional_hit_ratio": 0.53,
                 "cumulative_return": 0.03, "sharpe_ratio": 0.6, "max_drawdown": 0.07},
            ],
            "alpha_attribution": {"random_forest": {"delta_macro_f1": 0.05, "delta_cumulative_return": 0.05, "delta_hit_ratio": 0.05, "sentiment_effective": True}},
            "champion_model_name": "random_forest",
            "champion_score": 0.58,
        }
        self.assertIsNone(render_tournament_leaderboard(payload, mode=DataMode.REAL))

    def test_render_tournament_leaderboard_real_mode_with_empty_leaderboard_falls_back_to_error(self):
        """mode=REAL 但 leaderboard 為空清單時，視為契約不符，安全退回錯誤橫幅而非渲染空表。"""
        self.assertIsNone(render_tournament_leaderboard({"leaderboard": []}, mode=DataMode.REAL))


if __name__ == "__main__":
    unittest.main()
