# UG-G1-SB2 步驟 0／4／5 正式記錄

> **性質**：`SB2_GATE_A_PROPOSAL.md` §5.2（步驟 0）、§5.6（步驟 4）、§5.7（步驟 5）的補齊記錄。
> `SB2_STEP3_IMPLEMENTATION_REPORT.md` 當時以精簡格式回報，未含這三步；PO 2026-08-25 要求補齊。
> **執行日期**：2026-08-25
> **狀態**：`src/`、`app.py`、`tests/` 已變更，尚未 commit

---

## 0. 本次連帶處理：data_loader.py 的格式夾帶還原（PO 發現）

PO 逐行核對 diff 時發現 `src/ui/data_loader.py` 有至少 15 處與本次改動無關的純空白行清理，
與 `SB1_GATE_B_SUBMISSION.md` §5 記錄的那次同源——`Write` 工具整檔重寫時，把原檔中「帶空格的
空行」正規化為真空行。

**實測範圍比 PO 指出的更廣**：除 15 處純空白行外，另有 4 處「內容行尾多一個空格」也被夾帶
正規化（`SELECT `、`CASE `、`articles_query, `、`conn, ` 四行，皆在 SQL 查詢字串內），
合計 **19 處**。已全數以逐行比對方式（`git show HEAD:src/ui/data_loader.py` 取原始位元組，
逐一比對還原，而非整檔還原，避免連帶丟失合法改動）修正。

**還原後驗證**：

```bash
grep -n " $" src/ui/data_loader.py | wc -l   # 19 —— 與還原筆數一致，無新增/遺漏
```

還原後重跑 `py_compile`、全套測試（173/173 PASS）、contract-check（11/11 PASS）皆無異常，
證據見本文件 §3。

**工具限制記錄**：本次還原過程中，Windows 端 Python（含 Microsoft Store 版與獨立安裝版）
對此檔案的 `open(path, 'w')` 截斷寫入皆回傳 `OSError: [Errno 22] Invalid argument`，
改用 Perl（MSYS 環境）以 `index()`/`substr()` 逐一定位替換才成功寫入。額外發現：Perl 的
regex 比對（`quotemeta` + `=~ //`）在此檔案的中文字元內容上出現 UTF8-flag 不一致導致的
比對失敗（`index()` 找得到但 regex 找不到），改用純字串 `index()`/`substr()` 才穩定。
此為環境限制記錄，非本 SB 待辦事項。

---

## 1. 步驟 0：實測覆蓋歸因

以 `sys.settrace` runtime 歸因（非 grep 推導），確認哪些測試「實際執行到」
`src/ui/data_loader.py`、`src/ui/components.py`、`src/ui/charts.py`、`app.py` 四個目標模組。

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python <歸因腳本，見 §4 重跑程序>
```

```
=== src/ui/data_loader.py: 24 tests hit ===
=== src/ui/components.py: 4 tests hit ===
=== src/ui/charts.py: 4 tests hit ===
=== app.py: 0 tests hit ===
SUMMARY total=173 fail=0 error=0
```

**app.py 0 個測試命中**：`app.py` 的 `main()` 是 Streamlit 進入點，既有測試套件從未直接
`import app` 執行它（沿用既有測試設計，非本 SB 造成的缺口）——本 SB 對 `app.py` 的驗證
完全依賴其呼叫的 `data_loader.py`／`components.py`／`charts.py` 三個模組個別驗證，
以及步驟 4 的整體迴歸對照。

**去重後的 A 類測試（實際執行到至少一個目標模組）合計 28 個**：

| 測試 | 命中模組 |
|------|---------|
| `test_operational_ux.CustomStockAndTrendDiscoveryUITests.test_get_available_stocks_with_custom_stocks` | data_loader |
| `test_operational_ux...test_load_ai_discovered_keywords_demo_mode_bypasses_db` | data_loader |
| `test_operational_ux...test_load_ai_discovered_keywords_empty_result_is_empty_mode` | data_loader |
| `test_operational_ux...test_load_ai_discovered_keywords_falls_back_when_db_fails` | data_loader |
| `test_operational_ux...test_load_ai_discovered_keywords_returns_real_mode_when_db_has_data` | data_loader |
| `test_operational_ux...test_render_ai_trend_discovery_badge` | components |
| `test_real_articles_pipeline...test_fetch_real_articles_deduplication` | data_loader |
| `test_real_articles_pipeline...test_fetch_real_articles_empty_returns_dataframe_with_contract` | data_loader |
| `test_real_articles_pipeline...test_fetch_real_articles_with_entity_and_theme_and_title` | data_loader |
| `test_real_articles_pipeline...test_load_stock_articles_returns_clean_contract` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_fetch_real_stock_features_without_name_error` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_get_available_stocks` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_get_champion_predictor_inference` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_stock_articles_returns_error_mode_when_db_fails` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_stock_articles_returns_expected_columns` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_stock_features_demo_mode_bypasses_db_entirely` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_stock_features_returns_error_mode_when_db_fails` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_stock_features_returns_real_mode_with_mocked_db` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_thematic_radar_data_returns_error_mode_when_db_fails` | data_loader |
| `test_ui_contracts.DataLoaderContractTests.test_load_thematic_radar_data_structure` | data_loader |
| `test_ui_contracts.InteractiveChartsTests.test_render_feature_importance_bar_chart_structure` | charts |
| `test_ui_contracts.InteractiveChartsTests.test_render_pnl_equity_curve_chart_structure` | data_loader + charts |
| `test_ui_contracts.InteractiveChartsTests.test_render_price_sentiment_candlestick_chart_structure` | data_loader + charts |
| `test_ui_contracts.InteractiveChartsTests.test_render_price_sentiment_candlestick_chart_error_mode_is_placeholder` | charts |
| `test_ui_contracts.UIComponentsTests.test_article_table_filtering_logic` | data_loader |
| `test_ui_contracts.UIComponentsTests.test_render_raw_article_table_empty_state_and_with_data` | data_loader + components |
| `test_ui_contracts.UIComponentsTests.test_render_thematic_radar_component_structure` | data_loader + components |
| `test_ui_contracts.UIComponentsTests.test_render_thematic_radar_error_mode_shows_banner_not_crash` | components |

