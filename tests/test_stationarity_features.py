# -*- coding: utf-8 -*-
"""UG-G2-SB8：CORE_16 四個平穩化特徵（FEATURE_REGISTRY.md §3.4、§3.7 第 13–16 號）。

這四欄已在契約與 schema 中宣告、`db_writer` 也寫它們，但 `feature_aggregator`
從未計算——沒有它們，CORE_16 實際只有 12 個特徵、COMMENT_ENHANCED_19 只有 15 個。

本檔的重點不是公式（公式很簡單），是 **NULL 策略**：
契約對這四欄指定的 `fillna` 是在**四欄都還沒實作時**寫的，
`UG-G2-SB8` Gate A 逐欄檢視後由 PO 裁決修正兩處（DEC-030）。
"""
import os
import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg2  # noqa: F401
except ModuleNotFoundError:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock(name="unconfigured_psycopg2_connect")
    extras = types.ModuleType("psycopg2.extras")
    extras.execute_values = MagicMock(name="execute_values")
    psycopg2.extras = extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = extras

import pandas as pd

from src.transform.feature_aggregator import FeatureAggregator

MAPPING = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])


def _prices(rows, stock_id="2330"):
    """rows: list of dict(day, close, volume, high=None, low=None)"""
    return pd.DataFrame([{
        "trade_date": r["day"],
        "stock_id": stock_id,
        "open_price": r.get("open", r["close"]),
        "high_price": r.get("high"),
        "low_price": r.get("low"),
        "close_price": r["close"],
        "volume": r["volume"],
    } for r in rows])


def _run(df_prices):
    return FeatureAggregator().generate_daily_features(
        df_prices, pd.DataFrame(), MAPPING)


def _days(n, start=1):
    return ["2026-08-%02d" % d for d in range(start, start + n)]


class AmplitudeRatioTests(unittest.TestCase):
    """§3.4 `amplitude_ratio = (High - Low) / Close`"""

    def test_amplitude_ratio_formula(self):
        df = _run(_prices([
            {"day": "2026-08-03", "close": 100.0, "volume": 1000, "high": 105.0, "low": 95.0},
        ]))
        row = df.iloc[0]
        self.assertAlmostEqual(float(row["amplitude_ratio"]), (105.0 - 95.0) / 100.0, places=9)

    def test_missing_high_low_does_not_fabricate_zero_amplitude(self):
        """**known-FAIL（決策點 1，DEC-030）**：high/low 缺席時必須是 NULL，不得填 0.0。

        `(High - Low) / Close` 三個值全部來自同一列，**沒有 lag、沒有 rolling
        window——成因 W（暖機期）在結構上不可能發生**。因此契約原本指定的
        `fillna(0.0)` **唯一可能觸發的情境就是成因 F（資料根本沒取得）**，
        而 §5A.1 對 F 的規定是「必須保持 NULL，嚴禁任何填補」。

        且 `0.0` 的語意是 `High == Low`——**漲跌停鎖死或整日無成交**，
        一個真實且有意義的市場事件。把「取不到高低價」填成「振幅為零」，
        正是 §5A.1 那句「把後者填成前者，等同於讓模型讀到一個從未觀測到的訊號」。
        """
        df = _run(_prices([
            {"day": "2026-08-03", "close": 100.0, "volume": 1000, "high": None, "low": None},
        ]))
        self.assertTrue(pd.isna(df.iloc[0]["amplitude_ratio"]),
                        "high/low 缺席屬成因 F，必須保持 NULL；"
                        "填 0.0 等於宣稱「當日振幅為零」這個從未觀測到的事件")

    def test_zero_amplitude_is_a_real_observation_not_null(self):
        """反向守衛：`High == Low`（漲跌停鎖死）是**真實觀測**，必須有值 0.0。

        沒有這個測試，決策點 1 的修法最容易的失敗方式就是
        把「真的沒有振幅」也一起變成 NULL——那個退化不會報錯。
        """
        df = _run(_prices([
            {"day": "2026-08-03", "close": 100.0, "volume": 1000, "high": 100.0, "low": 100.0},
        ]))
        val = df.iloc[0]["amplitude_ratio"]
        self.assertFalse(pd.isna(val), "漲跌停鎖死是真實觀測，不是缺資料")
        self.assertAlmostEqual(float(val), 0.0, places=9)


