# src/loaders/etl_run_log.py
"""批次 ETL 的逐項 outcome 記錄與批次總結（UG-G2-SB7）。

================================================================================
本模組要擋的是什麼
================================================================================
SB7 Brief 要求「單一失敗不阻塞」。**若那實作成「跳過失敗的項目、繼續跑」，
那一項在結果裡就長得像「那天沒資料」** —— 而 `CLAUDE.md` §7.1 逐字禁止這件事：

> **Database Error 不得被偽裝成 Empty Result。失敗與「真的沒有資料」必須可區分。**

**批次層比逐項層更危險**：一次跑 150 項，失敗被吞掉時，
**報告上的數字看起來一樣正常**。

================================================================================
`assert_complete()` 是本模組唯一真正在把關的東西
================================================================================
態別計數本身**不會**發現「某一項根本沒被記錄」——
一個被 `except: continue` 吞掉的項目，在任何一格都不會出現，
**而那些數字看起來都很正常**。

所以判準不是「每一態都有記錄」，是 **「各態之和 == 本批的項目數」**。

> **什麼輸入會讓它 FAIL**：讓其中一項拋例外而不記錄 outcome → 和小於項目數。
> **這條專門抓靜默略過**，而它是本模組存在的理由。

⚠ **項目數必須由呼叫端在跑之前就決定**，不能事後由記錄反推 ——
後者永遠相等，那就是一個結構上無法失敗的檢查（§9A.1）。

================================================================================
純邏輯與 DB 存取分離
================================================================================
`summarize()` 與 `assert_complete()` **不碰資料庫、不讀時鐘、不用亂數**，
因此它們的測試可以封閉（同 `universe_builder` 的分層理由，`CLAUDE.md` §13.4）。
"""

OK = "OK"
NO_DATA = "NO_DATA"
FETCH_FAILED = "FETCH_FAILED"
# **第四態，2026-09-04 複查方裁決新增。**
# `ServiceRefusedError`（403／429）與 `FetchFailedError` 在生產程式碼裡分成兩個型別，
# 理由是**處置相反**：前者要停止對該服務施壓，後者只需記下讓其餘項目繼續。
# **那個區別若在 outcome 欄裡消失，run log 就回答不了
#  「那天是被拒絕，還是抓失敗」** —— 型別分得開而詞彙分不開，等於白分。
REFUSED = "REFUSED"

OUTCOMES = (OK, NO_DATA, FETCH_FAILED, REFUSED)
# 需要附上可觀測理由的兩態。
OUTCOMES_REQUIRING_DETAIL = (FETCH_FAILED, REFUSED)


class IncompleteBatchError(RuntimeError):
    """本批的 outcome 記錄數與項目數不符 —— **有項目被靜默略過**。"""


class RunLogEntry(object):
    """一個項目的一次 outcome。

    ⚠ `detail` 只能寫**可觀測的事實**（`HTTP 429`、`TLS handshake failed`），
    **不得寫推論**（`被封鎖`）—— 同 `universe_snapshots.exclusion_reason`。
    """

    __slots__ = ("source", "batch_key", "item_key", "outcome",
                 "detail", "http_attempts")

    def __init__(self, source, batch_key, item_key, outcome,
                 detail=None, http_attempts=None):
        if outcome not in OUTCOMES:
            raise ValueError("未知的 outcome：%r（可用：%s）"
                             % (outcome, ", ".join(OUTCOMES)))
        if outcome in OUTCOMES_REQUIRING_DETAIL and not detail:
            # 與 migration 007 的 CHECK 同一條，**在程式層先擋一次**：
            # 讓「失敗但說不出為什麼」在寫入資料庫之前就失敗。
            raise ValueError("%s 必須附可觀測的 detail" % outcome)
        if outcome not in OUTCOMES_REQUIRING_DETAIL and detail:
            raise ValueError("只有 %s 可以帶 detail；"
                             "一列 outcome=%s 卻寫著理由，會被讀成失敗"
                             % ("／".join(OUTCOMES_REQUIRING_DETAIL), outcome))
        self.source = source
        self.batch_key = batch_key
        self.item_key = item_key
        self.outcome = outcome
        self.detail = detail
        self.http_attempts = http_attempts

    def as_row(self, started_at, target_database):
        return (started_at, self.source, self.batch_key, self.item_key,
                self.outcome, self.detail, target_database, self.http_attempts)

    def __repr__(self):
        return "RunLogEntry(%s/%s=%s)" % (self.batch_key, self.item_key, self.outcome)


