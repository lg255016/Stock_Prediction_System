# PURGED_WALK_FORWARD_SPEC.md — 時序驗證與 Triple-Barrier 資料契約規格

> Gate 0 交付物 F
> 日期: 2026-08-22
> 狀態: READY FOR PO REVIEW

---

## 1. 問題根因

### 1.1 現況分析

**`feature_aggregator.py` L459 — shift(-1) 標籤洩漏**

```python
df_res['target_next_close'] = df_res.groupby('stock_id')['close_price'].shift(-1)
```

`shift(-1)` creates a label that depends on T+1 close price. The label for row T
(`target_up_down[T]`) encodes information about `close_price[T+1]`.

**`time_series_split.py` — 無 Purge/Embargo 切分器**

Current `WalkForwardSplitter` performs pure date-based splitting:
- Train includes all rows up to date T (inclusive)
- Test starts at date T+1

The splitter asserts `max(train_date) < min(test_date)`, but this check operates on
**trade_date** only — it does NOT account for the fact that `Train[T].label` depends on
`Test[T+1].close`.

**結論: Boundary Leakage (已驗證)**

```
Train[T].target_up_down = f(close[T+1])
Test[T+1].close = close[T+1]
→ Train label leaks Test target price at the boundary
```

This is NOT a catastrophic leak (only 1 row per fold boundary), but it violates the
strict temporal integrity contract and will compound with longer label horizons
(e.g., Triple-Barrier H=5).

---

## 2. Purge / Gap / Embargo 正式定義

### 2.1 label_end_date

每一筆訓練樣本的標籤所依賴的最遠未來日期:

```
label_end_date[T] = trade_date[T + label_horizon]
```

| 標籤類型 | label_horizon | label_end_date |
|----------|---------------|----------------|
| T+1 binary (`target_up_down`) | 1 | trade_date + 1 trading day |
| Triple-Barrier H=5 | 5 | trade_date + 5 trading days |

### 2.2 Purge

**定義:** 從訓練集中移除所有 `label_end_date >= test_start_date` 的樣本。

**目的:** 防止訓練標籤在時間上與測試特徵重疊。

```
Purged rows = { row ∈ Train | label_end_date(row) >= test_start_date }
Train_purged = Train \ Purged rows
```

**範例 (H=1):** 若 test_start_date = 2025-03-01，則 train 中 trade_date = 2025-02-28
的樣本會被 purge (因為 label_end_date = 2025-03-01 >= test_start_date)。

**範例 (H=5):** 若 test_start_date = 2025-03-01，則 train 中 trade_date 落在
2025-02-21 ~ 2025-02-28 的樣本皆被 purge (因為它們的 label_end_date >= 2025-03-01)。

### 2.3 Gap (Optional)

Train 結束與 Test 開始之間的隔離交易日。Gap 期間的資料不屬於任何集合。

```
Gap days ∉ Train ∧ Gap days ∉ Test
```

預設值: `gap_days = 0` (嚴格 Walk-Forward 不需要 Gap)。

### 2.4 Embargo

適用於交叉驗證 (Cross-Validation) 場景: 當 Test 之後的資料可能進入其他 Fold 的訓練集時，
排除 test_end_date 之後 `embargo_days` 天內的訓練候選樣本。

```
Embargoed rows = { row ∈ other_fold_Train | trade_date(row) <= test_end_date + embargo_days }
```

對於嚴格單向 Walk-Forward: `embargo_days = 0` 是合法的 (因為訓練集永遠在測試集之前，
不存在後方資料回流問題)。

### 2.5 時間單位

**所有時序參數一律使用交易日 (Trading Days)，禁止使用百分比或自然日。**

理由:
- 百分比對不同長度的資料集產生不同的實際天數，不可復現
- 自然日包含週末與假日，導致不同股市有不同的實際訓練天數
- 交易日是唯一可跨市場、跨時段一致的度量單位

### 2.6 核心斷言 (Core Assertion)

```python
assert max(train_purged.label_end_date) < min(test.trade_date), \
    "Purge violation: train label leaks into test period"
```

