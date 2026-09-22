# Engineering Decisions（工程決策紀錄）

## DEC-001：建立 Pre-Codex 可回復基線

- 日期：2026-08-18
- 狀態：Completed（已完成）

### Context（背景）

本專案在正式導入 Codex Agent 前，已累積由人工與舊 AI 協作完成的 ETL、NLP、資料庫 Schema、文件及研究資料。當前 Git Working Tree（Git 工作目錄）包含尚未提交的修改、刪除與新增檔案，且本機 PostgreSQL 18 的實體資料透過 bind mount（綁定掛載）保存在 `.devcontainer/postgres-data/`。

### Problem（問題）

若直接開始後續程式修改，既有 Pre-Codex 成果與 Codex 產生的變更將難以區分，也缺少可清楚回復的 Git 基準。PostgreSQL 實體資料若未被 Git 明確忽略，亦存在誤加入版本控制的風險。實體資料目錄本身不等同可攜式資料庫備份。

### Alternatives（考慮方案）

1. 直接在 `main` 提交目前狀態：步驟較少，但會讓尚在審查中的基線直接進入主要分支。
2. 不建立基線，直接開始修正程式：速度較快，但難以區分既有成果與後續 Agent 修改，也提高回復與審查成本。
3. 建立專用 branch、補強忽略規則、建立 PostgreSQL Logical Backup（邏輯備份），經人工審查後再建立單一 baseline commit（基線提交）。

### Decision（決策）

採用方案 3：

- 在 `chore/pre-codex-baseline` branch 整理 Gate 0，不直接修改 `main`，也不推送 remote。
- 正式文件採用 `doc/spec/PRD_Financial_Sentiment_System_v1.md` 與 `doc/spec/SDD_Financial_Sentiment_System_v1.md`；舊版 Markdown 與舊 PDF 不納入新基線。
- `doc/research/股價與情緒關聯研究.pdf` 納入基線。
- `trend_discover.py`、`feature_aggregator.py`、`nlp_processor.py` 視為 Codex 導入前既有成果，不描述為 Codex 新開發功能。
- 臨時測試檔與舊 AI 交接資料不納入正式基線。
- `.env`、秘密檔案、Python 快取、`.devcontainer/postgres-data/` 與資料庫 dump 必須由 `.gitignore` 排除。
- PostgreSQL 備份使用 Repository 外的 custom-format `pg_dump`，不修改或還原目前開發資料庫。
- Gate 0 不執行 repository-wide line-ending normalization（全儲存庫換行格式正規化），也不開始 Gate 1。

### Rationale（理由）

此方案同時保留現有開發成果、隔離後續 Codex 修改、降低秘密資訊與 PostgreSQL 實體資料誤提交風險，並提供 Git 與資料庫兩個層次的回復能力。專用 branch 也讓基線可在合併至 `main` 前先完成人工審查。

### Trade-offs（取捨）

- 建立基線前需要逐檔審查與備份驗證，初期投入時間較多。
- Baseline commit 代表「已凍結且可追蹤的現況」，不代表既有業務邏輯已正確、已通過完整測試或可正式上線。
- 本次不處理既有換行格式與架構問題，因此相關技術債仍需在後續核准的 Gate 中評估。

### Remaining Risks（剩餘風險）

- 既有 Git history 可能仍包含 Pre-Codex 階段的舊 database credential（資料庫憑證）。Gate 0 不重寫 Git history；若該 credential 曾為有效值，Repository 公開前必須完成 Credential Rotation（憑證輪替）與必要的 History Sanitization（歷史秘密資訊清理）。在完成上述安全處理前，本 Repository 應視為不適合公開。
- Gate 0 暫時保留單一 `.env` 同時注入 `app` 與 `db` service 的做法。Service-specific secret configuration（服務專屬秘密資訊設定）列為 Future Production Security Hardening（未來正式環境安全強化）事項，本 Gate 不拆分環境檔，也不導入 Docker Secrets。

### Verification（驗證）

- [x] 已建立並切換至 `chore/pre-codex-baseline` branch。
- [x] 已驗證本次指定的環境／秘密檔名模式、Python 快取、PostgreSQL 實體資料與 dump 均被 Git 忽略；`.env.example` 保持可追蹤。此項不代表已排除 tracked file（已追蹤檔案）內嵌秘密值。
- [x] 已移除正式 tracked files（已追蹤檔案）中的硬編碼資料庫憑證，並確認實際 credential value（憑證值）不會進入 baseline commit。
- [x] 已完成 Repository 外的 PostgreSQL logical backup：`D:\Python\Database_Backups\Stock_Prediction_System\stock_prediction_system_pre_codex_20260818_134017.dump`（24,216 bytes；PostgreSQL／`pg_dump` 18.6；SHA-256 `2E9DCFEEAD5005D6C7BF3A18F76B202FCED466F2D7DD2AF63836AFA30EA4A0F5`），並以 `pg_restore --list` 驗證可解析。
- [x] 已驗證 Dev Container 的 `postCreateCommand` 可重現 requirements 安裝；Python 3.14.6 可由 `vscode` user-site 載入 `psycopg2-binary` 2.9.12，並已使用 `DBWriter` 設定完成 read-only PostgreSQL `SELECT 1` 驗證。
- [x] 已完成所有納入 baseline 的 modified、deleted 與 untracked 檔案之人工 Final Review（最終審查）。
- [x] 已建立 baseline commit：`71fc6c75e54c076377360b2462a3e78bd073ab44`。

Baseline 完成僅代表 Pre-Codex 現況已凍結、可追蹤且具備已驗證的回復依據，不代表既有業務邏輯已完全正確。Gate 1+ remediation（後續修復）仍待依整頓計畫執行與驗證。

### Audit Correction（稽核更正）

- Gate 1 後續唯讀稽核發現，`database/init_db.py` 仍存在 Pre-Codex hard-coded database credential（硬編碼資料庫憑證）。
- 因此，DEC-001 當時對 tracked files 的 credential verification（憑證驗證）範圍不完整；本更正不顯示該 credential value（憑證值）。
- 保留 DEC-001 `Completed（已完成）` 狀態與既有歷史 commit，不執行 amend（修改既有提交）。該遺漏已納入 Gate 1：working-tree implementation 已移除硬編碼憑證，並完成隔離功能驗證；實際 credential value 未記錄於本文件。

---

## DEC-002：以 schema.sql 作為資料庫 DDL Single Source of Truth

- 日期：2026-08-18
- 狀態：Completed（已完成）；Final Gate Review：`PASS WITH NOTES`；Human Approval：`APPROVED`；Gate 1：`CLOSED`

### Context（背景）

Gate 1 開始時，專案同時存在 `database/schema.sql`、舊版 `database/init_db.py` 內嵌 DDL 與實際 PostgreSQL Schema 三種資料庫綱要表述。唯讀稽核確認，實際 PostgreSQL 的六張 public tables、欄位、PK、UNIQUE constraints（唯一限制）、indexes 與 defaults 與 `schema.sql` 一致，目前程式也使用 `daily_ml_features`、`tracking_keywords`、`entity_mapping` 與 `sentiment_cache`。

### Problem（問題）

Gate 1 開始時，`init_db.py` 維護另一份較舊的內嵌 DDL：它缺少目前程式需要的 tables，使用 `daily_model_features` 而非 `daily_ml_features`，並與 `schema.sql` 在欄位、index 與 FK 上不一致。繼續同時維護兩份 DDL 會使新環境無法可靠重建，也可能把初始化誤當成既有資料庫的 Migration（遷移）。

### Alternatives Considered（考慮方案）

1. 以 `schema.sql` 為 DDL authority（權威來源），`init_db.py` 僅負責執行。
2. 以 Python `init_db.py` 內嵌 DDL 為單一來源。
3. 現在導入正式 Migration Framework（資料庫遷移框架）。

### Decision（決策）

採用方案 1：

- `database/schema.sql` 是 Database DDL Single Source of Truth（資料庫 DDL 單一真實來源）。
- `database/init_db.py` 只負責 environment configuration（環境設定）、connection（連線）、transaction（交易）、讀取並執行 `schema.sql`、commit／rollback，以及 error propagation（錯誤傳遞）與正確 process exit status（程序結束狀態）。
- `init_db.py` 不得再維護第二份內嵌 DDL。
- Initialization（初始化）只負責建立新的空資料庫；不負責修正或轉換既有資料庫 Schema。
- Gate 1 不新增 FK、不修改 Canonical Stock ID（標準股票識別碼）、不修改目前開發資料庫 Schema、不刪除或遷移其他環境可能存在的 `daily_model_features`，也不導入 Migration Framework。

### Seed Data Policy（初始資料政策）

- Bootstrap Seed（初始化預設資料）只負責新資料庫的初始預設值。
- `tracking_keywords` 與 `entity_mapping` seed 採用 `ON CONFLICT DO NOTHING`。
- Initializer 重複執行不得覆蓋 Runtime Configuration（執行期設定）。
- 未來若需要修改既有 seed data，屬於 Migration Responsibility（遷移責任），不由 `init_db.py` 處理。

### Rationale（理由）

`schema.sql` 是目前唯一同時與實際 PostgreSQL Schema 及程式使用端一致的可版本控制 DDL artifact（產物）。將 Python 限縮為可觀測的執行器，可以在不引入過早架構複雜度的情況下，降低 Schema drift（綱要漂移）並提高新環境重建的可審查性。

### Trade-offs（取捨）

- 本方案沒有提供版本化 migration history（遷移歷史），不能用來自動升級已有資料庫。
- `CREATE ... IF NOT EXISTS` 只能提供可重複的 bootstrap（初始化），不會修復既有 column type 或 constraint 差異。
- Seed 採 `DO NOTHING` 後，未來預設值變更必須以明確 migration 處理，不會由 initializer 靜默覆寫。
- Migration Framework 延後導入；當 Schema 開始持續演進或進入 cloud deployment（雲端部署）時需重新評估。

### Affected Components（影響範圍）

- `database/schema.sql`
- `database/init_db.py`
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`
- `doc/evidence/DECISIONS.md`
- Gate 1 isolated initialization verification（隔離初始化驗證）

### Verification / Evidence（驗證／證據）

- [x] 已以 read-only PostgreSQL catalog queries 完成 `schema.sql` vs `init_db.py` vs actual PostgreSQL 三方稽核。
- [x] 已確認實際 PostgreSQL Schema 與 `schema.sql` 在本次稽核範圍內一致，並確認程式使用 `daily_ml_features` 而非 `daily_model_features`。
- [x] `init_db.py` 已完成 thin executor（薄型執行器）重構，並移除 hard-coded database credential；它以環境變數取得設定、讀取相鄰 `schema.sql`，並負責 transaction、commit／rollback、error propagation 與 resource cleanup。
- [x] 已在完全隔離的 temporary PostgreSQL 18.6 container 完成 fresh initialization；確認六張 canonical tables、欄位、型別、nullability、defaults、PK、UNIQUE constraints 與 named indexes，且 `daily_model_features` 不存在。
- [x] 第二次 initialization 成功；`tracking_keywords` 與 `entity_mapping` 的 runtime override 保留，row count 未增加且 duplicate query 為空，驗證 `ON CONFLICT DO NOTHING` 不覆寫 Runtime Configuration。
- [x] 第二次執行前後的 normalized catalog Schema Fingerprint 均為 SHA-256 `750b4b7803bb35b7fb17a3f49032ce80f8143757d0237e913cbfa068641c1609`。
- [x] Missing required environment 與明確 bad connection endpoint 均產生 non-zero process exit，且未出現成功 commit 訊息。
- [x] Temporary failure database 中以有效 DDL 後接 invalid SQL 驗證 transaction rollback；failure exit 為 non-zero，rollback probe 不存在，未留下 partial public schema。
- [x] Temporary container 未使用 development bind mount 或 host port；驗證後 container、anonymous volume 與 temporary test files 均已移除。Development PostgreSQL container ID、StartedAt、network、bind mount 與 running state 未改變。
- [x] 已同步 SDD 的 Schema authority、initializer responsibility、Initialization／Migration boundary 與 bootstrap seed policy。
- [x] Reviewer Final Recommendation 為 `PASS WITH NOTES — READY FOR HUMAN CLOSE / COMMIT APPROVAL`；人工已批准 Gate 1 close／commit。

上述證據只支持 fresh／bootstrap initialization 行為；不支持 existing database migration safety、legacy schema upgrade 或 production readiness。

### Security Incident / Risk Decision（安全事件／風險決策）

Gate 1 isolated verification 過程曾使用範圍過大的 Docker runtime inspection，使 container environment 中的 credential values 進入工具紀錄。本事件的 root cause（根因）是：**Read-only inspection（唯讀檢查）不代表 non-sensitive inspection（非敏感檢查）**；完整 `docker inspect` 違反 least-disclosure principle（最少揭露原則）。本紀錄不包含任何 credential value。

已採取與已核准的處置：

- Gemini API key 已由使用者手動 revoke／replace；此 credential incident item 記為 `CLOSED（已關閉）`。
- Local development PostgreSQL password 未 rotation，記為 `Accepted Risk（已接受風險） / Deferred Remediation（延後修復）`。
- 接受風險的理由限於目前環境：local-only development database、無 host port publishing，且不是 production／cloud database；使用者選擇現階段優先完成 Gate 1。
- 此決策不表示該 credential 沒有風險、已安全或不需後續處理。

下列任一 trigger 發生前，必須重新開啟 PostgreSQL credential remediation：

- cloud database deployment
- remote database exposure
- public repository release
- shared／multi-user development environment
- CI/CD 或 automation 使用相同 database credential

### Remaining Risks（剩餘風險）

- Existing database migration safety 尚未驗證；`CREATE ... IF NOT EXISTS` 不會修復既有 column type、constraint 或其他 Schema drift。
- 其他環境若存在 `daily_model_features` 或其他舊 Schema，必須先做獨立 migration audit（遷移稽核）；Gate 1 initializer 不會刪除、重命名或轉換它們，legacy schema upgrade 維持 Deferred（延後）。
- Canonical Stock ID、FK 與 Soft Delete（軟刪除）完整語意仍待後續 Gate 處理。
- 目前開發 PostgreSQL 不會作為 Gate 1 寫入或重建驗證目標。
- Local development PostgreSQL password rotation 依上述風險決策延後；在任何重新開啟 trigger 發生前必須處理。

---

## DEC-003：採用明確 DB Read Failure 與 Strict NLP Completion 語意

- 日期：2026-08-19
- 狀態：Implemented（已實作）且 deterministic unit／mock verification（可重現單元／模擬驗證）已完成；G2-SB1、G2-SB2、G2-SB3、Documentation Sync 與 Final Gate Review 均已完成；Final Gate Review：`PASS WITH NOTES`；Human Close 已批准，Gate 2 正式 `CLOSED`

### Context（背景）

Gate 2 開始時，`DBWriter` 的三個 read methods 會把 database exception 轉成 empty-shaped return，NLP cache hit 是否重用則由分數是否仍落在 fuzzy range（模糊區間）反推。`NLPProcessor` 也會把 SnowNLP／Gemini failure 降級成 `0.5` 或 `{}`，使原 SnowNLP fuzzy score 仍可能寫入 `market_articles.sentiment_score`。由於 NLP Orchestrator 以 `sentiment_score IS NULL` 選取 pending rows，這些行為會把 failure 誤標為 empty、cache miss 或 checkpoint success。

### Problem（問題）

系統缺少可區分的 success、successful empty 與 failure contract：

- DB failure 可能被上層解讀為「沒有待處理文章」或「沒有啟用關鍵字」。
- Cache DB failure 可能被解讀為 cache miss，進而產生不應發生的 Gemini call。
- Cached neutral score 仍在 0.4～0.6 時可能再次呼叫 Gemini。
- Missing API key、SnowNLP exception、Gemini exception、malformed／partial response 或 invalid score 可能仍留下非 NULL score，使 checkpoint 前進。
- Partial Gemini response 未先完成 whole-response validation（整體回應驗證），無法保證所有預期 fuzzy candidates 都有正式結果。

### Alternatives Considered（考慮方案）

#### Database Read Contract

1. 保留 empty-shaped fallback，讓 caller 自行從 log 猜測是否失敗。
2. 導入 explicit Result type（明確結果型別），全面改寫 caller contract。
3. 成功零筆資料維持既有 empty return；database／cache validation failure 直接 raise 並由目前 Pipeline fail-fast。

#### NLP Completion Contract

1. **Option A — Strict LLM Completion（嚴格 LLM 完成）**：非 fuzzy SnowNLP result 可完成

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-005／見 DEC-022 總覽）**：以上「NLP Completion
> Contract」小節原文在此戛然而止（第 199 行本身即為不完整句子，無句號、無下文），
> `Decision`／`Rationale`／`Affected Components`／`Verification` 等後續小節從未寫入本 ADR。
> 依 `CLAUDE.md` §16.1，`doc/evidence/` 為只增不減的證據記錄，本 ADR 原文（含其截斷狀態）
> 保留不動，不回頭補寫或還原缺漏內容。NLP Completion Contract 實際生效的規則現行以
> `CLAUDE.md` §7.2（Batch Checkpointing、LLM 失敗語意）與 `tests/test_nlp_checkpoint_semantics.py`、
> `tests/test_nlp_cache_semantics.py`、`tests/test_nlp_resilience_e2e.py` 三份測試檔為權威依據，
> 不以本段殘缺敘述為準。

## DEC-004：Gate 3 設定生命週期與 MVP 股票識別邊界

- 日期：2026-08-20
- 狀態：Architecture Decision `APPROVED`；G3-SB1 與 G3-SB2 均已實作並完成核准的 unit／mock／static verification（65/65 tests PASS），Reviewer Review `PASS WITH NOTES`、QA `PASS`；Human 已接受 notes／limitations，G3-SB1 與 G3-SB2 正式 `COMPLETE`；進入 Gate 3 Final Gate Review

### Context（背景）

Gate 3 要處理三個彼此相關但必須分批控制的問題：Soft Delete Integrity（軟刪除完整性）、Canonical Stock ID（標準股票識別碼）以及 TPEx（櫃買中心）文件與實作邊界。Human 於 2026-08-20 核准本 Decision 的架構方向，並分別批准 G3-SB1 與 G3-SB2 實作；保持現有 Database Schema 不變，不引入 Migration Framework，不修改開發資料庫既有資料。

### Problem（問題）

- AI Trend Discovery（AI 熱門詞探索）若使用 generic upsert，可能把 `is_active = FALSE` 的關鍵字重新啟用，或改寫既有 `category`；disable 操作若採 upsert，也可能在不存在的 key 上建立停用資料。
- External exploration failure（外部探索失敗）與 Database configuration write failure（資料庫設定寫入失敗）的生命週期語意不同；若一律吞掉 exception，排程可能把未保存結果誤認為成功。
- 現有資料表以 bare ID（例如 `2330`、`NVDA`）表達股票，但 provider boundary 可能需要 `.TW`、`.TWO` 等 symbol；若直接把 provider symbol 當成 canonical ID，會污染跨來源 join key。
- Direct TPEx extractor（直接櫃買資料擷取器）目前沒有足夠需求與驗證證據；歷史 TPEx experiment 只有 handoff report，不能升級成已獨立驗證事實。

### Alternatives Considered（考慮方案）

#### Tracking Keyword Lifecycle

1. 所有使用情境共用 generic upsert，讓 discovery／disable 覆寫 conflict row。
2. 使用 purpose-specific commands（目的明確的命令）：discovery insert-only，disable update-only，保留 public user upsert 的既有行為。
3. 修改 Schema，加入 source ownership／override policy 等欄位後再統一處理。

#### Stock Identity and Provider Mapping

1. 將 `.TW`／`.TWO` 等 provider symbol 直接存入所有下游 `stock_id`。
2. MVP 採 bare canonical ID；market 與 provider symbol 的映射只在 provider boundary 形成並明確傳遞。
3. 立即導入 instrument master、複合主鍵、FK 與 migration framework。

#### TPEx Data Access

1. MVP 先採 market-aware yfinance mapping，由 market 決定 provider suffix。
2. 立即新增 direct TPEx extractor 與 fallback chain。

### Decision（決策）

Human 核准下列四項 Gate 3 architecture decisions：

1. **Soft Delete lifecycle**
   - AI discovery 對新 keyword 採 insert-only；conflict 時 `DO NOTHING`，不得重新啟用、改寫 category 或覆寫既有 row。
   - Disable 採 update-only；只把既有 row 的 `is_active` 設為 `FALSE` 並更新時間，不插入缺少的 keyword、不改 category。
   - External PTT／Gemini exploration failure 必須可觀測，並 skip current discovery write；目前可觀測介面是 stdout message，不宣稱已具 structured logging／alerting。
   - DB configuration write failure 不得被 external-service fallback catch 吞掉，必須向上傳遞。
   - Public user `upsert_tracking_keyword()` 與 hard-delete method 的既有 public behavior 不在 G3-SB1 變更範圍。
2. **MVP bare canonical ID contract**
   - `stock_prices.stock_id`、`daily_ml_features.stock_id` 與 `entity_mapping.stock_id` 的 MVP 系統識別採 bare canonical ID，例如 `2330`、`NVDA`。
   - `.TW`、`.TWO` 等 provider-specific symbol 不得直接當成 canonical persistence key。
   - 由 `format_provider_symbol(stock_id, market)` 在資料擷取邊界轉換 Provider Symbol（TWSE -> `.TW`、TPEX/OTC -> `.TWO`、US -> 原名、未知市場拋出 `ValueError`）。
   - `DataCleaner` 的 `clean_twse_stock_data` 與 `clean_yfinance_stock_data` 顯式保證輸出之 `stock_id` 欄位一律覆寫為 Bare Canonical ID。
3. **Market-aware yfinance；direct TPEx deferred**
   - 由 market-aware policy 選擇 yfinance symbol，不得再以單一 `.TW` 規則假設所有台灣市場。
   - Direct TPEx extractor／fallback 留待需求、合規性、可靠性與維運成本另行評估，Gate 3 不預設導入。
   - 歷史 TPEx experiment 僅標為 `REPORTED, NOT INDEPENDENTLY VERIFIED`，不得作為目前 Repository 已支援 direct TPEx 的證據。
4. **Minimal read-only development DB audit**
   - 最小必要欄位的唯讀資料稽核已完成，確認既有資料無 canonical 與 provider-suffixed ID 衝突。

### Rationale（理由）

- Purpose-specific commands 讓 discovery、disable 與 public user upsert 的 authority 清楚分離，能在不改 Schema 的 Small Batch 中修復 soft-delete lifecycle。
- External exploration 可以安全 skip，但 configuration write 是持久化責任；分開 failure semantics 可避免把未保存結果誤報為成功。
- Bare canonical ID 保持目前三個資料契約的 join key 穩定，provider formatting 留在 boundary，解決跨市場與備援資料整合之特徵孤立問題。
- Market-aware yfinance 是 MVP 的漸進方案；直接 TPEx extractor 會引入新的資料契約、錯誤語意、測試與維運範圍，目前證據不足以批准。

### Trade-offs（取捨）

- Discovery conflict 採 `DO NOTHING`，因此 AI 不會自動更新既有 keyword 的 category 或重新啟用；需要重新啟用時必須走具明確 authority 的 user/configuration path。
- External failure 目前只以 stdout observable；尚未建立 structured event、metric、alert 或 scheduler-level failure state。
- Market-aware yfinance 仍依賴第三方 provider 的 symbol convention 與資料可用性；它不等於 TPEx 官方資料契約或完整 fallback。
- 不做 data correction 可避免未授權變更，但既有資料若日後發現 variant／collision，仍需獨立 migration／correction decision。

### Affected Components（影響範圍）

G3-SB1 已實作／測試 paths：
- `src/loaders/db_writer.py`
- `src/extractors/trend_discover.py`
- `tests/test_tracking_keyword_integrity.py`

G3-SB2 已實作／測試 paths：
- `src/transform/data_cleaner.py`
- `main_etl_pipeline.py`
- `tests/test_canonical_stock_id.py`

Documentation Sync paths：
- `doc/evidence/DECISIONS.md`
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`
- `doc/governance/PROJECT_STATUS.md`

### Verification / Evidence（驗證／證據）

`VERIFIED THIS SESSION — G3-SB1 & G3-SB2 / Reviewer / QA evidence`：

- Reviewer Review：G3-SB1 `PASS WITH NOTES`、G3-SB2 `PASS WITH NOTES`。
- QA Verification：G3-SB1 `PASS`、G3-SB2 `PASS`。
- Windows Python 3.10 與 Dev Container Python 3.14.6 完整 suite：**65 tests 全部通過 (OK)**（Gate 2 33 + G3-SB1 15 + G3-SB2 17）。
- 靜態檢查：`py_compile` 通過、`git diff --check` 通過。
- G3-SB1 驗證：AI 探索不重新啟用停用詞、不改 category、外部失敗可觀測跳過、DB 寫入例外向上傳遞。
- G3-SB2 驗證：市場映射正確（TWSE `.TW`、TPEX/OTC `.TWO`、US 原名、未知市場拋出 `ValueError`）、`DataCleaner` 輸出 `stock_id` 乾淨無後綴、`ETLPipelineManager` 備援調度正確、`FeatureAggregator` 多市場 Join 無 key mismatch。

`VERIFIED THIS SESSION — independent minimal read-only development DB audit`：

- `stock_prices`：`2330 = 11` rows、`NVDA = 23` rows；`daily_ml_features` 同為 `2330 = 11`、`NVDA = 23`。
- 上述兩表沒有 `.TW`、`.TWO` 或 `6488` rows。
- `entity_mapping` 聚合為 `2330 / TWSE = 1`、`2382 / TWSE = 1`、`6488 / TWSE = 1`、`NVDA / US = 2`；canonical／provider-suffixed variant pairs = `0`。

Evidence boundary：G3-SB1 與 G3-SB2 均為 deterministic unit／mock／static evidence。Live PostgreSQL conflict／update／rowcount／transaction behavior、real PTT、real Gemini、real yfinance/TWSE 與 `.env` runtime 均為 `NOT VERIFIED`。

### Remaining Risks（剩餘風險）

- Live PostgreSQL write semantics 與 transaction behavior 尚未於真實 DB 執行（依安全隔離規則維持 Mock 驗證）。
- Stdout observability 不等於 production monitoring；scheduler／daily execution 的 retry、alert 與 run status 仍待後續 Gate 討論。
- 時間對齊與 Prediction Time Convention 留待 Gate 4 處理。
- 股票與輿情特徵工程研究完整對齊留待 Gate 5 處理。 ID implementation 仍未批准

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-006／見 DEC-022 總覽）**：以下至本 DEC 結尾
> （原文第 315～432 行區間）是同一則決策在較早時間點的草稿快照，與上方第 201～313 行的定案版本
> 逐段重複，並非另一則獨立決策。兩者差異：上方定案版本狀態為「G3-SB1 與 G3-SB2 均已實作」
> 「正式 `COMPLETE`」；下方草稿版本狀態仍寫「G3-SB1 已實作／測試，Canonical ID 尚未實作或驗證」
> 「Gate 3 `ACTIVE` 未關閉」，且 Affected Components 只列 G3-SB1（不含 G3-SB2）。
> 依 `CLAUDE.md` §16.1「只增不減」，下方草稿原文保留不動，不刪除、不改寫。
> **權威版本為上方第 201～313 行**；下方草稿內容過期，讀者不應引用其狀態欄位或 Affected Components 清單。

### Context（背景）

Gate 3 要處理三個彼此相關但必須分批控制的問題：Soft Delete Integrity（軟刪除完整性）、Canonical Stock ID（標準股票識別碼）以及 TPEx（櫃買中心）文件與實作邊界。Human 於 2026-08-20 核准本 Decision 的架構方向，並另行批准 G3-SB1 實作與最小唯讀 development database audit；這些批准不等於 Canonical ID write-path implementation、資料修正、Schema migration 或 Gate 3 close approval。

### Problem（問題）

- AI Trend Discovery（AI 熱門詞探索）若使用 generic upsert，可能把 `is_active = FALSE` 的關鍵字重新啟用，或改寫既有 `category`；disable 操作若採 upsert，也可能在不存在的 key 上建立停用資料。
- External exploration failure（外部探索失敗）與 Database configuration write failure（資料庫設定寫入失敗）的生命週期語意不同；若一律吞掉 exception，排程可能把未保存結果誤認為成功。
- 現有資料表以 bare ID（例如 `2330`、`NVDA`）表達股票，但 provider boundary 可能需要 `.TW`、`.TWO` 等 symbol；若直接把 provider symbol 當成 canonical ID，會污染跨來源 join key。
- Direct TPEx extractor（直接櫃買資料擷取器）目前沒有足夠需求與驗證證據；歷史 TPEx experiment 只有 handoff report，不能升級成已獨立驗證事實。

### Alternatives Considered（考慮方案）

#### Tracking Keyword Lifecycle

1. 所有使用情境共用 generic upsert，讓 discovery／disable 覆寫 conflict row。
2. 使用 purpose-specific commands（目的明確的命令）：discovery insert-only，disable update-only，保留 public user upsert 的既有行為。
3. 修改 Schema，加入 source ownership／override policy 等欄位後再統一處理。

#### Stock Identity and Provider Mapping

1. 將 `.TW`／`.TWO` 等 provider symbol 直接存入所有下游 `stock_id`。
2. MVP 採 bare canonical ID；market 與 provider symbol 的映射只在 provider boundary 形成並明確傳遞。
3. 立即導入 instrument master、複合主鍵、FK 與 migration framework。

#### TPEx Data Access

1. MVP 先採 market-aware yfinance mapping，由 market 決定 provider suffix。
2. 立即新增 direct TPEx extractor 與 fallback chain。

### Decision（決策）

Human 核准下列四項 Gate 3 architecture decisions：

1. **Soft Delete lifecycle**
   - AI discovery 對新 keyword 採 insert-only；conflict 時 `DO NOTHING`，不得重新啟用、改寫 category 或覆寫既有 row。
   - Disable 採 update-only；只把既有 row 的 `is_active` 設為 `FALSE` 並更新時間，不插入缺少的 keyword、不改 category。
   - External PTT／Gemini exploration failure 必須可觀測，並 skip current discovery write；目前可觀測介面是 stdout message，不宣稱已具 structured logging／alerting。
   - DB configuration write failure 不得被 external-service fallback catch 吞掉，必須向上傳遞。
   - Public user `upsert_tracking_keyword()` 與 hard-delete method 的既有 public behavior 不在 G3-SB1 變更範圍。
2. **MVP bare canonical ID contract**
   - `stock_prices.stock_id`、`daily_ml_features.stock_id` 與 `entity_mapping.stock_id` 的 MVP 系統識別採 bare canonical ID，例如 `2330`、`NVDA`。
   - `.TW`、`.TWO` 等 provider-specific symbol 不得直接當成 canonical persistence key。
   - market-to-provider mapping 的 ownership、呼叫介面與逐層傳遞方式，必須在後續 Canonical ID Small Batch brief 明列並取得 Human 批准；目前尚未實作或驗證。
3. **Market-aware yfinance；direct TPEx deferred**
   - 後續 provider mapping 應由 market-aware policy 選擇 yfinance symbol，不得再以單一 `.TW` 規則假設所有台灣市場。
   - Direct TPEx extractor／fallback 留待需求、合規性、可靠性與維運成本另行評估，Gate 3 不預設導入。
   - 歷史 TPEx experiment 僅標為 `REPORTED, NOT INDEPENDENTLY VERIFIED`，不得作為目前 Repository 已支援 direct TPEx 的證據。
4. **Minimal read-only development DB audit**
   - 核准最小必要欄位的唯讀資料稽核，用於評估既有 Canonical ID variant／collision risk；不核准任何 data correction、write、migration 或 Schema change。

### Rationale（理由）

- Purpose-specific commands 讓 discovery、disable 與 public user upsert 的 authority 清楚分離，能在不改 Schema 的 Small Batch 中修復 soft-delete lifecycle。
- External exploration 可以安全 skip，但 configuration write 是持久化責任；分開 failure semantics 可避免把未保存結果誤報為成功。
- Bare canonical ID 保持目前三個資料契約的 join key 穩定，provider formatting 留在 boundary；同時要求後續 brief 明訂 mapping ownership，避免以口頭方向掩蓋尚未設計的傳遞責任。
- Market-aware yfinance 是 MVP 的漸進方案；直接 TPEx extractor 會引入新的資料契約、錯誤語意、測試與維運範圍，目前證據不足以批准。

### Trade-offs（取捨）

- Discovery conflict 採 `DO NOTHING`，因此 AI 不會自動更新既有 keyword 的 category 或重新啟用；需要重新啟用時必須走具明確 authority 的 user/configuration path。
- External failure 目前只以 stdout observable；尚未建立 structured event、metric、alert 或 scheduler-level failure state。
- Bare ID 本身不足以消除不同 market 的同碼風險；market responsibility 與 provider mapping 若未在 SB2 清楚傳遞，仍可能產生錯誤 symbol 或 cross-market collision。
- Market-aware yfinance 仍依賴第三方 provider 的 symbol convention 與資料可用性；它不等於 TPEx 官方資料契約或完整 fallback。
- 不做 data correction 可避免未授權變更，但既有資料若日後發現 variant／collision，仍需獨立 migration／correction decision。

### Affected Components（影響範圍）

G3-SB1 已實作／測試 paths：

- `src/loaders/db_writer.py`
- `src/extractors/trend_discover.py`
- `tests/test_tracking_keyword_integrity.py`

Documentation Sync paths：

