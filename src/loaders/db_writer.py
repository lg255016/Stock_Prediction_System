# src/loaders/db_writer.py
import math
import os
from collections import defaultdict
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd

# UG-G2-SB7 收尾：特徵組成的允許清單（權威在 MULTI_SOURCE_DATA_CONTRACT.md §3.5B）。
from src.transform.source_capabilities import FEATURE_SOURCE_ALLOWLIST
# §0.5 #32：NLP 未完成路徑複用既有、已測試的 cutoff 歸日函式，不重寫歸日邏輯
# （CLAUDE.md §7.1，見 Gate A 提案 §3.3b）。
from src.transform.feature_aggregator import map_timestamp_to_trading_day


class DBWriter:
    def __init__(self, db_config=None):
        """
        初始化資料庫寫入器。
        可以選擇傳入自訂的 db_config；若未傳入，則由執行程序的環境變數取得。
        """
        if db_config is not None:
            self.db_config = dict(db_config)
            missing_keys = [
                key for key in ("database", "user", "password")
                if not self.db_config.get(key)
            ]
            if missing_keys:
                raise ValueError(
                    "db_config 缺少必要設定：" + ", ".join(missing_keys)
                )

            # Dev Container 的 app 與 db 共用 network namespace，
            # 因此 localhost:5432 是目前架構下合理的非秘密開發預設。
            self.db_config.setdefault("host", "localhost")
            self.db_config.setdefault("port", 5432)
            return

        required_env = {
            "POSTGRES_DB": "<database>",
            "POSTGRES_USER": "<user>",
            "POSTGRES_PASSWORD": "<password>",
        }
        missing_env = [name for name in required_env if not os.getenv(name)]
        if missing_env:
            raise RuntimeError(
                "缺少必要資料庫環境變數：" + ", ".join(missing_env)
            )

        db_port = os.getenv("DB_PORT", "5432")
        try:
            db_port = int(db_port)
        except ValueError as exc:
            raise RuntimeError("DB_PORT 必須是有效整數。") from exc

        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": db_port,
            "database": os.environ["POSTGRES_DB"],
            "user": os.environ["POSTGRES_USER"],
            "password": os.environ["POSTGRES_PASSWORD"],
        }

    def _execute_batch(self, query: str, records: list):
        """內部共用的批次執行函數 (Insert / Update 皆適用)"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            execute_values(cursor, query, records)
            conn.commit()
            print(f"[Load] 成功執行資料庫作業。已處理 {len(records)} 筆資料。")
        except Exception as e:
            print(f"[Load] 資料庫作業發生錯誤：{e}")
            if 'conn' in locals():
                conn.rollback()
            raise e
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

    # ==================================================================
    # UG-G2-SB7：候選池每日增量寫入
    # ==================================================================
    CANDIDATE_PRICE_COLS = (
        "stock_id", "trade_date", "security_name", "open_price", "high_price",
        "low_price", "close_price", "volume", "turnover_amount", "transactions",
        "best_bid_price", "best_bid_volume", "best_ask_price", "best_ask_volume",
        "pe_ratio", "source")

    _CANDIDATE_PRICE_INSERT = """
    INSERT INTO candidate_prices
      (stock_id, trade_date, security_name, open_price, high_price, low_price,
       close_price, volume, turnover_amount, transactions,
       best_bid_price, best_bid_volume, best_ask_price, best_ask_volume,
       pe_ratio, source)
    VALUES %s
    ON CONFLICT (stock_id, trade_date) DO NOTHING
    RETURNING stock_id;
    """

    def upsert_to_candidate_prices(self, records: list) -> int:
        """把全市場報表的解析結果寫入 `candidate_prices`，回傳**實際插入**的列數。

        **`ON CONFLICT DO NOTHING` 而非 `DO UPDATE`**：候選池是已收盤的歷史事實，
        重跑同一天不應改寫既有列。冪等（`CLAUDE.md` §7.1），
        而重複執行的回傳值會是 0——**那是正確答案，不是失敗**。

        ⚠ **以 `RETURNING` 計數，不用 `cur.rowcount`**：
        `execute_values` 的 `page_size` 預設 100 會使後者只反映最後一批，
        `UG-G2-SB9` 曾因此把 887 列回報成 87 列、
        並據以宣稱「800 列被靜默丟棄」——**一個不存在的缺陷**。
        """
        if not records:
            return 0
        values = [tuple(r.get(c) for c in self.CANDIDATE_PRICE_COLS) for r in records]
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                returned = execute_values(cur, self._CANDIDATE_PRICE_INSERT, values,
                                          page_size=len(values), fetch=True)
            conn.commit()
            return len(returned)
        finally:
            if conn is not None:
                conn.close()

    def fetch_data(self, query: str, params=None) -> pd.DataFrame:
        """
        供 Phase 2 撈取尚未處理 NLP 的文章
        避開 Pandas SQLAlchemy 警告，改用 psycopg2 原生 cursor 抓取後轉 DataFrame

        Args:
            query: SQL 查詢字串。
            params: 選填的查詢參數（UG-G2-SB4 新增）——供需要繫結變數的查詢使用，
                一律經 psycopg2 參數化，不以字串拼接組 SQL。既有呼叫端不傳此參數，
                行為完全不變。
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query, params) if params is not None else cur.execute(query)
                rows = cur.fetchall()
                if not rows:
                    return pd.DataFrame()
                col_names = [desc[0] for desc in cur.description]
                return pd.DataFrame(rows, columns=col_names)
        finally:
            if conn is not None:
                conn.close()

    # `stock_prices.source` 的值域（migration 009，PRE-G3-03 DP1）。
    # **報表級命名，不是機構級** —— 沿用 candidate_prices.source 的原則（UG-G2-SB9）：
    # 指向哪一份報表，不是哪一個機構。
    #
    # ⚠ 本元組與 migration 009 的 CHECK 約束是**同一份契約的兩個副本**，
    #   而 CLAUDE.md §7.1 禁止維護兩套不一致的定義 ——
    #   `tests/test_stock_prices_source.py` 的 S3 逐值比對兩者，**不一致即 FAIL**。
    STOCK_PRICE_SOURCES = (
        "twse_mi_index",           # 證交所每日收盤行情，經 candidate_prices 帶入原值
        "tpex_daily_quotes",       # 櫃買中心每日收盤行情，經 candidate_prices 帶入原值
        "twse_stock_day",          # 證交所個股日成交資訊，自建爬蟲直取
        "yfinance_auto_adjusted",  # yfinance，auto_adjust=True（yfinance_api.py:63）
    )

    # 寫入欄位順序。**顯式列出，不依賴傳入 DataFrame 的欄位順序** ——
    # 原本的 `df.to_numpy()` 讓欄位順序成為呼叫端的隱性責任，
    # 而順序錯了會把 high 寫進 low，**且不會有任何錯誤**。
    STOCK_PRICE_COLUMNS = [
        "stock_id", "trade_date", "open_price", "high_price",
        "low_price", "close_price", "volume", "source",
    ]

    def upsert_to_stock_prices(self, df: pd.DataFrame):
        """寫入股價資料至 stock_prices。

        ⚠⚠ **`source` 欄是必要輸入**（migration 009／PRE-G3-03 DP1）。
        傳入的 DataFrame 沒有 `source` 欄即 `ValueError`，**不靜默寫 NULL**。

        **為什麼是 DataFrame 欄位而不是函式參數**：回補時一批會同時包含
        上市（`twse_mi_index`）與上櫃（`tpex_daily_quotes`）兩種來源，
        **逐列的來源才是事實**；單一參數會逼呼叫端拆批或選一個當代表。

        **為什麼不靜默寫 NULL**：`NULL` 在本欄有明確語意 ——
        「migration 009 之前寫入，血緣不可考」（既有 137 列）。
        若寫入端可以靜默產生 NULL，那個語意會在第一次每日執行後開始被稀釋，
        **而且每過一天稀釋一列，沒有任何告警**。
        """
        if df is None or df.empty:
            print("[Load] 沒有股價資料需要寫入。")
            return
            
        if "source" not in df.columns:
            raise ValueError(
                "upsert_to_stock_prices 缺少 `source` 欄 —— "
                "migration 009 之後每一列都必須帶血緣（PRE-G3-03 DP1）。"
                "**不得以 NULL 寫入**：NULL 保留給 migration 前的既有列。"
                "可用值：%s" % (self.STOCK_PRICE_SOURCES,))

        # ⚠ **兩道檢查的順序是承重的，改動前請先讀這裡。**
        # 上面那道（缺欄）若被移除或移到這之後，本行的 `df["source"]` 會先丟
        # `KeyError` —— 缺欄仍然被擋下，**但錯誤型別與訊息都不是設計的那一個**。
        # known-FAIL 演練 D1 實測即為此：達成 FAIL，機制卻是 `KeyError`。
        # 換言之 **S1 的保護會跟著順序移動**，而移動後它測到的不再是它宣稱的東西。
        bad = sorted(set(df["source"].dropna().unique())
                     - set(self.STOCK_PRICE_SOURCES))
        if bad or df["source"].isna().any():
            raise ValueError(
                "upsert_to_stock_prices 的 `source` 不合法：%s。"
                "可用值：%s（migration 009 的 CHECK 約束同一份清單）"
                % (bad or "含 NULL/NaN", self.STOCK_PRICE_SOURCES))

        print("\n[Load] 準備寫入股票價格至 PostgreSQL...")
        subset = df[self.STOCK_PRICE_COLUMNS]
        records = [tuple(x) for x in subset.where(pd.notnull(subset), None).to_numpy()]
        
        # ⚠ `source` 也在 DO UPDATE SET 裡，這是刻意的：
        #   DO UPDATE 會覆寫價格值，若不同時更新 source，
        #   那一列就會宣稱一個**與它現在的值不相符**的血緣 —— 比沒有血緣更糟。
        #
        # ⚠⚠ 這**不是**在修 DO UPDATE 本身。「每日重跑會無痕覆寫歷史列」
        #   仍是既存風險，登記於 RISK-022 名下（PRE-G3-03 §3.4）。
        #   **回補路徑另走只補缺日，不用本函式。**
        insert_query = """
            INSERT INTO stock_prices 
            (stock_id, trade_date, open_price, high_price, low_price, close_price,
             volume, source)
            VALUES %s
            ON CONFLICT (stock_id, trade_date) 
            DO UPDATE SET 
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                source = EXCLUDED.source;
        """
        self._execute_batch(insert_query, records)

    # market_articles 13 欄寫入契約（UG-G2-SB3，MULTI_SOURCE_DATA_CONTRACT.md §2.2）。
    # 不含 article_id（SERIAL）與 created_at（DEFAULT）兩個自動欄位。
    # 四個留言計數欄未解析時一律寫 NULL，**嚴禁補 0**——0 代表「已解析且確實零則留言」，
    # NULL 代表「尚未解析」，兩者語意不可混淆（DB_MIGRATION_PLAN.md §4.3）。
    ARTICLE_COLUMNS = [
        'source', 'fetch_keyword', 'post_time', 'title', 'url', 'author',
        'engagement_metric', 'sentiment_score',
        'push_count', 'boo_count', 'neutral_count', 'total_comments',
        'provider_article_id',
    ]

    def upsert_article_comments(self, rows):
        """寫入逐則留言（`article_comments`，migration 008）。

        Args:
            rows: `[(url, seq, tag, comment_time, year_inferred), ...]`
                  —— 以 `url` 指名文章，由本方法轉成 `article_id`，
                  **呼叫端不需要知道那個代理鍵**。

        冪等：`ON CONFLICT (article_id, comment_seq) DO NOTHING`。
        **與留言計數的 UPDATE 是兩條路徑** —— 同 §2.3 對 upsert 與回填的分工。

        ⚠ **本方法不做邊界檢查**。那是
        `comment_timeline.validate_comment_bounds()` 的事，
        而它在呼叫端就把違反的整篇擋掉了 ——
        **一個被擋下的東西不該有第二個地方也能決定放不放行。**
        """
        if not rows:
            return
        sql = """
            INSERT INTO article_comments
                (article_id, comment_seq, comment_tag, comment_time, year_inferred)
            SELECT m.article_id, data.seq, data.tag,
                   data.ts::timestamp, data.inferred
            FROM (VALUES %s) AS data(url, seq, tag, ts, inferred)
            JOIN market_articles m ON m.url = data.url
            ON CONFLICT (article_id, comment_seq) DO NOTHING;
        """
        print(f"\n[Load] 準備寫入 {len(rows)} 則逐則留言至 article_comments...")
        self._execute_batch(sql, rows)

    def upsert_to_market_articles(self, df: pd.DataFrame):
        """
        寫入文章資料至 market_articles（13 欄契約，UG-G2-SB3）。

        使用 ON CONFLICT (url) DO NOTHING，如果網址已存在則略過，確保冪等性——
        依 MULTI_SOURCE_DATA_CONTRACT.md §2.3 已核准之契約，初次寫入維持
        DO NOTHING，留言計數的後續回填走獨立的 UPDATE ... WHERE url=... 路徑，
        不與初次 upsert 混合。
        """
        if df is None or df.empty:
            print("[Load] 沒有文章資料需要寫入。")
            return

        print("\n[Load] 準備寫入文章資料至 PostgreSQL...")

        df_to_save = df.copy()
        for col in self.ARTICLE_COLUMNS:
            if col not in df_to_save.columns:
                df_to_save[col] = None

        df_subset = df_to_save[self.ARTICLE_COLUMNS]
        # 逐值以 pd.isna() 判定並轉為 None，不用 DataFrame.where(cond, None)——
        # 後者對全數值型欄位會把 None 折回 NaN 而非真正的 Python None，NaN 送進
        # INTEGER 欄位會觸發 NumericValueOutOfRange。四個留言計數欄正是 INTEGER
        # 且必須能寫 NULL，會踩到與 UG-G2-SB1 upsert_ml_features() 相同的坑
        # （DEC-023 剩餘風險欄已登記此寫法未經逐一稽核，本 SB 一併修正）。
        records = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df_subset.itertuples(index=False, name=None)
        ]

        insert_query = f"""
            INSERT INTO market_articles
            ({', '.join(self.ARTICLE_COLUMNS)})
            VALUES %s
            ON CONFLICT (url) DO NOTHING;
        """
        self._execute_batch(insert_query, records)

    def update_comment_counts(self, records: list):
        """回填留言計數（UG-G2-SB4）——**write-once**，已有計數者不覆寫。

        MULTI_SOURCE_DATA_CONTRACT.md §2.3：留言計數更新走獨立的
        `UPDATE ... WHERE url=...` 路徑，不與初次 upsert 混合。

        DEC-024（時點有效性判準）：`AND total_comments IS NULL` 這個條件是**承重的**，
        不是效能最佳化——`search?q={keyword}` 每次回傳最近約 20 篇、橫跨數日，
        三天前那篇今天會再被抓到一次。若允許覆寫，就會把**今天**的累計留言數寫進
        **三天前**那個交易日的列，構成真正的前視偏誤。write-once 使每篇文章保留
        「第一次擷取」的值——在穩定的每日排程下，第一次擷取本來就發生在該文章所歸屬
        交易日的決策時點，因此天然是正確時點的值。

        Args:
            records: [(push_count, boo_count, neutral_count, total_comments,
                       comments_scraped_at, url), ...]
        """
        if not records:
            return

        print(f"\n[Load] 準備回填 {len(records)} 筆留言計數至 market_articles（write-once）...")

        update_query = """
            UPDATE market_articles
            SET push_count          = data.push_count::integer,
                boo_count           = data.boo_count::integer,
                neutral_count       = data.neutral_count::integer,
                total_comments      = data.total_comments::integer,
                comments_scraped_at = data.comments_scraped_at::timestamp
            FROM (VALUES %s) AS data(push_count, boo_count, neutral_count,
                                     total_comments, comments_scraped_at, url)
            WHERE market_articles.url = data.url
              AND market_articles.total_comments IS NULL;
        """
        self._execute_batch(update_query, records)

    def fetch_articles_missing_comment_counts(self, urls: list) -> set:
        """回傳 urls 之中「尚未擷取留言計數」者（`total_comments IS NULL`）。

        UG-G2-SB4 決策點 4(b)：已有計數的文章直接跳過，不重複請求內頁——
        這既是節流（RISK-002／RISK-005），也與 write-once 語意一致
        （反正寫回去也會被 `AND total_comments IS NULL` 擋掉）。
        """
        if not urls:
            return set()
        df = self.fetch_data(
            "SELECT url FROM market_articles "
            "WHERE url = ANY(%s) AND total_comments IS NULL;",
            (list(urls),),
        )
        if df is None or df.empty:
            return set()
        return set(df["url"].tolist())

    def update_sentiment_scores(self, df: pd.DataFrame):
        """
        接收帶有 sentiment_score 與主鍵 (如 article_id) 的 DataFrame，批次更新回 PostgreSQL。
        """
        if df is None or df.empty:
            return
            
        df_valid = df.dropna(subset=['article_id', 'sentiment_score'])
        if df_valid.empty:
            return

        print(f"\n[Load] 準備更新 {len(df_valid)} 筆情緒分數至 PostgreSQL...")
        
        data_tuples = [
            (int(row['article_id']), float(row['sentiment_score'])) 
            for _, row in df_valid.iterrows()
        ]
        
        update_query = """
            UPDATE market_articles 
            SET sentiment_score = data.sentiment_score
            FROM (VALUES %s) AS data(article_id, sentiment_score)
            WHERE market_articles.article_id = data.article_id::integer;
        """
        self._execute_batch(update_query, data_tuples)

    def fetch_cached_scores(self, titles: list) -> dict:
        """
        傳入一批標題，去資料庫尋找是否有算過的歷史分數。
        回傳格式: {"標題A": 0.85, "標題B": 0.12}
        """
        if not titles:
            return {}
            
        query = "SELECT title, sentiment_score FROM sentiment_cache WHERE title IN %s;"
        
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query, (tuple(titles),))
                rows = cur.fetchall()
        finally:
            if conn is not None:
                conn.close()

        cached_scores = {}
        for title, raw_score in rows:
            if isinstance(raw_score, (str, bytes, bytearray, bool)):
                raise ValueError(f"快取分數不是數值：{title!r}")
            try:
                score = float(raw_score)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"快取分數不是數值：{title!r}") from exc
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError(f"快取分數必須是 0.0 到 1.0 的有限數值：{title!r}")
            cached_scores[title] = score

        return cached_scores

    def upsert_sentiment_cache(self, records: list):
        """
        將 LLM 算出來的「新標題與新分數」存入快取表。
        records 格式: [("標題A", 0.85), ("標題B", 0.12)]
        """
        if not records:
            return
            
        query = """
            INSERT INTO sentiment_cache (title, sentiment_score)
            VALUES %s
            ON CONFLICT (title) DO NOTHING;
        """
        self._execute_batch(query, records)

    def fetch_active_keywords(self) -> list:
        """
        從 PostgreSQL 撈取所有 is_active = TRUE 的關鍵字。
        回傳格式: ['環球晶', '廣達', '台積電', '降息', ...]
        """
        query = "SELECT keyword FROM tracking_keywords WHERE is_active = TRUE;"
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [row[0] for row in rows]
        finally:
            if conn is not None:
                conn.close()

    def fetch_active_stock_targets(self) -> list:
        """
        從 entity_mapping 與 tracking_keywords 撈取所有處於啟用狀態的股票標的與市場別。
        回傳格式: [{'stock_id': '2330', 'market': 'TWSE'}, {'stock_id': 'NVDA', 'market': 'US'}, ...]
        """
        query = """
            SELECT DISTINCT em.stock_id, em.market 
            FROM entity_mapping em
            JOIN tracking_keywords tk ON em.keyword = tk.keyword
            WHERE tk.is_active = TRUE;
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [{"stock_id": row[0], "market": row[1]} for row in rows]
        finally:
            if conn is not None:
                conn.close()

    def fetch_candidate_prices_max_date_by_market(self) -> dict:
        """首次每日 ETL 缺口自動追補用——依 `source` 值域（`SOURCE_BY_MARKET`）分組查

        `candidate_prices` 的 `MAX(trade_date)`。`candidate_prices` 本身沒有 `market`
        欄，但 `source` 欄的值域即市場對映（`twse_mi_index`／`tpex_daily_quotes`），
        用 `source` 分組等價於依市場分組（`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`
        §3.1 查證）。

        Returns:
            `{"twse": date或None, "tpex": date或None}`——市場在 `candidate_prices`
            沒有任何列時，對應值為 `None`（**不做任何預設**，呼叫端須自行決定
            如何處置；見 `MissingBackfillOriginError`）。
        """
        from src.extractors.market_report_fetcher import SOURCE_BY_MARKET

        query = """
            SELECT source, MAX(trade_date) AS max_date
            FROM candidate_prices
            WHERE source IN %s
            GROUP BY source;
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query, (tuple(SOURCE_BY_MARKET.values()),))
                rows = dict(cur.fetchall())
        finally:
            if conn is not None:
                conn.close()

        return {
            market: rows.get(source)
            for market, source in SOURCE_BY_MARKET.items()
        }

    def fetch_feature_lag(self) -> dict:
        """§0.5 #30 必修——尾端掛點視窗的 n 來源改為「特徵表落後股價表的交易日數」，
        取代原本錯誤地取自 `candidate_prices` 價格缺口的 `n_new_days`（那個來源在
        價格缺口被本次執行自己補齊後會歸零，即使 `daily_ml_features` 仍嚴重落後，
        見 `PROJECT_STATUS.md` §0.5 #30）。

        呼叫時機：逐股階段結束後、特徵階段開始前——此時 `stock_prices` 已是本次
        執行後的最終狀態，`daily_ml_features` 還是特徵階段寫入前的舊狀態，兩者的
        `MAX(trade_date)` 差距即為特徵階段即將新增的交易日數。

        SQL（唯讀）:
            SELECT MAX(trade_date) FROM daily_ml_features;             -- F
            SELECT MAX(trade_date) FROM stock_prices;                  -- P
            SELECT COUNT(DISTINCT trade_date) FROM stock_prices
                WHERE trade_date > %s;                                 -- n_lag（F 為引數）

        Returns:
            `{"feature_max_date": F 或 None, "price_max_date": P 或 None,
              "n_lag": int}`——`F` 為 `None`（`daily_ml_features` 是空表）時
            `n_lag` 直接為 0，不執行第三條查詢。

            實測驗證（唯讀，2026-09-17）：即使省略這個短路、直接把 `None`
            當引數執行第三條查詢，`trade_date > NULL` 在 PostgreSQL 三值邏輯下
            對每一列都是 UNKNOWN，`COUNT(DISTINCT ...)` 一樣算出 0——
            **兩種寫法在目前這句 SQL 下巧合地同答案，不是省略短路會出錯**。
            保留短路的理由是明確表達語意、不依賴這個容易在 SQL 改寫時
            （例如日後改成 `>=` 或 `IS DISTINCT FROM`）失效的三值邏輯巧合，
            並少執行一次查詢，不是「不這樣做會算錯」。
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(trade_date) FROM daily_ml_features;")
                feature_max_date = cur.fetchone()[0]

                cur.execute("SELECT MAX(trade_date) FROM stock_prices;")
                price_max_date = cur.fetchone()[0]

                if feature_max_date is None:
                    n_lag = 0
                else:
                    cur.execute(
                        "SELECT COUNT(DISTINCT trade_date) FROM stock_prices "
                        "WHERE trade_date > %s;",
                        (feature_max_date,),
                    )
                    n_lag = cur.fetchone()[0]
        finally:
            if conn is not None:
                conn.close()

        return {
            "feature_max_date": feature_max_date,
            "price_max_date": price_max_date,
            "n_lag": int(n_lag),
        }

    def fetch_last_discovery_probed_date(self):
        """§0.5 #31——回傳最近一次「有問過」AI 熱門詞探索的日期，供
        `run_all_daily_tasks()` 判斷距今是否已達 `DISCOVERY_INTERVAL_DAYS`
        （見 `doc/upgrade/gates/GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md` §3.1）。

        「有問過」＝ `source='ai_discovery'` `item_key='discovery'`
        `outcome IN ('OK', 'NO_DATA')` 的最近一列 `batch_key`——`NO_DATA` 代表
        探索確實發出過請求、內容為空，一樣算試過；`FETCH_FAILED`／`REFUSED`
        不算，隔天即可再試（恰好對上配額隔天重置的週期）。規則性跳過（A4
        裁決）不寫任何列，因此不會被這條查詢看見。

        Returns:
            `date` 或 `None`（從未問過）。
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(batch_key) FROM etl_run_log "
                    "WHERE source = 'ai_discovery' AND item_key = 'discovery' "
                    "AND outcome IN ('OK', 'NO_DATA');"
                )
                max_key = cur.fetchone()[0]
        finally:
            if conn is not None:
                conn.close()

        if max_key is None:
            return None
        return date.fromisoformat(max_key)

    def fetch_failed_source_keys(self) -> set:
        """§0.5 #32 成因 F 接線——回傳當日特徵應標記 `SOURCE_FAILED` 的
        `(stock_id, "YYYY-MM-DD")` 集合，供 `run_feature_engineering_pipeline()`
        傳入 `FeatureAggregator.generate_daily_features(failed_source_keys=...)`。

        每次呼叫都從資料庫重新推導完整集合（不是本次執行記憶體裡的 outcome）——
        `daily_ml_features` 每次全歷史重算，只用本次 outcome 會把先前標記的
        `SOURCE_FAILED` 洗回 `SUCCESS_EMPTY`（見 Gate A 提案 §3.1）。

        SQL（唯讀，五條查詢，彼此無序）：
            SELECT item_key, batch_key, outcome FROM etl_run_log WHERE source='ptt';
            SELECT keyword, stock_id FROM entity_mapping;
            SELECT theme_keyword, stock_id FROM theme_stock_mapping;
            SELECT stock_id, trade_date FROM stock_prices;
            SELECT article_id, fetch_keyword, post_time FROM market_articles
                WHERE sentiment_score IS NULL;

        合併兩個獨立來源（提案 §3.2／§3.2a／§3.3b）：

        (a) PTT 覆蓋缺口：關鍵字 k 在交易日 D 有覆蓋，若存在 `outcome IN ('OK',
            'NO_DATA')` 的批次 `batch_key=B` 使 `D ∈ [B-2, B]`。起算點取
            `MIN(batch_key) WHERE source='ptt'`，之前的交易日不套用本定義。
            只對「至少一個映射關鍵字曾出現在 PTT run log」的股票做覆蓋判斷
            （§3.2a 選 A——從未被抓過任何關鍵字的股票本案不動）；一檔股票映射
            多個關鍵字時，任一關鍵字覆蓋即算覆蓋。

        (b) NLP 未完成：`market_articles.sentiment_score IS NULL` 的文章，經
            `entity_mapping`／`theme_stock_mapping` 對到的股票，依
            `map_timestamp_to_trading_day()`（既有函式，不重寫歸日邏輯）歸日
            後即成立。不套用 (a) 的「曾被抓過關鍵字」資格過濾——判斷依據是
            「文章確實存在但未評分」，與 PTT 有沒有抓過這個關鍵字無關。
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT item_key, batch_key, outcome FROM etl_run_log "
                    "WHERE source='ptt';")
                ptt_rows = cur.fetchall()

                cur.execute("SELECT keyword, stock_id FROM entity_mapping;")
                entity_rows = cur.fetchall()

                cur.execute(
                    "SELECT theme_keyword, stock_id FROM theme_stock_mapping;")
                theme_rows = cur.fetchall()

                cur.execute("SELECT stock_id, trade_date FROM stock_prices;")
                price_rows = cur.fetchall()

                cur.execute(
                    "SELECT article_id, fetch_keyword, post_time FROM market_articles "
                    "WHERE sentiment_score IS NULL;")
                nlp_rows = cur.fetchall()
        finally:
            if conn is not None:
                conn.close()

        # 股票 <-> 關鍵字的雙向索引（entity_mapping ∪ theme_stock_mapping）。
        stock_keywords = defaultdict(set)
        keyword_stocks = defaultdict(set)
        for keyword, stock_id in entity_rows:
            sid = str(stock_id)
            stock_keywords[sid].add(keyword)
            keyword_stocks[keyword].add(sid)
        for theme_keyword, stock_id in theme_rows:
            sid = str(stock_id)
            stock_keywords[sid].add(theme_keyword)
            keyword_stocks[theme_keyword].add(sid)

        trading_days_by_stock = defaultdict(list)
        for stock_id, trade_date in price_rows:
            trading_days_by_stock[str(stock_id)].append(trade_date)
        for sid in trading_days_by_stock:
            trading_days_by_stock[sid].sort()

        failed_keys = set()

        # (a) PTT 覆蓋缺口——ptt_rows 為空時整段跳過，不對空序列呼叫 min()。
        if ptt_rows:
            origin = min(date.fromisoformat(batch_key) for _, batch_key, _ in ptt_rows)
            ever_crawled = {item_key for item_key, _, _ in ptt_rows}

            covered_keyword_dates = defaultdict(set)
            for item_key, batch_key, outcome in ptt_rows:
                if outcome in ("OK", "NO_DATA"):
                    b = date.fromisoformat(batch_key)
                    for delta in (0, 1, 2):
                        covered_keyword_dates[item_key].add(b - timedelta(days=delta))

            for stock_id, trade_dates in trading_days_by_stock.items():
                keywords = stock_keywords.get(stock_id, set())
                if not (keywords & ever_crawled):
                    continue  # §3.2a：從未被抓過任何關鍵字的股票本案不動
                for d in trade_dates:
                    if d < origin:
                        continue
                    covered = any(
                        d in covered_keyword_dates.get(k, set()) for k in keywords)
                    if not covered:
                        failed_keys.add((stock_id, d.isoformat()))

        # (b) NLP 未完成——與 (a) 的資格過濾無關，獨立計算。
        for _article_id, fetch_keyword, post_time in nlp_rows:
            for stock_id in keyword_stocks.get(fetch_keyword, set()):
                mapped_date = map_timestamp_to_trading_day(
                    post_time, trading_days_by_stock.get(stock_id, []))
                if mapped_date is not None:
                    failed_keys.add((stock_id, mapped_date.isoformat()))

        return failed_keys

    def fetch_ai_discovered_keywords(self, limit: int = 6) -> list:
        """
        從 tracking_keywords 撈取最新探索出的 AI 關鍵字。
        回傳格式: ['矽光子', '散熱模組', 'CoWoS', ...]
        """
        query = """
            SELECT keyword 
            FROM tracking_keywords 
            WHERE category = 'ai_discovered' AND is_active = TRUE 
            ORDER BY updated_at DESC 
            LIMIT %s;
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
                return [row[0] for row in rows]
        finally:
            if conn is not None:
                conn.close()

    def upsert_theme_stock_mapping(self, records: list):
        """
        將題材與概念成分股映射資料寫入 theme_stock_mapping 表。
        records 格式: [('矽光子', '3081', '聯亞', 1.0), ('矽光子', '6442', '光聖', 1.0), ...]
        """
        if not records:
            return

        print(f"\n[Load] 準備寫入 {len(records)} 筆題材成分股映射至 PostgreSQL...")
        # §0.5 #33：既有映射不得被 AI 探索的重複發現覆寫——權重是特徵值的一部分，
        # 每週重估一次就會每週回溯改寫全歷史 bullishness_index（DEC-039 題材溢出
        # 全歷史重算機制，見 RISK-032、§0.5 #32 結案 commit 0c9f169 的 2382 案例）。
        # 改權重必須是有人決定的事，不是 LLM 每次順手做的事——故新配對正常插入，
        # 既有配對三欄（stock_name／relevance_weight／updated_at）一律不動。
        query = """
            INSERT INTO theme_stock_mapping (theme_keyword, stock_id, stock_name, relevance_weight)
            VALUES %s
            ON CONFLICT (theme_keyword, stock_id)
            DO NOTHING;
        """
        self._execute_batch(query, records)

    def fetch_all_theme_baskets(self) -> dict:
        """
        撈取所有題材及其成分股籃子清單。
        回傳格式: {'矽光子': [{'stock_id': '3081', 'stock_name': '聯亞', 'relevance_weight': 1.0}, ...], ...}
        """
        query = """
            SELECT theme_keyword, stock_id, stock_name, relevance_weight
            FROM theme_stock_mapping
            ORDER BY theme_keyword, relevance_weight DESC;
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                baskets = {}
                for theme, s_id, s_name, weight in rows:
                    if theme not in baskets:
                        baskets[theme] = []
                    baskets[theme].append({
                        "stock_id": str(s_id),
                        "stock_name": str(s_name) if s_name else str(s_id),
                        "relevance_weight": float(weight) if weight is not None else 1.0
                    })
                return baskets
        finally:
            if conn is not None:
                conn.close()

    def upsert_tracking_keyword(self, keyword: str, category: str = 'user_added', is_active: bool = True):
        """
        動態新增或更新追蹤關鍵字。
        如果關鍵字已存在，則更新其類別與啟用狀態。
        """
        if not keyword:
            return
            
        print(f"[Config] 正在更新關鍵字設定: {keyword} (啟用: {is_active})")
        
        query = """
            INSERT INTO tracking_keywords (keyword, category, is_active)
            VALUES %s
            ON CONFLICT (keyword) DO UPDATE 
            SET category = EXCLUDED.category, 
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP;
        """
        record = [(keyword, category, is_active)]
        self._execute_batch(query, record)

    def insert_discovered_keywords(self, keywords: list):
        """新增 AI 探索詞；任何既有關鍵字的狀態與分類都保持不變。"""
        records = [
            (keyword, 'ai_discovered', True)
            for keyword in keywords
            if keyword
        ]
        if not records:
            return

        query = """
            INSERT INTO tracking_keywords (keyword, category, is_active)
            VALUES %s
            ON CONFLICT (keyword) DO NOTHING;
        """
        self._execute_batch(query, records)
        
    def disable_tracking_keyword(self, keyword: str):
        """
        停用既有關鍵字；不存在的關鍵字維持 no-op，不建立新資料。
        """
        if not keyword:
            return

        query = """
            UPDATE tracking_keywords
            SET is_active = FALSE,
                updated_at = CURRENT_TIMESTAMP
            FROM (VALUES %s) AS data(keyword)
            WHERE tracking_keywords.keyword = data.keyword;
        """
        self._execute_batch(query, [(keyword,)])

    def delete_tracking_keyword(self, keyword: str):
        """
        硬刪除 (Hard Delete)：將關鍵字從資料庫徹底抹除。
        """
        if not keyword:
            return
        print(f"[Config] 正在從資料庫徹底刪除關鍵字: {keyword}")
        query = "DELETE FROM tracking_keywords WHERE keyword = %s;"
        self._execute_batch(query, [(keyword,)])

    def fetch_all_for_features(self):
        """
        一次撈取所有需要的 Raw Data 供特徵工程使用。
        回傳: df_prices, df_articles, df_mapping, df_theme_mapping, df_comments

        df_comments（2026-09-14，DEC-039 新增）：article_comments 逐則留言，
        範圍與 df_articles 共用（JOIN market_articles 的同一過濾條件），
        供 generate_daily_features() 逐則重算留言特徵用。
        """
        # UG-G2-SB8：補上 high_price／low_price——amplitude_ratio 需要它們，
        # 而 stock_prices 一直都有這兩欄（真實庫實測 117/117 非 NULL）。
        # **這是同型讀取端缺口的第三次**（DEC-029）：SB4 的留言計數欄、
        # SB5 決策點 5 的 source、本次的 high/low——三次都是資料一直都在、
        # 是這一句 SELECT 沒撈，且三次都是靠人偶然發現的。
        # 機械化偵測見 gate0_contract_check.py Part B 第 12 項（反查檢查）。
        df_prices = self.fetch_data(
            "SELECT trade_date, stock_id, high_price, low_price, close_price, volume "
            "FROM stock_prices;"
        )
        # UG-G2-SB4：補上四個留言計數欄與擷取時點——SB3 完成 Schema 與寫入契約後，
        # 此查詢仍未 SELECT 這些欄位，特徵層因此看不到留言資料（讀取端缺口）。
        # 註：WHERE sentiment_score IS NOT NULL 為既有條件，使留言特徵隱性耦合於 NLP
        # 完成度（已解析留言但 NLP 未跑完的文章不會進入特徵計算）。此為既有行為，
        # 非 UG-G2-SB4 引入，但會影響留言特徵實際覆蓋率。
        # UG-G2-SB5 決策點 5：補上 `source`——方向類留言特徵是否可計算，
        # 取決於該來源在結構上提不提供推／噓標記（`source_capabilities`）。
        # 這是同型缺口的**第二例**：欄位一直都在 `market_articles`（NOT NULL），
        # UI 路徑（`ui/data_loader.py`）也一直有撈，缺的只是特徵路徑這一句 SELECT。
        # UG-G2-SB7 收尾（PO 2026-09-05）：**以允許清單過濾取樣 regime。**
        #
        # `source` **一直都有被 SELECT，只是沒拿它過濾** ——
        # 同 UG-G2-SB5 決策點 5 的形狀：欄位在、讀取端沒用。
        #
        # ⚠ **是允許清單，不是排除清單。** `source <> 'ptt_stock'` 的失效方向是
        # 「日後新增來源而忘了登錄 → 自動進入特徵」；
        # 允許清單的失效方向是「不會進入」。**後者才是誠實地少。**
        # 清單與理由見 `src/transform/source_capabilities.py`
        # 與 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5B。
        _allow = ", ".join(
            "'%s'" % s for s in sorted(FEATURE_SOURCE_ALLOWLIST))
        df_articles = self.fetch_data(
            "SELECT article_id, source, post_time, fetch_keyword, sentiment_score, "
            "push_count, boo_count, neutral_count, total_comments, comments_scraped_at "
            "FROM market_articles WHERE sentiment_score IS NOT NULL "
            "AND source IN (%s);" % _allow
        )
        df_mapping = self.fetch_data("SELECT keyword, stock_id FROM entity_mapping;")
        df_theme_mapping = self.fetch_data("SELECT theme_keyword, stock_id, relevance_weight FROM theme_stock_mapping;")

        # RISK-023／DEC-039：留言特徵改依逐則時間戳重算，取代文章層級
        # comments_scraped_at 過濾。與上面 df_articles 的 SELECT 共用同一個
        # 範圍過濾（JOIN market_articles，而非整表載入 article_comments）——
        # 避免載入不會被 generate_daily_features() 用到的留言列。
        df_comments = self.fetch_data(
            "SELECT ac.article_id, ac.comment_seq, ac.comment_tag, ac.comment_time "
            "FROM article_comments ac "
            "JOIN market_articles ma ON ma.article_id = ac.article_id "
            "WHERE ma.sentiment_score IS NOT NULL "
            "AND ma.source IN (%s);" % _allow
        )

        return df_prices, df_articles, df_mapping, df_theme_mapping, df_comments

    # daily_ml_features 29 欄契約（UG-G2-SB1，DB_MIGRATION_PLAN.md §4.2）。
    # 未存在於輸入 DataFrame 的欄位一律寫 NULL，不得補 0 或中立值（CLAUDE.md §7.1）——
    # CORE_16／留言衍生特徵／target_triple_barrier 尚未由 feature_aggregator.py 產出，
    # 對應欄位在本 SB 之後仍為 NULL，直到各自負責的 SB／Gate 完成。
    #
    # ⚠⚠ target_triple_barrier／label_reason 由標籤寫入者擁有（UG-G3-SB1 腳本／
    # UG-G3-SB2 每日尾端掛點／UG-G3-SB2a 段 3），upsert_ml_features() 的
    # ON CONFLICT DO UPDATE SET **刻意不覆寫這兩欄**（見該方法內 LABEL_OWNED_COLUMNS，
    # CHAL-010）——每日特徵 upsert 若覆寫，會把既有標籤全部清空。
    ML_FEATURE_COLUMNS = [
        'trade_date', 'stock_id', 'close_price', 'volume',
        'article_count', 'sentiment_mean', 'sentiment_3d_ma',
        'return_1d', 'rsi_14', 'volatility_5d', 'volatility_20d',
        'bullishness_index', 'agreement_index',
        'sentiment_5d_ma', 'sentiment_lag_1', 'sentiment_lag_2',
        'amplitude_ratio', 'ma5_bias_ratio', 'ma20_bias_ratio', 'volume_ratio_5d',
        'comment_volume_ratio', 'comment_polarization', 'net_push_momentum',
        'target_next_close', 'target_return_1d', 'target_up_down', 'target_triple_barrier',
        'source_status', 'label_reason',
    ]

    def upsert_ml_features(self, df: pd.DataFrame):
        """寫入聚合好的每日 ML 特徵表（29 欄契約，UG-G2-SB1）"""
        if df is None or df.empty:
            return

        print(f"\n[Load] 準備寫入 {len(df)} 筆特徵數據至 daily_ml_features...")

        # 強制將 Timestamp 或 date 轉回 python date string 以免 psycopg2 報錯
        df_to_save = df.copy()
        df_to_save['trade_date'] = pd.to_datetime(df_to_save['trade_date']).dt.strftime('%Y-%m-%d')

        target_cols = self.ML_FEATURE_COLUMNS
        for col in target_cols:
            if col not in df_to_save.columns:
                df_to_save[col] = None

        df_subset = df_to_save[target_cols]
        # 逐值以 pd.isna() 判定並轉為 None，不用 DataFrame.where(cond, None)——
        # 後者對全數值型（如 float64）欄位會把 None 折回 NaN 而非真正的 Python None，
        # 純數值欄位裡的 NaN（例如每檔股票最後一個交易日的 target_up_down）會被
        # psycopg2 送成非法整數值，觸發 NumericValueOutOfRange（UG-G2-SB1 E2E 驗證發現）。
        records = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df_subset.itertuples(index=False, name=None)
        ]

        # target_triple_barrier／label_reason 由標籤寫入者擁有（UG-G3-SB1 腳本／
        # UG-G3-SB2 每日尾端掛點／UG-G3-SB2a 段 3），不由本方法覆寫——
        # feature_aggregator 的輸出從不包含這兩欄，若列入 DO UPDATE SET，
        # 每一次每日特徵 upsert 都會把既有標籤覆寫成 NULL（CHAL-010，
        # PO 2026-09-10 複審 UG-G3-SB2a 提案期間發現）。INSERT 欄位清單仍含
        # 這兩欄（新列本來就還沒有標籤，值為 None 是正確狀態），只有
        # ON CONFLICT 的 DO UPDATE SET 排除它們。
        LABEL_OWNED_COLUMNS = ('target_triple_barrier', 'label_reason')
        update_cols = [
            c for c in target_cols
            if c not in ('trade_date', 'stock_id') and c not in LABEL_OWNED_COLUMNS
        ]
        set_clause = ",\n                ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        query = f"""
            INSERT INTO daily_ml_features
            ({', '.join(target_cols)})
            VALUES %s
            ON CONFLICT (trade_date, stock_id)
            DO UPDATE SET
                {set_clause};
        """
        self._execute_batch(query, records)

    def update_triple_barrier_tail_labels(self, df_tail: pd.DataFrame):
        """
        UG-G3-SB2 §3.1 每日尾端重算掛點的寫入層——只更新
        `target_triple_barrier`／`label_reason` 兩欄，不動 `daily_ml_features`
        其餘 27 欄。呼叫端傳入 `src.ml.triple_barrier.recompute_tail_labels()`
        的輸出（每檔股票尾端 `holding_period + 1` 列）。

        **刻意用 `UPDATE`，不是 `INSERT ... ON CONFLICT DO UPDATE`**——本方法
        只提供 4 欄，若目標列不存在，`ON CONFLICT` 的 `INSERT` 分支會建立一個
        其餘 27 欄皆為 NULL 的殘缺列。設計前提是本掛點排在當日特徵列（其餘
        欄位）寫入之後執行，目標列理應已存在；若實際影響列數少於預期，代表
        前提被違反，回傳實際影響列數供呼叫端判斷（`CLAUDE.md` §7.1「失敗
        不得偽裝成正常結果」——沉默的 0 列 UPDATE 不算安全）。

        ⚠ 本方法已定義但尚未被 `main_etl_pipeline.py` 的每日排程呼叫
        （見 `run_triple_barrier_tail_recompute()` 的接線但不啟用註記）——
        首次對真實庫啟用需 PO binding confirmation（RISK-013 三項協議），
        比照 `UG-G3-SB1` 的真實庫寫入流程。

        Returns:
            int: 實際影響列數（供呼叫端與 `len(df_tail)` 比對）。
        """
        if df_tail is None or df_tail.empty:
            return 0

        print(f"\n[Load] 準備更新 {len(df_tail)} 筆 Triple-Barrier 尾端重算標籤...")

        df_to_save = df_tail.copy()
        df_to_save['trade_date'] = pd.to_datetime(df_to_save['trade_date']).dt.strftime('%Y-%m-%d')

        # 逐值 pd.isna() 判定並轉為 None——沿用 UG-G3-SB1 已驗證的雙欄轉型，
        # 不重新發明；target 為 float64（NaN 迫使），需先轉 Python int/None，
        # label_reason 直接判 None（psycopg2 對 TEXT 欄位的 None 即寫 SQL NULL，
        # 不會重演 float NaN 被轉接為文字 'NaN' 的已知失敗模式）。
        n_updated = 0
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                for row in df_to_save[["stock_id", "trade_date", "target_triple_barrier", "label_reason"]].itertuples(index=False, name=None):
                    stock_id, trade_date, target, reason = row
                    tb_val = None if pd.isna(target) else int(target)
                    reason_val = None if pd.isna(reason) else reason
                    cur.execute(
                        "UPDATE daily_ml_features SET target_triple_barrier = %s, label_reason = %s "
                        "WHERE stock_id = %s AND trade_date = %s",
                        (tb_val, reason_val, stock_id, trade_date),
                    )
                    n_updated += cur.rowcount
            conn.commit()
            print(f"[Load] Triple-Barrier 尾端重算完成，實際影響 {n_updated} 列（預期 {len(df_tail)} 列）。")
        except Exception as e:
            print(f"[Load] Triple-Barrier 尾端重算發生錯誤：{e}")
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

        return n_updated
