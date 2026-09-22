# UG-G1-SB2 Gate B 送審文件：UI Demo/Real 模式分離（DEC-012）

> **性質**：`gate-submit` skill 六項強制產出的整合文件。**不是** commit 授權本身——
> commit 授權留待 PO 讀完本文件後另行決定。本次未執行 `git add`／`git commit`。
> **執行日期**：2026-08-25（第一輪：步驟 0～6）、2026-08-25（第二輪：Streamlit 視覺驗證與修復，PO 要求併入本文件）
> **狀態**：步驟 0～6 全數完成；§8 第 1 項視覺驗證缺口已補齊（過程中發現並修復一個 ERROR 模式當機 bug）；
> `src/`、`app.py`、`tests/` 變更尚未 commit

---

## 0. 步驟 0～6 完整回顧

| 步驟 | 內容 | 完成日期 | 證據位置 |
|------|------|---------|---------|
| Gate A | 提案撰寫、含 §3.2 三方案裁決請求、§5.1 schema smoke test 補充要求 | 2026-08-25 | `SB2_GATE_A_PROPOSAL.md` |
| PO 裁決 | §8 六項全數裁決：方案 B（ERROR 不自動退回 DEMO）、charts.py 需視覺標示、4 代表查詢足夠、核准實作 | 2026-08-25 | 對話紀錄；落實於 DEC-012 |
| 步驟 3 | 實作：`DataMode`／`DataSourceError`、四個公開函式改回傳元組、`components.py`／`charts.py` 視覺標示、HERM-01~09 重寫、schema smoke test | 2026-08-25 | `SB2_STEP3_IMPLEMENTATION_REPORT.md` |
| 格式夾帶還原 | PO 逐行核對抓到 15 處純空白行清理；PM 追加找到 4 處內容行尾空格，合計 19 處，逐一以原始位元組還原 | 2026-08-25 | `SB2_STEP0_4_5_RECORD.md` §0 |
| 步驟 0 | Runtime 覆蓋歸因：A 類 28 個測試（`data_loader.py` 24、`components.py` 4、`charts.py` 4，含重疊）；`app.py` 0（既有測試設計未直接執行） | 2026-08-25 | `SB2_STEP0_4_5_RECORD.md` §1 |
| 步驟 4 | AFTER 快照：164→173，逐檔比對僅 `test_operational_ux`（+3）與 `test_ui_contracts`（+6）有變化 | 2026-08-25 | `SB2_STEP0_4_5_RECORD.md` §2 |
| 步驟 5 | Sentinel：靜態 `connect()` 呼叫點仍 10 處；runtime 攔截數由 9 降為 0（PO 與 PM 各自獨立重跑，結果一致） | 2026-08-25 | `SB2_STEP0_4_5_RECORD.md` §3 |
| §7 文件同步 | `DECISIONS.md` 新增 DEC-012（`Proposed`）；`TRACEABILITY.md` 新增追溯列；`DOCUMENT_DRIFT_REMEDIATION.md` 更新 DRIFT-009／HERM-A/B/C/E | 2026-08-25 | `SB2_STEP0_4_5_RECORD.md` §5 |
| 步驟 6 | 本文件（Gate B 送審） | 2026-08-25 | 本檔 |
| 步驟 6b（第二輪，PO 要求） | Streamlit 視覺驗證：`streamlit run app.py` 於獨立臨時容器實際啟動，ERROR／REAL／DEMO 三態逐一截圖檢視；過程中發現並修復一個 ERROR 模式下的真實當機 bug（`StreamlitDuplicateElementId`）；一併完成 PO 臨時提出的兩項圖表調整（PnL 圖例遮擋、特徵重要性改圓餅圖並顯示全部特徵） | 2026-08-25 | 本節 §1／§6／§7；`git diff` |

**核心決策（DEC-012 方案 B，PO 原話）**：「這不是商業產品，是我的求職作品集，我要展示的是真實的
技術能力，不需要用假資料撐場面——就算某個區塊因為 DB 沒開而顯示錯誤，只要講得出原因，比顯示一堆
看起來正常但其實是虛構的數字更有價值。」ERROR 不再自動退回 DEMO；`demo=True` 是 DEMO 的唯一顯式入口。

---

## 1. 完整 Diff（最終全貌，已包含第二輪視覺驗證中的修復與圖表調整）

> 本節於 2026-08-25（第二輪）重新產出，取代第一輪的舊快照。新增部分：
> `app.py` 三處 `st.plotly_chart` 加上唯一 `key=`（修復 `StreamlitDuplicateElementId` 當機）；
> `src/ui/charts.py` 的 `render_pnl_equity_curve_chart`（圖例移至圖表下方，避免與標題重疊）與
> `render_feature_importance_bar_chart`（改用 `go.Pie` 圓餅圖，移除 `top_n` 截斷，顯示全部特徵）；
> `tests/test_ui_contracts.py` 同步移除已失效的 `top_n=5` 引數。

**檔案清單**（11 modified + 4 new，894 insertions(+), 310 deletions(-)）：

 app.py                                     | 198 ++++++++------
 doc/evidence/DECISIONS.md                  |  94 +++++++
 doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md |  12 +-
 doc/evidence/TRACEABILITY.md               |   1 +
 doc/governance/PROJECT_STATUS.md           |  13 +-
 src/ui/charts.py                           | 141 +++++++---
 src/ui/components.py                       |  93 ++++++-
 src/ui/data_loader.py                      | 399 ++++++++++++++++++-----------
 tests/test_operational_ux.py               |  49 +++-
 tests/test_real_articles_pipeline.py       |  30 ++-
 tests/test_ui_contracts.py                 | 174 +++++++++++--
 11 files changed, 894 insertions(+), 310 deletions(-)

```
 + 4 個新檔（untracked）：
   doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md
   doc/upgrade/gates/SB2_STEP3_IMPLEMENTATION_REPORT.md
   doc/upgrade/gates/SB2_STEP0_4_5_RECORD.md
   tests/schema_smoke_ui_data_loader.py
```

**重跑指令**：`git diff`（工作區尚未 staged，此指令即可重現下方全部內容）

<details>
<summary>完整 diff 內容（點擊展開）</summary>