- `doc/evidence/DECISIONS.md`
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`
- `doc/governance/PROJECT_STATUS.md`

Canonical ID／market-provider mapping 的 affected paths 必須由後續 Human-approved Small Batch brief 精確列出；本 Decision 不授權修改 extractor、orchestrator、Schema、existing data 或 tests。

### Verification / Evidence（驗證／證據）

`VERIFIED THIS SESSION — frozen G3-SB1 diff / Reviewer / QA evidence`：

- Frozen SHA-256 保持一致：`src/loaders/db_writer.py` = `C49F257FAAF362C95FA74F73038019FDC1D2971A222F4B554C7A1C649D0115D7`；`src/extractors/trend_discover.py` = `8D53210E040A66A8A6FBB31C3CB0491E81F0A4B108576E4A619FF57FA2AD8336`；`tests/test_tracking_keyword_integrity.py` = `104104DD6FEAD15B9AEA9E9C96FA0E93C8B6DCFC9D62C319911434894AE4BE19`。
- Reviewer Review：`PASS WITH NOTES`；QA：`PASS — approved mock/static scope`；Reviewer Evidence Review：`PASS WITH NOTES`。
- Windows Python 3.10 與 Dev Container Python 3.14.6 的完整 suite 均為 48 tests／`OK`，組成為 Gate 2 的 33 tests 加 G3-SB1 的 15 tests；相關 `py_compile` 與 diff／whitespace checks 通過。
- Reviewer correction 前原始 Windows suite 的 48 tests 曾有 2 個 `CP950` stdout encoding errors；原始 failure evidence 已保留，修正後兩個環境才取得 48／48。
- G3-SB1 tests 驗證 SQL contract／mock behavior：discovery conflict 不更新既有 row、disable 不 insert／不改 category、external exploration failure skip write、DB write exception propagation，以及 discovery path 不呼叫 generic `upsert_tracking_keyword()`。
- Frozen static diff inspection（凍結靜態差異檢查）確認 public user `upsert_tracking_keyword()` implementation 未變；這不是 unit／mock test claim。

`REPORTED, NOT INDEPENDENTLY VERIFIED`：

- Implementation pre-fix 7 failures／4 errors，以及 intermediate 47／48 結果來自 implementation handoff；保留為歷史 evidence，不升級為本 Decision 的獨立驗證。
- Historical TPEx experiment 只有先前報告，沒有本次可重現的 Repository evidence。

`VERIFIED THIS SESSION — independent minimal read-only development DB audit`：

- `stock_prices`：`2330 = 11` rows、`NVDA = 23` rows；`daily_ml_features` 同為 `2330 = 11`、`NVDA = 23`。
- 上述兩表沒有 `.TW`、`.TWO` 或 `6488` rows。
- `entity_mapping` 聚合為 `2330 / TWSE = 1`、`2382 / TWSE = 1`、`6488 / TWSE = 1`、`NVDA / US = 2`；canonical／provider-suffixed variant pairs = `0`。
- Audit 只讀最小必要欄位，使用 read-only transaction，完成後 rollback 並關閉 connection。
- 這項 audit 只支持目前沒有觀察到既有 ID variant collision；不支持 G3-SB1 live write semantics，也不授權 existing-data correction。

Evidence boundary：G3-SB1 只有 SQL-contract／mock／static evidence。Live PostgreSQL conflict／update／rowcount／transaction behavior、real PTT、real Gemini、real ETL 與 `.env` runtime 均為 `NOT VERIFIED`。

### Remaining Risks（剩餘風險）

- G3-SB1 Documentation Review 為 `PASS WITH NOTES`；Human 已接受 G3-SB1 notes／limitations 並批准正式標記 `COMPLETE`。Gate 3 仍為 `ACTIVE`，尚未 close。
- Live PostgreSQL write semantics 與 transaction behavior 尚未驗證；mock SQL inspection 不能替代 database integration evidence。
- Stdout observability 不等於 production monitoring；scheduler／daily execution 的 retry、alert 與 run status 仍待後續 Gate 討論。
- Canonical ID 的 market-to-provider mapping ownership、參數傳遞、unknown-market behavior、US／TWSE／TPEx test matrix 與候選 approved paths 尚待 SB2 brief 與 Human 批准。
- Read-only audit 目前沒有發現 collision evidence；existing data correction 未被授權，也不得因「目前為零」推論未來不會發生。
- 下一個 Human decision 是審批 Canonical ID Small Batch brief；現在不得開始 Canonical ID implementation。


---

## DEC-005: Dual-Mode Prediction Architecture & Time Alignment Convention（雙模式預測架構與時間對齊約定）

- 狀態：APPROVED（2026-08-20 由 Project Owner 拍板核准；狀態行格式於 2026-09-08 正規化，原格式見 `doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_B13_fix_evidence.json`）
- **Deciders（決策者）**：Human（Project Owner）、Architect Agent、PM / Orchestrator Agent
- **Date（日期）**：2026-08-20
- **Relevant Gate（關聯關卡）**：Gate 4 — Prediction Time Convention & Time Alignment

### Context / Problem（背景／問題）

在進入 Phase 3 機器學習模型訓練與複雜特徵工程前，現行系統存在前視偏誤（Look-ahead Bias）、週末/假期輿情丟失，以及 PTT 時間戳記粗糙寫死三大缺陷：

1. FeatureAggregator 直接採 trade_date == post_date 合併，若 T 日特徵包含 T 日 13:30 收盤後之輿情，並用以預測 T 日自身表現，會造成嚴重的「未來資訊洩漏」。
2. 週六、週日與國定假期發酵的重大群體情緒（DSSW 雜訊交易者信念），在現行 Left Join 股價交易日曆時會被全數丟棄（Dropped）。
3. DataCleaner._parse_date() 強制寫死 12:00:00 與 current_year，無法支援秒級時間，且 1 月爬取 12 月歷史文章時會產生跨年年份錯置。
4. Project Owner (Human) 正式提出系統核心願景——【雙模式預測架構（Dual-Mode Prediction Architecture）】，要求底層共用資料庫，但特徵工程層需具備參數化彈性，同時支援「模式一：盤前即時反應（08:30 Cutoff）」與「模式二：盤後動能延續（15:30 Cutoff）」。

### Alternatives Considered（考慮方案）

#### Prediction Point & Target Convention
1. **單一 Option A（盤後預測次日）**：固定於 15:30 預測 T+1 收盤，缺乏對開盤跳空與隔夜衝擊的敏捷捕捉能力。
2. **單一 Option B（盤前預測當日）**：固定於 08:30 預測當日開盤/日內，無法充分利用當日完整 OHLCV 與技術動能指標。
3. **雙模式預測架構（Dual-Mode Architecture，核准方案）**：共用同一套 PostgreSQL 價量與輿情表，特徵工程函式支援 cutoff_time 參數化，分離盤前事件衝擊與盤後波段動能。

#### Weekend & Holiday Alignment
1. **單純丟棄非交易日文章**：嚴重遺失週末重要情緒，造成特徵抽樣偏誤。
2. **簡單平均回填至前一交易日**：將週六/週日文章填入週五，構成嚴重前視偏誤（週五預測使用了週末才發生的事）。
3. **次一交易日歸併法（Roll-Forward Mapping，核准方案）**：將休市期間及過 cutoff 的文章，精確向後歸併至次一交易日特徵窗口。

### Decision（決策）

1. **雙模式預測架構（Dual-Mode Prediction Architecture）**：
   - 底層共用 stock_prices 與 market_articles。
   - 特徵聚合層支援參數化截止點：
     - **模式一（盤前即時反應模型 / Pre-Market Shock）**：08:30 Cutoff，輸入昨夜美股與隔夜/週末討論，預測 T 日開盤反應。
     - **模式二（盤後動能延續模型 / Post-Market Momentum）**：15:30 Cutoff，輸入當日完整 OHLCV 價量與全日情緒，預測 T+1 日收盤報酬。
2. **次一交易日歸併法（Roll-Forward Mapping）**：
   - 透過 map_timestamp_to_trading_day 依交易日曆進行確定性歸併：
     - 若發文時間 > Cutoff，歸併至下一交易日（T_next）。
     - 若發文時間 <= Cutoff 且為休假日，歸併至下一交易日（T_next）。
     - 若發文時間 <= Cutoff 且為交易日，歸入當日（T）。
   - 週五盤後、週六、週日與週一盤前文章全數無損累積至週一特徵列。
3. **PTT 日期時間解析強化與跨年防護**：
   - parse_ptt_datetime 支援標準 RFC/ANSI 內頁格式（Wed Aug 20 14:25:36 2026）、ISO 8601 格式與短日期 MM/DD。
   - 引入參考時間比對，若參考時間為 1~3 月且文章為 10~12 月，智慧推論年份為 Y-1，解決跨年 bug。
4. **漸進式小批次實作策略**：
   - **G4-SB1**：落實共用之 PTT 精確時間解析器與交易日曆 Roll-Forward 歸併邏輯。
   - **G4-SB2**：以模式二（盤後 15:30）為基線完成特徵聚合與 Target 0 洩漏驗證，並保持特徵管線支援模式一之彈性。

### Rationale（理由）

- 雙模式架構兼顧了「開盤前事件驅動當沖/避險」與「收盤後波段動能跟隨」兩種互補的量化交易情境，展現深厚的金融工程設計水準。
- 次一交易日歸併法在數學上嚴格確保「預測當下只使用已發生的歷史資訊」，徹底杜絕 Look-ahead Bias，同時解決週末輿情遺漏問題。
- 智慧跨年推論消除時間解析邊界隱患，避免產生未來時間戳記。

### Affected Components（影響範圍）

- src/transform/data_cleaner.py（新增 parse_ptt_datetime，支援參考時間與跨年解析）
- src/transform/feature_aggregator.py（新增 map_timestamp_to_trading_day、assign_trading_days_to_articles，支援 cutoff_time 參數化）
- tests/test_time_alignment.py（新增 13 項單元、跨年、跨週末與多模式測試）
- doc/evidence/DECISIONS.md（新增 DEC-005）
- doc/spec/SDD_Financial_Sentiment_System_v1.md（同步雙模式架構與時間對齊邊界）
- doc/governance/PROJECT_STATUS.md（記錄 Gate 4 實作進度）

### Verification / Evidence（驗證／證據）

VERIFIED THIS SESSION — G4-SB1 implementation & automated test suite：

- Windows Python 3.10 完整測試套件 **78 tests 全數通過 (78/78 OK)**，耗時 0.26s。
  - Gate 2 (DB/Cache/Strict NLP): 33 tests
  - Gate 3 (Soft Delete & Canonical ID): 32 tests (15 + 17)
  - Gate 4 G4-SB1 (PTT Time & Roll-Forward Alignment): 13 tests
- python -m py_compile 通過 data_cleaner.py、feature_aggregator.py 與 test_time_alignment.py。
- git diff --check 通過。
- 單元測試驗證涵蓋：
  - 標準 PTT 內頁格式、ISO 格式解析。
  - 跨年智慧年份推論（1 月執行爬蟲解析 12/31 文章正確判定為前一年）。
  - 週五盤後（>15:30）、週六、週日全天發文無損向後滾動歸併至週一交易日。
  - 連續假期（如 8/20 休市）文章無損滾動歸併至開盤日（8/21）。
  - 雙模式 Cutoff（15:30 vs 08:30）邊界切分正確。
  - FeatureAggregator 在週末文章情境下，週一特徵列完整累積週末所有文章聲量與平均情緒。

Evidence boundary：本批為單元與 mock 演算法驗證；live 爬蟲線上即時內文爬取、實體資料庫特徵批次持久化為 NOT VERIFIED。


---

## DEC-006: Institutional Feature Engineering & Antweiler-Wilder Protocol（機構級特徵工程與 Antweiler-Wilder 指標協定）

- 狀態：APPROVED（2026-08-20 由 Project Owner 拍板核准；狀態行格式於 2026-09-08 正規化，原格式見 `doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_B13_fix_evidence.json`）
- **Deciders（決策者）**：Human（Project Owner）、Architect Agent、PM / Orchestrator Agent
- **Date（日期）**：2026-08-20
- **Relevant Gate（關聯關卡）**：Gate 5 — Research Requirements Extraction & Feature Engineering

### Context / Problem（背景／問題）

在完成時間對齊與零前視偏誤防護（Gate 4）後，系統需從單純的平均情緒分數與 OHLCV 價量，升級至學術研究支持的機構級特徵矩陣，以捕捉散戶雜訊交易者信念與動能反轉：

1. 單一情緒平均值（sentiment_mean）無法表達多空力量懸殊程度與群體共識度。
2. 缺乏捕捉超買超賣動能反轉的技術指標（RSI-14）與衡量市場風險水平的滾動歷史波動率（Rolling Volatility 5D / 20D）。
3. 外部量化套件（如 TA-Lib）需依賴本機 C/C++ 編譯環境，跨平台（Windows / Dev Container / Linux CI）建置極易失敗。

### Alternatives Considered（考慮方案）

#### Feature Calculation Engine
1. **導入 TA-Lib C-Extension**：執行效率高，但需本機 C 編譯工具鏈，增加部署複雜度與環境脆弱性。
2. **純 NumPy / Pandas 向量化實作（核准方案）**：零外部沉重依賴，所有指標（Wilder's RSI、滾動波動率、Laplace Antweiler 公式）採純向量化運算，確保 100% 跨平台可重現性與快速執行。

### Decision（決策）

1. **Antweiler & Frank (2004) 輿情量化指標**：
   - **看多指數（Bullishness Index $）**： = \ln((1 + M_t^{	ext{Pos}}) / (1 + M_t^{	ext{Neg}}))$，採 Laplace 平滑（+1）徹底防範除以零與 $\ln(0)$。
   - **一致性指數（Agreement Index $）**： = 1 - \sqrt{1 - ((M_t^{	ext{Pos}} - M_t^{	ext{Neg}}) / (M_t^{	ext{Pos}} + M_t^{	ext{Neg}}))^2}$，量化市場觀點集中度，值域鎖定於 $[0.0, 1.0]$。
2. **技術動能與波動率指標**：
   - **RSI-14**：Wilder's 指數移動平滑（$lpha = 1/14$），初始不足 14 天補中立值 .0$。
   - **5 日 / 20 日滾動歷史波動率**：1 日對數報酬率之滾動標準差乘上 $\sqrt{252}$ 年化，初始不足補 .0$。
3. **多股票分組隔離規範**：所有時序滑動、EMA 與滯後特徵嚴格在 groupby('stock_id') 下執行，杜絕跨股票污染。
4. **特徵輸出契約**：FeatureAggregator 輸出 18 項標準特徵矩陣。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 項」
> 為 Gate 0 時期寫定的舊契約數字。經 `src/ml/model_trainer.py:L17-41` 實測，現行特徵矩陣為
> **`LEGACY_17`**（17 欄，見 `doc/upgrade/contracts/FEATURE_REGISTRY.md`）。本行原文保留不動
> （`CLAUDE.md` §16.1），此處僅補充現行權威數字之指標。

### Rationale（理由）

- 純向量化演算法執行 89 項測試僅需 ~0.5 秒，完全滿足 MVP 與生產環境之效能要求，且消除了外部 C 編譯工具鏈風險。
- Antweiler 與 Wilder 指標在金融計量學中有數十年實證支持，能提供機器學習模型更豐富的非線性特徵空間。

### Affected Components（影響範圍）

- doc/research/RESEARCH_REQUIREMENTS.md（建立研究需求單一真實規格）
- src/transform/feature_aggregator.py（實作 compute_bullishness_index, compute_agreement_index, compute_rsi, compute_rolling_volatility）
- tests/test_research_features.py（新增 Antweiler、RSI、波動率與多股票隔離單元測試）
- doc/evidence/DECISIONS.md（新增 DEC-006）
- doc/spec/SDD_Financial_Sentiment_System_v1.md（同步特徵契約）
- doc/governance/PROJECT_STATUS.md（更新 Gate 5 進度）

### Verification / Evidence（驗證／證據）

VERIFIED THIS SESSION — G5-SB1 / G5-SB2 implementation & test suite：

- Windows Python 3.10 完整測試套件 **89 tests 全數通過 (89/89 OK)**，耗時 0.51s。
- 專項測試驗證涵蓋：
  - Antweiler 看多指數 Laplace 平滑、多空勢均力敵與零文章邊界。
  - Antweiler 一致性指數極限共識（1.0）、最大分歧（0.0）與部分共識。
  - RSI-14 恆等價格（50.0）、連續大漲（100.0）、連續大跌（0.0）與 Warm-up 補值。
  - 5D/20D 滾動年化波動率數學檢驗。
  - 跨股票（2330 大漲 vs NVDA 大跌）特徵分組隔離與 18 欄位契約產出。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：同上——本行
> 「18 欄位」為舊契約數字，現行為 `LEGACY_17`（17 欄）。原文保留不動，見 DEC-006 上方
> 第一則補充註記之完整說明。

Evidence boundary：本批為演算法與向量化純數學驗證；實體資料庫特徵持久化與 Phase 3 模型交叉驗證為 NOT VERIFIED。

---

## DEC-007: Multi-Model Tournament & Alpha Attribution Protocol（機器學習多模型橫向競技與 Alpha 歸因協定）

- 狀態：APPROVED（已核准，核准日期見下方 Date 欄；狀態行格式於 2026-09-08 正規化，原格式見 `doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_B13_fix_evidence.json`——第 6 案執行中發現，非 PO 原始列表項目，見該檔 SCOPE_DEVIATION_DISCLOSED）
- **Date**：2026-08-20
- **Authors**：PM / Orchestrator Agent, Architect Agent, Implementation Agent
- **Approved by**：Project Owner (Human)

### Context / Problem（背景／問題）

在 Phase 3 機器學習模型訓練階段，必須解決三大核心挑戰：
1. **防止金融時序前視偏誤（Zero Look-ahead Bias）**：嚴禁使用隨機 K-Fold 切分，特徵前處理轉換器（Scaler）絕不能將測試集的極端值或分佈洩漏至訓練集。
2. **多模型橫向競技（Multi-Model Tournament）**：依據 PRD 承諾，必須橫向評比線性基準（Logistic Regression）、裝袋集成（Random Forest）與梯度提升樹（LightGBM, XGBoost）等多種演算法。
3. **社群輿情 Alpha 歸因量化（Alpha Attribution）**：必須建立嚴格的對照實驗，量化回答「加入 Antweiler 看多/一致性指數與社群情緒後，究竟能否為不同模型帶來統計與經濟顯著的預測提升？」。

### Alternatives Considered（考慮方案）

1. **Option A — 單一模型 + 隨機 K-Fold（不採納）**：
   - 僅使用 Random Forest，並採標準 5-Fold 隨機切分。
   - 缺陷：造成嚴重的「時間之箭倒流」與未來資料洩漏，產生虛假高準確率；無法回答不同演算法對情緒特徵的吸收能力差異。
2. **Option B — 重型深度學習架構（PyTorch / LSTM / Transformer）（不採納）**：
   - 引入深度學習時序模型。
   - 缺陷：算力成本高昂（需 GPU）、特徵可解釋性低（黑盒子）、訓練時間冗長且在小樣本（日線）易過擬合。
3. **Option C — Walk-Forward 時序前向切分 + 四大模型 8 組平行對照實驗（採納）**：
   - 時序切分：以市場唯一交易日（Unique Trading Dates）實作滑動/擴展窗口驗證，保證多股票全域日期對齊與訓練/測試集索引零交集。
   - 實驗對照：建立 4 種演算法 x 2 組特徵集（純價量 9 特徵 vs 多模態 18 特徵）= 8 組平行對照實驗。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 特徵」
> 為舊契約數字，現行為 `LEGACY_17`（17 欄，見 `doc/upgrade/contracts/FEATURE_REGISTRY.md`）。
> 原文保留不動。

   - 零洩漏保證：Scaler 嚴格在各 Fold 的 Train Set 內部擬合。
   - 即時推論：評選出最佳 Champion Model，產出明日漲跌、信心機率與 Top 3 關鍵驅動特徵。

### Decision（最終決策）

1. **時序切分**：以 WalkForwardSplitter 作為唯一的交叉驗證引擎。
2. **模型競技矩陣**：統一封裝 LogisticRegression、RandomForest、LightGBM、XGBoost 四大模型。
3. **8 組平行對照實驗**：
   - 控制組：EXP-1A ~ EXP-4A（純價量 9 欄位特徵，0 輿情污染）。
   - 實驗組：EXP-1B ~ EXP-4B（多模態 18 欄位特徵，含 Antweiler B_t, A_t 與時序滯後）。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 欄位」
> 同樣為舊契約數字，現行為 `LEGACY_17`（17 欄）。原文保留不動，完整說明見本 DEC 上方
> Alternatives Considered 小節之補充註記。

4. **Alpha 歸因評估標準**：
   \Delta \text{Alpha}_{\text{Model}_k} = \text{Performance}(\text{Model}_k, \text{MultiModal}) - \text{Performance}(\text{Model}_k, \text{PureTechnical})
5. **即時推論契約**：實作 StockTrendPredictor，輸出明日預測（UP/DOWN）、信心機率值（0.0 ~ 1.0）與前 3 大驅動因子，供 Phase 4 Streamlit BI 儀表板串接。

### Affected Components（影響範圍）

- src/ml/time_series_split.py（P3-SB1 時序切分引擎）
- src/ml/baseline_models.py（P3-SB2 四大基準模型與純技術隔離控制組）
- src/ml/model_trainer.py（P3-SB3 多模態特徵融合與四大模型競技訓練器）
- src/ml/evaluator.py（P3-SB4 8 組實驗 Alpha 歸因與多模型排行榜）
- src/ml/predictor.py（P3-SB4 冠軍模型即時推論引擎）
- 	ests/test_time_series_split.py, 	ests/test_baseline_models.py, 	ests/test_model_trainer.py, 	ests/test_ml_evaluator.py（24 項專項單元與整合測試）

### Verification / Evidence（驗證／證據）

VERIFIED THIS SESSION — Phase 3 (P3-SB1 ~ P3-SB4) 全套實作與 113 項自動化測試：
- Windows Python 3.10 測試套件 **113 tests 全數 PASS (113/113 OK)**，耗時 0.945s。
- 驗證覆蓋：
  1. Walk-Forward 邊界無交集、時間單調遞增、多股票全域日期對齊。
  2. 控制組特徵提取嚴格排除 8 欄位情緒特徵（0 輿情污染）。
  3. Scaler 嚴格在 Train Set Fit，測試集統計資訊 0 洩漏。
  4. 8 組平行實驗排行榜生成、Delta F1 / Delta Return Alpha 歸因計算無誤。
  5. 冠軍模型序列化保存與載入後推論結果 100% 精確還原。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-015／見 DEC-022 總覽）**：以上「4 大模型 8 組
> 平行對照實驗」的方法論敘述未標註其成立條件——GOV-02 已實測確認（`doc/governance/PROJECT_STATUS.md`
> §13.3／`CLAUDE.md` §13.3）：在 **host 環境**（Windows，缺 `sklearn`／`lightgbm`／`xgboost`）下，
> `random_forest`／`lightgbm`／`xgboost` 三個模型名稱實際對映到同一個 `_FallbackTreeEnsembleClassifier`
> fallback 類別，「4 種演算法」在 host 上實際只有 2 種相異實作，方法論意義上的「橫向競技」
> 在 host 環境不成立，僅在 **dev container**（真實 sklearn／lightgbm／xgboost）內才成立。
> 原文保留不動，此為評估本 DEC 之 Verification 宣稱時應併同閱讀的限制條件。

---

## DEC-008: Streamlit Institutional Visual Architecture, Dual-Axis Interactive Charts & Zero-Dependency Fallback（Streamlit 機構級視覺化架構、雙 Y 軸互動圖表與零依賴平滑回退設計）

- 狀態：APPROVED（已核准，核准日期見下方 Date 欄；狀態行格式於 2026-09-08 正規化，原格式見 `doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_B13_fix_evidence.json`）
- **Date**：2026-08-20
- **Authors**：PM / Orchestrator Agent, Architect Agent, Implementation Agent
- **Approved by**：Project Owner (Human)

### Context / Problem（背景／問題）

在 Phase 4 視覺化與即時預測 UI 開發階段，面臨四大核心工程與互動體驗需求：
1. **端到端數據流即時可視化**：必須將 Phase 2 特徵工程輸出的 18 欄位多模態特徵矩陣、Phase 3 訓練之最佳冠軍模型（`StockTrendPredictor`）與 PTT 原始文章，無縫串接成統一的互動操作終端。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 欄位」
> 為舊契約數字，現行為 `LEGACY_17`（17 欄，見 `doc/upgrade/contracts/FEATURE_REGISTRY.md`）。
> 原文保留不動。
2. **金融色彩語彙適配**：台灣市場與國際美股市場之漲跌色彩習慣相反（台股：紅漲綠跌；美股：綠漲紅跌），系統需具備靈活切換機制，避免認知混淆。
3. **模型決策可解釋性（Explainable AI）**：為消除量化模型的黑盒子疑慮，介面必須清晰呈現明日預測方向、置信度機率，以及前 3 大關鍵驅動因子（Top 3 Drivers）之中文可讀名稱與貢獻權重。
4. **輕量化 CI/CD 與無依賴回退安全網**：在無 GUI 瀏覽器、未安裝 Streamlit/Plotly 的極簡 Headless 或單元測試環境中，模組必須保證 0 崩潰且能秒級完成資料契約檢驗。

### Alternatives Considered（考慮方案）

1. **Option A — 傳統靜態 Matplotlib / Seaborn 圖表（不採納）**：
   - 伺服器端將圖表渲染為靜態 PNG 圖片並輸出。
   - 缺陷：缺乏滑鼠懸停同步 Tooltip、無法縮放平移、視覺質感難以達到金融終端標準。
2. **Option B — 外部商業套裝 BI（Tableau / PowerBI）（不採納）**：
   - 將特徵與預測匯出至商業 BI 平台。
   - 缺陷：無法一鍵直接嵌入 Python 原生訓練之模型即時推論，無法納入 Git 程式碼版本控制與自動化測試流水線。
3. **Option C — Streamlit + Plotly 雙 Y 軸互動圖 + 自適應色彩 + 零依賴 Fallback 架構（採納）**：
   - 介面骨架：採用 Streamlit 建構全螢幕寬版終端，注入金融深色模式 CSS（`#0E1117` 主色調）。
   - 互動圖表：採用 Plotly 雙層 Subplots（上層 70% 日 K 線 + MA5/20，下層 30% 社群情緒長條圖 + 0.5 基準線），支援統一 Tooltip 懸停同步顯示開高低收與 Antweiler $B_t$ 指標。
   - 策略與解釋：提供累積報酬回測曲線（AI vs. Buy & Hold）、Top 8 特徵重要性長條圖、AI 預測卡片與 8 組平行實驗多模型排行榜。
   - 輿情明細：內嵌 PTT 文章即時篩選器（多空標籤、4 種排序、標題關鍵字搜尋）。
   - 零依賴回退：實作 `_FallbackPlotlyFigure` 與 `_FallbackStreamlit`，確保在極簡測試環境下 100% 可測且毫秒級通過。

### Decision（最終決策）

1. **主題與色彩語彙**：建立 `src/ui/styles.py`，定義深色模式 CSS 與 `get_market_colors()`，嚴格依市場參數（TW / US）動態指派紅綠色碼。
2. **特徵與文章載入契約**：建立 `src/ui/data_loader.py`，支援 PostgreSQL 讀取與 18 欄位離線高仿真 Fallback 資料產生器，保證 0 異常中斷。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 欄位」
> 為舊契約數字，現行為 `LEGACY_17`（17 欄）。原文保留不動。另外，DEC-012 方案 B（UG-G1-SB2）已將
> 本行所述之「離線高仿真 Fallback 資料產生器」改為 `DataMode.ERROR`（DB 連線失敗時顯示明確錯誤，
> **不**自動退回模擬資料），與本行原始敘述的設計已不同，詳見 DEC-012。
3. **Plotly 多維互動圖表**：建立 `src/ui/charts.py`，實作雙 Y 軸 K 線/情緒圖、回測累積報酬曲線與特徵貢獻長條圖。
4. **AI 決策與明細元件**：建立 `src/ui/components.py`，實作預測面板、Top 3 驅動因子解析、8 組多模型排行榜與 PTT 多功能明細表。
5. **應用主入口**：於 `app.py` 整合上述所有模組，提供直觀之側邊欄控制與一鍵切換。

### Affected Components（影響範圍）

- `app.py`（Streamlit 主應用入口）
- `src/ui/__init__.py`（UI 模組入口與公開 API 導出）
- `src/ui/styles.py`（深色主題 CSS、色彩定義與 KPI 卡片 HTML 渲染）
- `src/ui/data_loader.py`（快取資料載入器與離線 Fallback 資料產生）
- `src/ui/charts.py`（Plotly 雙 Y 軸 K 線、情緒長條圖與回測曲線）
- `src/ui/components.py`（AI 推論面板、Top 3 驅動因子、排行榜與 PTT 表格）
- `tests/test_ui_contracts.py`（11 項 UI 樣式、資料契約、圖表與元件專項測試）
- `doc/archive/PHASE4_BI_PLAN.md`（Phase 4 BI 儀表板實作計畫書）
- `doc/governance/PROJECT_STATUS.md`（專案狀態同步）

### Verification / Evidence（驗證／證據）

`VERIFIED THIS SESSION — Phase 4 (P4-SB1 ~ P4-SB4) 全套實作與 124 項自動化測試`：
- Windows Python 3.10 測試套件 **124 tests 全數 PASS (124/124 OK)**，耗時 0.933s。
- 驗證覆蓋：
  1. 台股紅漲綠跌與美股綠漲紅跌色碼精確性檢驗。
  2. KPI 卡片 HTML 標籤結構與 Delta 渲染檢驗。
  3. 可選股票清單與 18 欄位多模態特徵資料契約檢驗。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 欄位」
> 為舊契約數字，現行為 `LEGACY_17`（17 欄）。原文保留不動。
  4. PTT 輿情文章格式、標籤篩選與關鍵字搜尋邏輯檢驗。
  5. 雙 Y 軸日 K 線、量化回測曲線與特徵重要性圖表資料結構檢驗。
  6. 冠軍模型即時推論與 Top 3 驅動因子可解釋性輸出契約檢驗。

---

## DEC-009: Thematic Concept Basket Mapping, Sentiment Spillover & Radar UI

- 狀態：APPROVED（PO 2026-09-08 追認核准——原始核准日期不可考，經跨文件狀態一致性稽核第 6 案反查發現本 ADR 自始缺少狀態欄位；歷史已實作見 `TRACEABILITY.md` §3.2「AI 題材概念股映射與知識庫」SB-TH1 列；核准歷史決定，不背書過期內文——已知內文缺陷見 DEC-022 缺陷索引 `doc/evidence/DECISIONS.md:1603`）

### Context / Problem（背景／問題）

在既有系統架構中存在嚴重的非結構化資料斷層：
1. **題材文章 100% 拋棄（Drop）**：`trend_discover.py` 與 `ptt_scraper.py` 成功抓取並計算了大量市場熱門概念詞（如：`矽光子`、`散熱模組`、`CoWoS`、`AI伺服器`），但因 `entity_mapping` 僅有一對一個股名稱映射，所有非個股代碼的產業題材文章在特徵工程聚合時因無對應 `stock_id` 而被 100% 拋棄。
2. **冷門日情緒鈍化**：當某檔概念股（如 `3081 聯亞`）當天無直接個股討論時，特徵工程只能填補中立 0.5，無法反映其所屬產業題材（如矽光子飆漲）的實質動能。
3. **終端介面缺乏題材連動**：使用者無法在 UI 儀表板檢視當前熱門題材多空指數與成分股，亦無法從題材一鍵切換預測標的。

### Alternatives Considered（考慮方案）

1. **Option A — 強行將題材詞硬寫入 `entity_mapping` 對應單一代表股（不採納）**：
   - 例：將 `矽光子` 硬對應 `2330 台積電`。
   - 缺陷：破壞 1-to-1 實體對應原則，忽略其他關鍵受惠概念股（如聯亞、光聖），資料血緣混亂。
2. **Option B — 大規模擴充特徵欄位至 25+ 欄（不採納）**：
   - 新增 `theme_sentiment_1`, `theme_sentiment_2` 等多個獨立欄位。
   - 缺陷：破壞 Phase 3 嚴格建立的 18 欄位 ML 資料契約（`ALL_MULTIMODAL_FEATURE_COLS`），需要全面重新訓練與重構所有機器學習模型。
3. **Option C — 獨立 1-to-N 知識圖譜 + 動態原位加權融合 + 頂部題材雷達卡片（採納）**：
   - 儲存層：新增 `theme_stock_mapping` 獨立表，支援一題材多成分股與關聯權重（如矽光子 ➔ 聯亞 1.0、光聖 1.0、台積電 0.8）。
   - 探索層：升級 Gemini Prompt 支援單次請求同步回傳題材與成分股（`{"trends": [{"theme": ..., "stocks": [...]}]}`），API 次數零增加。
   - 特徵層：採「直接個股情緒（70%）+ 題材溢出情緒（30%）」原位加權融合；無直接文章時採 100% 題材溢出補位。
   - ML 契約：**18 欄位特徵契約與數值型態 100% 保持不變**，現有冠軍隨機森林與 XGBoost 模型零誤差無縫推論。
   - 展示層：Streamlit 頂部渲染深色題材雷達卡片（聲量、看多指數 $B_t$、多空標籤），支援點擊成分股標籤秒速（<10ms）切換主畫面預測。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：以上「18 欄位」
> （Option B 段與 Option C「ML 契約」段共 2 處）為舊契約數字，現行為 `LEGACY_17`（17 欄，見
> `doc/upgrade/contracts/FEATURE_REGISTRY.md`）。「ML 契約」段的「**100% 保持不變**」「**零誤差
> 無縫推論**」屬 `CLAUDE.md` §9.2 禁用詞——沒有任何一次驗證記錄逐一比對過新舊特徵矩陣在所有
> 數值上零誤差，此宣稱缺乏對應證據支撐。原文保留不動，此處僅標註其為未經驗證之絕對化敘述。

### Decision（最終決策）

1. **Schema 升級**：在 `database/schema.sql` 與 `init_db.py` 新增 `theme_stock_mapping`，內建 4 大核心題材（矽光子、散熱模組、CoWoS、AI伺服器）種子資料。
2. **DB 操作**：於 `src/loaders/db_writer.py` 實作 `upsert_theme_stock_mapping()` 與 `fetch_all_theme_baskets()`。
3. **AI 探索升級**：升級 `src/extractors/trend_discover.py` 支援雙重現代結構解析與傳統向下相容。
4. **特徵引擎升級**：升級 `src/transform/feature_aggregator.py`，實作 70/30 動態加權融合演算法與 100% 溢出補位。
5. **UI 題材雷達**：於 `src/ui/components.py` 實作 `render_thematic_radar()`，於 `src/ui/data_loader.py` 實作 `load_thematic_radar_data()`，並在 `app.py` 實作一鍵選股秒速切換。

### Affected Components（影響範圍）

- `database/schema.sql` & `database/init_db.py`
- `src/loaders/db_writer.py`
- `src/extractors/trend_discover.py`
- `src/transform/feature_aggregator.py`
- `main_etl_pipeline.py`
- `src/ui/data_loader.py`
- `src/ui/components.py`
- `app.py`
- `tests/test_thematic_mapping.py` (4 tests)
- `tests/test_thematic_feature_spillover.py` (4 tests)
- `tests/test_ui_contracts.py` (+2 tests, total 13 tests)

### Verification / Evidence（驗證／證據）

`VERIFIED THIS SESSION — Thematic Trends 全套升級與 147 項自動化測試`：
- 全套自動化測試套件 **147 tests 全數 PASS (147/147 OK)**，耗時 1.827s。
- 驗證覆蓋：
  1. `theme_stock_mapping` 建表語法、外鍵與 4 大種子資料契約。
  2. Gemini 現代 JSON 結構雙重解析與傳統結構安全相容。
  3. 題材情緒 100% 溢出補位數學精確性。
  4. 個股與題材兼備時 70/30 動態加權融合數學精確性。
  5. 18 欄位特徵契約與數值型態不變性。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 DEC-022 總覽）**：本行「18 欄位」
> 為舊契約數字，現行為 `LEGACY_17`（17 欄）。原文保留不動。
  6. 冠軍隨機森林模型即時推論與 Top 3 決策驅動因子解析。
  7. 題材熱搜雷達卡片結構與一鍵選股切換邏輯。

---

## DEC-010：Schema Version & Additive Migration Strategy（含分層 Rollback）

- 日期：2026-08-22
- 狀態：APPROVED（Gate 0 交付物 E — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-08-23
- 觸發 Gate：UG-G1-SB4

### Context（背景）

專案完成 Gate 0-6 與 Phase 3-4 後，`daily_ml_features` 需從 7 欄擴充至 29 欄（含 2 個 Metadata/Lineage 欄），`market_articles` 需新增推噓留言欄位。目前不存在任何 Schema 遷移機制（無 ALTER TABLE、無版本追蹤）。DEC-002 曾決定不導入 Migration Framework，但明確保留在 Schema 演進時重新評估的空間。

### Problem（問題）

無遷移機制下，任何 Schema 修改都是手動且不可追蹤的。開發資料（`.devcontainer/postgres-data/`）必須受到保護，破壞性操作需嚴格禁止。

### Alternatives Considered（考慮方案）

1. **Additive DDL Script + schema_version 表 + apply_migrations.py runner**：輕量、透明、純增量、可在 Transaction 內執行。
2. **導入 Alembic**：功能完整但增加依賴與學習成本；專案目前僅需 3 個 Migration。
3. **繼續手動修改 schema.sql**：無版本追蹤、無回滾能力、不適合協作。

### Decision（決策）

採用方案 1：
- 新增 `schema_version` 表追蹤已套用的遷移版本。
- 遷移腳本存放於 `database/migrations/NNN_description.sql`。
- `apply_migrations.py` 為 runner，按版本順序執行未套用的遷移。
- 所有遷移使用 `ADD COLUMN IF NOT EXISTS`，純增量，不 DROP 任何 column 或 table。
- 累積超過 10 個 Migration 時重新評估是否遷移至 Alembic。

### Rationale（理由）

專案規模（3 個 Migration）不需要 Alembic 的複雜性。SQL Script 方案透明、可審查、可在 Transaction 內原子執行。schema_version 表提供版本追蹤，apply_migrations.py 提供冪等執行能力。

### Trade-offs（取捨）

- 無自動生成 Migration 功能（需手寫 SQL）。
- 無自動 downgrade 腳本（依靠分層 Rollback 策略）。
- 未來擴展到 10+ Migration 時可能需要升級為 Alembic。

### 分層 Rollback 策略

| 場景 | 方式 | 需 PO 批准 |
|------|------|-----------|
| 程式碼回滾 | git revert | 否 |
| 隔離驗證環境 | 銷毀臨時 DB | 否 |
| Migration 執行失敗 | Transaction 自動 ROLLBACK | 否 |
| 已成功 Migration 需修正 | Forward Fix (新增修正 Migration) | 否 |
| 需完整回復 | Pre-migration pg_dump 還原 | **是** |
| **禁止** | DROP columns 或 schema_version 表 | — |

### Affected Components（影響範圍）

`database/schema.sql`, `database/migrations/`, `database/apply_migrations.py`, `database/init_db.py`

### Verification（驗證）

- [x] 隔離 PostgreSQL 18 容器驗證 Migration 序列（2026-08-26，`sb4_migration_tmpdb`，
      port 55440，非 `postgres-data` 掛載，已拆除）——**目前僅 001_baseline.sql 一個
      遷移腳本**（002/003 屬 Gate 2/3 範圍，尚未實作），原構想的「3 個 Migration」
      驗證將隨 Gate 2/3 各自的 SB 逐步補齊
- [x] 冪等測試（二次執行顯示「無待執行遷移，已是最新版本」，無副作用）
- [x] 失敗回滾測試（故意失敗遷移確認 ROLLBACK，`schema_version` 版本未推進）
- [x] 開發資料不受影響（全程僅對隔離臨時 DB 操作，未連接真實開發 DB）

**UG-G1-SB4 實作階段發現並補上的細節（原 ADR 文字未涵蓋）**：

1. **RISK-013 根本解整合**：`apply_migrations.py` 在建立資料庫連線前，
   強制呼叫 `database/db_target_guard.py` 的 `assert_safe_migration_target()`——
   詳見 DEC-021。這是本 ADR 核准時（Gate 0，2026-08-22）尚未存在的風險項目
   （RISK-013 於 2026-08-24 才由 PO 追加），故原文未提及，屬後續 Gate 1 SB
   對本決策的必要補強，不代表原決策本身有誤。
2. **checksum 欄位的實際寫入方式**：`001_baseline.sql`（與 `DB_MIGRATION_PLAN.md`
   §4.2／§4.3 規劃的 002／003）皆在遷移腳本自身內嵌 `INSERT INTO schema_version
   ... ON CONFLICT (version) DO NOTHING`（不含 checksum）。若 runner 端也用 INSERT
   寫入 checksum，會被前述自我登記的 `ON CONFLICT` 擋下而永遠寫不進去。
   `apply_migrations.py` 改用 `UPDATE schema_version SET checksum = ... WHERE
   version = ...`，確保 checksum 不論遷移腳本是否自行登記都能正確補上。

### Remaining Risks（剩餘風險）

- 手動 SQL 可能引入錯誤 → 隔離容器驗證緩解。
- Migration 無法自動回退 → 分層策略 + pg_dump 緩解。
- 目前僅驗證 001_baseline.sql 單一遷移；002/003（Gate 2/3）尚未實作，
  多遷移序列的真實互動（例如遷移間的相依性、跨版本冪等性）尚待該等 SB 驗證。

### 證據文件

`doc/upgrade/contracts/DB_MIGRATION_PLAN.md`；`doc/upgrade/gates/SB4_GATE_A_PROPOSAL.md`；
`doc/upgrade/gates/SB4_STEP2_GATE_B_SUBMISSION.md`

---

## DEC-013：Feature Registry as Single Source of Truth（版本化特徵契約）

- 日期：2026-08-22
- 狀態：APPROVED（Gate 0 交付物 C — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-08-23
- 觸發 Gate：UG-G0-SB2

### Context（背景）

專案在 V4/V5 審查中反覆出現特徵數量矛盾（17/15/18/19），根因是缺少單一真實來源。程式碼 (`model_trainer.py`) 實際使用 17 個模型輸入（含 OHLCV），但文件各處宣稱 18 個。升級計畫需新增 4 個平穩特徵和 3 個留言特徵，使總數進一步複雜化。

### Problem（問題）

無單一 Feature Registry，導致 Master Plan、程式碼、Migration DDL、SDD 各自維護不同的特徵定義，工程師無法確定應實作哪一套 Schema。

### Alternatives Considered（考慮方案）

1. **建立版本化 Feature Registry 文件**：LEGACY_17 / CORE_16 / COMMENT_ENHANCED_19 三套契約，29 欄完整定義。
2. **在程式碼中用 Python 常數作為唯一來源**：僅程式碼層面，文件仍可能漂移。
3. **不建立 Registry，逐文件修正**：缺少錨點，每次新功能都可能再次漂移。

### Decision（決策）

採用方案 1：
- `FEATURE_REGISTRY.md` 為特徵定義的**單一真實來源**。
- 三套版本化契約：`LEGACY_17`（17 model inputs，含 OHLCV）、`CORE_16`（16 model inputs，移除 OHLC，新增 4 平穩特徵）、`COMMENT_ENHANCED_19`（19 model inputs）。
- `open_price`、`high_price`、`low_price` 留在 `stock_prices` 表，**不進入 Feature Store**，不作為跨股票 Panel Model 輸入。
- `close_price`、`volume` 為 context columns（保留在 Feature Store，不作為 model_input）。
- Feature Store (`daily_ml_features`) 固定 29 欄：2 identifier + 2 context + 2 metadata + 19 engineered + 4 target。
- Metadata 欄位 `source_status`／`label_reason` 為資料品質與標籤成因追蹤，`model_input=false`，絕不可入模。
- 每欄有 12 項必填屬性。10 條測試斷言驗證契約一致性（A1-A10）。
- 全欄位 NULL 語意規則（`FEATURE_REGISTRY.md` §5A）：區分成因 W（暖機期，允許填補）與成因 F（`SOURCE_FAILED`，必須 NULL）。

