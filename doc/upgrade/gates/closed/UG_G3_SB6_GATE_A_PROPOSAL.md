# UG-G3-SB6 Gate A 提案：Timeout Gating（原「Selective Inference & Regime Gating」）

> **狀態**：**Gate A 已核准（2026-09-15，PO 核准），v3 為核准版本**。v1 審查方複核：結構通過，九項必答皆有回應，§2 數字逐一核對相符；§3.5 量化目標有結構性問題（「≥3 倍且 ≥50% 覆蓋率」整段 1%～30% gate 比例都成立，釘不住任何 `θ`），審查方以唯讀探測直接裁定，四項裁決＋六處訂正落地為 v2。v2 複核：四項裁決與六處訂正皆確認落地，僅兩處再訂正——§2.5 的 `θ` 差異真因是 OvR 正規化（非 v2 誤猜的分位數取法差異，PM 已獨立重現確認）；§3.5 的可行區間選點規則在 Gate A 階段即釘住（召回最高，同召回取精準度較高），不留給實作階段——訂正後 v3 核准，直接 commit。
> **前置**：`UG-G3-SB5` 已於 2026-09-15 Gate B 核准結案（`3f77fb9`，訂正 `fe30ef2`）。新 ADR `DEC-041`（`PROPOSED`）記錄 Gate 3 主線轉軸：`UG-G3-SB6` 對 `target_up_down` 停做，改以 `target_triple_barrier`／Timeout 類校準後機率為 gating 對象。
> **本提案階段唯讀**：僅查證現況、規劃設計，未修改任何業務程式碼、未動任何資料庫。§2 的全部數字為對 `UG-G3-SB4` 凍結 OOF parquet（`oof_target_triple_barrier_20260915_025542.parquet`，sha256 `b9c1d432…4f94466c`，本次重新核對相符）與既有 `UG-G3-SB5` 證據 JSON 的唯讀查證，未重新擬合任何校準器供本文件之外的用途。**唯一的例外**：§2.5 的門檻曲線與 regime 診斷數字，審查方於 v1 複核時已用真實 Calib-eval 資料算過一次（唯讀，重建 `UG-G3-SB4` 已核准的 Meta(A)-LR／Ridge 並套用 `UG-G3-SB5` 已核准的校準器，未產生任何新模型或新門檻），PM 本輪用一次性、不 commit 的探測腳本（跑完即刪，過程見 §2.5 註記）獨立重現，逐位或近乎逐位相符——這是「複核既有結果」，不是「跑新實驗」。未碰 Holdout（折 33-42），探測腳本開頭即斷言 `fold_id.max()≤32` 且 `trade_date.max()<HOLDOUT_START_DATE`。

---

## 0. 摘要

`UG-G3-SB5` 校準 `target_up_down` 與 `target_triple_barrier` 兩個 target 的 Meta-Learner 機率時，實測發現 `target_up_down` 在折 27-32 全線無可偵測排序訊號（`RISK-030`），而 `target_triple_barrier` 的訊號幾乎全部集中在 Timeout 類（OvR AUC 0.82～0.91）。`UG-G3-SB5` Gate B 四項裁決（`DEC-041`）把 Gate 3 剩餘工作的主線從「預測漲跌方向」轉為「判斷何時不該交易」：`UG-G3-SB6` 停做 `target_up_down`，改以 TB／Timeout 校準後機率為信心門檻對象。

本提案依 `DEC-041` Decision 2 的四項必答（gating 評估指標、門檻選定範圍、Timeout gating 量化目標、原 Brief 範圍調整）逐一設計，另加 PO 本輪追加的 5 項（校準器選擇、regime gating 去留、Data Contract、與原 Brief 逐項對照、DoD 內 `DEC-041` 轉 `APPROVED` 條件），共 9 項必答，見 §3。

---

## 1. Requirement Source

| 來源 | 內容 |
|---|---|
| `DECISIONS.md` `DEC-041`（`PROPOSED`） | Decision 1：`UG-G3-SB6` 對 `target_up_down` 停做；Decision 2：改以 TB／Timeout 校準後機率為 gating 對象，Gate A 必答 gating 評估指標定義、門檻在 Calib-eval（折 30-32）選定、與 `DEC-040` 的 Holdout 隔離規則一致；Decision 4：Timeout gating 量化目標數字由本 Gate A 提案訂定 |
| `REMAINING_RISKS.md` `RISK-030` | `target_up_down` 折 27-32 全線無排序訊號的完整實測數字；TB 各類 OvR AUC 三段範圍 |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 `UG-G3-SB6` Brief（原表，2026-09-15 加範圍調整註記） | Goal／In Scope／Out of Scope／Affected Components／Tests／DoD 原規劃（方向性語意，本提案 §3.8 逐項對照修改） |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1 | 「條件勝率 (Selective) >60%」原目標數字保留、加狀態註記；本 Gate A 訂 Timeout gating 的新量化目標，不取代原數字 |
| `DECISIONS.md` `DEC-040`（`APPROVED`） | Holdout 邊界（折 33-42，`HOLDOUT_START_DATE=2025-10-23`）；`UG-G3-SB4`～`SB6` 全程不得讀取／訓練／評估／選擇 Holdout 資料 |
| `doc/upgrade/gates/closed/UG_G3_SB5_GATE_B_SUBMISSION.md` §2、§3 | TB 三段 AUC 表、Meta(A)-LR／Ridge 校準品質（Brier／log-loss／Platt 斜率） |
| `src/ml/calibration.py` | `CALIB_FIT_FOLDS=(27,28,29)`、`CALIB_EVAL_FOLDS=(30,31,32)`、`CALIBRATION_METHOD_BY_TARGET["target_triple_barrier"]=["sigmoid"]`、`fit_calibrator()`／`apply_calibrator()`／`evaluate_calibration_quality()` |
| `src/ml/stacking.py` | `TARGET_CLASS_DOMAINS`、`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` |
| `PROJECT_STATUS.md` §0.2 | `UG-G3-SB5` CLOSED 列，「下一步」指向本 Gate A |

