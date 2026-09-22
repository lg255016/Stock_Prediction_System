# Gate A 提案：量測 PTT 回補極限下 458 檔的情緒覆蓋率上限（§0.5 #40）

## 0. 摘要

本案回答一個問題：**若把 `entity_mapping`＋`theme_stock_mapping` 的全部 479 個關鍵字拿去比對 2026-01 之後的 PTT 文章，458 檔裡能有多少檔拿到情緒資料、面板覆蓋率上限是多少。** 純量測案，分三段：段 A（離線重新比對既有語料，零網路）、段 B1（頁面速率探測，小量網路只讀）、段 B2（全量看板掃頁，需要新的只讀量測變體）。**不重跑任何模型、不改 `tracking_keywords`、不寫入任何文章、不修改 `scrape_ptt_board_pages` 的現有行為。**

段 A 的結果（工作單已提供，本提案 §2.1 獨立重算相符）是**嚴格下界**：既有 1,349 篇文章本身是被現行 31 個關鍵字篩選過才進資料庫的語料，重新比對只能找出「已收錄文章裡被順帶提到的其他股票」，看不到任何一篇一個現行關鍵字都沒命中、因此從未被收錄的文章。要量到真正的上限，必須重新向 PTT 取數（段 B），而且要走看板掃頁模式，不走逐關鍵字搜尋——前者的請求數只跟頁數有關，與關鍵字數脫鉤，後者是採用 `UG-G2-SB7` 已經解決的舊模式。

## 1. Requirement Source

PO 開案工作單（2026-09-21），回應 `PROJECT_STATUS.md` §0.5 #39 登記的「第二層：關鍵字（唯一可零成本改善）」與 `RISK-015`。

## 2. Current State（唯讀查證，容器內程式碼閱讀＋`postgres@localhost:5432`唯讀查詢，`VERIFIED THIS SESSION`）

### 2.1 段 A 離線重新比對——獨立重算，工作單數字全部相符

**關鍵字聯集**：

```sql
SELECT COUNT(DISTINCT keyword) FROM entity_mapping;            -- 462
SELECT COUNT(DISTINCT theme_keyword) FROM theme_stock_mapping; -- 17
SELECT COUNT(*) FROM (
  SELECT keyword FROM entity_mapping
  UNION SELECT theme_keyword FROM theme_stock_mapping
) t;                                                            -- 479
```

**重新比對**（取全部 1,349 篇文章的 `title`／`fetch_keyword`／`post_time::date`，對 479 個關鍵字聯集重跑）：

| 口徑 | (股票, 日期) 配對 | 涉及股票數 |
|---|---|---|
| 現行：每篇只用抓到它的那一個 `fetch_keyword` | 1,502 | 30 |
| 全關鍵字重新比對標題 | 1,714 | 86 |

**與工作單逐字相符**（1,502/30 → 1,714/86，倍數 1,714/1,502≈1.14×、86/30≈2.87×，與工作單「1.1×／2.9×」一致）。**獨立驗算過程中自己先算錯一次**：第一次用 `(stock_id, article_id)` 當配對單位，得到 2,854/3,108（stocks 仍是 30/86，因為股票數與「用文章計或用日期計」無關），與工作單對不上；改用 `(stock_id, post_time::date)` 才精確重現 1,502/1,714——**工作單的「配對」指的是（股票,日期），不是（股票,文章）**，記此以免下次誤讀同一個詞。

### 2.2 語料偏誤——確認工作單陳述成立

既有 1,349 篇文章的 `source` 只有兩種：`ptt_board_pages`（1,269 篇，收錄條件是命中 31 個關鍵字之一）、`ptt_stock`（80 篇，切換前遺留）。**沒有一篇文章的存在不依賴於命中某個現行關鍵字**——段 A 的重新比對只能在「已經因為命中而被收錄」的語料內找出「順帶命中的其他關鍵字」，結構上無法發現「一個現行關鍵字都不命中、因此從未被抓取」的文章。這正是段 A 的 86 檔是**嚴格下界**而非上限的原因。

### 2.3 看板模式已完成過一次歷史回補——確認回溯至 2026-01 的機制

```sql
SELECT source, COUNT(*), MIN(post_time), MAX(post_time) FROM market_articles GROUP BY source;
-- ptt_board_pages | 1269 | 2026-01-17 20:51:46 | 2026-09-18 17:30:58
-- ptt_stock       |   80 | 2026-01-01 12:00:00 | 2026-12-29 12:00:00
```

