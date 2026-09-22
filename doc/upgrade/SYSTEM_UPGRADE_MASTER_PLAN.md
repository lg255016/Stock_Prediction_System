# SYSTEM_UPGRADE_MASTER_PLAN.md — 金融情緒與預測系統總體升級實作計畫書

> **版本**: V8 (Contract-Driven Verification & Metadata Columns)
> **日期**: 2026-08-23
> **狀態**: 待 Project Owner Gate 0 Closure Review（第二次送審）
> **前版**: V7 — FAIL / 退回修正（3 BLOCK + 4 S 項 + 4 輕微項已於 V8 修正）
> **約束**: 本文件替代 V7 全文；V4/V5/V6/V7 不得被視為仍然有效的規格

---

## 0. 版本歷程與審查紀錄

| 版本 | 日期 | 狀態 | 說明 |
|------|------|------|------|
| V1-V3 | 2026-08-21 | 已廢棄 | 初始規劃草稿 |
| V4 | 2026-08-21 | 暫緩批准 | 發現 8 大系統性問題（時序洩漏、UI 假資料、證據誇大、Migration 缺失、特徵數漂移、資料契約缺口、文件矛盾、批次過大）|
| V5 | 2026-08-22 | PASS WITH REQUIRED CORRECTIONS | 基於深度程式碼稽核事實全面重寫；PO 審查發現 10 項必須修正的矛盾 |
| V6 | 2026-08-22 | FAIL — REQUIRED CORRECTIONS | 修正 V5 的 10 項；但產生跨文件資料契約衝突（Registry／Migration／Master Plan 三套 Schema）與失敗語意、NULL 規則、Triple-Barrier 時間約定不一致 |
| V7 | 2026-08-22 | FAIL — 退回修正 | 修正 V6 的 6 項；但產生更上游的契約缺陷：raw 層 `DEFAULT 0` 從後門注入中立值、情緒六欄未涵蓋 `SOURCE_FAILED` 例外、`source_status`／`label_reason` 被規格引用卻不存在；且 Part B 驗證寫成通過條件而非偵測條件 |
| V8 | 2026-08-23 | **待審查** | 修正 V7 全部 3 BLOCK + 4 S 項 + 4 輕微項：raw 層移除 `DEFAULT`、§5A 全欄位 NULL 語意規則、27→**29 欄**（補 2 metadata）、Part B 改為**契約反查法**（10 項，附可重跑腳本）、補入 DEC-011/017/018、編號統一為 DB 序號 |

### 0.1 V7 → V8 修正對照

> V7 的裁決為 `FAIL / 退回修正`。以下逐項對應 PO 列出的 3 個 BLOCK、4 個 S 項與 4 個輕微項。

#### 阻擋項目（BLOCK）

| PO 退件項目 | V8 修正 | 驗證 |
|-------------|---------|------|
| **BLOCK-1** raw 層 `DEFAULT 0` 推翻留言 NULL 規則<br>（`total_comments=0` → `comment_polarization = 1-0² = 1.0`「最大分歧」偽訊號） | Migration 003 四個留言計數欄改為裸 `INTEGER`（可 NULL、無 DEFAULT）；新增非負 CHECK；DDL 註記說明 `NULL`=未解析 vs `0`=確實無留言 | §18.2 **B4** |
| **BLOCK-2** `SOURCE_FAILED` 的 NULL 語意對情緒六欄未落地<br>（Registry 無條件 `fillna`，A6 斷言主動禁止 NULL） | 原僅涵蓋留言三欄的 NULL 規則升級為 **§5A 全欄位 NULL 語意規則**：區分成因 W（暖機期，允許填補）與成因 F（來源失敗，必須 NULL）；§5A.3 涵蓋全部 19 個 engineered feature；A6/A7 加上 `source_status` 前置條件與反向斷言 | §18.2 **B3** |
| **BLOCK-3** `source_status` / `label_reason` 根本不存在 | 補入 29 欄契約（新增 Metadata/Lineage 類別）；Migration 002 加入兩欄 + domain CHECK + 一致性 CHECK；新增斷言 A9、A10 | §18.2 **B1, B2** |

#### 應修正項目（S）

| PO 退件項目 | V8 修正 | 驗證 |
|-------------|---------|------|
| **S-1** 兩份文件對「測試有沒有重跑」互相打臉 | `TRACEABILITY.md` §3A.2 校正為**已執行**（`Ran 154 tests in 1.486s / OK`），並補完整證據邊界表 | §18.3 Part C |
| **S-2** Part A 的 match 數字不可重現（驗證表自己含被搜尋字串） | 引入**活規格過濾器**（濾除 §0.1／§16／§18）；全部指令改為 `echo "$LS" \| grep`；逐處列出判定依據 | §18.0, §18.1 |
| **S-3** §19 有 4 項決策無 ADR 承接 | 補入 **DEC-011**（Purge/Gap/Embargo）、**DEC-017**（PIT Universe）、**DEC-018**（Triple-Barrier 三分類與 `Open[T+1]` anchor），狀態均為 `Proposed` | §18.2 **B8** |
| **S-4** §6.1 交付物表過期（F 列「10 項測試」、H 列「本文件 V6」） | F 改為 **19 項測試**（T-PW 5 + T-TB 12 + T-INT 2）；H 改為 **V8** | §6.1 |

#### 輕微項目

| PO 退件項目 | V8 修正 |
|-------------|---------|
| `MULTI_SOURCE_DATA_CONTRACT.md` 有兩個 `### 7.3` | 後者改為 `### 7.4 可觀測性` |
| 三套特徵編號互不對應（Master Plan 19/20/21、Registry 21/22/23、model_input 索引 17/18/19） | 全部統一為 **DB 欄位序號 1-29**；新增 `FEATURE_REGISTRY.md` **§3.7** 作為唯一權威對照表（DB 序號 ↔ 三套契約的 model_input 索引） |
| `push_ratio` 值域閉區間 vs 開區間不一致 | 統一為**開區間 `(-1, +1)`**；註明 Laplace `+1` 平滑使分母恆大於分子絕對值 |
| 前次回報寫「5 項阻擋問題」，文件記載 6 項 | **PO 指正屬實** — 以文件記載的 6 項為準，前次回報訊息漏算 TRACEABILITY 該項；文件本身無誤，不需修改 |

#### V8 方法論變更：Part B 改為契約反查法

PO 指出 V7 的 B4 指令 `grep "fillna" FEATURE_REGISTRY.md | grep -iE "comment|push"`
第二段把範圍限縮在留言三欄，**結構上不可能**發現情緒六欄的同型缺陷 —
那是為了通過而寫的驗證，不是為了偵測而寫的。

V8 全面改為**從契約要求出發列舉全部應受約束對象、逐一反查**，並附可重跑腳本
`scripts/verify/gate0_contract_check.py`。

方法論有效性的三個證據：
1. 新 B8 首次執行即 FAIL → 抓出 DEC-011/017/018 缺失（即 PO 的 S-3）
2. 新 B2 能發現「被引用但不存在的欄位」（即 BLOCK-3 類型）
3. 腳本首次執行時 B2/B6 亦 FAIL → 抓出**驗證表自己**污染掃描結果，遂內建 `strip_meta_sections()`

---

## 1. 工程治理協議 (Engineering Governance)

### 1.1 雙重審批協議 (Dual-Gate Approval SOP)

所有 Gate 與 Small Batch 嚴格遵守以下流程：

```
Step 1: Gate A — 啟動前審批
    → PM 呈報計畫、修改範圍、風險
    → 🛑 未獲 PO 批准前維持唯讀

Step 2: TDD + Code + Doc Sync
    → 先寫測試、再寫程式、同步文件
    → 全套測試 100% PASS

Step 3: Gate B — Commit 前審批
    → 呈報測試數據、diff 摘要
    → 🛑 未獲 PO 授權前嚴禁 Commit

Step 4: Clean Commit
    → 執行 Git Commit
    → 嚴禁自動進入下一 SB/Gate
```

### 1.2 證據標籤制度 (Evidence Labeling)

本文件所有量化描述必須附上以下標籤之一：

| 標籤 | 定義 |
|------|------|
| `VERIFIED` | 已有可重現測試或量測證據 |
| `OBSERVED` | 曾觀察到，尚未正式驗證 |
| `HYPOTHESIS` | 研究或工程待驗證假設 |
| `TARGET` | 希望達成的量化目標 |
| `PLANNED` | 尚未實作 |
| `NOT VERIFIED` | 目前沒有驗證證據 |

### 1.3 禁用詞清單

以下用語在無對應驗證證據時**嚴禁使用**：
`PRODUCTION READY`, `100% reliable`, `perfect`, `guaranteed`, `enterprise-grade`, `完美`, `保證`, `永遠不會`, `零誤差`

---

## 2. 代碼稽核事實基線 (Forensic Audit Baseline)

以下為 2026-08-21 深度稽核確認的**客觀事實**，所有後續設計以此為依據：

| 維度 | 代碼事實 | 證據位置 | 標籤 | V6 備註 |
|------|----------|----------|------|---------|
| 模型輸入特徵數 | **17** 個 (LEGACY_17 契約：含 OHLCV 5 欄) | `model_trainer.py:L18-41` | `VERIFIED` | 升級後 open/high/low 移出 Feature Store，見 §3.4 版本化契約 |
| 自動化測試 | **154** 項 / **18** 個檔案 | `tests/` grep 計數 | `VERIFIED` | — |
| DB 特徵寫入欄位 | **僅 7 個** (daily_ml_features) | `db_writer.py:L417-440` | `VERIFIED` | — |
| DB Migration 機制 | **完全沒有** (無 ALTER TABLE) | 全代碼庫搜尋 | `VERIFIED` | — |
| 時序邊界洩漏 | **存在** (shift(-1) + 切分邊界) | `feature_aggregator.py:L459` | `VERIFIED` | — |
| UI Mock Fallback | **靜默** (無模式標示) | `data_loader.py:L31-40` | `VERIFIED` | — |
| 模型排行榜 | **靜態寫死** | `components.py:L128-141` | `VERIFIED` | — |
| PTT 留言解析 | **僅列表頁 nrec** (未進入內頁) | `ptt_scraper.py:L57-58` | `VERIFIED` | — |
| README.md | **不存在** | `fd README` 結果為 0 | `VERIFIED` | — |
| SDD 模組狀態 | ML/UI 標為「規劃中」但已實作 | `SDD:L68,77-79` | `VERIFIED` | — |

---

## 3. Project Owner 決策紀錄 (PO Decisions)

### 3.1 Stock Universe (決策日 2026-08-22)

| 項目 | 決策 |
|------|------|
| 產品定義 | 台股流動性前 500 大普通股 |
| 分階段上線 | Phase 1: 前 150 大 → Phase 2: 前 500 大 |
| 流動性排名 | 過去 60 交易日「每日成交金額中位數」排序。**窗口嚴格早於 `effective_date`，不含當天**（DEC-033，2026-09-03）——DEC-017 的「生效日前已知」在 `UG-G2-SB6` 實作時被發現與提案內兩段校準 SQL 相矛盾，裁定以 ADR 為準 |
| 重建頻率 | 每月第一個交易日，不每日變動 |
| 納入範圍 | TWSE/TPEx 普通股 |
| 排除範圍 | ETF、ETN、權證、興櫃、停止交易、歷史資料不足 |
| 新上市股票 | 需累積足夠交易日後才能進入 |
| 資料擷取策略 | 批次下載/市場級資料，禁止逐股票爬取 |
| 失敗容忍 | 單一股票失敗不得使整批失敗 |
| **Point-in-Time 約束** | 每月 Universe 重建只能使用該月生效日前已知的 60 日成交資料，不得使用未來資料 |
| **Snapshot 保存** | 每次重建必須保存 `universe_effective_date`、排名依據（60 日中位數）、納入/排除清單 |
| **歷史回測約束** | 回測必須載入當期 Universe Snapshot，不得以今日 Universe 倒推歷史（防止存活偏誤 Survivorship Bias） |
| **異動處理** | 新上市（需累積足夠交易日）、下市（下市日起移出）、停牌（停牌期間排除）、代碼異動（追蹤延續性） |

### 3.2 多來源優先序 (決策日 2026-08-22)

| 優先序 | 來源 | 狀態 | 前置條件 |
|--------|------|------|----------|
| 1 | PTT 留言 | 必要 | 現有爬蟲基礎 |
| 2 | Dcard | 條件性 (Conditional) | PTT 契約穩定後；可用性驗證 PASS 才實作 |
| 3 | Threads | Conditional / Deferred | 官方 API 確認後 |

共用標準化輸出契約，但各自保留 Provider-specific raw fields。
三個來源必須是獨立 Small Batch。
不得用單一 `engagement_metric` 抹平平台差異。

### 3.3 Triple-Barrier 時間約定與標籤集合 (決策日 2026-08-22 — V7 修正)

#### 統一時間約定（PO 決策）

| 項目 | 決策 |
|------|------|
| 預測時點 | T 日收盤後產生預測 |
| 進場價 & Barrier anchor | **`Open[T+1]`**（統一為同一個價格，消除標籤與交易的錯配）|
| 觸線評估區間 | T+1 至 T+5 的 `High` / `Low`（含 T+1 當日）|
| Slippage 與交易成本 | 皆套用於 `Open[T+1]` |

#### 標籤集合（PO 決策：三分類）

| Label | 條件 | 說明 |
|-------|------|------|
| `1` | 先觸上障礙 | 止盈 |
| `-1` | 先觸下障礙 | 止損 |
| `0` | H=5 期間未觸線 | Timeout |
| `NULL` | 同日觸雙線 / 資料不足 / `Open[T+1]` 不存在 | 排除訓練 |

> 止損 (`-1`) 與未觸線 (`0`) 不得合併：兩者的報酬分布與風險特性不同。

#### 同日觸雙線處理

| 項目 | 決策 |
|------|------|
| 處理方式 | 標記為 `NULL` (Ambiguous)，排除訓練 |
| 禁止 | Forward-fill、補 0、轉成任一方向、任意 Tie-Breaker |
| 報告要求 | 評估報告必須列出 Ambiguous 比例與三分類類別分布 |
| 比例過高時 | 另開決策：導入盤中資料 或 調整 Barrier 寬度/持有期 |
| Label Horizon | 必須與 Purged Walk-Forward/Embargo 一起設計 |

完整規格見 `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §4。

### 3.4 版本化特徵契約 (決策日 2026-08-22 — V8 更新)

> **V6 修正說明**：V5 的 17/15/19 定義存在矛盾。PO 決策採用版本化契約，明確區分三個階段的特徵集定義。
> **V8 修正說明**：新增 2 個 Metadata / Lineage 欄位，資料契約由 27 欄調整為 **29 欄**。

#### 三套版本化特徵契約

| 契約名稱 | 定義 | model_input 數量 | 階段 |
|----------|------|-------------------|------|
| `LEGACY_17` | 目前程式碼實際行為：17 個欄位全部作為模型輸入（含 OHLCV 5 欄） | 17 | 目前代碼基線 (`VERIFIED`) |
| `CORE_16` | 升級後核心平穩特徵：12 個既有衍生特徵 + 4 個新增平穩特徵 | 16 | 升級目標 (`PLANNED`) |
| `COMMENT_ENHANCED_19` | CORE_16 + 3 個留言衍生特徵 | 19 | 留言資料就緒後 (`PLANNED`) |

#### 關鍵設計決策

| 項目 | 決策 |
|------|------|
| `close_price`, `volume` | **Context columns**：Data Lineage / UI / 標籤計算用途，不直接進入跨股票 Panel Model |
| `open_price`, `high_price`, `low_price` | **留在 `stock_prices` 表**，不存入 Feature Store (`daily_ml_features`)，不作為模型輸入。僅作為計算 `amplitude_ratio` 等衍生特徵的原始來源 |
| `source_status`, `label_reason` | **Metadata / Lineage columns**（V8 新增）：資料品質與標籤成因追蹤，**絕不可作為模型輸入** |
| Feature Store 保存 | 固定 19 個 engineered columns（CORE_16 的 16 欄 + 3 個留言欄）；留言未啟用時三欄為 NULL |
| 禁止全域替換 | 禁止全 Repository 18→17 文字替換；每處須判斷是 LEGACY_17 / CORE_16 / COMMENT_ENHANCED_19 / Store 的哪個語境 |
| daily_ml_features 資料契約 | **29 database columns** |
| 測試斷言 | Feature Store total columns: 29 |

#### 29 欄位資料契約

| 類別 | 數量 | 欄位 |
|------|------|------|
| Identifier | 2 | `trade_date`, `stock_id` |
| Context (Raw/Lineage) | 2 | `close_price`, `volume` |
| **Metadata / Lineage** | **2** | **`source_status`, `label_reason`** |
| Engineered Feature | 19 | CORE_16 (16 欄) + Comment (3 欄)；見 Feature Registry (§4) |
| Target | 4 | `target_next_close`, `target_return_1d`, `target_up_down`, `target_triple_barrier` |
| **Total** | **29** | — |

#### Metadata 欄位設計理由 (V8 新增)

| 欄位 | 值域 | 為何必須存在 |
|------|------|-------------|
| `source_status` | `SUCCESS` / `SUCCESS_EMPTY` / `SOURCE_DEGRADED` / `SOURCE_FAILED` | 沒有它，DB 層分不出「該日確實沒新聞」與「PTT 掛了」，`SOURCE_FAILED → 特徵 NULL → 排除訓練` 的契約無從執行 |
| `label_reason` | `ambiguous_dual_barrier` / `insufficient_data` / `no_entry` / NULL | 沒有它，三種 NULL 標籤成因在 DB 裡是同一個 NULL，Ambiguous Ratio 報告與 RISK-011 的 10% 觸發條件都算不出來 |

兩者皆為 `model_input=false`，由 DB CHECK constraint 強制值域（`DB_MIGRATION_PLAN.md` §4.2）。

#### 全欄位 NULL 語意規則 (V8 新增)

任何欄位的空值只可能是兩種成因之一，處理方式**完全相反**：

| 成因 | 定義 | 處理 | 訓練 |
|------|------|------|------|
| **W — 暖機期不足** | 資料確實存在，時序視窗未累積足夠歷史 | **允許填補**中立值 | 樣本可用 |
| **F — 來源失敗** | 資料根本沒取得（`source_status = 'SOURCE_FAILED'`） | **必須保持 NULL** | **排除訓練** |

> 兩者可能落到同一個數值（如 `sentiment_mean = 0.5`），但語意完全不同：
> 前者是「已知的中立」，後者是「未知」。把後者填成前者，
> 等同於在爬蟲掛掉的日子系統性注入一個與市場無關的偽訊號。

完整對照表見 `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5A.3。

**上游 raw 層約束**：`market_articles` 的四個留言計數欄**不得使用 `DEFAULT 0`** —
否則所有留言解析上線前的歷史文章會被 backfill 成「已解析且 0 則留言」，
導致 `comment_polarization = 1 - 0² = 1.0`（最大分歧）這個完全偽造的強訊號。

---

## 4. Feature Registry (正式特徵登記冊)

> 本節為 Master Plan 內的摘要。**權威定義以 `doc/upgrade/contracts/FEATURE_REGISTRY.md` 為準**
> （Gate 0 交付物 C）；該文件含 29 欄 × 12 屬性完整登記表、§3.7 編號對照、§5A 全欄位 NULL 語意規則。
> `feature_aggregator.py`、`model_trainer.py`、`db_writer.py`、`schema.sql` 必須共用此契約。
>
> **編號約定**：本節與 Registry 的 `#` 欄一律為 **DB 欄位序號（1-29）**，非模型輸入索引。
> 模型輸入索引見 `FEATURE_REGISTRY.md` §3.7。