```diff
diff --git a/app.py b/app.py
index 361d006..63757cd 100644
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
 
@@ -202,10 +233,10 @@ def main():
     # ----------------------------------------------------
     st.markdown(f"### 📈 {stocks[selected_stock]} 多維互動價格與社群情緒圖表")
     fig_main = render_price_sentiment_candlestick_chart(
-        df_features, stock_title=stocks[selected_stock], market=market_code
+        df_features, stock_title=stocks[selected_stock], market=market_code, mode=features_mode
     )
     if hasattr(fig_main, "to_dict"):
-        st.plotly_chart(fig_main, use_container_width=True)
+        st.plotly_chart(fig_main, use_container_width=True, key="chart_main_candlestick")
 
     # ----------------------------------------------------
     # 7. 量化回測曲線與特徵重要性 (Sub-Charts)
@@ -213,21 +244,26 @@ def main():
     sub_col1, sub_col2 = st.columns(2)
 
     with sub_col1:
-        fig_pnl = render_pnl_equity_curve_chart(df_features, market=market_code)
+        fig_pnl = render_pnl_equity_curve_chart(df_features, market=market_code, mode=features_mode)
         if hasattr(fig_pnl, "to_dict"):
-            st.plotly_chart(fig_pnl, use_container_width=True)
+            st.plotly_chart(fig_pnl, use_container_width=True, key="chart_pnl_equity")
 
     with sub_col2:
-        fig_imp = render_feature_importance_bar_chart(predictor.trainer.feature_importances_, top_n=8)
+        imp_mode = features_mode if can_predict else DataMode.ERROR
+        importances = predictor.trainer.feature_importances_ if predictor is not None else {}
+        fig_imp = render_feature_importance_bar_chart(importances, mode=imp_mode)
         if hasattr(fig_imp, "to_dict"):
-            st.plotly_chart(fig_imp, use_container_width=True)
+            st.plotly_chart(fig_imp, use_container_width=True, key="chart_feature_importance")
 
     st.markdown("---")
 
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
diff --git a/doc/evidence/DECISIONS.md b/doc/evidence/DECISIONS.md
index 708a55c..3ded1e8 100644
--- a/doc/evidence/DECISIONS.md
+++ b/doc/evidence/DECISIONS.md
@@ -1193,3 +1193,97 @@ V7 的初版規格存在兩個結構性錯誤：
 
 `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §4；`SYSTEM_UPGRADE_MASTER_PLAN.md` §3.3
 
