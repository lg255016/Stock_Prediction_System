# 跨文件狀態一致性稽核（第 6 案）—— Gate A 提案

- 日期：2026-09-08
- 性質：**Gate A 提案。Plan-Before-Code —— 本檔未修改任何程式碼或文件，僅規劃與判準設計。**
- 依據：PO 2026-09-08 裁示「第 6 案（跨文件狀態一致性）開案要點」——方法為反查法、
  五份文件交叉宣稱、判準寫死再跑、可機械化部分附 known-FAIL

---

## 0. 一句話

**問「PROJECT_STATUS 說 CLOSED 的那一列，`closed/` 裡真的有那份文件嗎」是反查；
問「`closed/` 裡的這份文件，有沒有任何地方登記過它」是反查的另一半——
兩個方向都要問，因為兩種遺漏長得不一樣。**

---

## 1. Goal

以**反查法**（從「每個治理物件應存在的狀態集」出發，逐一反查文件是否滿足，
而非從已知缺陷湊檢查）稽核五份治理文件之間的交叉宣稱：
`PROJECT_STATUS.md` ↔ `gates/closed/`（實體檔案）↔ `DECISIONS.md` ↔
`TRACEABILITY.md` ↔ `REMAINING_RISKS.md`。

## 2. Requirement Source

PO 2026-09-08 訊息逐字：

> 方法：反查法——從「每個治理物件應存在的狀態集」出發，逐一反查文件，
> 不從已知缺陷湊檢查。兩個奠基實例都要收：複查方當年那條「比較已列出者」的
> 錯誤判準（它找不到「根本沒被列出」的缺陷）與 PM 的反查方向——錯的那條也要
> 進文件，它是這個方法存在的理由。

## 3. 兩個奠基實例（方法論依據，必須收錄）

### 3.1 錯的那條：「比較已列出者」

`CLAUDE.md` §9A.1 記載的原始 B4 檢查：

```bash
grep "fillna" FEATURE_REGISTRY.md | grep -iE "comment|push"
```

第二個 `grep` 把搜尋範圍**限制在已知安全的欄位**（留言與推文），而真正的缺陷
在**情緒欄位**。**該檢查結構上就不可能發現那個缺陷**——它每次通過，因為
它只看已知沒問題的地方。PO 原話：「B4 是為了通過而寫的，不是為了偵測而寫的。」

