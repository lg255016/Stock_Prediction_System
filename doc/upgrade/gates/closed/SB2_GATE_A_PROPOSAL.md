# UG-G1-SB2 Gate A 提案：UI Demo/Real 模式分離

> **性質**：Gate A 提案（實作前審批），非實作。
> **提交日期**：2026-08-25
> **前置**：UG-Gate-1 已由 PO 核准（逐 SB 授權）；UG-G1-SB1 已於 2026-08-25 結案（commit `ccf0e52`）
> **狀態**：`src/` 未動，diff 為空
> **本次與 SB1 的差異**：PO 明確要求本次在核准**前**就審查（SB1 是事後接手），
> 故本提案在送審前已完成程式碼現況逐行核對，避免出現需要事後修正的設計缺口。

---

## 1. 本提案要解決的三件事

| # | 來源 | 內容 |
|---|------|------|
| 1 | `SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 UG-G1-SB2 Brief | DataMode 四狀態（REAL/DEMO/EMPTY/ERROR）、`data_loader.py`／`components.py`／`app.py` 改造 |
| 2 | `SB1_GATE_A_PROPOSAL.md` §2.3（PO 已於 SB1 核准） | 併同修復 HERM-01~09 的測試封閉性，使該 9 個測試不再依賴環境憑證與 DB 內容 |
| 3 | 本次新增（提案時發現） | `DEC-012`（UI Four-State Data Mode）目前**尚未寫入** `DECISIONS.md`（僅在 `TRACEABILITY.md` 被列為「規劃中」）；DataMode 在 ERROR 情境下是否仍自動退回 DEMO，是一個現有文件未回答的架構問題，本提案必須先取得 PO 裁決才能實作（見 §3） |

---

## 2. 現況與問題（逐行核對，2026-08-25）

### 2.1 目前的靜默回退鏈

`src/ui/data_loader.py` 目前對外的 4 個公開函式全部只回傳單一值（`DataFrame` 或 `list`），
呼叫端無法得知資料是「真的從 DB 來的」還是「DB 失敗後的替代值」：

| 公開函式 | 內部真實抓取函式 | 失敗/空值時的行為 |
|---------|-----------------|-------------------|
| `load_stock_features()`（L295-302） | `_fetch_real_stock_features_from_db()`（L136-216） | 內部函式在 **exception** 與 **`df_prices` 為空或 <2 列**（L156-158）兩種情況下**都回傳 `None`**——這兩種情況在語意上完全不同（DB 打不通 vs. 打得通但真的沒資料），但現行程式碼把它們**混為一談**。`load_stock_features()` 收到 `None` 或空 DataFrame 時，一律呼叫 `generate_mock_stock_features()`（純亂數模擬），無任何標記 |
| `load_stock_articles()`（L305-315） | `_fetch_real_stock_articles_from_db()`（L219-292） | exception → 回傳 `None`；成功但 0 列 → 回傳**空 DataFrame**（此函式本身已區分兩者，是 4 個函式中最接近正確的一個）。`load_stock_articles()` 收到 `None` 時回傳同欄位的空 DataFrame——**與「成功但無資料」外觀完全相同**，呼叫端仍分不出兩者 |
| `load_ai_discovered_keywords()`（L327-349） | `DBWriter.fetch_ai_discovered_keywords()` | exception 或空結果 → 回傳硬編碼 `default_ai_keywords` 六詞清單，`logger.debug` 記錄，UI 無任何提示 |
| `load_thematic_radar_data()`（L352-501） | 直接 `psycopg2.connect` + 兩段 SQL | exception 或 `df_mappings` 為空 → 回傳硬編碼 `default_radar` 四筆題材，`logger.debug` 記錄，UI 無任何提示 |

**根因與 DRIFT-009 完全一致**：`logger.debug()` 預設不輸出到終端使用者可見的位置，
且四個函式的容錯設計把「DB 連線失敗」「DB 查詢成功但無資料」「刻意使用示範資料」
三種不同情況，壓縮成同一個回傳值形狀，呼叫端（`app.py`）與最終使用者無法區分。

### 2.2 呼叫鏈與受影響元件

`app.py:main()` 呼叫上述 4 個函式（`load_stock_features` 呼叫兩次：`selected_days` 與固定 90 天），
資料流向如下：

```
load_ai_discovered_keywords() ──→ render_ai_trend_discovery_badge()
load_thematic_radar_data()    ──→ render_thematic_radar()
load_stock_features()         ──┬→ KPI 卡片（app.py 內直接算，L141-146）
  (selected_days / 90 天兩份)  │→ render_price_sentiment_candlestick_chart()（charts.py）
                                │→ render_pnl_equity_curve_chart()（charts.py）
                                │→ get_champion_predictor() → render_prediction_panel()
                                └→ render_feature_importance_bar_chart()（charts.py）
