# UG-G2-SB5 決策點 5 Gate A 提案：來源能力宣告（Source Capability Declaration）

> 狀態：**Gate A 審查中**（尚未實作，`src/` 一行未動）
> 日期：2026-08-30
> Gate：UG-Gate-2 · `UG-G2-SB5` 決策點 5（獨立 Gate A→B 循環）
> 前置：`UG-G2-SB5` 可用性驗證已完成並判定 `FAIL`／`DEFERRED WITH EVIDENCE`
> （commit `84c6c55`／`eca2f8c`／`a0e4248`）；本決策點 PO 已裁定
> **不分 PASS／FAIL 都要做**，與 Dcard 是否可用無關

---

## 0. 摘要

本 SB 要修的是一個**現在就存在、且與 Dcard 完全無關**的缺陷：

> `feature_aggregator.py` 有**兩道**把 `NULL` 壓成 `0` 的關卡，
> 使「這個來源沒有推噓的概念」被計算成「推噓各 0 則」，
> 進而產出 `comment_polarization = 1.0`（最大分歧）與
> `net_push_momentum = 0.0`（方向毫無變化）——**恆定的偽造強訊號**。

Dcard 判定 `FAIL` 不會讓這個缺陷消失。它等在那裡，
**下一個沒有推噓概念的來源（Threads，RISK-004）踩上去就會觸發**。

**本提案在撰寫過程中發現一個先前未被記錄的整合缺口（§1.6）**：
**真實開發資料庫從未套用過任何一次 migration**——
`market_articles` 仍是 10 欄、`daily_ml_features` 仍是 7 欄、`schema_version` 表不存在。
因此 `db_writer.py:494` 的特徵路徑查詢對真實 DB 執行會直接
`UndefinedColumn` 失敗。這**不是本次要改的東西造成的**，但它決定了
「本 SB 改完之後要怎麼證明它在真實環境可用」，故列為 §9 決策點 1。

---

## 1. Current State（全部逐行核實，`VERIFIED THIS SESSION`）

### 1.1 【核心缺陷】兩道把 `NULL` 壓成 `0` 的關卡

**第一道**，`src/transform/feature_aggregator.py:554-555`：

```python
for col in ['push_count', 'boo_count']:
    df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0)
```

**第二道**，同檔 `:557-560`：

```python
return df.groupby(['trade_date', 'stock_id']).agg(
    push_sum=('push_count', 'sum'),
    boo_sum=('boo_count', 'sum'),
    total_sum=('total_comments', 'sum'),
).reset_index()
```

pandas 的 `sum()` 預設對**全 NaN 群組回 `0.0`**，不是 `NaN`
（容器內實測，pandas 3.0.5：`.agg(push_sum=('push_count','sum'))` → `0.0`；
指定 `min_count=1` → `NaN`）。

> **只拿掉第一道修不好這個 bug。** 刪掉 `fillna(0)` 兩行後測試仍會 FAIL，
> 且看起來像「修了但沒效」——這是本設計必須同時處理兩處的唯一理由。

### 1.2 單一守衛管三個特徵（`:575`）

```python
has_comments = df['total_sum'].notna()
```

三個特徵共用它，但它們對來源的要求**並不相同**：

| 特徵 | 需要什麼 | 有數量無方向的來源 |
|------|---------|------------------|
| `comment_volume_ratio` | 只要**數量** | ✅ 可算 |
| `comment_polarization` | 需要**方向** | ❌ 結構上不可能 |
| `net_push_momentum` | 需要**方向** | ❌ 結構上不可能 |

`push_ratio`（`:578`）不是本專案設計出來的指標——**它之所以存在，
純粹是因為 PTT 的資料結構本來就提供方向**。
要讓沒有推噓標記的來源產生方向，得對**每則留言文字**做 NLP，
而本系統只對**標題**做 NLP，結構上做不到。

### 1.3 `source` 在特徵路徑取不到（讀取端缺口）

| 路徑 | 是否 SELECT `source` |
|------|---------------------|
| 特徵路徑 `db_writer.py:494-497`（`fetch_all_raw_data`） | **否**——只有 9 欄 |
| UI 路徑 `src/ui/data_loader.py:322` | **是** |

