# UG-G3-SB4 Gate A 提案：OOF Stacking Meta-Learner

> **狀態**：**Gate A 已核准（2026-09-14，PO，v3 定案）**。
> **前置**：`UG-G3-SB3` 已於 2026-09-13 Gate B 核准結案；RISK-023 獨立小案已於 2026-09-14 完成結案（`954b066`）。
> **版本歷程**：
> - v1（2026-09-14）：退回——§4.4 誤把已核准的 Gate 3 Holdout 規格當成自由裁量選項，漏答「OOF 覆蓋哪些 target × mode」。
> - v2（2026-09-14）：三層結構、二階 purge、Data Contract 皆訂正通過，**但審查方獨立查證發現一個讓 §3.1「Arm B 納入」裁決失效的事實**——折 0～32（Meta-Train／Meta-Eval）範圍內，`sentiment_mean` 非 NULL 列數為 **0**，SB3 全部情緒訊號都落在 Holdout 期間。改判 Arm B 不納入本 SB，另有三處小訂正 → v3。
> - v3（2026-09-14）：**核准**。審查方獨立核對全部列數／情緒訊號數／purge 數與 PM 實測相符，§0／§3.1 表述準確，無殘留 `Meta(A+B)` 字句。PO 核准時追加三點落地要求（選法指標固定為常數＋列完整排名、`split_segment` 新增 `purged` 值、LR／RidgeClassifier 不在 Meta-Eval 段互相淘汰），已併入本文件（§3.4、§4.6、§5、§10）。
> **本提案階段唯讀**：僅查證現況、規劃設計，未修改任何業務程式碼、未動任何資料庫。**下一步**：依 PO 指示先送紅測清單予審查方複核，審查方核准後才進紅測 commit，之後才實作（見 §13）。

---

## 0. 摘要

`UG-G3-SB4` 用 `UG-G3-SB3` 已訓練完成的 **Arm A（無情緒）四個 Specialist**（LogisticRegression／RandomForest／LightGBM／XGBoost）在 Purged Walk-Forward 折 0～32 的**樣本外（OOF）預測**，訓練一個二階 Meta-Learner（LogisticRegression 與 RidgeClassifier 並列），嚴格禁止 Meta-Learner 直接看到任何原始特徵。

**v3 與 v2 的差異**：v2 主張 Arm B（含情緒特徵）的 OOF 也應納入，由 Meta-Learner 自己判斷要不要用。**這個主張在本次查證中被推翻**：折 0～32 範圍內 `sentiment_mean` 非 NULL 列數為 0（`VERIFIED THIS SESSION`，PO／審查方雙方獨立核實），意味著 Arm B 在本 SB 可用的範圍內收到的八個情緒欄**全是 NaN**——Arm B 的 OOF 預測與 Arm A 的差異只可能來自樹模型的隨機性或欄數不同造成的細微差異，不可能來自情緒訊號本身。若仍照 v2 設計並列 `Meta(A+B)` 與 `Meta(A only)`，這個對照**結構上不可能顯示出有意義的差異**——那是一個不可能失敗的檢定（`CLAUDE.md` §9A.1），不產出證據。**本版改為只用 Arm A**，B 臂的可用性問題移交 RISK-015 後續案。

---

## 1. Requirement Source

| 來源 | 內容 |
|---|---|
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB4 Brief | Goal／Dependency／In Scope／Out of Scope／Affected Components／Tests／Rollback／DoD |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §10、§11.3 | Holdout 規格：最近 6–12 個月保留、不得使用相同 Folds 同時做模型選擇、門檻選擇與最終績效宣稱 |
| `PURGED_WALK_FORWARD_SPEC.md` §3.3 | Holdout／最少 Fold 數／最少訓練樣本需求 |
| `GATE3_STARTUP_APPLICATION.md` §5 | `UG-G3-SB4` 排在 `UG-G3-SB3` 之後，設計細節留給本提案 |
| `REMAINING_RISKS.md` RISK-009 | OOF Stacking 過擬合，緩解方式「Purged OOF + 校準資料隔離」——§4.4／§4.5 落地 |
| `REMAINING_RISKS.md` RISK-015 | 情緒覆蓋率不足，本版新增：Arm B OOF 對堆疊的貢獻，列為 RISK-015 後續驗證項（§7、§9） |
| `UG_G3_SB3_GATE_B_SUBMISSION.md` §2.4／§9 | D3 對照實驗最終裁決；面板凍結證據 |
| `DECISIONS.md` DEC-039 | 留言三欄真值與 PIT 機制（§3.3） |
| PO 三輪指示（2026-09-14） | 第一輪：承接 SB3／RISK-015／留言三欄。第二輪：七項訂正（三層結構、二階 purge、Data Contract）。第三輪：Arm B 改判 + 三處小訂正 |

