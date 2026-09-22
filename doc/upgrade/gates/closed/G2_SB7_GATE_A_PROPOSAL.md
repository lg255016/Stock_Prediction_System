# UG-G2-SB7 Gate A 提案：批次化 ETL 引擎

> **性質**：Gate A 提案，**非實作授權**。核准前不動 `src/`、`database/`、`main_etl_pipeline.py`，不寫入任何資料庫。
> **提交日期**：2026-09-03
> **前置**：`UG-G2-SB6` 已 CLOSED（2026-09-03）——真實庫已有 **46 期 PIT 快照**、每期 150 檔、85,641 列。
> **權威來源**：Master Plan §8 SB7 Brief、DEC-017（`APPROVED`）、DEC-031（`APPROVED`）、
> **DEC-032（`APPROVED`，明文點名本 SB）**、`MULTI_SOURCE_DATA_CONTRACT.md` §3.5／§7.2／§7.4、
> `CLAUDE.md` §7.1。

---

## 0A. 本提案的撰寫慣例【沿用 `UG-G2-SB6` §0A】

> **Gate A 提案描述的是「將要做什麼」，一律用未來式或祈使句。**
> **任何過去式的陳述都必須當場附上證據位置。**
> **若寫的時候還沒做，就不能用過去式 —— 即使你確定等一下會做。**

本提案中所有過去式陳述皆為**已執行的唯讀查證**，逐項附上檔案:行號或指令。
**判準若在實作期被修改，修正後的判準單獨 commit 一次，然後才跑**（DEC-033 §Decision 第 6 條）。

---

## 0. 四個前置問題的回答【複查方指定，提案不回答不得送審】

### 0.1 DEC-032 的三處生產違反 —— **在 SB7 內修，但範圍取決於 §0.2**

#### 現況（唯讀查證，2026-09-03）

| 位置 | 逐字 | 為何違反 |
|------|------|---------|
| `src/extractors/twse_scraper.py:14` | `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=10))` | **無 `retry=` 條件 → 對任何例外重試**。`:18` `response.raise_for_status()` 使 403／429 拋 `HTTPError`，**因此被重試 3 次** |
| `src/extractors/ptt_scraper.py:27` | `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))` | 同上；`:34` `raise_for_status()` |
| `src/extractors/yfinance_api.py:9` | `@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))` | 同上；`:26` `raise e  # 觸發 Tenacity 的重試機制` **明文寫著它在做這件事** |

**`ptt_scraper.py:31` 的 docstring 逐字**：

```
遇到 429 或 500 等錯誤會自動等待 2s, 4s, 8s 重試。
```

> **這不需要推論 —— 程式自己記載了它在做 DEC-032 禁止的事。**
> 那段 docstring 寫在 DEC-032 之前，**沒有人回頭檢查生產程式碼是否本來就違反**。
> 而 PTT 是社群網站：**對一個叫我們停的 429 做三次指數退避，正是那條紀律要防的行為。**

#### 本提案的立場：**在 SB7 內修**

| 選項 | 評估 |
|------|------|
| (a) **在 SB7 內修** | **採納** —— Brief 的 Affected Components **逐字列出這三個檔**。另立補救案等於在同一輪工作裡**碰同樣三個檔兩次**，而兩次之間那三個檔處於「已知違規但仍在跑」的狀態 |
| (b) 另立補救案，SB7 之前做 | 不採納，但**它比 (c) 好** —— 若 PO 希望把「修既有違規」與「新增批次能力」分成兩個可獨立回退的 commit，這是可行的；提案不反對，只反對把它排在 SB7 **之後** |
| (c) 登記為風險、延後 | **明確反對** —— SB7 動的正是這三個檔。**沉默等於選擇「照舊」，而那是把一個已知違規固化進批次層。** 批次層會把每天 3 次重試變成每天 150 × 3 次 |

#### ⚠ 三處**不是同一種東西**，處置也不同

**這一點複查方的清單沒有分開，而分不開會做錯。**

| 檔案 | DEC-032 的判別依據可用嗎 | 處置 |
|------|------------------------|------|
| `ptt_scraper.py` | **可用** —— 直接用 `requests`，拿得到 `response.status_code` | 加 `retry=` 條件：只對傳輸層例外與 5xx 重試；403／429 **硬停** |
| `twse_scraper.py` | **可用**（同上） | **取決於 §0.2** —— 若該路徑退役，正確處置是**刪除**而非修 |
| `yfinance_api.py` | **不可用** | 見 §0.1a |

**`yfinance` 是函式庫，不是我們控制的 HTTP client。**
DEC-032 的判別依據逐字是「**有沒有拿到 `status_code`**」——
而 `stock.history()` 把 HTTP 細節吞掉了，**我們拿不到 `status_code`**。

#### 0.1a `yfinance` 路徑的處置 —— **它不是美股專用路徑**

> **【2026-09-04 更正，本節的第一版事實基礎是錯的】**
> 第一版寫「`yfinance` 路徑目前只服務 `NVDA` 一檔…為一個**可能被移除的標的**
> 發明一套判別法，是把成本花在錯的地方」。
> **那是本節選擇處置方式的唯一理由，而它不成立。**

**台股上櫃每一次都走 yfinance。** 路由（`main_etl_pipeline.py:221`）是
`if mkt in ("TWSE", "TPEX")` → `run_twse_pipeline`，而該函式（`:44-57`）先試
`STOCK_DAY`、抓不到才落 yfinance 備援，並以
`format_provider_symbol` 轉成 `6488.TWO`（`data_cleaner.py:41` 逐字舉此例）。

