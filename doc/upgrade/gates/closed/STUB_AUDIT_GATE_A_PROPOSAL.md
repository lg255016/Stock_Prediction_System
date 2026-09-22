# 測試 Stub 稽核 —— Gate A 提案

- 日期：2026-09-08
- 性質：**Gate A 提案。Plan-Before-Code —— 本檔未修改任何程式碼或測試，僅規劃與量測方法設計。**
- 依據：`doc/upgrade/gates/closed/G2_SB7_GATE_B_SUBMISSION.md` §7 項目 5（「測試 stub 稽核｜`NOT VERIFIED`｜九個測試檔沿用舊的 `if "x" not in sys.modules` 形態，另案」）、
  `PROJECT_STATUS.md` §0.5 #17（「同一家族」）、`CLAUDE.md` §9A.1（既有先例：97→42 的 runtime 歸因方法）、
  PO 2026-09-08 裁示「第 5 案優先開案」

---

## 0. 一句話

**「哪些測試檔裡出現 `sys.modules` stub」是靜態 grep 能回答的問題；
「換回真實套件後，哪些測試的裁決真的會變」才是稽核要回答的問題——這兩者不是同一件事，
`CLAUDE.md` §9A.1 已經證明過一次（97→42）。**

---

## 1. Goal

1. 以**runtime 歸因法**（非靜態 grep 檔案數）重新盤點「模組層級條件式 stub」
   （`if "X" not in sys.modules: sys.modules["X"] = <stub>`）影響範圍內的測試檔，
   逐檔判定：在容器內（真實套件皆存在）執行時，**該檔的測試裁決是否真的由真實套件的
   行為驅動，還是被檔案內另一層（`@patch`／內嵌 `MagicMock()`）攔在半路，
   使套件在不在场都不影響裁決**。
2. 加一條 §9A.1 原本沒有的軸：**網路觸碰軸**——若移除攔截層，執行是否會嘗試真正對外
   發出請求（HTTP／DB）。這條軸決定「攔截層是否為必要的隔離設計」，
   而非「攔截層是否掩蓋了缺陷」。
3. 產出一份逐檔判定表，供 Gate 3 啟動前收尾此欠帳項目。

## 2. Requirement Source

`G2_SB7_GATE_B_SUBMISSION.md` §7 第 5 項逐字：「九個測試檔沿用舊的
`if "x" not in sys.modules` 形態，另案」——本提案是那個「另案」。

`PROJECT_STATUS.md` §0.5 #17 已指出這與 `run_all_daily_tasks` 編排測試的
mock 耦合問題「同一家族」：**兩者的共同根源是「用 mock／stub 換掉一段程式後，
測試還在測什麼」這個問題沒有機械化答案**。#17 已示範一次實測方法（改動生產路徑，
量測哪些檔案的 mock 因此打破）；本案是同一方法論在**模組層級套件 stub**這個
不同的攻擊面上的應用。

`CLAUDE.md` §9A.1 的既有先例逐字：「以檔案粒度的靜態 `grep` 判斷『哪些測試覆蓋某模組』，
把『測試把該模組換成 stub』讀成『測試覆蓋該模組』……改用 runtime 歸因後，
A 類證據由 97 個縮為 42 個」——**本案是同一個教訓的第二次應用**，範圍從
「哪些測試覆蓋某模組」換成「哪些測試檔的裁決真的被真實套件的行為決定」。

## 3. Current State（唯讀查證，本節無任何推測）

### 3.1 今日重新掃描：11 個檔案，非「九個」

```bash
grep -rln 'sys\.modules\[.*\]\s*=\|not in sys\.modules' tests/
```

