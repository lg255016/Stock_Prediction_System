# FEATURE_REGISTRY.md — 特徵登記冊（單一真實來源）

> **Gate 0 交付物 C**
> 日期: 2026-08-22
> 狀態: READY FOR PO REVIEW

---

## 1. 版本化契約總覽

| 契約版本 | 模型輸入數 | 說明 | 階段 |
|---|---|---|---|
| **LEGACY_17** | 17 | 當前程式碼行為：5 OHLCV + 12 衍生特徵。包含 open/high/low 作為模型輸入。 | 現行（待淘汰） |
| **CORE_16** | 16 | 升級目標：移除 open/high/low，保留 12 既有衍生特徵 + 新增 4 個平穩化特徵。 | 計劃中 |
| **COMMENT_ENHANCED_19** | 19 | CORE_16 + 3 個留言互動特徵 (comment_volume_ratio, comment_polarization, net_push_momentum)。 | 計劃中 |

### 契約演進路徑

```
LEGACY_17 (現行)
  │  移除 open_price, high_price, low_price (-3)
  │  保留 close_price, volume, return_1d, rsi_14, volatility_5d, volatility_20d,
  │        article_count, sentiment_mean, bullishness_index, agreement_index,
  │        sentiment_3d_ma, sentiment_5d_ma, sentiment_lag_1, sentiment_lag_2 (14)
  │  新增 amplitude_ratio, ma5_bias_ratio, ma20_bias_ratio, volume_ratio_5d (+4)
  │  移除 close_price, volume (非平穩，改用衍生形式) (-2)
  ▼
CORE_16 (升級目標)
  │  新增 comment_volume_ratio, comment_polarization, net_push_momentum (+3)
  ▼
COMMENT_ENHANCED_19 (最終目標)
```

---

## 2. 29 欄位資料契約（daily_ml_features 目標 Schema）

Feature Store `daily_ml_features` 表共 **29 欄位**，組成如下：

| 分類 | 數量 | 說明 |
|---|---|---|
| Identifier（識別欄位） | 2 | trade_date, stock_id |
| Context（上下文欄位） | 2 | close_price, volume — 保留供回測與 BI，不作為 CORE_16 模型輸入 |
| **Metadata / Lineage（血緣欄位）** | **2** | **source_status, label_reason — 資料品質與標籤成因追蹤，非模型輸入** |
| Engineered Feature（工程特徵） | 19 | 模型輸入候選池 |
| Target（預測目標） | 4 | target_next_close, target_return_1d, target_up_down, target_triple_barrier |
| **合計** | **29** | |

> **為何需要 Metadata 欄位**：沒有 `source_status`，資料庫層無法區分「該日確實沒新聞」
> 與「PTT 掛了」，`SOURCE_FAILED → 特徵 NULL → 排除訓練` 的契約無從執行。
> 沒有 `label_reason`，三種 NULL 標籤成因在 DB 裡是同一個 NULL，
> Ambiguous Ratio 報告（`PURGED_WALK_FORWARD_SPEC.md` §6）與 RISK-011 的 10% 觸發條件都算不出來。

---

## 3. 完整特徵登記表（29 欄位 x 12 屬性）

> **編號說明**：本章表格的 `#` 欄一律為 **DB 欄位序號（1-29）**，
> 對應 `daily_ml_features` 的 29 欄資料契約，**不是**模型輸入索引。
> 模型輸入索引（各契約內 1..N）另見 §3.7 對照表。
> 所有文件引用特徵編號時必須註明使用哪一套，避免 V7 曾出現的三套編號互不對應。

### 3.1 Identifier 欄位（2 欄）

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 1 | `trade_date` | identifier | ALL | 交易日期（主鍵之一） | stock_prices.trade_date | T 已知 | 有效交易日 | NOT NULL (PK) | `DATE` | false | VERIFIED | `test_model_trainer.py` |
| 2 | `stock_id` | identifier | ALL | 股票代碼（主鍵之一） | stock_prices.stock_id | T 已知 | 有效代碼字串 | NOT NULL (PK) | `TEXT` | false | VERIFIED | `test_model_trainer.py` |

### 3.2 Context 欄位（2 欄）

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 3 | `close_price` | context | LEGACY_17 input; CORE_16 context only | 當日收盤價 | stock_prices.close_price | T 已知（盤後模式） | > 0 | NOT NULL — 無收盤價即無該交易日記錄 | `NUMERIC(10,2)` | LEGACY_17: true; CORE_16: false | VERIFIED | `test_model_trainer.py:L18-41` |
| 4 | `volume` | context | LEGACY_17 input; CORE_16 context only | 當日成交量 | stock_prices.volume | T 已知 | >= 0 | fillna(0) | `BIGINT` | LEGACY_17: true; CORE_16: false | VERIFIED | `test_model_trainer.py:L18-41` |

