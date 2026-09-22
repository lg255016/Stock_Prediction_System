import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .styles import get_market_colors
from .data_loader import DataMode

logger = logging.getLogger(__name__)

# 輕量 Streamlit Fallback Stub (供無 streamlit 環境下執行單元測試)
try:
    import streamlit as st
except ImportError:
    class _FallbackStreamlit:
        def markdown(self, *args: Any, **kwargs: Any) -> None: pass
        def caption(self, *args: Any, **kwargs: Any) -> None: pass
        def progress(self, *args: Any, **kwargs: Any) -> None: pass
        def columns(self, spec: Any) -> List["_FallbackStreamlit"]:
            n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
            return [_FallbackStreamlit() for _ in range(n)]
        def dataframe(self, *args: Any, **kwargs: Any) -> None: pass
        def selectbox(self, label: str, options: List[Any], **kwargs: Any) -> Any:
            return options[0] if options else None
        def text_input(self, *args: Any, **kwargs: Any) -> str:
            return ""
        def info(self, *args: Any, **kwargs: Any) -> None: pass
        def button(self, label: str, *args: Any, **kwargs: Any) -> bool:
            return False

        class column_config:
            @staticmethod
            def TextColumn(*args: Any, **kwargs: Any) -> None: return None
            @staticmethod
            def ProgressColumn(*args: Any, **kwargs: Any) -> None: return None
            @staticmethod
            def NumberColumn(*args: Any, **kwargs: Any) -> None: return None

        def __enter__(self) -> "_FallbackStreamlit": return self
        def __exit__(self, *args: Any) -> None: pass

    st = _FallbackStreamlit()

# 特徵中文名稱友善對照表 (提高投資決策可解釋性)
FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    "bullishness_index": "Antweiler 看多指數 (Bt)",
    "agreement_index": "Antweiler 一致性指數 (At)",
    "sentiment_mean": "當日平均情緒分數",
    "sentiment_3d_ma": "3日情緒移動均線",
    "sentiment_5d_ma": "5日情緒移動均線",
    "sentiment_lag_1": "前1日情緒滯後",
    "sentiment_lag_2": "前2日情緒滯後",
    "article_count": "當日社群討論聲量",
    "rsi_14": "RSI-14 相對強弱指標",
    "volatility_5d": "5日滾動歷史波動率",
    "volatility_20d": "20日滾動歷史波動率",
    "return_1d": "前1日對數報酬率",
    "close_price": "收盤價",
    "open_price": "開盤價",
    "high_price": "最高價",
    "low_price": "最低價",
    "volume": "成交量",
}


# DataMode 非 REAL 時的橫幅文案 (icon, 說明文字, 強調色)
_MODE_BANNER: Dict[DataMode, Tuple[str, str, str]] = {
    DataMode.ERROR: ("⚠️", "資料來源目前無法連線，以下不顯示任何推算數值", "#FF5252"),
    DataMode.EMPTY: ("💡", "資料庫連線正常，但目前查無相關資料", "#FFA726"),
    DataMode.DEMO: ("🧪", "目前顯示離線示範資料，並非即時真實數據", "#2962FF"),
}


