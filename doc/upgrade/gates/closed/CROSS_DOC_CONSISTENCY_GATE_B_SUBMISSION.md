# 跨文件狀態一致性稽核（第 6 案）Gate B 送審

- 日期：2026-09-08
- 涵蓋：Gate A 提案 + 判準先寫死 + 執行結果 + PO 裁決落地（R2/R3/B13 三類處置）
- 性質：**送審文件**。依 `PRE-G3-04`／第 5 案已走通的順序執行——**送審 → 複查 → PO 核准 → 結案 commit**。
  本文件尚未移入 `closed/`；核准前 `gates/` 根層維持本檔與其他審查中文件並存。

---

## 0. 一句話

**「比較已列出者」找不到「根本沒被列出」的——這條教訓不只用來找 PROJECT_STATUS.md
的孤兒引用，也用來找既有機制自己的盲點：新 B13 一跑，既有機制對 6 則 ADR
「視而不見的 PASS」現形，且是在它自己被拿來當範本的那一刻被抓到的。**

---

## 1. 完整 commit 序列

| commit | 內容 |
|---|---|
| `7b789b3` | Gate A 提案（純規劃，未動任何程式碼） |
| `e8a018a` | Gate A 確認落地：`gate-submit` 產出 9 + 判準先寫死 |
| `7bb9643` | 腳本建立 + 初次執行結果：R1／R4 PASS，R2／R3 FAIL（真實案例） |
| `8100556` | `TEAM_PLAYBOOK.md` §5.1 新增 A11（背景執行失敗的教訓，PO 授權登記） |
| `633a336` | `PROJECT_STATUS.md` §0.5 #9 展開縮寫檔名 |
| `989206b` | R2 v2：8 個索引式引用改豁免表（附理由），加入面向未來的間接查找機制 |
| `64e9ae2` | `gate-submit` 產出 8（本次移入清單規則）／產出 9（腳本已存在）更新 |
| `bdf6036` | B13 根治 + 6 則 ADR 狀態行修正（自鎖規避：修法與資料修正同一 commit） |
| `4ababa1` | 完整集合重跑結果附入結果檔 |

---

## 2. 核心結果摘要

### 2.1 初次執行（`7bb9643`）：R1／R4 PASS，R2／R3 FAIL

- **R2**：9 個孤兒，逐一查證分兩類——8 個索引式引用（結案時只索引
  `GATE_B_SUBMISSION.md`，子文件不逐一列名，刻意的文件經濟性設計）、
  1 個縮寫式引用（`G2_SB5_DP5_GATE_B_SUBMISSION.md` 被寫成後綴省略前綴的形式）
- **R3**：5 個不合規（DEC-005/006/008/009/022），逐一查證後發現：4 則
  實質已核准，僅狀態行為舊式格式；DEC-009 完全沒有狀態欄位
- **⚠⚠ 重大發現**：既有 `gate0_contract_check.py` B13 對這些 ADR **從未真正檢查過**——
  B13 只計數 `^- 狀態：` 開頭的行，格式不符者從未進入 `b13_seen`

### 2.2 PO 裁決三類處置

| 類別 | 處置 | commit |
|---|---|---|
| R2（9 孤兒） | 8 個索引式→豁免表（附理由）+ 面向未來的「本次移入清單」規則；1 個縮寫式→展開全名 | `633a336`／`989206b`／`64e9ae2` |
| R3／B13（5→6 不合規） | B13 改逐則遍歷區塊、每則須恰一行可辨識狀態；4+1（新發現 DEC-007）則舊格式正規化，DEC-009 補 APPROVED（PO 裁決） | `bdf6036` |
| 執行面插曲 | 背景 fork 首次零工具呼叫回報「完成」，經產物存在性驗證戳穿，登記進失敗模式目錄 | `8100556` |

### 2.3 ⚠ 執行中發現、超出 PO 原始列表的一項：DEC-007

PO 原始裁決列出 4 則舊格式 ADR（DEC-005/006/008/022）。新 B13（掃描全部
`DECISIONS.md`，非僅 `PROJECT_STATUS.md` 引用者）執行後，額外發現 DEC-007
同屬同一類缺陷——未被 R3 抓到是因為 R3 範圍僅限「`PROJECT_STATUS.md` 引用
的 ADR」，DEC-007 未被引用；但 B13 範圍是「全部 ADR」。比照同類 4 則的處置
一併正規化，已於 `bdf6036` commit message 與
`CROSS_DOC_CONSISTENCY_B13_fix_evidence.json` 的 `SCOPE_DEVIATION_DISCLOSED`
明確揭露，非擅自擴大範圍。

### 2.4 自鎖規避

B13 修法若單獨先入庫，`contract-check` 會在現行未修正的 ADR 資料上 FAIL，
`.githooks/pre-commit` 檢查 1 隨即擋下所有後續 commit（含修正 ADR 的那個
commit 本身）。處置：紅色證據於拋棄式 `git worktree` 取得（新邏輯 FAIL、
舊邏輯 PASS 並排留存於 `CROSS_DOC_CONSISTENCY_B13_fix_evidence.json`），
worktree 拆除後，B13 修法與 6 則 ADR 資料修正在**同一個 commit**（`bdf6036`）
內完成，staged 樹自我一致，未觸發自鎖。

