# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 1：458 檔 Universe 股價回補（`stock_prices` ← `candidate_prices`）。

比照 `scripts/verify/ug_g3_sb2_backfill_entity_mapping.py`（最近的範本）與
`scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py` 既有模式：連線參數
全走環境變數，不在本檔留下任何字面連線值（CHAL-008 教訓）；寫入前必須完成
RISK-013 三項協議（binding confirmation／`pg_dump` 備份／拋棄式容器還原驗證）；
`--write` 模式檢查備份檔存在、非空、24 小時內新鮮，並要求 stdin 二次確認庫名。

**規格來源**：`UG_G3_SB2a_GATE_A_PROPOSAL.md` §3.2（重疊區處理規則）、§3.4（段 1
腳本設計）、§7（RISK-013）；PO 2026-09-10 對段 1 腳本的五項明確要求。

**選取規則（§3.2 一般規則）**：`universe_snapshots.included` 聯集的 458 檔 ×
`candidate_prices` 全部日期，**排除 `stock_prices` 已有的 `(stock_id,
trade_date)`**——只補「既有列缺席的日期」，不覆寫既有列。

**先查再插，不用 `ON CONFLICT`**（PO 2026-09-10 二擇一裁決，比照
`ug_g3_sb2_backfill_entity_mapping.py` 已確立的原則）：待插入集合在 Python／
pandas 端算好（`compute_missing_rows`，`stock_id`＋`trade_date` 的
`MultiIndex` 差集），寫入用純 `INSERT`（**不加 `ON CONFLICT`**）——任何意外
撞鍵（代表 `compute_missing_rows` 的排除邏輯有缺陷）大聲失敗並 `rollback`，
不被 `DO NOTHING` 靜默吞掉（`CLAUDE.md` §7.1）。

**欄位對映**：只取 `stock_prices` 已有的七欄（`stock_id`／`trade_date`／
OHLC／`volume`）＋ migration 009 新增的 `source`，`source` 帶 `candidate_prices`
那一列的原值過來（不寫字面 `'candidate_prices'`——RISK-022 要分辨的是調整
基準，基準由原始報表決定，見 `main_etl_pipeline.py` 既有註解的同一原則）。
不帶 `candidate_prices` 獨有的 `turnover_amount` 等欄——`stock_prices` 沒有
那些欄，決策點 2 的邊界是「不擴充 `stock_prices` 的 schema」。

**80 列 SQL NULL 價格列（§3.3，非 RISK-024）照插不特殊處理**：`UG-G3-SB1` 的
Triple-Barrier 消費端已正確處理 NaN（NaN High/Low → `insufficient_data`；
NaN anchor → `no_entry`，`874b3bf` 修復），本腳本不需要新的防禦邏輯。

**單一交易，不分批**（§3.5：段 1 純資料庫內操作，零外部請求，INSERT 一次
交易完成）。commit 前四項核對（PO 2026-09-10）：(1) 實際 INSERT 影響列數
== 預覽的待插入列數；(2) `stock_prices` 總列數 == 寫入前總列數 + 插入數；
(3) 逐股「插入後列數 == 插入前列數 + 該檔待插入列數」；(4) 隨機抽樣最多
100 列 ＋ 全部 SQL NULL 價格列，逐欄讀回精確比對。任一不符即 `rollback`，
不 commit。

⚠⚠ **核對 3 的措辭（2026-09-10 複核修正）**：原設計誤寫成「插入後逐股
列數 == `candidate_prices` 該股列數」——這假設「`stock_prices` 既有列數
== `candidate_prices` 列數」，對 2330／2382 不成立（§3.2 登記的
2026-09-01／09-02 批次覆蓋缺口使 `stock_prices` 987 列多於
`candidate_prices` 985 列），會在真實庫上對這兩檔必然 FAIL（審查方拋棄式
庫全量 `--write` dry-run 實測抓到）。**本腳本只保證「補進了該補的」，
不宣稱「插入後兩表列數相等」**——正確核對是插入前後的差值，見
`execute_write_and_verify` 內對應段落的行內註解。

⚠ 本腳本尚未對真實庫執行 `--write`——首次執行需 PO binding confirmation
（RISK-013 三項協議），比照 `UG-G3-SB1`／`UG-G3-SB2` 流程。
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
_MAX_BACKUP_AGE_SECONDS = 24 * 3600
_SPOT_CHECK_SAMPLE_SIZE = 100

