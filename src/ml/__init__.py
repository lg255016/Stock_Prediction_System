"""
金融情緒與股價趨勢預測系統 - Phase 3 機器學習模組
包含時序滾動切分 (WalkForwardSplitter)、基準模型、特徵融合訓練器、多模型競技評估器與即時推論引擎。
"""

from .time_series_split import WalkForwardSplitter
from .baseline_models import (
    DummyBaselineClassifier,
    PureTechnicalModelFactory,
    TechnicalBaselineSuite,
    TECHNICAL_FEATURE_COLS,
    SENTIMENT_FEATURE_COLS,
)
from .model_trainer import (
    MultiModalTrainer,
    ALL_MULTIMODAL_FEATURE_COLS,
    create_scaler,
)
from .evaluator import (
    MLEvaluator,
    compute_classification_metrics,
    compute_financial_strategy_metrics,
)
from .predictor import StockTrendPredictor

__all__ = [
    "WalkForwardSplitter",
    "DummyBaselineClassifier",
    "PureTechnicalModelFactory",
    "TechnicalBaselineSuite",
    "MultiModalTrainer",
    "MLEvaluator",
    "StockTrendPredictor",
    "compute_classification_metrics",
    "compute_financial_strategy_metrics",
    "TECHNICAL_FEATURE_COLS",
    "SENTIMENT_FEATURE_COLS",
    "ALL_MULTIMODAL_FEATURE_COLS",
    "create_scaler",
]