### 3.2A Metadata / Lineage 欄位（2 欄）

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 5 | `source_status` | metadata | ALL | 該 (trade_date, stock_id) 列社群情緒輸入的彙總狀態 | 由 ETL pipeline 依各來源回傳狀態彙總 | T 已知 | `{'SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED', 'SOURCE_FAILED'}` | NULL 僅在 Migration 後尚未回填期間；上線後應恆為非 NULL | `TEXT` + CHECK | **false** | `PLANNED` | `test_source_status_domain`, A8-3, A6 前置 |
| 6 | `label_reason` | metadata | ALL | `target_triple_barrier` 為 NULL 時的成因 | 由 `src/ml/triple_barrier.py::generate_triple_barrier_labels()` 寫入（`UG-G3-SB1`）；`db_writer.py::upsert_ml_features()` **不動此欄**（`ON CONFLICT DO UPDATE SET` 排除，CHAL-010） | T 未知（與標籤同時產生） | `{'ambiguous_dual_barrier', 'insufficient_data', 'no_entry'}` 或 NULL | NULL = 標籤正常生成 | `TEXT` + CHECK | **false** | **已實作，真實庫已寫入**（2026-09-09，`postgres`@`localhost:5432`，`UG-G3-SB1` 首次寫入 3,713 列，commit `b24fc01`→`d2e3f27`→`874b3bf`→`efd0205`，證據見 `doc/upgrade/gates/evidence/UG_G3_SB1_real_db_write.json`；**2026-09-11 `UG-G3-SB2a` 段 3 對 458＋NVDA 檔全部重算，現為全部 449,263 列**，commit `837a0c0`，證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage3_labels_write.json`） | `tests/test_triple_barrier.py`（T-TB-04/05/09/15/16/17，見 `PURGED_WALK_FORWARD_SPEC.md` §5.2） |

**不變式**：`label_reason IS NOT NULL` ⟺ `target_triple_barrier IS NULL`（標籤已計算的前提下）。
由 DB CHECK constraint `chk_label_reason_consistency` 強制（`DB_MIGRATION_PLAN.md` §4.2）。

### 3.3 Engineered Features — 既有衍生特徵（12 欄）

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 7 | `return_1d` | feature | LEGACY_17, CORE_16 | `ln(close_t / close_{t-1})` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` | T 已知 | (-inf, +inf)；實務 [-0.1, +0.1] | fillna(0.0)；首日無前日價格 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 8 | `rsi_14` | feature | LEGACY_17, CORE_16 | Wilder's RSI(14)：`100 - 100/(1+RS)` | `feature_aggregator.py::compute_rsi()` | T 已知 | [0.0, 100.0] | fillna(50.0)；暖機期 < 14 日補中立值 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 9 | `volatility_5d` | feature | LEGACY_17, CORE_16 | 5 日滾動年化波動率：`std(return_1d, window=5) * sqrt(252)` | `feature_aggregator.py::compute_rolling_volatility()` | T 已知 | [0.0, +inf) | fillna(0.0)；暖機期 < 2 日 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 10 | `volatility_20d` | feature | LEGACY_17, CORE_16 | 20 日滾動年化波動率：`std(return_1d, window=20) * sqrt(252)` | `feature_aggregator.py::compute_rolling_volatility()` | T 已知 | [0.0, +inf) | fillna(0.0)；暖機期 < 2 日 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 11 | `article_count` | feature | LEGACY_17, CORE_16 | 當日情緒文章總篇數（直接 + 題材溢出） | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` | T 已知 | [0, +inf) 整數 | fillna(0) | `INTEGER` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 12 | `sentiment_mean` | feature | LEGACY_17, CORE_16 | 加權融合情緒均值：70% 直接 + 30% 題材（僅一方時 100%） | `feature_aggregator.py::FeatureAggregator.generate_daily_features()`（融合規則實作於其內的巢狀函式 `_fuse_sentiment`——依 `DEC-044`，錨點只指到外層方法，巢狀函式不當作獨立錨點） | T 已知 | [0.0, 1.0] | fillna(0.5)（中立） | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 13 | `bullishness_index` | feature | LEGACY_17, CORE_16 | Antweiler & Frank (2004)：`ln((1 + pos) / (1 + neg))` | `feature_aggregator.py::compute_bullishness_index()` | T 已知 | (-inf, +inf) | fillna(0.0) | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 14 | `agreement_index` | feature | LEGACY_17, CORE_16 | Antweiler & Frank (2004)：`1 - sqrt(1 - ((pos-neg)/(pos+neg))^2)` | `feature_aggregator.py::compute_agreement_index()` | T 已知 | [0.0, 1.0] | fillna(0.0) | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 15 | `sentiment_3d_ma` | feature | LEGACY_17, CORE_16 | `rolling_mean(sentiment_mean, window=3, min_periods=1)` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` | T 已知 | [0.0, 1.0] | min_periods=1，首日即可計算 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 16 | `sentiment_5d_ma` | feature | LEGACY_17, CORE_16 | `rolling_mean(sentiment_mean, window=5, min_periods=1)` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` | T 已知 | [0.0, 1.0] | min_periods=1，首日即可計算 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 17 | `sentiment_lag_1` | feature | LEGACY_17, CORE_16 | `sentiment_mean_{t-1}` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` | T 已知（使用昨日值） | [0.0, 1.0] | fillna(0.5)；首日無前日 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |
| 18 | `sentiment_lag_2` | feature | LEGACY_17, CORE_16 | `sentiment_mean_{t-2}` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` | T 已知（使用前日值） | [0.0, 1.0] | fillna(0.5)；首兩日無前日 | `NUMERIC` | true | VERIFIED | `test_thematic_feature_spillover.py:L155` |

### 3.4 Engineered Features — CORE_16 新增平穩化特徵（4 欄）

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 19 | `amplitude_ratio` | feature | CORE_16 | `(High - Low) / Close` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()`（UG-G2-SB8 已實作） | T 已知 | [0.0, +inf)；典型值 0.01-0.10 | **保持 NULL**（DEC-030 決策點 1，2026-08-31 修正——原為 `fillna(0.0)`）：本欄三個輸入全部來自同一列，**成因 W 在結構上不可能發生**，該填補唯一可能觸發的情境是 high/low 取不到，那是**成因 F**，§5A.1 明文禁止填補。且 `0.0` 的語意是 `High == Low`（漲跌停鎖死）——真實觀測，非「無資料」 | `NUMERIC` | true | VERIFIED | `tests/test_stationarity_features.py` |
| 20 | `ma5_bias_ratio` | feature | CORE_16 | `(Close - MA5) / MA5`（**MA 含當日**，標準均線偏離率。與 `volume_ratio_5d` 的 `t-5..t-1` 基準**刻意不對稱**：兩者測的是不同東西，前者是**水位比較**、後者是**異常偵測**，基準含當日會讓今日成交量出現在自己的分母裡而壓抑要偵測的訊號；此不對稱為明寫的設計，非疏漏。DEC-030） | `feature_aggregator.py::FeatureAggregator.generate_daily_features()`（UG-G2-SB8 已實作） | T 已知 | (-inf, +inf)；典型值 [-0.1, +0.1] | fillna(0.0)；暖機期 < 5 日（成因 W）。**本策略尚未定案**——`0.0` 的語意是「收盤價恰好等於均線」，在值域 `(-inf, +inf)` 裡那是一個**事件**而非結構中點（對照 `rsi_14 → fillna(50.0)` 的 50 是 `[0,100]` 的結構中點）。同一批評涵蓋已上線的 `return_1d` 與 `volatility_5d/20d`，故不在 `UG-G2-SB8` 決定。**見 RISK-020，Gate 3 啟動前必須裁決。** | `NUMERIC` | true | VERIFIED | `tests/test_stationarity_features.py` |
| 21 | `ma20_bias_ratio` | feature | CORE_16 | `(Close - MA20) / MA20`（**MA 含當日**，標準均線偏離率。與 `volume_ratio_5d` 的 `t-5..t-1` 基準**刻意不對稱**：兩者測的是不同東西，前者是**水位比較**、後者是**異常偵測**，基準含當日會讓今日成交量出現在自己的分母裡而壓抑要偵測的訊號；此不對稱為明寫的設計，非疏漏。DEC-030） | `feature_aggregator.py::FeatureAggregator.generate_daily_features()`（UG-G2-SB8 已實作） | T 已知 | (-inf, +inf)；典型值 [-0.2, +0.2] | fillna(0.0)；暖機期 < 20 日（成因 W）。**本策略尚未定案**——`0.0` 的語意是「收盤價恰好等於均線」，在值域 `(-inf, +inf)` 裡那是一個**事件**而非結構中點（對照 `rsi_14 → fillna(50.0)` 的 50 是 `[0,100]` 的結構中點）。同一批評涵蓋已上線的 `return_1d` 與 `volatility_5d/20d`，故不在 `UG-G2-SB8` 決定。**見 RISK-020，Gate 3 啟動前必須裁決。** | `NUMERIC` | true | VERIFIED | `tests/test_stationarity_features.py` |
| 22 | `volume_ratio_5d` | feature | CORE_16 | `Volume / MA5_Vol`（**MA5_Vol 不含當日**，基準為 `t-5..t-1`——與 bias ratio 的含當日**刻意不對稱**，見 `ma5_bias_ratio` 列。DEC-030） | `feature_aggregator.py::FeatureAggregator.generate_daily_features()`（UG-G2-SB8 已實作） | T 已知 | [0.0, +inf)；典型值 0.5-3.0 | **暖機期（不足 5 日基準）→ `fillna(1.0)`（成因 W）；`MA5_Vol == 0` → 保持 NULL（成因 U）**（DEC-030 決策點 3，2026-08-31 修正——原文「`fillna(1.0)`；暖機期分母為零時」把兩種不同成因寫成同一件事）。基準採 `t-5..t-1`（不含當日），沿用 §5.2 同族慣例 | `NUMERIC` | true | VERIFIED | `tests/test_stationarity_features.py` |

### 3.5 Engineered Features — COMMENT_ENHANCED_19 留言特徵（3 欄）

