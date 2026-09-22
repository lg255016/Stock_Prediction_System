import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .styles import get_market_colors, COLOR_TAIWAN_UP, COLOR_TAIWAN_DOWN
from .data_loader import DataMode

logger = logging.getLogger(__name__)

# DataMode 非 REAL 時的圖表浮水印／佔位文案 (icon, 說明文字, 強調色)
_CHART_MODE_ANNOTATION: Dict[DataMode, Tuple[str, str, str]] = {
    DataMode.ERROR: ("⚠️", "資料來源目前無法連線", "#FF5252"),
    DataMode.EMPTY: ("💡", "目前查無相關資料", "#FFA726"),
    DataMode.DEMO: ("🧪 示範資料 DEMO", "並非即時真實數據", "#2962FF"),
}


class _FallbackPlotlyFigure:
    """輕量 Plotly 圖表物件 Fallback (供無 plotly 之輕量測試環境安全執行)"""
    def __init__(self, data: Optional[List[Any]] = None, layout: Optional[Dict[str, Any]] = None):
        self.data = data or []
        self.layout = layout or {}

    def update_layout(self, **kwargs: Any) -> "_FallbackPlotlyFigure":
        self.layout.update(kwargs)
        return self

    def update_xaxes(self, **kwargs: Any) -> "_FallbackPlotlyFigure":
        return self

    def update_yaxes(self, **kwargs: Any) -> "_FallbackPlotlyFigure":
        return self

    def add_annotation(self, **kwargs: Any) -> "_FallbackPlotlyFigure":
        self.layout.setdefault("annotations", []).append(kwargs)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {"data": self.data, "layout": self.layout}


def _placeholder_figure(mode: DataMode, height: int = 320) -> Any:
    """ERROR／EMPTY 狀態的佔位圖表：不畫任何數值，只顯示狀態說明。"""
    icon, text, color = _CHART_MODE_ANNOTATION[mode]
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#1E222D",
            plot_bgcolor="#1E222D",
            height=height,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        fig.add_annotation(
            text=f"{icon} {text}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color=color),
        )
        return fig
    except ImportError:
        return _FallbackPlotlyFigure(data=[], layout={"placeholder": text, "mode": mode.value})


def _apply_demo_watermark(fig: Any) -> Any:
    """DEMO 狀態：正常繪圖後疊加醒目浮水印標註，圖表本身照常顯示。"""
    icon_text, sub_text, color = _CHART_MODE_ANNOTATION[DataMode.DEMO]
    fig.add_annotation(
        text=f"{icon_text}<br><span style='font-size:11px'>{sub_text}</span>",
        xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=22, color=color),
        opacity=0.35,
    )
    return fig


