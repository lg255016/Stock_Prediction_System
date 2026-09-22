# DB_MIGRATION_PLAN.md — 資料庫遷移與回滾計畫

> **Gate 0 交付物 E**
> 日期: 2026-08-22
> 狀態: READY FOR PO REVIEW

---

## 1. 現況分析

### 1.1 現有 Schema（7 張表）

| # | 表名 | 層別 | 用途 |
|---|------|------|------|
| 1 | `tracking_keywords` | 配置層 | 爬蟲追蹤關鍵字清單 |
| 2 | `entity_mapping` | 配置層 | 關鍵字→股票代碼映射 |
| 3 | `theme_stock_mapping` | 配置層 | 題材→成分股知識映射 |
| 4 | `stock_prices` | 原始資料層 | OHLCV 股價時序資料 |
| 5 | `market_articles` | 原始資料層 | 社群與新聞輿情文章 |
| 6 | `sentiment_cache` | NLP 快取層 | 標題→情緒分數快取 |
| 7 | `daily_ml_features` | ML 特徵層 | 每日 ML 特徵黃金表 |

### 1.2 現有問題

- **無遷移機制**：無 `ALTER TABLE`、無 `schema_version`、無版本追蹤。
- **`database/schema.sql`** 是 DDL Single Source of Truth（DEC-002）。
- **`database/init_db.py`** 是薄層執行器，直接讀取並執行 `schema.sql`，僅支援全新初始化。
- **`daily_ml_features`** 目前僅 7 欄（trade_date, stock_id, close_price, volume, article_count, sentiment_mean, sentiment_3d_ma），需擴展至 **29 欄**（含 `source_status`、`label_reason` 兩個 metadata 欄）。
- **`market_articles`** 缺少推噓文計數與來源文章 ID 欄位。
- **開發資料（`.devcontainer/postgres-data/`）絕對不可被破壞。**

---

## 2. Migration Strategy

### 2.1 方法：Additive DDL Scripts + schema_version 表

採用**純加法式 DDL 腳本**搭配 `schema_version` 版本表，以手動管理的 SQL 檔案進行增量遷移。

### 2.2 為什麼不用 Alembic

- 專案目前表數少（7 張），遷移需求低（<5 個遷移腳本）。
- Alembic 引入額外依賴與學習成本，對小型專案過度工程化。
- **重新評估時機**：當累積遷移腳本超過 10 個時，再評估是否導入 Alembic。

### 2.3 目錄結構

```
database/
├── schema.sql                  # DDL Source of Truth（不變）
├── init_db.py                  # 全新初始化（不變）
├── apply_migrations.py         # 增量遷移執行器（新增）
└── migrations/                 # 遷移腳本目錄（新增）
    ├── 001_baseline.sql
    ├── 002_expand_ml_features.sql
    └── 003_expand_articles.sql
```

---

## 3. schema_version 表設計

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TIMESTAMP DEFAULT NOW(),
    checksum    TEXT
);
```

- `version`：遞增整數版本號，對應遷移腳本編號。
- `description`：人類可讀的遷移描述。
- `applied_at`：遷移執行時間戳。
- `checksum`：遷移腳本的 SHA-256 雜湊值，用於偵測事後竄改。

---

## 4. Migration Files

### 4.1 `001_baseline.sql`（v0→v1, UG-G1-SB4）

建立遷移基礎設施。

```sql
-- Migration 001: Baseline — 建立 schema_version 表
-- From: v0 (no migration tracking)
-- To:   v1

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TIMESTAMP DEFAULT NOW(),
    checksum    TEXT
);

INSERT INTO schema_version (version, description)
VALUES (1, 'Baseline: create schema_version table')
ON CONFLICT (version) DO NOTHING;
```

### 4.2 `002_expand_ml_features.sql`（v1→v2, UG-G2-SB1）

將 `daily_ml_features` 從 7 欄擴展至 **29 欄**，新增 **22 個**欄位（19 engineered + 4 target - 3 已存在 + 2 metadata）。

```sql
-- Migration 002: Expand daily_ml_features from 7 to 29 columns (add 22 new)
-- From: v1
-- To:   v2
--
-- 29-column contract (Master Plan §3.4):
--   Identifier (2): trade_date, stock_id                        [已存在]
--   Context    (2): close_price, volume                         [已存在]
--   Metadata   (2): source_status, label_reason                 [新增]
--   Engineered(19): 3 已存在 (article_count, sentiment_mean, sentiment_3d_ma) + 16 新增
--   Target     (4): 全部新增
--
-- NOTE: open_price, high_price, low_price are PROHIBITED here.
--       They belong in stock_prices only (Master Plan constraint).

-- Existing derived features not yet in DB (9 columns)
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS return_1d NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS rsi_14 NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS volatility_5d NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS volatility_20d NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS bullishness_index NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS agreement_index NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS sentiment_5d_ma NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS sentiment_lag_1 NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS sentiment_lag_2 NUMERIC;

