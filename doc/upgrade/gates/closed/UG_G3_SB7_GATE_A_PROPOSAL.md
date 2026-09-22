# UG-G3-SB7 Gate A 提案：Performance Benchmark（Holdout 最終驗證）

> **狀態**：**v2，提案草稿，尚未 commit**（依 PO 指示：只寫提案，不寫程式、不碰 Holdout）。
> **前置**：`UG-G3-SB6` 已於 2026-09-16 Gate B 核准結案（`db9eaf6`）。`DEC-041` `APPROVED`。
> **本提案階段唯讀**：僅查證現況、規劃設計，未修改任何業務程式碼、未執行任何 Holdout（折 33-42）讀取／訓練／評估。§2.1 的面板 sha256 重新核對屬**既有已凍結產物的唯讀驗證**，不算觸碰 Holdout 本身。
> **v1 複核（PO 2026-09-16）**：結構通過，九項必答皆有回應，四個主動發現皆屬實。六項裁決＋七處訂正落地為本版本：§3.1 執行順序裁定選項 A（先 SB7 後首次每日 ETL）；§3.5 三項目標裁決（覆蓋率不適用／Macro F1 只揭露／交易模擬候補案）；§3.4 `target_up_down` 改為要印（觀察用）；`DEC-040` §10 誤引改為結案時 forward-fix，且 §2.5 的歸因訂正為 `INFERENCE`（未如 `DEC-041` 般查證過 PO 原始訊息）；`RISK-005` 改綁首次每日 ETL 試跑（§0.5 #20），移出本 SB；`evaluator.py` 確認移交 Gate-4。七處訂正：`iter_holdout_folds()` 邊界改用 `test_start_date`（防跨界折雙重排除卻無人揭露）；補尾端 1,650 列缺口的明文排除；波動率基線改雙變體（三分位＋覆蓋率對齊版，後者切點已在本版本算出並凍結）；移除 `--force-reconsume`（無繞過旗標，重跑走人工流程）；乾跑設計現在就定案（`holdout_start_date` 參數化，乾跑代入 Calib-eval 邊界跑同一段程式碼）；逐折穩定性表加保護欄；凍結清單補三項。

---

## 0. 摘要

`UG-G3-SB7` 是 Gate 3 最後一個 SB，也是 `DEC-040` 所定義 Holdout（折 33-42，`HOLDOUT_START_DATE=2025-10-23`）的**唯一消費者**。本 SB 要驗證 `UG-G3-SB4`～`SB6` 建立的整條管線——Specialist OOF → Meta(A)-LR 重堆疊 → Platt 校準 → `θ*=0.06907452098250194` 的 Timeout gating——在從未被讀取、訓練、評估、選擇過的資料上是否仍然成立，並把結果與 `UG-G3-SB6` 新登記的波動率單變數基線（`PROJECT_STATUS.md` §0.5 #25）並列比較。

`Master Plan §11.1` 原始四項量化目標訂於 Gate 3 啟動當時，此後歷經 `DEC-041` 把主線從「猜方向」轉為「猜何時該觀望」，四項目標中只有「條件勝率」一項有明確的新對應（Timeout gating 三項判準）；其餘三項（Selective 覆蓋率 30～50%、Macro F1 >0.55、淨累積報酬 >Buy & Hold）v1 曾列選項供裁決，**PO 已於 v1 複核裁決 (b) 定案**：覆蓋率宣告不適用、Macro F1 只揭露不設門檻、淨累積報酬與交易模擬另開候補案（§3.5）。

---

## 1. Requirement Source

| 來源 | 內容 |
|---|---|
| `DECISIONS.md` `DEC-040`（`APPROVED`） | Holdout = 折 33-42；`UG-G3-SB4`～`SB6` 全程不得碰；`UG-G3-SB7` 為唯一消費者，且「該次宣稱不得回頭用於調整 `SB4`～`SB6` 的任何設計決定」 |
| `DECISIONS.md` `DEC-041`（`APPROVED`） | `target_up_down` 停做（`RISK-030`）；Timeout gating 為 SB6 產出，Holdout 檢驗留給本 SB |
| `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §3.3 | Holdout 規格原文：「最後 6-12 個月保留為 Holdout，不參與模型選擇」 |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1／§11.3 | 量化目標表、Measurement Template（含交易成本、基準清單） |
| `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 `UG-G3-SB7` Brief（原表） | Goal／資料期間／禁止／各類基準／評估／Tests（原表的財務／排名基準與淨累積報酬評估項，依 §3.5 裁決結果於本 SB 結案時更新） |
| `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md` | `θ*`、三項判準、regime 三分位切點、`PROJECT_STATUS.md` §0.5 #25（波動率基線必列） |
| `doc/upgrade/gates/closed/UG_G3_SB1_GATE_A_PROPOSAL.md` §3 | `embargo_days=0` 在 `label_horizon=5` 下的重議結論（已解決，見 §2.3） |
| `doc/upgrade/gates/GATE3_STARTUP_APPLICATION.md` §8 裁決 8 | RISK-005（150 檔 ETL 計時）安排，現況見 §2.6 |
| `PROJECT_STATUS.md` §0.5 #22／#23／#24／#25／#26 | 各自觸發條件是否因本 SB 啟動 |

---

## 2. Current State（唯讀查證，`VERIFIED THIS SESSION`）

### 2.1 Holdout 邊界現況與凍結面板重驗

`DEC-040` 定義 Holdout = 折 33-42，測試窗 2025-10-23～2026-08-20，另涵蓋折 42 之後、面板尾端 1,650 列缺口。本次重新計算兩個 target 凍結面板的 sha256，**與 `DEC-040` 記載值逐位相符**：

| 檔案 | sha256 |
|---|---|
| `panel_target_up_down_20260912.parquet` | `39dc6b8e6160add20f39a7265bad04de50c76199fa7ab81b979a7aabeabbd014` |
| `panel_target_triple_barrier_20260912.parquet` | `4c4657c4e7e36b227fef01d2f6f667b8e613b23587db40f2907d024db9b3f729` |

