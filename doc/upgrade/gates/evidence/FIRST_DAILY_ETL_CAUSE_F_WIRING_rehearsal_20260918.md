# §0.5 #32 成因 F 接線——段 B 拋棄式庫演練報告

見 `doc/upgrade/gates/FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`。程式碼已於
RED／GREEN（`431c2be`／`ee0b384`）與審查方複核追加子案例（`9079915`）落地，本報告是
段 B 的拋棄式庫演練，驗證接線在**接近真實資料**的情況下行為正確，未動任何真實庫資料。

## 零、關鍵發現先講

兩項第一次跑就對得上（三方集合逐列相等，含 known-FAIL 突變全數被抓到的 RED/GREEN
基礎上），**一項發現需要揭露**：今天（2026-09-18）執行演練時，`previous_business_day()
=09-17`，但 `candidate_prices` 現有最新僅到 09-16，有 1 天不相干的價格缺口（§0.5 #30
機制）。為避免這個缺口在「整日執行」裡被真的補上、混淆「翻轉列只動 `source_status`
與社群八欄」的三方比對，**額外把批次取價／逐股管線也 mock 掉**，只讓 PTT 真的失敗＋
NLP／特徵階段照常對拋棄式 DB 執行——這超出了複核訊息原文列出的兩個 mock
（`run_ptt_board_pipeline`／`TrendDiscover`），見一之範圍揭露。這個 scope 決定使得
「今日所有可達股票列 `SOURCE_FAILED`」這句話在**原始**演練裡看不到具體效果（因為
`stock_prices` 沒有今天的列，`daily_ml_features` 的交易日曆自然不含今天）——已另外
用一筆**合成種子列**（非真實抓價，僅演練用）補上這個demonstration，見三。

## 一、還原與範圍揭露

- 還原自 `stock_prediction_system2_POST_first_daily_etl_20260917_2009.dump`（現有
  POST 備份，§0.5 #32 落地前的最後一次真實庫快照）。
- 拋棄式容器 `sps_causef_rehearsal`（postgres:18，`--network container:
  stock_prediction_system2_devcontainer-db-1`，`PGPORT=55440`，隨機密碼，
  `--memory=2g --cpus=0.5`）。
- 兩個獨立資料庫（`rehearsal_db`／`rehearsal_db2`），各自從同一份 POST dump 乾淨還原，
  供第一、二項各自使用（避免第一項的寫入污染第二項的 before 基準）。**還原後皆逐表
  核對列數與 POST 備份已知狀態相符**（`stock_prices`＝`daily_ml_features`＝449,326、
  `etl_run_log`＝190、`theme_stock_mapping`＝63 等，與結案 commit `a3cc612` 報告的
  POST 備份數字一致）。
- **範圍揭露**：今天執行有 1 天不相干的價格缺口（09-17，§0.5 #30 機制），與本案
  （§0.5 #32 PTT/NLP 成因 F）無關。第二項額外把 `run_price_batch`／
  `run_twse_pipeline_from_candidate_prices`／`run_tpex_pipeline_from_candidate_prices`／
  `run_us_stock_pipeline` 也 mock 掉，不觸網、不寫 `stock_prices`，避免這個缺口被
  順便補上、混淆比對範圍。複核訊息原文只列了兩個 mock（`run_ptt_board_pipeline`／
  `TrendDiscover`），這裡主動多 mock 兩組，理由已寫入演練腳本輸出並在此報告揭露，
  非擅自縮小驗證範圍。

## 二、第一項：只跑特徵階段，三方集合對照

**連線目標**：`current_database()=rehearsal_db`, `inet_server_port()=55440`。

1. **Python `fetch_failed_source_keys()`**（執行前，唯讀）：**47** 個
   `(stock_id, trade_date)`，09-07～09-14（不含 09-04），7 檔追蹤標的（NVDA 因
   09-07 美國勞動節少一天，同 §0.5 #30 機制）。
2. **SQL 對照**（提案 §3.3，含 §3.2a `eligible_stocks` 過濾）：同樣 **47** 個，
   逐列比對 `python_keys == sql_keys` → **`True`**。
3. **實際 before/after 翻轉**：`run_feature_engineering_pipeline()` 對拋棄式 DB
   真實執行（`FeatureAggregator` 未 mock），`daily_ml_features` 列數 449,326→449,326
   （key set 不變，純值翻轉）；翻轉列 **47**，逐列比對 `flipped_to_failed ==
   python_keys` → **`True`**；`flipped_to_failed == sql_keys` → **`True`**。三方
   集合逐列相等。
