# -*- coding: utf-8 -*-
"""`UG-G3-SB3` 紅測（RED）——PO 2026-09-12 核准進入實作前指定的第一批紅測。

依 `doc/upgrade/gates/UG_G3_SB3_GATE_A_PROPOSAL.md` §3.3／§3.4／§5／§6，
本檔涵蓋 PO 明確列出的四類紅測：

1. `extract_multimodal_features()` 回歸測試——`SENTIMENT_FEATURE_COLS` 8 欄
   皆須保留 `NaN`（修復前必 FAIL：3 欄現行補 0.5、5 欄落入 `else` 分支補 0.0）。
2. 三個新常數定義測試（`CORE16_STATIONARY_COLS`／`ARM_A_FEATURE_COLS`／
   `ARM_B_FEATURE_COLS`，皆尚不存在，修復前必 FAIL：`ImportError`）。
3. NaN／NULL 標籤處理規則 (a)(b)(c) 測試（`src/ml/specialist_training.py`
   尚不存在，修復前必 FAIL：`ImportError`）。
4. `test_split_refuses_fallback_purge`——`WalkForwardSplitter.split()` 現行
   對缺席的 `label_end_date_col` 靜默走近似 fallback，不拋例外（修復前必
   FAIL：斷言的例外沒有被拋出）。

**額外加入一項**（PO 未明列於本輪紅測清單，但屬 §3.3 附帶條件要求 1 的
直接測試，比照同一流程一併送紅測確認）：`build_panel_dataset()` 須輸出
`label_end_date`（T+1，計算基準為 `df_stock_prices`）。

================================================================================
第二輪複核訂正（PO 2026-09-12）：RED 成立，但兩處介面設計需先修正
================================================================================
1. **`WalkForwardSplitter` 拒絕 fallback 的範圍**：不得一律拋例外——既有
   五個呼叫端（`test_baseline_models.py`／`test_ml_evaluator.py`／
   `test_model_trainer.py`／`test_generate_tournament_artifact.py`／
   `scripts/generate_tournament_artifact.py`）與 `test_time_series_split.py:428`
   皆依賴 fallback，一律拋例外會使它們全部壞掉，範圍溢出 SB3。改為新增
   `require_label_end_date: bool = False` 參數（預設不變既有行為），SB3
   呼叫端傳 `True`；`fold_metadata` 新增 `purge_mode: "exact"|"approximate"`
   誠實回報是否走了 fallback（比拋例外更根本——這才是本缺口沒被發現的
   原因）。
2. **`prepare_fold_data()` 規則 (c) 改為剔除，不拋例外**：面板實測有 17 列
   `amplitude_ratio` NULL，若對照臂 B 遇到非情緒欄 NaN 就整批中止，會讓
   D3 完全跑不完；且 D3 判準要求 A／B 兩臂逐 Fold 用同一批列比較，剔除
   規則必須對兩臂一致套用在「非情緒特徵欄」上，剔除後兩臂保留的列索引
   集合須相等。`ValueError` 保留給剔除後仍殘留 NaN 的防禦性斷言（結構上
   不應觸發，故未寫獨立測試——沒有不修改 `prepare_fold_data()` 內部邏輯
   就能構造出的 known-FAIL 案例，誠實揭露而非硬湊一個）。回傳 dict 新增
   `retained_index`／`trade_date`（供 §3.3 邊界窗/內部窗診斷使用）；
   `arm="A"` 時 `sentiment_cols` 必須為空，否則拋例外。

本檔**純為 RED 證據**——實作完成前，以下全部測試方法預期 FAIL 或 ERROR。
"""
import unittest

import numpy as np
import pandas as pd


class ExtractMultimodalFeaturesSentimentNanTests(unittest.TestCase):
    """`SENTIMENT_FEATURE_COLS` 8 欄皆須保留 `NaN`，不得被 `fillna` 抹平。"""

    def test_all_eight_sentiment_columns_preserve_nan(self):
        from src.ml.baseline_models import SENTIMENT_FEATURE_COLS
        from src.ml.model_trainer import ALL_MULTIMODAL_FEATURE_COLS, MultiModalTrainer

        row = {c: 1.0 for c in ALL_MULTIMODAL_FEATURE_COLS}
        for c in SENTIMENT_FEATURE_COLS:
            row[c] = np.nan
        df = pd.DataFrame([row])

        out = MultiModalTrainer.extract_multimodal_features(df)

        still_filled = [c for c in SENTIMENT_FEATURE_COLS if not pd.isna(out[c].iloc[0])]
        self.assertEqual(
            still_filled, [],
            f"以下情緒欄被 fillna 抹平、未保留 NaN：{still_filled}"
            "（sentiment_mean/sentiment_lag_1/sentiment_lag_2 現行補 0.5；"
            "article_count/bullishness_index/agreement_index/"
            "sentiment_3d_ma/sentiment_5d_ma 落入 else 分支補 0.0）")

    def test_non_sentiment_columns_still_filled(self):
        """非情緒欄的既有補值行為不應被本次修復波及（回歸防護）。"""
        from src.ml.baseline_models import SENTIMENT_FEATURE_COLS
        from src.ml.model_trainer import ALL_MULTIMODAL_FEATURE_COLS, MultiModalTrainer

        row = {c: np.nan for c in ALL_MULTIMODAL_FEATURE_COLS}
        df = pd.DataFrame([row])
        out = MultiModalTrainer.extract_multimodal_features(df)

        non_sentiment = [c for c in ALL_MULTIMODAL_FEATURE_COLS if c not in SENTIMENT_FEATURE_COLS]
        for c in non_sentiment:
            expected = 50.0 if c == "rsi_14" else 0.0
            self.assertEqual(out[c].iloc[0], expected,
                              f"{c} 的既有補值行為不應改變（預期 {expected}）")