# 與 `src/loaders/db_writer.py::DBWriter.STOCK_PRICE_COLUMNS` 同一份契約
# （寫入欄位順序），此處獨立宣告——本腳本走原生 psycopg2＋`execute_values`，
# 不經過 `DBWriter.upsert_to_stock_prices()`（該方法是 `ON CONFLICT DO
# UPDATE SET` 語意的每日 upsert 路徑，CHAL-010 之後排除標籤欄；本腳本要的
# 是「只補缺席、絕不覆寫」，兩者語意不同，不可混用）。
STOCK_PRICE_COLUMNS = [
    "stock_id", "trade_date", "open_price", "high_price",
    "low_price", "close_price", "volume", "source",
]

_INSERT_SQL = """
INSERT INTO stock_prices
  (stock_id, trade_date, open_price, high_price, low_price, close_price,
   volume, source)
VALUES %s
RETURNING stock_id;
"""
# ⚠ **無 `ON CONFLICT`**（本檔頭段說明的裁決）；**以 `RETURNING` 計數，
# 不用 `cur.rowcount`**——`execute_values` 的 `page_size` 若小於總筆數，
# `cur.rowcount` 只反映最後一批，`UG-G2-SB9` 曾因此把實際列數誤報
# （`src/loaders/db_writer.py::upsert_to_candidate_prices` 註解記載）。


def compute_missing_rows(
    df_candidate: pd.DataFrame, df_existing_keys: pd.DataFrame
) -> pd.DataFrame:
    """`df_candidate` 中不在 `df_existing_keys`（`stock_prices` 現有
    `(stock_id, trade_date)`）的列——即待插入的缺席日期。

    §3.2 一般規則：只補缺席，不覆寫既有列。用 `MultiIndex` 差集而非逐列
    迴圈比對，458 檔×~971 列規模下才不會慢到不可用。
    """
    cand = df_candidate.copy().reset_index(drop=True)
    cand["trade_date"] = pd.to_datetime(cand["trade_date"]).dt.date
    if df_existing_keys is None or df_existing_keys.empty:
        return cand
    existing = df_existing_keys.copy()
    existing["trade_date"] = pd.to_datetime(existing["trade_date"]).dt.date
    existing_idx = pd.MultiIndex.from_frame(existing[["stock_id", "trade_date"]])
    cand_idx = pd.MultiIndex.from_frame(cand[["stock_id", "trade_date"]])
    mask = ~cand_idx.isin(existing_idx)
    return cand.loc[mask].reset_index(drop=True)


def summarize_preview(df_candidate: pd.DataFrame, df_existing_keys: pd.DataFrame,
                       df_missing: pd.DataFrame) -> str:
    """唯讀預覽摘要（PO 2026-09-10 要求 4 項）：
    (a) 預計插入列數；(b) 依 `source` 分布；(c) 依股票列數的 min/max；
    (d) 既有 3 檔（若在 458 檔宇宙內）各自被跳過（已存在）的列數；
    (e) 80 列 SQL NULL 價格列中，有多少會被本次插入（照插，不特殊處理）。
    """
    lines = []
    lines.append(f"候選池（458 檔全部列）：{len(df_candidate)} 列")
    lines.append(f"stock_prices 現有 (stock_id, trade_date) 組合：{len(df_existing_keys)} 列")
    lines.append(f"待插入（缺席日期）：{len(df_missing)} 列")
    lines.append(f"跳過（已存在，不覆寫）：{len(df_candidate) - len(df_missing)} 列")

    if not df_missing.empty:
        lines.append("\n依 source 分布（待插入）：")
        for src, cnt in df_missing["source"].value_counts(dropna=False).items():
            lines.append(f"  {src!r}: {cnt}")

        per_stock = df_missing.groupby("stock_id").size()
        lines.append(
            f"\n依股票待插入列數：min={per_stock.min()}（{per_stock.idxmin()}）、"
            f"max={per_stock.max()}（{per_stock.idxmax()}）、"
            f"檔數={per_stock.shape[0]}"
        )

        null_price_mask = (
            df_missing["open_price"].isna() | df_missing["high_price"].isna()
            | df_missing["low_price"].isna() | df_missing["close_price"].isna()
        )
        lines.append(
            f"\n待插入列中 SQL NULL 價格列（§3.3，非 RISK-024）："
            f"{int(null_price_mask.sum())} 列——照插，不特殊處理"
            f"（UG-G3-SB1 Triple-Barrier 消費端已正確處理，874b3bf）"
        )

    existing_stock_ids = ("2330", "2382", "6488")
    for sid in existing_stock_ids:
        if sid in df_candidate["stock_id"].values:
            cand_n = int((df_candidate["stock_id"] == sid).sum())
            missing_n = int((df_missing["stock_id"] == sid).sum()) if not df_missing.empty else 0
            skipped_n = cand_n - missing_n
            lines.append(
                f"\n既有股票 {sid}：candidate_prices {cand_n} 列，"
                f"待插入 {missing_n} 列，跳過（已存在）{skipped_n} 列"
            )

    return "\n".join(lines)


