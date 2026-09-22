# UG-G2-MIG Gate A 提案：真實開發資料庫 Migration 同步（RISK-017）

> 狀態：**Gate A 審查中**。**核准前不得對真實開發庫執行任何寫入。**
> 日期：2026-08-30
> Gate：UG-Gate-2（PO 2026-08-30 定序：決策點 5 → **本 SB** → UG-G2-SB6 → SB7 → Gate 2 關閉）
> 依據：RISK-017（High）、Gate 2 關閉條件第五項

---

## 0. 摘要

本 SB 要關掉的缺口：**真實開發資料庫從未套用過任何一次 migration。**
四個 migration 全部只在拋棄式臨時 DB 裡跑過，
而每個 SB 的 DoD 都只涵蓋「臨時 DB 內驗證通過」——
**「臨時 DB 會過」與「真實環境能跑」之間沒有任何一步把它們接起來。**

本 SB 的真正價值不在遷移本身，而在第 3 步：
**這會是本專案第一次真正的整合驗證。** 至今所有 E2E 都在拋棄式容器裡。

**同時這是升級專案至今第一次對綁著 `postgres-data` 的真實開發庫執行寫入**，
因此 §5（守門覆寫）與 §4（備份）是本提案最需要被審查的部分。

---

## 1. Current State（唯讀查詢，`VERIFIED THIS SESSION`）

### 1.1 真實開發庫現況

連線目標：`current_database()` = `postgres`、`localhost:5432`
（app 容器 `network_mode: service:db`，直達綁定 `.devcontainer/postgres-data/` 的真實庫）。

| 表 | 列數 | 欄數 | migration 後應為 |
|----|------|------|-----------------|
| `market_articles` | 331 | **10** | **16**（見下方算式） |
| `daily_ml_features` | 117 | **7** | 29 |
| `stock_prices` | 117 | 8 | 8（不變） |
| `entity_mapping` | 5 | 4 | 4（不變） |
| `theme_stock_mapping` | 36 | 5 | 5（不變） |
| `tracking_keywords` | 26 | 4 | 4（不變） |
| `sentiment_cache` | 36 | 2 | 2（不變） |
| **`schema_version`** | — | — | **不存在**（migration 001 才會建立） |

- 資料庫大小：**8430 kB**（備份規模極小，非效能考量）
- 331 篇文章**全部**已完成 NLP（`sentiment_score IS NOT NULL`）
- `market_articles.source` 全為 `ptt_stock`

> **【2026-08-31 修正】`market_articles` 遷移後應為 16 欄，不是 15。**
> 算式：**10（`schema.sql` 基礎）＋ 5（migration 003：`push_count`／`boo_count`／
> `neutral_count`／`total_comments`／`provider_article_id`）＋ 1（migration 004：
> `comments_scraped_at`）= 16**。
>
> 本提案初稿寫「15（migration 003＋004）」——**把 003 之後的數字當成 003+004 之後的數字**。
> `15` 是 `UG-G2-SB3` 當時的**正確**數字（該 SB 只做到 003），
> 但 `UG-G2-SB4` 的 004 又加了一欄，而這個數字沒有被更新。
>
> **這個錯誤是被「預期先寫死」抓到的**：步驟 2 實測 16 欄與寫死的 15 不符，
> 依 §6.1 的規則停止回報，追查後發現不符的是提案而不是資料庫。
> 若當初猜對了 16，這個算術錯誤會靜靜留在 DoD 與 RISK-018 裡。
> 同一個錯誤已傳播至 `REMAINING_RISKS.md` RISK-018（已隨本 SB 修正）。

### 1.2 目前的失敗點（實測，非推論）

`db_writer.fetch_all_for_features()` 的查詢原文對真實庫執行：

```
UndefinedColumn: column "push_count" does not exist
```

`run_feature_engineering_pipeline()`（`main_etl_pipeline.py:170-190`）
**對真實開發庫跑會直接失敗**。失敗是大聲的（`fetch_data` 為 `try/finally` 無 `except`，
呼叫端亦無 `try/except`），**未被偽裝成空結果**（§7.1 合規）。

