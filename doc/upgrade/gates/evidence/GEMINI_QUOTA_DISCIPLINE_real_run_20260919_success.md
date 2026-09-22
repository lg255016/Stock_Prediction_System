# §0.5 #31＋#33 段 C：第三次真實每日 ETL 執行報告

- 日期：2026-09-19 00:26（台北時間，執行開始）
- 依據：`GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md` §7；PO 綁定確認（「#31＋#33
  段C第6步：綁定確認（附時間條件）」訊息）
- 對應 commit：`7861d14`（段 B 前最後一個 commit，本次未再新增 commit，
  執行本身不改動程式碼）
- 原始輸出：`GEMINI_QUOTA_DISCIPLINE_real_run_20260919_log.txt`、
  `GEMINI_QUOTA_DISCIPLINE_real_run_20260919_postcheck.txt`（同目錄）

## 一、RISK-013 協議執行紀錄

PO 綁定確認附帶時間條件：原 23:05 PRE 備份已超過 30 分鐘，要求重做。

1. **新 PRE 備份**：`stock_prediction_system2_PRE_third_daily_etl_20260919_0020.dump`
   （00:20 建立，122,100,599 bytes，與舊 PRE 同大小——真實庫兩次備份間未變）。
2. **還原驗證**：拋棄式容器 `pre_verify_third_daily_v2`（`postgres:18`，
   `PGPORT=55504`），`pg_restore --clean --if-exists` exit 0；核對
   `MAX(run_id)=236`、`theme_stock_mapping=66`、`daily_ml_features=449334`、
   `candidate_prices` twse/tpex 皆 `2026-09-17`——與真實庫執行前現況完全一致，
   確認**真實庫在兩次 PRE 之間未變**。已 `docker rm`。
3. **綁定確認**：執行腳本內建 `assert binding == ("postgres", 5432)`，
   執行前另印 `current_database()`／`inet_server_port()`，log 第 14 行確認
   `postgres`／`5432`。
4. **執行**：`ETLPipelineManager().run_all_daily_tasks()`，00:26 開始，
   **恰好一次**，exit 0，未拋例外。
5. **驗證**：見下方 §三（五條）與 §四（第 6、7 條）。
6. **POST 備份**：`stock_prediction_system2_POST_third_daily_etl_20260919_0046.dump`
   （00:46 建立，122,217,707 bytes）。

## 零、關鍵發現（PO 複核第四輪追加，非本案驗收範圍但需登記）

### 0.1 NVDA 09-18 K 棒是美股盤中快照，非收盤資料

本次 00:26 台北時間執行＝美東 09-18 12:26，美股當日**仍在交易中**。
`run_us_stock_pipeline` 以 `period="3mo"` 呼叫 yfinance，該參數會把「進行中
的當日 K 棒」一併回傳，於是真實庫寫入了盤中快照：

| `trade_date` | `close_price` | `volume` | `created_at`（UTC） |
|---|---|---|---|
| 09-17 | 219.34 | 93,960,500 | 09-18 06:46 |
| **09-18** | **219.31** | **54,734,472** | **09-18 16:26** |

`VERIFIED THIS SESSION`（獨立重跑同一條 SQL 查證，數字與 PO 複核完全一致）：
成交量僅平常六成，收盤價是台北 00:26（美東中午）當下的即時價，不是真正
收盤價。這一列會在下一次執行時被 `period="3mo"` 重新抓取覆蓋，NVDA 09-18
的特徵列與尾端標籤（目前 `label_reason=no_entry`）屆時也會一併重算——會
自我修正，不需要人工介入。驗收條件 1 本來就排除 NVDA，本次五條 PASS 不受
此影響。

這是**深夜執行的固有副作用**：之前 09-17（15:35）與 09-18（20:04）的執行
都在美股收盤後，未曾撞到這個情況；本次是探索頻率縮減後、系統首次在美股
交易時段內真實執行，第一次讓這個既有行為現形。已登記 §0.5 候補 #35（見
`PROJECT_STATUS.md`），與 08:30 雙時點案一併評估——08:30 台北時間抓的是
完整的前一美股交易日，不受此影響。是否繼續允許深夜執行由 PO 另決。

### 0.2 `trend_discover` 未重試 `DeadlineExceeded` 的根本原因

`Gemini 合計呼叫 1 次`（§五）不是巧合，是 `TrendDiscover._is_transient_
exception()` 的關鍵字清單（`429／quota／rate limit／resourceexhausted／
503／timeout`）**不含 `504` 也不含 `deadline`**（`VERIFIED THIS SESSION`，
`src/extractors/trend_discover.py:73`）——`"deadlineexceeded: 504 deadline
expired..."` 小寫化後仍不命中任何關鍵字，`_is_transient_exception` 回
`False`，於是第一次呼叫失敗就直接向上拋出，未進退避重試迴圈，log 裡因此
沒有任何重試警告。`nlp_processor.py` 的清單（`src/transform/nlp_processor.
py:112-115`）含 `deadline`、`timeout`，但同樣**不含 `504`**。