class MovingAverageBiasTests(unittest.TestCase):
    """§3.4 `ma5_bias_ratio` / `ma20_bias_ratio`（本 SB 維持契約的 `fillna(0.0)`）"""

    def test_ma5_bias_ratio_formula_after_warmup(self):
        rows = [{"day": d, "close": c, "volume": 1000, "high": c + 1, "low": c - 1}
                for d, c in zip(_days(5, 3), [100.0, 102.0, 104.0, 106.0, 108.0])]
        df = _run(_prices(rows)).sort_values("trade_date").reset_index(drop=True)
        ma5 = sum([100.0, 102.0, 104.0, 106.0, 108.0]) / 5
        self.assertAlmostEqual(float(df.iloc[4]["ma5_bias_ratio"]),
                               (108.0 - ma5) / ma5, places=9)

    def test_warmup_fills_zero_per_contract(self):
        """暖機期屬成因 W，依 §5A.1 允許填補中立值——本 SB 維持契約的 `fillna(0.0)`。

        **但 PO 已指出**：`0.0` 的語意是「收盤價恰好等於均線」，
        在 `(-inf, +inf)` 值域裡那是一個**事件**，不是結構中點
        （對照 `rsi_14` 的 `50.0` 是 `[0,100]` 的中點）。
        同一個批評適用於已上線的 `return_1d` 與 `volatility_5d/20d`，
        因此**不在本 SB 決定**——已登記 RISK-020，Gate 3 啟動前裁決。
        """
        rows = [{"day": d, "close": c, "volume": 1000, "high": c + 1, "low": c - 1}
                for d, c in zip(_days(3, 3), [100.0, 102.0, 104.0])]
        df = _run(_prices(rows)).sort_values("trade_date").reset_index(drop=True)
        self.assertFalse(pd.isna(df.iloc[0]["ma20_bias_ratio"]))
        self.assertAlmostEqual(float(df.iloc[0]["ma20_bias_ratio"]), 0.0, places=9)


class VolumeRatioTests(unittest.TestCase):
    """§3.4 `volume_ratio_5d = Volume / MA5_Vol`"""

    def test_volume_ratio_5d_formula_after_warmup(self):
        vols = [1000, 1000, 1000, 1000, 1000, 2000]
        rows = [{"day": d, "close": 100.0, "volume": v, "high": 101.0, "low": 99.0}
                for d, v in zip(_days(6, 3), vols)]
        df = _run(_prices(rows)).sort_values("trade_date").reset_index(drop=True)
        self.assertAlmostEqual(float(df.iloc[5]["volume_ratio_5d"]), 2000 / 1000.0, places=9)

    def test_zero_volume_baseline_is_not_filled_as_one(self):
        """**known-FAIL（決策點 3，DEC-030）**：`MA5_Vol == 0` 必須是 NULL，不得填 1.0。

        **這一格是 §5A.1 的第三種成因**（DEC-030 新增的 `U — 數學未定義`）：

        - 不是 W：視窗是足的（已累積 5 日），資料確實存在
        - 不是 F：資料取得了，就是 0

        填 `1.0` 的語意是「今日成交量等於 5 日均量」，
        而事實是「**過去 5 日完全沒有成交**」——不是中立值，**是與事實相反的值**。
        """
        vols = [0, 0, 0, 0, 0, 5000]
        rows = [{"day": d, "close": 100.0, "volume": v, "high": 101.0, "low": 99.0}
                for d, v in zip(_days(6, 3), vols)]
        df = _run(_prices(rows)).sort_values("trade_date").reset_index(drop=True)
        self.assertTrue(pd.isna(df.iloc[5]["volume_ratio_5d"]),
                        "MA5_Vol == 0 時公式在數學上未定義，必須保持 NULL；"
                        "填 1.0 等於宣稱「今日成交量等於 5 日均量」，與事實相反")

    def test_warmup_fills_one_per_contract(self):
        """暖機期（不足 5 日）屬成因 W，維持契約的 `fillna(1.0)`。

        與上一個測試互補——沒有這一半，把所有東西都設成 NULL 也會通過上一個測試。
        """
        rows = [{"day": d, "close": 100.0, "volume": 1000, "high": 101.0, "low": 99.0}
                for d in _days(2, 3)]
        df = _run(_prices(rows)).sort_values("trade_date").reset_index(drop=True)
        self.assertFalse(pd.isna(df.iloc[0]["volume_ratio_5d"]),
                         "暖機期屬成因 W，允許填補")
        self.assertAlmostEqual(float(df.iloc[0]["volume_ratio_5d"]), 1.0, places=9)


class PriceQueryContractTests(unittest.TestCase):
    """讀取端契約：股價查詢必須撈 high/low —— 這是同型缺口的第三次（DEC-029）。"""

    def test_price_query_selects_high_and_low(self):
        import inspect

        from src.loaders.db_writer import DBWriter
        src = inspect.getsource(DBWriter.fetch_all_for_features)
        self.assertIn("high_price", src,
                      "amplitude_ratio 需要 high_price；資料一直都在 stock_prices，"
                      "缺的是這一句 SELECT（讀取端缺口第三次）")
        self.assertIn("low_price", src)


if __name__ == "__main__":
    unittest.main()
