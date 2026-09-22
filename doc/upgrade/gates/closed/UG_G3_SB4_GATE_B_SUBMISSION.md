# UG-G3-SB4 Gate B 送審：OOF Stacking Meta-Learner

> **狀態**：**Gate B 已核准（2026-09-15，PO 核准）**。審查方逐節讀完並獨立重現 §3(d) 探測數字（類別平衡 53.46／46.54、係數最大 0.0396／0.0495、73.2% 落在 (0.45,0.55)、相關 0.61～0.93），§4 對 SB3「中位數」描述正確，§11 常數測試為封閉釘值——**草稿內容本身無需訂正**。
> **對應 Gate A 提案**：`doc/upgrade/gates/UG_G3_SB4_GATE_A_PROPOSAL.md`（v3，PO 核准 `be64f9b`）。
> **本 SB 全程無真實庫寫入**，不適用 RISK-013 三項協議；全程對 `UG-G3-SB3` 凍結面板 parquet 運算。

---

## 1. 完整 Commit 序列

依時間序，Gate A 核准（`be64f9b`）之後至今：

| # | Commit | 內容 |
|---|--------|------|
| 0 | `be64f9b` | Gate A 提案 v3 核准（三層結構、二階 Purge、Data Contract、Arm A only） |
| 1 | `e46a8a7` | 紅測（RED）——OOF Stacking Meta-Learner 14 項，`src/ml/stacking.py` 尚不存在 |
| 2 | `69f6e35` | 紅測訂正——二階 purge 測試盲點（夾具全純 `meta_train`，未測混入真 `meta_eval` 列），+4 項 |
| 3 | `dcf48c5` | ✅ 實作（GREEN）——`src/ml/stacking.py` 新建，14 項紅測轉綠，自我反查法追加 2 項（機率欄索引對齊、Holdout 半折洩漏），修正 1 處測試夾具錯誤 |
| 4 | `a1abcf4` | 紅測——審查方複核發現 5 個「靜默通過」契約缺口（regime/機率欄完整性、重複鍵、序列長度、模型完整性、固定 `labels=`） |
| 5 | `433cae0` | ✅ 實作——5 個結構性拒絕補上 |
| 6 | `da73153` | 紅測——P6/P7，`target_column` 未核對真定義域，`select_best_specialist` 有危險預設值 |
| 7 | `a8fe533` | ✅ 實作——`select_best_specialist` `target_column` 改必填＋值域核對；`build_meta_learner_input` 選用 `target_column` 值域核對 |
| 8 | `9f86b88` | ✅ 新增 `scripts/verify/ug_g3_sb4_oof_generation.py`／`ug_g3_sb4_meta_learner_report.py`（單折/28折探測，未跑全量） |
| 9 | `e9ac8da` | 紅測——審查方對真實凍結面板重算發現 3 個正確性問題（守衛常數為原始列數非保留列數、迴圈繞過 `iter_oof_folds()`、`argmax` 遇 NaN） |
| 10 | `c328805` | ✅ 修正上述 3 項＋`stacking.py` 契約小擴張（`return_retained_index`，P8）＋報告腳本新增揭露（訊號列數、多數類基線、逐類別 recall、LR `n_iter_`） |
| 11 | `3ba80b6` | ✅ **全量**——`target_up_down`／`target_triple_barrier` 各一次 OOF 產生（folds 0-32）＋段級報告，4 份證據 JSON |

**四份證據 JSON 的 sha256**：

| 檔案 | sha256 |
|---|---|
| `UG_G3_SB4_oof_generation_target_up_down.json` | 內容見檔案本身（含 `oof_parquet_sha256=de1998519aca799eba5df179f2909070d43162c1add1a33599b79669f0a8c1ba`） |
| `UG_G3_SB4_oof_generation_target_triple_barrier.json` | 內容見檔案本身（含 `oof_parquet_sha256=b9c1d432f0912a2cf9e2a3b3e544d32a57efb45464fc500646a34a7d6f94466c`） |
| `UG_G3_SB4_meta_learner_report_target_up_down.json` | 內容見檔案本身 |
| `UG_G3_SB4_meta_learner_report_target_triple_barrier.json` | 內容見檔案本身 |

