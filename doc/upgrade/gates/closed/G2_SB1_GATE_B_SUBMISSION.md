# UG-G2-SB1 Gate B 送審文件：`daily_ml_features` Schema 擴充（7→29 欄）

> 狀態：**待 PO 審查**
> 日期：2026-08-26
> 對應提案：`doc/upgrade/gates/G2_SB1_GATE_A_PROPOSAL.md`（已核准，含 §7 三個決策點）

---

## 1. 摘要

依 PO 核准之 §8 範圍完成實作：Migration 002（22 新欄，逐字採用 Gate 0 已核准 DDL）、
`db_writer.py` 擴充至 29 欄、`feature_aggregator.py` 接線 `source_status` 判定邏輯與
既有 15 個已算未寫入欄位、`main_etl_pipeline.py` 補上 `generate_target_labels()` 呼叫。
隔離臨時 DB 完整 E2E 驗證通過，過程中發現並修復一個真實 bug（NaN 寫入 INTEGER 欄位）。

**與已核准提案的差異**（皆已在實作過程中即時回報並取得你的確認）：

1. **`label_reason` 範圍縮小**：提案原規劃本 SB 會產生 `insufficient_data`／`no_entry` 兩值，
   實作時重新檢視 `chk_label_reason_consistency` 約束語意後發現這兩值屬於「Triple-Barrier
   已執行但無法產出標籤」的成因，與「尚未執行 Triple-Barrier」是不同狀態。`target_triple_barrier`
   在本 SB 完全不計算（Gate 3 才有），故 `label_reason` 本 SB 全部維持 `NULL`
   （符合約束第三分支「尚未計算標籤」）。
2. **新增一個真實 bug 修復**（非範圍變更，是隔離 DB E2E 驗證中發現）：`db_writer.py` 舊版
   `DataFrame.where(pd.notnull(df), None)` 對純數值型欄位（如 `target_up_down`，float64）
   不會把 `NaN` 正確轉為 Python `None`，導致每檔股票最後一個交易日（無未來資料，`target_up_down`
   為 `NaN`）寫入時觸發 `psycopg2.errors.NumericValueOutOfRange`。已修正為逐值 `pd.isna()` 判定，
   並補上 known-FAIL 迴歸測試（§8）。

---

## 2. Diff 摘要

| 檔案 | 異動類型 | 行數（+/-） |
|------|---------|-------------|
| `database/migrations/002_expand_ml_features.sql` | 新增 | +133 / -0 |
| `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 修改（決策點 2） | +1 / -1 |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | 修改（決策點 2、3） | +2 / -2 |
| `doc/upgrade/gates/G2_SB1_GATE_A_PROPOSAL.md` | 新增（Gate A 提案） | +258 / -0 |
| `doc/upgrade/gates/G2_SB1_GATE_B_SUBMISSION.md` | 新增（本文件） | — |
| `main_etl_pipeline.py` | 修改 | +4 / -0 |
| `src/loaders/db_writer.py` | 修改 | +37 / -20 |
| `src/transform/feature_aggregator.py` | 修改 | +17 / -2 |
| `tests/test_apply_migrations.py` | 修改（fixture 調整） | +1 / -1 |
| `tests/test_ml_feature_store_contract.py` | 新增 | +208 / -0 |
| `tests/test_nlp_resilience_e2e.py` | 修改（fixture 調整） | +2 / -2 |
| `tests/test_operational_ux.py` | 修改（fixture 調整） | +14 / -7 |

---

## 3. 產出 1：契約驗證原始輸出

```bash
$ python scripts/verify/gate0_contract_check.py
B1   PASS | 29 欄契約完整性
...
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂
==================================================
Part B: 11/11 PASS
```

---

## 4. 產出 2：執行環境、測試原始輸出、依賴狀態

**Host（Windows，非支援環境，Python 3.10.11）**：

```bash
$ python -m unittest discover -s tests -p "test_*.py"
Ran 208 tests in 2.506s
OK
```

208 = 原 200（Gate 1 收尾基線）+ 8 個本 SB 新增測試（`tests/test_ml_feature_store_contract.py`）。
`psycopg2` 缺席，`FeatureStoreColumnContractTests` 等測試檔已內建模組級 stub（見檔案開頭），
與 `test_research_features.py` 既有慣例一致，不代表真實 DB 路徑已在 host 驗證過。

**Container（`stock_prediction_system2_devcontainer-app-1`，Python 3.14.6，15 套件齊備）**：
真實 `psycopg2` 路徑於 §5 E2E 驗證中對隔離臨時 DB 實際執行過（非 mock）。

---

## 5. 產出 3：E2E 驗證（隔離臨時 DB，非 `postgres-data` 掛載）

### 5.1 RISK-013 綁定確認（PO 已於本次核可）

```
db_config: {'host': 'g2sb1_ml_features_tmpdb', 'port': 5432,
            'database': 'g2sb1_ml_features_tmpdb', 'user': 'tmpuser', 'password': 'tmppass'}