`created_at` 分佈（`VERIFIED THIS SESSION`）：**2026-09-07 13:00（UTC）單一批次寫入 1,249 篇，`post_time` 跨度 2026-01-17～09-06**——這是一次性回補，不是每日 2 天窗口累積出來的（其餘批次：08-20/08-21 共 80 篇即 `ptt_stock` 遺留資料；09-05 起的小批次為每日 ETL 正常增量）。

`scrape_ptt_board_pages(self, keywords, since_timestamp=None, page_budget=BOARD_PAGE_BUDGET)`（`ptt_scraper.py:169-170`，`VERIFIED THIS SESSION` 逐行核對）：`since_timestamp`／`page_budget` 皆為**呼叫端傳入的參數，不是函式內建的能力上限**。`main_etl_pipeline.py:932`：`since_ts = time.time() - BOARD_LOOKBACK_DAYS * 86400`——**`BOARD_LOOKBACK_DAYS=2` 是每日 ETL 呼叫端自己算出來傳進去的值，函式本身沒有 2 天限制**，確認工作單陳述成立，本提案不把它當成論證上限。

### 2.4 請求代價對照——確認看板模式優於逐關鍵字搜尋

`scrape_ptt_board_pages()` 的比對邏輯（`ptt_scraper.py:266-274`）在記憶體中對單次頁面抓取結果逐關鍵字比對，一頁一次請求，與關鍵字數無關；`scrape_ptt_stock_by_keyword()`（策略 A，逐關鍵字打 `/search?q=`）則每關鍵字至少一次請求。看板模式額外優勢：一次抓取的原始頁面內容可離線重複使用（關鍵字清單日後修訂不需要再發請求）——`UG-G2-SB7` 從策略 A 換到策略 B 正是為此。

### 2.5 DEC-032 的請求紀律——本案必須遵守的硬約束

`_fetch_page()`（`ptt_scraper.py:72-92`）唯一的請求出口：`@retry(retry=retry_if_exception(is_retriable), stop=stop_after_attempt(3), wait=wait_exponential(...), reraise=True)`——只對 `is_retriable()` 判定為可重試者（傳輸層失敗、5xx）重試，**4xx（含 403／429）不重試，`reraise=True` 直接向上拋出**；成功後有 1.0～2.5 秒隨機禮貌性延遲。`scrape_ptt_board_pages()` docstring 明文「本方法只透過 `self._fetch_page` 送出請求，不另開 HTTP 入口」，`tests/test_ptt_board_pages.py` 的 `V9MustGoThroughTheSharedFetchPage` 測試類別確認此約束受測試釘住（`VERIFIED THIS SESSION`，讀原始碼與測試檔確認）。**本案的量測變體必須沿用這個唯一出口，不得繞過。**

### 2.6 可觀測性缺口——`http_attempts` 確認全為 NULL，但逐日範例數字需訂正

```sql
SELECT COUNT(*) FROM etl_run_log WHERE source ILIKE '%ptt%';                            -- 147
SELECT COUNT(*) FROM etl_run_log WHERE source ILIKE '%ptt%' AND http_attempts IS NULL;  -- 147
```

**核心宣稱（PTT 的 147 列 `http_attempts` 全為 `NULL`）確認成立。** 但工作單引用的逐日範例數字與本次唯讀重查不符：

| 日期 | 工作單陳述 | 本次重查 |
|---|---|---|
| 2026-09-05 | 25 列，全 `NO_DATA` | **26 列**（25 `NO_DATA` + 1 `OK`） |
| 2026-09-19 | 62 列（8 OK／54 NO_DATA） | **31 列**（4 OK／27 `NO_DATA`） |

四個 `batch_key` 的完整分佈（`VERIFIED THIS SESSION`）：09-05 共 26（25 `NO_DATA`+1 `OK`）、09-17 共 59（46+13）、09-18 共 31（27+4）、09-19 共 31（27+4），總計 147，與總數核對一致。**「62／8／54」的成因已查明**：工作單原始查詢的時間篩選為 `started_at > '2026-09-18 12:00:00'`，而 09-18 批次（`started_at` 2026-09-18 14:45:47）與 09-19 批次（`started_at` 2026-09-19 00:26:10）皆落在此區間之後——**該篩選橫跨了兩次獨立執行**：31（09-18，4/27）+ 31（09-19，4/27）= 62（8/54），逐項核對相符（`VERIFIED THIS SESSION`，重跑同一條件得到 `(62, 8, 54)`）。成因是**篩選條件的時間邊界與記錄的執行粒度不一致**（用連續時間窗篩選，卻把結果當成單次執行的統計），不是資料異常。核心結論（`http_attempts` 結構性全為 `NULL`）不受影響，§6 的登記事項採本次以 `batch_key` 分組得到的準確逐日數字。

