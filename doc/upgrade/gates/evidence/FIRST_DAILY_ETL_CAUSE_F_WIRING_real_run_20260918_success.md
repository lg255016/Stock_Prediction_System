# §0.5 #32 成因 F 接線——第二次真實每日 ETL 執行報告（成功）

見 `doc/upgrade/gates/FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`。程式碼已於
RED／GREEN（`431c2be`／`ee0b384`）、審查方複核追加子案例（`9079915`）、段 B 拋棄式庫
演練（`FIRST_DAILY_ETL_CAUSE_F_WIRING_rehearsal_20260918.md`）全數通過。本報告是
§0.5 #32 首次對真實庫生效的真實執行，同時也是本專案第二次真實每日 ETL（第一次見
`FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success.md`）。

## 零、關鍵發現先講

**執行成功，`exit code 0`，全程無例外，無 Gemini 429。** 2026-09-18 14:45 台北時間
開始，於新 PRE 備份（14:42 建立）的 30 分鐘窗內執行。§0.5 #32 的 `SOURCE_FAILED`
翻轉**第一次在真實庫發生**：47 列（與執行前 expectations 逐列相等）。

**兩項需要誠實揭露、但確認不構成任何驗收條件違規的觀察**：

1. **NVDA `stock_prices.volume`（09-16）在本次重新抓價時被更新**（96,079,300→
   96,563,600，`created_at` 不變，`ON CONFLICT DO UPDATE` 覆寫），連帶
   `volume_ratio_5d` 微幅變動、`label_reason` 從 `no_entry` 變為可解出標籤（因
   09-17 價格現在存在，尾端重算能力所及）。這是 NVDA 透過 yfinance 抓價的既有
   已知特性（該來源的近日成交量會隨時間被結算修正），不是本案新缺陷——驗收條件 1
   本來就刻意排除 NVDA（`stock_id != 'NVDA'`），這裡再次確認排除的理由成立。
2. **股票 `2382`（廣達）的 `bullishness_index` 在 13 個歷史交易日（02-05～08-31）
   同步微幅偏移**，`article_count`／`sentiment_mean` 等其餘欄位不變。

   **【訂正，PO 複核指出原始成因寫錯】** 原始報告誤寫成「2382 今天新增一筆映射、
   第一次套用」——這個說法本身自相矛盾：若是全新映射第一次套用，`article_count`
   應該從 0 變 1、`sentiment_mean` 應該從 NULL 變有值、`source_status` 應該從
   `SUCCESS_EMPTY` 變 `SUCCESS`，不會只有 `bullishness_index` 單獨動；而且同一批
   upsert 的 `2317`／`NVDA` 也有歷史列，卻一列沒變，與「新映射套用」的說法對不上。

   **真正成因（`VERIFIED THIS SESSION`，以 `pg_restore --data-only -t
   theme_stock_mapping` 直接讀 PRE 備份 `…_1442.dump` 的舊列，不需還原整個資料庫，
   比對真實庫現況）**：`AI伺服器→2382` 這條映射**已經存在**（`updated_at=
   2026-08-21`），今天的 AI 探索**重新 upsert 了同一條映射，把 `relevance_weight`
   從 1.00 改成 0.90**；`2317` 的權重本來就是 0.90，今天 upsert 後仍是 0.90（值
   沒變，只有 `updated_at` 被 bump）；`NVDA` 權重本來就是 1.00，今天仍是 1.00。

   | `theme_keyword` | `stock_id` | PRE 權重 | PRE `updated_at` | 執行後權重 |
   |---|---|---|---|---|
   | AI伺服器 | 2382 | **1.00** | 2026-08-21 | **0.90** |
   | AI伺服器 | 2317 | 0.90 | 2026-08-21 | 0.90 |
   | AI伺服器 | NVDA | 1.00 | 2026-08-21 | 1.00 |
   | AI伺服器 | AAPL | （無） | — | 0.80（新） |

   機制：`feature_aggregator.py` 題材溢出計算用 `weighted_pos/neg = is_pos/is_neg
   × relevance_weight`，`bullishness_index = ln((1+weighted_pos)/(1+weighted_neg))`。
   2382 某日若題材溢出來源恰有 1 篇正向文章、0 篇負向，權重 1.00 時
   `ln((1+1.00)/(1+0)) = ln(2) = 0.6931471805599453`；權重 0.90 時
   `ln((1+0.90)/(1+0)) = ln(1.9) = 0.6418538861723947`——**與 PRE／執行後的實際
   數字逐位相符**（見報告零之揭露 2 的原始比對輸出）。`article_count` 用
   `theme_count`（不乘權重）故不變；單篇文章的 `sentiment_mean` 與權重無關故不變；
   2317／NVDA 權重未變故一列不動——與觀察到的訊號完全吻合。

   判準核對：`updated_at` 有 bump（今天 upsert 一定會更新這個欄位，即使值沒變如
   2317／NVDA），落在驗收條件 2 判準 (a) 「`updated_at` 晚於上次成功特徵階段的
   映射所涉股票（全歷史）」——**PASS 的結論不變**，但成因是「既有映射的權重被
   探索重寫」，不是「全新映射第一次套用」；後者是 `RISK-032` 登記的機制，前者是
   同一份風險登記裡的另一個子機制（AI 探索會重寫既有映射的 `relevance_weight`，
   不只是新增映射），兩者都會造成全歷史欄位改變，但觸發條件不同，見
   `REMAINING_RISKS.md` RISK-032 補充段落。

