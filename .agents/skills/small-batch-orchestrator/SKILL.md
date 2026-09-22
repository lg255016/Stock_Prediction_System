---
name: small-batch-orchestrator
description: >-
  Use this skill to orchestrate software engineering phases using the Plan-Before-Code Small Batch workflow.
  Guides reading PRD/SDD requirements, decomposing them into 3-4 independent testable small batches,
  enforcing TDD (tests before implementation), managing status sync in PROJECT_STATUS.md, and executing closure reviews.
---

> ## [DEPRECATED] 本 Skill 已遷移
>
> **現行版本：`.claude/skills/small-batch-orchestrator/SKILL.md`**
>
> **本路徑（`.agents/skills/`）不會被 Claude Code 載入**，因此本檔實際上並未生效。
> 本檔保留為歷史錨點，內文未更新，**不得作為現行 SOP 依據**。
>
> 既有文件中指向本路徑的引用，改寫作業排入 `UG-G1-SB5`。
> **建立依據**：GOV-01 治理層例外授權，2026-08-23。

---

# Small Batch Orchestrator Skill

本 Skill 定義「小批次工程治理與交付循環（Small Batch Lifecycle）」的標準作業程序（SOP）。
適用於中大型專案、具備 PRD/SDD 規格之多階段開發，以及需要杜絕範圍蔓延（Scope Creep）的敏捷工程流程。

---

## 1. 核心原則 (Core Invariants)

1. **先規劃後實作 (Plan-Before-Code)**：未經 Human 批准計畫前，維持唯讀狀態，嚴禁修改業務代碼。
2. **小批次拆解 (Small Batch Breakdown)**：每個 Phase 必須拆解為 3~4 個獨立可測、風險隔離的 Small Batches（例如：SB1 ➔ SB2 ➔ SB3 ➔ SB4）。
3. **測試安全網優先 (Test Safety Net First)**：新增功能或修正 Bug 時，必須同步建立/更新對應之單元與邊界測試。
4. **全套測試零容忍 (100% Test Pass Guarantee)**：每次交付前，全套測試套件必須 100% 通過（Ran N tests, OK）。
5. **單一真實狀態 (Single Source of Project State)**：每個 Small Batch 完成後，即時同步更新 `PROJECT_STATUS.md`。

---

## 2. 標準作業流程 (Standard Operating Procedure)

### 階段一：Phase 啟動與計畫起草 (Phase Inception & Planning)
1. **讀取規格真實來源**：
   - 研讀 `PRD`（要做什麼）、`SDD`（怎麼設計）、理論研究（若有）與當前代碼基準。
2. **起草實作計畫書 (`PHASE_X_PLAN.md`)**：
   - 明確本階段核心使命與範圍邊界（宣告嚴格禁止事項與不可違反原則）。
   - 拆解 3~4 個 Small Batches（定義各 Batch 的交付模組、預計新增測試與驗證標準）。
   - 定義資料契約（Data Contracts）與檔案路徑。
3. **提請 Human 審批**：
   - 呈報實作計畫書並請求正式授權，未獲核准前不更動代碼。

---

### 階段二：小批次執行循環 (Small Batch Execution Loop)
對每個核准的 Small Batch（SB-k）：

1. **Step 1: 建立/更新專項測試 (`tests/test_*.py`)**：
   - 針對該批次的邊界條件、異常輸入、資料隔離與核心演算法撰寫單元測試。
2. **Step 2: 實作生產程式碼 (`src/...`)**：
   - 遵循最小修改原則，只修改該批次授權之檔案路徑。
3. **Step 3: 執行全套測試套件**：
   - 執行 `python -m unittest discover -s tests -v`。
   - 確認所有歷史測試與新增測試全數通過（無任何 ERROR 或 FAIL）。
4. **Step 4: 同步專案狀態檔 (`PROJECT_STATUS.md`)**：
   - 更新 Section 1（Current Phase / Active Batch 狀態設為 `COMPLETE`）。
   - 更新 Section 13/14（記錄本次批次交付重點與下一個 Next Action）。
5. **Step 5: 產出小批次成果簡報**：
   - 向 Human 條列本次交付成果、測試矩陣與 Working Tree，提請驗收並申請下一個 Small Batch 授權。

---

### 階段三：階段結案與提交 (Phase Closure & Commit)
當所有 Small Batches（SB1 ~ SB4）均完成後：

1. **全系統回歸驗證**：
   - 執行全套自動化測試套件（確認毫秒級極速通過）。
   - 檢查靜態語法 `python -m py_compile` 與 `git diff --check`。
2. **工程資產對齊**：
   - 檢查本次變更是否產生重大架構決策（調用 `portfolio-evidence-sync` 更新 `DECISIONS.md`）。
   - 檢查是否遇到非瑣碎技術挑戰（調用 `portfolio-evidence-sync` 更新 `CHALLENGES.md`）。
   - 同步 `PROJECT_STATUS.md` 將該 Phase 標記為 `CLOSED`。
3. **呈報 Final Phase Review 報告**：
   - 列出所有交付模組、測試分佈與 Closure Commit 檔案清單。
4. **執行 Closure Commit**：
   - 獲得 Human 明確授權後，執行標準規範提交（例如：`feat(phaseX): ...`），確保 working tree 乾淨無殘留。