class NewFeatureColumnConstantsTests(unittest.TestCase):
    """三個新常數（`baseline_models.py`）尚未定義——ImportError 即為 RED。"""

    def test_core16_stationary_cols_defined(self):
        from src.ml.baseline_models import CORE16_STATIONARY_COLS
        self.assertEqual(
            set(CORE16_STATIONARY_COLS),
            {"amplitude_ratio", "ma5_bias_ratio", "ma20_bias_ratio", "volume_ratio_5d"})
        self.assertEqual(len(CORE16_STATIONARY_COLS), 4)

    def test_arm_a_excludes_raw_price(self):
        from src.ml.baseline_models import ARM_A_FEATURE_COLS, CORE16_STATIONARY_COLS
        self.assertEqual(len(ARM_A_FEATURE_COLS), 8)
        for raw in ("open_price", "high_price", "low_price", "close_price", "volume"):
            self.assertNotIn(raw, ARM_A_FEATURE_COLS,
                              f"對照臂 A 不得含原始價量欄 {raw}（Gate3 §5 只指定 "
                              "CORE_16 平穩化特徵＋4 個技術欄）")
        for c in CORE16_STATIONARY_COLS:
            self.assertIn(c, ARM_A_FEATURE_COLS)
        for c in ("return_1d", "rsi_14", "volatility_5d", "volatility_20d"):
            self.assertIn(c, ARM_A_FEATURE_COLS)

    def test_arm_b_equals_arm_a_plus_sentiment(self):
        from src.ml.baseline_models import (
            ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS)
        self.assertEqual(
            set(ARM_B_FEATURE_COLS), set(ARM_A_FEATURE_COLS) | set(SENTIMENT_FEATURE_COLS))
        self.assertEqual(len(ARM_B_FEATURE_COLS), 16)


class NullHandlingRulesTests(unittest.TestCase):
    """規則 (a)(b)(c)——`src/ml/specialist_training.py` 尚不存在，ImportError 即為 RED。

    **訂正版**（PO 2026-09-12 第二輪複核）：規則 (b) 的剔除統一套用在
    「非情緒特徵欄」上，對照臂 A／B 一視同仁，剔除後兩臂保留的列索引集合
    必須相等（D3 判準要求同一批列比較）；規則 (c) 從「拋例外」改為剔除後
    的防禦性斷言（結構上不應觸發，未寫獨立測試——見下方類別 docstring）。
    """

    def _panel(self, f1, s1=None, target=None, n=None):
        n = n or len(f1)
        data = {
            "f1": f1,
            "trade_date": pd.date_range("2026-01-01", periods=n),
            "target": target if target is not None else [1.0] * n,
        }
        if s1 is not None:
            data["s1"] = s1
        return pd.DataFrame(data)

    def test_arm_a_rejects_nonempty_sentiment_cols(self):
        """arm="A" 時 sentiment_cols 必須為空——避免 A 臂偷帶情緒欄。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0], s1=[0.5])
        with self.assertRaises(ValueError):
            prepare_fold_data(
                panel, [0], feature_cols=["f1", "s1"], sentiment_cols=["s1"],
                target_col="target", arm="A")

    def test_rule_a_null_target_rows_excluded_from_fold(self):
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, 2.0, 3.0], target=[1.0, np.nan, 0.0])
        result = prepare_fold_data(
            panel, [0, 1, 2], feature_cols=["f1"], sentiment_cols=[],
            target_col="target", arm="A")

        self.assertEqual(result["n_target_null_excluded"], 1)
        self.assertEqual(len(result["X"]), 2)
        self.assertEqual(len(result["y"]), 2)
        self.assertEqual(list(result["retained_index"]), [0, 2])

    def test_rule_a_excluded_y_is_int_dtype_not_float(self):
        """known-FAIL（PO 2026-09-13 複核指出）：面板 `target` 欄因含 NaN
        而是 float dtype，規則 (a) 剔除 NULL 列後若不轉回 int，剩餘的
        `y` 仍是 float（如 `0.0`／`-1.0`）——下游 `np.unique(y)` 產生
        float 標籤，JSON 輸出的 `labels_dropped` 會印成 `0.0`，與
        `compute_per_class_metrics()` 用 `cfg["labels"]`（int）算出的
        `per_class` 鍵（`"0"`）不一致，是同一組標籤的兩種不同字面呈現。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, 2.0, 3.0, 4.0], target=[-1.0, 0.0, 1.0, np.nan])
        result = prepare_fold_data(
            panel, [0, 1, 2, 3], feature_cols=["f1"], sentiment_cols=[],
            target_col="target", arm="A")

        self.assertEqual(result["n_target_null_excluded"], 1)
        self.assertNotEqual(
            result["y"].dtype.kind, "f",
            f"y 剔除 NULL 後仍是 float dtype（{result['y'].dtype}）——"
            "應轉回 int，讓下游標籤字面呈現與 per_class 的 int 鍵一致")
        self.assertEqual(sorted(result["y"].tolist()), [-1, 0, 1])

    def test_rule_b_null_feature_rows_excluded_not_filled(self):
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, np.nan, 3.0])
        result = prepare_fold_data(
            panel, [0, 1, 2], feature_cols=["f1"], sentiment_cols=[],
            target_col="target", arm="A")

        self.assertEqual(result["n_feature_null_excluded"], 1)
        self.assertEqual(len(result["X"]), 2)
        self.assertFalse(result["X"]["f1"].isna().any(),
                          "剔除後不應殘留 NaN；且剔除不等於 fillna(0.0)——"
                          "若誤寫成 fillna，len(X) 仍會是 3 而非 2")

    def test_rule_b_known_fail_companion_fillna_would_not_reduce_row_count(self):
        """known-FAIL 對照（與上一測試斷言同一件事，len==2 已蘊含 !=3，
        不算獨立 known-FAIL 案例——PO 2026-09-12 複核指出，留著無害）。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, np.nan, 3.0])
        result = prepare_fold_data(
            panel, [0, 1, 2], feature_cols=["f1"], sentiment_cols=[],
            target_col="target", arm="A")
        self.assertNotEqual(len(result["X"]), 3)

    def test_rule_c_sentiment_nan_allowed_in_arm_b(self):
        """對照：情緒欄的 NaN 是允許的，不剔除、不計入
        `n_feature_null_excluded`。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, 2.0], s1=[np.nan, 0.5])
        result = prepare_fold_data(
            panel, [0, 1], feature_cols=["f1", "s1"], sentiment_cols=["s1"],
            target_col="target", arm="B")
        self.assertEqual(len(result["X"]), 2)
        self.assertEqual(result["n_feature_null_excluded"], 0)
        self.assertTrue(pd.isna(result["X"]["s1"].iloc[0]))

    def test_rule_c_arm_b_nonsentiment_nan_excluded_and_counted(self):
        """訂正（原名 `..._raises`）：對照臂 B 的非情緒欄（`f1`）出現 NaN
        **剔除並計數**，不是拋例外——`ValueError` 保留給剔除後仍殘留 NaN
        的防禦性斷言（結構上不應觸發）。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, np.nan], s1=[np.nan, 0.5])
        result = prepare_fold_data(
            panel, [0, 1], feature_cols=["f1", "s1"], sentiment_cols=["s1"],
            target_col="target", arm="B")
        self.assertEqual(result["n_feature_null_excluded"], 1)
        self.assertEqual(len(result["X"]), 1)
        self.assertFalse(result["X"]["f1"].isna().any())

    def test_arm_a_and_arm_b_retain_identical_row_index_sets(self):
        """D3 判準要求兩臂逐 Fold 比較同一批列——剔除後 A／B 保留的列索引
        集合必須相等。known-FAIL：若 arm B 漏掉非情緒欄的剔除（例如誤植成
        只檢查情緒欄），兩者索引集合會不同。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(
            f1=[1.0, np.nan, 3.0, 4.0], s1=[np.nan, 0.1, 0.2, np.nan])
        result_a = prepare_fold_data(
            panel, [0, 1, 2, 3], feature_cols=["f1"], sentiment_cols=[],
            target_col="target", arm="A")
        result_b = prepare_fold_data(
            panel, [0, 1, 2, 3], feature_cols=["f1", "s1"], sentiment_cols=["s1"],
            target_col="target", arm="B")
        self.assertEqual(
            set(result_a["retained_index"]), set(result_b["retained_index"]),
            "對照臂 A／B 剔除後保留的列索引集合必須相等（D3 比較同一批列）")

    def test_retained_index_and_trade_date_present(self):
        """`retained_index`／`trade_date` 供 §3.3 邊界窗/內部窗診斷把測試列
        對回日期，兩者皆須存在於回傳 dict。"""
        from src.ml.specialist_training import prepare_fold_data

        panel = self._panel(f1=[1.0, 2.0])
        result = prepare_fold_data(
            panel, [0, 1], feature_cols=["f1"], sentiment_cols=[],
            target_col="target", arm="A")
        self.assertIn("retained_index", result)
        self.assertIn("trade_date", result)
        self.assertEqual(list(result["trade_date"]), list(panel["trade_date"]))


