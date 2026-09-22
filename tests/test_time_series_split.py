import io
import unittest
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from src.ml.time_series_split import WalkForwardSplitter
from src.transform.feature_aggregator import FeatureAggregator
from src.ui.data_loader import _stringify_date_columns


class WalkForwardSplitterUnitTests(unittest.TestCase):
    """測試 WalkForwardSplitter 的參數驗證、切分邊界與零前視偏誤防護"""

    def test_initialization_validation(self):
        # 1. 正常初始化
        splitter = WalkForwardSplitter(train_window_size=60, test_window_size=20, mode="rolling")
        self.assertEqual(splitter.train_window_size, 60)
        self.assertEqual(splitter.test_window_size, 20)
        self.assertEqual(splitter.step_size, 20)
        self.assertEqual(splitter.mode, "rolling")

        # 1a. UG-G1-SB1：label_horizon / embargo_days 預設值 (DEC-011)
        self.assertEqual(splitter.label_horizon, 1)
        self.assertEqual(splitter.embargo_days, 0)
        # min_train_size 未顯式指定時，預設容許 Purge 造成的縮減 (60 - 1 = 59)
        self.assertEqual(splitter.min_train_size, 59)

        # 2. 異常參數防護
        with self.assertRaises(ValueError):
            WalkForwardSplitter(train_window_size=0)

        with self.assertRaises(ValueError):
            WalkForwardSplitter(test_window_size=-5)

        with self.assertRaises(ValueError):
            WalkForwardSplitter(mode="random_kfold")

        with self.assertRaises(ValueError):
            WalkForwardSplitter(step_size=0)

        with self.assertRaises(ValueError):
            WalkForwardSplitter(label_horizon=-1)

        with self.assertRaises(ValueError):
            WalkForwardSplitter(embargo_days=-1)

    def test_rolling_mode_splits_and_temporal_invariants(self):
        # 建立 100 天交易日資料 (單檔股票)
        dates = pd.date_range("2026-01-01", periods=100, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 100,
            "close_price": np.linspace(100, 200, 100)
        })

        splitter = WalkForwardSplitter(
            train_window_size=40,
            test_window_size=20,
            step_size=20,
            mode="rolling"
        )

        n_splits = splitter.get_n_splits(df)
        self.assertEqual(n_splits, 3)

        folds = list(splitter.split(df))
        self.assertEqual(len(folds), 3)

        # UG-G1-SB1（Purged Walk-Forward）：預設 label_horizon=1，訓練窗尾端 1 天
        # 因 Purge 被移除（40 天窗口實得 39 天）。Purge 本身的專屬測試見
        # PurgedWalkForwardTests；本測試維持既有窗口/步長邏輯的迴歸覆蓋。
        expected_train_days_per_fold = 40 - 1

        # 逐 Fold 驗證嚴格時間約束
        prev_test_end = None
        for fold_idx, (train_idx, test_idx, meta) in enumerate(folds):
            self.assertEqual(meta["fold"], fold_idx)
            self.assertEqual(meta["train_days"], expected_train_days_per_fold)
            self.assertEqual(meta["test_days"], 20)
            self.assertEqual(len(train_idx), expected_train_days_per_fold)
            self.assertEqual(len(test_idx), 20)

            # 1. 索引絕對無交集 (Zero Overlap)
            intersection = np.intersect1d(train_idx, test_idx)
            self.assertEqual(len(intersection), 0)

            # 2. 訓練集最大時間嚴格小於測試集最小時間 (Arrow of Time)
            train_dates = df.iloc[train_idx]["trade_date"].tolist()
            test_dates = df.iloc[test_idx]["trade_date"].tolist()
            self.assertLess(max(train_dates), min(test_dates))

            # 3. 滾動模式：訓練窗口固定為 40 天，Purge 後為 39 天
            self.assertEqual(len(train_dates), expected_train_days_per_fold)

            # 4. 驗證 step_size 無縫銜接
            if prev_test_end is not None:
                self.assertEqual(min(test_dates), prev_test_end)
            prev_test_end = dates[40 + (fold_idx + 1) * 20] if 40 + (fold_idx + 1) * 20 < 100 else None

    def test_expanding_mode_accumulates_historical_data(self):
        # 建立 80 天交易日資料
        dates = pd.date_range("2026-01-01", periods=80, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["NVDA"] * 80,
            "close_price": np.linspace(50, 150, 80)
        })

        splitter = WalkForwardSplitter(
            train_window_size=30,
            test_window_size=15,
            step_size=15,
            mode="expanding"
        )

        n_splits = splitter.get_n_splits(df)
        self.assertEqual(n_splits, 3)

        folds = list(splitter.split(df))
        self.assertEqual(len(folds), 3)

        # Fold 0: train 0~29 (30天), test 30~44 (15天)
        # Fold 1: train 0~44 (45天), test 45~59 (15天)
        # Fold 2: train 0~59 (60天), test 60~74 (15天)
        # UG-G1-SB1：預設 label_horizon=1，各 Fold 訓練窗尾端 1 天因 Purge 被移除。
        expected_train_days = [29, 44, 59]
        for fold_idx, (train_idx, test_idx, meta) in enumerate(folds):
            self.assertEqual(meta["train_days"], expected_train_days[fold_idx])
            self.assertEqual(meta["test_days"], 15)
            # 起點永遠從 2026-01-01 開始累積
            self.assertEqual(meta["train_start_date"], "2026-01-01")
            self.assertLess(meta["train_end_date"], meta["test_start_date"])

    def test_multi_stock_global_date_alignment(self):
        # 建立 3 檔股票跨 50 天資料 (共 150 筆)
        dates = pd.date_range("2026-01-01", periods=50, freq="D").strftime("%Y-%m-%d")
        records = []
        for d in dates:
            for s in ["2330", "2382", "NVDA"]:
                records.append({"trade_date": d, "stock_id": s, "close_price": 100.0})
        df = pd.DataFrame(records)

        splitter = WalkForwardSplitter(
            train_window_size=20,
            test_window_size=10,
            step_size=10,
            mode="rolling"
        )

        n_splits = splitter.get_n_splits(df)
        self.assertEqual(n_splits, 3)  # (50 - 20 - 10) / 10 + 1 = 3

        # UG-G1-SB1：預設 label_horizon=1，訓練窗尾端 1 天因 Purge 被移除 (20 天 -> 19 天)。
        for fold_idx, (train_idx, test_idx, meta) in enumerate(splitter.split(df)):
            self.assertEqual(meta["train_days"], 19)
            self.assertEqual(meta["test_days"], 10)

            # 每檔股票每天有 1 筆，Purge 後 train_samples 應為 19 * 3 = 57
            self.assertEqual(len(train_idx), 57)
            self.assertEqual(len(test_idx), 30)

            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]

            # 驗證所有股票均落在同一個時序區間
            self.assertEqual(set(train_df["stock_id"]), {"2330", "2382", "NVDA"})
            self.assertEqual(set(test_df["stock_id"]), {"2330", "2382", "NVDA"})
            self.assertLess(train_df["trade_date"].max(), test_df["trade_date"].min())

    def test_insufficient_dates_and_empty_inputs(self):
        splitter = WalkForwardSplitter(train_window_size=60, test_window_size=20)

        # 1. None 與空 DataFrame
        self.assertEqual(splitter.get_n_splits(None), 0)
        self.assertEqual(splitter.get_n_splits(pd.DataFrame()), 0)
        self.assertEqual(list(splitter.split(pd.DataFrame())), [])

        # 2. 交易日數不足 (只有 70 天，不足 60+20=80 天)
        dates = pd.date_range("2026-01-01", periods=70, freq="D").strftime("%Y-%m-%d")
        df_short = pd.DataFrame({"trade_date": dates, "stock_id": ["2330"] * 70})
        self.assertEqual(splitter.get_n_splits(df_short), 0)
        self.assertEqual(list(splitter.split(df_short)), [])

    def test_missing_date_column_raises_key_error(self):
        splitter = WalkForwardSplitter(date_col="trade_date")
        df_wrong = pd.DataFrame({"timestamp": ["2026-01-01"], "close_price": [100.0]})
        with self.assertRaises(KeyError):
            splitter.get_n_splits(df_wrong)


