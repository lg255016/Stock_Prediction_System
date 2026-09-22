---
name: evidence-sync
description: >-
  Use this skill when creating or modifying an Architecture Decision Record (DECISIONS.md),
  logging an engineering challenge (CHALLENGES.md), or updating the traceability matrix
  (TRACEABILITY.md). Enforces Proposed-by-default ADR status (only the Project Owner may set
  APPROVED), and provides the mandatory propagation checklist so an ADR change does not leave
  stale copies of the same contract in other governance documents.
---

# evidence-sync — 決策與挑戰證據歸檔

本 Skill 定義 ADR（架構決策紀錄）、Challenge（工程挑戰紀錄）與 Traceability（追溯矩陣）的
建立、修改與**跨文件傳播**程序。

**核心哲學**：不要只證明程式能跑，要證明「為什麼這樣設計、放棄了哪些替代方案、
做了什麼取捨、如何用數據驗證」。

---

## 1. ADR 狀態規則【最重要】

### 1.1 一律預設 Proposed

新建或修改 ADR 時，`狀態` 欄位**一律填 `Proposed`**。

> **只有 Project Owner 可以把狀態改為 `APPROVED`。**
> Agent 不得自行填寫 `APPROVED`，也不得代 PO 填寫 `Approved by` 或核准日期。

| 狀態 | 誰可以設定 | 意義 |
|------|-----------|------|
| `Proposed` | Agent（預設） | 已撰寫，待 PO 審查 |
| `APPROVED` | **僅 PO** | PO 已核准，附 `Approved by` 與核准日期 |
| `Superseded by DEC-xxx` | 僅 PO | 已被後續決策取代 |
| `Rejected` | 僅 PO | PO 明確否決 |

### 1.2 ADR 模板

```markdown
## DEC-xxx：[決策名稱]

- 日期：YYYY-MM-DD
- 狀態：Proposed（[觸發來源] — 待 PO 核准後生效）
- 觸發 Gate：[Gate / SB 編號]

### Context（背景）
[面臨的工程挑戰、現狀矛盾或需求痛點]

### Problem（問題）
[若不決策會發生什麼]

### Alternatives Considered（考慮方案）
1. **方案 A**：做法／為什麼不選
2. **方案 B**：做法／為什麼選它
3. **方案 C**：做法／為什麼不選

### Decision（決策）
[條列具體的設計規則、介面契約與不可違反原則]

### Rationale（理由）
[技術選型背後的關鍵考量]

### Trade-offs（取捨）
[坦白列出妥協點]

### Affected Components（影響範圍）
- `[檔案路徑]`

### Verification（驗證）
- [ ] [具體可執行的驗證項目]

### Remaining Risks（剩餘風險）
[已知但未解決的風險，含嚴重度]

### 證據文件
`[對應的規格文件路徑與章節]`
```

**模板規則**：

- **不得在模板或範例中填入具體數字**（如欄位數、斷言數、測試數）。
  這類數字屬於**規格文件的權威值**，ADR 應以「見 `<文件>` §x」形式引用。
  歷史教訓：舊版 skill 的 ADR 範例把當時的特徵契約數字直接寫進範例文字，
  該數字後來成為 `DRIFT-001`／`DRIFT-007` 追蹤的過期值，並經由複製擴散到多份文件。
- `Verification` 欄位必須是**可執行的檢查項**，不是「已驗證」的宣稱。

---

## 2. ADR 傳播清單【建立或修改 ADR 後必做】

> **一份 ADR 改了，其他文件對同一契約的敘述不會自己跟著改。**

ADR 建立或修改後，**必須逐項檢查**以下同步位置。任一遺漏都會造成跨文件契約衝突。

| # | 同步位置 | 檢查什麼 |
|---|---------|---------|
| 1 | `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | 對應章節的規格敘述、Gate/SB Brief、ADR 清單（§15）、送審確認清單（§19） |
| 2 | `doc/upgrade/contracts/FEATURE_REGISTRY.md` | 若涉及特徵或欄位契約：登記表、契約總覽、測試斷言章節 |
| 3 | `doc/upgrade/contracts/DB_MIGRATION_PLAN.md`（含 SQL 內的註解） | 若涉及 Schema：DDL 語句本身**與 SQL 註解中的「契約來源」引用** |
| 4 | `doc/evidence/TRACEABILITY.md` §3.2 | ADR 快速索引的條目內容與狀態 |
| 5 | `doc/evidence/TRACEABILITY.md` §3A / §3A.1 | 交付物追溯矩陣與 PO 決策鏈中的 ADR 標記 |
| 6 | `SYSTEM_UPGRADE_MASTER_PLAN.md` §19.1 收尾程序 | PO 核准後要改狀態的 ADR 清單是否包含本 ADR |
| 7 | 其他 Gate 0 交付物 | 是否有引用本 ADR 或其契約值 |

### 2.1 為何需要這份清單

V8 審查時 PO 發現 `C-1`～`C-4` 四項缺陷：規格層（`FEATURE_REGISTRY.md`、`DB_MIGRATION_PLAN.md`）
已更新為新契約，但治理層（`DECISIONS.md` 的 ADR 內文、`TRACEABILITY.md` 的索引）
仍寫舊值。成因就是**只改了規格文件，沒有跑傳播清單**。

`C-5` 更嚴重：`§19.1` 的核准後收尾程序漏列新增的 ADR，
若照該程序執行，那些 ADR 會永遠停在 `Proposed`。

### 2.2 傳播後驗證

```bash
python scripts/verify/gate0_contract_check.py
```

該腳本含反查檢查，會偵測「被引用但不存在的欄位」與「跨文件契約數字不一致」。
**傳播完成後必須重跑並確認 exit 0。**

---

## 3. Challenge 紀錄（`CHALLENGES.md`）

遇到**非瑣碎**技術困難時建立 `CHAL-xxx`。

**建立門檻**：涉及架構彈性、限速、快取、並發、資料契約、時序洩漏等能展示工程判斷的問題。
單純拼寫錯誤或語法錯誤**不需要**建立。

```markdown
## CHAL-xxx：[挑戰名稱]

