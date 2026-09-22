# UG-G2-MIG Gate B 送審：真實開發資料庫 Migration 同步（RISK-017）

> 日期：2026-08-31
> Gate A 提案：`doc/upgrade/gates/closed/G2_MIGRATION_SB_GATE_A_PROPOSAL.md`（PO 2026-08-30 核准）
> 狀態：**待 PO 審查。尚未 commit。**

---

## 1. 交付摘要

**本專案第一次真正的整合驗證。** 至今所有 E2E 都在拋棄式容器裡跑，
`run_feature_engineering_pipeline()` 從未對真實開發庫執行過——
今天它跑起來了，而且六項寫死的預期全部相符。

| 步驟 | 內容 | 結果 |
|------|------|------|
| 1 | `pg_dump` 備份 **+ 實際還原至臨時容器驗證** | ✅ 四項判準全過（RISK-006 的還原流程**第一次實地驗證**） |
| 2 | 套用 migration 001～004 至 `postgres`@`localhost:5432` | ✅ 全部 COMMIT 至 v4；**一項不符：欄數預期是提案自己寫錯** |
| 3 | 對真實庫執行完整 feature pipeline | ✅ 六項預期全部相符 |

---

## 2. 三個步驟的原始輸出

### 2.1 步驟 1：備份與還原驗證

備份自 **db 容器**（app 容器無 `pg_dump`，Gate A §1.3 已先查明）：

```
pg_dump -U postgres -d postgres --format=custom  →  36,506 bytes
pg_restore -U postgres -d restore_tmpdb --no-owner --no-privileges  →  EXIT=0
```

| 判準 | 結果 |
|------|------|
| 7 張表全部存在 | ✅ 真實庫 7 / 還原庫 7，表名集合相同 |
| 每張表列數 | ✅ 331／117／117／5／36／26／36 逐表相符 |
| `market_articles` 欄數 = 10（**遷移前**狀態） | ✅ 兩邊皆 10 |
| 抽樣：最新 5 筆 `article_id`／`url`／`sentiment_score` | ✅ 逐欄 MATCH |

還原容器 `mig_restore_tmpdb`（匿名 volume、無 `postgres-data`、bridge 網路、port 55441）已拆除。

### 2.2 步驟 2：套用 migration

```
[apply_migrations] 目前已套用版本：v0
[apply_migrations] 正在套用 v1（001_baseline.sql）... v1 已套用並 COMMIT。
[apply_migrations] 正在套用 v2（002_expand_ml_features.sql）... v2 已套用並 COMMIT。
[apply_migrations] 正在套用 v3（003_expand_articles.sql）... v3 已套用並 COMMIT。
[apply_migrations] 正在套用 v4（004_comment_scrape_timestamp.sql）... v4 已套用並 COMMIT。
[apply_migrations] 完成，已套用至 v4。      EXIT=0
```

`schema_version` 四列：

```
v1 | Baseline: create schema_version table            | 2026-08-30 17:20:07.530219
v2 | Expand daily_ml_features: add 22 columns (29-c…  | 2026-08-30 17:20:07.794886
v3 | Expand market_articles: add nullable push/boo/…  | 2026-08-30 17:20:07.852810
v4 | Add comments_scraped_at to market_articles for…  | 2026-08-30 17:20:07.904013
```

| 表 | 遷移前 | 遷移後 | 列數 |
|----|--------|--------|------|
| `market_articles` | 331 列 10 欄 | 331 列 **16 欄** | 不變 |
| `daily_ml_features` | 117 列 7 欄 | 117 列 **29 欄** | 不變 |
| `stock_prices` | 117 列 8 欄 | 117 列 8 欄 | 不變 |
| `entity_mapping` | 5 列 4 欄 | 5 列 4 欄 | 不變 |
| `theme_stock_mapping` | 36 列 5 欄 | 36 列 5 欄 | 不變 |
| `tracking_keywords` | 26 列 4 欄 | 26 列 4 欄 | 不變 |
| `sentiment_cache` | 36 列 2 欄 | 36 列 2 欄 | 不變 |
| `schema_version` | 不存在 | 4 列 4 欄 | 新表 |

DB 大小 8430 kB → 8526 kB。

**Gate A §5.5 的兩個預測，現在是實測**：

- `chk_comments_scraped_at_consistency` = `(comments_scraped_at IS NULL AND total_comments IS NULL) OR (…)`；
  **331/331 列兩欄皆 NULL**，第一分支成立。