**這證明「真實庫首次每日 ETL 執行」（`DEC-040` Verification 欄登記的 NOT VERIFIED 項）截至本次查證仍未發生**——`PROJECT_STATUS.md` §0.5 #20 附近的延續記錄從 `UG-G3-SB2a` 結案（2026-09-11）一路到 `UG-G3-SB6` 結案（2026-09-16）反覆記載「每日 ETL 第一次執行——時點由 PO 決定」，從未標記完成。凍結面板未變，`DEC-040` 的折邊界與日期**目前仍然有效，不需要依 `DEC-040` 該項 NOT VERIFIED 的去處重新核對**。

**排序風險（新發現，必答項見 §3.1）**：若 PO 在本 SB 執行期間或之前啟動首次每日 ETL，凍結面板會改變，`DEC-040` 的折邊界／日期需要重新核對是否仍成立——**這個核對本身不在本提案範圍內**（`DEC-040` Verification 欄寫的去處就是「待 `UG-G3-SB7` 開工前確認」，但「開工前確認」預設面板不動；若面板真的動了，那已經超出「確認」，是「重新推導」，性質不同）。因此本提案在 §3.1 明訂：**Holdout 消費與每日 ETL 首跑不得同時發生**，兩者的執行順序需要 PO 明確裁決。

### 2.2 `iter_oof_folds()` 結構性排除 Holdout——Holdout 折的 Specialist 從未被 fit/predict

`src/ml/stacking.py::iter_oof_folds()`（第 563 行）docstring 明寫：「Holdout 折的 Specialist 因此**從未被 `fit`／`predict`**——不是『訓練了但不用其輸出』，是訓練迴圈本身的折迭代範圍就不包含這些折」。`UG-G3-SB4` 的 OOF parquet（`oof_target_triple_barrier_20260915_025542.parquet`，`n_folds_processed=33`）**只涵蓋折 0-32**，不存在任何 Holdout 折的 Specialist 機率。**本 SB 必須新產生 Holdout 折的 Specialist OOF**，設計見 §3.3。

### 2.3 待沿用的凍結產物清單（唯讀列舉，`VERIFIED THIS SESSION` 逐項核對存在）

| # | 產物 | 來源 | 標識 |
|---|---|---|---|
| 1 | 凍結面板 ×2 | `UG-G3-SB3` | sha256 見 §2.1（本次重驗相符） |
| 2 | `UG-G3-SB4` OOF parquet（`target_triple_barrier`） | `UG-G3-SB4` | sha256 `b9c1d432f0912a2cf9e2a3b3e544d32a57efb45464fc500646a34a7d6f94466c`（folds 0-32，供 Meta-Train／Calib-fit／Calib-eval 段重建用，本身不需重跑） |
| 3 | Meta(A)-LR／Ridge 訓練設定 | `UG-G3-SB4`／`SB5`／`SB6` 逐字一致 | `StandardScaler`（train-only）+ `LogisticRegression(max_iter=500, random_state=42)` + `RidgeClassifier(random_state=42)`，在 Meta-Train（折 0-26）重建 |
| 4 | 校準器 | `UG-G3-SB5` | `fit_calibrator(method="sigmoid")`，`CALIB_FIT_FOLDS=(27,28,29)`；`UG_G3_SB5_calibration_report_target_triple_barrier.json` |
| 5 | `θ*`、選點規則、三項判準門檻、θ 網格 | `UG-G3-SB6` | `θ*=0.06907452098250194`，`rule="max_recall_tiebreak_precision"`，`coverage≥0.80／lift≥4.0／recall≥0.60`；`doc/upgrade/gates/evidence/UG_G3_SB6_gating_report.json` sha256 `aff85bd5efc85fe688719a43de4c170a01726f479a7600defb28e4c8724e9227` |
| 6 | Regime 三分位切點 | `UG-G3-SB6` | `volatility_20d` 切點 `0.30421394224025783`／`0.48111676232087386`（Calib-eval 上決定，Holdout 上**沿用**，不重算） |
| 7 | Specialist（`lr`／`rf`／`lgbm`／`xgb`）超參數與模型建構邏輯 | `UG-G3-SB3` | `src/ml/baseline_models.py`（模型工廠函式），逐字複用，不修改，供 §3.3 Holdout 折逐折重新 `fit`／`predict` 使用 |
| 8 | Gating 判準常數 | `UG-G3-SB6` | `src/ml/gating.py`：`MIN_COVERAGE=0.80`／`MIN_LIFT=4.0`／`MIN_RECALL=0.60`／`MIN_POSITIVE_FOR_AUC=10` |
| 9 | `θ` 網格（`fine`＋`quantile`） | `UG-G3-SB6` | 取自 `UG_G3_SB6_gating_report.json` 的 `theta_grid` 欄（121＋100 點），**本 SB 不重新產生網格**，僅供對照，`θ*` 本身已是單一定值（第 5 項），不需要重新掃網格 |
| 10（**訂正 3，本版本新算，`VERIFIED THIS SESSION`）** | 波動率基線覆蓋率對齊切點 | 本提案 | 對 Calib-eval（`CALIB_EVAL_FOLDS`）的 `volatility_20d` 取第 20 百分位＝`0.23116970731839864`（`np.percentile(vol_calib_eval, 20)`，`n=8255`，代入後 `gate_pct=0.2000`，與 `θ*` 的 `gate_pct≈0.19999999999999996` 對齊）。Holdout 上**沿用**此切點，不重算。詳見 §3.2(b) |

**Holdout 讀取前，這份清單的每一項都必須已在證據 JSON 記錄其標識**（sha256、commit hash、或直接寫入數值），供讀者不需另外查其他文件就能確認「這次真的是套用凍結產物，不是意外重算」。

**「凍結」在本專案的既有意義**：本 repo 從未序列化保存 sklearn 模型物件（無 `joblib.dump()` 等機制）；`UG-G3-SB5`／`SB6` 的既有作法是**用同一批訓練資料＋同一組超參數＋固定 `random_state` 重新 `fit()`**，並用逐位數字比對守衛（`assert_matches_sb4_report()`／`assert_calibrator_matches_sb5()`）證明重建出的是「同一個」模型／校準器，而非又訓練出一個不同的東西。**本 SB 沿用此既有模式**，不引入模型持久化的新基礎設施——見 §3.3、§3.7。

### 2.4 `embargo_days=0` 重議狀態（已解決，非本 SB 待辦）

