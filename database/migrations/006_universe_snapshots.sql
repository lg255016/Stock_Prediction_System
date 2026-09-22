-- Migration 006: Create universe_snapshots (Point-in-Time Stock Universe)
-- From: v5
-- To:   v6
-- 規格來源：DEC-017（APPROVED，Gate 0 交付物 B/G）§Decision；
--           G2_SB6_GATE_A_PROPOSAL.md §4（PO 2026-09-03 核准 Gate A）
--
-- ============================================================================
-- 為什麼「排除清單」也要存
-- ============================================================================
-- DEC-017 明文要求「保存 universe_effective_date、排名依據、**納入／排除清單**」。
--
-- **只存納入名單，等於無法回答「這檔當時為什麼不在裡面」** ——
-- 而那正是稽核 Survivorship Bias（倖存者偏誤）時唯一要問的問題。
--
-- 舉例：若日後發現某檔股票在 2024 年整年都不在 universe 裡，
-- 只存納入名單的設計只能告訴你「它不在」，
-- 不能區分「當時流動性不夠」「當時資料不足」「當時已停止交易」——
-- 而這三者對回測結論的意義完全不同。
--
-- ============================================================================
-- 欄位語意
-- ============================================================================
-- effective_date：**每月第一個交易日**（DEC-017「每月第一個交易日重建」）。
--   ⚠ 是**交易日**不是日曆日——月初若逢假日，該月的 effective_date 是該月首個開市日。
--
-- median_turnover：排名依據，DEC-017 的「過去 60 交易日每日成交金額中位數」。
--   **逐筆保存，不只存排名** —— 排名是序，中位數是量。
--   只存排名的話，「第 150 名與第 151 名差多少」這個問題永遠答不出來，
--   而那正是判斷 150 這條線是否穩定所需的資訊（RISK-015 在 Gate 3 會問）。
--
--   ⚠ **缺席日計為 0，不是略過**（提案 §2.2a，PO 2026-09-02 指出）。
--   若只對「有資料的日子」取中位數，一檔重倉交易 5 天後就消失的股票會有很高的中位數，
--   進得了前 150 —— 而它根本不可交易。計為 0 之後，
--   60 天裡缺席超過 30 天者中位數必為 0，自動出局。
--
--   ⚠⚠ **這個 0 不是 `fillna(0)`，是觀測值。** 必須寫在這裡，
--   否則下一個人會拿本專案的 `DEFAULT 0` 禁令來反對它——**而他不會是錯的，
--   除非這行區別就寫在旁邊**。一檔停牌或已下市的股票，那天**確實沒有任何金額成交**。
--   `005_candidate_prices.sql` 對 volume 已確立同一立場：「0 = 真實觀測到的零成交」。
--   被禁止的那種 `fillna(0)`（例如 comment_polarization）是「**算不出來**被寫成一個值」；
--   這裡的 0 是「**金額為零**」這個事實本身。
--
-- observation_days：用於排名的 60 日窗內，該股**實際有資料的交易日數**（0~60）。
--   **必須存**：它是「歷史資料不足」這個排除理由的依據。
--   不存就無法事後區分「當時資料不足」與「當時流動性不夠」——
--   兩者的 median_turnover 都可能是 0（提案 §2.2a 的已知副作用）。
--
-- included：**納入與排除都要存**（見上方）。
--
-- exclusion_reason：included = FALSE 時必填，由 CHECK 強制。
--   ⚠ **只能寫可觀測的事實，不得寫「已下市」或「停牌」**（提案 §8 第 7 項，PO 指出）。
--   `effective_date` 當天**無法區分長期停牌與已下市** ——
--   停牌 199 天的那一檔在第 100 天看起來與已下市完全相同，
--   兩者都是「最近沒有出現」，而**區分它們需要未來的資料**，
--   PIT 明文禁止使用未來資料。**這不是缺陷，是資訊的邊界。**
--   寫成「已下市」會是一個 INFERENCE 被記錄成事實。
--
-- ============================================================================
-- 為什麼 rank 對排除者也給值
-- ============================================================================
-- 排除者的 rank 記為 NULL，**不是給一個假的名次**。
-- 一檔被排除的股票沒有名次可言；給它 999 或 0 都是在編一個數字。
-- 這與 median_turnover 的 0 不同：那個 0 是觀測，這個名次是不存在。

CREATE TABLE IF NOT EXISTS universe_snapshots (
    effective_date   DATE          NOT NULL,   -- 每月第一個交易日
    stock_id         VARCHAR(10)   NOT NULL,
    rank             INTEGER,                  -- 1 = 流動性最高；排除者為 NULL
    median_turnover  NUMERIC(20, 0) NOT NULL,  -- 排名依據（元），缺席日計 0
    observation_days INTEGER       NOT NULL,   -- 60 日窗內實際有資料的天數
    included         BOOLEAN       NOT NULL,   -- 納入與排除都要存
    exclusion_reason TEXT,                     -- included = FALSE 時必填
    created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (effective_date, stock_id)
);

-- 依 effective_date 載入當期快照是回測的主要存取樣式（DEC-017：
-- 「歷史回測必須載入當期 Snapshot」），且只取 included = TRUE 的那一批。
CREATE INDEX IF NOT EXISTS idx_universe_snapshots_effective_included
    ON universe_snapshots (effective_date, included);

-- 不變式一：排除必附理由，納入不得帶理由。
-- **雙向約束，不是單向** —— 只擋「排除無理由」的話，
-- 一列 included = TRUE 卻寫著 exclusion_reason 一樣會被讀成排除。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_universe_snapshots_exclusion_reason'
    ) THEN
        ALTER TABLE universe_snapshots ADD CONSTRAINT chk_universe_snapshots_exclusion_reason
        CHECK (
            (included = TRUE  AND exclusion_reason IS NULL)
            OR
            (included = FALSE AND exclusion_reason IS NOT NULL)
        );
    END IF;
END $$;

-- 不變式二：納入者必有名次，排除者不得有名次。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_universe_snapshots_rank'
    ) THEN
        ALTER TABLE universe_snapshots ADD CONSTRAINT chk_universe_snapshots_rank
        CHECK (
            (included = TRUE  AND rank IS NOT NULL AND rank >= 1)
            OR
            (included = FALSE AND rank IS NULL)
        );
    END IF;
END $$;

-- 不變式三：中位數不得為負；觀測天數必須落在 60 日窗內。
-- ⚠ 上界寫死 60 是刻意的：窗長是 DEC-017 定死的「過去 60 交易日」，
--   若日後改窗長，這個 CHECK 會**擋下寫入**並強迫一起改——
--   那正是要的行為。一個會隨參數自動放寬的約束不是約束。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_universe_snapshots_nonneg'
    ) THEN
        ALTER TABLE universe_snapshots ADD CONSTRAINT chk_universe_snapshots_nonneg
        CHECK (
            median_turnover >= 0
            AND observation_days >= 0
            AND observation_days <= 60
        );
    END IF;
END $$;

INSERT INTO schema_version (version, description)
VALUES (6, 'Create universe_snapshots for Point-in-Time Stock Universe (UG-G2-SB6, DEC-017)')
ON CONFLICT (version) DO NOTHING;