此斷言比現有 `max(train.trade_date) < min(test.trade_date)` 更嚴格，
它確保的是 **標籤依賴的最遠日期** (而非交易日本身) 不進入測試集。

---

## 3. Walk-Forward Configuration

### 3.1 參數定義

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `train_window_size` | int (trading days) | 60 | 訓練窗口長度 |
| `test_window_size` | int (trading days) | 20 | 測試窗口長度 |
| `step_size` | int (trading days) | = test_window_size | 每次平移步長 |
| `mode` | str | 'rolling' | 'rolling' 滾動 / 'expanding' 擴展 |
| `label_horizon` | int (trading days) | 1 | 標籤依賴的未來天數 (T+1=1, Triple-Barrier=5) |
| `embargo_days` | int (trading days) | 0 | 嚴格 WF 預設為 0 |

### 3.2 現有程式碼變更摘要

`WalkForwardSplitter` 需新增:
- `label_horizon` 參數
- Purge 邏輯: 在 `split()` 產生 `train_dates` 後，移除尾端 `label_horizon` 天
- 更新 metadata 增加 `purged_days`, `purged_samples` 欄位
- Core Assertion 從 `max(train_date) < min(test_date)` 升級為
  `max(train.label_end_date) < min(test.trade_date)`

### 3.3 最低資料需求

| 需求 | 說明 |
|------|------|
| 歷史深度 | 至少 3 年 (理想 5 年以上) |
| Holdout | 最後 6-12 個月保留為 Holdout，不參與模型選擇 |
| 最少 Fold 數 | ≥ 3 個完整 (Train, Test) 組合 |
| 最少訓練樣本 | 每 Fold purge 後仍需 ≥ min_train_size 天 |

---

## 4. Triple-Barrier Data Contract

> **PO 決策 (2026-08-22)**：標籤與實際交易必須是同一筆交易。
> 統一以 **T+1 開盤價** 作為進場價與 Barrier anchor，消除「以不可成交的 Close[T] 計算 barrier、卻以 Open[T+1] 成交」的錯配。
> 標籤採 **三分類**，不將止損與未觸線混為同一結果。

### 4.1 Entry / Price Basis (統一時間約定)

| 項目 | 定義 |
|------|------|
| Prediction time (預測時點) | T 日收盤後（Post-market，15:30 cutoff）— 模型在此時產生預測 |
| Feature cutoff (特徵截止) | 所有特徵僅使用 T 日及之前的資料 |
| **Entry price & Barrier anchor** | **T+1 日開盤價 `Open[T+1]`** — 同時作為進場成交價與 barrier 計算基準 |
| Barrier evaluation window | T+1 至 T+5 的 `High` / `Low`（含 T+1 當日）|
| Slippage | 套用於 `Open[T+1]` |
| Transaction costs | 以 `Open[T+1]`（含 slippage）為基礎計算 |

**時序流程**：

```
T 日 15:30 收盤 ──→ 特徵可用 ──→ 模型產生預測
                                      │
T+1 日 09:00 開盤 ──────────────────→ 以 Open[T+1] 進場（= barrier anchor）
                                      │
T+1 ~ T+5 逐日檢查 High/Low ─────────→ 觸線判定
                                      │
T+5 收盤仍未觸線 ────────────────────→ Timeout
```

### 4.2 Barrier Definitions

```
anchor        = Open[T+1]
Upper barrier = anchor × (1 + upper_width)
Lower barrier = anchor × (1 - lower_width)
```

| 模式 | upper_width | lower_width |
|------|-------------|-------------|
| Static (預設) | +2.0% | +1.5% |
| Dynamic (波動率調適) | 1.5 × σ_5d | 1.0 × σ_5d |

> **Note:** 所有 width 皆為正值。方向由公式處理：upper 用 `(1 + width)`，lower 用 `(1 - width)`。

其中 `σ_5d` = 截至 T 日（含）過去 5 個交易日收盤對數報酬的標準差 — 僅使用預測時點已知資料。

**Holding period H = 5 trading days**：評估區間為 T+1 至 T+5（使用交易日曆，跳過週末與假日）。

### 4.3 Label Values (三分類)

