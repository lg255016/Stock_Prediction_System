# -*- coding: utf-8 -*-
"""
UG-G3-SB1（Triple-Barrier Labeling）紅色測試。

規格來源：`doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §4、
`doc/upgrade/gates/UG_G3_SB1_GATE_A_PROPOSAL.md` §6.2/§7（PO 2026-09-09 核准）。

本檔在 `src/ml/triple_barrier.py` 存在前撰寫（`CLAUDE.md` §14「新增 bug fix /
功能時應先建立會重現問題的測試」的正向適用——先寫紅，後寫綠）。
本次執行預期為 RED（`ModuleNotFoundError` 或全部測試 FAIL），紅色本身即為證據，
以 commit 方式留下 git 歷史事實，之後才寫 `src/ml/triple_barrier.py` 使其轉綠。

十一項既有測試（Master Plan §9 UG-G3-SB1 Brief 既列）+ 兩項本提案追加
（`test_tb_label_reason_invariant`、`test_tb_purge_boundary_with_h5`）+
一項 PO 2026-09-09 語意裁定追加（`test_tb_insufficient_data_overrides_early_touch`）。

**語意裁定（PO 2026-09-09）**：規格 §4.3 原表第 1～2 列（先觸線即定 1/−1）與
第 5 列（資料集最後 H 個交易日一律 NULL）在「末 H 日內、但部分窗口已觸線」
的情況下互相矛盾。裁定採**字面規則**：只要剩餘天數 < holding_period，
一律 NULL + `insufficient_data`，即使剩餘天數內已可觀察到觸線——
理由是「先觸即定」會讓每檔序列尾端只可能出現 ±1 或 NULL（觸線可觀測、
到期不可觀測的截斷偏差），字面規則把這個偏差整段消掉，與「算不出來就是
NULL」的一貫原則同向。
"""
import unittest

import numpy as np
import pandas as pd

from src.ml.triple_barrier import generate_triple_barrier_labels
from src.ml.time_series_split import WalkForwardSplitter

UPPER_WIDTH = 0.02   # 規格 §4.2 Static 預設
LOWER_WIDTH = 0.015  # 規格 §4.2 Static 預設
HOLDING_PERIOD = 5   # 規格 §4.2 H = 5


def _mk_df(stock_id, rows):
    """
    rows: list[dict]，每個 dict 含 open/high/low（close 可選）。
    trade_date 以 `pd.bdate_range` 合成，僅需嚴格遞增，不對應真實交易日曆。
    """
    n = len(rows)
    dates = pd.bdate_range("2026-01-01", periods=n).strftime("%Y-%m-%d")
    data = {
        "stock_id": [stock_id] * n,
        "trade_date": dates,
        "open_price": [r["open"] for r in rows],
        "high_price": [r["high"] for r in rows],
        "low_price": [r["low"] for r in rows],
    }
    if any("close" in r for r in rows):
        data["close_price"] = [r.get("close", np.nan) for r in rows]
    return pd.DataFrame(data)