> **NULL 規則（以 Master Plan §4.3 為準）**：留言功能尚未啟用、當日無留言資料，或來源狀態為 `SOURCE_FAILED` 時，
> 這三個欄位一律保持 `NULL`，**不得** fillna 成 0、1.0 或任何中立值。
> 理由：把「沒有留言資料」補成具體數值，等同於讓模型讀到不存在的訊號（違反 AGENTS.md §7.1 失敗語意原則）。
> 含 NULL 的樣本在 COMMENT_ENHANCED_19 契約下排除訓練；在 CORE_16 契約下這三欄不參與，不影響樣本可用性。

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 23 | `comment_volume_ratio` | feature | COMMENT_ENHANCED_19 | `total_comments_t / (rolling_mean(total_comments, t-5..t-1) + 1)` | 待實作；需留言數時序 | T 已知 | [0.0, +inf)；典型值 0.5-3.0 | **保持 NULL**（未啟用／無留言／SOURCE_FAILED／暖機期不足 1 日／`suspect`——`comment_seq` 時間回退，RISK-029、DEC-039） | `NUMERIC` | true | PLANNED | — |
| 24 | `comment_polarization` | feature | COMMENT_ENHANCED_19 | `1 - push_ratio_t^2`；push_ratio 為共用中間值，非儲存欄位 | 待實作；衍生自 push_ratio | T 已知 | [0.0, 1.0] | **保持 NULL**（未啟用／無推噓資料／SOURCE_FAILED／`suspect`——RISK-029、DEC-039） | `NUMERIC` | true | PLANNED | — |
| 25 | `net_push_momentum` | feature | COMMENT_ENHANCED_19 | `push_ratio_t - push_ratio_{t-1}`；push_ratio 為共用中間值，非儲存欄位 | 待實作；需 PTT 推噓資料 | T 已知 | (-2.0, 2.0) | **保持 NULL**（未啟用／無推噓資料／SOURCE_FAILED／首日無前日 push_ratio／`suspect`——RISK-029、DEC-039） | `NUMERIC` | true | PLANNED | — |

### 3.6 Target 欄位（4 欄）

