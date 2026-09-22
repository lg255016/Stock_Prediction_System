# UG-G1-SB4 Gate A 提案：DB Migration 機制建立（含 RISK-013 根本解）

> **性質**：Gate A 提案（實作前審批），非實作。
> **提交日期**：2026-08-26
> **前置**：UG-Gate-1 已由 PO 核准（逐 SB 授權）；UG-G1-SB1（commit `ccf0e52a`）、
> UG-G1-SB2（commit `414fcc8`）、UG-G1-SB3（commit `61016ee`）皆已結案。
> **狀態**：`src/`、`database/` 未動，diff 為空。
> **與前三個 SB 的關鍵差異**：SB1～SB3 全部是**唯讀路徑**——最壞情況是讀到不該讀的資料，
> 可回復。SB4 是本專案第一個**寫入路徑**的 SB（DDL migration）。PO 明確要求：
> RISK-013 的根本解（「驗證腳本偵測到指向真實 DB 時自動拒絕執行」）必須是本 SB
> 的**第一個實作步驟**，且在這個步驟通過驗收之前，其餘部分（實際 migration 邏輯）
> 不得開始實作。本提案依此要求分為兩個階段。

---

## 1. 本提案要解決的問題

| # | 來源 | 內容 |
|---|------|------|
| 1 | Master Plan §7.1 UG-G1-SB4 Brief；`DB_MIGRATION_PLAN.md` | 建立可版本追蹤的 Schema 遷移機制（`schema_version` 表 + `database/migrations/` + `apply_migrations.py` runner） |
| 2 | `REMAINING_RISKS.md` RISK-013（High，PO 2026-08-24 簽核）；`PROJECT_STATUS.md` §0.5 義務 #1 | RISK-013 的既有緩解（呈報綁定確認的回報紀律）**擋不住寫入路徑**：漏設 `DB_HOST`／`DB_PORT` 的後果從「讀了不該讀的」變成「對真實開發資料庫執行 DDL」，回報紀律本身無法阻止操作已經發生。根本解**必須**在本 SB 動任何 migration 邏輯之前落地——這是 PO 對本提案的強制要求，不是建議 |
| 3 | `DB_MIGRATION_PLAN.md` §6「8 項安全保證」現況核對 | 既有 8 項保證（僅加法 DDL、禁止破壞性操作、pg_dump 備份、獨立事務、失敗 ROLLBACK、隔離容器先驗證、不動 postgres-data、schema_version 表永不 DROP）**沒有一項回答「腳本怎麼知道自己連到哪裡」**——全部假設連線目標已經正確，這正是 RISK-013 指出的缺口 |

---

## 2. 現況與問題（逐行核對，2026-08-26）

### 2.1 目前的連線解析路徑（`src/loaders/db_writer.py:11-55`）

`DBWriter.__init__` 未傳入 `db_config` 時，逐一以 `os.getenv` 解析：

```python
self.db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": ...（os.getenv("DB_PORT", "5432")）,
    "database": os.environ["POSTGRES_DB"],
    "user": os.environ["POSTGRES_USER"],
    "password": os.environ["POSTGRES_PASSWORD"],
}
```

`.env.example` 明文：`DB_HOST=localhost`、`DB_PORT=5432`，註解寫「app 與 db 共用
network namespace，local development 預設使用 localhost:5432」。這代表**不覆寫
任何環境變數時，`DBWriter()` 解析出的連線目標就是真實開發 DB**——這不是一個
需要外部資訊才能判斷的模糊情境，而是本專案 `.env`／`docker-compose.yml`
拓樸本身已經寫死的事實：容器內 `localhost:5432` 這組座標**就是**真實 DB 的座標。

`.devcontainer/docker-compose.yml` 的 `db:` 服務：

```yaml
volumes:
  - ./postgres-data:/var/lib/postgresql
```

真實開發資料透過此 bind mount 持久化於 `.devcontainer/postgres-data/`。這是本專案
自己定義的「真實」與「臨時」的實質差異——臨時 DB（本次以前 SB1～SB3 建立的
全部隔離容器）刻意不掛載這個路徑，用完即 `docker rm -f -v` 拆除。

### 2.2 既有緩解的實際邊界

