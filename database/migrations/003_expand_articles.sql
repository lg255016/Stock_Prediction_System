-- Migration 003: Expand market_articles with comment and provider columns
-- From: v2
-- To:   v3
-- 規格來源：doc/upgrade/contracts/DB_MIGRATION_PLAN.md §4.3（Gate 0 已核准，UG-G2-SB3 逐字採用）
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

-- provider_article_id 輔助索引（MULTI_SOURCE_DATA_CONTRACT.md §2.2 明訂，
-- §4.3 原始 DDL 遺漏；UG-G2-SB3 決策點 2，PO 2026-08-27 核准補上）。
-- 一般索引，**非 UNIQUE**——§2.3 明文「provider_article_id 為輔助去重索引，
-- 不取代 url 的 UNIQUE 約束」，去重主鍵仍為 market_articles.url。
CREATE INDEX IF NOT EXISTS idx_articles_provider_id
  ON market_articles(provider_article_id);

INSERT INTO schema_version (version, description)
VALUES (3, 'Expand market_articles: add nullable push/boo/neutral/total_comments + provider_article_id')
ON CONFLICT (version) DO NOTHING;
