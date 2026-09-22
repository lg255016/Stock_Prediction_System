"""
tests/test_generate_tournament_artifact.py

UG-G1-SB3：驗證 scripts/generate_tournament_artifact.py 的資料量防線
（PO 2026-08-26 裁示）。完全使用合成資料，不連接任何資料庫。

背景：`MLEvaluator.evaluate_tournament()` 在 Walk-Forward 產生零個 Fold 時，
`compute_financial_strategy_metrics([], [])` 仍會回傳一組全為 0 的合法指標字典，
`evaluate_tournament()` 因此仍會為 4 個演算法 × 2 個特徵集組出 8 列——是一份
「滿版但全部零分」的排行榜，不是空排行榜。單純檢查「leaderboard 是否為空」
攔不住這個情況。本檔驗證改用「唯一交易日數是否足夠」的防線後，
資料不足時會被明確擋下（不寫出 artifact），資料足夠時能正常跑出非零結果。
"""

import io
import unittest
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from scripts.generate_tournament_artifact import check_sufficient_data
from src.ml.evaluator import MLEvaluator
from src.ml.time_series_split import WalkForwardSplitter
from src.transform.feature_aggregator import FeatureAggregator
from src.ui.data_loader import _stringify_date_columns


class CheckSufficientDataTests(unittest.TestCase):
    """純函式層級：check_sufficient_data() 的邊界行為。"""

    def test_known_fail_insufficient_data_is_blocked(self):
        """known-FAIL 示範：資料量不足時必須被明確擋下並清楚說明所需天數與實際天數。"""
        with self.assertRaises(RuntimeError) as ctx:
            check_sufficient_data(unique_dates=50, train_window_size=60, test_window_size=20)
        msg = str(ctx.exception)
        self.assertIn("50", msg)
        self.assertIn("80", msg)  # 60 + 20

    def test_sufficient_data_passes_without_exception(self):
        """剛好等於門檻與明顯超過門檻皆不應拋錯。"""
        check_sufficient_data(unique_dates=80, train_window_size=60, test_window_size=20)
        check_sufficient_data(unique_dates=200, train_window_size=60, test_window_size=20)


class TournamentPipelineWithSyntheticDataTests(unittest.TestCase):
    """
    端到端驗證（純合成資料、不連 DB）：防線通過後，把資料實際餵進
    evaluate_tournament()，確認產出的是真的訓練過的非零結果——
    不是只驗證「防線沒擋下」，而是驗證擋下之後的路徑真的能跑出東西。
    """

    def _build_synthetic_panel(self, n_days: int) -> pd.DataFrame:
        rng = np.random.RandomState(42)
        dates = pd.date_range("2026-01-01", periods=n_days, freq="B").strftime("%Y-%m-%d").tolist()
        prices = 100.0 + np.cumsum(rng.normal(0, 1.0, n_days))
        df_prices = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * n_days,
            "close_price": prices,
            "volume": [1000] * n_days,
        })
        df_articles = pd.DataFrame({
            "article_id": list(range(n_days)),
            "fetch_keyword": ["台積電"] * n_days,
            "post_time": [f"{d} 10:00:00" for d in dates],
            "sentiment_score": rng.uniform(0.3, 0.7, n_days).tolist(),
        })
        df_mapping = pd.DataFrame({
            "keyword": ["台積電"], "stock_id": ["2330"], "market": ["TWSE"], "description": ["中文全稱"],
        })

        with redirect_stdout(io.StringIO()):
            aggregator = FeatureAggregator()
            df_features = aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            df_features = aggregator.generate_target_labels(df_features)
        return _stringify_date_columns(df_features)

    def test_insufficient_synthetic_data_blocked_before_any_evaluation(self):
        """資料量不足時，防線必須在呼叫 evaluate_tournament() 之前就擋下——不產出任何排行榜。"""
        df_features = self._build_synthetic_panel(n_days=15)
        unique_dates = pd.to_datetime(df_features["trade_date"]).nunique()

        with self.assertRaises(RuntimeError):
            check_sufficient_data(unique_dates, train_window_size=60, test_window_size=20)
        # 防線本身就是入口——check_sufficient_data 拋錯後，呼叫端（main()）不會走到
        # evaluate_tournament() 或寫檔那一行，這是由控制流保證，非本測試斷言範圍。

    def test_sufficient_synthetic_data_produces_real_nonzero_leaderboard(self):
        """資料量足夠時，通過防線後應能正常跑完並產生非零、真的訓練過的排行榜。"""
        df_features = self._build_synthetic_panel(n_days=90)
        unique_dates = pd.to_datetime(df_features["trade_date"]).nunique()

        check_sufficient_data(unique_dates, train_window_size=30, test_window_size=10)

        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        evaluator = MLEvaluator(random_state=42)
        with redirect_stdout(io.StringIO()):
            result = evaluator.evaluate_tournament(df_features, splitter)

        leaderboard = result["leaderboard"]
        self.assertFalse(leaderboard.empty)
        self.assertEqual(len(leaderboard), 8)  # 4 演算法 x 2 特徵集
        # 零 Fold 情境下 compute_financial_strategy_metrics 回傳全 0——
        # 這裡驗證的是「真的訓練過」，不是「防線沒擋下」。
        self.assertGreater(leaderboard["macro_f1"].abs().sum(), 0.0)


if __name__ == "__main__":
    unittest.main()
