# UG-G1-SB1 步驟 4／步驟 5：AFTER 快照與 Sentinel 防護

> **性質**：`SB1_GATE_A_PROPOSAL.md` §4.3 步驟 4、步驟 5 的必要產出物。
> 與 `SB1_STEP1_BEFORE_SNAPSHOT.md` 逐項對照，判斷步驟 3 實作是否符合預期、有無非預期迴歸。
> **執行日期**：2026-08-25
> **狀態**：`src/`、`tests/`、`database/` 自步驟 3 提交（尚未 commit）後未再變動；本文件僅新增
> **證據標籤**：`VERIFIED THIS SESSION`（重跑程序見 §6）

---

## 1. 執行環境

| 欄位 | 內容 |
|------|------|
| 環境 | dev container (`stock_prediction_system2_devcontainer-app-1`)，GOV-03 釘選 |
| Python | 3.14.6 |
| 身分 | `vscode`（不可省略） |
| 資料庫 | 獨立臨時 PostgreSQL，容器 `sb1_after_tmpdb`，port **55434**（BEFORE 用 55433，避免與已拆除容器混淆） |

### 1.1 隔離證據

| 項目 | 值 |
|------|-----|
| Volume | 匿名 docker volume，`HostConfig.Binds = null` —— 非 `./postgres-data` 的 bind |
| Schema | `database/schema.sql` 套用完成，exit 0 |
| 開發容器 | `app-1` / `db-1` 執行狀態未變（`docker ps` 顯示 uptime 連續） |
| 拆除 | 量測完成後 `docker rm -f -v sb1_after_tmpdb`，含匿名 volume |

### 1.2 綁定確認（RISK-013 控制措施，以 `DBWriter().db_config` 解析路徑取得）

```
專案解析出的連線設定: {'host': 'localhost', 'port': 55434, 'database': 'sb1_after', 'user': 'tmp_sb1_after'}

current_database() = sb1_after
current_user       = tmp_sb1_after
inet_server_port() = 55434
public schema 表數  = 8
_sb1_after_marker   = True    <- 僅存在於本次臨時 DB；若連到真實 DB 此值為 False
daily_ml_features   = 存在，列數 = 0
```

---

## 2. 全套測試 AFTER 快照

```
Ran 163 tests in 7.519s
OK
```

以自訂 `TestResult` 逐測試記錄 id + outcome（避免 verbose 模式因多行 docstring 造成行位移誤判），
確認：**163 PASS / 0 FAIL / 0 ERROR**。

### 2.1 逐檔案數量對照（BEFORE → AFTER）

| 測試檔 | BEFORE | AFTER | Δ | 說明 |
|--------|-------:|------:|---:|------|
| test_baseline_models | 6 | 6 | 0 | — |
| test_canonical_stock_id | 17 | 17 | 0 | — |
| test_db_read_semantics | 14 | 14 | 0 | — |
| **test_feature_aggregator_alignment** | 5 | **8** | **+3** | SB1 新增：`label_end_date` 欄位測試 3 個 |
| test_ml_evaluator | 7 | 7 | 0 | — |
| test_model_trainer | 5 | 5 | 0 | — |
| test_nlp_cache_semantics | 8 | 8 | 0 | — |
| test_nlp_checkpoint_semantics | 11 | 11 | 0 | — |
| test_nlp_resilience_e2e | 2 | 2 | 0 | — |
| test_operational_ux | 10 | 10 | 0 | — |
| test_real_articles_pipeline | 4 | 4 | 0 | — |
| test_research_features | 6 | 6 | 0 | — |
| test_thematic_feature_spillover | 5 | 5 | 0 | — |
| test_thematic_mapping | 5 | 5 | 0 | — |
| test_time_alignment | 13 | 13 | 0 | — |
| **test_time_series_split** | 6 | **12** | **+6** | SB1 新增：T-PW-01~05（5 個）+ 停牌重現測試（1 個） |
| test_tracking_keyword_integrity | 15 | 15 | 0 | — |
| test_ui_contracts | 15 | 15 | 0 | — |
| **合計** | **154** | **163** | **+9** | 154 + 9 個 SB1 新增測試 |

**逐檔數量零意外落差**：除兩個 SB1 直接新增測試的檔案外，其餘 16 個檔案的測試數量與 BEFORE
逐一相同；沒有測試消失、改名或被跳過。

---

## 3. 依 A/B/C 分類的逐項比對

> 分類定義見 `SB1_STEP1_BEFORE_SNAPSHOT.md` §3（runtime 歸因，非 grep 推導）。

### 3.1 A 類（42 個方法，SB1 的驗收依據）—— 全數 PASS

