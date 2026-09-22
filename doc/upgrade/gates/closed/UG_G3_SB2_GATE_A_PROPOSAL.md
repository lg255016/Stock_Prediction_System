# UG-G3-SB2 Gate A 提案：Panel Dataset 構建

> **性質**：Gate A 規劃提案，非實作授權。Plan-Before-Code——本提案未修改 `src/`／`tests/`／`database/`。
> **提交日期**：2026-09-09（重送版，PO 2026-09-09 退回後修正）
> **前置**：`UG-G3-SB1`（Triple-Barrier Labeling）已於 2026-09-09 由 PO 核准 Gate B 結案。
> **依賴**：`UG-G2-SB1`（`daily_ml_features` 29 欄）、`UG-G2-SB6`（`universe_snapshots`，DEC-017）、`UG-G3-SB1`（Triple-Barrier 標籤）。

---

## 0. 摘要

Gate A 第一步唯讀查證（`GATE3_STARTUP_APPLICATION.md` §4.3 第 3 點要求）揭露一個
比原始 Master Plan Brief 假設更大的落差：`universe_snapshots` 是 **Point-in-Time**
的，46 期跨期去重共 **458 檔**（不是最新一期的 150 檔），其中 **455 檔**在
`entity_mapping` 無路由，且 `daily_ml_features`／`stock_prices` 現皆僅 **3 檔**
有資料（2330／2382／6488；NVDA 不在台股候選空間內）。**好消息**：458/458 檔的
價格資料已存在於 `candidate_prices`（`UG-G2-SB9`，~4 年），只是從未搬進生產
特徵管線。

**首次送審誤把量體算成最新一期的 150／146／147，PO 複審獨立重跑抓出——本節
數字已全部改為全期正確值，並依 PO 2026-09-09 裁決把 458 檔資料回補拆分為新
SB `UG-G3-SB2a`（DEC-036），路由補齊（455 筆）依 Gate 3 啟動書既有裁決⑥維持
在本 SB。**

---

## 1. Requirement Source

| 來源 | 內容 |
|---|---|
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2／UG-G3-SB2a Brief | Goal／Dependency／In-Out Scope／Affected Components／Tests |
| `GATE3_STARTUP_APPLICATION.md` §4（PO 2026-09-08 裁示，2026-09-09 隨 Gate 3 啟動核准） | 宇宙接線三層分離設計；§4.3 對 SB2 的三項具體影響；§12 裁決⑥路由補齊不拆獨立 SB |
| `UG_G3_SB1_GATE_B_SUBMISSION.md` §7 | 未驗證清單交棒項：尾端列每日重算歸屬（本提案 §3.1 回答） |
| PO 2026-09-09（SB1 結案訊息） | 三項必答：尾端列重算歸屬、RISK-025 與面板凍結排程、`label_end_date_tb` 產生時機 |
| PO 2026-09-09（本提案退回意見） | 458／46 期全量數字訂正；`UG-G3-SB2a` 拆分裁決（DEC-036）；PIT 面板測試設計；掛點邊界訂正為 H+1=6 列 |

---

## 2. Current State（唯讀查證，非推測，2026-09-09，PIT 全期數字）

### 2.1 Universe 量體是跨期聯集，不是單期快照

`universe_snapshots` 共 **46 期**（`effective_date` 2022-11-01 ~ 2026-08-03），
每期 `included=TRUE` 150 檔，**跨期去重（PIT 聯集）共 458 檔**——面板依
DEC-017／RISK-012 逐期取當期名單，量體是聯集不是任一單期快照。

**可重跑查證**：
```sql
SELECT COUNT(DISTINCT effective_date), COUNT(DISTINCT stock_id) FILTER (WHERE included)
FROM universe_snapshots;
-- 結果：46 | 458
```

### 2.2 路由缺口（`GATE3_STARTUP_APPLICATION.md` §4.3 第 3 點要求的查核）

458 檔中 **455 檔在 `entity_mapping` 裡沒有任何路由列**（僅 2330／2382／6488
既有路由；NVDA 不在台股候選空間內，本不屬於此缺口）。`entity_mapping` 現僅
5 列，`tracking_keywords` 現僅 27 列，其中僅 4 個 `category='core_stock'` 對應
到既有 3 檔台股，其餘 23 列（`theme`／`macro`／`ai_discovered`）**沒有任何一列
對應到 455 檔未路由股票中的任何一檔**。

