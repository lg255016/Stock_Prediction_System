# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 2：458＋NVDA 檔特徵回補（`daily_ml_features` 真實庫寫入）。

**設計核准**：PO 2026-09-11（段 2 前置 `c54246c`＋`2ee8141` 複核通過後，
段 2 寫入腳本設計本身另案送審核准，含五項追加要求，見下方「設計追加」）。

================================================================================
流程
================================================================================
1. 唯讀連線，全量計算一次（`recompute_features_full()`，重用
   `ug_g3_sb2a_stage2_baseline_comparison.py`，不重寫，~7 秒）——**計算階段
   完全不分批**。
2. 唯讀預覽（`preview_features_backfill`）：印新增/更新列數、批次清單、
   既有標籤現況、分布快照。**不呼叫 `upsert_ml_features`**。
3. `--write --backup <path>` 才進入寫入（RISK-013 三項協議：PRE 備份存在性
   檢查 + stdin 資料庫名確認）。
4. 依 `sorted(stock_id)` 切 50 檔/批寫入。**每批呼叫一次
   `DBWriter.upsert_ml_features()`——該方法本身 connect → `execute_values`
   → `commit()` → close（`db_writer.py:61-78`），因此「每批一交易」不需要
   額外包 transaction**。批次之間若腳本中途中斷，已 commit 的批次不會自動
   回滾（PO 裁決：接受，因為 upsert 重跑冪等，復原方式是重跑整段，不做
   `--resume`）。
5. 每批核對（任一失敗即停，不寫下一批）：(a) 該批逐股列數比對
   `stock_prices` (b) 抽樣 50 列逐欄回讀 (c) **全表**標籤計數
   `EXPECTED_LABEL_COUNTS` 不變。
6. 全部批次完成後段級核對：總列數、全表標籤計數、455 檔新股標籤全 NULL、
   既有 4 檔基線比對（0 新鍵 0 差異）、7 項不需歷史基準的全表不變式、
   分布快照、4562/4583 人工抽審。

================================================================================
設計追加（PO 2026-09-11 複核，五項）
================================================================================
1. **重跑整段冪等，不做 `--resume`**——多一個狀態就多一個錯的地方；中斷後
   唯一復原方式是重跑全部批次（`upsert_ml_features` 的 `ON CONFLICT DO
   UPDATE` 保證冪等）。
2. **寫入前斷言股票子集**（`assert_batch_stock_subset`）+ **全表**標籤計數
   （不是「該批既有標籤不變」——對 455 檔新股那條件恆為 0→0，是個永遠通過
   的檢查，改成全表計數後此問題自然消失）。
3. **7 項不需歷史基準的全表不變式**（`check_invariants`）：見下方一項
   訂正說明。
4. **對段 3 的交接**：段 2 完成後，既有 2330/2382/6488 在 2026-08-21 之後
   （涵蓋 8 天缺口窗口）的既有 SB1 標籤已過期——H=5 窗口內容因缺口回補而
   改變，含原本因「剩餘不足 H」記 `insufficient_data` 的尾端列，現在可能
   有足夠未來列。**段 3 必須對 458 檔全部重算（本來就是），不是只補 455
   檔新股**；預期既有 3 檔重算後與現有標籤的差異只落在該日期帶，NVDA
   應零差異。本腳本只負責特徵回補，不處理標籤，此節僅為交接記錄。
5. **預覽模式零寫入可證**：`main()` 的 `if not write: ...; return` 在任何
   `DBWriter`/`upsert_ml_features` 之前，結構上不可能觸發寫入；對應
   known-FAIL 測試見 `tests/test_sb2a_backfill_features.py`。

