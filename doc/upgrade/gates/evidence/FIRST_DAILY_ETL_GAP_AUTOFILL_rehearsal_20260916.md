# 首次每日 ETL 缺口自動追補——拋棄式容器演練報告（v2，依審查方複核訂正）

**HEAD**: 演練本身跑在 `2b41cc4`；兩處小修已於複核後另 commit `f553333`（差異僅常數引用與
docstring，值不變，不要求重新演練）。

## 零、關鍵發現先講（審查方複核要求提升到最前面，不埋在表格裡）

**PTT（ptt.cc）演練當日對 `/bbs/Stock/index.html` 回 HTTP 500，26 個關鍵字全部 `FETCH_FAILED`。
這不只是一次外部服務不可用——它讓「日常路徑產生不出成因 F（`SOURCE_FAILED`）」這個原本只是
理論登記的缺口，第一次在真實輸入上被實證發生**：追蹤 8 檔本次新交易日的
`daily_ml_features` 仍全數寫成 `source_status='SUCCESS_EMPTY'`，把「來源掛了，沒抓到」與
「當天真的沒人討論」寫成同一個值，特徵層完全看不出 PTT 那天其實是故障的。技術面上 NULL／
預設值的 W／U 分類仍然正確、沒有出現無法歸類的情形，但**這件事不能寫成「符合成因 U，PASS」
——正確的結論是「W／U 分類技術上成立，但成因 F 接線缺口的必要性由本次演練證實」**。
PO 裁決：「成因 F 接線」小案排進真實首跑之後的第一個候補小案，優先於雙時點排程小案。

另一項發現（NVDA md5 差異）見下方第六節；PO 已裁決只排除 NVDA、不開新風險編號。

## 一、PRE 備份與還原驗證

