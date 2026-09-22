# UG-Gate-2 Closure Review：Feature Store & Data Pipeline

- 日期：2026-09-06
- 目標資料庫：**`postgres`@`localhost:5432`**（`gate-submit` 產出 7）
- 提交者：PM／Agent
- **Gate 關閉是 PO 專屬權限**（`TEAM_PLAYBOOK.md` §2）。**本文件是 recommendation，不是宣告。**

---

## 0. 三句話

1. **五條准出條件全部滿足**，逐條的 commit／檔案／數字見 §2 ——
   **不是「已完成」三個字**（DEC-031 收緊「Universe 建立」措辭的理由就是那個）。
2. **收尾期間發現並修正了一個 Look-ahead**（時區），
   **它發生在一條「存在的唯一理由就是防前視」的過濾裡**，見 §4。
3. **有七項未驗證，全部逐項列出取得條件**，見 §3。
   **本 Gate 刻意不為它們再開一次執行** ——
   **一次為了填格子而做的執行，產出的是格子被填滿，不是那些事被知道。**

---

## 1. Gate 2 的 Small Batch 完成情形

| SB | 內容 | 狀態 |
|----|------|------|
| `UG-G2-SB1` | Feature Store 29 欄（migration 002） | CLOSED |
| `UG-G2-SB2` | PTT 內頁留言解析 + Failure Semantics（`543beb4`） | CLOSED |
| `UG-G2-SB3` | `market_articles` 擴充（migration 003） | CLOSED |
| `UG-G2-SB4` | 留言計數接線與留言特徵（`3a470ec`，migration 004） | CLOSED |
| `UG-G2-SB5` | Dcard 可用性驗證 → 判定 `FAIL`，`DEFERRED WITH EVIDENCE`（DEC-027） | CLOSED |
| `UG-G2-SB6` | Point-in-Time Universe（`9ca3429`，migration 006、DEC-017／DEC-033） | CLOSED |
| `UG-G2-SB7` | Batch ETL 與失敗容忍（migration 007、DEC-032／DEC-034） | CLOSED |
| `UG-G2-SB8` | CORE_16 四個平穩化特徵（`bd926a6`、DEC-029／DEC-030） | CLOSED |
| `UG-G2-SB9` | 候選池價格取得（`99f8566`、`e163d36`，migration 005、DEC-031） | CLOSED |
| `UG-G2-MIG` | 真實庫 migration 套用（RISK-017 的解） | CLOSED |

`schema_version = 7`（migrations 001~007 全部套用於 `postgres`@`localhost:5432`）。

---

## 2. 五條准出條件的逐條證據

> 准出條件出自 `SYSTEM_UPGRADE_MASTER_PLAN.md`（DEC-031 收緊條件 3、DEC-029 新增條件 5）。
> **每一條給 commit／檔案／數字，不給形容詞。**

### 條件 1：PTT 留言解析

| 項目 | 證據 |
|------|------|
| 實作 | `src/extractors/ptt_scraper.parse_article_comments`（`543beb4`）；接線 `3a470ec` |
| Schema | migration 003／004（`push_count`／`boo_count`／`neutral_count`／`total_comments`／`comments_scraped_at`） |
| **生產實測** | `article_id = 1495`：`total_comments = 25`、`push 16`／`boo 0`／`neutral 9` |
| 契約一致性 | **16 + 0 + 9 = 25**，與 `MULTI_SOURCE_DATA_CONTRACT.md` §3.3 的 `total_comments = push + boo + neutral` 相符 |

#### ⚠ 為什麼 `331 篇全為 NULL` 不推翻這一條

舊批 331 列的 `total_comments` 全為 NULL —— **而成因是查證出來的，不是推論**：

```sql
SELECT count(*) FILTER (WHERE comments_scraped_at IS NULL), count(*)
FROM market_articles WHERE source = 'ptt_stock';
→ (331, 331)
```

**331 列連 `comments_scraped_at` 都沒有** —— 代表 `backfill_ptt_comment_counts`
**從未碰過它們**，而不是碰了卻失敗。那條回填是 `UG-G2-SB4` 才接線的，
**331 列全部寫在那之前**，且回填只吃當次抓到的 URL。

> **「總是 NULL」有兩種成因：路徑壞了、與路徑沒跑過。**
> **它們在那個欄位上長得一樣，而 `comments_scraped_at` 把它們分開了。**