**B 類（迴歸對照）= 173 − 28 = 145 個**，皆不觸及本 SB 修改的模組，預期零變化。

---

## 2. 步驟 4：AFTER 快照

### 2.1 逐檔案數量對照（164 基線 → 173 AFTER）

| 測試檔 | 164 基線 | AFTER (173) | Δ | 說明 |
|--------|--------:|------------:|---:|------|
| test_baseline_models | 6 | 6 | 0 | — |
| test_canonical_stock_id | 17 | 17 | 0 | — |
| test_db_read_semantics | 14 | 14 | 0 | — |
| test_feature_aggregator_alignment | 8 | 8 | 0 | — |
| test_ml_evaluator | 7 | 7 | 0 | — |
| test_model_trainer | 5 | 5 | 0 | — |
| test_nlp_cache_semantics | 8 | 8 | 0 | — |
| test_nlp_checkpoint_semantics | 11 | 11 | 0 | — |
| test_nlp_resilience_e2e | 2 | 2 | 0 | — |
| **test_operational_ux** | 10 | **13** | **+3** | HERM-01：1 個舊測試拆為 4 個確定性測試（REAL/ERROR/EMPTY/DEMO），淨增 3 |
| **test_real_articles_pipeline** | 4 | **4** | 0 | HERM-02：既有測試改寫為 mock，方法數不變 |
| test_research_features | 6 | 6 | 0 | — |
| test_thematic_feature_spillover | 5 | 5 | 0 | — |
| test_thematic_mapping | 5 | 5 | 0 | — |
| test_time_alignment | 13 | 13 | 0 | — |
| test_time_series_split | 13 | 13 | 0 | — |
| test_tracking_keyword_integrity | 15 | 15 | 0 | — |
| **test_ui_contracts** | 15 | **21** | **+6** | HERM-03~09：新增 6 個 ERROR/DEMO 正向測試 |
| **合計** | **164** | **173** | **+9** | 164 + 9 個 SB2 新增測試 |

**逐檔數量零意外落差**：除 `test_operational_ux`、`test_ui_contracts` 兩個直接涉及 HERM 修復的
檔案外，其餘 16 個檔案的測試數量與 164 基線逐一相同，增量正好等於新增測試數，
無測試消失、改名或被跳過。

### 2.2 A/B 類逐項比對

- **A 類（28 個，見 §1）**：全數 PASS。3 個 HERM-01 相關舊測試名稱已改為更精確的名稱
  （`test_load_ai_discovered_keywords_fallback` → 拆為 4 個），斷言內容從「隨環境而定」
  改為「mock 確定性」，此為預期的、SB2 存在的理由本身的變化，非非預期迴歸。
- **B 類（145 個）**：全數 PASS，zero 變化，無迴歸。

---

## 3. 步驟 5：Sentinel（獨立重跑確認，非僅引用 PO 數字）

### 3.1 靜態 `connect()` 呼叫點

```bash
grep -c "\.connect(" src/loaders/db_writer.py src/ui/data_loader.py
```

