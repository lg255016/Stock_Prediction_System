# UG-G3-SB3 Gate A 提案：Specialist Models（RF／LightGBM／XGBoost）訓練與評估

> **訂正版**（2026-09-12）：回應 PO 複核退回的四個缺口——(1) 對照臂 A 白名單
> 不存在，(2) 面板列數與 NVDA 是否在內未查證，(3) 視窗參數與 Fold 數未給
> 實測數字，(4) NaN／NULL 標籤處理規則未明寫。三項裁決已定（RISK-025 選項
> (c)、洩漏診斷方法核准、`extract_multimodal_features()` 修復範圍擴大到
> `SENTIMENT_FEATURE_COLS` 八欄）直接採用，不重複討論選項。本版新增的查證
> 皆為對真實庫 `postgres`@`localhost:5432` 的唯讀 `SELECT` 與純記憶體運算
> （呼叫既有 `build_panel_dataset()`／`WalkForwardSplitter`，未寫入任何資料）。

## 0. 摘要

`UG-G3-SB2`／`UG-G3-SB2a` 皆已完成（Gate B 核准結案），本 SB 前置依賴成立。
本提案落地 `GATE3_STARTUP_APPLICATION.md` §5／§10 已核准的 D3 對照實驗設計，
並回答五項必答項；PO 已就 RISK-025、洩漏診斷方法、`extract_multimodal_features()`
修復範圍三項直接裁決，本版依裁決內容執行，其餘二項（rolling/expanding 落地
方式、面板凍結時點）維持提案內容待本次一併核准。

**新發現、已裁決併入本 SB 的既有缺陷**：`src/ml/model_trainer.py::extract_multimodal_features()`
對情緒欄有無條件 `fillna`，且**範圍比初版提案描述得更廣**——`else` 分支會把
`sentiment_3d_ma`／`sentiment_5d_ma` 補成 `0.0`（情緒尺度 0～1，`0.0` 是「極度
看空」而非中立值，比原本發現的 `sentiment_mean`／`sentiment_lag_*` 補 `0.5`
更嚴重）。**裁決**：`baseline_models.py` 既有的 `SENTIMENT_FEATURE_COLS`
常數（8 欄：`article_count`／`sentiment_mean`／`bullishness_index`／
`agreement_index`／`sentiment_3d_ma`／`sentiment_5d_ma`／`sentiment_lag_1`／
`sentiment_lag_2`）全部保留 `NaN`，一律不補；`rsi_14` 的 `50.0` 不動。詳見 §3.4。

## 1. Requirement Source

- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB3 Brief（核心欄位）
- `doc/upgrade/gates/GATE3_STARTUP_APPLICATION.md` §5（D3 對照實驗設計，PO
  核准）、§10（九項裁決全文，②③④⑦與本 SB 直接相關）
- PO／審查方 2026-09-12 兩輪訊息：五項必答項 + 複核退回的四個訂正缺口
- `doc/evidence/DECISIONS.md` DEC-018（Triple-Barrier 三分類、類別不平衡揭露
  條款）、DEC-035（邊界修訂）、DEC-017（Universe／候選空間定義，決定 NVDA
  是否進面板）
- `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-025（Timeout <5%）、RISK-015
  （情緒覆蓋率稀疏）
- `doc/governance/PROJECT_STATUS.md` §0.5 #16（三決定點）、#18（U 語意消費端
  靜默抹平）
- `src/ml/panel_dataset.py::build_panel_dataset()`、`src/ml/time_series_split.py::WalkForwardSplitter`
  （既有交付物，本 SB 直接重用其輸出，皆已實際呼叫驗證，見 §2）

## 2. Current State（唯讀查證＋純記憶體運算，`VERIFIED THIS SESSION`，2026-09-12）

### 2.1 `daily_ml_features` 全表口徑（既有查證，PO 已逐條重跑核對相符）

```sql
SELECT count(*) FROM daily_ml_features;                                    -- 449263
SELECT count(target_triple_barrier), count(label_reason), count(target_up_down)
  FROM daily_ml_features;                                                  -- (410443, 38820, 448650)
SELECT target_triple_barrier, count(*) FROM daily_ml_features GROUP BY 1;  -- -1:226956  0:21199  1:162288  NULL:38820
SELECT count(*) FROM daily_ml_features WHERE amplitude_ratio IS NULL;      -- 81
SELECT count(*) FROM daily_ml_features WHERE target_up_down IS NULL;       -- 613
SELECT count(*) FROM daily_ml_features WHERE sentiment_mean IS NULL;       -- 448480
SELECT count(*) FROM daily_ml_features WHERE sentiment_3d_ma IS NULL;      -- 447944
SELECT count(*) FROM daily_ml_features WHERE sentiment_5d_ma IS NULL;      -- 447667
SELECT count(distinct stock_id) FROM daily_ml_features;                    -- 459
SELECT count(distinct trade_date) FROM daily_ml_features;                  -- 1041
SELECT count(*), max(effective_date), min(effective_date) FROM universe_snapshots;
  -- 85641, 2026-08-03, 2022-11-01
SELECT count(distinct stock_id) FROM universe_snapshots WHERE included;    -- 458
SELECT count(*) FROM tracking_keywords WHERE is_active = TRUE;             -- 26
SELECT count(distinct stock_id) FROM daily_ml_features
  WHERE sentiment_mean IS NOT NULL;                                        -- 23（含 NVDA）
```

**全表口徑不是本 SB 實際訓練的資料範圍**——`daily_ml_features` 尚未經過
`universe_snapshots` 的 PIT（Point-in-Time）過濾，459 檔含 NVDA（美股，不在
`DEC-017` 候選空間內）。§2.2 是實際重用 `build_panel_dataset()` 算出的訓練
用面板數字，兩者的差異正是 PO 複核指出的缺口 (2)。

### 2.2 `build_panel_dataset()` 實際輸出（新查證，回應缺口 (2)）

```python
panel = build_panel_dataset(df_universe_snapshots, df_daily_ml_features,
                             df_stock_prices, target_column=..., holding_period=5)