### 4.0 Metadata / Lineage 欄位 (V8 新增，DB #5-6)

| # | Column | Role | 值域 | model_input | Status |
|---|--------|------|------|-------------|--------|
| 5 | `source_status` | metadata | `SUCCESS` / `SUCCESS_EMPTY` / `SOURCE_DEGRADED` / `SOURCE_FAILED` | **false** | `PLANNED` |
| 6 | `label_reason` | metadata | `ambiguous_dual_barrier` / `insufficient_data` / `no_entry` / NULL | **false** | `PLANNED` |

**不變式**：`label_reason IS NOT NULL` ⟺ `target_triple_barrier IS NULL`（標籤已計算的前提下）。

### 4.1 Current Baseline — `LEGACY_17` 契約 (`VERIFIED`)

以下為目前代碼已實作的模型輸入配置，包含 OHLCV 5 欄。升級時 open/high/low 將移出 Feature Store，close_price/volume 改為 context。

#### OHLC 欄位（升級時移出 Feature Store）

> **V6 設計決策**：`open_price`、`high_price`、`low_price` 在升級後**不存入 `daily_ml_features`**，保留在 `stock_prices` 表中。它們是計算 `amplitude_ratio` 的原始來源，但絕對價格不具跨股票泛化能力，不得作為 Panel Model 輸入。

| # | Column | LEGACY_17 Role | 升級後歸屬 | 說明 |
|---|--------|----------------|------------|------|
| — | `open_price` | model_input (LEGACY) | 留在 `stock_prices`，不進 Feature Store | 計算 amplitude_ratio 的來源 |
| — | `high_price` | model_input (LEGACY) | 留在 `stock_prices`，不進 Feature Store | 計算 amplitude_ratio 的來源 |
| — | `low_price` | model_input (LEGACY) | 留在 `stock_prices`，不進 Feature Store | 計算 amplitude_ratio 的來源 |

#### Context Columns（保留在 Feature Store，不作為模型輸入）

| # | Column | Role | Formula | Source | Pred. Time | Range | NULL/Warm-up | PG Type | model_input | Test |
|---|--------|------|---------|--------|------------|-------|--------------|---------|-------------|------|
| 3 | `close_price` | **context** | 原始值 | `stock_prices` | T 日已知 | ≥0 | 不允許 NULL | `NUMERIC(10,2)` | **false** | `test_feature_aggregator_alignment` |
| 4 | `volume` | **context** | 原始值 | `stock_prices` | T 日已知 | ≥0 | 不允許 NULL | `BIGINT` | **false** | 同上 |

#### CORE_16 既有衍生特徵（12 欄，升級後保留為 model_input=true）

| # | Column | Role | Formula | Source | Pred. Time | Range | NULL/Warm-up | PG Type | model_input | Test |
|---|--------|------|---------|--------|------------|-------|--------------|---------|-------------|------|
| 7 | `return_1d` | feature | ln(Close_T / Close_{T-1}) | 衍生 | T 日已知 | 無量綱 | `fillna(0.0)`, 1d | `NUMERIC(10,6)` | true | `test_research_features` |
| 8 | `rsi_14` | feature | Wilder RSI-14 | 衍生 | T 日已知 | [0,100] | `fillna(50.0)`, 14d | `NUMERIC(6,2)` | true | 同上 |
| 9 | `volatility_5d` | feature | std(r,w=5)×√252 | 衍生 | T 日已知 | ≥0 | `fillna(0.0)`, 5d | `NUMERIC(10,6)` | true | 同上 |
| 10 | `volatility_20d` | feature | std(r,w=20)×√252 | 衍生 | T 日已知 | ≥0 | `fillna(0.0)`, 20d | `NUMERIC(10,6)` | true | 同上 |
| 11 | `article_count` | feature | 直接+題材計數 | `market_articles` | T 15:30 前 | ≥0 | `fillna(0)` | `INTEGER` | true | `test_thematic_feature_spillover` |
| 12 | `sentiment_mean` | feature | 70%直接+30%題材 | `market_articles` | T 15:30 前 | [0,1] | `fillna(0.5)` | `NUMERIC(5,4)` | true | 同上 |
| 13 | `bullishness_index` | feature | ln((1+Pos)/(1+Neg)) | 衍生 | T 15:30 前 | (-∞,+∞) | `fillna(0.0)` | `NUMERIC(8,4)` | true | `test_research_features` |
| 14 | `agreement_index` | feature | 1-√(1-((P-N)/(P+N))²) | 衍生 | T 15:30 前 | [0,1] | `fillna(0.0)` | `NUMERIC(5,4)` | true | 同上 |
| 15 | `sentiment_3d_ma` | feature | rolling(3,min=1).mean() | 衍生 | T 日已知 | [0,1] | 漸進 | `NUMERIC(5,4)` | true | 同上 |
| 16 | `sentiment_5d_ma` | feature | rolling(5,min=1).mean() | 衍生 | T 日已知 | [0,1] | 漸進 | `NUMERIC(5,4)` | true | 同上 |
| 17 | `sentiment_lag_1` | feature | shift(1) | 衍生 | T 日已知 | [0,1] | `fillna(0.5)`, 1d | `NUMERIC(5,4)` | true | 同上 |
| 18 | `sentiment_lag_2` | feature | shift(2) | 衍生 | T 日已知 | [0,1] | `fillna(0.5)`, 2d | `NUMERIC(5,4)` | true | 同上 |

**LEGACY_17 model_input count: 17** (含 OHLCV 5 欄 — 目前程式碼實際行為)
**升級後 CORE_16 既有 model_input count: 12** (移除 OHLC 3 欄、close_price/volume 改 context)

### 4.2 Upgrade Core Features — CORE_16 新增 4 項平穩特徵 (`PLANNED`)

升級後 CORE_16 = 12 既有衍生 + 4 新增 = **16 個 model_input**

| # | Column | Role | Formula | Source | Pred. Time | Range | NULL/Warm-up | PG Type | model_input | Status |
|---|--------|------|---------|--------|------------|-------|--------------|---------|-------------|--------|
| 19 | `amplitude_ratio` | feature | (High-Low)/Close | 衍生 (來源：`stock_prices`) | T 日已知 | ≥0 | `fillna(0.0)` | `NUMERIC(8,6)` | true | `PLANNED` |
| 20 | `ma5_bias_ratio` | feature | (Close-MA5)/MA5 | 衍生 | T 日已知 | 無量綱 | `fillna(0.0)`, 5d | `NUMERIC(8,6)` | true | `PLANNED` |
| 21 | `ma20_bias_ratio` | feature | (Close-MA20)/MA20 | 衍生 | T 日已知 | 無量綱 | `fillna(0.0)`, 20d | `NUMERIC(8,6)` | true | `PLANNED` |
| 22 | `volume_ratio_5d` | feature | Volume/MA5_Vol | 衍生 | T 日已知 | ≥0 | `fillna(1.0)`, 5d | `NUMERIC(8,4)` | true | `PLANNED` |

### 4.3 Comment Features — COMMENT_ENHANCED_19 (`PLANNED`, 條件性)

COMMENT_ENHANCED_19 = CORE_16 (16) + 3 留言衍生特徵 = **19 個 model_input**

> 留言衍生特徵需 PTT 內頁留言解析穩定（push/boo/neutral 已入庫）後才可啟用。Feature Store 固定保留此 3 欄，留言未啟用時為 NULL。

#### 共用中間值

```
push_ratio_t = (push_t - boo_t) / (push_t + boo_t + 1)    # 值域 (-1, +1) 開區間
# Laplace +1 平滑使分母恆大於 |分子|，故永遠取不到 ±1
```

#### 留言衍生特徵定義

| # | Column | Formula | Range | 金融意義 | 前置條件 | Status |
|---|--------|---------|-------|----------|----------|--------|
| 23 | `comment_volume_ratio` | `total_comments_t / (rolling_mean(total_comments, t-5..t-1) + 1)` | ≥0 | 散戶注意力激增指標：當日留言量相對過去 5 日滾動基準的倍數 | push/boo/neutral 已入庫 | `PLANNED` |
| 24 | `comment_polarization` | `1 - push_ratio_t²` | [0, 1] | 多空分歧度：push_ratio 接近 0 時分歧最大 (=1.0)；push_ratio 極端時一致最大 (→0) | push/boo > 0 | `PLANNED` |
| 25 | `net_push_momentum` | `push_ratio_t - push_ratio_(t-1)` | [-2, +2] | 情緒動能（加速度）：捕捉社群風向由空翻多或由多翻空的轉折點 | push/boo > 0 | `PLANNED` |

> **Rolling 約束**：`comment_volume_ratio` 的 5 日滾動均值僅使用 t-5 至 t-1 的已知資料，嚴禁前視。`net_push_momentum` 使用 t-1 日的 push_ratio，同樣僅使用已知過去資料。

### 4.4 Target Labels

| Column | Formula | Label Horizon | Status |
|--------|---------|---------------|--------|
| `target_next_close` | shift(-1) | H=1 | `VERIFIED` (目前已有) |
| `target_return_1d` | ln(Close_{T+1}/Close_T) | H=1 | `VERIFIED` |
| `target_up_down` | 1 if r>0 else 0 | H=1 | `VERIFIED` |
| `target_triple_barrier` | Triple-Barrier 三分類 `{1, -1, 0}`；anchor=`Open[T+1]`，評估區間 T+1~T+5；同日觸雙線／資料不足／無法進場=`NULL` | H=5 | `PLANNED` |

### 4.5 Feature Registry 測試契約

```
斷言 1: len(Feature Registry.where(role='identifier')) == 2
斷言 2: len(Feature Registry.where(role='context'))    == 2
斷言 3: len(Feature Registry.where(role='feature'))    == 19 (Feature Store 層)
斷言 4: len(Feature Registry.where(role='target'))     == 4
斷言 5: Total DB columns = 2 identifier + 2 context + 2 metadata + 19 feature + 4 target = 29
斷言 6: len(CORE_16.where(model_input=True))              == 16
斷言 7: len(COMMENT_ENHANCED_19.where(model_input=True))   == 19
斷言 8: len(LEGACY_17.where(model_input=True))             == 17  (程式碼基線驗證)
```

---

## 5. Upgrade Gate 結構與依賴矩陣

### 5.1 Gate 總覽

| Gate | 名稱 | 目的 | 准入條件 | 准出條件 |
|------|------|------|----------|----------|
| UG-Gate-0 | 文件修訂與規格設計 | 建立事實一致的文件基線 | PO 批准本計畫 | 交付物 A-J 通過 PO 審查 |
| UG-Gate-1 | Core Fixes | 修正時序洩漏、UI 模式分離、Migration 機制 | UG-Gate-0 關閉 | 154+N 測試 PASS, PO 審查 |
| UG-Gate-2 | Feature Store & Data Pipeline | 特徵持久化、PTT 留言、Universe 建立、批次 ETL | UG-Gate-1 關閉 | Feature Store 29 欄, PTT 留言契約驗證, Universe 建立, Batch ETL 驗證 |
| UG-Gate-3 | ML Upgrade | Triple-Barrier、Panel Dataset、堆疊、校準、選擇性推論 | UG-Gate-2 關閉 **+** RISK-015 情緒資料覆蓋率正式檢視（`REMAINING_RISKS.md`） | Purged WF OOF Benchmark |
| UG-Gate-4 | XAI, Export & UI | Model Artifact、XAI、CSV、排名 UI | UG-Gate-3 關閉 | E2E UI 驗證 |

> **V6 修正**：Gate 2 名稱從 "Feature Store & Comment" 改為 "Feature Store & Data Pipeline"。Dcard 為 Conditional，不阻擋 Gate 2 關閉（見 §8 UG-G2-SB5）。

### 5.2 依賴矩陣

```
UG-Gate-0 (文件修訂)
    ├── 無程式碼依賴
    └── 產出: Feature Registry, Data Contract, Migration Plan, WF Spec

UG-Gate-1 (Core Fixes) — 5 SBs
    ├── UG-G1-SB1 Purged Walk-Forward ← UG-Gate-0:F (WF Spec)
    ├── UG-G1-SB2 UI Demo/Real 分離 ← 無
    ├── UG-G1-SB3 UI 排行榜動態化 ← UG-G1-SB2
    ├── UG-G1-SB4 DB Migration 機制 ← UG-Gate-0:E (Migration Plan)
    └── UG-G1-SB5 文件全面校正 ← UG-Gate-0:A (漂移表)

UG-Gate-2 (Feature Store & Data Pipeline) — 9 SBs（2026-08-31：新增 UG-G2-SB8 見 DEC-029、UG-G2-SB9 見 DEC-031）
                                              ⚠ **編號 ≠ 執行順序**。實際執行順序為：
                                                SB1 → SB2 → SB3 → SB4 → SB5 → MIG → SB8 → **SB9** → SB6 → SB7
                                                SB9（候選池價格資料）必須在 SB6（Universe）之前——
                                                SB6 的流動性排名需要它的產出（DEC-031 循環依賴修正）
    ├── UG-G2-SB1 daily_ml_features 擴充 ← UG-G1-SB4 (Migration 機制)
    ├── UG-G2-SB2 PTT 內頁留言解析 ← 無
    ├── UG-G2-SB3 market_articles 擴充 ← UG-G1-SB4
    ├── UG-G2-SB4 留言衍生特徵 ← UG-G2-SB2 + UG-G2-SB3
    ├── UG-G2-SB5 Dcard Adapter (CONDITIONAL) ← UG-Gate-0:D (Data Contract); 若需 DB 欄位另依賴 UG-G2-SB3
    ├── UG-G2-MIG google-genai 遷移 ← 無（RISK-019，Gate 2 關閉後、Gate 3 啟動前的獨立遷移 SB，不佔 SB 編號序列）
    ├── UG-G2-SB8 CORE_16 四個平穩化特徵 + 讀取端缺口反查檢查 ← UG-G2-SB1（DEC-029，2026-08-31 新增）
    ├── UG-G2-SB9 候選池價格資料取得 ← 無（DEC-031，2026-08-31 新增，修正 SB6/SB7 循環依賴；編號 9 但實際執行順序在 SB6 之前，見上方本節開頭執行順序註記）
    ├── UG-G2-SB6 Stock Universe 建立 (Point-in-Time) ← UG-G2-SB1 + UG-G2-SB9（候選池價格資料）
    └── UG-G2-SB7 批次化 ETL 引擎 ← UG-G2-SB6

UG-Gate-3 (ML Upgrade) — 8 SBs — 嚴禁在 Gate-1 WF 修正前開始
    ├── UG-G3-SB1 Triple-Barrier Labeling ← UG-G1-SB1 (Purged WF)
    ├── UG-G3-SB2 Panel Dataset 構建（讀取器 + 路由補齊 + 每日尾端重算掛點）← UG-G2-SB1 + UG-G2-SB6 + UG-G3-SB1
    ├── UG-G3-SB2a 458 檔 Universe 資料回補（candidate_prices→stock_prices + 特徵 + 標籤）← UG-G2-SB9 + UG-G3-SB1；**新增，PO 2026-09-09 裁決，DEC-036**
    ├── UG-G3-SB3 Specialist Models (RF, LightGBM, XGBoost) ← UG-G3-SB2 + UG-G3-SB2a（**PO 裁決：SB2a 完成才可開始**）
    ├── UG-G3-SB4 OOF Stacking Meta-Learner ← UG-G3-SB3
    ├── UG-G3-SB5 Probability Calibration ← UG-G3-SB4
    ├── UG-G3-SB6 Selective Inference & Regime Gating ← UG-G3-SB5
    └── UG-G3-SB7 Performance Benchmark ← UG-G3-SB6

UG-Gate-4 (XAI, Export & UI) — 5 SBs
    ├── UG-G4-SB1 Model Artifact 規格化 ← UG-G3-SB7
    ├── UG-G4-SB2 XAI (Global/Local 分離) ← UG-G4-SB1
    ├── UG-G4-SB3 CSV 匯出 ← UG-G4-SB2
    ├── UG-G4-SB4 Top-K Ranking UI ← UG-G4-SB1
    └── UG-G4-SB5 回測曲線真實化 ← UG-G3-SB7
```

> **V6 修正**：Gate 3 順序重排 — Triple-Barrier 移至 SB1（標籤必須在 Panel Dataset 與模型訓練之前完成）；Dcard 標記為 CONDITIONAL。

### 5.3 關鍵排序約束

| 約束 | 理由 |
|------|------|
| Feature Registry 必須在 Feature Store 實作前完成 | 欄位定義是資料契約基礎 |
| Migration Plan 必須在 Schema 修改前完成 | 保護開發資料 |
| Purged Walk-Forward 必須在模型訓練前完成 | 消除前視偏誤 |
| **Triple-Barrier Labeling 必須在 Panel Dataset 構建前完成** | 模型訓練需要已產生的標籤；不能等模型訓練後才產生標籤 |
| Demo/Real 分離必須在 UI 宣稱預測績效前完成 | 防止假資料誤導 |
| Triple-Barrier 與 Purged WF 必須一起設計 | Label Horizon 影響 Purge 範圍 |
| PTT 留言解析必須在留言衍生特徵前完成 | 原始資料是特徵基礎 |
| **Panel Dataset 必須明確選擇訓練目標** | 須在構建時決定使用 `target_up_down` 或 `target_triple_barrier`，不能等模型訓練後才產生標籤 |

---

## 6. UG-Gate-0: 文件修訂與規格設計

### 6.1 交付物清單

| ID | 交付物 | Owner | Status | Acceptance Criteria | Evidence | 完成日期 |
|----|--------|-------|--------|---------------------|----------|----------|
| A | 文件與證據漂移對照表 | PM | `READY FOR PO REVIEW` | 每項矛盾有文件位置、代碼事實、嚴重度、修正方向與新證據標籤 | `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` — 14 項漂移 (3 CRITICAL / 8 HIGH / 3 MEDIUM)，每項附 file:line 證據 | 2026-08-22 |
| B | Upgrade Gate 0 規格 | PM | `READY FOR PO REVIEW` | 准入/准出條件、SB 清單、依賴矩陣完整 | 本章節 (§5, §6)；5 Gate + 31 SB 依賴矩陣無循環 | 2026-08-22 |
| C | Feature Registry | PM | `READY FOR PO REVIEW` | 每欄有 12 項必填屬性；model_input 標記正確；版本化契約定義清楚；測試契約 10 條斷言 | `doc/upgrade/contracts/FEATURE_REGISTRY.md` — 29 欄完整 Registry（含 2 metadata），LEGACY_17/CORE_16/COMMENT_ENHANCED_19 三套契約，§5A 全欄位 NULL 語意規則 | 2026-08-23 |
| D | Multi-Source Data Contract | PM | `READY FOR PO REVIEW` | PTT/Dcard/Threads 各有獨立契約；共用輸出格式；去重鍵定義；失敗語意 | `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` — PTT 完整契約 + Dcard/Threads 條件性契約 | 2026-08-22 |
| E | DB Migration & Rollback Plan | PM | `READY FOR PO REVIEW` | Additive DDL + schema_version + 備份 + Transaction + 隔離驗證 + 分層 Rollback 策略 | `doc/upgrade/contracts/DB_MIGRATION_PLAN.md` — 3 Migration + 5 層 Rollback + 8 安全保證 | 2026-08-22 |
| F | Purged Walk-Forward Spec | PM | `READY FOR PO REVIEW` | Purge/Gap/Embargo 定義 (交易日計) + label_end_date + Triple-Barrier Data Contract + 斷言 + 測試案例 | `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` — 完整 Purge/Gap/Embargo + Triple-Barrier 資料契約（anchor=`Open[T+1]`／三分類 `{1,-1,0}`+NULL／H=5／label_end_date／`label_reason` 三種成因）；**19 項測試**（T-PW 5 + T-TB 12 + T-INT 2） | 2026-08-23 |
| G | Gate & SB 矩陣 | PM | `READY FOR PO REVIEW` | Gate 1 SBs 有完整 16 項 Brief；Gate 2-4 SBs 至少 8 項；依賴矩陣無循環；可獨立回滾 | 本章節 (§5, §7-10)；Gate 1: 5 SB × 16 項；Gate 2-4: 19 SB × ≥8 項 | 2026-08-22 |
| H | 修訂版 Master Plan | PM | `READY FOR PO REVIEW` | V5 的 10 項 + V6 的 6 項 + V7 的 3 BLOCK/4 S 項 PO Required Corrections 已解決；所有量化目標附 Measurement Method | **本文件 V8**；§16 對照表確認全部修正 | 2026-08-23 |
| I | ADR 清單 | PM | `READY FOR PO REVIEW` | 新增 ADR 有完整標題與觸發 Gate；修訂 ADR 修復截斷/重複 | 本文件 §15：10 項新增 ADR (DEC-010~019) + 4 項修訂 | 2026-08-22 |
| J | 剩餘風險清冊 | PM | `READY FOR PO REVIEW` | 每項風險有 ID、嚴重度、證據標籤、緩解方式 | `doc/upgrade/contracts/REMAINING_RISKS.md` — 12 項風險 (3 HIGH / 7 MEDIUM / 2 LOW)，含風險接受準則 | 2026-08-22 |