load_stock_articles()         ──→ render_raw_article_table()
```

`render_tournament_leaderboard()`（components.py:122）**不接受任何參數**，資料完全來自
`components.py` 內的靜態 dict（DRIFT-008／DRIFT-018 的範疇）——**確認與本提案無關**，
不在本 SB 修改。

### 2.3 HERM-01~09 與本提案的關係

9 個測試呼叫上述公開函式時未做任何 mock，實際執行時是否連真實 DB、DB 內容為何，
完全取決於執行環境（dev container 的 `network_mode: service:db` 使其可直達真實開發 DB）：

| HERM | 測試 | 呼叫的公開函式 | 衍生問題 |
|------|------|---------------|---------|
| HERM-01 | `test_operational_ux.py:74` | `load_ai_discovered_keywords` | HERM-B：測試名稱宣稱測 fallback，但若 DB 有真實資料，測到的**不是** fallback 路徑 |
| HERM-02 | `test_real_articles_pipeline.py:130` | `load_stock_articles` | — |
| HERM-03 | `test_ui_contracts.py:77` | `load_stock_features` | HERM-C：硬斷言 `len(df)==30`，真實 DB 資料不足 30 天即失敗，且無法區分「程式壞了」與「當日資料不足」 |
| HERM-04 | `test_ui_contracts.py:89` | `load_stock_articles` | — |
| HERM-05 | `test_ui_contracts.py:96` | `load_stock_features`（間接） | 繼承 HERM-03 的問題 |
| HERM-06 | `test_ui_contracts.py:152` | `load_thematic_radar_data` | — |
| HERM-07 | `test_ui_contracts.py:174` | `load_stock_features`（間接） | 繼承 HERM-03 的問題 |
| HERM-08 | `test_ui_contracts.py:179` | `load_stock_features`（間接） | 繼承 HERM-03 的問題 |
| HERM-09 | `test_ui_contracts.py:222` | `load_thematic_radar_data`（間接） | — |

**HERM-D**（測試名稱「18 欄位」為 DRIFT-001 過期數字）**不在本 SB 處理**——那是特徵契約命名問題，
歸屬 UG-G1-SB5，本 SB 若順手改掉名稱中的數字，等於在未授權範圍內動了特徵契約措辭，**明確排除**。

---

## 3. 設計決策：DataMode 語意（需要 PO 裁決）

### 3.1 已經清楚、不需要裁決的部分

```python
class DataMode(Enum):
    REAL = "real"    # DB 連線成功且回傳非空資料
    DEMO = "demo"     # 展示用模擬資料（無論觸發原因），UI 必須顯著標示（Banner + 浮水印）
    EMPTY = "empty"   # DB 連線成功，查詢結果為零筆（非模擬，是真實的「沒有」）
    ERROR = "error"   # DB 連線或查詢本身失敗
