"""
tests/test_db_target_guard.py

UG-G1-SB4 階段一：驗證 database/db_target_guard.py（RISK-013 根本解）。
完全使用合成 db_config dict，不連接任何資料庫。

案例對照 doc/upgrade/gates/closed/SB4_GATE_A_PROPOSAL.md §3.5：
  known-FAIL 1：完全未覆寫（host/port 皆預設，database 名稱亦不含 tmp 字樣）
  known-FAIL 2：僅訊號 A 觸發（database 名稱符合慣例，但 host/port 仍是預設值）
  known-FAIL 3：覆寫值錯誤（設定了確認變數但值不是要求的完整字串）
  正向案例 1：隔離臨時 DB（host/port 非預設、database 名稱含 tmp）
  正向案例 2：真實 DB 座標 + 正確覆寫確認
"""

import os
import unittest

from database.db_target_guard import assert_safe_migration_target, _CONFIRM_ENV_VAR, _CONFIRM_REQUIRED_VALUE


class DBTargetGuardTests(unittest.TestCase):

    def setUp(self):
        # 確保每個測試前後環境變數乾淨，不因執行順序互相汙染
        self._orig_confirm = os.environ.pop(_CONFIRM_ENV_VAR, None)

    def tearDown(self):
        if self._orig_confirm is None:
            os.environ.pop(_CONFIRM_ENV_VAR, None)
        else:
            os.environ[_CONFIRM_ENV_VAR] = self._orig_confirm

    def test_known_fail_1_completely_unmodified_defaults_is_blocked(self):
        """known-FAIL 案例 1：host/port 皆預設，database 名稱亦不含 tmp 字樣，無確認變數。"""
        db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
        with self.assertRaises(SystemExit) as ctx:
            assert_safe_migration_target(db_config)
        msg = str(ctx.exception)
        self.assertIn("localhost", msg)
        self.assertIn("5432", msg)
        self.assertIn("postgres", msg)

    def test_known_fail_2_signal_a_alone_is_sufficient_to_block(self):
        """known-FAIL 案例 2：僅訊號 A（host/port 未覆寫）觸發，database 名稱本身符合臨時慣例，仍必須擋下。"""
        db_config = {"host": "localhost", "port": 5432, "database": "sb4_test_tmpdb"}
        with self.assertRaises(SystemExit):
            assert_safe_migration_target(db_config)

    def test_known_fail_3_wrong_confirm_value_is_still_blocked(self):
        """known-FAIL 案例 3：確認變數存在但值不是要求的完整字串（例如誤用 "1"），仍必須擋下。"""
        os.environ[_CONFIRM_ENV_VAR] = "1"
        db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
        with self.assertRaises(SystemExit):
            assert_safe_migration_target(db_config)

    def test_positive_1_isolated_temp_db_passes(self):
        """正向案例 1：host/port 非預設、database 名稱含 tmp——比照本專案既有臨時 DB 慣例，應正常放行。"""
        db_config = {"host": "localhost", "port": 55436, "database": "sb4_test_tmpdb"}
        assert_safe_migration_target(db_config)  # 不應拋出

    def test_positive_2_real_db_with_correct_confirmation_passes(self):
        """正向案例 2：真實 DB 座標，但已正確設定覆寫確認變數——證明機制不會鎖死正當的正式執行。"""
        os.environ[_CONFIRM_ENV_VAR] = _CONFIRM_REQUIRED_VALUE
        db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
        assert_safe_migration_target(db_config)  # 不應拋出


if __name__ == "__main__":
    unittest.main()