### Rationale（理由）

版本化契約避免「目前是幾個」的歧義；每個語境（程式碼基線、升級目標、留言增強）有明確名稱。12 項屬性確保每欄的定義完整可驗證。

### Trade-offs（取捨）

- 新增/修改特徵時須同步更新 Registry、程式碼與 Migration DDL（增加維護負擔）。
- 三套契約增加認知複雜度（但消除數字歧義的收益更大）。

### Affected Components（影響範圍）

`doc/upgrade/contracts/FEATURE_REGISTRY.md`, `src/ml/model_trainer.py`, `src/ml/baseline_models.py`, `src/transform/feature_aggregator.py`, `src/loaders/db_writer.py`, `database/schema.sql`

### Verification（驗證）

- [x] FEATURE_REGISTRY.md 29 欄完整且與 Master Plan §4 一致——`gate0_contract_check.py` B1「29 欄契約完整性」PASS（2026-09-14 重跑：migration 新增 22 + 既有 7 = 29）
- [x] Migration DDL 欄位與 Registry 一致——B1／B4（raw 層留言計數欄無 DEFAULT，反查法）PASS
- [ ] NOT VERIFIED → 去處：原文「10 條測試斷言可執行（A1-A10）」的 `A1`-`A10` 具名測試現已不存在於任何測試檔——判準已被 `gate0_contract_check.py` Part B（現 14 項，含本次收尾新增的 B14）取代，未逐一核對舊 A 系列與現行 B 系列的對應關係，建議下次觸碰本 ADR 時改寫本項措辭指向 Part B
- [x] `scripts/verify/gate0_contract_check.py` 全數 PASS——2026-09-14 重跑 14/14 PASS

### 證據文件

`doc/upgrade/contracts/FEATURE_REGISTRY.md`

---

## DEC-016：Multi-Source Comment Data Contract（多來源社群資料契約）

- 日期：2026-08-22
- 狀態：APPROVED（Gate 0 交付物 D — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-08-23
- 觸發 Gate：UG-G0-SB3

### Context（背景）

系統目前僅接入 PTT 作為社群來源，升級計畫需增加 Dcard（條件性）與 Threads（延後）。多來源輸入需要統一的資料契約，確保不同平台的文章可以寫入同一個 `market_articles` 表而不衝突。

### Problem（問題）

無跨平台資料契約，各來源的去重鍵、互動指標、失敗語意、時間格式各不相同。若直接實作多個 scraper 而無契約約束，會導致資料不一致與 pipeline 脆弱。

### Alternatives Considered（考慮方案）

1. **統一 Data Contract 文件**：每個來源獨立契約 + 共用輸出格式 + 明確失敗語意。
2. **每個 scraper 自行定義格式**：靈活但不一致。
3. **使用 Protobuf / JSON Schema 強制契約**：過度工程化。

### Decision（決策）

採用方案 1：
- 每個來源（PTT / Dcard / Threads）有獨立契約定義。
- 共用 `market_articles` 表作為輸出。
- Provider-prefixed `provider_article_id` 防止跨平台 ID 衝突。
- `url` UNIQUE 約束作為主要去重鍵。
- 不得用單一 `engagement_metric` 抹平平台差異。
- 失敗語意區分三態：`SUCCESS_EMPTY`（真的無資料）、`SOURCE_DEGRADED`（部分失敗）、`SOURCE_FAILED`（完全不可用 → 拋出例外，不回傳空 DataFrame）。
- Dcard 為 Conditional — PASS 則實作，FAIL 則 DEFERRED WITH EVIDENCE，不阻擋 Gate 2。
- 留言更新需獨立 UPDATE 路徑，不混入初始 `ON CONFLICT DO NOTHING` upsert。

### Rationale（理由）

統一契約確保多來源輸入可預測、可測試、可獨立部署。失敗語意區分保護 pipeline 不會把來源失敗誤判為「無資料」（遵守 AGENTS.md §7.1 不可變原則）。

### Trade-offs（取捨）

- 每新增一個來源都需要寫契約（增加文件工作量）。
- Dcard/Threads 可能永遠無法啟用（但 Conditional 設計允許此結果）。

### Affected Components（影響範圍）

`src/extractors/ptt_scraper.py`, `src/extractors/dcard_scraper.py` (新建), `src/loaders/db_writer.py`, `database/schema.sql`

### Verification（驗證）

- [x] PTT 契約與目前程式碼一致——`src/extractors/ptt_scraper.py`／`article_comments` 持續生產使用，2026-09-14（RISK-023 案）唯讀查證真實庫 1,330 篇文章、136,185 則留言，契約仍一致
- [x] Dcard 可用性驗證流程已定義並已執行——DEC-027（`APPROVED`）：「Dcard 可用性驗證判定 `FAIL`——來源標記 `DEFERRED WITH EVIDENCE`」
- [x] 失敗語意區分 SUCCESS_EMPTY / SOURCE_DEGRADED / SOURCE_FAILED——三態皆有實作與測試：`tests/test_source_failed_nulls.py`（SOURCE_FAILED／SUCCESS_EMPTY）、`src/extractors/ptt_scraper.py`／`tests/test_ptt_failure_is_recorded.py`（SOURCE_DEGRADED）

### 證據文件

`doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md`

---

## DEC-011：Purged Walk-Forward with Purge / Gap / Embargo（交易日計）

- 日期：2026-08-23
- 狀態：APPROVED（Gate 0 交付物 F — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-08-23
- 觸發 Gate：UG-G1-SB1

### Context（背景）

深度稽核確認 `time_series_split.py` 以特徵日期切分，不考慮標籤的資訊邊界；
`feature_aggregator.py:459` 的 `shift(-1)` 使 T 日標籤依賴 T+1 收盤價。
兩者結合造成訓練集尾端的標籤依賴測試集起始日的價格 —— 邊界前視偏誤（`VERIFIED`）。

### Problem（問題）

現行切分只斷言 `max(train_date) < min(test_date)`，未涵蓋 `label_end_date`。
V5 曾將 Embargo 定義為「從 Test 開頭移除 embargo 行」，這會刪除真正需要評估的測試資料，
且不解決標籤重疊；並使用意義不明的 `embargo_pct`（百分比的分母未定義）。

### Alternatives Considered（考慮方案）

1. **Purge + 可選 Gap + Embargo 三者分離，全部以交易日計**。
2. 僅加大 train/test 間隔：粗糙，且無法對應不同 label horizon。
3. 沿用 V5 的 Embargo 定義：會刪測試資料，不可接受。

### Decision（決策）

採用方案 1：
- **Purge**：移除訓練集中 `label_end_date >= test_start_date` 的列（防標籤與測試特徵時間重疊）。
- **Gap**（可選）：Train 結束與 Test 開始之間保留若干交易日，兩集合皆不使用；嚴格 Walk-Forward 預設 0。
- **Embargo**：僅在交叉驗證中「測試後資料會進入其他 Fold 訓練」時，排除 `test_end_date` 之後 `embargo_days` 個交易日的訓練候選；嚴格單向 Walk-Forward 可設 0。
- 所有時序參數一律使用**交易日數**，禁止 `embargo_pct` 等百分比。
- 核心斷言：`max(train.label_end_date) < min(test.trade_date)`。
- 新增 `label_end_date = trade_date + label_horizon 交易日`。

### Rationale（理由）

三者職責分離後語意清楚：Purge 解決標籤重疊、Gap 提供額外緩衝、Embargo 處理跨 Fold 汙染。
以交易日計可直接對應 label horizon（T+1 → 1 天；Triple-Barrier H=5 → 5 天），無歧義。

### Trade-offs（取捨）

- Purge 會減少訓練樣本（H=5 時每個 Fold 少 5 天）。
- 修正洩漏後模型準確率可能下降（RISK-001），但那是真實績效。

### Affected Components（影響範圍）

`src/ml/time_series_split.py`, `src/transform/feature_aggregator.py`, `tests/test_time_series_split.py`

### Verification（驗證）

> **實測結果補充（2026-08-25，UG-G1-SB1 步驟 3～5）**。`src/` 變更尚未 commit；
> 完整證據見 `doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`。

- [x] T-PW-01~05 五項測試（含 mutation test）—— 另加 PO 2026-08-25 回報之停牌重現測試（第 6 項），共 6 項，`tests/test_time_series_split.py` `PurgedWalkForwardTests`，全數 PASS
- [x] 所有 Fold 的核心斷言成立 —— `WalkForwardSplitter.assert_no_boundary_leakage()`，AFTER 快照全套 163 tests / OK

**實作與原始設計的差異（PO 獨立驗證發現並要求修正）**：原始實作以全域唯一交易日索引
反推 `label_end_date`，未讀取 `feature_aggregator.generate_target_labels()` 產出的逐列
`label_end_date` 欄位，個股停牌等日曆不對齊情形會低估應被 Purge 的列（已以停牌重現測試證實）。
已修正為 `split()` 優先採用 df 中逐列真實值，欄位缺席時才退回全域曆近似法（並於 docstring
揭露此路徑的精度限制）。

### Remaining Risks（剩餘風險）

- Purge 後訓練集可能不足 `min_train_size` → 該 Fold 跳過並記錄警告。**（已實作：`min_train_size`
  未顯式指定時預設為 `train_window_size - label_horizon`，跳過時 `logger.warning`。）**
- 無 `label_end_date` 欄位時的 fallback 近似法，假設面板內所有列共享同一份全域交易日曆；
  個股停牌等造成日曆不對齊時可能低估應 Purge 的列（見上方「實作與原始設計的差異」）。
  **建議一律透過 `FeatureAggregator.generate_target_labels()` 提供該欄位以取得精確結果**；
  是否所有生產路徑（含 evaluator/trainer 呼叫 `WalkForwardSplitter.split()` 的實際入口）都已
  正確傳入該欄位，尚待接 Gate 3 或 trainer 管線整合時逐一確認，PO 已同意此項延後處理。

### 證據文件

`doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §2, §3；
`doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`

---

## DEC-017：Stock Universe Definition & Point-in-Time Liquidity Ranking

- 日期：2026-08-23
- 狀態：APPROVED（Gate 0 交付物 B/G — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-08-23
- 觸發 Gate：UG-G2-SB6

### Context（背景）

PO 決定產品範圍為台股流動性前 500 大普通股，分階段上線（Phase 1 前 150 大 → Phase 2 前 500 大），
以過去 60 交易日「每日成交金額中位數」排序，每月第一個交易日重建。

### Problem（問題）

若 Universe 以「今日的前 150 大」倒推歷史回測，會系統性納入當時尚未上市、
或當時流動性不足、或後來已下市的標的，產生 Survivorship Bias（倖存者偏誤），
使回測績效虛高且不可重現。

### Alternatives Considered（考慮方案）

1. **Point-in-Time Snapshot**：每月重建時保存當期 Universe 與排名依據，回測載入當期快照。
2. 固定 Universe（一次選定不變）：簡單但無法反映市場結構變化，且仍有選樣偏誤。
3. 每日重建：計算成本高，且 Universe 頻繁變動不利於策略穩定性。

### Decision（決策）

採用方案 1：
- 每月 Universe 只能使用**生效日前已知**的 60 交易日成交資料。
- 保存 `universe_effective_date`、排名依據（60 日成交金額中位數）、納入／排除清單。
- 歷史回測必須載入**當期 Snapshot**，不得以今日 Universe 倒推。
- 明確處理：新上市（需累積足夠交易日）、下市（下市日起移出）、停牌（期間排除）、代碼異動（追蹤延續性）。
- 排除 ETF、ETN、權證、興櫃、停止交易、歷史資料不足者。

### Rationale（理由）

Point-in-Time 是量化回測的基本要求。沒有它，所有績效數字都不可信，
Gate 3 的 Benchmark 也失去意義。月度重建在計算成本與結構反映之間取得平衡。

### Trade-offs（取捨）

- 需額外儲存每月 Snapshot（空間成本低，但需設計 schema）。
- 回測程式必須按日期載入對應 Universe，複雜度略增。

### Affected Components（影響範圍）

`src/transform/universe_builder.py`（新建）、Universe 相關資料表、`src/ml/panel_dataset.py`

### Verification（驗證）

- [x] `test_p1_universe_point_in_time_no_future_data`（現行檔名帶 `p1` 前綴，原文未帶——`tests/test_universe_builder.py`，2026-09-14 重跑 PASS）
- [x] `test_universe_snapshot_saved`（`tests/test_universe_builder.py`，2026-09-14 重跑 PASS）
- [x] `test_p4_universe_handles_delisting`（現行檔名帶 `p4` 前綴，原文未帶——`tests/test_universe_builder.py`，2026-09-14 重跑 PASS）

### Remaining Risks（剩餘風險）

- RISK-012：若 PIT 未落實，存活偏誤將使所有 Benchmark 數字失效（High）。

### 證據文件

`SYSTEM_UPGRADE_MASTER_PLAN.md` §3.1；UG-G2-SB6 Brief

---

## DEC-018：Triple-Barrier 三分類標籤、`Open[T+1]` Anchor 與 Ambiguous = NULL

- 日期：2026-08-23
- 狀態：APPROVED（Gate 0 交付物 F — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-08-23
- 觸發 Gate：UG-G3-SB1

> **本 ADR 承接 Gate 0 Closure Review 中最重大的設計決策**，
> 依 PO 指示於 Gate 0 階段即以 `Proposed` 寫入 ADR 帳本，不延後至 Gate 3。

### Context（背景）

現行 `target_up_down` 為固定 T+1 二元標籤，對微幅震盪（±0.1%）同樣產生標籤，
無法區分「具備動能的有效突破」與「白雜訊」。
研究文獻（López de Prado 2018）建議採 Triple-Barrier 動態標籤。

### Problem（問題）

V7 的初版規格存在兩個結構性錯誤：

1. **標籤與交易不是同一筆**：Barrier 以 `Close[T]` 計算，但回測以 `Open[T+1]` 成交。
   收盤後無法以當日收盤價成交，模型學到的訊號與實際可執行的交易不對應。
2. **止損與未觸線被合併**：Timeout 與 Stop-Loss 皆標記為 `0`，
   但前者是持有到期以市價結算、後者是實際虧損出場，報酬分布與風險特性完全不同。

### Alternatives Considered（考慮方案）

1. **統一以 `Open[T+1]` 為 anchor + 三分類標籤**（PO 決策）。
2. 維持 `Close[T]` anchor，回測也改以 `Close[T]` 成交：不可執行（收盤後無法成交）。
3. 維持二元標籤，另加 `label_reason` 區分：資訊仍損失於模型輸入層。

### Decision（決策）

採用方案 1（PO 於 Gate 0 Closure Review 決定）：

**統一時間約定**：
- T 日收盤後產生預測。
- **`Open[T+1]` 同時作為進場成交價與 Barrier anchor**。
- 觸線評估區間為 T+1 至 T+5 的 `High` / `Low`（含 T+1 當日）。
- Slippage 與交易成本皆套用於 `Open[T+1]`。

**三分類標籤**：

| Label | 條件 |
|-------|------|
| `1` | 先觸上障礙（止盈） |
| `-1` | 先觸下障礙（止損） |
| `0` | H=5 期間未觸線（Timeout） |
| `NULL` | 同日觸雙線 / 資料不足 / `Open[T+1]` 不存在 |

**NULL 成因追蹤**：新增 `label_reason` 欄位記錄
`ambiguous_dual_barrier` / `insufficient_data` / `no_entry`。

**同日觸雙線**：標記 `NULL` 排除訓練；禁止 forward-fill、補 0、指定方向或任意 tie-breaker；
評估報告必須揭露 Ambiguous 比例；若 > 10% 開啟新決策。

### Rationale（理由）

- 統一 anchor 使「模型學到的」與「實際可執行的」是同一筆交易，消除標籤與回測的結構性錯配。
- 三分類保留止損與 Timeout 的差異；模型訓練時可依需求映射為二元，但**儲存層必須保留原始三分類資訊**。
- `label_reason` 使三種 NULL 成因可分離，Ambiguous Ratio 報告與 RISK-011 觸發條件才算得出來。

### Trade-offs（取捨）

- 三分類使類別不平衡問題更明顯（Timeout 可能佔多數）→ 評估報告須揭露類別分布。
- `Open[T+1]` anchor 使標籤依賴 T+1 資料，`label_end_date` 需正確設為 T+H。
- 需新增 `label_reason` 欄位（29 欄契約的一部分）。

### Affected Components（影響範圍）

`src/ml/triple_barrier.py`（新建）、`src/transform/feature_aggregator.py`、
`database/migrations/002_expand_ml_features.sql`、`src/ml/time_series_split.py`（label_horizon 對齊）

### Verification（驗證）

- [x] T-TB-01~17（`PURGED_WALK_FORWARD_SPEC.md` §5.2；T-TB-07 Dynamic barrier 為
      `UG-G3-SB1` Out of Scope，其餘 16 項 PASS，含 `test_tb_anchor_is_next_open`、
      `test_tb_stop_loss_distinct_from_timeout`）——`tests/test_triple_barrier.py`，
      commit `b24fc01`（紅）→`d2e3f27`（綠）→`874b3bf`（NaN 修復追加）
- [x] DB CHECK constraint `chk_target_triple_barrier_domain` 限制值域為 `{-1, 0, 1}` 或 NULL
      ——真實庫寫入 known-FAIL 驗證確認會拒絕越界值，見
      `doc/upgrade/gates/evidence/UG_G3_SB1_disposable_write_validation.json`
- [x] DB CHECK constraint `chk_label_reason_consistency` 強制不變式——同上證據檔，
      另於真實庫寫入 `doc/upgrade/gates/evidence/UG_G3_SB1_real_db_write.json`
      （2026-09-09，`postgres`@`localhost:5432` 3,713 列）實際落地生效

### Remaining Risks（剩餘風險）

- RISK-011：Ambiguous 比例過高（> 10%）需開新決策（Medium）。
- 三分類的類別極度不平衡可能影響模型收斂（任一類 < 5% 時標記並揭露）。
  **【2026-09-09 本條款已觸發】**：真實庫實測 Timeout（Label 0）佔已標籤列比例
  三檔 <5%（2382 2.6%、6488 2.9%、NVDA 0.9%；僅 2330 7.6% 未觸發），見 RISK-025。

### 證據文件

`doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §4；`SYSTEM_UPGRADE_MASTER_PLAN.md` §3.3

---

## DEC-012：UI Four-State Data Mode（REAL/DEMO/EMPTY/ERROR）

- 日期：2026-08-25
- 狀態：`APPROVED`（PO 於 Gate B 送審文件複查後核准，2026-08-25）
- 觸發 Gate：UG-G1-SB2

### Context（背景）

`src/ui/data_loader.py` 的四個公開函式（`load_stock_features`、`load_stock_articles`、
`load_ai_discovered_keywords`、`load_thematic_radar_data`）原本只回傳單一值，DB 連線失敗、
DB 成功但無資料、與刻意使用模擬資料三種情況被壓縮成同一種回傳值外觀，呼叫端與使用者無法區分
（DRIFT-009）。

### Problem（問題）

`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 的 Failure Semantics 原文把 ERROR／EMPTY／DEMO
列為三個獨立觸發來源，但未回答一個實際會發生的情境：DB 連線失敗時，UI 究竟該顯示空白
（嚴格對應 ERROR），還是顯示標示清楚的模擬資料（實質上退回 DEMO）？現行程式碼的行為是
後者但未標示；這正是 `SB2_GATE_A_PROPOSAL.md` §3.2 提出三個方案請 PO 裁決的原因。

### Alternatives Considered（考慮方案）

`SB2_GATE_A_PROPOSAL.md` §3.2：

- **方案 A**：ERROR 自動退回 DEMO，但顯著標示（PM 原建議，理由是保留「離線也能展示」的作品集體驗）。
- **方案 B**：ERROR 顯示空白／錯誤訊息，完全不顯示模擬數字，DEMO 僅供顯式啟用。
- **方案 C**：由使用者以 Sidebar 開關手動切換 ERROR 時的行為。

### Decision（決策）

**採方案 B**（PO 2026-08-25 決策）。原話：「這不是商業產品，是我的求職作品集，我要展示的是真實的
技術能力，不需要用假資料撐場面——就算某個區塊因為 DB 沒開而顯示錯誤，只要講得出原因，比顯示一堆
看起來正常但其實是虛構的數字更有價值。」

```python
class DataMode(Enum):
    REAL = "real"    # DB 連線成功且回傳非空資料
    DEMO = "demo"     # 展示用模擬資料，僅在呼叫端明確傳入 demo=True 時使用
    EMPTY = "empty"   # DB 連線成功，查詢結果為零筆——真實的「沒有」，非模擬
    ERROR = "error"   # DB 連線或查詢本身失敗，對應區塊不渲染任何數值
```

- ERROR：對應區塊顯示「⚠️ 資料來源目前無法連線」，**不渲染任何 KPI 卡片／圖表數值／預測結果**。
- DEMO：**不再是 ERROR 的自動 fallback**。四個公開函式新增 `demo: bool = False` 參數，
  作為 DEMO 模式的唯一合法入口；`app.py` 目前不傳入 `demo=True`（無 UI 開關，PO 明確表示
  「不用做到 UI 開關」，僅需函式參數層級的入口）。
- EMPTY 與 ERROR 需在資料層明確區分：`_fetch_real_stock_features_from_db`／
  `_fetch_real_stock_articles_from_db` 內部例外改為拋出 `DataSourceError`（→ ERROR），
  成功但零筆資料則回傳實際空結果（→ EMPTY），不再讓兩者共用同一個 `None` 回傳值。
- `charts.py` 三個圖表函式與 `components.py` 四個渲染元件皆新增 `mode` 參數：ERROR／EMPTY
  回傳／渲染不含任何數值的佔位內容；DEMO 正常渲染但疊加醒目浮水印／橫幅。

### Rationale（理由）

方案 B 直接對應 PO 的產品定位判斷：本專案的價值來自展示真實技術能力，虛構數字換取畫面完整性
在求職作品集情境下是負資產而非資產。比方案 A 更嚴格但語意更乾淨——ERROR 與 DEMO 的畫面呈現
不再重疊，`DataMode` 列舉值與使用者實際看到的內容一一對應。

### Trade-offs（取捨）

- 使用者在 DB 未啟動或未跑過 ETL 時開啟 UI，會看到較多空白／錯誤區塊，犧牲「離線也能展示」的
  即時可用性——PO 已權衡並接受此取捨。
- 需要在 `data_loader.py` 內部拆分 EMPTY／ERROR 兩種路徑（新增 `DataSourceError`），
  屬本 SB 新增的內部契約，不影響既有 Schema。
- `demo=True` 目前只有函式參數層級入口，沒有 UI 開關；日後若要在 UI 上實際展示 DEMO 模式，
  需要另一個決策與實作（不在本 SB 範圍）。

### Affected Components（影響範圍）

`src/ui/data_loader.py`（`DataMode`、`DataSourceError`、四個公開函式簽章）、
`src/ui/components.py`（`render_data_mode_banner` 與四個元件的 `mode` 參數）、
`src/ui/charts.py`（`_placeholder_figure`／`_apply_demo_watermark` 與三個圖表函式的 `mode` 參數）、
`app.py`（解包四個函式的 `(value, DataMode)` 元組、依 mode 分流 KPI／預測邏輯、Sidebar 全域來源追蹤）

### Verification（驗證）

- [x] 173/173 tests PASS（container，164 基線 + 9 個新增，含 REAL/ERROR/EMPTY/DEMO 各模式的正向測試）
- [x] HERM-01~09 全數改為 mock，不再依賴環境憑證與 DB 內容
- [x] GOV-02 sentinel：HERM 對應測試的 runtime `connect()` 攔截數由 9 降為 0（PO 與 PM 各自重跑確認）
- [x] `tests/schema_smoke_ui_data_loader.py`：4 個代表查詢對臨時 DB 執行，欄位契約相容性確認
- [ ] NOT VERIFIED → 去處：Streamlit 真實執行環境的視覺呈現尚未肉眼確認（僅驗證結構，見 `SB2_STEP3_IMPLEMENTATION_REPORT.md` §6）；需人工啟動 `streamlit run app.py` 並實際瀏覽四種 `DataMode` 的畫面呈現，非自動化可完成，待下次有 UI 走查需求時一併執行

### Remaining Risks（剩餘風險）

- `demo=True` 尚無 UI 觸發入口，若日後需要在畫面上實際展示 DEMO 模式，需另行設計進入點。
- ERROR 狀態的空白呈現尚未經真實使用者（含作品集審閱者）體驗驗證，僅有結構性測試支持。

### 證據文件

`doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md` §3；
`doc/upgrade/gates/SB2_STEP3_IMPLEMENTATION_REPORT.md`


## DEC-020：模型競技排行榜動態化（Artifact-Driven Tournament Leaderboard）

- 日期：2026-08-26
- 狀態：`APPROVED`（PO 於 Gate B 送審文件複查後核准，2026-08-26）
- 觸發 Gate：UG-G1-SB3
- 編號說明：`SYSTEM_UPGRADE_MASTER_PLAN.md` §15.1 原僅預留 DEC-010～DEC-019 對應各 SB，
  UG-G1-SB3 當時未分配編號；本決策取用下一個未使用編號 DEC-020，DEC-019
  仍保留給 UG-G2-SB7（Batch ETL Architecture），未互相衝突。

### Context（背景）

`src/ui/components.py:166-184`（`render_tournament_leaderboard`）8 組模型競技數據為字面常數，
不接受任何參數，是唯一未受 DEC-012 DataMode 約束的資料展示區塊（DRIFT-008）。
DRIFT-018（CRITICAL）進一步指出這 8 個常數存在三個互相獨立的矛盾：排名與自身數字牴觸、
同一實作被記錄為兩個不同分數、無任何實驗產出物連結。DRIFT-018 原歸屬 UG-G1-SB2，
但 SB2（已於 2026-08-25 CLOSED）僅完成「標註為未經驗證展示值」的標籤化處理，
三個矛盾本身未修正。

`SB3_GATE_A_PROPOSAL.md` 提案時另外發現：`src/ml/evaluator.py` 的
`MLEvaluator.evaluate_tournament()` 已是可執行的真實 8 組實驗評估器（4 演算法 × 2 特徵集，
跑在 SB1 修正的 Purged Walk-Forward 上），且其所需的 `target_up_down`／`target_return_1d`
標籤已由 `feature_aggregator.append_target_labels()`（T+1 簡單標籤）產出，不依賴 Gate 3
規劃中的 Triple-Barrier 標籤。這打破了 `SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 UG-G1-SB3
Brief 原本「模型競技本身列為 Out of Scope、Gate 3 完成前排行榜必為空」的前提。

### Alternatives Considered（考慮方案）

`SB3_GATE_A_PROPOSAL.md` §3.1：

- **方案 A**：維持 Master Plan 原範圍，僅新增讀取機制；無 artifact 時顯示 EMPTY。
  DRIFT-018 三個矛盾僅解決 (3)（無 artifact 連結），(1)(2) 因排行榜不顯示而被繞過，非解決。
- **方案 B**：一併執行評估器，產出真實 artifact，實際解決三個矛盾。
  代價：需對真實開發 DB 執行只讀查詢取得完整歷史資料（非 SB1/SB2 慣用之隔離臨時 DB）。

### Decision（決策）

**採方案 B**（PO 2026-08-25 核准），另同時核准四項裁決：

1. DRIFT-018 歸屬列由 UG-G1-SB2 改記為 UG-G1-SB3（已落實於 `DOCUMENT_DRIFT_REMEDIATION.md`）。
2. Artifact 欄位採用 `evaluate_tournament()` 現有完整輸出（`leaderboard`／`alpha_attribution`／
   `champion_model_name`／`champion_score`），不採 Master Plan 原提案較窄的欄位集合。
3. Artifact JSON（`models/artifacts/tournament_results.json`）產生後**直接 commit 進版控**
   （作品集展示用途，非 `.gitignore` 排除的 build 產物）。
4. 對真實開發 DB 執行只讀查詢取得完整歷史資料本身獲得核准，執行前依 RISK-013 協定呈報
   綁定確認，且比照 SB1/SB2 隔離臨時 DB 慣例升一級——`scripts/generate_tournament_artifact.py`
   完整程式碼須先交審查員複閱，確認全程唯讀後才可執行。

**實際執行結果（2026-08-26）**：程式碼複閱與 RISK-013 綁定確認流程已完成，
但複閱過程中審查員以合成資料（不連 DB）重現一個既有 bug（見 §7 known-FAIL 表）；
修正後審查員進一步指出資料量防線設計缺陷並要求補強（同上）。**修正完成後，
PO 決定本次不真正執行該腳本**——目前可用歷史資料量不足以支撐
`WalkForwardSplitter` 預設 window（`train_window_size=60 + test_window_size=20`），
真正執行會被腳本新增的 `check_sufficient_data()` 防線正確擋下。SB3 這次僅交付
「讀取機制＋防線」，實際產出真實 artifact 留待未來資料量足夠時再執行。

### Rationale（理由）

方案 B 直接解決 DRIFT-018 的核心問題——虛構或無依據的展示數字，與 DEC-012 建立的
「不以假資料撐場面」原則一致。既然評估引擎已存在且可獨立於 Gate 3 其餘未完成部分執行，
維持方案 A 只是把「假數字」換成「什麼都沒有」，對 CRITICAL 等級的漂移而言不是實質修正。

### Trade-offs（取捨）

- 真實 artifact 尚未產出前，排行榜區塊會持續顯示 EMPTY「尚未完成模型競技」，
  犧牲畫面完整性——PO 已權衡並接受（見 Context 段落之「實際執行結果」）。
- Artifact 產生腳本觸碰真實開發 DB（唯讀），承擔比 SB1/SB2 隔離臨時 DB 更高的操作風險，
  以加倍的複閱／確認流程（程式碼複閱 + RISK-013 綁定確認）換取。
- Artifact commit 進版控後，`models/artifacts/tournament_results.json` 的正確性
  取決於執行當下的資料品質與樣本量，非可持續自動更新——若未來需要排程重跑，
  屬另一個 SB 的範圍（`SB3_GATE_A_PROPOSAL.md` §6 已明確排除）。

### Affected Components（影響範圍）

`src/ui/data_loader.py`（`load_tournament_results`、`_stringify_date_columns`）、
`src/ui/components.py`（`render_tournament_leaderboard(data, mode)`）、`app.py`
（呼叫處解包與 Sidebar 追蹤）、`scripts/generate_tournament_artifact.py`（新檔，未執行）、
`doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-018 歸屬修正）

### Verification（驗證）

- [x] 189/189 tests PASS（container，含 9 個新增於讀取/渲染契約、3 個 `label_end_date`
      型別 bug 回歸測試、4 個資料量防線測試）
- [x] `label_end_date`／`trade_date` 型別不一致的既有 bug（SB1 起即存在，SB3 首次踩到）
      已修正並有 known-FAIL 回歸測試
- [x] 資料量防線（`check_sufficient_data`）已加入並有 known-FAIL 回歸測試；
      經實測證實「leaderboard 是否為空」判斷不了零 Fold 但滿版零分排行榜的情境
- [ ] NOT VERIFIED → 去處：真實 artifact 尚未產出（`models/` 目錄不存在），屬有意延後而非遺漏——待未來資料量足夠支撐 `WalkForwardSplitter` 預設 window 時，執行 `scripts/generate_tournament_artifact.py`（唯讀，已通過審查員複閱）

### Remaining Risks（剩餘風險）

- 真實 artifact 產出後，DRIFT-018 矛盾 (2)（lightgbm/xgboost 同分）是否真的消失，
  仍待實測確認，本次僅為理論推斷（container 內兩者為不同真實實作）。
- `scripts/generate_tournament_artifact.py` 從未在真實 DB 上執行過，其 Panel 大小／
  唯一交易日數等實際數字未知，執行時是否仍會被 `check_sufficient_data` 擋下待實測。

### 證據文件

`doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md`；`doc/upgrade/gates/SB3_GATE_B_SUBMISSION.md`


## DEC-021：RISK-013 根本解——`database/db_target_guard.py`

- 日期：2026-08-26
- 狀態：`APPROVED`（PO 於 SB4 階段一 Gate B 送審文件複查後核准，2026-08-26，commit `d2a4d48`）
- 觸發 Gate：UG-G1-SB4（階段一，DEC-010 的必要前置條件）

### Context（背景）

RISK-013（`REMAINING_RISKS.md`，PO 2026-08-24 簽核）指出：驗證／測試腳本可在未覆寫
`DB_HOST`／`DB_PORT` 時直連真實開發資料庫。既有緩解（呈報綁定確認的回報紀律）
是流程紀律，不是技術護欄——依賴執行者記得覆寫環境變數、記得先呈報。SB1～SB3
全部是唯讀路徑，此風險可承受；SB4 是本專案第一個寫入路徑（DDL migration）的 SB，
同一種疏失的後果從「讀了不該讀的」質變為「對真實開發資料庫執行 DDL」，且無法
事後補救。PO 明確要求：根本解必須在 SB4 動任何 migration 邏輯之前落地，並作為
獨立於 DEC-010（migration 框架本體）的優先步驟。

### Problem（問題）

需要一個不依賴「記得做」的技術機制，在偵測到連線目標疑似真實開發 DB 時，
於建立連線前自動拒絕執行。

### Alternatives Considered（考慮方案）

`SB4_GATE_A_PROPOSAL.md` §3.2：

- **訊號 A**：host/port 是否為 `.env.example` 未覆寫的預設值（`localhost:5432`）。
- **訊號 B**：database 名稱是否符合本專案臨時 DB 的命名慣例（含 `tmp`／`temp`／`test`）。
- **曾考慮但未採用之第三訊號**：偵測 `postgres-data` 是否被 bind mount。
  技術上不可靠而放棄——`apply_migrations.py` 執行於 app 容器內，與 db 為獨立容器
  命名空間，在不取得 docker socket 存取權（本身是更大的風險）的前提下，
  無法從應用程式容器內部可靠查詢另一個容器的 volume 掛載型態。PO 核准前
  親自查核 SB1～SB3 已結案文件裡實際使用過的臨時 DB 埠號（55433～55436）與
  命名（皆含 `tmp`），確認訊號 A／B 與既有慣例完全吻合，同意不需第三訊號。

### Decision（決策）

新增 `database/db_target_guard.py`，核心函式 `assert_safe_migration_target(db_config)`：
訊號 A 或訊號 B **任一**觸發，即判定「疑似真實 DB」，除非呼叫端已透過環境變數
`CONFIRM_REAL_DB_MIGRATION_TARGET` 提供完整確認句（`I_UNDERSTAND_THIS_WRITES_TO_
THE_REAL_DEV_DB`，刻意要求完整句子而非 `1`／`true` 等簡單真值），否則
`raise SystemExit`，不執行任何連線動作。本機制**不取代**既有的「呈報綁定確認」
流程紀律，兩者疊加：流程紀律要求執行前先給 PO 看；技術護欄保證就算流程紀律
這次失守，程式本身仍會在觸及疑似真實 DB 時自動停下。

`database/apply_migrations.py`（DEC-010 的實作）在建立資料庫連線前，
**強制**呼叫本函式——這是階段一與階段二產出物的唯一耦合點。

### Rationale（理由）

正向表列（要求臨時 DB 使用可辨識命名）優於嘗試「證明這是真實 DB」（後者需要
硬編碼真實 DB 名稱等機敏設定，不應出現在程式碼中）。兩個訊號分別覆蓋兩種
獨立的疏失來源：忘記覆寫連線座標、忘記為臨時 DB 命名，任一遺漏都會被攔下。

### Trade-offs（取捨）

- 機制依賴呼叫端「記得呼叫」`assert_safe_migration_target()`，與 RISK-013
  原本的問題是同一種「依賴記得做」，只是往上移了一層——**PO 已記錄此觀察，
  本次不要求改設計**；若未來 Gate 2／3 出現新的 DB 寫入路徑，屆時將評估是否
  讓 `DBWriter` 的寫入方法自動呼叫本函式。
- 訊號 A／B 皆為啟發式判斷，非密碼學等級的身分驗證；刻意選擇與本專案既有
  慣例強耦合的簡單規則，而非通用的資料庫身分識別系統。

### Affected Components（影響範圍）

`database/db_target_guard.py`（新檔）、`database/apply_migrations.py`
（唯一呼叫端）、`tests/test_db_target_guard.py`

### Verification（驗證）

- [x] 5 個可執行案例（3 known-FAIL + 2 正向）皆已執行並取得原始輸出
      （`SB4_STEP1_GATE_B_SUBMISSION.md` §7）
- [x] 第 6 個對照案例（舊防線失效示範）已於階段二補上：構造移除本函式呼叫的
      臨時版本，對隔離臨時 DB（`sb4_migration_tmpdb`，非真實 DB）執行，
      證實無保護時腳本會直接連線成功，無任何攔截點
      （`SB4_STEP2_GATE_B_SUBMISSION.md` §7）
- [x] `apply_migrations.py` 以真實 DB 座標（未覆寫環境變數）執行，於連線前
      即被拒絕，未建立任何連線（`SB4_STEP2_GATE_B_SUBMISSION.md` E2E 驗證項 4）

### Remaining Risks（剩餘風險）

- 見 Trade-offs：機制本身仍依賴呼叫端記得呼叫，非強制耦合於 `DBWriter` 寫入路徑本身。

### 證據文件

`doc/upgrade/gates/SB4_GATE_A_PROPOSAL.md` §3；`doc/upgrade/gates/SB4_STEP1_GATE_B_SUBMISSION.md`；
`doc/upgrade/gates/SB4_STEP2_GATE_B_SUBMISSION.md`

---

## DEC-022：歷史 ADR 記錄缺陷登錄（Legacy ADR Defect Index）

- 狀態：APPROVED（Project Owner，2026-08-26，UG-G1-SB5；狀態行格式於 2026-09-08 正規化，原格式見 `doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_B13_fix_evidence.json`）
- **Date**：2026-08-26
- **Authors**：PM / Orchestrator Agent
- **Approved by**：Project Owner (Human)

### Context / Problem（背景／問題）

`doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`（Gate 0 交付物）登錄了多項既有 ADR（DEC-003、
DEC-004、DEC-006、DEC-007、DEC-008、DEC-009）內文本身即帶有缺陷或已過期的問題（截斷、重複、
特徵數裸寫、禁用詞、證據邊界未標註）。這些 ADR 已於本 session 稍早（2026-08-19～08-20）由
Project Owner 核准，其原始文字依 `CLAUDE.md` §16.1（`doc/evidence/` 為只增不減之證據記錄）
不應回頭改寫；但讀者需要一個明確、可追溯的入口知道「這些條目有已知問題，正確資訊在哪裡」。

### Decision（決策）

**採方案 C（PO 核准，2026-08-26）**：

1. `doc/spec/`（PRD／SDD）等現行文件（非 `doc/evidence/`）直接修正裸寫數字與過期標記，
   不受本決策約束（本來就會持續更新）。
2. `doc/evidence/DECISIONS.md` 既有 ADR 原文**一字不改**；改為在每一處問題原文旁邊，
   以 `📌 **SB5 補充註記**` 區塊直接插入緊鄰的補充說明，指向現行權威來源。
3. 本 DEC-022 作為**總覽索引**，彙整所有補充註記的位置，供讀者快速定位；
   個別補充註記本身才是逐點的權威更正內容。

### 缺陷索引（逐條列出補充註記位置）

| ADR | 缺陷類型 | 對應漂移 ID | 原文行號（本次插入註記前） | 補充註記位置 |
|-----|---------|------------|--------------------------|-------------|
| DEC-003 | NLP Completion Contract 段落於句中截斷，缺 Decision／Rationale／Affected Components／Verification | DRIFT-005 | L199-200 | 緊接截斷句之後 |
| DEC-004 | 全 ADR 內容於 L315-432 被同一決策較舊的草稿快照重複一次 | DRIFT-006 | L313（定案版本結尾）/ L315（草稿版本開頭） | 緊接定案版本結尾、草稿版本開頭之前 |
| DEC-006 | 「18 欄位／18 項」特徵數裸寫（現行 `LEGACY_17`＝17 欄） | DRIFT-001／007 | L551、L577 | 各行原文之後 |
| DEC-007 | 「18 特徵／18 欄位」特徵數裸寫；8 組平行實驗方法論未標註 host 環境限制 | DRIFT-001／007／015 | L607、L617、L640（Verification 段末） | 各行原文之後 |
| DEC-008 | 「18 欄位」特徵數裸寫（3 處）；Fallback 資料產生器敘述已被 DEC-012 方案 B 取代 | DRIFT-001／007 | L654、L677、L701 | 各行原文之後 |
| DEC-009 | 「18 欄位」特徵數裸寫（3 處）；「100% 保持不變」「零誤差無縫推論」為 `CLAUDE.md` §9.2 禁用詞、無對應驗證證據 | DRIFT-001／007 | L724、L729、L763 | 各行原文之後 |

**權威特徵契約來源**：`doc/upgrade/contracts/FEATURE_REGISTRY.md`（`LEGACY_17` 現行 17 欄／
`CORE_16` 計劃中／`COMMENT_ENHANCED_19` 計劃中）。以上索引中所有「18 欄位／18 特徵／18 項」
裸寫，一律以此契約表為權威更正依據，不再逐條重述。

### Rationale（理由）

- 保守路線（原文不動 + 旁註）避免對已核准 ADR 的既有 `git blame`／審閱歷史造成擾動，
  且符合 §16.1「只增不減」的明文規則。
- 集中索引（本 DEC）讓讀者不必先逐一翻閱六份 ADR 才能知道問題全貌；逐點旁註
  （見各 ADR 內文）讓讀者在讀到問題原文的當下即可看到更正，不必來回跳轉。
- 兩者互補：本 DEC 回答「有哪些問題、在哪裡」；旁註回答「這一行具體錯在哪、正確值是什麼」。

### Affected Components（影響範圍）

- `doc/evidence/DECISIONS.md`（DEC-003／004／006／007／008／009 各自新增旁註區塊；本 DEC-022 新增）
- `doc/evidence/CHALLENGES.md`（L211 同類裸寫，另見該檔案內對應旁註）
- `doc/spec/PRD_Financial_Sentiment_System_v1.md`、`doc/spec/SDD_Financial_Sentiment_System_v1.md`（直接修正，不受本決策約束）
- `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-001／005／006／007／015 狀態更新）

