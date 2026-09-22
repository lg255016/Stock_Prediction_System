# UG-G1-SB2 步驟 3：實作報告

> **性質**：`SB2_GATE_A_PROPOSAL.md` 步驟 3 的實作交付。PO 已核准 §8 全部六項裁決
> （方案 B、charts.py 視覺標示、4 代表查詢確認），本文件為完成後的回報。
> **執行日期**：2026-08-25
> **狀態**：`src/`、`app.py`、`tests/` 已變更，尚未 commit

---

## 0. PO 核准的關鍵決策落實摘要

| 決策 | 落實方式 |
|------|---------|
| §3.2 方案 B：ERROR 不自動退回 DEMO | `data_loader.py` 四個公開函式的 ERROR 分支一律回傳空表／空清單，不呼叫任何 mock 生成器 |
| DEMO 僅供顯式啟用 | 四個公開函式新增 `demo: bool = False` 參數；`app.py` 目前不傳入 `demo=True`（無 UI 開關，符合 PO「不用做到 UI 開關」的指示） |
| charts.py 需要視覺標示 | 新增 `_placeholder_figure()`（ERROR／EMPTY 佔位圖）與 `_apply_demo_watermark()`（DEMO 浮水印），三個圖表函式全部套用 |
| 4 個代表查詢即可，不用全部 9 段 | `tests/schema_smoke_ui_data_loader.py` 維持 4 個 smoke test，PO 已確認欄位集合為聯集 |

---

## 1. 完整 Diff

**檔案清單**（8 modified + 2 new）：

 app.py                               | 192 ++++++++-------
 doc/governance/PROJECT_STATUS.md     |  13 +-
 src/ui/charts.py                     |  96 +++++++-
 src/ui/components.py                 |  93 +++++++-
 src/ui/data_loader.py                | 437 +++++++++++++++++++++--------------
 tests/test_operational_ux.py         |  49 +++-
 tests/test_real_articles_pipeline.py |  30 ++-
 tests/test_ui_contracts.py           | 172 ++++++++++++--
 8 files changed, 786 insertions(+), 296 deletions(-)

**重跑指令**：`git diff` （工作區尚未 staged，此指令即可重現下方全部內容）

<details>
<summary>完整 diff 內容（點擊展開）</summary>

```diff
diff --git a/app.py b/app.py
index 361d006..74fa446 100644
--- a/app.py
+++ b/app.py
@@ -14,6 +14,7 @@ from src.ui.data_loader import (
     get_champion_predictor,
     load_ai_discovered_keywords,
     load_thematic_radar_data,
+    DataMode,
 )
 from src.ui.charts import (
     render_price_sentiment_candlestick_chart,
@@ -26,8 +27,17 @@ from src.ui.components import (
     render_raw_article_table,
     render_ai_trend_discovery_badge,
     render_thematic_radar,
+    render_data_mode_banner,
 )
 
+# DataMode → 精簡狀態標籤，供 Sidebar 全域來源追蹤使用
+_MODE_LABEL = {
+    DataMode.REAL: "🟢 REAL",
+    DataMode.DEMO: "🧪 DEMO",
+    DataMode.EMPTY: "💡 EMPTY",
+    DataMode.ERROR: "🔴 ERROR",
+}
+
 # 1. 頁面全域配置
 st.set_page_config(
     page_title="金融情緒與股價趨勢預測系統",
@@ -111,89 +121,110 @@ def main():
     st.caption("Financial Sentiment & Machine Learning Quantitative Prediction Terminal | v1.0")
 
     # 載入與渲染 AI 今日熱門探索關鍵字 (AI Trend Discovery)
-    ai_keywords = load_ai_discovered_keywords(limit=6)
-    render_ai_trend_discovery_badge(ai_keywords)
+    ai_keywords, keywords_mode = load_ai_discovered_keywords(limit=6)
+    render_ai_trend_discovery_badge(ai_keywords, mode=keywords_mode)
 
     # 載入與渲染 🔥 市場熱門題材雷達 (AI Thematic Concept Radar)
-    radar_data = load_thematic_radar_data()
-    if radar_data:
-        clicked_stock = render_thematic_radar(radar_data)
-        if clicked_stock:
-            # 若點擊之成分股不在既有選單中，自動加入自選股清單
-            if clicked_stock not in stocks:
-                found_name = clicked_stock
-                for t in radar_data:
-                    for s in t.get("stocks", []):
-                        if s["stock_id"] == clicked_stock:
-                            found_name = s.get("display", clicked_stock)
-                st.session_state["custom_stocks"][clicked_stock] = found_name
-            st.session_state["selected_stock_id"] = clicked_stock
-            st.rerun()
+    # render_thematic_radar 內部依 mode 決定渲染內容（ERROR 顯示橫幅／EMPTY 安靜跳過／
+    # REAL・DEMO 正常渲染），因此一律呼叫，不再以 `if radar_data:` 短路。
+    radar_data, radar_mode = load_thematic_radar_data()
+    clicked_stock = render_thematic_radar(radar_data, mode=radar_mode)
+    if clicked_stock:
+        # 若點擊之成分股不在既有選單中，自動加入自選股清單
+        if clicked_stock not in stocks:
+            found_name = clicked_stock
+            for t in radar_data:
+                for s in t.get("stocks", []):
+                    if s["stock_id"] == clicked_stock:
+                        found_name = s.get("display", clicked_stock)
+            st.session_state["custom_stocks"][clicked_stock] = found_name
+        st.session_state["selected_stock_id"] = clicked_stock
+        st.rerun()
 
     # 載入特徵資料與文章數據
-    df_features = load_stock_features(selected_stock, days=selected_days)
-    df_all_history = load_stock_features(selected_stock, days=90)
-    df_articles = load_stock_articles(selected_stock, limit=25)
-
-    predictor = get_champion_predictor(df_all_history)
-    prediction_result = predictor.predict_latest(df_features)
+    df_features, features_mode = load_stock_features(selected_stock, days=selected_days)
+    df_all_history, history_mode = load_stock_features(selected_stock, days=90)
+    df_articles, articles_mode = load_stock_articles(selected_stock, limit=25)
+
+    # 全域來源狀態追蹤：本次頁面渲染中各資料來源的 DataMode，供 Sidebar 彙總顯示。
+    st.sidebar.caption(
+        f"• **本次資料來源**：特徵 {_MODE_LABEL[features_mode]} ｜ 文章 {_MODE_LABEL[articles_mode]} "
+        f"｜ AI熱詞 {_MODE_LABEL[keywords_mode]} ｜ 題材雷達 {_MODE_LABEL[radar_mode]}"
+    )
 
-    latest_row = df_features.iloc[-1]
-    close_price = latest_row["close_price"]
-    day_return = latest_row["return_1d"] * 100.0
-    sentiment_score = latest_row["sentiment_mean"]
-    bullishness_idx = latest_row["bullishness_index"]
-    agreement_idx = latest_row["agreement_index"]
+    # KPI 卡片、預測面板與主圖表均需要「有真正可用的特徵矩陣」——
+    # DEC-012 方案 B：ERROR／EMPTY 時不推算、不渲染任何數值，只顯示狀態說明。
+    usable_modes = (DataMode.REAL, DataMode.DEMO)
+    features_usable = features_mode in usable_modes and not df_features.empty
+    history_usable = history_mode in usable_modes and not df_all_history.empty
+    can_predict = features_usable and history_usable
 
-    is_price_up = day_return >= 0
-    is_pred_up = prediction_result["predicted_direction"] == "UP"
+    predictor = None
+    prediction_result = None
+    if can_predict:
+        predictor = get_champion_predictor(df_all_history)
+        prediction_result = predictor.predict_latest(df_features)
 
     # ----------------------------------------------------
     # 5. 頂部 3 大核心 KPI 卡片
     # ----------------------------------------------------
-    col1, col2, col3 = st.columns(3)
-
-    with col1:
-        delta_str = f"{'+' if day_return >= 0 else ''}{day_return:.2f}% (單日)"
-        card_html = render_kpi_card_html(
-            title="最新股價 (Latest Close)",
-            value=f"${close_price:,.2f} TWD" if market_code == "TW" else f"${close_price:,.2f} USD",
-            delta=delta_str,
-            is_positive=is_price_up,
-            icon="💵",
-            badge="即時盤後",
-            market=market_code,
-        )
-        st.markdown(card_html, unsafe_allow_html=True)
-
-    with col2:
-        sent_label = "強烈樂觀" if sentiment_score >= 0.65 else ("偏空悲觀" if sentiment_score <= 0.45 else "中性平衡")
-        sent_delta = f"看多指數 B_t: {bullishness_idx:+.2f} | 一致性: {agreement_idx:.2f}"
-        card_html = render_kpi_card_html(
-            title="社群情緒總分 (Market Sentiment)",
-            value=f"{sentiment_score:.2f} / 1.00",
-            delta=sent_delta,
-            is_positive=(sentiment_score >= 0.5),
-            icon="💬",
-            badge=sent_label,
-            market=market_code,
-        )
-        st.markdown(card_html, unsafe_allow_html=True)
-
-    with col3:
-        conf_pct = prediction_result["confidence_score"] * 100.0
-        dir_text = "看多 (UP)" if is_pred_up else "看空 (DOWN)"
-        pred_delta = f"AI 置信度: {conf_pct:.1f}% | 冠軍模型: {prediction_result['model_name']}"
-        card_html = render_kpi_card_html(
-            title="AI 明日趨勢預測 (Prediction)",
-            value=f"{'🟢' if is_pred_up else '🔴'} {dir_text}",
-            delta=pred_delta,
-            is_positive=is_pred_up,
-            icon="🤖",
-            badge=f"Confidence {conf_pct:.0f}%",
-            market=market_code,
-        )
-        st.markdown(card_html, unsafe_allow_html=True)
+    if not features_usable:
+        render_data_mode_banner(features_mode, "股價與情緒 KPI")
+    else:
+        latest_row = df_features.iloc[-1]
+        close_price = latest_row["close_price"]
+        day_return = latest_row["return_1d"] * 100.0
+        sentiment_score = latest_row["sentiment_mean"]
+        bullishness_idx = latest_row["bullishness_index"]
+        agreement_idx = latest_row["agreement_index"]
+
+        is_price_up = day_return >= 0
+
+        col1, col2, col3 = st.columns(3)
+
+        with col1:
+            delta_str = f"{'+' if day_return >= 0 else ''}{day_return:.2f}% (單日)"
+            card_html = render_kpi_card_html(
+                title="最新股價 (Latest Close)",
+                value=f"${close_price:,.2f} TWD" if market_code == "TW" else f"${close_price:,.2f} USD",
+                delta=delta_str,
+                is_positive=is_price_up,
+                icon="💵",
+                badge="即時盤後" if features_mode == DataMode.REAL else "離線示範",
+                market=market_code,
+            )
+            st.markdown(card_html, unsafe_allow_html=True)
+
+        with col2:
+            sent_label = "強烈樂觀" if sentiment_score >= 0.65 else ("偏空悲觀" if sentiment_score <= 0.45 else "中性平衡")
+            sent_delta = f"看多指數 B_t: {bullishness_idx:+.2f} | 一致性: {agreement_idx:.2f}"
+            card_html = render_kpi_card_html(
+                title="社群情緒總分 (Market Sentiment)",
+                value=f"{sentiment_score:.2f} / 1.00",
+                delta=sent_delta,
+                is_positive=(sentiment_score >= 0.5),
+                icon="💬",
+                badge=sent_label,
+                market=market_code,
+            )
+            st.markdown(card_html, unsafe_allow_html=True)
+
+        with col3:
+            if prediction_result is not None:
+                is_pred_up = prediction_result["predicted_direction"] == "UP"
+                conf_pct = prediction_result["confidence_score"] * 100.0
+                dir_text = "看多 (UP)" if is_pred_up else "看空 (DOWN)"
+                pred_delta = f"AI 置信度: {conf_pct:.1f}% | 冠軍模型: {prediction_result['model_name']}"
+                card_html = render_kpi_card_html(
+                    title="AI 明日趨勢預測 (Prediction)",
+                    value=f"{'🟢' if is_pred_up else '🔴'} {dir_text}",
+                    delta=pred_delta,
+                    is_positive=is_pred_up,
+                    icon="🤖",
+                    badge=f"Confidence {conf_pct:.0f}%",
+                    market=market_code,
+                )
+                st.markdown(card_html, unsafe_allow_html=True)
 
     st.markdown("---")
 
@@ -202,7 +233,7 @@ def main():
     # ----------------------------------------------------
     st.markdown(f"### 📈 {stocks[selected_stock]} 多維互動價格與社群情緒圖表")
     fig_main = render_price_sentiment_candlestick_chart(
-        df_features, stock_title=stocks[selected_stock], market=market_code
+        df_features, stock_title=stocks[selected_stock], market=market_code, mode=features_mode
     )
     if hasattr(fig_main, "to_dict"):
         st.plotly_chart(fig_main, use_container_width=True)
@@ -213,12 +244,14 @@ def main():
     sub_col1, sub_col2 = st.columns(2)
 
     with sub_col1:
-        fig_pnl = render_pnl_equity_curve_chart(df_features, market=market_code)
+        fig_pnl = render_pnl_equity_curve_chart(df_features, market=market_code, mode=features_mode)
         if hasattr(fig_pnl, "to_dict"):
             st.plotly_chart(fig_pnl, use_container_width=True)
 
     with sub_col2:
-        fig_imp = render_feature_importance_bar_chart(predictor.trainer.feature_importances_, top_n=8)
+        imp_mode = features_mode if can_predict else DataMode.ERROR
+        importances = predictor.trainer.feature_importances_ if predictor is not None else {}
+        fig_imp = render_feature_importance_bar_chart(importances, top_n=8, mode=imp_mode)
         if hasattr(fig_imp, "to_dict"):
             st.plotly_chart(fig_imp, use_container_width=True)
 
@@ -227,7 +260,10 @@ def main():
     # ----------------------------------------------------
     # 8. AI 預測推論面板與 Top 3 驅動因子 (Prediction Panel)
     # ----------------------------------------------------
-    render_prediction_panel(prediction_result, market=market_code)
+    render_prediction_panel(
+        prediction_result, market=market_code,
+        mode=features_mode if can_predict else DataMode.ERROR
+    )
 
     st.markdown("---")
 
@@ -241,7 +277,7 @@ def main():
     # ----------------------------------------------------
     # 10. PTT 原始社群輿情明細表 (Raw Articles Table)
     # ----------------------------------------------------
-    render_raw_article_table(df_articles)
+    render_raw_article_table(df_articles, mode=articles_mode)
 
 
 if __name__ == "__main__":
diff --git a/doc/governance/PROJECT_STATUS.md b/doc/governance/PROJECT_STATUS.md
index 3b7519e..b8a46fc 100644
--- a/doc/governance/PROJECT_STATUS.md
+++ b/doc/governance/PROJECT_STATUS.md
@@ -33,7 +33,8 @@
 | GOV-05 文件依歸屬與生命週期分類 | 完成 | `abfa743`、`7f7258e` |
 | GOV-06 交接 | 本次 | 本 commit |
 | **UG-Gate-1** | **已核准，採逐 SB 授權** | — |
-| └ **UG-G1-SB1** Purged Walk-Forward | Gate A 已核准；**步驟 0～5 完成；步驟 6（送 Gate B）未開始** | `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`；步驟 2 見 `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節；`src/` 變更尚未 commit |
+| └ **UG-G1-SB1** Purged Walk-Forward | **CLOSED**（2026-08-25 PO 核准結案） | commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`；證據見 `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、`SB1_GATE_B_SUBMISSION.md`；DEC-011、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-012）已同步 |
+| └ **UG-G1-SB2** UI Demo/Real 模式分離 | Gate A 提案撰寫中，**尚未核准，`src/` 不得變動** | `doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md` |
 
 RISK-001 `Accept`、RISK-010 `Defer`（至 Gate 3）、RISK-012 `Mitigate`、
 RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RISKS.md`。
@@ -42,14 +43,15 @@ RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RI
 
 | 項目 | 狀態 |
 |------|------|
-| **UG-G1-SB2 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權，SB1 尚未結案 |
+| **UG-G1-SB2 的 `src/` 實作** | **未授權**。Plan-Before-Code：PO 要求先看過並核准 Gate A 提案才可動 `src/`（與 SB1 不同，這次核准在實作前，不是事後接手） |
+| **UG-G1-SB3 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權 |
 | **UG-Gate-2、UG-Gate-3、UG-Gate-4** | **未核准，不得啟動** |
-| SB1 步驟 6（送 Gate B、commit） | 在已核准的 Gate A 範圍內，但**尚未執行**；步驟 0～5 已於 2026-08-24/25 完成，`src/` 變更尚未 commit，需另行取得 commit scope 授權 |
-| `src/`、`tests/`、`database/` | 升級專案至今**一行未改** |
+| `database/` | 升級專案至今**一行未改** |
 
 ### 0.4 測試基線
 
-**`154 tests / OK`**（dev container，Python 3.14.6，GOV-03 釘選環境）。
+**`164 tests / OK`**（dev container，Python 3.14.6，GOV-03 釘選環境；UG-G1-SB1 commit `ccf0e52`
+後之數字，較 GOV-02 基線 154 增加 10 個：SB1 新增 9 個 + 步驟 6 前補上的 `min_train_size` 跳過驗證 1 個）。
 
 §1 記載的「133/133」是 2026-08-20 的舊數字，**已過期**。
 **host 為降級環境**，其結果不得支撐任何 ML／NLP／重試／LLM 路徑的宣稱
@@ -70,6 +72,7 @@ grep -ch "def test_" tests/*.py | awk '{s+=$1} END {print s}'
 | 4 | `doc/upgrade/gates/closed/` 缺 `.gitkeep` | git 不追蹤空目錄，新 clone 後 `CLAUDE.md` §16.3 的歸檔規則會指向不存在的目錄 |
 | 5 | 「24 個 Small Batch」硬編碼於 `doc/README.md` 與 `CLAUDE.md` §16.3 | 該數字的唯一權威來源是 `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`；複製一份即為下一個 DRIFT |
 | 6 | 本文件 §1–§15 的 PRE_CODEX 舊內容未改寫 | 與現行升級專案的關係見 §0 開頭的編號警告 |
+| 7 | `CLAUDE.md` §16.3【強制】：SB 通過 Gate B 後，提案文件應移入 `doc/upgrade/gates/closed/` | SB1 結案（2026-08-25）後尚未執行此搬移（`SB1_GATE_A_PROPOSAL.md`、`SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、`SB1_GATE_B_SUBMISSION.md` 四份仍在 `gates/` 根層）；搬移屬 git 異動，需另行取得 commit 授權，本次未逕行執行。與義務 4（`closed/` 缺 `.gitkeep`）為同一批工作 |
 
 ### 0.6 新對話的入口路徑
 
