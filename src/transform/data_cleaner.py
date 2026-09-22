# src/transform/data_cleaner.py
import re

import pandas as pd
from datetime import datetime, timedelta, timezone
from src.common.clock import now_taipei

# PTT 文章 URL → provider_article_id 解析用（UG-G2-SB3）
_PTT_URL_PATTERN = re.compile(r"/bbs/([^/]+)/([^/]+?)\.html?$", re.IGNORECASE)


def build_ptt_provider_article_id(url) -> str:
    """由 PTT 文章 URL 產生 provider_article_id。

    MULTI_SOURCE_DATA_CONTRACT.md §3.1 格式：`ptt_{board}_{article_filename}`
    （例：`https://www.ptt.cc/bbs/Stock/M.1724567890.A.123.html`
      → `ptt_Stock_M.1724567890.A.123`）。

    §2.3：本欄為輔助去重索引，**不取代** `market_articles.url` 的 UNIQUE 約束。

    無法解析時回傳 None，不回傳部分猜測值——一個格式錯誤的 provider_article_id
    比沒有更糟（會被誤當成有效識別碼跨平台比對）。
    """
    if url is None or not isinstance(url, str):
        return None
    match = _PTT_URL_PATTERN.search(url.strip())
    if not match:
        return None
    board, filename = match.group(1), match.group(2)
    return f"ptt_{board}_{filename}"


def format_provider_symbol(stock_id: str, market: str) -> str:
    """
    根據市場別格式化資料提供者 (如 yfinance) 的股票代碼。

    Args:
        stock_id: 股票代碼 (Canonical Stock ID, 如 '2330', '6488', 'NVDA')
        market: 市場類別 ('TWSE', 'TPEX', 'OTC', 'US')

    Returns:
        str: 格式化後的 Provider Symbol (如 '2330.TW', '6488.TWO', 'NVDA')

    Raises:
        ValueError: 若市場類別不支援或不是有效字串
    """
    if not isinstance(market, str):
        raise ValueError(f"Unsupported market: {market}")

    market_upper = market.strip().upper()
    if market_upper == "TWSE":
        return f"{stock_id}.TW"
    elif market_upper in ("TPEX", "OTC"):
        return f"{stock_id}.TWO"
    elif market_upper == "US":
        return str(stock_id)
    else:
        raise ValueError(f"Unsupported market: {market}")


# ==========================================================================
# UG-G2-SB7 步驟 1：PTT 文章時間的權威來源是**網址**，不是索引頁的日期欄
# ==========================================================================
# PTT 是台灣的看板，`M.<unix>.A.<n>` 的 `<unix>` 是該篇的建立時刻（epoch 秒）。
#
# ⚠⚠ **必須顯式轉 UTC+8，不得用 `datetime.fromtimestamp()` 的機器本地時區。**
# dev container 的 `time.tzname` 是 `('UTC', 'UTC')`（實測 2026-09-05）——
# 用本地時區，一篇台北時間 03:20 的文章會變成前一天的 19:20。
# **日期會整個差一天，而且差多少取決於容器怎麼設**，
# 而 `feature_aggregator` 的 `cutoff_time` 是 `15:30`：
# **八小時的位移足以讓一篇文章從收盤後變成收盤前。**
_PTT_TZ = timezone(timedelta(hours=8))
_PTT_URL_TS_RE = re.compile(r"/M\.(\d+)\.A\.")


