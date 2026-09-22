# UG-G3-SB1 Gate A 提案：Triple-Barrier Labeling

> **性質**：Gate A 規劃提案，非實作授權。Plan-Before-Code——本提案未修改 `src/`／`tests/`／`database/`。
> **提交日期**：2026-09-09
> **前置**：UG-Gate-3 已於 2026-09-09 由 PO 核准啟動（逐 SB 授權），見
> `doc/upgrade/gates/GATE3_STARTUP_APPLICATION.md` §10。
> **依賴**：`UG-G1-SB1`（Purged Walk-Forward，`WalkForwardSplitter` 已存在且支援
> `label_horizon`／`embargo_days` 參數）。

---

## 0. 摘要

本 SB 實作 `target_triple_barrier` 三分類標籤（`{-1, 0, 1, NULL}`），規格已於 Gate 0
核准（DEC-018、`PURGED_WALK_FORWARD_SPEC.md` §4）。**本提案的核心不是標籤演算法本身
（已核准、無爭議），而是履行 PO 2026-09-09 裁決③附帶的失效條件**：Triple-Barrier
採 **H=5**（5 個交易日視野），與現行 `target_up_down` 的 H=1 不同——這在字面上立即
觸發「`embargo_days=0` 核准僅成立於現行 1 天標籤視野」的失效條款。§3 用真實
`WalkForwardSplitter`（非新寫模擬）唯讀重新量測 H=5 下的 purge／embargo／
`min_train_size` 連動，供 PO 於本 Gate A 一併重議或重新確認。

---

## 1. Requirement Source

| 來源 | 內容 |
|---|---|
| DEC-018（Gate 0，`APPROVED`） | Triple-Barrier 三分類標籤、`Open[T+1]` Anchor、Ambiguous=NULL |
| `PURGED_WALK_FORWARD_SPEC.md` §4 | Entry/Price Basis、Barrier 定義、Label Values 六種情形的完整規格 |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB1 Brief | Goal／Dependency／In-Out Scope／Affected Components／Tests／DoD（核心欄位，本提案予以完整化） |
| `FEATURE_REGISTRY.md` §29（`target_triple_barrier`）、第 6 項（`label_reason`） | 欄位契約，狀態皆為 `PLANNED` |
| `GATE3_STARTUP_APPLICATION.md` §10 裁決③④、四.3 | 本提案存在的直接原因——標籤視野宣告觸發的連動重議 |

---

## 2. Current State（唯讀查證，非推測）

### 2.1 Schema 現況

`database/migrations/002_expand_ml_features.sql` 已建立：

- `target_triple_barrier INTEGER`，`CHECK (target_triple_barrier IS NULL OR target_triple_barrier IN (-1, 0, 1))`
- `label_reason TEXT`，`CHECK` 值域 `{'ambiguous_dual_barrier', 'insufficient_data', 'no_entry'}` 或 `NULL`
- 不變式 `CHECK`：`label_reason IS NULL ⟺ target_triple_barrier IS NOT NULL`（尚未計算時兩者皆 `NULL`，此為第三態）

**兩欄皆已存在於真實庫，皆為 `NULL`**（`SELECT COUNT(*) FROM daily_ml_features WHERE target_triple_barrier IS NOT NULL` = 0，`VERIFIED THIS SESSION`，唯讀）。**本 SB 不需新增 migration**，只需寫入邏輯。

### 2.2 `src/ml/time_series_split.py`（`WalkForwardSplitter`）現況

已支援 `label_horizon`（預設 1）、`embargo_days`（預設 0）、`min_train_size`
（未傳入時預設 `max(1, train_window_size - label_horizon)`）。Purge 邏輯優先採用
df 逐列的 `label_end_date` 欄位，該欄不存在時才退回全域索引反推近似值
（`split()` docstring 明載精度限制）。**本檔本次不需修改**——它已經是為
可變 `label_horizon` 設計的。

### 2.3 `src/transform/feature_aggregator.py::generate_target_labels()` 現況