OOF parquet（**不進版控**，路徑與 sha256 記於證據 JSON 及 `3ba80b6` commit body）：`D:\Python\Database_Backups\Stock_Prediction_System2\ml_panels\oof_target_up_down_20260915_024419.parquet`、`...\oof_target_triple_barrier_20260915_025542.parquet`。

---

## 2. 三層結構落地與六項守衛實測值

### 2.1 三層結構（`DEC-040`）

| 段 | 折範圍 | 起訖日 | 說明 |
|---|---|---|---|
| Meta-Train | 折 0～26（27 折） | ～2025-04-30 | 二階 Purge 前 80,968（up_down）／74,394（TB） |
| Meta-Eval | 折 27～32（6 折） | 2025-05-02～2025-10-22 | 17,949（up_down）／16,730（TB），二階 Purge 不動此段 |
| Holdout（本 SB 不碰） | 折 33～42（10 折） | 2025-10-23～2026-08-20 | `HOLDOUT_START_DATE` 守衛，本 SB 訓練迴圈本身止於折 32，Holdout 折的資料未進入 `prepare_fold_data()` |

### 2.2 OOF 產生六項守衛（兩個 target 皆全數 PASS，實測值）

| # | 守衛 | target_up_down | target_triple_barrier |
|---|---|---|---|
| 1 | panel sha256 == 常數 | `39dc6b8e...eabbd014` 相符 | `4c4657c4...024db9b3f729` 相符 |
| 2 | 折 27／33 測試窗起日 == 常數 | 相符（未 abort） | 相符（未 abort） |
| 3 | 零 Holdout 列（`reject_rows_at_or_after`） | 相符 | 相符 |
| 4 | 二階 Purge 排除列數 == 常數 | **150** | **680**（訂正自原始列數 750，見 §3(e)訂正記錄） |
| 5 | Purge 前 meta_train／meta_eval == 常數 | 80,968／17,949 | 74,394／16,730 |
| 6 | 每折 `purge_mode=="exact"` | 相符 | 相符 |

`row_counts`（Purge 後）：up_down `{total:98917, meta_train:80818, meta_eval:17949, purged:150}`；TB `{total:91124, meta_train:73714, meta_eval:16730, purged:680}`。

`fold_timings` 總耗時：up_down 22.10s（33 折）、TB 31.83s（33 折）。

### 2.3 段級報告四項守衛（兩個 target 皆全數 PASS）

OOF parquet sha256 對應、`split_segment` 值域、三段列數對應 OOF 產生證據 JSON、零 Holdout 列二次確認——四項皆未 abort。

### 2.4 兩個 target 的四者並列（Meta-Eval 段，含逐類別 recall 與 support）

**target_up_down**（support: class0=9,346, class1=8,603, n_eval=17,949）：

| | macro F1 | recall(0) | recall(1) |
|---|---|---|---|
| Majority Baseline | 0.3424 | 1.0000 | 0.0000 |
| Meta(A)-LogisticRegression | 0.3812 | 0.9581 | 0.0473 |
| Meta(A)-RidgeClassifier | 0.3807 | 0.9583 | 0.0467 |
| Best Single Specialist（**lgbm**，Meta-Train 選） | **0.4654** | 0.7617 | 0.2339 |

`ranking_df`（Meta-Train，n_rows 皆 80,818）：lgbm 0.4894 > xgb 0.4888 > rf 0.4865 > lr 0.4754。

**target_triple_barrier**（support: class-1=9,324, class0=686, class1=6,720, n_eval=16,730）：

| | macro F1 | recall(-1) | recall(0) | recall(1) |
|---|---|---|---|---|
| Majority Baseline | 0.2386 | 1.0000 | 0.0000 | 0.0000 |
| Meta(A)-LogisticRegression | **0.3175** | 0.9858 | 0.1618 | 0.0036 |
| Meta(A)-RidgeClassifier | 0.3006 | 0.9891 | 0.1166 | 0.0033 |
| Best Single Specialist（**lr**，Meta-Train 選） | 0.3043 | 0.9740 | 0.1079 | 0.0150 |