`market_articles.source` 是 `VARCHAR(20) NOT NULL`（契約 §2），**資料一直都在**，
只是特徵層的查詢沒撈。`db_writer.py:489-493` 的既有註解已經寫過一次同型缺口的教訓
（`UG-G2-SB4` 的「SB3 完成寫入契約後，此查詢仍未 SELECT 這些欄位」），**這是第二例**。

### 1.4 `required` 集合不含 `source`（`:534`）

```python
required = {'trade_date', 'stock_id', 'total_comments', 'comments_scraped_at'}
```

### 1.5 影響半徑

`grep -rln "feature_aggregator" tests/` → **12 個測試檔**，
`def test_` 合計 **117 個測試**：

| 檔案 | 測試數 | | 檔案 | 測試數 |
|------|------|---|------|------|
| `test_canonical_stock_id.py` | 17 | | `test_nlp_checkpoint_semantics.py` | 11 |
| `test_time_series_split.py` | 16 | | `test_feature_aggregator_alignment.py` | 8 |
| `test_time_alignment.py` | 13 | | `test_ml_feature_store_contract.py` | 8 |
| `test_comment_features.py` | 13 | | `test_research_features.py` | 6 |
| `test_db_read_semantics.py` | 14 | | `test_thematic_feature_spillover.py` | 5 |
| `test_generate_tournament_artifact.py` | 4 | | `test_nlp_resilience_e2e.py` | 2 |

這是「這次不能再用『未重跑』帶過」的量化依據（§8）。

### 1.6 【本次發現】真實開發資料庫從未套用過任何一次 migration

**這不是本 SB 造成的，也不是本 SB 要改的東西——但它會決定本 SB 的驗證怎麼做。**

容器內對真實開發 DB 的**唯讀**查詢（`current_database()` = `postgres`、port `5432`，
即綁定 `.devcontainer/postgres-data/` 的真實開發庫）：

| 項目 | 契約／migration 應為 | 真實開發 DB 實際 |
|------|-------------------|----------------|
| `market_articles` 欄位數 | 15（migration 003＋004） | **10**（Gate 0 原始 schema） |
| `daily_ml_features` 欄位數 | 29（migration 002） | **7** |
| `schema_version` 表 | 存在（migration 001 建立） | **不存在** |
| 資料庫清單 | — | 只有 `postgres` 一個 |
| `market_articles` 列數 | — | 331 |
| `source` 值分佈 | — | `ptt_stock` 331 筆（**只有一個來源**） |

`database/migrations/` 下 `001_baseline.sql`～`004_comment_scrape_timestamp.sql` 四份**都在**。

**直接後果（已實測，非推論）**：把 `db_writer.py:494-497` 的查詢原文對真實開發 DB 執行 →

```
UndefinedColumn: column "push_count" does not exist
```

也就是說 **`run_feature_engineering_pipeline()` 現在對真實開發 DB 跑會直接失敗**。

**這件事的性質要說清楚，不要放大也不要縮小**：

- **不是資料損壞**，不是誰做錯了破壞性操作。331 筆文章完好。
- **不是既有 Gate B 證據造假**。`UG-G2-SB1`／`SB3`／`SB4` 的 E2E 都在**隔離臨時 DB**
  完成並如實標示（那正是 RISK-013 要求的謹慎作法），從未宣稱對真實 DB 驗證過。
- **是一個沒有人負責的缺口**：`apply_migrations.py` 從未對真實開發 DB 執行過，
  而每個 SB 的 DoD 都只涵蓋「臨時 DB 內驗證通過」。
  **「臨時 DB 會過」與「真實環境能跑」之間，沒有任何一步把它們接起來。**
- **失敗是大聲的，不是安靜的**（§7.1 合規）：`fetch_data`（`db_writer.py:88-99`）
  以 `try/finally` 且**無 `except`**，例外往上拋；
  `main_etl_pipeline.py:173` 呼叫端亦無 `try/except`。
  **DB 錯誤沒有被偽裝成空結果**——這一點現行實作是對的。

處置見 **§9 決策點 1**。