⚠⚠ **一項對 PO 原文的訂正（暖機期不變式）**
================================================================================
PO 原文列出的不變式草案含「暖機期形狀：每檔前 4 列 `volatility_5d` NULL、
前 19 列 `volatility_20d` NULL」，並已自行加註「或依 §5A 的實際定義為準」。
**讀過 `feature_aggregator.py:256-265` 原始碼後確認：實際定義是
`rolling(window, min_periods=2).std().fillna(0.0)`——只有每檔第一列因不足
2 個樣本而強制為 `0.0`，不是 NULL，也不是 4/19 列。** 若照 PO 原文字面
實作，這條不變式在**正確**資料上就會恆常 FAIL，違反 `CLAUDE.md` §9A.1
（不是為偵測而寫）。已改為**重算一致性檢查**（`check_volatility_consistency`
/`check_rsi_consistency`）：直接 import `feature_aggregator.py` 的
`compute_rolling_volatility`／`compute_rsi`，對全表重算後與寫入值比對——
比單純核對「前幾列是不是 NULL」更嚴格（能抓到任何寫入/計算不一致，不只
暖機期形狀），且不依賴可能猜錯的列數。

================================================================================
7 項不變式清單（`check_invariants`，全表，不需歷史基準）
================================================================================
1. `price_consistency`：`close_price`／`volume` 與 `stock_prices` 同鍵相等
2. `return_1d`：`ln(close_t/close_{t-1})`，`fillna(0.0)`
3. `target_consistency`：`target_next_close`／`target_return_1d`／
   `target_up_down` 三欄互相一致（`feature_aggregator.py:890-900`）
4. `rsi_consistency`：對 `close_price` 重算 `compute_rsi()` 比對
5. `volatility_consistency`：對 `return_1d` 重算
   `compute_rolling_volatility(window=5/20)` 比對
6. `source_status_enum`：值域 ⊆ `{SUCCESS, SUCCESS_EMPTY, SOURCE_DEGRADED,
   SOURCE_FAILED}`（DB CHECK 允許四值，`SOURCE_DEGRADED` 現行不可達但仍在
   允許值域內——見 `feature_aggregator.py:557-588`）
7. `sentiment_null_iff_article_zero`：僅對非 `SOURCE_FAILED` 列——`
   SOURCE_FAILED` 列的 `article_count` 契約上保持 NULL（非 0），不適用本
   不變式（`MULTI_SOURCE_DATA_CONTRACT.md:321`）

================================================================================
審查員 2026-09-11 複核追加二項（拋棄式庫 dry-run 通過後併入）
================================================================================
1. **`_values_differ` 的 `decimal.Decimal` 修正**：本檔的 (b) 抽樣回讀
   借用 `ug_g3_sb2a_stage2_baseline_comparison.py` 的 `_values_differ`，
   該函式已修正對 `psycopg2` 原生 `Decimal` 型別的誤判（見該檔案 docstring
   「三版修正」）。本檔不重複說明，只記錄：修正前的版本會讓 (b) 對極小值
   （<1e-4）欄位誤判為不符，導致段 2 寫入在某一批之後才假性失敗停止。
2. **唯讀預覽同時是寫入前的完整證據，不只是數字預告**：
   - 預覽階段**先在記憶體上對 `df_features` 跑一次 7 項不變式**（不需
     等寫入完成才驗證正確性），任一項有違規即 `sys.exit(1)`，連
     `--write` 都不會被授權執行。
   - 新增 `check_existing_state_matches_constants()`：`EXISTING_ROWS_BEFORE`
     ／`EXPECTED_LABEL_COUNTS` 是寫死的基準值，只反映撰寫當下查到的真實
     庫現況——**若這兩個常數已經過期**（例如又有其他回補動作先跑過，
     真實庫現況已經變了），後續所有「預計新增/更新列數」與段級核對基準
     全部不可信。因此在做任何事之前，先查真實庫現況與這兩個常數逐項比對，
     不符即拒絕執行（唯讀預覽與 `--write` 皆拒絕）。
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import psycopg2

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")

BATCH_SIZE = 50