`ranking_df`（Meta-Train，n_rows 皆 73,714）：lr 0.3961 > lgbm 0.3943 > rf 0.3791 > xgb 0.3726。

其餘揭露：`train_exclusions`／`eval_exclusions` 兩個 target 皆只有 `segment_mismatch` 一個鍵（無額外 NaN 排除）；LR `n_iter_`：up_down=6、TB=40，兩者 `n_convergence_warnings=0`；`signal_row_counts` 兩個 target 皆 `{meta_train:0, meta_eval:0, holdout_cited_from_gate_a_2_5:630}`。

---

## 3. 事實揭露（照實列出，不下結論、不迴避）

**(a) up_down 的 `Meta(A)` 兩者（0.3812／0.3807）低於最佳單一 Specialist（0.4654）**，少數類（class 1）recall 0.0473／0.0467 對 lgbm 的 0.2339——差距達 5 倍。

**(b) TB 的 `Meta(A)-LR`（0.3175）略高於最佳單一（0.3043）**，差距主要來自 Timeout（class 0）recall 0.1618 對 0.1079；獲利出場（class 1）recall 兩者都 <0.02（0.0036／0.0150），對 macro F1 的貢獻可忽略。

**(c) 兩個 target 的 Meta-Learner 都逼近多數類預測**：up_down 兩個 Meta(A) 的多數類（class 0）recall 皆 >0.95；TB 兩個 Meta(A) 的多數類（class -1）recall 皆 >0.98。

**(d) 審查方觀察，經 PM 獨立重現（探測腳本，不進版控，`probe_meta_lr_coef.py`）**：up_down 的 Meta(A)-LR 在標準化（`StandardScaler`）後，對 8 個 OOF 機率欄的係數絕對值全 <0.05（實測最大值 `rf_A_p1`/`rf_A_p0` = 0.0396；`ma20_bias_ratio` 反而是全部 10 個特徵中係數絕對值最大者，0.0495）。

`INFERENCE`（非既有規格或研究依據，PM 獨立重現支持此推論但非唯一可能解釋）：**Meta-Learner 幾乎沒有從 OOF 機率欄學到有區別力的訊號**——係數量級遠小於典型有效特徵，且 `predict_proba` 在 Meta-Eval 段的 class-1 機率分布幾乎全部擠在 0.34～0.94 但均值僅 0.4634、標準差僅 0.028，73%（13,140/17,949）落在 (0.45, 0.55) 窄帶內，`predict()` 的硬 argmax（0.5 門檻）因此把絕大多數列判給多數類。

**可能成因與各自驗證方式（提出，未在本 SB 內執行，交 PO 裁決是否處理）**：

| 候選成因 | PM 探測支持證據 | 驗證方式 |
|---|---|---|
| 1. 類別不平衡未加權 | **較弱**——Meta-Train 段 up_down 類別平衡（0/1 = 53.46%/46.54%），非極端失衡，探測數字不支持這是 up_down 的主因；TB 的 Timeout（class 0）僅約 4%，較可能是 TB 的部分成因，但 TB 的 LR 反而是三者中 macro F1 最高者，方向不一致 | 用 `class_weight="balanced"` 重 fit，比較係數量級與少數類 recall 變化 |
| 2. `argmax` 硬門檻對 SB6 前的評估不利 | **較強**——探測顯示 class-1 機率分布緊縮在 0.5 附近（std=0.028），73% 落在 (0.45,0.55)；SB6 才會做信心門檻/軟門控，SB4 現在用固定 0.5 門檻評估 | 對 Meta-Eval 段畫 precision-recall 曲線／不同門檻下的 recall，觀察是否存在門檻能顯著改善少數類 recall 且 precision 損失可接受 |
| 3. Specialist 之間高度相關 | **較強**——探測顯示 4 個 Specialist 的 class-1 OOF 機率兩兩相關係數 0.61～0.93（lgbm-xgb 最高 0.93，lr 與其餘三者最低約 0.61～0.67）；Meta-Learner 的輸入本質上接近 4 份高度共線的重複訊號 | 計算 VIF（variance inflation factor）或用 L1/PCA 降維後的子集重 fit，觀察 macro F1／係數是否顯著變化 |