現有函式（`:864-907`）以 `label_horizon` 參數計算 `label_end_date`
（`groupby('stock_id')['trade_date'].shift(-label_horizon)`），**但 `target_up_down`
本身的定義寫死為 T+1**（docstring 原文：「以 T+1 交易日收盤表現為基準，與
`label_horizon` 參數無關，恆為 T+1」）。**這是本提案 §6.1 要處理的設計缺口**：
現行函式把「`label_end_date` 的視野」與「`target_up_down` 的實際視野」耦合成
單一參數，但兩者現在會不一致（Triple-Barrier 用 H=5，`target_up_down` 仍是 H=1）。

### 2.4 尚無 Triple-Barrier 標籤生成邏輯

`src/ml/` 下無 `triple_barrier.py` 或同義模組；`src/transform/feature_aggregator.py`
未含任何 barrier／anchor／holding period 邏輯。`grep` 全庫確認零命中（`VERIFIED THIS SESSION`）。

---

## 3. 標籤視野宣告與 embargo／purge／`min_train_size` 連動重議【核心，PO 指定必要】

### 3.1 宣告

依 `PURGED_WALK_FORWARD_SPEC.md` §4.2「Holding period H = 5 trading days（評估區間 T+1 至 T+5）」，
**本 SB 的 `target_triple_barrier` 標籤視野 = 5 個交易日**（`label_horizon = 5`），
與現行 `target_up_down` 的 `label_horizon = 1` 不同。

**依 `GATE3_STARTUP_APPLICATION.md` §10 裁決③原文**：「若 Gate 3 改用多天視野標籤
（如 `target_triple_barrier` 的多日設定），purge 算術整組改變，本裁決自動失效、須重議」——
**本節即該重議**。

### 3.2 唯讀重新量測（真實 `WalkForwardSplitter`，非新寫模擬邏輯）

沿用 Gate 3 啟動申請書 §3 使用的同一顆 `WalkForwardSplitter`，僅將 `label_horizon`
由 1 改為 5，其餘參數（`train_window_size=60`、`test_window_size=20`、
`step_size=20`）不變。**日期索引為 `pandas.bdate_range` 合成的工作日序列**，
長度對齊 `daily_ml_features` 各檔實際列數（2330/2382=987、6488=985、NVDA=754）——
**本量測只需要正確的列數與嚴格遞增的日期序列，不需要真實交易日曆或任何標籤值本身**，
故純屬唯讀、不涉及資料庫、不涉及 Triple-Barrier 演算法實作。指令與結果如下：

```python
from src.ml.time_series_split import WalkForwardSplitter
import pandas as pd
df = pd.DataFrame({"trade_date": pd.bdate_range("2022-01-01", periods=754)})  # NVDA，最短序列
for H in (1, 5):
    for mode in ("rolling", "expanding"):
        for emb in (0, 1, 5, 10, 20):
            s = WalkForwardSplitter(train_window_size=60, test_window_size=20,
                                     mode=mode, label_horizon=H, embargo_days=emb)
            folds = list(s.split(df))
            # 記錄 len(folds)、最後一個 fold 的訓練列數
```

**結果（`VERIFIED THIS SESSION`，四檔股票列數皆已測，此處列 NVDA 754 列與
2330/2382/6488 987/985 列兩組代表值）**：

| 股票（列數） | H | mode | `min_train_size` 預設 | `embargo=0` | `embargo=1/5/10/20` |
|---|---|---|---|---|---|
| NVDA (754) | 1 | rolling | 59 | 34 fold，末 fold 訓練列數 59 | **2 fold**（訓練列數皆 59） |
| NVDA (754) | **5** | rolling | **55** | **34 fold（不變）**，末 fold 訓練列數 55 | **2 fold（不變）**（訓練列數皆 55） |
| NVDA (754) | 1 | expanding | 59 | 34 fold，末 fold 訓練列數 719 | 34 fold；末 fold 訓練列數隨 embargo 遞減至 80（emb=20） |
| NVDA (754) | **5** | expanding | **55** | **34 fold（不變）**，末 fold 訓練列數 **715**（**−4，−0.6%**） | 34 fold（不變）；末 fold 訓練列數遞減至 80（emb=20，與 H=1 相同——已觸底） |
| 2330/2382 (987) | 1→5 | rolling | 59→55 | 46 fold（不變） | 2 fold（不變） |
| 6488 (985) | 1→5 | rolling | 59→55 | 46 fold（不變） | 2 fold（不變） |