---

## 2. Requirement Source

- **PO 裁決（2026-08-28 第二輪）**：決策點 5 → 明確的來源能力宣告，
  以 `source` 值為鍵；不採 `push_count IS NULL` 隱含判定；三項機械要求；
  **不分 PASS／FAIL 都要做**。
- **PO 裁決（2026-08-29）**：本項插到 `UG-G2-SB6` 之前——
  兩道關卡是目前唯一還活著的偽造訊號路徑，SB6 之後每項特徵工作都會走過它。
- `FEATURE_REGISTRY.md` §5.1–§5.4（四條公式）、`:384-394`（`NULL` 語意）、
  §5.5（DEC-024 時點有效性）、§5.6（DEC-025 聚合範圍）
- `DB_MIGRATION_PLAN.md` §4.3（`DEFAULT 0` 禁令與偽造訊號）
- `CLAUDE.md` §9A.1／§9A.2（驗證為偵測而寫；每項檢查須有 known-FAIL 案例）
- `REMAINING_RISKS.md` RISK-004（Threads——**下一個沒有方向的來源**）

---

## 3. 設計

### 3.1 來源能力宣告表（新檔，內容極小）

`src/transform/source_capabilities.py`：

```python
# 來源能力宣告表（決策點 5，PO 2026-08-28 裁決）
#
# 宣告的是「這個來源在結構上**能不能**提供某項資料」，
# 不是「這一次**有沒有**抓到」。後者是 NULL 的既有語意
# （FEATURE_REGISTRY.md:384-394「文章存在，留言尚未解析」）。
# 兩者不得混用——那正是 §1.3 一欄兩義與 SB3 push_count 陷阱的成因。
COMMENT_DIRECTION_SOURCES = frozenset({'ptt_stock'})


def provides_comment_direction(source: str) -> bool:
    """該來源的留言是否帶有方向（推／噓）標記。

    未登錄的來源一律視為「不提供方向」。這個預設方向是刻意的：
    漏登錄的後果是特徵為 NULL（誠實地少），
    反過來設計的後果是偽造訊號（安靜地錯）。
    """
    return source in COMMENT_DIRECTION_SOURCES
```

**為什麼不採 `push_count IS NULL` 隱含判定**（PO 裁決理由）：
`FEATURE_REGISTRY.md:384-394` 已把 `NULL` 定義為「文章存在，留言尚未解析」。
再讓它兼任「這個來源沒有方向的概念」，就是**用同一個值裝兩種語意**——
本專案已經因為同一個病吃過兩次虧（§1.3 `engagement_metric` 一欄兩義、
`UG-G2-SB3` `push_count` 雙語意陷阱），不會用第三次。

**PO 補上的論證**：`MULTI_SOURCE_DATA_CONTRACT.md` §4.3 的 Dcard 欄位映射表
**只有 8 列**，`push_count`／`boo_count`／`neutral_count` **三欄完全不在裡面**。
**「Dcard 沒有方向」是 Gate 0 契約本來就已經隱含承認的事**——
本決策點不是發明新概念，是把契約已默認的事變成程式碼看得懂的宣告。

### 3.2 聚合層四項改動（`_aggregate_direct_comment_counts`）

| # | 改動 | 位置 |
|---|------|------|
| 1 | `required` 集合補 `'source'` | `:534` |
| 2 | `db_writer.py:494-497` 的 SELECT 補 `source` | 取得路徑 |
| 3 | 刪除 `fillna(0)` 兩行；改為**只有 `provides_comment_direction(source)` 為真的列**才參與 `push_sum`／`boo_sum` 聚合 | `:554-555` |
| 4 | `push_sum`／`boo_sum` 聚合改用 **`min_count=1`**；`total_sum` **不改**（數量本來就該跨來源相加，且來源必有 `total_comments`） | `:557-560` |

### 3.3 守衛拆分（`_compute_comment_features`）

`has_comments`（`:575`）拆為兩個：

```python
has_volume    = df['total_sum'].notna()    # comment_volume_ratio 用
has_direction = df['push_sum'].notna()     # polarization / momentum 用
```

