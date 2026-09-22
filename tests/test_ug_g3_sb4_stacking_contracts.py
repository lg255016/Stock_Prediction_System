# -*- coding: utf-8 -*-
"""`UG-G3-SB4` 補充紅測（RED）——PO 2026-09-15 複核 `dcf48c5` 後，審查方用
五個探針發現五處「靜默通過」，全部違反 Gate A §6 的結構性拒絕原則。

探針對照原始 `dcf48c5` 的實際現況（審查方實測，容器內乾淨模組）：

  P1  `build_meta_learner_input()` 的 `df` 缺 `ma20_bias_ratio` → 現況回傳
      9 欄矩陣、無錯。§4.3／§4.6 要求 `META_REGIME_FEATURE_COLS` 是允許
      清單，隱含「該有的都要有」，不是「有就用、沒有就跳過」。
  P2  `df` 缺 `xgb_A_p1` 機率欄 → 現況回傳 9 欄矩陣、無錯。機率欄必須
      恰為 4 模型 × 該 target 類別數，不符即拒絕。
  P3  `assemble_oof_matrix()` 同一 `(model, stock_id, trade_date)` 出現
      兩筆 → 現況後者靜默覆寫前者、無錯。同一列不可能來自兩折，重複鍵
      本身就是契約違規。
  P4  一筆紀錄 `stock_id` 兩個、`y_proba` 只有一列 → 現況 `zip()` 靜默
      截斷成一列、無錯。這是 `CLAUDE.md` §6「不得靜默截斷」的字面案例。
  P5  `select_best_specialist()` 只收到三個模型（缺一組）→ 現況回傳三列
      排名、無錯。模型集合必須等於 `EXPECTED_MODEL_NAMES`，否則
      `SelectionSourceError`。

另有一項非探針、審查方複核時一併指出的正確性缺口：`select_best_specialist()`
呼叫 `f1_score()` 未傳固定 `labels=`（依 `target_column` 對應的
`TARGET_CLASS_DOMAINS`）——若某 Specialist 的 Meta-Train 段剛好沒有某個
類別的真實列（例如 Triple-Barrier 的 Timeout），sklearn 預設只用
`y_true`／`y_pred` 聯集決定要平均哪些類別，會讓這個 Specialist 的 macro
分母比其他模型少一項，排名因此不可比（比照 `UG-G3-SB3` 洩漏診斷同一類
教訓：固定 `labels=` 才能保證跨模型可比）。

本檔**純為 RED 證據**——修正前，以下全部測試方法預期 `AssertionError`
（現況靜默通過，斷言的例外沒有被拋出）或數值不符。**不修改
`tests/test_ug_g3_sb4_stacking_red.py` 既有 41 條測試的任何斷言**（僅將
既有 `select_best_specialist(df)` 呼叫點改為顯式傳入 `target_column`，
屬呼叫方式調整，非斷言變更）。

================================================================================
第二輪補件（PO 2026-09-15 複核 `a1abcf4`／`433cae0` 後，回答 P2 修法的
第 2 點時發現的兩處新缺口）
================================================================================
  P6  `build_meta_learner_input()` 的 P2 修法只核對「四個模型的類別欄
      集合彼此一致」，不核對「與 target 真正的類別定義域一致」——四個
      模型**一致地**都缺同一個類別欄（例如都只有 `p0`、缺 `p1`）時，
      跨模型一致性檢查測不出來，因為四者互相比對時完全相同。新增選用
      參數 `target_column`，有給時核對機率欄類別集合等於
      `TARGET_CLASS_DOMAINS[target_column]` 的 token 集合。
  P7  `select_best_specialist()` 原本 `target_column` 有預設值
      `"target_up_down"`——審查方實測：用 TB 型態資料（`y_true` 含
      `-1/0/1`）呼叫但不傳 `target_column`，不報錯，`labels=[0,1]`
      靜默忽略 `-1` 類（實測第一名 `macro_f1` 0.750，顯式傳 TB 得
      0.722，兩者不同代表預設值把一個必須明講的選擇藏起來了）。修法：
      `target_column` 改為必填無預設；新增值域檢查，`y_true`／`y_pred`
      的值集合須 ⊆ `TARGET_CLASS_DOMAINS[target_column]`，不符即
      `SelectionSourceError`。

================================================================================
第三輪補件（PO 2026-09-15 複核 `9f86b88` 的 OOF／報告腳本後，回答「對齊
邏輯重複是風險」時要求的契約小擴張）
================================================================================
  P8  `build_meta_learner_input()` 回傳的乾淨矩陣 `reset_index(drop=True)`
      後，呼叫端無法知道哪些原始列被保留——下游若需要對齊其他欄（例如
      真實標籤 y），只能自己重算一次相同的兩層遮罩（segment＋NaN），
      這是重複邏輯，且「長度相等」不保證「同一批列」（兩次獨立計算若
      因欄位選取順序或條件寫法有一絲落差，會產生對不上但長度剛好相同
      的假陽性）。新增選用參數 `return_retained_index: bool = False`，
      `True` 時額外回傳一個 `pd.Index`——排除違規列之前、`oof_df` 原始
      索引標籤中真正保留下來的那些，供呼叫端以 `oof_df.loc[retained_index,
      其他欄]` 精確取值，不需重算遮罩。預設 `False` 維持既有呼叫端
      （T1／T11／`MetaLearnerTrainingSegmentTests`）零改動的 2-tuple
      回傳。
"""
import unittest
import warnings

