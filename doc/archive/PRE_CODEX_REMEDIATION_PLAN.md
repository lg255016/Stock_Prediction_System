# PRE_CODEX_REMEDIATION_PLAN.md

## 金融情緒與股價趨勢預測系統 — Codex 導入前整頓計畫

**文件目的**：把目前「Gemini 協助完成的原型＋研究報告＋PRD／SDD＋實際 Repository」整理成一個適合 Codex 長期協作的安全基線。

本計畫不是全面重寫專案，也不是立即進入 Phase 3 ML。核心策略是：

> **先建立可回復基線 → 修正高風險語意問題 → 建立最小測試安全網 → 對齊文件與 Research → 再進入研究驅動的 ML 開發。**

---

# 0. Audit Summary（稽核摘要）

目前 Repository 已具有良好的基本方向：

- `ETLPipelineManager` 作為 Orchestrator（流程協調器）
- Extract / Transform / Load 分層
- TWSE / yfinance / PTT 異質資料源
- PostgreSQL
- Hybrid NLP（SnowNLP + Cache + Gemini）
- Trend Discovery（熱門詞探索）
- FeatureAggregator（特徵聚合器）初版
- Idempotent Upsert（冪等寫入）基礎

但 Codex 導入前存在以下主要風險：

| ID | 問題 | 嚴重度 | 主要影響 |
|---|---|---|---|
| R-01 | `schema.sql` 與 `init_db.py` 不一致 | Critical | 新環境無法可靠重建 DB |
| R-02 | NLP LLM 失敗可能仍推進 Checkpoint | Critical | 未完成資料被誤標為完成 |
| R-03 | DB read error 被轉成 empty DataFrame | High | 錯誤被誤判為「無資料／全部完成」 |
| R-04 | Cache hit 的中立分數可能再次呼叫 LLM | High | API 成本、語意不一致 |
| R-05 | Soft Delete 可能被 AI 重新啟用／category 被覆寫 | High | 違反既有架構決策 |
| R-06 | TPEx 歷史紀錄與目前 Code 不一致 | High | 作品文件可信度下降 |
| R-07 | Canonical Stock ID 未定義 | High | 股價與情緒 merge 失敗風險 |
| R-08 | PTT 時間與交易日對齊未定義 | High | Look-ahead Bias 風險 |
| R-09 | Automated Tests 不足 | High | Agent 修改缺少回歸安全網 |
| R-10 | Research features 尚未完整落地 | Medium/High | Phase 3 無法宣稱 research-aligned |
| R-11 | Git working tree 尚未形成 Codex baseline | High | 難以追蹤修改來源與回滾 |
| R-12 | PostgreSQL physical data 未在 `.gitignore` 明確排除 | High | 誤 commit 本機 DB 風險 |

---

# 1. Remediation Principles（整頓原則）

1. **No Big Bang Rewrite（禁止一次性全面重寫）**：保留目前已能工作的模組化架構。
2. **Small Batch（小批次）**：一次只處理一個風險群組。
3. **Test Before Expansion（先測試，再擴充）**：Phase 3 前先補最小安全網。
4. **Evidence First（證據優先）**：每個重大修復都要留下問題、根因、修改與驗證紀錄。
5. **Local DB First（開發階段維持本機 DB）**：不在此階段推動 cloud migration（雲端遷移）。
6. **Preserve Data（保護資料）**：不得破壞 `.devcontainer/postgres-data/`。
7. **Research ≠ Specification（研究不等於規格）**：先把研究轉成明確 requirement，再實作。

---

# Gate 0 — Freeze & Recoverability（凍結現況與可回復性）

## Goal（目標）

在 Codex 第一次修改業務程式前，建立可以清楚回復的「Pre-Codex Baseline（Codex 導入前基線）」。

## Tasks（任務）

### G0-1. 建立專案備份