---

## 2. Current State（唯讀查證，`VERIFIED THIS SESSION`）

### 2.1～2.4（同 v2，未變）

`fit_predict_specialist_fold()` 只回傳硬標籤，無機率輸出；SB3 未持久化逐列 OOF；凍結面板未受 RISK-023 寫入影響；`build_panel_dataset()` 輸出可用 `(stock_id, trade_date)` 對齊。

### 2.5 `WalkForwardSplitter` 折邊界與三段列數（本輪擴充查證，`VERIFIED THIS SESSION`，PM／審查方獨立互核，數字相符）

對 `panel_target_up_down.parquet`（139,585 列）與 `panel_target_triple_barrier.parquet` 以 SB3 同款設定（`train_window_size=60, test_window_size=20, mode=rolling, label_horizon=1, embargo_days=0, require_label_end_date=True`）呼叫 `WalkForwardSplitter.split()`：**43 折，全數 `purge_mode=exact`**，兩個 target 折邊界結構相同。

| 段 | 折範圍 | 測試窗跨度 | 列數 | `sentiment_mean` 非 NULL |
|---|---|---|---|---|
| Meta-Train | 折 0～26（27 折） | 2023-02-06～2025-04-30 | **80,982** | **0** |
| Meta-Eval | 折 27～32（6 折） | 2025-05-02～2025-10-22 | **17,960** | **0** |
| Holdout | 折 33～42（10 折） | 2025-10-23～2026-08-20 | **30,000** | 630 |
| 不在任何折測試窗內 | 折 0 訓練窗前段（2022-11-01～2023-02-03，8,993 列）＋折 42 之後（2026-08-21～2026-09-04，1,650 列） | — | **10,643** | 53 |

**關鍵事實**：折 0～32（Meta-Train + Meta-Eval，合計 98,942 列，本 SB 實際可用範圍）內 `sentiment_mean` 非 NULL 列數為 **0**。SB3 全部情緒訊號集中在 2026-01-19 之後（`sentiment_subset` 20 檔股票的訊號列），全數落在 Holdout（2025-10-23 以後）或折 42 之後的缺口內。**這不是本 SB 的新問題，是折 0～32 這段時間本身的資料現況**——本 SB 唯讀查證出來，不是本 SB 造成的。

### 2.6 二階 Purge 邊界實測（本輪新增查證，`VERIFIED THIS SESSION`）

Meta-Eval 段最早 `trade_date` = 2025-05-02。以此為界，Meta-Train（折 0～26）中 `label_end_date`（`target_up_down`）或 `label_end_date_tb`（`target_triple_barrier`）晚於或等於此日期的列：

- `target_up_down`：**150 列**須排除，Meta-Train 內最晚 `label_end_date` = 2025-05-02。
- `target_triple_barrier`：**750 列**須排除（其中 `target_triple_barrier` 非 NULL 者 680 列），Meta-Train 內最晚 `label_end_date_tb` = 2025-05-08（T+5 效應，如 §4.5 原先預期，晚於 `up_down` 的 T+1）。

### 2.7 候選市場機制特徵與 `src/ml/stacking.py` 現況（同 v2）

`volatility_20d`／`ma20_bias_ratio` 已存在於 `ARM_A_FEATURE_COLS`；`src/ml/stacking.py` 尚不存在。

---

## 3. PO 指定必答項

### 3.1 承接 SB3 結論——**改判：本 SB 只用 Arm A**（v3 核心變更）

