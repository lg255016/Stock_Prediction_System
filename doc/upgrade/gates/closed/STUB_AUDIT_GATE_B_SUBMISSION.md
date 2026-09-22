# 測試 Stub 稽核 Gate B 送審

- 日期：2026-09-08
- 涵蓋：Gate A 提案 + 判準先寫死 + 執行結果 + PO 裁決落地
- 性質：**送審文件**。依 `PRE-G3-04` 已走通的順序執行——**送審 → 複查 → PO 核准 → 結案 commit**。
  本文件尚未移入 `closed/`；核准前 `gates/` 根層維持本檔與其他審查中文件並存。

---

## 0. 一句話

**立案時最擔心的「container 裡也在測假貨」，這次 AS-IS 驗證已經排除了大半——
剩下 ~120 個測試的逐一裁決比對不需要一次窮盡才有意義，改綁事件，債務隨接觸清償。**

---

## 1. 完整 commit 序列

| commit | 內容 |
|---|---|
| `75ebe72` | Gate A 提案（純規劃，未動任何程式碼） |
| `481e7f0` | Gate B 判準先寫死（觸執行前 commit），含 STEP_0 落差查明（「九個」為 `G2_SB7_GATE_B_SUBMISSION.md` 撰寫當時的計算誤植，非後續新增） |
| `56b9bf8` | Gate B 執行結果——部分完成，範圍限制如實揭露 |
| `7c1b13b` | PO 裁決落地：選項 (1) 收尾 + 窮盡覆蓋改綁事件 + `PROJECT_STATUS.md` §0.5 #17 升級 |

---

## 2. 核心結果摘要

### 2.1 AS-IS 逐檔驗證（11 檔，非文件原記載的「九個」）

全部 **0 次真實 psycopg2/socket 呼叫**——stub 作為隔離機制在容器內有效；
發現一個 grep 分類盲點：`test_market_articles_contract.py`／`test_ml_feature_store_contract.py`
用 `DBWriter.__new__()` + 方法級 `MagicMock` 賦值達到與 `@patch` 相同效果，
靜態掃描「僅比對 `@patch(`」偵測不到——**靜態掃描分不出攔截形態的第三個實例**。

### 2.2 獨立發現的既有缺陷（非本次稽核方法設計目標）

`tests/test_ptt_comments.py` 獨立執行會 `ImportError`（tenacity 假 stub 缺
`retry_if_exception`）。根因是該檔 stub guard 只檢查 `sys.modules` 是否已登錄，
不像其他檔案先真的 `try/except import`。**已在容器內獨立重現，證實這不是 host
降級環境獨有，是任何環境下匯入順序不巧即發作的結構性缺陷**——
`discover` 過關是偶然，非設計保證。已同步升級 `PROJECT_STATUS.md` §0.5 #17。

### 2.3 形狀 B 逐測試裁決比對：部分完成

對 `test_canonical_stock_id.py` 一個代表性測試完整執行移除 `@patch` 實驗：
決策由 PASS 變 ERROR（非觸網），確認該攔截是**必要隔離設計的最強形式**，非缺陷候選。
**未窮盡該類別與其餘候選檔案共約 120 個測試**——時間預算內做不到，已誠實揭露。

### 2.4 known-FAIL 構造

已實際執行：對同一測試竄改預期值，確認稽核方法本身有偵測能力
（`AssertionError: '2330' != '9999'`），滿足 `CLAUDE.md` §9A.2。

### 2.5 攔截機制的方法論修正

Python `socket` 層攔截對 psycopg2（libpq C 擴充）**無效**（已構造實驗驗證，
C 擴充直接做 socket syscall，繞過 Python `socket` 模組）；對 `requests`/HTTP **有效**，
DNS（`getaddrinfo`）先於 TCP（`create_connection`）的雙層攔截點確屬必要。
DB 零觸網改以 `DB_HOST`/`DB_PORT` 導向 + `psycopg2.connect` 呼叫包裝達成，
已用真實庫 12 表列數前後快照佐證（完全一致）。**此為日後任何網路攔截類設計都該引用的事實**。

---

## 3. PO 裁決（`7c1b13b`）

**選項 (1) 收尾**：AS-IS 驗證已排除本案立案時最擔心的情境，剩餘窮盡覆蓋
**不排另一輪，改綁事件**——日後任何 SB 修改這 11 檔中任一檔、或其受測模組時，
該檔的逐測試裁決比對隨該 SB 一併執行，沿用本次驗證過的機制。
**理由**：`PROJECT_STATUS.md` §0.5 的既有對照組——「綁事件的規則零漏，綁個案的漏了兩次」。

