# 首次每日 ETL 缺口自動追補——真實庫執行報告（成功）

## 零、關鍵發現先講

**首次每日 ETL 真實執行成功，`exit code 0`，全程無例外，無 Gemini 429。** 2026-09-17
20:04 台北時間開始，20:08 前完成，在 PO 授權的 20:18 前時限內。這是本案（缺口自動追補＋
§0.5 #30 n_lag 修法）第一次完整跑通到底（前一次真跑於 NLP 階段被 Gemini 每日配額打光中止，
見 `FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_aborted.md`）。

**三件事在複核過程中修正，寫在這裡避免讀者誤解：**

1. **段 B／段 C 驗收條件 2 的判準訂正**：原措辭「本次執行新增或更新的映射」對「題材情緒
   溢出對全歷史面板重算」這個既有機制（`FeatureAggregator`，`DECISIONS.md` 784 行附近）
   而言不精確——溢出邏輯每次執行都會把**尚未被套用過的映射**（不論那條映射是哪一次執行
   寫入的）一次套到相關股票的整段歷史。PO 複核後把判準訂正為「`updated_at` 晚於**上一次
   成功完成特徵階段**的映射」，這樣就能寫成可機械判定的 SQL，不需要每次都問。見四之 2。
2. **8299（群聯）的 152 列情緒欄變動來源**：`記憶體 → 8299` 這條 `theme_stock_mapping`
   映射**不是本次執行新增的**——寫入時間是 `2026-09-17 00:45:12`（前一次中止真跑的 AI
   探索階段，該次探索在 NLP 撞配額前已成功寫入題材映射，見 aborted 報告四之 1）。本次是
   這條映射第一次被特徵聚合器套用（上一次成功完成特徵階段是 09-12），回溯到「記憶體」
   題材第一篇相關文章出現的日期（2026-01-19）。
3. **容器 `core.autocrlf=true`**：段 C 前置檢查發現容器內 `git status` 顯示約 48 個檔案
   「已修改」，逐檔以「去除 `\r` 後比對 md5」驗證，**全部是 CRLF/LF 行尾差異，零實質內容
   差異**——根因是容器的 git 從未設定 `core.autocrlf`（host 是 `true`）。PO 指示對齊，已在
   容器執行 `git config core.autocrlf true`（**純 git 設定，非版控內容，不影響任何檔案位元
   組**），設定後容器 `git status --short` 確認乾淨。

## 一、執行時間軸（全部使用容器內 `now_taipei()`）

| 事件 | 台北時間 |
|---|---|
| 段 C 前置包完成（含容器 `core.autocrlf` 訂正） | 2026-09-17 20:0x |
| PO 綁定確認（RISK-013，本輪） | 2026-09-17 20:0x |
| 執行前最終 DB 身分確認 | 2026-09-17 20:04:02 |
| 真實執行開始（`python main_etl_pipeline.py`） | ~20:04 |
| 執行完成（`exit code 0`） | ~20:08（log 檔寫入完成時間 20:08:28） |
| `etl_run_log` 今日新增列時間跨度（UTC，僅涵蓋批次/PTT 階段） | 12:05:05.86～12:06:45.38（＝台北 20:05:05～20:06:45，99.52 秒） |
| POST 備份建立 | 2026-09-17 20:09 |

**總耗時估計**：以「執行前最終確認」（20:04:02）到「log 檔寫入完成」（20:08:28）估算，
約 **266 秒（4 分 26 秒）**——這是上界估計（含極短的工具往返時間），非逐階段精確計時
（本次直接執行 `python main_etl_pipeline.py`，未套用像前次中止那樣的自訂計時 harness）。
`etl_run_log` 本身只覆蓋批次取價與 PTT 兩段（99.52 秒），AI 探索（含 Gemini 呼叫）、NLP、
特徵工程（449,326 列全量寫入）、尾端掛點（5,967 列）四段不寫 `etl_run_log`，其耗時只
反映在前述的整體上界估計裡，無法從 log 拆分。**RISK-005 的計時基準見四之 3，此限制已
一併寫入。**

## 二、前置步驟（依綁定確認包執行，全部通過）

1. **拋棄式容器清理**：`sps_stageB_rehearsal`（段 B 演練用）先 `docker stop && docker rm`
   （只 rm，`postgres:18` image 確認未受影響）。
2. **Commit 確認**：HEAD＝`048e975`，host 與 container 一致；hooksPath 兩邊皆為
   `.githooks`；容器 `core.autocrlf` 訂正後 `git status --short` 乾淨（見零之 3）。
3. **PRE 備份**：`stock_prediction_system2_PRE_first_daily_etl_20260917_1948.dump`
   （19:48 建立，122,021,783 bytes）。還原至拋棄式容器 `sps_stageC_pre_verify`（port 55433）
   驗證，7 表＋`null_sentiment`(10)＋`theme_stock_mapping`(53)＋啟用關鍵字(28) 與真實庫
   當下逐項相符，驗證後 `docker rm`。
