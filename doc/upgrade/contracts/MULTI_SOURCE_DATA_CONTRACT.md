# MULTI_SOURCE_DATA_CONTRACT.md -- 多來源社群資料契約

> **Gate 0 交付物 D**
> 日期: 2026-08-22
> 狀態: READY FOR PO REVIEW

---

## 1. 設計原則

| # | 原則 | 說明 |
|---|------|------|
| 1 | **獨立轉接器 (Independent Adapter)** | 每個來源是一個獨立的 `src/extractors/<source>_scraper.py`，擁有自己的連線、解析、速率控制邏輯。任一來源故障不影響其他來源或股價 ETL。 |
| 2 | **共用輸出格式** | 所有轉接器輸出統一 DataFrame，欄位對齊 `market_articles` 表結構，交由 `db_writer.upsert_to_market_articles()` 統一寫入。 |
| 3 | **Provider 原生欄位分開保存** | 平台特有的結構信號（PTT 推/噓/箭頭、Dcard 愛心數）透過計畫新增的專用欄位保存，不壓縮到單一 `engagement_metric`。 |
| 4 | **不扁平化平台差異** | 單一 `engagement_metric INT` 不得用來混合不同平台的互動語義。PTT 存推噓差、Dcard 存愛心數、Threads 存按讚+轉發，各有獨立欄位。 |
| 5 | **每個來源是獨立 Small Batch** | 排程上各來源獨立觸發、獨立失敗、獨立重試，符合 Small Batch 交付策略。 |

---

## 2. Shared Output Schema (`market_articles`)

### 2.1 現行欄位 (已存在於 `database/schema.sql`)

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `article_id` | `SERIAL` | `PRIMARY KEY` | 自動遞增流水號 |
| `source` | `VARCHAR(20) NOT NULL` | -- | 來源標籤：`ptt_stock`, `dcard_stock`, `threads` |
| `fetch_keyword` | `VARCHAR(50)` | -- | 爬取時使用的關鍵字，對應 `tracking_keywords.keyword` |
| `post_time` | `TIMESTAMP NOT NULL` | -- | 文章發布時間，統一 UTC+8 |
| `title` | `TEXT NOT NULL` | -- | 文章標題 |
| `url` | `TEXT` | `UNIQUE` | 去重主鍵，防止跨次爬取重複寫入 |
| `author` | `VARCHAR(50)` | -- | 作者 |
| `engagement_metric` | `INT DEFAULT 0` | -- | 通用互動指標（向後相容用途） |
| `sentiment_score` | `NUMERIC(5,4)` | -- | NLP 情緒分數，算完前為 `NULL` |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | 寫入時間 |

### 2.2 計畫新增欄位 (UG-G2-SB2 留言解析)

| 欄位 | 型別 | 預設 | 來源 | 說明 |
|------|------|------|------|------|
| `push_count` | `INT` | `NULL` | PTT | 推文數（正面） |
| `boo_count` | `INT` | `NULL` | PTT | 噓文數（負面） |
| `neutral_count` | `INT` | `NULL` | PTT | 箭頭數（中性） |
| `total_comments` | `INT` | `NULL` | ALL | 留言總數，跨平台通用 |
| `provider_article_id` | `VARCHAR(100)` | `NULL` | ALL | Provider 前綴 ID，如 `ptt_Stock_M.1234567890`、`dcard_258910234` |

> **禁止 `DEFAULT 0`（`UG-G2-SB3`，PO 2026-08-27 裁示）**：四個留言計數欄若使用 `DEFAULT 0`，
> 所有留言解析上線前既有的文章都會被回填成 `0`，導致 `comment_polarization = 1 - push_ratio²`
> 在 `push_count = boo_count = 0` 時算出 `1.0`（「散戶意見最大分歧」），這是完全偽造的強訊號。
> `NULL` 才能正確表示「尚未解析」，與「已解析且確實零則留言」（`0`）語意上可區分。
> 完整理由見 `DB_MIGRATION_PLAN.md` §4.3。本節先前的表格與下方 SQL 預覽皆誤寫
> `DEFAULT 0`，已於 `UG-G2-SB3` 更正為與 §4.3 一致。

**Migration SQL (預覽)**：
```sql
ALTER TABLE market_articles
  ADD COLUMN IF NOT EXISTS push_count      INT,
  ADD COLUMN IF NOT EXISTS boo_count       INT,
  ADD COLUMN IF NOT EXISTS neutral_count   INT,
  ADD COLUMN IF NOT EXISTS total_comments  INT,
  ADD COLUMN IF NOT EXISTS provider_article_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_articles_provider_id
  ON market_articles(provider_article_id);
```

### 2.3 Upsert 語義

現行 `db_writer.upsert_to_market_articles()` 使用 `ON CONFLICT (url) DO NOTHING`：
- 同一 URL 只寫入一次，後續爬取自動略過。
- 多來源對同一篇文章不會產生 URL 衝突（不同平台 URL 自然不同）。
- `provider_article_id` 為輔助去重索引，不取代 `url` 的 UNIQUE 約束。

> **Upsert 策略演進 (UG-G2-SB2 留言更新)**
>
> 現行 `ON CONFLICT (url) DO NOTHING` 無法在重新爬取時更新推/噓/留言數。需區分兩條路徑：
> - **初次文章寫入**：`ON CONFLICT (url) DO NOTHING`（現行行為，正確）
> - **留言計數更新 (UG-G2-SB2)**：需獨立的 `UPDATE market_articles SET push_count=..., boo_count=..., neutral_count=..., total_comments=... WHERE url=...` 路徑
> - 更新路徑應為獨立操作，不與初次 upsert 混合

---

## 3. PTT Contract (Required -- Priority 1)

### 3.1 基本識別

