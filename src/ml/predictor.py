import logging
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from .model_trainer import MultiModalTrainer, ALL_MULTIMODAL_FEATURE_COLS

logger = logging.getLogger(__name__)


class StockTrendPredictor:
    """
    單日即時趨勢推論引擎 (Realtime Stock Trend Predictor)。
    
    核心功能：
    1. 載入訓練完成之最佳冠軍模型（Champion Model）與 Scaler 轉換器。
    2. 接收當日最新 1 筆 18 欄位特徵列，即時輸出明日漲跌方向（UP / DOWN）與信心機率值（0.0 ~ 1.0）。
    3. 解析並輸出前 3 大驅動因子（Top 3 Drivers），為 Phase 4 Streamlit BI 儀表板提供可解釋性 UI 支援。
    """

    def __init__(
        self,
        trainer: Optional[MultiModalTrainer] = None,
        model_artifact_path: Optional[str] = None
    ):
        """
        初始化即時推論引擎。

        Args:
            trainer: 已在記憶體中擬合的 MultiModalTrainer 實例 (優先採用)
            model_artifact_path: 若 trainer 為 None，可直接自磁碟路徑載入序列化模型檔案
        """
        if trainer is not None:
            self.trainer = trainer
        elif model_artifact_path is not None:
            self.trainer = MultiModalTrainer.load_artifact(model_artifact_path)
        else:
            # 預設建立一組空 Trainer (待後續訓練或載入)
            self.trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust")

    def predict_latest(self, df_feature_row: pd.DataFrame) -> Dict[str, Any]:
        """
        接收當日最新 1 筆特徵列，執行推論並輸出決策結構。

        Args:
            df_feature_row: 單列或多列特徵 DataFrame (包含 trade_date, stock_id 及 18 欄位多模態特徵)

        Returns:
            Dict[str, Any]:
                - stock_id: 股票代碼 (str)
                - trade_date: 特徵基準交易日 (str)
                - predicted_direction: 預測方向 ('UP' 或 'DOWN')
                - predicted_label: 預測數值標籤 (1 或 0)
                - confidence_score: 預測上漲之信心機率 (0.0 ~ 1.0)
                - model_name: 使用之冠軍模型代碼 (str)
                - top_drivers: 前 3 大關鍵驅動特徵清單 (List[Dict])
        """
        if df_feature_row is None or df_feature_row.empty:
            raise ValueError("輸入特徵列為空，無法執行即時推論！")

        # 若傳入多筆，預設取最後一筆 (最新交易日)
        row = df_feature_row.iloc[-1:].copy()

        stock_id = str(row["stock_id"].iloc[0]) if "stock_id" in row.columns else "UNKNOWN"
        trade_date = str(row["trade_date"].iloc[0]) if "trade_date" in row.columns else "LATEST"

        # 提取多模態特徵
        X = self.trainer.extract_multimodal_features(row)

        # 透過 Scaler 轉換
        if self.trainer.scaler is not None:
            if hasattr(self.trainer.scaler, "transform"):
                X_scaled = self.trainer.scaler.transform(X)
            else:
                X_scaled = X.to_numpy(dtype=float)
        else:
            X_scaled = X.to_numpy(dtype=float)

        # 執行預測
        if hasattr(self.trainer.model, "predict_proba"):
            probs = self.trainer.model.predict_proba(X_scaled)
            p_up = float(probs[0, 1]) if probs.shape[1] > 1 else float(probs[0, 0])
        else:
            pred_raw = self.trainer.model.predict(X_scaled)
            p_up = float(pred_raw[0])

        p_up = max(0.0, min(1.0, p_up))
        predicted_label = 1 if p_up >= 0.5 else 0
        predicted_direction = "UP" if predicted_label == 1 else "DOWN"

        # ----------------------------------------------------
        # 解析 Top 3 驅動因子 (結合特徵值與特徵重要性權重)
        # ----------------------------------------------------
        top_drivers: List[Dict[str, Any]] = []
        importances = self.trainer.feature_importances_
        if importances:
            # 依重要性降序排序
            sorted_feats = sorted(importances.items(), key=lambda item: item[1], reverse=True)
            for f_name, imp in sorted_feats[:3]:
                f_val = float(row[f_name].iloc[0]) if f_name in row.columns else 0.0
                top_drivers.append({
                    "feature_name": f_name,
                    "feature_value": round(f_val, 4),
                    "importance_weight": round(float(imp), 4),
                })
        else:
            # 若無重要性，預設取前 3 個欄位
            for f_name in ALL_MULTIMODAL_FEATURE_COLS[:3]:
                f_val = float(row[f_name].iloc[0]) if f_name in row.columns else 0.0
                top_drivers.append({
                    "feature_name": f_name,
                    "feature_value": round(f_val, 4),
                    "importance_weight": round(1.0 / 3.0, 4),
                })

        return {
            "stock_id": stock_id,
            "trade_date": trade_date,
            "predicted_direction": predicted_direction,
            "predicted_label": predicted_label,
            "confidence_score": round(p_up, 4),
            "model_name": self.trainer.model_name,
            "top_drivers": top_drivers,
        }