+---
+
+## DEC-012：UI Four-State Data Mode（REAL/DEMO/EMPTY/ERROR）
+
+- 日期：2026-08-25
+- 狀態：`Proposed`（PO 已裁決核心語意，待 PO 於 Gate B 確認狀態改為 `APPROVED`）
+- 觸發 Gate：UG-G1-SB2
+
+### Context（背景）
+
+`src/ui/data_loader.py` 的四個公開函式（`load_stock_features`、`load_stock_articles`、
+`load_ai_discovered_keywords`、`load_thematic_radar_data`）原本只回傳單一值，DB 連線失敗、
+DB 成功但無資料、與刻意使用模擬資料三種情況被壓縮成同一種回傳值外觀，呼叫端與使用者無法區分
+（DRIFT-009）。
+
+### Problem（問題）
+
+`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 的 Failure Semantics 原文把 ERROR／EMPTY／DEMO
+列為三個獨立觸發來源，但未回答一個實際會發生的情境：DB 連線失敗時，UI 究竟該顯示空白
+（嚴格對應 ERROR），還是顯示標示清楚的模擬資料（實質上退回 DEMO）？現行程式碼的行為是
+後者但未標示；這正是 `SB2_GATE_A_PROPOSAL.md` §3.2 提出三個方案請 PO 裁決的原因。
+
+### Alternatives Considered（考慮方案）
+
+`SB2_GATE_A_PROPOSAL.md` §3.2：
+
+- **方案 A**：ERROR 自動退回 DEMO，但顯著標示（PM 原建議，理由是保留「離線也能展示」的作品集體驗）。
+- **方案 B**：ERROR 顯示空白／錯誤訊息，完全不顯示模擬數字，DEMO 僅供顯式啟用。
+- **方案 C**：由使用者以 Sidebar 開關手動切換 ERROR 時的行為。
+
+### Decision（決策）
+
+**採方案 B**（PO 2026-08-25 決策）。原話：「這不是商業產品，是我的求職作品集，我要展示的是真實的
+技術能力，不需要用假資料撐場面——就算某個區塊因為 DB 沒開而顯示錯誤，只要講得出原因，比顯示一堆
+看起來正常但其實是虛構的數字更有價值。」
+
+```python
+class DataMode(Enum):
+    REAL = "real"    # DB 連線成功且回傳非空資料
+    DEMO = "demo"     # 展示用模擬資料，僅在呼叫端明確傳入 demo=True 時使用
+    EMPTY = "empty"   # DB 連線成功，查詢結果為零筆——真實的「沒有」，非模擬
+    ERROR = "error"   # DB 連線或查詢本身失敗，對應區塊不渲染任何數值
+```
+
+- ERROR：對應區塊顯示「⚠️ 資料來源目前無法連線」，**不渲染任何 KPI 卡片／圖表數值／預測結果**。
+- DEMO：**不再是 ERROR 的自動 fallback**。四個公開函式新增 `demo: bool = False` 參數，
+  作為 DEMO 模式的唯一合法入口；`app.py` 目前不傳入 `demo=True`（無 UI 開關，PO 明確表示
+  「不用做到 UI 開關」，僅需函式參數層級的入口）。
+- EMPTY 與 ERROR 需在資料層明確區分：`_fetch_real_stock_features_from_db`／
+  `_fetch_real_stock_articles_from_db` 內部例外改為拋出 `DataSourceError`（→ ERROR），
+  成功但零筆資料則回傳實際空結果（→ EMPTY），不再讓兩者共用同一個 `None` 回傳值。
+- `charts.py` 三個圖表函式與 `components.py` 四個渲染元件皆新增 `mode` 參數：ERROR／EMPTY
+  回傳／渲染不含任何數值的佔位內容；DEMO 正常渲染但疊加醒目浮水印／橫幅。
+
+### Rationale（理由）
+
+方案 B 直接對應 PO 的產品定位判斷：本專案的價值來自展示真實技術能力，虛構數字換取畫面完整性
+在求職作品集情境下是負資產而非資產。比方案 A 更嚴格但語意更乾淨——ERROR 與 DEMO 的畫面呈現
+不再重疊，`DataMode` 列舉值與使用者實際看到的內容一一對應。
+
+### Trade-offs（取捨）
+
+- 使用者在 DB 未啟動或未跑過 ETL 時開啟 UI，會看到較多空白／錯誤區塊，犧牲「離線也能展示」的
+  即時可用性——PO 已權衡並接受此取捨。
+- 需要在 `data_loader.py` 內部拆分 EMPTY／ERROR 兩種路徑（新增 `DataSourceError`），
+  屬本 SB 新增的內部契約，不影響既有 Schema。
+- `demo=True` 目前只有函式參數層級入口，沒有 UI 開關；日後若要在 UI 上實際展示 DEMO 模式，
+  需要另一個決策與實作（不在本 SB 範圍）。
+
+### Affected Components（影響範圍）
+
+`src/ui/data_loader.py`（`DataMode`、`DataSourceError`、四個公開函式簽章）、
+`src/ui/components.py`（`render_data_mode_banner` 與四個元件的 `mode` 參數）、
+`src/ui/charts.py`（`_placeholder_figure`／`_apply_demo_watermark` 與三個圖表函式的 `mode` 參數）、
+`app.py`（解包四個函式的 `(value, DataMode)` 元組、依 mode 分流 KPI／預測邏輯、Sidebar 全域來源追蹤）
+
+### Verification（驗證）
+
+- [x] 173/173 tests PASS（container，164 基線 + 9 個新增，含 REAL/ERROR/EMPTY/DEMO 各模式的正向測試）
+- [x] HERM-01~09 全數改為 mock，不再依賴環境憑證與 DB 內容
+- [x] GOV-02 sentinel：HERM 對應測試的 runtime `connect()` 攔截數由 9 降為 0（PO 與 PM 各自重跑確認）
+- [x] `tests/schema_smoke_ui_data_loader.py`：4 個代表查詢對臨時 DB 執行，欄位契約相容性確認
+- [ ] Streamlit 真實執行環境的視覺呈現尚未肉眼確認（僅驗證結構，見 `SB2_STEP3_IMPLEMENTATION_REPORT.md` §6）
+
+### Remaining Risks（剩餘風險）
+
+- `demo=True` 尚無 UI 觸發入口，若日後需要在畫面上實際展示 DEMO 模式，需另行設計進入點。
+- ERROR 狀態的空白呈現尚未經真實使用者（含作品集審閱者）體驗驗證，僅有結構性測試支持。
+
+### 證據文件
+
+`doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md` §3；
+`doc/upgrade/gates/SB2_STEP3_IMPLEMENTATION_REPORT.md`
+
diff --git a/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md b/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
index 3713491..192875d 100644
--- a/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
+++ b/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
@@ -33,7 +33,7 @@
 | DRIFT-006 | **HIGH** | DECISIONS.md (DEC-004) | `DECISIONS.md:L315-432` | DEC-004 應為單一連貫決策記錄 | L315-432 包含 DEC-004 Context/Problem/Alternatives/Decision/Rationale/Trade-offs/Affected Components/Verification 的 **完整重複副本**（與 L206-313 的內容幾乎相同，僅細節措辭略有不同）。造成文件長度膨脹且容易誤引。 | `VERIFIED — diff shows duplicate structure` | 移除 L315-432 的重複內容，保留 L206-313 的權威版本。 | UG-G1-SB5 |
 | DRIFT-007 | **HIGH** | DECISIONS.md (DEC-006, DEC-007) | `DECISIONS.md:L551,L607,L617` | DEC-006:「FeatureAggregator 輸出 18 項標準特徵矩陣」; DEC-007:「多模態 18 欄位特徵」「多模態 18 特徵」 | 同 DRIFT-001：實際為 17 項。此處文件引用與程式碼不一致。 | `VERIFIED — cross-ref DRIFT-001` | 統一改用版本化契約名稱（`LEGACY_17` / `CORE_16` / `COMMENT_ENHANCED_19`），消除硬編碼數字。 | UG-G1-SB5 |
 | DRIFT-008 | **HIGH** | components.py | `src/ui/components.py:L128-141` | 排行榜應反映真實 Walk-Forward 實驗結果 | `render_tournament_leaderboard()` 使用 **硬編碼 Python dict list** 作為 8 組實驗排行榜資料（L129-138），數據為靜態假值而非從模型訓練結果或資料庫動態載入。 | `VERIFIED — static dict at L129-138` | 改為從 `models/` 目錄載入最新實驗 metadata JSON，或從 DB 查詢歷史訓練結果，實現動態排行榜。 | UG-G1-SB3 |
-| DRIFT-009 | **HIGH** | data_loader.py | `src/ui/data_loader.py:L31-40` | UI 應明確區分 DB 即時資料與離線模擬資料 | `generate_mock_stock_features()` 在 DB 連線失敗時被靜默呼叫作為 fallback，使用者無法從 UI 辨別當前顯示的是真實資料還是模擬資料。函式註解寫「供離線演示與 DB Fallback」但無任何告警機制。 | `VERIFIED — silent fallback, no warning` | 加入明確的 UI 告警橫幅（`st.warning`），當 fallback 至 mock 資料時顯示「目前顯示離線模擬資料」，並在日誌記錄 fallback 事件。 | UG-G1-SB2 |
+| DRIFT-009 | **HIGH** | data_loader.py | `src/ui/data_loader.py:L31-40` | UI 應明確區分 DB 即時資料與離線模擬資料 | `generate_mock_stock_features()` 在 DB 連線失敗時被靜默呼叫作為 fallback，使用者無法從 UI 辨別當前顯示的是真實資料還是模擬資料。函式註解寫「供離線演示與 DB Fallback」但無任何告警機制。 | `VERIFIED — 已修正（2026-08-25，尚未 commit）：src/ui/data_loader.py 逐一驗證確認四個公開函式皆已改為 (value, DataMode) 回傳，ERROR 不再自動呼叫 generate_mock_stock_features()` | **已修正，採 DEC-012 方案 B（PO 2026-08-25 裁示）**：與本列原建議的「加告警橫幅但保留自動 fallback」不同——PO 判定連線失敗時**不應**自動顯示模擬資料，改為 ERROR 模式僅顯示「⚠️ 資料來源目前無法連線」，不渲染任何數值；`demo=True` 成為 DEMO 模式的唯一顯式入口。證據見 `SB2_STEP3_IMPLEMENTATION_REPORT.md`、DEC-012。 | UG-G1-SB2（已完成，待 commit） |
 | DRIFT-010 | **HIGH** | Repository root | Repository root | 專案應有 README.md 提供快速入門指引 | `ls README.md` 回傳 exit code 2（檔案不存在）。整個 Repository 沒有任何頂層 README 文件。 | `VERIFIED — file not found` | 建立 `README.md`，涵蓋專案簡介、架構圖、快速啟動、測試執行與貢獻指引。 | UG-G1-SB5 |
 | DRIFT-011 | **HIGH** | Database / Schema | `database/schema.sql`, `src/loaders/db_writer.py` | 系統應具備資料庫遷移機制以支援 Schema 演進 | 專案中 `grep -r "schema_version\|ALTER TABLE" *.py *.sql` 回傳零結果。無任何 migration framework（如 Alembic）、`ALTER TABLE` 語句或 `schema_version` 追蹤表。Schema 變更只能透過 drop-and-recreate 執行。 | `VERIFIED — no migration infrastructure` | 導入輕量 migration 機制：建立 `schema_version` 表 + 有序 migration 腳本目錄 `database/migrations/`，或整合 Alembic。 | UG-G1-SB4 |
 | DRIFT-012 | **MEDIUM** | feature_aggregator.py / time_series_split | `src/transform/feature_aggregator.py:L459` | Target label 生成與 Walk-Forward 切分邊界應無洩漏 | `append_target_labels()` 使用 `shift(-1)` 在完整 DataFrame 上生成 `target_next_close`（L459），此操作在 Walk-Forward splitter 切分邊界處，最後一筆訓練資料的 target 可能洩漏測試集首筆收盤價。需驗證 splitter 是否在 target label 附加 **之後** 切分（安全）還是 **之前** 切分（洩漏風險）。 | `VERIFIED — 洩漏已於 SB1_STEP1_BEFORE_SNAPSHOT.md §5.1 實測確認存在（gap 全為週末、交易日隔離為零），並於 UG-G1-SB1 步驟 3 修正` | **已修正（2026-08-24/25，尚未 commit）**：`WalkForwardSplitter` 新增 `label_horizon`／`embargo_days`／Purge；`generate_target_labels()` 新增 `label_end_date` 欄位供逐列精確 Purge 判定。稽核與修正證據見 `SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、DEC-011。 | UG-G1-SB1（已完成步驟 0～5，待 commit） |
