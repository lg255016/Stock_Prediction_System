# -*- coding: utf-8 -*-
"""`UG-G3-SB4` 紅測（RED）——PO 2026-09-14 核准進入實作前指定的紅測清單。

依已核准的 Gate A 提案（`doc/upgrade/gates/UG_G3_SB4_GATE_A_PROPOSAL.md`
`be64f9b` §4、§6、§13）與 PO 對紅測清單的複核意見（14 項），本檔涵蓋：

  T1  `build_meta_learner_input()` 只接受 OOF 欄 ∪ `META_REGIME_FEATURE_COLS`
  T2  OOF 矩陣結構性排除 Arm B（不留「記錄警告」選項）
  T3  二階 Purge：`label_end_date`／`label_end_date_tb` 各自參數化測試，
      含「晚於」與「等於」兩種邊界
  T4  `assemble_oof_matrix()` 的輸出形狀與宣告的 4 組 (model, arm) 不符即拒絕
  T5  缺席類別的 `predict_proba` 對齊——`proba_classes` 反映真實缺席
  T6  Holdout 守衛：`trade_date >= 2025-10-23`（含端點）拒絕
  T7  `select_best_specialist()` 只接受 `split_segment == "meta_train"` 的資料
  T8  排序指標為模組層級常數，介面不接受 `metric=` 覆寫
  T9  `split_segment` 完整性：列不消失，值域只有三者
  T10 `return_proba` 參數——既有呼叫端（`return_proba=False`）零改動
  T11 （新增，PO 複核追加）NaN 機率／regime 欄位列在 `build_meta_learner_input()`
      被排除並計數，不插補、不填 0
  T12 （新增）機率欄對齊：`predict_proba` 輸出形狀、逐列和為 1、
      `argmax` 與 `y_pred` 一致
  T13 （新增）Holdout 折的 Specialist 從未被迭代到（不是 fit 了不用）
  T14 （新增）`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 常數值釘住

**介面訂正（PO 第二輪複核，紅測清單階段）**：
  - `select_best_specialist(meta_train_df)` 不接受 `metric=` 關鍵字參數
    （原清單草稿寫成 `metric=SELECTION_METRIC` 與 T8「不可覆寫」自相矛盾，
    已訂正）；回傳 `(best_model_name, ranking_df)`，`ranking_df` 為四個
    Specialist 依 `SELECTION_METRIC` 遞減排序的完整排名（§3.4 要求揭露
    完整排名，不只第一名）。
  - `stacking.py` 定義三個專屬例外類別（`MetaInputContractError`／
    `HoldoutViolation`／`SelectionSourceError`），T1／T2／T4／T6／T7 斷言
    專屬型別，不用泛用的 `ValueError`／`Exception`——理由同 SB3 紅測的
    既有教訓（`MultiModalTrainerNanFailFastTests` 已示範：單純斷言
    `ValueError` 分不出是我方守衛擋的還是底層函式庫自己丟的）。
  - T3 的「對照真實凍結面板 150／750」迴歸基準**不放在本檔**——會依賴
    `/tmp/sb3_panels/` 或 `D:\\` 路徑下的 parquet，違反 `CLAUDE.md` §13.4
    測試封閉性。該項迴歸改為 OOF 產生腳本自身的證據 JSON 守衛（實作階段
    於腳本內比對常數，不符即 abort），不在單元測試裡對外部檔案系統路徑
    做斷言。

================================================================================
第三輪複核追加（PO 2026-09-14，比照 SB3 `6dcbdc7` 的盲點修補模式）
================================================================================
審查方指出：`SecondStagePurgeTests` 原本 8 條測試的輸入全是純
`split_segment == "meta_train"`，**沒有任何測試混入真正的 `meta_eval` 列**。
而 `meta_eval` 列的 `trade_date`／`label_end_date` 依定義必然晚於或等於
`META_EVAL_START_DATE`（它們就是從那天起算的）——一個不檢查 `split_segment`、
對全部列無差別套用日期規則的實作，會把整個 Meta-Eval 段（真實面板上
17,960 列）誤標為 `purged`，而原本 8 條測試會**全數通過**，抓不到這個
盲點（`CLAUDE.md` §9A.1：結構上不可能失敗的檢查不是檢查）。

補三類測試：

  1. `SecondStagePurgeTests.test_purge_rule_only_applies_to_meta_train_rows`
     ——輸入同時含 `meta_train`／`meta_eval`／已是 `purged` 的列，驗證
     規則只轉換符合條件的 `meta_train` 列，`meta_eval` 與既有 `purged`
     列維持不變。
  2. `MetaLearnerTrainingSegmentTests`（新類別）——Meta-Learner 訓練矩陣
     的產生路徑（`build_meta_learner_input(df, segment="meta_train")`）
     只能消費 `meta_train` 列，`meta_eval`／`purged` 列須被排除且排除數
     可查核（`exclusion_counts["segment_mismatch"]`）。known-FAIL：若
     實作把 `purged` 列也算進訓練，輸出列數會多出來，斷言的精確列數
     會抓到。
  3. `ExceptionHierarchyTests`（**本檔原始 14 項之外，額外新增**——回應
     PO 對紅測清單三個問題的回答第 1 點：三個專屬例外類別不得互相繼承，
     否則 T6 的 `assertRaises(HoldoutViolation)` 可能被一個實際上分類
     錯誤的例外滿足，測試因此失去分辨能力。此項未計入 PO 授權的「兩條
     測試」範圍，屬 PM 主動補上的低成本結構性檢查，一併揭露）。

本檔**純為 RED 證據**——`src/ml/stacking.py` 尚不存在，`META_REGIME_FEATURE_COLS`
與 `fit_predict_specialist_fold(..., return_proba=)` 尚未新增，實作完成前
以下全部測試方法預期 `ImportError`／`TypeError`／`AssertionError`。
"""
import unittest
from datetime import date

import numpy as np
import pandas as pd


