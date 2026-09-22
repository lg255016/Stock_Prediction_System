# UG-G1-SB4 階段二 Gate B 送審文件：Migration 框架本體（`schema_version`／`apply_migrations.py`）

> **性質**：`gate-submit` skill 六項強制產出的整合文件。**不是** commit 授權本身——
> commit 授權留待 PO 讀完本文件後另行決定。本次未執行 `git add`／`git commit`。
> **提交日期**：2026-08-26
> **前置**：UG-G1-SB4 階段一（`database/db_target_guard.py`，DEC-021）已於
> 2026-08-26 CLOSED（commit `d2a4d4894328d2ef5e186aa2aa45ec02a0fdea0b`）。
> **狀態**：`database/schema.sql` 新增 `schema_version` DDL、`database/migrations/
> 001_baseline.sql`、`database/apply_migrations.py`、`tests/test_apply_migrations.py`
> 已完成並通過隔離容器完整 E2E 驗證（含 PO 新增之第 4 項）；本次是本專案**第一次
> 真正對資料庫執行 DDL**（於隔離臨時 DB 上），已比照 SB1～SB3 慣例使用獨立容器、
> 不掛 `postgres-data`、事前呈報綁定確認。

---

## 0. 提交前回顧

| 項目 | 內容 | 完成日期 |
|------|------|---------|
| 階段一 | RISK-013 根本解，CLOSED，commit `d2a4d48` | 2026-08-26 |
| PO 裁決 | 核准開始階段二；提醒 `apply_migrations.py` 建立連線前須先呼叫 `assert_safe_migration_target()`，此為唯一耦合點；要求案例 6 這次補上（對隔離臨時 DB，非真實 DB）；要求隔離機制比照 SB1～SB3 慣例，不能省 | 2026-08-26 |
| 實作 | `database/schema.sql`（新增 `schema_version` DDL）、`database/migrations/001_baseline.sql`、`database/apply_migrations.py`（連線前強制呼叫階段一守門函式） | 2026-08-26 |
| 隔離容器 E2E 驗證 | 獨立容器 `sb4_migration_tmpdb`（port 55440，非 `postgres-data` 掛載）；bind 確認、fresh init+apply、冪等性、版本檢查、故意失敗遷移的 rollback、真實 DB 座標未確認即被拒絕（PO 新增第 4 項）、known-FAIL 案例 6 對照補上；驗證後已 `docker rm -f -v` 拆除 | 2026-08-26 |
| 隔離單元測試 | `tests/test_apply_migrations.py`（6 個 mock 測試，不連真實 DB） | 2026-08-26 |
| 修正 | 實作過程中發現 `checksum` 欄位設計缺陷（每個核准的遷移檔案內容本身自帶 `INSERT ... ON CONFLICT DO NOTHING`，導致 runner 端原設計的 INSERT 永遠被擋下、checksum 永遠是 NULL），改為 UPDATE 修正 | 2026-08-26 |
| §7 文件同步 | `DECISIONS.md`：DEC-010 Verification 補齊（打勾+新增實作細節說明）、新增 DEC-021（RISK-013 根本解 ADR，補齊階段一未及時撰寫的文件同步）；`DB_MIGRATION_PLAN.md`：§5 新增守門步驟與 checksum 設計說明、§6 新增第 9 項安全保證；`REMAINING_RISKS.md`：RISK-013 標記根本解已落地、RISK-006 標記部分驗證；`SDD`：新增「Schema Migration Boundary」章節；`TRACEABILITY.md`：新增 DEC-021／DEC-010 兩列；`SYSTEM_UPGRADE_MASTER_PLAN.md`：SB4 Gate A/B 狀態列更新；`PROJECT_STATUS.md`：SB4 進度、義務 #1 標記已解決 | 2026-08-26 |
| 步驟 6 | 本文件（階段二 Gate B 送審） | 2026-08-26 |

**一個附帶發現並修正的文件債**：階段一 Gate A 提案 §6 承諾「RISK-013 根本解的 ADR
於階段一驗收後撰寫」，但實際在階段一 commit（`d2a4d48`）後未及時補上，直到本次
準備階段二文件同步時才發現並補齊（即 DEC-021）。已一併記錄於 DEC-010 的
Verification 補充說明中，不隱瞞這個延遲。

---

## 1. 完整 Diff

**檔案清單**（8 modified + 3 new，458 insertions(+), 16 deletions(-)）：

```
 database/schema.sql                           |  15 ++
 doc/evidence/DECISIONS.md                     | 120 +++++++++++++++++++++--
 doc/evidence/TRACEABILITY.md                  |   2 +
 doc/governance/PROJECT_STATUS.md              |   8 +-
 doc/spec/SDD_Financial_Sentiment_System_v1.md |  26 +++++
 doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md     |   4 +-
 doc/upgrade/contracts/DB_MIGRATION_PLAN.md    |  20 +++-
 doc/upgrade/contracts/REMAINING_RISKS.md      |   4 +-
 database/apply_migrations.py                  | 144 ++++++++++++++++++++++++
 database/migrations/001_baseline.sql          |  15 ++
 tests/test_apply_migrations.py                | 116 +++++++++++++++++++
 11 files changed, 458 insertions(+), 16 deletions(-)
```

**重跑指令**（修改檔案）：`git diff -- database/schema.sql doc/evidence/DECISIONS.md doc/evidence/TRACEABILITY.md doc/governance/PROJECT_STATUS.md doc/spec/SDD_Financial_Sentiment_System_v1.md doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md doc/upgrade/contracts/DB_MIGRATION_PLAN.md doc/upgrade/contracts/REMAINING_RISKS.md`
（新檔部分需先 `git add -N database/apply_migrations.py database/migrations/001_baseline.sql tests/test_apply_migrations.py` 才能以 `git diff` 重現，執行後已 `git reset` 還原為未追蹤狀態）

<details>
<summary>完整 diff 內容（點擊展開）</summary>