三項候選成因**互不排斥**，探測數字對 2、3 支持較強，對 1（至少對 up_down）支持較弱。**PO 裁決（2026-09-15）：不在 SB4 內處理，SB4 誠實結案**。登記方式：`PROJECT_STATUS.md` §0.5 新增一項「Meta-Learner 幾乎未從 OOF 學到訊號（本 SB Gate B §3(d)）」，三項候選成因逐一列出驗證方式與去處——**門檻曲線與機率分布歸 `UG-G3-SB5`（機率校準）Gate A 必答項**；**信心門檻歸 `UG-G3-SB6`**；**`class_weight` 與共線性（VIF／降維）歸 `UG-G3-SB5` Gate A 必答項**（理由：決定校準對象是哪一個 Meta-Learner 之前，必須先回答這個問題）。

**(e) 訂正記錄**：`target_triple_barrier` 的二階 Purge 排除數在 Gate A 提案 §2.6 原載 750（面板原始列數，含 70 列標籤本身為 NULL 的列），審查方對凍結面板重算 OOF 保留列數（`prepare_fold_data()` 規則 (a)(b) 之後）發現正確基準是 **680**，已於 `c328805` 訂正並經 PM 獨立重算相符（見 §7 訂正記錄小節）。

---

## 4. 與 SB3 的對照（不同評估段，不可直接比，僅並列）

| | SB4 Best Single Specialist（Meta-Eval 段，折 27-32） | SB3（43 折全量中位數，Arm A） |
|---|---|---|
| target_up_down | 0.4654 | 0.45–0.49（落在區間內） |
| target_triple_barrier | 0.3043 | 0.34–0.37（略低於區間） |

**評估段不同**：SB3 是 43 折全量的逐折中位數（涵蓋 Meta-Train+Meta-Eval+Holdout 對應的全部時間範圍），SB4 的 Meta-Eval 只是折 27-32（6 折）這一段。TB 略低的一種可能是評估段本身時間範圍縮窄、樣本波動加大（Meta-Eval 段 TB 的 support 分布：class0 僅 686，占 4.1%），**不構成「SB4 訓練有問題」的證據，也不排除**，本文件不下結論。

---

## 5. `RISK-009`（OOF Stacking 過擬合）更新草案

**現況登記**（`REMAINING_RISKS.md`）：`OOF Stacking 過擬合 | Medium | HYPOTHESIS | ML Performance | UG-G3-SB4 | Purged OOF + 校準資料隔離 | Holdout 績效遠低於 OOF | 減少 Meta-Learner 複雜度`。

**擬更新為**（草案，供 Gate B 核准後寫入）：

> 緩解機制已實作並實測：三層結構（Holdout 折 33-42 全程不碰）＋二階 Purge（Meta-Train 中標籤結算日期晚於 Meta-Eval 起點的列排除，實測 up_down 150 列／TB 680 列）＋Meta-Eval 段獨立評估（非訓練所用資料）。**殘餘風險量化**（本 SB 新增）：§3(d) 的觀察顯示 Meta-Learner 的係數量級偏小、機率分布緊縮，**不是傳統意義的「過擬合」（訓練分數虛高、評估分數暴跌）**，而更像是「欠擬合／學不太到東西」——up_down 的 Meta(A) 甚至系統性劣於單一最佳 Specialist。這使原登記的「Holdout 績效遠低於 OOF」判準不完全對應本 SB 觀察到的現象，狀態維持 `HYPOTHESIS`（尚未有 Holdout 段的實測數字比對，Holdout 依 `DEC-040` 保留給 `UG-G3-SB7`），但新增一項後續觀察點：**`UG-G3-SB7` 對 Holdout 的最終評估應同時檢視 Meta-Learner 是否過擬合，也應檢視是否欠擬合（系統性劣於單一模型）**，兩者用同一套三層結構防護但診斷方向不同，不應預設只會發生前者。

---

## 6. `DEC-040` 轉 `APPROVED` 草案

