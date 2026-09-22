-- Migration 008: article_comments —— 逐則留言的時間軸
-- From: v7
-- To:   v8
-- 規格來源：PRE_G3_01_GATE_A_PROPOSAL.md §2.3（PO 2026-09-06 核准決策點 1、2、2b、3、4）
--
-- ============================================================================
-- 為什麼存逐則，而不是只存「截至 T 的計數」
-- ============================================================================
-- `feature_aggregator` 的 cutoff 是**參數，不是常數**：
--   generate_daily_features         :278  cutoff_time: str = "15:30:00"
--   map_timestamp_to_trading_day    :68   cutoff_time: str | time = "15:30:00"
--   assign_trading_days_to_articles :147  cutoff_time: str | time = "15:30:00"
--
-- 而 CLAUDE.md §7.4 要求 **Gate 3 之前先定義 Prediction Time Convention** ——
-- 那個定義還沒有做。
--
--   > 只存「截至 T 的計數」，等於把一個明確還開著的決定寫死進資料。
--   > **這與 stock_prices 沒有 source 欄是同一個形狀：
--   >  一個寫入時沒有捕捉的維度，事後補不回來。**
--
-- 逐則存下來之後，任一 cutoff 的計數都是它的函數
-- （`src/transform/comment_timeline.counts_as_of()`，測試 W5）。
--
-- ============================================================================
-- ⚠⚠ comment_time 的 NOT NULL 是**承重的**，不得改成可為空
-- ============================================================================
-- 解析失敗的列（`comment_time = None`）**寫不進去**，
-- 於是 **W4（`total_comments` 與逐則列數相等）會 FAIL，而不是靜默少一列**。
--
--   **日後若有人為了「讓寫入不要失敗」把它改成可為空，
--   W4 就會在沒有人發現的情況下失去偵測能力。**
--
-- 寫入路徑本身也不會送出這種列：`validate_comment_bounds()` 會把
-- `comment_time IS NULL` 回報為 `unparsed`，而**該篇整篇拒寫**。
-- 本約束是那條路徑的第二道，不是唯一一道 —— 兩道都要在。
--
-- ============================================================================
-- ⚠ year_inferred：為什麼一個目前全部為 TRUE 的欄位仍然要存
-- ============================================================================
-- 判準是**可否由同列其他欄位重建**（PO 2026-09-06）：
--
--   | 欄 | 能否重建 | 結論 |
--   | etl_run_log 的時區基準 | 能（run_id <= 43 就決定了它，§3.6B） | 衍生欄，不存 |
--   | year_inferred          | **不能** —— 沒有任何欄位記得頁面當時給了幾位數的年份 | 原始事實，該存 |
--
-- **「會不會變」不是判準** —— 一個欄位可能永遠都是同一個值，卻仍然該存在。
--
-- ⚠ 實測（PTT_INNER_PAGE_TIMESTAMP_PROBE_RESULT.json，2026-09-06）：
-- 281/281 則留言皆為 `MM/DD HH:MM`，**無一則帶年份** ——
-- 所以本欄在現行 PTT 上會全部是 TRUE。
--
-- ============================================================================
-- 刻意不存留言內文
-- ============================================================================
-- 本專案的 NLP 只對**標題**做（`nlp_processor`）；對留言文字做 NLP
-- 是 `source_capabilities.py` docstring 明載「結構上做不到」的事。
--
--   **不對稱是判準，不是省事**：
--   留言內文**現在不抓，日後也還在原頁面上**；
--   **時間戳現在不抓，回補完就要整批重來。**
--
-- ============================================================================
-- ⚠ 方向類特徵仍不受 cutoff 保護（RISK-023）
-- ============================================================================
-- 本表存了 comment_tag，**但 comment_polarization／net_push_momentum
-- 目前仍由 market_articles 的「取數當下」彙總算出**，不經過本表
-- （PRE-G3-01 決策點 2b 採 (乙)：存欄位、延後重算）。
-- 登記見 REMAINING_RISKS.md RISK-023 與 MULTI_SOURCE_DATA_CONTRACT.md §3.3A。
--
-- **那個污染不是本 migration 造成的**：feature_aggregator.py:789-791 的三個彙總
-- 從 UG-G2-SB4 起就都是取數當下的值。

CREATE TABLE IF NOT EXISTS article_comments (
    article_id      INTEGER   NOT NULL REFERENCES market_articles(article_id) ON DELETE CASCADE,
    comment_seq     INTEGER   NOT NULL,
    comment_tag     VARCHAR(8)  NOT NULL,
    -- ⚠ NOT NULL 承重，理由見檔頭。**不得改成可為空。**
    comment_time    TIMESTAMP NOT NULL,
    -- 年份是推論來的（TRUE）還是頁面給的（FALSE）。理由見檔頭。
    year_inferred   BOOLEAN   NOT NULL,
    PRIMARY KEY (article_id, comment_seq)
);

-- 依 article_id 取一篇的全部留言（`counts_as_of` 的輸入）。
CREATE INDEX IF NOT EXISTS idx_article_comments_article
    ON article_comments (article_id, comment_seq);

-- 依時間取窗（任一 cutoff 的重算）。
CREATE INDEX IF NOT EXISTS idx_article_comments_time
    ON article_comments (comment_time);

-- comment_tag 的值域：與 MULTI_SOURCE_DATA_CONTRACT.md §3.3 的三類一致。
-- ⚠ 刻意用 CHECK 而非 ENUM —— ENUM 的變更需要 ALTER TYPE，
--   而本專案的 migration 紀律是 additive-only（CLAUDE.md §7.1）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_article_comments_tag'
    ) THEN
        ALTER TABLE article_comments
          ADD CONSTRAINT chk_article_comments_tag
          CHECK (comment_tag IN ('推', '噓', '→'));
    END IF;
END $$;

INSERT INTO schema_version (version, description)
VALUES (8, 'article_comments: per-comment timeline for cutoff-agnostic recomputation (PRE-G3-01)')
ON CONFLICT (version) DO NOTHING;