`push_ratio`（`:578`）改以 `has_direction` 為 `.where()` 條件。

### 3.4 不建一般化的來源能力協商層（PO 機械要求 3）

只宣告 **comment direction 一項能力**。宣告表可擴充即可。
理由：現在只有一個真實需求，先建協商層是**為想像中的第二個需求付設計費**，
而那個需求的形狀還不知道。

---

## 4. 三件必須額外交代的事（複查指定）

### 4.1 混合來源日的行為必須是**明講的決定**，不是程式碼掉出來的副作用

同日同股兼有「有方向」與「無方向」來源時，本設計的行為是：

| 特徵 | 計算基礎 |
|------|---------|
| `comment_volume_ratio` | **全部**留言（含無方向來源） |
| `comment_polarization`／`net_push_momentum` | **只有有方向來源的那個子集** |

**實測（容器內，pandas 3.0.5）**：混合日 PTT 20 則（push=10, boo=2）＋ Dcard 200 則
→ `push_ratio = 0.615`（由 20 則算出），`total_sum = 220`。
**方向特徵描述 20 則，數量特徵描述 220 則，兩者並列於同一列。**

**這可以接受**（方向只能由有方向的資料算出，別無他法），
**但它必須寫進契約**，否則會變成下一個「沒人知道為什麼」。
處置：`FEATURE_REGISTRY.md` **新增 §5.7**（見 §10）。

### 4.2 `comment_volume_ratio` 的來源組成斷點——**這次不修**

**已登記的已知限制**（`G2_SB5_GATE_A_PROPOSAL.md` §1.12）：
前 5 日純 PTT（每日 `total=20`）、第 6 日 PTT 20 ＋ Dcard 200 →
比值由 `0.952381` 跳到 **`10.476190`（11.00x）**。
分子含兩來源，分母的 `t-5..t-1` rolling 基準卻全是純 PTT——
**量到的不是關注度變化，是來源上線事件**。

**為什麼這次不修**：

1. **現在不可能發生**：真實 DB 只有 `ptt_stock` 一個來源（§1.6 實測 331/331）；
   且決策點 3 已定 Dcard adapter 不接入 `main_etl_pipeline.py`，
   Dcard 又已 `DEFERRED WITH EVIDENCE`。**沒有第二個來源，就沒有組成變化。**
2. **修法尚未確定**：可選方向至少三種（基準期按來源分別計算、
   來源上線後暖機期內標 `NULL`、改用來源內相對量）——
   **哪一種正確取決於第二個來源的性質**，而現在沒有第二個來源可供判斷。
   在資料不存在時挑一種寫死，是把一個猜測固化成契約。
3. **它與本 SB 的缺陷不同型**：本 SB 修的是「**偽造出不存在的訊號**」；
   這一項是「**真實訊號的可比較性在邊界處失效**」。前者任何時候都是錯的，
   後者只在特定事件發生時才錯。

**什麼時候必須修**：**在任何第二個來源接入 `main_etl_pipeline.py` 之前**，
而不是「接入之後再看」。屆時 `comment_volume_ratio` 會在來源上線當日
產生一個純由組成造成的尖峰，而那一天的特徵會直接進入訓練集。

處置：登記為 `REMAINING_RISKS.md` 新風險項（見 §9 決策點 2——**編號由 PO 指派**），
並於 `FEATURE_REGISTRY.md` §5.7 一併載明。

### 4.3 兩個 known-FAIL 測試必須在本 SB 內轉綠

| 測試 | 現況 | 驗收 |
|------|------|------|
| `test_no_direction_source_yields_null_not_fabricated_signal` | **尚未建立**（`G2_SB5_GATE_A_PROPOSAL.md` §7 規劃，當時 SB 未進實作） | 建立後**先確認它 FAIL**，修完轉綠 |
| `test_direction_null_survives_aggregation` | **尚未建立**（同上） | 同上 |

> **執行紀律**：兩者都必須**先寫測試、確認 FAIL、留下 FAIL 的原始輸出**，
> 才動 `src/`（`CLAUDE.md` §13.5、§9A.2）。
> 只交出「修完之後是綠的」證明不了那個測試抓得到東西。