-- CORE_16 new stationary features (4 columns)
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS amplitude_ratio NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS ma5_bias_ratio NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS ma20_bias_ratio NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS volume_ratio_5d NUMERIC;

-- Comment features (3 columns)
-- NULL 語意：留言功能未啟用／當日無留言／來源 SOURCE_FAILED 時保持 NULL
-- 嚴禁 DEFAULT 值或 NOT NULL 約束 —— 沒有留言資料是事實，不是數值
-- 契約來源：FEATURE_REGISTRY.md §3.5（欄位定義）, §5A（全欄位 NULL 語意規則）
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS comment_volume_ratio NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS comment_polarization NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS net_push_momentum NUMERIC;

-- Target columns (4 columns)
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS target_next_close NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS target_return_1d NUMERIC;
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS target_up_down INTEGER;

-- target_triple_barrier: 三分類 {-1, 0, 1}，NULL 代表同日觸雙線／資料不足／無法進場
-- anchor = Open[T+1]，評估區間 T+1~T+5
-- 契約來源：PURGED_WALK_FORWARD_SPEC.md §4.3
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS target_triple_barrier INTEGER;

-- CHECK constraint 需冪等：PostgreSQL 無 ADD CONSTRAINT IF NOT EXISTS
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_target_triple_barrier_domain'
    ) THEN
        ALTER TABLE daily_ml_features
          ADD CONSTRAINT chk_target_triple_barrier_domain
          CHECK (target_triple_barrier IS NULL OR target_triple_barrier IN (-1, 0, 1));
    END IF;
END $$;

-- ===== Metadata / Lineage columns (2) =====
-- 這兩欄是 BLOCK-2 / BLOCK-3 的實作基礎：沒有它們，
-- 「來源失敗 → 特徵保持 NULL 並排除訓練」與「NULL 標籤的三種成因」
-- 在資料庫層都無法區分。

-- source_status: 該 (trade_date, stock_id) 列的社群情緒輸入彙總狀態
--   'SUCCESS'         = 至少一個來源成功且有文章
--   'SUCCESS_EMPTY'   = 查詢成功但確實無文章 → 情緒欄位可正當填中立值
--   'SOURCE_DEGRADED' = 部分來源／部分頁面失敗 → 使用已取得資料但標記
--   'SOURCE_FAILED'   = 全部來源不可達 → 情緒欄位必須 NULL，該筆排除訓練
-- 契約來源：MULTI_SOURCE_DATA_CONTRACT.md §7.2；FEATURE_REGISTRY.md §5A
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS source_status TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_source_status_domain'
    ) THEN
        ALTER TABLE daily_ml_features
          ADD CONSTRAINT chk_source_status_domain
          CHECK (source_status IS NULL OR source_status IN
                 ('SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED', 'SOURCE_FAILED'));
    END IF;
END $$;

-- label_reason: target_triple_barrier 為 NULL 時的成因
--   NULL                      = 標籤正常生成（target_triple_barrier 非 NULL）
--   'ambiguous_dual_barrier'  = 同日同時觸及上下障礙
--   'insufficient_data'       = 資料集最後 H 個交易日
--   'no_entry'                = Open[T+1] 不存在（停牌／下市）
-- 契約來源：PURGED_WALK_FORWARD_SPEC.md §4.3, §6
-- 用途：§6 Ambiguous Ratio 報告必須能分離三種成因，RISK-011 的 10% 觸發條件依賴此欄
ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS label_reason TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_label_reason_domain'
    ) THEN
        ALTER TABLE daily_ml_features
          ADD CONSTRAINT chk_label_reason_domain
          CHECK (label_reason IS NULL OR label_reason IN
                 ('ambiguous_dual_barrier', 'insufficient_data', 'no_entry'));
    END IF;
END $$;

-- 不變式：label_reason 非 NULL ⟺ target_triple_barrier 為 NULL
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_label_reason_consistency'
    ) THEN
        ALTER TABLE daily_ml_features
          ADD CONSTRAINT chk_label_reason_consistency
          CHECK (
            (label_reason IS NULL AND target_triple_barrier IS NOT NULL)
            OR (label_reason IS NOT NULL AND target_triple_barrier IS NULL)
            OR (label_reason IS NULL AND target_triple_barrier IS NULL)  -- 尚未計算標籤
          );
    END IF;
END $$;