v2 曾主張 Arm B 的 OOF 納入候選輸入，由 Meta-Learner 自己判斷。**這個判斷建立在一個未經查證的假設上——「Arm B 的原始特徵訊號稀薄」不等於「折 0～32 範圍內 Arm B 完全沒有非 NaN 的情緒輸入」，而 §2.5 的實測顯示後者才是實情：折 0～32 內 `sentiment_mean` 非 NULL 列數為 0**。

**後果**：Arm B 在折 0～32 收到的八個情緒欄全是 NaN，RF／LightGBM／XGBoost 三個支援 NaN 的模型在 Arm B 下實質上是在**用比 Arm A 多 8 個全 NaN 欄的相同資料**訓練——樹模型對全 NaN 欄的處理方式（多數實作視為「缺失，走預設分支」）不會產生任何有意義的資訊，Arm B 的 OOF 與 Arm A 的差異只會是訓練過程的隨機性（隨機森林的 bootstrap、樹的分裂順序等），不是情緒訊號。**若仍並列 `Meta(A+B)` 與 `Meta(A only)`，這個對照結構上不可能顯示出「B 臂有沒有貢獻」——因為 B 臂在本 SB 可用範圍內沒有東西可以貢獻。**

**裁決**：

- OOF 矩陣**只產 4 組**：`{lr, rf, lgbm, xgb} × A`。B 臂三組（RF／LightGBM／XGBoost × B）不在折 0～32 上訓練或收集 OOF。
- 並列報告改為**兩者**：`Meta(A)`（本 SB 的主要交付）與 `Best Single Specialist`（堆疊本身有沒有價值的對照組，選法見 §3.4）。
- **「Arm B 的 OOF 對堆疊是否有貢獻」本身是一個尚未回答的問題，但不是本 SB 能回答的問題**——它需要情緒訊號落在非 Holdout 期間的新資料，而這正是 RISK-015 資料源擴充後續案要解決的覆蓋率問題。本 SB 把這個問題明確登記為 RISK-015 的一項後續驗證項（見 §7、§9），不留給讀者自己去猜「B 臂是不是被忘記了」。

### 3.2 RISK-015 資料源擴充是否在 SB4 範圍——**答案：不在**（不變）

（同 v2，未變）

### 3.3 留言三欄真值（DEC-039）——**答案：本 SB 不直接使用**（不變，措辭同 v2 訂正版）

（同 v2，未變）

### 3.4 `Best Single Specialist` 的選法——**訂正：用 Meta-Train 選，Meta-Eval 報**

v2 原文「評估段對應期間表現最佳的單一 Specialist」是**選擇偏誤**——用 Meta-Eval 段的表現去挑「最佳」，再用同一段報告這個「最佳」的表現，會系統性高估。**訂正**：以 **Meta-Train 段**（折 0～26）各 Specialist（4 組 Arm A）的 OOF 表現排序選出最佳者，選定後**只在 Meta-Eval 段**報告其表現，與 `Meta(A)` 並列對照。

**PO 核准時追加（避免第二個隱藏偏誤）**：

1. **排序指標須事先固定為常數**，沿用 SB3 的 macro F1（`target_up_down`／`target_triple_barrier` 各自算自己的 macro F1），不得在看過結果後才決定要用哪個指標比較好看。
2. **報告不只列第一名**——四個 Specialist（Arm A）在 Meta-Train 段的完整排名與分數都要列出，讓讀者能自己判斷第一名與第二名的差距是否在雜訊範圍內（小樣本下排名本身不穩定，完整分數比單一「冠軍」更誠實）。
3. **紅測斷言**：選擇函式的實作**結構上只接受 Meta-Train 段的資料**（傳入 Meta-Eval 或 Holdout 列即拒絕），且排序指標名稱是模組層級常數（例如 `SELECTION_METRIC = "macro_f1"`），不得在呼叫端臨時覆寫。

### 3.5 RISK-009（OOF Stacking 過擬合）的具體防護設計——三層結構（不變）

（同 v2 §3.4，僅改動小節編號以容納 §3.4 新增項）

---

## 4. Meta-Learner 設計

### 4.1 OOF 矩陣的產生範圍——2 個 target × rolling × **4 組（Arm A only）**