def parse_ptt_post_time(url, date_str, reference_time=None):
    """PTT 文章的發文時間：**優先取網址內嵌的 unix 時間戳**。

    Args:
        url: 文章網址，如 `https://www.ptt.cc/bbs/Stock/M.1568748048.A.001.html`
        date_str: 索引頁的日期欄（`9/18`）——**僅作回退**
        reference_time: 回退路徑的參考時間

    Returns:
        naive `datetime`（台北時間）。`market_articles.post_time` 是
        `TIMESTAMP WITHOUT TIME ZONE`，**轉換在寫入前完成**。

    ================================================================
    為什麼不能用索引頁的日期欄
    ================================================================
    索引頁只給 `MM/DD` —— **沒有年份、沒有時刻**。
    `parse_ptt_datetime` 的跨年推論只處理 **±1 年**邊界，
    **而 `/search?q=` 回傳的是全站歷史，跨越七年。**

    > **跨年推論的前提是「這些文章都是最近的」，而搜尋結果從來不是。
    > 那個假設從沒被寫下來，因此也從沒被檢查。**

    實測（2026-09-05，`postgres`@`localhost:5432`）：331 篇中 **96 篇**
    `post_time` 與網址時間戳不同日，年份差 **+1 至 +7**；
    其中 **26 篇**落在 `daily_ml_features` 的日期窗內 ——
    **2019~2025 年的文章被聚合進 2026 年的特徵列**（`CLAUDE.md` §7.4 家族）。

    ⚠ **取不到時間戳時回退到 `parse_ptt_datetime`，不得丟掉該列** ——
    丟掉會讓「解析失敗」長得像「沒有這篇文章」（§7.1 換一個粒度）。
    """
    m = _PTT_URL_TS_RE.search(url) if isinstance(url, str) else None
    if m:
        return datetime.fromtimestamp(int(m.group(1)), _PTT_TZ).replace(tzinfo=None)
    return parse_ptt_datetime(date_str, reference_time=reference_time)


def parse_ptt_datetime(date_str: str, reference_time: datetime = None) -> datetime:
    """
    解析 PTT 日期字串，支援完整時間戳記、ISO 格式與短日期 (MM/DD) 跨年智慧推論。

    Args:
        date_str: PTT 日期字串 (如 'Wed Aug 20 14:25:36 2026', '2026-08-20 14:25:36', '8/20', ' 8/20')
        reference_time: 參考基準時間 (預設為 datetime.now())，用於 MM/DD 補齊年份與跨年判定

    Returns:
        datetime: 解析後的 datetime 物件
    """
    if not date_str or not isinstance(date_str, str):
        return reference_time or now_taipei()

    clean_str = date_str.strip()
    if not clean_str:
        return reference_time or now_taipei()

    ref = reference_time or now_taipei()

    # 1. 嘗試常見的完整時間格式
    full_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%a %b %d %H:%M:%S %Y",  # PTT 內頁標準格式: 'Wed Aug 20 14:25:36 2026'
        "%a %b  %d %H:%M:%S %Y", # PTT 內頁單日空格: 'Wed Aug  5 14:25:36 2026'
        "%Y-%m-%d",
        "%Y/%m/%d"
    ]
    for fmt in full_formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            pass

    # 2. 嘗試短日期格式 (MM/DD 或 M/D)
    short_formats = ["%m/%d", "%m-%d"]
    for s_fmt in short_formats:
        try:
            dt_parsed = datetime.strptime(clean_str, s_fmt)
            parsed_month = dt_parsed.month
            parsed_day = dt_parsed.day

            # 智慧跨年判定 (Smart Year Inference):
            # 若參考時間為 1~3 月，而文章月份為 10~12 月，判定為前一年的文章
            if ref.month <= 3 and parsed_month >= 10:
                inferred_year = ref.year - 1
            # 若參考時間為 10~12 月，而文章月份為 1~3 月，判定為同一年 (通常不會是未來)
            elif ref.month >= 10 and parsed_month <= 3 and (parsed_month - ref.month) > 6:
                inferred_year = ref.year + 1
            else:
                inferred_year = ref.year

            # 列表短日期預設時間為當日 12:00:00 (代表盤中)
            return datetime(inferred_year, parsed_month, parsed_day, 12, 0, 0)
        except ValueError:
            pass

    # 3. 若皆無法解析，回傳參考基準時間
    return ref


