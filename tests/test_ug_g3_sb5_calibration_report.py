# -*- coding: utf-8 -*-
"""`UG-G3-SB5` 段級報告腳本（`ug_g3_sb5_calibration_report.py`）的守衛與
純函式測試。全部使用合成資料，不讀取任何真實 OOF parquet（`CLAUDE.md`
§13.4 測試封閉性；真實面板／OOF 只在腳本層讀取，見 `run_report()` 的
`--oof-path` 參數）。"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify" / "ug_g3_sb5_calibration_report.py"
_SPEC = importlib.util.spec_from_file_location("ug_g3_sb5_calibration_report", _SCRIPT_PATH)
report_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(report_mod)


class NoDatabaseImportTests(unittest.TestCase):
    """結構性掃描：本腳本唯讀、不得匯入任何資料庫驅動程式。"""

    def test_source_does_not_import_db_drivers(self):
        source = _SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in ("psycopg2", "sqlalchemy", "import db", "DBWriter"):
            self.assertNotIn(forbidden, source,
                              f"腳本原始碼不得出現 {forbidden!r}（唯讀腳本，結構上不可能連 DB）")


class VerifyOofSha256Tests(unittest.TestCase):
    def test_mismatched_sha256_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            oof_path = Path(tmp) / "oof.parquet"
            pd.DataFrame({"a": [1, 2, 3]}).to_parquet(oof_path)
            evidence_path = Path(tmp) / "evidence.json"
            with open(evidence_path, "w") as f:
                json.dump({"oof_parquet_sha256": "0" * 64}, f)
            with self.assertRaises(report_mod.CalibrationReportError):
                report_mod.verify_oof_sha256(oof_path, evidence_path)

    def test_matching_sha256_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            oof_path = Path(tmp) / "oof.parquet"
            pd.DataFrame({"a": [1, 2, 3]}).to_parquet(oof_path)
            actual_sha256 = report_mod.compute_file_sha256(oof_path)
            evidence_path = Path(tmp) / "evidence.json"
            with open(evidence_path, "w") as f:
                json.dump({"oof_parquet_sha256": actual_sha256, "row_counts": {}}, f)
            sha256, gen_evidence = report_mod.verify_oof_sha256(oof_path, evidence_path)
            self.assertEqual(sha256, actual_sha256)


class SegmentGuardTests(unittest.TestCase):
    def test_bad_segment_value_raises(self):
        df = pd.DataFrame({"split_segment": ["meta_train", "bogus_segment"]})
        with self.assertRaises(report_mod.CalibrationReportError):
            report_mod.assert_segment_value_domain(df)

    def test_valid_segment_values_pass(self):
        df = pd.DataFrame({"split_segment": ["meta_train", "meta_eval", "purged"]})
        report_mod.assert_segment_value_domain(df)  # 不應拋出


class RowCountGuardTests(unittest.TestCase):
    def test_mismatched_row_counts_raises(self):
        df = pd.DataFrame({"split_segment": ["meta_train"] * 3 + ["meta_eval"] * 2})
        gen_evidence = {"row_counts": {"total": 100, "meta_train": 3, "meta_eval": 2, "purged": 0}}
        with self.assertRaises(report_mod.CalibrationReportError):
            report_mod.assert_row_counts_match_generation(df, gen_evidence)

    def test_matching_row_counts_pass(self):
        df = pd.DataFrame({"split_segment": ["meta_train"] * 3 + ["meta_eval"] * 2})
        gen_evidence = {"row_counts": {"total": 5, "meta_train": 3, "meta_eval": 2, "purged": 0}}
        report_mod.assert_row_counts_match_generation(df, gen_evidence)  # 不應拋出


class MatchesSB4ReportGuardTests(unittest.TestCase):
    def test_mismatch_raises(self):
        actual = {"LogisticRegression": 0.5, "RidgeClassifier": 0.4}
        sb4_evidence = {
            "meta_a": {
                "LogisticRegression": {"macro_f1_meta_eval": 0.5},
                "RidgeClassifier": {"macro_f1_meta_eval": 0.999},
            }
        }
        with self.assertRaises(report_mod.CalibrationReportError):
            report_mod.assert_matches_sb4_report(actual, sb4_evidence)

    def test_match_within_tolerance_passes(self):
        actual = {"LogisticRegression": 0.5000000001, "RidgeClassifier": 0.4}
        sb4_evidence = {
            "meta_a": {
                "LogisticRegression": {"macro_f1_meta_eval": 0.5},
                "RidgeClassifier": {"macro_f1_meta_eval": 0.4},
            }
        }
        report_mod.assert_matches_sb4_report(actual, sb4_evidence, tol=1e-9)  # 不應拋出（差值 1e-10）


class MetaEvalFoldGuardTests(unittest.TestCase):
    def test_out_of_range_fold_raises(self):
        fold_id = np.array([27, 28, 33])  # 33 不在 CALIB_FIT_FOLDS/CALIB_EVAL_FOLDS
        with self.assertRaises(report_mod.CalibrationReportError):
            report_mod.assert_meta_eval_folds_expected(fold_id)

    def test_all_valid_folds_pass(self):
        fold_id = np.array([27, 28, 29, 30, 31, 32])
        report_mod.assert_meta_eval_folds_expected(fold_id)  # 不應拋出


class ClassesMatchDomainGuardTests(unittest.TestCase):
    def test_wrong_order_raises(self):
        with self.assertRaises(report_mod.CalibrationReportError):
            report_mod.assert_classes_match_domain(np.array([1, 0]), "target_up_down")

    def test_correct_order_passes(self):
        report_mod.assert_classes_match_domain(np.array([0, 1]), "target_up_down")  # 不應拋出
        report_mod.assert_classes_match_domain(np.array([-1, 0, 1]), "target_triple_barrier")


class NaiveCalibrationProbabilitiesTests(unittest.TestCase):
    def test_binary_matches_manual_sigmoid(self):
        raw = np.array([-2.0, 0.0, 2.0])
        result = report_mod.naive_calibration_probabilities(raw, "target_up_down")
        expected = 1.0 / (1.0 + np.exp(-raw))
        np.testing.assert_allclose(result, expected)

    def test_tb_rows_sum_to_one(self):
        raw = np.array([[1.0, -1.0, 0.5], [0.0, 0.0, 0.0]])
        result = report_mod.naive_calibration_probabilities(raw, "target_triple_barrier")
        np.testing.assert_allclose(result.sum(axis=1), 1.0, atol=1e-9)


class FixedThresholdPredictionsTests(unittest.TestCase):
    def test_binary_threshold_at_half(self):
        probs = np.array([0.3, 0.5, 0.51, 0.7])
        result = report_mod.fixed_threshold_predictions(probs, "target_up_down")
        np.testing.assert_array_equal(result, [0, 1, 1, 1])

    def test_tb_argmax(self):
        probs = np.array([[0.7, 0.2, 0.1], [0.1, 0.1, 0.8]])
        result = report_mod.fixed_threshold_predictions(probs, "target_triple_barrier")
        np.testing.assert_array_equal(result, [-1, 1])


class ToTwoColumnTests(unittest.TestCase):
    def test_shape_and_sum(self):
        p1 = np.array([0.2, 0.8])
        result = report_mod.to_two_column(p1)
        self.assertEqual(result.shape, (2, 2))
        np.testing.assert_allclose(result.sum(axis=1), 1.0)
        np.testing.assert_allclose(result[:, 1], p1)


if __name__ == "__main__":
    unittest.main()