---

## 5. In / Out of Scope

**In Scope**：§3 的宣告表與四項聚合改動、§3.3 守衛拆分、
`db_writer.py:494` SELECT 補 `source`、§4.3 兩個 known-FAIL 測試、
`FEATURE_REGISTRY.md` §5.7、§4.2 的風險登記。

**Out of Scope**：
- `comment_volume_ratio` 來源組成斷點的**修法**（§4.2，登記不修）
- Dcard adapter（已 `DEFERRED WITH EVIDENCE`）
- 一般化的來源能力協商層（§3.4）
- `engagement_metric` 跨來源語意分歧的 UI 分流（決策點 3 裁定另開 SB）
- **真實開發 DB 的 migration 套用**（§1.6／§9 決策點 1——需 PO 明確授權，
  且屬 `database/` 變更，不得夾帶在本 SB）

---

## 6. Tests

### 6.1 新增（本 SB 的驗收標準）

| # | 測試 | 釘住什麼 | 現行程式碼下 |
|---|------|---------|-------------|
| 1 | `test_no_direction_source_yields_null_not_fabricated_signal` | 無方向來源 → `polarization`／`momentum` 為 `NULL`，不是 `1.0`／`0.0` | **必須 FAIL** |
| 2 | `test_direction_null_survives_aggregation` | 聚合層第二道關卡：全 NaN 群組聚合後仍為 `NaN` 而非 `0.0` | **必須 FAIL** |
| 3 | `test_zero_push_ptt_article_is_not_null` | **反向守衛**：真實零推文 PTT 文章（整數 `0`）修完後仍**有值** | 現行 PASS，修後仍須 PASS |
| 4 | `test_unregistered_source_defaults_to_no_direction` | 未登錄來源（如 `'threads'`）預設不提供方向 | 新能力 |
| 5 | `test_volume_ratio_still_uses_all_sources` | 數量特徵不受方向拆分影響，仍計入所有來源 | 新行為 |
| 6 | `test_required_columns_missing_source_returns_empty` | `required` 補 `source` 後，缺欄時走既有的空表路徑而非崩潰 | 新行為 |

**第 3 項為何必要**：§1.1 的修法同時動兩處，
**最容易的失敗方式是把「真正零推文」一起誤判成「無方向」**——
那個退化**不會有任何錯誤訊號**，只會讓一批 PTT 特徵安靜地變成 `NULL`。
容器內已實測整數 `0` 在 `min_count=1` 下仍聚合為 `0`（`notna=True`），
但「目前安全」與「改完之後仍安全」是兩件事。

### 6.2 既有測試

§1.5 的 117 個測試全部須通過。**若有任何一個需要修改斷言，
必須在 Gate B 逐項列出並說明為什麼那個改動是正確的**，
不得以「更新斷言以符合新行為」一語帶過。

---

## 7. E2E Verification Plan

**視 §9 決策點 1 的裁示而定，兩條路徑分別如下。**

### 7.1 共通（不論裁示為何）

1. 起**隔離臨時 DB**（獨立容器名、**不掛 `postgres-data`**、不進 compose 網路），
   **執行前呈報 RISK-013 綁定確認**：`current_database()` 與連線埠須為臨時目標。
2. 於臨時 DB 套用 migration 001～004（`apply_migrations.py`）。
3. 灌入涵蓋以下情境的 fixture：純 PTT（含零推文）、無方向來源、混合來源日、
   未登錄來源。
4. 走真實 DB 路徑執行 `fetch_all_raw_data` → `generate_daily_features`，
   驗證三個留言特徵的值與人工核算逐位相符。
5. **§0.5 未結義務 #8 的觸發條件因本步驟成立**——於同一臨時 DB 內執行
   `python -m unittest tests.schema_smoke_ui_data_loader -v` 並於 Gate B 回報。
6. 全套測試以 `DB_HOST`／`DB_PORT` 覆寫指向該臨時 DB 執行，
   **附完整原始輸出**（§8）。
7. 驗證後**拆除**臨時容器。

### 7.2 若決策點 1 裁示「本 SB 一併處理真實 DB」