diff --git a/src/ui/charts.py b/src/ui/charts.py
index 9c73fe0..cbadf6c 100644
--- a/src/ui/charts.py
+++ b/src/ui/charts.py
@@ -5,9 +5,17 @@ import numpy as np
 import pandas as pd
 
 from .styles import get_market_colors, COLOR_TAIWAN_UP, COLOR_TAIWAN_DOWN
+from .data_loader import DataMode
 
 logger = logging.getLogger(__name__)
 
+# DataMode 非 REAL 時的圖表浮水印／佔位文案 (icon, 說明文字, 強調色)
+_CHART_MODE_ANNOTATION: Dict[DataMode, Tuple[str, str, str]] = {
+    DataMode.ERROR: ("⚠️", "資料來源目前無法連線", "#FF5252"),
+    DataMode.EMPTY: ("💡", "目前查無相關資料", "#FFA726"),
+    DataMode.DEMO: ("🧪 示範資料 DEMO", "並非即時真實數據", "#2962FF"),
+}
+
 
 class _FallbackPlotlyFigure:
     """輕量 Plotly 圖表物件 Fallback (供無 plotly 之輕量測試環境安全執行)"""
@@ -25,20 +33,68 @@ class _FallbackPlotlyFigure:
     def update_yaxes(self, **kwargs: Any) -> "_FallbackPlotlyFigure":
         return self
 
+    def add_annotation(self, **kwargs: Any) -> "_FallbackPlotlyFigure":
+        self.layout.setdefault("annotations", []).append(kwargs)
+        return self
+
     def to_dict(self) -> Dict[str, Any]:
         return {"data": self.data, "layout": self.layout}
 
 
+def _placeholder_figure(mode: DataMode, height: int = 320) -> Any:
+    """ERROR／EMPTY 狀態的佔位圖表：不畫任何數值，只顯示狀態說明。"""
+    icon, text, color = _CHART_MODE_ANNOTATION[mode]
+    try:
+        import plotly.graph_objects as go
+        fig = go.Figure()
+        fig.update_layout(
+            template="plotly_dark",
+            paper_bgcolor="#1E222D",
+            plot_bgcolor="#1E222D",
+            height=height,
+            xaxis=dict(visible=False),
+            yaxis=dict(visible=False),
+        )
+        fig.add_annotation(
+            text=f"{icon} {text}",
+            xref="paper", yref="paper", x=0.5, y=0.5,
+            showarrow=False,
+            font=dict(size=16, color=color),
+        )
+        return fig
+    except ImportError:
+        return _FallbackPlotlyFigure(data=[], layout={"placeholder": text, "mode": mode.value})
+
+
+def _apply_demo_watermark(fig: Any) -> Any:
+    """DEMO 狀態：正常繪圖後疊加醒目浮水印標註，圖表本身照常顯示。"""
+    icon_text, sub_text, color = _CHART_MODE_ANNOTATION[DataMode.DEMO]
+    fig.add_annotation(
+        text=f"{icon_text}<br><span style='font-size:11px'>{sub_text}</span>",
+        xref="paper", yref="paper", x=0.5, y=0.5,
+        showarrow=False,
+        font=dict(size=22, color=color),
+        opacity=0.35,
+    )
+    return fig
+
+
 def render_price_sentiment_candlestick_chart(
     df: pd.DataFrame,
     stock_title: str = "2330 台積電",
-    market: str = "TW"
+    market: str = "TW",
+    mode: DataMode = DataMode.REAL,
 ) -> Any:
     """
     繪製機構級多維雙 Y 軸互動圖表：
     - 上層 (70% 高度)：日 K 線 (Candlestick) + MA5 (週線) + MA20 (月線)
     - 下層 (30% 高度)：社群情緒指數長條圖 (Sentiment Mean / Antweiler Bt) + 成交量
+
+    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
     """