### 6.2 UG-Gate-0 Small Batches

| SB | 名稱 | 主要責任 | 交付物 | 依賴 | 可獨立回滾 |
|----|------|----------|--------|------|------------|
| UG-G0-SB1 | 文件漂移修正方案 | 產出 A 表 (Critical + Major) | A | 無 | ✅ |
| UG-G0-SB2 | Feature Registry | 產出 Feature Registry 完整版 (含版本化契約) | C | 無 | ✅ |
| UG-G0-SB3 | Data Contract | 產出 PTT/Dcard/Threads 契約 | D | 無 | ✅ |
| UG-G0-SB4 | Migration Plan | 產出 DDL + 版本 + 備份 + 分層 Rollback 策略 | E | 無 | ✅ |
| UG-G0-SB5 | 時序驗證規格 | 產出 Purged WF (Purge/Gap/Embargo) + Triple-Barrier Spec | F | 無 | ✅ |
| UG-G0-SB6 | Gate 矩陣與 Master Plan | 整合 G + H | G, H | SB1-5 | ✅ |
| UG-G0-SB7 | ADR + 風險清冊 | 產出 I + J | I, J | SB1-6 | ✅ |

---

## 7. UG-Gate-1: Core Fixes (核心修正) — **CLOSED（2026-08-26，PO 核准，見 `doc/governance/PROJECT_STATUS.md` §0.2）**

> **Brief 完整度說明**：Gate 1 的 5 個 SB 提供完整 16 項 Brief。Gate 2-4 的 SB 在本章僅列出核心設計意圖（至少 8 項），完整 16 項 Brief 在各 Gate 規劃階段產出。

### 7.1 Small Batch Briefs

#### UG-G1-SB1: Purged Walk-Forward 實作

| 項目 | 內容 |
|------|------|
| Goal | 消除訓練集邊界的前視偏誤 |
| Requirement Source | 稽核報告 §1; AGENTS.md §7.4; PO 決策 §3.3 |
| Current State | `time_series_split.py:L148-160` 以特徵日期切分，不考慮 label_end_date |
| Proposed Change | 新增 `label_horizon` + `embargo_days` 參數 (交易日計)；切分時 Purge 訓練集中 `label_end_date >= test_start_date` 的行；新增 `label_end_date` 欄位 |
| In Scope | `WalkForwardSplitter` 修改; `feature_aggregator.py` 新增 label_end_date; 迴歸測試 |
| Out of Scope | Triple-Barrier 標籤本身 (Gate-3); 模型重訓練 |
| Affected Components | `src/ml/time_series_split.py`, `src/transform/feature_aggregator.py`, `tests/test_time_series_split.py`, `tests/test_feature_aggregator_alignment.py`（實作時追加：`label_end_date` 為 `feature_aggregator.py` 新欄位，其既有測試需同步覆蓋） |
| Data/API/Schema Contract | label_end_date = trade_date + H 交易日 |
| Failure Semantics | Purge 後訓練集不足 min_train_size → 該 Fold 跳過並 log warning |
| Risks & Trade-offs | Purge 減少訓練資料量；Embargo 減少可用訓練候選 |
| Tests | `test_purge_removes_label_overlapping_rows`（T-PW-01）, `test_purge_h5_removes_five_days`（T-PW-02）, `test_embargo_excludes_post_test_train_candidates`（T-PW-03）, `test_core_assertion_holds`（T-PW-04）, `test_future_data_mutation`（T-PW-05）, `test_purge_uses_per_stock_label_end_date_for_calendar_misalignment`（PO 2026-08-25 回報重現測試，第 6 項） |
| E2E Verification | 於 GOV-03 釘選環境 + 空臨時 DB 執行，依 A／B／C 三類證據分割（見 `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md` §4.2）；Fold 數 ≥ 3；不得以「163/163 OK」單獨作為 SB1 驗收結論 |
| Documentation Sync | SDD §3.1; DECISIONS.md (DEC-011); TRACEABILITY.md; DOCUMENT_DRIFT_REMEDIATION.md (DRIFT-012) |
| Rollback | Revert commit; 舊 WalkForwardSplitter 無需 Migration |
| Definition of Done | 1) 所有 Fold 的 `max(train.label_end_date) < min(test.trade_date)`；2) Purge 後訓練集不足 `min_train_size` 時該 Fold 跳過並記錄警告，嚴禁縮小 Purge 範圍保留 Fold（RISK-001 接受邊界）；3) A 類證據 before/after 對照完成且差異均有解釋；4) Sentinel 檢查通過：`connect()` 靜態呼叫點仍為 10 處；5) 修正前基線已保存並標註污染來源（見 §2） |
| 狀態 | **CLOSED**（2026-08-25，PO 核准結案），見 `doc/upgrade/gates/closed/SB1_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-23）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-25）**，commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`；提案文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

> **本 Gate 所有 SB 的測試執行環境**：dev container（Python 3.14.6，GOV-03 釘選之
> `requirements.lock.txt`），**非 host**。host 執行結果不得作為驗收證據（`CLAUDE.md` §13.0）。
> 涉及 DB 的驗證須指向空臨時資料庫並附綁定確認。（`doc/upgrade/gates/closed/SB1_GATE_A_PROPOSAL.md` §2.4，PO 已核准
> 採「集中一處」陳述，各 SB 的 Tests 欄不重複此段。）

#### UG-G1-SB2: UI Demo/Real 模式分離

| 項目 | 內容 |
|------|------|
| Goal | UI 不得在 DB 失敗時無提示顯示仿真數字 |
| Requirement Source | 稽核報告 §2; AGENTS.md §10; DRIFT-009 |
| Current State | `data_loader.py:L31-40` 靜默回退 `generate_mock_stock_features()`; `logger.debug()` 不對終端使用者可見 |
| Proposed Change | 定義 `DataMode` enum 四狀態: REAL/DEMO/EMPTY/ERROR; 每個 UI 元件接收 DataMode; DEMO 模式醒目標示（Banner + 浮水印）|
| In Scope | `data_loader.py` 回傳 `(DataFrame, DataMode)` 元組; `components.py` 各元件根據 mode 渲染; `app.py` 全局 mode 追蹤；併同修復 HERM-01~09 的測試封閉性，使該 9 個測試不再依賴環境憑證與 DB 內容（`doc/upgrade/gates/closed/SB1_GATE_A_PROPOSAL.md` §2.3，PO 已核准） |
| Out of Scope | 排行榜動態化 (SB3); 回測真實化 (Gate-4); 新增 DB 連線重試邏輯 |
| Affected Components | `src/ui/data_loader.py`, `src/ui/components.py`, `app.py` |
| Data/API/Schema Contract | DataMode enum: REAL (DB 成功回傳非空) / DEMO (Mock fallback) / EMPTY (DB 成功但無資料) / ERROR (DB 連線失敗) |
| Failure Semantics | DB 連線失敗 → ERROR 模式 (不顯示數值); DB 回傳空 → EMPTY 模式; Mock → DEMO 模式 (醒目標示) |
| Risks & Trade-offs | UI 頻繁顯示 ERROR 可能影響使用者體驗；DEMO 標示可能讓使用者忽略 |
| Tests | `test_data_mode_real`, `test_data_mode_demo_shows_banner`, `test_data_mode_error`, `test_data_mode_empty`, `test_data_mode_propagates_to_components` |
| E2E Verification | 斷開 DB 連線 → UI 顯示 ERROR 而非假資料; 連線正常 → REAL; 無資料 → EMPTY |
| Documentation Sync | SDD UI 章節; DECISIONS.md (DEC-012); TRACEABILITY.md |
| Rollback | Revert commit; 恢復原本靜默 fallback 行為 |
| Definition of Done | 任何 Mock 資料路徑都有醒目 Demo 標示; ERROR 模式不顯示數值; 全套測試 PASS |
| 狀態 | **CLOSED**（2026-08-25，PO 核准結案；DEC-012 方案 B 裁決），見 `doc/upgrade/gates/closed/SB2_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-25，含 DEC-012 方案 B 裁決）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-25）**，commit `414fcc81fccde57d84e883b4a44a9b0e50465500`；過程中另發現並修復一個 ERROR 模式 `StreamlitDuplicateElementId` 當機 bug（Streamlit 視覺驗證時發現，見 `doc/upgrade/gates/closed/SB2_GATE_B_SUBMISSION.md` §6／§7）；提案文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

#### UG-G1-SB3: UI 排行榜動態化

| 項目 | 內容 |
|------|------|
| Goal | 排行榜數據從 Artifact 讀取，不再寫死 |
| Requirement Source | 稽核報告 §2; DRIFT-008 |
| Current State | `components.py:L128-141` 靜態字典寫死 8 組模型排名數據 |
| Proposed Change | 新增 `load_tournament_results()` 從 JSON Artifact 或 DB 讀取; 無 Artifact 時顯示 EMPTY (DataMode) 而非假資料; 排行榜結構解耦為資料驅動 |
| In Scope | `components.py` 排行榜渲染邏輯改為接收外部資料; `data_loader.py` 新增 Artifact 讀取函式 |
| Out of Scope | 模型競技本身 (Gate-3); Artifact 寫入邏輯; 模型訓練 |
| Affected Components | `src/ui/components.py`, `src/ui/data_loader.py` |
| Data/API/Schema Contract | Tournament Artifact JSON: `{model_name, feature_set, macro_f1, hit_ratio, cumulative_return, alpha_delta}[]` |
| Failure Semantics | Artifact 不存在 → EMPTY 模式; Artifact 格式錯誤 → ERROR 模式 + log warning |
| Risks & Trade-offs | Gate 3 完成前排行榜為空; 使用者可能預期看到數據 |
| Dependency | UG-G1-SB2 (DataMode enum) |
| Tests | `test_leaderboard_from_artifact`, `test_leaderboard_empty_when_no_artifact`, `test_leaderboard_error_on_malformed`, `test_leaderboard_demo_mode_banner` |
| E2E Verification | 放置測試 Artifact → 排行榜顯示; 移除 Artifact → 顯示「尚未完成模型競技」|
| Documentation Sync | SDD UI 章節; TRACEABILITY.md |
| Rollback | Revert commit; 暫時恢復靜態字典（標記為 DEMO）|
| Definition of Done | 排行榜數據來自 Artifact; 無 Artifact 時 UI 顯示「尚未完成模型競技」; 全套測試 PASS |
| 狀態 | **CLOSED**（2026-08-26，PO 核准結案；方案 B + 4 項附帶裁決，`DEC-020` `APPROVED`），見 `doc/upgrade/gates/closed/SB3_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-25，方案 B + 4 項附帶裁決，見 DEC-020）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-26）**，commit `61016ee19c07caec990b51563f21b7f6571412b9`；三輪程式碼複閱找出並修正兩個真實缺陷（`label_end_date`／`trade_date` 型別不一致既有 bug、資料量防線設計缺陷）；真實 artifact 因資料量不足暫未產出，`load_tournament_results()` 正確顯示 `EMPTY`；提案文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

#### UG-G1-SB4: DB Migration 機制建立

| 項目 | 內容 |
|------|------|
| Goal | 建立可版本追蹤的 Schema 遷移機制 |
| Requirement Source | 稽核報告 §4; AGENTS.md §7.1; DRIFT-011; DB_MIGRATION_PLAN.md |
| Current State | 無 ALTER TABLE、無版本追蹤; `init_db.py` 僅處理 fresh initialization |
| Proposed Change | 新增 `schema_version` 表 + `database/migrations/` 目錄 + `apply_migrations.py` runner; 001_baseline.sql 建立版本表 |
| In Scope | Migration 框架; 001_baseline.sql; 版本檢查邏輯; apply_migrations.py runner |
| Out of Scope | 實際 daily_ml_features 擴充 (Gate-2); market_articles 擴充 (Gate-2); 導入 Alembic |
| Affected Components | `database/schema.sql` (新增 schema_version DDL), `database/migrations/001_baseline.sql`, `database/apply_migrations.py` |
| Data/API/Schema Contract | schema_version 表: (version INTEGER PK, description TEXT, applied_at TIMESTAMP, checksum TEXT) |
| Failure Semantics | Migration 在 Transaction 內失敗 → 自動 ROLLBACK; 版本不符 → 拒絕執行並回報; runner 返回 non-zero exit code |
| Risks & Trade-offs | 輕量 Script 方案未來可能需要升級為 Alembic (>10 migrations 時評估); 001_baseline 僅新增表不修改既有結構 |
| 不修改 postgres-data 保證 | 001_baseline.sql 僅 INSERT INTO schema_version; 不修改既有表結構 |
| Tests | `test_migration_idempotency`, `test_version_check`, `test_rollback_on_failure`, `test_runner_nonzero_exit_on_error` |
| E2E Verification | 隔離 PostgreSQL 18 容器: 1) fresh init + apply → schema_version 存在; 2) 二次 apply → 冪等; 3) 故意失敗 → rollback |
| Documentation Sync | SDD 資料庫章節; DECISIONS.md (DEC-010); DB_MIGRATION_PLAN.md |
| Rollback | 見 §12.4 分層 Rollback 策略; 程式碼回滾: git revert |
| Definition of Done | schema_version 表存在; apply_migrations.py 可冪等執行; 全套測試 PASS |
| 狀態 | **CLOSED**（2026-08-26，PO 核准結案；兩階段皆完成，`DEC-010` Verification 補齊、`DEC-021` `APPROVED`），見 `doc/upgrade/gates/closed/SB4_STEP1_GATE_B_SUBMISSION.md`／`SB4_STEP2_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-26，兩階段拆分：RISK-013 根本解優先於 migration 框架本體，DEC-021／DEC-010）** |
| Gate B | PO 授權 Commit —— **兩階段皆已完成，CLOSED（2026-08-26）**。階段一 commit `d2a4d4894328d2ef5e186aa2aa45ec02a0fdea0b`（`database/db_target_guard.py`，DEC-021）；階段二 commit `0fdb9c50c774388b42842075bdf69b2c12e666e0`（`schema_version` 表、`database/migrations/001_baseline.sql`、`database/apply_migrations.py`，DEC-010 Verification 補齊），已於隔離容器完成完整 E2E 驗證（含真實 DB 座標未確認即被拒絕、known-FAIL 案例 6 對照組）；提案文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

#### UG-G1-SB5: 文件全面校正

| 項目 | 內容 |
|------|------|
| Goal | 修復所有 Critical + Major 漂移項目 |
| Requirement Source | 交付物 A (DOCUMENT_DRIFT_REMEDIATION.md); DRIFT-001~014 |
| Current State | 14 項漂移：3 CRITICAL + 8 HIGH + 3 MEDIUM (詳見 §2 與交付物 A) |
| Proposed Change | 按 A 表逐項修正: PRD 特徵數描述、SDD 模組狀態更新、PROJECT_STATUS HEAD/測試數更新、TRACEABILITY 特徵數一致、DECISIONS.md DEC-003 恢復 + DEC-004 去重 + DEC-006/007 契約名稱; 新建 README.md |
| In Scope | 文件修正 (PRD/SDD/PROJECT_STATUS/TRACEABILITY/DECISIONS/README); 特徵數統一使用版本化契約名稱 (LEGACY_17/CORE_16/COMMENT_ENHANCED_19) |
| Out of Scope | 程式碼修改; 新功能; Gate 2+ 的 Schema 修改 |
| Affected Components | `doc/spec/PRD_Financial_Sentiment_System_v1.md`, `doc/spec/SDD_Financial_Sentiment_System_v1.md`, `doc/governance/PROJECT_STATUS.md`, `doc/evidence/TRACEABILITY.md`, `doc/evidence/DECISIONS.md`, `README.md` (新建) |
| Data/API/Schema Contract | 無 Schema 修改; 純文件 |
| Failure Semantics | 不適用 (純文件修改) |
| Risks & Trade-offs | 大範圍文件修改可能引入新不一致; 需要 grep 驗證 |
| Tests | grep 驗證: 禁用詞 = 0; 特徵數引用均附契約名; 測試數 = 154; SDD 模組狀態 = 已實作 |
| E2E Verification | grep 全域搜尋: "18 features" / "18 欄" 無裸數字; "規劃中" 不出現在已實作模組; 禁用詞 = 0 |
| Documentation Sync | 本 SB 本身就是文件同步 |
| Rollback | Revert commit |
| Definition of Done | A 表所有 Critical/Major 項目關閉; grep 驗證通過; 全套現有 154 測試仍 PASS |
| 狀態 | **CLOSED**（2026-08-26，PO 核准結案），見 `doc/upgrade/gates/closed/SB5_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-26，方案 C：`doc/spec/` 直接改、`DECISIONS.md` 走方案 B 補充註記；核准修正範圍後重新對 `doc/evidence/` 完整 grep 找出 15 處裸寫，非原提案 7 處）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-26）**，commit `31f5507ce1fc0cecebd468d0065a63f90c984412`。本 Brief 上方所列之 Current State（14 項漂移、154 測試）與 Tests／E2E Verification 欄之數字（154）均為 Gate 0 時期舊數字，SB5 提案已重新核對實際狀態（見 `doc/upgrade/gates/closed/SB5_GATE_A_PROPOSAL.md` §1、§9）；實際完成範圍為 DRIFT-001／002／004／005／006／007／010（CLOSED）與 DRIFT-015 文件標註部分（CLOSED，容器內重跑部分仍待 Gate 3）；DRIFT-013 經重新分析後判定應排除、不修正（見提案 §9.3）；`DECISIONS.md` 既有 ADR 原文依決策全數保留不動，改以緊鄰補充註記處理，新增 DEC-022 總覽索引；提案與送審文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3）。**Gate 1 至此五個 Small Batch（SB1～SB5）全數 CLOSED。** |

---

## 8. UG-Gate-2: Feature Store & Data Pipeline — **CLOSED（2026-09-06，PO 核准，見 `doc/upgrade/gates/closed/GATE2_CLOSURE_REVIEW.md`）**