```

獨立容器（`g2sb1_ml_features_tmpdb`，host port 55441 對外，容器內部經由 devcontainer 同一
bridge network 連線），非真實開發 DB，database 名稱含 `tmpdb` 符合臨時命名慣例。

### 5.2 Fresh Init + Migration（001 + 002）

```
$ python database/init_db.py
資料庫初始化已成功 commit。

$ python database/apply_migrations.py
[apply_migrations] 目前已套用版本：v0
[apply_migrations] 正在套用 v1（001_baseline.sql）...
[apply_migrations] v1 已套用並 COMMIT。
[apply_migrations] 正在套用 v2（002_expand_ml_features.sql）...
[apply_migrations] v2 已套用並 COMMIT。
[apply_migrations] 完成，已套用至 v2。
```

### 5.3 Schema 驗證（29 欄、4 個 CHECK constraints、schema_version 雙筆記錄）

```
COLUMN COUNT: (29,)
CHECK CONSTRAINTS: [('chk_label_reason_consistency',), ('chk_label_reason_domain',),
                     ('chk_source_status_domain',), ('chk_target_triple_barrier_domain',)]
SCHEMA_VERSION: [(1, 'Baseline: create schema_version table', 'ec02925a75...'),
                  (2, 'Expand daily_ml_features: add 22 columns ...', '2cd49363ef...')]
