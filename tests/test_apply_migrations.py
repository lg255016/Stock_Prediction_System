"""
tests/test_apply_migrations.py

UG-G1-SB4 階段二：database/apply_migrations.py 的隔離單元測試（mock DB 連線與游標，
不連接任何真實資料庫，符合測試封閉性慣例）。

**這些測試驗證的是邏輯正確性，不是「跑起來真的能連 Postgres」**——後者已於
2026-08-26 對隔離臨時 DB（sb4_migration_tmpdb，port 55440，非 postgres-data 掛載）
實際執行過完整 E2E 驗證（fresh init + apply、冪等性、版本檢查、真實 DB 座標被拒絕、
故意失敗遷移的 ROLLBACK），原始輸出見 doc/upgrade/gates/closed/SB4_STEP2_GATE_B_SUBMISSION.md。
"""

import unittest
from unittest.mock import MagicMock, patch


class MigrationVersionCheckTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_version_check"""

    def test_version_check_table_missing_returns_zero(self):
        from database.apply_migrations import _get_current_version
        cursor = MagicMock()
        cursor.fetchone.return_value = (False,)  # information_schema 查詢：表不存在
        self.assertEqual(_get_current_version(cursor), 0)

    def test_version_check_table_exists_returns_max_version(self):
        from database.apply_migrations import _get_current_version
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(True,), (3,)]  # 表存在 → MAX(version)=3
        self.assertEqual(_get_current_version(cursor), 3)

    def test_version_check_table_exists_but_empty_returns_zero(self):
        """表已建立但尚未有任何版本列（MAX 回傳 NULL）時應視為版本 0，不得誤判為 None 或拋錯。"""
        from database.apply_migrations import _get_current_version
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(True,), (None,)]
        self.assertEqual(_get_current_version(cursor), 0)


class MigrationIdempotencyTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_migration_idempotency"""

    @patch("database.apply_migrations.psycopg2.connect")
    @patch("database.apply_migrations.assert_safe_migration_target")
    @patch("database.apply_migrations.DBWriter")
    def test_no_pending_migrations_skips_execution_and_returns_zero(self, mock_writer_cls, mock_guard, mock_connect):
        """目前版本已等於最新遷移版本時，不得執行任何遷移 SQL，直接回傳 0。"""
        from database.apply_migrations import apply_migrations, _discover_migrations

        # 由實際 migrations/ 目錄推導最新版本號，不寫死數字——每次新增一份遷移
        # （SB1 加 002、SB3 加 003）都要回來手動改這個 fixture 的話，
        # 這個測試本身就會變成新增遷移時的固定阻礙，而非有效檢查。
        latest_version = _discover_migrations()[-1][0]

        mock_writer_cls.return_value.db_config = {"host": "x", "port": 1, "database": "sb4_test_tmpdb"}
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.side_effect = [(True,), (latest_version,)]  # 表存在，目前版本已是最新

        exit_code = apply_migrations()

        self.assertEqual(exit_code, 0)
        # 除了版本檢查用的兩次 fetchone 之外，不應再對任何遷移 SQL 呼叫 execute
        # （_apply_one_migration 會另外開新的 cursor context，這裡驗證的是主流程未進入該分支）
        mock_conn.commit.assert_not_called()


class MigrationRollbackTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_rollback_on_failure"""

    @patch("database.apply_migrations.psycopg2.connect")
    @patch("database.apply_migrations.assert_safe_migration_target")
    @patch("database.apply_migrations.DBWriter")
    def test_migration_failure_triggers_rollback_and_nonzero_return(self, mock_writer_cls, mock_guard, mock_connect):
        """遷移 SQL 執行拋出例外時，必須呼叫 connection.rollback()，且 apply_migrations() 回傳非 0。"""
        from database.apply_migrations import apply_migrations

        mock_writer_cls.return_value.db_config = {"host": "x", "port": 1, "database": "sb4_test_tmpdb"}
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.side_effect = [(True,), (0,)]  # 目前版本 v0，001_baseline.sql（v1）待套用

        def execute_side_effect(sql, *args, **kwargs):
            # 僅讓「版本檢查」查詢正常通過；遷移本體 SQL（001_baseline.sql 內容不含
            # information_schema／MAX(version) 字樣）才觸發模擬失敗，避免連版本檢查
            # 這個前置步驟都被誤判為失敗。
            if "information_schema" in sql or "MAX(version)" in sql:
                return None
            raise Exception("simulated DDL failure")

        mock_cursor.execute.side_effect = execute_side_effect

        exit_code = apply_migrations()

        self.assertEqual(exit_code, 1)
        mock_conn.rollback.assert_called()
        mock_conn.commit.assert_not_called()


class MigrationGuardIntegrationTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_runner_nonzero_exit_on_error（RISK-013 根本解整合）"""

    @patch("database.apply_migrations.psycopg2.connect")
    @patch("database.apply_migrations.DBWriter")
    def test_guard_rejection_prevents_any_connection_attempt(self, mock_writer_cls, mock_connect):
        """assert_safe_migration_target 判定疑似真實 DB 時，不得呼叫 psycopg2.connect。"""
        from database.apply_migrations import apply_migrations

        # 未覆寫的預設值 + 非臨時命名，且未設定確認變數 → 應觸發 SystemExit
        mock_writer_cls.return_value.db_config = {"host": "localhost", "port": 5432, "database": "postgres"}

        with self.assertRaises(SystemExit):
            apply_migrations()

        mock_connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
