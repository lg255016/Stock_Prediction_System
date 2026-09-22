# UG-G2-SB7 Gate B 送審：批次化 ETL 與失敗容忍

- 日期：2026-09-05
- 對應提案：`doc/upgrade/gates/G2_SB7_GATE_A_PROPOSAL.md`（PO 已核准）
- 追加提案：`G2_SB7_ROUND_B_DESIGN.md`（B 輪）、`G2_SB7_ITEM5_PROPOSAL.md`（第 5 項）
- 目標資料庫：**`postgres`@`localhost:5432`**（`gate-submit` 產出 7）

---

## 0. 三句話說完這個 SB

1. **每日取價由 150 個請求變成 2 個**（每市場 1 個報表請求），
   社群取數由 25 次搜尋變成**至多 25 頁、與關鍵字數脫鉤**的一次看板抓取。
2. **失敗不再長得像「沒有資料」**：`etl_run_log` 四態 outcome 落地
   （`OK`／`NO_DATA`／`FETCH_FAILED`／`REFUSED` —— ⚠ **與
   `daily_ml_features.source_status` 的四態是兩回事**，後者見 §7.1，
   **兩個欄位都有四態 CHECK，而目前一個滿了、一個沒滿**），
   `SOURCE_FAILED` 的列情緒欄強制 NULL，DEC-032 的三處生產違反已修正。
3. **本 SB 沒有做完的事，在 §7 逐項列出** ——
   而 2026-09-05 的**單次受控執行**（§13）把其中三項補上了，
   **同時抓出一個生產缺陷（E3）**：看板回溯被置底公告靜默截斷，
   **一次被截斷的抓取回報成 `OK`**。已修（`bccffa9`），
   **但頁數的量測仍是 `NOT VERIFIED`** —— 修正不產生新的量測。

---

## 1. `gate-submit` 產出 1：契約驗證原始輸出

容器內執行：

```
python scripts/verify/gate0_contract_check.py
```

```
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約)
       — DRIFT-007，排定 UG-G1-SB5 修訂
B12  PASS | 特徵契約需要的 DB 欄位，讀取端皆有 SELECT（反查法）
       契約需求 13 欄；讀取端缺 0；未涵蓋 2 類
       [未涵蓋] 四個 CORE_16 平穩化特徵的「資料來源」欄為
                「待實作於 feature_aggregator.py」——自然語言，無法對應到具體 DB 欄位
       [未涵蓋] 題材溢出（theme_stock_mapping）與 entity_mapping 的欄位需求——
                由獨立查詢取得，不在 fetch_all_for_features 的兩句 SELECT 內

==================================================
Part B: 12/12 PASS
EXIT=0
```

**`WARN` 行與 B12 的兩項未涵蓋皆未過濾**（提案 §0.4 (一) 的承諾）。

---

## 2. 產出 2：執行環境 + 測試 + 依賴狀態

### 2a. 執行環境

| 欄位 | 內容 |
|------|------|
| 執行環境 | **container** |
| 容器名稱 | `stock_prediction_system2_devcontainer-app-1` |
| Python 版本 | `Python 3.14.6` |

### 2b. 測試原始輸出

```
Ran 422 tests in 32.749s

OK
```

### 2c. 依賴狀態

```
numpy                      PRESENT
pandas                     PRESENT
sklearn                    PRESENT
lightgbm                   PRESENT
xgboost                    PRESENT
psycopg2                   PRESENT
jieba                      PRESENT
snownlp                    PRESENT
tenacity                   PRESENT
dotenv                     PRESENT
```

**全部 PRESENT**，無 fallback 路徑。

### 2d. ⚠ host 的結果本次刻意不採用，理由值得記

`tests/test_ptt_board_pages.py` **單獨在 host 執行會得到**：

```
ModuleNotFoundError: No module named 'tenacity'
```

而**全套 `discover` 在 host 上會過** —— 因為別的測試檔在它之前塞了 `tenacity` stub。

> **同一個耦合，一邊讓改動打破無關的檔案，一邊讓無關的檔案替改動遮住失敗。**

這是 §0.5 #17 的另一面。**若本次以 host 的全綠交差，
第 5 項的六項檢查會在一個「靠別的檔案才跑得起來」的環境下宣稱通過。**

---

## 3. 產出 3：Commit 檔案清單與逐檔授權稽核

本 SB 的 commit（依時序）：

