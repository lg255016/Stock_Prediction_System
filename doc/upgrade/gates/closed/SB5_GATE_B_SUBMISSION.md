# UG-G1-SB5 Gate B 送審文件：文件全面校正（Gate 1 最後一個 Small Batch）

> 狀態：**待 PO 審查**
> 日期：2026-08-26
> 對應提案：`doc/upgrade/gates/SB5_GATE_A_PROPOSAL.md`（含 §9 PO 核准與修正記錄）
> 範圍：純文件修改，未動 `src/`／`database/`／任何 Schema

---

## 1. 摘要

依 PO 核准之修正範圍完成 SB5 全部工作項目：

- `doc/spec/`（PRD／SDD）直接修正「18 欄位」裸寫、SDD `trend_discover.py` 規劃中標記、
  SDD 檔案清單表補齊 SB4 新增之 3 個 Migration 相關檔案。
- `doc/evidence/DECISIONS.md`：依 PO 核准之方案 C／方案 B 執行方式（原文一字不改，緊鄰問題
  原文插入 `📌 SB5 補充註記`），修正 DEC-003（截斷）、DEC-004（重複）、DEC-006／007／008／009
  （特徵數裸寫共 10 處、禁用詞 1 處、DEC-007 host 環境證據邊界），並新增 **DEC-022** 作為總覽索引。
- `doc/evidence/CHALLENGES.md`：本次完整 grep 新發現的第 15 處裸寫（L211），同等方式處理。
- `doc/governance/PROJECT_STATUS.md`：§0.4 測試計數 164→200（改指令化免責聲明寫法）。
- `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`：DRIFT-001／002／004／005／006／007／010 狀態
  更新為 CLOSED 並附具體修正說明；DRIFT-013 重新分類為「排除，維持不動」（見 §3 新發現）；
  DRIFT-015 文件標註部分 CLOSED；「修復工單對照」表 DRIFT-008／009／011／012／018 共 5 列
  （決策點 2 核准之 4 列 + 過程中另發現同型問題的 DRIFT-018 一列）更新為 CLOSED + commit hash；
  HERM-A/B/C/D/E 5 列 Owner 欄同步更新。
- 新建 `README.md`（Repository 根目錄，DRIFT-010）。

---

## 2. 範圍修正說明（與原提案的差異，需 PO 知悉）

### 2.1 「18 欄位」裸寫清單：15 處，非原提案「7 處」或 PO 指出的「12 處」

PO 核准訊息指出審查員發現 5 處遺漏（`SDD:L229`、`DECISIONS.md:L654/677/701`、`L763`）。
依 PO 指示對整個 `doc/evidence/` 資料夾重新跑一次完整 grep（非僅 DEC-006／007／009 附近）後，
**另外發現 2 處此前無人（含審查員與本 Agent）發現的位置**：`DECISIONS.md:L577`（DEC-006
Verification 段）與 `CHALLENGES.md:L211`（此前從未被 `DOCUMENT_DRIFT_REMEDIATION.md` 登錄
為 DRIFT-001／007 的引用位置）。完整清單共 **15 處**，詳見 `SB5_GATE_A_PROPOSAL.md` §9.2。

### 2.2 DRIFT-013（PROJECT_STATUS.md Current HEAD）重新分類為排除

原提案 §2.7 建議修正 `PROJECT_STATUS.md`「Current HEAD」欄位。實作階段重新檢視後發現：
該欄位（現行位置為「## 2. Git State」）落在文件自身在檔案開頭明文宣告的
「§1 以下為 PRE_CODEX 舊紀錄」範圍內，與已確立排除慣例的「133/133」測試計數屬同一類舊快照，
不應修正。**此為原提案分析的錯誤，已於實作時修正**——本次**未修改**該欄位（`a41a9ea` 保留不動），
`DOCUMENT_DRIFT_REMEDIATION.md` 對應列已改標「排除，維持不動」。此為範圍**縮減**，非新增工作。