| Condition | Label | Description |
|-----------|-------|-------------|
| T+1~T+5 期間先觸及 upper barrier | **1** | 止盈 (Profit Target) |
| T+1~T+5 期間先觸及 lower barrier | **-1** | 止損 (Stop Loss) |
| T+1~T+5 期間未觸及任一 barrier | **0** | 持有期到期 (Timeout) |
| 同一日同時觸及 upper 與 lower | **NULL** | 模糊標籤 (Ambiguous) — 排除訓練 |
| 資料集最後 H 個交易日 | **NULL** | 資料不足 (Insufficient Data) |
| `Open[T+1]` 不存在（停牌、下市） | **NULL** | 無法進場 (No Entry) |

> **語意裁定（PO 2026-09-09，`UG-G3-SB1` Gate A）**：本表第 1～2 列（先觸線即定
> 1/−1）與第 5 列（資料集最後 H 個交易日一律 NULL）在「剩餘天數不足 H、但
> 那剩餘天數內已可觀察到觸線」的邊界情況下字面矛盾——本規格原文未言明優先序。
> **裁定：第 5 列優先，採字面規則**：只要 T 之後剩餘天數 < H，一律 NULL +
> `insufficient_data`，**即使剩餘天數內已觀察到觸線也不例外**。理由：「先觸即定」
> 會讓每檔股票序列尾端只可能出現 `±1` 或 `NULL`、不可能出現 `0`——觸線事件
> 可在不足 H 天內被觀察到，但「到期未觸線」這個結論必須撐滿整個 H 天窗口才能
> 下，於是尾端標籤分布會系統性偏向極端走勢（截斷偏差）。字面規則把這個偏差
> 整段消掉，且與「算不出來就是 NULL」的一貫原則同向。此裁定要求判斷順序
> 見 §4.6 —— **剩餘天數檢查必須先於價格路徑評估迴圈**，不得在迴圈內才判斷。
> **本裁定與 §4.6 的 NaN 價格處理已收錄為 ADR，見 `doc/evidence/DECISIONS.md` DEC-035
> （修訂 DEC-018）。**

> **PO 決策**：採三分類 `{1, -1, 0}` + `NULL`。
> 止損 (`-1`) 與未觸線 (`0`) 是不同的交易結果，不得合併：
> 前者是實際虧損出場，後者是持有到期以市價結算，兩者的報酬分布與風險特性不同。
> 模型訓練時可依需求映射為二元（例如 `1` vs `其他`），但**儲存層必須保留三分類原始資訊**。

**label domain**: `{-1, 0, 1, NULL}` — 此定義為 `target_triple_barrier` 欄位的唯一合法值域，
`FEATURE_REGISTRY.md` 與 Migration DDL 必須與此一致。

### 4.4 Same-Day Dual-Barrier (PO Decision)

**決策: 標記為 NULL (Ambiguous)，排除訓練。**

| 規則 | 說明 |
|------|------|
| 標記 | `label = NULL`, `label_reason = 'ambiguous_dual_barrier'` |
| 排除 | 不進入訓練集、不進入驗證集的標籤計算 |
| 禁止操作 | No forward-fill, no zero-fill, no direction assignment, no tie-breaker |
| 報告義務 | 必須在評估報告中揭露 Ambiguous ratio (見 §6) |
| 升級條件 | 若 Ambiguous ratio > 10%，開啟新決策 (考慮日內資料或調整 barrier 寬度) |

### 4.5 label_end_date for Triple-Barrier

```
label_end_date = trade_date + H trading days (using trading calendar)
```

評估區間為 T+1 至 T+H（共 H 個交易日），因此標籤所依賴的最後一筆價格資料落在 `T+H`，
`label_end_date = T+H` 正確涵蓋標籤的資訊邊界。此值直接送入 Purge 計算 (§2.2)。

**範例:** trade_date = 2025-03-10 (週一), H = 5
→ 進場日 = 2025-03-11 (週二 Open)
→ 評估區間 = 2025-03-11 ~ 2025-03-17（5 個交易日，跳過週末）
→ label_end_date = 2025-03-17 (下週一)
→ 若 test_start_date = 2025-03-14 (週五)，此樣本被 purge (2025-03-17 >= 2025-03-14)

### 4.6 Price Path Evaluation