### Verification / Evidence（驗證／證據）

`VERIFIED THIS SESSION`：

```bash
grep -rnE "18[[:space:]]*(欄|項|特徵|features?)" doc/evidence/ doc/spec/
```

修正前命中 15 處（PRD 2、SDD 2、`DECISIONS.md` 10、`CHALLENGES.md` 1）；修正後 `doc/spec/`
應為 0，`doc/evidence/` 應僅剩本次新增之旁註區塊本身引用 `LEGACY_17`／`17` 而非裸寫 `18`
（旁註文字中提及「18」是為了指出錯誤，不算殘留違規；判讀時應排除 `📌 SB5 補充註記` 區塊內文）。

**修正範圍說明**：原 SB5 提案 §2.1 僅列出 7 處裸寫位置，經 PO 指示重新對整個 `doc/evidence/`
資料夾完整 `grep` 後，額外發現 5 處（`SDD:L229`、`DECISIONS.md:L654/677/701` 屬 DEC-008、
`DECISIONS.md:L763` 屬 DEC-009，此 5 處由 PO 指出）及另外 2 處此前無人發現（`DECISIONS.md:L577`
屬 DEC-006、`CHALLENGES.md:L211`，由本次完整 grep 找出）。完整清單共 15 處，均已於上表登錄。

Evidence boundary：本 DEC 為純文件修正之索引記錄；不涉及任何 `src/`／`database/` 變更，
不改變任何既有測試行為。

---

## DEC-023：`label_reason` 判定範圍延後至 Gate 3 + `db_writer.py` NaN→NULL 轉換修正

- 日期：2026-08-26
- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-29
- 原始裁決來源：UG-G2-SB1 實作階段即時裁決
- 觸發 Gate：UG-G2-SB1（`daily_ml_features` Schema 擴充）

### Context（背景）

`G2_SB1_GATE_A_PROPOSAL.md`（已核准）§3.4 原規劃本 SB 會讓 `label_reason` 產生
`insufficient_data`／`no_entry` 兩個實際值。實作 `database/migrations/002_expand_ml_features.sql`
的 `chk_label_reason_consistency` 約束時，重新檢視該約束定義的三個合法分支，發現原提案對
「什麼時候該寫哪個值」的理解不完整。與此同時，本 SB 的隔離臨時 DB E2E 驗證（真實資料寫入測試，
非 mock）觸發了 `psycopg2.errors.NumericValueOutOfRange`，追查後確認 `src/loaders/db_writer.py`
既有的空值轉換邏輯存在一個此前從未被任何 mock 測試發現的真實缺陷。

### Problem（問題）

**問題一：`label_reason` 範圍誤判**

`chk_label_reason_consistency` 約束（`DB_MIGRATION_PLAN.md` §4.2）定義三個合法分支：

1. `label_reason IS NULL AND target_triple_barrier IS NOT NULL`（標籤正常生成）
2. `label_reason IS NOT NULL AND target_triple_barrier IS NULL`（Triple-Barrier 判定後
   因故無法產出標籤，說明原因）
3. `label_reason IS NULL AND target_triple_barrier IS NULL`（**尚未計算標籤**）

`insufficient_data`／`no_entry`／`ambiguous_dual_barrier` 三個 `label_reason` 值，語意上
是分支 2 的「說明原因」——它們回答的是「Triple-Barrier 演算法**執行過**，但為什麼沒有產出
標籤」。而 UG-G2-SB1 的範圍不含 Triple-Barrier 演算法本身（`target_triple_barrier` 一律不
計算，屬 `UG-G3-SB1` 的工作）。若本 SB 仍嘗試填入 `insufficient_data`／`no_entry`，等同在
Triple-Barrier 演算法從未執行的情況下宣稱「執行過但沒結果」，語意上不成立，且會使分支 3
（「尚未計算」，本 SB 實際所處的真實狀態）從未被使用到。

**問題二：`db_writer.py` 的 NaN 未被正確轉為 `NULL`**

`upsert_ml_features()` 舊版使用 `df_subset.where(pd.notnull(df_subset), None)` 將 `NaN`
替換為 `None`。此寫法對**全數值型**（如 `float64`）欄位無效——`pandas` 會把替換值 `None`
折回該欄位的原生 `NaN` 表示，而非產生 Python 原生 `None`。舊版 7 欄寫入路徑從未觸發此問題，
因為那 7 欄在既有流程中從不含 `NaN`（`article_count`／`sentiment_mean` 等皆已在
`feature_aggregator.py` 內 `fillna()` 過）。UG-G2-SB1 新增 `target_next_close`／
`target_return_1d`／`target_up_down` 三欄後，每檔股票時間序列最後一個交易日（`shift(-1)`
後無未來資料）產生的合法 `NaN` 首次流入這條寫入路徑，暴露此缺陷：`target_up_down` 為
`INTEGER` 型態，`NaN`（Python `float`）傳給 `psycopg2` 時被判定為非法整數值。

### Alternatives Considered（考慮方案）

#### `label_reason` 範圍

1. **維持原提案**：本 SB 實作 `insufficient_data`／`no_entry` 判定邏輯（不採納）——
   缺陷：語意與 CHECK 約束的分支 2 不符，且會與 Gate 3 未來實際執行 Triple-Barrier 時
   的判定邏輯產生重複或衝突風險。
2. **全部延後至 Gate 3（採納）**：本 SB 的 `label_reason` 一律維持 `NULL`（對應分支 3），
   `insufficient_data`／`no_entry`／`ambiguous_dual_barrier` 三值與計算 `target_triple_barrier`
   的邏輯一併留給 `UG-G3-SB1`，因為判斷「為什麼沒產出標籤」與「如何產出標籤」本來就該是
   同一個函式的責任邊界。

#### `db_writer.py` 空值轉換

1. **維持 `DataFrame.where(pd.notnull(df), None)`，另加欄位別特殊處理**（不採納）——
   需要為每個可能全數值型的欄位額外判斷型態，增加維護負擔且容易遺漏新欄位。
2. **逐值 `pd.isna()` 判定（採納）**：改用
   `tuple(None if pd.isna(v) else v for v in row)` 逐一檢查每個純量值，
   不依賴欄位整體 dtype，對任何欄位型態組合皆正確轉換。

### Decision（決策）

1. **`label_reason`**：`UG-G2-SB1` 之後，`label_reason` 一律為 `NULL`，直到 `UG-G3-SB1`
   實作 Triple-Barrier 演算法時一併補上三值判定邏輯。`chk_label_reason_consistency`
   約束原文不變（原設計已正確涵蓋此狀態，不需修改 DDL）。
2. **`db_writer.py`**：`upsert_ml_features()` 的空值轉換邏輯改為逐值 `pd.isna()` 判定，
   不再使用 `DataFrame.where(pd.notnull(df), None)`。

### Rationale（理由）

- `label_reason` 延後：避免在 Triple-Barrier 演算法不存在的情況下產生語意不成立的欄位值；
  將「原因判定」與「標籤計算」綁在同一個未來 SB，降低邏輯分裂在兩個不同時間點實作、
  未來需要重新對齊語意的風險。
- `db_writer.py` 修正：逐值判定不依賴欄位 dtype，是更根本的修法，而非僅補一個
  `target_up_down` 專用特例；本缺陷是透過**對隔離 DB 執行真實寫入**（非 mock）才被發現——
  說明合成情境測試無法涵蓋所有 dtype 組合，真實資料路徑驗證仍有其不可取代之處。

### Trade-offs（取捨）

- `label_reason` 延後代表 `UG-G3-SB1` 開工時需同時處理 Triple-Barrier 計算與
  `label_reason` 判定兩件事，範圍略大於原本設想的「本 SB 先做兩值、Gate 3 再補
  `ambiguous_dual_barrier`」；但避免了跨兩個時間點維護同一組語意規則的一致性風險。
- 本次修正僅涵蓋 `upsert_ml_features()` 這一個寫入路徑；`src/loaders/db_writer.py`
  其餘方法若有類似的空值轉換模式，未逐一稽核，非本 SB 範圍。

### Affected Components（影響範圍）

- `database/migrations/002_expand_ml_features.sql`（DDL 原文不變，僅實作面理解修正）
- `src/loaders/db_writer.py`（`upsert_ml_features()` 空值轉換邏輯）
- `tests/test_ml_feature_store_contract.py`（新增 `label_reason` 恆為 `NULL` 一致性測試、
  NaN→None 迴歸測試）
- `doc/upgrade/gates/G2_SB1_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/G2_SB1_GATE_B_SUBMISSION.md`

### Verification（驗證）

- [x] `tests/test_ml_feature_store_contract.py::UnimplementedColumnsStayNullTests::test_label_reason_stays_null_when_target_triple_barrier_not_yet_computed`
- [x] `tests/test_ml_feature_store_contract.py::FeatureStoreColumnContractTests::test_upsert_ml_features_converts_nan_to_none_in_pure_numeric_columns`（known-FAIL 案例已於 Gate B §8 記錄：暫時還原舊版實作可重現原始崩潰）
- [x] 隔離臨時 DB（`g2sb1_ml_features_tmpdb`，已拆除）真實寫入驗證：每檔股票最後一個交易日
      `target_next_close`／`target_up_down` 正確寫入 DB `NULL`，未再觸發
      `NumericValueOutOfRange`（`G2_SB1_GATE_B_SUBMISSION.md` §5.5）

### Remaining Risks（剩餘風險）

- `db_writer.py` 是否還有其他方法存在類似的 dtype 相關空值轉換問題未被本次修正覆蓋
  （Medium，`NOT VERIFIED`，未逐一稽核其餘方法）。

### 證據文件

`doc/upgrade/gates/G2_SB1_GATE_A_PROPOSAL.md` §3.4、§7；
`doc/upgrade/gates/G2_SB1_GATE_B_SUBMISSION.md` §1、§5.5、§8；
`database/migrations/002_expand_ml_features.sql`（`chk_label_reason_consistency`）

---

## DEC-024：時間性會變動之特徵的時點有效性判準（Temporal Validity Criterion）

- 日期：2026-08-28
- 狀態：`SUPERSEDED`（by DEC-039，2026-09-14，PO；內文保留不動，供對照歷史推理過程——見 DEC-039）
- Approved by: Project Owner
- 核准日期：2026-08-29
- 原始裁決來源：UG-G2-SB4 Gate A 審查中由 PO 提出並裁決
- 觸發 Gate：UG-G2-SB4（留言接線與衍生特徵計算）

### Context（背景）

`UG-G2-SB4` 規劃階段，PM 在核對現況時提出疑慮：留言計數是「爬取當下的快照」，
而特徵聚合依 `post_time` 把文章歸屬到交易日，因此 T+3 才回填的留言數會被當成 T 日的特徵值，
判定為根本性的前視偏誤（Look-ahead Bias），並建議以「只採用發文當日擷取的計數」處理。

**PO 於審查時指出該判準框架有誤**，這個修正過程本身就是本 ADR 要留下的主要內容——
因為錯誤的判準會導致實作**過度保守地丟掉大量合法可用資料**，而這種錯誤不會有任何
測試或檢查抓得到（它產出的是「安全但貧乏」的特徵，看起來完全正常）。

### Problem（問題）

「這個特徵值算不算前視偏誤」需要一個明確、可重複套用的判準。
錯誤的判準有兩個方向的代價：

- **太鬆**：真的把未來資訊放進特徵，模型績效虛高，且 Purge／Embargo（DEC-011）攔不到——
  它們處理的是標籤與訓練集的邊界，不是特徵值本身的時點污染。
- **太緊**：把合法可見的資訊也排除掉，丟失真實訊號，而且**不會有任何徵兆**。

### Alternatives Considered（考慮方案）

1. **以「是否為發文當日的數字」為判準（PM 原始提案，不採納）**：
   凡是留言數不等於發文當日的計數即視為污染。
   **缺陷**：此等式不成立。Roll-Forward Mapping（`assign_trading_days_to_articles()`）
   本來就會把週五盤後、週六、週日的文章歸屬到**週一**——週一早上爬到那篇週六文章有
   500 則留言，那是**週一決策時點當下真實可見**的數字，屬合法特徵。
   更進一步，模型本來就應該學到「假日後的開盤日留言數天生較多」這種真實存在、
   每週重複、預測當下確實可得的規律；把它當污染抹掉等於丟棄有效訊號。
2. **以「決策時點可見性」為判準（採納）**：見下方 Decision。

### Decision（決策）

**判準**：

> 一個特徵值是否構成前視偏誤，看的**不是**「它是不是發文那天的數字」，
> 而是「**它在被歸屬的那個交易日的決策時點，是不是已經看得到了**」。

決策時點 = `combine(trade_date, cutoff_time)`。本專案 production 的 `cutoff_time`
實際走 `15:30` 預設值（`main_etl_pipeline.py` 的 `generate_daily_features()` 呼叫未傳參數）。

**依此判準，真正的洩漏只剩兩種情況**：

| # | 情況 | 處置 |
|---|------|------|
| 1 | 舊文章被重複爬取並覆寫——`search?q={keyword}` 每次回傳最近約 20 篇、橫跨數日，三天前那篇今天又被抓到，`UPDATE` 把**今天**的累計留言數寫進**三天前**那個交易日的列 | **`write-once`**（`db_writer.update_comment_counts()` 的 `AND total_comments IS NULL`）——此條件是**承重的**，不是效能最佳化 |
| 2 | 回填期——系統開跑前的歷史文章，第一次擷取就已晚於該交易日決策時點 | `comments_scraped_at` 時點過濾，該筆特徵為 `NULL` |

**`write-once` 是核心修法**：在穩定的每日排程下，一篇文章的**第一次爬取本來就發生在
它所歸屬的那個交易日的決策時點**。只要不覆寫，第一次拿到的值就是正確時點的值——
`write-once` 直接消滅情況 1，`comments_scraped_at` 過濾則是第二道防線兼稽核依據。

**本判準約束範圍**：**所有時間性會變動的特徵**，不只留言計數——未來的 Dcard 留言、
按讚數、轉發數等同類欄位一律適用，不是一次性決定。

### Rationale（理由）

- 與 `CLAUDE.md` §7.4（防止 Look-ahead Bias）一致，且補上 DEC-011 的 Purge／Embargo
  攔不到的那條路徑（特徵值本身的時點污染，而非標籤邊界）。
- 判準以「決策時點可見性」表述，可直接對映到可執行的檢查
  （`comments_scraped_at <= combine(trade_date, cutoff_time)`），不是抽象原則。
- 保留 Roll-Forward 帶來的合法訊號（假日效應），不因防弊而誤傷。

### Trade-offs（取捨）

- 需要 `comments_scraped_at` 欄位（Migration 004）與 `write-once` 的 `UPDATE` 條件，
  兩者都增加實作複雜度。
- 回填期（系統開跑前的歷史文章）的留言特徵會是 `NULL`，且無法補救——
  但那是**誠實的 `NULL`**，優於一個看似有值、實際偷看未來的數字。
- **重要**：`comments_scraped_at` 的角色是**驗證對齊的稽核欄位**，
  **不是**「過濾掉大部分資料的篩子」。穩定運作下每篇文章的第一次爬取天然滿足時點條件，
  `NULL` 應為少數而非多數。實作時不得因為預期「反正大部分都會是 `NULL`」而過度保守。

### Affected Components（影響範圍）

- `database/migrations/004_comment_scrape_timestamp.sql`（新增 `comments_scraped_at` + 一致性 CHECK）
- `src/loaders/db_writer.py`（`update_comment_counts()` write-once、`fetch_articles_missing_comment_counts()`）
- `src/transform/feature_aggregator.py`（`_aggregate_direct_comment_counts()` 時點過濾）
- `main_etl_pipeline.py`（`backfill_ptt_comment_counts()`）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.5（時點語意寫入契約本文）

### Verification（驗證）

- [x] `tests/test_comment_features.py::CommentTimingValidityTests::test_comment_count_scraped_after_decision_point_is_excluded`（known-FAIL：移除時點過濾後此測試 FAIL）
- [x] `tests/test_comment_features.py::CommentTimingValidityTests::test_comment_count_scraped_before_decision_point_is_used`（互補案例：確認不是把所有東西都排除掉）
- [x] `tests/test_comment_features.py::CommentCountWriteOnceTests::test_update_comment_counts_is_write_once`（known-FAIL：移除 `AND total_comments IS NULL` 後此測試 FAIL）

### Remaining Risks（剩餘風險）

- 本判準目前只實作於留言計數。未來新增其他時間性會變動的欄位時，**需要記得套用**——
  機制本身不會自動涵蓋新欄位（與 DEC-021 `assert_safe_migration_target()` 依賴呼叫端
  記得呼叫是同一類「依賴記得做」的風險，Medium）。

### 證據文件

`doc/upgrade/gates/G2_SB4_GATE_A_PROPOSAL.md` §1.3（原始錯誤框架，保留以呈現推理過程）、
§14.1（PO 修正後的正確判準）；`doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.5

---

## DEC-025：留言計數只採用直接個股文章，不套用題材溢出

- 日期：2026-08-28
- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-29
- 原始裁決來源：UG-G2-SB4 Gate A，PO 裁決決策點 2 選項 C
- 觸發 Gate：UG-G2-SB4

### Context / Problem（背景／問題）

`daily_ml_features` 的留言特徵是 per (trade_date, stock_id)，但 `push_count` 等是
per article，中間必須有聚合步驟。本專案的文章→股票映射有兩條路徑（DEC-009）：
直接個股文章、題材溢出文章（一篇文章對應多檔成分股，含 `relevance_weight`）。

`FEATURE_REGISTRY.md` §5.1~§5.4 的四條公式只寫「當日推文數 push_t」，
**未定義題材溢出文章的留言數要不要計入成分股**。而既有兩個欄位的處理方式並不一致：
`article_count = direct_count + theme_count`（未加權相加）；
`sentiment_mean` 走 70/30 動態加權融合。

### Alternatives Considered（考慮方案）

1. **比照 `article_count`，未加權相加**（不採納）：溢出文章的留言數直接計入所有成分股。
2. **比照 `sentiment_mean`，乘 `relevance_weight` 加權**（不採納）。
3. **只採用直接個股文章**（採納）。

### Decision（決策）

留言計數的聚合**只採用直接個股文章**；題材溢出文章的留言數不計入其成分股。
無直接文章的 (交易日, 股票) 其三個留言特徵為 `NULL`。

### Rationale（理由）

1. **會製造假的相關性，比 `NULL` 有害**：`comment_polarization` 與 `net_push_momentum`
   **都是 `push_ratio` 的函數**。一篇矽光子文章的留言若計入 4 檔成分股，
   這 4 檔的這兩個特徵會**幾乎完全相同**——模型會看到 4 筆看似獨立、實則同源的樣本。
   這不只是稀疏問題，是主動製造虛假的橫斷面相關性。
2. **與 DEC-009 的 70/30 先例性質不同，不應套用**：DEC-009 對情緒走加權融合是合理的，
   因為**情緒是方向訊號，可以外溢**（題材看多，成分股通常也受益）；
   但**留言數量是量級**——「這篇題材文有 500 則留言」不等於「每檔成分股各獲得 500 則討論」。
   兩者是不同性質的量，不該因為都叫「社群特徵」就套用同一個聚合規則。

### Trade-offs（取捨）

- 小型概念股（多半只有題材討論、少有直接個股文章）的留言特徵會大量為 `NULL`，
  降低 `COMMENT_ENHANCED_19` 的實際覆蓋率——與 RISK-015（情緒覆蓋率）同向。
  接受此代價：語意乾淨的 `NULL` 優於同源灌水的假訊號。

### Affected Components（影響範圍）

- `src/transform/feature_aggregator.py`（`_aggregate_direct_comment_counts()` 僅取 `df_arts_direct`）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.6（聚合規則寫入契約本文）

### Verification（驗證）

- [x] `tests/test_comment_features.py::ThemeSpilloverExcludedFromCommentsTests::test_theme_article_comments_do_not_leak_into_constituent_stocks`
      （同時驗證情緒欄位的 DEC-009 既有行為未受影響）

### Remaining Risks（剩餘風險）

- 留言特徵覆蓋率可能極低（Medium）——須於 Gate B 實測回報實際覆蓋率，不得只回報公式正確。

### 證據文件

`doc/upgrade/gates/G2_SB4_GATE_A_PROPOSAL.md` §1.4、§14.2 決策點 2；
`doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.6

---

## DEC-026：UG-G2-SB5 對 Gate 0 交付物的兩處偏離——Adapter 不接入 pipeline、Feasibility Gate 強化取代

- 日期：2026-08-29
- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-29
- 原始裁決來源：UG-G2-SB5 Gate A
- 觸發 Gate：UG-G2-SB5

### Context / Problem（背景／問題）

`UG-G2-SB5` 的 Gate A 審查過程中出現兩處與**已核准 Gate 0 交付物**不一致之處。
兩者若不登記，會造成兩份已核准文件並存矛盾：

1. **Master Plan 的 SB5 Brief** 於 `Affected Components` 明列 `main_etl_pipeline.py`，
   但 PO 2026-08-28 裁決 3 定為「adapter 交付為可運作但**未接入** daily pipeline」。
2. **`MULTI_SOURCE_DATA_CONTRACT.md` §4.5** 本來就有一個 Feasibility Gate
   （`limit=1` → HTTP 200 + 有效 JSON），而本 SB 的 §3 判準 A1–A5 是它的**嚴格超集**。
   Gate A 提案初稿**完全沒有引用 §4.5**，讀起來像憑空發明判準。

### Alternatives Considered（考慮方案）

1. **沉默偏離**（不採納）：實作照裁決做，文件不動。後果是兩份已核准文件互相矛盾，
   且下一個讀者無從得知哪一份才算數。
2. **改寫原文使其一致**（不採納）：等於竄改已核准交付物的歷史，
   且會失去「當時的契約長什麼樣」這個比較基準。
3. **原文保留＋加註＋一則 ADR 說明理由**（採納）：比照 `UG-G2-SB2`
   （自 Master Plan 移除「Top-5 高讚留言擷取」）與 `UG-G2-SB4`
   （於 Brief 加註原措辭不正確）的既有慣例。

### Decision（決策）

兩處偏離**均明示登記於原文件**，原措辭保留、加註說明，不刪除、不改寫：

- **偏離一**：Master Plan SB5 Brief 的 `Affected Components` 加註
  「`main_etl_pipeline.py` — UG-G2-SB5 未修改」，並說明兩個獨立理由
  （可用性 `FAIL` 故不建立 adapter；即使 PASS 亦依裁決 3 不接入）。
- **偏離二**（同一條文兩項，合記為一則）：契約 §4.5 加註「本節於 UG-G2-SB5 被強化取代」——
  (i) 可用性判定改依 A1–A5（§4.5 原文為其真子集）；
  (ii) 請求參數由 `limit=1` 改為對齊 §4.2 正式端點的 `popular=true&limit=30`。

### Rationale（理由）

1. **「不得寫入」必須是機械性的，不能只靠記得**（偏離一）：
   不接入 pipeline，使 `engagement_metric` 跨來源顯示失真
   （愛心數被 UI 標示為「推噓數」並跨來源排序）在**結構上不可能發生**，
   而不是依賴執行者記得不要接。
2. **§4.5 說「結構已變更就降級」卻沒定義什麼叫變更**（偏離二 (i)）：
   A1–A5 把它變成機械可判定，特別是 A4 將「變更」定義為
   §4.3 五個必要欄位的存在性與型別。這是強化，不是取代其意圖。
3. **(ii) 的方向是「更貼近正式路徑」，不是「更偏離」**：
   `popular=true&limit=30` 正是 §4.2 正式端點的參數。
   若沿用 §4.5 的 `limit=1`，A6 的關鍵字覆蓋率量測會描述「最新文章」這個母體，
   而實際抓取路徑用的是「熱門文章」——**量錯母體的覆蓋率數字，誤導性大於沒有數字**。
   總請求數不變（同一次 GET）。

### Trade-offs（取捨）

- 契約 §4.5 原文與現行判準不再一字對應，讀者需同時讀原文與加註。
  接受此代價：原文是未來重新評估時「當時契約長什麼樣」的比較基準，不可失去。

### Affected Components（影響範圍）

- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`（SB5 Brief `Affected Components`）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §4.5
- `scripts/verify/dcard_availability_check.py`（`LIST_URL` 常數）

### Verification（驗證）

- [x] `python scripts/verify/gate0_contract_check.py` → `exit 0`（容器內）
- [x] 兩份文件的加註已實際寫入，原措辭保留（`git diff` 可核）

### Remaining Risks（剩餘風險）

- 未來若有人只讀 §4.5 原文而未讀加註，仍可能以 `limit=1` 重跑並得到不同的觀察範圍（Low）。

### 證據文件

`doc/upgrade/gates/closed/G2_SB5_GATE_A_PROPOSAL.md` §1.10、§1.11、§13、§15.2

---

## DEC-027：Dcard 可用性驗證判定 `FAIL`——來源標記 `DEFERRED WITH EVIDENCE`

- 日期：2026-08-29
- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-29
- 原始裁決來源：UG-G2-SB5
- 觸發 Gate：UG-G2-SB5

### Context / Problem（背景／問題）

RISK-003 自 Gate 0 起即標明 Dcard 端點為「非公開正式 API」，狀態 `NOT VERIFIED`，
處置為「可用性驗證 PASS/FAIL 分流」。本 SB 依 Gate A 提案 §3 的 A1–A5 判準
（**判準於執行前經 PO 核准，事後未作任何調整**）實際執行驗證。

### Decision（決策）

**整體判定 `FAIL`。Dcard 來源標記 `DEFERRED WITH EVIDENCE`，不建立 adapter。**
**RISK-003 由 `NOT VERIFIED` 改為 `OBSERVED`，但不標為「已解決」。**

### 判定過程與原始證據

| 判準 | 結果 | 細節 |
|------|------|------|
| A1 端點連通性 | **`FAIL`** | **HTTP 403** |
| A2 匿名性自我檢查 | `NOT EXECUTED` | 阻斷來源 A1 |
| A3 回應可解析且非空 | `NOT EXECUTED` | 阻斷來源 A1 |
| A4 契約欄位存在性與型別 | `NOT EXECUTED` | 阻斷來源 A1 |
| A5 單篇／留言端點 | `NOT EXECUTED` | 阻斷來源 A1 |
| A6 關鍵字覆蓋率（量測項） | `NOT EXECUTED` | 阻斷來源 A1；不參與判定 |

請求用量：邏輯 1／3、HTTP 嘗試 1／9。剩餘配額**未使用**。

### Rationale（理由）：這是「被擋在門外」，不是「端點消失」

回應特徵明確指向 Cloudflare 邊緣攔截，而非應用層回應：

- `Content-Type: text/html`（**不是 JSON**）
- HTML `<title>` = `Attention Required! | Cloudflare`
- `Server: cloudflare`、`CF-RAY: a32a14aa2c2a8f15-TPE`、`set-cookie: __cf_bm=…`
- 回應時間 0.14 秒、`final_url` 無重導

因此本次驗證：

- **證明了**：以一般 HTTP client、自 Docker bridge NAT 經**消費級 ISP** 出口
  （**非資料中心**），無法取得 Dcard 資料。
- **沒有證明**：端點是否仍存在、契約 §4.3 五個欄位是否仍正確——
  **A3／A4 一次都沒測到**。

一個**一般家用 IP** 即被 bot management 擋下，是「Dcard 廣泛封鎖自動化流量」的
**較強**證據，不是較弱。

### 觀察界限（必須與結論一起被讀到）

- 單一時點、單一出口 IP、單次請求：**無法區分**「Dcard 封鎖所有自動化流量」
  與「此出口 IP 被標記」。剩餘 2 次配額從同一 IP 發出亦無鑑別力，故未使用。
- **未嘗試繞過**（不更換 UA、不加 Cookie、不改請求特徵）——
  那已超出「可用性驗證」的性質，且未經授權。
- 只驗證**股票板**；契約 §4.1 的目標板塊尚有**理財板（`money`）未驗**。
- 證據檔的 `timestamp_local` 等於 `timestamp_utc`：容器未設 `TZ`，本地時間即 UTC。

### Alternatives Considered（考慮方案）

1. **更換 User-Agent／加入瀏覽器特徵後重試**（不採納）：那是規避偵測，
   超出「可用性驗證」的性質與本 SB 授權範圍。
2. **用完剩餘 2 次配額**（不採納）：同一出口 IP 再打只會得到相同的 403，
   不增加任何鑑別力，卻會讓「驗證」看起來像在試。
3. **判定 `INCONCLUSIVE`**（不適用）：A1 是 `FAIL` 而非 `NOT EXECUTED`——
   請求確實發出、端點確實回應了。儀器沒有故障。

### Consequence（後果）

- 契約 §4 章首加註「本章節暫停適用」，**原文保留**。
- Master Plan SB5 Brief 回填實際結果；**不阻擋 Gate 2 關閉**。
- **未建立 `src/extractors/dcard_scraper.py`**（不留空殼檔案——
  一個不會被呼叫的 adapter 是下一個「能力齊備但沒人用」）。

### 重新評估的觸發條件

**前提不是「再跑一次這支腳本」**——同一條路徑會得到同樣的結果。需要下列其一：

1. **Dcard 的邊緣防護政策改變**；或
2. **改採本契約未涵蓋的存取方式**（官方 API、認證存取等），**需另行提案與授權**。

沒有這一條，`DEFERRED WITH EVIDENCE` 會被讀成「過陣子再試試」。

### Affected Components（影響範圍）

- `doc/upgrade/contracts/REMAINING_RISKS.md`（RISK-003）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §4
- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`（SB5 Brief、RISK-003 列）
- `doc/governance/PROJECT_STATUS.md` §0.2、§0.3
- `src/`、`database/`：**未修改**

### Verification（驗證）

- [x] 原始證據：`doc/upgrade/gates/evidence/G2_SB5_availability_evidence.json`
- [x] 關鍵字快照：`doc/upgrade/gates/evidence/G2_SB5_keywords_snapshot.json`（25 筆 `is_active`）
- [x] 判準邏輯 known-FAIL：`tests/test_dcard_availability_criteria.py`（容器內 `Ran 25 tests` / `OK`）
- [x] `python scripts/verify/gate0_contract_check.py` → `exit 0`

### Remaining Risks（剩餘風險）

- RISK-003 **維持開啟**（`OBSERVED`，非「已解決」）。
- Dcard 缺席使情緒／討論資料的來源僅剩 PTT，與 RISK-015（覆蓋率稀疏）同向加壓（Medium）。

### 證據文件

`doc/upgrade/gates/closed/G2_SB5_GATE_A_PROPOSAL.md` §17

---

## DEC-028：來源能力宣告（Source Capability Declaration）

- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-30
- 原始裁決來源：UG-G2-SB5 決策點 5（PO 2026-08-28 裁決，2026-08-30 Gate B 核准）
- 日期：2026-08-30
- 觸發 Gate：UG-G2-SB5（決策點 5，獨立 Gate A→B 循環）

### Context / Problem（背景／問題）

`feature_aggregator.py` 有**兩道**把 `NULL` 壓成 `0` 的關卡：
`fillna(0)` 與 `groupby().agg('sum')`（pandas 對全 NaN 群組預設回 `0.0`）。
兩者使「這個來源沒有推噓的概念」被算成「推噓各 0 則」，
於是 `push_ratio = 0`、`comment_polarization = 1 - 0² = 1.0`
（「散戶意見最大分歧」）、`net_push_momentum = 0.0`（「方向毫無變化」）
——**恆定的偽造強訊號，而且不會報錯**。

三個留言特徵原本共用單一守衛 `has_comments`，等於宣稱「有留言就有方向」。

此缺陷**與 Dcard 是否可用無關**：Dcard 判定 `FAIL` 不會讓它消失，
下一個沒有推噓概念的來源（Threads，RISK-004）踩上去就會觸發。
PO 因此裁定本項**不分 PASS／FAIL 都要做**，並於 2026-08-30 定序在 `UG-G2-SB6` 之前。

### Alternatives Considered（考慮方案）

1. **以 `push_count IS NULL` 隱含判定**（不採納）：
   `FEATURE_REGISTRY.md` 已把 `NULL` 定義為「文章存在，留言尚未解析」。
   再讓它兼任「這個來源沒有方向的概念」，就是**用同一個值裝兩種語意**——
   而那正是 `engagement_metric` 一欄兩義與 `UG-G2-SB3` `push_count`
   雙語意陷阱的成因。本專案已因同一個病吃過兩次虧。
2. **建立一般化的來源能力協商層**（不採納）：
   現在只有一個真實需求，先建協商層是為想像中的第二個需求付設計費，
   而那個需求的形狀還不知道。
3. **明確的來源能力宣告表**（採納）。

### Decision（決策）

- 新增 `src/transform/source_capabilities.py`：`COMMENT_DIRECTION_SOURCES`
  與 `provides_comment_direction(source)`。**只宣告 comment direction 一項能力**，
  宣告表可擴充。
- **未登錄的來源一律視為不提供方向**（刻意的預設方向）。
- 聚合層依 `source` 過濾方向類計數；`push_sum`／`boo_sum` 聚合加 **`min_count=1`**；
  `total_sum` 不加（數量本來就該跨來源相加）。
- `has_comments` 拆為 `has_volume` 與 `has_direction`。
- `db_writer.fetch_all_for_features()` 的 SELECT 補 `source`
  （欄位一直都在且 `NOT NULL`，UI 路徑也一直有撈，缺的只是特徵路徑這一句）。
- 契約條文寫入 `FEATURE_REGISTRY.md` §5.7。

### Rationale（理由）

1. **宣告的是「能不能」，不是「有沒有」**：前者是來源的結構性質，
   後者是本次擷取的狀態（`NULL` 的既有語意）。分開才不會一值兩義。
2. **預設「不提供方向」是刻意的**：漏登錄的後果是特徵為 `NULL`（**誠實地少**），
   反過來設計的後果是偽造訊號（**安靜地錯**）。
3. **兩道關卡必須同時處理**：只拿掉 `fillna(0)` 的話，
   `agg('sum')` 會把 NaN 重新變回 `0`，測試仍 FAIL 且看起來像「修了但沒效」。
4. **契約本來就已隱含承認**：`MULTI_SOURCE_DATA_CONTRACT.md` §4.3 的 Dcard
   欄位映射表只有 8 列，`push_count`／`boo_count`／`neutral_count` 三欄不在其中。
   本決策不是發明新概念，是把契約已默認的事變成程式碼看得懂的宣告。

### Trade-offs（取捨）

- 混合來源日時，方向類特徵描述的是**有方向來源的子集**，
  數量類描述的是**全部**——兩者並列於同一列卻是不同母體。
  接受此代價（方向只能由有方向的資料算出），但**必須寫進契約**（§5.7.3），
  不得讓它變成「沒人知道為什麼」。
- `comment_volume_ratio` 在來源組成改變的邊界仍會失去可比較性——
  **本 SB 不修**，登記為 RISK-016。

### Affected Components（影響範圍）

- `src/transform/source_capabilities.py`（新建）
- `src/transform/feature_aggregator.py`（`_aggregate_direct_comment_counts`、`_compute_comment_features`）
- `src/loaders/db_writer.py`（`fetch_all_for_features` 的 SELECT）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.7

