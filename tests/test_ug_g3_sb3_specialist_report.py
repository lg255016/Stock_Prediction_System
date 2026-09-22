# -*- coding: utf-8 -*-
"""`UG-G3-SB3` 段級報告腳本紅測（PO 2026-09-13 核准命名／參數／守衛）。

`scripts/verify/ug_g3_sb3_specialist_report.py` 尚不存在，ImportError 即為
RED。涵蓋 PO 明確列出的四項守衛 known-FAIL，以及輸出契約與「不連 DB」的
結構性驗證：

1. parquet sha256 與 evidence JSON 記載值不符 → abort。
2. `WalkForwardSplitter` 未以 `require_label_end_date=True` 建構 → abort
   （用直接檢查建構後物件的屬性，而非 mock 呼叫參數——更直接驗證真實
   行為，而非只驗證呼叫方式）。
3. 面板缺少 `label_end_date`／`label_end_date_tb` → abort。
4. 任一 Fold 的 `purge_mode != "exact"` → abort（防禦性重驗——正常情況下
   守衛 2 已保證這件事恆成立，本檢查是extracted 成獨立函式的單元測試，
   沒有不修改 `WalkForwardSplitter` 內部邏輯就能構造出的端到端 known-FAIL
   案例，誠實揭露而非硬湊一個，比照 `prepare_fold_data()` 規則 (c) 防禦性
   斷言的既有處理方式）。

另外涵蓋：情緒子集股票判定（面板現場計算，不複製 evidence JSON 既有清單）、
輸出契約的必要欄位、以及「不匯入 psycopg2、不讀 DB_HOST」的結構性驗證。
"""
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


class Sha256GuardTests(unittest.TestCase):
    """守衛 1：parquet sha256 必須等於 evidence JSON 記載值。"""

    def _write_temp_files(self, tmpdir, parquet_bytes, sha256_in_evidence):
        panel_path = Path(tmpdir) / "panel_target_up_down_20260912.parquet"
        panel_path.write_bytes(parquet_bytes)
        evidence_path = Path(tmpdir) / "evidence.json"
        evidence_path.write_text(json.dumps({
            "part_B_panel_export": {
                "targets": {
                    "target_up_down": {"sha256": sha256_in_evidence}
                }
            }
        }), encoding="utf-8")
        return panel_path, evidence_path

    def test_matching_sha256_passes(self):
        from scripts.verify.ug_g3_sb3_specialist_report import verify_panel_sha256

        with tempfile.TemporaryDirectory() as tmpdir:
            content = b"fake parquet bytes for hash test"
            real_sha256 = hashlib.sha256(content).hexdigest()
            panel_path, evidence_path = self._write_temp_files(tmpdir, content, real_sha256)

            result = verify_panel_sha256(panel_path, "target_up_down", evidence_path)
            self.assertEqual(result, real_sha256)

    def test_mismatched_sha256_raises(self):
        """known-FAIL：parquet 內容篡改（或 evidence JSON 記載值過期）時必須 abort。"""
        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, verify_panel_sha256,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            content = b"fake parquet bytes for hash test"
            wrong_sha256 = "0" * 64
            panel_path, evidence_path = self._write_temp_files(tmpdir, content, wrong_sha256)

            with self.assertRaises(PanelIntegrityError):
                verify_panel_sha256(panel_path, "target_up_down", evidence_path)


class SplitterConstructionTests(unittest.TestCase):
    """守衛 2：`build_splitter()` 產出的切分器必須以
    `require_label_end_date=True` 建構——直接檢查物件屬性，不是檢查呼叫
    方式，確認的是真實行為。"""

    def test_target_up_down_splitter_config(self):
        from scripts.verify.ug_g3_sb3_specialist_report import build_splitter

        splitter = build_splitter("target_up_down", "rolling")
        self.assertTrue(splitter.require_label_end_date)
        self.assertEqual(splitter.label_end_date_col, "label_end_date")
        self.assertEqual(splitter.label_horizon, 1)
        self.assertEqual(splitter.train_window_size, 60)
        self.assertEqual(splitter.test_window_size, 20)
        self.assertEqual(splitter.embargo_days, 0)
        self.assertEqual(splitter.mode, "rolling")

    def test_target_triple_barrier_splitter_config(self):
        from scripts.verify.ug_g3_sb3_specialist_report import build_splitter

        splitter = build_splitter("target_triple_barrier", "expanding")
        self.assertTrue(splitter.require_label_end_date)
        self.assertEqual(splitter.label_end_date_col, "label_end_date_tb")
        self.assertEqual(splitter.label_horizon, 5)
        self.assertEqual(splitter.mode, "expanding")


