# -*- coding: utf-8 -*-
"""
`scripts/verify/ug_g3_sb2a_backfill_features.py` 的單元測試
（PO 2026-09-11 複核要求：批次切分、批次失敗即停、標籤計數回歸偵測、
預覽模式零寫入、7 項不變式各一個 known-FAIL 案例）。

純邏輯測邏輯，不連真實庫、不觸網——與段 1、基線比對腳本的測試範圍劃分
一致。真實庫互動另外唯讀驗證（見 binding confirmation 證據）。
"""
import contextlib
import inspect
import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from scripts.verify.ug_g3_sb2a_backfill_features import (
    split_into_batches,
    assert_batch_stock_subset,
    write_one_batch,
    run_features_backfill,
    verify_batch_after_write,
    check_price_consistency,
    check_return_1d,
    check_target_consistency,
    check_rsi_consistency,
    check_volatility_consistency,
    check_source_status_enum,
    check_sentiment_null_iff_article_zero,
    check_invariants,
    check_total_row_count,
    check_label_counts,
    EXISTING_ROWS_BEFORE,
    EXPECTED_LABEL_COUNTS,
)
from scripts.verify.ug_g3_sb2a_stage2_baseline_comparison import COMPARE_COLUMNS


class SplitIntoBatchesTests(unittest.TestCase):

    def test_disjoint_and_covers_all_459_stocks(self):
        ids = [str(i) for i in range(459)]
        batches = split_into_batches(ids, batch_size=50)
        flat = [s for b in batches for s in b]
        self.assertEqual(sorted(flat), sorted(ids), "批次聯集必須等於全部股票")
        self.assertEqual(len(flat), len(set(flat)), "批次之間不得重疊")

    def test_batch_size_and_count_459_stocks(self):
        ids = [str(i) for i in range(459)]
        batches = split_into_batches(ids, batch_size=50)
        self.assertEqual(len(batches), 10, "459 檔、50 檔/批 → 10 批")
        for b in batches[:-1]:
            self.assertEqual(len(b), 50)
        self.assertEqual(len(batches[-1]), 9, "末批應為 459 - 9*50 = 9 檔")

    def test_sorted_deterministic_regardless_of_input_order(self):
        ids = ["6488", "2330", "NVDA", "2382"]
        batches = split_into_batches(ids, batch_size=2)
        self.assertEqual(batches[0], ["2330", "2382"])
        self.assertEqual(batches[1], ["6488", "NVDA"])


class AssertBatchStockSubsetTests(unittest.TestCase):

    def test_passes_when_all_rows_within_allowed_stocks(self):
        df = pd.DataFrame({"stock_id": ["2330", "2330", "2382"]})
        assert_batch_stock_subset(df, ["2330", "2382", "6488"])  # 不得拋出

    def test_fails_when_foreign_stock_id_present(self):
        """known-FAIL：批次 DataFrame 含未授權股票——寫入前斷言必須擋下。"""
        df = pd.DataFrame({"stock_id": ["2330", "9999"]})
        with self.assertRaises(AssertionError):
            assert_batch_stock_subset(df, ["2330", "2382"])


class WriteOneBatchTests(unittest.TestCase):

    def test_calls_upsert_after_assertion_passes(self):
        db_writer = MagicMock()
        df = pd.DataFrame({"stock_id": ["2330"]})
        write_one_batch(db_writer, df, ["2330"])
        db_writer.upsert_ml_features.assert_called_once_with(df)

    def test_does_not_call_upsert_when_assertion_fails(self):
        """known-FAIL：寫入前斷言失敗時，`upsert_ml_features` 完全不得被呼叫。"""
        db_writer = MagicMock()
        df = pd.DataFrame({"stock_id": ["9999"]})
        with self.assertRaises(AssertionError):
            write_one_batch(db_writer, df, ["2330"])
        db_writer.upsert_ml_features.assert_not_called()


