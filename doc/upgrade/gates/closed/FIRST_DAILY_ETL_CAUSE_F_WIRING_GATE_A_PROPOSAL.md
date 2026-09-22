# §0.5 #32 成因 F 接線（PTT 失敗＋NLP 未完成 → `SOURCE_FAILED`）——Gate A 提案 v2

> **v2 修訂**：依 PO 複核（2026-09-18）訂正起算點（§3.2）、新增「從未抓過的關鍵字」
> 語意裁決（§3.2a）、覆蓋算術改在 Python 實作、SQL 降級為段 B 獨立對照（§3.3 重寫）、
> 補測試第 8 條、若干小修（§2.2／§4／§6）。v1 的事實錯誤（「兩種起算點答案相同」）已
> 訂正，見 §3.2 附註。

## 0. 摘要

`FeatureAggregator.generate_daily_features()` 已支援 `failed_source_keys` 參數（命中的
(股票, 日期) 標記 `source_status=SOURCE_FAILED`、社群八欄保持 NULL），但生產呼叫點
`main_etl_pipeline.py:560` 從未傳入，預設 `None`。結果：PTT 來源失敗（例如 09-16 演練
26/26 `FETCH_FAILED`）與 NLP 未完成（文章 `sentiment_score` 仍是 NULL）兩種「沒觀測到」
的情形，特徵表目前都寫成 `SUCCESS_EMPTY`（「那天真的沒人討論」）——把「沒查到」與
「查了、真的沒有」混為同一個值，是 `CLAUDE.md` §7.1「Database Error 不得被偽裝成 Empty
Result」在特徵層的對應版本。

本提案**只做接線與失敗鍵推導**，不動 NLP 429 重試或執行中止邏輯（那是 §0.5 #31 的事，
本案完成後 #31(b) 才能安全把「不重試、繼續執行」接上）。本案不動任何真實庫資料；
`source_status` 的翻轉發生在下一次真實每日執行的全歷史重算，不是本案自己寫的。

## 1. Requirement Source

- `PROJECT_STATUS.md` §0.5 #32（PO 2026-09-17 裁決，首次每日 ETL 真實首跑中止複核追加）。
- `PROJECT_STATUS.md` §0.5 #31(b)（依賴本案完成，兩案設計耦合但不同一個 commit）。
- `MULTI_SOURCE_DATA_CONTRACT.md:321`（`SOURCE_FAILED` 契約定義：該來源當日特徵保持
  NULL，不得寫 0 或中立值，該筆排除訓練）。
- `tests/test_source_failed_nulls.py`（聚合器層既有紅測，已證明 `failed_source_keys`
  命中時的欄位處理正確；本案要補的是「誰來算這個集合、什麼時候傳進去」）。

## 2. Current State（唯讀查證，2026-09-18，容器內／程式碼閱讀／真實庫唯讀）

### 2.1 聚合器已具備能力，呼叫端沒接

- `src/transform/feature_aggregator.py:348` `generate_daily_features()` 簽章已有
  `failed_source_keys=None`；`:616-627` 依集合命中與否覆寫 `source_status`；
  `:634-` 起只對非 `SOURCE_FAILED` 的列做既有填補（`bullishness_index`／
  `agreement_index` 等 0.0 真值 vs `SOURCE_FAILED` 的 NULL 排除訓練，兩者不衝突）。
- `main_etl_pipeline.py:560` 呼叫時**未傳 `failed_source_keys`**，函式退化為 B 輪之前
  行為（docstring 明文的預設保證），PTT／NLP 失敗與「當天真的沒人討論」在特徵層無法
  區分。
- NLP 未評分的文章：`feature_aggregator.py:402` `df_arts = df_articles.dropna(
  subset=['sentiment_score'])`——未評分文章在聚合輸入階段就被丟棄，之後的
  `article_count`／`is_pos`／`is_neg` 等計算完全看不到它們存在過，連「有文章但沒算出
  情緒」這件事本身都不會留下任何痕跡（比 PTT 失敗更隱蔽——PTT 失敗至少 `etl_run_log`
  有列，NLP 未完成目前連查都查不到，只能從 `market_articles.sentiment_score IS NULL`
  反推）。

### 2.2 真實庫現況（唯讀，`postgres`@`localhost:5432`，`VERIFIED THIS SESSION`）