`GATE3_STARTUP_APPLICATION.md` §10 裁決③附帶失效條款：`embargo_days=0` 的核准僅成立於 1 天標籤視野，若改用多日視野（`target_triple_barrier` 為 5 日），該裁決「自動失效、須重議」。`UG-G3-SB1_GATE_A_PROPOSAL.md` §3 已完成此重議：**實測 H=1→H=5 對 fold 數量與崩潰模式沒有任何影響**，`embargo_days=0` 在 H=5 下重新確認有效。`UG-G3-SB4` 實際 OOF 生成（`splitter_config.embargo_days=0, label_horizon=5`）與此結論一致。**本項唯讀查證，非本 SB 待答，僅供 §3.1 凍結清單的背景確認。**

### 2.5 `DEC-040` 既有引用缺陷（新發現，PO 裁決 (d)：SB7 結案時 forward-fix）

`DEC-040` 的 Context 段引用「`SYSTEM_UPGRADE_MASTER_PLAN.md` §10／§11.3」作為 Holdout 規格來源。查證：**§10 實際章節是「UG-Gate-4: XAI, Export & UI Enhancement」，與 Holdout 定義無關**；真正定義 Holdout 的是 `PURGED_WALK_FORWARD_SPEC.md` §3.3（本提案 §1 已正確引用）與 `SYSTEM_UPGRADE_MASTER_PLAN.md` §9（Gate 3 各 SB Brief，`UG-G3-SB7` Brief 的「資料期間」欄明寫「最近 6-12 個月保留為 Holdout」）／§11.3。

**歸因訂正（`INFERENCE`，非查證過的事實）**：v1 曾類比 `DEC-041` 先前的「§10→§11.1」筆誤（該次**已由 PO 明確確認**筆誤源頭是 PO 自己核准訊息裡的原始文字，`fe30ef2` 訂正記錄有據），推論 `DEC-040` 的「§10」也是同一種「PO 原始訊息筆誤被照抄」模式。**這是類比推論，不是查證過的事實**——本提案唯讀階段沒有找到 `DEC-040` 觸發來源（`UG-G3-SB4` Gate A `be64f9b` 核准脈絡）裡 PO 原始文字的逐字紀錄可供核對；唯一找到的相關文字是 PM 自己當時寫的 `be64f9b` commit message（「v1 退回：§4.4 誤把已核准的 Gate 3 Holdout 規格（`PURGED_WALK_FORWARD_SPEC.md` §3.3、`Master Plan` §10/§11.3）當成自由裁量選項」）——這是 PM 對 v1 退回理由的**事後摘要**，不是 PO 原話的逐字引用，無法確認「§10」是 PO 原話還是 PM 摘要時自己複製錯的。**標記 `INFERENCE`，不寫成事實**；若 PO 手上還留有 `UG-G3-SB4` v1 審查時的原始訊息，可查證後改標為事實。

**本提案不修改 `DEC-040`**（已 `APPROVED`）。依 PO 裁決 (d)：**`UG-G3-SB7` 結案 commit 內 forward-fix**——只把 `§10／§11.3` 改為 `§9／§11.3`，加一行帶日期的訂正註記，不動決策內容本身；`TRACEABILITY.md` 若有同一引用一併訂正。比照 `fe30ef2` 先例的處理方式（訂正記錄留痕，不 amend 既有 commit）。

### 2.6 RISK-005（150 檔 ETL 計時）現況：仍為 `HYPOTHESIS`（PO 裁決 (e)：綁首次每日 ETL 試跑，不在本 SB 做）

`GATE3_STARTUP_APPLICATION.md` §8 裁決 8 安排「唯讀計時，排在 `UG-G3-SB2` 收尾」，但查證 `REMAINING_RISKS.md` 現況，`RISK-005` **仍標記 `HYPOTHESIS`**，未見任何 `UG-G3-SB2`／`SB2a` 結案記錄提及已執行計時測試——該項安排似乎未被執行。

**PO 裁決**：不在本 SB 補做。理由——計時測試需要真的跑一次外部擷取（網路 I/O、`RISK-028` TPEX 端間歇性 SSL 憑證失敗風險），不是零風險的唯讀動作，與「消費 Holdout」性質不同，不應混進同一個 SB。**改綁首次每日 ETL 試跑本身**——那次執行本來就是對 150 檔的真實計時，併入 `PROJECT_STATUS.md` §0.5 #20 既有的 binding confirmation 與十項觀察清單一併處理。Gate 3 關閉時（§3.9）如實列為「已知缺口，去處 #20」，不在本 SB DoD 內。

---

## 3. PO 必答項逐一回應

### 3.1 Holdout 消費協議

**只讀一次、只評估不選擇**：本 SB 對 Holdout 資料的唯一合法操作是「用 §2.3 凍結清單的產物，在 Holdout 折上計算既定指標」——不得依 Holdout 上的結果調整 `θ*`、重新訓練任何模型、重新選擇校準方法，或以任何方式把 Holdout 表現回饋進 §2.3 清單裡的任何一項。

**執行順序（PO 裁決 (a)：選項 A 定案）**：**先跑 `UG-G3-SB7`（消費 Holdout），之後才啟動首次每日 ETL。** 首次每日 ETL 本來就需要另一輪 binding confirmation（`PROJECT_STATUS.md` §0.5 #20），順序自然成立，不需要額外協調機制。開工前重驗一次面板 sha256（§2.1 已示範，正式開工時再核對一次）即可，不需要在本 SB 內設計「偵測面板是否變動」的守衛。

**機械化的「只讀一次」保證（不靠自律，無繞過旗標）**：報告腳本首次成功執行且完成 `--write` 時，在證據 JSON 寫入 `holdout_consumed_at`（時間戳）與 `holdout_consumed_guard`（記錄實際讀取的折集合、面板 sha256）。**若證據 JSON 已存在且 `holdout_consumed_at` 已填，腳本第二次 `--write` 執行時一律結構性拒絕，沒有任何旗標可以繞過**（訂正 4：v1 設計的 `--force-reconsume` 已移除——「一個存在的旗標就是會被用的旗標」）。若因程式錯誤（非資料或模型問題）必須重跑：流程是 **PO 明確授權 → 人工把既有 evidence JSON 改名保留（不刪除，例如加 `_superseded_<timestamp>` 後綴）→ 重新執行**，且 Gate B 文件必須記錄兩份 JSON 的差異與重跑理由。**重跑等於 Holdout 已消費、視為新一輪 Gate A**（因為凍結清單的任一項若因此改變，就不再是「本次裁決」）——這句沿用不變。

