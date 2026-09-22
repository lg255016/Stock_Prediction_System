# UG-G1-SB1 步驟 1：覆蓋歸因與 BEFORE 快照

> **性質**：`SB1_GATE_A_PROPOSAL.md` §4.3 步驟 0 與步驟 1 的**必要產出物**。
> 不是交接文件 —— 步驟 1 要求的就是產出此快照，沒有它 Gate B 無可比對。
> **執行日期**：2026-08-24
> **狀態**：步驟 2～5 已完成（見下方「下一步」表）；`src/` 變更為 `time_series_split.py`、
> `feature_aggregator.py`，尚未 commit
> **證據標籤**：`VERIFIED THIS SESSION`（重跑程序見 §7）

---

## 1. 執行環境

| 欄位 | 內容 |
|------|------|
| 環境 | **dev container**（`stock_prediction_system2_devcontainer-app-1`），GOV-03 釘選 |
| Python | 3.14.6 |
| 身分 | `vscode`（不可省略；以 root 執行會看到全部套件 ABSENT）|
| 資料庫 | **空的臨時 PostgreSQL**，獨立容器 `sb1_before_tmpdb`，port **55433** |

### 1.1 隔離證據

| 項目 | 值 |
|------|-----|
| Volume | 1 個**匿名 docker volume**，`HostConfig.Binds = []` —— **非** `./postgres-data` 的 bind |
| Port | 55433（真實開發 DB 在 5432） |
| Schema | `database/schema.sql` 套用完成，exit 0 |
| PO 的容器 | `app-1` / `db-1` 皆 `RestartCount=0`、`StartedAt` 全程未變 |
| 拆除 | 量測完成後 `docker rm -f -v sb1_before_tmpdb`，含匿名 volume |

### 1.2 綁定確認（RISK-013 控制措施，執行前已呈報 PO 放行）

以**專案自身的 `DBWriter.db_config` 解析路徑**取得，非手寫連線字串 ——
手寫只證明「能連到臨時 DB」，證不到「測試將使用的那組設定指向臨時 DB」。

```
專案解析出的連線設定：host='localhost'  port=55433  database='sb1_before'  user='tmp_sb1'

實際連上的目標：
   current_database()  = sb1_before
   current_user        = tmp_sb1
   inet_server_port()  = 55433
   public schema 表數  = 8
   _sb1_before_marker  = True    <- 僅存在於臨時 DB；若連到真實 DB 此值為 False
   daily_ml_features   = True，列數 = 0
```

---

## 2. 全套測試 BEFORE 快照

```
154 tests / PASS=154 / FAIL=0 / ERROR=0 / SKIP=0 / elapsed 11.566s
```

`elapsed` 含 `sys.settrace` 逐呼叫追蹤開銷，故高於 GOV-02 的 6.1–10.1s，**不可與之直接比較**。

### 2.1 逐檔結果（全部 154 筆 outcome 皆為 PASS）

| 測試檔 | 總數 | A | B | C |
|--------|-----:|--:|--:|--:|
| test_baseline_models | 6 | 1 | 5 | 0 |
| test_canonical_stock_id | 17 | 7 | 10 | 0 |
| test_db_read_semantics | 14 | **0** | 14 | 0 |
| test_feature_aggregator_alignment | 5 | 5 | 0 | 0 |
| test_ml_evaluator | 7 | 1 | 6 | 0 |
| test_model_trainer | 5 | 1 | 4 | 0 |
| test_nlp_cache_semantics | 8 | 0 | 8 | 0 |
| test_nlp_checkpoint_semantics | 11 | **0** | 11 | 0 |
| test_nlp_resilience_e2e | 2 | 2 | 0 | 0 |
| test_operational_ux | 10 | 0 | 9 | 1 |
| test_real_articles_pipeline | 4 | 0 | 3 | 1 |
| test_research_features | 6 | 6 | 0 | 0 |
| test_thematic_feature_spillover | 5 | 5 | 0 | 0 |
| test_thematic_mapping | 5 | 0 | 5 | 0 |
| test_time_alignment | 13 | 7 | 6 | 0 |
| test_time_series_split | 6 | 6 | 0 | 0 |
| test_tracking_keyword_integrity | 15 | 0 | 15 | 0 |
| test_ui_contracts | 15 | 1 | 7 | 7 |
| **合計** | **154** | **42** | **103** | **9** |

---

## 3. 方法粒度 A／B／C 分類（取代 Gate A §4.2 的 grep 推導版）

| 類 | 定義 | 數量 |
|---|------|-----:|
| **A 直接覆蓋** | 實測執行到 `src/ml/time_series_split.py` 或 `src/transform/feature_aggregator.py`，且非 HERM | **42** |
| **B 迴歸對照** | 未執行到上述兩模組，且非 HERM | **103** |
| **C 零證據** | HERM-01~09 | **9** |