```
src/loaders/db_writer.py:7
src/ui/data_loader.py:3
合計：10 處 —— 與 SB1 基線一致，未增加。
```

SB2 只改動 `data_loader.py` 內既有 `connect()` 呼叫點的**例外處理邏輯**（`except Exception` →
`raise DataSourceError`），未新增或刪除任何 `connect()` 呼叫點本身。

### 3.2 Runtime 攔截數（GOV-02 sentinel，PM 獨立重跑，非僅引用 PO 提供的數字）

```
RUNTIME_INTERCEPTIONS=0
SUMMARY total=173 fail=0 error=0
```

**與 BEFORE（SB1 commit `ccf0e52` 時的基線）對照**：BEFORE 為 9 次（`SB1_STEP4_AFTER_SNAPSHOT.md`
§4.2 記錄，對應 HERM-01~09 的 4 個呼叫點）；AFTER 為 **0 次** —— HERM-01~09 的測試封閉性修復
已完全生效，全套測試在 `psycopg2.connect` 被攔截、每次呼叫皆拋出例外的情況下仍 173/173 PASS，
確認沒有任何測試僥倖依賴真實連線成功。

**與 PO 獨立量測結果比對**：PO 回報「已自己重跑 GOV-02 sentinel，確認從 9 降到 0」，
與本次 PM 獨立重跑結果**完全一致**——兩次獨立量測互相印證，不是同一次數字被複製貼上兩次。

---

## 4. 重跑程序

```bash
# 步驟 0：覆蓋歸因（container，-u vscode 不可省略）
MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python - <<'EOF'
import sys, unittest, io
from collections import defaultdict
TARGETS = ("src/ui/data_loader.py", "src/ui/components.py", "src/ui/charts.py", "app.py")
hits = defaultdict(set)
current_test = [None]
def tracer(frame, event, arg):
    if event == "call":
        fn = frame.f_code.co_filename.replace("\\", "/")
        for t in TARGETS:
            if fn.endswith(t) and current_test[0]:
                hits[current_test[0]].add(t)
    return tracer
class AttrResult(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test); current_test[0] = test.id(); sys.settrace(tracer)
    def stopTest(self, test):
        sys.settrace(None); current_test[0] = None; super().stopTest(test)
loader = unittest.TestLoader()
suite = loader.discover(start_dir="tests", pattern="test_*.py")
runner = unittest.TextTestRunner(stream=io.StringIO(), resultclass=AttrResult, verbosity=0)
result = runner.run(suite)
print(f"SUMMARY total={result.testsRun} fail={len(result.failures)} error={len(result.errors)}")
by_module = defaultdict(list)
for test_id, mods in hits.items():
    for m in mods: by_module[m].append(test_id)
for m in TARGETS:
    tests = sorted(by_module.get(m, []))
    print(f"=== {m}: {len(tests)} tests hit ===")
    for t in tests: print(f"  {t}")
EOF

# 步驟 4：AFTER 快照
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python -m unittest discover -s tests -p "test_*.py" -v

# 步驟 5a：靜態呼叫點
grep -c "\.connect(" src/loaders/db_writer.py src/ui/data_loader.py

# 步驟 5b：runtime 攔截數
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
```

---

## 5. §7 文件同步範圍：完成狀態

| 文件 | 狀態 |
|------|------|
| `DECISIONS.md` | **完成**：新增 DEC-012（狀態 `Proposed`），完整記錄 PO 方案 B 裁決原話與理由 |
| `TRACEABILITY.md` | **完成**：新增「UI 四狀態資料來源透明化」追溯列 |
| `DOCUMENT_DRIFT_REMEDIATION.md` | **完成**：DRIFT-009、HERM-A、HERM-B、HERM-C、HERM-E 狀態更新為已修正；HERM-D 維持不變（歸屬 UG-G1-SB5，不在本 SB 範圍） |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` | 未變更——`SB2_GATE_A_PROPOSAL.md` §7 未要求本步驟修改 Master Plan（與 SB1 不同，SB2 的 Brief 調整已在 Gate A 核准時一併處理） |

contract-check 於每次文件異動後重跑，皆為 `11/11 PASS`（見 §6）。

---

## 6. 最終驗證

```bash
python scripts/verify/gate0_contract_check.py   # Part B: 11/11 PASS
git diff --numstat > ns_raw.txt; git diff --numstat -w > ns_now.txt; diff ns_raw.txt ns_now.txt
```

（結果見對話紀錄；`data_loader.py` 還原 19 處後，`app.py` 仍有預期內的縮排造成落差，
已在 `SB2_STEP3_IMPLEMENTATION_REPORT.md` §4 說明成因，非本次新增問題。）