+    if mode in (DataMode.ERROR, DataMode.EMPTY):
+        return _placeholder_figure(mode, height=580)
+
     colors = get_market_colors(market)
     up_color = colors["up"]
     down_color = colors["down"]
@@ -116,19 +172,32 @@ def render_price_sentiment_candlestick_chart(
         )
         fig.update_xaxes(showgrid=True, gridcolor="#2B313F", zeroline=False)
         fig.update_yaxes(showgrid=True, gridcolor="#2B313F", zeroline=False)
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
         return fig
 
     except ImportError:
-        return _FallbackPlotlyFigure(
+        fig = _FallbackPlotlyFigure(
             data=[{"type": "candlestick", "stock": stock_title}],
             layout={"title": stock_title, "market": market}
         )
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
+        return fig
 
 
-def render_pnl_equity_curve_chart(df: pd.DataFrame, market: str = "TW") -> Any:
+def render_pnl_equity_curve_chart(
+    df: pd.DataFrame,
+    market: str = "TW",
+    mode: DataMode = DataMode.REAL,
+) -> Any:
     """
     繪製模擬量化策略累積報酬率曲線 (AI Multi-Modal Strategy vs. Buy & Hold Benchmark)。
+    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
     """
+    if mode in (DataMode.ERROR, DataMode.EMPTY):
+        return _placeholder_figure(mode, height=320)
+
     try:
         import plotly.graph_objects as go
 
@@ -179,22 +248,32 @@ def render_pnl_equity_curve_chart(df: pd.DataFrame, market: str = "TW") -> Any:
             yaxis=dict(title="累積報酬率 (%)", showgrid=True, gridcolor="#2B313F"),
             xaxis=dict(showgrid=True, gridcolor="#2B313F")
         )
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
         return fig
 
     except ImportError:
-        return _FallbackPlotlyFigure(
+        fig = _FallbackPlotlyFigure(
             data=[{"type": "equity_curve"}],
             layout={"title": "Cumulative Strategy Return"}
         )
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
+        return fig
 
 
 def render_feature_importance_bar_chart(
     importances: Dict[str, float],
-    top_n: int = 8
+    top_n: int = 8,
+    mode: DataMode = DataMode.REAL,
 ) -> Any:
     """
     繪製模型 Top N 關鍵特徵重要性長條圖。
+    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
     """
+    if mode in (DataMode.ERROR, DataMode.EMPTY):
+        return _placeholder_figure(mode, height=320)
+
     try:
         import plotly.graph_objects as go
 
@@ -236,10 +315,15 @@ def render_feature_importance_bar_chart(
             xaxis=dict(title="重要性權重 (%)", showgrid=True, gridcolor="#2B313F"),
             yaxis=dict(showgrid=False)
         )
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
         return fig
 
     except ImportError:
-        return _FallbackPlotlyFigure(
+        fig = _FallbackPlotlyFigure(
             data=[{"type": "feature_importance"}],
             layout={"top_n": top_n}
         )
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
+        return fig
diff --git a/src/ui/components.py b/src/ui/components.py
index e269430..c88ccf8 100644
--- a/src/ui/components.py
+++ b/src/ui/components.py
@@ -5,6 +5,7 @@ import numpy as np
 import pandas as pd
 
 from .styles import get_market_colors
+from .data_loader import DataMode
 
 logger = logging.getLogger(__name__)
 
@@ -63,10 +64,55 @@ FEATURE_DISPLAY_NAMES: Dict[str, str] = {
 }
 
 
-def render_prediction_panel(prediction_result: Dict[str, Any], market: str = "TW") -> None:
+# DataMode 非 REAL 時的橫幅文案 (icon, 說明文字, 強調色)
+_MODE_BANNER: Dict[DataMode, Tuple[str, str, str]] = {
+    DataMode.ERROR: ("⚠️", "資料來源目前無法連線，以下不顯示任何推算數值", "#FF5252"),
+    DataMode.EMPTY: ("💡", "資料庫連線正常，但目前查無相關資料", "#FFA726"),
+    DataMode.DEMO: ("🧪", "目前顯示離線示範資料，並非即時真實數據", "#2962FF"),
+}
+
+
+def render_data_mode_banner(mode: DataMode, context_label: str = "") -> None:
+    """
+    渲染 DataMode 狀態橫幅。REAL 時不渲染任何內容（no-op）。
+    ERROR／EMPTY／DEMO 三態使用統一視覺語彙，供各元件呼叫，避免各自維護重複文案。
+    """
+    if mode == DataMode.REAL:
+        return
+    icon, text, color = _MODE_BANNER[mode]
+    suffix = f"（{context_label}）" if context_label else ""
+    st.markdown(
+        f"""
+        <div style="background-color: #1E222D; border: 1px solid {color}; border-radius: 8px;
+                    padding: 10px 16px; margin-bottom: 10px; font-size: 13px; color: {color};">
+            {icon} <b>{text}{suffix}</b>
+        </div>
+        """,
+        unsafe_allow_html=True
+    )
+
+
+def render_prediction_panel(
+    prediction_result: Optional[Dict[str, Any]],
+    market: str = "TW",
+    mode: DataMode = DataMode.REAL,
+) -> None:
     """
     渲染 AI 即時預測決策面板與 Top 3 驅動因子解析。
+    mode 非 REAL／DEMO 時（ERROR／EMPTY），prediction_result 應為 None，僅渲染狀態橫幅，
+    不渲染任何預測數值（DEC-012 方案 B）。
     """
+    st.markdown("### 🤖 AI 智能趨勢決策與可解釋性面板")
+
+    if prediction_result is None:
+        # 防禦性保護：呼叫端未依 mode 提供 prediction_result 時一律視為無法顯示
+        render_data_mode_banner(mode if mode != DataMode.REAL else DataMode.ERROR, "AI 預測面板")
+        return
+    if mode in (DataMode.ERROR, DataMode.EMPTY):
+        render_data_mode_banner(mode, "AI 預測面板")
+        return
+
+    render_data_mode_banner(mode, "AI 預測面板")
     colors = get_market_colors(market)
     is_up = prediction_result.get("predicted_direction", "UP") == "UP"
     dir_color = colors["up"] if is_up else colors["down"]
@@ -74,8 +120,6 @@ def render_prediction_panel(prediction_result: Dict[str, Any], market: str = "TW
     conf = float(prediction_result.get("confidence_score", 0.5))
     model_name = str(prediction_result.get("model_name", "random_forest")).upper()
 
-    st.markdown("### 🤖 AI 智能趨勢決策與可解釋性面板")
-    
     col_pred, col_conf = st.columns([1, 2])
     with col_pred:
         st.markdown(
@@ -140,12 +184,22 @@ def render_tournament_leaderboard() -> None:
     st.dataframe(df_lb, use_container_width=True, hide_index=True)
 
 
-def render_raw_article_table(df_articles: pd.DataFrame) -> None:
+def render_raw_article_table(df_articles: pd.DataFrame, mode: DataMode = DataMode.REAL) -> None:
     """
     渲染 PTT 原始輿情文章明細表格（支援多維篩選、即時搜尋與透明化空狀態展示）。
+    mode=ERROR 時僅渲染連線失敗橫幅，不嘗試渲染表格（df_articles 預期為空）。
+    mode=EMPTY 時沿用既有的「查無文章」空狀態說明（比 ERROR 更精確：DB 連線正常，只是真的沒有）。
+    mode=DEMO 時渲染示範資料橫幅後正常渲染表格。
     """
     st.markdown("### 📰 PTT 股市版社群輿情明細 (Raw Sentiment Articles)")
 
+    if mode == DataMode.ERROR:
+        render_data_mode_banner(mode, "PTT 輿情明細")
+        return
+
+    if mode == DataMode.DEMO:
+        render_data_mode_banner(mode, "PTT 輿情明細")
+
     if df_articles is None or df_articles.empty:
         st.markdown(
             """
@@ -216,13 +270,24 @@ def render_raw_article_table(df_articles: pd.DataFrame) -> None:
     )
 
 
-def render_ai_trend_discovery_badge(keywords: List[str]) -> None:
+def render_ai_trend_discovery_badge(keywords: List[str], mode: DataMode = DataMode.REAL) -> None:
     """
     渲染 AI 今日市場熱搜探索詞 (AI Trend Discovery) 視覺化卡片。
+    mode=ERROR 時渲染連線失敗橫幅並停止（keywords 預期為空）。
+    mode=EMPTY 時安靜跳過（DB 連線正常但目前無探索詞，非錯誤，維持既有低干擾行為）。
     """
-    if not keywords:
+    if mode == DataMode.ERROR:
+        render_data_mode_banner(mode, "AI 熱門題材探索")
+        return
+    if mode == DataMode.EMPTY or not keywords:
         return
 
+    if mode == DataMode.DEMO:
+        render_data_mode_banner(mode, "AI 熱門題材探索")
+
+    status_text = "● 實時探索中" if mode == DataMode.REAL else "● 離線示範"
+    status_color = "#00C853" if mode == DataMode.REAL else "#2962FF"
+
     badges_html = " ".join([
         f'<span style="display: inline-block; background: linear-gradient(135deg, rgba(255, 75, 75, 0.2), rgba(255, 140, 0, 0.2)); border: 1px solid #FF8C00; color: #FFA726; padding: 4px 10px; border-radius: 14px; font-size: 12px; font-weight: 600; margin: 4px 4px 4px 0;">🔥 {kw}</span>'
         for kw in keywords
@@ -233,7 +298,7 @@ def render_ai_trend_discovery_badge(keywords: List[str]) -> None:
         <div style="background-color: #1E222D; border: 1px solid #2B313F; border-radius: 10px; padding: 14px 18px; margin-bottom: 15px;">
             <div style="font-size: 13px; color: #848E9C; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                 <span>🤖 <b>AI 自動挖掘市場熱門題材詞</b> (Trend Discovery)</span>
-                <span style="font-size: 11px; color: #00C853;">● 實時探索中</span>
+                <span style="font-size: 11px; color: {status_color};">{status_text}</span>
             </div>
             <div>{badges_html}</div>
         </div>
@@ -242,16 +307,26 @@ def render_ai_trend_discovery_badge(keywords: List[str]) -> None:
     )
 
 
-def render_thematic_radar(themes_data: List[Dict[str, Any]]) -> Optional[str]:
+def render_thematic_radar(
+    themes_data: List[Dict[str, Any]],
+    mode: DataMode = DataMode.REAL,
+) -> Optional[str]:
     """
     渲染頂部「🔥 市場熱門題材雷達 (AI Thematic Concept Radar)」卡片群。
     支援點擊成分股按鈕，一鍵秒速切換選取標的。
     回傳被點擊的 stock_id (若有)，否則回傳 None。
+    mode=ERROR 時渲染連線失敗橫幅並停止（themes_data 預期為空）。
+    mode=EMPTY 時安靜跳過（DB 連線正常但目前無題材，非錯誤，維持既有低干擾行為）。
     """
-    if not themes_data:
+    if mode == DataMode.ERROR:
+        render_data_mode_banner(mode, "題材熱搜雷達")
+        return None
+    if mode == DataMode.EMPTY or not themes_data:
         return None
 
     st.markdown("### 🔥 市場熱門題材雷達 (AI Thematic Concept Radar)")
+    if mode == DataMode.DEMO:
+        render_data_mode_banner(mode, "題材熱搜雷達")
     cols = st.columns(len(themes_data))
     clicked_stock = None
 
diff --git a/src/ui/data_loader.py b/src/ui/data_loader.py
index a78186e..3087a21 100644
--- a/src/ui/data_loader.py
+++ b/src/ui/data_loader.py
@@ -1,5 +1,6 @@
 import logging
 import os
+from enum import Enum
 from typing import Any, Dict, List, Optional, Tuple
 
 import numpy as np
@@ -20,6 +21,105 @@ DEFAULT_STOCKS: Dict[str, str] = {
 }
 
 
+class DataMode(Enum):
+    """
+    UI 資料來源狀態（UG-G1-SB2, DEC-012）。
+
+    REAL  ：DB 連線成功且回傳非空資料。
+    DEMO  ：展示用模擬資料。僅在呼叫端明確傳入 demo=True 時使用，不作為 ERROR 的自動 fallback
+            （PO 2026-08-25 方案 B 決策：這是求職作品集，不以假資料撐場面）。
+    EMPTY ：DB 連線成功，查詢結果為零筆——真實的「沒有」，非模擬。
+    ERROR ：DB 連線或查詢本身失敗。對應區塊不渲染任何數值，只顯示錯誤說明。
+    """
+    REAL = "real"
+    DEMO = "demo"
+    EMPTY = "empty"
+    ERROR = "error"
+
+
+class DataSourceError(Exception):
+    """DB 連線或查詢層級失敗，供內部函式向上拋出、由公開函式轉換為 DataMode.ERROR。"""
+
+
+# 特徵矩陣欄位契約（ERROR／EMPTY 時回傳同結構的空 DataFrame，供呼叫端安全檢查 .columns）
+_STOCK_FEATURE_COLUMNS: List[str] = [
+    "trade_date", "stock_id", "open_price", "high_price", "low_price", "close_price", "volume",
+    "return_1d", "rsi_14", "volatility_5d", "volatility_20d", "article_count", "sentiment_mean",
+    "bullishness_index", "agreement_index", "sentiment_3d_ma", "sentiment_5d_ma",
+    "sentiment_lag_1", "sentiment_lag_2", "target_return_1d", "target_up_down",
+]
+
+_STOCK_ARTICLE_COLUMNS: List[str] = [
+    "publish_time", "stock_id", "title", "sentiment_score",
+    "sentiment_label", "push_count", "source", "url",
+]
+
+# DEMO 專用內容（僅在 demo=True 時使用，不再作為 ERROR 的自動 fallback）
+DEFAULT_AI_KEYWORDS: List[str] = [
+    "矽光子 (CPO)",
+    "散熱模組",
+    "CoWoS 先進封裝",
+    "GB200 伺服器",
+    "人形機器人",
+    "ASIC 客製晶片",
+]
+
+DEFAULT_THEMATIC_RADAR: List[Dict[str, Any]] = [
+    {
+        "theme": "矽光子 (CPO)",
+        "raw_theme": "矽光子",
+        "icon": "💡",
+        "article_count": 48,
+        "bullishness": 1.82,
+        "sentiment_label": "極度看好",
+        "stocks": [
+            {"stock_id": "3081", "name": "聯亞", "display": "3081 聯亞"},
+            {"stock_id": "6442", "name": "光聖", "display": "6442 光聖"},
+            {"stock_id": "2330", "name": "台積電", "display": "2330 台積電"},
+        ]
+    },
+    {
+        "theme": "散熱模組 (Thermal)",
+        "raw_theme": "散熱模組",
+        "icon": "❄️",
+        "article_count": 32,
+        "bullishness": 1.15,
+        "sentiment_label": "偏多",
+        "stocks": [
+            {"stock_id": "3324", "name": "雙鴻", "display": "3324 雙鴻"},
+            {"stock_id": "3017", "name": "奇鋐", "display": "3017 奇鋐"},
+            {"stock_id": "3653", "name": "健策", "display": "3653 健策"},
+        ]
+    },
+    {
+        "theme": "CoWoS 先進封裝",
+        "raw_theme": "CoWoS",
+        "icon": "📦",
+        "article_count": 26,
+        "bullishness": 0.94,
+        "sentiment_label": "穩定看好",
+        "stocks": [
+            {"stock_id": "3131", "name": "弘塑", "display": "3131 弘塑"},
+            {"stock_id": "3583", "name": "辛耘", "display": "3583 辛耘"},
+            {"stock_id": "2330", "name": "台積電", "display": "2330 台積電"},
+        ]
+    },
+    {
+        "theme": "AI 伺服器 (OEM)",
+        "raw_theme": "AI伺服器",
+        "icon": "🤖",
+        "article_count": 55,
+        "bullishness": 1.45,
+        "sentiment_label": "強烈偏多",
+        "stocks": [
+            {"stock_id": "2382", "name": "廣達", "display": "2382 廣達"},
+            {"stock_id": "6669", "name": "緯穎", "display": "6669 緯穎"},
+            {"stock_id": "NVDA", "name": "輝達", "display": "NVDA 輝達"},
+        ]
+    }
+]
+
+
 def get_available_stocks(custom_stocks: Optional[Dict[str, str]] = None) -> Dict[str, str]:
     """取得系統支援之股票代碼與名稱對照表 (支援使用者動態新增之自選股)"""
     stocks = dict(DEFAULT_STOCKS)
@@ -30,7 +130,7 @@ def get_available_stocks(custom_stocks: Optional[Dict[str, str]] = None) -> Dict
 
 def generate_mock_stock_features(stock_id: str, days: int = 60) -> pd.DataFrame:
     """
-    生成高仿真之 18 欄位離線特徵 DataFrame (供離線演示與 DB Fallback)。
+    生成高仿真之 18 欄位離線特徵 DataFrame。僅供 load_stock_features(demo=True) 使用。
     """
     np.random.seed(int(sum(ord(c) for c in str(stock_id))))
     end_date = pd.Timestamp.now()
@@ -99,7 +199,7 @@ def generate_mock_stock_features(stock_id: str, days: int = 60) -> pd.DataFrame:
 
 def generate_mock_ptt_articles(stock_id: str, limit: int = 20) -> pd.DataFrame:
     """
-    生成高仿真之 PTT 原始文章資料庫 (供輿情明細表展示)。
+    生成高仿真之 PTT 原始文章資料庫。僅供 load_stock_articles(demo=True) 使用。
     """
     stock_name = DEFAULT_STOCKS.get(stock_id, stock_id).split()[0]
     sample_titles = [
@@ -136,14 +236,19 @@ def generate_mock_ptt_articles(stock_id: str, limit: int = 20) -> pd.DataFrame:
 def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optional[pd.DataFrame]:
     """
     從 PostgreSQL 撈取真實股價與文章資料，並透過 FeatureAggregator 即時推導完整 18 欄位特徵矩陣。
+
+    Returns:
+        None：DB 連線與查詢皆成功，但沒有可用資料（歷史不足 2 筆、彙總後為空）。
+    Raises:
+        DataSourceError：DB 連線或查詢本身失敗。
     """
     try:
         from ..loaders.db_writer import DBWriter
         from ..transform.feature_aggregator import FeatureAggregator
-        
+
         writer = DBWriter()
         conn = psycopg2.connect(**writer.db_config)
-        
+
         # 1. 撈取真實歷史股價 (按日期遞增排序)
         price_query = """
             SELECT trade_date, stock_id, open_price, high_price, low_price, close_price, volume
@@ -152,11 +257,11 @@ def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optiona
             ORDER BY trade_date ASC;
         """
         df_prices = pd.read_sql(price_query, conn, params=(stock_id,))
-        
+
         if df_prices.empty or len(df_prices) < 2:
             conn.close()
             return None
-            
+
         # 2. 撈取該股票關聯之關鍵字
         mapping_query = """
             SELECT keyword, stock_id
@@ -167,7 +272,7 @@ def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optiona
         if df_mapping.empty:
             df_mapping = pd.DataFrame({"keyword": [stock_id], "stock_id": [stock_id]})
         keywords = df_mapping['keyword'].tolist()
-            
+
         # 3. 撈取所屬題材映射
         theme_query = """
             SELECT theme_keyword, stock_id, relevance_weight
@@ -189,9 +294,9 @@ def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optiona
             df_articles = pd.read_sql(articles_query, conn, params=(tuple(all_keywords),))
         else:
             df_articles = pd.DataFrame()
-            
+
         conn.close()
-        
+
         # 5. 透過 FeatureAggregator 向量化運算生成 18 欄位完整特徵 (支援題材情緒溢出加權)
         aggregator = FeatureAggregator()
         df_features = aggregator.generate_daily_features(
@@ -199,21 +304,23 @@ def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optiona
         )
         if df_features.empty:
             return None
-            
+
         # 5. 生成目標標籤 target_return_1d / target_up_down
         df_features = aggregator.generate_target_labels(df_features)
-        
+
         # 日期轉型為字串 YYYY-MM-DD
         df_features['trade_date'] = pd.to_datetime(df_features['trade_date']).dt.strftime('%Y-%m-%d')
-        
+
         # 僅保留最近 days 天
         if len(df_features) > days:
             df_features = df_features.iloc[-days:].reset_index(drop=True)
-            
+
         return df_features
+    except DataSourceError:
+        raise
     except Exception as e:
-        logger.debug(f"PostgreSQL 特徵讀取異常，啟用離線 Fallback: {e}")
-        return None
+        logger.warning(f"PostgreSQL 特徵讀取異常: {e}")
+        raise DataSourceError(str(e)) from e
 
 
 def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Optional[pd.DataFrame]:
@@ -223,12 +330,17 @@ def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Option
     1. Entity Mapping 個股關鍵字 (如 2330 ➔ 台積電)
     2. Thematic Mapping 所屬題材關鍵字 (如 3081 ➔ 矽光子, 3324 ➔ 散熱模組)
     3. 標題全域模糊比對 (title ILIKE %stock_id% OR title ILIKE %stock_name%)
+
+    Returns:
+        符合欄位契約的 DataFrame（可能為空，代表 DB 成功但無相關文章）。
+    Raises:
+        DataSourceError：DB 連線或查詢本身失敗。
     """
     try:
         from ..loaders.db_writer import DBWriter
         writer = DBWriter()
         conn = psycopg2.connect(**writer.db_config)
-        
+
         # 1. 撈取個股關鍵字
         mapping_query = "SELECT keyword FROM entity_mapping WHERE stock_id = %s;"
         with conn.cursor() as cur:
@@ -246,18 +358,18 @@ def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Option
                     theme_keywords.append(r[0])
                 if r[1]:
                     stock_names.append(r[1])
-            
+
         all_keywords = list(set(keywords + theme_keywords + [stock_id]))
         stock_name_pattern = f"%{stock_names[0]}%" if stock_names else f"%{stock_id}%"
         stock_id_pattern = f"%{stock_id}%"
 
         articles_query = """
-            SELECT 
+            SELECT
                 TO_CHAR(post_time, 'YYYY-MM-DD HH24:MI') AS publish_time,
                 %s AS stock_id,
                 title,
                 ROUND(COALESCE(sentiment_score, 0.5)::numeric, 3) AS sentiment_score,
-                CASE 
+                CASE
                     WHEN sentiment_score >= 0.6 THEN '看多'
                     WHEN sentiment_score <= 0.4 THEN '看空'
                     ELSE '中立'
@@ -273,141 +385,119 @@ def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Option
             LIMIT %s;
         """
         df_arts = pd.read_sql(
-            articles_query, 
-            conn, 
+            articles_query,
+            conn,
             params=(stock_id, tuple(all_keywords), stock_id_pattern, stock_name_pattern, limit)
         )
         conn.close()
-        
+
         if df_arts.empty:
-            return pd.DataFrame(columns=[
-                'publish_time', 'stock_id', 'title', 'sentiment_score', 
-                'sentiment_label', 'push_count', 'source', 'url'
-            ])
+            return pd.DataFrame(columns=_STOCK_ARTICLE_COLUMNS)
         # 去重
         df_arts = df_arts.drop_duplicates(subset=['title', 'publish_time']).reset_index(drop=True)
         return df_arts
+    except DataSourceError:
+        raise
     except Exception as e:
-        logger.debug(f"PostgreSQL 文章讀取異常: {e}")
-        return None
+        logger.warning(f"PostgreSQL 文章讀取異常: {e}")
+        raise DataSourceError(str(e)) from e
 
 
-def load_stock_features(stock_id: str, days: int = 60) -> pd.DataFrame:
+def load_stock_features(stock_id: str, days: int = 60, demo: bool = False) -> Tuple[pd.DataFrame, DataMode]:
     """
-    載入指定股票之特徵矩陣 (優先嘗試 DB，失敗或無資料時自動平滑回退離線 Mock)。
+    載入指定股票之特徵矩陣。
+
+    Args:
+        demo: True 時直接回傳離線模擬資料（DataMode.DEMO），不嘗試連線 DB。
+            預設 False：DB 連線失敗回傳空特徵矩陣與 DataMode.ERROR（不自動退回模擬資料，
+            DEC-012 方案 B）；DB 連線成功但無資料回傳 DataMode.EMPTY；成功且有資料回傳 DataMode.REAL。
+
+    Returns:
+        (DataFrame, DataMode) 元組。ERROR／EMPTY 時 DataFrame 為符合欄位契約的空表。
     """
-    df_real = _fetch_real_stock_features_from_db(stock_id, days=days)
-    if df_real is not None and not df_real.empty:
-        return df_real
-    return generate_mock_stock_features(stock_id, days=days)
+    if demo:
+        return generate_mock_stock_features(stock_id, days=days), DataMode.DEMO
+
+    try:
+        df_real = _fetch_real_stock_features_from_db(stock_id, days=days)
+    except DataSourceError as e:
+        logger.warning(f"[DataMode.ERROR] load_stock_features({stock_id}): {e}")
+        return pd.DataFrame(columns=_STOCK_FEATURE_COLUMNS), DataMode.ERROR
 
+    if df_real is None or df_real.empty:
+        return pd.DataFrame(columns=_STOCK_FEATURE_COLUMNS), DataMode.EMPTY
+    return df_real, DataMode.REAL
 
-def load_stock_articles(stock_id: str, limit: int = 20) -> pd.DataFrame:
+
+def load_stock_articles(stock_id: str, limit: int = 20, demo: bool = False) -> Tuple[pd.DataFrame, DataMode]:
     """
-    載入指定股票之真實 PTT 文章明細 (優先嘗試 DB，查無資料或連線異常時回傳標準空 DataFrame，落實資料透明度)。
+    載入指定股票之真實 PTT 文章明細。
+
+    Args:
+        demo: True 時直接回傳離線模擬文章（DataMode.DEMO）。
+            預設 False：DB 連線失敗回傳空表與 DataMode.ERROR；查無資料回傳 DataMode.EMPTY；
+            成功且有資料回傳 DataMode.REAL。
     """
-    df_real = _fetch_real_stock_articles_from_db(stock_id, limit=limit)
-    if df_real is not None:
-        return df_real
-    return pd.DataFrame(columns=[
-        'publish_time', 'stock_id', 'title', 'sentiment_score', 
-        'sentiment_label', 'push_count', 'source', 'url'
-    ])
+    if demo:
+        return generate_mock_ptt_articles(stock_id, limit=limit), DataMode.DEMO
+
+    try:
+        df_real = _fetch_real_stock_articles_from_db(stock_id, limit=limit)
+    except DataSourceError as e:
+        logger.warning(f"[DataMode.ERROR] load_stock_articles({stock_id}): {e}")
+        return pd.DataFrame(columns=_STOCK_ARTICLE_COLUMNS), DataMode.ERROR
+
+    if df_real is None or df_real.empty:
+        return pd.DataFrame(columns=_STOCK_ARTICLE_COLUMNS), DataMode.EMPTY
+    return df_real, DataMode.REAL
 
 
 def get_champion_predictor(df_features: pd.DataFrame) -> StockTrendPredictor:
     """
     以當前特徵矩陣快速擬合冠軍隨機森林模型，並回傳即時推論引擎。
+    呼叫端須確保 df_features 來自 DataMode.REAL 或 DataMode.DEMO（非空、具備完整欄位）。
     """
     trainer = MultiModalTrainer(model_name="random_forest", scaler_type="robust", random_state=42)
     trainer.train_and_predict_fold(df_features, df_features)
     return StockTrendPredictor(trainer=trainer)
 
 
-def load_ai_discovered_keywords(limit: int = 6) -> List[str]:
+def load_ai_discovered_keywords(limit: int = 6, demo: bool = False) -> Tuple[List[str], DataMode]:
     """
     載入由 AI (trend_discover.py) 探索之最新市場熱門關鍵字。
-    優先嘗試從 PostgreSQL 撈取，失敗時自動平滑回退精選熱門題材詞。
+
+    Args:
+        demo: True 時直接回傳精選展示詞（DataMode.DEMO）。
+            預設 False：DB 連線失敗回傳空清單與 DataMode.ERROR；查無資料回傳 DataMode.EMPTY；
+            成功且有資料回傳 DataMode.REAL。
     """
-    default_ai_keywords = [
-        "矽光子 (CPO)",
-        "散熱模組",
-        "CoWoS 先進封裝",
-        "GB200 伺服器",
-        "人形機器人",
-        "ASIC 客製晶片",
-    ]
+    if demo:
+        return list(DEFAULT_AI_KEYWORDS), DataMode.DEMO
+
     try:
         from ..loaders.db_writer import DBWriter
         writer = DBWriter()
         keywords = writer.fetch_ai_discovered_keywords(limit=limit)
-        if keywords:
-            return keywords
-        return default_ai_keywords
     except Exception as e:
-        logger.debug(f"AI 關鍵字 DB 讀取異常，啟用 Fallback: {e}")
-        return default_ai_keywords
+        logger.warning(f"[DataMode.ERROR] load_ai_discovered_keywords: {e}")
+        return [], DataMode.ERROR
 
+    if not keywords:
+        return [], DataMode.EMPTY
+    return keywords, DataMode.REAL
 
-def load_thematic_radar_data() -> List[Dict[str, Any]]:
+
+def load_thematic_radar_data(demo: bool = False) -> Tuple[List[Dict[str, Any]], DataMode]:
     """
     載入題材熱搜雷達數據 (包含題材名稱、討論聲量、看多指數、情緒評級與成分股清單)。
-    優先嘗試從 PostgreSQL 撈取真實統計，失敗或無資料時自動平滑回退精選高仿真題材雷達。
+
+    Args:
+        demo: True 時直接回傳精選展示題材（DataMode.DEMO）。
+            預設 False：DB 連線失敗回傳空清單與 DataMode.ERROR；查無資料回傳 DataMode.EMPTY；
+            成功且有資料回傳 DataMode.REAL。
     """
-    default_radar = [
-        {
-            "theme": "矽光子 (CPO)",
-            "raw_theme": "矽光子",
-            "icon": "💡",
-            "article_count": 48,
-            "bullishness": 1.82,
-            "sentiment_label": "極度看好",
-            "stocks": [
-                {"stock_id": "3081", "name": "聯亞", "display": "3081 聯亞"},
-                {"stock_id": "6442", "name": "光聖", "display": "6442 光聖"},
-                {"stock_id": "2330", "name": "台積電", "display": "2330 台積電"},
-            ]
-        },
-        {
-            "theme": "散熱模組 (Thermal)",
-            "raw_theme": "散熱模組",
-            "icon": "❄️",
-            "article_count": 32,
-            "bullishness": 1.15,
-            "sentiment_label": "偏多",
-            "stocks": [
-                {"stock_id": "3324", "name": "雙鴻", "display": "3324 雙鴻"},
-                {"stock_id": "3017", "name": "奇鋐", "display": "3017 奇鋐"},
-                {"stock_id": "3653", "name": "健策", "display": "3653 健策"},
-            ]
-        },
-        {
-            "theme": "CoWoS 先進封裝",
-            "raw_theme": "CoWoS",
-            "icon": "📦",
-            "article_count": 26,
-            "bullishness": 0.94,
-            "sentiment_label": "穩定看好",
-            "stocks": [
-                {"stock_id": "3131", "name": "弘塑", "display": "3131 弘塑"},
-                {"stock_id": "3583", "name": "辛耘", "display": "3583 辛耘"},
-                {"stock_id": "2330", "name": "台積電", "display": "2330 台積電"},
-            ]
-        },
-        {
-            "theme": "AI 伺服器 (OEM)",
-            "raw_theme": "AI伺服器",
-            "icon": "🤖",
-            "article_count": 55,
-            "bullishness": 1.45,
-            "sentiment_label": "強烈偏多",
-            "stocks": [
-                {"stock_id": "2382", "name": "廣達", "display": "2382 廣達"},
-                {"stock_id": "6669", "name": "緯穎", "display": "6669 緯穎"},
-                {"stock_id": "NVDA", "name": "輝達", "display": "NVDA 輝達"},
-            ]
-        }
-    ]
+    if demo:
+        return list(DEFAULT_THEMATIC_RADAR), DataMode.DEMO
 
     try:
         from ..loaders.db_writer import DBWriter
@@ -415,7 +505,7 @@ def load_thematic_radar_data() -> List[Dict[str, Any]]:
 
         writer = DBWriter()
         conn = psycopg2.connect(**writer.db_config)
-        
+
         # 1. 撈取所有題材成分股
         mapping_query = """
             SELECT theme_keyword, stock_id, stock_name, relevance_weight
@@ -425,7 +515,7 @@ def load_thematic_radar_data() -> List[Dict[str, Any]]:
         df_mappings = pd.read_sql(mapping_query, conn)
         if df_mappings.empty:
             conn.close()
-            return default_radar
+            return [], DataMode.EMPTY
 
         # 2. 撈取題材文章統計
         theme_names = tuple(df_mappings['theme_keyword'].unique())
@@ -440,63 +530,64 @@ def load_thematic_radar_data() -> List[Dict[str, Any]]:
         """
         df_stats = pd.read_sql(arts_query, conn, params=(theme_names,))
         conn.close()
-
-        stats_dict = {}
-        if not df_stats.empty:
-            for _, r in df_stats.iterrows():
-                stats_dict[r['fetch_keyword']] = {
-                    'count': int(r['article_count']),
-                    'pos': int(r['pos_cnt']),
-                    'neg': int(r['neg_cnt'])
-                }
-
-        radar_list = []
-        theme_icons = {
-            "矽光子": "💡",
-            "散熱模組": "❄️",
-            "CoWoS": "📦",
-            "AI伺服器": "🤖"
-        }
-
-        for theme, group in df_mappings.groupby('theme_keyword'):
-            s_info = stats_dict.get(theme, {'count': 0, 'pos': 0, 'neg': 0})
-            cnt = s_info['count']
-            if cnt > 0:
-                b_val = float(compute_bullishness_index(pd.Series([s_info['pos']]), pd.Series([s_info['neg']])).iloc[0])
-            else:
-                b_val = 0.85
-
-            if b_val >= 1.0:
-                lbl = "極度看好"
-            elif b_val >= 0.3:
-                lbl = "偏多"
-            elif b_val <= -0.5:
-                lbl = "偏空"
-            else:
-                lbl = "穩定"
-
-            stocks_list = []
-            for _, row in group.iterrows():
-                s_id = str(row['stock_id'])
-                s_name = str(row['stock_name']) if pd.notnull(row['stock_name']) else s_id
-                stocks_list.append({
-                    "stock_id": s_id,
-                    "name": s_name,
-                    "display": f"{s_id} {s_name}"
-                })
-
-            radar_list.append({
-                "theme": f"{theme}",
-                "raw_theme": theme,
-                "icon": theme_icons.get(theme, "🔥"),
-                "article_count": cnt if cnt > 0 else len(group) * 8,
-                "bullishness": b_val,
-                "sentiment_label": lbl,
-                "stocks": stocks_list[:3] # 每題材展示前 3 檔核心
+    except Exception as e:
+        logger.warning(f"[DataMode.ERROR] load_thematic_radar_data: {e}")
+        return [], DataMode.ERROR
+
+    stats_dict = {}
+    if not df_stats.empty:
+        for _, r in df_stats.iterrows():
+            stats_dict[r['fetch_keyword']] = {
+                'count': int(r['article_count']),
+                'pos': int(r['pos_cnt']),
+                'neg': int(r['neg_cnt'])
+            }
+
+    radar_list = []
+    theme_icons = {
+        "矽光子": "💡",
+        "散熱模組": "❄️",
+        "CoWoS": "📦",
+        "AI伺服器": "🤖"
+    }
+
+    for theme, group in df_mappings.groupby('theme_keyword'):
+        s_info = stats_dict.get(theme, {'count': 0, 'pos': 0, 'neg': 0})
+        cnt = s_info['count']
+        if cnt > 0:
+            b_val = float(compute_bullishness_index(pd.Series([s_info['pos']]), pd.Series([s_info['neg']])).iloc[0])
+        else:
+            b_val = 0.85
+
+        if b_val >= 1.0:
+            lbl = "極度看好"
+        elif b_val >= 0.3:
+            lbl = "偏多"
+        elif b_val <= -0.5:
+            lbl = "偏空"
+        else:
+            lbl = "穩定"
+
+        stocks_list = []
+        for _, row in group.iterrows():
+            s_id = str(row['stock_id'])
+            s_name = str(row['stock_name']) if pd.notnull(row['stock_name']) else s_id
+            stocks_list.append({
+                "stock_id": s_id,
+                "name": s_name,
+                "display": f"{s_id} {s_name}"
             })
 
-        return radar_list if radar_list else default_radar
-    except Exception as e:
-        logger.debug(f"題材雷達 DB 讀取異常，啟用 Fallback: {e}")
-        return default_radar
+        radar_list.append({
+            "theme": f"{theme}",
+            "raw_theme": theme,
+            "icon": theme_icons.get(theme, "🔥"),
+            "article_count": cnt if cnt > 0 else len(group) * 8,
+            "bullishness": b_val,
+            "sentiment_label": lbl,
+            "stocks": stocks_list[:3]  # 每題材展示前 3 檔核心
+        })
 
+    if not radar_list:
+        return [], DataMode.EMPTY
+    return radar_list, DataMode.REAL
diff --git a/tests/test_operational_ux.py b/tests/test_operational_ux.py
index a724df0..2b57a86 100644
--- a/tests/test_operational_ux.py
+++ b/tests/test_operational_ux.py
@@ -3,7 +3,7 @@ from datetime import datetime
 from unittest.mock import MagicMock, patch
 
 from scheduler import is_trading_weekday, get_next_run_time, TARGET_HOUR, TARGET_MINUTE
-from src.ui.data_loader import get_available_stocks, load_ai_discovered_keywords
+from src.ui.data_loader import get_available_stocks, load_ai_discovered_keywords, DataMode
 from src.ui.components import render_ai_trend_discovery_badge
 from main_etl_pipeline import ETLPipelineManager
 
@@ -70,14 +70,53 @@ class CustomStockAndTrendDiscoveryUITests(unittest.TestCase):
         self.assertIn("2330", all_stocks)
         self.assertEqual(all_stocks["2454"], "聯發科 (2454)")
 
-    def test_load_ai_discovered_keywords_fallback(self):
-        keywords = load_ai_discovered_keywords(limit=6)
+    def test_load_ai_discovered_keywords_returns_real_mode_when_db_has_data(self):
+        """
+        HERM-01／HERM-B 修復：mock DBWriter 使測試真正命中 REAL 路徑（有真實資料）。
+        原測試名稱宣稱測 fallback，但未 mock 時測到的路徑隨環境而定——若 DB 剛好有資料，
+        測到的根本不是 fallback。拆成本測試（REAL）與下一個測試（ERROR fallback），
+        兩者都是確定性的。
+        """
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
+            mock_writer_cls.return_value.fetch_ai_discovered_keywords.return_value = ["矽光子", "散熱模組"]
+            keywords, mode = load_ai_discovered_keywords(limit=6)
+
+        self.assertEqual(mode, DataMode.REAL)
+        self.assertEqual(keywords, ["矽光子", "散熱模組"])
+
+    def test_load_ai_discovered_keywords_falls_back_when_db_fails(self):
+        """
+        HERM-01／HERM-B 修復：mock DBWriter 拋出例外，確定性地測到 fallback 路徑本身。
+        DEC-012 方案 B：ERROR 不自動退回展示詞，回傳空清單與 DataMode.ERROR。
+        """
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
+            mock_writer_cls.return_value.fetch_ai_discovered_keywords.side_effect = ConnectionError("db down")
+            keywords, mode = load_ai_discovered_keywords(limit=6)
+
+        self.assertEqual(mode, DataMode.ERROR)
+        self.assertEqual(keywords, [])
+
+    def test_load_ai_discovered_keywords_empty_result_is_empty_mode(self):
+        """DB 連線成功但查無關鍵字時，回傳 DataMode.EMPTY，與 ERROR 明確區分。"""
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
+            mock_writer_cls.return_value.fetch_ai_discovered_keywords.return_value = []
+            keywords, mode = load_ai_discovered_keywords(limit=6)
+
+        self.assertEqual(mode, DataMode.EMPTY)
+        self.assertEqual(keywords, [])
+
+    def test_load_ai_discovered_keywords_demo_mode_bypasses_db(self):
+        """demo=True 是 DataMode.DEMO 的唯一合法入口，完全不觸及 DBWriter。"""
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls:
+            keywords, mode = load_ai_discovered_keywords(limit=6, demo=True)
+            mock_writer_cls.assert_not_called()
+
+        self.assertEqual(mode, DataMode.DEMO)
         self.assertGreaterEqual(len(keywords), 1)
-        self.assertTrue(any("矽光子" in k or "散熱" in k or len(k) > 0 for k in keywords))
 
     def test_render_ai_trend_discovery_badge(self):
         # 驗證在輕量環境下安全調用無異常
-        render_ai_trend_discovery_badge(["矽光子", "散熱模組", "CoWoS"])
+        render_ai_trend_discovery_badge(["矽光子", "散熱模組", "CoWoS"], mode=DataMode.REAL)
 
 
 class DynamicPipelineUnitTests(unittest.TestCase):
diff --git a/tests/test_real_articles_pipeline.py b/tests/test_real_articles_pipeline.py
index 3fb3775..0a2b81f 100644
--- a/tests/test_real_articles_pipeline.py
+++ b/tests/test_real_articles_pipeline.py
@@ -6,7 +6,7 @@ import unittest
 from unittest.mock import patch, MagicMock
 import pandas as pd
 
-from src.ui.data_loader import _fetch_real_stock_articles_from_db, load_stock_articles
+from src.ui.data_loader import _fetch_real_stock_articles_from_db, load_stock_articles, DataMode
 
 
 class RealArticlesPipelineTests(unittest.TestCase):
@@ -126,8 +126,32 @@ class RealArticlesPipelineTests(unittest.TestCase):
             self.assertEqual(len(df_res), 1)
 
     def test_load_stock_articles_returns_clean_contract(self):
-        """測試 load_stock_articles 公開介面在任何情境下均回傳符合規範之 DataFrame"""
-        df_articles = load_stock_articles("2330", limit=10)
+        """
+        HERM-02 修復：測試 load_stock_articles 公開介面（含 DataMode）在 REAL 模式下
+        回傳符合規範之 DataFrame。mock DB 使結果具確定性，不依賴真實 DB 內容。
+        """
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect") as mock_connect, \
+             patch("pandas.read_sql") as mock_read_sql:
+            mock_writer = mock_writer_cls.return_value
+            mock_writer.db_config = {"database": "test", "user": "u", "password": "p"}
+            mock_conn = mock_connect.return_value
+            mock_cur = mock_conn.cursor.return_value.__enter__.return_value
+            mock_cur.fetchall.side_effect = [[("台積電",)], [("CoWoS", "台積電")]]
+            mock_read_sql.return_value = pd.DataFrame([{
+                "publish_time": "2026-08-20 10:00",
+                "stock_id": "2330",
+                "title": "[新聞] 台積電先進製程擴產",
+                "sentiment_score": 0.88,
+                "sentiment_label": "看多",
+                "push_count": 50,
+                "source": "ptt_stock",
+                "url": "https://ptt.cc/1"
+            }])
+
+            df_articles, mode = load_stock_articles("2330", limit=10)
+
+        self.assertEqual(mode, DataMode.REAL)
         self.assertIsInstance(df_articles, pd.DataFrame)
         expected_cols = ['publish_time', 'stock_id', 'title', 'sentiment_score', 'sentiment_label', 'push_count', 'source', 'url']
         for c in expected_cols:
diff --git a/tests/test_ui_contracts.py b/tests/test_ui_contracts.py
index 83a1649..7b950a1 100644
--- a/tests/test_ui_contracts.py
+++ b/tests/test_ui_contracts.py
@@ -19,6 +19,8 @@ from src.ui.data_loader import (
     load_thematic_radar_data,
     _fetch_real_stock_features_from_db,
     generate_mock_ptt_articles,
+    DataMode,
+    DataSourceError,
 )
 from src.ui.charts import (
     render_price_sentiment_candlestick_chart,
@@ -73,27 +75,117 @@ class DataLoaderContractTests(unittest.TestCase):
         self.assertIn("NVDA", stocks)
         self.assertIn("6488", stocks)
 
-    def test_load_stock_features_returns_18_columns(self):
-        df = load_stock_features("2330", days=30)
-        self.assertEqual(len(df), 30)
+    def test_load_stock_features_returns_real_mode_with_mocked_db(self):
+        """
+        HERM-03 修復：以 mock DB 產生確定性資料，驗證 REAL 模式與欄位契約。
+        原斷言 len(df)==30 對 live 資料硬編碼，真實 DB 若當日不足 30 筆即失敗，
+        且無法區分「程式壞了」與「當日資料不足」——改為「mock 回傳幾列，就該回傳幾列」。
+        """
+        from unittest.mock import patch
+        n_rows = 5
+        df_mock_prices = pd.DataFrame({
+            "trade_date": pd.date_range("2026-08-01", periods=n_rows),
+            "stock_id": ["2330"] * n_rows,
+            "open_price": [100.0] * n_rows,
+            "high_price": [105.0] * n_rows,
+            "low_price": [95.0] * n_rows,
+            "close_price": [102.0] * n_rows,
+            "volume": [10000] * n_rows,
+        })
+        df_mock_mapping = pd.DataFrame({"keyword": ["台積電"], "stock_id": ["2330"]})
+        df_mock_theme = pd.DataFrame(columns=["theme_keyword", "stock_id", "relevance_weight"])
+        df_mock_articles = pd.DataFrame(columns=[
+            "article_id", "source", "fetch_keyword", "post_time",
+            "title", "url", "author", "engagement_metric", "sentiment_score"
+        ])
 
-        # 驗證包含完整 18 欄位特徵
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect"), \
+             patch("pandas.read_sql") as mock_read_sql:
+            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "p"}
+            mock_read_sql.side_effect = [df_mock_prices, df_mock_mapping, df_mock_theme, df_mock_articles]
+
+            df, mode = load_stock_features("2330", days=30)
+
+        self.assertEqual(mode, DataMode.REAL)
+        self.assertEqual(len(df), n_rows)
         for col in ALL_MULTIMODAL_FEATURE_COLS:
             self.assertIn(col, df.columns)
-
-        # 驗證包含目標欄位
         self.assertIn("target_return_1d", df.columns)
         self.assertIn("target_up_down", df.columns)
 
+    def test_load_stock_features_returns_error_mode_when_db_fails(self):
+        """
+        HERM-03／HERM-E 修復：DB 連線失敗時回傳 DataMode.ERROR 與符合欄位契約的空表，
+        不自動退回模擬資料（DEC-012 方案 B：連線失敗不得以假資料撐場面）。
+        """
+        from unittest.mock import patch
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect", side_effect=ConnectionError("db down")):
+            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "p"}
+            df, mode = load_stock_features("2330", days=30)
+
+        self.assertEqual(mode, DataMode.ERROR)
+        self.assertTrue(df.empty)
+        for col in ALL_MULTIMODAL_FEATURE_COLS:
+            self.assertIn(col, df.columns)  # 空表仍保有正確欄位契約，呼叫端可安全檢查 .columns
+
+    def test_load_stock_features_demo_mode_bypasses_db_entirely(self):
+        """demo=True 是 DataMode.DEMO 的唯一合法入口，且完全不觸及 DB。"""
+        from unittest.mock import patch
+        with patch("psycopg2.connect") as mock_connect:
+            df, mode = load_stock_features("2330", days=10, demo=True)
+            mock_connect.assert_not_called()
+
+        self.assertEqual(mode, DataMode.DEMO)
+        self.assertEqual(len(df), 10)
+
     def test_load_stock_articles_returns_expected_columns(self):
-        df_articles = load_stock_articles("2330", limit=10)
+        """HERM-04 修復：mock DB 驗證 REAL 模式下的欄位契約，不依賴真實 DB 內容。"""
+        from unittest.mock import patch
+        df_mock_arts = pd.DataFrame({
+            "publish_time": ["2026-08-01 10:00"],
+            "stock_id": ["2330"],
+            "title": ["台積電營收亮眼"],
+            "sentiment_score": [0.8],
+            "sentiment_label": ["看多"],
+            "push_count": [10],
+            "source": ["ptt_stock"],
+            "url": ["https://ptt.cc/1"],
+        })
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect") as mock_connect, \
+             patch("pandas.read_sql", return_value=df_mock_arts):
+            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "p"}
+            mock_conn = mock_connect.return_value
+            mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
+
+            df_articles, mode = load_stock_articles("2330", limit=10)
+
+        self.assertEqual(mode, DataMode.REAL)
         self.assertIsInstance(df_articles, pd.DataFrame)
         expected_cols = ["publish_time", "stock_id", "title", "sentiment_score", "sentiment_label", "push_count", "source", "url"]
         for c in expected_cols:
             self.assertIn(c, df_articles.columns)
 
+    def test_load_stock_articles_returns_error_mode_when_db_fails(self):
+        """HERM-02／HERM-04／HERM-E 修復：DB 失敗回傳 DataMode.ERROR，不隱藏於「查無文章」的空表外觀之後。"""
+        from unittest.mock import patch
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect", side_effect=ConnectionError("db down")):
+            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "p"}
+            df_articles, mode = load_stock_articles("2330", limit=10)
+
+        self.assertEqual(mode, DataMode.ERROR)
+        self.assertTrue(df_articles.empty)
+
     def test_get_champion_predictor_inference(self):
-        df_features = load_stock_features("2330", days=40)
+        """
+        HERM-05 修復：以 demo=True 取得確定性合成特徵矩陣，測試目的是驗證 predictor 本身，
+        不是 DB 層——demo 模式完全不觸及 DB，是這個測試目的最貼切、最單純的資料來源。
+        """
+        df_features, mode = load_stock_features("2330", days=40, demo=True)
+        self.assertEqual(mode, DataMode.DEMO)
         predictor = get_champion_predictor(df_features)
 
         pred_res = predictor.predict_latest(df_features)
@@ -149,9 +241,31 @@ class DataLoaderContractTests(unittest.TestCase):
             self.assertEqual(df_res.iloc[-1]["close_price"], 1025.0)
 
     def test_load_thematic_radar_data_structure(self):
-        radar = load_thematic_radar_data()
+        """HERM-06 修復：mock DB 產生確定性題材資料，驗證 REAL 模式與結構契約。"""
+        from unittest.mock import patch
+        df_mock_mappings = pd.DataFrame({
+            "theme_keyword": ["矽光子", "矽光子"],
+            "stock_id": ["3081", "6442"],
+            "stock_name": ["聯亞", "光聖"],
+            "relevance_weight": [1.0, 0.9],
+        })
+        df_mock_stats = pd.DataFrame({
+            "fetch_keyword": ["矽光子"],
+            "article_count": [10],
+            "pos_cnt": [7],
+            "neg_cnt": [1],
+        })
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect"), \
+             patch("pandas.read_sql") as mock_read_sql:
+            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "p"}
+            mock_read_sql.side_effect = [df_mock_mappings, df_mock_stats]
+
+            radar, mode = load_thematic_radar_data()
+
+        self.assertEqual(mode, DataMode.REAL)
         self.assertIsInstance(radar, list)
-        self.assertGreaterEqual(len(radar), 3)
+        self.assertGreaterEqual(len(radar), 1)
 
         for theme in radar:
             self.assertIn("theme", theme)
@@ -166,18 +280,37 @@ class DataLoaderContractTests(unittest.TestCase):
                 self.assertIn("name", s)
                 self.assertIn("display", s)
 
+    def test_load_thematic_radar_data_returns_error_mode_when_db_fails(self):
+        """HERM-06／HERM-E 修復：DB 失敗回傳 DataMode.ERROR，不自動退回精選展示題材。"""
+        from unittest.mock import patch
+        with patch("src.loaders.db_writer.DBWriter") as mock_writer_cls, \
+             patch("psycopg2.connect", side_effect=ConnectionError("db down")):
+            mock_writer_cls.return_value.db_config = {"database": "t", "user": "u", "password": "p"}
+            radar, mode = load_thematic_radar_data()
+
+        self.assertEqual(mode, DataMode.ERROR)
+        self.assertEqual(radar, [])
+
 
 class InteractiveChartsTests(unittest.TestCase):
     """測試 Plotly 雙 Y 軸互動圖表與策略曲線產生器"""
 
     def test_render_price_sentiment_candlestick_chart_structure(self):
-        df = load_stock_features("2330", days=30)
-        fig = render_price_sentiment_candlestick_chart(df, stock_title="2330 台積電", market="TW")
+        """HERM-07 修復：demo=True 取得確定性合成資料，測試目的是圖表結構，不是 DB 層。"""
+        df, mode = load_stock_features("2330", days=30, demo=True)
+        fig = render_price_sentiment_candlestick_chart(df, stock_title="2330 台積電", market="TW", mode=mode)
         self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))
 
     def test_render_pnl_equity_curve_chart_structure(self):
-        df = load_stock_features("2330", days=30)
-        fig = render_pnl_equity_curve_chart(df, market="TW")
+        """HERM-08 修復：demo=True 取得確定性合成資料，測試目的是圖表結構，不是 DB 層。"""
+        df, mode = load_stock_features("2330", days=30, demo=True)
+        fig = render_pnl_equity_curve_chart(df, market="TW", mode=mode)
+        self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))
+
+    def test_render_price_sentiment_candlestick_chart_error_mode_is_placeholder(self):
+        """ERROR／EMPTY 模式回傳不含任何數值的佔位圖表，不嘗試對空 df 繪圖。"""
+        empty_df = pd.DataFrame()
+        fig = render_price_sentiment_candlestick_chart(empty_df, mode=DataMode.ERROR)
         self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))
 
     def test_render_feature_importance_bar_chart_structure(self):