### 2.3 「待 commit」staleness 的延伸修正

決策點 2 明確核准的是「修復工單對照」表 4 列（DRIFT-012/009/008/011）。執行時發現同一張
「修復工單對照」表另有 **DRIFT-018** 一列（Owner 欄同樣寫「待 commit」，但 SB3 早已 CLOSED），
以及主要「漂移對照表」中 **DRIFT-009、DRIFT-012** 兩列的 Owner 欄（與工單對照表分屬不同表格）
同樣殘留過期的「待 commit」字樣，以及 §「測試封閉性」HERM-A/B/C/E 4 列的 Owner 欄同樣如此。
這些與決策點 2 核准的 4 列屬同一類「Owner／狀態欄位過期」問題，一併更新為 CLOSED + commit hash，
未觸及任何列的原始問題描述文字。`TRACEABILITY.md`／`DOCUMENT_DRIFT_REMEDIATION.md` 內嵌在
較長 Evidence Label 敘述句中、附帶當時日期的歷史性「尚未 commit」措辭（描述的是撰寫當下的
狀態，非現行宣稱）**未觸碰**，若 PO 認為也需要更新，可另外指示。

---

## 3. Diff 摘要

| 檔案 | 異動類型 | 行數（新增/刪除） |
|------|---------|-------------------|
| `README.md` | 新增 | +105 / -0 |
| `doc/evidence/CHALLENGES.md` | 修改 | +6 / -0 |
| `doc/evidence/DECISIONS.md` | 修改 | +143 / -0 |
| `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 修改 | +24 / -23 |
| `doc/governance/PROJECT_STATUS.md` | 修改 | +4 / -3 |
| `doc/spec/PRD_Financial_Sentiment_System_v1.md` | 修改 | +2 / -2 |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 修改 | +7 / -4 |
| `doc/upgrade/gates/SB5_GATE_A_PROPOSAL.md` | 新增（本次提案+修正記錄） | +469 / -0 |
| `doc/upgrade/gates/SB5_GATE_B_SUBMISSION.md` | 新增（本文件） | — |

`DECISIONS.md`／`CHALLENGES.md`／`DOCUMENT_DRIFT_REMEDIATION.md` 的 -0 刪除數，符合 PO 決策點 1
「原文一字不改」的要求（唯一例外是 `DOCUMENT_DRIFT_REMEDIATION.md` 的 24/-23，屬既有
「Owner／狀態」欄位值本身的更新，PO 決策點 2 已核准此類欄位更新不受 §16.1 爭議約束）。

---

## 4. 產出 1：契約驗證原始輸出

```bash
$ python scripts/verify/gate0_contract_check.py
B1   PASS | 29 欄契約完整性
B2   PASS | 被引用欄位皆存在於契約（反查法）
B3   PASS | 社群欄位皆有 SOURCE_FAILED→NULL 規則（反查法）
B4   PASS | raw 層留言計數欄無 DEFAULT（反查法）
B5   PASS | Triple-Barrier label domain 一致
B6   PASS | Barrier anchor 一致為 Open[T+1]
B7   PASS | 無「來源失敗→空 DataFrame」
B8   PASS | §19 需 PO 簽的決策皆有 ADR 承接
B9   PASS | Dcard SB 引用正確
B10  PASS | 編號方案有唯一對照表
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂
==================================================
Part B: 11/11 PASS
EXIT=0
```

**B11 WARN 說明**：此 WARN 為 `gate0_contract_check.py` 內建 `LEGACY_ALLOWLIST` 機制，鍵值為
`("DECISIONS.md", "18")`，只要 `DECISIONS.md` 內任何一行符合其欄位契約正則就會命中一次
（本次落在 L599，即 DEC-006 內原提案 §2.1 表格已列的 L551 行，行號因本次新增內容位移）。
由於 PO 核准之方案 C／方案 B 執行方式是「原文一字不改」，`DECISIONS.md` 內的裸寫「18」
**永久保留**，此 WARN **今後每次執行都會持續出現**，屬設計上的預期行為，非新問題。
腳本內 `LEGACY_ALLOWLIST` 旁的註解寫「排定由 UG-G1-SB5 處理」，字面上暗示 SB5 後此 WARN
會消失——**這與本次核准的實際處理方式（保留 WARN，不刪除觸發源）不符**，但
`scripts/verify/gate0_contract_check.py` 屬程式碼而非文件，不在 SB5「純文件修改」範圍內，
本次未修改該註解，僅此揭露供 PO知悉。

---

## 5. 產出 2：執行環境、測試原始輸出、依賴狀態

**執行環境：host（非支援環境）**，`Python 3.10.11`。

```bash
$ python -m unittest discover -s tests -p "test_*.py"
Ran 200 tests in 2.304s
OK
```

本次修改為純文件變更，不涉及 `src/`／`database/` 任何路徑，200/200 通過屬**回歸確認**
（證明文件修改未意外影響任何程式碼行為），**不構成**對 ML／NLP／DB 路徑本身的驗證宣稱。

---

## 6. 產出 3：Commit 檔案清單（待 PO 授權）

| 檔案 | 異動類型 |
|------|---------|
| `README.md` | 新增 |
| `doc/evidence/CHALLENGES.md` | 修改 |
| `doc/evidence/DECISIONS.md` | 修改 |
| `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 修改 |
| `doc/governance/PROJECT_STATUS.md` | 修改 |
| `doc/spec/PRD_Financial_Sentiment_System_v1.md` | 修改 |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 修改 |
| `doc/upgrade/gates/SB5_GATE_A_PROPOSAL.md` | 新增 |
| `doc/upgrade/gates/SB5_GATE_B_SUBMISSION.md`（本文件） | 新增 |