4. **PTT 探測**：1 次，200。未另行探測 Gemini。
5. **連線目標與現況確認**：`current_database()=postgres`、`inet_server_port()=5432`；
   `now_taipei=2026-09-17 19:52:29`，`today_taipei=09-17`，`previous_business_day=09-16`，
   `n_lag=8`（F=09-04, P=09-16）；`candidate_prices` 兩市場皆已達 `previous_business_day()`
   （價格缺口 0，批次請求預期 0）；8 檔啟用標的（7 檔 TWSE/TPEX＋NVDA，預期逐股 0＋
   NVDA 1）。

## 三、執行內容（全部成功）

- **批次取價**：0 請求（價格缺口確實是 0，log 開頭直接跳過該段落）。
- **逐股階段**：`tracked_stocks_daily` 1 筆 `OK`（NVDA，63 筆股價資料寫入）。與段 B 演練、
  前置確認完全一致。
- **AI 熱門趨勢探索**：真實執行（非 no-op），Gemini 呼叫 **1 次**，未撞限速或配額。發現
  3 個新題材（高頻寬記憶體(HBM)、銅箔基板(CCL)、營建營造），10 筆題材成分股關聯寫入
  `theme_stock_mapping`（HBM 4、CCL 3、營建營造 3），3 個新關鍵字寫入 `tracking_keywords`
  （啟用關鍵字 28→31）。
- **PTT 看板**：31 個關鍵字，8 頁請求，15 筆命中，`OK 7／NO_DATA 24／FETCH_FAILED 0`。
  新增 6 篇文章、174 則留言（4 篇「記憶體」、1 篇「聯發科」、1 篇「AI伺服器」）。
- **NLP 情緒運算**：16 篇待處理（原 10 篇 NULL＋新 6 篇），Gemini 呼叫 **1 次**（單一
  batch prompt 處理 6 筆複雜標題，`_generate_content_with_retry` 只被呼叫一次，非逐篇
  呼叫）。**本次執行 Gemini 總計 2 次**，未撞每日配額。16 篇情緒分數全部寫入，`market_articles`
  未評分文章數：10→**0**。`sentiment_cache` 36→42（+6）。
- **特徵工程**：股價 449,326 筆、文章 1,266 筆，Cutoff 15:30:00，449,326 列寫入
  `daily_ml_features`（全量面板重算，既有設計特性）。
- **尾端掛點重算**：`tail_window=13`（`TRIPLE_BARRIER_HOLDING_PERIOD(5)+n_lag(8)`），
  5,967 列更新，`n_updated(5967)==len(tail)(5967)`，無 WARNING。

## 四、post-execution 四條驗收（PO 訂正後版本）

**以 20:04 執行前的 PRE 備份還原為 before，真實庫現況為 after**（還原容器
`sps_stageC_pre_verify`／`sps_stageC_post_verify`／`sps_stageC_evidence` 皆已
`docker rm`，`postgres:18` image 與真實 app/db 容器確認未受影響）。

### 1. 價格衍生 10 欄：F（09-04）以前、458 檔台股，逐列零差異——**PASS**

`close_price／volume／return_1d／rsi_14／volatility_5d／volatility_20d／amplitude_ratio／
ma5_bias_ratio／ma20_bias_ratio／volume_ratio_5d` 十欄逐欄核對，全部 **0 差異**。

### 2. 情緒／留言／`source_status` 欄——**PASS（訂正判準後）**

訂正後判準：「(a) `theme_stock_mapping`／`entity_mapping`／`tracking_keywords` 中
`updated_at` 晚於上一次成功特徵階段時間（**2026-09-12**，`UG-G3-SB2a` 重跑 RISK-027 那次）
的列所涉及的股票（全歷史）；或 (b) 本次新增文章與留言依 cutoff 歸日後涉及的 (股票,日期)
及其 5 日滾動延伸」。

187 列相異中，35 列（7 檔追蹤標的 × 各 5 個日期 08-31～09-04）只動 `target_*`／
`label_reason`，屬條件 3；152 列屬本條件，全部集中在單一股票 **8299**（群聯），來源即
零之 2 所述、`記憶體→8299` 映射（`updated_at=2026-09-17 00:45:12`，晚於上次成功特徵階段
09-12）——**符合訂正後判準 (a)**，且「記憶體」正是本次新增文章的 fetch_keyword 之一
（同時符合 (b) 的觸發語意）。逐列差異表：見
`FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success_diff_table.json`。

### 3. 標籤／目標欄：變動須落在各股尾端 `tail_window` 內——**PASS**

35 列（7 檔追蹤標的，08-31～09-04）只動 `target_next_close／target_return_1d／
target_up_down／target_triple_barrier／label_reason`，全部落在 `tail_window=13` 涵蓋範圍
內（各股最後 13 個交易日）。8299 亦有同形狀的 5 列（08-31～09-04）落在其自身 tail_window
內（8299 屬「全部股票」尾端重算範圍，非僅追蹤中的 8 檔）。

### 4. `daily_ml_features` 新增列數——**PASS，精確吻合**

預期值＝逐股計算 `stock_prices` 中 `trade_date > F`（F=09-04）的相異交易日數再加總：