---

## 2. Current State（唯讀查證，`VERIFIED THIS SESSION`）

### 2.1 校準基礎設施現況

`src/ml/calibration.py` 已提供 TB 的校準管線：`fit_calibrator()` 對 TB 回傳 3 個 OvR 校準器（`TARGET_CLASS_DOMAINS["target_triple_barrier"]` 順序 `[-1, 0, 1]`）；`apply_calibrator()` 對 dict 型校準器逐類別套用後 renormalize；`evaluate_calibration_quality()` 對 dict 校準器回傳逐類別 `{class: result_dict}`。**本 SB 尚無任何「門檻」或「gating 決策」相關函式——這是本提案要新增的部分，不是複用既有函式。**

### 2.2 Meta(A)-LR／Ridge 的 TB Timeout（class 0）校準品質（`VERIFIED THIS SESSION`，重讀 `UG_G3_SB5_calibration_report_target_triple_barrier.json`）

僅 `sigmoid`（Platt）可用（TB 的 Timeout 類 Calib-fit 僅 297 筆 <500，未達 Isotonic 門檻，`CALIBRATION_METHOD_BY_TARGET` 結構性排除）：

| 校準器 | `auc_calib_fit_raw`（class 0） | Platt slope（class 0） | Brier 前→後 | log-loss 前→後 | `calibration_not_meaningful` |
|---|---|---|---|---|---|
| Meta(A)-LR | 0.8295 | +1.2164 | 0.5287→0.5196 | 0.7993→0.7801 | `False` |
| Meta(A)-Ridge | 0.8382 | +4.8652 | 0.5769→0.5207 | 0.9528→0.7897 | `False` |

兩者校準前後 AUC 精確保留（正斜率，`calibration_not_meaningful=False`），皆為有效校準。Ridge 的 Calib-fit 原始 AUC 略高（0.8382 對 0.8295），起始 Brier 較差但校準後與 LR 接近（0.5207 對 0.5196）；兩者差距在小數點後兩位內，不構成單方壓倒性優勢——與 `UG-G3-SB4`／`SB5` 一貫的「LR／Ridge 並列不淘汰」原則一致（§3.2 據此提案）。

### 2.3 Timeout 類別基期（`VERIFIED THIS SESSION`，對 OOF parquet `split_segment=="meta_eval"` 依 `fold_id` 再切分 Calib-fit／Calib-eval）

| 段 | n | `-1` | `0`（Timeout） | `1` |
|---|---|---|---|---|
| Calib-fit（折 27-29） | 8,475 | 55.73%（4,723） | **3.50%（297）** | 40.77%（3,455） |
| Calib-eval（折 30-32） | 8,255 | 55.74%（4,601） | **4.71%（389）** | 39.55%（3,265） |

與 `UG_G3_SB5_calibration_report_target_triple_barrier.json` 的 `calib_fit_class_distribution`／`calib_eval_class_distribution` 逐位相符。**Timeout 是稀有類別（3.5%～4.7%）**——這是 §3.5 訂量化目標時必須納入的基本約束：任何 gating 規則的「精準度」都要對照這個基期評估提升倍數（lift），不能只看絕對百分比。

### 2.4 Meta-Eval 全段（折 27-32）四個 Specialist 的 OvR AUC（`VERIFIED THIS SESSION`，PO 上輪已獨立算過，本次重新核對，逐位相符）

| 類別 | lr | rf | lgbm | xgb |
|---|---|---|---|---|
| `-1` | 0.5248 | 0.5333 | 0.5267 | 0.5263 |
| `0`（Timeout） | 0.8828 | 0.8721 | 0.8737 | 0.8727 |
| `1` | 0.5119 | 0.5097 | 0.5050 | 0.5040 |

四個 Specialist 對 Timeout 類的判別力高度一致（0.87～0.88），方向類（`±1`）一致近隨機（0.50～0.53）——與 `RISK-030` 記載相符，本 SB 的 gating 對象選擇（§3.2）建立在這個一致性上。

### 2.5 門檻曲線與 regime 診斷（`VERIFIED THIS SESSION`，審查方 v1 複核提供，PM 獨立重現）

**重建方式**：`build_meta_learner_input()` 在 Meta-Train（折 0-26）重建 Meta(A)-LR／Ridge（設定逐字同 `UG-G3-SB4`／`ug_g3_sb5_calibration_report.py`：`StandardScaler` train-only、`LogisticRegression(max_iter=500, random_state=42)`、`RidgeClassifier(random_state=42)`），`decision_function()` 在 Calib-fit（折 27-29）以 `fit_calibrator(method="sigmoid")` 擬合，套到 Calib-eval（折 30-32）。**PM 重建的 class 0 `auc_calib_fit_raw`＝0.8295（LR）／0.8382（Ridge），與 `UG-G3-SB5` 證據 JSON 逐位相同**，證明是同一個校準器，非另一次獨立訓練。

**Calib-eval（n=8,255，Timeout 389，基期 4.71%）門檻曲線**（依校準後 `P₀` 由高到低 gate）：