# ==============================================================================
# T1／T4 — Meta-Learner 輸入契約：欄位允許清單與組合數
# ==============================================================================

class MetaLearnerInputContractTests(unittest.TestCase):
    """`build_meta_learner_input()`：輸出欄位集合須精確等於
    OOF 機率欄 ∪ `META_REGIME_FEATURE_COLS`，多一欄或少一組模型都必須
    結構性拒絕（`MetaInputContractError`），不得默默訓練。"""

    def _oof_df(self, extra_cols=None):
        from src.ml.baseline_models import META_REGIME_FEATURE_COLS

        n = 6
        data = {
            "stock_id": ["2330"] * n,
            "trade_date": pd.date_range("2024-01-02", periods=n),
            "lr_A_p0": np.linspace(0.1, 0.9, n),
            "lr_A_p1": 1 - np.linspace(0.1, 0.9, n),
            "rf_A_p0": np.linspace(0.2, 0.8, n),
            "rf_A_p1": 1 - np.linspace(0.2, 0.8, n),
            "lgbm_A_p0": np.linspace(0.3, 0.7, n),
            "lgbm_A_p1": 1 - np.linspace(0.3, 0.7, n),
            "xgb_A_p0": np.linspace(0.4, 0.6, n),
            "xgb_A_p1": 1 - np.linspace(0.4, 0.6, n),
            "split_segment": ["meta_train"] * n,
            "label_end_date": pd.date_range("2024-01-03", periods=n),
        }
        for c in META_REGIME_FEATURE_COLS:
            data[c] = np.linspace(-1.0, 1.0, n)
        if extra_cols:
            data.update(extra_cols)
        return pd.DataFrame(data)

    def test_rejects_disallowed_extra_column(self):
        """T1・known-FAIL：混入原始特徵欄 `rsi_14`（不在允許清單內）。"""
        from src.ml.stacking import MetaInputContractError, build_meta_learner_input

        df = self._oof_df(extra_cols={"rsi_14": np.linspace(20, 80, 6)})
        with self.assertRaises(MetaInputContractError):
            build_meta_learner_input(df)

    def test_accepts_allowed_columns_exactly(self):
        """T1・正向案例：只含允許清單內的欄位時，輸出欄位集合精確符合。"""
        from src.ml.baseline_models import META_REGIME_FEATURE_COLS
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df()
        prob_cols = [c for c in df.columns if c.startswith(("lr_", "rf_", "lgbm_", "xgb_"))]
        expected = set(prob_cols) | set(META_REGIME_FEATURE_COLS)

        matrix, _ = build_meta_learner_input(df)
        self.assertEqual(set(matrix.columns), expected)

    def test_assemble_oof_matrix_rejects_incomplete_model_arm_groups(self):
        """T4・known-FAIL：`fold_results` 只含 3 組模型（漏 `xgb`），
        輸出形狀與宣告的 4 組不符，必須拒絕、不得靜默用 3 組跑完。"""
        from src.ml.stacking import MetaInputContractError, assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.4, 0.6]]), "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm")  # 漏 xgb
        ]
        with self.assertRaises(MetaInputContractError):
            assemble_oof_matrix(fold_results, target_column="target_up_down")

    def test_assemble_oof_matrix_accepts_complete_four_groups(self):
        """T4・正向案例：4 組齊全時正常組出矩陣，欄數與宣告一致。"""
        from src.ml.stacking import assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.4, 0.6]]), "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        matrix = assemble_oof_matrix(fold_results, target_column="target_up_down")
        prob_cols = [c for c in matrix.columns if c.startswith(("lr_", "rf_", "lgbm_", "xgb_"))]
        self.assertEqual(len(prob_cols), 4 * 2, "4 組 × 2 類別（up_down 二分類）")


# ==============================================================================
# T2 — Arm B 結構性排除
# ==============================================================================

class ArmBExclusionTests(unittest.TestCase):
    """本 SB 只用 Arm A（折 0～32 情緒訊號為 0，Gate A §3.1 裁決）。
    OOF 矩陣組裝遇到任何 Arm B 紀錄，一律拋例外——不留「記錄警告後繼續」
    的選項（PO 複核明確要求）。"""

    def test_assemble_oof_matrix_rejects_arm_b_entry(self):
        """T2・known-FAIL：`fold_results` 混入一筆 `arm="B"`。"""
        from src.ml.stacking import MetaInputContractError, assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.4, 0.6]]), "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        fold_results.append(
            {"model_name": "rf", "arm": "B", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.5, 0.5]]), "proba_classes": [0, 1]})
        with self.assertRaises(MetaInputContractError):
            assemble_oof_matrix(fold_results, target_column="target_up_down")

    def test_assemble_oof_matrix_output_has_no_arm_b_columns(self):
        """T2・正向案例：Arm A only 輸入時，輸出欄名不存在任何 `*_B_p*` 形式。"""
        import re

        from src.ml.stacking import assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.4, 0.6]]), "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        matrix = assemble_oof_matrix(fold_results, target_column="target_up_down")
        arm_b_cols = [c for c in matrix.columns if re.match(r".*_B_p", c)]
        self.assertEqual(arm_b_cols, [])


# ==============================================================================
# T3／T9 — 二階 Purge 與 split_segment 完整性
# ==============================================================================

