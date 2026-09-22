# UG-G3-SB3 Gate B 送審：Specialist Models（RF／LightGBM／XGBoost）訓練與 D3 對照實驗

> **狀態**：**Gate B 已核准結案（2026-09-13，PO 核准）**。
> **對應 Gate A 提案**：`doc/upgrade/gates/UG_G3_SB3_GATE_A_PROPOSAL.md`（訂正版，PO 核准進入實作 commit `1769481`）。
> **本 SB 全程無真實庫寫入**，不適用 RISK-013 三項協議；面板匯出後全程對凍結 parquet 檔運算。

---

## 1. 完整 Commit 序列

依時間序，每項附一句話與對應證據；`✅` 標記已含真實輸出核對的 commit。

| # | Commit | 內容 |
|---|--------|------|
| 0 | `1769481` | Gate A 提案訂正版——PO 核准進入實作（回應複核退回的四個缺口） |
| 1 | `4b4ffc1` | 紅測——`baseline_models.py` 新常數／`extract_multimodal_features()` NaN 保留／`WalkForwardSplitter` fallback 拒絕／`label_end_date` 四項，`src/ml/specialist_training.py` 尚不存在 |
| 2 | `6dcbdc7` | 紅測訂正——PO 第二輪複核：`require_label_end_date` 範圍限縮為選擇性收緊（非一律拒絕）、規則 (c) 改剔除（非拋例外） |
| 3 | `cae860f` | ✅ 實作——`CORE16_STATIONARY_COLS`／`ARM_A_FEATURE_COLS`／`ARM_B_FEATURE_COLS` 新常數；`extract_multimodal_features()` 8 欄情緒特徵保留 `NaN`（**§0.5 #18 修復**）；`build_panel_dataset()` 新增 `label_end_date`；`WalkForwardSplitter` 新增 `require_label_end_date`／`purge_mode` |
| 4 | `eda08f5` | ✅ 修補 `test_label_end_date_tb_unaffected_by_new_column` 測試盲點（M6：`holding_period=1` 使 T+1 與 T+H 重合，改用 3）；`NAN_INTOLERANT_MODELS` fail-fast 擋 LR 吃到 NaN 特徵 |
| 5 | `e4cae8a` | ✅ 面板凍結匯出證據歸檔——訂正兩處歸因與數字（股票缺口成因、20/458 情緒股票數計算方法），對應 §5 面板凍結流程 |
| 6 | `baec8d9` | 紅測——訓練迴圈本體（`run_fold_for_arms`／`iter_model_arm_pairs`／`compute_per_class_metrics`／`compute_boundary_interior_metrics`）與邊界窗/內部窗洩漏診斷，含合成滲漏 Fold known-FAIL |
| 7 | `95114e0` | 補紅測——跨 Fold 洩漏彙總判準（`summarize_leakage_diagnosis`）；修正 mock 簽名脆弱處 |
| 8 | `82432ec` | ✅ 實作——訓練迴圈本體五函式＋跨 Fold 洩漏彙總函式 |
| 9 | `d1c8904` | ✅ 修正邊界窗/內部窗 Δ 可比性缺陷——限定於兩窗共同支持類別，新增 `labels_used_for_delta`／`labels_dropped` |
| 10 | `4b03b45` | 補紅測——`fit_predict_specialist_fold()` 基本介面＋兩項必修（LabelEncoder、RobustScaler） |
| 11 | `13f3208` | ✅ 實作——`fit_predict_specialist_fold()`：LabelEncoder 統一編碼、`create_scaler("robust")` train-only 縮放 |
| 12 | `ad856d6` | ✅ 段級報告腳本 `scripts/verify/ug_g3_sb3_specialist_report.py`（四項守衛：sha256／`require_label_end_date`／必要欄位／逐 Fold `purge_mode`） |
| 13 | `9eae1f9` | ✅ 報告腳本補 `sys.path`，可從任意工作目錄直接執行 |
| 14 | `bdc7929` | ✅ 報告腳本實跑前三項訂正——`sentiment_subset` 兩臂皆算、`compute_pair_aggregate()` 跨 Fold 彙總、`assert_panel_has_rangeindex()` 守衛 |
| 15 | `24ec05f` | ✅ 全量前三補件——`prepare_fold_data()` 剔除後 `y` 轉 int、`majority_baseline` 彙總、容器內 `git` 兩個環境坑修正（`-c safe.directory`／`-c core.autocrlf=true`） |
| 16 | `3ed714e` | ✅ 單配置報告樣本——`target_triple_barrier × rolling × RF × A/B`（樣本，非全量） |
| 17 | `90d8369` | ✅ **全量**——`target_up_down × rolling × 4 模型 × A/B` |
| 18 | `968828e` | ✅ **全量**——`target_triple_barrier × rolling × 4 模型 × A/B`（覆蓋樣本，RF 兩臂逐 Fold 指紋核對與 `3ed714e` 逐位相同） |
| 19 | `4ce5bfa` | ✅ **全量**——`target_triple_barrier × expanding × 4 模型 × A/B`（RF-only 探測 163 秒後才跑全量） |
| 20 | `32fc298` | ✅ **全量**——`target_up_down × expanding × 4 模型 × A/B` |
| 21 | `79fd08e` | ✅ 報告腳本補訊號列子集（`signal_rows_subset`）——量化「情緒覆蓋率不足」的依據 |
| 22 | `8b9077e` | ✅ 全量重跑——`target_up_down × rolling` 補訊號列子集（deep-equal 核對其餘欄位與前版逐位相同） |
| 23 | `0d58d5e` | ✅ 全量重跑——`target_triple_barrier × rolling` 補訊號列子集 |
| 24 | `98ba197` | ✅ 全量重跑——`target_triple_barrier × expanding` 補訊號列子集 |
| 25 | `1beb24f` | ✅ 全量重跑——`target_up_down × expanding` 補訊號列子集（四份報告 JSON 全部補齊完成，**現行 HEAD**） |