| 項目 | 值 |
|------|-----|
| Source identifier | **見 §3.5A（三值，隨取數模式而定）** |
| Scraper module | `src/extractors/ptt_scraper.py` -- `PttScraper` class |
| Provider article ID format | `ptt_Stock_{article_filename}` (例: `ptt_Stock_M.1724567890.A.123`) |
| Dedup key | `url` (`UNIQUE` constraint on `market_articles.url`) |
| Board | `/bbs/Stock/` |

### 3.2 現行欄位映射

PttScraper 輸出 DataFrame 欄位 → `market_articles` 欄位：

| Scraper 輸出 | DB 欄位 | 轉換邏輯 |
|-------------|---------|----------|
| `source` = `"ptt_stock"` | `source` | 直接對應 |
| `fetch_keyword` | `fetch_keyword` | 直接對應 |
| `date` (MM/DD 格式) | `post_time` | 需跨年推論：若解析出的日期在當前日期之後，年份 -1 |
| `title` | `title` | 直接對應 |
| `url` | `url` | `self.base_url + title_tag["href"]`，如 `https://www.ptt.cc/bbs/Stock/M.1724567890.A.123.html` |
| `author` | `author` | 直接對應 |
| `push_count` (nrec text) | `engagement_metric` | 列表頁 nrec：數字字串 → INT；`"爆"` → 100；`"X"` 系列 → 負值；空字串 → 0 |

### 3.3 留言解析契約 (UG-G2-SB2 Inner Page Parsing)

進入文章內頁後解析 `<div class="push">` 區塊：

| Push tag class | 語義 | 寫入欄位 |
|----------------|------|----------|
| `push-tag` 含 `推` | 正面推文 | `push_count` |
| `push-tag` 含 `噓` | 負面噓文 | `boo_count` |
| `push-tag` 含 `→` | 中性回應 | `neutral_count` |

- `total_comments = push_count + boo_count + neutral_count`
- `engagement_metric` (向後相容) = `push_count - boo_count` (推噓差)

### 3.3A 留言特徵的時點有效性——RISK-023 診斷訂正，DEC-039 已處置（2026-09-14）

> **建立依據**：`PRE-G3-01` Gate A 查證，2026-09-06，登記為 `RISK-023`。
> **【2026-09-14 訂正並處置，DEC-039】** 本節原文（見下方保留的歷史敘述）
> 描述「`total_comments`／`comment_volume_ratio` 受文章層級 cutoff 保護，
> `comment_polarization`／`net_push_momentum` 不受保護」的**不對稱**——
> 後續診斷（`RISK-023_GATE_A_PROPOSAL.md` §一）核實三個留言特徵其實
> **共用同一組聚合結果**（`push_sum`／`boo_sum`／`total_sum`），受**相同**保護，
> 原文的「不對稱」敘述不精確；真正的缺口是保護粒度是**文章層級**
> （`comments_scraped_at`），不是**逐則層級**。

**現況（DEC-039 實作後）**：三個留言特徵一律改依逐則時間戳重算
（`_aggregate_direct_comment_counts()` 呼叫 `comment_timeline.counts_as_of()`），
取代文章層級 `comments_scraped_at` 過濾。詳見 `FEATURE_REGISTRY.md` §5.5、
DEC-039、`doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md`。

**以下為診斷當時的歷史敘述，保留供對照**（處置前狀態，不再是現況）：

| 特徵 | 資料來源（診斷當時） | 受 cutoff 保護？（診斷當時的認知） |
|------|---------|-----------------|
| `total_comments`／`comment_volume_ratio` | `comments_scraped_at <= trade_date + cutoff`（DEC-024） | 是（文章層級） |
| `comment_polarization` | `push_count`／`boo_count` 的取數當下彙總 | 診斷當時認為否，後核實為相同的文章層級保護 |
| `net_push_momentum` | 同上 | 同上 |

`feature_aggregator.py:780-828` 的路徑（`push_count`／`boo_count` → `push_ratio` → 兩特徵）
從 `UG-G2-SB4` 起就沒有經過任何**逐則**時點過濾（原文「沒有經過任何時點過濾」
不精確，已訂正為「沒有逐則粒度的過濾」，見上方訂正說明）。

**處置**：改由 `article_comments` 的逐則時間戳在 cutoff 下重算 `push_ratio`（**已完成，DEC-039**）。
`PRE-G3-01` 當初刻意延後（該提案決策點 2b 採 (乙)），理由是「逐則重算」與「擷取」
分開驗收，避免 Gate B 同時驗兩件事、出錯時分不清是哪一項造成的。

### 3.4 Rate Limiting

來自 `ptt_scraper.py` 現行實作：

| 策略 | 實作 |
|------|------|
| 禮貌性延遲 | `time.sleep(random.uniform(1.0, 2.5))` -- 每次成功請求後 |
| 失敗重試 | `@retry(retry=retry_if_exception(is_retriable), stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))` |
| **429／403 處理** | **一次都不重試，硬停**（DEC-032）——`is_retriable()` 見 `src/extractors/retry_policy.py` |
| 5xx／傳輸層失敗 | 有界重試，退避 2s／4s／8s，上限 3 次 |
| 頁面請求預算 | `BOARD_PAGE_BUDGET = 25`（僅看板頁面模式，見 §3.5A） |
| Cookie | `{"over18": "1"}` -- 繞過 PTT 年齡限制門檻 |
| User-Agent | 偽裝 Chrome 120 瀏覽器 |

> ⚠ **本表的前一版逐字寫著「429/5xx 處理：觸發 tenacity 重試，等待 2s, 4s, 8s」**
> ——**那正是 DEC-032 禁止的行為，而契約文件自己記載了它。**
> `UG-G2-SB7` 修 `ptt_scraper.py` 的 docstring 時**只改了程式、沒有回頭改這裡**，
> 於是同一句話又在文件層存活了一輪（2026-09-05 第 5 項施工時發現）。
>
> **一個被修好的行為，它的舊敘述會留在所有沒被一起改的地方** ——
> 而契約文件的優先序高於程式碼（`CLAUDE.md` §0.2），
> 這份殘留比程式裡的殘留更危險。

