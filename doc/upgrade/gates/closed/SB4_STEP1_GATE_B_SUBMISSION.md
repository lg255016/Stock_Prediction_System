# UG-G1-SB4 階段一 Gate B 送審文件：RISK-013 根本解（`db_target_guard`）

> **性質**：`gate-submit` skill 六項強制產出的整合文件。**不是** commit 授權本身——
> commit 授權留待 PO 讀完本文件後另行決定。本次未執行 `git add`／`git commit`。
> **提交日期**：2026-08-26
> **範圍**：僅 UG-G1-SB4 **階段一**（RISK-013 根本解本體）。依 PO 明確裁決，
> 階段一獨立送審、獨立取得核准，不與階段二（`schema_version` 表、migration 框架、
> `apply_migrations.py`）併入同一份 Gate B 文件——「保護真實 DB 的機制本身，
> 值得有自己聚焦的 Gate B，不要被階段二的實際 migration diff 稀釋審查注意力」
> （PO 原話，2026-08-26）。
> **狀態**：`database/db_target_guard.py` 與 `tests/test_db_target_guard.py` 已完成
> 並通過 §7 全部 5 個可執行案例；`src/`、`database/schema.sql`、
> `database/migrations/`、`database/apply_migrations.py` 完全未動——階段二尚未開始，
> 待本階段取得 PO 核准後才會啟動。

---

## 0. 提交前回顧

| 項目 | 內容 | 完成日期 |
|------|------|---------|
| Gate A | `SB4_GATE_A_PROPOSAL.md`，含兩階段拆分設計、§3 偵測訊號與 known-FAIL 驗證計畫 | 2026-08-26 |
| PO 裁決 | §7 四項全數核准：不需第三個訊號（app 容器無法可靠偵測 db 服務掛載型態，需要 docker socket 存取權本身是更大風險）；覆寫值用完整句子；階段一獨立送審；核准開始階段一實作 | 2026-08-26 |
| 實作 | `database/db_target_guard.py`（`assert_safe_migration_target`、訊號 A／B）；`tests/test_db_target_guard.py`（5 個案例） | 2026-08-26 |
| 驗證 | 5 個案例個別執行並取得原始輸出；194/194 全套測試（含既有 189 個）；contract-check 11/11 | 2026-08-26 |
| 步驟 6 | 本文件（階段一 Gate B 送審） | 2026-08-26 |

**核心決策**：偵測邏輯採兩個獨立訊號（host/port 是否為未覆寫預設值；database 名稱
是否符合臨時 DB 命名慣例），任一觸發即判定「疑似真實 DB」並要求明確覆寫確認
（`CONFIRM_REAL_DB_MIGRATION_TARGET=I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB`，
刻意要求完整句子而非簡單真值）。PO 核准前曾親自查核 SB1～SB3 所有已結案文件裡
實際使用過的臨時 DB 埠號（55433～55436）與命名（皆含 `tmp`），確認訊號設計與
既有慣例完全吻合，故不需第三個「postgres-data 掛載偵測」訊號。

---

## 1. 完整 Diff

**檔案清單**（2 new，150 insertions(+)）：

```
 database/db_target_guard.py   | 81 +++++++++++++++++++++++++++++++++++++++++++
 tests/test_db_target_guard.py | 69 ++++++++++++++++++++++++++++++++++++
 2 files changed, 150 insertions(+)
```

**重跑指令**：`git add -N database/db_target_guard.py tests/test_db_target_guard.py && git diff -- database/db_target_guard.py tests/test_db_target_guard.py`
（兩檔皆為新檔，`git diff` 預設不涵蓋未追蹤檔案，需先以 `-N` intent-to-add 才能重現下方內容；本次僅用於產出這份文件的 diff 展示，執行後已 `git reset` 還原為未追蹤狀態，未真正 staged）

<details>
<summary>完整 diff 內容（點擊展開）</summary>