class SecondStagePurgeTests(unittest.TestCase):
    """`apply_second_stage_purge()`：Meta-Train 中 `label_end_date`（或
    `label_end_date_tb`）晚於或等於 Meta-Eval 最早 `trade_date` 的列，
    須標為 `purged`（保留列，不刪除）；其餘列維持 `meta_train`。
    分別以 `label_end_date` 與 `label_end_date_tb` 兩欄各測一次
    （PO 複核要求：規則須對兩個 target 都成立，不只驗證其中一欄）。"""

    META_EVAL_START = pd.Timestamp("2025-05-02")

    def _df(self, label_end_col, label_end_values):
        n = len(label_end_values)
        return pd.DataFrame({
            "stock_id": ["2330"] * n,
            "trade_date": pd.date_range("2025-04-01", periods=n),
            label_end_col: label_end_values,
            "split_segment": ["meta_train"] * n,
        })

    def test_label_end_date_later_than_boundary_is_purged(self):
        """T3・known-FAIL（label_end_date，「晚於」案例）。"""
        from src.ml.stacking import apply_second_stage_purge

        df = self._df("label_end_date", [pd.Timestamp("2025-05-05")])  # 晚於邊界
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date")
        self.assertEqual(out.iloc[0]["split_segment"], "purged")

    def test_label_end_date_equal_to_boundary_is_purged(self):
        """T3・known-FAIL（label_end_date，「等於」案例，PO 複核追加）——
        規則是「晚於或等於」，恰好等於邊界的列也必須是 purged。"""
        from src.ml.stacking import apply_second_stage_purge

        df = self._df("label_end_date", [self.META_EVAL_START])  # 恰好等於邊界
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date")
        self.assertEqual(out.iloc[0]["split_segment"], "purged")

    def test_label_end_date_earlier_than_boundary_stays_meta_train(self):
        """T3・正向案例（label_end_date）：明顯早於邊界的列不得被誤刪，
        防止「過度保守、全部排除」的相反錯誤。"""
        from src.ml.stacking import apply_second_stage_purge

        df = self._df("label_end_date", [pd.Timestamp("2025-04-02")])  # 明顯早於邊界
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date")
        self.assertEqual(out.iloc[0]["split_segment"], "meta_train")

    def test_label_end_date_tb_later_than_boundary_is_purged(self):
        """T3・known-FAIL（label_end_date_tb，「晚於」案例——參數化第二欄）。"""
        from src.ml.stacking import apply_second_stage_purge

        df = self._df("label_end_date_tb", [pd.Timestamp("2025-05-08")])
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date_tb")
        self.assertEqual(out.iloc[0]["split_segment"], "purged")

    def test_label_end_date_tb_equal_to_boundary_is_purged(self):
        """T3・known-FAIL（label_end_date_tb，「等於」案例）。"""
        from src.ml.stacking import apply_second_stage_purge

        df = self._df("label_end_date_tb", [self.META_EVAL_START])
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date_tb")
        self.assertEqual(out.iloc[0]["split_segment"], "purged")

    def test_label_end_date_tb_earlier_than_boundary_stays_meta_train(self):
        """T3・正向案例（label_end_date_tb）。"""
        from src.ml.stacking import apply_second_stage_purge

        df = self._df("label_end_date_tb", [pd.Timestamp("2025-04-10")])
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date_tb")
        self.assertEqual(out.iloc[0]["split_segment"], "meta_train")

    def test_row_count_invariant_no_row_disappears(self):
        """T9・known-FAIL：輸出總列數必須精確等於輸入總列數——purge
        是標記，不是刪除。"""
        from src.ml.stacking import apply_second_stage_purge

        values = [pd.Timestamp("2025-04-01"), self.META_EVAL_START, pd.Timestamp("2025-06-01")]
        df = self._df("label_end_date", values)
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date")
        self.assertEqual(len(out), len(df))

    def test_split_segment_value_domain_is_exactly_three_values(self):
        """T9：`split_segment` 欄的值域只能是三者之一，不存在其他字串或 NaN。"""
        from src.ml.stacking import apply_second_stage_purge

        values = [pd.Timestamp("2025-04-01"), self.META_EVAL_START, pd.Timestamp("2025-06-01")]
        df = self._df("label_end_date", values)
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date")
        self.assertTrue(out["split_segment"].isin(["meta_train", "meta_eval", "purged"]).all())
        self.assertFalse(out["split_segment"].isna().any())

    def test_purge_rule_only_applies_to_meta_train_rows(self):
        """T3・盲點修補（PO 第三輪複核，比照 SB3 `6dcbdc7`）：規則只能
        作用在 `split_segment == "meta_train"` 的列。`meta_eval` 列的
        `trade_date`／`label_end_date` 依定義必然晚於或等於
        `META_EVAL_START_DATE`（它們就是從那天起算的）——一個不看
        `split_segment`、對全部列無差別套用日期規則的實作，會把整個
        Meta-Eval 段誤標為 `purged`，而先前 8 條測試的輸入全是純
        `meta_train`，抓不到這個盲點（`CLAUDE.md` §9A.1）。"""
        from src.ml.stacking import apply_second_stage_purge

        df = pd.DataFrame({
            "stock_id": ["2330", "2330", "2330"],
            "trade_date": [
                pd.Timestamp("2025-04-20"),  # meta_train 列
                pd.Timestamp("2025-05-10"),  # meta_eval 列（在邊界之後起算）
                pd.Timestamp("2025-05-15"),  # 已是 purged 的列
            ],
            "label_end_date": [
                pd.Timestamp("2025-05-05"),  # 晚於邊界，應被轉為 purged
                pd.Timestamp("2025-05-11"),  # 晚於邊界，但屬 meta_eval，不受規則影響
                pd.Timestamp("2025-05-20"),  # 晚於邊界，但本已是 purged
            ],
            "split_segment": ["meta_train", "meta_eval", "purged"],
        })
        out = apply_second_stage_purge(df, self.META_EVAL_START, label_end_col="label_end_date")

        self.assertEqual(
            out.iloc[0]["split_segment"], "purged",
            "meta_train 列的 label_end_date 晚於邊界，應轉為 purged")
        self.assertEqual(
            out.iloc[1]["split_segment"], "meta_eval",
            "meta_eval 列不受二階 purge 規則影響，即使其 label_end_date 也晚於"
            "邊界，仍須維持 meta_eval——這是本測試要抓的盲點")
        self.assertEqual(
            out.iloc[2]["split_segment"], "purged",
            "本已是 purged 的列維持不變，不得被改回其他值")


# ==============================================================================
# T5／T12 — 機率輸出：缺席類別對齊與形狀/一致性
# ==============================================================================

