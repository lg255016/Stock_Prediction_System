# UG-G3-SB5 Gate A 提案：Probability Calibration

> **狀態**：**Gate A 已核准（2026-09-15，PO 核准）**。訂正版經審查方核對，五處訂正全部落地確認，五項裁決見 §9。§2.3 探測數字與 §2.4 逐折分布已由審查方獨立重現（`VERIFIED THIS SESSION`）。**下一步**：依 §13 產出紅測清單，先送審查方複核，通過後才建紅測 commit。
> **前置**：`UG-G3-SB4` 已於 2026-09-15 Gate B 核准結案（`da7eafc`）。
> **本提案階段唯讀**：僅查證現況、規劃設計，未修改任何業務程式碼、未動任何資料庫。全部數字為對 `UG-G3-SB4` 凍結 OOF parquet 的唯讀查證，**且全部查證限定在 Meta-Train 段（折 0-26）內部再切分，未使用 Meta-Eval 段（折 27-32）任何一列調整任何模型參數或門檻**，未碰 Holdout（折 33-42）。

---

## 0. 摘要

`UG-G3-SB4` 已完成 OOF Stacking，但留下一個尚未回答的問題：Meta-Eval 段實測顯示 up_down 的 `Meta(A)-LogisticRegression`／`Meta(A)-RidgeClassifier` 系統性劣於單一最佳 Specialist（macro F1 0.381/0.381 對 0.465），標準化係數量級極小（<0.05），機率分布緊縮在 0.5 附近。`UG-G3-SB4` Gate B 把三項候選成因（類別不平衡未加權、`argmax` 硬門檻、Specialist 間高度共線）登記為 `UG-G3-SB5` Gate A 必答項（`PROJECT_STATUS.md` §0.5 #22）。

本提案：(1) 對三項候選成因提供**真實驗證數字**（Meta-Train 內部切分，非假設）；(2) 設計校準資料集的切法，明說與 SB4 報告的重疊；(3) 提出 Isotonic／Platt 的選用判準（資料量驅動，非武斷選擇）；(4) 明定 LR／Ridge 皆校準、統一用 `decision_function()` 取原始分數；(5) 預先寫明校準能改變什麼、不能改變什麼，避免事後合理化。

---

## 1. Requirement Source

| 來源 | 內容 |
|---|---|
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB5 Brief | Goal／In Scope／Out of Scope／Affected Components／Tests／DoD |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §11.3 Measurement Template | 「Training/Validation: 前段資料, Purged Walk-Forward（模型選擇與校準）」「不得使用相同 Folds 同時進行模型選擇、門檻選擇與最終績效宣稱」 |
| `DECISIONS.md` DEC-040（APPROVED） | Gate 3 Holdout 邊界（折 33-42，`HOLDOUT_START_DATE=2025-10-23`）；`UG-G3-SB4`～`SB6` 全程不得讀取／訓練／評估／選擇 Holdout 資料 |
| `doc/upgrade/gates/closed/UG_G3_SB4_GATE_B_SUBMISSION.md` §2、§3(d) | 三層結構實測值；Meta-Learner 近零訊號的三項候選成因觀察 |
| `PROJECT_STATUS.md` §0.5 #22 | 三項候選成因分派：`class_weight`／共線性（VIF/降維）、`argmax` 門檻曲線／機率分布 → `UG-G3-SB5` Gate A 必答項；信心門檻 → `UG-G3-SB6` |
| `REMAINING_RISKS.md` RISK-009 | OOF Stacking 殘餘風險量化（欠擬合觀察），`UG-G3-SB7` 應同時檢視過擬合／欠擬合 |

---

## 2. Current State（唯讀查證，`VERIFIED THIS SESSION`）

### 2.1 `src/ml/stacking.py` 現況