# Part C（`2ee8141`）已驗證的全量重算基準值，段 2 寫入完成後應精確重現。
TOTAL_ROWS_EXPECTED = 449263
EXISTING_ROWS_BEFORE = 3713
EXPECTED_LABEL_COUNTS = (3529, 184)  # (target_triple_barrier 非 NULL, label_reason 非 NULL)

# 人工抽審（PO 指定）：候選池/stock_prices 缺口回補前即存在的兩個異常列
# （NULL 價格但 volume>0），核對 NULL 傳播是否符合 W／F／U 分類。
MANUAL_REVIEW_KEYS = [("4562", "2023-10-30"), ("4583", "2022-09-19")]

# `002_expand_ml_features.sql` 的 CHECK 允許四值；`feature_aggregator.py`
# 現行只產得出前三態，`SOURCE_DEGRADED` 結構上不可達（見模組docstring）。
ALLOWED_SOURCE_STATUS = {"SUCCESS", "SUCCESS_EMPTY", "SOURCE_DEGRADED", "SOURCE_FAILED"}

_NUMERIC_TOLERANCE = 1e-6
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


# ==============================================================================
# 批次切分與寫入
# ==============================================================================

def split_into_batches(stock_ids, batch_size=BATCH_SIZE):
    """依 `sorted(stock_id)` 決定性切分，確保可重跑時批次邊界一致。"""
    sorted_ids = sorted(set(stock_ids))
    return [sorted_ids[i:i + batch_size] for i in range(0, len(sorted_ids), batch_size)]


def assert_batch_stock_subset(df_batch: pd.DataFrame, batch_stock_ids) -> None:
    """寫入前斷言（PO 追加要求 2）：`df_batch` 的股票集合必須是
    `batch_stock_ids` 的子集——防止「某批寫錯了別批的列」這類抽樣回讀
    驗不到的失效模式。"""
    actual = set(df_batch["stock_id"].unique())
    allowed = set(batch_stock_ids)
    extra = actual - allowed
    if extra:
        raise AssertionError(
            f"批次 DataFrame 含未授權股票 stock_id：{sorted(extra)}"
            f"（本批允許：{sorted(allowed)}）")


def write_one_batch(db_writer, df_batch: pd.DataFrame, batch_stock_ids) -> None:
    """呼叫一次 `upsert_ml_features()`——該方法自身的 connect/commit/close
    週期即為本批的交易邊界。抽成獨立函式供測試注入 mock `db_writer`。"""
    assert_batch_stock_subset(df_batch, batch_stock_ids)
    db_writer.upsert_ml_features(df_batch)


def verify_batch_after_write(conn, batch_stock_ids, df_batch: pd.DataFrame,
                              expected_label_counts=EXPECTED_LABEL_COUNTS):
    """每批核對三項，任一失敗回傳 `(False, 說明)`；全過回傳 `(True, "OK")`。
    (a) 列數比對 (b) 抽樣 50 列逐欄回讀 (c) **全表**標籤計數不變。"""
    ids = list(batch_stock_ids)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_id, count(*) FROM daily_ml_features "
            "WHERE stock_id = ANY(%s) GROUP BY stock_id;", (ids,))
        actual_counts = dict(cur.fetchall())
        cur.execute(
            "SELECT stock_id, count(*) FROM stock_prices "
            "WHERE stock_id = ANY(%s) GROUP BY stock_id;", (ids,))
        expected_counts = dict(cur.fetchall())
    mismatches = {
        sid: (expected_counts.get(sid, 0), actual_counts.get(sid, 0))
        for sid in ids if expected_counts.get(sid, 0) != actual_counts.get(sid, 0)
    }
    if mismatches:
        return False, f"(a) 列數不符（預期,實際）：{mismatches}"

    sample_n = min(50, len(df_batch))
    if sample_n:
        from scripts.verify.ug_g3_sb2a_stage2_baseline_comparison import (
            _values_differ, COMPARE_COLUMNS)
        df_sample = df_batch.sample(n=sample_n, random_state=42)
        mismatched_samples = []
        with conn.cursor() as cur:
            for _, row in df_sample.iterrows():
                trade_date = pd.to_datetime(row["trade_date"]).date()
                cur.execute(
                    "SELECT %s FROM daily_ml_features "
                    "WHERE stock_id = %%s AND trade_date = %%s;" % ", ".join(COMPARE_COLUMNS),
                    (row["stock_id"], trade_date))
                db_row = cur.fetchone()
                if db_row is None:
                    mismatched_samples.append((row["stock_id"], str(trade_date), "缺列"))
                    continue
                for col, db_val in zip(COMPARE_COLUMNS, db_row):
                    if _values_differ(row[col], db_val):
                        mismatched_samples.append((row["stock_id"], str(trade_date), col))
        if mismatched_samples:
            return False, f"(b) 抽樣回讀比對不符：{mismatched_samples[:10]}"

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(target_triple_barrier), count(label_reason) "
            "FROM daily_ml_features;")
        actual_label_counts = tuple(cur.fetchone())
    if actual_label_counts != tuple(expected_label_counts):
        return False, (f"(c) 全表標籤計數不符：實際 {actual_label_counts}，"
                        f"預期 {tuple(expected_label_counts)}")

    return True, "OK"