class PurgedWalkForwardTests(unittest.TestCase):
    """
    UG-G1-SB1：Purged Walk-Forward 測試 (PURGED_WALK_FORWARD_SPEC.md §5.1, T-PW-01~05)。
    驗證 Purge / Embargo / 核心斷言，涵蓋邊界洩漏修正的正向與失敗路徑。
    """

    def test_purge_removes_label_overlapping_rows(self):
        """T-PW-01: H=1 時，train 尾端 1 天被移除"""
        dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 30,
            "close_price": np.linspace(100, 130, 30)
        })

        splitter = WalkForwardSplitter(
            train_window_size=10, test_window_size=5, step_size=5,
            mode="rolling", label_horizon=1, min_train_size=1
        )

        train_idx, test_idx, meta = next(splitter.split(df))

        self.assertEqual(meta["train_days"], 9)
        self.assertEqual(meta["purged_days"], 1)
        self.assertEqual(meta["purged_samples"], 1)
        self.assertEqual(len(train_idx), 9)

        train_dates = set(df.iloc[train_idx]["trade_date"])
        # 未 Purge 前訓練窗尾端應為第 10 天 (index 9)；Purge 後不得出現於 train
        self.assertNotIn(dates[9], train_dates)
        self.assertIn(dates[8], train_dates)

    def test_fold_skipped_with_warning_when_purge_drops_below_min_train_size(self):
        """
        Gate A DoD 第 2 項 / RISK-001 接受邊界：Purge 後訓練集不足 min_train_size 時，
        該 Fold 跳過並記錄警告 —— 嚴禁縮小 Purge 範圍或放寬 label_end_date 判定以保留 Fold。
        本測試先前為此行為的覆蓋缺口（僅以 min_train_size=1 迴避觸發），現補上正向驗證。
        """
        dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 30,
            "close_price": np.linspace(100, 130, 30)
        })

        # train_window=10, label_horizon=1 -> Purge 後每個 Fold 恆為 9 天；
        # min_train_size=10 使其恆低於門檻，驗證「跳過並警告」而非「縮小 Purge 保留 Fold」。
        splitter = WalkForwardSplitter(
            train_window_size=10, test_window_size=5, step_size=5,
            mode="rolling", label_horizon=1, min_train_size=10
        )

        with self.assertLogs("src.ml.time_series_split", level="WARNING") as log_ctx:
            folds = list(splitter.split(df))

        # 每個 Fold 的 Purge 後訓練天數恆為 9 < min_train_size=10，故全部跳過，產出 0 個 Fold
        self.assertEqual(folds, [])
        self.assertGreaterEqual(len(log_ctx.output), 1)
        warning_text = log_ctx.output[0]
        self.assertIn("Fold 0", warning_text)
        self.assertIn("9", warning_text)  # 實際 Purge 後訓練天數
        self.assertIn("10", warning_text)  # min_train_size 門檻
        self.assertIn("不縮小 Purge 範圍", warning_text)

        # get_n_splits() 只算窗口是否排得下，不知道 Purge 會使 Fold 全數被跳過 ——
        # 與 split() 實際產出的落差正是 get_n_splits() docstring 明示的行為。
        self.assertGreater(splitter.get_n_splits(df), 0)

    def test_purge_h5_removes_five_days(self):
        """T-PW-02: H=5 時，train 尾端 5 天被移除"""
        dates = pd.date_range("2026-01-01", periods=35, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 35,
            "close_price": np.linspace(100, 135, 35)
        })

        splitter = WalkForwardSplitter(
            train_window_size=20, test_window_size=10, step_size=10,
            mode="rolling", label_horizon=5, min_train_size=1
        )

        train_idx, test_idx, meta = next(splitter.split(df))

        self.assertEqual(meta["train_days"], 15)
        self.assertEqual(meta["purged_days"], 5)
        self.assertEqual(meta["purged_samples"], 5)

        train_dates = set(df.iloc[train_idx]["trade_date"])
        for purged_pos in range(15, 20):
            self.assertNotIn(dates[purged_pos], train_dates)
        self.assertIn(dates[14], train_dates)

    def test_embargo_excludes_post_test_train_candidates(self):
        """T-PW-03: embargo_days > 0 時，前一 Fold 測試窗結束後的天數被排除於後續 Fold 訓練候選"""
        dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 30,
            "close_price": np.linspace(100, 130, 30)
        })

        # label_horizon=0 停用 Purge，隔離 Embargo 的效果單獨驗證；
        # step_size(8) > test_window_size(5) 使第二個 Fold 的訓練窗延伸到
        # 第一個 Fold 測試窗結束之後，才有 Embargo 可排除的候選日。
        splitter = WalkForwardSplitter(
            train_window_size=10, test_window_size=5, step_size=8,
            mode="rolling", label_horizon=0, embargo_days=3, min_train_size=1
        )

        folds = list(splitter.split(df))
        self.assertGreaterEqual(len(folds), 2)

        fold0_train_idx, fold0_test_idx, fold0_meta = folds[0]
        self.assertEqual(fold0_meta["test_end_date"], dates[14])

        fold1_train_idx, fold1_test_idx, fold1_meta = folds[1]
        # 未 Embargo 前，Fold 1 訓練窗為 positions 8~17 (10 天)；
        # Embargo 排除 test_end (position14) 之後 3 天 (15,16,17)，故剩 7 天。
        self.assertEqual(fold1_meta["train_days"], 7)
        self.assertEqual(fold1_meta["embargoed_days"], 3)

        fold1_train_dates = set(df.iloc[fold1_train_idx]["trade_date"])
        for excluded_pos in (15, 16, 17):
            self.assertNotIn(dates[excluded_pos], fold1_train_dates)
        self.assertIn(dates[14], fold1_train_dates)

    def test_core_assertion_holds(self):
        """T-PW-04: 所有 Fold 的 max(train.label_end_date) < min(test.trade_date) 恆成立"""
        dates = pd.date_range("2026-01-01", periods=100, freq="D").strftime("%Y-%m-%d")
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 100,
            "close_price": np.linspace(100, 200, 100)
        })
        date_to_gidx = {d: i for i, d in enumerate(dates)}

        splitter = WalkForwardSplitter(
            train_window_size=30, test_window_size=10, step_size=10,
            mode="rolling", label_horizon=3
        )

        folds = list(splitter.split(df))
        self.assertGreater(len(folds), 0)

        for train_idx, test_idx, meta in folds:
            last_train_gidx = date_to_gidx[meta["train_end_date"]]
            label_end_gidx = last_train_gidx + splitter.label_horizon
            self.assertLess(label_end_gidx, len(dates))
            label_end_date = dates[label_end_gidx]
            # DoD／PURGED_WALK_FORWARD_SPEC.md §2.6 核心斷言
            self.assertLess(label_end_date, meta["test_start_date"])

    def test_future_data_mutation(self):
        """T-PW-05: 注入 label_end_date >= test_start_date 的洩漏資料 -> assert_no_boundary_leakage 拋出異常"""
        # 正常情況：所有 label_end_date 皆早於 test_start_date -> 不拋出
        WalkForwardSplitter.assert_no_boundary_leakage(
            train_label_end_dates=["2026-01-08", "2026-01-09", None],
            test_start_date="2026-01-10",
        )

        # 已知會 FAIL 的案例：注入一筆 label_end_date 等於 test_start_date (邊界相等亦視為洩漏)
        with self.assertRaises(RuntimeError):
            WalkForwardSplitter.assert_no_boundary_leakage(
                train_label_end_dates=["2026-01-08", "2026-01-10"],
                test_start_date="2026-01-10",
            )

        # 已知會 FAIL 的案例：注入一筆晚於 test_start_date 的「未來」資料（模擬資料被竄改／洩漏）
        with self.assertRaises(RuntimeError):
            WalkForwardSplitter.assert_no_boundary_leakage(
                train_label_end_dates=["2026-01-08", "2026-01-15"],
                test_start_date="2026-01-10",
                fold_idx=2,
            )

    def test_purge_uses_per_stock_label_end_date_for_calendar_misalignment(self):
        """
        PO 2026-08-25 回報：split() 若僅以全域唯一交易日索引近似 label_end_date，
        個股停牌等造成日曆不對齊時會低估應被 Purge 的列。本測試重現該情境
        （股票 B 於 train 尾端前一天停牌），驗證：
        1. df 含 FeatureAggregator 產出的逐列 label_end_date 欄位時，Purge 正確抓到洩漏列；
        2. 缺該欄位、退回全域曆近似法時，同一筆洩漏列會被誤判為安全（示範舊行為的缺陷，
           呼應 split() docstring 的精度限制揭露）。
        """
        dates = pd.date_range("2026-01-01", periods=20, freq="D").strftime("%Y-%m-%d")

        # 股票 A：連續交易 20 天，無停牌
        df_a = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["A"] * 20,
            "close_price": np.linspace(100, 119, 20)
        })
        # 股票 B：於 dates[9]（train 窗口尾端）停牌，只有 19 筆
        b_dates = [d for i, d in enumerate(dates) if i != 9]
        df_b = pd.DataFrame({
            "trade_date": b_dates,
            "stock_id": ["B"] * 19,
            "close_price": np.linspace(50, 68, 19)
        })
        df_features = pd.concat([df_a, df_b], ignore_index=True)

        with redirect_stdout(io.StringIO()):
            aggregator = FeatureAggregator()
        df_target = aggregator.generate_target_labels(df_features, label_horizon=1)

        # 股票 B 在 dates[8] 那筆的真實 label_end_date：因 dates[9] 停牌，
        # 其個股自身下一交易日是 dates[10] (= test_start_date)，依 §2.6 應被 Purge。
        b_row_at_8 = df_target[(df_target["stock_id"] == "B") & (df_target["trade_date"] == dates[8])]
        self.assertEqual(len(b_row_at_8), 1)
        self.assertEqual(b_row_at_8.iloc[0]["label_end_date"], dates[10])

        splitter = WalkForwardSplitter(
            train_window_size=10, test_window_size=5, step_size=5,
            mode="rolling", label_horizon=1, min_train_size=1
        )

        # --- 1. 精確路徑 (df 含 label_end_date)：B 在 dates[8] 的列必須被 Purge ---
        train_idx, test_idx, meta = next(splitter.split(df_target))
        train_rows = df_target.iloc[train_idx]
        b_leaking_row_present = (
            (train_rows["stock_id"] == "B") & (train_rows["trade_date"] == dates[8])
        ).any()
        self.assertFalse(
            b_leaking_row_present,
            "股票 B 於 dates[8] 的列 label_end_date == test_start_date，必須被 Purge"
        )
        # A 在 dates[8] 的列無停牌干擾，真實 label_end_date=dates[9] < test_start，應保留
        a_row_present = (
            (train_rows["stock_id"] == "A") & (train_rows["trade_date"] == dates[8])
        ).any()
        self.assertTrue(a_row_present)

        # --- 2. Fallback 路徑 (無 label_end_date 欄位)：同一筆列會被誤判為安全，示範修正前缺陷 ---
        df_no_label_end = df_target.drop(columns=["label_end_date"])
        fallback_train_idx, _, _ = next(splitter.split(df_no_label_end))
        fallback_train_rows = df_no_label_end.iloc[fallback_train_idx]
        b_leaking_row_present_fallback = (
            (fallback_train_rows["stock_id"] == "B") & (fallback_train_rows["trade_date"] == dates[8])
        ).any()
        self.assertTrue(
            b_leaking_row_present_fallback,
            "Fallback 近似法假設全域曆對齊，無法偵測股票 B 的個股停牌，"
            "會誤將洩漏列判為安全 —— 此為 docstring 明示的精度限制，非本測試斷言錯誤"
        )