### Verification（驗證）

- [x] `tests/test_comment_features.py::SourceCapabilityTests`（6 個測試）
      —— 其中 `test_no_direction_source_yields_null_not_fabricated_signal` 與
      `test_direction_null_survives_aggregation` 為 known-FAIL，
      **實作前已確認 FAIL 並留存原始輸出**，實作後轉綠。
- [x] 反向守衛 `test_zero_push_ptt_article_is_not_null`：真實零推文（整數 `0`）
      修法後仍有值，未被誤判為「無方向」。
- [x] 全套測試（隔離臨時 DB `g2sb5dp5_tmpdb`，非 `postgres-data` 掛載）：
      `Ran 269 tests` / `OK`。
- [x] E2E 走真實 DB 讀取路徑（非 mock）：無方向來源方向類為 `NULL`、
      數量類仍有值；混合日 `polarization = 0.621302`（由 PTT 20 則算出）、
      `volume_ratio = 33.846154`（含 220 則），與人工核算逐位相符。

### Remaining Risks（剩餘風險）

- RISK-016（來源組成邊界的可比較性）——本 SB 刻意不修，已登記。
- `comment_polarization = 1.0` 仍可**正當**出現（全中立留言的 PTT 文章，
  `push_ratio = 0`）。被消除的只有「來源根本沒有方向概念卻算出 1.0」那一種。
  此為 §5.3 公式本身的性質，非本 SB 引入，未列入本次範圍。

### 證據文件

`doc/upgrade/gates/closed/G2_SB5_DP5_GATE_A_PROPOSAL.md`；
`doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.7

---

## DEC-029：新增 UG-G2-SB8 於 Gate 2——CORE_16 的四個平穩化特徵

- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-31
- 原始裁決來源：PO 2026-08-31 交辦（`UG-G2-MIG` Gate B 稽核後）

> **關於核准時點的說明（避免被誤讀為違反 §0.5 第 10 項）**：
> 本則記錄的是 **PO 當下做出的排程與範圍決定**，不是實作階段才發現的事，
> 因此**寫入時即由 PO 核准**，不等 `UG-G2-SB8` 的 Gate B。
> `PROJECT_STATUS.md` §0.5 第 10 項（「SB 新增的 ADR 於該 SB Gate B 通過時
> 一併轉 `APPROVED`」）是**防止 ADR 永遠停在 `Proposed` 的安全網，
> 不是禁止更早核准**——本則屬前者不適用的情形。

### Context / Problem（背景／問題）

`FEATURE_REGISTRY.md` §3.7 的模型輸入索引對照表把四個欄位列為
**CORE_16 的第 13–16 號**：`amplitude_ratio`／`ma5_bias_ratio`／
`ma20_bias_ratio`／`volume_ratio_5d`。§3.4 的標題即為
「CORE_16 新增平穩化特徵（4 欄）」，`:14` 對 CORE_16 的定義是
「保留 12 既有衍生特徵 **+ 新增 4 個平穩化特徵**」。

這四欄**已在契約與 schema 中宣告，`db_writer` 也寫它們**
（migration 002 建立、29 欄寫入契約涵蓋），
**但 `feature_aggregator` 從未計算**（`grep` 零命中），
`db_writer.py:531-534` 的「欄位不在 DataFrame 就填 `None`」使它們靜靜寫成 NULL。
`UG-G2-MIG` 對真實庫的逐欄檢視實測為 **0/117**。

**而掃過 Gate 2 與 Gate 3 全部 Brief：沒有任何一個 SB 負責計算它們。**
`PLANNED` 標的是「計畫要做」，但沒有任何地方寫著誰做、何時做。

**後果**：沒有這四欄，**CORE_16 實際只有 12 個特徵、
COMMENT_ENHANCED_19 只有 15 個**——整個升級計畫的目標特徵集建不出來。

### Alternatives Considered（考慮方案）

1. **放進 Gate 3 SB2（Panel Dataset 構建）**（不採納）：
   該 SB **消費**特徵存儲，讓它順便實作特徵是**把範圍洩漏到錯的 Gate**。
2. **併入 `UG-G2-SB6`／`SB7`**（不採納）：
   Universe 建立與批次化 ETL 是不同的關注點，併入會使兩者都失焦。
3. **維持延後**（不採納）：
   **Gate 2 就是 Feature Store 這個 Gate。**
   帶著自己宣告的 16 個核心特徵裡有 4 個算不出來去關閉它，
   **與帶著沒遷移的真實庫去關閉它是同一類錯誤**（RISK-017）。
4. **新增 `UG-G2-SB8` 於 Gate 2，排在 SB6／SB7 之前**（採納）。

### Decision（決策）

- **新增 `UG-G2-SB8`**：實作 CORE_16 的四個平穩化特徵，
  並補上 `db_writer` 股價查詢缺少的 `high_price`／`low_price`。
- **排在 `UG-G2-SB6`／`SB7` 之前**：SB7 是把 pipeline 大規模跑起來，
  先把特徵集補完，SB7 跑的才是完整的 CORE_16，**不用事後重跑**。
- **Gate 2 關閉條件新增一項**：「CORE_16 的 16 個特徵全部可計算」。
- **交付讀取端缺口的反查檢查**（見下節）。

### Rationale（理由）

**為什麼屬於 Gate 2 而不是 Gate 3**——這是本則 ADR 最需要被保存的判斷，
因為半年後不會有人重新推導得出來，只會看到「Gate 2 突然多一個 SB」：

> **Gate 2 的名稱就是 Feature Store & Data Pipeline。**
> 一個宣稱交付 16 個核心特徵的 Gate，若關閉時有 4 個算不出來，
> 那個 Gate 交付的不是它宣稱的東西。
> Gate 3 是**消費**特徵存儲的 Gate，不是**建立**它的 Gate。

### 【一併記錄】讀取端缺口——同一形狀的第三次

| # | SB | 缺口 | 當時紀錄 |
|---|----|------|---------|
| 1 | `UG-G2-SB4` | `market_articles` 四個留言計數欄 | `db_writer.py:489-493` 註解寫「讀取端缺口」 |
| 2 | `UG-G2-SB5` 決策點 5 | `source` 欄（`NOT NULL`，UI 路徑一直有撈） | 該處註解寫「同型缺口的**第二例**」 |
| 3 | `UG-G2-SB8`（本則） | `high_price`／`low_price`（真實庫 117/117 非 NULL） | 本 ADR |

**三次形狀完全相同：資料一直都在，是讀取端的 SELECT 沒撈。
而三次都是靠人偶然發現的**——第三次尤其明顯，
是 `UG-G2-MIG` 為了驗證 migration 才逐欄看到的，**不是任何檢查抓到的**。

**機械化處置**：`gate0_contract_check.py` **Part B 第 12 項**——
以 `FEATURE_REGISTRY` 每個特徵的「資料來源」欄，
**反查 `fetch_all_for_features()` 實際 SELECT 的欄位集合**，缺的就 FAIL。
這是 `CLAUDE.md` §9A.1 的**契約反查法**。

**放在 contract-check 而不是測試**：`.githooks/pre-commit` 檢查 1 會跑 contract-check，
**每一次 commit 都會驗**——那是唯一能在第四次發生前抓到它的位置。
測試只有在有人跑測試時才會跑。

依 §9A.2 附 known-FAIL 案例，且**用真實缺陷**：
移除 `db_writer.py:488` 的 `high_price` → 檢查必須 FAIL。

### Consequence（後果）

- `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 依賴矩陣：UG-Gate-2 **7 SBs → 8 SBs**
- `SYSTEM_UPGRADE_MASTER_PLAN.md` §8 新增 `UG-G2-SB8` Brief
- Gate 2 關閉條件新增「CORE_16 的 16 個特徵全部可計算」
- `PROJECT_STATUS.md` §0.2／§0.3 同步
- `gate0_contract_check.py` Part B 由 11 項增為 12 項

### Trade-offs（取捨）

- Gate 2 的範圍擴大一個 SB，關閉時點延後。
  接受此代價：**一個交付不出自己宣告內容的 Gate，關閉了也沒有意義。**

### Remaining Risks（剩餘風險）

- 反查檢查依賴「資料來源」欄的自然語言解析，**規則本身可能不完備**；
  處置為**明確輸出「未涵蓋」清單而非靜默略過**——
  一個宣稱涵蓋全部卻實際跳過一半的檢查，比沒有檢查更危險（Medium）。
- 四欄的 NULL 填補策略在契約中是**四欄都還沒實作時寫的**，
  `UG-G2-SB8` Gate A 提案已逐欄檢視並提出三個決策點（Low，已納入該 SB 範圍）。

### 證據文件

`doc/upgrade/gates/G2_SB8_GATE_A_PROPOSAL.md`；
`doc/upgrade/gates/closed/G2_MIGRATION_SB_GATE_B_SUBMISSION.md` §4.1（逐欄填充表）

---

## DEC-030：CORE_16 四個平穩化特徵的 NULL 策略修正，並新增第三種 NULL 成因

- 狀態：`APPROVED`（PO 2026-08-31 核准，隨 `UG-G2-SB8` Gate B）

> **【2026-09-05 同步，非新裁決】** 本則的狀態欄自 2026-08-31 起一直停在 `Proposed`，
> **而 `TRACEABILITY.md` §3.2 第 27 條同日即記為 `APPROVED`（PO 2026-08-31 核准）。**
> PO 於 2026-09-05 確認核准屬實，本次僅補上同步。
>
> ⚠ **不一致的方向是最糟的那一種**：依 `CLAUDE.md` §0.2，
> **`DECISIONS.md` 是權威 —— 而權威的那一份是舊的。**
> 兩次獨立查證都查了權威文件，兩次都得到與事實相反的答案 ——
> **不是查得不夠仔細，是查對了地方而那個地方是錯的。**
>
> **為什麼兩次都沒查到**：查詢用的樣式是 `` `PROPOSED` ``（反引號＋全大寫），
> 而本則寫的是 `Proposed（…）`。**一個為了確認「沒事」而寫的檢查，
> 用了一個文件裡不存在的格式 —— 它每次都會回報零命中**（§9A.1）。
>
> **系統性修法另案**：`DECISIONS.md` 的 `- 狀態：` 目前有六種格式，
> 使該欄位無法被機械檢查。應由 `gate0_contract_check.py` 列舉狀態值、
> 比對 `TRACEABILITY.md` 對同一則 DEC 的記載是否一致。
- 日期：2026-08-31
- 觸發 Gate：UG-G2-SB8

### Context / Problem（背景／問題）

`UG-G2-SB8` 實作 CORE_16 的四個平穩化特徵時，依 PO 指示
**逐一對照 `FEATURE_REGISTRY.md` §5A 檢視每一個 `fillna` 是否正當，不照抄契約**。

檢視結果：**契約指定的四個 NULL 策略中有兩個不正當**，
且其中一個**證偽了 §5A.1 對成因的窮盡性宣稱**。

**共同成因**：這四欄的 NULL 策略是在**四欄都還沒實作時**寫的。
在實作之前，沒有人需要回答「這個 `fillna` 會在什麼情況下觸發」。
**契約寫過不等於契約想過。**

### Decision（決策）

#### 1. `amplitude_ratio`：`fillna(0.0)` → **保持 NULL**

`(High − Low) / Close` 三個值**全部來自同一列**，沒有 lag、沒有 rolling window
——**成因 W（暖機期）在結構上不可能發生**。

因此該填補**唯一可能觸發的情境是 high/low 取不到**，那是**成因 F**，
而 §5A.1 對 F 的規定是「**必須保持 NULL，嚴禁任何填補**」。

**契約在這一欄上自相矛盾**：NULL Handling 欄寫「`fillna(0.0)`；**需 high/low/close**」
——那句「需 high/low/close」正是在描述 F 的觸發條件，
然後對它指定了 F 明文禁止的處理方式。

語意上，`0.0` 代表 `High == Low`，即**漲跌停鎖死或整日無成交**——
一個真實且有意義的市場事件。把「取不到高低價」填成「振幅為零」，
正是 §5A.1 那句「把後者填成前者，等同於讓模型讀到一個從未觀測到的訊號」。

> **與本專案已修掉三次的病同型**：`DEFAULT 0` 禁令、
> `fillna(0)` 偽造 `comment_polarization = 1.0`、`sum()` 把全 NaN 變 0。

#### 2. `volume_ratio_5d`：拆成兩種成因，並**新增第三種成因 U**

契約原文「`fillna(1.0)`；**暖機期分母為零時**」把兩件事寫成同一件：

| 情境 | 成因 | 處理 |
|------|------|------|
| 不足 5 日基準 | **W 暖機期** | `fillna(1.0)`（維持契約） |
| **`MA5_Vol == 0`**（過去 5 日完全沒有成交） | **U（新增）** | **保持 NULL** |

**`MA5_Vol == 0` 既不是 W 也不是 F**：

- 不是 W——§5A.1 對 W 的定義是「資料**確實存在**，但時序視窗尚未累積足夠歷史」，
  而此處**視窗是足的**
- 不是 F——§5A.1 對 F 的定義是「資料**根本沒取得**」，
  而此處**資料取得了，就是 0**

**§5A.1 原文宣稱「任何欄位出現空值，只可能是以下兩種成因之一」——
那個窮盡性被這一格證偽。**

因此新增 **成因 U（Undefined，數學未定義）**：
資料齊備、視窗足夠，但公式在該點數學上未定義（零除等）。
處理方式為**保持 NULL，嚴禁填補**——
填補值必然是一個**與事實相反**的陳述：
填 `1.0` 等於宣稱「今日成交量等於 5 日均量」，而事實是「過去 5 日完全沒有成交」。

#### 3. `ma5_bias_ratio` / `ma20_bias_ratio`：**維持契約的 `fillna(0.0)`**

暖機期確實屬成因 W，依 §5A.1 允許填補。

**但記錄一個未解決的問題**：`0.0` 的語意是「收盤價恰好等於均線」，
在值域 `(-inf, +inf)` 裡那是一個**事件**，不是結構中點
（對照 `rsi_14 → fillna(50.0)` 的 50 是 `[0,100]` 的**結構中點**，
中性是它的內建語意）。

**同一個批評適用於已上線的 `return_1d` 與 `volatility_5d/20d`**
（分別填「價格完全沒變」與「波動度為零」，兩者也都是事件）。
因此**不在本 SB 決定**——在 SB8 裡決定只會有兩種結果：
與兄弟欄位不一致，或 SB8 膨脹成重新審視全部價量特徵。
**已登記 RISK-020，Gate 3 啟動前裁決。**

### Alternatives Considered（考慮方案）

- **`MA5_Vol == 0` 沿用 `compute_push_ratio()` 的 Laplace 平滑（分母 +1）**（不採納）：
  Laplace 的 `+1` 只有在**分母的自然尺度與 1 可比**時才是平滑。
  推噓數是 0～數百的小整數，`+1` 是輕微擾動；
  而成交量以股／張計，量級 10³–10⁹，**對零基準加 1 股不會正則化**，
  只會讓比值等於**今日原始成交量**——那已經不是一個比值。
  **同一個技巧不因為本專案用過就適用。**
- **照抄契約**（不採納）：那正是 PO 指示要避免的。

### 【實作決定】契約未指定的 MA 視窗語意

契約只寫 `Volume / MA5_Vol` 與 `(Close − MA_n) / MA_n`，**未指定 MA 是否含當日**。
本 SB 的決定：

| 特徵 | MA 視窗 | 理由 |
|------|--------|------|
| `ma5_bias_ratio`／`ma20_bias_ratio` | **含當日** | `(Close − MA5)/MA5` 是標準均線偏離率；MA 不含當日會變成另一個指標 |
| `volume_ratio_5d` | **不含當日**（`t-5..t-1`） | 沿用同族 `comment_volume_ratio` 的既有慣例（§5.2 明文「僅使用 t-5..t-1 已知資料」）。基準含當日會讓今日成交量出現在自己的分母裡，壓抑本來要偵測的放量訊號 |

### Consequence（後果）

- `FEATURE_REGISTRY.md` §3.4 兩欄的 NULL Handling、§5A.1 成因表（新增 U）、
  §5A.3 對照表兩列
- `src/transform/feature_aggregator.py` 依上述策略實作
- RISK-020 新增

### Verification（驗證）

- [x] `tests/test_stationarity_features.py`（9 個測試），其中兩個為 known-FAIL：
      `test_missing_high_low_does_not_fabricate_zero_amplitude`（決策 1）、
      `test_zero_volume_baseline_is_not_filled_as_one`（決策 3）——
      **實作前已確認 FAIL 並留存原始輸出**。
- [x] 反向守衛 `test_zero_amplitude_is_a_real_observation_not_null`：
      `High == Low`（漲跌停鎖死）是真實觀測，必須有值 `0.0` 而非 NULL。
- [x] 互補守衛 `test_warmup_fills_one_per_contract`：
      暖機期仍填 `1.0`——沒有這一半，把所有東西設成 NULL 也會通過決策 3 的測試。

### Remaining Risks（剩餘風險）

- RISK-020（暖機期填補可能偽造事件值）——涵蓋本則決策 3 未處理的部分。
- 成因 U 目前只在兩處被識別（`MA5_Vol == 0`、`Close == 0`）。
  §5A.3 其餘欄位**尚未依新的三成因分類重新檢視**（Low，與 RISK-020 同批處理）。

### 證據文件

`doc/upgrade/gates/G2_SB8_GATE_A_PROPOSAL.md` §3；
`doc/upgrade/gates/G2_SB8_GATE_B_SUBMISSION.md`

---

## DEC-031：新增 UG-G2-SB9（候選池價格資料取得），並修正 SB6／SB7 的循環依賴

- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-08-31
- 原始裁決來源：PO 2026-08-31 交辦（`UG-G2-SB8` 結案、交辦 `UG-G2-SB6` 前查現況時發現）

> **關於核准時點**：比照 DEC-029，本則記錄的是 **PO 當下做出的排程與範圍決定**，
> 非實作階段才發現的事，因此寫入時即核准。
> `PROJECT_STATUS.md` §0.5 第 10 項是**防止 ADR 永遠停在 `Proposed` 的安全網，
> 不是禁止更早核准**——本則屬前者不適用的情形。

### Context / Problem（背景／問題）

**循環依賴**（Master Plan §8 實測）：

| | `UG-G2-SB6` | `UG-G2-SB7` |
|---|---|---|
| Dependency | `UG-G2-SB1` | **`UG-G2-SB6`** |
| In Scope | Universe 建構；**流動性排名** | **股價批次下載** |
| DoD | 每個 Snapshot 只用 `effective_date` 前資料 | **150 檔**批次 ETL 可完成 |

SB6 的「流動性排名」需要**全市場候選股的價格資料**，
而取得那批資料的能力寫在 SB7 的 In Scope；**SB7 卻依賴 SB6**。

且 SB7 的 DoD 寫「150 檔」——**它假設那 150 檔已經存在**，
批次處理的是一個**已知的** universe，不負責建立候選池。

> **「取得候選池的價格資料」這件事，兩個 SB 都沒有負責。**
> 這與本專案已抓到三次的**讀取端缺口**是同一個形狀
> （SB4 留言計數欄、SB5 `source`、SB8 `high/low`），
> 只是發生在**計畫層**而不是程式層：
> **每個部分都寫了，但把它們接起來的那一步沒有人負責。**

**現況佐證**（唯讀實測）：`stock_prices` 僅 **4 檔**（14／14／25／64 個交易日）、
**無成交金額欄位**、`universe_snapshot`／`stock_universe` 表皆不存在、
`universe_builder.py` 不存在、股票清單來自手工維護的 `entity_mapping`。

### Alternatives Considered（考慮方案）

1. **併入 SB6**（不採納）：SB6 的職責是**建構 Universe 與 PIT Snapshot**，
   取得原料是不同的關注點；併入會讓 SB6 同時承擔對外部端點的依賴驗證。
2. **併入 SB7**（不採納）：SB7 依賴 SB6，併入無法解開循環。
3. **調換 SB6／SB7 順序**（不採納）：SB7 的 DoD 明寫「150 檔」，
   那個數字來自 Universe——調換順序後 SB7 仍然不知道要批次處理哪 150 檔。
4. **新增 `UG-G2-SB9`，依賴上排在 SB6 之前**（採納）。

### Decision（決策）

- **新增 `UG-G2-SB9`：候選池價格資料取得**，職責是為 SB6 的流動性排名提供原料。
- **依賴順序**：`SB9 → SB6 → SB7`。
  **編號與執行順序刻意不一致**（SB9 在 SB6 之前執行）——
  PO 接受此不一致，但 Master Plan 的依賴矩陣**必須明確標示執行順序**，
  不得讓後人以為編號即順序。
- **目標訂 (b)：歷史 PIT Snapshot 序列，深度至少 3 年**，
  依據 `PURGED_WALK_FORWARD_SPEC.md:146`「歷史深度 | 至少 3 年（理想 5 年以上）」。
  **這不是選項**——沒有它 RISK-012 存活偏誤無法解決，
  Gate 3 的 Purged Walk-Forward 也跑不起來。
- **分兩階段**：階段一取最近 **60 個交易日**驗證整條路徑；
  階段二回補至至少 3 年，**需 PO 另行放行**。
- **候選空間依 DEC-017：上市 + 上櫃（排除興櫃）**（2026-08-31 補記）。
  **關鍵在 DEC-017 的排除清單**：若候選空間本來就只有上市，
  「興櫃」根本不需要被單獨列出來排除——**它被明文排除，代表候選空間比「上市」大**；
  加上原文是「台股**普通股**」而非「台股**上市**普通股」。
  **分階段**：階段一只驗證上市（證交所）端點——一次驗兩個來源只會讓未知翻倍；
  **上櫃在本 SB 範圍內，延後至階段二**——**沉默地縮小範圍，與明示地分階段，是兩件事**。
  美股（`NVDA`）不在候選空間內，**但本 SB 不移除**，已登記 RISK-021。
- **Gate 2 關閉條件中「Universe 建立」的措辭收緊**為可證偽形式
  （涵蓋規模與歷史深度）——**不新增第七項，是把既有那一項寫清楚**。

### Rationale（理由）

**為什麼分兩階段，且分界不在成本**：

階段一要回答的問題——端點是否提供**成交金額**、約 1000 檔的資料格式是否乾淨、
**停牌／下市當天那檔股票在回應裡長什麼樣**——
**用 60 次請求回答，與用 792 次回答，答案完全一樣**。

而如果哪裡不對，**在幾分鐘後就知道，不是在把約 79 萬筆髒資料寫進資料庫之後才知道**。

**為什麼「Universe 建立」的措辭必須收緊**：
它是那種**在 4 檔股票上也能宣稱達成**的措辭——
與 `UG-G2-SB1` 的「`daily_ml_features` 有 29 欄」（沒說哪個資料庫）是同一個形狀。
RISK-017 就是那個形狀造成的。

### Consequence（後果）

- `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 依賴矩陣：UG-Gate-2 **8 SBs → 9 SBs**，
  並標示執行順序
- §8 新增 `UG-G2-SB9` Brief；SB6／SB7 的 Dependency 欄修正
- Gate 2 關閉條件「Universe 建立」改寫
- `PROJECT_STATUS.md` §0.2／§0.3 同步

### Trade-offs（取捨）

- Gate 2 再擴大一個 SB，關閉時點再延後。
  接受此代價：**SB6 在缺少原料的情況下無法交付它宣稱的東西**，
  而那正是本專案這幾輪一再處理的同一件事。
- 編號與執行順序不一致，增加閱讀成本。
  接受此代價：既有編號已在多份文件中被引用，重編號的成本與風險更高。

### Remaining Risks（剩餘風險）

- 端點驗證可能 `FAIL`（B5 成交金額尤其關鍵）——處置路徑已寫入 SB9 提案 §5.5（Medium）。
- 階段二的 792～1280 次請求對證交所服務的負載——
  節流參數已定為 3.0–5.0 秒（比 PTT 保守），且需 PO 另行放行（Low）。

### 證據文件

`doc/upgrade/gates/G2_SB9_GATE_A_PROPOSAL.md`

---

## DEC-032：對外取數的重試紀律——403／429 與 5xx／傳輸層必須分開

- 狀態：`APPROVED`
- Approved by: Project Owner
- 核准日期：2026-09-02（隨 `UG-G2-SB9` Gate B 通過一併核准，`PROJECT_STATUS.md` §0.5 #10）
- 提出日期：2026-09-02
- 提出來源：`UG-G2-SB9` 三年回補實作期間，複查方指出該規則變更未有 ADR 登錄
- 適用範圍：**專案級**——所有對外部端點取數的腳本，含 `UG-G2-SB6`／`UG-G2-SB7`

> **為何需要 ADR**：這不是 `UG-G2-SB9` 的內部細節，是**取數紀律的變更**。
> 原規則是「403／429／5xx 一律立即停止、不重試」，現在拆成兩類。
> **SB6 與 SB7 都要對外取數，它們會繼承這條規則。**
> 而該規則目前只存在於腳本註解、Gate B 報告與 hook 註解裡
> ——**三個地方都不是規格權威**。

### Context / Problem（背景／問題）

`UG-G2-SB5`（Dcard）建立的紀律是：**遇 403／429／5xx 立即停止，不重試至成功、
不調整節流後重跑**。它要防的是兩件事：

1. **重試至成功會把封鎖訊號磨掉** —— 一個「試到過為止」的腳本，
   永遠不會回報「我們被擋了」。
2. **把失敗藏起來** —— 調整參數直到通過，等於用結論換耐心。

`UG-G2-SB9` 的櫃買三年回補（740 交易日）實測顯示，把三者綁在同一條規則下，
**會讓取數在結構上無法完成**：

| 觀測 | 次數 |
|------|------|
| HTTP 520（Cloudflare 邊緣層「origin 未回應」） | 十餘次 |
| TLS 交握失敗（`CERTIFICATE_VERIFY_FAILED: Missing Subject Key Identifier`） | 十餘次 |
| **403／429（服務拒絕）** | **0 次** |

**一次都沒有被拒絕過。** 停下來的全部是「服務沒能回答」。

### Alternatives Considered（考慮方案）

1. **維持單一規則、靠加大段數吸收**（不採納）：`UG-G2-SB9` 實測，
   `TRANSPORT_RETRIES = 2` 時一整段只換到 1 個邏輯請求、**0 個交易日**。
   **段數是拿來計「邏輯進度停滯」的，拿去吸收 TLS 抖動會讓它失去意義。**
2. **關閉憑證驗證**（明確拒絕）：`verify=False` **不是修好，是把偵測拿掉**。
3. **無上限重試**（明確拒絕）：那正是原規則要防的「重試至成功」。
4. **有界重試 + 全程入帳**（採納）：見下。

### Decision（決策）

**依「服務是否已經回答」二分，不依 HTTP 狀態碼是否 ≥ 400。**

| 類別 | 語意 | 處置 |
|------|------|------|
| **403 / 429** | **服務在叫你停** | **硬停，一次都不重試。** 回報並請示，不自行續行 |
| **5xx** | 服務**沒能回答** | 退避後**有界重試**（實作值：60 秒 × 最多 1 次）。仍失敗則**停止本段並記下該日期** |
| **傳輸層失敗**（TLS 交握／連線／逾時） | 服務**連我們問了什麼都還不知道** | 於**同一個邏輯請求內**有界重試（實作值：最多 5 次，退避 5／10／20／40／60 秒）。**不消耗邏輯請求配額** |

**判別依據是「有沒有拿到 `status_code`」，不是例外類別名稱**
——後者需要窮舉，而窮舉不完的那一項會被靜默歸錯類。

**三條不可放寬的邊界**：

1. **重試必須有上限、有退避、每次嘗試入帳**（雙軌計數：邏輯請求／HTTP 嘗試）。
2. **5xx 重試失敗後停止本段，不得跳過該日繼續** ——
   價格序列裡的一個洞，跟一次比較慢的執行不是同一件事。
3. **不得關閉或放寬憑證驗證。**

### Rationale（理由）

**傳輸層失敗發生在服務知道我們要什麼之前。**

TLS 交握是對主機做的，**在任何 path 或 query 送出之前完成或失敗**；SNI 只帶主機名。
**憑證驗證失敗的那一刻，伺服器根本不知道我們要問哪一天。**

因此把它當成「服務拒絕」是**歸因錯誤**——那與原規則要防的東西無關。
而 5xx 是邊緣層的暫時性錯誤，**不是對方在拒絕我們**。

**實測依據（同一個起點，`20260615`）**：

| `TRANSPORT_RETRIES` | 取得天數 |
|---------------------|---------|
| 2 | **0**（SSL ×3） |
| 5 + 遞增退避 | **105**，且該日**第一次嘗試就通過** |

**該日期連敗 4 次曾被誤讀成「這個日期特殊」。** 那是**選擇效應**：
每一段都從中斷點起跑，所以每一次隨機失敗都**必然**落在同一個日期上。
**它是失敗累積的地方，不是失敗的原因** ——
一個看起來像訊號的數字，其實是取樣方式的產物。

### Consequence（後果）

- `UG-G2-SB9` 的兩市場三年回補得以完成：**740/740 交易日、1,389,890 列**，
  邏輯請求 804／850、**403／429 零次**。
- `UG-G2-SB6`／`UG-G2-SB7` 繼承本規則，不需各自重新發明。
- 取數腳本必須實作**雙軌計數**，否則無法區分「要問的問題數」與「造成的實際負載」。

### Trade-offs（取捨）

**放寬的是重試次數，不是重試的邊界。** 上限、退避、入帳三者皆在，
「重試至成功」與「把失敗藏起來」兩條都沒有被違反。

**代價**：單一邏輯請求的最壞情況耗時由數秒拉長到約 2 分鐘（5 次退避累計 135 秒）。
在 740 天的回補上這是可接受的；**在互動式路徑上不是**，故本規則**限批次取數**。

### Remaining Risks（剩餘風險）

- **TPEx 端點的 SSL 不穩定成因未查明**（`Missing Subject Key Identifier`，
  疑為部分邊緣節點送出不合規的中間憑證）。**有界重試是吸收症狀，不是理解成因。**
- **本規則未機械強制**：目前靠各腳本自行實作。`UG-G2-SB9` 實測顯示
  **同一個規則實作在一支腳本而不在另一支**，是本 SB 第六次同型缺陷。

### 證據文件

`doc/upgrade/gates/G2_SB9_GATE_B_SUBMISSION.md` §3、§4；
`scripts/verify/fetch_candidate_prices.py`（`TRANSPORT_RETRIES`／`SERVER_ERROR_RETRIES`）；
十份段報告 `doc/upgrade/gates/evidence/G2_SB9_tpex_backfill_seg*.json`


---

## DEC-033：60 日流動性窗**嚴格早於** `effective_date`，且校準基準隨之作廢重算

- 日期：2026-09-03
- 狀態：`APPROVED`（`UG-G2-SB6` 實作期發現 — 隨該 SB Gate B 通過核准）
- Approved by: Project Owner
- 核准日期：2026-09-03
- 觸發 Gate：UG-G2-SB6

### Context（背景）

`UG-G2-SB6` 的 Gate A 提案於 2026-09-03 經 PO 核准，進入實作。
實作 `src/transform/universe_builder.py` 時必須決定一件提案沒有給出單一答案的事：
**60 交易日的流動性窗，要不要包含 `effective_date` 當天？**

### Problem（問題）

**已核准的文件對這件事給了兩個相反的答案，而兩邊都被實際使用過。**

| 立場 | 出處 |
|------|------|
| **嚴格早於** | DEC-017（**APPROVED**）§Decision 逐字：「每月 Universe 只能使用**生效日前已知**的 60 交易日成交資料」；`G2_SB6_GATE_A_PROPOSAL.md` §5 的 P1 逐字：`max(trade_date) < effective_date` |
| **含當日** | §6 第 3 項的校準 SQL `c.rk BETWEEN e.rk-59 AND e.rk`；§7 決策點 1 的 K = 1 措辭「必須在 `effective_date` **當天**出現」；K 校準 SQL 同樣為 `e.rk-59 AND e.rk` |

不裁定就無法寫出 `liquidity_window()`。而**沉默地選一邊是最糟的選項** ——
兩種窗口的輸出差異小到不會被列數總計發現（實測 46 列中僅 8 列不同、差 1~2 檔），
**足以讓錯誤的那個一路通過所有既有檢查**。

### Alternatives Considered（考慮方案）

1. **含當日（`rk-59 .. rk`）**：與既有兩份校準 SQL 一致，46 列基準無需重算。
   **不選** —— 一份在 `2022-11-01` 生效的快照若使用當天的整日成交金額，
   **要等到當天收盤後才算得出來**，在當天做任何決定時它並不存在。那是 Look-ahead Bias。
2. **嚴格早於（`rk-60 .. rk-1`）**：**採用**。
   依 `CLAUDE.md` §0.2 的來源優先順序，**已核准的 ADR（優先序 2）高於 Gate A 提案（過程文件）**；
   且提案自己的 P1 也站在這一邊 —— **站在含當日那邊的是兩段 SQL 與一句措辭，不是決策。**
3. **窗口可設定，由呼叫端決定**：**不選** ——
   PIT 不是偏好設定。一個可以被設定成違反 DEC-017 的參數，遲早會被那樣設定。

### Decision（決策）

1. `liquidity_window()` 回傳 `effective_date` **之前**的 60 個交易日，**不含當天**。
2. `build_snapshot()` 在收到任何 `trade_date >= effective_date` 的觀測時
   **raise `LookaheadError`**，不是忽略它。取數 SQL 另帶 `trade_date < %s`，
   **兩道防線**。
3. **K = 1 的語意隨之改寫**：該股必須在 `effective_date` **之前最後一個交易日**
   出現於報表中，才視為「仍在交易」。
4. **§6 第 3 項的 46 列逐月基準作廢重算**，新基準見證據文件。
   舊基準保留為紀錄，**不刪除**。
5. 重算**必須在實作首次執行之前完成** —— 順序顛倒就成了照著結果改判準。
6. **【本次補上的機制，複查方 2026-09-03】判準在實作期被修改時，修正後的判準必須「單獨 commit 一次，然後才跑」。**
   **理由**：本次的順序宣稱（判準先於首次執行）**無法被獨立驗證** ——
   mtime 記的是最後一次寫入而非首次執行，且兩個檔在同一個 commit 裡，
   git 歷史不帶順序。**產物不記錄順序，宣稱就只能是宣稱。**
   單獨 commit 讓 git 歷史自己帶著順序，**與任何人的說法無關**。
   > 這是同型問題的第三次（前兩次：`prior_common_supplied` 的來源、
   > 「已實測還原」寫在實測之前），而正解在第一次就講出來了 ——
   > **真正的修法是讓來源被記下來，而不是事後論證。**

### Rationale（理由）

判準寫死在前、跑完只做比對，是本專案一貫的紀律。
**但這次的情形是判準本身錯了，而不是實作沒達標。**
兩者的處置完全相反：後者要改實作，前者要改判準 —— 而**改判準必須有實作輸出以外的依據**。
本次的依據是 DEC-017 的逐字條文，`universe_builder` 當時**一次都還沒執行過**。

### Trade-offs（取捨）

- 46 列基準中 8 列改變，既有校準檔降為歷史紀錄；讀者需分辨哪一份是現行。
- K = 1 的新語意**是換算而非重測**：原校準的排名以含當日的窗口計算，
  排名輕微變動時該落在哪一格未經重新量測。標籤 `INFERENCE`，重測需求已登記。

### Affected Components（影響範圍）

- `src/transform/universe_builder.py`
- `tests/test_universe_builder.py`
- `doc/upgrade/gates/evidence/G2_SB6_union_count_calibration_pit.json`（現行基準）
- `doc/upgrade/gates/evidence/G2_SB6_union_count_calibration_4y.json`（已作廢，保留）
- `doc/upgrade/gates/G2_SB6_GATE_A_PROPOSAL.md` §5 P1、§6 第 3 項、§7 決策點 1

### Verification（驗證）

- [x] `test_liquidity_window_excludes_effective_date`（`tests/test_universe_builder.py`，2026-09-14 重跑 PASS）
- [x] `test_p1_universe_point_in_time_no_future_data`（含 known-FAIL，`tests/test_universe_builder.py`，2026-09-14 重跑 PASS）
- [x] 管線寫入 `universe_snapshots` 的逐月候選數與現行基準逐一比對，不符數為 0——`doc/upgrade/gates/evidence/G2_SB6_union_count_calibration_pit.json`（2026-09-03，PREVIOUSLY VERIFIED，本次未重跑）
- [ ] NOT VERIFIED → 去處：K = 1 在**排他窗**下的誤判曲線重測——同 Remaining Risks 所載，尚未執行，所需 SQL 與資料皆在真實庫內、成本低，待下次觸碰 `universe_builder.py` 時一併補測

### Remaining Risks（剩餘風險）

- **K = 1 在排他窗下未重測**（Medium）：換算落在原校準的零誤判區間內，
  但排名基礎已改變。重測所需的 SQL 與資料皆在真實庫內，成本低。
- 同型的窗口定義若日後出現在 Gate 3 的 panel dataset 或標籤生成，
  **不會被本 ADR 自動涵蓋** —— 那是另一組程式碼的另一個決定。

### 證據文件

`doc/upgrade/gates/evidence/G2_SB6_union_count_calibration_pit.json` 的 `THE_CONFLICT`；
`doc/upgrade/gates/evidence/G2_SB6_implementation_verification.json`

---

## DEC-034：舊批 PTT 文章以**允許清單排除**出特徵，而非修正或刪除

- 日期：2026-09-05
- 狀態：`APPROVED`（PO 2026-09-05 核准，隨 `UG-G2-SB7` Gate B）
- 觸發 Gate：UG-G2-SB7

> ⚠ **本則刻意不重述規則。** 「哪些 `source` 進入 `daily_ml_features`」的權威定義在
> **`MULTI_SOURCE_DATA_CONTRACT.md` §3.5B**，本則只記**決定與被否決的替代方案**。
>
> **分工的理由**：契約是**活文件**，描述「現在的規則」，規則變了就被改寫；
> 而 `evidence/` 是專案唯一設計成**只增不減**的地方（`CLAUDE.md` §16.1）。
> **若「為什麼不修正、不刪除」只寫在契約裡，日後有人改規則時它會跟著被改掉**
> —— 因為它看起來不是規則，是說明。
> **而下一個想反轉這個決定的人，正是需要那段推理的人。**
>
> **DEC-030 剛示範了重複會發生什麼事**：同一個狀態寫在兩個地方，
> 兩份漂移了五天而沒有人發現（見該則的 2026-09-05 同步註記）。

### Context（背景）

`UG-G2-SB7` 第 5 項把 PTT 取數由**逐關鍵字搜尋**改為**看板固定頁面 + 記憶體比對**。

切換前寫入的 331 列（`source = 'ptt_stock'`）在收尾期被查出
**76 列 `post_time` 錯誤，年份差 +1 至 +7**，其中 15 列落在 `daily_ml_features`
的日期窗內 —— **2019~2025 年的文章被聚合進 2026 年的特徵列**。
成因與修正見 `MULTI_SOURCE_DATA_CONTRACT.md` §3.6A 與 commit `e67d3d6`。

### Problem（問題）

那 331 列要不要繼續進入特徵？**而「日期是錯的」不是唯一要考慮的事。**

### Alternatives Considered（考慮方案）

1. **修正 `post_time`（`UPDATE` 76 列）**
   - 需 PO 授權的真實庫寫入 + 備份 + 還原驗證；可逆
   - **否決理由見 Rationale 第 1 點** —— 它解決的不是主要問題

2. **刪除該批（`DELETE` 331 列）**
   - 同樣需授權與備份，**且不可逆**
   - 否決：它銷毀了一批**日後可能有用**的原始觀測，
     而我們並不需要銷毀它才能停止使用它

3. **排除（讀取端過濾）** ← **採用**
   - **零資料庫操作、完全可逆**
   - 資料一列都不動；只有 `db_writer.fetch_all_for_features` 的取數 SQL 改變

### Decision（決策）

1. **採方案 3。** 規則（哪些 `source` 進入特徵）見
   `MULTI_SOURCE_DATA_CONTRACT.md` §3.5B，程式落點見該節。
2. **以允許清單實作，不以排除清單。**
3. **修正（方案 1）不放棄，只是押後** —— 押到「決定要用那批資料」的時候。
   **若那一天不會來，那次對真實庫的授權寫入就永遠不必發生。**
4. **刪除（方案 2）明確否決**，不列為日後選項。

### Rationale（理由）

1. **決定性的一點：就算日期修對了，那 331 篇仍然是另一種取樣。**

   > **舊批是逐關鍵字搜尋橫跨七年，新批是看板固定頁面只涵蓋最近幾頁。**
   > **修正日期只解決「哪一天」，不解決「怎麼取到的」。**

   一批日期正確、但取樣方式不同的資料混進特徵，
   **仍然會讓 `REMAINING_RISKS.md` RISK-015 的覆蓋率量測失真** ——
   而那正是該風險要量的東西。
   **所以「修正」是一件價值未證實的工作**：為了目前不打算使用的資料，
   付一次對真實庫的授權寫入。

2. **兩件事必須分開**：
   - **修正**是**資料完整性** —— 一個把 2019 記成 2026 的欄位是缺陷，修它永遠是對的
   - **排除**是**特徵組成的決定** —— 要不要讓另一種取樣 regime 進訓練資料

3. **為什麼是允許清單**：兩種寫法的**失效方向相反**。
   `source <> 'ptt_stock'` 在日後新增來源而忘了登錄時**自動放行**；
   `source IN (...)` 則**不放行**。判準與 DEC-028 的
   `provides_comment_direction()` 預設方向**完全相同** ——
   **漏登錄的後果應該是「誠實地少」，不是「安靜地錯」。**

### Trade-offs（取捨）

- **情緒特徵覆蓋率降為零。** `daily_ml_features` 的 `SUCCESS` 將由 38 降為 **0**
  （改動前寫死的預期，見證據文件）。
  ⚠ **那不是回歸，是現況的真實樣貌** —— 先前的 38 是由日期錯置的舊文撐起來的。
- **331 列成為目前不被使用的資料。** 它們仍在庫裡、仍可查詢，
  但不進特徵，直到（若）方案 1 被執行。
- **允許清單需要維護**：新增取數模式時必須登錄，否則該模式的資料不會進特徵。
  **那個失效方向是刻意選的。**

### Affected Components（影響範圍）

- `src/transform/source_capabilities.py`
- `src/loaders/db_writer.py`（`fetch_all_for_features`）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §3.5B

### Verification（驗證）

- [x] `tests/test_feature_source_allowlist.py` 全數通過——2026-09-14 重跑 `Ran 8 tests ... OK`
- [x] `test_an_unregistered_source_does_not_enter` —— **允許清單與排除清單的差別所在**（同檔，2026-09-14 重跑 PASS）
- [x] `test_ptt_stock_has_direction_but_is_excluded_from_features` ——
      **釘住「能力宣告」與「特徵組成」是兩個不同的問題**（同檔，2026-09-14 重跑 PASS）
- [x] known-FAIL：改寫成 `source <> 'ptt_stock'` 時測試確實 FAIL——`test_the_excluded_source_is_not_named_as_an_exclusion`（反向釘子）即此案例，已實測
- [ ] NOT VERIFIED → 去處：「下一次 `run_feature_engineering_pipeline` 後，`SUCCESS` 實測為 0」是 2026-09-05 決策生效**當下**的一次性驗證，未留下可定位的執行證據；**且此不變式此後已不再成立**——`PRE-G3-01` 回補與後續真實 PTT 擷取已產生合法的新批資料，`source_status=SUCCESS` 現為正數（2026-09-14 真實庫實測 783／449,263），回頭驗證這條會驗到錯的東西，不予補測

### Remaining Risks（剩餘風險）

- **覆蓋率為零不是本則解決的問題**（High）。解法是 **PTT 歷史回補**（另案，Gate 3 之前）
  與 E3 修正後的每日累積，**不是把舊批放回來**。
- **回補本身有一個必須先決定的前提**：留言計數帶前視偏誤
  （回補抓到的舊文，其留言累積到抓取當下）。
  `push-ipdatetime` 的處置**必須在回補動手之前決定** ——
  回補的昂貴部分是每篇一次內頁請求，**先補完再決定要時間戳，整批要重抓**。
- 方案 1 若日後執行，**會改變既有特徵列的值** —— 屆時需獨立的備份與前後比對。

### 證據文件

`doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §3.5B、§3.6A；
`doc/upgrade/gates/evidence/G2_SB7_exclusion_expectations.json`；
`doc/upgrade/gates/evidence/G2_SB7_controlled_run_results.json` 的
`FOR_THE_LATER_DISPOSITION_DECISION`

