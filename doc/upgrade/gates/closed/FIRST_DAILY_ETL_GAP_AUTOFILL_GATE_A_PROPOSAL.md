# 首次每日 ETL 缺口自動追補——Gate A 提案

## 0. 摘要

`PROJECT_STATUS.md` §0.5 #20 首次每日 ETL 真實執行段 0 唯讀查證發現：`candidate_prices`／`stock_prices`
最新日期停在 2026-09-04，距今（2026-09-16）已有多個交易日缺口。`run_all_daily_tasks()` 目前只抓
`previous_business_day()`（昨日）一天，不會回補中間缺口；且 `feature_aggregator.py` 的滾動特徵
（`return_1d`／`volatility_5d`／`volatility_20d`／Triple-Barrier 進場價）一律用**列位移**
（`groupby(...).shift(1)`／`.rolling(window=N)`），不感知交易日曆是否連續——若直接對現況執行，
會把 09-04 到 09-15 之間的缺口**靜默**吃進滾動窗口，產生語意錯誤但數值上「看起來正常」的特徵
（例如把 8 個交易日的報酬算成 `return_1d`）。

**本提案**：在批次階段前插入缺口偵測與自動逐日追補，取代現行單日邏輯，使中斷任意長度的時間
後再執行都能自行補齊，不需人工介入或另開回補腳本。首次每日 ETL 的真實執行即為本案的首次真跑。

---

## 1. Requirement Source

- PO 2026-09-16 工作單「首次每日 ETL 真實執行」段 0 唯讀查證的衍生發現。
- 審查方（`sps_project_reviewer`）2026-09-16 複核：段 0 三處 expectations 錯誤 + 本結構問題。
- PO 2026-09-16 裁決：改為「偵測沒有價格的日子後自動回補」，走 `bug-fix-protocol`。

---

## 2. Current State（唯讀查證，2026-09-16，容器內／程式碼閱讀）

| # | 事實 | 出處 |
|---|------|------|
| 1 | `candidate_prices`／`stock_prices` 最新日期皆為 `2026-09-04` | 段 0 SQL 查詢，`FIRST_DAILY_ETL_expectations.json` |
| 2 | `previous_business_day()` 只回傳「昨日」（跳過週末，不知道國定假日），無記憶上次執行時間 | `src/extractors/market_report_fetcher.py:250-263` |
| 3 | `run_price_batch(trade_date, markets=(...))` 已支援單日、可指定市場子集呼叫；`ServiceRefusedError` 在該次呼叫內立即 raise（run log 已先落地），由呼叫端決定如何處置 | `main_etl_pipeline.py:90-195` |
| 4 | `run_all_daily_tasks()` 目前對 `ServiceRefusedError` 的處置是：捕捉、記下 `refusal`、其餘階段照跑、**全部階段跑完才 raise** | `main_etl_pipeline.py:623-647`、`796-798` |
| 5 | `run_triple_barrier_tail_recompute()` 對**整個 `stock_prices`**（459 檔，非僅追蹤 8 檔）呼叫 `recompute_tail_labels()`；後者用 `groupby("stock_id").tail(holding_period+1)`，故實際觸及約 459×6≈2,754 列，UPDATE 語意 | `main_etl_pipeline.py:582-591`、`src/ml/triple_barrier.py:143-162` |
| 6 | `recompute_tail_labels(df, holding_period=5)` **只有一個 `holding_period` 參數，同時決定 (a) Triple-Barrier 本身的持有期窗口與 (b) 要重算尾端幾列**（`full = generate_triple_barrier_labels(df, holding_period=holding_period)` 接著 `.tail(holding_period+1)`） | `src/ml/triple_barrier.py:160-161` |
| 7 | `upsert_ml_features()` 對 `daily_ml_features` 做 `INSERT ... ON CONFLICT (trade_date, stock_id) DO UPDATE SET`，`update_cols` 排除**僅** `target_triple_barrier`／`label_reason` 兩欄，其餘 27 欄（含 `sentiment_mean`／`comment_polarization`／`net_push_momentum`）逐次執行都會被覆寫 | `src/loaders/db_writer.py:709-756` |
| 8 | `fetch_all_for_features()` 對 `stock_prices`／`market_articles`／`article_comments` **無日期篩選**，每次呼叫都撈全歷史、全宇宙 | `src/loaders/db_writer.py:625-686` |
| 9 | `generate_daily_features()` 有 `failed_source_keys` 參數（用於標記成因 F／`SOURCE_FAILED`），但 `run_feature_engineering_pipeline()` 呼叫時**未傳入**，故此參數在每日排程路徑上恆為 `None` | `src/transform/feature_aggregator.py:341-349`、`main_etl_pipeline.py:550-553` |
| 10 | `return_1d`／`volatility_5d`／`volatility_20d`／`sentiment_lag_1/2`／`volume_ratio_5d` 等一律用 `groupby('stock_id')[...].shift(N)` 或 `.rolling(window=N)`，純列位移，不檢查 `trade_date` 是否連續 | `src/transform/feature_aggregator.py:701-820` |

