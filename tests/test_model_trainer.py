import os
import shutil
import tempfile
import unittest
import numpy as np
import pandas as pd

from src.ml.model_trainer import (
    MultiModalTrainer,
    ALL_MULTIMODAL_FEATURE_COLS,
    create_scaler,
    _FallbackStandardScaler,
    _FallbackRobustScaler,
)
from src.ml.time_series_split import WalkForwardSplitter


class MultiModalFeatureExtractionTests(unittest.TestCase):
    """測試 18 欄位多模態特徵提取與預設補值"""

    def test_extract_multimodal_features_includes_all_columns(self):
        df_raw = pd.DataFrame({
            "trade_date": ["2026-08-01", "2026-08-02"],
            "stock_id": ["2330", "2330"],
            "open_price": [100.0, np.nan],
            "high_price": [105.0, 106.0],
            "low_price": [98.0, 100.0],
            "close_price": [102.0, 104.0],
            "volume": [1000, 1200],
            "return_1d": [0.02, np.nan],
            "rsi_14": [np.nan, 60.0],
            "volatility_5d": [0.15, np.nan],
            "volatility_20d": [0.20, 0.22],
            "article_count": [5, np.nan],
            "sentiment_mean": [np.nan, 0.70],
            "bullishness_index": [0.80, np.nan],
            "agreement_index": [np.nan, 0.90],
            "sentiment_3d_ma": [0.60, 0.65],
            "sentiment_5d_ma": [0.58, 0.62],
            "sentiment_lag_1": [np.nan, 0.65],
            "sentiment_lag_2": [0.50, np.nan],
        })

        df_extracted = MultiModalTrainer.extract_multimodal_features(df_raw)

        # 1. 驗證欄位順序與數量嚴格符合 18 欄位白名單
        self.assertListEqual(list(df_extracted.columns), ALL_MULTIMODAL_FEATURE_COLS)

        # 2. 驗證補值策略（UG-G3-SB3 訂正，PO 2026-09-12：SENTIMENT_FEATURE_COLS
        # 8 欄一律保留 NaN，不填補——原本 sentiment_mean/sentiment_lag_* 補
        # 0.5、article_count/bullishness_index/agreement_index/
        # sentiment_3d_ma/sentiment_5d_ma 落 else 分支補 0.0 皆已移除。
        # rsi_14 仍補 50.0，非情緒欄仍補 0.0。）
        self.assertTrue(pd.isna(df_extracted["sentiment_mean"].iloc[0]))
        self.assertTrue(pd.isna(df_extracted["sentiment_lag_1"].iloc[0]))
        self.assertTrue(pd.isna(df_extracted["sentiment_lag_2"].iloc[1]))
        self.assertTrue(pd.isna(df_extracted["bullishness_index"].iloc[1]))
        self.assertTrue(pd.isna(df_extracted["agreement_index"].iloc[0]))
        self.assertEqual(df_extracted["rsi_14"].iloc[0], 50.0)
        self.assertEqual(df_extracted["open_price"].iloc[1], 0.0)


class ScalerZeroLookAheadLeakageTests(unittest.TestCase):
    """測試 Scaler 嚴格在 Train Set 內部擬合之零前視洩漏防護"""

    def test_scaler_fitted_strictly_on_train_set(self):
        # 建立訓練集 (均值 = 100, 標準差 = 10)
        train_data = np.array([[90.0], [100.0], [110.0]])
        # 建立測試集 (包含未來極端異常值 1000.0)
        test_data = np.array([[1000.0]])

        scaler = _FallbackStandardScaler()
        scaler.fit(train_data)

        # 驗證 Scaler 記錄的均值嚴格等於 Train 的 100.0
        self.assertAlmostEqual(scaler.mean_[0], 100.0)

        # 驗證 Transform 測試集時，使用的是 Train 的 100.0 均值
        test_scaled = scaler.transform(test_data)
        # (1000 - 100) / 8.1649... > 100.0
        self.assertGreater(test_scaled[0, 0], 100.0)