### 1.3 `pg_dump` 在哪裡——**app 容器沒有**

| 容器 | `pg_dump` |
|------|----------|
| `stock_prediction_system2_devcontainer-app-1` | **不存在** |
| `stock_prediction_system2_devcontainer-db-1` | **`pg_dump (PostgreSQL) 18.6`** |

**因此備份必須從 db 容器執行**，不是從 app 容器。
這一點如果沒先查清楚，會在執行當下才發現，而那時已經處在「準備寫入真實庫」的狀態。

---

## 2. Requirement Source

- `REMAINING_RISKS.md` **RISK-017**（High，2026-08-30 登記）三條緩解
- `REMAINING_RISKS.md` **RISK-006**：pg_dump 還原流程**從未驗證過**
- **Gate 2 關閉條件第五項**（Master Plan §8，2026-08-30 新增）
- `CLAUDE.md` §3（不得以「重建環境」為由執行破壞性資料庫操作；
  physical data directory **不等於**可攜式備份）、§7.1（不得 destructive migration）
- `DECISIONS.md` DEC-010（分層 Rollback 策略）、DEC-021（RISK-013 根本解）

---

## 3. 三個步驟（PO 定案，缺一件就是重犯同一個錯）

| # | 內容 | 為什麼不能省 |
|---|------|-------------|
| 1 | `pg_dump` 備份，**並實際還原到臨時 DB 驗證它能還原** | RISK-006 明載還原流程**從未驗證過**。**做一份沒試過能否還原的備份，跟現在這個缺口是同一種病** |
| 2 | 套用 001～004，逐項比對欄數與 `schema_version` | 缺口本身 |
| 3 | **實際對真實庫跑一次完整 pipeline**，記錄結果 | 只遷移 schema 而不跑，等於在更小的尺度上重犯——**「schema 對了」不等於「系統能跑」** |

---

## 4. 步驟 1：備份與**還原驗證**

### 4.1 備份

```bash
docker exec stock_prediction_system2_devcontainer-db-1 \
  pg_dump -U <user> -d postgres --format=custom --file=/tmp/pre_mig_backup.dump
docker cp stock_prediction_system2_devcontainer-db-1:/tmp/pre_mig_backup.dump \
  <host 上的證據路徑>
```

**必須是 `pg_dump` logical backup。**
依 `CLAUDE.md` §3，**`.devcontainer/postgres-data/` 不得被當成備份**——
那是 physical data directory，不是可攜式備份。

### 4.2 還原驗證（RISK-006 的第一次實地驗證）

還原到**獨立臨時容器**（名稱含 `tmp`，不掛 `postgres-data`，獨立埠），並比對：

| 比對項 | 判準 |
|--------|------|
| 7 張表全部存在 | 表名集合完全相同 |
| 每張表列數 | 與 §1.1 完全相同（331／117／117／5／36／26／36） |
| `market_articles` 欄數 | 10（還原的是**遷移前**的狀態） |
| 抽樣內容 | `market_articles` 最新 5 筆的 `article_id`／`url`／`sentiment_score` 逐欄相同 |

**任一項不符 → 停止，不進行步驟 2。**
備份不可還原時繼續遷移，等於沒有回復方案。

---

## 5. 步驟 2：套用 migration —— **守門覆寫是本提案最需要被審查的一步**

### 5.1 `db_target_guard` 會怎麼擋

`database/db_target_guard.py` 的 `assert_safe_migration_target()`
由 `database/apply_migrations.py:106` 在**建立連線之前**呼叫（連線在 `:114`）。

對真實庫 `postgres`@`localhost:5432`，**兩個訊號同時觸發**：

| 訊號 | 判斷 | 真實庫 |
|------|------|--------|
| A `_is_unmodified_default_endpoint` | `host == "localhost" and port == 5432` | **觸發** |
| B `not _is_recognized_temp_db_name` | database 名稱不含 `tmp`／`temp`／`test` | **觸發**（名稱為 `postgres`） |

→ `raise SystemExit`，**不建立任何連線**。

### 5.2 覆寫的唯一方式