## 一、執行時間軸（容器內 `now_taipei()`）

| 事件 | 台北時間 |
|---|---|
| 段 C 前置包完成、送 PO 綁定確認 | 2026-09-18 14:03 |
| PO 給第一次綁定確認（要求先重做 PRE，因超過 30 分鐘） | 2026-09-18（訊息時間） |
| 真實庫唯讀確認未變（`stock_prices`／`daily_ml_features` max 仍 09-16、PTT run log 仍 85 列） | 2026-09-18 14:40:58 |
| 新 PRE 備份建立 | 2026-09-18 14:42 |
| 新 PRE 還原拋棄式容器驗證通過，`docker rm` | 2026-09-18 14:4x |
| 執行前最終 DB 身分確認 | 2026-09-18 14:45:15 |
| 真實執行開始（`python main_etl_pipeline.py`） | ~14:45 |
| 執行完成（`exit code 0`） | ~14:50（POST 備份 14:50 建立） |

## 二、前置步驟（段 C 前置包 1～5，全部通過，`FIRST_DAILY_ETL_CAUSE_F_WIRING_expectations.json`）

1. Commit `9079915`，host／container 皆確認，`git status` 乾淨，hooksPath 正確。
2. **Expectations（執行前，唯讀）**：Python `fetch_failed_source_keys()` 與提案 §3.3
   的 SQL 對照，逐列相等，**47 個鍵**（09-07～09-14，7 檔追蹤標的，NVDA 因 09-07
   美國勞動節少一天）；`n_lag=0`（F=P=09-16，已同步）；價格缺口 1 天（09-17，
   批次請求預期 2 次）。
3. **PRE 備份**（第二次，因第一次超過 30 分鐘作廢）：
   `stock_prediction_system2_PRE_second_daily_etl_20260918_1442.dump`
   （122,010,119 bytes，與第一次同大小，確認真實庫期間未變）。還原拋棄式容器
   驗證 7 表與真實庫逐項相符，`docker rm`。
4. PTT 探測 200（第一次前置包時做過，本輪依 PO 指示未重做）。
5. 連線確認：`current_database()=postgres`、`inet_server_port()=5432`；
   `now_taipei=2026-09-18 14:45:15`，`today_taipei=09-18`，
   `previous_business_day=09-17`，`n_lag=0`。

## 三、執行內容（全部成功）

- **批次取價**：2 請求（TWSE／TPEx 各 1，09-17），皆 `OK`（TPEx 888 列、TWSE 1082
  列），與預期完全相符。
- **逐股階段**：8 檔追蹤標的（2454/2059/2330/3008/6488/2382/NVDA/8069）全數
  `OK`，`n_lag` 由 0 變為 **1**（F=09-16 舊值、P=09-17 新值，本次批次補齊後的
  必然結果）。
- **AI 熱門趨勢探索**：Gemini 呼叫 **1 次**，未撞限速或配額。發現 3 個新題材
  （營建營造、銅箔基板(CCL)、AI伺服器），11 筆題材成分股關聯寫入
  `theme_stock_mapping`（含 `AI伺服器→2382`，即零之揭露 2 的成因），0 個新關鍵字
  （3 個題材皆非全新，`tracking_keywords` 啟用數維持 31）。
- **PTT 看板**：31 個關鍵字，7 頁請求，11 筆命中，`OK 4／NO_DATA 27／
  FETCH_FAILED 0`。新增 1 篇文章、11 則留言。
- **NLP 情緒運算**：1 篇待處理，**Gemini 呼叫 0 次**（`sentiment_cache` 42→42
  不變，未經過 LLM 批次路徑，走 Hybrid 管線的簡單/規則路徑解出）。未評分文章數：
  0→0（全程維持 0）。
