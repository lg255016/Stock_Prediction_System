# UG-Gate-1 啟動申請

> **性質**：Gate 啟動申請，非實作授權。
> **提交日期**：2026-08-23
> **提交前狀態**：`src/` 與 `tests/` 未動（diff 為空）
> **前置 Gate**：UG-Gate-0 已於 2026-08-23 由 PO 核准關閉（commit `3baa34f`）
> **環境基線**：GOV-03 已釘選（commit `0269fb1`），淨重建驗證通過

---

## 1. 申請範圍

UG-Gate-1「Core Fixes」的 5 個 Small Batch。**逐個 SB 送審、逐個取得授權**，
不申請一次性授權全部 5 個。

| SB | 名稱 | 主要影響 |
|----|------|----------|
| UG-G1-SB1 | Purged Walk-Forward 實作 | `src/ml/time_series_split.py`、`src/transform/feature_aggregator.py` |
| UG-G1-SB2 | UI Demo/Real 模式分離 | `src/ui/data_loader.py`、`src/ui/components.py`、`app.py` |
| UG-G1-SB3 | UI 排行榜動態化 | `src/ui/components.py`、`src/ui/data_loader.py` |
| UG-G1-SB4 | DB Migration 機制建立 | `database/`（新增 migrations 與 runner） |
| UG-G1-SB5 | 文件全面校正 | `doc/`、`README.md`（新建） |

---

## 2. 五個 SB 的 16 項 Brief

完整 Brief 位於 `SYSTEM_UPGRADE_MASTER_PLAN.md` §7，本節僅提供完整度稽核結果。

### 2.1 欄位完整度稽核

以核心 17 欄位（16 項 Brief + Gate B）逐一比對：

| SB | 實際欄位數 | 缺少的核心欄位 |
|----|-----------|---------------|
| UG-G1-SB1 | 17 | 無 |
| UG-G1-SB2 | 17 | 無 |
| UG-G1-SB3 | 18 | 無 |
| UG-G1-SB4 | 18 | 無 |
| UG-G1-SB5 | 17 | 無 |

核心欄位集：`Goal`／`Requirement Source`／`Current State`／`Proposed Change`／`In Scope`／
`Out of Scope`／`Affected Components`／`Data/API/Schema Contract`／`Failure Semantics`／
`Risks & Trade-offs`／`Tests`／`E2E Verification`／`Documentation Sync`／`Rollback`／
`Definition of Done`／`Gate A`／`Gate B`

**稽核方式**（可重跑）：解析 Master Plan §7 各 SB 表格的第一欄，與核心欄位集做差集。

### 2.2 GOV-02/GOV-03 後需要調整的 Brief 內容

以下三處在 Brief 撰寫時尚未有 GOV-02/GOV-03 的發現，開工前應併入：

| SB | 需調整處 | 原因 |
|----|---------|------|
| SB1 | `E2E Verification` 欄 | 原寫「LEGACY_17 baseline + Purged WF 全流程跑通」，未涵蓋 §4 的證據分割要求 |
| SB2 | `In Scope` 欄 | 應明確納入 HERM-01~09 的封閉性修復（原僅寫 DataMode 四狀態） |
| 全部 | `Tests` 欄 | 執行環境須標明為 dev container（GOV-02 §13.0），非 host |

**本申請不修改 Master Plan** —— 上述調整待 PO 核准 Gate 1 後，於各 SB 的 Gate A 階段一併提出。

---

## 3. High 風險處置說明

依 `REMAINING_RISKS.md` 準則 1，High 風險須 PO 明確簽核 Accept／Mitigate／Defer。

### 3.1 適用範圍釐清（先講清楚哪一項真正擋 Gate 1）

| 風險 | 影響 Gate | 是否阻擋 Gate 1 開工 |
|------|----------|---------------------|
| **RISK-001** | **UG-G1-SB1**, UG-G3-SB7 | **是** —— 直接落在本 Gate |
| RISK-010 | UG-G3-SB7 | 否 —— 屬 Gate 3 |
| RISK-012 | UG-G2-SB6 | 否 —— 屬 Gate 2 |

