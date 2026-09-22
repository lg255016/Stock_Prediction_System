# UG-G3-SB5 Gate B 送審：Probability Calibration

> **狀態**：**Gate B 已核准（2026-09-15，PO 核准，草稿無需訂正）**。
> **對應 Gate A 提案**：`doc/upgrade/gates/UG_G3_SB5_GATE_A_PROPOSAL.md`（PO 核准 `5624e74`）。
> **本 SB 全程無真實庫寫入**，不適用 RISK-013 三項協議；全程對 `UG-G3-SB4` 已核准 OOF parquet 唯讀運算。
> **主要發現**：`RISK-030`——`target_up_down` 在折 27-32 無可偵測的 OOF 排序訊號（四個 Specialist 與 Meta(A) 皆然），`target_triple_barrier` 的訊號幾乎全部集中於 Timeout 類。§5 四項裁決已由 PO 核定，見下；新 ADR `DEC-041`（狀態 `PROPOSED`）記錄「Gate 3 後續主線改以 TB／Timeout 為對象」。

---

## 1. 完整 Commit 序列

| # | Commit | 內容 |
|---|--------|------|
| 0 | `5624e74` | Gate A 提案核准（含五處訂正：手動 Isotonic/Platt、AUC 判準修正、`test_calibration_not_in_train` 結構性拒絕定案、§4.7 資料預算、reliability/Brier 定義；§6 AUC 列改唯一行為） |
| 1 | `22f685e` | 紅測（RED）——`src/ml/calibration.py` 30 項，全合成資料 |
| 2 | `deb95cc` | 實作（GREEN）——`src/ml/calibration.py` 新建，30 項轉綠；GREEN 階段自行發現並訂正兩處紅測錯誤（多類別 Brier 代數關係、`test_tb_sigmoid_allowed` 參數錯誤） |
| 3 | `89f9f33` | Platt 改未正則化擬合（`PLATT_C=1e6`）——紅→綠，2 項新測試 |
| 4 | `7c65b4f` | 段級報告腳本 GREEN＋`assert_auc_preserved()` 鏡射容忍檢查＋`calibration_not_meaningful` 判準複核訂正——commit A（程式碼/測試/文件） |
| 5 | `b286ec5` | 段級報告全量證據（乾淨樹重跑）——commit B |

**四份證據 JSON**：`UG_G3_SB4_oof_generation_target_up_down.json`／`_target_triple_barrier.json`（`UG-G3-SB4` 既有）＋ `UG_G3_SB5_calibration_report_target_up_down.json`／`_target_triple_barrier.json`（本 SB，`script_commit=7c65b4f`，`script_dirty=false`）。

---

## 2. `RISK-030`：三段 AUC 表與 SB4 macro F1 的誤讀澄清

### 2.1 `target_up_down`——四個 Specialist 與 Meta(A) 全線無訊號

| Specialist | Meta-Train AUC（27 折全量） | Calib-fit AUC（折 27-29） | Calib-eval AUC（折 30-32） |
|---|---|---|---|
| `lr` | 0.5151 | 0.4988 | 0.4923 |
| `rf` | 0.5255 | 0.4951 | 0.5102 |
| `lgbm` | 0.5236 | 0.5001 | 0.4997 |
| `xgb` | 0.5238 | 0.4977 | 0.5029 |

證據：`UG_G3_SB5_calibration_report_target_up_down.json` → `specialist_raw_auc.<model>.["1"]`（二分類兩類數值恆等，見 `specialist_raw_auc_note`）。`lgbm` 27 折逐折中位數 0.5188，僅 4 折 >0.55（PO 2026-09-15 獨立重算，`VERIFIED THIS SESSION`）。

**Meta(A)**：`Calib-fit` 原始分數（`decision_function`）AUC——`LogisticRegression` 0.4959、`RidgeClassifier` 0.4959（`calibration_results.*.auc_calib_fit_raw`）。Platt 擬合斜率 LR `-0.1539`、Ridge `-0.3102`（`per_class_quality.1.platt_slope`），`calibration_not_meaningful=true`（四個條目：LR/Ridge × isotonic/sigmoid，全數）。

