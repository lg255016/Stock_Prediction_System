# 首次每日 ETL 缺口自動追補——真實庫執行報告（中止，A12 適用，未修正未重跑）

## 零、關鍵發現先講

**真實執行在 NLP 情緒運算階段被 Gemini 免費層級的「每日請求數」配額（20 次/日/模型）打光，
5 次重試後仍 429，`ResourceExhausted` 例外未被攔截，`run_all_daily_tasks()` 中止。這不是
`REFUSED`（那是 TWSE/TPEX 特定例外），是一個沒被預期到的失敗模式，依 PO 指示：停下來，
不重跑，不自行修正。**

**好消息**：失敗點落在 NLP 階段（第 5 步），**在特徵工程（第 6 步）與尾端掛點（第 7 步）
之前**——`daily_ml_features` 與標籤**完全未被觸碰**（列數 449,263，與基線逐位相同，
`MAX(trade_date)` 仍是 2026-09-04）。已寫入真實庫的只有價格表、文章、留言、AI 探索的題材
映射與關鍵字——**這些全部是 append 或既有 checkpointing 機制保護的寫入，不存在半套的
`daily_ml_features`／標籤資料**。10 篇新文章的 `sentiment_score` 全部仍是 NULL（NLP 一篇
都沒有成功寫入），未來任何一次乾淨執行的 checkpointing 會自然重新撿起它們，不需要回補腳本。

**兩項 PO 複核追加的發現**：

1. **同一把 Gemini key 疑似有本次執行以外的消費者**：本次執行自己只打了 2 次 Gemini 請求
   （AI 探索 1、NLP 1），但探索那一次就撞到「每分鐘 5 次」限速、NLP 那一次撞到「每天 20 次」
   配額——20 次的每日額度在本次執行**之前**就已經幾乎用光。程式碼寫的模型別名
   `gemini-flash-latest`（`src/transform/nlp_processor.py:27`、`src/extractors/trend_discover.py:17`，
   **兩處都未釘版**）本次實際解析到 `gemini-3.8-flash`，該模型的免費層配額正是 5/分、20/日。
   **我已嘗試查證但沒有查證能力**：容器內沒有 `gcloud` CLI、沒有任何 OAuth 憑證，只有一把
   API key（不足以讀取 Google AI Studio／Cloud Console 的用量頁面，那需要帳號登入）。
   **這項需要有 Console 存取權限的人代查**，本報告只能陳述現象，無法確認成因。
2. **`n_new_days` 的計算來源在下一次執行前有一個真實缺陷**：現行邏輯取自
   `candidate_prices` 的價格缺口；本次執行後價格已補到 09-16、缺口歸零，下次執行
   `n_new_days` 會算成 0、尾端視窗退回預設的 6 列——但特徵階段屆時會一次為追蹤 8 檔
   INSERT 8 天新列（09-05～09-16，標籤欄 NULL），且既有 08-28～09-04 那些 `insufficient_data`
   的列也需要一併重算，6 列蓋不到。**n 必須改成「特徵表落後股價幾個交易日」**：特徵階段
   前取 `daily_ml_features.max(trade_date)`，逐股階段後取 `stock_prices.max(trade_date)`，
   兩者之間的交易日數才是尾端該覆蓋的範圍。這是本案下次真跑前的必修項，本報告只登記，
   不在今天動任何程式碼。

## 一、執行時間軸（全部使用容器內 `now_taipei()`，不用 host date/TZ）

| 事件 | 台北時間 |
|---|---|
| watch 探測 #1（PO 授權後第一次） | 2026-09-16 23:38:54，狀態 500 |
| watch 探測 #2（本次 cron 觸發） | 2026-09-17 00:28:24，狀態 200 |
| 序列探測之二（備份還原後、執行前） | 2026-09-17 00:40:05，狀態 200 |
| 連線目標確認、印出計算值 | 2026-09-17 00:41:00，`today_taipei()=09-17`、`previous_business_day()=09-16` |
| 真實執行開始 | ~00:41 |
| Gemini 配額打光、執行中止 | ~00:47（總耗時 371.06 秒，見七） |