### 2.7 送審前突變測試（記憶體內，未落地，`VERIFIED THIS SESSION`）

對 §2.1 的重算邏輯做兩次刻意破壞性檢驗：

**突變 1（關鍵字聯集完整性）**：把 `kw2stocks` 的建構改成只讀 `entity_mapping`（漏掉 `theme_stock_mapping` 的 17 個關鍵字），重算後 stocks 從 86 降為 **75**、pairs 從 1,714 降為 **715**（實際執行結果；**本節初版曾誤植未經執行的猜測數字 84／1,675，發現後已重新實測訂正——此記錄依複核意見保留，日後修訂本提案或移入 `closed/` 時不得刪除**）——確認關鍵字聯集缺漏會被腳本的輸出數字察覺，不是靜默吞掉。

**突變 2（比對邏輯本身，複核第二輪要求追加）**：把 `if kw in title` 的子字串包含比對改成 `if kw == title` 的完全相等比對，重算後 pairs 與 stocks **雙雙崩為 0**（實際執行結果：`pairs=0 stocks=0`，因為 1,349 篇文章的標題沒有任何一篇與關鍵字字串逐字相等，標題必然帶有周邊文字）——確認整個量測結論所依賴的那一行比對邏輯本身有 known-FAIL 覆蓋，不是只驗過關鍵字清單的完整性、卻從未驗過比對方式本身。

## 3. 設計提案

### 3.1 段 A：離線重新比對腳本（零網路，可在提案核准後直接執行）

新增唯讀腳本 `scripts/verify/measure_ptt_keyword_coverage_offline.py`：
1. 讀 `market_articles`（`article_id`／`title`／`fetch_keyword`／`post_time`）與 `entity_mapping`／`theme_stock_mapping` 的關鍵字-股票映射（479 個聯集）。
2. 產出 §2.1 的兩種口徑（現行 vs 全關鍵字重新比對）：`(stock, date)` 配對數、涉及股票數。
3. **開檔前先核對 sha256**：面板檔案的完整路徑為 `D:\Python\Database_Backups\Stock_Prediction_System2\ml_panels\panel_target_up_down_20260912.parquet`（容器內掛載於 `/workspaces/Database_Backups/Stock_Prediction_System2/ml_panels/`，**不在 repo 或容器工作區內**，本次獨立以 `sha256sum` 核對與 `DECISIONS.md` `39dc6b8e6160add20f39a7265bad04de50c76199fa7ab81b979a7aabeabbd014` 相符，`VERIFIED THIS SESSION`）。腳本開檔前必須重新核對此 sha256，不符即中止，不得靜默照跑；它是 Gate 3 已凍結並已消耗的交付物，全程唯讀，不重算、不覆寫。
4. **套到面板窗口——口徑不得混用（複核第二輪訂正）**：`article_count > 0` 與 `sentiment_5d_ma notna` 是兩種不同語意的覆蓋率（後者是 5 日移動平均，會把單日訊號往後攤約 5 列，兩者在同一個 24,450 列子集上分別是 2.79%（683 列）與 5.76%（1,409 列），`VERIFIED THIS SESSION` 逐一核對）。段 A／B2 重新比對出的 `(stock, date)` 對映語意等同 `article_count>0`（「哪些格子有至少一篇命中」），**主要比較對象為 2.79% 這個同語意基準**，報告需明寫「新覆蓋率 vs. 2.79%（`article_count>0`）」。**次要／選配指標**：腳本可另外對新對映套用與 `sentiment_5d_ma` 相同的 5 日移動平均邏輯，算出與現有 5.76% 頭條數字可比的版本，但輸出時**兩個數字分開標示口徑**（例如 `coverage_raw_hit_pct` vs. `coverage_5d_ma_pct`），不得只寫一個數字讓讀者誤判是同一口徑的改善倍數。
5. 輸出至 `doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_offline_rematch.json`，含逐股票明細（每檔命中的日數，供段 B2 比對）。
6. **零寫入**：全程只 `SELECT`，不 `INSERT`/`UPDATE`，不連線 PTT。

### 3.2 段 B1：頁面速率探測（小量網路，只讀不寫，需 PO 另外授權才可執行）

新增唯讀腳本 `scripts/verify/measure_ptt_board_page_rate_probe.py`：

