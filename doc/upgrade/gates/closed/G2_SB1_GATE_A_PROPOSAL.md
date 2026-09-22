# UG-G2-SB1 Gate A 提案：`daily_ml_features` Schema 擴充（7→29 欄）

> 狀態：**Gate A 審查中**（尚未實作，未動 `src/`／`database/`／schema）
> 日期：2026-08-26
> Gate：UG-Gate-2（已核准啟動，commit `baaf9bd`，逐 SB 授權）
> 前置：UG-G1-SB4（Migration 機制，`apply_migrations.py`／`db_target_guard.py`）已 CLOSED

---

## 0. 摘要

`daily_ml_features` 目前僅 7 欄，`src/loaders/db_writer.py:405-440` 的 `upsert_ml_features()`
只寫入其中 7 個硬編碼欄位，其餘 `feature_aggregator.py` 已經算出來的特徵（RSI、波動率、
Antweiler 指標等）從未被持久化——這正是 DRIFT-003（`UG-G2-SB1` 已登錄）描述的缺口。

本 SB 的核心工作**不是重新設計契約**——29 欄的完整 DDL 已是 Gate 0 核准交付物
（`doc/upgrade/contracts/DB_MIGRATION_PLAN.md` §4.2，含 CHECK constraints），本 SB 是
**依已核准設計執行**：新增 Migration 檔、擴充 DB Writer、補齊尚未實作的少數特徵計算，
並解決一個 Gate 0 規劃時未完全想清楚的問題——`source_status` 實際上要怎麼判定
（見 §3、§7 PO 決策點）。

---

## 1. Current State（重新對實際檔案核對，非沿用 Master Plan 舊敘述）

### 1.1 `daily_ml_features` 現況（`VERIFIED THIS SESSION`）

```sql
-- database/schema.sql:95-104
CREATE TABLE IF NOT EXISTS daily_ml_features (
    trade_date DATE, stock_id TEXT, close_price NUMERIC, volume BIGINT,
    article_count INTEGER DEFAULT 0, sentiment_mean NUMERIC, sentiment_3d_ma NUMERIC,
    PRIMARY KEY (trade_date, stock_id)
);
```

`src/loaders/db_writer.py:416-440` 的 `upsert_ml_features()` 硬編碼 7 欄清單，
`INSERT ... ON CONFLICT DO UPDATE` 也只更新這 7 欄。

### 1.2 目標 29 欄中，計算邏輯已存在／尚未存在的比例

逐欄核對 `src/transform/feature_aggregator.py` 現況（`VERIFIED THIS SESSION`）：

| 分類 | 欄位 | 計算邏輯現況 |
|------|------|-------------|
| 已存在於 DB（3） | `article_count`、`sentiment_mean`、`sentiment_3d_ma` | 已算、已寫入 |
| **LEGACY_17 已算未寫入（9）** | `return_1d`、`rsi_14`、`volatility_5d`、`volatility_20d`、`bullishness_index`、`agreement_index`、`sentiment_5d_ma`、`sentiment_lag_1`、`sentiment_lag_2` | **已算，只是沒被 `upsert_ml_features()` 寫入**——`feature_aggregator.py:421,428` 確認這些欄位在記憶體 DataFrame 中已存在 |
| Target 已算未寫入（3） | `target_next_close`、`target_return_1d`、`target_up_down` | 已由 `append_target_labels()` 計算（含 UG-G1-SB1 的 `label_end_date` 修正），未寫入 DB |
| **CORE_16 新特徵，尚未實作（4）** | `amplitude_ratio`、`ma5_bias_ratio`、`ma20_bias_ratio`、`volume_ratio_5d` | **`feature_aggregator.py` 目前不存在任何相關計算**（`VERIFIED` — 全檔 grep 零命中）；`FEATURE_REGISTRY.md` 標註為「計劃中」 |
| Target，屬 Gate 3 範圍（1） | `target_triple_barrier` | **不存在**（`VERIFIED` — 全檔 grep 零命中）；Triple-Barrier 演算法是 `UG-G3-SB1` 的工作，本 SB 僅加欄位，不加邏輯 |
| 留言特徵，屬 SB4 範圍（3） | `comment_volume_ratio`、`comment_polarization`、`net_push_momentum` | 不存在，正確——`UG-G2-SB4` 的工作 |
| **Metadata，尚無任何判定邏輯（2）** | `source_status`、`label_reason` | **全專案目前沒有任何程式碼設定這兩個值**——見 §1.3，這是本 SB 唯一需要真正新設計的部分 |