---

## 3. 設計回應（逐條回應審查方 §3.1 七項要求）

### 3.1 偵測——**同意**

對 `twse`／`tpex` 各自查 `candidate_prices` 的 `max(trade_date)`（`WHERE source IN (...)` 依市場區分,
或直接 `SELECT market, MAX(trade_date) ... GROUP BY market` 若 `candidate_prices` 有市場欄——
**查證**：`candidate_prices` 無 `market` 欄，但 `source` 欄的值域即市場對映（`twse_mi_index`／
`tpex_daily_quotes`，見 `SOURCE_BY_MARKET`），故用 `source` 分組等價於依市場分組），從次日起逐平日
推進到 `previous_business_day()`。同意分開偵測的理由（RISK-028 TPEX 常態性單邊失敗）成立，
`etl_run_log` 08-25／08-26 的既有紀錄即為實例。

**補充（審查方要求）**：`fetch_candidate_prices_max_date_by_market()`（新 `DBWriter` 方法）對某市場
在 `candidate_prices` 沒有任何既有列時，該市場對應值回傳 `None`——**不得預設成任何日期（例如
「昨天」）後靜默只跑單日**。呼叫端偵測到 `None` 時，直接 raise 新例外
`MissingBackfillOriginError(market)`（計劃放 `src/extractors/market_report_fetcher.py`，與
`BackfillWindowExceededError` 同檔），**拒絕執行，零請求送出**，需人工判斷該市場的起點
（例如首次上線、或資料表被清空過）。這與「缺口過大」（§3.3）是不同的失敗模式：前者是「不知道
從哪裡開始」，後者是「知道從哪裡開始，但太遠」，兩者的處置都是拒絕執行，但原因需分開報錯，
不得共用同一個例外類別。

### 3.2 三態語意不變——**同意**

`NO_DATA` 繼續、`FETCH_FAILED` 記錄繼續（該市場 `max(trade_date)` 不前進，下次執行自然從失敗日
重試）、`REFUSED` 記錄後**停止對該市場的後續追補日期**（不是整批停止——同 `run_price_batch()`
既有的「一邊拒絕不代表另一邊要停」原則，§2 第 4 項已查證），最後統一 raise。

### 3.3 上界——**同意，30 個平日**

理由與審查方一致：長期停機不能讓程式自動對交易所打幾百個請求。30 個平日 ≈ 6 週，
超過即拒絕執行並明確報錯，要求人工處理（不自動截斷後靜默執行部分回補）。

### 3.4 節流——**同意**

沿用既有 `throttle` 參數與既有節流機制，不新增請求頻率、不繞過。

### 3.5 逐股階段跟著逐日——**同意，且補一個必須顯式處理的邊界**

追蹤 8 檔對每個追補日期各自走 `run_*_pipeline_from_candidate_prices(sid, date, batch_outcome=...)`，
`etl_run_log` 的 `batch_key` 逐日分開，`assert_complete()` 逐日成立。**補充**：若某日某市場被
`REFUSED`（3.2 的結果），該日對應市場的追蹤股票逐股階段**沒有 `candidate_prices` 可複製**——
**訂正（原文誤植，審查方指出）**：此時逐股階段對該日該市場的標的應記 `REFUSED`，**不是**
`FETCH_FAILED`（因為上游是被拒絕，不是抓取失敗；「該股真的沒有交易」則是另一種語意，不得混淆）。
這與現行 `run_tpex_pipeline_from_candidate_prices()` 的既有機制完全一致：該方法在無列且
`batch_outcome != OK` 時 raise 的例外，其 `upstream_outcome` 屬性已明文寫死
`REFUSED if batch_outcome == REFUSED else FETCH_FAILED`（`main_etl_pipeline.py:282-283`），
外層迴圈的例外處理（`main_etl_pipeline.py:704-710`）原樣沿用這個 `upstream_outcome`——
本提案不改這段既有邏輯，只是延伸到多日迴圈時要正確把每日各自的 `batch_outcome` 傳進去，
不得因為多日迴圈而退化成單一預設值。此為紅測必須覆蓋的邊界（見 §6）。