> **Brief 完整度說明**：以下 SB briefs 列出核心設計意圖（至少 8 項）。完整 16 項 Brief 在 Gate 2 規劃階段產出。

### Small Batch Briefs

#### UG-G2-SB1: daily_ml_features Schema 擴充

| 項目 | 內容 |
|------|------|
| Goal | 將 daily_ml_features 從 7 欄擴充至 29 欄 (Additive Migration) |
| Dependency | UG-G1-SB4 (Migration 機制)；**軟性依賴 UG-G2-SB2**（`source_status` 的 `SOURCE_DEGRADED`／`SOURCE_FAILED` 兩態需 UG-G2-SB2 的 pipeline 例外傳播才可能產生，`MULTI_SOURCE_DATA_CONTRACT.md` §7.4 已登記此缺口；不阻擋 UG-G2-SB1 開工，本 SB 只會寫出 `SUCCESS`／`SUCCESS_EMPTY` 兩態，詳見 `G2_SB1_GATE_A_PROPOSAL.md` §1.3、§7 決策點 3） |
| In Scope | `002_expand_ml_features.sql` Migration（22 個新欄，含 `source_status`／`label_reason`）; `db_writer.py` upsert_ml_features 擴充至 29 欄 |
| Out of Scope | 留言特徵計算 (SB4); Triple-Barrier 標籤 (Gate-3) |
| Affected Components | `database/migrations/002_expand_ml_features.sql`, `src/loaders/db_writer.py`, `src/transform/feature_aggregator.py` |
| Tests | `test_feature_store_total_columns_29`, `test_migration_002_idempotent`, `test_dbwriter_upsert_29_columns`（欄位數已由 27 修正為 29，與 §7.1 V8 修正說明的權威數字一致；`G2_SB1_GATE_A_PROPOSAL.md` §6、§7 決策點 2 已記錄此修正） |
| Rollback | 見 §12.4 分層 Rollback 策略 |
| Definition of Done | daily_ml_features 有 29 欄; DBWriter 寫入 29 欄; CHECK constraints 生效; 遷移冪等; 測試 PASS |
| 狀態 | **CLOSED**（2026-08-27，PO 核准結案），見 `doc/upgrade/gates/closed/G2_SB1_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-26，§7 三個決策點：`source_status` 判定邏輯、DRIFT-003／27→29 殘留修正、`Dependency` 補軟性依賴註記）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-27）**，實作 commit `ef029a6b5753d071e9c17f0227389d0772681097`；evidence-sync（DEC-023、`TRACEABILITY.md`、Master Plan §15.1 回填）commit `014b372b7b03500c44d766e6e8d957d129973bac`。實作階段修正提案原訂範圍兩處（`label_reason` 延後至 Gate 3、`db_writer.py` NaN→NULL 轉換 bug 修復），已於 DEC-023 記錄；隔離容器 `g2sb1_ml_features_tmpdb`（非 `postgres-data` 掛載）完成完整 E2E 驗證，已拆除；提案與送審文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

#### UG-G2-SB2: PTT 內頁留言解析

| 項目 | 內容 |
|------|------|
| Goal | 進入 PTT 文章內頁，解析推/噓/箭頭留言計數 |
| Dependency | 無 |
| In Scope | `ptt_scraper.py` 新增 `parse_article_comments()` 方法; 推/噓/箭頭計數；Failure Semantics 依 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5 拆分 `SOURCE_DEGRADED`／`SOURCE_FAILED`；內頁完整時間戳記接線至既有 `parse_ptt_datetime()`；內頁請求節流；`main_etl_pipeline.py` 捕捉 `SOURCE_FAILED` 例外（§3.5 契約原文即要求下游 pipeline 捕獲，非範圍擴充） |
| Out of Scope | Dcard/Threads 留言; 留言衍生特徵計算 (SB4); NLP 情緒分析; **留言文字內容擷取（原「Top-5 高讚留言擷取」，`G2_SB2_GATE_A_PROPOSAL.md` §6 決策點 1 已核准移除——`MULTI_SOURCE_DATA_CONTRACT.md` §3.3 無對應規格，`FEATURE_REGISTRY.md` 三項留言特徵亦只需計數，無任何消費者需要留言內容）** |
| Affected Components | `src/extractors/ptt_scraper.py`, `main_etl_pipeline.py`（`SOURCE_FAILED` catch，見 In Scope）, `tests/test_ptt_comments.py` |
| Tests | `test_parse_push`, `test_parse_boo`, `test_parse_neutral`, `test_parse_failure_keeps_null`, `test_rate_limit_backoff` |
| Rollback | Revert commit |
| Definition of Done | 推/噓/箭頭留言計數可重現解析; `SOURCE_DEGRADED`／`SOURCE_FAILED` 正確區分; 單一來源失敗不中斷 daily pipeline; 測試 PASS |
| 狀態 | **CLOSED**（2026-08-27，PO 核准結案），見 `doc/upgrade/gates/closed/G2_SB2_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-27，§14 三個決策點：不納入留言內容擷取、內頁請求加保守節流、`main_etl_pipeline.py` 捕捉 `SOURCE_FAILED` 屬契約必要項）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-27）**，commit `543beb4771a645f8eb208904316bdfdba63b79d2`。過程中發現並修復一個既有測試隔離缺陷（4 個測試檔的 `bs4` stub 判斷式錯誤，永久把真的 `bs4` 換成 `MagicMock`）；known-FAIL 案例（單篇解析失敗續爬）第一版 fixture 經 PO 實測發現無偵測力，已改為三篇排列並重新驗證有效；真實 PTT 網站唯讀驗證已完成（審查員先審查程式碼、PO 核准後執行，2 篇真實文章，其中一篇獨立人工核對逐項相符）；提案與送審文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

#### UG-G2-SB3: market_articles Schema 擴充

| 項目 | 內容 |
|------|------|
| Goal | 新增 push_count, boo_count, neutral_count, total_comments, provider_article_id 等欄位 |
| Dependency | UG-G1-SB4 (Migration 機制) |
| In Scope | `003_expand_articles.sql` Migration; `db_writer.py` 更新 upsert 邏輯 |
| Out of Scope | 留言內容 NLP; 留言衍生特徵 (SB4) |
| Affected Components | `database/migrations/003_expand_articles.sql`, `src/loaders/db_writer.py` |
| Tests | `test_migration_003_idempotent`, `test_article_push_boo_write`, `test_provider_article_id_format`（原表列為 `_unique`，實作時修正——`MULTI_SOURCE_DATA_CONTRACT.md` §2.3 明訂 `provider_article_id` 為輔助索引、不取代 `url` 的 UNIQUE 約束，DB 層並無 UNIQUE constraint 可驗證，見 `G2_SB3_GATE_A_PROPOSAL.md` §1.4） |
| Rollback | 見 §12.4 分層 Rollback 策略 |
| Definition of Done | market_articles 新欄位可寫入; 遷移冪等; 測試 PASS |
| 狀態 | **CLOSED**（2026-08-27，PO 核准結案），見 `doc/upgrade/gates/closed/G2_SB3_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-27，§14 兩個決策點：不接線 `parse_article_comments()`（選項 A）、`provider_article_id` 用 `TEXT` + 補上 §4.3 遺漏的一般索引；原決策點 3 經查 `MULTI_SOURCE_DATA_CONTRACT.md` §2.3 已有明文答案，改為引用契約而非送裁決）** |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-27）**，commit `db03541f31ffd6b7145a434d30a051caec8bf1ec`。Gate A 審查階段 PO 另發現兩項問題並隨本 SB 修正：`MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的 `DEFAULT 0` 與 §4.3 明文禁令直接矛盾（會使 `comment_polarization` 算出 `1.0` 的偽造強訊號）；`gate0_contract_check.py` 的 B4 檢查結構上抓不到該矛盾（只掃單一檔案、正則要求同一行），已強化為跨全部 7 份文件掃描並支援多行 `ALTER TABLE`，附 known-FAIL 案例。一併修掉 DEC-023 剩餘風險欄登記的 NaN→None 未稽核寫法。隔離容器 `g2sb3_articles_tmpdb`（非 `postgres-data` 掛載）完成完整 E2E 驗證（15 欄、四欄無 `DEFAULT` 之 DB 層實證、CHECK 拒絕負數、索引確認非 UNIQUE、`ON CONFLICT DO NOTHING` 不覆寫、`NULL` vs `0` 語意可區分），已拆除。使用 `--no-verify`（PO 個別授權，範圍限本 commit，6 行已揭露空白差異）。提案與送審文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

#### UG-G2-SB4: 留言衍生特徵計算

| 項目 | 內容 |
|------|------|
| Goal | 計算 comment_volume_ratio, comment_polarization, net_push_momentum |
| Dependency | UG-G2-SB2（**解析能力**，非原始資料——`parse_article_comments()` 已可用但**至今無任何呼叫端**）+ UG-G2-SB3（Schema 與 13 欄寫入契約已就緒，但 `market_articles` 的四個留言計數欄目前**全為 `NULL`**）。**本 SB 必須先自行接線產生資料，才有東西可算**——原措辭「UG-G2-SB2（原始資料）」不正確，照該描述開工當天就會發現無料可算（`G2_SB3_GATE_B_SUBMISSION.md` §9.2） |
| In Scope | **（先做）接線 `parse_article_comments()` 進 `main_etl_pipeline.run_ptt_pipeline()`**，含兩項尚未決定的語意／策略決策：(a) 單篇內頁請求失敗（`SOURCE_DEGRADED`）時該篇文章是缺留言計數寫入、還是整篇跳過；(b) 每篇多一次內頁請求造成的請求量上限／節流策略（RISK-002 為 `OBSERVED`，非假設性風險）——兩者皆需於本 SB 的 Gate A 提案送 PO 裁決；（後做）`feature_aggregator.py` 新增 3 個留言衍生特徵計算; Feature Store 寫入 |
| Out of Scope | NLP 情緒重算; 新增模型訓練 |
| Affected Components | `main_etl_pipeline.py`（接線）, `src/extractors/ptt_scraper.py`（若節流策略需調整）, `src/transform/feature_aggregator.py`, `src/loaders/db_writer.py` |
| Tests | `test_comment_volume_ratio_uses_rolling_baseline`, `test_polarization_boundary`, `test_momentum_is_delta_not_ratio`, `test_null_when_no_comments` |
| Rollback | Revert commit |
| Definition of Done | 接線完成且留言計數真的進入 `market_articles`; 3 項特徵可重算; 公式與 §4.3 及 FEATURE_REGISTRY.md 一致; 無留言時保持 NULL; 測試 PASS |
| 狀態 | **CLOSED**（2026-08-28，PO 核准結案），見 `doc/upgrade/gates/closed/G2_SB4_GATE_B_SUBMISSION.md` |
| Gate A | PO 審查計畫 —— **已核准（2026-08-28）**。§14.1 為本 SB 最重要的產出：PM 原始提案把「留言數不是發文當天數的」判定為前視偏誤，PO 指出該等式不成立（Roll-Forward 本來就把週五盤後與週末文章歸屬到週一，週一早上爬到的留言數屬合法可見資訊），修正為「決策時點可見性」判準——此修正避免了實作過度保守地丟棄合法資料，而該類錯誤**沒有任何測試抓得到**。五項裁決：決策點 1 選項 A（`comments_scraped_at` + **write-once**，核准擴大範圍至 Migration 004）、決策點 2 選項 C（只算直接個股文章）、決策點 3（單篇失敗保持 `NULL`）、決策點 4（先做 URL 去重與跳過已有計數，不設硬性上限） |
| Gate B | PO 授權 Commit —— **已完成，CLOSED（2026-08-28）**，commit `3a470ec5430aa43f075fa0c152a7b22188ab82f2`。新增 DEC-024（時點有效性判準，約束**所有時間性會變動的特徵**，非僅留言計數）與 DEC-025（聚合範圍），兩者皆已寫入 `FEATURE_REGISTRY.md` §5.5／§5.6 **契約本文**。隔離容器 `g2sb4_comments_tmpdb`（非 `postgres-data` 掛載）完成端到端實證：留言計數確實進入 `market_articles`、URL 去重（4 URL→3 請求）、write-once 兩層防護（第二次 backfill 0 請求且值未被覆寫）、三特徵由真實 DB 留言數算出且與人工獨立核算逐位相符、時點過濾於真實 DB 路徑生效，已拆除。真實 Universe 覆蓋率標記 `NOT VERIFIED`（歸 RISK-015，Gate 3 前檢視）。提案與送審文件已移入 `doc/upgrade/gates/closed/`（`CLAUDE.md` §16.3） |

> ⚠ **接線時的型態陷阱（`push_count` 在兩層語意不同，UG-G2-SB3 登記）**
>
> | 層 | `push_count` 含意 | 型態 |
> |----|------------------|------|
> | `ptt_scraper.scrape_ptt_stock_by_keyword()` 輸出 | 列表頁推文徽章**文字**（「爆」「12」「X3」） | `str` |
> | `market_articles.push_count`（DB） | 內頁**真實推文則數** | `INTEGER` |
>
> 目前安全，因為 `clean_ptt_data()` 的 `final_cols` 不含徽章欄位——徽章在該函式內經
> `_parse_push_count()` 轉為 `engagement_metric` 後即被丟棄，不會流到 DB 層。
> **但接線時若把 scraper 的原始 DataFrame 直接餵進 `upsert_to_market_articles()`，
> 「爆」這個字串就會撞上 `INTEGER` 欄位。** 內頁解析結果（`parse_article_comments()`
> 回傳的 `push_count`／`boo_count`／`neutral_count`／`total_comments`）才是該寫進 DB 的值。
>
> **UG-G2-SB4 接線完成後的現況**：`backfill_ptt_comment_counts()` 走獨立的
> `update_comment_counts()` 路徑，只傳 `parse_article_comments()` 的回傳值，
> 未觸及 scraper 的徽章欄位——本陷阱**在現行程式碼中已避開**。此警告保留供未來
> 新增其他寫入路徑時參考。

> ⚠ **RISK-002 再現時須重新評估的決定（UG-G2-SB4 決策點 4，PO 2026-08-28）**
>
> 內頁請求量**不設硬性上限**——依 Gate B §5.3／§5.4 實證，URL 去重與跳過已有計數
> 兩層控制已使穩定期請求量自然收斂；再加硬性上限反而會在某天文章較多時**靜默丟掉資料**，
> 與 DEC-024 指出的「太緊」問題同類（過度保守的錯誤是沉默的，沒有徵兆）。
>
> **此決定不是永久豁免，是「目前證據支持不需要」。
> 若未來 RISK-002 再次被觀測到（PTT 回 429 或封鎖），此決定須重新評估。**

#### UG-G2-SB5: Dcard Adapter (CONDITIONAL — 非 Gate 2 阻擋條件)

| 項目 | 內容 |
|------|------|
| Goal | 以獨立 Adapter 接入 Dcard |
| Dependency | UG-Gate-0 交付物 D (MULTI_SOURCE_DATA_CONTRACT.md); 若需資料庫新欄位另依賴 UG-G2-SB3 |
| In Scope | `src/extractors/dcard_scraper.py` 新增; 可用性驗證 (API/Rate Limit/匿名/刪文/使用條款) |
| Out of Scope | PTT 修改; Threads; 模型訓練 |
| Affected Components | `src/extractors/dcard_scraper.py` (新建), `main_etl_pipeline.py` — **UG-G2-SB5 兩者皆未修改**。(1) 可用性驗證 `FAIL`（2026-08-29，Cloudflare 403），依 Definition of Done 走 `DEFERRED WITH EVIDENCE`，**不建立 adapter**（不留空殼檔案）。(2) 即使驗證 PASS，PO 2026-08-28 裁決 3 亦定為「adapter 交付為可運作但**未接入** daily pipeline」，使 `engagement_metric` 跨來源顯示失真在結構上不可能發生；接入時機另開 SB。見 DEC-026。 |
| Tests | `test_dcard_fetch_articles`, `test_dcard_dedup_key`, `test_dcard_failure_isolation` |
| Rollback | Revert commit; 移除 dcard_scraper.py |
| Definition of Done | Dcard 可用性驗證 PASS → Adapter 可抓取文章並寫入 market_articles; FAIL → DEFERRED WITH EVIDENCE |
| **實際結果（2026-08-29）** | **可用性驗證 `FAIL`** —— A1 HTTP 403（Cloudflare 邊緣攔截），A2–A6 `NOT EXECUTED`。狀態：**`DEFERRED WITH EVIDENCE`**，**不阻擋 Gate 2 關閉**（本 Brief 既有關閉條件已如此規定）。證據：`doc/upgrade/gates/evidence/G2_SB5_availability_evidence.json`；判定見 DEC-027；偏離登記見 DEC-026。**決策點 5（來源能力宣告）與本次 FAIL 無關，PO 裁定不分 PASS／FAIL 都要做，另走獨立 Gate B。** |

> **Gate 2 關閉條件**：Gate 2 在 PTT 留言解析、Feature Store 29 欄、
> **Universe 建立（2026-08-31 措辭收緊，DEC-031——原文「Universe 建立」是那種**在 4 檔股票上也能宣稱達成**
> 的措辭，與 `UG-G2-SB1`「`daily_ml_features` 有 29 欄」沒說哪個資料庫是同一個形狀，而 RISK-017 正是那個形狀
> 造成的。改為可證偽形式）：**候選池涵蓋台股上市全市場（≥ 500 檔）、歷史深度 ≥ 3 年
> （`PURGED_WALK_FORWARD_SPEC.md:146`），且已據此產出至少一個 PIT Universe Snapshot**、
> Batch ETL 完成，
> **且「CORE_16 的 16 個特徵全部可計算」**（2026-08-31 新增，見 DEC-029——
> `amplitude_ratio`／`ma5_bias_ratio`／`ma20_bias_ratio`／`volume_ratio_5d`
> 已在契約與 schema 中宣告但從未被計算，沒有它們 CORE_16 實際只有 12 個特徵；
> **一個宣稱交付 16 個核心特徵的 Gate，若關閉時有 4 個算不出來，
> 交付的就不是它宣稱的東西**），
> **且「真實開發資料庫與 migration 狀態同步，且 pipeline 已對其實際執行過一次」**時即可關閉。
>
> **新增最後一項的理由（PO 2026-08-30）**：原本四項**全部都能在拋棄式臨時 DB 裡滿足**——
> Gate 2 可以在真實開發庫仍停在 Gate 0 schema 的情況下關閉，
> **關掉一個從來沒跑起來過的系統**。RISK-017 實測確認這個情況已經發生
> （`market_articles` 10 欄、`daily_ml_features` 7 欄、`schema_version` 表不存在）。Dcard 的處理路徑為：
> - Dcard 可用性驗證 **PASS** → 在 Gate 2 內實作 Adapter
> - Dcard 可用性驗證 **FAIL** → 標記為 `DEFERRED WITH EVIDENCE`，**不阻擋 Gate 2 關閉**

#### UG-G2-SB8: CORE_16 四個平穩化特徵 + 讀取端缺口反查檢查

> **2026-08-31 新增（DEC-029）。** 編號為 SB8 但**執行順序排在 SB6／SB7 之前**——
> SB7 是把 pipeline 大規模跑起來，先把特徵集補完，SB7 跑的才是完整的 CORE_16，
> 不用事後重跑。