class WalkForwardSplitterRefusesFallbackTests(unittest.TestCase):
    """`label_end_date_col` 指定欄名不存在時，SB3 呼叫端要求
    `require_label_end_date=True` 就必須拋例外，不得靜默走近似 fallback；
    但既有五個呼叫端（預設 `require_label_end_date=False`）不得受影響
    （PO 2026-09-12 複核指出：既有呼叫端與 `scripts/generate_tournament_artifact.py`
    皆依賴 fallback，直接一律拋例外會使它們全部壞掉，範圍溢出 SB3）。
    fallback 發生時 `fold_metadata` 必須誠實回報 `purge_mode`，這是本缺口
    的根因（走了 fallback 沒人知道），比拋例外本身更重要。
    """

    def _df(self, with_label_end_date=False):
        dates = pd.bdate_range("2026-01-01", periods=100)
        data = {"trade_date": dates, "f1": np.arange(100, dtype=float)}
        if with_label_end_date:
            data["label_end_date"] = dates
        return pd.DataFrame(data)

    def test_split_refuses_fallback_purge_when_required(self):
        from src.ml.time_series_split import WalkForwardSplitter

        df = self._df(with_label_end_date=False)
        splitter = WalkForwardSplitter(
            train_window_size=20, test_window_size=10, label_horizon=1,
            label_end_date_col="label_end_date_does_not_exist",
            require_label_end_date=True)

        with self.assertRaises(KeyError):
            list(splitter.split(df))

    def test_split_allows_fallback_by_default_existing_callers_unaffected(self):
        """回歸防護：`require_label_end_date` 預設 `False`，既有呼叫端
        （`test_baseline_models.py`／`test_ml_evaluator.py`／
        `test_model_trainer.py`／`test_generate_tournament_artifact.py`／
        `scripts/generate_tournament_artifact.py`）的呼叫方式不變，行為
        不受本次修復影響——本測試模擬同一種呼叫方式（缺欄、未傳新參數）。"""
        from src.ml.time_series_split import WalkForwardSplitter

        df = self._df(with_label_end_date=False)
        splitter = WalkForwardSplitter(
            train_window_size=20, test_window_size=10, label_horizon=1,
            label_end_date_col="label_end_date_does_not_exist")
        folds = list(splitter.split(df))  # 不應拋例外
        self.assertGreater(len(folds), 0)

    def test_split_still_works_when_label_end_date_col_present(self):
        """對照：欄位存在時應正常運作（回歸防護，避免修復把正常路徑也擋死）。"""
        from src.ml.time_series_split import WalkForwardSplitter

        df = self._df(with_label_end_date=True)
        splitter = WalkForwardSplitter(
            train_window_size=20, test_window_size=10,
            label_horizon=1, label_end_date_col="label_end_date")
        folds = list(splitter.split(df))
        self.assertGreater(len(folds), 0)

    def test_fold_metadata_reports_purge_mode_exact(self):
        from src.ml.time_series_split import WalkForwardSplitter

        df = self._df(with_label_end_date=True)
        splitter = WalkForwardSplitter(
            train_window_size=20, test_window_size=10,
            label_horizon=1, label_end_date_col="label_end_date")
        _, _, meta = next(splitter.split(df))
        self.assertIn("purge_mode", meta, "fold_metadata 尚未回報 purge_mode")
        self.assertEqual(meta["purge_mode"], "exact")

    def test_fold_metadata_reports_purge_mode_approximate(self):
        from src.ml.time_series_split import WalkForwardSplitter

        df = self._df(with_label_end_date=False)
        splitter = WalkForwardSplitter(
            train_window_size=20, test_window_size=10, label_horizon=1,
            label_end_date_col="label_end_date_does_not_exist")
        _, _, meta = next(splitter.split(df))
        self.assertIn("purge_mode", meta, "fold_metadata 尚未回報 purge_mode")
        self.assertEqual(meta["purge_mode"], "approximate")