```

REAL／EMPTY／ERROR 三者的判定條件明確：需要先把 `_fetch_real_stock_features_from_db()`
與 `load_thematic_radar_data()` 內部「exception」與「成功但空」兩種現行都回傳 `None`／
觸發 default 的路徑**拆開**——exception 改為拋出明確的 `DataSourceError`（新增，僅供
`src/ui/` 內部使用，不外洩至 `app.py`），成功但空的情況改為回傳**真正的空結果**（空
DataFrame／空 list），而非 `None`。

### 3.2 唯一需要 PO 裁決的問題：ERROR 時是否仍自動顯示 DEMO 資料

`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 的 Failure Semantics 寫著：

> DB 連線失敗 → ERROR 模式 (不顯示數值); DB 回傳空 → EMPTY 模式; Mock → DEMO 模式 (醒目標示)

字面上把三者列成三個獨立的觸發來源，但沒有回答一個實際會發生的情境：
**DB 連線失敗時，UI 究竟要顯示「空白／錯誤訊息」（嚴格對應 ERROR），
還是要顯示「標示清楚的模擬資料」（退回 DEMO，只是不再偽裝成 REAL）？**

現行程式碼的行為是後者（自動退回 mock），問題只在於**沒有標示**——這正是 DRIFT-009
要修的東西。但「DB 失敗時完全不顯示模擬資料」是一個更嚴格、會改變現有使用者體驗的選擇。

| 方案 | 行為 | 優點 | 缺點 |
|------|------|------|------|
| **A（建議）**：ERROR 時自動退回 DEMO，但顯著標示 | 連線失敗 → 顯示 `generate_mock_stock_features()` 等既有模擬資料，UI 加上醒目 Banner／浮水印「⚠️ 目前顯示離線模擬資料」；ERROR 與 DEMO 在 DataMode 上仍是兩個不同的列舉值，但 UI 呈現上 ERROR 情境**視覺上等同 DEMO**（不是空白頁） | 修復 DRIFT-009 的核心問題（透明度）同時不犧牲既有的「有東西可看」的展示體驗；本專案作為轉職作品集，需要在沒有即時 DB 資料時仍能展示介面完整性 | 嚴格說「DB 連線失敗」與「刻意使用模擬資料」被 UI 呈現成同一種視覺狀態，兩者的 `DataMode` 值不同但畫面相同，需要在 §7 文件同步時說明清楚這個折衷 |
| **B**：ERROR 時顯示空白／錯誤訊息，完全不顯示模擬數字 | 連線失敗 → 對應區塊顯示「⚠️ 資料來源目前無法連線」，不渲染任何 KPI 卡片／圖表數值 | 與 Master Plan 字面定義完全一致；ERROR 與 DEMO 語意純粹不重疊 | 使用者（含未來的作品集審閱者）在 DB 未啟動或未跑過 ETL 時，開啟 UI 會看到大量空白區塊，喪失現有「離線也能展示」的能力；`generate_mock_stock_features()` 等既有生成器變成僅供 DEMO 模式主動啟用（例如一個顯式切換），失去現有「失敗自動有東西可看」的效果 |
| **C**：由使用者控制（Sidebar 開關「離線展示模式」），ERROR 預設走方案 B，但可手動切換成方案 A 的行為 | 新增一個 Sidebar 選項；ERROR 預設空白，使用者可勾選後改顯示模擬資料 | 兩種語意都不遺失，決定權交給檢視者 | 範圍比 Master Plan 原始 Brief 大（新增互動元件），且要多一輪 UI 設計；本 SB 的 In Scope 未列出新增 Sidebar 控制項 |

**PM 建議採方案 A**，理由：
1. 這是本專案的「作品集」定位（`CLAUDE.md` §1）與「DB 失敗透明化」兩個目標的折衷點——
   方案 B 雖然語意最乾淨，但會讓一個沒有先跑 ETL／沒開 DB 的檢視環境幾乎空白，
   不利於這個 Repository 的第二個目的（成果展示）。