| gate 比例 | 覆蓋率 | LR 精準度（倍數） | LR 召回 | Ridge 精準度（倍數） | Ridge 召回 |
|---|---|---|---|---|---|
| 1% | 99% | 50.6%（10.7×） | 10.8% | 43.4%（9.2×） | 9.3% |
| 5% | 95% | 38.3%（8.1×） | 40.6% | 37.3%（7.9×） | 39.6% |
| 10% | 90% | 28.1%（6.0×） | 59.6% | 28.3%（6.0×） | 60.2% |
| 15% | 85% | 22.2%（4.7×） | 70.7% | 23.3%（4.9×） | 74.0% |
| 20% | 80% | 19.6%（4.2×） | 83.0% | 19.8%（4.2×） | 83.8% |
| 30% | 70% | 14.3%（3.0×） | 91.0% | 14.8%（3.1×） | 94.1% |
| 50% | 50% | 9.2%（2.0×） | 97.9% | 9.3%（2.0×） | 98.2% |

**PM 獨立重現**：precision／lift／recall 全部逐位相符。門檻 `θ` 的具體數值在 PM 的一次性探測腳本裡與上表對不上（例如 gate=1% 處 LR 的 `θ`，PM 算出 0.293，上表對應 0.389）——**真正原因是 OvR 正規化，不是取法差異（審查方複核，PM 用正式管線重跑後確認）**：上表的 `θ` 來自只對 class 0 做單一 Platt、未正規化的中間值；PM 的探測腳本改用正式的 `apply_calibrator()`（三類 OvR 逐列正規化為和 1）取 class 0 欄，兩者 Spearman 相關 0.9999998，precision 在每個 gate 比例上完全相同，但正規化會讓**極少數列的排序互換**（gate=15% 處實測互換 2 列，恰好不影響該點的 precision 數值）。**本 SB 一律以正規化後（`apply_calibrator()` 輸出）的 `P₀` 定義 `θ`**——上表的 `θ` 欄位是未正規化的中間產物，不是本 SB 要用的定義；`precision`／`recall`／`coverage` 三個指標數值本身不受影響，仍照抄使用。

**方法論教訓**：兩份數字對不上時，「不影響結論」的判斷必須建立在**找到真正原因之後**，不能先猜一個聽起來合理的解釋就結案——這次的猜測（排序統計量／內插分位數的取法差異）方向錯了，只是剛好也無害；若差異的真正原因是別的（例如用錯了折、資料對錯行），同樣「precision 一樣所以沒事」的推論方式會把真正的問題蓋掉。

保留集方向比例：`-1` 由 55.7%（全段基期）緩升至 57～59%，`+1` 幾乎不動（40～41%）——位移量小，不作為 gating 決策依據，只列入 §3.3 的第三項指標供人工核對。

**Regime 診斷（`volatility_20d` 三分位，Calib-eval，切點 0.304／0.481）**：

| 分位 | n | Timeout 基期 | 校準後 `P₀` 的組內 AUC（LR） |
|---|---|---|---|
| 低波動 | 2,752 | **12.94%**（356 正例） | 0.776 |
| 中波動 | 2,751 | **1.16%**（32 正例） | 0.754 |
| 高波動 | 2,752 | **0.04%**（1 正例） | 未定義（正例數 <10，不報 AUC） |

PM 獨立重現：三組基期（12.94%／1.16%／0.04%）與 LR 組內 AUC（0.776／0.754）逐位相符；高波動組僅 1 個正例，AUC 在統計上無意義（`roc_auc_score` 在極端小樣本下對哪一列恰好是正例高度敏感，Ridge 算出的 0.15～0.20 區間數字即為此現象，本身不是可信的判別力估計）——本表已依裁決 (b) 只在正例數 ≥10 的組別報 AUC（見 §3.6）。這組數字直接支持 `UG-G3-SB5` Gate B §4 的 `INFERENCE`（Timeout 訊號大半是波動率水準本身）：低波動組的 Timeout 基期是高波動組的 300 倍以上。

---

## 3. PO 必答項逐一回應

### 3.1 明寫引用 `RISK-030` 排除 `target_up_down`

**設計規則（結構性，非流程提醒）**：本 SB 的所有程式碼、測試、報告腳本**一律不接受 `target_column="target_up_down"`**。提案要求：任何新函式若帶 `target_column` 參數，比照 `src/ml/stacking.py::select_best_specialist()`／`src/ml/calibration.py::fit_calibrator()` 已有的先例，在函式入口做值域檢查，只允許 `"target_triple_barrier"`；傳入 `"target_up_down"` 時拋 `ValueError`（訊息內文引用 `RISK-030`），而非靜默忽略或印警告。紅測需包含一個 known-FAIL：對新函式傳入 `target_column="target_up_down"` 必須拋例外（§5）。

不產出任何 up_down 的門檻、報告列、或圖表——**不是「跑了但不採用」，是「不跑」**，與 `DEC-041` Decision 1 逐字一致。

### 3.2 Gating 對象與校準器選擇

**Gating 對象**：`target_triple_barrier` Timeout 類（class 0）經 `src/ml/calibration.py::fit_calibrator()`／`apply_calibrator()` 校準後的機率，**不是** Specialist 的原始 OOF 機率、也不是未校準的 `decision_function()` 分數——校準的意義正是讓這個機率可以被當成「實際頻率」解讀（`UG-G3-SB5` 的整個目的），門檻選擇若跳過校準直接用原始分數，等於讓 SB5 的工作白做。

**校準器選擇（PO 裁決 (c)，2026-09-15）：Meta(A)-LR 為 gating 來源，事前宣告，不在 Calib-eval 上選。** 理由：`UG-G3-SB4` TB 段的 Best Single／Meta(A) 排名裡 Meta(A)-LR 已是表現最佳的 Meta-Learner；`UG-G3-SB5` 校準品質兩者相當（§2.2）；§2.5 的探測曲線在全部 gate 比例下幾乎重合（例如 gate=10%：LR 28.1% 對 Ridge 28.3%，差距在雜訊範圍內）。**在 Calib-eval 上再多選一個「校準器」維度，等於對只有 389 個正例的同一批資料多擬合一次雜訊**——這正是門檻選定已限定只用 Calib-eval（§3.4）要避免的事，不能因為校準器選擇不是「門檻」就當作例外。

