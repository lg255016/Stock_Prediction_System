# UG-G2-SB3 Gate A 提案：`market_articles` Schema 擴充

> 狀態：**Gate A 審查中**（尚未實作，未動 `src/`／`database/`）
> 日期：2026-08-27
> Gate：UG-Gate-2（已核准啟動，逐 SB 授權）
> 前置：UG-G2-SB1（CLOSED，commit `ef029a6`）、UG-G2-SB2（CLOSED，commit `543beb4`）

---

## 0. 摘要

`market_articles` 目前 10 欄（`article_id`／`source`／`fetch_keyword`／`post_time`／`title`／
`url`／`author`／`engagement_metric`／`sentiment_score`／`created_at`，含 `article_id`／
`created_at` 兩個自動欄位；`db_writer.py` 實際手動寫入的僅 8 欄），
`engagement_metric` 現行資料來源是**列表頁**的推文徽章文字（不是內頁真實推噓文），
`UG-G2-SB2` 新增的 `parse_article_comments()` 目前**完全沒有任何呼叫端**——它只是一個
待用的方法，尚未接進 `main_etl_pipeline.py` 的真實 ETL 流程。本 SB 的核心工作是 Schema
擴充（逐字採用 Gate 0 已核准 DDL）＋ `db_writer.py` 寫入邏輯更新；但實作前必須先解決一個
本次重新核對才發現、Gate 0 規劃時未想清楚的架構缺口——**究竟由誰、在什麼時機呼叫
`parse_article_comments()`**（§1.3、§6 決策點 1）。

---

## 1. Current State（重新對實際檔案核對）

### 1.1 `market_articles` 現況（`VERIFIED THIS SESSION`）

```sql
-- database/schema.sql:60-71
CREATE TABLE IF NOT EXISTS market_articles (
    article_id SERIAL PRIMARY KEY, source VARCHAR(20) NOT NULL, fetch_keyword VARCHAR(50),
    post_time TIMESTAMP NOT NULL, title TEXT NOT NULL, url TEXT UNIQUE, author VARCHAR(50),
    engagement_metric INT DEFAULT 0, sentiment_score NUMERIC(5, 4), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`src/loaders/db_writer.py` 的 `upsert_to_market_articles()` 寫入 8 欄
（`source, fetch_keyword, post_time, title, url, author, engagement_metric, sentiment_score`），
`ON CONFLICT (url) DO NOTHING`——**同一 URL 只會被寫入一次，之後重複遇到同一篇文章會被
整批跳過，不會更新任何欄位**。這對本 SB 的欄位擴充有直接影響，見 §1.3。

### 1.2 `engagement_metric` 目前資料來源與 SB2 產出的落差

`engagement_metric` 目前的值是 `data_cleaner.clean_ptt_data()` 從**列表頁** `push_count`
徽章（如「爆」「12」「X3」）轉換而來，不是內頁真實推噓文計算的
`push_count - boo_count`。`UG-G2-SB2` 的 `parse_article_comments()` 已能算出真正的
`engagement_metric`，但**這個函式從未被任何 pipeline 呼叫過**（`VERIFIED` —
全 repo grep `parse_article_comments` 僅命中定義與其自身測試檔）。

### 1.3 關鍵發現：Migration 只擴充 Schema，不會讓資料自動出現

`main_etl_pipeline.py` 的 `run_ptt_pipeline()` 現行流程：

```
scrape_ptt_stock_by_keyword()  →  clean_ptt_data()  →  upsert_to_market_articles()
```

全程只碰列表頁，從未進入任何文章內頁。**即使本 SB 把 `push_count`／`boo_count`／
`neutral_count`／`total_comments`／`provider_article_id` 五個欄位加進 Schema 與
`upsert_to_market_articles()` 的欄位清單，這條既有流程送進來的 DataFrame 依然不會有
這五個值**——欄位會存在，但持續寫入 `NULL`，直到有人接上 `parse_article_comments()`
的呼叫。這與 `UG-G2-SB1` 讓 CORE_16／Triple-Barrier 欄位「先建欄位、留給未來 SB 填值」
是同一種模式，但 Master Plan 對 SB3 的既定 `In Scope`（「`db_writer.py` 更新 upsert 邏輯」）
沒有明確排除「接上呼叫」這件事，需要 PO 決定本 SB 的邊界劃在哪裡（§6 決策點 1）。

### 1.5 `DEFAULT 0` 直接矛盾（PO 於 Gate A 審查時發現，比 §1.4 更嚴重，已修正）

`MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的欄位表與 Migration SQL 預覽，四個留言計數欄
（`push_count`／`boo_count`／`neutral_count`／`total_comments`）原文皆寫 `DEFAULT 0`，
與 `DB_MIGRATION_PLAN.md` §4.3 用一整段明文警告的「不得使用 `DEFAULT 0`」直接矛盾——
`DEFAULT 0` 會讓所有留言解析上線前既有的文章被回填成 `0`，使
`comment_polarization = 1 - push_ratio²` 在 `push_count = boo_count = 0` 時算出 `1.0`
（「散戶意見最大分歧」），這是完全偽造的強訊號，不是精度誤差。本提案原始版本
只 flag 了 §1.4 的型態矛盾（功能上 `TEXT` 與 `VARCHAR(100)` 無差異），漏了這個
「會不會偽造訊號」等級的矛盾。**已修正**：`MULTI_SOURCE_DATA_CONTRACT.md` §2.2
的表格與 SQL 預覽已改為與 §4.3 一致（移除 `DEFAULT 0`），並加註理由。

