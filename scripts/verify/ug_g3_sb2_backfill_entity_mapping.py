# -*- coding: utf-8 -*-
"""
UG-G3-SB2 §5/§5.1 `entity_mapping` 路由補齊（455 檔，457 筆）。

比照 `scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py` 既有模式：
連線參數全走環境變數，不在本檔留下任何字面連線值（CHAL-008 教訓）；寫入前
必須完成 RISK-013 三項協議（binding confirmation／pg_dump 備份／拋棄式容器
還原驗證）；`--write` 模式檢查備份檔存在且夠新，並要求 stdin 二次確認庫名。

**四項設計裁決（PO 2026-09-09，`UG_G3_SB2_GATE_A_PROPOSAL.md` §5.1）**：
1. `market`：取該 `stock_id` 於 `candidate_prices` 中 `MAX(trade_date)` 那一列
   的 `source`，經封閉映射（`MARKET_BY_SOURCE`）轉換；未知來源一律 raise，
   不得預設——3 檔股票（6446/6472/6589）市場別隨時間改變過（上櫃轉上市），
   取第一列或任一列會拿到過期市場別。
2. 名稱清理（`clean_keyword`）：只移除任意位置的 `*`（資料品質標記，位置不
   固定，`矽力*-KY`／`材料*-KY` 出現在中段）；`-KY`（開曼註冊）／`-DR`
   （存託憑證）是公司簡稱本體，原樣保留。
3. `description`：固定前綴 `[auto:UG-G3-SB2]`，區分「現名」與「改名前舊名」
   （`DESC_CURRENT` / `DESC_OLD_TMPL`），供日後 `LIKE '[auto:UG-G3-SB2]%'`
   精確回溯或整批撤銷。
4. 既有已路由股票（`entity_mapping` 現有列涵蓋的 `stock_id`）以 **`stock_id`**
   明確排除（`exclude_already_routed_stock_ids`），不靠 keyword 層級隱式去重；
   寫入用純 `INSERT`，**禁用 `ON CONFLICT`**——任何意外撞名大聲失敗並
   rollback，不被 `DO NOTHING` 靜默吞掉（`CLAUDE.md` §7.1）。

**寫入前機械 keyword 撞名檢查**（`check_keyword_collisions`，PO 2026-09-09
複審追加）：(a) 新增列彼此撞名、(b) 對既有 `entity_mapping` 撞名、(c) 對
458 檔宇宙以外的 `candidate_prices` 股票撞名，任一非零即 raise，不寫入。

⚠ 本腳本尚未對真實庫執行 `--write`——首次執行需 PO binding confirmation
（RISK-013 三項協議），比照 `UG-G3-SB1` 流程。
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
_MAX_BACKUP_AGE_SECONDS = 24 * 3600

MARKET_BY_SOURCE = {
    "twse_mi_index": "TWSE",
    "tpex_daily_quotes": "TPEX",
}

DESC_PREFIX = "[auto:UG-G3-SB2]"
DESC_CURRENT = f"{DESC_PREFIX} 交易所簡稱（candidate_prices.security_name）"
DESC_OLD_TMPL = DESC_PREFIX + " 交易所舊簡稱，現名：{current_name}"


def clean_keyword(name: str) -> str:
    """移除任意位置的 `*`（資料品質標記）；`-KY`／`-DR` 等公司簡稱本體不動。"""
    return name.replace("*", "")


def derive_market(source: str) -> str:
    """封閉映射：僅認得 `MARKET_BY_SOURCE` 列出的來源，其餘一律 raise，不得預設
    （PO 2026-09-09 裁決 1）。"""
    try:
        return MARKET_BY_SOURCE[source]
    except KeyError:
        raise ValueError(
            f"未知的 candidate_prices.source：{source!r}，"
            f"market 映射表為封閉集合 {sorted(MARKET_BY_SOURCE)}，不得預設。"
        )


def compute_routing_rows(df_candidate: pd.DataFrame) -> pd.DataFrame:
    """
    df_candidate: 需含 stock_id, security_name, source, trade_date，**呼叫端
    先以 `exclude_already_routed_stock_ids()` 排除既有已路由股票**。

    每個 stock_id：market 取 trade_date 最大那一列的 source 映射；清理後
    security_name 去重，每個相異結果各一列；trade_date 最大那列對應的清理後
    名稱視為「現名」（DESC_CURRENT），其餘為「改名前舊名」（DESC_OLD_TMPL）。

    Returns: DataFrame[keyword, stock_id, market, description]，依
    stock_id, keyword 排序。
    """
    cols = ["keyword", "stock_id", "market", "description"]
    if df_candidate is None or df_candidate.empty:
        return pd.DataFrame(columns=cols)

    df = df_candidate.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["keyword"] = df["security_name"].map(clean_keyword)

    rows = []
    for stock_id, grp in df.groupby("stock_id"):
        latest = grp.loc[grp["trade_date"].idxmax()]
        market = derive_market(latest["source"])
        current_keyword = latest["keyword"]

        for keyword in sorted(grp["keyword"].unique()):
            if keyword == current_keyword:
                description = DESC_CURRENT
            else:
                description = DESC_OLD_TMPL.format(current_name=current_keyword)
            rows.append({
                "keyword": keyword, "stock_id": stock_id,
                "market": market, "description": description,
            })

    return pd.DataFrame(rows, columns=cols).sort_values(["stock_id", "keyword"]).reset_index(drop=True)


def exclude_already_routed_stock_ids(
    df_candidate: pd.DataFrame, df_existing_entity_mapping: pd.DataFrame
) -> pd.DataFrame:
    """以 `stock_id` 明確排除既有已路由股票，不靠 keyword 層級隱式去重
    （PO 2026-09-09 裁決 4）。"""
    if df_existing_entity_mapping is None or df_existing_entity_mapping.empty:
        return df_candidate.copy()
    routed_ids = set(df_existing_entity_mapping["stock_id"].unique())
    return df_candidate.loc[~df_candidate["stock_id"].isin(routed_ids)].copy()


def check_keyword_collisions(
    df_new_rows: pd.DataFrame,
    df_existing_entity_mapping: pd.DataFrame,
    df_non_universe_candidate: pd.DataFrame,
) -> None:
    """寫入前機械檢查（PO 2026-09-09 複審追加）。三種撞名任一非零即
    `raise ValueError`，不寫入：
    (a) df_new_rows 內部同一 keyword 對到不同 stock_id
    (b) df_new_rows 與既有 entity_mapping 同一 keyword 對到不同 stock_id
    (c) df_new_rows 與宇宙外 candidate_prices 股票同一 keyword 對到不同 stock_id
    （同一 keyword 對到同一 stock_id 不算撞名——那是自己對自己。）
    """
    dup = df_new_rows.groupby("keyword")["stock_id"].nunique()
    cross_new = dup[dup > 1]
    if not cross_new.empty:
        raise ValueError(
            f"新增路由列彼此撞名（同一 keyword 對到不同 stock_id）：{cross_new.index.tolist()}"
        )

    if df_existing_entity_mapping is not None and not df_existing_entity_mapping.empty:
        merged = df_new_rows.merge(
            df_existing_entity_mapping[["keyword", "stock_id"]],
            on="keyword", how="inner", suffixes=("", "_existing"),
        )
        conflict = merged.loc[merged["stock_id"] != merged["stock_id_existing"]]
        if not conflict.empty:
            raise ValueError(f"新增路由列與既有 entity_mapping 撞名：{conflict['keyword'].tolist()}")

    if df_non_universe_candidate is not None and not df_non_universe_candidate.empty:
        non_uni = df_non_universe_candidate.copy()
        non_uni["keyword"] = non_uni["security_name"].map(clean_keyword)
        non_uni_keys = non_uni[["keyword", "stock_id"]].drop_duplicates()
        merged = df_new_rows.merge(non_uni_keys, on="keyword", how="inner", suffixes=("", "_other"))
        conflict = merged.loc[merged["stock_id"] != merged["stock_id_other"]]
        if not conflict.empty:
            raise ValueError(f"新增路由列與宇宙外股票撞名：{conflict['keyword'].tolist()}")


def write_routing_rows(conn, df_rows: pd.DataFrame) -> int:
    """
    以純 `INSERT`（**不用 `ON CONFLICT`**）寫入 df_rows 至 entity_mapping。
    **不 commit**——呼叫端於讀回核對通過後才 commit（比照 SB1 既有模式：
    核對在 commit 之前）。任何例外 `conn.rollback()` 後重新拋出，不吞掉
    （`CLAUDE.md` §7.1）。

    Returns: int，實際 INSERT 影響列數（cur.rowcount 加總）。
    """
    if df_rows is None or df_rows.empty:
        return 0
    try:
        n = 0
        with conn.cursor() as cur:
            for row in df_rows[["keyword", "stock_id", "market", "description"]].itertuples(
                index=False, name=None
            ):
                keyword, stock_id, market, description = row
                cur.execute(
                    "INSERT INTO entity_mapping (keyword, stock_id, market, description) "
                    "VALUES (%s, %s, %s, %s)",
                    (keyword, stock_id, market, description),
                )
                n += cur.rowcount
        return n
    except Exception:
        conn.rollback()
        raise


def _fetch_entity_mapping_by_keywords(cur, keywords) -> pd.DataFrame:
    cols = ["keyword", "stock_id", "market", "description"]
    keywords = list(keywords)
    if not keywords:
        return pd.DataFrame(columns=cols)
    cur.execute(
        "SELECT keyword, stock_id, market, description FROM entity_mapping WHERE keyword = ANY(%s)",
        (keywords,),
    )
    return pd.DataFrame(cur.fetchall(), columns=cols)


def _fetch_entity_mapping_total_count(cur) -> int:
    cur.execute("SELECT count(*) FROM entity_mapping;")
    return cur.fetchone()[0]


def _normalize_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    """比較前正規化：統一轉字串型別，避免 pd.read_sql／手動建構／dict 三種來源
    dtype 不同導致 `.equals()` 誤判不相符（PO 2026-09-09 複審發現的根因：
    0 筆新增時兩個空 DataFrame 因 dtype 不同被判不相等，把「無事可做」回報
    成「失敗」）。"""
    cols = ["keyword", "stock_id", "market", "description"]
    return df[cols].astype(str).sort_values("keyword").reset_index(drop=True)


def execute_write_and_verify(conn, df_existing: pd.DataFrame, df_new_rows: pd.DataFrame) -> int:
    """
    寫入 `df_new_rows` 至 `entity_mapping` 並於 commit 前完成核對，核心邏輯
    獨立於 `main()` 之外以便測試（PO 2026-09-09 複審發現兩個真實缺陷後追加，
    `UG_G3_SB2_GATE_A_PROPOSAL.md` §5.1）。

    `df_new_rows` 為空（所有宇宙股票已路由）時：印訊息、直接回傳 0，**不呼叫
    `write_routing_rows()`、不呼叫 `conn.rollback()`**——修正前的版本用
    `.equals()` 比較兩個空 DataFrame，因 dtype 不同誤判不相符，把「無事可做」
    回報成「失敗」（`CLAUDE.md` §7.1 反方向的同一種錯：訊號與事實不符）。

    核對四件事，任一不符即 `conn.rollback()` 後 `raise RuntimeError`，不 commit：
    1. INSERT 影響列數 == len(df_new_rows)
    2. 既有列（依 keyword 讀回）與 df_existing 逐列相同
    3. 新增列（依 keyword 讀回）與 df_new_rows 逐列相同
    4. entity_mapping 總列數 == len(df_existing) + len(df_new_rows)——前兩項
       核對看不到「多了一列不在既有也不在新增集合」的情形，補這一道
       （PO 2026-09-09 複審追加，缺陷 2）

    Returns: 實際 INSERT 影響列數（df_new_rows 為空時為 0）。
    """
    if df_new_rows is None or df_new_rows.empty:
        print("無待新增路由列（所有宇宙股票已路由），不執行寫入。")
        return 0

    n_inserted = write_routing_rows(conn, df_new_rows)
    if n_inserted != len(df_new_rows):
        print(
            f"ERROR：INSERT 實際影響列數 {n_inserted} != 預期 {len(df_new_rows)}"
            f"（差額 {len(df_new_rows) - n_inserted}）。rollback，不 commit。"
        )
        conn.rollback()
        raise RuntimeError(f"INSERT 影響列數不符：{n_inserted} != {len(df_new_rows)}")
    print(f"INSERT 影響列數核對通過：{n_inserted} == {len(df_new_rows)}")

    with conn.cursor() as cur:
        existing_after = _fetch_entity_mapping_by_keywords(cur, df_existing["keyword"])
        new_after = _fetch_entity_mapping_by_keywords(cur, df_new_rows["keyword"])
        total_after = _fetch_entity_mapping_total_count(cur)

    if not _normalize_for_compare(df_existing).equals(_normalize_for_compare(existing_after)):
        print("ERROR：commit 前讀回既有列，與寫入前不完全相同（不應被本次寫入動到）。rollback，不 commit。")
        conn.rollback()
        raise RuntimeError("既有列讀回與寫入前不完全相同。")
    print(f"既有 {len(df_existing)} 列核對通過：未被本次寫入動到。")

    if not _normalize_for_compare(df_new_rows).equals(_normalize_for_compare(new_after)):
        print("ERROR：commit 前逐列讀回新增列與記憶體預期不符。rollback，不 commit。")
        conn.rollback()
        raise RuntimeError("新增列讀回與記憶體預期不符。")
    print(f"新增 {len(df_new_rows)} 列逐列讀回核對通過：與記憶體預期完全相符。")

    expected_total = len(df_existing) + len(df_new_rows)
    if total_after != expected_total:
        print(
            f"ERROR：entity_mapping 總列數核對不符：{total_after} != {expected_total}"
            f"（既有 {len(df_existing)} + 新增 {len(df_new_rows)}）。前兩項核對看不到"
            f"「多出不在任何集合內的列」，靠這道抓。rollback，不 commit。"
        )
        conn.rollback()
        raise RuntimeError(f"entity_mapping 總列數不符：{total_after} != {expected_total}")
    print(f"總列數核對通過：{total_after} == {expected_total}（既有 + 新增）。")

    conn.commit()
    print("COMMIT 完成。")
    return n_inserted


# ----------------------------------------------------------------------------
# CLI（唯讀預覽 / --write 實際寫入）——比照 ug_g3_sb1_write_triple_barrier_labels.py
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

    df_existing = pd.read_sql("SELECT keyword, stock_id, market, description FROM entity_mapping", conn)
    print(f"既有 entity_mapping：{len(df_existing)} 列")

    df_universe = pd.read_sql(
        "SELECT DISTINCT stock_id FROM universe_snapshots WHERE included", conn
    )
    universe_ids = tuple(df_universe["stock_id"].tolist())

    df_candidate_universe = pd.read_sql(
        "SELECT stock_id, security_name, source, trade_date FROM candidate_prices "
        "WHERE stock_id = ANY(%(ids)s) AND security_name IS NOT NULL",
        conn, params={"ids": list(universe_ids)},
    )
    print(f"宇宙股票 candidate_prices 有名稱列：{len(df_candidate_universe)} 列（{df_candidate_universe['stock_id'].nunique()} 檔）")

    df_candidate_new = exclude_already_routed_stock_ids(df_candidate_universe, df_existing)
    df_new_rows = compute_routing_rows(df_candidate_new)
    print(f"待新增路由列：{len(df_new_rows)} 筆（{df_new_rows['stock_id'].nunique()} 檔）")

    df_non_universe = pd.read_sql(
        "SELECT stock_id, security_name FROM candidate_prices "
        "WHERE stock_id != ALL(%(ids)s) AND security_name IS NOT NULL",
        conn, params={"ids": list(universe_ids)},
    )
    check_keyword_collisions(df_new_rows, df_existing, df_non_universe)
    print("撞名檢查通過（新增列彼此、對既有、對宇宙外，三者皆無撞名）。")

    if not write:
        print("\n【唯讀模式】僅唯讀連線，不執行 INSERT。加 --write --backup <path> 執行實際寫入。")
        print(df_new_rows.to_string(index=False))
        conn.close()
        return

    try:
        execute_write_and_verify(conn, df_existing, df_new_rows)
    except RuntimeError as e:
        print(f"ERROR：{e}")
        conn.close()
        sys.exit(1)

    cur.execute("SELECT count(*) FROM entity_mapping;")
    print("=== 寫入後真實庫 entity_mapping 總列數 ===", cur.fetchone())

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", default=None)
    args = parser.parse_args()
    main(write=args.write, backup_path=args.backup)