@@ -77,7 +77,7 @@ lock 只保證「照 lock 安裝會得到已驗證的版本組合」，並未修
 | Owner Gate/SB | 漂移 ID | 簡述 |
 |---------------|---------|------|
 | UG-G1-SB1（已修正，待 commit） | DRIFT-012 | 時序邊界洩漏稽核與修正 |
-| UG-G1-SB2 | DRIFT-009 | Silent mock fallback 告警 |
+| UG-G1-SB2（已修正，待 commit） | DRIFT-009 | Silent mock fallback 告警 → DEC-012 方案 B 移除自動 fallback |
 | UG-G1-SB3 | DRIFT-008 | 靜態排行榜改動態 |
 | UG-G1-SB4 | DRIFT-011 | DB migration 機制 |
 | UG-G1-SB5 | DRIFT-001, DRIFT-002, DRIFT-004, DRIFT-005, DRIFT-006, DRIFT-007, DRIFT-010, DRIFT-013 | 文件同步與修復（特徵契約名稱、SDD 模組狀態、測試計數、DEC-003 還原、DEC-004 去重、Git State、README） |
@@ -128,11 +128,11 @@ lock 只保證「照 lock 安裝會得到已驗證的版本組合」，並未修
 
 | ID | Severity | 問題 | 證據 | Remediation |
 |----|----------|------|------|-------------|
-| HERM-A | **HIGH** | 9 個測試行為隨環境憑證與 DB 內容改變，不具封閉性 | 上表；sentinel 堆疊紀錄 | 併入 UG-G1-SB2 一併處理 |
-| HERM-B | **HIGH** | `test_load_ai_discovered_keywords_fallback` 名稱明示測 fallback，但在有真實資料的環境下測到的**不是** fallback 路徑 | `test_operational_ux.py:74` | UG-G1-SB2 |
-| HERM-C | **HIGH** | `test_load_stock_features_returns_18_columns` 對 live 資料硬斷言 `assertEqual(len(df), 30)`；真實 DB 若該股不足 30 日資料即失敗，且無法區分「程式壞了」與「當日資料不足」 | `test_ui_contracts.py:77` | UG-G1-SB2 |
+| HERM-A | **HIGH** | 9 個測試行為隨環境憑證與 DB 內容改變，不具封閉性 | 上表；sentinel 堆疊紀錄 | **已修正（2026-08-25，尚未 commit）**：9 個測試皆已改為 `unittest.mock` 隔離，不再連真實 DB。GOV-02 sentinel 重跑確認 runtime `connect()` 攔截數由 9 降為 0（PO 與 PM 各自重跑確認一致）。證據見 `SB2_STEP3_IMPLEMENTATION_REPORT.md`。 | UG-G1-SB2（已修正，待 commit） |
+| HERM-B | **HIGH** | `test_load_ai_discovered_keywords_fallback` 名稱明示測 fallback，但在有真實資料的環境下測到的**不是** fallback 路徑 | `test_operational_ux.py:74` | **已修正**：拆為 `test_load_ai_discovered_keywords_returns_real_mode_when_db_has_data`（mock 出 REAL 路徑）與 `test_load_ai_discovered_keywords_falls_back_when_db_fails`（mock 出 ERROR 路徑），兩者皆確定性命中各自宣稱的路徑，不再受環境影響。 | UG-G1-SB2（已修正，待 commit） |
+| HERM-C | **HIGH** | `test_load_stock_features_returns_18_columns` 對 live 資料硬斷言 `assertEqual(len(df), 30)`；真實 DB 若該股不足 30 日資料即失敗，且無法區分「程式壞了」與「當日資料不足」 | `test_ui_contracts.py:77` | **已修正**：改名為 `test_load_stock_features_returns_real_mode_with_mocked_db`，斷言改為「mock 回傳幾列，就該回傳幾列」（n_rows=5），不再依賴真實 DB 當日資料量。 | UG-G1-SB2（已修正，待 commit） |
 | HERM-D | **MEDIUM** | 同一測試名稱中的「18 欄位」為 DRIFT-001 的過期數字（實際 `ALL_MULTIMODAL_FEATURE_COLS` 為 17，目標契約為 29） | 同上；參照 DRIFT-001 | UG-G1-SB5 |
-| HERM-E | **HIGH** | 靜默回退：`src/ui/data_loader.py:214-215` 以 `logger.debug` 吞掉連線例外後 `return None`，上層改用 mock，測試照樣通過。與已登錄的 DRIFT-009 同一根因 | `data_loader.py:214-215` | UG-G1-SB2（併入 DRIFT-009） |
+| HERM-E | **HIGH** | 靜默回退：`src/ui/data_loader.py:214-215` 以 `logger.debug` 吞掉連線例外後 `return None`，上層改用 mock，測試照樣通過。與已登錄的 DRIFT-009 同一根因 | `data_loader.py:214-215` | **已修正**：`logger.debug` 提升為 `logger.warning`；例外不再被吞掉後靜默回傳 `None`，改為拋出 `DataSourceError` 並由公開函式明確轉換為 `DataMode.ERROR`，上層不再自動改用 mock（DEC-012 方案 B）。 | UG-G1-SB2（併入 DRIFT-009，已修正，待 commit） |
 
 ### 環境降級的可見性差異
 
diff --git a/doc/evidence/TRACEABILITY.md b/doc/evidence/TRACEABILITY.md
index 072921a..5e3ad38 100644
--- a/doc/evidence/TRACEABILITY.md
+++ b/doc/evidence/TRACEABILITY.md
@@ -57,6 +57,7 @@
 | **AI 題材概念股映射與知識庫** | 題材全系統升級 (SB-TH1) | 2.1 儲存與探索架構 | **DEC-009** (SB-TH1) | `src/extractors/trend_discover.py`<br>`src/loaders/db_writer.py` | `tests/test_thematic_mapping.py` | 4 tests | `VERIFIED THIS SESSION` (Thematic) |
 | **題材情緒溢出加權特徵引擎** | 題材全系統升級 (SB-TH2) | 2.3 題材特徵邊界 | **DEC-009** (SB-TH2) | `src/transform/feature_aggregator.py`<br>`main_etl_pipeline.py` | `tests/test_thematic_feature_spillover.py` | 5 tests | `VERIFIED THIS SESSION` (Thematic) |
 | **三重查詢真實文章與空狀態透明化** | 輿情明細透明化 (SB-ART1~3) | 4.1 輿情明細架構 | **DEC-008** / REAL-ART | `src/ui/data_loader.py`<br>`src/ui/components.py` | `tests/test_real_articles_pipeline.py` | 4 tests | `VERIFIED THIS SESSION` (Real Articles) |