追加：`pg_dump` logical backup → 對真實 DB 套用 001～004 →
驗證 `run_feature_engineering_pipeline()` 可實際跑完 →
回報前後 schema 差異與資料列數。
**此路徑屬 `database/` 變更，需 PO 於決策點 1 明確授權。**

---

## 8. 測試證據要求（本次不得以「未重跑」帶過）

`PROJECT_STATUS.md` §0.4 的 `263 / 26` 是**靜態計數，不是通過紀錄**。
全套測試自 `UG-G2-SB4` 收尾後未再實際執行
（`UG-G2-SB5` 各輪標為「未重跑」時 `src/` 未動，PO 已接受）。

**本 SB 動 `src/transform/feature_aggregator.py`，Gate B 必須附全套測試的實際執行輸出**，
依 `CLAUDE.md` §13.4 以 `DB_HOST`／`DB_PORT` 覆寫指向臨時 DB，
**並在執行前確認 `current_database()` 與連線埠確實是臨時目標**。
收尾時 §0.4 的基線數字再更新一次。

---

## 9. PO 決策點

### 決策點 1【阻擋 E2E 設計，不阻擋實作】：§1.6 的 migration 缺口如何處置

真實開發 DB 從未套用任何 migration，`run_feature_engineering_pipeline()`
對它執行會 `UndefinedColumn` 失敗。可選：

- **(a) 本 SB 只在臨時 DB 驗證，真實 DB 缺口另開 SB**（本提案建議）。
  **理由**：真實 DB 套用 migration 屬 `database/` 變更，需要備份與回復方案
  （`CLAUDE.md` §3、§7.1），把它夾帶進一個特徵層的 SB 會讓兩件不同性質的風險
  綁在同一次 commit。且本 SB 的正確性不依賴它。
  **代價**：「真實環境能跑」仍然沒有人負責，缺口繼續存在（但會被登記）。
- **(b) 本 SB 一併處理**：先 `pg_dump`，再對真實 DB 套用 001～004。
  **優點**：缺口當場關閉。**代價**：範圍擴大到 `database/`，
  且 migration 004 的 CHECK 約束會套用到 331 筆既有資料
  （四個留言計數欄與 `comments_scraped_at` 皆為 NULL，滿足約束，
  但這需要實測而非推論）。
- **(c) 其他你指定的方式。**

> 無論選哪個，**§1.6 都必須被登記**——它現在不在任何風險清冊或未結義務裡。

### 決策點 2：§4.2 的來源組成斷點登記為新風險項

建議登記於 `REMAINING_RISKS.md`，嚴重度 **Medium**，
觸發條件「任何第二個來源接入 `main_etl_pipeline.py` 之前」。
**風險編號請你指派**（現行最高為 RISK-015），本提案不預先佔號。

### 決策點 3：`FEATURE_REGISTRY.md` 新增 §5.7 的位置與編號

§5.5（DEC-024）、§5.6（DEC-025）之後接 **§5.7「來源能力與方向類特徵的適用範圍」**。
新增契約條文需 ADR 承接——**是否新增一則 DEC（現行最高 DEC-027）**，
或併入既有 ADR？本提案建議**新增一則**，理由：這是一個會約束未來每一個新來源的
通用規則，不宜寄生在 Dcard 相關的 ADR 底下。

---

## 10. Documentation Sync

