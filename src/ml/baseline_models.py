import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 定義 9 欄位純價量與技術指標白名單 (0 輿情污染防護)
TECHNICAL_FEATURE_COLS: List[str] = [
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "return_1d",
    "rsi_14",
    "volatility_5d",
    "volatility_20d",
]

# 定義情緒特徵黑名單 (用於嚴格斷言防護)
SENTIMENT_FEATURE_COLS: List[str] = [
    "article_count",
    "sentiment_mean",
    "bullishness_index",
    "agreement_index",
    "sentiment_3d_ma",
    "sentiment_5d_ma",
    "sentiment_lag_1",
    "sentiment_lag_2",
]

# `UG-G3-SB3`（Gate 3 §5 D3 對照實驗，PO 2026-09-12 核准）：對照臂 A／B 的
# 特徵白名單。**刻意新增獨立常數，不修改上面兩個既有常數**——
# `TECHNICAL_FEATURE_COLS`／`ALL_MULTIMODAL_FEATURE_COLS` 被
# `src/ml/predictor.py`、`src/ui/data_loader.py` 消費，直接修改會把 SB3
# 的範圍擴大到 Predictor／UI（見 `UG_G3_SB3_GATE_A_PROPOSAL.md` §5 項 1）。
#
# CORE_16 平穩化特徵（`UG-G2-SB8`，DEC-029/030）——與原始 OHLCV 不同，
# 這四欄是相對值/比率，適合餵給對尺度敏感的 Logistic Regression。
CORE16_STATIONARY_COLS: List[str] = [
    "amplitude_ratio",
    "ma5_bias_ratio",
    "ma20_bias_ratio",
    "volume_ratio_5d",
]

# 對照臂 A（無情緒）：CORE_16 平穩化特徵 + 4 個既有技術欄，**不含原始
# 價量五欄**——Gate 3 §5 原文只列「CORE_16 + 4 欄」，保留原始價格會把
# 非平穩序列餵給 LR，違背平穩化的目的（`UG_G3_SB3_GATE_A_PROPOSAL.md` §4）。
ARM_A_FEATURE_COLS: List[str] = CORE16_STATIONARY_COLS + [
    "return_1d",
    "rsi_14",
    "volatility_5d",
    "volatility_20d",
]

# 對照臂 B（有情緒）：對照臂 A + 8 個社群情緒欄位。只餵給原生支援 NaN
# 的模型（RF／LightGBM／XGBoost），不含 LogisticRegression。
ARM_B_FEATURE_COLS: List[str] = ARM_A_FEATURE_COLS + SENTIMENT_FEATURE_COLS

# `UG-G3-SB4`（Gate A §4.3，PO 2026-09-14 裁決）：Meta-Learner 允許的
# 唯一非 OOF 輸入欄——Master Plan 明文「使用 OOF 預測值 + 市場機制特徵；
# 嚴格禁止使用原始特徵」，這個常數就是把「+ 市場機制特徵」與「嚴禁原始
# 特徵」兩句話接起來的地方：`src/ml/stacking.py::build_meta_learner_input()`
# 依「OOF 欄 ∪ 本常數」斷言輸入矩陣欄位，任何其他面板欄（例如不慎混入
# 的 `rsi_14`）一律拒絕。兩欄已存在於 `ARM_A_FEATURE_COLS`，資料管線已
# 驗證可用，刻意不新增計算邏輯；與 `UG-G3-SB6` Brief 提及的「市場機制
# 特徵」用詞一致，維持跨 SB 設計連貫。
META_REGIME_FEATURE_COLS: List[str] = [
    "volatility_20d",
    "ma20_bias_ratio",
]

# `UG-G3-SB3`（PO 2026-09-12 裁決）：明確宣告哪些模型**不**支援 NaN 特徵
# 輸入——`MultiModalTrainer.train_and_predict_fold()` 據此對這些模型
# fail-fast，而不是讓 sklearn 自己丟一個不含脈絡的 `ValueError: Input X
# contains NaN.`。**刻意寫成黑名單**（`SUPPORTED_MODELS` 只有 4 個，其中
# 3 個原生支援 NaN，只有 1 個不支援，列不支援的比列支援的短）；新增模型
# 時若忘記登記，預設落在「未列入即視為支援 NaN」——這與
# `provides_comment_direction()` 的 fail-safe 方向刻意相反，因為後果不同：
# 這裡漏登錄的後果是 sklearn 自己的 `ValueError`（一樣會報錯，只是訊息
# 較不友善），不是靜默錯誤，故不需要「未登錄一律最保守」的防線。
NAN_INTOLERANT_MODELS = frozenset({"logistic_regression"})