class TripleBarrierLabelingTests(unittest.TestCase):
    """UG-G3-SB1：Triple-Barrier 三分類標籤（PURGED_WALK_FORWARD_SPEC.md §4）。"""

    def test_tb_upper_barrier(self):
        """T+1~T+5 期間先觸及 upper barrier → label = 1（規格 §4.3 第一列）。"""
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T
            {"open": 100, "high": 103, "low": 99},    # T+1 = anchor 100；觸 upper(102)，未觸 lower(98.5)
            {"open": 101, "high": 101, "low": 100},   # T+2
            {"open": 101, "high": 101, "low": 100},   # T+3
            {"open": 101, "high": 101, "low": 100},   # T+4
            {"open": 101, "high": 101, "low": 100},   # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertEqual(result.loc[0, "target_triple_barrier"], 1)
        self.assertTrue(pd.isna(result.loc[0, "label_reason"]))

    def test_tb_lower_barrier(self):
        """T+1~T+5 期間先觸及 lower barrier → label = -1（規格 §4.3 第二列）。"""
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T
            {"open": 100, "high": 101, "low": 98},    # T+1 = anchor 100；觸 lower(98.5)，未觸 upper(102)
            {"open": 100, "high": 100, "low": 99},    # T+2
            {"open": 100, "high": 100, "low": 99},    # T+3
            {"open": 100, "high": 100, "low": 99},    # T+4
            {"open": 100, "high": 100, "low": 99},    # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertEqual(result.loc[0, "target_triple_barrier"], -1)
        self.assertTrue(pd.isna(result.loc[0, "label_reason"]))

    def test_tb_timeout(self):
        """T+1~T+5 期間未觸及任一 barrier → label = 0（Timeout，規格 §4.3 第三列）。"""
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T
            {"open": 100, "high": 101, "low": 99.5},  # T+1 = anchor 100；未觸 upper(102)/lower(98.5)
            {"open": 100, "high": 101, "low": 99.5},  # T+2
            {"open": 100, "high": 101, "low": 99.5},  # T+3
            {"open": 100, "high": 101, "low": 99.5},  # T+4
            {"open": 100, "high": 101, "low": 99.5},  # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertEqual(result.loc[0, "target_triple_barrier"], 0)
        self.assertTrue(pd.isna(result.loc[0, "label_reason"]))

    def test_tb_ambiguous_null(self):
        """同一日同時觸及 upper 與 lower → label = NULL，label_reason = 'ambiguous_dual_barrier'。"""
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T
            {"open": 100, "high": 101, "low": 99.5},  # T+1 = anchor 100；未觸任一 barrier
            {"open": 100, "high": 103, "low": 98},    # T+2：同日觸 upper(102) 與 lower(98.5)
            {"open": 100, "high": 100, "low": 100},   # T+3
            {"open": 100, "high": 100, "low": 100},   # T+4
            {"open": 100, "high": 100, "low": 100},   # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertTrue(pd.isna(result.loc[0, "target_triple_barrier"]))
        self.assertEqual(result.loc[0, "label_reason"], "ambiguous_dual_barrier")

    def test_tb_last_h_days_null(self):
        """資料集最後 H 個交易日（Open[T+1] 存在但不足 5 天窗口）→ NULL，'insufficient_data'。"""
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T：之後僅剩 2 列（< holding_period=5）
            {"open": 100, "high": 101, "low": 99.5},  # T+1（存在，故非 no_entry）
            {"open": 100, "high": 101, "low": 99.5},  # T+2（資料集到此結束）
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertTrue(pd.isna(result.loc[0, "target_triple_barrier"]))
        self.assertEqual(result.loc[0, "label_reason"], "insufficient_data")

    def test_tb_label_end_date(self):
        """`label_end_date_tb` = trade_date[T + holding_period]；視野外為 NaT（同 label_end_date 既有慣例）。"""
        rows = [{"open": 100, "high": 100, "low": 100} for _ in range(8)]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        # T = index 0，T+5 = index 5：full window 存在
        self.assertEqual(result.loc[0, "label_end_date_tb"], df.loc[5, "trade_date"])
        # T = index 5，T+5 = index 10 不存在（僅到 index 7）→ NaT
        self.assertTrue(pd.isna(result.loc[5, "label_end_date_tb"]))

    def test_tb_anchor_is_next_open(self):
        """Anchor 必須是 Open[T+1]，不是 Close[T]——用兩者代入會得到相反標籤的資料辨別。"""
        rows = [
            {"open": 100, "high": 100, "low": 100, "close": 110},  # T：Close[T]=110（若誤用會使 barrier 大幅偏移）
            {"open": 100, "high": 103, "low": 99},                 # T+1：正確 anchor=Open[T+1]=100
            {"open": 100, "high": 100, "low": 100},                # T+2
            {"open": 100, "high": 100, "low": 100},                # T+3
            {"open": 100, "high": 100, "low": 100},                # T+4
            {"open": 100, "high": 100, "low": 100},                # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        # anchor=100 時：upper=102，high=103 觸 upper → label=1
        # 若誤用 Close[T]=110：upper=112.2，未觸；lower=108.35，low=99 觸 lower → label=-1（相反結論）
        self.assertEqual(result.loc[0, "target_triple_barrier"], 1)

    def test_tb_no_entry_when_open_missing(self):
        """`Open[T+1]` 不存在（資料集最後一列，無下一列）→ NULL，label_reason = 'no_entry'。"""
        rows = [{"open": 100, "high": 100, "low": 100} for _ in range(6)]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        last_idx = len(df) - 1
        self.assertTrue(pd.isna(result.loc[last_idx, "target_triple_barrier"]))
        self.assertEqual(result.loc[last_idx, "label_reason"], "no_entry")

    def test_tb_label_domain(self):
        """值域僅 `{-1, 0, 1}` 或 NULL，無其他值——較大合成資料集上逐值檢查。"""
        rng = np.random.RandomState(42)
        n = 60
        base = 100 + np.cumsum(rng.normal(0, 1, n))
        rows = []
        for b in base:
            o = b
            h = b + abs(rng.normal(0, 2))
            l = b - abs(rng.normal(0, 2))
            rows.append({"open": o, "high": h, "low": l})
        df = pd.concat([
            _mk_df("2330", rows),
            _mk_df("2382", rows),
        ], ignore_index=True)
        result = generate_triple_barrier_labels(df)

        observed = set(result["target_triple_barrier"].dropna().unique().tolist())
        self.assertTrue(observed.issubset({-1, 0, 1}))
        self.assertGreater(result["target_triple_barrier"].notna().sum(), 0)

    def test_tb_stop_loss_distinct_from_timeout(self):
        """止損 (-1) 與未觸線 (0) 不得合併——同一測試內建構兩個各自不相混的案例。"""
        timeout_rows = [
            {"open": 100, "high": 100, "low": 100},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
        ]
        stop_loss_rows = [
            {"open": 100, "high": 100, "low": 100},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 101, "low": 99.5},
            {"open": 100, "high": 100.5, "low": 98},  # T+5：僅此日觸及 lower(98.5)
        ]
        df = pd.concat([
            _mk_df("TIMEOUT_STOCK", timeout_rows),
            _mk_df("STOPLOSS_STOCK", stop_loss_rows),
        ], ignore_index=True)
        result = generate_triple_barrier_labels(df)

        timeout_label = result.loc[result["stock_id"] == "TIMEOUT_STOCK", "target_triple_barrier"].iloc[0]
        stoploss_label = result.loc[result["stock_id"] == "STOPLOSS_STOCK", "target_triple_barrier"].iloc[0]

        self.assertEqual(timeout_label, 0)
        self.assertEqual(stoploss_label, -1)
        self.assertNotEqual(timeout_label, stoploss_label)

    def test_tb_entry_day_hit_counted(self):
        """T+1（進場日）當日觸線需計入，且邊界採「含等於」判定（規格 §4.2「含 T+1 當日」）。"""
        anchor = 100.0
        upper = anchor * (1 + UPPER_WIDTH)  # 與 §6.2 規格公式相同運算式，避免浮點誤差造成假陰性
        rows = [
            {"open": 100, "high": 100, "low": 100},          # T
            {"open": anchor, "high": upper, "low": 99},      # T+1：high 恰等於 upper（邊界）
            {"open": 100, "high": 100, "low": 100},          # T+2
            {"open": 100, "high": 100, "low": 100},          # T+3
            {"open": 100, "high": 100, "low": 100},          # T+4
            {"open": 100, "high": 100, "low": 100},          # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertEqual(result.loc[0, "target_triple_barrier"], 1)

    def test_tb_insufficient_data_overrides_early_touch(self):
        """
        PO 2026-09-09 語意裁定：資料集末 H 日內即使已觀察到觸線，仍優先判定為
        `insufficient_data`（NULL），不得因「先觸即定」而標為 1/−1。
        測資：資料在 T+2 結束（T 之後僅剩 2 列 < holding_period=5），且 T+1
        已明確觸及 upper barrier——若實作誤用「先觸即定」語意會錯標為 1。
        """
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T：之後僅剩 2 列（< holding_period=5）
            {"open": 100, "high": 103, "low": 99},    # T+1：anchor=100，已觸 upper(102)
            {"open": 100, "high": 100, "low": 100},   # T+2（資料集到此結束）
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertTrue(pd.isna(result.loc[0, "target_triple_barrier"]))
        self.assertEqual(result.loc[0, "label_reason"], "insufficient_data")

    def test_tb_anchor_nan_is_no_entry(self):
        """
        審查方發現（2026-09-09）：T+1 列存在但 `open_price` 為 NaN（anchor 無法判定）
        → NULL + 'no_entry'，不得因 NaN 比較恆為 False 而落入迴圈末端誤判為 0（Timeout）。
        對應規格 §4.6 偽碼「Open[T+1] is None → NULL + no_entry」，`stock_prices` 三個
        價格欄皆 nullable（`schema.sql`）。**【2026-09-09 訂正】** 原稿稱「現行真實庫
        3,713 列零 NULL」——該量測用 SQL `IS NULL`，查不到 NUMERIC 型別另有的
        `NaN` 值（`= 'NaN'::numeric` 才找得到）。真實庫確有 1 列（NVDA 2026-06-04）
        四個價格欄皆為 NUMERIC NaN，非「潛伏、未觀察」的假設案例——已登記
        RISK-024（`REMAINING_RISKS.md`），本測試對應的正是這筆真實資料會走的路徑。
        """
        rows = [
            {"open": 100, "high": 100, "low": 100},          # T
            {"open": np.nan, "high": 101, "low": 99},          # T+1：open_price NaN，anchor 無法判定
            {"open": 100, "high": 100, "low": 100},            # T+2
            {"open": 100, "high": 100, "low": 100},            # T+3
            {"open": 100, "high": 100, "low": 100},            # T+4
            {"open": 100, "high": 100, "low": 100},            # T+5
            {"open": 100, "high": 100, "low": 100},            # T+6（緩衝，確保 remaining>=holding_period）
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertTrue(pd.isna(result.loc[0, "target_triple_barrier"]))
        self.assertEqual(result.loc[0, "label_reason"], "no_entry")

    def test_tb_window_nan_is_insufficient_data(self):
        """
        審查方發現（2026-09-09）：評估窗口內任一日 `high_price`／`low_price` 為 NaN
        → NULL + 'insufficient_data'（沿用既有原則「算不出來就是 NULL」，不新增
        reason 值、不動 migration 002 的 CHECK 域）。**順序要求**：NaN 檢查須在
        觸線判定之前——本測試刻意讓 NaN 那一日的「另一側」（low）本身會觸及
        lower barrier，若實作誤判順序（先判觸線、NaN 恆 False 才略過）會錯誤
        產出 -1，而非正確的 NULL + insufficient_data。
        """
        rows = [
            {"open": 100, "high": 100, "low": 100},   # T
            {"open": 100, "high": 101, "low": 99.5},  # T+1：anchor=100，未觸任一 barrier
            {"open": 100, "high": 101, "low": 99.5},  # T+2：未觸
            {"open": 100, "high": np.nan, "low": 98},  # T+3：high NaN；low=98 若單獨判會觸 lower(98.5)
            {"open": 100, "high": 100, "low": 100},   # T+4
            {"open": 100, "high": 100, "low": 100},   # T+5
        ]
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        self.assertTrue(pd.isna(result.loc[0, "target_triple_barrier"]))
        self.assertEqual(result.loc[0, "label_reason"], "insufficient_data")

    def test_tb_label_reason_invariant(self):
        """不變式：`label_reason IS NULL ⟺ target_triple_barrier IS NOT NULL`（DB CHECK 同款邏輯，逐列成立）。"""
        rng = np.random.RandomState(7)
        n = 40
        base = 100 + np.cumsum(rng.normal(0, 1, n))
        rows = []
        for b in base:
            o = b
            h = b + abs(rng.normal(0, 2))
            l = b - abs(rng.normal(0, 2))
            rows.append({"open": o, "high": h, "low": l})
        df = _mk_df("2330", rows)
        result = generate_triple_barrier_labels(df)

        label_is_null = result["target_triple_barrier"].isna()
        reason_is_null = result["label_reason"].isna()
        # label_reason 為 NULL 若且唯若 target_triple_barrier 非 NULL
        self.assertTrue((reason_is_null == ~label_is_null).all())

    def test_tb_purge_boundary_with_h5(self):
        """
        UG-G3-SB1 §3／§7 追加項：`label_end_date_tb` 供 `WalkForwardSplitter(label_horizon=5,
        label_end_date_col='label_end_date_tb')` 正確 purge 訓練集尾端 5 天——把 Gate A §3
        的量測落地為可執行檢查，而非只停在文件量測。對應規格 §2.2 H=5 範例的同型驗證
        （T-PW-02 的自訂欄位名版本）。
        """
        rng = np.random.RandomState(3)
        n = 40
        base = 100 + np.cumsum(rng.normal(0, 1, n))
        rows = [{"open": b, "high": b + 1, "low": b - 1} for b in base]
        df = _mk_df("2330", rows)
        labeled = generate_triple_barrier_labels(df)

        self.assertIn("label_end_date_tb", labeled.columns)

        splitter = WalkForwardSplitter(
            train_window_size=10, test_window_size=5, step_size=5,
            mode="rolling", label_horizon=5, min_train_size=1,
            label_end_date_col="label_end_date_tb",
        )
        train_idx, test_idx, meta = next(splitter.split(labeled))

        self.assertEqual(meta["purged_days"], 5)
        self.assertEqual(meta["train_days"], 5)  # train_window(10) - purge(5)

        train_dates = set(labeled.iloc[train_idx]["trade_date"])
        # 未 Purge 前訓練窗尾端為第 10 天 (index 9)；H=5 應清空 index 5~9
        for purged_pos in range(5, 10):
            self.assertNotIn(labeled.loc[purged_pos, "trade_date"], train_dates)
        for kept_pos in range(0, 5):
            self.assertIn(labeled.loc[kept_pos, "trade_date"], train_dates)


if __name__ == "__main__":
    unittest.main()