`DEC-040`（Gate 3 Holdout 邊界落地）現狀態 `PROPOSED`，內容已完整（見 `DECISIONS.md`），Verification 清單三項中兩項已勾選（`WalkForwardSplitter` 實測、`ConstantsPinnedTests`／`HoldoutFoldsNeverIteratedTests`），第三項（真實庫首次每日 ETL 執行後重新核對折 33/42 邊界）明確標示 `NOT VERIFIED → 去處：UG-G3-SB7 開工前`。**本 SB 的全量執行（folds 0-32，兩個 target）進一步實測驗證了 `iter_oof_folds()` 對此邊界的過濾在真實資料上運作正確（零 Holdout 列，§2.2 守衛 3）**，可作為 Verification 清單追加一項已完成項。**PO 核准（2026-09-15）**：`DEC-040` 狀態轉 `APPROVED`，附核准日期與本 Gate B 結案 commit hash；Verification 清單追加：`[x] UG-G3-SB4 全量執行（folds 0-32）對兩個 target 的 OOF parquet 皆確認零 Holdout 列（reject_rows_at_or_after 二次確認），VERIFIED THIS SESSION`。

---

## 7. `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 Affected Components 訂正

現況登記：`src/ml/stacking.py (新建), src/ml/evaluator.py`。

**訂正為實際觸及的完整清單**：

```
src/ml/stacking.py（新建：OOF 矩陣組裝、二階 purge、Meta-Learner 選擇邏輯、
iter_oof_folds、HOLDOUT_START_DATE/META_EVAL_START_DATE 常數）
src/ml/specialist_training.py（fit_predict_specialist_fold() 新增 return_proba 參數）
src/ml/baseline_models.py（新增 META_REGIME_FEATURE_COLS 常數）
scripts/verify/ug_g3_sb4_oof_generation.py（新腳本：OOF 產生器，六項守衛）
scripts/verify/ug_g3_sb4_meta_learner_report.py（新腳本：段級報告器，四項守衛）
```

**訂正記錄**：Gate A §5 In Scope 第 5 項原載「`src/ml/evaluator.py`：擴充消費 `y_proba` 的評估路徑」——該項原文為視需要擴充的條件式規劃，**實際實作未觸及 `src/ml/evaluator.py`**：段級報告的評估邏輯（`select_best_specialist`、per-class 指標、Meta-Learner 訓練/評估）全部寫在 `scripts/verify/ug_g3_sb4_meta_learner_report.py` 這個獨立腳本內，未經過 `evaluator.py` 共用模組。實作階段發現 SB4 的評估邏輯（Meta-Train 選、Meta-Eval 報、四者並列）與 `evaluator.py` 既有的 tournament 式評估模型不同構，改為腳本自帶邏輯更直接，**不構成違反 Gate A 範圍**。**PO 裁決（2026-09-15）**：登記為後續小案（`PROJECT_STATUS.md` §0.5），待 `UG-G3-SB7` Benchmark 的評估需求明確後，一併決定是否統一評估路徑；不在本 SB 範圍內處理。

---

## 8. `RISK-015` 備註

現況已於 Gate A 階段（`VERIFIED THIS SESSION`，2026-09-14/15）登記：「Arm B 的 OOF 是否對 Meta-Learner 堆疊有貢獻」正式列為 RISK-015 後續驗證項，需等資料源擴充後才能評估。**本 Gate B 無新增內容**——Arm B 全程排除（Gate A §3.1 已裁決），本輪全量執行未產生任何 Arm B 相關數字，登記維持原狀。

---

## 9. `PROJECT_STATUS.md` 進度列（草案）

§0.2 `UG-G3-SB4` 列擬更新為：

> **Gate B 送審中**（實作與全量執行完成，2026-09-15）——延續 §0.2 現有敘述（Gate A 三版歷程、紅測歷程），追加：GREEN 實作三輪（初版 14 項→P1-P5 缺口 5 項→P6/P7 定義域核對 2 項→OOF/報告腳本正確性問題 3 項＋P8 契約擴張），累計紅測 `e46a8a7`(35)→`69f6e35`(+4=39)→自我反查(+2=41)→`a1abcf4`(+5)→`da73153`(+2)→`e9ac8da`(+3 failures/4 errors on old impl)。全量執行（folds 0-32，兩個 target）：六項 OOF 守衛與四項報告守衛皆全數 PASS，四份證據 JSON 已 commit（`3ba80b6`）。四者並列數字見 Gate B 文件 §2.4；`DEC-040` 待 Gate B 核准轉 `APPROVED`。

