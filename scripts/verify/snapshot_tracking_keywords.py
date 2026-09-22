# -*- coding: utf-8 -*-
"""UG-G2-SB5：追蹤關鍵字清單快照工具（唯讀）。

**存在理由**：A6（關鍵字覆蓋率量測）需要知道「量測當時 `is_active = TRUE` 的關鍵字
是哪些、有幾筆」。PO 指定的作法是——**清單先快照進證據檔，驗證腳本不連 DB**。

為什麼要拆成兩支腳本（而不是讓驗證腳本直接查 DB）：

1. `dcard_availability_check.py` 要對外發網路請求。一支同時「連內部資料庫」又
   「打外部 API」的腳本，出事時難以界定影響範圍。
2. A6 的證據必須包含**量測當下的關鍵字清單全文**。若驗證腳本自己查 DB，
   清單就成了執行期的隱含輸入——重跑時 DB 已變，證據無法重現。
   快照成檔案之後，同一個檔案配同一份 API 回應，A6 的結果可完全重現。
3. 容器的 `network_mode: service:db` 使 `localhost:5432` 直達真實開發資料庫
   （`CLAUDE.md` §13.4）。把 DB 存取集中在這一支、且**只有 SELECT**，
   是最小化接觸面的作法。

**本腳本只執行 SELECT，不做任何寫入**，因此不呼叫
`database/db_target_guard.py`（該守衛是為寫入／migration 目標設計的）。
改為**無條件印出 `current_database()`、host、port 與 server 版本**，
讓證據自己說明「這份快照是從哪個資料庫取得的」。

用法：
    python scripts/verify/snapshot_tracking_keywords.py \
        --out doc/upgrade/gates/evidence/G2_SB5_keywords_snapshot.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

QUERY = (
    "SELECT keyword, category, is_active, updated_at "
    "FROM tracking_keywords WHERE is_active = TRUE ORDER BY keyword;"
)


def build_db_config() -> dict:
    """與 `src/loaders/db_writer.py:38-56` 相同的環境變數契約。

    刻意不 import DBWriter：那個類別在建構時就準備好寫入路徑，
    而本腳本的整個賣點是「只讀」。重複這十行，換取「這支腳本不可能寫入」的可讀性。
    """
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("缺少必要資料庫環境變數：" + ", ".join(missing))
    try:
        port = int(os.getenv("DB_PORT", "5432"))
    except ValueError as exc:
        raise RuntimeError("DB_PORT 必須是有效整數。") from exc
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": port,
        "database": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="UG-G2-SB5 追蹤關鍵字快照（唯讀）")
    parser.add_argument("--out", required=True, help="輸出的證據檔路徑（JSON）")
    args = parser.parse_args(argv)

    try:
        import psycopg2  # noqa: WPS433  (延後 import：無 DB 需求時不應強制依賴)
    except ImportError:
        print("[FAIL] psycopg2 不存在。本腳本必須在 dev container 內執行"
              "（CLAUDE.md §13.0：host 為降級環境）。", file=sys.stderr)
        return 2

    config = build_db_config()
    conn = psycopg2.connect(**config)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), version();")
            db_name, server_version = cur.fetchone()
            cur.execute(QUERY)
            rows = cur.fetchall()
    finally:
        conn.close()

    keywords = [
        {
            "keyword": r[0],
            "category": r[1],
            "is_active": bool(r[2]),
            "updated_at": r[3].isoformat() if r[3] is not None else None,
        }
        for r in rows
    ]
    snapshot = {
        "purpose": "UG-G2-SB5 A6 關鍵字覆蓋率量測的輸入快照",
        "taken_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "taken_at_local": _dt.datetime.now().astimezone().isoformat(),
        "source_of_truth": {
            "table": "tracking_keywords",
            "filter": "is_active = TRUE",
            "query": QUERY,
            "current_database": db_name,
            "host": config["host"],
            "port": config["port"],
            "server_version": server_version,
        },
        "keyword_count": len(keywords),
        "keywords": keywords,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("[OK] 快照完成")
    print("  資料庫       :", db_name)
    print("  host:port    : %s:%s" % (config["host"], config["port"]))
    print("  is_active 筆數:", len(keywords))
    print("  輸出         :", args.out)
    if not keywords:
        print("  [注意] 清單為空。這是一個合法但重要的觀察——"
              "A6 在空清單下的覆蓋率必然為 0，且該 0 不代表 Dcard 沒有相關文章。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
