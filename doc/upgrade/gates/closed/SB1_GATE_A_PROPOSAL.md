# UG-G1-SB1 Gate A 提案：Purged Walk-Forward 實作

> **性質**：Gate A 提案（實作前審批），非實作。
> **提交日期**：2026-08-23
> **前置**：UG-Gate-1 已由 PO 核准（逐 SB 授權）；RISK-001 已簽核 `Accept`
> **狀態**：`src/` 未動，diff 為空
>
> **2026-08-24 修正（GOV-06，PO 指示）**：本文件原將 `connect()` 靜態呼叫點寫為 **9 處**（§2.1 第 4 點、§4.3 步驟 5），
> 實測為 **10 處**（`db_writer.py` 7 + `data_loader.py` 3）。9 是 GOV-02 的 **runtime 攔截次數**，被誤植為靜態呼叫點數。
> 若照 9 當基線，步驟 5 的 sentinel 會在什麼都沒改的情況下報假警 —— **而會製造假警報的檢查遲早會被無視，
> 那比沒有檢查更糟**。兩處已更正為 10，並要求 runtime 攔截數與靜態呼叫點數分開陳述。
>
> **步驟 1 已完成**，實測結果見 `SB1_STEP1_BEFORE_SNAPSHOT.md`（含依實測重建的 A／B／C 分類與 Gate B 追加證據要求）。
> **步驟 2 已完成（2026-08-24）**，見 `DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節。
> **步驟 3 已完成（2026-08-24/25）**：`time_series_split.py` 新增 Purge/Embargo；PO 2026-08-25 獨立驗證
> 發現並要求修正「Purge 僅用全域曆近似、未讀取 `feature_aggregator` 產出的逐列 `label_end_date`」的
> 正確性問題，已修正為「df 含該欄位時逐列精確判定，缺席時才退回近似法」。
> **步驟 4、5 已完成（2026-08-25）**，見 `SB1_STEP4_AFTER_SNAPSHOT.md`。
> **步驟 6（送 Gate B）尚未開始。**

---

## 1. 本提案要解決的四件事

| # | 來源 | 內容 |
|---|------|------|
| 1 | PO 核准 Gate 1 時指示 | RISK-001 接受邊界的第二句寫進 SB1 的 `Definition of Done` |
| 2 | PO 補充要求 1 | 修正前的準確率數字必須保留並標註含洩漏，不得刪除或覆寫 |
| 3 | PO 補充要求 2 | A 類證據必須包含「修改前」的執行結果 |
| 4 | PO 同意的 Brief 調整 | 三處；其中第三項跨五個 SB，在本次一次改完 |

---

## 2. Brief 調整（提請核准後才修改 Master Plan）

### 2.1 SB1 `Definition of Done` —— 納入 RISK-001 接受邊界

**現行**：

> 所有 Fold 的 max(train.label_end_date) < min(test.trade_date); 全套測試 PASS

**提議改為**：

> 1. 所有 Fold 的 `max(train.label_end_date) < min(test.trade_date)`
> 2. **Purge 後訓練集不足 `min_train_size` 時，該 Fold 跳過並記錄警告；
>    嚴禁為了保留 Fold 而縮小 Purge 範圍或放寬 `label_end_date` 判定**
>    （RISK-001 接受邊界，PO 2026-08-23 簽核）
> 3. A 類證據（§4.2）before/after 對照完成，且每一項差異都有解釋
> 4. Sentinel 檢查通過：`connect()` **靜態呼叫點仍為 10 處**，未增加（`db_writer.py` 7 + `data_loader.py` 3；`init_db` 另 2 處，測試不觸及）
> 5. 修正前基線已保存並標註污染來源（§3）

**理由**：第 2 點是實際會發生的失敗模式 —— Purge H=5 時每個 Fold 少 5 天，
在資料量邊緣的 Fold 會不足。屆時最省事的做法就是把 Purge 調小，
那等於把洩漏放回來。寫進 DoD 才能在驗收時被檢查到。

### 2.2 SB1 `E2E Verification` —— 納入證據分割

**現行**：

> LEGACY_17 baseline + Purged WF 全流程跑通，Fold 數 ≥ 3

**提議改為**：

> 於 GOV-03 釘選環境 + 空臨時 DB 執行，並依 §4.2 分割為 A／B／C 三類證據：
> A 類（直接覆蓋）為驗收依據且須附 before/after 對照；B 類為迴歸對照；
> C 類（HERM-01~09）標註零證據價值。
> Fold 數 ≥ 3；**不得以「154/154 OK」作為 SB1 驗收結論**。

### 2.3 SB2 `In Scope` —— 明確納入 HERM 修復

**現行**：

> `data_loader.py` 回傳 `(DataFrame, DataMode)` 元組; `components.py` 各元件根據 mode 渲染; `app.py` 全局 mode 追蹤

**提議追加一句**：

> 併同修復 HERM-01~09 的測試封閉性：使該 9 個測試不再依賴環境憑證與 DB 內容
> （見 `DOCUMENT_DRIFT_REMEDIATION.md` GOV-02 章節）。

**理由**：DataMode 四狀態是機制，HERM 封閉性是該機制要達成的結果之一。
不寫進 `In Scope`，SB2 驗收時無法要求它。

### 2.4 五個 SB 的 `Tests` 欄 —— 標明執行環境（一次改完）

依 PO 指示，這是跨五個 SB 的同一件事，在 SB1 的 Gate A 一次處理。

**提議**：在 §7 Gate 1 章節開頭加入一段共用說明，而非逐 SB 重複：

> **本 Gate 所有 SB 的測試執行環境**：dev container（Python 3.14.6，
> GOV-03 釘選之 `requirements.lock.txt`），**非 host**。
> host 執行結果不得作為驗收證據（`CLAUDE.md` §13.0）。
> 涉及 DB 的驗證須指向空臨時資料庫並附綁定確認。

**理由**：五處重複同一段文字會製造下一個漂移點 —— 改一處忘一處。
集中一處，各 SB 的 `Tests` 欄保持原樣。

---

## 3. 修正前基線的保存（PO 補充要求 1）

### 3.1 先釐清這些數字實際在哪裡

| 位置 | 內容 | 型態 |
|------|------|------|
| `src/ui/components.py` | Macro F1 `0.5820`／`0.5910`、方向命中率 `58.4%`／`59.2%`、累積報酬 `+8.2%`／`+9.6%`、ΔAlpha `+4.7%`／`+5.5%` 等 8 個值 | **唯一的實際數值來源**（寫死靜態排行榜，DRIFT-008） |
| `TRACEABILITY.md:164` | 「量化證明社群情緒融合模型相較純價量控制組帶來顯著之 ΔF1 與 ΔReturn 超額報酬」 | 質性強宣稱 |
| `TRACEABILITY.md:52` | 該列標記 `VERIFIED THIS SESSION` (Phase 3 Closed) | 證據標籤 |
| `DECISIONS.md` DEC-007 | 描述協定與公式，**未宣稱具體數字** | 方法論 |

**實測確認**：`DECISIONS.md`、`PROJECT_STATUS.md`、`TRACEABILITY.md` 三份文件中
**沒有任何具體準確率數值** —— 數字只存在於 `components.py`。

### 3.2 這些數字被兩個獨立問題污染，不只一個

| 污染源 | 說明 | 修復 |
|--------|------|------|
| **邊界洩漏** | `train[T].label` 依賴 `test[T+1].close` | SB1（本批次） |
| **fallback 型別碰撞（DRIFT-015）** | host 上 `lightgbm`／`xgboost`／`random_forest` 回傳同一個 `_FallbackTreeEnsembleClassifier`，四模型競技實為兩種實作 | 需於容器內重跑（Gate 3） |

**因此標註不能只寫「含洩漏」** —— 那會低估污染程度，讓人以為修掉洩漏就能用。

### 3.3 提議的保存方式

在 `DOCUMENT_DRIFT_REMEDIATION.md` 新增一節「修正前績效基線（已污染，保留供對照）」，
內容包含：

1. `components.py` 8 個數值的**原文照錄**（含來源行號與擷取日期）
2. 兩個污染源的說明與各自的修復排程
3. 明確標註：**這些數字不得作為任何績效宣稱的依據，僅供修正前後對照**
4. `TRACEABILITY.md:164` 的質性宣稱同樣照錄並標註

**不刪除、不覆寫任何現有內容** —— 只新增保存記錄。
`components.py` 本身由 SB3 處理（DRIFT-008），SB1 不碰 `src/ui/`。

---

## 4. 驗證計畫（含 PO 補充要求 2）

### 4.1 執行環境

GOV-03 釘選環境（dev container，`requirements.lock.txt`）+ **空的臨時 PostgreSQL**
（沿用 GOV-02 機制：獨立容器、獨立 volume、不掛 `postgres-data`、不進 compose 網路、
執行前綁定確認 `current_database()` 與 `inet_server_port()`）。

### 4.2 證據三分類

| 類 | 範圍 | 驗收角色 |
|---|------|---------|
| **A. 直接覆蓋** | `test_time_series_split.py`、`test_baseline_models.py`、`test_ml_evaluator.py`、`test_model_trainer.py`（splitter）；`test_canonical_stock_id.py`、`test_db_read_semantics.py`、`test_feature_aggregator_alignment.py`、`test_nlp_checkpoint_semantics.py`、`test_nlp_resilience_e2e.py`、`test_research_features.py`、`test_thematic_feature_spillover.py`、`test_time_alignment.py`（aggregator）+ SB1 新增測試 | **SB1 的驗收依據** |
| **B. 迴歸對照** | 其餘未觸及 SB1 模組的測試 | 證明無非預期破壞 |
| **C. 零證據** | HERM-01~09（`test_operational_ux.py`、`test_real_articles_pipeline.py`、`test_ui_contracts.py`） | **不計入驗收** |

### 4.3 執行順序（PO 補充要求 2：先量再改）

```
步驟 0  實測覆蓋歸因
        以呼叫追蹤確認哪些測試「實際執行到」SB1 的兩個模組，
        產出實測版 A/B/C 分類表。
        若與 §4.2 的 grep 推論不符 → 以實測為準並回報。