```
PTT batch_key 相異日期：['2026-09-05', '2026-09-17']
etl_run_log MIN(started_at)（不限 source，最早列來自 twse_mi_index/tpex_daily_quotes）：
    2026-09-04 06:33:25.378310
etl_run_log MIN(started_at) WHERE source='ptt'：2026-09-05 05:52:52.825455
etl_run_log MIN(batch_key) WHERE source='ptt'：2026-09-05
entity_mapping 相異 stock_id 數：459；相異 keyword 數：462
theme_stock_mapping／entity_mapping 合計相異 stock_id 數：459（與 entity_mapping 相同全覆蓋）
PTT run log 出現過的相異 item_key（追蹤關鍵字）數：31
經 entity_mapping 直接對到「曾出現在 PTT run log 的關鍵字」的股票數：8
經 theme_stock_mapping 對到「曾出現在 PTT run log 的關鍵字」的股票數：48
兩者聯集（至少一個關鍵字曾被抓過的股票數）：50
daily_ml_features.source_status（trade_date >= 2026-09-01）：SUCCESS 30、SUCCESS_EMPTY 1853
market_articles 未評分文章數：0（首次每日 ETL 段 C 已全部評分完畢）
```

`etl_run_log` 只在 09-05 與 09-17 兩天有 PTT 批次記錄——中間 09-07～09-16 這段完全沒有
PTT 執行紀錄（首次每日 ETL 段 C 之前，`run_all_daily_tasks()` 從未真實跑過每日排程），
不是「跑了但失敗」，是「根本沒跑」。§3.2 的定義把這兩者視為同一格。

**關鍵發現（PO 複核追加，本節已據此訂正）**：`entity_mapping` 涵蓋全部 459 檔股票的
自身關鍵字，但 PTT **實際抓過**的關鍵字只有 31 個（追蹤宇宙）。459 檔裡只有 50 檔透過
「至少一個關鍵字曾出現在 PTT run log」與 PTT 資料產生過關聯；其餘 409 檔的 `entity_
mapping`／`theme_stock_mapping` 關鍵字從未被 PTT 抓過一次。這個事實直接決定 §3.2a 的
語意裁決——若不處理，這 409 檔會被判定為「永遠未覆蓋」，一旦股價宇宙擴回 459 檔，這些
股票每天都會翻成 `SOURCE_FAILED`，等於重新定義 RISK-015 的覆蓋率語意（真實庫目前看不
出這個問題，是因為 `stock_prices` 現在只有追蹤宇宙 8 檔有列）。

### 2.3 呼叫端清單（`git grep generate_daily_features`，逐一列出接線與否）

| 呼叫點 | 用途 | 本案處置 |
|---|---|---|
| `main_etl_pipeline.py:560` | 生產每日 ETL 管線，寫回 `daily_ml_features` | **接線**——本案的核心變更 |
| `src/ui/data_loader.py:342` | UI 展示路徑（Demo/Real 模式），不寫回資料庫 | **不接**——純顯示用途，`df_comments=pd.DataFrame()` 已是刻意的既有簡化（見該行註解），`failed_source_keys` 若要顯示 `SOURCE_FAILED` 需要另外接 `entity_mapping`／`etl_run_log` 查詢，屬 UI 功能擴充而非本案的資料正確性範疇，本案不動；如需展示留待另案 |
| `scripts/verify/risk023_write_comment_features.py:327,341` | DEC-039 一次性真實庫寫入腳本（留言三欄），2026-09-14 已執行完畢 | **不接**——歷史腳本，只更新留言三欄，明文不涉及 `source_status`／情緒欄，不預期重跑 |
| `scripts/verify/ug_g3_sb2a_stage2_baseline_comparison.py:191` | `UG-G3-SB2a` 段 2 基準比對，純唯讀不寫庫 | **不接**——`UG-G3-SB2a` 已 CLOSED（`PROJECT_STATUS.md` §0.2），此腳本是已完成關卡的比對工具，非生產路徑 |
| `scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py:317,328` | `RISK-027` 段 2 重跑，已於腳本檔頭明文標註「自 DEC-039 起不可重跑，僅供歷史對照」 | **不接**——腳本自身已停用（缺少必要參數 `df_comments` 會直接執行失敗），維持現狀 |

生產路徑只有一個呼叫點需要接線，其餘四個（含 UI）皆有明確理由不動。**複核結果：清單
5 個檔案 7 行無漏，接受。**

## 3. 設計提案

### 3.1 失敗鍵由資料庫狀態推導，不用本次執行的記憶體 outcome（承重點，複核接受）

`daily_ml_features` 每次執行都全歷史重算，`source_status` 寫在同一次 `UPSERT ... DO
UPDATE` 裡。**若只用本次執行記憶體裡的 outcome 算 `failed_source_keys`，昨天標成
`SOURCE_FAILED` 的列，今天重算時只要「本次」沒有失敗，就會被洗回
`SUCCESS_EMPTY`**——因為聚合器每次都是從頭決定 `source_status`，不是疊加。