```

### 5.4 冪等性驗證（重跑 `apply_migrations.py`）

```
$ python database/apply_migrations.py
[apply_migrations] 目前已套用版本：v2
[apply_migrations] 無待執行遷移，已是最新版本。
```

### 5.5 真實資料寫入驗證（`generate_daily_features` → `generate_target_labels` → `upsert_ml_features`）

3 個交易日、1 篇直接文章（第一日）的合成資料，寫入後查詢：

```
ROW: (date(2026,8,24), '2330', 'SUCCESS',       1, Decimal('101.0'), 1,    None, None, None)
ROW: (date(2026,8,25), '2330', 'SUCCESS_EMPTY', 0, Decimal('99.0'),  0,    None, None, None)
ROW: (date(2026,8,26), '2330', 'SUCCESS_EMPTY', 0, None,             None, None, None, None)
```

（欄位順序：trade_date, stock_id, source_status, article_count, target_next_close,
target_up_down, amplitude_ratio, label_reason, target_triple_barrier）

驗證重點：(a) 第一日有直接文章 → `SUCCESS`；(b) 第二、三日無文章 → `SUCCESS_EMPTY`；
(c) 最後一個交易日（第三日）無未來資料 → `target_next_close`／`target_up_down` 正確為
資料庫 `NULL`（**修復前**此處會是造成 `NumericValueOutOfRange` 崩潰的欄位，見 §8）；
(d) `amplitude_ratio`／`label_reason`／`target_triple_barrier` 全部正確為 `NULL`
（尚未實作／尚未計算），未被補 0 或中立值。

### 5.6 RISK-013 護欄拒絕驗證（未覆寫環境變數，容器 `network_mode: service:db` 使
`localhost:5432` 直達真實開發 DB）

```
$ python database/apply_migrations.py   # 未設定 DB_HOST/DB_PORT
[RISK-013 guard] 偵測到連線目標疑似為真實開發 DB (host=localhost, port=5432, database=postgres)，拒絕執行。
若確實要對真實 DB 執行...請先完成 CLAUDE.md RISK-013 協定之綁定確認呈報...
EXIT=1
```

連線前即被拒絕，未建立任何連線。驗證後已 `docker rm -f g2sb1_ml_features_tmpdb` 拆除。

---

## 6. 產出 4：格式／行尾夾帶偵測（含 PO 已指出的 6 行揭露）

```bash
$ git diff --numstat > raw.txt && git diff --numstat -w > nows.txt && diff raw.txt nows.txt
6c6
< 37	20	src/loaders/db_writer.py
---
> 31	14	src/loaders/db_writer.py
```

**`src/loaders/db_writer.py` 有 6 行純空白差異**（3 處空白行行尾空格被清掉、3 處
`upsert_ml_features()` 內 SQL 字串行尾空格被清掉），內容無實質變化。**重寫
`upsert_ml_features()` 過程中一併清除了這 6 行行尾空格，屬附帶清理**——PO 已於本次審查中
主動發現並指出這項未揭露的格式差異，本文件依 `CLAUDE.md` §12.2 補上揭露。除此檔案外，
其餘 11 個修改／新增檔案的 numstat 與 `-w` 版本完全一致，無其他格式夾帶。

---

## 7. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 說明 |
|------|---------|-------------------|
| 29 欄 Migration 於隔離 DB 成功套用且冪等 | `VERIFIED THIS SESSION` | §5.2、§5.4（container，`g2sb1_ml_features_tmpdb`，已拆除） |
| 4 個 CHECK constraints 生效 | `VERIFIED THIS SESSION` | §5.3 |
| `source_status` 三種情境（直接文章／僅溢出／無文章）判定正確 | `VERIFIED THIS SESSION` | `tests/test_ml_feature_store_contract.py::SourceStatusDeterminationTests`（host，208/208 OK）+ §5.5 真實 DB 寫入交叉驗證直接文章與無文章兩種情境 |
| 「僅溢出」情境於真實 DB 亦驗證過 | `NOT VERIFIED` | §5.5 的合成資料僅涵蓋直接文章與無文章兩種情境；僅溢出情境目前只有 host 端 mock 測試覆蓋，未於本次 E2E 對真實 DB 額外驗證（範圍在單元測試已足夠證明邏輯正確，未視為阻擋項） |
| NaN→INTEGER bug 已修復 | `VERIFIED THIS SESSION` | §8 known-FAIL 案例 + §5.5 真實 DB 寫入未再觸發崩潰 |
| RISK-013 護欄於本 SB 新 Migration 場景下仍生效 | `VERIFIED THIS SESSION` | §5.6 |
| 全套測試 208/208 OK（host，非 DB／ML 路徑宣稱） | `VERIFIED THIS SESSION` | §4 |
| CORE_16／留言特徵／`target_triple_barrier`／`label_reason` 維持 NULL | `VERIFIED THIS SESSION` | `test_null_not_zero_for_unimplemented_columns`（host）+ §5.5 真實 DB 交叉驗證 |
| numstat 無格式夾帶（除已揭露的 db_writer.py 6 行） | `VERIFIED THIS SESSION` | §6 |

---

## 8. 產出 6：Known-FAIL 案例對照表

| # | 檢查 | Known-FAIL 案例 | 實測結果 | 復原確認 |
|---|------|-----------------|---------|---------|
| 1 | `db_writer.py` NaN→None 轉換 | 暫時還原舊版 `DataFrame.where(pd.notnull(df), None)` 實作，重跑 `test_upsert_ml_features_converts_nan_to_none_in_pure_numeric_columns` | `FAIL — AssertionError: nan is not None`（型態 `<class 'float'>`），與隔離 DB 上實際發生的 `NumericValueOutOfRange` 根因一致 | 已還原為修正版；還原後重跑同一測試 PASS，全套 208/208 OK；`git diff` 確認 `db_writer.py` 無殘留 demo 痕跡 |
| 2 | RISK-013 護欄（本 SB 新 Migration 場景） | 未設定 `DB_HOST`／`DB_PORT`，容器內執行 `apply_migrations.py`（`network_mode: service:db` 使 `localhost:5432` 直達真實 DB） | `[RISK-013 guard] 偵測到連線目標疑似為真實開發 DB...拒絕執行`，`EXIT=1`，未建立任何連線 | 無需復原（未執行任何寫入） |
| 3 | `apply_migrations.py` 冪等性 | 對已套用至 v2 的隔離 DB 重跑 | `無待執行遷移，已是最新版本`，`EXIT=0`，無錯誤 | 無需復原 |

---

## 9. Definition of Done 對照

- [x] 29 欄 Migration 已套用（隔離臨時 DB 驗證）。
- [x] `db_writer.py` 寫入 29 欄。
- [x] 15 個既有計算欄位正確接線（`return_1d` 等 9 個 LEGACY_17 特徵 + `target_next_close`／
      `target_return_1d`／`target_up_down` 3 個 target + `source_status`／原 3 個既有欄位）。
- [x] `source_status`（兩態）判定邏輯正確，依 PO 核准之決策點 1 實作。
- [x] `label_reason` 維持 `NULL`（範圍修正，見 §1，不再是提案原訂的兩值）。
- [x] CORE_16／Triple-Barrier／留言欄位確認為 `NULL`（非 0／中立值）。
- [x] 全部測試 PASS（208/208，host）。
- [x] 契約驗證與既有測試無回歸。
- [x] §7 決策點 2、3 已於 Master Plan／`DOCUMENT_DRIFT_REMEDIATION.md` 完成。

---

## 10. 待 PO 裁決事項

1. 是否核准本次 commit（12 個檔案：8 modified + 4 new，清單見 §2）。
2. §1 列出的兩項與提案的差異（`label_reason` 範圍縮小、NaN bug 修復）是否認可為本次範圍內的
   合理執行結果。
3. §6 已揭露的 6 行 `db_writer.py` 純空白差異，是否同意隨本次一併 commit（不需另外處理）。