def run_features_backfill(db_writer, conn, batches, df_features,
                           expected_label_counts=EXPECTED_LABEL_COUNTS):
    """逐批寫入＋核對。任一批核對失敗立即停止，不寫下一批（不吞例外、
    不繼續）。回傳 `(completed_batches, failed_at)`——`failed_at` 為觸發
    失敗的批次編號（1-indexed），全數完成時為 `None`。"""
    completed_batches = []
    for i, batch_stock_ids in enumerate(batches, start=1):
        df_batch = df_features.loc[
            df_features["stock_id"].isin(batch_stock_ids)].reset_index(drop=True)
        print(f"\n========== 批次 {i}/{len(batches)}"
              f"（{len(batch_stock_ids)} 檔、{len(df_batch)} 列）==========")
        write_one_batch(db_writer, df_batch, batch_stock_ids)
        ok, detail = verify_batch_after_write(
            conn, batch_stock_ids, df_batch, expected_label_counts)
        print(f"  批次 {i} 核對：{detail}")
        if not ok:
            print(f"  批次 {i} 核對失敗——停止，不寫下一批。"
                  f"已完成批次：{completed_batches}")
            return completed_batches, i
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


def check_label_counts(conn, expected=EXPECTED_LABEL_COUNTS):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(target_triple_barrier), count(label_reason) "
            "FROM daily_ml_features;")
        counts = tuple(cur.fetchone())
    return counts == tuple(expected), counts


def check_new_stock_labels_null(conn, new_stock_ids):
    if not new_stock_ids:
        return True, 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM daily_ml_features WHERE stock_id = ANY(%s) "
            "AND (target_triple_barrier IS NOT NULL OR label_reason IS NOT NULL);",
            (list(new_stock_ids),))
        n = cur.fetchone()[0]
    return n == 0, n


def rerun_baseline_check(conn, compare_stock_ids=None):
    """重跑既有 4 檔基線比對（重用 `ug_g3_sb2a_stage2_baseline_comparison.py`
    的函式，不複製邏輯）。段 2 完成後預期 0 孤兒、0 新鍵、0 逐欄差異。"""
    from scripts.verify.ug_g3_sb2a_stage2_baseline_comparison import (
        recompute_features_full, fetch_existing_features, compare_columns,
        COMPARE_COLUMNS, DEFAULT_COMPARE_STOCK_IDS)
    ids = compare_stock_ids or DEFAULT_COMPARE_STOCK_IDS
    df_recomputed_full = recompute_features_full(conn)
    df_recomputed = df_recomputed_full.loc[
        df_recomputed_full["stock_id"].isin(ids)].reset_index(drop=True)
    df_existing = fetch_existing_features(conn, ids)
    diffs = compare_columns(df_recomputed, df_existing, COMPARE_COLUMNS)
    return (not diffs), diffs