**Meta(A)-Ridge 曲線並列揭露、不參與選擇**——報告仍完整列出兩者的門檻曲線（§2.5 已示範），供日後若 LR 的實際部署效果不如預期時的比較基準，但本 SB 的 gating 決策只依 LR。

`±1` 方向類機率**只揭露、不設門檻**（`DEC-041` Decision 2 原文）——報告仍列出兩者校準後機率供人工核對，但不進入任何 gating 決策邏輯。

### 3.3 Gating 評估指標的精確定義

定義四個核心量（**訂正 4**：v1 只有三項，缺 Timeout 召回，裁決 (a) 需要它），全部在 **Calib-eval 段（折 30-32，n=8,255）**上計算，`θ` 為 Timeout 校準後機率的門檻，`P₀(row)` 為該列 Timeout 校準後機率。

**`P₀` 的精確定義（§2.5 教訓落地）**：`P₀` 必須是 `src/ml/calibration.py::apply_calibrator()` 對 TB 三類 OvR 校準器**正規化後**輸出的 class 0 欄，**不得**自行對 class 0 另外做一次單一 Platt 擬合再直接使用（那是未正規化的中間值，數值上系統性偏高，見 §2.5）。gating 模組取得 `P₀` 的唯一合法路徑是呼叫 `apply_calibrator()` 取第 2 欄（`TARGET_CLASS_DOMAINS` 順序 `[-1,0,1]` 的索引 1），不得繞過此函式另行計算。

| 指標 | 定義 | 計算式 |
|---|---|---|
| **Gated-out Timeout 精準度** | 「說觀望」的那些列裡，真的是 Timeout 的比例 | `gated = {row : P₀(row) ≥ θ}`；`precision(θ) = \|{row∈gated : y=0}\| / \|gated\|` |
| **覆蓋率（Coverage）** | 沒被 gate 掉、保留給下游策略判斷的列比例 | `coverage(θ) = 1 - \|gated\| / n` |
| **Timeout 召回（Recall）** | 全部真正的 Timeout 列裡，有多少比例被成功 gate 掉 | `recall(θ) = \|{row∈gated : y=0}\| / \|{row : y=0}\|` |
| **保留集方向基期位移** | gate 掉可能的 Timeout 後，剩餘列裡 `±1` 的相對比例是否位移（不宣稱「勝率」，因方向本身不可預測，`RISK-030`） | `retained = {row : P₀(row) < θ}`；分別報告 `retained` 中 `y=-1`／`y=1` 的比例，與 Calib-eval 全段基期（55.74%／39.55%，§2.3）相減，得位移量 |

**θ 網格（訂正 1）**：v1 原提議 `{0.05, 0.10, …, 0.95}` 在校準後 `P₀` 的實際分布下不可行——`P₀` 中位數僅 0.014、p90 為 0.13、p99 為 0.39（§2.5），0.30 以上的網格點全是空集合，等於白算。改為**兩種網格並存**：(1) 等距細網格 `{0.005, 0.010, …, 0.60}`（涵蓋 99% 以上的實際 `P₀` 範圍）；(2) `P₀` 的實際分位數網格（例如每 1 個百分位一個切點），確保網格點落在資料實際分布內、不留空段。證據 JSON 對每個網格點同時記錄 `θ` 數值與對應的實際 gate 比例（見 §3.7），避免 §2.5 附註提到的「同一 precision／recall 對應不同 `θ` 數值表示法」造成的閱讀混淆。

**明確排除的解讀**：`precision(θ)` 高不代表「知道會不會漲跌」，只代表「知道這段時間可能盤整」——這個區分必須寫進報告的顯著位置（比照 `RISK-030` 對 `macro F1` 誤導性的既有揭露筆調），避免下游誤讀為方向判斷力。

### 3.4 門檻選定範圍與 Holdout 隔離

- `θ*` 的選定**只使用 Calib-eval（折 30-32）**，理由：`Calib-fit`（折 27-29）已用於擬合校準器本身（`PLATT_C=1e6` 的斜率／截距），若再用來選門檻，門檻會對同一段資料的雜訊過擬合兩次；`DEC-041` Decision 2 原文也明寫「門檻在 Calib-eval 段選定」。
- **Holdout（折 33-42）全程不碰（訂正 2）**：v1 提議的 `assert (df["split_segment"] != "holdout").all()` **結構性不可能失敗**——現行 OOF parquet 的 `split_segment` 定義域是 `{meta_train, meta_eval, purged}`，根本沒有 `"holdout"` 這個值可以違反，這個檢查永遠通過，屬於 `CLAUDE.md` §9A.1「為通過而寫，不是為偵測而寫」的反例，不計入證據。改為對**折序號與日期兩者**直接斷言（比照 `UG-G3-SB5` 探測腳本開頭已用的寫法）：`assert fold_id.max() <= 32` 且 `assert (trade_date < HOLDOUT_START_DATE).all()`（`HOLDOUT_START_DATE` 讀 `src/ml/stacking.py` 既有常數，不寫死日期字串）。
- **Known-FAIL 案例（§9A.2 要求，訂正 2 連動）**：紅測構造一個 mutant——手動在門檻計算的輸入 OOF 裡注入一列 `fold_id=33`（真實會落在 Holdout 範圍的折號），驗證上述兩個斷言必須至少有一個拋出；同時保留一個「乾淨輸入通過」的正控制測試，證明 guard 不是恆真也不是恆假。

### 3.5 Timeout gating 量化目標與基線對照