**可重跑查證**：
```sql
SELECT COUNT(DISTINCT u.stock_id) FROM universe_snapshots u
WHERE u.included AND NOT EXISTS (SELECT 1 FROM entity_mapping e WHERE e.stock_id=u.stock_id);
-- 結果：455
```

### 2.3 資料缺口（本提案查證，範圍比 §4.3 原描述更大）

| 表 | 涵蓋範圍 | 對 458 檔宇宙的覆蓋 |
|---|---|---|
| `candidate_prices`（migration 005，`UG-G2-SB9`） | 2,016 檔、1,825,814 列、2022-08-03~2026-09-04（**~4.05 年**） | **458/458 全覆蓋**（該表本來就是 `universe_snapshots` 排名時的來源池） |
| `stock_prices`（生產特徵管線讀取的表） | **3 檔**（2330／2382／6488） | **3/458** |
| `daily_ml_features`（`UG-G3-SB2` Brief 指定的讀取來源） | **3 檔**，2,959 列（987+987+985，3,713 列扣除 NVDA 754 列，NVDA 不在此缺口範圍） | **3/458** |

**這意味著**：即使 §2.2 的路由缺口今天全部補齊，`daily_ml_features` 明天也不會
突然出現另外 455 檔的資料——路由只解決「未來每日 ETL 要不要抓這檔」，**不會**
回填過去 ~4 年的價格與特徵。**價格資料本身其實已經在 `candidate_prices` 裡**，
但從 `candidate_prices` 搬到 `stock_prices` ＋ 跑過 `feature_aggregator.py` 全套
特徵工程 ＋ 跑過 `UG-G3-SB1` 的 Triple-Barrier 標籤，**這整條路徑對 458 檔股票
一次都沒有執行過**。

**可重跑查證**：
```sql
SELECT COUNT(DISTINCT stock_id) FROM stock_prices;                                            -- 3（不含 NVDA）
SELECT COUNT(*), COUNT(DISTINCT stock_id) FROM candidate_prices;                              -- 1825814, 2016
SELECT COUNT(DISTINCT stock_id) FROM universe_snapshots
WHERE included AND stock_id NOT IN (SELECT DISTINCT stock_id FROM candidate_prices);          -- 0
```

### 2.4 為什麼 Master Plan 原始 Brief 沒有寫到這件事

`SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2 的 Goal 原文是「從 `daily_ml_features`
讀取跨股票面板資料集」——**這句話的前提假設是 `daily_ml_features` 屆時已經是多股票
的**。該假設在 Gate 0 規劃當時合理，但 Gate 3 啟動時仍未成立。**這不是本提案發現
新問題，是原規劃的一個前提，第一次被拿出來對照真實資料時沒有成立。**

---

## 3. PO 指定必答項

### 3.1 尾端 `insufficient_data` 列的每日重算歸屬

**現況**：`scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py` 是**一次性回填
腳本**，沒有任何機制在每日 ETL 新增 `stock_prices` 列後，回頭重算尾端列。

**邊界訂正（PO 複審指出）**：新列進來後，需要重新評估的不是「原本標
`insufficient_data` 的 H-1=4 列」，而是**尾端 `H+1=6` 列**——原尾列（曾經
`no_entry`，因為當時 `Open[T+1]` 不存在）現在有了 `Open[T+1]`，`remaining` 從
0 變 1；原尾列前第 5 列（曾經 `remaining=5` 已可判定的正常標籤）不受影響；但
`remaining` 剛好等於 H 邊界前後的列都需要重新檢查——**正確範圍是新列加入前的
最後 `holding_period + 1 = 6` 列**，實作時以測試逐列釘死邊界，不假設本提案這
段文字本身沒有差一風險。

**回答**：**併入 `UG-G3-SB2` 的每日 ETL 掛載點，不另開 SB**，且**列入本 SB
DoD（見 §10）與測試（見 §6）**——首次送審遺漏了這兩處，本次補上。具體設計：

- 每日 ETL 寫入當日 `stock_prices` 後，對每檔股票尾端 `H+1=6` 列重跑
  `generate_triple_barrier_labels()`，只 `UPDATE` 這些列的
  `target_triple_barrier`／`label_reason`。
- **不是全量重算**——每日僅觸及每檔股票尾端 6 列，成本可忽略。
- 沿用 `UG-G3-SB1` 已驗證的雙欄 `pd.isna()`→`None` 轉換、三道核對（列數／分布
  快篩／逐列精確比對）與 CHECK 約束防線，不重新發明轉型與驗證邏輯。
- **冪等性要求（新增）**：同一天重跑掛點兩次，結果必須相同（第二次的 `UPDATE`
  應為 no-op 或寫入相同值），列入 §6 測試。
- 執行順序：**在當日特徵列（`daily_ml_features` 其餘欄位）寫入之後**——掛點
  需要當日的 `stock_prices` 已存在，但不依賴當日特徵是否已計算完成（Triple-
  Barrier 只讀價格，不讀情緒／技術特徵）。
- 首次對真實庫啟用走 RISK-013 三項協議（比照 `UG-G3-SB1`），非首次啟用後續每日
  執行不需要每次都走完整協議（比照既有 `UG-G2-SB7` 的每日排程慣例，但仍需
  `db_target_guard.py` 的連線目標防線常駐生效）。

### 3.2 RISK-025 與面板凍結排程的關係

**回答**：**`panel_dataset.py` 設計為即時讀取器，不是靜態匯出／materialize 的表**。

- Panel Dataset 每次呼叫時**即時查詢** `daily_ml_features` ＋ `universe_snapshots`
  當期快照，**不寫入新表、不快取一份獨立副本**。
- 「凍結」這個詞需要被拆解：**真正被凍結的是 `daily_ml_features` 裡已寫入的
  `target_triple_barrier`／`label_reason` 值**，不是 Panel Dataset 本身（它只是
  一個查詢視角）。若 `UG-G3-SB3` 決定調整 barrier 寬度，需要重算的對象是
  `daily_ml_features`（比照 SB1 RISK-013 協議），Panel Dataset 讀取器不需要
  任何改動就能讀到新值——**代價是「重算 `daily_ml_features`」這件事本身，不是
  「重建 Panel Dataset」**。
- **不建議** SB2 在開工前先去問 SB3 的 D3 排程再決定——RISK-025 的處置已排定在
  `UG-G3-SB3`，SB2 現在能做的只有把重算成本降到最低（即時讀取器設計），而不是
  預先揣測 SB3 的結論。

### 3.3 `label_end_date_tb` 在面板構建中的產生時機

**現況**：`label_end_date_tb` 是 `generate_triple_barrier_labels()` 的 DataFrame
層輸出欄位，**未持久化到 `daily_ml_features`**——該表只存 `target_triple_barrier`／
`label_reason` 兩欄。

**回答**：**由 `panel_dataset.py` 在面板構建時呼叫**：

1. 從 `stock_prices` 讀取 `stock_id, trade_date, open_price, high_price, low_price`。
2. 呼叫 `generate_triple_barrier_labels()`，**只取其 `label_end_date_tb` 欄位**——
   `target_triple_barrier`／`label_reason` 兩欄改讀 `daily_ml_features` 裡已真實
   庫寫入的值，不用這次重新計算的結果，避免兩份計算結果不一致時不知道要信哪一份。
3. 把 `label_end_date_tb` 併回面板 DataFrame，供
   `WalkForwardSplitter(label_horizon=5, label_end_date_col="label_end_date_tb")` 使用。

**已知的時點落差需容忍，不得遮掩（PO 複審指出）**：`label_end_date_tb` 於面板構
建當下即時計算，而 `target_triple_barrier`／`label_reason` 來自 `daily_ml_features`
的落地值——**兩者可能不是同一時點的產物**。若每日尾端重算掛點（§3.1）尚未對某
批新資料執行，尾端列會出現「有 `label_end_date_tb`、但 `target_triple_barrier`
為 NULL（尚未重算或本來就是 `insufficient_data`）」的組合。讀取器**必須能容忍
這個組合**（不得因此拋錯或靜默丟棄該列），並在文件與程式註解中明確記載此為
已知、預期的時序落差，不是資料錯誤。

**為什麼不是別的元件呼叫**：`WalkForwardSplitter` 本身不知道如何產生
`label_end_date_tb`；`daily_ml_features` 沒有這欄位可讀；因此產生點只能在面板
構建這一層，且計算成本極低（純 `groupby().shift()`，不含價格路徑評估迴圈）。

---

## 4. `UG-G3-SB2` / `UG-G3-SB2a` 分工（PO 2026-09-09 裁決，DEC-036）

首次送審提出 A／B／C 三個排程選項，PO 裁定**選項 C 的精神（拆分）成立，但拆分
方式不同於原提案**——路由補齊**不**隨資料回補一起拆出，因為 Gate 3 啟動書 §12
裁決⑥已明文「路由補齊併入 `UG-G3-SB2` 為明確子項，不拆獨立 SB」，原提案的選項 C
把路由也拆進 `SB2b`，與既有裁決衝突。

| SB | 範圍 | 依賴 |
|---|---|---|
| **`UG-G3-SB2`（本提案）** | (1) Panel 讀取器（PIT 正確）；(2) `entity_mapping` 路由補齊（455 筆，主策略 `candidate_prices.security_name` 自動產生，458/458 零缺口；俗稱/黑話類人工核對另案）；(3) 每日尾端重算掛點（§3.1） | `UG-G2-SB1` + `UG-G2-SB6` + `UG-G3-SB1` |
| **`UG-G3-SB2a`（新增，DEC-036）** | 458 檔 `candidate_prices → stock_prices` 搬遷 + `feature_aggregator.py` 全套 + Triple-Barrier 標籤；前置：RISK-022 面向二價格基準政策、RISK-024 NaN 規模量測、既有 3 檔重疊列處理 | `UG-G2-SB9`（`candidate_prices`）+ `UG-G3-SB1` |

**`UG-G3-SB3` 依賴 `UG-G3-SB2` 與 `UG-G3-SB2a` 皆完成**（PO 裁決，非任一先行）。
`UG-G3-SB2a` 詳細 Brief 見 `SYSTEM_UPGRADE_MASTER_PLAN.md` §9，其 Gate A 提案另
案送審，本提案僅涵蓋 `UG-G3-SB2` 本體範圍（§5 起）。

---

## 5. In Scope

- `src/ml/panel_dataset.py`（新建）：跨股票 **PIT** 面板讀取器
  - Universe 過濾：**每個 `trade_date`，取 `universe_snapshots` 中
    `effective_date ≤ trade_date` 的最近一期 `included=TRUE` 股票清單**
    （不是「當期」這種含糊說法，也不是固定用最新一期）——取代現行
    `entity_mapping` 的隱性守門（Gate 3 §4.2 裁決）
  - 讀取器接受 `as_of` 參數：面板輸出的 `trade_date` 上界，且所選用的
    `universe_snapshots` 快照 `effective_date ≤ as_of`
  - 輸出為 **long-format**（`stock_id, trade_date, ...features..., target, label_end_date_tb`），
    不是矩形矩陣——Universe 每月換名單，矩形假設不成立
- `entity_mapping` 路由補齊（455 筆）：
  - **主策略**：`keyword = candidate_prices.security_name` → `stock_id`。
    `security_name` 為交易所公告簡稱（`UG-G2-SB9` 回補時帶回，DEC-017 用於
    代碼異動的唯一連結訊號），**唯讀查證 458 檔宇宙股票在 `candidate_prices`
    裡 `security_name` 皆非 NULL（458/458，零缺口）**，可作為自動產生路由的
    唯一資料源，不需額外擷取。
  - 俗稱／黑話類關鍵字（例如既有路由中的「台積電」「輝達」——這類是官方簡稱
    以外的口語別名）需人工核對，量體與方式另案評估，不在本提案內設計自動化
    細節。

  **可重跑查證**：
  ```sql
  SELECT COUNT(DISTINCT u.stock_id) FROM universe_snapshots u
  WHERE u.included
    AND EXISTS (SELECT 1 FROM candidate_prices cp WHERE cp.stock_id = u.stock_id AND cp.security_name IS NOT NULL);
  -- 結果：458（458/458，零缺口）
  ```

  **寫入前機械 keyword 撞名檢查（PO 2026-09-09 複審追加，非自我假設）**：
  清理後的 keyword 集合必須逐一反查三種撞名，任一非零即 raise、不寫入：
  (a) 本次新增的 457 筆彼此之間（跨股票撞同一 keyword）、
  (b) 對既有 `entity_mapping` 既有 keyword（撞到不同 stock_id）、
  (c) 對 458 檔宇宙以外的 `candidate_prices` 股票（非宇宙股票撞同名）。
  唯讀查證現況三者皆為 0，但**腳本必須把它做成寫入前的機械檢查，不是假設
  現況永遠成立**：
  ```sql
  WITH uni AS (SELECT DISTINCT stock_id FROM universe_snapshots WHERE included),
  names AS (SELECT DISTINCT cp.stock_id, replace(cp.security_name,'*','') AS kw
            FROM candidate_prices cp JOIN uni USING (stock_id) WHERE cp.security_name IS NOT NULL)
  SELECT (SELECT count(*) FROM (SELECT kw FROM names GROUP BY kw HAVING count(DISTINCT stock_id)>1) t) AS cross_stock,
         (SELECT count(*) FROM names n JOIN entity_mapping e ON e.keyword=n.kw AND e.stock_id<>n.stock_id) AS vs_existing,
         (SELECT count(*) FROM names n JOIN (SELECT DISTINCT stock_id, replace(security_name,'*','') kw
                                            FROM candidate_prices WHERE stock_id NOT IN (SELECT stock_id FROM uni)) o
                          ON o.kw=n.kw AND o.stock_id<>n.stock_id) AS vs_non_universe;
  -- 結果：0 | 0 | 0
  ```

  **路由列的惰性以 keyword 是否已在 active `tracking_keywords` 為界，非全體
  皆惰性（2026-09-09 訂正，原「完全惰性」宣稱經真實庫寫入步驟 5 惰性驗證
  推翻，見 CHAL-009）**：特徵聚合對 `entity_mapping` 是 `fetch_keyword ==
  keyword` 的等值 join（`feature_aggregator.py:331-333`），不掃文章全文；
  每日抓取目標是 `entity_mapping ⋈ tracking_keywords(is_active=TRUE)`
  （`db_writer.py:471-475`）。**因此**：
  - 對 keyword **尚未**進入 active `tracking_keywords` 的股票，新增路由列
    確實惰性——「世紀」「宏大」這類簡稱在被排入 `tracking_keywords` 前不會
    誤把無關文章路由到該股。
  - 對 keyword **已在** active `tracking_keywords` 的股票，新增路由列
    **立即生效**——`fetch_active_stock_targets()` 會立刻多解出該股票。
    **原提案宣稱「完全不影響任何既有每日流程」對此類股票不成立**，
    且**這個前提從未經過反向查核**（新增 keyword 集合 ∩ active
    `tracking_keywords`）。

  **反向查核（2026-09-09，真實庫唯讀，寫入前）**：
  ```sql
  SELECT count(*) FROM candidate_prices cp
  JOIN universe_snapshots u ON u.stock_id = cp.stock_id AND u.included
  JOIN tracking_keywords tk ON tk.keyword = replace(cp.security_name, '*', '')
  WHERE tk.is_active = TRUE
    AND cp.stock_id NOT IN (SELECT stock_id FROM entity_mapping);
  -- 結果：4（is_active = FALSE 者 0，4 即為完整曝險範圍）
  ```
  對應 4 檔：`2059`（川湖）／`2454`（聯發科）／`3008`（大立光）／`8069`（元太），
  皆 `category='ai_discovered'`（AI 熱門詞探索機制早於本 SB 已加入追蹤）。
  真實庫寫入後 `fetch_active_stock_targets()` 由 4 檔變 8 檔，與此查核結果
  完全吻合。追蹤宇宙擴大本身是 Gate 3 §4.2 三層設計的本意（PO 2026-09-09
  裁決：接受、不回滾），**但其連帶後果（3 檔 TWSE 股將經
  `run_twse_pipeline` 日常路徑入庫，基準未定）已登記為
  `PROJECT_STATUS.md` §0.5 #20 每日 ETL 執行閘門與 RISK-022（四）**，
  綁 `UG-G3-SB2a` Gate B 通過解除。本提案**仍不觸碰 `tracking_keywords`
  本身**（見 Out of Scope）——本次訂正的是「惰性」宣稱的精確範圍，不是
  範圍邊界本身。

### 5.1 路由補齊實作細節（PO 2026-09-09 裁決，規格未言明、不得自行選擇）

| # | 事項 | 裁決 |
|---|------|------|
| 1 | `market` 判定 | 取該 `stock_id` 在 `candidate_prices` 中 `MAX(trade_date)` 那一列的 `source` 映射；映射表**封閉**（僅 `twse_mi_index`→`TWSE`、`tpex_daily_quotes`→`TPEX`，其他值 raise，不得預設）。3 檔股票（6446/6472/6589）市場別隨時間改變過（上櫃轉上市），必須取最新一列，取第一列或任一列會拿到過期市場別 |
| 2 | 名稱清理 | 只移除任意位置的 `*`（資料品質標記，非公司簡稱本體）；`-KY`（開曼註冊）／`-DR`（存託憑證）原樣保留，剝除會造出不存在的路由關鍵字 |
| 3 | `description` 措辭 | 新列固定前綴 `[auto:UG-G3-SB2] 交易所簡稱（candidate_prices.security_name）`；6111／8932 舊名稱列改為 `[auto:UG-G3-SB2] 交易所舊簡稱，現名：<現名>`。固定前綴供日後 `LIKE '[auto:UG-G3-SB2]%'` 精確回溯或整批撤銷 |
| 4 | 既有 3 檔（2330/2382/6488） | 腳本先以 `stock_id` 明確排除，再用純 `INSERT`（**禁用 `ON CONFLICT`**）——任何意外撞名大聲失敗並 rollback，不被 `DO NOTHING` 靜默吞掉（`CLAUDE.md` §7.1） |

- 每日尾端重算掛點（§3.1），含冪等測試與 DoD 項目
- 訓練目標配置切換：`target_up_down` 或 `target_triple_barrier`，兩者皆存在於
  輸出 DataFrame，只有選定的一個進訓練
- `label_end_date_tb` 即時產生（§3.3），含時點落差容忍設計

## Out of Scope

- Specialist 模型訓練（`UG-G3-SB3`）
- Feature 計算邏輯本身變更（Gate 2 既有範圍，本 SB 只改「餵誰進去」的過濾條件）
- **458 檔資料回補本身**（`UG-G3-SB2a`，見 §4）
- 追蹤宇宙（`tracking_keywords`）擴大——路由補齊只解決「知道這檔股票對應哪個
  關鍵字」，不等於把它排進每日爬蟲抓取範圍，兩者是不同的決定

---

## 6. Failure Semantics & Tests

| 測試 | 驗證目標 |
|---|---|
| `test_panel_shape` | Long-format 面板列數 = Σ(各交易日「當期 `included` 股票」∩「該日有 `daily_ml_features` 列」的交集數) |
| `test_panel_no_future_dates` | 給定 `as_of`，面板輸出無 `trade_date > as_of`，且所用快照 `effective_date ≤ as_of`（防前視偏誤，`CLAUDE.md` §7.4） |
| `test_panel_universe_is_point_in_time`（新增） | 構造某股票在 2024 年某期 `included=TRUE`、2026 年某期 `included=FALSE` 的情境，斷言面板在前者對應日期含該股、後者不含 |
| `test_panel_target_column_selection` | 訓練目標配置切換正確，兩欄皆存在但只有選定欄位供訓練消費 |
| `test_panel_universe_filter_uses_snapshot_not_entity_mapping` | 面板股票範圍取自 `universe_snapshots.included`，不受 `entity_mapping` 有無路由列影響 |
| `test_panel_label_end_date_tb_present` | 面板輸出含 `label_end_date_tb` 欄位且非全 NaT |
| `test_panel_tolerates_label_end_date_target_mismatch`（新增） | 構造「有 `label_end_date_tb` 但 `target_triple_barrier` 為 NULL」的列，斷言讀取器不拋錯、不靜默丟棄（§3.3 時點落差容忍） |
| `test_daily_hook_recomputes_tail_h_plus_1_rows`（新增） | 新增一日 `stock_prices` 後，掛點正確重跑尾端 `H+1=6` 列，其餘列不變 |
| `test_daily_hook_is_idempotent`（新增） | 同一天重跑掛點兩次，`daily_ml_features` 結果相同 |

## 7. Risks & Trade-offs

| 風險 | 說明 |
|---|---|
| 458 檔資料缺口 | 已拆至 `UG-G3-SB2a`（DEC-036），本 SB 的面板在 `SB2a` 完成前只對 3 檔有真實資料，Gate B 需誠實揭露此時間差 |
| 情緒覆蓋率（RISK-015 延伸） | 即使價格資料補齊，`tracking_keywords` 只有 27 列，多數股票的 `sentiment_mean` 仍將長期為 U——這是 D3 實驗範圍聲明的一部分（Gate 3 §10 三.） |
| RISK-025 排程依賴 | 見 §3.2，已設計為低成本重算路徑，但重算本身仍需 PO 每次授權（比照 RISK-013） |
| 每日掛點的真實庫首次啟用 | 走 RISK-013 三項協議，需 PO binding confirmation（比照 `UG-G3-SB1`） |

## 8. E2E Verification Plan

- 容器內全套測試
- `gate0_contract_check.py`（若新增欄位或 SQL 查詢對應到契約文件，需同步 `FEATURE_REGISTRY.md`）
- 唯讀對真實庫試跑面板構建（3 檔現有資料 + PIT 過濾邏輯），人工核對輸出形狀與樣本列
- 路由補齊（455 筆）於隔離拋棄式容器驗證寫入，比照 `UG-G3-SB1` DoD 第 2 項模式

## 9. Documentation Sync

- `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2／UG-G3-SB2a Brief：已隨本次重送同步（§4）
- `entity_mapping` 語意變更（退回純路由）：`MULTI_SOURCE_DATA_CONTRACT.md` 或
  `FEATURE_REGISTRY.md` 對應章節同步
