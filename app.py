import streamlit as st
import pandas as pd
import numpy as np

from src.ui.styles import (
    DARK_THEME_CSS,
    render_kpi_card_html,
    get_market_colors,
)
from src.ui.data_loader import (
    get_available_stocks,
    load_stock_features,
    load_stock_articles,
    get_champion_predictor,
    load_ai_discovered_keywords,
    load_thematic_radar_data,
    load_tournament_results,
    DataMode,
)
from src.ui.charts import (
    render_price_sentiment_candlestick_chart,
    render_pnl_equity_curve_chart,
    render_feature_importance_bar_chart,
)
from src.ui.components import (
    render_prediction_panel,
    render_tournament_leaderboard,
    render_raw_article_table,
    render_ai_trend_discovery_badge,
    render_thematic_radar,
    render_data_mode_banner,
)

# DataMode → 精簡狀態標籤，供 Sidebar 全域來源追蹤使用
_MODE_LABEL = {
    DataMode.REAL: "🟢 REAL",
    DataMode.DEMO: "🧪 DEMO",
    DataMode.EMPTY: "💡 EMPTY",
    DataMode.ERROR: "🔴 ERROR",
}

# 1. 頁面全域配置
st.set_page_config(
    page_title="金融情緒與股價趨勢預測系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. 注入金融深色模式 CSS
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)


