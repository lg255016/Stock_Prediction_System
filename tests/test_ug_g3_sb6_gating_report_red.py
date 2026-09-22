# -*- coding: utf-8 -*-
"""UG-G3-SB6 報告腳本紅測（RED）——`scripts/verify/ug_g3_sb6_gating_report.py`
的管線函式（`run_report()`／`extract_sb5_reference()`／
`_build_holdout_guard()`／`_select_and_diagnose()`／`_should_write()`／
`_build_dual_curves()`）尚不存在，全部測試預期 `ImportError`／
`AttributeError`。

依審查方複核 GREEN `09bcba9` 時發現的真實缺陷設計（詳見
`doc/upgrade/gates/UG_G3_SB6_GATE_A_PROPOSAL.md` §3.7 與本輪
PO／審查方訊息）：

**`assert_calibrator_matches_sb5()` 比對鍵名訂正**——原設計比對
`auc_calib_fit_raw`，但真實 `UG_G3_SB5_calibration_report_target_triple_barrier.json`
裡這個鍵雖然存在，卻是 `{class: float}` 的巢狀字典（三類 OvR），不是
單一浮點數，直接拿來當浮點數比較在真實資料上會撞到型別錯誤。正確的
比對對象是 `per_class_quality["0"]` 底下逐類別、已是單一浮點數的
`auc_before`／`auc_after`／`platt_slope`／`platt_intercept`，加模型
層級的 `brier_after`。`extract_sb5_reference()` 負責從真實巢狀結構
抽出這五個數字。

比照既有先例：全部測試使用合成資料（`numpy`／`pandas` 手造，或**逐字
仿照**真實 JSON 巢狀結構的合成 dict），不讀取任何真實 OOF parquet
或真實 `UG-G3-SB5` 證據檔（`CLAUDE.md` §13.4 測試封閉性）。
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd


class VerifyOofSha256Tests(unittest.TestCase):
    """乾跑（2026-09-16）實測發現：`verify_oof_sha256()` 讀
    `gen_evidence["oof_sha256"]`，但真實 `UG-G3-SB4` 產生腳本
    （`ug_g3_sb4_oof_generation.py::run_generation()`）寫入的鍵名是
    `oof_parquet_sha256`——`UG-G3-SB5` 報告腳本的同名函式（`verify_oof_sha256()`
    第 153 行）讀的正是這個鍵，`UG-G3-SB6` 宣稱『比照』卻沒有照抄。舊有
    紅測只用 `mock.patch.object(report_module, "verify_oof_sha256", ...)`
    把整個函式換成樁函式，結構上不可能測到函式本體的鍵名——本類別
    是第一個用**真實形狀**的 evidence fixture 呼叫它本體的測試。"""

    def _make_real_shaped_evidence(self, oof_sha256: str) -> dict:
        """鍵名逐字仿真實 `UG_G3_SB4_oof_generation_target_triple_barrier.json`
        頂層結構（PM 乾跑時讀取真實檔案核對過）。"""
        return {
            "target": "target_triple_barrier",
            "panel_path": "fake_panel.parquet",
            "panel_sha256": "0" * 64,
            "oof_parquet_path": "fake_oof.parquet",
            "oof_parquet_sha256": oof_sha256,
            "oof_row_count": 8255,
            "row_counts": {"total": 8255, "meta_train": 6000, "meta_eval": 2255, "purged": 0},
        }

    def test_reads_oof_parquet_sha256_key(self):
        from scripts.verify.ug_g3_sb6_gating_report import verify_oof_sha256

        with tempfile.TemporaryDirectory() as tmpdir:
            oof_path = Path(tmpdir) / "fake_oof.parquet"
            oof_path.write_bytes(b"not a real parquet file, just bytes to hash")
            expected_sha = hashlib.sha256(oof_path.read_bytes()).hexdigest()

            evidence_path = Path(tmpdir) / "evidence.json"
            evidence = self._make_real_shaped_evidence(expected_sha)
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            actual_sha, gen_evidence = verify_oof_sha256(oof_path, evidence_path)

        self.assertEqual(actual_sha, expected_sha)
        self.assertEqual(gen_evidence, evidence)

    def test_sha_mismatch_raises(self):
        from scripts.verify.ug_g3_sb6_gating_report import verify_oof_sha256
        from src.ml.gating import GatingContractError

        with tempfile.TemporaryDirectory() as tmpdir:
            oof_path = Path(tmpdir) / "fake_oof.parquet"
            oof_path.write_bytes(b"not a real parquet file, just bytes to hash")
            real_sha = hashlib.sha256(oof_path.read_bytes()).hexdigest()
            distorted_sha = ("0" if real_sha[0] != "0" else "1") + real_sha[1:]
            self.assertNotEqual(distorted_sha, real_sha)

            evidence_path = Path(tmpdir) / "evidence.json"
            evidence_path.write_text(
                json.dumps(self._make_real_shaped_evidence(distorted_sha)), encoding="utf-8")

            with self.assertRaises(GatingContractError):
                verify_oof_sha256(oof_path, evidence_path)

    def test_legacy_key_name_not_accepted(self):
        """evidence 只有舊鍵名 `oof_sha256`、沒有真實鍵名
        `oof_parquet_sha256` 時必須拋錯——不得為了相容偷偷兩個鍵都接受，
        那會把這次的錯誤藏起來。"""
        from scripts.verify.ug_g3_sb6_gating_report import verify_oof_sha256

        with tempfile.TemporaryDirectory() as tmpdir:
            oof_path = Path(tmpdir) / "fake_oof.parquet"
            oof_path.write_bytes(b"not a real parquet file, just bytes to hash")
            real_sha = hashlib.sha256(oof_path.read_bytes()).hexdigest()

            evidence_path = Path(tmpdir) / "evidence.json"
            legacy_evidence = {"target": "target_triple_barrier", "oof_sha256": real_sha}
            evidence_path.write_text(json.dumps(legacy_evidence), encoding="utf-8")

            with self.assertRaises(KeyError):
                verify_oof_sha256(oof_path, evidence_path)


class TargetColumnEntryGuardTests(unittest.TestCase):
    """`run_report()` 必須把 `_validate_target_column()` 放在第一行，
    任何檔案存取之前——用不存在的路徑證明順序對，而不是「反正檔案
    讀不到所以也測不出驗證有沒有先發生」。"""

    def test_run_report_rejects_up_down_before_file_access(self):
        from scripts.verify.ug_g3_sb6_gating_report import run_report
        from src.ml.gating import GatingTargetColumnError
        with self.assertRaises(GatingTargetColumnError):
            run_report(
                oof_path=Path("/nonexistent/does_not_exist.parquet"),
                oof_generation_evidence_path=Path("/nonexistent/evidence.json"),
                sb5_reference_path=Path("/nonexistent/sb5.json"),
                target_column="target_up_down",
            )

    def test_run_report_accepts_triple_barrier_and_proceeds_to_file_access(self):
        """正控制：`target_triple_barrier` 不觸發
        `GatingTargetColumnError`——驗證通過後才因檔案不存在而拋出
        別的例外，證明驗證確實發生在管線最前面，不是被跳過。"""
        from scripts.verify.ug_g3_sb6_gating_report import run_report
        from src.ml.gating import GatingTargetColumnError
        with self.assertRaises(Exception) as ctx:
            run_report(
                oof_path=Path("/nonexistent/does_not_exist.parquet"),
                oof_generation_evidence_path=Path("/nonexistent/evidence.json"),
                sb5_reference_path=Path("/nonexistent/sb5.json"),
                target_column="target_triple_barrier",
            )
        self.assertNotIsInstance(ctx.exception, GatingTargetColumnError)


class ExtractSb5ReferenceTests(unittest.TestCase):
    """對應複核意見「修法 2」：`extract_sb5_reference()` 逐字仿照真實
    `UG_G3_SB5_calibration_report_target_triple_barrier.json` 的巢狀
    結構（`calibration_results` → `<model>__sigmoid` →
    `per_class_quality` → `"0"`，類別鍵為字串）。"""

    def _make_sb5_json_fixture(self):
        """`auc_calib_fit_raw`（頂層，PO 2026-09-15 要求新增：Calib-fit
        段的原始 AUC，逐類別字典）數字取自真實
        `UG_G3_SB5_calibration_report_target_triple_barrier.json`
        （PM 逐位核對過，非杜撰）。"""
        return {
            "calibration_results": {
                "LogisticRegression__sigmoid": {
                    "brier_after": 0.5196138852147298,
                    "auc_calib_fit_raw": {
                        "-1": 0.5430525979340767, "0": 0.8295208545881081, "1": 0.5026993040861157,
                    },
                    "per_class_quality": {
                        "-1": {"auc_before": 0.5478, "auc_after": 0.5478,
                               "platt_slope": 0.0638, "platt_intercept": 0.1264},
                        "0": {"auc_before": 0.9045026037019825, "auc_after": 0.9045026037019825,
                              "platt_slope": 1.216430131756554, "platt_intercept": -0.9222457511653753},
                        "1": {"auc_before": 0.5250, "auc_after": 0.5230,
                              "platt_slope": 0.0001, "platt_intercept": -0.3737},
                    },
                },
                "RidgeClassifier__sigmoid": {
                    "brier_after": 0.5207400880859983,
                    "auc_calib_fit_raw": {
                        "-1": 0.5411518260908037, "0": 0.8382030956009925, "1": 0.5147566607664854,
                    },
                    "per_class_quality": {
                        "-1": {"auc_before": 0.5412, "auc_after": 0.5412,
                               "platt_slope": 1.6284, "platt_intercept": 0.2},
                        "0": {"auc_before": 0.9118679396602606, "auc_after": 0.9118679396602606,
                              "platt_slope": 4.865197115079203, "platt_intercept": 0.86910395727489},
                        "1": {"auc_before": 0.5148, "auc_after": 0.5148,
                               "platt_slope": 0.7411, "platt_intercept": -0.1},
                    },
                },
            },
        }

    def test_extract_sb5_reference_from_real_structure(self):
        from scripts.verify.ug_g3_sb6_gating_report import extract_sb5_reference
        sb5_json = self._make_sb5_json_fixture()
        result = extract_sb5_reference(sb5_json, "LogisticRegression__sigmoid")
        self.assertAlmostEqual(result["brier_after"], 0.5196138852147298)
        self.assertAlmostEqual(result["auc_before"], 0.9045026037019825)
        self.assertAlmostEqual(result["auc_after"], 0.9045026037019825)
        self.assertAlmostEqual(result["platt_slope"], 1.216430131756554)
        self.assertAlmostEqual(result["platt_intercept"], -0.9222457511653753)
        # PO 2026-09-15 要求新增：Calib-fit 段原始 AUC（與上面 auc_before／
        # auc_after 的 Calib-eval 段不同時間段，兩段都比對才能證明擬合
        # 輸入與評估輸出皆相同）
        self.assertAlmostEqual(result["auc_calib_fit_raw_class0"], 0.8295208545881081)

    def test_extract_sb5_reference_ridge(self):
        from scripts.verify.ug_g3_sb6_gating_report import extract_sb5_reference
        sb5_json = self._make_sb5_json_fixture()
        result = extract_sb5_reference(sb5_json, "RidgeClassifier__sigmoid")
        self.assertAlmostEqual(result["brier_after"], 0.5207400880859983)
        self.assertAlmostEqual(result["platt_slope"], 4.865197115079203)
        self.assertAlmostEqual(result["auc_calib_fit_raw_class0"], 0.8382030956009925)

    def test_extract_rejects_missing_model(self):
        from scripts.verify.ug_g3_sb6_gating_report import extract_sb5_reference
        from src.ml.gating import GatingContractError
        sb5_json = self._make_sb5_json_fixture()
        with self.assertRaises(GatingContractError):
            extract_sb5_reference(sb5_json, "NoSuchModel__sigmoid")


class HoldoutGuardFieldsTests(unittest.TestCase):
    def test_holdout_guard_fields_recorded(self):
        from scripts.verify.ug_g3_sb6_gating_report import _build_holdout_guard
        from src.ml.stacking import HOLDOUT_START_DATE
        fold_id = np.array([27, 28, 29, 30, 31, 32])
        trade_date = pd.to_datetime([
            "2025-05-05", "2025-05-06", "2025-05-07",
            "2025-09-01", "2025-09-02", "2025-10-22",
        ])
        guard = _build_holdout_guard(fold_id, trade_date)
        self.assertEqual(guard["fold_id_max"], 32)
        self.assertEqual(guard["trade_date_max"], "2025-10-22")
        self.assertEqual(guard["holdout_start_date"], str(HOLDOUT_START_DATE.date()))


class SelectAndDiagnoseTests(unittest.TestCase):
    """對應複核項目 8：可行區間為空時，不得對不存在的 `θ*` 硬跑
    regime 診斷——現行清單第 10 步直接用 `selected["theta"]`，不可行
    時會 `KeyError`。"""

    def test_infeasible_selection_skips_regime_with_reason(self):
        from scripts.verify.ug_g3_sb6_gating_report import _select_and_diagnose
        curve_rows = [
            {"theta": 0.5, "gate_pct": 0.05, "coverage": 0.95, "precision": 0.10, "lift": 2.0, "recall": 0.30},
        ]
        volatility = np.array([0.1, 0.5, 0.9])
        p0 = np.array([0.2, 0.3, 0.4])
        y = np.array([0, 1, -1])
        result = _select_and_diagnose(curve_rows, base_rate=0.05, volatility=volatility, p0=p0, y_true=y)
        self.assertFalse(result["selected_theta"]["feasible"])
        self.assertIsNone(result["regime_diagnostic"])

    def test_feasible_selection_runs_regime(self):
        """正控制：可行時 `regime_diagnostic` 欄不為 `None`。"""
        from scripts.verify.ug_g3_sb6_gating_report import _select_and_diagnose
        curve_rows = [
            {"theta": 0.1, "gate_pct": 0.20, "coverage": 0.80, "precision": 0.40, "lift": 4.0, "recall": 0.60},
        ]
        n = 10
        volatility = np.concatenate([np.full(n, 0.1), np.full(n, 0.5), np.full(n, 0.9)])
        rng = np.random.RandomState(9)
        p0 = rng.uniform(0, 1, n * 3)
        y = rng.choice([-1, 0, 1], size=n * 3, p=[0.45, 0.1, 0.45])
        result = _select_and_diagnose(curve_rows, base_rate=0.1, volatility=volatility, p0=p0, y_true=y)
        self.assertTrue(result["selected_theta"]["feasible"])
        self.assertIsNotNone(result["regime_diagnostic"])


class WriteGuardTests(unittest.TestCase):
    """對應複核項目 9、10，加一項 script_dirty 拒寫與一項正控制。"""

    def test_write_refused_when_max_rows_set(self):
        from scripts.verify.ug_g3_sb6_gating_report import _should_write
        should_write, reason = _should_write(write_flag=True, max_rows=100, script_dirty=False)
        self.assertFalse(should_write)

    def test_no_write_flag_writes_nothing(self):
        from scripts.verify.ug_g3_sb6_gating_report import _should_write
        should_write, reason = _should_write(write_flag=False, max_rows=None, script_dirty=False)
        self.assertFalse(should_write)

    def test_write_refused_when_script_dirty(self):
        from scripts.verify.ug_g3_sb6_gating_report import _should_write
        should_write, reason = _should_write(write_flag=True, max_rows=None, script_dirty=True)
        self.assertFalse(should_write)

    def test_write_proceeds_when_conditions_met(self):
        """正控制：`--write`、無 `--max-rows`、`script_dirty=False` 同時
        成立才允許寫檔——三項條件的交集，不是任一項就夠。"""
        from scripts.verify.ug_g3_sb6_gating_report import _should_write
        should_write, reason = _should_write(write_flag=True, max_rows=None, script_dirty=False)
        self.assertTrue(should_write)


class DualCurveTests(unittest.TestCase):
    """對應複核項目 11 與 GREEN `81def57` 複核追加訂正：Ridge 對照
    曲線的 `P₀` 必須來自 Ridge **自己的校準器與自己的原始分數**——
    v1 的簽章只接受單一 `raw_eval` 同時套給兩個校準器，不反映真實
    管線 LR／Ridge `decision_function()` 輸出本來就不同的事實，
    `run_report()` GREEN 時因此被迫繞過此函式（空殼未接主管線），
    導致「Ridge 用自己校準器」這件事在主管線裡完全沒有測試保護
    （`CLAUDE.md` §9A.1 第二個實例——測試覆蓋的是被替換掉的東西）。
    本輪訂正簽章為 `_build_dual_curves(lr_calibrator, lr_raw_eval,
    ridge_calibrator, ridge_raw_eval, theta_grid, y_calib_eval, *,
    base_rate)`，並新增 `test_run_report_routes_through_build_dual_curves`
    確保主管線真的呼叫它、且兩個模型收到不同的 `raw_eval`。"""

    def test_ridge_curve_uses_own_calibrator_and_own_raw_scores(self):
        from scripts.verify.ug_g3_sb6_gating_report import _build_dual_curves

        calls = []

        def fake_calibrated_timeout_probability(calibrator, raw_scores):
            calls.append((calibrator["tag"], float(raw_scores[0][0])))
            # 回傳與 tag 成比例的機率，確保 theta=0.1 時 gated 非空、
            # precision 非 None（驗證回傳列真的來自 assemble_curve_row，
            # 不是空殼的全 None 佔位）。
            return np.full(len(raw_scores), calibrator["tag"])

        lr_calibrator = {"tag": 0.3}
        ridge_calibrator = {"tag": 0.7}
        theta_grid = [0.1, 0.9]
        lr_raw_eval = np.zeros((5, 3))
        ridge_raw_eval = np.full((5, 3), 2.0)  # 刻意與 lr_raw_eval 不同
        y = np.array([0, 1, -1, 0, 1])

        with mock.patch(
            "scripts.verify.ug_g3_sb6_gating_report.calibrated_timeout_probability",
            side_effect=fake_calibrated_timeout_probability,
        ):
            curve_lr, curve_ridge = _build_dual_curves(
                lr_calibrator, lr_raw_eval, ridge_calibrator, ridge_raw_eval,
                theta_grid, y, base_rate=0.4,
            )

        # LR 收到 lr_calibrator + lr_raw_eval 第一列；Ridge 收到
        # ridge_calibrator + ridge_raw_eval 第一列——證明兩者不是共用
        # 同一份 raw_scores。
        self.assertEqual(calls, [(0.3, lr_raw_eval[0][0]), (0.7, ridge_raw_eval[0][0])])

        # 回傳列真的來自 assemble_curve_row()：theta=0.1 時兩個模型的
        # p0（0.3／0.7）都 >=0.1，gated 非空，precision 必須是數字，
        # 不是空殼的 None 佔位。
        row_lr_01 = next(r for r in curve_lr if r["theta"] == 0.1)
        row_ridge_01 = next(r for r in curve_ridge if r["theta"] == 0.1)
        self.assertIsNotNone(row_lr_01["precision"])
        self.assertIsNotNone(row_ridge_01["precision"])

    def test_run_report_routes_through_build_dual_curves(self):
        """`run_report()` 的主管線必須真的呼叫 `_build_dual_curves()`
        一次、且 LR 與 Ridge 收到的 `raw_eval` 是不同的陣列——防止
        『函式存在但沒接進主管線』的空殼版本再次發生（GREEN `81def57`
        複核發現的真實案例）。

        全鏈路合成資料，不讀真實 parquet／SB5 JSON：`build_meta_learner_input`／
        `fit_calibrator`／`evaluate_calibration_quality`／`apply_calibrator`／
        `brier_score_multiclass`／`roc_auc_score`／`extract_sb5_reference`／
        `assert_calibrator_matches_sb5`／`calibrated_timeout_probability`／
        `build_theta_grid` 全部 mock 為確定性樁函式；`LogisticRegression`／
        `RidgeClassifier` mock 為回傳**互不相同**的 `decision_function()`
        輸出的假模型，這是唯一需要驗證的變因——其餘管線步驟只是讓
        `run_report()` 能跑到呼叫 `_build_dual_curves()` 那一行。"""
        from scripts.verify import ug_g3_sb6_gating_report as report_module

        n_train, n_eval = 10, 20
        fake_oof_df = pd.DataFrame({
            "fold_id": np.concatenate([np.full(n_train, 5), np.full(6, 27), np.full(7, 30), np.full(7, 31)]),
            "trade_date": pd.to_datetime(["2025-05-05"] * (n_train + n_eval)),
            "target_triple_barrier": np.resize([-1, 0, 1, -1], n_train + n_eval),
        })

        def fake_build_meta_learner_input(oof_df, segment, target_column, return_retained_index=True):
            if segment == "meta_train":
                idx = oof_df.index[:n_train]
            else:
                idx = oof_df.index[n_train:]
            X = pd.DataFrame({
                "feat_a": np.linspace(0, 1, len(idx)),
                "volatility_20d": np.linspace(0.1, 0.9, len(idx)),
            }, index=idx)
            return X, {}, idx

        class _FakeModel:
            def __init__(self, tag):
                self._tag = tag
            def fit(self, X, y):
                return self
            def decision_function(self, X):
                # 每個模型回傳自己專屬、彼此不同的 (n,3) 分數
                base = np.full((len(X), 3), self._tag)
                return base + np.arange(len(X)).reshape(-1, 1) * 0.01

        captured = {}

        def fake_build_dual_curves(lr_calibrator, lr_raw_eval, ridge_calibrator, ridge_raw_eval,
                                    theta_grid, y_calib_eval, *, base_rate):
            captured["lr_raw_eval"] = np.asarray(lr_raw_eval).copy()
            captured["ridge_raw_eval"] = np.asarray(ridge_raw_eval).copy()
            captured["called"] = captured.get("called", 0) + 1
            return [], []

        fake_quality = {0: {"auc_before": 0.9, "auc_after": 0.9, "platt_slope": 1.0, "platt_intercept": 0.0}}

        with mock.patch.object(report_module, "verify_oof_sha256", return_value=("fakesha", {})), \
             mock.patch.object(report_module.pd, "read_parquet", return_value=fake_oof_df), \
             mock.patch.object(report_module, "build_meta_learner_input", side_effect=fake_build_meta_learner_input), \
             mock.patch("builtins.open", mock.mock_open(read_data="{}")), \
             mock.patch.object(report_module.json, "load", return_value={}), \
             mock.patch("sklearn.linear_model.LogisticRegression", side_effect=lambda **kw: _FakeModel(0.2)), \
             mock.patch("sklearn.linear_model.RidgeClassifier", side_effect=lambda **kw: _FakeModel(0.8)), \
             mock.patch.object(report_module, "fit_calibrator", return_value="fake_calibrator"), \
             mock.patch.object(report_module, "evaluate_calibration_quality", return_value=fake_quality), \
             mock.patch.object(report_module, "apply_calibrator", return_value=np.full((7, 3), 1 / 3)), \
             mock.patch("src.ml.calibration.brier_score_multiclass", return_value=0.5), \
             mock.patch("sklearn.metrics.roc_auc_score", return_value=0.5), \
             mock.patch.object(report_module, "extract_sb5_reference", return_value=fake_quality[0]), \
             mock.patch.object(report_module, "assert_calibrator_matches_sb5", return_value=None), \
             mock.patch.object(report_module, "calibrated_timeout_probability", return_value=np.full(7, 0.5)), \
             mock.patch.object(report_module, "build_theta_grid", return_value={"fine": [0.3], "quantile": []}), \
             mock.patch.object(report_module, "_build_dual_curves", side_effect=fake_build_dual_curves):
            report_module.run_report(
                oof_path=Path("dummy.parquet"),
                oof_generation_evidence_path=Path("dummy_evidence.json"),
                sb5_reference_path=Path("dummy_sb5.json"),
                target_column="target_triple_barrier",
            )

        self.assertEqual(captured.get("called", 0), 1)
        self.assertFalse(np.array_equal(captured.get("lr_raw_eval"), captured.get("ridge_raw_eval")))


class ReportJsonSerializableTests(unittest.TestCase):
    """`_json_default` 直接重用 `UG-G3-SB5` 報告腳本既有函式，不另寫
    （審查方要求）。"""

    def test_report_dict_json_serializable(self):
        from scripts.verify.ug_g3_sb5_calibration_report import _json_default
        report_dict = {
            "theta_grid": {"quantile": [np.float64(0.1), np.float64(0.2)]},
            "holdout_guard": {"fold_id_max": np.int64(32)},
            "n": np.int64(100),
            "trade_date": pd.Timestamp("2025-10-22"),
        }
        serialized = json.dumps(report_dict, default=_json_default)
        self.assertIsInstance(serialized, str)


if __name__ == "__main__":
    unittest.main()
