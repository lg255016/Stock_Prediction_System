# src/transform/universe_builder.py
"""Point-in-Time Stock Universe 建構（UG-G2-SB6）。

規格來源：DEC-017（APPROVED，Gate 0 交付物 B/G）、
`doc/upgrade/gates/G2_SB6_GATE_A_PROPOSAL.md`（PO 2026-09-03 核准 Gate A）。

================================================================================
本模組的結構：純邏輯與資料庫存取**刻意分離**
================================================================================
`month_first_trading_days`／`liquidity_window`／`build_snapshot` 都是**純函式** ——
輸入是日曆與觀測值，輸出是快照列，**不碰資料庫、不讀時鐘、不用亂數**。

**這不是為了好看，是為了測試能封閉。** `CLAUDE.md` §13.4 記載本專案有 9 個
測試「其行為取決於環境是否具備資料庫憑證與 DB 內容」。PIT 是本 SB 的核心正確性，
**它的測試不能是那種測試** —— 一個在沒有 DB 時就悄悄跳過的 PIT 測試，
與一個永遠通過的檢查沒有區別（§9A.1）。

================================================================================
⚠ 窗口邊界：**嚴格早於 effective_date**
================================================================================
DEC-017 §Decision 逐字：「每月 Universe 只能使用**生效日前已知**的 60 交易日成交資料」。
提案 §5 的 P1 把它寫成可測形式：`max(trade_date) < effective_date`。

因此 `liquidity_window()` 回傳的是 **effective_date 之前**的 60 個交易日，
**不含 effective_date 當天**。

**為什麼這件事必須嚴格**：一個在 `2022-11-01` 生效的快照，
若使用了 `2022-11-01` 當天的整日成交金額，那份快照要等到當天收盤後才算得出來，
**在當天做任何決定時它並不存在**。那正是 Look-ahead Bias（前視偏誤）。

`_assert_no_lookahead()` 在每次建構時檢查這件事並在違反時 raise，
**不是靠註解約束** —— 見 P1 的 known-FAIL 測試。
"""

import os
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.extractors.twse_market_report import is_common_stock_code

# --- DEC-017 定死的參數（不是可調旋鈕）---
WINDOW_SIZE = 60      # 「過去 60 交易日」
TOP_N = 150           # Phase 1 前 150 大（PO 2026-09-02 裁決；Phase 2 的 500 另案）

# --- 提案 §7 決策點 1，PO 2026-09-03 裁決 ---
# K = 1：股票必須在 **effective_date 之前最後一個交易日**出現於報表中，
# 才視為「仍在交易」。校準見 `G2_SB6_k_threshold_calibration.json`：
# K 從 1 到 15 在資料上零誤判，**故取值不是在權衡，是在一組同樣正確的選項裡挑最簡單的**。
# K = 1 是唯一不需要另一個數字的版本 —— 1 代表「不設窗口」。
RECENCY_K = 1

# --- 排除理由（**只寫可觀測的事實**）---
# ⚠ 提案 §8 第 7 項（PO 2026-09-02 指出）：`effective_date` 當天
# **無法區分「長期停牌」與「已下市」** —— 兩者都是「最近沒有出現」，
# 而區分它們需要未來的資料，PIT 明文禁止使用未來資料。
# **這不是缺陷，是資訊的邊界。** 因此理由只能寫成 `no_recent_activity`，
# 不得寫成 `delisted` 或 `suspended` —— 那會是一個 INFERENCE 被記錄成事實。
REASON_NOT_COMMON_STOCK = "not_common_stock_code"
REASON_NO_RECENT_ACTIVITY = "no_recent_activity"
REASON_ZERO_MEDIAN_TURNOVER = "zero_median_turnover"
REASON_OUTSIDE_TOP_N = "outside_top_%d"


class LookaheadError(ValueError):
    """排名輸入含有 `effective_date` 當天或之後的資料。

    **這個例外存在的意義是它會被丟出來。** 提案 §5 的 P1 要求
    「故意把 effective_date 當日或之後的資料餵進排名 → 必須 FAIL」，
    而一個只寫在註解裡的約束，在被違反時不會發出任何聲音。
    """


class InsufficientHistoryError(ValueError):
    """`effective_date` 之前的交易日不足 WINDOW_SIZE 天（暖機期未過）。"""


def month_first_trading_days(calendar):
    """回傳每個月的第一個**交易日**。

    ⚠ 是交易日不是日曆日 —— 月初逢假日時，該月的重建日是該月首個開市日。
    DEC-017：「每月第一個交易日重建」。

    Args:
        calendar: 已排序、無重複的交易日序列。
    """
    seen = set()
    result = []
    for d in calendar:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def effective_dates(calendar, window_size=WINDOW_SIZE):
    """回傳所有**具備完整 60 日窗**的月首交易日。

    暖機的判準是**交易日序列**，不是月份相減。
    提案 §3 記錄了三個曾經出現過的數字（36／33／46）與各自的錯法：
    36 是用月份相減算的，33 的算法對但輸入已被延伸取代。
    """
    calendar = list(calendar)
    index = {d: i for i, d in enumerate(calendar)}
    return [d for d in month_first_trading_days(calendar)
            if index[d] >= window_size]


