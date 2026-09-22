> ## [DEPRECATED] 本檔已由 `CLAUDE.md` 取代
>
> **現行權威文件為根目錄的 `CLAUDE.md`**。Claude Code 載入的是該檔，不是本檔。
>
> 本檔**內文保留不動**，作為相容錨點（compatibility anchor）：
> 已經 Project Owner 核准的 Gate 0 交付物（`DECISIONS.md` DEC-016、`FEATURE_REGISTRY.md`、
> `MULTI_SOURCE_DATA_CONTRACT.md`、`TRACEABILITY.md`、`SYSTEM_UPGRADE_MASTER_PLAN.md`）
> 以 `AGENTS.md §7.1` 形式引用本檔的工程不變量。在這些引用改寫完成前，本檔不得刪除或改動內文。
>
> `CLAUDE.md` §7 已整段承接本檔 §7 並**保留原編號**（§7.1 仍是 §7.1），
> 因此舊引用在改寫前仍可對應到正確條文。
>
> **除役條件**：`UG-G1-SB5`（文件全面校正）完成上述引用改寫後。
> **建立依據**：GOV-01 治理層例外授權，2026-08-23。

---

# AGENTS.md — 金融情緒與股價趨勢預測系統

> 本文件是本 Repository 的 Codex 長期工作規則（durable project guidance／持久專案指引）。
> 目標不是告訴 Agent 每一次要做什麼，而是定義「每一次都不能忽略的工程原則、專案脈絡與完成標準」。

## 1. Project Mission（專案使命）

本 Repository 同時具有兩個目的：

1. 建立可執行的「金融情緒與股價趨勢預測系統」，完成從資料擷取、清洗、情緒分析、資料儲存、特徵工程、機器學習到 BI 視覺化的 End-to-End（端到端）流程。
2. 作為個人轉職與成果發表作品，保留足以說明工程能力的 Decision Evidence（決策證據）與 Problem-Solving Evidence（問題解決證據）。

因此，不得只追求「程式能跑」。重要修改必須能回答：

- 為什麼要改？
- 根據哪一項 PRD / SDD / Research / 實測證據？
- 有哪些替代方案？
- 有什麼 Trade-off（取捨）？
- 如何驗證？
- 是否留下可用於成果發表與面試的工程證據？

---

## 2. Language Policy（語言規則）

與使用者溝通時：

- 預設使用繁體中文。
- 必須使用英文專業術語時，第一次出現請寫成：`English Term（中文翻譯）`。
- 後續可視上下文使用英文縮寫，但不要為了看起來專業而堆疊不必要的英文。
- 程式碼、套件名稱、API、SQL、檔名與正式技術名詞保留原文。
- 對重要工程概念，優先用容易理解的中文解釋，再補上標準英文名稱。

---

## 3. Current Development Environment（目前開發環境）

目前正式開發環境：

- VS Code
- Dev Containers
- Docker / Docker Compose
- Python
- PostgreSQL 18（Docker container）
- PostgreSQL 開發資料透過 bind mount（綁定掛載）持久化到本機 `.devcontainer/postgres-data/`

目前策略：

- Development（開發階段）：使用本機 PostgreSQL。
- Final / Deployment（最終成品／部署階段）：預計再評估 Cloud PostgreSQL（雲端 PostgreSQL）。

未經使用者明確要求：

- 不要把開發資料庫遷移到雲端。
- 不要刪除、重建、清空或修改 `.devcontainer/postgres-data/` 的實體資料檔。
- 不要以「重建環境」為理由執行破壞性資料庫操作。
- 不要假設 physical data directory（實體資料目錄）等同可攜式備份；需要備份或遷移時，優先規劃 PostgreSQL logical backup（邏輯備份，例如 `pg_dump`）。

---

## 4. Repository Sources of Truth（規格真實來源）

本專案的重要依據包括：