+| **UI 四狀態資料來源透明化（REAL/DEMO/EMPTY/ERROR）** | 稽核報告 §2；AGENTS.md §10；DRIFT-009 | 7.1 UI Demo/Real 模式分離 | **DEC-012**（UG-G1-SB2） | `src/ui/data_loader.py`（`DataMode`／`DataSourceError`）<br>`src/ui/components.py`（`render_data_mode_banner`）<br>`src/ui/charts.py`（佔位圖／浮水印）<br>`app.py`（mode 分流與全域追蹤） | `tests/test_ui_contracts.py`<br>`tests/test_operational_ux.py`<br>`tests/test_real_articles_pipeline.py`<br>`tests/schema_smoke_ui_data_loader.py`（不進正式套件） | 9 個新增測試 + 4 個 schema smoke test | `VERIFIED THIS SESSION`（`SB2_STEP3_IMPLEMENTATION_REPORT.md`；173/173 PASS；HERM runtime 攔截數 9→0；`src/` 尚未 commit） |
 | **總計 (Total)** | - | - | **9 大核心 ADR + 7 大挑戰** | **18 大核心生產模組** | **17 大測試套件檔案** | **154 項測試** | **100% PASS (~1.80s)** |
 
 ---
diff --git a/doc/governance/PROJECT_STATUS.md b/doc/governance/PROJECT_STATUS.md
index 3b7519e..a082bcc 100644
--- a/doc/governance/PROJECT_STATUS.md
+++ b/doc/governance/PROJECT_STATUS.md
@@ -33,7 +33,8 @@
 | GOV-05 文件依歸屬與生命週期分類 | 完成 | `abfa743`、`7f7258e` |
 | GOV-06 交接 | 本次 | 本 commit |
 | **UG-Gate-1** | **已核准，採逐 SB 授權** | — |
-| └ **UG-G1-SB1** Purged Walk-Forward | Gate A 已核准；**步驟 0～5 完成；步驟 6（送 Gate B）未開始** | `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`；步驟 2 見 `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節；`src/` 變更尚未 commit |
+| └ **UG-G1-SB1** Purged Walk-Forward | **CLOSED**（2026-08-25 PO 核准結案） | commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`；證據見 `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、`SB1_GATE_B_SUBMISSION.md`；DEC-011、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-012）已同步 |
+| └ **UG-G1-SB2** UI Demo/Real 模式分離 | Gate A 已核准（含 DEC-012 方案 B 裁決）；**步驟 0、3、4、5 完成；§7 文件同步完成；步驟 6（送 Gate B、commit）未開始** | `doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md`、`SB2_STEP3_IMPLEMENTATION_REPORT.md`、`SB2_STEP0_4_5_RECORD.md`；`src/` 變更尚未 commit |
 
 RISK-001 `Accept`、RISK-010 `Defer`（至 Gate 3）、RISK-012 `Mitigate`、
 RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RISKS.md`。
@@ -42,14 +43,15 @@ RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RI
 
 | 項目 | 狀態 |
 |------|------|
-| **UG-G1-SB2 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權，SB1 尚未結案 |
+| SB2 步驟 6（送 Gate B、commit） | 在已核准的 Gate A 範圍內，但**尚未執行**；步驟 0、3、4、5 與 §7 文件同步已於 2026-08-25 完成，`src/` 變更尚未 commit，需另行取得 commit scope 授權 |
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
index 9c73fe0..a00458f 100644
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
+        return _placeholder_figure(mode, height=380)
+
     try:
         import plotly.graph_objects as go
 
@@ -167,34 +236,43 @@ def render_pnl_equity_curve_chart(df: pd.DataFrame, market: str = "TW") -> Any:
         ))
 
         fig.update_layout(
-            title="📊 累積報酬率回測曲線 (Cumulative Strategy Return %)",
+            title=dict(text="📊 累積報酬率回測曲線 (Cumulative Strategy Return %)", y=0.97, yanchor="top"),
             template="plotly_dark",
             paper_bgcolor="#1E222D",
             plot_bgcolor="#1E222D",
             font=dict(color="#E0E3EB"),
-            margin=dict(l=40, r=40, t=50, b=30),
-            height=320,
+            margin=dict(l=40, r=40, t=60, b=70),
+            height=380,
             hovermode="x unified",
-            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
+            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
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
+    mode: DataMode = DataMode.REAL,
 ) -> Any:
     """
-    繪製模型 Top N 關鍵特徵重要性長條圖。
+    繪製模型全特徵貢獻度圓餅圖。
+    mode=ERROR／EMPTY 時回傳不含任何數值的佔位圖表；mode=DEMO 時正常繪圖但疊加醒目浮水印。
     """
+    if mode in (DataMode.ERROR, DataMode.EMPTY):
+        return _placeholder_figure(mode, height=380)
+
     try:
         import plotly.graph_objects as go
 
@@ -210,36 +288,41 @@ def render_feature_importance_bar_chart(
                 "sentiment_lag_1": 0.06
             }
 
-        sorted_items = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:top_n]
-        feat_names = [x[0] for x in sorted_items][::-1]  # 倒序以利由上往下排
-        feat_values = [x[1] * 100.0 for x in sorted_items][::-1]
+        sorted_items = sorted(importances.items(), key=lambda x: x[1], reverse=True)
+        feat_names = [x[0] for x in sorted_items]
+        feat_values = [x[1] * 100.0 for x in sorted_items]
 
-        # 為情緒類特徵加上醒目色彩
-        bar_colors = ["#2962FF" if ("sentiment" in f or "bullish" in f or "agree" in f) else "#00C853" for f in feat_names]
+        # 為情緒類特徵加上醒目色彩，與長條圖版本沿用相同配色語意
+        slice_colors = ["#2962FF" if ("sentiment" in f or "bullish" in f or "agree" in f) else "#00C853" for f in feat_names]
 
