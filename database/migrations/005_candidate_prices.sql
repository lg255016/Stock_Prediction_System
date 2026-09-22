-- Migration 005: Create candidate_prices (Universe 排名用的候選池價量)
-- From: v4
-- To:   v5
-- 規格來源：G2_SB9_GATE_A_PROPOSAL.md §4（PO 2026-08-31 裁決決策點 1 → 方案 (a) 獨立表）
--
-- ============================================================================
-- 為什麼是獨立表，而不是在 stock_prices 加標記欄
-- ============================================================================
-- `db_writer.fetch_all_for_features()` 的股價查詢**沒有任何 WHERE 條件**，
-- 而 stock_prices 沒有欄位能區分「追蹤中的股票」與「候選池」。
-- 若把全市場資料寫進 stock_prices，特徵管線下一次執行就會從 117 列變成約 79 萬列，
-- 為約 1000 檔沒有任何文章的股票計算完整特徵。
--
-- 那**不是效能問題，是語意問題**：daily_ml_features 會被填入大量
-- 「有價量、無情緒」的列，source_status 幾乎全是 SUCCESS_EMPTY，
-- **而那個比例正是 RISK-015 要看的東西**——目前 SUCCESS 37 / SUCCESS_EMPTY 80
-- 是在 4 檔追蹤股票上量到的，混入候選股後會被稀釋成雜訊。
--
-- 方案 (b)（stock_prices 加標記欄 + 特徵查詢補 WHERE）被否決的理由：
-- **它把正確性寄託在「記得改查詢」上**，而本專案已有三次證據顯示那件事會被漏掉
-- （UG-G2-SB4 的留言計數欄、UG-G2-SB5 的 source、UG-G2-SB8 的 high/low），
-- 且失敗是**靜默**的。獨立表讓漏改不可能發生——特徵管線根本看不到這張表。
--
-- ============================================================================
-- 欄位語意
-- ============================================================================
-- turnover_amount：**成交金額**，DEC-017 流動性排名的依據
--   （「以過去 60 交易日每日成交金額中位數排序」）。
--   端點直接提供此欄（B5 判準 PASS），**不使用 close × volume 近似**——
--   後者由收盤價推算，而真實成交金額由盤中逐筆價累計，
--   在振幅大的股票上兩者可能有可觀差距，而排名正是要區分
--   「大額成交」與「小額頻繁成交」。
--
-- open/high/low/close_price：**可為 NULL**。
--   零成交當日，端點的價格欄回傳 `--`（實測：1538 正峰、5906 台南-KY、9110 越南控-DR）。
--   `--` 不是價格，**必須存 NULL，嚴禁存 0**——存 0 等於宣稱「當日成交價為 0 元」，
--   那是 FEATURE_REGISTRY §5A.1 禁止的「把未知填成已知」。
--
-- volume / turnover_amount 於零成交當日為 **0**（不是 NULL）：
--   那是**真實觀測**——確實有 0 股、0 元成交。與價格的 NULL 語意不同：
--   價格是「沒有發生過的事，無值可記」，成交量是「發生了，值為 0」。
--   **兩者必須可區分**，否則 UG-G2-SB6 的排名會把停牌股當成
--   「流動性極低但有效」的樣本，而**排名結果看起來完全正常**（無任何錯誤訊號）。
--   排除「停止交易」是 SB6 建構 Universe 時的職責（DEC-017 排除清單），
--   本表的職責是**忠實記錄**，不是預先過濾。
--
-- ============================================================================
-- 本表**不含**的東西
-- ============================================================================
-- 端點回傳的是「每日收盤行情(全部)」——含 ETF、ETN、權證。
-- 實測 20260821：共 32,751 列，其中 6 碼（權證等）31,523、普通股 1,085。
-- DEC-017 明文「排除 ETF、ETN、權證」，故**寫入前依代號形態過濾**，
-- 過濾規則實作於 `src/extractors/twse_market_report.py`，附 known-FAIL 測試
-- ——**不是解析時順手做掉的一步**。