| commit | 範圍 |
|--------|------|
| `0047d98` | DEC-032 三處生產違反 |
| （A 輪數個） | `etl_run_log`／migration 007／批次取價／逐股迴圈失敗容忍 |
| （B 輪數個） | 四態 `source_status`、`SOURCE_FAILED` 列強制 NULL、網路守衛 |
| `afd7e16` | 第 5 項 **V6~V11 紅**（實作之前） |
| `4de6fae` | 第 5 項實作 + 契約 §3.1／§3.4／§3.5A |
| `5afc644` | 第 5 項 **V12 紅** |
| `2de3ad3` | V12 修正 + 每日任務接線 + §0.5 #17 追記 |

### 超出核准清單的檔案【§12.3 主動揭露】

| 檔案 | 狀態 | 理由 |
|------|------|------|
| `src/transform/source_capabilities.py` | **超出第 5 項核准的六項檢查** | 見 §5.3；**複查方 2026-09-05 追認**：「不是範圍蔓延，是我指定的條件 2 的直接後果」 |
| `tests/test_operational_ux.py` | **超出** | 接縫由 `run_ptt_pipeline` 移至 `run_ptt_board_pipeline`，mock 需同步 |
| `tests/test_ptt_failure_is_recorded.py` | **超出** | 見 §5.2；**已取得裁決** |
| `doc/governance/PROJECT_STATUS.md` | **超出** | 複查方指定併入 §0.5 #17 |
| `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` | 在授權內 | 第 5 項條件 2 明文要求寫入契約 |

---

## 4. 產出 4：格式／行尾夾帶偵測

**本 SB 內 pre-commit 檢查 2 共觸發 6 次**（整體第 1~6 次）：

| # | commit | 判定 | 成因 |
|---|--------|------|------|
| 1~3 | A 輪 | **誤報** | 縮排位移 |
| 4 | `84e1598` | **檢查 2 是對的** | `yfinance_api.py` 的真實空白變更 |
| 5 | B 輪 | **誤報** | 縮排位移（縮排減少） |
| 6 | `2de3ad3` | **誤報** | 縮排位移，見下 |

> ⚠ **必須分得開**：六次不是六次誤報，是**五次誤報、一次正確**。
> 把它們寫成同一件事，等於在紀錄上把那一次正確攔截也變成雜訊。

### 第 6 次（`2de3ad3`）的逐行成因

```
main_etl_pipeline.py                    95/15  vs -w  90/10
tests/test_ptt_failure_is_recorded.py  113/34  vs -w 109/30
```

9 行**全部**為縮排位移：

- `main_etl_pipeline.py`（5 行）：`try:`／`except Exception as exc:` 及兩行註解
  **移出 `for kw` 迴圈**（退 4 格）；一行 `keyword_entries.append(RunLogEntry(`
  **移入新迴圈**（進 4 格）。
- `tests/test_ptt_failure_is_recorded.py`（4 行）：`if kw == "廣達":` 移除後，
  四行 `raise`／續行字串各退 4 格。

複查方獨立驗證：**兩檔去縮排後多重集合相同 = `True`**，
且 `-w` 仍顯示大量結構變更（90/10、109/30），**位移由那些變更解釋**。
方向為混合（12→8、16→12、25→29）—— **而方向不是判準**。

`--no-verify` 由 PO 於 2026-09-05 授權（僅該次 commit）。
停用的另三項檢查已手動執行並貼於 commit message：
契約驗證 `12/12 PASS`／`exit 0`、秘密檔案未偵測到、staged 清單 6 檔。

---

## 5. 本 SB 的實質交付

### 5.1 DEC-032 的三處生產違反

| 位置 | 修正 |
|------|------|
| `ptt_scraper._fetch_page` | `@retry` 加上 `retry_if_exception(is_retriable)` |
| `market_report_fetcher` | 同上，共用 `src/extractors/retry_policy.py` 的單一判別式 |
| `yfinance_api` | **不宣稱符合** —— `@retry` 移除，模組 docstring **第一段**逐字寫明「本模組**不符合 DEC-032**，也不宣稱符合」 |

判別式只有一份（`is_retriable()`）：**沒有 `status_code` → 重試；5xx → 重試；4xx → 硬停。**

**生產實測證據**（`etl_run_log` `run_id=11`）：

