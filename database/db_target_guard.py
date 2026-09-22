"""
database/db_target_guard.py

RISK-013 根本解（UG-G1-SB4 階段一）：任何會對資料庫執行寫入（DDL／INSERT／UPDATE／
DELETE）的腳本，在建立連線之前，必須呼叫 assert_safe_migration_target(db_config)。

偵測到連線目標「疑似真實開發 DB」且未提供明確覆寫確認時，raise SystemExit（非 0
結束碼），不執行任何連線動作。

設計依據：doc/upgrade/gates/closed/SB4_GATE_A_PROPOSAL.md §3（PO 已核准）。
"""

import os
import re

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432

_TEMP_DB_NAME_PATTERN = re.compile(r"(tmp|temp|test)", re.IGNORECASE)

_CONFIRM_ENV_VAR = "CONFIRM_REAL_DB_MIGRATION_TARGET"
_CONFIRM_REQUIRED_VALUE = "I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB"


def _is_unmodified_default_endpoint(db_config: dict) -> bool:
    """
    host/port 是否等於 .env.example 的未覆寫預設值（localhost:5432）。

    本專案的 docker-compose 拓樸下，這組座標從 app 容器內連線時直接指向真實開發 DB
    （network_mode: service:db）。本專案至今建立的每一個隔離臨時 DB 皆刻意使用
    與 5432 不同的埠號，因此「host/port 完全等於預設值」在本專案的實際慣例下，
    等同於「呼叫端沒有主動選擇一個隔離目標」。
    """
    try:
        port = int(db_config.get("port", 0))
    except (TypeError, ValueError):
        port = 0
    return db_config.get("host") == _DEFAULT_HOST and port == _DEFAULT_PORT


def _is_recognized_temp_db_name(database_name: str) -> bool:
    """
    database 名稱是否符合本專案臨時 DB 的命名慣例（含 tmp／temp／test）。

    採正向表列：要求刻意建立的臨時 DB 使用可辨識的名稱，而非嘗試判斷「這是真實 DB」
    （後者需要硬編碼真實 DB 名稱等機敏設定，不應出現在程式碼中）。
    """
    return bool(_TEMP_DB_NAME_PATTERN.search(database_name or ""))


def assert_safe_migration_target(db_config: dict) -> None:
    """
    RISK-013 根本解守門函式。DB 寫入腳本執行任何 DDL／INSERT 前必須呼叫本函式。

    判定邏輯：訊號 A（host/port 未覆寫）或訊號 B（database 名稱不符臨時 DB 命名慣例）
    任一觸發，即判定為「疑似真實 DB」，除非呼叫端已透過環境變數
    CONFIRM_REAL_DB_MIGRATION_TARGET 提供完整且正確的確認字串，否則拒絕執行。

    Args:
        db_config: 通常為 DBWriter().db_config 的解析結果（host/port/database/...）。

    Raises:
        SystemExit: 偵測到疑似真實 DB 且未提供正確覆寫確認。
    """
    suspect_real = (
        _is_unmodified_default_endpoint(db_config)
        or not _is_recognized_temp_db_name(db_config.get("database", ""))
    )
    if not suspect_real:
        return

    confirm = os.environ.get(_CONFIRM_ENV_VAR)
    if confirm != _CONFIRM_REQUIRED_VALUE:
        raise SystemExit(
            f"[RISK-013 guard] 偵測到連線目標疑似為真實開發 DB "
            f"(host={db_config.get('host')}, port={db_config.get('port')}, "
            f"database={db_config.get('database')})，拒絕執行。\n"
            f"若確實要對真實 DB 執行（例如正式套用 migration），"
            f"請先完成 CLAUDE.md RISK-013 協定之綁定確認呈報，"
            f"再設定環境變數 {_CONFIRM_ENV_VAR}={_CONFIRM_REQUIRED_VALUE} 後重跑。"
        )