新增 `DBWriter` 方法（暫名 `fetch_failed_source_keys()`），每次呼叫都從資料庫重新推導
完整集合，供 `run_feature_engineering_pipeline()` 呼叫聚合器前取用。

### 3.2 起算點——依 PO 裁決訂正，本節定案不再開放討論

**v1 的錯誤**：v1 寫「`MIN(started_at) WHERE source='ptt'` 與不限 source 的
`MIN(started_at)` 在真實庫答案相同（皆 2026-09-04），選哪個不影響結果」——**這句話是
錯的，已由 PO 複核指出並由本次唯讀重查證實**：

| 算法 | 值 |
|---|---|
| `MIN(started_at)` 不限 source | 2026-09-04 06:33 UTC（該列 source 為 `twse_mi_index`／`tpex_daily_quotes`，不是 PTT） |
| `MIN(started_at) WHERE source='ptt'` | 2026-09-05 05:52 UTC |
| `MIN(batch_key) WHERE source='ptt'`（**PO 裁定採用**） | **2026-09-05** |

用不限 source 的 09-04 當起算點重跑 §3.3 的推導邏輯，多出 09-04 當天 **422 列**（總計
469，不是 47）——成因正是 §2.2 揭露的「409 檔股票的關鍵字從未被 PTT 抓過」：09-04 那天
`stock_prices` 尚未限縮到追蹤宇宙 8 檔（見 §0.5 #30 相關案發現的曆法/宇宙過渡狀態），
起算點選錯會讓大量從未被觀測過的股票被誤判為「這天缺口」。**三種算法答案不同，選擇本身
是有後果的決定，不是無關緊要的實作細節**——v1 判斷有誤，本節訂正致歉。

**PO 裁定起算點：`MIN(batch_key) WHERE source='ptt'`（2026-09-05），三個理由**（PO
原文，本提案採納）：只有 PTT 的紀錄能代表 PTT 的觀測起點；`batch_key` 是台北日期，
`started_at` 是 UTC，`::date` 會在台北 08:00 前跨日錯一天；覆蓋算術本來就是用
`batch_key` 算的，起算點同一個欄位才語意一致。**此項已裁定，不再開放討論。**

### 3.2a「從未被抓過的關鍵字」——PO 裁決，選 A（本案不擴大覆蓋率語意）

**問題**：`entity_mapping` 涵蓋全部 459 檔的自身關鍵字，但只有 50 檔（8 直接＋48 題材，
交集後聯集 50）曾經被 PTT 抓過至少一次。若覆蓋判斷對全部 459 檔一視同仁，409 檔「從未
被觀測過」的股票會被永久判定為「未覆蓋」——只要股價宇宙擴回 459 檔（或起算點取到更早
日期），這 409 檔每天都會翻成 `SOURCE_FAILED`。

**PO 裁決（選 A，已裁定）**：覆蓋判斷只對「至少有一個關鍵字曾出現在 PTT run log
（`source='ptt'` 的 `item_key`）」的股票做；從來沒被抓過任何關鍵字的股票本案不動，
維持現狀 `SUCCESS_EMPTY`。理由：把 409 檔的全部未來改成 NULL 等於重新定義 RISK-015 的
覆蓋率語意，牽動 Gate 4 的資料源擴充範圍，不是一個接線案該片面決定的事；那個決定留給
Gate 4 啟動申請書。`REMAINING_RISKS.md` RISK-015 加註見 §8。

**多關鍵字語意（PO 複核提出並裁定接受）**：一檔股票對到多個關鍵字時，**任一關鍵字有
覆蓋即算覆蓋**（不要求全部關鍵字都覆蓋）。理由：關鍵字會被 AI 探索持續新增，新關鍵字
在它出現之前沒有 log；若改成「全部關鍵字都要覆蓋」，每次探索新增題材就會把成分股的
歷史全部翻成未覆蓋——這個語意連帶寫入 DEC-042，測試第 8 條驗證。

### 3.3 覆蓋推導改在 Python 實作；SQL 降級為段 B 獨立對照

**v1 的架構問題（PO 複核指出，接受）**：v1 把 §3.2 覆蓋算術整段寫在 SQL 裡。但單元
測試會 mock 掉 `db_writer`，§4 前七條測的是覆蓋算術本身，若算術埋在 SQL 字串裡，這些
測試 mock 掉 `db_writer` 之後根本測不到真正的邏輯，只是在測「mock 回傳值符合預期」這種
空洞斷言。兩條路（打拋棄式 Postgres 違反 `CLAUDE.md` §13.4 測試封閉性，不採）中，
本提案採**推導寫在 Python**：