```
(11, 2026-09-04 06:39:52, 'tpex_daily_quotes', '2026-09-03', 'tpex', 'OK',
     None, 'postgres', http_attempts=3, ...)
```

> **有界重試在真實執行中實際觸發過，第 3 次成功。**
> 這不是單元測試的 mock —— 是 `http_attempts = 3` 且 `outcome = OK` 的一列。

### 5.2 第 5 項：社群取數由逐關鍵字搜尋改為看板固定頁面

六項核准檢查 **V6~V11 全 PASS**，`known-FAIL` 見 §6。

#### ⚠ 逐關鍵字失敗隔離的損失，**比第一版描述的更窄**

A 輪那兩個測試釘的其實是**兩個不同的性質**（複查方 2026-09-05 裁決）：

| | 性質 | 批次模式下 |
|---|------|-----------|
| (a) | 迴圈不得中止 —— **每個關鍵字都要有一筆紀錄** | **保留**（三筆 `FETCH_FAILED`，非靜默） |
| (b) | 一個失敗，其餘仍 `OK` | **僅在「完全沒抓到」時消失** |

**(b) 沒有全部消失。** 降級批次下**命中的關鍵字仍是 `OK`** ——
隔離在「抓到多少」的粒度上還在。
**真正歸零的只有「第一頁就失敗」那一種，而那時我們確實對每個關鍵字一無所知
—— 那不是損失，是誠實。**

> **本節刻意不寫成「隔離已被交換掉」** —— 後者把一個窄的、
> 且在總失敗時為套套邏輯的結果，講成一個全面的退讓。

**為什麼不把隔離救回來**：唯一的路是「失敗後回退逐關鍵字模式」，
**那等於在站方拒絕我們之後再送 25 個請求 —— 正是 DEC-032 硬停要防的行為。**

新增的**反向釘子**是本節最重要的東西：**批次正常時「沒命中」→ `NO_DATA`**。
沒有它，會反過來把「真的沒人討論」偽裝成故障，
**而 RISK-015 的覆蓋率量測正是靠這個區別。**

改寫後的測試 docstring **保留 A 輪的原始語意與變更理由** ——
否則下一個人只會看到新語意，不知道隔離曾經被考慮過。

### 5.3 施工中發現：換掉 `source` 值會悄悄關掉一項能力（V12）

`COMMENT_DIRECTION_SOURCES` 原為 `frozenset({"ptt_stock"})`。
新模式的 `source` 是 `ptt_board_pages`，**不在集合裡** ——
`provides_comment_direction()` 對**每一列新資料**回傳 `False`，
`comment_polarization` 與 `net_push_momentum` 全部變 `NULL`，
**而那兩個特徵用的是同一批 PTT 內頁，方向能力一點都沒少。**

**它為什麼不會自己被發現**：該模組的預設方向是**刻意 fail-safe** 的
（docstring 逐字：「漏登錄的後果 → 方向類特徵為 `NULL`（**誠實地少**）」）。

> **那個設計是對的，而它正是這個缺陷不會報錯的原因。兩件事同時為真。**
>
> **一個 fail-safe 的預設，讓漏登錄變成一件不痛的事。**
> **不痛的事不會被記得 —— 所以它需要一個檢查，而不是靠記得。**

修法：三值全部登錄；V12 對照 `ptt_scraper` 的三個常數，
**並帶反向釘子**（`dcard`／`threads` 仍須無方向），
以免有人為了讓 V12 過而把本表改成「全部都算」——
那正好會做出 docstring 說的「安靜地錯」。
教訓已寫進 `source_capabilities.py` 的 docstring：**該模組的下一次擴充會再遇到同一件事。**

### 5.4 【獨立列出】契約文件裡活著的 DEC-032 違規

`MULTI_SOURCE_DATA_CONTRACT.md` §3.4 原文**逐字**：

```
| 429/5xx 處理 | response.raise_for_status() 觸發 tenacity 重試，等待 2s, 4s, 8s |
```

**那正是 DEC-032 禁止的行為，而契約文件自己記載了它。**

A 輪修 `ptt_scraper.py` 的 docstring 時**只改了程式、沒有回頭改契約**，
於是同一句話又在文件層存活了一輪，直到第 5 項施工時才被撞到。

> **契約優先序高於程式碼（`CLAUDE.md` §0.2）—— 這份殘留比程式裡的那份更危險：**
> **程式裡的違規會被測試抓到，文件裡的違規會被當成要求照做。**