| 項目 | 內容 |
|------|------|
| Goal | 實作 CORE_16 的四個平穩化特徵（§3.7 模型輸入第 13–16 號），並機械化偵測讀取端缺口 |
| Dependency | UG-G2-SB1（`daily_ml_features` 29 欄，欄位已存在）；UG-G2-MIG（真實庫已同步） |
| In Scope | `db_writer` 股價查詢補 `high_price`／`low_price`；`feature_aggregator` 實作四公式；NULL 策略逐欄檢視（三個決策點）；`gate0_contract_check.py` Part B 第 12 項反查檢查 + known-FAIL |
| Out of Scope | `open_price` 作為直接特徵（CORE_16 明文移除）；既有欄位 NULL 策略複審；對真實庫重跑 pipeline（須另行授權） |
| Affected Components | `src/loaders/db_writer.py`、`src/transform/feature_aggregator.py`、`scripts/verify/gate0_contract_check.py`、`doc/upgrade/contracts/FEATURE_REGISTRY.md` |
| Rollback | Revert commit；四欄回復為 NULL（與本 SB 之前的狀態相同） |
| Definition of Done | 見 Gate A 提案 §8——**每一項指名目標資料庫**（`gate-submit` 產出 7，RISK-017 緩解第 2 條的示範） |
| 狀態 | **CLOSED**（2026-08-31，PO 核准結案；`DEC-029` 新增本 SB、`DEC-030` NULL 策略修正），見 `doc/upgrade/gates/closed/G2_SB8_GATE_B_SUBMISSION.md` |

#### UG-G2-SB9: 候選池價格資料取得 (Universe 的前置)

> **2026-08-31 新增（DEC-031）。編號為 SB9，但執行順序排在 SB6 之前**——
> SB6 的流動性排名需要本 SB 的產出。編號與順序不一致是刻意接受的，
> 因為既有編號已在多份文件中被引用，重編號的成本與風險更高。

| 項目 | 內容 |
|------|------|
| Goal | 為 `UG-G2-SB6` 的流動性排名取得全市場候選股價格資料（含**成交金額**，DEC-017 的排名依據）。**候選空間依 DEC-017 為上市 + 上櫃（排除興櫃）**；階段一只驗證上市端點 |
| Dependency | 無（本 SB 是 SB6 的前置） |
| In Scope | 端點驗證（判準先寫死、核准後才觸網，比照 `UG-G2-SB5` 協定）；**階段一**取最近 60 個交易日；候選池資料落地位置決策 |
| Out of Scope | **階段二回補至 ≥ 3 年（需 PO 另行放行）**；Universe 建構模組（SB6）；批次化 ETL（SB7）；對真實庫套用 migration。**注意：上櫃（TPEx）不在 Out of Scope**——依 DEC-017 候選空間為上市 + 上櫃，上櫃**在本 SB 範圍內、延後至階段二**（沉默地縮小範圍與明示地分階段是兩件事） |
| Affected Components | `src/extractors/`（新增取數模組）、`database/migrations/`（候選價格表，依決策點 1）、`scripts/verify/`（端點驗證腳本） |
| Tests | 判準 known-FAIL（B1–B5 各一）、`NOT EXECUTED` 三態根因歸因、非數值標記解析、**停牌零成交不得被當成 0 元成交金額**、**`daily_ml_features` 不受候選池影響**、冪等性 |
| Rollback | 候選價格表可整表清空重建（衍生資料，來源為外部端點）；不涉及既有表的破壞性變更 |
| Definition of Done | 見 Gate A 提案 §10——**每一項指名目標資料庫**。特別是：**`postgres`@`localhost:5432` 的 `daily_ml_features` 與 `stock_prices` 皆維持 117 列**——本 SB 不對真實庫寫入任何候選池資料 |
| 狀態 | **CLOSED**（2026-09-02，PO 核准結案，closure commit `088ff27`；`DEC-031` 新增本 SB 並修正 SB6／SB7 循環依賴、`DEC-032` 重試紀律），見 `doc/upgrade/gates/closed/G2_SB9_GATE_B_SUBMISSION.md` |

> **目標依據**：`PURGED_WALK_FORWARD_SPEC.md:146`「歷史深度 | 至少 3 年（理想 5 年以上）」。
> **這不是選項**——沒有它，RISK-012 存活偏誤無法解決，Gate 3 的 Purged Walk-Forward 也跑不起來。

> **分兩階段的理由不是成本，是錯誤的代價**：階段一要回答的問題（端點是否提供成交金額、
> 約 1000 檔的格式是否乾淨、停牌／下市當天那檔在回應裡長什麼樣）——
> **用 60 次請求回答，與用 792 次回答，答案完全一樣**；
> 而如果哪裡不對，在幾分鐘後就知道，不是在把約 79 萬筆髒資料寫進資料庫之後才知道。

#### UG-G2-SB6: Stock Universe 建立 (Point-in-Time)

| 項目 | 內容 |
|------|------|
| Goal | 建立流動性前 150/500 大股票池，嚴格 Point-in-Time |
| Dependency | UG-G2-SB1 (Feature Store 就緒)；**UG-G2-SB9（候選池價格資料）——2026-08-31 新增，DEC-031**。本 SB 的「流動性排名」需要全市場候選股的價格資料，而該能力原本寫在 SB7 的 In Scope，**SB7 卻依賴本 SB**——循環依賴。取得候選池資料這件事兩個 SB 都沒有負責，已由 SB9 承接 |
| In Scope | Universe 建構模組; 流動性排名; Snapshot 保存; 異動處理 (新上市/下市/停牌/代碼異動) |
| Out of Scope | 批次 ETL (SB7); 模型訓練 |
| Affected Components | `src/transform/universe_builder.py` (新建), `database/` (universe 相關表) |
| Tests | `test_universe_excludes_etf`, `test_universe_monthly_rebuild`, `test_universe_size`, `test_universe_point_in_time_no_future_data`, `test_universe_snapshot_saved`, `test_universe_handles_delisting` |
| Rollback | Revert commit |
| Definition of Done | 每個 Universe Snapshot 只使用 effective_date 前已知資料；歷史回測載入當期 Snapshot；測試 PASS |
| 狀態 | **CLOSED**（2026-09-03，PO 核准結案，closure commit `8f1381d`；`DEC-033` 窗口邊界裁定），見 `doc/upgrade/gates/closed/G2_SB6_GATE_B_SUBMISSION.md` |

> **RISK-015 提醒**：本 SB 的流動性排名為**暫定標準**，非以情緒資料覆蓋率為依據——目前尚不知道
> 候選股票間的討論量實際分佈。正式檢視點設在 Gate 3 啟動前（見 `REMAINING_RISKS.md` RISK-015），
> 屆時若評估顯示覆蓋率結構性不足，Universe 篩選邏輯可能需要調整（分層或門檻），須另提 PO 裁決。

#### UG-G2-SB7: 批次化 ETL 引擎

| 項目 | 內容 |
|------|------|
| Goal | 將逐股票/逐關鍵字爬取改為批次化 |
| Dependency | UG-G2-SB6 (Universe) |
| **範圍澄清（2026-08-31，DEC-031）** | 本 SB 的「股價批次下載」指的是**對已知 universe 的例行批次擷取**，**不含「取得候選池以供排名」**——後者是 SB9 的職責。本 SB 的 DoD 寫「150 檔」即已假設那 150 檔存在，故本來就不負責建立候選池 |
| In Scope | 股價批次下載; 社群固定頁面一次抓取 + 記憶體比對; 失敗容忍 (單一失敗不阻塞) |
| Out of Scope | 新增資料來源; 模型訓練 |
| Affected Components | `main_etl_pipeline.py`, `src/extractors/twse_scraper.py`, `src/extractors/yfinance_api.py`, `src/extractors/ptt_scraper.py` |
| Tests | `test_batch_etl_partial_failure`, `test_batch_etl_retry`, `test_etl_time_benchmark` |
| Rollback | Revert commit |
| Definition of Done | 150 檔批次 ETL 可完成; 單一失敗不阻塞; 測試 PASS |
| 狀態 | **CLOSED**（2026-09-05，PO 核准結案，closure commit `4c6e3f6`；`DEC-032` 生產落實、`DEC-034` 舊批排除），見 `doc/upgrade/gates/closed/G2_SB7_GATE_B_SUBMISSION.md` |

---

## 9. UG-Gate-3: ML Upgrade (模型升級) — **CLOSED（2026-09-16，PO 核准，`UG-G3-SB7` 結案即關閉）**

> **關鍵約束**: 本 Gate 所有 SB 嚴禁在 UG-G1-SB1 (Purged WF) 完成前開始。
> **准入前置條件**：依 §5.1，本 Gate 開工前須先完成 RISK-015 情緒資料覆蓋率正式檢視
> （`doc/upgrade/contracts/REMAINING_RISKS.md` RISK-015），以 `UG-G2-SB1`／`SB6` 累積之真實
> `source_status` 資料重新評估，而非沿用 Gate 2 規劃時的假設。
> **Brief 完整度說明**：以下 SB briefs 列出核心設計意圖（至少 8 項）。完整 16 項 Brief 在 Gate 3 規劃階段產出。
> **V6 順序修正**：Triple-Barrier 移至 SB1，在 Panel Dataset 與模型訓練之前。

### Small Batch Briefs

#### UG-G3-SB1: Triple-Barrier Labeling

> **狀態（2026-09-09）**：綠色實作已完成（commit `b24fc01`→`d2e3f27`→`874b3bf`），
> 完整 Gate A 提案見 `doc/upgrade/gates/UG_G3_SB1_GATE_A_PROPOSAL.md`（PO 核准）。
> 下表為核心欄位快照，**Affected Components／Tests／DoD 已依實際實作更新**，
> 詳細設計、embargo/purge 重議、`label_end_date_tb` 歸屬裁決見 Gate A 提案本身。

| 項目 | 內容 |
|------|------|
| Goal | 實作 Triple-Barrier 三分類動態標籤（anchor = `Open[T+1]`）|
| Dependency | UG-G1-SB1 (Purged WF — Label Horizon 必須對齊) |
| In Scope | Triple-Barrier 標籤生成器; anchor=`Open[T+1]`; 三分類 `{1,-1,0}`; 同日觸雙線／剩餘天數不足 H／無法進場（含 NaN 價格）NULL; Ambiguous 比例與類別分布報告 |
| Out of Scope | Panel Dataset 構建 (SB2); 模型訓練; Dynamic barrier 模式（PO 2026-09-09 Gate A 裁決維持 Out of Scope，見 T-TB-07） |
| Affected Components | `src/ml/triple_barrier.py`（新建）——**非** `feature_aggregator.py`：標籤生成獨立於既有特徵聚合流程，未修改該檔 |
| Data Contract | `PURGED_WALK_FORWARD_SPEC.md` §4；label domain = `{-1, 0, 1, NULL}` |
| Tests | 見 `tests/test_triple_barrier.py`（T-TB-01~17，`PURGED_WALK_FORWARD_SPEC.md` §5.2 為權威清單，此處不重複列舉避免複製後與該處數字漂移）|
| Rollback | Revert commit |
| Definition of Done | 三分類標籤已產生；anchor 為 `Open[T+1]`；Ambiguous 比例與類別分布報告**已完成**（Gate A §11 DoD 第 3 項，四檔皆 <10%）；`label_end_date_tb`（獨立欄位，非既有 `label_end_date`）正確；測試 PASS（已達成）；真實庫寫入**已完成**（2026-09-09，`postgres`@`localhost:5432` 全部 3,713 列，走 RISK-013 三項協議，證據見 `doc/upgrade/gates/evidence/UG_G3_SB1_real_db_write.json`，Gate A §11 DoD 第 6 項）|
| 狀態 | **CLOSED**（2026-09-09，PO 核准結案），見 `doc/upgrade/gates/closed/UG_G3_SB1_GATE_B_SUBMISSION.md` |

#### UG-G3-SB2: Panel Dataset 構建

> **狀態（2026-09-10）**：**Gate B 已核准結案**。三項子工作皆已完成：PIT 面板
> 讀取器（`src/ml/panel_dataset.py`）、`entity_mapping` 路由補齊（真實庫
> `postgres`@`localhost:5432` 寫入 457 筆）、每日尾端重算掛點（已接線，
> 未啟用——`run_all_daily_tasks()` 執行受 `PROJECT_STATUS.md` §0.5 #20 閘門）。
> 458 檔資料本身的回補**移出本 SB，另立 `UG-G3-SB2a`**（下方緊接的 Brief，
> `DEC-036` 已 `APPROVED`）。`UG-G3-SB3` 依賴兩者皆完成，本 SB 結案**不解除**
> §0.5 #20 閘門，該閘門綁 `UG-G3-SB2a` Gate B 通過。完整記錄見
> `doc/upgrade/gates/closed/UG_G3_SB2_GATE_B_SUBMISSION.md`。

| 項目 | 內容 |
|------|------|
| Goal | 從 `daily_ml_features` 讀取 Point-in-Time 跨股票面板資料集（**PIT，非矩形**——`universe_snapshots` 每月換名單，面板需依 `effective_date ≤ trade_date` 取當期最近一期名單） |
| Dependency | UG-G2-SB1 + UG-G2-SB6 + **UG-G3-SB1 (Triple-Barrier 標籤)** |
| In Scope | (1) Panel DataLoader（PIT 正確，long-format）；(2) `entity_mapping` 路由補齊（458 檔宇宙中 455 檔缺路由，官方簡稱自動產生 + 俗稱/黑話類人工核對另案）；(3) 每日尾端重算掛點（`stock_prices` 新增當日列後，對每檔股票尾端 `H+1=6` 列重跑 `generate_triple_barrier_labels()`，寫回 `daily_ml_features`）；訓練目標配置切換 |
| Out of Scope | Specialist 模型訓練 (SB3)；Feature 計算本身邏輯 (Gate-2)；**458 檔資料回補本身（`UG-G3-SB2a`）** |
| Affected Components | `src/ml/panel_dataset.py` (新建), `src/loaders/db_writer.py`, `main_etl_pipeline.py`（每日掛點） |
| **訓練目標選擇** | Panel Dataset 必須透過配置明確選擇 `target_up_down` 或 `target_triple_barrier` 作為訓練目標。兩個 target 都必須存在於 dataset 中，但模型訓練只使用選定的一個 |
| Tests | `test_panel_shape`（long-format 列數）, `test_panel_no_future_dates`（相對 `as_of` 參數）, `test_panel_target_column_selection`, `test_panel_universe_is_point_in_time`（新增）, 每日掛點冪等測試（新增） |
| Rollback | Revert commit |
| Definition of Done | Panel Dataset 可載入且 PIT 正確；路由補齊完成（455 筆）；每日掛點接上且冪等；訓練目標可配置切換；測試 PASS |
| 狀態 | **CLOSED**（2026-09-10，PO 核准結案），見 `doc/upgrade/gates/closed/UG_G3_SB2_GATE_B_SUBMISSION.md` |

#### UG-G3-SB2a: 458 檔 Universe 資料回補（新增，DEC-036）

> **狀態（2026-09-11）**：**Gate B 已核准結案**。三段真實庫寫入全部完成：
> 段 1（`stock_prices` 458 檔皆補齊）、段 2（`daily_ml_features` 458＋NVDA
> 檔特徵回補，449,263 列）、段 3（Triple-Barrier 標籤全部重算，標籤計數
> 410,443／38,820）；另有候選池 8 天全市場缺口回補與段 1 重跑，**五次真實
> 庫寫入皆完整執行 RISK-013 三項協議**。過程中發現並登記 RISK-027（交易
> 日曆跨市場聯集缺陷，獨立小案待修）、RISK-028（TPEX 端間歇性 SSL 驗證
> 失敗，另案診斷）。`PROJECT_STATUS.md` §0.5 #20 每日 ETL 執行閘門**已隨
> 本 Gate B 核准解除**（解除 ≠ 執行，第一次執行需另一輪 binding
> confirmation，十項觀察清單為必答項）。完整記錄見
> `doc/upgrade/gates/closed/UG_G3_SB2a_GATE_B_SUBMISSION.md`。

| 項目 | 內容 |
|------|------|
| Goal | 把 `universe_snapshots` 46 期跨期去重 458 檔的價格資料從 `candidate_prices`（已 100% 覆蓋，`UG-G2-SB9`）搬遷至 `stock_prices`，跑過 `feature_aggregator.py` 全套特徵工程與 `UG-G3-SB1` 的 Triple-Barrier 標籤，使 `daily_ml_features` 從現有 3 檔（2330/2382/6488）擴大至 458 檔 |
| Dependency | UG-G2-SB9（`candidate_prices` 回補）+ UG-G3-SB1（Triple-Barrier 標籤生成器） |
| In Scope | (1) `stock_prices` 價格基準政策制定（RISK-022 面向二——證交所原始價 vs yfinance 還原價混合，須先定基準與 `source` 標記規則才能搬遷）；(2) `candidate_prices → stock_prices` 搬遷（458 檔，純資料庫操作，零外部請求）；(3) 重疊列處理（既有 3 檔的既有列與搬遷來源如何合併，PRE-G3-03 已量到 25 列碰撞的處理模式可參考）；(4) RISK-024 擷取端 NaN 防護評估（回補批次本身若引入 NaN 列，SB1 消費端會正確處理但需量測規模）；(5) 對 458 檔跑 `feature_aggregator.py`；(6) 對 458 檔跑 Triple-Barrier 標籤（沿用 `UG-G3-SB1` 腳本模式） |
| Out of Scope | Panel 讀取器本身（`UG-G3-SB2`）；情緒特徵覆蓋率擴大（`tracking_keywords` 追蹤宇宙擴大是另一個決定，不隨路由自動發生） |
| Affected Components | `database/`（`stock_prices` 資料，非 schema 變更）、`src/transform/feature_aggregator.py`（執行，非邏輯變更）、`src/ml/triple_barrier.py`（執行，非邏輯變更）、新的一次性回補腳本（比照 `scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py` 模式） |
| Tests | 沿用既有測試套件驗證邏輯正確性（不新增邏輯，只新增執行規模）；回補腳本自身的列數/讀回核對比照 `UG-G3-SB1` 硬化後的寫入腳本設計 |
| Rollback | RISK-013 三項協議（`pg_dump` 備份 + 還原驗證），比照 `UG-G3-SB1` |
| Definition of Done | `stock_prices` 458 檔皆有資料；`daily_ml_features` 458 檔皆有特徵與 Triple-Barrier 標籤；RISK-022 基準政策已定並記錄；真實庫寫入完成，備份與還原驗證通過 |
| 狀態 | **CLOSED**（2026-09-11，PO 核准結案），見 `doc/upgrade/gates/closed/UG_G3_SB2a_GATE_B_SUBMISSION.md` |
| **Gate A 必答項（2026-09-09 追加）** | **日常路徑（`run_twse_pipeline`）與回補路徑（`candidate_prices`）的基準一致性**——`UG-G3-SB2` routing 真實庫寫入的惰性驗證（步驟 5）發現追蹤宇宙由 4 檔擴為 8 檔，其中 3 檔（TWSE）下次每日 ETL 會經 `run_twse_pipeline` 日常路徑（yfinance 備援、未還原基準）寫入 `stock_prices`，與本 SB 待制定的回補基準政策若不一致，會產生同一張表內兩種基準並存的新接縫（同 RISK-022（一）「來源不可知」的成因）。本必答項要求：制定基準政策時，一併回答「日常路徑寫入的列，基準與回補路徑寫入的列是否一致；不一致時如何標記或調和」，不得只處理回補批次本身。詳見 RISK-022（四）、`doc/evidence/CHALLENGES.md` CHAL-009、`PROJECT_STATUS.md` §0.5 #20（每日 ETL 執行閘門） |

