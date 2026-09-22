import os
from pathlib import Path

import psycopg2


SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")
REQUIRED_DB_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


def _load_db_config() -> dict:
    """從環境變數取得與 DBWriter 一致的資料庫連線設定。"""
    missing_env = [name for name in REQUIRED_DB_ENV if not os.getenv(name)]
    if missing_env:
        raise RuntimeError(
            "缺少必要資料庫環境變數：" + ", ".join(missing_env)
        )

    db_port = os.getenv("DB_PORT", "5432")
    try:
        db_port = int(db_port)
    except ValueError as exc:
        raise RuntimeError("DB_PORT 必須是有效整數。") from exc

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": db_port,
        "database": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def _load_schema_sql() -> str:
    """以 UTF-8 讀取 canonical schema，並在連線前對檔案問題快速失敗。"""
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"無法讀取資料庫 Schema 檔案：{SCHEMA_PATH}") from exc

    if not schema_sql.strip():
        raise RuntimeError(f"資料庫 Schema 檔案為空：{SCHEMA_PATH}")

    return schema_sql


def create_tables():
    """在新的空資料庫執行 canonical schema initialization。"""
    schema_sql = _load_schema_sql()
    db_config = _load_db_config()

    print("正在連線到 PostgreSQL...")
    connection = psycopg2.connect(**db_config)

    try:
        with connection.cursor() as cursor:
            print("正在執行 database/schema.sql...")
            cursor.execute(schema_sql)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print("資料庫初始化已成功 commit。")


def reset_database(keep_seeds: bool = True):
    """
    清空業務資料表 (stock_prices, market_articles, sentiment_cache, daily_ml_features)，
    並確保 tracking_keywords, entity_mapping 與 theme_stock_mapping 種子資料完整。
    """
    db_config = _load_db_config()
    print("正在連線到 PostgreSQL 執行安全清空重設...")
    connection = psycopg2.connect(**db_config)

    try:
        with connection.cursor() as cursor:
            print("正在清空業務資料表 (TRUNCATE stock_prices, market_articles, sentiment_cache, daily_ml_features)...")
            cursor.execute("""
                TRUNCATE TABLE daily_ml_features, sentiment_cache, market_articles, stock_prices RESTART IDENTITY CASCADE;
            """)
            if keep_seeds:
                print("正在驗證與恢復種子資料 (tracking_keywords, entity_mapping, theme_stock_mapping)...")
                schema_sql = _load_schema_sql()
                cursor.execute(schema_sql)
        connection.commit()
        print("✅ 資料庫重設已成功完成並 Commit。")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    create_tables()