**這個形狀在本專案還沒有被記錄過**（複查方 2026-09-05 指定獨立列出）：
「修了實作沒修契約」與已登記的 DRIFT 系列不同 ——
後者是**兩份文件互相矛盾**，本例是**文件與已核准的 ADR 矛盾，而文件贏**。

已於 `4de6fae` 修正，並在原處留下記錄說明它為什麼會活下來。

### 5.5 §6 規模預期的比對【取數前寫死，跑完只做比對】

| # | 項目 | 預期（提案 §6，取數前寫死） | 實測 | 判定 |
|---|------|------|------|------|
| 1 | 每日股價請求數 | 每市場 **1 個邏輯請求** | `etl_run_log` 每批 2 列（twse／tpex 各 1） | **符合** |
| 2 | 單日 `candidate_prices` 新增列數 | TWSE **950~1,130**、TPEx **780~930** | 2026-09-03：TWSE **1,085**、TPEx **887** | **兩者皆在區間內** |
| 3 | 批次總結三數之和 | **= 項目數** | 三次批次各 2/2 | **符合** |
| 4 | `target_database` | 每列非空且 = `current_database()` | 6/6 皆為 `postgres`，**NULL 0 列** | **符合** |
| 5 | `daily_ml_features` / `stock_prices` | **維持 117 / 117** | **117 / 117** | **符合** |

> §6 的區間是**取數之前寫死**的，且第一版的推導曾被自己推翻過
> （「單日 ≤ 60 日聯集」在結構上必然成立，產生不出那兩個數字）。
> **修正後的區間兩個都命中，而它們是在看到結果之前定下來的。**

---

## 6. 產出 6：known-FAIL 案例對照表

| 檢查 | known-FAIL 構造 | 實測原始輸出 | 復原確認 |
|------|----------------|-------------|---------|
| **V1** 403/429 不重試 | 對修正前的程式碼直接執行 | 嘗試次數 3 ≠ 1 → FAIL（A 輪，紅已進歷史） | 修正後轉綠 |
| **V3** 失敗不得讀成無資料 | 讓 `SOURCE_FAILED` 列走原本的 `fillna` | `article_count` 為 0 而非 NULL → FAIL | 同上 |
| **V6** 新模式的 source 值 | 改用 `SOURCE_LEGACY` | `FAIL: AssertionError: np.False_ is not true` | 已還原，檔案內容比對相符 |
| **V8** 請求預算 | 迴圈條件放寬為 `page_budget * 2` | `FAIL: AssertionError: 50 != 25` | 同上 |
| **V10** 預算用盡的處置 | 用盡後不設 `SOURCE_DEGRADED` | `FAIL: AssertionError: 'OK' != 'SOURCE_DEGRADED'` | 同上 |
| **V12** 能力宣告 | 即現況（只登錄 `ptt_stock`） | `AssertionError: 'ptt_keyword_search' not found in frozenset({'ptt_stock'})` | **紅已進歷史 `5afc644`** |

### ⚠ 逐案檢查了 `FAIL:` 與 `ERROR:` 的前綴

**三個新案例都是 `FAIL:`（斷言觸發），不是 `ERROR:`（collection 失敗）。**

> 本 SB 的 yfinance 示範**曾因這個區別作廢一次**：
> 還原整個舊檔造成 collection 失敗，那不是「檢查抓到了」，是「測試根本沒跑起來」。
> 兩者在退出碼上完全一樣。

構造腳本依 `CLAUDE.md` §11A.4 以 Python + `finally` 撰寫
（`scratchpad/known_fail_item5.py`），還原後逐檔比對內容相符，
`git status --porcelain` 只剩該輪本來就在改的檔案。

---

## 7. 【最重要】本 SB **沒有**做完的事