INSERT INTO schema_version (version, description)
VALUES (2, 'Expand daily_ml_features: add 22 columns (29-column contract incl. source_status, label_reason)')
ON CONFLICT (version) DO NOTHING;
```

### 4.3 `003_expand_articles.sql`（v2→v3, UG-G2-SB3）

為 `market_articles` 新增推噓文計數與來源文章 ID 欄位。

```sql
-- Migration 003: Expand market_articles with comment and provider columns
-- From: v2
-- To:   v3
--
-- ⚠ 關鍵設計約束：四個留言計數欄 **不得** 使用 DEFAULT 0
--
-- 理由：這四欄是 comment_volume_ratio / comment_polarization / net_push_momentum
--       三個特徵的唯一上游來源。若使用 DEFAULT 0，所有在留言解析上線前
--       爬取的既有文章都會被 backfill 成 0，導致：
--           total_comments = 0  → comment_volume_ratio = 0/(0+1) = 0.0
--           push=boo=0          → push_ratio = 0
--                               → comment_polarization = 1 - 0² = 1.0（「最大分歧」）
--       這等同於在 daily_ml_features 層嚴禁的中立值填補，從 raw 層後門放進來，
--       且產生的是「散戶意見最大分歧」這種強訊號 —— 完全是偽造的。
--
-- 必須可區分的兩種狀態：
--   NULL → 文章存在，但留言尚未解析（或解析失敗）
--   0    → 文章已解析，確實有 0 則留言
--
-- 契約來源：FEATURE_REGISTRY.md §5A.5；測試斷言 A8-4／A8-5 依賴此區分

ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS push_count INTEGER;
ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS boo_count INTEGER;
ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS neutral_count INTEGER;
ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS total_comments INTEGER;
ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS provider_article_id TEXT;

-- 非負約束（允許 NULL）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_comment_counts_nonneg'
    ) THEN
        ALTER TABLE market_articles
          ADD CONSTRAINT chk_comment_counts_nonneg
          CHECK (
            (push_count      IS NULL OR push_count      >= 0) AND
            (boo_count       IS NULL OR boo_count       >= 0) AND
            (neutral_count   IS NULL OR neutral_count   >= 0) AND
            (total_comments  IS NULL OR total_comments  >= 0)
          );
    END IF;
END $$;

INSERT INTO schema_version (version, description)
VALUES (3, 'Expand market_articles: add nullable push/boo/neutral/total_comments + provider_article_id')
ON CONFLICT (version) DO NOTHING;
```

> **既有資料的處理**：Migration 003 執行後，所有既有文章的四個留言欄皆為 `NULL`
> （代表「尚未解析」），不是 `0`。UG-G2-SB2 的留言解析器上線後才逐步回填真實值。
> 未回填的歷史文章在 `COMMENT_ENHANCED_19` 契約下不產生留言特徵，該樣本排除訓練。

---

## 5. apply_migrations.py 設計

### 5.1 核心邏輯

```
0. （UG-G1-SB4 階段一新增）assert_safe_migration_target()：偵測連線目標是否疑似
   真實開發 DB，未提供明確覆寫確認時直接拒絕，不進入步驟 1
1. 連線資料庫
2. 檢查 schema_version 表是否存在
   - 不存在 → 目前版本為 0
   - 存在 → SELECT MAX(version) FROM schema_version
3. 掃描 database/migrations/ 目錄，按編號排序
4. 篩選出 version > current_version 的腳本
5. 依序對每個腳本：
   a. BEGIN TRANSACTION
   b. 執行 SQL 內容
   c. UPDATE schema_version SET checksum = ... WHERE version = ...
   d. COMMIT
   e. 若失敗 → ROLLBACK，停止執行，回報錯誤