### 3.3 結論（誠實揭露，非事先假設的驗證）

**H=1 → H=5 對 fold 數量與崩潰模式（rolling+embargo>0 崩到 2 fold）沒有任何影響**——
兩者完全相同。唯一的實測差異是：

1. `min_train_size` 預設值機械性下降 4（`max(1, 60−label_horizon)`：59→55），
   這是既有公式的直接推論，非新發現。
2. **【2026-09-09 訂正】** `expanding` 模式下，**除 `embargo=20` 外，各 embargo 值的
   末 fold 訓練列數皆一致減少 4 天**（H=1→H=5）：`embargo=0` 719→715、`embargo=1`
   687→683、`embargo=5` 559→555、`embargo=10` 399→395；只有 `embargo=20` 因已被
   embargo 本身壓到相同的 80 列下限而無差異（80→80）。**原稿誤寫為「其餘 embargo
   值下的末 fold 訓練列數與 H=1 完全相同」——這是結論文字的錯誤，§3.2 表格本身
   （第 4 列）數字是對的。此錯誤的方向恰好讓 H=5 顯得比實測更無害，經審查方
   獨立重跑抓出，特此訂正**：正確結論是「除已觸底的 emb=20 外，各 embargo 值
   下末 fold 訓練列數皆穩定減少 4 天（−0.6%~−1.0%），量級一致，不影響 §3.4
   的裁決方向」。

**這與 Gate 3 啟動裁決③原先預期的「purge 算術整組改變」規模不符**——實測顯示
在 `train_window_size=60` 的量級下，`label_horizon` 從 1 增至 5 只造成個位數天數的
邊際影響，不是質變。**理論上的疑慮**（H=5 標籤視野更長，測試窗結束後緊鄰的下一
fold 訓練起點，是否有更高的自相關滲漏風險）**本量測無法回答**——它是統計性質，
不是排程算術，PO 2026-09-09 裁決②的原文已將此類疑慮明確指派給
「`UG-G3-SB3` 洩漏診斷，屆時帶證據開 ADR」，本提案不越權代答。

### 3.4 提案建議（非裁決，供 PO 參考）

依上述量測，**`embargo_days=0` 在 H=5 下的機械代價與 H=1 幾乎相同**（fold 數不變，
末 fold 訓練列數差異 <1%），**沒有出現「須重議」原本預期的規模**。建議：

- **`embargo_days` 維持 0**——重議的結論與原裁決一致，非推翻，但依裁決③的文字
  要求，**仍需 PO 就 H=5 的事實重新確認**，不視為自動延續。
- **`min_train_size` 隨公式自動下修為 55**（H=5 下的 `max(1, 60−5)`），
  不需另外覆寫，維持 `GATE3_STARTUP_APPLICATION.md` §10 裁決④「條件未觸發」的結論。
- rolling vs expanding 仍依裁決②，暫維持 rolling，兩模式對照留待 `UG-G3-SB3`。

---

## 4. In Scope

- `src/ml/triple_barrier.py`（新建）：Triple-Barrier 標籤生成器，實作
  `PURGED_WALK_FORWARD_SPEC.md` §4 全部六種 Label Values 情形
- Anchor = `Open[T+1]`；評估區間 T+1~T+5（`High`/`Low`）；Static 模式
  `upper=+2.0%`／`lower=+1.5%`（Dynamic 模式此 SB 暫不實作，見 §5 Out of Scope）
- `label_end_date` 的歸屬問題（見 §6.1）
- `label_reason` 寫入（`ambiguous_dual_barrier`／`insufficient_data`／`no_entry`）
- Ambiguous 比例與三分類分布報告（Gate B 必附）
- §3 的 embargo／purge／`min_train_size` 連動重議（本提案已完成量測，待 PO 裁決）