- 保留目前上傳的 ZIP 作為外部快照。
- 開發資料庫建立 logical backup（邏輯備份），優先使用 `pg_dump`，不要只依賴 PostgreSQL physical data directory（實體資料目錄）。
- 確認備份不包含要公開的 secrets（秘密資訊）。

### G0-2. Repository Hygiene（Repository 整潔）

檢查並更新 `.gitignore`，至少確認忽略：

```gitignore
.env
*.env
__pycache__/
*.pyc
.devcontainer/postgres-data/
```

不要 commit：

- `.env`
- `.devcontainer/postgres-data/`
- API keys / tokens / passwords
- Python bytecode cache

### G0-3. 整理目前 Git Working Tree

目前有大量 modified / deleted / untracked files。先人工 review：

- 哪些刪除是刻意的文件版本升級？
- 哪些新檔是應保留的新版本？
- `src/extractors/test.py` 是否只是實驗檔？
- 舊 PDF／handoff 暫存資料是否需要移出正式 source tree？

### G0-4. 建立 Baseline Commit

完成上述確認後，建立一次明確提交，例如：

```text
chore: establish pre-Codex project baseline
```

這個 commit 的目的不是表示「程式已完成」，而是表示「從這個點開始，Codex 的修改可以清楚追蹤」。

## Verification（驗證）

- `git status` 為乾淨，或僅存在使用者明確保留、不打算 commit 的檔案。
- `.env` 與 `postgres-data` 不在 Git index（Git 索引）中。
- 有可用 DB logical backup。
- 可找到 baseline commit hash。

## Portfolio Evidence（成果證據）

記錄一次「從 AI-assisted prototype（AI 協助原型）轉向可治理 Agent workflow（Agent 工作流程）」的工程治理決策。

## Gate 0 Done When

**有備份、有乾淨 Git 基線、有 secret/data safety。**

---

# Gate 1 — Database Single Source of Truth（資料庫單一真實來源）

## Goal

消除 `database/schema.sql` 與 `database/init_db.py` 的分歧，使新環境能可靠建立目前程式需要的資料表。

## Current Conflict（目前衝突）

`schema.sql` 已定義：

- `tracking_keywords`
- `entity_mapping`
- `stock_prices`
- `market_articles`
- `sentiment_cache`
- `daily_ml_features`

而 `init_db.py` 仍定義較舊的：

- `stock_prices`
- `market_articles`
- `daily_model_features`

其中 `daily_model_features` 與現在 Code 使用的 `daily_ml_features` 名稱不一致。

## Proposed Direction（建議方向）

第一階段不要引入 Alembic 等 migration framework（遷移框架），先採簡單且透明的方案：

- `database/schema.sql` 作為 DDL Single Source of Truth（資料定義單一真實來源）。
- `init_db.py` 改成讀取並執行 `schema.sql`，避免複製兩套建表 SQL。
- Database config（資料庫設定）逐步由環境變數取得；本機可保留安全的 development default，但不能把 cloud credential 寫死。

## Tests / Checks

- 在獨立測試資料庫或暫時 database 中從零執行 schema。
- 驗證所有目前程式依賴的 table / index 都存在。
- 第二次執行 initialization 不應失敗（idempotent initialization／冪等初始化）。
- 不碰目前開發 DB 的實體資料。

## Documentation Update

- SDD 更新資料庫初始化方式。
- `DECISIONS.md` 記錄「為何採 schema.sql 單一 DDL 來源」。

## Gate 1 Done When

**任何新 Dev Container 都能用一條明確流程建立與目前 Code 相容的 schema。**

---

# Gate 2 — Failure Semantics & NLP Reliability（失敗語意與 NLP 可靠性）

## Goal

讓系統明確區分「成功」、「沒有資料」與「失敗」，修正目前最危險的假成功路徑。

## G2-1. DB Error != Empty Result

### Problem

`DBWriter.fetch_data()` 遇到 exception 目前回傳 empty DataFrame。

### Risk

上層可能把 DB 連線失敗解讀為「沒有待處理資料」，例如 NLP pipeline 顯示全部完成。

### Desired Behavior