```python
def fetch_failed_source_keys(self) -> set:
    """§0.5 #32：回傳當日特徵應標記 SOURCE_FAILED 的 (stock_id, "YYYY-MM-DD") 集合。

    SQL 只負責撈「原始列」，覆蓋算術（起算點過濾、[B-2,B] 視窗、任一關鍵字覆蓋即算覆蓋、
    題材展開）與 NLP 未完成的 cutoff 歸日全部在 Python 做——理由：
    (1) 讓單元測試 mock 掉 db_writer 之後仍測得到真正的邏輯，不是空洞斷言；
    (2) NLP 路徑本來就要複用既有 map_timestamp_to_trading_day()，兩個來源用同一種
        「SQL 撈料、Python 算」風格，不要一半在 SQL 一半在 Python。

    SQL 撈的原始列：
        SELECT item_key, batch_key, outcome FROM etl_run_log WHERE source='ptt';
        SELECT keyword, stock_id FROM entity_mapping;
        SELECT theme_keyword, stock_id FROM theme_stock_mapping;
        SELECT stock_id, trade_date FROM stock_prices;
        SELECT article_id, fetch_keyword, post_time FROM market_articles
            WHERE sentiment_score IS NULL;
    """
```

Python 端邏輯（僅列演算法輪廓，實作時逐條對應 §4 測試）：

```python
# (a) PTT 覆蓋缺口
origin = min(batch_key for item_key, batch_key, outcome in ptt_rows)  # §3.2 裁定
ever_crawled_keywords = {item_key for item_key, _, _ in ptt_rows}      # §3.2a 裁定
covered_keyword_dates = defaultdict(set)  # keyword -> {covered trade dates}
for item_key, batch_key, outcome in ptt_rows:
    if outcome in ("OK", "NO_DATA"):
        b = date.fromisoformat(batch_key)
        for d in (b - timedelta(days=2), b - timedelta(days=1), b):
            covered_keyword_dates[item_key].add(d)

stock_keywords = defaultdict(set)  # stock_id -> {keyword, ...}（entity ∪ theme）
# ... 由 entity_mapping／theme_stock_mapping 填入

for stock_id, trade_date in stock_price_dates:
    if trade_date < origin:
        continue  # §3.2 起算點
    keywords = stock_keywords.get(stock_id, set())
    if not (keywords & ever_crawled_keywords):
        continue  # §3.2a：從未被抓過任何關鍵字的股票不動
    # 任一關鍵字覆蓋即算覆蓋（§3.2a 多關鍵字語意）
    covered = any(trade_date in covered_keyword_dates.get(k, set())
                  for k in keywords)
    if not covered:
        failed_keys.add((str(stock_id), trade_date.isoformat()))

# (b) NLP 未完成——見 §3.3b
```

**§3.2 原 SQL 草稿保留，角色改為段 B 演練的獨立對照實作**（見 §6 第 1 項）：Python
推導集合必須與這份 SQL 集合逐列相等（SQL 依 §3.2a 加一個 `WHERE stock_id IN (SELECT
DISTINCT stock_id FROM stock_kw WHERE keyword IN ever_crawled_keywords)` 子句限縮）。
兩個獨立實作（一個 Python 迴圈、一個 SQL 查詢）對同一批真實資料算出同一個答案，才是
一個能 FAIL 的檢查；同一份邏輯自己對自己不是。

**訂正後的 SQL**（供段 B 對照用，已對真實庫唯讀重跑）：

```sql
WITH ever_crawled AS (
  SELECT DISTINCT item_key AS keyword FROM etl_run_log WHERE source = 'ptt'
),
origin AS (
  SELECT MIN(batch_key)::date AS d FROM etl_run_log WHERE source = 'ptt'
),
ptt_ok AS (
  SELECT item_key AS keyword, batch_key::date AS b
  FROM etl_run_log
  WHERE source = 'ptt' AND outcome IN ('OK', 'NO_DATA')
),
keyword_cov AS (
  SELECT keyword, gs::date AS d
  FROM ptt_ok, generate_series(b - 2, b, interval '1 day') AS gs
),
stock_kw AS (
  SELECT stock_id, keyword FROM entity_mapping
  UNION
  SELECT stock_id, theme_keyword AS keyword FROM theme_stock_mapping
),
eligible_stocks AS (
  -- §3.2a：只對「至少一個關鍵字曾出現在 PTT run log」的股票做覆蓋判斷
  SELECT DISTINCT stock_id FROM stock_kw WHERE keyword IN (SELECT keyword FROM ever_crawled)
),
stock_cov AS (
  SELECT DISTINCT sk.stock_id, kc.d
  FROM stock_kw sk JOIN keyword_cov kc ON sk.keyword = kc.keyword
),
stock_dates AS (
  SELECT sp.stock_id, sp.trade_date AS d
  FROM stock_prices sp, origin
  WHERE sp.trade_date >= origin.d
    AND sp.stock_id IN (SELECT stock_id FROM eligible_stocks)
)
SELECT sd.stock_id, sd.d
FROM stock_dates sd
LEFT JOIN stock_cov sc ON sd.stock_id = sc.stock_id AND sd.d = sc.d
WHERE sc.d IS NULL
ORDER BY sd.stock_id, sd.d;
```