**凍結清單**：見 §2.3，本節不重複列出。

### 3.2 Holdout 上要回答的問題

全部在折 33-42（`assert_holdout_isolation()` 逆向使用：本 SB 的紅測需確認新產生的 Specialist OOF **全部**落在此範圍內，任何漏出到折 0-32 或漏入 Holdout 之後的列即拋錯）。

**(a) 三項判準在 Holdout 是否仍成立**：對 Holdout 折套用 §2.3 第 3-5 項凍結產物，計算 `coverage`／`precision`／`recall`／`lift`，與 Calib-eval 段數字（覆蓋率 80.00%、精準度提升 4.15×、召回 83.03%）並列對照表。

**尾端缺口明文排除（訂正 2）**：折 42 之後、凍結面板尾端的 1,650 列（`DEC-040` Decision 1 已記載此缺口存在）**屬 Holdout 範圍但不在任何折內**——`iter_holdout_folds()`／`iter_oof_folds()` 皆不會產出這批列（兩者都以「折」為單位迭代，這批列從未被任何折的 train／test 窗涵蓋）。**本 SB 不評估這批列**，於 §3.2 結果與 Data Contract（§3.7）明文排除，不得誤植為「已涵蓋全部 Holdout」。

**(b) 與兩個基線並列比較（訂正 3：波動率基線改為雙變體，覆蓋率對齊版切點本輪已算出並凍結）**：

| 對照組 | 定義 | 切點來源 |
|---|---|---|
| 隨機 gating | 解析值 | 同 `UG-G3-SB6` §3.5，等於 Holdout 段 Timeout 基期，不需模擬 |
| 波動率基線 (i)：三分位規則 | `volatility_20d ≤ 0.30421394224025783` → 觀望 | `UG-G3-SB6` regime 診斷既有切點（§2.3 第 6 項），並列揭露用，覆蓋率約 33%，與 `θ*` 的 20% 不同 |
| 波動率基線 (ii)：覆蓋率對齊版（**主要對照**） | `volatility_20d ≤ 0.23116970731839864` → 觀望 | 本提案 §2.3 第 10 項，Calib-eval 上第 20 百分位，`gate_pct=0.2000`，與 `θ*` 覆蓋率對齊，公平比較 |
| Timeout gating（本 SB 主角） | §3.2(a) | — |

四者（隨機、(i)、(ii)、Timeout gating）並列於同一張表，四個指標逐一對照；**(ii) 為主要對照組**（覆蓋率相同才能公平比較 precision／recall／lift），(i) 僅並列揭露。不下結論式包裝——若波動率基線表現接近，明寫接近；若明顯較差，明寫較差。兩個波動率切點**皆沿用 Calib-eval 上算出的值，Holdout 上不重新計算**（known-FAIL 見 §5）。

**(c) 保留集方向比例位移**：沿用 `UG-G3-SB6` §3.3 第四項指標定義（`retained` 集合中 `-1`／`1` 的比例與 Holdout 全段基期相減），只揭露、不下結論（依 `DEC-041` Decision 2：`±1` 方向類機率只揭露不設門檻）。

**(d) 逐折（33-42）穩定性（訂正 6：加保護欄）**：10 個 Holdout 折各自的 `coverage`／`precision`／`recall`／`lift` 附表，**每折另附 `n`（列數）、`n_timeout`（真實 Timeout 列數）、`n_gated`（被 gate 列數）**——Holdout 單折 Timeout 正例可能只有幾十筆、被 gate 的列更少，`precision` 數值在小樣本下會很吵。**表格需明寫：逐折不設通過／失敗判準，只用來檢視是否有折明顯偏離其餘折（可能提示 regime shift 或資料品質問題），不對任何單折的數字做「通過／不通過」的宣稱。**

### 3.3 Specialist 在 Holdout 的 OOF 形式

**新增 `iter_holdout_folds(splitter, panel, holdout_start_date)`**（`src/ml/stacking.py`，與既有 `iter_oof_folds()` 互補，**訂正 1：邊界改用 `test_start_date`**）：只 yield `test_start_date >= holdout_start_date` 的折。

**v1 缺陷（審查方複核發現）**：v1 原設計用 `test_end_date >= holdout_start_date`。`iter_oof_folds()` 用 `test_end_date < boundary` 排除，其排除條件是 `test_end_date >= boundary`——這個條件同時涵蓋「整折在邊界之後」**與**「跨界折」（`test_start < boundary ≤ test_end`）。若 `iter_holdout_folds()` 也用 `test_end_date >= boundary` 當作**納入**條件，會把跨界折**整個**納入 Holdout 評估，讓邊界之前（本應屬 Meta-Eval／Calib-eval 段）的列混進 Holdout 結果——這是真正的資料污染，不是理論疑慮。

現行面板折 32 結束於 2025-10-22、折 33 起於 2025-10-23，剛好沒有跨界折，所以 v1「並集覆蓋全部、交集為空」在**現行資料**上成立——但那是資料湊巧，不是函式性質，不能當作正確性的證明。

**訂正後**：`iter_holdout_folds()` 用 `test_start_date >= boundary` 納入；跨界折（`test_start < boundary ≤ test_end`）在 `iter_oof_folds()`（`test_end_date >= boundary` 排除）與 `iter_holdout_folds()`（`test_start_date < boundary` 排除）**兩者都不會 yield**——兩個迭代器對跨界折達成一致排除，不是誤入其中一邊。**報告腳本必須揭露是否存在被兩者同時排除的折**（記錄折號於證據 JSON 的一個欄位，例如 `folds_excluded_by_both_iterators`），不得靜默——即使現行資料上這個清單預期為空，也要讓讀者能不透過原始碼就確認這件事。

對這些折，**Specialist（`lr`／`rf`／`lgbm`／`xgb`）依 `UG-G3-SB4` 既有流程逐折重新 `fit`／`predict`**——每折的訓練窗仍是該折之前 60 天（`train_window_size=60`，`mode=rolling`），這是 walk-forward 內、該折測試窗**之前**的資料，不觸碰任何未來資訊，合法。