- `provider_article_id` 索引為 `CREATE INDEX idx_articles_provider_id`（**非 UNIQUE**）。

### 2.3 步驟 3：對真實庫執行 pipeline

**未設定覆寫**（`DBWriter` 不經 `db_target_guard`，設了反而是把不該存在的習慣帶進來）。

```
========== 啟動 ML 特徵工程管線 ==========
[INFO] [Feature] 開始聚合特徵：股價 117 筆, 文章 331 筆 (Cutoff: 15:30:00)
[INFO] [Feature] 特徵表聚合完成！

[Load] 準備寫入 117 筆特徵數據至 daily_ml_features...
[Load] 成功執行資料庫作業。已處理 117 筆資料。
EXIT=0
```

唯一 warning：`google.generativeai` 套件支援已結束的 `FutureWarning`
（NLPProcessor 初始化時觸發，本次未實際呼叫 LLM）→ **已登記 RISK-019**。

---

## 3. §6.1 六項預期逐項比對

| # | 預期 | 實際 | |
|---|------|------|---|
| 1 | 執行成功，不再 `UndefinedColumn` | `EXIT=0` | ✅ |
| 2 | **三個留言特徵全部 `NULL`** | 非 NULL 列數 = **0** | ✅ |
| 3 | 逐欄指名（改寫後，見 §4） | 逐欄相符 | ✅ |
| 4 | 29 欄 | 29 欄 | ✅ |
| 5 | `source_status` 有值 | `SUCCESS_EMPTY` 80、`SUCCESS` 37 | ✅ |
| 6 | 列數維持 **117** | 117，不增不減 | ✅ |

### 3.1 第 2 項是本 SB 最重要的一項

331 筆 `total_comments` 全為 NULL → 三個留言特徵全部 NULL，
**沒有任何一列產出偽造的 `comment_polarization = 1.0`**。

**修正前的程式碼在這批資料上會產出 117 列全是 `1.0` 的假訊號。**
`UG-G2-SB5` 決策點 5 的修正**第一次在真實資料上被證明有效**。

### 3.2 `market_articles` 未被改動——已驗證，非假設

```
步驟 3 前：331 列，md5 = b08c8fdab9ff6853e837dac12d19475c
步驟 3 後：331 列，md5 = b08c8fdab9ff6853e837dac12d19475c
```

md5 取自 `article_id||url||sentiment_score` 全表排序後彙總，**逐字元相同**。

---

## 4. 【要記取】§6.1 第 3 項的驗證方法太窄

初稿的第 3 項寫「價量與情緒特徵**正常產出**」，驗證方式是抽驗
`close_price` 117 列、`sentiment_mean` 117 列、`article_count>0` 37 列，然後判定 ✅。

**這個預期在欄位粒度上不可證偽**——它沒說哪幾欄、幾列。
而抽驗的三欄**剛好都是有值的那一批**。

### 4.1 逐欄填充表（29 欄，總列數 117）

| 欄位 | 非 NULL | 判定 |
|------|--------|------|
| `trade_date`／`stock_id`／`close_price`／`volume`／`article_count` | 117 | 應為 117 ✅ |
| `sentiment_mean`／`sentiment_3d_ma`／`sentiment_5d_ma` | 117 | 應為 117 ✅ |
| `sentiment_lag_1`／`sentiment_lag_2` | 117 | 應為 117 ✅ |
| `return_1d`／`rsi_14`／`volatility_5d`／`volatility_20d` | 117 | 應為 117 ✅ |
| `bullishness_index`／`agreement_index`／`source_status` | 117 | 應為 117 ✅ |
| **`amplitude_ratio`／`ma5_bias_ratio`／`ma20_bias_ratio`／`volume_ratio_5d`** | **0** | **應為 0**——契約標 `PLANNED` |
| `comment_volume_ratio`／`comment_polarization`／`net_push_momentum` | **0** | **應為 0**——留言未回填（§3.1） |
| `target_next_close`／`target_return_1d`／`target_up_down` | **113** | **應為 113**（§4.3） |
| `target_triple_barrier`／`label_reason` | **0** | **應為 0**——Gate 3 範圍 |

### 4.2 那四欄不是缺陷（已查證）