依準則 5（跨多 Gate 風險須在最早影響的 Gate Review 首次審查），RISK-001 必須在本次簽核。
RISK-010 與 RISK-012 的處置一併提出供您預覽，但它們不構成 Gate 1 的開工前提。

### 3.2 RISK-001：修正時序洩漏後模型準確率可能下降

| 項目 | 內容 |
|------|------|
| 現況標籤 | `HYPOTHESIS` |
| 建議處置 | **Accept（接受）** |

**理由**：

1. 準確率下降**不是副作用，是修正本身的預期結果**。目前的數字建立在
   `train[T].label` 依賴 `test[T+1].close` 的邊界洩漏之上（`VERIFIED`，
   `feature_aggregator.py:459` + `time_series_split.py:148-160`）。
   修正後數字下降，代表原數字虛高，不代表新實作有問題。
2. 不接受此風險的唯一替代是保留洩漏，那違反 `CLAUDE.md` §7.4
   （必須防止 Look-ahead Bias）與已核准的 DEC-011。
3. 下降幅度在 Gate 1 無法量測 —— Gate 1 只實作切分機制，
   真正的 benchmark 在 UG-G3-SB7。Gate 1 階段可觀測的是
   「Fold 數是否仍 ≥ 3」與「Purge 後訓練集是否仍足夠」。

**接受的邊界**：

- 接受「準確率下降」本身，**不接受**「因下降而回退到有洩漏的版本」。
- 若 Purge 後某些 Fold 的訓練樣本不足 `min_train_size`，該 Fold 跳過並記錄警告
  （已寫入 SB1 Brief 的 `Failure Semantics`），不得為了保留 Fold 而縮小 Purge 範圍。

**追蹤**：依準則 5，於 UG-G3-SB7 Benchmark 時重新評估並更新標籤。

### 3.3 RISK-010：台股前 150 檔 × 短歷史樣本量不足

| 項目 | 內容 |
|------|------|
| 現況標籤 | `HYPOTHESIS` |
| 建議處置 | **Defer（延後至 Gate 3 決議）** |

**理由**：

1. 本風險的觸發條件是「Fold 內樣本不足」，**只有在 Panel Dataset 實際建立後才能量測**
   （UG-G3-SB2）。Gate 1 完全不碰資料量。
2. Master Plan §11 已將 Benchmark 資料期間從 6 個月改為至少 3 年
   （V6 修正，PO 已核准），這是針對本風險的既有緩解。該緩解是否足夠，
   要等實際載入資料後才知道。
3. 現在做 Accept 或 Mitigate 決策都缺乏依據 —— 沒有數字可以判斷。

**Defer 的具體條件**：於 UG-G3-SB2（Panel Dataset）完成後，
以實際 Fold 樣本數重新評估並提交 PO 簽核，方可進入 UG-G3-SB7。

### 3.4 RISK-012：未採 Point-in-Time Universe 導致存活偏誤

| 項目 | 內容 |
|------|------|
| 現況標籤 | `PLANNED` |
| 建議處置 | **Mitigate（緩解，已有設計）** |

**理由**：

1. 與 RISK-001/010 不同，本風險**已有明確的設計解法**：DEC-017（PO 已核准）
   規定 Point-in-Time Snapshot、`universe_effective_date` 保存、
   歷史回測載入當期 Universe，以及新上市／下市／停牌／代碼異動處理。
2. 緩解措施已寫入 UG-G2-SB6 Brief 的 `Tests` 欄
   （`test_universe_point_in_time_no_future_data` 等三項）。
3. 因此本風險不是「是否接受」的問題，而是「實作是否確實落地」的問題。

**Mitigate 的驗收條件**：UG-G2-SB6 的三項 PIT 測試通過，
且 Universe Snapshot 可證明只使用 `effective_date` 前已知資料。