### 3.1 A 類 42 個方法（SB1 的驗收依據）

**splitter — 9 個**

| 測試檔 | 方法 |
|--------|------|
| test_time_series_split | `WalkForwardSplitterUnitTests` 全 6：`test_expanding_mode_accumulates_historical_data`、`test_initialization_validation`、`test_insufficient_dates_and_empty_inputs`、`test_missing_date_column_raises_key_error`、`test_multi_stock_global_date_alignment`、`test_rolling_mode_splits_and_temporal_invariants` |
| test_baseline_models | `TechnicalBaselineWalkForwardIntegrationTests.test_technical_suite_walk_forward_execution` |
| test_ml_evaluator | `MultiModelTournamentEvaluatorTests.test_tournament_evaluates_8_experiments_and_produces_leaderboard` |
| test_model_trainer | `MultiModalWalkForwardIntegrationTests.test_multimodal_trainer_walk_forward_pipeline` |

**aggregator — 33 個**

| 測試檔 | 數量 | 類別 |
|--------|-----:|------|
| test_canonical_stock_id | 7 | `ETLPipelineManagerCanonicalDispatchTests` 6 + `FeatureAggregatorMultiMarketJoinTests` 1 |
| test_time_alignment | 7 | `TradingDayRollForwardMappingTests` 6 + `FeatureAggregatorRollForwardIntegrationTests` 1 |
| test_research_features | 6 | `AntweilerMetricsUnitTests` 2 + `FeatureAggregatorResearchIntegrationTests` 2 + `TechnicalAndRiskMetricsUnitTests` 2 |
| test_feature_aggregator_alignment | 5 | `TargetLabelGenerationTests` 1 + `TimeSeriesFeatureAndLagTests` 2 + `ZeroLookAheadBiasStrictVerificationTests` 2 |
| test_thematic_feature_spillover | 5 | `ThematicFeatureSpilloverTests` 5 |
| test_nlp_resilience_e2e | 2 | `NLPResilienceAndE2EIntegrationTests` 2 |
| test_ui_contracts | 1 | `DataLoaderContractTests.test_fetch_real_stock_features_without_name_error` |

### 3.2 C 類：HERM-01~09 交叉檢查

| HERM | 方法 | 執行到 SB1 模組？ | outcome |
|------|------|------------------|---------|
| HERM-01 | `test_load_ai_discovered_keywords_fallback` | **無** | PASS |
| HERM-02 | `test_load_stock_articles_returns_clean_contract` | **無** | PASS |
| HERM-03 | `test_load_stock_features_returns_18_columns` | **無** | PASS |
| HERM-04 | `test_load_stock_articles_returns_expected_columns` | **無** | PASS |
| HERM-05 | `test_get_champion_predictor_inference` | **無** | PASS |
| HERM-06 | `test_load_thematic_radar_data_structure` | **無** | PASS |
| HERM-07 | `test_render_price_sentiment_candlestick_chart_structure` | **無** | PASS |
| HERM-08 | `test_render_pnl_equity_curve_chart_structure` | **無** | PASS |
| HERM-09 | `test_render_thematic_radar_component_structure` | **無** | PASS |

**9 個 HERM 方法無一執行到 SB1 的兩個模組。**
SB1 的驗收證據與 HERM 封閉性缺口**不重疊** —— Gate 1 啟動申請中提出的
「HERM 未修好之前 SB1 如何取得可信證據」順序問題，實測顯示不存在。

`test_ui_contracts.py` 唯一命中 SB1 模組的是 **非 HERM** 的
`DataLoaderContractTests.test_fetch_real_stock_features_without_name_error`，
依 PO 指示歸入 **A 類**，不因住在 HERM 檔案裡而被排除。

---

## 4. 方法論結論：靜態 grep 與 runtime 歸因測的不是同一件事

Gate A §4.2 的 A 類是 **12 個整檔**（grep 推導），換算 **97 個測試**。
實測方法粒度為 **42 個**。落差最大的兩個檔案，grep 版整檔列入 A，實測**一個方法都沒執行到**：

| 檔案 | grep 版 | 實測 |
|------|--------:|-----:|
| `test_db_read_semantics.py` | 14 全列 A | **0** |
| `test_nlp_checkpoint_semantics.py` | 11 全列 A | **0** |

### 4.1 根因：它們不是「碰巧沒執行到」，是主動替換

```python
# tests/test_db_read_semantics.py:67
"src.transform.feature_aggregator": pipeline_dependency_stub(
    "src.transform.feature_aggregator", "FeatureAggregator"
),

# tests/test_nlp_checkpoint_semantics.py:54
"src.transform.feature_aggregator": class_module(
    "src.transform.feature_aggregator", "FeatureAggregator"
),
```