-- ============================================================================
-- 為什麼存這些「排名用不到」的欄位（PO 2026-08-31 指示）
-- ============================================================================
-- **資料就在回應裡。現在不存，之後要用就得把 3 年重抓一次**——
-- 約 800 次請求，對政府單位的服務。四個 nullable 欄位的成本是零，重抓的成本不是。
--
-- security_name：**DEC-017 明文要求處理「代碼異動（追蹤延續性）」。**
--   代碼變了，靠什麼認出是同一家公司？名稱是回應裡唯一可能的連結。
--   不存它，UG-G2-SB6 的代碼異動處理沒有任何可用訊號。
--
-- best_bid/ask_price/volume：**可能是「停止交易」的唯一判別依據。**
--   實測 20260821 的 1538：成交股數 0、開高低收 `--`，
--   **但最後揭示買價 8.26／賣價 9.97 有值**。
--   一檔真正停止交易的股票是否仍有揭示買賣價——**尚未驗證，且不會為此探測端點**。
--   若答案是「不會」，這就是區分「有掛牌報價但當日無人成交」與「停止交易」的依據，
--   而 DEC-017 要求排除後者。不存它，SB6 到時候可能找不到任何判別訊號。
--
-- pe_ratio：**不可由本表其他欄位推導**（需要 EPS），適用同一個「現在不存就要重抓」的理由。
--   ⚠ **端點的 `0.00` 是 sentinel，不是量測值，寫入前一律轉 NULL。**
--   本益比 = 股價 / EPS；要等於 0.00 需股價為 0 或 EPS 大到股價的兩百倍以上——
--   實務上不存在。交易所在 EPS ≤ 0 或無法計算時填 `0.00`。
--   **實測 20260820**：1085 檔中 `0.00` 者 217 檔，**其中 216 檔有收盤價**
--   （1101 台泥 收盤 24.8、1304 台聚 收盤 11.8 …）——
--   即它**與有無價格無關**，故不做條件式轉換，一律轉 NULL。
--
-- **刻意不存**（已做決定，非默默略過）：
--   `漲跌(+/-)`  —— 內容是 HTML 片段（`<p style= color:red>+</p>`），不是資料；
--                   且方向可由連續兩日 close 推導。
--   `漲跌價差`   —— 可由連續兩日 close 推導，屬衍生值。
--   （無價格的日子兩者都推導不出來，但那些日子本來就沒有價格可比。）

CREATE TABLE IF NOT EXISTS candidate_prices (
    stock_id        VARCHAR(10)  NOT NULL,
    trade_date      DATE         NOT NULL,
    security_name   TEXT,                    -- DEC-017「代碼異動」的唯一連結訊號
    open_price      NUMERIC(12, 4),          -- NULL = 當日未成交，無價可記
    high_price      NUMERIC(12, 4),
    low_price       NUMERIC(12, 4),
    close_price     NUMERIC(12, 4),
    volume          BIGINT       NOT NULL,   -- 0 = 真實觀測到的零成交
    turnover_amount NUMERIC(20, 0) NOT NULL, -- 成交金額（元），DEC-017 排名依據
    transactions    BIGINT,                  -- 成交筆數（端點提供，保留供後續分析）
    -- 最後揭示買賣價量：可能是「停止交易」vs「無人成交」的判別依據（見上方說明）
    best_bid_price  NUMERIC(12, 4),
    best_bid_volume BIGINT,
    best_ask_price  NUMERIC(12, 4),
    best_ask_volume BIGINT,
    pe_ratio        NUMERIC(12, 4),          -- 不可由本表推導，故一併保存
    source          VARCHAR(20)  NOT NULL,   -- 資料來源標記，例：'twse_mi_index'
    -- ⚠ `stock_prices` 沒有來源欄位，正是「無法判斷任何一列是哪個來源」的成因
    --   （yfinance fallback 的 auto_adjust=True vs 證交所原始價）。新表不重蹈覆轍。
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_id, trade_date)
);

-- 排名查詢以 (trade_date, turnover_amount) 為主要存取路徑
CREATE INDEX IF NOT EXISTS idx_candidate_prices_date
    ON candidate_prices (trade_date);

-- 不變式：價格四欄要嘛全部有值，要嘛全部為 NULL。
-- 端點在零成交當日對四欄一律回傳 `--`，不會只缺其中一兩個；
-- 出現「部分有值」代表解析出了問題，那是必須被知道的事，不該被靜默寫入。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_candidate_prices_ohlc_consistency'
    ) THEN
        ALTER TABLE candidate_prices ADD CONSTRAINT chk_candidate_prices_ohlc_consistency
        CHECK (
            (open_price IS NULL AND high_price IS NULL
             AND low_price IS NULL AND close_price IS NULL)
            OR
            (open_price IS NOT NULL AND high_price IS NOT NULL
             AND low_price IS NOT NULL AND close_price IS NOT NULL)
        );
    END IF;
END $$;

-- 不變式：成交量與成交金額不得為負
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_candidate_prices_nonneg'
    ) THEN
        ALTER TABLE candidate_prices ADD CONSTRAINT chk_candidate_prices_nonneg
        CHECK (volume >= 0 AND turnover_amount >= 0);
    END IF;
END $$;

INSERT INTO schema_version (version, description)
VALUES (5, 'Create candidate_prices for Universe liquidity ranking (UG-G2-SB9)')
ON CONFLICT (version) DO NOTHING;