```

對兩種 `target_column` 各呼叫一次，`holding_period=5`（DEC-018 H 值）：

| 指標 | `target_up_down` | `target_triple_barrier` |
|---|---|---|
| 面板列數 | 139,585 | 139,585（同一份 PIT 過濾，僅 `target` 欄來源不同） |
| 面板股票數 | **458** | **458** |
| **NVDA 是否在面板內** | **否** | **否** |
| `trade_date` 範圍 | 2022-11-01 ~ 2026-09-04 | 同左 |
| `target` 為 `NULL` 列數 | 185 | 15,147 |
| `amplitude_ratio` 為 `NULL` 列數 | 17 | 17 |

**NVDA 不在面板內，原因**：`universe_snapshots`（`UG-G2-SB6`，DEC-017）的
候選空間定義為「台股普通股」，NVDA 是美股，`included=TRUE` 從未涵蓋它——
`build_panel_dataset()` 的面板股票範圍完全取自 `universe_snapshots.included`
（函式 docstring 明文「不受 `entity_mapping` 是否有路由列影響」），這是
既有、已核准的設計，不是本次查證發現的異常。**本提案初版所有「459 檔」
字樣，凡指本 SB 實際訓練範圍者，皆訂正為「458 檔」；NVDA 的存在僅影響
`daily_ml_features` 全表統計，不影響本 SB 的面板與 Fold**。

**20／458（有情緒訊號的股票 in 面板內，非 23／459——正確算法見下方訂正）**：

**⚠ 訂正（PO 2026-09-12 複核第二輪）**：本節初版用「全表 23 檔有情緒訊號的
股票」∩「面板股票集合」算出 22 檔——**這個算法只檢查股票是否同時出現在
兩邊，沒有檢查該股票『有情緒訊號的那幾列』是否真的落在面板涵蓋的日期
範圍內**。`3141`（唯一情緒列在 2026-02-24，該股面板列只到 2023-04-28）與
`3362`（情緒列在 2026-06～09，該股面板列只到 2024-05-31）皆通過交集檢查、
被誤計入 22 檔，但面板實際列裡沒有它們的任何非 `NULL` `sentiment_mean`。

**正確算法**：直接在面板（parquet）上數 `sentiment_mean` 非 `NULL` 的相異
`stock_id`：

```python
panel["stock_id"][panel["sentiment_mean"].notna()].unique()  # 20 檔
```

即：面板內實際有非 `NULL` 情緒值的股票為 **20 檔**，`20／458 = 4.4%`
（訂正 §3.4／§4 原「22／458 = 4.8%」，該數字本身也是對「23／459 = 5.0%」
的第一輪訂正，但方法仍有誤，本輪才是正確算法）。

### 2.3 `WalkForwardSplitter` 實際 Fold 數（新查證，回應缺口 (3)）

參數：`train_window_size=60`、`test_window_size=20`、`step_size=20`（未傳，
等於 `test_window_size`）、`embargo_days=0`；`target_triple_barrier` 用
`label_horizon=5, label_end_date_col="label_end_date_tb"`，`target_up_down`
用 `label_horizon=1, label_end_date_col="label_end_date"`。

| 目標欄 | mode | Fold 數 | 切分耗時 | 訓練列數（min/中位數/max） | 測試列數（min/中位數/max） |
|---|---|---|---|---|---|
| `target_triple_barrier` | rolling | **43** | 1.52s | 8,205 / 8,250 / 8,250 | 2,985 / 3,000 / 3,000 |
| `target_triple_barrier` | expanding | **43** | 12.45s | 8,243 / 71,225 / 134,180 | 2,985 / 3,000 / 3,000 |
| `target_up_down` | rolling | **43** | 2.05s | 8,811 / 8,850 / 8,850 | 2,985 / 3,000 / 3,000 |
| `target_up_down` | expanding | **43** | 16.03s | 8,843 / 71,825 / 134,785 | 2,985 / 3,000 / 3,000 |

（切分耗時純粹是 `WalkForwardSplitter.split()` 本身的計算成本，不含任何
模型訓練；`expanding` 較慢是因為每個 Fold 都要重新對累積中的訓練集做
Purge 掃描，資料量隨 Fold 遞增。）

**單 Fold 訓練時間估計（`ENGINEERING JUDGMENT`，實測一個資料點外推）**：
在本容器（4GB／1.5 CPU，`n_jobs=1`）對 `target_triple_barrier` rolling 模式
第 1 個 Fold（訓練列 8,205，Drop `target` 為 `NULL` 後實際 7,730 列，16 個
Arm B 特徵欄）以 `RandomForestClassifier(n_estimators=200)` 訓練一次，
耗時 **2.88 秒**。粗略外推（未含 LightGBM／XGBoost 的實測，兩者對此規模
通常同量級或更快）：

- rolling：3 模型 × 2 對照臂 × 43 Fold × ~3 秒 ≈ **774 秒（~13 分鐘）**
- expanding：訓練列數中位數是 rolling 的 8.6 倍（71,225 / 8,250），若訓練
  時間近似線性隨列數增長，粗估 3 模型 × 2 對照臂 × 43 Fold × ~26 秒 ≈
  **6,708 秒（~112 分鐘，近 2 小時）**

**這是外推估計，不是實測總量**——`ENGINEERING JUDGMENT`，不可當作精確
排程依據。**實作階段第一步**（依 PO 於複核中的明確要求）：先只跑
`target_triple_barrier` × rolling × RF 的全部 43 個 Fold，量出真實總耗時，
再決定是否需要調整（例如降低 `n_estimators`、改用 `n_jobs>1`、或先只跑
rolling 再排 expanding）後才執行完整 3×2×2×43 組合。

## 3. PO 指定必答項

### 3.1 RISK-025：Timeout <5% 在 D3 的處置——**已裁決 (c)**

**裁決**（PO 2026-09-12）：維持現行 Static barrier，逐 Fold 揭露 per-class
指標；本 SB 不重算標籤。若訓練結果顯示 Timeout 類別 Recall 恆為 0 或近似
隨機，登記為 RISK-025 新證據並建議下一步（調寬 barrier 或改 Dynamic），
但下一步的執行屬另案。

**現況數字（兩個口徑分開陳述，避免混淆）**：

- **全表**：Timeout 佔已標籤列 21,199／410,443 = **5.17%**——這是整體比例，
  **不是** RISK-025 的判準本身。
- **逐檔**（RISK-025 實際判準）：**337／459 檔**（73.4%）逐檔 Timeout 佔比
  <5%（`VERIFIED THIS SESSION` 重新查證，與段 3 舊數字一致，未受 RISK-027
  修復影響——標籤欄本身未被段 2 重跑觸及）。
- 全表類別分布：`-1` 226,956／`0`（Timeout）21,199／`1` 162,288，`-1:+1` ≈
  1.399:1。DEC-018 原預期「Timeout 可能佔多數」，實測相反，方向與止損／
  止盈非對稱寬度（`lower_width` 1.5% 窄於 `upper_width` 2.0%）一致，非隨機
  噪音。

**本 SB 的具體動作**：訓練與評估流程對 `target_triple_barrier` 逐 Fold 輸出
三分類的 per-class Precision／Recall／F1（不只 Macro 平均值），段級報告
明確揭露 Timeout 類別的樣本外表現。

### 3.2 rolling vs expanding：內建子實驗（非新裁決，落地執行細節）

**已裁決內容**（`GATE3_STARTUP_APPLICATION.md` §10 裁決②，`PREVIOUSLY VERIFIED`）：
暫維持規格預設 `rolling`；兩模式對照列為本 SB 內建子實驗，**共用同一批 Fold
順帶比較，不另跑一輪**。實際 Fold 數與訓練列數見 §2.3（兩模式皆 43 Fold，
`embargo_days=0` 故本 SB 不會出現決定點 1 已實測的「expanding 訓練天數在
高 embargo 下萎縮」現象——仍列出訓練列數供未來若調整 `embargo_days` 時
對照）。**不產出「哪個模式更好」的單一結論**——最終選擇仍是 PO 的建模決定。

### 3.3 Embargo 長度與 `label_end_date_tb`——洩漏診斷方法**已核准**

**`label_end_date_tb` 的產生者——已存在，不需新建，已實際呼叫驗證（§2.2）**：
`src/ml/panel_dataset.py::build_panel_dataset()`（`UG-G3-SB2` 既有交付物）
在記憶體中對 `df_stock_prices['trade_date']` 做
`groupby('stock_id').shift(-holding_period)` 產生 `label_end_date_tb`，
不從 `daily_ml_features` 讀（該欄從未落庫）。本 SB 直接重用其輸出：

- `target_triple_barrier`：`WalkForwardSplitter(label_horizon=5, label_end_date_col="label_end_date_tb")`
- `target_up_down`：`WalkForwardSplitter(label_horizon=1, label_end_date_col="label_end_date")`

`build_panel_dataset()` 呼叫時明確傳入 `holding_period=5`，不依賴函式預設值
（即使目前預設恰好也是 5，明確傳入使這個耦合在呼叫端可見）。

**`embargo_days=0` 的失效條件已被觸發，洩漏診斷是本 SB 的責任（已核准設計）**：
`GATE3_STARTUP_APPLICATION.md` §10 裁決③明文「本裁決成立於現行 1 天標籤
視野；若 Gate 3 改用多天視野標籤，purge 算術整組改變，本裁決自動失效、
須重議」。`UG-G3-SB1` 的 Triple-Barrier 是 H=5，字面上已觸發此失效條件。
`UG-G3-SB1` Gate A 已做過機械代價重測（`PREVIOUSLY VERIFIED`）：`min_train_size`
59→55、fold 數與崩潰模式不變、expanding 最後一個 Fold 訓練天數只減少
0.6%——機械代價確認無實質變化。但「理論上的自相關滲漏疑慮」明文留給本 SB
（§10 裁決理由二：「SB3 洩漏診斷若顯示折邊界表現異常，屆時帶證據開 ADR」）。

**洩漏診斷設計（PO 已核准）**：每個 Fold 的測試窗拆成「邊界窗」（前 H=5 個
交易日，最靠近 Purge 邊界）與「內部窗」（其餘天數），分別計算 Macro F1／
per-class 指標；**判準**：邊界窗表現系統性偏離內部窗（非單一 Fold 隨機
波動）。觀察到此症狀 → 段級報告標示並建議開 ADR 重議 `embargo_days`；未
觀察到 → 記錄「本次量測未發現邊界窗異常，`embargo_days=0` 維持有效」。
**known-FAIL**（PO 要求）：合成一個刻意讓未來資料洩漏進訓練集的 Fold
（例如故意不做 Purge，讓訓練集包含測試窗標籤所依賴的日期），確認診斷方法
能偵測到該邊界窗異常；同時**明寫此法不窮盡所有滲漏形式**（見 §7）。

`min_train_size`：沿用預設推導值（`rolling`+`embargo_days=0` 下 `max(1,
train_window_size - label_horizon)`），§10 裁決④「條件未觸發，不裁」在本
SB 內同樣不觸發。

**⚠ 本缺口由 PO 複核發現**：`target_up_down` 路徑目前會**靜默走 Purge 近似
fallback**，本提案原述「既有 T+1 欄 `label_end_date`，不受本 SB 影響」不
成立——`build_panel_dataset()` 只產生 `label_end_date_tb`，**沒有**
`label_end_date`。T+1 欄由 `feature_aggregator.py::generate_target_labels()`
在記憶體產生，**從未落庫**（29 欄契約沒有它），面板裡根本不存在這一欄。
因此 §2.3 對 `target_up_down` 的兩次 `WalkForwardSplitter` 呼叫，`label_end_date_col="label_end_date"`
在面板裡找不到對應欄，**靜默落入 `time_series_split.py:183-191` 明文的
近似 fallback 路徑**（以全域唯一交易日索引 + `label_horizon` 反推，該函式
docstring 自己寫明「停牌股可能低估應被 Purge 的列」「不應作為正式驗收
依據」）。`fold_metadata` 未標示走了 fallback，故 §2.3 量出的 43 Fold
數字對 rolling／expanding 兩模式看起來一致，**無法從輸出本身分辨是否已經
是精確路徑**。

**設計選擇（PO 要求擇一並說明理由）**：**採用「擴充 `build_panel_dataset()`
同時輸出兩欄」**，不在 SB3 入口另外補 `label_end_date`。理由：`label_end_date_tb`
刻意對 `df_stock_prices['trade_date']`（該股票**完整、未經 PIT 過濾**的
真實交易日序列）做位移，不是對面板自身（PIT 過濾後，股票可能因下市／
退出候選池而序列有缺口）的 `trade_date` 位移——這正是函式現有 docstring
強調的設計理由。若 `label_end_date`（T+1）改在 SB3 入口對**面板自身**的
`trade_date` 做位移，會重新引入同一類「用了錯的日曆序列」風險（與
RISK-027 的根因同一種形狀：對哪一份序列做位移，選錯就會安靜地錯）。兩個
`label_end_date*` 欄的計算基準應該只有一個地方決定，讓 `build_panel_dataset()`
同時輸出兩欄，取 `holding_period=1` 位移得到 `label_end_date`、
`holding_period=holding_period`（傳入值，H=5）位移得到 `label_end_date_tb`，
兩者共用同一份 `prices.groupby('stock_id')['trade_date']` 排序物件，一次
`groupby` 兩次 `shift`，不重複掃描價格表。

**併入實作的具體要求**：
1. `build_panel_dataset()` 新增輸出欄 `label_end_date`（`holding_period=1`
   的位移，語意與 `feature_aggregator.py:986` 的 T+1 定義一致，惟計算基準
   為 `df_stock_prices` 而非面板自身，理由如上）；函式簽章與既有呼叫端
   （若有）相容，僅新增輸出欄，不改變既有欄位語意。
2. `WalkForwardSplitter` 新增 `require_label_end_date: bool = False` 建構
   參數（**訂正**——PO 2026-09-12 第二輪複核：不得一律拋例外，既有五個
   呼叫端與 `scripts/generate_tournament_artifact.py` 皆依賴近似 fallback，
   直接一律拒絕會使它們全部壞掉，範圍溢出 SB3）：預設 `False` 維持既有
   行為；SB3 呼叫端傳 `True`，`label_end_date_col` 指定欄名不存在於傳入
   的 `df` 即拋 `KeyError`。無論本參數為何，`fold_metadata` 皆新增
   `purge_mode`（`"exact"`／`"approximate"`）誠實回報實際路徑——這是本
   缺口的根因（走了 fallback 沒人知道），比拋例外本身更重要。
3. 段級報告記錄 `target_up_down` 兩個模式的 `purged_samples` 逐 Fold 數字，
   與「精確欄補上前的近似值」對照一次——用於實測驗證本面板上是否真的
   發生「fallback 低估 Purge」（預期：無停牌股的 Fold 兩者相同，有停牌股
   的 Fold 精確值 >= 近似值）。

### 3.4 `sentiment_mean` NULL 0.998：修復範圍擴大 + 範圍揭露訂正——**已裁決**

**修復（裁決：範圍擴大到 `SENTIMENT_FEATURE_COLS` 全部 8 欄）**：
`model_trainer.py::extract_multimodal_features()` 目前對
`sentiment_mean`／`sentiment_lag_1`／`sentiment_lag_2` 補 `0.5`，其餘情緒欄
（`article_count`／`bullishness_index`／`agreement_index`／`sentiment_3d_ma`／
`sentiment_5d_ma`）落入 `else` 分支補 `0.0`——**`sentiment_3d_ma`／
`sentiment_5d_ma` 補 `0.0` 比補 `0.5` 更嚴重**：情緒尺度 0～1，`0.0` 是
「極度看空」的具體語意值，不是中立點。真實庫全表 NULL 數：`sentiment_3d_ma`
447,944 列、`sentiment_5d_ma` 447,667 列（`VERIFIED THIS SESSION`）。

**修復方式**：直接重用 `baseline_models.py` 既有的 `SENTIMENT_FEATURE_COLS`
常數（8 欄，已在 `model_trainer.py` 匯入）作為排除清單——欄名在此清單者
一律保留 `NaN`，不進 `fillna` 迴圈；`rsi_14` 仍 `fillna(50.0)`（聚合層已
保證非 NULL，此為安全防禦，非本次對象）；其餘欄（原始價量、`return_1d`、
`volatility_5d/20d`，及 §5 新增的 CORE_16 平穩化欄）仍 `fillna(0.0)`——
`article_count`／`bullishness_index`／`agreement_index` 在庫裡本應已無
`NULL`（聚合層已補 `0.0` 真值），改為不補是**零行為變化**，但規則統一套用
整份 `SENTIMENT_FEATURE_COLS` 比逐欄列名更不易在未來新增情緒欄時漏改。

**範圍揭露訂正（回應缺口 (2)，並經第二輪複核修正計算方法）**：初版
「23／459 = 5.0%」是全表口徑，且含 NVDA（不在面板內）；第一輪訂正的
「22／458」用交集法計算，漏查兩檔股票的情緒列是否真的落在面板日期範圍內
（§2.2）。**正確：本 SB 實際訓練面板內，`sentiment_mean` 非 `NULL` 的股票
為 20／458 = 4.4%**——`tracking_keywords` 僅 26 個啟用關鍵字，其餘 438 檔
股票的情緒欄在面板內全部是 `NULL`（成因 U）。本 SB 段級報告除全宇宙
（458 檔）整體 D3 對照外，**必須額外附一份限定在這 20 檔的子集對照**，
兩者並列。

### 3.5 面板凍結時點：每日 ETL 首跑之前，且以指定 POST 備份為可稽核基準——**已裁決**

**裁決**（PO 2026-09-12）：每日 ETL 首跑之前凍結；凍結基準為
`D:\Python\Database_Backups\Stock_Prediction_System2\stock_prediction_system2_POST_g3_sb2a_stage2_rerun_risk027_20260912_121252.dump`
（RISK-027 段 2 重跑的 POST 備份，即本次查證所依據的真實庫現況）。

**落地流程**（實作階段執行，本提案先寫定步驟）：

1. 確認當前真實庫與該 POST 備份一致（比照本次段 2 重跑報告的指紋比對法：
   `daily_ml_features` 列數＋標籤計數、`stock_prices` 列數＋md5），或直接
   將該備份還原至一個拋棄式容器，在其上執行本 SB 全部運算（與真實庫零
   接觸，天然滿足「唯讀」）。
2. 呼叫 `build_panel_dataset()`（兩種 `target_column` 各一次）取得面板，
   匯出成靜態檔案（`parquet`，含 `sha256`／`md5` 與列數、欄位清單、
   `trade_date` 範圍寫入證據 JSON）。
3. 本 SB 之後所有 Fold 切分、模型訓練、洩漏診斷，皆讀這份匯出檔，**不再
   重新查詢即時 DB**——即使真實庫在 SB3 執行期間因其他小案（如 wrap-rule
   平行小案）而變動，也不會悄悄污染本 SB 的結果，且任何人事後都能用同一份
   匯出檔重現本 SB 的全部數字。
4. 每日 ETL 首跑之後的面板變化，屬於下一次獨立的重新訓練或增量驗證，
   **不回填進本 SB 的結果**。

**本 SB 不觸發、不等待、也不阻擋每日 ETL 首跑**——兩者是獨立時間軸。

## 4. D3 對照實驗設計（`GATE3_STARTUP_APPLICATION.md` §5／§10 已核准，本節
落地執行細節，數字依 §2 訂正）

| 項目 | 設計 |
|---|---|
| 對照臂 A（無情緒） | `CORE_16` 平穩化特徵（`amplitude_ratio`／`ma5_bias_ratio`／`ma20_bias_ratio`／`volume_ratio_5d`）+ `return_1d`／`rsi_14`／`volatility_5d`／`volatility_20d`，共 8 欄，**不含原始 OHLCV**（§5 白名單修訂理由）；**必含 Logistic Regression 基準** |
| 對照臂 B（有情緒） | 對照臂 A + `SENTIMENT_FEATURE_COLS` 8 欄（§3.4 修復後皆為真 `NaN`），共 16 欄 |
| 留言欄（`comment_volume_ratio`／`comment_polarization`／`net_push_momentum`） | **不使用**——不在既有 `ALL_MULTIMODAL_FEATURE_COLS`（18 欄，即將擴充版）內，且全表全 `NULL`（DEC-024 時點過濾），本 SB 不將其納入任一對照臂 |
| 模型選擇 | 對照臂 B 只用 RF／LightGBM／XGBoost（原生支援 `NaN`，`5bfb3b8` §9.1 已實測）；LR 不進對照臂 B，不得為它插補 |
| 判準 | 對照臂 B 相對 A 的樣本外表現提升（Macro F1／Conditional Win Rate），Purged Walk-Forward 下量測，不用單一 Accuracy |
| 執行時機 | 本 SB 內，與各 Specialist 本來就要做的獨立訓練評估共用同一批 Fold |
| 覆蓋率門檻 | 本實驗結果直接回答「覆蓋率夠不夠」，不預先訂百分比門檻 |
| **範圍聲明（訂正）** | 對照臂 B 的訊號只存在於面板內 **20／458 檔（4.4%）**；報告需並列全宇宙與 20 檔子集兩份數字 |

## 5. In Scope

1. **`src/ml/baseline_models.py`：新增兩個常數**（不修改既有
   `TECHNICAL_FEATURE_COLS`／`ALL_MULTIMODAL_FEATURE_COLS`／
   `SENTIMENT_FEATURE_COLS`——三者被 `src/ml/predictor.py`、
   `src/ui/data_loader.py` 消費，變更會擴大本 SB 範圍到 Predictor／UI，
   不屬於本 SB Affected Components）：
   - `CORE16_STATIONARY_COLS`：`amplitude_ratio`／`ma5_bias_ratio`／
     `ma20_bias_ratio`／`volume_ratio_5d`（4 欄）。
   - `ARM_A_FEATURE_COLS = CORE16_STATIONARY_COLS + ["return_1d", "rsi_14",
     "volatility_5d", "volatility_20d"]`（8 欄，對照臂 A）。
   - `ARM_B_FEATURE_COLS = ARM_A_FEATURE_COLS + SENTIMENT_FEATURE_COLS`
     （16 欄，對照臂 B）。
   - **受影響測試**：零個既有測試檔需要修改——`TECHNICAL_FEATURE_COLS`／
     `ALL_MULTIMODAL_FEATURE_COLS`／`SENTIMENT_FEATURE_COLS` 三者的值完全
     不變（僅新增，未修改既有常數），依賴它們的既有 4 個測試檔
     （`test_baseline_models.py`／`test_ml_evaluator.py`／
     `test_model_trainer.py`／`test_thematic_feature_spillover.py`／
     `test_ui_contracts.py`）與 `predictor.py`／`src/ui/data_loader.py`
     不受影響。新增常數只需新增測試（`test_arm_a_excludes_raw_price`／
     `test_arm_b_equals_arm_a_plus_sentiment`）。
2. `src/ml/model_trainer.py::MultiModalTrainer.extract_multimodal_features()`：
   改用 `SENTIMENT_FEATURE_COLS` 判斷是否跳過 `fillna`（§3.4），8 欄全部
   保留 `NaN`；`rsi_14` 的 `fillna(50.0)` 不動。
3. `src/ml/panel_dataset.py::build_panel_dataset()`：新增輸出欄
   `label_end_date`（`holding_period=1` 位移，計算基準為 `df_stock_prices`，
   理由與擇一說明見 §3.3「本缺口由 PO 複核發現」段落）；`df_stock_prices`
   為空或缺席時比照既有 `label_end_date_tb` 同樣設為 `NaT`。
4. `src/ml/time_series_split.py::WalkForwardSplitter`：新增
   `require_label_end_date: bool = False` 建構參數（預設不變既有行為，
   `True` 時 `label_end_date_col` 指定欄名不存在於傳入 `df` 即拋
   `KeyError`）；`fold_metadata` 新增 `purge_mode`（§3.3）。
5. `src/ml/specialist_training.py::prepare_fold_data()`（新增模組）：
   規則 (a)(b)(c)（§5 規則 (c) 文字訂正——PO 2026-09-12 第二輪複核：原文
   「對照臂 B 遇到非情緒欄 NaN 中止並拋例外」會讓 D3 在真實面板上直接
   中止——面板內有 17 列 `amplitude_ratio` NULL，且 D3 判準要求 A／B 兩臂
   逐 Fold 用同一批列比較，剔除規則必須對兩臂一致，不能一臂剔除、一臂
   拋例外）：
   (a) `target` 為 `NULL` 的列**從訓練與測試集剔除**（面板內：
   `target_triple_barrier` 15,147 列／`target_up_down` 185 列），逐 Fold
   記錄剔除數；
   (b) **非情緒特徵欄**（`feature_cols` 中不在 `sentiment_cols` 者，對照臂
   A 即 `ARM_A_FEATURE_COLS` 全部、對照臂 B 亦同）含 `NULL` 的列**剔除並
   計數**，兩臂一律套用（面板內 `amplitude_ratio` NULL 17 列；不得
   `fillna(0.0)` 掩蓋）；剔除後 A、B 兩臂保留的列索引集合必須相等；
   (c) 情緒欄（`SENTIMENT_FEATURE_COLS`）的 `NaN` 允許保留，不剔除、不
   填補，交給 RF／LightGBM／XGBoost 原生處理；規則 (b) 執行後若非情緒欄
   仍殘留 `NaN`（結構上不應發生）才拋例外，作為防禦性斷言，不是「對照臂
   B 遇到即拋例外」的主要判斷分支。回傳 `retained_index`／`trade_date`
   供 §3.3 邊界窗/內部窗診斷使用。
6. 建立 Specialist 訓練與評估的 SB3 專屬入口（新模組或擴充
   `model_trainer.py`／`evaluator.py`，最終命名於實作階段定案；**可與本
   輪 commit 分批**，本輪僅完成 `prepare_fold_data()` 亦可）：
   - 讀取 §3.5 匯出的凍結面板檔（非即時查詢 DB）。
   - 逐 Specialist（RF／LightGBM／XGBoost）× 逐對照臂（A／B，B 排除 LR）×
     逐模式（rolling／expanding）訓練與評估，共用同一批 `WalkForwardSplitter`
     Fold（§2.3 已實測 43 Fold／目標欄／模式），呼叫 `prepare_fold_data()`
     取得每個 Fold 的訓練/測試資料。
   - 逐 Fold、逐邊界窗/內部窗（§3.3 洩漏診斷）輸出 Macro F1／per-class
     Precision／Recall／F1。
7. RISK-025 揭露（§3.1）：per-class 指標作為段級報告固定項目，隨評估輸出
   自然產生，不需另建機制。
8. 測試（Master Plan 既定命名 + 本提案新增）：
   - `test_rf_fold_output`／`test_lgbm_fold_output`／`test_xgb_fold_output`
     （既定命名）
   - `test_specialist_no_leakage`（既定命名，驗證訓練/測試索引無交集、
     Purge 生效）
   - `test_arm_a_excludes_raw_price`／`test_arm_b_equals_arm_a_plus_sentiment`
     （§5 項 1 新常數的定義測試）
   - `test_extract_multimodal_features_preserves_all_sentiment_nan`
     （§3.4 修復回歸測試，known-FAIL：對 `SENTIMENT_FEATURE_COLS` 8 欄各
     放一個合成 `NaN` 列，修復前 5 欄——`sentiment_3d_ma`／`sentiment_5d_ma`／
     `article_count`／`bullishness_index`／`agreement_index`——必 FAIL，因
     它們現行落在 `else: fillna(0.0)` 分支）
   - `test_panel_dataset_produces_label_end_date`（§5 項 3，斷言
     `build_panel_dataset()` 輸出含 `label_end_date`，值等於該股票在
     `df_stock_prices` 序列中下一個交易日）
   - `test_split_refuses_fallback_purge_when_required`（§5 項 4，known-FAIL：
     `require_label_end_date=True` 時把 `label_end_date_col` 指定欄名從
     傳入的 `df` 移除，確認 `WalkForwardSplitter.split()` 拋 `KeyError`
     而非靜默走近似 fallback）
   - `test_split_allows_fallback_by_default_existing_callers_unaffected`
     （回歸防護：`require_label_end_date` 預設 `False`，既有五個呼叫端
     與 `scripts/generate_tournament_artifact.py` 的既有呼叫方式不受影響）
   - `test_fold_metadata_reports_purge_mode_exact`／
     `test_fold_metadata_reports_purge_mode_approximate`（`fold_metadata`
     新增 `purge_mode` 欄位，known-FAIL：現行 metadata 沒有這個鍵）
   - `test_null_target_rows_excluded_from_fold`（規則 (a)）
   - `test_rule_b_null_feature_rows_excluded_not_filled`（規則 (b)，
     known-FAIL：若誤寫成 `fillna(0.0)`，該測試斷言的剔除計數會變成 0）
   - `test_rule_c_sentiment_nan_allowed_in_arm_b`（規則 (c)，情緒欄 `NaN`
     允許保留的對照）
   - `test_arm_a_and_arm_b_retain_identical_row_index_sets`（規則 (b) 對
     兩臂一致套用，known-FAIL：若 arm B 漏掉非情緒欄的剔除，兩臂保留的
     列索引集合會不同）
   - `test_boundary_window_vs_interior_window_metrics`（§3.3 洩漏診斷函式
     單元測試，含合成滲漏 Fold 的 known-FAIL，排入後續 commit）

## Out of Scope

- OOF Stacking（`UG-G3-SB4`）、機率校準（`SB5`）、選擇性推論（`SB6`）、完整
  Benchmark 對照組（`SB7`）。
- RISK-025 選項 (a)／(b)（調寬 barrier／Dynamic barrier）的實際執行——本 SB
  只揭露證據，不執行標籤重算。
- RISK-020（暖機期填值是否為事件值）的重量測——`緩裁`狀態延續，與本 SB
  無依賴關係。
- 每日 ETL 首次執行——獨立時間軸（§3.5）。
- 修改 `src/ml/predictor.py`、`src/ui/data_loader.py`——本 SB 新增常數不
  觸碰既有共用常數，兩檔不受影響（§5 項 1）。

## 6. Failure Semantics & Tests

| 情境 | 設計行為 | 測試 |
|---|---|---|
| `extract_multimodal_features()` 收到 `SENTIMENT_FEATURE_COLS` 任一欄全 `NaN` | 保留 `NaN`，不填補 | `test_extract_multimodal_features_preserves_all_sentiment_nan` |
| `target` 為 `NULL` | 該列剔除，計數記錄 | `test_null_target_rows_excluded_from_fold` |
| 非情緒特徵欄含 `NaN`（兩臂一致） | 該列剔除，計數記錄，不 `fillna` | `test_rule_b_null_feature_rows_excluded_not_filled` |
| 對照臂 B 情緒欄含 `NaN` | 允許保留，不剔除、不填補 | `test_rule_c_sentiment_nan_allowed_in_arm_b` |
| 對照臂 A／B 剔除後保留列不一致 | 兩臂保留的列索引集合須相等 | `test_arm_a_and_arm_b_retain_identical_row_index_sets` |
| Fold 訓練集與測試集索引重疊 | `WalkForwardSplitter` 既有斷言擋下 | `test_specialist_no_leakage` |
| 對照臂 B 誤用 LogisticRegression | 模型清單常數限制，設計上排除 | 涵蓋於 D3 對照實驗建構測試 |
| Fold 邊界窗系統性偏離內部窗 | 標示滲漏症狀，建議開 ADR | `test_boundary_window_vs_interior_window_metrics`（含合成滲漏 known-FAIL） |
| 凍結面板檔雜湊／列數與證據記錄不符 | 前置守衛拒絕執行 | 隨實作補上 known-FAIL 案例 |
| `label_end_date_col` 指定欄名不在面板內且 `require_label_end_date=True` | `WalkForwardSplitter.split()` 拋 `KeyError`，不落入近似 fallback | `test_split_refuses_fallback_purge_when_required` |
| 同上但 `require_label_end_date=False`（既有呼叫端預設） | 維持既有近似 fallback 行為不變 | `test_split_allows_fallback_by_default_existing_callers_unaffected` |
| `fold_metadata` 是否誠實回報走了哪條 Purge 路徑 | 新增 `purge_mode`（`"exact"`／`"approximate"`） | `test_fold_metadata_reports_purge_mode_exact`／`_approximate` |
| `build_panel_dataset()` 輸出面板 | 含 `label_end_date`（T+1，計算基準 `df_stock_prices`）與 `label_end_date_tb` 兩欄 | `test_panel_dataset_produces_label_end_date` |

## 7. Risks & Trade-offs

- 20／458 檔（4.4%）的情緒覆蓋率意味著 D3 對照臂 B 即使有提升，也可能只
  反映極少數股票的訊號，**不構成「情緒特徵對全宇宙普遍有效」的證據**——
  §3.4／§4 的範圍聲明已明文界定，段級報告不得誇大結論範圍。
- 洩漏診斷（§3.3）是本 SB 新設計、未經產業標準驗證的方法，可能無法偵測
  所有形式的滲漏（例如非常微弱、需要更長觀察窗才顯現的滲漏）——已附
  known-FAIL 案例，但不宣稱此方法窮盡所有滲漏形式。
- `expanding` 模式全量執行的耗時估計（§2.3）為外推非實測，可能與實際相差
  數倍——已設計「先跑一個目標×一個模式×一個模型的全部 Fold 量測真實
  耗時」作為實作第一步，避免在容器資源（4GB／1.5 CPU）下無預警長時間
  佔用。
- Timeout 類別（RISK-025）若被證實完全無法學習，會直接影響 Macro F1 的
  可信度（少數類別 Recall=0 時 Macro F1 仍可能被多數類別撐高）——段級報告
  需同時揭露 per-class 指標。

## 8. E2E Verification Plan

1. 容器內全套測試：`python -m unittest discover -s tests -p "test_*.py"`。
2. `python scripts/verify/gate0_contract_check.py`（本 SB 未變更資料契約，
   預期 13/13 PASS 不受影響；仍需重跑確認）。
3. 面板匯出（§3.5）：對凍結基準（POST 備份或還原後的拋棄式容器）呼叫
   `build_panel_dataset()` 兩次，匯出檔案並記錄雜湊／列數/欄位/日期範圍。
4. **單 Fold 耗時實測**（§2.3 要求的實作第一步）：`target_triple_barrier`
   × `rolling` × RF，跑滿 43 Fold，記錄真實總耗時，據此決定是否調整規模
   再執行完整 3 模型 × 2 對照臂 × 2 模式組合。
5. 完整組合執行，段級報告附全部 Fold 的逐項指標（不只摘要平均值），含
   全宇宙與 20 檔子集並列的 D3 對照。
6. 洩漏診斷（含合成滲漏 Fold 的 known-FAIL 案例）執行記錄。
7. 本 SB 不寫入任何資料庫，不需要 RISK-013 三步驟協議。

## 9. Documentation Sync

- `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB3 Brief：新增 Affected
  Components（`src/ml/baseline_models.py` 新常數）隨 Gate B 訂正。