**Meta(A)-LR／Ridge、校準器絕對不重訓**：用 §2.3 第 3-4 項凍結的訓練資料範圍（Meta-Train 折 0-26、Calib-fit 折 27-29）與超參數**重建**（非讀取序列化檔案，理由見 §2.3），把新產生的 Holdout 折 Specialist OOF 機率餵給重建出的 Meta(A) 模型取得 `decision_function()`，再套用重建出的校準器取得校準後機率。

**比對守衛（比照既有先例）**：重建的 Meta(A)-LR／Ridge 品質數字須與 `UG-G3-SB4`／`UG-G3-SB5` 證據 JSON 逐位相符（`assert_matches_sb4_report()`／`assert_calibrator_matches_sb5()` 既有函式直接複用），證明「確實是同一個模型／校準器在跑，不是又訓練出一個不同的東西」——這一步不是新設計，是既有模式在新資料段上的自然延伸。

**Known-FAIL 設計**：構造 mutant 讓新的 Holdout 折生成邏輯意外呼叫 `iter_oof_folds()`（而非 `iter_holdout_folds()`），斷言 `assert_holdout_isolation()` 或本 SB 新增的逆向隔離檢查必須攔截——證明兩個迭代器的邊界互斥是真的被守住，不是恰好没測到。

### 3.4 Benchmark 對 `target_up_down` 的處置（PO 裁決 (c)：要印，觀察用）

**Holdout 上不做 `target_up_down` 的任何績效宣稱**（不進 DoD、不設門檻），依 `RISK-030`／`DEC-041`；但**要產生並印出樣本外封閉證據**：

1. 額外生成 `target_up_down` 的 Holdout 折 Specialist OOF（同 §3.3 機制，`iter_holdout_folds()` 對 `target_up_down` 面板重跑一次；`target_up_down` 的 `label_horizon=1`，與 `target_triple_barrier` 的 5 不同，折邊界日期是否相同需在實作階段對面板重新核對，不假設沿用）。
2. 報告四個 Specialist 與 Meta(A)-LR／Ridge 在 Holdout 折的 AUC（比照 `RISK-030` 既有的三段 AUC 表格式：Meta-Train／Calib-fit／Calib-eval／**Holdout（新增第四段）**）。
3. 欄位明確標示「**觀察用，非績效宣稱**」，不進 `Master Plan §11.1` 的任何目標對號。
4. **結果寫入 `RISK-030` 作為樣本外封閉證據**：若 Holdout AUC 仍 `≈0.50`（與 Meta-Train／Calib-fit／Calib-eval 一致），`RISK-030`「`target_up_down` 現行特徵集下無排序訊號」的結論視為**在樣本外也成立，定案**；若 Holdout AUC 明顯偏離 `0.50`（無論升或降），**如實記錄，回報 PO，本 SB 不自行推論原因**（可能是 Holdout 段特性使然，也可能是先前三段的樣本內結論本身有問題，需要 PO 判斷）。

`Master Plan §11.1` 的量化目標表逐項對號時（§3.5），每個指標欄位仍一律標註「`target_up_down`：不評估，理由 `RISK-030`」，不因為有觀察用 AUC 就誤植為「已評估」。

### 3.5 `Master Plan §11.1` 目標表逐項對號（PO 裁決 (b)：四項全部定案）

| Metric | 原始目標 | 裁決 |
|---|---|---|
| 條件勝率 (Selective) >60% | `target_up_down` 為主線的方向性勝率 | **已由 `DEC-041` 轉向**：Timeout gating 三項判準（覆蓋率≥80%／精準度提升≥4×／召回≥60%）於 Calib-eval 已達成，Holdout 檢驗見 §3.2(a)。無需再裁決 |
| Selective 覆蓋率 30%～50% | 原設計「三段式方向信號」發出訊號的比例，與現行二元 gating 不對應 | **宣告不適用現行二元設計**——只報告「實際達成覆蓋率」（Calib-eval 80%、Holdout 待算），不作為通過／失敗門檻。不重新定義成「觀望比例」再套用 30-50%（那個門檻是為另一種架構設計的，用在這裡沒有依據） |
| Macro F1 >0.55（vs 分類基準） | 方向性三分類的固定門檻硬分類 F1 | **照算 Timeout 三分類（`-1/0/1`）的 fixed-argmax macro F1**（`UG-G3-SB5` 既有算法沿用），**只揭露不設 0.55 門檻**——Timeout 類稀有本就會拉低 macro F1，且此數字衡量的是「三類都猜對」，不是 gating 任務的成功判準 |
| 淨累積報酬 >Buy & Hold + 交易成本 | 完整交易模擬 | **Out of Scope**——系統目前沒有交易模擬引擎（`src/ml/` 無回測／損益計算模組）。登記「交易模擬引擎」候補案至 `PROJECT_STATUS.md` §0.5（本 SB 結案時新增條目，觸發條件待 PO 於 Gate B 核准時決定排程） |

**排名基準（Equal Weight Top-K／Random Top-K）**：隨淨累積報酬項一併 Out of Scope（系統沒有「排名」概念，Timeout gating 是二元觀望／保留，不是對股票排序）。

**`Master Plan §11.1` 表格處置**：**數字不改**，`UG-G3-SB7` 結案時在每個目標旁**逐項加狀態註記**（比照既有 `DEC-041` 狀態註記的既有寫法），不修改原始目標值本身——保留歷史脈絡，讓讀者能看出「原目標是什麼、現在的對應結論是什麼」兩件事並存。

### 3.6 失敗語意

| 情境 | 處置 |
|---|---|
| 三項判準在 Holdout 不成立 | **不調 `θ`、不重選**，如實記錄差距、回報 PO。依 `DEC-040`「該次宣稱不得回頭用於調整 `SB4`～`SB6` 的任何設計決定」，若要調整，是新一輪 Gate A，且 Holdout 視為已消費（依 §3.1 訂正 4 的人工重跑流程，不是自動旗標） |
| §0.5 #22（SB4a 重訓候補案）是否觸發 | **不觸發**——`PROJECT_STATUS.md` §0.5 #22 追加項已裁定：`RISK-030` 確立後，正確路徑是參照 `RISK-030`／`DEC-041`（是否繼續 TB／Timeout 主線或重開特徵案），不是重訓 Meta-Learner。即使 Holdout 召回偏低，也不代表 Meta-Learner 訓練方式有問題 |
| §0.5 #24（特徵層面方向預測改進案）是否觸發 | **是，既定排程**——觸發條件即「`UG-G3-SB7` 之後」，無論本 SB 結果如何都會進入排隊，非因失敗而觸發 |
| §0.5 #25（波動率單變數基線）比較結果 | 若波動率基線在 Holdout 上表現與 Timeout gating 接近，**如實揭露於 Gate B 報告顯著位置**，可能開一個「簡化為波動率規則」的候補案（是否開案，供 PO 裁決，不預設） |