| 文件 | 變更 |
|------|------|
| `FEATURE_REGISTRY.md` | 新增 §5.7（來源能力宣告、混合來源日的方向／數量母體差異、未登錄來源預設） |
| `DECISIONS.md` | 新增一則 DEC（依決策點 3），狀態 `Proposed`——**僅 PO 可改 `APPROVED`** |
| `TRACEABILITY.md` | §2 追溯矩陣新增列；**§3.2 ADR 索引一併補上**（§0.5 第 10 項的第一次實地演練） |
| `REMAINING_RISKS.md` | 新增風險項（決策點 2）；§1.6 缺口的登記（決策點 1） |
| `PROJECT_STATUS.md` | §0.2 SB5 列補記決策點 5 結果；§0.4 基線數字更新；§0.5 第 8 項（若已補跑）與第 9 項（提案搬移）結案 |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` | SB5 Brief 補記決策點 5 的實際交付 |

---

## 11. Rollback

單一 commit，`git revert` 即可。無 schema 變更（決策點 1 選 (a) 時）、
無資料遷移、無外部相依。

**行為回復點**：revert 後偽造訊號路徑會回來——
因此 revert 只應在「修法本身有錯」時使用，不應用於「測試不過就先退回」。

---

## 12. Definition of Done

- §6.1 六個測試全部存在；**第 1、2 項已先確認 FAIL 並留下原始輸出**，修後轉綠。
- §1.5 的 117 個既有測試全部通過；任何斷言修改逐項說明理由。
- **全套測試實際執行輸出已附**（臨時 DB，含 `current_database()` 與連線埠確認）。
- §0.5 未結義務 #8（`schema_smoke_ui_data_loader`）已於同一臨時 DB 補跑並回報。
- `FEATURE_REGISTRY.md` §5.7 已寫入；對應 DEC 已建立（`Proposed`）；
  `TRACEABILITY.md` §2 與 **§3.2** 皆已同步。
- §4.2 的已知限制與 §1.6 的 migration 缺口**都已登記**，不是只寫在本提案裡。
- `PROJECT_STATUS.md` §0.4 基線數字已更新（依實際核對，不引用舊數字）。
- 未夾帶格式／行尾變更（§12.2）；contract-check `exit 0`。

---

## 13. 待 PO 裁決事項彙總

| # | 事項 | 狀態 |
|---|------|------|
| 決策點 1 | §1.6 真實 DB migration 缺口的處置 | **已裁示 → (a)**，另開 Migration SB；**但登記不等那個 SB，現在就做** → RISK-017 |
| 決策點 2 | §4.2 來源組成斷點的風險編號與登記 | **已裁示 → RISK-016** |
| 決策點 3 | §5.7 的 ADR 承接方式 | **已裁示 → 新增 DEC-028** |
| — | 本提案整體是否核准進入實作 | **已核准（2026-08-30）** |

---

## 14. PO 裁示與實作記錄（2026-08-30）

### 14.1 PO 對 §1.6 的兩處更正（均已接受並修正）

| # | 更正 | 處置 |
|---|------|------|
| 1 | 本提案原寫「這個缺口不在任何風險清冊或未結義務裡」——**不正確**。`REMAINING_RISKS.md` RISK-006 已有原文「**未曾對真實開發 DB 執行過 migration**」，只是被框成「pg_dump 回滾未驗證」的附帶說明 | RISK-017 **交叉引用 RISK-006**（006 記「migration 失敗會破壞資料」，017 記「migration 從未執行的後果」），並在 RISK-006 加上指回 RISK-017 的註記。**不另立孤立風險** |
| 2 | 不得把缺口描述成「文件與實作不符」——**文件沒有宣稱過任何未發生的事**。`PROJECT_STATUS.md` §0.2 白紙黑字寫著「隔離容器…已拆除」 | 缺的是**「沒做什麼」的紀錄**：本專案對「驗了什麼、在哪裡驗的」紀律極嚴（§9 證據標籤），但**沒有任何機制追蹤「哪個環境還沒收到這個變更」**——前者記得再完整也推導不出後者。已照此措辭寫入 RISK-017 |

> 第 1 點是本輪唯一一處把論證講得比證據強的地方。論證本身成立，不需要加碼。

### 14.2 三項裁示與後續順序

- **決策點 1 → (a)**，Migration SB 另開；RISK-017（**High**）現在就登記。
- **決策點 2 → RISK-016**（Medium）。
- **決策點 3 → DEC-028**（`Proposed`）。
- **後續順序（PO 定序）**：
  `決策點 5 → Migration SB → UG-G2-SB6 → UG-G2-SB7 → Gate 2 關閉`。
  Migration SB 不放在決策點 5 之前的理由：套完 003 後 `push_count` 欄會存在但全 `NULL`，
  **接著跑留言回填時 `fillna(0)` 會讓每一列的 `comment_polarization` 變成 1.0，
  偽造訊號直接寫進真實的 `daily_ml_features`**。先修好再開門。
- **Gate 2 關閉條件新增第五項**：「真實開發資料庫與 migration 狀態同步，
  且 pipeline 已對其實際執行過一次」——已寫入 Master Plan §8 與 `PROJECT_STATUS.md` §0.3。

### 14.3 實作結果

| 項目 | 結果 |
|------|------|
| `src/transform/source_capabilities.py` | 新建（宣告表 + `provides_comment_direction()`） |
| `feature_aggregator.py` | `required` 補 `source`；`fillna(0)` → 依來源能力過濾；`agg` 加 `min_count=1`；`has_comments` 拆為 `has_volume`／`has_direction` |
| `db_writer.py` | `fetch_all_for_features()` 的 SELECT 補 `source` |
| `FEATURE_REGISTRY.md` | 新增 §5.7（五個小節，含混合來源日母體差異與兩道關卡的實作註記） |
| `DECISIONS.md` | DEC-028（`Proposed`） |
| `TRACEABILITY.md` | §3.2 第 25 項（§0.5 第 10 項規則的**第一次實地演練**） |
| `REMAINING_RISKS.md` | RISK-016、RISK-017 新增；RISK-006 交叉引用；Risk Summary 計數同步（High 5→6、Medium 8→9、ML Integrity 1→2、Data Safety 2→3） |

### 14.4 known-FAIL 紀律：先確認 FAIL 才動 `src/`

實作前執行 `tests.test_comment_features.SourceCapabilityTests`：

```
FAIL: test_direction_null_survives_aggregation
AssertionError: False is not true : 全 NaN 群組的 push_sum 必須是 NaN；sum() 預設回 0.0，需 min_count=1

