# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 3：458＋NVDA 檔 Triple-Barrier 標籤重算（`daily_ml_features`
真實庫寫入，只動 `target_triple_barrier`／`label_reason` 兩欄）。

**設計核准**：PO 2026-09-11（段 3 設計送審，一項必改＋四項補充，見下方）。

================================================================================
流程
================================================================================
1. 一次讀取全量 `stock_prices`（459 檔，含 `created_at`）、一次計算
   `generate_triple_barrier_labels()`（量體遠小於段 2 特徵計算，不分批）。
2. 計算「預期受影響範圍」（`compute_expected_relabel_impact`）：對既有 3
   檔台股（2330/2382/6488），用「排除段 1 今日重跑插入列」後的子集重算
   一次（= SB1 當時看到的序列形狀），與全量重算比較，分岔的鍵集合即為
   機械算出的預期受影響範圍——**不猜日期**。
3. 唯讀預覽：印預期集合大小、80 列 NULL 價格對照、RISK-025 表。
4. `--write --backup <path>` 才進入寫入。
5. 依 `sorted(stock_id)` 切 50 檔/批，`execute_values` 批次 UPDATE，
   `RETURNING` 計數，每批一交易，commit 前三道檢查。
6. 段級核對：總列數不變、一致性不變式、全表兩欄重算 vs 庫內逐列相等、
   既有 3 檔差異＝預期集合（相等，非僅子集——PO 2026-09-11 複核第二輪
   收緊）且互補集合零差異、標籤分布與算術對帳（只揭露）、80 列 NULL
   對照、RISK-025。

================================================================================
一項必改（PO 2026-09-11 複核指正，已採用）
================================================================================
初版設計想用「扣掉 8 個缺口日期」重建 2330/2382/6488 回補前的序列形狀。
**這是錯的**：2330/2382 在缺口回補前就已有 2026-09-01／09-02 兩列（舊逐股
路徑寫的，`UG_G3_SB2a_GATE_A_PROPOSAL.md` §3.2 登記過），只有 08-24～08-31
六個日期是段 1 今日重跑才新增的；6488 則是 8 個全新。照「8 個缺口日期」
硬扣，2330/2382 會多扣兩列，重建出來的序列**不是 SB1 當時實際看到的**，
預期集合就會算錯。**改為用 `created_at` 判斷**：段 1 今日重跑（8 天缺口
回補）插入的列，`created_at >= SEGMENT1_RERUN_CUTOFF`；重建時只排除
「目標股票 且 今日插入」的列，其餘一律保留——不依賴對日期清單的人工
枚舉，直接用寫入時間這個結構性事實。

================================================================================
四項補充（PO 2026-09-11 複核追加）
================================================================================
1. **互補集合檢查**：預期受影響範圍**之外**的所有列（NVDA 全部、3 檔
   台股非受影響列）必須零差異，明列在輸出裡，不只印「差異 ⊆ 預期」。
2. **SB1 三道檢查移植到分批**：(a) 影響列數改用 `RETURNING` 計數，不用
   `cur.rowcount`（`execute_values` 分頁時 `rowcount` 只反映最後一頁，
   段 1 已踩過）；(b) 逐列精確比對改成一次 `SELECT` 該批鍵集合再比對，
   不逐列查。分批交易邊界的補償是段級「全表兩欄重算 vs 庫內逐列相等」
   （`check_full_table_recompute_equality`）——中斷造成的部分完成狀態
   在這裡一定會被抓到。
3. **80 列 NULL 價格列對照**：依 DEC-035，一列的標籤取決於**未來**幾列
   的價格，跟它自己的價格是否為 NULL 無關；NULL 列造成的影響出現在
   **看得到它的列**：NULL 列的**前一列**因 `Open[T+1]` 缺 → `no_entry`；
   窗口（`pos+1..pos+holding_period`）涵蓋 NULL 列的更前面幾列 →
   `insufficient_data`。NULL 列自身的標籤照樣由它自己的未來資料決定，
   可能是任何正常值——**這是唯讀預覽用真實計算結果驗證後才寫準的敘述**
   （初版寫「NULL 列本身 → no_entry」是誤植，dry-run 對照真實輸出才
   發現：`no_entry` 出現在 NULL 列的前一列，不是 NULL 列自己）。唯讀
   預覽逐列印出對照，屬預期不屬異常。
4. **RISK-025 量測**：458 檔逐檔三類佔比＋Timeout（`target_triple_barrier=0`）
   <5% 的檔數與比例，寫入輸出／證據。DEC-018 揭露條款歸 SB3 D3 處理，
   本段只揭露不把關。