class DataCleaner:
    def __init__(self, reference_time: datetime = None):
        """
        初始化清洗器，可在這裡宣告共用屬性。
        """
        self.reference_time = reference_time
        self.current_year = (reference_time.year if reference_time
                             else now_taipei().year)

    def format_provider_symbol(self, stock_id: str, market: str) -> str:
        """格式化 Provider Symbol"""
        return format_provider_symbol(stock_id, market)

    def clean_twse_stock_data(self, df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
        """清洗台灣證交所股價資料"""
        if df is None or df.empty:
            return df
            
        print(f"\n[Transform] 開始清洗 {stock_id} 的股價資料...")
        df_clean = df.copy()
        
        df_clean['stock_id'] = str(stock_id)
        
        df_clean = df_clean.rename(columns={
            'date': 'trade_date',
            'open': 'open_price',
            'high': 'high_price',
            'low': 'low_price',
            'close': 'close_price',
            'volume': 'volume'
        })
        
        final_cols = ['stock_id', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume']
        print(f"[Transform] {stock_id} 股價資料清洗完成！")
        return df_clean[final_cols]

    def clean_yfinance_stock_data(self, df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
        """清洗 yfinance 股價資料 (美股或台股備援)"""
        if df is None or df.empty:
            return df
            
        print(f"\n[Transform] 開始清洗 {stock_id} 的股價資料...")
        df_clean = df.copy()
        
        df_clean['stock_id'] = str(stock_id)
        df_clean['Date'] = pd.to_datetime(df_clean['Date']).dt.tz_localize(None).dt.date
        
        df_clean = df_clean.rename(columns={
            'Date': 'trade_date',
            'Open': 'open_price',
            'High': 'high_price',
            'Low': 'low_price',
            'Close': 'close_price',
            'Volume': 'volume'
        })
        
        final_cols = ['stock_id', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume']
        print(f"[Transform] {stock_id} 股價資料清洗完成！")
        return df_clean[final_cols]

    def clean_ptt_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗 PTT 輿情資料"""
        if df is None or df.empty:
            return df
            
        print("\n[Transform] 開始清洗 PTT 文章資料...")
        df_clean = df.copy()
        
        # 將原本內嵌的 function 改為 class 內部邏輯
        df_clean['engagement_metric'] = df_clean['push_count'].apply(self._parse_push_count)
        # ⚠⚠ **UG-G2-SB7 步驟 1：改由 `url` 決定，不再由 `date` 欄決定。**
        #
        # 本行的前一版是 `df_clean['date'].apply(self._parse_date)` ——
        # 而**下面第三行**早就在用同一個 DataFrame 的 `url`。
        # **專案早就知道 url 帶著權威時間，只是拿它做 ID、沒拿它做時間。**
        df_clean['post_time'] = [
            parse_ptt_post_time(u, d, reference_time=self.reference_time)
            for u, d in zip(df_clean['url'], df_clean['date'])
        ]
        df_clean['sentiment_score'] = None
        # UG-G2-SB3：由 url 推導 provider_article_id（純字串處理，不需額外請求）
        df_clean['provider_article_id'] = df_clean['url'].apply(build_ptt_provider_article_id)

        final_cols = [
            'source', 'fetch_keyword', 'post_time', 'title',
            'url', 'author', 'engagement_metric', 'sentiment_score',
            'provider_article_id'
        ]

        print("[Transform] PTT 資料清洗完成！")
        return df_clean[final_cols]

    # --- 私有輔助方法 (Private Helper Methods) ---
    def _parse_push_count(self, push_str: str) -> int:
        """解析 PTT 推文數"""
        if not push_str: return 0
        if push_str == '爆': return 100
        if push_str.startswith('X'): return -10
        try:
            return int(push_str)
        except ValueError:
            return 0

    def _parse_date(self, date_str: str) -> datetime:
        """解析 PTT 日期格式，支援完整時間戳記與跨年推論"""
        return parse_ptt_datetime(date_str, reference_time=self.reference_time)