```diff
diff --git a/database/schema.sql b/database/schema.sql
index a84b960..c585441 100644
--- a/database/schema.sql
+++ b/database/schema.sql
@@ -104,6 +104,21 @@ CREATE TABLE IF NOT EXISTS daily_ml_features (
 );
 
 
+-- ----------------------------------------------------------------------------
+-- [5. Migration 版本追蹤 (Schema Version Tracking)]
+-- UG-G1-SB4：供 database/apply_migrations.py 判斷目前已套用至哪個版本；
+-- 與 database/migrations/001_baseline.sql 定義相同，供全新初始化時直接建立。
+-- ----------------------------------------------------------------------------
+
+-- 5.1 Schema 版本表：記錄每個已套用遷移的版本號、描述、時間與內容雜湊
+CREATE TABLE IF NOT EXISTS schema_version (
+    version     INTEGER PRIMARY KEY,
+    description TEXT NOT NULL,
+    applied_at  TIMESTAMP DEFAULT NOW(),
+    checksum    TEXT
+);
+
+
 -- ============================================================================
 -- [附錄：初始設定資料 (Seed Data)]
 -- 在資料庫建立時，預設塞入的核心追蹤名單與映射規則。
diff --git a/doc/evidence/DECISIONS.md b/doc/evidence/DECISIONS.md
index 65f5bf7..b00d115 100644
--- a/doc/evidence/DECISIONS.md
+++ b/doc/evidence/DECISIONS.md
@@ -824,19 +824,39 @@ VERIFIED THIS SESSION — Phase 3 (P3-SB1 ~ P3-SB4) 全套實作與 113 項自
 
 ### Verification（驗證）
 
-- [ ] 隔離 PostgreSQL 18 容器驗證 3 個 Migration 序列
-- [ ] 冪等測試（二次執行無副作用）
-- [ ] 失敗回滾測試
-- [ ] 開發資料不受影響
+- [x] 隔離 PostgreSQL 18 容器驗證 Migration 序列（2026-08-26，`sb4_migration_tmpdb`，
+      port 55440，非 `postgres-data` 掛載，已拆除）——**目前僅 001_baseline.sql 一個
+      遷移腳本**（002/003 屬 Gate 2/3 範圍，尚未實作），原構想的「3 個 Migration」
+      驗證將隨 Gate 2/3 各自的 SB 逐步補齊
+- [x] 冪等測試（二次執行顯示「無待執行遷移，已是最新版本」，無副作用）
+- [x] 失敗回滾測試（故意失敗遷移確認 ROLLBACK，`schema_version` 版本未推進）
+- [x] 開發資料不受影響（全程僅對隔離臨時 DB 操作，未連接真實開發 DB）
+
+**UG-G1-SB4 實作階段發現並補上的細節（原 ADR 文字未涵蓋）**：
+
+1. **RISK-013 根本解整合**：`apply_migrations.py` 在建立資料庫連線前，
+   強制呼叫 `database/db_target_guard.py` 的 `assert_safe_migration_target()`——
+   詳見 DEC-021。這是本 ADR 核准時（Gate 0，2026-08-22）尚未存在的風險項目
+   （RISK-013 於 2026-08-24 才由 PO 追加），故原文未提及，屬後續 Gate 1 SB
+   對本決策的必要補強，不代表原決策本身有誤。
+2. **checksum 欄位的實際寫入方式**：`001_baseline.sql`（與 `DB_MIGRATION_PLAN.md`
+   §4.2／§4.3 規劃的 002／003）皆在遷移腳本自身內嵌 `INSERT INTO schema_version
+   ... ON CONFLICT (version) DO NOTHING`（不含 checksum）。若 runner 端也用 INSERT
+   寫入 checksum，會被前述自我登記的 `ON CONFLICT` 擋下而永遠寫不進去。
+   `apply_migrations.py` 改用 `UPDATE schema_version SET checksum = ... WHERE
+   version = ...`，確保 checksum 不論遷移腳本是否自行登記都能正確補上。
 
 ### Remaining Risks（剩餘風險）
 
 - 手動 SQL 可能引入錯誤 → 隔離容器驗證緩解。
 - Migration 無法自動回退 → 分層策略 + pg_dump 緩解。
+- 目前僅驗證 001_baseline.sql 單一遷移；002/003（Gate 2/3）尚未實作，
+  多遷移序列的真實互動（例如遷移間的相依性、跨版本冪等性）尚待該等 SB 驗證。
 
 ### 證據文件
 
-`doc/upgrade/contracts/DB_MIGRATION_PLAN.md`
+`doc/upgrade/contracts/DB_MIGRATION_PLAN.md`；`doc/upgrade/gates/SB4_GATE_A_PROPOSAL.md`；
+`doc/upgrade/gates/SB4_STEP2_GATE_B_SUBMISSION.md`
 
 ---
 
@@ -1381,10 +1401,98 @@ PO 決定本次不真正執行該腳本**——目前可用歷史資料量不足
 
 - 真實 artifact 產出後，DRIFT-018 矛盾 (2)（lightgbm/xgboost 同分）是否真的消失，
   仍待實測確認，本次僅為理論推斷（container 內兩者為不同真實實作）。
-- `scripts/generate_tournament_artifact.py` 从未在真實 DB 上執行過，其 Panel 大小／
+- `scripts/generate_tournament_artifact.py` 從未在真實 DB 上執行過，其 Panel 大小／
   唯一交易日數等實際數字未知，執行時是否仍會被 `check_sufficient_data` 擋下待實測。
 
 ### 證據文件
 
 `doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md`；`doc/upgrade/gates/SB3_GATE_B_SUBMISSION.md`
 
+
+## DEC-021：RISK-013 根本解——`database/db_target_guard.py`
+
+- 日期：2026-08-26
+- 狀態：`APPROVED`（PO 於 SB4 階段一 Gate B 送審文件複查後核准，2026-08-26，commit `d2a4d48`）
+- 觸發 Gate：UG-G1-SB4（階段一，DEC-010 的必要前置條件）
+
+### Context（背景）
+
+RISK-013（`REMAINING_RISKS.md`，PO 2026-08-24 簽核）指出：驗證／測試腳本可在未覆寫
+`DB_HOST`／`DB_PORT` 時直連真實開發資料庫。既有緩解（呈報綁定確認的回報紀律）
+是流程紀律，不是技術護欄——依賴執行者記得覆寫環境變數、記得先呈報。SB1～SB3
+全部是唯讀路徑，此風險可承受；SB4 是本專案第一個寫入路徑（DDL migration）的 SB，
+同一種疏失的後果從「讀了不該讀的」質變為「對真實開發資料庫執行 DDL」，且無法
+事後補救。PO 明確要求：根本解必須在 SB4 動任何 migration 邏輯之前落地，並作為
+獨立於 DEC-010（migration 框架本體）的優先步驟。
+
+### Problem（問題）
+
+需要一個不依賴「記得做」的技術機制，在偵測到連線目標疑似真實開發 DB 時，
+於建立連線前自動拒絕執行。
+
+### Alternatives Considered（考慮方案）
+
+`SB4_GATE_A_PROPOSAL.md` §3.2：
+
+- **訊號 A**：host/port 是否為 `.env.example` 未覆寫的預設值（`localhost:5432`）。
+- **訊號 B**：database 名稱是否符合本專案臨時 DB 的命名慣例（含 `tmp`／`temp`／`test`）。
+- **曾考慮但未採用之第三訊號**：偵測 `postgres-data` 是否被 bind mount。
+  技術上不可靠而放棄——`apply_migrations.py` 執行於 app 容器內，與 db 為獨立容器
+  命名空間，在不取得 docker socket 存取權（本身是更大的風險）的前提下，
+  無法從應用程式容器內部可靠查詢另一個容器的 volume 掛載型態。PO 核准前
+  親自查核 SB1～SB3 已結案文件裡實際使用過的臨時 DB 埠號（55433～55436）與
+  命名（皆含 `tmp`），確認訊號 A／B 與既有慣例完全吻合，同意不需第三訊號。
+
+### Decision（決策）
+
+新增 `database/db_target_guard.py`，核心函式 `assert_safe_migration_target(db_config)`：
+訊號 A 或訊號 B **任一**觸發，即判定「疑似真實 DB」，除非呼叫端已透過環境變數
+`CONFIRM_REAL_DB_MIGRATION_TARGET` 提供完整確認句（`I_UNDERSTAND_THIS_WRITES_TO_
+THE_REAL_DEV_DB`，刻意要求完整句子而非 `1`／`true` 等簡單真值），否則
+`raise SystemExit`，不執行任何連線動作。本機制**不取代**既有的「呈報綁定確認」
+流程紀律，兩者疊加：流程紀律要求執行前先給 PO 看；技術護欄保證就算流程紀律
+這次失守，程式本身仍會在觸及疑似真實 DB 時自動停下。
+
+`database/apply_migrations.py`（DEC-010 的實作）在建立資料庫連線前，
+**強制**呼叫本函式——這是階段一與階段二產出物的唯一耦合點。
+
+### Rationale（理由）
+
+正向表列（要求臨時 DB 使用可辨識命名）優於嘗試「證明這是真實 DB」（後者需要
+硬編碼真實 DB 名稱等機敏設定，不應出現在程式碼中）。兩個訊號分別覆蓋兩種
+獨立的疏失來源：忘記覆寫連線座標、忘記為臨時 DB 命名，任一遺漏都會被攔下。
+
+### Trade-offs（取捨）
+
+- 機制依賴呼叫端「記得呼叫」`assert_safe_migration_target()`，與 RISK-013
+  原本的問題是同一種「依賴記得做」，只是往上移了一層——**PO 已記錄此觀察，
+  本次不要求改設計**；若未來 Gate 2／3 出現新的 DB 寫入路徑，屆時將評估是否
+  讓 `DBWriter` 的寫入方法自動呼叫本函式。
+- 訊號 A／B 皆為啟發式判斷，非密碼學等級的身分驗證；刻意選擇與本專案既有
+  慣例強耦合的簡單規則，而非通用的資料庫身分識別系統。
+
+### Affected Components（影響範圍）
+
+`database/db_target_guard.py`（新檔）、`database/apply_migrations.py`
+（唯一呼叫端）、`tests/test_db_target_guard.py`
+
+### Verification（驗證）
+
+- [x] 5 個可執行案例（3 known-FAIL + 2 正向）皆已執行並取得原始輸出
+      （`SB4_STEP1_GATE_B_SUBMISSION.md` §7）
+- [x] 第 6 個對照案例（舊防線失效示範）已於階段二補上：構造移除本函式呼叫的
+      臨時版本，對隔離臨時 DB（`sb4_migration_tmpdb`，非真實 DB）執行，
+      證實無保護時腳本會直接連線成功，無任何攔截點
+      （`SB4_STEP2_GATE_B_SUBMISSION.md` §7）
+- [x] `apply_migrations.py` 以真實 DB 座標（未覆寫環境變數）執行，於連線前
+      即被拒絕，未建立任何連線（`SB4_STEP2_GATE_B_SUBMISSION.md` E2E 驗證項 4）
+
+### Remaining Risks（剩餘風險）
+
+- 見 Trade-offs：機制本身仍依賴呼叫端記得呼叫，非強制耦合於 `DBWriter` 寫入路徑本身。
+
+### 證據文件
+
+`doc/upgrade/gates/SB4_GATE_A_PROPOSAL.md` §3；`doc/upgrade/gates/SB4_STEP1_GATE_B_SUBMISSION.md`；
+`doc/upgrade/gates/SB4_STEP2_GATE_B_SUBMISSION.md`
+
diff --git a/doc/evidence/TRACEABILITY.md b/doc/evidence/TRACEABILITY.md
index 5e44bea..fc4eace 100644
--- a/doc/evidence/TRACEABILITY.md
+++ b/doc/evidence/TRACEABILITY.md
@@ -59,6 +59,8 @@
 | **三重查詢真實文章與空狀態透明化** | 輿情明細透明化 (SB-ART1~3) | 4.1 輿情明細架構 | **DEC-008** / REAL-ART | `src/ui/data_loader.py`<br>`src/ui/components.py` | `tests/test_real_articles_pipeline.py` | 4 tests | `VERIFIED THIS SESSION` (Real Articles) |
 | **UI 四狀態資料來源透明化（REAL/DEMO/EMPTY/ERROR）** | 稽核報告 §2；AGENTS.md §10；DRIFT-009 | 7.1 UI Demo/Real 模式分離 | **DEC-012**（UG-G1-SB2） | `src/ui/data_loader.py`（`DataMode`／`DataSourceError`）<br>`src/ui/components.py`（`render_data_mode_banner`）<br>`src/ui/charts.py`（佔位圖／浮水印）<br>`app.py`（mode 分流與全域追蹤） | `tests/test_ui_contracts.py`<br>`tests/test_operational_ux.py`<br>`tests/test_real_articles_pipeline.py`<br>`tests/schema_smoke_ui_data_loader.py`（不進正式套件） | 9 個新增測試 + 4 個 schema smoke test | `VERIFIED THIS SESSION`（`SB2_STEP3_IMPLEMENTATION_REPORT.md`；173/173 PASS；HERM runtime 攔截數 9→0；`src/` 尚未 commit） |
 | **模型競技排行榜動態化（Artifact-Driven Leaderboard）** | 稽核報告 §2；DRIFT-008；DRIFT-018 | 7.1 UI 排行榜動態化 | **DEC-020**（UG-G1-SB3） | `src/ui/data_loader.py`（`load_tournament_results`／`_stringify_date_columns`）<br>`src/ui/components.py`（`render_tournament_leaderboard(data, mode)`）<br>`app.py`（呼叫處解包）<br>`scripts/generate_tournament_artifact.py`（新檔，未執行） | `tests/test_ui_contracts.py`<br>`tests/test_time_series_split.py`（`label_end_date` 型別回歸）<br>`tests/test_generate_tournament_artifact.py`（資料量防線） | 9 個讀取/渲染測試 + 3 個型別回歸測試 + 4 個防線測試 | `VERIFIED THIS SESSION`（`SB3_GATE_B_SUBMISSION.md`；189/189 PASS；真實 artifact 尚未產出，`NOT VERIFIED`——見該文件 §6；`src/` 尚未 commit） |
+| **RISK-013 根本解（DB 連線目標守門）** | RISK-013（PO 2026-08-24 簽核）；PO 2026-08-26 裁示須為 SB4 第一步驟 | 不適用（風險緩解機制，非產品需求章節） | **DEC-021**（UG-G1-SB4 階段一） | `database/db_target_guard.py`（`assert_safe_migration_target`） | `tests/test_db_target_guard.py` | 5 個案例（3 known-FAIL + 2 正向） | `VERIFIED THIS SESSION`（`SB4_STEP1_GATE_B_SUBMISSION.md`；194/194 PASS；commit `d2a4d48`） |
+| **Schema Version & Migration 機制（Additive DDL + Runner）** | 稽核報告 §4；AGENTS.md §7.1；DRIFT-011；`DB_MIGRATION_PLAN.md` | 資料庫章節 | **DEC-010**（UG-G1-SB4 階段二） | `database/schema.sql`（新增 `schema_version` DDL）<br>`database/migrations/001_baseline.sql`<br>`database/apply_migrations.py`（強制呼叫 `assert_safe_migration_target`） | `tests/test_apply_migrations.py` | 6 個 mock 單元測試 + 4 項 E2E 隔離容器驗證（含新增第 4 項：真實 DB 座標未確認即被拒絕） | `VERIFIED THIS SESSION`（`SB4_STEP2_GATE_B_SUBMISSION.md`；隔離容器 `sb4_migration_tmpdb`，非 `postgres-data` 掛載，已拆除；`src/`／`database/` 變更尚未 commit） |
 | **總計 (Total)** | - | - | **9 大核心 ADR + 7 大挑戰** | **18 大核心生產模組** | **17 大測試套件檔案** | **154 項測試** | **100% PASS (~1.80s)** |
 
 ---
diff --git a/doc/governance/PROJECT_STATUS.md b/doc/governance/PROJECT_STATUS.md
index 9381265..d3b82ef 100644
--- a/doc/governance/PROJECT_STATUS.md
+++ b/doc/governance/PROJECT_STATUS.md
@@ -36,15 +36,17 @@
 | └ **UG-G1-SB1** Purged Walk-Forward | **CLOSED**（2026-08-25 PO 核准結案） | commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`；證據見 `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_STEP4_AFTER_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_GATE_B_SUBMISSION.md`；DEC-011、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-012）已同步 |
 | └ **UG-G1-SB2** UI Demo/Real 模式分離 | **CLOSED**（2026-08-25 PO 核准結案；DEC-012 方案 B 裁決） | commit `414fcc81fccde57d84e883b4a44a9b0e50465500`；證據見 `doc/upgrade/gates/closed/SB2_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB2_STEP3_IMPLEMENTATION_REPORT.md`、`doc/upgrade/gates/closed/SB2_STEP0_4_5_RECORD.md`、`doc/upgrade/gates/closed/SB2_GATE_B_SUBMISSION.md`；DEC-012、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-009／HERM-A/B/C/E）已同步；過程中發現並修復 ERROR 模式 `StreamlitDuplicateElementId` 當機 bug |
 | └ **UG-G1-SB3** 模型競技排行榜動態化 | **CLOSED**（2026-08-26 PO 核准結案；方案 B + 4 項附帶裁決，DEC-020 `APPROVED`） | commit `61016ee19c07caec990b51563f21b7f6571412b9`；證據見 `doc/upgrade/gates/closed/SB3_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB3_GATE_B_SUBMISSION.md`；DEC-020、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-008／DRIFT-018 歸屬修正）、SDD UI 章節已同步；真實 artifact 因資料量不足暫未產出（`load_tournament_results()` 正確顯示 `EMPTY`）；過程中發現並修復兩個既有缺陷（`label_end_date`／`trade_date` 型別不一致、資料量防線設計缺陷） |