**真實庫執行結果（`VERIFIED THIS SESSION`，唯讀，`postgres`@`localhost:5432`，起算點
訂正為 `MIN(batch_key) WHERE source='ptt'`＝2026-09-05 後重跑）**：

```
總計 47 個 (stock_id, trade_date) 未覆蓋
by date: 09-07(7) 09-08(8) 09-09(8) 09-10(8) 09-11(8) 09-14(8)
distinct stocks: 8（2059/2330/2382/2454/3008/6488/8069 各 6 天；NVDA 5 天）
```

**與 v1 的 47 列數字巧合相同**——因為真實庫現在 `stock_prices` 只有追蹤宇宙 8 檔有列，
這 8 檔剛好全部落在「曾被抓過關鍵字」的 50 檔子集內，§3.2a 的過濾這次沒有排除任何一列；
起算點從 09-04 改到 09-05 也沒有影響，因為追蹤宇宙 8 檔在 09-04 那天本來就有覆蓋（09-05
批次涵蓋 `[09-03, 09-05]`，09-04 落在窗內）。**這個「巧合相同」本身也是需要在段 B 演練
時獨立驗證的東西，不能假設下次真實庫狀態改變後還會一樣**——這正是 §3.3 要求 Python／
SQL 兩個獨立實作互相對照的原因。

NVDA 只有 5 天（非 6 天）：09-07 是美國勞動節，`stock_prices` 對 NVDA 在那天沒有交易日
列，被 `stock_dates` 的日曆過濾掉——與首次每日 ETL 案 NVDA 曆法差異（§0.5 #30）是同一個
機制，不是新缺陷。

### 3.3b (b) NLP 未完成——SQL 抓資料，複用既有 Python 函式做 cutoff 歸日

**定義**：交易日 D、股票 s 的鍵成立，若存在至少一篇文章經直接映射（`entity_mapping`）
或題材映射（`theme_stock_mapping`）對到 s、依 cutoff（15:30）歸日到 D、且
`market_articles.sentiment_score IS NULL`。

**不用純 SQL 重寫歸日邏輯**：`feature_aggregator.py` 的
`map_timestamp_to_trading_day()`（roll-forward：`post_time` 未過 cutoff 且當天是交易日
→ 當天；否則往後滾到下一個交易日）依賴「該股自己的交易日曆」（`trading_days_by_stock`，
RISK-027 方案 B 修復後的既有邏輯），在 SQL 裡重寫等於維護第二套與 Python 版本可能不同步
的歸日規則，違反 `CLAUDE.md` §7.1「不得同時維護兩套互相不一致的定義」。改法：
`fetch_failed_source_keys()` 只用 SQL 撈**原始資料**（`market_articles` 中
`sentiment_score IS NULL` 的文章、其 `fetch_keyword`、經 `entity_mapping`／
`theme_stock_mapping` 展開的 `stock_id`、以及每檔股票的 `stock_prices.trade_date`
集合），歸日計算直接呼叫**既有、已測試**的 `map_timestamp_to_trading_day()`，不重寫。

⚠ 本來源不套用 §3.2a 的「曾被抓過關鍵字」過濾——NLP 未完成的判斷依據是「文章確實存在
但沒評分」，文章本身能不能對到某股票，是 `entity_mapping`／`theme_stock_mapping` 的
映射關係決定的，與「這個關鍵字有沒有被 PTT 抓過」是兩件獨立的事（一篇文章可能經由
AI 探索新增的題材映射對到一檔股票，即使 PTT 從未主動抓過那個關鍵字）。

**真實庫現況**：未評分文章數 0（§2.2），此來源目前貢獻 0 個失敗鍵——這是正確答案，不是
設計沒東西可測。紅測（§4 第 5 條）會用合成資料覆蓋這條路徑；下次真實 PTT/NLP 執行後若
再度中止，這條路徑會自然開始貢獻真實鍵。這個來源天然自我修復：NLP 補完評分後，下次
全歷史重算，`sentiment_score` 不再是 NULL，鍵自然消失，`source_status` 自然回到
`SUCCESS`／`SUCCESS_EMPTY`——不需要另外寫回補邏輯。

**§0.5 #32 原裁決**：PTT 失敗與 NLP 未完成兩種成因都記 `SOURCE_FAILED`，NLP **部分**
評分也算未完成，不用 `SOURCE_DEGRADED`（聚合器現有註解已說明該態「下游不可達」，本案
不新增這個路徑，維持現狀，只是把這句話寫進本提案讓決定有據可查）。

