# §0.5 #31＋#33 段 B（拋棄式庫演練）報告

- 日期：2026-09-18
- 依據：`GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md` §6；PO 複核授權（「三、段 B 授權」與
  複核第三輪「二、範圍決定」「四、段 C 前置包」訊息）
- 對應 commit：`9536771`（GREEN）、`7861d14`（3b 補測）
- 原始輸出：`GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918_log.txt`（場景 1／2a／2b／2c／3）、
  `GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918_scenario1b_log.txt`（場景 1b，同目錄）

## 一、還原來源與拋棄式容器

- 備份檔：`D:\Python\Database_Backups\Stock_Prediction_System2\stock_prediction_system2_POST_second_daily_etl_20260918_1450.dump`
- 拋棄式容器（場景 1／2a／2b／2c／3）：`gemquota_rehearsal_db`（`postgres:18`，
  與真實庫容器 `stock_prediction_system2_devcontainer-db-1` 共用 network
  namespace，`PGPORT=55501`，隨機密碼，`database=gemquota_rehearsal`，
  `--memory=2g --cpus=0.5`）
- 拋棄式容器（場景 1b，獨立第二個容器）：`gemquota_rehearsal_db2`（同規格，
  `PGPORT=55502`，`database=gemquota_rehearsal2`）
- `pg_restore --no-owner --no-privileges --clean --if-exists`，兩次皆 exit 0
- 綁定確認：每個場景開始前都執行 `SELECT current_database(), inet_server_port();`，
  五＋一次全部回傳對應的拋棄式庫名稱／連接埠（見兩份 log 逐段 `[BINDING]` 行），
  未曾誤連真實庫

## 二、範圍決策（誠實揭露）

場景 1／2a／2b／2c／3 **不呼叫完整 `run_all_daily_tasks()`**，改為直接呼叫
被測方法本身（`run_nlp_sentiment_pipeline()`／`run_discovery()`／
`fetch_last_discovery_probed_date()`／`upsert_theme_stock_mapping()`），理由：
`run_all_daily_tasks()` 一次執行會同時觸發 PTT／TWSE／TPEX／yfinance 的真實
外部服務呼叫，那些路徑與本案（Gemini 用量紀律）本身無關。`db_writer`／
`run_log_writer` 全程指向拋棄式庫、未被 mock，因此每個被測方法與資料庫的
實際互動（SQL 查詢、寫入、CHECK 約束）都是真實執行，只有 Gemini 呼叫本身
（`model.generate_content`／`_fetch_recent_hot_titles`）與 PTT 掃頁失敗被 mock。

**複核第三輪指出**：方法層演練驗證不到「呼叫端接線」本身——探索閘門那段
邏輯、`run_log_writer`／`started_at`／`tracked_batch_key` 傳進 NLP 管線那一行，
只有單元測試用 mock 走過，沒對真實（拋棄式）庫跑過。**場景 1b** 因此補上，
比照 §0.5 #32 段 B 第 2 項配方：把批次取價／逐股／`run_us_stock_pipeline`／
`run_ptt_board_pipeline` 全部 mock 掉，讓探索與 NLP 對拋棄式庫真跑**完整
`run_all_daily_tasks()`**，見 §三.6。

真實庫在第二次每日 ETL（09-18）執行當時，`etl_run_log` 尚無 `ai_discovery`
來源的列（本 SB 尚未接線）——場景 2a 因此需要合成插入一列 `OK`／`batch_key=
今天` 才能演練「距上次有問過不足 7 天」的情況，見下方逐場景說明。

## 三、逐場景結果

### 場景 1：NLP 撞每日配額，整日執行

**合成操作（報告揭露）**：把對映到追蹤股票 2330 關鍵字（`台積電`）的 5 篇
文章 `sentiment_score` 設回 `NULL`（`article_id`：1504／1505／1510／1512／1518）。

**mock**：`nlp_processor.model.generate_content` 拋出含 `PerDay` 的原始例外
（09-17 log 404-426 原文精簡版，含 `quota_id: "GenerateRequestsPerDayPer
ProjectPerModel-FreeTier"`）。

**結果**（`VERIFIED THIS SESSION`）：

| 驗收項 | 結果 |
|---|---|
| `generate_content` 呼叫次數 | 1（不重試） |
| `etl_run_log` | 1 列 `nlp_gemini／daily_quota／REFUSED`，`detail` 含「剩餘 5 篇未評分」 |
| 特徵階段 | 完成，未拋例外 |
| 5 篇文章映射到的交易日 | `2026-09-01`～`2026-09-04`（4 個相異日期，其中 2 篇roll-forward 到同一日） |
| 這些日期是否都在 `fetch_failed_source_keys()` 的 2330 集合裡 | **True**（獨立查詢覆核） |
| `daily_ml_features` 這 4 個 (2330, date) 列的 `source_status`／`sentiment_mean` | 全部 `SOURCE_FAILED`／`NULL`（獨立查詢覆核，直接讀寫入後的資料表，非僅信賴中間集合） |
| exit | 0 |