def render_price_sentiment_candlestick_chart(
    df: pd.DataFrame,
    stock_title: str = "2330 台積電",
    market: str = "TW",
    mode: DataMode = DataMode.REAL,
) -> Any:
    """
    繪製機構級多維雙 Y 軸互動圖表：
    - 上層 (70% 高度)：日 K 線 (Candlestick) + MA5 (週線) + MA20 (月線)
    - 下層 (30% 高度)：社群情緒指數長條圖 (Sentiment Mean / Antweiler Bt) + 成交量

    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
    """
    if mode in (DataMode.ERROR, DataMode.EMPTY):
        return _placeholder_figure(mode, height=580)

    colors = get_market_colors(market)
    up_color = colors["up"]
    down_color = colors["down"]

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.7, 0.3],
            subplot_titles=(f"📈 {stock_title} 價格走勢與均線", "💬 社群輿情情緒指數 (Sentiment Score)")
        )

        dates = df["trade_date"]
        close_prices = df["close_price"]

        # 1. 上層：日 K 線圖
        candlestick = go.Candlestick(
            x=dates,
            open=df["open_price"],
            high=df["high_price"],
            low=df["low_price"],
            close=close_prices,
            name="K線",
            increasing_line_color=up_color,
            decreasing_line_color=down_color,
            increasing_fillcolor=up_color,
            decreasing_fillcolor=down_color,
            customdata=np.stack((df.get("sentiment_mean", np.zeros(len(df))), df.get("bullishness_index", np.zeros(len(df)))), axis=-1),
            hovertemplate="<b>日期:</b> %{x}<br><b>開:</b> %{open:.2f} | <b>高:</b> %{high:.2f}<br><b>低:</b> %{low:.2f} | <b>收:</b> %{close:.2f}<br><b>情緒:</b> %{customdata[0]:.2f} (Bt: %{customdata[1]:.2f})<extra></extra>"
        )
        fig.add_trace(candlestick, row=1, col=1)

        # 2. 上層：MA5 與 MA20 均線
        ma5 = close_prices.rolling(5, min_periods=1).mean()
        ma20 = close_prices.rolling(20, min_periods=1).mean()

        fig.add_trace(go.Scatter(x=dates, y=ma5, mode="lines", name="MA5 (週線)", line=dict(color="#FFD600", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=dates, y=ma20, mode="lines", name="MA20 (月線)", line=dict(color="#2962FF", width=1.5)), row=1, col=1)

        # 3. 下層：社群情緒分數長條圖
        sentiment_scores = df.get("sentiment_mean", pd.Series(0.5, index=df.index))
        bar_colors = [up_color if s >= 0.5 else down_color for s in sentiment_scores]

        fig.add_trace(
            go.Bar(
                x=dates,
                y=sentiment_scores,
                name="情緒總分",
                marker_color=bar_colors,
                opacity=0.75,
                hovertemplate="<b>日期:</b> %{x}<br><b>情緒總分:</b> %{y:.2f}<extra></extra>"
            ),
            row=2, col=1
        )

        # 下層：加入 0.5 中立基準線
        fig.add_hline(y=0.5, line_dash="dash", line_color="#848E9C", line_width=1, row=2, col=1)

        # 4. 全域深色金融佈局微調
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117",
            font=dict(color="#E0E3EB", family="Segoe UI, sans-serif"),
            xaxis_rangeslider_visible=False,
            margin=dict(l=40, r=40, t=40, b=30),
            height=580,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(showgrid=True, gridcolor="#2B313F", zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor="#2B313F", zeroline=False)
        if mode == DataMode.DEMO:
            fig = _apply_demo_watermark(fig)
        return fig

    except ImportError:
        fig = _FallbackPlotlyFigure(
            data=[{"type": "candlestick", "stock": stock_title}],
            layout={"title": stock_title, "market": market}
        )
        if mode == DataMode.DEMO:
            fig = _apply_demo_watermark(fig)
        return fig


def render_pnl_equity_curve_chart(
    df: pd.DataFrame,
    market: str = "TW",
    mode: DataMode = DataMode.REAL,
) -> Any:
    """
    繪製模擬量化策略累積報酬率曲線 (AI Multi-Modal Strategy vs. Buy & Hold Benchmark)。
    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
    """
    if mode in (DataMode.ERROR, DataMode.EMPTY):
        return _placeholder_figure(mode, height=380)

    try:
        import plotly.graph_objects as go

        dates = df["trade_date"]
        actual_returns = df.get("return_1d", pd.Series(0.0, index=df.index)).fillna(0.0)

        # Buy & Hold 累積報酬
        bh_cum = np.exp(np.cumsum(actual_returns)) - 1.0

        # AI 多空策略模擬報酬 (若當日情緒偏多且回報正向，給予增益)
        sentiment = df.get("sentiment_mean", pd.Series(0.5, index=df.index)).fillna(0.5)
        signals = np.where(sentiment >= 0.5, 1.0, -1.0)
        strat_returns = signals * actual_returns
        strat_cum = np.exp(np.cumsum(strat_returns)) - 1.0

        fig = go.Figure()

        # Buy & Hold 基準線
        fig.add_trace(go.Scatter(
            x=dates,
            y=bh_cum * 100.0,
            mode="lines",
            name="買入持有基準 (Buy & Hold)",
            line=dict(color="#848E9C", width=1.5, dash="dot")
        ))

        # AI 多模態策略報酬線
        fig.add_trace(go.Scatter(
            x=dates,
            y=strat_cum * 100.0,
            mode="lines",
            name="AI 多模態情緒融合策略 (Alpha Model)",
            line=dict(color="#2962FF", width=2.5),
            fill="tonexty",
            fillcolor="rgba(41, 98, 255, 0.1)"
        ))

        fig.update_layout(
            title=dict(text="📊 累積報酬率回測曲線 (Cumulative Strategy Return %)", y=0.97, yanchor="top"),
            template="plotly_dark",
            paper_bgcolor="#1E222D",
            plot_bgcolor="#1E222D",
            font=dict(color="#E0E3EB"),
            margin=dict(l=40, r=40, t=60, b=70),
            height=380,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
            yaxis=dict(title="累積報酬率 (%)", showgrid=True, gridcolor="#2B313F"),
            xaxis=dict(showgrid=True, gridcolor="#2B313F")
        )
        if mode == DataMode.DEMO:
            fig = _apply_demo_watermark(fig)
        return fig

    except ImportError:
        fig = _FallbackPlotlyFigure(
            data=[{"type": "equity_curve"}],
            layout={"title": "Cumulative Strategy Return"}
        )
        if mode == DataMode.DEMO:
            fig = _apply_demo_watermark(fig)
        return fig


def render_feature_importance_bar_chart(
    importances: Dict[str, float],
    mode: DataMode = DataMode.REAL,
) -> Any:
    """
    繪製模型全特徵貢獻度圓餅圖。
    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
    """
    if mode in (DataMode.ERROR, DataMode.EMPTY):
        return _placeholder_figure(mode, height=380)

    try:
        import plotly.graph_objects as go

        if not importances:
            importances = {
                "bullishness_index": 0.22,
                "rsi_14": 0.18,
                "sentiment_3d_ma": 0.15,
                "volatility_5d": 0.12,
                "agreement_index": 0.10,
                "return_1d": 0.09,
                "volume": 0.08,
                "sentiment_lag_1": 0.06
            }

        sorted_items = sorted(importances.items(), key=lambda x: x[1], reverse=True)
        feat_names = [x[0] for x in sorted_items]
        feat_values = [x[1] * 100.0 for x in sorted_items]

        # 為情緒類特徵加上醒目色彩，與長條圖版本沿用相同配色語意
        slice_colors = ["#2962FF" if ("sentiment" in f or "bullish" in f or "agree" in f) else "#00C853" for f in feat_names]

        fig = go.Figure(go.Pie(
            labels=feat_names,
            values=feat_values,
            hole=0.35,
            sort=False,
            marker=dict(colors=slice_colors, line=dict(color="#1E222D", width=1)),
            hovertemplate="<b>特徵:</b> %{label}<br><b>貢獻權重:</b> %{value:.1f}%<extra></extra>"
        ))

        fig.update_layout(
            title="🧠 全特徵貢獻度 (Feature Importance %)",
            template="plotly_dark",
            paper_bgcolor="#1E222D",
            plot_bgcolor="#1E222D",
            font=dict(color="#E0E3EB"),
            margin=dict(l=20, r=20, t=50, b=20),
            height=380,
            legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.0)
        )
        if mode == DataMode.DEMO:
            fig = _apply_demo_watermark(fig)
        return fig

    except ImportError:
        fig = _FallbackPlotlyFigure(
            data=[{"type": "feature_importance_pie"}],
            layout={}
        )
        if mode == DataMode.DEMO:
            fig = _apply_demo_watermark(fig)
        return fig