### 條件 2：Feature Store 29 欄

| 項目 | 證據 |
|------|------|
| Schema | `database/migrations/002_expand_ml_features.sql` |
| **實測** | `information_schema.columns` 對 `daily_ml_features` 計數 = **29** |
| 契約 | `FEATURE_REGISTRY.md`；`db_writer.ML_FEATURE_COLUMNS` 29 項 |

### 條件 3：Universe 建立（候選池 ≥ 500 檔、深度 ≥ 3 年、≥ 1 個 PIT 快照）

> DEC-031 收緊過措辭，原文是「那種**在 4 檔股票上也能宣稱達成**的寫法」。

| 子條件 | 門檻 | **實測** | 判定 |
|--------|------|---------|------|
| 候選池檔數 | ≥ 500 | **2,016 檔** | 超標 4.0× |
| 歷史深度 | ≥ 3 年 | **4.09 年**（2022-08-03 ~ 2026-09-04） | 超標 |
| PIT 快照 | ≥ 1 | **46 個**（2022-11-01 ~ 2026-08-03，85,641 列） | 超標 46× |

`candidate_prices` **1,823,842 列**（migration 005，SB9）；
`universe_snapshots`（migration 006，SB6）；窗口邊界由 DEC-033 裁定為**嚴格早於** `effective_date`。

### 條件 4：Batch ETL 完成

| 項目 | 證據 |
|------|------|
| 實作 | `main_etl_pipeline.run_price_batch`／`run_ptt_board_pipeline`；`src/loaders/etl_run_log.py`；migration 007 |
| **生產實測**（2026-09-05 單次受控執行） | 逐來源 outcome 總數 **= 項目數**：批次 **2/2**、逐股 **4/4**、關鍵字 **26/26** |
| 請求量 | 每市場 **1 個邏輯請求**；單日列數 TWSE **1,085**／TPEx **887**，**兩者皆落在取數前寫死的區間**（950–1,130／780–930） |
| 稽核 | `etl_run_log` **38 列**，`target_database` 全為 `postgres`、NULL **0** 列 |
| 失敗語意 | 四態 `OK`／`NO_DATA`／`FETCH_FAILED`／`REFUSED`；`FETCH_FAILED`／`REFUSED` 強制附可觀測 `detail` |
| DEC-032 生產實測 | `run_id = 11`：`http_attempts = 3` 且 `outcome = OK` —— **有界重試在真實執行中觸發並成功** |

證據檔：`evidence/G2_SB7_controlled_run_expectations.json`（**執行前** commit）
與 `evidence/G2_SB7_controlled_run_results.json`。

### 條件 5：CORE_16 的 16 個特徵全部可計算

| 項目 | 證據 |
|------|------|
| 實作 | `UG-G2-SB8`（`bd926a6`）四個平穩化特徵 + 讀取端缺口反查（contract-check B12） |
| ADR | DEC-029（新增 SB8）、**DEC-030**（NULL 策略修正 + 第三種成因 `U`） |
| DEC-030 三個決策逐項核對 | `amplitude_ratio` → `feature_aggregator.py:639` `= np.nan` 無 `fillna`；`volume_ratio_5d` → `:655-662` 拆暖機 `W` 與數學未定義 `U`；兩個 `bias_ratio` → `:653` 維持契約的 `fillna(0.0)` |
| 契約 | `FEATURE_REGISTRY.md` §5A.1（**三種** NULL 成因；標題於 2026-09-05 更正，內文自 2026-08-31 即為三種） |

---

## 3. 未驗證項目【七項，逐項列出取得條件】