---

## 10. Definition of Done 逐項對號（Gate A §10）

| # | 項目 | 狀態 | 對應 |
|---|------|------|------|
| 1 | OOF 矩陣依 §4.1／§4.6 契約產生，2 target × rolling × 4 組（Arm A only），範圍限於折 0～32，逐 target 分檔 | ✅ 已完成 | `3ba80b6`，兩份 OOF parquet |
| 2 | `return_proba` 參數已落地，既有呼叫端零改動 | ✅ 已完成 | `dcf48c5`；既有 SB3 測試套件（`tests/test_ug_g3_sb3_*`）未受影響（全套測試持續 OK） |
| 3 | `META_REGIME_FEATURE_COLS` 常數已定義並被斷言 | ✅ 已完成 | `dcf48c5`；`test_meta_uses_only_oof_preds` |
| 4 | 三層結構已落地，折邊界、二階 purge 排除數（150／**680**）寫入證據 JSON 與新 ADR | ✅ 已完成（TB 數字已訂正為 680，見 §3(e)） | `c328805`／`3ba80b6`；`DEC-040` |
| 5 | Meta-Eval 段報告 `Meta(A)` 與 `Best Single Specialist` 並列，含完整排名 | ✅ 已完成 | §2.4；`ranking_df` 四列皆含 `n_rows` |
| 6 | `LogisticRegression` 與 `RidgeClassifier` 兩者皆完整報告，未淘汰其中之一 | ✅ 已完成 | §2.4 兩表皆列兩者 |
| 7 | `split_segment` 含 `purged` 值，且列數與實測值核對一致 | ✅ 已完成 | §2.2 守衛 4 |
| 8 | Holdout 與 Arm B 零產出的結構性斷言存在且通過 | ✅ 已完成 | `HoldoutFoldsNeverIteratedTests`；OOF 矩陣結構上只含 4 組 Arm A 欄 |
| 9 | 全套測試 PASS；`gate0_contract_check.py` exit 0；§6 全部 known-FAIL 案例已實際執行並附原始輸出 | ✅ 已完成 | 915 tests OK；14/14 PASS；見 §11 |
| 10 | `REMAINING_RISKS.md` RISK-015 已登記 Arm B 後續驗證項 | ✅ 已完成（Gate A 階段完成） | §8 |

**額外完成（超出原 DoD，審查複核期間追加要求）**：OOF 產生腳本 test_window_exclusions 揭露、報告腳本 signal_row_counts／majority_baseline／逐類別 recall／LR n_iter_ 與 ConvergenceWarning 追蹤／scaler_type 明寫、`build_meta_learner_input` 的 `return_retained_index` 契約擴張（P8）。

---

## 11. 驗證環境與結果

**執行環境**：容器（`stock_prediction_system2_devcontainer-app-1`），Python 3.14.6，HEAD `3ba80b6`。

**依賴狀態**：全部 `PRESENT`（15 項），ML 相關測試皆走真實 sklearn／lightgbm／xgboost 實作。

**全套測試**（`VERIFIED THIS SESSION`）：
```
Ran 915 tests in 47.063s
OK
```

**跨文件契約驗證**（`VERIFIED THIS SESSION`）：`Part B: 14/14 PASS`，`exit 0`。

**格式／秘密掃描**：本 Gate B 涉及的 11 個 commit（編號 0～11），每一個在建立當下皆經 `.githooks/pre-commit`（GOV-04）四項機械檢查攔截，皆為 PASS 才允許 commit 建立。一次 `SKIP_CHECK2_REASON` 具名跳過：`c328805`（情況(2)：`model.fit()` 因新增 `warnings.catch_warnings()` 區塊巢狀進去一層造成的縮排位移，逐行核對無其他純空白落差）**已在該 commit message 本文中指名分類**。

**known-FAIL 案例**（代表性）：