**基線定義（供對照，不需訓練任何模型）**：
1. **不 gating 基線**：`θ→+∞`（永不觀望），`coverage=100%`，`gated` 為空集，`precision` 依**訂正 5** 記為 `null`（見下）。
2. **隨機 gating 基線**：在給定覆蓋率下隨機抽同樣比例的列標記為「觀望」，其 Timeout 精準度的期望值 **等於 Calib-eval 全段基期 4.71%**（隨機抽樣不改變子集的類別比例的期望，解析結果，不需要模擬——**訂正 3**：v1 原提議跑隨機取樣驗證可重現性是多餘的，改法見 §5）。

**v1 的判準被審查方推翻，理由記錄如下**：v1 提議「`precision(θ) ≥3` 倍且 `coverage(θ) ≥50%`」，審查方用 §2.5 的實測曲線檢驗發現**從 gate 1% 到 30%（覆蓋率 70%～99%）整段都同時滿足這兩條**——判準釘不住任何 `θ*`。更根本的是覆蓋率地板防錯了方向：gate 得越多，精準度只會越往基期 4.71% 靠攏（gate 50% 時精準度僅 9.2%，仍 ≥3 倍門檻），**真正的退化解是另一端**（gate 1%：精準度 50.6%、覆蓋率 99%，同時滿足兩條件卻幾乎什麼都沒 gate 掉，召回只有 10.8%）——v1 缺的正是**召回**這一項。

**PO 裁決 (a)（2026-09-15，取代 v1 判準）：選定的 `θ*` 須同時滿足三項——覆蓋率 ≥80%、精準度提升 ≥4 倍（≥18.8%）、Timeout 召回 ≥60%。**

依 §2.5 的 LR 曲線核對可行性：gate=15%（覆蓋率 85%、精準度 4.7×、召回 70.7%）與 gate=20%（覆蓋率 80%、精準度 4.2×、召回 83.0%）皆同時滿足三項，gate=10%（覆蓋率 90%、精準度 6.0×、召回僅 59.6%）則因召回差 0.4 個百分點未達標——**可行區間大致落在 gate 11%～20%（覆蓋率 80%～89%）**，三項判準確實能圈出一個非空、非退化的區間，不像 v1 判準整段都通過。

**可行區間內的選點規則（Gate A 階段即釘住，不留到實作階段）**：**在滿足三項判準的 `θ` 集合內，取 Timeout 召回最高者；召回相同時取精準度較高者。** 理由：產品目的是避開 Timeout，覆蓋率 ≥80% 已是不可退讓的地板，在地板之上應把召回推到極限——依 §2.5 曲線，這會使選點落在可行區間覆蓋率 80% 附近的邊界（gate≈20% 一帶），報告需如實揭露「`θ*` 是把召回判準推到覆蓋率地板邊界的結果」，不得包裝成「自然收斂到最佳點」。精確 `θ*` 由實作階段用完整（非 §2.5 抽樣網格）的門檻曲線代入此規則計算，Gate A 只釘規則本身，不釘數值。

**明寫聲明（PO 裁決 (a) 原文要求）**：三項判準是**看過 §2.5 實測曲線之後訂的事後目標**，不是獨立於資料的先驗設計；本 SB **不得宣稱這個 `θ*` 在未來資料（例如 `UG-G3-SB7` 的 Holdout）上會穩定重現**——真正的樣本外檢驗留給 `UG-G3-SB7`，SB6 的產出是「在 Calib-eval 上可行」的門檻，不是「已驗證的規則」。

**訂正 5（邊界行為）**：`θ` 使 `gated` 為空集（例如 `θ` 設得極高或無限大）時，`precision(θ)` 必須明確記為 `null`（JSON 與程式碼皆同），**不得**回傳 `0`（會被誤讀成「完全不精準」）或回傳基期 `4.71%`（會被誤讀成「等同隨機」，兩者都是對「未定義」的錯誤偽裝）。`coverage(θ)` 與 `recall(θ)` 在空集情況下仍有明確定義（`coverage=100%`、`recall=0%`），只有 `precision` 因分母為零需要 `null`。

### 3.6 Regime Gating（原 Brief 的市場狀態軟門控）去留

**PO 裁決 (b)（2026-09-15）：接受折衷方案，改為必做項目（非「若核准」的選項）。**

理由：原 Brief 設計是「`volatility_20d`／`ma20_bias_ratio` 作為 Meta-Learner 連續輸入」，前提是 Meta-Learner 本身要重新訓練或至少重新納入這兩欄——但 `DEC-041` 的裁決是**校準既有、已關閉的 `UG-G3-SB4` Meta-Learner**，不重訓（`§0.5 #22` 已把「重訓」排除在 SB5／SB6 範圍外）。訓練一個新的 regime-conditioned 門控模型會牴觸「不重訓」的既有裁決，範圍膨脹。

**折衷方案的精確規格（依裁決 (b) 訂正）**：
- **只用 `volatility_20d` 三分位，不加 `ma20_bias_ratio`**——`ma20_bias_ratio` 不在 OOF parquet 內（§2.1／§2.5 用的 `X_eval` 只含 `META_REGIME_FEATURE_COLS` 中已隨 OOF 產生流程留存的欄），加它需要另外 join 凍結面板，範圍膨脹，且 `UG-G3-SB5` Gate B §4 的 `INFERENCE` 本來就只針對波動率立論，不涉及 `ma20_bias_ratio`。
- **明寫這是 `UG-G3-SB5` Gate B §4 `INFERENCE` 的驗證**（Timeout 訊號大半是波動率水準本身），不是獨立的新分析目的。§2.5 的實測（低波動基期 12.94% 對高波動 0.04%，落差 300 倍以上）已支持這個推論，寫入報告時標明 `INFERENCE`→部分驗證（仍非因果，只是相關性支持）。
- **組內正例數 <10 的組別不報 AUC，只報基期**（§2.5 高波動組僅 1 個正例，AUC 統計上無意義，Ridge 算出的 0.15～0.20 區間即是這個小樣本假象的示範）。
- **不訓練 regime 模型**——純唯讀分組統計，複用 §3.3 已定義的四個指標（此處指標的分母改為各組內的列數，而非全 Calib-eval）。
- **真正的 regime-conditioned gating 模型若日後需要**：另開候補案（比照方向預測特徵改進案 `PROJECT_STATUS.md` §0.5 #24 的處理方式），不在本 SB 範圍內，理由同上——避免與「不重訓」的既有裁決衝突。