### 3.5 Failure Semantics

> **重要：** 遵循 AGENTS.md §7.1「DB Error != Empty Result」不變量。來源不可用與查無結果是不同語義，不得混用空 DataFrame 表示兩者。

| 情境 | 狀態碼 | 行為 |
|------|--------|------|
| 搜尋成功但無結果 | `SUCCESS_EMPTY` | 回傳空 DataFrame — 查詢成功，確實沒有文章，下游正常處理 |
| 單篇文章解析失敗 | `SOURCE_DEGRADED` | `except Exception as e: print(...)` → 跳過該篇，繼續下一篇；回傳已收集的部分資料 + log warning |
| 整頁抓取失敗 | `SOURCE_DEGRADED` | 3 次重試耗盡 → `break` 結束爬取迴圈，回傳已收集的部分資料 + log warning |
| PTT 完全不可用 | `SOURCE_FAILED` | 拋出可觀測的例外 (不回傳空 DataFrame)；下游 pipeline 應捕獲此例外後記錄並跳過該來源，不得將其視為「無文章」 |

### 3.5A `source` 值與取數模式的對應【權威定義】

`market_articles.source` 記錄的是**這一列是用哪一種方式取得的**，
不是「哪個站台」——後者由 `provider_article_id` 的前綴與 §3.1 的 Board 決定。

> **先例是本專案自己的**：TPEx 的 `source` 用 `tpex_daily_quotes` 而不是 `tpex`。
> **來源標記要指向「哪一份報表」，不是「哪個機構」。**
> 逐關鍵字搜尋與看板固定頁面抓取，**是兩份不同的「報表」**——
> 它們看得到的文章集合不同（搜尋涵蓋全站歷史；看板頁面只涵蓋最近 N 頁）。

| `source` 值 | 取數模式 | 端點 | 狀態 |
|-------------|---------|------|------|
| `ptt_stock` | 逐關鍵字搜尋 | `/bbs/Stock/search?q={kw}` | **Legacy**——`UG-G2-SB7` 第 5 項之前寫入的既有列 |
| `ptt_keyword_search` | 逐關鍵字搜尋 | `/bbs/Stock/search?q={kw}` | 保留可用（`scrape_ptt_stock_by_keyword`） |
| `ptt_board_pages` | **看板固定頁面 + 記憶體比對** | `/bbs/Stock/index.html` 起往回翻頁 | **現行預設**（`scrape_ptt_board_pages`） |

**程式落點**：`src/extractors/ptt_scraper.py` 的 `SOURCE_LEGACY`／
`SOURCE_KEYWORD_SEARCH`／`SOURCE_BOARD_PAGES`。
`tests/test_ptt_board_pages.py` 的 **V7** 驗證三值都出現在本文件中——
**否則它們的唯一記載處會是 Gate A 提案，而提案通過後會移入 `closed/`**（`CLAUDE.md` §16.3）。

#### 為什麼 `ptt_stock` 不回填為 `ptt_keyword_search`

既有 331 列全部來自逐關鍵字搜尋（該模式是本專案唯一存在過的 PTT 取數方式），
故 `ptt_stock` 與 `ptt_keyword_search` 在**資訊量上等價**；
而回填要改寫既有歷史資料。**改寫歷史資料換取一個零資訊增益的整齊，不划算。**
切換前的分佈量測見 `doc/upgrade/gates/evidence/G2_SB7_item5_coverage_before.json`。

#### 看板頁面模式的四態對應

| 情境 | 狀態 | `scrape_ptt_board_pages` 回傳 |
|------|------|------|
| 抓到頁面且有命中 | `SUCCESS` | `(df, "OK")` |
| 抓到頁面、一篇都沒命中 | `SUCCESS_EMPTY` | `(空 df, "NO_DATA")`——**那是有效觀測** |
| 第 2 頁以後失敗／分頁解析失敗／**預算用盡而未回溯到目標時間** | `SOURCE_DEGRADED` | `(部分 df, "SOURCE_DEGRADED")` |
| **第一頁即失敗** | `SOURCE_FAILED` | 拋 `PttSourceUnavailableError`，**不回傳空 DataFrame** |

> **「預算用盡而未回溯到目標時間」被歸為 `SOURCE_DEGRADED`，不是 `OK`。**
> 未達成目標就停下來是**部分成功**；記成 `OK` 會讓「少抓了幾天」變得看不見。
>
> ⚠ 未指定回溯目標（`since_timestamp is None`）時，預算用盡回報 `OK`：
> **沒有目標時間，就沒有「少抓了」這回事**——`SOURCE_DEGRADED` 需要一個沒被達成的目標。

#### 回溯的時間依據是**網址的 unix 時間戳**，不是索引頁的日期欄

索引頁的日期形如 `9/05`——**沒有年份、沒有時刻**，跨年時無法比較大小（§3.6 的跨年推論即為此而存在）。
文章網址 `/bbs/Stock/M.1724567890.A.123.html` 內嵌精確 unix 秒，
與 §3.1 `provider_article_id` 的取值來源同一個。

**取不到時間戳的文章回傳 `None`，不視為 0**——
0 會被讀成「1970 年，比任何目標都舊」，於是回溯**當場停止**：
**一個解析失敗會偽裝成「已經抓夠了」。**

### 3.5B 哪些 `source` 進入 `daily_ml_features`【權威定義】

> **建立依據**：PO 2026-09-05 裁決（`UG-G2-SB7` 收尾）。
> **寫在契約而不是提案裡**，理由與 §3.5A 完全相同 ——
> 提案通過 Gate B 後會移入 `closed/`，而這是一條長期生效的規則。