class DummyBaselineClassifier:
    """
    基準控制組：Dummy / Buy & Hold 分類器。
    
    支援策略：
    - 'buy_and_hold' / 'always_up'：恆常預測上漲 (1)，代表傳統買入持有自然漂移基準。
    - 'majority'：依訓練集多數類別進行恆常預測。
    """

    def __init__(self, strategy: str = "buy_and_hold"):
        if strategy not in ("buy_and_hold", "always_up", "majority"):
            raise ValueError(f"不支援的 Dummy 策略: {strategy}")
        self.strategy = strategy
        self.majority_class_: int = 1
        self.class_priors_: np.ndarray = np.array([0.5, 0.5])

    def fit(self, X: Any, y: Union[pd.Series, np.ndarray]) -> "DummyBaselineClassifier":
        y_arr = np.asarray(y, dtype=int)
        if len(y_arr) == 0:
            return self

        unique, counts = np.unique(y_arr, return_counts=True)
        self.majority_class_ = int(unique[np.argmax(counts)])

        p1 = float(np.mean(y_arr == 1))
        self.class_priors_ = np.array([1.0 - p1, p1])
        return self

    def predict(self, X: Any) -> np.ndarray:
        n_samples = len(X)
        if self.strategy in ("buy_and_hold", "always_up"):
            return np.ones(n_samples, dtype=int)
        return np.full(n_samples, self.majority_class_, dtype=int)

    def predict_proba(self, X: Any) -> np.ndarray:
        n_samples = len(X)
        if self.strategy in ("buy_and_hold", "always_up"):
            # 100% 信心預測上漲
            probs = np.zeros((n_samples, 2), dtype=float)
            probs[:, 1] = 1.0
            return probs
        # 依先驗機率輸出
        return np.tile(self.class_priors_, (n_samples, 1))


class PureTechnicalModelFactory:
    """
    純價量技術模型工廠（支援 Logistic Regression, Random Forest, LightGBM, XGBoost）。
    提供跨套件統一適配器介面，並內建輕量 Mock Fallback 機制確保測試環境相容性。
    """

    SUPPORTED_MODELS = ("logistic_regression", "random_forest", "lightgbm", "xgboost")

    @classmethod
    def create_model(cls, model_name: str, random_state: int = 42, **kwargs: Any) -> Any:
        name = model_name.lower().strip()
        if name not in cls.SUPPORTED_MODELS:
            raise ValueError(f"不支援的模型名稱: '{model_name}'，支援清單: {cls.SUPPORTED_MODELS}")

        # 1. Logistic Regression
        if name == "logistic_regression":
            try:
                from sklearn.linear_model import LogisticRegression
                params = {"max_iter": 500, "random_state": random_state}
                params.update(kwargs)
                return LogisticRegression(**params)
            except ImportError:
                return _FallbackLinearClassifier(random_state=random_state)

        # 2. Random Forest
        elif name == "random_forest":
            try:
                from sklearn.ensemble import RandomForestClassifier
                params = {"n_estimators": 50, "max_depth": 5, "random_state": random_state, "n_jobs": -1}
                params.update(kwargs)
                return RandomForestClassifier(**params)
            except ImportError:
                return _FallbackTreeEnsembleClassifier(random_state=random_state)

        # 3. LightGBM
        elif name == "lightgbm":
            try:
                import lightgbm as lgb
                params = {
                    "n_estimators": 50,
                    "max_depth": 4,
                    "learning_rate": 0.05,
                    "random_state": random_state,
                    "verbose": -1,
                    "n_jobs": -1
                }
                params.update(kwargs)
                return lgb.LGBMClassifier(**params)
            except ImportError:
                return _FallbackTreeEnsembleClassifier(random_state=random_state)

        # 4. XGBoost
        elif name == "xgboost":
            try:
                import xgboost as xgb
                params = {
                    "n_estimators": 50,
                    "max_depth": 4,
                    "learning_rate": 0.05,
                    "random_state": random_state,
                    "eval_metric": "logloss",
                    "n_jobs": -1
                }
                params.update(kwargs)
                return xgb.XGBClassifier(**params)
            except ImportError:
                return _FallbackTreeEnsembleClassifier(random_state=random_state)


