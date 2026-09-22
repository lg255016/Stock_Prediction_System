# -*- coding: utf-8 -*-
"""`UG-G3-SB4` OOF 產生腳本與段級報告腳本的測試（PO 2026-09-15 授權進入
腳本階段）。

只測腳本自身的守衛與輔助函式邏輯（sha256 比對、值域檢查、格式轉換、
X/y 對齊），**不重複測試** `src/ml/stacking.py` 已有測試覆蓋的核心邏輯
（`assemble_oof_matrix`／`apply_second_stage_purge`／
`build_meta_learner_input`／`select_best_specialist` 本身的行為，見
`tests/test_ug_g3_sb4_stacking_red.py`／`tests/test_ug_g3_sb4_stacking_contracts.py`）。

`NoDatabaseImportTests` 比照 `UG-G3-SB3`
`ug_g3_sb3_specialist_report.py` 的既有慣例：直接掃描兩支腳本原始碼
字面，確認未匯入任何資料庫驅動程式或連線環境變數名稱——結構上保證
唯讀、零 DB 接觸。

本檔涵蓋兩支腳本的合成資料測試（不觸碰真實凍結面板或 Database_Backups
掛載路徑），單折／多折探測的真實面板驗證已於實作階段人工執行並記錄於
送審報告（`VERIFIED THIS SESSION`），不在本檔重複。

================================================================================
第二輪補件（PO 2026-09-15 複核 `9f86b88` 後，審查方對真實凍結面板重新
計算發現三個正確性問題）
================================================================================
1. `EXPECTED_SEGMENT_COUNTS`／`EXPECTED_PURGE_COUNTS` 原本是面板折測試窗
   的**原始**列數，不是 `prepare_fold_data()` 規則 (a)(b) 之後的**保留**
   列數——OOF 矩陣只含保留列，兩者不同。審查方對凍結面板重算（PM 已
   獨立重現，數字相符）：`target_up_down` meta_train 保留 80,968／
   meta_eval 保留 17,949／purged 150；`target_triple_barrier` meta_train
   保留 74,394／meta_eval 保留 16,730／purged **680**（非原本錯誤的
   750）。
2. 訓練迴圈原本沒有真的呼叫 `iter_oof_folds()`，而是手動重寫了一份
   幾乎相同的 Holdout 排除邏輯（`test_start >= HOLDOUT_START_DATE` 才
   `continue`）——這正是紅測 `test_straddling_fold_is_excluded_entirely`
   要擋的半折放行規則所在的函式，繞過它等於讓那條紅測失去對本腳本的
   保護力（只是真實資料剛好沒有跨界折，沒有暴露這個落差）。
3. `build_long_format_for_selection()` 的 `argmax` 遇到 `NaN`（缺席類別
   欄）會回傳錯誤的類別索引（`np.argmax` 對含 NaN 的列有未定義／誤導性
   行為）——該模型該列須整列排除，不得帶著錯誤的 `y_pred` 進入
   `select_best_specialist()`。
"""
import importlib
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "verify"


def _load_module(name: str):
    import sys

    sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module(name)


class NoDatabaseImportTests(unittest.TestCase):
    """兩支腳本結構上不得匯入任何資料庫驅動程式或連線環境變數名稱
    （唯讀保證，字面掃描原始碼，不依賴實際 import 是否成功）。"""

    FORBIDDEN_TOKENS = ("psycopg2", "DB_HOST", "DB_PORT", "DB_NAME", "sqlalchemy")

    def _assert_source_clean(self, filename: str):
        source = (SCRIPTS_DIR / filename).read_text(encoding="utf-8")
        found = [tok for tok in self.FORBIDDEN_TOKENS if tok in source]
        self.assertEqual(found, [], f"{filename} 不應提及資料庫相關名稱：{found}")

    def test_oof_generation_script_has_no_database_references(self):
        self._assert_source_clean("ug_g3_sb4_oof_generation.py")

    def test_meta_learner_report_script_has_no_database_references(self):
        self._assert_source_clean("ug_g3_sb4_meta_learner_report.py")


class OofGenerationSha256GuardTests(unittest.TestCase):
    """`verify_panel_sha256()`：parquet 實際內容與登記值不符即拒絕。"""

    def test_mismatched_sha256_rejected(self, ):
        mod = _load_module("ug_g3_sb4_oof_generation")
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            pd.DataFrame({"a": [1, 2, 3]}).to_parquet(f.name)
            with self.assertRaises(mod.OofGenerationError):
                mod.verify_panel_sha256(Path(f.name), "target_up_down")

    def test_matching_sha256_accepted(self):
        mod = _load_module("ug_g3_sb4_oof_generation")
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            pd.DataFrame({"a": [1, 2, 3]}).to_parquet(f.name)
            actual = mod.compute_file_sha256(Path(f.name))
            mod.PANEL_SHA256["target_up_down"], saved = actual, mod.PANEL_SHA256["target_up_down"]
            try:
                result = mod.verify_panel_sha256(Path(f.name), "target_up_down")
                self.assertEqual(result, actual)
            finally:
                mod.PANEL_SHA256["target_up_down"] = saved