import numpy as np
import pandas as pd


class RegimeColumnCompletenessTests(unittest.TestCase):
    """P1：`build_meta_learner_input()` 要求 `META_REGIME_FEATURE_COLS`
    全部存在，不是「有就用、沒有就跳過」。"""

    def _df_missing_regime_col(self):
        n = 3
        return pd.DataFrame({
            "stock_id": ["2330"] * n,
            "trade_date": pd.date_range("2024-01-02", periods=n),
            "lr_A_p0": [0.1, 0.2, 0.3], "lr_A_p1": [0.9, 0.8, 0.7],
            "rf_A_p0": [0.15, 0.25, 0.35], "rf_A_p1": [0.85, 0.75, 0.65],
            "lgbm_A_p0": [0.2, 0.3, 0.4], "lgbm_A_p1": [0.8, 0.7, 0.6],
            "xgb_A_p0": [0.25, 0.35, 0.45], "xgb_A_p1": [0.75, 0.65, 0.55],
            "split_segment": ["meta_train"] * n,
            # 刻意只給 volatility_20d，缺 ma20_bias_ratio
            "volatility_20d": [0.1, 0.2, 0.3],
        })

    def test_missing_regime_column_rejected(self):
        """P1・known-FAIL：現況（修正前）回傳 9 欄矩陣，不拋例外。"""
        from src.ml.stacking import MetaInputContractError, build_meta_learner_input

        df = self._df_missing_regime_col()
        with self.assertRaises(MetaInputContractError):
            build_meta_learner_input(df)


class ProbabilityColumnCompletenessTests(unittest.TestCase):
    """P2：機率欄必須恰為 4 模型 × 該 target 類別數，缺一欄即拒絕。"""

    def test_missing_one_model_class_column_rejected(self):
        """P2・known-FAIL：`xgb_A_p1` 缺席，現況回傳 9 欄矩陣，不拋例外。"""
        from src.ml.stacking import MetaInputContractError, build_meta_learner_input

        n = 2
        df = pd.DataFrame({
            "stock_id": ["2330"] * n,
            "trade_date": pd.date_range("2024-01-02", periods=n),
            "lr_A_p0": [0.1, 0.2], "lr_A_p1": [0.9, 0.8],
            "rf_A_p0": [0.15, 0.25], "rf_A_p1": [0.85, 0.75],
            "lgbm_A_p0": [0.2, 0.3], "lgbm_A_p1": [0.8, 0.7],
            "xgb_A_p0": [0.25, 0.35],  # 缺 xgb_A_p1
            "split_segment": ["meta_train"] * n,
            "volatility_20d": [0.1, 0.2], "ma20_bias_ratio": [0.01, 0.02],
        })
        with self.assertRaises(MetaInputContractError):
            build_meta_learner_input(df)


class AssembleOofMatrixDuplicateKeyTests(unittest.TestCase):
    """P3：`assemble_oof_matrix()` 同一 `(model, stock_id, trade_date)`
    出現兩筆須拒絕，不得靜默覆寫。"""

    def test_duplicate_model_stock_date_key_rejected(self):
        """P3・known-FAIL：現況後者靜默覆寫前者，不拋例外。"""
        from src.ml.stacking import MetaInputContractError, assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.4, 0.6]]), "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        # 對 lr 再補一筆同樣的 (stock_id, trade_date)，模擬折邊界重疊
        fold_results.append(
            {"model_name": "lr", "arm": "A", "fold_id": 1,
             "stock_id": ["2330"], "trade_date": [pd.Timestamp("2024-01-02")],
             "y_proba": np.array([[0.1, 0.9]]), "proba_classes": [0, 1]})

        with self.assertRaises(MetaInputContractError):
            assemble_oof_matrix(fold_results, target_column="target_up_down")