| # | Column | Role | Contract | Formula | Source | Prediction-Time Available | Range | NULL Handling | PG Type | model_input | Status | Test Ref |
|---|--------|------|----------|---------|--------|---------------------------|-------|---------------|---------|-------------|--------|----------|
| 26 | `target_next_close` | target | ALL | `close_price_{t+1}` — shift(-1) | `feature_aggregator.py::FeatureAggregator.generate_target_labels()` | T 未知（未來資料） | > 0 | NaN：最後一日無未來價格 | `NUMERIC(10,2)` | false | VERIFIED | `test_model_trainer.py` |
| 27 | `target_return_1d` | target | ALL | `ln(Close_{T+1} / Close_T)` | `feature_aggregator.py::FeatureAggregator.generate_target_labels()` | T 未知 | (-inf, +inf) | NaN：最後一日 | `NUMERIC` | false | VERIFIED | `test_model_trainer.py` |
| 28 | `target_up_down` | target | ALL | `1 if r > 0 else 0` | `feature_aggregator.py::FeatureAggregator.generate_target_labels()` | T 未知 | {0, 1} | NaN：最後一日 | `INTEGER` | false | VERIFIED | `test_model_trainer.py` |
| 29 | `target_triple_barrier` | target | ALL | Triple-Barrier 三分類；anchor = `Open[T+1]`，評估區間 T+1~T+5。1=止盈, -1=止損, 0=Timeout | `src/ml/triple_barrier.py::generate_triple_barrier_labels()`（`UG-G3-SB1`，新建，非 `feature_aggregator.py`——標籤生成獨立於既有特徵聚合流程）；規格見 `PURGED_WALK_FORWARD_SPEC.md` §4；`db_writer.py::upsert_ml_features()` **不動此欄**（`ON CONFLICT DO UPDATE SET` 排除，CHAL-010——每日特徵 upsert 曾會把既有標籤覆寫成 NULL） | T 未知 | **`{-1, 0, 1}` 或 NULL** | NULL：同日觸雙線 / 剩餘天數不足 H（即使窗口內已觸線亦同，PO 2026-09-09 裁定）/ `Open[T+1]` 不存在或為 NaN | `INTEGER` | false | **已實作，真實庫已寫入**（2026-09-09，`postgres`@`localhost:5432`，`UG-G3-SB1` 首次寫入 3,713 列，`float64`→`Int64`→`INTEGER` 轉型確認正確，證據見 `doc/upgrade/gates/evidence/UG_G3_SB1_real_db_write.json`；**2026-09-11 `UG-G3-SB2a` 段 3 對 458＋NVDA 檔全部重算，現為全部 449,263 列**，分布 `-1`226,956／`0`21,199／`1`162,288，`label_reason` 分布 `ambiguous_dual_barrier`36,388／`insufficient_data`1,892／`no_entry`540，commit `837a0c0`，證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage3_labels_write.json`） | `tests/test_triple_barrier.py`（T-TB-01~17，見 `PURGED_WALK_FORWARD_SPEC.md` §5.2） |

### 3.7 DB 欄位序號 ↔ 模型輸入索引對照

> 解決 V7 遺留的「三套編號互不對應」問題。以下為唯一權威對照表。

| DB # | Column | LEGACY_17 idx | CORE_16 idx | COMMENT_ENHANCED_19 idx |
|------|--------|:-------------:|:-----------:|:-----------------------:|
| — | `open_price` (在 `stock_prices`) | 1 | — | — |
| — | `high_price` (在 `stock_prices`) | 2 | — | — |
| — | `low_price` (在 `stock_prices`) | 3 | — | — |
| 3 | `close_price` | 4 | — (context) | — (context) |
| 4 | `volume` | 5 | — (context) | — (context) |
| 7 | `return_1d` | 6 | 1 | 1 |
| 8 | `rsi_14` | 7 | 2 | 2 |
| 9 | `volatility_5d` | 8 | 3 | 3 |
| 10 | `volatility_20d` | 9 | 4 | 4 |
| 11 | `article_count` | 10 | 5 | 5 |
| 12 | `sentiment_mean` | 11 | 6 | 6 |
| 13 | `bullishness_index` | 12 | 7 | 7 |
| 14 | `agreement_index` | 13 | 8 | 8 |
| 15 | `sentiment_3d_ma` | 14 | 9 | 9 |
| 16 | `sentiment_5d_ma` | 15 | 10 | 10 |
| 17 | `sentiment_lag_1` | 16 | 11 | 11 |
| 18 | `sentiment_lag_2` | 17 | 12 | 12 |
| 19 | `amplitude_ratio` | — | 13 | 13 |
| 20 | `ma5_bias_ratio` | — | 14 | 14 |
| 21 | `ma20_bias_ratio` | — | 15 | 15 |
| 22 | `volume_ratio_5d` | — | 16 | 16 |
| 23 | `comment_volume_ratio` | — | — | **17** |
| 24 | `comment_polarization` | — | — | **18** |
| 25 | `net_push_momentum` | — | — | **19** |
| **合計 model_input** | | **17** | **16** | **19** |

非模型輸入欄位（不出現在上表 idx 欄）：`trade_date`(1)、`stock_id`(2)、`source_status`(5)、`label_reason`(6)、4 個 target(26-29)。

---

## 4. OHLC 遷移說明

### 現況（LEGACY_17）

`ALL_MULTIMODAL_FEATURE_COLS` 定義於 `src/ml/model_trainer.py:18-41`，包含 17 個模型輸入：

```python
ALL_MULTIMODAL_FEATURE_COLS = [
    "open_price", "high_price", "low_price",    # <-- 待移除
    "close_price", "volume",                     # <-- CORE_16 降級為 context
    "return_1d", "rsi_14",
    "volatility_5d", "volatility_20d",
    "article_count", "sentiment_mean",
    "bullishness_index", "agreement_index",
    "sentiment_3d_ma", "sentiment_5d_ma",
    "sentiment_lag_1", "sentiment_lag_2",
]
```

`TECHNICAL_FEATURE_COLS` 定義於 `src/ml/baseline_models.py:10-20`，包含 9 個純價量輸入。

### 遷移規則

| 欄位 | 現行位置 | 目標位置 | 遷移動作 |
|------|---------|---------|---------|
| `open_price` | stock_prices + Feature Store + 模型輸入 | stock_prices only | 從 daily_ml_features 移除；從 ALL_MULTIMODAL_FEATURE_COLS 移除 |
| `high_price` | stock_prices + Feature Store + 模型輸入 | stock_prices only | 同上 |
| `low_price` | stock_prices + Feature Store + 模型輸入 | stock_prices only | 同上 |
| `close_price` | stock_prices + Feature Store + 模型輸入 | stock_prices + Feature Store (context) | 保留於 daily_ml_features 供回測，但從 CORE_16 模型輸入中移除 |
| `volume` | stock_prices + Feature Store + 模型輸入 | stock_prices + Feature Store (context) | 保留於 daily_ml_features 供回測，改用 volume_ratio_5d 作為模型輸入 |

### 理由

1. **非平穩性**：open/high/low/close 為名目價格，跨股票不可比較，且隨時間漂移，不利於機器學習泛化。
2. **多重共線性**：open/high/low 與 close 高度相關（典型 r > 0.99），提供的獨立資訊極少。
3. **替代方案**：`return_1d`、`amplitude_ratio`、`ma5_bias_ratio`、`ma20_bias_ratio`、`rsi_14`、`volatility_5d`、`volatility_20d`、`volume_ratio_5d` 以平穩化衍生形式捕捉相同的價格動態。

---

## 5. 留言特徵公式（Comment Feature Formulas）

以下 3 + 1 個留言特徵公式定義，適用於 COMMENT_ENHANCED_19 契約：

### 5.1 Push Ratio（推噓比）

```
push_ratio_t = (push_t - boo_t) / (push_t + boo_t + 1)
```

- **push_t**: 當日推文數（正面留言）
- **boo_t**: 當日噓文數（負面留言）
- **+1**: Laplace 平滑，防止零除錯誤
- **值域**: (-1.0, 1.0)，正值表示看多主導，負值表示看空主導

### 5.2 Comment Volume Ratio（留言量比）

```
comment_volume_ratio_t = total_comments_t / (rolling_mean(total_comments, t-5..t-1) + 1)
```

- **total_comments_t**: 當日留言總數（推 + 噓 + 箭頭）
- **rolling_mean(...)**: 過去 5 個交易日的留言均值，僅使用 t-5..t-1 已知資料
- **+1**: 防止零除
- **值域**: [0.0, +inf)，> 1.0 表示留言量異常放大
- **暖機期**: 首日無任何歷史留言基準時 → **保持 NULL**，不填補
- **NULL 條件**: 留言功能未啟用、當日無留言資料、來源狀態 `SOURCE_FAILED`、暖機期不足 1 日

### 5.3 Comment Polarization（留言極化度）

> **【RISK-018，2026-08-30】本公式無法區分「真實兩極對立」與「無方向訊號」。**
> `push=5, boo=5`（真實對半）與 `push=0, boo=0`（全中立留言）
> **都得到 `polarization = 1.0`**，且都是該指標的最大值。
> 這與 §5.7 修掉的偽造訊號是同一個形狀，只是從另一道門進來——
> 而且**今天就會在真實 PTT 資料上發生，不需要第二個來源**。
> **Gate 3 啟動前必須裁決**；裁決前不得將本特徵當作可信的模型輸入。
> 見 `REMAINING_RISKS.md` RISK-018。

```
comment_polarization_t = 1 - push_ratio_t^2
```

- 衍生自 push_ratio，衡量意見分歧程度
- **值域**: [0.0, 1.0]
- push_ratio 接近 0 時（多空均衡），polarization 接近 1.0（最大分歧）
- push_ratio 接近 +/-1 時（一面倒），polarization 接近 0.0（高度共識）
- **NULL 條件**: 留言功能未啟用、當日無推噓資料、來源狀態 `SOURCE_FAILED`

### 5.4 Net Push Momentum（淨推文動量）— COMMENT_ENHANCED_19 模型輸入

```
net_push_momentum_t = push_ratio_t - push_ratio_{t-1}
```

- 衡量推噓比的日變化率
- **值域**: (-2.0, 2.0)
- push_ratio 為共用中間值（非儲存欄位），net_push_momentum 為 COMMENT_ENHANCED_19 的第 3 個留言特徵模型輸入
- **NULL 條件**: 留言功能未啟用、當日或前一日無推噓資料、來源狀態 `SOURCE_FAILED`

### 5.5 留言計數的時點有效性（Temporal Validity）— UG-G2-SB4 落定 DEC-024，2026-09-14 由 DEC-039 修訂

留言數與情緒分數有本質差異：**情緒分數算的是標題，標題在發文當下就定案、之後不會變；
留言數會持續累積**。因此留言計數必須額外滿足時點條件才可用於特徵計算。

**判準**（DEC-024，判準本身不變，DEC-039 只改變判斷粒度）：

> 一個特徵值是否構成前視偏誤，看的**不是**「它是不是發文那天的數字」，
> 而是「**它在被歸屬的那個交易日的決策時點，是不是已經看得到了**」。

- **決策時點** = `combine(trade_date, cutoff_time)`，以 `(article, stock_id)` 列為單位
  （同一篇文章對到不同股票可能有不同 `trade_date`／決策時點，RISK-027 之後）。
- Roll-Forward Mapping 本來就會把週五盤後與週末的文章歸屬到週一，
  因此**週一早上爬到的留言數屬於週一決策時點的合法可見資訊，不是洩漏**。
- 模型應當學到「假日後的開盤日留言數天生較多」這種真實、可得的規律，不應抹除。

**【2026-09-14 訂正，DEC-039】** RISK-023 診斷發現：本專案實際排程（`scheduler.py`
每日僅 15:35 執行一次）下，文章層級 `comments_scraped_at <= 決策時點` 過濾在穩定
運作時通過率僅約 0.2%——「`NULL` 應為少數」這個原始預期**結構性不成立**。
判準改為**逐則時間戳重算**：

| # | 機制 | 位置 | 說明 |
|---|------|------|------|
| 1 | `comments_scraped_at` 欄位 | `market_articles`（Migration 004） | 保留，角色限縮為稽核用途（「這篇文章是否已完成擷取」的旗標來源），不再是特徵計算依賴的資料來源 |
| 2 | `write-once` | `db_writer.update_comment_counts()` 的 `AND total_comments IS NULL` | 保留，供 `market_articles` 聚合欄位（稽核用途）的一致性保護 |
| 3 | **逐則重算**（現行核心機制） | `feature_aggregator._aggregate_direct_comment_counts()` 呼叫 `comment_timeline.counts_as_of()` | 已擷取旗標＝`total_comments IS NOT NULL`；對每個 `(article, stock_id)` 列，取該文章的 `article_comments` 逐則留言，以該列自己的決策時點呼叫 `counts_as_of()` |
| 4 | 落界排除 | `comment_timeline.validate_comment_bounds()` | `comment_time` 落在 `[post_time, comments_scraped_at]` 之外的留言不計入任何一格 |
| 5 | `suspect` 守衛（RISK-029） | `comment_timeline.is_time_reset()` | 該篇留言依 `comment_seq` 排序後時間戳出現回退，整篇標記 `suspect`，涉及列留言三欄一律 `NULL`（不去重） |

**本條規則適用於所有時間性會變動的特徵**（未來的 Dcard 留言、按讚數、轉發數等），
不限於 PTT 推噓文。詳見 DEC-039、`doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md`。

### 5.5A 交易日曆的建構範圍（Per-Stock，非全市場聯集）— RISK-027 方案 B，DEC-037

§5.5 的 Roll-Forward Mapping 所依賴的交易日曆，**依每篇文章實際歸屬的股票自身在
`stock_prices` 的 `trade_date` 集合建構，不對輸入涵蓋的所有股票取聯集**。

- **成因**：全市場聯集日曆會把「任一檔有交易」誤判為「該日不是假日」。跨市場輸入
  （例如同批含台股與 NVDA）時，台股假期文章會被滾動到一個台股根本不存在的交易日，
  與該股價格表合併時靜默流失（`RISK-027`，`MITIGATED`；見
  `doc/evidence/CHALLENGES.md` CHAL-011）。
- **實作**：`src/transform/feature_aggregator.py::assign_trading_days_per_stock()`。
  呼叫端須先將文章展開成 `(article, stock_id)` 列（直接路由或題材溢出皆同一規則），
  **再**依該列 `stock_id` 對應的日曆做 Roll-Forward——順序是承重的，
  不能像修復前那樣在合併之前就用單一聯集日曆決定 `trade_date`。
- **不變性判準**：混合市場輸入下每檔股票的輸出，必須等於該檔單獨輸入時的輸出，
  見 `tests/test_risk027_cross_market_calendar.py`
  的 `test_mixed_market_input_matches_single_market_input_for_each_stock`。
- 決策見 DEC-037。

### 5.6 留言計數的聚合範圍（Aggregation Scope）— UG-G2-SB4 落定，DEC-025

`push_count` 等為 per-article，留言特徵為 per (trade_date, stock_id)，中間的聚合
**只採用直接個股文章；題材溢出文章（DEC-009）的留言數不計入其成分股**。

**理由**：`comment_polarization` 與 `net_push_momentum` 都是 `push_ratio` 的函數，
一篇題材文章的留言若計入 N 檔成分股，這 N 檔的這兩個特徵會幾乎完全相同——
模型會看到 N 筆看似獨立、實則同源的樣本，**製造假的橫斷面相關性，比 `NULL` 有害**。

**與 DEC-009 情緒 70/30 加權的區別**：情緒是**方向訊號**，可以外溢（題材看多，
成分股通常受益）；留言數量是**量級**，「這篇題材文有 500 則留言」不等於
「每檔成分股各獲得 500 則討論」。兩者性質不同，不因同屬社群特徵而套用同一聚合規則。

**代價**：無直接個股文章的 (交易日, 股票) 其三個留言特徵為 `NULL`；
小型概念股（多半只有題材討論）覆蓋率會偏低——與 RISK-015 同向，已知並接受。

---

## 5A. 全欄位 NULL 語意規則（Universal NULL Semantics）

> **V8 升級**：V7 的 §5.5 只涵蓋留言三欄，導致情緒六欄的同型缺陷未被發現。
> 本章升級為**全欄位規則**，適用於 `daily_ml_features` 的所有 19 個 engineered feature。

### 5A.1 三種 NULL 成因必須嚴格區分

> **【2026-09-05 更正】本標題原寫「兩種」，而它自己的下一行寫的是「三者之一」。**
> §5A.1 的**內文**已於 2026-08-31 依 DEC-030 修訂並新增第三種成因 `U`，
> **但標題沒有跟著改** —— 從那天起標題與內文互相矛盾。
>
> **這是「本體改了、摘要沒改」的又一次，而這一次摘要是章節標題 ——
> 它是最多人只看一眼的那一行。**
>
> 改標題**不是對 Gate 0 交付物的新變更**：內文已在 DEC-030 的授權下修過，
> **本次只是把那次修訂做完。**

任何欄位出現空值，成因**必為**以下四者之一，且處理方式**完全不同**：

> **【2026-09-14 追加，DEC-039，RISK-029】本節原為「三者之一」，本次新增第四種 S。**
> 沿用 DEC-030 當時的教訓——**表格寫過不等於窮盡過**：本次是留言特徵新增
> `comment_seq` 時間回退偵測（`suspect` 守衛）時撞到，該情境不是 W（資料不是
> 暖機期不足）、不是 F（資料確實擷取到了）、也不是 U（不是數學未定義），
> 是**資料本身內部不一致、可信度存疑**，需要第四種成因。

> **【2026-08-31 修正，DEC-030】本節原文寫的是「只可能是以下兩種成因之一」。**
> 那個窮盡性宣稱**被 `volume_ratio_5d` 的 `MA5_Vol == 0` 這一格證偽**：
> 它不是 W（視窗是足的，資料確實存在），也不是 F（資料取得了，就是 0）。
> **它是第三種：資料齊備、視窗足夠，但公式在數學上未定義。**
> 這個缺口是 `UG-G2-SB8` 逐欄檢視四個平穩化特徵的 `fillna` 時撞到的——
> **契約寫過不等於契約想過**：那四欄的 NULL 策略是在四欄都還沒實作時寫的。

| 成因 | 定義 | 處理方式 | 訓練處理 |
|------|------|----------|----------|
| **W — 暖機期不足**<br>(Warm-up) | 資料**確實存在**，但時序視窗尚未累積足夠歷史（如首日無前日價格、RSI 需 14 日） | **允許填補**中立值（見 §5A.3 對照表） | 樣本可用 |
| **F — 來源失敗**<br>(`SOURCE_FAILED`) | 資料**根本沒取得**，來源不可達 | **必須保持 NULL**，嚴禁任何填補 | **排除訓練** |
| **U — 數學未定義**<br>(Undefined)<br>**2026-08-31 新增，DEC-030** | 資料**齊備、視窗足夠**，但公式在該點**數學上未定義**（零除等）。例：`volume_ratio_5d` 的 `MA5_Vol == 0`（過去 5 日完全沒有成交）；`amplitude_ratio` 的 `Close == 0` | **必須保持 NULL**，嚴禁填補——填補值必然是一個**與事實相反**的陳述（填 `1.0` 等於宣稱「今日成交量等於 5 日均量」，而事實是過去 5 日完全沒有成交） | 該列該欄不可用 |
| **S — 可疑**<br>(Suspect)<br>**2026-09-14 新增，DEC-039／RISK-029** | 資料**確實取得**，但通過某項可執行的一致性檢查後判定**內部矛盾、不可信**。例：留言特徵的 `comment_seq` 時間回退偵測（`comment_timeline.is_time_reset()`）——`article_comments` 依 `comment_seq` 排序後時間戳不是非遞減，代表擷取器單次解析產生了重複或交錯的留言區塊（見 RISK-029），逐則重算若原樣套用會虛高計數 | **必須保持 NULL**，不嘗試修復或去重——去重規則在沒有留言原文可核對的情況下只能是猜測 | 該列該欄不可用 |

> 這幾者在數學上可能落到同一個值（例如 `sentiment_mean` 暖機期填 0.5，來源失敗也「看起來像」0.5），
> 但語意完全不同：前者是「已知的中立」，後者是「未知」。
> 把後者填成前者，等同於讓模型讀到一個從未觀測到的訊號 —— 這正是 AGENTS.md §7.1 禁止的行為。
> **S 與 F 的區別**：F 是「根本沒取得資料」，S 是「取得了資料，但資料本身自相矛盾」——
> 兩者都導向 NULL、都排除訓練，但成因不同：F 需要重新擷取才能解決，
> S 需要先定位並修復產生矛盾資料的根因（RISK-029）才可能恢復可用性。

### 5A.2 判定流程

```
對每個 (trade_date, stock_id) 列的每個 engineered feature：

    if source_status == 'SOURCE_FAILED':
        → 所有「情緒／留言來源」欄位一律 NULL（成因 F）
        → 價量衍生欄位不受影響（來源是 stock_prices，非社群來源）
        → 該列在含情緒特徵的契約下排除訓練

    elif source_status in ('SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED'):
        → 依 §5A.3 對照表處理暖機期（成因 W）
        → 若 article_count == 0（無論 SUCCESS 或 SUCCESS_EMPTY）：
            sentiment_mean 及其四個衍生欄（3d_ma／5d_ma／lag_1／lag_2）
            保持 NULL（成因 U），除非該列落在序列前 1～2 列（真暖機期，填中立值）
            article_count／bullishness_index／agreement_index 不受影響（真值）
        → 留言三欄若「未啟用／無推噓資料」仍為 NULL（成因 F 的子類）
