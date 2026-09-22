import unittest
import numpy as np
import pandas as pd

from src.ml.baseline_models import (
    DummyBaselineClassifier,
    PureTechnicalModelFactory,
    TechnicalBaselineSuite,
    TECHNICAL_FEATURE_COLS,
    SENTIMENT_FEATURE_COLS,
)
from src.ml.time_series_split import WalkForwardSplitter


class DummyBaselineClassifierTests(unittest.TestCase):
    """測試 Dummy / Buy & Hold 基準分類器"""

    def test_buy_and_hold_strategy_always_predicts_one(self):
        dummy = DummyBaselineClassifier(strategy="buy_and_hold")
        X_train = np.array([[100, 10], [105, 12], [95, 8]])
        y_train = np.array([0, 0, 1])

        dummy.fit(X_train, y_train)

        X_test = np.array([[110, 15], [90, 5]])
        preds = dummy.predict(X_test)
        probs = dummy.predict_proba(X_test)

        self.assertEqual(len(preds), 2)
        self.assertListEqual(preds.tolist(), [1, 1])
        self.assertTrue((probs[:, 1] == 1.0).all())

    def test_majority_strategy_respects_class_distribution(self):
        # 測試負類別 (0) 佔多數
        dummy = DummyBaselineClassifier(strategy="majority")
        X = np.random.randn(10, 2)
        y = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1, 1])  # 7 個 0, 3 個 1
        dummy.fit(X, y)

        preds = dummy.predict(np.random.randn(4, 2))
        self.assertListEqual(preds.tolist(), [0, 0, 0, 0])

        probs = dummy.predict_proba(np.random.randn(4, 2))
        self.assertAlmostEqual(probs[0, 0], 0.7)
        self.assertAlmostEqual(probs[0, 1], 0.3)


class PureTechnicalFeatureIsolationTests(unittest.TestCase):
    """測試純價量控制組特徵提取之絕對隔離性（0 輿情污染）"""

    def test_extract_pure_technical_features_strictly_excludes_sentiment_features(self):
        # 建立包含全部 18 欄位之混合 DataFrame
        df_full = pd.DataFrame({
            "trade_date": ["2026-08-01", "2026-08-02"],
            "stock_id": ["2330", "2330"],
            # 9 欄位純價量特徵
            "open_price": [100.0, 102.0],
            "high_price": [103.0, 104.0],
            "low_price": [99.0, 101.0],
            "close_price": [102.0, 103.0],
            "volume": [1000, 1200],
            "return_1d": [0.02, 0.01],
            "rsi_14": [55.0, 60.0],
            "volatility_5d": [0.15, 0.16],
            "volatility_20d": [0.20, 0.21],
            # 8 欄位社群情緒特徵 (黑名單)
            "article_count": [5, 10],
            "sentiment_mean": [0.65, 0.70],
            "bullishness_index": [0.80, 1.10],
            "agreement_index": [0.90, 0.95],
            "sentiment_3d_ma": [0.60, 0.65],
            "sentiment_5d_ma": [0.58, 0.62],
            "sentiment_lag_1": [0.55, 0.65],
            "sentiment_lag_2": [0.50, 0.55],
        })

        df_tech = TechnicalBaselineSuite.extract_pure_technical_features(df_full)

        # 1. 驗證欄位數量嚴格等於 9
        self.assertEqual(len(df_tech.columns), 9)

        # 2. 驗證所有技術欄位皆存在
        for col in TECHNICAL_FEATURE_COLS:
            self.assertIn(col, df_tech.columns)

        # 3. 嚴格斷言：絕無任何社群情緒欄位滲透
        for col in SENTIMENT_FEATURE_COLS:
            self.assertNotIn(col, df_tech.columns)


class MultiModelFactoryAndTechnicalSuiteTests(unittest.TestCase):
    """測試四大模型工廠與純價量訓練套件"""

    def test_four_models_fit_and_predict_on_technical_features(self):
        # 建立模擬技術資料集
        np.random.seed(42)
        n_samples = 60
        df_train = pd.DataFrame({col: np.random.randn(n_samples) for col in TECHNICAL_FEATURE_COLS})
        df_train["target_up_down"] = np.random.choice([0, 1], size=n_samples)

        df_test = pd.DataFrame({col: np.random.randn(20) for col in TECHNICAL_FEATURE_COLS})
        df_test["target_up_down"] = np.random.choice([0, 1], size=20)

        models = ["logistic_regression", "random_forest", "lightgbm", "xgboost"]

        for model_name in models:
            suite = TechnicalBaselineSuite(model_name=model_name, random_state=42)
            res = suite.train_and_predict_fold(df_train, df_test)

            self.assertEqual(res["model_name"], model_name)
            self.assertEqual(len(res["y_pred"]), 20)
            self.assertEqual(len(res["y_proba"]), 20)
            self.assertEqual(res["n_train"], 60)
            self.assertEqual(res["n_test"], 20)

            # 驗證輸出值域
            self.assertTrue(set(res["y_pred"]).issubset({0, 1}))
            self.assertTrue((res["y_proba"] >= 0.0).all() and (res["y_proba"] <= 1.0).all())

            # 驗證使用的特徵清單嚴格等於 9 欄位技術指標
            self.assertListEqual(res["feature_names"], TECHNICAL_FEATURE_COLS)

    def test_invalid_model_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            PureTechnicalModelFactory.create_model("deep_learning_transformer")


class TechnicalBaselineWalkForwardIntegrationTests(unittest.TestCase):
    """測試純價量控制組與 WalkForwardSplitter 整合前向滾動訓練"""

    def test_technical_suite_walk_forward_execution(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D").strftime("%Y-%m-%d")
        records = []
        for d in dates:
            for s in ["2330", "NVDA"]:
                row = {col: 100.0 + np.random.randn() for col in TECHNICAL_FEATURE_COLS}
                row["trade_date"] = d
                row["stock_id"] = s
                row["target_up_down"] = np.random.choice([0, 1])
                # 加入情緒干擾欄位 (測試其是否被自動隔離)
                for sent_col in SENTIMENT_FEATURE_COLS:
                    row[sent_col] = 0.8
                records.append(row)

        df = pd.DataFrame(records)
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, step_size=10)
        suite = TechnicalBaselineSuite(model_name="random_forest", random_state=42)

        fold_count = 0
        for train_idx, test_idx, meta in splitter.split(df):
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]

            res = suite.train_and_predict_fold(train_df, test_df)
            self.assertEqual(res["n_test"], 20)  # 10 天 * 2 檔股票 = 20
            # 再次確保特徵名單無情緒欄位
            self.assertEqual(len(res["feature_names"]), 9)
            for sc in SENTIMENT_FEATURE_COLS:
                self.assertNotIn(sc, res["feature_names"])
            fold_count += 1

        self.assertEqual(fold_count, 3)


if __name__ == "__main__":
    unittest.main()