### 場景 2a：距上次「有問過」不足 7 天 → 跳過

**合成操作（報告揭露，見 §二 說明）**：插入一列
`source='ai_discovery', item_key='discovery', outcome='OK', batch_key='2026-09-18'`。

**結果**：`fetch_last_discovery_probed_date() = 2026-09-18`，
`should_run_discovery = False`；`run_discovery()` 未被呼叫（`assert_not_called`
通過）；`ai_discovery` 列數維持 1（僅合成的那列），無新增列——符合 A4。

### 場景 2b：把該 OK 列的 `batch_key` 改到 8 天前 → 執行，掃頁失敗

**合成操作**：`UPDATE etl_run_log SET batch_key='2026-09-10' WHERE
source='ai_discovery' AND outcome='OK'`。

**mock**：`_fetch_recent_hot_titles` 回傳 `None`（模擬掃頁出錯）。

**結果**：`fetch_last_discovery_probed_date() = 2026-09-10`，
`should_run_discovery = True`；`run_discovery()` 回傳
`("FETCH_FAILED", "PTT 熱門標題擷取失敗（掃頁時發生錯誤）")`；`etl_run_log`
新增 1 列 `ai_discovery／discovery／FETCH_FAILED`，`detail` 非空。

### 場景 2c：Gemini 回應有效但無新詞 → NO_DATA

**結果**：`fetch_last_discovery_probed_date()` 仍為 `2026-09-10`（`FETCH_FAILED`
不算「有問過」，未被 2b 的結果更新，符合設計）；`should_run_discovery = True`；
mock `generate_content` 回傳 `{"trends": []}`；`run_discovery()` 回傳
`("NO_DATA", None)`；`etl_run_log` 新增 1 列 `ai_discovery／discovery／NO_DATA`，
`detail` 為 `None`（符合 `chk_etl_run_log_detail`）。

### 場景 3：既有映射不被探索結果覆寫

**合成操作**：把既有映射 `AI伺服器／2382`（restore 時 `relevance_weight=0.90`）
改成 `0.50`。

**mock 輸入**：`upsert_theme_stock_mapping([("AI伺服器", "2382", "廣達", 0.90)])`
（模擬探索重新發現同一配對，回傳權重 0.90）。

**結果**：`relevance_weight` 與 `updated_at` 皆與改動後（0.50、原時間戳）
完全一致——`DO NOTHING` 確實生效，既有列未被覆寫。

### 場景 1b：整條 `run_all_daily_tasks()` 對拋棄式庫真跑（複核第三輪追加）

**前置**：`fetch_last_discovery_probed_date()` 事前值確認為 `None`
（真實情況的忠實重現，見 §二說明）。

**合成操作（報告揭露）**：本檔還原後全庫 0 篇未評分文章，挑 1 篇
（`article_id=15`）`sentiment_score` 設回 `NULL`，供 NLP 撞配額情境使用。

**mock 範圍**：`run_price_batch`／`run_us_stock_pipeline`／
`run_twse_pipeline_from_candidate_prices`／`run_tpex_pipeline_from_
candidate_prices`／`run_ptt_board_pipeline`（回全 `OK`）；
`trend_discover._fetch_recent_hot_titles`（回固定標題，不真的爬 PTT）；
`trend_discover.model.generate_content`（回 `{"trends": []}`）；
`nlp_processor.model.generate_content`（拋含 `PerDay` 的原始例外）；
`nlp_processor._calc_snownlp`（強制回傳落入模糊區間的 0.5，確保該篇合成
文章必進 LLM 路徑，見下方「過程中的兩個修正」）。**未 mock**：
`db_writer`、`run_log_writer`（`EtlRunLogWriter` 指向拋棄式庫）、
`feature_aggregator`（真實 `FeatureAggregator`）、探索閘門判準、
`run_nlp_sentiment_pipeline()` 的參數傳遞、特徵工程與尾端重算階段。

**結果**（`VERIFIED THIS SESSION`）：

