import unittest
import numpy as np
import pandas as pd

from src.ml.evaluator import (
    MLEvaluator,
    compute_classification_metrics,
    compute_financial_strategy_metrics,
)
from src.ml.model_trainer import MultiModalTrainer, ALL_MULTIMODAL_FEATURE_COLS
from src.ml.predictor import StockTrendPredictor
from src.ml.time_series_split import WalkForwardSplitter


class ClassificationMetricsUnitTests(unittest.TestCase):
    """測試分類統計指標純向量化計算"""

    def test_perfect_predictions_yield_perfect_metrics(self):
        y_true = [1, 0, 1, 0]
        y_pred = [1, 0, 1, 0]
        y_proba = [0.95, 0.05, 0.90, 0.10]

        res = compute_classification_metrics(y_true, y_pred, y_proba)
        self.assertEqual(res["accuracy"], 1.0)
        self.assertEqual(res["precision"], 1.0)
        self.assertEqual(res["recall"], 1.0)
        self.assertEqual(res["f1"], 1.0)
        self.assertEqual(res["macro_f1"], 1.0)
        self.assertEqual(res["roc_auc"], 1.0)
        self.assertLess(res["brier_score"], 0.02)

    def test_empty_and_imbalanced_inputs_safety(self):
        # 空資料輸入
        res_empty = compute_classification_metrics([], [])
        self.assertEqual(res_empty["accuracy"], 0.0)
        self.assertEqual(res_empty["roc_auc"], 0.5)

        # 單一類別全錯情況
        y_true = [1, 1, 1, 1]
        y_pred = [0, 0, 0, 0]
        res_fail = compute_classification_metrics(y_true, y_pred)
        self.assertEqual(res_fail["accuracy"], 0.0)
        self.assertEqual(res_fail["f1"], 0.0)


class FinancialStrategyMetricsUnitTests(unittest.TestCase):
    """測試金融量化模擬策略指標"""

    def test_directional_hit_ratio_and_cumulative_return(self):
        # 預測全中 (報酬均為正且預測 1)
        y_pred = [1, 1, 1]
        actual_returns = [0.02, 0.03, 0.01]

        res = compute_financial_strategy_metrics(y_pred, actual_returns)
        self.assertEqual(res["directional_hit_ratio"], 1.0)
        self.assertGreater(res["cumulative_strategy_return"], 0.05)
        self.assertEqual(res["max_drawdown"], 0.0)

    def test_max_drawdown_calculation(self):
        # 模擬經歷一次 10% 回撤
        y_pred = [1, 1, 1]
        actual_returns = [0.10, -0.15, 0.05]

        res = compute_financial_strategy_metrics(y_pred, actual_returns)
        self.assertGreater(res["max_drawdown"], 0.10)


class MultiModelTournamentEvaluatorTests(unittest.TestCase):
    """測試 8 組平行對照實驗排行榜與 Alpha 歸因"""

    def test_tournament_evaluates_8_experiments_and_produces_leaderboard(self):
        np.random.seed(42)
        dates = pd.date_range("2026-01-01", periods=60, freq="D").strftime("%Y-%m-%d")
        records = []
        for d in dates:
            for s in ["2330", "NVDA"]:
                row = {col: np.random.randn() for col in ALL_MULTIMODAL_FEATURE_COLS}
                row["trade_date"] = d
                row["stock_id"] = s
                row["target_up_down"] = np.random.choice([0, 1])
                row["target_return_1d"] = np.random.randn() * 0.02
                records.append(row)

        df = pd.DataFrame(records)
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, step_size=10)
        evaluator = MLEvaluator(random_state=42)

        tournament_res = evaluator.evaluate_tournament(df, splitter)

        # 1. 驗證排行榜包含 8 組實驗 (4 種演算法 x 2 組特徵集)
        df_lb = tournament_res["leaderboard"]
        self.assertEqual(len(df_lb), 8)
        self.assertIn("experiment_id", df_lb.columns)
        self.assertIn("macro_f1", df_lb.columns)
        self.assertIn("cumulative_return", df_lb.columns)

        # 2. 驗證 Alpha 歸因字典
        alpha_att = tournament_res["alpha_attribution"]
        self.assertEqual(len(alpha_att), 4)
        for m in ("logistic_regression", "random_forest", "lightgbm", "xgboost"):
            self.assertIn(m, alpha_att)
            self.assertIn("delta_macro_f1", alpha_att[m])
            self.assertIn("delta_cumulative_return", alpha_att[m])

        # 3. 驗證冠軍模型評選
        champion = tournament_res["champion_model_name"]
        self.assertIn(champion, evaluator.SUPPORTED_MODELS)
        self.assertGreater(tournament_res["champion_score"], 0.0)


class StockTrendPredictorRealtimeInferenceTests(unittest.TestCase):
    """測試單日即時推論引擎與 Top 3 驅動因子契約"""

    def test_realtime_predictor_latest_output_contract(self):
        # 訓練一組模型
        np.random.seed(42)
        df_train = pd.DataFrame({col: np.random.randn(50) for col in ALL_MULTIMODAL_FEATURE_COLS})
        df_train["target_up_down"] = np.random.choice([0, 1], size=50)

        trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust", random_state=42)
        trainer.train_and_predict_fold(df_train, df_train)

        # 建立推論引擎
        predictor = StockTrendPredictor(trainer=trainer)

        # 模擬當日盤後產生的最新 1 筆特徵列
        df_latest = pd.DataFrame({
            "trade_date": ["2026-08-20"],
            "stock_id": ["2330"],
            "open_price": [100.0],
            "high_price": [105.0],
            "low_price": [99.0],
            "close_price": [104.0],
            "volume": [5000],
            "return_1d": [0.03],
            "rsi_14": [65.0],
            "volatility_5d": [0.18],
            "volatility_20d": [0.22],
            "article_count": [12],
            "sentiment_mean": [0.75],
            "bullishness_index": [1.45],
            "agreement_index": [0.88],
            "sentiment_3d_ma": [0.70],
            "sentiment_5d_ma": [0.68],
            "sentiment_lag_1": [0.72],
            "sentiment_lag_2": [0.65],
        })

        pred_res = predictor.predict_latest(df_latest)

        # 驗證契約欄位
        self.assertEqual(pred_res["stock_id"], "2330")
        self.assertEqual(pred_res["trade_date"], "2026-08-20")
        self.assertIn(pred_res["predicted_direction"], ("UP", "DOWN"))
        self.assertIn(pred_res["predicted_label"], (0, 1))
        self.assertTrue(0.0 <= pred_res["confidence_score"] <= 1.0)
        self.assertEqual(pred_res["model_name"], "random_forest")

        # 驗證 Top 3 驅動因子結構
        top_drivers = pred_res["top_drivers"]
        self.assertLessEqual(len(top_drivers), 3)
        self.assertGreaterEqual(len(top_drivers), 1)
        for d in top_drivers:
            self.assertIn("feature_name", d)
            self.assertIn("feature_value", d)
            self.assertIn("importance_weight", d)

    def test_empty_input_raises_value_error(self):
        predictor = StockTrendPredictor()
        with self.assertRaises(ValueError):
            predictor.predict_latest(pd.DataFrame())


if __name__ == "__main__":
    unittest.main()
