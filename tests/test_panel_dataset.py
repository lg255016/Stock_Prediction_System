# -*- coding: utf-8 -*-
"""
UG-G3-SB2（Panel Dataset 構建）紅色測試。

規格來源：`doc/upgrade/gates/UG_G3_SB2_GATE_A_PROPOSAL.md` §5/§6（PO 2026-09-09 核准）。

本檔在 `src/ml/panel_dataset.py` 存在前撰寫（`CLAUDE.md` §14 先寫紅、後寫綠）。
本次執行預期為 RED（`ModuleNotFoundError`／`ImportError`），紅色本身即為證據，
以 commit 方式留下 git 歷史事實，之後才寫綠色實作。

十三項測試：八項面板讀取器（`build_panel_dataset()`）+ 五項每日尾端重算掛點
（`recompute_tail_labels()`／`apply_tail_labels()`，新增於既有
`src/ml/triple_barrier.py`）。PO 2026-09-09 複審後追加五項（idempotent 測試
改走 `apply_tail_labels()` 而非直接比對純函式兩次呼叫；H+1 邊界改為由建構
證明，不是宣告；補「首期快照之前的日期不得默默納入」；補「掛點必須逐股票
處理，不得全域 tail() 或只用 trade_date 當合併鍵」；補「`label_reason` 全
NaN float64 欄位的 dtype 陷阱」）。

**設計契約（供綠色實作對照）**：
- `build_panel_dataset(df_universe_snapshots, df_daily_ml_features, df_stock_prices,
  target_column="target_up_down", as_of=None) -> pd.DataFrame`
  - Universe 過濾：每個 `trade_date`，取 `effective_date <= trade_date` 的最近一期
    `included=True` 股票清單（PIT，非最新一期、非矩形）。**`trade_date` 早於
    最早一期 `effective_date` 時無任何可用名單，該列不得出現在面板**（不得
    默默沿用第一期回填）。
  - **刻意不接受 `df_entity_mapping` 參數**——這本身就是「不受 entity_mapping 是否
    有路由列影響」的設計證明（Gate 3 §4.2 裁決）。
  - 輸出為 long-format，附加 `label_end_date_tb`（即時呼叫
    `generate_triple_barrier_labels()` 取得）與 `target`（依 `target_column`
    選定，`target_up_down`／`target_triple_barrier` 兩欄原樣保留）。
  - `as_of`：面板輸出 `trade_date` 上界；所用快照 `effective_date <= as_of`。
- `recompute_tail_labels(df_prices, holding_period=5) -> pd.DataFrame`（新增於
  `src/ml/triple_barrier.py`）：對每檔股票只回傳尾端 `holding_period+1` 列的
  `generate_triple_barrier_labels()` 重算結果——**純計算，不碰任何既有表**。
- `apply_tail_labels(df_features, df_tail) -> pd.DataFrame`（新增於同檔）：把
  `recompute_tail_labels()` 的結果**套用**到既有 `daily_ml_features` 風格的
  DataFrame 上，依 `(stock_id, trade_date)` 只更新 `target_triple_barrier`／
  `label_reason` 兩欄，其餘欄位與其餘列逐位元組不變。**這是套用到表上的性質
  （冪等、只動尾端 H+1 列）的測試對象**——純計算函式本身測不到這個性質。
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# db_writer.py 於模組層級 `import psycopg2`——host 未安裝該套件，需以假模組占位；
# container 已安裝真實 psycopg2（CLAUDE.md §13.0 十五套件之一），此時必須用真的，
# 不得覆蓋——`if "psycopg2" not in sys.modules` 判準看的是「有沒有被 import 過」，
# 不是「有沒有安裝」，單獨跑本檔時容器內真實 psycopg2 尚未被 import，會被 stub
# 蓋掉，之後同一進程內任何需要真 psycopg2 的模組都會拿到 MagicMock（PO 2026-09-09
# 複審發現；tests/test_ml_feature_store_contract.py 有同一問題，一併修正）。
try:
    import psycopg2  # noqa: F401  能 import 就是真的裝了，直接用，不覆蓋
except ImportError:
    _psycopg2_stub = types.ModuleType("psycopg2")
    _psycopg2_stub.connect = MagicMock()
    _psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    _psycopg2_extras_stub.execute_values = MagicMock()
    _psycopg2_stub.extras = _psycopg2_extras_stub
    sys.modules["psycopg2"] = _psycopg2_stub
    sys.modules["psycopg2.extras"] = _psycopg2_extras_stub

import numpy as np
import pandas as pd

import src.loaders.db_writer as db_writer_mod
from src.loaders.db_writer import DBWriter
from src.ml.panel_dataset import build_panel_dataset
from src.ml.time_series_split import WalkForwardSplitter
from src.ml.triple_barrier import (
    apply_tail_labels,
    generate_triple_barrier_labels,
    recompute_tail_labels,
)


def _mk_universe(rows):
    """rows: list[(effective_date, stock_id, included)]"""
    return pd.DataFrame(rows, columns=["effective_date", "stock_id", "included"])


def _mk_features(rows):
    """rows: list[dict]，每個 dict 至少含 stock_id, trade_date；
    未提供的欄位補上 target_up_down/target_triple_barrier/label_reason 為 NaN。"""
    df = pd.DataFrame(rows)
    for col in ("target_up_down", "target_triple_barrier", "label_reason"):
        if col not in df.columns:
            df[col] = np.nan
    return df


def _mk_prices(stock_id, rows):
    n = len(rows)
    dates = pd.bdate_range("2022-01-03", periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({
        "stock_id": [stock_id] * n,
        "trade_date": dates,
        "open_price": [r["open"] for r in rows],
        "high_price": [r["high"] for r in rows],
        "low_price": [r["low"] for r in rows],
    })


class PanelDatasetTests(unittest.TestCase):
    """UG-G3-SB2：Panel Dataset 讀取器（PIT 正確，§5/§6）。"""

    def test_panel_shape(self):
        """Long-format 面板列數 = 「當期 included 股票」∩「該日有 daily_ml_features 列」的交集數。"""
        universe = _mk_universe([
            ("2022-01-01", "A", True),
            ("2022-01-01", "B", True),
        ])
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2022-01-03"},
            {"stock_id": "A", "trade_date": "2022-01-04"},
            {"stock_id": "B", "trade_date": "2022-01-03"},
            # C 沒有 universe 列，不應出現在面板
            {"stock_id": "C", "trade_date": "2022-01-03"},
        ])
        prices = pd.concat([
            _mk_prices("A", [{"open": 100, "high": 101, "low": 99}] * 2),
            _mk_prices("B", [{"open": 100, "high": 101, "low": 99}]),
        ], ignore_index=True)

        panel = build_panel_dataset(universe, features, prices, as_of="2022-01-04")

        self.assertEqual(len(panel), 3)  # A×2 + B×1，C 被排除

    def test_panel_no_future_dates(self):
        """給定 as_of，面板輸出無 trade_date > as_of，且所用快照 effective_date <= as_of。"""
        universe = _mk_universe([
            ("2022-01-01", "A", True),
            ("2022-02-01", "A", True),  # 更新一期快照，日期在 as_of 之後
        ])
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2022-01-05"},
            {"stock_id": "A", "trade_date": "2022-01-20"},  # 超過 as_of
        ])
        prices = _mk_prices("A", [{"open": 100, "high": 101, "low": 99}] * 2)

        panel = build_panel_dataset(universe, features, prices, as_of="2022-01-10")

        self.assertTrue((pd.to_datetime(panel["trade_date"]) <= pd.Timestamp("2022-01-10")).all())
        self.assertEqual(len(panel), 1)

    def test_panel_universe_is_point_in_time(self):
        """某股票在早期 included、晚期不 included，面板在對應日期區間反映此變化。"""
        universe = _mk_universe([
            ("2024-01-01", "A", True),
            ("2026-01-01", "A", False),  # 2026 期起排除
        ])
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2024-06-01"},   # 落在 2024 期，included=True
            {"stock_id": "A", "trade_date": "2026-06-01"},   # 落在 2026 期，included=False
        ])
        prices = _mk_prices("A", [{"open": 100, "high": 101, "low": 99}] * 2)

        panel = build_panel_dataset(universe, features, prices, as_of="2026-12-31")

        trade_dates = set(pd.to_datetime(panel["trade_date"]).dt.strftime("%Y-%m-%d"))
        self.assertIn("2024-06-01", trade_dates)
        self.assertNotIn("2026-06-01", trade_dates)

    def test_panel_target_column_selection(self):
        """訓練目標配置切換正確，兩欄皆存在但只有選定欄位供訓練消費（df['target']）。"""
        universe = _mk_universe([("2022-01-01", "A", True)])
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2022-01-03",
             "target_up_down": 1, "target_triple_barrier": -1},
        ])
        prices = _mk_prices("A", [{"open": 100, "high": 101, "low": 99}])

        panel_up_down = build_panel_dataset(universe, features, prices,
                                             target_column="target_up_down", as_of="2022-01-03")
        panel_tb = build_panel_dataset(universe, features, prices,
                                        target_column="target_triple_barrier", as_of="2022-01-03")

        self.assertIn("target_up_down", panel_up_down.columns)
        self.assertIn("target_triple_barrier", panel_up_down.columns)
        self.assertEqual(panel_up_down.iloc[0]["target"], 1)
        self.assertEqual(panel_tb.iloc[0]["target"], -1)

    def test_panel_universe_filter_uses_snapshot_not_entity_mapping(self):
        """面板股票範圍取自 universe_snapshots.included，不受 entity_mapping 有無路由列影響。

        本測試本身即證明：`build_panel_dataset()` 的函式簽章刻意不接受
        `df_entity_mapping` 參數——一檔股票只要在 universe_snapshots 當期
        included=True 且有 daily_ml_features 列，就必須出現在面板，無論
        entity_mapping 是否存在該股票的路由（本測試甚至不建構 entity_mapping
        資料，證明面板構建邏輯完全不依賴它）。
        """
        universe = _mk_universe([("2022-01-01", "UNROUTED_STOCK", True)])
        features = _mk_features([
            {"stock_id": "UNROUTED_STOCK", "trade_date": "2022-01-03"},
        ])
        prices = _mk_prices("UNROUTED_STOCK", [{"open": 100, "high": 101, "low": 99}])

        panel = build_panel_dataset(universe, features, prices, as_of="2022-01-03")

        self.assertEqual(len(panel), 1)
        self.assertEqual(panel.iloc[0]["stock_id"], "UNROUTED_STOCK")

    def test_panel_label_end_date_tb_present(self):
        """面板輸出含 label_end_date_tb 欄位且非全 NaT。"""
        universe = _mk_universe([("2022-01-01", "A", True)])
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(8)]
        prices = _mk_prices("A", rows)
        features = _mk_features([
            {"stock_id": "A", "trade_date": d} for d in prices["trade_date"]
        ])

        panel = build_panel_dataset(universe, features, prices, as_of=prices["trade_date"].iloc[-1])

        self.assertIn("label_end_date_tb", panel.columns)
        self.assertTrue(panel["label_end_date_tb"].notna().any())

    def test_panel_tolerates_label_end_date_target_mismatch(self):
        """有 label_end_date_tb 但 target_triple_barrier 為 NULL（尚未重算）的列，讀取器不拋錯、不丟棄。"""
        universe = _mk_universe([("2022-01-01", "A", True)])
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(8)]
        prices = _mk_prices("A", rows)
        # 刻意讓 target_triple_barrier 全部是 NaN（模擬每日掛點尚未執行的狀態）
        features = _mk_features([
            {"stock_id": "A", "trade_date": d, "target_triple_barrier": np.nan}
            for d in prices["trade_date"]
        ])

        panel = build_panel_dataset(universe, features, prices,
                                     target_column="target_triple_barrier",
                                     as_of=prices["trade_date"].iloc[-1])

        # 不拋錯即通過；且列數不因 target 為 NULL 被丟棄
        self.assertEqual(len(panel), 8)
        self.assertTrue(panel["label_end_date_tb"].notna().any())

    def test_panel_excludes_dates_before_first_snapshot(self):
        """trade_date 早於最早一期 universe_snapshots.effective_date 時，無 PIT 名單可用，
        該列不得出現在面板——不得默默沿用第一期回填（PO 2026-09-09 複審要求，規格未言明時
        不得由實作自行選擇，此測試把「不納入」釘為預期行為）。"""
        universe = _mk_universe([("2022-01-01", "A", True)])  # 最早一期 2022-01-01
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2021-12-01"},  # 早於首期快照
            {"stock_id": "A", "trade_date": "2022-01-05"},  # 正常，晚於首期快照
        ])
        prices = pd.DataFrame({
            "stock_id": ["A", "A"],
            "trade_date": ["2021-12-01", "2022-01-05"],
            "open_price": [100, 100],
            "high_price": [101, 101],
            "low_price": [99, 99],
        })

        panel = build_panel_dataset(universe, features, prices, as_of="2022-01-05")

        trade_dates = set(pd.to_datetime(panel["trade_date"]).dt.strftime("%Y-%m-%d"))
        self.assertNotIn("2021-12-01", trade_dates)
        self.assertIn("2022-01-05", trade_dates)
        self.assertEqual(len(panel), 1)

    def test_panel_raises_on_duplicate_universe_snapshot_rows(self):
        """同一 `(effective_date, stock_id)` 在 `universe_snapshots` 出現兩次時，
        必須 raise，不得讓面板列靜默翻倍（PO 2026-09-09 複審發現：`merge` 對
        重複鍵會產生笛卡兒積，該股票的面板列變成兩列；真實表有 PK
        `(effective_date, stock_id)` 擋得住，但 `build_panel_dataset()` 吃的是
        DataFrame，不保證來源一定符合這個約束——`CLAUDE.md` §7.1「失敗不得
        偽裝成正常結果」，這裡選 raise 而非默默去重）。"""
        universe = _mk_universe([
            ("2022-01-01", "A", True),
            ("2022-01-01", "A", True),  # 重複列
        ])
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2022-01-03"},
        ])
        prices = _mk_prices("A", [{"open": 100, "high": 101, "low": 99}])

        with self.assertRaises(ValueError):
            build_panel_dataset(universe, features, prices, as_of="2022-01-03")

    def test_panel_excludes_stock_absent_from_applicable_snapshot(self):
        """股票在較早一期 included=True，但在「該 trade_date 適用的那一期」快照裡
        完全沒有該股票的列（不是 included=False，是缺席——下市／退出候選池的
        真實長相），該股票在該期不得沿用舊期的 included=True（PO 2026-09-09
        複審發現：現行實作以 `us[us["stock_id"] == stock_id]` 只看該股票自己
        的快照列，缺席時會沿用它自己最後一次出現的那期，逃過排除）。

        適用期必須是**全域**判定：所有快照中 effective_date <= trade_date 的
        最大 effective_date 為該 trade_date 的適用期；股票必須在**那一期**
        有列且 included=True 才算在名單內。
        """
        universe = _mk_universe([
            ("2024-01-01", "A", True),
            ("2026-01-01", "B", True),  # 2026 期只有 B，A 缺席
        ])
        features = _mk_features([
            {"stock_id": "A", "trade_date": "2026-06-01"},  # A 在適用期（2026-01-01）缺席
            {"stock_id": "B", "trade_date": "2026-06-01"},
        ])
        # _mk_prices 用固定起始日合成 trade_date，與上面手寫的 features trade_date
        # 對不上，因此改用手動建構，確保 prices/features 的 trade_date 一致
        prices = pd.DataFrame({
            "stock_id": ["A", "B"],
            "trade_date": ["2026-06-01", "2026-06-01"],
            "open_price": [100, 100],
            "high_price": [101, 101],
            "low_price": [99, 99],
        })

        panel = build_panel_dataset(universe, features, prices, as_of="2026-06-01")

        stock_ids = set(panel["stock_id"])
        self.assertNotIn("A", stock_ids)
        self.assertIn("B", stock_ids)

    def test_panel_label_end_date_tb_dtype_matches_trade_date(self):
        """`label_end_date_tb` 的 dtype 必須與 `trade_date`（已被面板轉為
        `datetime64`）一致，否則下游 `WalkForwardSplitter` 的日期比較會
        `TypeError`（PO 2026-09-09 複審發現：現行實作合併自
        `generate_triple_barrier_labels()` 的 `shift()` 結果，沿用輸入
        `df_stock_prices["trade_date"]` 原始 dtype——測試餵字串就是字串，
        真實庫餵 date 才是 date，兩者不受面板自身的 `pd.to_datetime` 轉換
        影響）。"""
        universe = _mk_universe([("2022-01-01", "A", True)])
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(8)]
        prices = _mk_prices("A", rows)  # trade_date 為字串（_mk_prices 的合成方式）
        features = _mk_features([
            {"stock_id": "A", "trade_date": d} for d in prices["trade_date"]
        ])

        panel = build_panel_dataset(universe, features, prices, as_of=prices["trade_date"].iloc[-1])

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(panel["trade_date"]))
        self.assertTrue(
            pd.api.types.is_datetime64_any_dtype(panel["label_end_date_tb"]),
            f"label_end_date_tb dtype 應與 trade_date 一致為 datetime64，"
            f"實際為 {panel['label_end_date_tb'].dtype}",
        )

    def test_panel_feeds_walk_forward_splitter(self):
        """面板輸出必須能直接餵給 `WalkForwardSplitter(label_end_date_col=
        'label_end_date_tb')` 且正確 purge——不只是「這一欄存在」，而是「這一
        欄能被下游實際消費」（PO 2026-09-09 複審要求；與
        `tests/test_triple_barrier.py::test_tb_purge_boundary_with_h5` 同型
        驗證，經由面板讀取器而非直接呼叫 `generate_triple_barrier_labels()`）。
        """
        universe = _mk_universe([("2022-01-01", "A", True)])
        rng = np.random.RandomState(3)
        n = 40
        base = 100 + np.cumsum(rng.normal(0, 1, n))
        rows = [{"open": b, "high": b + 1, "low": b - 1} for b in base]
        prices = _mk_prices("A", rows)
        features = _mk_features([
            {"stock_id": "A", "trade_date": d} for d in prices["trade_date"]
        ])

        panel = build_panel_dataset(universe, features, prices, as_of=prices["trade_date"].iloc[-1])

        splitter = WalkForwardSplitter(
            train_window_size=10, test_window_size=5, step_size=5,
            mode="rolling", label_horizon=5, min_train_size=1,
            label_end_date_col="label_end_date_tb",
        )
        train_idx, test_idx, meta = next(splitter.split(panel))

        self.assertEqual(meta["purged_days"], 5)
        self.assertEqual(meta["train_days"], 5)  # train_window(10) - purge(5)


class DailyTailRecomputeTests(unittest.TestCase):
    """每日尾端重算掛點：`recompute_tail_labels()` / `apply_tail_labels()`（§3.1）。"""

    def test_daily_hook_recomputes_tail_h_plus_1_rows(self):
        """`recompute_tail_labels()` 回傳列數與內容與全量重算的尾端一致（快篩，非邊界證明）。"""
        rng = np.random.RandomState(11)
        n = 30
        base = 100 + np.cumsum(rng.normal(0, 1, n))
        rows = [{"open": b, "high": b + 1, "low": b - 1} for b in base]
        df = _mk_prices("A", rows)

        full = generate_triple_barrier_labels(df, holding_period=5)
        tail = recompute_tail_labels(df, holding_period=5)

        self.assertEqual(len(tail), 6)  # holding_period + 1
        full_tail = full.tail(6).reset_index(drop=True)
        tail_reset = tail.reset_index(drop=True)
        for col in ("stock_id", "trade_date", "target_triple_barrier"):
            pd.testing.assert_series_equal(
                tail_reset[col].reset_index(drop=True),
                full_tail[col].reset_index(drop=True),
                check_names=False,
            )

    def test_tail_boundary_is_exactly_h_plus_1_by_construction(self):
        """
        邊界由建構證明，不是宣告：新增一列後，僅最後 H+1 列的標籤可能改變，
        其餘列與新列加入前的全量計算逐列相同——本測試不呼叫
        `recompute_tail_labels()`，直接對「新列加入前／後」兩份資料獨立跑
        `generate_triple_barrier_labels()`，比對邊界本身在哪裡。

        資料刻意用平盤價格（open=high=low=100，無任何觸線）構造，讓「變成
        可判定」的那一列有可預期、非隨機的結果（Timeout=0），避免用隨機資料
        時邊界列恰好也是其他成因、看不出變化。

        known-FAIL（PM 於送審前以拋棄式參考實作驗證，見 commit 說明）：把本
        測試斷言的邊界常數從 H+1 改成 H，會漏掉倒數第 H+1 列本應改變卻被排除
        在比對之外，測試對「該列未改變」的斷言錯誤地通過而不是抓到問題；
        改成 H+2，會把本不该檢查的一列（before 中同樣未定義的位置）也納入
        「應相同」的比對，兩個方向都必須讓本測試的斷言邏輯本身失去意義——
        H+1 是唯一讓兩類斷言同時成立的邊界。
        """
        H = 5
        n_after = 16
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(n_after)]
        df_after = _mk_prices("A", rows)
        df_before = df_after.iloc[:-1].copy()  # 少最後一列，模擬「新列加入前」

        before = generate_triple_barrier_labels(df_before, holding_period=H)
        after = generate_triple_barrier_labels(df_after, holding_period=H)

        boundary = n_after - (H + 1)  # 前 boundary 列不受新列影響

        # 前 boundary 列：target/reason 逐列與新列加入前相同
        pd.testing.assert_series_equal(
            after.loc[:boundary - 1, "target_triple_barrier"].reset_index(drop=True),
            before.loc[:boundary - 1, "target_triple_barrier"].reset_index(drop=True),
            check_names=False,
        )
        pd.testing.assert_series_equal(
            after.loc[:boundary - 1, "label_reason"].reset_index(drop=True),
            before.loc[:boundary - 1, "label_reason"].reset_index(drop=True),
            check_names=False,
        )

        # 邊界列本身（倒數第 H+1 列）：新列加入前為 insufficient_data，
        # 加入後因平盤價格無觸線，變為可判定的 Timeout=0
        self.assertEqual(before.loc[boundary, "label_reason"], "insufficient_data")
        self.assertEqual(after.loc[boundary, "target_triple_barrier"], 0)
        self.assertTrue(pd.isna(after.loc[boundary, "label_reason"]))

    def test_daily_hook_apply_is_idempotent(self):
        """
        `apply_tail_labels()` 套用到表上兩次，結果相同；且只有尾端 H+1 列
        的 target/reason 改變，其餘列（含其他欄位）逐位元組不變——這是純函式
        `recompute_tail_labels()` 本身測不到的性質（它不知道「表」的存在）。
        """
        n = 20
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(n)]  # 平盤，Timeout 可預期
        df_prices = _mk_prices("A", rows)

        # 既有 daily_ml_features 風格的表：全部設為與任何合法重算結果都不同的
        # 哨兵值（target=-1, reason=NaN——「已標籤且為止損」），確保尾端 6 列
        # 無論重算成 no_entry／insufficient_data／Timeout=0 中的哪一種，都與
        # 這個哨兵值不同，逐列真的會被 recompute 改到，而不是巧合地本來就對
        df_features = _mk_features([
            {"stock_id": "A", "trade_date": d,
             "target_triple_barrier": -1, "label_reason": np.nan}
            for d in df_prices["trade_date"]
        ])
        df_features["unrelated_col"] = range(len(df_features))

        tail = recompute_tail_labels(df_prices, holding_period=5)
        applied_once = apply_tail_labels(df_features, tail)
        applied_twice = apply_tail_labels(applied_once, tail)

        pd.testing.assert_frame_equal(
            applied_once.reset_index(drop=True), applied_twice.reset_index(drop=True)
        )

        # 只有尾端 H+1=6 列的 target/reason 改變
        orig_tb = df_features["target_triple_barrier"].reset_index(drop=True)
        new_tb = applied_once["target_triple_barrier"].reset_index(drop=True)
        orig_reason = df_features["label_reason"].reset_index(drop=True)
        new_reason = applied_once["label_reason"].reset_index(drop=True)
        changed = (
            ~(orig_tb.isna() & new_tb.isna()) & (orig_tb != new_tb)
        ) | (
            ~(orig_reason.isna() & new_reason.isna()) & (orig_reason != new_reason)
        )
        self.assertEqual(changed.sum(), 6)  # holding_period + 1

        # 無關欄位逐位元組不變
        pd.testing.assert_series_equal(
            df_features["unrelated_col"].reset_index(drop=True),
            applied_once["unrelated_col"].reset_index(drop=True),
        )

    def test_tail_hook_is_per_stock(self):
        """
        多股票、日期完全重疊時，掛點必須逐股票各自處理，不得全域 tail() 或
        只用 trade_date 當合併鍵——兩者在單股票資料上都測不出來，但面板本
        來就是多股票、日期重疊的（PO 2026-09-09 複審要求）。

        A 全程平盤（尾端應為 Timeout=0）；B 尾端第 3 列觸 upper（尾端應為 1）。
        """
        n = 20
        rows_a = [{"open": 100, "high": 101, "low": 99} for _ in range(n)]
        rows_b = [{"open": 100, "high": 101, "low": 99} for _ in range(n)]
        rows_b[-4] = {"open": 100, "high": 103, "low": 99}  # 尾端窗口內觸 upper

        df_prices = pd.concat([_mk_prices("A", rows_a), _mk_prices("B", rows_b)],
                               ignore_index=True)

        tail = recompute_tail_labels(df_prices, holding_period=5)

        self.assertEqual(len(tail), 12)  # 兩檔各 6 列
        self.assertEqual((tail["stock_id"] == "A").sum(), 6)
        self.assertEqual((tail["stock_id"] == "B").sum(), 6)

        # A、B 尾端結果不同，證明沒有交叉污染
        a_targets = tail.loc[tail["stock_id"] == "A", "target_triple_barrier"].tolist()
        b_targets = tail.loc[tail["stock_id"] == "B", "target_triple_barrier"].tolist()
        self.assertNotEqual(a_targets, b_targets)
        self.assertIn(1, b_targets)  # B 觸 upper 應產生至少一個 label=1
        self.assertNotIn(1, [t for t in a_targets if pd.notna(t)])  # A 平盤不應有 1

        # apply_tail_labels 逐股票正確更新，互不覆蓋
        df_features = _mk_features([
            {"stock_id": sid, "trade_date": d, "target_triple_barrier": -1, "label_reason": np.nan}
            for sid, d in zip(df_prices["stock_id"], df_prices["trade_date"])
        ])
        applied = apply_tail_labels(df_features, tail)

        orig_tb = df_features["target_triple_barrier"].reset_index(drop=True)
        new_tb = applied["target_triple_barrier"].reset_index(drop=True)
        orig_reason = df_features["label_reason"].reset_index(drop=True)
        new_reason = applied["label_reason"].reset_index(drop=True)
        changed = (
            ~(orig_tb.isna() & new_tb.isna()) & (orig_tb != new_tb)
        ) | (
            ~(orig_reason.isna() & new_reason.isna()) & (orig_reason != new_reason)
        )
        self.assertEqual(changed.sum(), 12)  # 兩檔各 6 列，共 12 列

    def test_apply_tail_labels_handles_all_nan_float_label_reason_column(self):
        """
        已觀測的 pandas dtype 陷阱（本檔早前撰寫紅色測試時，拋棄式參考實作
        踩到過）：`label_reason` 欄若初始全為 NaN，pandas 會推斷為 `float64`，
        之後賦值字串會 `TypeError: Invalid value ... for dtype 'float64'`。
        `apply_tail_labels()` 必須自行處理型別轉換，不得要求呼叫端先手動轉。
        """
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(10)]
        df_prices = _mk_prices("A", rows)

        df_features = _mk_features([
            {"stock_id": "A", "trade_date": d}  # target/reason 皆預設 NaN（float64）
            for d in df_prices["trade_date"]
        ])
        self.assertEqual(df_features["label_reason"].dtype, np.float64)

        tail = recompute_tail_labels(df_prices, holding_period=5)

        # 不應拋出 TypeError
        applied = apply_tail_labels(df_features, tail)
        self.assertEqual(len(applied), len(df_features))

    def test_apply_tail_labels_raises_keyerror_for_key_absent_from_features(self):
        """`df_tail` 含有 `df_features` 沒有的 `(stock_id, trade_date)` 組合時，
        `apply_tail_labels()` 必須 raise（PO 2026-09-09 複審發現，已探測）——
        不得沿用 `db_writer.update_triple_barrier_tail_labels()` 的「不建立
        殘缺列」語意卻自己默默吞掉，兩處對「目標列不存在」必須有一致、明確
        的失敗行為（`CLAUDE.md` §7.1）。"""
        rows = [{"open": 100, "high": 101, "low": 99} for _ in range(10)]
        df_prices = _mk_prices("A", rows)
        tail = recompute_tail_labels(df_prices, holding_period=5)

        # df_features 只含前 3 天，缺少 tail 對應的尾端列
        df_features = _mk_features([
            {"stock_id": "A", "trade_date": d} for d in df_prices["trade_date"].iloc[:3]
        ])

        with self.assertRaises(KeyError):
            apply_tail_labels(df_features, tail)


def _mk_db_writer():
    writer = DBWriter.__new__(DBWriter)
    writer.db_config = {
        "host": "x", "port": 1, "database": "d", "user": "u", "password": "<test>",
    }
    return writer


def _mk_mock_conn(rowcount=1):
    """回傳 (conn, cur) 兩個 MagicMock；cur 支援 `with conn.cursor() as cur:` 用法。"""
    cur = MagicMock()
    cur.rowcount = rowcount
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    return conn, cur


def _mk_tail_rows(n=1):
    return pd.DataFrame({
        "stock_id": ["A"] * n,
        "trade_date": [f"2022-01-{i+1:02d}" for i in range(n)],
        "target_triple_barrier": [1.0] * n,
        "label_reason": [np.nan] * n,
    })


class DbWriterTripleBarrierTailWriteTests(unittest.TestCase):
    """`DBWriter.update_triple_barrier_tail_labels()` 契約測試（PO 2026-09-09 複審要求）。

    用 `MagicMock` 游標／連線釘住三件事，不觸及任何資料庫：
    1. 寫入語句是 `UPDATE`，不是 `INSERT ... ON CONFLICT DO UPDATE`（避免建立殘缺列）。
    2. 回傳值是逐列 `cur.rowcount` 加總，供呼叫端與 `len(df_tail)` 比對。
    3. 例外時 `rollback()` 被呼叫且例外原樣重新拋出（不得吞掉、不得偽裝成成功）。
    """

    def test_update_uses_plain_update_not_insert(self):
        writer = _mk_db_writer()
        conn, cur = _mk_mock_conn(rowcount=1)

        with patch.object(db_writer_mod.psycopg2, "connect", return_value=conn):
            n = writer.update_triple_barrier_tail_labels(_mk_tail_rows(1))

        sql = cur.execute.call_args[0][0]
        self.assertIn("UPDATE", sql.upper())
        self.assertNotIn("INSERT", sql.upper())
        self.assertNotIn("ON CONFLICT", sql.upper())
        self.assertEqual(n, 1)
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_update_returns_rowcount_sum_across_rows(self):
        writer = _mk_db_writer()
        conn, cur = _mk_mock_conn(rowcount=1)  # 每次 execute 後 cur.rowcount 固定為 1

        with patch.object(db_writer_mod.psycopg2, "connect", return_value=conn):
            n = writer.update_triple_barrier_tail_labels(_mk_tail_rows(3))

        self.assertEqual(cur.execute.call_count, 3)
        self.assertEqual(n, 3)  # 3 列，逐列 rowcount=1，加總為 3

    def test_update_rolls_back_and_reraises_on_error(self):
        writer = _mk_db_writer()
        conn, cur = _mk_mock_conn()
        cur.execute.side_effect = RuntimeError("boom")

        with patch.object(db_writer_mod.psycopg2, "connect", return_value=conn):
            with self.assertRaises(RuntimeError):
                writer.update_triple_barrier_tail_labels(_mk_tail_rows(1))

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_update_empty_df_is_noop(self):
        """空／None 輸入直接回傳 0，不連線資料庫（既有防護，補上迴歸釘子）。"""
        writer = _mk_db_writer()
        with patch.object(db_writer_mod.psycopg2, "connect") as mock_connect:
            n_empty_df = writer.update_triple_barrier_tail_labels(pd.DataFrame())
            n_none = writer.update_triple_barrier_tail_labels(None)

        self.assertEqual(n_empty_df, 0)
        self.assertEqual(n_none, 0)
        mock_connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