- DB exception 應 raise（拋出）明確錯誤，或使用顯式 Result type（結果狀態）。
- Empty DataFrame 只代表 query 成功但沒有 row。

### Tests

- 模擬 DB exception → pipeline 必須失敗／停止，不得印出「全部完成」。
- Query 成功 0 rows → 才能正常視為 empty。

## G2-2. Checkpoint Success Semantics

### Problem

LLM 失敗時 `_batch_llm_api()` 回傳 `{}`，原 SnowNLP fuzzy score（模糊分數）仍可能被寫入 `market_articles.sentiment_score`，造成 checkpoint 前進。

### Required Decision

在實作前先決定其中一個正式策略：

**Option A — Strict LLM Completion（嚴格 LLM 完成）**  
Fuzzy item 只有 Gemini 成功或 Cache 命中才算完成；失敗保持 pending，可重試。

**Option B — Explicit Fallback State（明確 fallback 狀態）**  
允許 SnowNLP 當正式 fallback，但 DB 必須額外保存來源／狀態，例如 `sentiment_source`、`processing_status`，不能只靠一個分數假裝已完成 LLM。

目前較推薦 **Option A** 作為 MVP，因為較小改動且 checkpoint 語意清楚；若之後要追求高 availability（高可用性），再評估 Option B。

### Tests

- LLM failure → fuzzy article 下次仍可被撈取。
- Cache hit → 不需要 API。
- 成功 LLM → 才推進正式 checkpoint。

## G2-3. Cache Semantics

### Problem

現有程式在套用 cache 後以「分數是否還在 0.4–0.6」判斷是否再呼叫 LLM，因此 cached neutral score（已快取的中立分數）可能再次送 LLM。

### Desired Behavior

將「是否已有可信 cache」與「數值是否 fuzzy」分開判斷。

### Tests

- Cache = 0.50 時，不再呼叫 Gemini。
- Cache = 0.45 / 0.55 同樣不再呼叫 Gemini。
- 只有沒有 cache 的 fuzzy item 才進 LLM。

## Gate 2 Done When

**Failure 不再假裝成功；Checkpoint 與 Cache 的行為有測試保護。**

---

# Gate 3 — Configuration Integrity & Data Contracts（設定完整性與資料契約）

## Goal

修正追蹤關鍵字生命週期與 stock identity（股票識別）問題，避免 Phase 3 在錯誤 join 上訓練。

## G3-1. Soft Delete Integrity（軟刪除完整性）

### Problems

- `TrendDiscover` 對既有 keyword 使用 upsert 並設 `is_active=True`，可能重新啟用使用者已停用的詞。
- `disable_tracking_keyword()` 透過預設 `category='user_added'` 的 upsert，可能改變原分類。

### Desired Behavior

- AI discovery 不得自動覆蓋人工停用狀態。
- Disable 僅更新 `is_active` 與 `updated_at`，不改 category。
- 如果要重新啟用人工停用詞，需由明確的 user action（使用者操作）或特別核准規則完成。

### Tests

- `core_stock + inactive` 經 AI discovery 後仍 inactive 且 category 不變。
- disable 不改 category。

## G3-2. Canonical Stock ID（標準股票識別碼）

### Problem

目前可能同時出現：

- `2330`
- `2330.TW`
- `6488`
- `6488.TWO`
- `NVDA`

Provider symbol（資料來源代碼）與 internal stock_id（系統內部 ID）尚未正式分離。

### Required Design Decision

在進 Phase 3 前建立一個最小可行的 identity contract，例如：

```text
canonical_stock_id: 6488
market: TPEx
provider: yfinance
provider_symbol: 6488.TWO
```

不一定要立刻新增完整 instrument master table（標的主檔），但必須確保：

- `stock_prices.stock_id`
- `entity_mapping.stock_id`
- `daily_ml_features.stock_id`

使用同一套 canonical ID。

### Tests

- yfinance fallback 取得 `6488.TWO`，寫入 DB 後仍能與 `entity_mapping -> 6488` 正確 join。