程式自己記載了三次：

| 位置 | 逐字 |
|------|------|
| `main_etl_pipeline.py:40` | 「整合 TWSE 爬蟲與 yfinance **救援機制**」 |
| `data_cleaner.py:158` | 「清洗 yfinance 股價資料（美股**或台股備援**）」 |
| `yfinance_api.py:31` | `__main__` 示範就是 `fetch_yfinance_data('6488.TWO','1mo')` |

**而真實庫的資料證實了它，不只是讀程式**（`postgres`@`localhost:5432`，唯讀查詢）：

| stock_id | 天數 | 期間 | 判讀 |
|---|---|---|---|
| 2330 / 2382（上市） | 14 | `2026-08-03` ~ `08-20` | 自月初起算 → `STOCK_DAY`（`date=YYYYMM01`） |
| **6488（上櫃）** | **25** | **`2026-07-20` ~ `08-21`** | **跨月** |
| NVDA（美股） | 64 | `2026-05-20` ~ `08-20` | yfinance `period="3mo"` |

> **`6488` 的區間起於 2026-07-20 —— 而 `STOCK_DAY` 帶的參數是 `date=20260801`，
> 它結構上給不出 7 月的列。** 那 25 天只可能來自 yfinance 的 `period="1mo"`。
> **所以「上櫃落備援」不是推論，是資料裡看得到的事實。**

⚠ 「`STOCK_DAY` 端點不供應上櫃股票」本身標 `INFERENCE` ——
**本提案不為此探測端點**；但上面那三列資料**不依賴該推論**，
它們直接顯示 6488 的價格不是來自 `STOCK_DAY`。

**所以處置必須與 §0.2 的落地狀態綁在一起，不能先選：**

| §0.2 落地後 | `yfinance` 路徑對台股 | 處置 |
|---|---|---|
| 上櫃改由 `tpex_market_report` 供應（**本提案的方向**） | **不再被使用** | 該路徑只剩美股。屆時 (iii)「拿掉 `@retry`、失敗記 `FETCH_FAILED`」的代價才真的只落在 `RISK-021` 待檢視的標的上 |
| 上櫃仍走備援 | **仍是上櫃取價的正常路徑** | (iii) 會改變**台股**的取價行為。**那需要另一次裁決，不能沿用「反正只有 NVDA」** |

> **§0.2 不只影響 §0.1 的範圍 —— 它可能直接消滅 §0.1 第三列的問題本身**
> （複查方 2026-09-04）。`tpex_market_report.py` 正確供應上櫃，
> **一旦每日增量改走市場報表，上櫃標的就不再需要 yfinance 備援。**

**因此本提案的處置改為有序的兩步，而不是一個選擇**：

1. **先落地 §0.2**（上櫃改由市場報表供應）；
2. **再以「該路徑是否仍服務台股」決定 (iii) 是否適用**，並在 Gate B 報告中出示
   **落地後 `yfinance` 的實際呼叫對象**（可由 `etl_run_log` 的 `source` 與 `item_key` 查證）。

⚠ **無論哪一種**：(iii) **不是** DEC-032 的合規實作，是**在無法判別時選擇最保守的行為**。
提案不宣稱 `yfinance_api.py` 因此「符合 DEC-032」。
**這個區別必須寫在程式註解裡**，否則下一個人會以為那條路徑已經合規。

#### 0.1b `auto_adjust` —— **RISK-022 的一個前提建立在我們從未設定的第三方預設值上**

`yfinance_api.py:16` 逐字是 `df = stock.history(period=period)` ——
**從未明確傳入 `auto_adjust`**。

而 `REMAINING_RISKS.md` 的 RISK-022 面向一逐字宣稱
「yfinance 路徑 `auto_adjust=True` **會**還原，證交所原始價**不會**」。

**實測（container，yfinance 1.6.0）**：

```
Ticker.history 簽章:        (self, *args, **kwargs) -> pandas.DataFrame
PriceHistory.history 簽章:  (self, period=..., interval='1d', start=None, end=None,
                             prepost=False, actions=True, auto_adjust=True, ...)
```

> **該宣稱對 1.6.0 是對的 —— 但它對的方式很脆弱。**
> `Ticker.history` 的簽章是 `(*args, **kwargs)`，**在呼叫端讀不出任何預設值**；
> 真正的預設藏在 `PriceHistory.history` 裡。
> 而 `requirements.txt:4` 對 `yfinance` **沒有任何版本約束**（只有 lock 釘在 1.6.0）。
>
> **也就是說：`stock_prices` 的價格是否已還原權值，取決於一個我們從未設定、
> 在呼叫端讀不出來、且沒有版本約束保護的第三方預設值。**
> **那個值若在某次升級後改變，價格基準會靜默翻轉，而沒有任何檢查會發現**
> —— `stock_prices` 連 `source` 欄都沒有，更不會有還原基準欄。

**本 SB 的處置（最小）**：在 `fetch_yfinance_data` **明確傳入 `auto_adjust=`** 並註明理由，
**讓那個值成為我們的決定，而不是別人的預設**；並於 RISK-022 面向一補記此事實。

⚠ **不順手改 `requirements.txt` 的版本約束** —— 那是 DRIFT-016 的範圍，另案。