class RunFeaturesBackfillTests(unittest.TestCase):

    def _make_df(self, stock_ids):
        return pd.DataFrame({
            "stock_id": stock_ids,
            "trade_date": ["2026-01-01"] * len(stock_ids),
        })

    def test_batch_failure_stops_before_next_batch(self):
        """**known-FAIL 要求**：第 2 批核對失敗時，第 3 批**完全不得被
        `upsert_ml_features` 呼叫**——不是「記錄失敗後繼續」，是「立即停止」。
        """
        db_writer = MagicMock()
        conn = MagicMock()
        batches = [["A"], ["B"], ["C"]]
        df_features = self._make_df(["A", "B", "C"])

        results = {
            "A": (True, "OK"),
            "B": (False, "(c) 全表標籤計數不符：實際 (3500, 184)，預期 (3529, 184)"),
            "C": (True, "OK"),
        }

        def fake_verify(conn_, batch_stock_ids, df_batch, expected_label_counts=None):
            return results[batch_stock_ids[0]]

        with patch(
            "scripts.verify.ug_g3_sb2a_backfill_features.verify_batch_after_write",
            side_effect=fake_verify,
        ):
            completed, failed_at = run_features_backfill(
                db_writer, conn, batches, df_features)

        self.assertEqual(completed, [1], "只有批次 1 核對通過並列入已完成")
        self.assertEqual(failed_at, 2)
        self.assertEqual(
            db_writer.upsert_ml_features.call_count, 2,
            "批次 1、2 各呼叫一次寫入（批次 2 核對失敗發生在寫入之後）；"
            "批次 3 完全不得被呼叫")

    def test_all_batches_succeed_returns_no_failure(self):
        """對照組：全部批次核對通過時，`failed_at` 為 `None`，
        `completed` 含全部批次編號。"""
        db_writer = MagicMock()
        conn = MagicMock()
        batches = [["A"], ["B"], ["C"]]
        df_features = self._make_df(["A", "B", "C"])

        with patch(
            "scripts.verify.ug_g3_sb2a_backfill_features.verify_batch_after_write",
            return_value=(True, "OK"),
        ):
            completed, failed_at = run_features_backfill(
                db_writer, conn, batches, df_features)

        self.assertEqual(completed, [1, 2, 3])
        self.assertIsNone(failed_at)
        self.assertEqual(db_writer.upsert_ml_features.call_count, 3)


class VerifyBatchAfterWriteLabelRegressionTests(unittest.TestCase):

    def test_full_table_label_count_regression_detected_as_fail(self):
        """**known-FAIL 要求**：(a) 列數、(b) 抽樣回讀皆通過，但 (c) 全表
        標籤計數與預期不符時，整體核對必須回傳 `False` 並在說明中指出是
        (c) 這一項——不是被 (a)/(b) 誤判擋下。"""
        df_batch = pd.DataFrame({"trade_date": ["2026-01-01"], "stock_id": ["2330"]})
        for col in COMPARE_COLUMNS:
            df_batch[col] = "SUCCESS" if col == "source_status" else 0.0

        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor

        row_values = tuple(df_batch.iloc[0][col] for col in COMPARE_COLUMNS)

        cursor.fetchall.side_effect = [
            [("2330", 1)],  # (a) daily_ml_features 該批逐股列數
            [("2330", 1)],  # (a) stock_prices 該批逐股列數——相符，通過 (a)
        ]
        cursor.fetchone.side_effect = [
            row_values,   # (b) 抽樣回讀——與 df_batch 完全相同，通過 (b)
            (999, 184),   # (c) 全表標籤計數——target_triple_barrier 不符
        ]

        ok, detail = verify_batch_after_write(conn, ["2330"], df_batch)

        self.assertFalse(ok)
        self.assertIn("(c)", detail, "失敗原因必須指出是全表標籤計數這一項")

    def test_passes_when_all_three_checks_agree(self):
        """對照組：(a)(b)(c) 皆相符時回傳 `(True, "OK")`。"""
        df_batch = pd.DataFrame({"trade_date": ["2026-01-01"], "stock_id": ["2330"]})
        for col in COMPARE_COLUMNS:
            df_batch[col] = "SUCCESS" if col == "source_status" else 0.0

        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor

        row_values = tuple(df_batch.iloc[0][col] for col in COMPARE_COLUMNS)

        cursor.fetchall.side_effect = [
            [("2330", 1)],
            [("2330", 1)],
        ]
        cursor.fetchone.side_effect = [
            row_values,
            (3529, 184),
        ]

        ok, detail = verify_batch_after_write(conn, ["2330"], df_batch)

        self.assertTrue(ok)
        self.assertEqual(detail, "OK")


