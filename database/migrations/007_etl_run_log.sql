-- Migration 007: Create etl_run_log (批次 ETL 的逐項 outcome)
-- From: v6
-- To:   v7
-- 規格來源：G2_SB7_GATE_A_PROPOSAL.md §4.1（PO 2026-09-04 核准 Gate A、裁決決策點 1「建表」）
--
-- ============================================================================
-- 為什麼「單一失敗不阻塞」需要一張表
-- ============================================================================
-- SB7 Brief 的 In Scope 與 DoD 都寫「失敗容忍（單一失敗不阻塞）」。
-- **若「不阻塞」實作成「跳過失敗的項目、繼續跑」，那一項在結果裡就長得像「那天沒資料」。**
--
-- `CLAUDE.md` §7.1 逐字：
--   **Database Error 不得被偽裝成 Empty Result。**
--   **失敗與「真的沒有資料」必須可區分。**
--
-- 而這件事**今天就已經在發生**（`UG-G2-SB7` Gate A 唯讀查證，四段鏈）：
--
--   1. `main_etl_pipeline.py:79-82` 捕捉 `PttSourceUnavailableError` 後只 `print` 再 `return`
--      —— **失敗沒有進入任何資料**。
--   2. `feature_aggregator.py:454-456` 的 `source_status` 只由 `article_count > 0` 決定，
--      **該段註解自己寫著「本函式僅產出 SUCCESS／SUCCESS_EMPTY 兩態」**。
--   3. `MULTI_SOURCE_DATA_CONTRACT.md:321` 逐字要求 `SOURCE_FAILED` 時
--      「該來源當日特徵保持 NULL；**不得**寫入 0 或中立值；**該筆排除訓練**」。
--   4. 而 `feature_aggregator.py:441` 是 `sentiment_mean.fillna(0.5)` —— **中立值**。
--
-- **所以一次 PTT 抓取失敗，最終呈現為 `SUCCESS_EMPTY` + `sentiment_mean = 0.5`，
--   那些列不但沒被排除訓練，還帶著 0.5 進了訓練集。**
--
-- ⚠ **禁令不在遠處的契約文件裡** —— 它就寫在被 catch 的那個例外類別上
--   （`ptt_scraper.py:12-13`）：「呼叫端不得將其誤判為『查無資料』」。
--   `UG-G2-SB2` 把 extractor 端做對了，**而 pipeline 在兩個檔案之外做了它明文禁止的事**。
--   **這說明把規則寫對並不足夠。**
--
-- 一個只印到 stdout 的 outcome，**在下一次執行後就不存在了**；
-- 而「這批有幾項是真的沒資料、幾項是抓失敗」是**事後**才會被問的問題。
--
-- ============================================================================
-- 欄位語意
-- ============================================================================
-- outcome：**四態，且互斥窮盡**（本批的每一個項目恰好落在一格）。
--   OK           —— 取得資料且解析成功，列數 > 0
--   NO_DATA      —— **請求成功**（拿到 2xx 且可解析），但內容為空。
--                   例：國定假日的全市場報表確實沒有資料列 —— **那是正確答案，不是失敗**。
--   FETCH_FAILED —— 未取得可解析的回應：傳輸層失敗、5xx 重試耗盡、或解析失敗。
--   REFUSED      —— **服務在叫我們停**（403／429，DEC-032）。
--
--   ⚠ **REFUSED 與 FETCH_FAILED 必須分開**（2026-09-04 複查方裁決）。
--     生產程式碼把 `ServiceRefusedError` 與 `FetchFailedError` 分成兩個型別，
--     理由是**處置相反**：前者要停止對該服務施壓，後者只需記下讓其餘項目繼續。
--     **那個區別若在 outcome 欄裡消失，run log 就回答不了
--      「那天是被拒絕，還是抓失敗」** —— 型別分得開而詞彙分不開，等於白分。
--
--   ⚠ **`NO_DATA` 與 `FETCH_FAILED` 不得互相取代。** 兩者在「這一項沒有列」上
--     長得一樣，而下游的處置完全相反：前者是有效觀測，後者必須讓該項當日特徵保持 NULL。
--
-- detail：`FETCH_FAILED` 與 `REFUSED` 時必填，由 CHECK 強制。
--   **只能寫可觀測的事實**（`HTTP 429`、`TLS handshake failed`、`parse error: ...`），
--   **不得寫推論**（`被封鎖`）—— 同 `universe_snapshots.exclusion_reason` 的紀律
--   （`006_universe_snapshots.sql`）。
--
-- target_database：`current_database()` 的實際輸出。
--   **為什麼要存**：`assert_safe_migration_target()` 的呼叫端只有
--   `apply_migrations.py:106`，`db_writer.py` 零命中 —— **主要寫入路徑不受守門保護，
--   而那是設計不是疏漏**（RISK-013：`DBWriter` 的職責就是寫真實庫）。
--   技術護欄不存在時只剩流程紀律，而**流程紀律管到的是「宣稱」，管不到「執行」**。
--   存下它，「這次跑的是哪個資料庫」就成為**事後可查的事實，而不是回憶**。
--   > RISK-017 的成因正是「沒有任何機制追蹤哪個環境收到了哪個變更」，
--   > 那次的教訓被寫成「DoD 要指名資料庫」—— **那只管到宣稱。**
--
-- http_attempts：DEC-032 雙軌計數的第二軌。
--   邏輯請求數（我們想問的問題數）與 HTTP 嘗試數（造成的實際負載）**不是同一件事**；
--   少了後者就無法回答「這次執行對對方造成多少負擔」。

CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id          BIGSERIAL   PRIMARY KEY,
    started_at      TIMESTAMP   NOT NULL,
    source          VARCHAR(40) NOT NULL,   -- 'twse_mi_index' / 'tpex_daily_quotes' / 'ptt'
    batch_key       TEXT        NOT NULL,   -- 本批的識別，例：'2026-09-03'
    item_key        TEXT        NOT NULL,   -- 項目識別：股票代號／頁面 URL／關鍵字
    outcome         VARCHAR(16) NOT NULL,   -- OK / NO_DATA / FETCH_FAILED / REFUSED
    detail          TEXT,                   -- FETCH_FAILED／REFUSED 時必填，且只寫可觀測事實
    target_database TEXT        NOT NULL,   -- current_database()
    http_attempts   INTEGER,                -- 雙軌計數的第二軌
    created_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

-- 批次總結的主要存取樣式：某一批的各態計數。
CREATE INDEX IF NOT EXISTS idx_etl_run_log_batch
    ON etl_run_log (source, batch_key, outcome);

-- 不變式一：outcome 只能是四態之一。
-- **窮舉在此是刻意的** —— 新增一態必須改 migration，
-- 而那正是應該被看見的時刻；讓它自由文字化，下一個人就會寫出 'SKIPPED'。
-- **2026-09-04 這件事真的發生了一次**：REFUSED 是複查方裁決後補上的第四態，
-- 而它確實是經由改 migration 進來的 —— **窮舉逼出了那次審視。**
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_etl_run_log_outcome'
    ) THEN
        ALTER TABLE etl_run_log ADD CONSTRAINT chk_etl_run_log_outcome
        CHECK (outcome IN ('OK', 'NO_DATA', 'FETCH_FAILED', 'REFUSED'));
    END IF;
END $$;

-- 不變式二：失敗必附可觀測理由，成功不得帶理由。
-- **雙向約束** —— 只擋「失敗無理由」的話，一列 outcome='OK' 卻寫著 detail
-- 一樣會被讀成失敗（同 `universe_snapshots` 的 exclusion_reason CHECK）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_etl_run_log_detail'
    ) THEN
        ALTER TABLE etl_run_log ADD CONSTRAINT chk_etl_run_log_detail
        CHECK (
            (outcome IN ('FETCH_FAILED', 'REFUSED') AND detail IS NOT NULL)
            OR
            (outcome NOT IN ('FETCH_FAILED', 'REFUSED') AND detail IS NULL)
        );
    END IF;
END $$;

-- 不變式三：HTTP 嘗試數不得為負；有嘗試才可能有 outcome。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_etl_run_log_attempts'
    ) THEN
        ALTER TABLE etl_run_log ADD CONSTRAINT chk_etl_run_log_attempts
        CHECK (http_attempts IS NULL OR http_attempts >= 0);
    END IF;
END $$;

-- ⚠ **本檔於 2026-09-04 修訂（新增 REFUSED 第四態）。**
--   修訂而非另立 008 的理由：**本 migration 從未被任何資料庫套用過**
--   （真實庫 `schema_version` 當時為 6）。已套用的 migration 不可改，
--   **未套用的 migration 改它才是對的** —— 另立 008 會留下一個從未存在過的中間狀態。
INSERT INTO schema_version (version, description)
VALUES (7, 'Create etl_run_log for batch ETL per-item outcomes (UG-G2-SB7)')
ON CONFLICT (version) DO NOTHING;
