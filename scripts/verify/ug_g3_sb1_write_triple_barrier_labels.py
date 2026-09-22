"""
UG-G3-SB1 Gate A §11 DoD 第 6 項——target_triple_barrier／label_reason 真實庫寫入。

連線參數全走環境變數（DB_HOST／DB_PORT／POSTGRES_DB／POSTGRES_USER／POSTGRES_PASSWORD），
不在本檔留下任何字面連線值（CHAL-008 教訓，見 doc/evidence/CHALLENGES.md）。

寫入前必須完成 RISK-013 三項協議：(1) binding confirmation（PO 授權）、
(2) pg_dump 備份、(3) 拋棄式容器實際還原驗證。本腳本本身不執行備份／還原，
那是獨立步驟，但 --write 模式會**檢查備份檔確實存在且夠新**才放行（見 --backup）。

用法：
    python scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py
        唯讀模式（預設）：僅唯讀連線，不執行 UPDATE，只印出統計預覽。

    python scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py --write --backup <path>
        實際寫入。必須同時提供 --backup 指向一份存在、非空、
        mtime 在執行前 24 小時內的 pg_dump 檔（RISK-013 第二項協議的機械化檢查，
        而非僅供人記得做）。執行時會先印出 CONN CHECK，要求以互動輸入
        （stdin）鍵入目標資料庫全名以二次確認，避免環境變數指錯庫時一路跑到底。

安全機制（均為 known-FAIL 驗證過的機械檢查，不是「應等於」式的人眼比對）：
    - 寫入列數 n_updated != 讀取列數 len(df) → rollback + 非零 exit
    - 【快篩】同一交易內、commit 前，讀回 DB 的 (stock_id, label_reason 或 '__LABELED__') →
      COUNT(*) 分布，與記憶體 result 的同款分布逐格比對；任一格不同 → rollback + 非零 exit。
      這只能偵測「reason 或列數層級」的錯誤，**偵測不到 target_triple_barrier 本身寫錯
      （例如 +1/-1 對調）或日期錯位（分布相同、鍵配對錯誤）**——這兩種情形分布比對
      恆為 PASS，見下一項
    - 【定案】同一交易內、commit 前，逐列讀回 (stock_id, trade_date) → (target_triple_barrier,
      label_reason)，與記憶體 result 逐列轉換後的同款 dict 做精確比對；任一列不符
      → 印出前 10 筆差異（key／expected／actual）、rollback、非零 exit。這是唯一
      同時涵蓋列數、reason、target 值、日期鍵配對正確性的檢查，快篩通過不代表這關會過
    三項檢查都在 commit 之前完成，任一失敗即整個交易 rollback，daily_ml_features
    維持寫入前狀態不變。

兩欄皆須 pd.isna() → None 轉換（label_reason 在 pandas 3.0.5 下 dtype 為 str，
正常產生標籤時缺值為 float NaN，非 None——直接寫入會被 psycopg2 轉接為文字 'NaN'，
觸發 chk_label_reason_consistency CHECK 拒絕。見 UG_G3_SB1_disposable_write_validation.json）。

已知限制：
    - pd.read_sql 直接吃 psycopg2 連線會印 pandas UserWarning（pandas 僅正式支援
      SQLAlchemy／sqlite3 連線）；目前可正常運作，若未來 pandas 版本改為拒絕，
      本腳本需要改用 SQLAlchemy engine，屬已知風險而非本次處理範圍。
    - 本檔以 Path(__file__).resolve().parents[2] 推算 repo 根目錄以插入
      sys.path，**須從 repo 內原位執行**（scripts/verify/ 下），複製到其他
      目錄執行會 IndexError；此為刻意的路徑假設，不是缺陷。
"""
import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2

from src.ml.triple_barrier import generate_triple_barrier_labels

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
_LABELED_KEY = "__LABELED__"  # 內部字典鍵，代表「正常產生標籤，label_reason 為 NULL」，不寫入 DB
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


def _to_db_value(v):
    """target_triple_barrier／label_reason 共用的 NaN→None 轉換。"""
    return None if pd.isna(v) else v


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


def _expected_distribution(result: pd.DataFrame) -> Counter:
    counts = Counter()
    for _, row in result.iterrows():
        reason_key = _LABELED_KEY if pd.isna(row["label_reason"]) else row["label_reason"]
        counts[(row["stock_id"], reason_key)] += 1
    return counts


def _actual_distribution(cur, stock_ids) -> Counter:
    cur.execute(
        "SELECT stock_id, COALESCE(label_reason, %s) AS reason_key, COUNT(*) "
        "FROM daily_ml_features WHERE stock_id = ANY(%s) GROUP BY 1, 2",
        (_LABELED_KEY, list(stock_ids)),
    )
    return Counter({(sid, reason): cnt for sid, reason, cnt in cur.fetchall()})


