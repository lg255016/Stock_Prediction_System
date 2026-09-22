# REAL_ARTICLES_READING_PLAN.md — 真實社群輿情文章讀取與空資料透明化升級計畫書

> **專案使命**：徹底解決 Streamlit 介面中「PTT 股市版社群輿情明細」顯示重複假文章模板之問題。建立「個股實體 ➔ 題材關聯 ➔ 標題模糊搜尋」三重真實文章查詢引擎，並淘汰假資料模板，落實金融資料透明度與真實資料血緣（Data Lineage）。

---

## 1. 現狀問題與根因剖析 (Problem Statement & Root Cause)

1. **查詢限制過窄**：
   現有 `_fetch_real_stock_articles_from_db()` 僅以 `entity_mapping` 精確比對 `fetch_keyword`（例如 `stock_id = '2330' ➔ fetch_keyword = '台積電'`）。
   * 當使用者切換至題材概念股（如 `3081 聯亞`、`3324 雙鴻`、`3131 弘塑`）時，因未查詢 `theme_stock_mapping` 所屬題材詞（如 `矽光子`、`散熱模組`、`CoWoS`），導致查詢回傳 0 筆。
2. **缺乏標題全域比對**：
   PTT 爬蟲抓取文章時，有些討論個股的文章其 `fetch_keyword` 可能是總經詞或產業詞，但標題內明確包含 `2330` 或 `台積電`。目前的查詢條件漏掉了標題關鍵字檢索。
3. **假資料模板遮蔽真實狀態**：
   當查無資料時，系統呼叫了 `generate_mock_ptt_articles`，產生 8 篇固定模板（`[標的] ... 業績噴發 多`、`[新聞] ... Q3 財報`），讓使用者誤以為是系統產生之假資料或標題錯誤。

---

## 2. 架構升級目標與不可違反原則 (Architecture Objectives & Invariants)

1. **三重階梯式真實查詢引擎 (Three-Tier Article Query Engine)**：
   * **Tier 1 (Direct Entity Mapping)**：查詢 `entity_mapping` 中與該股票直接關聯的關鍵字（如 `2330 ➔ 台積電`）。
   * **Tier 2 (Thematic Spillover Mapping)**：查詢 `theme_stock_mapping` 中該股票所屬題材的所有關鍵字（如 `3081 ➔ 矽光子`）。
   * **Tier 3 (Title Substring Search)**：針對 `market_articles` 的 `title` 欄位進行 `ILIKE %stock_id% OR ILIKE %stock_name%` 全域搜尋。
2. **淘汰偽造假模板，落實空狀態透明化 (Zero-Mock Invariant)**：
   * 查無文章時，**嚴禁偽造假新聞或假標題**。
   * 介面明確渲染高質感 Empty State 資訊卡片：「*💡 目前資料庫中暫無【股票名稱/代碼】之社群討論文章，特徵工程已依金融規範自動給予中立情緒分數（0.50）。*」
3. **100% 保持 UI 資料契約與相容性**：
   * 輸出之 DataFrame 欄位契約保持不變：`['publish_time', 'stock_id', 'title', 'sentiment_score', 'sentiment_label', 'push_count', 'source']`。

---

## 3. 小批次實作拆解 (Small Batch Decomposition)

本升級依據 `small-batch-orchestrator` 標準規範，拆解為 3 個獨立可測之小批次：

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        真實社群輿情讀取升級 Small Batch 規劃                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【SB-ART1】資料層：三重階梯式真實文章查詢引擎實作                                      │
│   • 修改 src/ui/data_loader.py 中的 _fetch_real_stock_articles_from_db()               │
│   • 整合 entity_mapping + theme_stock_mapping + title ILIKE 全域檢索                   │
│   • 確保回傳真實資料 DataFrame (無資料回傳 empty DataFrame，不拋 None)                 │
│                                           ▼                                            │
│ 【SB-ART2】展示層：空資料透明化與 UI 輿情明細渲染升級                                   │
│   • 改造 src/ui/components.py 中的 render_raw_article_table()                         │
│   • 支援真實文章標籤篩選、關鍵字搜尋、情感顏色高亮                                    │
│   • 實作高質感 Empty State Banner，淘汰 generate_mock_ptt_articles 假模板               │
│                                           ▼                                            │
│ 【SB-ART3】測試層：端到端契約測試、防回歸與文檔同步                                    │
│   • 建立 tests/test_real_articles_pipeline.py 專項測試 (涵蓋多層查詢與空狀態)          │
│   • 更新 tests/test_ui_contracts.py                                                    │
│   • 確保全套 150+ 項測試 100% PASS，同步 PROJECT_STATUS.md 與 DEC-009                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 詳細批次定義：

#### 🔹 【SB-ART1】資料層：三重階梯式真實文章查詢引擎實作
- **修改路徑**：`src/ui/data_loader.py`
- **實作內容**：
  1. 擴充 `_fetch_real_stock_articles_from_db(stock_id, limit=30)`。
  2. 同步撈取 `entity_mapping`（個股詞）與 `theme_stock_mapping`（題材詞）。
  3. 構造強健的 SQL 查詢：
     ```sql
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
     ```
  4. 回傳精確去重後的真實文章 DataFrame。

#### 🔹 【SB-ART2】展示層：空資料透明化與 UI 輿情明細渲染升級
- **修改路徑**：`src/ui/components.py`, `src/ui/data_loader.py`
- **實作內容**：
  1. 在 `src/ui/components.py` 的 `render_raw_article_table()` 中，當 `df_articles` 為空時，渲染深色 Empty State 資訊盒，說明當前標的無社群文章、特徵工程已套用中立平滑，並提示使用者可於排程中新增關鍵字。
  2. 廢除 `generate_mock_ptt_articles` 中的偽造標題模板，將其簡化為純測試用 fixture 或直接回傳空表。

#### 🔹 【SB-ART3】測試層：端到端契約測試、防回歸與文檔同步
- **新增/修改路徑**：`tests/test_real_articles_pipeline.py`, `tests/test_ui_contracts.py`, `doc/engineering/PROJECT_STATUS.md`
- **實作內容**：
  1. 撰寫單元測試：驗證個股關鍵字文章查詢、題材關聯文章查詢、標題模糊匹配文章查詢。
  2. 驗證空資料時 UI 渲染零崩潰且正確呈現 Empty State。
  3. 運行全套自動化測試（目標 150+ 項全數 PASS）。
  4. 同步 `PROJECT_STATUS.md`。

---

## 4. 驗收標準 (Definition of Done)

1. **真實性驗證**：切換股票標的時，輿情明細表只顯示從 PostgreSQL 爬取入庫之真實 PTT 文章，標題不再千篇一律。
2. **題材連動驗證**：切換至題材概念股（如聯亞、雙鴻）時，自動帶出所屬題材（矽光子、散熱）的真實 PTT 文章。
3. **空狀態透明化**：若標的無文章，明確呈現友好提示，絕不捏造假標題。
4. **測試覆蓋**：全套自動化測試 100% PASS。