- `doc/spec/PRD_Financial_Sentiment_System_v1.md`：Product Requirements Document（產品需求文件），描述「要做什麼」。
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`：System Design Document（系統設計文件），描述「系統預期怎麼設計」。
- `doc/research/`：研究報告，提供金融理論、情緒量化、Feature Engineering（特徵工程）與模型驗證的研究依據。
- `doc/governance/`：團隊編制、Gate 流程與專案現況。
- `doc/evidence/`：已核准的工程決策、問題紀錄、追溯關係與文件漂移登錄（只增不減）。
- `doc/upgrade/`：現行升級計畫的主計畫、規格契約、來源規格與各 Gate/SB 提案。
- `doc/archive/`：已結束計畫的唯讀遺留文件。
- Repository source code：描述「現在實際做到了什麼」，但不能因現有程式已存在就自動視為正確規格。

### 4.1 Conflict Rule（衝突處理規則）

當文件、研究、既有決策與程式碼互相矛盾時，不得自行偷偷選一個版本當答案。

優先順序原則：

1. 使用者在目前任務中的明確指示。
2. 已明確核准的 Architecture Decision Record, ADR（架構決策紀錄）或 `doc/evidence/DECISIONS.md`。
3. PRD 對產品目標與需求的定義。
4. SDD 對架構與模組責任的定義。
5. Research Requirements（研究轉譯後的工程要求）。
6. 現有程式碼僅代表 Current State（目前狀態），不是自動的設計真理。

若高階來源之間本身矛盾：

- 停止重大實作。
- 清楚列出衝突。
- 說明可能影響。
- 提供可選方案與建議。
- 等待使用者決策，除非任務明確允許採取低風險、可逆的暫時方案。

---

## 5. Current Architecture（目前架構基線）

現有系統核心結構：

- `main_etl_pipeline.py`：`ETLPipelineManager`，負責 Orchestration（流程協調）。
- `src/extractors/`：外部資料抽取。
  - `twse_scraper.py`
  - `yfinance_api.py`
  - `ptt_scraper.py`
  - `trend_discover.py`
- `src/transform/`：資料清洗、NLP 與特徵聚合。
  - `data_cleaner.py`
  - `nlp_processor.py`
  - `feature_aggregator.py`
- `src/loaders/`：PostgreSQL 讀寫。
  - `db_writer.py`
- `database/`：資料庫 Schema 與初始化。
  - `schema.sql`
  - `init_db.py`

目前 Phase 1 / Phase 2 已有實作，但仍存在 Audit 中發現的重大缺口；不要把現況描述成完整 Production-ready（可正式上線）系統。

---

## 6. Scope Control（範圍控制）

本專案目前優先目標是完成可驗證的 End-to-End MVP（端到端最小可行產品），而不是立即擴充成全市場、企業級或大規模分散式架構。

未經使用者批准，不要主動導入下列大型變更：

- 全市場資料湖（Data Lake）重構
- 大規模 NER（命名實體辨識）架構
- RabbitMQ / Kafka 等 Message Queue（訊息佇列）
- Airflow / Prefect 等 Orchestration Platform（工作流程編排平台）
- Kubernetes
- 微服務拆分
- 雲端資料庫遷移
- 大型框架替換

如果現有架構可以透過小範圍修改完成任務，優先使用 Incremental Refactoring（漸進式重構），不要 Big Bang Rewrite（一次性全面重寫）。

---

## 7. Engineering Invariants（不可輕易違反的工程原則）

### 7.1 Database & ETL（資料庫與 ETL）

- ETL 重複執行應維持 Idempotency（冪等性）。
- Database Error（資料庫錯誤）不得被偽裝成 Empty Result（沒有資料）。
- 失敗與「真的沒有資料」必須可區分。
- 修改 Database Schema（資料庫綱要）前，先檢查 `schema.sql`、`init_db.py`、DBWriter 與所有依賴欄位的模組。
- 不得同時維護兩套互相不一致的 Schema 定義。
- 不得做 destructive migration（破壞性遷移）除非使用者明確同意，且已有備份／回復方案。
- 任何 fallback（備援）資料源都必須符合明確 Data Contract（資料契約），不得將 provider-specific ID（資料提供者專用代碼）直接當成系統唯一識別碼而未經設計。

### 7.2 NLP / Checkpoint / Cache（NLP、檢查點與快取）

- Batch Checkpointing（批次檢查點）只有在一筆工作「確實成功完成」後才能推進。
- LLM 呼叫失敗時，不得把未完成的 fallback 分數誤標示為完成，除非規格明確定義 fallback 分數就是正式結果。
- Cache Hit（快取命中）代表已取得可重用結果時，不應因分數仍落在 fuzzy range（模糊區間）而再次呼叫 LLM；若要例外，必須有版本或品質策略。
- 快取失敗、LLM 失敗與 NLP 計算失敗要能被觀測、測試與重試。

### 7.3 Tracking Keywords（追蹤關鍵字）

- `is_active = FALSE` 的 Soft Delete（軟刪除）狀態不得被 AI Trend Discovery（AI 熱門詞探索）無意重新啟用。
- 停用關鍵字不得意外改變原本的 category（分類）。
- Hard Delete（硬刪除）可能破壞 Data Lineage（資料血緣），執行前必須取得明確許可。

### 7.4 Time-Series & ML（時間序列與機器學習）

- 不得使用會讓未來資料進入訓練集的隨機時間序列切分方式。
- Phase 3 驗證應使用 Walk-Forward Validation（滾動前向驗證）或其他明確保持時間順序的方法。
- 必須防止 Look-ahead Bias（前視偏誤／未來資料洩漏）。
- 在建立 target label（目標標籤）與 feature（特徵）前，先定義 Prediction Time Convention（預測時間約定）：模型在什麼時間點做預測，可使用哪些已知資料。
- 不得只用 Accuracy（準確率）宣稱模型有效；評估方式要與研究要求、資料不平衡與實際目標相符。
- 不得因研究報告提到某演算法，就把它當成一定優於其他方法。Research Evidence（研究證據）與本專案實測結果要分開陳述。

---

## 8. Research-to-Code Discipline（研究到程式碼的轉譯規則）

Research（研究）不是直接翻譯成 Code（程式碼）。

重要研究結論應經過：

`Research Evidence → Engineering Interpretation → Requirement → Design → Implementation → Test / Measurement`

對每一項研究驅動的重大修改，至少說明：

- 研究指出什麼？
- 它是否真的適用本專案資料與市場？
- 這是 Required（必要要求）、Candidate（候選方案）、Hypothesis（待驗證假設）還是 Background（背景知識）？
- 程式中的哪個模組負責？
- 如何用測試、benchmark（基準測試）或實驗驗證？

若證據不足，不得把 Engineering Judgment（工程判斷）寫成「學術已證明」。

---

## 9. Portfolio Evidence Policy（成果發表證據規則）

本專案最終需要成果簡報與面試說明，因此重要工程歷程必須被保留。

### 9.1 Meaningful Decision（值得紀錄的決策）

當任務涉及以下情況之一，應更新 `doc/evidence/DECISIONS.md`（若檔案尚不存在，依整頓計畫建立）：

- 架構或模組邊界
- Database Schema / Data Contract
- 技術、套件或模型選型
- SQL vs Pandas 等合理替代方案
- 性能、成本、可靠性或可維護性取捨
- fallback / retry / idempotency 策略
- ML 驗證方法
- Scope（範圍）與 Scalability（擴展性）取捨

紀錄內容至少包含：

- Context / Problem（背景／問題）
- Alternatives Considered（考慮方案）
- Decision（最終決策）
- Rationale（原因）
- Trade-offs（取捨）
- Affected Components（影響範圍）
- Verification / Evidence（驗證／證據）
- Remaining Risks（剩餘風險）

### 9.2 Meaningful Challenge（值得紀錄的困難）

當遇到非瑣碎的技術困難時，應更新 `doc/evidence/CHALLENGES.md`。

紀錄內容至少包含：

- Symptom（現象）
- Impact（影響）
- Investigation（排查過程）
- Root Cause（根因）
- Failed Attempts（有學習價值的失敗嘗試）
- Solution（解法）
- Verification（驗證方式）
- Lesson Learned（學到什麼）

不要為每個小 syntax error（語法錯誤）製造一筆文件；只紀錄能展示工程判斷、系統理解或除錯能力的事件。

---

## 10. Evidence & Claim Discipline（證據與描述紀律）

文件、README、成果簡報素材與程式註解都不得用沒有驗證依據的絕對說法。

避免在沒有證據時使用：

- 100% reliable
- perfect
- enterprise-grade
- production-ready
- guaranteed
- completely prevents
- 永遠不會
- 完美解決
- 100% 符合

請區分：

- Verified（已驗證）
- Observed（已觀察）
- Inferred（推論）
- Assumed（假設）
- Planned（規劃中）

任何「改善效能／可靠性／準確率／成本」的主張，應盡可能提供 test result（測試結果）、benchmark（基準數據）、log（紀錄）或明確 Measurement Plan（量測計畫）。

---

## 11. Repository Safety（Repository 安全規則）

- 不要讀出、回傳、commit 或顯示 `.env` 中的 secret value（秘密值）。
- 不要 commit API key、token、password 或其他 credential（憑證）。
- `.env` 僅用於本機秘密設定；公開範例使用 `.env.example`。
- `.devcontainer/postgres-data/` 不得 commit。
- 不要修改 `.git/` 內部檔案。
- 未經使用者明確要求，不要 force push、rebase public history、reset --hard 或刪除 branch。
- 需要新增 production dependency（正式依賴套件）時，先說明原因與替代方案；大型或關鍵依賴應先取得使用者同意。

---

## 12. Working Method（工作方式）

### 12.1 Before Coding（開始寫程式前）

對任何非微小修改：

1. 讀取本 `AGENTS.md`。
2. 找到相關 PRD / SDD / Research / engineering docs。
3. 檢查實際 implementation（實作）與 tests（測試）。
4. 確認目前 Git diff，避免覆蓋使用者未完成工作。
5. 用簡短方式說明：
   - Goal（目標）
   - Current State（目前狀態）
   - Proposed Change（建議修改）
   - Risks（風險）
   - Verification（驗證）
6. 任務複雜或規格不明確時，先 Plan（規劃），不要直接大量改 Code。

### 12.2 During Coding（修改過程）

- 優先 Small Batch（小批次）修改。
- 一次只解一個主要問題。
- 保持修改可測試、可回滾、可 review（審查）。
- 不要順手進行與任務無關的大規模 cleanup（清理）或 refactor（重構）。
- 發現額外問題時，記錄為 follow-up（後續事項），除非它阻塞目前任務。

### 12.3 After Coding（修改完成後）

至少：

1. 執行與修改相關的 tests / checks。
2. 檢查 regression risk（回歸風險）。
3. `git diff` review（差異檢查）。
4. 說明變更檔案與原因。
5. 確認 PRD / SDD / Research / engineering docs 是否需要同步。
6. 若產生 meaningful decision 或 challenge，更新對應文件。
7. 未通過驗證時不得宣稱 Done（完成）。

### 12.4 Bug Troubleshooting & Fixing Protocol（錯誤排查與修復協議）

當排查問題或修復 Bug 時，必須依循 `interactive-bug-fix-protocol` Skill 之 4 步驟嚴格作業：

1. **先診斷回報，絕對不私自改代碼**：深入排查日誌與代碼，向使用者回報：
   - 問題根因在哪裡（Where & Why）
   - 預計如何修正（Proposed Fix）
   - 潛在影響與副作用評估（Impact & Risks）
   - 預計測試與驗證方式（Verification Plan）
   - **🛑 停止動作，等待 Human 批准；未獲准前嚴禁修改檔案！**
2. **核准後精確實作與測試**：依核准方案修改代碼，新增防回歸測試，確保全套測試 100% PASS。
3. **成果回報與請求 Commit 授權**：回報修改差異摘要與測試通過數據，**🛑 停止動作，請求 Human 授權 Commit**。
4. **授權後提交**：僅在 Human 明確同意後方可執行 Git Commit。

---

## 13. Testing Policy（測試政策）

目前 Repository 的 Automated Test Suite（自動化測試套件）尚未成熟，因此：

- 在大量 Agent-driven refactoring（Agent 驅動重構）前，優先建立 Minimal Test Safety Net（最小測試安全網）。
- 新增 bug fix（錯誤修正）時，若可行，應先建立會重現問題的測試，再修復。
- 測試不應依賴真實 Gemini API 或不可控制的外部網站作為唯一驗證方式；優先 mock / fixture（模擬／測試資料）。
- Integration Test（整合測試）需要 PostgreSQL 時，必須避免破壞開發用真實資料。
- 測試資料庫與本機實際開發資料要明確隔離。

在建立正式測試命令後，應回來更新本節，列出準確的 test / lint / run commands。

---

## 14. Known Pre-Codex Risks（已知導入前風險）

以下問題已在 Codex 導入前 Audit 中辨識，未完成前不要直接跳進大規模 Phase 3 模型開發：

1. `database/schema.sql` 與 `database/init_db.py` 不一致。
2. NLP Batch Checkpointing 可能在 LLM 失敗時將未真正完成的資料推進 checkpoint。
3. `sentiment_cache` 對 0.4–0.6 中立／模糊分數可能再次呼叫 LLM，削弱 cache 的意義。
4. DB read error 可能被 `fetch_data()` 轉成 empty DataFrame，讓上層誤判「沒有資料／已完成」。
5. Soft Delete 決策尚未完整落實；AI discovery 可能重新啟用已停用 keyword，停用操作也可能改變 category。
6. TPEx fallback 的歷史文件與目前實際 Repository 不一致。
7. Feature Engineering 目前僅是 MVP，尚未完整實作研究要求的 Bullishness Index、Agreement Index、lagged returns、RSI、rolling volatility、sentiment lags 等。
8. 股票識別碼尚未建立清楚的 Canonical Stock ID（標準股票 ID）與 provider symbol（供應商代碼）區分。
9. PTT 文章時間與交易日對齊缺乏明確 Prediction Time Convention。
10. Automated Tests（自動化測試）不足。
11. 目前 Git working tree 並非乾淨基線；開始 Agent 大量修改前應建立可回復的 Pre-Codex Baseline。

詳細順序見 `PRE_CODEX_REMEDIATION_PLAN.md`。

---

## 15. Definition of Done（完成定義）

一個非微小任務只有在以下條件成立時才算 Done：

- 行為符合已確認的 requirement（需求）。
- 相關測試或可接受的驗證已通過。
- 沒有已知未說明的資料破壞風險。
- 沒有偷偷改變 public behavior（對外行為）或 Database Schema。
- 相關文件已同步，或明確說明為什麼不需要更新。
- 有意義的 Decision / Challenge 已留下證據。
- 最終摘要明確區分「已驗證」與「尚未驗證」。

對 ML 任務額外要求：

- 時間順序與資料可用時間已明確。
- 無已知 Look-ahead Bias。
- Evaluation（評估）不只依賴單一 Accuracy。
- 結果能與合理 baseline（基準模型）比較。

---

## 16. Initial Agent Behavior（Codex 導入初期規則）

在 `PRE_CODEX_REMEDIATION_PLAN.md` 的 Gate 0–Gate 4 完成前：

- 不要開始大規模 Phase 3 Model Training implementation（模型訓練實作）。
- 不要建立大量 Skills。
- 不要大規模重構 Repository。
- 優先完成：可回復基線、Schema 一致性、錯誤語意、Checkpoint / Cache、Soft Delete、Canonical ID、時間對齊規格、最小測試安全網與文件同步。

每完成一個 Gate，先讓使用者 review（審查）結果，再進下一個 Gate。