### 3.7 Data Contract

**輸入**：

| 項目 | 來源 | 校驗 |
|---|---|---|
| 凍結面板 ×2 | `UG-G3-SB3` | sha256（§2.1，開工前再驗一次） |
| `UG-G3-SB4` OOF parquet（`target_triple_barrier`） | `UG-G3-SB4` | sha256 `b9c1d432…4f94466c`（供重建 Meta(A) 訓練資料段用，不重跑生成） |
| `UG-G3-SB6` evidence JSON | `UG-G3-SB6` | sha256 `aff85bd5…9227`（取 `θ*`、regime 切點） |
| Holdout 折的 Specialist OOF | 本 SB 新產生 | 不落地為中繼檔案，現場算（或落地供除錯，但不作為既有守衛的比對基準） |

**產出**（新報告腳本，暫名 `scripts/verify/ug_g3_sb7_holdout_report.py`）：

| 欄位 | 內容 |
|---|---|
| `holdout_folds_processed`／`holdout_row_count`／`holdout_class_distribution` | Holdout 折的基本統計 |
| `holdout_tail_gap_excluded` | 折 42 之後 1,650 列缺口的明文排除記錄（訂正 2） |
| `folds_excluded_by_both_iterators` | 訂正 1：`iter_oof_folds()`／`iter_holdout_folds()` 皆未 yield 的折號清單（現行資料預期為空，但必須記錄） |
| `holdout_gating_metrics` | §3.2(a)：coverage／precision／recall／lift，與 Calib-eval 數字並列 |
| `baseline_comparison` | §3.2(b)：Timeout gating／隨機基線／波動率基線 (i) 三分位／波動率基線 (ii) 覆蓋率對齊版，四者並列，(ii) 標記為主要對照 |
| `retained_direction_shift` | §3.2(c) |
| `per_fold_stability` | §3.2(d)：10 折逐折表，含 `n`／`n_timeout`／`n_gated` |
| `up_down_observational_auc` | §3.4：四個 Specialist＋Meta(A)-LR／Ridge 的 Holdout AUC，標記「觀察用，非績效宣稱」 |
| `holdout_consumed_at`／`holdout_consumed_guard` | §3.1：只讀一次的機械記錄 |
| `script_commit`／`script_dirty`／`script_untracked_paths` | 比照既有慣例 |

**輸出檔案位置**：`doc/upgrade/gates/evidence/UG_G3_SB7_holdout_report.json`，比照既有命名慣例。

### 3.8 `evaluator.py` 未擴充（§0.5 #23）在本 SB 是否處理（PO 裁決 (f)：接受建議，不在本 SB 處理）

`DEC-041` 裁決 (d) 已將 `predictor.py`／`evaluator.py` 列為 `UG-G3-SB6` Out of Scope，留給「`UG-G3-SB7`／Gate-4」決定「是否接入、如何接」。「決定如何接入」與「驗證 Holdout 上是否成立」是兩件不同性質的工作——後者是本 SB 的任務，前者是把系統接成可實際使用產品的整合工作，範圍更大、需要另外的 Gate A 必答項（API 介面、呼叫時機、失敗時的降級行為）。**`evaluator.py` 擴充移交 Gate-4 或獨立候補案，不併入本 SB**；`PROJECT_STATUS.md` §0.5 #23 的觸發條件於本 SB 結案時更新為「Gate-4 啟動前」。

### 3.9 Gate 3 關閉條件

`UG-G3-SB7` Gate B 通過後：

1. `GATE3_STARTUP_APPLICATION.md` 依 `CLAUDE.md` §16.3 規則 5，`git mv` 至 `closed/`（與本 SB 自己的 Gate A／B 文件一起，同一結案 commit）。
2. **Gate 3 DoD 逐項檢視**（非全部解決才能關閉，是逐項寫明「關閉時的狀態」）：

| 項目 | 關閉時狀態 |
|---|---|
| `UG-G3-SB1`～`SB7`（含 `SB2a`） | 全部 `CLOSED` |
| `GATE3_STARTUP_APPLICATION.md` §8 九項裁決 | 逐項對號：#2 rolling 已定案並實測；#3 embargo=0 已於 SB1 重議確認；#4 條件未觸發；#5 RISK-020（暖機期）——**需查證是否已於 SB2 重量測完成**（§8 待補查證）；#6 宇宙接線已落地；#7 D3 實驗已於 SB3 執行；#8 RISK-005——**已改綁首次每日 ETL 試跑（§2.6，PO 裁決 (e)），不在本 SB 補做，Gate 3 關閉時如實列為「已知缺口，去處 #20」**；#9 wrap-rule 平行小案狀態需查證 |
| `DEC-040` 唯一消費者條款 | 本 SB 履行完畢 |
| `PROJECT_STATUS.md` §0.5 未結義務 | #22 已結案；#23 移交 Gate-4（§3.8）；#24 進入排隊（既定）；#25 本 SB 直接回答；#26（`.gitattributes` 候補）維持獨立候補，Gate 3 關閉不需先解決；新增條目：交易模擬引擎候補案（§3.5）、`RISK-005` 綁 #20（§2.6） |
| `DEC-040` §2.5 的既有引用缺陷 | 本 SB 結案 commit 內 forward-fix（§2.5，PO 裁決 (d)），不阻擋 Gate 3 關閉 |

**§8 待補查證項（本提案唯讀階段尚未逐字核對，列為開工前最後一項查證，非重新裁決）**：RISK-020 重量測結果、wrap-rule 平行小案現況——若這兩項在既有 `PROJECT_STATUS.md` 記錄中找不到完成證據，需在本 SB Gate B 前補一次唯讀查證或請 PO 說明現況。

---

## 4. In Scope