| # | 項目 | 標籤 | 取得條件 |
|---|------|------|---------|
| 1 | 社群端切換後的 `source_status` 分佈 | `NOT VERIFIED` | **兩個成因都要處理完才重測**：(i) 15 列 `post_time` 錯置到特徵窗內的舊文章（處置為排除，DEC-034），(ii) E3 截斷（已修 `bccffa9`）。**且需重跑一次每日任務** |
| 2 | E3 修正後看板抓取的實際頁數 | `NOT VERIFIED` | 修正只保證截斷會被記成 `SOURCE_DEGRADED`，**不產生新量測**。需重跑一次 |
| 3 | 排除生效後 `SUCCESS` = 0 | 預期已寫死，**待實測** | 下一次 `run_feature_engineering_pipeline`。預期見 `evidence/G2_SB7_exclusion_expectations.json`（**改動前** commit） |
| 4 | RISK-015 情緒覆蓋率（含 `total_comments` 舊批為零） | `NOT VERIFIED` | **Gate 3 啟動前檢視**。解法是 PTT 歷史回補，**不是每日累積** |
| 5 | `SOURCE_DEGRADED` 在 `daily_ml_features.source_status` 上可達 | `NOT VERIFIED` | **阻塞點已由「取不到」變成「沒接線」**：`scrape_ptt_board_pages` 回報得出逐頁 outcome，但 `run_ptt_board_pipeline` 把它折成 `etl_run_log` 的 `FETCH_FAILED`。接線需先決定「一天內部分關鍵字降級」如何映射到逐股票、逐交易日的 `source_status` |
| 6 | 九個測試檔的 stub 形態稽核 | `NOT VERIFIED` | 測試基礎設施另案（與 `PROJECT_STATUS.md` §0.5 #17 同家族） |
| 7 | B13 的跨文件狀態一致性（`DECISIONS` vs `TRACEABILITY`） | `NOT VERIFIED` | 治理案，已裁示分兩步、第一步（詞彙檢查）已完成 |

### ⚠ 第 1~3 項共用一次執行 —— **本 Gate 刻意不跑**

三者都需要「再跑一次 `run_all_daily_tasks`」，**而它們都不在五條准出條件裡**。

> **一次為了填格子而做的執行，產出的是格子被填滿，不是那三件事被知道。**

它們會在例行執行恢復後自然取得 —— **而例行執行是否開放，是 Gate 2 之後的獨立決定**
（2026-09-05 的單次受控執行明文：**不得用一次成功的執行去換一個常態授權**）。

---

## 4. 收尾期間發現並修正的 Look-ahead（時區）

### 4.1 成因：**一次修了一半，而那一半是複查方要求的**

`e67d3d6` 把 `market_articles.post_time` 改為由網址時間戳決定並顯式轉 **UTC+8**
（§3.6A），**卻沒有一併處理同一列的 `comments_scraped_at`** ——
後者仍是 `datetime.now()`，而 **dev container 的時區是 UTC**。

> **複查方 2026-09-05 自陳**：那一半是他要求的，**他沒有要求檢查其他呼叫點**。
> **這一條記在這裡，是因為它說明缺陷可以由一個正確的指示產生。**

受控執行寫出的那一列：

```
post_time            2026-09-05 10:07:38   ← UTC+8
comments_scraped_at  2026-09-05 05:53:32   ← UTC
```

**留言看起來在文章發表前 4 小時就被抓走了。**

### 4.2 為什麼它是 Look-ahead 而不只是「時間不準」

`feature_aggregator.py:768` 是 **DEC-024 的時點有效性判準**：

```python
decision_point = trade_date + cutoff_time            # 15:30，台北收盤
df = df[df['comments_scraped_at'] <= decision_point]
```

> ⚠⚠ **偏差方向是寬鬆的。** 時間戳被記早 8 小時，**比應該的更容易通過那個過濾**。
> 一次台北 **20:00** 的抓取會被記成 **12:00**、通過 15:30 的 cutoff ——
> **只有在 20:00 才知道的留言數，被算進 15:30 就要下的決策。**
>
> **那是 `CLAUDE.md` §7.4 的 Look-ahead，
> 而它發生在一條「存在的唯一理由就是防前視」的過濾裡。**

### 4.3 掃描找到 **10 處**，而雙方的人工清單都不完整

| 來源 | 找到幾處 |
|------|---------|
| 複查方的人工清單 | 4 |
| PM 的 `grep` | 8（含 4 處不相關） |
| **AST 掃描** | **10** |

#### 主要例子：`market_report_fetcher.previous_business_day`（`:256`）

**這一處比 `%Y%m01` 那一處嚴重，因此列為主要例子**（複查方指定）：

| 位置 | 影響 |
|------|------|
| `main_etl_pipeline` 的 `now.strftime("%Y%m01")` | **月底才抓錯月份** —— 邊界情況 |
| **`previous_business_day()`** | **每天 00:00–08:00 抓錯交易日** —— 若排程設在早上六點，**每一次都錯** |

