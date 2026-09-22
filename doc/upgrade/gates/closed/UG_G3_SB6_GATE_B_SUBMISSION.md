# UG-G3-SB6 Gate B 送審：Timeout Gating

> **狀態**：**Gate B 已核准（2026-09-16，PO 核准；§7 一處解釋訂正、§2／§1 兩處小數訂正後結案）**。
> **對應 Gate A 提案**：`doc/upgrade/gates/UG_G3_SB6_GATE_A_PROPOSAL.md`（PO 核准 `83749de`，v3）。
> **本 SB 全程無真實庫寫入**，不適用 RISK-013 三項協議；全程對 `UG-G3-SB4` 已核准 OOF parquet 唯讀運算，只寫一份證據 JSON。
> **主要發現**：`selected_theta` 落在裁決 (a) 三項判準的覆蓋率地板邊界（θ=0.06907，coverage=0.8000），非退化解；`regime_diagnostic` 顯示被 gate 的列**全部**落在低波動三分位組——現行 Timeout gating 在行為上近似「低波動期不交易」，是 `UG-G3-SB5` Gate B §4 `INFERENCE` 的第一個行為層證據（見 §3）。

---

## 1. 完整 Commit 序列

| # | Commit | 內容 | 發現／要求者 |
|---|--------|------|------|
| 0 | `83749de` | Gate A 提案核准（v1→v2→v3：v1 審查方唯讀探測推翻量化判準→四項裁決＋六處訂正→v2 兩處再訂正：`θ` 差異真因為 OvR 正規化、可行區間選點規則於 Gate A 即釘住→v3 核准） | PO／審查方核准 |
| 1 | `900c616` | 紅測（RED）——`src/ml/gating.py` 38 項，紅測清單 v1→v2（3 項結構性缺口＋7 項強化，審查方複核提出） | PM 撰寫，審查方複核清單 |
| 2 | `09bcba9` | 實作（GREEN）——`src/ml/gating.py` 新建，38 項轉綠；審查方複核 5 個 PO 指定突變體逐一構造，另發現 2 個未覆蓋邊界（`min_positive_for_auc` 邊界、class-0 索引硬編碼，結構性） | PM 實作，審查方複核 |
| 3 | `23e2039` | 紅測（RED）——報告腳本 60 項，含 `assert_calibrator_matches_sb5()` 比對鍵訂正 | 審查方複核 `09bcba9` 時發現真實缺陷設計（`doc/upgrade/gates/UG_G3_SB6_GATE_A_PROPOSAL.md` §3.7 與本輪訊息）；**PM 訂正審查方原始診斷**——審查方最初認為 TB JSON 完全沒有 `auc_calib_fit_raw` 鍵，PM 獨立核對後確認該鍵確實存在，只是巢狀 `{class: float}` 字典而非單一浮點數，修法方向不變但診斷更精確 |
| 4 | `81def57` | 實作（GREEN）——`run_report()` 完整管線；`src/ml/gating.py` 三處補強（regime 欄位補回、比對鍵泛化、新增 `assemble_curve_row()`） | PM 實作；PM 自我揭露 `_build_dual_curves()` 已知限制（簽章只接受單一 `raw_eval`，主管線未接入此函式，改為直接對兩模型各自分數呼叫 `assemble_curve_row()`） |
| 5 | `3eacb6f` | 紅測（RED）——訂正 `_build_dual_curves()` 簽章，防止空殼繞過 | 審查方複核 `81def57` 時判定 PM 的「已知限制」揭露不足以結案：該函式的既有測試覆蓋的是**被主管線繞過、未實際使用**的空殼，`CLAUDE.md` §9A.1「測試把該模組換成 stub」的第二個實例；PO 裁決根因「責任一半在我（PO 的簽章設計批准）、一半在 PM（提案設計）」 |
| 6 | `cd5f69a` | 實作（GREEN）——`_build_dual_curves()` 簽章訂正為接受 LR／Ridge**各自**的校準器與**各自**的原始分數，`run_report()` 改組後統一呼叫一次 | PM 實作，審查方複核 |
| 7 | `217eb43` | 紅測（RED）——`verify_oof_sha256()` 真實鍵名（`oof_parquet_sha256`），含 `VerifyOofSha256Tests` 三項 | **PM 乾跑自抓**——單折乾跑第一步即拋 `KeyError: 'oof_sha256'`，`gen_evidence["oof_sha256"]` 讀的鍵名不存在，真實鍵名為 `oof_parquet_sha256`（`UG-G3-SB5` 同名函式已正確讀取，SB6 宣稱「比照」卻未照抄）；PM 停下回報 PO 後獲授權修正，非審查方或 PO 先發現 |
| 8 | `8ef8378` | 實作（GREEN）——一行修正，不加相容 fallback | PM 實作，PO 授權範圍 |
| 9 | `627cca7` | `.gitignore` 加 `.claude/settings.local.json` | **PM 乾跑自抓**——`script_untracked_paths` 非空，PM 查明是 host **使用者層級** `~/.config/git/ignore` 與容器環境差異（非 repo 層級 `.gitignore`，非工作樹真髒），審查方裁決加入 repo 層級 `.gitignore` | 
| 10 | `20af8c8` | 全量執行證據 JSON（`--write`） | PM 執行，與乾跑 JSON 程式化逐鍵 diff，審查方獨立驗證確認差異集合為空（排除預期鍵） |