```
CONFIRM_REAL_DB_MIGRATION_TARGET=I_UNDERSTAND_THIS_WRITES_TO_THE_REAL_DEV_DB
```

（`db_target_guard.py:19-20` 的 `_CONFIRM_ENV_VAR` 與 `_CONFIRM_REQUIRED_VALUE`。）

### 5.3 這個覆寫**會在哪一行、由誰、在什麼前提下設定**

| 項目 | 內容 |
|------|------|
| **在哪裡** | **不寫進任何檔案。** 僅作為 `docker exec -e` 的單次行內環境變數，隨該次指令結束即消失 |
| **由誰** | PM 執行，且**僅在本 SB 的步驟 2 執行當下**。**不得**寫入 `.env`／`docker-compose.yml`／`devcontainer.json`／任何腳本 |
| **前提** | (a) 步驟 1 的備份**與還原驗證**皆已完成並回報；(b) 已完成 RISK-013 綁定確認呈報並取得 PO 明示放行；(c) 該次指令**只跑 `apply_migrations.py`**，不附帶其他動作 |
| **範圍** | 只有步驟 2 這一次。步驟 3 跑 pipeline **不需要也不得設定它**（見 §6.3） |

> **為什麼刻意不寫進檔案**：寫進檔案的覆寫會**一直有效**，
> 而這個覆寫的全部價值就在於「它只在被刻意打開的那一刻有效」。
> 一個常駐的覆寫等於把 RISK-013 的根本解關掉。

### 5.4 套用後的逐項比對

| 比對項 | 預期 |
|--------|------|
| `schema_version` 表 | 存在，`MAX(version) = 4` |
| `market_articles` 欄數 | 10 → **16**（10 ＋ 003 的 5 ＋ 004 的 1） |
| `daily_ml_features` 欄數 | 7 → **29** |
| 各表列數 | **完全不變**（331／117／117／5／36／26／36） |
| `chk_comments_scraped_at_consistency` | 存在且成立 |

### 5.5 三個必須先講清楚的細節

1. **`apply_migrations.py` 不建立基礎 schema。** 決策點 5 的臨時 DB 實測顯示：
   對空庫直接跑 `apply_migrations.py`，**002 會因 `daily_ml_features` 不存在而失敗並 ROLLBACK**，
   必須先跑 `init_db.py`。**本 SB 不需要也不得跑 `init_db.py`**——
   真實庫的基礎 schema 已存在，跑它有覆寫風險。此處僅記錄，避免執行時誤判。
2. **migration 004 的 CHECK 對 331 筆既有資料成立**（預期）：
   003／004 新增的欄位無 `DEFAULT`，既有列的 `total_comments` 與 `comments_scraped_at`
   **皆為 NULL**，滿足「同時為 NULL 或同時非 NULL」。
   **這是預測，不是事實**——若 004 失敗，那是一個發現。
3. **001～004 在乾淨 schema 上套用全程無誤**（複查方 2026-08-30 於
   `sb5dp5_review_tmpdb` 實測）。真實庫有資料，情況不完全相同，
   但 **DDL 本身沒問題**這一點已有旁證。

---

## 6. 步驟 3：對真實庫跑一次完整 pipeline

### 6.1 【核心】跑之前先寫死預期結果

> 比照 `UG-G2-SB5` §3 判準先定死的作法：**在跑之前就把預期寫進提案，
> 跑完只做比對，不做解釋。**

