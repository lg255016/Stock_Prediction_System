# src/transform/feature_aggregator.py
from datetime import datetime, time, date
from typing import Optional, Union, List, Dict
import bisect
import pandas as pd
import numpy as np

from src.transform.source_capabilities import provides_comment_direction
from src.transform.comment_timeline import counts_as_of, validate_comment_bounds, is_time_reset

# ============================================================================
# UG-G2-SB7 B 輪：SOURCE_FAILED 與 §5A.3 的「社群情緒」欄位
# ============================================================================
SOURCE_FAILED = "SOURCE_FAILED"

# **權威來源：`FEATURE_REGISTRY.md` §5A.3 的「社群情緒」群組（該處逐字列 8 欄）。**
#
# ⚠ 本清單是那份契約的**複本**，而複本會漂移 ——
#   `tests/test_source_failed_nulls.py` **直接解析 §5A.3 的表格**並斷言兩者逐欄相符。
#   **沒有那個測試，「指向 §5A.3」就只是一句話**：
#   本輪的起因正是一份短了三欄的清單。
#
# ⚠ 「社群留言」是**另一個群組**（`comment_volume_ratio`／`comment_polarization`），
#   它們本來就「不填補 — 保持 NULL」，**已合規**，不在本清單內。
SOCIAL_SENTIMENT_COLUMNS = (
    "article_count",
    "sentiment_mean",
    "bullishness_index",
    "agreement_index",
    "sentiment_3d_ma",
    "sentiment_5d_ma",
    "sentiment_lag_1",
    "sentiment_lag_2",
)


def enforce_source_failed_nulls(df):
    """把 `SOURCE_FAILED` 列的 §5A.3 社群情緒八欄全部設為 NULL。

    **契約 `MULTI_SOURCE_DATA_CONTRACT.md:321` 逐字**：
    「該來源當日特徵保持 `NULL`；**不得**寫入 0 或中立值；該筆排除訓練」。

    ⚠ **刻意做成「最後一道」而非散落在各計算點**：
    情緒欄經過填補、rolling、shift 三段處理，**每一段都可能把 NULL 補回去**
    （`sentiment_lag_1/2` 自帶的 `fillna(0.5)` 就是實例）。
    集中在一個地方，契約要求才有一個**可稽核的落點**。

    ⚠ **`sentiment_3d_ma`／`sentiment_5d_ma` 的 NULL 是契約要求，不是設計選擇** ——
    `rolling(min_periods=1)` 會跳過 NaN，**在失敗日仍會給出一個由鄰近日推出的、
    看起來合理的數字**，那比它取代的 `0.5` 更難發現。

    ⚠ **本函式不負責「該筆排除訓練」** —— 那需要一個讀 `daily_ml_features` 的消費端，
    而 `src/ml/` 目前零命中。排除屬 `UG-G3-SB2` 的 panel dataset。
    """
    if "source_status" not in df.columns:
        return df
    mask = df["source_status"] == SOURCE_FAILED
    if not mask.any():
        return df
    for col in SOCIAL_SENTIMENT_COLUMNS:
        if col in df.columns:
            df.loc[mask, col] = np.nan
    return df


def map_timestamp_to_trading_day(
    timestamp: datetime | pd.Timestamp | str,
    trading_days: list[date] | pd.Series | pd.DatetimeIndex,
    cutoff_time: str | time = "15:30:00"
) -> date | None:
    """
    根據預測截止時間點 (Cutoff Time) 與交易日曆，將文章發布時間映射至對應的交易日 (Roll-Forward Mapping)。

    Args:
        timestamp: 文章時間戳記 (datetime, Timestamp 或字串)
        trading_days: 有序的交易日清單 (由小到大排序的 date 物件)
        cutoff_time: 當日截止時間點 (字串如 '15:30:00' 或 time 物件，支援雙模式架構)

    Returns:
        date | None: 映射後的目標交易日，若超出日曆範圍則回傳 None
    """
    if timestamp is None or pd.isna(timestamp):
        return None

    # 1. 正規化 timestamp
    if isinstance(timestamp, str):
        try:
            ts = pd.to_datetime(timestamp).to_pydatetime()
        except Exception:
            return None
    elif isinstance(timestamp, pd.Timestamp):
        ts = timestamp.to_pydatetime()
    elif isinstance(timestamp, datetime):
        ts = timestamp
    else:
        return None

    # 2. 正規化 cutoff_time
    if isinstance(cutoff_time, str):
        try:
            cutoff_t = datetime.strptime(cutoff_time.strip(), "%H:%M:%S").time()
        except ValueError:
            cutoff_t = time(15, 30, 0)
    elif isinstance(cutoff_time, time):
        cutoff_t = cutoff_time
    else:
        cutoff_t = time(15, 30, 0)

    # 3. 正規化 trading_days 為 sorted list of datetime.date
    if isinstance(trading_days, (pd.DatetimeIndex, pd.Series)):
        valid_dates = [d.date() if isinstance(d, (datetime, pd.Timestamp)) else d for d in trading_days]
    else:
        valid_dates = [d.date() if isinstance(d, (datetime, pd.Timestamp)) else d for d in trading_days if d is not None]

    sorted_days = sorted(list(set(valid_dates)))
    if not sorted_days:
        return None

    post_date = ts.date()
    post_time_of_day = ts.time()

    # 4. 判斷是否超過當日 Cutoff
    # 若發文時間 > Cutoff，該文章屬於下一個交易日的情緒窗口
    # 若發文時間 <= Cutoff，若當天是交易日則歸當天；若當天是休假日則向後滾動至下一個交易日
    if post_time_of_day > cutoff_t:
        # 尋找嚴格大於 post_date 的最小交易日
        idx = bisect.bisect_right(sorted_days, post_date)
        if idx < len(sorted_days):
            return sorted_days[idx]
        else:
            return None
    else:
        # 發文時間 <= Cutoff
        if post_date in sorted_days:
            return post_date
        else:
            # 休假日 (週六/週日/假期)，尋找大於 post_date 的最小交易日
            idx = bisect.bisect_right(sorted_days, post_date)
            if idx < len(sorted_days):
                return sorted_days[idx]
            else:
                return None


def assign_trading_days_to_articles(
    df_articles: pd.DataFrame,
    trading_days: list[date] | pd.Series | pd.DatetimeIndex,
    cutoff_time: str | time = "15:30:00"
) -> pd.DataFrame:
    """
    批次將文章 DataFrame 中的 post_time 欄位依 Roll-Forward 規則映射至 trade_date。
    """
    if df_articles is None or df_articles.empty:
        return df_articles

    df_res = df_articles.copy()
    df_res['trade_date'] = df_res['post_time'].apply(
        lambda x: map_timestamp_to_trading_day(x, trading_days, cutoff_time=cutoff_time)
    )
    # 過濾掉無法對齊到任何交易日的文章 (超出日曆邊界)
    df_res = df_res.dropna(subset=['trade_date'])
    return df_res