## G3-3. TPEx Documentation Conflict

### Problem

舊 Phase 2 文件宣稱 TPEx fallback 已實作，但目前 `twse_scraper.py` 沒有完整 TPEx 流程；只有實驗性 `src/extractors/test.py` 片段。

### Required Action

先做 Evidence Reconciliation（證據對齊），不要為了讓文件看起來正確而硬補一套 TPEx。

選擇：

- 若 TPEx 是當前需求：建立正式 ADR，再完整實作與測試。
- 若目前 MVP 使用 yfinance fallback：更新歷史回顧文件，寫清楚「曾嘗試 TPEx，最後目前版本採 yfinance fallback」，保留嘗試與決策過程。

## Gate 3 Done When

**追蹤設定不會被 AI 無意破壞；股票代碼具有一致 Data Contract；文件不再宣稱不存在的 TPEx 實作。**

---

# Gate 4 — Prediction Time Convention & Time Alignment（時間對齊與防前視偏誤）

> **工程治理附註**：原定獨立的「最小自動化測試安全網」已隨行落實於 Gate 1 至 Gate 3 的小批次實作中（累積 65 項測試，覆蓋 DB / NLP / Soft Delete / Canonical ID）。原 Gate 5（時間對齊規格）正式整合編排為 **Gate 4**，並持續將測試套件擴充至 83 項測試。

## Goal

在產生 ML target 以前先決定「模型在什麼時間預測，以及當下能看到哪些資料」，徹底根除前視偏誤（Look-ahead Bias）。

## Architecture Decisions (DEC-005)

落實 Project Owner 核准之 **雙模式預測架構（Dual-Mode Prediction Architecture）**：
1. **模式一（盤前即時反應模型 / Pre-Market Shock）**：08:30 Cutoff，聚合昨夜美股與隔夜/週末討論，預測當日開盤漲跌。
2. **模式二（盤後動能延續模型 / Post-Market Momentum）**：15:30 Cutoff，結合當日完整 OHLCV 價量與全日情緒，預測次一交易日（$T+1$）收盤報酬。
3. **次一交易日歸併法（Roll-Forward Mapping）**：週末、連續假期與當日過 Cutoff 的文章，一律向後確定性歸併至「次一開盤交易日」，確保週末情緒無損累積且零時間洩漏。
4. **PTT 日期時間解析強化**：支援標準 RFC/ANSI 內頁格式、ISO 格式，並以參考時間比對修復 1 月初抓取 12 月底文章的跨年 bug。

## Small Batches
- **G4-SB1**：PTT 精確時間解析器與交易日曆 Roll-Forward 歸併邏輯（已完成，13 項測試通過）。
- **G4-SB2**：Zero Look-ahead 特徵聚合、多日滾動/滯後特徵與 Target Label 生成器（已完成，5 項防洩漏測試通過）。

## Gate 4 Done When

**任何一筆 feature 都能回答「在預測當下，這筆資料是否已經可取得？」且測試套件確認 0 前視偏誤洩漏。**

---

# Gate 5 — Research Requirements Extraction（研究需求抽取）

## Goal

不要讓 Codex 每次都重新閱讀整份研究 PDF 並自行解讀。建立精簡、可追蹤的 Research Requirements（研究工程要求）。

## Create

`doc/research/RESEARCH_REQUIREMENTS.md`

建議每項要求使用 ID：

```text
RES-001 Bullishness Index
RES-002 Agreement Index
RES-003 Lagged log returns
RES-004 RSI-14
RES-005 Rolling volatility 5/20
RES-006 Sentiment lag 1/3/5
RES-007 Walk-forward validation
RES-008 Information Coefficient
RES-009 Sharpe / risk-adjusted evaluation
```

每一項標示：

- Evidence（研究依據）
- Classification：Required / Candidate / Hypothesis / Background
- Engineering implication（工程含義）
- Affected module（影響模組）
- Verification（驗證方式）
- Status（尚未實作／已實作／部分實作／已驗證）