| `source` | 進入特徵 | 理由 |
|----------|---------|------|
| `ptt_board_pages` | **是** | 現行取數模式 |
| `ptt_keyword_search` | **是** | 同一個程式路徑仍可用 |
| `ptt_stock` | **否** | **取樣 regime 不同**（見下） |
| **其他任何未登錄的值** | **否** | **允許清單的預設方向** |

**程式落點**：`src/transform/source_capabilities.py` 的
`FEATURE_SOURCE_ALLOWLIST` 與 `source_enters_features()`；
過濾發生在 `db_writer.fetch_all_for_features` 的取數 SQL。
`tests/test_feature_source_allowlist.py` 釘住兩者。

#### 為什麼排除 `ptt_stock` —— **理由不是那些錯誤的日期**

`ptt_stock` 是 `UG-G2-SB7` 第 5 項之前、以逐關鍵字搜尋取得的 331 列，
其中 **76 列 `post_time` 錯誤**（年份差 +1~+7；成因與修正見 §3.6A）。

**但就算日期修對了，那 331 篇仍然是另一種取樣**：

| | 舊批 `ptt_stock` | 新批 `ptt_board_pages` |
|---|-----------------|----------------------|
| 取數方式 | 逐關鍵字 `/search?q=` | 看板固定頁面往回翻 |
| 涵蓋範圍 | **全站歷史，橫跨七年** | **最近幾頁** |

> **修正日期只解決「哪一天」，不解決「怎麼取到的」。**

一批日期正確、但取樣方式不同的資料混進特徵，
**仍然會讓 `REMAINING_RISKS.md` RISK-015 的覆蓋率量測失真** ——
而那正是該風險要量的東西。

#### 排除 ≠ 修正：兩件事分開

| | 是什麼 | 現況 |
|---|--------|------|
| **修正** `post_time` | **資料完整性** —— 把 2019 記成 2026 是缺陷，修它永遠是對的 | **未做**。押到「決定要用那批資料」的時候；**若那一天不會來，那次對真實庫的授權寫入就永遠不必發生** |
| **排除** | **特徵組成的決定** —— 要不要讓另一種取樣 regime 進訓練資料 | **已做**（零 DB 操作、可逆） |

**資料本身一列都沒有被改動或刪除。** 排除只發生在讀取端。

#### ⚠ 為什麼是**允許**清單而不是**排除**清單

**兩者的失效方向相反**：

| 寫法 | 日後新增一個來源而忘了登錄 |
|------|--------------------------|
| `source <> 'ptt_stock'` | **自動進入特徵** —— 未經檢視的取樣 regime 靜默混入 |
| **`source IN (...)`** | **不會進入** —— 資料誠實地少 |

判準與 `source_capabilities.provides_comment_direction()` 的預設方向**完全相同**
（該模組 docstring 逐字：「漏登錄的後果 → NULL（**誠實地少**）；
反過來 → 偽造訊號（**安靜地錯**）」）。

而允許清單**自我說明**：它直接寫出哪些 regime 在特徵集裡。

#### ⚠ 這張表與「留言方向能力」不是同一張

`ptt_stock` **同時**是 `COMMENT_DIRECTION_SOURCES` 的成員
（它**確實**提供推／噓標記）**且不在**本允許清單。

> **「這個來源能不能提供某項資料」與「要不要讓它進訓練資料」，
> 是兩個獨立的判斷。**
> **排除 `ptt_stock` 的理由不是能力不足，是取樣 regime 不同。**

#### 生效後的預期【改動前寫死】

`daily_ml_features` 的 `SUCCESS` 將由 **38 降為 0**
（唯讀模擬，見 `doc/upgrade/gates/evidence/G2_SB7_exclusion_expectations.json`）。

> ⚠⚠ **那不是回歸，是現況的真實樣貌** ——
> **情緒特徵覆蓋率實質為零**，而先前的 38 是由日期錯置的舊文撐起來的。

覆蓋率的解是 **PTT 歷史回補**（另案，Gate 3 之前）與 E3 修正後的每日累積，
**不是把舊批放回來**。

### 3.6A `post_time` 的權威來源是網址時間戳

> **建立依據**：`UG-G2-SB7` 收尾（commit `e67d3d6`），2026-09-05。

`market_articles.post_time` **優先取文章網址內嵌的 unix 時間戳**
（`/bbs/Stock/M.<unix>.A.<n>.html`），**顯式以 UTC+8 解讀**後存為 naive datetime。
取不到時間戳才回退到 §3.6 的 `MM/DD` 跨年推論。

**程式落點**：`src/transform/data_cleaner.parse_ptt_post_time()`。

#### 為什麼不能只靠 §3.6 的跨年推論

§3.6 的規則只處理 **±1 年**邊界，**而 `/search?q=` 回傳的是全站歷史，跨越七年**。

> **跨年推論的前提是「這些文章都是最近的」，而搜尋結果從來不是。
> 那個假設從沒被寫下來，因此也從沒被檢查。**

實測（2026-09-05，唯讀）：331 篇中 **76 篇**與網址時間戳不同日，
**年份差 +1 至 +7**，`MM/DD` 本身是對的。

#### ⚠ 時區必須顯式指定

`datetime.fromtimestamp(ts)` 取的是**機器的本地時區**，而 dev container 是 UTC。
一篇台北時間 03:20 的文章會變成前一天的 19:20 ——
**日期整個差一天，且差多少取決於容器怎麼設**。
而 `feature_aggregator` 的 `cutoff_time` 是 `15:30`：
**八小時的位移足以讓一篇文章從收盤後變成收盤前。**

### 3.6B 時間戳的時區基準【權威定義】與**切換時點**