# ==============================================================================
# 不變式（全表，不需歷史基準）——見模組 docstring 的訂正說明與清單
# ==============================================================================

def _close_enough(a, b) -> pd.Series:
    """逐元素比較，NaN 對 NaN 視為相同，數值容許 `_NUMERIC_TOLERANCE`。"""
    a = pd.Series(a).astype(float).reset_index(drop=True)
    b = pd.Series(b).astype(float).reset_index(drop=True)
    both_nan = a.isna() & b.isna()
    diff_ok = ((a - b).abs() <= _NUMERIC_TOLERANCE).fillna(False)
    return both_nan | diff_ok


def check_price_consistency(df_features: pd.DataFrame, df_prices: pd.DataFrame) -> pd.DataFrame:
    merged = df_features.merge(
        df_prices, on=["trade_date", "stock_id"], suffixes=("_ml", "_sp"))
    close_ok = _close_enough(merged["close_price_ml"], merged["close_price_sp"])
    volume_ok = (merged["volume_ml"] == merged["volume_sp"]).reset_index(drop=True)
    bad_mask = ~(close_ok.values & volume_ok.values)
    return merged.loc[bad_mask]


def check_return_1d(df_features: pd.DataFrame) -> pd.DataFrame:
    df_sorted = df_features.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    prev_close = df_sorted.groupby("stock_id")["close_price"].shift(1)
    expected = np.log(
        df_sorted["close_price"].astype(float) / prev_close.astype(float)
    ).fillna(0.0)
    ok = _close_enough(df_sorted["return_1d"], expected)
    return df_sorted.loc[~ok.values]


def check_target_consistency(df_features: pd.DataFrame) -> pd.DataFrame:
    df_sorted = df_features.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    exp_next_close = df_sorted.groupby("stock_id")["close_price"].shift(-1)
    next_close_ok = _close_enough(df_sorted["target_next_close"], exp_next_close)
    exp_return = np.log(
        exp_next_close.astype(float) / df_sorted["close_price"].astype(float))
    return_ok = _close_enough(df_sorted["target_return_1d"], exp_return)
    exp_up_down = exp_return.apply(
        lambda r: 1 if r > 0 else (0 if pd.notna(r) else np.nan))
    up_down_ok = _close_enough(df_sorted["target_up_down"], exp_up_down)
    bad_mask = ~(next_close_ok.values & return_ok.values & up_down_ok.values)
    return df_sorted.loc[bad_mask]


def check_rsi_consistency(df_features: pd.DataFrame) -> pd.DataFrame:
    from src.transform.feature_aggregator import compute_rsi
    df_sorted = df_features.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    exp_rsi = df_sorted.groupby("stock_id")["close_price"].transform(
        lambda x: compute_rsi(x.astype(float), period=14))
    ok = _close_enough(df_sorted["rsi_14"], exp_rsi)
    return df_sorted.loc[~ok.values]


def check_volatility_consistency(df_features: pd.DataFrame) -> pd.DataFrame:
    from src.transform.feature_aggregator import compute_rolling_volatility
    df_sorted = df_features.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    exp_5d = df_sorted.groupby("stock_id")["return_1d"].transform(
        lambda x: compute_rolling_volatility(x, window=5, annualize=True))
    exp_20d = df_sorted.groupby("stock_id")["return_1d"].transform(
        lambda x: compute_rolling_volatility(x, window=20, annualize=True))
    ok_5d = _close_enough(df_sorted["volatility_5d"], exp_5d)
    ok_20d = _close_enough(df_sorted["volatility_20d"], exp_20d)
    bad_mask = ~(ok_5d.values & ok_20d.values)
    return df_sorted.loc[bad_mask]