================================================================================
寫入語法（PO 2026-09-11 複核指定）
================================================================================
`execute_values` 的 `UPDATE ... FROM (VALUES %s) ... RETURNING`，不是
`ug_g3_sb1_write_triple_barrier_labels.py` 原本的逐列 `UPDATE`（3,713 次
可行，449,263 次不可行）。型別轉換沿用 SB1：`float64 → Int64 → int`，
**兩欄 NaN 皆轉 `None`**（`label_reason` 在 pandas 3 是 `float('nan')`
不是 `None`，SB1 踩過——直接寫入會被存成文字 `'NaN'`，觸發
`chk_label_reason_consistency` CHECK 拒絕）。

================================================================================
不做的事（明確排除，避免範圍蔓延）
================================================================================
- `label_end_date_tb` 仍不落庫（29 欄契約沒有這欄）。
- `UG-G3-SB2` 的每日尾端掛點（`run_triple_barrier_tail_recompute()`）仍
  不啟用。
- RISK-024（NVDA NaN 列）維持現狀，本段不處理。
"""
import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")

BATCH_SIZE = 50
TOTAL_ROWS_EXPECTED = 449263
EXISTING_LABEL_COUNTS_BEFORE = (3529, 184)  # 段 2 未動標籤，段 3 開工前現況

# 段 1 今日重跑（8 天全市場缺口回補）的時間邊界——用 created_at 而非
# 硬寫日期清單，見模組 docstring「一項必改」。
SEGMENT1_RERUN_CUTOFF = "2026-09-11"

COMPARE_STOCK_IDS = ("2330", "2382", "6488")
CONTROL_STOCK_ID = "NVDA"
HOLDING_PERIOD = 5
MANUAL_REVIEW_CONTEXT = 5

_LABELED_KEY = "__LABELED__"
_MAX_BACKUP_AGE_SECONDS = 24 * 3600


def _load_db_config() -> dict:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError("缺少必要資料庫環境變數：" + ", ".join(missing))
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def _label_key(tb, reason):
    """`(target_triple_barrier, label_reason)` 正規化成可比較、可當 dict
    鍵的形式：NaN／None 統一為 `None`，`target_triple_barrier` 統一為
    `int`。"""
    tb_n = None if pd.isna(tb) else int(tb)
    reason_n = None if pd.isna(reason) else reason
    return (tb_n, reason_n)


# ==============================================================================
# 計算層
# ==============================================================================

def fetch_all_prices_with_created_at(conn) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT stock_id, trade_date, open_price, high_price, low_price, "
        "created_at FROM stock_prices ORDER BY stock_id, trade_date;",
        conn,
    )
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def reconstruct_pre_rerun_prices(df_prices: pd.DataFrame,
                                  stock_ids=COMPARE_STOCK_IDS,
                                  cutoff=SEGMENT1_RERUN_CUTOFF) -> pd.DataFrame:
    """重建段 1 今日重跑前，`stock_ids` 這幾檔的 `stock_prices` 序列形狀
    ——排除「屬於 `stock_ids` 且 `created_at >= cutoff`」的列（今日重跑
    插入的列），其餘股票與其餘列不動。"""
    cutoff_ts = pd.Timestamp(cutoff)
    is_target = df_prices["stock_id"].isin(stock_ids)
    is_new = pd.to_datetime(df_prices["created_at"]) >= cutoff_ts
    exclude = is_target & is_new
    return df_prices.loc[~exclude].reset_index(drop=True)


def compute_expected_relabel_impact(df_prices: pd.DataFrame,
                                     stock_ids=COMPARE_STOCK_IDS) -> set:
    """機械算出的預期受影響鍵集合（PO 2026-09-11 複核核准的設計）：用
    「回補前序列」與「現在完整序列」各重算一次 Triple-Barrier，逐列比較，
    分岔的 `(stock_id, trade_date)` 即為預期受影響範圍。**這是子集關係
    的上界，不是相等**——窗口內容改變不保證標籤值一定改變（可能巧合
    同值），因此實際差異只須是這個集合的子集。"""
    from src.ml.triple_barrier import generate_triple_barrier_labels

    df_old_prices = reconstruct_pre_rerun_prices(df_prices, stock_ids)
    df_old_subset = df_old_prices.loc[df_old_prices["stock_id"].isin(stock_ids)]
    df_new_subset = df_prices.loc[df_prices["stock_id"].isin(stock_ids)]

    old_result = generate_triple_barrier_labels(df_old_subset)
    new_result = generate_triple_barrier_labels(df_new_subset)

    old_map = {
        (r.stock_id, r.trade_date): _label_key(r.target_triple_barrier, r.label_reason)
        for r in old_result.itertuples(index=False)
    }
    new_map = {
        (r.stock_id, r.trade_date): _label_key(r.target_triple_barrier, r.label_reason)
        for r in new_result.itertuples(index=False)
    }

    return {key for key, new_val in new_map.items() if old_map.get(key) != new_val}


# ==============================================================================
# 批次切分與寫入
# ==============================================================================

def split_into_batches(stock_ids, batch_size=BATCH_SIZE):
    sorted_ids = sorted(set(stock_ids))
    return [sorted_ids[i:i + batch_size] for i in range(0, len(sorted_ids), batch_size)]


def assert_batch_stock_subset(df_batch: pd.DataFrame, batch_stock_ids) -> None:
    actual = set(df_batch["stock_id"].unique())
    allowed = set(batch_stock_ids)
    extra = actual - allowed
    if extra:
        raise AssertionError(
            f"批次 DataFrame 含未授權股票 stock_id：{sorted(extra)}"
            f"（本批允許：{sorted(allowed)}）")


def write_one_batch(conn, batch_stock_ids, batch_result: pd.DataFrame) -> int:
    """`execute_values` 批次 `UPDATE...FROM (VALUES %s)...RETURNING`，
    呼叫端負責 commit/rollback（本函式只執行、不 commit，供 commit 前
    核對）。回傳 `RETURNING` 收集到的實際影響列數——不用 `cur.rowcount`
    （PO 2026-09-11 複核要求，`execute_values` 分頁時 `rowcount` 只反映
    最後一頁，段 1 已踩過這個陷阱）。"""
    assert_batch_stock_subset(batch_result, batch_stock_ids)

    records = []
    for row in batch_result.itertuples(index=False):
        tb_val, reason_val = _label_key(row.target_triple_barrier, row.label_reason)
        records.append((row.stock_id, row.trade_date, tb_val, reason_val))

    query = """
        UPDATE daily_ml_features AS d
        SET target_triple_barrier = v.tb, label_reason = v.reason
        FROM (VALUES %s) AS v(stock_id, trade_date, tb, reason)
        WHERE d.stock_id = v.stock_id AND d.trade_date = v.trade_date
        RETURNING d.stock_id;
    """
    with conn.cursor() as cur:
        returned = execute_values(
            cur, query, records,
            template="(%s, %s::date, %s::integer, %s::text)",
            fetch=True,
        )
    return len(returned)


def verify_batch_after_write(conn, batch_stock_ids, batch_result: pd.DataFrame,
                              n_updated_returned: int):
    """commit 前三道檢查（移植自 SB1，改為分批＋向量化）。任一失敗回傳
    `(False, 說明)`；全過回傳 `(True, "OK")`。"""
    ids = list(batch_stock_ids)

    if n_updated_returned != len(batch_result):
        return False, (f"(a) RETURNING 影響列數不符：實際 {n_updated_returned}，"
                        f"預期 {len(batch_result)}")

    expected_dist = Counter()
    for row in batch_result.itertuples(index=False):
        _, reason_val = _label_key(row.target_triple_barrier, row.label_reason)
        expected_dist[(row.stock_id, reason_val or _LABELED_KEY)] += 1

    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_id, COALESCE(label_reason, %s), count(*) "
            "FROM daily_ml_features WHERE stock_id = ANY(%s) GROUP BY 1, 2;",
            (_LABELED_KEY, ids))
        actual_dist = Counter({(sid, reason): cnt for sid, reason, cnt in cur.fetchall()})

    if expected_dist != actual_dist:
        only_expected = {k: v for k, v in expected_dist.items() if actual_dist.get(k) != v}
        only_actual = {k: v for k, v in actual_dist.items() if expected_dist.get(k) != v}
        return False, (f"(b) 分布快篩不符：expected 側 {only_expected}，"
                        f"actual 側 {only_actual}")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_id, trade_date, target_triple_barrier, label_reason "
            "FROM daily_ml_features WHERE stock_id = ANY(%s);", (ids,))
        actual_rows = {
            (sid, td): _label_key(tb, reason) for sid, td, tb, reason in cur.fetchall()
        }

    expected_rows = {
        (row.stock_id, row.trade_date): _label_key(row.target_triple_barrier, row.label_reason)
        for row in batch_result.itertuples(index=False)
    }
    mismatches = [k for k in expected_rows if actual_rows.get(k) != expected_rows[k]]
    if mismatches:
        detail = [(k, expected_rows[k], actual_rows.get(k)) for k in mismatches[:10]]
        return False, f"(c) 逐列比對不符（{len(mismatches)} 筆）：前 10 筆 {detail}"

    return True, "OK"


def run_labels_backfill(conn, batches, df_result_full: pd.DataFrame):
    """逐批寫入＋commit 前核對＋commit／rollback。任一批核對失敗立即
    停止（rollback 該批、不寫下一批）。回傳 `(completed_batches, failed_at)`
    ——`failed_at` 為觸發失敗的批次編號（1-indexed），全數完成時為 `None`。
    重跑整段冪等（UPDATE 語意本身冪等），不支援 `--resume`。"""
    completed_batches = []
    for i, batch_stock_ids in enumerate(batches, start=1):
        batch_result = df_result_full.loc[
            df_result_full["stock_id"].isin(batch_stock_ids)].reset_index(drop=True)
        print(f"\n========== 批次 {i}/{len(batches)}"
              f"（{len(batch_stock_ids)} 檔、{len(batch_result)} 列）==========")
        n_updated = write_one_batch(conn, batch_stock_ids, batch_result)
        ok, detail = verify_batch_after_write(
            conn, batch_stock_ids, batch_result, n_updated)
        print(f"  批次 {i} 核對：{detail}")
        if not ok:
            conn.rollback()
            print(f"  批次 {i} 核對失敗——已 rollback，停止，不寫下一批。"
                  f"已完成批次：{completed_batches}")
            return completed_batches, i
        conn.commit()
        completed_batches.append(i)
    return completed_batches, None


# ==============================================================================
# 段級核對
# ==============================================================================

def check_total_row_count(conn, expected=TOTAL_ROWS_EXPECTED):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM daily_ml_features;")
        n = cur.fetchone()[0]
    return n == expected, n


def check_existing_label_counts(conn, expected=EXISTING_LABEL_COUNTS_BEFORE):
    """開工前常數過期守衛用——段 2 未動標籤，開工當下應仍是
    `EXISTING_LABEL_COUNTS_BEFORE`。抽成獨立函式（不內嵌在 `main()`）
    方便測試直接 mock，比照 `check_total_row_count` 的作法。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(target_triple_barrier), count(label_reason) "
            "FROM daily_ml_features;")
        counts = tuple(cur.fetchone())
    return counts == tuple(expected), counts