def liquidity_window(calendar, effective_date, window_size=WINDOW_SIZE):
    """回傳 `effective_date` **之前**的 `window_size` 個交易日（不含當天）。

    Raises:
        InsufficientHistoryError: 之前的交易日不足 window_size 天。
    """
    calendar = list(calendar)
    try:
        pos = calendar.index(effective_date)
    except ValueError:
        # effective_date 不在日曆上：以「嚴格早於它的交易日」界定窗口，
        # 這使本函式對「非交易日的 effective_date」也有定義良好的行為。
        pos = sum(1 for d in calendar if d < effective_date)
    if pos < window_size:
        raise InsufficientHistoryError(
            "effective_date %s 之前只有 %d 個交易日，不足 %d 天暖機"
            % (effective_date, pos, window_size))
    return calendar[pos - window_size:pos]


def _assert_no_lookahead(observations, effective_date):
    """排名輸入不得含 `effective_date` 當天或之後的資料（提案 §5 P1）。

    **刻意在這裡就擋，而不是相信呼叫端只餵了正確的窗口** ——
    P1 的 known-FAIL 案例就是把未來資料餵進來，
    而一個「呼叫端保證會做對」的約束在被違反時是安靜的。
    """
    offending = sorted({d for (_, d) in observations if d >= effective_date})
    if offending:
        raise LookaheadError(
            "排名輸入含 effective_date %s 當天或之後的資料：%s（共 %d 個日期）"
            % (effective_date, offending[:3], len(offending)))


def build_snapshot(effective_date, calendar, observations,
                   window_size=WINDOW_SIZE, top_n=TOP_N, recency_k=RECENCY_K):
    """建構單一 `effective_date` 的 universe 快照。

    Args:
        effective_date: 生效日（該月第一個交易日）。
        calendar: 已排序的交易日序列（全期）。
        observations: `{(stock_id, trade_date): turnover_amount}`。
            **只需涵蓋窗口內的資料**；含窗口外的資料不影響結果，
            但含 `effective_date` 當天或之後的資料會 raise `LookaheadError`。
        window_size / top_n / recency_k: 見模組層常數。

    Returns:
        list[dict]，**納入與排除的股票都在裡面**（DEC-017 要求保存排除清單）。
        依 rank 遞增排序，排除者排在最後（依 stock_id）。
    """
    _assert_no_lookahead(observations, effective_date)
    window = liquidity_window(calendar, effective_date, window_size)
    window_set = set(window)
    recent_days = set(window[-recency_k:]) if recency_k > 0 else set()

    # 窗口內出現過的所有股票 = 本期候選聯集
    per_stock = {}
    for (stock_id, trade_date), turnover in observations.items():
        if trade_date not in window_set:
            continue
        per_stock.setdefault(stock_id, {})[trade_date] = turnover

    scored = []
    for stock_id, by_date in per_stock.items():
        # **缺席日計為 0**（提案 §2.2a）——不是略過。
        # 這個 0 是觀測（那天確實沒有任何金額成交），不是 fillna。
        values = [by_date.get(d, 0) for d in window]
        median = statistics.median(values)
        scored.append({
            "stock_id": stock_id,
            "median_turnover": int(median),
            "observation_days": len(by_date),
            "is_recent": bool(recent_days & set(by_date)),
        })

    def _exclusion_reason(row):
        if not is_common_stock_code(row["stock_id"]):
            # 取數層已依代號形態排除 ETF／ETN／權證，本層是第二道。
            # **兩道都在，是因為第一道的失效是安靜的** ——
            # 若日後有人繞過 extractor 直接寫入 candidate_prices，
            # 只有這一道會發現。
            return REASON_NOT_COMMON_STOCK
        if not row["is_recent"]:
            return REASON_NO_RECENT_ACTIVITY
        if row["median_turnover"] <= 0:
            return REASON_ZERO_MEDIAN_TURNOVER
        return None

    eligible, excluded = [], []
    for row in scored:
        reason = _exclusion_reason(row)
        (excluded if reason else eligible).append((row, reason))

    # **tie-break 用 stock_id，不是任意順序**（提案 §5 的 P2）：
    # 同一個 effective_date 重跑兩次必須逐筆相同。
    # 字典序不定的 tie-break 會讓兩次結果在中位數相同的股票上互換名次，
    # **而那種不穩定不會讓任何測試變紅，只會讓快照不可重現**。
    eligible.sort(key=lambda pair: (-pair[0]["median_turnover"], pair[0]["stock_id"]))

    result = []
    for i, (row, _) in enumerate(eligible):
        included = i < top_n
        result.append({
            "effective_date": effective_date,
            "stock_id": row["stock_id"],
            "rank": (i + 1) if included else None,
            "median_turnover": row["median_turnover"],
            "observation_days": row["observation_days"],
            "included": included,
            "exclusion_reason": None if included else REASON_OUTSIDE_TOP_N % top_n,
        })
    for row, reason in sorted(excluded, key=lambda pair: pair[0]["stock_id"]):
        result.append({
            "effective_date": effective_date,
            "stock_id": row["stock_id"],
            "rank": None,
            "median_turnover": row["median_turnover"],
            "observation_days": row["observation_days"],
            "included": False,
            "exclusion_reason": reason,
        })
    return result


