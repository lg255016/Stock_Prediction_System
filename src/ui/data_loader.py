import json
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2

from ..ml.model_trainer import MultiModalTrainer, ALL_MULTIMODAL_FEATURE_COLS
from ..ml.predictor import StockTrendPredictor
from src.common.clock import now_taipei

logger = logging.getLogger(__name__)

# 預設可用股票清單
DEFAULT_STOCKS: Dict[str, str] = {
    "2330": "台積電 (2330.TW)",
    "2382": "廣達 (2382.TW)",
    "6488": "環球晶 (6488.TWO)",
    "NVDA": "NVIDIA (NVDA)",
}


class DataMode(Enum):
    """
    UI 資料來源狀態（UG-G1-SB2, DEC-012）。

    REAL  ：DB 連線成功且回傳非空資料。
    DEMO  ：展示用模擬資料。僅在呼叫端明確傳入 demo=True 時使用，不作為 ERROR 的自動 fallback
            （PO 2026-08-25 方案 B 決策：這是求職作品集，不以假資料撐場面）。
    EMPTY ：DB 連線成功，查詢結果為零筆——真實的「沒有」，非模擬。
    ERROR ：DB 連線或查詢本身失敗。對應區塊不渲染任何數值，只顯示錯誤說明。
    """
    REAL = "real"
    DEMO = "demo"
    EMPTY = "empty"
    ERROR = "error"


class DataSourceError(Exception):
    """DB 連線或查詢層級失敗，供內部函式向上拋出、由公開函式轉換為 DataMode.ERROR。"""


# 特徵矩陣欄位契約（ERROR／EMPTY 時回傳同結構的空 DataFrame，供呼叫端安全檢查 .columns）
_STOCK_FEATURE_COLUMNS: List[str] = [
    "trade_date", "stock_id", "open_price", "high_price", "low_price", "close_price", "volume",
    "return_1d", "rsi_14", "volatility_5d", "volatility_20d", "article_count", "sentiment_mean",
    "bullishness_index", "agreement_index", "sentiment_3d_ma", "sentiment_5d_ma",
    "sentiment_lag_1", "sentiment_lag_2", "target_return_1d", "target_up_down",
]

_STOCK_ARTICLE_COLUMNS: List[str] = [
    "publish_time", "stock_id", "title", "sentiment_score",
    "sentiment_label", "push_count", "source", "url",
]

# 模型競技排行榜 artifact（UG-G1-SB3, DRIFT-008／DRIFT-018）：
# 由 scripts/generate_tournament_artifact.py 一次性產出，UI 僅讀取，不在頁面渲染時即時計算。
_TOURNAMENT_ARTIFACT_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models", "artifacts", "tournament_results.json"
)
_TOURNAMENT_REQUIRED_KEYS = {"leaderboard", "alpha_attribution", "champion_model_name", "champion_score"}
_TOURNAMENT_LEADERBOARD_ROW_KEYS = {
    "experiment_id", "model_name", "feature_set", "macro_f1", "accuracy", "roc_auc",
    "directional_hit_ratio", "cumulative_return", "sharpe_ratio", "max_drawdown",
}

# DEMO 專用內容（僅在 demo=True 時使用，不再作為 ERROR 的自動 fallback）
DEFAULT_AI_KEYWORDS: List[str] = [
    "矽光子 (CPO)",
    "散熱模組",
    "CoWoS 先進封裝",
    "GB200 伺服器",
    "人形機器人",
    "ASIC 客製晶片",
]