---

## DEC-035：Triple-Barrier 標籤條件表修訂——邊界優先序與 NaN 價格處理

- 日期：2026-09-09
- 狀態：APPROVED（`UG-G3-SB1` Gate B 核准結案時一併核准 — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-09-09
- 觸發 Gate：UG-G3-SB1

> **本則修訂 DEC-018，不取代它。** DEC-018 的 anchor／三分類／同日雙觸決策維持不變；
> 本則補齊 DEC-018 原表沒有回答的兩個邊界情況，這兩個情況是 `UG-G3-SB1` 綠色實作與
> 審查期間才浮現的——DEC-018 立案時（Gate 0）尚未實作到會撞見它們的程度。

### Context（背景）

`PURGED_WALK_FORWARD_SPEC.md` §4.3 原表第 1～2 列（先觸線即定 1/−1）與第 5 列
（資料集最後 H 個交易日一律 NULL）在「剩餘天數不足 H、但那剩餘天數內已可觀察到
觸線」的情況下字面矛盾，規格原文未言明優先序。

`stock_prices` 的 `open_price`／`high_price`／`low_price` 三欄皆為 nullable
（`schema.sql`），且該欄位在 PostgreSQL `NUMERIC` 型別下另有獨立於 SQL `NULL` 的
`NaN` 值。`UG-G3-SB1` 綠色實作的第一版（commit `d2e3f27`）未處理這兩種缺值情形：
NaN 比較恆為 `False`，使演算法落入迴圈末端被靜默標記為 `0`（Timeout）——一筆缺
資料的列因此以合法標籤進入訓練集，違反 `CLAUDE.md` §7.1「失敗不得偽裝成正常
結果」。真實庫 `postgres`@`localhost:5432` 確有 1 列命中（NVDA `2026-06-04`，四個
價格欄皆為 `NaN`），非人為構造的假設情境。

### Problem（問題）

若不明訂這兩個邊界的處理順序，日後任何人重讀規格或重寫實作，都可能重新做出
「先觸即定」或「NaN 靜默當作未觸線」的選擇，重演本次審查期間發現的問題。

### Alternatives Considered（考慮方案）

1. **「先觸即定」優先於「剩餘天數不足」**：若剩餘天數內已觀察到觸線，即使不足
   完整 H 天窗口也判定該次觸線結果。**否決**：這會讓每檔股票序列尾端只可能出現
   `±1` 或 `NULL`、不可能出現 `0`——觸線事件可在不足 H 天內被觀察到，但「到期未
   觸線」這個結論必須撐滿整個 H 天窗口才能下，於是尾端標籤分布會系統性偏向極端
   走勢（截斷偏差）。
2. **新增第四個 `label_reason` 值**（例如 `price_data_missing`）區分「資料本身
   缺失」與「資料集邊界」兩種成因。**否決**：`chk_label_reason_domain` 的值域是
   資料庫層 CHECK 約束，改動需要 migration；且「算不出來就是 NULL」是本專案對
   NULL 語意的一貫原則（`return_1d`／`comment_polarization` 等既有欄位皆以此
   原則處理缺值），沿用既有 `insufficient_data`／`no_entry` 已能表達，沒有新增
   值域的必要。
3. **採字面規則，剩餘天數檢查優先於價格路徑評估；NaN 檢查優先於觸線判定**
   （**採用**）：見 Decision。

### Decision（決策）

修訂 DEC-018 的標籤條件表，補上以下邊界處理順序（四層依序短路，任一層命中即不
下探下一層）：

(a) **剩餘天數 < H → 一律 `insufficient_data`，即使剩餘天數內已觀察到觸線也不
    例外**——此檢查優先於價格路徑評估。
(b) **Anchor（`Open[T+1]`）為 `NaN` → `no_entry`**——與「`Open[T+1]` 不存在」同一
    reason 值，因為兩者對下游而言都是「無法確定進場價」。
(c) **評估窗口內任一日 `High`／`Low` 為 `NaN` → `insufficient_data`**——且此檢查
    必須先於當日觸線判定，否則僅檢查非 `NaN` 的那一側，等同用另一側偽造一個
    確定結果。
(d) 判斷順序本身是規格的一部分，不是實作細節——`PURGED_WALK_FORWARD_SPEC.md`
    §4.6 已據此重寫偽碼。

**理由**（對應 Alternatives 的否決理由）：截斷偏差（見方案 1 否決理由）；
「算不出來就是 NULL」的一貫原則（見方案 2 否決理由）；不新增 `label_reason`
值域，`chk_label_reason_domain` 不需修改。

### Rationale（理由）

四層短路順序讓「資料不足以下判斷」與「資料本身有缺陷」兩類情況，都收斂到既有
的 `insufficient_data`／`no_entry` 語意下，不製造新的分類維度；且順序本身可被
測試直接釘死（見 Verification），日後重構若打亂順序會立即被測試攔下。

### Trade-offs（取捨）

- 剩餘天數不足時捨棄了「本可判定」的少數尾端標籤（每檔最多 H-1 列）——換取尾端
  分布不帶截斷偏差。
- NaN 價格的處理成本是每次評估多兩層檢查（anchor 一次、逐日窗口內每天一次）——
  對本專案資料量級（3,713 列 × 至多 5 天）效能影響可忽略。

### Affected Components（影響範圍）

- `src/ml/triple_barrier.py`
- `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §4.3、§4.6

### Verification（驗證）

- [x] `test_tb_insufficient_data_overrides_early_touch`（T-TB-15）——剩餘天數不足
      時即使窗口內已觸線仍判 `insufficient_data`；known-FAIL：「先觸即定」錯誤
      語意注入後確認該測試 FAIL（`AssertionError: False is not true`）
- [x] `test_tb_anchor_nan_is_no_entry`（T-TB-16）——anchor NaN 判 `no_entry`；
      known-FAIL：對修復前的 `d2e3f27` 舊實作直接跑出紅（`AssertionError: False is not true`）
- [x] `test_tb_window_nan_is_insufficient_data`（T-TB-17）——窗口內 NaN 判
      `insufficient_data`，且驗證 NaN 檢查確實先於觸線判定；known-FAIL 同上，
      對修復前舊實作直接跑出紅
- 真實庫落地驗證：`postgres`@`localhost:5432` NVDA `2026-06-03`（其 T+1 anchor =
  `2026-06-04` 的 NaN open）正確得到 `no_entry`；`2026-06-04` 本身（T+1 = 06-05
  有效）正常算出 `-1`——證明 NaN 列只影響「以它為 anchor」的那一列，不影響它
  自己的標籤。見 `doc/upgrade/gates/evidence/UG_G3_SB1_real_db_write.json`

### Remaining Risks（剩餘風險）

- RISK-024：`stock_prices` 允許 NaN 價格列入庫，擷取端未擋下（本則只處理消費端
  的正確反應，不處理成因本身，另案處理）。

### 連結

DEC-018（本則修訂的對象）、DEC-023（`label_reason` 判定範圍延後至 Gate 3 的前例）、
DEC-030（NULL 策略第三種成因的前例，`UG-G2-SB8`）、RISK-024

### 證據文件

`doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §4.3、§4.6；
`tests/test_triple_barrier.py`；
`doc/upgrade/gates/UG_G3_SB1_GATE_B_SUBMISSION.md`

---

## DEC-036：新增 `UG-G3-SB2a`——458 檔 Universe 資料回補，自 `UG-G3-SB2` 拆分

- 日期：2026-09-09
- 狀態：APPROVED（`UG-G3-SB2` Gate B 核准結案時一併核准 — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-09-10
- 觸發 Gate：UG-G3-SB2 Gate A

### Context（背景）

`UG-G3-SB2`（Panel Dataset 構建）Gate A 提案唯讀查證 `universe_snapshots` 全部
46 期（`effective_date` 2022-11-01 ~ 2026-08-03），**跨期去重 `included=TRUE`
共 458 檔**（非僅最新一期的 150 檔——面板是 Point-in-Time 的，DEC-017／RISK-012
要求逐期取當期名單，故量體是跨期聯集，不是單期快照）。查證結果：

- **455 檔**在 `entity_mapping` 無任何路由列（僅 3 檔台股既有路由：2330／2382／6488）
- **458/458 檔**皆已存在於 `candidate_prices`（`UG-G2-SB9` 回補，2022-08-03~2026-09-04，
  ~4.05 年）——**價格資料本身已齊備**，只是從未搬進生產特徵管線
- `stock_prices`／`daily_ml_features` 現皆僅 **3 檔**有資料（NVDA 不在台股候選
  空間內，本不屬於此缺口）

可重跑：
```sql
SELECT COUNT(DISTINCT effective_date), COUNT(DISTINCT stock_id) FILTER (WHERE included)
FROM universe_snapshots;                                                        -- 46 | 458
SELECT COUNT(DISTINCT u.stock_id) FROM universe_snapshots u
WHERE u.included AND NOT EXISTS (SELECT 1 FROM entity_mapping e WHERE e.stock_id=u.stock_id); -- 455
SELECT COUNT(DISTINCT stock_id) FROM universe_snapshots
WHERE included AND stock_id NOT IN (SELECT DISTINCT stock_id FROM candidate_prices);          -- 0
```

### Problem（問題）

`SYSTEM_UPGRADE_MASTER_PLAN.md` 原 `UG-G3-SB2` Brief 假設「從 `daily_ml_features`
讀取跨股票面板」——該假設在 Gate 3 啟動時未成立（僅 3 檔）。若把「把 458 檔資料
從 `candidate_prices` 搬到可訓練狀態」與「寫一個正確的 PIT 面板讀取器」混在同一
個 SB，兩者的 Definition of Done 無法乾淨地逐項驗收，且前者牽涉 RISK-022（價格
基準混合擴大至 458 檔）與 RISK-024（NaN 價格列）兩個既有風險的前置處理，量體與
讀取器工程本身不同源。

### Alternatives Considered（考慮方案）

1. **併入 `UG-G3-SB2` 一起做**：否決——讀取器正確性與資料是否齊全是兩個不同的
   驗證問題，混在一起會讓 Gate B 的 DoD 難以逐項打勾。
2. **維持現狀，`UG-G3-SB2` 只讀現有 3 檔**：否決——與 Master Plan「Universe 全
   股票 × 日期矩陣」的設計意圖不符，且 `UG-G3-SB3` D3 情緒對照臂的樣本量不會
   因此改善。
3. **拆成獨立 `UG-G3-SB2a`**（**採用**）：資料回補與讀取器工程分開驗收；`UG-G3-SB2`
   本體維持路由補齊（見下方，**不隨資料回補一併拆出**，依 Gate 3 啟動書 §12
   裁決⑥「路由補齊併入 `UG-G3-SB2` 為明確子項，不拆獨立 SB」）+ 每日尾端重算
   掛點 + 讀取器三項子工作。

### Decision（決策）

1. 新增 `UG-G3-SB2a`：**458 檔 `candidate_prices → stock_prices` 搬遷 + 全套
   特徵工程 + Triple-Barrier 標籤**。範圍與前置條件見
   `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2a Brief。
2. **路由補齊（455 筆）不隨資料回補拆出，維持在 `UG-G3-SB2` 本體**——與已核准
   的 Gate 3 啟動書 §12 裁決⑥一致，不重新開放該裁決。
3. `UG-G3-SB3`（Specialist Models）依賴 `UG-G3-SB2` **與** `UG-G3-SB2a` 皆完成，
   不可任一先行。
4. `UG-G3-SB2a` 動工前，必須先定 `stock_prices` 的價格基準政策（RISK-022 面向
   二，見 SB2a Brief 第 1 項）——**這不是純資料庫搬遷操作，混合基準的問題會
   從 3 檔擴大到 458 檔**。

### Rationale（理由）

把「工程正確性」與「資料規模／來源」兩個不同性質的問題分別驗收，符合本專案一貫
的拆分原則（同 `UG-G3-SB1` §6.1 不動既有 `label_end_date` 欄位、避免耦合兩個決定
的邏輯一致）。編號採 `SB2a`（而非重新排列既有 SB3~SB7 編號），比照 `UG-G2-SB9`
「編號晚但執行早」的前例，不因插入新 SB 而擾動既有編號序列。

### Trade-offs（取捨）

- 多一個 SB，`UG-G3-SB3` 的開工時點需等兩個前置 SB 皆完成，比原規劃多一道關卡。
- `UG-G3-SB2a` 的工作量體（458 檔全套管線）明顯大於原先「146 檔」的估計（實為
  455 檔路由 + 458 檔資料，量體約為原估計的 3 倍），需要獨立的執行時間評估，
  本則不預先估算執行時間。

### Affected Components（影響範圍）

`database/`（`stock_prices` 資料）、`src/transform/feature_aggregator.py`（執行）、
`src/ml/triple_barrier.py`（執行）、`SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2、§9

### Verification（驗證）

- [x] `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 依賴矩陣與 §9 Brief 已同步（`8c3e10d`）
- [x] `UG-G3-SB2a` 自己的 Gate A 提案——原文「待開」已過期：Gate A 已核准（`f668503`）、前置條件（RISK-022 基準政策）已於 Gate A 內回答，`UG-G3-SB2a` 三段真實庫寫入全部完成並於 2026-09-11 Gate B 核准結案（`5dc8d75`）

### Remaining Risks（剩餘風險）

- RISK-022（面向二，價格基準混合）：`UG-G3-SB2a` 動工前必須先定政策，否則搬遷
  458 檔會把既有 3 檔的混合問題等比例放大。
- RISK-024（NaN 價格列）：回補批次規模化後，NaN 列的絕對數量可能增加，`UG-G3-SB1`
  的消費端防禦行為正確但需在 SB2a 量測規模，不得假設維持與現有 1 列同量級。

### 連結

DEC-017（Universe 定義）、DEC-018／DEC-035（Triple-Barrier）、RISK-012、RISK-022、
RISK-024、Gate 3 啟動書 §12 裁決⑥（路由補齊不拆獨立 SB）

### 證據文件

`doc/upgrade/gates/UG_G3_SB2_GATE_A_PROPOSAL.md`（重送版）§2；
`doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2a

---

## DEC-037：Roll-Forward 交易日曆改依股票自身，取代全市場聯集（RISK-027 方案 B）

- 日期：2026-09-12
- 狀態：APPROVED（隨段 2 重跑真實庫寫入完成 — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-09-12
- 觸發 Gate：`UG-G3-SB2a` Gate B 結案後之獨立小案（`bug-fix-protocol` Gate A，
  PO 2026-09-11 裁決採方案 B）

### Context（背景）

`UG-G3-SB2a` 段 2 唯讀基線比對期間發現：`feature_aggregator.py` 的 Roll-Forward
Mapping 所依賴的交易日曆，取自輸入價格表 `stock_id` 的**聯集**，不分市場
（`RISK-027`，`OBSERVED`，2026-09-11）。生產輸入含 NVDA（美股）時，日曆含美股
獨有交易日；台股假期期間發布的文章被滾動到這些「美股有、台股沒有」的日期，
與台股價格表合併時靜默流失。根因排查過程見 `CHAL-011`。

### Problem（問題）

若不修，任何跨市場（現況：TWSE／TPEX＋US）輸入的特徵計算都會系統性遺失台股
在「純美股交易日」發布的文章情緒與留言訊號，且**不會報錯**——`daily_ml_features`
該日該股僅是情緒／留言欄缺席，看起來與「當天沒有文章討論」無法區分。
`UG-G3-SB2a` 段 1 已把 458 檔全部搬進 `stock_prices`，段 2 若對全量重算會
繼承同一缺陷。

### Alternatives Considered（考慮方案）

1. **方案 A：日曆依市場分開計算**（台股／美股各自的交易日集合）——否決：
   需要一個「市場」中介欄位才能決定每篇文章該用哪一份日曆；真實庫查證
   （唯讀）顯示 `theme_stock_mapping` 有 6 個題材含 `stock_id` 不在
   `entity_mapping`（查不到市場），方案 A 的市場中介在這裡會斷；且題材溢出
   本來就會一文對到多檔、可能跨市場，「先定市場再選日曆」對這個形狀是多一層
   不必要的假設。
2. **方案 C：兩階段折衷**——診斷階段的初步偏好，前提為「一篇文章不會同時對到
   TW 與 US 股票」。PO 2026-09-11 指示查證後，真實庫（唯讀）顯示
   `theme_stock_mapping` 的「AI伺服器」題材同時涵蓋 TWSE 股票與 NVDA——**前提
   不成立，方案 C 出局**。
3. **方案 B：文章依其對應股票自身的交易日曆做 Roll-Forward**（**採用**）：
   語意上就是對的——「這篇文章對股票 S 的貢獻，落在 S 在 cutoff 後的第一個
   交易日」；直接路由與題材溢出用同一條規則；TWSE／TPEX／US 三者一體適用，
   不需要市場中介這個額外概念；向量化後（`np.searchsorted` 逐股票分組）
   效能可接受（見 Verification）。

### Decision（決策）

1. 新增 `src/transform/feature_aggregator.py::assign_trading_days_per_stock()`：
   接受已展開的 `(article, stock_id)` 列與 `{stock_id: 交易日清單}` 字典，
   規則與既有 `map_timestamp_to_trading_day()` 逐分支等價（統一為「該股票
   日曆中 `>= 生效日` 的最小交易日」），僅將日曆來源換成該列自身股票的日曆。
2. `generate_daily_features()` 的處理順序改為：**先**與 `df_mapping`／
   `df_theme_mapping` 合併展開成 `(article, stock_id)` 列，**再**呼叫
   `assign_trading_days_per_stock()` 指派 `trade_date`——不得反過來（合併前
   就用單一日曆決定 `trade_date`，即修復前的錯誤順序）。
3. `_aggregate_direct_comment_counts()` 不另外修改——它讀的是
   `df_arts_direct['trade_date']`，該欄在上述順序調整後已自動正確；留言的
   時點有效性過濾（DEC-024）邏輯不變。
4. 既有 `map_timestamp_to_trading_day()`／`assign_trading_days_to_articles()`
   **保留不變**（其他呼叫端與既有測試仍直接使用單一日曆的語意），不因本決策
   刪除或改變其行為。
5. **不變性判準**：混合市場輸入下，每檔股票的輸出必須等於該檔單獨輸入時的
   輸出——`tests/test_risk027_cross_market_calendar.py` 的
   `test_mixed_market_input_matches_single_market_input_for_each_stock`。
6. `UG-G3-SB2a` 段 2（既有特徵）修復後須重跑，另走 RISK-013 三步驟協議；
   **NVDA 不得作為零差異對照組**（NVDA 自身在台股假日／美股交易日撞期時
   也會受影響），預期影響集改用「新舊兩版對同一輸入的差異＝實際差異」
   （相等斷言，比照段 3 的作法）。段 3（Triple-Barrier 標籤）為純價格計算，
   不受本決策影響，不需重跑。

### Rationale（理由）

方案 B 是三個方案中**假設最少、規則最統一**的一個：不需要「市場」這個額外
中介概念（該中介在題材股上會斷），直接路由與題材溢出共用同一條規則，且
TWSE／TPEX／US 未來任何新市場都自動適用，不需要為新市場擴充分支邏輯。

### Trade-offs（取捨）

- 效能：文章展開成 `(article, stock_id)` 列後逐股票分組做 `searchsorted`，
  比修復前「先算一次全域日曆」多一層分組運算；4 項合成測試下無可觀測影響
  （0.4 秒內完成含 4 個測試）。**2026-09-12 段 2 重跑實測（459 檔、449,263
  列全量）**：新版（現行）全量重算約 4 秒，與舊版（`0da87d9`）全量重算
  耗時相同量級——多一層分組運算在此規模下無可觀測的效能代價。
- `assign_trading_days_per_stock()` 與 `map_timestamp_to_trading_day()` 是
  兩套獨立但語意必須保持等價的實作（後者的「全市場聯集」場景不會消失——
  其他呼叫端仍可能只有單一市場輸入）；未來修改任一方的 cutoff／Roll-Forward
  規則時，需同步檢查另一方，`CLAUDE.md` §9A 對兩者的 known-FAIL 案例要求
  是防止語意漂移的唯一機制。

### Affected Components（影響範圍）

- `src/transform/feature_aggregator.py`（`assign_trading_days_per_stock()`
  新增；`generate_daily_features()` 的處理順序調整）
- `tests/test_risk027_cross_market_calendar.py`（新增，4 項測試）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md`（§5.5A 新增）

### Verification（驗證）

- [x] `tests/test_risk027_cross_market_calendar.py` 4/4 GREEN（修復前 4/4 FAIL，
      落點精確對應根因）
- [x] 全套測試 696/696 OK（容器內，Python 3.14.6）
- [x] `python scripts/verify/gate0_contract_check.py` 13/13 PASS，exit 0
- [x] **`UG-G3-SB2a` 段 2 全量重跑（2026-09-12，RISK-013 三步驟協議完成）**：
      `scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py --write`，只更新
      「舊版 vs 新版」機械算出的預期影響集與「新版 vs 現有庫」實際差異集
      斷言相等後的 **132 個 `(stock_id, trade_date)` 鍵、14 檔股票**
      （2330/2344/2408/5289/2454/NVDA/2382/2317/3008/3081/3163/3363/6442/6669）
      的 12 個情緒／留言欄。PRE 備份
      `stock_prediction_system2_PRE_g3_sb2a_stage2_rerun_risk027_20260912_120202.dump`、
      POST 備份
      `stock_prediction_system2_POST_g3_sb2a_stage2_rerun_risk027_20260912_121252.dump`
      （皆存 `D:\Python\Database_Backups\Stock_Prediction_System2\`）。commit
      前後核對（RETURNING 鍵集合、交易內讀回、標籤計數未變、全表 25 欄
      重算 vs 庫零差異、`stock_prices` 列數＋md5 寫入前後相同）全數 PASS；
      審查方獨立對真實庫重跑全表重算與跨庫（真實庫／PRE 還原／POST 還原）
      逐列雜湊比對，PRE vs 真實庫 132 列不同、POST vs 真實庫 0 列不同，
      三份狀態互相印證。**留言三欄（`comment_volume_ratio`／
      `comment_polarization`／`net_push_momentum`）在全部 132 鍵的新舊值
      皆為 NaN**——真實資料的留言全部因 DEC-024 時點過濾而不通過，本決策
      對留言路徑的修復效果**僅由合成測試（`tests/test_risk027_cross_market_calendar.py`
      的 `test_comment_counts_follow_same_per_stock_trading_day`）證明，
      真實資料無法驗證**。證據見
      `doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_rerun_risk027.json`。

### Remaining Risks（剩餘風險）

- 段 2 重跑前，`daily_ml_features` 既有列仍帶著 RISK-027 的已知缺陷（文件
  已於 `REMAINING_RISKS.md` 揭露，未實際變更資料庫）。
- `assign_trading_days_per_stock()` 與 `map_timestamp_to_trading_day()` 的
  雙重實作維護成本（見 Trade-offs）。

### 連結

RISK-027、CHAL-011、DEC-024（留言時點有效性）、`UG-G3-SB2a`（段 2／段 3）

### 證據文件

`src/transform/feature_aggregator.py::assign_trading_days_per_stock()`；
`tests/test_risk027_cross_market_calendar.py`；
`doc/upgrade/contracts/REMAINING_RISKS.md` RISK-027；
`doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.5A

---

## DEC-038：D3 對照實驗的兩種情緒覆蓋率子集口徑，與多數類基線 tie-break 規則

- 日期：2026-09-13
- 狀態：APPROVED（隨 `UG-G3-SB3` Gate B 核准結案 — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-09-13
- 觸發 Gate：`UG-G3-SB3`（Specialist Models／D3 對照實驗）

### Context（背景）

`UG-G3-SB3` 全量報告產出後，PO 複核指出：Gate A 提案原設計的「情緒子集」
（面板中曾出現過非 `NULL` `sentiment_mean` 的**股票**，取其全部列）不足以
量化「B 臂與 A 臂在 99.5% 的列上輸入完全相同」這件事——同一檔股票的其他
日期即使沒有情緒訊號，仍算在這個子集內，會高估 B 臂實際可用的資訊量。

### Problem（問題）

若只用股票子集做 D3 對照，段級報告會低估「B 臂真的多出資訊」的樣本有多
稀少，讀者可能誤以為 20/458=4.4% 的股票覆蓋率就是 B 臂訊號的實際密度，
而忽略同一檔股票絕大多數日期仍是 `NULL`。

### Alternatives Considered（考慮方案）

1. **只用股票子集（既有設計）**——否決：無法回答「B 臂真的多出資訊的列
   有多少」，只能回答「哪些股票曾經有過訊號」。
2. **只用列子集（`article_count>0` 或 `sentiment_5d_ma` 非 `NULL`）**——
   否決：單獨使用會失去「這個訊號分布在哪些股票」的脈絡，且與既有
   `sentiment_subset` 欄位不相容，會造成報告 schema 的破壞性變更。
3. **兩種子集並列**（**採用**）：股票子集與列子集回答的是不同問題，
   互補而非互斥，皆需在段級報告輸出，不得只取其一。

### Decision（決策）

1. `sentiment_subset`（股票子集）與 `signal_rows_subset`（列子集）為兩種
   **互補、非互斥**的口徑，段級報告須並列兩者，不得只取其一；兩者的定義
   字串（`SUBSET_DEFINITIONS`）寫入報告 JSON 本身（`subset_definitions`
   欄位），不只留在原始碼 docstring 裡。
2. 多數類基線（`majority_baseline`）票數並列時取數值最小者（`np.unique`
   遞增排序 + `argmax` 取第一個最大值），確保可重現、不依賴任意
   tie-break；規則字串（`MAJORITY_BASELINE_RULE`）同樣寫入報告 JSON 的
   `aggregate.majority_baseline.rule`。
3. `signal_rows_subset` 的判定：`article_count>0` 或 `sentiment_5d_ma`
   非 `NULL` 的列本身；缺少必要欄位時回傳全 `False`（不報錯），比照既有
   `determine_sentiment_subset_stock_ids()` 對缺欄的處理方式。

### Rationale（理由）

股票子集的「同一檔股票的其他日期即使沒訊號也算在內」會高估 B 臂實際可用
的資訊量；列子集才是「B 臂真的多出資訊的列」的精確定義，是「覆蓋率不足
以檢定」這一裁決文字（見 `doc/upgrade/gates/UG_G3_SB3_GATE_B_SUBMISSION.md`
§2.4）的量化基礎。兩者並列而非互相取代，讀者才能同時看到「哪些股票」與
「多少列」兩個維度。

### Trade-offs（取捨）

- 段級報告 schema 因此多兩組欄位（`signal_rows_subset`／
  `aggregate.signal_rows_subset`／`aggregate.majority_baseline`），
  增加讀者需要理解的欄位數；已用 `subset_definitions`／`rule` 兩個
  自我說明欄位緩解，不需要讀者回頭查原始碼。
- 多數類基線的 tie-break 規則（取數值最小者）是任意選擇之一，並非唯一
  合理選項；本決策的重點是「確保可重現」，不是宣稱這是最優的 tie-break
  策略。

### Affected Components（影響範圍）

- `scripts/verify/ug_g3_sb3_specialist_report.py`
  （`determine_signal_row_mask`／`SUBSET_DEFINITIONS`／
  `MAJORITY_BASELINE_RULE`／`compute_majority_baseline_predictions`）

### Verification（驗證）

- [x] `tests/test_ug_g3_sb3_specialist_report.py::SignalRowMaskTests`／
      `AggregateAcrossFoldsTests` 全綠（含 tie-break 規則的合成案例）
- [x] 四份段級報告 JSON（`target_up_down`／`target_triple_barrier` ×
      `rolling`／`expanding`）皆含 `subset_definitions`／
      `aggregate.majority_baseline.rule` 兩欄

### Remaining Risks（剩餘風險）

若未來資料源擴充（RISK-015 後續案）使覆蓋率大幅提升，`signal_rows_subset`
與 `sentiment_subset` 的差距會縮小，屆時兩種口徑是否仍需並列可重新評估，
本決策不預先假設擴充後的情境。

### 連結

RISK-015、`UG-G3-SB3`

### 證據文件

`scripts/verify/ug_g3_sb3_specialist_report.py`；
`tests/test_ug_g3_sb3_specialist_report.py`；

---

## DEC-039：留言特徵時點有效性改依逐則時間戳重算，取代文章層級擷取時點過濾（修訂 DEC-024）

- 日期：2026-09-14
- 狀態：APPROVED
- Approved by: Project Owner
- 核准日期：2026-09-14（真實庫寫入複核通過，binding confirmation 生效）
- 觸發：RISK-023（`bug-fix-protocol` 獨立小案，Gate A 提案 `doc/upgrade/gates/closed/RISK023_GATE_A_PROPOSAL.md`）

### Context（背景）

DEC-024 建立了留言特徵的時點有效性判準，並以「穩定運作下，一篇文章的第一次爬取本來就發生在它所歸屬的那個交易日的決策時點」為前提，設計了 `comments_scraped_at <= decision_point` 的文章層級過濾，預期 `NULL` 只出現在系統開跑前的回填期、且應為少數。

RISK-023 Gate A 診斷以本專案已驗證的實際排程常數（`scheduler.py:31-32` 每日 15:35 執行一次；`feature_aggregator.py` 決策點 cutoff 15:30）獨立模擬穩定運作下一整週的發文情境，發現該前提**結構性不成立**：通過率僅 0.20%~0.25%，NULL 比例恆定維持在 99.75%~99.8%，不會隨系統穩定運作而降低。

同時，`PRE-G3-01` 已建立 `article_comments` 逐則留言時間戳表與 `comment_timeline.counts_as_of()` 重算函式，使 DEC-024 情況 2（回填期）「無法對齊決策時點」的前提也不再成立。

### Problem（問題）

DEC-024 的文章層級過濾機制，其設計依據的兩個假設都已被證明不成立或不再成立。繼續依賴這個機制，留言特徵三欄（`comment_volume_ratio`／`comment_polarization`／`net_push_momentum`）在生產環境會恆定為 99.8% NULL，而非 DEC-024 原本預期的「少數」——這實質上等同於這三個特徵從未真正上線過。

### Alternatives Considered（考慮方案）

1. **調整排程時間（單獨採用，不採納為唯一方案）**：無法解決「文章本身歸屬到當日、但只有在當日排程執行時才第一次被看見」這個結構性時序。
2. **文章層級過濾 + 放寬 cutoff／排程對齊規則（不採納）**：治標不治本，仍是「整篇文章要嘛全通過要嘛全排除」的粗粒度判斷。
3. **改依 `article_comments` 逐則時間戳重算（採納，見 Decision）**：直接以留言本身的時間戳判斷是否落在決策點之前，不受「文章擷取整體完成時刻」這個代理變數拖累。

### Decision（決策）

1. **特徵計算改為逐則重算**：`_aggregate_direct_comment_counts()` 改用 `comment_timeline.counts_as_of(comments, decision_point)`，取代對 `market_articles` 已聚合欄位的文章層級 `comments_scraped_at` 過濾。
2. **DEC-024 情況 2（回填期 → NULL）的前提已不成立，其處置隨之取消**：回填期與穩定期的文章一體適用逐則重算。
3. **DEC-024 情況 1（write-once）保留**，但角色限縮為 `market_articles` 聚合欄位（稽核、非特徵用途查詢）的一致性保護，不再是特徵計算依賴的資料來源。
4. **NULL／0 語意**（沿用 `FEATURE_REGISTRY.md` §5A）：已擷取旗標 = `market_articles.total_comments IS NOT NULL`；未擷取 → NULL（成因 F）；已擷取（無論該文章實際有無 `article_comments` 列）→ 呼叫 `counts_as_of`，回傳值即為觀測到的計數（含 0）。
5. **決策點以 (article, stock_id) 列為單位**，非以文章為單位——同一篇文章對到不同股票時，各自用該列的 `trade_date` 算 `decision_point`。
6. **`validate_comment_bounds()` 接線**：`comment_time` 落在 `[post_time, comments_scraped_at]` 之外者排除計數。全庫實測僅 13 則違規、集中於單一已知文章（`article_id=1495`），成因與 write-once 凍結問題相同，非新的年份推斷缺陷。
7. **P6 不變式改寫**：`article_comments` 列數 ≥ Σ `market_articles.total_comments`（逐文章不等式），驗證機制為新增的唯讀腳本 `scripts/verify/risk023_p6_invariant_check.py`，不放 `gate0_contract_check.py`。
8. `comments_scraped_at`／`market_articles` 聚合欄位不廢除——仍是稽核與「已擷取」旗標的權威來源。
9. **`comment_seq` 時間回退防禦性守衛（`suspect` 標記，不去重）**：呼叫 `counts_as_of` 前，先檢查該篇文章的留言時間依 `comment_seq` 排序是否非遞減；出現回退，該篇標記 `suspect`，涉及的所有 `(article, stock_id)` 列留言三欄一律給 NULL。不去重（根因另立 **RISK-029**，不在本案修擷取器）。
10. **P6 一致性守衛**（2026-09-14 Gate B 前複核要求）：`total_comments`（`market_articles` 凍結快照）與 `df_comments`（呼叫端傳入的逐則資料）是兩個獨立來源；若逐則列數**少於** `total_comments`（P6 不變式被違反，或呼叫端傳了不完整的 `df_comments`），同樣標記 `suspect` 給 NULL——否則逐則重算會算出一個偏低的偽觀測值。真實庫實測：`suspect` 篇數 2（皆為 RISK-029 的時間回退案例）、落界則數 13（皆為 `article_id=1495`），本項守衛在真實庫目前無額外觸發案例。
11. **`df_comments=None` 拒絕本身需要可驗證**：`_aggregate_direct_comment_counts()` 內部對 `df_comments is None` 的 `raise` 原本沒有任何測試直接觸及（既有測試皆經由 `generate_daily_features()` 呼叫，後者自己的前置檢查先擋下 `None`）；已補上直接呼叫該函式本身的紅測，並以移除該 `raise` 的突變確認真的會被觸發（`CLAUDE.md` §9A.2）。