## 二、前置步驟（依綁定確認包執行，全部通過）

1. **PRE 備份**（新做，不沿用演練那份）：`stock_prediction_system2_PRE_first_daily_etl_20260917_002832.dump`
   （121,413,501 bytes），存標準路徑。
2. **拋棄式容器還原驗證**：`throwaway_first_daily_etl_2`（port 59992，隨機密碼，
   `--network container:...db-1`）。還原前**現查**真實庫當下七張表列數（未沿用舊數字），
   還原後逐一相等（stock_prices/daily_ml_features 449,263、candidate_prices 1,841,594、
   market_articles 1,330、article_comments 136,185、etl_run_log 57、sentiment_cache 36）。
   驗證後 `docker rm -f`（**只 rm，未 rmi 任何 image**，`postgres:18` tag 確認未受影響）。
3. **PTT 兩次探測皆 200**（見一）。
4. **連線目標確認**：`current_database()=postgres`、`inet_server_port()=5432`（真實庫，harness
   內建 assert 擋非 5432）。

## 三、缺口與批次階段（完整成功）

- `previous_business_day()=2026-09-16`（凌晨執行，已跨過 08:00 UTC/容器日界，見
  `market_report_fetcher.py` L258），`candidate_prices` 現有最新日期仍是 09-04，
  **n=8 個交易日**（09-07/08/09/10/11/14/15/16，含 09-16 本身）。
- 16 個批次請求（8 天 × 2 市場）全部 `OK`，無 `REFUSED`、無 `FETCH_FAILED`。
- 逐股階段：`tracked_stocks_daily` 57 筆全 `OK`（7 檔 TWSE/TPEX × 8 天 = 56 ＋ NVDA 1 次 = 57）。

## 四、AI 熱門趨勢探索（成功，過程中也撞到 Gemini 限速但自行重試成功）

- 同樣撞到 Gemini 429（`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`，limit 5），
  但該模組有自己的重試邏輯，2 秒後重試成功。
- 發現 3 個新題材（記憶體、AI伺服器與運算、蘋果供應鏈），12 筆題材成分股關聯寫入
  `theme_stock_mapping`，2 個新關鍵字寫入 `tracking_keywords`（`category=ai_discovered`）。

## 五、PTT（成功，真實新資料）

- 28 個關鍵字：6 `OK`、22 `NO_DATA`、0 `FETCH_FAILED`——**這次 PTT 沒有故障**，第 3 項的
  「成因 F 未接線」缺口這次沒有觸發（因為源頭沒有失敗）。
- 10 篇新文章、908 則新留言寫入。

## 六、NLP 情緒運算（**失敗，中止點**）

- 撈到 10 筆待處理文章，開始呼叫 Gemini。
- 前段有「4 筆複雜標題」批次處理，撞到 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
  （**每日配額 20 次，非每分鐘**）——這代表 AI 熱門趨勢探索與 NLP 的 Gemini 呼叫**共用同一個
  每日配額**，探索階段已先消耗掉一部分。
- 5 次重試（2/4/8/16 秒指數退避）後仍 429，`ResourceExhausted` 未被 `NLPProcessor` 內部攔截，
  往上傳播到 `run_all_daily_tasks()`，執行中止。
- **10 篇文章的 `sentiment_score` 全數仍為 NULL**（一篇都沒寫入）。

## 七、七、逐段計時（成功部分）

| 階段 | 秒數 |
|---|---|
| 1_batch（8天×2市場，16請求） | 71.98 |
| 2_per_stock（推算） | 5.27 |
| 3_ai_trend（含 429 重試等待） | 79.75 |
| 4_ptt | 62.45 |
| 5_nlp（含 5 次重試等待，最終失敗） | 151.61 |
| 6_feature_engineering | **未執行** |
| 7_tail_recompute | **未執行** |
| 總計（到中止為止） | 371.06 |