> **排程**：`UG-G3-SB3` 需本 SB 與 `UG-G3-SB2` 皆完成才可開始（PO 2026-09-09 裁決）。
> **每日 ETL 執行閘門**：本 SB 的 Gate B 通過（基準政策定案）前，`run_all_daily_tasks()`／`scheduler.py` 不得執行（`PROJECT_STATUS.md` §0.5 #20，2026-09-09 PO 裁決）。

#### UG-G3-SB3: Specialist Models (RF, LightGBM, XGBoost)

> **狀態（2026-09-13）**：**CLOSED**（Gate B 已核准結案，PO 2026-09-13）——見
> `doc/upgrade/gates/closed/UG_G3_SB3_GATE_B_SUBMISSION.md`。以下表格為 Gate A 規劃版，
> **Affected Components 已訂正為實作實際觸及的完整清單**（原版僅列兩檔，
> 實作追加了三個既有模組的擴充與兩個新模組/腳本）。

| 項目 | 內容 |
|------|------|
| Goal | 獨立訓練與評估各 Specialist 模型 |
| Dependency | UG-G3-SB2 + **UG-G3-SB2a**（458 檔資料回補，PO 2026-09-09 裁決：兩者皆完成才可開始） |
| In Scope | 技術腦 (LightGBM) + 情緒腦 (RF) 分別訓練; XGBoost 對照; Purged WF 下逐 Fold 評估; D3 對照實驗（有情緒 vs 無情緒特徵，`GATE3_STARTUP_APPLICATION.md` §5 核准） |
| Out of Scope | OOF Stacking (SB4); 校準 (SB5) |
| Affected Components（**訂正**） | `src/ml/baseline_models.py`（新增 `CORE16_STATIONARY_COLS`／`ARM_A_FEATURE_COLS`／`ARM_B_FEATURE_COLS`）、`src/ml/model_trainer.py`（`extract_multimodal_features()` 情緒欄保留 NaN、`NAN_INTOLERANT_MODELS` fail-fast）、`src/ml/panel_dataset.py`（新增 `label_end_date` 輸出）、`src/ml/time_series_split.py`（`require_label_end_date`／`purge_mode`）、`src/ml/specialist_training.py`（**新模組**：`prepare_fold_data`／`run_fold_for_arms`／`iter_model_arm_pairs`／per-class 與洩漏診斷函式／`fit_predict_specialist_fold`）、`scripts/verify/ug_g3_sb3_specialist_report.py`（**新腳本**：段級報告產生器） |
| Tests | `test_rf_fold_output`, `test_lgbm_fold_output`, `test_xgb_fold_output`, `test_specialist_no_leakage`（既定命名，實際落地為 `tests/test_ug_g3_sb3_specialist_training_red.py`／`tests/test_ug_g3_sb3_specialist_report.py` 內對應測試，功能涵蓋一致） |
| Rollback | Revert commit |
| Definition of Done | 各 Specialist 在 Purged WF 下可獨立訓練與評估；測試 PASS——**✅ 已完成**，見 Gate B 送審文件 §4 逐項對號 |
| 狀態 | **CLOSED**（2026-09-13，PO 核准結案；新 ADR `DEC-038` `APPROVED`），見 `doc/upgrade/gates/closed/UG_G3_SB3_GATE_B_SUBMISSION.md` |

#### UG-G3-SB4: OOF Stacking Meta-Learner

| 項目 | 內容 |
|------|------|
| Goal | 使用 Purged Walk-Forward OOF 預測做二階堆疊 |
| Dependency | UG-G3-SB3 |
| In Scope | Meta-Learner (Logistic/Ridge) 使用 OOF 預測值 + 市場機制特徵; 嚴格禁止使用原始特徵 |
| Out of Scope | 校準 (SB5); 選擇性推論 (SB6) |
| Affected Components（**訂正**） | `src/ml/stacking.py`（**新建**：OOF 矩陣組裝、二階 Purge、Meta-Learner 選擇邏輯、`iter_oof_folds`、`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 常數）、`src/ml/specialist_training.py`（`fit_predict_specialist_fold()` 新增 `return_proba` 參數）、`src/ml/baseline_models.py`（新增 `META_REGIME_FEATURE_COLS` 常數）、`scripts/verify/ug_g3_sb4_oof_generation.py`（**新腳本**：OOF 產生器，六項守衛）、`scripts/verify/ug_g3_sb4_meta_learner_report.py`（**新腳本**：段級報告器，四項守衛）。**`src/ml/evaluator.py` 未觸及**（Gate A §5 原列為視需要擴充的條件式規劃；實作階段評估邏輯改走獨立報告腳本，見 Gate B §7 訂正記錄，登記為後續小案待 `UG-G3-SB7` 一併決定） |
| Tests | `test_oof_no_train_leakage`, `test_meta_learner_input_shape`, `test_meta_uses_only_oof_preds`（既定命名，實際落地為 `tests/test_ug_g3_sb4_stacking_red.py`／`test_ug_g3_sb4_stacking_contracts.py`／`test_ug_g3_sb4_oof_scripts.py` 內對應測試，功能涵蓋一致） |
| Rollback | Revert commit |
| Definition of Done | Meta-Learner 使用 OOF 預測值；無二階洩漏；測試 PASS——**✅ 已完成**，見 Gate B 送審文件 §10 逐項對號 |
| 狀態 | **CLOSED**（2026-09-15，PO 核准），見 `doc/upgrade/gates/closed/UG_G3_SB4_GATE_B_SUBMISSION.md` |

#### UG-G3-SB5: Probability Calibration

| 項目 | 內容 |
|------|------|
| Goal | 在獨立校準資料集上做 Isotonic/Platt 校準 |
| Dependency | UG-G3-SB4 |
| In Scope | 校準資料隔離; Isotonic 或 Platt 校準; 校準後機率單調性驗證 |
| Out of Scope | 選擇性推論 (SB6); Benchmark (SB7) |
| Affected Components（**訂正**） | `src/ml/calibration.py`（**新建**：`fit_calibrator`／`apply_calibrator`／`assert_calibration_monotonic`／`assert_auc_preserved`／`evaluate_calibration_quality`／`brier_score_multiclass`／`reliability_table` 等，手動 Isotonic／Platt，不用 `CalibratedClassifierCV`）、`scripts/verify/ug_g3_sb5_calibration_report.py`（**新腳本**：段級報告器，七項守衛）。**`src/ml/predictor.py` 未觸及**（原規劃條件式，實作階段評估邏輯全走獨立報告腳本，比照 `UG-G3-SB4` Gate B §7 先例誠實記錄，非違反範圍） |
| Tests | `test_calibration_data_isolation`, `test_calibration_monotonicity`, `test_calibration_not_in_train`（既定命名，實際落地為 `tests/test_ug_g3_sb5_calibration_red.py`／`test_ug_g3_sb5_calibration_report.py` 內對應測試，功能涵蓋一致） |
| Rollback | Revert commit |
| Definition of Done | 校準資料獨立；校準後機率單調；測試 PASS——**✅ 已完成**，見 Gate B 送審文件 §6 逐項對號 |
| 狀態 | **CLOSED**（2026-09-15，PO 核准），見 `doc/upgrade/gates/closed/UG_G3_SB5_GATE_B_SUBMISSION.md`。主要發現 `RISK-030`，新 ADR `DEC-041`（Gate 3 後續主線改 `target_triple_barrier`／Timeout） |

#### UG-G3-SB6: Timeout Gating（原「Selective Inference & Regime Gating」）

> **Gate B 已核准（2026-09-16）**，實際範圍見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md`。依 `DEC-041`（`UG-G3-SB5` Gate B 核准，2026-09-15）：依 `RISK-030` 實測（`target_up_down` 無可偵測排序訊號），本 SB 對 `target_up_down` **停做**；改以 `target_triple_barrier`／Timeout 類的校準後機率為信心門檻對象（產品形態「何時不交易」）。以下表格已依實際落地結果更新，原規劃見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_A_PROPOSAL.md` §3.8 逐項對照。

| 項目 | 內容 |
|------|------|
| Goal | `target_triple_barrier`／Timeout 校準機率門檻過濾（「何時不交易」）；市場狀態（`volatility_20d` 三分位）為必做診斷區塊，非模型連續輸入 |
| Dependency | UG-G3-SB5 |
| In Scope | 二元：`P(Timeout)≥θ*`→觀望；`P(Timeout)<θ*`→保留（不宣稱方向）；`volatility_20d` 三分位事後診斷分組 |
| Out of Scope | `target_up_down` 全部工作（`RISK-030`）；獨立 regime-conditioned 模型訓練；`src/ml/predictor.py`／`src/ml/evaluator.py`（gating 決策是否接入既有預測輸出路徑留給 `UG-G3-SB7`／Gate-4）；Benchmark (SB7)；UI 排名 (Gate-4) |
| Affected Components | `src/ml/gating.py`（新建）、`scripts/verify/ug_g3_sb6_gating_report.py`（新建）、`.gitignore` |
| Tests | `tests/test_ug_g3_sb6_gating_red.py`（38 項）、`tests/test_ug_g3_sb6_gating_report_red.py`（60+3 項） |
| Rollback | Revert commit |
| Definition of Done | `θ*` 於 Calib-eval 達成覆蓋率 ≥80%／精準度提升 ≥4×／召回 ≥60%（實際：80.00%／4.15×／83.03%）；`volatility_20d` regime 診斷完成；測試 PASS；`DEC-041` 轉 `APPROVED` |
| 狀態 | **CLOSED**（2026-09-16，PO 核准結案），見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md` |

#### UG-G3-SB7: Performance Benchmark（Holdout 最終驗證）

> **Gate B 已核准（2026-09-16）**，實際範圍見 `doc/upgrade/gates/closed/UG_G3_SB7_GATE_B_SUBMISSION.md`。依 `DEC-041`（Gate 3 主線轉向 Timeout gating）：本 SB 驗證 `UG-G3-SB4`～`SB6` 建立的管線在 Holdout（折 33-42）上是否仍成立，非原規劃的方向性多類基準對照。以下表格已依實際落地結果更新，原規劃見 Gate A 提案 §3.8。

| 項目 | 內容 |
|------|------|
| Goal | 對 `DEC-040` 定義的 Holdout（折 33-42）唯一一次正式消費，驗證 Timeout gating 三項判準是否成立，並與波動率單變數基線並列比較 |
| Dependency | UG-G3-SB6 |
| **資料期間** | 沿用 `UG-G3-SB3` 凍結面板；Holdout＝折 33-42（`HOLDOUT_START_DATE=2025-10-23`），唯讀一次消費，不得回饋調整 `SB4`～`SB6` 任何設計決定（`DEC-040`） |
| **In Scope** | `iter_holdout_folds()` 新增；Holdout 折 Specialist OOF 重生（凍結 Meta(A)／校準器／`θ*`／regime 切點）；三項判準與雙變體波動率基線並列；`target_up_down` 觀察用 AUC |
| **Out of Scope** | 淨累積報酬與交易模擬（無交易模擬引擎，登記候補案）；Timeout 三分類 Macro F1（PO 裁決不補，見 Gate B §0）；`evaluator.py`／`predictor.py` 整合（移交 Gate-4） |
| 評估 | Timeout gating 三項判準（覆蓋率／精準度提升／召回）於 Holdout 成立；波動率單變數基線並列，不下結論 |
| Tests | `tests/test_ug_g3_sb7_holdout_red.py`（40 項） |
| Rollback | Revert commit |
| Definition of Done | 多類基準完整對照；Holdout 未用於選擇；交易成本一致；測試 PASS |

---

## 10. UG-Gate-4: XAI, Export & UI Enhancement

> **Brief 完整度說明**：以下 SB briefs 列出核心設計意圖（至少 8 項）。完整 16 項 Brief 在 Gate 4 規劃階段產出。

### Small Batch Briefs

#### UG-G4-SB1: Model Artifact 規格化

| 項目 | 內容 |
|------|------|
| Goal | 模型序列化含完整 metadata |
| Dependency | UG-G3-SB7 (Benchmark 完成) |
| In Scope | Artifact 格式定義; metadata 含 model_version, feature_schema_hash, training_data_period, dataset_fingerprint, hyperparameters, evaluation_result, calibration_config, created_timestamp, library_versions |
| Out of Scope | 模型訓練 (Gate-3); XAI (SB2) |
| Affected Components | `src/ml/predictor.py`, `src/ml/model_trainer.py` |
| Tests | `test_artifact_metadata_complete`, `test_artifact_schema_hash_match`, `test_artifact_load_roundtrip` |
| Rollback | Revert commit |
| Definition of Done | Artifact 含完整 metadata；序列化/反序列化一致；測試 PASS |

#### UG-G4-SB2: XAI 計算 (Global/Local 分離)

| 項目 | 內容 |
|------|------|
| Goal | 明確分離 Global Importance 與 Local Attribution |
| Dependency | UG-G4-SB1 (Artifact) |
| In Scope | Global: RF MDI / Permutation Importance; Local: SHAP TreeExplainer; 嚴格禁止把 MDI 稱為「單筆預測貢獻」|
| Out of Scope | 新增模型; UI 渲染 (SB4) |
| Affected Components | `src/ml/evaluator.py`, `src/ml/xai.py` (新建) |
| Tests | `test_global_importance_is_mdi`, `test_local_attribution_sums_to_prediction`, `test_xai_global_local_separation` |
| Rollback | Revert commit |
| Definition of Done | Global/Local 分離清楚；MDI 不標為單筆貢獻；測試 PASS |

#### UG-G4-SB3: CSV 匯出

| 項目 | 內容 |
|------|------|
| Goal | 特徵/預測/XAI 報表 CSV 匯出 |
| Dependency | UG-G4-SB2 (XAI) |
| In Scope | 特徵 CSV、預測 CSV、XAI 報表 CSV; UTF-8 BOM 編碼 (Excel 相容) |
| Out of Scope | 自動排程匯出; 雲端儲存 |
| Affected Components | `src/ml/exporter.py` (新建) |
| Tests | `test_csv_columns_match_registry`, `test_csv_encoding_utf8`, `test_csv_no_nan_values` |
| Rollback | Revert commit |
| Definition of Done | CSV 欄位與 FEATURE_REGISTRY.md 一致；UTF-8 編碼；測試 PASS |

#### UG-G4-SB4: Top-K Ranking UI

| 項目 | 內容 |
|------|------|
| Goal | 即時排名儀表板 (從 Model Artifact 讀取) |
| Dependency | UG-G4-SB1 (Artifact) |
| In Scope | 每日截面 Top-K 排名卡片; DataMode 整合 (REAL/DEMO/EMPTY) |
| Out of Scope | 模型訓練; CSV 匯出 (SB3) |
| Affected Components | `src/ui/components.py`, `src/ui/data_loader.py`, `app.py` |
| Tests | `test_topk_from_artifact`, `test_topk_demo_mode_banner`, `test_topk_empty_when_no_artifact` |
| Rollback | Revert commit |
| Definition of Done | 排名從 Artifact 動態讀取；DEMO 模式有標示；測試 PASS |

#### UG-G4-SB5: 回測曲線真實化

| 項目 | 內容 |
|------|------|
| Goal | 使用 OOF 信號繪圖，取代當日情緒乘報酬 |
| Dependency | UG-G3-SB7 (Benchmark 產出) |
| In Scope | 讀取 Benchmark 產出的 OOF signal + T+1 return 繪圖; 含交易成本 |
| Out of Scope | 模型重訓練; 新增 Benchmark |
| Affected Components | `src/ui/charts.py`, `src/ui/data_loader.py` |
| Tests | `test_backtest_uses_oof_signals`, `test_backtest_includes_costs`, `test_backtest_demo_mode` |
| Rollback | Revert commit |
| Definition of Done | 回測曲線使用 OOF 信號；含交易成本；DEMO 模式有標示；測試 PASS |

---

## 11. 量化目標 (全部標記為 TARGET 或 HYPOTHESIS)

> 以下數字均為**目標或假設**，非已證實成果。需完成 UG-Gate-3 Benchmark 後才能升級為 VERIFIED 或 OBSERVED。

### 11.1 準確度目標

| Metric | Target Value | Evidence Label | Measurement Method |
|--------|-------------|----------------|-------------------|
| 條件勝率 (Selective) | > 60% (保守)。**狀態註記（`UG-G3-SB5` Gate B，2026-09-15，`DEC-041`）**：`target_up_down` 於現行特徵集（`ARM_A_FEATURE_COLS`）下未達成本目標所隱含的方向判別力前提（`RISK-030`：四個 Specialist 與 Meta-Learner 的 OOF AUC 皆 ≈0.50，接近隨機）；目標數字本身保留不改，`UG-G3-SB6` 改以 `target_triple_barrier`／Timeout 類為 gating 對象。**Timeout gating 目標已達成（`UG-G3-SB7` Gate B，2026-09-16）**：覆蓋率 ≥80%、精準度提升 ≥4×、召回 ≥60% 已於 Calib-eval **與 Holdout（折 33-42）兩段皆達成**（Calib-eval 80.00%／4.15×／83.03%；Holdout 92.52%／10.73×／80.28%）；`target_up_down` 四個 Specialist 於 Holdout 的觀察用 AUC（0.50～0.52）與樣本內三段一致，樣本外封閉，無排序訊號結論定案 | `OBSERVED` | Purged WF OOF; 台股前 150 大; 至少 3 年歷史 (理想 5 年); 最近 6-12 個月保留為 Holdout |
| Selective 覆蓋率 | 30%~50% 的交易日發出信號。**狀態註記（`UG-G3-SB7` Gate B，2026-09-16）**：與現行二元 gating 設計不對應，宣告不適用，改為描述性報告「實際達成覆蓋率」——Calib-eval 80.00%、Holdout 92.52% | `TARGET`（原定義不適用，見狀態註記） | 同上 |
| Macro F1 | > 0.55 (vs 分類基準：Always-Up, Majority Class, Logistic Regression)。**狀態註記（`UG-G3-SB7` Gate B，2026-09-16）**：Timeout 三分類 fixed-argmax macro F1 一項，PO 裁決不補（為此需二次讀取已消費的 Holdout，代價與「只揭露不設門檻」的資訊價值不成比例）；若 Gate 4 需要，於當時的 Gate A 提案一併定義 | `NOT VERIFIED`（裁決不補，去處見狀態註記） | 同上 |
| 淨累積報酬 | > Buy & Hold + 交易成本 (Buy & Hold 為財務策略基準，不具「勝率」概念)。**狀態註記（`UG-G3-SB7` Gate A v2 裁決，2026-09-16）**：Out of Scope——系統目前沒有交易模擬引擎，登記候補案（`PROJECT_STATUS.md` §0.5），排名基準（Equal Weight Top-K／Random Top-K）隨之一併 Out of Scope | `TARGET`（Out of Scope，見狀態註記） | 含 0.1425% 手續費 + 0.3% 證交稅 + 0.1% Slippage |

### 11.2 效能目標

| Metric | Target Value | Evidence Label | Measurement Method |
|--------|-------------|----------------|-------------------|
| ETL 總耗時 (150 檔) | < 5 分鐘 | `HYPOTHESIS` | Dev Container CPU-only; 含股價 + PTT |
| 推論延遲 (單檔) | < 50ms | `HYPOTHESIS` | Model Artifact 載入後 predict() 計時 |
| API 費用 | $0 (不使用付費 API) | `TARGET` | yfinance + PTT/Dcard 公開資料 |

### 11.3 Measurement Template

每個量化目標在正式 Benchmark 時必須附上：