### Rationale（理由）

- 逐則時間戳是比「文章擷取完成時刻」更精確的判斷依據，不改變 DEC-024 原判準（決策時點可見性）本身，只改變判斷粒度。
- 與 `CLAUDE.md` §7.4（防止 Look-ahead Bias）一致。
- `comment_timeline.py` 模組與 `counts_as_of()` 函式已存在、已有既定行為與文件，只需要接線。

### Trade-offs（取捨）

- 特徵計算的讀取路徑變重：需要載入 `article_comments`（現有 136,185 列，持續成長）而非只讀已聚合的五欄。
- `suspect` 守衛只偵測「時間回退」，偵測不到「時間仍遞增但內容重複／交錯」的其他形態（根因見 RISK-029）。
- `market_articles` 的聚合欄位與 `article_comments` 逐則表並存，兩者語意不再完全對應，未來任何直接查詢 `market_articles.total_comments` 的用途需注意這個落差是預期行為。

### Affected Components（影響範圍）

- `src/loaders/db_writer.py`（`fetch_all_for_features()` 新增 `article_comments` 讀取，回傳值由 4-tuple 擴為 5-tuple）
- `src/transform/feature_aggregator.py`（`generate_daily_features()` 新增 `df_comments` 必要參數；`_aggregate_direct_comment_counts()` 改用逐則重算）
- `src/transform/comment_timeline.py`（新增 `is_time_reset()`；`counts_as_of()`／`validate_comment_bounds()` 由未使用狀態轉為生產路徑依賴）
- `src/ui/data_loader.py`（`_fetch_real_stock_features_from_db()` 傳入空 `df_comments`，維持該路徑既有的「留言特徵恆為 NULL」行為不變）
- `main_etl_pipeline.py`（`run_feature_engineering_pipeline()` 接住 5-tuple，傳遞 `df_comments`）
- `scripts/verify/risk023_p6_invariant_check.py`（新增）
- `scripts/verify/ug_g3_sb2a_stage2_baseline_comparison.py`（同步新增 `df_comments` 讀取，維持可重跑）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.5、§5A
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §3.3A
- `doc/upgrade/contracts/REMAINING_RISKS.md`（RISK-029 新增；RISK-023 列更新）

### Verification（驗證）

- [x] `tests/test_risk023_comment_recompute_red.py` 全部 15 項紅測轉綠（容器內，`Ran 812 tests ... OK`）
- [x] `tests/test_comment_features.py`／`tests/test_risk027_cross_market_calendar.py`／`tests/test_source_failed_nulls.py`／`tests/test_ml_feature_store_contract.py` 等既有測試同步更新，全數通過
- [x] 六項突變測試（`git diff` 可稽核，測試後已還原）：拿掉 `suspect` 守衛 → 對應測試 FAIL；拿掉 `validate_comment_bounds` → 對應測試 FAIL（首次示範發現測試本身設計不隔離，已訂正後重驗）；決策點改 per article → 對應測試 FAIL；已擷取旗標改回「有無逐則列」→ 對應測試 FAIL；拿掉 P6 一致性守衛 → 對應測試 FAIL；拿掉 `_aggregate_direct_comment_counts()` 內部 `df_comments is None` 的 `raise` → 對應測試 FAIL（原本無任何測試觸及，見 Decision 第 11 項）
- [x] `scripts/verify/risk023_p6_invariant_check.py` 對真實庫 exit 0；known-FAIL 於拋棄式容器示範（見腳本 docstring 的流程訂正記錄）
- [x] `scripts/verify/gate0_contract_check.py` 13/13 PASS
- [x] 對真實庫唯讀全量重算：留言三欄現行全 NULL → 新版至少一欄非 NULL 的組數 **352**、涉及股票數 **8**（診斷階段估計為 353/8，差 1 列，可歸因於本次新增的 `suspect` 守衛使原估計中 1 組被正確判為 NULL）；`suspect` 篇數 2、落界則數 13，其餘 22 欄零差異、無孤兒鍵
- [x] 真實庫寫入（2026-09-14，`postgres`@`localhost:5432`）：RISK-013 三步驟協議——PRE 備份（`stock_prediction_system2_PRE_risk023_comment_features_20260914_130807.dump`，拋棄式容器還原驗證：449,263 列、標籤 `(410443,38820)`、留言三欄全 0 非 NULL）→ 執行 `risk023_write_comment_features.py --write`（前置守衛全 PASS、RETURNING 352 鍵、讀回相等、commit 後全表 25 欄零差異、`stock_prices` 指紋不變）→ POST 備份（`stock_prediction_system2_POST_risk023_comment_features_20260914_130807.dump`）。寫入後真實庫現況：`comment_volume_ratio` 299、`comment_polarization` 352、`net_push_momentum` 201 個非 NULL 值；標籤與 `stock_prices` 未變。證據見 `doc/upgrade/gates/evidence/RISK023_comment_features_write.json`（352 列逐列舊值→新值，獨立以 PRE 備份唯讀還原比對真實庫重新推導，不沿用腳本自身記憶體結果）。

### Remaining Risks（剩餘風險）

- 排程本身（15:35 執行）不因本 ADR 改動。
- `suspect` 守衛的已知偵測邊界（見 Trade-offs）。
- 交叉引用：**RISK-029**（留言擷取器單次解析產生重複／交錯留言區塊，根因未定位，另案處理）。
- `scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py`（RISK-027 段 2 重跑腳本，已結案的歷史腳本）的 `compute_new_full_recompute()` 未同步更新以支援新的 `df_comments` 參數——該腳本工作已完成、不預期重跑，僅記錄此已知限制。
- **全歷史重算使晚到的映射與資料回溯套用，見 RISK-032**（2026-09-17，首次每日 ETL 段 B 拋棄式庫演練發現：`theme_stock_mapping` 映射從寫入到第一次被 `FeatureAggregator` 套用之間若間隔多次執行未觸發特徵重算，會在某次執行中一次性把相關股票的全部歷史情緒特徵改寫）——本決策的逐則重算機制本身不變，此為同一類「全歷史面板重算」設計特性在題材溢出情境下的表現，非本決策的缺陷。

### 連結

RISK-023、RISK-029、DEC-024（superseded by 本決策）、DEC-025

### 證據文件

`doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md`；`doc/upgrade/contracts/REMAINING_RISKS.md`（RISK-023／RISK-029）；`tests/test_risk023_comment_recompute_red.py`；`scripts/verify/risk023_p6_invariant_check.py`
`doc/upgrade/gates/UG_G3_SB3_GATE_B_SUBMISSION.md` §2.4／§8

---

## DEC-040：Gate 3 Holdout 邊界落地（折 33～42，起日 2025-10-23）

- 日期：2026-09-15
- 狀態：APPROVED（隨 `UG-G3-SB4` Gate B 核准結案 — 由 Project Owner 核准）
- Approved by: Project Owner
- 核准日期：2026-09-15
- 觸發：`UG-G3-SB4`（`doc/upgrade/gates/UG_G3_SB4_GATE_A_PROPOSAL.md` `be64f9b` §4.4，PO 2026-09-14 核准設計、要求本 ADR 隨實作 commit 一併登記）

### Context（背景）

`PURGED_WALK_FORWARD_SPEC.md` §3.3 與 `SYSTEM_UPGRADE_MASTER_PLAN.md` §9／§11.3 已核准 Gate 3 的 Holdout 規格：最近 6～12 個月資料保留為 Holdout，全程不得用於模型選擇、門檻選擇，僅供 `UG-G3-SB7` 做最終績效宣稱，且「不得使用相同 Folds 同時進行模型選擇、門檻選擇與最終績效宣稱」。`UG-G3-SB1`～`SB3` 的 43 折 Purged Walk-Forward 切分從未實際切出這段 Holdout——規格存在，但邊界從未落地成具體的折序號與日期。

### Problem（問題）

若不把 Holdout 邊界固定為一組具名常數並跨 SB 引用，`UG-G3-SB4`～`SB7` 各自可能用不同的切法定義「最近 6～12 個月」，導致：(a) 不同 SB 對同一批資料有不同認定；(b) 無法驗證「SB4～SB6 是否真的沒有碰過 Holdout」；(c) `UG-G3-SB7` 的最終 Benchmark 失去唯一、可稽核的 Holdout 定義。

### Alternatives Considered（考慮方案）

1. **各 SB 各自在自己的凍結面板上重新計算「最近 6～12 個月」（不採納）**：面板每次凍結時間不同，會導致 Holdout 邊界漂移，且無法保證後續 SB 引用同一條線。
2. **用日曆日期區間定義（例如「2025-10 月起」）而非折序號（不採納）**：折序號才是 Purged Walk-Forward 實際運作的單位，日曆區間需要額外換算，容易與凍結面板的實際折切分產生落差。
3. **以 `UG-G3-SB4` 對凍結面板實測的折邊界為準，固定成具名常數，跨 SB 引用（採納，見 Decision）**。

### Decision（決策）

1. **Holdout = 折 33～42（共 10 折）**，測試窗跨度 2025-10-23～2026-08-20（約 10 個月，落在規格「6～12 個月」區間內）。邊界以 `trade_date >= HOLDOUT_START_DATE`（`2025-10-23`，含端點本身）表達，**涵蓋 10 折本身，加上凍結面板尾端（折 42 之後、2026-08-21～2026-09-04）的 1,650 列缺口**——不是只擋 10 折本身。
2. 邊界依據的凍結面板為 `UG-G3-SB3` 已凍結、經 sha256 驗證的兩個 target 面板（`panel_target_up_down.parquet` sha256 `39dc6b8e6160add20f39a7265bad04de50c76199fa7ab81b979a7aabeabbd014`；`panel_target_triple_barrier.parquet` sha256 `4c4657c4e7e36b227fef01d2f6f667b8e613b23587db40f2907d024db9b3f729`，見 `UG_G3_SB3_panel_export.json`），以 `train_window_size=60, test_window_size=20, mode=rolling, label_horizon=1, embargo_days=0, require_label_end_date=True` 呼叫 `WalkForwardSplitter.split()` 實測得出 43 折、全數 `purge_mode=exact`。
3. **`UG-G3-SB4`～`UG-G3-SB6` 全程不得讀取、訓練、評估、選擇**落在此邊界之後（或恰好等於邊界起日）的任何資料列——四個動詞涵蓋模型 `fit`／特徵讀取／指標評估／門檻或模型選擇，任一皆不得觸碰。
4. **`UG-G3-SB7` 是唯一消費者**，用於最終 Benchmark 績效宣稱，且該次宣稱不得回頭用於調整 `SB4`～`SB6` 的任何設計決定。
5. `HOLDOUT_START_DATE`（`2025-10-23`）與 `META_EVAL_START_DATE`（`2025-05-02`，折 27 測試窗起點，`UG-G3-SB4` 內部 Meta-Train／Meta-Eval 巢狀切分邊界）皆定義於 `src/ml/stacking.py` 模組層級常數，供後續 SB 直接引用，不得各自重算。

### Rationale（理由）

- 折序號與具體日期一次性從真實面板量出來，比每個 SB 各自「大約算一下最近幾個月」更精確、更可稽核。
- 集中定義為模組常數，任何 SB 需要引用時直接 import，不會產生多份不一致的定義。
- 10 折的測試窗跨度（約 10 個月）落在規格要求的 6～12 個月區間內，不需要額外裁量。

### Trade-offs（取捨）

- 邊界一旦登記即不可回頭調整（見 `UG_G3_SB4_GATE_A_PROPOSAL.md` §7 風險揭露）——若日後發現這個邊界選得不好（例如 Holdout 段剛好落在資料品質不佳的期間），調整代價是重開多個已結案的 SB。
- 邊界依賴 `UG-G3-SB3` 的凍結面板本身不再更新（面板凍結於每日 ETL 首跑之前）——若面板重新凍結（例如每日 ETL 首跑後產生新資料），本 ADR 定義的折序號與日期需要重新核對是否仍然成立，不會自動延伸。

### Affected Components（影響範圍）

- `src/ml/stacking.py`（`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 常數定義、`iter_oof_folds()` 邊界過濾邏輯）
- `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §3.3（規格來源，未修改，僅引用）
- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §9／§11.3（規格來源，未修改，僅引用）

> **2026-09-16 forward-fix（`UG-G3-SB7` 結案）**：本段原引用「§10／§11.3」，經查證 §10 實際章節為「UG-Gate-4: XAI, Export & UI Enhancement」，與 Holdout 定義無關，正確引用為 §9（Gate 3 各 SB Brief，`UG-G3-SB7` Brief「資料期間」欄明寫 Holdout 規格）／§11.3（Measurement Template）。依 `CLAUDE.md` §11A 不 amend 既有內容形成的決策本身，僅訂正引用章節號，不影響本 ADR 的決策與理由。

### Verification（驗證）

- [x] `WalkForwardSplitter` 對兩個 target 凍結面板實測 43 折、全數 `purge_mode=exact`，折邊界逐日核對（`UG_G3_SB4_GATE_A_PROPOSAL.md` §2.5，PM／審查方獨立互核相符）
- [x] `tests/test_ug_g3_sb4_stacking_red.py::ConstantsPinnedTests` 釘住 `HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 常數值（容器內 `Ran 41 tests ... OK`）
- [x] `tests/test_ug_g3_sb4_stacking_red.py::HoldoutFoldsNeverIteratedTests` 含跨界整折排除測試（含半折洩漏 known-FAIL：`test_straddling_fold_is_excluded_entirely`，實測邊界精確落在某折測試窗中點，確認整折被丟棄而非切半折）
- [x] `UG-G3-SB4` 全量執行（folds 0-32）對兩個 target 的 OOF parquet 皆確認零 Holdout 列（`reject_rows_at_or_after()` 二次確認），`VERIFIED THIS SESSION`（2026-09-15，證據 `doc/upgrade/gates/evidence/UG_G3_SB4_oof_generation_target_up_down.json`／`_target_triple_barrier.json`）
- [ ] NOT VERIFIED → 去處：真實庫首次每日 ETL 執行後，凍結面板若重新產生，須重新核對折 33／42 邊界日期是否仍為 2025-10-23／2026-08-20，去處待 `UG-G3-SB7` 開工前確認（SB7 已於 2026-09-16 完成確認，面板 sha 未變，見 `closed/UG_G3_SB7_GATE_A_PROPOSAL.md` §2.1；本項待辦本身仍未發生，因首次每日 ETL 截至本次尚未執行）

### Remaining Risks（剩餘風險）

- 交叉引用 `UG_G3_SB4_GATE_A_PROPOSAL.md` §7：Holdout 段（含情緒訊號 630 個非 NULL 值，`sentiment_mean` 落於此段）的訊號分布特性是否適合 `UG-G3-SB7` 的最終 Benchmark，本 ADR 登記時尚未評估，留待 `UG-G3-SB7` 開工前檢視。

### 連結

`UG-G3-SB4`、`UG-G3-SB3`（面板凍結來源）、`PURGED_WALK_FORWARD_SPEC.md` §3.3

### 證據文件

`doc/upgrade/gates/UG_G3_SB4_GATE_A_PROPOSAL.md` §2.5／§4.4；`doc/upgrade/gates/evidence/UG_G3_SB3_panel_export.json`

---

## DEC-041：Gate 3 後續主線改以 `target_triple_barrier`／Timeout 為對象

- 日期：2026-09-15
- 狀態：APPROVED（`UG-G3-SB6` Gate B 核准，approved by: Project Owner，核准日期 2026-09-16）
- 觸發：`UG-G3-SB5`（`doc/upgrade/gates/closed/UG_G3_SB5_GATE_B_SUBMISSION.md` §2／§5，`RISK-030`）

### Context（背景）

`UG-G3-SB5` 段級報告腳本對 `UG-G3-SB4` 已核准的 OOF 資料做校準品質分析時，實測發現：`target_up_down` 在折 27-32（Meta-Train／Meta-Eval 可用範圍）**全線無可偵測的 OOF 排序訊號**——四個 Specialist（`lr`／`rf`／`lgbm`／`xgb`）的 OOF `p1` AUC 在 Meta-Train 段（27 折全量）僅 0.515～0.526，`Calib-fit`（折 27-29）／`Calib-eval`（折 30-32）更低至 0.492～0.510；Meta(A)（`LogisticRegression`／`RidgeClassifier`）的 `decision_function` 在 `Calib-fit` 的 AUC 同樣 ≈0.496，`calibration_not_meaningful=true` 標記於全部四個校準條目。相對地，`target_triple_barrier` 的 Timeout 類（class 0）OvR AUC 達 0.82～0.91（Meta-Train／Calib-fit／Calib-eval 三段皆然），`±1` 方向類則與 up_down 同量級的近零訊號（0.50～0.55）。完整數字見 `UG_G3_SB5_GATE_B_SUBMISSION.md` §2.1／§2.2，登記於 `REMAINING_RISKS.md` `RISK-030`（`OBSERVED`，High）。

### Problem（問題）

Gate 3 原規劃（`SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1 條件勝率 >60% 目標）以 `target_up_down`（價格方向）為隱含主線，`UG-G3-SB6`（選擇性推論／信心門檻）若照原規劃對 `target_up_down` 的機率做門檻選擇與 regime gating，選出來的門檻本質上是在對一個沒有排序訊號的機率做雜訊擬合——不會產生任何實質可用的產品行為，且會讓後續 `UG-G3-SB7` 的 Benchmark 對 up_down 的績效宣稱建立在一個已知無效的基礎上。

### Alternatives Considered（考慮方案）

1. **維持原規劃，`UG-G3-SB6` 仍對 `target_up_down` 做門檻選擇（不採納）**——`RISK-030` 已證明 up_down 的 Meta(A) 與四個 Specialist 皆無排序訊號，門檻選擇的輸入本身是雜訊，產出的門檻不具備解讀價值，卻會製造「已完成方向預測校準」的錯覺。
2. **暫停整個 Gate 3，等特徵層面問題解決後再繼續（不採納）**——`target_triple_barrier` 的 Timeout 類已有實質可用訊號（AUC 0.82～0.91），沒有理由讓整個 Gate 3 停擺；特徵層面的方向預測改進是獨立、耗時較長的問題，不應阻塞已經有訊號可用的部分。
3. **`UG-G3-SB6` 改以 `target_triple_barrier`／Timeout 類為 gating 對象，`target_up_down` 停做，方向預測特徵改進另案候補（採納）**——把已驗證有訊號的部分（Timeout／「何時波動偏低」）與已驗證無訊號的部分（方向）分開處理，前者立即可用，後者列候補案，不阻塞 Gate 3 進度。

### Decision（決策）

1. **`UG-G3-SB6` 對 `target_up_down` 停做**——Gate A 提案須明寫引用 `RISK-030` 排除 `target_up_down`，不跑訓練迴圈、不產出任何門檻或報告；未來若方向訊號有進展（例如決策 3 的候補案有結果），可重新開放，屆時需另一輪 Gate A。
2. **`UG-G3-SB6` 改以 `target_triple_barrier`／Timeout 類的校準後機率為 gating 對象**，產品形態定位為「何時不交易」（規避低把握時段），而非「往哪個方向交易」；`±1` 方向類機率僅揭露、不設門檻。Gate A 必答：gating 評估指標定義（被排除時段的實際 Timeout 率、保留時段的方向勝率變化）、門檻在 `Calib-eval`（折 30-32）段選定（不得使用 Holdout）、與 `DEC-040` 的 Holdout 隔離規則一致。
3. **特徵層面的方向預測改進案登記為候補**，排在 `UG-G3-SB7` 結案後；與 `RISK-015`（情緒特徵覆蓋率不足，0.49%）連動，候選方向包含情緒覆蓋率擴充、新特徵來源、或重新檢視標籤定義。登記於 `PROJECT_STATUS.md` §0.5 與 `RISK-030` 去處欄。
4. **`SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1「條件勝率 >60%」目標數字保留不改**，追加狀態註記：「`target_up_down` 於現行特徵集下未達成本目標的判別力前提（見 `RISK-030`）」；另訂 Timeout gating 的量化目標，具體數字由 `UG-G3-SB6` Gate A 提案訂定。

### Rationale（理由）

Timeout 類的訊號強度（AUC 0.82～0.91）與方向類（0.50～0.55）之間的落差達 30 個百分點以上，不是量測雜訊可以解釋的量級——把已驗證有效的部分立即投入使用，同時誠實記錄無效的部分並列候補案，比「兩者一起等」或「假裝方向預測有效繼續往下做」更符合證據導向的工程紀律。

### Trade-offs（取捨）

- Gate 3 的產品形態從「預測方向」窄化為「何時不交易」，這是比原規劃更保守的產品承諾，需要向下游（Gate 4／實際使用者）明確溝通這個範圍調整。
- `target_up_down` 停做代表已投入的 `UG-G3-SB4`／`UG-G3-SB5` 對該 target 的所有工作（OOF、Meta-Learner、校準）在短期內不會被下游消費——但這些工作本身仍是有效的唯讀分析與方法驗證（校準管線、鏡射容忍判準等技術資產可直接複用於 TB），不是浪費。
- 特徵層面候補案的時程（`UG-G3-SB7` 結案後）代表方向預測的改進至少要等到 Gate 3 全部結束才會被排入，若特徵改進的效益其實很快就能驗證，這個時程可能過於保守——但提前插隊會打亂已核准的 Gate 3 SB 順序，取捨由 PO 承擔。

### Affected Components（影響範圍）

- `UG-G3-SB6`（尚未開始）：Gate A 範圍需依本決策調整（`target_triple_barrier`／Timeout 為 gating 對象，`target_up_down` 排除）。
- `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 `UG-G3-SB6` Brief：範圍依本決策調整，於 `UG-G3-SB6` Gate A 定案。
- `SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1：條件勝率目標加狀態註記。
- `doc/upgrade/contracts/REMAINING_RISKS.md`：`RISK-030` 應對措施欄回填本決策內容。

### Verification（驗證）

- [x] `RISK-030` 三段 AUC 表為 `UG-G3-SB5` 段級報告腳本實測結果，`VERIFIED THIS SESSION`（2026-09-15，PO／審查方獨立重算，PM 獨立重現，見 `UG_G3_SB5_calibration_report_target_up_down.json`／`_target_triple_barrier.json`）。
- [x] 決策 2 的 gating 評估指標已具體定義並實測驗證（`UG-G3-SB6` Gate B 核准，2026-09-16，`VERIFIED THIS SESSION`）：`θ*=0.06907452098250194` 於 Calib-eval 段達成覆蓋率 80.00%／精準度提升 4.15×／召回 83.03%（裁決 (a) 三項判準），`regime_diagnostic` 顯示被 gate 的列全部落在低波動三分位組。見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md`、`doc/upgrade/gates/evidence/UG_G3_SB6_gating_report.json`。
- [ ] NOT VERIFIED → 去處：決策 3 的特徵層面候補案本身尚未開始，效益未知，觸發條件已於 2026-09-16 成立（`UG-G3-SB7` 已結案），PO 裁決併入 `UG-Gate-4` 啟動申請書一併評估，不現在單獨開案。
- [x] `θ*` 在 Holdout（折 33-42）的樣本外穩定性與波動率單變數基線的比較已於 `UG-G3-SB7` 完成（2026-09-16，`VERIFIED THIS SESSION`）：三項判準（覆蓋率≥0.80／精準度提升≥4×／召回≥0.60）於 Holdout 成立；波動率單變數基線與 Timeout gating 表現接近，未下結論，登記候補案（`PROJECT_STATUS.md` §0.5）。見 `doc/upgrade/gates/closed/UG_G3_SB7_GATE_B_SUBMISSION.md`、`doc/upgrade/gates/evidence/UG_G3_SB7_holdout_report.json`。

### Remaining Risks（剩餘風險）

- 交叉引用 `RISK-030`（本決策的依據）、`RISK-015`（決策 3 候補案的連動風險）、`RISK-009`（OOF Stacking 過擬合／欠擬合，與 `RISK-030` 性質不同但數字互為背景，見 `REMAINING_RISKS.md` `RISK-009` 交叉引用）。
- `UG-G3-SB6` 改以 Timeout 為 gating 對象後，若 Timeout 類的訊號強度在 Holdout（折 33-42，`UG-G3-SB7`）不如 Meta-Train／Meta-Eval 段穩健，本決策的前提需要重新評估——`DEC-040` 的 Holdout 隔離規則使這個驗證只能在 `UG-G3-SB7` 才能進行，屬已知的延遲驗證缺口。

### 連結

`UG-G3-SB5`、`UG-G3-SB6`（後續）、`RISK-030`、`RISK-015`、`RISK-009`、`DEC-040`（Holdout 邊界，本決策的門檻選定規則依此延續）

### 證據文件

`doc/upgrade/gates/closed/UG_G3_SB5_GATE_B_SUBMISSION.md` §2／§5；`doc/upgrade/gates/evidence/UG_G3_SB5_calibration_report_target_up_down.json`／`_target_triple_barrier.json`

---

## DEC-042：§0.5 #32 成因 F 失敗鍵推導規則（PTT 覆蓋缺口＋NLP 未完成 → `SOURCE_FAILED`）

- 日期：2026-09-18
- 狀態：APPROVED（Approved by: Project Owner，2026-09-21，隨 §0.5 #40 GOV
  摘要案 commit 一併補上戳記；`FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`
  核准、紅綠兩輪（`431c2be`／`ee0b384`／`9079915`）與真實庫首次生效
  （`…real_run_20260918_success.md`）皆已通過 PO 複核）
- 觸發 Gate：`PROJECT_STATUS.md` §0.5 #32（PO 2026-09-17 裁決，首次每日 ETL 真實
  首跑中止複核追加）

### Context（背景）

`FeatureAggregator.generate_daily_features()` 已支援 `failed_source_keys` 參數，
但生產呼叫點 `main_etl_pipeline.py` 從未傳入，PTT 來源失敗與 NLP 未完成兩種「沒
觀測到」的情形，特徵表一律寫成 `SUCCESS_EMPTY`（「那天真的沒人討論」），把「沒
查到」與「查了、真的沒有」混為同一個值。

### Problem（問題）

`daily_ml_features` 每次執行都全歷史重算，`source_status` 在同一次 `UPSERT` 內
決定，若失敗鍵只用本次執行記憶體裡的 outcome 計算，先前標記的 `SOURCE_FAILED`
會在下次執行（只要那次本身沒失敗）被洗回 `SUCCESS_EMPTY`，需要一個每次都從
資料庫狀態重新推導的規則。

### Alternatives Considered（考慮方案）

1. **失敗鍵用本次執行記憶體 outcome 計算（不採納）**：如上，會被下次重算洗掉。
2. **覆蓋算術寫在 SQL 裡，`DBWriter` 只回傳查詢結果（不採納為唯一實作）**：
   單元測試 mock 掉 `db_writer` 後測不到真正的覆蓋邏輯，只是測 mock 回傳值本身。
3. **覆蓋算術與 NLP 歸日邏輯在 Python 實作，SQL 只作段 B 演練的獨立對照（採納）**：
   兩個獨立實作（Python 迴圈、SQL 查詢）對同一批真實資料算出同一個答案，才是
   一個能 FAIL 的檢查；單元測試也才測得到真正的邏輯。

### Decision（決策）

1. **PTT 覆蓋缺口**：關鍵字 k 在交易日 D 有覆蓋，若存在 `etl_run_log` 列
   `source='ptt'`、`item_key=k`、`outcome IN ('OK','NO_DATA')`、
   `batch_key ∈ [D, D+2]`（看板抓取 `BOARD_LOOKBACK_DAYS=2`，一次成功批次涵蓋
   貼文日 `[B-2, B]`，故「D 被涵蓋」等價於存在 `B ∈ [D, D+2]` 的成功批次）。
2. **「沒跑」與「跑了但失敗」同一格**：兩者皆為「沒有 `OK`／`NO_DATA` 的
   batch_key 落在 `[D, D+2]`」，結果都是未覆蓋 → `SOURCE_FAILED`。
3. **起算點**：`MIN(batch_key) WHERE source='ptt'`（PO 裁定）——理由：只有 PTT
   自己的紀錄能代表 PTT 的觀測起點；`batch_key` 是台北日期字串，`started_at` 是
   UTC，`::date` 轉換會在台北 08:00 前跨日錯一天；覆蓋算術本來就是用 `batch_key`
   算的，起算點用同一個欄位才語意一致。起算點之前的交易日不套用本定義，維持
   `SUCCESS_EMPTY` 現狀。
4. **資格過濾（§3.2a，PO 裁定選 A）**：覆蓋判斷只對「至少一個映射關鍵字曾出現
   在 PTT run log」的股票做；從未被抓過任何關鍵字的股票本案不動，維持現狀——
   理由：把全部從未觀測過的股票都改標 NULL，等於重新定義 `RISK-015` 的覆蓋率
   語意，牽動 Gate 4 資料源擴充範圍，不是接線案該片面決定的事。
5. **多關鍵字任一覆蓋即算覆蓋（PO 裁定）**：一檔股票映射多個關鍵字時，任一有
   覆蓋即算覆蓋——理由：關鍵字由 AI 探索持續新增，新關鍵字在它出現之前沒有
   log，若要求全部關鍵字都覆蓋，每次探索新增題材就會把成分股的歷史全部翻成
   未覆蓋。
6. **NLP 未完成**：`market_articles.sentiment_score IS NULL` 的文章，經
   `entity_mapping`／`theme_stock_mapping` 對到的股票，依既有、已測試的
   `map_timestamp_to_trading_day()`（不重寫歸日邏輯，`CLAUDE.md` §7.1）歸日後
   即成立。**不套用 4 的資格過濾**——判斷依據是「文章確實存在但未評分」，與
   PTT 有沒有抓過這個關鍵字無關。文章時間超出該股交易日曆時
   `map_timestamp_to_trading_day()` 回 `None`，此時不得寫入任何鍵（審查方複核
   追加的 known-FAIL，見 `9079915`）。
7. **推導邏輯全部在 Python 實作**：`DBWriter.fetch_failed_source_keys()` 的 SQL
   只負責撈五張表的原始列（`etl_run_log`／`entity_mapping`／
   `theme_stock_mapping`／`stock_prices`／`market_articles`），起算點過濾、覆蓋
   視窗、資格判斷、任一關鍵字覆蓋、NLP 歸日全部在 Python 算。
8. **呼叫時機**：`fetch_failed_source_keys()` 排在 NLP 階段（`run_nlp_sentiment_
   pipeline()`）之後、`generate_daily_features()` 之前。
9. **查詢例外不得吞**：沿用 `DBWriter` 既有 `try/finally` 無 `except` 的慣例，
   資料庫錯誤必須傳播，不得回傳空集合讓特徵階段誤判「今天沒有失敗」。

### Rationale（理由）

- 每次從資料庫狀態重新推導，是唯一能讓 `SOURCE_FAILED` 標記在全歷史重算下持續
  正確的做法。
- 覆蓋算術與 NLP 歸日邏輯統一「SQL 撈料、Python 算」風格，讓單元測試測得到真正
  的邏輯，也讓 PTT／NLP 兩個獨立來源共用同一套設計語言。
- §3.2a 的資格過濾與多關鍵字任一覆蓋語意，都是為了不讓本案片面擴大或緊縮
  `RISK-015` 既有的覆蓋率語意邊界。

### Trade-offs（取捨）

- 資格過濾（4）意味著「從未被抓過任何關鍵字」的股票即使實際上完全沒有社群資料
  可信度，也不會被標記——這個邊界刻意留給 Gate 4 決定，不是本案的缺陷，但讀者
  需要知道這個邊界存在。
- Python 端的覆蓋算術需要載入 `etl_run_log`／兩張映射表／`stock_prices` 的完整
  列（非只查聚合結果），讀取路徑比純 SQL 聚合更重，但换來單元測試的真實覆蓋。

### Affected Components（影響範圍）

- `src/loaders/db_writer.py`（新增 `fetch_failed_source_keys()`）
- `main_etl_pipeline.py`（`run_feature_engineering_pipeline()` 接線）
- `tests/test_first_daily_etl_cause_f_wiring.py`（新檔，11 條測試）
- `tests/test_source_failed_nulls.py`（既有聚合器層測試，行為未變，本案驗證與
  之一致）

### Verification（驗證）

- [x] 11 條紅測對現行未修正程式碼全數 FAIL/ERROR（`431c2be`）
- [x] GREEN 實作後 11 條測試第一次執行即全數 PASS，既有全套測試 1105 條無回歸
  （`ee0b384`）
- [x] 9 個方法層級記憶體內突變 (i)(ii-narrow)(ii-wide)(ii-future)(iii)(iv)(vi)
  (vii)(viii) 全數被對應測試抓到；呼叫時機突變 (v) 另用暫時搬動程式碼的方式驗證，
  確認 FAIL 後即時還原，`git diff --stat` 確認零殘留
- [x] 審查方複核追加子案例（超出交易日曆的 NLP 文章不得崩潰）：known-FAIL 驗證
  `AttributeError: 'NoneType' object has no attribute 'isoformat'`，還原後零殘留
  （`9079915`）
- [x] 段 B 拋棄式庫演練：Python `fetch_failed_source_keys()`、Gate A 提案 SQL、
  實際 before/after 翻轉三方集合逐列相等（47 列）；強制 PTT 整日失敗的真實執行
  驗證同一集合；合成種子列驗證「當日」效果成立（`…rehearsal_20260918.md`）
- [x] 段 C 真實庫首次生效：五條驗收全數 PASS，含新增列數精確吻合（8=8）、
  `SOURCE_FAILED` 翻轉列集合與執行前 expectations 逐列相等（47=47）
  （`…real_run_20260918_success.md`）

### Remaining Risks（剩餘風險）

- 交叉引用 `RISK-015`（覆蓋率量測邊界，本案的資格過濾與其連動）、`RISK-032`
  （題材／關鍵字映射非 point-in-time——本案首次真實執行時，2382 案例證實這個
  風險還有一個子機制：AI 探索重寫既有映射的 `relevance_weight` 也會觸發全歷史
  欄位改變，不只是新增映射，見 `REMAINING_RISKS.md` RISK-032 補充段落）。
- `PROJECT_STATUS.md` §0.5 新增兩條候補：AI 探索重寫既有映射權重的影響範圍是否
  需要限制（與 #31 探索改每週一次同案處理）；35 篇未來日期文章的 `post_time`
  年份回修（獨立小案）。

### 連結

`RISK-015`、`RISK-032`、`PROJECT_STATUS.md` §0.5 #31／#32、
`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`（§0.5 #30，本案依賴的 n_lag
機制）

### 證據文件

`doc/upgrade/gates/closed/FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`；
`doc/upgrade/gates/evidence/FIRST_DAILY_ETL_CAUSE_F_WIRING_expectations.json`；
`doc/upgrade/gates/evidence/FIRST_DAILY_ETL_CAUSE_F_WIRING_rehearsal_20260918.md`；
`doc/upgrade/gates/evidence/FIRST_DAILY_ETL_CAUSE_F_WIRING_real_run_20260918_success.md`

---

## DEC-043：§0.5 #31＋#33 Gemini 用量紀律（探索頻率／每日配額分類／既有映射凍結）

- 日期：2026-09-19
- 狀態：APPROVED（Approved by: Project Owner，2026-09-19，「#31＋#33 真實執行複核：
  七條驗收 PASS（條件 6 裁決 PASS，措辭訂正）；一個 PM 沒看到的發現要登記；授權
  結案 commit」訊息中直接核准戳記——PO 明確指示跳過 `PROPOSED` 中繼態，理由是
  紅綠、段 B、段 C 皆已個別通過複核，避免為同一內容再走一輪）
- 觸發 Gate：`PROJECT_STATUS.md` §0.5 #31（Gemini 用量縮減）＋ #33（AI 探索不改
  既有映射權重）合案（PO 2026-09-18 開案，理由：兩案都改 `run_all_daily_tasks()`
  的 AI 探索段與 `upsert_theme_stock_mapping()`，分開做會對同一段程式改兩次）

### Context（背景）

09-17 首次真實每日 ETL 因 Gemini 每日配額耗盡中止（RISK-031）：`trend_discover.
py`／`nlp_processor.py` 兩處硬寫 `gemini-flash-latest`；探索每次執行無條件呼叫；
`_is_transient_exception` 把「每日配額耗盡」與「每分鐘限速」用同一組關鍵字判斷，
前者重試 5 次（2+4+8+16+16=46 秒）毫無意義才放棄；`run_nlp_sentiment_pipeline()`
完全沒有 try/except，例外直接穿透中止整個 `run_all_daily_tasks()`；
`upsert_theme_stock_mapping()` 的 `ON CONFLICT DO UPDATE` 會覆寫既有映射的
`relevance_weight`，09-18 真實執行時證實這會觸發 `FeatureAggregator` 的題材溢出
全歷史重算機制（DEC-039），回溯改寫既有股票 13 天的 `bullishness_index`。

### Problem（問題）

不縮減用量，Gemini 免費層每日 20 次請求的額度會在探索＋NLP 混合消耗下持續
不穩定觸頂；探索每次都可能改寫既有映射權重，讓 DEC-039 的全歷史重算機制被
一個「LLM 每次重新發現同一題材就順手改一次權重」的非人為決策觸發，而權重是
特徵值的一部分。

### Alternatives Considered（考慮方案）

1. **維持探索每日執行、只加重試上限（不採納）**：治標不治本，配額耗盡的根因是
   請求頻率，不是重試策略。
2. **每日配額耗盡與每分鐘限速共用同一套重試判斷（不採納）**：09-17 中止的直接
   成因；兩者處置相反（前者要停止對該服務施壓等隔天，後者可退避重試），詞彙
   不分就無法分別處置（同 `REFUSED`／`FETCH_FAILED` 分離的既有先例，DEC-032）。
3. **探索每週一次、每日配額耗盡不重試、既有映射權重凍結、`run_discovery()` 改
   回傳四態元組（採納）**：見 Decision。