> **建立依據**：`UG-G2-SB7` 收尾，2026-09-05（複查方指出的 look-ahead）。

**本專案所有持久化的時間戳，基準一律為台北時間（UTC+8），存為 naive。**

程式落點：**`src/common/clock.py`** 的 `now_taipei()`／`today_taipei()`／`to_taipei()`
—— 那是「現在」的**唯一**入口。
`tests/test_timezone_policy.py` **以 AST 掃描 `src/` 與 `main_etl_pipeline.py`**，
發現任何 naive 的 `now()`／`today()`／`utcnow()` 即 FAIL。**沒有例外清單。**

#### 為什麼需要這條

**dev container 的時區是 UTC**（`time.tzname == ('UTC','UTC')`，實測 2026-09-05），
**而本專案所有業務基準都是台北時間**（交易日、15:30 收盤、PTT 發文時刻）。

`UG-G2-SB7` 的受控執行寫出這樣一列：

```
post_time            2026-09-05 10:07:38   ← UTC+8（§3.6A）
comments_scraped_at  2026-09-05 05:53:32   ← UTC（datetime.now()）
```

**留言看起來在文章發表前 4 小時就被抓走了。**

而 `feature_aggregator` 的 DEC-024 判準是
`comments_scraped_at <= trade_date + 15:30`：

> ⚠⚠ **偏差方向是寬鬆的** —— 時間戳被記早 8 小時，
> **比應該的更容易通過那個過濾**。
> 一次台北 20:00 的抓取會被記成 12:00、通過 15:30 的 cutoff：
> **只有在 20:00 才知道的留言數，被算進 15:30 就要下的決策。**
> **那是 §7.4 的 Look-ahead，發生在一條「存在的唯一理由就是防前視」的過濾裡。**

同一次掃描還找到兩處決定**「抓哪一天／哪一個月」**的呼叫
（`previous_business_day()`、`now.strftime("%Y%m01")`）——
**台北時間每月最後一天的 16:00–24:00，UTC 還停在前一天。**

#### ⚠ 切換時點【必須記載，不得默默切換】

| 項目 | 值 |
|------|-----|
| 切換 commit | **`87256e4`**（`fix(tz): UG-G2-SB7 時區政策 —— 10 處 naive「現在」全部改走 src/common/clock.py`） |
| 切換時點 | **`2026-09-06 01:18:12 +0800`**（`87256e4` 的 author date） |
| **切換前**寫入、基準為 **UTC** 的列 | `etl_run_log` **38 列**（`started_at`／`created_at`）<br>`market_articles.comments_scraped_at` **1 列**（`article_id = 1495`） |
| 切換後寫入 | 一律台北時間 |

> **記載這件事本身是義務。** 39 列資料的時間基準在某一個 commit 之後改變，
> **而沒有任何地方記載那個時點 —— 那就是下一個「`stock_prices` 沒有 `source` 欄」。**

##### ⚠ 【2026-09-06 更正】本表原本的兩個欄位都指不準

| 欄位 | 原文 | 更正後 |
|------|------|--------|
| 切換 commit | 「**見本節加入時的 commit**」 | `87256e4` |
| 切換日期 | **2026-09-05** | **2026-09-06 01:18:12 +0800** |

**「見本節加入時的 commit」是自我指涉** —— 寫下的那一刻精確，
**離開那個 commit 就指不到任何東西**。
（`PROJECT_STATUS.md` 的 GOV-06「本次｜本 commit」是同一個形狀。）

**日期差一天有實際後果**：`2026-09-05 20:00` ~ `2026-09-06 01:18` 之間的任何寫入
是 **UTC 基準**，**但照原記載會被判成「切換後 = 台北」**。

⚠ **已用實際切換時點重數，結果不變**（2026-09-06 唯讀）：
`etl_run_log` **38 列**（`run_id` 6~43）**全部** `started_at < 切換點`，
切換點之後 **0 列**；最後一列 `started_at = 2026-09-05 05:52:52`，
**離切換點還很遠，沒有任何列落在那個模糊區間**。
`market_articles.comments_scraped_at` 非 NULL 者仍為 **1 列**。
**數字仍是 38 與 1 —— 而那也是一個要寫下來的結果。**

**既有列的處置（維持現狀／修正／加欄位標示基準）待 PO 裁決**，
本節先確保「切換點被知道」。

#### ⚠⚠ 2026-09-06 升級：那 1 列現在是**活的**，不是歷史紀錄

`PRE-G3-01` 決策點 4 對 `article_id = 1495` 補寫了 38 列 `article_comments`
（**只寫該表，不動 `market_articles` 任何欄位** —— 那是為了保住比對基準）。
**後果是同一篇文章現在有兩種時間基準：**

| 欄位 | 基準 |
|------|------|
| `market_articles.comments_scraped_at` | **UTC**（`2026-09-05 05:53:32`） |
| `article_comments.comment_time`（38 列） | **台北**（`10:09` ~ 次日 `08:43`） |

**切換之前它是「整列都是舊基準」；現在它是「同一篇文章裡兩種基準」。**

> ⚠ **任何人寫出 `counts_as_of(該篇留言, 該篇的 comments_scraped_at)`
> —— 一個完全自然的寫法 —— 會得到 `0`。**
> **而 `0` 看起來像「cutoff 之前沒有留言」，不像「時區基準不一致」。**
>
> **這一次我們知道，是因為判準先寫死了 25 去撞它。下一次不會有那個 25。**

**實測**（`evidence/PRE_G3_01_refetch_1495.json`）：

```
cutoff = DB 值（UTC）05:53:32      → total 0    （推 0／噓 0／→ 0）
cutoff = 同一時刻的台北值 13:53:32 → total 25   （推 16／噓 0／→ 9）
market_articles 上次取數記載        → total 25   （推 16／噓 0／→ 9）
```

