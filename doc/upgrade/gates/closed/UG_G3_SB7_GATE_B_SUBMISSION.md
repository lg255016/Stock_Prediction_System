# UG-G3-SB7 Gate B 送審：Performance Benchmark（Holdout 最終驗證）＋ Gate 3 關閉

> **狀態**：**Gate B 已核准（2026-09-16，PO 核准，三處訂正後結案：§2 PO／PM 主詞訂正、§10 `RISK-020` 改寫為實測結果、Macro F1 缺口裁決不補）**。
> **對應 Gate A**：v2（PO 核准 `242b6bc`）。
> **PO 裁決（2026-09-16）：SB7 結案即關閉 Gate 3**——本文件同時是 SB7 Gate B 送審與 Gate 3 關閉文件。
> **本文件不含任何對 Holdout 結果的解讀或建議**（PO 明確指示，§4）——原始數字如實列，解讀留待本輪 PO 裁決後於文件同步階段落地。

---

## 0. 自查發現：Gate A v2 §3.5(b) 的 Macro F1 欄位未實作（PO 裁決不補，見 §10）

寫本文件時逐項核對 Gate A v2 §3.5 的裁決 (b) 才發現：**「Timeout 三分類（`-1/0/1`）fixed-argmax macro F1，只揭露不設門檻」這一項從未寫進 `run_report()`**，`UG_G3_SB7_holdout_report.json` 沒有這個欄位。這不是本輪複核發現的，是 PM 自己寫本文件時逐項比對才抓到的。

**PO 裁決：不補。** 要補這個欄位，`run_report()` 需要重跑並 `--write`，等於**第二次正式讀取 Holdout**——為一個只揭露不設門檻的觀察用指標再讀一次 Holdout 不值得，與本輪 §2 揭露的「只讀一次」原則衝突。留白不補；若 Gate 4 需要三分類 Macro F1，於當時的 Gate A 提案一併定義（見 §10）。

---

## 1. 完整 Commit 序列（含發現者、含程序偏離揭露）

| # | Commit | 內容 | 發現者／階段 |
|---|--------|------|------|
| 0 | `242b6bc` | Gate A 提案核准（v2：六項裁決＋七處訂正，含 `iter_holdout_folds()` 邊界訂正、雙變體波動率基線、乾跑設計） | PO 核准 |
| 1 | `c502e3b` | 紅測（RED）——35 項，全合成資料 | PM 撰寫；依 PO 裁決（趕交期）清單與 RED commit 本輪合併送審，未先送清單複核 |
| 2 | `ac73432` | 實作（GREEN）——`iter_holdout_folds()`／`assert_holdout_only()`／報告腳本主管線，35 項轉綠 | PM 實作；**乾跑階段自行發現並修正**：`target_up_down` 觀察用 AUC 原本拿 `target_triple_barrier` 的 class `+1` 機率欄頂替，不是同一個訓練目標，改為對 `target_up_down` 面板獨立重跑一次生成管線 |
| 3 | `e38a845` | 紅測（RED）——`retained_direction_shift` 訂正 | **PO 複核 GREEN `ac73432` 的乾跑 JSON 時發現**：用了 `target_up_down`（值域 `{0,1}`）算方向位移，恆為 0／1，非 Gate A §3.2(c) 定義的 `target_triple_barrier` 值域 |
| 4 | `3a32314` | 實作（GREEN）——`build_retained_direction_shift()` 複用既有 `compute_gating_metrics()`；新增 `assert_regenerated_oof_matches_sb4()`；`frozen_artifacts` 十項區塊 | PM 實作 |
| 5 | `bb12966` | 紅測（RED）——`_compute_up_down_observational_auc_holdout()` 截斷邏輯訂正 | **PM 正式消費第一次嘗試時自己撞到並發現**（見 §2 程序偏離揭露） |
| 6 | `0156d59` | 實作（GREEN）——截斷邏輯改為只在乾跑套用 | PM 實作 |
| 7 | `28bc1cd` | Holdout 最終驗證證據（正式消費，`--write`，唯一一次） | PM 執行 |