def _expected_rows(result: pd.DataFrame) -> dict:
    """逐列 (stock_id, trade_date) -> (target_triple_barrier, label_reason)，
    與實際寫入 DB 前使用的同一套 NaN→None／int() 轉換，確保比較的是「打算
    寫入什麼」而非重新推導一次可能不一致的邏輯。"""
    expected = {}
    for _, row in result.iterrows():
        tb_val = _to_db_value(row["target_triple_barrier"])
        tb_val = None if tb_val is None else int(tb_val)
        reason_val = _to_db_value(row["label_reason"])
        expected[(row["stock_id"], row["trade_date"])] = (tb_val, reason_val)
    return expected


def _actual_rows(cur, stock_ids) -> dict:
    cur.execute(
        "SELECT stock_id, trade_date, target_triple_barrier, label_reason "
        "FROM daily_ml_features WHERE stock_id = ANY(%s)",
        (list(stock_ids),),
    )
    return {(sid, td): (tb, reason) for sid, td, tb, reason in cur.fetchall()}


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
        typed = input(f"即將對資料庫 '{current_db}' 執行 UPDATE。請輸入資料庫名稱以確認：")
        if typed != current_db:
            print(f"ERROR：輸入 '{typed}' 與目標資料庫 '{current_db}' 不符，拒絕執行。")
            conn.close()
            sys.exit(1)

    df = pd.read_sql(
        "SELECT stock_id, trade_date, open_price, high_price, low_price "
        "FROM stock_prices ORDER BY stock_id, trade_date",
        conn,
    )
    print(f"讀取 stock_prices：{len(df)} 列")

    result = generate_triple_barrier_labels(df)

    summary = result.groupby("stock_id")["label_reason"].value_counts(dropna=False)
    print("=== 逐檔 label_reason 分布（寫入前預覽）===")
    print(summary)

    if not write:
        print("\n【唯讀模式】僅唯讀連線，不執行 UPDATE。加 --write --backup <path> 執行實際寫入。")
        conn.close()
        return

    n_updated = 0
    for _, row in result.iterrows():
        tb_val = _to_db_value(row["target_triple_barrier"])
        tb_val = None if tb_val is None else int(tb_val)
        reason_val = _to_db_value(row["label_reason"])
        cur.execute(
            "UPDATE daily_ml_features SET target_triple_barrier = %s, label_reason = %s "
            "WHERE stock_id = %s AND trade_date = %s",
            (tb_val, reason_val, row["stock_id"], row["trade_date"]),
        )
        n_updated += cur.rowcount

    if n_updated != len(df):
        print(
            f"ERROR：UPDATE 實際影響列數 {n_updated} != 讀取列數 {len(df)}"
            f"（差額 {len(df) - n_updated}）。rollback，不 commit。"
        )
        conn.rollback()
        conn.close()
        sys.exit(1)
    print(f"UPDATE 影響列數核對通過：{n_updated} == {len(df)}")

    expected_dist = _expected_distribution(result)
    actual_dist = _actual_distribution(cur, df["stock_id"].unique())
    if expected_dist != actual_dist:
        only_expected = {k: v for k, v in expected_dist.items() if actual_dist.get(k) != v}
        only_actual = {k: v for k, v in actual_dist.items() if expected_dist.get(k) != v}
        print("ERROR：commit 前讀回分布快篩與記憶體預期不符。rollback，不 commit。")
        print("  expected 側差異：", only_expected)
        print("  actual   側差異：", only_actual)
        conn.rollback()
        conn.close()
        sys.exit(1)
    print("讀回分布快篩通過：與記憶體預期逐格相符。")

    expected_rows = _expected_rows(result)
    actual_rows = _actual_rows(cur, df["stock_id"].unique())
    if expected_rows != actual_rows:
        mismatched_keys = [
            k for k in set(expected_rows) | set(actual_rows)
            if expected_rows.get(k) != actual_rows.get(k)
        ]
        print(
            f"ERROR：commit 前逐列讀回與記憶體預期不符（{len(mismatched_keys)} 筆），"
            f"rollback，不 commit。前 10 筆差異："
        )
        for k in mismatched_keys[:10]:
            print(f"  {k}: expected={expected_rows.get(k)}  actual={actual_rows.get(k)}")
        conn.rollback()
        conn.close()
        sys.exit(1)
    print(f"逐列讀回核對通過：{len(expected_rows)} 列與記憶體預期完全相符。")

    conn.commit()
    print("COMMIT 完成。")

    cur.execute(
        "SELECT stock_id, target_triple_barrier IS NOT NULL AS labeled, "
        "COUNT(*) FROM daily_ml_features GROUP BY 1, 2 ORDER BY 1, 2"
    )
    print("=== 寫入後真實庫逐檔統計 ===")
    for row in cur.fetchall():
        print(row)

    cur.execute(
        "SELECT trade_date, target_triple_barrier, label_reason FROM daily_ml_features "
        "WHERE stock_id = 'NVDA' AND trade_date IN ('2026-06-03', '2026-06-04') ORDER BY trade_date"
    )
    print("=== NVDA 2026-06-03／06-04 點查 ===")
    for row in cur.fetchall():
        print(row)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", default=None)
    args = parser.parse_args()
    main(write=args.write, backup_path=args.backup)
