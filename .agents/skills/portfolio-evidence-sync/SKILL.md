---
name: portfolio-evidence-sync
description: >-
  Use this skill to capture, structure, and document engineering decisions, architectural trade-offs, and technical challenges for portfolio and interview evidence.
  Standardizes recording of Architecture Decision Records (ADRs in DECISIONS.md), Engineering Challenge logs in CHALLENGES.md, and end-to-end Traceability matrices.
---

> ## [DEPRECATED] 本 Skill 已遷移
>
> **現行版本：`.claude/skills/evidence-sync/SKILL.md`**
>
> **本路徑（`.agents/skills/`）不會被 Claude Code 載入**，因此本檔實際上並未生效。
> 本檔保留為歷史錨點，內文未更新，**不得作為現行 SOP 依據**。
>
> 既有文件中指向本路徑的引用，改寫作業排入 `UG-G1-SB5`。
> **建立依據**：GOV-01 治理層例外授權，2026-08-23。

---

# Portfolio Evidence Sync Skill

本 Skill 定義「作品集決策證據（Decision Evidence）與問題解決證據（Problem-Solving Evidence）」的自動化歸檔標準。
專為資深軟體工程師、資料工程師（DE）與量化開發者打造，確保專案每一次關鍵技術選型與除錯排查歷程，都能轉化為高說服力的履歷與面試素材。

---

## 1. 核心哲學 (Core Philosophy)

> **「不要只證明程式能跑，要證明『為什麼這樣設計、放棄了哪些替代方案、做了什麼取捨、如何用數據驗證』。」**

---

## 2. 架構決策紀錄標準 (`DECISIONS.md`)

當專案涉及以下情況時，應建立一筆 `DEC-xxx` 決策紀錄：
- 架構或模組邊界劃分（如：抽象工廠、雙模式時間對齊、統一適配器）
- 技術與套件選型（如：輕量樹模型 vs 重型深度學習、純 NumPy 向量化 vs C 編譯依賴）
- 資料庫 Schema 與資料契約設計（如：Canonical Stock ID、軟刪除生命週期、18 欄位特徵契約）
- 性能、成本、可靠性或可維護性取捨（如：精確比對快取命中率提升、Strict NLP 檢查點）

### 決策標準結構模板：
```markdown
## DEC-xxx: [決策英文名稱]（決策繁體中文名稱）

- **Status**：APPROVED（已核准）
- **Date**：YYYY-MM-DD
- **Authors**：[參與角色]
- **Approved by**：Project Owner (Human)

### Context / Problem（背景／問題）
[描述面臨的核心工程挑戰、現狀矛盾或業務需求痛點]

### Alternatives Considered（考慮方案）
1. **Option A — [方案名稱]（[採納/不採納]）**：
   - 做法描述
   - 缺陷／為什麼不選
2. **Option B — [方案名稱]（[採納/不採納]）**：
   - 做法描述
   - 優勢／為什麼選它

### Decision（最終決策）
[條列具體的設計規則、介面契約與不可違反原則]

### Rationale（原因）
[說明技術選型背後的關鍵考量：如極速執行、0 GPU 依賴、高可維護性]

### Trade-offs（取捨）
[坦白列出該決策的妥協點，展現資深工程思維]

### Affected Components（影響範圍）
- `[修改之檔案路徑]`

### Verification / Evidence（驗證／證據）
[條列具體的測試數據、測試通過數量、執行毫秒數、Benchmark 或對照實驗數據]
```

---

## 3. 技術挑戰排查紀錄標準 (`CHALLENGES.md`)

當遇到非瑣碎的技術困難、隱蔽 Bug（如 Look-ahead Bias、快取穿透、時序洩漏）時，應建立一筆 `CHAL-xxx` 挑戰紀錄：

### 挑戰標準結構模板：
```markdown
## CHAL-xxx: [挑戰名稱]

- **領域類別**：[如：金融時序防護 / NLP 異常處理 / 資料庫併發]
- **嚴重等級**：[Critical / High / Medium]
- **發現階段**：[如：Gate 2 / Phase 3]

### 1. Phenomenon & Symptom（現象與症狀）
[描述系統出現的異常行為、報錯日誌或邏輯漏洞]

### 2. Impact（工程與業務影響）
[說明若不修復將導致的嚴重後果，如模型虛假高準確率、資料庫污染]

### 3. Investigation & Diagnostic Steps（排查歷程）
[展示結構化除錯思維：日誌分析、斷點調試、時序數據比對]

### 4. Root Cause Analysis（根因分析）
[深入說明問題的根本技術原因]

### 5. Failed Attempts（有價值的失敗嘗試）
[記錄嘗試過但不可行的解法及其教訓，展現深度探索歷程]

### 6. Final Solution & Architecture（最終解法）
[詳細說明採用的架構修復方案與代碼實作]

### 7. Verification & Evidence（驗證證據）
[列出專項單元測試、回歸測試與實測數據]

### 8. Lessons Learned & Portfolio Takeaway（面試精華提煉）
[一句話提煉可帶走的工程原則與面試回答亮點]
```

---

## 4. 端到端追溯矩陣維護 (`TRACEABILITY.md`)

確保系統每一項關鍵設計具備雙向追溯性（Two-Way Traceability）：
$$\text{理論研究/PRD 需求} \iff \text{系統設計 (SDD)} \iff \text{架構決策 (DEC)} \iff \text{生產代碼路徑} \iff \text{自動化測試} \iff \text{驗證證據}$$