**結論**：29 欄中有 15 欄的計算邏輯本來就已經存在，只是沒被持久化——本 SB 大部分工作是
「接線」而非「新設計」。真正需要設計判斷的只有 `source_status`（§1.3、§3、§7）。

### 1.3 `source_status` 目前完全沒有判定依據（關鍵發現）

`MULTI_SOURCE_DATA_CONTRACT.md` §7.2「三態結果契約」與 §7.4 已明確登記：

> 「與現行程式碼的差異：目前 `db_writer.py` L128-129 的 `if df.empty: return` 無法區分
> 『無資料』與『來源失敗』。**UG-G2-SB2 實作時**必須讓 scraper 回傳 `(DataFrame, SourceStatus)`
> 或在失敗時拋出例外，由 pipeline 層明確處理。」

也就是說，**`SOURCE_DEGRADED`／`SOURCE_FAILED` 這兩個狀態的判定邏輯，依 Gate 0 已核准的
契約文字，明確是 `UG-G2-SB2` 的工作範圍，不是本 SB**。但 Master Plan 目前 `UG-G2-SB1` 的
`Dependency` 欄只寫「`UG-G1-SB4`」，未列 `UG-G2-SB2`——這是一個需要在完整 Brief 中補上的
相依關係缺口（詳見 §7 決策點 3）。

另外，目前系統是**單一資料來源（僅 PTT）**，`SOURCE_DEGRADED`（部分來源失敗、部分成功）
這個語意在只有一個來源時邏輯上不可能發生——它是為未來多來源（Dcard／Threads）預留的狀態，
現在寫入這個 CHECK 約束值域是對的（架構前瞻），但**本 SB 實際上只可能寫出 `SUCCESS` 與
`SUCCESS_EMPTY` 兩種值**，這點在驗收時必須誠實揭露，不得宣稱四態全部驗證過。

---

## 2. Requirement Source

- `doc/upgrade/contracts/DB_MIGRATION_PLAN.md` §4.2（Gate 0 交付物 E，已核准，含完整 DDL）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md`（29 欄契約定義、`LEGACY_17`／`CORE_16` 版本化命名）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §7（三態結果契約）
- `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` DRIFT-003（本 SB 的原始登錄問題）
- `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-006（Migration 失敗風險）、RISK-015（情緒覆蓋率，本 SB 的 `source_status` 是其量測基礎）

---

## 3. Proposed Change

### 3.1 Migration：`database/migrations/002_expand_ml_features.sql`

直接採用 `DB_MIGRATION_PLAN.md` §4.2 已核准之完整 DDL（22 個 `ALTER TABLE ADD COLUMN IF NOT EXISTS`
+ 3 個冪等 CHECK constraint 區塊 + `schema_version` 自我登記列），逐字複製，不重新設計。
透過 `database/apply_migrations.py`（`UG-G1-SB4` 建立）套用，套用前強制經過
`assert_safe_migration_target()` 護欄。

### 3.2 `db_writer.py`：`upsert_ml_features()` 擴充至 29 欄

`target_cols` 清單從 7 欄擴充至 29 欄；`INSERT ... ON CONFLICT DO UPDATE` 的 `SET` 子句同步
擴充。不存在於輸入 DataFrame 的欄位（如 `target_triple_barrier`、留言特徵）維持寫入 `NULL`，
不得補 0 或中立值（`CLAUDE.md` §7.1 不變量）。