沿用 SB3 已凍結的面板，對折 0～32（**不含折 33～42**）重新執行訓練迴圈（`prepare_fold_data`／`fit_predict_specialist_fold`，§4.2 擴充機率輸出後）。呼叫既有 `iter_model_arm_pairs()` 取得 7 組候選，**篩選 `arm == 'A'` 僅保留 4 組**——不修改該函式本身（維持 SB3 既有行為，供其他呼叫端沿用不受影響）。

**Holdout 折（33～42）內的 Specialist 模型在本 SB 全程不 fit、不 predict**——不是「fit 了但不用其輸出」，而是訓練迴圈本身的折迭代範圍就止於折 32，Holdout 折的資料連進入 `prepare_fold_data()` 的機會都沒有。這是 §4.6 守衛機制之外，從程式流程本身就杜絕碰觸 Holdout 的設計。

**OOF 覆蓋範圍**：只含折 0～32 各自測試窗涵蓋的列（§2.5 已實測列數）。面板最早 8,993 列（折 0 訓練窗前段）與折 42 之後 1,650 列從未出現在任何一折的測試窗，沒有 OOF 預測，不進入 Meta-Learner 的任何切分。

### 4.2 機率輸出設計（同 v2，`return_proba` 參數）

`fit_predict_specialist_fold()` 新增 `return_proba: bool = False` 參數，既有呼叫端零改動。`return_proba=True` 時新增 `y_proba`（`shape=(n_test, n_classes)`）與 `proba_classes`（該折訓練集實際出現的類別，遞增排序）。`target_up_down` 二分類 2 互補欄；`target_triple_barrier` 三分類最多 3 欄，缺類別折填 `NaN`。

### 4.3 市場機制特徵允許清單——`META_REGIME_FEATURE_COLS`（同 v2）

`META_REGIME_FEATURE_COLS = ["volatility_20d", "ma20_bias_ratio"]`，定義於 `src/ml/baseline_models.py`。`test_meta_uses_only_oof_preds` 依「OOF 欄 ∪ 此常數」斷言。

### 4.4 三層結構：Gate 3 Holdout ＋ 巢狀訓練／評估切分（邊界已實測，數字同 §2.5）

三段邊界與列數見 §2.5 表格，不再重複。**Holdout（折 33～42）與折 42 之後的缺口（1,650 列）都不得被 SB4～SB6 讀取、訓練、評估或用於選擇**——守衛機制見 §4.6，用 `trade_date ≥ 2025-10-23` 表達，涵蓋整個 Holdout 加缺口尾段，不是只擋 10 折本身。

三段邊界需寫入證據 JSON，並以新 ADR 登記（§4.6、§9）。

### 4.5 二階 Purge 規則——實測數字已確認（同 v2 規則，數字更新）

規則不變：Meta-Train 中任一列，若其 `label_end_date`（或 `label_end_date_tb`）晚於或等於 Meta-Eval 最早 `trade_date`（2025-05-02），須排除出 Meta-Train。

**實測規模（§2.6，取代 v2「待實作階段測量」）**：`target_up_down` 排除 150 列；`target_triple_barrier` 排除 750 列（其中標籤非 NULL 680 列）。TB 排除數多於 up_down，與預期方向一致（T+5 標籤視野比 T+1 長）。

**known-FAIL**（實作階段）：構造合成資料驗證排除邏輯，並驗證未觸發條件的正常列不被誤刪；可直接用上述兩個實測數字做迴歸基準（例如「重跑後排除列數仍為 150／750，任何偏離即代表 purge 規則或面板本身被意外改動」）。

### 4.6 OOF／證據 JSON 的資料契約——**改為逐 target 分檔**（訂正）

**訂正**：v2 曾把 `split_segment` 設計成 OOF 矩陣的單一欄，但二階 purge 依 target 不同（150 vs 750 列），**同一列在 `target_up_down` 與 `target_triple_barrier` 兩個 target 下的 `split_segment` 可能不同**（例如某列在 up_down 下仍屬 Meta-Train，在 TB 下卻因 `label_end_date_tb` 較晚而被二階 purge 排除）。單一欄無法同時表達兩者。