```

> **2026-09-08 補（`PRE-G3-04`／D5，PO 2026-09-07 裁決 `5bfb3b8`）**：
> 上方 U 分支為本次新增。**判定「序列前 1～2 列」用 `groupby(stock_id).cumcount()`**，
> 不是用 `shift()` 結果是否為 `NaN`——`shift(1)` 對「真暖機期（前面沒有任何一天）」
> 與「前一天本身是空日（U 已生效）」的 `NaN` 完全無法區分，`cumcount()` 是與
> `NaN` 成因無關的獨立判準。實作見 `feature_aggregator.py` 的
> `sentiment_lag_1`／`sentiment_lag_2` 計算點。

### 5A.3 全欄位 NULL Handling 對照表

| 欄位 | 來源類別 | 成因 W（暖機期）處理 | 成因 F（`SOURCE_FAILED`）處理 |
|------|----------|---------------------|------------------------------|
| `return_1d` | 價量 | `fillna(0.0)` | 不適用（價量來源獨立） |
| `rsi_14` | 價量 | `fillna(50.0)` | 不適用 |
| `volatility_5d` / `volatility_20d` | 價量 | `fillna(0.0)` | 不適用 |
| `amplitude_ratio` | 價量 | **保持 NULL**（DEC-030；無暖機期，該欄的 NULL 只可能是 F 或 U） | 不適用 |
| `ma5_bias_ratio` / `ma20_bias_ratio` | 價量 | `fillna(0.0)` | 不適用 |
| `volume_ratio_5d` | 價量 | **W → `fillna(1.0)`；U（`MA5_Vol == 0`）→ 保持 NULL**（DEC-030） | 不適用 |
| **`article_count`** | **社群** | `fillna(0)`（空日真值，不受 U 影響） | **必須 NULL** |
| **`sentiment_mean`** | **社群** | **U（`article_count==0`）→ 保持 NULL**（2026-09-08，`PRE-G3-04`／D5，取代原 `fillna(0.5)`——空日的「情緒平均」數學上未定義，`0.5` 是編出來的） | **必須 NULL** |
| **`bullishness_index`** | **社群** | `fillna(0.0)`（空日真值，Laplace 平滑定義，不受 U 影響） | **必須 NULL** |
| **`agreement_index`** | **社群** | `fillna(0.0)`（空日真值，`Pos+Neg==0 → 0.0` 明文定義，不受 U 影響） | **必須 NULL** |
| **`sentiment_3d_ma` / `sentiment_5d_ma`** | **社群** | `min_periods=1` 漸進計算（nanmean 語意）；**窗內全為 U（空）時本身亦為 NULL**（2026-09-08，`PRE-G3-04`／D5——U 分支刻意不做同等強制清空，「窗內至少一天有真實情緒」是誠實訊號） | **必須 NULL** |
| **`sentiment_lag_1` / `sentiment_lag_2`** | **社群** | **`cumcount() < N` 判定真暖機期 → `fillna(0.5)`；非真暖機期但仍 NaN（前 N 日本身是 U 空日）→ 保持 NULL**（2026-09-08，`PRE-G3-04`／D5，取代原無條件 `fillna(0.5)`） | **必須 NULL** |
| **`comment_volume_ratio`** | **社群留言** | **不填補 — 保持 NULL** | **必須 NULL** |
| **`comment_polarization`** | **社群留言** | **不填補 — 保持 NULL** | **必須 NULL** |
| **`net_push_momentum`** | **社群留言** | **不填補 — 保持 NULL** | **必須 NULL** |

**分界說明**（三類加總 = 19 個 engineered features）：

| 類別 | 數量 | 欄位 | 成因 W | 成因 F |
|------|:----:|------|--------|--------|
| **價量** | **8** | `return_1d`, `rsi_14`, `volatility_5d`, `volatility_20d`, `amplitude_ratio`, `ma5_bias_ratio`, `ma20_bias_ratio`, `volume_ratio_5d` | 允許填補（既有已驗證行為，維持不變） | 不適用（來源為 `stock_prices`，與社群狀態無關） |
| **社群情緒** | **8** | `article_count`, `sentiment_mean`, `bullishness_index`, `agreement_index`, `sentiment_3d_ma`, `sentiment_5d_ma`, `sentiment_lag_1`, `sentiment_lag_2` | 允許填補（資料確實取得，只是時序不足） | **必須 NULL** |
| **社群留言** | **3** | `comment_volume_ratio`, `comment_polarization`, `net_push_momentum` | **保持 NULL**（留言解析尚未上線，任何值都是偽造） | **必須 NULL** |
| **合計** | **19** | | | |

> **易混淆點**：`src/ml/baseline_models.py` 的 `TECHNICAL_FEATURE_COLS` 有 **9** 個欄位，
> 因為它額外包含 `close_price` 與 `volume`。那兩欄在 29 欄契約中歸類為 **context**（非 engineered feature），
> 故此處價量類為 **8** 而非 9。兩個數字都正確，但屬於不同的分類體系。

### 5A.4 嚴禁事項

> 對任何欄位，在 `source_status == 'SOURCE_FAILED'` 時使用
> `fillna(0)`、`fillna(0.5)`、`fillna(1.0)` 或任何常數填補。
>
> 沒有取得資料是一種事實，不是一個數值。填補會讓模型讀到不存在的訊號，
> 且該訊號會系統性地出現在「爬蟲掛掉的日子」—— 形成與市場無關的偽規律。

### 5A.5 對上游 raw 層的約束

`market_articles` 的四個留言計數欄（`push_count`, `boo_count`, `neutral_count`, `total_comments`）
**不得使用 `DEFAULT 0`**（見 `DB_MIGRATION_PLAN.md` §4.3）。

| raw 層值 | 語意 | 下游留言特徵 |
|----------|------|-------------|
| `NULL` | 文章存在，留言尚未解析 | 三欄 NULL |
| `0` | 文章已解析，確實 0 則留言 | 可正當計算 |

若 raw 層使用 `DEFAULT 0`，所有歷史文章會被 backfill 成「已解析且 0 留言」，
導致 `comment_polarization = 1 - 0² = 1.0`（最大分歧）—— 一個完全偽造的強訊號。

---

### 5.7 來源能力與方向類特徵的適用範圍 — UG-G2-SB5 決策點 5 落定，DEC-028

**每個來源明確宣告它在結構上能提供什麼**，宣告表見
`src/transform/source_capabilities.py`（`COMMENT_DIRECTION_SOURCES`）。

#### 5.7.1 為什麼需要這個概念

`push_ratio`（§5.1）不是本專案設計出來的指標——**它之所以存在，
純粹是因為 PTT 的資料結構本來就提供推／噓標記**。
要讓沒有這種標記的來源產生方向，得對**每則留言的文字**做 NLP，
而本系統只對**標題**做 NLP，結構上做不到。

三個留言特徵對來源的要求因此並不相同：

| 特徵 | 需要什麼 | 無方向來源 |
|------|---------|-----------|
| §5.2 `comment_volume_ratio` | 只要**數量** | 可算，且**可跨來源相加** |
| §5.3 `comment_polarization` | 需要**方向** | **結構上不可能** → `NULL` |
| §5.4 `net_push_momentum` | 需要**方向** | **結構上不可能** → `NULL` |

#### 5.7.2 宣告的是「能不能」，不是「有沒有」

**宣告表回答的是「這個來源在結構上能不能提供方向」，
不是「這一次有沒有抓到」。**

後者是 `NULL` 的既有語意（§5A、本檔「`DEFAULT 0` 禁令」段落：
「文章存在，留言尚未解析」）。**兩者不得混用**——
用同一個值裝兩種語意，正是 `engagement_metric` 一欄兩義與
`UG-G2-SB3` `push_count` 雙語意陷阱的成因。

**未登錄的來源一律視為不提供方向。** 這個預設方向是刻意的：
漏登錄的後果是特徵為 `NULL`（**誠實地少**）；
反過來設計的後果是偽造訊號（**安靜地錯**）。

#### 5.7.3 混合來源日：方向與數量描述的是不同母體【必讀】

同日同股兼有「有方向」與「無方向」來源時：

| 特徵 | 計算基礎 |
|------|---------|
| `comment_volume_ratio` | **全部**留言 |
| `comment_polarization`／`net_push_momentum` | **只有有方向來源的那個子集** |

**實測（UG-G2-SB5 決策點 5 E2E，臨時 DB 真實讀取路徑）**：
同日 PTT 20 則（push=10, boo=2）＋ 無方向來源 200 則 →
`comment_polarization = 0.621302`（由 20 則算出）、
`comment_volume_ratio = 33.846154`（分子含 220 則）。

**這是明講的決定，不是副作用**：方向只能由有方向的資料算出，別無他法。
但兩者並列於同一列時**隱含「這是同一群人的意見」，而實際不是**——
使用這兩類特徵時必須知道它們的母體可能不同。

#### 5.7.4 兩道必須同時處理的關卡（實作註記）

把 `NULL` 壓成 `0` 的地方有**兩處**，只修一處會產生「已修復」的錯覺：

1. `fillna(0)` —— 改為依來源能力過濾。
2. `groupby().agg('sum')` —— pandas 對**全 NaN 群組預設回 `0.0`**，
   必須明確指定 **`min_count=1`**。

`total_sum` 刻意**不加** `min_count`：數量本來就該跨來源相加。

#### 5.7.5 邊界：`0` 與 `NULL` 不同，且 `polarization = 1.0` 仍可正當出現

真實零推文的 PTT 文章寫入的是整數 `0`（`ptt_scraper.py` 三個計數器以 `0` 初始化），
`push_ratio = 0` → `comment_polarization = 1.0`。
**這個 `1.0` 是正當計算結果，不是偽造訊號**——
被消除的是「來源根本沒有方向概念卻算出 1.0」那一種。
兩者在 DB 層本來就可區分（`0` vs `NULL`），會把它們壓平的只有聚合層。

> **但這個 `1.0` 本身另有問題**：§5.3 的公式使「真實推噓對半」與「全中立留言」
> 得到同一個值。本 SB 未處理——**已登記為 RISK-018，Gate 3 啟動前必須裁決**。
> 本節說明的是「哪一種 1.0 被消除了」，**不是**「剩下的 1.0 都沒問題」。

---

## 6. 測試契約（10 項斷言）

以下 10 項斷言構成 Feature Registry 的可執行驗證規範。標記 EXISTING 為已有測試覆蓋，NEW 為待實作，EXISTING → 需修改 為既有測試需依 V8 契約更新：

### A1: LEGACY_17 模型輸入數量 [EXISTING]

```python
# test_model_trainer.py — 驗證 ALL_MULTIMODAL_FEATURE_COLS 長度
assert len(ALL_MULTIMODAL_FEATURE_COLS) == 17  # 含 open/high/low (待升級為 16)
```

**現行對應**: `test_model_trainer.py:L47` — 驗證 extract 後的 DataFrame 欄位數與 ALL_MULTIMODAL_FEATURE_COLS 一致。

### A2: TECHNICAL_FEATURE_COLS 子集關係 [EXISTING]

```python
# test_baseline_models.py — 驗證 baseline 9 欄位皆為 ALL_MULTIMODAL 的子集
assert set(TECHNICAL_FEATURE_COLS).issubset(set(ALL_MULTIMODAL_FEATURE_COLS))
```

**現行對應**: `test_baseline_models.py:L83` — 隱含驗證所有欄位均可由特徵表擷取。

### A3: Feature Store Schema 欄位數 [NEW]

```python
# 驗證 daily_ml_features 表定義欄位數 = 29
assert len(DAILY_ML_FEATURES_COLUMNS) == 29