## 5. Out of Scope（明確排除，不在本輪動）

- Dynamic barrier 模式（`1.5σ_5d`／`1.0σ_5d`）——規格已定義但 Master Plan Brief
  未要求本 SB 實作，維持 Static 模式；動態模式若需要另案評估
- Panel Dataset 構建（`UG-G3-SB2`）
- 模型訓練與消費端（`UG-G3-SB2`／`SB3`，含 §0.5 #18 `model_trainer.py` 的
  `fillna(0.5)` 抹平問題——該問題與 U 語意有關，非本 SB 範圍）
- `UG-G3-SB3` 的洩漏診斷與 rolling/expanding 對照實驗
- RISK-022（價格基準混合）——`Open[T+1]` 取自 `stock_prices`，該表既有的
  基準混合問題（面向二）不在本 SB 處理範圍，但 §8 會標注為已知風險傳導

---

## 6. 設計

### 6.1 `label_end_date` 歸屬問題（新發現，需 PO 決定）

現行 `generate_target_labels(df, label_horizon=1)` 產出的 `label_end_date`
綁定單一 `label_horizon` 值，對應 `target_up_down`（H=1）。Triple-Barrier
標籤（H=5）需要**自己的** `label_end_date`（T+5），兩者不能共用同一欄——
若面板同時保留 `target_up_down` 與 `target_triple_barrier` 兩個目標（供
D3 對照或未來切換使用），`WalkForwardSplitter` 的 purge 判定必須知道
「現在訓練的是哪一個目標」才能選對 `label_end_date`。

**三個選項**：

| 選項 | 做法 | 代價 |
|---|---|---|
| A：新增獨立欄位 | `label_end_date` 保留 H=1（既有行為不變），Triple-Barrier 另建 `label_end_date_tb`（H=5） | 兩欄並存，`WalkForwardSplitter` 呼叫端需自行選擇正確欄位傳入；不動既有欄位語意，風險最低 |
| B：`label_end_date` 語意改為「隨面板實際使用的目標而定」 | 面板構建時（`UG-G3-SB2`）依訓練目標動態計算 | 語意隨用途變動，需在 `FEATURE_REGISTRY.md` 明確警示，複雜度轉嫁給 SB2 |
| C：`label_end_date` 一律取兩者較大值（H=5） | 對 `target_up_down` 訓練也使用 H=5 的 purge 邊界 | Purge 範圍過度保守（H=1 任務被迫承擔 H=5 的邊界代價），但單一欄位、實作最簡單 |

**本提案傾向選項 A**（新增 `label_end_date_tb`，不動既有欄位），理由：
`target_up_down` 是既有、已有下游消費者（`UG-G1-SB1` 起即用於 Purged WF 驗證）的
欄位，選項 B／C 都會改變其既有語意或邊界行為，屬 §12.2 意義上的 scope 擴張，
未經授權不應動。**此為 §12 待 PO 裁決事項之一**，非本提案逕行決定。

### 6.2 Triple-Barrier 演算法設計（依規格 §4，逐條對應）

| 規格條文 | 實作對應 |
|---|---|
| §4.1 Entry/Price Basis | `anchor = Open[T+1]`；讀取 `stock_prices` 的 `open_price` 欄，`T+1` 依個股自身交易日序列（非全域對齊，同 `generate_target_labels` 既有作法） |
| §4.2 Barrier Definitions（Static） | `upper = anchor × 1.02`；`lower = anchor × 0.985`；評估區間 `High`/`Low`，T+1 至 T+5（含 T+1，交易日曆，跳過假日——依賴既有交易日序列，非自然日） |
| §4.3 Label Values | 六種情形逐一實作：先觸 upper→`1`；先觸 lower→`-1`；區間內未觸→`0`；同日雙觸→`NULL`+`label_reason='ambiguous_dual_barrier'`；資料集末 H 日→`NULL`+`'insufficient_data'`；`Open[T+1]` 不存在（停牌/下市）→`NULL`+`'no_entry'` |
| 不變式 | `label_reason IS NULL ⟺ target_triple_barrier IS NOT NULL`（既有 DB CHECK 已強制，實作邏輯需與之一致，測試須覆蓋） |