**SB4 `lgbm` macro F1 0.465 > 多數類基線 0.342 的誤讀澄清**：多數類基線對其中一類（class 1）的 recall／F1 恆為 0，`lgbm` 只要兩類都給出非零預測，macro F1 平均後幾乎必然高於多數類基線——**這是 macro F1 對「至少猜兩類」的獎勵，不是排序能力的證據**。AUC 才是量測排序能力的指標，`lgbm` 的 AUC（0.50～0.52）顯示它幾乎沒有比隨機猜測更好的排序能力，與它 macro F1 領先多數類基線的事實**不矛盾**——兩者衡量的是不同性質。

### 2.2 `target_triple_barrier`——訊號集中於 Timeout 類

| Specialist | Meta-Train AUC | Calib-fit AUC | Calib-eval AUC |
|---|---|---|---|
| | `-1` / `0` / `1` | `-1` / `0` / `1` | `-1` / `0` / `1` |
| `lr` | 0.5478 / **0.9118** / 0.5250 | 0.5092 / 0.8384 / 0.4968 | 0.5412 / **0.9104** / 0.5279 |
| `rf` | 0.5486 / **0.9044** / 0.5251 | 0.5345 / 0.8170 / 0.5042 | 0.5344 / **0.9076** / 0.5088 |
| `lgbm` | 0.5463 / **0.8994** / 0.5211 | 0.5239 / 0.8284 / 0.5009 | 0.5280 / **0.9027** / 0.5064 |
| `xgb` | 0.5446 / **0.8951** / 0.5206 | 0.5242 / 0.8290 / 0.4996 | 0.5285 / **0.9009** / 0.5061 |

證據：`UG_G3_SB5_calibration_report_target_triple_barrier.json` → `specialist_raw_auc.<model>.["-1"/"0"/"1"]`。

**Meta(A)**：六個 OvR Platt 斜率全正（LR：`-1`=+0.0638／`0`=+1.2164／`1`=+0.0001；Ridge：`-1`=+1.6284／`0`=+4.8652／`1`=+0.7411，`calibration_results.*.per_class_quality.<cls>.platt_slope`），`calibration_not_meaningful=false`（兩個條目）。`auc_calib_fit_raw`：LR `-1`=0.5431／`0`=0.8295／`1`=0.5027，Ridge `-1`=0.5412／`0`=0.8382／`1`=0.5148。

---

## 3. 校準結果並列（僅揭露，不下結論——依 Gate A §4.6 訂正版準則）

### 3.1 `target_up_down`：四條目皆無意義

| Model×Method | Brier 前 | Brier 後 | log-loss 前 | log-loss 後 | fixed 0.5 門檻 macro F1 前 | 後 |
|---|---|---|---|---|---|---|
| LR-isotonic | 0.4990 | 0.4997 | 0.6922 | 0.7041 | 0.4115 | 0.3456 |
| LR-sigmoid | 0.4990 | 0.4990 | 0.6922 | 0.6922 | 0.4115 | 0.3461 |
| Ridge-isotonic | 0.4986 | 0.4997 | 0.6917 | 0.7041 | 0.4108 | 0.3456 |
| Ridge-sigmoid | 0.4986 | 0.4990 | 0.6917 | 0.6922 | 0.4108 | 0.3461 |

LR 原生 `predict_proba` Brier（`Calib-eval`，僅揭露對照）：0.4990（與校準前後幾乎相同——原生機率本身就已經接近 0.5 的常數輸出，校準無從改善）。

### 3.2 `target_triple_barrier`：Brier／log-loss 改善，固定 argmax 下部分模型退化

| Model | Brier 前 | Brier 後 | log-loss 前 | log-loss 後 | fixed argmax macro F1 前 | 後 |
|---|---|---|---|---|---|---|
| LR-sigmoid | 0.5287 | **0.5196** | 0.7993 | 0.7801 | 0.3369 | **0.2437** |
| Ridge-sigmoid | 0.5769 | **0.5207** | 0.9528 | 0.7897 | 0.3152 | 0.3122 |