**複核第二輪訂正：不呼叫 `scrape_ptt_board_pages()`。** 該函式對每個 `r-ent` 只在命中關鍵字時才記錄列（`ptt_scraper.py:266-274`），頁面 HTML 解析後即捨棄；若以 `keywords=[]` 呼叫，比對迴圈不執行，`rows` 恆空、`outcome` 依既有邏輯（`ptt_scraper.py:319-321`：`if not rows and outcome == "OK": outcome = "NO_DATA"`）轉為 `NO_DATA`，**回傳零可用資訊，卻已經實際送出 `page_budget` 次請求**——與腳本自建的最小抓取函式（見下）疊加會讓 B1 的請求數平白加倍，直接違反本案以節制請求為前提的設計（`RISK-002`）。

1. **腳本自建最小抓取函式**（不修改、不呼叫 `scrape_ptt_board_pages()`）：只透過 `PttScraper()._fetch_page` 這個唯一出口取得頁面 HTML，自行解析每個 `r-ent`，記錄標題數、去重後標題數、每篇是否有連結（已刪除文章無連結，本探測統計跳過筆數）、頁面最新／最舊時間戳。此函式與段 B2 共用（見 §3.3 的只讀量測變體）。
2. **實測值輸出**：總頁數、總耗時、頁/秒速率、回溯到的最舊 `post_time`（是否達到或超過 2026-01-01）、每頁標題數分佈、已刪除文章跳過筆數。
3. **請求間隔與硬上限**（§5 已裁定，逐項落實）：頁與頁之間沿用 `_fetch_page()` 既有的 1.0～2.5 秒隨機禮貌性延遲（**不額外加碼，也不縮短**——沿用已核准的既有節奏，不在本案引入新的時間常數）；本段硬上限 30 頁；撞到 403／429（`_fetch_page` 的 `@retry` 條件已保證不重試、直接拋出）即中止，腳本捕捉例外、記錄已完成頁數與例外訊息、正常結束（不視為腳本錯誤，視為**觀測**，寫入 evidence JSON）。
4. 由實測頁/天速率推算「回溯到 2026-01-01 需要幾頁」，作為段 B2 `page_budget` 的推算依據。**不採用 PO 粗估的 900～1,000 頁作為提案內的參考值**——工作單已明確此為 `INFERENCE`、不作為提案依據，段 B2 的預算以 B1 實測值加緩衝為準。

### 3.3 段 B2：全量看板掃頁 + 只讀量測變體（需 PO 另外授權，且以 B1 報告為前提）

**新增方法 `PttScraper.scrape_ptt_board_pages_capture_all()`**（與 `scrape_ptt_board_pages()` 並列的獨立方法，**不修改、不共用** `scrape_ptt_board_pages()` 的函式本體一個字元）：

- 簽章：`scrape_ptt_board_pages_capture_all(self, since_timestamp=None, page_budget=BOARD_PAGE_BUDGET)`——**不接受 `keywords` 參數**，因為它的用途就是捕捉全部標題，不做關鍵字過濾。
- 內部邏輯複製 `scrape_ptt_board_pages()` 的翻頁／停止／例外分類骨架（`page_newest` 取最新一篇判斷停止、第一頁失敗拋 `PttSourceUnavailableError`、後續頁失敗轉 `SOURCE_DEGRADED`、預算用盡未達 `since_timestamp` 同樣轉 `SOURCE_DEGRADED`），但**移除關鍵字比對迴圈**，改為無條件記錄每個 `r-ent` 條目的 `title`／`url`／`date`（索引頁 `MM/DD` 欄原始值）／`push_count`／`author`（去重鍵改為單純 `url`，因為沒有關鍵字維度）。
- **唯一請求出口不變**：一樣只透過 `self._fetch_page()`。
- 輸出全部標題（不論是否命中任何關鍵字）至本機 JSONL 檔（例如 `scripts/verify/evidence_local/ptt_board_full_scrape_<timestamp>.jsonl`，**不進 `doc/upgrade/gates/evidence/`**——原始網頁擷取內容體積大且非治理文件，僅摘要與統計數字進 evidence JSON）。**不寫入 `market_articles` 或任何資料表**。