逐日掃描演算法（**2026-09-09 修訂**：原版偽碼未言明「剩餘天數不足 H」與
「價格為 NaN」兩種邊界情形的判斷順序，`UG-G3-SB1` 綠色實作審查時發現並由
PO 裁定補齊——見下方判斷順序與 §4.3 語意裁定）:

```python
remaining_days = 資料集中 T 之後尚有幾個交易日（該股票自身序列）

# 判斷順序第一層：Open[T+1] 是否存在（該列是否存在）
if remaining_days == 0:
    label = NULL          # label_reason = 'no_entry'（序列末列，無下一筆資料）

# 判斷順序第二層：剩餘天數是否足夠撐滿整個 H 天評估窗口
# ——此檢查優先於價格路徑評估，即使剩餘天數內已可觀察到觸線也不例外
# （PO 2026-09-09 語意裁定，見 §4.3）
elif remaining_days < H:
    label = NULL          # label_reason = 'insufficient_data'

else:
    anchor = Open[T+1]

    # 判斷順序第三層：anchor 本身是否為 NaN（該列存在但價格值缺失，如 NULL 價格）
    # ——NaN 比較恆為 False，若不在此提前判斷，會落入迴圈末端被誤判為 0 (Timeout)
    # （UG-G3-SB1 審查方 2026-09-09 發現：`stock_prices` 三個價格欄皆 nullable）
    if anchor is NaN:
        label = NULL       # label_reason = 'no_entry'
    else:
        upper_barrier = anchor * (1 + upper_width)
        lower_barrier = anchor * (1 - lower_width)

        label = 0          # 預設 Timeout；迴圈觸線時覆寫

        # 評估區間含 T+1 當日（進場當日即可能觸線）
        for d in [T+1, T+2, ..., T+H]:
            high_d = High[d]
            low_d  = Low[d]

            # 判斷順序第四層：該日 High/Low 是否為 NaN——須先於觸線判定，
            # 否則僅檢查非 NaN 的那一側等同偽造一個確定結果（同上，審查方發現）
            if high_d is NaN or low_d is NaN:
                label = NULL   # label_reason = 'insufficient_data'（沿用既有 reason 值，不新增）
                break

            hit_upper = (high_d >= upper_barrier)
            hit_lower = (low_d  <= lower_barrier)

            if hit_upper and hit_lower:
                label = NULL  # Ambiguous same-day dual hit
                break
            elif hit_upper:
                label = 1     # Profit target
                break
            elif hit_lower:
                label = -1    # Stop loss
                break
        # 迴圈完成未 break → label 維持 0 (Timeout)
```

**注意事項:**
1. 使用 `High`/`Low` 而非 `Close` 判斷觸線，因為日內價格可能觸及 barrier 後收盤回彈。
2. 評估區間**包含 T+1 當日**：以開盤價進場後，當日盤中即可能觸線。
3. `Open[T+1]` 不存在時標記 `NULL`（`label_reason = 'no_entry'`），不得以 `Close[T]` 替代。
4. **判斷順序是規格的一部分，不是實作細節**：剩餘天數檢查 → anchor NaN 檢查 →
   逐日 High/Low NaN 檢查 → 觸線判定，四層依序短路，任一層命中即不下探下一層。
   顛倒順序會產生不同（且錯誤）的標籤——`UG-G3-SB1` 的
   `test_tb_insufficient_data_overrides_early_touch`、
   `test_tb_anchor_nan_is_no_entry`、`test_tb_window_nan_is_insufficient_data`
   三項測試（`tests/test_triple_barrier.py`）逐層釘死此順序。
5. `high_d`／`low_d` 為 NaN 時歸類為 `insufficient_data`（沿用既有「算不出來
   就是 NULL」原則），**不新增第四個 reason 值**，故不影響
   `chk_label_reason_domain`（migration 002）的 CHECK 值域。

---

## 5. Test Cases

### 5.1 Purge / Embargo 測試