| # | 項目 | 標籤 | 具體未驗證範圍 |
|---|------|------|---------------|
| 1 | 社群端的切換已在生產執行過一次 | **已執行**（§13），**但頁數量測 `NOT VERIFIED`** | 那一次被 E3 截斷（只抓 1 頁），修正後**未再執行**。頁數的有效量測需要再跑一次 |
| 2 | 切換後的 `source_status` 分佈 | `NOT VERIFIED` | **兩個成因**（§13.7）：15 列錯置文章 + E3 截斷。**兩者都處理完才重測** |
| 3 | `yfinance` 路徑落地後的實際呼叫對象 | **已出示**（§13.1 E8） | `etl_run_log` 的 `tracked_stocks_daily` 4 列；NVDA 是唯一走 yfinance 的 |
| 3b | **既有 331 列的 `post_time`（76 列錯誤）** | `VERIFIED THIS SESSION`（是實測，**不是**已解決） | 新寫入已修（`e67d3d6`），**既有列未修**；處置待 PO 裁決 |
| 4 | `total_comments` 全為 NULL | `VERIFIED THIS SESSION`（是實測，**不是**已解決） | 331 篇文章**一列都沒回填成功**。已併入 RISK-015 |
| 5 | 測試 stub 稽核 | `NOT VERIFIED` | 九個測試檔沿用舊的 `if "x" not in sys.modules` 形態，另案 |

### 7.1 `source_status` 的實際態數【決策點 3 附帶要求】

**必須區分「不會失敗」與「沒接線」** —— 逐層回答：

| 層 | 四態的可達性 |
|----|-------------|
| `002_expand_ml_features.sql:86` 的 CHECK | 允許**四態** |
| `feature_aggregator` 程式**可產出** | **三態**（`SUCCESS`／`SUCCESS_EMPTY`／`SOURCE_FAILED`） |
| `daily_ml_features` **實際資料** | **兩態**：`SUCCESS` 37、`SUCCESS_EMPTY` 80 |

> **本 SB 仍寫「三態可達」，不寫「四態已實作」。**

**`SOURCE_DEGRADED` 仍不可達 —— 但阻塞點變了，這件事必須記下來：**

- **B 輪時**：`feature_aggregator.py:562` 的理由是
  「`scrape_ptt_stock_by_keyword` **不回報那個粒度**」——**extractor 給不出來**。
- **第 5 項之後**：`scrape_ptt_board_pages` **回報了那個粒度**（部分成功 = `SOURCE_DEGRADED`），
  但 `run_ptt_board_pipeline` 把它折成 `etl_run_log` 的 `FETCH_FAILED`，
  **沒有一條路把它送進 `daily_ml_features.source_status`**。

**阻塞由「取不到」變成「沒接線」。**
`feature_aggregator.py:562` 的註解**現在是過期的**（它說 extractor 不回報，但已經回報了），
**已登記為本 SB 的遺留項，不在本 SB 內修** ——
接線需要決定「一天之內部分關鍵字降級」如何映射到逐股票的 `source_status`，
那是一個設計問題，不是一行改動。

---

## 8. 產出 5：證據標籤表

| 宣稱 | 標籤 | 可重跑指令／不可重跑原因 |
|------|------|------------------------|
| 422 tests OK | `VERIFIED THIS SESSION` | 容器內 `python -m unittest discover -s tests -p "test_*.py"` |
| contract-check `exit 0`、`12/12 PASS` | `VERIFIED THIS SESSION` | 容器內 `python scripts/verify/gate0_contract_check.py` |
| V1／V3／V6／V8／V10／V12 具偵測能力 | `VERIFIED THIS SESSION` | `scratchpad/known_fail_item5.py`（第 5 項三案） |
| 單日 TWSE 1,085／TPEx 887 | `VERIFIED THIS SESSION` | 對 `postgres`@`localhost:5432` 的唯讀查詢，SQL 見 §5.5 |
| `etl_run_log` 6 列、`target_database` 全為 `postgres` | `VERIFIED THIS SESSION` | 同上 |
| **有界重試在生產觸發過**（`http_attempts=3` 且 `OK`） | `VERIFIED THIS SESSION` | `SELECT * FROM etl_run_log WHERE run_id=11` |
| `daily_ml_features`／`stock_prices` = 117/117 | `VERIFIED THIS SESSION` | 同上 |
| 一次執行的 HTTP 請求 ≤ 25 | `VERIFIED THIS SESSION`（**單元測試層**） | V8；⚠ **不等於生產已量測** |
| **首次生產執行的實際頁數** | `NOT VERIFIED` | `run_all_daily_tasks` 真實執行暫緩 |
| **切換後 `source_status` 分佈** | `NOT VERIFIED` | 同上 |
| **`yfinance` 落地後的實際呼叫對象** | `NOT VERIFIED` | 逐股迴圈未在生產跑過 |
| pg_dump 備份可還原 | `PREVIOUSLY VERIFIED` | 紀錄位置：`UG-G2-SB6` 的還原實測；本次未重跑 |
| §0.1 的取捨可接受 | `ENGINEERING JUDGMENT` | 不可重跑；理由見 §5.2，**已經複查方裁決成立** |
| `BOARD_LOOKBACK_DAYS = 2` | `ENGINEERING JUDGMENT` | 不可重跑；每日跑 1 天即足夠，取 2 天為「昨天沒跑成」留一天重疊 |
| `BOARD_PAGE_BUDGET = 25` | `ENGINEERING JUDGMENT` | 不可重跑；**25 是我們已經在用的量，不因換模式而增加**（25 關鍵字 × 1 頁）。**那是一個約束，不是一個門檻** |