@@ -219,13 +352,18 @@ class UIComponentsTests(unittest.TestCase):
         render_raw_article_table(df_articles)
 
     def test_render_thematic_radar_component_structure(self):
-        radar_data = load_thematic_radar_data()
-        res = render_thematic_radar(radar_data)
+        """HERM-09 修復：demo=True 取得確定性展示題材，測試目的是元件渲染，不是 DB 層。"""
+        radar_data, mode = load_thematic_radar_data(demo=True)
+        res = render_thematic_radar(radar_data, mode=mode)
         # 離線環境無按鈕點擊應安全回傳 None
         self.assertIsNone(res)
 
         # 空資料安全不崩潰
-        self.assertIsNone(render_thematic_radar([]))
+        self.assertIsNone(render_thematic_radar([], mode=DataMode.EMPTY))
+
+    def test_render_thematic_radar_error_mode_shows_banner_not_crash(self):
+        """mode=ERROR 時安全渲染錯誤橫幅並回傳 None，不嘗試渲染空清單。"""
+        self.assertIsNone(render_thematic_radar([], mode=DataMode.ERROR))
 
 
 if __name__ == "__main__":
```

</details>

---

## 2. 契約驗證原始輸出

```bash
python scripts/verify/gate0_contract_check.py
echo "EXIT=$?"
```

B1   PASS | 29 欄契約完整性
       migration 新增 22 + 既有 7 = 29
B2   PASS | 被引用欄位皆存在於契約（反查法）
       8 個被引用，缺失 0
B3   PASS | 社群欄位皆有 SOURCE_FAILED→NULL 規則（反查法）
       9 社群列全部標明 NULL
B4   PASS | raw 層留言計數欄無 DEFAULT（反查法）
       四欄型別: ['INTEGER']
B5   PASS | Triple-Barrier label domain 一致
       3/3 文件宣告；DDL CHECK=True
B6   PASS | Barrier anchor 一致為 Open[T+1]
       6 份使用；殘留舊 anchor 0
B7   PASS | 無「來源失敗→空 DataFrame」
       8 處提及，逐行判定全部為正當語境
B8   PASS | §19 需 PO 簽的決策皆有 ADR 承接
       6/6 存在
B9   PASS | Dcard SB 引用正確
       UG-G2-SB5 存在，無 UG-G3-SB1 誤引用
B10  PASS | 編號方案有唯一對照表
       FEATURE_REGISTRY.md §3.7 DB序號↔模型輸入索引對照
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:577 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂

==================================================
Part B: 11/11 PASS
EXIT=0
```

