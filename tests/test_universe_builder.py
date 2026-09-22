# -*- coding: utf-8 -*-
"""UG-G2-SB6：Point-in-Time Stock Universe 建構的守衛。

規格來源：DEC-017（APPROVED）§Verification 的三項 +
`SYSTEM_UPGRADE_MASTER_PLAN.md` §8 SB6 Brief 指名的六項 +
提案 §5 的 P1~P5。

================================================================================
本檔**不連資料庫**，而那是刻意的
================================================================================
`CLAUDE.md` §13.4 記載本專案有 9 個測試「其行為取決於環境是否具備資料庫憑證
與 DB 內容」。**PIT 的正確性不能靠那種測試守** ——
一個在沒有 DB 時就悄悄跳過的 PIT 測試，與一個永遠通過的檢查沒有區別（§9A.1）。

因此所有斷言都跑在純函式上，輸入是手寫的小日曆與觀測值。
**代價是資料庫存取層（`UniverseBuilder`）沒有被本檔覆蓋** ——
那一層由實際執行 46 期快照時的逐期比對負責，**並在報告中明確標示為不同的證據**。

================================================================================
每一項檢查都附「什麼輸入會讓它 FAIL」
================================================================================
提案 §5 的表格逐項寫下了 FAIL 條件（§9A.1：結構上無法失敗的檢查不是檢查）。
本檔把那些 FAIL 條件**實際建構出來**：P1、P3、P4、P5 各有一個
「若實作寫錯就會通過」的反例被明確斷言為必須失敗。
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.transform.universe_builder import (  # noqa: E402
    InsufficientHistoryError, LookaheadError,
    REASON_NOT_COMMON_STOCK, REASON_NO_RECENT_ACTIVITY,
    REASON_OUTSIDE_TOP_N, REASON_ZERO_MEDIAN_TURNOVER,
    build_snapshot, effective_dates, liquidity_window,
    month_first_trading_days,
)


def make_calendar(start, n_days):
    """產生 n_days 個「交易日」（跳過週末）。"""
    out, d = [], start
    while len(out) < n_days:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class UniverseCalendarTests(unittest.TestCase):
    """月首交易日與暖機邊界。"""

    def test_month_first_trading_days_skips_holidays(self):
        # 2023-01-01 是週日；該月第一個交易日應為 01-02。
        cal = make_calendar(date(2022, 12, 28), 40)
        firsts = month_first_trading_days(cal)
        self.assertIn(date(2023, 1, 2), firsts)
        self.assertNotIn(date(2023, 1, 1), firsts)

    def test_universe_monthly_rebuild(self):
        """Brief 指名：每月重建一次，且只在暖機完成後開始。

        **會讓它 FAIL 的輸入**：把暖機用月份相減算（提案 §3 記錄的 36 那個錯法）
        —— 那會讓第一個 effective_date 提早出現。
        """
        cal = make_calendar(date(2022, 1, 3), 200)
        effs = effective_dates(cal, window_size=60)
        # 每個月最多一個
        self.assertEqual(len(effs), len({(d.year, d.month) for d in effs}))
        # 第一個 effective_date 之前必須有滿 60 個交易日
        self.assertGreaterEqual(cal.index(effs[0]), 60)
        # 而它的前一個月首**不**具備完整窗口，否則就是漏了一期
        earlier = [d for d in month_first_trading_days(cal) if d < effs[0]]
        for d in earlier:
            self.assertLess(cal.index(d), 60)

    def test_liquidity_window_excludes_effective_date(self):
        """窗口嚴格早於 effective_date（DEC-017「生效日前已知」、提案 P1）。

        **會讓它 FAIL 的輸入**：`rk-59 .. rk` 這種含當日的窗口 ——
        校準用的 SQL 正是那樣寫的，本斷言就是為了不讓它進入執行期。
        """
        cal = make_calendar(date(2022, 1, 3), 100)
        eff = cal[70]
        window = liquidity_window(cal, eff, window_size=60)
        self.assertEqual(len(window), 60)
        self.assertEqual(window[-1], cal[69])
        self.assertTrue(all(d < eff for d in window))
        self.assertNotIn(eff, window)

    def test_liquidity_window_raises_before_warmup(self):
        cal = make_calendar(date(2022, 1, 3), 100)
        with self.assertRaises(InsufficientHistoryError):
            liquidity_window(cal, cal[59], window_size=60)


class UniverseRankingTests(unittest.TestCase):
    """排名、納入數與排除理由。"""

    def setUp(self):
        self.cal = make_calendar(date(2022, 1, 3), 100)
        self.eff = self.cal[70]
        self.window = liquidity_window(self.cal, self.eff, 60)

    def _obs(self, spec):
        """spec: {stock_id: turnover}（該股在整個窗口每天都以該金額成交）。"""
        return {(s, d): amt for s, amt in spec.items() for d in self.window}

    def test_universe_size(self):
        """Brief 指名：納入數為 top_n，除非候選不足。"""
        obs = self._obs({"%d" % (1000 + i): 10_000 + i for i in range(200)})
        rows = build_snapshot(self.eff, self.cal, obs, top_n=150)
        included = [r for r in rows if r["included"]]
        self.assertEqual(len(included), 150)
        self.assertEqual([r["rank"] for r in included], list(range(1, 151)))
        # 排除者不得有名次（migration 006 的 CHECK 也擋，此處先擋在程式內）
        self.assertTrue(all(r["rank"] is None for r in rows if not r["included"]))
        # 候選不足時不補滿
        small = build_snapshot(self.eff, self.cal,
                               self._obs({"1101": 5, "1102": 7}), top_n=150)
        self.assertEqual(len([r for r in small if r["included"]]), 2)

    def test_universe_excludes_etf(self):
        """Brief 指名：ETF／ETN／權證不得進入 universe。

        **會讓它 FAIL 的輸入**：只依賴取數層的代號過濾。
        本層是第二道 —— 若日後有人繞過 extractor 直接寫入 `candidate_prices`，
        **只有這一道會發現**。
        """
        obs = self._obs({
            "2330": 1_000_000,      # 普通股
            "0050": 9_999_999_999,  # ETF：金額最大，若沒擋就會是第 1 名
            "00878": 8_888_888,     # ETN 型 5 碼
            "031234": 7_777_777,    # 權證 6 碼
        })
        rows = build_snapshot(self.eff, self.cal, obs, top_n=150)
        by_id = {r["stock_id"]: r for r in rows}
        self.assertTrue(by_id["2330"]["included"])
        for code in ("0050", "00878", "031234"):
            self.assertFalse(by_id[code]["included"])
            self.assertEqual(by_id[code]["exclusion_reason"],
                             REASON_NOT_COMMON_STOCK)

    def test_absent_days_count_as_zero_not_skipped(self):
        """提案 §2.2a：缺席日計為 0，不是只對有資料的日子取中位數。

        **會讓它 FAIL 的輸入**：`statistics.median([v for v in values if v])`
        —— 一檔只交易 5 天、每天 10 億的股票會因此排到第 1 名，而它根本不可交易。
        """
        heavy_but_absent = {("8888", d): 1_000_000_000 for d in self.window[-5:]}
        steady = {("2330", d): 1_000_000 for d in self.window}
        rows = build_snapshot(self.eff, self.cal,
                              {**heavy_but_absent, **steady}, top_n=150)
        by_id = {r["stock_id"]: r for r in rows}
        self.assertEqual(by_id["8888"]["median_turnover"], 0)
        self.assertEqual(by_id["8888"]["observation_days"], 5)
        self.assertFalse(by_id["8888"]["included"])
        self.assertEqual(by_id["8888"]["exclusion_reason"],
                         REASON_ZERO_MEDIAN_TURNOVER)
        self.assertTrue(by_id["2330"]["included"])

    def test_universe_snapshot_saved(self):
        """DEC-017 §Verification：保存排名依據與**納入／排除**清單。

        **會讓它 FAIL 的輸入**：只回傳納入名單 ——
        那樣就無法回答「這檔當時為什麼不在裡面」，而那是稽核偏誤時唯一要問的問題。
        """
        obs = self._obs({"%d" % (1000 + i): 10_000 + i for i in range(160)})
        obs.update({("0050", d): 5 for d in self.window})
        rows = build_snapshot(self.eff, self.cal, obs, top_n=150)
        self.assertEqual(len(rows), 161)                      # 納入 + 排除都在
        self.assertEqual(len([r for r in rows if not r["included"]]), 11)
        for r in rows:
            self.assertEqual(r["effective_date"], self.eff)
            self.assertIsNotNone(r["median_turnover"])
            self.assertIsNotNone(r["observation_days"])
            # migration 006 的雙向 CHECK 在程式層的對應
            self.assertEqual(r["included"], r["exclusion_reason"] is None)
        outside = [r for r in rows
                   if r["exclusion_reason"] == REASON_OUTSIDE_TOP_N % 150]
        self.assertEqual(len(outside), 10)


class PointInTimeTests(unittest.TestCase):
    """提案 §5 的 P1~P5。**P3、P4 是本 SB 的 known-FAIL 主體。**"""

    def setUp(self):
        self.cal = make_calendar(date(2022, 1, 3), 200)
        self.eff = self.cal[70]
        self.window = liquidity_window(self.cal, self.eff, 60)

    def test_p1_universe_point_in_time_no_future_data(self):
        """P1（DEC-017 §Verification 指名）：排名輸入不得含 effective_date 當天或之後。

        **known-FAIL**：下方 `assertRaises` 內的輸入就是那個會失敗的案例 ——
        餵進 effective_date 當天的資料，實作必須 raise。
        若把 `_assert_no_lookahead` 拿掉，這個測試會變紅。
        """
        ok = {("2330", d): 1_000 for d in self.window}
        build_snapshot(self.eff, self.cal, ok)          # 不得 raise

        with self.assertRaises(LookaheadError):
            build_snapshot(self.eff, self.cal,
                           {**ok, ("2330", self.eff): 9_999})
        with self.assertRaises(LookaheadError):
            build_snapshot(self.eff, self.cal,
                           {**ok, ("2330", self.cal[90]): 9_999})

    def test_p2_rebuild_is_deterministic(self):
        """P2：同一 effective_date 重跑兩次逐筆相同（含中位數相同時的名次）。

        **會讓它 FAIL 的輸入**：tie-break 用 `set` 的迭代序或 `now()`。
        故意讓十檔股票中位數完全相同 —— 沒有穩定 tie-break 時，
        **兩次結果會在這十檔上互換名次，而那不會讓任何其他測試變紅**。
        """
        obs = {("200%d" % i, d): 5_000 for i in range(10) for d in self.window}
        first = build_snapshot(self.eff, self.cal, obs)
        second = build_snapshot(self.eff, self.cal, dict(reversed(list(obs.items()))))
        self.assertEqual(first, second)
        self.assertEqual([r["stock_id"] for r in first],
                         sorted(r["stock_id"] for r in first))

    def test_p3_history_unchanged_by_later_data(self):
        """P3：舊快照不得因為後來的資料存在而改變。

        **這條專門抓提案 §0.1 的 (b) 錯誤** —— 用「今日仍存在的股票」過濾歷史。

        **known-FAIL**：`survivor_filtered` 就是那個錯誤實作的輸出。
        它把「期末已不存在的 1101」整個抽掉，快照因此不同 —— 斷言必須抓到差異。
        """
        obs = {("2330", d): 1_000_000 for d in self.cal[:150]}
        obs.update({("1101", d): 900_000 for d in self.cal[:80]})   # 之後消失
        base = build_snapshot(self.eff, self.cal, {
            k: v for k, v in obs.items() if k[1] < self.eff})

        # 加入 effective_date 之後才發生的資料，舊快照必須一模一樣
        obs.update({("2454", d): 5_000_000 for d in self.cal[100:150]})
        again = build_snapshot(self.eff, self.cal, {
            k: v for k, v in obs.items() if k[1] < self.eff})
        self.assertEqual(base, again)

        # known-FAIL：倖存者過濾的實作會產生不同的快照
        survivors = {"2330", "2454"}
        survivor_filtered = build_snapshot(self.eff, self.cal, {
            k: v for k, v in obs.items() if k[1] < self.eff and k[0] in survivors})
        self.assertNotEqual(base, survivor_filtered)
        self.assertIn("1101", {r["stock_id"] for r in base})
        self.assertNotIn("1101", {r["stock_id"] for r in survivor_filtered})

    def test_p4_universe_handles_delisting(self):
        """P4（DEC-017 §Verification 指名）：退出股在**退出前**的快照中仍然存在。

        **這是 Survivorship Bias 的直接測試。**
        `1101` 在 `cal[80]` 之後不再出現。對一個 `effective_date = cal[70]` 的
        觀察者而言，它**當時完全正常** —— 快照必須納入它。

        **known-FAIL**：回溯移除已下市股的實作會讓 `assertIn` 失敗。
        """
        obs = {("2330", d): 1_000_000 for d in self.cal[:150]}
        obs.update({("1101", d): 900_000 for d in self.cal[:80]})
        rows = build_snapshot(self.eff, self.cal,
                             {k: v for k, v in obs.items() if k[1] < self.eff})
        by_id = {r["stock_id"]: r for r in rows}
        self.assertIn("1101", by_id)
        self.assertTrue(by_id["1101"]["included"],
                        "退出前的快照必須納入該股——移除它就是 Survivorship Bias")

        # 退出之後的快照則不再納入（近期性 K = 1）
        later_eff = self.cal[120]
        later = build_snapshot(later_eff, self.cal,
                               {k: v for k, v in obs.items() if k[1] < later_eff})
        later_by_id = {r["stock_id"]: r for r in later}
        self.assertFalse(later_by_id["1101"]["included"])
        # **理由是近期性，不是中位數為 0** —— 兩者在這一列都成立
        # （20/60 天有值，中位數確實是 0），而實作把近期性排在前面判。
        # **刻意斷言在前面那一個**：它是更具體的可觀測事實
        # （「eff 前最後一個交易日沒出現」），而中位數 0 還混著
        # 「有出席但每天零成交」那一類（提案 §2.2a 的已知副作用）。
        self.assertEqual(later_by_id["1101"]["exclusion_reason"],
                         REASON_NO_RECENT_ACTIVITY)

    def test_p5_suspension_is_not_delisting(self):
        """P5：停牌股在停牌期間不從 universe 除名（但排除於當期可交易清單）。

        **會讓它 FAIL 的實作**：把停牌當退出而整列不寫入 ——
        該股回來時會表現為一次假的「新進」事件。

        本斷言要求：停牌期間**該股仍在快照裡**，只是 `included = FALSE`
        且理由是可觀測的 `no_recent_activity`，
        **不是 `delisted`** —— 那會是 INFERENCE 被記錄成事實（提案 §8 第 7 項）。
        """
        active = [d for d in self.cal[:150]]
        halted = set(self.cal[65:75])                     # 橫跨 eff = cal[70]
        obs = {("2330", d): 1_000_000 for d in active}
        obs.update({("1102", d): 800_000 for d in active if d not in halted})
        rows = build_snapshot(self.eff, self.cal,
                             {k: v for k, v in obs.items() if k[1] < self.eff})
        by_id = {r["stock_id"]: r for r in rows}
        self.assertIn("1102", by_id, "停牌股不得從快照消失")
        self.assertFalse(by_id["1102"]["included"])
        self.assertEqual(by_id["1102"]["exclusion_reason"],
                         REASON_NO_RECENT_ACTIVITY)
        self.assertGreater(by_id["1102"]["median_turnover"], 0,
                           "停牌只有 5 天，中位數不該是 0——排除的理由是近期性")

        # 復牌後的下一期必須回到 included，且不需要任何「重新上市」處理
        back_eff = self.cal[90]
        back = build_snapshot(back_eff, self.cal,
                              {k: v for k, v in obs.items() if k[1] < back_eff})
        self.assertTrue({r["stock_id"]: r for r in back}["1102"]["included"])


if __name__ == "__main__":
    unittest.main()