- **特徵工程**：股價 449,334 筆、文章 1,267 筆，449,334 列寫入 `daily_ml_features`
  （全量面板重算）。
- **尾端掛點重算**：`tail_window=6`（`TRIPLE_BARRIER_HOLDING_PERIOD(5)+n_lag(1)`），
  2,754 列更新（459 檔 × 6），`n_updated(2754)==len(tail)(2754)`，無 WARNING。

## 四、post-execution 五條驗收（PO 訂正判準後版本）

**以 14:42 執行前的新 PRE 備份還原為 before，真實庫現況為 after**（還原容器
`sps_stageC2_pre_verify2`／`sps_stageC2_post_verify` 皆已 `docker rm`，
`postgres:18` image 與真實 app/db 容器確認未受影響）。

### 1. 價格衍生 10 欄：F（09-16）以前、458 檔台股，逐列零差異——**PASS**

`close_price／volume／return_1d／rsi_14／volatility_5d／volatility_20d／
amplitude_ratio／ma5_bias_ratio／ma20_bias_ratio／volume_ratio_5d` 十欄逐欄核對，
全部 **0 差異**（NVDA 依既有慣例排除在本條範圍外，見零之揭露 1）。

### 2. 情緒／留言／`source_status` 欄——**PASS**

60 列有社群欄或 `source_status` 變動，全數落在判準內：
- **47 列**：§0.5 #32 本案推導集合（`fetch_failed_source_keys()`＝expectations
  逐列相等，見五）。
- **13 列**：股票 `2382`，`updated_at=2026-09-18 14:46:49` 的 `AI伺服器→2382`
  映射晚於上次成功特徵階段（09-17 20:04），落在判準 (a) 「映射所涉股票（全歷史）」
  款——見零之揭露 2。

集合外零列。

### 3. 標籤／目標欄：變動須落在各股尾端 `tail_window` 內——**PASS**

8 列（8 檔追蹤標的皆在 09-16 這天）只動 `target_next_close／target_return_1d／
target_up_down／label_reason`（`label_reason` 從 `no_entry` 解出具體標籤），全部
落在 `tail_window=6` 範圍內——09-17 價格現在存在，使 09-16（先前「還沒有下一天
價格可算」而標 `no_entry` 的邊界列）第一次能被解出。

### 4. `daily_ml_features` 新增列數——**PASS，精確吻合**

逐股 SQL（`trade_date > F` 的相異交易日數加總，F=09-16，執行後以真實
`stock_prices` 重新查詢）：8 檔各 1 天（NVDA 09-17 亦成功抓到，無曆法缺口）＝
**8**。實際 `daily_ml_features` 449,326→449,334，delta＝**8**。完全相符。

### 5. `source_status` 翻轉為 `SOURCE_FAILED` 的列集合＝expectations——**PASS**

執行後 `fetch_failed_source_keys()` 重新查詢：**47** 個鍵，與執行前 expectations
的 47 個鍵**逐列相等**（`current_keys == expected_keys` → `True`）。實際翻轉為
`SOURCE_FAILED` 的列：**47**，與此集合**逐列相等**，集合外 **0** 列。翻轉列
`article_count` 為非 `NULL` 違規：**0** 筆。

## 五、Gemini 呼叫核對

本次執行 Gemini 呼叫總計 **1 次**（AI 探索），NLP 階段 0 次（`sentiment_cache`
不變，1 篇待評分文章走 Hybrid 管線的非 LLM 路徑）。PTT 探測前已確認 200，全程未撞
限速或配額。

## 六、標籤算術核對

`target_triple_barrier`／`label_reason` 的算術本次未做逐值統計表（尾端影響列數
2,754＝459×6 已於三之尾端掛點段落核對；八列 09-16 邊界解出屬於「原本 `no_entry`
→現在有值」，NaN／None 減少 8、對應 `label_reason` NULL 增加 8，算術自洽）。

## 七、真實庫寫入後狀態

| 表 | 執行前（新 PRE 備份） | 執行後（現況） | diff |
|---|---|---|---|
| stock_prices | 449,326 | 449,334 | +8 |
| candidate_prices | 1,857,371 | 1,859,341 | +1,970 |
| market_articles | 1,346 | 1,347 | +1 |
| article_comments | 137,267 | 137,278 | +11 |
| **daily_ml_features** | **449,326** | **449,334** | **+8** |
| etl_run_log | 190 | 231 | +41 |
| sentiment_cache | 42 | 42 | 0 |
| theme_stock_mapping | 63 | 66 | +3（僅 3 檔新增，因部分關聯的股票已存在於既有題材，見三） |
| 啟用關鍵字 | 31 | 31 | 0 |
| 未評分文章數 | 0 | 0 | 0（全程維持） |