# 分類計數
assert len([c for c in REGISTRY if c.role == 'identifier']) == 2
assert len([c for c in REGISTRY if c.role == 'context'])    == 2
assert len([c for c in REGISTRY if c.role == 'metadata'])   == 2   # source_status, label_reason
assert len([c for c in REGISTRY if c.role == 'feature'])    == 19
assert len([c for c in REGISTRY if c.role == 'target'])     == 4
# 2 + 2 + 2 + 19 + 4 = 29
```

### A4: 模型輸入不含 Identifier/Metadata/Target [NEW]

```python
# 驗證 CORE_16 模型輸入不包含 identifier、metadata 或 target 欄位
IDENTIFIERS = {'trade_date', 'stock_id'}
METADATA    = {'source_status', 'label_reason'}
TARGETS     = {'target_next_close', 'target_return_1d', 'target_up_down', 'target_triple_barrier'}
assert IDENTIFIERS.isdisjoint(set(CORE_16_FEATURE_COLS))
assert METADATA.isdisjoint(set(CORE_16_FEATURE_COLS))     # metadata 絕不可入模
assert TARGETS.isdisjoint(set(CORE_16_FEATURE_COLS))

# COMMENT_ENHANCED_19 同樣不得含 metadata
assert METADATA.isdisjoint(set(COMMENT_ENHANCED_19_FEATURE_COLS))
```

### A5: OHLC 不在 CORE_16 模型輸入 [NEW]

```python
# 驗證 open/high/low 不出現在升級後的模型輸入
REMOVED_OHLC = {'open_price', 'high_price', 'low_price'}
assert REMOVED_OHLC.isdisjoint(set(CORE_16_FEATURE_COLS))
```

### A6: 特徵聚合器輸出完整性 [EXISTING → 需修改]

> **V8 修正（BLOCK-2）**：原斷言為「全欄位零 NaN」無前置條件，
> 與 `MULTI_SOURCE_DATA_CONTRACT.md` §7 的「`SOURCE_FAILED` 時情緒欄位必須 NULL」直接互斥。
> 必須加上 `source_status` 前置條件。

```python
# 欄位存在性 — 無條件成立
for col in ALL_MULTIMODAL_FEATURE_COLS:
    assert col in df_features.columns

