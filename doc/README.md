# 文件地圖（Document Map）

> **本檔用途**：回答「這份文件屬於誰、還活著嗎、該不該讀」。
> **建立依據**：GOV-05 文件分類（PO 授權，2026-08-24）。
> **規格衝突時的優先順序**：見 `CLAUDE.md` §0.2。本檔只描述**歸屬與狀態**，不定義權威順序。

---

## 1. 資料夾的意義

| 資料夾 | 歸屬 | 生命週期 | 該不該讀 |
|--------|------|---------|---------|
| `spec/` | 全專案 | 長青 | 要理解「系統要做什麼」時讀 |
| `governance/` | 全專案 | 長青 | 要知道「誰負責什麼、流程怎麼走」時讀 |
| `evidence/` | 全專案 | **只增不減** | 要查「為什麼這樣決定」時讀 |
| `research/` | 全專案 | 長青（輸入） | 要追研究依據時讀 |
| `upgrade/` | **現行升級計畫團隊** | 進行中 | **日常工作主要讀這裡** |
| `archive/` | 前任團隊 | **已結束，唯讀** | 只有考古時才讀 |
| `progress/` | 全專案 | **本機、不版控、只增不減、不維護**（GOV 決策，PO 裁決 2026-09-21，見 `DECISIONS.md` DEC-046） | 要看某個已結案 SB／小案的一頁式概念摘要時讀——**不在 repo 內，`git clone` 或另一台機器看不到** |
| `report/` | 全專案 | 長青、結果文件、凍結版 | 要看整個專案做了什麼與量到什麼時讀 |

判斷法則：**`upgrade/` 是現在正在做的事；`archive/` 是已經結束的事；其餘五個跨計畫共用。**

---

## 2. 逐份文件

### `spec/` — 產品與系統規格

| 文件 | 內容 |
|------|------|
| `PRD_Financial_Sentiment_System_v1.md` | 產品需求：要做什麼 |
| `SDD_Financial_Sentiment_System_v1.md` | 系統設計：模組責任與架構 |

### `governance/` — 治理制度（跨計畫）

| 文件 | 回答的問題 |
|------|-----------|
| `TEAM_PLAYBOOK.md` | **給下一個 Claude 團隊**：實際的角色、PO 專屬批准事項、Gate／SB 迴圈、失敗模式與環境陷阱目錄 |
| `PROJECT_STATUS.md` | 專案目前做到哪裡、哪個 Gate 已關閉 |
| `GOV_013_PROPOSAL_secret_content_scan.md` | **`APPROVED`（PO 2026-09-10）**：pre-commit 檢查 3 增加 staged 內容層秘密掃描（CHAL-008 四次同型漏洞後提出），已實作於 `CLAUDE.md` §12.4／`.githooks/pre-commit`，11 項情境驗證通過 |

> 每次工作都不能忽略的工程原則與完成標準在 `CLAUDE.md`（根目錄），不在此處。

### `evidence/` — 證據帳本（只增不減）

| 文件 | 內容 |
|------|------|
| `DECISIONS.md` | ADR（架構決策紀錄）。**狀態欄只有 PO 能改為 `APPROVED`** |
| `CHALLENGES.md` | 工程挑戰紀錄：現象、根因、失敗嘗試、解法 |
| `TRACEABILITY.md` | 追溯矩陣：理論 → PRD → SDD → ADR → 程式碼 → 測試 → 證據 |
| `DOCUMENT_DRIFT_REMEDIATION.md` | 文件漂移登錄（DRIFT-xxx）與測試封閉性缺口（HERM-xx） |

### `research/` — 研究輸入

| 文件 | 內容 |
|------|------|
| `RESEARCH_REQUIREMENTS.md` | 研究轉譯後的工程要求 |
| `ML_ACCURACY_RESEARCH_AND_SYSTEM_IMPACT_ASSESSMENT.md` | 準確率研究與系統衝擊評估（唯讀輸入） |
| `股價與情緒關聯研究.pdf` | 原始研究報告 |

### `upgrade/` — 現行升級計畫 ★

| 文件 | 內容 |
|------|------|
| `SYSTEM_UPGRADE_MASTER_PLAN.md` | **主計畫**。Gate 0–4 與全部 Small Batch 的 Brief |
| `contracts/FEATURE_REGISTRY.md` | 特徵登記表與版本化特徵契約 |
| `contracts/MULTI_SOURCE_DATA_CONTRACT.md` | 多來源資料契約與失敗語意 |
| `contracts/DB_MIGRATION_PLAN.md` | 資料庫遷移計畫與 DDL |
| `contracts/PURGED_WALK_FORWARD_SPEC.md` | Purged Walk-Forward 驗證規格 |
| `contracts/REMAINING_RISKS.md` | 已知未解風險與處置 |
| `sources/ADVANCED_ML_STRATEGY_PORTFOLIO_SPEC.md` | 進階 ML 策略規格（唯讀來源） |
| `sources/MULTI_SOURCE_SENTIMENT_AND_COMMENT_FEATURE_SPEC.md` | 多來源情緒與留言特徵規格（唯讀來源） |
| `gates/` | **審查中**的 Gate／SB 提案（見 §3） |
| `gates/closed/` | 已通過 Gate B、結論已被吸收的**過程文件**——含 SB 的 Gate A 提案／Gate B 送審，**以及已關閉 Gate 的啟動申請書**（`GATE1_STARTUP_APPLICATION.md` 於 2026-09-01 移入；`GATE3_STARTUP_APPLICATION.md` 於 2026-09-16 `UG-Gate-3` 關閉時移入）|
| `gates/evidence/` | Gate／SB 執行期產出的**原始證據檔**（JSON）。與提案分離：提案會被改寫、證據不得事後修改。首例為 `UG-G2-SB5` 的 Dcard 可用性驗證原始回應與關鍵字快照 |