執行環境：host（Python 3.10.11）—— 純文件與 git 層次的靜態檢查，符合 `CLAUDE.md` §13.0 host 允許用途。

---

## 3. 執行環境 + 測試原始輸出 + 依賴狀態表

### 3a. 執行環境

| 欄位 | 內容 |
|------|------|
| 執行環境 | **container** |
| Python 版本 | `Python 3.14.6` |
| 容器名稱 | `stock_prediction_system2_devcontainer-app-1`（`-u vscode`） |

### 3b. 測試原始輸出

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python -m unittest discover -s tests -p "test_*.py"
```

```
Ran 173 tests in 7.822s

OK
```

173 = 164（SB1 commit `ccf0e52` 後基線）+ 9 個新增（HERM 修復拆分的正向/ERROR/EMPTY/DEMO 測試）。
`schema_smoke_ui_data_loader.py`（不含 `test_` 前綴）確認不被此指令撿到（見 §5）。

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python -m py_compile \
  app.py src/ui/data_loader.py src/ui/components.py src/ui/charts.py \
  tests/test_ui_contracts.py tests/test_operational_ux.py tests/test_real_articles_pipeline.py \
  tests/schema_smoke_ui_data_loader.py
echo "PY_COMPILE_EXIT=$?"
```
`PY_COMPILE_EXIT=0`