class PreviewZeroWriteTests(unittest.TestCase):
    """段 3 唯讀預覽模式的零寫入保證——`main()` 的 `if not write: ...;
    return` 必須在任何 `run_features_backfill` 呼叫之前，結構上不可能
    觸發寫入。"""

    class _SentinelWriteCalled(Exception):
        pass

    def _run_with_mocks(self, write, mutate=False):
        """`mutate=True` 時，**在 patch 生效之後**才對 `main()` 做
        `inspect.getsource()` + `exec()` 變異——`namespace = dict(vars(mod))`
        必須讀到已被 patch 換成 `MagicMock` 的 `psycopg2`，否則變異函式會
        綁到 patch 之前的真實 `psycopg2` 模組物件，變成真的嘗試連線
        （曾經踩過這個坑：先在 patch 外建立 namespace 快照，results in
        `psycopg2.OperationalError: role "u" does not exist`——不是 guard
        失效，是 mock 沒套用到）。"""
        import scripts.verify.ug_g3_sb2a_backfill_features as mod

        df_fake = pd.DataFrame({
            "stock_id": ["2330"],
            "trade_date": ["2026-01-01"],
            "sentiment_mean": [None],
            "source_status": ["SUCCESS_EMPTY"],
        })

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "POSTGRES_DB": "testdb", "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "<test>",
            }))
            mock_psycopg2 = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.psycopg2"))
            mock_recompute = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "recompute_features_full"))
            mock_fetch_prices = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "fetch_all_prices"))
            stack.enter_context(patch("builtins.input", return_value="testdb"))
            # 常數過期守衛與唯讀預覽不變式（審查員 2026-09-11 複核追加）不是
            # 本測試要驗證的對象——本測試只關心 write=False 是否會進入寫入
            # 路徑，所以直接 mock 成「通過」，避免 MagicMock 的 cursor 回傳值
            # 被 check_total_row_count 等函式拿去做真的比較而意外導致提早
            # sys.exit(1)（那樣會讓這個測試看似「正確擋下」，但擋下的理由
            # 錯了，不是在測 write=False 這個 guard 本身）。
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_total_row_count",
                return_value=(True, EXISTING_ROWS_BEFORE)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_label_counts",
                return_value=(True, EXPECTED_LABEL_COUNTS)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_invariants",
                return_value={}))
            mock_run_backfill = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.run_features_backfill",
                side_effect=self._SentinelWriteCalled))

            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            mock_conn.cursor.return_value.fetchone.return_value = (
                "testdb", "u", 5432)
            mock_recompute.return_value = df_fake
            mock_fetch_prices.return_value = df_fake[["stock_id", "trade_date"]].copy()

            if mutate:
                source = inspect.getsource(mod.main)
                assert "if not write:" in source, "前提：原始碼裡確實有這個 guard 可供變異"
                mutated_source = source.replace("if not write:", "if False:", 1)
                assert mutated_source != source
                namespace = dict(vars(mod))
                exec(compile(mutated_source, "<mutated_main>", "exec"), namespace)
                main_func = namespace["main"]
            else:
                main_func = mod.main

            reached_write_path = False
            try:
                main_func(write=write, backup_path=None)
            except self._SentinelWriteCalled:
                reached_write_path = True

            return reached_write_path, mock_run_backfill

    def test_preview_mode_never_reaches_write_path(self):
        reached, mock_run_backfill = self._run_with_mocks(write=False, mutate=False)

        self.assertFalse(
            reached, "write=False 時，main() 絕不得進入 run_features_backfill")
        mock_run_backfill.assert_not_called()

    def test_guard_removed_is_load_bearing(self):
        """**known-FAIL 案例**：把 `main()` 原始碼裡的 `if not write:` 改成
        `if False:`（guard 永遠不觸發），用同一套 mock 重跑——必須真的
        「進入」寫入路徑（被安插的哨兵例外攔下），證明原本的 guard 確實是
        承重的，不是碰巧通過。手法比照
        `tests/test_sb2a_backfill_candidate_prices_gap.py` 的
        `test_stopping_is_load_bearing`：`inspect.getsource()` 取出本體、
        只動一個關鍵字、`exec` 成獨立函式後跑同一套斷言。"""
        reached, _ = self._run_with_mocks(write=False, mutate=True)

        self.assertTrue(
            reached,
            "變異版本（guard 失效）即使 write=False 也會進入 "
            "run_features_backfill——證明原本的 guard 是承重的，"
            "移除後行為真的不同")


