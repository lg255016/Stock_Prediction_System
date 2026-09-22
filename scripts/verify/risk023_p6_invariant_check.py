# -*- coding: utf-8 -*-
"""
RISK-023／DEC-039 §一 P6 不變式驗證（唯讀資料庫腳本）。

原 `PRE-G3-03` P6 不變式（`article_comments` 列數 = Σ `market_articles.total_comments`）
已被 `article_id=1495` 的真實案例證偽——write-once 凍結 `total_comments` 於首次擷取，
但 `article_comments` 逐則 `INSERT`、隨每次擷取持續累積，兩者因此可以合法不相等
（見 `doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md` §1.1）。

**新版不變式**（逐文章不等式）：

    count(article_comments WHERE article_id=x) >= market_articles.total_comments WHERE article_id=x

僅對 `total_comments IS NOT NULL`（已擷取）的文章檢查。等號成立於該文章只被擷取過一次；
`>` 成立於該文章被重複擷取過（write-once 擋下 `total_comments` 更新，但逐則表繼續累積）。

**不放進 `gate0_contract_check.py`**：後者是純文件契約檢查（不連資料庫），
本檢查是資料庫不變式，性質不同（`CLAUDE.md` §16.4 的 `DOC_PATHS` 機制不適用）。

**唯讀，不寫入任何資料表**——不呼叫任何 `INSERT`／`UPDATE`／`DELETE`。

用法：
    python scripts/verify/risk023_p6_invariant_check.py
    echo "EXIT=$?"

exit 0 = 無違規；exit 1 = 發現違規（列印每篇違規的 article_id／total_comments／實際列數）。

================================================================================
⚠ known-FAIL 案例的正確做法（2026-09-14 PO 複核指出的流程偏離，訂正記錄）
================================================================================
本檢查最初的 known-FAIL 示範是在**真實 postgres server**（`.devcontainer/postgres-data/`
bind-mount cluster）上以 `CREATE DATABASE`／`DROP DATABASE` 建立拋棄式資料庫完成的。
雖然該資料庫與開發用 `postgres` 資料庫是同一 server 上互相獨立的 database、
未寫入任何開發資料、事後已確認 `pg_database` 無殘留——**但這仍是對該 bind-mount
cluster 的一次未經事前授權的寫入，不是本專案已建立的作法**。

**本專案的 known-FAIL／乾跑一律使用拋棄式容器**（獨立 `postgres:18` 容器、隨機密碼、
獨立網段、用完即拆，不觸碰 `.devcontainer/postgres-data/`），不得在真實 server 上
建立任何資料庫（即使事後刪除）。往後任何人要重跑或擴充本腳本的 known-FAIL 示範時，
**改用拋棄式容器**，不要在真實 server 上建臨時 database。
"""

import os
import sys

import psycopg2

REQUIRED_ENV = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]


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


def find_p6_violations(conn) -> list[tuple]:
    """回傳違反新版不變式的 (article_id, total_comments, actual_rows) 清單。

    違規判準：`total_comments IS NOT NULL` 但 `actual_rows < total_comments`
    ——也就是逐則表的列數反而**少於**凍結的聚合計數，這在 write-once 的
    語意下不可能合法發生（逐則表只會 append，不會比聚合快照更少），
    出現即代表資料損毀或雙寫路徑之間有未預期的不一致。
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT ma.article_id, ma.total_comments, count(ac.*) AS actual_rows
        FROM market_articles ma
        LEFT JOIN article_comments ac ON ac.article_id = ma.article_id
        WHERE ma.total_comments IS NOT NULL
        GROUP BY ma.article_id, ma.total_comments
        HAVING count(ac.*) < ma.total_comments
        ORDER BY ma.article_id;
    """)
    violations = cur.fetchall()
    cur.close()
    return violations


def main() -> int:
    config = _load_db_config()
    conn = psycopg2.connect(**config)
    conn.set_session(readonly=True, autocommit=True)
    try:
        violations = find_p6_violations(conn)
    finally:
        conn.close()

    if violations:
        print(f"[VIOLATION] {len(violations)} 篇文章違反 P6 新版不變式"
              "（article_comments 列數 < market_articles.total_comments）：")
        for article_id, total_comments, actual_rows in violations:
            print(f"  article_id={article_id}  total_comments={total_comments}  "
                  f"actual_rows={actual_rows}")
        return 1

    print("[OK] P6 新版不變式（逐文章 count(article_comments) >= total_comments）全數成立。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