```diff
diff --git a/database/db_target_guard.py b/database/db_target_guard.py
new file mode 100644
index 0000000..08dc27c
--- /dev/null
+++ b/database/db_target_guard.py
@@ -0,0 +1,81 @@
+"""
+database/db_target_guard.py
+
+RISK-013 根本解（UG-G1-SB4 階段一）：任何會對資料庫執行寫入（DDL／INSERT／UPDATE／
+DELETE）的腳本，在建立連線之前，必須呼叫 assert_safe_migration_target(db_config)。
+
+偵測到連線目標「疑似真實開發 DB」且未提供明確覆寫確認時，raise SystemExit（非 0
+結束碼），不執行任何連線動作。
+
+設計依據：doc/upgrade/gates/closed/SB4_GATE_A_PROPOSAL.md §3（PO 已核准）。
+"""
+
+import os
+import re
+
+_DEFAULT_HOST = "localhost"
+_DEFAULT_PORT = 5432
+
+_TEMP_DB_NAME_PATTERN = re.compile(r"(tmp|temp|test)", re.IGNORECASE)
+
+_CONFIRM_ENV_VAR = "CONFIRM_REAL_DB_MIGRATION_TARGET"
+_CONFIRM_REQUIRED_VALUE = "I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB"
+
+
+def _is_unmodified_default_endpoint(db_config: dict) -> bool:
+    """
+    host/port 是否等於 .env.example 的未覆寫預設值（localhost:5432）。
+
+    本專案的 docker-compose 拓樸下，這組座標從 app 容器內連線時直接指向真實開發 DB
+    （network_mode: service:db）。本專案至今建立的每一個隔離臨時 DB 皆刻意使用
+    與 5432 不同的埠號，因此「host/port 完全等於預設值」在本專案的實際慣例下，
+    等同於「呼叫端沒有主動選擇一個隔離目標」。
+    """
+    try:
+        port = int(db_config.get("port", 0))
+    except (TypeError, ValueError):
+        port = 0
+    return db_config.get("host") == _DEFAULT_HOST and port == _DEFAULT_PORT
+
+
+def _is_recognized_temp_db_name(database_name: str) -> bool:
+    """
+    database 名稱是否符合本專案臨時 DB 的命名慣例（含 tmp／temp／test）。
+
+    採正向表列：要求刻意建立的臨時 DB 使用可辨識的名稱，而非嘗試判斷「這是真實 DB」
+    （後者需要硬編碼真實 DB 名稱等機敏設定，不應出現在程式碼中）。
+    """
+    return bool(_TEMP_DB_NAME_PATTERN.search(database_name or ""))
+
+
+def assert_safe_migration_target(db_config: dict) -> None:
+    """
+    RISK-013 根本解守門函式。DB 寫入腳本執行任何 DDL／INSERT 前必須呼叫本函式。
+
+    判定邏輯：訊號 A（host/port 未覆寫）或訊號 B（database 名稱不符臨時 DB 命名慣例）
+    任一觸發，即判定為「疑似真實 DB」，除非呼叫端已透過環境變數
+    CONFIRM_REAL_DB_MIGRATION_TARGET 提供完整且正確的確認字串，否則拒絕執行。
+
+    Args:
+        db_config: 通常為 DBWriter().db_config 的解析結果（host/port/database/...）。
+
+    Raises:
+        SystemExit: 偵測到疑似真實 DB 且未提供正確覆寫確認。
+    """
+    suspect_real = (
+        _is_unmodified_default_endpoint(db_config)
+        or not _is_recognized_temp_db_name(db_config.get("database", ""))
+    )
+    if not suspect_real:
+        return
+
+    confirm = os.environ.get(_CONFIRM_ENV_VAR)
+    if confirm != _CONFIRM_REQUIRED_VALUE:
+        raise SystemExit(
+            f"[RISK-013 guard] 偵測到連線目標疑似為真實開發 DB "
+            f"(host={db_config.get('host')}, port={db_config.get('port')}, "
+            f"database={db_config.get('database')})，拒絕執行。\n"
+            f"若確實要對真實 DB 執行（例如正式套用 migration），"
+            f"請先完成 CLAUDE.md RISK-013 協定之綁定確認呈報，"
+            f"再設定環境變數 {_CONFIRM_ENV_VAR}={_CONFIRM_REQUIRED_VALUE} 後重跑。"
+        )
diff --git a/tests/test_db_target_guard.py b/tests/test_db_target_guard.py
new file mode 100644
index 0000000..9ef17e4
--- /dev/null
+++ b/tests/test_db_target_guard.py
@@ -0,0 +1,69 @@
+"""
+tests/test_db_target_guard.py
+
+UG-G1-SB4 階段一：驗證 database/db_target_guard.py（RISK-013 根本解）。
+完全使用合成 db_config dict，不連接任何資料庫。
+
+案例對照 doc/upgrade/gates/closed/SB4_GATE_A_PROPOSAL.md §3.5：
+  known-FAIL 1：完全未覆寫（host/port 皆預設，database 名稱亦不含 tmp 字樣）
+  known-FAIL 2：僅訊號 A 觸發（database 名稱符合慣例，但 host/port 仍是預設值）
+  known-FAIL 3：覆寫值錯誤（設定了確認變數但值不是要求的完整字串）
+  正向案例 1：隔離臨時 DB（host/port 非預設、database 名稱含 tmp）
+  正向案例 2：真實 DB 座標 + 正確覆寫確認
+"""
+
+import os
+import unittest
+
+from database.db_target_guard import assert_safe_migration_target, _CONFIRM_ENV_VAR, _CONFIRM_REQUIRED_VALUE
+
+
+class DBTargetGuardTests(unittest.TestCase):
+
+    def setUp(self):
+        # 確保每個測試前後環境變數乾淨，不因執行順序互相汙染
+        self._orig_confirm = os.environ.pop(_CONFIRM_ENV_VAR, None)
+
+    def tearDown(self):
+        if self._orig_confirm is None:
+            os.environ.pop(_CONFIRM_ENV_VAR, None)
+        else:
+            os.environ[_CONFIRM_ENV_VAR] = self._orig_confirm
+
+    def test_known_fail_1_completely_unmodified_defaults_is_blocked(self):
+        """known-FAIL 案例 1：host/port 皆預設，database 名稱亦不含 tmp 字樣，無確認變數。"""
+        db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
+        with self.assertRaises(SystemExit) as ctx:
+            assert_safe_migration_target(db_config)
+        msg = str(ctx.exception)
+        self.assertIn("localhost", msg)
+        self.assertIn("5432", msg)
+        self.assertIn("postgres", msg)
+
+    def test_known_fail_2_signal_a_alone_is_sufficient_to_block(self):
+        """known-FAIL 案例 2：僅訊號 A（host/port 未覆寫）觸發，database 名稱本身符合臨時慣例，仍必須擋下。"""
+        db_config = {"host": "localhost", "port": 5432, "database": "sb4_test_tmpdb"}
+        with self.assertRaises(SystemExit):
+            assert_safe_migration_target(db_config)
+
+    def test_known_fail_3_wrong_confirm_value_is_still_blocked(self):
+        """known-FAIL 案例 3：確認變數存在但值不是要求的完整字串（例如誤用 "1"），仍必須擋下。"""
+        os.environ[_CONFIRM_ENV_VAR] = "1"
+        db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
+        with self.assertRaises(SystemExit):
+            assert_safe_migration_target(db_config)
+
+    def test_positive_1_isolated_temp_db_passes(self):
+        """正向案例 1：host/port 非預設、database 名稱含 tmp——比照本專案既有臨時 DB 慣例，應正常放行。"""
+        db_config = {"host": "localhost", "port": 55436, "database": "sb4_test_tmpdb"}
+        assert_safe_migration_target(db_config)  # 不應拋出
+
+    def test_positive_2_real_db_with_correct_confirmation_passes(self):
+        """正向案例 2：真實 DB 座標，但已正確設定覆寫確認變數——證明機制不會鎖死正當的正式執行。"""
+        os.environ[_CONFIRM_ENV_VAR] = _CONFIRM_REQUIRED_VALUE
+        db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
+        assert_safe_migration_target(db_config)  # 不應拋出
+
+
+if __name__ == "__main__":
+    unittest.main()
```