def write_missing_rows(conn, df_rows: pd.DataFrame) -> int:
    """以純 `INSERT`（**不用 `ON CONFLICT`**）批次寫入 `df_rows` 至
    `stock_prices`。**不 commit**——呼叫端於讀回核對通過後才 commit。
    任何例外 `conn.rollback()` 後重新拋出，不吞掉（`CLAUDE.md` §7.1）。

    以 `RETURNING stock_id` 計數，不用 `cur.rowcount`（見檔頭 `_INSERT_SQL`
    上方註解）。單一交易、單一 `execute_values` 呼叫（`page_size` 給滿，
    §3.5 段 1 不分批）。

    Returns: int，實際 INSERT 影響列數。
    """
    if df_rows is None or df_rows.empty:
        return 0
    values = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in df_rows[STOCK_PRICE_COLUMNS].itertuples(index=False, name=None)
    ]
    try:
        with conn.cursor() as cur:
            returned = execute_values(
                cur, _INSERT_SQL, values, page_size=len(values), fetch=True)
        return len(returned)
    except Exception:
        conn.rollback()
        raise


def _fetch_stock_prices_keys(cur) -> pd.DataFrame:
    cur.execute("SELECT stock_id, trade_date FROM stock_prices;")
    return pd.DataFrame(cur.fetchall(), columns=["stock_id", "trade_date"])


def _fetch_stock_prices_total_count(cur) -> int:
    cur.execute("SELECT count(*) FROM stock_prices;")
    return cur.fetchone()[0]


def _fetch_per_stock_counts(cur, table: str, stock_ids) -> pd.Series:
    cur.execute(
        f"SELECT stock_id, count(*) FROM {table} WHERE stock_id = ANY(%s) "
        f"GROUP BY stock_id;",
        (list(stock_ids),),
    )
    rows = cur.fetchall()
    return pd.Series({sid: cnt for sid, cnt in rows}, name="count")


def _build_spot_check_sample(df_missing: pd.DataFrame, sample_size: int) -> pd.DataFrame:
    """隨機抽樣最多 `sample_size` 列 **＋ 全部 SQL NULL 價格列**（PO 2026-09-10
    複核指出：隨機抽樣幾乎不會碰到那 80 列，而它們正是 NULL→None 轉換
    最容易出錯的地方，必須全部涵蓋，不能只靠機率）。"""
    if df_missing.empty:
        return df_missing
    null_price_mask = (
        df_missing["open_price"].isna() | df_missing["high_price"].isna()
        | df_missing["low_price"].isna() | df_missing["close_price"].isna()
    )
    df_null_rows = df_missing.loc[null_price_mask]

    n = min(sample_size, len(df_missing))
    df_random = df_missing.sample(n=n, random_state=42)

    combined = pd.concat([df_random, df_null_rows]).drop_duplicates(
        subset=["stock_id", "trade_date"])
    return combined.reset_index(drop=True)