DEFAULT_THEMATIC_RADAR: List[Dict[str, Any]] = [
    {
        "theme": "矽光子 (CPO)",
        "raw_theme": "矽光子",
        "icon": "💡",
        "article_count": 48,
        "bullishness": 1.82,
        "sentiment_label": "極度看好",
        "stocks": [
            {"stock_id": "3081", "name": "聯亞", "display": "3081 聯亞"},
            {"stock_id": "6442", "name": "光聖", "display": "6442 光聖"},
            {"stock_id": "2330", "name": "台積電", "display": "2330 台積電"},
        ]
    },
    {
        "theme": "散熱模組 (Thermal)",
        "raw_theme": "散熱模組",
        "icon": "❄️",
        "article_count": 32,
        "bullishness": 1.15,
        "sentiment_label": "偏多",
        "stocks": [
            {"stock_id": "3324", "name": "雙鴻", "display": "3324 雙鴻"},
            {"stock_id": "3017", "name": "奇鋐", "display": "3017 奇鋐"},
            {"stock_id": "3653", "name": "健策", "display": "3653 健策"},
        ]
    },
    {
        "theme": "CoWoS 先進封裝",
        "raw_theme": "CoWoS",
        "icon": "📦",
        "article_count": 26,
        "bullishness": 0.94,
        "sentiment_label": "穩定看好",
        "stocks": [
            {"stock_id": "3131", "name": "弘塑", "display": "3131 弘塑"},
            {"stock_id": "3583", "name": "辛耘", "display": "3583 辛耘"},
            {"stock_id": "2330", "name": "台積電", "display": "2330 台積電"},
        ]
    },
    {
        "theme": "AI 伺服器 (OEM)",
        "raw_theme": "AI伺服器",
        "icon": "🤖",
        "article_count": 55,
        "bullishness": 1.45,
        "sentiment_label": "強烈偏多",
        "stocks": [
            {"stock_id": "2382", "name": "廣達", "display": "2382 廣達"},
            {"stock_id": "6669", "name": "緯穎", "display": "6669 緯穎"},
            {"stock_id": "NVDA", "name": "輝達", "display": "NVDA 輝達"},
        ]
    }
]