步驟 1  建立 BEFORE 快照        ← PO 補充要求 2
        同一釘選環境、同一空臨時 DB，執行全套測試並記錄
        「逐測試」結果（非僅總數）。
        另記錄：Fold 數、各 Fold 的 train/test 樣本數。
        此快照是後續判斷「失敗是 SB1 造成還是本來就有」的唯一依據。

步驟 2  保存修正前績效基線（§3.3）

步驟 3  實作 SB1                 ← 僅在 PO 核准本提案後

步驟 4  建立 AFTER 快照
        同一環境、同一配置，逐測試比對步驟 1。
        A 類：逐項列出，任何 before→after 變化都要解釋
        B 類：逐測試 diff，預期為零變化
        C 類：僅記錄，標註零證據價值

步驟 5  Sentinel 防護
        以 GOV-02 可攔截 sentinel 執行一次，
        connect() **靜態呼叫點須仍為 10 處**（數量與位置皆不得增加）。
        runtime 攔截數與靜態呼叫點數必須分開陳述，不得互相代替。

步驟 6  依 gate-submit skill 產出五項證據並送 Gate B
```

### 4.4 為何 BEFORE 快照不可省略

Purge 會改變 Fold 的組成 —— 這是**預期中的行為改變**，不是 bug。
但它也可能連帶影響依賴 Fold 數的測試（如 `test_baseline_models.py`、
`test_ml_evaluator.py` 走 Walk-Forward 的部分）。

沒有 before 快照時，若步驟 4 出現失敗，無法區分：

- SB1 的實作有錯
- Purge 的預期行為改變
- 該測試在 SB1 之前就已經是脆弱的

這與 GOV-02「先量再改」是同一個道理 —— 那次若沒先量 host 基線，
就不會知道容器裡的 154/154 代表完全不同的執行路徑。

---

## 5. 文件同步範圍（含 digest 維護義務）

依 PO 指示，digest 釘選的維護義務登錄併入本 SB 的文件同步：

| 文件 | 變更 |
|------|------|
| `REMAINING_RISKS.md` | 新增一筆：digest 釘選使基底映像安全更新不再自動到來；附觸發條件與應對 |
| `DECISIONS.md` | 新增 DEC-011（Purged Walk-Forward）—— 已於 Gate 0 以 `Proposed` 寫入，本批次更新其 `Verification` 欄的實測結果 |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` | §7 Brief 調整（§2）；§13 Purged WF 規格與實作對齊 |
| `TRACEABILITY.md` | 新增 Purged WF 的追溯列；標註 §164 質性宣稱為已污染 |
| `DOCUMENT_DRIFT_REMEDIATION.md` | 新增「修正前績效基線」保存節（§3.3）；DRIFT-012 狀態更新 |

---

## 6. 範圍邊界（本 SB 不做什麼）

| 不做 | 原因 |
|------|------|
| 修改 `src/ui/` | 屬 SB2／SB3 範圍 |
| 修復 HERM-01~09 | 屬 SB2 範圍；本 SB 只確保它們不污染證據 |
| 修改 `components.py` 的靜態數字 | 屬 SB3（DRIFT-008）；本 SB 只保存不修改 |
| 實作 Triple-Barrier | 屬 UG-G3-SB1；本 SB 只提供 `label_horizon` 參數化以供其對齊 |
| 重跑 tournament 取得無污染數字 | 需 Panel Dataset，屬 Gate 3 |

---

## 7. 請求 PO 裁決

| # | 事項 |
|---|------|
| 1 | §2 的四項 Brief 調整是否核准（含第 2.4 項採「集中一處」而非逐 SB 重複） |
| 2 | §3.3 的修正前基線保存方式是否認可（特別是「標註兩個污染源」而非只標洩漏） |
| 3 | §4.3 的六步驟執行順序是否核准 |
| 4 | 是否授權進入 SB1 實作（步驟 3） |

**未獲核准前不動 `src/`。**