1. 新增 `iter_holdout_folds()`（`src/ml/stacking.py`，`test_start_date` 邊界）與對應的逆向隔離守衛，含跨界折雙重排除記錄。
2. Holdout 折的 Specialist OOF 生成（比照 `UG-G3-SB4` 既有流程，僅折範圍不同），`target_triple_barrier` 與 `target_up_down` 皆生成（後者僅供 §3.4 觀察用 AUC）。
3. 重建 Meta(A)-LR／Ridge、校準器（凍結訓練資料範圍與超參數，比對守衛複用既有函式）。
4. 新報告腳本 `scripts/verify/ug_g3_sb7_holdout_report.py`：§3.2(a)(b)(c)(d) 四項分析、只讀一次機械保證、`--holdout-start-date` 參數化（支援乾跑）。
5. Timeout gating／隨機基線／波動率基線（三分位＋覆蓋率對齊版兩個變體）於 Holdout 上的並列比較。
6. `target_up_down` 觀察用 Holdout AUC（§3.4），寫入 `RISK-030`，不進 DoD 判準。
7. `Master Plan §11.1` 四項量化目標逐項對號（§3.5，已裁決），落地為報告文件的結論區塊。

## Out of Scope

1. `target_up_down` 的任何**績效宣稱**（`RISK-030`，§3.4）——觀察用 AUC 已改為 In Scope（見上），但仍不進 DoD、不設門檻，不得與績效宣稱混淆。
2. 交易模擬引擎（淨累積報酬、排名基準）——`Out of Scope`，登記候補案至 `PROJECT_STATUS.md` §0.5（§3.5 裁決）。
3. `evaluator.py`／`predictor.py` 的 gating 決策整合（§3.8），移交 Gate-4 或獨立候補案。
4. 重訓任何既有模型（Specialist 訓練設定、Meta(A)、校準器皆凍結沿用，僅 Specialist 對 Holdout 折的預測是「新產生」而非「重訓」）。
5. `θ*`、regime 兩個切點（三分位、覆蓋率對齊版）、選點規則的重新計算（一律沿用既定數值）。
6. 每日 ETL 首次執行本身（§3.1 執行順序已裁決為 SB7 之後，不在本 SB 執行範圍）。
7. `RISK-005`（150 檔 ETL 計時）——已改綁首次每日 ETL 試跑（§2.6，PO 裁決 (e)），不在本 SB 補做。

---

## 5. Failure Semantics & Tests（規劃，紅測階段依此擴充）

| 場景 | 預期行為 | Known-FAIL 設計 |
|---|---|---|
| Holdout 折的 Specialist OOF 意外經 `iter_oof_folds()`（非 `iter_holdout_folds()`）產生 | 隔離守衛攔截 | mutant：讓生成邏輯誤用 `iter_oof_folds()`，斷言逆向隔離檢查 FAIL |
| **（訂正 1）跨界折被 `iter_holdout_folds()` 誤納入** | `test_start_date >= boundary` 才納入，跨界折（`test_start < boundary ≤ test_end`）不得被任一迭代器 yield | 合成一個跨界折（人工構造 `test_start` 與 `test_end` 橫跨 `holdout_start_date`），斷言 `iter_oof_folds()`／`iter_holdout_folds()` 兩者都不 yield 它；另一條正控制：確認 `folds_excluded_by_both_iterators` 欄位正確記錄該折號 |
| 重建的 Meta(A)／校準器品質數字與 `UG-G3-SB4`／`SB5` 證據 JSON 不符 | 拋例外，比照 `assert_matches_sb4_report()`／`assert_calibrator_matches_sb5()` 既有精神 | mutant：扭曲一個係數，斷言 guard 攔截 |
| `θ*`／regime 切點被意外重新計算而非沿用 `UG-G3-SB6` 證據 JSON | 拋例外或數值比對 FAIL | mutant：讓報告腳本重算切點而非讀取既有值，斷言與 `UG_G3_SB6_gating_report.json` 記載值不符時 FAIL |
| **（訂正 4）第二次 `--write` 執行（`holdout_consumed_at` 已存在）** | **一律拒絕，無任何繞過旗標** | 正控制：首次執行成功寫入；known-FAIL：第二次執行（無論帶什麼參數），斷言 REFUSED，且確認不存在任何能讓它通過的旗標 |
| 波動率基線 (i)／(ii) 的切點被意外在 Holdout 上重新計算 | 應沿用 Calib-eval 切點（`0.30421394224025783`／`0.23116970731839864`），不得重算 | mutant：讓基線邏輯改用 Holdout 資料自己的分位數，斷言與凍結值不符時 FAIL（兩個切點各一個 mutant） |
| Holdout 折資料意外漏出到 Meta-Train／Calib-fit／Calib-eval 段的任何計算 | `assert_holdout_isolation()` 既有守衛攔截 | 沿用既有 known-FAIL 案例，於新程式碼路徑上重跑一次確認仍然攔截 |
| **（訂正 5）`--write` 時 `holdout_start_date` 不等於 `HOLDOUT_START_DATE` 常數** | 拒絕執行，防止「乾跑參數不小心被用在正式寫入」 | 正控制：`--write` + 預設 `HOLDOUT_START_DATE` 成功；known-FAIL：`--write` + 自訂 `holdout_start_date`（例如乾跑用的 `META_EVAL_START_DATE`），斷言 REFUSED |

---

## 6. Risks & Trade-offs

- **Holdout 折的 Specialist OOF 是「新產生」而非既有資料**——這是唯一允許在本 SB 內「訓練」的部分（Specialist 對 Holdout 折的 rolling 訓練），需要格外小心確保訓練窗確實只用該折之前的資料，不是「重訓整個 Specialist」。§3.3 的比對守衛只驗證 Meta(A)／校準器沒有變，**不能**驗證 Specialist 訓練本身沒有洩漏未來資訊——這件事需要靠 `iter_holdout_folds()` 的邊界正確性（§5 known-FAIL）與既有 `WalkForwardSplitter` 的 Purge 機制共同保證，不是新發明的驗證方式。
- **`Master Plan §11.1` 三項指標的適用性問題（§3.5）已由 PO 裁決定案**（覆蓋率不適用／Macro F1 只揭露／交易模擬 Out of Scope），不再是本 SB 的範圍不確定性來源；殘餘風險是「交易模擬引擎」候補案的時程與範圍尚未規劃，留待該候補案自己的 Gate A 處理。
- **Holdout 消費是不可逆事件**——移除 `--force-reconsume` 後（§3.1 訂正 4），重跑必須經過人工改名既有 JSON＋PO 明確授權，沒有任何自動旗標可以繞過；本提案要求這類重跑應附上「為什麼是程式錯誤、不是在挑 Holdout 結果」的說明，避免「重跑到滿意為止」的疑慮。
- **RISK-005（150 檔 ETL 計時）與 §8 待補查證項**（§2.6、§3.9）代表 Gate 3 啟動時排定的部分安排可能未被執行——這不是本 SB 造成的缺口，但若不在本 SB 或 Gate 3 關閉前處理，會變成下一個「揭露了卻沒有執行」的案例（比照 `CLAUDE.md` §16.3 修訂記錄 GOV-09 的教訓）。