**日期推導——複核第二輪追加的硬性規定**：索引頁的 `date` 欄只有 `MM/DD`，沒有年份，不可直接當成量測用的日期。`src/transform/data_cleaner.py:76` 的 `parse_ptt_post_time(url, date_str, reference_time=None)` 已是本專案處理這個問題的權威實作——「優先取網址內嵌的 unix 時間戳，索引頁日期欄僅作回退」。**離線比對階段的日期一律呼叫 `parse_ptt_post_time(url, date_str)` 推導，不得直接使用索引頁原始 `date` 欄。** `VERIFIED THIS SESSION` 對既有語料的驗證：`ptt_board_pages`（1,269 篇）網址時間戳與資料庫 `post_time` 逐篇同日，0 篇需要回退；`ptt_stock`（切換前遺留 80 篇）僅 4 篇同日、76 篇不同且全數跨年——**回溯到 2026-01-01 的掃頁必然翻進 2025-12，正是最容易誤判年份的區段**，`_url_timestamp()` 解析失敗時既有設計回傳 `None`（不是 0，避免誤判為「已回溯夠遠」而提早停止），段 B2 的日期推導必須沿用同一原則。**報告須列出有幾筆記錄實際走了回退路徑**（即 `_url_timestamp()` 解析失敗、只能用 `MM/DD` 猜年份的筆數）——走回退路徑的記錄在涉及跨年的區段不可信，量測報告需單獨標示，不與網址時間戳可靠推導出的記錄混在一起計入覆蓋率。

**離線後處理**：對 §3.3 產出的全量標題（含已推導的可靠 `post_time`），用 §3.1 腳本的比對邏輯（不重複實作，import 共用）對 479 個關鍵字聯集比對，算出精確上限：多少檔拿到資料、面板覆蓋率上限（口徑比照 §3.1 的訂正，明寫是對 2.79% 還是 5.76% 的可比版本）、**每檔的文章日數分佈**（直方圖，用於判斷該檔的訊號密度是否足以支撐 43 個時間窗的模型，而不只是總數）。

**請求上限與中止規則**：`page_budget` 取 B1 實測值加緩衝（緩衝幅度由 B1 報告當下與 PO 討論定案，本提案不預先訂死數字）；`RISK-002`（PTT 被 Rate Limit 封鎖）為本段主要風險，撞到 403／429 時（`_fetch_page` 的 `@retry` 已保證不重試）腳本必須**立即中止、記錄已完成頁數與已擷取內容、正常結束**，不得重跑補足；outcome 若為 `SOURCE_DEGRADED`（預算用盡未達 2026-01-01），照實記錄涵蓋範圍，**不得為了「湊到 2026-01-01」而追加預算重跑**——除非 PO 另外授權新一輪。**段 B1 與段 B2 不得連續執行**（§5 硬性規定），兩段之間至少間隔一次 PO 的明確授權動作。

**段 B2 策略裁決（PO 2026-09-21，B1 報告後追加）**：B1 訂正版實測 `pages_per_day≈2.31`，回溯到 2026-01-01 約需 577 頁（09-19 日誌另估上界約 920 頁）。PO 在「分段各自授權」／「一次跑完照舊延遲」／「一次跑完延遲加倍」三個選項中選擇**一次跑完、延遲加倍**——分段需要額外設計「從指定頁碼起抓」的續傳邏輯，B2 的產出是一次性語料，不值得為它擴設計；照舊延遲下 25～37 分鐘的連續請求，PO 認為風險暴露不放心。

- **`extra_page_delay` 參數**（新方法專屬，不影響 `_fetch_page()`／`scrape_ptt_board_pages()` 一個位元組）：`scrape_ptt_board_pages_capture_all(self, since_timestamp=None, page_budget=BOARD_PAGE_BUDGET, extra_page_delay=0)`。預設 `0`——維持不變的既有行為，只有 B2 腳本呼叫時才傳入非零值。`extra_page_delay` 非零時，新方法在每頁處理完畢後**另加**一段 `random.uniform(1.0, 2.5)` 秒等待（與 `_fetch_page()` 既有延遲的區間相同、獨立疊加），合計每頁延遲 2.0～5.0 秒——**延遲加倍不是修改 `_fetch_page`（DEC-032 唯一請求出口不得修改），是新方法自己額外多等一段**。
- **`page_budget=950`**：B1 推算 577，取 09-19 日誌估的上界 920 再留緩衝，取整為 950。
- **時間預估**：950 頁 × 每頁約 4.9 秒（1.0～2.5 秒既有延遲＋1.0～2.5 秒額外延遲的期望值中段＋實際請求延遲，比照 B1 實測平均值換算）≈ **預期約 50 分鐘，最壞約 78 分鐘**；實際到達 `since_timestamp=2026-01-01` 即停，預期約 600 頁即可回溯完成，950 只是硬上限。
- 中止規則、`SOURCE_DEGRADED` 語意、「段 B1／B2 不得連續執行」皆不變，照本節上方既有規定。