def _spot_check_rows(cur, df_missing: pd.DataFrame, sample_size: int) -> None:
    """隨機抽樣最多 `sample_size` 列 ＋ 全部 SQL NULL 價格列，逐欄讀回精確
    比對（PO 2026-09-10 要求）。

    任一列任一欄不符即 raise——由呼叫端 `rollback`。
    """
    if df_missing.empty:
        return
    sample = _build_spot_check_sample(df_missing, sample_size)

    for row in sample.itertuples(index=False):
        cur.execute(
            "SELECT open_price, high_price, low_price, close_price, volume, "
            "source FROM stock_prices WHERE stock_id = %s AND trade_date = %s;",
            (row.stock_id, row.trade_date),
        )
        db_row = cur.fetchone()
        if db_row is None:
            raise RuntimeError(
                f"抽樣核對失敗：{row.stock_id}@{row.trade_date} 讀回時找不到列"
            )
        expected = (row.open_price, row.high_price, row.low_price,
                    row.close_price, row.volume, row.source)
        for col_name, exp_val, db_val in zip(
            ("open_price", "high_price", "low_price", "close_price",
             "volume", "source"),
            expected, db_row,
        ):
            exp_is_null = pd.isna(exp_val)
            db_is_null = db_val is None
            if exp_is_null and db_is_null:
                continue
            if exp_is_null != db_is_null:
                raise RuntimeError(
                    f"抽樣核對失敗：{row.stock_id}@{row.trade_date}.{col_name} "
                    f"NULL 狀態不符（預期 {exp_val!r}，讀回 {db_val!r}）"
                )
            if col_name == "volume":
                if int(exp_val) != int(db_val):
                    raise RuntimeError(
                        f"抽樣核對失敗：{row.stock_id}@{row.trade_date}.{col_name} "
                        f"不符（預期 {exp_val!r}，讀回 {db_val!r}）"
                    )
            elif col_name == "source":
                if str(exp_val) != str(db_val):
                    raise RuntimeError(
                        f"抽樣核對失敗：{row.stock_id}@{row.trade_date}.{col_name} "
                        f"不符（預期 {exp_val!r}，讀回 {db_val!r}）"
                    )
            else:
                if abs(float(exp_val) - float(db_val)) > 1e-6:
                    raise RuntimeError(
                        f"抽樣核對失敗：{row.stock_id}@{row.trade_date}.{col_name} "
                        f"不符（預期 {exp_val!r}，讀回 {db_val!r}）"
                    )
    print(f"抽樣核對通過：{len(sample)} 列（隨機樣本 + 全部 SQL NULL 價格列）"
          f"逐欄讀回與記憶體預期完全相符。")


def execute_write_and_verify(
    conn, df_candidate: pd.DataFrame, df_existing_keys: pd.DataFrame,
    df_missing: pd.DataFrame,
) -> int:
    """寫入 `df_missing` 至 `stock_prices` 並於 commit 前完成四項核對
    （PO 2026-09-10 要求，見檔頭）。核心邏輯獨立於 `main()` 之外以便測試。

    `df_missing` 為空（458 檔已全數齊備）時：印訊息、直接回傳 0，**不呼叫
    `write_missing_rows()`、不呼叫 `conn.rollback()`**——比照
    `ug_g3_sb2_backfill_entity_mapping.py::execute_write_and_verify` 已確立
    的「無事可做不是失敗」原則。

    Returns: 實際 INSERT 影響列數（`df_missing` 為空時為 0）。
    """
    if df_missing is None or df_missing.empty:
        print("無待插入列（458 檔已全數齊備），不執行寫入。")
        return 0

    stock_ids = sorted(df_candidate["stock_id"].unique())
    with conn.cursor() as cur:
        total_before = _fetch_stock_prices_total_count(cur)
        before_counts = _fetch_per_stock_counts(cur, "stock_prices", stock_ids)

    n_inserted = write_missing_rows(conn, df_missing)
    if n_inserted != len(df_missing):
        print(
            f"ERROR：INSERT 實際影響列數 {n_inserted} != 預期 {len(df_missing)}"
            f"（差額 {len(df_missing) - n_inserted}）。rollback，不 commit。"
        )
        conn.rollback()
        raise RuntimeError(f"INSERT 影響列數不符：{n_inserted} != {len(df_missing)}")
    print(f"（核對 1/4）INSERT 影響列數核對通過：{n_inserted} == {len(df_missing)}")

    with conn.cursor() as cur:
        total_after = _fetch_stock_prices_total_count(cur)
    expected_total = total_before + n_inserted
    if total_after != expected_total:
        print(
            f"ERROR：stock_prices 總列數核對不符：{total_after} != {expected_total}"
            f"（寫入前 {total_before} + 插入 {n_inserted}）。rollback，不 commit。"
        )
        conn.rollback()
        raise RuntimeError(f"stock_prices 總列數不符：{total_after} != {expected_total}")
    print(f"（核對 2/4）總列數核對通過：{total_after} == {expected_total}（寫入前 + 插入）。")

    # ⚠⚠ **2026-09-10 複核修正**：核對 3 原本比對「插入後逐股列數 ==
    # candidate_prices 逐股列數」——這個假設對「stock_prices 既有列數 ==
    # candidate_prices 列數」的股票才成立。2330／2382 因 §3.2 登記的
    # 2026-09-01／09-02 批次覆蓋缺口，`stock_prices` 987 列而
    # `candidate_prices` 只有 985 列，這條核對在真實庫上必然 FAIL（審查方
    # 拋棄式庫全量 dry-run 實測抓到）。正確核對是「插入後列數 == 插入前
    # 列數 + 該檔待插入列數」——不管插入前 `stock_prices` 與
    # `candidate_prices` 是否本就有差異，本腳本只保證「補進了該補的」，
    # 不宣稱「插入後兩表列數相等」。
    missing_counts = df_missing.groupby("stock_id").size()
    with conn.cursor() as cur:
        after_counts = _fetch_per_stock_counts(cur, "stock_prices", stock_ids)
    mismatched = []
    for sid in stock_ids:
        before_n = int(before_counts.get(sid, 0))
        missing_n = int(missing_counts.get(sid, 0))
        expect = before_n + missing_n
        got = int(after_counts.get(sid, 0))
        if expect != got:
            mismatched.append((sid, before_n, missing_n, expect, got))
    if mismatched:
        print(
            f"ERROR：{len(mismatched)} 檔逐股列數不符「插入前 + 待插入」："
            f"{mismatched[:10]}{'...' if len(mismatched) > 10 else ''}"
            f"（格式：stock_id, 插入前, 待插入, 預期, 實得）。rollback，不 commit。"
        )
        conn.rollback()
        raise RuntimeError(f"逐股列數核對不符：{len(mismatched)} 檔")
    print(f"（核對 3/4）逐股列數核對通過：{len(stock_ids)} 檔皆等於「插入前 + 待插入」。")

    with conn.cursor() as cur:
        try:
            _spot_check_rows(cur, df_missing, _SPOT_CHECK_SAMPLE_SIZE)
        except RuntimeError as e:
            print(f"ERROR：{e}。rollback，不 commit。")
            conn.rollback()
            raise
    print("（核對 4/4）抽樣讀回核對通過。")

    conn.commit()
    print("COMMIT 完成。")
    return n_inserted