LR 原生 `predict_proba` Brier：0.5192（介於校準前後之間）。**LR 的 fixed-argmax macro F1 從 0.337 掉到 0.244**——逐類別對照（`fixed_threshold_per_class_after`）：class `1` recall 校準後降到 **0**（校準前 0.0049，本就極低），class `-1` recall 從 0.980 升到 0.9998（幾乎全猜多數類），class `0`（Timeout）recall 從 0.219 降到 0.0077。**這不是校準「讓模型變差」——是校準後的機率更貼近真實分布（class 1 本來就幾乎不可預測，class 0 稀有），argmax 因此更用力地把邊界模糊的列都判給多數類**，與 Brier／log-loss 同時改善的事實**不矛盾**（Brier／log-loss 衡量機率品質，macro F1 衡量固定門檻下的硬分類結果，兩者一致改善的方向不保證相同）。Ridge 的 macro F1 幾乎不變（0.315→0.312），因為 Ridge 校準前後對 class `1` 的 recall 本來就已經接近 0。

---

## 4. TB Timeout 訊號的解讀（`INFERENCE`，非既有規格或研究依據）

Timeout 類別的定義是「5 天內價格未觸及上下邊界」，本質上接近「**未來一段時間波動偏低**」這件事的另一種表述。`ARM_A_FEATURE_COLS` 含波動相關欄位（如 `volatility_20d`），**模型學到「用近期波動預測近期波動是否會持續偏低」，是比「用技術指標預測方向」容易得多的任務**——這與 Timeout 類 AUC（~0.83-0.91）遠高於方向類（`-1`／`1`，~0.50-0.55）的觀察一致。`±1` 兩類 AUC ≈ 0.52 支持這個讀法：**「可預測 Timeout」不等於「可預測方向」**，Specialist／Meta-Learner 在本特徵集下，實質上只學到了「波動是否偏低」這一件事，價格漲跌方向本身仍然接近隨機。此推論**尚未有額外驗證**（例如未檢驗 `volatility_20d`／`ma20_bias_ratio` 對 Timeout 類的邊際貢獻是否確實主導了 AUC），列為 `INFERENCE`，供 §5 裁決參考。

---

## 5. 裁決項（PO 2026-09-15 核定）