def summarize(entries):
    """回傳各 outcome 的計數與 `total`。

    ⚠ **本函式只彙總，不檢查** —— 需要檢查請用 `assert_complete()`。
    **不要為了印摘要而呼叫檢查函式**：那會誘使呼叫端把分母寫成
    「從同一份 entries 數出來的長度」，而 `assert_complete(X, len(X))` **永遠通過**。
    （2026-09-04 實際發生過一次，見 `main_etl_pipeline.run_price_batch` 的註解。）
    """
    counts = dict((o, 0) for o in OUTCOMES)
    for e in entries:
        counts[e.outcome] += 1
    counts["total"] = sum(counts[o] for o in OUTCOMES)
    return counts


def assert_complete(entries, item_count):
    """三數之和必須等於本批的項目數，否則有項目被靜默略過。

    Args:
        entries: 本批記錄到的 `RunLogEntry`。
        item_count: **在跑之前就決定的**項目數。

    Raises:
        IncompleteBatchError: 和不等於 `item_count`。
    """
    counts = summarize(entries)
    if counts["total"] != item_count:
        raise IncompleteBatchError(
            "本批 %d 項，但只記錄到 %d 個 outcome"
            "（OK %d／NO_DATA %d／FETCH_FAILED %d／REFUSED %d）"
            "—— 差額代表有項目被靜默略過，那正是 §7.1 禁止的形態"
            % (item_count, counts["total"], counts[OK], counts[NO_DATA],
               counts[FETCH_FAILED], counts[REFUSED]))
    return counts


def format_summary(source, batch_key, counts):
    """人可讀的一行總結。**三個數字一起印**，不只印失敗數。

    只印失敗數時，「0 個失敗」與「一項都沒跑」看起來一樣。
    """
    return ("[Batch] %s %s｜OK %d／NO_DATA %d／FETCH_FAILED %d／REFUSED %d｜合計 %d"
            % (source, batch_key, counts[OK], counts[NO_DATA],
               counts[FETCH_FAILED], counts[REFUSED], counts["total"]))


_INSERT_SQL = """
INSERT INTO etl_run_log
    (started_at, source, batch_key, item_key, outcome,
     detail, target_database, http_attempts)
VALUES %s
RETURNING run_id;
"""


class EtlRunLogWriter(object):
    """把 `RunLogEntry` 寫進 `etl_run_log`。

    ⚠ **`target_database` 由本類別自己查 `current_database()`，不由呼叫端傳入** ——
    呼叫端傳入的是它**以為**在寫哪裡，而本欄要記的是**實際**寫了哪裡
    （RISK-013：主要寫入路徑不受 `db_target_guard` 保護，只剩流程紀律）。
    """

    def __init__(self, db_config=None):
        from src.loaders.db_writer import DBWriter
        self.db_config = DBWriter(db_config).db_config

    def _connect(self):
        import psycopg2
        return psycopg2.connect(**self.db_config)

    def write(self, entries, started_at):
        """寫入並回傳實際插入的列數。

        以 `RETURNING` 計數而非 `cur.rowcount` ——
        `execute_values` 的 `page_size` 預設 100 會使後者只反映最後一批
        （`UG-G2-SB9` 曾因此把 887 列回報成 87 列）。
        """
        entries = list(entries)
        if not entries:
            return 0
        from psycopg2.extras import execute_values
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database();")
                target_database = cur.fetchone()[0]
                values = [e.as_row(started_at, target_database) for e in entries]
                returned = execute_values(cur, _INSERT_SQL, values,
                                          page_size=len(values), fetch=True)
            conn.commit()
            return len(returned)
        finally:
            conn.close()