# ----------------------------------------------------------------------------
# CLI（唯讀預覽 / --write 實際寫入）——比照 ug_g3_sb2_backfill_entity_mapping.py
# ----------------------------------------------------------------------------

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


def _check_backup_or_exit(backup_path: str) -> None:
    p = Path(backup_path)
    if not p.exists():
        print(f"ERROR：--backup 指向的檔案不存在：{backup_path}")
        sys.exit(1)
    size = p.stat().st_size
    if size == 0:
        print(f"ERROR：--backup 指向的檔案為空（0 bytes）：{backup_path}")
        sys.exit(1)
    age_seconds = time.time() - p.stat().st_mtime
    if age_seconds > _MAX_BACKUP_AGE_SECONDS:
        print(
            f"ERROR：--backup 檔案 mtime 為 {age_seconds / 3600:.1f} 小時前，"
            f"超過 {_MAX_BACKUP_AGE_SECONDS / 3600:.0f} 小時上限，拒絕執行：{backup_path}"
        )
        sys.exit(1)
    print(f"備份檔檢查通過：{backup_path}（{size:,} bytes，{age_seconds / 60:.1f} 分鐘前）")


def main(write: bool, backup_path: str) -> None:
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

    if write:
        typed = input(f"即將對資料庫 '{current_db}' 執行 INSERT。請輸入資料庫名稱以確認：")
        if typed != current_db:
            print(f"ERROR：輸入 '{typed}' 與目標資料庫 '{current_db}' 不符，拒絕執行。")
            conn.close()
            sys.exit(1)

    df_candidate = pd.read_sql(
        "SELECT cp.stock_id, cp.trade_date, cp.open_price, cp.high_price, "
        "       cp.low_price, cp.close_price, cp.volume, cp.source "
        "FROM candidate_prices cp "
        "JOIN (SELECT DISTINCT stock_id FROM universe_snapshots WHERE included) u "
        "  ON u.stock_id = cp.stock_id;",
        conn,
    )
    print(f"候選池（458 檔全部列）：{len(df_candidate)} 列，"
          f"{df_candidate['stock_id'].nunique()} 檔")

    df_existing_keys = _fetch_stock_prices_keys(cur)
    print(f"stock_prices 現有：{len(df_existing_keys)} 列")

    df_missing = compute_missing_rows(df_candidate, df_existing_keys)

    print("\n" + summarize_preview(df_candidate, df_existing_keys, df_missing))

    if not write:
        print("\n【唯讀模式】僅唯讀連線，不執行 INSERT。加 --write --backup <path> 執行實際寫入。")
        conn.close()
        return

    try:
        execute_write_and_verify(conn, df_candidate, df_existing_keys, df_missing)
    except RuntimeError as e:
        print(f"ERROR：{e}")
        conn.close()
        sys.exit(1)

    cur.execute("SELECT count(*) FROM stock_prices;")
    print("=== 寫入後真實庫 stock_prices 總列數 ===", cur.fetchone())

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", default=None)
    args = parser.parse_args()
    main(write=args.write, backup_path=args.backup)