+| └ **UG-G1-SB4** DB Migration 機制（含 RISK-013 根本解） | Gate A 已核准（兩階段拆分）；**階段一 CLOSED**（2026-08-26，commit `d2a4d4894328d2ef5e186aa2aa45ec02a0fdea0b`，DEC-021 `APPROVED`）；**階段二已實作並完成隔離容器 E2E 驗證，送審中，尚未 commit** | `doc/upgrade/gates/SB4_GATE_A_PROPOSAL.md`、`SB4_STEP1_GATE_B_SUBMISSION.md`、`SB4_STEP2_GATE_B_SUBMISSION.md`；DEC-010（Verification 補齊）、DEC-021、`TRACEABILITY.md` 已同步；`database/`、`tests/` 變更待 commit |
 
 RISK-001 `Accept`、RISK-010 `Defer`（至 Gate 3）、RISK-012 `Mitigate`、
-RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RISKS.md`。
+RISK-013 **根本解已落地**（2026-08-26，`db_target_guard.py`，commit `d2a4d48`）——見
+`doc/upgrade/contracts/REMAINING_RISKS.md`。
 
 ### 0.3 明確未授權項目
 
 | 項目 | 狀態 |
 |------|------|
-| **UG-G1-SB4 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權（SB1～SB3 已 CLOSED，見 §0.2；SB4 Gate A 提案撰寫中，未動 `src/`） |
+| **UG-G1-SB5** | **未授權**。Gate 1 採逐 SB 授權（SB1～SB3 已 CLOSED；SB4 Gate A 已核准，階段一 CLOSED，階段二送審中，見 §0.2） |
 | **UG-Gate-2、UG-Gate-3、UG-Gate-4** | **未核准，不得啟動** |
 | `database/` | 升級專案至今**一行未改** |
 
@@ -66,7 +68,7 @@ grep -ch "def test_" tests/*.py | awk '{s+=$1} END {print s}'
 
 | # | 義務 | 期限／歸屬 |
 |---|------|-----------|
-| 1 | **RISK-013 根本解**：「驗證腳本在偵測到指向真實 DB 時拒絕執行」 | **必須在 UG-G1-SB4（DB Migration 機制）之前落地。** 至今所有暴露皆為唯讀路徑，漏設 `DB_HOST` 的後果可回復；SB4 屬**寫入路徑**，同一次漏設會對真實開發資料庫執行 DDL —— 回報紀律擋不住 |
+| 1 | ~~**RISK-013 根本解**：「驗證腳本在偵測到指向真實 DB 時拒絕執行」~~ | **已解決（2026-08-26，UG-G1-SB4 階段一，commit `d2a4d48`，DEC-021）**：`database/db_target_guard.py` 的 `assert_safe_migration_target()`，`apply_migrations.py` 建立連線前強制呼叫。已實測：以真實 DB 座標未確認執行 → 連線前即被拒絕。剩餘缺口（機制依賴呼叫端主動呼叫，未強制耦合於 `DBWriter` 寫入方法本身）已記錄於 DEC-021 Trade-offs，PO 同意本次不要求改設計 |
 | 2 | GOV-04 三項補件（hook 檔頭、檢查目標不一致、§11A 規則化） | 已完成，隨 GOV-06 落盤 |
 | 3 | DRIFT-018：`src/ui/components.py` 排行榜八個寫死數值 | UG-G1-SB2。標註為「**未經驗證的展示值，證據待補**」，**不得**標為「含洩漏」—— 後者預設它們是有已知瑕疵的真實量測，而無證據顯示曾被量測過 |
 | 4 | ~~`doc/upgrade/gates/closed/` 缺 `.gitkeep`~~ | **已解決（2026-08-25，隨 SB2 結案一併處理）**：義務 7 的搬移已執行，`closed/` 現含 8 份檔案，git 因非空目錄自然追蹤，`.gitkeep` 已無必要 |
diff --git a/doc/spec/SDD_Financial_Sentiment_System_v1.md b/doc/spec/SDD_Financial_Sentiment_System_v1.md
index 911df13..f648ed3 100644
--- a/doc/spec/SDD_Financial_Sentiment_System_v1.md
+++ b/doc/spec/SDD_Financial_Sentiment_System_v1.md
@@ -102,6 +102,32 @@ Bootstrap seed 只服務新資料庫的預設設定。`tracking_keywords` 與 `e
 
 Gate 1 已在隔離 PostgreSQL 18 環境驗證 fresh initialization、第二次重跑、runtime configuration preservation、Schema Fingerprint stability、failure exit semantics 與 transaction rollback。這些證據不代表 existing database migration safety 或 production readiness。
 