class StringifyDateColumnsRegressionTests(unittest.TestCase):
    """
    UG-G1-SB3 回歸測試：`_fetch_real_stock_features_from_db()` 曾只把 trade_date 轉為
    字串、漏轉 label_end_date，兩欄位型別不一致（str vs. pandas.Timestamp）在
    `WalkForwardSplitter.split()` 逐列比較 `label_end_date >= test_start_date` 時
    以 TypeError 現形。此 bug 自 SB1 起即存在，但直到 SB3 的 artifact 產生腳本第一次
    把 `_fetch_real_stock_features_from_db()` 的輸出接上 `split()` 才被踩到
    （審查員以純合成資料、不連 DB 的方式重現並回報）。

    本測試完全不連接 DB：以與 `_fetch_real_stock_features_from_db()` 內部相同的
    `FeatureAggregator` 呼叫序列（`generate_daily_features` → `generate_target_labels`）
    產生合成特徵矩陣，驗證修正後的 `_stringify_date_columns()` 讓 `split()` 可以
    正常跑完整個生成器，不再拋出 TypeError。
    """

    def _build_synthetic_features(self) -> pd.DataFrame:
        with redirect_stdout(io.StringIO()):
            dates = pd.date_range("2026-07-01", periods=15, freq="B").strftime("%Y-%m-%d").tolist()
            df_prices = pd.DataFrame({
                "trade_date": dates,
                "stock_id": ["2330"] * len(dates),
                "close_price": [100.0 + i for i in range(len(dates))],
                "volume": [1000] * len(dates),
            })
            df_articles = pd.DataFrame({
                "article_id": list(range(len(dates))),
                "fetch_keyword": ["台積電"] * len(dates),
                "post_time": [f"{d} 10:00:00" for d in dates],
                "sentiment_score": [0.5] * len(dates),
            })
            df_mapping = pd.DataFrame({
                "keyword": ["台積電"], "stock_id": ["2330"], "market": ["TWSE"], "description": ["中文全稱"],
            })

            aggregator = FeatureAggregator()
            df_features = aggregator.generate_daily_features(df_prices, df_articles, df_mapping, df_comments=pd.DataFrame())
            df_features = aggregator.generate_target_labels(df_features)
        return df_features

    def test_stringify_date_columns_makes_trade_date_and_label_end_date_consistent_type(self):
        """修正後兩欄位皆為 str（或 NaT 轉出的 None），不再一邊 str 一邊 Timestamp。"""
        df_features = self._build_synthetic_features()
        # 轉換前的真實型別非 str（FeatureAggregator 內部以 datetime.date／Timestamp 表示日期，
        # 具體型別不是本測試重點——重點是「轉換前不是 str」，這正是型別不一致的根源）。
        self.assertNotIsInstance(df_features["label_end_date"].iloc[0], str)

        df_stringified = _stringify_date_columns(df_features)

        non_null_label_end = df_stringified["label_end_date"].dropna()
        self.assertGreater(len(non_null_label_end), 0)
        for v in df_stringified["trade_date"]:
            self.assertIsInstance(v, str)
        for v in non_null_label_end:
            self.assertIsInstance(v, str)

    def test_split_does_not_raise_typeerror_after_stringify_fix(self):
        """修正後把 _fetch_real_stock_features_from_db() 的實際輸出型別餵進 split()，能跑完不拋錯。"""
        df_features = self._build_synthetic_features()
        df_stringified = _stringify_date_columns(df_features)

        splitter = WalkForwardSplitter(train_window_size=6, test_window_size=3, mode="rolling")
        folds = list(splitter.split(df_stringified))  # 曾在此處拋 TypeError；修正前的重現見下方 known-FAIL 測試

        self.assertGreater(len(folds), 0, "測試資料量不足以產生任何 Fold，無法驗證 Purge 比較邏輯是否執行")

    def test_known_fail_unfixed_type_mismatch_raises_typeerror(self):
        """
        known-FAIL 示範（CLAUDE.md §9A.2）：手動重建修正前的型別不一致狀態
        （trade_date 轉字串、label_end_date 維持 Timestamp——即修正前 _fetch_real_stock_features_from_db()
        的真實輸出型別），證明 split() 確實會因此拋出 TypeError，本測試不是裝飾性斷言。
        """
        df_features = self._build_synthetic_features()
        df_features = df_features.copy()
        df_features["trade_date"] = pd.to_datetime(df_features["trade_date"]).dt.strftime("%Y-%m-%d")
        # 刻意不轉換 label_end_date，重現修正前的漏轉

        splitter = WalkForwardSplitter(train_window_size=6, test_window_size=3, mode="rolling")
        with self.assertRaises(TypeError):
            list(splitter.split(df_features))


if __name__ == "__main__":
    unittest.main()