class PanelDatasetLabelEndDateTests(unittest.TestCase):
    """`build_panel_dataset()` 尚未輸出 `label_end_date`（T+1）——附帶條件
    要求 1 的直接測試，比照同一紅測流程送審（PO 未在本輪明列，屬其明確
    要求的自然延伸，一併請確認 RED）。"""

    def test_panel_dataset_produces_label_end_date(self):
        from src.ml.panel_dataset import build_panel_dataset

        df_universe = pd.DataFrame({
            "effective_date": ["2026-01-01"], "stock_id": ["AAA"], "included": [True],
        })
        df_features = pd.DataFrame({
            "stock_id": ["AAA", "AAA"],
            "trade_date": ["2026-01-02", "2026-01-05"],
            "target_up_down": [1, 0],
            "target_triple_barrier": [1, 0],
        })
        df_prices = pd.DataFrame({
            "stock_id": ["AAA", "AAA", "AAA"],
            "trade_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
        })

        panel = build_panel_dataset(
            df_universe, df_features, df_prices,
            target_column="target_up_down", holding_period=1)

        self.assertIn("label_end_date", panel.columns,
                       "build_panel_dataset() 尚未輸出 label_end_date（T+1）")
        row0 = panel.loc[panel["trade_date"] == pd.Timestamp("2026-01-02")].iloc[0]
        self.assertEqual(row0["label_end_date"], pd.Timestamp("2026-01-05"),
                          "label_end_date 應為該股票在 df_stock_prices 序列中"
                          "下一個交易日（T+1），計算基準為價格表而非面板自身")

    def test_label_end_date_and_label_end_date_tb_are_distinct(self):
        """回歸防護（訂正——PO 2026-09-12 複核第三輪，M6 突變抓到的測試盲點）：
        新增 `label_end_date` 不得改變既有 `label_end_date_tb` 的值，**且兩欄
        本身必須不同**。

        **`holding_period` 必須 ≠ 1 才有鑑別力**：本測試原用
        `holding_period=1`（見上一個測試方法），此時 T+1（`label_end_date`）
        與 T+`holding_period`（`label_end_date_tb`）恰好相同——若實作把
        `label_end_date` 誤寫成 `shift(-holding_period)`（與 `label_end_date_tb`
        同一個位移量，而非固定 `shift(-1)`），這條測試在 `holding_period=1`
        下**結構上分不出來**（`CLAUDE.md` §9A.1）。本測試改用
        `holding_period=3`，`label_end_date`（T+1=2026-01-05）與
        `label_end_date_tb`（T+3=2026-01-07）為不同值，才具鑑別力。
        """
        from src.ml.panel_dataset import build_panel_dataset

        df_universe = pd.DataFrame({
            "effective_date": ["2026-01-01"], "stock_id": ["AAA"], "included": [True],
        })
        df_features = pd.DataFrame({
            "stock_id": ["AAA"], "trade_date": ["2026-01-02"],
            "target_up_down": [1], "target_triple_barrier": [1],
        })
        df_prices = pd.DataFrame({
            "stock_id": ["AAA"] * 4,
            "trade_date": ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"],
        })
        panel = build_panel_dataset(
            df_universe, df_features, df_prices,
            target_column="target_up_down", holding_period=3)
        row0 = panel.iloc[0]
        self.assertEqual(row0["label_end_date"], pd.Timestamp("2026-01-05"),
                          "label_end_date 應為 T+1（下一個交易日），"
                          "與 holding_period 無關")
        self.assertEqual(row0["label_end_date_tb"], pd.Timestamp("2026-01-07"),
                          "label_end_date_tb 應為 T+holding_period（此處 T+3）")
        self.assertNotEqual(
            row0["label_end_date"], row0["label_end_date_tb"],
            "holding_period=3 時兩欄必須不同——若相同，代表 label_end_date "
            "被誤植為 shift(-holding_period) 而非固定 shift(-1)")