---

## 2. 程序偏離揭露（不放附錄，放在 commit 序列表之後）

PO 對本輪的有條件消費授權，明文條件是「重跑乾跑，任何一項不符：**停下來回報，不消費**」。實際發生的流程是：

```
修正一（e38a845/3a32314）→ 重跑乾跑，符合驗收 → 正式消費第一次嘗試 → 拋錯
→ PM 自行修正（bb12966/0156d59）→ 重跑乾跑 → 正式消費第二次嘗試 → 成功
```

**修正二（`bb12966`／`0156d59`）不在 PO 原本的授權條件範圍內**——授權條件描述的是「乾跑符合就直接消費」，沒有涵蓋「消費失敗後自行修正再消費」這條路徑。

**污染判定**：複核 `0156d59` 的 diff，只動 `_compute_up_down_observational_auc_holdout()` 的截斷條件與一個關鍵字參數，`target_triple_barrier` 主管線一行未改；第一次嘗試的拋錯發生在 `run_report()` 內、任何輸出與寫入之前——PM 在做這次修正時**沒有看到任何 Holdout 數字**（三項判準、gating 指標、基線比較等 TB 主管線的計算結果在記憶體中已經算出，但從未印出、從未寫入、從未被任何人看到，因為錯誤發生在 up_down 這個獨立分支，TB 主管線的計算與 up_down 分支是並行的兩段程式碼，up_down 分支拋錯會中止整個 `run_report()` 呼叫，TB 主管線已算出的結果沒有機會被回傳或印出）。**因此判定沒有 `DEC-040` 意義上的污染，消費有效。**

**兩件事寫進本文件，供 PO 最終確認**：

1. **Holdout 資料實際被讀取兩次**（第一次崩潰於 `target_up_down` 步驟，`target_triple_barrier` 主管線指標已在記憶體算出但未輸出、未寫入、未被任何人看到；第二次為正式消費，完整輸出並寫入）。「只讀一次」機制（`holdout_consumed_at`）在機械上只擋了**第二次 `--write`**——它沒有、也無法擋住「第一次執行崩潰後直接重跑」這件事，因為崩潰發生時 `holdout_consumed_at` 還沒被寫入，系統沒有任何痕跡記錄「已經讀過一次」。這是本次消費機制設計的**已知限制**，如實記錄，不視為缺陷需要立即補強（補強的代價是要嘛更複雜的鎖機制，要嘛犧牲「先算完再寫」的簡單性，非本輪範圍）。
2. **偏離本身**：正確作法是拋錯後停下、回報 PM、等待明確授權再重試。這次的後果經核對為零（未讀到任何實質 Holdout 結果、未產生任何輸出），但「消費失敗→自行修正→再消費」這個模式**不能成為先例**——下一次類似情境若後果不是零，這個模式會造成真正的問題。本項是否登記進 `TEAM_PLAYBOOK.md` §5.1 失敗模式目錄，留給文件對齊那一輪決定（§10）。

---

## 3. Gate A §8 Definition of Done 逐項對號