### 1.6 `gate0_contract_check.py` 的 B4 檢查結構上抓不到 §1.5 的矛盾（已修正）

B4（「raw 層留言計數欄無 DEFAULT」）舊版只掃描 `DB_MIGRATION_PLAN.md`
（`mig = D["DB_MIGRATION_PLAN.md"]`），且正則要求 `ALTER TABLE market_articles ADD COLUMN`
整句在同一行——`MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的多行 `ALTER TABLE` 寫法
（`ALTER TABLE market_articles` 與 `ADD COLUMN IF NOT EXISTS ...` 分行）兩個條件都不符合，
即使該份文件當時確實寫著 `DEFAULT 0`，B4 也結構上不可能命中。這正是 `CLAUDE.md` §9A.1
警告的「只看已知沒問題的地方」。**已修正**：B4 改為掃描全部 7 份受驗文件，且不再要求
`ALTER TABLE market_articles` 與 `ADD COLUMN` 同一行。Known-FAIL 案例：暫時在
`MULTI_SOURCE_DATA_CONTRACT.md` 重新加回一處 `DEFAULT 0`，重跑新版 B4 得到
`FAIL`，精確指出 `MULTI_SOURCE_DATA_CONTRACT.md:push_count=INT DEFAULT 0`；還原後重跑
`Part B: 11/11 PASS`。

### 1.4 `provider_article_id` 型態／索引在兩份 Gate 0 契約文件中不一致

- `DB_MIGRATION_PLAN.md` §4.3（實際要執行的 DDL）：`provider_article_id TEXT`，
  **無**額外 index。
- `MULTI_SOURCE_DATA_CONTRACT.md` §2.2：`provider_article_id VARCHAR(100)`，
  **明訂**需要 `CREATE INDEX ... ON market_articles(provider_article_id)`
  （用途：「輔助查詢與除錯」，§2.2 附註明確說明「不取代 `url` 的 UNIQUE 約束」——
  即這是一般索引，不是 UNIQUE 約束）。

兩者都是 Gate 0 已核准文件，型態與是否建索引互相矛盾，需要 PO 選擇如何調和（§6 決策點 2）。
Master Plan 的 SB3 測試清單裡 `test_provider_article_id_unique` 這個名稱容易讓人誤以為
DB 層有 `UNIQUE` 約束——依 `MULTI_SOURCE_DATA_CONTRACT.md` 原文，這個約束**不存在**，
測試驗證的應該是「函式邏輯上為不同文章產生不同 ID」，不是 DB constraint。

---

## 2. Requirement Source

- `doc/upgrade/contracts/DB_MIGRATION_PLAN.md` §4.3（Gate 0 交付物 E，已核准，含完整 DDL）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §2.2（`market_articles` 計畫新增欄位）、
  §3.1（`provider_article_id` 格式：`ptt_Stock_{article_filename}`）
- `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`（原始 §3.3 留言解析契約已於 `UG-G2-SB2` 落地）
- `G2_SB2_GATE_A_PROPOSAL.md` §1.3（本 SB 是 `UG-G2-SB2` 明確排出、留給後續處理的接線缺口）

---

## 3. Proposed Change

### 3.1 Migration：`database/migrations/003_expand_articles.sql`

逐字採用 `DB_MIGRATION_PLAN.md` §4.3 已核准 DDL（5 欄 `ALTER TABLE ADD COLUMN IF NOT EXISTS`
+ `chk_comment_counts_nonneg` 非負約束，四個留言計數欄**禁止 DEFAULT 0**——NULL＝尚未解析，
0＝已解析且確實零則留言，語意不可混淆，`DB_MIGRATION_PLAN.md` §4.3 已有詳盡理由說明）。
依 §6 決策點 2 之 PO 裁決，決定是否在此檔案內一併補上 `provider_article_id` 的索引。

### 3.2 `db_writer.py`：`upsert_to_market_articles()` 擴充

`INSERT` 欄位清單自 8 欄擴充至 13 欄（新增 5 欄）；缺欄位時寫 `NULL`（比照 `UG-G2-SB1` 的
`ML_FEATURE_COLUMNS` 模式，不存在的欄位一律補 `None`，不得補 0）。`ON CONFLICT (url)
DO NOTHING` **維持不變**，依 `MULTI_SOURCE_DATA_CONTRACT.md` §2.3 已核准之契約（見 §6A），
不併入留言計數回填邏輯。

### 3.3 `provider_article_id` 產生邏輯

依 `MULTI_SOURCE_DATA_CONTRACT.md` §3.1：`ptt_Stock_{article_filename}`，
`{article_filename}` 取自 `url` 去除副檔名與網域（如 `M.1787643158.A.FE2.html` →
`ptt_Stock_M.1787643158.A.FE2`）。純字串處理，不需額外請求。

---

## 4. Data/API/Schema Contract

依 §6 決策點 2 之裁決結果，統一 `provider_article_id` 的型態與索引宣告，兩份 Gate 0
文件中較不完整的一方需同步更新（現行文件，可直接修正，非 `doc/evidence/`）。

---

## 5. Risks & Trade-offs

| 風險 | 說明 | 因應 |
|------|------|------|
| 選項 A（決策點 1）讓 `parse_article_comments()` 持續閒置 | `UG-G2-SB2` 完成的解析能力沒有實際被使用，若未登記為待辦容易被遺忘 | 本 SB 完成時於 `REMAINING_RISKS.md` 或 Master Plan 後續 SB Brief 明確登記「留言計數解析已就緒，尚待接線」 |
| `MULTI_SOURCE_DATA_CONTRACT.md` §2.2 曾與 §4.3 矛盾（`DEFAULT 0`） | 已於 Gate A 審查時發現並修正（§1.5），本表列出供 Gate B 驗收對照 | 已修正；`gate0_contract_check.py` B4 已同步強化為跨文件掃描（§1.6） |

---

## 6. PO 決策點

### 決策點 1：本 SB 是否一併把 `parse_article_comments()` 接進 `main_etl_pipeline.py`

**選項 A（僅 Schema＋db_writer，不接線）**：比照 `UG-G2-SB1` 的 CORE_16 模式——本 SB 只加
欄位與擴充 `upsert_to_market_articles()` 能接受這些欄位，實際呼叫 `parse_article_comments()`
取得真實值留給下一個 SB。風險最低，但 `UG-G2-SB2` 完成的解析能力會繼續閒置，**必須明確
登記為待辦**（Master Plan 後續 SB Brief 或 `REMAINING_RISKS.md`），否則 SB2、SB3 做完後會
留下「能力齊備但沒人用」且無人追蹤的狀態。

**選項 B（本 SB 一併接線）**：`run_ptt_pipeline()` 對每篇列表頁文章呼叫
`parse_article_comments()`。接線牽涉「單篇內頁失敗時整篇跳過還是缺值寫入」這類獨立語意
決策，不應與 Schema 擴充擠在同一個 SB。

### 決策點 2：`provider_article_id` 型態與索引的兩份 Gate 0 文件如何調和

- **建議方案**：DDL 採 `TEXT`（`DB_MIGRATION_PLAN.md` 已核准之實際可執行 SQL為準，
  且 `TEXT` 在 PostgreSQL 是比 `VARCHAR(n)` 更慣用的任意長度字串型態，功能無差異）；
  但補上 `MULTI_SOURCE_DATA_CONTRACT.md` §2.2 明訂、`DB_MIGRATION_PLAN.md` DDL 原文
  遺漏的 `CREATE INDEX`（一般索引，非 `UNIQUE`）。
- **替代方案**：改型態為 `VARCHAR(100)` 貼合 `MULTI_SOURCE_DATA_CONTRACT.md` 逐字规格。

---

## 6A. 已由 Gate 0 契約回答、不列為決策點的事項

`MULTI_SOURCE_DATA_CONTRACT.md` §2.3「Upsert 策略演進」（已核准內容）明文回答了
`ON CONFLICT (url) DO NOTHING` 是否該改的問題，**答案與本提案原始版本假設的方向相反**：

> - 初次文章寫入：`ON CONFLICT (url) DO NOTHING`（現行行為，正確）
> - 留言計數更新：需獨立的 `UPDATE market_articles SET push_count=..., ... WHERE url=...` 路徑
> - 更新路徑應為獨立操作，不與初次 upsert 混合

即：**不改** `upsert_to_market_articles()` 的 `ON CONFLICT` 子句；未來若要回填留言計數
（無論是本 SB 選項 A 之後的待辦，或其他情境），走獨立的 `UPDATE ... WHERE url=...`，
不併入 upsert 邏輯。本提案原始版本把這件事列為「決策點 3」送 PO 裁決，是沒有先確認
Gate 0 契約是否已有答案——`UG-G2-SB2` 決策點 3（`main_etl_pipeline.py` 是否該接
`SOURCE_FAILED` catch）也是同一種情況（`MULTI_SOURCE_DATA_CONTRACT.md` §3.5 當時已明訂
答案）。連續兩次後已建立提醒機制：遇到「這件事要不要做」的問題，先查 Gate 0 契約
是否已有明文答案，有的話用引用取代裁決請求。

---

## 7. In / Out of Scope

**In Scope**：`database/migrations/003_expand_articles.sql`（新增，逐字採用已核准 DDL，
含依決策點 2 之索引調整）；`db_writer.py` `upsert_to_market_articles()` 擴充至 13 欄；
`provider_article_id` 產生邏輯；依決策點 1／3 結果決定的額外範圍。

**Out of Scope**：留言內容 NLP；留言衍生特徵計算（`UG-G2-SB4`）；
`parse_article_comments()` 本身的解析邏輯（`UG-G2-SB2` 已完成，本 SB 不重新設計）。

---

## 8. Affected Components

`database/migrations/003_expand_articles.sql`（新）、`src/loaders/db_writer.py`；
依決策點 1 結果，可能包含 `main_etl_pipeline.py`。

---

## 9. Tests

- `test_migration_003_idempotent`
- `test_article_push_boo_write`（NULL 語意：未解析＝`NULL`，非 0）
- `test_provider_article_id_format`（非 `_unique`——依 §1.4，DB 層無 `UNIQUE` 約束，
  測試驗證的是格式與函式邏輯正確性）
- `test_upsert_null_not_zero_for_unparsed_comment_counts`

`gate0_contract_check.py` 的 B4 強化（§1.6）比照本專案既有慣例（`scripts/verify/` 不進
`tests/` 正式套件），以手動 known-FAIL 示範作為證據，不新增 `tests/` 測試檔。

---

## 10. E2E Verification Plan

比照 `UG-G2-SB1`：獨立隔離臨時 DB（非 `postgres-data` 掛載），流程：`init_db.py` →
`apply_migrations.py`（含 001+002+003）→ 驗證 `market_articles` 共 15 欄（10 既有 + 5 新增）、`chk_comment_counts_nonneg`
生效、留言計數欄為 `NULL` 而非 0（未解析情境）、`provider_article_id` 格式正確。
需 PO 依 RISK-013 協定確認綁定目標後才可執行。

---

## 11. Documentation Sync

`MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的 `DEFAULT 0` 已於 Gate A 審查時修正（§1.5）；
依決策點 2 之裁決同步 `provider_article_id` 索引敘述；`PROJECT_STATUS.md`。