> **順帶記錄成因**（複查方 2026-09-03 自陳）：DEC-032 是從**驗證腳本**的角度裁決的，
> **當時沒有人回頭查生產端**。這與本專案已記錄十次的同型缺陷同一形狀：
> **一條規則實作在一支腳本而不在另一支**（DEC-032 §Remaining Risks 自己就寫著這句）。

---

### 0.2 Brief 的核心框架比 SB9 舊 —— **取價路徑重用市場報表，逐股路徑限縮不刪除**

#### 現況（唯讀查證）

| 元件 | 端點 | 粒度 | 位置 | DEC-032 |
|------|------|------|------|---------|
| `twse_scraper.py` | `exchangeReport/STOCK_DAY?stockNo=` | **一檔股票 × 一個月** | 生產 `src/` | **違反** |
| `twse_market_report.py`／`tpex_market_report.py` | —— | **全市場 × 一天** | 生產 `src/`，**但只有 parser，沒有 fetch** | 不適用 |
| `scripts/verify/fetch_candidate_prices.py` | `MI_INDEX` / TPEx daily | 全市場 × 一天 | **`scripts/verify/`，不是生產位置** | **符合**（雙軌計數、有界重試、預算） |

> **所以現況比「同概念兩實作」更精確地說是：**
> **兩個 parser 在生產位置、兩個 fetcher 分屬生產與驗證，
> 而唯一符合 DEC-032 的那個 fetcher 不在生產位置。**

**請求量的差距**（`UG-G2-SB9` 實測）：全市場報表**一天一個請求**即得 1,000+ 檔；
逐股路徑取 150 檔需 **150 個請求**。對政府單位服務而言**差兩個數量級**。

#### 本提案的立場

1. **每日增量取價改用市場報表路徑。**
   將 `scripts/verify/fetch_candidate_prices.py` 的取數核心**提升為生產 extractor**
   （暫定 `src/extractors/market_report_fetcher.py`），
   **連同 DEC-032 的實作一起搬**（`TRANSPORT_RETRIES`／`SERVER_ERROR_RETRIES`／雙軌計數／請求預算）。

2. **`twse_scraper.py` 的逐股路徑不刪除，但限縮職責並寫進模組 docstring。**

   | 用途 | 路徑 | 理由 |
   |------|------|------|
   | **每日增量**（全市場或 universe） | 市場報表 | 1 個請求 vs 150 個 |
   | **單檔歷史回補**（新納入標的補既往資料） | `STOCK_DAY` | **`MI_INDEX` 一次只給一天**；補一檔一年的歷史要 240 個請求，而 `STOCK_DAY` 只要 12 個 |

   > **兩個端點的形狀本來就相反**：一個是「一天全部股票」，一個是「一檔股票一個月」。
   > **刪掉逐股路徑會失去一個真實能力**，而那個能力在「新股票納入追蹤」時會立刻需要。
   > **但職責邊界若只存在於某個人的理解裡，它就會在下一次被違反** ——
   > 故要求寫進模組 docstring 並以測試釘住（§5 的 V4）。

3. **⚠ 這使 §0.1 的 `twse_scraper.py` 一項成為「修」而非「刪」** ——
   兩個問題因此耦合，**必須先答 §0.2 再定 §0.1 的範圍**。

#### ⚠ 第三個問題：**寫到哪張表** —— 這是本 SB 最容易做錯的地方

`stock_prices` 的實際欄位（`database/schema.sql:45-55`，唯讀查證）：
`stock_id`／`trade_date`／`open`／`high`／`low`／`close`／`volume`／`created_at`。
**沒有 `source`，沒有 `turnover_amount`。**

而 `main_etl_pipeline.py:218` 的迴圈由 `fetch_active_stock_targets()` 驅動，
其查詢是 `entity_mapping ⋈ tracking_keywords WHERE is_active`（`db_writer.py:329-334`）——
**目前 4 檔追蹤標的，不是 150 檔 universe。**

| 選項 | 評估 |
|------|------|
| (A) 每日市場報表 → `candidate_prices`（全市場，已有 `source` 欄） | **建議** —— 它已經是全市場表、已有來源標記、SB6 的排名直接吃它 |
| (B) 同時把 universe 的 150 檔寫進 `stock_prices` | **需 PO 裁決**（§7 決策點 2）。**它會把 `daily_ml_features` 由 117 列變成 150 檔 × N 天** |
| (C) 只寫 `stock_prices`，不動 `candidate_prices` | **反對** —— `stock_prices` 無 `source` 欄，會讓 RISK-022 面向一擴大到全市場規模 |

> **(B) 的代價必須先說**：`005_candidate_prices.sql` 的建表理由逐字寫著
> 「`daily_ml_features` 會被填入大量『有價量、無情緒』的列，`source_status` 幾乎全是
> `SUCCESS_EMPTY`，**而那個比例正是 RISK-015 要看的東西**」。
> **RISK-015 的正式檢視排在 Gate 3 啟動前，尚未進行。**
> **在量測之前先把分母灌大，等於在量測之前先改變被量測的東西。**

---

### 0.3 「單一失敗不阻塞」與 §7.1 的衝突 —— **不接受靜默略過；本 SB 交付可持久化的三態 outcome**

#### 現況比 Brief 描述的更嚴重（唯讀查證，逐項附行號）

**(一) 股價迴圈現在其實是「會阻塞」的。**
`main_etl_pipeline.py:218-224` 的 `for stock in active_stocks:` **沒有 try／except**。
所以 Brief 的「單一失敗不阻塞」是一個**真實的缺口**，不是既有行為的描述。