class MetaLearnerReportSha256GuardTests(unittest.TestCase):
    """`verify_oof_sha256()`：OOF parquet 實際內容與 OOF 產生階段記載值
    不符即拒絕。"""

    def test_mismatched_sha256_rejected(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            pd.DataFrame({"a": [1, 2, 3]}).to_parquet(f.name)
            oof_path = Path(f.name)

        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"oof_parquet_sha256": "0" * 64}, f)
            evidence_path = Path(f.name)

        with self.assertRaises(mod.MetaLearnerReportError):
            mod.verify_oof_sha256(oof_path, evidence_path)


class SegmentValueDomainGuardTests(unittest.TestCase):
    """`assert_segment_value_domain()`：`split_segment` 值域外的值須拒絕。"""

    def test_unknown_segment_value_rejected(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = pd.DataFrame({"split_segment": ["meta_train", "holdout", "meta_eval"]})
        with self.assertRaises(mod.MetaLearnerReportError):
            mod.assert_segment_value_domain(df)

    def test_valid_values_accepted(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = pd.DataFrame({"split_segment": ["meta_train", "meta_eval", "purged"]})
        mod.assert_segment_value_domain(df)  # 不拋例外即通過


class RowCountRegressionGuardTests(unittest.TestCase):
    """`assert_row_counts_match_generation()`：三段列數與 OOF 產生階段
    記載值不符即拒絕（防禦性重驗）。"""

    def test_mismatched_counts_rejected(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = pd.DataFrame({"split_segment": ["meta_train"] * 3 + ["meta_eval"] * 2})
        gen_evidence = {"row_counts": {"total": 5, "meta_train": 999, "meta_eval": 2, "purged": 0}}
        with self.assertRaises(mod.MetaLearnerReportError):
            mod.assert_row_counts_match_generation(df, gen_evidence)

    def test_matching_counts_accepted(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = pd.DataFrame({"split_segment": ["meta_train"] * 3 + ["meta_eval"] * 2})
        gen_evidence = {"row_counts": {"total": 5, "meta_train": 3, "meta_eval": 2, "purged": 0}}
        mod.assert_row_counts_match_generation(df, gen_evidence)  # 不拋例外即通過


class ClassTokenLocalConsistencyTests(unittest.TestCase):
    """`_class_token_local()` 必須與 `src.ml.stacking._class_token()`
    的規則一致（本地鏡射版本的存在理由就是為了跟它同步，若不一致，
    組出來的欄名會找不到對應的 OOF 欄）。"""

    def test_matches_stacking_private_class_token_for_up_down(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.ml.stacking import _class_token

        mod = _load_module("ug_g3_sb4_meta_learner_report")
        for cls in (0, 1):
            self.assertEqual(
                mod._class_token_local("target_up_down", cls),
                _class_token("target_up_down", cls))

    def test_matches_stacking_private_class_token_for_triple_barrier(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.ml.stacking import _class_token

        mod = _load_module("ug_g3_sb4_meta_learner_report")
        for cls in (-1, 0, 1):
            self.assertEqual(
                mod._class_token_local("target_triple_barrier", cls),
                _class_token("target_triple_barrier", cls))


class BuildLongFormatForSelectionTests(unittest.TestCase):
    """`build_long_format_for_selection()`：寬格式 → 長格式轉換正確性
    （`y_pred` 由 `argmax` 反推類別）。"""

    def _synthetic_oof(self):
        # 2 列，4 模型皆有 p0/p1，split_segment 皆 meta_train。
        data = {
            "target_up_down": [0, 1],
            "split_segment": ["meta_train", "meta_train"],
        }
        for model in ("lr", "rf", "lgbm", "xgb"):
            data[f"{model}_A_p0"] = [0.9, 0.2]  # 列 0 應判 0，列 1 應判 1
            data[f"{model}_A_p1"] = [0.1, 0.8]
        return pd.DataFrame(data)

    def test_argmax_prediction_matches_higher_probability_class(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = self._synthetic_oof()
        long_df = mod.build_long_format_for_selection(df, "target_up_down", "meta_train")

        self.assertEqual(len(long_df), 4 * 2, "4 模型 × 2 列")
        for model in ("lr", "rf", "lgbm", "xgb"):
            rows = long_df[long_df["model_name"] == model].reset_index(drop=True)
            self.assertEqual(rows.loc[0, "y_pred"], 0)
            self.assertEqual(rows.loc[1, "y_pred"], 1)
            self.assertEqual(rows.loc[0, "y_true"], 0)
            self.assertEqual(rows.loc[1, "y_true"], 1)


class ExpectedConstantsCorrectnessTests(unittest.TestCase):
    """審查方對凍結面板重算（PM 已獨立重現，數字相符）：
    `EXPECTED_SEGMENT_COUNTS`／`EXPECTED_PURGE_COUNTS` 必須是
    `prepare_fold_data()` 規則 (a)(b) 之後的**保留**列數，不是折測試窗的
    原始列數。known-FAIL（訂正前）：`target_triple_barrier` 的 purge
    數原本錯寫為 750（那是原始列數上的迴歸基準），保留列上的正確值是
    680。"""

    def test_segment_counts_are_per_target_and_match_retained_rows(self):
        mod = _load_module("ug_g3_sb4_oof_generation")

        self.assertEqual(
            mod.EXPECTED_SEGMENT_COUNTS["target_up_down"],
            {"meta_train": 80968, "meta_eval": 17949})
        self.assertEqual(
            mod.EXPECTED_SEGMENT_COUNTS["target_triple_barrier"],
            {"meta_train": 74394, "meta_eval": 16730})

    def test_purge_counts_match_retained_rows_not_raw_test_window_rows(self):
        mod = _load_module("ug_g3_sb4_oof_generation")

        self.assertEqual(mod.EXPECTED_PURGE_COUNTS["target_up_down"], 150)
        self.assertEqual(
            mod.EXPECTED_PURGE_COUNTS["target_triple_barrier"], 680,
            "TB 的 purge 數是保留列上算的 680，不是原始列數上的 750")


class IterOofFoldsActuallyUsedTests(unittest.TestCase):
    """known-FAIL（訂正前）：`generate_oof_for_target()` 手動重寫了一份
    Holdout 排除邏輯（`test_start >= HOLDOUT_START_DATE` 才 `continue`），
    沒有真的呼叫 `iter_oof_folds()`——結構上繞過了該函式已通過的紅測
    保護（`test_straddling_fold_is_excluded_entirely` 等）。本測試直接
    掃描原始碼字面，確認訓練迴圈的 `for` 陳述式呼叫的是
    `iter_oof_folds(`，且手動重寫的判斷式已移除。"""

    def test_source_calls_iter_oof_folds_in_main_loop(self):
        source = (SCRIPTS_DIR / "ug_g3_sb4_oof_generation.py").read_text(encoding="utf-8")
        self.assertIn(
            "for train_idx, test_idx, fold_meta in iter_oof_folds(",
            source,
            "訓練迴圈必須直接迭代 iter_oof_folds() 的輸出，不得手動重寫"
            "等義的 Holdout 排除邏輯")
        self.assertNotIn(
            "if test_start >= HOLDOUT_START_DATE:",
            source,
            "手動重寫的 Holdout 判斷式必須移除，改用 iter_oof_folds() 本身的過濾")


class BuildLongFormatNaNExclusionTests(unittest.TestCase):
    """known-FAIL（訂正前）：`build_long_format_for_selection()` 對含
    `NaN` 機率欄的列做 `argmax`，會回傳錯誤或未定義的類別索引——該
    (model, 列) 組合必須整列排除，不得帶著錯誤的 `y_pred` 進入
    `select_best_specialist()`。"""

    def _synthetic_oof_with_nan(self):
        data = {
            "target_up_down": [0, 1, 0],
            "split_segment": ["meta_train"] * 3,
        }
        for model in ("lr", "rf", "lgbm", "xgb"):
            data[f"{model}_A_p0"] = [0.9, 0.2, 0.6]
            data[f"{model}_A_p1"] = [0.1, 0.8, 0.4]
        # 列 2 的 rf 模型機率欄整組是 NaN（模擬缺席類別的 OOF 產生結果）。
        data["rf_A_p0"][2] = np.nan
        data["rf_A_p1"][2] = np.nan
        return pd.DataFrame(data)

    def test_nan_row_excluded_for_affected_model_only(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = self._synthetic_oof_with_nan()
        long_df = mod.build_long_format_for_selection(df, "target_up_down", "meta_train")

        rf_rows = long_df[long_df["model_name"] == "rf"]
        self.assertEqual(len(rf_rows), 2, "rf 模型應排除含 NaN 的第 3 列，只剩 2 列")

        lr_rows = long_df[long_df["model_name"] == "lr"]
        self.assertEqual(len(lr_rows), 3, "lr 模型不受 rf 的 NaN 影響，維持 3 列")

    def test_exclusion_count_reported_per_model(self):
        mod = _load_module("ug_g3_sb4_meta_learner_report")

        df = self._synthetic_oof_with_nan()
        _, exclusion_counts = mod.build_long_format_for_selection(
            df, "target_up_down", "meta_train", return_exclusion_counts=True)
        self.assertEqual(exclusion_counts.get("rf"), 1)
        self.assertNotIn("lr", exclusion_counts)


if __name__ == "__main__":
    unittest.main()