**注意**：標籤為 `PLANNED` 而非 `HYPOTHESIS`，依準則 4，
`NOT VERIFIED` 類標籤須在對應 Gate 開始前完成驗證。
本風險於 Gate 2 開工前須先確認 PIT 設計可實作。

---

## 4. SB1 驗證計畫：HERM 順序問題的處理

> **問題陳述**：SB1 的驗收依賴測試結果，但 HERM-01~09 這 9 個測試要到 SB2 才變封閉。

### 4.1 先確認實際耦合關係（不是假設）

| 事實 | 證據 |
|------|------|
| HERM 測試分布 | `test_operational_ux.py`(1)、`test_real_articles_pipeline.py`(1)、`test_ui_contracts.py`(7) |
| SB1 修改的模組 | `src/ml/time_series_split.py`、`src/transform/feature_aggregator.py` |
| 直接覆蓋 `time_series_split` 的測試檔 | `test_time_series_split.py`、`test_baseline_models.py`、`test_ml_evaluator.py`、`test_model_trainer.py` |
| 直接覆蓋 `feature_aggregator` 的測試檔 | `test_canonical_stock_id.py`、`test_db_read_semantics.py`、`test_feature_aggregator_alignment.py`、`test_nlp_checkpoint_semantics.py`、`test_nlp_resilience_e2e.py`、`test_research_features.py`、`test_thematic_feature_spillover.py`、`test_time_alignment.py` |
| **交集** | **零** —— 沒有任何 HERM 測試出現在上述 12 個檔案中 |

**關鍵機制**（決定了整個處理方式）：

```
真實路徑  _fetch_real_stock_features_from_db (data_loader.py:196)
             → FeatureAggregator.generate_daily_features()   ← 會碰到 SB1 改的程式碼

Mock 路徑  generate_mock_stock_features()
             → 完全不經過 FeatureAggregator                   ← 碰不到 SB1 改的程式碼
```

HERM 測試只在 **DB 有資料時**才走真實路徑進入 `FeatureAggregator`。

### 4.2 處理方式

**在空的臨時資料庫上執行 SB1 驗證**（沿用 GOV-02 已驗證的機制）。

在該配置下，9 個 HERM 測試因 DB 回傳空結果而走 mock 路徑，
**完全不會執行到 SB1 修改的任何程式碼**。因此：

| 分類 | 測試 | 對 SB1 的證據價值 |
|------|------|------------------|
| **A. 直接覆蓋** | 上表 12 個檔案 + SB1 新增測試 | **這是 SB1 的真正證據** |
| **B. 迴歸對照** | 其餘未觸及 SB1 模組的測試 | 證明 SB1 未造成非預期破壞 |
| **C. 無訊號** | HERM-01~09 | **零證據價值** —— 走 mock 路徑，碰不到 SB1 的程式碼 |

**驗收報告必須明確分割這三類，C 類的通過不得被計入 SB1 的驗證證據。**

### 4.3 具體執行步驟

1. **前置：實測覆蓋歸因**（不採信 §4.1 的 grep 推論）
   於 SB1 開工前，以呼叫追蹤確認「哪些測試實際執行到 `time_series_split`
   與 `feature_aggregator` 的函式」，產出實測版的 A/B/C 分類表。
   若實測結果與 §4.1 不符，**以實測為準並回報**。

2. **建立 SB1 前基線**
   於 GOV-03 釘選環境 + 空臨時 DB 執行全套測試，記錄逐測試結果作為對照基準。

3. **實作 SB1**（僅在 PO 核准後）

4. **執行 SB1 後驗證**（同一釘選環境、同一空臨時 DB）
   - A 類：逐項列出結果，這是 SB1 的驗收依據
   - B 類：與步驟 2 基線逐測試 diff，任何變化都要解釋
   - C 類：僅記錄，明確標註「零證據價值」

