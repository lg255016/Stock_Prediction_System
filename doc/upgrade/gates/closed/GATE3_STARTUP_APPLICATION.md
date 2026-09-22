# UG-Gate-3 啟動申請

> **性質**：Gate 啟動申請，非實作授權。
> **提交日期**：2026-09-09
> **提交前狀態**：`src/`／`tests/`／`database/` 未動（本次僅 `doc/upgrade/` 文件異動）
> **前置 Gate**：UG-Gate-2 已於 2026-09-06 由 PO 核准關閉（`doc/upgrade/gates/closed/GATE2_CLOSURE_REVIEW.md`）
> **准入條件覆核**：依 `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.1，UG-Gate-3 准入條件為
> 「UG-Gate-2 關閉 **+** RISK-015 情緒資料覆蓋率正式檢視」。前者已滿足；後者已於
> `PRE-G3-02`（`5bfb3b8`）完成正式檢視——`RISK-015` 由 `HYPOTHESIS` 轉 `OBSERVED`，
> 帶著四檔真實覆蓋數字（2330 86.30%／NVDA 57.23%／2382 22.60%／6488 8.33%）轉為
> Gate 3 的第一個實驗問題（D3），**准入條件兩項皆已滿足**。

---

## 1. 入口條件自檢

### 1.1 面板現況

`daily_ml_features` 已於 `PRE-G3-04`（D5）全量重算為 **3,713 列**（137→3,713，
27 倍於 Gate 3 規劃當時的現況），採 U 語意（`sentiment_mean` 等五欄空日保持
`NULL`，非填 `0.5`）。逐檔分佈：2330=987、2382=987、6488=985、NVDA=754，
對齊 `stock_prices` 逐檔列數。`sentiment_mean IS NOT NULL` 逐檔 = 2330=126、
2382=33、6488=12、NVDA=91，與 `PRE-G3-02` 量測的覆蓋天數逐檔完全相符
（兩條獨立路徑對同一批資料算出一致答案，`PRE-G3-04` R2）。

### 1.2 Gate 3 準備工作現況

| 項目 | 狀態 |
|---|---|
| `PRE-G3-01`（逐則留言時間戳全鏈 + B0/B1） | **CLOSED**（2026-09-08） |
| `PRE-G3-02`（覆蓋率門檻 D1~D5 + 量測 + RISK-015 收案） | **CLOSED**（2026-09-08） |
| `PRE-G3-03`（全量回補 + 段 A 七段 + 評分 + 匯入） | **CLOSED**（2026-09-08） |
| `PRE-G3-04`（D5 落地 + 全量重算） | **CLOSED**（2026-09-08） |
| 欠帳案 1：測試 stub 稽核 | **CLOSED**（2026-09-08） |
| 欠帳案 2：跨文件狀態一致性稽核 | **CLOSED**（2026-09-08，`gate0_contract_check.py` B13 既有盲點根治） |
| 欠帳案 3：wrap-rule 推論規則精修 | **未結案**——依 PO 2026-09-08 裁決，**排定為 Gate 3 期間平行小案，不阻擋本次啟動**（見 §7） |

`gates/` 根層現為空（第四次清空）。

### 1.3 風險登錄現況（`REMAINING_RISKS.md`，僅列與 Gate 3 開工相關者）

| 風險 | 標籤 | 是否阻擋本次啟動 |
|---|---|---|
| RISK-012（PIT Universe 存活偏誤） | `Mitigate`（延續 Gate 1/2 既有裁決，DEC-017） | 否——已緩解 |
| RISK-015（情緒覆蓋率） | `OBSERVED`，轉為 Gate 3 D3 實驗問題 | 否——這正是准入條件本身，已滿足 |
| RISK-005（150 檔 ETL 超時） | `HYPOTHESIS`，未實測 | 否，但需在本申請書內安排應對（見 §6） |
| RISK-020（暖機期填值是否偽造事件值） | `OBSERVED`，**Gate 3 啟動前必須裁決**（依既有登記字面） | **是，本申請書一併請 PO 裁決**（見 §3 附帶項） |
| RISK-022（價格基準混合） | `OBSERVED（High）`，面向（一）已部分緩解（migration 009 `source` 欄），面向（二）未動 | 否——不落在 Gate 3 SB1~SB7 的直接路徑上，但 SB7 Benchmark 階段的報酬率計算會使用到 `stock_prices`，需留意 |
| RISK-023（方向類留言特徵不受 DEC-024 保護） | `OBSERVED`，潛在非活躍 | 否——三個留言特徵目前皆無真實輸入 |
| `PROJECT_STATUS.md` §0.5 #16（`min_train_size`／embargo／fold 模式衝突） | 未解 | **是，Gate 3 啟動前必裁**（見 §3） |
| `PROJECT_STATUS.md` §0.5 #18（`model_trainer.py` 抹平 U 語意） | 未解，去處 `UG-G3-SB2` | 否——SB2 自己的範圍，非啟動阻擋項 |

---

## 2. 七個 SB（既有 Master Plan §9，本次不重寫，僅列出並核對依賴）

| SB | 名稱 | Dependency | 本申請書相關備註 |
|----|------|-----------|------------------|
| UG-G3-SB1 | Triple-Barrier Labeling | UG-G1-SB1（Purged WF） | 無額外備註 |
| UG-G3-SB2 | Panel Dataset 構建 | UG-G2-SB1 + UG-G2-SB6 + UG-G3-SB1 | **需先完成 §4 的宇宙接線**，否則面板只看得到 `entity_mapping` 現有 4 檔，看不到 `universe_snapshots` 的 150 檔排名池 |
| UG-G3-SB3 | Specialist Models | UG-G3-SB2 | D3 預測力對照（§5）建議併入本 SB 的驗證階段 |
| UG-G3-SB4 | OOF Stacking Meta-Learner | UG-G3-SB3 | 無額外備註 |
| UG-G3-SB5 | Probability Calibration | UG-G3-SB4 | 無額外備註 |
| UG-G3-SB6 | Selective Inference & Regime Gating | UG-G3-SB5 | 無額外備註 |
| UG-G3-SB7 | Performance Benchmark | UG-G3-SB6 | RISK-005 的實測時機（§6）；RISK-022 面向（二）的報酬率計算需留意 |

**建議執行順序**：維持編號順序 SB1→SB7，逐 SB 授權，與 Gate 1／2 一致。

---

## 3. `PROJECT_STATUS.md` §0.5 #16：三件事，PO 必裁（附選項與代價）

原文完整登記於 §0.5 #16，本節摘要三個決定點與已實測的代價數字，供裁決：

### 3.1 決定點 1：rolling vs expanding

| 選項 | 代價 | 證據 |
|---|---|---|
| **rolling**（§3.1 預設） | 與 `embargo_days>0` 疊加時 fold 數從 34 崩到 **2**（低於規格 §3.3 要求的 ≥3） | 實測：`embargo_days=0→34 fold`／`=1,5,10→2 fold` |
| **expanding** | fold 數在任何 `embargo_days` 下皆維持 **34**，但最後一個 fold 的訓練天數隨 embargo 遞減——`embargo=20` 時只剩 **80 天（少了 89%）**，而 `min_train_size` 檢查對此**完全沒有反應** | PM 實測：`embargo=0→719 天`／`=5→559`／`=10→399`／`=20→80` |

**這是建模決定，不是驗證守衛能替你選的**：rolling 保留「捨棄舊 regime 資料」的假設，expanding 保留「用滿全部歷史」的假設，兩者對應不同的市場穩定性假設。**需要 regime shift 影響的證據才能回答，本申請書不代為決定**——若 PO 希望，可將此列為 `UG-G3-SB2` 或 `SB3` 內的一個小型前置量測（比較兩種模式下 Specialist 模型的樣本外表現差異），而非純理論判斷。

### 3.2 決定點 2：`embargo_days`

規格 §3.2 已明文嚴格單向 Walk-Forward 下 `embargo_days=0` 合法。若選 rolling 且要
`embargo_days>0`（例如防止標籤截止日與下一 fold 訓練起點之間的資訊滲漏留一個緩衝），
需先接受 fold 數量會掉到 2 個，即低於規格自訂的 ≥3 門檻——**這代表 §3.3 的兩個判準
本身在這個組合下互相矛盾，需要 PO 決定哪一個判準讓步，或明確調整 `PURGED_WALK_FORWARD_SPEC.md`
本身**（改判準需 ADR，非本申請書可逕行決定）。

### 3.3 決定點 3：`min_train_size` 若需覆寫，覆寫成多少

僅在「選 rolling 且 `embargo_days>0`」的組合下才有意義（見 §3.1）。目前
`time_series_split.py:94` 推導值為 `max(1, train_window_size − label_horizon)`，
本身只偵測「Purge/Embargo 疊加造成的額外縮減」，不是資料量下界——**需要一個有依據
的數字，不是隨手填**。

### 3.4 附帶項：RISK-020（暖機期填值是否為事件值）

`REMAINING_RISKS.md` 登記為「Gate 3 啟動前必須裁決」的 Medium 風險——判準已給出
（PO 2026-08-31：「填的值是值域的結構中點，還是一個有語意的事件？」），關鍵輸入
（`ma20_bias_ratio` 暖機期佔比：2330／2382 各 100%、6488 76.0%、NVDA 29.7%）已於
`UG-G2-SB8` 實測。**本申請書一併請 PO 於本次核准 Gate 3 時裁決**，避免再拖到
某個 SB 內部才發現阻擋。

---

## 4. 宇宙接線設計（PO 2026-09-08 裁示方向落成設計）

### 4.1 現況（唯讀查證，非推測）

| 表 | 現況角色 | 問題 |
|---|---|---|
| `entity_mapping`（`keyword TEXT PRIMARY KEY → stock_id`） | 目前**同時**扮演兩個角色：(a) 關鍵字→股票代碼的路由；(b) **事實上定義了哪些股票會被特徵聚合看見**——`feature_aggregator.py` 的 `df_arts.merge(df_mapping[['keyword','stock_id']], ...)` 只認得 `entity_mapping` 裡有的股票。現僅 4 筆種子資料（2330／2382／6488／NVDA） | 二合一導致 `universe_snapshots` 排出的 150 檔候選池，實際上被 `entity_mapping` 的 4 筆種子資料卡死——`UG-G3-SB2` 現在若直接開工，面板仍然只看得到 4 檔 |
| `universe_snapshots`（`effective_date, stock_id → rank, included, ...`） | **已是** PIT 排名的權威來源（`UG-G2-SB6`，DEC-017），85,641 列，46 期，每期 150 檔 | 尚未被任何下游消費——`feature_aggregator`／`db_writer` 皆未讀過這張表 |
| `tracking_keywords`（`keyword → category, is_active`） | 驅動**每日爬蟲抓什麼**（`category` 分 `core_stock`／`macro`／`theme`／`ai_discovered`），支援 AI 動態探索（`trend_discover.py`）寫入新關鍵字 | 與 `entity_mapping`／`universe_snapshots` 三者目前互相獨立，沒有一個地方能回答「現在系統認定的追蹤宇宙是哪些股票」 |

### 4.2 目標設計（三層分離，PO 裁示）

```
ML 宇宙       = universe_snapshots（排名，effective_date 當期 included=TRUE 的股票）
                → 唯一供 Panel Dataset（UG-G3-SB2）與模型訓練使用
                → entity_mapping 不再是「能不能進面板」的守門員