### 3.4 未回溯到 2026-01-17 更早處的邊界性質判定——歸屬段 B2，段 B1 僅有條件回報（複核第二輪訂正）

現有 09-07 回補批次最舊到 2026-01-17 20:51:46，但**該次回補未走每日 ETL 路徑，`etl_run_log` 沒有對應列可查其 outcome**（`NOT VERIFIED`，工作單已標註）。判定「01-17 是看板保留邊界還是當初預算用盡」需要翻頁翻到比 01-17 更舊，而段 B1 的硬上限是 30 頁（§3.2）——以待實測的頁/天速率量級估算，30 頁大約只能回溯一週左右，遠不足以觸及 01-17。**段 B1 在其自身預算內結構上無法回答這個問題，不列為 B1 的交付項**，避免一個段落背負它自己做不到的交付。

- **段 B1（有條件回報）**：若 30 頁預算內翻頁本身就中斷（連不上上一頁、或遇到 PTT 站方層級的顯示限制），這本身即為觀察到的邊界，B1 據實回報；否則 B1 在報告中明確寫「本段預算不足以判定，留待段 B2」，不得留白不提。
- **段 B2（正式交付項）**：`page_budget` 已依 B1 實測速率加緩衝、足以回溯到 2026-01-01 附近，若在此過程中翻到比 01-17 更舊的文章，代表當初回補是**預算用盡**；若在某處翻頁卡住，代表那是**看板保留邊界**——後者本身就是本案「PTT 回補極限」量測結果的一部分，需寫入最終報告，不只是一則旁註。

## 4. Tests（先紅後綠，紅 FAIL 數＝新增測試數，`TEAM_PLAYBOOK.md` A13）

新測試檔：`tests/test_ptt_board_pages_capture_all.py`（5 個測項、展開為 10 條實際斷言，全數鎖定**新方法** `scrape_ptt_board_pages_capture_all()`，對現行程式碼皆為 `AttributeError`——紅測 FAIL 數＝10，與新增測試數一致）

| # | 測試 | Known-FAIL 構造法 |
|---|------|-------------------|
| 1 | `scrape_ptt_board_pages_capture_all()` 對含多篇文章的合成頁面，回傳全部標題，不受任何關鍵字過濾（因為根本不接受 `keywords` 參數） | 對現行程式碼：`AttributeError`（方法不存在） |
| 2 | 該方法**只透過** `self._fetch_page` 送出請求（mock `_fetch_page`，斷言其為唯一被呼叫的網路介面；比照既有 `V9MustGoThroughTheSharedFetchPage` 的構造法） | 對現行程式碼：同上 `AttributeError` |
| 3 | `page_budget`／`since_timestamp` 的停止邏輯與 `scrape_ptt_board_pages()` 行為一致（複用既有 V8/V10 等測試的合成頁面 fixture，驗證新方法在相同輸入下的頁數/停止時機相同） | 同上 |
| 4 | 第一頁抓取失敗 → 拋 `PttSourceUnavailableError`；後續頁失敗 → 保留已收集資料、`SOURCE_DEGRADED` | 同上 |
| 5（新檔） | **`extra_page_delay`（PO 裁決 2026-09-21 段 B2 補段）**：預設 `0` 時不呼叫 `time.sleep`（mock 斷言 `call_count==0`）；`extra_page_delay>0` 時每頁恰呼叫一次額外延遲、區間為 `random.uniform(1.0, 2.5)`（mock `time.sleep`／`random.uniform`，斷言呼叫次數與參數） | 對現行程式碼：同上 `AttributeError`；方法存在後，known-FAIL 為把預設值改成非 0——`test_default_zero_does_not_sleep` 會轉為 FAIL |

**測項 5：`scrape_ptt_board_pages()` 行為金標——改放既有測試檔（複核第三輪訂正，採複核給的兩個選項之一）**

測項 5 鎖定的是**既有、未修改**的 `scrape_ptt_board_pages()` 方法，在現行程式碼上引入時即會 **PASS**，不會 FAIL——若列在新測試檔的紅測清單裡，會讓「紅 FAIL 數＝新增測試數」這個表格標題本身不成立，這正是 `TEAM_PLAYBOOK.md` A13 描述的同一種缺陷形狀（一條新增測試在修法前的舊程式碼上也會 PASS，未被發現就混入紅測清單當作證據）。**修法**：測項 5 不進新測試檔，改為 `tests/test_ptt_board_pages.py` 新增第 19 條（既有 18 條不動）。這樣一來，新檔的 4 條測試全數為真紅測，A13 在新檔內自然成立；測項 5 作為隨新方法一併引入的**回歸鎖定**，docstring 需明寫：本測試在引入時即為綠燈，其偵測力不由紅測階段證明，而由送審前已實際執行的突變證明（見下表構造法欄）。

