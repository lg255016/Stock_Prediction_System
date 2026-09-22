-- ============================================================================
-- 專案名稱：金融情緒與股價趨勢預測系統 (Financial Sentiment System)
-- 檔案說明：PostgreSQL 資料庫定義檔 (DDL)，包含建表語法與初始設定資料。
-- 執行順序：建議依序執行，以符合外鍵與系統依賴邏輯。
-- ============================================================================

-- ----------------------------------------------------------------------------
-- [1. 配置與映射層 (Config & Mapping)]
-- 負責控制 ETL 行為與資料對齊，是系統的大腦設定。
-- ----------------------------------------------------------------------------

-- 1.1 追蹤關鍵字表：決定爬蟲每天要去抓哪些標的，並支援 AI 動態探索寫入
CREATE TABLE IF NOT EXISTS tracking_keywords (
    keyword TEXT PRIMARY KEY,
    category TEXT NOT NULL,          -- 類別 (core_stock, macro, theme, ai_discovered)
    is_active BOOLEAN DEFAULT TRUE,  -- 軟刪除開關：TRUE 啟用爬取，FALSE 暫停爬取
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 1.2 實體對應表：解決跨國市場與俗稱問題，將非結構化關鍵字映射到唯一股票代碼
CREATE TABLE IF NOT EXISTS entity_mapping (
    keyword TEXT PRIMARY KEY,
    stock_id TEXT NOT NULL,          -- 系統唯一股票代碼 (對應 stock_prices)
    market TEXT NOT NULL,            -- 市場別 (如 TWSE, TPEX, US)
    description TEXT                 -- 備註 (人工識別用，如「中文全稱」、「鄉民黑話」)
);

-- 1.3 題材-成分股知識映射表：解決產業題材概念 (如矽光子、散熱、CoWoS) 與一對多個股的關聯
CREATE TABLE IF NOT EXISTS theme_stock_mapping (
    theme_keyword VARCHAR(50) NOT NULL,          -- 題材名詞 (如: '矽光子', '散熱模組', 'CoWoS')
    stock_id VARCHAR(20) NOT NULL,                -- 概念成分股代號 (如: '3081', '3324', '2330')
    stock_name VARCHAR(50),                       -- 股票名稱 (如: '聯亞', '雙鴻', '台積電')
    relevance_weight NUMERIC(3, 2) DEFAULT 1.0,   -- 關聯權重 (1.0=核心龍頭, 0.8=主要受惠)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (theme_keyword, stock_id)
);


-- ----------------------------------------------------------------------------
-- [2. 原始資料儲存層 (Raw Data / Data Lake)]
-- 負責存放從外部 API 與網頁爬蟲抓回來的第一手乾淨資料。
-- ----------------------------------------------------------------------------

-- 2.1 股票歷史價格表：存放時序型 OHLCV 股價數據
CREATE TABLE IF NOT EXISTS stock_prices (
    stock_id VARCHAR(20) NOT NULL,       -- 股票代號 (如 '2330', '6488', 'NVDA')
    trade_date DATE NOT NULL,            -- 交易日期
    open_price NUMERIC(10, 2),           -- 開盤價
    high_price NUMERIC(10, 2),           -- 最高價
    low_price NUMERIC(10, 2),            -- 最低價
    close_price NUMERIC(10, 2),          -- 收盤價
    volume BIGINT,                       -- 成交量
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_id, trade_date)   -- 確保同一天同一檔股票不會重複寫入 (冪等性)
);
-- 建立索引：加速 BI 儀表板與特徵工程按日期區間查詢
CREATE INDEX IF NOT EXISTS idx_stock_prices_date ON stock_prices(trade_date);