class MissingClassProbaAlignmentTests(unittest.TestCase):
    """`fit_predict_specialist_fold(..., return_proba=True)`：訓練集若缺席
    某個類別，`proba_classes` 須忠實反映（不得假設固定三類）。"""

    def _prepared(self, X_df, y_series, dates):
        return {
            "X": X_df, "y": y_series,
            "trade_date": np.asarray(dates),
            "retained_index": np.arange(len(y_series)),
            "n_target_null_excluded": 0,
            "n_feature_null_excluded": 0,
        }

    def test_proba_classes_reflects_missing_timeout_class(self):
        """T5・known-FAIL：訓練集僅含 `{-1, 1}`（無 Timeout `0`），
        `proba_classes` 必須是 `[-1, 1]`，不得假設固定三類。"""
        from src.ml.specialist_training import fit_predict_specialist_fold

        rng = np.random.RandomState(1)
        n_train = 20
        y_train = pd.Series(rng.choice([-1, 1], size=n_train))
        X_train = pd.DataFrame({"f1": rng.normal(size=n_train), "f2": rng.normal(size=n_train)})
        n_test = 5
        y_test = pd.Series(rng.choice([-1, 1], size=n_test))
        X_test = pd.DataFrame({"f1": rng.normal(size=n_test), "f2": rng.normal(size=n_test)})

        train_prepared = self._prepared(X_train, y_train, pd.date_range("2026-01-01", periods=n_train))
        test_prepared = self._prepared(X_test, y_test, pd.date_range("2026-03-01", periods=n_test))

        result = fit_predict_specialist_fold(
            "random_forest", train_prepared, test_prepared, return_proba=True)
        self.assertEqual(sorted(result["proba_classes"]), [-1, 1])
        self.assertEqual(result["y_proba"].shape, (n_test, 2))

    def test_missing_class_column_filled_with_nan_not_zero_in_matrix(self):
        """T5：下游組矩陣時，缺席類別（此處 Timeout `0`）對應欄位須為
        `NaN`，不得誤植 `0`（0 機率與「訓練集沒見過這個類別」語意不同）。"""
        from src.ml.stacking import assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.5, 0.5]]), "proba_classes": [-1, 1]}  # 缺 0
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        matrix = assemble_oof_matrix(fold_results, target_column="target_triple_barrier")
        for m in ("lr", "rf", "lgbm", "xgb"):
            col = f"{m}_A_p0"
            self.assertIn(col, matrix.columns)
            self.assertTrue(pd.isna(matrix.iloc[0][col]), f"{col} 缺席類別應為 NaN，不是 0")

    def test_assemble_oof_matrix_probability_values_align_with_declared_classes(self):
        """T5・known-FAIL（實作階段補強，反查法自我測試發現）：先前的
        `test_missing_class_column_filled_with_nan_not_zero_in_matrix` 用
        `y_proba=[[0.5, 0.5]]`（對稱值），一個把 `proba_classes` 的索引
        對錯（例如錯位一格）的實作，剛好因為兩個值相同而測不出來。改用
        不對稱機率值（`0.3`／`0.7`），直接斷言每個類別欄落在正確的值，
        才能真正抓到「欄位存在但塞錯值」這類錯誤（不只「欄位存在與否」）。"""
        from src.ml.stacking import assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.3, 0.7]]), "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        matrix = assemble_oof_matrix(fold_results, target_column="target_up_down")
        for m in ("lr", "rf", "lgbm", "xgb"):
            self.assertAlmostEqual(
                matrix.iloc[0][f"{m}_A_p0"], 0.3,
                msg=f"{m}_A_p0 應對應 proba_classes[0]（類別 0）的機率 0.3")
            self.assertAlmostEqual(
                matrix.iloc[0][f"{m}_A_p1"], 0.7,
                msg=f"{m}_A_p1 應對應 proba_classes[1]（類別 1）的機率 0.7")


class ProbabilityAlignmentTests(unittest.TestCase):
    """T12（PO 複核追加）：`predict_proba` 輸出形狀、逐列和為 1、
    `argmax` 與 `y_pred` 一致——四個模型（LR／RF／LightGBM／XGBoost）
    各跑一次，這是 sklearn／LightGBM／XGBoost 的既定行為，不是本 SB
    自訂邏輯，但若 `return_proba` 參數接線接錯（例如回傳了未對齊的
    陣列），本測試會抓到。"""

    def _prepared(self, X_df, y_series, dates):
        return {
            "X": X_df, "y": y_series,
            "trade_date": np.asarray(dates),
            "retained_index": np.arange(len(y_series)),
            "n_target_null_excluded": 0,
            "n_feature_null_excluded": 0,
        }

    def test_proba_shape_sums_to_one_and_matches_argmax(self):
        from src.ml.specialist_training import MODEL_NAMES, fit_predict_specialist_fold

        rng = np.random.RandomState(3)
        n_per_class = 15
        labels = [-1, 0, 1]
        y_train_arr = np.repeat(labels, n_per_class)
        n_train = len(y_train_arr)
        X_train = pd.DataFrame({
            "f1": y_train_arr * 2.0 + rng.normal(scale=0.1, size=n_train),
            "f2": rng.normal(size=n_train),
        })
        y_test_arr = np.array(labels * 4)
        n_test = len(y_test_arr)
        X_test = pd.DataFrame({
            "f1": y_test_arr * 2.0 + rng.normal(scale=0.1, size=n_test),
            "f2": rng.normal(size=n_test),
        })

        train_prepared = self._prepared(X_train, pd.Series(y_train_arr), pd.date_range("2026-01-01", periods=n_train))
        test_prepared = self._prepared(X_test, pd.Series(y_test_arr), pd.date_range("2026-03-01", periods=n_test))

        for model_name in MODEL_NAMES:
            with self.subTest(model=model_name):
                result = fit_predict_specialist_fold(
                    model_name, train_prepared, test_prepared, return_proba=True)
                y_proba = result["y_proba"]
                proba_classes = np.asarray(result["proba_classes"])

                self.assertEqual(y_proba.shape, (n_test, len(proba_classes)))
                row_sums = y_proba.sum(axis=1)
                np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

                argmax_labels = proba_classes[np.argmax(y_proba, axis=1)]
                np.testing.assert_array_equal(
                    argmax_labels, np.asarray(result["y_pred"]),
                    err_msg=f"{model_name}：predict_proba 的 argmax 應與 y_pred 逐列一致")