- `DECISIONS.md` DEC-036（`UG-G3-SB2a` 新增）已隨本次重送建立，狀態 `Proposed`

## 10. Definition of Done

| # | 項目 | 目標資料庫 |
|---|---|---|
| 1 | `panel_dataset.py` 建立，PIT 正確，§6 測試 PASS | 不涉及寫入 |
| 2 | Universe 過濾正確使用 `universe_snapshots`（`effective_date ≤ trade_date` 最近一期） | `postgres`@`localhost:5432`，唯讀 |
| 3 | 訓練目標配置切換正確 | 不涉及資料庫 |
| 4 | ~~`entity_mapping` 路由補齊 455 筆完成~~ **已完成（2026-09-09）** | `postgres`@`localhost:5432`，**RISK-013 三項協議全走完**：備份 `stock_prediction_system2_PRE_g3_sb2_routing_20260909_232124.dump`（71,828,551 bytes）→ `--write` 457 筆（455 檔，含 6111／8932 各 2 個 keyword）→ 寫入後唯讀查證（總列數 462、`[auto:UG-G3-SB2]` 前綴 457、既有 5 列逐字不變、無星號 keyword）→ 拋棄式容器還原驗證（`entity_mapping` 5 列，寫入前狀態）。**惰性驗證（步驟 5）發現追蹤宇宙由 4 檔變 8 檔，訂正 §5 宣稱、登記 RISK-022（四）與 `PROJECT_STATUS.md` §0.5 #20 每日 ETL 執行閘門，PO 裁決接受不回滾**，見 CHAL-009、`doc/upgrade/gates/evidence/UG_G3_SB2_routing_real_db_write.json` |
| 5 | ~~每日尾端重算掛點接上，冪等測試通過，首次啟用完成 RISK-013 三項協議~~ **接線部分已完成（2026-09-10，PO binding confirmation，僅接線）；「首次啟用」（實際觸發 `run_all_daily_tasks()`）不在本次範圍** | `postgres`@`localhost:5432`——接線本身無寫入（唯讀基線比對 24/24 相符）；`run_all_daily_tasks()` 實際執行受 `PROJECT_STATUS.md` §0.5 #20 閘門，`UG-G3-SB2a` Gate B 通過前不得執行，故「首次啟用完成 RISK-013 三項協議」這句原文在本 SB 範圍內不成立，留待閘門解除後另行處理 |
| 6 | §3 三項必答已落地為設計／實作 | 依項目而定——尾端 `insufficient_data` 每日重算歸屬：`recompute_tail_labels`／`apply_tail_labels`（已接線，未啟用）；RISK-025 與面板凍結排程：已登記關聯，`UG-G3-SB3` D3 必答項；`label_end_date_tb` 生成點：面板構建時即時計算（`build_panel_dataset` 內 `groupby.shift`），不持久化 |

## 11. 請求 PO 裁決事項

| # | 事項 | 選項 |
|---|---|---|
| 1 | §3、§5、§6、§10 修正內容 | 核准／修改 |
| 2 | 本提案是否核准進入實作 | 核准／退回修改 |

## 12. 未獲核准前的自我約束

- 不修改 `src/`、`tests/`、`database/`
- 不執行任何 DB migration 或資料寫入（§2 的查證皆為唯讀 `SELECT`）
- 不 Commit（本提案文件除外，且需 PO 授權）