**RISK-005 無法回填**：批次階段本身（71.98s，8 天 16 請求）遠低於 5 分鐘門檻，但**整個
`run_all_daily_tasks()` 未完整跑完**，無法給出完整的單次執行耗時基準；且本次是 8 天追補，
仍不是純粹單日增量的計時。

## 八、真實庫寫入後狀態（唯讀評估，未做任何修正）

| 表 | 基線 | 執行後 | diff |
|---|---|---|---|
| stock_prices | 449,263 | 449,326 | +63 |
| candidate_prices | 1,841,594 | 1,857,371 | +15,777 |
| market_articles | 1,330 | 1,340 | +10 |
| article_comments | 136,185 | 137,093 | +908 |
| **daily_ml_features** | **449,263** | **449,263** | **0（未觸碰，特徵階段未執行到）** |
| etl_run_log | 57 | 158 | +101 |
| sentiment_cache | 36 | 36 | 0 |

`daily_ml_features` 的 `MAX(trade_date)` 仍是 `2026-09-04`；`stock_prices` 的 `MAX(trade_date)`
已是 `2026-09-16`——**價格資料已經領先特徵資料 8 個交易日，這是預期中的正常過渡狀態
（特徵引擎本來就該晚一步跑），不是資料損毀**。

`etl_run_log` 新增 101 列，逐項核對：ptt(NO_DATA 22＋OK 6)=28、tpex OK 8、twse OK 8、
tracked_stocks_daily OK 57，28+8+8+57=101 ✅ 算術核對通過。

## 九、POST 備份

`stock_prediction_system2_POST_first_daily_etl_20260917_0107_partial_nlp_quota_failure.dump`
（122,021,783 bytes）——刻意在檔名裡標記「partial」與失敗原因，避免日後誤認為是一次成功
執行的 POST 快照。

## 十、未驗證／未執行清單（有名字有去處）

- 十項觀察清單第 4／7 項以外全數**未達可驗證階段**（依賴 `daily_ml_features` 更新，這次沒發生）。
- 尾端掛點觸及列數、md5 對帳（458 檔台股）：**未執行，無資料可對**。
- CHAL-010 標籤算術：**未執行**。
- RISK-005 完整計時：**未達成**（見七）。

## 十一、我沒有做的事（刻意，依 PO 指示）

- 沒有重跑 `run_all_daily_tasks()`。
- 沒有手動呼叫 NLP／特徵工程／尾端掛點把這次「補完」。
- 沒有更動任何 Gemini 相關程式碼（重試次數、配額處理、切換模型或 API key）。
- 沒有嘗試用任何方式繞過或提高 Gemini 配額。
- CronCreate 的 watch job（`e7aaf990`）已刪除——本次一次性條件式授權已用盡，不會自動再試。

## 十二、PO 複核裁決（2026-09-17）與本輪處置

PO 已裁決：登記 `RISK-031`（見結案 commit）；n 來源缺陷（見零、第 2 項）本案內修，真跑前必做，
今天只登記不動碼；Gemini 用量縮減與 F 接線範圍擴大兩個候補小案已排定順序，見 §0.5 新增項。
本輪不再真跑、不改 Gemini 設定、不換模型、不手動評分那 10 篇。

**「同一把 key 是否有其他消費者」的查證能力揭露**：PO 要求到 Google AI Studio／Cloud Console
的用量頁面抓 09-16 15:00～09-17 01:00（太平洋日界對應台北時間）的請求時間分布。**我不具備
這項查證能力**——容器內沒有 `gcloud` CLI，沒有任何 OAuth 憑證，只有一把 API key，不足以
讀取需要帳號登入的用量／帳單頁面。這項需要持有 Console 存取權限的人代查，本報告只能陳述
「本次執行自己只打了 2 次請求，但配額在執行前就已幾乎用光」這個現象，無法確認成因是否為
其他消費者。