### 3.4 接線點

`run_feature_engineering_pipeline()` 呼叫時機：**NLP 階段（`run_nlp_sentiment_pipeline`）
之後、`generate_daily_features()` 之前**——否則本次剛評完分的文章仍會被算成未完成
（M3 教訓，`TEAM_PLAYBOOK.md` A15 同一類問題：時機不是形式，需要專門測試釘住，見 §4
第 7 條）。`main_etl_pipeline.py:560` 呼叫處新增：

```python
failed_source_keys = self.db_writer.fetch_failed_source_keys()
df_features = self.feature_aggregator.generate_daily_features(
    df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
    df_comments=df_comments, failed_source_keys=failed_source_keys,
)
```

`n_lag` 與尾端重算（§0.5 #30）不受影響——`failed_source_keys` 只影響
`source_status`／社群八欄，不影響 `stock_prices`／`target_triple_barrier`。驗收條件
需確認：`source_status` 翻轉的列不會被誤算進「標籤變動列必須落在 tail_window 內」那條
驗收，寫入本案 DoD。

## 4. Tests（先紅後綠，紅 FAIL 數＝新增測試數，逐條核對，`TEAM_PLAYBOOK.md` A13）

Fixture 原則：每條測試混合「命中」與「未命中」列，不用整片同一態的資料。

1. **演練形狀**：`etl_run_log` 全部關鍵字 `FETCH_FAILED`、單一 `batch_key=B`，無其他
   批次覆蓋 → 所有映射到的股票在 D=B 標 `SOURCE_FAILED`、社群八欄 NULL；完全沒有映射
   關鍵字的股票維持 `SUCCESS_EMPTY`。
   **known-FAIL**：不接線（`failed_source_keys` 傳 `None`）→ 全部列仍是
   `SUCCESS_EMPTY`，斷言 FAIL。
2. **跨日存續 + 覆蓋視窗邊界**：D 的失敗在 D+1、D+2 的重算仍是 `SOURCE_FAILED`
   （沒有批次覆蓋到 D）；`batch_key=D+2` 的 OK 批次涵蓋 `[D, D+2]`，D **被覆蓋**，回到
   `SUCCESS`／`SUCCESS_EMPTY`。兩個 known-FAIL **分開列**，各自對應一個獨立突變：
   - **known-FAIL (i)**：突變成只用本次執行的記憶體 outcome（不查歷史 `etl_run_log`）
     → 「跨日存續」子句斷言 FAIL（D+1、D+2 沒有本次 outcome 可用，會誤判為未失敗）。
   - **known-FAIL (ii)**：突變覆蓋視窗寫成 `[B, B]` 或 `[B-3, B]` → 「覆蓋視窗邊界」
     子句斷言 FAIL（`batch_key=D+2` 這個邊界點覆蓋判斷錯誤）。
3. **起算點之前不動**：`etl_run_log` 最早 PTT `batch_key`（依 §3.2 裁定為
   `MIN(batch_key) WHERE source='ptt'`，**不是** `started_at`）之前的交易日，即使沒有
   任何批次覆蓋，也不得出現在 `failed_source_keys` 裡（維持 `SUCCESS_EMPTY`）。
   **known-FAIL**：拿掉起算點過濾（改成無條件套用缺口定義到全部歷史）→ 這條斷言
   FAIL（起算點之前的舊資料被誤標成 `SOURCE_FAILED`）。
4. **沒跑等於未覆蓋**：某交易日完全沒有任何 `source='ptt'` 的 `etl_run_log` 列（不是
   失敗，是沒跑）→ 該日映射到的股票仍標 `SOURCE_FAILED`。
   **known-FAIL**：只在「有 `FETCH_FAILED` 列」的情形觸發，「完全沒有列」的情形被
   忽略 → 這條斷言 FAIL（測資中日期本身無任何 log 列）。
5. **NLP 未完成**：一篇未評分文章對到股票 s、依 cutoff 歸日到 D → (s, D) 標
   `SOURCE_FAILED`；同一篇文章補上分數後重算 → 回到 `SUCCESS`／`SUCCESS_EMPTY`。
   **known-FAIL**：`fetch_failed_source_keys()` 只做 (a) 不做 (b) → 這條斷言 FAIL。
6. **題材路徑**：某關鍵字未覆蓋，且該關鍵字只經 `theme_stock_mapping`（非
   `entity_mapping`）對到某股票 → 該股票仍命中。
   **known-FAIL**：合併時漏掉 `theme_stock_mapping`、只查 `entity_mapping` → 這條
   斷言 FAIL。