**splitter — 9 個**（`WalkForwardSplitterUnitTests` 全 6 + 3 個端到端）：

| 方法 | BEFORE | AFTER | 斷言內容變化 |
|------|--------|-------|-------------|
| `test_rolling_mode_splits_and_temporal_invariants` | PASS | PASS | **有變化**：`train_days`/`train_idx` 長度由 40 改為 39（預設 `label_horizon=1` 自動 Purge 1 天），已於測試內加註解說明；Fold 數、無交集、時序先後等其餘斷言不變 |
| `test_expanding_mode_accumulates_historical_data` | PASS | PASS | **有變化**：`expected_train_days` 由 `[30,45,60]` 改為 `[29,44,59]`，同上原因 |
| `test_multi_stock_global_date_alignment` | PASS | PASS | **有變化**：`train_days` 20→19、`train_idx` 長度 60→57，同上原因；`test_days`/`test_idx`（10／30）不變 |
| `test_initialization_validation` | PASS | PASS | 僅新增對 `label_horizon`／`embargo_days`／`min_train_size` 預設值與負數防護的斷言，原有斷言未刪改 |
| `test_insufficient_dates_and_empty_inputs` | PASS | PASS | 無變化（純窗口不足情境，Purge 邏輯不介入） |
| `test_missing_date_column_raises_key_error` | PASS | PASS | 無變化 |
| `test_technical_suite_walk_forward_execution`（baseline_models） | PASS | PASS | 無斷言變化；內部呼叫 splitter 時 fold 邊界隨預設 Purge 改變，但此測試不斷言精確邊界數字 |
| `test_tournament_evaluates_8_experiments_and_produces_leaderboard`（ml_evaluator） | PASS | PASS | 同上 |
| `test_multimodal_trainer_walk_forward_pipeline`（model_trainer） | PASS | PASS | 同上 |

**aggregator — 33 個**：全數 PASS，斷言內容**無變化**（SB1 對 `feature_aggregator.py` 的修改僅為新增
`label_end_date` 欄位與 `label_horizon` 參數，未改動任何既有欄位的計算邏輯；33 個既有方法不涉及
新欄位，故無需修改斷言）。逐方法清單見 `SB1_STEP1_BEFORE_SNAPSHOT.md` §3.1，本次逐一重跑確認
outcome 與 BEFORE 相同，不重複列出。

**結論**：42 個 A 類方法全數 PASS；其中 3 個因 SB1 的預期行為改變（默認啟用 Purge）而調整了斷言
數值，其餘 39 個斷言內容完全未變。此結果符合 `SB1_GATE_A_PROPOSAL.md` §5.2「train n 應下降、
train 末日應往前推、交易日隔離應 ≥ H」的預期。

### 3.2 B 類（103 個方法，迴歸對照）—— 全數 PASS，零變化

全套測試 outcome 為 163/163 PASS，其中 B 類 103 個方法不在 SB1 變更的兩個模組（`time_series_split.py`、
`feature_aggregator.py`）覆蓋範圍內；本次執行確認其 outcome 與 BEFORE 逐一相同（PASS→PASS），
無任何非預期迴歸。

### 3.3 C 類（HERM-01~09，零證據價值）—— 僅記錄

9 個 HERM 方法本次仍全數 PASS，與 BEFORE 相同。依既定原則，此結果**不具驗證力**（見
`DOCUMENT_DRIFT_REMEDIATION.md` GOV-02 章節），僅供記錄；不作為 SB1 驗收依據。

### 3.4 新增測試（9 個，非 BEFORE/AFTER 對照對象）

SB1 新增測試無 BEFORE 基線可比對，本次為首次執行，全數 PASS：

| 測試檔 | 新增方法 |
|--------|---------|
| `test_time_series_split.py`（`PurgedWalkForwardTests`） | `test_purge_removes_label_overlapping_rows`（T-PW-01）、`test_purge_h5_removes_five_days`（T-PW-02）、`test_embargo_excludes_post_test_train_candidates`（T-PW-03）、`test_core_assertion_holds`（T-PW-04）、`test_future_data_mutation`（T-PW-05）、`test_purge_uses_per_stock_label_end_date_for_calendar_misalignment`（PO 2026-08-25 回報重現測試） |
| `test_feature_aggregator_alignment.py`（`TargetLabelGenerationTests`） | `test_label_end_date_defaults_to_t_plus_1`、`test_label_end_date_respects_explicit_label_horizon`、`test_label_end_date_computed_per_stock_calendar` |

---

## 4. 步驟 5：Sentinel 防護