## Important

不要把研究報告中的強烈敘述直接當成 project truth（專案真理）。研究中也包含 replication concerns（重現性爭議）與 overfitting warning（過度擬合警告），必須保留這種不確定性。

## Gate 6 Done When

**Codex 能從一份精簡文件知道哪些研究結論要轉成工程要求，以及哪些仍只是待驗證假設。**

---

# Gate 6 — Documentation Reconciliation（文件對齊）

## Goal

消除 PRD、SDD、Research、歷史 Gemini 回顧文件與實際 Repository 的不一致。

## Create / Maintain

```text
doc/engineering/
├── DECISIONS.md
├── CHALLENGES.md
├── TRACEABILITY.md
└── PROJECT_STATUS.md
```

## Required Updates

### PROJECT_STATUS.md

以 Repository 實際狀態為準，清楚標示：

- Completed（已完成）
- Partial（部分完成）
- Planned（規劃中）
- Deprecated / Replaced（已淘汰／被替代）

例如：

- `trend_discover.py`：Code 已存在，不應再在 SDD 標「規劃中」。
- `feature_aggregator.py`：MVP 已存在，但 Research-aligned feature set 尚未完成。
- `src/ml/`：Phase 3 model 尚未完成。
- `src/app/`：Phase 4 dashboard 尚未完成。

### DECISIONS.md

將 Phase 1/2 有價值的既有決策轉成正式記錄，例如：

- Multi-source pipeline（多來源管線）
- yfinance + TWSE
- Pushdown filtering first（先關鍵字過濾）
- ETL modularization（ETL 模組化）
- Config as Data（設定即資料）
- Soft Delete（軟刪除）
- SQL + Pandas hybrid feature engineering
- MVP before full-market expansion

### CHALLENGES.md

整理現有挑戰，例如：

- `__pycache__` 誤解（可視價值決定是否保留）
- PostgreSQL bind mount permission
- duplicate writes / idempotency
- TPEx experiment / WAF / JSON decode
- schema mismatch
- 新 Audit 發現的 checkpoint semantics、cache semantics、DB error semantics

### TRACEABILITY.md

建立：

`Research / PRD → Requirement → SDD / ADR → Code → Test → Evidence`

## Gate 6 Done When

**Codex 不需要猜目前真實進度；成果簡報也有可靠的工程歷程來源。**

---

# Gate 7 — Phase 3 Readiness Review（Phase 3 就緒審查）

在開始模型前，回答以下問題：

- [ ] Schema 可重建且一致。
- [ ] DB failure / empty semantics 已分離。
- [ ] NLP checkpoint / cache 有測試。
- [ ] Soft Delete 正確。
- [ ] Canonical Stock ID 已定義。
- [ ] Prediction Time Convention 已核准。
- [ ] Research requirements 已抽取。
- [ ] Feature table 所需欄位與目標已明確。
- [ ] Minimal Test Safety Net 已存在。
- [ ] Git baseline 乾淨。
- [ ] PRD / SDD / PROJECT_STATUS 已同步。

全部通過後，才進入：

# Phase 3 — Research-Driven ML Development（研究驅動的機器學習開發）

建議順序：

1. 建立 target label（例如下一交易日上漲／下跌）。
2. 補齊必要 feature engineering。
3. 建立 simple baseline model（簡單基準模型），例如 majority class / logistic regression，作為比較基準。
4. Random Forest。
5. XGBoost（若決定納入且依賴合理）。
6. Walk-Forward Validation。
7. 指標：Accuracy、Precision、Recall、F1、ROC-AUC（適用時）、IC，以及研究／產品需要的風險調整指標。
8. 分析「加入情緒特徵」是否真的優於只用價量特徵的 baseline。
9. 保留 out-of-sample（樣本外）結果，不得只展示最佳歷史區間。
10. 將結果寫入 Dashboard 所需的 prediction/evaluation data contract。

---