def render_data_mode_banner(mode: DataMode, context_label: str = "") -> None:
    """
    渲染 DataMode 狀態橫幅。REAL 時不渲染任何內容（no-op）。
    ERROR／EMPTY／DEMO 三態使用統一視覺語彙，供各元件呼叫，避免各自維護重複文案。
    """
    if mode == DataMode.REAL:
        return
    icon, text, color = _MODE_BANNER[mode]
    suffix = f"（{context_label}）" if context_label else ""
    st.markdown(
        f"""
        <div style="background-color: #1E222D; border: 1px solid {color}; border-radius: 8px;
                    padding: 10px 16px; margin-bottom: 10px; font-size: 13px; color: {color};">
            {icon} <b>{text}{suffix}</b>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_prediction_panel(
    prediction_result: Optional[Dict[str, Any]],
    market: str = "TW",
    mode: DataMode = DataMode.REAL,
) -> None:
    """
    渲染 AI 即時預測決策面板與 Top 3 驅動因子解析。
    mode 非 REAL／DEMO 時（ERROR／EMPTY），prediction_result 應為 None，僅渲染狀態橫幅，
    不渲染任何預測數值（DEC-012 方案 B）。
    """
    st.markdown("### 🤖 AI 智能趨勢決策與可解釋性面板")

    if prediction_result is None:
        # 防禦性保護：呼叫端未依 mode 提供 prediction_result 時一律視為無法顯示
        render_data_mode_banner(mode if mode != DataMode.REAL else DataMode.ERROR, "AI 預測面板")
        return
    if mode in (DataMode.ERROR, DataMode.EMPTY):
        render_data_mode_banner(mode, "AI 預測面板")
        return

    render_data_mode_banner(mode, "AI 預測面板")
    colors = get_market_colors(market)
    is_up = prediction_result.get("predicted_direction", "UP") == "UP"
    dir_color = colors["up"] if is_up else colors["down"]
    dir_text = "🟢 看多上漲 (UP)" if is_up else "🔴 看跌下挫 (DOWN)"
    conf = float(prediction_result.get("confidence_score", 0.5))
    model_name = str(prediction_result.get("model_name", "random_forest")).upper()

    col_pred, col_conf = st.columns([1, 2])
    with col_pred:
        st.markdown(
            f"""
            <div style="background-color: #1E222D; border: 2px solid {dir_color}; border-radius: 10px; padding: 20px; text-align: center;">
                <div style="font-size: 13px; color: #848E9C;">預測明日收盤趨勢</div>
                <div style="font-size: 24px; font-weight: 700; color: {dir_color}; margin: 8px 0;">{dir_text}</div>
                <div style="font-size: 12px; color: #E0E3EB;">推論模型: <b>{model_name}</b></div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col_conf:
        st.markdown(f"**📈 模型預測信心水準 (Confidence Score): `{conf * 100.0:.1f}%`**")
        st.progress(conf)
        st.caption("決策依據：結合當日 18 欄位價量與社群輿情特徵，由 Walk-Forward 驗證之冠軍樹模型輸出之條件機率。")

    # 渲染 Top 3 關鍵驅動特徵
    st.markdown("#### 🔍 前 3 大關鍵驅動因子解析 (Top 3 Decision Drivers)")
    top_drivers = prediction_result.get("top_drivers", [])
    if top_drivers:
        cols = st.columns(len(top_drivers))
        for i, d in enumerate(top_drivers):
            raw_name = d.get("feature_name", f"Feature {i+1}")
            display_name = FEATURE_DISPLAY_NAMES.get(raw_name, raw_name)
            val = d.get("feature_value", 0.0)
            weight = d.get("importance_weight", 0.0) * 100.0

            with cols[i]:
                st.markdown(
                    f"""
                    <div style="background-color: #1A1E29; border: 1px solid #2B313F; border-radius: 8px; padding: 14px 16px;">
                        <div style="font-size: 12px; color: #848E9C;">Top {i+1} 驅動特徵</div>
                        <div style="font-size: 14px; font-weight: 600; color: #2962FF; margin: 4px 0;">{display_name}</div>
                        <div style="font-size: 18px; font-weight: 700; color: #FFFFFF;">{val:,.2f}</div>
                        <div style="font-size: 12px; color: #00C853;">貢獻權重: <b>{weight:.1f}%</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


_TOURNAMENT_RANK_LABELS = ["🏆 冠軍", "🥈 亞軍", "🥉 季軍", "第 4 名"]
_TOURNAMENT_MODEL_DISPLAY = {
    "logistic_regression": "Logistic Regression",
    "random_forest": "Random Forest",
    "lightgbm": "LightGBM",
    "xgboost": "XGBoost",
}


def render_tournament_leaderboard(data: Optional[Dict[str, Any]] = None, mode: DataMode = DataMode.EMPTY) -> None:
    """
    渲染 8 組平行對照實驗多模型排行榜 (Multi-Model Tournament Leaderboard)。

    資料來源見 `data_loader.load_tournament_results()`（UG-G1-SB3；DRIFT-008／DRIFT-018）。
    mode=EMPTY 時顯示「尚未完成模型競技」而非假資料；mode=ERROR 時顯示錯誤橫幅；
    mode=REAL 時渲染 `MLEvaluator.evaluate_tournament()` 產出的真實排行榜與 Alpha 歸因。
    """
    st.markdown("### 🏆 8 組平行對照實驗競技排行榜 (Multi-Model Leaderboard)")
    st.caption("透過 Walk-Forward 時序交叉驗證，量化驗證社群情緒特徵在 4 大演算法下的 Alpha 增益 (ΔAlpha)。")

    if mode == DataMode.EMPTY:
        st.markdown(
            """
            <div style="background-color: #1E222D; border: 1px dashed #4E5D78; border-radius: 8px;
                        padding: 18px 24px; text-align: center; margin: 15px 0;">
                <span style="color: #848E9C;">💡 尚未完成模型競技——執行
                <code>scripts/generate_tournament_artifact.py</code> 後即可顯示真實結果</span>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    if mode != DataMode.REAL or not data or not data.get("leaderboard"):
        render_data_mode_banner(mode if mode != DataMode.REAL else DataMode.ERROR, "模型競技排行榜")
        return

    rows = data["leaderboard"]
    mm_rows = sorted(
        (r for r in rows if "MultiModal" in r.get("feature_set", "")),
        key=lambda r: r.get("macro_f1", 0.0) * 0.7 + r.get("directional_hit_ratio", 0.0) * 0.3,
        reverse=True,
    )
    tech_rows = [r for r in rows if "PureTechnical" in r.get("feature_set", "")]
    alpha = data.get("alpha_attribution", {})

    table_rows = []
    for i, r in enumerate(mm_rows):
        rank_label = _TOURNAMENT_RANK_LABELS[i] if i < len(_TOURNAMENT_RANK_LABELS) else f"第 {i + 1} 名"
        model = r.get("model_name", "")
        delta_f1 = alpha.get(model, {}).get("delta_macro_f1")
        table_rows.append({
            "排名": rank_label,
            "模型演算法": _TOURNAMENT_MODEL_DISPLAY.get(model, model),
            "特徵集": r.get("feature_set", ""),
            "Macro F1": f"{r.get('macro_f1', 0.0):.4f}",
            "方向命中率": f"{r.get('directional_hit_ratio', 0.0) * 100:.1f}%",
            "累積策略報酬": f"{r.get('cumulative_return', 0.0) * 100:+.1f}%",
            "ΔAlpha 增益": f"{delta_f1 * 100:+.1f}%" if delta_f1 is not None else "—",
        })
    for r in tech_rows:
        model = r.get("model_name", "")
        table_rows.append({
            "排名": "控制組",
            "模型演算法": _TOURNAMENT_MODEL_DISPLAY.get(model, model),
            "特徵集": r.get("feature_set", ""),
            "Macro F1": f"{r.get('macro_f1', 0.0):.4f}",
            "方向命中率": f"{r.get('directional_hit_ratio', 0.0) * 100:.1f}%",
            "累積策略報酬": f"{r.get('cumulative_return', 0.0) * 100:+.1f}%",
            "ΔAlpha 增益": "基準線",
        })

    df_lb = pd.DataFrame(table_rows)
    st.dataframe(df_lb, use_container_width=True, hide_index=True)

    champion = data.get("champion_model_name", "")
    st.caption(
        f"🏆 綜合冠軍模型：**{_TOURNAMENT_MODEL_DISPLAY.get(champion, champion)}**"
        f"（綜合分數 {data.get('champion_score', 0.0):.4f} = Macro F1 × 0.7 + 方向命中率 × 0.3）"
    )


def render_raw_article_table(df_articles: pd.DataFrame, mode: DataMode = DataMode.REAL) -> None:
    """
    渲染 PTT 原始輿情文章明細表格（支援多維篩選、即時搜尋與透明化空狀態展示）。
    mode=ERROR 時僅渲染連線失敗橫幅，不嘗試渲染表格（df_articles 預期為空）。
    mode=EMPTY 時沿用既有的「查無文章」空狀態說明（比 ERROR 更精確：DB 連線正常，只是真的沒有）。
    mode=DEMO 時渲染示範資料橫幅後正常渲染表格。
    """
    st.markdown("### 📰 PTT 股市版社群輿情明細 (Raw Sentiment Articles)")

    if mode == DataMode.ERROR:
        render_data_mode_banner(mode, "PTT 輿情明細")
        return

    if mode == DataMode.DEMO:
        render_data_mode_banner(mode, "PTT 輿情明細")

    if df_articles is None or df_articles.empty:
        st.markdown(
            """
            <div style="background-color: #1E222D; border: 1px dashed #4E5D78; border-radius: 8px; padding: 18px 24px; text-align: center; margin: 15px 0;">
                <div style="font-size: 16px; font-weight: 600; color: #FFA726; margin-bottom: 6px;">💡 目前資料庫中暫無此標的之 PTT 社群文章</div>
                <div style="font-size: 13px; color: #848E9C; line-height: 1.6;">
                    • 系統已依量化金融規範，在特徵工程中自動將社群情緒分數平滑為中立基準值 <b style="color: #FFA726;">(0.50)</b>。<br>
                    • 若欲追蹤此標的之 PTT 討論，可在 ETL 排程中新增關鍵字進行即時爬取與 NLP 運算。
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    # 篩選控制列
    col_filter1, col_filter2, col_filter3 = st.columns([1, 1, 2])
    with col_filter1:
        sentiment_filter = st.selectbox("📌 情緒標籤篩選", options=["全部標籤", "看多", "中立", "看空"], index=0)

    with col_filter2:
        sort_by = st.selectbox("🔃 排序方式", options=["最新發文優先", "情緒分數由高到低", "情緒分數由低到高", "推文數優先"], index=0)

    with col_filter3:
        search_query = st.text_input("🔍 搜尋標題關鍵字", placeholder="輸入如：財報、外資、營收...")

    # 套用篩選
    df_filtered = df_articles.copy()
    if sentiment_filter != "全部標籤":
        df_filtered = df_filtered[df_filtered["sentiment_label"] == sentiment_filter]

    if search_query:
        df_filtered = df_filtered[df_filtered["title"].str.contains(search_query, case=False, na=False)]

    if df_filtered.empty:
        st.info("🔍 沒有符合目前篩選條件的文章。")
        return

    # 套用排序
    if sort_by == "最新發文優先":
        df_filtered = df_filtered.sort_values(by="publish_time", ascending=False)
    elif sort_by == "情緒分數由高到低":
        df_filtered = df_filtered.sort_values(by="sentiment_score", ascending=False)
    elif sort_by == "情緒分數由低到高":
        df_filtered = df_filtered.sort_values(by="sentiment_score", ascending=True)
    elif sort_by == "推文數優先":
        df_filtered = df_filtered.sort_values(by="push_count", ascending=False)

    cols_to_show = ["publish_time", "stock_id", "sentiment_label", "sentiment_score", "push_count", "title", "source"]
    col_cfg = {
        "publish_time": st.column_config.TextColumn("發文時間", width="medium"),
        "stock_id": st.column_config.TextColumn("股票代碼", width="small"),
        "sentiment_label": st.column_config.TextColumn("多空判定", width="small"),
        "sentiment_score": st.column_config.ProgressColumn("情緒分數", min_value=0.0, max_value=1.0, format="%.2f"),
        "push_count": st.column_config.NumberColumn("推噓數", width="small"),
        "title": st.column_config.TextColumn("文章標題", width="large"),
        "source": st.column_config.TextColumn("資料來源", width="small"),
    }
    if "url" in df_filtered.columns:
        cols_to_show.append("url")
        col_cfg["url"] = st.column_config.LinkColumn("原文連結", width="small")

    st.dataframe(
        df_filtered[cols_to_show],
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg
    )


def render_ai_trend_discovery_badge(keywords: List[str], mode: DataMode = DataMode.REAL) -> None:
    """
    渲染 AI 今日市場熱搜探索詞 (AI Trend Discovery) 視覺化卡片。
    mode=ERROR 時渲染連線失敗橫幅並停止（keywords 預期為空）。
    mode=EMPTY 時安靜跳過（DB 連線正常但目前無探索詞，非錯誤，維持既有低干擾行為）。
    """
    if mode == DataMode.ERROR:
        render_data_mode_banner(mode, "AI 熱門題材探索")
        return
    if mode == DataMode.EMPTY or not keywords:
        return

    if mode == DataMode.DEMO:
        render_data_mode_banner(mode, "AI 熱門題材探索")

    status_text = "● 實時探索中" if mode == DataMode.REAL else "● 離線示範"
    status_color = "#00C853" if mode == DataMode.REAL else "#2962FF"

    badges_html = " ".join([
        f'<span style="display: inline-block; background: linear-gradient(135deg, rgba(255, 75, 75, 0.2), rgba(255, 140, 0, 0.2)); border: 1px solid #FF8C00; color: #FFA726; padding: 4px 10px; border-radius: 14px; font-size: 12px; font-weight: 600; margin: 4px 4px 4px 0;">🔥 {kw}</span>'
        for kw in keywords
    ])

    st.markdown(
        f"""
        <div style="background-color: #1E222D; border: 1px solid #2B313F; border-radius: 10px; padding: 14px 18px; margin-bottom: 15px;">
            <div style="font-size: 13px; color: #848E9C; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                <span>🤖 <b>AI 自動挖掘市場熱門題材詞</b> (Trend Discovery)</span>
                <span style="font-size: 11px; color: {status_color};">{status_text}</span>
            </div>
            <div>{badges_html}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_thematic_radar(
    themes_data: List[Dict[str, Any]],
    mode: DataMode = DataMode.REAL,
) -> Optional[str]:
    """
    渲染頂部「🔥 市場熱門題材雷達 (AI Thematic Concept Radar)」卡片群。
    支援點擊成分股按鈕，一鍵秒速切換選取標的。
    回傳被點擊的 stock_id (若有)，否則回傳 None。
    mode=ERROR 時渲染連線失敗橫幅並停止（themes_data 預期為空）。
    mode=EMPTY 時安靜跳過（DB 連線正常但目前無題材，非錯誤，維持既有低干擾行為）。
    """
    if mode == DataMode.ERROR:
        render_data_mode_banner(mode, "題材熱搜雷達")
        return None
    if mode == DataMode.EMPTY or not themes_data:
        return None

    st.markdown("### 🔥 市場熱門題材雷達 (AI Thematic Concept Radar)")
    if mode == DataMode.DEMO:
        render_data_mode_banner(mode, "題材熱搜雷達")
    cols = st.columns(len(themes_data))
    clicked_stock = None

    for i, t in enumerate(themes_data):
        with cols[i]:
            theme_name = t.get("theme", "題材")
            icon = t.get("icon", "💡")
            cnt = t.get("article_count", 0)
            bullishness = t.get("bullishness", 0.0)
            sentiment_label = t.get("sentiment_label", "穩定")
            stocks = t.get("stocks", [])

            tag_color = "#00C853" if bullishness >= 0.5 else ("#FF5252" if bullishness <= -0.5 else "#FFA726")

            st.markdown(
                f"""
                <div style="background-color: #1E222D; border: 1px solid #2B313F; border-top: 3px solid {tag_color}; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
                    <div style="font-size: 14px; font-weight: 700; color: #FFFFFF; margin-bottom: 6px;">
                        {icon} {theme_name}
                    </div>
                    <div style="font-size: 11px; color: #848E9C; line-height: 1.6;">
                        • 討論聲量：<b style="color: #E0E3EB;">{cnt} 篇</b><br>
                        • 看多指數：<b style="color: {tag_color};">+{bullishness:.2f} ({sentiment_label})</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            for s in stocks:
                s_id = s.get("stock_id", "")
                display_name = s.get("display", s_id)
                if st.button(f"👉 {display_name}", key=f"btn_theme_{i}_{s_id}", use_container_width=True):
                    clicked_stock = s_id

    return clicked_stock