**四份證據 JSON 的 sha256（最終版，皆含 `signal_rows_subset`）**：

| 檔案 | sha256 | 產出 commit |
|---|---|---|
| `UG_G3_SB3_report_target_up_down_rolling.json` | `37f45865d60efde7434d2485c07426df43efb14fc22eafb8c49ecc9fe78ebc88` | `8b9077e` |
| `UG_G3_SB3_report_target_triple_barrier_rolling.json` | `2f10ca1635ae243a5b2f8a6154c0b9b48e8d6f5b8c19fa7538c703b09e2a9145` | `0d58d5e` |
| `UG_G3_SB3_report_target_triple_barrier_expanding.json` | `492366b3ef367346819f34af5079f261990ade23509d5349febfa4dba01d3b44` | `98ba197` |
| `UG_G3_SB3_report_target_up_down_expanding.json` | `1ede3f10c33df258485b92f11e7c7ca1c3e2f1299accad4a2a4ad074e6eff5e5` | `1beb24f` |

面板凍結證據：`doc/upgrade/gates/evidence/UG_G3_SB3_panel_export.json`（`e4cae8a`）；凍結基準 `stock_prediction_system2_POST_g3_sb2a_stage2_rerun_risk027_20260912_121252.dump`（Gate A §3.5 裁決指定）。

---

## 2. 五項必答的最終答案

### 2.1 RISK-025：Triple-Barrier Timeout <5% 在 D3 的處置

**答案**：段級報告對 `target_triple_barrier` 逐 (model, arm, mode) 輸出三分類 per-class Precision／Recall／F1（不只 Macro 平均）。**28 組實測**（`VERIFIED THIS SESSION`，可重跑：`python scripts/verify/ug_g3_sb3_specialist_report.py --target target_triple_barrier --mode {rolling,expanding} --models logistic_regression,random_forest,lightgbm,xgboost --arms A,B`）：

- 多數類（`-1`，止損）recall **0.916～0.971**——模型明顯偏向多數類。
- Timeout（`0`）recall **0.163～0.301**——比全表 5.17% 的先驗比例高（模型有學到部分訊號），但遠非可靠。**macro F1（0.340～0.366）高於多數類基線（0.240）的部分主要來自這裡**——多數類基線對 Timeout 的 recall 恆為 0，模型能有 0.163～0.301 即構成差距。
- 獲利出場（`+1`）recall **0.020～0.080**——四模型兩臂兩模式下全面偏低，這個類別的 F1 幾乎為零，**對 macro F1 的貢獻可忽略**，**不構成「模型能可靠辨識獲利時機」的證據**。

**裁決沿用**（PO 2026-09-12 已裁決 (c)）：不在本 SB 調寬 barrier 或改 Dynamic；本 SB 只揭露證據。**下一步**（調寬 barrier width 或改採 Dynamic barrier）留待另案，不在本 Gate B 範圍。

### 2.2 rolling vs expanding：內建子實驗

**答案**：不產出「哪個模式更好」的單一結論（Gate A §3.2 已裁定），兩模式共用同一批 43 Fold 並列數字：