### 3c. 依賴狀態表

12/12 PRESENT（container，與 SB1 步驟 4/5 同一環境，未變動）：numpy／pandas／streamlit／plotly／sklearn／lightgbm／xgboost／psycopg2／jieba／snownlp／tenacity／dotenv 全部 PRESENT。本結果可支撐 DB 路徑的宣稱。

---

## 4. 格式／行尾夾帶偵測

```bash
git diff --numstat > /tmp/ns_raw.txt
git diff --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

```
1c1
< 114	78	app.py
---
> 54	18	app.py
5c5
< 264	173	src/ui/data_loader.py
---
> 191	100	src/ui/data_loader.py
WSDIFF_EXIT=1
```

**本節原始判斷有誤，已由 PO 2026-08-25 逐行核對 diff 抓到並已修正——見
`SB2_STEP0_4_5_RECORD.md` §0 完整記錄，此處僅保留更正後的結論，不覆寫原始錯誤判斷的存在事實**：

- `app.py` 的落差**確認為合法重新縮排**：KPI 卡片／預測邏輯整段移入新的
  `if features_usable: ... else: ...` 條件區塊，約 40 行縮排層級改變，判斷維持不變。
- `src/ui/data_loader.py` 的落差**當時判斷為「純屬重寫造成的相對位置改變」，這個判斷是不完整的**——
  PO 逐行核對後發現其中確實有 **19 處與本次改動無關的純格式清理**（15 處空白行的尾隨空格、
  4 處內容行尾多餘空格），是 `Write` 工具整檔重寫時的副作用，與 SB1 步驟 3 那次同源。
  **已逐一以原始位元組還原**（過程與工具限制記錄見 `SB2_STEP0_4_5_RECORD.md` §0），
  還原後 `src/ui/data_loader.py` 的 `numstat` 落差才是單純出於「新增 `DataMode` 類別／
  `demo` 參數等大量新內容插入既有函式之間，改變前後文位置」——這部分無法用 `-w` 消除，
  是 diff 演算法對「大範圍插入」的正常表現，不是格式夾帶。

**排除意外格式夾帶的方式**：`git diff --check`（見下方）僅顯示既有的全庫 LF→CRLF 提示，
未回報任何新增的行尾空白錯誤（trailing whitespace）——若有孤立的格式正規化，這裡會顯示。
**但本次事件證明「`git diff --check` 沒有額外警告」不足以單獨排除格式夾帶**——已還原的 15 個
純空白行、4 個內容行尾空格，兩者皆不會被 `git diff --check` 標記為 trailing whitespace 錯誤
（因為它們是「消失」而非「新增」的空白，`--check` 只抓新增的行尾空白）。此為本次的重要教訓，
記錄於 `SB2_STEP0_4_5_RECORD.md`。

```bash
git diff --check
```

```
warning: in the working copy of 'app.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'doc/governance/PROJECT_STATUS.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/charts.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/components.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/data_loader.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_operational_ux.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_real_articles_pipeline.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_ui_contracts.py', LF will be replaced by CRLF the next time Git touches it
```

（八個檔案的既有 CRLF 提示，與過去每一輪相同，非本次新增。無 trailing-whitespace 錯誤。）

---

## 5. Schema Smoke Test：臨時 DB 執行紀錄

比照 SB1 隔離臨時 DB 機制。

### 5a. 隔離證據

| 項目 | 值 |
|------|-----|
| 容器 | `sb2_smoke_tmpdb`（已拆除） |
| Volume | 匿名 docker volume，`HostConfig.Binds = null` |
| Port | 55435（真實開發 DB 在 5432） |
| Schema | `database/schema.sql` 套用完成，exit 0 |
| 拆除 | `docker rm -f -v sb2_smoke_tmpdb`；開發容器 uptime 未受影響 |

### 5b. 綁定確認（RISK-013 控制措施，以 `DBWriter().db_config` 取得）

```
專案解析出的連線設定: {'host': 'localhost', 'port': 55435, 'database': 'sb2_smoke', 'user': 'tmp_sb2'}
current_database() = sb2_smoke
current_user       = tmp_sb2
inet_server_port() = 55435
public schema 表數  = 7
```

### 5c. 4 個 Smoke Test 執行結果

```bash
MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=localhost -e DB_PORT=55435 -e POSTGRES_DB=sb2_smoke \
  -e POSTGRES_USER=tmp_sb2 -e POSTGRES_PASSWORD=tmp_sb2 \
  stock_prediction_system2_devcontainer-app-1 \
  python -m unittest tests.schema_smoke_ui_data_loader -v