**兩份證據 JSON**：`UG_G3_SB4_oof_generation_target_triple_barrier.json`（`UG-G3-SB4` 既有）＋`UG_G3_SB6_gating_report.json`（本 SB，`script_commit=627cca7`，`script_dirty=false`，`script_untracked_paths=[]`，sha256 `aff85bd5efc85fe688719a43de4c170a01726f479a7600defb28e4c8724e9227`）。

---

## 2. Gate A §8 Definition of Done 逐項對號

| # | 項目 | 狀態 | 對應 |
|---|------|------|------|
| 1 | `target_up_down` 排除守衛與 known-FAIL 通過（§3.1、§5） | ✅ 已完成 | `_validate_target_column()`／`GatingTargetColumnError`；`TargetColumnEntryGuardTests`（`run_report()` 第一行即驗證，任何檔案存取之前，紅測 `test_run_report_rejects_up_down_before_file_access` 鎖定順序） |
| 2 | Holdout 折序號／日期雙重守衛與 known-FAIL 通過（§3.4 訂正 2、§5） | ✅ 已完成 | `assert_holdout_isolation()`；`HoldoutIsolationTests`（5 項，含 `fold_id=33` mutant 注入的 known-FAIL 與乾淨輸入正控制）；乾跑／全量執行實際 `holdout_guard={"fold_id_max": 32, "trade_date_max": "2025-10-22", "holdout_start_date": "2025-10-23"}`，逐位符合 `DEC-040` |
| 3 | `θ` 門檻曲線（LR 主、Ridge 對照）與隨機基線（解析值）對照皆已計算並寫入證據 JSON，雙網格皆涵蓋 | ✅ 已完成 | `theta_grid={"fine": [121 點], "quantile": [100 點]}`；`lr_curve`／`ridge_curve` 各 221 列；`random_baseline_precision=0.047123`（解析值，等於 Calib-eval 全段 Timeout 基期 389/8255，`assert_report_baseline_consistent()` 獨立重算比對） |
| 4 | 裁決 (a) 三項量化判準的可行區間，與依固定選點規則選定的 `θ*`，連同選擇理由明確記錄；若與 §2.5 抽樣預期有出入需誠實揭露 | ✅ 已完成，見下方逐項對號 | `selected_theta` |
| 5 | §3.6 `volatility_20d` 三分位診斷區塊完成（必做），組內正例 <10 的組別 `auc` 正確記為 `null` | ✅ 已完成，見 §3 | `regime_diagnostic`；高波動組（正例=1）`auc=null` |
| 6 | 全套測試 PASS；`gate0_contract_check.py` 14/14 PASS | ✅ 已完成 | 見 §7 |
| 7 | 四份文件依實作結果更新，`predictor.py`／`evaluator.py` 出現在 Out of Scope | 待本 Gate B 核准後執行，草案見 §5 | — |
| 8 | `DEC-041` 狀態轉 `APPROVED` | 待本 Gate B 核准後執行，草案見 §5 | — |
| 9 | `PROJECT_STATUS.md` §0.2 新增 `UG-G3-SB6` CLOSED 列，下一步指向 `UG-G3-SB7` | 待本 Gate B 核准後執行，草案見 §5 | — |

### 第 4 項：`selected_theta` 逐項對號裁決 (a) 三項判準