- `REMAINING_RISKS.md` RISK-025：追加本 SB 的 per-class 實測結果段落。
- `PROJECT_STATUS.md` §0.5 #16／#18：#18（U 語意消費端抹平）於本 SB 修復
  （範圍擴大版）後可標記關閉；#16 的 rolling/expanding 對照結果、embargo
  洩漏診斷結果登記。
- 若洩漏診斷發現異常，另開 ADR（`Proposed`，待 PO 核准）——本提案不預先
  假設結果。
- `doc/evidence/CHALLENGES.md`：本次複核發現「修復範圍比初版描述更廣
  （`else` 分支的 0.0 比原判的 0.5 更嚴重）」與「對照臂 A 白名單在 ML 白
  名單裡不存在」兩處，性質屬非瑣碎的設計缺口，依 `evidence-sync` skill
  評估是否建 CHAL（傾向於：待實作完成、若無新發現則併入 Gate B 揭露，不
  另開，因為根因已在本提案內完整記錄）。

## 10. Definition of Done

- [ ] `baseline_models.py` 新增 `CORE16_STATIONARY_COLS`／`ARM_A_FEATURE_COLS`／
      `ARM_B_FEATURE_COLS`，既有常數與其消費者（`predictor.py`／
      `src/ui/data_loader.py`）零行為變化（測試證明）。