`FEATURE_REGISTRY.md:108-111` 對 `amplitude_ratio`／`ma5_bias_ratio`／
`ma20_bias_ratio`／`volume_ratio_5d` 的 `Status` 欄明寫 **`PLANNED`**、
Source 欄寫「**待實作於 `feature_aggregator.py`**」。
`grep` 這四個名字於 `feature_aggregator.py` → **零命中**。
`db_writer.py:531-534` 的「欄位不在 DataFrame 就填 `None`」讓它們靜靜寫成 NULL。

**這是已登記的延後，本 SB 不需要處理。**

### 4.3 【正面證據】`target` 欄 113/117 是防前視偏誤的實證

那 4 個 NULL 的分佈：

| stock_id | NULL 的 trade_date | 該檔最後交易日 |
|----------|-------------------|---------------|
| 2330 | 2026-08-20 | 2026-08-20 |
| 2382 | 2026-08-20 | 2026-08-20 |
| 6488 | 2026-08-21 | 2026-08-21 |
| NVDA | 2026-08-20 | 2026-08-20 |

**4 檔 × 各自最後一個交易日 = 恰好 4 列，117 − 4 = 113。**

這正是 `generate_target_labels()` 防前視偏誤的設計行為（每檔最後一日無未來資料 → NaN），
而且**這是它第一次在真實資料上被驗證**。

### 4.4 這與 §9A.1 的 B4 grep 是同一個形狀

**檢查只看了已知沒問題的地方。** 本次結果無害，
但**方法本身不會告訴你它無害**——是逐欄查過才知道。

Gate A §6.1 第 3 項已改寫為可證偽形式（逐欄指名應為 117／0／113 及各自原因）。

---

## 5. 一個數字巧合，已排除

`SUCCESS_EMPTY = 80` 與「命中 `entity_mapping` 的文章 = 80/331」**分母不同**
（117 個「交易日×股票」組合 vs 331 篇文章）。

更硬的理由：**`SUCCESS_EMPTY` 必然等於 `117 − SUCCESS = 117 − 37 = 80`**，
它由 117 與 37 算術決定，與 331 篇裡有 80 篇命中 `entity_mapping` **無因果關係**。

---

## 6. RISK-015 實測底數

| stock_id | `SUCCESS` / 總列數 | 覆蓋率 |
|----------|------------------|--------|
| 2330 | 11/14 | **78.6%** |
| 6488 | 8/25 | 32.0% |
| NVDA | 16/64 | 25.0% |
| 2382 | 2/14 | **14.3%** |

整體 **37/117 = 31.6%**，最高與最低差 **5.5 倍**。
文章面：**80/331** 命中 `entity_mapping` 且已完成 NLP。

樣本只有 4 檔、117 列，**還不足以證實或推翻 RISK-015 的假設**
（「小型概念股討論量不一定低於大型權值股」），
但**覆蓋率在股票之間高度不均**這點現在有實測數字。

---

## 7. 版本偵測交付（RISK-017 緩解第 3 條）

`scripts/verify/check_schema_version.py` —— **唯讀**，只執行 `SELECT`。

| 案例 | 目標 | 輸出 | 退出碼 |
|------|------|------|--------|
| A 對照組 | 真實庫（v4） | 「已是最新（v4）」 | **0** |
| B **known-FAIL** | 全新空庫（`schema_version` 不存在） | 「**落後 4 個版本**」，逐一列出 v1～v4 | **1** |
| C **known-FAIL** | 刻意停在 v2 的臨時 DB | 「**落後 2 個版本**」，列出 v3／v4 | **1** |

**案例 B 正是 RISK-017 的真實形狀**——腳本明確區分
「`schema_version` 表不存在（migration 機制從未在此資料庫執行過）」
與「表存在但版本落後」，因為那是兩件不同的事。

臨時容器 `schemaver_tmpdb` 已拆除。

---

## 8. 全套測試與 §0.5 #8

| 項目 | 結果 |
|------|------|
| 全套測試（隔離臨時 DB `migsb_final_tmpdb`，已套用 001～004） | **`Ran 269 tests` / `OK`** |
| `tests.schema_smoke_ui_data_loader` | **`Ran 4 tests` / `OK`** |
| RISK-013 綁定確認 | `current_database() = migsb_final_tmpdb`、`DB_PORT = 55445`、匿名 volume、無 `postgres-data` |
| contract-check | `exit 0` |

**本 SB 未修改 `src/`**，基線維持 269 / 26 檔。臨時容器已拆除。