`etl_run_log` 新增 41 列：`twse_mi_index` 1、`tpex_daily_quotes` 1、
`tracked_stocks_daily` 8、`ptt`（`OK` 4＋`NO_DATA` 27）31，1+1+8+31=41 ✅ 算術
核對通過。

## 八、POST 備份

`stock_prediction_system2_POST_second_daily_etl_20260918_1450.dump`
（122,100,599 bytes），存標準路徑，14:50 建立。

## 九、Log 密碼樣式檢查

`grep -iE "pass(word)?=" ／ "api[_-]?key|token=|secret"` 對執行 log 與 postcheck
輸出全文比對，**無命中**。

## 十、順帶發現（不屬本案驗收範圍，登記即可，PO 複核追加）

1. **`market_articles` 有 35 篇 `post_time` 在未來**（`VERIFIED THIS SESSION`，
   `SELECT COUNT(*) FROM market_articles WHERE post_time > NOW();`，範圍
   09-18 11:23～12-29 12:00；PO 複核當時查得 33 篇，本次重查為 35 篇，差異可能
   來自查詢時點或邊界定義微差，以本次重新查得的數字為準）。逐關鍵字：電子紙 8、
   CoWoS 7、環球晶 6、矽光子 5、AI伺服器 4、散熱模組 2、光學鏡頭 1、記憶體 1、
   川湖 1。這些是舊資料的年份推斷結果，現行 `parse_ptt_post_time()` 已改用網址
   時間戳推年份，但這批文章沒被回修。目前因超出交易日曆被特徵層丟棄（不影響
   本次驗收），等日期到了會被算進錯的年份。**§0.5 登記候補**：用網址時間戳重算
   這批文章的 `post_time`（真實庫寫入，需獨立小案，走 `bug-fix-protocol`）。
2. **`etl_run_log` 的 PTT 批次現在有 09-05、09-17、09-18 三天**。今天之後若連續
   幾天 PTT 成功，**09-07～09-14 那 47 列不會自動回復**——它們的日期永遠不會落進
   任何新批次的 `[B-2, B]` 視窗。這是設計如此（那幾天確實沒有可信觀測，見 Gate A
   提案 §3.2「沒跑等於未覆蓋」），寫在這裡供日後查閱者參考，避免被誤認為是 bug。

## 十一、我沒有做的事

- 沒有為了讓「零之揭露」兩項觀察消失而調整驗收條件範圍——先如實查出成因
  （NVDA 既有已知特性、2382 是既有映射權重被探索重寫的既有機制子項），確認落在
  既有判準內才寫 PASS，不是先射箭再畫靶。
- 2382 成因原始報告寫錯（誤判為「全新映射第一次套用」），經 PO 複核指出自相
  矛盾處後，以 `pg_restore --data-only` 直接讀 PRE 備份的權重舊值重新查證訂正，
  未略過或淡化這個錯誤。
- 沒有保留任何拋棄式容器（`sps_stageC2_pre_verify`／`sps_stageC2_pre_verify2`／
  `sps_stageC2_post_verify`，全部驗證完即 `docker rm`，`postgres:18` image 與
  真實 app/db 容器確認未受影響）。
- 沒有在段 C 前置包已過 30 分鐘時逕行執行——依 PO 條件先重做 PRE、確認真實庫
  未變，才在新窗口內執行。

## 十二、PO 複核裁決（2026-09-18）與結案

五條驗收全數 PASS（2382 成因已訂正，PASS 結論不受影響）。PO 已授權結案 commit，
內容：
- `PROJECT_STATUS.md` §0.5 #32 改 CLOSED（`431c2be`／`ee0b384`／`9079915`，執行
  2026-09-18 14:4x，PRE `…_1442`、POST `…_1450`）；#31 維持登記；新增兩條候補
  （探索權重重寫全歷史效應、35 篇未來日期文章年份回修）；§0.2 加「第二次每日
  ETL 已完成」一列。
- 新 ADR `DEC-042`（失敗鍵推導規則，依 Gate A 提案 §8）。
- `REMAINING_RISKS.md` RISK-015 加註（覆蓋率量測可區分 `SOURCE_FAILED`）；
  RISK-032 補充段落（AI 探索重寫既有映射權重、非僅新增映射，也會觸發全歷史欄位
  改變——本次 2382 案例的真正成因）。
- Gate A 提案 `git mv` 至 `gates/closed/`；`doc/README.md` 查無需要同步的清單。