- `target_up_down`：**rolling 略高**（macro F1 中位數 0.468～0.490）於 expanding（0.447～0.457）。
- `target_triple_barrier`：**expanding 略高**（0.347～0.366）於 rolling（0.340～0.356）。

方向在兩個 target 上相反，且差距皆在 ±0.02 量級——**不足以支持任一模式的普遍優越性宣稱**。最終建模選擇仍是 PO 的決定，本 SB 僅並列證據。

### 2.3 Embargo 長度與洩漏診斷

**答案**：`embargo_days=0` 的失效條件（Gate 3 啟動裁決③，標籤視野一變即需重議）已於 `UG-G3-SB1`（H=5）字面觸發，本 SB 的邊界窗/內部窗洩漏診斷即為責任落地。**28 組（target×mode×model×arm）逐 Fold 診斷，`leakage_summary.flagged` 全數 `False`**——`frac_positive`（Δ>0 比例，實測 0.44～0.53）與 `median_delta`（實測接近 0）皆未達雙門檻（`≥0.70` 且 `≥0.05`）。**結論：本次量測未發現邊界窗系統性異常，`embargo_days=0` 維持有效**（已登記 `PROJECT_STATUS.md` §0.5 #16，見 §7）。診斷方法本身的 known-FAIL（合成滲漏 Fold 必被標示）已於紅測 `baec8d9` 執行並通過，**同時明寫此法不窮盡所有滲漏形式**（Gate A §7 已載明）。

### 2.4 `sentiment_mean` NULL 0.998（RISK-015）

**答案**：修復（`extract_multimodal_features()` 8 情緒欄保留 `NaN`，commit `cae860f`）與範圍量化並行——四個口徑各回答不同問題，不可互相替代：

| 口徑 | 定義 | 數字 |
|---|---|---|
| 全表（`daily_ml_features`） | 原始登記 NULL 佔比，含非面板股票與時間範圍 | 0.998 NULL |
| 面板股票子集（`sentiment_subset`） | 曾出現過非 `NULL` `sentiment_mean` 的股票，取其全部列 | **20／458 = 4.4%** |
| 面板情緒列 | `sentiment_mean` 本身非 `NULL` 的列 | **683／139,585 = 0.49%** |
| 面板訊號列（`signal_rows_subset`，**本 SB 新增，量化依據**） | `article_count>0` 或 `sentiment_5d_ma` 非 `NULL` 的列——與 target 無關，兩個 parquet 皆同 | **1,409／139,585 = 1.01%**；扣掉 target `NULL` 後：`target_up_down` 1,394 列、`target_triple_barrier` 1,069 列 |

**進入測試集的訊號列**（跨 43 Fold 加總後的 `n_total`，`VERIFIED THIS SESSION`）：`target_up_down` **1,298**、`target_triple_barrier` **1,034**——43 Fold 中僅 **8 個**有非零列，其餘 35 個為 0。逐 Fold `n`（第一個 Fold 僅個位數，其餘 122～216 列）：

- `target_up_down`：4, 142, 216, 204, 192, 172, 191, 177
- `target_triple_barrier`：3, 122, 181, 170, 139, 135, 137, 147

**D3 對照臂 B 相對 A 的樣本外表現**：全宇宙差 ±0.01（macro F1），20 檔子集差 ±0.02，訊號列子集（上表 `n_total`）方向不一致（`target_up_down` 多數組合 B 較高，`target_triple_barrier` 多數組合 B 較低）。**裁決文字（PO 2026-09-13）**：**在 0.49%（`sentiment_mean` 本身）／1.01%（B 臂真正多出資訊的訊號列）的覆蓋率下，本實驗無法區分 B 臂與 A 臂；D3 對「覆蓋率夠不夠」的回答是「不夠」**。後續案為資料源擴充（`RISK-015`），不是換模型。

### 2.5 面板凍結時點

**答案**：每日 ETL 首跑之前凍結，基準為指定 POST 備份（Gate A §3.5 裁決）。`build_panel_dataset()` 對兩種 `target_column` 各呼叫一次，匯出 parquet（不進版控，僅 sha256／列數/欄位/日期範圍等文字證據進版控，`e4cae8a`）。**本 SB 之後所有 Fold 切分、模型訓練、洩漏診斷皆讀這份匯出檔**——四次全量報告執行前皆由腳本守衛 1 驗證 parquet 實際 sha256 與 evidence JSON 記載值相符，不符即 abort（結構上不可能對未經複核的面板產出報告）。**本 SB 不觸發、不等待、也不阻擋每日 ETL 首跑**。

