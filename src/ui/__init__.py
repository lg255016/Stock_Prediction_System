"""
金融情緒與股價趨勢預測系統 - Phase 4 Streamlit BI 視覺化與互動模組
"""

from .styles import (
    DARK_THEME_CSS,
    get_market_colors,
    render_kpi_card_html,
    COLOR_TAIWAN_UP,
    COLOR_TAIWAN_DOWN,
)
from .data_loader import (
    load_stock_features,
    load_stock_articles,
    get_available_stocks,
    get_champion_predictor,
    load_ai_discovered_keywords,
)
from .charts import (
    render_price_sentiment_candlestick_chart,
    render_pnl_equity_curve_chart,
    render_feature_importance_bar_chart,
)
from .components import (
    render_prediction_panel,
    render_tournament_leaderboard,
    render_raw_article_table,
    render_ai_trend_discovery_badge,
    FEATURE_DISPLAY_NAMES,
)

__all__ = [
    "DARK_THEME_CSS",
    "get_market_colors",
    "render_kpi_card_html",
    "COLOR_TAIWAN_UP",
    "COLOR_TAIWAN_DOWN",
    "load_stock_features",
    "load_stock_articles",
    "get_available_stocks",
    "get_champion_predictor",
    "load_ai_discovered_keywords",
    "render_price_sentiment_candlestick_chart",
    "render_pnl_equity_curve_chart",
    "render_feature_importance_bar_chart",
    "render_prediction_panel",
    "render_tournament_leaderboard",
    "render_raw_article_table",
    "render_ai_trend_discovery_badge",
    "FEATURE_DISPLAY_NAMES",
]