### Decision（決策）

1. **探索頻率改每週一次**：新增 `DBWriter.fetch_last_discovery_probed_date()`，
   查最近一列 `source='ai_discovery' item_key='discovery' outcome IN ('OK',
   'NO_DATA')` 的 `batch_key`，距今未達 `DISCOVERY_INTERVAL_DAYS`（7）天則跳過。
   `NO_DATA` 代表探索確實發出過請求、內容為空，一樣算「問過」；`FETCH_FAILED`／
   `REFUSED` 不算，隔天即可再試，恰好對上配額隔天重置的週期。
   `run_all_daily_tasks()` 新增 `run_discovery: bool = True` 參數，供未來
   08:30 雙時點觸發案傳入 `False`。
2. **規則性跳過不寫任何 `etl_run_log` 列**（決策點 A，PO 裁決「A4」，v1 提出的
   「跳過寫 `NO_DATA`／`detail`」三案皆已否決）：`etl_run_log` 記的是「發出去的
   請求得到什麼」，依規則不發出的請求不是一筆觀測，沒有 outcome 可記——把跳過
   記成 `NO_DATA` 等於把「沒問」寫成「問了沒東西」，是 DEC-042 剛清除過的
   `SUCCESS_EMPTY`／`SOURCE_FAILED` 同型混淆的鏡像版本。
3. **每日配額耗盡不重試，`outcome=REFUSED`**：`nlp_processor.py` 新增
   `GeminiDailyQuotaExhausted` 例外與 `is_daily_quota_exhausted()`（判斷字串是否
   含 `PerDay`，必須排在一般 `quota` 關鍵字判斷**之前**——配額訊息同時含兩者，
   順序反過來這個分支永遠執行不到）。撞到即不重試、直接拋出。`REFUSED` 而非
   `FETCH_FAILED`：配額耗盡是「服務主動叫停」，不是我方抓取失敗（沿用
   `REFUSED`／`FETCH_FAILED` 分離的既有語意，DEC-032／migration 007）。
4. **`trend_discover.run_discovery()` 改回傳 `(outcome, detail)` 四態元組**，
   例外（含每日配額）不跨越函式邊界：複核第二輪發現原本有五種情況會靜默
   `return`（隱式 `None`）——缺 API key、PTT 掃頁失敗、熱門標題為空、Gemini
   回應無效、Gemini 回應有效但無新詞——呼叫端「呼叫回來就記 OK」的設計會把
   其中三種失敗全部誤記成成功。四態對照：`OK`（正常寫入）；`NO_DATA`（熱門標題
   為空；回應有效但無新詞）；`FETCH_FAILED`（缺 API key；掃頁出錯；回應無效或
   萃取失敗）；`REFUSED`（每日配額耗盡）。`run_nlp_sentiment_pipeline()` 新增
   `run_log_writer`／`started_at`／`batch_key` 三個延遲驗證參數（皆預設
   `None`，只在真正撞到配額耗盡時才驗證是否齊備，缺任一項拋 `ValueError`——
   既有測試檔呼叫端不必先改，但生產路徑一旦真的撞到配額卻缺這些參數，必須
   拋錯而非靜默不落地）。
5. **`upsert_theme_stock_mapping()` 改 `ON CONFLICT (theme_keyword, stock_id)
   DO NOTHING`**：既有映射的 `relevance_weight`／`stock_name`／`updated_at`
   不再被探索結果覆寫，只有全新配對會被插入。權重是特徵值的一部分，改權重
   必須是有人決定的事，不是 LLM 每次重新發現同一題材就順手做的事。

模型名常數化（`src/config.py::GEMINI_MODEL_NAME = "gemini-3.8-flash"`，取代
兩處硬寫的 `gemini-flash-latest`，值取自 09-17 真實 log 解析結果）屬實作細節，
記於 Trade-offs，不列為獨立決策條目。

### Rationale（理由）

- 探索頻率、跳過不記錄、配額分類三條決策互相依賴同一組語意：`etl_run_log` 只
  記錄真實發出的請求與其結果，「要不要問」與「問了發生什麼」是兩個分開的問題，
  混在一起會讓 run log 的「有沒有問過」判準失去意義。
- 四態回傳設計直接由 09-19 真實執行驗證其必要性：探索撞到 `DeadlineExceeded`
  （504 逾時，非配額問題），若是舊碼會被既有 `except Exception` 生吞，`main_
  etl_pipeline.py` 呼叫端解包 `None` 極可能直接 `TypeError` 中止整個每日任務；
  新碼下正確分類為 `FETCH_FAILED`、正確落地、流程繼續完成全部後續階段（見
  `…real_run_20260919_success.md` §四.6、§零.0.2）。
- 映射凍結（`DO NOTHING`）的必要性同樣由真實執行驗證：09-18 執行時既有映射
  被改權重觸發 DEC-039 全歷史重算（13 天 `bullishness_index` 回溯改寫）；
  09-19 執行後 `theme_stock_mapping` 66 列（含 `updated_at`）與執行前完全相等，
  全歷史重算機制「這次沒有東西可重算」。

### Trade-offs（取捨）

- 探索每週一次意味著新題材最多延遲 6 天才被納入追蹤，這是用量與時效的刻意
  取捨，不是缺陷。
- `run_discovery()` 五個分支改寫後，凡是測試把 `trend_discover` 設成未配置
  `return_value` 的裸 `MagicMock()` 並呼叫 `run_all_daily_tasks()`，解包
  `(outcome, detail)` 就會 `TypeError`——波及 8 個既有測試檔（`test_batch_etl_
  boundary.py` 等）與 2 個用 module-stub 隔離技術的測試檔（`test_db_read_
  semantics.py`／`test_nlp_checkpoint_semantics.py`），僅補 mock 預設值／stub
  屬性，未改動任何既有斷言（同 §0.5 #30 `fetch_feature_lag()` 的先例）。
- 模型名常數化把兩處硬寫的 `'latest'` alias 改成釘死版本號，換取「哪一版模型
  在跑」可稽核，代價是 Google 端若下架該版本需要人工更新常數，不再依賴自動
  解析到新版。

### Affected Components（影響範圍）

- `src/config.py`（新檔，`GEMINI_MODEL_NAME`）
- `src/transform/nlp_processor.py`（`GeminiDailyQuotaExhausted`／
  `is_daily_quota_exhausted()`／模型常數）
- `src/extractors/trend_discover.py`（`run_discovery()` 四態回傳、模型常數、
  `_generate_with_retry()` 的 `PerDay` 分類）
- `src/loaders/db_writer.py`（`fetch_last_discovery_probed_date()`；
  `upsert_theme_stock_mapping()` 改 `DO NOTHING`）
- `main_etl_pipeline.py`（探索段改寫、`run_discovery` 參數、
  `run_nlp_sentiment_pipeline()` 新增三參數）
- `tests/test_gemini_quota_discipline.py`（新檔，12 條）
- `tests/test_thematic_mapping.py`（既有測試改寫，1 條，`DO UPDATE`→`DO NOTHING`）

### Verification（驗證）

- [x] 12 條紅測（新檔 11 條＋既有測試改寫 1 條）對現行未修正程式碼：10 條自然
  FAIL/ERROR，2 條（一般 429 仍重試、非配額例外仍中止）現在通過——依提案設計
  是既有行為的防回歸鎖定，known-FAIL 證據改用記憶體內突變取得（`86ad3b1`）
- [x] GREEN 實作後全數 PASS，既有全套測試 1116 條無回歸（`9536771`）
- [x] 8 項記憶體內／原地暫時突變逐一執行確認 FAIL、逐一復原確認 `git diff
  --stat` 乾淨（`9536771` commit body 逐項列出 FAIL 訊息）
- [x] 審查方 GREEN 後獨立跑 16 項突變，15 項被抓到、1 項存活（探索端 `_generate_
  with_retry()` 的 `PerDay` 分類邏輯從未被真正執行到），補測 3b 並確認 known-FAIL
  （`7861d14`）
- [x] 距今天數判準測試未 patch 系統時鐘，09-19 系統日期推進後真實 FAIL 一次，
  修復並登記 `TEAM_PLAYBOOK.md` A16（`63b4419`）
- [x] 段 B 拋棄式庫演練：五個場景（配額耗盡、探索三態、映射不改）＋場景 1b
  （整條 `run_all_daily_tasks()` 對拋棄式庫真跑，驗證呼叫端接線本身）全數 PASS
  （`…rehearsal_20260918.md`）
- [x] 段 C 真實庫首次生效：七條驗收（標準五條＋本案新增兩條）全數 PASS，
  含 `theme_stock_mapping` 66 列（含 `updated_at`）執行前後完全相等、
  `fetch_failed_source_keys()` 47=47（`…real_run_20260919_success.md`）

### Remaining Risks（剩餘風險）

- RISK-031（Gemini 用量共用者不明）：PO 已查證用量主控台，確認僅本專案使用該
  key（`REPORTED, NOT INDEPENDENTLY VERIFIED`），用量縮減本案已落地。
- RISK-032（題材／關鍵字映射非 point-in-time）：`DO NOTHING` 阻斷了「探索改權重」
  這個新增觸發源，09-19 真實執行證實映射零變動時全歷史重算機制確實「沒有東西可
  重算」，但既有的「新增映射」觸發源本身仍在（`DO NOTHING` 只擋覆寫，不擋插入）。
- 09-19 真實執行發現兩項附帶事實，已登記 `PROJECT_STATUS.md` §0.5 候補：
  - **#35**：`run_us_stock_pipeline`（`period="3mo"`）在美股交易時段內執行會
    寫入盤中快照（09-18 執行當時美東時間中午，NVDA 收盤價／成交量皆為盤中值，
    下次執行時 3 個月視窗會自動覆蓋修正，不需人工介入，但驗收條件 1 因此持續
    排除 NVDA 在合理範圍）——與 08:30 雙時點案一併評估。
  - **#36**：`trend_discover._is_transient_exception()` 與 `nlp_processor._is_
    transient_exception()` 的暫態關鍵字清單不一致，且都缺 `504`——09-19 真實執行
    的 `DeadlineExceeded` 因此未進退避重試、第一次呼叫失敗就直接拋出（於本案
    是好事，避免浪費配額在重試上，但清單本身的不一致仍是需要另案處理的技術債）。

### 連結

`RISK-031`、`RISK-032`、`DEC-032`（`REFUSED`／`FETCH_FAILED` 分離先例）、
`DEC-039`（題材溢出全歷史重算機制）、`DEC-042`（成因 F 失敗鍵推導，Python 端
決策／SQL 端只取資料的架構先例，本案 `fetch_last_discovery_probed_date()`
沿用同一分工）、`PROJECT_STATUS.md` §0.5 #31／#33／#35／#36

### 證據文件

`doc/upgrade/gates/closed/GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md`；
`doc/upgrade/gates/evidence/GEMINI_QUOTA_DISCIPLINE_expectations.json`；
`doc/upgrade/gates/evidence/GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918.md`；
`doc/upgrade/gates/evidence/GEMINI_QUOTA_DISCIPLINE_real_run_20260919_success.md`

---

## DEC-044：`FEATURE_REGISTRY.md` Source 欄改函式／方法名稱錨點，禁止指向巢狀函式

- 日期：2026-09-20
- 狀態：APPROVED（Approved by: Project Owner，2026-09-21，隨 §0.5 #40 GOV
  摘要案 commit 一併補上戳記；`FEATURE_REGISTRY_SOURCE_ANCHOR_GATE_A_PROPOSAL.md`
  v2 核准、紅測 `c9ed87d`、GREEN 皆已通過複核）
- 觸發 Gate：`PROJECT_STATUS.md` §0.5 #38（審查方唯讀查證發現，2026-09-20，
  PO 裁決採方案 (a)）

### Context（背景）

`FEATURE_REGISTRY.md`（`UG-Gate-0` 已核准交付物）的 `Source` 欄原本以行號指向
`feature_aggregator.py`，唯讀查證發現 15 處引用中 14 處已經指到與該欄位完全
無關的程式碼——行號當文件錨點結構上保證會隨程式碼插入而漂移，且
`gate0_contract_check.py` 先前沒有任何一項檢查驗證這件事。同一份文件另有兩列
（`label_reason`／`target_triple_barrier`）早已使用 `<檔案>::<函式>()` 格式的
函式名稱錨點，自 `UG-G3-SB1`（2026-09-09）沿用至今（2026-09-20）仍正確——
函式名不會因為上方插入程式碼而失效，是行號會失效、函式名不會的直接對照組。

### Problem（問題）

不改變錨點機制，行號漂移會無限期持續且無法被發現——`gate0_contract_check.py`
的既有 14 項檢查沒有一項驗證 `Source` 欄的行號是否仍指向正確位置，14/15 處
失效的情況可以存在任意長時間而不被察覺。

### Alternatives Considered（考慮方案）

1. **逐列訂正行號、不改機制（不採納）**：只解決當下，下一次任何人在
   `feature_aggregator.py` 任何位置插入程式碼，全部引用會再次一起失效，
   而且因為剛訂正過，下一個人更不會去懷疑它。
2. **函式名稱錨點，但比照既有第 6／29 列，不區分頂層函式與類別方法
   （不採納）**：`FeatureAggregator.generate_daily_features()` 這類類別方法
   若只寫方法名（不含類別名），讀者無法直接定位該方法屬於哪個類別；且
   複核過程中發現 `_fuse_sentiment`（`sentiment_mean` 原錨點）其實是巢狀
   閉包，不是穩定的頂層函式或類別方法——若不特別區分三種穩定度，會把巢狀
   函式也當成合法錨點目標。
3. **函式／方法名稱錨點，區分頂層函式／類別方法／巢狀函式三種穩定度，
   只允許前兩種作為錨點（採納）**：見 Decision。

### Decision（決策）

1. `Source` 欄格式統一為 `<相對路徑檔名>::<函式名>()`（頂層函式）或
   `<相對路徑檔名>::<類別名>.<方法名>()`（類別方法）。
2. **錨點只准指向頂層函式或類別方法，不得指向巢狀函式、閉包或 lambda。**
   需要標示實作細節（例如某段邏輯實際實作在一個巢狀函式裡）時，寫成錨點
   **之外**的括號散文備註，不進錨點本身——本案 `sentiment_mean`
   （第 12 列）即為此規則的第一個實例：原錨點誤指向巢狀閉包
   `_fuse_sentiment()`，訂正為外層方法 `FeatureAggregator.generate_daily_
   features()`，`_fuse_sentiment` 降級為備註。
3. `gate0_contract_check.py` 新增 B15 檢查：驗證每個 `Source` 欄錨點的
   `<檔案>` 存在、且該檔案內存在 `def <函式或方法名>(`（正則允許前導縮排）。
   **刻意不驗證**：函式內是否真的賦值了對應欄位名（避免對迴圈變數間接
   賦值的合法寫法誤報）；`<類別名>` 前綴是否與函式實際所屬類別相符（要驗
   類別歸屬需解析 AST，是另一個量級的工作，且本案要修的是「指都指錯地方」，
   不是「指對地方但歸屬標錯」）。
4. 既有第 6／29 列（指向 `triple_barrier.py` 的頂層函式）維持原樣不動，
   不因新規則回頭改動——本來就符合規則，不需要類別名前綴。

### Rationale（理由）

- 函式名不會因為上方插入程式碼而失效，這是本文件既有兩列（第 6／29 列）
  十一天以來持續正確的直接證據，不是理論推測。
- 規則 2（禁止巢狀函式錨點）是本案真正的產出：機械檢查（B15）結構上無法
  分辨「頂層函式」與「巢狀閉包」——`def <名稱>(` 的正則比對不管縮排，
  一個巢狀函式被改名或整個被重構內聯掉，B15 一樣會誤判為「函式存在」
  （只是找到的是另一個同名但語意不同的定義，或根本找不到而 FAIL，取決於
  重構方式）。機械檢查在這一點上是結構性盲區，只能靠這條人工規則在源頭
  堵住——這個分工本身就是本決策要記錄的理由，不能只寫在 Gate A 提案裡，
  否則規則的存在理由會隨提案文件被歸檔而遺失。

### Trade-offs（取捨）

- B15 不驗證類別名前綴是否正確，`WrongClass.generate_daily_features()`
  這種類別名寫錯的情況仍會通過檢查——這是「只驗方法名、類別名當可選前綴」
  這個設計換來的直接副作用，換取的是同一條檢查邏輯能同時涵蓋頂層函式與
  類別方法兩種格式，不需要為類別方法另寫一套解析邏輯。
- 巢狀函式規則依賴人工紀律（撰寫或複核 `FEATURE_REGISTRY.md` 時遵守），
  沒有機械強制——刻意不做成機械檢查：要真的驗證「錨點指向的是頂層函式或
  類別方法，不是巢狀函式」需要解析 AST 取得每個 `def` 的巢狀深度，是本案
  範圍外的工作量，且目前只有一個歷史實例（`_fuse_sentiment`），尚不構成
  立即需要機械化的頻率。

### Affected Components（影響範圍）

- `doc/upgrade/contracts/FEATURE_REGISTRY.md`（19 列 `Source` 欄，見提案 §2.2）
- `scripts/verify/gate0_contract_check.py`（新增 B15）

### Verification（驗證）

- [x] `/tmp` 拋棄式副本 known-FAIL：把 `compute_rsi` 改名為 `compute_rsi_v2`
  後，B15 對應邏輯正確回報「找不到 def compute_rsi(」；復原後 `git diff
  --stat` 對真實 repo 顯示零變更（`c9ed87d`）
- [x] 類別名前綴故意寫錯（`WrongClass.generate_daily_features()`）仍
  PASS，確認實作沒有偷偷加上未經提案核准的類別名驗證（`c9ed87d` 附驗證
  過程）
- [x] 錨點後的括號散文備註不參與抽取，確認不會誤把備註內容當成第二個
  錨點（`c9ed87d` 附驗證過程）
- [x] 對現行（未修改）`FEATURE_REGISTRY.md` 執行 B15：掃描到 4 個既有錨點
  （第 6／29 列各含兩個），0 個不合規，PASS——確認此結果的意義是「B15
  只驗證已存在的錨點是否有效」，不是「檢查沒有偵測力」（`c9ed87d`）
- [x] GREEN 後對真實 `FEATURE_REGISTRY.md` 執行 B15：掃描到 23 個錨點
  （4 個既有＋19 個新改），0 個不合規，PASS；`gate0_contract_check.py`
  Part B 15/15 PASS；全套測試 1117 條無回歸
- [x] **複核第三輪補強**（2026-09-20，審查方發現）：B15 原始版本的迴圈結構
  只對「已抽到的錨點」逐一驗證，若某列 Source 欄**一個錨點都抽不到**
  （例如被改回行號或裸檔名——本案要防的正是這種回歸），內層迴圈完全不會
  碰到該列，B15 對它零檢查、PASS 照樣成立。補上規則：Source 欄提及 `.py`
  卻抽不到任何錨點即 FAIL。`/tmp` 拋棄式副本 known-FAIL：將第 8 列
  （`rsi_14`）錨點換回行號 `feature_aggregator.py L142-168`，B15 正確回報
  `#8 rsi_14: Source 欄提及 .py 檔卻抽不到函式/方法名錨點`；復原後對現行
  文件重跑仍 23 個錨點、0 不合規、PASS，對真實 repo `git diff --stat`
  於補強落地前顯示零殘留變更。

### Remaining Risks（剩餘風險）

- B15 的已知盲區（見 Trade-offs）：類別名前綴不受驗證、巢狀函式規則無機械
  強制。若未來新增更多巢狀函式被誤用為錨點，需要靠複核而非工具發現。
- ~~Source 欄整列無錨點時 B15 零檢查、無聲通過~~——此項已於複核第三輪補強
  關閉（見上方 Verification 新增項）。
- `FEATURE_REGISTRY.md` 第 310 行（散文，非表格 Source 欄）另有一個符合
  格式的錨點 `` `src/transform/feature_aggregator.py::assign_trading_days_
  per_stock()` ``，B15 依設計只掃表格 Source 欄，此錨點不受保護。複核第
  三輪已確認該函式現實存在，目前正確，僅登記風險不在本案處理。

### 連結

`PROJECT_STATUS.md` §0.5 #38；`DOCUMENT_DRIFT_REMEDIATION.md` `DRIFT-035`
（本案落地後結清「另兩列留待下次」註記）；`CLAUDE.md` §9A.1（機械檢查的
結構性盲區需要靠人工規則堵住的同一類案例）

### 證據文件

`doc/upgrade/gates/closed/FEATURE_REGISTRY_SOURCE_ANCHOR_GATE_A_PROPOSAL.md`
（v2，git mv 待結案 commit 一併執行）

---

## DEC-045：統一 Gemini 暫態例外判斷清單；`deadline`／`504` 不列為可重試

- 日期：2026-09-21
- 狀態：APPROVED（Approved by: Project Owner，2026-09-21，隨 §0.5 #40 GOV
  摘要案 commit 一併補上戳記；`GEMINI_TRANSIENT_KEYWORDS_UNIFY_GATE_A_PROPOSAL.md`
  v3 核准、紅測 `6b0eb37`，皆已通過複核）
- 觸發 Gate：`PROJECT_STATUS.md` §0.5 #36（第三次真實每日 ETL，2026-09-19，
  PO 複核唯讀查證發現）

### Context（背景）

`src/extractors/trend_discover.py` 與 `src/transform/nlp_processor.py` 各自
維護一份「哪些例外算暫態、值得退避重試」的關鍵字清單，兩份清單是真包含關係
（前者是後者的子集）。2026-09-19 第三次真實每日 ETL 撞到
`DeadlineExceeded: 504 Deadline expired before operation could complete.`
時，`nlp_processor` 端的清單含 `deadline`、判為暫態並退避重試；`trend_
discover` 端不含、直接拋出——同一類錯誤在兩條路徑上結果不一致。

### Problem（問題）

不統一，這種不一致會無限期持續：任一模組單獨補上遺漏的關鍵字，另一模組仍
落後，且沒有任何機制強制兩份清單同步。`tests/` 內原本也沒有任何測試直接
斷言清單內容，兩份清單漂移到真包含關係且都缺 `504`，卻在 #31/#33 整個
Gate/SB 週期與段 B 拋棄式演練中都未被發現。

### Alternatives Considered（考慮方案）

1. **兩份清單合一後補上 `504`（v1 提案，不採納）**：前提是「504 應該重試，
   只是重試幾次」。PO 推翻此前提——`DeadlineExceeded` 代表同一份 prompt
   已經跑到逾時上限，用一模一樣的內容原地重送，沒有機制讓伺服器端在期限內
   算得更快，重試换來的期望結果是再次逾時，白白燒掉配額（免費層每日僅
   20 次請求，探索每週僅 1 次），直接抵銷 #31 才剛省下來的成果。
2. **把共用邏輯塞進既有的 `src/extractors/retry_policy.py`（不採納）**：
   該模組 `is_retriable()` 第一道判斷是 `isinstance(exc, requests.
   exceptions.RequestException)`——Gemini SDK 例外不是這個型別的子類別，
   塞進去會讓所有 Gemini 暫態錯誤被無條件誤判為不可重試，不是語意混雜，
   是會產生錯誤行為。
3. **兩份清單取聯集後移除 `deadline`、不新增 `504`，抽成 `src/common/
   gemini_retry.py` 獨立模組（採納）**：見 Decision。

### Decision（決策）

1. `src/common/gemini_retry.py`（新建）持有唯一一份
   `GEMINI_TRANSIENT_KEYWORDS`（九項：`429`／`quota`／`rate limit`／
   `resourceexhausted`／`resource_exhausted`／`503`／`unavailable`／
   `timeout`／`connection error`）與判斷函式 `is_transient_gemini_
   exception()`，兩處呼叫端的 `_is_transient_exception` 皆委派此函式，
   不再各自持有清單字面量。
2. **`deadline`／`504` 兩類錯誤皆不列為可重試**：同一份 payload 重送**不會
   讓伺服器端 deadline 變短**，這是本案真正的判斷依據，不是清單長短的
   問題。`429`（等待期過了配額就恢復）、`503`（伺服器忙完就正常）的「稍等
   重試」有明確物理機制支持會變好，deadline 沒有——重試 deadline 類錯誤的
   期望結果是再次逾時，只會消耗配額而不會提高成功率。
3. **保留 `timeout`**：連線層逾時（TCP handshake、TLS 交握、等待首個
   byte）可能在請求根本還沒送達 Gemini 伺服器、伺服器完全不知道我們問了
   什麼的階段就發生，這種情況下重試不是「用同樣的內容再求一次已經跑不完
   的運算」，而是「再給一次連線機會」，與 `retry_policy.py`（DEC-032）對
   「拿不到 `status_code`」歸類為可重試的邏輯同構。`deadline` 則是請求已
   被伺服器接手、只是沒能在期限內做完——兩者發生的層次不同，值得重試的
   理由也不同，因此保留 `timeout`、移除 `deadline`。
4. **不新增 `504`**：`504` 這個數字字串本來就不在任一份現行清單裡。`504`
   對應的 `DeadlineExceeded` 已經被 `deadline` 這個詞面判準涵蓋（真實
   訊息「小寫後含 `504` 也含 `deadline`」）——**加了 `504` 反而會讓 504
   訊息透過數字字串命中變成暫態，與移除 `deadline` 的決策矛盾，兩件事
   必須一起做才自洽**，不能只做其中一半。
5. `is_daily_quota_exhausted()`（`nlp_processor.py`，DEC-043 決策 3）的
   呼叫順序不變：兩處呼叫端必須先判每日配額耗盡、才判暫態分類，`src/
   common/gemini_retry.py` 不重複、不依賴這個判斷，維持兩者各自獨立。
6. `max_retries`（兩處皆 5）與退避序列（`min(2**attempt, 16)`）不動——
   v1 提案原本列出的三個 `max_retries` 選項連同其前提一併撤回。

### Rationale（理由）

- **同一份 payload 重送不會讓伺服器端 deadline 變短，因此 deadline／504
  類錯誤不列為可重試**——這是本決策的核心論點，日後若有人想把 `504`／
  `deadline` 加回可重試清單，需先在此提出推翻這句話的理由，而非直接改
  程式碼。
- 09-19 真實事件已證實「不重試」路徑可行且代價有界：探索撞 504 未重試、
  記成 `FETCH_FAILED`（不算「已問過」）、後續階段全部完成、`exit 0`；
  `FETCH_FAILED` 語意誠實，下週探索排程會自然再試一次，NLP 端同理靠既有
  checkpoint／`SOURCE_FAILED` 機制自然回補。
- 影響面驗證改採**封閉式證明，不採語料掃描**：語料掃描（對既有 log／
  文件裡出現過的真實訊息逐條套用新舊清單比對）曾被考慮作為佐證，但結果
  隨掃描範圍變動（三種掃法分別得到 190／127／27 段候選、對應 1／9／8 段
  變化，彼此不一致），不是可重跑的證據。正確證明：因 `OLD = NEW ∪
  {"deadline"}` 且判定式為 `any(...)`，兩者判定不同若且唯若訊息含
  `"deadline"` 且不含九項保留關鍵字中任一個——用 500,000 組隨機合成訊息
  窮舉核對，不一致次數為 0，任何人重跑同一段程式碼都得到同一個結論。

### Trade-offs（取捨）

- `src/common/gemini_retry.py` 是本案唯一新建模組，`nlp_processor.py`／
  `trend_discover.py` 對它的依賴屬「共用行為邏輯」，與既有的
  `is_daily_quota_exhausted()`（「共用資料型別」）依賴性質不同，兩者刻意
  不合併，見 §3.1 三候選比較。
- `is_transient_gemini_exception()` 沿用既有清單式判準的既有限制（子字串
  比對，非結構化例外分類），未在本案一併改為例外類別判準——那是本案範圍
  外的更大改動。

### Affected Components（影響範圍）

- `src/common/gemini_retry.py`（新建）
- `src/extractors/trend_discover.py`（`_is_transient_exception` 改為委派）
- `src/transform/nlp_processor.py`（同上，並移除 `deadline`）
- `tests/test_gemini_transient_keywords_unify.py`（新建，6 條）

### Verification（驗證）

- [x] 500,000 組隨機合成訊息窮舉核對 `old_match != new_match` 與封閉式
  判準 `("deadline" in msg) and not any(NEW)` 完全一致，不一致次數 0
- [x] 四個邊界案例（真實 504 訊息／`"deadline exceeded after timeout"`／
  `"429 quota exceeded"`／`"503 Service Unavailable"`）逐一核對，結果與
  封閉式判準預測一致
- [x] 紅測 `6b0eb37`：6 條測試中 4 條對現行程式碼 FAIL（測項 1
  `ModuleNotFoundError`；測項 2／3 紅燈落在 `nlp_processor` 側，
  `trend_discover` 側本來就 PASS；測項 6 兩模組皆含字面清單），2 條
  （測項 4／5）本來就 PASS（防回歸鎖定）——與各測試 docstring 逐條預期
  完全吻合
- [x] **複核第三輪追加的身分比對測試**（測項 1 的 `assertIs`）：原始
  `call_count==2` 斷言只證明「兩處各自有同名可呼叫物件、且被呼叫」，不
  證明兩者指向同一物件——用 `/tmp` 拋棄式 mirror 構造 known-FAIL：把共用
  函式複製回 `trend_discover.py`（模組層級新增同名函式 `is_transient_
  gemini_exception`，覆蓋 import 進來的綁定，清單變數改名為 `GEMINI_
  TRANSIENT_KEYWORDS` 躲避測項 6 的字面清單比對），確認**原始 `call_
  count==2` 斷言與測項 6 皆 PASS，新增的 `assertIs` 正確 FAIL**——證明
  舊版兩條檢查聯集起來仍會放行「兩份獨立複本」這個 #36 本來要防的回歸，
  身分比對補上了這個盲區。mirror 事後整個刪除，`git status` 確認真實
  repo 全程未被觸碰。
- [x] GREEN 後 6 條測試全數 PASS；全套測試 `Ran 1123 tests` OK；
  `gate0_contract_check.py` Part B 15/15 PASS

### Remaining Risks（剩餘風險）

- `is_transient_gemini_exception()` 的清單式判準（子字串比對）本身可能有
  誤判空間（例如訊息內容恰好含 `"timeout"` 但實際是應用層邏輯錯誤），此
  風險為既有設計沿用，非本案新增，不在本案處理範圍。
- 若 Gemini SDK 未來的例外訊息格式改變（例如不再含 `"deadline"` 字面
  詞），本判準會失效，需要屆時另案處理——本案未加入格式穩定性的機械檢查。

### 連結

`PROJECT_STATUS.md` §0.5 #36；`DEC-032`（`retry_policy.py` 的「拿不到
status_code 即可重試」邏輯，本案 §3 保留 `timeout` 的理由與其同構）；
`DEC-043`（`is_daily_quota_exhausted()` 判斷順序，本案繼承不變）；
`CLAUDE.md` §9A.1（`FEATURE_REGISTRY_SOURCE_ANCHOR` 案 B15 的「檢查看不見
它自己要防的回歸」同一類案例，本案身分比對的追加是同一教訓的第二個實例）

### 證據文件

`doc/upgrade/gates/GEMINI_TRANSIENT_KEYWORDS_UNIFY_GATE_A_PROPOSAL.md`
（v3，待結案 commit git mv 至 `gates/closed/`）

---

## DEC-046：給 PO 的一頁式進程摘要——格式、時機、存放位置（`doc/progress/`，本機不版控）

- 日期：2026-09-21
- 狀態：APPROVED（Approved by: Project Owner，2026-09-21，本次裁決直接核准）
- 觸發 Gate：`PROJECT_STATUS.md` §0.5 #40（PTT 情緒覆蓋率量測案段 A 結案
  commit `b131bbf` 複核通過後，PO 直接裁決開立本 GOV 案）

### Context（背景）

Gate B 報告是給審查方的證據文件，動輒 150～280 行，hash／路徑／逐項驗收對
PO 是雜訊；PO 直到讀技術報告才第一次知道情緒擷取只追蹤 27 個關鍵字
（§0.5 #39），代表**現行的結案報告流程沒有讓 PO 建立起每個案子的概念層
理解**，PO 需要另一種文件才看得到「這案做了什麼、中途出了什麼事」。

### Problem（問題）

不建立標準格式與強制觸發點，這件事只會停在「PO 口頭要求時才臨時寫一份」，
品質與涵蓋範圍因案而異，且沒有機制確保**盲點也被寫進去**——§0.5 #39 那個
問題發生當下沒有任何人發現，任何摘要格式都寫不出「發生了什麼我沒發現的事」；
唯一能提早讓盲點浮現的結構是強制回答「這案依賴但未驗證的假設是什麼」
「這案動了哪個前提、還有什麼建立在那個前提上」。

### Alternatives Considered（考慮方案）

1. **摘要進 `doc/upgrade/gates/closed/`，隨 Gate B 文件一起 commit（不採納）**：
   會被 `gate0_contract_check.py` 的 `DOC_PATHS` 與既有文件同步機制當成受管
   治理文件對待，之後任何規格變動都要連動改它，而它的性質是「當下的概念快照」，
   不該隨系統演進被「維護」成看起來仍然準確。
2. **不設固定格式，每案自由發揮（不採納）**：格式自由等於沒有格式——
   §5、§6（未驗證假設、動了哪個前提）這種容易被跳過的必填項，正是最需要
   結構強制的部分，自由發揮下第一個被省略的就是它們。
3. **一頁式、八節固定格式，存 `doc/progress/`，加入 `.gitignore`，
   綁在 `gate-submit` skill 產出 10（採納）**：見 Decision。

### Decision（決策）

1. **格式**：一頁、硬上限 60 行，八節固定順序——①為什麼做／②做了什麼
   （零 hash，概念層）／③中途發生什麼（含被複核退回的原因、自己抓到的錯）／
   ④成果（≤5 個關鍵數字，各附一句白話解讀）／⑤沒做的與沒驗證的（**必填**，
   含本案依賴但未驗證的上游假設）／⑥改變了什麼前提、哪些其他機制依賴它
   （**必填**）／⑦新登記的候補與風險（編號＋一句話）／⑧PO 接下來要決定的事。
   完整欄位定義見 `gate-submit` skill 產出 10（唯一權威位置，本檔不重複列出
   逐欄細節，避免日後修訂時兩處各自漂移）。
2. **時機**：Gate B 送審且**結案 commit 完成之後**才寫，不影響 commit 本身
   的授權與內容；一案一份。分段執行的案子只在**全案結束**時寫一份，不逐段。
3. **存放與生命週期**：`doc/progress/YYYY-MM-DD_<案號>_<slug>.md`。
   **不 commit、不上 GitHub**（`.gitignore` 已排除）、**不進
   `gate0_contract_check.py` 的 `DOC_PATHS`**、**不維護**（寫完即為證據檔，
   只在發現錯誤時修正，不隨後續文件同步連動）、**不回填**（本決策生效前已
   結案的案子不補寫）。
4. **審查**：送審查方核對「與 Gate B 證據是否一致」，通過才轉 PO；不另開
   一輪獨立複核（避免摘要本身變成又一個需要走完整 Gate 流程的交付物）。
5. **觸發機制**：綁進 `gate-submit` skill 產出 10，而非另立一條規則——
   理由同產出 7／8／9（`CLAUDE.md` §16.3 規則 4／5、`gate-submit` 產出 7／8／9
   的既有先例）：**綁事件、不綁個案**。`GOV-09` 的教訓是「綁個案的規則
   （如 `gates/` 根層清空義務）漏了兩次，綁事件的規則（如 §0.5 #10 的
   ADR 一併轉 `APPROVED`）一次都沒漏」——本決策延續同一個機制選擇。
6. **第一份**：§0.5 #40（PTT 情緒覆蓋率量測案）全案結束時。

### Rationale（理由）

- 概念式摘要與 Gate B 證據文件服務不同讀者、不同目的，分離存放（`gates/`
  vs `progress/`）比混在一起再靠格式區分更不容易被日後的文件同步機制誤觸。
- 不版控是刻意選擇，不是疏漏：這類摘要的價值在於「當下寫作者看得到什麼」，
  若進 repo 就會被期待隨程式碼演進保持準確，而這正是它不該承擔的責任——
  歷史快照的價值在於誠實反映寫作當下的認知邊界，事後修飾反而失真。

### Trade-offs（取捨）

- 不版控代表沒有 `git log`／`git blame` 可稽核這些摘要的修改歷史，也沒有
  `git reflog`／`git fsck` 可復原意外刪除——`gate-submit` 產出 10 與
  `TEAM_PLAYBOOK.md` 已明文揭露 `git clean -fdx` 會直接刪除且 `git status`
  無感知，清理前需人工確認，這是本決策明知並接受的代價，換取「不必維護」
  的效益。
- 「不進 `DOC_PATHS`」代表 `gate0_contract_check.py` 不會驗證這些摘要與
  程式碼的一致性——本來就不該驗證，它是快照不是規格。

### Affected Components（影響範圍）

- `.gitignore`（新增 `doc/progress/`）
- `doc/README.md`（資料夾表新增一列）
- `.claude/skills/gate-submit/SKILL.md`（新增產出 10，自檢流程新增一步）
- `doc/governance/TEAM_PLAYBOOK.md`（§4 表新增一列＋ `git clean -fdx` 警語）

### Verification（驗證）

- [x] `git check-ignore -v doc/progress/2026-09-21_test_sample.md`：
  `.gitignore:33:doc/progress/`，`EXIT=0`，證明 ignore 生效
- [x] `python scripts/verify/gate0_contract_check.py`：Part B 15/15 PASS，
  `exit 0`（`doc/progress/` 未出現在任何 `DOC_PATHS` 檢查項，未被要求存在
  或符合任何契約）
- [x] `doc/README.md`、`gate-submit` skill 產出 10、`TEAM_PLAYBOOK.md` §4
  三處皆已同步（本 ADR 傳播清單，本次 commit 一併落地）

### Remaining Risks（剩餘風險）

- 本機限定代表換機器或另一位協作者看不到歷史摘要——已在決策中明文接受，
  價值在於降低單一 PO 逐案理解的認知成本，不是建立可攜式團隊知識庫。
- 「摘要與 Gate B 證據是否一致」的審查標準未機械化，依賴審查方人工判讀，
  與本專案 §9A.1「為偵測而寫」的精神不完全一致——已知的權衡，可留待日後
  視實際使用情形決定是否需要補一項機械檢查。

### 連結

`PROJECT_STATUS.md` §0.5 #40；`gate-submit` skill 產出 7／8／9（同一「綁事件
不綁個案」機制家族）；`CLAUDE.md` §16.3（規則 4／5 漏執行兩次的同型教訓，
GOV-09）

### 證據文件

本 ADR 為格式與流程本身的權威定義來源之一，完整逐欄格式見
`.claude/skills/gate-submit/SKILL.md` 產出 10。