+### Schema Migration Boundary（資料庫遷移邊界，UG-G1-SB4）
+
+上一節的缺口——existing schema upgrade——由 `database/apply_migrations.py`（DEC-010）
+填補，與 `init_db.py` 職責分離、互不取代：
+
+- `schema_version` 表（`database/schema.sql` 與 `database/migrations/001_baseline.sql`
+  皆定義，全新建庫與既有升級路徑各自涵蓋）追蹤已套用的遷移版本、描述、時間與內容
+  SHA-256 雜湊（`checksum`，供事後竄改偵測）。
+- `apply_migrations.py` 掃描 `database/migrations/` 目錄，依檔名編號嚴格排序，
+  僅套用版本號大於目前已套用版本的遷移，每個遷移在獨立 Transaction 內執行，
+  失敗時自動 ROLLBACK 且版本不推進。
+- **RISK-013 根本解整合（DEC-021）**：建立資料庫連線前，`apply_migrations.py`
+  強制呼叫 `database/db_target_guard.py` 的 `assert_safe_migration_target()`——
+  偵測到連線目標疑似為真實開發 DB（host/port 為未覆寫預設值，或 database 名稱
+  不符臨時 DB 命名慣例）時，於連線建立前即 `raise SystemExit`，不執行任何連線
+  或寫入動作。
+
+**驗證邊界**：截至 UG-G1-SB4，僅 `001_baseline.sql`（建立 `schema_version` 表本身）
+一個遷移腳本已實作並於隔離容器（非 `postgres-data` 掛載）驗證 fresh apply、
+冪等重跑、版本檢查、故意失敗遷移的 rollback，以及以真實 DB 座標執行時連線前
+即被拒絕。`002_expand_ml_features.sql`／`003_expand_articles.sql`（`DB_MIGRATION_PLAN.md`
+§4.2／§4.3 已規劃）屬 Gate 2／3 範圍，尚未實作；多遷移序列間的實際互動
+（例如遷移間相依性）尚待該等 Gate 各自的 SB 驗證。分層 Rollback 策略第 5 層
+（`pg_dump` 完整還原，需 PO 核准）本次未觸發，因全程僅對隔離臨時 DB 操作，
+未曾對真實開發 DB 執行過 migration。
+
 ### Runtime Read & NLP Completion Boundary（執行期讀取與 NLP 完成邊界）
 
 Gate 2 採用 DEC-003 的 DB read、cache 與 strict fuzzy completion contracts。
diff --git a/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md b/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
index 6d036ce..83c4489 100644
--- a/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
+++ b/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
@@ -577,8 +577,8 @@ UG-Gate-4 (XAI, Export & UI) — 5 SBs
 | Documentation Sync | SDD 資料庫章節; DECISIONS.md (DEC-010); DB_MIGRATION_PLAN.md |
 | Rollback | 見 §12.4 分層 Rollback 策略; 程式碼回滾: git revert |
 | Definition of Done | schema_version 表存在; apply_migrations.py 可冪等執行; 全套測試 PASS |
-| Gate A | PO 審查計畫 |
-| Gate B | PO 授權 Commit |
+| Gate A | PO 審查計畫 —— **已核准（2026-08-26，兩階段拆分：RISK-013 根本解優先於 migration 框架本體，DEC-021／DEC-010）** |
+| Gate B | PO 授權 Commit —— **階段一已完成，CLOSED（2026-08-26）**，commit `d2a4d4894328d2ef5e186aa2aa45ec02a0fdea0b`（`database/db_target_guard.py`）；**階段二**（`schema_version` 表、`database/migrations/001_baseline.sql`、`database/apply_migrations.py`）已實作並完成隔離容器 E2E 驗證，送審中，尚未 commit——證據見 `SB4_STEP1_GATE_B_SUBMISSION.md`、`SB4_STEP2_GATE_B_SUBMISSION.md` |
 
 #### UG-G1-SB5: 文件全面校正
 
diff --git a/doc/upgrade/contracts/DB_MIGRATION_PLAN.md b/doc/upgrade/contracts/DB_MIGRATION_PLAN.md
index a18c922..871a00c 100644
--- a/doc/upgrade/contracts/DB_MIGRATION_PLAN.md
+++ b/doc/upgrade/contracts/DB_MIGRATION_PLAN.md
@@ -298,6 +298,8 @@ ON CONFLICT (version) DO NOTHING;
 ### 5.1 核心邏輯
 
 ```
+0. （UG-G1-SB4 階段一新增）assert_safe_migration_target()：偵測連線目標是否疑似
+   真實開發 DB，未提供明確覆寫確認時直接拒絕，不進入步驟 1
 1. 連線資料庫
 2. 檢查 schema_version 表是否存在
    - 不存在 → 目前版本為 0
@@ -307,21 +309,32 @@ ON CONFLICT (version) DO NOTHING;
 5. 依序對每個腳本：
    a. BEGIN TRANSACTION
    b. 執行 SQL 內容
-   c. COMMIT
-   d. 若失敗 → ROLLBACK，停止執行，回報錯誤
+   c. UPDATE schema_version SET checksum = ... WHERE version = ...
+   d. COMMIT
+   e. 若失敗 → ROLLBACK，停止執行，回報錯誤
 6. 輸出執行結果摘要
 ```
 
+**實作階段發現的細節（步驟 5c 為何是 UPDATE 而非 INSERT）**：§4 的每個遷移檔案
+（`001_baseline.sql`、`002_expand_ml_features.sql`、`003_expand_articles.sql`）
+內容本身皆已內嵌 `INSERT INTO schema_version (version, description) VALUES (...)
+ON CONFLICT (version) DO NOTHING`（不含 checksum）——這是遷移檔案自我登記版本號的
+既定設計，早於 runner 執行前就已寫入該列。若 runner 也用 INSERT 補 checksum，
+會被這個既有列的 `ON CONFLICT` 擋下而永遠寫不進去。改用 UPDATE 後，不論該列是
+由遷移檔案自行建立或尚不存在，皆能正確補上 `checksum`。
+
 ### 5.2 設計原則
 
 - **冪等性**：每個遷移使用 `IF NOT EXISTS` 與 `ON CONFLICT DO NOTHING`，重複執行不會出錯。
 - **原子性**：每個遷移在獨立事務中執行，失敗時自動 ROLLBACK。
 - **順序性**：嚴格按檔名編號順序執行，不可跳號。
+- **連線前守門**：見步驟 0；`database/db_target_guard.py`（DEC-021）為本 runner
+  與外部連線之間的唯一必經檢查點。
 - **安全性**：不執行已套用的版本（版本號已存在於 `schema_version`）。
 
 ---
 
-## 6. Safety Guarantees（8 項安全保證）
+## 6. Safety Guarantees（9 項安全保證）
 
 | # | 保證項目 | 說明 |
 |---|---------|------|
@@ -333,6 +346,7 @@ ON CONFLICT (version) DO NOTHING;
 | 6 | **先在隔離 PostgreSQL 18 容器中驗證** | 正式執行前必須通過隔離環境測試 |
 | 7 | **絕不修改/刪除/破壞 `.devcontainer/postgres-data/`** | 開發資料受到最高保護 |
 | 8 | **`schema_version` 表永不 DROP** | 版本追蹤表是不可回滾的永久基礎設施 |
+| 9 | **連線目標守門檢查（UG-G1-SB4 階段一，DEC-021）** | `apply_migrations.py` 建立連線前強制呼叫 `database/db_target_guard.py` 的 `assert_safe_migration_target()`；偵測到連線目標疑似真實開發 DB 且未提供明確覆寫確認時，於連線前即拒絕執行——彌補第 3／6 項本身仍依賴「先做才有備份／先驗證才正式跑」這種流程紀律的缺口，是技術層面而非流程層面的護欄 |
 
 ---
 