| # | 問題 | **PO 裁決** |
|---|---|---|
| (a) | `UG-G3-SB6` 對 `target_up_down` 是停做，還是只跑並揭露？ | **停做。** `UG-G3-SB6` Gate A 提案須明寫引用 `RISK-030` 排除 `target_up_down`——不跑、不揭露。將來若方向訊號有進展（例如 §5(c) 的特徵層面案有結果），再重新開放。 |
| (b) | `UG-G3-SB6` 的門檻與 regime gating 是否改以 TB／Timeout 機率為對象？ | **改以 `target_triple_barrier`／Timeout 類的校準後機率為 gating 對象**，產品形態定位為「何時不交易」（而非「往哪個方向交易」）；`±1` 方向類機率只揭露、不設門檻。`UG-G3-SB6` Gate A 必答：gating 評估指標定義（被排除時段的實際 Timeout 率、保留時段的方向勝率變化）、門檻在 `Calib-eval`（折 30-32）段選定、`Holdout`（折 33-42）全程不碰。 |
| (c) | 是否開特徵層面的案處理方向預測？ | **登記為候補案，`UG-G3-SB7` 結案後再排**；與 `RISK-015`（情緒特徵覆蓋率不足）連動，候選方向包含情緒覆蓋率擴充、新特徵來源、或重新檢視標籤定義。登記於 `PROJECT_STATUS.md` §0.5 與 `RISK-030` 去處欄。 |
| (d) | `SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1「條件勝率 >60%」對 `target_up_down` 是否仍適用？ | **目標數字保留不改**，但追加狀態註記：「`target_up_down` 於現行特徵集下未達成本目標的判別力前提（見 `RISK-030`）」。另訂 Timeout gating 的量化目標，具體數字由 `UG-G3-SB6` Gate A 提案訂定。 |

**新 ADR `DEC-041`**（狀態 `PROPOSED`，隨本結案 commit 一併登記）記錄上述四項裁決與其依據（`RISK-030` 三段 AUC 表），`UG-G3-SB6` Gate B 通過時轉 `APPROVED`。

> **2026-09-15 訂正**：本節 (d) 與 §9 第 6 點原誤引 `SYSTEM_UPGRADE_MASTER_PLAN.md` §10（實為 Gate 4 章節），正確章節為 §11.1「準確度目標」。錯誤源頭是 PO 核准訊息本身的筆誤，PM 撰寫本文件時原樣照抄未查證；審查方複核 `3f77fb9` 時發現同一 commit 內 PROJECT_STATUS.md／commit message 已正確寫 §11.1，與本文件、`DECISIONS.md`、`TRACEABILITY.md`、`REMAINING_RISKS.md` 的 §10 寫法互相矛盾，訂正 commit 已同步修正全部位置。

---

## 6. Definition of Done 逐項對號（Gate A §10）

| # | 項目 | 狀態 | 對應 |
|---|------|------|------|
| 1 | `src/ml/calibration.py` 新建，手動 Isotonic／Platt 落地並被測試覆蓋，不依賴 `CalibratedClassifierCV` | ✅ 已完成 | `deb95cc`；34 項紅測全綠 |
| 2 | 校準資料集依 §4.1 切分，證據 JSON 記錄折集合、列數、類別分布，與 §2.4 核對一致 | ✅ 已完成 | `calib_fit_row_count`／`calib_eval_row_count`／`calib_fit_class_distribution`／`calib_eval_class_distribution`，兩個 target 皆與 Gate A §2.4／§4.1 核對一致 |
| 3 | 兩個 target 的 LR／Ridge 皆完成校準（up_down 產出 isotonic+sigmoid，TB 只產出 sigmoid），不淘汰任一 Meta-Learner；LR 原生 `predict_proba` Brier 對照一併揭露 | ✅ 已完成 | §3 兩表；`lr_native_proba_brier_calib_eval` |
| 4 | 單調性驗證通過（正規化前）；TB 正規化後多類別機率和為 1 驗證通過；校準前後 AUC／PR-AUC **保留或鏡射**驗證通過（訂正） | ✅ 已完成 | `n_unique_calibrated_values`（up_down sigmoid 8981＝全部唯一，isotonic 19/20＝階梯 ties）；TB 六類 AUC 前後逐位相等（保留），up_down sigmoid 兩條目符合鏡射（`auc_after=1-auc_before`） |
| 5 | 校準前後 Brier score／log-loss／AUC 並列報告；macro F1 變化量如實揭露（不要求特定方向）；若 AUC 不相等（且非鏡射）須附原因說明 | ✅ 已完成 | §3 兩表；無 AUC 既非保留也非鏡射的情況發生 |
| 6 | `test_calibration_not_in_train` 落地為結構性拒絕，`fit()`／`evaluate()` 分別只接受 `CALIB_FIT_FOLDS`／`CALIB_EVAL_FOLDS` | ✅ 已完成 | `CalibrationFoldIsolationError`，`CalibrationNotInTrainTests` |
| 7 | 全套測試 PASS；`gate0_contract_check.py` exit 0；§6 全部 known-FAIL 案例已實際執行並附原始輸出 | ✅ 已完成 | 967 tests OK；14/14 PASS；5 項 PO 指定突變體逐一構造確認 |
| 8 | §9 五項 PO 裁決已全部落地（含 #1 的 `PROJECT_STATUS.md` §0.5 登記、#5 的 SB6 資料段確認） | ✅ 已完成 | `PROJECT_STATUS.md` §0.5 #22 延續列；§4.7 資料預算 |
| 9（新增，守衛 5） | 重建的 LR／Ridge Meta-Eval macro F1 與 `UG-G3-SB4` 已核准報告逐位相同（容差 1e-9），證明校準的是同一個模型 | ✅ 已完成 | `sb4_model_match`（兩個 target 皆逐位相同） |

---

## 7. 文件同步

- **`SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB5 Brief，Affected Components 訂正**：現況登記 `src/ml/calibration.py (新建), src/ml/predictor.py`——**`src/ml/predictor.py` 未被觸及**，實際新增／修改為 `src/ml/calibration.py`（新建）、`scripts/verify/ug_g3_sb5_calibration_report.py`（新建）。訂正記錄比照 `UG-G3-SB4` Gate B §7 先例（Gate A 規劃與實際落地的落差，誠實記錄，不視為違規）。
- **`REMAINING_RISKS.md` `RISK-009`**：是否更新——**建議不合併，交叉引用即可**。`RISK-009` 談的是 OOF Stacking 架構本身的過擬合／欠擬合風險，`RISK-030` 談的是特定 target（up_down）在目前特徵集下的訊號天花板，兩者性質不同（一個是「堆疊設計是否會過擬合」，一個是「輸入本身有沒有訊號可堆疊」）。**建議在 `RISK-009` 的殘餘風險量化文字追加一句交叉引用 `RISK-030`**，說明「欠擬合」觀察與 `RISK-030` 的訊號天花板是同一組實測數字的兩種描述角度，避免讀者誤以為是兩個獨立問題。
- **`RISK-030`**：已於上一輪登記（`REMAINING_RISKS.md`），本輪無需修改，§5 的四項裁決結果待 PO 決定後回填「應對措施」欄。
- **`PROJECT_STATUS.md`**：§0.2 新增 `UG-G3-SB5` 列（狀態：Gate B 送審中）；§0.5 #22 延續列已於上一輪登記，本輪待 §5 裁決後視需要再追加一則延續列記錄結果。