**(二) 但 PTT 那一路已經「不阻塞」了，而它正是錯誤的做法。**
`main_etl_pipeline.py:79-82`：

```python
except PttSourceUnavailableError as e:
    print(f"[WARNING] PTT 來源不可達，跳過關鍵字 [{keyword}]：{e}")
    return
```

**失敗只被 `print` 出來，沒有被記錄到任何資料裡。**

**(三) 而下游把那次失敗讀成「成功但沒有文章」。**
`src/transform/feature_aggregator.py:454-456` 逐字：

```python
df_features['source_status'] = np.where(
    df_features['article_count'] > 0, 'SUCCESS', 'SUCCESS_EMPTY'
)
```

同一段的註解自己寫著：「`SOURCE_DEGRADED`／`SOURCE_FAILED` 兩態依 Gate 0 契約
需 `UG-G2-SB2` 的 pipeline 例外傳播才可能產生，**本函式僅產出 `SUCCESS`／`SUCCESS_EMPTY` 兩態**」。

**(四) 而契約明文禁止這個結果。**
`MULTI_SOURCE_DATA_CONTRACT.md:321` 逐字：
`SOURCE_FAILED` → 「該來源當日特徵保持 `NULL`；**不得**寫入 0 或中立值；該筆排除訓練」。
而現況是 `sentiment_mean` 被 `fillna(0.5)`（`feature_aggregator.py:441`）——**中立值**。

**(五) 而禁令不在遠處的契約文件裡 —— 它就寫在被 catch 的那個例外類別上。**
`src/extractors/ptt_scraper.py:12-13` 逐字：

> 「此例外必須被拋出，**呼叫端不得將其誤判為「查無資料」而回傳空 DataFrame**
> （CLAUDE.md §7.1：DB Error != Empty Result）。」

> **`UG-G2-SB2` 把 extractor 端做對了** —— 拋出可觀測例外，
> 並把**呼叫端的義務寫進例外自己的 docstring**。
> **而 pipeline 在兩個檔案之外，做了它明文禁止的事。**
>
> **這比「契約被違反」更值得記，因為它說明了把規則寫對並不足夠** ——
> 規則寫在正確的地方、寫在最靠近使用點的地方，**呼叫端仍然違反了它**。

**(六) 契約那一列的最後一句，第一版少引了。**
`MULTI_SOURCE_DATA_CONTRACT.md:321` 完整逐字：

> `SOURCE_FAILED` → 「該來源當日特徵保持 `NULL`；**不得**寫入 0 或中立值；**該筆排除訓練**」

> **所以今天一次 PTT 抓取失敗，最終會在 `daily_ml_features` 裡呈現為
> `source_status = SUCCESS_EMPTY`、`sentiment_mean = 0.5`。**
> **失敗被洗成了「成功地確認沒有資料」** ——
> **而那些列不但沒有被排除訓練，還帶著 `0.5` 進了訓練集。**

⚠ **本段必須進 Gate B 報告**（複查方 2026-09-04 指定）。
>
> 這是 `push_count` 的雙語意、`agg(sum)` 把全 NaN 變 0、`本益比 0.00`、
> `cur.rowcount` 不是插入數 —— **同一個病，換到批次層。**
> **而批次層更危險：一次跑 150 項，失敗被吞掉時，報告上的數字看起來一樣正常。**

#### 本提案的立場

**「不阻塞」必須實作成「記錄後繼續」，不是「略過」。** 三項要求：

1. **每一項的 outcome 必須持久化，不是 `print`。**
   最低三態：`OK`／`NO_DATA`／`FETCH_FAILED`。
   > **判準**：一個只印到 stdout 的 outcome，在下一次執行後就不存在了；
   > 而「這批有幾項是真的沒資料、幾項是抓失敗」是**事後**才會被問的問題。

2. **每次執行必須產出總結，且該總結要能回答那個問題。**
   格式：`OK n / NO_DATA n / FETCH_FAILED n`，**三數之和等於本批項目數**。
   > 這條的 FAIL 條件是可寫的：**三數之和 ≠ 項目數即為靜默吞掉**（§5 的 V2）。

3. **`SOURCE_FAILED` 必須變成可達狀態。**
   ⚠ **這不是新增契約，是實作一個已核准但從未實作的契約狀態**
   （`MULTI_SOURCE_DATA_CONTRACT.md` §7.2／§7.4 已定義四態）。
   本 SB 只負責讓它**對本 SB 觸碰的來源**可達；
   **`feature_aggregator` 的完整四態判定若牽動 29 欄契約，屬另案**（§7 決策點 3）。

---

### 0.4 兩件已有機制 —— **不繞過，並各自加一條可證偽的承諾**

#### (一) 讀取端缺口反查（contract-check Part B #12）

`fetch_all_for_features()` 少 SELECT 新欄位，在 `SB4`／`DP5`／`SB8` 發生過三次。
現在 Part B #12 以反查法檢查「契約需要的欄位，讀取端皆有 SELECT」（本次實測 `契約需求 13 欄；讀取端缺 0`）。

**本 SB 的承諾**：若 SB7 新增任何寫入欄位而 #12 因此 FAIL，
**處置是補讀取端，不是調整 #12 的判準**。
> **這條承諾要有辦法被檢查**：Gate B 報告必須附 #12 的原始輸出，
> 且若 `契約需求` 的欄數改變，**必須說明改變的原因**。