diff --git a/doc/upgrade/contracts/REMAINING_RISKS.md b/doc/upgrade/contracts/REMAINING_RISKS.md
index d31c5b8..151d474 100644
--- a/doc/upgrade/contracts/REMAINING_RISKS.md
+++ b/doc/upgrade/contracts/REMAINING_RISKS.md
@@ -15,14 +15,14 @@
 | RISK-003 | Dcard 端點非公開正式 API | Medium | NOT VERIFIED | Data Acquisition | UG-G2-SB5 | 可用性驗證 PASS/FAIL 分流 | API 結構變更或封鎖 | FAIL → DEFERRED WITH EVIDENCE |
 | RISK-004 | Threads 官方 API 權限不明 | Medium | NOT VERIFIED | Data Acquisition | Deferred | 等待官方 API 確認 | 無公開 API | Conditional/Deferred |
 | RISK-005 | 150 檔 ETL 超出時間窗口 | Medium | HYPOTHESIS | Performance | UG-G2-SB7 | 批次化 + 效能基準測試 | ETL > 5 分鐘 | 批次 API、平行化 |
-| RISK-006 | PostgreSQL Migration 失敗破壞開發資料 | Low | NOT VERIFIED | Data Safety | UG-G1-SB4 | 隔離容器驗證 + pg_dump + Transaction rollback | Migration SQL 錯誤 | 分層 Rollback 策略 |
+| RISK-006 | PostgreSQL Migration 失敗破壞開發資料 | Low | VERIFIED（部分——見說明） | Data Safety | UG-G1-SB4 | 隔離容器驗證 + pg_dump + Transaction rollback。**已驗證**：隔離容器驗證（`sb4_migration_tmpdb`，非 `postgres-data` 掛載）與 Transaction rollback（故意失敗遷移確認 ROLLBACK、`schema_version` 版本未推進，`SB4_STEP2_GATE_B_SUBMISSION.md`）。**尚未驗證**：pg_dump 備份還原流程（L5 完整回滾）——本次全程僅對隔離臨時 DB 操作，未曾對真實開發 DB 執行過 migration，故無實際觸發 pg_dump 還原的情境；此為 DEC-010 分層 Rollback 策略 L5，需 PO 核准才會使用，待真正對真實 DB 執行 migration 時才有機會驗證 | Migration SQL 錯誤 | 分層 Rollback 策略 |
 | RISK-007 | SHAP 計算對大模型過慢 | Low | HYPOTHESIS | Performance | UG-G4-SB2 | 先用 MDI；SHAP 可選 | 單次 > 30 秒 | 使用 TreeExplainer；必要時只算 Top-K |
 | RISK-008 | Git history 含舊 credential | Medium | OBSERVED | Security | 公開前 | 公開前 credential rotation + history sanitization | Repository 公開 | 不公開直到清理完成 |
 | RISK-009 | OOF Stacking 過擬合 | Medium | HYPOTHESIS | ML Performance | UG-G3-SB4 | Purged OOF + 校準資料隔離 | Holdout 績效遠低於 OOF | 減少 Meta-Learner 複雜度 |
 | RISK-010 | 台股前 150 檔 × 短歷史樣本量不足 | High | HYPOTHESIS | ML Performance | UG-G3-SB7 | 至少 3 年歷史；先設保守 TARGET 60% | Fold 內樣本不足 | 調整 Fold 大小或 Universe |
 | RISK-011 | Triple-Barrier Ambiguous 比例過高 | Medium | HYPOTHESIS | ML Performance | UG-G3-SB1 | 監控並報告；必要時調 Barrier 寬度/持有期 | Ambiguous > 10% | 開新 PO 決策 |
 | RISK-012 | 未採 Point-in-Time Universe 導致存活偏誤 | High | PLANNED | ML Integrity | UG-G2-SB6 | PIT Snapshot + 歷史回測載入當期 Universe | 回測用今日 Universe | UG-G2-SB6 PIT 實作 |
-| RISK-013 | 驗證／測試腳本可在未覆寫 `DB_HOST`／`DB_PORT` 時直連真實開發資料庫 | High | OBSERVED | Data Safety | 全部 | **Mitigate**（PO 簽核 2026-08-24）。已部署控制措施：每次碰 DB 的執行，綁定確認輸出必須先呈報 PO 再跑，且須以專案自身的 `DBWriter.db_config` 解析路徑取得 —— 手寫連線字串只證明「能連到臨時 DB」，證不到「測試將使用的那組設定指向臨時 DB」。**根本解「驗證腳本在偵測到指向真實 DB 時拒絕執行」必須在 UG-G1-SB4（DB Migration 機制）之前落地。**理由：至今所有暴露皆為唯讀路徑（`data_loader` 零寫入 SQL、`db_writer:270` 為 SELECT），漏設 `DB_HOST` 的後果是「讀了不該讀的」，可回復；SB4 執行 migration 屬**寫入路徑**，同一次漏設的後果變成對真實開發資料庫執行 DDL —— 回報紀律擋得住前者，擋不住後者 | 執行者遺漏環境變數覆寫（已於 2026-08-23 發生一次） | 停止執行；比對資料最新寫入時間戳確認有無損害；改以空臨時 DB 重跑 |
+| RISK-013 | 驗證／測試腳本可在未覆寫 `DB_HOST`／`DB_PORT` 時直連真實開發資料庫 | High | VERIFIED | Data Safety | 全部（寫入路徑另受 `db_target_guard` 強制保護） | **根本解已落地（UG-G1-SB4 階段一，2026-08-26，commit `d2a4d48`；DEC-021）**：`database/db_target_guard.py` 的 `assert_safe_migration_target()`，`database/apply_migrations.py` 在建立連線前強制呼叫，偵測到連線目標疑似真實 DB（host/port 未覆寫預設值，或 database 名稱不符臨時 DB 命名慣例）即 `raise SystemExit`，不建立任何連線。已實測確認：以真實 DB 座標、未設定覆寫確認變數執行 → 連線前即被拒絕（`SB4_STEP2_GATE_B_SUBMISSION.md` E2E 驗證項 4）。原有「呈報綁定確認」流程紀律**維持不變**，兩者疊加，非取代關係——技術護欄是流程紀律失守時的最後防線，不是免除流程紀律的理由。**剩餘缺口**（DEC-021 Trade-offs 已記錄，PO 同意本次不要求改設計）：機制依賴呼叫端主動呼叫，未強制耦合於 `DBWriter` 寫入方法本身；`data_loader`／`db_writer:270` 等既有唯讀路徑仍僅受流程紀律保護，未整合本機制（RISK-013 原文即限定寫入路徑為根本解範圍，唯讀路徑風險評估不變） | 執行者遺漏環境變數覆寫（已於 2026-08-23 發生一次）；或遺漏呼叫 `assert_safe_migration_target()`（技術護欄僅保護「有呼叫」的路徑） | 若寫入路徑遺漏呼叫本函式：停止執行；比對資料最新寫入時間戳確認有無損害；改以空臨時 DB 重跑 |
 | RISK-014 | 基底映像 digest 釘選使安全性更新不再自動到來 | Medium | OBSERVED | Security | 全部 | 更新為刻意行為：改 digest → 重建 → 重新產生 lock → 淨重建驗證四項 | 上游發布安全性修補，或 lock/digest 需變更 | 依 `CLAUDE.md` §13.6 執行淨重建驗證；任一項不符即回報，不得調整 lock 使其通過 |
 
 ## Risk Summary
