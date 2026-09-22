import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .baseline_models import TechnicalBaselineSuite
from .model_trainer import MultiModalTrainer

logger = logging.getLogger(__name__)


def compute_classification_metrics(
    y_true: Union[List[int], np.ndarray],
    y_pred: Union[List[int], np.ndarray],
    y_proba: Optional[Union[List[float], np.ndarray]] = None
) -> Dict[str, float]:
    """
    以純 NumPy 向量化計算完整分類統計指標（無任何環境依賴）。

    Returns:
        Dict[str, float]: accuracy, precision, recall, f1, macro_f1, roc_auc, brier_score
    """
    y_t = np.asarray(y_true, dtype=int)
    y_p = np.asarray(y_pred, dtype=int)

    if len(y_t) == 0:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "macro_f1": 0.0,
            "roc_auc": 0.5,
            "brier_score": 0.0,
        }

    tp = np.sum((y_t == 1) & (y_p == 1))
    tn = np.sum((y_t == 0) & (y_p == 0))
    fp = np.sum((y_t == 0) & (y_p == 1))
    fn = np.sum((y_t == 1) & (y_p == 0))

    accuracy = (tp + tn) / len(y_t) if len(y_t) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # 類別 0 的 F1
    prec_0 = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    rec_0 = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1_0 = (2.0 * prec_0 * rec_0) / (prec_0 + rec_0) if (prec_0 + rec_0) > 0 else 0.0
    macro_f1 = (f1 + f1_0) / 2.0

    # ROC-AUC 梯形積分 / Mann-Whitney 演算法
    roc_auc = 0.5
    brier_score = 0.0
    if y_proba is not None:
        y_prob_arr = np.asarray(y_proba, dtype=float)
        brier_score = float(np.mean((y_prob_arr - y_t) ** 2))

        # 純數值 ROC-AUC 計算
        pos_mask = (y_t == 1)
        neg_mask = (y_t == 0)
        n_pos = np.sum(pos_mask)
        n_neg = np.sum(neg_mask)
        if n_pos > 0 and n_neg > 0:
            # 依機率由小到大排名
            ranks = pd.Series(y_prob_arr).rank(method="average").to_numpy()
            sum_pos_ranks = np.sum(ranks[pos_mask])
            u_stat = sum_pos_ranks - (n_pos * (n_pos + 1.0)) / 2.0
            roc_auc = float(u_stat / (n_pos * n_neg))
        else:
            roc_auc = 0.5

    return {
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "macro_f1": round(float(macro_f1), 4),
        "roc_auc": round(float(roc_auc), 4),
        "brier_score": round(float(brier_score), 4),
    }


def compute_financial_strategy_metrics(
    y_pred: Union[List[int], np.ndarray],
    actual_returns: Union[List[float], np.ndarray],
    risk_free_rate: float = 0.015
) -> Dict[str, float]:
    """
    計算金融量化模擬策略指標。
    
    策略定義：
    - 多空雙向策略 (Long/Short Strategy)：當 y_pred == 1 做多，y_pred == 0 做空。
    - 策略單期對數報酬率：r_strat = (2 * y_pred - 1) * r_actual
    """
    y_p = np.asarray(y_pred, dtype=int)
    r_act = np.asarray(actual_returns, dtype=float)

    if len(y_p) == 0 or len(r_act) == 0:
        return {
            "directional_hit_ratio": 0.0,
            "cumulative_strategy_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        }

    # 1. 漲跌方向命中率 (Directional Hit Ratio)
    # 若實際報酬為正且預測為 1，或實際報酬為負且預測為 0
    correct_dir = ((r_act >= 0) & (y_p == 1)) | ((r_act < 0) & (y_p == 0))
    hit_ratio = np.mean(correct_dir)

    # 2. 多空策略報酬率序列
    signals = 2.0 * y_p - 1.0  # +1 或 -1
    strat_log_returns = signals * r_act

    # 累積策略報酬率 (exp(cumsum) - 1)
    cum_returns = np.exp(np.cumsum(strat_log_returns)) - 1.0
    total_return = cum_returns[-1] if len(cum_returns) > 0 else 0.0

    # 年化報酬與年化波動率
    n_periods = len(strat_log_returns)
    ann_factor = 252.0 / max(n_periods, 1)
    mean_ret = np.mean(strat_log_returns)
    std_ret = np.std(strat_log_returns)

    ann_return = mean_ret * 252.0
    ann_vol = std_ret * np.sqrt(252.0)

    # 夏普比率 (Sharpe Ratio)
    sharpe = (ann_return - risk_free_rate) / ann_vol if ann_vol > 0 else 0.0

    # 最大回撤 (Maximum Drawdown, MDD)
    equity_curve = 1.0 + cum_returns
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - running_max) / running_max
    max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    return {
        "directional_hit_ratio": round(float(hit_ratio), 4),
        "cumulative_strategy_return": round(float(total_return), 4),
        "annualized_return": round(float(ann_return), 4),
        "annualized_volatility": round(float(ann_vol), 4),
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown": round(float(abs(max_dd)), 4),
    }