#### (二) RISK-013 的技術護欄在這條路徑上不存在

`assert_safe_migration_target` 的呼叫端**只有** `database/apply_migrations.py:106`
（`grep` 實測，另加兩個測試檔）；`src/loaders/db_writer.py` **零命中**。

**而這是設計，不是疏漏**（RISK-013 欄位逐字）：守門的行為是「拒絕真實 DB」，
而 `DBWriter` 的正常職責就是在日常 ETL 中寫入真實 DB，裝上去等於讓正式 pipeline 永遠無法運作。

> **但 SB7 是生產 ETL、寫真實庫，blast radius 比驗證腳本大。**
> **技術護欄不存在時，剩下的只有流程紀律** ——
> 而流程紀律不會因為「這次是正式管線」就自動更可靠，**它只會更容易被說成不必要**。

**本 SB 的承諾**：
1. 任何會寫入的執行，**執行前呈報綁定確認**（目標 host／port／database、`current_database()` 輸出、前置備份檔名與位元組數）。
2. **run log 本身記錄 `current_database()`** ——
   > 這使「這次跑的是哪個資料庫」成為**事後可查**的事實，而不是回憶。
   > **RISK-017 的成因正是「沒有任何機制追蹤哪個環境收到了哪個變更」**，
   > 而那次的教訓被寫成「DoD 要指名資料庫」——**那只管到宣稱，管不到執行。**

---

## 1. Goal（本 SB 要做完的事）

依 Master Plan §8 SB7 Brief：**將逐股票／逐關鍵字爬取改為批次化**，並使單一失敗不阻塞。

依 §0.2 的框架修正，具體為：

- 每日增量取價改走**全市場報表路徑**（1 個請求／市場／日），寫入 `candidate_prices`
- 社群端改為**固定頁面一次抓取 + 記憶體比對**，取代逐關鍵字重複抓取
- **失敗容忍以「記錄後繼續」實作**，交付可持久化的三態 outcome 與可稽核的批次總結
- 修正 DEC-032 的三處生產違反（範圍見 §0.1／§0.2）

**不屬於本 SB**：Gate 2 的關閉、模型訓練、RISK-015 的正式檢視。

---

## 2. 【核心設計】三個必須先定的判準

### 2.1 批次的邊界是什麼

**一個「批次」= 一次執行中，對同一來源的一組同質項目。**
股價：一個交易日 × 一個市場（項目 = 該市場當日的所有普通股）。
社群：一次抓取 × 一個看板頁面集合（項目 = 頁面）。

> **為何要定義**：「單一失敗不阻塞」的「單一」指的是**項目**，
> 而 §0.3 第 2 點的「三數之和等於項目數」若沒有明確的項目定義，**就是一句無法檢查的話**。

### 2.2 記憶體比對比對的是什麼

Brief 的「固定頁面一次抓取 + 記憶體比對」指：抓回頁面後，
**先在記憶體中與已存在的 URL 集合比對**，只對新 URL 進內頁，取代目前逐關鍵字重複抓同一批頁面。

⚠ **比對鍵為 `url`**，與 `market_articles` 的既有唯一性一致；
**不以標題或作者比對** —— 那會把同名不同篇的文章誤判為重複。

### 2.3 失敗的三態如何區分【與 §0.3 相接】

| 狀態 | 判定 | **不得**被寫成 |
|------|------|--------------|
| `OK` | 取得資料且解析成功，列數 > 0 | —— |
| `NO_DATA` | **請求成功**（有 `status_code` 且為 2xx）、回應可解析、但內容為空 | 不得與 `FETCH_FAILED` 混為一談 |
| `FETCH_FAILED` | 未取得可解析的回應（傳輸層失敗、5xx 重試耗盡、403／429 硬停、解析失敗） | **不得**寫成 `NO_DATA`；**不得**只 `print` |

⚠ **403／429 歸入 `FETCH_FAILED` 且不重試**（DEC-032）。
⚠ **`FETCH_FAILED` 必須使該項目當日的下游特徵保持 `NULL`，不得填 0 或中立值**
（`MULTI_SOURCE_DATA_CONTRACT.md:321`）。

---

## 3. In Scope / Out of Scope

### In Scope

1. `src/extractors/market_report_fetcher.py`（新建）——
   由 `scripts/verify/fetch_candidate_prices.py` 提升，**含 DEC-032 實作**
2. `database/migrations/007_etl_run_log.sql`（新建，**待決策點 1**）——outcome 持久化
3. `main_etl_pipeline.py` —— 批次迴圈、失敗容忍、批次總結
4. `src/extractors/ptt_scraper.py` —— 固定頁面一次抓取 + 記憶體比對；**DEC-032 修正**
5. `src/extractors/yfinance_api.py` —— **DEC-032 處置（§0.1a 的兩步）**
   + **明確傳入 `auto_adjust=` 並註明理由**（§0.1b）
6. `src/extractors/twse_scraper.py` —— **DEC-032 修正 + 職責限縮**（§0.2）
7. 測試：Brief 指名的三項 + 本提案 §5 的 V1–V5

### Out of Scope

- **Gate 2 的關閉**（PO 專屬）
- **模型訓練、Panel Dataset**（Gate 3）
- **RISK-015 的情緒覆蓋率正式檢視** —— Brief 明文設在 Gate 3 啟動前
- **RISK-022 的權值還原** —— 排定於 Gate 2 關閉後
- **`feature_aggregator` 的完整四態 `source_status` 判定**（若牽動 29 欄契約 —— 決策點 3）
- **新增資料來源**（Brief 明文）