diff --git a/database/apply_migrations.py b/database/apply_migrations.py
new file mode 100644
index 0000000..9aa1df0
--- /dev/null
+++ b/database/apply_migrations.py
@@ -0,0 +1,144 @@
+"""
+database/apply_migrations.py
+
+增量 Schema 遷移執行器（UG-G1-SB4 階段二）。
+規格來源：doc/upgrade/contracts/DB_MIGRATION_PLAN.md §5（Gate 0 已核准）。
+
+核心邏輯：
+1. 連線資料庫前，先呼叫 database.db_target_guard.assert_safe_migration_target()
+   （RISK-013 根本解——本檔與 database/db_target_guard.py 的唯一耦合點，
+   不可省略、不可延後）。
+2. 檢查 schema_version 表是否存在；不存在 → 目前版本為 0，存在 → SELECT MAX(version)。
+3. 掃描 database/migrations/ 目錄，依檔名編號排序。
+4. 篩選出 version > current_version 的腳本。
+5. 依序對每個腳本：BEGIN → 執行 SQL 內容 → COMMIT；任一失敗 → ROLLBACK，
+   停止執行，回報錯誤，回傳非 0 結束碼。
+6. 全部成功後輸出執行結果摘要，回傳 0。
+
+設計原則（DB_MIGRATION_PLAN.md §5.2）：
+- 冪等性：每個遷移使用 IF NOT EXISTS 與 ON CONFLICT DO NOTHING，重複執行不出錯。
+- 原子性：每個遷移在獨立事務中執行，失敗時自動 ROLLBACK。
+- 順序性：嚴格按檔名編號順序執行，不可跳號。
+- 安全性：不執行已套用的版本（版本號已存在於 schema_version）。
+"""
+
+import hashlib
+import os
+import re
+import sys
+from pathlib import Path
+
+import psycopg2
+
+sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
+
+from database.db_target_guard import assert_safe_migration_target
+from src.loaders.db_writer import DBWriter
+
+MIGRATIONS_DIR = Path(__file__).resolve().with_name("migrations")
+_MIGRATION_FILENAME_PATTERN = re.compile(r"^(\d+)_.*\.sql$")
+
+
+def _discover_migrations() -> list:
+    """
+    掃描 MIGRATIONS_DIR，回傳依 version 遞增排序的 (version, path) 清單。
+    檔名不符合 `<數字>_<描述>.sql` 樣式者略過，不視為錯誤（允許目錄下有 README 等）。
+    """
+    found = []
+    for entry in MIGRATIONS_DIR.iterdir():
+        if not entry.is_file():
+            continue
+        m = _MIGRATION_FILENAME_PATTERN.match(entry.name)
+        if not m:
+            continue
+        found.append((int(m.group(1)), entry))
+    found.sort(key=lambda pair: pair[0])
+    return found
+
+
+def _get_current_version(cursor) -> int:
+    """回傳目前已套用的最高版本號；schema_version 表不存在時視為版本 0。"""
+    cursor.execute(
+        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_version');"
+    )
+    (table_exists,) = cursor.fetchone()
+    if not table_exists:
+        return 0
+
+    cursor.execute("SELECT MAX(version) FROM schema_version;")
+    (max_version,) = cursor.fetchone()
+    return max_version or 0
+
+
+def _apply_one_migration(connection, version: int, path: Path) -> None:
+    """
+    在獨立事務中執行單一遷移檔案；失敗時 ROLLBACK 並重新拋出例外。
+
+    每個已核准的遷移檔案（見 DB_MIGRATION_PLAN.md §4）內容本身即包含自我登記的
+    `INSERT INTO schema_version ... ON CONFLICT (version) DO NOTHING`，不含 checksum。
+    此函式執行完遷移 SQL 後改用 UPDATE 補上 checksum——若改用 INSERT 會被前述
+    自我登記的 ON CONFLICT 擋下而永遠寫不進去；UPDATE 則不論該列是否已由遷移檔案
+    自行建立，皆能正確補上。
+    """
+    sql_text = path.read_text(encoding="utf-8")
+    checksum = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
+
+    try:
+        with connection.cursor() as cursor:
+            cursor.execute(sql_text)
+            cursor.execute(
+                "UPDATE schema_version SET checksum = %s WHERE version = %s;",
+                (checksum, version),
+            )
+        connection.commit()
+    except Exception:
+        connection.rollback()
+        raise
+
+
+def apply_migrations() -> int:
+    """
+    執行全部待套用遷移。回傳結束碼（0 成功，非 0 失敗）。
+    不在此函式內呼叫 sys.exit，由呼叫端（__main__ 區塊）決定進程結束碼，
+    以利測試以函式呼叫方式驗證回傳值而不終止測試進程。
+    """
+    db_config = DBWriter().db_config
+    assert_safe_migration_target(db_config)  # RISK-013 根本解：連線前必經檢查
+
+    migrations = _discover_migrations()
+    if not migrations:
+        print(f"[apply_migrations] {MIGRATIONS_DIR} 內無符合命名樣式的遷移檔案。")
+        return 0
+
+    print("[apply_migrations] 正在連線到 PostgreSQL...")
+    connection = psycopg2.connect(**db_config)
+    try:
+        with connection.cursor() as cursor:
+            current_version = _get_current_version(cursor)
+        print(f"[apply_migrations] 目前已套用版本：v{current_version}")
+
+        pending = [(v, p) for v, p in migrations if v > current_version]
+        if not pending:
+            print("[apply_migrations] 無待執行遷移，已是最新版本。")
+            return 0
+
+        for version, path in pending:
+            print(f"[apply_migrations] 正在套用 v{version}（{path.name}）...")
+            try:
+                _apply_one_migration(connection, version, path)
+            except Exception as exc:
+                print(
+                    f"[apply_migrations] v{version}（{path.name}）執行失敗，已 ROLLBACK，"
+                    f"版本未推進：{exc}"
+                )
+                return 1
+            print(f"[apply_migrations] v{version} 已套用並 COMMIT。")
+
+        print(f"[apply_migrations] 完成，已套用至 v{pending[-1][0]}。")
+        return 0
+    finally:
+        connection.close()
+
+
+if __name__ == "__main__":
+    sys.exit(apply_migrations())
diff --git a/database/migrations/001_baseline.sql b/database/migrations/001_baseline.sql
new file mode 100644
index 0000000..d9502a4
--- /dev/null
+++ b/database/migrations/001_baseline.sql
@@ -0,0 +1,15 @@
+-- Migration 001: Baseline — 建立 schema_version 表
+-- From: v0 (no migration tracking)
+-- To:   v1
+-- 規格來源：doc/upgrade/contracts/DB_MIGRATION_PLAN.md §4.1（Gate 0 已核准）
+
+CREATE TABLE IF NOT EXISTS schema_version (
+    version     INTEGER PRIMARY KEY,
+    description TEXT NOT NULL,
+    applied_at  TIMESTAMP DEFAULT NOW(),
+    checksum    TEXT
+);
+
+INSERT INTO schema_version (version, description)
+VALUES (1, 'Baseline: create schema_version table')
+ON CONFLICT (version) DO NOTHING;
diff --git a/tests/test_apply_migrations.py b/tests/test_apply_migrations.py
new file mode 100644
index 0000000..4ae4ca2
--- /dev/null
+++ b/tests/test_apply_migrations.py
@@ -0,0 +1,116 @@
+"""
+tests/test_apply_migrations.py
+
+UG-G1-SB4 階段二：database/apply_migrations.py 的隔離單元測試（mock DB 連線與游標，
+不連接任何真實資料庫，符合測試封閉性慣例）。
+
+**這些測試驗證的是邏輯正確性，不是「跑起來真的能連 Postgres」**——後者已於
+2026-08-26 對隔離臨時 DB（sb4_migration_tmpdb，port 55440，非 postgres-data 掛載）
+實際執行過完整 E2E 驗證（fresh init + apply、冪等性、版本檢查、真實 DB 座標被拒絕、
+故意失敗遷移的 ROLLBACK），原始輸出見 SB4_STEP2_GATE_B_SUBMISSION.md。
+"""
+
+import unittest
+from unittest.mock import MagicMock, patch
+
+
+class MigrationVersionCheckTests(unittest.TestCase):
+    """對應 Master Plan Brief 既定測試名稱：test_version_check"""
+
+    def test_version_check_table_missing_returns_zero(self):
+        from database.apply_migrations import _get_current_version
+        cursor = MagicMock()
+        cursor.fetchone.return_value = (False,)  # information_schema 查詢：表不存在
+        self.assertEqual(_get_current_version(cursor), 0)
+
+    def test_version_check_table_exists_returns_max_version(self):
+        from database.apply_migrations import _get_current_version
+        cursor = MagicMock()
+        cursor.fetchone.side_effect = [(True,), (3,)]  # 表存在 → MAX(version)=3
+        self.assertEqual(_get_current_version(cursor), 3)
+
+    def test_version_check_table_exists_but_empty_returns_zero(self):
+        """表已建立但尚未有任何版本列（MAX 回傳 NULL）時應視為版本 0，不得誤判為 None 或拋錯。"""
+        from database.apply_migrations import _get_current_version
+        cursor = MagicMock()
+        cursor.fetchone.side_effect = [(True,), (None,)]
+        self.assertEqual(_get_current_version(cursor), 0)
+
+
+class MigrationIdempotencyTests(unittest.TestCase):
+    """對應 Master Plan Brief 既定測試名稱：test_migration_idempotency"""
+
+    @patch("database.apply_migrations.psycopg2.connect")
+    @patch("database.apply_migrations.assert_safe_migration_target")
+    @patch("database.apply_migrations.DBWriter")
+    def test_no_pending_migrations_skips_execution_and_returns_zero(self, mock_writer_cls, mock_guard, mock_connect):
+        """目前版本已等於最新遷移版本時，不得執行任何遷移 SQL，直接回傳 0。"""
+        from database.apply_migrations import apply_migrations
+
+        mock_writer_cls.return_value.db_config = {"host": "x", "port": 1, "database": "sb4_test_tmpdb"}
+        mock_conn = MagicMock()
+        mock_connect.return_value = mock_conn
+        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
+        mock_cursor.fetchone.side_effect = [(True,), (1,)]  # 表存在，目前版本 v1（等於 001_baseline.sql）
+
+        exit_code = apply_migrations()
+
+        self.assertEqual(exit_code, 0)
+        # 除了版本檢查用的兩次 fetchone 之外，不應再對任何遷移 SQL 呼叫 execute
+        # （_apply_one_migration 會另外開新的 cursor context，這裡驗證的是主流程未進入該分支）
+        mock_conn.commit.assert_not_called()
+
+
+class MigrationRollbackTests(unittest.TestCase):
+    """對應 Master Plan Brief 既定測試名稱：test_rollback_on_failure"""
+
+    @patch("database.apply_migrations.psycopg2.connect")
+    @patch("database.apply_migrations.assert_safe_migration_target")
+    @patch("database.apply_migrations.DBWriter")
+    def test_migration_failure_triggers_rollback_and_nonzero_return(self, mock_writer_cls, mock_guard, mock_connect):
+        """遷移 SQL 執行拋出例外時，必須呼叫 connection.rollback()，且 apply_migrations() 回傳非 0。"""
+        from database.apply_migrations import apply_migrations
+
+        mock_writer_cls.return_value.db_config = {"host": "x", "port": 1, "database": "sb4_test_tmpdb"}
+        mock_conn = MagicMock()
+        mock_connect.return_value = mock_conn
+        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
+        mock_cursor.fetchone.side_effect = [(True,), (0,)]  # 目前版本 v0，001_baseline.sql（v1）待套用
+
+        def execute_side_effect(sql, *args, **kwargs):
+            # 僅讓「版本檢查」查詢正常通過；遷移本體 SQL（001_baseline.sql 內容不含
+            # information_schema／MAX(version) 字樣）才觸發模擬失敗，避免連版本檢查
+            # 這個前置步驟都被誤判為失敗。
+            if "information_schema" in sql or "MAX(version)" in sql:
+                return None
+            raise Exception("simulated DDL failure")
+
+        mock_cursor.execute.side_effect = execute_side_effect
+
+        exit_code = apply_migrations()
+
+        self.assertEqual(exit_code, 1)
+        mock_conn.rollback.assert_called()
+        mock_conn.commit.assert_not_called()
+
+
+class MigrationGuardIntegrationTests(unittest.TestCase):
+    """對應 Master Plan Brief 既定測試名稱：test_runner_nonzero_exit_on_error（RISK-013 根本解整合）"""
+
+    @patch("database.apply_migrations.psycopg2.connect")
+    @patch("database.apply_migrations.DBWriter")
+    def test_guard_rejection_prevents_any_connection_attempt(self, mock_writer_cls, mock_connect):
+        """assert_safe_migration_target 判定疑似真實 DB 時，不得呼叫 psycopg2.connect。"""
+        from database.apply_migrations import apply_migrations
+
+        # 未覆寫的預設值 + 非臨時命名，且未設定確認變數 → 應觸發 SystemExit
+        mock_writer_cls.return_value.db_config = {"host": "localhost", "port": 5432, "database": "postgres"}
+
+        with self.assertRaises(SystemExit):
+            apply_migrations()
+
+        mock_connect.assert_not_called()
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
本次修改的 `DECISIONS.md` 皆在 `DOC_PATHS` 掃描範圍內，重跑確認未破壞跨文件契約
一致性。

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
Ran 200 tests in 9.583s