2. DRIFT-009 的原始指控是「使用者無法分辨」，不是「不該有模擬資料可看」——
   方案 A 精準對應原始問題，不過度矯正。
3. 方案 C 的互動元件超出 Master Plan 已登記的 In Scope，若要做應該是**追加**而非本 SB 預設路徑。

**此裁決會實際影響程式碼行為（ERROR 分支是否呼叫 mock 生成器），必須在實作前取得 PO 明確選擇**，
選 A、B 或 C 皆可，也可能是 PO 有第四種想法——這正是本提案存在的理由。

---

## 4. HERM-01~09 具體修復對照表

| HERM | 現行問題 | 修復方式 |
|------|---------|---------|
| HERM-01, HERM-B | `test_load_ai_discovered_keywords_fallback` 未 mock，測到的路徑隨環境而定 | 改用 `unittest.mock.patch` 固定 `DBWriter.fetch_ai_discovered_keywords`；拆成至少兩個測試：`test_load_ai_discovered_keywords_returns_real_mode_when_db_has_data`（mock 回傳非空清單，斷言 `DataMode.REAL`）與 `test_load_ai_discovered_keywords_falls_back_when_db_fails`（mock 拋出例外，斷言 `DataMode.DEMO`／`ERROR`，依 §3.2 裁決結果而定，且**真正測到 fallback 路徑**，不再因環境而不確定） |
| HERM-02, HERM-04 | `load_stock_articles` 未 mock | 同上手法：mock `_fetch_real_stock_articles_from_db` 的上游（`psycopg2.connect` 或 `DBWriter`），分別驗證 REAL／EMPTY／ERROR 三種 `DataMode` 下的欄位契約與資料內容 |
| HERM-03, HERM-C | `assertEqual(len(df), 30)` 對 live 資料硬斷言 | mock 出一份**確定性**、恰好 30 列的合成資料集，斷言改為「mock 回傳幾列，`load_stock_features` 就回傳幾列」；不再依賴真實 DB 當天有多少歷史資料 |
| HERM-05, HERM-07, HERM-08 | 間接依賴 HERM-03 的 live 資料 | 隨 HERM-03 的 mock 修復一併固定為確定性資料 |
| HERM-06, HERM-09 | `load_thematic_radar_data` 未 mock | mock `psycopg2.connect` 回傳固定的 `df_mappings`／`df_stats`，驗證 REAL／EMPTY／ERROR 三態下的清單結構與 `default_radar` fallback 內容 |
| HERM-A | 9 個測試整體不具封閉性 | 上述逐項修復後，9 個測試皆改為 mock-only，不再連真實 DB；步驟 5 Sentinel 將以 GOV-02 機制驗證這 9 個測試的 runtime `connect()` 攔截數變為 **0**（見 §5.5） |
| HERM-E | `data_loader.py:214-215` 靜默 `logger.debug` 吞例外 | 隨 §3.1 的 `DataSourceError` 改造一併處理：例外不再被吞掉後回傳 `None`，而是被上一層明確捕捉並轉換為 `DataMode.ERROR`（或依 §3.2 裁決轉為 DEMO），`logger` 呼叫層級同時提升為 `warning`，使其在預設終端輸出可見 |
| HERM-D | 過期「18 欄位」命名 | **不在本 SB 範圍**，歸屬 UG-G1-SB5 |

---

## 5. 驗證計畫（比照 SB1 步驟 0～6 模式）

### 5.1 執行環境

GOV-03 釘選環境（dev container，`requirements.lock.txt`）。

**PO 2026-08-25 補充要求（已納入，非本 PM 原判斷）**：HERM-01~09 修復前是全專案唯一會對
`stock_prices`／`entity_mapping`／`theme_stock_mapping`／`market_articles` 四張表執行真實
SQL 的測試；§4 把它們全部改成 mock 之後，**schema 相容性會變成沒有任何測試在守**——
mock 只驗證「程式碼假設的欄位名稱」，驗證不了「這些欄位名稱在真實 schema 裡還存不存在」。
兩者是完全不同的失敗模式，mock 對後者結構上就沒有偵測能力。