| 新增於既有檔（`tests/test_ptt_board_pages.py` 第 19 條，原 18 條不動） | Known-FAIL 構造法 |
|---|---|
| `scrape_ptt_board_pages()` 行為金標：沿用既有 `board_page_html()` fixture（`tests/test_ptt_board_pages.py:34`），對 3 篇合成標題（含 2 篇分別命中「台積電」「聯發科」、1 篇不命中）呼叫 `scrape_ptt_board_pages(["台積電","聯發科"])`，斷言回傳 2 列、`fetch_keyword` 集合為 `{"台積電","聯發科"}`、`outcome=="OK"`——即「舊方法行為沒變」用**行為**表達，不用原始碼文字表達 | **真實 known-FAIL，本提案送審前已在容器內 `/tmp` 拋棄式 mirror 實際構造並執行、非猜測**：把 `scrape_ptt_board_pages()` 的比對邏輯 `if kw not in title: continue`（子字串包含）改成 `if kw != title: continue`（完全相等），對同一組合成 fixture 重跑，回傳列數從 2 降為 0、`outcome` 從 `OK` 轉為 `NO_DATA`；復原後重跑確認回到 2 列／`OK`，mirror 事後整個刪除，`git status` 確認真實 repo 全程未被觸碰。（原提案初版誤寫「大小寫敏感度翻轉」為構造法，經實際嘗試前檢查才發現中文字無大小寫之分、該突變對既有 fixture 不會改變任何行為，已改用「子字串→完全相等」這個真正會改變輸出的突變，並在寫入本表前才送出。） |

**測項 5 的設計理由**：原提案的「位元組級原始碼比對」被複核第二輪指出三項缺陷而撤回——(a) 唯一可構造的 known-FAIL 只是「方法不存在」，不是「方法本體被改動」，不符合 `CLAUDE.md` §9A.2 對 known-FAIL 案例的要求；(b) 比對固定行區間對「新方法插在舊方法之前」這種常見排列方式結構性盲目，行號位移後仍可能誤判 PASS；(c) `DEC-032` 的請求紀律有一部分住在 `_fetch_page()`，不在 `scrape_ptt_board_pages()` 的行區間內，改動 `_fetch_page` 不會被這項檢查察覺。行為金標改為直接斷言輸出行為，known-FAIL 已實際構造並執行，不受行號位移影響，也自然涵蓋任何會改變輸出的修改（含 `_fetch_page` 的行為若透過既有測試層面反映）。

**原測項 6 移至 §7（複核第二輪訂正）**：「每日 ETL 呼叫路徑零變動、既有 `tests/test_ptt_board_pages.py` 全數維持 PASS」本身不構成新增紅燈，留在本表會與表格標題「紅 FAIL 數＝新增測試數」互相矛盾——它是 DoD 檢查項，不是測試，移至 §7。

## 5. Affected Components

- `scripts/verify/measure_ptt_keyword_coverage_offline.py`（新建，段 A）
- `scripts/verify/measure_ptt_board_page_rate_probe.py`（新建，段 B1）
- `src/extractors/ptt_scraper.py`（新增 `scrape_ptt_board_pages_capture_all()` 方法，段 B2；**不修改任何既有方法**）
- `tests/test_ptt_board_pages_capture_all.py`（新建，測項 1～5，含 `extra_page_delay`）
- `tests/test_ptt_board_pages.py`（新增第 19 條，測項 5 行為金標／回歸鎖定；原 18 條不動）
- `doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_offline_rematch.json`（段 A 產出）
- `doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_rate_probe.json`（段 B1 產出）
- `doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_full_scrape_report.json`（段 B2 摘要，原始標題另存本機 JSONL，不進 repo）
- 唯讀參考（不修改）：`main_etl_pipeline.py`（**repo 根層，不在 `src/` 底下**，`:932` 為 `BOARD_LOOKBACK_DAYS` 呼叫端算式所在處，`VERIFIED THIS SESSION`）、`src/transform/data_cleaner.py:76`（`parse_ptt_post_time`，段 B2 日期推導的權威實作）、面板檔 `D:\Python\Database_Backups\Stock_Prediction_System2\ml_panels\panel_target_up_down_20260912.parquet`（唯讀，開檔前核對 sha256）