# ============================================================================
# 資料庫存取層
# ============================================================================

_SELECT_CALENDAR = "SELECT DISTINCT trade_date FROM candidate_prices ORDER BY trade_date;"

# ⚠ **PIT 約束寫進 SQL 本身**，不只寫在 Python 裡。
# `trade_date < %s` 使「取到未來資料」在查詢層就不可能發生 ——
# 兩道防線的成本是一行 WHERE，而少一道的代價是 Survivorship Bias 靜默發生。
_SELECT_WINDOW = """
SELECT stock_id, trade_date, turnover_amount
FROM candidate_prices
WHERE trade_date < %s AND trade_date >= %s;
"""

_UPSERT = """
INSERT INTO universe_snapshots
    (effective_date, stock_id, rank, median_turnover,
     observation_days, included, exclusion_reason)
VALUES %s
ON CONFLICT (effective_date, stock_id) DO UPDATE SET
    rank             = EXCLUDED.rank,
    median_turnover  = EXCLUDED.median_turnover,
    observation_days = EXCLUDED.observation_days,
    included         = EXCLUDED.included,
    exclusion_reason = EXCLUDED.exclusion_reason
RETURNING stock_id;
"""


class UniverseBuilder:
    """把純邏輯接到 `candidate_prices` 與 `universe_snapshots`。

    ⚠ 寫入前必須自行完成 RISK-013 的綁定確認 —— 本類別**不呼叫**
    `assert_safe_migration_target()`，因為它寫的是資料列而非 schema；
    但它會在 `build_all()` 開始前印出 `current_database()`，
    **讓「寫錯資料庫」至少是可見的**。
    """

    def __init__(self, db_config=None):
        from src.loaders.db_writer import DBWriter
        self.db_config = DBWriter(db_config).db_config

    def _connect(self):
        import psycopg2
        return psycopg2.connect(**self.db_config)

    def load_calendar(self, conn):
        with conn.cursor() as cur:
            cur.execute(_SELECT_CALENDAR)
            return [r[0] for r in cur.fetchall()]

    def load_window_observations(self, conn, effective_date, window):
        """只取窗口內的資料。SQL 的 `trade_date < effective_date` 是第一道 PIT 防線。"""
        with conn.cursor() as cur:
            cur.execute(_SELECT_WINDOW, (effective_date, window[0]))
            return {(r[0], r[1]): int(r[2]) for r in cur.fetchall()}

    def store_snapshot(self, conn, rows):
        from psycopg2.extras import execute_values
        if not rows:
            return 0
        values = [(r["effective_date"], r["stock_id"], r["rank"],
                   r["median_turnover"], r["observation_days"],
                   r["included"], r["exclusion_reason"]) for r in rows]
        with conn.cursor() as cur:
            # `page_size` 預設 100 會使 `cur.rowcount` 只反映最後一批 ——
            # `UG-G2-SB9` 曾因此把 887 列回報成 87 列。改以 RETURNING 計數。
            returned = execute_values(cur, _UPSERT, values,
                                      page_size=len(values), fetch=True)
        return len(returned)

    def build_all(self, window_size=WINDOW_SIZE, top_n=TOP_N,
                  recency_k=RECENCY_K, verbose=True):
        """建構全部 effective_date 的快照並寫入。回傳逐期摘要。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_setting('port');")
                dbname, port = cur.fetchone()
            if verbose:
                print("[Universe] 目標資料庫：%s @ %s" % (dbname, port))

            calendar = self.load_calendar(conn)
            targets = effective_dates(calendar, window_size)
            if verbose:
                print("[Universe] 交易日 %d 天｜effective_date %d 個（%s ~ %s）"
                      % (len(calendar), len(targets), targets[0], targets[-1]))

            summary = []
            for eff in targets:
                window = liquidity_window(calendar, eff, window_size)
                obs = self.load_window_observations(conn, eff, window)
                rows = build_snapshot(eff, calendar, obs,
                                      window_size, top_n, recency_k)
                written = self.store_snapshot(conn, rows)
                conn.commit()
                included = [r for r in rows if r["included"]]
                summary.append({
                    "effective_date": eff,
                    "window_first": window[0],
                    "window_last": window[-1],
                    "candidates": len(rows),
                    "included": len(included),
                    "written": written,
                    "min_included_turnover": (included[-1]["median_turnover"]
                                              if included else None),
                })
                if verbose:
                    print("  %s  候選 %4d｜納入 %3d｜寫入 %4d｜窗 %s ~ %s"
                          % (eff, len(rows), len(included), written,
                             window[0], window[-1]))
            return summary
        finally:
            conn.close()


if __name__ == "__main__":
    UniverseBuilder().build_all()