- PRE 備份：`stock_prediction_system2_PRE_first_daily_etl_20260916_215529.dump`（121,413,501 bytes），存 `D:\Python\Database_Backups\Stock_Prediction_System2\`。
- 拋棄式容器：`throwaway_first_daily_etl`，`postgres:18`，隨機密碼（32 字元，未落地任何檔案外的地方，容器移除後即失效），`--network container:stock_prediction_system2_devcontainer-db-1`，`PGPORT=59991`，`--memory=2g --cpus=0.5`。
- 還原後七張表列數與段 0 基線逐一相等：
  | 表 | 基線 | 還原後 |
  |---|---|---|
  | stock_prices | 449,263 | 449,263 |
  | candidate_prices | 1,841,594 | 1,841,594 |
  | market_articles | 1,330 | 1,330 |
  | article_comments | 136,185 | 136,185 |
  | daily_ml_features | 449,263 | 449,263 |
  | etl_run_log | 57 | 57 |
  | sentiment_cache | 36 | 36 |
- 連線目標確認：`current_database()=postgres`、`inet_server_port()=59991`（非真實庫 5432）。

## 二、執行

`run_all_daily_tasks()` 對拋棄式庫完整執行一次（真實對外請求：TWSE／TPEX／PTT／yfinance；Gemini 因無新文章未觸發）。`error: None`（正常完成，無例外）。

**缺口偵測結果**：twse／tpex 皆從 2026-09-04 次日追補到 `previous_business_day()`=2026-09-15，n=7 個交易日（09-07/08/09/10/11/14/15，跳過 09-12/13 週末）。14 個批次請求（7 天 × 2 市場）全部 `OK`，**無 `REFUSED`、無 `FETCH_FAILED`，RISK-028 這次沒有出現**（間歇性問題，本次運氣好，不代表已修復）。

## 三、十項觀察清單

| # | 項目 | 結果 |
|---|------|------|
| 1 | 161 篇孤兒文章歸屬 | 2059:13→13（不變）、2454:99→100（+1）、3008:20→22（+2）、8069:20→20（不變）——7 天內新文章量少，符合預期，無異常流失 |
| 2 | 4 檔新股 source 值域 | 追補期間新寫入 `stock_prices` 的 source 只有 `twse_mi_index`／`tpex_daily_quotes`，**零 `yfinance_auto_adjusted`** ✅ |
| 3 | 暖機期 NULL 分類 | **訂正（見零、關鍵發現）**：2059/2454/3008/8069 新增 28 列（4 檔×7天），技術指標欄 0 個 NULL、W／U 分類無未分類情形，技術面成立；**但 `source_status` 全數 `SUCCESS_EMPTY`／`SUCCESS`，未反映當天 PTT 實際回 HTTP 500 全面失敗——成因 F 接線缺口本次由真實輸入實證，不是單純「符合成因 U 過關」** |
| 4 | 批次請求數與耗時 | 14 個邏輯請求（7天×2市場），每個 `HTTP 嘗試 1`，無 rate-limit 訊號；批次階段總耗時 61.56s |
| 5 | 2330/2382 於 09-01/09-02 | 沿用段 0 已確認結果（PASS，本次未重查） |
| 6 | 缺口自動偵測機制 | ✅ 本次執行本身即證明：機制存在，7 天缺口全數自動偵測並依序追補，非人工介入 |
| 7 | CHAL-010 回歸算術 | 見下方「五、標籤算術對帳」，逐項核對通過 |
| 8 | RISK-027 假期流失 | 本次 7 天皆非台股假期前後，article_count 無異常流失 |
| 9 | RISK-028 outcome | `etl_run_log` 逐市場 outcome 全數 `OK`，本次未觸發 |
| 10 | 缺口偵測常設化 | 見下方「四、七張表 diff」，逐日覆蓋已列印確認無新缺口 |

## 四、七張表 diff

| 表 | 基線 | 執行後 | diff |
|---|---|---|---|
| stock_prices | 449,263 | 449,319 | +56（7天×7檔 TWSE/TPEX ×1 + NVDA新增7天×1=56，算術核對：49+7=56 ✅） |
| candidate_prices | 1,841,594 | 1,855,399 | +13,805（7天全市場批次，平均每天 ~1,972 列，7×1,972≈13,804，相符） |
| market_articles | 1,330 | 1,330 | 0（PTT 本次 FETCH_FAILED，無新文章） |
| article_comments | 136,185 | 136,185 | 0（同上） |
| daily_ml_features | 449,263 | 449,319 | +56（與 stock_prices 同步，1:1） |
| etl_run_log | 57 | 147 | +90（26 PTT FETCH_FAILED + 7 tpex OK + 7 twse OK + 50 tracked_stocks_daily OK = 90 ✅） |
| sentiment_cache | 36 | 36 | 0（無新文章需要情緒運算） |

`daily_ml_features` 總列數＝基線 449,263 ＋ 7 個新交易日 × 8 個有價格的追蹤檔（7 個 TWSE/TPEX + NVDA）＝449,263+56＝449,319 ✅ 算術核對通過。

## 五、標籤算術對帳（CHAL-010）

| | -1 | 0 | +1 | TB=NaN | label NaN | ambiguous | insufficient | no_entry |
|---|---|---|---|---|---|---|---|---|
| 基線 | 226,956 | 21,199 | 162,288 | 38,820 | 410,443 | 36,388 | 1,892 | 540 |
| 執行後 | 226,984 | 21,199 | 162,309 | 38,827 | 410,492 | 36,395 | 1,892 | 540 |
| Δ | +28 | 0 | +21 | +7 | +49 | +7 | 0 | 0 |

核對：TB 非 NULL 總 Δ（28+21=49）＝ label_reason NULL 的 Δ（49）✅；TB NaN 的 Δ（7）＝ ambiguous_dual_barrier 的 Δ（7）✅；insufficient_data／no_entry 皆 0（尾端視窗加寬只會把先前卡在邊界的列解出真標籤或 ambiguous，不會產生新的 insufficient/no_entry）；總計 226,984+21,199+162,309+38,827=449,319，與 daily_ml_features 總列數相符 ✅。尾端掛點觸及 **5,508 列**（預期 459 檔 ×(5+7)=5,508，精確相符 ✅），值真的改變的只落在追蹤 8 檔範圍內（此點下方 md5 對帳一併確認）。

## 六、md5 對帳（09-04 以前、458 檔台股、25 個特徵欄，排除 NVDA）——**PO 已裁決**

**第一次比對用型別不一致的比法（`DBWriter.fetch_data()` 回 `Decimal`、`pd.read_sql` 回 `float64`），誤判出幾乎每欄都有數萬列「差異」——那是比對腳本自己的 bug，不是真實資料差異。改用型別正規化＋浮點容差（1e-6）重新比對後：**

- **449,263 列中，449,206 列（99.987%）逐欄位元完全相同。**
- **57 列不同，全部是 `NVDA`，日期範圍 2026-06-16～2026-09-04，恰好等於今天（09-16）往前 3 個月。**
- 差異只出現在 NVDA 的 `close_price`／`volume`／`return_1d`／`rsi_14`／`volatility_5d`／`volatility_20d`／`amplitude_ratio`／`ma5_bias_ratio`／`ma20_bias_ratio`／`volume_ratio_5d`（皆為價格衍生欄）。
- **情緒／留言欄（`sentiment_mean`／`sentiment_3d_ma`／`sentiment_5d_ma`／`sentiment_lag_1`／`sentiment_lag_2`／`bullishness_index`／`agreement_index`／`comment_volume_ratio`／`comment_polarization`／`net_push_momentum`）全部 0 差異**——你在段 A 複核最擔心的 RISK-027／023 覆寫風險**沒有發生**，聚合器對同一批文章/留言輸入是確定性的。

**成因（已定位，非臆測）**：`run_us_stock_pipeline(sid, period="3mo")`——NVDA 走 yfinance，每次執行都重抓「今天往前 3 個月」並 upsert，**這是本案完全沒有動過的既有機制**（§3.7 不動的東西之一）。yfinance 的調整後收盤價會隨時間對同一天做微幅回溯修正（已知公開行為，常見於除權息或資料源自身校正），所以同一天的值在不同時間點重抓會有極小差異，連帶讓 `return_1d`／`rsi_14`／`volatility_*` 等衍生欄也跟著微幅變動。

**這件事本來就會發生，且與本案（缺口自動追補）無關**——`run_us_stock_pipeline()` 從 SB2/SB2a 以來就是這樣寫的，只是這是本專案第一次真的把 `run_all_daily_tasks()` 完整跑兩次（一次歷史回補、一次這次），第一次真正觀察到這個現象。**不是回歸，是既有機制的既有行為，這次才第一次被看見。**

**PO 裁決（2026-09-16）：只排除 NVDA，不登記新風險。** 驗收範圍改為「09-04 以前、458 檔台股
（排除 NVDA）、25 個特徵欄」——這 458 檔在本次演練 md5 前後完全相同（PASS）；NVDA 的變動屬
既有 `run_us_stock_pipeline(period="3mo")` 機制的預期行為，不算回歸，也不需要新風險編號。
`FIRST_DAILY_ETL_GAP_AUTOFILL_expectations.json` 已同步訂正此驗收範圍。

## 七、逐段計時

| 階段 | 秒數 |
|---|---|
| 1_batch（7天×2市場） | 61.56 |
| 2_per_stock（推算） | 2.87 |
| 3_ai_trend | 0.07 |
| 4_ptt | 4.30 |
| 5_nlp | 0.00（無新文章） |
| 6_feature_engineering（全歷史重算） | 48.89 |
| 7_tail_recompute | 5.66 |
| **總計** | **123.37** |

RISK-005：本次是「追補 7 天＋當日增量」混合，不是純粹的單日增量計時——之後真實首跑若缺口已補齊（只剩 1 天），批次階段耗時預期遠低於 61.56s（該數字主要反映 7 天 14 個請求的總和，不是單日速度）。回填 `REMAINING_RISKS.md` 時會把這個混合性質寫清楚，不誤植為單日基準。

## 八、清理

- 拋棄式容器 `throwaway_first_daily_etl` 已 `docker rm -f`。
- **誠實揭露一個操作失誤並已修正**：清理時誤用 `docker rmi -f postgres:18` 把真實 db／app 容器共用的 `postgres:18` tag 一併移除（image 層本身還在，只是 untagged，真實容器當下不受影響，仍 `Up`）。發現後已用 `docker tag <相同 image ID> postgres:18` 復原，`docker images` 確認 tag 已指回真實容器實際使用的那個 image ID，未影響任何運行中容器或資料。
- 真實庫 `daily_ml_features`／`stock_prices` 執行後仍為 449,263（唯讀 `psql` 查詢確認），全程未被本次演練觸碰。

## 九、結論

十項清單：8 項乾淨 PASS，1 項（第 3 項，暖機期 NULL 分類）技術面成立但同時實證了成因 F 接線
缺口，1 項（md5，PO 已裁決排除 NVDA 後 458 檔台股 PASS）。標籤算術、七張表 diff、尾端掛點列數
全部精確核對通過。RISK-027/023 最擔心的覆寫風險確認未發生。兩項 PO 裁決已落實到
expectations.json；成因 F 接線小案已排進真實首跑後的候補清單，優先於雙時點排程小案。