RISK-013 目前的緩解（「每次碰 DB 的執行，綁定確認輸出必須先呈報 PO 再跑」）是
**流程紀律**，不是**技術護欄**——它依賴執行者（我）記得覆寫環境變數、記得先呈報。
本 Session 已發生過一次遺漏（`REMAINING_RISKS.md` RISK-013 列的「已知觸發條件」，
2026-08-23）。對唯讀路徑而言，這個風險目前可承受；對 SB4 要建立的寫入路徑而言，
同一種遺漏的後果質變為對真實開發資料庫執行 DDL，且**無法用「回報紀律」事後補救**
——DDL 一旦執行，動作已經發生。

### 2.3 為什麼需要一個獨立於「記得做」的技術機制

人為紀律的失效模式是「這次忘了」；技術護欄的失效模式必須是「刻意繞過」。
兩者的差別，就是 RISK-013 至今懸而未決的核心理由。

---

## 3. 階段一（強制優先，其餘步驟的前置條件）：RISK-013 根本解

### 3.1 設計目標

一個可被任何未來的 DB 寫入腳本（本 SB 的 `apply_migrations.py`、以及日後任何
新增的寫入腳本）呼叫的守門函式：**在偵測到連線目標「看起來像真實開發 DB」時，
預設拒絕執行**，除非呼叫端提供明確、不易被誤觸的覆寫確認。

### 3.2 偵測訊號設計（兩個獨立訊號，任一觸發即判定為「疑似真實 DB」）

**訊號 A：host／port 是否為未覆寫的預設值**

```python
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432

def _is_unmodified_default_endpoint(db_config: dict) -> bool:
    return db_config.get("host") == _DEFAULT_HOST and int(db_config.get("port", 0)) == _DEFAULT_PORT
```

理由：本專案至今建立的**每一個**隔離臨時 DB（SB1～SB3 累計超過 5 個），都刻意使用
與 5432 不同的埠號（55432 系列）——這不是巧合，是既有的操作慣例。「host/port 完全
等於 `.env.example` 的預設值」在本專案的實際拓樸下，直接等同於「呼叫端沒有主動
選擇一個隔離目標」。這個檢查不需要連線，執行成本近乎零，作為第一道快速攔截。

**訊號 B：database 名稱是否符合臨時 DB 命名慣例**

```python
import re
_TEMP_DB_NAME_PATTERN = re.compile(r"(tmp|temp|test)", re.IGNORECASE)

def _is_recognized_temp_db_name(database_name: str) -> bool:
    return bool(_TEMP_DB_NAME_PATTERN.search(database_name or ""))
```

理由：與其嘗試「證明這是真實 DB」（需要真實 DB 名稱等特權資訊，本身也是不該
硬編碼進程式碼的機敏設定），改採**正向表列**——要求任何刻意建立的臨時 DB
必須以可辨識的名稱建立（本 Session 實際使用過的 `sb2_knownfail_tmpdb`、
`sb3_gateb_tmpdb`、`sb2_smoke_tmpdb` 皆已符合此樣式，無需額外改名）。
資料庫名稱不含這類字樣 → 視為「未被證明是臨時的」，預設判定疑似真實。

**為何兩個訊號都要，缺一不可**：只靠訊號 A，若有人手動把臨時 DB 也放在
`localhost:5432`（換一個容器頂替掉真實 DB 的埠號）就會誤放行；只靠訊號 B，
若忘記命名（用預設的 `postgres` 資料庫名稱建臨時 DB）也會誤放行。兩者交集
覆蓋兩種各自獨立的疏失來源。

### 3.3 明確覆寫機制（防止機制本身變成擋開發的阻礙）

```python
_CONFIRM_ENV_VAR = "CONFIRM_REAL_DB_MIGRATION_TARGET"
_CONFIRM_REQUIRED_VALUE = "I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB"

def assert_safe_migration_target(db_config: dict) -> None:
    """
    RISK-013 根本解：DB 寫入腳本執行任何 DDL／INSERT 前必須呼叫本函式。

    偵測到疑似真實 DB 且未提供正確覆寫確認時，raise SystemExit（非 0 結束碼），
    不執行任何連線動作之外的操作。
    """
    suspect_real = (
        _is_unmodified_default_endpoint(db_config)
        or not _is_recognized_temp_db_name(db_config.get("database", ""))
    )
    if not suspect_real:
        return  # 訊號皆未觸發，視為明確指向隔離臨時 DB，放行

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
    # 確認值正確才放行——不接受 "1"／"true" 等容易誤觸的值，
    # 刻意要求完整句子，降低複製貼上腳本樣板時意外帶過的機率。
```