</details>

---

## 2. 產出 1：契約驗證原始輸出

```bash
python scripts/verify/gate0_contract_check.py
echo "EXIT=$?"
```

```
B1   PASS | 29 欄契約完整性
       migration 新增 22 + 既有 7 = 29
B2   PASS | 被引用欄位皆存在於契約（反查法）
       8 個被引用，缺失 0
B3   PASS | 社群欄位皆有 SOURCE_FAILED→NULL 規則（反查法）
       9 社群列全部標明 NULL
B4   PASS | raw 層留言計數欄無 DEFAULT（反查法）
       四欄型別: ['INTEGER']
B5   PASS | Triple-Barrier label domain 一致
       3/3 文件宣告；DDL CHECK=True
B6   PASS | Barrier anchor 一致為 Open[T+1]
       6 份使用；殘留舊 anchor 0
B7   PASS | 無「來源失敗→空 DataFrame」
       8 處提及，逐行判定全部為正當語境
B8   PASS | §19 需 PO 簽的決策皆有 ADR 承接
       6/6 存在
B9   PASS | Dcard SB 引用正確
       UG-G2-SB5 存在，無 UG-G3-SB1 誤引用
B10  PASS | 編號方案有唯一對照表
       FEATURE_REGISTRY.md §3.7 DB序號↔模型輸入索引對照
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:577 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂

==================================================
Part B: 11/11 PASS
EXIT=0
```

執行環境：container（`stock_prediction_system2_devcontainer-app-1`，`-u vscode`）。
`database/db_target_guard.py` 與 `tests/test_db_target_guard.py` 皆不在 `DOC_PATHS`
掃描範圍內，重跑僅為確認本次新增未破壞既有跨文件契約一致性。