---

## 3. 揭露清單

以下事項皆與本 Gate B 相關但**不阻擋核准**：

1. **`labels_dropped` 三個 Fold**——`target_triple_barrier`（rolling 與 expanding 皆同）在 fold 26／40／42 的 **interior 側**缺 class `0`（Timeout），boundary 側無缺；7 個 (model, arm) 全部一致。這正是 `d1c8904` 修 Δ 可比性缺陷時預期會發生的情況（Timeout 僅占 ~5%，小樣本 Fold 偶爾缺席），證明那次修正不是多餘的。
2. **NVDA 不在面板**——`universe_snapshots` 候選空間為「台股普通股」，NVDA（美股）`included` 從未涵蓋它，兩個 target 面板皆為 458 檔，非全表口徑的 459 檔。
3. **`script_untracked_paths` 屬執行環境快照**——記錄執行當下工作樹的未追蹤檔案清單（例如本機 `.claude/settings.local.json`），會隨執行當下本機狀態變動（實測：`target_up_down×rolling` 兩次執行分別為 2 個與 1 個未追蹤檔），**不是模型輸出的一部分、不影響任何數值正確性**，僅供環境可追溯性參考。
4. **RF 超參數用工廠預設**（`PureTechnicalModelFactory`：50 棵樹／深 5／`n_jobs=-1`），**Gate A §2.3 的舊耗時估計（200 棵樹、外推 ~13 分鐘 rolling／~112 分鐘 expanding）已標為過期**——實測數字（本文件 §6）遠低於外推值，因子為實際走工廠預設而非一次性測試用的超參數。
5. **LR 全數收斂**——28 組中 `n_lr_max_iter_hits` 全數為 0，`create_scaler("robust")` train-only 縮放修復（`13f3208`）在真實面板資料上生效。
6. **兩種子集口徑並列，不可混淆**：`sentiment_subset`（股票子集，20/458，較寬——同一檔股票的其他日期即使沒訊號也算在內）與 `signal_rows_subset`（列子集，1,409/139,585＝1.01%，較精確——只算真的帶訊號的列本身，扣掉 target `NULL` 後進入測試集的加總為 1,298／1,034）。**模型高於多數類基線的部分（`target_up_down` 約 0.10～0.15，`target_triple_barrier` 約 0.10～0.12）主要來自 Timeout 類別的部分辨識能力（RISK-025，§2.1），不是情緒特徵貢獻**——B 臂並未系統性高於 A 臂。

---

## 4. Definition of Done 逐項對號（Gate A §10）

| # | 項目 | 狀態 | 對應 |
|---|------|------|------|
| 1 | `baseline_models.py` 新增三常數，既有常數與消費者零行為變化 | ✅ 已完成 | `cae860f`；`test_arm_a_excludes_raw_price`／`test_arm_b_equals_arm_a_plus_sentiment` |
| 2 | `extract_multimodal_features()` 修復（8 欄保留 NaN）並通過回歸測試 | ✅ 已完成 | `cae860f`；known-FAIL 見 §5 |
| 3 | `build_panel_dataset()` 新增 `label_end_date`；`WalkForwardSplitter` 缺欄拋例外，`purged_samples` 精確值/近似值對照 | ✅ 已完成 | `cae860f`；`test_panel_dataset_produces_label_end_date`／`test_split_refuses_fallback_purge_when_required` |
| 4 | 面板匯出檔案產生，雜湊/列數/日期範圍記入證據文件 | ✅ 已完成 | `e4cae8a`，`UG_G3_SB3_panel_export.json` |
| 5 | 單 Fold 耗時實測完成，取代外推估計 | ✅ 已完成 | RF-only 探測（163 秒）→ §3 揭露清單第 4 項 |
| 6 | 三 Specialist × 兩對照臂（B 排除 LR）× 兩模式，凍結面板上完成 Purged WF 訓練評估 | ✅ 已完成 | `90d8369`／`968828e`／`4ce5bfa`／`32fc298`（首版）＋`8b9077e`／`0d58d5e`／`98ba197`／`1beb24f`（補訊號列子集） |
| 7 | 段級報告含全宇宙／20 檔子集並列 D3 對照、RISK-025 per-class 揭露、rolling vs expanding 對照、邊界窗 vs 內部窗洩漏診斷 | ✅ 已完成 | 四份證據 JSON；§2 本文件 |
| 8 | NaN/NULL 標籤處理規則 (a)(b)(c) 全部有對應測試與 known-FAIL | ✅ 已完成 | `4b4ffc1`→`cae860f`；`tests/test_ug_g3_sb3_specialist_training_red.py` |
| 9 | 全套測試 PASS；`gate0_contract_check.py` 13/13 PASS exit 0 | ✅ 已完成 | §5 |
| 10 | 無任何資料庫寫入 | ✅ 已完成 | 全程唯讀 parquet + evidence JSON；報告腳本結構上不匯入任何 DB 驅動程式（`NoDatabaseImportTests`） |