OK
```

200 = 194（SB4 階段一 commit `d2a4d48` 基線）+ 6 個新增（`tests/test_apply_migrations.py`，
mock DB 連線與游標，不連真實資料庫）。**既有 194 個測試仍全數 PASS，未受影響。**

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

**12/12 PRESENT**。`psycopg2` 為本次唯一直接相關依賴（DB 連線），確認為真實實作。

---

## 4. 產出 3：檔案清單與逐檔授權稽核

```bash
git status --porcelain
```

```
 M database/schema.sql
 M doc/evidence/DECISIONS.md
 M doc/evidence/TRACEABILITY.md
 M doc/governance/PROJECT_STATUS.md
 M doc/spec/SDD_Financial_Sentiment_System_v1.md
 M doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
 M doc/upgrade/contracts/DB_MIGRATION_PLAN.md
 M doc/upgrade/contracts/REMAINING_RISKS.md
?? database/apply_migrations.py
?? database/migrations/
?? tests/test_apply_migrations.py
```

> 本文件本身（`SB4_STEP2_GATE_B_SUBMISSION.md`）亦為新檔，比照階段一慣例
> 併入同一次 commit（詳見 §8）。

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `database/schema.sql` | 在授權交付物內 | `SB4_GATE_A_PROPOSAL.md` §4「階段二」明列 |
| `database/migrations/001_baseline.sql`（新檔） | 在授權交付物內 | 同上；規格源自 `DB_MIGRATION_PLAN.md` §4.1（Gate 0 已核准，內容未改動） |
| `database/apply_migrations.py`（新檔） | 在授權交付物內 | 同上；PO 明確提醒須先呼叫 `assert_safe_migration_target()` |
| `tests/test_apply_migrations.py`（新檔） | 在授權交付物內 | Master Plan Brief 既定四項測試名稱 |
| `doc/evidence/DECISIONS.md` | 在授權交付物內 | Documentation Sync 既定要求；DEC-010 Verification 補齊、新增 DEC-021 |
| `doc/evidence/TRACEABILITY.md` | 在授權交付物內 | 同上 |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 在授權交付物內 | Master Plan Brief「Documentation Sync：SDD 資料庫章節」既定要求 |
| `doc/upgrade/contracts/DB_MIGRATION_PLAN.md` | 在授權交付物內 | Documentation Sync 既定要求；§5/§6 補充實作發現的細節 |
| `doc/upgrade/contracts/REMAINING_RISKS.md` | 在授權交付物內 | RISK-013／RISK-006 狀態更新，反映階段一/二實測結果 |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | **不在明列清單，屬狀態追蹤慣例** | 與 SB1～SB3 各步驟的既有做法一致，§16.3 規則 2 之必要前置 |
| `doc/governance/PROJECT_STATUS.md` | **不在明列清單，屬狀態追蹤慣例** | 同上 |
| `doc/upgrade/gates/SB4_STEP2_GATE_B_SUBMISSION.md`（新檔，本檔） | 在授權交付物內 | 比照階段一慣例，Gate B 文件與其描述的程式碼同一次 commit |

**本次無超出授權清單的檔案。**

---

## 5. 產出 4：格式／行尾夾帶偵測

```bash
git diff --numstat > /tmp/ns_raw.txt
git diff --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

```
（無輸出，兩者完全一致）
```

**無落差**——3 個新檔皆為全新內容；8 個修改檔案的變更皆為新增段落／表格列，
逐檔核對後 raw 與 `-w` 結果一致，無格式夾帶。

---

## 6. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 不可重跑原因 |
|------|---------|--------------------------|
| contract-check 11/11 PASS | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py` |
| 全套測試 200/200 PASS（既有 194 個未受影響） | `VERIFIED THIS SESSION` | §3b 指令 |
| E2E 驗證 1（fresh init + apply → `schema_version` 存在，v1） | `VERIFIED THIS SESSION` | §7 逐項原始輸出；隔離容器 `sb4_migration_tmpdb`（已拆除） |
| E2E 驗證 2（冪等性：二次執行顯示「無待執行遷移」） | `VERIFIED THIS SESSION` | 同上 |
| E2E 驗證 3（版本檢查：`schema_version` 內容含正確 `checksum`） | `VERIFIED THIS SESSION` | 同上 |
| E2E 驗證 4（PO 新增：真實 DB 座標未確認即被拒絕，連線前中止） | `VERIFIED THIS SESSION` | 同上；未對真實 DB 建立任何連線 |
| 故意失敗遷移觸發 ROLLBACK，版本未推進 | `VERIFIED THIS SESSION` | 同上；已刪除測試用的故意失敗遷移檔案，不併入 commit |
| known-FAIL 案例 6（舊防線失效對照組）已補上 | `VERIFIED THIS SESSION` | §7；對隔離臨時 DB（非真實 DB）執行，示範腳本已從容器內刪除，不併入 commit |
| `checksum` 欄位設計缺陷已發現並修正（INSERT→UPDATE） | `VERIFIED THIS SESSION` | 修正前後皆有原始查詢輸出對照，見 §7 與 `DECISIONS.md` DEC-010 |
| 隔離容器全程未觸及 `.devcontainer/postgres-data/` | `VERIFIED THIS SESSION` | `docker inspect sb4_migration_tmpdb` 確認掛載為匿名 volume，非 bind mount；容器已 `docker rm -f -v` 拆除 |
| 6 個 mock 單元測試涵蓋版本檢查／冪等／回滾／守門整合四類邏輯 | `VERIFIED THIS SESSION` | `tests/test_apply_migrations.py`；`gate0_contract_check.py` 不掃描此檔 |
| `002_expand_ml_features.sql`／`003_expand_articles.sql` 之多遷移序列真實互動 | `NOT VERIFIED` | 未驗證範圍：屬 Gate 2／3 範圍，尚未實作，本次僅驗證單一遷移（001） |
| 分層 Rollback 策略 L5（`pg_dump` 完整還原） | `NOT VERIFIED` | 未驗證範圍：全程僅對隔離臨時 DB 操作，未曾對真實開發 DB 執行 migration，無實際觸發情境 |

---

## 7. 產出 6：known-FAIL 案例對照表 + E2E 原始輸出

### 7a. RISK-013 綁定確認（執行任何 E2E 驗證前）

```bash
docker run -d --name sb4_migration_tmpdb \
  --network stock_prediction_system2_devcontainer_default \
  -e POSTGRES_DB=sb4_migration_tmpdb -e POSTGRES_USER=sb4_tmp_user -e POSTGRES_PASSWORD=sb4_tmp_pass \
  -p 55440:5432 postgres:18
