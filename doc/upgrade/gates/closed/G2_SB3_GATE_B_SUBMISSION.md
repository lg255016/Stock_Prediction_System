# UG-G2-SB3 Gate B 送審文件：`market_articles` Schema 擴充

> 狀態：**待 PO 審查**
> 日期：2026-08-27
> 對應提案：`doc/upgrade/gates/G2_SB3_GATE_A_PROPOSAL.md`（已核准，含 §1.5／§1.6 Gate A 階段修正）

---

## 1. 摘要

依核准之 §7 範圍完成實作：Migration 003（5 欄 + `chk_comment_counts_nonneg` + 決策點 2
核准補上的 `provider_article_id` 一般索引）、`db_writer.py` 擴充至 13 欄寫入契約、
`provider_article_id` 產生邏輯。隔離臨時 DB 完整 E2E 驗證通過。

**Gate A 審查階段已完成的兩項修正**（PO 發現，本 SB 一併交付）：
`MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的 `DEFAULT 0` 與 §4.3 直接矛盾，已修正；
`gate0_contract_check.py` 的 B4 檢查結構上抓不到該矛盾（只掃單一檔案、正則要求同一行），
已強化為跨全部 7 份文件掃描並支援多行 `ALTER TABLE` 寫法。

---

## 2. Diff 摘要（9 個檔案：5 modified + 4 new）

| 檔案 | 異動類型 | 行數（+/-） |
|------|---------|-------------|
| `database/migrations/003_expand_articles.sql` | 新增 | +55 / -0 |
| `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` | 修改（§2.2 移除 `DEFAULT 0` + 加註理由） | +15 / -8 |
| `doc/upgrade/gates/G2_SB3_GATE_A_PROPOSAL.md` | 新增（Gate A 提案，含 §1.5／§1.6／§6A） | +267 / -0 |
| `doc/upgrade/gates/G2_SB3_GATE_B_SUBMISSION.md` | 新增（本文件） | — |
| `scripts/verify/gate0_contract_check.py` | 修改（B4 跨文件強化） | +17 / -4 |
| `src/loaders/db_writer.py` | 修改（`ARTICLE_COLUMNS` 13 欄 + NaN→None 修正） | +38 / -8 |
| `src/transform/data_cleaner.py` | 修改（`build_ptt_provider_article_id()`） | +34 / -4 |
| `tests/test_apply_migrations.py` | 修改（fixture 改為動態取得最新版本號） | +7 / -2 |
| `tests/test_market_articles_contract.py` | 新增（11 個測試） | +184 / -0 |

---

## 3. 產出 1：契約驗證原始輸出

```bash
$ python scripts/verify/gate0_contract_check.py
...
B4   PASS | raw 層留言計數欄無 DEFAULT（反查法，跨全部文件、支援多行 ALTER TABLE）
       四欄型別: {'push_count': ['INT', 'INTEGER'], 'boo_count': ['INT', 'INTEGER'],
                  'neutral_count': ['INT', 'INTEGER'], 'total_comments': ['INT', 'INTEGER']}
...
B11  PASS | 全文件契約數字宣告一致（反查法）
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂
==================================================
Part B: 11/11 PASS
```

B4 現在同時掃到 `DB_MIGRATION_PLAN.md`（`INTEGER`）與 `MULTI_SOURCE_DATA_CONTRACT.md`
（`INT`）兩份文件的宣告，兩者皆無 `DEFAULT`——舊版只看得到前者。

---

## 4. 產出 2：執行環境、測試原始輸出

**Host（Windows，非支援環境，Python 3.10.11）**：

```bash
$ PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -p "test_*.py"
Ran 225 tests in 2.560s
OK
```

225 = 原 214 + 11 個本 SB 新增測試（`tests/test_market_articles_contract.py`）。

**Container（`stock_prediction_system2_devcontainer-app-1`，真實 `psycopg2` 路徑）**：
用於 §5 E2E 驗證。

---

## 5. 產出 3：E2E 驗證（隔離臨時 DB，非 `postgres-data` 掛載）

### 5.1 RISK-013 綁定確認（PO 已核可，並自行以 `assert_safe_migration_target()` 實測驗證）

```
db_config: {'host': 'g2sb3_articles_tmpdb', 'port': 5432,
            'database': 'g2sb3_articles_tmpdb', 'user': 'tmpuser', 'password': 'tmppass'}
