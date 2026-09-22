-- Migration 002: Expand daily_ml_features from 7 to 29 columns (add 22 new)
-- From: v1
-- To:   v2
-- 規格來源：doc/upgrade/contracts/DB_MIGRATION_PLAN.md §4.2（Gate 0 已核准，UG-G2-SB1 逐字採用）
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
-- UG-G2-SB1 實作邊界：本 SB 只會寫出 SUCCESS／SUCCESS_EMPTY 兩態；
-- SOURCE_DEGRADED／SOURCE_FAILED 依賴 UG-G2-SB2 的 pipeline 例外傳播才可能產生
-- （見 G2_SB1_GATE_A_PROPOSAL.md §1.3）。值域仍完整定義供未來使用。
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
-- UG-G2-SB1 實作邊界：本 SB 只會寫出 insufficient_data／no_entry／NULL 三值；
-- ambiguous_dual_barrier 屬 Triple-Barrier 語意，Gate 3（UG-G3-SB1）才會產生
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