> **那不是邊界情況，是日常。**

#### 兩處連樣式都看不到

`src/ui/data_loader.py:149/229` 是 `pd.Timestamp.now()` ——
**不含 `datetime.now` 字樣，任何以它為樣式的搜尋都看不到它們。**

> **「列舉四處等於承認第五處不受保護」還不夠強 ——
> 連掃描用的樣式本身都可能漏掉一整類。**

### 4.4 修法：政策 + AST 掃描，**沒有豁免清單**

- **單一入口** `src/common/clock.py`：`now_taipei()`／`today_taipei()`／`to_taipei()`
- **`tests/test_timezone_policy.py` 以 AST 掃描** `src/` 與 `main_etl_pipeline.py`，
  發現任何 naive `now()`／`today()`／`utcnow()` 即 FAIL
- **用 AST 不用 grep**：`data_cleaner.py` 的 docstring 逐字寫著「預設為 `datetime.now()`」，
  **grep 會把那句說明判成違規**。靜態字串掃描在原理上分不出「呼叫它」與「提到它」——
  同 §0.5 stub 稽核分不出 `use` 與 `replace`
- **不建豁免清單**：`src/ui/data_loader.py` 那兩處在 demo 產生器裡、不碰資料庫，
  **仍一起走政策** —— **一個絕對的規則不需要維護豁免，而豁免清單會漏掉下一個新增的地方**

**known-FAIL 四案**（行為層，全部 `FAIL:` 無 `ERROR:`，還原後 6/6 OK）：

| 構造 | 實測 |
|------|------|
| `comments_scraped_at` 改回 `datetime.now()` | `Lists differ: ['main_etl_pipeline.py:...'] != []` |
| `previous_business_day` 改回 `date.today()` | `Lists differ: ['src/extractors/market_report_fetcher.py:...'] != []` |
| **掃描範圍改成不存在的路徑** | `0 not greater than 15：掃描到的檔案太少` |
| `now_taipei()` 退回機器本地時區 | `8e-06 != 28800 within 5 delta` |

> 第三案是反向釘子：**一個掃了零個檔案的掃描，與一個沒有違規的掃描，輸出完全一樣。**

### 4.5 既有資料：採 **(a) 記載切換點**，不修正、不加欄位

| 選項 | 判定 | 理由 |
|------|------|------|
| 修正既有列 | **不做** | `etl_run_log` 記的是「曾經發生過什麼」。DEC 的 Rollback 逐字：「**刪掉一次失敗的紀錄，等於讓那次失敗變成沒發生過**」——**改寫一筆稽核紀錄的時間戳，是同一件事的較輕版本** |
| 加欄位標示基準 | **不做** | 一個**切換後永遠是同一個值**的欄位，**是一個不再攜帶資訊的欄位** |
| **記載切換點** | **採用** | 零 DB 操作、可逆；與第 5 項的取數模式切換同一形狀、同一處置（`G2_SB7_item5_coverage_before.json` 為先例） |

**切換界線用 `run_id`，不用日期** —— 契約 §3.6B 記載為 **`run_id <= 43`**（實測 `max(run_id) = 43`）。

> **用日期去標示一次「時區修正」的界線是循環的 —— 那個日期本身要用哪個時區讀？
> 而那正是被修的東西。`run_id` 是單調的整數，不依賴任何時區。**

受影響的列：`etl_run_log` **38 列**、`market_articles.comments_scraped_at` **1 列**（`article_id = 1495`）。

⚠ **已查證那 1 列的實際影響**：真實抓取時刻是台北 **13:53**，早於 15:30 的 cutoff ——
**以 UTC（05:53）或台北（13:53）計算，它都通過那個過濾，該列結論不受影響。**
**但那是時機湊巧，不是設計正確。**

### 4.6 為什麼**不**為這件事開一則 RISK

它是「一個被發現、被修正、有 known-FAIL 的缺陷」。

> **RISK 是給「知道但不修」的東西用的。**
> **一個修好了還掛著 RISK 的項目，會讓 RISK 清單失去「這些是還沒解決的」這個意義。**

---

## 5. `gate-submit` 八項產出

### 產出 1：契約驗證