### 3.6 尾端掛點視窗要跟著加寬——**同意方向，但實作方式需修正**

**問題**：`recompute_tail_labels(df, holding_period=5)` 的 `holding_period` 參數**同時**是
(a) Triple-Barrier 本身的持有期窗口（業務常數，`DEC-040`／`DEC-041` 相關，**不得因為這次補了
n 天資料就改變**）與 (b) 要重算尾端幾列（`.tail(holding_period+1)`）。**若照審查方原文字面把
`holding_period+n` 整個傳進 `recompute_tail_labels`，會連帶把 Triple-Barrier 的持有期窗口從
5 天改成 `5+n` 天，這是錯的**——那會讓本次追補之後產生的標籤，與既有 458+NVDA 檔用
`holding_period=5` 算出的標籤語意不一致，是本提案沒有授權去動的東西（§2 第 6 項）。

**修正做法**：`recompute_tail_labels()` 新增一個獨立參數 `tail_window`（預設 `None`，
即退化為現行的 `holding_period+1`），語意改為：

```python
def recompute_tail_labels(df, holding_period=5, tail_window=None):
    full = generate_triple_barrier_labels(df, holding_period=holding_period)  # 持有期窗口不變
    window = tail_window if tail_window is not None else holding_period + 1
    tail_idx = full.groupby("stock_id").tail(window).index
    return full.loc[tail_idx].reset_index(drop=True)
```

呼叫端 `run_triple_barrier_tail_recompute()` 依本次實際追補的新交易日數 `n` 算出
`tail_window = holding_period + n`（`n=1` 時 `tail_window = holding_period+1`，與現行輸出逐位相同，
既有測試不需改動），`holding_period` 本身維持呼叫端傳入的既有預設值 `5`，不變。

**`n` 的定義（訂正，審查方要求補上）**：`n = 本次追補日期序列的長度`，**含 `NO_DATA` 與
`FETCH_FAILED` 的日子**，不是「實際成功寫入的天數」。理由：視窗只是選取範圍，選寬一點只會
多重算幾列冪等結果（該列本來就沒有新資料，重算後值不變）；若改用「成功天數」，還要多一層
統計、多一個可能出錯的地方，且與偵測到的缺口序列本身脫鉤，徒增覆核負擔。

### 3.7 不動的東西——**同意**

`previous_business_day()` 本身、`market_report_fetcher` 的請求邏輯、`retry_policy`、
`FeatureAggregator`（特徵聚合演算法本身）、`DBWriter` 的寫入語意（`upsert_ml_features()` 的
`ON CONFLICT DO UPDATE` 排除清單、`update_triple_barrier_tail_labels()` 的純 `UPDATE` 語意）皆不修改。

---

## 4. In Scope / Out of Scope

**In Scope**：
- `main_etl_pipeline.py`：`run_all_daily_tasks()` 批次階段與逐股階段改為多日迴圈；新增缺口偵測、
  上界拒絕、`n`（本次追補新交易日數）的計算與傳遞給尾端掛點。
- `src/ml/triple_barrier.py`：`recompute_tail_labels()` 新增 `tail_window` 參數（向下相容）。
- 對應紅測。

**Out of Scope（本輪不動，登記在段 0 JSON 供之後另案）**：
- `generate_daily_features()` 的 `failed_source_keys` 未接線問題（成因 F 結構上不可能出現）——
  本案不修，維持登記為候補小案。
- `feature_aggregator.py` 對「重算後值與既有值不同」的偵測本身——本案用 md5 對帳作為**驗證手段**，
  不是在生產程式碼裡新增偵測邏輯。