class ExistingStateGuardTests(unittest.TestCase):
    """常數過期守衛（審查員 2026-09-11 複核追加）：`EXISTING_ROWS_BEFORE`／
    `EXPECTED_LABEL_COUNTS` 與真實庫現況不符時，`main()` 必須在做任何進一步
    計算或寫入之前就 `sys.exit(1)`——常數可能已過期，不得沿用繼續往下跑。"""

    def _run_expect_exit(self, row_check_result, label_check_result):
        import scripts.verify.ug_g3_sb2a_backfill_features as mod

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "POSTGRES_DB": "testdb", "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "<test>",
            }))
            mock_psycopg2 = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.psycopg2"))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_total_row_count",
                return_value=row_check_result))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_label_counts",
                return_value=label_check_result))
            mock_recompute = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "recompute_features_full"))

            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            mock_conn.cursor.return_value.fetchone.return_value = (
                "testdb", "u", 5432)

            with self.assertRaises(SystemExit) as ctx:
                mod.main(write=False, backup_path=None)

            return ctx.exception, mock_recompute

    def test_row_count_mismatch_stops_before_any_computation(self):
        """known-FAIL：`EXISTING_ROWS_BEFORE` 過期（真實庫列數已經不是
        寫死的常數）時，連 `recompute_features_full`（~7 秒的全量計算）
        都不該被呼叫——不是算完才發現常數錯了，是先擋下。"""
        exc, mock_recompute = self._run_expect_exit(
            row_check_result=(False, 999999),
            label_check_result=(True, EXPECTED_LABEL_COUNTS))
        self.assertEqual(exc.code, 1)
        mock_recompute.assert_not_called()

    def test_label_count_mismatch_stops_before_any_computation(self):
        """known-FAIL：`EXPECTED_LABEL_COUNTS` 過期時同樣先擋下。"""
        exc, mock_recompute = self._run_expect_exit(
            row_check_result=(True, EXISTING_ROWS_BEFORE),
            label_check_result=(False, (0, 0)))
        self.assertEqual(exc.code, 1)
        mock_recompute.assert_not_called()

    def test_both_constants_matching_does_not_stop_here(self):
        """對照組：常數與現況相符時，這道守衛本身必須放行，繼續往下跑到
        `recompute_features_full`——用 `side_effect` 拋出可辨識的例外當
        「有沒有跑到這裡」的哨兵，不必把後面整個 main() 流程都 mock 完。"""
        import scripts.verify.ug_g3_sb2a_backfill_features as mod

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "POSTGRES_DB": "testdb", "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "<test>",
            }))
            mock_psycopg2 = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.psycopg2"))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_total_row_count",
                return_value=(True, EXISTING_ROWS_BEFORE)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_label_counts",
                return_value=(True, EXPECTED_LABEL_COUNTS)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "recompute_features_full",
                side_effect=RuntimeError("REACHED_RECOMPUTE")))

            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            mock_conn.cursor.return_value.fetchone.return_value = (
                "testdb", "u", 5432)

            with self.assertRaises(RuntimeError) as ctx:
                mod.main(write=False, backup_path=None)
            self.assertEqual(str(ctx.exception), "REACHED_RECOMPUTE")