---

## 12. Rollback

見 `DB_MIGRATION_PLAN.md` §7 五層 Rollback 策略；純加法 DDL，L1～L4 已足夠因應。

---

## 13. Definition of Done

- `market_articles` 擴充至 15 欄 Migration 已套用（隔離臨時 DB 驗證）；`upsert_to_market_articles()` 正確寫入 13 欄（不含自動欄位）；
  留言計數欄未解析時為 `NULL`（非 0）；`provider_article_id` 格式正確；`ON CONFLICT (url)
  DO NOTHING` 維持不變（§6A）；`parse_article_comments()` 閒置狀態已登記為待辦；§9 測試 PASS
  （含 B4 known-FAIL 迴歸）；契約驗證與既有測試無回歸。

---

## 14. 待 PO 裁決事項彙總

1. **決策點 1**：本 SB 是否一併把 `parse_article_comments()` 接進 `main_etl_pipeline.py`（建議：不接，比照 SB1 CORE_16 模式；選定選項 A 時須明確登記待辦）。
2. **決策點 2**：`provider_article_id` 型態與索引如何調和兩份 Gate 0 文件的矛盾（建議：DDL 用 TEXT + 補上遺漏的一般索引）。
3. §6A：`ON CONFLICT (url) DO NOTHING` 是否改為 `DO UPDATE`——已由 `MULTI_SOURCE_DATA_CONTRACT.md` §2.3 回答（維持不變），非裁決事項，僅供確認。
4. 是否核准依 §7 範圍開始實作（含 §1.5／§1.6 已修正之 `DEFAULT 0` 矛盾與 B4 檢查強化）。