---

## 4. 資料落點

### 4.1 `etl_run_log`（新建，待決策點 1）

```sql
CREATE TABLE etl_run_log (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMP   NOT NULL,
    source        VARCHAR(40) NOT NULL,   -- 例：'twse_mi_index'、'ptt'
    batch_key     TEXT        NOT NULL,   -- 例：'2026-09-03'、關鍵字集合的識別
    item_key      TEXT        NOT NULL,   -- 項目識別（股票代號／頁面 URL／關鍵字）
    outcome       VARCHAR(16) NOT NULL,   -- OK / NO_DATA / FETCH_FAILED
    detail        TEXT,                   -- FETCH_FAILED 時必填：可觀測的失敗事實
    target_database TEXT      NOT NULL,   -- current_database()，見 §0.4 (二)
    http_attempts INTEGER,                -- DEC-032 雙軌計數的第二軌
    CONSTRAINT chk_etl_run_log_outcome
        CHECK (outcome IN ('OK','NO_DATA','FETCH_FAILED')),
    CONSTRAINT chk_etl_run_log_detail
        CHECK ((outcome = 'FETCH_FAILED' AND detail IS NOT NULL)
               OR (outcome <> 'FETCH_FAILED' AND detail IS NULL))
);
```

**`detail` 只能寫可觀測的事實**（例如 `HTTP 429`、`TLS handshake failed`、`parse error: missing column X`），
**不得寫推論**（例如 `被封鎖`）—— 同 `UG-G2-SB6` 的 `exclusion_reason` 紀律。

**`target_database` 為 `NOT NULL`**：見 §0.4 (二)。

### 4.2 `candidate_prices`（既有，migration 005）

每日增量寫入。**冪等**：`ON CONFLICT (stock_id, trade_date) DO UPDATE`。

---

## 5. 驗證設計【每項寫得出「什麼輸入會讓它 FAIL」】

| # | 檢查 | **什麼輸入會讓它 FAIL** |
|---|------|----------------------|
| **V1** | 403／429 **不重試** | 以 mock 回傳 429 → 斷言 HTTP 嘗試次數 **恰為 1**。目前的實作會是 3 → **今天就會 FAIL**，這是它的 known-FAIL |
| **V2** | 批次總結三數之和 = 項目數 | 讓其中一項拋例外而不記錄 outcome → 和小於項目數 → FAIL。**這條專門抓靜默略過** |
| **V3** | `FETCH_FAILED` 不得被讀成 `NO_DATA` | 構造一次抓取失敗，斷言 `etl_run_log.outcome = 'FETCH_FAILED'` **且**該項目當日下游特徵為 `NULL`。**若下游寫入 0 或 0.5 → FAIL** |
| **V4** | ~~逐股路徑不得用於每日增量~~ **批次路徑不得使用逐股取數器** | 對 `run_price_batch` 斷言 `TwseScraper.fetch_twse_stock_data` **零呼叫**。若有人「順手」把它接進批次路徑 → FAIL。**【2026-09-04 標題修正，複查方指出】** 原名說的比它量的多：**舊逐股迴圈今天仍每日在用**，為 `stock_prices`（4 檔追蹤標的）服務，而批次路徑寫的是 `candidate_prices`（全市場）。決策點 2 已裁決不把 150 檔寫進 `stock_prices`，**故兩條路徑並存，舊迴圈不是待淘汰的東西**。**V4 綠不得被當成「每日執行已經批次化」的證據。** |
| **V5** | 5xx／傳輸層**有界**重試 | 以 mock 持續回傳 500 → 斷言嘗試次數等於上限 + 1 且**最終為 `FETCH_FAILED`**。**若實作成無上限重試 → 測試不會結束**，該情形視為 FAIL |

**V1 與 V3 是本 SB 的 known-FAIL 主體**，且**必須實際跑出 FAIL 一次**（§9A.2）。

> **V1 的特殊之處**：它**對現在的程式碼就會 FAIL**。
> 因此它是本專案少見的「先寫測試、看它紅、再修」的情形 ——
> **而那正是 `CLAUDE.md` §13.5 對 bug fix 的要求**（先建立會重現問題的測試，再修復）。

---

## 6. 規模預期【取數前寫死，跑完只做比對】

| # | 項目 | 預期 | 不符代表什麼 |
|---|------|------|-------------|
| 1 | 每日股價請求數 | **每市場 1 個邏輯請求**（HTTP 嘗試可 > 1，雙軌計數） | 沒有真的改成批次 |
| 2 | 單日 `candidate_prices` 新增列數 | TWSE **950~1,130**、TPEx **780~930**（推導見下） | 報表被截斷，或過濾規則改變 |
| 3 | 批次總結三數之和 | **= 項目數**，46 期歷史不適用（本項僅對新執行） | 靜默略過 |
| 4 | `etl_run_log` 的 `target_database` | **每一列皆非空且等於執行時的 `current_database()`** | 綁定確認流於形式 |
| 5 | `daily_ml_features` / `stock_prices` | **維持 117 / 117**，除非決策點 2 裁決為 (B) | 未經裁決就擴大寫入範圍 |