6. 輸出執行結果摘要
```

**實作階段發現的細節（步驟 5c 為何是 UPDATE 而非 INSERT）**：§4 的每個遷移檔案
（`001_baseline.sql`、`002_expand_ml_features.sql`、`003_expand_articles.sql`）
內容本身皆已內嵌 `INSERT INTO schema_version (version, description) VALUES (...)
ON CONFLICT (version) DO NOTHING`（不含 checksum）——這是遷移檔案自我登記版本號的
既定設計，早於 runner 執行前就已寫入該列。若 runner 也用 INSERT 補 checksum，
會被這個既有列的 `ON CONFLICT` 擋下而永遠寫不進去。改用 UPDATE 後，不論該列是
由遷移檔案自行建立或尚不存在，皆能正確補上 `checksum`。

### 5.2 設計原則

- **冪等性**：每個遷移使用 `IF NOT EXISTS` 與 `ON CONFLICT DO NOTHING`，重複執行不會出錯。
- **原子性**：每個遷移在獨立事務中執行，失敗時自動 ROLLBACK。
- **順序性**：嚴格按檔名編號順序執行，不可跳號。
- **連線前守門**：見步驟 0；`database/db_target_guard.py`（DEC-021）為本 runner
  與外部連線之間的唯一必經檢查點。
- **安全性**：不執行已套用的版本（版本號已存在於 `schema_version`）。

---

## 6. Safety Guarantees（9 項安全保證）

| # | 保證項目 | 說明 |
|---|---------|------|
| 1 | **僅使用 ADD COLUMN IF NOT EXISTS** | 所有遷移皆為純加法操作，不修改現有欄位 |
| 2 | **禁止 DROP TABLE / TRUNCATE / PK 修改** | 遷移腳本中絕不出現破壞性 DDL |
| 3 | **遷移前必須執行 pg_dump -Fc** | 每次遷移前產生完整備份檔 |
| 4 | **每個遷移在獨立事務中執行** | 單一腳本失敗不影響其他已成功的遷移 |
| 5 | **失敗時自動 ROLLBACK** | 事務失敗立即回滾，不推進版本號 |
| 6 | **先在隔離 PostgreSQL 18 容器中驗證** | 正式執行前必須通過隔離環境測試 |
| 7 | **絕不修改/刪除/破壞 `.devcontainer/postgres-data/`** | 開發資料受到最高保護 |
| 8 | **`schema_version` 表永不 DROP** | 版本追蹤表是不可回滾的永久基礎設施 |
| 9 | **連線目標守門檢查（UG-G1-SB4 階段一，DEC-021）** | `apply_migrations.py` 建立連線前強制呼叫 `database/db_target_guard.py` 的 `assert_safe_migration_target()`；偵測到連線目標疑似真實開發 DB 且未提供明確覆寫確認時，於連線前即拒絕執行——彌補第 3／6 項本身仍依賴「先做才有備份／先驗證才正式跑」這種流程紀律的缺口，是技術層面而非流程層面的護欄 |

---

## 7. Layered Rollback Strategy（5 層回滾策略）

| 層級 | 情境 | 回滾方法 | 需 PO 核准 |
|------|------|---------|-----------|
| L1 | 程式碼問題，Schema 無需改動 | `git revert` 回退程式碼 | No |
| L2 | 隔離環境測試失敗 | 銷毀臨時測試容器與資料庫 | No |
| L3 | 開發 DB 遷移腳本執行失敗 | 事務自動 ROLLBACK，版本不推進 | No |
| L4 | 已成功的加法遷移需要修正 | 撰寫新的 forward-fix 遷移腳本（例：修正欄位型別） | No |
| L5 | 需要完整回滾至遷移前狀態 | 使用遷移前 `pg_dump -Fc` 備份檔還原 | **YES** |

### 回滾原則

- **L1–L4 不需要 PO 核准**：這些操作不涉及資料遺失風險。
- **L5 需要 PO 明確核准**：完整還原意味著遷移後寫入的所有新資料都將遺失。
- **永遠優先 forward-fix（L4）**：除非 forward-fix 不可行，否則不走 L5。

---

## 8. Verification Plan（驗證計畫）

### 8.1 隔離容器測試

在獨立的 PostgreSQL 18 Docker 容器中執行完整遷移流程：

```bash
# 啟動隔離測試容器
docker run --name migration-test -e POSTGRES_DB=test_db \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=<value> \
  -p 15432:5432 -d postgres:18

# 執行初始化
python database/init_db.py

# 執行遷移
python database/apply_migrations.py

# 驗證後銷毀
docker rm -f migration-test
```

### 8.2 冪等性測試

```bash
# 連續執行兩次 apply_migrations.py
python database/apply_migrations.py
python database/apply_migrations.py
# 預期：第二次執行應顯示「無待執行遷移」，無錯誤
```

### 8.3 版本檢查測試

```sql
SELECT version, description, applied_at FROM schema_version ORDER BY version;
-- 預期：顯示 v1, v2, v3 三筆記錄
```

### 8.4 失敗回滾測試

```bash
# 建立一個故意失敗的遷移腳本（例：引用不存在的表）
# 執行 apply_migrations.py
# 預期：失敗的遷移被 ROLLBACK，schema_version 不推進
```

---

## 9. Relationship to init_db.py（與 init_db.py 的關係）

### 9.1 職責分離

| 工具 | 職責 | 使用時機 |
|------|------|---------|
| `init_db.py` | 全新資料庫初始化（`CREATE TABLE IF NOT EXISTS` + Seed Data） | 第一次建立資料庫、或從零重建 |
| `apply_migrations.py` | 增量 Schema 變更（`ALTER TABLE ADD COLUMN IF NOT EXISTS`） | 現有資料庫需要擴展欄位 |

### 9.2 共存規則

- **兩者共存**，互不取代。
- `apply_migrations.py` 假設基礎 Schema（由 `init_db.py` 建立）已經存在。
- 全新建庫流程：先執行 `init_db.py`，再執行 `apply_migrations.py`。
- `schema.sql` 保持為 DDL Source of Truth；未來當遷移穩定後，將遷移後的完整欄位回寫至 `schema.sql`，確保新建庫時直接包含所有欄位。