- 任何 rolling／shift 邏輯本身改為「日曆感知」——不在本案範圍，30 個平日上界已把最壞情況的
  失真幅度限制在可控範圍，且回補後的資料本來就會是逐日連續的，失真只發生在追補當下那一批。

---

## 5. Affected Components

| 檔案 | 變更性質 |
|------|---------|
| `main_etl_pipeline.py` | 修改：批次階段（原 line 620-647）與逐股階段（原 line 649-718）改為多日迴圈；`run_triple_barrier_tail_recompute()` 呼叫改傳入本次新增天數 |
| `src/extractors/market_report_fetcher.py` | 新增：`compute_gap_backfill_dates(last_date, target_date, max_days=30)`（純函式）、`BackfillWindowExceededError`、`MissingBackfillOriginError`；`previous_business_day()` 本身不動 |
| `src/loaders/db_writer.py` | 新增：`fetch_candidate_prices_max_date_by_market()`——依 `source` 值域（`SOURCE_BY_MARKET`）分組查 `candidate_prices` 的 `MAX(trade_date)`，供批次階段偵測缺口起點；不改任何既有方法 |
| `src/ml/triple_barrier.py` | 修改：`recompute_tail_labels()` 新增 `tail_window` 參數（向下相容，預設 `None`） |
| `tests/test_first_daily_etl_gap_autofill.py`（新增，已存在，紅測全數確認 FAIL） | 紅測：見 §6 逐項對應與實測結果（數字以 §6 為準，本表不重複列） |

---

## 6. Tests（已寫成 `tests/test_first_daily_etl_gap_autofill.py`，全合成資料，不碰網路不碰真實庫）

| # | 測試函式 | 對應設計要求 |
|---|---------|-------------|
| 1 | `test_sequence_skips_weekends` | §3.1 缺口日期序列跳過週末 |
| — | `test_no_gap_returns_empty_list`（額外邊界） | `last_date==target_date` 時序列為空 |
| 2 | `test_holiday_no_data_day_does_not_interrupt_sequence` | §3.2 `NO_DATA` 不中斷序列 |
| 3 | `test_fetch_failed_day_does_not_interrupt_sequence` | §3.2 `FETCH_FAILED` 不中斷序列，且不移除該市場 |
| 4 | `test_refused_market_stops_only_that_market_for_later_dates` | §3.2 `REFUSED` 停該市場、不停整批（`assertRaises(ServiceRefusedError)` 包住呼叫——deferred raise） |
| 5 | `test_upper_bound_rejects_without_partial_result` | §3.3 超過 30 個平日拒絕，不回傳部分結果 |
| — | `test_upper_bound_boundary_exactly_30_is_allowed`（額外邊界） | 恰好等於上界應放行 |
| 6 | `test_tail_window_widens_selected_rows` | §3.6 `tail_window=holding_period+n` 選取列數 |
| — | `test_tail_window_does_not_change_barrier_calc_itself`（核心安全斷言） | §3.6 訂正點——**寬窄視窗重疊列的標籤值必須逐位相同**，防止 `tail_window` 誤動 barrier 計算窗口本身（此為 §2 第 6 項發現的字面誤植風險，本測試是它的迴歸鎖） |
| 7 | `test_default_tail_window_matches_existing_behavior` | `tail_window=None` 與現行行為逐位相同 |
| 8 | `test_batch_key_separated_per_backfill_date` | §3.5 `etl_run_log` 的 `batch_key` 逐日分開 |
| 9 | `test_refused_market_propagates_batch_outcome_to_per_stock_stage` | §3.5 訂正——`REFUSED` 日該市場的 `batch_outcome` 正確傳遞給逐股階段（見下方自我糾正說明） |
| — | `test_run_price_batch_called_once_per_backfill_date`（整合驗證） | 缺口天數與 `run_price_batch` 呼叫次數、日期一致 |
| 補 1 | `test_tail_recompute_receives_n_new_days_as_tail_window` | §3.6 呼叫端把追補天數 `n` 真的傳進 `run_triple_barrier_tail_recompute(tail_window=...)`；`n` 含 `NO_DATA`／`FETCH_FAILED` 的日子 |
| 補 2a | `test_maps_source_to_market` | 新 `DBWriter.fetch_candidate_prices_max_date_by_market()`：`source` 值域正確對映 `twse`／`tpex` |
| 補 2b | `test_missing_market_is_none_not_absent_key` | 同上：市場無任何列時回傳 `None`（非缺鍵） |
| 補 2c | `test_missing_backfill_origin_rejects_execution` | 某市場起點為 `None` 時整個拒絕執行、零請求（`MissingBackfillOriginError`） |
| 補 3 | `test_same_day_rerun_skips_batch_but_runs_rest` | 同日重跑：`run_price_batch` 零呼叫，PTT／NLP／特徵／尾端掛點照常執行 |