### 3.3 `feature_aggregator.py`：接線既有計算 + 新增 `source_status` 判定

1. **接線**：`generate_daily_features()` 回傳的 DataFrame 已包含 9 個 LEGACY_17 已算欄位，
   確認這些欄位名稱與 29 欄契約完全一致（逐欄核對，不假設命名相符）。
2. **新增 `source_status` 判定邏輯**（依 §7 決策點 1 之 PO 裁決結果實作）：
   建議設計——`SUCCESS` 當 `direct_count > 0 OR theme_count > 0`；否則 `SUCCESS_EMPTY`。
   `SOURCE_DEGRADED`／`SOURCE_FAILED` 本 SB 不產生（見 §1.3），欄位值域仍完整定義供未來使用。
3. **不實作**：CORE_16 新特徵（`amplitude_ratio` 等 4 個）、Triple-Barrier、留言特徵——
   對應欄位存在於 Schema，但本 SB 寫入 `NULL`，交由各自負責的未來 SB／Gate 實作。

### 3.4 `label_reason` 判定

`append_target_labels()` 已有 `label_end_date` 邏輯（`UG-G1-SB1` 成果），可據此推導
`insufficient_data`（資料集最後 H 個交易日）；`no_entry`（`Open[T+1]` 不存在）需新增判定；
`ambiguous_dual_barrier` 屬 Triple-Barrier 語意，本 SB 不產生（該邏輯不存在於本 SB 範圍）。
即本 SB 只會用到 `label_reason` 值域中的 `insufficient_data`／`no_entry`／`NULL` 三者。

---

## 4. Data/API/Schema Contract

依 `DB_MIGRATION_PLAN.md` §4.2 逐字執行，不新增契約內容。`source_status`／`label_reason`
的 CHECK constraint 已在核准 DDL 中定義，本 SB 不修改值域，僅新增判定該用哪個值的**程式邏輯**
（DDL 本身早已核准；本 SB 新增的是 Python 層「怎麼決定寫哪個值」，非 SQL 層修改）。

---

## 5. Failure Semantics

- 特徵計算失敗（如上游 `df_prices` 為空）：`generate_daily_features()` 已有既定行為
  （回傳空 DataFrame + WARNING log），本 SB 不變更此行為。
- Migration 失敗：`apply_migrations.py` 既有機制（單一遷移獨立 transaction，失敗 ROLLBACK，
  版本不推進），本 SB 不修改該機制本身，僅新增一個要被套用的遷移檔案。
- `source_status`／`label_reason` 寫入不符合 CHECK constraint 值域時：DB 層直接拒絕該筆
  INSERT（constraint violation），不會靜默寫入不合法值——這是選擇「讓 DB 當最後防線」而非
  僅靠 Python 端驗證。

---

## 6. Risks & Trade-offs