追蹤宇宙     = ML 宇宙 ∪ AI 動態發現（tracking_keywords.category='ai_discovered'）
                ∪ 使用者自選（UI「自選」寫入的 keyword／stock_id）
                → 決定每日 ETL 實際抓取範圍與儀表板可選標的

儀表板       = 追蹤宇宙的展示層（不是獨立的第三個宇宙定義來源）
                → 讀追蹤宇宙，不直接讀 entity_mapping 或 universe_snapshots
```

`entity_mapping` **退回純路由**：只回答「這個關鍵字對應哪個 `stock_id`」，
不再隱含「這個股票在不在追蹤範圍內」——後者由追蹤宇宙（`tracking_keywords` +
`universe_snapshots` 的聯集）回答。**一個關鍵字沒有 `entity_mapping` 列，
不代表它不該被追蹤；一個股票在 `entity_mapping` 裡，也不代表它在 ML 宇宙裡**——
兩件事現在被同一張表回答，之後分開。

### 4.3 對 UG-G3-SB2 的具體影響（需併入該 SB 的 Gate A Brief 調整）

1. `feature_aggregator.py` 讀取股價/文章聚合的 join 對象，需從「`entity_mapping`
   裡有的股票」改為「`universe_snapshots` 當期 `included=TRUE` 的股票」——這是
   `UG-G3-SB2` 開工前必須先解決的資料可見度問題，不是可以順手繞過的細節。
2. `entity_mapping` 需要為 `universe_snapshots` 的候選股票**補齊路由資料**
   （目前只有 4 筆種子）——需要決定新增策略（例如以股票官方簡稱／代碼自動產生
   一筆路由，人工核對俗稱/黑話類關鍵字另案）。**此為新工作量，需估算並排入
   `UG-G3-SB2` 或獨立為其 Gate A 內一個明確子項，本申請書不預先決定要不要
   拆成獨立 SB**。
3. `tracking_keywords` 與 `universe_snapshots` 目前沒有已知的資料落差查核機制——
   若 ML 宇宙排出的股票，其對應關鍵字從未被 `tracking_keywords` 標記為
   `is_active=TRUE`，該股票實際上永遠抓不到文章，`sentiment_mean` 永遠是 U。
   **這是 Gate 3 D3 實驗（§5）能不能拿到有意義樣本的前提**，建議在 `UG-G3-SB2`
   開工前先做一次唯讀查核（`universe_snapshots` 候選股 vs `tracking_keywords`
   啟用狀態的落差清單），量小、零風險，可視為 SB2 Gate A 階段的第一步。

---

## 5. D3 預測力對照——實驗設計

依 `PRE-G3-02` D3 裁決（`5bfb3b8`）：「錨定預測力對照（有／無情緒特徵的
walk-forward 對照），與總經詞裁決同一把尺，不雙標」。

| 項目 | 設計 |
|---|---|
| 對照臂 A（無情緒特徵） | 純價量特徵（`CORE_16` 平穩化特徵 + `return_1d`／`rsi_14`／`volatility_5d`／`volatility_20d`），**必含 Logistic Regression 基準**（`UG-G3-SB7` 分類基準之一） |
| 對照臂 B（有情緒特徵） | 對照臂 A + 8 個社群情緒欄位（含 U 語意的 `NULL`） |
| 模型選擇 | **只有原生支援 `NaN` 的模型可進對照臂 B**（`5bfb3b8` §9.1 實測：`RandomForest`／`LightGBM`／`XGBoost` 接受 `NaN`；`LogisticRegression` 不接受）——**Logistic Regression 因此只出現在對照臂 A**，不得對它做額外的插補處理讓它「也能」進對照臂 B，那會混淆「模型能力差異」與「特徵有無差異」兩個變因 |
| 判準 | 對照臂 B 相對對照臂 A 的樣本外表現提升（Macro F1／Conditional Win Rate），**在 Purged Walk-Forward 下**量測，不用單一 Accuracy 宣稱（`CLAUDE.md` §7.4） |
| 執行時機 | `UG-G3-SB3`（Specialist Models）驗證階段——與該 SB 本來就要做的「各 Specialist 獨立訓練與評估」共用同一批 Fold，不另外重跑一輪 |
| 覆蓋率門檻的錨定方式 | **本實驗的結果直接回答「覆蓋率夠不夠」**——若對照臂 B 在現有覆蓋率下已有可觀察的提升，覆蓋率視為足夠；若無提升，需要先判斷是特徵無效還是覆蓋率不足才能決定是否補充資料源（`PRE-G3-02` D3 已裁決不預先訂一個先驗百分比門檻） |

---

## 6. RISK-005（150 檔 ETL 超出時間窗口）應對安排

**現況**：`UG-G2-SB7` 已把每日取價從 150 個請求降為 **2 個**（批次 API），
但 RISK-005 登記的「效能基準測試」從未在**真實 150 檔規模**下實測過
（`entity_mapping` 目前只有 4 檔，日常 ETL 從未真的跑過 150 檔的量）。

**安排**：`UG-G3-SB2` 完成 §4 的宇宙接線、`entity_mapping` 補齊路由後，
系統首次具備「真的對 150 檔跑一次完整 ETL」的條件。建議在 `UG-G3-SB7`
（Performance Benchmark）或更早的 `UG-G3-SB2` 收尾階段，安排一次**唯讀
計時**的批次 ETL 執行，量測實際耗時是否超出 5 分鐘門檻（`REMAINING_RISKS.md`
RISK-005 現有判準），量測結果據以決定 RISK-005 轉 `OBSERVED` 後的最終標籤
（Accept／Mitigate）。**本申請書不預先假設會不會超時**。

---

## 7. wrap-rule 精修案——排定為 Gate 3 期間平行小案

依 PO 2026-09-08 裁決：不阻擋 Gate 3 啟動，理由——拒寫資料**不進面板**
（誠實缺席，U 語意已保護此性質），精修的收益是「找回 13 篇拒寫中因 wrap-rule
規則不夠精細而被拒的部分」，量級不影響 Gate 3 的設計本身。

| 項目 | 內容 |
|---|---|
| 範圍 | 6 個子形狀（`PRE-G3-01`／`03` 已界定）+ 段 5「跨文章相同推文序列」待查成因 + 該查明所需的請求預算（2 個） |
| 排程 | **Gate 3 期間的平行小案**，與 `UG-G3-SB1~SB7` 的任一 SB 皆無依賴關係，可在 Gate 3 執行期間任何空檔啟動，不需要排在特定 SB 之前或之後 |
| 收益若完成 | 找回部分因規則不精細而被拒寫的文章，增加 `market_articles` 樣本量，**不改變 Gate 3 任何 SB 的設計**（面板結構、模型訓練邏輯皆不受影響，只是覆蓋率的分子可能略增） |

---

## 8. 請求 PO 裁決事項

| # | 事項 | 需要的決定 |
|---|------|-----------|
| 1 | Gate 3 啟動 | 是否核准；若核准，是否採「逐 SB 授權」（本申請的預設，與 Gate 1／2 相同） |
| 2 | §3 決定點 1：rolling vs expanding | 直接裁決，或授權在 `UG-G3-SB2`／`SB3` 內先做小型前置量測再裁決 |
| 3 | §3 決定點 2：`embargo_days` | 0（嚴格單向 WF）或某個 >0 值（需接受 fold 數量代價） |
| 4 | §3 決定點 3：`min_train_size` 覆寫值 | 僅在決定點 1／2 選 rolling+embargo>0 時才需要；若選 embargo=0 或 expanding，本項可略過 |
| 5 | §3.4 附帶項：RISK-020 | Accept／Mitigate（依「結構中點 vs 事件」判準） |
| 6 | §4 宇宙接線設計 | 是否核准三層分離設計；`entity_mapping` 補齊路由的工作量是否併入 `UG-G3-SB2`、還是拆獨立 SB |
| 7 | §5 D3 實驗設計 | 是否核准；是否同意執行時機併入 `UG-G3-SB3` |
| 8 | §6 RISK-005 應對安排 | 是否核准唯讀計時安排；執行時機 `UG-G3-SB2` 收尾 或 `UG-G3-SB7` |
| 9 | §7 wrap-rule 精修案 | 確認排定為 Gate 3 期間平行小案（PO 已於前次訊息裁決，本項為書面確認） |

---

## 9. 未獲核准前的自我約束

- 不修改 `src/`、`tests/`、`database/`
- 不修改 `SYSTEM_UPGRADE_MASTER_PLAN.md` 各 SB 的既有 Brief 內容（§4 的宇宙接線
  調整待核准後，於 `UG-G3-SB2` 自己的 Gate A 階段正式納入 Brief）
- 不執行任何 DB migration 或資料寫入
- 不 Commit（本申請文件除外，且需 PO 授權）

---

## 10. PO 裁決（2026-09-09，九項全文）

> 本節逐字保留 PO 對 §8 九項請求的裁決，作為本 Gate 啟動的權威授權紀錄。
> 依 `CLAUDE.md` §16.3 規則 5，本申請書留根層至 Gate 3 正式關閉才移入 `closed/`，
> 本節隨文件一併保留，不另外摘要改寫。

### 〇、總裁決

**Gate 3 啟動核准，採逐 SB 授權**（同 Gate 1／2：每個 SB 仍走 Gate A 送審 → 核准 → 實作 → Gate B）。
申請書品質記一筆：§5 那句「不得對 LR 做額外插補讓它也能進對照臂 B ——
那會混淆模型能力差異與特徵有無差異兩個變因」**是對照實驗該有的變因隔離意識，保持。**

### 一、九項裁決

| # | 事項 | 裁決 |
|---|------|------|
| 1 | Gate 3 啟動 | **核准，逐 SB 授權** |
| 2 | rolling vs expanding | **暫維持規格預設 rolling**；兩模式對照**列為 `UG-G3-SB3` 內的實測子實驗**（同一批 fold 順帶比較，不另跑一輪）——「需要 regime shift 的證據才能回答」成立，**那就去量，不理論裁** |
| 3 | `embargo_days` | **= 0**（規格 §3.2 明文合法）。⚠ **附失效條件**：本裁決成立於**現行 1 天標籤視野**；若 Gate 3 改用多天視野標籤（如 `target_triple_barrier` 的多日設定），purge 算術整組改變，**本裁決自動失效、須重議** —— 這句原文寫進裁決記錄，不要讓它變成下一顆過期釘子 |
| 4 | `min_train_size` 覆寫 | **不裁 —— 條件未觸發**（#2 rolling + #3 = 0 之下公式推導值 59 照舊）。正式記「條件未觸發，不填」，**不是「已解決」** |
| 5 | RISK-020 | **緩裁** —— ⚠ 申請書引用的暖機佔比（2330/2382 = 100% 等）是 **137 列舊面板**的量測；新面板 987 天序列的 ma20 暖機僅約 2%，**利害關係已完全不同**。**先用 3,713 列面板重量一次（唯讀），數字連同你的建議送回來再裁** —— 不拿過期輸入做決定 |
| 6 | 宇宙接線 | **核准三層分離設計**（ML 宇宙 = `universe_snapshots`／追蹤宇宙 = 排名 ∪ AI ∪ 自選／儀表板 = 展示層；`entity_mapping` 退回純路由）。**路由補齊併入 `UG-G3-SB2` 為明確子項**，不拆獨立 SB；**§4.3 第 3 點的落差查核（宇宙股 vs `tracking_keywords` 啟用狀態）為 SB2 Gate A 第一步**，唯讀 |
| 7 | D3 實驗設計 | **核准**，執行時機併入 `UG-G3-SB3` 核准 |
| 8 | RISK-005 | **核准唯讀計時，排在 `UG-G3-SB2` 收尾**（不等 SB7 —— 早量早知道，若真超時，影響的是後面所有 SB 的排程） |
| 9 | wrap-rule 平行小案 | **書面確認**（照 §7 排定） |

### 二、#3 的裁決理由（存檔用，PM 收錄進裁決索引）

purge 已移除可證明的機械洩漏（標籤伸進測試區）；embargo 加保的是自相關滲漏，
對日線資料、1 天視野屬溫和風險。而 embargo=1 就使可用訓練天數 58 < `min_train_size` 59，
**34 折崩到 2 折** —— 代價與收益完全不成比例。**可逆性**：SB3 洩漏診斷若顯示
折邊界表現異常（滲漏症狀），屆時帶證據開 ADR —— **那時是有依據的決定，現在是憑感覺的決定。**

### 三、一個要寫進 SB2 Gate A 的誠實後果

**150 檔宇宙接上後，關鍵字只有 26 個** —— 絕大多數股票的情緒欄將長期為 U。
這在 D3 框架下合法（空日可訓練），但要說出來：
**情緒對照臂實質上只在少數有覆蓋的標的上被檢驗** —— §4.3 第 3 點的落差查核
就是把這件事量成數字的那一步，其結果要作為 D3 實驗的範圍聲明收進 SB3。

### 四、啟動後的順序

1. `PROJECT_STATUS.md` §0.2 登記 Gate 3 啟動（真實 hash）；申請書照 §16.3 規則 5
   留根層（Gate 3 關閉時才移 `closed/`）
2. **`UG-G3-SB1`（Triple-Barrier Labeling）Gate A 提案** —— 照申請書 §2 的依賴序
   SB1→SB7，SB2 的 Panel 需要 SB1 的標籤
3. ⚠ **SB1 的 Gate A 必須明確宣告標籤視野（label horizon）** ——
   若 triple-barrier 採**多日視野**，本文件 #3 的失效條件**立即觸發**：
   embargo=0 裁決失效、purge 算術重算、`min_train_size` 連動重議。
   **這不是日後的事，SB1 就是那個「日後」。** 提案裡直接把這組連動的重議方案帶上來
4. §四.6 的宇宙接線、落差查核、RISK-020 重量測照裁決併入 **SB2** 的 Gate A（輪到時）；
   RISK-020 的重量測若先做完（唯讀），隨任一輪回報附上即可
5. wrap-rule 平行小案自行擇空檔啟動

**SB1 Gate A 見。**