- [ ] `extract_multimodal_features()` 修復（`SENTIMENT_FEATURE_COLS` 8 欄
      保留 `NaN`）並通過回歸測試（含 known-FAIL）。
- [ ] `build_panel_dataset()` 新增輸出 `label_end_date`（T+1）；
      `WalkForwardSplitter.split()` 缺 `label_end_date_col` 時拋例外，不再
      靜默走近似 fallback；`target_up_down` 兩模式的 `purged_samples` 精確
      值與近似值對照記入段級報告（含 known-FAIL）。
- [ ] 面板匯出檔案產生，雜湊／列數/日期範圍記入證據文件。
- [ ] 單 Fold 耗時實測完成，記錄真實數字（取代 §2.3 的外推估計）。
- [ ] 三個 Specialist × 兩個對照臂（B 排除 LR）× 兩種模式，在凍結面板上
      完成 Purged Walk-Forward 訓練與評估。
- [ ] 段級報告含：全宇宙（458 檔）與 20 檔子集並列的 D3 對照結果；RISK-025
      per-class 揭露（含全表 5.17% 與逐檔 337/459 兩個口徑分列）；rolling
      vs expanding 逐 Fold 對照；邊界窗 vs 內部窗洩漏診斷結果。
- [ ] NaN／NULL 標籤處理規則 (a)(b)(c) 全部有對應測試與 known-FAIL。
- [ ] 全套測試 PASS；`gate0_contract_check.py` 13/13 PASS exit 0。
- [ ] 無任何資料庫寫入。