字串 `src.transform.feature_aggregator` 出現的原因，**正是為了把該模組換成替身**。

**靜態掃描在原理上分不出 use 與 replace** —— 兩者在檔案裡都只是同一個字串。
grep 把「替換這個模組」讀成「覆蓋這個模組」，方向完全相反。
**這不是 pattern 寫得不夠好，是方法本身的能力上限。**

反向漏抓一例：`test_ui_contracts.py` 完全不在 grep 版 A 類，實測有 1 個命中。

### 4.2 結論

| | 靜態 grep | runtime 歸因 |
|---|---|---|
| 回答的問題 | 檔案裡**有沒有提到**這個模組 | 測試**有沒有執行到**這個模組 |
| 對 stub／mock | **無法區分**，會把替換算成覆蓋 | 正確排除 |
| 適用場合 | 快速找候選 | **驗收證據分類** |

**驗收證據的分類必須用 runtime 歸因，且必須是方法粒度。**
若照 grep 版驗收，會有 55 個從未執行到 SB1 程式碼的測試被當成「直接覆蓋」的證據 ——
那只會讓覆蓋看起來比實際好。**縮減讓標準更嚴，不是放寬。**

---

## 5. BEFORE 基線：Fold 特性

**面板**：確定性合成，3 檔（`1101`／`2330`／`2454`）× 120 個工作日
（`pd.bdate_range("2024-01-01", periods=120)`）= 360 列。**無隨機性**，AFTER 可逐項比對。

```
mode=rolling    train=60 test=20 step=20  ->  get_n_splits() = 3
   Fold 0 | train n=180 [2024-01-01..2024-03-22] | test n=60 [2024-03-25..2024-04-19] | gap=3 日
   Fold 1 | train n=180 [2024-01-29..2024-04-19] | test n=60 [2024-04-22..2024-05-17] | gap=3 日
   Fold 2 | train n=180 [2024-02-26..2024-05-17] | test n=60 [2024-05-20..2024-06-14] | gap=3 日

mode=expanding  train=60 test=20 step=20  ->  get_n_splits() = 3
   Fold 0 | train n=180 [2024-01-01..2024-03-22] | test n=60 [2024-03-25..2024-04-19] | gap=3 日
   Fold 1 | train n=240 [2024-01-01..2024-04-19] | test n=60 [2024-04-22..2024-05-17] | gap=3 日
   Fold 2 | train n=300 [2024-01-01..2024-05-17] | test n=60 [2024-05-20..2024-06-14] | gap=3 日
```

### 5.1 洩漏在基線裡直接可見

`gap=3 日` **全部是週末** —— 2024-03-22／04-19／05-17 皆為週五，test 首日皆為次週一。
train 末日與 test 首日是**相鄰交易日，交易日隔離為零**。

H=5 時 `train[T]` 的標籤需要 `close[T+5]`，那 5 天**完全落在 test 窗口內**。
**洩漏不是推論，是基線裡看得見的事實。**

### 5.2 AFTER 的三個比對點

| 項目 | BEFORE | Purge 後預期 |
|------|--------|-------------|
| `train n`（rolling） | 180 | **下降** |
| `train` 末日 | 與 test 首日相鄰 | **往前推 H 個交易日** |
| 交易日隔離 | **0** | **>= H**（加 embargo 則更多） |

`get_n_splits()` 若因 `min_train_size` 不足而下降，屬 RISK-001 接受邊界所涵蓋的預期行為 ——
**嚴禁為了保留 Fold 而縮小 Purge 範圍或放寬 `label_end_date` 判定。**

---

## 6. Gate B 追加證據要求（PO 指示，GOV-06）

### 6.1 證據必須分模組陳述，不得把「42 個全過」當均質

證據分布與風險分布是**反的**：

| 模組 | A 類證據 | SB1 的變更 |
|------|--------:|-----------|
| splitter | **9** | **核心演算法變更**（purge / gap / embargo） |
| aggregator | **33** | 只新增一個 `label_end_date` 欄位 |

而那 9 個裡有 3 個是端到端性質
（`test_technical_suite_walk_forward_execution`、
`test_tournament_evaluates_8_experiments_and_produces_leaderboard`、
`test_multimodal_trainer_walk_forward_pipeline`）——
它們抓得到「切分壞了會爆」，**抓不到「purge 邊界差一天」**。

**真正驗證 purge 正確性的，實質上只有 `test_time_series_split.py` 的 6 個。**

**要求**：Gate B 報告中，splitter 的變更必須由 splitter 證據支撐；
**aggregator 的 33 個不得替 splitter 背書**。