7. **呼叫時機**：`fetch_failed_source_keys()` 排在 NLP 階段之後、`generate_daily_
   features()` 之前——比照 §0.5 #30 的 `test_feature_lag_measured_after_per_stock_
   stage`，用 `MagicMock.attach_mock` 把 `run_nlp_sentiment_pipeline`、
   `fetch_failed_source_keys`、`generate_daily_features`（或聚合器某個可觀察呼叫）
   掛在同一個 parent mock，斷言 `mock_calls` 順序。
   **known-FAIL**：把呼叫搬到 NLP 階段之前重跑本測試，確認 FAIL 後還原（`git diff
   --stat` 確認零殘留，比照 §0.5 #30 M3 的做法）。**PO 複核：比照方式可以，直接採用。**
8. **【新增，PO 複核追加】從未被抓過的關鍵字 ＋ 多關鍵字任一覆蓋即算覆蓋**：
   - 8a：股票 s 只映射一個「從未出現在 PTT run log」的關鍵字 → 即使該日完全沒有任何
     覆蓋，s 仍維持 `SUCCESS_EMPTY`，**不**標 `SOURCE_FAILED`（§3.2a 選 A 裁決）。
   - 8b：股票 s 映射兩個關鍵字 k1（有覆蓋）與 k2（未覆蓋）→ s 判定為覆蓋（任一即可）。
   **known-FAIL (8a)**：拿掉「曾被抓過關鍵字」的過濾（對全部股票一視同仁套用缺口定義）
   → 這條斷言 FAIL（從未被觀測過的股票被誤標 `SOURCE_FAILED`）。
   **known-FAIL (8b)**：改成「全部關鍵字都要覆蓋才算覆蓋」→ 這條斷言 FAIL。

**送審前自我突變清單**（記憶體內執行，不碰真實庫，`CLAUDE.md` §9A.2）：至少驗證下列
突變各自被哪一條測試抓到，若有突變存活，先補測試再送：
(i) 只用本次執行 outcome、不查歷史 `etl_run_log`——第 2 條 known-FAIL (i)；
(ii) 覆蓋視窗寫成 `[B, B]` 或 `[B-3, B]`——第 2 條 known-FAIL (ii)；
(iii) 漏掉 `theme_stock_mapping` 只查 `entity_mapping`——第 6 條；
(iv) 忽略起算點、對全部歷史套用缺口定義——第 3 條；
(v) `fetch_failed_source_keys()` 呼叫時機搬到 NLP 之前——第 7 條；
(vi) 拿掉「曾被抓過關鍵字」過濾——第 8a 條；
(vii) 改成全部關鍵字都要覆蓋——第 8b 條。

## 5. Affected Components

- `src/loaders/db_writer.py`（新增 `fetch_failed_source_keys()`，覆蓋算術與 NLP 歸日
  邏輯皆在 Python 實作，見 §3.3）
- `main_etl_pipeline.py`（`run_feature_engineering_pipeline()` 接線，呼叫時機在 NLP
  之後、聚合器呼叫之前）
- `tests/test_first_daily_etl_cause_f_wiring.py`（新檔，本案 8 條紅測）
- 既有 `tests/test_source_failed_nulls.py`／`tests/test_first_daily_etl_gap_autofill.py`
  等呼叫 `run_all_daily_tasks()`／`run_feature_engineering_pipeline()` 的測試檔，若
  mock `db_writer` 需要補 `fetch_failed_source_keys` 的 mock 回傳值（比照 §0.5 #30
  的處置方式，只補 mock 不改既有斷言，紅測階段逐檔確認）

## 6. 段 B（拋棄式庫演練）

1. **只跑特徵階段**（不抓價、不抓 PTT、不探索、不 NLP）：還原自
   `stock_prediction_system2_POST_first_daily_etl_20260917_2009.dump`；before/after
   逐列比對。**兩個獨立實作互相對照**：Python `fetch_failed_source_keys()` 的結果與
   §3.3 訂正後 SQL 的結果必須逐列相等（見 §3.3 說明，這是本案唯一的「能 FAIL 的
   對照」，缺一不可）；再與 before/after 的實際翻轉列比對，須**等於**這個集合（演練
   時點重算一次，非沿用本提案 §3.3 的 47 列——時間會往前推移，數字會不同）；翻轉列
   只准動 `source_status` 與社群八欄；價格衍生 10 欄與其餘列零差異。**【PO 複核追加】**
   翻轉列的 `article_count` 必須是 **NULL**，不是 0——`tests/test_source_failed_nulls.py`
   已在聚合器單元層級釘住這個行為，演練層再對真實資料看一次，確認接線沒有繞過這個
   既有保護。
2. **強制 PTT 失敗的整日執行**：monkeypatch `run_ptt_board_pipeline` 拋
   `PttSourceUnavailableError`，`TrendDiscover` 一併 stub（不打 Gemini）；跑
   `run_all_daily_tasks()` → 當日 `etl_run_log` 全 `FETCH_FAILED`、當日所有映射股票
   （限 §3.2a 定義的「曾被抓過關鍵字」子集）列標 `SOURCE_FAILED`。
3. 拋棄式容器清理只 `docker rm`（`TEAM_PLAYBOOK.md` A14）。

## 7. 段 C（真實庫，下一次真實每日執行）

本案程式碼落地不直接動真實庫；翻轉發生在下一次真實每日執行的全歷史重算。執行程序
照現行 RISK-013 五步、binding confirmation。驗收條件新增第 5 條：「`source_status`
的每一列變動必須落在 §3.3(a)∪§3.3b(b) 的推導集合內，集合外一列即 FAIL」，預期翻轉
列數於執行前用 Python 推導與 SQL 對照各重算一次寫入 expectations（不沿用本提案的 47，
那是今天的時間點）。

## 8. 文件

- `PROJECT_STATUS.md` §0.5 #32：本提案核准後標「進行中」，段 C 驗收通過後 CLOSED。
- 新 ADR **DEC-042**（`VERIFIED THIS SESSION`：`DECISIONS.md` 目前最大編號為 DEC-041）：
  失敗鍵推導規則——(1) 覆蓋視窗 `[B-2, B]`；(2) 未跑＝未覆蓋；(3) 起算點
  `MIN(batch_key) WHERE source='ptt'`（PO 裁定，理由見 §3.2）；(4)「從未被抓過關鍵字」
  的股票本案不動、維持 `SUCCESS_EMPTY`（PO 裁定選 A，理由見 §3.2a，交叉引用
  RISK-015）；(5) 一檔股票多關鍵字任一覆蓋即算覆蓋（PO 裁定，理由：關鍵字持續由 AI
  探索新增，避免每次新增題材把成分股歷史全翻成未覆蓋）；(6) NLP 任一未評分即失敗；
  (7) 覆蓋算術與 NLP 歸日邏輯皆在 Python 實作，SQL 只作段 B 獨立對照，不是推導本身
  （理由：單元測試封閉性，`CLAUDE.md` §13.4／§13.5）；(8) NLP 未完成不重寫歸日邏輯而
  複用 `map_timestamp_to_trading_day()`。這是決策不是實作細節——日後有人改
  `BOARD_LOOKBACK_DAYS` 或新增題材關鍵字，需要知道它們牽動這裡。
- `REMAINING_RISKS.md` RISK-015 加註：覆蓋率量測自本案起可區分 `SOURCE_FAILED`
  （`PRE-G3-02` 當時 `failed_source_keys=None` 的限制解除），**但加註明文邊界**：
  「未納入追蹤關鍵字的股票，其 `SUCCESS_EMPTY` 是『未觀測』而非『觀測到空』，本案
  刻意不改這個既有邊界（§3.2a 選 A）；股價宇宙擴回 459 檔或追蹤關鍵字擴大時，覆蓋率
  數字需重新檢視這批股票是否該改口徑，去處 Gate 4 啟動申請書」。
- `MULTI_SOURCE_DATA_CONTRACT.md`（`VERIFIED THIS SESSION`，已逐字查證 `SOURCE_FAILED`
  相關段落，約 187／224／704／710～714 行）：**沒有「由呼叫端 outcome 決定」這樣的
  措辭**——PO 複核確認為記憶有誤，接受本提案 v1 的判斷。**本案不需要修改本契約文件**，
  新 ADR DEC-042 補上文件裡本來就缺的這一層（失敗鍵怎麼算）。

## 9. Definition of Done

- [ ] Gate A 提案 v2 送審查方複核、PO 核准
- [ ] 8 條紅測全數 FAIL（對現行未修正程式碼），逐條 known-FAIL 輸出附 commit body
- [ ] 7 個自我突變全數被至少一條測試抓到
- [ ] 綠燈實作，全套測試 OK，contract-check 14/14，numstat/-w 無落差
- [ ] 段 B 演練通過（§6 三項，含 Python／SQL 兩個獨立實作互相對照）
- [ ] 段 C 真實執行驗收條件 5（`source_status` 翻轉列在推導集合內）通過
- [ ] 文件同步（§8）完成，結案 commit 送審查方複核

## 10. 流程

本提案 v2 送審查方複核一次，複核通過後 PO 核准；核准後才寫紅測。§3.2／§3.2a 已由 PO
裁定，複核與後續實作不再重新討論這兩點。紅／綠／段 B 演練各自回報，不一口氣跑到底。