| 領域 | 代表性 known-FAIL 案例 |
|---|---|
| Holdout 折排除 | `HoldoutFoldsNeverIteratedTests::test_straddling_fold_is_excluded_entirely`（半折跨界必整折排除，非切半折） |
| 二階 Purge 混入 meta_eval | `SecondStagePurgeTests`（69f6e35 新增，混合夾具，純 meta_train 夾具測不出的盲點已補） |
| 機率欄索引對齊 | `test_assemble_oof_matrix_probability_values_align_with_declared_classes`（不對稱值 0.3/0.7，對稱值測不出索引錯位） |
| `target_column` 未核對真定義域 | P7 紅測（`da73153`）：TB 資料誤配 `target_up_down` 預設值必被拒絕 |
| OOF 產生守衛 4/5（保留列數常數） | `ExpectedConstantsCorrectnessTests`（e9ac8da 新增，錯誤常數必 FAIL） |
| `iter_oof_folds()` 被繞過 | `IterOofFoldsActuallyUsedTests`（source-scan，手寫等義邏輯必 FAIL） |
| `argmax` 遇 NaN | `BuildLongFormatNaNExclusionTests`（合成 NaN 夾具，排除數必為 1） |
| `return_retained_index` 契約 | `BuildMetaLearnerInputRetainedIndexTests`（3 項，含 PM 自行發現並訂正的夾具位置/標籤混淆錯誤） |

---

## 12. 未驗證清單（有名字有去處）

| 項目 | 去處 |
|------|------|
| §3(d) 三項候選成因的實際驗證（class_weight、門檻曲線、VIF/降維） | **PO 裁決（2026-09-15）：不在 SB4 處理**——門檻曲線與機率分布、`class_weight`／共線性歸 `UG-G3-SB5` Gate A 必答項；信心門檻歸 `UG-G3-SB6` |
| `evaluator.py` 未依 Gate A §5 擴充，評估路徑改走獨立腳本 | 登記為後續案，是否統一評估路徑留待 PO 裁決（§7 訂正記錄） |
| `expanding` 模式的 OOF | 本 SB 明確不跑（Gate A Out of Scope），未來若需要另案 |
| Holdout（折 33-42）對 Meta-Learner 的最終評估 | `UG-G3-SB7`，`DEC-040` 唯一消費者條款 |
| RISK-009 是否為「欠擬合」而非「過擬合」的判定 | `UG-G3-SB7` Holdout 評估時一併檢視（§5） |
| `LogisticRegression`／`RidgeClassifier` 二選一 | Gate A 已裁決本 SB 不做，留待有新資料（SB7 Holdout 但依 DEC-040 不得用於選擇）或 Gate 3 之外 |
| RISK-015 資料源擴充後 Arm B 重新評估 | 另案，依賴資料源擴充進度 |

---

## 13. 核准後動作（PO 已核准，本結案 commit 執行）

依 `CLAUDE.md` §16.3、`gate-submit` skill 產出 8：

1. `git mv` 本文件與 `UG_G3_SB4_GATE_A_PROPOSAL.md` 至 `doc/upgrade/gates/closed/`。
2. 確認 `git diff --cached --name-status` 顯示為 `R100`（純 rename）。
3. 檢查搬移後的檔案是否出現在 `gate0_contract_check.py` 的 `DOC_PATHS`，若有則同一 commit 內更新。
4. 同步 `doc/README.md` 逐份文件表。
5. `PROJECT_STATUS.md` §0.2 `UG-G3-SB4` 列狀態改為 `CLOSED`，附核准日期與結案 commit hash。
6. `DECISIONS.md`：`DEC-040` 轉 `APPROVED`，附核准日期，補進 `TRACEABILITY.md` 對應分節；Verification 清單追加項（§6）。
7. `REMAINING_RISKS.md`：RISK-009 更新為 §5 草案文字（待 PO 核可措辭）。
8. `SYSTEM_UPGRADE_MASTER_PLAN.md` §9：Affected Components 訂正為 §7 清單。

**Gate B 已核准，本文件與 Gate A 提案隨結案 commit 一併 `git mv` 至 `closed/`。**