class RequiredColumnsGuardTests(unittest.TestCase):
    """守衛 3：面板缺少 `label_end_date`／`label_end_date_tb` 必須 abort。"""

    def test_missing_required_column_raises(self):
        """known-FAIL：面板只有 label_end_date，缺 label_end_date_tb。"""
        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, assert_required_columns,
        )

        panel = pd.DataFrame({"label_end_date": [1, 2, 3]})
        with self.assertRaises(PanelIntegrityError):
            assert_required_columns(panel, ("label_end_date", "label_end_date_tb"))

    def test_all_required_columns_present_passes(self):
        from scripts.verify.ug_g3_sb3_specialist_report import assert_required_columns

        panel = pd.DataFrame({"label_end_date": [1], "label_end_date_tb": [2]})
        assert_required_columns(panel, ("label_end_date", "label_end_date_tb"))  # 不應拋例外


class PurgeModeGuardTests(unittest.TestCase):
    """守衛 4：任一 Fold 的 `purge_mode != "exact"` 必須 abort（防禦性重驗，
    見模組 docstring 說明沒有端到端 known-FAIL 案例的誠實揭露）。"""

    def test_non_exact_purge_mode_raises(self):
        """known-FAIL：偽造一個 purge_mode='approximate' 的 fold_metadata。"""
        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, assert_purge_mode_exact,
        )

        with self.assertRaises(PanelIntegrityError):
            assert_purge_mode_exact({"fold": 3, "purge_mode": "approximate"})

    def test_exact_purge_mode_passes(self):
        from scripts.verify.ug_g3_sb3_specialist_report import assert_purge_mode_exact

        assert_purge_mode_exact({"fold": 3, "purge_mode": "exact"})  # 不應拋例外


class SentimentSubsetDeterminationTests(unittest.TestCase):
    """情緒子集股票判定：面板現場計算 `sentiment_mean` 非 NULL 的相異
    `stock_id` 集合，不複製 evidence JSON 既有清單（避免同一數字兩處各自
    維護、日後漂移）。"""

    def test_subset_determined_from_sentiment_mean_notna(self):
        from scripts.verify.ug_g3_sb3_specialist_report import (
            determine_sentiment_subset_stock_ids,
        )

        panel = pd.DataFrame({
            "stock_id": ["A1", "A1", "A2", "A2", "A3"],
            "sentiment_mean": [0.5, np.nan, np.nan, np.nan, 0.1],
        })
        result = determine_sentiment_subset_stock_ids(panel)
        self.assertEqual(result, ["A1", "A3"])

    def test_subset_empty_when_column_missing(self):
        from scripts.verify.ug_g3_sb3_specialist_report import (
            determine_sentiment_subset_stock_ids,
        )

        panel = pd.DataFrame({"stock_id": ["A1", "A2"]})
        result = determine_sentiment_subset_stock_ids(panel)
        self.assertEqual(result, [])


class SignalRowMaskTests(unittest.TestCase):
    """訊號列遮罩（PO 2026-09-13）：`article_count>0` 或 `sentiment_5d_ma`
    非 NULL 的列——面板情緒欄覆蓋率僅 0.49%（VERIFIED THIS SESSION：
    139,585 列中 683 列 `sentiment_mean` 非 NULL），其餘列的情緒衍生欄
    是聚合層補的 0.0 常數，對模型沒有資訊。這是 B 臂在本面板上唯一真的
    「多出資訊」的列，是「覆蓋率不足」這句話的量化依據。"""

    def test_mask_true_when_article_count_positive_or_sentiment_5d_ma_notna(self):
        from scripts.verify.ug_g3_sb3_specialist_report import determine_signal_row_mask

        panel = pd.DataFrame({
            "article_count": [0, 1, 0, 0],
            "sentiment_5d_ma": [np.nan, np.nan, 0.3, np.nan],
        })
        mask = determine_signal_row_mask(panel)
        self.assertEqual(mask.tolist(), [False, True, True, False])

    def test_mask_all_false_when_columns_missing(self):
        from scripts.verify.ug_g3_sb3_specialist_report import determine_signal_row_mask

        panel = pd.DataFrame({"stock_id": ["A1", "A2"]})
        mask = determine_signal_row_mask(panel)
        self.assertEqual(mask.tolist(), [False, False])