---

## 7. Failure Semantics & Tests

| 測試（Master Plan Brief 既列，本提案不重複發明） | 對應規格情形 |
|---|---|
| `test_tb_upper_barrier` | Label=1 |
| `test_tb_lower_barrier` | Label=-1 |
| `test_tb_timeout` | Label=0 |
| `test_tb_ambiguous_null` | 同日雙觸→NULL |
| `test_tb_last_h_days_null` | 末 H 日資料不足→NULL |
| `test_tb_label_end_date` | `label_end_date`（或 `label_end_date_tb`，依 §6.1 裁決）正確性 |
| `test_tb_anchor_is_next_open` | Anchor 確為 `Open[T+1]`，非 `Close[T]` |
| `test_tb_no_entry_when_open_missing` | 停牌/下市→NULL+`no_entry` |
| `test_tb_label_domain` | 值域僅 `{-1,0,1,NULL}`，無其他值 |
| `test_tb_stop_loss_distinct_from_timeout` | `-1` 與 `0` 不得合併判定 |
| `test_tb_entry_day_hit_counted` | T+1 當日觸線需計入（§4.2「含 T+1 當日」） |

**新增測試（本提案追加，Brief 原列未涵蓋）**：

- `test_tb_label_reason_invariant`：`label_reason IS NULL ⟺ target_triple_barrier IS NOT NULL` 逐列成立
- `test_tb_purge_boundary_with_h5`：`WalkForwardSplitter(label_horizon=5)` 對含
  Triple-Barrier `label_end_date` 的 df 正確 purge（對應 spec §2.2 H=5 範例：
  `test_start_date=2025-03-01` 時，`trade_date` 落在 `2025-02-21~2025-02-28`
  皆應被 purge）——**這是 §3 重議結論落地為可執行測試的地方，不能只停留在
  Gate A 文件的量測**

---

## 8. Risks & Trade-offs

| 風險 | 說明 |
|---|---|
| Ambiguous 比例未知 | 台股 `+2.0%/−1.5%` 靜態寬度下同日雙觸的實際比例本 SB 前未實測，Gate B 需附真實分布報告，若比例異常偏高需回頭檢視寬度設定是否合理（非本提案預先假設會發生） |
| RISK-022 面向（二）傳導 | Anchor 取自 `stock_prices.open_price`，該表除權息基準未還原的風險（RISK-022 面向二）會直接影響 barrier 觸發判定的正確性——本 SB 不修 RISK-022，但 Gate B 報告需誠實揭露這條傳導路徑，不得略過 |
| §6.1 `label_end_date` 歸屬未決 | 若 PO 選 B 或 C，`WalkForwardSplitter` 呼叫端或既有 `target_up_down` 的既有行為會受影響，需追加設計工作，本提案已列選項但不預先假設會選 A |
| §3 重議的「理論疑慮未答」 | 自相關滲漏疑慮延後至 `UG-G3-SB3`，本 SB 若被誤讀為「已充分驗證 embargo=0 安全」則構成過度宣稱——Gate B 報告必須明確重申此點未答 |

---

## 9. E2E Verification Plan

- 容器內全套測試 `python -m unittest discover -s tests -p "test_*.py"`
- `python scripts/verify/gate0_contract_check.py`（`FEATURE_REGISTRY.md` §29／第 6 項
  狀態由 `PLANNED` 改為已實作後，B 系列反查測試需重跑確認欄位存在性與值域一致）
- 隔離拋棄式容器對真實庫欄位子集（`target_triple_barrier`／`label_reason`）
  做 E2E 寫入驗證，比照 `PRE-G3-04` 的 RISK-013 三項協議（binding confirmation +
  `pg_dump` + 實際還原驗證），**非直接寫入 `postgres`@`localhost:5432`**
- Ambiguous／分布報告：以真實庫 3,713 列價格資料唯讀試算（不寫入），附四檔逐檔分布

## 10. Documentation Sync