### 6.2 新增測試必須打在 splitter 上

涵蓋 `PURGED_WALK_FORWARD_SPEC.md` §5.1 的 **T-PW-01~05**：

| ID | 測試 | 驗證 |
|----|------|------|
| T-PW-01 | `test_purge_removes_label_overlapping_rows` | H=1 時 train 尾端 1 天被移除 |
| T-PW-02 | `test_purge_h5_removes_five_days` | H=5 時 train 尾端 5 天被移除 |
| T-PW-03 | `test_embargo_excludes_post_test_train_candidates` | `embargo_days > 0` 時 test 後方天數被排除 |
| T-PW-04 | `test_core_assertion_holds` | `max(train.label_end_date) < min(test.trade_date)` 恆成立 |
| T-PW-05 | `test_future_data_mutation` | 注入未來資料 → assertion 失敗或拋出異常 |

**特別是 T-PW-01 與 T-PW-04。**

### 6.3 Sentinel 基線更正

`connect()` **靜態呼叫點為 10 處**（`db_writer.py` 7 + `data_loader.py` 3；
`init_db` 另 2 處，測試不觸及），非提案原文的 9。9 是 GOV-02 的 **runtime 攔截次數**。
兩者在 Gate B 必須**分開陳述**，不得互相代替。

---

## 7. 重跑程序

本次量測為**確定性**：合成面板無隨機性、容器由 GOV-03 以 digest 與 `requirements.lock.txt`
釘選、臨時 DB 程序如 §1。重跑需一輪工作，但結果應可重現 —— **這是可重跑的量測，不是不可回復的資產。**

```bash
# 1. 臨時 DB（不掛 postgres-data，與真實 DB 的 5432 分離）
docker run -d --name sb1_before_tmpdb \
  --network container:stock_prediction_system2_devcontainer-db-1 \
  -e POSTGRES_PASSWORD=tmp_sb1 -e POSTGRES_USER=tmp_sb1 -e POSTGRES_DB=sb1_before \
  postgres:18 -c port=55433

docker exec -i sb1_before_tmpdb psql -p 55433 -U tmp_sb1 -d sb1_before \
  -v ON_ERROR_STOP=1 -q < database/schema.sql

# 2. 綁定確認 —— 必須先呈報 PO 再跑（RISK-013 控制措施）
#    須以 DBWriter().db_config 取得，不得手寫連線字串

# 3. 量測（容器內，-u vscode 不可省略）
MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=localhost -e DB_PORT=55433 -e POSTGRES_DB=sb1_before \
  -e POSTGRES_USER=tmp_sb1 -e POSTGRES_PASSWORD=tmp_sb1 \
  stock_prediction_system2_devcontainer-app-1 python - < <歸因腳本>

# 4. 拆除
docker rm -f -v sb1_before_tmpdb
```

歸因腳本以 `sys.settrace` 攔截 `call` 事件，比對 `frame.f_code.co_filename`
是否以 `src/ml/time_series_split.py` 或 `src/transform/feature_aggregator.py` 結尾，
於 `unittest.TextTestResult.startTest` 安裝、`stopTest` 卸除，逐測試方法記錄命中與 outcome。

兩個執行陷阱（本次都踩到）：

| 陷阱 | 症狀 | 解法 |
|------|------|------|
| MSYS 路徑轉換 | `docker exec` 的 `-w` 被改寫，`Cwd must be an absolute path` | 前置 `MSYS_NO_PATHCONV=1` |
| `discover` 的 `top_level_dir` | `tests/` 無 `__init__.py`，設為 repo 根會 `ImportError: Start directory is not importable` | 不傳 `top_level_dir`，與 `python -m unittest discover -s tests` 行為一致 |

---

## 8. 下一步

| 步驟 | 狀態 |
|------|------|
| 步驟 0 覆蓋歸因 | **完成**（§3、§4） |
| 步驟 1 BEFORE 快照 | **完成**（§2、§5） |
| 步驟 2 保存修正前績效基線 | **完成**（2026-08-24）—— 見 `DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節 |
| 步驟 3 實作 | **完成**（2026-08-24/25）—— `time_series_split.py`／`feature_aggregator.py`；含 PO 2026-08-25 回報之精確路徑修正 |
| 步驟 4 AFTER 快照 | **完成**（2026-08-25）—— 見 `SB1_STEP4_AFTER_SNAPSHOT.md` |
| 步驟 5 Sentinel | **完成**（2026-08-25）—— 靜態 10 處不變；runtime 攔截 9 次與 GOV-02 基線一致，見 `SB1_STEP4_AFTER_SNAPSHOT.md` §4 |
| 步驟 6 送 Gate B | 未開始 |