---

## 3. 產出 2：執行環境 + 測試原始輸出 + 依賴狀態表

### 3a. 執行環境

| 欄位 | 內容 |
|------|------|
| 執行環境 | **container** |
| Python 版本 | `Python 3.14.6` |
| 容器名稱 | `stock_prediction_system2_devcontainer-app-1`（`-u vscode`） |

### 3b. 測試原始輸出

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python -m unittest discover -s tests -p "test_*.py"
```

```
Ran 194 tests in 13.668s

OK
```

194 = 189（SB3 commit `61016ee` 基線）+ 5 個新增（`tests/test_db_target_guard.py`）。
**既有 189 個測試在本次新增後仍全數 PASS，未受影響**——`database/db_target_guard.py`
是全新獨立模組，不修改任何既有程式碼路徑。

### 3c. 依賴狀態表

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode stock_prediction_system2_devcontainer-app-1 \
  python -c "import importlib.util as u; [print(f'{m:26}', 'PRESENT' if u.find_spec(m) else 'ABSENT') for m in ['numpy','pandas','streamlit','plotly','sklearn','lightgbm','xgboost','psycopg2','jieba','snownlp','tenacity','dotenv']]"
```

```
numpy                      PRESENT
pandas                     PRESENT
streamlit                  PRESENT
plotly                     PRESENT
sklearn                    PRESENT
lightgbm                   PRESENT
xgboost                    PRESENT
psycopg2                   PRESENT
jieba                      PRESENT
snownlp                    PRESENT
tenacity                   PRESENT
dotenv                     PRESENT
```

**12/12 PRESENT**。`database/db_target_guard.py` 本身不依賴任何第三方套件
（僅用 `os`、`re` 標準函式庫），本表僅為維持格式一致性列出，非本模組直接相關。

---

## 4. 產出 3：檔案清單與逐檔授權稽核

```bash
git status --porcelain
```

```
?? database/db_target_guard.py
?? tests/test_db_target_guard.py
```

> 本次僅列本階段新增的 2 個檔案。SB3 結案（`PROJECT_STATUS.md`、
> `SYSTEM_UPGRADE_MASTER_PLAN.md` 修改與 2 份文件搬移至 `closed/`）為獨立、
> 尚待您另行授權的 commit，不併入本階段報告；`SB4_GATE_A_PROPOSAL.md` 為
> 已核准之提案本體，亦不在本次 commit 範圍內討論（其去留另計）。

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `database/db_target_guard.py`（新檔） | 在授權交付物內 | `SB4_GATE_A_PROPOSAL.md` §3.4／§7 第 4 項，PO 已核准開始階段一實作 |
| `tests/test_db_target_guard.py`（新檔） | 在授權交付物內 | `SB4_GATE_A_PROPOSAL.md` §3.5 六案例驗證計畫（本文件 §7 說明其中 5 項為可執行測試） |

**本次無超出授權清單的檔案。**

---

## 5. 產出 4：格式／行尾夾帶偵測

```bash
git add -N database/db_target_guard.py tests/test_db_target_guard.py
git diff --numstat -- database/db_target_guard.py tests/test_db_target_guard.py > /tmp/ns_raw.txt
git diff --numstat -w -- database/db_target_guard.py tests/test_db_target_guard.py > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
git reset database/db_target_guard.py tests/test_db_target_guard.py
```

```
（無輸出，兩者完全一致）
```

**無落差**——兩份皆為全新檔案，內容從無到有，不存在「格式夾帶」的可能性
（沒有舊版本可供對照出格式差異）。

---