---

## 7. E2E Verification Plan

1. 開工前查證（唯讀）：重驗面板 sha256（§2.1，若已在本提案完成可略過重跑）；確認首次每日 ETL 仍未執行；補查 §3.9 待補查證項（RISK-020 重量測、wrap-rule 現況）。
2. 紅測（依 §5 場景）→ 送審 → 核准後建紅測 commit。
3. 實作（GREEN）：`iter_holdout_folds()` + 報告腳本，§3.2 四項分析。
4. 全套測試 + `gate0_contract_check.py`，比照既有先例。
5. **乾跑，不消費 Holdout（訂正 5，設計現在就定案）**：報告腳本的 Holdout 邊界以 `--holdout-start-date` 參數傳入，**預設值為 `HOLDOUT_START_DATE` 常數**。乾跑時明確傳入一個不同的邊界日期——例如 `META_EVAL_START_DATE`（`2025-05-02`，折 27 起點）或 `CALIB_EVAL_FOLDS` 的起始日——讓 `iter_holdout_folds()` 把折 27-32（或僅 Calib-eval 的折 30-32）當成「偽 Holdout」跑過同一段程式碼（Specialist 逐折重新 `fit`／`predict`、Meta(A)／校準器重建、四項分析計算），**這些折的真實結果已知**（`UG-G3-SB4`～`SB6` 已經算過），可以直接核對乾跑輸出是否與既有結果一致，作為管線正確性的交叉驗證。乾跑輸出到 scratchpad，**永不 `--write`**；`--write` 時若 `holdout_start_date` 不等於 `HOLDOUT_START_DATE` 常數，腳本結構性拒絕（§5 known-FAIL）——這樣「乾跑」與「正式消費」共用同一段程式碼路徑，又保證乾跑階段碰不到真正的折 33-42。
6. **正式 Holdout 消費（唯一一次）**：全量執行，寫入 `holdout_consumed_at`。
7. Gate B 送審，含 `Master Plan §11.1` 四項目標的最終對號結果、`GATE3_STARTUP_APPLICATION.md` §8 待補查證項的補查結果。
8. Gate 3 關閉條件核對（§3.9）。

---

## 8. Definition of Done

1. `iter_holdout_folds()`（`test_start_date` 邊界）與逆向隔離守衛落地並通過 known-FAIL（§5，含跨界折雙重排除測試）。
2. Holdout 折 Specialist OOF 生成完成，Meta(A)／校準器比對守衛全數通過（證明凍結產物未被意外改動）。
3. §3.2(a)(b)(c)(d) 四項分析完成並寫入證據 JSON：三項判準 Holdout 對照表、四方基線比較表（隨機／波動率(i)／波動率(ii)／Timeout gating，(ii) 為主要對照）、方向位移揭露、逐折穩定性表（附 `n`／`n_timeout`／`n_gated`，不設逐折通過門檻）。
4. `θ*`、regime 兩個切點（三分位、覆蓋率對齊版）確認沿用既有記載值，未被重算。
5. `holdout_consumed_at` 只讀一次機制驗證：正控制（首次成功）與 known-FAIL（第二次一律拒絕，無旗標可繞過）皆已執行並附原始輸出；乾跑 `--holdout-start-date` 守衛驗證（§5 訂正 5）。
6. `target_up_down` Holdout 觀察用 AUC 已產生並寫入 `RISK-030`（§3.4）。
7. `Master Plan §11.1` 四項目標逐項對號結果（§3.5 已裁決）落地為報告文件結論區塊，原始表格數字不變、加狀態註記。
8. 全套測試 PASS；`gate0_contract_check.py` 14/14 PASS。
9. `GATE3_STARTUP_APPLICATION.md` §8 待補查證項（RISK-020、wrap-rule）已查明現況並記錄；`RISK-005` 已改綁 §0.5 #20，不留在本 SB 待辦。
10. `DECISIONS.md`（含 `DEC-040` §10 forward-fix）／`TRACEABILITY.md`／`REMAINING_RISKS.md`／`SYSTEM_UPGRADE_MASTER_PLAN.md` §9／§11.1 依實作結果更新；`PROJECT_STATUS.md` §0.2 新增 `UG-G3-SB7` CLOSED 列、§0.5 #22～#26 逐項更新狀態＋新增交易模擬引擎候補案條目。
11. `GATE3_STARTUP_APPLICATION.md` 依 §16.3 規則 5 移入 `closed/`，Gate 3 正式關閉（需 PO 額外裁決，本 SB 只是條件具備，不代為宣告）。

---

## 9. Documentation Sync

Gate B 結案時比照 `UG-G3-SB5`／`SB6` 先例：`git mv` 本提案與 Gate B 送審文件至 `doc/upgrade/gates/closed/`；`GATE3_STARTUP_APPLICATION.md` 一併移入（Gate 3 本身關閉時，依 §16.3 規則 5，非 SB 提案的生命週期，需另外確認 PO 同意 Gate 3 正式關閉才移動）；`DECISIONS.md`／`TRACEABILITY.md`／`REMAINING_RISKS.md`／`SYSTEM_UPGRADE_MASTER_PLAN.md`／`PROJECT_STATUS.md` 五份文件同步；`gate0_contract_check.py` 的 `DOC_PATHS` 依 `CLAUDE.md` §16.4 查證（依 SB4／SB5／SB6 先例，預期不需要，需重新查證非假設沿用）。