# A6-1: 零 NaN 斷言僅適用於「來源成功」的列
SUCCESS_STATES = {'SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED'}
ok = df_features['source_status'].isin(SUCCESS_STATES)

# 價量欄位：任何狀態下都不應有 NaN（來源獨立於社群）
assert df_features[PRICE_FEATURE_COLS].isna().sum().sum() == 0

# 社群情緒欄位：僅在來源成功時要求零 NaN
assert df_features.loc[ok, SENTIMENT_FEATURE_COLS].isna().sum().sum() == 0

# A6-2: 來源失敗的列，社群情緒欄位必須全部為 NaN（反向斷言）
failed = df_features['source_status'] == 'SOURCE_FAILED'
if failed.any():
    assert df_features.loc[failed, SENTIMENT_FEATURE_COLS].isna().all().all(), \
        "SOURCE_FAILED 列的情緒欄位必須為 NULL，不得填補中立值"

# A6-3: 留言三欄不受 A6-1 約束（允許 NULL，見 A8）
```

**現行對應**: `test_thematic_feature_spillover.py:L155-159` — 需於 UG-G2-SB1 加上 `source_status` 後更新。

### A7: NULL 暖機期填補正確性 [EXISTING → 需擴充]

```python
# 成因 W（暖機期）— 允許填補，已由端到端測試覆蓋：
#   return_1d: fillna(0.0)          | rsi_14: fillna(50.0)
#   volatility_*: fillna(0.0)       | sentiment_*: fillna(0.5)
#   article_count: fillna(0)        | volume_ratio_5d: fillna(1.0)

