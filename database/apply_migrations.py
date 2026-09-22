"""
database/apply_migrations.py

增量 Schema 遷移執行器（UG-G1-SB4 階段二）。
規格來源：doc/upgrade/contracts/DB_MIGRATION_PLAN.md §5（Gate 0 已核准）。

核心邏輯：
1. 連線資料庫前，先呼叫 database.db_target_guard.assert_safe_migration_target()
   （RISK-013 根本解——本檔與 database/db_target_guard.py 的唯一耦合點，
   不可省略、不可延後）。
2. 檢查 schema_version 表是否存在；不存在 → 目前版本為 0，存在 → SELECT MAX(version)。
3. 掃描 database/migrations/ 目錄，依檔名編號排序。
4. 篩選出 version > current_version 的腳本。
5. 依序對每個腳本：BEGIN → 執行 SQL 內容 → COMMIT；任一失敗 → ROLLBACK，
   停止執行，回報錯誤，回傳非 0 結束碼。
6. 全部成功後輸出執行結果摘要，回傳 0。

設計原則（DB_MIGRATION_PLAN.md §5.2）：
- 冪等性：每個遷移使用 IF NOT EXISTS 與 ON CONFLICT DO NOTHING，重複執行不出錯。
- 原子性：每個遷移在獨立事務中執行，失敗時自動 ROLLBACK。
- 順序性：嚴格按檔名編號順序執行，不可跳號。
- 安全性：不執行已套用的版本（版本號已存在於 schema_version）。
"""

import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_target_guard import assert_safe_migration_target
from src.loaders.db_writer import DBWriter

MIGRATIONS_DIR = Path(__file__).resolve().with_name("migrations")
_MIGRATION_FILENAME_PATTERN = re.compile(r"^(\d+)_.*\.sql$")


def _discover_migrations() -> list:
    """
    掃描 MIGRATIONS_DIR，回傳依 version 遞增排序的 (version, path) 清單。
    檔名不符合 `<數字>_<描述>.sql` 樣式者略過，不視為錯誤（允許目錄下有 README 等）。
    """
    found = []
    for entry in MIGRATIONS_DIR.iterdir():
        if not entry.is_file():
            continue
        m = _MIGRATION_FILENAME_PATTERN.match(entry.name)
        if not m:
            continue
        found.append((int(m.group(1)), entry))
    found.sort(key=lambda pair: pair[0])
    return found


def _get_current_version(cursor) -> int:
    """回傳目前已套用的最高版本號；schema_version 表不存在時視為版本 0。"""
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_version');"
    )
    (table_exists,) = cursor.fetchone()
    if not table_exists:
        return 0

    cursor.execute("SELECT MAX(version) FROM schema_version;")
    (max_version,) = cursor.fetchone()
    return max_version or 0


def _apply_one_migration(connection, version: int, path: Path) -> None:
    """
    在獨立事務中執行單一遷移檔案；失敗時 ROLLBACK 並重新拋出例外。

    每個已核准的遷移檔案（見 DB_MIGRATION_PLAN.md §4）內容本身即包含自我登記的
    `INSERT INTO schema_version ... ON CONFLICT (version) DO NOTHING`，不含 checksum。
    此函式執行完遷移 SQL 後改用 UPDATE 補上 checksum——若改用 INSERT 會被前述
    自我登記的 ON CONFLICT 擋下而永遠寫不進去；UPDATE 則不論該列是否已由遷移檔案
    自行建立，皆能正確補上。
    """
    sql_text = path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql_text)
            cursor.execute(
                "UPDATE schema_version SET checksum = %s WHERE version = %s;",
                (checksum, version),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def apply_migrations() -> int:
    """
    執行全部待套用遷移。回傳結束碼（0 成功，非 0 失敗）。
    不在此函式內呼叫 sys.exit，由呼叫端（__main__ 區塊）決定進程結束碼，
    以利測試以函式呼叫方式驗證回傳值而不終止測試進程。
    """
    db_config = DBWriter().db_config
    assert_safe_migration_target(db_config)  # RISK-013 根本解：連線前必經檢查

    migrations = _discover_migrations()
    if not migrations:
        print(f"[apply_migrations] {MIGRATIONS_DIR} 內無符合命名樣式的遷移檔案。")
        return 0

    print("[apply_migrations] 正在連線到 PostgreSQL...")
    connection = psycopg2.connect(**db_config)
    try:
        with connection.cursor() as cursor:
            current_version = _get_current_version(cursor)
        print(f"[apply_migrations] 目前已套用版本：v{current_version}")

        pending = [(v, p) for v, p in migrations if v > current_version]
        if not pending:
            print("[apply_migrations] 無待執行遷移，已是最新版本。")
            return 0

        for version, path in pending:
            print(f"[apply_migrations] 正在套用 v{version}（{path.name}）...")
            try:
                _apply_one_migration(connection, version, path)
            except Exception as exc:
                print(
                    f"[apply_migrations] v{version}（{path.name}）執行失敗，已 ROLLBACK，"
                    f"版本未推進：{exc}"
                )
                return 1
            print(f"[apply_migrations] v{version} 已套用並 COMMIT。")

        print(f"[apply_migrations] 完成，已套用至 v{pending[-1][0]}。")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(apply_migrations())