兩份清單本來就不一致（`trend_discover` 是六項舊清單，`nlp_processor` 後來
加了 `deadline`／`unavailable`／`connection error` 但兩邊都漏了 `504`），
本案不改（範圍外），已登記 §0.5 候補 #36：統一兩個 Gemini 呼叫器的暫態
判斷關鍵字清單，並考慮抽成共用實作——改了會影響「504 算不算暫態、要不要
重試」，而每次重試都算一次配額用量，需要獨立評估，不宜順手改。

## 二、執行前狀態（真實庫，00:26）

| 項目 | 值 |
|---|---|
| `today_taipei()` | `2026-09-19` |
| `previous_business_day()` | `2026-09-18` |
| `fetch_feature_lag()` | `feature_max_date=09-17`, `price_max_date=09-17`, `n_lag=0` |
| `fetch_last_discovery_probed_date()` | `None`（符合預期，觸發真實探索） |
| `fetch_failed_source_keys()` | 47 個鍵 |

## 三、標準五條驗收（沿用 §0.5 #32 判準，`before`＝新 PRE 備份還原、`after`＝真實庫現況）

### 1. 價格衍生 10 欄：F（09-17）以前逐列零差異——**PASS**

`close_price／volume／return_1d／rsi_14／volatility_5d／volatility_20d／
amplitude_ratio／ma5_bias_ratio／ma20_bias_ratio／volume_ratio_5d` 十欄，
共同列（PRE 與 POST 皆存在的 449,334 筆）中 F 以前逐欄核對，**0 筆差異**。

### 2. 情緒／留言／`source_status` 欄——**PASS**

共同列中情緒／`source_status` 欄**0 筆變動**（與 §0.5 #32 執行時 60 筆變動
形成鮮明對比——那次是既有映射被改權重／新增映射觸發 DEC-039 全歷史重算；
本次因 `upsert_theme_stock_mapping()` 已改 `DO NOTHING` 且探索本身因
`DeadlineExceeded` 未能發現任何新配對，**沒有任何映射變動，全歷史重算機制
這次沒有東西可重算**）。超出 47 鍵集合外的變動：0 筆。

### 3. 標籤／目標欄：變動須落在各股尾端 `tail_window` 內——**PASS**

共同列中 16 筆標籤欄變動（`n_lag=1`，`tail_window=holding_period(5)+1=6`），
逐股核對尾端 window 範圍，**0 筆超出**。

### 4. `daily_ml_features` 新增列數——**PASS，精確吻合**

逐股核對：8 檔追蹤標的各新增 1 筆（`trade_date=2026-09-18`）＝**8**。
實際 `daily_ml_features` 449,334→449,342，delta＝**8**。完全相符。

### 5. `source_status` 翻轉為 `SOURCE_FAILED` 的列集合＝expectations——**PASS**

執行後 `fetch_failed_source_keys()` 重新查詢：**47** 個鍵，與執行前
expectations 的 47 個鍵**逐列相等**。實際翻轉為 `SOURCE_FAILED` 的列：
**0** 筆（本次沒有新增 PTT 覆蓋缺口或 NLP 未評分文章對應到追蹤股票——
PTT 今日全部成功，NLP 僅 2 篇待評分且皆非 LLM 路徑成功評分，見下）。
翻轉列 `article_count` 非 `NULL` 違規：**0** 筆。

## 四、§0.5 #31＋#33 本案新增驗收項

### 6. `etl_run_log` 探索列——**PASS（PO 裁決，判準訂正）**

PO 訂正後判準：「`ai_discovery` 恰一列，`outcome` 為四態之一且與 log 中的
實際事件一致；`FETCH_FAILED`／`REFUSED` 附 `detail`」（原措辭「`OK` 或
`NO_DATA`」只想到兩種結果，四態設計本來就有四種，PO 認定是判準本身寫窄，
不是實作或執行有問題）。**實際結果**：

```
run_id=247, batch_key=2026-09-19, item_key=discovery,
outcome=FETCH_FAILED, detail="DeadlineExceeded: 504 Deadline expired
before operation could complete."
```

`FETCH_FAILED` 附 `detail`，與 log 中的實際事件（探索呼叫 Gemini 時撞到
504 逾時）一致——符合訂正後判準。`nlp_gemini` 列：**0 筆**（NLP 階段撈到
2 篇待評分文章，皆非 SnowNLP 模糊區間，全程未呼叫 `generate_content`，
見 §五），符合「只在真的撞配額時出現」。