-- 2.2 社群與新聞輿情表：存放異質文章來源
CREATE TABLE IF NOT EXISTS market_articles (
    article_id SERIAL PRIMARY KEY,       -- 自動遞增唯一流水號
    source VARCHAR(20) NOT NULL,         -- 來源標籤 (預留擴充：'ptt_stock', 'yahoo_news')
    fetch_keyword VARCHAR(50),           -- 爬取時使用的關鍵字 (對應 tracking_keywords)
    post_time TIMESTAMP NOT NULL,        -- 文章發布時間
    title TEXT NOT NULL,                 -- 文章標題
    url TEXT UNIQUE,                     -- 網址 (設為 UNIQUE 防止爬蟲重複寫入)
    author VARCHAR(50),                  -- 作者
    engagement_metric INT DEFAULT 0,     -- 互動指標 (推文數)
    sentiment_score NUMERIC(5, 4),       -- NLP 情緒分數 (算完前為 NULL)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 建立索引：加速 Checkpointing 撈取未處理文章，以及特徵聚合
CREATE INDEX IF NOT EXISTS idx_articles_source_time ON market_articles(source, post_time);
CREATE INDEX IF NOT EXISTS idx_articles_keyword ON market_articles(fetch_keyword);


-- ----------------------------------------------------------------------------
-- [3. NLP 處理與快取層 (Processing & Cache)]
-- 為了節省 LLM API Token 成本與加速運算而設立的中繼站。
-- ----------------------------------------------------------------------------

-- 3.1 情緒快取表：以文章標題為 PK，確保相同的標題永遠只呼叫一次 API
CREATE TABLE IF NOT EXISTS sentiment_cache (
    title TEXT PRIMARY KEY,
    sentiment_score NUMERIC
);


-- ----------------------------------------------------------------------------
-- [4. 機器學習特徵層 (Data Mart)]
-- 專供 ML 訓練與 BI 儀表板使用的黃金特徵表，由 Python FeatureAggregator 產出。
-- ----------------------------------------------------------------------------

-- 4.1 每日機器學習特徵表：已將股價與情緒完美對齊，並加入時間序列衍生特徵
CREATE TABLE IF NOT EXISTS daily_ml_features (
    trade_date DATE,
    stock_id TEXT,
    close_price NUMERIC,             -- 當日收盤價
    volume BIGINT,                   -- 當日成交量
    article_count INTEGER DEFAULT 0, -- 當日討論總聲量 (篇數)
    sentiment_mean NUMERIC,          -- 當日平均情緒分數
    sentiment_3d_ma NUMERIC,         -- 過去3天情緒移動平均 (核心時間序列特徵)
    PRIMARY KEY (trade_date, stock_id)
);


-- ----------------------------------------------------------------------------
-- [5. Migration 版本追蹤 (Schema Version Tracking)]
-- UG-G1-SB4：供 database/apply_migrations.py 判斷目前已套用至哪個版本；
-- 與 database/migrations/001_baseline.sql 定義相同，供全新初始化時直接建立。
-- ----------------------------------------------------------------------------

-- 5.1 Schema 版本表：記錄每個已套用遷移的版本號、描述、時間與內容雜湊
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TIMESTAMP DEFAULT NOW(),
    checksum    TEXT
);


-- ============================================================================
-- [附錄：初始設定資料 (Seed Data)]
-- 在資料庫建立時，預設塞入的核心追蹤名單與映射規則。
-- ============================================================================

-- 塞入靜態預設池關鍵字
INSERT INTO tracking_keywords (keyword, category, is_active) VALUES
    ('環球晶', 'core_stock', TRUE),
    ('廣達', 'core_stock', TRUE),
    ('台積電', 'core_stock', TRUE),
    ('輝達', 'core_stock', TRUE),
    ('降息', 'macro', TRUE),
    ('非農', 'macro', TRUE),
    ('AI伺服器', 'theme', TRUE),
    ('矽光子', 'theme', TRUE),
    ('散熱模組', 'theme', TRUE),
    ('CoWoS', 'theme', TRUE),
    ('高端', 'core_stock', FALSE)
ON CONFLICT (keyword) DO NOTHING;

-- 塞入實體對應規則
INSERT INTO entity_mapping (keyword, stock_id, market, description) VALUES
    ('環球晶', '6488', 'TPEX', '中文全稱'),
    ('廣達', '2382', 'TWSE', '中文全稱'),
    ('台積電', '2330', 'TWSE', '中文全稱'),
    ('輝達', 'NVDA', 'US', '中文譯名'),
    ('NVDA', 'NVDA', 'US', 'Ticker 原名')
ON CONFLICT (keyword) DO UPDATE SET
    stock_id = EXCLUDED.stock_id,
    market = EXCLUDED.market,
    description = EXCLUDED.description;

-- 塞入初始題材概念股籃子規則 (Seed Theme Baskets)
INSERT INTO theme_stock_mapping (theme_keyword, stock_id, stock_name, relevance_weight) VALUES
    ('矽光子', '3081', '聯亞', 1.0),
    ('矽光子', '6442', '光聖', 1.0),
    ('矽光子', '3163', '波若威', 1.0),
    ('矽光子', '2330', '台積電', 0.8),
    ('散熱模組', '3324', '雙鴻', 1.0),
    ('散熱模組', '3017', '奇鋐', 1.0),
    ('散熱模組', '3653', '健策', 0.9),
    ('CoWoS', '3131', '弘塑', 1.0),
    ('CoWoS', '3583', '辛耘', 1.0),
    ('CoWoS', '6187', '萬潤', 0.9),
    ('CoWoS', '2330', '台積電', 1.0),
    ('AI伺服器', '2382', '廣達', 1.0),
    ('AI伺服器', '2317', '鴻海', 0.9),
    ('AI伺服器', '6669', '緯穎', 1.0),
    ('AI伺服器', 'NVDA', '輝達', 1.0)
ON CONFLICT (theme_keyword, stock_id) DO UPDATE SET
    stock_name = EXCLUDED.stock_name,
    relevance_weight = EXCLUDED.relevance_weight,
    updated_at = CURRENT_TIMESTAMP;