### 4.1 靜態呼叫點（可重跑：`grep -rn "\.connect(" src/loaders/db_writer.py src/ui/data_loader.py`）

```
db_writer.py: 7 處（L61, L84, L180, L225, L247, L270, L311）
data_loader.py: 3 處（L145, L230, L417）
合計: 10 處 —— 與 SB1_GATE_A_PROPOSAL.md 更正後基線一致，數量與位置皆未增加。
init_db.py 另 2 處，測試不觸及，不計入本次比對範圍。
```

SB1 變更檔案（`src/ml/time_series_split.py`、`src/transform/feature_aggregator.py`）內
**零個** `connect()` 呼叫（確認為純 pandas 運算，不涉及 DB）。

### 4.2 Runtime 攔截數（GOV-02 可攔截 sentinel，一次性替換 `psycopg2.connect`，全套測試不連真實 DB）

```
RUNTIME_INTERCEPTIONS=9
  db_writer.py:270 in fetch_ai_discovered_keywords         x1
  data_loader.py:145 in _fetch_real_stock_features_from_db x4
  data_loader.py:230 in _fetch_real_stock_articles_from_db x2
  data_loader.py:417 in load_thematic_radar_data           x2

SUMMARY total=163 fail=0 error=0
```

與 GOV-02 原始基線（9）一致，攔截點與 `DOCUMENT_DRIFT_REMEDIATION.md` 登錄的 HERM-01~09
呼叫路徑完全對應。**靜態呼叫點（10）與 runtime 攔截數（9）為兩個不同量測，本節分開陳述，
不互相代替**（兩者差 1，因 `fetch_ai_discovered_keywords` 以外的 `db_writer.py` 6 個 connect()
呼叫點未被本次測試套件的任何路徑觸發）。

全套測試在 `psycopg2.connect` 被攔截、每次呼叫皆拋出例外的情況下仍 163/163 PASS，
確認既有的連線失敗容錯路徑（`data_loader.py` 的 debug-log + fallback）未被 SB1 變更影響。

---

## 5. 結論

| 項目 | 結果 |
|------|------|
| A 類（42）| 全數 PASS；3 個因 Purge 預期行為變化調整斷言數值，已逐項列出並解釋；39 個斷言內容不變 |
| B 類（103）| 全數 PASS，零變化，無迴歸 |
| C 類（HERM 9）| 全數 PASS，零證據價值，僅記錄 |
| 新增（9）| 全數 PASS，首次執行 |
| 靜態 `connect()` 呼叫點 | 10 處，未增加 |
| Runtime 攔截數 | 9 次，與 GOV-02 基線一致 |

步驟 4、步驟 5 完成，未發現非預期迴歸或 Sentinel 違規。

---

## 6. 重跑程序

```bash
# 1. 臨時 DB
docker run -d --name sb1_after_tmpdb \
  --network container:stock_prediction_system2_devcontainer-db-1 \
  -e POSTGRES_PASSWORD=tmp_sb1_after -e POSTGRES_USER=tmp_sb1_after -e POSTGRES_DB=sb1_after \
  postgres:18 -c port=55434

docker exec -i sb1_after_tmpdb psql -p 55434 -U tmp_sb1_after -d sb1_after \
  -v ON_ERROR_STOP=1 -q < database/schema.sql

# 2. 綁定確認 —— 須以 DBWriter().db_config 取得，不得手寫連線字串

# 3. AFTER 快照（容器內，-u vscode、-i 皆不可省略）
MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=localhost -e DB_PORT=55434 -e POSTGRES_DB=sb1_after \
  -e POSTGRES_USER=tmp_sb1_after -e POSTGRES_PASSWORD=tmp_sb1_after \
  stock_prediction_system2_devcontainer-app-1 \
  python -m unittest discover -s tests -p "test_*.py" -v

# 4. 拆除
docker rm -f -v sb1_after_tmpdb

# 5. Sentinel（不需真實 DB，connect() 全程被攔截）
MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python - <<'EOF'
import traceback, unittest, io
from collections import Counter
call_log = []
def sentinel_connect(*a, **k):
    call_log.append(f"{traceback.extract_stack()[-2].filename}:{traceback.extract_stack()[-2].lineno}")
    raise RuntimeError("sentinel")
import psycopg2
psycopg2.connect = sentinel_connect
r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
    unittest.TestLoader().discover("tests", "test_*.py"))
print(len(call_log), Counter(call_log), r.testsRun, len(r.failures), len(r.errors))
EOF

# 6. 靜態呼叫點
grep -rn "\.connect(" src/loaders/db_writer.py src/ui/data_loader.py
```