**額外完成（超出原 DoD，PO 複核期間追加要求）**：`signal_rows_subset`（§2.4 量化依據）、`majority_baseline`（跨 Fold 多數類基線彙總）、`script_commit`/`script_dirty`/`run_timestamp`（輸出可追溯性）。

---

## 5. 驗證環境與結果

**執行環境**：容器（`stock_prediction_system2_devcontainer-app-1`），Python 3.14.6，HEAD `1beb24f`。

**依賴狀態**（12 項）：全部 `PRESENT`，無 fallback／mock 路徑，ML 相關測試皆走真實 sklearn／lightgbm／xgboost 實作。

**全套測試**（`python -m unittest discover -s tests -p "test_*.py"`，`VERIFIED THIS SESSION`）：

```
Ran 797 tests in 44.000s
OK
```

**跨文件契約驗證**（`python scripts/verify/gate0_contract_check.py`，`VERIFIED THIS SESSION`）：`Part B: 13/13 PASS`，`exit 0`。

**格式／秘密掃描**：本 Gate B 涉及的 26 個 commit（編號 0～25），每一個在建立當下皆經 `.githooks/pre-commit`（GOV-04）機械檢查（跨文件契約驗證、`numstat` 與 `-w` 一致性、GOV-13 秘密偵測）攔截，四項檢查逐次皆為 PASS 才允許 commit 建立。兩次 `SKIP_CHECK2_REASON` 具名跳過：`24ec05f`（情況(2)：`run_single_configuration()` 移除條件包裹造成的縮排位移）**已在該 commit message 本文中指名分類**；`968828e`（情況(3)：新增 `logistic_regression__A` 鍵插入造成的 diff 配對位移，`numstat` 38,803/3,392 vs `-w` 38,821/3,410，零空白內容變更）**當時僅以環境變數傳給 hook，未寫入 commit message 本文**——PO 複核發現此缺漏（與 `6dcbdc7` 同型，第二次），已於本 Gate B 結案 commit 訊息中補記分類。

**known-FAIL 案例**（代表性，逐一為真的會失敗的案例）：

| 領域 | 代表性 known-FAIL 案例 |
|---|---|
| 情緒欄 NaN 保留 | `test_extract_multimodal_features_preserves_all_sentiment_nan`（修復前 5 欄落 `else: fillna(0.0)` 分支必 FAIL） |
| Purge fallback 拒絕 | `test_split_refuses_fallback_purge_when_required`（`require_label_end_date=True` 時缺欄必拋 `KeyError`） |
| 邊界窗/內部窗 Δ 可比性 | `test_label_set_mismatch_produces_false_delta_without_intersection_fix`（修復前 Δ≈0.44 假訊號，修復後 Δ=0） |
| LabelEncoder 編碼 | `test_triple_barrier_labels_supported_by_all_models`（拿掉編碼時 xgboost 對 `{-1,0,1}` 直接拋 `ValueError`，已實測複現） |
| RobustScaler train-only 縮放 | `test_lr_scaling_prevents_max_iter_convergence_failure`（拿掉 scaler 時 `n_iter_=500` 撞滿且發 `ConvergenceWarning`） |
| 段級報告守衛 1（sha256） | `test_mismatched_sha256_raises`（parquet 篡改或 evidence JSON 過期必拋 `PanelIntegrityError`） |
| 段級報告守衛 4（`purge_mode`） | `test_non_exact_purge_mode_raises`（偽造 `purge_mode='approximate'` 必拋） |
| RangeIndex 守衛 | `test_non_rangeindex_panel_raises`（面板索引非預設 RangeIndex 必拋） |
| 容器 git 環境修正 | `test_git_commands_carry_both_c_flags`（拿掉 `core.autocrlf` 的 `-c` 參數必 FAIL） |
| 訊號列子集彙總 | `test_signal_rows_subset_aggregate_matches_hand_calculation`（合成 fold 手算中位數比對） |