FAIL: test_no_direction_source_yields_null_not_fabricated_signal
AssertionError: False is not true : 無方向來源不得產出 comment_polarization，補 0 會造出 1.0 這個偽造的最大分歧訊號

Ran 4 tests in 0.144s
FAILED (failures=2)
```

同一次執行中，反向守衛 `test_zero_push_ptt_article_is_not_null` 與
`test_volume_ratio_still_uses_all_sources` **PASS**——
證明這兩個 FAIL 是被特定缺陷觸發的，不是測試本身寫壞。

實作後同檔 **19 tests / OK**。

### 14.5 【本次發現】全套測試揭露一個既有的測試隔離缺陷

**這正是複查堅持要跑全套的理由——單獨跑新測試檔時全過，併入全套後出現 4 個 error。**

```
TypeError: '>=' not supported between instances of 'MagicMock' and 'int'
Ran 269 tests ... FAILED (errors=4)
```

**成因**：`test_canonical_stock_id.py`／`test_feature_aggregator_alignment.py`／
`test_research_features.py`／`test_time_alignment.py` 四個檔以

```python
if "requests" not in sys.modules:
    sys.modules["requests"] = <stub>
```

的方式塞 stub。**「已安裝」不等於「已被 import」**——容器裡 `requests` 雖已安裝，
但在這些模組被載入的當下通常還不在 `sys.modules`，因此判斷幾乎必然成立，
**stub 會永久取代真實 `requests`，影響同一個 process 內後續所有測試模組**
（`unittest discover` 是同一個 process）。

**這與 `UG-G2-SB2` 修掉的 4 個 `bs4` stub 隔離缺陷是同一類問題**——
而且**同一個檔案裡 `bs4` 用的已經是正確寫法**（`try/except ModuleNotFoundError`），
只有 `requests` 沒改到。

**修法**：改用該檔自己對 `bs4` 已在使用的正確寫法——真實套件存在就用真實的，
只有缺席時才 stub。四個檔案各改一處，**未改任何斷言**。

> **同一個 pattern 仍存在於 `tenacity`／`yfinance` 的 stub 區塊**。
> 本次**不改**（目前沒有測試需要真實的它們，改了等於在沒有失敗案例的情況下動既有測試），
> 但在此登記——下一個需要真實 `tenacity` 或 `yfinance` 的測試會撞到同一件事。

修正後全套 **269 tests / OK**。