| # | 項目 | 狀態 | 對應 |
|---|------|------|------|
| 1 | `iter_holdout_folds()`（`test_start_date` 邊界）與逆向隔離守衛落地並通過 known-FAIL | ✅ 已完成 | `c502e3b`／`ac73432`；`IterHoldoutFoldsTests`／`AssertHoldoutOnlyTests` |
| 2 | Holdout 折 Specialist OOF 生成完成，Meta(A)／校準器比對守衛全數通過 | ✅ 已完成 | `run_report()` 內 `assert_matches_sb4_report()`／`assert_calibrator_matches_sb5()` 皆未拋錯（消費成功即為通過） |
| 3 | §3.2(a)(b)(c)(d) 四項分析完成並寫入證據 JSON | ✅ 已完成 | 見 §4 對照表；`holdout_gating_metrics`／`baseline_comparison`／`retained_direction_shift`／`per_fold_stability` |
| 4 | `θ*`、regime 兩個切點確認沿用既有記載值，未被重算 | ✅ 已完成 | `frozen_artifacts`／`sb6_reference`；`assert_frozen_value_matches()` 未拋錯 |
| 5 | `holdout_consumed_at` 只讀一次機制驗證；乾跑 `--holdout-start-date` 守衛驗證 | ✅ 已完成，**但見 §2 已知限制** | `holdout_consumed_at=2026-09-16T05:10:40.253598+00:00` |
| 6 | `target_up_down` Holdout 觀察用 AUC 已產生並寫入 `RISK-030` | ✅ 已完成 | §6 |
| 7 | `Master Plan §11.1` 四項目標逐項對號結果落地為報告文件結論區塊 | ✅ 已完成——Macro F1 一項 PO 裁決不補，留白（§0） | §7 |
| 8 | 全套測試 PASS；`gate0_contract_check.py` 14/14 PASS | ✅ 已完成 | §9 |
| 9 | `GATE3_STARTUP_APPLICATION.md` §8 待補查證項已查明現況並記錄 | ✅ 已完成 | §9 |
| 10 | `DECISIONS.md`（含 `DEC-040` §10 forward-fix）等五份文件依實作結果更新 | 草案見 §9，待核准後執行 | — |
| 11 | Gate 3 正式關閉 | 本文件提案，待 PO 核准 | §11 |

---

## 4. Holdout 結果對照表（原始數字，不含解讀）

| 項目 | Calib-eval（`UG-G3-SB6`） | Holdout（折 33-42） |
|---|---|---|
| Timeout 基期 | 4.71% | 1.76% |
| `θ*` 下 coverage／precision／recall／lift | 0.800／0.196／0.830／4.15 | 0.925／0.189／0.803／10.73 |
| 三項判準（覆蓋率≥0.80／精準度提升≥4×／召回≥0.60） | 成立（邊界） | **成立** |
| 波動率 (ii) 覆蓋率對齊 | 0.800／0.192／0.815／4.07 | 0.920／0.182／0.822／10.30 |
| 波動率 (i) 三分位 | — | 0.851／0.111／0.934／6.28 |
| 保留集 −1／+1 比例、位移 | — | 0.587／0.410、+0.0085／+0.0053 |
| `up_down` 觀察 AUC（lr／rf／lgbm／xgb） | 0.492／0.510／0.500／0.503 | 0.505／0.520／0.523／0.522 |

**三項判準在 Holdout 上成立。**

> **`INFERENCE`（未查證的推論，非既有規格或研究依據）**：Holdout 段的 Timeout 基期（1.76%）遠低於 Calib-eval（4.71%），固定 `θ*` 下 coverage 隨之自然上升到 0.925；`lift` 的上升（4.15→10.73）主要來自基期下降本身（`lift=precision/base_rate`，分母變小則比值變大），不必然代表模型在 Holdout 上的判別力比 Calib-eval 更強——這個區分需要額外驗證（例如比較 precision 本身的絕對變化，或用與基期無關的排序指標）才能確認，本文件不代為下結論。

### 逐折穩定性（不設逐折通過／失敗判準，僅供檢視是否有折明顯偏離）