---

## 6. D3 對照實驗結果總表

（模型 × 臂 × 模式 × 目標；macro F1 中位數、多數類基線中位數、20 檔子集中位數、per-class recall、洩漏診斷 flag、LR `n_iter_` 撞滿數）

| target | mode | model | arm | macroF1_med | majority_med | subset_med | recall (by class) | leak_flag | lr_max_iter_hits |
|---|---|---|---|---|---|---|---|---|---|
| target_up_down | rolling | logistic_regression | A | 0.468 | 0.341 | 0.450 | 0:0.760 / 1:0.260 | False | 0 |
| target_up_down | rolling | random_forest | A | 0.482 | 0.341 | 0.460 | 0:0.758 / 1:0.273 | False | 0 |
| target_up_down | rolling | random_forest | B | 0.486 | 0.341 | 0.459 | 0:0.755 / 1:0.274 | False | 0 |
| target_up_down | rolling | lightgbm | A | 0.488 | 0.341 | 0.465 | 0:0.739 / 1:0.289 | False | 0 |
| target_up_down | rolling | lightgbm | B | 0.485 | 0.341 | 0.462 | 0:0.737 / 1:0.290 | False | 0 |
| target_up_down | rolling | xgboost | A | 0.490 | 0.341 | 0.461 | 0:0.739 / 1:0.289 | False | 0 |
| target_up_down | rolling | xgboost | B | 0.482 | 0.341 | 0.465 | 0:0.741 / 1:0.285 | False | 0 |
| target_up_down | expanding | logistic_regression | A | 0.447 | 0.341 | 0.436 | 0:0.799 / 1:0.217 | False | 0 |
| target_up_down | expanding | random_forest | A | 0.450 | 0.341 | 0.453 | 0:0.809 / 1:0.219 | False | 0 |
| target_up_down | expanding | random_forest | B | 0.448 | 0.341 | 0.453 | 0:0.811 / 1:0.221 | False | 0 |
| target_up_down | expanding | lightgbm | A | 0.457 | 0.341 | 0.462 | 0:0.798 / 1:0.229 | False | 0 |
| target_up_down | expanding | lightgbm | B | 0.457 | 0.341 | 0.460 | 0:0.797 / 1:0.230 | False | 0 |
| target_up_down | expanding | xgboost | A | 0.456 | 0.341 | 0.455 | 0:0.799 / 1:0.228 | False | 0 |
| target_up_down | expanding | xgboost | B | 0.456 | 0.341 | 0.455 | 0:0.797 / 1:0.230 | False | 0 |
| target_triple_barrier | rolling | logistic_regression | A | 0.356 | 0.240 | 0.264 | -1:0.948 / 0:0.258 / 1:0.045 | False | 0 |
| target_triple_barrier | rolling | random_forest | A | 0.340 | 0.240 | 0.268 | -1:0.946 / 0:0.199 / 1:0.050 | False | 0 |
| target_triple_barrier | rolling | random_forest | B | 0.342 | 0.240 | 0.266 | -1:0.950 / 0:0.195 / 1:0.046 | False | 0 |
| target_triple_barrier | rolling | lightgbm | A | 0.354 | 0.240 | 0.281 | -1:0.916 / 0:0.209 / 1:0.080 | False | 0 |
| target_triple_barrier | rolling | lightgbm | B | 0.355 | 0.240 | 0.281 | -1:0.916 / 0:0.210 / 1:0.080 | False | 0 |
| target_triple_barrier | rolling | xgboost | A | 0.351 | 0.240 | 0.273 | -1:0.928 / 0:0.163 / 1:0.069 | False | 0 |
| target_triple_barrier | rolling | xgboost | B | 0.351 | 0.240 | 0.275 | -1:0.928 / 0:0.162 / 1:0.069 | False | 0 |
| target_triple_barrier | expanding | logistic_regression | A | 0.366 | 0.240 | 0.252 | -1:0.952 / 0:0.301 / 1:0.041 | False | 0 |
| target_triple_barrier | expanding | random_forest | A | 0.356 | 0.240 | 0.253 | -1:0.968 / 0:0.252 / 1:0.024 | False | 0 |
| target_triple_barrier | expanding | random_forest | B | 0.358 | 0.240 | 0.250 | -1:0.971 / 0:0.258 / 1:0.020 | False | 0 |
| target_triple_barrier | expanding | lightgbm | A | 0.364 | 0.240 | 0.262 | -1:0.945 / 0:0.253 / 1:0.050 | False | 0 |
| target_triple_barrier | expanding | lightgbm | B | 0.364 | 0.240 | 0.260 | -1:0.945 / 0:0.253 / 1:0.050 | False | 0 |
| target_triple_barrier | expanding | xgboost | A | 0.347 | 0.240 | 0.253 | -1:0.955 / 0:0.199 / 1:0.043 | False | 0 |
| target_triple_barrier | expanding | xgboost | B | 0.347 | 0.240 | 0.250 | -1:0.955 / 0:0.200 / 1:0.043 | False | 0 |