---

## 9. 兩份備份

```
D:\Python\Database_Backups\Stock_Prediction_System2\
  stock_prediction_system2_pre_migration_20260831_004705.dump    36,506 bytes
  stock_prediction_system2_post_migration_20260831_012248.dump   40,933 bytes
```

- **在 repo 之外**（`git` 回報 `outside repository`），`git status` 無任何 dump 檔
- 原 scratchpad 副本**已移除**（無並存，避免日後不知哪份是準的）
- 命名依既有慣例 `{專案}_{標籤}_{YYYYMMDD}_{HHMMSS}.dump`
- **保留至本 SB 結案**
- 第二份依 PO 指示**未再做完整還原驗證**——還原流程已於步驟 1 驗證，重複不增加資訊

**第二份備份的價值**（PO 2026-08-31 指出，Gate A 未寫）：
用遷移前的備份回滾，等於必須**再跑一次 migration** 才能回到可用狀態——
那又是一次需要覆寫、需要重新授權的真實庫寫入。
一次還原會變成「還原 + 再遷移 + 再驗證」三步。
**第二份備份讓步驟 3 的回滾變成單一動作**，成本是 36 KB 和幾秒鐘。

---

## 10. 欄數修正：預期先寫死抓到的不是 migration 的錯，是提案自己的錯

步驟 2 實測 `market_articles` **16 欄**，而 Gate A 提案寫死的預期是 **15**。
依 §6.1 規則**停止並回報，未自行調整預期**。

追查結果：**資料庫是對的，錯的是提案。**

```
10（schema.sql 基礎）＋ 5（003）＋ 1（004）＝ 16
```

`15` 是 `UG-G2-SB3` 當時的**正確**數字（該 SB 只做到 003），
但 `UG-G2-SB4` 的 004 又加了一欄，而這個數字沒有被更新。

**已核准文件無一宣稱 post-004 是 15 欄**（PROJECT_STATUS 的 SB3 列寫
「Migration 003（15 欄…）」是描述 003 做了什麼，正確）。
錯誤只在兩處，皆為本次新寫：Gate A 提案（§1.1／§5.4／§11 DoD）
與 `REMAINING_RISKS.md` RISK-018（已 commit 於 `a049748`）。
**PO 核准後已全部修正為 16，並寫明算式**。

> **如果當初把 16 猜對了，這個算術錯誤會靜靜留在 DoD 和 RISK-018 裡沒人發現。**
> **一個檢查抓到「非它原本要抓的東西」，這是它有效的最強證據。**
> 這是本專案第二次證明先寫死預期有用（第一次是 `UG-G2-SB5` 決策點 6 的 A6）。

---

## 11. 驗證邊界【必讀】

- **本次驗證的是欄位填充狀態與列數，不是逐列數值正確性。**
  117 列的特徵值未經人工逐列核算——計算邏輯由既有 269 個測試涵蓋，
  但**在真實資料上的逐列核算沒做**。不得把本 SB 讀成「特徵值已驗證正確」。
- 只驗證了 `run_feature_engineering_pipeline()`，
  **未執行** `run_all_daily_tasks()`（爬蟲與 NLP 路徑未觸及）。
- RISK-015 的覆蓋率數字取自 4 檔股票、117 列，**樣本不足以支撐分佈結論**。

---

## 12. 逐檔授權稽核（§12.3）

| 檔案 | 變更 | 授權狀態 |
|------|------|---------|
| `scripts/verify/check_schema_version.py` | 新建 | In Scope（Gate A §8） |
| `doc/upgrade/gates/closed/G2_MIGRATION_SB_GATE_A_PROPOSAL.md` | 新建＋收尾修訂 | 過程文件 |
| `doc/upgrade/gates/closed/G2_MIGRATION_SB_GATE_B_SUBMISSION.md` | 新建（本檔） | 過程文件 |
| `doc/upgrade/contracts/REMAINING_RISKS.md` | RISK-013 措辭修正、RISK-017 狀態更新、RISK-018 欄數修正、RISK-019 新增、Summary 計數 | In Scope（PO 逐項指示） |
| `doc/evidence/TRACEABILITY.md` | §2 回填 DEC-024～027 | In Scope（Gate A §9） |
| `doc/governance/PROJECT_STATUS.md` | §0.5 第 10 項規則修補、新增第 11 項、§0.2 本 SB 列 | In Scope（Gate A §9） |