- 領域類別：[如：金融時序防護 / NLP 異常處理 / 資料契約]
- 嚴重等級：[Critical / High / Medium]
- 發現階段：[Gate / SB 編號]

### Phenomenon（現象）
[異常行為、報錯日誌或邏輯漏洞]

### Impact（影響）
[若不修復會導致什麼後果]

### Investigation（排查歷程）
[結構化除錯思維：日誌分析、時序比對、假設驗證]

### Root Cause（根因）
[真正的成因，不是表象]

### Failed Attempts（有學習價值的失敗嘗試）
[試過但不work的方案，及為什麼]

### Solution（解法）
[實際採用的修復方式]

### Verification（驗證）
[可重跑的驗證指令與結果]

### Lesson Learned（學到什麼）
[可推廣的原則]
```

---

## 4. Traceability 維護（`TRACEABILITY.md`）

追溯鏈：`理論/PRD → SDD → ADR → 程式碼 → 測試 → 驗證證據`

### 4.1 可執行步驟

新增或修改追溯條目時，**依序執行**：

1. **確認 ADR 存在且狀態正確**

   ```bash
   grep -n "^## DEC-" doc/evidence/DECISIONS.md
   grep -A3 "^## DEC-<xxx>" doc/evidence/DECISIONS.md | grep "狀態"
   ```

2. **確認程式碼路徑存在**

   ```bash
   ls <claimed_code_path>
   ```

   若路徑尚未實作，追溯表該欄應填「待實作於 `<path>`」，不得填不存在的路徑。

3. **確認測試檔存在且測試名稱可對應**

   ```bash
   ls tests/<claimed_test_file>
   grep -n "def test_" tests/<claimed_test_file>
   ```

   尚未實作的測試填 `PLANNED`，**不得**填寫未撰寫的測試名稱並標為已驗證。

4. **標註證據狀態**

   依 `CLAUDE.md` §9 的八種標籤標註，並附重跑指令或不可重跑原因。

5. **更新 ADR 索引與交付物矩陣**

   §3.2 的 ADR 條目內容、§3A 的交付物列、§3A.1 的決策鏈標記三處都要同步。

6. **重跑契約驗證**

   ```bash
   python scripts/verify/gate0_contract_check.py
   ```

### 4.2 常見錯誤

- 填入尚未撰寫的測試名稱並標為 `VERIFIED` → 應標 `PLANNED`
- ADR 狀態在 `DECISIONS.md` 與 `TRACEABILITY.md` 不一致 → 傳播清單第 4、5 項漏做
- 追溯表引用的規格數字與權威文件不符 → 應改為「見 `<文件>` §x」而非複製數字

---

## 5. 失敗範例（本 Skill 必須能擋下的東西）

### 失敗範例 A：Agent 自行把 ADR 標成 APPROVED

> ❌ 新建 ADR 時直接寫 `狀態：APPROVED` / `Approved by: Project Owner`

**為何 FAIL**：核准權專屬 PO（`doc/governance/TEAM_PLAYBOOK.md` §2）。
Agent 自填等同偽造核准紀錄。

**偵測指令**：

```bash
grep -n "APPROVED" .claude/skills/evidence-sync/SKILL.md
```

本 Skill 的模板中不得出現預填的 `APPROVED`；出現即為模板錯誤。

### 失敗範例 B：ADR 內文複製規格數字

> ❌ 「Feature Store 固定 N 欄：⋯⋯」寫死在 ADR 內文

**為何 FAIL**：契約數字有唯一權威來源。ADR 複製一份後，權威文件更新時 ADR 不會跟著改，
成為下一個 `DRIFT`。正確寫法：「Feature Store 欄位契約見 `FEATURE_REGISTRY.md` §2」。

### 失敗範例 C：只改規格文件，沒跑傳播清單

> ❌ 更新了 `FEATURE_REGISTRY.md` 的契約，但 `DECISIONS.md` 的 ADR 內文與
> `TRACEABILITY.md` 的索引仍是舊值。

**為何 FAIL**：這正是 V8 的 `C-1`～`C-4`。

**偵測指令**：

```bash
python scripts/verify/gate0_contract_check.py
```

腳本的跨文件數字宣告檢查會抓到不一致。

---

## 6. 相關規則

- `CLAUDE.md` §9 — 證據標籤
- `CLAUDE.md` §14 — Definition of Done
- `doc/governance/TEAM_PLAYBOOK.md` §2 — PO 專屬批准事項
- `gate-submit` skill — 送審前自檢