**耗時**（容器 4GB／1.5 CPU）：rolling 每 (model,arm) 約 1.4～12.8 秒；expanding 約 7～113 秒（訓練集隨 Fold 累積擴大，LR／RF 增幅最明顯）。全部四次全量執行皆遠低於 30 分鐘停下門檻，實測數字已取代 Gate A §2.3 的外推估計。

**訊號列子集（`signal_rows_subset`）A vs B 對照**（§2.4 量化依據，8/43 Fold 有非零列）：

| target | mode | model | macroF1_med (A/B) | n_folds_with_data | n_total |
|---|---|---|---|---|---|
| target_up_down | rolling | RF/LightGBM/XGBoost | 0.469/0.495、0.475/0.499、0.487/0.489 | 8 | 1298 |
| target_up_down | expanding | RF/LightGBM/XGBoost | 0.508/0.510、0.513/0.516、0.503/0.509 | 8 | 1298 |
| target_triple_barrier | rolling | RF/LightGBM/XGBoost | 0.280/0.272、0.315/0.315、0.302/0.300 | 8 | 1034 |
| target_triple_barrier | expanding | RF/LightGBM/XGBoost | 0.258/0.249、0.273/0.265、0.260/0.251 | 8 | 1034 |

---

## 7. 文件同步

本 Gate B 送審**同一批**完成以下同步（草稿階段，隨本文件一併複核）：

- **`PROJECT_STATUS.md`**：§0.2 新增 `UG-G3-SB3` 列（狀態：Gate B 送審中，待核准）；§0.5 #16 追加 rolling/expanding 與 embargo 洩漏診斷的實測結論（本文件 §2.2／§2.3）；§0.5 新增一則登記 RISK-023 排程（本 Gate B 核准後、`UG-G3-SB4` 之前，走 `bug-fix-protocol` 獨立小案）與容器 `git` 設定（`safe.directory`／`core.autocrlf`）小案候補（`.devcontainer/devcontainer.json` `postCreateCommand` 加設定，比照 `679e26e` 環境小案模式，需 PO 授權，本次僅登記不動工）。
- **`REMAINING_RISKS.md`**：RISK-025 追加 28 組 per-class 實測結果段落（本文件 §2.1）；RISK-015 追加「D3 回答：覆蓋率不夠」裁決文字（本文件 §2.4）；RISK-023 處置欄補排程（本 Gate B 之後、`UG-G3-SB4` 之前）。
- **`SYSTEM_UPGRADE_MASTER_PLAN.md`** §9 `UG-G3-SB3` Brief：Affected Components 訂正為實際觸及的完整清單（`src/ml/baseline_models.py`、`src/ml/model_trainer.py`、`src/ml/panel_dataset.py`、`src/ml/time_series_split.py`、新模組 `src/ml/specialist_training.py`、新腳本 `scripts/verify/ug_g3_sb3_specialist_report.py`）；狀態區塊標記完成。
- **`FEATURE_REGISTRY.md`**：已檢查（`grep` 掃描），本 SB 未新增或修改任何 DB 欄位契約，**無需同步**。

---

## 8. 新 ADR 提案（`DEC-038`，狀態 `PROPOSED`，待 PO 核准）

**決策名稱**：D3 對照實驗的兩種情緒覆蓋率子集口徑，以及多數類基線的 tie-break 規則。

**背景**：Gate A 提案原只設計「情緒子集（股票層級）」一種對照口徑，PO 複核全量結果後指出這不足以量化「B 臂與 A 臂在 99.5% 的列上輸入完全相同」這件事，需要「列層級」的訊號子集才是量化依據。

**決策內容**：
1. `sentiment_subset`（股票子集）與 `signal_rows_subset`（列子集）為兩種**互補、非互斥**的口徑，皆需在段級報告並列，不得只取其一。
2. 多數類基線（`majority_baseline`）票數並列時取數值最小者（`np.unique` 遞增排序 + `argmax` 取第一個最大值），確保可重現。
3. 兩種子集與多數類基線的定義字串（`SUBSET_DEFINITIONS`／`MAJORITY_BASELINE_RULE`）寫入報告 JSON 本身，不只留在原始碼 docstring 裡——供 Gate B 讀者查核而不需回頭讀程式碼。