class AssembleOofMatrixSequenceLengthTests(unittest.TestCase):
    """P4：一筆紀錄的 `stock_id`／`trade_date`／`y_proba` 列數必須一致，
    不得靜默截斷（`CLAUDE.md` §6 字面案例）。"""

    def test_mismatched_sequence_lengths_rejected(self):
        """P4・known-FAIL：現況 `zip()` 靜默截斷成一列，不拋例外。"""
        from src.ml.stacking import MetaInputContractError, assemble_oof_matrix

        fold_results = [
            {"model_name": m, "arm": "A", "fold_id": 0,
             "stock_id": ["2330", "2454"],  # 兩個 stock_id
             "trade_date": [pd.Timestamp("2024-01-02")],  # 只有一個 trade_date
             "y_proba": np.array([[0.4, 0.6]]),  # 只有一列
             "proba_classes": [0, 1]}
            for m in ("lr", "rf", "lgbm", "xgb")
        ]
        with self.assertRaises(MetaInputContractError):
            assemble_oof_matrix(fold_results, target_column="target_up_down")


class SelectBestSpecialistModelCompletenessTests(unittest.TestCase):
    """P5：`select_best_specialist()` 的模型集合必須等於
    `EXPECTED_MODEL_NAMES`，缺一組即拒絕。"""

    def test_incomplete_model_set_rejected(self):
        """P5・known-FAIL：只給 3 個模型，現況回傳三列排名，不拋例外。"""
        from src.ml.stacking import SelectionSourceError, select_best_specialist

        rng = np.random.RandomState(9)
        n_per_model = 6
        rows = []
        for model in ("lr", "rf", "lgbm"):  # 缺 xgb
            rows.append(pd.DataFrame({
                "model_name": [model] * n_per_model,
                "y_true": rng.choice([0, 1], size=n_per_model),
                "y_pred": rng.choice([0, 1], size=n_per_model),
                "split_segment": ["meta_train"] * n_per_model,
            }))
        df = pd.concat(rows, ignore_index=True)

        with self.assertRaises(SelectionSourceError):
            select_best_specialist(df, target_column="target_up_down")


class SelectBestSpecialistFixedLabelsTests(unittest.TestCase):
    """審查方複核追加（非探針，正確性缺口）：`f1_score()` 須依
    `target_column` 對應的 `TARGET_CLASS_DOMAINS` 傳固定 `labels=`，
    不能讓 sklearn 用預設（只看 `y_true`／`y_pred` 聯集）決定要平均哪些
    類別——否則某模型段內若剛好沒有某類別的真實列，macro 分母會跟其他
    模型不同，排名不可比（比照 `UG-G3-SB3` 洩漏診斷「固定基準才可比」
    的教訓）。"""

    def test_missing_true_class_still_counted_with_fixed_labels(self):
        """known-FAIL：`lr` 的 Meta-Train 段只出現 `{-1, 1}`（沒有
        Timeout `0` 的真實列）。若不傳固定 `labels=[-1,0,1]`，sklearn
        預設只平均 `{-1,1}` 兩類；固定後必須把類別 `0`（precision/recall
        皆為 0）也計入 macro 分母，數值因此低於未固定版本。"""
        from src.ml.stacking import select_best_specialist

        lr_rows = pd.DataFrame({
            "model_name": ["lr"] * 3,
            "y_true": [-1, 1, -1],
            "y_pred": [-1, 1, 1],
            "split_segment": ["meta_train"] * 3,
        })
        # 其餘三模型三類皆有、預測完全正確，只作為「湊滿 4 組」的填充
        other_rows = []
        for model in ("rf", "lgbm", "xgb"):
            other_rows.append(pd.DataFrame({
                "model_name": [model] * 3,
                "y_true": [-1, 0, 1],
                "y_pred": [-1, 0, 1],
                "split_segment": ["meta_train"] * 3,
            }))
        df = pd.concat([lr_rows] + other_rows, ignore_index=True)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, ranking_df = select_best_specialist(df, target_column="target_triple_barrier")

            from sklearn.metrics import f1_score as sk_f1_score
            expected_fixed = sk_f1_score(
                lr_rows["y_true"], lr_rows["y_pred"], labels=[-1, 0, 1], average="macro")
            unfixed_would_be = sk_f1_score(
                lr_rows["y_true"], lr_rows["y_pred"], average="macro")

        lr_score = ranking_df.loc[ranking_df["model_name"] == "lr", "macro_f1"].iloc[0]
        self.assertAlmostEqual(lr_score, expected_fixed, places=6)
        self.assertNotAlmostEqual(lr_score, unfixed_would_be, places=6,
                                   msg="固定 labels 後的分數不應等於未固定版本——"
                                       "若相等，代表 labels= 沒有真的被傳入")