def check_label_consistency_invariant(conn):
    """`chk_label_reason_consistency` 的等價全表核對（不只信任 DB CHECK，
    自己也查一次）：`label_reason` 與 `target_triple_barrier` 不得同時
    非 NULL（兩者皆 NULL＝未標籤新股，屬合法狀態，不是違規）。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM daily_ml_features "
            "WHERE label_reason IS NOT NULL AND target_triple_barrier IS NOT NULL;")
        n = cur.fetchone()[0]
    return n == 0, n


def check_full_table_recompute_equality(conn, df_result_full: pd.DataFrame):
    """段級：全表兩欄重算 vs 庫內逐列相等（449,263 列）——PO 2026-09-11
    複核指定的交易邊界補償：分批寫入若中途中斷，「部分完成」狀態在這裡
    一定露餡（沒寫到的批次仍是舊值/NULL，與重算不符）。"""
    df_written = pd.read_sql(
        "SELECT stock_id, trade_date, target_triple_barrier, label_reason "
        "FROM daily_ml_features;", conn)
    df_written["trade_date"] = pd.to_datetime(df_written["trade_date"]).dt.date

    written_map = {
        (r.stock_id, r.trade_date): _label_key(r.target_triple_barrier, r.label_reason)
        for r in df_written.itertuples(index=False)
    }
    expected_map = {
        (r.stock_id, r.trade_date): _label_key(r.target_triple_barrier, r.label_reason)
        for r in df_result_full.itertuples(index=False)
    }
    mismatches = [k for k in expected_map if written_map.get(k) != expected_map[k]]
    return (len(mismatches) == 0), mismatches


def check_impact_subset_and_complement(df_labels_before: dict, df_labels_after: dict,
                                        expected_impact_keys: set,
                                        four_stock_keys: set):
    """既有 3 檔差異 = 預期集合（**相等，不只是子集**——PO 2026-09-11
    複核第二輪要求收緊）；互補集合（預期集合之外的全部，含 NVDA 全部、
    3 檔台股非受影響列）零差異。

    子集關係（`compute_expected_relabel_impact()` 本身只保證「實際差異
    ⊆ 預期」，因為它比的是「窗口內容是否改變」的上界）在**理論上**是對
    的，但**實際跑出來這兩個集合會相等**——因為 `daily_ml_features` 裡
    既有的標籤本來就是同一份 `generate_triple_barrier_labels()` 對同一份
    「回補前序列」算出來的（SB1 當時的寫入結果），不是另一個獨立來源。
    若「實際差異」與「預期集合」不相等，代表 SB1 當時寫進庫的標籤**不是**
    同一份程式碼對同一份舊序列算出的結果——這是必須被發現、不該被子集
    關係悄悄吞掉的事。因此本函式**用相等當作 PASS 條件**，子集/互補的
    拆解只用來在不相等時定位差在哪裡（多了什麼、少了什麼）。

    Args:
        df_labels_before / df_labels_after: `{(stock_id, trade_date):
            (tb, reason)}`，涵蓋 `COMPARE_STOCK_IDS ∪ {CONTROL_STOCK_ID}`
            的寫入前／寫入後標籤快照。
        expected_impact_keys: `compute_expected_relabel_impact()` 的輸出。
        four_stock_keys: 這 4 檔目前在 `daily_ml_features` 的全部鍵
            （寫入後現況，含今日新插入的 20 列本身）。

    Returns:
        `(ok, actual_diff_keys, outside_expected, complement_violations,
          missing_from_actual, is_equal)`——`outside_expected` 是「實際有、
        預期沒有」的差集，`missing_from_actual` 是「預期有、實際沒有」的
        差集，兩者皆空即為 `is_equal`。
    """
    actual_diff_keys = {
        k for k in four_stock_keys
        if df_labels_before.get(k) != df_labels_after.get(k)
    }
    outside_expected = actual_diff_keys - expected_impact_keys
    missing_from_actual = expected_impact_keys - actual_diff_keys
    is_equal = actual_diff_keys == expected_impact_keys

    complement_keys = four_stock_keys - expected_impact_keys
    complement_violations = {
        k for k in complement_keys
        if df_labels_before.get(k) != df_labels_after.get(k)
    }
    ok = is_equal and (not complement_violations)
    return (ok, actual_diff_keys, outside_expected, complement_violations,
            missing_from_actual, is_equal)


def compute_label_reconciliation(df_prices: pd.DataFrame, df_result_full: pd.DataFrame) -> dict:
    """六類分布＋算術對帳（**只揭露不把關**，PO 2026-09-11 複核第二輪
    要求）：

    - `no_entry` 預期基準 = 每檔尾列（`remaining==0`，恰 1 筆／檔）
      ＋「非尾列但 `Open[T+1]` 仍為 NaN」的列數（資料品質缺口造成）。
    - `insufficient_data` 預期基準 = 每檔尾端 `holding_period-1` 列
      （`remaining` 1～`holding_period-1`，恰 4 筆／檔，H=5 時）；實際數字
      與此基準的差額即為「窗口內撞到 NaN High/Low」造成的列數。

    兩個基準都是用來讓人眼核對數量級是否合理，不是拿來擋寫入的斷言——
    `label_reason` 值域已有 DB CHECK、`check_label_consistency_invariant`
    把關過一致性，這裡只負責把「數字為什麼是這樣」攤開來。"""
    df_sorted = df_prices.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    n_stocks = df_sorted["stock_id"].nunique()

    open_next = df_sorted.groupby("stock_id")["open_price"].shift(-1)
    is_last_row = (df_sorted.groupby("stock_id").cumcount(ascending=False) == 0)
    nan_anchor_not_tail = int((open_next.isna() & (~is_last_row)).sum())

    reason_counts = df_result_full["label_reason"].value_counts(dropna=True).to_dict()
    tb_counts = df_result_full["target_triple_barrier"].value_counts(dropna=True).to_dict()

    expected_no_entry_baseline = n_stocks + nan_anchor_not_tail
    expected_insufficient_tail_baseline = n_stocks * (HOLDING_PERIOD - 1)
    actual_no_entry = int(reason_counts.get("no_entry", 0))
    actual_insufficient = int(reason_counts.get("insufficient_data", 0))

    total_labeled_or_reasoned = (
        sum(tb_counts.values()) + sum(reason_counts.values()))

    return {
        "n_stocks": n_stocks,
        "tb_counts": tb_counts,
        "reason_counts": reason_counts,
        "expected_no_entry_baseline": expected_no_entry_baseline,
        "actual_no_entry": actual_no_entry,
        "expected_insufficient_tail_baseline": expected_insufficient_tail_baseline,
        "actual_insufficient_data": actual_insufficient,
        "window_nan_caused_insufficient": actual_insufficient - expected_insufficient_tail_baseline,
        "total_labeled_or_reasoned": total_labeled_or_reasoned,
    }


def print_label_reconciliation(recon: dict) -> None:
    print("\n=== 標籤分布與算術對帳（誠實揭露，不把關）===")
    print(f"六類分布：target_triple_barrier {recon['tb_counts']}；"
          f"label_reason {recon['reason_counts']}")
    total = recon["total_labeled_or_reasoned"]
    if total:
        amb = recon["reason_counts"].get("ambiguous_dual_barrier", 0)
        neg = recon["tb_counts"].get(-1, 0)
        pos = recon["tb_counts"].get(1, 0)
        zero = recon["tb_counts"].get(0, 0)
        print(f"  ambiguous_dual_barrier 佔比：{amb}/{total} = {amb/total:.4f}")
        print(f"  -1 : +1 = {neg} : {pos}"
              + (f"（比例 {neg/pos:.3f}:1，明顯偏空）" if pos and neg > pos * 1.2 else ""))
        print(f"  Timeout(0) 佔比：{zero}/{total} = {zero/total:.4f}")
    print(f"no_entry 對帳：基準（{recon['n_stocks']} 檔尾列 + "
          f"{recon['actual_no_entry'] - recon['n_stocks']} 筆 NaN anchor 非尾列）"
          f"= {recon['expected_no_entry_baseline']}，實際 {recon['actual_no_entry']}")
    print(f"insufficient_data 對帳：尾端基準（{recon['n_stocks']} 檔 × "
          f"{HOLDING_PERIOD - 1} 列）= {recon['expected_insufficient_tail_baseline']}，"
          f"實際 {recon['actual_insufficient_data']}"
          f"（窗口撞 NaN 造成 {recon['window_nan_caused_insufficient']} 筆）")


def find_null_price_rows(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_id, trade_date FROM stock_prices "
            "WHERE open_price IS NULL OR high_price IS NULL OR low_price IS NULL "
            "ORDER BY stock_id, trade_date;")
        return cur.fetchall()


def print_null_price_label_context(df_result_full: pd.DataFrame, null_rows,
                                    context=MANUAL_REVIEW_CONTEXT):
    """80 列 NULL 價格列對照（PO 2026-09-11 複核要求）：依 DEC-035，NULL
    列的**前一列**因 `Open[T+1]` 缺 → `no_entry`；窗口涵蓋 NULL 列的更
    前面幾列 → `insufficient_data`；NULL 列**自身**的標籤由它自己的未來
    資料決定，與它自己缺值無關（模組 docstring「三、80 列」有完整推導，
    真實 dry-run 對照過）。逐列印出對照，屬預期不屬異常，只揭露不把關。

    ⚠ 刻意吃**記憶體中剛算出的 `df_result_full`**，不查 `daily_ml_features`
    ——查 DB 在唯讀預覽（尚未 `--write`）階段只會看到寫入前的舊值（對
    455 檔新股就是全 NULL，對照不出任何東西，證明不了 DEC-035 有沒有
    照規則產生）；用剛算出的結果才是「示範將會寫成什麼」。"""
    print(f"\n=== 80 列 NULL 價格對照（DEC-035 預期規則核對，"
          f"實際 {len(null_rows)} 列）===")
    df_indexed = df_result_full.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    by_stock = {}
    for sid, td in null_rows:
        by_stock.setdefault(sid, []).append(td)
    for sid, dates in sorted(by_stock.items())[:10]:
        stock_rows = df_indexed.loc[df_indexed["stock_id"] == sid].reset_index(drop=True)
        row_dates = list(stock_rows["trade_date"])
        for td in dates:
            if td not in row_dates:
                continue
            idx = row_dates.index(td)
            window = stock_rows.iloc[max(0, idx - context):idx + 1][
                ["trade_date", "target_triple_barrier", "label_reason"]]
            print(f"  {sid}/{td}（NULL 價格列，將寫入的計算結果）：")
            print(window.to_string(index=False))


def compute_risk025_table(df_labels: pd.DataFrame, threshold=0.05):
    """逐股 Timeout（`target_triple_barrier=0`）佔比——只揭露不把關，
    DEC-018／SB3 D3 裁決範圍。

    ⚠ 吃 DataFrame（`target_triple_barrier` 欄即可），不吃 DB 連線——
    唯讀預覽階段查 DB 只會看到寫入前的舊值（455 檔新股 `labeled_n=0`，
    RISK-025 表看起來像只有 3～4 檔有標籤，證明不了任何事）；呼叫端傳
    記憶體中剛算出的 `df_result_full` 才能看到「將會怎樣」。段級核對
    階段沿用同一份 `df_result_full`——`check_full_table_recompute_equality`
    已驗證它與寫入後的 DB 內容逐列相等，不必為了這張揭露表另外重讀。"""
    df = df_labels.groupby("stock_id").agg(
        timeout_n=("target_triple_barrier", lambda s: (s == 0).sum()),
        labeled_n=("target_triple_barrier", "count"),
    ).reset_index()
    df["timeout_ratio"] = df["timeout_n"] / df["labeled_n"].replace(0, np.nan)
    below = df.loc[df["timeout_ratio"] < threshold].sort_values("timeout_ratio")
    return df, below


# ==============================================================================
# 揭露性輸出
# ==============================================================================

def preview_labels_backfill(conn, df_result_full: pd.DataFrame,
                             expected_impact_keys: set, batches) -> None:
    print("\n=== 段 3 標籤回補預覽（唯讀，--write 前必經）===")
    print(f"全量計算：{df_result_full['stock_id'].nunique()} 檔、"
          f"{len(df_result_full)} 列")
    print(f"批次：{len(batches)} 批（{BATCH_SIZE} 檔/批，末批 {len(batches[-1])} 檔）")
    print(f"\n既有 3 檔（{COMPARE_STOCK_IDS}）機械算出的預期受影響鍵數："
          f"{len(expected_impact_keys)}")

    df_dist, below_5pct = compute_risk025_table(df_result_full)
    print(f"\n=== RISK-025：逐股 Timeout 佔比（{len(below_5pct)}／"
          f"{len(df_dist)} 檔 <5%，只揭露不把關）===")
    print(below_5pct.to_string(index=False))

    null_rows = find_null_price_rows(conn)
    print_null_price_label_context(df_result_full, null_rows)


# ==============================================================================
# main
# ==============================================================================

def main(write: bool, backup_path: str) -> None:
    from scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap import _check_backup_or_exit

    if write and not backup_path:
        print("ERROR：--write 必須同時提供 --backup <path>（RISK-013 第二項協議機械化檢查）")
        sys.exit(1)
    if write:
        _check_backup_or_exit(backup_path)

    db_config = _load_db_config()
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user, inet_server_port();")
    conn_info = cur.fetchone()
    current_db = conn_info[0]
    print("CONN CHECK:", conn_info)

    print("\n=== 常數過期守衛 ===")
    ok_rows, actual_rows = check_total_row_count(conn, expected=TOTAL_ROWS_EXPECTED)
    ok_labels, actual_labels = check_existing_label_counts(conn)
    print(f"daily_ml_features 現況：{actual_rows} 列（預期 {TOTAL_ROWS_EXPECTED}）"
          f"[{'PASS' if ok_rows else 'FAIL'}]，標籤 {actual_labels}"
          f"（預期 {EXISTING_LABEL_COUNTS_BEFORE}）[{'PASS' if ok_labels else 'FAIL'}]")
    if not (ok_rows and ok_labels):
        print("ERROR：真實庫現況與常數不符——拒絕執行（唯讀預覽與 --write 皆拒絕）。")
        conn.close()
        sys.exit(1)

    t_start = time.time()
    df_prices = fetch_all_prices_with_created_at(conn)
    from src.ml.triple_barrier import generate_triple_barrier_labels
    df_result_full = generate_triple_barrier_labels(df_prices)
    t_elapsed = time.time() - t_start
    print(f"\n全量標籤計算耗時：{t_elapsed:.2f} 秒"
          f"（{df_result_full['stock_id'].nunique()} 檔、{len(df_result_full)} 列）")

    expected_impact_keys = compute_expected_relabel_impact(df_prices)

    all_stock_ids = sorted(df_result_full["stock_id"].unique())
    batches = split_into_batches(all_stock_ids)

    preview_labels_backfill(conn, df_result_full, expected_impact_keys, batches)

    if not write:
        print("\n【唯讀模式】僅計算與唯讀查詢，不執行任何 UPDATE。"
              "加 --write --backup <path> 執行實際回補。")
        conn.close()
        return

    # 寫入前快照既有 4 檔（3 檔台股＋NVDA）的標籤，供寫入後做互補集合核對。
    four_stocks = COMPARE_STOCK_IDS + (CONTROL_STOCK_ID,)
    with conn.cursor() as c3:
        c3.execute(
            "SELECT stock_id, trade_date, target_triple_barrier, label_reason "
            "FROM daily_ml_features WHERE stock_id = ANY(%s);", (list(four_stocks),))
        labels_before = {
            (sid, td): _label_key(tb, reason) for sid, td, tb, reason in c3.fetchall()
        }

    typed = input(
        f"即將對資料庫 '{current_db}' 執行 {len(batches)} 批標籤 UPDATE"
        f"（{len(df_result_full)} 列）。請輸入資料庫名稱以確認：")
    if typed != current_db:
        print(f"ERROR：輸入 '{typed}' 與目標資料庫 '{current_db}' 不符，拒絕執行。")
        conn.close()
        sys.exit(1)

    completed_batches, failed_at = run_labels_backfill(conn, batches, df_result_full)

    print("\n=== 寫入結果摘要 ===")
    print(f"完成批次：{completed_batches}/{list(range(1, len(batches) + 1))}")
    if failed_at:
        print(f"批次 {failed_at} 核對失敗——已 rollback 該批並停止。"
              f"重跑整段（冪等）是唯一復原方式，不支援 --resume。")
        conn.close()
        sys.exit(1)

    print("\n=== 段級核對 ===")
    all_ok = True

    ok, n = check_total_row_count(conn)
    print(f"1. 總列數：{n}（預期 {TOTAL_ROWS_EXPECTED}）[{'PASS' if ok else 'FAIL'}]")
    all_ok = all_ok and ok

    ok, n = check_label_consistency_invariant(conn)
    print(f"2. 一致性不變式：違規列數 {n}（預期 0）[{'PASS' if ok else 'FAIL'}]")
    all_ok = all_ok and ok

    ok, mismatches = check_full_table_recompute_equality(conn, df_result_full)
    print(f"3. 全表兩欄重算 vs 庫內逐列相等：不符 {len(mismatches)} 筆"
          f"（預期 0）[{'PASS' if ok else 'FAIL'}]")
    if not ok:
        print(f"   前 10 筆：{mismatches[:10]}")
    all_ok = all_ok and ok

    with conn.cursor() as c4:
        c4.execute(
            "SELECT stock_id, trade_date, target_triple_barrier, label_reason "
            "FROM daily_ml_features WHERE stock_id = ANY(%s);", (list(four_stocks),))
        labels_after = {
            (sid, td): _label_key(tb, reason) for sid, td, tb, reason in c4.fetchall()
        }
    four_stock_keys = set(labels_after.keys())
    ok, actual_diff, outside_expected, complement_violations, missing_from_actual, is_equal = (
        check_impact_subset_and_complement(
            labels_before, labels_after, expected_impact_keys, four_stock_keys))
    print(f"4. 既有 3 檔差異＝預期集合：實際差異 {len(actual_diff)} 筆、"
          f"預期集合 {len(expected_impact_keys)} 筆、相等：{'是' if is_equal else '否'}"
          f"[{'PASS' if is_equal else 'FAIL'}]")
    print(f"   互補集合（NVDA 全部＋3 檔非受影響列）零差異：違規 "
          f"{len(complement_violations)} 筆[{'PASS' if not complement_violations else 'FAIL'}]")
    if outside_expected:
        print(f"   範圍外差異（實際有、預期沒有）前 10 筆：{sorted(outside_expected)[:10]}")
    if missing_from_actual:
        print(f"   未達成差異（預期有、實際沒有）前 10 筆：{sorted(missing_from_actual)[:10]}")
    if complement_violations:
        print(f"   互補集合違規前 10 筆：{sorted(complement_violations)[:10]}")
    all_ok = all_ok and ok

    df_dist, below_5pct = compute_risk025_table(df_result_full)
    print(f"\n5. RISK-025：逐股 Timeout 佔比 <5% 共 {len(below_5pct)}／"
          f"{len(df_dist)} 檔（只揭露不把關）")

    recon = compute_label_reconciliation(df_prices, df_result_full)
    print_label_reconciliation(recon)

    null_rows = find_null_price_rows(conn)
    print_null_price_label_context(df_result_full, null_rows)

    conn.close()

    if not all_ok:
        print("\nFAIL：至少一項段級核對不通過——資料已寫入（批次各自 commit，"
              "無法回滾），如實回報不通過，須人工排查。")
        sys.exit(1)
    print("\n全部段級核對通過。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", default=None)
    args = parser.parse_args()
    main(write=args.write, backup_path=args.backup)