4. **驗收條件核對**：價格衍生 10 欄違規 **0**；`target_*`／`label_reason`
   違規 **0**（本次未跑尾端重算）；非社群欄／`source_status` 以外的欄位違規 **0**；
   47 筆翻轉為 `SOURCE_FAILED` 的列，`article_count` 為 `NULL` 違規（非 `NULL`）
   **0** 筆——`test_source_failed_nulls.py` 釘住的聚合器層行為，在接線之後對真實
   （拋棄式）資料重新驗證一次成立。

完整輸出見 `FIRST_DAILY_ETL_CAUSE_F_WIRING_rehearsal_item1_log.txt`。

## 三、第二項：強制 PTT 整日失敗

**連線目標**：`current_database()=rehearsal_db2`, `inet_server_port()=55440`。

- `run_ptt_board_pipeline` 改為直接拋 `PttSourceUnavailableError`；`trend_discover`
  stub 掉（0 次 Gemini 呼叫）；批次取價／逐股管線依一之揭露 mock 掉。
- `run_all_daily_tasks()` 對拋棄式 DB 真實執行：
  - `etl_run_log` 今日（09-18）新增 **31** 筆 `source='ptt'` 列，**全部**
    `outcome='FETCH_FAILED'`（31 個追蹤關鍵字，非 `FETCH_FAILED` 違規 **0**）——
    看板批次層級失敗、全部關鍵字受影響的既有行為（`main_etl_pipeline.py` 既有
    `except` 區塊）正確運作，本案未改動這段。
  - 特徵階段重算後，翻轉列 **47**，與第一項**完全相同的 47 個鍵**——這是預期
    結果：09-07～09-14 那批舊缺口原本就存在（不受今天執行影響），今天新產生的
    `FETCH_FAILED` 沒有對應的 `daily_ml_features` 列可標記（見零、關鍵發現）。
    價格衍生欄違規 **0**；非社群欄違規 **0**；`article_count` 非 `NULL` 違規 **0**。
  - 尾端掛點也照常對拋棄式 DB 執行（本案未 mock，未接線範圍外），2,754 列，
    `n_updated==len(tail)`，無 WARNING——證明 §0.5 #32 的接線與 §0.5 #30 的既有
    機制互不干擾。
  - 執行後 `fetch_failed_source_keys()` 重新查詢：47 個，`flipped_to_failed` 是其
    子集（`<=`）成立——與第一項的推導邏輯一致。

**【零之揭露延伸】合成種子列驗證「當日」效果**：另外在 `rehearsal_db2` 插入一筆
**合成** `stock_prices` 列（`('2330', '2026-09-18', ...)`，非真實抓價，明文標記僅
供本次演練驗證用），重跑特徵階段——`daily_ml_features` 新增
`('2330', '2026-09-18', source_status='SOURCE_FAILED', article_count=None)`
一列，**證實「當日所有可達股票列 `SOURCE_FAILED`」在有對應價格列時確實成立**，
補上原始演練因 mock 範圍而看不到的這一段效果。

完整輸出見 `FIRST_DAILY_ETL_CAUSE_F_WIRING_rehearsal_item2_log.txt`。

## 四、容器清理

`sps_causef_rehearsal` 已 `docker stop && docker rm`（只 rm，`postgres:18` image
與真實 `app`／`db` 容器確認未受影響）。

## 五、我沒有做的事

- 沒有對真實庫（`postgres`@`localhost:5432`）做任何寫入或修改。
- 沒有為了讓比對好做而放寬驗收條件（三方集合要求逐列相等，不是「大致相符」）。
- 額外多 mock 的兩組（批次取價／逐股管線）與合成種子列，皆在報告中明確揭露，
  不是悄悄縮小驗證範圍。

## 六、待 PO 裁決

段 B 兩項驗收皆通過（三方集合逐列相等、驗收條件全數 0 違規），「今日所有可達股票列
`SOURCE_FAILED`」的效果已用合成種子列補充驗證成立。段 C（真實庫，下一次真實每日
執行）的翻轉留待下一次真實執行時發生，需要 PO 另一輪 binding confirmation，屆時
`fetch_failed_source_keys()` 的預期翻轉列數以執行前重新查詢的即時結果為準（不沿用
本報告的 47，那是今天這個時間點的數字）。