# 2. Suggested Codex Task Sequence（建議 Codex 任務順序）

**不要把整份計畫一次交給 Codex 並要求全部執行。**

建議每次只處理一個 Gate：

```text
Task 1 → Gate 0：安全與 Git baseline 檢查 (CLOSED)
Task 2 → Gate 1：統一 Database schema 與 DDL 單一真實來源 (CLOSED)
Task 3 → Gate 2：修復 failure / checkpoint / cache 失敗語意 (CLOSED)
Task 4 → Gate 3：修復 soft delete / stock ID / TPEx 文件對齊 (CLOSED)
Task 5 → Gate 4：時間對齊與防前視偏誤 (雙模式預測架構 + 測試安全網) (ACTIVE)
Task 6 → Gate 5：Research requirements 抽取與特徵工程
Task 7 → Gate 6：文件全對齊 (DECISIONS / CHALLENGES / TRACEABILITY)
Task 8 → Gate 7：Phase 3 readiness review
Task 9 → Phase 3 第一個最小 ML increment
```

每個 Task 完成後：

1. 看 Codex 的 plan。
2. Review diff。
3. 跑 tests。
4. 確認沒有資料破壞。
5. 記錄有價值的 decision / challenge。
6. 再 commit。
7. 才開下一個 Task。

---

# 3. First Codex Session — Recommended Scope（第一次 Codex 工作範圍）

第一次不要讓 Codex修改 business logic（業務邏輯）。

建議第一次只做 Read-only Verification（唯讀驗證）：

- 讀 `AGENTS.md`
- 讀 `PRE_CODEX_REMEDIATION_PLAN.md`
- 讀 PRD / SDD
- 掃描 Repository
- 檢查 Git status
- 驗證 Gate 0 的實際狀態
- 提出「只針對 Gate 0」的執行計畫
- 不修改檔案
- 不執行 DB destructive command
- 不讀出 `.env` 的秘密值

等你 review 這份計畫後，再給 Codex寫入權限做 Gate 0。

---

# 4. Skills Strategy（Skills 策略）

**現在先不要建立大量 Skills。**

等至少完成 Gate 4，並實際使用 Codex 幾輪後，再觀察哪些流程重複出現。

可能值得抽成 Skill 的候選：

### `project-retrospective`

用途：分析本次 diff / tests / issue，判斷是否需要更新 `DECISIONS.md` 或 `CHALLENGES.md`。

### `financial-ml-validation`

用途：檢查 time-series split、look-ahead bias、feature availability、baseline、evaluation metrics。

### `etl-safety-review`

用途：檢查 idempotency、retry、checkpoint、database error semantics、data contract。

只有在流程已經證明會反覆使用時才抽成 Skill；不要建立 `python-skill`、`postgres-skill` 這類只重複通用知識的 Skill。

---

# 5. Milestone Definition（里程碑）

## Milestone A — Safe for Codex

Gate 0–4 完成：

> Agent 可以安全修改 ETL / NLP，而有 Git 與 tests 保護。

## Milestone B — Safe for ML

Gate 5–8 完成：

> 時間、資料契約、Research requirements 與文件已對齊，可以開始 Phase 3。

## Milestone C — Portfolio-ready ML MVP

- 一套可重現的 feature pipeline
- baseline vs sentiment-enhanced model comparison
- walk-forward evaluation
- 可解釋的結果
- 有失敗／限制說明
- 有 Decisions / Challenges evidence

## Milestone D — Final Demo

- Streamlit / BI Dashboard
- 本機 development database 與 cloud deployment strategy 分離
- 可重現 setup
- 簡報可直接引用的 architecture、metrics、decisions、challenges、limitations

---

# 6. Success Criteria（整頓成功標準）

Codex 導入成功不是「Agent 寫了很多程式」。

真正成功是：

> **每個 Agent 修改都有清楚的規格來源、可 review 的 diff、可執行的驗證、可回復的 Git 基線，而且重要工程思考能自然累積成最終作品與面試證據。**