```

```
容器掛載檢查（docker inspect --format '{{range .Mounts}}...{{end}}'）：
volume /var/lib/docker/volumes/.../_data -> /var/lib/postgresql
（匿名 volume，非 .devcontainer/postgres-data/ bind mount，確認隔離）

綁定確認（DBWriter().db_config 解析 + current_database()/current_user/inet_server_port()）：
db_config: {'host': 'sb4_migration_tmpdb', 'port': 5432, 'database': 'sb4_migration_tmpdb', 'user': 'sb4_tmp_user', 'password': '***'}
bind confirmation: ('sb4_migration_tmpdb', 'sb4_tmp_user', 5432)
```

### 7b. E2E 驗證 1：fresh init + apply

```bash
docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=sb4_migration_tmpdb -e DB_PORT=5432 \
  -e POSTGRES_DB=sb4_migration_tmpdb -e POSTGRES_USER=sb4_tmp_user -e POSTGRES_PASSWORD=sb4_tmp_pass \
  stock_prediction_system2_devcontainer-app-1 python database/init_db.py
```
```
正在連線到 PostgreSQL...
正在執行 database/schema.sql...
資料庫初始化已成功 commit。
```

```bash
docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=sb4_migration_tmpdb -e DB_PORT=5432 \
  -e POSTGRES_DB=sb4_migration_tmpdb -e POSTGRES_USER=sb4_tmp_user -e POSTGRES_PASSWORD=sb4_tmp_pass \
  stock_prediction_system2_devcontainer-app-1 python database/apply_migrations.py
```
```
[apply_migrations] 正在連線到 PostgreSQL...
[apply_migrations] 目前已套用版本：v0
[apply_migrations] 正在套用 v1（001_baseline.sql）...
[apply_migrations] v1 已套用並 COMMIT。
[apply_migrations] 完成，已套用至 v1。
EXIT=0
```

### 7c. E2E 驗證 3：版本檢查（含 checksum 修正後的正確結果）

```sql
SELECT version, description, applied_at, checksum FROM schema_version ORDER BY version;
```
```
(1, 'Baseline: create schema_version table', datetime.datetime(2026, 8, 26, 6, 20, 58, 887584), 'ec02925a75da276cd75002482f7cde50a055b891b5237217d3a510a52aabbe54')
```

**修正前的原始問題（已修正，附對照）**：改用 UPDATE 前，此欄位查詢結果為
`checksum=None`——原因見 §0「修正」列與 `DECISIONS.md` DEC-010：`001_baseline.sql`
內容本身即含 `INSERT INTO schema_version ... ON CONFLICT (version) DO NOTHING`，
runner 端原本也用 INSERT 補 checksum，被前者的 `ON CONFLICT` 擋下。

### 7d. E2E 驗證 2：冪等性（第二次執行）

```
[apply_migrations] 正在連線到 PostgreSQL...
[apply_migrations] 目前已套用版本：v1
[apply_migrations] 無待執行遷移，已是最新版本。
EXIT=0
```

### 7e. E2E 驗證 4（PO 新增）：真實 DB 座標，未設定確認變數

```bash
docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python database/apply_migrations.py
```
```
[RISK-013 guard] 偵測到連線目標疑似為真實開發 DB (host=localhost, port=5432, database=postgres)，拒絕執行。
若確實要對真實 DB 執行（例如正式套用 migration），請先完成 CLAUDE.md RISK-013 協定之綁定確認呈報，再設定環境變數 CONFIRM_REAL_DB_MIGRATION_TARGET=I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB 後重跑。
EXIT=1
```

未附加任何 `DB_HOST`／`DB_PORT` 環境變數覆寫（即真實 DB 座標）；輸出中**沒有**
「正在連線到 PostgreSQL...」這行，證實 `assert_safe_migration_target()` 在
`psycopg2.connect()` 之前就已中止，從未嘗試連線。

### 7f. 失敗回滾測試（Master Plan Brief §8.4）

構造一支故意失敗的遷移 `database/migrations/002_deliberately_broken_for_test.sql`
（`ALTER TABLE this_table_does_not_exist ADD COLUMN nonexistent_col TEXT;`），
執行後立即刪除，不併入 commit：

```
[apply_migrations] 正在連線到 PostgreSQL...
[apply_migrations] 目前已套用版本：v1
[apply_migrations] 正在套用 v2（002_deliberately_broken_for_test.sql）...
[apply_migrations] v2（002_deliberately_broken_for_test.sql）執行失敗，已 ROLLBACK，版本未推進：relation "this_table_does_not_exist" does not exist
EXIT=1
```

還原後確認：`SELECT version FROM schema_version` 僅剩 v1，v2 從未被記錄。

### 7g. known-FAIL 案例 6：舊防線失效對照組（本階段補上，PO 明確要求）

構造一支精簡複製版 `apply_migrations.py`，**唯一差異是移除 `assert_safe_
migration_target()` 呼叫**，僅對隔離臨時 DB（`sb4_migration_tmpdb`）執行，
不對真實 DB 執行：

```
=== [對照組] 未受保護版本：跳過 assert_safe_migration_target() ===
[demo] db_config（未經任何守門檢查）: host=sb4_migration_tmpdb, port=5432, database=sb4_migration_tmpdb
[demo] 直接嘗試連線（沒有任何攔截點）...
[demo] 連線成功，已建立與 ('sb4_migration_tmpdb', 5432) 的連線——若這是真實 DB 座標，此時已經連上了，
[demo] 且下一步就會直接執行 DDL，沒有任何機制能在這裡回頭。
```

對照 §7e：**同一種未覆寫環境變數的疏失**，有守門函式時於連線前即被拒絕
（EXIT=1，從未連線）；沒有守門函式時直接連線成功（此範例為隔離臨時 DB，
若換成真實 DB 座標，下一步即是執行 DDL，無任何攔截點）——這就是 DEC-021
存在的理由本身。示範腳本執行後已從容器內刪除，不併入任何 commit。

### 7h. known-FAIL 案例對照表彙總

| # | 案例 | 是否對真實 DB 操作 | 實測結果 |
|---|------|---------------------|---------|
| 1 | 真實 DB 座標，未設定確認變數 | 否——連線前即被拒絕 | §7e：`SystemExit`，`psycopg2.connect` 從未被呼叫 |
| 2 | 故意失敗的遷移 | 否——僅隔離臨時 DB | §7f：`ROLLBACK`，版本未推進，EXIT=1 |
| 3 | 舊防線失效對照組（無守門函式） | 否——僅隔離臨時 DB | §7g：直接連線成功，無任何攔截點 |
| 4 | fresh init + apply | 否——僅隔離臨時 DB | §7b：`schema_version` 正確建立並套用 v1 |
| 5 | 冪等重跑 | 否——僅隔離臨時 DB | §7d：「無待執行遷移」，無副作用 |
| 6 | 版本檢查（含 checksum） | 否——僅隔離臨時 DB | §7c：checksum 正確非空 |

**全程未對真實開發 DB 建立任何連線**——案例 1（唯一涉及「真實 DB 座標」的案例）
的重點正是「連線前就被擋下」，本身即是安全的驗證方式。

---

## 8. 尚未解決／請 PO 裁決事項

1. **Gate B 文件是否併入同一次 commit**：比照階段一（PO 已同意該次處理方式，
   commit `d2a4d48` 一併納入 `SB4_GATE_A_PROPOSAL.md`／`SB4_STEP1_GATE_B_
   SUBMISSION.md`），本文件預設也隨階段二程式碼一併 commit；若您希望分開，請告知。
2. **DEC-010 Verification 補齊是否需要另外裁示**：本文件已將 DEC-010 的 4 個
   Verification 勾選項目全部標記完成（見 §1 diff），這是既有 Gate 0 ADR 的
   狀態更新，非新決策，理論上不需要重新核准；若您認為仍需明確裁示，請告知。
3. **002／003 遷移何時開始**：屬 Gate 2／3 範圍，不在本次請求範圍內，僅提醒
   `DECISIONS.md` DEC-010 的 Remaining Risks 已記錄此缺口。

**commit 授權**：本文件為送審文件，不代表 commit 已獲授權。若 PO 決定放行，
請明確指出授權範圍（哪些檔案）；`gate-submit` skill 的自檢流程第 3～5 步
（`git add`、逐檔稽核、格式偵測）將在取得授權後於 commit 前重新針對實際 staged 內容執行一次。