---

## 8. 未驗證清單（有名字有去處）

| 項目 | 去處 |
|------|------|
| §4「TB Timeout 訊號來自波動特徵」的 `INFERENCE` 未經額外驗證（例如特徵重要度、消融實驗） | 若 §5(c) 裁決開特徵層面案，屆時一併驗證；本 SB 不驗證 |
| §5 四項裁決本身 | 交 PO，本文件不代為決定 |
| `expanding` 模式的校準 | `UG-G3-SB4` 未跑，本 SB 同樣不涉及，維持 Gate A Out of Scope |
| Holdout（折 33-42）對校準品質的最終驗證 | `UG-G3-SB7`，`DEC-040` 唯一消費者條款延續 |
| §2.3(a)(c)（`class_weight`、Specialist 共線性）的候補案 `SB4a` | `PROJECT_STATUS.md` §0.5 #22，觸發條件已因 `RISK-030` 追加一層但未撤銷，待 `UG-G3-SB6` 門檻選定後視情況決定 |

---

## 9. 核准後動作（PO 已核准，本結案 commit 執行）

依 `CLAUDE.md` §16.3、`gate-submit` skill 產出 8：

1. `git mv` 本文件與 `UG_G3_SB5_GATE_A_PROPOSAL.md` 至 `doc/upgrade/gates/closed/`。
2. 確認 `git diff --cached --name-status` 顯示為 `R100`（純 rename）。
3. 檢查搬移後的檔案是否出現在 `gate0_contract_check.py` 的 `DOC_PATHS`，若有則同一 commit 內更新。
4. 同步 `doc/README.md` 逐份文件表（依既有慣例，資料夾層級登錄即可，不需逐檔）。
5. `PROJECT_STATUS.md` §0.2 `UG-G3-SB5` 列狀態改為 `CLOSED`，附核准日期與結案 commit hash。
6. `SYSTEM_UPGRADE_MASTER_PLAN.md` §9：Affected Components 訂正為 §7 清單；§11.1 目標加狀態註記；SB6 Brief 加一行範圍調整說明。
7. `REMAINING_RISKS.md`：`RISK-030` 應對措施欄補上 §5 四項裁決結果、去處寫 `DEC-041`；`RISK-009` 追加交叉引用一句。
8. `DECISIONS.md` 新增 `DEC-041`（狀態 `PROPOSED`）；`TRACEABILITY.md` 對應分節同步。
9. `PROJECT_STATUS.md` §0.5 新增裁決 (c) 的候補案登記。

**Gate B 已核准，本文件與 Gate A 提案隨結案 commit 一併 `git mv` 至 `closed/`。**
