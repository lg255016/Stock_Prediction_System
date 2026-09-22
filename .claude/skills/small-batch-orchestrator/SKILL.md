---
name: small-batch-orchestrator
description: >-
  Use this skill to plan, execute, and close Gates and Small Batches under this project's Gate
  governance model. Enforces Plan-Before-Code (read-only until PO approves), Small Batch decomposition
  driven by the approved roadmap rather than a fixed batch count, per-Gate Brief completeness tiers,
  status sync to the authoritative status document, and contract-check as a Small Batch exit condition.
---

# small-batch-orchestrator — Gate 與 Small Batch 治理

本 Skill 定義 Gate／Small Batch（SB）的規劃、執行循環與結案程序。

**適用模型**：本專案採 **Gate → Small Batch** 治理結構（非 Phase 模型）。
Gate 與 SB 的權威定義見 `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`
與 `doc/governance/TEAM_PLAYBOOK.md`。

---

## 1. 核心不可違反原則

1. **Plan-Before-Code**：未經 PO 批准前維持唯讀，嚴禁修改業務程式碼。
2. **拆解依循已核准路線圖**：SB 的數量與邊界**由已核准的 Master Plan 決定**，
   不由本 Skill 規定固定數量。新增或合併 SB 屬 scope 變更，需 PO 批准。
3. **測試安全網優先**：新增功能或修正 Bug 時同步建立／更新對應測試。
4. **驗證邊界必須揭露**：測試通過時必須同時揭露環境依賴狀態
   （見 `CLAUDE.md` §13.3 與 `gate-submit` skill）。
5. **單一狀態來源**：SB 完成後同步更新 `doc/governance/PROJECT_STATUS.md`。
6. **一次一個 SB**：完成一個 SB 後**停止**，回報並等待 PO 授權下一個。
   嚴禁自動連續執行多個 SB 或跨 Gate 推進。

---

## 2. Brief 完整度分級

SB Brief 的欄位要求**依 Gate 與實作距離分級**。
各 Gate 的實際欄位清單以 `SYSTEM_UPGRADE_MASTER_PLAN.md` 對應章節為權威。

| Gate 位置 | Brief 要求 | 理由 |
|-----------|-----------|------|
| **下一個要執行的 Gate** | 完整 Brief（含 Requirement Source、Current State、Data/API/Schema Contract、Failure Semantics、Risks & Trade-offs、E2E Verification、Documentation Sync、Gate A/B 等） | 即將開工，決策必須完整 |
| **後續 Gate** | 核心欄位（Goal、Dependency、In Scope、Out of Scope、Affected Components、Tests、Definition of Done、Rollback） | 保留設計意圖，細節於該 Gate 規劃階段補齊 |

**規則**：

- 各 Gate 開工前，該 Gate 的所有 SB 必須先補成完整 Brief 並經 PO 審查。
- 不得以「後續 Gate 只需核心欄位」為由，在開工時仍使用簡略 Brief。

---

## 3. 標準作業流程

### 階段一：Gate 啟動與規劃

1. **讀取權威來源**

   ```bash
   # 目前進度與已關閉的 Gate
   sed -n '1,40p' doc/governance/PROJECT_STATUS.md
   # 本 Gate 的 SB 清單與依賴矩陣
   grep -n "UG-Gate\|UG-G[0-9]-SB" doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
   ```

   另讀 `CLAUDE.md`（工程不變量）、相關已核准 ADR、PRD／SDD。

2. **確認 Gate 准入條件成立**

   前一個 Gate 必須已由 PO 正式關閉。查 `PROJECT_STATUS.md` 與 Master Plan 的准入條件欄。

3. **確認高風險項目已簽核**

   ```bash
   grep -n "High" doc/upgrade/contracts/REMAINING_RISKS.md
   ```

   依 `REMAINING_RISKS.md` 的風險接受準則，High 風險需 PO 明確簽核才可開工。

4. **提請 PO 授權**

   呈報本 Gate 的 SB 清單、範圍邊界、風險與驗證計畫。**未獲核准前不動任何程式碼。**

### 階段二：Small Batch 執行循環

對每個**已獲 PO 授權**的 SB：