## 11. 請求 PO 裁決事項——**全部四項已核准（PO 2026-09-12）**

| # | 事項 | 裁決 |
|---|---|---|
| 1 | §5 新增 `CORE16_STATIONARY_COLS`／`ARM_A_FEATURE_COLS`／`ARM_B_FEATURE_COLS`（不修改既有三個常數） | **核准** |
| 2 | §2.3 單 Fold 耗時實測作為實作第一步（而非直接跑全量） | **核准**——量完把真實數字取代外推值，再決定規模 |
| 3 | §3.5 落地流程 | **核准，指定用拋棄式容器還原**
  `stock_prediction_system2_POST_g3_sb2a_stage2_rerun_risk027_20260912_121252.dump`
  （不採指紋比對路線），在其上跑 `build_panel_dataset()` 匯出 parquet，
  SB3 全程與真實庫零接觸 |
| 4 | 本訂正版整體 | **核准進入實作**，附 §3.3「本缺口由 PO 複核發現」一項條件（已併入本文件） |

**實作順序**（PO 核准）：紅測先行 → PO／審查方確認 RED → 實作 commit
（`baseline_models.py`／`model_trainer.py`／`panel_dataset.py`／
`time_series_split.py`／SB3 入口模組）→ 複核 → 拋棄式還原＋面板匯出＋單
配置耗時實測 → 全量 → 段級報告 → Gate B。SB3 全程無真實庫寫入，不需
RISK-013。

## 12. 未獲核准前（實作 commit 前）的自我約束

- 已核准進入實作，但**紅測 commit 前**仍不得有實作內容混入——先送 RED
  測試（含 known-FAIL 案例的實測記錄），經 PO／審查方確認 RED 成立後才
  進入實作 commit。
- 不執行任何 DB migration 或真實庫資料寫入（面板匯出／訓練評估皆在拋棄式
  容器或記憶體中進行）。
- 不觸發每日 ETL 執行。
- 每個 commit 前依 `gate-submit` skill 自檢；超出授權清單的檔案逐檔揭露。