### 3.7 Data Contract

**輸入**：
| 項目 | 來源 | 校驗 |
|---|---|---|
| OOF 矩陣 | `oof_target_triple_barrier_20260915_025542.parquet` | sha256 `b9c1d432…4f94466c`（本提案已重新核對） |
| 校準器 | `src/ml/calibration.py::fit_calibrator()`，`method="sigmoid"`，`target_column="target_triple_barrier"`，在 `CALIB_FIT_FOLDS` 上擬合 | 比照 `ug_g3_sb5_calibration_report.py` guard 5（`sb4_model_match`）精神，新增等價 guard：本 SB 重建的校準器品質數字（Brier／AUC／Platt slope）須與 `UG_G3_SB5_calibration_report_target_triple_barrier.json` 已核准數字逐位相符，證明「同一個校準器」 |

**產出**（新報告腳本，暫名 `scripts/verify/ug_g3_sb6_gating_report.py`）：
| 欄位 | 內容 |
|---|---|
| `threshold_curve` | 每個網格點的 `theta`（浮點值）、`gate_pct`（對應實際 gate 比例，訂正 1）、`precision`（`null` 表空集，訂正 5）、`coverage`、`recall`（訂正 4）、`retained_direction_shift`——**只 LR**（裁決 (c)：LR 為唯一 gating 來源） |
| `ridge_threshold_curve` | 同上結構，Ridge 版，**僅供對照揭露，不參與 `selected_theta` 的選擇** |
| `selected_theta` | 選定的 `θ*`（LR），對應 `gate_pct`／`coverage`／`precision`／`recall` |
| `selection_rationale` | 固定規則（§3.5）：可行區間內召回最高者，同召回取精準度較高者；此欄記錄實際套用此規則後選中的 `θ*` 對應數值與可行區間的完整候選清單，供人工核對規則有沒有套對 |
| `random_baseline_precision` | Calib-eval 全段 Timeout 基期（4.71%），解析值，供對照 |
| `regime_diagnostic` | §3.6 `volatility_20d` 三分位表：各組 `n`／`timeout_rate`／`auc`（正例 <10 則為 `null`） |
| `holdout_guard` | `{"fold_id_max": int, "trade_date_max": str, "holdout_start_date": str}`，兩個斷言的實際比較值（訂正 2，取代原 `holdout_row_count`——新 guard 不再依賴 `split_segment` 值域） |
| `script_commit`／`script_dirty` | 比照既有先例 |

**輸出檔案位置**：`doc/upgrade/gates/evidence/UG_G3_SB6_gating_report.json`，比照既有命名慣例。

### 3.8 與 `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 原 Brief 逐項對照

| 項目 | 原規劃（方向性語意） | 本提案修改 |
|---|---|---|
| Goal | 信心門檻過濾 + 市場狀態軟門控 | 改為：TB／Timeout 校準機率門檻過濾（「何時不交易」）；市場狀態降為必做診斷區塊（§3.6，裁決 (b)），非獨立模型 |
| Dependency | `UG-G3-SB5` | 不變 |
| In Scope | P≥θ_high→看多；P≤θ_low→避險；中間→觀望（三段方向性） | 改為二元：`P(Timeout)≥θ*`→觀望（不交易）；`P(Timeout)<θ*`→保留（不宣稱方向）；`volatility_20d` 降為事後診斷分組（三分位，不含 `ma20_bias_ratio`），非模型連續輸入 |
| Out of Scope | Benchmark (SB7)；UI 排名 (Gate-4) | 不變，另加：`target_up_down` 全部工作（`RISK-030`）；獨立 regime-conditioned 模型訓練（§3.6）；**裁決 (d)：`src/ml/predictor.py`／`src/ml/evaluator.py` 明列 Out of Scope** |
| Affected Components | `src/ml/predictor.py`, `src/ml/evaluator.py` | **裁決 (d)：改為 `src/ml/gating.py`（暫名，新模組）與 `scripts/verify/ug_g3_sb6_gating_report.py`（新報告腳本）；`src/ml/calibration.py` 唯讀複用（不修改）。`predictor.py`／`evaluator.py` 不在本 SB 觸及——gating 決策接入既有預測輸出路徑是否需要、如何接，留給 `UG-G3-SB7`／Gate-4 決定，不在本 SB 預先承諾** |
| Tests | `test_selective_coverage_rate`, `test_regime_gate_logic`, `test_threshold_adjustable` | `test_regime_gate_logic` 改為必做的診斷區塊測試（裁決 (b)）；新增 `test_up_down_rejected`（§3.1 known-FAIL）、`test_holdout_fold_and_date_guard`（§3.4 訂正 2 known-FAIL）、`test_random_baseline_analytic`（訂正 3）、`test_empty_gate_precision_is_null`（訂正 5） |
| DoD | 信心門檻可調；覆蓋率/勝率權衡可觀測；測試 PASS | 見 §8（新增裁決 (a) 三項量化判準與 `DEC-041` 轉 `APPROVED` 條件） |

### 3.9 `DEC-041` 轉 `APPROVED` 條件