# A7-1: 暖機期填補只在 source_status 成功時生效
ok = df_features['source_status'].isin({'SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED'})
warmup_rows = df_features.loc[ok].groupby('stock_id').head(1)   # 每檔首日
assert warmup_rows['rsi_14'].eq(50.0).all()       # 暖機期填中立值
assert warmup_rows['return_1d'].eq(0.0).all()

# A7-2: 成因 F（SOURCE_FAILED）不得套用任何暖機期填補
failed = df_features['source_status'] == 'SOURCE_FAILED'
if failed.any():
    assert not df_features.loc[failed, 'sentiment_mean'].eq(0.5).any(), \
        "SOURCE_FAILED 不得填 0.5 —— 那是暖機期的值，不是失敗的值"
    assert not df_features.loc[failed, 'article_count'].eq(0).any(), \
        "SOURCE_FAILED 不得填 0 —— 那代表『確實沒文章』"
```

> **A7 的核心**：同一個值（`sentiment_mean = 0.5`）在成因 W 下合法、在成因 F 下是偽造。
> 測試必須用 `source_status` 區分，不能只看值本身。

### A8: 留言特徵值域約束與 NULL 規則 [NEW]

```python
COMMENT_COLS = ['comment_volume_ratio', 'comment_polarization', 'net_push_momentum']

# A8-1: 值域約束僅套用於非 NULL 值（NULL 是合法狀態）
non_null = df['comment_volume_ratio'].notna()
assert (df.loc[non_null, 'comment_volume_ratio'] >= 0.0).all()

non_null = df['comment_polarization'].notna()
assert df.loc[non_null, 'comment_polarization'].between(0.0, 1.0, inclusive='both').all()

non_null = df['net_push_momentum'].notna()
assert df.loc[non_null, 'net_push_momentum'].between(-2.0, 2.0, inclusive='neither').all()

# A8-2: 留言功能未啟用時，三欄必須全部為 NULL（不得被填補）
if not comment_feature_enabled:
    assert df[COMMENT_COLS].isna().all().all(), "留言未啟用時三欄必須為 NULL"

# A8-3: 來源失敗當日，三欄必須為 NULL（不得寫入 0 或中立值）
failed_dates = df[df['source_status'] == 'SOURCE_FAILED'].index
assert df.loc[failed_dates, COMMENT_COLS].isna().all().all(), \
    "SOURCE_FAILED 當日留言特徵必須為 NULL"

# A8-4: 嚴禁中立值填補 — 若三欄全為同一常數值，視為錯誤填補
for col in COMMENT_COLS:
    non_null_vals = df[col].dropna()
    if len(non_null_vals) > 5:
        assert non_null_vals.nunique() > 1, f"{col} 疑似被常數填補"

# A8-5: raw 層不得 DEFAULT 0（BLOCK-1）
# market_articles 的留言計數欄必須可為 NULL，
# 以區分「未解析」(NULL) 與「確實 0 則留言」(0)
raw_cols = ['push_count', 'boo_count', 'neutral_count', 'total_comments']
schema = introspect_columns('market_articles')
for c in raw_cols:
    assert schema[c].default is None, \
        f"market_articles.{c} 不得有 DEFAULT —— 會把未解析文章偽造成 0 則留言"
    assert schema[c].is_nullable, f"market_articles.{c} 必須允許 NULL"
```

> **與 A6/A7 的關係**：A6 的「零 NaN」斷言已於 V8 加上 `source_status` 前置條件，
> 且明確排除留言三欄。三者共同構成 §5A 全欄位 NULL 語意規則的可執行驗證。

### A9: Metadata 欄位值域與不變式 [NEW]

```python
# A9-1: source_status 值域
VALID_STATUS = {'SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED', 'SOURCE_FAILED'}
non_null = df['source_status'].notna()
assert df.loc[non_null, 'source_status'].isin(VALID_STATUS).all()

# A9-2: label_reason 值域
VALID_REASON = {'ambiguous_dual_barrier', 'insufficient_data', 'no_entry'}
non_null = df['label_reason'].notna()
assert df.loc[non_null, 'label_reason'].isin(VALID_REASON).all()

# A9-3: 不變式 — label_reason 非 NULL ⟺ target_triple_barrier 為 NULL
labeled = df['target_triple_barrier'].notna()
assert df.loc[labeled, 'label_reason'].isna().all(), \
    "標籤已生成的列不應有 label_reason"

has_reason = df['label_reason'].notna()
assert df.loc[has_reason, 'target_triple_barrier'].isna().all(), \
    "有 label_reason 的列，標籤必須為 NULL"

# A9-4: metadata 欄位絕不可進入模型輸入
assert 'source_status' not in ALL_MODEL_INPUT_COLS
assert 'label_reason'  not in ALL_MODEL_INPUT_COLS
```

### A10: Ambiguous Ratio 可計算性 [NEW]

```python
# PURGED_WALK_FORWARD_SPEC.md §6 的報告依賴 label_reason 分離三種成因
total = len(df)
ambiguous    = (df['label_reason'] == 'ambiguous_dual_barrier').sum()
insufficient = (df['label_reason'] == 'insufficient_data').sum()
no_entry     = (df['label_reason'] == 'no_entry').sum()

# 三種成因加總 = 標籤 NULL 的總數
assert ambiguous + insufficient + no_entry == df['target_triple_barrier'].isna().sum()

# RISK-011 觸發條件可計算
ambiguous_ratio = ambiguous / total
assert isinstance(ambiguous_ratio, float)   # 必須算得出來，不是 NaN
```

---

## 附錄 A: 程式碼位置索引

| 檔案 | 內容 | 關鍵行號 |
|------|------|---------|
| `src/ml/model_trainer.py` | ALL_MULTIMODAL_FEATURE_COLS (LEGACY_17 白名單) | L18-41 |
| `src/ml/baseline_models.py` | TECHNICAL_FEATURE_COLS (純價量 baseline 白名單) | L10-20 |
| `src/transform/feature_aggregator.py` | 特徵生成邏輯：RSI、波動率、情緒融合、滯後特徵 | L108-437 |
| `src/transform/feature_aggregator.py` | 目標標籤生成：target_next_close, target_return_1d, target_up_down | L439-470 |
| `database/schema.sql` | daily_ml_features 表定義（現行 7 欄位，待擴充至 29 欄位） | L95-104 |
| `src/loaders/db_writer.py` | upsert_ml_features（現行寫入 7 欄位） | L405-440 |

## 附錄 B: Schema 差異摘要（現行 vs 目標）

### 現行 daily_ml_features（7 欄位）

```sql
CREATE TABLE daily_ml_features (
    trade_date DATE,
    stock_id TEXT,
    close_price NUMERIC,
    volume BIGINT,
    article_count INTEGER DEFAULT 0,
    sentiment_mean NUMERIC,
    sentiment_3d_ma NUMERIC,
    PRIMARY KEY (trade_date, stock_id)
);
```

### 目標 daily_ml_features（29 欄位）

需新增 22 欄位：`source_status`, `label_reason`, `return_1d`, `rsi_14`, `volatility_5d`, `volatility_20d`, `bullishness_index`, `agreement_index`, `sentiment_5d_ma`, `sentiment_lag_1`, `sentiment_lag_2`, `amplitude_ratio`, `ma5_bias_ratio`, `ma20_bias_ratio`, `volume_ratio_5d`, `comment_volume_ratio`, `comment_polarization`, `net_push_momentum`, `target_next_close`, `target_return_1d`, `target_up_down`, `target_triple_barrier`。

遷移計畫詳見 `DB_MIGRATION_PLAN.md`（Gate 0 交付物 E）。