-        fig = go.Figure(go.Bar(
-            x=feat_values,
-            y=feat_names,
-            orientation="h",
-            marker_color=bar_colors,
-            hovertemplate="<b>特徵:</b> %{y}<br><b>貢獻權重:</b> %{x:.1f}%<extra></extra>"
+        fig = go.Figure(go.Pie(
+            labels=feat_names,
+            values=feat_values,
+            hole=0.35,
+            sort=False,
+            marker=dict(colors=slice_colors, line=dict(color="#1E222D", width=1)),
+            hovertemplate="<b>特徵:</b> %{label}<br><b>貢獻權重:</b> %{value:.1f}%<extra></extra>"
         ))
 
         fig.update_layout(
-            title=f"🧠 Top {top_n} 驅動特徵貢獻度 (Feature Importance %)",
+            title="🧠 全特徵貢獻度 (Feature Importance %)",
             template="plotly_dark",
             paper_bgcolor="#1E222D",
             plot_bgcolor="#1E222D",
             font=dict(color="#E0E3EB"),
-            margin=dict(l=40, r=40, t=50, b=30),
-            height=320,
-            xaxis=dict(title="重要性權重 (%)", showgrid=True, gridcolor="#2B313F"),
-            yaxis=dict(showgrid=False)
+            margin=dict(l=20, r=20, t=50, b=20),
+            height=380,
+            legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.0)
         )
+        if mode == DataMode.DEMO:
+            fig = _apply_demo_watermark(fig)
         return fig
 
     except ImportError:
-        return _FallbackPlotlyFigure(
-            data=[{"type": "feature_importance"}],
-            layout={"top_n": top_n}
+        fig = _FallbackPlotlyFigure(
+            data=[{"type": "feature_importance_pie"}],
+            layout={}
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
index a78186e..601752f 100644
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
@@ -136,6 +236,11 @@ def generate_mock_ptt_articles(stock_id: str, limit: int = 20) -> pd.DataFrame:
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
@@ -211,9 +316,11 @@ def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optiona
             df_features = df_features.iloc[-days:].reset_index(drop=True)
             
         return df_features
+    except DataSourceError:
+        raise
     except Exception as e:
-        logger.debug(f"PostgreSQL 特徵讀取異常，啟用離線 Fallback: {e}")
-        return None
+        logger.warning(f"PostgreSQL 特徵讀取異常: {e}")
+        raise DataSourceError(str(e)) from e
 
 
 def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Optional[pd.DataFrame]:
@@ -223,6 +330,11 @@ def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Option
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
@@ -280,134 +392,112 @@ def _fetch_real_stock_articles_from_db(stock_id: str, limit: int = 25) -> Option
         conn.close()
         
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
+
+    if not keywords:
+        return [], DataMode.EMPTY
+    return keywords, DataMode.REAL
 
 
-def load_thematic_radar_data() -> List[Dict[str, Any]]:
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
index 83a1649..b64d06a 100644
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
@@ -166,23 +280,42 @@ class DataLoaderContractTests(unittest.TestCase):
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
         imp = {"bullishness_index": 0.35, "rsi_14": 0.25, "sentiment_3d_ma": 0.20}
-        fig = render_feature_importance_bar_chart(imp, top_n=5)
+        fig = render_feature_importance_bar_chart(imp)
         self.assertTrue(hasattr(fig, "to_dict") or hasattr(fig, "data"))
 
 
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

## 2. 產出 1：契約驗證原始輸出

```bash
python scripts/verify/gate0_contract_check.py
echo "EXIT=$?"
```

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

執行環境：host（Python 3.10.11）——純文件與 git 層次的靜態檢查，符合 `CLAUDE.md` §13.0 host 允許用途。

---

## 3. 產出 2：執行環境 + 測試原始輸出 + 依賴狀態表

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
Ran 173 tests in 5.951s

OK
```

173 = 164（SB1 commit `ccf0e52` 基線）+ 9 個新增。全套測試已在本文件 §0 列出的多次
往返（實作、格式還原、known-FAIL 示範還原）後**重複驗證均為 173/173 PASS**，非單次僥倖。
第二輪（Streamlit 視覺驗證發現當機 bug 修復後＋兩項圖表調整後）在同一個容器重跑**仍為 173/173 PASS**
（未新增、未減少測試項目，只改了 `test_ui_contracts.py` 內一行已失效的 `top_n=5` 引數呼叫方式）。

### 3c. 依賴狀態表

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode stock_prediction_system2_devcontainer-app-1 \
  python -c "import importlib.util as u; [print(f'{m:26}', 'PRESENT' if u.find_spec(m) else 'ABSENT') for m in ['numpy','pandas','streamlit','plotly','sklearn','lightgbm','xgboost','psycopg2','jieba','snownlp','tenacity','dotenv']]"
```

```
numpy                      PRESENT
pandas                     PRESENT
streamlit                  PRESENT
plotly                     PRESENT
sklearn                    PRESENT
lightgbm                   PRESENT
xgboost                    PRESENT
psycopg2                   PRESENT
jieba                      PRESENT
snownlp                    PRESENT
tenacity                   PRESENT
dotenv                     PRESENT
```

**12/12 PRESENT**——全部走真實路徑，無 fallback／mock 降級。本結果可支撐 ML／NLP／DB 路徑的宣稱。

---

## 4. 產出 3：檔案清單與逐檔授權稽核

```bash
git status --porcelain
```

```
 M app.py
 M doc/evidence/DECISIONS.md
 M doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
 M doc/evidence/TRACEABILITY.md
 M doc/governance/PROJECT_STATUS.md
 M src/ui/charts.py
 M src/ui/components.py
 M src/ui/data_loader.py
 M tests/test_operational_ux.py
 M tests/test_real_articles_pipeline.py
 M tests/test_ui_contracts.py
?? doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md
?? doc/upgrade/gates/SB2_STEP0_4_5_RECORD.md
?? doc/upgrade/gates/SB2_STEP3_IMPLEMENTATION_REPORT.md
?? tests/schema_smoke_ui_data_loader.py
```

> **尚未 `git add`**，本表對照的是工作區變更，非 staged 內容。

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `src/ui/data_loader.py` | 在授權交付物內 | `SB2_GATE_A_PROPOSAL.md` §5.5 步驟 3 明列 |
| `src/ui/components.py` | 在授權交付物內 | 同上 |
| `src/ui/charts.py` | 在授權交付物內 | PO §8 第 2 項明確要求（原提案未定案，PO 核准後才確定納入） |
| `app.py` | 在授權交付物內 | §5.5 步驟 3 明列（解包元組、mode 分流、全域來源追蹤） |
| `tests/test_ui_contracts.py` | 在授權交付物內 | §4 HERM-03~09 修復對照表明列 |
| `tests/test_operational_ux.py` | 在授權交付物內 | §4 HERM-01 修復對照表明列 |
| `tests/test_real_articles_pipeline.py` | 在授權交付物內 | §4 HERM-02 修復對照表明列 |
| `tests/schema_smoke_ui_data_loader.py`（新檔） | 在授權交付物內 | PO §8 第 6 項明確要求新增 |
| `doc/evidence/DECISIONS.md` | 在授權交付物內 | PO 本輪明確要求「§7 的文件同步...一併排進 Gate B 準備裡」；新增 DEC-012 |
| `doc/evidence/TRACEABILITY.md` | 在授權交付物內 | 同上 |
| `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 在授權交付物內 | 同上 |
| `doc/governance/PROJECT_STATUS.md` | **不在 §7 明列清單，屬狀態追蹤慣例** | 與 SB1 各步驟的既有做法一致，非新增授權範圍 |
| `doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md` | 在授權交付物內 | 提案本體，PO 已核准其內容 |
| `doc/upgrade/gates/SB2_STEP3_IMPLEMENTATION_REPORT.md`（新檔） | 在授權交付物內 | PO 要求的步驟 3 完成後回報 |
| `doc/upgrade/gates/SB2_STEP0_4_5_RECORD.md`（新檔） | 在授權交付物內 | PO 本輪明確要求補齊步驟 0／4／5 記錄 |

**本次無超出授權清單的檔案。**

---

## 5. 產出 4：格式／行尾夾帶偵測

### 5a. 本輪最終檢查結果

```bash
git diff --numstat > /tmp/ns_raw.txt
git diff --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

```
1c1
< 117	81	app.py
---
> 57	21	app.py
8c8
< 245	154	src/ui/data_loader.py
---
> 191	100	src/ui/data_loader.py
WSDIFF_EXIT=1
```

（`app.py` 的數字較第一輪各增 3，與本輪新增的 3 處 `st.plotly_chart(..., key=...)` 實質內容變更一致，
非新增空白夾帶；`src/ui/data_loader.py` 本輪未變動，數字與第一輪相同。）

### 5b. 完整還原事件記錄（本輪最重要的一項揭露）

**PO 逐行核對 diff，發現 `src/ui/data_loader.py` 有格式夾帶**——與 `SB1_GATE_B_SUBMISSION.md` §5
記錄的那次同源：`Write` 工具整檔重寫時，把原檔中帶尾隨空白的空行正規化為真空行。

**PM 獨立擴大搜尋範圍，額外找到 4 處**：原判斷只處理 PO 指出的「空白行」類別（15 處），
複查後發現還有「內容行尾多一個空格」的類別（4 處，皆在 SQL 查詢字串內：`SELECT `、`CASE `、
`articles_query, `、`conn, `），合計 **19 處**。

**還原方法**：以 `git show HEAD:src/ui/data_loader.py` 取得原始位元組，逐一以「前一行＋後一行」
的唯一上下文定位每一處，非整檔還原（避免連帶丟失本次合法新增的內容）。

**還原後驗證**：

```bash
grep -n " $" src/ui/data_loader.py | wc -l
```
```
19
```
與還原筆數精確一致，無新增、無遺漏。

**本次額外教訓（已寫入記憶體，供未來 session 參考）**：`git diff --check` **無法**單獨排除這類
格式夾帶——它只標記**新增**的行尾空白，標記不到**消失**的行尾空白。這 19 處全部是空白被拿掉
（不是加上），因此每一次執行 `git diff --check` 都只顯示既有的 CRLF 提示，從未對這 19 處發出
任何警告。後續若再用 `Write` 工具整檔重寫既有檔案，必須額外執行「原檔逐行掃描空白異常
（`grep -n "^[ \t]\+$"` 與 `grep -n "[^ \t]  *$"`）並逐一比對新檔」，不能只看 `--check` 有沒有噪音。

### 5c. 還原後最終確認

```bash
git diff --check
```

```
warning: in the working copy of 'app.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'doc/governance/PROJECT_STATUS.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/charts.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/components.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/data_loader.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_operational_ux.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_real_articles_pipeline.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_ui_contracts.py', LF will be replaced by CRLF the next time Git touches it
```

（既有 CRLF 提示，無新增 trailing-whitespace 錯誤——但如 §5b 所述，此結果本身不足以證明
「無格式夾帶」，需搭配逐行掃描。）

### 5d. 剩餘 numstat 落差的說明（非格式夾帶）

還原 19 處後，`app.py`、`src/ui/data_loader.py` 仍有 `-w` 落差，**已排除為格式夾帶**：

- `app.py`：KPI／預測邏輯整段移入新的 `if features_usable: ... else: ...` 條件區塊，
  約 40 行縮排層級改變，屬合法重新縮排。
- `src/ui/data_loader.py`：大量新內容（`DataMode`／`DataSourceError`／`demo` 參數處理）
  插入既有函式之間，改變既有程式碼的前後文位置，是 diff 演算法對「大範圍插入」的正常表現
  （既有函式本體逐行比對後內容完全相同，僅顯示為刪除＋重新插入，而非真正修改）。

第二輪新增的 `app.py` +3/+3（117/81 vs 57/21）：三處 `st.plotly_chart(fig, use_container_width=True)`
改為 `st.plotly_chart(fig, use_container_width=True, key="...")`，每處新增一個實質對比字串的 `key=` 引數，
不是空白變化。`src/ui/charts.py` 本輪雖有實質重寫（PnL 圖例位置、特徵重要性改圓餅圖），
`git diff --numstat` 與 `-w` 完全一致（無落差），未列入上表。

---

## 6. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 不可重跑原因 |
|------|---------|--------------------------|
| contract-check 11/11 PASS | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py` |
| 全套測試 173/173 PASS（container，15 套件齊備） | `VERIFIED THIS SESSION` | §3b 指令；本次已重跑 4 次以上（實作後、格式還原後、兩次 known-FAIL 示範還原後），結果一致 |
| 依賴表 12/12 PRESENT | `VERIFIED THIS SESSION` | §3c 指令 |
| 靜態 `connect()` 呼叫點 10 處，未增加 | `VERIFIED THIS SESSION` | `grep -c "\.connect(" src/loaders/db_writer.py src/ui/data_loader.py` |
| Runtime 攔截數 0 次（BEFORE 9 次） | `VERIFIED THIS SESSION` | `SB2_STEP0_4_5_RECORD.md` §4 完整腳本；PM 與 PO 各自獨立重跑，結果一致（互相印證） |
| 步驟 0 覆蓋歸因：A 類 28 個測試 | `VERIFIED THIS SESSION` | `SB2_STEP0_4_5_RECORD.md` §1、§4 |
| 步驟 4 AFTER 快照：164→173 逐檔比對零意外落差 | `VERIFIED THIS SESSION` | `SB2_STEP0_4_5_RECORD.md` §2 |
| `data_loader.py` 19 處格式夾帶已還原、無殘留 | `VERIFIED THIS SESSION` | §5b；`grep -n " $" src/ui/data_loader.py \| wc -l` → 19，與還原筆數一致 |
| DEC-012 方案 B：ERROR 不自動退回 DEMO | `VERIFIED THIS SESSION` | §7 known-FAIL 案例 1（實際注入 bug 並確認測試攔下） |
| Schema smoke test 對欄位缺漏具偵測力 | `VERIFIED THIS SESSION` | §7 known-FAIL 案例 2（實際注入不存在欄位並確認測試攔下） |
| 4 個 schema 代表查詢對真實 schema.sql 相容 | `PREVIOUSLY VERIFIED` | 記錄位置：`SB2_STEP3_IMPLEMENTATION_REPORT.md` §5（2026-08-25 執行，臨時 DB `sb2_smoke_tmpdb`，已拆除），本次未重跑；known-FAIL 示範改用另一個臨時 DB（`sb2_knownfail_tmpdb`，已拆除） |
| §7 文件同步（DEC-012／TRACEABILITY.md／DOCUMENT_DRIFT_REMEDIATION.md）已完成 | `VERIFIED THIS SESSION` | `SB2_STEP0_4_5_RECORD.md` §5 逐項核對 |
| Streamlit 真實執行環境的視覺呈現（浮水印／橫幅） | `VERIFIED THIS SESSION` | 於獨立臨時容器（`sb2_streamlit_visual`，掛載真實原始碼、獨立 port，非開發容器）以 `streamlit run app.py` 實際啟動，claude-in-chrome 逐一截圖 ERROR／REAL／DEMO 三態；容器已 `docker rm -f` 拆除 |
| ERROR 模式下 `StreamlitDuplicateElementId` 當機並已修復 | `VERIFIED THIS SESSION` | 修復前重現一次（截圖含 traceback），修復後（三處 `st.plotly_chart` 加 `key=`）重跑 ERROR 模式二次確認不再當機 |
| PnL 圖表標題／圖例重疊已修復；特徵重要性改圓餅圖並顯示全部 18 特徵 | `VERIFIED THIS SESSION` | REAL 模式截圖確認標題不再遮擋；圓餅圖圖例是否被容器裁切另以 `javascript_tool` 量測 DOM `getBoundingClientRect()` 確認 `overflowsRight: false`，非僅憑截圖判斷 |

---

## 7. 產出 6：known-FAIL 案例對照表

| 檢查 / 機制 | known-FAIL 案例 | 實測結果 | 復原確認 |
|------------|----------------|---------|---------|
| **DEC-012 方案 B**：ERROR 不得自動退回 DEMO | 暫時把 `load_ai_discovered_keywords` 的 ERROR 分支改回舊行為（`return list(DEFAULT_AI_KEYWORDS), DataMode.DEMO`，模擬 SB2 之前的靜默 fallback），單行 Edit | `test_load_ai_discovered_keywords_falls_back_when_db_fails` 變 `FAIL`：`AssertionError: DataMode.DEMO != DataMode.ERROR`——證實這是 SB2 存在的理由本身（禁止假資料撐場面）真的被測試守著，不是裝飾性斷言 | 已用 Edit 改回原樣；`git diff --stat` 與注入前完全相同（245 insertions(+), 154 deletions(-)）；全套測試還原後重跑 173/173 PASS |
| **Schema smoke test**：欄位缺漏偵測力 | 在 `test_stock_prices_query_executes_and_columns_match` 的預期欄位清單加入一個不存在的欄位 `nonexistent_column_xyz`，對臨時 DB（`sb2_knownfail_tmpdb`，port 55436，已拆除）重跑 | `FAIL`：`AssertionError: 'nonexistent_column_xyz' not found in Index([...])`——證實此類測試不是「查詢不拋錯就一定綠燈」的裝飾性檢查，真的會抓到欄位契約不符 | 已用 Edit 改回原樣；`py_compile` 確認語法正常；臨時 DB 已 `docker rm -f -v` 拆除 |
| numstat vs `-w` 格式夾帶偵測 | **本輪的真實 organic 案例**：`src/ui/data_loader.py` 因 `Write` 整檔重寫產生 19 處純空白格式夾帶（15 空白行 + 4 內容行尾空格），由 **PO 逐行核對真實抓到**，PM 複查後再擴大找出全部範圍 | `git diff --numstat` 於還原前顯示落差，還原後 `grep -n " $" \| wc -l` = 19（與還原筆數精確一致）——本檢查本輪**兩次**（PO 一次、PM 複查一次）都真的攔下了問題，不是紙上談兵 | 已於 §5b 完整記錄；工作區狀態除本次合法變更外無殘留 |
| `git diff --check` 作為格式夾帶排除依據 | **known-FAIL 案例即為本輪教訓本身**：19 處格式夾帶全部通過 `git diff --check` 而未被標記（因為都是空白**消失**而非新增） | 證實 `git diff --check` 對這類「空白消失」的格式夾帶**結構上無偵測能力**——不是本次沒調對參數，是這個工具的原理限制 | 已記錄於 §5b 與個人記憶體（`git-diff-check-blind-spot.md`），作為本專案往後執行 `Write` 整檔重寫時的強制附加檢查 |
| `gate0_contract_check.py`（B1~B11 契約檢查） | 本次未重新示範；已於 Gate 0（B4/B8 校正事件）與 SB1 Gate B 獨立確認過 | — | `PREVIOUSLY VERIFIED`，不在本次範圍內重複驗證 |
| GOV-02 sentinel（runtime `connect()` 攔截機制） | 本次未刻意示範其能攔截真實連線失敗以外的情境；但**本次執行本身即是它發揮作用的證據**——全套 173 個測試在 `connect()` 被強制攔截、每次呼叫皆拋例外的情況下仍全數 PASS，證明沒有任何測試僥倖依賴真實連線成功 | `RUNTIME_INTERCEPTIONS=0`，`SUMMARY total=173 fail=0 error=0` | 機制為唯讀攔截（monkeypatch `psycopg2.connect`），未修改任何追蹤檔案 |
| Streamlit 視覺驗證（本身作為一種檢查） | **本輪的真實 organic 案例**：ERROR 模式第一次啟動即因 `render_pnl_equity_curve_chart` 與 `render_feature_importance_bar_chart` 在 ERROR／EMPTY 分支回傳結構完全相同的 `_placeholder_figure`，導致 Streamlit 對兩個 `st.plotly_chart` 自動產生相同 element ID 而拋出 `StreamlitDuplicateElementId`，整頁當機顯示 traceback | 這不是刻意注入的 known-FAIL 案例，而是視覺驗證第一次執行就攔下的真實缺陷——結構性測試（`hasattr(fig, "to_dict")`）對此完全沒有偵測能力，因為它從不會把兩個圖表同時放進同一個 Streamlit session 檢查 element ID 衝突。證實「肉眼視覺驗證」這道關卡本身有偵測力，不是走過場 | 已修復（三處 `st.plotly_chart` 加明確 `key=`），修復後 ERROR／REAL／DEMO 三態重新截圖確認正常；`git diff --numstat` 與 `-w` 核對 `charts.py` 無格式夾帶落差 |

**與 SB1 Gate B 的差異**：SB1 的 known-FAIL 表最後留了兩項「未獨立示範」的誠實揭露，PO 隨後要求補做。
本次 Gate B 文件**在送審前就主動補上兩個核心機制的 known-FAIL 示範**（ERROR 不自動 fallback、
schema smoke test 偵測力），吸取了 SB1 的經驗，不再留到 PO 讀完才發現缺口。

---

## 8. 尚未解決／請 PO 裁決事項

1. **（已解決）Streamlit 視覺呈現肉眼確認**：已於獨立臨時容器實際執行 `streamlit run app.py`，
   ERROR／REAL／DEMO 三態逐一截圖並肉眼檢視（見 §1 附註、§6、§7 新增列）。過程中額外發現並修復一個
   ERROR 模式當機 bug（`StreamlitDuplicateElementId`），以及完成 PO 臨時提出的兩項圖表調整
   （PnL 圖例遮擋、特徵重要性改圓餅圖）。**PO 已決定將本輪新增內容併入本份 Gate B 文件**（而非另立
   新文件或新 SB），本次更新即為落實此決定；§1 diff、§5 numstat、§6 證據表、§7 known-FAIL 表均已同步。
2. **`demo=True` 目前無 UI 觸發入口**（DEC-012 Remaining Risks 已登錄）：`app.py` 不曾傳入
   `demo=True`，DEMO 模式目前只能透過直接呼叫 `load_stock_features(..., demo=True)` 等方式觸發，
   沒有畫面上的開關。PO 先前表示「不用做到 UI 開關」，此處僅重申以免遺漏，非請求變更範圍。
3. **（已解決）DEC-012 狀態**：PO 於授權本次 commit 時一併明確核准，狀態已由 `Proposed` 改為
   `APPROVED`（`doc/evidence/DECISIONS.md` DEC-012，2026-08-25）。

**commit 授權**：本文件為送審文件，不代表 commit 已獲授權。若 PO 決定放行，請明確指出授權範圍
（哪些檔案）；`gate-submit` skill 的自檢流程第 3～5 步（`git add`、逐檔稽核、格式偵測）將在
取得授權後於 commit 前重新針對實際 staged 內容執行一次。