**逐 tag 四項相符 —— 偏移量已被證明是 +8 小時。**

#### 待 PO 裁決的處置建議（**尚未核准，不得先動**）

| 對象 | 建議 | 理由 |
|------|------|------|
| `market_articles.comments_scraped_at`（**1 列**） | **修正為台北基準（+8h）** | 它現在是一個**活的比較基準**，而偏移量已被四項相符證明；UTC+8 為固定偏移，台灣無日光節約 |
| `etl_run_log`（**38 列**，`run_id <= 43`） | **維持現狀** | 它是**紀錄**，不是任何比較的基準；修正沒有消費者 |

> **這個不對稱就是判準本身：在它被拿來比較的地方修正，在它只是紀錄的地方不動。**

⚠ **修正需 PO 明確授權**（對真實庫的 `UPDATE`），且**不得取代本節的記載** ——
**切換點的紀錄要留著，修正本身另記一筆。否則就變成「悄悄改掉再假裝沒發生過」。**

#### 【2026-09-06】既有列處置 —— 已執行（1 列修正、38 列維持）

| 項 | 內容 |
|---|------|
| 授權 | PO 2026-09-06，**逐字不得外推** |
| 修正對象 | `market_articles.comments_scraped_at`，`article_id = 1495`，**恰好 1 列** |
| 修正前 → 後 | `2026-09-05 05:53:32.868583` → **`13:53:32.868583`**（+8h） |
| **未修正** | **`etl_run_log` 38 列（`run_id <= 43`）—— 維持現狀** |
| 執行證據 | `evidence/PRE_G3_01_tz_row_fix_expectations.json`（**UPDATE 之前**寫死）與 `..._result.json` |

**不對稱的理由**：

> **`etl_run_log` 是紀錄，不是任何比較的基準。修正它沒有消費者。**
> **在它被拿來比較的地方修正，在它只是紀錄的地方不動 —— 這個不對稱本身就是判準。**

**這不是竄改歷史**：+8h 之後那一列說「取數發生在 13:53:32」——
**而那就是它真正發生的台北時刻**。
**修正前的值是一個被錯誤標示的事實，修正後是同一個事實用專案的標準單位表示。**
偏移量**是被證明的，不是估的**（逐 tag 16／0／9 四項相符）。

##### 修正後 2a 的重驗結果

| 預期 | 結果 |
|------|------|
| `counts_as_of(該篇留言, 該列 comments_scraped_at)` == 25，逐 tag 16／0／9 | **PASS** |
| `daily_ml_features` 指紋 `4fc208b9…` / 137 列不變 | **PASS** |
| 其餘六表列數不變、`article_comments` 38、`total_comments` 25 | **PASS** |
| `UPDATE` 的 `rowcount` | **1** |

> ⚠ **2a 當初 FAIL 的那條判準，用同一條、同一個寫法，現在 PASS。**
> **不是改判準讓它過，是改資料讓它過 —— 這兩件事的差別就是這次操作的全部意義。**

##### ⚠ 指紋證明的比它看起來的少

| 宣稱 | 指紋能證明嗎 |
|------|-------------|
| (i) 這次 `UPDATE` 沒有動到預期以外的東西 | **能** —— `VERIFIED THIS SESSION` |
| (ii) 修正不會改變任何特徵值 | **不能** —— `daily_ml_features` 是**物化輸出**，`UPDATE market_articles` 不會傳播到它 |

> **指紋不變，不代表重跑之後結果會一樣；它只代表沒有人重跑。**

(ii) 標 **`INFERENCE`**：`comments_scraped_at` 的唯一計算消費者是
`feature_aggregator.py:768` 的 DEC-024 過濾，而 `05:53:32` 與 `13:53:32`
**同樣 `<= 2026-09-05 15:30`**。
⚠ **「剛好沒差」是運氣** —— 若那次取數在台北 16:00，修正會把它從通過翻成不通過。
**這一列落在同一側，純屬偶然。**

##### ⚠ 上方切換點的表**未被修改** —— 切換發生過這件事要留著

> **一份「修正完就把問題紀錄刪掉」的文件，下一個人會以為那個問題從來沒發生過。**

⚠ **已查證那 1 列的實際影響**：`article_id = 1495` 的真實抓取時刻是
台北 **13:53**，早於 15:30 的 cutoff；**以 UTC（05:53）或台北（13:53）計算，
它都通過那個過濾** —— **該列的結論不受影響**。
**但那是時機湊巧，不是設計正確。**

#### 刻意**不**受本條約束的東西

- **`time.time()`** —— epoch 秒沒有時區。
  `scrape_ptt_board_pages` 的回溯目標拿它跟**網址內嵌的 epoch** 比較，
  兩邊同基準，**那是對的，不要改**。
- **`scripts/verify/`** —— 產出的是證據檔、不寫入資料庫，
  且已用 `.astimezone()` 記下 offset。

### 3.6 時間解析

PTT 列表頁只提供 `MM/DD` 格式（如 `8/22`），不含年份：
- **跨年推論規則**：若解析出的月/日在當前日期之後（例：當前 1/2 但文章顯示 12/31），年份設為上一年。
- 內頁 `<meta>` 含完整 datetime，UG-G2-SB2 進入內頁時應優先使用完整時間。

---

## 4. Dcard Contract (Conditional -- Priority 2)