def assign_trading_days_per_stock(
    df: pd.DataFrame,
    trading_days_by_stock: Dict[str, list],
    cutoff_time: str | time = "15:30:00"
) -> pd.DataFrame:
    """依每一列自身的 `stock_id` 所屬股票之交易日曆做 Roll-Forward Mapping。

    **RISK-027 方案 B（PO 2026-09-11 Gate A 裁決）**：取代
    `assign_trading_days_to_articles()` 的全市場聯集單一日曆——後者把「任一檔
    有交易」誤判為「不是假日」，造成跨市場輸入（如台股＋NVDA）下，文章被滾動到
    某檔股票根本不存在的交易日，與該股價格表合併時靜默流失
    （見 `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-027、`CHAL-011`）。

    `df` 必須已含 `stock_id` 欄——呼叫端須**先**與 `df_mapping`／`df_theme_mapping`
    合併展開成 `(article, stock_id)` 列，**再**呼叫本函式；順序是承重的，
    不能反過來（先指派 `trade_date` 再合併，就是修復前的錯誤順序）。

    規則與 `map_timestamp_to_trading_day()` 逐分支等價（僅將「全市場聯集日曆」
    換成「該列 `stock_id` 對應的日曆」）：兩者統一為「該股票日曆中
    `>= 生效日` 的最小交易日」，其中生效日 = 發文日（未過 cutoff）或
    發文日 + 1（已過 cutoff）。在單一市場輸入下，兩函式對同一批資料的輸出
    必須逐列相等（見 `tests/test_risk027_cross_market_calendar.py` 的不變性測試）。

    找不到該股票下一個交易日的 `(article, stock)` 列一律丟棄（`trade_date` 為
    `NaT`），沿用 `map_timestamp_to_trading_day()`「超出日曆範圍回傳 `None`」
    的既有語意，**不得**回退到聯集日曆。
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    cutoff_t = normalize_cutoff_time(cutoff_time)

    ts = pd.to_datetime(df['post_time'], errors='coerce')
    valid = ts.notna()
    df = df.loc[valid].copy()
    ts = ts.loc[valid]
    if df.empty:
        return df

    post_date = ts.dt.normalize()
    is_after_cutoff = np.array([t > cutoff_t for t in ts.dt.time])
    effective_date = (
        post_date + pd.to_timedelta(is_after_cutoff.astype(int), unit='D')
    ).dt.date
    eff_arr_all = np.array(effective_date.tolist(), dtype='datetime64[D]')

    mapped = np.full(len(df), np.datetime64('NaT', 'D'), dtype='datetime64[D]')
    stock_ids = df['stock_id'].to_numpy()
    for stock_id in pd.unique(stock_ids):
        days = trading_days_by_stock.get(stock_id)
        if not days:
            continue
        mask = stock_ids == stock_id
        days_arr = np.array(sorted(set(days)), dtype='datetime64[D]')
        eff_arr = eff_arr_all[mask]
        pos = np.searchsorted(days_arr, eff_arr, side='left')
        found = pos < len(days_arr)
        mapped[mask] = np.where(
            found, days_arr[np.clip(pos, 0, len(days_arr) - 1)], np.datetime64('NaT', 'D')
        )

    df['trade_date'] = pd.Series(mapped, index=df.index)
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    df = df.dropna(subset=['trade_date'])
    return df


def compute_bullishness_index(pos_count, neg_count):
    """
    計算 Antweiler & Frank (2004) 看多指數 (Bullishness Index, RES-001):
    B_t = ln((1 + M_t^Pos) / (1 + M_t^Neg))
    具備 Laplace 平滑 (+1)，防止 ln(0) 或除以零。
    """
    pos = np.asarray(pos_count, dtype=float)
    neg = np.asarray(neg_count, dtype=float)
    res = np.log((1.0 + pos) / (1.0 + neg))
    if isinstance(pos_count, pd.Series):
        return pd.Series(res, index=pos_count.index)
    return float(res) if np.ndim(res) == 0 else res


def compute_agreement_index(pos_count, neg_count):
    """
    計算 Antweiler & Frank (2004) 一致性指數 (Agreement Index, RES-002):
    A_t = 1 - sqrt(1 - ((M_t^Pos - M_t^Neg) / (M_t^Pos + M_t^Neg))^2)
    若 Pos + Neg == 0，定義為 0.0 (無共識)。值域: [0.0, 1.0]。
    """
    pos = np.asarray(pos_count, dtype=float)
    neg = np.asarray(neg_count, dtype=float)
    total = pos + neg

    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(total > 0, (pos - neg) / total, 0.0)
        ratio_sq = np.clip(ratio ** 2, 0.0, 1.0)
        res = np.where(total > 0, 1.0 - np.sqrt(1.0 - ratio_sq), 0.0)

    if isinstance(pos_count, pd.Series):
        return pd.Series(res, index=pos_count.index)
    return float(res) if np.ndim(res) == 0 else res


def normalize_cutoff_time(cutoff_time):
    """將 cutoff_time（字串或 time 物件）正規化為 datetime.time，無法解析時回退 15:30。

    UG-G2-SB4 抽出為共用函式：原本此段邏輯只存在於 assign_trading_days_to_articles()
    內部，但留言計數的時點稽核（DEC-024）也需要同一個 cutoff 才能算出決策時點。
    """
    if isinstance(cutoff_time, str):
        try:
            return datetime.strptime(cutoff_time.strip(), "%H:%M:%S").time()
        except ValueError:
            return time(15, 30, 0)
    if isinstance(cutoff_time, time):
        return cutoff_time
    return time(15, 30, 0)


def compute_push_ratio(push_count, boo_count):
    """推噓比（FEATURE_REGISTRY.md §5.1）。

        push_ratio_t = (push_t - boo_t) / (push_t + boo_t + 1)

    +1 為 Laplace 平滑，防止零除。值域 (-1.0, 1.0)，
    正值表示看多主導，負值表示看空主導。
    """
    push = pd.to_numeric(push_count, errors="coerce")
    boo = pd.to_numeric(boo_count, errors="coerce")
    return (push - boo) / (push + boo + 1)


def compute_rsi(close_series: pd.Series, period: int = 14) -> pd.Series:
    """
    以純 Pandas / NumPy 向量化計算 Wilder's Relative Strength Index (RSI-14, RES-004):
    - 範圍: [0.0, 100.0]
    - 初期樣本不足或全無波動時以 50.0 (中立動能) 補值
    """
    if len(close_series) < 2:
        return pd.Series(50.0, index=close_series.index)

    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's Exponential Smoothing (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.where(avg_loss > 0, avg_gain / avg_loss, np.nan)
        rsi = np.where(
            avg_loss == 0,
            np.where(avg_gain > 0, 100.0, 50.0),
            100.0 - (100.0 / (1.0 + rs))
        )

    res = pd.Series(rsi, index=close_series.index)
    return res.fillna(50.0)


def compute_rolling_volatility(return_series: pd.Series, window: int = 5, annualize: bool = True) -> pd.Series:
    """
    計算歷史對數報酬率之滾動年化波動率 (Rolling Historical Volatility, RES-005):
    - window: 滾動窗口 (如 5 日週線, 20 日月線)
    - annualize: 是否乘上 sqrt(252) 年化因子 (預設 True)
    - 初始樣本不足時補 0.0
    """
    scale = np.sqrt(252.0) if annualize else 1.0
    vol = return_series.rolling(window=window, min_periods=2).std() * scale
    return vol.fillna(0.0)


class FeatureAggregator:
    def __init__(self):
        print("[FeatureAggregator] 已初始化 ML 特徵聚合器 (支援雙模式時間對齊、研究指標與題材情緒溢出)")

    def generate_daily_features(
        self,
        df_prices: pd.DataFrame,
        df_articles: pd.DataFrame,
        df_mapping: pd.DataFrame,
        df_theme_mapping: Optional[pd.DataFrame] = None,
        cutoff_time: str = "15:30:00",
        failed_source_keys=None,
        df_comments: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        將原始股價與非結構化文章，透過 Mapping 表轉換為每日 ML 特徵表。

        Args（UG-G2-SB7 B 輪新增）:
            failed_source_keys: `{(stock_id, "YYYY-MM-DD"), ...}` ——
                當日**社群來源取數失敗**的 (股票, 日期)。
                這些列的 `source_status` 為 `SOURCE_FAILED`，
                且 §5A.3「社群情緒」八欄**全部保持 NULL**（契約 :321）。

                ⚠ **預設 `None` 時行為與 B 輪之前完全相同** ——
                既有列不重算的前提。

                ⚠ **由呼叫端提供，不由本層查 `etl_run_log`**：
                本層不該知道 run log 的存在，而呼叫端本來就握有那次執行的 outcome。
            df_comments（2026-09-14，DEC-039 新增）：`article_comments` 逐則留言
                （`article_id`／`comment_seq`／`comment_tag`／`comment_time`）。

                ⚠ **只要 `df_articles` 展開後有直接映射的 (article, stock_id) 列，
                本參數就不得省略**——省略時本函式會在呼叫
                `_aggregate_direct_comment_counts()` 前主動拋出 `ValueError`，
                不會靜默退回已被 RISK-023 診斷判定為結構性缺陷的文章層級
                `comments_scraped_at` 過濾。空表請傳入空 `DataFrame`，不要傳 `None`。
        支援雙模式預測架構之 Cutoff Time (預設 15:30:00 盤後動能延續模式，亦支援 08:30:00 盤前即時反應模式)。
        支援題材-成分股知識圖譜之情緒溢出加權聚合 (Thematic Spillover Effect)。
        """
        if df_prices is None or df_prices.empty:
            print("[WARNING] [Feature] 股價資料為空，無法進行特徵聚合。")
            return pd.DataFrame()

        print(f"[INFO] [Feature] 開始聚合特徵：股價 {len(df_prices)} 筆, 文章 {len(df_articles) if df_articles is not None else 0} 筆 (Cutoff: {cutoff_time})")

        # 確保 df_prices 中的 trade_date 為標準 datetime.date 與數值欄位型態標準化
        df_prices_clean = df_prices.copy()
        df_prices_clean['trade_date'] = pd.to_datetime(df_prices_clean['trade_date']).dt.date
        for p_col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume']:
            if p_col in df_prices_clean.columns:
                df_prices_clean[p_col] = pd.to_numeric(df_prices_clean[p_col], errors='coerce')
        # RISK-027 方案 B（PO 2026-09-11 Gate A 裁決）：交易日曆改為「每檔股票自己的
        # trade_date 集合」，取代先前的全市場聯集單一日曆——後者會把「任一檔有交易」
        # 誤判為「不是假日」，造成跨市場輸入下文章被滾動到某檔股票不存在的交易日、
        # 與該股價格表合併時靜默流失（見 REMAINING_RISKS.md RISK-027、CHAL-011）。
        trading_days_by_stock = {
            sid: sorted(set(grp['trade_date']))
            for sid, grp in df_prices_clean.groupby('stock_id')
        }

        # ==========================================
        # 1. 處理文章資料 (直接情緒 + 題材溢出情緒)
        # ==========================================
        if df_articles is not None and not df_articles.empty and df_mapping is not None and not df_mapping.empty:
            # 確保文章有 sentiment_score，過濾掉還沒算完 NLP 的空值並強制轉型為 float (防範 PostgreSQL Decimal 物件)
            df_arts = df_articles.dropna(subset=['sentiment_score']).copy()
            df_arts['sentiment_score'] = pd.to_numeric(df_arts['sentiment_score'], errors='coerce')
            df_arts = df_arts.dropna(subset=['sentiment_score'])

            if not df_arts.empty:
                # 標記多空文章 (看多: score >= 0.55, 看空: score <= 0.45)
                df_arts['is_pos'] = (df_arts['sentiment_score'] >= 0.55).astype(float)
                df_arts['is_neg'] = (df_arts['sentiment_score'] <= 0.45).astype(float)

                # 1.1 直接個股情緒計算 (Direct Sentiment)
                #
                # ⚠ 順序是承重的（RISK-027 方案 B）：先合併映射表展開成
                # (article, stock_id) 列，再依「該列 stock_id 自身的交易日曆」
                # 做 Roll-Forward——不能像修復前那樣在合併之前就用單一聯集日曆
                # 決定 trade_date。
                df_arts_direct = df_arts.merge(
                    df_mapping[['keyword', 'stock_id']],
                    left_on='fetch_keyword',
                    right_on='keyword',
                    how='inner'
                )
                df_arts_direct = assign_trading_days_per_stock(
                    df_arts_direct, trading_days_by_stock, cutoff_time=cutoff_time
                )

                if not df_arts_direct.empty:
                    daily_direct = df_arts_direct.groupby(['trade_date', 'stock_id']).agg(
                        direct_count=('sentiment_score', 'count'),
                        direct_sentiment_mean=('sentiment_score', 'mean'),
                        direct_pos_count=('is_pos', 'sum'),
                        direct_neg_count=('is_neg', 'sum')
                    ).reset_index()
                else:
                    daily_direct = pd.DataFrame(columns=[
                        'trade_date', 'stock_id', 'direct_count', 'direct_sentiment_mean',
                        'direct_pos_count', 'direct_neg_count'
                    ])

                # 1.1b 留言計數聚合（UG-G2-SB4）——**只採用直接個股文章**
                #
                # 決策點 2 選項 C（PO 2026-08-28）：題材溢出文章的留言數不計入成分股。
                # 理由：comment_polarization 與 net_push_momentum 都是 push_ratio 的函數，
                # 一篇題材文章的留言若計入 4 檔成分股，這 4 檔的這兩個特徵會幾乎完全相同——
                # 模型會看到 4 筆看似獨立、實則同源的樣本，這不只是稀疏，是製造假的相關性，
                # 比 NULL 有害。DEC-009 對情緒走 70/30 是合理的（情緒是方向訊號，可以外溢），
                # 但留言數量是量級，「這篇題材文有 500 則留言」不等於「每檔成分股各獲得
                # 500 則討論」，性質不同，不套用同一個先例。（DEC-025）
                # DEC-039：df_comments 為必要參數，不得省略後靜默退回舊的
                # 文章層級 comments_scraped_at 過濾（見本函式 docstring）。
                if df_comments is None:
                    raise ValueError(
                        "generate_daily_features() 收到直接映射的文章列，"
                        "但未提供 df_comments（article_comments 逐則資料）——"
                        "DEC-039 已取消文章層級留言時點過濾，不得省略後靜默退回舊判準。"
                        "呼叫端請改用 db_writer.fetch_all_for_features() 的新回傳值，"
                        "或明確傳入空 DataFrame（若確定沒有任何逐則留言）。"
                    )
                daily_comments = self._aggregate_direct_comment_counts(
                    df_arts_direct, normalize_cutoff_time(cutoff_time), df_comments
                )

                # 1.2 題材溢出情緒計算 (Thematic Spillover Sentiment)
                daily_theme = pd.DataFrame(columns=[
                    'trade_date', 'stock_id', 'theme_count', 'theme_sentiment_mean',
                    'theme_pos_count', 'theme_neg_count'
                ])

                if df_theme_mapping is not None and not df_theme_mapping.empty:
                    # 複製並強制將 relevance_weight 轉換為 float
                    df_theme_map_clean = df_theme_mapping[['theme_keyword', 'stock_id', 'relevance_weight']].copy()
                    df_theme_map_clean['relevance_weight'] = pd.to_numeric(
                        df_theme_map_clean['relevance_weight'], errors='coerce'
                    ).fillna(1.0).astype(float)

                    # 合併題材映射表——同樣先展開成 (article, stock_id) 列，
                    # 再依各股自身交易日曆滾動（RISK-027 方案 B）。
                    df_arts_theme = df_arts.merge(
                        df_theme_map_clean,
                        left_on='fetch_keyword',
                        right_on='theme_keyword',
                        how='inner'
                    )
                    df_arts_theme = assign_trading_days_per_stock(
                        df_arts_theme, trading_days_by_stock, cutoff_time=cutoff_time
                    )
                    if not df_arts_theme.empty:
                        # 權重加成
                        df_arts_theme['weighted_score'] = df_arts_theme['sentiment_score'].astype(float) * df_arts_theme['relevance_weight']
                        df_arts_theme['weighted_pos'] = df_arts_theme['is_pos'].astype(float) * df_arts_theme['relevance_weight']
                        df_arts_theme['weighted_neg'] = df_arts_theme['is_neg'].astype(float) * df_arts_theme['relevance_weight']

                        daily_theme = df_arts_theme.groupby(['trade_date', 'stock_id']).agg(
                            theme_count=('sentiment_score', 'count'),
                            theme_weighted_score_sum=('weighted_score', 'sum'),
                            theme_weight_sum=('relevance_weight', 'sum'),
                            theme_pos_count=('weighted_pos', 'sum'),
                            theme_neg_count=('weighted_neg', 'sum')
                        ).reset_index()

                        daily_theme['theme_sentiment_mean'] = (
                            daily_theme['theme_weighted_score_sum'] / daily_theme['theme_weight_sum']
                        )
                        daily_theme = daily_theme.drop(columns=['theme_weighted_score_sum', 'theme_weight_sum'])

                # 1.3 動態原位加權融合 (In-Place Dynamic Fusion)
                if not daily_direct.empty and not daily_theme.empty:
                    merged_sent = daily_direct.merge(daily_theme, on=['trade_date', 'stock_id'], how='outer')
                elif not daily_direct.empty:
                    merged_sent = daily_direct.copy()
                    merged_sent['theme_count'] = 0
                    merged_sent['theme_sentiment_mean'] = np.nan
                    merged_sent['theme_pos_count'] = 0.0
                    merged_sent['theme_neg_count'] = 0.0
                elif not daily_theme.empty:
                    merged_sent = daily_theme.copy()
                    merged_sent['direct_count'] = 0
                    merged_sent['direct_sentiment_mean'] = np.nan
                    merged_sent['direct_pos_count'] = 0.0
                    merged_sent['direct_neg_count'] = 0.0
                else:
                    merged_sent = pd.DataFrame()

                if not merged_sent.empty:
                    merged_sent['direct_count'] = merged_sent.get('direct_count', 0).fillna(0).astype(int)
                    merged_sent['theme_count'] = merged_sent.get('theme_count', 0).fillna(0).astype(int)
                    merged_sent['direct_pos_count'] = pd.to_numeric(merged_sent.get('direct_pos_count', 0), errors='coerce').fillna(0.0).astype(float)
                    merged_sent['direct_neg_count'] = pd.to_numeric(merged_sent.get('direct_neg_count', 0), errors='coerce').fillna(0.0).astype(float)
                    merged_sent['theme_pos_count'] = pd.to_numeric(merged_sent.get('theme_pos_count', 0), errors='coerce').fillna(0.0).astype(float)
                    merged_sent['theme_neg_count'] = pd.to_numeric(merged_sent.get('theme_neg_count', 0), errors='coerce').fillna(0.0).astype(float)

                    # 動態融合規則：
                    # 1. 直接文章與題材兼備：70% 直接 + 30% 題材
                    # 2. 僅直接文章：100% 直接
                    # 3. 僅題材文章：100% 題材溢出補位
                    def _fuse_sentiment(row):
                        has_direct = row['direct_count'] > 0 and pd.notnull(row['direct_sentiment_mean'])
                        has_theme = row['theme_count'] > 0 and pd.notnull(row['theme_sentiment_mean'])
                        if has_direct and has_theme:
                            return 0.70 * float(row['direct_sentiment_mean']) + 0.30 * float(row['theme_sentiment_mean'])
                        elif has_direct:
                            return float(row['direct_sentiment_mean'])
                        elif has_theme:
                            return float(row['theme_sentiment_mean'])
                        return 0.5

                    merged_sent['sentiment_mean'] = merged_sent.apply(_fuse_sentiment, axis=1).astype(float)
                    merged_sent['article_count'] = merged_sent['direct_count'] + merged_sent['theme_count']

                    # 融合多空加權計數以計算 Antweiler 指數
                    merged_sent['pos_count'] = np.where(
                        (merged_sent['direct_count'] > 0) & (merged_sent['theme_count'] > 0),
                        merged_sent['direct_pos_count'] + 0.30 * merged_sent['theme_pos_count'],
                        np.where(merged_sent['direct_count'] > 0, merged_sent['direct_pos_count'], merged_sent['theme_pos_count'])
                    )
                    merged_sent['neg_count'] = np.where(
                        (merged_sent['direct_count'] > 0) & (merged_sent['theme_count'] > 0),
                        merged_sent['direct_neg_count'] + 0.30 * merged_sent['theme_neg_count'],
                        np.where(merged_sent['direct_count'] > 0, merged_sent['direct_neg_count'], merged_sent['theme_neg_count'])
                    )

                    merged_sent['bullishness_index'] = compute_bullishness_index(
                        merged_sent['pos_count'], merged_sent['neg_count']
                    )
                    merged_sent['agreement_index'] = compute_agreement_index(
                        merged_sent['pos_count'], merged_sent['neg_count']
                    )

                    daily_sentiment = merged_sent[[
                        'trade_date', 'stock_id', 'article_count', 'sentiment_mean',
                        'bullishness_index', 'agreement_index'
                    ]].copy()
                else:
                    daily_sentiment = pd.DataFrame(columns=[
                        'trade_date', 'stock_id', 'article_count', 'sentiment_mean',
                        'bullishness_index', 'agreement_index'
                    ])
            else:
                daily_sentiment = pd.DataFrame(columns=[
                    'trade_date', 'stock_id', 'article_count', 'sentiment_mean',
                    'bullishness_index', 'agreement_index'
                ])
                daily_comments = self._empty_daily_comments()
        else:
            # 如果完全沒有文章，建立一個空的 DataFrame 以防合併報錯
            daily_sentiment = pd.DataFrame(columns=[
                'trade_date', 'stock_id', 'article_count', 'sentiment_mean',
                'bullishness_index', 'agreement_index'
            ])
            daily_comments = self._empty_daily_comments()

        # ==========================================
        # 2. 合併股價與情緒特徵
        # ==========================================
        # 使用 Left Join 保留所有交易日，沒有文章的日子情緒特徵為 NaN
        df_features = df_prices_clean.merge(
            daily_sentiment,
            on=['trade_date', 'stock_id'],
            how='left'
        )
        # 留言計數同樣以 left join 併入；沒有留言資料的 (交易日, 股票) 保持 NaN，
        # 後續由 _compute_comment_features() 轉為 NULL 特徵（FEATURE_REGISTRY.md §5A.5：
        # 未解析／無留言資料一律 NULL，不得補 0 或中立值）。
        df_features = df_features.merge(
            daily_comments,
            on=['trade_date', 'stock_id'],
            how='left'
        )

        # ==========================================================
        # UG-G2-SB7 B 輪：source_status 必須在填補**之前**決定
        # ==========================================================
        # **順序是承重的**：填補會把 NaN 變成 0／0.5，
        # 之後就再也分不出「那天沒有文章」與「那天沒能查」。
        # 先定狀態、再依狀態決定填不填。
        failed_keys = set(failed_source_keys or ())
        _key = list(zip(df_features['stock_id'].astype(str),
                        pd.to_datetime(df_features['trade_date'])
                        .dt.strftime('%Y-%m-%d')))
        is_failed = np.array([k in failed_keys for k in _key], dtype=bool)

        # `SUCCESS` / `SUCCESS_EMPTY` 依 article_count（NaN 視為 0）；
        # 命中 failed_keys 者覆寫為 `SOURCE_FAILED`。
        _has_article = df_features['article_count'].fillna(0) > 0
        df_features['source_status'] = np.where(
            is_failed, SOURCE_FAILED,
            np.where(_has_article, 'SUCCESS', 'SUCCESS_EMPTY'))

        # 補值策略：沒有文章討論的日子，文章數為 0，看多與一致性指數為 0.0——
        # 這三欄在空日是**真值**（`PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md` §1.4：
        # `bullishness_index` 有 Laplace 平滑定義、`agreement_index` 公式明文
        # `Pos+Neg==0 → 0.0`），不是編出來的中立值。
        #
        # ⚠⚠ **只對非 SOURCE_FAILED 的列填補**（UG-G2-SB7 B 輪）。
        # 契約 `MULTI_SOURCE_DATA_CONTRACT.md:321` 逐字：
        #   `SOURCE_FAILED` → 「該來源當日特徵保持 NULL；**不得**寫入 0 或中立值；
        #                       該筆排除訓練」
        #
        # 【D5，`PRE-G3-04`，PO 2026-09-07 裁決】`sentiment_mean` **不在此填補**——
        # 空日（`article_count == 0`）的 `sentiment_mean` 是**成因 U（數學未定義）**，
        # 不是成因 F：資料確實拿到了（沒有文章討論），只是「情緒平均」在零篇文章上
        # 沒有定義，填 `0.5` 是編出來的、不是算出來的。§5A.2 U 分支見
        # `FEATURE_REGISTRY.md`。三個衍生欄（`sentiment_3d_ma`／`sentiment_5d_ma`／
        # `sentiment_lag_1`／`sentiment_lag_2`）的 U 傳播規則見下方個別計算點。
        _fill = ~is_failed
        df_features.loc[_fill, 'article_count'] = \
            df_features.loc[_fill, 'article_count'].fillna(0)
        df_features.loc[_fill, 'bullishness_index'] = \
            df_features.loc[_fill, 'bullishness_index'].fillna(0.0)
        df_features.loc[_fill, 'agreement_index'] = \
            df_features.loc[_fill, 'agreement_index'].fillna(0.0)
        # ⚠ `article_count` **不再無條件 astype(int)** ——
        # `SOURCE_FAILED` 列必須保持 NULL，而 numpy 整數型別無法表示 NULL。

        # source_status（UG-G2-SB1，daily_ml_features 29 欄契約 metadata 欄）：
        # article_count = direct_count + theme_count（見上方 1.3 動態原位加權融合），
        # 兩者皆為 0 時 article_count 才會是 0，故 article_count > 0 等價於「直接文章或題材溢出
        # 至少一者存在」。依 PO 核准之判定邏輯（G2_SB1_GATE_A_PROPOSAL.md §7 決策點 1），
        # 題材溢出視為合法訊號、計入 SUCCESS——這代表 coverage_ratio 量的是「有無可用訊號」，
        # 不是「原生直接討論量」，兩者不可混為一談（見 REMAINING_RISKS.md RISK-015）。
        # 本專案目前僅 PTT 單一來源，SOURCE_DEGRADED／SOURCE_FAILED 兩態依 Gate 0 契約
        # （MULTI_SOURCE_DATA_CONTRACT.md §7.2/§7.4）需 UG-G2-SB2 的 pipeline 例外傳播才可能產生，
        # 本函式僅產出 SUCCESS／SUCCESS_EMPTY 兩態。
        # 【UG-G2-SB7 B 輪】本區塊已上移至填補之前，並新增 `SOURCE_FAILED`。
        # 原本只由 `article_count > 0` 決定，**只產得出兩態** ——
        # 而 `002_expand_ml_features.sql:86` 的 CHECK 允許四態，
        # **後兩格因此結構上無法到達**（§9A.1 在資料庫層）。
        #
        # ⚠ **`SOURCE_DEGRADED` 仍不可達 —— 但阻塞在下游，不在上游**
        #   （UG-G2-SB7 第 5 項更正，2026-09-05）。
        #
        #   **本行的前一版寫的是**：「它需要『部分頁面成功、部分失敗』的逐頁
        #   outcome，而 `scrape_ptt_stock_by_keyword` 不回報那個粒度。」
        #   **那句話現在是錯的，而且錯在會誤導工作方向。**
        #
        #   每日路徑已不走該函式。`scrape_ptt_board_pages`（第 5 項）
        #   **回報得出那個粒度** —— 預算用盡而未回溯到目標時間即為
        #   `SOURCE_DEGRADED`。**能力已經具備。**
        #
        #   實際阻塞點：`main_etl_pipeline.run_ptt_board_pipeline` 把該 outcome
        #   **折成 `etl_run_log` 的 `FETCH_FAILED`**，沒有任何路徑把它送進
        #   `daily_ml_features.source_status`。
        #
        #   > **舊註解說阻塞在上游（沒有那個能力），實際在下游（有能力但沒接線）。**
        #   > **一個過期的理由，會讓一件已經變容易的事看起來仍然很難** ——
        #   > 讀到舊句子的人會以為得先改 scraper，而那已經不是真的。
        #
        #   **接線刻意延後**：它要先決定「一天之內部分關鍵字降級」如何映射到
        #   **逐股票、逐交易日**的 `source_status`（兩者粒度不同），
        #   那是設計決定，不是一行改動。
        #
        #   **本輪仍只讓三態可達，不得寫成「四態已實作」。**

        # ==========================================
        # 3. 計算時間序列衍生特徵 (ML 亮點)
        # ==========================================
        # 先依照股票代碼與日期排序，確保時間序列正確
        df_features = df_features.sort_values(by=['stock_id', 'trade_date']).reset_index(drop=True)
        
        # 歷史 1 日對數報酬率 (已知過去價量動能: ln(Close_T / Close_{T-1}))
        df_features['return_1d'] = df_features.groupby('stock_id')['close_price'] \
                                              .transform(lambda x: np.log(x.astype(float) / x.shift(1).astype(float))) \
                                              .fillna(0.0)

        # 技術動能指標: RSI-14 (RES-004)
        df_features['rsi_14'] = df_features.groupby('stock_id')['close_price'] \
                                           .transform(lambda x: compute_rsi(x.astype(float), period=14))

        # 風險波動度指標: 5 日週線與 20 日月線滾動年化波動率 (RES-005)
        df_features['volatility_5d'] = df_features.groupby('stock_id')['return_1d'] \
                                                 .transform(lambda x: compute_rolling_volatility(x, window=5, annualize=True))
        df_features['volatility_20d'] = df_features.groupby('stock_id')['return_1d'] \
                                                  .transform(lambda x: compute_rolling_volatility(x, window=20, annualize=True))

        # ==========================================
        # 3b. CORE_16 平穩化特徵（UG-G2-SB8；DEC-029 範圍、DEC-030 NULL 策略）
        #     FEATURE_REGISTRY.md §3.4、§3.7 模型輸入第 13–16 號
        # ==========================================
        #
        # 【契約未指定、本 SB 決定的一件事】MA 視窗是否含當日：
        #   - `ma5/ma20_bias_ratio` 的 MA **含當日**——`(Close − MA5)/MA5` 是標準
        #     均線偏離率，MA 不含當日會變成另一個指標。
        #   - `volume_ratio_5d` 的 MA5_Vol **不含當日**（`t-5..t-1`）——沿用同族
        #     `comment_volume_ratio` 的既有慣例（§5.2 明文「僅使用 t-5..t-1 已知資料」）。
        #     基準含當日會讓今日成交量出現在自己的分母裡，壓抑本來要偵測的放量訊號。
        _close = df_features['close_price'].astype(float)

        # §3.4 amplitude_ratio = (High − Low) / Close
        #
        # 【DEC-030 決策點 1】契約原指定 `fillna(0.0)`，本 SB 修正為**保持 NULL**：
        # 三個值全部來自同一列，沒有 lag、沒有 rolling window——
        # **成因 W（暖機期）在結構上不可能發生**。因此該填補唯一可能觸發的情境
        # 就是 high/low 取不到，那是**成因 F**，§5A.1 明文「必須保持 NULL，嚴禁任何填補」。
        # 且 `0.0` 的語意是 `High == Low`（漲跌停鎖死／整日無成交）——
        # 一個真實且有意義的市場事件。把「取不到高低價」填成「振幅為零」，
        # 正是 §5A.1 禁止的「把未知填成已知的中立」。
        if 'high_price' in df_features.columns and 'low_price' in df_features.columns:
            df_features['amplitude_ratio'] = (
                (df_features['high_price'].astype(float) - df_features['low_price'].astype(float))
                / _close.replace(0.0, np.nan)   # Close == 0：成因 U（見下），保持 NULL
            )
        else:
            # 讀取端沒撈到 high/low —— 成因 F。不得填補，也不得讓欄位消失
            # （欄位消失會讓 db_writer 的「不在 DataFrame 就填 None」把它變成 NULL，
            #  結果雖同，但那是巧合而非設計；明確寫 NaN 使意圖可讀）。
            df_features['amplitude_ratio'] = np.nan

        # §3.4 ma5_bias_ratio / ma20_bias_ratio = (Close − MA_n) / MA_n
        #
        # 【DEC-030 決策點 2】暖機期屬**成因 W**，依 §5A.1 允許填補，
        # 本 SB **維持契約的 `fillna(0.0)`**，與已上線的 `return_1d`／`volatility_*`
        # 一致。但「`0.0` 是事件值而非值域結構中點」這個問題涵蓋那些兄弟欄位，
        # 已登記 RISK-020，Gate 3 啟動前裁決——**不在本 SB 決定**。
        for _win, _col in ((5, 'ma5_bias_ratio'), (20, 'ma20_bias_ratio')):
            _ma = df_features.groupby('stock_id')['close_price'].transform(
                lambda s, w=_win: s.astype(float).rolling(window=w).mean()
            )
            _warmup = _ma.isna()                       # 成因 W
            _bias = (_close - _ma) / _ma.replace(0.0, np.nan)   # MA == 0：成因 U
            df_features[_col] = _bias.where(~_warmup, 0.0)

        # §3.4 volume_ratio_5d = Volume / MA5_Vol
        #
        # 【DEC-030 決策點 3】契約原文「`fillna(1.0)`；暖機期分母為零時」把**兩種
        # 不同成因寫成同一件事**，本 SB 拆開：
        #   - 暖機期（不足 5 日基準）→ **成因 W**，填 `1.0`（維持契約）
        #   - **MA5_Vol == 0**（過去 5 日完全沒有成交）→ **成因 U（數學未定義）**，
        #     保持 NULL。它不是 W（視窗是足的）也不是 F（資料取得了，就是 0）——
        #     §5A.1 原本宣稱「只可能是兩種成因之一」，被這一格證偽，
        #     DEC-030 因此補上第三種成因。
        #     填 `1.0` 的語意是「今日成交量等於 5 日均量」，而事實是
        #     「過去 5 日完全沒有成交」——**不是中立值，是與事實相反的值**。
        #
        # 【為何不沿用 compute_push_ratio() 的 Laplace 平滑（分母 +1）】
        # Laplace 的 `+1` 只有在**分母的自然尺度與 1 可比**時才是平滑：
        # 推噓數是 0～數百的小整數，`+1` 是輕微擾動；
        # 而成交量以股／張計，量級 10³–10⁹，對零基準加 1 股不會正則化，
        # 只會讓比值等於**今日原始成交量**——那已經不是一個比值。
        # **同一個技巧不因為本專案用過就適用**，故此處選擇 NULL 而非平滑。
        _ma5_vol = df_features.groupby('stock_id')['volume'].transform(
            lambda s: s.astype(float).shift(1).rolling(window=5).mean()
        )
        _warmup_vol = _ma5_vol.isna()                              # 成因 W
        _vol_ratio = (df_features['volume'].astype(float)
                      / _ma5_vol.replace(0.0, np.nan))             # MA5_Vol == 0：成因 U
        df_features['volume_ratio_5d'] = _vol_ratio.where(~_warmup_vol, 1.0)

        # 利用 groupby + rolling 計算過去 3 天與 5 天的情緒移動平均
        # 嚴格按交易日序列歷史滑動，防止未來資料洩漏
        #
        # 【D5，`PRE-G3-04`】此處**無需改動**（已實測驗證，非推測）：
        # `rolling(window, min_periods=1).mean()` 對 NaN 是 nanmean 語意——
        # `min_periods=1` 計的是窗內非 NaN 觀測值數量，不是原始列數。
        # 上游的 `sentiment_mean` 空日已保持 NaN（不再早期填 0.5），
        # 本段的行為自動變成「窗內有值的日子取平均，全為空則本身為 NaN」。
        #
        # ⚠ 與 F 分支不同：`enforce_source_failed_nulls` 對 `is_failed` 列仍會
        # 在最後把這兩欄強制設回 NaN（即使窗內有其他有效值）；U 分支刻意不做
        # 同等的強制清空——「3 日內至少一天有真實情緒」是誠實可用的訊號，
        # 不是編造（PO 已於 Gate A 確認此不對稱，`PRE_G3_04_D5_GATE_A_PROPOSAL.md` §5.2）。
        df_features['sentiment_3d_ma'] = df_features.groupby('stock_id')['sentiment_mean'] \
                                                    .transform(lambda x: x.rolling(window=3, min_periods=1).mean())
        df_features['sentiment_5d_ma'] = df_features.groupby('stock_id')['sentiment_mean'] \
                                                    .transform(lambda x: x.rolling(window=5, min_periods=1).mean())

        # 情緒滯後特徵 (Lagged Features: T-1, T-2)
        # ⚠ **條件式填補**（UG-G2-SB7 B 輪）：`.fillna(0.5)` 先前是無條件的，
        # **只改上面的 :441 不夠 —— 這兩行會把 NULL 再填回中立值。**
        #
        # 【D5，`PRE-G3-04`】`shift(1)`／`shift(2)` 產生的 NaN **無法從結果本身
        # 分辨兩種成因**：「該股票序列的第一列」（真暖機期，成因 W，前面沒有任何
        # 一天）與「前一天本身是空日」（U 已生效，`sentiment_mean[T-1]` 為 NaN）——
        # 兩者的 `shift` 結果同樣是 NaN。`groupby('stock_id').cumcount()` 是與
        # NaN 成因無關的獨立判準，用它單獨判定「真暖機期」：
        #   - 真暖機期（`cumcount() < N`）→ 填 0.5（W，既有行為維持）
        #   - 非真暖機期但仍是 NaN（即 T-N 那天本身是空日）→ 保持 NaN（U 的傳播）
        # 這保留了資訊：若前一天確實有討論、只是今天沒有，`lag_1` 仍應誠實反映
        # 「昨天有討論、分數是多少」——這件事我們真的知道，填成 NULL 才是錯的方向。
        _lag1 = df_features.groupby('stock_id')['sentiment_mean'].shift(1)
        _lag2 = df_features.groupby('stock_id')['sentiment_mean'].shift(2)
        _cumcount = df_features.groupby('stock_id').cumcount()
        _true_warmup_lag1 = _cumcount < 1
        _true_warmup_lag2 = _cumcount < 2
        df_features['sentiment_lag_1'] = _lag1.where(
            is_failed | ~_true_warmup_lag1, _lag1.fillna(0.5))
        df_features['sentiment_lag_2'] = _lag2.where(
            is_failed | ~_true_warmup_lag2, _lag2.fillna(0.5))

        # 4. 留言衍生特徵（UG-G2-SB4，COMMENT_ENHANCED_19 契約）
        df_features = self._compute_comment_features(df_features)

        # 整理最終要輸出的欄位（LEGACY_17 版本化特徵契約 + source_status metadata 欄
        # + COMMENT_ENHANCED_19 的 3 個留言特徵，
        # 見 doc/upgrade/contracts/FEATURE_REGISTRY.md；UG-G2-SB1 前為裸寫「18 項」，已更正）
        final_cols = [
            'trade_date', 'stock_id', 'close_price', 'volume',
            'return_1d', 'rsi_14', 'volatility_5d', 'volatility_20d',
            # CORE_16 平穩化特徵（UG-G2-SB8，§3.7 模型輸入第 13–16 號）
            'amplitude_ratio', 'ma5_bias_ratio', 'ma20_bias_ratio', 'volume_ratio_5d',
            'article_count', 'sentiment_mean', 'bullishness_index', 'agreement_index',
            'sentiment_3d_ma', 'sentiment_5d_ma', 'sentiment_lag_1', 'sentiment_lag_2',
            'comment_volume_ratio', 'comment_polarization', 'net_push_momentum',
            'source_status'
        ]

        # ⚠⚠ **最後一道**：契約 :321 對 `SOURCE_FAILED` 列的要求，
        # 在所有填補／rolling／shift 之後統一強制一次。
        # **放在這裡而不是各計算點**，是因為每一段都可能把 NULL 補回去。
        df_features = enforce_source_failed_nulls(df_features)
        
        # 保留可能存在的其他 OHLC 價格欄位
        for col in ['open_price', 'high_price', 'low_price']:
            if col in df_features.columns and col not in final_cols:
                final_cols.insert(2, col)

        print("[INFO] [Feature] 特徵表聚合完成！")
        return df_features[final_cols]

    _COMMENT_AGG_COLUMNS = ['trade_date', 'stock_id', 'push_sum', 'boo_sum', 'total_sum']

    def _empty_daily_comments(self) -> pd.DataFrame:
        """無任何留言資料時的空聚合表（欄位齊備，供 left join 不報錯）。"""
        return pd.DataFrame(columns=self._COMMENT_AGG_COLUMNS)

    def _aggregate_direct_comment_counts(
        self, df_arts_direct: pd.DataFrame, cutoff_t, df_comments: pd.DataFrame
    ) -> pd.DataFrame:
        """將逐則留言重算為 per (trade_date, stock_id)——僅直接個股文章。

        【2026-09-14，DEC-039，修訂 DEC-024】改為逐則時間戳重算，取代文章層級
        `comments_scraped_at <= decision_point` 過濾。原因：RISK-023 診斷發現，
        本專案實際排程常數（每日僅 15:35 執行一次；決策點 cutoff 15:30）下，
        文章層級過濾在穩定運作時通過率僅約 0.2%——NULL 比例恆定，不是回填期
        特有的暫時現象。詳見 `doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md`。

        **`df_comments` 為必要參數，不接受省略後靜默退回舊的文章層級過濾**——
        呼叫端必須明確提供 `article_comments` 逐則資料（可為空表，但不可為
        `None`），否則本函式應該讓呼叫失敗，而不是安靜地用一個已知有嚴重缺陷
        的判準頂替。

        **判準**（沿用 DEC-024 的核心哲學，只是把粒度從「整篇文章」改成
        「逐則留言」）：一則留言是否可用，看的是「它是否在被歸屬的那個交易日
        決策時點之前就已存在」，即 `comment_time <= combine(trade_date, cutoff_time)`
        （`comment_timeline.counts_as_of()`）。

        **決策點是 per (article, stock_id) 列，不是 per article**（RISK-027 之後
        `trade_date` 由 `assign_trading_days_per_stock()` 對每一列個別指派，
        同一篇文章對到不同股票可能有不同 `trade_date`／`decision_point`）。

        **已擷取旗標** = `total_comments IS NOT NULL`（來自 `market_articles`）——
        不是「`article_comments` 有沒有列」：真實庫存在「已擷取、觀測到零留言、
        逐則表本來就沒有任何列」的文章（`article_id ∈ {1772, 1872, 2117}`），
        這種情況必須是觀測到的 0，不是 NULL。

        **落界留言排除**（`comment_timeline.validate_comment_bounds()`）：
        `comment_time` 落在 `[post_time, comments_scraped_at]` 之外的留言不計入
        任何一格（真實案例 `article_id=1495` 第 26~38 則，`above_scraped_at`）。

        **`suspect` 守衛**（`comment_timeline.is_time_reset()`，RISK-029）：
        依 `comment_seq` 排序後，若該篇留言時間出現回退（同一批留言被重複解析、
        或兩段留言流被交錯串接），整篇標記 `suspect`，該篇涉及的所有
        `(article, stock_id)` 列留言三欄一律 NULL——不嘗試去重或猜測正確順序
        （`article_comments` 未儲存留言文字，任何去重規則都是猜測）。

        **P6 一致性守衛**（2026-09-14 PO 複核要求）：`total_comments`
        （`market_articles` 凍結快照）與 `df_comments`（呼叫端傳入的逐則資料）
        是兩個獨立來源。若逐則列數**少於** `total_comments`（P6 不變式被違反，
        或呼叫端傳了不完整的 `df_comments`），同樣標記 `suspect` 給 NULL——
        否則逐則重算會算出一個偏低的偽觀測值，而非誠實的「不可信」。
        """
        # UG-G2-SB5 決策點 5：`source` 是必要欄——方向類特徵是否可計算，
        # 取決於該列的來源在結構上提不提供推／噓標記（source_capabilities）。
        # `article_id` 是新增必要欄——供對應 `df_comments` 的逐則留言。
        required = {'article_id', 'trade_date', 'stock_id', 'source', 'total_comments',
                    'post_time', 'comments_scraped_at'}
        if df_arts_direct is None or df_arts_direct.empty or not required.issubset(df_arts_direct.columns):
            return self._empty_daily_comments()
        if df_comments is None:
            raise ValueError(
                "_aggregate_direct_comment_counts() 需要 df_comments（article_comments 逐則資料）"
                "——DEC-039 已取消文章層級過濾，不得省略後靜默退回舊判準。空表請傳入空 DataFrame。"
            )

        df = df_arts_direct.copy()
        df['total_comments'] = pd.to_numeric(df['total_comments'], errors='coerce')
        df['post_time'] = pd.to_datetime(df['post_time'], errors='coerce')
        df['comments_scraped_at'] = pd.to_datetime(df['comments_scraped_at'], errors='coerce')

        # 已擷取旗標——與 df_comments 是否有列無關（見上方 docstring）
        df = df[df['total_comments'].notna()]
        if df.empty:
            return self._empty_daily_comments()

        # 每篇文章的逐則留言，依 comment_seq 遞增排序（is_time_reset 依此順序判斷回退）
        comments_by_article: Dict[object, List[dict]] = {}
        if df_comments is not None and not df_comments.empty:
            sorted_comments = df_comments.sort_values('comment_seq')
            for article_id, group in sorted_comments.groupby('article_id'):
                comments_by_article[article_id] = [
                    {"seq": r.comment_seq, "tag": r.comment_tag, "comment_time": r.comment_time,
                     "raw_time": None}
                    for r in group.itertuples()
                ]

        def _recompute(row) -> pd.Series:
            comments = comments_by_article.get(row['article_id'], [])
            if is_time_reset(comments):
                return pd.Series({'push_count': np.nan, 'boo_count': np.nan, 'total_comments': np.nan})
            # P6 一致性守衛（PO 2026-09-14 複核要求）：`total_comments`（market_articles
            # 凍結快照）與 `df_comments`（呼叫端傳入的逐則資料）是兩個獨立來源。
            # 若逐則列數**少於** `total_comments`，代表 P6 不變式被違反，或呼叫端
            # 傳了不完整的 df_comments——這種情況下逐則重算會算出一個偏低的
            # 「觀測值」甚至 0，那不是真的觀測到的 0，是資料不一致，必須標 suspect。
            if len(comments) < row['total_comments']:
                return pd.Series({'push_count': np.nan, 'boo_count': np.nan, 'total_comments': np.nan})
            bad_seqs = {b['seq'] for b in
                        validate_comment_bounds(comments, row['post_time'], row['comments_scraped_at'])}
            usable = [c for c in comments if c.get('seq') not in bad_seqs]
            decision_point = pd.Timestamp(row['trade_date']) + pd.Timedelta(
                hours=cutoff_t.hour, minutes=cutoff_t.minute, seconds=cutoff_t.second
            )
            counts = counts_as_of(usable, decision_point)
            return pd.Series({'push_count': counts['push_count'], 'boo_count': counts['boo_count'],
                               'total_comments': counts['total_comments']})

        recomputed = df.apply(_recompute, axis=1)
        df[['push_count', 'boo_count', 'total_comments']] = recomputed

        # UG-G2-SB5 決策點 5（DEC-028、FEATURE_REGISTRY.md §5.7）：
        # 方向類計數只採用**結構上提供推／噓標記**的來源。
        #
        # 這裡原本是 `.fillna(0)`——那會把「這個來源沒有方向的概念」
        # 算成「推噓各 0 則」，於是 push_ratio = (0-0)/(0+0+1) = 0，
        # comment_polarization = 1 - 0² = 1.0（「散戶意見最大分歧」）。
        # 一個恆定的偽造強訊號，而且不會報錯。
        has_direction = df['source'].map(provides_comment_direction)
        for col in ['push_count', 'boo_count']:
            df[col] = pd.to_numeric(df[col], errors='coerce').where(has_direction)

        # `min_count=1` 不可省略於任何一欄，`total_comments` 現在也可能因
        # `suspect` 守衛而整組皆為 NaN——pandas 的 sum() 對全 NaN 群組預設回
        # 0.0 而非 NaN，那會讓 suspect 篇的 NULL 被悄悄變回 0。
        return df.groupby(['trade_date', 'stock_id']).agg(
            push_sum=('push_count', lambda s: s.sum(min_count=1)),
            boo_sum=('boo_count', lambda s: s.sum(min_count=1)),
            total_sum=('total_comments', lambda s: s.sum(min_count=1)),
        ).reset_index()

    def _compute_comment_features(self, df_features: pd.DataFrame) -> pd.DataFrame:
        """計算 COMMENT_ENHANCED_19 的三個留言特徵（FEATURE_REGISTRY.md §5.2~§5.4）。

        NULL 語意（§5A.5）：留言未解析／當日無留言資料／暖機期不足時一律保持 NULL，
        **不得**補 0 或中立值——`comment_polarization = 1 - 0² = 1.0` 會是「散戶意見
        最大分歧」這種完全偽造的強訊號。
        """
        df = df_features
        for col in ['push_sum', 'boo_sum', 'total_sum']:
            if col not in df.columns:
                df[col] = np.nan

        # UG-G2-SB5 決策點 5：拆成兩個守衛。
        # 原本單一的 `has_comments` 管三個特徵，但它們對來源的要求並不相同——
        # 數量類只要有留言就能算，方向類還需要該來源提供推／噓標記。
        # 用同一個守衛，等於宣稱「有留言就有方向」，而那是 §1.7 偽造訊號的結構成因。
        has_volume = df['total_sum'].notna()
        has_direction = df['push_sum'].notna()

        # §5.1 push_ratio（共用中間值，非儲存欄位）
        push_ratio = compute_push_ratio(df['push_sum'], df['boo_sum']).where(has_direction)

        # §5.2 comment_volume_ratio = total_t / (rolling_mean(total, t-5..t-1) + 1)
        #      僅使用 t-5..t-1 已知資料（shift(1) 後 rolling），暖機期不足 1 日 → NULL
        prior_mean = df.groupby('stock_id')['total_sum'].transform(
            lambda s: s.shift(1).rolling(window=5, min_periods=1).mean()
        )
        df['comment_volume_ratio'] = (df['total_sum'] / (prior_mean + 1)).where(
            has_volume & prior_mean.notna()
        )

        # §5.3 comment_polarization = 1 - push_ratio²
        df['comment_polarization'] = 1 - push_ratio ** 2

        # §5.4 net_push_momentum = push_ratio_t - push_ratio_{t-1}
        #      前一日無推噓資料時為 NULL（差分的兩端都必須存在）
        prev_push_ratio = push_ratio.groupby(df['stock_id']).shift(1)
        df['net_push_momentum'] = push_ratio - prev_push_ratio

        return df.drop(columns=['push_sum', 'boo_sum', 'total_sum'])

    def generate_target_labels(self, df_features: pd.DataFrame, label_horizon: int = 1) -> pd.DataFrame:
        """
        為時間序列特徵表生成監督式機器學習預測目標 (Target Labels)。
        嚴格遵循防前視偏誤 (Zero Look-ahead Bias) 約定：
        - 預測目標以 T+1 交易日收盤表現為基準 (與 label_horizon 參數無關，恆為 T+1)。
        - 每檔股票的最後一個交易日目標為 NaN (因為未來資料尚未發生)。

        Args:
            df_features: 包含基本價量特徵的 DataFrame (含 trade_date, stock_id, close_price)
            label_horizon: 標籤依賴的未來交易日數 (預設 1，對應 target_up_down 的 T+1 依賴)。
                用於計算 label_end_date = trade_date[T + label_horizon]，供
                Purged Walk-Forward (`WalkForwardSplitter`) 的 Purge 邊界判定使用；
                不影響 target_next_close / target_return_1d / target_up_down 本身。

        Returns:
            pd.DataFrame: 附加 target_next_close, target_return_1d, target_up_down, label_end_date 的特徵矩陣
        """
        if df_features is None or df_features.empty:
            return df_features
        if label_horizon < 1:
            raise ValueError(f"label_horizon 必須大於等於 1，收到: {label_horizon}")

        df_res = df_features.copy()
        df_res = df_res.sort_values(by=['stock_id', 'trade_date']).reset_index(drop=True)

        # 1. 計算次一交易日收盤價 (T+1 Close)
        df_res['target_next_close'] = df_res.groupby('stock_id')['close_price'].shift(-1)

        # 2. 計算次一交易日對數報酬率 (r_{T+1} = ln(Close_{T+1} / Close_T))
        df_res['target_return_1d'] = np.log(
            df_res['target_next_close'].astype(float) / df_res['close_price'].astype(float)
        )

        # 3. 生成二元漲跌標籤 (1: 上漲, 0: 下跌或平盤，無未來資料之最後一天為 NaN)
        df_res['target_up_down'] = df_res['target_return_1d'].apply(
            lambda r: 1 if r > 0 else (0 if pd.notna(r) else np.nan)
        )

        # 4. label_end_date = trade_date[T + label_horizon]（依個股自身交易日序列，非全域對齊）。
        #    供 WalkForwardSplitter 的 Purge 判定使用；每檔股票尾端 label_horizon 天為 NaT
        #    (超出該股票已知資料範圍，未來尚未發生，見 PURGED_WALK_FORWARD_SPEC.md §2.1)。
        df_res['label_end_date'] = df_res.groupby('stock_id')['trade_date'].shift(-label_horizon)

        return df_res