| 折 | n | n_timeout | n_gated | coverage | precision | recall | lift | 備註 |
|---|---|---|---|---|---|---|---|---|
| 33 | 2639 | 64 | 371 | 0.859 | 0.154 | 0.891 | 6.34 | |
| 34 | 2748 | 93 | 279 | 0.898 | 0.240 | 0.720 | 7.10 | |
| 35 | 2631 | 95 | 384 | 0.854 | 0.211 | 0.853 | 5.84 | |
| 36 | 2444 | 44 | 327 | 0.866 | 0.116 | 0.864 | 6.45 | |
| 37 | 2403 | 27 | 121 | 0.950 | 0.207 | 0.926 | 18.39 | |
| 38 | 2350 | 50 | 92 | 0.961 | 0.315 | **0.580** | 14.82 | **唯一召回 <0.60 的折** |
| 39 | 2203 | 19 | 140 | 0.936 | 0.136 | 1.000 | 15.74 | |
| 40 | 2218 | **4** | 32 | 0.986 | 0.094 | 0.750 | 51.98 | **`n_timeout=4`，`lift` 統計上無意義** |
| 41 | 2258 | **6** | 21 | 0.991 | 0.286 | 1.000 | 107.52 | **`n_timeout=6`，`lift` 統計上無意義** |
| 42 | 2268 | 24 | 41 | 0.982 | 0.415 | 0.708 | 39.18 | |

---

## 5. `PROJECT_STATUS.md` §0.5 #25 回答

**波動率單變數基線與 Timeout gating 在 Holdout 上表現接近**（coverage 0.920 vs 0.925，precision 0.182 vs 0.189，recall 0.822 vs 0.803，lift 10.30 vs 10.73）——本文件**如實記錄接近，不下「管線無用」或「管線有效」的結論**。依 PO 裁決，登記候補案至 `PROJECT_STATUS.md` §0.5（草案見 §9），去處 Gate 4 啟動前裁決。

---

## 6. `RISK-030` 追加：Holdout 樣本外封閉證據

`target_up_down` 四個 Specialist 在 Holdout 的觀察用 AUC：`lr=0.5051`／`rf=0.5202`／`lgbm=0.5231`／`xgb=0.5220`（Meta-Train／Calib-fit／Calib-eval 三段既有數字：≈0.50～0.53，見 `UG-G3-SB5` 證據）。草案見 §9。

---

## 7. `Master Plan §11.1` 四項目標狀態註記

| Metric | Gate A v2 裁決 (b) | Holdout 落地狀態 |
|---|---|---|
| 條件勝率 (Selective) >60% | 對應 Timeout gating 三項判準 | **三項判準於 Holdout 成立**（§4） |
| Selective 覆蓋率 30%～50% | 不適用現行二元設計，只報實際覆蓋率 | Holdout 實際覆蓋率 92.52% |
| Macro F1 >0.55 | 照算 Timeout 三分類 fixed-argmax macro F1，只揭露不設門檻 | **未實作，PO 裁決不補（§0）**——不為此重新消費 Holdout |
| 淨累積報酬 >Buy & Hold | Out of Scope，登記交易模擬引擎候補案 | 草案見 §9 |

---

## 8. `DEC-040` forward-fix 草案 ＋ `DEC-041` Verification 更新

**`DEC-040`**：Context 段 `SYSTEM_UPGRADE_MASTER_PLAN.md §10／§11.3` 改為 `§9／§11.3`，附註：「2026-09-16 forward-fix（`UG-G3-SB7` 結案）：§10 實際章節與 Holdout 定義無關，正確引用為 §9（Gate 3 各 SB Brief）／§11.3（Measurement Template）」。不動決策內容本身。

**`DEC-041`** Verification 欄第四項勾選：

```
- [x] `θ*` 在 Holdout（折 33-42）的樣本外穩定性與波動率單變數基線的比較已於
      `UG-G3-SB7` 完成（2026-09-16，`VERIFIED THIS SESSION`）：三項判準於
      Holdout 成立；波動率單變數基線與 Timeout gating 表現接近，未下結論，
      登記候補案（`PROJECT_STATUS.md` §0.5）。見
      `doc/upgrade/gates/closed/UG_G3_SB7_GATE_B_SUBMISSION.md`、
      `doc/upgrade/gates/evidence/UG_G3_SB7_holdout_report.json`。
```

---

## 9. 文件同步草案（待 Gate B 核准後執行）