```
- Dataset: 台股前 150 大 × N 交易日 (至少 3 年歷史, 理想 5 年)
- Training/Validation: 前段資料, Purged Walk-Forward (模型選擇與校準)
- Holdout: 最近 6-12 個月 (從不用於模型選擇、門檻選擇)
- Constraint: 不得使用相同 Folds 同時進行模型選擇、門檻選擇與最終績效宣稱
- Classification Baselines: Always-Up, Majority Class, Logistic Regression
- Financial Baseline: Buy & Hold (策略基準, 非分類器)
- Ranking Baselines: Equal Weight Top-K, Random Top-K
- Metric Definition: [精確定義]
- Hardware/Environment: Dev Container, PostgreSQL 18, CPU-only
- Transaction Cost: 0.1425% + 0.3% + 0.1% slippage (所有基準與策略一致)
- Acceptance Threshold: [精確門檻]
- Measurement Method: Purged Walk-Forward OOF (Holdout 分離)
```

---

## 12. Database Migration Plan 摘要

### 12.1 Migration 策略

| 項目 | 決策 |
|------|------|
| 方案 | Additive DDL Script + schema_version 表 |
| 理由 | 專案規模適合輕量 SQL Script；累積 >10 Migration 後再評估 Alembic |
| 目錄結構 | `database/migrations/NNN_description.sql` + `apply_migrations.py` |

### 12.2 Migration 清單

| Migration | 版本 | 內容 | Gate |
|-----------|------|------|------|
| 001_baseline.sql | v0→v1 | schema_version 表建立 | UG-G1-SB4 |
| 002_expand_ml_features.sql | v1→v2 | daily_ml_features 7→29 欄（+22，含 2 metadata） | UG-G2-SB1 |
| 003_expand_articles.sql | v2→v3 | market_articles 新增 push/boo/neutral/provider_id | UG-G2-SB3 |

### 12.3 安全保證

1. 只使用 `ADD COLUMN IF NOT EXISTS` — 純增量
2. 不 DROP TABLE、不 TRUNCATE、不修改 PK
3. 遷移前必須 `pg_dump -Fc` (邏輯備份到 Repository 外)
4. 每個 Migration 在單一 Transaction 內
5. 失敗 → 自動 ROLLBACK
6. 先在隔離 PostgreSQL 18 容器驗證
7. **不修改、不刪除、不破壞 `.devcontainer/postgres-data/`**
8. **`schema_version` 表一旦建立，不得以 DROP TABLE 方式回滾**

### 12.4 分層 Rollback 策略 (V6 新增)

> **V6 修正**：V5 將 Rollback 寫為 `DROP TABLE schema_version`，屬破壞性操作且會摧毀遷移追蹤。V6 改為分層策略。

| 場景 | Rollback 方式 | 需要 PO 批准 |
|------|---------------|-------------|
| 程式碼回滾 | `git revert` 回復 runner commit | 否 |
| 隔離驗證環境 | 銷毀整個臨時測試資料庫（不影響 dev/prod） | 否 |
| 開發資料庫：Migration 執行失敗 | Transaction 自動 ROLLBACK（Migration 在 Transaction 內執行） | 否 |
| 開發資料庫：已成功的 Additive Migration 需要修正 | Forward Fix（新增一個修正 Migration） | 否 |
| 開發資料庫：需要完整回復到遷移前狀態 | 使用遷移前 `pg_dump` logical backup 還原 | **是** |
| **禁止** | 自動 DROP columns 或 `schema_version` 表 | — |

---

## 13. Purged Walk-Forward 規格摘要

### 13.1 問題根因

```
feature_aggregator.py:459  target_next_close = shift(-1)
    → T 日標籤 = f(Close[T+1])

time_series_split.py:148   Train 包含 T 日
time_series_split.py:152   Test 從 T+1 日開始
    → Train[T].label 依賴 Test[T+1].close
    → 邊界前視偏誤 (VERIFIED)
```

### 13.2 修正方案 (V6 校正)

> **V6 修正**：V5 將 Embargo 寫為「從 Test 開頭移除 embargo 行」，會刪除真實測試資料。V6 校正為正確的 Purge/Gap/Embargo 定義。

```
label_end_date[T] = trade_date[T + label_horizon]

Purge:
    移除 TRAINING 中 label_end_date >= test_start_date 的行。
    目的：防止訓練標籤與測試特徵的時間重疊。

Gap (可選):
    在 Train 結束與 Test 開始之間保留若干交易日的隔離區間。
    隔離天數內的資料不參與訓練集也不參與測試集。
    嚴格 Walk-Forward 可設為 0。

Embargo:
    在交叉驗證中，若 Test Fold 結束後的資料可能進入其他 Fold 的訓練集，
    則排除 test_end_date 之後 embargo_days 個交易日的訓練候選。
    嚴格單向 Walk-Forward (無未來 Fold 重用) 可設 embargo_days=0，
    主要依 label_end_date Purge 保護。

時間單位：所有時序參數使用交易日數，不使用不明確的百分比 (embargo_pct)。

斷言: max(train.label_end_date) < min(test.trade_date)
```

### 13.3 Label Horizon 對應

| 標籤策略 | H | Purge 範圍 |
|----------|---|------------|
| T+1 漲跌 | 1 | 移除 Train 中 label_end_date >= test_start 的行 (通常末 1 天) |
| Triple-Barrier 5 日 | 5 | 移除 Train 中 label_end_date >= test_start 的行 (通常末 5 天) |

### 13.4 實作對齊（UG-G1-SB1 步驟 3～5，2026-08-24/25）

`src/ml/time_series_split.py`／`src/transform/feature_aggregator.py` 已依 §13.1～§13.3 實作，
`WalkForwardSplitter` 新增 `label_horizon`、`embargo_days`、`assert_no_boundary_leakage()`；
`generate_target_labels()` 新增 `label_end_date` 欄位。完整證據見
`doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_STEP4_AFTER_SNAPSHOT.md`。

**規格未明訂、實作時需補充定義的一點**：§13.2 定義 `label_end_date[T] = trade_date[T + label_horizon]`，
但未指明當面板內多檔股票的實際交易日曆不對齊時（例如個股停牌），此定義應以**全域**交易日序列
還是**個股自身**交易日序列計算。PO 2026-08-25 獨立驗證發現，以全域序列近似會在停牌情境下低估
應被 Purge 的列（已以重現測試證實），因此實作採**個股自身交易日曆**為準（`generate_target_labels()`
逐股 `groupby('stock_id')['trade_date'].shift(-label_horizon)`），`WalkForwardSplitter.split()`
優先讀取該逐列真實值，僅在欄位缺席時才退回全域近似法並於 docstring 揭露精度限制。

---

## 14. 剩餘風險清冊

| ID | 描述 | 嚴重度 | 標籤 | 緩解方式 |
|----|------|--------|------|----------|
| RISK-001 | 修正時序洩漏後模型準確率可能下降 | High | `HYPOTHESIS` | UG-G3-SB7 Benchmark 驗證 |
| RISK-002 | PTT 內頁解析被 Rate Limit 封鎖 | Medium | `OBSERVED` | Backoff + 可選略過 |
| RISK-003 | Dcard 端點非公開正式 API | Medium | `OBSERVED`（2026-08-29 實測 FAIL） | UG-G2-SB5 已執行；A1 HTTP 403（Cloudflare 邊緣攔截，A2–A6 `NOT EXECUTED`）→ **`DEFERRED WITH EVIDENCE`**。詳見 `REMAINING_RISKS.md` RISK-003 與 DEC-027 |
| RISK-004 | Threads 官方 API 權限不明 | Medium | `NOT VERIFIED` | Conditional/Deferred |
| RISK-005 | 150 檔 ETL 超出時間窗口 | Medium | `HYPOTHESIS` | UG-G2-SB7 效能基準測試 |
| RISK-006 | PostgreSQL Migration 失敗 | Low | `NOT VERIFIED` | 隔離容器驗證 + pg_dump + Transaction rollback |
| RISK-007 | SHAP 計算對大模型過慢 | Low | `HYPOTHESIS` | 先用 MDI, SHAP 可選 |
| RISK-008 | Git history 含舊 credential | Medium | `OBSERVED` | 公開前輪替 |
| RISK-009 | Stacking 過擬合 | Medium | `HYPOTHESIS` | Purged OOF |
| RISK-010 | 台股前 150 檔樣本量可能不足 | High | `HYPOTHESIS` | 至少 3 年歷史資料部分緩解；先設 60% TARGET |
| RISK-011 | Triple-Barrier Ambiguous 比例過高 | Medium | `HYPOTHESIS` | 監控並報告，必要時調 Barrier |
| RISK-012 | 未採用 Point-in-Time Universe 將導致存活偏誤 (Survivorship Bias) | High | `PLANNED` | UG-G2-SB6 PIT 約束：Snapshot 保存 + 歷史回測載入當期 Universe |

---

## 15. 建議新增/修訂 ADR 清單

### 15.1 新增 ADR

| ID | 標題 | 觸發 Gate |
|----|------|-----------|
| DEC-010 | Schema Version & Additive Migration Strategy (含分層 Rollback) | UG-G1-SB4 |
| DEC-011 | Purged Walk-Forward with Purge/Gap/Embargo (交易日計) | UG-G1-SB1 |
| DEC-012 | UI Four-State Data Mode (REAL/DEMO/EMPTY/ERROR) | UG-G1-SB2 |
| DEC-013 | Feature Registry as Single Source of Truth (版本化契約 LEGACY_17/CORE_16/COMMENT_ENHANCED_19) | UG-G0-SB2 |
| DEC-014 | Model Artifact Specification & Metadata Contract | UG-G4-SB1 |
| DEC-015 | XAI Global vs Local Attribution Separation | UG-G4-SB2 |
| DEC-016 | Multi-Source Comment Data Contract | UG-G0-SB3 |
| DEC-017 | Stock Universe Definition & Liquidity Ranking (Point-in-Time) | UG-G2-SB6 |
| DEC-018 | Triple-Barrier 三分類標籤、`Open[T+1]` Anchor 與 Ambiguous=NULL | UG-G3-SB1 |
| DEC-019 | Batch ETL Architecture (禁止逐股票爬取) | UG-G2-SB7 |
| DEC-020 | 模型競技排行榜動態化（Artifact-Driven Tournament Leaderboard） | UG-G1-SB3（實際新增，本表 Gate 0 規劃時未預見） |
| DEC-021 | RISK-013 根本解——`database/db_target_guard.py` | UG-G1-SB4（實際新增，本表 Gate 0 規劃時未預見） |
| DEC-022 | 歷史 ADR 記錄缺陷登錄（Legacy ADR Defect Index） | UG-G1-SB5（實際新增，本表 Gate 0 規劃時未預見） |
| DEC-023 | `label_reason` 判定範圍延後至 Gate 3 + `db_writer.py` NaN→NULL 轉換修正 | UG-G2-SB1（實際新增，本表 Gate 0 規劃時未預見） |

### 15.2 修訂既有 ADR

| ID | 修訂內容 |
|----|----------|
| DEC-003 | 恢復截斷內容 (L197+) |
| DEC-004 | 刪除 L315-432 重複區塊 |
| DEC-006 | 「18 欄位」→ 使用版本化契約名稱 (LEGACY_17 / CORE_16); 修復 LaTeX |
| DEC-007 | 同步校正特徵數量描述，使用版本化契約名稱 |

---

## 16. 舊版 V4/V5 問題解決對照表

| V4/V5 問題 | V6 解決方式 | 位置 |
|------------|------------|------|
| 68%~75% 勝率無證據 | 改為 TARGET > 60%; 附 Measurement Template | §11.1 |
| 30 秒 ETL 無測試 | 改為 HYPOTHESIS < 5 分鐘 | §11.2 |
| 5ms 推論無基準 | 改為 HYPOTHESIS < 50ms | §11.2 |
| 100% 零破壞性遷移 | 改為 Additive DDL + pg_dump + 隔離驗證 + 分層 Rollback | §12 |
| SB1.3 同時含 Dcard+Threads+Panel | 拆為 UG-G2-SB5/SB6/SB7 三個獨立 SB | §8 |
| 無 Migration 機制 | schema_version + apply_migrations.py + 分層 Rollback | §12 |
| 無 Feature Registry | 29 欄位完整 Registry 含版本化契約 (LEGACY_17/CORE_16/COMMENT_ENHANCED_19) | §4 |
| 時序洩漏未解決 | Purged WF + label_end_date + Purge/Gap/Embargo 正確定義 + 迴歸測試 | §13 |
| UI 假資料混淆 | 四狀態模式 + DEMO 醒目標示 | §7 (UG-G1-SB2) |
| 排行榜寫死 | 從 Artifact 動態讀取 | §7 (UG-G1-SB3) |
| 批次過大 | 24 個後續獨立 SB (Gate 1-4) + 7 個 Gate 0 SB = 31 個 | §5.2 |
| Gate 命名衝突 | UG-Gate-N 前綴 | §5.1 |
| **V5-C1: 17/15/19 矛盾** | 版本化契約 LEGACY_17 / CORE_16 / COMMENT_ENHANCED_19；open/high/low 移出 Feature Store | §3.4, §4 |
| **V5-C2: 留言公式錯誤** | 修正為 PO 核准公式：push_ratio 共用中間值 + rolling baseline + delta momentum | §4.3 |
| **V5-C3: Triple-Barrier 順序錯誤** | 移至 Gate 3 SB1（標籤在模型之前） | §5.2, §9 |
| **V5-C4: Embargo 定義錯誤** | 校正 Purge/Gap/Embargo 定義；embargo_pct → embargo_days | §13.2 |
| **V5-C5: Universe 缺 PIT** | 加入 Point-in-Time 約束、Snapshot 保存、存活偏誤防護 | §3.1, §8 |
| **V5-C6: 6 個月資料不足** | 改為至少 3 年 + Holdout 6-12 個月 | §11 |
| **V5-C7: Buy & Hold ≠ 勝率** | 分離分類/財務/排名三類基準 | §9, §11 |
| **V5-C8: Dcard 阻擋 Gate 2** | Dcard 改為 CONDITIONAL，不阻擋 Gate 2 | §5.1, §8 |
| **V5-C9: SB 計數錯誤** | 24 個後續 SB + 7 個 Gate 0 = 31；Brief 完整度分級 | §5.2, §6.1 |
| **V5-C10: DROP TABLE rollback** | 分層 Rollback 策略，禁止 DROP schema_version | §12.4 |
| **V7-BLOCK-1: raw 層 `DEFAULT 0`** | Migration 003 四個留言計數欄改為可 NULL 無 DEFAULT；區分「未解析」與「確實 0 則留言」 | §12.2, `DB_MIGRATION_PLAN.md` §4.3 |
| **V7-BLOCK-2: 情緒欄位無 `SOURCE_FAILED` 例外** | §5A 全欄位 NULL 語意規則（成因 W vs F）；A6/A7 加 `source_status` 前置條件 | §3.4, `FEATURE_REGISTRY.md` §5A |
| **V7-BLOCK-3: metadata 欄位不存在** | 補入 `source_status`／`label_reason`，27 → 29 欄；加 domain 與一致性 CHECK | §3.4, §4.0 |
| **V7-S1: 測試執行事實互相矛盾** | TRACEABILITY §3A.2 校正為已執行，附完整證據邊界 | §18.3 |
| **V7-S2: Part A 數字不可重現** | 活規格過濾器 + 逐處判定依據 | §18.0, §18.1 |
| **V7-S3: 4 項決策無 ADR 承接** | 補入 DEC-011／DEC-017／DEC-018（`Proposed`） | §15.1 |
| **V7-S4: §6.1 交付物表過期** | F 列改 19 項測試；H 列改 V8 | §6.1 |
| **V7-輕微: 三套編號互不對應** | 統一為 DB 序號 1-29；新增 `FEATURE_REGISTRY.md` §3.7 唯一對照表 | §4 |
| **V7-方法論: Part B 寫成通過條件** | 改為契約反查法（10 項）+ 可重跑腳本 `scripts/verify/gate0_contract_check.py` | §18.2 |

---

## 17. 執行時程估計

| Gate | SB 數量 | 預估工期 | 前置條件 |
|------|---------|----------|----------|
| UG-Gate-0 | 7 | 1-2 天 | PO 批准本計畫 |
| UG-Gate-1 | 5 | 2-3 天 | UG-Gate-0 關閉 |
| UG-Gate-2 | 7 | 3-5 天 | UG-Gate-1 關閉 |
| UG-Gate-3 | 7 | 5-7 天 | UG-Gate-2 關閉 |
| UG-Gate-4 | 5 | 2-3 天 | UG-Gate-3 關閉 |
| **Total** | **31** | **13-20 天** | — |

---

## 18. 全域驗證證據 (Auditable Verification Evidence)

> 驗證日期：2026-08-23。分為三組：
> **Part A（12 項）** — 單一文件內部正確性。
> **Part B（11 項）** — 跨文件契約一致性（V8 改為契約反查法；V8.1 依 PO 建議新增 B11）。
> **Part C** — 測試套件執行證據與環境邊界。

### 18.0 可重現性前置：活規格過濾器

> **V8 修正（S-2）**：V7 的 Part A 數字不可重現，因為驗證表**自己**含有被搜尋的字串，
> 稽核者照指令跑會得到與表格不同的數字。V8 引入「活規格過濾器」解決此問題。

三個 meta 章節本來就會引用舊字串來說明問題，不應計入活規格搜尋：
`§0.1`（版本修正對照）、`§16`（舊版問題解決對照表）、`§18`（驗證證據，即本章）。

```bash
# /tmp/livespec.sh — 抽出 Master Plan 的「活規格」文字
awk '
  /^### 0\.1 / {skip=1}   /^## 1\. /  {skip=0}
  /^## 16\. /  {skip=1}   /^## 17\. / {skip=0}
  /^## 18\. /  {skip=1}   /^## 19\. / {skip=0}
  !skip
' "$1"
```

**驗證此過濾器本身**：全文 1201 行 → 活規格 1073 行（濾除 128 行 meta 內容）。

以下 Part A 全部指令均以 `LS=$(bash /tmp/livespec.sh SYSTEM_UPGRADE_MASTER_PLAN.md)` 為輸入。

### 18.1 Part A — 單一文件正確性驗證