```
B13  PASS | DECISIONS.md 狀態欄字首為全大寫的詞彙成員（反查法）
       掃描 25 則；豁免 4 則（DEC-001~004 為前一團隊的描述性狀態）；不合規 0 則
       [待轉] 無 —— 目前沒有停在 PROPOSED 的 ADR

==================================================
Part B: 13/13 PASS
EXIT=0
```

（含既有 `[WARN 已登錄遺留] DECISIONS.md:599 DRIFT-007` 與 B12 兩項未涵蓋，**未過濾**。）

### 產出 2：環境 + 測試 + 依賴

**環境：container** `stock_prediction_system2_devcontainer-app-1`，Python **3.14.6**，
`numpy`／`pandas`／`sklearn`／`lightgbm`／`xgboost`／`psycopg2`／`jieba`／`snownlp`／
`tenacity`／`dotenv` **全部 PRESENT**。

```
Ran 447 tests in 33.098s

OK
```

### 產出 3~4：檔案清單與格式夾帶

見各 SB 的 Gate B 文件。**Gate 2 期間 pre-commit 檢查 2 共觸發 6 次：五次誤報（縮排位移）、一次正確**（`84e1598`，`yfinance_api.py` 的真實空白變更）。
**必須分得開** —— 寫成同一件事等於把那一次正確攔截也變成雜訊。

### 產出 5~6：證據標籤與 known-FAIL

見 §2（逐條給數字）、§3（逐項給標籤）、§4.4（四案 known-FAIL）。

### 產出 7：DoD 措辭指名目標資料庫

本文件所有數字均指 **`postgres`@`localhost:5432`**（RISK-017 的緩解）。

### 產出 8：過程文件移入 `closed/`

| # | 項目 | 狀態 |
|---|------|------|
| 1 | 各 SB 的 Gate A／Gate B 文件 | **已於各 SB 結案時移入** |
| 2 | **`GATE2_STARTUP_APPLICATION.md`** | **待本次結案 commit 移入 `closed/`** |
| 3 | rename 是否為 `R100` | 待執行後確認 |
| 4 | `DOC_PATHS` 是否含被搬移檔案 | **否**（已查證，`grep -c "gates/"` = 0） |
| 5 | `doc/README.md` | README 只列資料夾、不逐份列 Gate 文件（`grep "G2_SB[0-9]"` 零命中）—— **查證後判定無需變更** |

> ⚠ **第 2 項是 `CLAUDE.md` §16.3 規則 5 第一次真正被觸發。**
> 規則 3（SB 提案）已走過很多次，**規則 5（Gate 啟動申請書）從來沒有** ——
> **`GATE1_STARTUP_APPLICATION.md` 當年就是漏在這裡，那是 GOV-09 的由來。**
> **搬移是結案 commit 的一部分，不是事後補做。**

---

## 6. 剩餘風險

| 風險 | 嚴重度 | 現況 |
|------|--------|------|
| RISK-015 情緒覆蓋率 | High | **排除生效後 `SUCCESS` 預期為 0** —— 那不是回歸，是現況的真實樣貌。解法是 PTT 歷史回補（另案，Gate 3 之前） |
| RISK-022 價格調整基礎 | Medium | 面向一已補記（`auto_adjust` 顯式傳入）；其餘未動 |
| 留言計數的前視偏誤（回補情境） | **未決** | 回補抓到的舊文，留言累積到抓取當下。**`push-ipdatetime` 的處置必須在回補動手之前決定** —— 回補的昂貴部分是每篇一次內頁請求，**先補完再決定要時間戳，整批要重抓** |
| §0.5 #16 `min_train_size` 與 Fold 數衝突 | 未決 | 觸發條件：Gate 3 啟動前 |
| §0.5 #17 測試替身耦合 | 未決 | 第五次表現已量化：13 個 mock 落點、5 個檔案、破 4 個測試 |

---

## 7. 建議

**建議關閉 UG-Gate-2。**

理由：五條准出條件全部滿足且有可稽核的數字；
未驗證項目已逐項列出並附取得條件；
收尾期間發現的 Look-ahead 已修正並有 known-FAIL。

⚠ **Gate 3 啟動前必須先處理**：

1. **RISK-015 檢視**（准入條件）
2. **PTT 歷史回補**與 **`push-ipdatetime` 的處置**（後者必須在回補之前）
3. §0.5 #16 的 `min_train_size` 衝突

> **Gate 關閉是 PO 專屬權限。本節是 recommendation，不是宣告。**