> **【2026-09-04 更正，第一版的推導產生不出它自己的數字】**
>
> 第一版寫「單日數必然略低於 60 日聯集」，然後給了 TWSE 1,050~1,120、TPEx 880~920 ——
> **而聯集實測是 973~1,087／802~893，兩個上界都高於聯集最大值。**
> 「單日 ≤ 同期 60 日聯集」在結構上必然成立（聯集包含那一天），
> **所以那句推導產生不出那兩個數字。**
>
> **真正的推導是兩段，第一版只寫了第一段：**
>
> 1. **下界**取自聯集區間的下緣附近（TWSE 973、TPEx 802），
>    再往下留一點餘裕 → **TWSE 950、TPEx 780**。
> 2. **上界**必須加**未來成長餘裕** —— SB7 跑的是 `2026-08-21` **之後**的新資料，
>    而聯集區間量的是 `2022-08` ~ `2026-08` 的歷史。
>    四年成長 TWSE 11.7%／TPEx 11.3%（約每年 2.8%），
>    取**一年份成長 × 1.5 倍**作為餘裕（約 4%）→
>    TWSE `1,087 × 1.04 ≈ 1,130`、TPEx `893 × 1.04 ≈ 930`。
>
> **修正後的區間：TWSE 950~1,130、TPEx 780~930。**
>
> **這是預期，不是硬門檻** —— 若實測顯著偏離，先回報再判斷，**不調整判準使其通過**。
> ⚠ **餘裕的來源是外插，不是量測** —— 標籤 `ENGINEERING JUDGMENT`。
> **若 SB7 執行時實測落在區間外，先看是不是外插錯了，再看是不是取數錯了。**

---

## 7. PO 決策點

### 決策點 1【阻擋實作】：`etl_run_log` 是否建表

**問題**：outcome 持久化需要一張新表（migration 007，`schema_version` 6 → 7）。

| 選項 | 評估 |
|------|------|
| (a) 建表 | **建議** —— §0.3 的三項要求都需要它；且 `target_database` 欄同時解掉 §0.4 (二) |
| (b) 改寫成每次執行的 JSON 檔 | 不建議 —— 下游（`feature_aggregator`）無法查詢，`SOURCE_FAILED` 仍不可達 |
| (c) 不做，只改進 log 訊息 | **反對** —— 那正是 §0.3 描述的現況 |

### 決策點 2【阻擋實作】：universe 的 150 檔是否寫入 `stock_prices`

見 §0.2 的 (A)/(B)/(C)。**本提案建議先只做 (A)**，理由：

**理由一（更難被推翻的那個）：`stock_prices` 沒有 `source` 欄。**
`database/schema.sql:45-55` 實測：`stock_id`／`trade_date`／OHLC／`volume`／`created_at`，
**沒有 `source`，也沒有 `turnover_amount`**。
而那正是 RISK-022 面向一「**任一列的權值基準無法判斷**」的成因 ——
該表現在就混著證交所原始價與 yfinance（`auto_adjust` 見 §0.1b）兩種基準。

> **把 150 檔市場資料灌進一張來源已不可知的表，是讓不可知的部分變大。**
> `candidate_prices` 有 `source` 欄，**本來就是為此建的**（migration 005 的建表理由）。

**理由二：(B) 會在 RISK-015 被量測之前改變被量測的東西。**
`daily_ml_features` 現為 117 列、`SUCCESS` 37／`SUCCESS_EMPTY` 80；
加入 150 檔 universe 後，`SUCCESS_EMPTY` 比例會被稀釋，
**而那個比例正是 RISK-015 的量測對象**（migration 005 的建表理由逐字記載此顧慮）。

⚠ **但要誠實說出 (A) 的代價**：只做 (A) 時，**Gate 3 的 panel dataset 需要從
`candidate_prices` + `universe_snapshots` 組出價量**，而不是從 `stock_prices` 讀。
**那是 Gate 3 的設計，不是本 SB 的** —— 但若 PO 傾向 (B)，現在說比 Gate 3 才說便宜。

### 決策點 3：`feature_aggregator` 的四態 `source_status` 是否納入本 SB

**本提案建議納入最小範圍**：讓 `SOURCE_FAILED` 對**本 SB 觸碰的來源**可達，
不重寫整個判定邏輯。若 PO 認為牽動 29 欄契約過大，**則本 SB 只交付 `etl_run_log`
與批次總結，並將「下游讀取 outcome」明確登記為未完成**（不得只寫「已記錄」就當作解決）。

### 決策點 4：DEC-032 三處修正是否與批次能力**分開 commit**

見 §0.1 的選項 (b)。**本提案無偏好**，但要求兩者**不得混在同一個 commit**——
修既有違規與新增能力的回退代價不同。

---

## 8. 已知限制（先寫下來，不等到 Gate B）

1. **`yfinance_api.py` 的處置不是 DEC-032 的合規實作**（§0.1a）——
   是在無法取得 `status_code` 時選擇最保守行為。**必須寫進程式註解。**
2. **「`STOCK_DAY` 不供應上櫃」標 `INFERENCE`** —— 本提案不為此探測端點。
   §0.1a 的三列資料證據**不依賴該推論**，但那個推論本身未經直接驗證。
3. **`auto_adjust` 的預設值只對 yfinance 1.6.0 實測過**（§0.1b）；
   `requirements.txt` 對該套件無版本約束（DRIFT-016，另案）。
2. **`twse_scraper.py` 保留逐股路徑**，其職責邊界靠 docstring 與 V4 釘住。
   **V4 只檢查每日批次路徑，不檢查所有可能的呼叫端** —— 有人從別處呼叫它，V4 抓不到。
