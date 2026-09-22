-- Migration 009: stock_prices.source —— 價格列的血緣
-- From: v8
-- To:   v9
-- 規格來源：PRE_G3_03_BACKFILL_PROPOSAL.md §3（PO 2026-09-07 裁決 DP1 = 選項 (i)）
--
-- ============================================================================
-- 為什麼現在補這一欄
-- ============================================================================
-- migration 008 的檔頭已經指名過這件事：
--
--   > 一個寫入時沒有捕捉的維度，事後補不回來。
--   > **這與 stock_prices 沒有 source 欄是同一個形狀。**
--
-- 而 `run_tpex_pipeline_from_candidate_prices` 的 docstring（main_etl_pipeline.py:274）
-- 也寫過：「順手加欄位會讓 RISK-022 面向一的處置範圍**在無人裁決的情況下**變大。」
--
-- **現在裁決了**（PO 2026-09-07，DP1）：`PRE-G3-03` 要把 `candidate_prices` 的
-- 985 個交易日回補進 `stock_prices`，而那是把**第二個來源**寫進一張分不出來源的表。
--
-- ============================================================================
-- ⚠⚠ 既有 137 列一律 NULL —— 這是刻意的，不是還沒填
-- ============================================================================
-- 實測（PRE_G3_03_BACKFILL_PROPOSAL.md §3.1，唯讀比對）：
--
--     2330  16/16 相符      2382  16/16 相符
--     6488  25/26 相符 ——  2026-08-21：stock_prices 935 vs candidate_prices 941
--     NVDA  0 列可比對（candidate_prices 只涵蓋 TWSE／TPEx）
--
--   ⇒ **137 列裡有 79 列（58%）連比對都做不了。**
--
-- ⚠⚠ **2026-09-07 更正（本 migration 已套用；僅更正註解，SQL 一個字元未改）**：
--   **上面那三行是 `close_price` 單欄比對的結果。** 全欄比對
--   （`open`／`high`／`low`／`close`／`volume`）下：
--
--     6488  **1/26 完全相符**（僅 2026-09-04），碰撞 **25 列**
--
--   其中 24 列僅差 `volume` 且成因已查明（上櫃報表為**張數粒度**，
--   `tpex_daily_quotes` 的 volume 985/985 為 1000 的倍數；差幅平均 0.13%）；
--   1 列（2026-08-21）價格欄亦不同、volume 差 23%，**仍無從判定**。
--   見 `doc/upgrade/gates/evidence/PRE_G3_03_price_collision_report.json`。
--
--   **「79 列無從比對」與「NULL 是刻意的」兩個結論不受影響 —— 反而更強：**
--   **全欄比對顯示可比對的那 58 列裡也有 25 列不一致。**
--
-- **不把相符者標成來源值**（⚠ 原文寫「那 57 列」——**同屬 2026-09-07 更正的單欄產物**；
--   全欄比對下完全相符者為 **33 列**，16+16+1）：`run_twse_pipeline`（main_etl_pipeline.py:215-233）
-- 在自建爬蟲失敗時會落 yfinance 備援（auto_adjust=True），
-- **兩條路在無股利事件的區間會給出相同的值**。
--
--   > 相等只證明沒有分歧，不證明同源。
--   > 用結果回推過程，是製造一份看起來完整、實際上是推測的血緣。
--
-- **NULL 在這裡的語意是「migration 009 之前寫入，血緣不可考」，
--   不是「資料有問題」，也不是「還沒填」。**
--
-- ⚠ 6488 @ 2026-08-21 的 935／941 差異**登記為未解差異，刻意不解決**：
--   成因無從判定，正是本欄存在的理由。留著它。
--
-- ============================================================================
-- ⚠⚠ 為什麼**沒有** DEFAULT
-- ============================================================================
-- 設任何 DEFAULT 都會把上述 137 列 backfill 成一個推測值，
-- 而那正是本 migration 要防止的事。**無 DEFAULT 是承重的，不得補上。**
--
-- 同理，本欄**不設 NOT NULL** —— 既有列沒有可信的值可填。
-- 「新寫入的列必須帶 source」由**寫入端強制**（db_writer.upsert_to_stock_prices
-- 的必要參數 + tests/test_stock_prices_source.py），不由 schema 強制。
--
--   > schema 管得住「值域」，管不住「誰該填」——
--   > 若在此加 NOT NULL，唯一的落地方式就是給既有列編一個值。
--
-- ============================================================================
-- 值域：報表級命名，不是機構級
-- ============================================================================
-- 沿用 candidate_prices.source 已經確立的原則（UG-G2-SB9）：
-- **指向哪一份報表，不是哪一個機構。**
--
--   twse_mi_index          證交所每日收盤行情（MI_INDEX）—— 由 candidate_prices 帶入原值
--   tpex_daily_quotes      櫃買中心每日收盤行情 —— 由 candidate_prices 帶入原值
--   twse_stock_day         證交所個股日成交資訊（exchangeReport/STOCK_DAY），自建爬蟲直取
--   yfinance_auto_adjusted yfinance，**auto_adjust=True**（src/extractors/yfinance_api.py:63）
--
-- ⚠ 前兩者**帶 candidate_prices 那一列的 source 原值過來，不是寫 'candidate_prices'**：
--   RISK-022 要分辨的是**調整基準**，而基準由**原始報表**決定，不由中繼表決定。
--   寫 'candidate_prices' 等於把血緣停在中繼站。
--
-- ⚠ `yfinance_auto_adjusted` 的名字裡帶著 `auto_adjusted`是刻意的：
--   **本欄存在的頭號理由就是分開兩種調整基準，那件事應該在名字裡看得見**，
--   而不是要讀者去查 yfinance_api.py 的常數。
--
-- ⚠⚠ **本欄不使 RISK-022 關閉**：它讓混合變得看得見，
--    而看得見的混合仍然是混合 —— 跨股利日的報酬率在兩種基準下仍然不同。
--
-- ============================================================================
-- CHECK 而非 ENUM
-- ============================================================================
-- 同 migration 008 的 comment_tag 先例：ENUM 的變更需要 ALTER TYPE，
-- 而本專案的 migration 紀律是 additive-only（CLAUDE.md §7.1）。
--
-- **沒有 CHECK，'yfinance' 與 'yFinance' 會安靜地變成兩個來源。**
-- ============================================================================

ALTER TABLE stock_prices
    ADD COLUMN IF NOT EXISTS source TEXT;

-- 值域 = 四個報表級名稱 + NULL（NULL 的語意見檔頭）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_stock_prices_source'
    ) THEN
        ALTER TABLE stock_prices
          ADD CONSTRAINT chk_stock_prices_source
          CHECK (source IS NULL OR source IN (
              'twse_mi_index',
              'tpex_daily_quotes',
              'twse_stock_day',
              'yfinance_auto_adjusted'
          ));
    END IF;
END $$;

-- 依來源查列（碰撞報告與 RISK-022 的稽核路徑）。
CREATE INDEX IF NOT EXISTS idx_stock_prices_source
    ON stock_prices (source);

INSERT INTO schema_version (version, description)
VALUES (9, 'stock_prices.source: price-row lineage, report-level naming, existing rows NULL (PRE-G3-03 DP1)')
ON CONFLICT (version) DO NOTHING;