| 判準 | 門檻 | 實際值 | 是否滿足 |
|---|---|---|---|
| 覆蓋率 | ≥80% | 0.8000（精確落在地板） | ✅（邊界） |
| 精準度提升 | ≥4.0× | 4.1517× | ✅ |
| Timeout 召回 | ≥60% | 83.03% | ✅ |

`θ*=0.06907452098250194`，`gate_pct=0.19999999999999996`（≈20%），`precision=0.1956390066626287`，`rule="max_recall_tiebreak_precision"`。

**`θ*` 是把召回判準推到覆蓋率地板邊界的結果，不是自然收斂到最佳點**（Gate A §3.5 已明寫此性質，本節為落地驗證）：`select_theta_star()` 在滿足三項判準的可行集內取召回最高者——召回隨 gate 比例單調上升，覆蓋率隨 gate 比例單調下降，兩者此消彼長，因此「召回最高」必然發生在可行集裡覆蓋率最低（即最接近 80% 地板）的那一端。相鄰兩個網格點驗證此性質非邊界效應誤選：

| θ | gate_pct | coverage | recall | 是否可行 |
|---|---|---|---|---|
| 0.065 | 20.87% | 0.7913 | 0.8432 | ❌（coverage < 0.80） |
| **0.06907（選中）** | **20.00%** | **0.8000** | **0.8303** | ✅ |
| 0.07 | 19.83% | 0.8017 | 0.8278 | ✅ |

左鄰點（0.065）的 recall（0.8432）高於選中點，但因 coverage 跌破地板而被判定不可行；選中點是可行集內 recall 最高者，符合設計，不是誤選。

**`θ_grid_source` 揭露**：θ 網格（`fine`＋`quantile` 兩種並存）僅依 **LR 的校準後 `P₀` 分布**建構（`build_theta_grid(lr_p0_for_grid)`），Ridge 的對照曲線套用同一組網格點，不是各自獨立建的網格。這反映裁決 (c)「LR 為唯一 gating 來源，Ridge 僅對照揭露」的既有設計，但目前證據 JSON 未附加明文欄位標註此事——下次觸碰報告腳本時補 `theta_grid_source: "LogisticRegression"` 欄位，本輪先以文件揭露。

---

## 3. Regime 診斷（§3.6，必做項目，行為層發現）

**`volatility_20d` 三分位（切點 0.304214／0.481117），Calib-eval，`θ*` 下各組表現**：

| 分位 | n | 該組 coverage（未被 gate 比例） | Timeout 基期 | 組內 Timeout 召回 | 組內 AUC（LR） |
|---|---|---|---|---|---|
| 低波動 | 2,752 | **0.4001**（60% 列被 gate） | 12.94% | **90.73%** | 0.7761 |
| 中波動 | 2,751 | **1.0000**（0% 列被 gate） | 1.16% | 0.00% | 0.7539 |
| 高波動 | 2,752 | **1.0000**（0% 列被 gate） | 0.04% | 0.00% | `null`（正例=1 <10，`min_positive_for_auc` 守衛） |

> **⚠ 訂正**：`20af8c8` commit body 誤植低波動組 coverage 為 `0.4007`，正確值為 **`0.4001`**（`UG_G3_SB6_gating_report.json` → `regime_diagnostic[0].coverage=0.4000726744186046`，PM 自行核對時的四捨五入誤植，PO 本輪複核訊息中的 `0.4001`是正確值）。依 `CLAUDE.md` §11A 不 amend 既有 commit，訂正記錄於本文件，比照 §6 `fe30ef2` 的處理方式。

**`INFERENCE`**（非既有規格或研究依據，供 §5 決策參考）：**被 `θ*` gate 掉的列全部落在低波動三分位組（中、高波動組 0 列被 gate）**——現行 Timeout gating 在行為上幾乎等價於「低波動期不交易」。這是 `UG-G3-SB5` Gate B §4 `INFERENCE`（「Timeout 訊號大半是波動率水準本身」）的**第一個行為層證據**：不只是「低波動組的 Timeout 基期是高波動組的 300 倍以上」這個相關性觀察，而是「用校準後機率做門檻選擇，選出來的觀望時段幾乎完全由波動率水準決定」這個更直接的行為結果。