class MultiModalFourModelsTrainingTests(unittest.TestCase):
    """測試四大模型在多模態特徵上的擬合、預測與特徵重要性分析"""

    def test_four_models_train_and_predict_on_multimodal_dataset(self):
        np.random.seed(42)
        n_train = 60
        n_test = 20

        # 建立 18 欄位模擬資料
        df_train = pd.DataFrame({col: np.random.randn(n_train) for col in ALL_MULTIMODAL_FEATURE_COLS})
        df_train["target_up_down"] = np.random.choice([0, 1], size=n_train)

        df_test = pd.DataFrame({col: np.random.randn(n_test) for col in ALL_MULTIMODAL_FEATURE_COLS})
        df_test["target_up_down"] = np.random.choice([0, 1], size=n_test)

        models = ["logistic_regression", "random_forest", "lightgbm", "xgboost"]

        for model_name in models:
            trainer = MultiModalTrainer(model_name=model_name, scaler_type="robust", random_state=42)
            res = trainer.train_and_predict_fold(df_train, df_test)

            self.assertEqual(res["model_name"], model_name)
            self.assertEqual(res["feature_set"], "multimodal")
            self.assertEqual(len(res["y_pred"]), n_test)
            self.assertEqual(len(res["y_proba"]), n_test)

            # 驗證預測值合法性
            self.assertTrue(set(res["y_pred"]).issubset({0, 1}))
            self.assertTrue((res["y_proba"] >= 0.0).all() and (res["y_proba"] <= 1.0).all())

            # 驗證特徵重要性輸出
            importances = res["feature_importances"]
            self.assertEqual(len(importances), len(ALL_MULTIMODAL_FEATURE_COLS))
            self.assertIn("bullishness_index", importances)
            self.assertIn("agreement_index", importances)
            self.assertIn("rsi_14", importances)

            # 驗證重要性權重總和為 1.0 (或接近 1.0)
            total_imp = sum(importances.values())
            self.assertAlmostEqual(total_imp, 1.0, places=2)


class ModelArtifactSerializationTests(unittest.TestCase):
    """測試模型、Scaler 與元資料之保存與載入"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.model_path = os.path.join(self.temp_dir, "test_champion_model.pkl")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_artifact_preserves_weights_and_predictions(self):
        np.random.seed(42)
        df_train = pd.DataFrame({col: np.random.randn(40) for col in ALL_MULTIMODAL_FEATURE_COLS})
        df_train["target_up_down"] = np.random.choice([0, 1], size=40)

        df_test = pd.DataFrame({col: np.random.randn(10) for col in ALL_MULTIMODAL_FEATURE_COLS})
        df_test["target_up_down"] = np.random.choice([0, 1], size=10)

        trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust", random_state=42)
        res_orig = trainer.train_and_predict_fold(df_train, df_test)

        # 保存
        trainer.save_artifact(self.model_path)
        self.assertTrue(os.path.exists(self.model_path))

        # 載入
        loaded_trainer = MultiModalTrainer.load_artifact(self.model_path)
        self.assertTrue(loaded_trainer.is_fitted_)
        self.assertEqual(loaded_trainer.model_name, "random_forest")
        self.assertEqual(len(loaded_trainer.feature_names_), len(ALL_MULTIMODAL_FEATURE_COLS))

        # 驗證載入後的模型預測結果與原模型 100% 相同
        X_test = loaded_trainer.extract_multimodal_features(df_test)
        X_test_scaled = loaded_trainer.scaler.transform(X_test)
        preds_loaded = loaded_trainer.model.predict(X_test_scaled)

        self.assertListEqual(res_orig["y_pred"].tolist(), preds_loaded.tolist())


class MultiModalWalkForwardIntegrationTests(unittest.TestCase):
    """測試多模態訓練器與 WalkForwardSplitter 整合前向滾動訓練"""

    def test_multimodal_trainer_walk_forward_pipeline(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D").strftime("%Y-%m-%d")
        records = []
        for d in dates:
            for s in ["2330", "NVDA"]:
                row = {col: np.random.randn() for col in ALL_MULTIMODAL_FEATURE_COLS}
                row["trade_date"] = d
                row["stock_id"] = s
                row["target_up_down"] = np.random.choice([0, 1])
                records.append(row)

        df = pd.DataFrame(records)
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, step_size=10)
        trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust", random_state=42)

        fold_count = 0
        for train_idx, test_idx, meta in splitter.split(df):
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]

            res = trainer.train_and_predict_fold(train_df, test_df)
            self.assertEqual(res["feature_set"], "multimodal")
            self.assertEqual(res["n_test"], 20)  # 10 天 * 2 檔股票
            self.assertEqual(len(res["feature_names"]), 17)  # 全部 17 項特徵
            self.assertIn("bullishness_index", res["feature_importances"])
            fold_count += 1

        self.assertEqual(fold_count, 3)


if __name__ == "__main__":
    unittest.main()
