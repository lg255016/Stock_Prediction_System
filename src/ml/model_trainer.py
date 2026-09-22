import logging
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .baseline_models import (
    TECHNICAL_FEATURE_COLS,
    SENTIMENT_FEATURE_COLS,
    NAN_INTOLERANT_MODELS,
    PureTechnicalModelFactory,
)

logger = logging.getLogger(__name__)

# 完整 18 欄位多模態特徵白名單 (價量 + 技術 + 風險 + 機構情緒 + 滯後)
ALL_MULTIMODAL_FEATURE_COLS: List[str] = [
    # 基礎價量 (5)
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    # 技術動能 (2)
    "return_1d",
    "rsi_14",
    # 風險波動 (2)
    "volatility_5d",
    "volatility_20d",
    # 社群輿情與機構指標 (4)
    "article_count",
    "sentiment_mean",
    "bullishness_index",
    "agreement_index",
    # 時序均線與滯後 (4)
    "sentiment_3d_ma",
    "sentiment_5d_ma",
    "sentiment_lag_1",
    "sentiment_lag_2",
]


class _FallbackStandardScaler:
    """輕量純 NumPy 標準化轉換器 (供無 sklearn 環境安全執行)"""
    def __init__(self):
        self.mean_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None

    def fit(self, X: Any) -> "_FallbackStandardScaler":
        X_arr = np.asarray(X, dtype=float)
        self.mean_ = np.nanmean(X_arr, axis=0)
        scale = np.nanstd(X_arr, axis=0)
        # 防止除以零
        self.scale_ = np.where(scale == 0, 1.0, scale)
        return self

    def transform(self, X: Any) -> np.ndarray:
        X_arr = np.asarray(X, dtype=float)
        if self.mean_ is None or self.scale_ is None:
            raise RuntimeError("Scaler 尚未 Fit，無法執行 Transform！")
        return (X_arr - self.mean_) / self.scale_

    def fit_transform(self, X: Any) -> np.ndarray:
        return self.fit(X).transform(X)


class _FallbackRobustScaler:
    """輕量純 NumPy 中位數與 IQR 強健轉換器 (抗金融極端值)"""
    def __init__(self):
        self.center_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None

    def fit(self, X: Any) -> "_FallbackRobustScaler":
        X_arr = np.asarray(X, dtype=float)
        self.center_ = np.nanmedian(X_arr, axis=0)
        q75 = np.nanpercentile(X_arr, 75, axis=0)
        q25 = np.nanpercentile(X_arr, 25, axis=0)
        iqr = q75 - q25
        self.scale_ = np.where(iqr == 0, 1.0, iqr)
        return self

    def transform(self, X: Any) -> np.ndarray:
        X_arr = np.asarray(X, dtype=float)
        if self.center_ is None or self.scale_ is None:
            raise RuntimeError("Scaler 尚未 Fit，無法執行 Transform！")
        return (X_arr - self.center_) / self.scale_

    def fit_transform(self, X: Any) -> np.ndarray:
        return self.fit(X).transform(X)


def create_scaler(scaler_type: Optional[str] = "robust") -> Any:
    """建立標準化前處理轉換器"""
    if scaler_type is None:
        return None
    st = scaler_type.lower().strip()
    if st == "robust":
        try:
            from sklearn.preprocessing import RobustScaler
            return RobustScaler()
        except ImportError:
            return _FallbackRobustScaler()
    elif st == "standard":
        try:
            from sklearn.preprocessing import StandardScaler
            return StandardScaler()
        except ImportError:
            return _FallbackStandardScaler()
    else:
        raise ValueError(f"不支援的 Scaler 類型: '{scaler_type}'，支援 'robust', 'standard', None")