| 風險 | 說明 | 因應 |
|------|------|------|
| RISK-006（Migration 失敗風險） | 本 SB 是 `UG-G1-SB4` 之後第一個新增真實 Migration 的 SB；pg_dump 備份還原尚未在真實情境驗證過 | 隔離臨時 DB 驗證 + 遵循 `DB_MIGRATION_PLAN.md` §6 九項安全保證；若對真實開發 DB 執行，依既有流程紀律先 `pg_dump` |
| `source_status` 語意不完整 | 本 SB 只能產生 `SUCCESS`／`SUCCESS_EMPTY`，`SOURCE_DEGRADED`／`SOURCE_FAILED` 要等 `UG-G2-SB2`（單一來源例外傳播）與未來多來源 SB 才可能出現 | 驗收報告明確揭露此邊界，不宣稱四態全部驗證；`REMAINING_RISKS.md` RISK-015 的覆蓋率量測在本 SB 完成後即可開始運作（`SUCCESS`/`SUCCESS_EMPTY` 已足夠支撐覆蓋率計算），不受此邊界阻擋 |
| CORE_16／Triple-Barrier／留言特徵欄位長期為 NULL | 29 欄中有 8 欄在本 SB 之後仍全為 NULL，直到各自的 SB／Gate 完成 | 這是刻意設計（Additive Migration 允許欄位先於邏輯存在），非缺陷；`FEATURE_REGISTRY.md` 已標註各欄位所屬版本化契約 |
| DRIFT-003 登錄文字本身有「27 欄」與「29 欄」不一致 | `DOCUMENT_DRIFT_REMEDIATION.md:30`（DRIFT-003）與 Master Plan SB1 Brief 的 `Tests` 欄（`test_feature_store_total_columns_27`、`test_dbwriter_upsert_27_columns`）仍寫「27」，但 Master Plan §7.1（V8 修正說明）已改為 29——與 Gate 1 SB5 剛處理過的「18 欄位」硬編碼是**同一類問題的另一個尚未修正的實例** | 本 SB 的完整 Brief／測試命名一律使用 29（或版本化契約名稱），不沿用「27」；是否同時修正 DRIFT-003 原文與 Master Plan 該欄，屬 §7 決策點 2 |

---

## 7. PO 決策點

### 決策點 1：`source_status` 的 `SUCCESS`／`SUCCESS_EMPTY` 判定邏輯

**建議方案**：`direct_count > 0 OR theme_count > 0` → `SUCCESS`；否則 `SUCCESS_EMPTY`。
**理由**：DEC-009 已核准題材溢出情緒為合法的 30% 加權輸入，不是雜訊；一檔股票即使零直接文章、
只靠題材溢出，`sentiment_mean` 仍帶有真實訊號（非中立值填補），把它標為 `SUCCESS_EMPTY`
會低估其真正的資料覆蓋率，也會讓 RISK-015 未來的覆蓋率評估把「有溢出訊號」的股票誤判為
「無資料」。

**替代方案**：僅以 `direct_count > 0` 判定 `SUCCESS`（忽略溢出）——缺點是與上述理由相反，
可能高估「零覆蓋」股票的比例，讓 RISK-015 評估過度悲觀。

若無 PO 明確選擇，本 SB 依建議方案實作。

### 決策點 2：DRIFT-003 與 Master Plan SB1 Brief 的「27 欄」殘留是否本次一併修正