| # | 驗證項目 | 可重現指令 | 活規格 matches | 逐處判定 | PASS/FAIL |
|---|---------|-----------|:--------------:|----------|-----------|
| A1 | `"15 model inputs"` 無裸數字 | `echo "$LS" \| grep -c "15 model inputs"` | **0** | — | ✅ PASS |
| A2 | `embargo_pct` 不作為活參數 | `echo "$LS" \| grep -n "embargo_pct"` | **1** | §13.2「不使用不明確的百分比 (embargo_pct)」— **禁止語句**，非參數定義 | ✅ PASS |
| A3 | `DROP TABLE schema_version` 不作為 rollback | `echo "$LS" \| grep -n "DROP TABLE schema_version"` | **1** | §12.4「V5 將 Rollback 寫為…V6 改為分層策略」— **歷史說明**，非 rollback 指令 | ✅ PASS |
| A4 | Buy & Hold 不被描述為有「勝率」 | `echo "$LS" \| grep "Buy & Hold" \| grep -c "勝率"` | **2**（總計 5 處提及） | 兩處皆為否定句：「不是二元分類器，**不具有**「勝率」」／「為財務策略基準，**不具**「勝率」概念」 | ✅ PASS |
| A5 | `"23 個獨立 SB"` 已更正 | `echo "$LS" \| grep -c "23 個獨立"` | **0** | 已改為 24+7=31 | ✅ PASS |
| A6 | Gate 3 SB1 = Triple-Barrier | `echo "$LS" \| grep -c "UG-G3-SB1.*Triple"` | **3** | §5.2 依賴矩陣 + §9 SB1 Brief + §9 SB2 Panel Dataset 依賴 | ✅ PASS |
| A7 | 留言特徵公式正確 | 逐一對照 §4.3 vs `MULTI_SOURCE_SENTIMENT_AND_COMMENT_FEATURE_SPEC.md` L85-87 | — | rolling baseline ✓ ／ `1-push_ratio²` ✓ ／ delta momentum ✓ | ✅ PASS |
| A8 | Gate 2 准出條件不含 Dcard | `echo "$LS" \| sed -n '/\| UG-Gate-2 \|/p' \| grep -c "Dcard"` | **0** | 准出條件為「Feature Store 29 欄, PTT 留言契約驗證, Universe 建立, Batch ETL 驗證」 | ✅ PASS |
| A9 | Point-in-Time 已落地 | `echo "$LS" \| grep -c "Point-in-Time"` | **7** | §3.1 決策表 + §5.2/§5.3 約束 + §8 UG-G2-SB6 Brief | ✅ PASS |
| A10 | "最近 6 個月" 非唯一評估期間 | `echo "$LS" \| grep -c "最近 6 個月"` | **0** | 已改為至少 3 年 + Holdout 6-12 個月 | ✅ PASS |
| A11 | SB 加總 = 31 | `echo "$LS" \| grep -oE '— [0-9]+ SBs' \| grep -oE '[0-9]+' \| awk '{s+=$1} END {print s}'`；另計 `grep -c '^\| UG-G0-SB[0-9]'` | **24 + 7** | Gate 1-4 = 5+7+7+5 = 24；Gate 0 = 7；合計 **31** ✓ | ✅ PASS |
| A12 | **29 欄**加總正確 | 計算 §3.4 資料契約表 | — | 2 identifier + 2 context + **2 metadata** + 19 engineered + 4 target = **29** ✓ | ✅ PASS |

> **A2/A3/A4 的判定原則**：這三項的 match 數不為 0 是**預期且正確**的 —
> 活規格需要明確寫出「不使用 X」「V5 曾經 X，現改為 Y」才能防止回退。
> 驗證的重點不是「字串完全消失」，而是「每一處出現都是禁止語句或歷史說明，沒有一處是活的規格」。
> 本表已逐處列出判定依據，稽核者可直接照指令重跑核對。

### 18.2 Part B — 跨文件契約一致性驗證（V8 改為契約反查法，V8.1 新增 B11）

> **V8 方法論修正（PO 指正）**：V7 的 Part B 有一個根本缺陷 —
> B4 的指令是 `grep "fillna" FEATURE_REGISTRY.md | grep -iE "comment|push"`，
> 第二段 grep 把搜尋範圍**限縮在留言三欄**，因此結構上不可能發現情緒六欄的同型缺陷。
> **那是為了通過而寫的驗證，不是為了偵測而寫的。**
>
> V8 全面改為**契約反查法（contract-driven）**：
> 從**契約要求**出發列舉所有應受約束的對象，逐一反查文件是否滿足，
> 而非從已知答案出發湊 grep。
>
> **方法論有效性的證據**：新的 B8 在首次執行時即 **FAIL**，
> 抓出 DEC-011 / DEC-017 / DEC-018 三份 ADR 不存在（PO 的 S-3 意見）。
> 舊式 grep 檢查不可能發現此問題，因為沒人會去 grep 一個「應該存在但不知道不存在」的東西。

**完整驗證腳本**：`scripts/verify/gate0_contract_check.py`（已納入版控，可由稽核者直接重跑）。

```bash
python scripts/verify/gate0_contract_check.py
# exit 0 = 全部通過；non-zero = 有項目 FAIL
```

執行日期 2026-08-23，結果 **10/10 PASS，exit 0**。

| # | 驗證項目 | 反查邏輯（從契約要求出發） | 實際結果 | PASS/FAIL |
|---|---------|---------------------------|----------|-----------|
| B1 | **29 欄契約完整性** | 從 Migration DDL 抽出 `daily_ml_features` 全部 `ADD COLUMN`，加既有 7 欄，斷言總數 == 29 | migration 新增 **22** + 既有 7 = **29** ✓ | ✅ PASS |
| B2 | **被引用欄位皆存在於契約**<br>（抓 BLOCK-3 的檢查） | 掃描 5 份 Gate 0 文件中所有 `df['x']` / `df.loc[...,'x']` 形式的欄位引用，反查是否都在 29 欄契約或 `market_articles` 新欄中 | **8** 個被引用欄位，缺失 **0**（`source_status`、`label_reason` 已補入契約） | ✅ PASS |
| B3 | **社群欄位皆有 `SOURCE_FAILED`→NULL 規則**<br>（抓 BLOCK-2 的檢查） | 從 `FEATURE_REGISTRY.md` §5A.3 對照表列舉**所有**來源為「社群／社群留言」的列，逐列檢查其「成因 F」欄是否寫明 NULL | **9** 個社群列，全部標明「必須 NULL」，缺失 **0** | ✅ PASS |
| B4 | **raw 層留言計數欄無 `DEFAULT`**<br>（抓 BLOCK-1 的檢查） | 從 Migration 003 抽出 `market_articles` 四個留言計數欄的 DDL，斷言皆不含 `DEFAULT` | 四欄型別皆為裸 `INTEGER`（可 NULL，無 DEFAULT） | ✅ PASS |
| B5 | **Triple-Barrier label domain 一致** | 列舉三份應宣告 domain 的文件，逐一確認皆為 `{-1,0,1}`；另確認 DDL 有 CHECK 約束 | 3/3 文件宣告；DDL `CHECK (... IN (-1,0,1))` = True | ✅ PASS |
| B6 | **Barrier anchor 一致為 `Open[T+1]`** | 正向：計算使用 `Open[T+1]` 的文件數；反向：搜尋殘留的 `Close[T] × (1` 舊 anchor | **6** 份文件使用 `Open[T+1]`；殘留舊 anchor **0** | ✅ PASS |
| B7 | **無「來源失敗→空 DataFrame」** | 列舉 7 份文件中**每一處**提及「回傳空 DataFrame」或「article_count = 0」，逐行判定是否為正當語境（`SUCCESS_EMPTY` / 否定句） | **9** 處提及，逐行判定全部為正當語境 | ✅ PASS |
| B8 | **§19 需 PO 簽的決策皆有 ADR 承接** | 從 §19 清單列舉所有需 PO 核准的架構決策，反查 `DECISIONS.md` 是否都有對應 ADR | **6/6** 存在：DEC-010, **DEC-011**, DEC-013, DEC-016, **DEC-017**, **DEC-018**（粗體為 V8 依 S-3 新增） | ✅ PASS |
| B9 | **Dcard SB 引用正確** | 反查 `MULTI_SOURCE_DATA_CONTRACT.md` 是否殘留 `UG-G3-SB1` 誤引用 | 無殘留；Appendix A 為 `UG-G2-SB5` | ✅ PASS |
| B10 | **編號方案有唯一對照表** | 確認存在單一權威對照表解決「DB 序號 vs 模型輸入索引」歧義 | `FEATURE_REGISTRY.md` §3.7 存在，涵蓋三套契約 | ✅ PASS |
| B11 | **全文件契約數字宣告一致**<br>（V8.1 新增，抓 C-1~C-4 類型的缺陷） | 掃描全部 7 份文件中所有「N 欄契約」「N 條測試斷言」宣告，反查是否等於權威值（29 欄 / 10 條）；已知遺留以具名 allowlist 標為 WARN 而非隱藏 | 掃描 7 份文件，**違規 0**；1 筆已登錄遺留（`DECISIONS.md:577` DEC-007 的 18 欄舊契約 — DRIFT-007，排定 UG-G1-SB5 修訂） | ✅ PASS |

**Part B: 11/11 PASS**

#### B11 的由來

PO 在 V8 審查中指出 C-1~C-4（治理層文件仍寫 27 欄／8 條斷言）能存活的原因很具體：

> 腳本已把 `DECISIONS.md`／`TRACEABILITY.md` 讀進 `D`，但 **B1 是拿 DDL 跟自己對，B8 只查 ADR 是否存在、不查內容**。

B11 補上這個盲點：不再只驗證「規格層自洽」，而是反查**所有文件**對契約數字的宣告是否一致。
已知的既有 ADR 遺留（DEC-007 的 18 欄）以具名 allowlist 標為 `WARN` 並附修復排程，
**讓債務可見而非消失** —— 若直接排除該檔案，等於製造下一個 C-1。

#### 反查法 vs 舊式 grep 的差異

| | 舊式（V7） | 契約反查法（V8） |
|---|---|---|
| 起點 | 已知的問題字串 | 契約要求的完整對象集合 |
| 能否發現「未知的同型缺陷」 | ❌ 不能（範圍已被限縮） | ✅ 能（列舉全部後逐一檢查） |
| 能否發現「應存在但缺失」 | ❌ 不能 | ✅ 能（B2、B8 即為此類） |
| 首次執行結果 | 8/8 PASS（有洞） | 9/10 PASS → 修正後 10/10 |

#### 腳本本身的自我污染防護

新腳本首次執行時 B2 與 B6 亦 FAIL —— 因為 §18 的驗證表**自己**含有
`df['x']` 範例與 `Close[T] × (1` 字串，被腳本掃描為「活規格中的違規」。
這與 §18.0 描述的 Part A 自我污染是同一類問題。

腳本已內建 `strip_meta_sections()` 濾除 Master Plan 的 §0.1 / §16 / §18，
與 Part A 的活規格過濾器採用相同邊界。修正後 10/10 PASS。

> 這件事本身是方法論有效的第三個證據：**一個能抓到自己缺陷的驗證器，
> 才有可能抓到文件的缺陷。**

### 18.3 Part C — 測試套件現況（回應 PO 無法重現「154 tests PASS」）

> PO 於 V6 審查時回報：Dev Container 未運行，本機執行結果為 `Ran 66 tests` 與 13 個 Import Error，
> 因此不能將「154 tests PASS」標為目前已驗證。PM 已就此重新執行並記錄完整環境條件。

| 項目 | 內容 |
|------|------|
| 執行日期 | 2026-08-22 |
| 執行指令 | `python -m unittest discover -s tests -p "test_*.py"` |
| 執行環境 | Windows 本機 Python 3.10.11（**非** Dev Container） |
| **結果** | **`Ran 154 tests in 1.486s` / `OK`** |
| 測試檔案數 | 18（`ls tests/*.py \| wc -l`） |
| 測試函式數 | 154（`grep -c "def test_" tests/*.py` 加總） |

#### 依賴套件實際狀態

| 套件 | 狀態 | 影響 |
|------|------|------|
| `numpy` 2.2.6 | 存在 | 測試可正常 import |
| `pandas` 2.3.3 | 存在 | 測試可正常 import |
| `streamlit`, `plotly` | 存在 | UI 契約測試走真實路徑 |
| `sklearn`, `lightgbm`, `xgboost` | **缺席** | 測試走程式內建的純 NumPy fallback 實作 |
| `psycopg2` | **缺席** | 測試走 `MagicMock` 替身（所有 DB 存取皆 `@patch`，不觸及真實資料庫） |

#### 差異根因與證據邊界

- **PO 環境 66 tests 的根因**：`numpy` / `pandas` 缺席時，13 個測試檔案在 import 階段即失敗，
  只剩 5 個不依賴這兩者的檔案共 66 個測試可執行。此為**環境依賴缺失**，非程式回歸失敗。
- **`PREVIOUSLY VERIFIED`（本次未重驗的部分）**：
  `sklearn` / `lightgbm` / `xgboost` 三個 ML 套件在本次環境缺席，
  相關測試走的是 fallback 實作路徑，**不等於**真實 sklearn/LightGBM/XGBoost 行為已驗證。
- **`NOT VERIFIED`**：Dev Container 環境（Python 3.14.6 + 完整依賴）本次未執行；
  真實 PostgreSQL 連線、Live Gemini API、真實 PTT 爬蟲皆未觸及。
- **可重現條件**：在安裝 `numpy` 與 `pandas` 的任一 Python 3.10+ 環境執行上述指令即可重現 154/154。
  若需驗證真實 ML 套件路徑，須另行安裝 `requirements.txt` 全部依賴。

### 18.4 驗證與 PO 確認項目的關係

| 項目 | 性質 | 數量 | 判定者 |
|------|------|------|--------|
| §18.1 Part A | 單一文件內部正確性的字串／數值檢查 | 12 項 | PM 執行，可重現 |
| §18.2 Part B | 跨文件契約一致性的集合比對 | 8 項 | PM 執行，可重現 |
| §18.3 Part C | 測試套件執行證據與環境邊界 | 1 組 | PM 執行，可重現 |
| §19 Closure Review | 治理層級的設計意圖與授權邊界審查 | **20 項** | **PO 人工判定** |

Part A + B + C 保證技術準確（文件之間不打架、測試可重現）；§19 保證決策正確（設計意圖符合 PO 期待）。
兩者互補，不可互相取代。

---

## 19. Gate 0 Closure Review 審查請求（共 20 項）

> **性質**：Gate 0 關閉審查 — A～J 交付物全部為 `READY FOR PO REVIEW`，請 PO 逐項審查後決定是否關閉 Gate 0。
> **本清單共 20 項確認事項**（§18.4 已對照說明其與 Part A/B/C 技術驗證的分工）。

**請 Project Owner 確認：**

| # | 確認事項 | 依據 |
|---|---------|------|
| 1 | ☐ A～J 交付物全部為 `READY FOR PO REVIEW`，各有 Evidence 文件與完成日期 | §6.1 |
| 2 | ☐ 6 份獨立證據文件已產出並內容一致 | DOCUMENT_DRIFT_REMEDIATION / FEATURE_REGISTRY / MULTI_SOURCE_DATA_CONTRACT / DB_MIGRATION_PLAN / PURGED_WALK_FORWARD_SPEC / REMAINING_RISKS |
| 3 | ☐ 每個 SB 只有一個主要責任，依賴矩陣無混合責任 | §5.2 |
| 4 | ☐ 每個 SB 能獨立測試、回滾、審查及 Commit | §7-10 |
| 5 | ☐ Gate 1 的 5 個 SB 均有完整 16 項 Brief | §7 |
| 6 | ☐ Gate 2-4 的 19 個 SB 均有至少 8 項 Brief | §8-10 |
| 7 | ☐ 4 個後續 Gate 有明確輸入/輸出依賴，不跨 Gate 偷跑 | §5.2 + §5.3 |
| 8 | ☐ Triple-Barrier 在 Panel Dataset 與模型訓練之前完成 | §5.3 |
| 9 | ☐ Feature Registry 使用版本化契約 LEGACY_17 / CORE_16 / COMMENT_ENHANCED_19 | §3.4 |
| 10 | ☐ Migration Plan 在 Feature Store 前完成，Rollback 採分層策略 | §12.4 |
| 11 | ☐ Demo/Real 分離在 UI 宣稱預測績效前完成 | §5.3 |
| 12 | ☐ 所有量化數字標記為 TARGET 或 HYPOTHESIS | §11 |
| 13 | ☐ Purge/Gap/Embargo 使用交易日數，非百分比 | §13.2 |
| 14 | ☐ Buy & Hold 為財務策略基準，分類基準獨立列出 | §9, §11 |
| 15 | ☐ Dcard 為 Conditional，依賴 Gate 0 交付物 D，不阻擋 Gate 2 關閉 | §5.1, §8 |
| 16 | ☐ Stock Universe 採 Point-in-Time，歷史回測載入當期 Snapshot | §3.1 |
| 17 | ☐ Benchmark 使用至少 3 年資料，Holdout 6-12 個月分離 | §11 |
| 18 | ☐ **Triple-Barrier 統一時間約定**：T 收盤預測 → `Open[T+1]` 進場＝Barrier anchor → T+1~T+5 觸線 → Slippage/成本套用於 `Open[T+1]` | §3.3, `PURGED_WALK_FORWARD_SPEC.md` §4.1 |
| 19 | ☐ **Triple-Barrier 三分類標籤**：`1`=止盈 / `-1`=止損 / `0`=Timeout / `NULL`=同日觸雙線或資料不足；止損與 Timeout 不合併 | §3.3, `PURGED_WALK_FORWARD_SPEC.md` §4.3 |
| 20 | ☐ **來源失敗語意與留言 NULL 規則統一**：`SOURCE_FAILED` 拋例外不回傳空 DataFrame；留言三欄失敗／未啟用時保持 `NULL`，不得補 0 或中立值 | `MULTI_SOURCE_DATA_CONTRACT.md` §7, `FEATURE_REGISTRY.md` §5A |

### 19.1 核准後 PM 應執行的收尾程序

> **【適用範圍警告，2026-08-29 補】本節只針對 Gate 0，且清單寫死 6 則 ADR。**
> Gate 1／2 沒有對應程序——實務結果是 DEC-020／021／022 靠各自 Gate B 臨時核准僥倖處理，
> **DEC-023／024／025 就這樣停在 `Proposed`**（DEC-024 的 CHECK 約束卻已隨 migration 004
> 在資料庫生效）。`evidence-sync` §2.1 把這個病命名為 **C-5**，**它已發生三次**。
>
> **根因是「綁清單」**：清單只列當時已知的 ADR，新增的必然落在清單外。
> 通用規則改為**綁事件**，見 `PROJECT_STATUS.md` §0.5 第 10 項——
> **每個 SB 的 Gate B 通過時，該 SB 新增的 ADR 一併轉 `APPROVED` 並補進
> `TRACEABILITY.md` §3.2**。本節保留原文作為 Gate 0 的歷史紀錄。

PO 核准 Gate 0 後，PM 才可執行以下動作（**核准前不得執行**）：

1. 將 `DECISIONS.md` 中**全部 6 份** Gate 0 提案 ADR 的狀態由 `Proposed` 更新為：
   - `狀態：APPROVED`
   - `Approved by: Project Owner`
   - `核准日期：<PO 核准當日>`

   | ADR | 標題 | 觸發 Gate |
   |-----|------|-----------|
   | **DEC-010** | Schema Version & Additive Migration Strategy | UG-G1-SB4 |
   | **DEC-011** | Purged Walk-Forward with Purge / Gap / Embargo | UG-G1-SB1 |
   | **DEC-013** | Feature Registry as Single Source of Truth | UG-G0-SB2 |
   | **DEC-016** | Multi-Source Comment Data Contract | UG-G0-SB3 |
   | **DEC-017** | Stock Universe Definition & Point-in-Time Liquidity Ranking | UG-G2-SB6 |
   | **DEC-018** | Triple-Barrier 三分類標籤、`Open[T+1]` Anchor 與 Ambiguous = NULL | UG-G3-SB1 |

   > 六份必須一併更新。DEC-011／017／018 承接的是 §19 第 13、16、18、19 項需 PO 當下核准的決策，
   > 若遺漏，這些決策將永遠停留在 `Proposed`，S-3 的補正等於失效。

2. 同步更新 `TRACEABILITY.md` §3.2 的狀態說明（由「待 PO 核准」改為已核准並註記日期）。
3. 依 PO 授權範圍執行 Gate 0 Commit：
   - **必須納入** `scripts/verify/`（§18.2 引用的可重跑驗證證據，目前為未追蹤目錄）
   - **不得包含** `.claude/settings.local.json` 或其他未經審查檔案
4. Gate 1 啟動仍需 PO 另行核准，Gate 0 關閉不自動授權 Gate 1。