class MultiModalTrainerNanFailFastTests(unittest.TestCase):
    """`MultiModalTrainer.train_and_predict_fold()` 對不支援 NaN 的模型
    fail-fast（`UG-G3-SB3`，PO 2026-09-12 裁決，回應 Gate 2 tournament
    `LR × MultiModal` 組在真實面板上會撞見 sklearn 原生、不含脈絡的
    `ValueError: Input X contains NaN.` 這件事）。"""

    def _make_df(self, n=6):
        from src.ml.model_trainer import ALL_MULTIMODAL_FEATURE_COLS

        data = {c: np.linspace(1.0, 2.0, n) for c in ALL_MULTIMODAL_FEATURE_COLS}
        data["sentiment_mean"] = [np.nan] * n  # 模擬真實面板：情緒欄含 NaN
        data["target_up_down"] = [0, 1] * (n // 2)
        return pd.DataFrame(data)

    def test_rejects_nan_for_nan_intolerant_model(self):
        """**注意**：`LogisticRegression` 本身遇到 NaN 也會拋 sklearn 原生的
        `ValueError`（"Input X contains NaN"）——單純斷言 `assertRaises(ValueError)`
        分不出「我們的 fail-fast」與「sklearn 自己的錯誤」，兩者都會讓
        `assertRaises(ValueError)` 通過，即使把 fail-fast 檢查整個拿掉也一樣
        （已實測確認：清空 `NAN_INTOLERANT_MODELS` 後本測試若只斷言
        `ValueError` 類型仍會 `ok`，需改斷言訊息內容才有鑑別力）。因此改用
        `assertRaisesRegex` 鎖定我們自訂訊息的關鍵字，兩者才分得開。"""
        from src.ml.model_trainer import MultiModalTrainer

        df = self._make_df()
        trainer = MultiModalTrainer(model_name="logistic_regression")
        with self.assertRaisesRegex(ValueError, "不支援 NaN 特徵輸入"):
            trainer.train_and_predict_fold(df, df, target_col="target_up_down")

    def test_accepts_nan_for_tree_models(self):
        """對照：RF／LightGBM／XGBoost 原生支援 NaN，不應被 fail-fast 擋下。"""
        from src.ml.model_trainer import MultiModalTrainer

        df = self._make_df()
        for model_name in ("random_forest", "lightgbm", "xgboost"):
            with self.subTest(model_name=model_name):
                trainer = MultiModalTrainer(model_name=model_name)
                result = trainer.train_and_predict_fold(
                    df, df, target_col="target_up_down")
                self.assertEqual(len(result["y_pred"]), len(df))


# ==============================================================================
# 訓練迴圈本體與邊界窗/內部窗洩漏診斷——紅測（PO 2026-09-12 第三輪指定）
# ==============================================================================
# 涵蓋：(1) Fold 迴圈對 A/B 兩臂使用 prepare_fold_data 且保留列相等；
# (2) LR 只出現在 A 臂；(3) per-class 指標輸出形狀；(4) 邊界窗＝測試窗前
# H 個「交易日」（不是列——面板是跨股票 long-format，同一天多列）；
# (5) 合成滲漏 Fold 必被診斷函式標示。以下函式皆尚不存在，ImportError
# 即為 RED。

class RunFoldForArmsTests(unittest.TestCase):
    """`run_fold_for_arms()`：一個 Fold 對 A/B 兩臂各呼叫一次
    `prepare_fold_data()`，保留列索引集合須相等（跨臂一致性防禦，不只是
    `prepare_fold_data()` 自己的既有測試——這裡驗證迴圈本體真的有做這個
    交叉檢查，而不是各自呼叫、沒人比對）。"""

    def _panel(self):
        from src.ml.baseline_models import ARM_B_FEATURE_COLS
        n = 6
        data = {c: np.linspace(0.0, 1.0, n) for c in ARM_B_FEATURE_COLS}
        data["trade_date"] = pd.date_range("2026-01-01", periods=n)
        data["target"] = [0, 1, 0, 1, 0, 1]
        df = pd.DataFrame(data)
        df.loc[2, "amplitude_ratio"] = np.nan  # 非情緒欄 NaN，兩臂應剔除同一列
        return df

    def test_retained_indices_equal_across_arms(self):
        from src.ml.specialist_training import run_fold_for_arms
        from src.ml.baseline_models import ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS

        panel = self._panel()
        result = run_fold_for_arms(
            panel, list(range(0, 4)), list(range(4, 6)),
            ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS)
        self.assertEqual(
            set(result["A"]["train"]["retained_index"]),
            set(result["B"]["train"]["retained_index"]))
        self.assertEqual(
            set(result["A"]["test"]["retained_index"]),
            set(result["B"]["test"]["retained_index"]))

    def test_raises_on_retained_index_mismatch(self):
        """known-FAIL：用 mock 讓 A／B 臂回傳刻意不同的 retained_index，
        確認 `run_fold_for_arms()` 的交叉檢查真的會抓到（不是形式上存在但
        沒有實際比對）。"""
        from unittest.mock import patch
        from src.ml.baseline_models import ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS

        panel = self._panel()

        def fake_prepare(panel_, indices, feature_cols, sentiment_cols, target_col, arm, **kwargs):
            # 刻意讓 arm A 少保留一列，與 arm B 製造不一致——**不能**用
            # 「B 多加一個已存在的索引」，那會被 set() 去重抵消掉，反而
            # 測不出不一致（已實測撞過這個坑：兩臂經 set() 後其實相同）。
            idx = list(indices)
            if arm == "A" and len(idx) > 1:
                idx = idx[:-1]
            base = {
                "X": panel_.iloc[idx][feature_cols],
                "y": panel_.iloc[idx][target_col],
                "trade_date": panel_.iloc[idx]["trade_date"].to_numpy(),
                "n_target_null_excluded": 0,
                "n_feature_null_excluded": 0,
                "retained_index": np.array(idx),
            }
            return base

        with patch("src.ml.specialist_training.prepare_fold_data", side_effect=fake_prepare):
            from src.ml.specialist_training import run_fold_for_arms
            with self.assertRaises(ValueError):
                run_fold_for_arms(
                    panel, [0, 1, 2, 3], [4, 5],
                    ARM_A_FEATURE_COLS, ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS)


class ModelArmPairingTests(unittest.TestCase):
    """`iter_model_arm_pairs()`：LogisticRegression 只配對照臂 A；
    RF／LightGBM／XGBoost 兩臂皆配（Gate 3 §5 設計，直接重用既有
    `NAN_INTOLERANT_MODELS` 常數判斷，不重複硬寫模型名稱清單）。"""

    def test_lr_only_pairs_with_arm_a(self):
        from src.ml.specialist_training import iter_model_arm_pairs

        pairs = list(iter_model_arm_pairs())
        lr_arms = {arm for model, arm in pairs if model == "logistic_regression"}
        self.assertEqual(lr_arms, {"A"},
                          "LogisticRegression 不得出現在對照臂 B")

    def test_tree_models_pair_with_both_arms(self):
        from src.ml.specialist_training import iter_model_arm_pairs

        pairs = list(iter_model_arm_pairs())
        for model in ("random_forest", "lightgbm", "xgboost"):
            arms = {arm for m, arm in pairs if m == model}
            self.assertEqual(arms, {"A", "B"}, f"{model} 應兩臂皆配")


class PerClassMetricsTests(unittest.TestCase):
    """`compute_per_class_metrics()` 輸出形狀：逐類別 precision/recall/f1/
    support，另附 macro_f1。"""

    def test_output_shape(self):
        from src.ml.specialist_training import compute_per_class_metrics

        y_true = [0, 1, 1, 0, 1]
        y_pred = [0, 1, 0, 0, 1]
        result = compute_per_class_metrics(y_true, y_pred)
        for label in ("0", "1"):
            self.assertIn(label, result)
            for key in ("precision", "recall", "f1", "support"):
                self.assertIn(key, result[label])
        self.assertIn("macro_f1", result)


class BoundaryInteriorDiagnosisTests(unittest.TestCase):
    """`compute_boundary_interior_metrics()`：邊界窗＝測試窗前 H 個**交易日**
    （面板是跨股票 long-format，同一天多檔股票、多列——不是前 H 列）。"""

    def test_boundary_uses_trading_days_not_row_count(self):
        from src.ml.specialist_training import compute_boundary_interior_metrics

        # 3 個交易日，每天 4 檔股票＝12 列；holding_period=1（H=1 天）。
        # 若誤用「前 holding_period 列」，邊界窗會只切到第 1 天的第 1 列
        # （n=1），而不是整個第 1 天（n=4）。
        dates = ["2026-01-01"] * 4 + ["2026-01-02"] * 4 + ["2026-01-05"] * 4
        y_true = [0, 1, 0, 1] * 3
        y_pred = [0, 1, 0, 1] * 3
        result = compute_boundary_interior_metrics(dates, y_true, y_pred, holding_period=1)
        self.assertEqual(
            result["boundary"]["n"], 4,
            "邊界窗應為整個第一個交易日的 4 列，不是前 1 列")
        self.assertEqual(result["interior"]["n"], 8)

    def test_synthetic_leak_fold_flagged_by_diagnosis(self):
        """known-FAIL 案例本身：合成邊界窗（前 2 天）被『洩漏』（完美預測）、
        內部窗（後 2 天）預測全錯的情境，確認診斷函式回報邊界 macro_f1
        明顯高於內部 macro_f1（滲漏症狀的判準）。"""
        from src.ml.specialist_training import compute_boundary_interior_metrics

        dates = (["2026-01-01"] * 4 + ["2026-01-02"] * 4
                 + ["2026-01-05"] * 4 + ["2026-01-06"] * 4)
        y_true = [0, 1, 0, 1] * 4
        y_pred = [0, 1, 0, 1] * 2 + [1, 0, 1, 0] * 2  # 邊界完美、內部全錯
        result = compute_boundary_interior_metrics(dates, y_true, y_pred, holding_period=2)
        self.assertGreater(
            result["boundary"]["macro_f1"], result["interior"]["macro_f1"],
            "合成滲漏情境下，邊界窗表現必須明顯優於內部窗——這是滲漏症狀"
            "的判準，診斷函式必須能反映這個落差")


class SummarizeLeakageDiagnosisTests(unittest.TestCase):
    """`summarize_leakage_diagnosis()`：跨 43 Fold 彙總「邊界窗是否系統性
    偏離內部窗」（提案 §3.3 判準），不能只靠人眼看單一 Fold 的數字。判準
    為工程判斷（Δ>0 的 Fold 比例 ≥ 0.70 且 Δ 中位數 ≥ 0.05 才 flag），
    非統計檢定——`summarize_leakage_diagnosis()` 尚不存在，ImportError
    即為 RED。"""

    def _fold_result(self, delta, interior_f1=0.5):
        """建構一個合成 Fold 的 delta 專用欄位，boundary_macro_f1_for_delta
        = interior_f1 + delta（PO 2026-09-12 複核訂正：Δ 改走
        `*_macro_f1_for_delta`，不是兩側各自 `macro_f1`——見
        `compute_boundary_interior_metrics()` docstring）。"""
        return {
            "boundary_macro_f1_for_delta": interior_f1 + delta,
            "interior_macro_f1_for_delta": interior_f1,
        }

    def test_all_positive_delta_flags_true(self):
        from src.ml.specialist_training import summarize_leakage_diagnosis

        results = [self._fold_result(0.10) for _ in range(43)]
        summary = summarize_leakage_diagnosis(results)
        self.assertEqual(summary["n_folds"], 43)
        self.assertAlmostEqual(summary["median_delta"], 0.10)
        self.assertEqual(summary["frac_positive"], 1.0)
        self.assertTrue(summary["flagged"])

    def test_all_positive_but_tiny_delta_does_not_flag(self):
        """比例門檻與中位數門檻是 AND，缺一不可——本測試專門釘住中位數
        門檻：全部 43 Fold 皆為正（比例門檻過關），但 Δ 只有 +0.01（< 0.05
        中位數門檻），不應 flag。known-FAIL：若實作把中位數門檻拿掉、只看
        比例，這條測試會被誤判為 flagged=True。"""
        from src.ml.specialist_training import summarize_leakage_diagnosis

        results = [self._fold_result(0.01) for _ in range(43)]
        summary = summarize_leakage_diagnosis(results)
        self.assertEqual(summary["frac_positive"], 1.0)
        self.assertAlmostEqual(summary["median_delta"], 0.01)
        self.assertFalse(
            summary["flagged"],
            "比例門檻過關但 Δ 中位數只有 0.01（< 0.05 門檻），不應 flag——"
            "若這裡是 True，代表中位數門檻沒有生效")

    def test_mixed_sign_delta_flags_false(self):
        """43 個 Fold，Δ 為 ±0.05 隨機正負各半（固定 seed）——約半數 Fold
        為正，未達 0.70 比例門檻，不應 flag。"""
        from src.ml.specialist_training import summarize_leakage_diagnosis

        rng = np.random.RandomState(42)
        signs = rng.choice([0.05, -0.05], size=43)
        results = [self._fold_result(float(d)) for d in signs]
        summary = summarize_leakage_diagnosis(results)
        self.assertEqual(summary["n_folds"], 43)
        self.assertFalse(summary["flagged"])

    def test_known_fail_naive_any_fold_positive_criterion_would_differ(self):
        """known-FAIL 對照：若判準退化成『任一 Fold Δ>0 就 flag』這種天真
        規則，上一個測試的資料（約半數 Fold 為正）會被誤判為 True——本
        測試證明正確判準與天真判準在這組資料上必須得到不同結論，藉此
        釘住「不是任一 Fold 就 flag」這件事。"""
        from src.ml.specialist_training import summarize_leakage_diagnosis

        rng = np.random.RandomState(42)
        signs = rng.choice([0.05, -0.05], size=43)
        results = [self._fold_result(float(d)) for d in signs]

        naive_flagged = any(d > 0 for d in signs)
        self.assertTrue(
            naive_flagged,
            "本測試的前提是這組隨機資料裡至少有一個 Fold 為正——"
            "若這裡是 False，測試本身設計有誤，需重新固定 seed 或資料")

        summary = summarize_leakage_diagnosis(results)
        self.assertNotEqual(
            summary["flagged"], naive_flagged,
            "正確判準（比例+中位數雙門檻）與天真的『任一 Fold』判準，"
            "必須在這組資料上得到不同結論——否則判準退化成天真規則也偵測不到")


# ==============================================================================
# 邊界窗/內部窗類別集合交集修復——紅測（PO 2026-09-12 複核指出的可比性缺陷）
# ==============================================================================
# compute_boundary_interior_metrics() 對兩窗各自呼叫 compute_per_class_metrics()
# 時，labels=None 會取「該子集自己的」y_true∪y_pred 類別。若邊界窗剛好缺席
# 某一類（Timeout 小樣本時常見），邊界窗與內部窗的 macro F1 是不同類別數的
# 平均，Δ 混進類別組成差異，會產生假滲漏訊號。修復要求：Δ 只在兩窗 y_true
# 皆有支持（support>0）的類別交集上算，另揭露 labels_used_for_delta／
# labels_dropped；compute_boundary_interior_metrics() 現行版本沒有這些欄位，
# 修復前必 FAIL（KeyError）。

class BoundaryInteriorLabelIntersectionTests(unittest.TestCase):
    """`compute_boundary_interior_metrics()` 的 Δ 計算必須限定在兩窗
    `y_true` 皆有支持的類別交集上，避免類別組成差異被誤判為滲漏訊號。"""

    def test_label_set_mismatch_produces_false_delta_without_intersection_fix(self):
        """known-FAIL（修復前 KeyError；即使補上欄位但未做交集限定，
        Δ 仍會是假訊號）：邊界窗只有 class 1（完美預測），內部窗多了
        class 0（品質差、拉低內部整體 macro F1）——class 1 本身在兩窗
        品質相同，正確判準應給 Δ≈0；只用各窗自己的類別集合算 macro F1
        會把類別組成差異算成假滲漏訊號。"""
        from src.ml.specialist_training import compute_boundary_interior_metrics

        # 邊界窗：1 個交易日、4 列，全部 true=1、預測全對。
        boundary_dates = ["2026-01-01"] * 4
        boundary_true = [1, 1, 1, 1]
        boundary_pred = [1, 1, 1, 1]

        # 內部窗：第二天、8 列——4 列 true=1 全對（與邊界窗同品質，且
        # class 0／2 的誤判都彼此混淆、不會誤判成 1，故不污染 class 1
        # 的 precision/recall）；4 列 true∈{0,2}、各一半誤判成對方
        # （拉低內部窗整體 macro F1，但與 class 1 無關）。
        interior_dates = ["2026-01-02"] * 8
        interior_true = [1, 1, 1, 1, 0, 0, 2, 2]
        interior_pred = [1, 1, 1, 1, 0, 2, 2, 0]

        dates = boundary_dates + interior_dates
        y_true = boundary_true + interior_true
        y_pred = boundary_pred + interior_pred

        result = compute_boundary_interior_metrics(dates, y_true, y_pred, holding_period=1)

        # 兩窗共同類別交集只有 {1}——class 0／2 只出現在內部窗的 true 標籤。
        self.assertEqual(result["labels_used_for_delta"], [1])
        self.assertEqual(result["labels_dropped"], {"boundary": [], "interior": [0, 2]})

        # 限定在交集 {1} 上算：兩側品質相同（皆為完美預測），Δ 必須為 0。
        self.assertAlmostEqual(result["boundary_macro_f1_for_delta"], 1.0)
        self.assertAlmostEqual(result["interior_macro_f1_for_delta"], 1.0)

        # 對照：若誤用兩側各自完整類別集合的 macro_f1（修復前的做法），
        # 內部窗因多出 class 0/2 的混淆會被拉低，與邊界窗（僅 class 1、
        # 必為 1.0）之間出現假 Δ——這就是本測試要擋下的假訊號來源。
        self.assertLess(
            result["interior"]["macro_f1"], 1.0,
            "內部窗自己完整類別集合的 macro_f1 應被 class 0/2 混淆拉低"
            "（本測試的前提），否則無法示範『類別組成差異被誤判為 Δ』")

    def test_full_label_agreement_unaffected(self):
        """對照案例：兩窗類別齊全時，交集限定後的 delta 專用欄位須與
        各窗自己完整類別集合算出的 macro_f1 相同——確認修復不影響類別
        齊全的正常情況。"""
        from src.ml.specialist_training import compute_boundary_interior_metrics

        dates = ["2026-01-01"] * 4 + ["2026-01-02"] * 4
        y_true = [0, 1, 0, 1] * 2
        y_pred = [0, 1, 0, 1, 0, 1, 1, 0]  # 內部窗兩列預測錯誤
        result = compute_boundary_interior_metrics(dates, y_true, y_pred, holding_period=1)

        self.assertEqual(result["labels_used_for_delta"], [0, 1])
        self.assertEqual(result["labels_dropped"], {"boundary": [], "interior": []})
        self.assertAlmostEqual(
            result["boundary_macro_f1_for_delta"], result["boundary"]["macro_f1"])
        self.assertAlmostEqual(
            result["interior_macro_f1_for_delta"], result["interior"]["macro_f1"])


# ==============================================================================
# fit_predict_specialist_fold()——紅測（PO 2026-09-13 核准介面＋兩項必修）
# ==============================================================================
# `src/ml/specialist_training.py` 尚無「實際 fit/predict 一個 Fold」的函式
# （模組 docstring 原本就寫「訓練迴圈完整入口排在後續 commit」）。本函式尚
# 不存在，ImportError 即為 RED。兩項必修（PO 用真實工廠模型於容器內實測
# 驗證過）：
# 1. 標籤須經 LabelEncoder 編碼——XGBClassifier 對 Triple-Barrier 原始
#    {-1,0,1} 標籤直接拋 ValueError（已複現：
#    "Invalid classes inferred from unique values of `y`.
#     Expected: [0 1 2], got [-1  0  1]"）。
# 2. 特徵須經 create_scaler("robust") 做 train-only fit 縮放——未縮放的
#    LR 在真實形狀資料（多特徵、一欄尺度放大、標籤弱相依）上會撞滿
#    max_iter=500 且發 ConvergenceWarning（PO 提供可重現配方，已複核：
#    unscaled n_iter_=[500] 有警告；scaled n_iter_=[14] 無警告）。

class FitPredictSpecialistFoldTests(unittest.TestCase):
    """`fit_predict_specialist_fold()`：對 `prepare_fold_data()` 輸出實際
    fit/predict，統一走 LabelEncoder 編碼＋RobustScaler train-only 縮放。"""

    def _prepared(self, X_df, y_series, dates):
        return {
            "X": X_df,
            "y": y_series,
            "trade_date": np.asarray(dates),
            "retained_index": np.arange(len(y_series)),
            "n_target_null_excluded": 0,
            "n_feature_null_excluded": 0,
        }

    def test_basic_fit_predict_shape_and_class_domain(self):
        """基本 fit/predict：輸出長度與 test 相同，預測值域落在訓練類別內，
        `scaler_type` 揭露為 `"robust"`。"""
        from src.ml.specialist_training import fit_predict_specialist_fold

        rng = np.random.RandomState(42)
        n_train, n_test = 30, 10
        X_train = pd.DataFrame({"f1": rng.normal(size=n_train), "f2": rng.normal(size=n_train)})
        y_train = pd.Series(rng.choice([0, 1], size=n_train))
        X_test = pd.DataFrame({"f1": rng.normal(size=n_test), "f2": rng.normal(size=n_test)})
        y_test = pd.Series(rng.choice([0, 1], size=n_test))

        train_prepared = self._prepared(X_train, y_train, pd.date_range("2026-01-01", periods=n_train))
        test_prepared = self._prepared(X_test, y_test, pd.date_range("2026-03-01", periods=n_test))

        result = fit_predict_specialist_fold("random_forest", train_prepared, test_prepared)

        self.assertEqual(len(result["y_pred"]), n_test)
        self.assertTrue(set(result["y_pred"].tolist()) <= set(result["train_classes"]))
        self.assertEqual(result["scaler_type"], "robust")
        self.assertEqual(result["n_train"], n_train)
        self.assertEqual(result["n_test"], n_test)

    def test_triple_barrier_labels_supported_by_all_models(self):
        """known-FAIL（修復前對 xgboost）：{-1,0,1} 標籤若不經 LabelEncoder，
        `XGBClassifier.fit()` 對此標籤空間直接拋 ValueError（已於容器內
        用真實工廠模型複現）。四模型統一走同一條編碼路徑後皆應能
        fit/predict，且預測值域落在訓練類別 {-1,0,1} 內。"""
        from src.ml.specialist_training import fit_predict_specialist_fold, MODEL_NAMES

        rng = np.random.RandomState(7)
        n_per_class = 12
        labels = [-1, 0, 1]
        y_train_arr = np.repeat(labels, n_per_class)
        n_train = len(y_train_arr)
        X_train = pd.DataFrame({
            "f1": y_train_arr * 2.0 + rng.normal(scale=0.1, size=n_train),
            "f2": rng.normal(size=n_train),
        })
        y_test_arr = np.array(labels * 3)
        n_test = len(y_test_arr)
        X_test = pd.DataFrame({
            "f1": y_test_arr * 2.0 + rng.normal(scale=0.1, size=n_test),
            "f2": rng.normal(size=n_test),
        })

        train_prepared = self._prepared(X_train, pd.Series(y_train_arr), pd.date_range("2026-01-01", periods=n_train))
        test_prepared = self._prepared(X_test, pd.Series(y_test_arr), pd.date_range("2026-03-01", periods=n_test))

        for model_name in MODEL_NAMES:
            with self.subTest(model=model_name):
                result = fit_predict_specialist_fold(model_name, train_prepared, test_prepared)
                self.assertEqual(len(result["y_pred"]), n_test)
                self.assertTrue(
                    set(result["y_pred"].tolist()) <= set(labels),
                    f"{model_name} 的預測值域必須落在訓練類別 {labels} 內")
                self.assertEqual(sorted(result["train_classes"]), labels)

    def test_lr_scaling_prevents_max_iter_convergence_failure(self):
        """known-FAIL（修復前）：未縮放時 LR 在此資料上撞滿 max_iter=500
        且發 ConvergenceWarning（PO 2026-09-13 提供可重現配方，容器內
        複核：unscaled n_iter_=[500] 有警告；scaled n_iter_=[14] 無警告）。
        資料：8 特徵、300 列、其中一欄尺度放大 1e4、三類且與特徵僅弱
        相依（噪音標籤）——不斷言預測類別數（未縮放也會預測多類，
        真正的症狀只有撞滿 max_iter／收斂警告）。"""
        import warnings

        from sklearn.exceptions import ConvergenceWarning

        from src.ml.specialist_training import fit_predict_specialist_fold

        rng = np.random.default_rng(0)
        n = 300
        X = rng.normal(size=(n, 8))
        X[:, 0] *= 1e4
        y = rng.choice([-1, 0, 1], size=n, p=[0.55, 0.05, 0.40])

        n_train = 250
        col_names = [f"f{i}" for i in range(8)]
        X_train = pd.DataFrame(X[:n_train], columns=col_names)
        y_train = pd.Series(y[:n_train])
        X_test = pd.DataFrame(X[n_train:], columns=col_names)
        y_test = pd.Series(y[n_train:])

        train_prepared = self._prepared(X_train, y_train, pd.date_range("2026-01-01", periods=n_train))
        test_prepared = self._prepared(X_test, y_test, pd.date_range("2027-01-01", periods=n - n_train))

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = fit_predict_specialist_fold("logistic_regression", train_prepared, test_prepared)
            conv_warnings = [x for x in w if issubclass(x.category, ConvergenceWarning)]

        self.assertLess(
            result["n_iter_"], 500,
            "縮放後 LR 應在 max_iter=500 之前收斂——PO 2026-09-13 實測配方："
            "8 特徵、其中一欄尺度放大 1e4、與特徵無關的三類雜訊標籤")
        self.assertEqual(len(conv_warnings), 0, "縮放後不應出現 ConvergenceWarning")

    def test_scaler_fit_only_on_train_not_test(self):
        """結構紅測：`create_scaler()` 回傳的縮放器只能在訓練集上 `fit`
        一次，`transform(X_test)` 的輸出必須等於「用訓練集中位數／IQR
        轉換」的結果——不是用 test 自己的統計量、也不是合併統計量。
        train／test 刻意用明顯不同的中位數與離散度，若實作誤用了 test
        或合併統計量，轉換結果會偏離手動重算值。"""
        from unittest.mock import patch

        from sklearn.preprocessing import RobustScaler

        from src.ml.specialist_training import fit_predict_specialist_fold

        class _SpyRobustScaler:
            def __init__(self):
                self._inner = RobustScaler()
                self.fit_inputs = []
                self.transform_outputs = []

            def fit(self, X):
                self.fit_inputs.append(np.asarray(X).copy())
                self._inner.fit(X)
                return self

            def transform(self, X):
                out = self._inner.transform(X)
                self.transform_outputs.append(out.copy())
                return out

            def fit_transform(self, X):
                return self.fit(X).transform(X)

        rng = np.random.RandomState(11)
        n_train, n_test = 30, 10
        X_train = pd.DataFrame({
            "f1": rng.normal(loc=0.0, scale=1.0, size=n_train),
            "f2": rng.normal(loc=0.0, scale=1.0, size=n_train),
        })
        X_test = pd.DataFrame({
            "f1": rng.normal(loc=50.0, scale=5.0, size=n_test),
            "f2": rng.normal(loc=-30.0, scale=2.0, size=n_test),
        })
        y_train = pd.Series(rng.choice([0, 1], size=n_train))
        y_test = pd.Series(rng.choice([0, 1], size=n_test))

        train_prepared = self._prepared(X_train, y_train, pd.date_range("2026-01-01", periods=n_train))
        test_prepared = self._prepared(X_test, y_test, pd.date_range("2026-03-01", periods=n_test))

        spy = _SpyRobustScaler()
        with patch("src.ml.specialist_training.create_scaler", return_value=spy):
            fit_predict_specialist_fold("logistic_regression", train_prepared, test_prepared)

        self.assertEqual(len(spy.fit_inputs), 1, "scaler 只能 fit 一次（僅訓練集）")
        np.testing.assert_allclose(spy.fit_inputs[0], X_train.to_numpy())

        median_train = np.median(X_train.to_numpy(), axis=0)
        q75 = np.percentile(X_train.to_numpy(), 75, axis=0)
        q25 = np.percentile(X_train.to_numpy(), 25, axis=0)
        iqr = q75 - q25
        expected_test_scaled = (X_test.to_numpy() - median_train) / iqr

        np.testing.assert_allclose(spy.transform_outputs[-1], expected_test_scaled, rtol=1e-6)


if __name__ == "__main__":
    unittest.main()