def check_source_status_enum(df_features: pd.DataFrame) -> pd.DataFrame:
    return df_features.loc[~df_features["source_status"].isin(ALLOWED_SOURCE_STATUS)]


def check_sentiment_null_iff_article_zero(df_features: pd.DataFrame) -> pd.DataFrame:
    """僅對非 `SOURCE_FAILED` 列成立——`SOURCE_FAILED` 列的 `article_count`
    契約上保持 NULL（非 0），該來源當日不填補，見模組 docstring 不變式 7。"""
    df_scope = df_features.loc[df_features["source_status"] != "SOURCE_FAILED"]
    article_zero = (df_scope["article_count"].fillna(0) == 0).reset_index(drop=True)
    sentiment_null = df_scope["sentiment_mean"].isna().reset_index(drop=True)
    bad_mask = (article_zero != sentiment_null).values
    return df_scope.reset_index(drop=True).loc[bad_mask]


def check_invariants(df_features: pd.DataFrame, df_prices: pd.DataFrame) -> dict:
    """回傳 `{不變式名稱: 違規列 DataFrame}`——只含有違規的項目，全過則為
    空字典。7 項清單見模組 docstring。"""
    checks = {
        "price_consistency": check_price_consistency(df_features, df_prices),
        "return_1d": check_return_1d(df_features),
        "target_consistency": check_target_consistency(df_features),
        "rsi_consistency": check_rsi_consistency(df_features),
        "volatility_consistency": check_volatility_consistency(df_features),
        "source_status_enum": check_source_status_enum(df_features),
        "sentiment_null_iff_article_zero": check_sentiment_null_iff_article_zero(df_features),
    }
    return {name: bad for name, bad in checks.items() if not bad.empty}


# ==============================================================================
# 揭露性輸出（不把關，只誠實揭露）
# ==============================================================================

def print_distribution_snapshot(df_features: pd.DataFrame) -> None:
    print("\n=== 分布快照（誠實揭露，不美化）===")
    null_ratio = df_features.groupby("stock_id")["sentiment_mean"].apply(
        lambda s: s.isna().mean())
    print(f"sentiment_mean NULL 比例：全體平均 {null_ratio.mean():.3f}")
    print(f"NULL 比例最高 5 檔：\n{null_ratio.sort_values(ascending=False).head(5)}")
    status_counts = df_features["source_status"].value_counts(dropna=False)
    print(f"\nsource_status 分布：\n{status_counts}")


def manual_review_print(conn, keys=MANUAL_REVIEW_KEYS, context=5) -> None:
    print("\n=== 人工抽審（4562/4583 異常列前後 context，PO 逐列判讀）===")
    for stock_id, trade_date in keys:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trade_date, close_price, volume, article_count, "
                "sentiment_mean, source_status, target_triple_barrier, label_reason "
                "FROM daily_ml_features WHERE stock_id = %s ORDER BY trade_date;",
                (stock_id,))
            rows = cur.fetchall()
        dates = [r[0] for r in rows]
        target = pd.Timestamp(trade_date).date()
        if target not in dates:
            print(f"  {stock_id}/{trade_date}：不在 daily_ml_features"
                  f"（可能非交易日或尚未回補）")
            continue
        idx = dates.index(target)
        window = rows[max(0, idx - context):idx + context + 1]
        print(f"\n  股票 {stock_id}，目標日 {trade_date} 前後 {context} 列：")
        for r in window:
            print(f"    {r}")