class NoDatabaseImportTests(unittest.TestCase):
    """腳本結構上不可能連 DB：原始碼不含 `psycopg2`／`DB_HOST`／`DB_PORT`
    字樣，且匯入本模組不會使 `psycopg2` 進入 `sys.modules`。"""

    def test_module_source_has_no_db_references(self):
        src_path = Path("scripts/verify/ug_g3_sb3_specialist_report.py")
        text = src_path.read_text(encoding="utf-8")
        self.assertNotIn("psycopg2", text)
        self.assertNotIn("DB_HOST", text)
        self.assertNotIn("DB_PORT", text)

    def test_importing_module_does_not_newly_load_psycopg2(self):
        mod_name = "scripts.verify.ug_g3_sb3_specialist_report"
        sys.modules.pop(mod_name, None)
        before = set(sys.modules.keys())
        importlib.import_module(mod_name)
        after = set(sys.modules.keys())
        newly_imported = after - before
        self.assertNotIn("psycopg2", newly_imported)


class SingleFoldReportRecordTests(unittest.TestCase):
    """端到端（合成小面板，非真實 parquet）：`run_single_configuration()`
    的輸出契約——逐 Fold per-class（固定 labels）、boundary_interior 含
    `labels_dropped`、剔除計數 (a)(b)、`purge_mode`、LR 的 `n_iter_`
    （非 LR 為 `None`）、跨 Fold `leakage_summary`、耗時；B 臂另有
    `sentiment_subset_arm_b`。"""

    def _tiny_panel(self):
        from src.ml.baseline_models import ARM_B_FEATURE_COLS, SENTIMENT_FEATURE_COLS

        n_days = 90
        stock_ids = ("A1", "A2", "A3")
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        rng = np.random.RandomState(0)
        rows = []
        for d in dates:
            for sid in stock_ids:
                row = {"trade_date": d, "stock_id": sid}
                for col in ARM_B_FEATURE_COLS:
                    row[col] = float(rng.normal())
                if sid != "A1":
                    # 只有 A1 有情緒訊號，其餘兩檔全 NaN——模擬真實面板的
                    # 稀疏情緒覆蓋（20/458 = 4.4%），用來驗證子集判定與
                    # sentiment_subset_arm_b 的計算對象正確。
                    for col in SENTIMENT_FEATURE_COLS:
                        row[col] = np.nan
                row["target"] = int(rng.choice([0, 1]))
                row["label_end_date"] = d + pd.tseries.offsets.BDay(1)
                row["label_end_date_tb"] = d + pd.tseries.offsets.BDay(5)
                rows.append(row)
        return pd.DataFrame(rows)

    def _write_panel_and_evidence(self, tmpdir, panel, target):
        panel_path = Path(tmpdir) / f"panel_{target}_20260912.parquet"
        panel.to_parquet(panel_path)
        sha256 = hashlib.sha256(panel_path.read_bytes()).hexdigest()
        evidence_path = Path(tmpdir) / "evidence.json"
        evidence_path.write_text(json.dumps({
            "part_B_panel_export": {"targets": {target: {"sha256": sha256}}}
        }), encoding="utf-8")
        return panel_path, evidence_path

    def test_arm_a_report_record_shape(self):
        from scripts.verify.ug_g3_sb3_specialist_report import run_single_configuration

        panel = self._tiny_panel()
        with tempfile.TemporaryDirectory() as tmpdir:
            panel_path, evidence_path = self._write_panel_and_evidence(
                tmpdir, panel, "target_up_down")

            report = run_single_configuration(
                target="target_up_down", mode="rolling",
                models=["random_forest"], arms=["A"],
                panel_path=panel_path, evidence_json_path=evidence_path)

            self.assertGreaterEqual(report["n_folds"], 1)
            self.assertEqual(report["labels"], [0, 1])
            key = "random_forest__A"
            self.assertIn(key, report["results"])
            pair = report["results"][key]
            self.assertIn("leakage_summary", pair)
            self.assertIn("total_elapsed_seconds", pair)
            self.assertIn("aggregate", pair)
            self.assertIn("full", pair["aggregate"])
            self.assertIn("sentiment_subset", pair["aggregate"])
            self.assertIn("n_lr_max_iter_hits", pair["aggregate"])
            self.assertIn("majority_baseline", pair["aggregate"])
            self.assertIn("full", pair["aggregate"]["majority_baseline"])
            self.assertIn("sentiment_subset", pair["aggregate"]["majority_baseline"])
            self.assertIn("signal_rows_subset", pair["aggregate"])
            self.assertGreaterEqual(len(pair["folds"]), 1)
            self.assertIn("subset_definitions", report)
            self.assertIn("sentiment_subset", report["subset_definitions"])
            self.assertIn("signal_rows_subset", report["subset_definitions"])

            fold_record = pair["folds"][0]
            for required_key in (
                "fold", "purge_mode", "n_train", "n_test",
                "n_target_null_excluded", "n_feature_null_excluded",
                "per_class", "boundary_interior", "n_iter_", "elapsed_seconds",
                "majority_baseline", "signal_rows_subset",
            ):
                self.assertIn(required_key, fold_record, f"缺少必要欄位: {required_key}")
            self.assertIn("full", fold_record["majority_baseline"])
            self.assertIn("n", fold_record["signal_rows_subset"])
            self.assertIn("sentiment_subset", fold_record["majority_baseline"])

            self.assertEqual(fold_record["purge_mode"], "exact")
            self.assertIsNone(fold_record["n_iter_"], "random_forest 沒有 n_iter_ 屬性，應為 None")
            self.assertIn("0", fold_record["per_class"], "固定 labels=[0,1] 即使某類缺席也應出現鍵")
            self.assertIn("1", fold_record["per_class"])
            self.assertIn("labels_dropped", fold_record["boundary_interior"])
            self.assertIn(
                "sentiment_subset", fold_record,
                "PO 2026-09-13 訂正：兩臂皆須輸出 sentiment_subset 供對照"
                "——A 臂不再排除此欄位")

    def test_sentiment_subset_present_and_equal_n_on_both_arms(self):
        """PO 2026-09-13 訂正：提案 §3.4 要的是「限定在情緒子集的 A/B 對照」，
        對照需要 A 臂在同一批子集列上的數字，不能只有 B 臂。兩臂剔除後
        保留列相等（`run_fold_for_arms` 已保證），故子集遮罩對兩臂相同、
        `n` 必須相等。"""
        from scripts.verify.ug_g3_sb3_specialist_report import run_single_configuration

        panel = self._tiny_panel()
        with tempfile.TemporaryDirectory() as tmpdir:
            panel_path, evidence_path = self._write_panel_and_evidence(
                tmpdir, panel, "target_up_down")

            report = run_single_configuration(
                target="target_up_down", mode="rolling",
                models=["random_forest"], arms=["A", "B"],
                panel_path=panel_path, evidence_json_path=evidence_path)

            self.assertEqual(report["sentiment_subset_stock_ids"], ["A1"])
            fold_a = report["results"]["random_forest__A"]["folds"][0]
            fold_b = report["results"]["random_forest__B"]["folds"][0]
            self.assertIn("sentiment_subset", fold_a)
            self.assertIn("sentiment_subset", fold_b)
            self.assertIn("n", fold_a["sentiment_subset"])
            self.assertEqual(
                fold_a["sentiment_subset"]["n"], fold_b["sentiment_subset"]["n"],
                "兩臂保留列集合相等，情緒子集列數必須相等")

    def test_pipeline_rejects_sha256_mismatch(self):
        """known-FAIL（管線層級）：evidence JSON 記載值被竄改／過期時，
        整條 pipeline（不只是 verify_panel_sha256 單元本身）必須 abort，
        不得跑到一半才發現。"""
        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, run_single_configuration,
        )

        panel = self._tiny_panel()
        with tempfile.TemporaryDirectory() as tmpdir:
            panel_path, evidence_path = self._write_panel_and_evidence(
                tmpdir, panel, "target_up_down")
            # 竄改 evidence JSON 記載的 sha256。
            evidence_path.write_text(json.dumps({
                "part_B_panel_export": {"targets": {"target_up_down": {"sha256": "0" * 64}}}
            }), encoding="utf-8")

            with self.assertRaises(PanelIntegrityError):
                run_single_configuration(
                    target="target_up_down", mode="rolling",
                    models=["random_forest"], arms=["A"],
                    panel_path=panel_path, evidence_json_path=evidence_path)

    def test_pipeline_rejects_missing_label_end_date_column(self):
        """known-FAIL（管線層級）：面板缺少必要欄位時，pipeline 必須在
        進入 Fold 迴圈前 abort。"""
        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, run_single_configuration,
        )

        panel = self._tiny_panel().drop(columns=["label_end_date_tb"])
        with tempfile.TemporaryDirectory() as tmpdir:
            panel_path, evidence_path = self._write_panel_and_evidence(
                tmpdir, panel, "target_up_down")

            with self.assertRaises(PanelIntegrityError):
                run_single_configuration(
                    target="target_up_down", mode="rolling",
                    models=["random_forest"], arms=["A"],
                    panel_path=panel_path, evidence_json_path=evidence_path)

    def test_main_writes_script_commit_and_run_timestamp_to_output(self):
        """PO 2026-09-13 全量前補件：輸出 JSON 須記錄產出它的腳本
        commit hash 與執行時間戳，供全量覆蓋時追溯是哪個版本產出的。"""
        from scripts.verify.ug_g3_sb3_specialist_report import main

        panel = self._tiny_panel()
        with tempfile.TemporaryDirectory() as tmpdir:
            panel_path, evidence_path = self._write_panel_and_evidence(
                tmpdir, panel, "target_up_down")
            output_path = Path(tmpdir) / "output.json"

            main(
                target="target_up_down", mode="rolling",
                models=["random_forest"], arms=["A"],
                panel_path=panel_path, evidence_json_path=evidence_path,
                output_path=output_path)

            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertRegex(written["script_commit"], r"^[0-9a-f]{40}$")
            self.assertIn("script_dirty", written)
            self.assertIsInstance(written["script_dirty"], bool)
            self.assertIn("run_timestamp", written)