BINDING（DB 端自陳）: ('g2sb3_articles_tmpdb', 'tmpuser', 5432)
```

獨立容器（host port 55442 對外），非真實開發 DB。驗證後已 `docker rm -f` 拆除。

### 5.2 Fresh Init + Migration（001 + 002 + 003）

```
$ python database/init_db.py
資料庫初始化已成功 commit。

$ python database/apply_migrations.py
[apply_migrations] 目前已套用版本：v0
[apply_migrations] 正在套用 v1（001_baseline.sql）... v1 已套用並 COMMIT。
[apply_migrations] 正在套用 v2（002_expand_ml_features.sql）... v2 已套用並 COMMIT。
[apply_migrations] 正在套用 v3（003_expand_articles.sql）... v3 已套用並 COMMIT。
[apply_migrations] 完成，已套用至 v3。
```

### 5.3 Schema 驗證（15 欄、無 `DEFAULT`、CHECK、索引型態）

```
COLUMN COUNT: 15
   ('push_count', 'integer', None)          ← column_default 為 None，確認無 DEFAULT 0
   ('boo_count', 'integer', None)
   ('neutral_count', 'integer', None)
   ('total_comments', 'integer', None)
   ('provider_article_id', 'text', None)
CHECK CONSTRAINTS: [('chk_comment_counts_nonneg',)]
INDEX: idx_articles_provider_id → CREATE INDEX ... USING btree (provider_article_id)   ← 一般索引
INDEX: market_articles_url_key  → CREATE UNIQUE INDEX ... USING btree (url)            ← UNIQUE 仍在 url
SCHEMA_VERSION: v1 / v2 / v3
```

`provider_article_id` 的索引確認為**一般 btree 索引**，非 `UNIQUE`；`url` 的 UNIQUE
約束不受影響（`MULTI_SOURCE_DATA_CONTRACT.md` §2.3）。

### 5.4 冪等性驗證

```
$ python database/apply_migrations.py
[apply_migrations] 目前已套用版本：v3
[apply_migrations] 無待執行遷移，已是最新版本。
```

### 5.5 NULL vs 0 語意驗證（真實 DB 寫入）

| 情境 | 寫入路徑 | DB 實際結果 |
|------|---------|------------|
| 未解析留言（走既有 `clean_ptt_data()` 列表頁流程） | `clean_ptt_data()` 輸出 9 欄 → `upsert_to_market_articles()` 補 4 欄 `None` | `('未解析留言的文章', engagement_metric=100, push_count=None, boo_count=None, total_comments=None, provider_article_id='ptt_Stock_M.1.A.1')` |
| 已解析且確實零則留言 | 直接提供計數 `0` | `('零則留言的文章', engagement_metric=None, push_count=0, boo_count=0, total_comments=0, provider_article_id='ptt_Stock_M.2.A.2')` |

兩種狀態在 DB 層可正確區分——`NULL`（尚未解析）與 `0`（已解析、零則留言）。
`provider_article_id` 由 `clean_ptt_data()` 自 `url` 正確推導。

### 5.6 CHECK constraint 與 `ON CONFLICT DO NOTHING` 驗證

```
CHECK CONSTRAINT ENFORCED: new row for relation "market_articles"
    violates check constraint "chk_comment_counts_nonneg"          ← 負數計數被 DB 拒絕