尚無任何校準相關函式或常數。`build_meta_learner_input()`／`select_best_specialist()`／`assemble_oof_matrix()` 已存在且穩定（`UG-G3-SB4` 已凍結）。`SELECTION_METRIC="macro_f1"`、`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 為既有模組常數。

### 2.2 `RidgeClassifier` 沒有 `predict_proba`（`VERIFIED THIS SESSION`，sklearn 1.x 文件與容器內互動確認）

`sklearn.linear_model.RidgeClassifier` 以最小平方法在 `{-1,+1}` 編碼目標上求解，**不提供 `predict_proba`**，只有 `decision_function()`（線性判別分數）與 `predict()`。`LogisticRegression` 雖有原生 `predict_proba`，但 `UG-G3-SB4` 已發現其原始機率本身分布緊縮、係數量級極小——原生機率不能直接當作「已校準」的機率。**為讓 LR／Ridge 的校準管線一致、可比**，本提案 §4.4 統一用 `decision_function()` 作為兩者校準的輸入分數，不使用 LR 的原生 `predict_proba`。

### 2.3 三項候選成因的真實驗證（Meta-Train 內部切分：`calib_fit`=折 0-20 擬合，`calib_val`=折 21-26 驗證；`target_up_down`，`VERIFIED THIS SESSION`）

**切分理由**：`UG-G3-SB4` 的 Meta-Learner 已在全部 Meta-Train（折 0-26）上擬合完成並已 Gate B 核准，本查證**不影響、不重跑**該已核准結果，只是在 Meta-Train 內部另外切一刀，把折 21-26 當作純查證用的驗證集，折 0-20 重新擬合一個查證用的 LR（與 SB4 的 Meta-Learner是兩個獨立物件），藉此在完全不碰 Meta-Eval／Holdout 的前提下得到有意義的驗證數字。

| 查證項 | 設定 | 結果 |
|---|---|---|
| **(a) `class_weight` 未加權** | `LogisticRegression(max_iter=500)` vs `LogisticRegression(max_iter=500, class_weight="balanced")`，皆在 `calib_fit` 擬合、`calib_val` 評估 | 預設：recall(0)=0.8577／recall(1)=0.2020／macro F1=0.4866。`class_weight="balanced"`：recall(0)=0.5465／recall(1)=**0.5170**／macro F1=**0.5313**（+0.0447）。**強力支持**——比 `UG-G3-SB4` Gate B 原先「探測數字不支持」的初步判斷（僅依 Meta-Train 段整體類別比例 53.46%/46.54% 做的粗判）更明確：即使整體類別接近平衡，`class_weight="balanced"` 仍大幅改善少數類 recall 與 macro F1。 |
| **(b) `argmax` 硬門檻** | 對 (a) 預設設定的 `predict_proba` 在 `calib_val` 上算不同門檻的 precision/recall（class 1） | 門檻 0.50（預設）：僅 3,026/17,850 列被判為正類，recall=0.2020。門檻降至 0.45：13,799/17,850 列被判正類，recall=0.7968、precision=0.4703（僅略高於基期 0.4563）。**中等偏強支持**——原始分數確有可回收的排序訊號，但預設 0.5 門檻只擷取了分數分布最尾端的一小段；門檻本身是 `UG-G3-SB6`（選擇性推論）的職責，本 SB 只確認「校準後的機率仍保有這段可調整的空間」。 |
| **(c) Specialist 間高度共線** | VIF（人工計算，因容器內無 `statsmodels`）：**第一次計算誤把 `_A_p0`／`_A_p1` 兩欄都納入，因二分類下 `p0=1-p1` 恆成立，造成 8 個機率欄 VIF 全部 `inf`——這是欄位設計本身的必然結果，不是「Specialist 間共線」的證據，已重新只取 4 個 `_A_p1` 欄＋2 個 regime 欄（6 欄）計算** | `lgbm_A_p1`=7.15、`xgb_A_p1`=7.00、`rf_A_p1`=4.31、`lr_A_p1`=1.82、`ma20_bias_ratio`=1.12、`volatility_20d`=1.01。**中等支持**——`lgbm`／`xgb`（皆為梯度提升樹）VIF 超過常用門檻 5，與 `UG-G3-SB4` Gate B §3(d) 的兩兩相關係數（`lgbm`-`xgb` 最高 0.93）一致；`rf` 邊緣、`lr` 無虞。 |

**重要澄清（自我發現的量測錯誤，如實揭露）**：VIF 第一次計算把每個模型的 `p0`／`p1` 兩欄都當成獨立特徵，導致全部 8 欄 VIF 為 `inf`——這**不是**「4 個 Specialist 彼此完全共線」的證據，而是**同一個模型的兩個互補欄位（`p0+p1=1`）本身就是完美線性相依**，任何二分類的機率欄都會有這個現象，與 Specialist 之間的關係無關。重新只取「類別 1」欄位後才是有意義的共線性讀數。**此錯誤已修正，未寫入最終結論**，記錄於此供稽核。

**三項成因與「校準對象是哪個 Meta-Learner」的關係（PO 需決定的範圍問題）**：(a)(c) 的驗證結果指向「換一個訓練方式的 Meta-Learner 可能更好」，但**這是重新訓練 Meta-Learner 的問題，不是機率校準的問題**——`UG-G3-SB5` 依 Master Plan Brief 的範圍是「在既有模型輸出上做後驗機率校準」，不包含重新擬合 Meta-Learner 本身。若要把 `class_weight="balanced"` 或降低共線性（例如只保留 `lr`／`rf` 兩個機率欄）納入，等同於**重開 `UG-G3-SB4` 已核准結案的 Meta-Learner 設計**，超出本 SB 範圍。**PO 裁決（§9 #1）**：`UG-G3-SB5` 只校準 `UG-G3-SB4` 已核准的既有 LR／Ridge 輸出，(a)(c) 兩項發現登記為獨立候補案（附觸發條件，不在本 SB 內處理）；(b) 門檻本身留給 `UG-G3-SB6`。

### 2.4 Meta-Eval 段逐折類別分布（`VERIFIED THIS SESSION`，供 §4.1 校準集切分設計）

| target | 折 27 | 折 28 | 折 29 | 折 30 | 折 31 | 折 32 |
|---|---|---|---|---|---|---|
| `target_up_down`（0／1） | 1522/1478 | 1510/1476 | 1572/1410 | 1545/1440 | 1539/1461 | 1658/1338 |
| `target_triple_barrier`（-1／0／1） | 1696/82/1031 | 1455/87/1276 | 1572/128/1148 | 1525/152/1104 | 1537/155/1055 | 1539/82/1106 |

**TB 的 Timeout（class 0）在任一折都只有 82-155 列**——這是 §4.3 選用 Isotonic 還是 Platt 的關鍵依據。

---

## 3. PO 必答項回應（依你上一則訊息的五項逐一回答）

### 3.1（對應你的第 1 項）三項候選成因驗證結果——見 §2.3

驗證已完成，全部在 Meta-Train 內部切分，未動 Meta-Eval。**(a)(c) 的處置：PO 裁決不在本 SB 處理**（§9 #1），登記候補案並附觸發條件（`UG-G3-SB6` 門檻選定後視少數類 recall 是否回升決定是否開案）。

### 3.2（對應你的第 2 項）校準資料集切法——見 §4.1

**建議**：把 Meta-Eval（折 27-32）依時間序切成 `Calib-fit`（折 27-29）／`Calib-eval`（折 30-32），不新開一段、不碰 Holdout。與 SB4 報告的重疊**明說**（見 §4.1「與 SB4 報告的重疊」小節）。`test_calibration_data_isolation` 的斷言內容見 §6。

### 3.3（對應你的第 3 項）Isotonic／Platt 選用依據與單調性驗證——見 §4.3、§4.5

資料量驅動的判準：`Calib-fit` 段每個類別樣本數 <500 者不得用 Isotonic（TB 的 Timeout 類別 §2.4 顯示僅約 297-389 列）。up_down 兩類皆 >4,000 列，Isotonic／Platt 皆可，**兩者並列報告**（比照 SB4 LR/Ridge 不淘汰其一的既有原則）。TB 三類中 Timeout 類別不足，**強制用 Platt（`sigmoid`）**，不產出 TB 的 Isotonic 版本（避免小樣本下的階梯狀過擬合，屬結構性拒絕而非事後選擇）。

### 3.4（對應你的第 4 項）LR／Ridge 皆校準；`RidgeClassifier` 無 `predict_proba` 的處理——見 §2.2、§4.4

兩者皆校準（承接 `UG-G3-SB4` DoD「不淘汰其一」原則）。統一用 `decision_function()` 取原始分數再校準，不使用 LR 原生 `predict_proba`，確保兩者管線一致、可比。

### 3.5（對應你的第 5 項）校準能改變什麼、不能改變什麼——見 §4.6

**能改變**：機率的可信度（Brier score／log-loss／reliability diagram 的對齊程度）——校準後「模型說 55% 就真的接近 55% 發生」，機率本身變得可拿來做決策依據。**不能改變**：排序能力（AUC／PR-AUC 理論上完全不變，因 Isotonic／Platt 都是原始分數的單調轉換）。**訂正（PO 2026-09-15）**：固定門檻（0.5）下的 macro F1 **可能顯著改變**——這不是排序能力的改變，是切點位置被校準連帶移動的正常副作用（§2.3(b) 已證明切點移動 0.05 就讓正類預測列數變 4.6 倍），因此**不列為驗收項，也不解讀為判別力改善或惡化**。**預先寫明的驗收準則（§10 DoD）**：校準後 Brier score／log-loss 須不劣於未校準基準，AUC／PR-AUC 須與校準前相等（容忍浮點誤差）；macro F1 只揭露數字，不設驗收門檻。

---

## 4. 校準設計

### 4.1 校準資料集：Meta-Eval 內部切分為 `Calib-fit`／`Calib-eval`

| 段 | 折範圍 | up_down 列數 | TB 列數 |
|---|---|---|---|
| `Calib-fit` | 折 27-29 | 8,968（1: 4,364／0: 4,604） | 8,475（-1: 4,723／0: **297**／1: 3,455） |
| `Calib-eval` | 折 30-32 | 8,981（1: 4,239／0: 4,742） | 8,255（-1: 4,601／0: **389**／1: 3,265） |

**Alternatives Considered**：

1. **重新切 Meta-Train，保留一段給校準（不採納）**——需要重新擬合 `UG-G3-SB4` 已核准的 Meta-Learner（用更少折數），等於重開已結案的 SB4 設計，代價過高、也違反 Gate 治理「結案後不回頭改」的精神。
2. **直接用整個 Meta-Eval 當校準集，另外評估也在同一段（不採納）**——校準擬合與校準品質評估用同一批列，Isotonic 尤其容易在自己擬合過的資料上顯得「完美校準」，這是校準特有的過擬合風險，不是模型選擇意義下的洩漏，但同樣會製造虛假的信心。
3. **Meta-Eval 依時間序切 `Calib-fit`／`Calib-eval`（採納）**：Meta-Learner 從未在 Meta-Eval 任何一列上擬合過（`UG-G3-SB4` 的擬合只用 Meta-Train），所以 `Calib-fit` 對 Meta-Learner 本身是乾淨的樣本外資料；`Calib-eval` 對校準器（isotonic/platt）本身也是乾淨的樣本外資料。兩個不同物件（Meta-Learner、校準器）各自的「有沒有看過這批資料」都成立，是三個選項裡對「不循環驗證」最乾淨的設計。

**與 SB4 報告的重疊，明說**：`UG-G3-SB4` 已用**整個** Meta-Eval（折 27-32）報告過 `Meta(A)` vs `Best Single Specialist` 的**未校準**點預測比較（macro F1、逐類別 recall）。這與本 SB 的「機率校準品質」是不同問題——前者問「預測對不對」，後者問「說的機率準不準」。依 Master Plan §11.3 明文的限制「不得使用相同 Folds 同時進行模型選擇、門檻選擇與最終績效宣稱」：SB4 對 Meta-Eval 的使用是**報告**（不是選擇、不是門檻調整、也不是 Holdout 意義下的「最終績效宣稱」），本 SB 對 `Calib-fit`／`Calib-eval` 的使用是**校準擬合／校準品質評估**，同樣都不是「模型選擇」或「門檻選擇」或 Holdout 的「最終績效宣稱」——**不違反字面規則**。但誠實揭露：這 6 折資料已經是第二次被拿來做分析，讀者不應把 `Calib-eval` 的校準品質數字誤讀為「全新、完全未經任何分析的資料」。

### 4.2 新模組 `src/ml/calibration.py`

> **訂正（PO 2026-09-15，審查方實測）**：原設計擬包裝 `sklearn.calibration.CalibratedClassifierCV(cv="prefit")`，但容器內 sklearn 1.9.0 已移除 `cv="prefit"` 這個選項——`VERIFIED THIS SESSION`（PM 獨立重現）：
> ```
> InvalidParameterError: The 'cv' parameter of CalibratedClassifierCV must be an int in
> the range [2, inf), an object implementing 'split' and 'get_n_splits', an iterable or
> None. Got 'prefit' instead.
> ```
> 改為**手動校準器**，不使用 `CalibratedClassifierCV`／`FrozenEstimator`（其內部 CV 重訓行為不透明，且難以為此構造 known-FAIL 案例）：
> - **二分類（up_down）**：`IsotonicRegression(out_of_bounds="clip")` 直接對 `decision_function` 分數 → `y` 擬合；Platt 為手動擬合一個**只有一個輸入特徵**（該分數本身）的 `LogisticRegression`，把它的 `predict_proba` 當作校準後機率。
> - **多類別（TB）**：逐類別 One-vs-Rest——對每個類別各自的 `decision_function` 分數獨立擬合一個 Platt（`sigmoid`，因 §4.3 已排除 isotonic），得到三個「該類別為 1 vs 其餘」的校準機率，**逐列正規化**（三者相除各自總和）成和為 1。

| 函式 | 說明 |
|---|---|
| `fit_calibrator(raw_scores, y_true, method, target_column)` | 手動擬合校準器：二分類回傳單一 `IsotonicRegression` 或單一 1-D `LogisticRegression`（Platt）物件；多類別回傳一個「類別 → 1-D Platt 物件」的字典（逐類別 OvR，`method` 固定為 `sigmoid`，見 §4.3） |
| `apply_calibrator(calibrator, raw_scores)` | 對新的原始分數套用已擬合的校準器：二分類直接回傳單一機率欄；多類別先逐類別套用各自的 Platt 得到**正規化前**的三欄分數，再逐列正規化（相除各自總和）使三欄機率和為 1，回傳正規化後的三欄 |
| `assert_calibration_monotonic(raw_scores, calibrated_probs)` | 結構性檢查：**檢查對象是正規化前**的「單一類別原始分數 → 該類別校準機率」配對，排序後須非遞減，不符即拋 `CalibrationMonotonicityError`——**正規化後的三欄（TB）不保證各自單調**（分母隨列變動），這是多類別正規化的已知性質，不在本函式檢查範圍，`§4.5` 另外說明 |
| `CALIBRATION_METHOD_BY_TARGET` | 模組常數：`{"target_up_down": ["isotonic", "sigmoid"], "target_triple_barrier": ["sigmoid"]}`——TB 結構性排除 isotonic 選項，不是執行期判斷，是宣告層級的常數 |
| `MIN_MINORITY_SAMPLES_FOR_ISOTONIC` | 模組常數 `500`，`§3.3` 判準的具體數字，供測試斷言與未來若資料量變動時重新核對 |
| `CALIB_FIT_FOLDS` | 模組常數 `(27, 28, 29)`（§4.7） |
| `CALIB_EVAL_FOLDS` | 模組常數 `(30, 31, 32)`（§4.7） |
| `PLATT_C`（**新增，2026-09-15 訂正，GREEN 階段審查方發現**） | 模組常數 `1e6`。**Platt 為未正則化擬合**——`LogisticRegression()` 預設 `C=1.0`（L2 懲罰）對小尺度分數（`UG-G3-SB4` Meta-Learner 的 `decision_function` 正是此情況）會嚴重壓扁擬合斜率，把校準機率拉向 0.5，那是正則化的副作用不是校準。PM 獨立重現：合成資料（分數 std=0.05、真實 logit 斜率 40）C=1.0 擬合斜率 13.95、C=1e6 擬合 39.29（審查方原始數字 14.11／38.98，質性結論一致） |
| `brier_score_multiclass(y_true, calibrated_probs)`（**新增，2026-09-15 訂正**） | §4.8 定義的多類別 Brier score，函式本身進本模組（原設計誤放段級報告腳本），報告腳本只呼叫不自算；二分類是其特例 |
| `reliability_table(raw_scores_or_probs, y_true, n_bins=RELIABILITY_N_BINS)`（**新增，2026-09-15 訂正**） | 依 `RELIABILITY_N_BINS` 等寬分桶，回傳每桶的列數（`bin_counts`）、平均預測機率、實際發生頻率 |

### 4.3 Isotonic／Platt 選用判準（結構性，非執行期挑選）

`CALIBRATION_METHOD_BY_TARGET` 直接把「TB 不產出 isotonic」寫死為模組常數（依 §2.4 的既有實測列數決定，非每次執行時動態判斷「這批資料夠不夠」）——**理由**：動態判準本身難以寫出 known-FAIL 案例（怎樣的資料量算「不夠」，門檻本身若可在執行期任意調整，就失去反查法的意義，見 `CLAUDE.md` §9A.1）。改為「先用既有實測數字定案，若未來資料量改變（例如換一批凍結面板），需要重新審視這個常數本身，而不是讓程式自己動態決定」。

### 4.4 LR／Ridge 統一校準管線

```
raw_score = model.decision_function(X)   # LR 與 Ridge 皆有此方法
calibrator = fit_calibrator(raw_score[Calib-fit], y[Calib-fit], method=..., target_column=...)
calibrated_proba = apply_calibrator(calibrator, raw_score[Calib-eval])
```

**兩者皆校準，不淘汰其一**（承接 `UG-G3-SB4` DoD 第 6 項原則）。`Best Single Specialist`（lgbm／lr，依 target 而定）**不在本 SB 校準範圍**——它是 SB4 的對照基準，不是本 SB 的校準對象；若 PO 認為 SB6/SB7 需要一個校準過的 Best Single Specialist 才能公平比較，另案處理，不預先假設。

**LR 原生機率對照（PO 2026-09-15 追加，僅揭露不驗收）**：LR 校準管線的輸入是 `decision_function()` 而非它自己的 `predict_proba`（§2.2 理由）。段級報告額外並列 LR 原生 `predict_proba` 在 `Calib-eval` 上的 Brier score，作為「不做任何校準、直接用模型自己的機率」這個基準的對照——**只揭露，不作為驗收項，也不暗示校準版一定優於原生版**。

### 4.5 單調性驗證

`assert_calibration_monotonic()` 檢查**正規化前**的「單一類別 `raw_score` → 該類別校準機率」配對，排序後須非遞減。**known-FAIL**：構造一個刻意違反單調性的假校準器（例如對特定分數區間輸出隨機值），驗證函式必須拋出。

**TB 多類別的額外檢查**：三類別分別校準（正規化前）後，逐列正規化，驗證正規化後三欄機率和為 1（容忍浮點誤差 1e-9）——這是正規化步驟本身的結構完整性檢查，與單調性檢查是兩件事，**正規化後的三欄各自不保證單調**（因分母隨列變動而改變），不在 `assert_calibration_monotonic()` 的檢查範圍內，另立獨立函式或斷言。

**整體性檢查——訂正（PO 2026-09-15，紅測階段審查方實測發現）**：原文「校準前後 AUC 須相等」對 **Platt 成立、對 Isotonic 不成立**——Isotonic 是階梯函數，會把大量不同的原始分數壓成同一個輸出值（產生大量 ties），AUC 的計算方式對 ties 敏感，因此 AUC 前後出現非零差值**是這個方法本身的性質，不是實作缺陷**。審查方容器內合成資料示範（`VERIFIED THIS SESSION`，PM 獨立重現，質性結論一致，見紅測 commit）：500／5,000 列的合成資料，Isotonic 後 AUC 皆有 `+1e-2`／`+3e-3` 量級的正向偏移，相異輸出值數遠少於列數（如 15/500、36/5,000）；Platt 前後 AUC 差值恆為 0（連續分數幾乎不產生 ties，Platt 是嚴格單調的 1-1 變換）。**訂正後的檢查方式，依方法分流**：

- **Platt**：維持「AUC／PR-AUC 校準前後相等（容差 1e-9）」，不相等即拋 `CalibrationRankingViolationError`。**known-FAIL**：構造打亂排序的假校準器（例如把最高分與最低分對調）。
- **Isotonic**：AUC 相等**不再是檢查項**，改用**配對序檢查**（pairwise order check）——對任意兩列 `raw_score_i < raw_score_j`，必須 `calibrated_i ≤ calibrated_j`（允許相等，因 Isotonic 本就會產生相等輸出；只禁止反轉）；違反才拋 `CalibrationRankingViolationError`。AUC 前後差值**只計算、只揭露**（證據 JSON 記 `auc_before`／`auc_after`／`n_unique_calibrated_values`），不作為通過／失敗的判準。**known-FAIL**：假校準器製造至少一對分數反轉（`raw_score_i < raw_score_j` 但 `calibrated_i > calibrated_j`）。

### 4.6 預期結果（`ENGINEERING JUDGMENT`，實作前寫明，避免事後合理化）

> **訂正（PO 2026-09-15）**：原表格第二列「macro F1 預期無明顯變化」是錯的——單調轉換只保證**排序**不變（AUC／PR-AUC／逐桶單調不變），**不保證固定切點（如 0.5）的分類結果不變**。Platt 的截距與 Isotonic 的階梯函數形狀都會移動「原始分數多少算正類」這個切點的位置。§2.3(b) 自己的探測數字已經證明這件事：切點從 0.50 移到 0.45，正類預測列數從 3,026 變成 13,799——校準改變切點位置的方式，跟門檻調整改變切點位置的方式，數學上是同一件事。

| 指標 | 預期方向 |
|---|---|
| Brier score／log-loss（`Calib-eval` 上，校準後 vs 未校準） | **預期改善或持平**——這是校準要解決的問題本身 |
| AUC／PR-AUC（`Calib-eval` 上，校準後 vs 未校準） | **訂正（2026-09-15）：Platt 預期不變**（嚴格單調 1-1 變換，這是 §4.5 對 Platt 的驗收依據）；**Isotonic 預期有小幅非零差值**（階梯函數產生 ties 所致，`VERIFIED THIS SESSION` 合成資料示範 `+1e-2`～`+3e-3` 量級），**只揭露、不驗收**，Isotonic 的排序保持改驗配對序（§4.5） |
| macro F1（固定 0.5 門檻，`Calib-eval` 上，校準後 vs 未校準） | **可能顯著改變，方向未知**——只揭露數字與變化量，**不列為驗收項，也不解讀為「校準改善或惡化了判別力」**：判別力（排序能力）由 AUC 衡量且理論上不變，固定門檻下的分類指標變化純粹反映切點位置的移動，這是校準的正常副作用，不是校準的效果 |
| 校準後機率分布形狀 | **預期仍然緊縮**（不會突然變成漂亮的雙峰分布），但緊縮的位置應更貼近真實發生頻率 |

若 AUC／PR-AUC 校準前後不相等（超出浮點誤差範圍），代表校準器實作本身有 bug（破壞了排序），須在 Gate B 額外說明原因，不得默默略過；macro F1 的變化本身不需要「解釋原因」，只需要如實揭露數字。

### 4.7 `Calib-eval`（折 30-32）的資料預算——三次使用，逐一列出（PO 2026-09-15 追加）

`Calib-eval`（折 30-32）不是只被本 SB 用過一次，完整使用序列：

| # | SB | 用途 | 對機率／預測的影響 |
|---|---|---|---|
| 1 | `UG-G3-SB4` | 報告 `Meta(A)` vs `Best Single Specialist` 的**未校準**點預測比較（macro F1、逐類別 recall） | 只讀取、不調整任何參數 |
| 2 | `UG-G3-SB5`（本 SB） | 評估校準品質（Brier／log-loss／AUC／reliability） | 只讀取、不調整任何參數（校準器只在 `Calib-fit` 上 `fit()`） |
| 3 | `UG-G3-SB6`（PO 2026-09-15 裁決） | 在本 SB 產出的**校準後機率**上選定分類門檻 | 會實際決定一個門檻數字，是「門檻選擇」意義下的使用 |

**這不違反 Master Plan §11.3 的字面規則**——該規則禁止「同一批 Folds 同時做模型選擇、門檻選擇、最終績效宣稱」，上述三次使用中只有第 3 次（`UG-G3-SB6`）構成「門檻選擇」，且與模型選擇（`UG-G3-SB4` 在 Meta-Train 完成）、最終績效宣稱（`UG-G3-SB7` 的 Holdout）在時間與資料上都分離。**但這確實代表折 30-32 被連續三個 SB 分析，是全部三層結構中除 Holdout 外唯一被如此密集使用的一段**，本節如實記錄供未來稽核；`UG-G3-SB7` 的 Holdout（折 33-42）依 `DEC-040` 仍是唯一完全未被觸碰、保留給最終績效宣稱的資料。**本節內容擬作為 `UG-G3-SB5` Gate B 核准時，對 `DEC-040` 附註的草案文字**（`DEC-040` 決策本身不變，只是把這個既有 Holdout 隔離設計之外的「Calib-eval 三次使用」事實記錄進附註，供未來查閱時不需要另外拼湊三個 SB 的文件）。

### 4.8 Reliability 分桶與多類別 Brier 定義（PO 2026-09-15 追加，小項訂正）

- **Reliability 分桶**：模組常數 `RELIABILITY_N_BINS = 10`（等寬分桶，`[0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]`）。段級報告須揭露每桶的實際列數（`bin_counts`），供讀者判斷哪些桶樣本太少、reliability 數字不穩定。
- **多類別 Brier score 定義**（TB）：逐列 $\sum_{c} (p_c - \mathbb{1}[y=c])^2$（該列三個類別的校準機率與 one-hot 真實標籤的平方差總和），再對全部列取平均。**訂正（GREEN 階段，PM 自我發現，2026-09-15）**：二分類（up_down）並非此定義的代數等值特例，而是常見單一機率 Brier score 公式（$(p_1-y)^2$ 的平均）的 **2 倍**——$p_0=1-p_1$、$o_0=1-o_1$ 時 $(p_0-o_0)^2=(p_1-o_1)^2$，兩項相加即 $2(p_1-y)^2$，不是相等。容器內獨立驗證：合成資料 `multiclass=0.150`／`standard=0.075`，比值恰為 2（`VERIFIED THIS SESSION`）。實作（`src/ml/calibration.py::brier_score_multiclass`）採用完整 one-hot 加總定義，呼叫端若要與單一機率公式比較須自行乘以（或除以）2；原提案「等價」措辭有誤，已訂正。

---

## 5. In Scope

1. 新增 `src/ml/calibration.py`：`fit_calibrator`／`apply_calibrator`／`assert_calibration_monotonic`（手動 Isotonic／Platt，不用 `CalibratedClassifierCV`，見 §4.2）、`brier_score_multiclass`／`reliability_table`（**2026-09-15 訂正併入**：指標計算進模組本身，報告腳本只呼叫不自算），常數 `CALIBRATION_METHOD_BY_TARGET`／`MIN_MINORITY_SAMPLES_FOR_ISOTONIC`／`CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS`／`RELIABILITY_N_BINS`（§4.2-4.8）。
2. Meta-Eval 折 27-29／30-32 切分為 `Calib-fit`／`Calib-eval`，供 §4.1 使用；不新增欄位進 OOF parquet 本身（校準是下游消費者的行為，不回頭改動 `UG-G3-SB4` 已凍結的 OOF 檔案）。
3. 對兩個 target 的 `Meta(A)-LogisticRegression`／`Meta(A)-RidgeClassifier` 做校準（up_down 產出 isotonic+sigmoid 兩版，TB 只產出 sigmoid）。
4. 段級報告腳本：校準前後 Brier score／log-loss／AUC 對照、`Calib-eval` 段逐類別校準機率的 reliability 統計（10 個等寬分桶，揭露每桶列數）、LR 原生 `predict_proba` 的 Brier 對照（§4.4，僅揭露）。
5. 測試：`test_calibration_data_isolation`、`test_calibration_monotonicity`、`test_calibration_not_in_train`（既定命名，見 §6）。

## Out of Scope

- 重新訓練 Meta-Learner（`class_weight`、移除共線特徵等）——§2.3 (a)(c) 發現登記為獨立候補案（附觸發條件，見 §9 #1），不在本 SB 處理。
- 信心門檻與選擇性推論（`UG-G3-SB6`）——§2.3 (b) 的門檻曲線僅供參考，門檻本身的決定不在本 SB。
- `Best Single Specialist` 的校準——不是本 SB 校準對象（§4.4）。
- Holdout（折 33-42）與折 42 之後缺口的任何讀取——`DEC-040` 禁令延續。
- `expanding` 模式——`UG-G3-SB4` 未跑，本 SB 同樣不涉及。
- Benchmark 最終績效宣稱（`UG-G3-SB7`）。

---

## 6. Failure Semantics & Tests

| 情境 | 應有行為 | 對應測試 |
|---|---|---|
| 校準器 `fit()` 收到的列，`fold_id` 不是全部落在 `CALIB_FIT_FOLDS=(27,28,29)` | 結構性拒絕，拋專屬例外 | `test_calibration_data_isolation`（known-FAIL：混入 Meta-Train、`CALIB_EVAL_FOLDS` 或 Holdout 的列） |
| 校準品質評估函式收到的列，`fold_id` 不是全部落在 `CALIB_EVAL_FOLDS=(30,31,32)` | 結構性拒絕，拋專屬例外 | `test_calibration_not_in_train`（**訂正，PO 2026-09-15 定案**：`fit()`／`evaluate()` 兩個介面都強制要求傳入 `fold_id`（或等義的 `split_segment` 標記），`fit()` 只接受 `CALIB_FIT_FOLDS`、`evaluate()` 只接受 `CALIB_EVAL_FOLDS`，其他一律拋出——不是「待實作階段定案」，是本提案階段已定案的結構性拒絕，理由：Meta-Learner 本身的訓練資料是 Meta-Train，若校準品質評估不慎收到 Meta-Train 列，等於在模型已經看過的資料上評估「校準準不準」，是校準特有的循環驗證問題（§4.1 方案 2 已否決的理由）；known-FAIL：混入任一 Meta-Train 折號必拋） |
| `CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS` 折集合重疊 | 結構性拒絕（模組載入期斷言，非執行期檢查） | `test_calibration_data_isolation`（known-FAIL：以修改過的重疊常數匯入模組必拋） |
| 校準後機率（正規化前）非單調（違反排序保持） | 拋 `CalibrationMonotonicityError` | `test_calibration_monotonicity`（known-FAIL：構造刻意違反單調性的假校準器） |
**Platt**：校準前後 AUC／PR-AUC 不相等 | 拋 `CalibrationRankingViolationError`（PO 2026-09-15 定案：只能有一種行為，不留「或明確標示異常」的模糊空間） | 新增（known-FAIL：構造打亂排序的假校準器，如最高分與最低分對調） |
| **Isotonic（訂正，2026-09-15，紅測階段發現原「AUC 相等」判準對 Isotonic 不成立，見 §4.5）**：`raw_score_i < raw_score_j` 但 `calibrated_i > calibrated_j`（排序反轉） | 拋 `CalibrationRankingViolationError` | 新增（known-FAIL：假校準器製造至少一對分數反轉）——AUC 差值改為只計算揭露，不在此列拋例外 |
| TB 嘗試使用 `isotonic` 方法 | 結構性拒絕（`CALIBRATION_METHOD_BY_TARGET` 常數不含此選項） | 新增（known-FAIL：直接呼叫 `fit_calibrator(..., method="isotonic", target_column="target_triple_barrier")` 必拋） |
| 多類別（TB）正規化後三欄機率和不為 1 | 拋例外或明確排除該列 | 新增（known-FAIL：構造一組加總偏離 1 的合成機率） |

---

## 7. Risks & Trade-offs

- **Meta-Eval 折 27-29/30-32 的切分把一個原本 6 折的段再切一次**——樣本量對 TB 的 Timeout 類別本就偏少（§2.4），切一半後更少，這正是 §4.3 排除 TB isotonic 選項的原因，已在設計中處理，非未知風險。
- **§2.3 (a)(c) 發現不在本 SB 處理**（PO 2026-09-15 裁決，§9）——已附觸發條件：`UG-G3-SB6` 門檻選定後若少數類 recall 仍明顯低於 §2.3(a) 探測到的水準（`class_weight="balanced"` 的 recall(1)=0.517），開獨立候補案重訓 Meta-Learner；否則視為已由 SB6 的門檻工作回收，關閉此觀察。這是有觸發條件、非永久擱置的風險登記，不是「已知有更好做法但暫不採用」。
- **`decision_function()` 統一管線犧牲了 LR 原生 `predict_proba` 的資訊**——這是刻意選擇（§2.2 理由），已在 §4.4 補上 LR 原生機率 Brier 作為揭露性對照，緩解「讀者看不到原生機率表現」的疑慮。
- **校準品質評估本身依賴 `Calib-eval` 只有 3 折**——若 3 折剛好在時間上有特殊性（例如某段市場劇烈波動），校準品質數字可能不具代表性，本 SB 不修正，如實揭露。
- **`Calib-eval`（折 30-32）被連續三個 SB 使用**（SB4 報告、SB5 校準評估、SB6 門檻選擇，§4.7）——不違反 Master Plan §11.3 字面規則，但已如實記錄供未來稽核，不視為需要修正的問題。

---

## 8. E2E Verification Plan

1. 容器內全套測試 PASS。
2. `gate0_contract_check.py` exit 0。
3. `Calib-fit`／`Calib-eval` 的折集合、列數、類別分布寫入證據 JSON，與 §2.4 實測值核對一致。
4. 校準前後 Brier score／log-loss／AUC 對照，兩個 target、兩個 Meta-Learner（up_down 另外 isotonic vs sigmoid 兩版）並列報告；LR 原生 `predict_proba` Brier 對照（僅揭露）一併列出。
5. 單調性驗證通過（正規化前），TB 正規化後三欄機率和為 1 的驗證通過。
6. 校準前後 AUC／PR-AUC 相等（§4.5 整體性檢查），reliability 分桶（10 桶）逐桶列數揭露。
7. §6 全部測試皆需 known-FAIL 案例，實際執行並附原始輸出。
8. 校準後 macro F1 變化量如實揭露（§4.6），不要求特定方向、不需解釋原因；AUC 若不相等則須說明原因（視為實作缺陷）。

---

## 9. PO 裁決（2026-09-15，四項待裁決皆依提案立場核准，另加一項新裁決）

| # | 問題 | PO 裁決 |
|---|---|---|
| 1 | §2.3 (a)(c) 的發現（`class_weight`、降低共線輸入）是否另開候補案，或本 SB 順便處理？ | **核准：不在本 SB 處理，不重訓 Meta-Learner。** 登記 `PROJECT_STATUS.md` §0.5（附 §2.3 數字）。**觸發條件**：`UG-G3-SB6` 門檻選定後，若少數類 recall 仍明顯低於 §2.3(a) 探測到的水準（`class_weight="balanced"` 的 recall(1)=0.517），開獨立候補案（暫名 `SB4a`）重訓 Meta-Learner；否則視為已由 SB6 門檻工作回收，關閉此觀察。**理由**：§2.3(b) 已證明原始分數確有排序訊號，`class_weight` 的效果本質上接近移動決策切點，`UG-G3-SB6` 的門檻選擇工作可以回收這個效果，不一定需要重訓模型 |
| 2 | `Calib-fit`／`Calib-eval` 折 27-29／30-32 的切法（3+3）是否可接受？ | **核准** |
| 3 | TB 結構性排除 isotonic、門檻常數 500 是否可接受？ | **核准** |
| 4 | `Best Single Specialist` 是否需要在本 SB 一併校準？ | **核准（不需要）** |
| 5（新裁決） | `UG-G3-SB6` 的門檻選擇資料段是哪裡？ | **`Calib-eval`（折 30-32）的校準後機率**——見 §4.7「資料預算」，本 SB 的校準輸出直接是 SB6 門檻選擇的輸入 |

**訂正版核對通過即核准，授權提案單檔 commit**；接著依 §13 產出紅測清單，比照 `UG-G3-SB4` 先例送審查方複核。

---

## 10. Definition of Done

- `src/ml/calibration.py` 新建，手動 Isotonic／Platt 校準（`fit_calibrator`／`apply_calibrator`／`assert_calibration_monotonic`）落地並被測試覆蓋，不依賴 `CalibratedClassifierCV`。
- 校準資料集依 §4.1 切分（`CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS` 模組常數），證據 JSON 記錄折集合、列數、類別分布，與 §2.4 核對一致。
- 兩個 target 的 LR／Ridge 皆完成校準（up_down 產出 isotonic+sigmoid，TB 只產出 sigmoid），不淘汰任一 Meta-Learner；LR 原生 `predict_proba` Brier 對照一併揭露。
- 單調性驗證通過（正規化前）；TB 正規化後多類別機率和為 1 驗證通過；校準前後 AUC／PR-AUC 相等驗證通過。
- 校準前後 Brier score／log-loss／AUC 並列報告；macro F1 變化量如實揭露（不要求特定方向）；若 AUC 不相等須附原因說明（視為實作缺陷）。
- `test_calibration_not_in_train` 落地為結構性拒絕（§6），`fit()`／`evaluate()` 分別只接受 `CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS`。
- 全套測試 PASS；`gate0_contract_check.py` exit 0；§6 全部 known-FAIL 案例已實際執行並附原始輸出。
- §9 五項 PO 裁決已全部落地（含 #1 的 `PROJECT_STATUS.md` §0.5 登記、#5 的 SB6 資料段確認）。

---

## 11. Documentation Sync

- `PROJECT_STATUS.md` §0.5：新增一項登記 §2.3(a)(c) 發現與 §9 #1 的觸發條件（`SB4a` 候補案，非現在開）。
- `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB5 Brief：Gate B 結案時訂正 Affected Components。
- `REMAINING_RISKS.md` RISK-009：視校準結果是否改變「欠擬合」判斷，Gate B 時視需要更新。
- `DECISIONS.md` DEC-040：Gate B 核准時附註 §4.7「`Calib-eval` 資料預算」的三次使用記錄（決策本身不變，只是附註新事實）。
- 無新 ADR 草案於本提案階段——校準方法選用（Isotonic vs Platt 的判準常數）是否需要 ADR 留待 Gate B 依實測結果決定，若判準本身在實作中有重大調整才需要。

---

## 12. 未獲核准前（實作 commit 前）的自我約束

- 不修改 `src/ml/` 任何檔案、不新增 `calibration.py`。
- 不對任何資料庫執行寫入或 schema 查詢以外的操作。
- 不使用 Meta-Eval 段任何一列調整任何模型參數或門檻——§2.3 的全部驗證僅在 Meta-Train 內部切分完成。
- 本提案所有數字（VIF、recall、precision、macro F1、折級類別分布）均為唯讀查證所得，已標示查證方式與一次自我發現並訂正的量測錯誤（§2.3 VIF）。

---

## 13. Gate A 核准後、紅測前的流程（比照 `UG-G3-SB4` 先例）

1. **先產出紅測清單**（不是紅測本身），送審查方複核，涵蓋 §6 全部情境。
2. **審查方複核紅測清單後**，才授權建立紅測 commit（RED）。
3. **紅測 commit 通過後**，才開始實作（GREEN）。
4. 本 SB 全程對凍結 OOF parquet 運算，不涉真實庫寫入。