**訂正後設計**：**每個 target 各自一份獨立 OOF parquet**（`oof_target_up_down_<時間戳>.parquet`、`oof_target_triple_barrier_<時間戳>.parquet`），各自的 `split_segment` 依該 target 自己的 `label_end_date` 欄計算。

**每份檔案的欄位**：

| 欄位 | 說明 |
|---|---|
| `stock_id`、`trade_date` | 對齊鍵 |
| `<model>_A_p<class_token>` | 4 組 Specialist（`lr`／`rf`／`lgbm`／`xgb`，皆為 Arm A）的機率欄。`class_token`：`up_down` 用 `0`／`1`；`triple_barrier` 用 `m1`／`0`／`p1`。**欄名仍保留 `_A_` 這段**（不省略），為未來若 RISK-015 後續案改變 Arm B 可用性、需要重新引入 B 臂欄位時保留擴充空間，不需重新設計命名規則 |
| `volatility_20d`、`ma20_bias_ratio` | `META_REGIME_FEATURE_COLS`，原樣複製 |
| `fold_id` | 產生該列 OOF 預測的折序號（0～32），僅供稽核，不作為模型輸入 |
| `split_segment` | `{"meta_train", "meta_eval", "purged"}`（**PO 核准時追加第三值**）——`purged` 表示該列因 §4.5 二階 purge 被排除（`label_end_date` 或 `label_end_date_tb` 晚於或等於 Meta-Eval 最早 `trade_date`），**列本身保留在檔案內、不刪除**，只是不屬於 `meta_train` 也不屬於 `meta_eval`，讓被排除的列也有明確去處可查核，不是悄悄消失 |
| `label_end_date`（或 `label_end_date_tb`） | 該 target 對應的標籤結算日期 |
| `target_up_down`／`target_triple_barrier` | 對應 target 的原始標籤 |

**證據 JSON 頂層欄位**（記錄兩份檔案共用的邊界資訊，訂正新增）：`panel_sha256`（兩個 target 面板的 sha256，§2.3 已驗證值）、`holdout_start_date`（`2025-10-23`）、`meta_eval_start_date`（`2025-05-02`），以及各自檔案的 sha256／列數／三段（`meta_train`／`meta_eval`／`purged`）各自列數。**`purged` 列數須與 §2.6 的實測值（`up_down` 150、TB 750）核對一致**，兩者理論上完全對應——`split_segment == "purged"` 的列數就是二階 purge 排除的列數，不是另一個獨立計算。

**守衛機制**：sha256 篡改即 abort、`RangeIndex` 守衛、必要欄位守衛；任何列 `trade_date ≥ 2025-10-23`（`holdout_start_date`）即結構性拒絕。

---

## 5. In Scope

1. 新增 `src/ml/stacking.py`：OOF 矩陣組裝（§4.1、§4.6，僅 Arm A）、二階 purge（§4.5）、Meta-Learner（`LogisticRegression`＋`RidgeClassifier`）訓練與預測介面。
2. 擴充 `src/ml/specialist_training.py`：`fit_predict_specialist_fold()` 新增 `return_proba` 參數（§4.2）。
3. 擴充 `src/ml/baseline_models.py`：新增 `META_REGIME_FEATURE_COLS` 常數（§4.3）。
4. 新增段級報告腳本：`Meta(A)` 與 `Best Single Specialist`（選法見 §3.4）並列對照，Meta-Eval 段報告。
5. `src/ml/evaluator.py`：擴充消費 `y_proba` 的評估路徑。
6. 測試：`test_meta_uses_only_oof_preds`、`test_oof_no_train_leakage`（含二階 purge）、`test_meta_learner_input_shape`。
7. 新 ADR：Gate 3 Holdout 落地邊界登記（折 33～42、起日 2025-10-23、四動詞禁令、SB7 唯一消費者，§4.4、§9）。
8. `REMAINING_RISKS.md` RISK-015：登記「Arm B OOF 對堆疊的貢獻」為後續驗證項（§7、§9）。

## Out of Scope