### 2.5 完整集合重跑（`4ababa1`）

R1~R4：**4/4 PASS**。`gate0_contract_check.py` B13：掃描 27 則、不合規 0
（非舊版的假 PASS）。R4 的先前 CAVEAT（建立在受限 21 則子集上）已解除，
現於完整 27 則 `APPROVED` 集合上驗證。

---

## 3. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 / 依據 |
|---|---|---|
| R1~R4 初次執行結果 | `VERIFIED THIS SESSION` | `python scripts/verify/cross_doc_consistency_check.py`（`7bb9643` 當時） |
| R2 9 個孤兒的分類查證 | `VERIFIED THIS SESSION` | `CROSS_DOC_CONSISTENCY_result.json` §R2 |
| R3 5 個不合規的根因查證（含 DEC-009 全文區塊逐段讀過） | `VERIFIED THIS SESSION` | `CROSS_DOC_CONSISTENCY_result.json` §R3 `root_cause_investigation` |
| B13 既有盲點（6 則 ADR 從未進入 `b13_seen`） | `VERIFIED THIS SESSION` | `CROSS_DOC_CONSISTENCY_B13_fix_evidence.json` 新舊邏輯並排輸出 |
| R2 v2 修正後 0 孤兒 | `VERIFIED THIS SESSION` | `python scripts/verify/cross_doc_consistency_check.py`（`989206b` 後） |
| B13 修正後 27 則、0 不合規 | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py`（`bdf6036` 後） |
| 完整集合重跑 4/4 PASS | `VERIFIED THIS SESSION` | `CROSS_DOC_CONSISTENCY_result.json` §POST_FIX_RERUN_2026_09_08 |

---

## 4. Known-FAIL 對照（`CLAUDE.md` §9A.2）

| 檢查 | known-FAIL 案例 | 實測結果 | 復原確認 |
|---|---|---|---|
| R1 | 拋棄式 worktree：CLOSED 列路徑改不存在檔名 | `FAIL`，不合規 1 | worktree 已拆除，主樹未受影響 |
| R2 | 拋棄式 worktree：`closed/` 新增無人引用檔案 | `FAIL`，孤兒 10（含新增檔） | 同上 |
| R3 | 拋棄式 worktree：`DEC-010` 狀態改回 `Proposed` | `FAIL`，不合規 6（含新增） | 同上 |
| R4 | 拋棄式 worktree：`TRACEABILITY.md` 移除全部 `DEC-010` 字串 | `FAIL`，缺失 1 | 同上 |
| B13（新邏輯） | 於同一拋棄式 worktree，套用新邏輯對**未修正**的真實 `DECISIONS.md` 執行 | `FAIL`，不合規 6（DEC-009 為活的案例，不必構造） | 同上，且與舊邏輯的 `PASS` 並排留存，兩者對照即盲點存在過的直接證明 |

四案（含 B13）皆於拋棄式 `git worktree` 實際執行，取得原始 FAIL 輸出，
還原後 diff 確認與 baseline 逐位元組相同，worktree 已拆除確認。

---

## 5. 未驗證清單（有名字、有去處）

本案為稽核性質，發現的不合規案例依判準只記錄不搶修——但本次的 R3／B13
一項已因自鎖考量而在本案內修正（PO 明確裁決授權，非本案自行擴權）。

| # | 項目 | 現況 | 去處 |
|---|---|---|---|
| 1 | R5 的人工判讀部分未來若有新增觸發風險，需持續依鎖定的四欄格式核對 | 3 則現有觸發風險已核對完畢（3/3 成立） | 常設方法，非一次性動作，日後 `REMAINING_RISKS.md` 新增解決性宣稱時依同格式核對 |
| 2 | `cross_doc_consistency_check.py` 的執行時機已綁事件（結案類 commit 前），但未機械強制 | `gate-submit` 產出 9 為 skill 指示，非腳本強制 | 同產出 7／8 的既有誠實揭露：真正機械化需另外設計判準，刻意不順手做 |

---

## 6. 裁決索引

| 裁決 | 裁決者 | commit |
|---|---|---|
| Gate A 兩點確認（獨立腳本綁事件、R5 四欄格式） | PO 2026-09-08 | `7b789b3` 前置訊息，落地於 `e8a018a` |
| Gate B 執行結果覆核 | 複查方／PO 2026-09-08 | 本輪訊息 |
| R2/R3/B13 三類處置 + TEAM_PLAYBOOK 失敗模式登記 | PO 2026-09-08 | 落地於 `8100556`／`633a336`／`989206b`／`64e9ae2`／`bdf6036`／`4ababa1` |

---

## 7. `DOC_PATHS` 檢查

已核對，本檔不在 `gate0_contract_check.py` 的 `DOC_PATHS` 清單內，移入 `closed/` 時無需同步。

---

## 8. 送審聲明

跨文件狀態一致性稽核（第 6 案）的 Gate A 提案、判準、執行結果、PO 裁決三類
處置皆已完成，如上列出完整證據。**本文件為送審文件，尚未結案**。核准後才
執行結案 commit：本檔與 `CROSS_DOC_CONSISTENCY_GATE_A_PROPOSAL.md` 一併
移入 `closed/`，`PROJECT_STATUS.md` §0.2 登記 `CLOSED`（含真實 commit hash）。