**明確不動**：`tracking_keywords`（任何列）、`market_articles`／`article_comments`（零寫入）、`daily_ml_features`／任何面板 parquet（零重算）、`scrape_ptt_board_pages()` 方法本體（`tests/test_ptt_board_pages.py` 第 19 條行為金標驗證）、既有 18 條測試（不改一字）、`src/extractors/retry_policy.py`（DEC-032 的判準本身不動）、`src/transform/data_cleaner.py`（僅唯讀呼叫既有函式，不修改）。

## 6. 順便登記（不在本案處理）

`PROJECT_STATUS.md` §0.5 新增候補：`etl_run_log.http_attempts` 欄位存在但 PTT 來源（`source='ptt'`）147 列全為 `NULL`——log 看起來詳細（依日期分 26～59 列不等），但那是**關鍵字維度**（每個追蹤關鍵字各記一列 `OK`/`NO_DATA`），真正的成本維度（頁數／請求數）一列都沒有。登記方向：PTT 兩種模式都應填 `http_attempts`，看板模式填實際頁數、搜尋模式填實際請求數。**本案不做**，純登記；登記時採 §2.6 本次唯讀重查的準確逐日數字，不採工作單的範例數字。

## 7. Definition of Done

- [ ] 段 A：腳本產出 §2.1 的兩種口徑數字與面板覆蓋率下界，口徑不得混用（§3.1 第 4 點），開檔前 sha256 核對，evidence JSON 落地
- [ ] 段 A：零網路，本提案核准即在授權範圍內，**不需另外授權**
- [ ] 段 B1 必須在段 A 送審並核准之後才可排程，**且需 PO 另外一次明確授權**；不呼叫 `scrape_ptt_board_pages()`（§3.2 訂正），全程走自建最小抓取函式；產出頁/天速率、回溯到的最舊時間戳是否達 2026-01-01、每頁標題數分佈、已刪除文章跳過筆數；§3.4 的邊界判定僅有條件回報，evidence JSON 落地，報告送 PO
- [ ] 段 B2：**需 PO 另外明確授權，且以 B1 報告已送 PO 為前提**；`scrape_ptt_board_pages_capture_all()` 紅測→綠燈，新測試檔 10 條全數 PASS（測項 1～5，紅測 FAIL 數＝10，含 `extra_page_delay` 預設 0／非 0 兩態）；既有 `tests/test_ptt_board_pages.py` 新增第 19 條（V19，行為金標，引入時即綠燈、已實際構造 known-FAIL）維持 PASS；`page_budget=950`、`extra_page_delay` 非零（延遲加倍）；日期一律經 `parse_ptt_post_time()` 推導，回退路徑筆數獨立標示（沿用 B1 的 `_exclude_pinned_outliers()` 置底排除邏輯）；全量標題落地本機 JSONL；離線比對產出精確上限（涉及股票數、面板覆蓋率上限、逐檔日數分佈）；§3.4 的保留邊界／預算用盡判定完成
- [ ] **每日 ETL 呼叫路徑零變動**（原測項 6，移自 §4）：既有 `tests/test_ptt_board_pages.py` 原 18 條（新增第 19 條後共 19 條）全數維持 PASS，不因新增 `scrape_ptt_board_pages_capture_all()` 而受影響
- [ ] 段 B1／B2 之間至少間隔一次 PO 授權動作，不得連續執行
- [ ] 撞到 403／429 時腳本正確中止、不重試、記錄已完成進度
- [ ] 全套測試 `python -m unittest discover -s tests -p "test_*.py"` 無回歸
- [ ] `python scripts/verify/gate0_contract_check.py` exit 0
- [ ] numstat／`-w` 無落差
- [ ] §6 的可觀測性缺口候補登記（純文件，可與段 A 同批或獨立處理）

## 8. 流程

本提案先送審查方複核（含 §3.1 段 A 腳本設計與口徑選擇、§3.2 段 B1 探測設計與速率推算方法、§3.3 段 B2 只讀量測變體的設計與日期推導規則、§3.4 邊界判定的段落歸屬、§4 行為金標的 known-FAIL 構造）；通過後送 PO 核准。核准後：**段 A 可直接執行**（零網路，不需另外授權）→ 送複核 → 報告 PO。**段 B1 需 PO 另外明確授權**；B1 報告 PO 過目後，**PO 決定是否授權段 B2**。段 B2 前需先完成 `scrape_ptt_board_pages_capture_all()` 的紅測→綠燈（純程式碼，不涉及真實網路，可與段 B1 授權平行進行，唯執行段 B2 本身仍需段 B1 報告核可）。全案結束後彙整一份量測報告，不寫入任何生產資料。