## 6. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 不可重跑原因 |
|------|---------|--------------------------|
| contract-check 11/11 PASS | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py` |
| 全套測試 194/194 PASS（container，含既有 189 個未受影響） | `VERIFIED THIS SESSION` | §3b 指令 |
| `assert_safe_migration_target` 對 5 個案例行為正確 | `VERIFIED THIS SESSION` | §7 逐案例原始輸出；`tests/test_db_target_guard.py` |
| 訊號 A／B 設計與 SB1～SB3 實際使用過的臨時 DB 埠號／命名慣例吻合 | `REPORTED, NOT INDEPENDENTLY VERIFIED` | PO 本人查核 SB1～SB3 已結案文件後回報（2026-08-26），本次未由 PM 重新逐一核對每份文件 |
| 第三個偵測訊號（postgres-data 掛載）技術上不可靠而未採用 | `ENGINEERING JUDGMENT` | 不可重跑：屬架構限制判斷（app 容器與 db 容器為獨立命名空間，無 docker socket 存取權下無法從內部查詢對方 volume 掛載型態），非執行結果 |
| `py_compile` 語法檢查通過 | `VERIFIED THIS SESSION` | `python -m py_compile database/db_target_guard.py tests/test_db_target_guard.py` |

---

## 7. 產出 6：known-FAIL 案例對照表

依 `SB4_GATE_A_PROPOSAL.md` §3.5，共 6 項案例。以下 5 項為可執行測試，皆已實際
執行並取得原始輸出；第 6 項（對照組）維持提案中即已聲明的「非執行」性質，
理由見案例 6 說明。

| # | 案例 | 建構方式 | 實測結果（原始輸出） |
|---|------|---------|---------------------|
| 1 | **known-FAIL：完全未覆寫預設值** | `{"host": "localhost", "port": 5432, "database": "postgres"}`，無確認變數 | `SystemExit: [RISK-013 guard] 偵測到連線目標疑似為真實開發 DB (host=localhost, port=5432, database=postgres)，拒絕執行。...` |
| 2 | **known-FAIL：僅訊號 A 單獨觸發** | `{"host": "localhost", "port": 5432, "database": "sb4_test_tmpdb"}`（database 名稱本身符合慣例，但 host/port 未覆寫） | `SystemExit: ...(host=localhost, port=5432, database=sb4_test_tmpdb)，拒絕執行。...`——證實「任一訊號觸發即擋」而非「兩者皆需觸發」 |
| 3 | **known-FAIL：確認值錯誤** | 設定 `CONFIRM_REAL_DB_MIGRATION_TARGET=1`（非要求的完整字串），config 同案例 1 | `SystemExit: ...`——證實簡單真值無法意外繞過確認機制 |
| 4 | **正向：隔離臨時 DB** | `{"host": "localhost", "port": 55436, "database": "sb4_test_tmpdb"}`（比照 SB1～SB3 既有慣例） | 正常回傳，無例外 |
| 5 | **正向：真實 DB 座標 + 正確覆寫** | config 同案例 1，`CONFIRM_REAL_DB_MIGRATION_TARGET=I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB` | 正常回傳，無例外——證實刻意覆寫確實可用，機制不會鎖死正當的正式執行 |
| 6 | **對照組：舊防線失效示範** | 提案 §3.5 原文：「假設性重建『沒有本機制』的世界」 | **維持非執行**。理由：階段二（`apply_migrations.py`）尚未實作，沒有「舊版本」可供實際執行對照；且唯一能讓這個對照具備實質意義的方式，是真的讓一支未受保護的腳本嘗試連向真實 DB 座標——這正是本機制存在的目的所要防止的事，不應為了產出一筆執行紀錄而刻意重現。本項維持提案中已聲明的程式碼走查形式：無 `assert_safe_migration_target` 保護時，任何腳本呼叫 `DBWriter()` 解析出 `localhost:5432` 後會直接進入 `psycopg2.connect(...)`，中間沒有任何攔截點——這點可由 §1 diff 與 `src/loaders/db_writer.py:50-55`（本次未變更）逐行核對確認，但刻意不以實際連線執行來驗證 |

**若 PO 認為案例 6 仍必須有可執行證據**：可行方案是在階段二 `apply_migrations.py`
完成後，構造一個「移除 `assert_safe_migration_target` 呼叫」的臨時版本，對**隔離
臨時 DB**（非真實 DB）執行，證明沒有守門函式時腳本會直接嘗試連線——這樣可以
在不碰真實 DB 的前提下取得可執行證據，但需要階段二的程式碼才能構造，本階段
無法提前完成。請您裁示是否需要，若需要將排入階段二的驗證計畫。

---

## 8. 尚未解決／請 PO 裁決事項

1. **案例 6 是否需要可執行證據**：見 §7 案例 6 說明，若需要將排入階段二。
2. **SB3 結案 commit 仍待授權**：與本階段無關，獨立列出提醒——上次回報後尚未收到
   您對 SB3 結案（2 modified + 2 rename）的 commit 授權。
3. 階段一驗收通過、取得您的 commit 授權後，才會開始階段二（`schema_version` 表、
   `database/migrations/`、`apply_migrations.py`）的實作。

**commit 授權**：本文件為送審文件，不代表 commit 已獲授權。若 PO 決定放行，
請明確指出授權範圍（哪些檔案）；`gate-submit` skill 的自檢流程第 3～5 步
（`git add`、逐檔稽核、格式偵測）將在取得授權後於 commit 前重新針對實際 staged 內容執行一次。
