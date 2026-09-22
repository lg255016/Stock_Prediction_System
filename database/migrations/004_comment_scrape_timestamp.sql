-- Migration 004: Add comments_scraped_at to market_articles
-- From: v3
-- To:   v4
-- 規格來源：G2_SB4_GATE_A_PROPOSAL.md §14（PO 2026-08-28 核准），DEC-024
--
-- 用途：留言計數的**時點有效性稽核欄位**。
--
-- 判準（DEC-024）：一個特徵值是否構成前視偏誤，看的不是「它是不是發文那天的數字」，
-- 而是「它在被歸屬的那個交易日的決策時點，是否已經看得到」。Roll-Forward Mapping
-- 本來就會把週五盤後與週末的文章歸屬到週一，因此週一早上爬到的留言數屬於
-- 週一決策時點的合法可見資訊，不是洩漏。
--
-- 本欄記錄「這筆留言計數是何時擷取的」，使下游能：
--   1. 驗證留言計數與其歸屬交易日的時點對齊（稽核，非過濾大多數資料）
--   2. 把回填期（系統開跑前的歷史文章）無法對齊的舊資料誠實標記出來
--
-- ⚠ 本欄**不得**有 DEFAULT——與四個留言計數欄同理：
--   NULL → 留言尚未擷取（與 total_comments IS NULL 同步出現）
--   有值 → 該時點確實執行過內頁解析
-- 若給 DEFAULT NOW()，所有既有列會被 backfill 成「剛剛擷取過」，
-- 使時點稽核完全失去意義（同 DB_MIGRATION_PLAN.md §4.3 對 DEFAULT 0 的反對理由）。

ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS comments_scraped_at TIMESTAMP;

-- 不變式：comments_scraped_at 非 NULL ⟺ total_comments 非 NULL
-- （留言計數與其擷取時點必須同時存在或同時不存在——只有其中一個等於
--  「有數字但不知道何時抓的」或「知道抓過但沒數字」，兩者都無法稽核）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_comments_scraped_at_consistency'
    ) THEN
        ALTER TABLE market_articles
          ADD CONSTRAINT chk_comments_scraped_at_consistency
          CHECK (
            (comments_scraped_at IS NULL AND total_comments IS NULL)
            OR (comments_scraped_at IS NOT NULL AND total_comments IS NOT NULL)
          );
    END IF;
END $$;

INSERT INTO schema_version (version, description)
VALUES (4, 'Add comments_scraped_at to market_articles for comment-count timing audit (DEC-024)')
ON CONFLICT (version) DO NOTHING;