**超出 Gate A 列舉範圍者：無。**
RISK-013 措辭修正與 RISK-018 欄數修正皆為**修正已 commit 內容中的錯誤**，
由 PO 於 2026-08-31 逐項指示，於此主動揭露。

---

## 13. Definition of Done 對照（每一項指名資料庫）

| DoD | 狀態 |
|-----|------|
| `pg_dump` 備份已產出且已還原至獨立臨時容器逐項比對通過 | ✅ §2.1 |
| **`postgres`@`localhost:5432`** 的 `schema_version` 存在且 `MAX(version) = 4` | ✅ |
| **`postgres`@`localhost:5432`** 的 `market_articles` 有 **16** 欄 | ✅ |
| **`postgres`@`localhost:5432`** 的 `daily_ml_features` 有 **29** 欄 | ✅ |
| **`postgres`@`localhost:5432`** 的七張表列數與遷移前完全相同 | ✅ |
| `run_feature_engineering_pipeline()` 對 **`postgres`@`localhost:5432`** 實際執行成功，六項預期逐項比對 | ✅ §3 |
| `check_schema_version.py` 已交付，含 known-FAIL 實際輸出 | ✅ §7 |
| §0.5 規則修補與 DEC-024～027 的 §2 回填 | ✅ |
| 覆寫環境變數**未寫入任何檔案** | ✅ `git diff` 無任何相關字串 |
| 全套測試在隔離臨時 DB 通過 | ✅ 269 / OK |
| contract-check `exit 0`；無夾帶格式／行尾變更 | ✅ |

---

## 14. PO 裁示與收尾調整（2026-08-31）

| # | 事項 | 裁示 | 處置 |
|---|------|------|------|
| 1 | commit | **核准，拆兩個**（腳本一個、文件一個） | 已執行 |
| 2 | RISK-017 標記 | **判斷正確，但保留 `OBSERVED`**——`OBSERVED（實測日）→ MITIGATED（處置日）` **並列而非取代** | 已改寫 |

### 14.1 為什麼兩個狀態要並列

**「我們量測到它是真的」與「我們處置到什麼程度」是兩件事，後者不會取消前者。**

只寫 `MITIGATED` 會把實測證據從狀態欄擠掉——
`market_articles` 10 欄／`daily_ml_features` 7 欄／`schema_version` 表不存在——
未來讀者將看不出這條風險曾被**實地量測過**。

RISK-017 是 High、會被反覆閱讀，兩個資訊都該留著。

### 14.2 狀態欄本來就混著兩個軸——登記為另案，本次不順手統一

該欄現有詞彙：`HYPOTHESIS`／`NOT VERIFIED`／`OBSERVED`／`VERIFIED`／
`VERIFIED（部分）`／**`PLANNED`**／**`MITIGATED`**。
其中 `PLANNED` 與 `MITIGATED` 是**處置狀態**，其餘是**證據狀態**。

**這不是本 SB 引入的**（`PLANNED` 早於本 SB 即存在），`MITIGATED` 只是延續。
**本次刻意不順手統一整欄**——那需要先決定要不要拆成兩欄，
在未決定前統一只是把混淆換個形式。已登記為 `PROJECT_STATUS.md` §0.5 **第 13 項**。

### 14.3 緩解第 2 條需要一個具名的觸發點——已登記為 §0.5 第 12 項

「DoD 措辭必須指名目標資料庫」目前**只是一條寫在 RISK-017 緩解欄裡的文字，
沒有任何觸發機制**。

而本專案**已三次證明「規則沒有觸發機制就會被漏掉」**：
§0.5 第 7 項在 `UG-G1-SB1` 結案時「揭露了卻沒有執行」；
第 8 項的說明自己寫著「綁編號就會再度落空」（而它確實在
`UG-G2-SB5` 可用性驗證判 `FAIL` 時差點落空）；`evidence-sync` §2.1 的 C-5 發生了三次。

觸發條件已寫成**「每一個會動 schema 或資料庫的 SB 撰寫 Gate A 提案時」**，
比照第 9／10 項的綁事件寫法。放本清單或放 `gate-submit` skill 檢查清單待 PO 裁示。

**本項不阻擋 commit**，但不得只活在 RISK-017 的緩解欄裡。

---

## 15. 待 PO 決定

1. §0.5 第 12 項的位置：本清單 vs `gate-submit` skill 檢查清單。