| # | 檔案 | 條件式 stub 的套件 | 檔內有無 `@patch` 針對被測物件本身 |
|---|------|-------------------|-------------------------------|
| 1 | `test_db_read_semantics.py` | `pandas`、`psycopg2` | 有——`@patch("src.loaders.db_writer.psycopg2.connect")`（10 處，僅攔 I/O 邊界） |
| 2 | `test_canonical_stock_id.py` | `tenacity`、`yfinance`、`requests` | 有——`@patch("main_etl_pipeline.DBWriter")`／`TwseScraper`／`YFinanceAPI`（攔整個類別） |
| 3 | `test_stationarity_features.py` | `psycopg2` | 無 |
| 4 | `test_time_alignment.py` | `tenacity`、`yfinance`、`requests` | 無 |
| 5 | `test_feature_aggregator_alignment.py` | `tenacity`、`yfinance`、`requests` | 無 |
| 6 | `test_research_features.py` | `tenacity`、`yfinance`、`requests` | 無 |
| 7 | `test_comment_features.py` | `psycopg2` | 無 |
| 8 | `test_market_articles_contract.py` | `psycopg2` | 無 |
| 9 | `test_ptt_comments.py` | `tenacity` | 有——`@patch("time.sleep")`（僅攔重試延遲，非攔網路本身） |
| 10 | `test_ml_feature_store_contract.py` | `psycopg2` | 無 |
| 11 | `test_tracking_keyword_integrity.py` | `pandas`、`psycopg2`、`requests`、`bs4` | 無 |

**⚠ 與 `G2_SB7_GATE_B_SUBMISSION.md` 的「九個」對不上，落差未查明**——
`test_stationarity_features.py`（`UG-G2-SB8`，`bd926a6`）與 `test_tracking_keyword_integrity.py`
（`8ef18cd`，前任團隊遺留檔）皆先於或約於 G2_SB7 結案時已存在，**當時為何未計入「九個」，
本提案不猜測，列為稽核第一步待查明**（見 §6 方法第 0 步）。

### 3.2 保護方式的既有分類（實測分類，非推測）

**A 類——`try/except ModuleNotFoundError`（無條件保護，僅在套件真的不存在時介入）**：
`test_db_read_semantics.py`、`test_stationarity_features.py`、部分見於
`test_time_alignment.py`／`test_feature_aggregator_alignment.py`／`test_research_features.py`
的 `psycopg2` 區塊、`test_tracking_keyword_integrity.py` 的 `pandas`／`psycopg2` 區塊。

**B 類——`if "X" not in sys.modules`（顯式條件，同樣僅在不存在時介入，語意與 A 類相同，
寫法不同）**：其餘 `tenacity`／`yfinance`／`requests`／`bs4` 區塊。

⚠ **A、B 兩類在容器內（§13.0 正式環境，15 套件齊備）語意相同**：兩者的保護分支
**皆不會觸發**，容器內執行到的是真實套件本身。**「哪一種寫法」不是本稽核的分類軸**——
兩者對容器內執行的影響完全相同（零影響）。真正的分類軸是 §3.1 表格第三欄：
**檔內是否還有另一層 `@patch`／內嵌 `MagicMock()`，攔在「真實套件」與「被測邏輯」之間**。

### 3.3 三種形狀，已由靜態讀取初步分出（待 runtime 驗證，非結論）

| 形狀 | 特徵 | 候選檔案 | 初步研判（**未驗證**，見 §6） |
|------|------|---------|------------------------------|
| **形狀 A：I/O 邊界攔截** | `@patch` 目標是套件的**最底層呼叫**（如 `psycopg2.connect`），其上的邏輯（SQL 組裝、資料轉換）仍是真實程式碼 | `test_db_read_semantics.py` | **可能正確**——攔在「不可控外部資源」的最後一道，符合 `CLAUDE.md` §13.5「測試不應依賴真實 DB」 |
| **形狀 B：類別整體替身** | `@patch` 目標是**整個類別**（如 `DBWriter`、`TwseScraper`），該類別內部邏輯完全不被執行 | `test_canonical_stock_id.py` | **需查明**——若這些測試宣稱「驗證資料處理正確性」而非「驗證呼叫順序」，類別整體替身會使裁決與套件真實行為無關，同 §9A.1 的 97→42 情境 |
| **形狀 C：只剩模組層 stub，檔內無任何 `@patch`** | 無第二層攔截，若容器內套件存在，理論上測的就是真實邏輯 | `test_stationarity_features.py`、`test_time_alignment.py`、`test_feature_aggregator_alignment.py`、`test_research_features.py`、`test_comment_features.py`、`test_market_articles_contract.py`、`test_ml_feature_store_contract.py`、`test_tracking_keyword_integrity.py`（8 檔） | **看似安全，但「沒有 `@patch`」不代表「有實際呼叫」**——需確認測試函式本身是否真的呼叫到會用上該套件的路徑（例如某些函式可能根本不含 DB/網路呼叫，套件只是import chain 的副作用，這種情況 stub 與否從未影響任何裁決，屬**假陽性風險**的反面：不是「被掩蓋的缺陷」，是「與缺陷無關的雜訊」） |

