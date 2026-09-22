# UG-G1-SB3 Gate A 提案：UI 排行榜動態化

> **性質**：Gate A 提案（實作前審批），非實作。
> **提交日期**：2026-08-25
> **前置**：UG-Gate-1 已由 PO 核准（逐 SB 授權）；UG-G1-SB1（commit `ccf0e52a`）與
> UG-G1-SB2（commit `414fcc8`）已結案。
> **狀態**：`src/` 未動，diff 為空。
> **與 Master Plan Brief 的關係**：`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 UG-G1-SB3 已有一份
> Brief，本提案在其基礎上做了現況逐行核對，並發現兩處需要 PO 裁決才能定案的落差（§3）。

---

## 1. 本提案要解決的問題

| # | 來源 | 內容 |
|---|------|------|
| 1 | Master Plan §7.1 UG-G1-SB3 Brief；DRIFT-008（HIGH） | 排行榜資料改為從 Artifact 讀取，不再寫死；無 Artifact 時顯示 EMPTY 而非假資料 |
| 2 | DRIFT-018（**CRITICAL**，PROJECT_STATUS.md §0.5 義務 #3） | 排行榜現行 8 個寫死數值存在三個獨立矛盾（見 §2.2）。歸屬原標記為 UG-G1-SB2，但 SB2 只做了「標註為未經驗證展示值」的**標籤化處理**，未實際修正——這正是 SB3 的對象，本提案請求把 DRIFT-018 的實際修正併入 SB3 範圍（§3.2） |
| 3 | 本次提案時發現 | `src/ml/evaluator.py` 的 `MLEvaluator.evaluate_tournament()` 已是**可執行的真實 8 組實驗評估器**，並非只是 Gate 3 的規劃文字——這改變了 Master Plan Brief 原本「Gate 3 完成前排行榜必為空」的前提，需要 PO 就此重新裁決範圍（§3.1） |

---

## 2. 現況與問題（逐行核對，2026-08-25）

### 2.1 現行程式碼

`src/ui/components.py:166-184`（`render_tournament_leaderboard()`）：

```python
def render_tournament_leaderboard() -> None:
    ...
    data = [
        {"排名": "🏆 冠軍", "模型演算法": "Random Forest", ..., "Macro F1": "0.5820", ...},
        {"排名": "🥈 亞軍", "模型演算法": "LightGBM", ..., "Macro F1": "0.5910", ...},
        ...  # 共 8 組，全部字面常數
    ]
    df_lb = pd.DataFrame(data)
    st.dataframe(df_lb, use_container_width=True, hide_index=True)