> **【本章節暫停適用】UG-G2-SB5（2026-08-29）可用性驗證結果：`FAIL`。**
>
> **失敗性質**：A1 回 **HTTP 403**，回應為 HTML 挑戰頁而非 API 回應
> （`<title>` = `Attention Required! | Cloudflare`、`Server: cloudflare`、`CF-RAY` 尾碼 `TPE`）
> —— **Cloudflare 邊緣攔截，請求未觸及應用層**。
>
> **因此 A2～A6 均為 `NOT EXECUTED`：本章節所描述的端點是否仍存在、
> §4.3 的欄位映射是否仍正確，本次驗證未能取得任何證據。**
> 本註記**不表示**這些內容已被證實過時。
>
> Dcard 來源狀態：**`DEFERRED WITH EVIDENCE`**。
> **章節內容原文保留**，供未來重新評估時對照實際變化。
>
> **重新評估的前提不是「再跑一次驗證腳本」**——同一條路徑會得到同樣的結果。
> 需要下列其一：**Dcard 的邊緣防護政策改變**，或**改採本契約未涵蓋的存取方式**
> （官方 API、認證存取等），後者需**另行提案與授權**。
>
> 原始證據：`doc/upgrade/gates/evidence/G2_SB5_availability_evidence.json`；
> 判定過程見 DEC-027。

### 4.1 基本識別

| 項目 | 值 |
|------|-----|
| Source identifier | `dcard_stock` |
| Planned scraper module | `src/extractors/dcard_scraper.py` |
| Provider article ID format | `dcard_{post_id}` (例: `dcard_258910234`) |
| Dedup key | `url` (`https://www.dcard.tw/f/stock/p/{post_id}`) |
| Target boards | 股票板 (`stock`)、理財板 (`money`) |

### 4.2 API Endpoint

```
GET https://www.dcard.tw/service/api/v2/forums/stock/posts
  ?popular=true
  &limit=30
  &before={cursor_post_id}
```

- 公開 REST API，不需登入即可取得文章列表。
- 分頁透過 `before` cursor 實現。
- 單篇文章內容：`GET https://www.dcard.tw/service/api/v2/posts/{post_id}`
- 留言：`GET https://www.dcard.tw/service/api/v2/posts/{post_id}/comments?limit=30`

### 4.3 欄位映射

| API Response 欄位 | DB 欄位 | 轉換邏輯 |
|-------------------|---------|----------|
| `"dcard_stock"` (硬編碼) | `source` | 直接對應 |
| 由搜尋關鍵字決定 | `fetch_keyword` | 直接對應 |
| `createdAt` (ISO 8601) | `post_time` | 直接解析，已含完整時區 |
| `title` | `title` | 直接對應 |
| 組合 URL | `url` | `https://www.dcard.tw/f/stock/p/{id}` |
| `"anonymous"` 或 `school` | `author` | Dcard 多為匿名，存 `"anonymous"` 或學校名 |
| `likeCount` | `engagement_metric` | 愛心數 |
| `commentCount` | `total_comments` | 留言總數 |

### 4.4 Rate Limiting

| 策略 | 值 |
|------|-----|
| 請求間隔 | 1.5--3.0 秒隨機延遲 |
| 重試策略 | 與 PTT 相同：tenacity 指數退避，最多 3 次 |
| 403/429 處理 | 指數退避 + 記錄日誌 |

### 4.5 Feasibility Gate

> **【本節於 `UG-G2-SB5` 被強化取代】** 可用性判定改依該 SB Gate A 提案 §3 的 A1–A5
> （本節原文為其**真子集**）。請求參數由本節的最小探測 `limit=1`
> **改為對齊 §4.2 正式端點的 `popular=true&limit=30`** ——
> 驗證因此打的是**與正式抓取路徑相同的端點形態**，而非一個只為探測而存在的變體
> （**同一次請求，總請求數不變**）。
> 本節原文**保留**為對照基準。見 DEC-026。

> **前提條件**：Dcard API 端點在實作前必須通過可用性驗證。
> 驗證方式：對 `https://www.dcard.tw/service/api/v2/forums/stock/posts?limit=1` 發送 GET 請求，確認回傳 HTTP 200 且包含有效 JSON。
> 若 API 不可用或回傳結構已變更，則 Dcard 來源降級為 Deferred。

### 4.6 Failure Semantics

| 情境 | 行為 |
|------|------|
| API 回傳非 200 | 指數退避重試 3 次後放棄，不阻塞其他來源 |
| 單篇文章解析失敗 | 跳過該篇，記錄錯誤，繼續 |
| API 結構變更 | Schema 驗證失敗 → 標記來源為 `DEGRADED`，發出告警 |

---

## 5. Threads Contract (Conditional/Deferred -- Priority 3)

### 5.1 基本識別

| 項目 | 值 |
|------|-----|
| Source identifier | `threads` |
| Planned scraper module | `src/extractors/threads_scraper.py` |
| Provider article ID format | `threads_{post_id}` |
| Dedup key | `url` |

### 5.2 API 狀態

- Meta Threads API 截至 2026-08 提供有限的公開 API（讀取自己的貼文）。
- **搜尋與公開時間線 API 尚未穩定開放**，無法可靠地按關鍵字抓取。
- 本來源 **暫緩實作 (Deferred)**，待以下任一條件滿足後啟動：
  1. Meta 官方開放公開搜尋 API 並文件化。
  2. 社群出現穩定的非官方存取路徑且法律風險可接受。

### 5.3 預留欄位映射 (Draft)

| 預期資料 | DB 欄位 | 說明 |
|----------|---------|------|
| 貼文 ID | `provider_article_id` | `threads_{post_id}` |
| 貼文文字 | `title` | Threads 無標題，取前 100 字作為 title |
| 按讚 + 轉發數 | `engagement_metric` | 合併計算 |
| 回覆數 | `total_comments` | 留言總數 |

### 5.4 Failure Semantics

與其他來源相同：獨立失敗、不阻塞、記錄日誌。

---

## 6. Cross-Platform Deduplication

### 6.1 去重策略