寫入 §8 DoD 明確項目：**本 SB Gate B 通過、PO 核准結案時，`DEC-041` 狀態同步轉 `APPROVED`**（依 `PROJECT_STATUS.md` §0.5 #10 既有通則，`DEC-040` 已是先例）。結案 commit 需同步：`DECISIONS.md` 狀態列與 `Approved by`／核准日期；`TRACEABILITY.md` 條目 38 狀態；`gate0_contract_check.py` B13 重跑確認「待轉」清單不再含 `DEC-041`。

---

## 4. In Scope

1. `src/ml/calibration.py` 既有校準管線的**唯讀複用**（不修改該模組）：對 `target_triple_barrier` 套用 `fit_calibrator()`／`apply_calibrator()`，取得 Meta(A)-LR 的 Timeout 類校準後機率（裁決 (c)：LR 事前宣告為唯一 gating 來源，Ridge 僅並列揭露）。
2. 新的 gating 門檻選擇邏輯（暫名模組 `src/ml/gating.py`，待實作階段確認最終位置與是否需要）：`θ` 雙網格掃描（訂正 1）、§3.3 四指標計算、§3.5 裁決 (a) 三項量化判準的可行區間判定。
3. 新報告腳本 `scripts/verify/ug_g3_sb6_gating_report.py`：產出門檻曲線（LR 主、Ridge 對照）、選定結果、隨機基線對照（解析值，訂正 3）、`volatility_20d` regime 診斷區塊（**裁決 (b)：必做**）。
4. `target_up_down` 排除守衛（§3.1）與 Holdout 折序號／日期雙重守衛（§3.4 訂正 2）。

## Out of Scope

1. `target_up_down` 的任何工作（`RISK-030`，§3.1）。
2. 重訓 Meta-Learner 或任何 Specialist（維持 `UG-G3-SB4` 已關閉的模型不變）。
3. 獨立的 regime-conditioned gating 模型訓練（§3.6——只做唯讀診斷分組，不訓練模型）。
4. **`src/ml/predictor.py`／`src/ml/evaluator.py`（裁決 (d)，明列）**——gating 決策是否接入既有預測輸出路徑留給 `UG-G3-SB7`／Gate-4。
5. `UG-G3-SB7` Benchmark（最終 Holdout 績效宣稱，且 §3.5 明寫本 SB 的 `θ*` 不宣稱在 Holdout 上穩定重現）。
6. Gate-4 UI 呈現。
7. `ma20_bias_ratio`（regime 診斷只用 `volatility_20d`，裁決 (b)）。

---

## 5. Failure Semantics & Tests（規劃，紅測階段依此擴充）

| 場景 | 預期行為 | Known-FAIL 設計 |
|---|---|---|
| `target_column="target_up_down"` 傳入新函式 | 拋 `ValueError`，訊息引用 `RISK-030` | 直接呼叫並斷言拋出 |
| 門檻選定輸入混入 `fold_id=33`（訂正 2） | `fold_id.max()<=32` 或 `trade_date<HOLDOUT_START_DATE` 斷言至少一個拋出 | 注入一列 `fold_id=33` 的 mutant，斷言必須 FAIL（§9A.2）；另備一個乾淨輸入的正控制測試，證明非恆真恆假 |
| `θ` 使 `gated` 為空集（訂正 5） | `precision=null`；`coverage=100%`；`recall=0%`，三者皆為明確值，不靜默回傳 `0` 或拋未預期例外 | 空集合輸入的單元測試，斷言 `precision is None`（或 JSON 的 `null`），非 `0` |
| 隨機基線為解析值（訂正 3，取代 v1 的模擬式驗證） | `random_baseline_precision` 恰等於 Calib-eval 的 Timeout 比例（`0.0471`，容忍浮點誤差） | 正控制：比對報告輸出與獨立計算的基期相等；known-FAIL：餵入一個基期算錯的證據 JSON，guard 必須拋出 |
| LR／Ridge 校準器品質數字與 `UG-G3-SB5` 證據 JSON 不符 | 拋例外（比照既有 `sb4_model_match` guard 精神） | 故意扭曲一個係數，斷言 guard 攔截 |
| 裁決 (a) 三項判準的可行區間為空（例如若未來重跑資料分布改變） | 報告誠實揭露「無 `θ` 同時滿足三項」，不得放寬判準或隱藏此結果 | 構造一個三項判準互斥的合成資料集，斷言報告產出「無可行解」欄位而非拋例外或靜默選一個不合格的 `θ*` |
| regime 診斷組內正例數 <10（裁決 (b)） | 該組 `auc` 欄位為 `null`，只報 `timeout_rate` | 構造正例數=1 的合成分組，斷言 `auc is None` |
| `P₀` 的來源（§2.5／§3.3 教訓） | gating 模組計算出的 `P₀` 須與 `apply_calibrator()` 回傳的 class 0 欄（正規化後）逐位相等 | 故意讓 gating 模組改用未正規化的單一 Platt 輸出（mutant），斷言與 `apply_calibrator()` 官方輸出比對時 FAIL（容忍度需小於 §2.5 實測的正規化前後最大差距） |

---

## 6. Risks & Trade-offs