**這個機制刻意不取代既有的「呈報綁定確認」流程紀律**——兩者疊加：流程紀律要求
「執行前先給 PO 看」，技術護欄則保證「就算流程紀律這次失守（忘記呈報），
程式本身仍會在觸及疑似真實 DB 時自動停下」。訊息文字裡也明確引導使用者回到
既有協定，而不是繞過它。

### 3.4 放置位置

`database/db_target_guard.py`（新檔）——與 `database/init_db.py`、
`database/schema.sql`、日後的 `database/apply_migrations.py` 同一資料夾，
語意上屬於「資料庫工具層」共用元件，非 UI／ML 程式碼。

### 3.5 known-FAIL 驗證計畫（PO 明確要求，機制本身必須通過）

| 案例 | 建構方式 | 預期結果 |
|------|---------|---------|
| 已知會 FAIL 案例 1 | 合成 `db_config = {"host": "localhost", "port": 5432, "database": "postgres"}`（模擬完全未覆寫的預設狀態，且未設定確認環境變數） | `assert_safe_migration_target` 必須 `raise SystemExit` |
| 已知會 FAIL 案例 2（訊號 A 單獨觸發） | `db_config = {"host": "localhost", "port": 5432, "database": "sb4_test_tmpdb"}`（database 名稱符合慣例，但 host/port 仍是預設值） | 依 §3.3 邏輯（任一訊號觸發即拒絕）**仍應 raise**——需在測試中明確驗證這一步，避免誤植為「兩個訊號都要觸發才擋」 |
| 已知會 FAIL 案例 3（覆寫值錯誤） | 設定 `CONFIRM_REAL_DB_MIGRATION_TARGET=1`（非要求的完整字串），其餘同案例 1 | 仍應 `raise SystemExit`——證明確認機制不會被隨手一個真值意外繞過 |
| 正向案例 1（隔離臨時 DB） | `db_config = {"host": "localhost", "port": 55436, "database": "sb4_test_tmpdb"}`（比照本 Session 既有臨時 DB 慣例） | 正常回傳，不 raise |
| 正向案例 2（真實 DB＋正確覆寫） | 案例 1 的 `db_config`，並正確設定 `CONFIRM_REAL_DB_MIGRATION_TARGET=I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB` | 正常回傳，不 raise——證明刻意覆寫確實可用，機制不會鎖死正當的正式執行 |
| **舊防線失效示範（對照組，證明本機制存在的必要性）** | 假設性重建「沒有本機制」的世界：`apply_migrations.py` 若直接呼叫 `DBWriter()` 未經任何檢查、`.env` 又剛好未覆寫 → 會直接對 `localhost:5432` 執行 DDL，無任何攔截點 | 以程式碼走查（非執行）方式在提案／報告中列出這個對照，說明「加了本機制之後，同一個疏失會在 `assert_safe_migration_target` 這一行被攔下，而不是在 DDL 真正執行後才被人發現」 |

驗收標準：以上 6 項案例**全部**要有實際執行過的原始輸出（`pytest`／`unittest` 輸出
或手動執行的 traceback），不得只用文字描述「應該會擋下」。

### 3.6 階段一的 Definition of Done

1. `database/db_target_guard.py` 已實作，`assert_safe_migration_target()` 可被匯入呼叫。
2. §3.5 六項案例全部執行過並附原始輸出。
3. 全套既有測試（189 個）仍 PASS，未受影響。
4. **本階段獨立向 PO 送審並取得明確核准，才可開始階段二**——不與階段二合併送審。

---

## 4. 階段二（待階段一驗收通過才開工）：Migration 框架本體

沿用 `DB_MIGRATION_PLAN.md` 既有設計（該文件已是 Gate 0 核准交付物，本 SB 不重新
設計，僅執行），並新增一項：`apply_migrations.py` 在建立資料庫連線前**必須**先呼叫
`assert_safe_migration_target(db_config)`，此為階段一產出物與階段二的唯一耦合點。