```

函式**不接受任何參數、不讀取任何檔案／DB／DataMode**，8 組數字完全寫死在 UI 層。
`app.py` 呼叫時也不帶入任何資料來源狀態（`render_tournament_leaderboard()`，無參數）。
這與 SB2 已建立的「所有資料展示區塊皆標示 DataMode」原則不一致——目前是**唯一一個
完全不受 DataMode 約束的資料展示區塊**。

### 2.2 DRIFT-018 的三個矛盾（逐一核對現行常數，2026-08-25 SB2 視覺驗證時已確認程式碼現況未變）

1. **排名與自身數字牴觸**：冠軍 Random Forest（F1 `0.5820`／命中率 `58.4%`／報酬 `+8.2%`）
   在全部三個指標上同時輸給亞軍 LightGBM（`0.5910`／`59.2%`／`+9.6%`）與季軍 XGBoost
   （`0.5860`／`58.8%`／`+8.9%`）——常數本身的排序邏輯不自洽。
2. **同一實作兩個分數**：依 DRIFT-015，host 環境下 `lightgbm` 與 `xgboost` 回傳同一個
   `_FallbackTreeEnsembleClassifier`，但常數表仍給它們不同分數（此矛盾在**容器內**環境下
   不成立，因容器 12/12 套件齊備、兩者是不同真實實作——但常數表本身無法呈現「環境相關」
   這件事，因為它連環境都不知道自己跑在哪）。
3. **無任何實驗產出物連結**：`render_tournament_leaderboard()` 不讀取任何檔案、JSON 或
   artifact——這是三個矛盾中**唯一**單靠「動態化」就能直接解決的一項；前兩項需要數字本身
   來自真實計算才能一併解決。

### 2.3 意外發現：評估引擎已存在且可執行

`src/ml/evaluator.py` 的 `MLEvaluator.evaluate_tournament(df, splitter, ...)`：

- 對 `SUPPORTED_MODELS = (logistic_regression, random_forest, lightgbm, xgboost)` 逐一執行
  控制組（`PureTechnical`，9 特徵）與實驗組（`MultiModal`，18 特徵）共 8 組實驗。
- 每組呼叫 `splitter.split(df)`（即 SB1 已修正的 `WalkForwardSplitter`，含 Purge/Embargo）
  逐 Fold 訓練，回傳 `macro_f1`／`accuracy`／`roc_auc`／`directional_hit_ratio`／
  `cumulative_return`／`sharpe_ratio`／`max_drawdown`。
- 自動計算 `alpha_attribution`（`delta_macro_f1`／`delta_cumulative_return`／
  `delta_hit_ratio`／`sentiment_effective`）與 `champion_model_name`
  （綜合分數 `macro_f1*0.7 + hit_ratio*0.3` 排序選出，非人工指定）。
- 訓練目標欄位 `target_up_down`／`target_return_1d` 已由 `feature_aggregator.py`
  的 `append_target_labels()` 產出（`shift(-1)` 的簡單 T+1 二元標籤），**不依賴**
  Gate 3 規劃中的 Triple-Barrier 標籤——這是現行 `app.py` 即時預測面板已在用的同一組標籤。

**結論**：`evaluate_tournament()` 今天就能對真實歷史資料跑出真實的 8 組結果，不需要
等 Gate 3。Master Plan Brief 把「模型競技本身」列為 Out of Scope、註記「Gate 3 完成前
排行榜為空」，這個前提**在提案當下已不成立**——不是規劃錯誤，而是評估器已经先於
Gate 3 正式啟動被建好（本專案曾有版控外工作的先例，見 DRIFT-017，這可能是同一批遺留）。

### 2.4 尚不存在的部分

- 沒有任何 artifact 檔案或目錄（`models/`、`artifacts/` 皆不存在）。
- 沒有任何程式碼呼叫過 `evaluate_tournament()`——它是完整實作但從未被執行過的死碼，
  尚未有任何證據顯示它跑起來真的會成功（未 verified，見 §5 known-FAIL 對照）。
- `MultiModalTrainer.save_artifact()`／`load_artifact()`（`model_trainer.py:284,303`）
  是**模型物件**的序列化，不是排行榜結果的序列化——兩者是不同的持久化需求，不能直接複用。

---

## 3. 需要 PO 裁決的兩個問題

### 3.1 範圍選項：只做讀取機制，還是連同真正跑一次？

| | 方案 A：維持 Master Plan 原範圍 | 方案 B：本次一併執行評估器 |
|---|---|---|
| 做的事 | 新增 `load_tournament_results()` 讀取 artifact；`components.py` 改為接收 `(data, mode)`；無 artifact 時 EMPTY | 方案 A 的全部 + 一支一次性腳本呼叫 `evaluate_tournament()`，對真實歷史資料跑出真實 8 組結果並寫成 artifact |
| DRIFT-018 三個矛盾 | 只解決矛盾 (3)；矛盾 (1)(2) 仍懸而未決（因為 EMPTY 狀態下排行榜不顯示任何數字，矛盾暫時「消失」但不是「解決」） | 三個矛盾全部解決——數字來自真實計算，排名邏輯自洽，容器內兩個演算法本就是不同實作 |
| 使用者可見結果 | 排行榜顯示「尚未完成模型競技」，與 Master Plan 原 Risk 註記一致 | 排行榜顯示真實回測結果（可能與現行 KPI 卡片的即時預測面板數字產生新的一致性要求，需一併檢查） |
| 新增風險 | 低——純讀取邏輯，無新執行路徑 | 中——需要對**真實開發資料庫**執行只讀查詢取得完整歷史資料（非 SB1/SB2 慣用的隔離臨時 DB，因為這次需要的正是真實歷史資料本身）；執行時間未知（8 組 × Walk-Forward 多 Fold，需先小規模試跑量測） |
| 與 Gate 3 的關係 | 完全不觸碰 Gate 3 範圍 | 使用了 Gate 3 規劃書中「Specialist Models」概念的評估邏輯，但**評估器程式碼已存在且與 Gate 3 尚未啟動的其他項目（Panel Dataset／Triple-Barrier）無耦合**——本身可獨立執行 |

**本提案傾向方案 B**——理由：方案 A 只是把「顯示假數字」換成「顯示什麼都沒有」，
DRIFT-018 被評為 CRITICAL 的三個矛盾裡有兩個依然不會被解決；而評估器經核對後
確認可獨立執行、不依賴 Gate 3 其餘未完成部分。但方案 B 需要動用真實開發資料庫的
完整歷史資料（唯讀），且執行時間未知，**這是本提案的核心裁決請求，PM 不自行決定**。

若 PO 選方案 B，執行前會先依 RISK-013 協定，在真正對真實 DB 執行只讀查詢前，
先呈報綁定確認（`DBWriter.db_config` 解析結果）供 PO 過目再執行。

### 3.2 DRIFT-018 歸屬修正

`DOCUMENT_DRIFT_REMEDIATION.md` 第 89 列目前寫「UG-G1-SB2」，但 SB2 已於 2026-08-25
CLOSED，且 SB2 對 DRIFT-018 做的僅是「標註原則」（§0.5 義務 #3 的措辭），三個矛盾本身
未修正。本提案請求：若 PO 核准 SB3 開工，一併修正該列歸屬為 UG-G1-SB3，並在 SB3
Gate B 結案時登記 DRIFT-018 的實際修正證據（而非僅標籤）。

---

## 4. 變更範圍（依 §3.1 選定方案而定）

### 4.1 兩方案共通部分

| 項目 | 內容 |
|------|------|
| Affected Components | `src/ui/data_loader.py`（新增 `load_tournament_results()`）、`src/ui/components.py`（`render_tournament_leaderboard()` 簽章改為接收 `(data, mode)`） |
| Data/API/Schema Contract | Artifact JSON 路徑提案：`models/artifacts/tournament_results.json`；結構直接沿用 `evaluate_tournament()` 現有回傳形狀（`leaderboard: [...]`、`alpha_attribution: {...}`、`champion_model_name`、`champion_score`），**不重新設計一套更窄的欄位**（Master Plan 原提案的 `{model_name, feature_set, macro_f1, hit_ratio, cumulative_return, alpha_delta}` 欄位較窄，建議改採評估器實際輸出，理由：既有計算已含 `accuracy`／`roc_auc`／`sharpe_ratio`／`max_drawdown`，捨棄可用資訊沒有必要） |
| Failure Semantics | Artifact 不存在 → `DataMode.EMPTY`；JSON 格式錯誤／欄位缺失 → `DataMode.ERROR` + log warning（沿用 DEC-012 方案 B 精神：不自動退回假資料） |
| In Scope | 上述兩檔案；`app.py` 呼叫處改為解包 `(data, mode)` 並傳給 `render_tournament_leaderboard` |
| Out of Scope | Triple-Barrier 標籤（Gate 3）；Panel Dataset（Gate 3）；模型 artifact（`.pkl`）本身的版本管理；排行榜之外的其他 UI 區塊 |

### 4.2 方案 B 額外需要

| 項目 | 內容 |
|------|------|
| 新增檔案 | 一支一次性腳本（暫定 `scripts/generate_tournament_artifact.py`），呼叫 `MLEvaluator.evaluate_tournament()` 並寫出 JSON |
| 執行環境 | 容器內、真實開發 DB（唯讀），非隔離臨時 DB——執行前呈報綁定確認 |
| Artifact 是否入版控 | 待 PO 決定：(a) 直接 commit 這份 JSON（作品集展示用途，內容透明可稽核）；(b) `.gitignore` 排除，視為可重新產生的 build 產物，README 附上重新產生指令。本提案傾向 (a)，理由與 DEC-012 一致——這是求職作品集，真實產出的證據本身就是展示的一部分 |

---

## 5. 驗證計畫（比照 SB1/SB2 模式）

| 項目 | 內容 |
|------|------|
| Tests | `test_leaderboard_from_artifact`、`test_leaderboard_empty_when_no_artifact`、`test_leaderboard_error_on_malformed`、`test_leaderboard_demo_mode_banner`（沿用 Master Plan Brief 既定四項） |
| known-FAIL 示範（§9A.2） | 至少對「artifact 格式錯誤 → ERROR」與「artifact 缺失 → EMPTY」各構造一個真實會 FAIL 的案例，證明測試不是裝飾性斷言 |
| E2E Verification | 放置測試 artifact → 排行榜顯示；移除 artifact → 顯示「尚未完成模型競技」（EMPTY 橫幅） |
| 若選方案 B | 額外驗證：`evaluate_tournament()` 首次真實執行的原始輸出（含執行時間量測，供未來排程/CI 決策參考）；champion_model_name 與 app.py 即時預測面板目前使用的模型是否一致，不一致需說明原因（兩者選模邏輯本來就可能不同，但需先弄清楚差異來源避免使用者混淆） |
| Documentation Sync | `SDD` UI 章節；`TRACEABILITY.md`；`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-008 結案、DRIFT-018 歸屬修正與實際修正證據）；新增 ADR（DEC-013 或下一個可用編號，記錄方案 A/B 之裁決） |