| # | 預期 | 推導依據 |
|---|------|---------|
| 1 | `run_feature_engineering_pipeline()` **執行成功，不再 `UndefinedColumn`** | 欄位已由 003／004 建立 |
| 2 | **三個留言特徵全部為 `NULL`** | 331 筆的 `total_comments` 從未回填、全為 NULL → `_aggregate_direct_comment_counts()` 的 `total_comments.notna()` 過濾濾掉全部 → 回 `_empty_daily_comments()` → `_compute_comment_features()` 中 `has_volume`／`has_direction` 皆 False |
| 3 | **【2026-08-31 改寫為可證偽形式】** 逐欄指名：`close_price`／`volume`／`article_count`／`sentiment_mean`／`sentiment_3d_ma`／`sentiment_5d_ma`／`sentiment_lag_1`／`sentiment_lag_2`／`return_1d`／`rsi_14`／`volatility_5d`／`volatility_20d`／`bullishness_index`／`agreement_index`／`source_status` **應為 117/117 非 NULL**；`amplitude_ratio`／`ma5_bias_ratio`／`ma20_bias_ratio`／`volume_ratio_5d` **應為 0/117**（契約 `FEATURE_REGISTRY.md:108-111` 標 `PLANNED`「待實作於 `feature_aggregator.py`」，`grep` 該四名於 `feature_aggregator.py` 零命中）；`target_triple_barrier`／`label_reason` **應為 0/117**（Gate 3 範圍，DEC-018／DEC-023）；`target_next_close`／`target_return_1d`／`target_up_down` **應為 113/117**（每檔股票最後一個交易日無未來資料 → NULL，4 檔 × 1 = 4） | 117 筆股價 × 5 個 `entity_mapping` 關鍵字，331 篇文章全部已完成 NLP |

> **【本項為何要改寫】** 初稿寫「價量與情緒特徵**正常產出**」，**在欄位粒度上不可證偽**——它沒說哪幾欄、幾列。
> 實際驗證時抽驗了 `close_price`／`sentiment_mean`／`article_count` 三欄，而那三欄**剛好都是有值的那一批**；
> **若那四個 `PLANNED` 欄真的是缺陷，這個檢查抓不到**。
> 這與 `CLAUDE.md` §9A.1 的 B4 grep 是同一個形狀：**檢查只看了已知沒問題的地方。**
> 本次結果無害，但**方法本身不會告訴你它無害**——是逐欄查過才知道。
| 4 | `daily_ml_features` 由 7 欄 117 列 → **29 欄**，列數由 upsert 決定 | `upsert_ml_features` 走 29 欄寫入契約 |
| 5 | `source_status` 欄有值（`SUCCESS`／`SUCCESS_EMPTY` 等） | `UG-G2-SB1` 已實作。**不預先猜測分佈**——實際比例為未知，跑完才記錄 |
| 6 | **`daily_ml_features` 列數維持 117，不增不減** | `upsert_ml_features()` 為 `ON CONFLICT (trade_date, stock_id) DO UPDATE SET`；`stock_prices` 有 117 個相異 `(trade_date, stock_id)` 組合，`daily_ml_features` 現有亦為 117——同一組主鍵，全部走 UPDATE。**若跑完列數變多，代表特徵層產出了 `stock_prices` 沒有的組合，那是一個發現** |

**PO 的預測與本提案一致**（第 2 項）。兩邊獨立推導出相同結論，
但**這仍然只是預測**——

> **如果跑出來不是這樣，那就是一個發現，不是一個要被解釋掉的意外。**
> 不符時：完整記錄實際結果、停止後續動作、回報 PO，**不得調整預期使其相符**。

### 6.2 只跑特徵工程，**不跑爬蟲與 NLP**

只呼叫 `run_feature_engineering_pipeline()`，**不呼叫** `run_all_daily_tasks()`。

理由：後者會觸發 PTT 爬蟲與 Gemini API 呼叫——**對外網路請求與 API 成本**，
且與本 SB 要驗證的事（schema 遷移後 pipeline 能不能跑）無關。

### 6.3 【必須揭露】步驟 3 的寫入**不受任何守門保護**

`upsert_ml_features()` 經 `DBWriter` 寫入，
而 **`DBWriter` 的寫入方法本身不呼叫 `assert_safe_migration_target()`**——
守門只裝在 `apply_migrations.py`。這是 RISK-013／DEC-021 已登記的**剩餘缺口**
（「機制依賴呼叫端主動呼叫，未強制耦合於 `DBWriter` 寫入方法本身」）。

**後果**：步驟 3 **不需要**設定覆寫環境變數就能寫入真實庫。

**因此步驟 3 的保護只有流程紀律，沒有技術護欄。**
本提案的處置：