**理由**：股票子集的「同一檔股票的其他日期即使沒訊號也算在內」會高估 B 臂實際可用的資訊量；列子集才是「B 臂真的多出資訊的列」的精確定義，是「覆蓋率不足以檢定」這一裁決文字（§2.4）的量化基礎，未來任何情緒特徵相關的 D3 型實驗（若擴充資料源後重跑）應沿用同一組口徑定義以維持可比性。

**影響範圍**：`scripts/verify/ug_g3_sb3_specialist_report.py`（`determine_signal_row_mask`／`SUBSET_DEFINITIONS`／`MAJORITY_BASELINE_RULE`）。

**驗證**：`tests/test_ug_g3_sb3_specialist_report.py::SignalRowMaskTests`／`AggregateAcrossFoldsTests`（含 tie-break 規則的 known-FAIL 對照）。

**剩餘風險**：若未來資料源擴充（RISK-015 後續案）使覆蓋率大幅提升，`signal_rows_subset` 與 `sentiment_subset` 的差距會縮小，屆時兩種口徑是否仍需並列可重新評估，不在本決策預先假設。

---

## 9. 未驗證清單（有名字有去處）

| 項目 | 去處 |
|------|------|
| RISK-025 barrier width 調整或改 Dynamic barrier 的實際執行 | 另案，非本 SB 範圍（§2.1 已裁決不執行） |
| RISK-023（留言三欄逐則時間戳重算）修復 | 本 Gate B 核准後、`UG-G3-SB4` 之前，走 `bug-fix-protocol` 獨立小案 |
| rolling vs expanding 最終建模選擇 | PO 建模決定，本 SB 僅並列證據（§2.2），不代為決定 |
| Gate 2 tournament `LR × MultiModal` 組因 §0.5 #18 修復而失效 | 已登記 `PROJECT_STATUS.md` §0.5 #21，去處 `UG-G3-SB7`（Benchmark 重建時重定義） |
| 情緒覆蓋率擴大後 D3 是否能給出有統計力的答案 | RISK-015 後續案（資料源擴充），非模型層面可解 |
| `.devcontainer` 容器 git 環境設定（`safe.directory`／`core.autocrlf`）常設化 | 待 PO 授權的環境小案，本 Gate B 僅登記候補（§7） |

---

## 10. 證據標籤

- 本文件第 1、4、5、6 節列出的所有 commit hash、sha256、測試計數，凡標註 `✅ 已完成`／`VERIFIED THIS SESSION` 者，其底層驗證動作（容器內執行、獨立 deep-equal 比對、known-FAIL 案例實測）皆為 **`VERIFIED THIS SESSION`**，可重跑指令見 §1／§5／各 commit message。
- 第 2 節「五項必答」引用的 Gate A 裁決本身（RISK-025 選項 (c)、洩漏診斷方法核准等）標為 **`PREVIOUSLY VERIFIED`**（記錄位置：`UG_G3_SB3_GATE_A_PROPOSAL.md` §3、§11）。
- 第 3 節揭露清單第 3 項（`script_untracked_paths`）的兩次觀察數字（2 個／1 個）為 **`VERIFIED THIS SESSION`**（PO 獨立重跑核對）。

---

## 11. 核准後動作（已執行，2026-09-13）

依 `CLAUDE.md` §16.3、`gate-submit` skill 產出 8：

1. `git mv` 本文件與 `UG_G3_SB3_GATE_A_PROPOSAL.md` 至 `doc/upgrade/gates/closed/`。
2. 確認 `git diff --cached --name-status` 顯示為 `R100`（純 rename）。
3. 檢查搬移後的檔案是否出現在 `gate0_contract_check.py` 的 `DOC_PATHS`，若有則同一 commit 內更新。
4. 同步 `doc/README.md` 逐份文件表。
5. `PROJECT_STATUS.md` §0.2 `UG-G3-SB3` 列狀態改為 `CLOSED`，附核准日期與結案 commit hash。
6. `DECISIONS.md`：`DEC-038` 若 PO 核准則轉 `APPROVED`，補進 `TRACEABILITY.md` 對應分節。
7. 核准後方可依 §9 排程開啟 RISK-023 獨立小案（`bug-fix-protocol`）。