**尚未驗證，登記 `UG-G3-SB7` 必列基線**：一個**只用 `volatility_20d` 分位數、不訓練任何模型**的規則（例如「波動率低於某分位數即觀望」）是否能達到接近的 gating 效果，是本 SB 未回答的問題——若答案是「接近」，代表整條 Meta-Learner／校準管線對 Timeout gating 這個具體任務的邊際貢獻有限；若答案是「明顯較差」，則校準後機率確實提供了波動率單變數給不了的資訊。此比較**不是本 SB 的結論，是待驗證項**，需與 Timeout gating 並列比較，於 `UG-G3-SB7` Gate A 提案登記為必列基線。

---

## 4. 未驗證清單（有名字有去處）

| 項目 | 去處 |
|------|------|
| `θ*` 在 Holdout（折 33-42）的穩定性 | `UG-G3-SB7`，`DEC-040` 唯一消費者條款延續 |
| 裁決 (a) 三項判準是看過 §2.5 實測曲線後訂的事後目標，非獨立於資料的先驗設計 | `UG-G3-SB7` 用 Holdout 檢驗是否仍然成立，Gate A §3.5 已明寫不宣稱穩定重現 |
| 波動率單變數基線是否等效於 Timeout gating（§3 新登記） | `UG-G3-SB7` Gate A 必列基線 |
| `theta_grid_source` 欄位未寫入證據 JSON，僅文件揭露 | 下次觸碰報告腳本時補欄位，非本輪範圍 |
| Ridge 只揭露未參與選擇——若 SB7 上 LR 失效 | 屆時可回頭評估 Ridge 作為備選 gating 來源，本 SB 不預先決定 |
| `predictor.py`／`evaluator.py` 是否需要接入 gating 決策、如何接 | `UG-G3-SB7`／Gate-4（Gate A 裁決 (d) 明列 Out of Scope） |

---

## 5. 文件同步草案（待 Gate B 核准後執行）

### 5.1 `DECISIONS.md` `DEC-041` 狀態轉 `APPROVED`

```
- 狀態：APPROVED（UG-G3-SB6 Gate B 核准，PO YYYY-MM-DD 核准，approved by: Project Owner）
```

`Verification` 欄兩項 `NOT VERIFIED` 勾選項更新：
- [x] `UG-G3-SB6` Gate A 提案已具體定義 gating 評估指標並實測驗證（`VERIFIED THIS SESSION`，本 Gate B，`UG_G3_SB6_gating_report.json`）。
- [ ] NOT VERIFIED → 去處不變：決策 3 特徵層面候補案仍待 `UG-G3-SB7` 結案後評估。

### 5.2 `REMAINING_RISKS.md` `RISK-030` 追加一段（去處欄）

> **`UG-G3-SB6` Gate B 結果（YYYY-MM-DD）**：Timeout gating 於 Calib-eval 段達成裁決 (a) 三項量化目標（覆蓋率 80.00%、精準度提升 4.15×、召回 83.03%，`θ*=0.06907`，落在覆蓋率地板邊界）；`regime_diagnostic` 顯示被 gate 的列全部落在低波動三分位組，是本風險「Timeout 訊號集中於波動率水準」推論的第一個行為層證據。樣本外檢驗（Holdout）與波動率單變數基線比較留待 `UG-G3-SB7`。`DEC-041` 狀態轉 `APPROVED`。

### 5.3 `SYSTEM_UPGRADE_MASTER_PLAN.md`