1. 步驟 3 執行前**再次呈報綁定確認**（`current_database()`、埠、目標表），取得 PO 放行。
2. 步驟 3 **只寫 `daily_ml_features`**（pipeline 該階段的唯一寫入目標），
   **不觸及 `market_articles`／`stock_prices`** 等原始資料表。
3. 備份（步驟 1）此時已完成且**已驗證可還原**——這是步驟 3 的回復依據。

> 這一項**不是本 SB 要修的**（修它等於改 `DBWriter` 的寫入路徑，範圍另計），
> 但**必須被知道**：否則「有守門」會給人一種步驟 3 也被保護著的錯覺。

---

## 7. In / Out of Scope

**In Scope**：§3 三個步驟；版本偵測交付（§8）；
`PROJECT_STATUS.md` §0.5 第 10 項規則缺口修補與 DEC-024～027 的 §2 回填（§9）。

**Out of Scope**：
- 修 `DBWriter` 寫入路徑的守門缺口（§6.3，範圍另計）
- `TRACEABILITY.md` §2「總計」列的更新（§9.3，另案，本提案只登記判準）
- RISK-016／RISK-018 的修法
- 任何 `src/` 功能變更（本 SB 只交付版本偵測腳本，不改既有模組）

---

## 8. 版本偵測交付（RISK-017 緩解第 3 條）

**現在沒有任何東西會告訴你真實庫在第幾版**——`schema_version` 表在真實庫根本不存在。
前兩條緩解處理**已知的這一次**，第三條才讓**下一次能被發現**。

交付 `scripts/verify/check_schema_version.py`：

| 行為 | 內容 |
|------|------|
| 讀取 | 連線目標的 `schema_version`（不存在 → 版本 0） |
| 比對 | `database/migrations/` 下的最高版本號 |
| 輸出 | 目標資料庫名稱、host:port、已套用版本、可用最高版本、**是否落後** |
| 退出碼 | 落後 → 非 0；一致 → 0 |
| 保證 | **唯讀**，只執行 `SELECT`；不呼叫守門（無寫入） |

**known-FAIL 案例**：對一個刻意停在 v2 的臨時 DB 執行 → 必須非 0 且指出落後 2 版。
不出示這個案例，這支腳本不計入證據（§9A.2）。

---

## 9. 連帶處理：§0.5 第 10 項的規則缺口（PO 指示隨本 SB 一起帶）

### 9.1 缺口

§0.5 第 10 項寫「補進 `TRACEABILITY.md` **§3.2**」，**未涵蓋 §2 追溯矩陣**。
實測：§2 裡 DEC-024／025／026／027 出現次數**各為 0**，只有 DEC-028 有一列。

**這是上一輪剛立的規則，第二次生效時就露出缺口。**
不現在補，DEC-029 會用一模一樣的方式漏掉——**那正是 C-5 的形狀**。

### 9.2 處置

1. §0.5 第 10 項改為「補進 **§3.2 與 §2**」。
2. 回填 DEC-024／025／026／027 的 §2 追溯矩陣列。
3. **隨本 SB 的 commit 一起帶**，不另開 commit。

### 9.3 §2「總計」列過期 —— 另案，但先登記判準

`TRACEABILITY.md:66` 仍為
`9 大核心 ADR + 7 大挑戰｜18 大核心生產模組｜17 大測試套件檔案｜154 項測試｜100% PASS`，
現行是 **269／26 檔**、ADR 已到 **028**。

本提案**不修**（半修比不修更誤導），但登記 PO 指定的判準，
使另案有辦法動手：

> **§2 裡的數字要先分成「當前狀態宣稱」與「歷史執行紀錄」，
> 前者必須更新，後者絕對不能動。**
>
> `:66` 的總計列是**當前狀態宣稱**，必須更新；
> 而 `:164-165` 的 `Ran 154 tests in 1.486s / OK` 加上「PO 獨立複驗得 1.643s」
> 是**某一次執行的歷史紀錄**，改它就是**竄改證據**。

沒有這個判準，「更新總計」很容易變成把歷史紀錄一起改掉。

---

## 10. Rollback