| Test ID | 測試名稱 | 驗證目標 |
|---------|----------|----------|
| T-PW-01 | `test_purge_removes_label_overlapping_rows` | H=1 時，train 尾端 1 天被移除 |
| T-PW-02 | `test_purge_h5_removes_five_days` | H=5 時，train 尾端 5 天被移除 |
| T-PW-03 | `test_embargo_excludes_post_test_train_candidates` | embargo_days > 0 時，test 後方天數被排除 |
| T-PW-04 | `test_core_assertion_holds` | `max(train.label_end_date) < min(test.trade_date)` 恆成立 |
| T-PW-05 | `test_future_data_mutation` | 注入未來資料 → assertion 失敗或拋出異常 |

### 5.2 Triple-Barrier 測試

| Test ID | 測試名稱 | 驗證目標 |
|---------|----------|----------|
| T-TB-01 | `test_tb_upper_barrier` | T+1~T+5 先觸上障礙 → label = **1** |
| T-TB-02 | `test_tb_lower_barrier` | T+1~T+5 先觸下障礙 → label = **-1** |
| T-TB-03 | `test_tb_timeout` | H 日內未觸線 → label = **0** |
| T-TB-04 | `test_tb_ambiguous_null` | 同日觸雙線 → label = NULL |
| T-TB-05 | `test_tb_last_h_days_null` | 資料集最後 H 日 → label = NULL |
| T-TB-06 | `test_tb_label_end_date` | label_end_date = trade_date + H trading days |
| T-TB-07 | `test_tb_dynamic_barrier_uses_sigma` | dynamic mode 正確使用 σ_5d（僅 T 日前已知資料）——**`UG-G3-SB1` Out of Scope**（PO 2026-09-09 Gate A 裁決：規格有定義但 Brief 未要求，維持 Static 模式；Ambiguous ratio > 10% 時 §4.4 升級條件自動叫回）|
| T-TB-08 | `test_tb_anchor_is_next_open` | barrier anchor = `Open[T+1]`，**非** `Close[T]` |
| T-TB-09 | `test_tb_no_entry_when_open_missing` | `Open[T+1]` 不存在（停牌）→ label = NULL, reason='no_entry' |
| T-TB-10 | `test_tb_label_domain` | 所有非 NULL 標籤 ∈ `{-1, 0, 1}`；不得出現其他值 |
| T-TB-11 | `test_tb_stop_loss_distinct_from_timeout` | 止損樣本 label = -1，超時樣本 label = 0，兩者不得合併 |
| T-TB-12 | `test_tb_entry_day_hit_counted` | T+1 當日即觸線的樣本必須被正確標記（評估區間含 T+1）|
| T-TB-13 | `test_tb_label_reason_invariant` | `label_reason IS NULL ⟺ target_triple_barrier IS NOT NULL` 逐列成立（`UG-G3-SB1` Gate A 追加） |
| T-TB-14 | `test_tb_purge_boundary_with_h5` | `label_end_date_tb` 供 `WalkForwardSplitter(label_horizon=5)` 正確 purge（`UG-G3-SB1` Gate A 追加，把本節 §4.5 落地為可執行檢查）|
| T-TB-15 | `test_tb_insufficient_data_overrides_early_touch` | 剩餘天數 < H 時一律 `insufficient_data`，即使窗口內已觀察到觸線（PO 2026-09-09 語意裁定，見 §4.3）|
| T-TB-16 | `test_tb_anchor_nan_is_no_entry` | `Open[T+1]` 存在但值為 NaN → NULL, reason='no_entry'（`UG-G3-SB1` 審查方 2026-09-09 發現）|
| T-TB-17 | `test_tb_window_nan_is_insufficient_data` | 評估窗口內某日 High/Low 為 NaN → NULL, reason='insufficient_data'，且驗證 NaN 檢查先於觸線判定（同上）|

### 5.3 Integration 測試

| Test ID | 測試名稱 | 驗證目標 |
|---------|----------|----------|
| T-INT-01 | `test_purge_with_triple_barrier_pipeline` | TB labeler + Purged WF splitter 端到端正確 |
| T-INT-02 | `test_no_information_leakage_end_to_end` | 全流程不存在前視偏誤 |

---

## 6. Ambiguous Ratio Report Template

每次 Triple-Barrier 標籤生成後，必須輸出以下報告:

```
=== Triple-Barrier Label Report ===
Stock ID:          {stock_id}
Date Range:        {start_date} ~ {end_date}
Barrier Anchor:    Open[T+1]
Label Domain:      {-1, 0, 1, NULL}
Total Samples:     {total}
Labeled Samples:   {labeled}    ({labeled/total:.1%})
  - Label  1 (Profit Target): {count_pos}  ({count_pos/labeled:.1%})
  - Label -1 (Stop Loss):     {count_neg}  ({count_neg/labeled:.1%})
  - Label  0 (Timeout):       {count_zero} ({count_zero/labeled:.1%})
NULL Breakdown:    {null_total}  ({null_total/total:.1%})
  - Ambiguous (dual barrier): {ambiguous}    ({ambiguous/total:.1%})
  - Insufficient Data:        {insufficient} ({insufficient/total:.1%})
  - No Entry (停牌/下市):      {no_entry}     ({no_entry/total:.1%})

⚠ Ambiguous Ratio: {ambiguous/total:.1%}
  Threshold: 10%
  Status: {PASS / ESCALATE TO PO}

⚠ Class Balance (三分類):
  Profit : Loss : Timeout = {count_pos} : {count_neg} : {count_zero}
  若任一類別 < 5%，標記為極度不平衡並於評估報告揭露
```

**升級決策流程:**
- Ambiguous ratio ≤ 10%: 正常，記錄即可
- Ambiguous ratio > 10%: 暫停訓練，開啟 PO Decision
  - 選項 A: 引入日內 (intraday) 資料判斷觸及先後順序
  - 選項 B: 加寬 barrier (降低同日雙觸機率)
  - 選項 C: 調整 H (改變持有期)

---

## 7. Integration with Walk-Forward

### 7.1 標籤類型與 Purge 天數對應

| 標籤類型 | label_horizon | Purge 移除天數 | 說明 |
|----------|---------------|----------------|------|
| `target_up_down` (T+1 binary) | 1 | 1 天 | 現有標籤，purge 影響最小 |
| `target_triple_barrier` (H=5) | 5 | 5 天 | 新標籤，purge 影響較大 |

### 7.2 Panel Dataset 設定

Panel Dataset (多股票面板資料) 必須透過組態選擇使用哪個 target:

```yaml
# config/ml_pipeline.yaml (示意)
target:
  type: "triple_barrier"    # or "up_down"
  label_horizon: 5          # auto-derived from type
  upper_width: 0.02
  lower_width: 0.015
  holding_period: 5
  barrier_mode: "static"    # or "dynamic"
```

`label_horizon` 由 target type 自動推導，不允許手動覆寫以防止不一致。

### 7.3 Migration Path

1. **Phase 1:** 在現有 `WalkForwardSplitter` 中加入 `label_horizon` 參數與 Purge 邏輯
2. **Phase 2:** 實作 `TripleBarrierLabeler` 類別，生成 `target_triple_barrier` 欄位
3. **Phase 3:** 整合 Panel Dataset pipeline，支援 target type 切換
4. **Phase 4:** 全面啟用 Purged Walk-Forward + Triple-Barrier，廢棄裸 shift(-1) 標籤

---

## Appendix A: Current Code References

| File | Line | Issue |
|------|------|-------|
| `src/transform/feature_aggregator.py` | L459 | `shift(-1)` creates T+1 label dependency |
| `src/ml/time_series_split.py` | L155-157 | Asserts `max(train_date) < min(test_date)` but not `label_end_date` |
| `src/ml/time_series_split.py` | L24-31 | No `label_horizon`, `purge`, or `embargo` parameters |

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| Purge | 移除訓練集中標籤依賴期與測試集重疊的樣本 |
| Embargo | 排除測試集結束後一段期間的訓練候選樣本 (防止跨 Fold 洩漏) |
| Gap | Train 與 Test 之間的緩衝期，不屬於任何集合 |
| label_end_date | 標籤所依賴的最遠未來日期 |
| Triple-Barrier | 以止盈/止損/到期三重條件定義標籤的方法 |
| H | Holding period，持有期 (交易日) |
| σ_5d | 過去 5 個交易日收盤對數報酬的標準差 |