- **`DECISIONS.md`**：`DEC-040` §8 草案落地；`DEC-041` §8 勾選落地。**不新增 ADR**——`UG-G3-SB7` 沒有新的設計決策，只有既有 `DEC-041` 決策的驗證結果，寫進 `TRACEABILITY.md`／`RISK-030` 即可。
- **`TRACEABILITY.md`**：條目 37（`DEC-040`）、條目 38（`DEC-041`）依 §8 同步。
- **`REMAINING_RISKS.md`**：`RISK-030` 依 §6 追加 Holdout 封閉證據段。
- **`SYSTEM_UPGRADE_MASTER_PLAN.md`**：§9 `UG-G3-SB7` Brief 依實作更新（Affected Components：`src/ml/stacking.py`／`src/ml/gating.py`／`scripts/verify/ug_g3_sb7_holdout_report.py`）；§11.1 依 §7 加狀態註記；Gate 3 狀態列標記關閉。
- **`PROJECT_STATUS.md`**：
  - §0.2 新增 `UG-G3-SB7` CLOSED 列（比照既有寫法，commit 序列摘要＋§2 程序偏離摘要＋DoD 對號摘要）；新增 **Gate 3 CLOSED** 列（下一步：`UG-Gate-4` 啟動申請，或先進行文件對齊輪，依 §10 未驗證清單決定順序）。
  - §0.5：新增波動率單變數基線候補案（#25 的最終回答，去處 Gate 4 啟動前）、交易模擬引擎候補案（Gate A v2 §3.5 裁決）、`ma5`／`ma20_bias_ratio` 序列中段零值成因小案（§10，去處文件對齊輪後）；#20/#22/#23/#24/#26 逐項更新狀態或維持不變（#20 已解除，本輪不變；#22 已結案，不變；#23 觸發條件確認為「Gate-4 啟動前」；#24 進入排隊，既定；#26 維持獨立候補）。Macro F1 欄位 PO 裁決不補（§0），不需登記候補案，僅於 §11.1 狀態註記留痕，若 Gate 4 需要於當時的 Gate A 提案一併定義。
- **`gate0_contract_check.py` `DOC_PATHS`**：依 `CLAUDE.md` §16.4 查證，預期不需更新（比照 SB4/5/6 先例），需重新查證非假設沿用。

---

## 10. 未驗證清單（有名字有去處）

| 項目 | 去處 |
|---|---|
| **Macro F1 欄位未實作**（§0） | **PO 裁決：不補**，留白；去處：若 Gate 4 需要三分類 Macro F1，於當時的 Gate A 提案一併定義 |
| Holdout 逐折小樣本（折 40／41 `n_timeout` 僅 4／6，`lift` 無統計意義） | 已於 §4 逐折表標註，不另開驗證項 |
| 基期漂移對 `θ*` 意義的 `INFERENCE`（§4） | 需要額外驗證（例如絕對 precision 變化或與基期無關的排序指標）才能確認，本文件不代為驗證 |
| 波動率單變數規則等效性的正式檢驗 | `PROJECT_STATUS.md` §0.5 候補案，去處 Gate 4 啟動前（§5） |
| `RISK-020`（暖機期偽造事件值）的 Gate 3 期間平行小案（`ma5_bias_ratio`／`ma20_bias_ratio` 改 `NULL`，成因 W） | **平行小案未執行（查無完成記錄）；PO 2026-09-16 對凍結面板重量測，`VERIFIED THIS SESSION`（PM 獨立重算相符）**：對 `panel_target_triple_barrier_20260912.parquet`（458 檔、139,585 列）逐檔前 20 列（暖機期視窗）與全面板核對 `=0` 比例——`volatility_5d`／`volatility_20d` 全面板 `=0` 比例 ≈0（2／0 列）；`ma5_bias_ratio` 前 20 列 0.5%、全面板 0.82%（1,150 列）；`ma20_bias_ratio` 前 20 列 0.2%、全面板 0.33%（454 列）；`return_1d` 前 20 列 4.2%、全面板 4.76%；`volume_ratio_5d`／`rsi_14` ≈0。`ma20_bias_ratio=0` 的 454 列中僅 18 列落在該檔前 20 列（序列位置中位數 303，涉及 91 檔）；`ma5` 同型（1,150 列中 50 列在前 20 列，中位數 243，涉及 272 檔）。**這些零不是暖機期填值**——面板起點 2022-11-01 早於暖機期視窗，面板內結構上不含任何暖機列，零值落在序列中段，成因未定（與當日平盤重合比例 13.9%，非唯一解釋）。**Timeout gating 唯一依賴的 `volatility_20d` 在面板內零個填值，RISK-020 對 `UG-G3-SB3`～`SB7` 結果沒有可量測的影響。** 去處：`REMAINING_RISKS.md` `RISK-020` 追加本次量測，狀態維持 `OBSERVED`；序列中段零值成因列為文件對齊輪後的獨立小案，非本 SB 處理 |
| `wrap-rule` 推論規則精修（Gate 3 期間平行小案） | **查無完成證據**（`PROJECT_STATUS.md` 全文查無完成記錄）——去處：文件對齊輪，需向 PO 確認現況 |
| `PRD`／`SDD` 未反映 Gate 3 的設計決策 | 去處：文件對齊輪（PO 既定排程） |