```

```
test_entity_mapping_query_executes_and_columns_match ... ok
test_market_articles_query_executes_and_columns_match ... ok
test_stock_prices_query_executes_and_columns_match ... ok
test_theme_stock_mapping_query_executes_and_columns_match ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.044s

OK
```

全部針對套用 `schema.sql` 後的空表執行（僅驗證查詢可執行、欄位相符，未斷言具體數值，符合 §5.1.2 設計原則）。

### 5d. 確認不進正式套件

```bash
python -m unittest discover -s tests -p "test_*.py"   # Ran 173 tests（非 177），確認 smoke 檔未被撿到
```

---

## 6. 尚未涵蓋／後續事項

1. **HERM-D**（測試名稱過期「18 欄位」數字）：本 SB 明確排除，歸屬 UG-G1-SB5。
2. **§6 圖表浮水印的持久化驗證**：`_apply_demo_watermark()`／`_placeholder_figure()` 已通過單元測試結構驗證
   （`hasattr(fig, "to_dict")`），但**尚未在真實 Streamlit 執行環境肉眼確認視覺呈現**——建議 Gate B 前
   以 `streamlit run app.py` 手動過一次三種非 REAL 情境（可暫時在 app.py 呼叫處手動傳入 `demo=True`
   或模擬 DB 斷線來檢視）。
3. **BEFORE／AFTER 快照與 Sentinel（`SB2_GATE_A_PROPOSAL.md` §5.2、§5.6、§5.7）尚未執行**——
   本次直接進入步驟 3 實作並回報，比照 PO 這一輪要求的精簡格式；若要完整比照 SB1 的六步驟證據鏈，
   還需要步驟 0（覆蓋歸因）、步驟 4（AFTER 快照）與步驟 5（Sentinel：HERM runtime 攔截數應歸零）。
   是否需要補齊，或以本報告直接進入 Gate B 整理，請 PO 指示。