# ==============================================================================
# T6 — Holdout 守衛
# ==============================================================================

class HoldoutGuardTests(unittest.TestCase):
    """`reject_rows_at_or_after()`：`trade_date >= HOLDOUT_START_DATE`
    （2025-10-23，含端點本身）一律拒絕。"""

    def _df(self, trade_dates):
        return pd.DataFrame({
            "stock_id": ["2330"] * len(trade_dates),
            "trade_date": pd.to_datetime(trade_dates),
        })

    def test_rejects_boundary_date_itself(self):
        """T6・known-FAIL：`trade_date == "2025-10-23"`（邊界當天本身）。"""
        from src.ml.stacking import HOLDOUT_START_DATE, HoldoutViolation, reject_rows_at_or_after

        df = self._df(["2025-10-23"])
        with self.assertRaises(HoldoutViolation):
            reject_rows_at_or_after(df, "trade_date", HOLDOUT_START_DATE)

    def test_rejects_dates_clearly_after_boundary(self):
        """T6・known-FAIL：`trade_date` 明顯落在 Holdout 內。"""
        from src.ml.stacking import HOLDOUT_START_DATE, HoldoutViolation, reject_rows_at_or_after

        df = self._df(["2026-01-01"])
        with self.assertRaises(HoldoutViolation):
            reject_rows_at_or_after(df, "trade_date", HOLDOUT_START_DATE)

    def test_allows_day_before_boundary(self):
        """T6・正向案例：`trade_date == "2025-10-22"`（邊界前一日）不得觸發，
        避免「差一天」的邊界錯誤。"""
        from src.ml.stacking import HOLDOUT_START_DATE, reject_rows_at_or_after

        df = self._df(["2025-10-22"])
        result = reject_rows_at_or_after(df, "trade_date", HOLDOUT_START_DATE)
        self.assertEqual(len(result), 1)


# ==============================================================================
# T7／T8 — Best Single Specialist 選法
# ==============================================================================