**§9 `UG-G3-SB6` Brief**：範圍調整註記追加一句「**Gate B 已核准（YYYY-MM-DD）**，實際範圍見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md`」；Affected Components 訂正為：

```
| Affected Components | `src/ml/gating.py`（新建）、`scripts/verify/ug_g3_sb6_gating_report.py`（新建）、`.gitignore` |
```

（原規劃 `src/ml/predictor.py`／`src/ml/evaluator.py` 未被觸及，依裁決 (d) 已於 Gate A 明列 Out of Scope。）

**§11.1** 條件勝率目標行追加一句：

> Timeout gating 目標（覆蓋率 ≥80%、精準度提升 ≥4×、召回 ≥60%）已於 `UG-G3-SB6` Calib-eval 段達成；Holdout 樣本外檢驗待 `UG-G3-SB7`。

### 5.4 `PROJECT_STATUS.md`

**§0.2** 新增 `UG-G3-SB6` 列草案（比照既有 CLOSED 列寫法，commit 序列摘要、DoD 對號摘要、下一步指向 `UG-G3-SB7`，正式版本於結案時依§0.3A 三處同步規則展開）。

**§0.5** 新增兩則：
1. 波動率單變數基線待列入 `UG-G3-SB7` Gate A 必答項（見本文件 §3「尚未驗證，登記 `UG-G3-SB7` 必列基線」段落），觸發條件綁 `UG-G3-SB7` Gate A 提案階段。
2. **候補小案**：repo 無 `.gitattributes`，容器與 host 對行尾（CRLF／LF）判定不一致（見本文件 §7，`touch` 測試證實約 48 個既有追蹤檔案存在真實、持續的行尾差異，僅 `git status` 是否顯示受 stat cache 影響）；是否加 `.gitattributes` 統一行尾規則，另案評估，**不在本 SB 處理**。觸發條件：下一次有人在容器內執行會依賴 `git status`／`git diff` 判斷工作樹狀態的 git 操作（而非只跑既有腳本，既有報告腳本已用 `-c core.autocrlf=true` 規避此問題）。

### 5.5 `TRACEABILITY.md`

對應章節同步 `DEC-041` 狀態為 `APPROVED`（§3.2 索引與 §3A／§3A.1 交付物矩陣、決策鏈標記三處，依 `evidence-sync` skill 傳播清單）。

### 5.6 `gate0_contract_check.py` `DOC_PATHS`

依 `CLAUDE.md` §16.4 查證：`DOC_PATHS` 只涵蓋 `SYSTEM_UPGRADE_MASTER_PLAN.md`／`FEATURE_REGISTRY.md`／`PURGED_WALK_FORWARD_SPEC.md`／`MULTI_SOURCE_DATA_CONTRACT.md`／`DB_MIGRATION_PLAN.md`／`DECISIONS.md`／`TRACEABILITY.md` 七份固定文件，不含 `gates/` 資料夾下的 Gate A／B 文件本身——本次 `git mv` 至 `closed/` **不需要**更新 `DOC_PATHS`（比照 `UG-G3-SB5` 先例的查證結論，非假設沿用）。

---

## 6. Commit 敘事訂正（兩處，兩個事實並列，不擇一）

### 6.1 `fe30ef2`（延續自 `UG-G3-SB5` Gate B §9 附註）

`fe30ef2` commit body 的「PM 在核准訊息……把 §10 寫錯」一句，正確敘事為兩個事實並列：

1. **§10 這個章節號的筆誤，源頭是 PO 在核准訊息（`UG-G3-SB5` Gate B 裁決 (d)）裡寫錯**。
2. **PM 把這個筆誤原樣照抄進 `DEC-041`／文件同步，未在送審前查證章節號是否正確**——這是 PM 自己的疏失。

兩者缺一都不完整：只寫 1 會顯得 PM 沒有查證責任；只寫 2（`fe30ef2` 目前的寫法）會讓人以為 §10 這個錯誤數字是 PM 憑空寫出來的，模糊了它其實來自 PO 自己的訊息。依 `CLAUDE.md` §11A 不 amend 既有 commit；本節取代 `fe30ef2` 這句不完整的敘事。

### 6.2 `20af8c8`（本 Gate B 新增）

`20af8c8` commit body 記載低波動組 coverage 為 `0.4007`，正確值為 `0.4001`——PM 手動謄寫證據 JSON 數字時的四捨五入誤植（原始值 `0.4000726744186046`），非計算錯誤或證據 JSON 本身有誤（JSON 內數值正確，`--write` 全量執行的結果不受影響）。已於本文件 §3 訂正並標註來源。依 `CLAUDE.md` §11A 不 amend 既有 commit。

---

## 7. 驗證環境與結果

| 項目 | 結果 |
|---|---|
| 執行環境 | **container**（`stock_prediction_system2_devcontainer-app-1`），Python 3.14.6 |
| 全套測試 | `Ran 1031 tests` `OK`（`217eb43` RED 後最終狀態；`900c616`→`09bcba9`→`23e2039`→`81def57`→`3eacb6f`→`cd5f69a`→`217eb43`→`8ef8378` 各輪 RED/GREEN 交替，零回歸累計） |
| `gate0_contract_check.py` | Part B: 14/14 PASS（三個收尾 commit `627cca7`／`20af8c8` 前後各執行一次，皆 14/14） |
| numstat 與 `-w` 格式夾帶偵測 | 全部 commit 無落差 |
| 容器內 `git status` 顯示約 48 個檔案為 ` M` | **訂正（審查方複核指出原判斷有誤）**：不是暫態快取，是**持續存在**的真實 CRLF／LF 差異。獨立重驗：`touch AGENTS.md`（只改 mtime，不改內容）後 `git diff --stat` 顯示該檔 **418 insertions/418 deletions**——整檔逐行皆判為變更，證明工作區位元組與 git 記錄的 blob 確實逐行不同（不是視覺格式問題）；`git diff --numstat -w` 為空，差異僅止於行尾；repo 無 `.gitattributes`；容器內 `git config --get core.autocrlf` 為空（未設定），故 git 對此類檔案不做任何行尾轉換，逐位元組比較直接暴露 host 端 `core.autocrlf=true` 寫入的 CRLF 與 blob 記錄的行尾不一致。**這個差異本身不會消失**——會消失的是 `git status` 是否「顯示」它：git 索引的 stat cache（記錄的 mtime／size）若與目前檔案相符，`git status` 會略過逐位元組重新比對、直接回報乾淨，即使底層行尾差異從未真正解決；一旦任何動作使 mtime 改變（如上述 `touch` 測試，或不同 exec session 對 bind mount 的 stat 觀測差異），下一次比對就會重新暴露差異。這解釋了為何同一份工作樹在不同時間點的 `git status` 呼叫，看到的受影響檔案數會不一致——不是差異時有時無，是「是否被重新檢查」時有時無。報告腳本用 `-c core.autocrlf=true` 呼叫 git，強制做行尾正規化後比較，因此 `script_dirty=False` 的判定不受此影響，結論不變 |
| evidence JSON sha256 | `aff85bd5efc85fe688719a43de4c170a01726f479a7600defb28e4c8724e9227` |
| 乾跑 vs 全量執行程式化逐鍵 diff | 排除 `run_timestamp`／`total_elapsed_seconds`／`script_commit`／`script_untracked_paths` 後差異集合為空（審查方獨立驗證確認） |

---

## 8. 核准後動作（待 PO 核准後執行）

依 `CLAUDE.md` §16.3、`gate-submit` skill 產出 8：

**Commit 方式（比照 `UG-G3-SB5` 先例，`3f77fb9`）**：本文件此前未曾 commit 過，結案 commit 內**以新檔直接寫入 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md`**（不先進 `gates/` 根層再 `git mv`）；`UG_G3_SB6_GATE_A_PROPOSAL.md` 已於 `83749de` commit 過，`git mv` 至 `closed/`（須為 `R100` 純 rename）。commit body 需寫明採用此方式（新檔進 `closed/`＋既有檔 `git mv`，二擇一已擇定）。