class PreviewInvariantGuardTests(unittest.TestCase):
    """審查員 2026-09-11 複核追加：唯讀預覽階段先對記憶體中的 `df_features`
    跑一次 7 項不變式（不必等寫入完成才驗證正確性），任一項違規即
    `sys.exit(1)`，連 `--write` 都不授權——唯讀預覽本身就是寫入前證據，
    不只是數字預告。"""

    def test_invariant_violation_in_preview_stops_before_preview_output(self):
        """known-FAIL：不變式違規時，連 `preview_features_backfill`（印
        批次清單與分布快照）都不該被呼叫——不是印完數字才發現算錯了。"""
        import scripts.verify.ug_g3_sb2a_backfill_features as mod

        df_fake = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": ["2026-01-01"],
            "sentiment_mean": [None], "source_status": ["SUCCESS_EMPTY"],
        })

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "POSTGRES_DB": "testdb", "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "<test>",
            }))
            mock_psycopg2 = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.psycopg2"))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_total_row_count",
                return_value=(True, EXISTING_ROWS_BEFORE)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_label_counts",
                return_value=(True, EXPECTED_LABEL_COUNTS)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "recompute_features_full", return_value=df_fake))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "fetch_all_prices",
                return_value=df_fake[["stock_id", "trade_date"]].copy()))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_invariants",
                return_value={"source_status_enum": df_fake}))
            mock_preview_print = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features."
                "preview_features_backfill"))

            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            mock_conn.cursor.return_value.fetchone.return_value = (
                "testdb", "u", 5432)

            with self.assertRaises(SystemExit) as ctx:
                mod.main(write=False, backup_path=None)

            self.assertEqual(ctx.exception.code, 1)
            mock_preview_print.assert_not_called()

    def test_invariants_passing_does_not_stop_here(self):
        """對照組：不變式全過時，這道守衛放行，繼續跑到
        `preview_features_backfill`。"""
        import scripts.verify.ug_g3_sb2a_backfill_features as mod

        df_fake = pd.DataFrame({
            "stock_id": ["2330"], "trade_date": ["2026-01-01"],
            "sentiment_mean": [None], "source_status": ["SUCCESS_EMPTY"],
        })

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "POSTGRES_DB": "testdb", "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "<test>",
            }))
            mock_psycopg2 = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.psycopg2"))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_total_row_count",
                return_value=(True, EXISTING_ROWS_BEFORE)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_label_counts",
                return_value=(True, EXPECTED_LABEL_COUNTS)))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "recompute_features_full", return_value=df_fake))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_stage2_baseline_comparison."
                "fetch_all_prices",
                return_value=df_fake[["stock_id", "trade_date"]].copy()))
            stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features.check_invariants",
                return_value={}))
            mock_preview_print = stack.enter_context(patch(
                "scripts.verify.ug_g3_sb2a_backfill_features."
                "preview_features_backfill"))

            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            mock_conn.cursor.return_value.fetchone.return_value = (
                "testdb", "u", 5432)

            mod.main(write=False, backup_path=None)

            mock_preview_print.assert_called_once()