def get_available_stocks(custom_stocks: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """取得系統支援之股票代碼與名稱對照表 (支援使用者動態新增之自選股)"""
    stocks = dict(DEFAULT_STOCKS)
    if custom_stocks:
        stocks.update(custom_stocks)
    return stocks


def generate_mock_stock_features(stock_id: str, days: int = 60) -> pd.DataFrame:
    """
    生成高仿真之 18 欄位離線特徵 DataFrame。僅供 load_stock_features(demo=True) 使用。
    """
    np.random.seed(int(sum(ord(c) for c in str(stock_id))))
    # demo 資料也走時區政策 —— **一個絕對的規則不需要維護豁免清單**。
    end_date = pd.Timestamp(now_taipei())
    dates = pd.date_range(end=end_date, periods=days, freq="B").strftime("%Y-%m-%d")

    # 基礎價格走勢模擬
    base_price = 1000.0 if stock_id == "2330" else (300.0 if stock_id == "2382" else 120.0)
    returns = np.random.normal(0.001, 0.018, size=days)
    close_prices = base_price * np.exp(np.cumsum(returns))
    open_prices = close_prices * (1.0 + np.random.normal(0, 0.005, size=days))
    high_prices = np.maximum(open_prices, close_prices) * (1.0 + np.abs(np.random.normal(0, 0.008, size=days)))
    low_prices = np.minimum(open_prices, close_prices) * (1.0 - np.abs(np.random.normal(0, 0.008, size=days)))
    volumes = np.random.randint(10000, 50000, size=days) * 1000

    # 技術指標模擬
    return_1d = np.concatenate([[0.0], np.diff(close_prices) / close_prices[:-1]])
    rsi_14 = np.clip(50.0 + np.cumsum(np.random.normal(0, 3.0, size=days)), 20.0, 80.0)
    volatility_5d = np.clip(np.abs(np.random.normal(0.20, 0.05, size=days)), 0.05, 0.60)
    volatility_20d = np.clip(np.abs(np.random.normal(0.22, 0.04, size=days)), 0.05, 0.55)

    # 輿情與機構特徵模擬
    article_counts = np.random.randint(2, 25, size=days)
    sentiment_mean = np.clip(0.52 + 0.3 * return_1d + np.random.normal(0, 0.08, size=days), 0.1, 0.9)
    # Antweiler 看多指數 Bt 與一致性指數 At
    bullishness = np.clip((sentiment_mean - 0.5) * 3.0 + np.random.normal(0, 0.2, size=days), -2.0, 3.0)
    agreement = np.clip(0.70 + np.abs(sentiment_mean - 0.5) * 0.5 + np.random.normal(0, 0.05, size=days), 0.0, 1.0)

    # 時序滯後與均線
    s_series = pd.Series(sentiment_mean)
    sentiment_3d_ma = s_series.rolling(3, min_periods=1).mean().to_numpy()
    sentiment_5d_ma = s_series.rolling(5, min_periods=1).mean().to_numpy()
    sentiment_lag_1 = s_series.shift(1).fillna(0.5).to_numpy()
    sentiment_lag_2 = s_series.shift(2).fillna(0.5).to_numpy()

    # 目標標籤
    target_return = np.roll(return_1d, -1)
    target_return[-1] = np.nan
    target_up_down = np.where(target_return > 0, 1.0, 0.0)
    target_up_down[-1] = np.nan

    df = pd.DataFrame({
        "trade_date": dates,
        "stock_id": [stock_id] * days,
        "open_price": np.round(open_prices, 2),
        "high_price": np.round(high_prices, 2),
        "low_price": np.round(low_prices, 2),
        "close_price": np.round(close_prices, 2),
        "volume": volumes,
        "return_1d": np.round(return_1d, 4),
        "rsi_14": np.round(rsi_14, 2),
        "volatility_5d": np.round(volatility_5d, 4),
        "volatility_20d": np.round(volatility_20d, 4),
        "article_count": article_counts,
        "sentiment_mean": np.round(sentiment_mean, 4),
        "bullishness_index": np.round(bullishness, 4),
        "agreement_index": np.round(agreement, 4),
        "sentiment_3d_ma": np.round(sentiment_3d_ma, 4),
        "sentiment_5d_ma": np.round(sentiment_5d_ma, 4),
        "sentiment_lag_1": np.round(sentiment_lag_1, 4),
        "sentiment_lag_2": np.round(sentiment_lag_2, 4),
        "target_return_1d": target_return,
        "target_up_down": target_up_down,
    })
    return df


def generate_mock_ptt_articles(stock_id: str, limit: int = 20) -> pd.DataFrame:
    """
    生成高仿真之 PTT 原始文章資料庫。僅供 load_stock_articles(demo=True) 使用。
    """
    stock_name = DEFAULT_STOCKS.get(stock_id, stock_id).split()[0]
    sample_titles = [
        f"[標的] {stock_id} {stock_name} 業績噴發 多",
        f"[新聞] {stock_name} Q3 財報展望超越預期，外資調升目標價",
        f"[請益] {stock_name} 現在進場追高會太慢嗎？",
        f"[心得] {stock_name} 抱緊就對了，AI 伺服器動能強勁",
        f"[標的] {stock_id} 短線融資過高 注意回檔風險",
        f"[新聞] 法人單日大買 {stock_name} 逾萬張",
        f"[討論] 今日 {stock_name} 盤中大單對敲解讀",
        f"[心得] 感謝 {stock_name} 賜我吃飽，獲利了結一趟",
    ]

    dates = pd.date_range(end=pd.Timestamp(now_taipei()), periods=limit, freq="6h").strftime("%Y-%m-%d %H:%M")
    records = []
    np.random.seed(42)
    for i, dt in enumerate(dates):
        title = sample_titles[i % len(sample_titles)]
        score = round(float(np.clip(np.random.normal(0.65, 0.2), 0.1, 0.95)), 3)
        push_count = int(np.random.randint(5, 120))
        label = "看多" if score >= 0.6 else ("看空" if score <= 0.4 else "中立")
        records.append({
            "publish_time": dt,
            "stock_id": stock_id,
            "title": title,
            "sentiment_score": score,
            "sentiment_label": label,
            "push_count": push_count,
            "source": "PTT Stock"
        })
    return pd.DataFrame(records)


def _stringify_date_columns(df_features: pd.DataFrame) -> pd.DataFrame:
    """
    將 trade_date 與 label_end_date（若存在）統一轉為 YYYY-MM-DD 字串。

    兩欄位必須維持**同一型別**——`label_end_date` 由
    `FeatureAggregator.generate_target_labels()` 以 `groupby('stock_id')['trade_date'].shift(...)`
    產生，若只轉換 `trade_date` 而漏轉 `label_end_date`，兩者會分別是 str 與 pandas.Timestamp。
    這個型別不一致本身不會立即出錯——它會潛伏到 `WalkForwardSplitter.split()` 逐列比較
    `label_end_date >= test_start_date` 時才以 TypeError 現形。此函式存在的理由就是確保
    這兩欄位在同一個地方被同時轉換，不會再各自轉、各自忘。

    NaT（`label_end_date` 在每檔股票最後 `label_horizon` 列必然出現）會被
    `.dt.strftime()` 轉為 None，與 `WalkForwardSplitter` 對 `pd.isna(v)` 的既有防呆一致。
    """
    df_features = df_features.copy()
    df_features['trade_date'] = pd.to_datetime(df_features['trade_date']).dt.strftime('%Y-%m-%d')
    if 'label_end_date' in df_features.columns:
        df_features['label_end_date'] = pd.to_datetime(df_features['label_end_date']).dt.strftime('%Y-%m-%d')
    return df_features


def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optional[pd.DataFrame]:
    """
    從 PostgreSQL 撈取真實股價與文章資料，並透過 FeatureAggregator 即時推導完整 18 欄位特徵矩陣。

    Returns:
        None：DB 連線與查詢皆成功，但沒有可用資料（歷史不足 2 筆、彙總後為空）。
    Raises:
        DataSourceError：DB 連線或查詢本身失敗。
    """
    try:
        from ..loaders.db_writer import DBWriter
        from ..transform.feature_aggregator import FeatureAggregator
        
        writer = DBWriter()
        conn = psycopg2.connect(**writer.db_config)
        
        # 1. 撈取真實歷史股價 (按日期遞增排序)
        price_query = """
            SELECT trade_date, stock_id, open_price, high_price, low_price, close_price, volume
            FROM stock_prices
            WHERE stock_id = %s
            ORDER BY trade_date ASC;
        """
        df_prices = pd.read_sql(price_query, conn, params=(stock_id,))
        
        if df_prices.empty or len(df_prices) < 2:
            conn.close()
            return None
            
        # 2. 撈取該股票關聯之關鍵字
        mapping_query = """
            SELECT keyword, stock_id
            FROM entity_mapping
            WHERE stock_id = %s;
        """
        df_mapping = pd.read_sql(mapping_query, conn, params=(stock_id,))
        if df_mapping.empty:
            df_mapping = pd.DataFrame({"keyword": [stock_id], "stock_id": [stock_id]})
        keywords = df_mapping['keyword'].tolist()
            
        # 3. 撈取所屬題材映射
        theme_query = """
            SELECT theme_keyword, stock_id, relevance_weight
            FROM theme_stock_mapping
            WHERE stock_id = %s;
        """
        df_theme_mapping = pd.read_sql(theme_query, conn, params=(stock_id,))
        theme_keywords = df_theme_mapping['theme_keyword'].tolist() if not df_theme_mapping.empty else []

        # 4. 撈取關聯文章輿情 (包含個股關鍵字與所屬題材關鍵字)
        all_keywords = list(set(keywords + theme_keywords))
        articles_query = """
            SELECT article_id, source, fetch_keyword, post_time, title, url, author, engagement_metric, sentiment_score
            FROM market_articles
            WHERE fetch_keyword IN %s
            ORDER BY post_time ASC;
        """
        if all_keywords:
            df_articles = pd.read_sql(articles_query, conn, params=(tuple(all_keywords),))
        else:
            df_articles = pd.DataFrame()
            
        conn.close()
        
        # 5. 透過 FeatureAggregator 向量化運算生成 18 欄位完整特徵 (支援題材情緒溢出加權)
        aggregator = FeatureAggregator()
        # DEC-039：df_comments 為必要參數。本路徑的 articles_query 從未 SELECT
        # 留言相關欄位（push_count 等），留言特徵在此路徑本來就一直是 NULL
        # （舊版 _aggregate_direct_comment_counts() 的 required 欄位檢查會提早
        # 失敗返回空表）——傳入空 DataFrame 維持這個既有行為不變，不是新的限制。
        df_features = aggregator.generate_daily_features(
            df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame(),
        )
        if df_features.empty:
            return None
            
        # 5. 生成目標標籤 target_return_1d / target_up_down
        df_features = aggregator.generate_target_labels(df_features)
        
        df_features = _stringify_date_columns(df_features)
        
        # 僅保留最近 days 天
        if len(df_features) > days:
            df_features = df_features.iloc[-days:].reset_index(drop=True)
            
        return df_features
    except DataSourceError:
        raise
    except Exception as e:
        logger.warning(f"PostgreSQL 特徵讀取異常: {e}")
        raise DataSourceError(str(e)) from e


def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Optional[pd.DataFrame]:
    """
    從 PostgreSQL 撈取真實 PTT 輿情文章明細。
    採用三重階梯式查詢：
    1. Entity Mapping 個股關鍵字 (如 2330 ➔ 台積電)
    2. Thematic Mapping 所屬題材關鍵字 (如 3081 ➔ 矽光子, 3324 ➔ 散熱模組)
    3. 標題全域模糊比對 (title ILIKE %stock_id% OR title ILIKE %stock_name%)

    Returns:
        符合欄位契約的 DataFrame（可能為空，代表 DB 成功但無相關文章）。
    Raises:
        DataSourceError：DB 連線或查詢本身失敗。
    """
    try:
        from ..loaders.db_writer import DBWriter
        writer = DBWriter()
        conn = psycopg2.connect(**writer.db_config)
        
        # 1. 撈取個股關鍵字
        mapping_query = "SELECT keyword FROM entity_mapping WHERE stock_id = %s;"
        with conn.cursor() as cur:
            cur.execute(mapping_query, (stock_id,))
            keywords = [r[0] for r in cur.fetchall()]

        # 2. 撈取題材關鍵字與股票名稱
        theme_query = "SELECT theme_keyword, stock_name FROM theme_stock_mapping WHERE stock_id = %s;"
        theme_keywords = []
        stock_names = []
        with conn.cursor() as cur:
            cur.execute(theme_query, (stock_id,))
            for r in cur.fetchall():
                if r[0]:
                    theme_keywords.append(r[0])
                if r[1]:
                    stock_names.append(r[1])
            
        all_keywords = list(set(keywords + theme_keywords + [stock_id]))
        stock_name_pattern = f"%{stock_names[0]}%" if stock_names else f"%{stock_id}%"
        stock_id_pattern = f"%{stock_id}%"

        articles_query = """
            SELECT 
                TO_CHAR(post_time, 'YYYY-MM-DD HH24:MI') AS publish_time,
                %s AS stock_id,
                title,
                ROUND(COALESCE(sentiment_score, 0.5)::numeric, 3) AS sentiment_score,
                CASE 
                    WHEN sentiment_score >= 0.6 THEN '看多'
                    WHEN sentiment_score <= 0.4 THEN '看空'
                    ELSE '中立'
                END AS sentiment_label,
                engagement_metric AS push_count,
                source,
                url
            FROM market_articles
            WHERE fetch_keyword IN %s
               OR title ILIKE %s
               OR title ILIKE %s
            ORDER BY post_time DESC
            LIMIT %s;
        """
        df_arts = pd.read_sql(
            articles_query, 
            conn, 
            params=(stock_id, tuple(all_keywords), stock_id_pattern, stock_name_pattern, limit)
        )
        conn.close()
        
        if df_arts.empty:
            return pd.DataFrame(columns=_STOCK_ARTICLE_COLUMNS)
        # 去重
        df_arts = df_arts.drop_duplicates(subset=['title', 'publish_time']).reset_index(drop=True)
        return df_arts
    except DataSourceError:
        raise
    except Exception as e:
        logger.warning(f"PostgreSQL 文章讀取異常: {e}")
        raise DataSourceError(str(e)) from e


def load_stock_features(stock_id: str, days: int = 60, demo: bool = False) -> Tuple[pd.DataFrame, DataMode]:
    """
    載入指定股票之特徵矩陣。

    Args:
        demo: True 時直接回傳離線模擬資料（DataMode.DEMO），不嘗試連線 DB。
            預設 False：DB 連線失敗回傳空特徵矩陣與 DataMode.ERROR（不自動退回模擬資料，
            DEC-012 方案 B）；DB 連線成功但無資料回傳 DataMode.EMPTY；成功且有資料回傳 DataMode.REAL。

    Returns:
        (DataFrame, DataMode) 元組。ERROR／EMPTY 時 DataFrame 為符合欄位契約的空表。
    """
    if demo:
        return generate_mock_stock_features(stock_id, days=days), DataMode.DEMO

    try:
        df_real = _fetch_real_stock_features_from_db(stock_id, days=days)
    except DataSourceError as e:
        logger.warning(f"[DataMode.ERROR] load_stock_features({stock_id}): {e}")
        return pd.DataFrame(columns=_STOCK_FEATURE_COLUMNS), DataMode.ERROR

    if df_real is None or df_real.empty:
        return pd.DataFrame(columns=_STOCK_FEATURE_COLUMNS), DataMode.EMPTY
    return df_real, DataMode.REAL


def load_stock_articles(stock_id: str, limit: int = 20, demo: bool = False) -> Tuple[pd.DataFrame, DataMode]:
    """
    載入指定股票之真實 PTT 文章明細。

    Args:
        demo: True 時直接回傳離線模擬文章（DataMode.DEMO）。
            預設 False：DB 連線失敗回傳空表與 DataMode.ERROR；查無資料回傳 DataMode.EMPTY；
            成功且有資料回傳 DataMode.REAL。
    """
    if demo:
        return generate_mock_ptt_articles(stock_id, limit=limit), DataMode.DEMO

    try:
        df_real = _fetch_real_stock_articles_from_db(stock_id, limit=limit)
    except DataSourceError as e:
        logger.warning(f"[DataMode.ERROR] load_stock_articles({stock_id}): {e}")
        return pd.DataFrame(columns=_STOCK_ARTICLE_COLUMNS), DataMode.ERROR

    if df_real is None or df_real.empty:
        return pd.DataFrame(columns=_STOCK_ARTICLE_COLUMNS), DataMode.EMPTY
    return df_real, DataMode.REAL


def get_champion_predictor(df_features: pd.DataFrame) -> StockTrendPredictor:
    """
    以當前特徵矩陣快速擬合冠軍隨機森林模型，並回傳即時推論引擎。
    呼叫端須確保 df_features 來自 DataMode.REAL 或 DataMode.DEMO（非空、具備完整欄位）。
    """
    trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust", random_state=42)
    trainer.train_and_predict_fold(df_features, df_features)
    return StockTrendPredictor(trainer=trainer)


def load_ai_discovered_keywords(limit: int = 6, demo: bool = False) -> Tuple[List[str], DataMode]:
    """
    載入由 AI (trend_discover.py) 探索之最新市場熱門關鍵字。

    Args:
        demo: True 時直接回傳精選展示詞（DataMode.DEMO）。
            預設 False：DB 連線失敗回傳空清單與 DataMode.ERROR；查無資料回傳 DataMode.EMPTY；
            成功且有資料回傳 DataMode.REAL。
    """
    if demo:
        return list(DEFAULT_AI_KEYWORDS), DataMode.DEMO

    try:
        from ..loaders.db_writer import DBWriter
        writer = DBWriter()
        keywords = writer.fetch_ai_discovered_keywords(limit=limit)
    except Exception as e:
        logger.warning(f"[DataMode.ERROR] load_ai_discovered_keywords: {e}")
        return [], DataMode.ERROR

    if not keywords:
        return [], DataMode.EMPTY
    return keywords, DataMode.REAL


def load_thematic_radar_data(demo: bool = False) -> Tuple[List[Dict[str, Any]], DataMode]:
    """
    載入題材熱搜雷達數據 (包含題材名稱、討論聲量、看多指數、情緒評級與成分股清單)。

    Args:
        demo: True 時直接回傳精選展示題材（DataMode.DEMO）。
            預設 False：DB 連線失敗回傳空清單與 DataMode.ERROR；查無資料回傳 DataMode.EMPTY；
            成功且有資料回傳 DataMode.REAL。
    """
    if demo:
        return list(DEFAULT_THEMATIC_RADAR), DataMode.DEMO

    try:
        from ..loaders.db_writer import DBWriter
        from ..transform.feature_aggregator import compute_bullishness_index

        writer = DBWriter()
        conn = psycopg2.connect(**writer.db_config)
        
        # 1. 撈取所有題材成分股
        mapping_query = """
            SELECT theme_keyword, stock_id, stock_name, relevance_weight
            FROM theme_stock_mapping
            ORDER BY theme_keyword, relevance_weight DESC;
        """
        df_mappings = pd.read_sql(mapping_query, conn)
        if df_mappings.empty:
            conn.close()
            return [], DataMode.EMPTY

        # 2. 撈取題材文章統計
        theme_names = tuple(df_mappings['theme_keyword'].unique())
        arts_query = """
            SELECT fetch_keyword,
                   COUNT(*) AS article_count,
                   SUM(CASE WHEN sentiment_score >= 0.55 THEN 1 ELSE 0 END) AS pos_cnt,
                   SUM(CASE WHEN sentiment_score <= 0.45 THEN 1 ELSE 0 END) AS neg_cnt
            FROM market_articles
            WHERE fetch_keyword IN %s
            GROUP BY fetch_keyword;
        """
        df_stats = pd.read_sql(arts_query, conn, params=(theme_names,))
        conn.close()
    except Exception as e:
        logger.warning(f"[DataMode.ERROR] load_thematic_radar_data: {e}")
        return [], DataMode.ERROR

    stats_dict = {}
    if not df_stats.empty:
        for _, r in df_stats.iterrows():
            stats_dict[r['fetch_keyword']] = {
                'count': int(r['article_count']),
                'pos': int(r['pos_cnt']),
                'neg': int(r['neg_cnt'])
            }

    radar_list = []
    theme_icons = {
        "矽光子": "💡",
        "散熱模組": "❄️",
        "CoWoS": "📦",
        "AI伺服器": "🤖"
    }

    for theme, group in df_mappings.groupby('theme_keyword'):
        s_info = stats_dict.get(theme, {'count': 0, 'pos': 0, 'neg': 0})
        cnt = s_info['count']
        if cnt > 0:
            b_val = float(compute_bullishness_index(pd.Series([s_info['pos']]), pd.Series([s_info['neg']])).iloc[0])
        else:
            b_val = 0.85

        if b_val >= 1.0:
            lbl = "極度看好"
        elif b_val >= 0.3:
            lbl = "偏多"
        elif b_val <= -0.5:
            lbl = "偏空"
        else:
            lbl = "穩定"

        stocks_list = []
        for _, row in group.iterrows():
            s_id = str(row['stock_id'])
            s_name = str(row['stock_name']) if pd.notnull(row['stock_name']) else s_id
            stocks_list.append({
                "stock_id": s_id,
                "name": s_name,
                "display": f"{s_id} {s_name}"
            })

        radar_list.append({
            "theme": f"{theme}",
            "raw_theme": theme,
            "icon": theme_icons.get(theme, "🔥"),
            "article_count": cnt if cnt > 0 else len(group) * 8,
            "bullishness": b_val,
            "sentiment_label": lbl,
            "stocks": stocks_list[:3]  # 每題材展示前 3 檔核心
        })

    if not radar_list:
        return [], DataMode.EMPTY
    return radar_list, DataMode.REAL


def load_tournament_results(artifact_path: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], DataMode]:
    """
    載入 8 組平行對照實驗（4 演算法 × 2 特徵集）模型競技排行榜結果
    （UG-G1-SB3；DRIFT-008 靜態排行榜改動態、DRIFT-018 三項矛盾修正）。

    資料來源為 `MLEvaluator.evaluate_tournament()` 產出並持久化的 JSON artifact
    （見 `scripts/generate_tournament_artifact.py`），UI 僅讀取，不在頁面渲染時即時重跑訓練。

    Args:
        artifact_path: artifact 檔案路徑，預設 `models/artifacts/tournament_results.json`。

    Returns:
        (None, DataMode.EMPTY)：artifact 不存在（尚未執行過模型競技）。
        (None, DataMode.ERROR)：artifact 存在但格式錯誤／必要欄位缺失。
        (dict, DataMode.REAL)：成功載入，dict 含 leaderboard／alpha_attribution／
            champion_model_name／champion_score。
    """
    path = artifact_path or _TOURNAMENT_ARTIFACT_PATH

    if not os.path.exists(path):
        return None, DataMode.EMPTY

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"[DataMode.ERROR] load_tournament_results: 無法讀取或解析 {path}: {e}")
        return None, DataMode.ERROR

    if not isinstance(payload, dict) or not _TOURNAMENT_REQUIRED_KEYS.issubset(payload.keys()):
        logger.warning(f"[DataMode.ERROR] load_tournament_results: {path} 缺少必要欄位 {_TOURNAMENT_REQUIRED_KEYS}")
        return None, DataMode.ERROR

    leaderboard = payload.get("leaderboard")
    if not isinstance(leaderboard, list) or not leaderboard:
        logger.warning(f"[DataMode.ERROR] load_tournament_results: {path} 的 leaderboard 為空或格式錯誤")
        return None, DataMode.ERROR

    for row in leaderboard:
        if not isinstance(row, dict) or not _TOURNAMENT_LEADERBOARD_ROW_KEYS.issubset(row.keys()):
            logger.warning(f"[DataMode.ERROR] load_tournament_results: {path} 的 leaderboard 列缺少必要欄位")
            return None, DataMode.ERROR

    return payload, DataMode.REAL