全部 9 個檔案皆在 SB5 核准範圍內，無超出授權清單之檔案。

---

## 7. 產出 4：格式／行尾夾帶偵測

```bash
$ git diff --numstat > ns_raw.txt
$ git diff --numstat -w > ns_nows.txt
$ diff ns_raw.txt ns_nows.txt
$ echo $?
0
```

無輸出、exit 0，未偵測到任何純空白／行尾夾帶變更。

---

## 8. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 |
|------|---------|-----------|
| 「18 欄位」裸寫完整清單共 15 處 | `VERIFIED THIS SESSION` | `grep -rnE "18[[:space:]]*(欄\|項\|特徵\|features?)" doc/evidence/ doc/spec/` |
| PRD/SDD 修正後 0 殘留 | `VERIFIED THIS SESSION` | 同上，限定 `doc/spec/` |
| 禁用詞修正後僅剩 `DECISIONS.md` 原文（不動）+ 本次新增旁註引述 | `VERIFIED THIS SESSION` | `grep -rniE "100% reliable\|perfect\|enterprise-grade\|production-ready\|guaranteed\|completely prevents\|永遠不會\|完美解決\|零誤差" doc/spec doc/governance doc/evidence` |
| SDD 規劃中標記清零 | `VERIFIED THIS SESSION` | `grep -n "規劃中\|⏳" doc/spec/SDD_Financial_Sentiment_System_v1.md` |
| 測試數 200，與 `PROJECT_STATUS.md` §0.4 一致 | `VERIFIED THIS SESSION` | `grep -ch "def test_" tests/test_*.py \| awk '{s+=$1} END {print s}'` |
| README.md 已建立 | `VERIFIED THIS SESSION` | `ls README.md` |
| contract-check 11/11 PASS | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py` |
| 全套測試 200/200 OK（host，回歸確認） | `VERIFIED THIS SESSION` | `python -m unittest discover -s tests -p "test_*.py"`（host，非 ML/NLP/DB 宣稱） |
| numstat 無格式夾帶 | `VERIFIED THIS SESSION` | 見產出 4 |
| DEC-008 描述之 Fallback 資料產生器已被 DEC-012 方案 B 取代 | `PREVIOUSLY VERIFIED` | 紀錄位置：UG-G1-SB2 Gate B（commit `414fcc81`），本次未重跑，僅援引既有結論 |
| DRIFT-013 應排除、不修正 | `INFERENCE` | 依 `PROJECT_STATUS.md` 檔案開頭 §0 前言之明文宣告（§1 以下為 PRE_CODEX 舊紀錄）推導，非新的獨立驗證 |

---

## 9. 產出 6：Known-FAIL 案例對照表

| # | 檢查 | Known-FAIL 案例（修正前實際執行） | 修正前原始輸出 | 修正後結果 |
|---|------|-----------------------------------|----------------|-----------|
| V1 | 禁用詞掃描 | 修正前對 `doc/spec doc/governance doc/evidence` 執行同一指令 | 命中 2 處：`SDD:L246`、`DECISIONS.md:L729` | SDD 命中清零；`DECISIONS.md` 剩原文（PO 核准不動）+ 旁註引述（非新違規） |
| V2 | 特徵數裸寫掃描 | 修正前執行同一 grep | 命中 15 處（PRD 2、SDD 2、`DECISIONS.md` 10、`CHALLENGES.md` 1） | `doc/spec/` 0 處；`doc/evidence/` 僅剩原文（不動）+ 15 個緊鄰旁註 |
| V3 | SDD 規劃中標記 | 修正前執行同一 grep | 命中 1 處（L68 `trend_discover.py`） | 0 處 |
| V4 | 測試計數一致性 | 修正前 `PROJECT_STATUS.md` §0.4 寫「164」 | `164 ≠ 200`（FAIL） | 「200」與實測值相等 |
| V5 | README 存在性 | 修正前 `ls README.md` | `No such file or directory`（exit 2，FAIL） | 檔案存在、非空 |
| V6 | contract-check 全綠 | 修正前後皆已執行（見產出 1） | 修正前後皆 11/11 PASS（B11 WARN 為設計上永久保留，非 FAIL） | 同左 |
| V7 | 全套測試不受影響 | 修正前後各執行一次 | 修正前 200/200 OK | 修正後 200/200 OK，無回歸 |

---

## 10. Definition of Done 對照

- [x] §2.1～§2.8（原提案）九項 SB5-owned 漂移項目：DRIFT-001／002／004／005／006／007／010／015
      已修正；DRIFT-013 已依重新分析排除（見 §2.2）。
- [x] 三個 PO 決策點均有明確裁決記錄（`SB5_GATE_A_PROPOSAL.md` §9.1）。
- [x] V1～V7 全數執行且附原始輸出，V1～V5 附修正前 FAIL 輸出。
- [x] 未新增、未刪除、未修改任何 `src/`、`database/` 檔案。
- [x] `DOCUMENT_DRIFT_REMEDIATION.md` 對應列狀態更新為 CLOSED（含決策點 2 核准之 4 列 +
      過程中發現同型問題的 DRIFT-018／DRIFT-009／DRIFT-012 Owner 欄 + HERM-A/B/C/D/E）。
- [ ] 依 `CLAUDE.md` §16.3，本提案文件與 Gate B 文件於 PO 核准結案後移入
      `doc/upgrade/gates/closed/`，並回填 `SYSTEM_UPGRADE_MASTER_PLAN.md` 狀態列——
      **待 PO 核准結案後執行**。

---

## 11. 待 PO 裁決事項

1. 是否核准本次 commit（§6 檔案清單，9 個檔案，皆為新增或修改，無刪除）。
2. §2 所列與原提案的三處差異（15 處裸寫清單、DRIFT-013 重新分類、待commit staleness 延伸修正）
   是否認可為本次範圍內的合理執行結果。
3. §4 揭露之 `gate0_contract_check.py` 註解與實際處理方式不符一事，是否需要另開工單處理
   （屬程式碼變更，非本次範圍）。