5. **Sentinel 防護：確認 SB1 未引入新的 DB 耦合**
   以 GOV-02 的可攔截 sentinel 執行一次，記錄 `connect()` 呼叫點。
   **呼叫點必須仍是原本那 9 處，數量與位置皆不得增加。**
   若 SB1 意外使 `feature_aggregator` 產生新的 DB 依賴，此步驟會抓到。

6. **環境揭露**
   依 `gate-submit` skill 產出五項證據，標明執行環境為 container、
   Python 版本、依賴狀態，以及臨時 DB 的綁定確認。

### 4.4 這個方案的邊界（誠實說明）

- **不修復 HERM-01~09** —— 那是 SB2 的範圍，本方案只是讓它們不污染 SB1 的證據。
- **存在覆蓋缺口**：`FeatureAggregator` 的「真實 DB 路徑」在 SB1 階段不會被測試覆蓋
  （因為空 DB 走 mock）。此缺口為既有問題（HERM-E／DRIFT-009），
  在 SB2 修復 DataMode 後才會有真實路徑的測試覆蓋。
  SB1 對 `FeatureAggregator` 的驗證僅來自 A 類的 8 個 fixture-based 測試檔。
- **不以「154/154 OK」作為 SB1 驗收結論** —— 該數字包含 C 類，
  依 `CLAUDE.md` §9.1 屬於不當外推。

### 4.5 替代方案與為何不採用

| 方案 | 不採用的原因 |
|------|-------------|
| 先做 SB2 再做 SB1 | 違反 Master Plan §5.2 依賴矩陣；SB2 的 DataMode 不依賴 SB1，但調換順序需 PO 核准變更 SB 順序，且不解決 SB1 的覆蓋缺口 |
| 在 SB1 內順手修 HERM | 違反 Small Batch 邊界；SB1 的 `Out of Scope` 明確排除 UI 相關修改 |
| 用真實 DB 跑 SB1 驗證 | 測試結果與 DB 內容耦合，不可重現（GOV-02 已證實 `assertEqual(len(df), 30)` 對 live 資料硬斷言的問題） |
| 暫時跳過那 9 個測試 | 會失去 B 類迴歸訊號，且掩蓋問題 |

---

## 5. 待辦：digest 釘選的維護義務登錄

依 PO 於 GOV-03 驗收時的指示，`REMAINING_RISKS.md` 需補一筆風險：

| 項目 | 內容 |
|------|------|
| 風險 | digest 釘選使基底映像安全性更新不再自動到來 |
| 觸發條件 | 基底映像發布安全性修補，但專案因 digest 釘選而未取得 |
| 現況 | 已記錄於 `.devcontainer/Dockerfile` 註解與 `CLAUDE.md` §13.6，但**註解不會被定期審查，風險清冊會** |

**本申請不執行此項** —— 依 PO 指示「收在 Gate 1 一併做」，
將於 Gate 1 核准後隨 UG-G1-SB5（文件校正）或獨立小批次提出。

---

## 6. 請求 PO 裁決事項

| # | 事項 | 需要的決定 |
|---|------|-----------|
| 1 | **RISK-001** 處置 | Accept／Mitigate／Defer（建議 Accept，理由見 §3.2） |
| 2 | RISK-010 處置 | 建議 Defer 至 Gate 3（§3.3） |
| 3 | RISK-012 處置 | 建議 Mitigate（§3.4） |
| 4 | **SB1 驗證計畫**（§4） | 是否認可以「A/B/C 證據分割 + 空臨時 DB + sentinel 防護」處理 HERM 順序問題 |
| 5 | Gate 1 啟動 | 是否核准；若核准，是否採「逐 SB 授權」（本申請的預設）|
| 6 | SB 執行順序 | 是否維持 SB1 → SB2 → SB3 → SB4 → SB5（Master Plan §5.2 依賴矩陣）|

---

## 7. 未獲核准前的自我約束

- 不修改 `src/`、`tests/`、`database/`
- 不修改 Master Plan 的 SB Brief 內容（§2.2 列出的調整待核准後提出）
- 不執行任何 DB migration
- 不 Commit（本申請文件除外，且需 PO 授權）