class BestSingleSpecialistSelectionTests(unittest.TestCase):
    """`select_best_specialist(meta_train_df, target_column) -> (best_model_name, ranking_df)`：
    只接受 `split_segment == "meta_train"` 的資料；排序指標為模組層級常數，
    介面不接受 `metric=` 覆寫。

    **2026-09-15 補件（PO 複核 P2 回答第 2 點，審查方實測）**：`target_column`
    改為必填、無預設值——舊版預設 `"target_up_down"` 曾被審查方用 TB 型態
    資料（`y_true` 含 `-1/0/1`）呼叫但不傳 `target_column` 實測：不報錯，
    `labels=[0,1]` 靜默忽略 `-1` 類，算出一個看似合理但其實用錯定義域的
    分數（實測第一名 `macro_f1` 0.750，顯式傳 TB 得 0.722，兩者不同代表
    預設值確實把一個必須明講的選擇藏起來了）。既有呼叫端已全部改為顯式
    傳入 `target_column`（呼叫方式調整，非斷言變更）。"""

    def _meta_train_df(self, segments=None):
        n = 12
        rng = np.random.RandomState(5)
        models = np.tile(["lr", "rf", "lgbm", "xgb"], n // 4)
        y_true = rng.choice([0, 1], size=n)
        y_pred = rng.choice([0, 1], size=n)
        return pd.DataFrame({
            "model_name": models,
            "y_true": y_true,
            "y_pred": y_pred,
            "split_segment": segments if segments is not None else ["meta_train"] * n,
        })

    def test_rejects_non_meta_train_rows(self):
        """T7・known-FAIL：`split_segment` 混有 `meta_eval`／`holdout`，
        必須拒絕、不得靜默納入計算。"""
        from src.ml.stacking import SelectionSourceError, select_best_specialist

        segments = ["meta_train"] * 10 + ["meta_eval", "holdout"]
        df = self._meta_train_df(segments=segments)
        with self.assertRaises(SelectionSourceError):
            select_best_specialist(df, target_column="target_up_down")

    def test_accepts_pure_meta_train_and_returns_full_ranking(self):
        """T7＋§3.4：輸入全為 `meta_train` 時正常回傳；`ranking_df` 須含
        四個 Specialist 的完整排名（不只第一名），依 `SELECTION_METRIC`
        遞減排序。"""
        from src.ml.stacking import SELECTION_METRIC, select_best_specialist

        df = self._meta_train_df()
        best_model, ranking_df = select_best_specialist(df, target_column="target_up_down")

        self.assertIsInstance(best_model, str)
        self.assertEqual(len(ranking_df), 4, "四個 Specialist（Arm A）的完整排名")
        self.assertIn(SELECTION_METRIC, ranking_df.columns)
        scores = ranking_df[SELECTION_METRIC].tolist()
        self.assertEqual(scores, sorted(scores, reverse=True), "須依指標遞減排序")
        self.assertEqual(best_model, ranking_df.iloc[0]["model_name"])

    def test_rejects_metric_override_keyword(self):
        """T8・known-FAIL：嘗試以 `metric=` 關鍵字參數覆寫排序指標——
        介面本身不接受該參數（不是「接受了但忽略」）。"""
        from src.ml.stacking import select_best_specialist

        df = self._meta_train_df()
        with self.assertRaises(TypeError):
            select_best_specialist(df, target_column="target_up_down", metric="accuracy")

    def test_selection_metric_is_module_level_constant_not_a_parameter(self):
        """T8：靜態檢查——`select_best_specialist()` 的簽章不存在任何
        指標名稱參數，唯一涉及指標的名稱是對模組常數 `SELECTION_METRIC`
        的引用。"""
        import inspect

        from src.ml.stacking import SELECTION_METRIC, select_best_specialist

        self.assertEqual(SELECTION_METRIC, "macro_f1")
        sig = inspect.signature(select_best_specialist)
        self.assertNotIn("metric", sig.parameters)


# ==============================================================================
# T11 — NaN 機率／regime 欄位列在 Meta-Learner 輸入端被排除並計數
# ==============================================================================

class NanExclusionInMetaLearnerInputTests(unittest.TestCase):
    """`LogisticRegression`／`RidgeClassifier` 不接受 NaN，但 OOF 檔本身
    保留 NaN（T5 已驗證，供稽核）。`build_meta_learner_input()` 對任何
    輸入欄含 NaN 的列必須排除並回傳逐欄排除計數，不得插補、不得填 0
    （比照 SB3 規則 (b)）。

    **實作階段發現並訂正的夾具錯誤**：`_oof_df()` 原本把 `rf_A_p0`
    （列 2）與 `ma20_bias_ratio`（意圖列 3）的 `NaN` 都放在同一列索引 2
    （`[0.01, 0.02, np.nan, 0.04]` 的 `NaN` 落在索引 2，不是索引 3），
    導致兩個「不同欄各自 NaN」的案例實際疊在同一列上——只有 1 列被排除，
    不是預期的 2 列，`build_meta_learner_input()` 的實作本身沒有問題，
    是夾具資料構造錯誤。已訂正為 `[0.01, 0.02, 0.03, np.nan]`（NaN 移至
    索引 3），使兩個 NaN 分別落在不同列，測試才能真正驗證「機率欄 NaN」
    與「regime 欄 NaN」是兩個獨立會被排除的案例。"""

    def _oof_df(self):
        from src.ml.baseline_models import META_REGIME_FEATURE_COLS

        n = 4
        data = {
            "stock_id": ["2330"] * n,
            "trade_date": pd.date_range("2024-01-02", periods=n),
            "lr_A_p0": [0.1, 0.2, 0.3, 0.4],
            "lr_A_p1": [0.9, 0.8, 0.7, 0.6],
            "rf_A_p0": [0.15, 0.25, np.nan, 0.45],   # 列 2 有一欄 NaN（缺席類別）
            "rf_A_p1": [0.85, 0.75, 0.55, 0.55],
            "lgbm_A_p0": [0.2, 0.3, 0.4, 0.5],
            "lgbm_A_p1": [0.8, 0.7, 0.6, 0.5],
            "xgb_A_p0": [0.25, 0.35, 0.45, 0.55],
            "xgb_A_p1": [0.75, 0.65, 0.55, 0.45],
            "split_segment": ["meta_train"] * n,
            "label_end_date": pd.date_range("2024-01-03", periods=n),
        }
        vol = [0.1, 0.2, 0.3, 0.4]
        ma20 = [0.01, 0.02, 0.03, np.nan]  # 列 3 的 regime 欄 NaN（模擬暖機期）
        data["volatility_20d"] = vol
        data["ma20_bias_ratio"] = ma20
        for c in META_REGIME_FEATURE_COLS:
            if c not in data:
                data[c] = np.linspace(0, 1, n)
        return pd.DataFrame(data)

    def test_row_with_nan_probability_column_excluded(self):
        """T11・known-FAIL：列 2（`rf_A_p0` 為 NaN）不得出現在輸出矩陣中。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df()
        matrix, exclusion_counts = build_meta_learner_input(df)
        self.assertEqual(len(matrix), 2, "4 列中有 2 列含 NaN，應排除 2 列")
        self.assertFalse(matrix.isna().any().any(), "輸出矩陣不得殘留任何 NaN")

    def test_row_with_nan_regime_feature_excluded(self):
        """T11・known-FAIL：列 3（`ma20_bias_ratio` 為 NaN，模擬暖機期）
        同樣須排除，不因為是 regime 欄而網開一面。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df()
        matrix, _ = build_meta_learner_input(df)
        self.assertNotIn(2, matrix.index.tolist() if matrix.index.name else [])
        # 以列數與殘留 NaN 檢查取代直接比對原始 index（組裝過程可能重置索引）
        self.assertEqual(len(matrix), 2)

    def test_exclusion_counts_reported_per_column(self):
        """T11：排除計數逐欄回報，不是只給一個總數——供證據 JSON 稽核用。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df()
        _, exclusion_counts = build_meta_learner_input(df)
        self.assertIsInstance(exclusion_counts, dict)
        self.assertGreater(sum(exclusion_counts.values()), 0)
        self.assertIn("rf_A_p0", exclusion_counts)
        self.assertIn("ma20_bias_ratio", exclusion_counts)

    def test_rows_without_nan_preserved_unchanged(self):
        """T11・正向案例：不含 NaN 的列（列 0、列 1）原樣保留在輸出中。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df()
        matrix, _ = build_meta_learner_input(df)
        self.assertAlmostEqual(matrix.iloc[0]["lr_A_p0"], 0.1)
        self.assertAlmostEqual(matrix.iloc[1]["lr_A_p0"], 0.2)


# ==============================================================================
# T13 — Holdout 折的 Specialist 從未被迭代到
# ==============================================================================

class HoldoutFoldsNeverIteratedTests(unittest.TestCase):
    """`iter_oof_folds(splitter, panel, holdout_start_date)`：§4.1 承諾
    訓練迴圈根本不迭代到 Holdout 折——不是 fit 了不用，是產出的折集合
    本身就不包含任何測試窗跨入 Holdout 的折。"""

    def _panel(self, n_days=200):
        dates = pd.bdate_range("2024-01-01", periods=n_days)
        n_stocks = 3
        rows = []
        for d in dates:
            for s in ("A", "B", "C"):
                rows.append({"stock_id": s, "trade_date": d, "target_up_down": 0})
        return pd.DataFrame(rows)

    def test_no_fold_test_window_reaches_holdout_boundary(self):
        """T13・正向案例：所有產出折的測試窗結束日期皆早於 Holdout 起點。"""
        from src.ml.time_series_split import WalkForwardSplitter

        from src.ml.stacking import iter_oof_folds

        panel = self._panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        holdout_start = panel["trade_date"].max() - pd.Timedelta(days=40)  # 人為切在資料尾端前

        folds = list(iter_oof_folds(splitter, panel, holdout_start))
        for _, test_idx, _ in folds:
            test_dates = panel.loc[test_idx, "trade_date"]
            self.assertLess(test_dates.max(), holdout_start,
                             "任何一折的測試窗結束日期都不得達到或超過 Holdout 起點")
            self.assertLess(test_dates.min(), holdout_start)

    def test_straddling_fold_is_excluded_entirely(self):
        """T13・known-FAIL（實作階段補強，反查法自我測試發現）：邊界若恰好
        落在某一折測試窗**中間**（而非折與折的交界），一個誤用
        `test_dates.min() < boundary`（而非 `test_dates.max() < boundary`）
        的實作，會把這個「半折」也產出——測試窗前半段落在邊界前、後半段
        已跨入 Holdout，整折理應被丟棄，不得只切一半。用真實折邊界
        （非任意天數偏移）精確算出邊界，確保這個折真的被跨到，不是
        「湊巧沒有任何折跨界」而讓突變體僥倖通過。"""
        from src.ml.time_series_split import WalkForwardSplitter

        from src.ml.stacking import iter_oof_folds

        panel = self._panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")

        all_folds = list(splitter.split(panel))
        target_fold_idx = 5  # 任意挑一個離頭尾都夠遠的折
        _, target_test_idx, _ = all_folds[target_fold_idx]
        target_test_dates = panel.loc[target_test_idx, "trade_date"]
        straddle_boundary = target_test_dates.min() + (
            (target_test_dates.max() - target_test_dates.min()) / 2)

        # 邊界必須真的落在該折測試窗的開區間內，否則不構成「跨界」案例
        self.assertGreater(straddle_boundary, target_test_dates.min())
        self.assertLess(straddle_boundary, target_test_dates.max())

        produced_folds = list(iter_oof_folds(splitter, panel, straddle_boundary))
        for _, test_idx, _ in produced_folds:
            test_dates = panel.loc[test_idx, "trade_date"]
            self.assertLess(
                test_dates.max(), straddle_boundary,
                "任何產出折的測試窗都不得跨過邊界——半折洩漏必須整折丟棄")

    def test_shifting_boundary_earlier_reduces_fold_count_by_expected_amount(self):
        """T13・known-FAIL：把 Holdout 邊界往前挪一折的份量，產出折數應
        相應減少——證明 `iter_oof_folds()` 真的依邊界過濾，不是回傳全部
        折數的假象。"""
        from src.ml.time_series_split import WalkForwardSplitter

        from src.ml.stacking import iter_oof_folds

        panel = self._panel()
        splitter = WalkForwardSplitter(train_window_size=30, test_window_size=10, mode="rolling")
        holdout_start = panel["trade_date"].max() - pd.Timedelta(days=40)
        holdout_start_earlier = holdout_start - pd.Timedelta(days=14)  # 約一折份量

        folds_normal = list(iter_oof_folds(splitter, panel, holdout_start))
        folds_earlier = list(iter_oof_folds(splitter, panel, holdout_start_earlier))

        self.assertLess(
            len(folds_earlier), len(folds_normal),
            "邊界往前挪動後，產出折數應減少，證明過濾邏輯真的在依邊界生效")


# ==============================================================================
# T14 — 常數釘住
# ==============================================================================

class ConstantsPinnedTests(unittest.TestCase):
    """`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 常數值釘住——這兩個
    常數是整個三層結構的邊界依據（Gate A §4.4／§4.6），任何一個被意外
    改動都必須被測試抓到。"""

    def test_holdout_start_date_value(self):
        from src.ml.stacking import HOLDOUT_START_DATE

        self.assertEqual(pd.Timestamp(HOLDOUT_START_DATE), pd.Timestamp("2025-10-23"))

    def test_meta_eval_start_date_value(self):
        from src.ml.stacking import META_EVAL_START_DATE

        self.assertEqual(pd.Timestamp(META_EVAL_START_DATE), pd.Timestamp("2025-05-02"))

    def test_constants_are_comparable_to_timestamps(self):
        """兩個常數須可與 `pd.Timestamp` 直接比較（`<`／`>=`），供 §4.6
        腳本層守衛與 T6／T3 的實作直接使用，不需每次呼叫端自行轉型。"""
        from src.ml.stacking import HOLDOUT_START_DATE, META_EVAL_START_DATE

        self.assertLess(pd.Timestamp(META_EVAL_START_DATE), pd.Timestamp(HOLDOUT_START_DATE))
        self.assertTrue(pd.Timestamp("2025-10-23") >= pd.Timestamp(HOLDOUT_START_DATE))


# ==============================================================================
# T10 — return_proba 參數：既有呼叫端零改動回歸驗證
# ==============================================================================

class ReturnProbaRegressionTests(unittest.TestCase):
    """`fit_predict_specialist_fold()` 新增 `return_proba` 參數，
    預設 `False` 時既有呼叫端（SB3）零改動。"""

    def _prepared(self, X_df, y_series, dates):
        return {
            "X": X_df, "y": y_series,
            "trade_date": np.asarray(dates),
            "retained_index": np.arange(len(y_series)),
            "n_target_null_excluded": 0,
            "n_feature_null_excluded": 0,
        }

    def _synthetic(self, seed=42, n_train=30, n_test=10):
        rng = np.random.RandomState(seed)
        X_train = pd.DataFrame({"f1": rng.normal(size=n_train), "f2": rng.normal(size=n_train)})
        y_train = pd.Series(rng.choice([0, 1], size=n_train))
        X_test = pd.DataFrame({"f1": rng.normal(size=n_test), "f2": rng.normal(size=n_test)})
        y_test = pd.Series(rng.choice([0, 1], size=n_test))
        return (
            self._prepared(X_train, y_train, pd.date_range("2026-01-01", periods=n_train)),
            self._prepared(X_test, y_test, pd.date_range("2026-03-01", periods=n_test)),
        )

    def test_default_return_proba_false_keys_unchanged(self):
        """T10・回歸基準：不傳 `return_proba`（維持預設）時，回傳鍵集合
        與 SB3 既有行為完全相同——不多不少。"""
        from src.ml.specialist_training import fit_predict_specialist_fold

        train_prepared, test_prepared = self._synthetic()
        result = fit_predict_specialist_fold("random_forest", train_prepared, test_prepared)

        expected_keys = {
            "model_name", "y_true", "y_pred", "trade_date", "retained_index",
            "n_train", "n_test", "train_classes", "scaler_type", "n_iter_",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertNotIn("y_proba", result)
        self.assertNotIn("proba_classes", result)

    def test_return_proba_true_adds_keys_without_changing_existing_values(self):
        """T10：`return_proba=True` 時純粹疊加，既有欄位的值與
        `return_proba=False` 的呼叫逐值相同——證明新增參數不改變既有路徑
        的計算結果。"""
        from src.ml.specialist_training import fit_predict_specialist_fold

        train_prepared, test_prepared = self._synthetic()
        result_false = fit_predict_specialist_fold("random_forest", train_prepared, test_prepared)
        result_true = fit_predict_specialist_fold(
            "random_forest", train_prepared, test_prepared, return_proba=True)

        self.assertIn("y_proba", result_true)
        self.assertIn("proba_classes", result_true)
        np.testing.assert_array_equal(result_false["y_pred"], result_true["y_pred"])
        self.assertEqual(result_false["n_train"], result_true["n_train"])
        self.assertEqual(result_false["n_test"], result_true["n_test"])
        self.assertEqual(result_false["scaler_type"], result_true["scaler_type"])


# ==============================================================================
# 盲點修補（PO 第三輪複核，2026-09-14）——Meta-Learner 訓練路徑只吃
# meta_train 列；三個專屬例外類別不得互相繼承
# ==============================================================================

class MetaLearnerTrainingSegmentTests(unittest.TestCase):
    """`build_meta_learner_input(df, segment="meta_train")`：Meta-Learner
    訓練矩陣只能來自 `split_segment == "meta_train"` 的列；`meta_eval`／
    `purged` 列必須被排除，且排除數量可查核（PO 第三輪複核追加，比照
    SB3 `6dcbdc7` 的盲點修補模式——先前 T1／T11 的夾具全是純
    `meta_train`，未曾驗證「混入其他 segment 時會不會被正確過濾」）。"""

    def _mixed_segment_df(self):
        from src.ml.baseline_models import META_REGIME_FEATURE_COLS

        rows = []
        for seg, n in (("meta_train", 3), ("meta_eval", 2), ("purged", 1)):
            for i in range(n):
                row = {
                    "stock_id": "2330",
                    "trade_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                    "lr_A_p0": 0.3, "lr_A_p1": 0.7,
                    "rf_A_p0": 0.4, "rf_A_p1": 0.6,
                    "lgbm_A_p0": 0.35, "lgbm_A_p1": 0.65,
                    "xgb_A_p0": 0.45, "xgb_A_p1": 0.55,
                    "split_segment": seg,
                    "label_end_date": pd.Timestamp("2024-01-02"),
                }
                for c in META_REGIME_FEATURE_COLS:
                    row[c] = 0.1
                rows.append(row)
        return pd.DataFrame(rows)

    def test_training_matrix_only_contains_meta_train_rows(self):
        """known-FAIL：若實作把 `purged`（或 `meta_eval`）列也算進訓練，
        輸出列數會是 4／5／6，不是預期的 3——精確列數斷言會抓到。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._mixed_segment_df()
        matrix, exclusion_counts = build_meta_learner_input(df, segment="meta_train")

        self.assertEqual(len(matrix), 3, "只有 3 列 meta_train，meta_eval／purged 皆須排除")
        self.assertEqual(
            exclusion_counts.get("segment_mismatch"), 3,
            "2 列 meta_eval + 1 列 purged = 3 列因 segment 不符被排除，須可查核")

    def test_segment_parameter_defaults_to_meta_train(self):
        """未顯式傳 `segment` 時，預設仍是 `meta_train`——訓練路徑的安全
        預設值，不得預設吃全部列（避免呼叫端忘記傳參數就靜默訓練在
        不該用的資料上）。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._mixed_segment_df()
        matrix, _ = build_meta_learner_input(df)
        self.assertEqual(len(matrix), 3)


class ExceptionHierarchyTests(unittest.TestCase):
    """三個專屬例外類別（`MetaInputContractError`／`HoldoutViolation`／
    `SelectionSourceError`）彼此不得互相繼承（PO 第三輪複核，回應紅測
    清單三個問題的回答第 1 點）——若其中一個繼承自另一個，該型別的
    `assertRaises` 可能被一個實際上分類錯誤的例外滿足，測試因此失去
    分辨力。**本項未計入 PO 授權的兩條測試範圍，屬 PM 主動補上的低成本
    結構性檢查，一併揭露於送審報告。**"""

    def test_exceptions_do_not_inherit_from_each_other(self):
        from src.ml.stacking import HoldoutViolation, MetaInputContractError, SelectionSourceError

        pairs = [
            (MetaInputContractError, HoldoutViolation),
            (MetaInputContractError, SelectionSourceError),
            (HoldoutViolation, SelectionSourceError),
        ]
        for a, b in pairs:
            with self.subTest(a=a.__name__, b=b.__name__):
                self.assertFalse(issubclass(a, b), f"{a.__name__} 不得繼承自 {b.__name__}")
                self.assertFalse(issubclass(b, a), f"{b.__name__} 不得繼承自 {a.__name__}")


if __name__ == "__main__":
    unittest.main()