---

## 4. In Scope

1. 逐檔（11 個候選 + 待查明的「九個」落差）以 runtime 方法判定形狀 A／B／C 的實際歸屬
2. 對每個判定為形狀 B（類別整體替身）的檔案，**逐測試**（非逐檔案）量測：
   若移除該 `@patch`、換上容器內真實可用的套件／類別，該測試的裁決是否改變
3. 網路觸碰軸：對每個「若移除攔截層會嘗試真正呼叫」的測試點分類標記，
   **不實際觸發網路呼叫**（方法見 §6）
4. 產出逐檔／逐測試判定表，附充分的證據標籤

## 5. Out of Scope（明確排除，不在本案動）

- **`PROJECT_STATUS.md` §0.5 #17**（`run_all_daily_tasks` 編排測試的 mock 耦合）——
  「同一家族」不等於「同一案」，該項已有自己的建議修法（共用 test double），
  本案不重做，僅在 §7 交叉引用其方法論
- **修改任何測試檔或程式碼**——本案是 Gate A（Plan-Before-Code），修正動作待
  Gate B 執行階段、且需先有本提案核准的判準
- **9→11 落差的歷史考古**（為何 G2_SB7 沒算到後兩檔）——列為稽核執行時的
  第一步查明項，不在 Gate A 規劃階段猜測結論

---

## 6. 方法（判準寫死，執行前必須核准）

### 6.0 第 0 步：落差查明

讀 `G2_SB7_GATE_B_SUBMISSION.md` 撰寫當下（`4c6e3f6` 前）的 `tests/` 目錄快照，
比對是否確實只有 9 個檔案符合 §3.1 的 grep 條件。**若確認當時就是 11 個、「九」是
計算錯誤，據實記錄；若確認當時確實是 9 個、後兩者是新增，記錄新增的觸發時點。**
兩種結果都合法，重點是**不得不查就寫「九個」或「十一個」二選一**。

### 6.1 第 1 步：逐檔形狀分類（已完成初步，見 §3.3，本步驟為 runtime 驗證）

對每個候選檔案，在容器內以 `unittest.mock.patch` 疊加一層**呼叫計數器**於
「§3.1 第三欄的攔截目標」與「該攔截目標底下最近一層真實套件函式」兩點，
執行該檔全部測試，記錄：

- 真實套件函式是否被呼叫過（次數 ≥ 1 即形狀 A／C；0 次且測試仍 PASS 即形狀 B 候選）
- 若為形狀 B 候選，**移除該 `@patch`**（暫時，於拋棄式副本執行，不改動版控檔案），
  重跑該檔測試：
  - 若因此嘗試真正對外連線（DB／HTTP），**必須在連線建立前以獨立的、範圍更小的
    攔截攔下**（例如攔 `socket.create_connection` 而非攔整個類別），**目的僅是
    確認「若無攔截會不會撥出去」，不是真的撥出去**——這正是網路觸碰軸的量測方法，
    不違反 `CLAUDE.md` §13.5
  - 若測試在此條件下依然 PASS 且未觸網，代表真實邏輯本身撐住了斷言——歸形狀 A
  - 若測試 FAIL 或會觸網，代表該 `@patch` 是必要的隔離設計，歸類為「**已知需要
    隔離，且隔離正確**」，非缺陷

### 6.2 第 2 步：逐測試裁決比對表

對每個形狀 B 確認案例，產出：

| 檔案 | 測試名稱 | 移除 `@patch` 前裁決 | 移除後（不觸網前提下）裁決 | 是否改變 | 網路觸碰 |
|---|---|---|---|---|---|
| … | … | PASS/FAIL | PASS/FAIL/無法判定（會觸網） | 是/否 | 是/否 |