### `archive/` — 已結束計畫（唯讀）

| 文件 | 所屬計畫 | 狀態 |
|------|---------|------|
| `PRE_CODEX_REMEDIATION_PLAN.md` | 前任團隊整頓計畫（Gate 0–6） | 全數 `CLOSED` |
| `PHASE3_ML_PLAN.md` | Phase 3 機器學習 | `CLOSED` |
| `PHASE4_BI_PLAN.md` | Phase 4 BI 視覺化 | `CLOSED` |
| `THEMATIC_TRENDS_PLAN.md` | 主題趨勢 | `CLOSED` |
| `REAL_ARTICLES_READING_PLAN.md` | 真實文章閱讀 | `CLOSED` |
| `AGENT_TEAM.md` | 五角色 Agent 治理模型 | **已退役**（GOV-07）。其五個交付物零產出；§4.1 已遷入 `governance/TEAM_PLAYBOOK.md` §2 |
| `WORKFLOW.md` | Gate 生命週期與 Small Batch 流程 | **已退役**（GOV-07）。§3／§4 已遷入 playbook §3；§9 Commit Policy 刪除，權威為 `CLAUDE.md` §12 |

> **`archive/` 的內容不得修改。** 這些文件記錄的是當時的計畫與當時的結構，
> 竄改它們等於竄改歷史紀錄。其中對舊路徑的引用**刻意保留原樣**。

### `report/` — 完整技術報告（結果文件，凍結版）

| 文件 | 內容 |
|------|------|
| `完整技術報告.md` | 全專案完整技術報告，v1.2，凍結於 2026-09-16 |
| `figures/` | 報告內引用的圖表（`fig15`～`fig20`、`purged_wf_timeline.png`） |
| `demo_page.html` | 單檔展示頁面 |

`spec/` 回答「要做什麼」，本資料夾回答「做出來了什麼、量到了什麼」的結果文件——
兩者責任不同，不合併。**不進 `gate0_contract_check.py` 的 `DOC_PATHS`、不建立跨文件同步
義務**；日後若要更新報告內容，直接替換整份 `完整技術報告.md`，不逐段修訂。

---

## 3. Gate／SB 提案的生命週期【強制】

**問題**：Gate 1–4 的 Small Batch 數量以 `upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 為準（**該處為唯一權威**；此處刻意不複製數字——見 `PROJECT_STATUS.md` §0.5 #5）。若每個 SB 的提案與報告都永久留在 `gates/`，
半年後這個資料夾會比整頓前的 `doc/engineering/` 更難讀 —— 分類只是把成長裝進盒子，不會讓它變少。

**規則**：

1. Gate A 提案與 Gate B 報告是**過程文件**，不是永久資產。
2. SB 通過 Gate B 後，其結論已分別被吸收進：
   - `evidence/DECISIONS.md`（決策）
   - `evidence/TRACEABILITY.md`（追溯）
   - `upgrade/contracts/`（契約變更）
   - `upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`（Brief 調整）
3. 此時該提案文件**移入 `gates/closed/`**，不再是需要閱讀的現行文件。
4. **`gates/` 根層永遠只保留正在審查中的 SB**（通常 1–2 份）。
5. **Gate 層級的啟動申請書沿用同一個生命週期**：該 Gate 關閉時移入 `closed/`。
   **不另創類別**——它與 SB 提案同樣是有日期的過程文件。
   （2026-09-01 補：原規則只為 SB 提案設計，`GATE1_STARTUP_APPLICATION.md`
   因此在 Gate 1 關閉後仍留在根層。）

> **搬移時內容一個位元組都不改。** 這些文件記錄的是**當時申請／提案了什麼**，
> 那是治理紀錄。若現行範圍已與當初不同，**加超越註記，不改原文**
> （`GATE2_STARTUP_APPLICATION.md` 即為此例：Gate 2 已由 7 個 SB 增為 9 個，
> 但文內表格保持原樣）。

要知道「現在在做什麼」，打開 `upgrade/gates/` 就是答案，不必在數十份裡翻找。

---

## 4. 不在 `doc/` 底下的治理文件

| 檔案 | 地位 |
|------|------|
| `CLAUDE.md`（根目錄） | **現行權威**。Claude Code 實際載入的專案規則 |
| `AGENTS.md`（根目錄） | 相容錨點（Deprecated）。保留因已核准 ADR 以 `§7.x` 形式引用 |
| `.claude/skills/` | 強制 SOP：`gate-submit`、`evidence-sync`、`small-batch-orchestrator`、`bug-fix-protocol` |
| `scripts/verify/gate0_contract_check.py` | 跨文件契約驗證。受驗文件路徑定義於腳本的 `DOC_PATHS` |

> **搬移 `doc/` 底下任何受驗文件時，必須同步更新 `DOC_PATHS`**，
> 否則 contract-check 失敗，pre-commit hook 會擋下所有後續 commit。