**因此本 SB 除了 §4 的 mock 化測試，另外新增一組獨立的 schema smoke test**：

#### 5.1.1 涵蓋範圍與代表查詢

`src/ui/data_loader.py` 內共有 9 段對這 4 張表的 SQL（同一張表在不同函式內有欄位數不同的
變體）。**本提案採「每張表挑欄位數最多的一段查詢」作為 smoke test 代表**，理由是欄位最多
的查詢對 schema 變動最敏感，能涵蓋到的失敗面最大：

| 表 | 代表查詢來源 | 涵蓋欄位 |
|----|-------------|---------|
| `stock_prices` | `_fetch_real_stock_features_from_db` 的 `price_query`（L148-153） | `trade_date, stock_id, open_price, high_price, low_price, close_price, volume` |
| `entity_mapping` | `_fetch_real_stock_features_from_db` 的 `mapping_query`（L161-165） | `keyword, stock_id` |
| `theme_stock_mapping` | `load_thematic_radar_data` 的 `mapping_query`（L420-424，欄位數最多的版本） | `theme_keyword, stock_id, stock_name, relevance_weight` |
| `market_articles` | `_fetch_real_stock_features_from_db` 的 `articles_query`（L182-187） | `article_id, source, fetch_keyword, post_time, title, url, author, engagement_metric, sentiment_score` |

**提請 PO 確認**：此「每表一個代表查詢」的範圍是否足夠，或希望改為涵蓋全部 9 段 SQL
逐一 smoke test（後者工作量更大但涵蓋更完整）。若未特別指示，本提案採前者執行。

#### 5.1.2 測試設計原則

- 每個 smoke test **只斷言**：(a) 查詢執行不拋出例外，(b) 回傳的 `DataFrame.columns`
  與該表的預期欄位集合相符。**不斷言任何具體數值**——臨時 DB 套用 `schema.sql` 後
  無需額外灌入資料，空表即可驗證欄位相容性（`pd.read_sql` 對 0 列結果仍會回傳
  正確的欄位結構）。
- 直接呼叫 `data_loader.py` 內對應的私有函式（如 `_fetch_real_stock_features_from_db`），
  而非重新謄寫 SQL 字串——避免 smoke test 與production code 各自維護一份 SQL，
  兩者不同步時 smoke test 會測到假的東西。

#### 5.1.3 存放位置：獨立於正式 mock 套件

**依 PO 指示，不進正式 mock 測試套件**。新增檔案 `tests/schema_smoke_ui_data_loader.py`
——**檔名刻意不含 `test_` 前綴**，使 `python -m unittest discover -s tests -p "test_*.py"`
（本專案唯一的標準測試指令）不會自動撿到它，不會在一般測試執行（含未啟動臨時 DB 的情境）
中意外嘗試連線失敗。改以明確的模組路徑手動執行：

```bash
MSYS_NO_PATHCONV=1 docker exec -i -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=localhost -e DB_PORT=<temp_port> -e POSTGRES_DB=<temp_db> \
  -e POSTGRES_USER=<temp_user> -e POSTGRES_PASSWORD=<temp_password> \
  stock_prediction_system2_devcontainer-app-1 \
  python -m unittest tests.schema_smoke_ui_data_loader -v
```

#### 5.1.4 執行程序（比照 SB1 隔離臨時 DB 機制）

獨立臨時 PostgreSQL 容器（不掛 `postgres-data`、獨立埠、匿名 volume）、套用
`database/schema.sql`、以 `DBWriter().db_config` 解析路徑做綁定確認（RISK-013 控制措施，
執行前先呈報）、執行 4 個 smoke test、拆除容器——完整重跑此組 smoke test 屬於**步驟 4
AFTER 快照的一部分**，不是獨立的第七步驟。