class ProbabilityColumnMatchesTargetDomainTests(unittest.TestCase):
    """P6：`build_meta_learner_input()` 的 `target_column` 選用參數——
    四個模型**一致地**缺同一類別欄時，跨模型一致性檢查測不出來，需額外
    核對真正的 target 類別定義域。"""

    def _df_uniformly_missing_class_1(self):
        """四個模型都只有 p0，一致缺 p1——模擬某個上游環節（例如 OOF
        腳本的類別欄位生成邏輯本身有誤）系統性漏掉了同一個類別，而非
        個別模型偶發缺欄。"""
        from src.ml.baseline_models import META_REGIME_FEATURE_COLS

        n = 2
        data = {
            "stock_id": ["2330"] * n,
            "trade_date": pd.date_range("2024-01-02", periods=n),
            "lr_A_p0": [0.1, 0.2], "rf_A_p0": [0.15, 0.25],
            "lgbm_A_p0": [0.2, 0.3], "xgb_A_p0": [0.25, 0.35],
            "split_segment": ["meta_train"] * n,
        }
        for c in META_REGIME_FEATURE_COLS:
            data[c] = np.linspace(0, 1, n)
        return pd.DataFrame(data)

    def test_uniform_missing_class_undetectable_without_target_column(self):
        """P6・正向案例（訂正前行為）：不傳 `target_column` 時，四個模型
        彼此一致（都只有 p0），跨模型一致性檢查本身不會抓到，函式正常
        回傳——這正是 P6 要補的缺口，本測試確認「不傳參數」時的既有行為
        不受本次修法影響（向後相容）。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._df_uniformly_missing_class_1()
        matrix, _ = build_meta_learner_input(df)  # 不傳 target_column
        self.assertIn("lr_A_p0", matrix.columns)

    def test_uniform_missing_class_rejected_with_target_column(self):
        """P6・known-FAIL：傳入 `target_column="target_up_down"`
        （定義域 `{0,1}`，應有 p0／p1 兩欄）後，必須偵測到機率欄類別集合
        `{0}` 與定義域不符，拒絕執行。"""
        from src.ml.stacking import MetaInputContractError, build_meta_learner_input

        df = self._df_uniformly_missing_class_1()
        with self.assertRaises(MetaInputContractError):
            build_meta_learner_input(df, target_column="target_up_down")


class SelectBestSpecialistRequiresTargetColumnTests(unittest.TestCase):
    """P7：`target_column` 改為必填，且核對 `y_true`／`y_pred` 值域。"""

    def _four_model_df(self, y_true, y_pred):
        rows = []
        for model in ("lr", "rf", "lgbm", "xgb"):
            rows.append(pd.DataFrame({
                "model_name": [model] * len(y_true),
                "y_true": y_true,
                "y_pred": y_pred,
                "split_segment": ["meta_train"] * len(y_true),
            }))
        return pd.concat(rows, ignore_index=True)

    def test_missing_target_column_raises_type_error(self):
        """P7・known-FAIL：不傳 `target_column`（訂正前的預設值已移除）
        必須拋 `TypeError`，不得靜默套用任何預設定義域。"""
        from src.ml.stacking import select_best_specialist

        df = self._four_model_df([0, 1, 0, 1], [0, 1, 1, 0])
        with self.assertRaises(TypeError):
            select_best_specialist(df)

    def test_out_of_domain_values_rejected(self):
        """P7・known-FAIL（審查方原始實測案例的紅測化）：TB 型態資料
        （`y_true` 含 `-1`）配 `target_column="target_up_down"`
        （定義域 `{0,1}`，不含 `-1`）必須拒絕，不得靜默把 `-1` 排除在
        macro 平均之外算出一個看似合理的分數。"""
        from src.ml.stacking import SelectionSourceError, select_best_specialist

        df = self._four_model_df([-1, 0, 1, -1], [-1, 0, 1, 0])
        with self.assertRaises(SelectionSourceError):
            select_best_specialist(df, target_column="target_up_down")

    def test_in_domain_values_accepted(self):
        """P7・正向案例：`y_true`／`y_pred` 值域落在宣告的 `target_column`
        定義域內時，正常回傳。"""
        from src.ml.stacking import select_best_specialist

        df = self._four_model_df([-1, 0, 1, -1], [-1, 0, 1, 0])
        best_model, ranking_df = select_best_specialist(
            df, target_column="target_triple_barrier")
        self.assertIsInstance(best_model, str)
        self.assertEqual(len(ranking_df), 4)


class BuildMetaLearnerInputRetainedIndexTests(unittest.TestCase):
    """P8：`return_retained_index=True` 時回傳三元組，第三個元素為
    `oof_df` 原始索引標籤中真正保留下來的那些，供呼叫端精確對齊其他欄
    （例如真實標籤），不需重算遮罩。

    **實作階段發現並訂正的夾具錯誤**：`_oof_df_with_custom_index()`
    原本把 `rf_A_p0` 的 `NaN` 放在**位置** 3（對應原始標籤 40），但
    docstring／變數命名意圖是標籤 30——`GREEN` 驗證時斷言失敗才發現
    「位置」與「標籤」被混淆。已訂正為位置 2（對應標籤 30）。實作本身
    沒有問題，是夾具資料構造錯誤（與 `NanExclusionInMetaLearnerInputTests`
    先前踩過的同一類坑）。"""

    def _oof_df_with_custom_index(self):
        from src.ml.baseline_models import META_REGIME_FEATURE_COLS

        n = 5
        data = {
            "lr_A_p0": [0.1, 0.2, 0.3, 0.4, 0.5],
            "lr_A_p1": [0.9, 0.8, 0.7, 0.6, 0.5],
            "rf_A_p0": [0.15, 0.25, np.nan, 0.45, 0.55],  # 位置 2（原始標籤 30）含 NaN
            "rf_A_p1": [0.85, 0.75, 0.65, 0.6, 0.45],
            "lgbm_A_p0": [0.2, 0.3, 0.4, 0.5, 0.6],
            "lgbm_A_p1": [0.8, 0.7, 0.6, 0.5, 0.4],
            "xgb_A_p0": [0.25, 0.35, 0.45, 0.55, 0.65],
            "xgb_A_p1": [0.75, 0.65, 0.55, 0.45, 0.35],
            "split_segment": ["meta_train"] * n,
        }
        for c in META_REGIME_FEATURE_COLS:
            data[c] = np.linspace(0, 1, n)
        # 刻意用非預設（非 0..n-1 連續）的原始索引標籤，模擬真實情境
        # （merge 之後的 DataFrame 索引不一定是乾淨的 RangeIndex）。
        df = pd.DataFrame(data)
        df.index = [10, 20, 30, 40, 50]
        return df

    def test_default_returns_two_tuple_unchanged(self):
        """既有呼叫端（不傳此參數）維持 2-tuple 回傳，零改動。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df_with_custom_index()
        result = build_meta_learner_input(df)
        self.assertEqual(len(result), 2)

    def test_return_retained_index_gives_three_tuple(self):
        """known-FAIL（訂正前）：`return_retained_index=True` 時現況仍
        只回傳 2-tuple，解包成三個變數會拋 `ValueError`。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df_with_custom_index()
        matrix, exclusion_counts, retained_index = build_meta_learner_input(
            df, return_retained_index=True)
        self.assertEqual(len(matrix), len(retained_index))

    def test_retained_index_excludes_nan_row_and_matches_original_labels(self):
        """索引標籤 30 的列（`rf_A_p0` 為 NaN）必須被排除在
        `retained_index` 之外；其餘四個原始標籤（10/20/40/50）皆須保留，
        且可直接用來對齊 `oof_df` 的其他欄（例如此處驗證用的
        `lr_A_p0` 原始值）。"""
        from src.ml.stacking import build_meta_learner_input

        df = self._oof_df_with_custom_index()
        matrix, _, retained_index = build_meta_learner_input(
            df, return_retained_index=True)

        self.assertNotIn(30, retained_index.tolist())
        self.assertEqual(sorted(retained_index.tolist()), [10, 20, 40, 50])
        # 用 retained_index 對齊回原始欄，值須與原始 df 完全相符
        # （精確對齊性驗證，不只是列數相符）。
        aligned_lr_p0 = df.loc[retained_index, "lr_A_p0"].to_numpy()
        np.testing.assert_array_equal(aligned_lr_p0, matrix["lr_A_p0"].to_numpy())


if __name__ == "__main__":
    unittest.main()