class InvariantChecksTests(unittest.TestCase):
    """7 項不變式，每項至少一個會 FAIL 的已實測案例（`CLAUDE.md` §9A.2）。
    「應通過」的基準資料一律**用實際生產函式算出**（`compute_rsi`／
    `compute_rolling_volatility`／`feature_aggregator` 的公式），不手填猜測
    值——避免『基準本身就是錯的、檢查永遠通不過』（§9A.1 的鏡像風險）。"""

    def _build_consistent_df(self):
        from src.transform.feature_aggregator import (
            compute_rsi, compute_rolling_volatility)

        closes = pd.Series([100.0, 102.0, 101.0, 105.0, 107.0])
        dates = list(pd.date_range("2026-01-01", periods=5).date)
        df = pd.DataFrame({
            "trade_date": dates,
            "stock_id": ["2330"] * 5,
            "close_price": closes.values,
            "volume": [1000, 1100, 1050, 1200, 1300],
            "article_count": [1.0, 0.0, 2.0, 0.0, 1.0],
            "sentiment_mean": [0.5, np.nan, 0.3, np.nan, 0.7],
            "source_status": ["SUCCESS", "SUCCESS_EMPTY", "SUCCESS",
                               "SUCCESS_EMPTY", "SUCCESS"],
        })
        df["return_1d"] = np.log(closes / closes.shift(1)).fillna(0.0).values
        df["rsi_14"] = compute_rsi(closes, period=14).values
        df["volatility_5d"] = compute_rolling_volatility(
            df["return_1d"], window=5, annualize=True).values
        df["volatility_20d"] = compute_rolling_volatility(
            df["return_1d"], window=20, annualize=True).values
        df["target_next_close"] = closes.shift(-1).values
        df["target_return_1d"] = np.log(
            df["target_next_close"].astype(float) / closes.astype(float)).values
        df["target_up_down"] = df["target_return_1d"].apply(
            lambda r: 1 if r > 0 else (0 if pd.notna(r) else np.nan)).values
        return df

    # ---- price_consistency ----

    def test_price_consistency_detects_mismatch(self):
        df_features = self._build_consistent_df()
        df_prices = df_features[["trade_date", "stock_id", "close_price", "volume"]].copy()
        df_prices.loc[0, "close_price"] = 999.0
        bad = check_price_consistency(df_features, df_prices)
        self.assertFalse(bad.empty)

    def test_price_consistency_passes_when_consistent(self):
        df_features = self._build_consistent_df()
        df_prices = df_features[["trade_date", "stock_id", "close_price", "volume"]].copy()
        bad = check_price_consistency(df_features, df_prices)
        self.assertTrue(bad.empty)

    # ---- return_1d ----

    def test_return_1d_detects_wrong_formula(self):
        df = self._build_consistent_df()
        df.loc[1, "return_1d"] = 0.999
        bad = check_return_1d(df)
        self.assertFalse(bad.empty)

    def test_return_1d_passes_when_correct(self):
        df = self._build_consistent_df()
        bad = check_return_1d(df)
        self.assertTrue(bad.empty)

    # ---- target_consistency ----

    def test_target_consistency_detects_break(self):
        df = self._build_consistent_df()
        df.loc[0, "target_up_down"] = 0.0  # 實際 r>0，應為 1
        bad = check_target_consistency(df)
        self.assertFalse(bad.empty)

    def test_target_consistency_passes_when_correct(self):
        df = self._build_consistent_df()
        bad = check_target_consistency(df)
        self.assertTrue(bad.empty)

    # ---- rsi_consistency ----

    def test_rsi_consistency_detects_break(self):
        df = self._build_consistent_df()
        df["rsi_14"] = [12.3, 45.6, 78.9, 11.1, 22.2]
        bad = check_rsi_consistency(df)
        self.assertFalse(bad.empty)

    def test_rsi_consistency_passes_when_correct(self):
        df = self._build_consistent_df()
        bad = check_rsi_consistency(df)
        self.assertTrue(bad.empty)

    # ---- volatility_consistency ----

    def test_volatility_consistency_detects_break(self):
        df = self._build_consistent_df()
        df.loc[3, "volatility_5d"] = 999.0
        bad = check_volatility_consistency(df)
        self.assertFalse(bad.empty)

    def test_volatility_consistency_passes_when_correct(self):
        df = self._build_consistent_df()
        bad = check_volatility_consistency(df)
        self.assertTrue(bad.empty)

    # ---- source_status_enum ----

    def test_source_status_enum_detects_invalid_value(self):
        df = self._build_consistent_df()
        df.loc[0, "source_status"] = "BOGUS_STATUS"
        bad = check_source_status_enum(df)
        self.assertFalse(bad.empty)

    def test_source_status_enum_passes_for_allowed_values(self):
        df = self._build_consistent_df()
        bad = check_source_status_enum(df)
        self.assertTrue(bad.empty)

    # ---- sentiment_null_iff_article_zero ----

    def test_sentiment_null_iff_article_zero_detects_break(self):
        df = self._build_consistent_df()
        df.loc[1, "article_count"] = 0.0
        df.loc[1, "sentiment_mean"] = 0.5  # article_count=0 但 sentiment_mean 非 NULL
        bad = check_sentiment_null_iff_article_zero(df)
        self.assertFalse(bad.empty)

    def test_sentiment_null_iff_article_zero_passes_when_correct(self):
        df = self._build_consistent_df()
        bad = check_sentiment_null_iff_article_zero(df)
        self.assertTrue(bad.empty)

    def test_sentiment_null_iff_article_zero_ignores_source_failed_rows(self):
        """`SOURCE_FAILED` 列的 `article_count` 契約上保持 NULL（非 0）——
        本不變式必須排除這類列，否則會對合法狀態誤判違規。"""
        df = self._build_consistent_df()
        df.loc[1, "source_status"] = "SOURCE_FAILED"
        df.loc[1, "article_count"] = np.nan
        df.loc[1, "sentiment_mean"] = np.nan
        bad = check_sentiment_null_iff_article_zero(df)
        self.assertTrue(bad.empty, "SOURCE_FAILED 列不適用本不變式，不應被判違規")

    # ---- 聚合 ----

    def test_check_invariants_returns_empty_dict_when_all_pass(self):
        df_features = self._build_consistent_df()
        df_prices = df_features[["trade_date", "stock_id", "close_price", "volume"]].copy()
        result = check_invariants(df_features, df_prices)
        self.assertEqual(result, {})

    def test_check_invariants_reports_only_broken_ones(self):
        df_features = self._build_consistent_df()
        df_features.loc[0, "source_status"] = "BOGUS_STATUS"
        df_prices = df_features[["trade_date", "stock_id", "close_price", "volume"]].copy()
        result = check_invariants(df_features, df_prices)
        self.assertEqual(set(result.keys()), {"source_status_enum"},
                          "只有真正違規的項目該出現在結果字典裡")


if __name__ == "__main__":
    unittest.main()