---

## 9. Definition of Done 逐項核對（提案 §9）

| # | DoD 項目 | 狀態 |
|---|---------|------|
| 1 | 四個決策點經 PO 裁決**後**才實作 | **達成** |
| 2 | V1 已先跑出 FAIL，修正後轉綠 | **達成** |
| 3 | `etl_run_log` 建立於 `postgres`@`localhost:5432`；前置 `pg_dump` 已實測還原 | **達成**（`schema_version` = 7） |
| 4 | **一次完整的每日批次已對 `postgres` 執行，三態總和 = 項目數** | **達成**（2026-09-05 受控執行，§13）—— 逐來源總數 = 項目數：批次 2／逐股 4／關鍵字 26 |
| 5 | `etl_run_log` 每列 `target_database` = `postgres` | **達成**（6/6，NULL 0 列） |
| 6 | `daily_ml_features`／`stock_prices` 維持 117/117 | **達成** |
| 7 | `candidate_prices` 新增列數符合 §6 第 2 項 | **達成**（TWSE 1,085、TPEx 887，皆在區間內） |
| 8 | V1–V5 全通過，V1、V3 各出示實際 FAIL | **達成** |
| 9 | 三處 DEC-032 違反已修正或明確標示不適用 | **達成** |
| 10 | 逐來源列出 `source_status` 實際態數並說明 | **達成**（§7.1，三層分開陳述） |
| 11 | `yfinance` 落地後的實際呼叫對象已出示 | **達成**（§13）—— `etl_run_log` 的 `tracked_stocks_daily` 4 列；日誌顯示 6488 由 `candidate_prices` 供應，**NVDA 是唯一走 yfinance 的** |
| 12 | `fetch_yfinance_data` 明確傳入 `auto_adjust=` | **達成**（`AUTO_ADJUST = True` 顯式傳入） |
| 13 | 全套測試容器通過；contract-check exit 0；無夾帶格式變更 | **達成**（格式：五次誤報、一次正確，逐次揭露於 §4） |
| 14 | `gate-submit` 八項產出齊備，Gate B 與提案同時在 `gates/` 根層 | **本文件即第 14 項** |
| 15 | 過程文件於 PO 核准後的結案 commit 移入 `closed/` | **待核准後執行**（§10） |

> **第 4 與第 11 項原本未達成，成因同一個：`run_all_daily_tasks` 的真實執行暫緩。**
> **2026-09-05 的單次受控執行解除了那個暫緩（僅一次），兩項因此達成。**
>
> ⚠ **「不以『批次階段已執行』代替『完整每日任務已執行』」這條仍然有效** ——
> 它擋掉的是最方便的那條路，而本次是**真的跑了完整的每日任務**，不是拿批次充數。

---

## 10. 產出 8：結案時的文件搬移（**待 PO 核准後執行**）

| # | 問題 | 答案 |
|---|------|------|
| 1 | Gate A 提案與 Gate B 送審文件是否已 `git mv` 至 `closed/`？ | **尚未** —— 依 §16.3 規則 6，搬移是**核准後結案 commit 的一部分** |
| 2 | 待搬移清單 | `G2_SB7_GATE_A_PROPOSAL.md`、`G2_SB7_ROUND_B_DESIGN.md`、`G2_SB7_ITEM5_PROPOSAL.md`、`G2_SB7_GATE_B_SUBMISSION.md`（**四份**） |
| 3 | 本次關閉的是整個 Gate 嗎？ | **否** —— Gate 2 未關閉，`GATE2_STARTUP_APPLICATION.md` **不動** |
| 4 | 被搬移的檔案是否在 `gate0_contract_check.py` 的 `DOC_PATHS`？ | **否**（已查證，`DOC_PATHS` 不含任何 Gate 提案） |
| 5 | `doc/README.md` 是否需同步？ | **需要** —— 四份過程文件的位置變更 |