BEFORE re-upsert: (count=1, max(push_count)=0)
（以同一 url、push_count=999、title='嘗試覆寫' 重新 upsert）
AFTER re-upsert:  (count=1, max(push_count)=0, max(title)='零則留言的文章')   ← 完全未變動
```

確認 `ON CONFLICT (url) DO NOTHING` 依 §2.3 契約運作：重複 url 不新增、不覆寫任何欄位。

---

## 6. 產出 4：格式／行尾夾帶偵測

```bash
$ git diff --numstat > raw.txt && git diff --numstat -w > nows.txt && diff raw.txt nows.txt
5,6c5,6
< 38	8	src/loaders/db_writer.py
< 34	4	src/transform/data_cleaner.py
---
> 35	5	src/loaders/db_writer.py
> 31	1	src/transform/data_cleaner.py
```

**兩個檔案各有 3 行純空白差異，共 6 行**（`db_writer.py` 3 行、`data_cleaner.py` 3 行），
皆為原檔案中帶行尾空格的空白行在編輯時被改為真正的空行，內容邏輯無任何損失。

**揭露時機的檢討**：本項在前兩個 SB（`UG-G2-SB1` 的 `db_writer.py` 6 行、`UG-G2-SB2` 的
15 行）均由 PO 發現後才補上揭露，本次是第三次。PO 已明確要求：實作完成回報時就附上
numstat 比對結果，不等 Gate B 文件、更不等 PO 抓。已列為後續固定動作。

---

## 7. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 說明 |
|------|---------|-------------------|
| Migration 003 於隔離 DB 成功套用且冪等 | `VERIFIED THIS SESSION` | §5.2、§5.4（container，`g2sb3_articles_tmpdb`，已拆除） |
| 四個留言計數欄無 `DEFAULT`（DB 層實證） | `VERIFIED THIS SESSION` | §5.3，`information_schema.columns.column_default` 皆為 `None` |
| `provider_article_id` 索引為一般索引非 UNIQUE | `VERIFIED THIS SESSION` | §5.3，`pg_indexes.indexdef` 原始輸出 |
| NULL（未解析）與 0（零則留言）在 DB 層可區分 | `VERIFIED THIS SESSION` | §5.5 真實寫入後查詢 |
| `chk_comment_counts_nonneg` 生效 | `VERIFIED THIS SESSION` | §5.6，負數 INSERT 被 `CheckViolation` 拒絕 |
| `ON CONFLICT DO NOTHING` 不覆寫既有列 | `VERIFIED THIS SESSION` | §5.6，re-upsert 前後 count／push_count／title 皆未變 |
| NaN→None 轉換已修正 | `VERIFIED THIS SESSION` | §8 known-FAIL 案例（PO 亦獨立做過 mutation 測試確認） |
| B4 檢查已具備跨文件偵測力 | `VERIFIED THIS SESSION` | §8 known-FAIL 案例（PO 亦獨立重跑確認） |
| 全套測試 225/225 OK（host，回歸確認） | `VERIFIED THIS SESSION` | §4 |
| `parse_article_comments()` 仍無呼叫端（本 SB 依決策點 1 選項 A 不接線） | `VERIFIED THIS SESSION` | `grep -rn "parse_article_comments" src/ main_etl_pipeline.py` 僅命中定義；已依 §9 登記待辦 |

---

## 8. 產出 6：Known-FAIL 案例對照表

| # | 檢查 | Known-FAIL 案例 | 實測結果 | 復原確認 |
|---|------|-----------------|---------|---------|
| 1 | `db_writer.py` NaN→None 轉換（留言計數欄） | 暫時還原 `DataFrame.where(pd.notnull(df), None)` 寫法，重跑 `test_upsert_converts_nan_to_none_in_pure_numeric_columns` | `FAIL — AssertionError: nan is not None`（型態 `<class 'float'>`） | 已還原；`grep KNOWN-FAIL` 無殘留；全套 225/225 OK。PO 亦獨立做過同一 mutation 測試 |
| 2 | `gate0_contract_check.py` B4 跨文件偵測 | 暫時在 `MULTI_SOURCE_DATA_CONTRACT.md` §2.2 加回一處 `push_count INT DEFAULT 0`（多行 `ALTER TABLE` 寫法） | `B4 FAIL`，精確指出 `MULTI_SOURCE_DATA_CONTRACT.md:push_count=INT DEFAULT 0` | 已還原；`Part B: 11/11 PASS`。PO 亦獨立重跑確認 |
| 3 | `chk_comment_counts_nonneg`（DB 層） | 對隔離 DB 直接 `INSERT ... push_count = -1` | `psycopg2.errors.CheckViolation: violates check constraint "chk_comment_counts_nonneg"` | 該筆已 `rollback()`，未進入資料 |
| 4 | `ON CONFLICT DO NOTHING` 不覆寫 | 以同一 url、`push_count=999`、不同 title 重新 upsert | 既有列完全未變（count=1、push_count=0、title 未變） | 無需復原（本來就不該寫入） |

---

## 9. 與提案的差異／需登記的待辦

### 9.1 `provider_article_id` 實作位置（PO 已核准此判斷）

提案 §8 的 Affected Components 列的是 `db_writer.py`，實際實作放在
`src/transform/data_cleaner.py` 的 `build_ptt_provider_article_id()`，並由
`clean_ptt_data()` 呼叫。理由：這是「由 `url` 推導欄位」的轉換工作，與
`engagement_metric`（由 `push_count` 徽章推導）、`post_time`（由 `date` 推導）同類，
本來就都在 `clean_ptt_data()` 內完成；放進 loader 層會讓載入層開始承擔轉換責任。
PO 於審查時確認此判斷成立，不需搬回。

### 9.2 待辦：`parse_article_comments()` 尚無呼叫端（決策點 1 選項 A 的必要登記）

`UG-G2-SB2` 已完成內頁留言解析能力、`UG-G2-SB3` 已完成 Schema 與寫入契約，但兩者之間
**尚未接線**——`main_etl_pipeline.run_ptt_pipeline()` 目前仍只走列表頁。接線牽涉
「單篇內頁失敗時整篇跳過還是缺值寫入」與請求量節流策略等獨立語意決策，依 PO 裁決不與
Schema 擴充擠在同一個 SB。**須於 Master Plan 後續 SB Brief 或 `REMAINING_RISKS.md`
明確登記**，避免留下「能力齊備但沒人用」且無人追蹤的狀態。

### 9.3 潛在地雷登記：`push_count` 在兩層有不同語意（PO 於審查時指出）

| 層 | `push_count` 含意 | 型態 |
|----|------------------|------|
| `ptt_scraper.scrape_ptt_stock_by_keyword()` 輸出 | 列表頁推文徽章**文字**（「爆」「12」「X3」） | `str` |
| `market_articles.push_count`（DB） | 內頁**真實推文則數** | `INTEGER` |

**目前安全**，因為 `clean_ptt_data()` 的 `final_cols` 不含徽章欄位——徽章在該函式內
經 `_parse_push_count()` 轉為 `engagement_metric` 後即被丟棄，不會流到 DB 層。
**但 SB4 接線時若有人把 scraper 的原始 DataFrame 直接餵進 `upsert_to_market_articles()`，
「爆」這個字串就會撞上 `INTEGER` 欄位**。此提醒須隨 §9.2 的待辦一併登記。

### 9.4 附帶修正：`test_apply_migrations.py` fixture 改為版本無關

`test_no_pending_migrations_skips_execution_and_returns_zero` 原本寫死「最新版本 = v2」，
`UG-G2-SB1` 新增 002 時壞過一次、本 SB 新增 003 又壞一次。已改為由
`_discover_migrations()[-1][0]` 動態取得，之後新增 migration 不會再無謂地弄壞它。
此為附帶修正，非提案原始範圍。

---

## 10. Definition of Done 對照

- [x] `market_articles` 擴充至 15 欄，Migration 已於隔離臨時 DB 套用且冪等。
- [x] `upsert_to_market_articles()` 正確寫入 13 欄（不含 `article_id`／`created_at`）。
- [x] 留言計數欄未解析時為 `NULL`（非 0），已解析零則留言時為 `0`——兩種狀態皆實證可區分。
- [x] `provider_article_id` 格式正確，索引為一般索引非 UNIQUE。
- [x] `ON CONFLICT (url) DO NOTHING` 維持不變（§6A 契約）。
- [x] §9 測試 PASS（225/225）；契約驗證 11/11 PASS，無回歸。
- [x] `DEFAULT 0` 矛盾已修正、B4 檢查已強化並附 known-FAIL。
- [ ] §9.2／§9.3 的待辦登記——**待 PO 裁示登記位置**（Master Plan 後續 SB Brief
      或 `REMAINING_RISKS.md`），本文件先行記錄。

---

## 11. 待 PO 裁決事項

1. 是否核准本次 commit（9 個檔案：5 modified + 4 new，清單見 §2）。
2. §6 已揭露的 6 行純空白差異（`db_writer.py` 3 行、`data_cleaner.py` 3 行）是否同意隨本次一併 commit。
3. §9.2（`parse_article_comments()` 待接線）與 §9.3（`push_count` 雙語意地雷）要登記在哪裡——
   Master Plan 的 `UG-G2-SB4` Brief、`REMAINING_RISKS.md` 新增風險項，或兩者皆是？