1. **建立／更新測試**（`tests/test_*.py`）
   針對邊界條件、異常輸入、資料隔離與核心演算法。

2. **實作**
   遵循最小修改原則，**只修改該 SB Brief 中列明的檔案路徑**。
   發現範圍外問題時停手並回報，不得順手修改。

3. **執行 SB 完成條件檢查**

   ```bash
   # 全套測試
   python -m unittest discover -s tests -p "test_*.py"

   # 跨文件契約驗證（涉及規格或資料契約的 SB 必跑）
   python scripts/verify/gate0_contract_check.py
   ```

   **兩者皆須通過**才算 SB 完成。contract-check exit 非 0 即為未完成。

4. **同步狀態**
   更新 `doc/governance/PROJECT_STATUS.md`：目前 Gate／SB 狀態、本次交付重點、下一步。

5. **文件同步檢查**
   若本 SB 產生架構決策或非瑣碎技術挑戰，啟動 `evidence-sync` skill
   建立 ADR／Challenge，**並執行其傳播清單**。

6. **產出 SB 成果報告並停止**
   啟動 `gate-submit` skill 產出五項強制證據。
   **回報後停止，等待 PO 驗收與下一個 SB 授權。**

### 階段三：Gate 結案

該 Gate 所有 SB 完成後：

1. **全系統回歸**

   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   python scripts/verify/gate0_contract_check.py
   git diff --check
   ```

2. **工程資產對齊**
   確認 ADR／Challenge 已建立且傳播完成；`PROJECT_STATUS.md` 標記該 Gate 待關閉。

3. **呈報 Gate Closure Review**
   依 `gate-submit` skill 產出完整證據，含未驗證範圍與剩餘風險。

4. **等待 PO 裁決**
   Gate 關閉是 **PO 專屬權限**（`TEAM_PLAYBOOK.md` §2）。
   Agent 只能提出 recommendation，不得自行宣稱 Gate 已關閉。

5. **獲授權後才 commit**
   Commit 範圍限於 PO 明確授權的檔案清單。

---

## 4. 失敗範例（本 Skill 必須能擋下的東西）

### 失敗範例 A：自行決定 SB 數量

> ❌ 「本 Gate 我拆成四個 SB 執行。」（Master Plan 定義的是五個）

**為何 FAIL**：SB 邊界由已核准的 Master Plan 決定。自行增減屬未授權的 scope 變更。

**偵測**：

```bash
grep -c "^#### UG-G1-SB" doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
```

實際 SB 數與回報數不符即為違規。

### 失敗範例 B：連續執行多個 SB 不停止

> ❌ 「SB1 到 SB3 都已完成，測試全過，請驗收。」

**為何 FAIL**：違反原則 6。每個 SB 完成後必須停止並取得 PO 授權才進入下一個。
PO 失去逐批攔截的機會。

### 失敗範例 C：SB 完成但未跑 contract-check

> ❌ 「測試 OK，SB 完成。」（該 SB 修改了資料契約相關文件）

**為何 FAIL**：違反階段二第 3 步。單元測試不會偵測跨文件契約不一致。

**偵測**：報告中沒有 contract-check 的原始輸出。

### 失敗範例 D：Gate 自行宣告關閉

> ❌ 「所有 SB 完成，Gate N 正式關閉，進入 Gate N+1。」

**為何 FAIL**：Gate 關閉是 PO 專屬權限。正確說法是
「所有 SB 完成，提交 Gate Closure Review，等待 PO 裁決」。

---

## 5. 相關規則

- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` — Gate／SB 權威定義與 Brief 欄位
- `doc/governance/TEAM_PLAYBOOK.md` §3 — Gate 生命週期、Gate 狀態、Small Batch
- `doc/governance/TEAM_PLAYBOOK.md` §1、§2 — 實際角色與 PO 專屬批准事項
- `doc/upgrade/contracts/REMAINING_RISKS.md` — 風險接受準則
- `CLAUDE.md` §13、§14 — 測試指令與 Definition of Done
- `gate-submit` skill — 送審前自檢
- `evidence-sync` skill — ADR／Challenge 歸檔與傳播