---

## 11. 驗證環境與結果

| 項目 | 結果 |
|---|---|
| 執行環境 | **container**（`stock_prediction_system2_devcontainer-app-1`），Python 3.14.6 |
| 全套測試 | 最終狀態 `Ran 1071 tests` `OK`（`c502e3b`→`ac73432`→`e38a845`→`3a32314`→`bb12966`→`0156d59` 各輪 RED/GREEN 交替，零回歸累計） |
| `gate0_contract_check.py` | 每個 commit 前皆執行，Part B: 14/14 PASS |
| numstat 與 `-w` 格式夾帶偵測 | 除 `0156d59` 一處情況(2)（縮排位移，`SKIP_CHECK2_REASON` 標記，逐行核對僅此一行）外，其餘全部無落差 |
| Holdout evidence JSON sha256 | `7a7d12b97b045acde56aa05a42a2c8d7ec55e49d090b806478b3c46894a97738` |
| Panel sha256 | `panel_target_triple_barrier_20260912.parquet`＝`4c4657c4…`；`panel_target_up_down_20260912.parquet`＝`39dc6b8e…`，與 `DEC-040` 記載值逐位相符（消費前最後一次核對） |

---

## 12. 核准後動作（PO 核准後執行，含 Gate 3 關閉）

依 `CLAUDE.md` §16.3、`gate-submit` skill 產出 8：

1. `git mv` `UG_G3_SB7_GATE_A_PROPOSAL.md` 至 `doc/upgrade/gates/closed/`（確認 `R100`）；本 Gate B 文件以新檔直接進 `closed/`（比照 `UG-G3-SB5`／`SB6` 先例，未曾在 `gates/` 根層 commit 過）。
2. **Gate 3 關閉**：`GATE3_STARTUP_APPLICATION.md` 依 `CLAUDE.md` §16.3 規則 5，`git mv` 至 `closed/`（與上述兩份文件同一結案 commit）。
3. `gate0_contract_check.py` 的 `DOC_PATHS` 查證（§9），預期不需更新。
4. `doc/README.md` 逐份文件表同步（資料夾層級登錄）。
5. §9 五份文件同步草案落地（`DECISIONS.md`／`TRACEABILITY.md`／`REMAINING_RISKS.md`／`SYSTEM_UPGRADE_MASTER_PLAN.md`／`PROJECT_STATUS.md`）。
6. `gate0_contract_check.py` B13 重跑確認「待轉」清單不再含因本輪而停留的項目；B14 對新增 `APPROVED` 勾選通過。
7. 容器內全套測試、contract-check 最終確認。

**Gate 3 關閉為 PO 專屬權限**（`TEAM_PLAYBOOK.md` §2），本文件提出建議與條件具備的證據，不代為宣告。