**容器內最終執行結果（2026-09-16，`postgres@localhost:5432` 之外不觸及任何真實資源）**：

```
Ran 18 tests in 3.249s
FAILED (failures=7, errors=11)
```

全套（含既有）：`Ran 1089 tests`（1071 既有 + 18 新增），失敗數＝新增紅測數，既有測試零迴歸。
18 項全數 FAIL，符合 `CLAUDE.md` §9A.2。

**⚠ 撰寫過程中的兩次自我糾正（誠實揭露）**：

1. **網路外洩**：第一版三個整合測試把 `run_ptt_pipeline`（未被呼叫的舊方法）誤當成 mock 對象，
   且用 `fetch_active_stock_targets.return_value = []` 觸發了 `run_all_daily_tasks()` 的預設
   fallback 清單（含 NVDA）——兩者疊加，導致測試執行期間**真的打出了對 `ptt.cc` 與 yfinance
   的網路請求**（未觸及任何真實庫寫入，`db_writer` 全程為 `MagicMock`）。已修正並重跑確認
   `grep` 不出任何網路相關字樣。
2. **§9A.1 級的假紅測**：測項 9（原名 `..._marks_fetch_failed`）第一版把
   `previous_business_day()` 直接設成 `REFUSED` 發生的那一天（單一缺口日）——結果**舊的單日
   程式碼剛好也會在那天呼叫到 `run_price_batch`、也剛好把同一個 `batch_outcome` 傳給逐股階段，
   測試在完全沒有任何新程式碼的情況下意外 PASS**。改為 tpex 缺口兩天（09-07 `REFUSED`、
   09-08 是 `previous_business_day()`），斷言改成「呼叫記錄裡存在 `trade_date=09-07` 且
   `batch_outcome=REFUSED` 的那一筆」，重跑確認對舊程式碼正確 FAIL（舊碼只會用
   `previous_business_day()` 單一日期呼叫一次，不會產生 `trade_date=09-07` 的呼叫）。
   這正是 `CLAUDE.md` §9A.1「結構上無法失敗的檢查不是檢查」的一次實例，發現方式是逐一核對
   紅測結果的測試名稱清單，發現總數與 FAIL／ERROR 數對不上（18 項只有 17 項在失敗清單裡）。

每項先看到 FAIL（因為實作尚未存在）再進入段 B 實作（`CLAUDE.md` §9A.2）。

---

## 7. Rollback / RISK-013

本案段 A／段 B（提案、紅測、實作、測試、拋棄式庫演練）全程不碰真實庫。真實執行（段 C）
沿用原工作單的 RISK-013 三項協議：PRE 備份 → 拋棄式容器還原驗證 → PO 綁定確認 → 執行 →
獨立驗證 → POST 備份。若拋棄式庫演練任一項不符段 0 JSON（依 §2 三處修正後）的預期，
停在演練，真實庫一列都不動。

---

## 8. Definition of Done

- §6 登記的全部紅測（或依實作過程新增的邊界案例）在容器內（`postgres@localhost:5432` 之外的臨時測試庫，
  或使用純記憶體合成 DataFrame，不連真實庫）先 FAIL，實作後全綠。
- 全套測試 `python -m unittest discover -s tests -p "test_*.py"` 於 `postgres`@`localhost:5432` 上
  的資料**不受影響**（測試本身不得動真實庫，唯讀查詢除外）。
- `python scripts/verify/gate0_contract_check.py` 14/14 PASS。
- 拋棄式庫演練：對還原自 PRE 備份的拋棄式容器完整跑一次 `run_all_daily_tasks()`，十項觀察清單
  （依段 0 JSON 第二節三處修正後）逐項核對，md5 對帳（09-04 以前、459 檔的 25 個特徵欄）通過。
- 演練報告送審查方複核通過後，才進入段 C 真實執行的 PO 綁定確認。