---

## 6. 範圍邊界（本 SB 不做什麼）

- 不修改 `src/ml/evaluator.py`、`model_trainer.py`、`baseline_models.py` 的既有邏輯——
  若方案 B 執行後發現評估器本身有 bug，停手回報，不在本 SB 內順手修正（除非是阻擋
  SB3 完成的必要修復，屆時會先停下來請示）。
- 不建立排行榜的自動排程／CI 定期重跑機制（如需要，屬未來另一個 SB）。
- 不變更 `app.py` 即時預測面板（KPI 卡片、AI 預測面板）的既有邏輯，僅新增排行榜區塊的
  資料來源改造。
- 不處理 Gate 3 規劃中的 Triple-Barrier 標籤或 Panel Dataset。

---

## 7. 請求 PO 裁決

1. **§3.1 範圍選項**：方案 A（僅讀取機制，排行榜維持 EMPTY 直到未來某次真正執行）
   或方案 B（本次一併執行評估器，產出真實 artifact，實際解決 DRIFT-018 三個矛盾）？
2. **§3.2 DRIFT-018 歸屬修正**：是否同意歸屬列由 UG-G1-SB2 改為 UG-G1-SB3？
3. **§4.1 Artifact 欄位**：是否同意採用評估器現有的完整輸出欄位，而非 Master Plan
   原提案的較窄欄位集合？
4. **§4.2 Artifact 入版控**（僅方案 B 適用）：commit 這份 JSON，或 `.gitignore` 排除？
5. 若選方案 B：是否同意「對真實開發 DB 執行只讀查詢取得完整歷史資料」這件事本身
   （執行前仍會依 RISK-013 協定先呈報綁定確認）？

裁決後才會開始動 `src/`／新增檔案。