class MLEvaluator:
    """
    機器學習多模型橫向競技評估器 (Multi-Model Tournament Evaluator)。
    
    核心功能：
    1. 執行 8 組平行對照實驗（4 大演算法 x 2 組特徵集）。
    2. 量化各模型之 Alpha 增益：ΔF1 = F1(MultiModal) - F1(PureTech)。
    3. 產出橫向對比排行榜（Leaderboard）並自動選出全系統冠軍模型（Champion Model）。
    """

    SUPPORTED_MODELS = ("logistic_regression", "random_forest", "lightgbm", "xgboost")

    def __init__(self, random_state: int = 42):
        self.random_state = random_state

    def evaluate_tournament(
        self,
        df: pd.DataFrame,
        splitter: Any,
        target_col: str = "target_up_down",
        return_col: str = "target_return_1d"
    ) -> Dict[str, Any]:
        """
        在 Walk-Forward 時序切分器上執行全量 8 組平行實驗並產出排行榜。

        Returns:
            Dict[str, Any]:
                - leaderboard: 排行榜 DataFrame
                - alpha_attribution: 各模型之 Alpha 增益摘要字典
                - champion_model_name: 綜合表現最優之冠軍模型代碼
        """
        experiment_results: List[Dict[str, Any]] = []

        for model_name in self.SUPPORTED_MODELS:
            # ----------------------------------------------------
            # 1. 執行控制組 (EXP-xA: Pure Technical)
            # ----------------------------------------------------
            tech_suite = TechnicalBaselineSuite(model_name=model_name, random_state=self.random_state)
            tech_y_true, tech_y_pred, tech_y_proba, tech_returns = [], [], [], []

            for train_idx, test_idx, _ in splitter.split(df):
                train_df = df.iloc[train_idx]
                test_df = df.iloc[test_idx]
                res = tech_suite.train_and_predict_fold(train_df, test_df, target_col=target_col)
                if len(res["y_true"]) > 0:
                    tech_y_true.extend(res["y_true"])
                    tech_y_pred.extend(res["y_pred"])
                    tech_y_proba.extend(res["y_proba"])
                    # 提取對應實際報酬
                    valid_test = test_df.dropna(subset=[target_col])
                    if return_col in valid_test.columns:
                        tech_returns.extend(valid_test[return_col].to_numpy())
                    else:
                        tech_returns.extend(np.where(res["y_true"] == 1, 0.01, -0.01))

            tech_cls_metrics = compute_classification_metrics(tech_y_true, tech_y_pred, tech_y_proba)
            tech_fin_metrics = compute_financial_strategy_metrics(tech_y_pred, tech_returns)

            experiment_results.append({
                "experiment_id": f"EXP-{model_name[:2].upper()}-TECH",
                "model_name": model_name,
                "feature_set": "PureTechnical (9 Feat)",
                "macro_f1": tech_cls_metrics["macro_f1"],
                "accuracy": tech_cls_metrics["accuracy"],
                "roc_auc": tech_cls_metrics["roc_auc"],
                "directional_hit_ratio": tech_fin_metrics["directional_hit_ratio"],
                "cumulative_return": tech_fin_metrics["cumulative_strategy_return"],
                "sharpe_ratio": tech_fin_metrics["sharpe_ratio"],
                "max_drawdown": tech_fin_metrics["max_drawdown"],
            })

            # ----------------------------------------------------
            # 2. 執行實驗組 (EXP-xB: Multi-Modal Sentiment)
            # ----------------------------------------------------
            mm_trainer = MultiModalTrainer(model_name=model_name, scaler_type="robust", random_state=self.random_state)
            mm_y_true, mm_y_pred, mm_y_proba, mm_returns = [], [], [], []

            for train_idx, test_idx, _ in splitter.split(df):
                train_df = df.iloc[train_idx]
                test_df = df.iloc[test_idx]
                res = mm_trainer.train_and_predict_fold(train_df, test_df, target_col=target_col)
                if len(res["y_true"]) > 0:
                    mm_y_true.extend(res["y_true"])
                    mm_y_pred.extend(res["y_pred"])
                    mm_y_proba.extend(res["y_proba"])
                    valid_test = test_df.dropna(subset=[target_col])
                    if return_col in valid_test.columns:
                        mm_returns.extend(valid_test[return_col].to_numpy())
                    else:
                        mm_returns.extend(np.where(res["y_true"] == 1, 0.01, -0.01))

            mm_cls_metrics = compute_classification_metrics(mm_y_true, mm_y_pred, mm_y_proba)
            mm_fin_metrics = compute_financial_strategy_metrics(mm_y_pred, mm_returns)

            experiment_results.append({
                "experiment_id": f"EXP-{model_name[:2].upper()}-MM",
                "model_name": model_name,
                "feature_set": "MultiModal (18 Feat)",
                "macro_f1": mm_cls_metrics["macro_f1"],
                "accuracy": mm_cls_metrics["accuracy"],
                "roc_auc": mm_cls_metrics["roc_auc"],
                "directional_hit_ratio": mm_fin_metrics["directional_hit_ratio"],
                "cumulative_return": mm_fin_metrics["cumulative_strategy_return"],
                "sharpe_ratio": mm_fin_metrics["sharpe_ratio"],
                "max_drawdown": mm_fin_metrics["max_drawdown"],
            })

        df_leaderboard = pd.DataFrame(experiment_results)

        # ----------------------------------------------------
        # 3. 計算 Alpha 增益 (ΔF1 與 ΔReturn)
        # ----------------------------------------------------
        alpha_attribution: Dict[str, Dict[str, float]] = {}
        for m in self.SUPPORTED_MODELS:
            m_tech = df_leaderboard[(df_leaderboard["model_name"] == m) & (df_leaderboard["feature_set"].str.contains("PureTechnical"))].iloc[0]
            m_mm = df_leaderboard[(df_leaderboard["model_name"] == m) & (df_leaderboard["feature_set"].str.contains("MultiModal"))].iloc[0]

            delta_f1 = m_mm["macro_f1"] - m_tech["macro_f1"]
            delta_ret = m_mm["cumulative_return"] - m_tech["cumulative_return"]
            delta_hit = m_mm["directional_hit_ratio"] - m_tech["directional_hit_ratio"]

            alpha_attribution[m] = {
                "delta_macro_f1": round(float(delta_f1), 4),
                "delta_cumulative_return": round(float(delta_ret), 4),
                "delta_hit_ratio": round(float(delta_hit), 4),
                "sentiment_effective": bool(delta_f1 >= 0.0 or delta_ret >= 0.0),
            }

        # ----------------------------------------------------
        # 4. 評選冠軍模型 (依多模態組 Macro F1 與 累積報酬 綜合排名)
        # ----------------------------------------------------
        mm_only = df_leaderboard[df_leaderboard["feature_set"].str.contains("MultiModal")].copy()
        # 綜合得分 = F1 * 0.6 + Sharpe * 0.4 (或 Macro F1 優先)
        mm_only["score"] = mm_only["macro_f1"] * 0.7 + mm_only["directional_hit_ratio"] * 0.3
        champion_row = mm_only.sort_values(by="score", ascending=False).iloc[0]
        champion_model_name = champion_row["model_name"]

        return {
            "leaderboard": df_leaderboard,
            "alpha_attribution": alpha_attribution,
            "champion_model_name": champion_model_name,
            "champion_score": round(float(champion_row["score"]), 4),
        }