#### 5.1.5 定位：本次驗收證據，也是未來的常設資產

這組 smoke test 通過後即完成本 SB 的驗收需求；但檔案本身**不刪除**，留在
`tests/schema_smoke_ui_data_loader.py` 作為往後 `schema.sql` 變動時的迴歸防護——
下次有人改動這 4 張表的欄位，只要沒有手動執行這個檔案就不會發現，這是已知的
**非自動化限制**（不像 `tests/test_*.py` 會被 `discover` 自動撿到），提請 PO 一併知悉；
若未來想讓它自動化（例如掛進 CI 或另一個排程），屬本 SB 之後的追加決定，不在此次核准範圍。

### 5.2 步驟 0：實測覆蓋歸因

以 SB1 同樣的 `sys.settrace` runtime 歸因方法（非 grep 推導），確認哪些現有測試「實際執行到」
`src/ui/data_loader.py`、`src/ui/components.py`、`app.py` 三個目標模組，產出 A／B／C 分類表。
預期 A 類至少涵蓋 9 個 HERM 測試 + `test_ui_contracts.py` 其餘測試方法。

### 5.3 步驟 1：BEFORE 快照

同一釘選環境，執行全套測試並記錄逐測試結果（現行基線：164 tests，UG-G1-SB1 commit `ccf0e52` 後）。
另外**以 GOV-02 sentinel 機制**單獨量測 HERM-01~09 這 9 個測試目前的 runtime `connect()`
攔截次數（預期與 GOV-02 原始基線一致：9 次，對應 4 個呼叫點）——這是本 SB 要歸零的數字，
必須先量出修正前的值。

### 5.4 步驟 2：不適用

SB1 的步驟 2（保存修正前績效基線）是 SB1 特有的 PO 補充要求（保存 `components.py` 排行榜數值）。
本 SB 沒有類似的「污染數值」需要保存，此步驟**不適用**，直接跳至步驟 3。

### 5.5 步驟 3：實作（僅在 PO 核准本提案後）

1. `src/ui/data_loader.py`：新增 `DataMode` enum 與 `DataSourceError`；四個公開函式改回傳
   `(value, DataMode)` 元組；依 §3.2 的 PO 裁決實作 ERROR 分支行為。
2. `src/ui/components.py`：`render_prediction_panel`、`render_raw_article_table`、
   `render_ai_trend_discovery_badge`、`render_thematic_radar` 四個既有元件新增 `mode` 參數，
   非 REAL 時渲染醒目標示（Banner／浮水印，DEMO 與 EMPTY／ERROR 視覺區分）。
3. `app.py`：解包四個函式的元組回傳值，追蹤各區塊的 mode（全域追蹤 = 同一次頁面渲染中
   記錄「本次有哪些區塊處於非 REAL 狀態」，供頂部可能的彙總提示使用；不強制要求單一
   全頁面 mode，因為不同資料來源可能同時處於不同狀態）。
4. 依 §4 逐項重寫 HERM-01~09 對應測試。

### 5.6 步驟 4：AFTER 快照

同一環境重跑全套測試，比照 SB1 的 A／B／C 分類逐項比對：A 類（HERM-01~09 + 其餘直接覆蓋
`data_loader.py`／`components.py`／`app.py` 的測試）任何 before→after 變化需解釋；B 類
（迴歸對照）預期零變化；同時重新以 GOV-02 sentinel 量測 HERM-01~09 的 runtime `connect()`
攔截次數。**另外於同一次臨時 DB 環境內，執行 §5.1.4 的 `tests/schema_smoke_ui_data_loader.py`
4 個 smoke test，全數通過（查詢不拋錯、欄位相符）為本步驟的必要產出，不可省略。**

### 5.7 步驟 5：Sentinel