`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-003 原文）與 `SYSTEM_UPGRADE_MASTER_PLAN.md`
（SB1 Brief `Tests` 欄）皆殘留「27」，與已核准的 V8 修正（29 欄）不一致。
比照 Gate 1 SB5 對 `DECISIONS.md` 既有 ADR 的處理慣例——`DOCUMENT_DRIFT_REMEDIATION.md`
屬 `doc/evidence/`「只增不減」範圍，若要修正比照 SB5 方案（原文不動 + 補充註記）；
Master Plan 屬現行文件，可直接修正。是否本次一併處理，或留待未來一次性文件校正批次？

### 決策點 3：Master Plan SB1 完整 Brief 的 `Dependency` 欄補充

依 §1.3 發現，`source_status` 的 `SOURCE_DEGRADED`／`SOURCE_FAILED` 判定邏輯依 Gate 0 契約
明確屬 `UG-G2-SB2` 範圍，但現行 Master Plan 精簡 Brief 只列 `UG-G1-SB4` 為 Dependency。
本 SB 完整 Brief 是否應新增「（軟性）依賴 UG-G2-SB2 以取得完整四態語意」的註記——不阻擋
本 SB 開工（本 SB 只寫兩態），但避免未來誤以為 `source_status` 已完整可信。

---

## 8. In / Out of Scope

**In Scope**：`database/migrations/002_expand_ml_features.sql`（新增，逐字採用已核准 DDL）；
`db_writer.py` `upsert_ml_features()` 擴充至 29 欄；`feature_aggregator.py` 接線 9 個
LEGACY_17 已算欄位、3 個 Target 欄位、新增 `source_status`（兩態）與 `label_reason`
（`insufficient_data`／`no_entry`／`NULL` 三值）判定邏輯。

**Out of Scope**：CORE_16 新特徵計算（`amplitude_ratio` 等 4 個，欄位加入但邏輯不實作）；
Triple-Barrier 標籤邏輯（Gate 3）；留言衍生特徵（`UG-G2-SB4`）；`source_status` 的
`SOURCE_DEGRADED`／`SOURCE_FAILED` 判定（`UG-G2-SB2` 與未來多來源 SB）；`schema.sql`
的欄位回寫（依 `DB_MIGRATION_PLAN.md` §9.2，待遷移穩定後才回寫，非本 SB）。

---

## 9. Affected Components

`database/migrations/002_expand_ml_features.sql`（新）、`src/loaders/db_writer.py`、
`src/transform/feature_aggregator.py`、`tests/test_apply_migrations.py`（新增 002 相關案例）、
新增測試檔或擴充既有測試檔（見 §10）。

---

## 10. Tests（修正 Master Plan 殘留的「27」命名）

- `test_feature_store_total_columns_29`（非 27——見 §6 風險列、§7 決策點 2）
- `test_migration_002_idempotent`
- `test_dbwriter_upsert_29_columns`
- `test_source_status_success_when_direct_articles_present`
- `test_source_status_success_when_only_spillover_present`（驗證決策點 1 的判定邏輯）
- `test_source_status_success_empty_when_no_articles`
- `test_label_reason_insufficient_data_at_dataset_tail`
- `test_label_reason_no_entry_when_open_t1_missing`
- `test_label_reason_target_triple_barrier_consistency_constraint`（DB CHECK 層驗證，非 Python 邏輯）
- `test_null_not_zero_for_unimplemented_columns`（CORE_16／留言／Triple-Barrier 欄位確認為 `NULL` 而非 0 或中立值）

---

## 11. E2E Verification Plan

比照 Gate 1（UG-G1-SB4）既有慣例：獨立隔離臨時 DB（獨立容器、非 `postgres-data` 掛載、
distinct port），流程：`init_db.py` → `apply_migrations.py`（含 001+002）→ 驗證 29 欄存在、
CHECK constraint 生效、`source_status`／`label_reason` 值域正確、冪等性（重跑無錯誤）。
需 PO 依 RISK-013 協定確認綁定目標後才可執行。

---

## 12. Documentation Sync

`FEATURE_REGISTRY.md`（欄位狀態由「計劃中」更新為對應本 SB 完成後的實際狀態）、
`doc/spec/SDD_Financial_Sentiment_System_v1.md`（`daily_ml_features` 欄位數更新）、
`PROJECT_STATUS.md`（SB 進度）；DRIFT-003 狀態更新依 §7 決策點 2 結果處理。

---

## 13. Rollback

見 `DB_MIGRATION_PLAN.md` §7 五層 Rollback 策略；本 SB 僅涉及純加法 DDL，正常情況下
L1～L4（不需 PO 核准）已足夠因應。

---

## 14. Definition of Done

- 29 欄 Migration 已套用（隔離臨時 DB 驗證）；`db_writer.py` 寫入 29 欄；15 個既有計算欄位
  正確接線；`source_status`（兩態）／`label_reason`（三值）判定邏輯正確；CORE_16／Triple-Barrier／
  留言欄位確認為 `NULL`（非 0／中立值）；§10 全部測試 PASS；契約驗證與既有測試無回歸。

---

## 15. 待 PO 裁決事項彙總

1. **決策點 1**：`source_status` 判定邏輯——建議方案（含溢出視為 `SUCCESS`）／替代方案（僅直接文章）。
2. **決策點 2**：DRIFT-003 與 Master Plan「27→29」殘留是否本次一併修正。
3. **決策點 3**：Master Plan SB1 完整 Brief 是否新增對 `UG-G2-SB2` 的軟性依賴註記。
4. 是否核准依 §8 範圍開始實作。