class MultiModalTrainer:
    """
    多模態特徵融合與多模型訓練器 (Multi-Modal Sentiment Fusion & Tournament Trainer)。

    核心功能：
    1. 特徵全集成：整合 18 欄位多模態特徵矩陣（價量 + RSI + 波動率 + Antweiler 看多/一致性指數 + 滯後）。
    2. 多模型支援：支援 Logistic Regression、Random Forest、LightGBM、XGBoost 四大演算法橫向對比。
    3. 嚴格防前視洩漏（Zero Leakage Protocol）：Scaler 與模型嚴格只在各 Fold 的 Train Set 內部擬合（Fit），
       絕不跨入 Test Set。
    4. 特徵重要性分析（Feature Importance Matrix）：自動提取各模型之特徵貢獻權重，量化情緒指標價值。
    5. 模型輕量化序列化：支援完整訓練狀態與 Scaler 的保存與載入。
    """

    def __init__(
        self,
        model_name: str = "random_forest",
        scaler_type: Optional[str] = "robust",
        random_state: int = 42,
        **model_kwargs: Any
    ):
        self.model_name = model_name.lower().strip()
        self.scaler_type = scaler_type
        self.random_state = random_state
        self.model_kwargs = model_kwargs

        self.model = PureTechnicalModelFactory.create_model(
            self.model_name, random_state=self.random_state, **self.model_kwargs
        )
        self.scaler = create_scaler(self.scaler_type)
        self.feature_names_: List[str] = []
        self.feature_importances_: Dict[str, float] = {}
        self.is_fitted_: bool = False

    @staticmethod
    def extract_multimodal_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        從輸入 DataFrame 中嚴格提取多模態特徵矩陣，補齊缺失值並維持欄位順序。

        **`UG-G3-SB3` 修復（PO 2026-09-12）**：`SENTIMENT_FEATURE_COLS` 8 欄
        一律保留 `NaN`，不填補——原本 `sentiment_mean`／`sentiment_lag_1`／
        `sentiment_lag_2` 補 `0.5`，其餘 5 欄落入 `else` 分支補 `0.0`
        （`sentiment_3d_ma`／`sentiment_5d_ma` 補 `0.0` 尤其嚴重：情緒尺度
        0～1，`0.0` 是「極度看空」的具體語意值，不是中立點）。這會把
        D5（`PRE-G3-04`）建立的成因 U（`NULL`）語意靜默抹平成假中立值，
        廢掉 D3 對照臂 B 讓 NaN-native 模型（RF／LightGBM／XGBoost）看見
        真實缺失的整個設計前提。`rsi_14` 的 `fillna(50.0)` 不動（聚合層
        已保證非 NULL，屬安全防禦）。
        """
        if df is None or df.empty:
            return pd.DataFrame()

        available_cols = [c for c in ALL_MULTIMODAL_FEATURE_COLS if c in df.columns]
        if not available_cols:
            raise ValueError(f"輸入資料不包含任何有效的特徵欄位！要求欄位: {ALL_MULTIMODAL_FEATURE_COLS}")

        # 複製並執行安全補值
        df_feat = df[available_cols].copy()
        for col in df_feat.columns:
            if col in SENTIMENT_FEATURE_COLS:
                continue  # 保留 NaN（成因 U），不得填補
            elif col == "rsi_14":
                df_feat[col] = df_feat[col].fillna(50.0)
            else:
                df_feat[col] = df_feat[col].fillna(0.0)

        return df_feat

    def train_and_predict_fold(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        target_col: str = "target_up_down"
    ) -> Dict[str, Any]:
        """
        在單一 Fold 上執行嚴格防洩漏之「Scaler 擬合 ➔ 特徵縮放 ➔ 模型訓練 ➔ 測試集預測」。
        """
        if target_col not in train_df.columns:
            raise KeyError(f"訓練集缺少目標欄位: '{target_col}'")

        train_valid = train_df.dropna(subset=[target_col])
        test_valid = test_df.dropna(subset=[target_col])

        if train_valid.empty or test_valid.empty:
            return {
                "model_name": self.model_name,
                "feature_set": "multimodal",
                "y_true": np.empty(0, dtype=int),
                "y_pred": np.empty(0, dtype=int),
                "y_proba": np.empty(0, dtype=float),
                "n_train": len(train_valid),
                "n_test": len(test_valid),
                "feature_names": [],
                "feature_importances": {},
            }

        X_train = self.extract_multimodal_features(train_valid)
        y_train = train_valid[target_col].astype(int).to_numpy()

        X_test = self.extract_multimodal_features(test_valid)
        y_test = test_valid[target_col].astype(int).to_numpy()

        self.feature_names_ = list(X_train.columns)

        # ----------------------------------------------------
        # Fail-fast：不支援 NaN 的模型（UG-G3-SB3，PO 2026-09-12 裁決）
        # ----------------------------------------------------
        # Gate 3 §5 的 D3 對照實驗設計本來就規定 LogisticRegression 只配
        # 對照臂 A（無情緒）特徵，不得為它插補情緒欄的 NaN 讓它「也能」跑
        # 對照臂 B——那會混淆「模型能力差異」與「特徵有無差異」兩個變因。
        # 這裡不是新規則，是把既有裁決做成一個明確、有說明的錯誤，而不是
        # 讓呼叫端在真實面板（sentiment_mean 99.8% NULL）上撞見 sklearn
        # 自己那句不含脈絡的「Input X contains NaN.」。
        if self.model_name in NAN_INTOLERANT_MODELS:
            nan_cols = sorted({
                c for c in X_train.columns
                if X_train[c].isna().any() or X_test[c].isna().any()
            })
            if nan_cols:
                raise ValueError(
                    f"模型 '{self.model_name}' 不支援 NaN 特徵輸入，"
                    f"但以下欄位含 NaN：{nan_cols}。依 Gate 3 §5（D3 對照"
                    "實驗設計）與 UG-G3-SB3 裁決（PO 2026-09-12），"
                    f"'{self.model_name}' 只應配對照臂 A（無情緒）特徵，"
                    "不得為它插補情緒欄的 NaN 讓它「也能」跑對照臂 B。"
                )

        # ----------------------------------------------------
        # 嚴格防前視洩漏：Scaler 僅在 X_train 上 Fit，再 Transform X_train 與 X_test
        # ----------------------------------------------------
        if self.scaler is not None:
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
        else:
            X_train_scaled = X_train.to_numpy(dtype=float)
            X_test_scaled = X_test.to_numpy(dtype=float)

        # 模型擬合
        self.model.fit(X_train_scaled, y_train)
        self.is_fitted_ = True

        # 測試集預測
        y_pred = self.model.predict(X_test_scaled)

        # 信心機率計算
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(X_test_scaled)
            y_proba = probs[:, 1] if probs.shape[1] > 1 else probs[:, 0]
        else:
            y_proba = y_pred.astype(float)

        # 提取特徵重要性
        self.feature_importances_ = self._extract_feature_importances(self.feature_names_)

        return {
            "model_name": self.model_name,
            "feature_set": "multimodal",
            "y_true": y_test,
            "y_pred": np.asarray(y_pred, dtype=int),
            "y_proba": np.asarray(y_proba, dtype=float),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "feature_names": self.feature_names_,
            "feature_importances": self.feature_importances_,
            "scaler_type": self.scaler_type,
        }

    def _extract_feature_importances(self, feature_names: List[str]) -> Dict[str, float]:
        """從擬合後模型提取特徵重要性或係數絕對值"""
        importances: Dict[str, float] = {}
        if not self.is_fitted_:
            return {f: 0.0 for f in feature_names}

        # 1. 樹模型 feature_importances_ (Random Forest, LightGBM, XGBoost)
        if hasattr(self.model, "feature_importances_"):
            raw_imp = getattr(self.model, "feature_importances_")
            total = float(np.sum(raw_imp)) if np.sum(raw_imp) > 0 else 1.0
            for f, val in zip(feature_names, raw_imp):
                importances[f] = round(float(val) / total, 6)

        # 2. 線性模型 coef_ (Logistic Regression)
        elif hasattr(self.model, "coef_"):
            raw_coef = getattr(self.model, "coef_").flatten()
            abs_coef = np.abs(raw_coef)
            total = float(np.sum(abs_coef)) if np.sum(abs_coef) > 0 else 1.0
            for f, val in zip(feature_names, abs_coef):
                importances[f] = round(float(val) / total, 6)

        # 3. Fallback 線性模型 weights_
        elif hasattr(self.model, "weights_"):
            raw_w = getattr(self.model, "weights_")
            abs_w = np.abs(raw_w)
            total = float(np.sum(abs_w)) if np.sum(abs_w) > 0 else 1.0
            for f, val in zip(feature_names, abs_w):
                importances[f] = round(float(val) / total, 6)
        else:
            for f in feature_names:
                importances[f] = round(1.0 / len(feature_names), 6)

        return importances

    def save_artifact(self, filepath: str) -> None:
        """將訓練完成之模型、Scaler 與元資料序列化保存"""
        if not self.is_fitted_:
            logger.warning("[MultiModalTrainer] 模型尚未擬合，保存未訓練狀態。")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        payload = {
            "model_name": self.model_name,
            "scaler_type": self.scaler_type,
            "feature_names": self.feature_names_,
            "feature_importances": self.feature_importances_,
            "model": self.model,
            "scaler": self.scaler,
            "is_fitted": self.is_fitted_,
        }
        with open(filepath, "wb") as f:
            pickle.dump(payload, f)
        logger.info(f"✅ 模型與特徵轉換器已成功保存至: {filepath}")

    @classmethod
    def load_artifact(cls, filepath: str) -> "MultiModalTrainer":
        """從序列化檔案載入訓練後之模型與 Scaler"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"找不到指定的模型檔案: {filepath}")
        with open(filepath, "rb") as f:
            payload = pickle.load(f)

        trainer = cls(
            model_name=payload.get("model_name", "random_forest"),
            scaler_type=payload.get("scaler_type", "robust"),
        )
        trainer.feature_names_ = payload.get("feature_names", [])
        trainer.feature_importances_ = payload.get("feature_importances", {})
        trainer.model = payload.get("model")
        trainer.scaler = payload.get("scaler")
        trainer.is_fitted_ = payload.get("is_fitted", False)
        return trainer