def preview_features_backfill(conn, df_features: pd.DataFrame, batches) -> None:
    n_total = len(df_features)
    n_new = n_total - EXISTING_ROWS_BEFORE
    print("\n=== 段 2 特徵回補預覽（唯讀，--write 前必經）===")
    print(f"全量計算：{df_features['stock_id'].nunique()} 檔、{n_total} 列")
    print(f"daily_ml_features 現況：{EXISTING_ROWS_BEFORE} 列，"
          f"標籤 {EXPECTED_LABEL_COUNTS[0]}/{EXPECTED_LABEL_COUNTS[1]}")
    print(f"預計：新增 {n_new} 列、更新 {EXISTING_ROWS_BEFORE} 列")
    print(f"批次：{len(batches)} 批（{BATCH_SIZE} 檔/批，末批 {len(batches[-1])} 檔）")
    for i, b in enumerate(batches, start=1):
        print(f"  批次 {i}：{b[0]}~{b[-1]}（{len(b)} 檔）")
    print_distribution_snapshot(df_features)


# ==============================================================================
# main
# ==============================================================================

def main(write: bool, backup_path: str) -> None:
    from scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap import _check_backup_or_exit
    from scripts.verify.ug_g3_sb2a_stage2_baseline_comparison import (
        recompute_features_full, fetch_all_prices, DEFAULT_COMPARE_STOCK_IDS)

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

    # 常數過期守衛（審查員 2026-09-11 複核追加）：EXISTING_ROWS_BEFORE／
    # EXPECTED_LABEL_COUNTS 是寫死的基準值，只反映撰寫當下查到的真實庫
    # 現況——若不符，代表常數已過期，後續所有數字都不可信，唯讀預覽與
    # --write 一律拒絕，不得沿用過期常數繼續往下跑。
    print("\n=== 常數過期守衛 ===")
    ok_rows, actual_rows = check_total_row_count(conn, expected=EXISTING_ROWS_BEFORE)
    ok_labels, actual_labels = check_label_counts(conn, expected=EXPECTED_LABEL_COUNTS)
    print(f"daily_ml_features 現況：{actual_rows} 列（預期 {EXISTING_ROWS_BEFORE}）"
          f"[{'PASS' if ok_rows else 'FAIL'}]，標籤 {actual_labels}"
          f"（預期 {EXPECTED_LABEL_COUNTS}）[{'PASS' if ok_labels else 'FAIL'}]")
    if not (ok_rows and ok_labels):
        print("ERROR：真實庫現況與 EXISTING_ROWS_BEFORE／EXPECTED_LABEL_COUNTS 不符，"
              "常數可能已過期——拒絕執行（唯讀預覽與 --write 皆拒絕）。")
        conn.close()
        sys.exit(1)

    t_start = time.time()
    df_features = recompute_features_full(conn)
    t_elapsed = time.time() - t_start
    print(f"\n全量計算耗時：{t_elapsed:.2f} 秒"
          f"（{df_features['stock_id'].nunique()} 檔、{len(df_features)} 列）")

    df_prices = fetch_all_prices(conn)

    # 不變式在寫入前就先對記憶體中的計算結果跑一次（審查員 2026-09-11 複核
    # 追加）：唯讀預覽不再只是數字預告，本身就是「寫入前證據」——任一項
    # 違規即拒絕執行，連 --write 都不會被授權。
    t_inv_start = time.time()
    preview_invariant_diffs = check_invariants(df_features, df_prices)
    t_inv_elapsed = time.time() - t_inv_start
    if preview_invariant_diffs:
        print(f"\n不變式（唯讀預覽，對記憶體中的計算結果，{t_inv_elapsed:.2f} 秒）："
              f"FAIL——{list(preview_invariant_diffs.keys())}")
        for name, bad_df in preview_invariant_diffs.items():
            print(f"   {name}：{len(bad_df)} 列違規，前 5 列：\n{bad_df.head(5)}")
        conn.close()
        sys.exit(1)
    print(f"\n不變式（唯讀預覽，對記憶體中的計算結果）：全數 PASS"
          f"（7 項，{t_inv_elapsed:.2f} 秒）")

    all_stock_ids = sorted(df_features["stock_id"].unique())
    batches = split_into_batches(all_stock_ids)
    new_stock_ids = [s for s in all_stock_ids if s not in DEFAULT_COMPARE_STOCK_IDS]

    preview_features_backfill(conn, df_features, batches)

    if not write:
        print("\n【唯讀模式】僅計算與唯讀查詢，不呼叫 upsert_ml_features、"
              "不執行任何寫入。加 --write --backup <path> 執行實際回補。")
        conn.close()
        return

    typed = input(
        f"即將對資料庫 '{current_db}' 執行 {len(batches)} 批特徵寫入"
        f"（{len(df_features)} 列）。請輸入資料庫名稱以確認：")
    if typed != current_db:
        print(f"ERROR：輸入 '{typed}' 與目標資料庫 '{current_db}' 不符，拒絕執行。")
        conn.close()
        sys.exit(1)

    from src.loaders.db_writer import DBWriter
    db_writer = DBWriter()

    completed_batches, failed_at = run_features_backfill(
        db_writer, conn, batches, df_features)

    print("\n=== 寫入結果摘要 ===")
    print(f"完成批次：{completed_batches}/{list(range(1, len(batches) + 1))}")
    if failed_at:
        print(f"批次 {failed_at} 核對失敗——停止。已寫入的批次無法自動回滾"
              f"（各批已各自 commit）；重跑整段（冪等）是唯一復原方式，"
              f"不支援 --resume。")
        conn.close()
        sys.exit(1)

    print("\n=== 段級核對 ===")
    all_ok = True

    ok, n = check_total_row_count(conn)
    print(f"1. 總列數：{n}（預期 {TOTAL_ROWS_EXPECTED}）[{'PASS' if ok else 'FAIL'}]")
    all_ok = all_ok and ok

    ok, counts = check_label_counts(conn)
    print(f"2. 標籤計數：{counts}（預期 {EXPECTED_LABEL_COUNTS}）[{'PASS' if ok else 'FAIL'}]")
    all_ok = all_ok and ok

    ok, n = check_new_stock_labels_null(conn, new_stock_ids)
    print(f"3. 新股標籤應全 NULL：違規列數 {n}（預期 0）[{'PASS' if ok else 'FAIL'}]")
    all_ok = all_ok and ok

    ok, diffs = rerun_baseline_check(conn)
    if ok:
        print("4. 既有 4 檔基線比對：PASS（0 孤兒、0 新鍵、0 逐欄差異）")
    else:
        print(f"4. 既有 4 檔基線比對：FAIL——{list(diffs.keys())}")
    all_ok = all_ok and ok

    # df_prices 沿用預覽階段已讀取的版本——段 2 不寫 stock_prices，
    # 兩個時間點的內容相同，不必重查一次。
    df_written = pd.read_sql("SELECT * FROM daily_ml_features;", conn)
    df_written["trade_date"] = pd.to_datetime(df_written["trade_date"]).dt.date
    invariant_diffs = check_invariants(df_written, df_prices)
    if invariant_diffs:
        print(f"5. 不變式：FAIL——{list(invariant_diffs.keys())}")
        for name, bad_df in invariant_diffs.items():
            print(f"   {name}：{len(bad_df)} 列違規，前 5 列：\n{bad_df.head(5)}")
        all_ok = False
    else:
        print("5. 不變式：全數 PASS（7 項）")

    print_distribution_snapshot(df_written)
    manual_review_print(conn, MANUAL_REVIEW_KEYS)

    print("\n⚠ 對段 3 的交接：既有 2330/2382/6488 在 2026-08-21 之後、涵蓋"
          "缺口回補窗口的既有 SB1 標籤已過期（H=5 窗口內容因缺口回補而改變，"
          "含原本因『剩餘不足 H』記 insufficient_data 的尾端列，現在可能有"
          "足夠未來列）。段 3 必須對 458 檔全部重算，不是只補 455 檔新股；"
          "預期既有 3 檔重算後與現有標籤的差異只落在該日期帶，NVDA 應零差異。")

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