依 `evidence-sync` skill 傳播清單：

- `FEATURE_REGISTRY.md` §29、第 6 項：狀態 `PLANNED` → 已實作（含真實測試斷言）
- `TRACEABILITY.md` §3.2：DEC-018 索引補上「已實作於 `UG-G3-SB1`」
- `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB1 Brief：由核心欄位補為完整 Brief
  （本提案內容即補齊依據）
- 若 §6.1 裁決為選項 A：`PURGED_WALK_FORWARD_SPEC.md` 需補充「`label_end_date_tb`
  與 `label_end_date` 並存」的說明，避免下一個讀者以為只有一個 label_end_date 欄位

## 11. Definition of Done

**【2026-09-09 補答，PO 要求釐清】真實庫的標籤寫入排在哪一步**：**排在本 SB（SB1）
自己的 Gate B**，不留到 `UG-G3-SB2`。理由：`target_triple_barrier`／`label_reason`
是 SB1 貢獻的欄位（схема 已於 migration 002 就位），比照本專案既有慣例——每個 SB
在自己的 Gate B 把自己負責的欄位寫入真實庫（`UG-G2-SB1` 的 29 欄、`SB3` 的
`market_articles`、`SB4` 的留言衍生特徵、`PRE-G3-04` 的 D5 全量重算皆是同一模式，
無一延後給下一個 SB）。`UG-G3-SB2`（Panel Dataset 構建）的角色是**讀取**已存在的
欄位組成面板，不是**代寫**上一個 SB 尚未完成的欄位。因此下表新增第 6 項，走
`PRE-G3-04` 已驗證過的 RISK-013 三項協議（binding confirmation + `pg_dump` +
實際還原驗證），**必須在 `UG-G3-SB2` Panel 凍結之前完成**（PO 2026-09-09，同
RISK-020 平行小案的時限要求同一句話——面板一旦凍結，任何欄位缺漏都會是下一次
全量重算，不是補一筆）。

| # | 項目 | 目標資料庫（`gate-submit` 產出 7） |
|---|---|---|
| 1 | `src/ml/triple_barrier.py` 建立，§7 全部測試 PASS | 不涉及資料庫（純函式邏輯） |
| 2 | `target_triple_barrier`／`label_reason` 於隔離拋棄式容器寫入驗證通過 | **已完成**（2026-09-09）：拋棄式容器 `ug_g3_sb1_tb_write_tmpdb`（非 `postgres-data` 掛載），驗證後已拆除（容器+匿名卷皆確認移除）。見 `doc/upgrade/gates/evidence/UG_G3_SB1_disposable_write_validation.json`：`float64`→`Int64`→INTEGER 轉型正確寫入；三個 DB CHECK 約束逐一 known-FAIL 驗證（不變式、target 值域、reason 值域皆正確拒絕違規寫入）+ 合法對照組正常寫入；對真實開發庫零觸碰查證（唯讀 `SELECT`，`target_triple_barrier` 非 NULL 計數與測試用 stock_id 皆為 0） |
| 3 | Ambiguous 比例與三分類分布報告完成（四檔逐檔） | **已完成**（2026-09-09）：唯讀試算於 `postgres`@`localhost:5432`，不寫入，見 `doc/upgrade/gates/evidence/UG_G3_SB1_ambiguous_ratio_report.json`。四檔 Ambiguous ratio 皆 <10%（2330 0.7%／2382 4.2%／6488 6.1%／NVDA 7.3%），未觸發 §4.4 升級條件；真實資料恰含 1 筆 NULL 價格列（NVDA 2026-06-04），命中 `874b3bf` 修復的 anchor-NaN 路徑，非人為構造 |
| 4 | §3 embargo／purge／`min_train_size` 重議已附 PO 裁決 | 不涉及資料庫 |
| 5 | §6.1 `label_end_date` 歸屬已由 PO 選定並落地 | 依選項而定，選項 A 不涉及既有欄位改動 |
| 6 | **真實庫寫入**：`target_triple_barrier`／`label_reason` 對全部 3,713 列完成計算並寫入，走 RISK-013 三項協議；**須早於 `UG-G3-SB2` Panel 凍結** | **已完成**（2026-09-09，PO binding confirmation 核准）：`postgres`@`localhost:5432` 全部 3,713 列已寫入，24 格逐檔統計與 `UG_G3_SB1_ambiguous_ratio_report.json` 完全相符，0 列遺漏。RISK-013 三項協議：(1) `pg_dump` 備份 `D:\Python\Database_Backups\Stock_Prediction_System2\stock_prediction_system2_PRE_g3_sb1_tb_labels_20260909_151621.dump`（71,826,690 bytes）；(2) 寫入腳本 `efd0205` 版本、三道核對（列數/分布快篩/逐列精確）全過；(3) 備份還原至拋棄式容器驗證通過（3,713/3,713 列，還原後 target/reason 全 NULL，確認備份忠實記錄寫入前狀態）。完整證據見 `doc/upgrade/gates/evidence/UG_G3_SB1_real_db_write.json` |

## 12. PO 裁決（2026-09-09）

> 審查方已獨立重跑本提案 §3 的 splitter 全參數矩陣與 RISK-020 真實庫唯讀查核，
> 數字相符（含 §一訂正前發現的錯誤），格式與 contract-check 皆重跑通過。

| # | 事項 | 裁決 |
|---|---|---|
| 1 | §3 `embargo_days=0` 於 H=5 下是否維持 | **維持 0，核准**。裁決③要求的重議已履行——帶著實測而來，非自動延續。實測顯示 H=5 下算術未變：`embargo=1` 的可用天數 `60−5−1=54` 仍 `< min_train_size=55`，崩折機制原封不動，代價收益比與 H=1 相同。**失效條件更新**：本裁決成立於 **H≤5**；標籤視野再變，或 `UG-G3-SB3` 洩漏診斷出現折邊界異常，即重議 |
| 2 | §6.1 `label_end_date` 歸屬 | **選項 A**（新增 `label_end_date_tb`，不動既有欄位）。審查方已確認 `label_end_date` **不是 DB 欄位**（`database/` 全庫零命中），是 `generate_target_labels()` 的記憶體欄——選項 A 屬 DataFrame 層新增，不需 migration，與 §2.1「不需新增 migration」一致。B 把語意複雜度轉嫁 SB2，C 讓 H=1 任務白白承擔 H=5 的 purge 代價（每折多丟 4 天）——都不必要 |
| 3 | Dynamic barrier 模式是否併入本 SB | **維持 Out of Scope**。規格有定義但 Brief 未要求，範圍紀律優先；Ambiguous 比例報告出來若 >10%，規格 §4.4 的升級條件自己會把它叫回來 |
| 4 | 本提案是否核准進入實作 | **核准**，前提是本次 §一訂正（§3.3 第 2 點）與 §二補答（§11 第 6 項真實庫寫入）已完成——**兩者皆已完成，本提案現為核准版本**。設計逐條對規格 §4 核過；測試清單含兩個追加項（不變式逐列、purge 邊界落地為測試——後者正是把 §3 量測變成可執行檢查）；E2E 走拋棄式容器不碰真實庫，真實庫寫入另走本 SB 自己 Gate B 的 RISK-013 三項協議（§11 第 6 項） |

**§一訂正記錄**：原稿 §3.3 第 2 點稱「其餘 embargo 值下的末 fold 訓練列數與 H=1 完全相同」，
審查方獨立重跑抓出為誤——正確為除 `embargo=20`（已觸底）外皆穩定減少 4 天。**此錯誤的方向
恰好讓 H=5 顯得比實測更無害**，已於 §3.3 原地訂正並保留訂正痕跡，不覆蓋抹除。

---

## 13. 未獲核准前的自我約束

- 不修改 `src/`、`tests/`、`database/`
- 不執行任何 DB migration 或資料寫入（§3.2 的量測純屬記憶體內合成資料，
  未連線資料庫；§2.1 的欄位存在性查證為唯讀 `SELECT`）
- 不 Commit（本提案文件除外，且需 PO 授權）