`FETCH_FAILED` 正是 v3 §3.1 四態設計裡「Gemini 回應無效或萃取失敗」那一
格該有的分類，且是複核第二輪找到的「五個靜默 return」那個 bug 修好後的
直接證據：**若是舊碼，這個 `DeadlineExceeded` 會被既有的 `except
Exception` 生吞，呼叫端只看到隱式 `None`，本次執行極可能直接
`TypeError` 中止。新碼下，它被正確分類、正確落地、流程正常繼續完成
全部後續階段——正是本案要證明的行為。** `FETCH_FAILED` 不算「有問過」
（§3.1 判準只認 `OK`／`NO_DATA`），下次執行會再探索一次，這是設計內的
結果，`expectations.json` 依此撰寫。撞到 504 逾時而非每日配額 `REFUSED`
是本次真實環境的偶然，不影響本條的 PASS 判定；`REFUSED` 路徑仍待未來某次
真實撞到配額時驗證。

### 7. 既有映射列 `updated_at` 最大值不變、權重零變動、新配對只准新增——**PASS**

`theme_stock_mapping` 執行前後**完全相等**（含 `updated_at`，66 列逐列
`==`，`PRE == POST` 為 `True`）。無新配對（探索本身因 `DeadlineExceeded`
未能產出任何 `trends` 資料，`insert_discovered_keywords`／
`upsert_theme_stock_mapping` 皆未被呼叫）。

## 五、Gemini／PTT 呼叫核對

| 呼叫 | 次數 | 結果 |
|---|---|---|
| 探索（`trend_discover.run_discovery` 內的 `generate_content`） | 1 | `DeadlineExceeded`（504），已分類為 `FETCH_FAILED` |
| NLP（`nlp_processor.process_batch_hybrid` 內的 `generate_content`） | 0 | 2 篇待評分文章皆非 SnowNLP 模糊區間（0.4～0.6），純 SnowNLP 路徑完成，未觸發 LLM 呼叫 |
| **合計 Gemini 呼叫** | **1** | 落在提案 §7 預期「合計 ≤ 3」內 |
| PTT 看板批次 | 1（7 頁請求） | `OK`，12 筆命中，4 個關鍵字 `OK`／27 個 `NO_DATA`（合計 31，`assert_complete` 通過） |

PTT 執行前已探測 200（見前置包步驟 4），本次執行未撞限速或配額。

## 六、真實庫寫入後狀態

| 表／量 | 執行前（新 PRE 備份還原） | 執行後（現況） | diff |
|---|---|---|---|
| `daily_ml_features` | 449,334 | 449,342 | +8 |
| `etl_run_log`（`MAX(run_id)`） | 236 | 278 | +42 |
| `theme_stock_mapping` | 66 | 66 | 0 |
| `market_articles`（未評分數） | 0 | 0 | 0（全程維持） |
| `fetch_failed_source_keys()` 筆數 | 47 | 47 | 0 |

`etl_run_log` 新增 42 列算術核對：`twse_mi_index` 1＋`tpex_daily_quotes` 1＋
`tracked_stocks_daily` 8＋`ai_discovery` 1＋`ptt`（`OK` 4＋`NO_DATA` 27）31
＝42 ✅。

## 七、清理

演練與驗證用拋棄式容器（`pre_verify_third_daily_v2`、
`post_compare_third_daily`）皆已 `docker stop && docker rm`；
`docker images` 內 postgres 相關映像數量演練前後不變（3 個），確認**未執行
`docker rmi`**。

## 八、Log 密碼樣式檢查

`grep -iE "pass(word)?="` 對執行 log 與 postcheck 輸出全文比對，**無命中**。

## 九、與提案 §7 預期的對照

| 提案 §7 預期 | 實際結果 |
|---|---|
| 探索 1 次（真實呼叫，因 `last_probed=None`） | ✅ 1 次，結果 `FETCH_FAILED`（非預期文字列出的 `OK`／`NO_DATA`，但屬設計內四態之一） |
| NLP 依新文章 0～2 次，合計 ≤ 3 | ✅ NLP 0 次＋探索 1 次＝合計 1，在上限內 |
| 撞每日配額走新機制記 `REFUSED` 並繼續 | 本次**未撞到配額**，撞到的是逾時（`FETCH_FAILED`）——同一份四態設計的另一分支，行為邏輯已在此次真實驗證，`REFUSED` 路徑仍待未來驗證 |
| `ai_discovery` 恰 1 列（`OK`/`NO_DATA`），`nlp_gemini` 除非撞配額否則不出現 | `ai_discovery` 恰 1 列，`FETCH_FAILED` 附 `detail`（PO 訂正判準後 PASS，見 §四.6）；`nlp_gemini` 0 列，符合 |
| `theme_stock_mapping` 既有列 `updated_at` 不變、零變動 | ✅ 完全吻合 |

## 十、結論

七條驗收（標準五條＋本案新增的條件 6、7）**全數 PASS**（條件 6 依 PO
訂正判準後裁決 PASS，見 §四.6）。整體執行 exit 0，未拋任何例外，
`RISK-013` 協議（新 PRE→還原驗證→執行→驗證→POST）完整走完。

附帶兩項關鍵發現已登記於 §零：NVDA 09-18 盤中快照（候補 #35）、
`trend_discover` 暫態判斷清單缺 `504`／`deadline`（候補 #36）。

**已獲 PO 授權結案 commit。**