**核心驗收指標**：HERM-01~09 的 runtime `connect()` 攔截次數必須從 BEFORE 的 9 次降為
**AFTER 的 0 次**——這是「測試封閉性已修復」的可證偽判準（不是「測試還是綠燈」，
而是「測試不再有能力連到真實 DB」）。另外確認 `src/loaders/db_writer.py` 與
`src/ui/data_loader.py` 的靜態 `connect()` 呼叫點數量不因本次重構而改變（除非
`DataSourceError` 的實作方式需要新增呼叫點，屆時須明確揭露新增位置與理由）。

### 5.8 步驟 6：送 Gate B

依 `gate-submit` skill 產出六項證據。

---

## 6. 範圍邊界（本 SB 不做什麼）

| 不做 | 原因 |
|------|------|
| 排行榜動態化（`render_tournament_leaderboard` 讀取真實訓練產出） | 屬 UG-G1-SB3（DRIFT-008），本 SB 不修改 `components.py` 內排行榜相關函式 |
| 回測真實化 | 屬 Gate-4，本 SB 不改變任何回測計算邏輯 |
| 新增 DB 連線重試邏輯（retry/backoff） | Master Plan Out of Scope 明列；`DataSourceError` 只負責語意分類，不新增重試機制 |
| HERM-D（測試名稱「18 欄位」過期數字） | 屬 UG-G1-SB5 特徵契約命名範疇，見 §2.3、§4 |
| 新增 Sidebar「離線展示模式」開關（方案 C） | 除非 PO 在 §3.2 選擇方案 C，否則不在本 SB 範圍 |
| `charts.py`（`render_price_sentiment_candlestick_chart` 等）的浮水印／視覺標示 | Master Plan In Scope 僅列 `components.py`；圖表本身是否也需要 DEMO 浮水印，提請 PO 一併裁決（見 §7），若 PO 未特別要求則本 SB 僅圖表接收 mode 參數但不改變圖表視覺樣式，浮水印只加在 `components.py` 渲染的卡片／表格 |
| `database/`、`main_etl_pipeline.py`、`scheduler.py` | 未搜尋到這些檔案呼叫 `src/ui/data_loader.py` 的公開函式，不受影響，不列入 Affected Components |

---

## 7. 文件同步範圍

| 文件 | 變更 |
|------|------|
| `DECISIONS.md` | 新增 **DEC-012**（UI Four-State Data Mode），狀態 `Proposed`；§3.2 的 PO 裁決結果寫入 Decision 欄 |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` | §7.1 UG-G1-SB2 Brief 視需要微調（若 PO 選擇方案 B 或 C，Failure Semantics 欄需要對應更新） |
| `TRACEABILITY.md` | 新增 DataMode／HERM 修復的追溯列 |
| `DOCUMENT_DRIFT_REMEDIATION.md` | DRIFT-009、HERM-A~C、HERM-E 狀態更新為已修正；HERM-D 狀態維持不變（歸屬 SB5） |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | UI 章節同步 DataMode 契約 |

---

## 8. 請求 PO 裁決

| # | 事項 |
|---|------|
| 1 | §3.2：ERROR 時的 UI 行為——方案 A（建議，自動退回標示清楚的 DEMO）、方案 B（嚴格空白）或方案 C（使用者可切換）？ |
| 2 | §6：圖表（`charts.py`）是否也需要 DEMO／ERROR 視覺標示，或僅 `components.py` 渲染的卡片／表格需要？ |
| 3 | §4／§5 的 HERM 修復與 DataMode 實作是否核准 |
| 4 | §7 的文件同步範圍是否核准（含新增 DEC-012 為 `Proposed` 狀態） |
| 5 | 是否授權進入 SB2 實作（步驟 3） |
| 6 | §5.1.1：schema smoke test 採「每張表一個代表查詢」（4 個測試）是否足夠，或要求涵蓋全部 9 段 SQL（更完整但工作量更大）？ |

**未獲核准前不動 `src/`。**