class ScriptCommitInfoTests(unittest.TestCase):
    """`get_script_commit_info()`：回傳真實 repo 的 commit hash（40 位
    十六進位）與工作樹是否乾淨（PO 2026-09-13 訂正：容器內 git 兩個既有
    環境坑——(1) bind mount 造成 dubious ownership，比照既有
    `ug_g3_sb2a_stage2_rerun_risk027.py` 慣例用 `-c safe.directory=<root>`
    逐次授權，不動全域/本機設定；(2) 容器沒設 `core.autocrlf`，行尾差異
    會被當成大量修改，另加 `-c core.autocrlf=true`）。"""

    def test_returns_commit_hash_and_dirty_flag(self):
        from scripts.verify.ug_g3_sb3_specialist_report import get_script_commit_info

        info = get_script_commit_info()
        self.assertRegex(info["commit"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(info["dirty"], bool)
        self.assertIn("dirty_paths", info)
        self.assertIn("untracked_paths", info)

    def test_git_commands_carry_both_c_flags(self):
        """known-FAIL：拿掉 `safe.directory` 或 `core.autocrlf` 任一個 `-c`
        參數，本測試必 FAIL——這兩個環境坑各自獨立，缺一個都會讓
        `get_script_commit_info()` 在真實容器環境中失敗或算錯。"""
        from unittest.mock import MagicMock, patch

        from scripts.verify.ug_g3_sb3_specialist_report import get_script_commit_info

        captured_argvs = []

        def fake_run(argv, **kwargs):
            captured_argvs.append(argv)
            result = MagicMock()
            result.stdout = "deadbeef" * 5 + "\n" if "rev-parse" in argv else ""
            return result

        with patch("scripts.verify.ug_g3_sb3_specialist_report.subprocess.run", side_effect=fake_run):
            get_script_commit_info(repo_root=Path("/fake/repo"))

        for argv in captured_argvs:
            self.assertIn("safe.directory=/fake/repo", " ".join(argv))
            self.assertIn("core.autocrlf=true", " ".join(argv))

    def test_dirty_excludes_report_output_and_untracked_files(self):
        """dirty 只看 tracked 檔案的修改，且排除本腳本自身輸出的
        report JSON（否則每次全量重跑都會自我宣告 dirty）；未追蹤檔
        （如 `.claude/settings.local.json`）不計入 dirty，另列
        `untracked_paths`。"""
        from unittest.mock import MagicMock, patch

        from scripts.verify.ug_g3_sb3_specialist_report import get_script_commit_info

        porcelain = "\n".join([
            " M src/ml/specialist_training.py",
            " M doc/upgrade/gates/evidence/UG_G3_SB3_report_target_triple_barrier_rolling.json",
            "?? .claude/settings.local.json",
            "?? doc/upgrade/gates/evidence/UG_G3_SB3_report_target_up_down_rolling.json",
        ])

        def fake_run(argv, **kwargs):
            result = MagicMock()
            if "rev-parse" in argv:
                result.stdout = "deadbeef" * 5 + "\n"
            else:
                result.stdout = porcelain + "\n"
            return result

        with patch("scripts.verify.ug_g3_sb3_specialist_report.subprocess.run", side_effect=fake_run):
            info = get_script_commit_info(repo_root=Path("/fake/repo"))

        self.assertTrue(info["dirty"])
        self.assertEqual(info["dirty_paths"], ["src/ml/specialist_training.py"])
        self.assertIn(".claude/settings.local.json", info["untracked_paths"])

    def test_rev_parse_failure_raises_not_silently_none(self):
        """known-FAIL：`git rev-parse` 失敗時必須拋例外，不得把 `commit`
        寫成 `None` 讓輸出 JSON 帶一個版本不明的假欄位。"""
        import subprocess as subprocess_module
        from unittest.mock import patch

        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, get_script_commit_info,
        )

        def fake_run(argv, **kwargs):
            raise subprocess_module.CalledProcessError(128, argv, stderr="dubious ownership")

        with patch("scripts.verify.ug_g3_sb3_specialist_report.subprocess.run", side_effect=fake_run):
            with self.assertRaises(PanelIntegrityError):
                get_script_commit_info(repo_root=Path("/fake/repo"))


# ==============================================================================
# 跨 Fold 彙總（`aggregate`）——紅測（PO 2026-09-13 實跑前補件 2）
# ==============================================================================
# Gate B 的 D3 結論不能只靠 43 筆逐 Fold 紀錄讓人自己算，`compute_pair_aggregate()`
# 須彙總 macro F1 分布（中位數／平均／最小／最大）、逐類別平均
# recall／f1（只在該 Fold 該類別 support>0 時列入，避免類別缺席的 Fold
# 把平均拉向 0，並揭露列入的 Fold 數）、n 總和、LR 撞滿 max_iter 的
# Fold 數。函式尚不存在，ImportError 即為 RED。

class AggregateAcrossFoldsTests(unittest.TestCase):
    """`compute_pair_aggregate()`：合成兩個 fold record，手算中位數等
    統計量與函式輸出比對。"""

    def _fold_record(self, macro_f1, n_test, label_0_support, label_1_support,
                      label_0_recall=0.6, label_1_recall=0.7,
                      label_0_f1=0.55, label_1_f1=0.65,
                      subset_macro_f1=None, subset_n=0, n_iter_=None):
        per_class = {
            "0": {"precision": 0.5, "recall": label_0_recall, "f1": label_0_f1,
                  "support": label_0_support},
            "1": {"precision": 0.5, "recall": label_1_recall, "f1": label_1_f1,
                  "support": label_1_support},
            "macro_f1": macro_f1,
        }
        if subset_macro_f1 is None:
            sentiment_subset = {"n": subset_n, "macro_f1": None}
        else:
            sentiment_subset = {
                "0": {"precision": 0.4, "recall": 0.4, "f1": 0.4, "support": subset_n},
                "1": {"precision": 0.6, "recall": 0.6, "f1": 0.6, "support": 0},
                "macro_f1": subset_macro_f1,
                "n": subset_n,
            }
        return {
            "n_test": n_test,
            "per_class": per_class,
            "sentiment_subset": sentiment_subset,
            "n_iter_": n_iter_,
        }

    def test_macro_f1_median_matches_hand_calculation(self):
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.60, n_test=100, label_0_support=40, label_1_support=60),
            self._fold_record(macro_f1=0.80, n_test=120, label_0_support=50, label_1_support=70),
        ]
        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")

        self.assertAlmostEqual(agg["full"]["macro_f1_median"], 0.70)
        self.assertAlmostEqual(agg["full"]["macro_f1_mean"], 0.70)
        self.assertAlmostEqual(agg["full"]["macro_f1_min"], 0.60)
        self.assertAlmostEqual(agg["full"]["macro_f1_max"], 0.80)
        self.assertEqual(agg["full"]["n_total"], 220)
        self.assertEqual(agg["full"]["n_folds_with_data"], 2)

    def test_per_label_average_skips_folds_without_support(self):
        """known-FAIL 對照：若彙總誤把「該類別缺席（support=0）時被
        zero_division 帶出的 0.0」也計入平均，這裡手算的期望值會對不上——
        本測試專門釘住「只在 support>0 的 Fold 列入平均」這件事。"""
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.5, n_test=10, label_0_support=5, label_1_support=5,
                               label_0_recall=0.8, label_0_f1=0.75),
            # 第二個 Fold 的 label 0 完全缺席（support=0）——若誤把它的
            # recall/f1（依 zero_division=0 慣例會是 0.0）也計入平均，
            # 期望值就不會是單獨第一個 Fold 的 0.8/0.75。
            self._fold_record(macro_f1=0.5, n_test=10, label_0_support=0, label_1_support=10,
                               label_0_recall=0.0, label_0_f1=0.0),
        ]
        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")

        label_0_agg = agg["full"]["per_label"]["0"]
        self.assertAlmostEqual(label_0_agg["mean_recall"], 0.8)
        self.assertAlmostEqual(label_0_agg["mean_f1"], 0.75)
        self.assertEqual(label_0_agg["n_folds_with_support"], 1)

    def test_sentiment_subset_aggregate_skips_empty_folds(self):
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.5, n_test=10, label_0_support=5, label_1_support=5,
                               subset_macro_f1=0.4, subset_n=3),
            self._fold_record(macro_f1=0.5, n_test=10, label_0_support=5, label_1_support=5,
                               subset_macro_f1=None, subset_n=0),
        ]
        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")

        self.assertAlmostEqual(agg["sentiment_subset"]["macro_f1_median"], 0.4)
        self.assertEqual(agg["sentiment_subset"]["n_folds_with_data"], 1)
        self.assertEqual(agg["sentiment_subset"]["n_total"], 3)

    def test_lr_max_iter_hit_count(self):
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.5, n_test=10, label_0_support=5, label_1_support=5, n_iter_=500),
            self._fold_record(macro_f1=0.5, n_test=10, label_0_support=5, label_1_support=5, n_iter_=42),
        ]
        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="logistic_regression")
        self.assertEqual(agg["n_lr_max_iter_hits"], 1)

        agg_rf = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")
        self.assertEqual(agg_rf["n_lr_max_iter_hits"], 0, "非 LR 模型不應計入 max_iter 撞滿次數")

    def test_majority_baseline_aggregate_matches_hand_calculation(self):
        """PO 2026-09-13 全量前補件：沒有多數類基線，Gate B 讀者無法判斷
        模型的 macro F1 是不是雜訊。合成兩個 fold 的 majority_baseline，
        手算中位數比對。"""
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.6, n_test=10, label_0_support=5, label_1_support=5),
            self._fold_record(macro_f1=0.6, n_test=10, label_0_support=5, label_1_support=5),
        ]
        fold_records[0]["majority_baseline"] = {
            "full": {"macro_f1": 0.30},
            "sentiment_subset": {"macro_f1": None, "n": 0},
        }
        fold_records[1]["majority_baseline"] = {
            "full": {"macro_f1": 0.50},
            "sentiment_subset": {"macro_f1": None, "n": 0},
        }

        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")
        self.assertAlmostEqual(agg["majority_baseline"]["full"]["macro_f1_median"], 0.40)

    def test_majority_baseline_missing_defaults_to_no_data(self):
        """對照：既有（未補 majority_baseline 欄位的）fold record 不應讓
        compute_pair_aggregate() 出錯——回頭相容既有呼叫端。"""
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.6, n_test=10, label_0_support=5, label_1_support=5),
        ]
        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")
        self.assertEqual(agg["majority_baseline"]["full"]["n_folds_with_data"], 0)
        self.assertIsNone(agg["majority_baseline"]["full"]["macro_f1_median"])

    def test_majority_baseline_rule_documented_in_output(self):
        """PO 2026-09-13：「票數並列取數值最小者」的判定規則須寫進輸出，
        不能只留在 docstring 裡——Gate B 讀者看 JSON 就要能查到規則。"""
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.6, n_test=10, label_0_support=5, label_1_support=5),
        ]
        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")
        self.assertIn("rule", agg["majority_baseline"])
        self.assertIn("最小", agg["majority_baseline"]["rule"])

    def test_signal_rows_subset_aggregate_matches_hand_calculation(self):
        """PO 2026-09-13：訊號列子集（`article_count>0` 或 `sentiment_5d_ma`
        非 NULL 的列）是 B 臂在本面板上唯一真的「多出資訊」的列——彙總
        須附每 Fold 的 `n`，合成兩個 fold 手算中位數比對。"""
        from scripts.verify.ug_g3_sb3_specialist_report import compute_pair_aggregate

        fold_records = [
            self._fold_record(macro_f1=0.6, n_test=100, label_0_support=50, label_1_support=50),
            self._fold_record(macro_f1=0.6, n_test=100, label_0_support=50, label_1_support=50),
        ]
        fold_records[0]["signal_rows_subset"] = {
            "0": {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 3},
            "1": {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2},
            "macro_f1": 0.30, "n": 5,
        }
        fold_records[1]["signal_rows_subset"] = {"n": 0, "macro_f1": None}

        agg = compute_pair_aggregate(fold_records, labels=[0, 1], model_name="random_forest")
        self.assertAlmostEqual(agg["signal_rows_subset"]["macro_f1_median"], 0.30)
        self.assertEqual(agg["signal_rows_subset"]["n_folds_with_data"], 1)
        self.assertEqual(agg["signal_rows_subset"]["n_total"], 5)