| 項目 | 內容 |
|------|------|
| Goal | 建立可版本追蹤的 Schema 遷移機制 |
| Proposed Change | 新增 `schema_version` 表 + `database/migrations/` 目錄 + `apply_migrations.py` runner；`001_baseline.sql` 建立版本表 |
| In Scope | Migration 框架；`001_baseline.sql`；版本檢查邏輯；`apply_migrations.py`（含呼叫階段一守門函式） |
| Out of Scope | 實際 `daily_ml_features` 擴充（Gate-2）；`market_articles` 擴充（Gate-2）；導入 Alembic |
| Affected Components | `database/schema.sql`（新增 `schema_version` DDL）、`database/migrations/001_baseline.sql`、`database/apply_migrations.py` |
| Data/API/Schema Contract | `schema_version` 表：`(version INTEGER PK, description TEXT, applied_at TIMESTAMP, checksum TEXT)` |
| Failure Semantics | Migration 在 Transaction 內失敗 → 自動 ROLLBACK；版本不符 → 拒絕執行並回報；runner 回傳 non-zero exit code；**新增**：`assert_safe_migration_target` 判定疑似真實 DB 且未確認 → 在連線建立前即以 `SystemExit` 中止，不進入 Transaction |
| Risks & Trade-offs | 沿用 `DB_MIGRATION_PLAN.md` §6 既有 8 項安全保證；輕量 Script 方案未來可能需要升級為 Alembic（>10 migrations 時評估） |
| Tests | `test_migration_idempotency`、`test_version_check`、`test_rollback_on_failure`、`test_runner_nonzero_exit_on_error`（既有四項，Master Plan Brief 原定） |
| E2E Verification | 隔離 PostgreSQL 18 容器：1) fresh init + apply → `schema_version` 存在；2) 二次 apply → 冪等；3) 故意失敗 → rollback；4) **新增**：以真實 DB 座標（`localhost:5432`）但不設定確認變數執行 → 於連線前即被拒絕，不建立任何連線 |
| Documentation Sync | SDD 資料庫章節；`DECISIONS.md`（DEC-010）；`DB_MIGRATION_PLAN.md` |
| Rollback | 見 `DB_MIGRATION_PLAN.md` §7 分層 Rollback 策略；程式碼回滾：`git revert` |
| Definition of Done | `schema_version` 表存在；`apply_migrations.py` 可冪等執行；全套測試 PASS；`apply_migrations.py` 在無確認變數時對真實 DB 座標的執行會被階段一機制攔下（E2E 驗證項 4） |

---

## 5. 範圍邊界（本 SB 不做什麼）

- 不修改 `daily_ml_features`／`market_articles` 的實際欄位擴充（屬 Gate 2）。
- 不導入 Alembic 或其他第三方 migration 框架。
- 不對已存在的 `database/schema.sql`／`database/init_db.py` 既有邏輯做非必要重構。
- 階段一的守門函式**不**嘗試偵測所有可能的「真實 DB」情境（例如透過 SSH tunnel
  轉發、非本專案慣例的埠號選擇）——設計目標是攔住「忘記覆寫環境變數」這個
  RISK-013 明文指出的**具體**觸發條件，不是通用的資料庫身分識別系統。
  若未來出現本機制無法涵蓋的新情境，屬另一個風險項目，不在本 SB 補強範圍內。

## 6. 文件同步範圍

- `doc/evidence/DECISIONS.md`：新增 ADR 記錄 RISK-013 根本解的設計決策（階段一驗收後撰寫）。
- `doc/upgrade/contracts/REMAINING_RISKS.md`：RISK-013 狀態由 `Mitigate` 更新為根本解已落地
  （階段一驗收後）。
- `doc/upgrade/contracts/DB_MIGRATION_PLAN.md`：§6 安全保證新增第 9 項（連線目標守門檢查）。
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`：資料庫章節同步（階段二完成後）。

---

## 7. 請求 PO 裁決

1. **§3.2 偵測訊號設計**：host/port 預設值比對 + database 名稱慣例比對，兩者任一觸發即判定
   疑似真實 DB，是否同意此設計？是否需要納入第三個訊號（例如您先前提到的 postgres-data
   掛載偵測——本提案 §2.1 已說明技術上難以從應用程式容器內可靠偵測 db 服務的掛載狀態，
   故未採用，但若您認為仍需補強，請指示方向）？
2. **§3.3 覆寫機制**：環境變數 `CONFIRM_REAL_DB_MIGRATION_TARGET` 需設為完整句子而非
   簡單真值，是否同意？
3. **§3.6 兩階段分開送審**：階段一（守門函式）獨立完成、驗收、送審，取得核准後才開始
   階段二（migration 框架本體）——是否同意這個分階段方式，或您希望階段一驗收後直接
   併入同一份 Gate B 文件（比照 SB3 的 PO 裁決模式）？
4. 是否核准開始階段一的實作？

裁決後才會開始動 `database/`。