| 驗收項 | 結果 |
|---|---|
| `etl_run_log`（`ai_discovery`） | 恰 1 列，`batch_key=2026-09-18`，`outcome=NO_DATA`，`detail=None` |
| `etl_run_log`（`nlp_gemini`） | 恰 1 列，`batch_key=2026-09-18`，`outcome=REFUSED`，`detail` 含「剩餘 1 篇未評分」與 `quota_id` |
| `today_taipei().isoformat()` | `2026-09-18`，與上述兩列 `batch_key` 完全一致——**證明 `run_all_daily_tasks()` 傳給 `run_nlp_sentiment_pipeline()` 與探索寫入用的都是同一個 `tracked_batch_key`，不是各自獨立推導** |
| `generate_content` 呼叫次數（探索／NLP） | 1／1（皆不重試） |
| 特徵階段 | 完成，`daily_ml_features` 449,334 列（與還原時股價列數量級一致） |
| 尾端重算 | 完成，2,754 列（「實際影響列數＝預期列數」自我一致） |
| exit | 0（未拋例外） |

**過程中的兩個修正（誠實揭露，均已在最終版本套用並重跑到通過）**：

1. 第一次執行時 `_fetch_recent_hot_titles` 誤用 `TrendDiscover.__new__()`
   繞過 `__init__`，導致真的嘗試對 PTT 發真實 HTTP 請求並因缺 `base_url`
   屬性而 `AttributeError`——改為直接 mock 掉該方法，不讓任何真實網路請求
   發生。
2. 第一次修正後改用 `MagicMock(return_value=0.5)` 取代 `_calc_snownlp`，
   但 pandas 的 `Series.apply()` 對單列資料搭配 `MagicMock` 會誤判成
   dict-like 呼叫，拋 `ValueError: No objects to concatenate`——改用一般
   `lambda text: 0.5` 後正常運作。

## 四、零真實 Gemini 呼叫確認

全程僅 `nlp_processor.model` 與 `trend_discover.model`／
`_fetch_recent_hot_titles` 被 mock（`unittest.mock.MagicMock`），未執行任何
對 Google API 的真實網路請求；`GEMINI_API_KEY` 亦未在演練程序中被讀取或使用。

## 五、清理

`docker stop gemquota_rehearsal_db && docker rm gemquota_rehearsal_db`，
`docker stop gemquota_rehearsal_db2 && docker rm gemquota_rehearsal_db2`，
兩次皆 exit 0；`docker images` 內 postgres 相關映像數量演練前後不變（3 個），
確認**未執行 `docker rmi`**（`CLAUDE.md` §11A、`TEAM_PLAYBOOK.md` A14）。

## 六、證據標籤

| 宣稱 | 標籤 | 重跑方式 |
|---|---|---|
| 5 篇文章映射日期均落在 `fetch_failed_source_keys()` 的 2330 集合 | `VERIFIED THIS SESSION` | 見 `GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918_log.txt` 之後的獨立查詢（未存入 log 檔，指令已列於本報告場景 1 表格上方之驗證流程，可用相同拋棄式庫還原後重跑） |
| `daily_ml_features` 對應列 `source_status=SOURCE_FAILED` | `VERIFIED THIS SESSION` | 同上，直接 `SELECT` 該 4 列 |
| 五個場景（1／2a／2b／2c／3）的綁定確認、outcome／detail 結果 | `VERIFIED THIS SESSION` | `GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918_log.txt` 逐行可查 |
| 場景 1b 的綁定確認、`etl_run_log` 兩列、`batch_key` 一致性、特徵／尾端階段完成 | `VERIFIED THIS SESSION` | `GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918_scenario1b_log.txt` 逐行可查 |
| 零真實 Gemini／PTT 呼叫 | `VERIFIED THIS SESSION` | 演練程式碼本身可查（`gemquota_rehearsal.py`／`gemquota_rehearsal_1b.py`，僅存於本次會話 scratchpad，未提交版控——演練用腳本，非交付物） |
| 兩份 log 皆已 `grep -iE "pass(word)?="` 覆核零命中 | `VERIFIED THIS SESSION` | 同一指令對兩份 log 檔重跑 |

## 七、已由 PO 裁決事項（曾為待複核，本輪已定案）

- 段 C（下一次真實每日 ETL）前，真實庫目前仍無 `ai_discovery` 列，
  `fetch_last_discovery_probed_date()` 第一次真實執行時會是 `None`，
  **依設計就是要探索一次**——PO 已裁決這是判準正確運作的結果，**不得**為了
  讓舊預期成立而在真實庫預先插入合成列。`GEMINI_QUOTA_DISCIPLINE_GATE_A_
  PROPOSAL.md` §7 已改寫為「探索 1 次＋NLP 1～2 次，合計 ≤ 3 次」，
  本報告不再重複列為待決事項。
- 場景 1／2a／1b 的合成操作（5 篇設 NULL、插一列 OK、1 篇設 NULL）PO 已
  複核接受，形狀與 §0.5 #32 段 B 已用過的手法一致。