# ==============================================================================
# 面板 RangeIndex 守衛——紅測（PO 2026-09-13 實跑前補件 3）
# ==============================================================================
# `prepare_fold_data()` 回傳的 `retained_index` 是 `sub.index`（pandas 索引
# 標籤），本腳本拿它對 `panel` 做 `.loc` 取股票代號（情緒子集遮罩）——這
# 假設面板索引是預設 RangeIndex（讀 parquet 後未經任何列過濾，標籤與
# 位置一致）。若日後呼叫端先過濾面板再傳進來，索引標籤與位置不再對應，
# `.loc` 會取到錯誤的列且不會報錯——因此明確斷言，不留給下游默默算錯。

class PanelRangeIndexGuardTests(unittest.TestCase):

    def test_non_rangeindex_panel_raises(self):
        """known-FAIL：面板索引被過濾／重排後不再是 RangeIndex。"""
        from scripts.verify.ug_g3_sb3_specialist_report import (
            PanelIntegrityError, assert_panel_has_rangeindex,
        )

        panel = pd.DataFrame({"a": [1, 2, 3]}, index=[0, 2, 4])  # 過濾後留下的非連續索引
        with self.assertRaises(PanelIntegrityError):
            assert_panel_has_rangeindex(panel)

    def test_rangeindex_panel_passes(self):
        from scripts.verify.ug_g3_sb3_specialist_report import assert_panel_has_rangeindex

        panel = pd.DataFrame({"a": [1, 2, 3]})  # 預設 RangeIndex(0,1,2)
        assert_panel_has_rangeindex(panel)  # 不應拋例外


if __name__ == "__main__":
    unittest.main()