- Arm B 的 OOF 產生與使用——本 SB 折 0～32 範圍內情緒訊號為 0，移交 RISK-015 後續案（§3.1）。
- 機率校準（`UG-G3-SB5`）。
- 信心門檻與市場狀態軟門控（`UG-G3-SB6`）。
- Holdout（折 33～42）與折 42 之後缺口的任何讀取、訓練或評估——保留給 `UG-G3-SB7`。
- `expanding` 模式的 OOF（未驗證，本 SB 不跑）。
- 資料源擴充（RISK-015 後續案，§3.2）。
- 留言三欄併入任何 Specialist Arm 的特徵白名單（§3.3）。
- Meta-Learner 超參數調整——正則化強度固定為預設值，不在本 SB 調參。
- **在 Meta-Eval 段對 `LogisticRegression` 與 `RidgeClassifier` 做二選一**（PO 核准時追加）——本 SB 只並列兩者在 Meta-Eval 段的表現，**不淘汰、不選出「更好的那個」**。理由：若本 SB 就在 Meta-Eval 段挑出勝者，`UG-G3-SB5` 的機率校準若沿用同一段資料，該段就已經被「用來選過模型」污染，不再是乾淨的校準集——哪個模型最終採用，留待有更多獨立資料（例如 SB7 的 Holdout，但 Holdout 依 §4.4 不得用於模型選擇，故實務上這個選擇會留到 Gate 3 之外或需要新資料時才做）。
- 真實庫寫入——不適用 RISK-013 三項協議。

---

## 6. Failure Semantics & Tests

| 情境 | 應有行為 | 對應測試 |
|---|---|---|
| Meta-Learner 特徵矩陣含 OOF 欄與 `META_REGIME_FEATURE_COLS` 以外的欄 | 結構性拒絕 | `test_meta_uses_only_oof_preds`（known-FAIL：混入 `rsi_14`） |
| OOF 矩陣意外含 Arm B 欄位 | 結構性拒絕（本 SB 只產 Arm A） | 新增（known-FAIL：合成一欄 `rf_B_p0` 混入） |
| Meta-Train 列的 `label_end_date`／`label_end_date_tb` 晚於或等於 Meta-Eval 最早 `trade_date` | 排除出 Meta-Train | `test_oof_no_train_leakage`（known-FAIL：對照 §2.6 實測的 150／750 基準數字） |
| Meta-Learner 輸入形狀與宣告的組合數不符 | 拋例外 | `test_meta_learner_input_shape` |
| 某折的某類別在訓練集缺席 | 對齊時填 `NaN`，不誤植 0 | 新增（known-FAIL：合成缺 Timeout 類別折） |
| OOF 矩陣讀取端發現任何列 `trade_date ≥ 2025-10-23` | 結構性拒絕 | 新增（known-FAIL：合成一列注入 Holdout 日期） |
| `Best Single Specialist` 選法誤用 Meta-Eval 段挑選 | 結構性拒絕（選擇邏輯只讀 Meta-Train 段資料） | 新增（§3.4，known-FAIL：傳入 Meta-Eval 段列驗證拒絕） |
| 選擇指標被臨時覆寫（非固定常數） | 選擇函式只讀模組層級常數，不接受外部指標名參數 | 新增（§3.4，known-FAIL：嘗試以非常數指標呼叫，驗證介面本身不允許） |
| `split_segment` 未涵蓋二階 purge 排除的列（列消失而非標記） | 結構性拒絕（輸出列數須等於輸入列數，`purged` 列保留） | 新增（§4.6，known-FAIL：比對輸出總列數與輸入總列數不符） |

---

## 7. Risks & Trade-offs

- **RISK-009（OOF Stacking 過擬合）**——§4.4／§4.5 直接回應；Meta-Eval 段（17,960 列）樣本量遠大於 v2 估計，統計把握度較 v2 預期更好。
- **RISK-015 後續驗證項（本版新增登記）**：Arm B 的 OOF 是否對堆疊有貢獻，本 SB 結構上無法回答（折 0～32 情緒訊號為 0）。待 RISK-015 資料源擴充案使情緒覆蓋率落在非 Holdout 的可用期間後，需要一次獨立的 SB4 補充實驗（或 SB4 的一次擴充）重新評估——**不是本 SB 的缺陷，是本 SB 唯讀查證出的既有現況邊界**。
- **Holdout 邊界一旦登記即不可回頭調整**——同 v2。
- **`expanding` 模式未驗證**——同 v2。
- **計算成本降低**——4 組 × 2 target × 43 折（Arm B 排除後，較 v2 估計再減少約 3/7），預期遠低於 SB3 資源用量。