---

## 11. 遺留項與後續

| 項目 | 去向 |
|------|------|
| `SOURCE_DEGRADED` 接線（阻塞點已由「取不到」變成「沒接線」） | **本 SB 遺留**，見 §7.1 |
| `feature_aggregator.py:562` 註解已過期 | 同上，隨接線一併修 |
| 九個測試檔的 stub 形態稽核 | 另案（與 §0.5 #17 同一家族） |
| RISK-015（含 `total_comments` 實測為零） | 已更新，Gate 3 啟動前檢視 |
| RISK-022（價格調整基礎） | 面向一已補記；其餘未動 |
| §0.5 #17（測試替身耦合） | 第五次表現已併入，**含「擋住連鎖的是 mock 得更深，不是耦合更少」** |

---

## 13. 【2026-09-05 追加】單次受控執行

> 複查方 2026-09-05 §八：**暫緩解除，但只解除一次。**
> **一次受控執行與開放例行執行是兩件事；不得用一次成功的執行去換一個常態授權。**

預期於執行**之前** commit（`1e12068`），結果 commit `a3e926c`。
完整逐項對照見 `evidence/G2_SB7_controlled_run_expectations.json` 與
`evidence/G2_SB7_controlled_run_results.json`。

- 綁定確認：`current_database=postgres`／`port=5432`／`user=postgres`／`addr=::1`／PostgreSQL 18.6
- 前置備份：`70,610,889` bytes，md5 `63ce0b267cc132575aa7b80c4abcbe24`，
  `pg_restore -l` 可讀、11 個 TABLE DATA
- 執行：`python main_etl_pipeline.py` **一次**，`EXIT=0`

### 13.1 結果：8 項 PASS、1 項假通過、1 項是我的檢查寫錯

| # | 項目 | 結果 |
|---|------|------|
| E1 | 每市場 1 個邏輯請求 | PASS |
| E2 | 單日列數 | **TWSE 1,085／TPEx 887，第二次落在取數前寫死的區間內** |
| E3 | 看板實際頁數 | ⚠ **假通過，見 §13.2** |
| E4 | 新文章 `source` | PASS（`ptt_board_pages` 1 列，既有 331 列未動） |
| E5 | 既有 117 列的值不得變 | PASS —— **但第一次比對報 FAIL，見 §13.3** |
| E6 | §7.3 軟刪除不變量 | **PASS —— 見 §13.4** |
| E7 | Gemini 呼叫 | PASS（既有 331 篇 0 次） |
| E8 | 6488 由 `candidate_prices` 供應 | **PASS —— DoD 第 11 項的證據到位** |
| E9 | 逐來源 outcome 總數 = 項目數 | PASS（2／4／26） |
| E10 | `target_database` | PASS（全為 `postgres`，NULL 0 列） |

### 13.2 E3：一個**假通過**，而它假通過的方式正是本 SB 的主軸

```
[Extract] 已回溯至 1768934799 <= 1788414806，停止翻頁。
[Extract] 看板頁面模式完成：1 頁請求，1 筆命中，outcome=OK
```

`1768934799` = **2026-01-21**，**而那是看板最新的一頁**。
PTT 的置底公告時間戳很舊，而停止條件用 `min(全頁時間戳)` ——
**被置底文一次擊沉。**

> ⚠⚠ **它讓被截斷的抓取看起來像成功的回溯。**
> outcome 回報 `OK` 而不是 `SOURCE_DEGRADED`，因為程式相信自己已回溯到目標時間。
> 於是 **25 個關鍵字拿到 `NO_DATA`，在 run log 裡宣稱「那天沒有討論」——
> 實際上是我們只看了一頁。**

**E3 的界寫的是 1~25 頁，實測 1 頁落在界內 —— 而落在界內不等於對。**
**一個區間判準通過，不代表被量的東西是對的。**

**修正**（V13 紅 `a9f1778` → 綠 `bccffa9`）：停止依據由 `min` 改為 **`max`**。

> **置底文的時間戳是「舊」的：它拉低 `min`，永遠不會拉高 `max`。**
> 用 `max` **不必知道它在哪、也不必知道頁內怎麼排**；
> 我原本提的「取第一個 `r-ent`」則依賴兩個推論，**需要一次線上抓取查證**。

