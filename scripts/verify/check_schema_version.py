# -*- coding: utf-8 -*-
"""回答一個在 2026-08-31 之前沒有任何東西能回答的問題：**這個資料庫在第幾版？**

RISK-017 緩解第 3 條（偵測）。

**為什麼需要它**：`UG-G2-SB1`／`SB3`／`SB4` 三個 SB 各自新增了 migration，
每一次都在拋棄式臨時 DB 裡驗證通過、結案、拆掉容器。
三次都做對了「驗了什麼、在哪裡驗的」的紀錄（`CLAUDE.md` §9 證據標籤），
但**沒有任何機制追蹤「哪個環境還沒收到這個變更」**——
前者記得再完整也推導不出後者。

結果是真實開發資料庫落後四個 migration 而無人察覺，直到 `UG-G2-SB5` 決策點 5
為了核對一個小問題順手查了真實庫才撞到（RISK-017）。

**前兩條緩解處理已知的這一次，這一條讓下一次能被發現。**

用法：

    # 檢查預設連線目標（讀 .env／環境變數）
    python scripts/verify/check_schema_version.py

    # 檢查指定目標
    DB_HOST=host.docker.internal DB_PORT=55437 POSTGRES_DB=some_tmpdb \\
        python scripts/verify/check_schema_version.py

退出碼：0 = 已是最新；1 = 落後；2 = 執行錯誤（無法連線、缺環境變數等）。

**本腳本唯讀**，只執行 `SELECT`，不呼叫 `db_target_guard`（無寫入）。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"
_FILENAME_RE = re.compile(r"^(\d+)_.*\.sql$")


def available_versions():
    """掃描 migrations 目錄，回傳 (version, filename) 依版本遞增。

    與 `apply_migrations.py` 用同一套命名慣例；此處刻意重複實作而非 import，
    因為本腳本的賣點是「不觸發任何寫入路徑」——
    import 一個以寫入為職責的模組，會把那條路徑帶進來。
    """
    out = []
    if not MIGRATIONS_DIR.is_dir():
        return out
    for entry in sorted(MIGRATIONS_DIR.iterdir()):
        m = _FILENAME_RE.match(entry.name)
        if m:
            out.append((int(m.group(1)), entry.name))
    return sorted(out)


def build_db_config() -> dict:
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [n for n in required if not os.getenv(n)]
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


def applied_version(cursor):
    """目前已套用的最高版本；`schema_version` 表不存在時為 0。

    「表不存在」與「表存在但為空」都回 0，但兩者在輸出中會被區分——
    前者代表 migration 機制從未在此資料庫執行過，後者代表執行過但沒套用任何版本。
    這個區分是本腳本存在的理由之一：RISK-017 的真實庫屬於前者。
    """
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'schema_version');"
    )
    if not cursor.fetchone()[0]:
        return 0, False
    cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version;")
    return cursor.fetchone()[0], True


def main(argv=None) -> int:
    try:
        import psycopg2
    except ImportError:
        print("[ERROR] psycopg2 不存在。本腳本須在 dev container 內執行"
              "（CLAUDE.md §13.0）。", file=sys.stderr)
        return 2

    try:
        config = build_db_config()
    except RuntimeError as exc:
        print("[ERROR] %s" % exc, file=sys.stderr)
        return 2

    available = available_versions()
    latest = available[-1][0] if available else 0

    try:
        conn = psycopg2.connect(**config)
    except Exception as exc:
        print("[ERROR] 無法連線 %s:%s/%s —— %s: %s"
              % (config["host"], config["port"], config["database"],
                 type(exc).__name__, exc), file=sys.stderr)
        return 2

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database();")
            dbname = cur.fetchone()[0]
            current, table_exists = applied_version(cur)
    finally:
        conn.close()

    behind = latest - current

    print("=" * 66)
    print("Schema 版本檢查（RISK-017 緩解第 3 條）")
    print("=" * 66)
    print("  目標資料庫        : %s" % dbname)
    print("  連線座標          : %s:%s" % (config["host"], config["port"]))
    print("  schema_version 表 : %s" % ("存在" if table_exists else "**不存在**"))
    print("  已套用版本        : v%d%s"
          % (current, "" if table_exists else "（migration 機制從未在此資料庫執行過）"))
    print("  可用最高版本      : v%d（%s）"
          % (latest, available[-1][1] if available else "無 migration 檔案"))
    print("-" * 66)
    if behind > 0:
        print("  結果              : **落後 %d 個版本**" % behind)
        print("  未套用            : %s"
              % ", ".join("v%d（%s）" % (v, n) for v, n in available if v > current))
        print("=" * 66)
        return 1
    if behind < 0:
        # 資料庫版本高於檔案：通常代表 migration 檔被刪除或 checkout 到舊 commit。
        # 這不是「落後」，但同樣需要有人看一眼，因此也回非 0。
        print("  結果              : **資料庫版本高於可用檔案（v%d > v%d）**"
              % (current, latest))
        print("  可能原因          : migration 檔案被刪除，或工作區為較舊的 commit")
        print("=" * 66)
        return 1
    print("  結果              : 已是最新（v%d）" % current)
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