1. `git mv` `UG_G3_SB6_GATE_A_PROPOSAL.md` 至 `doc/upgrade/gates/closed/`；確認 `git diff --cached --name-status` 對該檔為 `R100`。本 Gate B 文件以新檔（`A`）方式直接進 `closed/`。
2. `gate0_contract_check.py` 的 `DOC_PATHS` 依 §5.6 查證結論，不需更新。
3. `doc/README.md` 逐份文件表同步（資料夾層級登錄，比照 `UG-G3-SB5` 先例）。
4. `PROJECT_STATUS.md` §0.2 `UG-G3-SB6` 列狀態改為 `CLOSED`，附核准日期與結案 commit hash，下一步指向 `UG-G3-SB7` Gate A；§0.5 新增 §5.4 草案的兩則登記（波動率基線、`.gitattributes` 候補）。
5. `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 依 §5.3 草案更新；§11.1 依 §5.3 草案追加一句。
6. `REMAINING_RISKS.md` `RISK-030` 依 §5.2 草案追加一段。
7. `DECISIONS.md` `DEC-041` 依 §5.1 草案轉 `APPROVED`（狀態列、`Approved by`、核准日期、Verification 勾選更新）；`TRACEABILITY.md` 條目 38 與 §3A／§3A.1 矩陣三處依 §5.5 同步。
8. 容器內重跑：全套測試、`gate0_contract_check.py` 14/14 PASS 且 **B13「待轉」清單不再含 `DEC-041`**、B14 對 `DEC-041` 通過；`git diff --cached --numstat` 與 `-w` 無落差。

**Gate B 已核准，結案 commit 依上述方式執行。**