⚠ **E3 的頁數量測仍是 `NOT VERIFIED`** —— 修正只保證截斷會被記成
`SOURCE_DEGRADED`，**沒有產生新的量測**；那需要再一次執行。

### 13.3 E5：第一次比對報 FAIL，是**我的檢查**寫錯

指紋 `52a1687…`／**118 列** vs 預期 `0d80953…`／117 列。

成因：**我把「既有列的值不變」寫成了「該日期範圍內的列不變」。**
執行前快照記載 NVDA 最大 `trade_date` 是 **2026-08-20**，
本次 yfinance `period=3mo` 補上 **08-21** —— **那是全新資料，不是既有列被改。**
扣掉 `(NVDA, 2026-08-21)` 後，117 列指紋與執行前**逐位元相同**。

> **細判成立的條件是：它可以被執行前已記錄的資料獨立驗證**
> （複查方 2026-09-05）。快照裡的「NVDA 至 2026-08-20」就是那份紀錄，
> **不需要在看到結果之後發現任何新事實。**

> **一個把兩件事綁在一起的檢查，會在其中一件發生時誤報另一件。**

**第一次的 FAIL 判定與成因保留在結果檔，不刪** ——
**一個被細判推翻的 FAIL，本身是證據**：它記錄了檢查曾經量錯了什麼。

### 13.4 E6：`CLAUDE.md` §7.3 的軟刪除不變量**第一次被實際驗證**

執行後 `高端` 仍為 `(is_active=FALSE, category='core_stock')`，停用清單仍只有它；
趨勢探索新增了「生技醫療」（25 → 26 個關鍵字）而**沒有碰到停用的那一個**。

> 那條規則寫在專案規則裡很久了，**而在今天之前，沒有任何執行證明過它成立。**
> 預期文件把它**寫死**，而不是期待它成立 —— 這是它第一次有機會被檢驗。

### 13.5 【更正】`post_time` 錯誤數 96 → 76，窗內 26 → 15

先前的量測腳本用 `datetime.fromtimestamp(ts)`（容器本地時區 = **UTC**）
還原網址時間戳，正確解讀是 **UTC+8**。
**與 `e67d3d6` 修掉的是同一個錯誤，只是我先犯在量測端。**

更正後**沒有「同年不同日」那一格**了 —— 先前的 20 列**全部是時區假象**：

```
76 列全部是整年數偏移：+1:43  +2:10  +3:4  +4:8  +5:6  +6:1  +7:4
MM/DD 本身是對的，錯的只有年份。
```

> **一個量測錯誤，讓一個乾淨的缺陷看起來比實際更雜亂 ——
> 而它與被量測的缺陷同源。**

舊 commit message 與 expectations 檔**不改**（歷史紀錄），更正記在結果檔。

### 13.6 混合狀態【必須明說】

⚠ **本次執行的產出是「舊的部分不變且已知污染、新的部分乾淨」。**

| | 內容 |
|---|------|
| 舊 | `ptt_stock` 331 列，其中 **76 列 `post_time` 錯誤**（15 列落在特徵窗內），**未修** |
| 新 | `ptt_board_pages` 1 列，`post_time` 由網址時間戳決定，**已生產驗證**（DB 值 = 網址還原值） |

**兩者在任何報表或量測中不得被當成同一批資料。**

### 13.7 條件 1 仍不成立 —— 現在有**兩個**成因

| # | 成因 |
|---|------|
| 1 | 15 列 `post_time` 錯置到特徵窗內的文章 |
| 2 | **E3 的截斷** —— 25 個關鍵字的 `NO_DATA` 不是有效觀測 |

**不得以本次的 `SUCCESS 38 / SUCCESS_EMPTY 99` 充當條件 1 的「後」。**

⚠ **E3 修好之後也不會自動補上** ——
**兩個條件都滿足（舊資料處置已定 且 重跑一次）才重測**，
**不是「修好 E3 就可以」**（複查方 2026-09-05）。

---

## 12. 建議

**建議關閉 UG-G2-SB7**，並將 §7 的五項未驗證項目
（尤其第 1、2、3 項）**在 `run_all_daily_tasks` 恢復執行時一併補測**。

> **Gate 關閉是 PO 專屬權限**（`TEAM_PLAYBOOK.md` §2）。
> 本節是 recommendation，不是宣告。