| 機制 | 層級 | 說明 |
|------|------|------|
| `url UNIQUE` | Database constraint | 主要去重手段。不同平台的 URL 天然不同，同平台重複爬取由此攔截。 |
| `provider_article_id` | Application-level index | 輔助查詢與除錯用。格式 `{platform}_{native_id}`，保證跨平台不碰撞。 |
| `ON CONFLICT (url) DO NOTHING` | Upsert semantics | `db_writer.upsert_to_market_articles()` 現行行為：URL 已存在則靜默跳過，確保冪等性。 |

### 6.2 跨平台同一事件處理

同一則新聞可能同時出現在 PTT、Dcard、Threads：
- **不做跨平台去重**：三則視為獨立文章，各自保留。
- **理由**：不同平台的留言生態與情緒分布有獨立分析價值，合併反而損失資訊。
- **特徵聚合層**（`feature_aggregator.py`）可透過 `source` 欄位按平台分組或加權。

---

## 7. Failure Semantics (Cross-Source)

> **不可變原則 (AGENTS.md §7.1)**：失敗不得偽裝成 Empty Result（沒有資料）。
> 來源故障與「今日確實沒有文章」必須可區分，且不得讓下游把故障當成中立情緒發布。

### 7.1 隔離原則

```
PTT 失敗      ──→ Dcard/Threads 照常 ──→ 股價 ETL 照常 ──→ 該日 PTT 情緒特徵 = NULL
Dcard 失敗    ──→ PTT/Threads 照常   ──→ 股價 ETL 照常 ──→ 該日 Dcard 情緒特徵 = NULL
全部來源失敗  ──→ 股價 ETL 照常      ──→ 該日社群特徵全部 NULL，該筆排除訓練
```

每個來源的爬取是獨立的 Python 函數呼叫，任一來源故障不影響其他來源或股價 ETL 執行。

**關鍵約束**：來源失敗時，**不得**將 `article_count` 寫成 `0`，也**不得**將 `sentiment_mean` 補成中立值 `0.5`。
`article_count = 0` 只在 `SUCCESS_EMPTY`（查詢成功但確實無文章）時成立。

### 7.2 三態結果契約

| 狀態 | 觸發條件 | 回傳 | 特徵層行為 |
|------|----------|------|------------|
| `SUCCESS_EMPTY` | 查詢成功，該關鍵字/時段確實無文章 | 空 DataFrame + status=SUCCESS_EMPTY | `article_count = 0`；`sentiment_mean = 0.5`（中立）— 這是有效資料 |
| `SOURCE_DEGRADED` | 部分頁面成功、部分失敗 | 部分 DataFrame + status=SOURCE_DEGRADED + 失敗頁清單 | 使用已取得資料，並記錄 degraded 標記供評估時排除 |
| `SOURCE_FAILED` | 來源完全不可達（連線失敗、重試耗盡、認證失效） | **拋出可觀測例外**（不得回傳空 DataFrame） | 該來源當日特徵保持 `NULL`；**不得**寫入 0 或中立值；該筆排除訓練 |

### 7.3 共用錯誤處理規範

| 錯誤類型 | 策略 | 結果狀態 | 實作參考 |
|----------|------|----------|----------|
| **Rate limit (429)** | 指數退避：2s → 4s → 8s，最多 3 次 | 重試成功 → SUCCESS；耗盡 → SOURCE_FAILED | `tenacity @retry(wait=wait_exponential(multiplier=1, min=2, max=10))` |
| **Server error (5xx)** | 同上，與 429 共用重試鏈 | 同上 | `response.raise_for_status()` |
| **Parse error（單篇）** | 跳過該篇文章，記錄錯誤，繼續批次 | SOURCE_DEGRADED | `ptt_scraper.py` L79 現行模式 |
| **Network timeout** | requests timeout → 重試 | 重試成功 → SUCCESS；耗盡 → SOURCE_FAILED | 建議所有 scraper 加上 `timeout=15` 參數 |
| **整個來源不可用** | **拋出 `SourceUnavailableError` 例外** | SOURCE_FAILED | 上層 pipeline catch 後記錄並跳過該來源，**不得**回傳空 DataFrame 讓 `if df.empty: return` 靜默吞掉 |

> **與現行程式碼的差異**：目前 `db_writer.py` L128-129 的 `if df.empty: return` 無法區分「無資料」與「來源失敗」。
> UG-G2-SB2 實作時必須讓 scraper 回傳 `(DataFrame, SourceStatus)` 或在失敗時拋出例外，由 pipeline 層明確處理。

### 7.4 可觀測性

- 每個 scraper 在開始與結束時輸出 `[Extract]` 前綴日誌。
- `db_writer` 在寫入時輸出 `[Load]` 前綴日誌與筆數。
- 未來改進方向：結構化 logging (JSON) + 失敗計數 metrics。

---

## Appendix A: Source Priority Matrix

| 來源 | 優先級 | 狀態 | 前提條件 | Small Batch |
|------|--------|------|----------|-------------|
| PTT Stock | P1 (Required) | ACTIVE | 無 -- 已有 `ptt_scraper.py` 運作中 | UG-G2-SB1 (列表頁), UG-G2-SB2 (內頁留言) |
| Dcard Stock | P2 (Conditional) | PLANNED | API 可用性驗證通過 | UG-G2-SB5 |
| Threads | P3 (Deferred) | DEFERRED | Meta 官方 API 開放 | TBD |

## Appendix B: File Reference

| 檔案 | 角色 |
|------|------|
| `src/extractors/ptt_scraper.py` | PTT 爬蟲轉接器 (現行) |
| `src/loaders/db_writer.py` | 統一資料寫入層 (`upsert_to_market_articles`) |
| `database/schema.sql` | `market_articles` 表定義 |
| `doc/upgrade/sources/MULTI_SOURCE_SENTIMENT_AND_COMMENT_FEATURE_SPEC.md` | 多來源情緒與留言特徵化規格書 |