**三項連帶處置**（`56b9bf8`／`7c1b13b` 已記錄，本節不重複）：
§0.5 #17 升級（tenacity stub 缺陷從 host 現象升級為結構性缺陷，修復去處綁事件）；
grep 分類盲點記入方法節；libpq 不經 socket 層的結論保留供日後引用。

---

## 4. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 / 依據 |
|---|---|---|
| STEP_0 落差查明（九個為計算誤植） | `VERIFIED THIS SESSION` | `git ls-tree 4c6e3f6 tests/` 逐檔核對，見 `STUB_AUDIT_criteria.json` |
| 11 檔 AS-IS 驗證全部 0 次真實 I/O 呼叫 | `VERIFIED THIS SESSION` | 拋棄式 worktree 執行，記錄於 `STUB_AUDIT_result.json.per_file_as_is_run` |
| `test_ptt_comments.py` 容器內獨立執行 `ImportError` | `VERIFIED THIS SESSION` | `python -m unittest tests.test_ptt_comments -v`（容器內，無稽核工具介入） |
| 形狀 B 代表案例 PASS→ERROR | `VERIFIED THIS SESSION` | 見 `shape_b_removal_experiment`，僅 1 測試，範圍已揭露 |
| known-FAIL 構造 | `VERIFIED THIS SESSION` | 見 `known_fail_construction` |
| libpq 繞過 Python socket 層 | `VERIFIED THIS SESSION` | 構造實驗：武裝 socket 攔截後 `psycopg2.connect()` 仍成功連線 |
| 其餘 ~120 個候選測試的逐一裁決 | `NOT VERIFIED` | 範圍限制已揭露，去處見 §3 PO 裁決的 new_rule |

---

## 5. Known-FAIL 對照（`CLAUDE.md` §9A.2）

| 檢查 | known-FAIL 案例 | 實測結果 | 復原確認 |
|---|---|---|---|
| 稽核方法（移除攔截層看裁決是否改變） | 竄改 `test_canonical_stock_id.py` 相關測試的預期 `stock_id` 為錯誤值 | `AssertionError: '2330' != '9999'` | 構造僅於拋棄式 worktree 內執行，主工作目錄未受影響 |

---

## 6. 未驗證清單（有名字、有去處）

| # | 項目 | 現況 | 去處 |
|---|---|---|---|
| 1 | **~120 個候選測試的逐一裁決比對** | 僅 1 個代表案例已執行 | 綁事件：日後任何 SB 觸及 11 檔中任一檔或其受測模組時一併執行（PO 裁決，`7c1b13b`） |
| 2 | **`test_ptt_comments.py` stub guard 缺陷修復** | 已重現，未修復 | 綁事件：下一次修改該檔或 `src/extractors/ptt_scraper.py` 的 SB 一併修正 |
| 3 | **`PROJECT_STATUS.md` §0.5 #17 本身**（`run_all_daily_tasks` 編排耦合） | 「同一家族」，非同一案，未動 | 該項自己的既有建議修法（共用 test double），不歸本案 |

---

## 7. 裁決索引

| 裁決 | 裁決者 | commit |
|---|---|---|
| Gate A 三點確認 + 一項追加防護 | PO 2026-09-08 | `75ebe72` 前置訊息，落地於 `481e7f0` |
| Gate B 執行結果覆核 | 複查方／PO 2026-09-08 | 本輪訊息 |
| 選項 (1) 收尾 + 窮盡覆蓋改綁事件 + §0.5 #17 升級 | PO 2026-09-08 | `7c1b13b` |

---

## 8. `DOC_PATHS` 檢查

已核對，本檔不在 `gate0_contract_check.py` 的 `DOC_PATHS` 清單內，移入 `closed/` 時無需同步。

---

## 9. 送審聲明

測試 Stub 稽核（第 5 案）的 Gate A 提案、判準、執行結果、PO 裁決落地皆已完成，
如上列出完整證據。**本文件為送審文件，尚未結案**。核准後才執行結案 commit：
本檔與 `STUB_AUDIT_GATE_A_PROPOSAL.md` 一併移入 `closed/`，
`PROJECT_STATUS.md` §0.5 移除或標記本項為已收尾（依 §一 new_rule 的形式，
非傳統「已解決」——**該項不會真正關閉，是轉為一條常設規則**，
比照 §0.5 #12 對「常設標準」的既有切法：一次性動作結案，常設標準本身留存）。