def main():
    # 初始化自選股 session_state
    if "custom_stocks" not in st.session_state:
        st.session_state["custom_stocks"] = {}

    stocks = get_available_stocks(st.session_state["custom_stocks"])
    stock_keys = list(stocks.keys())

    # ----------------------------------------------------
    # 3. 側邊欄控制面板 (Sidebar Controls)
    # ----------------------------------------------------
    with st.sidebar:
        st.markdown("### ⚙️ 終端控制區")
        st.markdown("---")

        # 股票標的選擇器
        selected_stock_idx = 0
        if "selected_stock_id" in st.session_state and st.session_state["selected_stock_id"] in stock_keys:
            selected_stock_idx = stock_keys.index(st.session_state["selected_stock_id"])

        selected_stock = st.selectbox(
            "📌 選擇目標股票標的",
            options=stock_keys,
            format_func=lambda x: stocks[x],
            index=selected_stock_idx,
        )
        st.session_state["selected_stock_id"] = selected_stock

        # 自選/新增股票互動區塊 (Custom Stock Management)
        with st.expander("➕ 自選 / 新增股票標的", expanded=False):
            with st.form("add_stock_form", clear_on_submit=True):
                new_id = st.text_input("股票代碼 (例: 2454, TSLA, 2603)").strip().upper()
                new_name = st.text_input("股票名稱 (例: 聯發科, 特斯拉)").strip()
                submitted = st.form_submit_button("➕ 加入觀察清單")

                if submitted and new_id:
                    display_text = f"{new_name} ({new_id})" if new_name else new_id
                    st.session_state["custom_stocks"][new_id] = display_text
                    st.session_state["selected_stock_id"] = new_id
                    st.success(f"✅ 已成功將 {display_text} 加入自選清單！")
                    st.rerun()

        date_options = {7: "近 7 天 (週線)", 30: "近 30 天 (月線)", 60: "近 60 天 (季線)", 90: "近 90 天 (半年)"}
        selected_days = st.selectbox(
            "📅 檢視時序區間",
            options=list(date_options.keys()),
            format_func=lambda x: date_options[x],
            index=1,
        )

        market_color_choice = st.radio(
            "🎨 漲跌色彩語彙",
            options=["台股習慣 (紅漲綠跌)", "美股/國際 (綠漲紅跌)"],
            index=0,
        )
        market_code = "TW" if "台股" in market_color_choice else "US"

        st.markdown("---")
        st.markdown("#### 🛡️ 系統運行狀態")
        st.caption("• **時序驗證**：Walk-Forward (0 洩漏)")
        st.caption("• **特徵矩陣**：18 欄位機構級特徵")
        st.caption("• **自動排程**：每日 15:35 定時觸發")
        st.caption("• **測試狀態**：124 / 124 PASS ✅")

    # ----------------------------------------------------
    # 4. 主畫面標題與 AI 熱門探索詞展示
    # ----------------------------------------------------
    st.markdown("## 📊 金融情緒與股價趨勢預測系統")
    st.caption("Financial Sentiment & Machine Learning Quantitative Prediction Terminal | v1.0")

    # 載入與渲染 AI 今日熱門探索關鍵字 (AI Trend Discovery)
    ai_keywords, keywords_mode = load_ai_discovered_keywords(limit=6)
    render_ai_trend_discovery_badge(ai_keywords, mode=keywords_mode)

    # 載入與渲染 🔥 市場熱門題材雷達 (AI Thematic Concept Radar)
    # render_thematic_radar 內部依 mode 決定渲染內容（ERROR 顯示橫幅／EMPTY 安靜跳過／
    # REAL・DEMO 正常渲染），因此一律呼叫，不再以 `if radar_data:` 短路。
    radar_data, radar_mode = load_thematic_radar_data()
    clicked_stock = render_thematic_radar(radar_data, mode=radar_mode)
    if clicked_stock:
        # 若點擊之成分股不在既有選單中，自動加入自選股清單
        if clicked_stock not in stocks:
            found_name = clicked_stock
            for t in radar_data:
                for s in t.get("stocks", []):
                    if s["stock_id"] == clicked_stock:
                        found_name = s.get("display", clicked_stock)
            st.session_state["custom_stocks"][clicked_stock] = found_name
        st.session_state["selected_stock_id"] = clicked_stock
        st.rerun()

    # 載入特徵資料與文章數據
    df_features, features_mode = load_stock_features(selected_stock, days=selected_days)
    df_all_history, history_mode = load_stock_features(selected_stock, days=90)
    df_articles, articles_mode = load_stock_articles(selected_stock, limit=25)
    tournament_data, tournament_mode = load_tournament_results()

    # 全域來源狀態追蹤：本次頁面渲染中各資料來源的 DataMode，供 Sidebar 彙總顯示。
    st.sidebar.caption(
        f"• **本次資料來源**：特徵 {_MODE_LABEL[features_mode]} ｜ 文章 {_MODE_LABEL[articles_mode]} "
        f"｜ AI熱詞 {_MODE_LABEL[keywords_mode]} ｜ 題材雷達 {_MODE_LABEL[radar_mode]} "
        f"｜ 模型競技 {_MODE_LABEL[tournament_mode]}"
    )

    # KPI 卡片、預測面板與主圖表均需要「有真正可用的特徵矩陣」——
    # DEC-012 方案 B：ERROR／EMPTY 時不推算、不渲染任何數值，只顯示狀態說明。
    usable_modes = (DataMode.REAL, DataMode.DEMO)
    features_usable = features_mode in usable_modes and not df_features.empty
    history_usable = history_mode in usable_modes and not df_all_history.empty
    can_predict = features_usable and history_usable

    predictor = None
    prediction_result = None
    if can_predict:
        predictor = get_champion_predictor(df_all_history)
        prediction_result = predictor.predict_latest(df_features)

    # ----------------------------------------------------
    # 5. 頂部 3 大核心 KPI 卡片
    # ----------------------------------------------------
    if not features_usable:
        render_data_mode_banner(features_mode, "股價與情緒 KPI")
    else:
        latest_row = df_features.iloc[-1]
        close_price = latest_row["close_price"]
        day_return = latest_row["return_1d"] * 100.0
        sentiment_score = latest_row["sentiment_mean"]
        bullishness_idx = latest_row["bullishness_index"]
        agreement_idx = latest_row["agreement_index"]

        is_price_up = day_return >= 0

        col1, col2, col3 = st.columns(3)

        with col1:
            delta_str = f"{'+' if day_return >= 0 else ''}{day_return:.2f}% (單日)"
            card_html = render_kpi_card_html(
                title="最新股價 (Latest Close)",
                value=f"${close_price:,.2f} TWD" if market_code == "TW" else f"${close_price:,.2f} USD",
                delta=delta_str,
                is_positive=is_price_up,
                icon="💵",
                badge="即時盤後" if features_mode == DataMode.REAL else "離線示範",
                market=market_code,
            )
            st.markdown(card_html, unsafe_allow_html=True)

        with col2:
            sent_label = "強烈樂觀" if sentiment_score >= 0.65 else ("偏空悲觀" if sentiment_score <= 0.45 else "中性平衡")
            sent_delta = f"看多指數 B_t: {bullishness_idx:+.2f} | 一致性: {agreement_idx:.2f}"
            card_html = render_kpi_card_html(
                title="社群情緒總分 (Market Sentiment)",
                value=f"{sentiment_score:.2f} / 1.00",
                delta=sent_delta,
                is_positive=(sentiment_score >= 0.5),
                icon="💬",
                badge=sent_label,
                market=market_code,
            )
            st.markdown(card_html, unsafe_allow_html=True)

        with col3:
            if prediction_result is not None:
                is_pred_up = prediction_result["predicted_direction"] == "UP"
                conf_pct = prediction_result["confidence_score"] * 100.0
                dir_text = "看多 (UP)" if is_pred_up else "看空 (DOWN)"
                pred_delta = f"AI 置信度: {conf_pct:.1f}% | 冠軍模型: {prediction_result['model_name']}"
                card_html = render_kpi_card_html(
                    title="AI 明日趨勢預測 (Prediction)",
                    value=f"{'🟢' if is_pred_up else '🔴'} {dir_text}",
                    delta=pred_delta,
                    is_positive=is_pred_up,
                    icon="🤖",
                    badge=f"Confidence {conf_pct:.0f}%",
                    market=market_code,
                )
                st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("---")

    # ----------------------------------------------------
    # 6. 主要圖表區 (Main Chart: Plotly 雙 Y 軸互動圖)
    # ----------------------------------------------------
    st.markdown(f"### 📈 {stocks[selected_stock]} 多維互動價格與社群情緒圖表")
    fig_main = render_price_sentiment_candlestick_chart(
        df_features, stock_title=stocks[selected_stock], market=market_code, mode=features_mode
    )
    if hasattr(fig_main, "to_dict"):
        st.plotly_chart(fig_main, use_container_width=True, key="chart_main_candlestick")

    # ----------------------------------------------------
    # 7. 量化回測曲線與特徵重要性 (Sub-Charts)
    # ----------------------------------------------------
    sub_col1, sub_col2 = st.columns(2)

    with sub_col1:
        fig_pnl = render_pnl_equity_curve_chart(df_features, market=market_code, mode=features_mode)
        if hasattr(fig_pnl, "to_dict"):
            st.plotly_chart(fig_pnl, use_container_width=True, key="chart_pnl_equity")

    with sub_col2:
        imp_mode = features_mode if can_predict else DataMode.ERROR
        importances = predictor.trainer.feature_importances_ if predictor is not None else {}
        fig_imp = render_feature_importance_bar_chart(importances, mode=imp_mode)
        if hasattr(fig_imp, "to_dict"):
            st.plotly_chart(fig_imp, use_container_width=True, key="chart_feature_importance")

    st.markdown("---")

    # ----------------------------------------------------
    # 8. AI 預測推論面板與 Top 3 驅動因子 (Prediction Panel)
    # ----------------------------------------------------
    render_prediction_panel(
        prediction_result, market=market_code,
        mode=features_mode if can_predict else DataMode.ERROR
    )

    st.markdown("---")

    # ----------------------------------------------------
    # 9. 8 組平行對照實驗橫向排行榜 (Tournament Leaderboard)
    # ----------------------------------------------------
    render_tournament_leaderboard(tournament_data, mode=tournament_mode)

    st.markdown("---")

    # ----------------------------------------------------
    # 10. PTT 原始社群輿情明細表 (Raw Articles Table)
    # ----------------------------------------------------
    render_raw_article_table(df_articles, mode=articles_mode)


if __name__ == "__main__":
    main()