- **Timeout 稀有（3.5%～4.7%）意味著任何門檻選擇都建立在小樣本上**——Calib-eval 只有 389 個 Timeout 正例（折 30-32），`θ*` 的選定可能對這批樣本的雜訊敏感，§3.5 已明寫「不宣稱在未來資料上穩定重現」，真正的樣本外檢驗留給 `UG-G3-SB7`。
- **§3.5 裁決 (a) 的三項判準在 §2.5 抽樣網格上驗證過可行（區間約 gate 11%～20%），但抽樣網格與正式實作的細網格可能在區間邊界附近有微小出入**——若正式實作發現可行區間為空（機率低但非零，例如浮點誤差恰好落在邊界），依 §5 新增的 known-FAIL 場景處理：誠實回報，不放寬判準。
- **regime 診斷（§3.6）的高波動組樣本量極小（僅 1 個正例）**——裁決 (b) 已限定 <10 正例不報 AUC，但即使只看基期，1 個正例的比例估計本身信賴區間極寬，報告需標明這點，不宣稱「高波動時 Timeout 絕對不會發生」。
- **`predictor.py`／`evaluator.py` 明列 Out of Scope（裁決 (d)）降低了本 SB 的範圍風險**，但代價是 gating 決策目前只停留在報告／證據 JSON 層級，尚未接入任何實際預測輸出路徑——這個整合工作被推遲到 `UG-G3-SB7`／Gate-4，需要在那邊的 Gate A 提案中重新評估範圍。
- **OvR 正規化會讓極少數列的 `P₀` 排序與單一 Platt 輸出互換**（§2.5 實測 gate=15% 處 2 列互換）——這是已知、可解釋的性質（三類 OvR 機率各自獨立擬合後正規化為和 1，每列的分母不同），不是缺陷，對三項判準（裁決 (a)）的可行區間判定沒有實質影響（互換發生在精準度數值不變的情況下），但報告若逐列列出 gating 結果時需注意此性質，不宣稱排序在正規化前後完全一致。

---

## 7. E2E Verification Plan

1. **唯讀探測已完成**（v1 複核階段，審查方 + PM 各自獨立算過，§2.5）——三項量化判準（裁決 (a)）已用實測曲線核對可行，不再需要 Gate A 核准後的額外探測步驟；實作階段的紅測直接針對這批已確認的數字設計。
2. 紅測（依 §5 場景，含訂正 2/3/5 的新 known-FAIL）→ 送審 → 核准後建紅測 commit。
3. 實作（GREEN）：`src/ml/gating.py`（暫名）+ 報告腳本，門檻曲線（雙網格）產出需與 §2.5 的抽樣結果在重疊網格點上一致（作為實作正確性的交叉核對，不是新驗收標準，只是「同一 parquet、同一校準器」的自然推論）。
4. 全套測試 + `gate0_contract_check.py`，比照既有先例。
5. 段級報告全量執行（僅對 TB Meta(A)-LR 為主、Ridge 對照，不含 up_down）。
6. Gate B 送審，含 `DEC-041` 轉 `APPROVED` 的核對。

---

## 8. Definition of Done

1. `target_up_down` 排除守衛與 known-FAIL 通過（§3.1、§5）。
2. Holdout 折序號／日期雙重守衛與 known-FAIL 通過（§3.4 訂正 2、§5）。
3. `θ` 門檻曲線（LR 主、Ridge 對照）與隨機基線（解析值）對照皆已計算並寫入證據 JSON，雙網格（等距細網格＋分位數網格）皆涵蓋。
4. 裁決 (a) 三項量化判準（覆蓋率 ≥80%、精準度提升 ≥4×、召回 ≥60%）的可行區間，與**依固定選點規則（可行區間內召回最高，同召回取精準度較高，§3.5）**選定的 `θ*`，連同選擇理由明確記錄於證據 JSON 與報告文件；若正式實作結果與 §2.5 抽樣預期有出入（可行區間為空或位置顯著偏移），需誠實揭露並回報 PO，不得放寬判準或另訂選點規則使其「通過」。
5. §3.6 `volatility_20d` 三分位診斷區塊完成（**必做，裁決 (b)**），組內正例 <10 的組別 `auc` 正確記為 `null`。
6. 全套測試 PASS；`gate0_contract_check.py` 14/14 PASS。
7. `DECISIONS.md`／`TRACEABILITY.md`／`REMAINING_RISKS.md`／`SYSTEM_UPGRADE_MASTER_PLAN.md` §9 SB6 Brief 依實作結果更新，`predictor.py`／`evaluator.py` 出現在 Out of Scope（裁決 (d)）。
8. **`DEC-041` 狀態轉 `APPROVED`**（§3.9）。
9. `PROJECT_STATUS.md` §0.2 新增 `UG-G3-SB6` CLOSED 列，下一步指向 `UG-G3-SB7`。

---

## 9. Documentation Sync

Gate B 結案時比照 `UG-G3-SB5` 先例：`git mv` 本提案與 Gate B 送審文件至 `doc/upgrade/gates/closed/`；`DECISIONS.md`／`TRACEABILITY.md`／`REMAINING_RISKS.md`／`SYSTEM_UPGRADE_MASTER_PLAN.md`／`PROJECT_STATUS.md` 五份文件同步；`gate0_contract_check.py` 的 `DOC_PATHS` 依 `CLAUDE.md` §16.4 檢查是否需要更新（依 SB4／SB5 先例，預期不需要，但需重新查證非假設沿用）。

---

## 附註：commit 敘事準確性（訂正 6，兩個事實並列，不擇一）

`fe30ef2` commit body 的「PM 在核准訊息……把 §10 寫錯」一句需要訂正為兩個事實並列，各佔一半：

1. **§10 這個章節號的筆誤，源頭是 PO 在核准訊息（`UG-G3-SB5` Gate B 裁決 (d)）裡寫錯**——PO 上輪已確認。
2. **PM 把這個筆誤原樣照抄進 `DEC-041`／文件同步，未在送審前查證章節號是否正確**——這是 PM 自己的疏失，`fe30ef2` 的訂正說明裡已承認過。

兩者缺一都不完整：只寫 1 會顯得 PM 沒有查證責任；只寫 2（`fe30ef2` commit body 目前的寫法）會讓人以為 §10 這個錯誤數字是 PM 憑空寫出來的，模糊了它其實來自 PO 自己的訊息。依 `CLAUDE.md` §11A 不 amend 既有 commit；本 SB 的結案 commit 序列表會把兩個事實並列記錄，取代 `fe30ef2` 這句不完整的敘事。