`scripts/verify/gate0_contract_check.py` 現行 B4（`raw 層留言計數欄無 DEFAULT`）
的程式碼註解也記了同一種病灶的第二個實例（`UG-G2-SB3`，2026-08-27）：
舊版檢查只掃 `DB_MIGRATION_PLAN.md`、且正則要求整句同一行，
`MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的多行 `ALTER TABLE` 寫法
**結構上不可能被舊版抓到**——即使該份文件當時確實寫著 `DEFAULT 0`。

**兩次同一個病灶**：檢查的搜尋範圍是從「已知答案」往回湊的，
不是從「契約要求什麼」往前列的。

### 3.2 對的那條：契約反查法

改採**契約反查法**（從契約要求出發列舉所有應受約束的對象，逐一反查文件是否滿足）
之後，新增的 B8 檢查**立刻 FAIL**，抓出三個缺漏的 ADR。現行
`gate0_contract_check.py` 的 B2／B3／B4／B11／B12／B13 皆已是這個方法論的實例
（檢查標題逐一標註「反查法」）。

**本案是同一方法論的擴大應用**——從「單一契約文件內部的欄位/規則完整性」
擴大到「五份治理文件之間的狀態宣稱一致性」，範圍不同，方法相同。

---

## 4. Current State（唯讀查證，本節無任何推測）

### 4.1 既有機制的覆蓋範圍（已核對 `gate0_contract_check.py` 全部 13 項）

| 檢查 | 覆蓋範圍 | 與本案的關係 |
|---|---|---|
| B8 | `SYSTEM_UPGRADE_MASTER_PLAN.md` §19 需 PO 簽的決策 → `DECISIONS.md` 是否有對應 ADR | **已覆蓋**「規格要求 ADR」這個反查方向，本案不重做 |
| B13 | `DECISIONS.md` 狀態欄字首是否為合法詞彙 | 覆蓋單文件內部欄位合法性，非跨文件狀態宣稱一致性 |
| 其餘 B1~B7、B9~B12 | 特徵契約、DB schema、編號方案等**內容**一致性 | 與本案的**治理狀態**（CLOSED／APPROVED／已解決）宣稱一致性是不同層次 |

**結論**：現行機制**沒有**任何檢查涵蓋「`PROJECT_STATUS.md` 的 CLOSED 宣稱是否有
對應的 `closed/` 實體檔案」「`closed/` 的實體檔案是否都被登記」
「`REMAINING_RISKS.md` 的風險狀態與 `PROJECT_STATUS.md`／`DECISIONS.md` 是否互相矛盾」——
**這正是本案的空白範圍，不是重工**。

### 4.2 五份文件的角色（唯讀複述，非推測）

| 文件 | 本案關心的宣稱類型 |
|---|---|
| `PROJECT_STATUS.md` §0.2 | 「某 SB 已 CLOSED」+ 引用的 `closed/` 路徑 + 引用的 ADR 編號 + 引用的 commit hash |
| `gates/closed/` | 實體存在的過程文件（哪些 SB 真的有結案文件） |
| `DECISIONS.md` | 每則 ADR 的狀態（`Proposed`／`APPROVED`／`Superseded`／`Rejected`）與觸發 Gate/SB |
| `TRACEABILITY.md` | §3.2 ADR 快速索引、§3A／§3A.1 交付物追溯矩陣 |
| `REMAINING_RISKS.md` | 每則風險的狀態（`HYPOTHESIS`／`OBSERVED`／`MITIGATED`／…）與其宣稱的解決依據（commit、SB） |

---

## 5. In Scope

反查方向逐一列出（**每個方向都是「從應存在的狀態集出發」，不是從已知缺陷出發**）：

| # | 反查方向 | 起點物件集 | 逐一核對什麼 |
|---|---|---|---|
| R1 | `PROJECT_STATUS.md` → `gates/closed/` | §0.2 中標記 **CLOSED** 的每一列 | 該列引用的 `closed/*.md` 路徑是否**實際存在** |
| R2 | `gates/closed/` → `PROJECT_STATUS.md` | `closed/` 目錄下**實際存在**的每一份文件 | 是否被 `PROJECT_STATUS.md`（§0.2 或 §0.5）**至少一處**引用——**孤兒文件偵測**，R1 的反方向，抓的遺漏形狀不同 |
| R3 | `PROJECT_STATUS.md` → `DECISIONS.md` | §0.2 中提及的每一個 ADR 編號 | 是否存在於 `DECISIONS.md`，且狀態是否為 **`APPROVED`**（`PROJECT_STATUS.md` 宣稱已核准的 ADR，不得在 `DECISIONS.md` 仍停在 `Proposed`——`DEC-030` 的五天空窗即此形狀，已由 B13 部分緩解，本案從 `PROJECT_STATUS.md` 端再核一次，方向不同） |
| R4 | `DECISIONS.md`（`APPROVED`）→ `TRACEABILITY.md` | 狀態為 **`APPROVED`** 的每一則 ADR | 是否出現在 `TRACEABILITY.md` §3.2 ADR 快速索引 |
| R5 | `REMAINING_RISKS.md` → `PROJECT_STATUS.md`／`DECISIONS.md` | 狀態含**解決性宣稱**（`MITIGATED`／`VERIFIED`／`VERIFIED（部分）`）且**附帶具體 commit 或 SB 引用**的每一則風險 | 該 commit/SB 在 `PROJECT_STATUS.md` 中是否確實存在、且該列描述是否與風險宣稱的解決方式不矛盾 |

## 6. Out of Scope（明確排除）

- **`REMAINING_RISKS.md` 狀態欄混著兩軸**（`PROJECT_STATUS.md` §0.5 #13 已登記為另案）——
  本案不重複處理該項，若 R5 的反查因此撞到欄位語意混淆，**如實記錄、不代為修正**
- **ADR 內容本身是否正確**（僅核對「狀態欄」與「是否被索引」的一致性，不重新審查決策內容）
- **`§0.5` 清單本身的義務是否已履行**（那是 §0.5 逐項的責任，本案只核對它與其他四份文件的交叉宣稱）
- **`archive/` 內容**——依 `CLAUDE.md` §16.2 唯讀，不在反查範圍內

---

## 7. 方法（判準寫死，執行前需核准）

### 7.1 可機械化部分（納入獨立腳本，非 `gate0_contract_check.py` 本體——理由見 §7.3）

| 反查方向 | 機械化方式 |
|---|---|
| R1 | 解析 `PROJECT_STATUS.md` §0.2 每列的 **CLOSED** 標記與其後文字中形如 `` `doc/upgrade/gates/closed/XXX.md` `` 的路徑引用（正則），逐一 `os.path.exists()` |
| R2 | `os.listdir("doc/upgrade/gates/closed/")` 取得實體清單，逐檔案名以純文字搜尋是否出現在 `PROJECT_STATUS.md` 全文中（不限 §0.2，因 §0.5 也可能引用） |
| R3 | 解析 `PROJECT_STATUS.md` 全文中形如 `` DEC-\d{3} `` 的引用，逐一比對 `DECISIONS.md` 對應章節的狀態欄是否為 `APPROVED` |
| R4 | 解析 `DECISIONS.md` 中狀態為 `APPROVED` 的 ADR 編號清單，逐一確認出現於 `TRACEABILITY.md` §3.2 |

### 7.2 需要人工判讀的部分（如實揭露，不假裝可機械化）

**R5 無法完全機械化**：「風險宣稱的解決方式是否與 `PROJECT_STATUS.md` 該列描述矛盾」
需要語意比對（例如風險寫「已透過 DB_HOST 覆寫解決」而 `PROJECT_STATUS.md` 該列
描述的是完全不同的解法），**這不是字串匹配能判定的**。R5 的機械化部分僅到
「引用的 commit/SB 是否存在」，**矛盾與否需要人工逐則讀過**——本提案不假裝
能自動化這一半，Gate B 執行時會列出「R5 機械可查部分」與「R5 人工核對部分」
兩張表，分開回報。

### 7.3 為何是獨立腳本，不是塞進 `gate0_contract_check.py`

`gate0_contract_check.py` 的 `DOC_PATHS` 定義的是**受驗契約文件**（規格/契約類），
其 Part B 檢查的是**契約內容**一致性。本案檢查的是**治理狀態**一致性，
物件（SB 結案狀態、ADR 核准狀態、風險處置狀態）與檢查頻率的自然節奏不同
（契約檢查該在每次 commit 前跑；治理狀態反查該在**每次 SB／Gate 結案時**跑，
頻率低很多）。**混進同一支腳本會讓兩種不同節奏的檢查綁在一起**，
比照 `gate-submit` skill 產出 7／8 的既有判斷（機械化與否分開決定，
不因為方便就塞進去）。獨立腳本置於 `scripts/verify/cross_doc_consistency_check.py`
（待 Gate B 核准後建立）。

### 7.4 Known-FAIL 案例（`CLAUDE.md` §9A.2 要求，僅列可機械化部分）

| 檢查 | known-FAIL 構造方式 |
|---|---|
| R1 | 於拋棄式副本中，把某一 CLOSED 列的路徑改成不存在的檔名，確認腳本回報缺失 |
| R2 | 於拋棄式副本中，在 `closed/` 新增一份未被任何文件引用的檔案，確認腳本回報孤兒 |
| R3 | 於拋棄式副本中，把某個被引用 ADR 的狀態改回 `Proposed`，確認腳本回報不一致 |
| R4 | 於拋棄式副本中，把某個 `APPROVED` ADR 從 `TRACEABILITY.md` §3.2 索引中移除，確認腳本回報缺失 |

四項皆需**實際執行**於拋棄式副本（沿用 stub 稽核已驗證可行的 `git worktree`
隔離機制），不得只描述「應該會抓到」。

---

## 8. Failure Semantics & Definition of Done

| 項目 | 判準 |
|---|---|
| R1~R4 | 逐一產出「合規／不合規」清單，不合規者附具體檔名/編號，皆為機械化結果 |
| R5 | 機械可查部分（引用是否存在）+ 人工核對部分（是否矛盾）分開產出，人工部分附讀過的具體依據，不得只寫「已核對」 |
| known-FAIL | §7.4 四項皆已實際執行並確認腳本能偵測 |
| 不修改任何既有文件內容 | 本案為稽核，Gate A/B 階段唯讀；若 R1~R5 發現不合規，**列入 Gate B 結果的未驗證/待修清單，不在本案內順手修**（同 stub 稽核的原則：本案只負責把數字量出來） |

## 9. E2E Verification

1. 獨立腳本於容器內執行，產出 R1~R5 結果 JSON
2. `python -m unittest discover -s tests -p "test_*.py"`（確認未意外修改任何檔案）
3. `python scripts/verify/gate0_contract_check.py`（EXIT=0，確認本案未觸及既有受驗契約文件）

## 10. Documentation Sync

- 若 R1~R5 發現不合規案例，依 `CLAUDE.md` §14 精神列入 Gate B 送審文件的
  未驗證清單，逐項有名字有去處，不在本案內搶修
- `PROJECT_STATUS.md` §0.5：待 Gate B 核准後，比照 stub 稽核的 #19 切法登記
  （一次性稽核動作結案；若發現值得成為常設規則的項目，另立一則）

---

## 11. 待 PO 於 Gate A 核准時確認的兩點

1. **獨立腳本 vs 塞進 `gate0_contract_check.py`**（§7.3 已給理由，傾向獨立）——
   是否同意，或有不同判斷
2. **R5 人工核對部分的產出格式**——本提案傾向「逐則風險列出讀過的依據與結論」，
   是否需要更嚴格的格式（例如附上讀取的具體行號範圍）