| stock_id | 新增交易日數 |
|---|---|
| 2454 | 8 |
| 2059 | 8 |
| 2330 | 8 |
| 3008 | 8 |
| 6488 | 8 |
| 2382 | 8 |
| NVDA | 7（09-07 美國勞動節不開盤，曆法差異） |
| 8069 | 8 |
| **合計** | **63** |

實際：`daily_ml_features` 449,263→449,326，delta＝**63**。完全相符。

## 五、標籤算術核對

**`REPORTED, NOT INDEPENDENTLY VERIFIED`（PO 複核訊息本身標為 `VERIFIED THIS SESSION`，
本報告未重跑 before 側查詢獨立核對，只確認 after 側絕對值與 PO 的差值運算後回推一致）**：
PO 複核給出的差值——`target_triple_barrier`：`-1` +34、`+1` +22、NaN +7；`label_reason`：
NULL +56、`ambiguous_dual_barrier` +7、其餘 0。

Post-execution after 側絕對值（本報告 `VERIFIED THIS SESSION`，見
`FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success_postcheck.json`）：
`target_triple_barrier`：`-1` 226,990、`0` 21,199、`1` 162,310、NULL 38,827；
`label_reason`：NULL 410,499、`ambiguous_dual_barrier` 36,395、`insufficient_data` 1,892、
`no_entry` 540。

按 PO 給的差值回推：`-1`與`1`合計增量 34+22=56＝`label_reason` NULL 的增量 56（barrier
解出、`label_reason` 轉空）；`target_triple_barrier` NaN 的增量 +7＝`label_reason`
`ambiguous_dual_barrier` 的增量 +7（barrier 未解出、判定為雙邊模糊）。算術一致。
本報告未獨立重新查詢 before 側的四個絕對值去核對 PO 給的差值本身是否精確——187 列
逐列 before/after 已收錄在
`FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success_diff_table.json`，可由該檔逐列
加總重算獨立驗證。

## 六、真實庫寫入後狀態

| 表 | 執行前（PRE 備份） | 執行後（現況） | diff |
|---|---|---|---|
| stock_prices | 449,326 | 449,326 | 0（本次無 TWSE/TPEX 價格缺口，僅 NVDA 63 筆） |
| candidate_prices | 1,857,371 | 1,857,371 | 0 |
| market_articles | 1,340 | 1,346 | +6 |
| article_comments | 137,093 | 137,267 | +174 |
| **daily_ml_features** | **449,263** | **449,326** | **+63** |
| etl_run_log | 158 | 190 | +32 |
| sentiment_cache | 36 | 42 | +6 |
| theme_stock_mapping | 53 | 63 | +10 |
| 啟用關鍵字 | 28 | 31 | +3 |
| 未評分文章數 | 10 | 0 | -10 |

`etl_run_log` 今日新增 32 列：`ptt`（`NO_DATA` 24＋`OK` 7）=31、`tracked_stocks_daily`
`OK`（NVDA）=1，31+1=32 ✅ 算術核對通過。

## 七、POST 備份

`stock_prediction_system2_POST_first_daily_etl_20260917_2009.dump`（122,010,119 bytes），
存標準路徑，20:09 建立。

## 八、Log 密碼樣式檢查

`grep -iE "pass(word)?=" ／ "api[_-]?key|token=|secret"` 對執行 log 全文比對，
**無命中**（見附件 log 檔本身，已收錄未刪改）。

## 九、我沒有做的事

- 沒有為了配合預期數字調整任何驗收條件的計算方式（criterion 4 的 SQL 預期值先算好、
  執行後才核對，不是反推湊出來的）。
- 沒有在條件 2 判定上自行拍板——先如實列出字面不符之處送審查方複核，待 PO 親自訂正判準
  後才採用。
- 沒有在發現容器 `core.autocrlf` 缺口時自行更動設定，先報告等 PO 指示才執行。
- 沒有保留任何一個拋棄式容器（`sps_stageB_rehearsal`／`sps_stageC_pre_verify`／
  `sps_stageC_post_verify`／`sps_stageC_evidence`，全部驗證完即 `docker rm`，皆確認
  `postgres:18` image 與真實 app/db 容器未受影響）。

## 十、附件

- `FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success_log.txt`——本次執行完整
  stdout/stderr（已 grep 密碼樣式，無命中）。
- `FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success_postcheck.json`——連線目標、
  表列數 after、標籤/label_reason 計數 after、`etl_run_log` 今日彙總。
- `FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success_diff_table.json`——187 列
  逐列差異（`stock_id`／`trade_date`／變動欄 before/after）。

## 十一、PO 複核裁決（2026-09-17）與本輪處置

PO 複核通過，四條驗收條件全數 PASS（含條件 2 判準訂正後）。授權結案 commit，內容見
`PROJECT_STATUS.md`／`REMAINING_RISKS.md`／`TEAM_PLAYBOOK.md`／`DECISIONS.md` 對應章節
與本次 commit 訊息。§0.5 #31（Gemini 用量縮減）、#32（F 接線擴大）、雙時點排程、PTT
追補模式候補、`.gitattributes`（#26）維持登記，本 commit 不動它們，順序由 PO 另排。