3. **`etl_run_log` 不記錄「這次執行為何啟動」**（排程／手動／重跑）——
   本 SB 不設計，若 Gate 3 需要追溯，屆時補欄。
4. **RISK-022 未解**：`candidate_prices` 為未還原權值的原始價；
   `best_bid_volume`／`best_ask_volume` 仍不得使用。
5. **RISK-015 未檢視**：決策點 2 的建議是「先不擴大分母」，
   **但那不等於 RISK-015 被處理了。**
6. **DEC-032 仍未機械強制**（該 ADR 的 §Remaining Risks 自陳）——
   本 SB 修正三處生產違反，**但下一支新腳本仍可能再犯**。
   > **要真正機械化需要一個能識別「這是對外請求」的判準，而那不好寫。**
   > **不順手做 —— 做不好會變成一個永遠通過的檢查**（§9A.1）。

---

## 9. Definition of Done（**每一項指名目標資料庫**，`gate-submit` 產出 7）

- [ ] §7 四個決策點經 PO 裁決**後**才開始實作。
- [ ] **V1 已先寫出並實際跑出 FAIL**（對修正前的程式碼），修正後轉綠。
- [ ] `etl_run_log` 建立於 **`postgres`@`localhost:5432`**（若決策點 1 為 (a)）；
      前置 `pg_dump` 備份已完成**並實測還原驗證**。
- [ ] 一次完整的每日批次已對 **`postgres`@`localhost:5432`** 執行，
      且 `etl_run_log` 的三態總和 **= 項目數**。
- [ ] `etl_run_log` 每一列的 `target_database` **等於 `postgres`**。
- [ ] **`daily_ml_features` 與 `stock_prices` 在 `postgres`@`localhost:5432` 維持 117 / 117**
      （除非決策點 2 裁決為 (B)，屆時改為裁決後的預期值並先寫死）。
- [ ] `candidate_prices` 在 **`postgres`@`localhost:5432`** 的新增列數符合 §6 第 2 項。
- [ ] V1–V5 全部通過，**且 V1、V3 各出示一個實際跑出的 FAIL**。
- [ ] 三處 DEC-032 違反已修正或已明確標示為「不適用判別依據」（`yfinance`）。
- [ ] **逐來源列出 `source_status` 的實際態數**（四態／兩態），並說明兩態者的原因 ——
      **「沒有 `SOURCE_FAILED`」必須能區分「不會失敗」與「沒接線」**（決策點 3 附帶要求）。
- [ ] **`yfinance` 路徑落地後的實際呼叫對象已出示**（§0.1a 第 2 步），
      可由 `etl_run_log` 的 `source`／`item_key` 查證。
- [ ] `fetch_yfinance_data` **已明確傳入 `auto_adjust=`**，且 RISK-022 面向一已補記（§0.1b）。
- [ ] 全套測試於 **dev container** 通過；contract-check `exit 0`（**含 Part B #12 原始輸出**）；
      無夾帶格式／行尾變更。
- [ ] **`gate-submit` 的八項產出齊備**，Gate B 送審文件與本提案同時存在於 `gates/` 根層。
      > **`UG-G2-SB6` 漏過這一項** —— 送審文件在實作完成、兩次 commit、兩輪複查之後才產生。
- [ ] 過程文件於 **PO 核准後的結案 commit** 移入 `gates/closed/`（§16.3 規則 3、6）。

---

## 10. Rollback

| 項目 | 回退方式 |
|------|---------|
| migration 007 | 前置 `pg_dump` 還原（**須先實測還原**，見 DoD） |
| `candidate_prices` 的每日增量 | 以 `trade_date` 刪除該批 —— **但需 PO 授權**（§11 受管制操作） |
| `src/` 與 `main_etl_pipeline.py` | revert commit |

⚠ **`etl_run_log` 本身不回退** —— 它記錄的是「曾經發生過什麼」，
**刪掉一次失敗的紀錄，等於讓那次失敗變成沒發生過。**

---

## 11. 裁決狀態

| # | 事項 | 狀態 |
|---|------|------|
| 決策點 1 | `etl_run_log` 是否建表 | **已裁決：建**（migration 007，`schema_version` 6→7） |
| 決策點 2 | universe 150 檔是否寫入 `stock_prices` | **已裁決：不寫入**（採 (A)） |
| 決策點 3 | 四態 `source_status` | **已裁決：納入，最小範圍。** DoD 須寫明**哪些來源變四態、哪些仍是兩態** |
| 決策點 4 | DEC-032 修正是否分開 commit | **已裁決：分開** |

> **決策點 4 的理由值得記**：**V1 是一個對現行程式碼會紅、修完才綠的測試。**
> **分開 commit 才看得到那個紅→綠的轉折**；混進批次功能就永遠看不出來了。

> **決策點 3 的附帶要求**：DoD 必須寫明哪些來源變四態、哪些仍是兩態 ——
> **否則下一個人分不出「這個來源沒有 `SOURCE_FAILED`」是因為它不會失敗，還是因為沒接線。**

### 仍待裁決

**只有一項：Gate A 本身的核准（PO）。**

> **§0.1~§0.4 四個前置問題已在本提案回答，不列入待裁決** ——
> 它們是**提案必須先答的問題**，不是請 PO 選擇的選項。
> 若 PO 不同意其中任一項的立場，那是對提案的否決，不是一個開放的決策點。