---

## 8. E2E Verification Plan

1. 容器內全套測試 PASS。
2. `gate0_contract_check.py` exit 0。
3. 兩份逐 target OOF parquet 的 sha256／列數／三段列數／二階 purge 排除列數，皆寫入證據 JSON（§4.6），與 §2.5／§2.6 的實測值核對一致。
4. `Meta(A)` 與 `Best Single Specialist`（§3.4 選法）的 Meta-Eval 段指標須並列報告。
5. Holdout（折 33～42＋折 42 之後缺口）零讀取的結構性斷言存在且通過。
6. Arm B 零產出的結構性斷言存在且通過（§6）。
7. 每一項 §6 列出的測試皆需 known-FAIL 案例，實際執行並附原始輸出。

---

## 9. Documentation Sync

- **新 ADR**：登記 Gate 3 Holdout 落地邊界——折 33～42、起日 `2025-10-23`、凍結面板 sha256（§2.3 已驗證值）、「SB4～SB6 不得讀取／訓練／評估／選擇」四動詞、SB7 唯一消費者。引用 `PURGED_WALK_FORWARD_SPEC.md` §3.3、`SYSTEM_UPGRADE_MASTER_PLAN.md` §10／§11.3。狀態 `Proposed`，隨 Gate B 請 PO 核准。
- `REMAINING_RISKS.md` RISK-015：新增備註，登記「Arm B OOF 對堆疊貢獻」為後續驗證項，依賴資料源擴充案。
- `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB4 Brief：Gate B 結案時訂正 Affected Components 為實作實際觸及的完整清單。
- `REMAINING_RISKS.md` RISK-009：Gate B 時補上實際採用的防護設計與殘餘風險。
- `PROJECT_STATUS.md` §0.2／§0.5：新增 `UG-G3-SB4` 進度列，登記新 ADR 對 SB5～SB7 的約束。

---

## 10. Definition of Done

- OOF 矩陣依 §4.1／§4.6 契約產生，2 target × rolling × **4 組（Arm A only）**，範圍限於折 0～32，逐 target 分檔。
- `return_proba` 參數已落地，既有呼叫端零改動。
- `META_REGIME_FEATURE_COLS` 常數已定義並被斷言。
- 三層結構已落地，折邊界、二階 purge 排除數（150／750）寫入證據 JSON 與新 ADR。
- Meta-Eval 段報告 `Meta(A)` 與 `Best Single Specialist`（選法：Meta-Train 選、Meta-Eval 報，排序指標為固定常數，報告含完整排名非僅第一名）並列。
- `LogisticRegression` 與 `RidgeClassifier` 兩者皆完整報告 Meta-Eval 段表現，**未在本 SB 淘汰其中之一**。
- `split_segment` 含 `purged` 值，且 `purged` 列數與 §2.6 實測值（150／750）核對一致。
- Holdout 與 Arm B 零產出的結構性斷言存在且通過。
- 全套測試 PASS；`gate0_contract_check.py` exit 0；§6 全部 known-FAIL 案例已實際執行並附原始輸出。
- `REMAINING_RISKS.md` RISK-015 已登記 Arm B 後續驗證項。

---

## 11. PO 裁決狀態——**Gate A 已核准（2026-09-14）**

三輪裁決全部落地：Holdout 三層結構、二階 purge、Data Contract（含 `purged` 三值 `split_segment`）、市場機制特徵常數、Meta-Learner 模型選擇（`LogisticRegression`＋`RidgeClassifier` 並列、不在 Meta-Eval 段互相淘汰）、Arm B 排除（折 0～32 情緒訊號為 0，PO／審查方雙方獨立查證確認）、`Best Single Specialist` 選法（Meta-Train 選、固定指標常數、列完整排名）。折 26／27 切點（Meta-Eval 17,960 列、6 折）PO 已確認不需再調整。

**無待裁決項。**

---

## 12. 未獲核准前（實作 commit 前）的自我約束

- 不修改 `src/ml/` 任何檔案、不新增 `stacking.py`。
- 不對任何資料庫執行寫入或 schema 查詢以外的操作。
- 不重跑 SB3 的訓練迴圈以外的任何運算（§2.5／§2.6 的查證屬純唯讀分析，未修改任何檔案，僅讀取容器內 SB3 遺留的 parquet 副本並以 sha256 核實其未被篡改）。
- 本提案所有數字（欄位名稱、函式簽章、折邊界、三段列數、二階 purge 排除數、sha256）均為唯讀查證所得，已標示查證方式；未做任何假設性推算。

---

## 13. Gate A 核准後、紅測前的流程（PO 授權，2026-09-14）

比照 `UG-G3-SB3` 先例，Gate A 核准**不等於**可以直接開始寫紅測 commit：

1. **先產出紅測清單**（不是紅測本身）：逐項列出 §6 表格中每一項測試的具體斷言內容、預計檔案位置、known-FAIL 構造方式，送審查方複核。清單須涵蓋：`test_oof_no_train_leakage`（含二階 purge）、`test_meta_learner_input_shape`、`test_meta_uses_only_oof_preds`、缺類別 `NaN` 對齊、Holdout 守衛（`trade_date ≥ 2025-10-23`）、Arm B 零產出守衛、`Best Single Specialist` 選法（含固定指標常數、Meta-Train-only 資料來源）、`split_segment` 三值完整性（含 `purged`）、`return_proba` 參數的既有呼叫端零改動回歸驗證。
2. **審查方複核紅測清單後**，才授權建立紅測 commit（RED，全部新測試 FAIL 或標記 skip，不動生產程式碼，比照 SB3 `66114c2`／RISK-023 `66114c2` 模式）。
3. **紅測 commit 通過後**，才開始實作（GREEN）。
4. **Holdout ADR**（§9）與 `PROJECT_STATUS.md`／`REMAINING_RISKS.md` RISK-015 備註，隨紅測 commit 或實作 commit 一併送出——ADR 先 `Proposed`，Gate B 核准後轉 `APPROVED`。
5. 本 SB 全程對凍結面板運算，不涉真實庫寫入；OOF parquet 存放於 `D:\Python\Database_Backups\Stock_Prediction_System2\ml_panels\`（比照 SB3 面板凍結存放模式，非 repo 內）。

---

## 訂正紀錄

### v1 → v2（PO 第二輪複核，七項訂正）

見 v2 版本的訂正紀錄表（已併入本版各節內容，不再重複列出）：三層結構取代選項 A／B、新增二階 purge、補答 OOF 覆蓋範圍、三者並列、市場機制特徵常數、Meta-Learner 模型固定、§3.3 母體混淆訂正、`return_proba` 參數設計、新增 §4.6 Data Contract。

### v2 → v3（PO 第三輪複核，一項改判＋三處小訂正）

| # | 內容 | 本版對應 |
|---|---|---|
| 1 | Arm B 改判：折 0～32 情緒訊號為 0，三者並列失效，改為只用 Arm A、兩者並列 | §0、§3.1、§4.1、§4.6、§5、§6、§7、§10 |
| 2 | `Best Single Specialist` 選法訂正：Meta-Train 選、Meta-Eval 報，避免選擇偏誤 | §3.4 |
| 3 | `split_segment` 依 target 不同，改為逐 target 分檔（非單一 OOF 矩陣單一欄） | §4.6 |
| 4 | Holdout 守衛以 `trade_date ≥ 2025-10-23` 表達（涵蓋缺口尾段）；ADR 內容明定四要素；Holdout 折 Specialist 在 SB4 全程不 fit | §4.1、§4.4、§4.6、§9 |

### v3 → 核准（PO 2026-09-14，三點落地要求，未退回）

| # | 內容 | 本版對應 |
|---|---|---|
| 1 | `Best Single Specialist` 選法：排序指標固定為常數（macro F1），報告列完整排名非僅第一名 | §3.4 |
| 2 | `split_segment` 新增第三值 `purged`，二階 purge 排除的列保留在檔案內、不刪除 | §4.6 |
| 3 | `LogisticRegression`／`RidgeClassifier` 只並列不淘汰，避免污染 SB5 校準集 | §5 Out of Scope、§10 |