**判準**：裁決改變 = 缺陷候選（該測試先前的 PASS 不是被真實邏輯撐住的）；
裁決不變且未觸網 = 安全，`@patch` 可能是多餘的（非缺陷，屬簡化機會）；
會觸網 = `@patch` 是必要隔離，非缺陷，**不需要拿掉**，本項只需記錄理由。

### 6.3 已知會 FAIL 的案例（`CLAUDE.md` §9A.2 要求）

本稽核方法本身必須能被證明「不是永遠通過的檢查」。**known-FAIL 構造**：
在一個已知形狀 B 的檔案（如 `test_canonical_stock_id.py`）人工把某個
`@patch("main_etl_pipeline.DBWriter")` 覆寫的回傳值改成明顯錯誤的資料
（例如讓 mock 回傳的股票代碼與斷言不符），確認稽核方法的「移除攔截層重跑」
步驟會如實回報「移除前後裁決不同」——若這個構造案例被判定為「無變化」，
代表量測方法本身有漏洞，稽核方法需重新設計。

---

## 7. Failure Semantics & Definition of Done

| 項目 | 判準 |
|---|---|
| 落差查明 | §0 步驟有明確結論（哪一年、哪個 commit，或確認「九」為計算誤植） |
| 逐檔分類 | 11 個候選檔案（或查明後的實際數字）皆有形狀 A／B／C 的 runtime 驗證結論，非僅靜態初判 |
| 形狀 B 逐測試裁決比對 | 每個形狀 B 候選檔案的**每個相關測試**皆有本檔 §6.2 表格的完整列 |
| 網路觸碰分類 | 每個「移除攔截層會觸網」的測試點皆有記錄，且過程本身未真正觸網（唯讀原則，同 `PRE-G3-01`／`03` 的觸網前寫死判準精神） |
| known-FAIL | §6.3 構造案例已實際執行並確認方法可偵測 |
| 不修改任何程式碼／測試檔 | 本案全程唯讀（Gate A 階段），`git status --porcelain` 除本提案與其產出證據 JSON 外無其他變更 |

## 8. E2E Verification

1. `python -m unittest discover -s tests -p "test_*.py"`（容器內，確認稽核過程未意外修改任何檔案，基線不變）
2. `python scripts/verify/gate0_contract_check.py`（EXIT=0，確認未觸及受驗契約文件）
3. 逐檔／逐測試判定表完整產出，存於 `doc/upgrade/gates/evidence/STUB_AUDIT_*.json`

## 9. Documentation Sync

- `PROJECT_STATUS.md` §0.5 #17：若稽核結果與 #17 的既有建議（共用 test double）產生交集，
  於該項追記交叉引用，不重寫其內容
- `G2_SB7_GATE_B_SUBMISSION.md` §7 項目 5：**該檔屬 `closed/`，依 §16.2 不得修改**——
  本案的稽核結果不回頭改寫它，僅在本提案與後續 Gate B 送審文件中承接
- 若稽核發現任何測試裁決確實被錯誤掩蓋（形狀 B 且裁決改變），依 `CLAUDE.md` §14
  的「新增 bug fix 時應先建立會重現問題的測試」原則，另案（Gate B 執行階段）處理，
  不在本 Gate A 階段搶修

---

## 10. 待 PO 於 Gate A 核准時確認的三點

1. **§6.1 的「移除 `@patch` 重跑」是否需要拋棄式副本執行，還是可直接在工作目錄暫時
   註解後還原**——兩者皆需遵守 `CLAUDE.md` §11A（若涉及檔案暫時修改再還原，
   不得使用受管制的破壞性指令鏈式寫法）
2. **網路觸碰軸的攔截粒度**（§6.1 建議攔 `socket.create_connection` 而非攔整個類別）
   是否同意，或有更精確的攔截點建議
3. **形狀 B 且裁決改變的案例，是否在本案內只記錄不修，還是需要立即另開 Gate B**——
   提案傾向前者（本案是 Gate A 規劃 + 稽核執行，修正是下一步），但明確請 PO 確認