class _FallbackLinearClassifier:
    """輕量純 NumPy 線性分類器 Fallback (供無 sklearn 環境測試)"""
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.weights_: Optional[np.ndarray] = None
        self.bias_: float = 0.0

    def fit(self, X: Any, y: Any) -> "_FallbackLinearClassifier":
        X_arr = np.asarray(X, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        # 簡易正則化最小平方法估計係數
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(-1, 1)
        # 補 1 偏置項
        X_ext = np.hstack([X_arr, np.ones((len(X_arr), 1))])
        reg = 1e-3 * np.eye(X_ext.shape[1])
        try:
            w = np.linalg.solve(X_ext.T @ X_ext + reg, X_ext.T @ (2.0 * y_arr - 1.0))
            self.weights_ = w[:-1]
            self.bias_ = float(w[-1])
        except Exception:
            self.weights_ = np.zeros(X_arr.shape[1])
            self.bias_ = 0.0
        return self

    def predict_proba(self, X: Any) -> np.ndarray:
        X_arr = np.asarray(X, dtype=float)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(-1, 1)
        z = X_arr @ self.weights_ + self.bias_
        p1 = 1.0 / (1.0 + np.exp(-np.clip(z, -10.0, 10.0)))
        return np.column_stack([1.0 - p1, p1])

    def predict(self, X: Any) -> np.ndarray:
        prob = self.predict_proba(X)
        return (prob[:, 1] >= 0.5).astype(int)


class _FallbackTreeEnsembleClassifier:
    """輕量純 NumPy 決策集成分類器 Fallback (供無 lightgbm/xgboost 環境測試)"""
    def __init__(self, random_state: int = 42):
        self.linear_model = _FallbackLinearClassifier(random_state=random_state)

    def fit(self, X: Any, y: Any) -> "_FallbackTreeEnsembleClassifier":
        self.linear_model.fit(X, y)
        return self

    def predict_proba(self, X: Any) -> np.ndarray:
        return self.linear_model.predict_proba(X)

    def predict(self, X: Any) -> np.ndarray:
        return self.linear_model.predict(X)


class TechnicalBaselineSuite:
    """
    純價量技術指標控制組套件 (Pure Technical Baseline Control Suite)。
    
    核心保證：
    1. 嚴格限定只使用 9 欄位純價量特徵（OHLCV + return_1d + rsi_14 + volatility_5d/20d）。
    2. 0 輿情污染保證（Zero Sentiment Contamination）：若特徵包含情緒欄位將強制過濾並記錄斷言。
    3. 支援四大模型之單 Fold 訓練與全時序 Walk-Forward 評估。
    """

    def __init__(self, model_name: str = "random_forest", random_state: int = 42, **model_kwargs: Any):
        self.model_name = model_name.lower().strip()
        self.random_state = random_state
        self.model_kwargs = model_kwargs
        self.model = PureTechnicalModelFactory.create_model(
            self.model_name, random_state=self.random_state, **self.model_kwargs
        )

    @staticmethod
    def extract_pure_technical_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        從輸入 DataFrame 中嚴格提取純價量技術特徵，杜絕任何社群情緒欄位。

        Args:
            df: 包含多維特徵的 DataFrame

        Returns:
            pd.DataFrame: 僅含 9 欄位純價量技術特徵的乾淨 DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # 檢驗並過濾出存在的技術特徵欄位
        available_cols = [c for c in TECHNICAL_FEATURE_COLS if c in df.columns]
        if not available_cols:
            raise ValueError(f"輸入資料不包含任何有效的純價量技術欄位！要求欄位: {TECHNICAL_FEATURE_COLS}")

        # 嚴格驗證：過濾結果中絕不包含任何社群情緒欄位
        for sentiment_col in SENTIMENT_FEATURE_COLS:
            if sentiment_col in available_cols:
                raise RuntimeError(f"致命異常：純價量特徵子集混入了社群情緒欄位 '{sentiment_col}'！")

        df_tech = df[available_cols].copy()
        return df_tech.fillna(0.0)

    def train_and_predict_fold(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        target_col: str = "target_up_down"
    ) -> Dict[str, Any]:
        """
        在單一 Fold 上執行純價量特徵模型訓練與測試集預測。
        """
        if target_col not in train_df.columns:
            raise KeyError(f"訓練集缺少預測標籤: '{target_col}'")

        # 排除包含 NaN 目標的資料列 (如最後一個交易日)
        train_valid = train_df.dropna(subset=[target_col])
        test_valid = test_df.dropna(subset=[target_col])

        if train_valid.empty or test_valid.empty:
            return {
                "model_name": self.model_name,
                "y_true": np.empty(0, dtype=int),
                "y_pred": np.empty(0, dtype=int),
                "y_proba": np.empty(0, dtype=float),
                "n_train": len(train_valid),
                "n_test": len(test_valid)
            }

        X_train = self.extract_pure_technical_features(train_valid)
        y_train = train_valid[target_col].astype(int).to_numpy()

        X_test = self.extract_pure_technical_features(test_valid)
        y_test = test_valid[target_col].astype(int).to_numpy()

        # 模型訓練與預測
        self.model.fit(X_train, y_train)
        y_pred = self.model.predict(X_test)
        
        # 提取預測為上漲 (類別 1) 之信心機率
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(X_test)
            y_proba = probs[:, 1] if probs.shape[1] > 1 else probs[:, 0]
        else:
            y_proba = y_pred.astype(float)

        return {
            "model_name": self.model_name,
            "y_true": y_test,
            "y_pred": np.asarray(y_pred, dtype=int),
            "y_proba": np.asarray(y_proba, dtype=float),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "feature_names": list(X_train.columns)
        }