| 層級 | 內容 |
|------|------|
| L1 | migration 以 transaction 執行，單一 migration 失敗即 ROLLBACK 且版本不推進（DEC-010，`UG-G1-SB4` 已實測） |
| L2 | 步驟 3 只寫 `daily_ml_features`；該表可由 pipeline 重新產生 |
| L5 | **`pg_dump` 完整還原** —— 本 SB 的步驟 1 使其**第一次成為經過驗證的選項**（RISK-006） |

**不使用**：刪除／重建 `postgres-data`（`CLAUDE.md` §3 明文禁止）。

---

## 11. Definition of Done —— **指名資料庫**（RISK-017 緩解第 2 條的第一個示範）

> 以下每一項都指名目標資料庫。
> 對照組：`UG-G2-SB1` 的 DoD 寫「`daily_ml_features` **有 29 欄**」——
> **沒說哪一個資料庫**，因此在 `g2sb1_ml_features_tmpdb` 裡達成就算滿足，
> 而那個容器已拆除。SB3／SB4 同一套寫法。**不修這條，下一個動 schema 的 SB 會再過一次。**

- [ ] `pg_dump` 備份已產出，**且已還原至獨立臨時容器並逐項比對通過**（§4.2）。
- [ ] **`postgres`@`localhost:5432`** 的 `schema_version` 表存在且 `MAX(version) = 4`。
- [ ] **`postgres`@`localhost:5432`** 的 `market_articles` **有 16 欄**
      （10 基礎 ＋ migration 003 的 5 ＋ migration 004 的 1）。
- [ ] **`postgres`@`localhost:5432`** 的 `daily_ml_features` **有 29 欄**。
- [ ] **`postgres`@`localhost:5432`** 的七張表列數與遷移前完全相同。
- [ ] `run_feature_engineering_pipeline()` **對 `postgres`@`localhost:5432` 實際執行成功**，
      結果與 §6.1 的五項預期逐項比對並回報（**不符即回報不符，不調整預期**）。
- [ ] `scripts/verify/check_schema_version.py` 已交付，
      **含 known-FAIL 案例的實際執行輸出**。
- [ ] §9 的 §0.5 規則修補與 DEC-024～027 的 §2 回填已完成。
- [ ] 覆寫環境變數**未寫入任何檔案**（`git diff` 可核）。
- [ ] 全套測試在**隔離臨時 DB** 內執行通過（不因本 SB 而改變既有基線）。
- [ ] contract-check `exit 0`；無夾帶格式／行尾變更。

---

## 12. PO 決策點

### 決策點 1【阻擋執行】：是否核准對真實開發庫執行寫入

本 SB 是升級專案至今**第一次**對綁著 `postgres-data` 的真實開發庫寫入。
請確認：(a) §4 的備份與還原驗證方案是否足夠；
(b) §5.3 的覆寫使用方式（僅行內、不寫入任何檔案、只涵蓋步驟 2）是否可接受。

### 決策點 2：步驟 3 的無守門狀態（§6.3）是否需要額外保護

本提案的處置是「再次呈報綁定確認 + 只寫 `daily_ml_features` + 已驗證的備份」。
若你認為需要更強的保護（例如先為 `DBWriter` 寫入路徑加守門），
那會擴大範圍到 `src/`，需要明確授權。

### 決策點 3：執行分段回報的粒度

建議**三個步驟各自回報後才進行下一步**（步驟 1 → 呈報 → 步驟 2 → 呈報 → 步驟 3）。
這會多兩輪往返，但這是第一次對真實庫寫入。若你認為可以一次跑完再回報，請指示。

---

## 13. 待 PO 裁決事項彙總

| # | 事項 | 狀態 |
|---|------|------|
| 決策點 1 | 是否核准對真實庫寫入；備份與覆寫方案 | **待裁決** |
| 決策點 2 | 步驟 3 無守門狀態是否需額外保護 | **待裁決** |
| 決策點 3 | 分段回報粒度 | **待裁決**（建議三段） |
| — | 本提案整體是否核准 | **待裁決**（核准前不對真實庫執行任何寫入） |
