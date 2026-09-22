# UG-G1-SB3 Gate B 送審文件：模型競技排行榜動態化（DRIFT-008／DRIFT-018／DEC-020）

> **性質**：`gate-submit` skill 六項強制產出的整合文件。**不是** commit 授權本身——
> commit 授權留待 PO 讀完本文件後另行決定。本次未執行 `git add`／`git commit`。
> **執行期間**：2026-08-25（Gate A 提案與裁決、步驟 3 實作）～2026-08-26（三輪程式碼複閱
> 與缺陷修正、RISK-013 綁定確認、PO 最終裁決）
> **狀態**：步驟 0～6 全數完成；真實 artifact **尚未產出**——資料量不足，PO 裁示本次
> 不執行 `scripts/generate_tournament_artifact.py`，留待未來資料量足夠時再說；
> `src/`、`app.py`、`tests/`、`doc/evidence/`、`doc/governance/` 變更尚未 commit

---

## 0. 步驟 0～6 完整回顧

| 步驟 | 內容 | 完成日期 | 證據位置 |
|------|------|---------|---------|
| Gate A | 提案撰寫，含 §3.1（範圍選項 A/B）、§3.2（DRIFT-018 歸屬修正）兩項核心裁決請求 | 2026-08-25 | `SB3_GATE_A_PROPOSAL.md` |
| PO 裁決 | 核准方案 B（實際執行評估器產出真實 artifact）+ 4 項附帶裁決：DRIFT-018 歸屬修正、artifact 欄位採完整輸出、artifact 入版控、對真實 DB 唯讀查詢本身核准（比照升一級：程式碼複閱 + RISK-013） | 2026-08-25 | 對話紀錄；落實於 DEC-020 |
| 步驟 3 實作 | `load_tournament_results()`／`render_tournament_leaderboard(data, mode)`／`app.py` 呼叫處／9 個讀取渲染測試；草擬 `scripts/generate_tournament_artifact.py`（唯讀自我稽核） | 2026-08-25 | 本文件 §1 |
| 程式碼複閱第一輪 | 審查員以合成資料（不連 DB）重現 `label_end_date`／`trade_date` 型別不一致的既有 bug（SB1 起即存在，SB3 首次踩到）；另指出 `EMBARGO_DAYS=1` 與「沿用預設」的溝通不一致 | 2026-08-25 | 本文件 §7 |
| 缺陷修正一 | 新增 `_stringify_date_columns()` 統一轉換兩欄位；補 3 個回歸測試（含 known-FAIL 示範）；`EMBARGO_DAYS` 改回類別預設 `0` | 2026-08-25 | 本文件 §1／§7 |
| RISK-013 綁定確認 | `DBWriter().db_config` 解析呈報（`host=localhost`／`port=5432`／`database=postgres`），PO 確認為真實開發 DB（非隔離臨時 DB） | 2026-08-25 | 對話紀錄 |
| 程式碼複閱第三輪 | 審查員發現「`leaderboard` 是否為空」判斷不了「零 Fold 但滿版零分排行榜」的情境，要求補強真正有效的資料量防線 | 2026-08-26 | 本文件 §7 |
| 缺陷修正二 | 新增 `check_sufficient_data()`，在 `evaluate_tournament()` 之前檢查唯一交易日數；補 4 個測試（含 known-FAIL 與端到端合成資料驗證）；實測證實舊防線確有此缺陷 | 2026-08-26 | 本文件 §1／§7 |
| PO 最終裁決 | 本次不真正執行 `generate_tournament_artifact.py`——目前資料量不足以支撐 `WalkForwardSplitter` 預設 window，SB3 僅交付「讀取機制＋防線」，真實 artifact 留待未來 | 2026-08-26 | 對話紀錄 |
| §7 文件同步 | `DECISIONS.md` 新增 DEC-020（`Proposed`）；`DOCUMENT_DRIFT_REMEDIATION.md` 更新 DRIFT-018 歸屬（UG-G1-SB2 → UG-G1-SB3）；`TRACEABILITY.md` 新增追溯列；`PROJECT_STATUS.md` 更新 SB3 進度 | 2026-08-26 | 本文件 §1 |
| 步驟 6 | 本文件（Gate B 送審） | 2026-08-26 | 本檔 |

**核心決策（DEC-020，PO 2026-08-25 核准方案 B）**：既有的 `MLEvaluator.evaluate_tournament()`
評估引擎不依賴 Gate 3 尚未完成的部分即可獨立執行，維持 Master Plan 原範圍（僅讀取機制）
只是把「假數字」換成「什麼都沒有」，對 CRITICAL 等級的 DRIFT-018 而言不是實質修正；
因此核准本次一併執行評估器、產出真實 artifact 並直接 commit 進版控。**實際結果**：
三輪程式碼複閱找出並修正兩個真實缺陷後，PO 判斷目前資料量不足，裁示本次不真正執行——
`load_tournament_results()` 顯示 `DataMode.EMPTY`「尚未完成模型競技」正確反映現況，
不是繞過驗收。

---

## 1. 完整 Diff（最終全貌，已包含 PO 裁決後的 SDD 同步與 DEC-020 APPROVED）

**檔案清單**（10 modified + 4 new，463 insertions(+), 22 deletions(-)）：

```
 app.py                                        |   7 +-
 doc/evidence/DECISIONS.md                     | 101 ++++++++++++++++++++++++++
 doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md    |  15 +++-
 doc/evidence/TRACEABILITY.md                  |   1 +
 doc/governance/PROJECT_STATUS.md              |   3 +-
 doc/spec/SDD_Financial_Sentiment_System_v1.md |   7 +-
 src/ui/components.py                          |  85 +++++++++++++++++++---
 src/ui/data_loader.py                         |  83 ++++++++++++++++++++-
 tests/test_time_series_split.py               |  82 +++++++++++++++++++++
 tests/test_ui_contracts.py                    | 101 ++++++++++++++++++++++++++
 10 files changed, 463 insertions(+), 22 deletions(-)
```

```
 + 4 個新檔（untracked，不包含於下方 diff 區塊）：
   doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md（176 行）
   doc/upgrade/gates/SB3_GATE_B_SUBMISSION.md（本檔）
   scripts/generate_tournament_artifact.py（170 行，未執行）
   tests/test_generate_tournament_artifact.py（110 行）
```

**重跑指令**：`git diff -- app.py doc/evidence/DECISIONS.md doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md doc/evidence/TRACEABILITY.md doc/governance/PROJECT_STATUS.md doc/spec/SDD_Financial_Sentiment_System_v1.md src/ui/components.py src/ui/data_loader.py tests/test_time_series_split.py tests/test_ui_contracts.py`
（工作區尚未 staged，此指令即可重現下方全部內容）

<details>
<summary>完整 diff 內容（點擊展開）</summary>

```diff
diff --git a/app.py b/app.py
index 63757cd..4fdf611 100644
--- a/app.py
+++ b/app.py
@@ -14,6 +14,7 @@ from src.ui.data_loader import (
     get_champion_predictor,
     load_ai_discovered_keywords,
     load_thematic_radar_data,
+    load_tournament_results,
     DataMode,
 )
 from src.ui.charts import (
@@ -145,11 +146,13 @@ def main():
     df_features, features_mode = load_stock_features(selected_stock, days=selected_days)
     df_all_history, history_mode = load_stock_features(selected_stock, days=90)
     df_articles, articles_mode = load_stock_articles(selected_stock, limit=25)
+    tournament_data, tournament_mode = load_tournament_results()
 
     # 全域來源狀態追蹤：本次頁面渲染中各資料來源的 DataMode，供 Sidebar 彙總顯示。
     st.sidebar.caption(
         f"• **本次資料來源**：特徵 {_MODE_LABEL[features_mode]} ｜ 文章 {_MODE_LABEL[articles_mode]} "
-        f"｜ AI熱詞 {_MODE_LABEL[keywords_mode]} ｜ 題材雷達 {_MODE_LABEL[radar_mode]}"
+        f"｜ AI熱詞 {_MODE_LABEL[keywords_mode]} ｜ 題材雷達 {_MODE_LABEL[radar_mode]} "
+        f"｜ 模型競技 {_MODE_LABEL[tournament_mode]}"
     )
 
     # KPI 卡片、預測面板與主圖表均需要「有真正可用的特徵矩陣」——
@@ -270,7 +273,7 @@ def main():
     # ----------------------------------------------------
     # 9. 8 組平行對照實驗橫向排行榜 (Tournament Leaderboard)
     # ----------------------------------------------------
-    render_tournament_leaderboard()
+    render_tournament_leaderboard(tournament_data, mode=tournament_mode)
 
     st.markdown("---")
 
diff --git a/doc/evidence/DECISIONS.md b/doc/evidence/DECISIONS.md
index 7c98959..65f5bf7 100644
--- a/doc/evidence/DECISIONS.md
+++ b/doc/evidence/DECISIONS.md
@@ -1287,3 +1287,104 @@ class DataMode(Enum):
 `doc/upgrade/gates/SB2_GATE_A_PROPOSAL.md` §3；
 `doc/upgrade/gates/SB2_STEP3_IMPLEMENTATION_REPORT.md`
 
+
+## DEC-020：模型競技排行榜動態化（Artifact-Driven Tournament Leaderboard）
+
+- 日期：2026-08-26
+- 狀態：`APPROVED`（PO 於 Gate B 送審文件複查後核准，2026-08-26）
+- 觸發 Gate：UG-G1-SB3
+- 編號說明：`SYSTEM_UPGRADE_MASTER_PLAN.md` §15.1 原僅預留 DEC-010～DEC-019 對應各 SB，
+  UG-G1-SB3 當時未分配編號；本決策取用下一個未使用編號 DEC-020，DEC-019
+  仍保留給 UG-G2-SB7（Batch ETL Architecture），未互相衝突。
+
+### Context（背景）
+
+`src/ui/components.py:166-184`（`render_tournament_leaderboard`）8 組模型競技數據為字面常數，
+不接受任何參數，是唯一未受 DEC-012 DataMode 約束的資料展示區塊（DRIFT-008）。
+DRIFT-018（CRITICAL）進一步指出這 8 個常數存在三個互相獨立的矛盾：排名與自身數字牴觸、
+同一實作被記錄為兩個不同分數、無任何實驗產出物連結。DRIFT-018 原歸屬 UG-G1-SB2，
+但 SB2（已於 2026-08-25 CLOSED）僅完成「標註為未經驗證展示值」的標籤化處理，
+三個矛盾本身未修正。
+
+`SB3_GATE_A_PROPOSAL.md` 提案時另外發現：`src/ml/evaluator.py` 的
+`MLEvaluator.evaluate_tournament()` 已是可執行的真實 8 組實驗評估器（4 演算法 × 2 特徵集，
+跑在 SB1 修正的 Purged Walk-Forward 上），且其所需的 `target_up_down`／`target_return_1d`
+標籤已由 `feature_aggregator.append_target_labels()`（T+1 簡單標籤）產出，不依賴 Gate 3
+規劃中的 Triple-Barrier 標籤。這打破了 `SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 UG-G1-SB3
+Brief 原本「模型競技本身列為 Out of Scope、Gate 3 完成前排行榜必為空」的前提。
+
+### Alternatives Considered（考慮方案）
+
+`SB3_GATE_A_PROPOSAL.md` §3.1：
+
+- **方案 A**：維持 Master Plan 原範圍，僅新增讀取機制；無 artifact 時顯示 EMPTY。
+  DRIFT-018 三個矛盾僅解決 (3)（無 artifact 連結），(1)(2) 因排行榜不顯示而被繞過，非解決。
+- **方案 B**：一併執行評估器，產出真實 artifact，實際解決三個矛盾。
+  代價：需對真實開發 DB 執行只讀查詢取得完整歷史資料（非 SB1/SB2 慣用之隔離臨時 DB）。
+
+### Decision（決策）
+
+**採方案 B**（PO 2026-08-25 核准），另同時核准四項裁決：
+
+1. DRIFT-018 歸屬列由 UG-G1-SB2 改記為 UG-G1-SB3（已落實於 `DOCUMENT_DRIFT_REMEDIATION.md`）。
+2. Artifact 欄位採用 `evaluate_tournament()` 現有完整輸出（`leaderboard`／`alpha_attribution`／
+   `champion_model_name`／`champion_score`），不採 Master Plan 原提案較窄的欄位集合。
+3. Artifact JSON（`models/artifacts/tournament_results.json`）產生後**直接 commit 進版控**
+   （作品集展示用途，非 `.gitignore` 排除的 build 產物）。
+4. 對真實開發 DB 執行只讀查詢取得完整歷史資料本身獲得核准，執行前依 RISK-013 協定呈報
+   綁定確認，且比照 SB1/SB2 隔離臨時 DB 慣例升一級——`scripts/generate_tournament_artifact.py`
+   完整程式碼須先交審查員複閱，確認全程唯讀後才可執行。
+
+**實際執行結果（2026-08-26）**：程式碼複閱與 RISK-013 綁定確認流程已完成，
+但複閱過程中審查員以合成資料（不連 DB）重現一個既有 bug（見 §7 known-FAIL 表）；
+修正後審查員進一步指出資料量防線設計缺陷並要求補強（同上）。**修正完成後，
+PO 決定本次不真正執行該腳本**——目前可用歷史資料量不足以支撐
+`WalkForwardSplitter` 預設 window（`train_window_size=60 + test_window_size=20`），
+真正執行會被腳本新增的 `check_sufficient_data()` 防線正確擋下。SB3 這次僅交付
+「讀取機制＋防線」，實際產出真實 artifact 留待未來資料量足夠時再執行。
+
+### Rationale（理由）
+
+方案 B 直接解決 DRIFT-018 的核心問題——虛構或無依據的展示數字，與 DEC-012 建立的
+「不以假資料撐場面」原則一致。既然評估引擎已存在且可獨立於 Gate 3 其餘未完成部分執行，
+維持方案 A 只是把「假數字」換成「什麼都沒有」，對 CRITICAL 等級的漂移而言不是實質修正。
+
+### Trade-offs（取捨）
+
+- 真實 artifact 尚未產出前，排行榜區塊會持續顯示 EMPTY「尚未完成模型競技」，
+  犧牲畫面完整性——PO 已權衡並接受（見 Context 段落之「實際執行結果」）。
+- Artifact 產生腳本觸碰真實開發 DB（唯讀），承擔比 SB1/SB2 隔離臨時 DB 更高的操作風險，
+  以加倍的複閱／確認流程（程式碼複閱 + RISK-013 綁定確認）換取。
+- Artifact commit 進版控後，`models/artifacts/tournament_results.json` 的正確性
+  取決於執行當下的資料品質與樣本量，非可持續自動更新——若未來需要排程重跑，
+  屬另一個 SB 的範圍（`SB3_GATE_A_PROPOSAL.md` §6 已明確排除）。
+
+### Affected Components（影響範圍）
+
+`src/ui/data_loader.py`（`load_tournament_results`、`_stringify_date_columns`）、
+`src/ui/components.py`（`render_tournament_leaderboard(data, mode)`）、`app.py`
+（呼叫處解包與 Sidebar 追蹤）、`scripts/generate_tournament_artifact.py`（新檔，未執行）、
+`doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-018 歸屬修正）
+
+### Verification（驗證）
+
+- [x] 189/189 tests PASS（container，含 9 個新增於讀取/渲染契約、3 個 `label_end_date`
+      型別 bug 回歸測試、4 個資料量防線測試）
+- [x] `label_end_date`／`trade_date` 型別不一致的既有 bug（SB1 起即存在，SB3 首次踩到）
+      已修正並有 known-FAIL 回歸測試
+- [x] 資料量防線（`check_sufficient_data`）已加入並有 known-FAIL 回歸測試；
+      經實測證實「leaderboard 是否為空」判斷不了零 Fold 但滿版零分排行榜的情境
+- [ ] 真實 artifact 尚未產出（`models/` 目錄不存在）——本項 `NOT VERIFIED`，
+      屬有意延後而非遺漏
+
+### Remaining Risks（剩餘風險）
+
+- 真實 artifact 產出後，DRIFT-018 矛盾 (2)（lightgbm/xgboost 同分）是否真的消失，
+  仍待實測確認，本次僅為理論推斷（container 內兩者為不同真實實作）。
+- `scripts/generate_tournament_artifact.py` 从未在真實 DB 上執行過，其 Panel 大小／
+  唯一交易日數等實際數字未知，執行時是否仍會被 `check_sufficient_data` 擋下待實測。
+
+### 證據文件
+
+`doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md`；`doc/upgrade/gates/SB3_GATE_B_SUBMISSION.md`
+
diff --git a/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md b/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
index 192875d..1b641ea 100644
--- a/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
+++ b/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
@@ -46,7 +46,18 @@
 **(1) 排名與自身數字牴觸** —— 冠軍 Random Forest（Macro F1 `0.5820`／命中率 `58.4%`／報酬 `+8.2%`）在**全部三個指標**上同時輸給亞軍 LightGBM（`0.5910`／`59.2%`／`+9.6%`）與季軍 XGBoost（`0.5860`／`58.8%`／`+8.9%`）。
 **(2) 同一實作有兩個分數** —— 依 DRIFT-015，host 上 `lightgbm` 與 `xgboost` 回傳同一個 `_FallbackTreeEnsembleClassifier`（實測 `type(a) is type(b) == True`），同一段程式碼卻被記錄為 `0.5910` 與 `0.5860`。
 **(3) 無任何實驗產出物連結** —— 全部為 UI 檔內的字面常數；`render_tournament_leaderboard` 不讀取任何檔案、JSON 或 artifact（實測確認）。 | `VERIFIED — 三項矛盾逐一實測` | **標註原則（PO 2026-08-24 裁示）**：不得標為「含洩漏」—— 該說法預設它們是有已知瑕疵的**真實量測**，但目前沒有任何證據支持它們曾被量測出來。**應標註為「未經驗證的展示值，證據待補」**。本專案不宣稱這些數字是捏造的（無證據），但**主張它們是量測結果的一方負舉證責任，而目前舉不出來**。
-**歸屬**：UG-G1-SB2（DRIFT-009 Demo/Real 分離）——由該批次決定這些值是移除、標為 DEMO、或改由 artifact 讀取。UG-G1-SB1 **不修改** `components.py`，僅於文件同步時登錄本項。 | UG-G1-SB2 |
+**歸屬修正（PO 2026-08-25 裁示）**：原歸屬 UG-G1-SB2 僅完成「標註為未經驗證展示值」的標籤化處理，
+三個矛盾本身未修正；SB2 已於 2026-08-25 CLOSED。實際修正改記於 **UG-G1-SB3**。
+
+**UG-G1-SB3 修正現況（2026-08-26，尚未 commit）**：新增 `load_tournament_results()`／
+`render_tournament_leaderboard(data, mode)`，排行榜資料源改為讀取
+`models/artifacts/tournament_results.json`（由 `MLEvaluator.evaluate_tournament()` 產出）。
+矛盾 (1)(3) **結構上已消除**——不再有任何字面常數，排名邏輯改為由真實分數即時排序；
+矛盾 (2) 待真實 artifact 產出後才能實測確認（container 內 lightgbm／xgboost 是不同真實實作，
+理論上不會重現）。**真實 artifact 尚未產出**——`models/` 目錄不存在，資料量不足以支撐
+`WalkForwardSplitter` 預設 window（見 `SB3_GATE_A_PROPOSAL.md` §3.1 方案 B 與
+`SB3_GATE_B_SUBMISSION.md` §6 NOT VERIFIED 項）；目前 UI 正確顯示 `DataMode.EMPTY`
+「尚未完成模型競技」，不是繞過驗收。 | UG-G1-SB3 |
 ・類別 `StationaryFeaturesAndPanelTests`
 ・4 個測試 `test_stationary_features_computation`(L51)、`test_target_label_deadband_filtering`(L66)、`test_aggregate_cross_sectional_dataset`(L80)、`test_trainer_fit_with_stationary_features`(L96)
 ・符號 `STATIONARY_MULTIMODAL_FEATURE_COLS`（現行程式碼中不存在；現行為 `ALL_MULTIMODAL_FEATURE_COLS`）
@@ -86,7 +97,7 @@ lock 只保證「照 lock 安裝會得到已驗證的版本組合」，並未修
 | UG-G1-SB5 + UG-G3-SB3/SB7 | DRIFT-015 | DEC-007 證據基礎標註 + 容器內重跑 tournament |
 | GOV-03（緩解）／待 PO 指定（根治）| DRIFT-016 | `requirements.lock.txt` 已加入為緩解；意圖檔約束補強待 PO 決定 |
 | 已處理（2026-08-23）| DRIFT-017 | 孤兒 bytecode 已清除並登錄；版控外工作先例已記錄 |
-| UG-G1-SB2 | DRIFT-018 | 排行榜三項矛盾；標註為「未經驗證的展示值」而非「含洩漏」 |
+| UG-G1-SB3（讀取機制已完成，待真實 artifact；待 commit） | DRIFT-018 | 排行榜三項矛盾；歸屬由 UG-G1-SB2 修正為 UG-G1-SB3（SB2 僅標籤化，未實際修正） |
 
 ---
 
diff --git a/doc/evidence/TRACEABILITY.md b/doc/evidence/TRACEABILITY.md
index 5e3ad38..5e44bea 100644
--- a/doc/evidence/TRACEABILITY.md
+++ b/doc/evidence/TRACEABILITY.md
@@ -58,6 +58,7 @@
 | **題材情緒溢出加權特徵引擎** | 題材全系統升級 (SB-TH2) | 2.3 題材特徵邊界 | **DEC-009** (SB-TH2) | `src/transform/feature_aggregator.py`<br>`main_etl_pipeline.py` | `tests/test_thematic_feature_spillover.py` | 5 tests | `VERIFIED THIS SESSION` (Thematic) |
 | **三重查詢真實文章與空狀態透明化** | 輿情明細透明化 (SB-ART1~3) | 4.1 輿情明細架構 | **DEC-008** / REAL-ART | `src/ui/data_loader.py`<br>`src/ui/components.py` | `tests/test_real_articles_pipeline.py` | 4 tests | `VERIFIED THIS SESSION` (Real Articles) |
 | **UI 四狀態資料來源透明化（REAL/DEMO/EMPTY/ERROR）** | 稽核報告 §2；AGENTS.md §10；DRIFT-009 | 7.1 UI Demo/Real 模式分離 | **DEC-012**（UG-G1-SB2） | `src/ui/data_loader.py`（`DataMode`／`DataSourceError`）<br>`src/ui/components.py`（`render_data_mode_banner`）<br>`src/ui/charts.py`（佔位圖／浮水印）<br>`app.py`（mode 分流與全域追蹤） | `tests/test_ui_contracts.py`<br>`tests/test_operational_ux.py`<br>`tests/test_real_articles_pipeline.py`<br>`tests/schema_smoke_ui_data_loader.py`（不進正式套件） | 9 個新增測試 + 4 個 schema smoke test | `VERIFIED THIS SESSION`（`SB2_STEP3_IMPLEMENTATION_REPORT.md`；173/173 PASS；HERM runtime 攔截數 9→0；`src/` 尚未 commit） |
+| **模型競技排行榜動態化（Artifact-Driven Leaderboard）** | 稽核報告 §2；DRIFT-008；DRIFT-018 | 7.1 UI 排行榜動態化 | **DEC-020**（UG-G1-SB3） | `src/ui/data_loader.py`（`load_tournament_results`／`_stringify_date_columns`）<br>`src/ui/components.py`（`render_tournament_leaderboard(data, mode)`）<br>`app.py`（呼叫處解包）<br>`scripts/generate_tournament_artifact.py`（新檔，未執行） | `tests/test_ui_contracts.py`<br>`tests/test_time_series_split.py`（`label_end_date` 型別回歸）<br>`tests/test_generate_tournament_artifact.py`（資料量防線） | 9 個讀取/渲染測試 + 3 個型別回歸測試 + 4 個防線測試 | `VERIFIED THIS SESSION`（`SB3_GATE_B_SUBMISSION.md`；189/189 PASS；真實 artifact 尚未產出，`NOT VERIFIED`——見該文件 §6；`src/` 尚未 commit） |
 | **總計 (Total)** | - | - | **9 大核心 ADR + 7 大挑戰** | **18 大核心生產模組** | **17 大測試套件檔案** | **154 項測試** | **100% PASS (~1.80s)** |
 
 ---
diff --git a/doc/governance/PROJECT_STATUS.md b/doc/governance/PROJECT_STATUS.md
index abbd25c..30e7e4f 100644
--- a/doc/governance/PROJECT_STATUS.md
+++ b/doc/governance/PROJECT_STATUS.md
@@ -35,6 +35,7 @@
 | **UG-Gate-1** | **已核准，採逐 SB 授權** | — |
 | └ **UG-G1-SB1** Purged Walk-Forward | **CLOSED**（2026-08-25 PO 核准結案） | commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`；證據見 `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_STEP4_AFTER_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_GATE_B_SUBMISSION.md`；DEC-011、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-012）已同步 |
 | └ **UG-G1-SB2** UI Demo/Real 模式分離 | **CLOSED**（2026-08-25 PO 核准結案；DEC-012 方案 B 裁決） | commit `414fcc81fccde57d84e883b4a44a9b0e50465500`；證據見 `doc/upgrade/gates/closed/SB2_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB2_STEP3_IMPLEMENTATION_REPORT.md`、`doc/upgrade/gates/closed/SB2_STEP0_4_5_RECORD.md`、`doc/upgrade/gates/closed/SB2_GATE_B_SUBMISSION.md`；DEC-012、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-009／HERM-A/B/C/E）已同步；過程中發現並修復 ERROR 模式 `StreamlitDuplicateElementId` 當機 bug |
+| └ **UG-G1-SB3** 模型競技排行榜動態化 | Gate A 已核准（方案 B + 4 項附帶裁決）；**步驟 0～6 全數完成，送 Gate B 審查中**；真實 artifact **尚未產出**（資料量不足，PO 裁示暫不執行 `scripts/generate_tournament_artifact.py`） | `doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md`、`SB3_GATE_B_SUBMISSION.md`；DEC-020（`APPROVED`，2026-08-26）；DRIFT-008／DRIFT-018 歸屬修正；SDD UI 章節已同步；`src/`、`doc/evidence/`、`doc/spec/` 變更待 commit |
 
 RISK-001 `Accept`、RISK-010 `Defer`（至 Gate 3）、RISK-012 `Mitigate`、
 RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RISKS.md`。
@@ -43,7 +44,7 @@ RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RI
 
 | 項目 | 狀態 |
 |------|------|
-| **UG-G1-SB3 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權 |
+| **UG-G1-SB4 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權（SB3 已核准 Gate A，見 §0.2） |
 | **UG-Gate-2、UG-Gate-3、UG-Gate-4** | **未核准，不得啟動** |
 | `database/` | 升級專案至今**一行未改** |
 
diff --git a/doc/spec/SDD_Financial_Sentiment_System_v1.md b/doc/spec/SDD_Financial_Sentiment_System_v1.md
index 4c9bdfd..911df13 100644
--- a/doc/spec/SDD_Financial_Sentiment_System_v1.md
+++ b/doc/spec/SDD_Financial_Sentiment_System_v1.md
@@ -74,9 +74,9 @@ graph TD
 #### 3. 載入層 (`src/loaders/`) - *負責與資料庫進行安全且高效的互動*
 *   **✅ `db_writer.py`**: (DBWriter): 封裝 `psycopg2` 連線邏輯與 `execute_values` 批次寫入功能，管理 `stock_prices`、`market_articles`、`sentiment_cache` 與 tracking configuration。Read methods 以 exception propagation 區分 DB failure 與 successful empty result，並驗證 cache score 是 0.0～1.0 的有限數值。
 
-#### 4. 應用與 ML 層 (`src/ml/` & `src/app/`) - *規劃中*
-*   **⏳ `model_trainer.py` (規劃中 - Phase 3)**: 從資料庫讀取價格與情緒特徵，訓練機器學習分類器 (如 Random Forest) 來預測股價趨勢，並將預測結果寫回資料庫。
-*   **⏳ `dashboard.py` (規劃中 - Phase 4)**: 使用 Streamlit 建立前端 BI 儀表板，將資料庫中的結果進行視覺化圖表呈現。
+#### 4. 應用與 ML 層 (`src/ml/` & `src/ui/`)
+*   **✅ `model_trainer.py`**: 從資料庫讀取價格與情緒特徵，訓練機器學習分類器（Logistic Regression／Random Forest／LightGBM／XGBoost）來預測股價趨勢；`src/ml/evaluator.py` 的 `MLEvaluator.evaluate_tournament()` 可執行 4 演算法 × 2 特徵集共 8 組平行對照實驗並產出排行榜（見下方 `app.py`／`src/ui/` 條目）。
+*   **✅ `app.py` 與 `src/ui/`（原規劃檔名 `dashboard.py`，實際實作為此路徑）**: 使用 Streamlit 建立前端終端，將資料庫中的結果進行視覺化圖表呈現。核心架構為 `DataMode` 四狀態資料來源透明化（`REAL`／`DEMO`／`EMPTY`／`ERROR`，DEC-012）：`src/ui/data_loader.py` 各公開函式回傳 `(value, DataMode)` 元組，`src/ui/components.py`／`src/ui/charts.py` 依 mode 渲染對應橫幅／浮水印／佔位圖表，DB 連線失敗時**不自動退回模擬資料**，僅顯示明確錯誤說明。模型競技排行榜（`render_tournament_leaderboard`）已改為從 `models/artifacts/tournament_results.json` artifact 讀取（DEC-020），不再是 UI 層字面常數；artifact 尚未產出時顯示 `EMPTY`「尚未完成模型競技」。
 
 ### 📁 專案進入點與自動化指令
 *   **✅ `main_etl_pipeline.py`**: (ETLPipelineManager): 系統總指揮官 (Orchestrator)。負責實例化所有模組並注入資源，定義資料流動的順序 (Extract -> Transform -> Load)。NLP pending rows 以 `sentiment_score IS NULL` 選取；只有 processor 正常回傳後才呼叫 article score update，processor failure 會停止目前 invocation。
@@ -232,3 +232,4 @@ Gate 5 採用 DEC-006 與 `doc/research/RESEARCH_REQUIREMENTS.md`。將行為金
 4.  **Strict NLP Checkpointing（嚴格 NLP 檢查點）**：DB read failure、SnowNLP 非預期 exception 與不完整／無效 Gemini response 會停止目前 batch；只有完整 processor success 後才更新 article score。此行為有 deterministic unit／mock evidence，但 real PostgreSQL／Gemini／End-to-End recovery 尚未驗證。
 5.  **部分冪等寫入基礎**：目前使用 `stock_prices` 的 `(stock_id, trade_date)` conflict update、`market_articles.url` conflict ignore 與 cache title conflict ignore。這些規則降低特定 duplicate insert 風險，但不保證所有資料來源、資料契約或內容品質問題都被排除。
 6.  **AI 題材概念股溢出與雷達連動 (Thematic Trends & Spillover)**：建立 1-to-N 概念股知識映射表，透過動態加權演算法將產業題材情緒溢出至成分股特徵矩陣中，並於 Streamlit 實現一鍵選股秒速預測連動。
+7.  **UI 資料來源透明化與排行榜動態化 (DataMode Architecture & Artifact-Driven Leaderboard)**：`DataMode`（`REAL`／`DEMO`／`EMPTY`／`ERROR`，DEC-012）貫穿 KPI 卡片、圖表、AI 預測面板、文章明細表、AI 熱詞、題材雷達與模型競技排行榜共 7 個資料展示區塊；`ERROR` 時**不自動退回模擬資料**，僅顯示「⚠️ 資料來源目前無法連線」，`demo=True` 為 `DEMO` 模式的唯一顯式入口（求職作品集定位下的刻意取捨：真實技術能力優先於畫面完整性）。8 組平行對照實驗排行榜（4 演算法 × 2 特徵集）改由 `MLEvaluator.evaluate_tournament()` 產出並持久化為 JSON artifact（DEC-020），UI 僅讀取，不再是頁面內字面常數；無 artifact 時顯示 `EMPTY`「尚未完成模型競技」，不以假資料撐場面。
diff --git a/src/ui/components.py b/src/ui/components.py
index c88ccf8..dd8286c 100644
--- a/src/ui/components.py
+++ b/src/ui/components.py
@@ -163,26 +163,87 @@ def render_prediction_panel(
                 )
 
 
-def render_tournament_leaderboard() -> None:
+_TOURNAMENT_RANK_LABELS = ["🏆 冠軍", "🥈 亞軍", "🥉 季軍", "第 4 名"]
+_TOURNAMENT_MODEL_DISPLAY = {
+    "logistic_regression": "Logistic Regression",
+    "random_forest": "Random Forest",
+    "lightgbm": "LightGBM",
+    "xgboost": "XGBoost",
+}
+
+
+def render_tournament_leaderboard(data: Optional[Dict[str, Any]] = None, mode: DataMode = DataMode.EMPTY) -> None:
     """
     渲染 8 組平行對照實驗多模型排行榜 (Multi-Model Tournament Leaderboard)。
+
+    資料來源見 `data_loader.load_tournament_results()`（UG-G1-SB3；DRIFT-008／DRIFT-018）。
+    mode=EMPTY 時顯示「尚未完成模型競技」而非假資料；mode=ERROR 時顯示錯誤橫幅；
+    mode=REAL 時渲染 `MLEvaluator.evaluate_tournament()` 產出的真實排行榜與 Alpha 歸因。
     """
     st.markdown("### 🏆 8 組平行對照實驗競技排行榜 (Multi-Model Leaderboard)")
     st.caption("透過 Walk-Forward 時序交叉驗證，量化驗證社群情緒特徵在 4 大演算法下的 Alpha 增益 (ΔAlpha)。")
 
-    data = [
-        {"排名": "🏆 冠軍", "模型演算法": "Random Forest", "特徵集": "多模態 (18 Feat)", "Macro F1": "0.5820", "方向命中率": "58.4%", "累積策略報酬": "+8.2%", "ΔAlpha 增益": "+4.7%"},
-        {"排名": "🥈 亞軍", "模型演算法": "LightGBM", "特徵集": "多模態 (18 Feat)", "Macro F1": "0.5910", "方向命中率": "59.2%", "累積策略報酬": "+9.6%", "ΔAlpha 增益": "+5.5%"},
-        {"排名": "🥉 季軍", "模型演算法": "XGBoost", "特徵集": "多模態 (18 Feat)", "Macro F1": "0.5860", "方向命中率": "58.8%", "累積策略報酬": "+8.9%", "ΔAlpha 增益": "+5.1%"},
-        {"排名": "第 4 名", "模型演算法": "Logistic Regression", "特徵集": "多模態 (18 Feat)", "Macro F1": "0.5480", "方向命中率": "54.2%", "累積策略報酬": "+4.8%", "ΔAlpha 增益": "+2.7%"},
-        {"排名": "控制組", "模型演算法": "LightGBM", "特徵集": "純價量 (9 Feat)", "Macro F1": "0.5410", "方向命中率": "54.0%", "累積策略報酬": "+4.1%", "ΔAlpha 增益": "基準線"},
-        {"排名": "控制組", "模型演算法": "XGBoost", "特徵集": "純價量 (9 Feat)", "Macro F1": "0.5380", "方向命中率": "53.9%", "累積策略報酬": "+3.8%", "ΔAlpha 增益": "基準線"},
-        {"排名": "控制組", "模型演算法": "Random Forest", "特徵集": "純價量 (9 Feat)", "Macro F1": "0.5340", "方向命中率": "53.8%", "累積策略報酬": "+3.5%", "ΔAlpha 增益": "基準線"},
-        {"排名": "控制組", "模型演算法": "Logistic Regression", "特徵集": "純價量 (9 Feat)", "Macro F1": "0.5120", "方向命中率": "51.5%", "累積策略報酬": "+2.1%", "ΔAlpha 增益": "基準線"},
-    ]
-    df_lb = pd.DataFrame(data)
+    if mode == DataMode.EMPTY:
+        st.markdown(
+            """
+            <div style="background-color: #1E222D; border: 1px dashed #4E5D78; border-radius: 8px;
+                        padding: 18px 24px; text-align: center; margin: 15px 0;">
+                <span style="color: #848E9C;">💡 尚未完成模型競技——執行
+                <code>scripts/generate_tournament_artifact.py</code> 後即可顯示真實結果</span>
+            </div>
+            """,
+            unsafe_allow_html=True
+        )
+        return
+
+    if mode != DataMode.REAL or not data or not data.get("leaderboard"):
+        render_data_mode_banner(mode if mode != DataMode.REAL else DataMode.ERROR, "模型競技排行榜")
+        return
+
+    rows = data["leaderboard"]
+    mm_rows = sorted(
+        (r for r in rows if "MultiModal" in r.get("feature_set", "")),
+        key=lambda r: r.get("macro_f1", 0.0) * 0.7 + r.get("directional_hit_ratio", 0.0) * 0.3,
+        reverse=True,
+    )
+    tech_rows = [r for r in rows if "PureTechnical" in r.get("feature_set", "")]
+    alpha = data.get("alpha_attribution", {})
+
+    table_rows = []
+    for i, r in enumerate(mm_rows):
+        rank_label = _TOURNAMENT_RANK_LABELS[i] if i < len(_TOURNAMENT_RANK_LABELS) else f"第 {i + 1} 名"
+        model = r.get("model_name", "")
+        delta_f1 = alpha.get(model, {}).get("delta_macro_f1")
+        table_rows.append({
+            "排名": rank_label,
+            "模型演算法": _TOURNAMENT_MODEL_DISPLAY.get(model, model),
+            "特徵集": r.get("feature_set", ""),
+            "Macro F1": f"{r.get('macro_f1', 0.0):.4f}",
+            "方向命中率": f"{r.get('directional_hit_ratio', 0.0) * 100:.1f}%",
+            "累積策略報酬": f"{r.get('cumulative_return', 0.0) * 100:+.1f}%",
+            "ΔAlpha 增益": f"{delta_f1 * 100:+.1f}%" if delta_f1 is not None else "—",
+        })
+    for r in tech_rows:
+        model = r.get("model_name", "")
+        table_rows.append({
+            "排名": "控制組",
+            "模型演算法": _TOURNAMENT_MODEL_DISPLAY.get(model, model),
+            "特徵集": r.get("feature_set", ""),
+            "Macro F1": f"{r.get('macro_f1', 0.0):.4f}",
+            "方向命中率": f"{r.get('directional_hit_ratio', 0.0) * 100:.1f}%",
+            "累積策略報酬": f"{r.get('cumulative_return', 0.0) * 100:+.1f}%",
+            "ΔAlpha 增益": "基準線",
+        })
+
+    df_lb = pd.DataFrame(table_rows)
     st.dataframe(df_lb, use_container_width=True, hide_index=True)
 
+    champion = data.get("champion_model_name", "")
+    st.caption(
+        f"🏆 綜合冠軍模型：**{_TOURNAMENT_MODEL_DISPLAY.get(champion, champion)}**"
+        f"（綜合分數 {data.get('champion_score', 0.0):.4f} = Macro F1 × 0.7 + 方向命中率 × 0.3）"
+    )
+
 
 def render_raw_article_table(df_articles: pd.DataFrame, mode: DataMode = DataMode.REAL) -> None:
     """
diff --git a/src/ui/data_loader.py b/src/ui/data_loader.py
index 601752f..562af0e 100644
--- a/src/ui/data_loader.py
+++ b/src/ui/data_loader.py
@@ -1,3 +1,4 @@
+import json
 import logging
 import os
 from enum import Enum
@@ -54,6 +55,18 @@ _STOCK_ARTICLE_COLUMNS: List[str] = [
     "sentiment_label", "push_count", "source", "url",
 ]
 
+# 模型競技排行榜 artifact（UG-G1-SB3, DRIFT-008／DRIFT-018）：
+# 由 scripts/generate_tournament_artifact.py 一次性產出，UI 僅讀取，不在頁面渲染時即時計算。
+_TOURNAMENT_ARTIFACT_PATH: str = os.path.join(
+    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
+    "models", "artifacts", "tournament_results.json"
+)
+_TOURNAMENT_REQUIRED_KEYS = {"leaderboard", "alpha_attribution", "champion_model_name", "champion_score"}
+_TOURNAMENT_LEADERBOARD_ROW_KEYS = {
+    "experiment_id", "model_name", "feature_set", "macro_f1", "accuracy", "roc_auc",
+    "directional_hit_ratio", "cumulative_return", "sharpe_ratio", "max_drawdown",
+}
+
 # DEMO 專用內容（僅在 demo=True 時使用，不再作為 ERROR 的自動 fallback）
 DEFAULT_AI_KEYWORDS: List[str] = [
     "矽光子 (CPO)",
@@ -233,6 +246,27 @@ def generate_mock_ptt_articles(stock_id: str, limit: int = 20) -> pd.DataFrame:
     return pd.DataFrame(records)
 
 
+def _stringify_date_columns(df_features: pd.DataFrame) -> pd.DataFrame:
+    """
+    將 trade_date 與 label_end_date（若存在）統一轉為 YYYY-MM-DD 字串。
+
+    兩欄位必須維持**同一型別**——`label_end_date` 由
+    `FeatureAggregator.generate_target_labels()` 以 `groupby('stock_id')['trade_date'].shift(...)`
+    產生，若只轉換 `trade_date` 而漏轉 `label_end_date`，兩者會分別是 str 與 pandas.Timestamp。
+    這個型別不一致本身不會立即出錯——它會潛伏到 `WalkForwardSplitter.split()` 逐列比較
+    `label_end_date >= test_start_date` 時才以 TypeError 現形。此函式存在的理由就是確保
+    這兩欄位在同一個地方被同時轉換，不會再各自轉、各自忘。
+
+    NaT（`label_end_date` 在每檔股票最後 `label_horizon` 列必然出現）會被
+    `.dt.strftime()` 轉為 None，與 `WalkForwardSplitter` 對 `pd.isna(v)` 的既有防呆一致。
+    """
+    df_features = df_features.copy()
+    df_features['trade_date'] = pd.to_datetime(df_features['trade_date']).dt.strftime('%Y-%m-%d')
+    if 'label_end_date' in df_features.columns:
+        df_features['label_end_date'] = pd.to_datetime(df_features['label_end_date']).dt.strftime('%Y-%m-%d')
+    return df_features
+
+
 def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optional[pd.DataFrame]:
     """
     從 PostgreSQL 撈取真實股價與文章資料，並透過 FeatureAggregator 即時推導完整 18 欄位特徵矩陣。
@@ -308,8 +342,7 @@ def _fetch_real_stock_features_from_db(stock_id: str, days: int = 60) -> Optiona
         # 5. 生成目標標籤 target_return_1d / target_up_down
         df_features = aggregator.generate_target_labels(df_features)
         
-        # 日期轉型為字串 YYYY-MM-DD
-        df_features['trade_date'] = pd.to_datetime(df_features['trade_date']).dt.strftime('%Y-%m-%d')
+        df_features = _stringify_date_columns(df_features)
         
         # 僅保留最近 days 天
         if len(df_features) > days:
@@ -591,3 +624,49 @@ def load_thematic_radar_data(demo: bool = False) -> Tuple[List[Dict[str, Any]],
     if not radar_list:
         return [], DataMode.EMPTY
     return radar_list, DataMode.REAL
+
+
+def load_tournament_results(artifact_path: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], DataMode]:
+    """
+    載入 8 組平行對照實驗（4 演算法 × 2 特徵集）模型競技排行榜結果
+    （UG-G1-SB3；DRIFT-008 靜態排行榜改動態、DRIFT-018 三項矛盾修正）。
+
+    資料來源為 `MLEvaluator.evaluate_tournament()` 產出並持久化的 JSON artifact
+    （見 `scripts/generate_tournament_artifact.py`），UI 僅讀取，不在頁面渲染時即時重跑訓練。
+
+    Args:
+        artifact_path: artifact 檔案路徑，預設 `models/artifacts/tournament_results.json`。
+
+    Returns:
+        (None, DataMode.EMPTY)：artifact 不存在（尚未執行過模型競技）。
+        (None, DataMode.ERROR)：artifact 存在但格式錯誤／必要欄位缺失。
+        (dict, DataMode.REAL)：成功載入，dict 含 leaderboard／alpha_attribution／
+            champion_model_name／champion_score。
+    """
+    path = artifact_path or _TOURNAMENT_ARTIFACT_PATH
+
+    if not os.path.exists(path):
+        return None, DataMode.EMPTY
+
+    try:
+        with open(path, "r", encoding="utf-8") as f:
+            payload = json.load(f)
+    except (OSError, json.JSONDecodeError) as e:
+        logger.warning(f"[DataMode.ERROR] load_tournament_results: 無法讀取或解析 {path}: {e}")
+        return None, DataMode.ERROR
+
+    if not isinstance(payload, dict) or not _TOURNAMENT_REQUIRED_KEYS.issubset(payload.keys()):
+        logger.warning(f"[DataMode.ERROR] load_tournament_results: {path} 缺少必要欄位 {_TOURNAMENT_REQUIRED_KEYS}")
+        return None, DataMode.ERROR
+
+    leaderboard = payload.get("leaderboard")
+    if not isinstance(leaderboard, list) or not leaderboard:
+        logger.warning(f"[DataMode.ERROR] load_tournament_results: {path} 的 leaderboard 為空或格式錯誤")
+        return None, DataMode.ERROR
+
+    for row in leaderboard:
+        if not isinstance(row, dict) or not _TOURNAMENT_LEADERBOARD_ROW_KEYS.issubset(row.keys()):
+            logger.warning(f"[DataMode.ERROR] load_tournament_results: {path} 的 leaderboard 列缺少必要欄位")
+            return None, DataMode.ERROR
+
+    return payload, DataMode.REAL
diff --git a/tests/test_time_series_split.py b/tests/test_time_series_split.py
index cdf55e1..c07e093 100644
--- a/tests/test_time_series_split.py
+++ b/tests/test_time_series_split.py
@@ -7,6 +7,7 @@ import pandas as pd
 
 from src.ml.time_series_split import WalkForwardSplitter
 from src.transform.feature_aggregator import FeatureAggregator
+from src.ui.data_loader import _stringify_date_columns
 
 
 class WalkForwardSplitterUnitTests(unittest.TestCase):
@@ -436,5 +437,86 @@ class PurgedWalkForwardTests(unittest.TestCase):
         )
 
 
+class StringifyDateColumnsRegressionTests(unittest.TestCase):
+    """
+    UG-G1-SB3 回歸測試：`_fetch_real_stock_features_from_db()` 曾只把 trade_date 轉為
+    字串、漏轉 label_end_date，兩欄位型別不一致（str vs. pandas.Timestamp）在
+    `WalkForwardSplitter.split()` 逐列比較 `label_end_date >= test_start_date` 時
+    以 TypeError 現形。此 bug 自 SB1 起即存在，但直到 SB3 的 artifact 產生腳本第一次
+    把 `_fetch_real_stock_features_from_db()` 的輸出接上 `split()` 才被踩到
+    （審查員以純合成資料、不連 DB 的方式重現並回報）。
+
+    本測試完全不連接 DB：以與 `_fetch_real_stock_features_from_db()` 內部相同的
+    `FeatureAggregator` 呼叫序列（`generate_daily_features` → `generate_target_labels`）
+    產生合成特徵矩陣，驗證修正後的 `_stringify_date_columns()` 讓 `split()` 可以
+    正常跑完整個生成器，不再拋出 TypeError。
+    """
+
+    def _build_synthetic_features(self) -> pd.DataFrame:
+        with redirect_stdout(io.StringIO()):
+            dates = pd.date_range("2026-07-01", periods=15, freq="B").strftime("%Y-%m-%d").tolist()
+            df_prices = pd.DataFrame({
+                "trade_date": dates,
+                "stock_id": ["2330"] * len(dates),
+                "close_price": [100.0 + i for i in range(len(dates))],
+                "volume": [1000] * len(dates),
+            })
+            df_articles = pd.DataFrame({
+                "article_id": list(range(len(dates))),
+                "fetch_keyword": ["台積電"] * len(dates),
+                "post_time": [f"{d} 10:00:00" for d in dates],
+                "sentiment_score": [0.5] * len(dates),
+            })
+            df_mapping = pd.DataFrame({
+                "keyword": ["台積電"], "stock_id": ["2330"], "market": ["TWSE"], "description": ["中文全稱"],
+            })
+
+            aggregator = FeatureAggregator()
+            df_features = aggregator.generate_daily_features(df_prices, df_articles, df_mapping)
+            df_features = aggregator.generate_target_labels(df_features)
+        return df_features
+
+    def test_stringify_date_columns_makes_trade_date_and_label_end_date_consistent_type(self):
+        """修正後兩欄位皆為 str（或 NaT 轉出的 None），不再一邊 str 一邊 Timestamp。"""
+        df_features = self._build_synthetic_features()
+        # 轉換前的真實型別非 str（FeatureAggregator 內部以 datetime.date／Timestamp 表示日期，
+        # 具體型別不是本測試重點——重點是「轉換前不是 str」，這正是型別不一致的根源）。
+        self.assertNotIsInstance(df_features["label_end_date"].iloc[0], str)
+
+        df_stringified = _stringify_date_columns(df_features)
+
+        non_null_label_end = df_stringified["label_end_date"].dropna()
+        self.assertGreater(len(non_null_label_end), 0)
+        for v in df_stringified["trade_date"]:
+            self.assertIsInstance(v, str)
+        for v in non_null_label_end:
+            self.assertIsInstance(v, str)
+
+    def test_split_does_not_raise_typeerror_after_stringify_fix(self):
+        """修正後把 _fetch_real_stock_features_from_db() 的實際輸出型別餵進 split()，能跑完不拋錯。"""
+        df_features = self._build_synthetic_features()
+        df_stringified = _stringify_date_columns(df_features)
+
+        splitter = WalkForwardSplitter(train_window_size=6, test_window_size=3, mode="rolling")
+        folds = list(splitter.split(df_stringified))  # 曾在此處拋 TypeError；修正前的重現見下方 known-FAIL 測試
+
+        self.assertGreater(len(folds), 0, "測試資料量不足以產生任何 Fold，無法驗證 Purge 比較邏輯是否執行")
+
+    def test_known_fail_unfixed_type_mismatch_raises_typeerror(self):
+        """
+        known-FAIL 示範（CLAUDE.md §9A.2）：手動重建修正前的型別不一致狀態
+        （trade_date 轉字串、label_end_date 維持 Timestamp——即修正前 _fetch_real_stock_features_from_db()
+        的真實輸出型別），證明 split() 確實會因此拋出 TypeError，本測試不是裝飾性斷言。
+        """
+        df_features = self._build_synthetic_features()
+        df_features = df_features.copy()
+        df_features["trade_date"] = pd.to_datetime(df_features["trade_date"]).dt.strftime("%Y-%m-%d")
+        # 刻意不轉換 label_end_date，重現修正前的漏轉
+
+        splitter = WalkForwardSplitter(train_window_size=6, test_window_size=3, mode="rolling")
+        with self.assertRaises(TypeError):
+            list(splitter.split(df_features))
+
+
 if __name__ == "__main__":
     unittest.main()
diff --git a/tests/test_ui_contracts.py b/tests/test_ui_contracts.py
index b64d06a..1490b3e 100644
--- a/tests/test_ui_contracts.py
+++ b/tests/test_ui_contracts.py
@@ -1,3 +1,6 @@
+import json
+import os
+import tempfile
 import unittest
 import numpy as np
 import pandas as pd
@@ -17,6 +20,7 @@ from src.ui.data_loader import (
     load_stock_articles,
     get_champion_predictor,
     load_thematic_radar_data,
+    load_tournament_results,
     _fetch_real_stock_features_from_db,
     generate_mock_ptt_articles,
     DataMode,
@@ -31,9 +35,25 @@ from src.ui.components import (
     FEATURE_DISPLAY_NAMES,
     render_thematic_radar,
     render_raw_article_table,
+    render_tournament_leaderboard,
 )
 
 
+def _valid_tournament_payload():
+    """建立一份符合 load_tournament_results 契約的最小合法 artifact 內容，供測試共用。"""
+    row_template = {
+        "experiment_id": "EXP-RF-MM", "model_name": "random_forest", "feature_set": "MultiModal (18 Feat)",
+        "macro_f1": 0.58, "accuracy": 0.6, "roc_auc": 0.61, "directional_hit_ratio": 0.58,
+        "cumulative_return": 0.08, "sharpe_ratio": 1.1, "max_drawdown": 0.05,
+    }
+    return {
+        "leaderboard": [row_template],
+        "alpha_attribution": {"random_forest": {"delta_macro_f1": 0.05, "delta_cumulative_return": 0.03, "delta_hit_ratio": 0.02, "sentiment_effective": True}},
+        "champion_model_name": "random_forest",
+        "champion_score": 0.58,
+    }
+
+
 class StylesAndThemeTests(unittest.TestCase):
     """測試深色金融終端樣式與市場色彩語彙"""
 
@@ -291,6 +311,58 @@ class DataLoaderContractTests(unittest.TestCase):
         self.assertEqual(mode, DataMode.ERROR)
         self.assertEqual(radar, [])
 
+    def test_load_tournament_results_empty_when_no_artifact(self):
+        """artifact 檔案不存在 → EMPTY，不得回傳假排行榜資料。"""
+        with tempfile.TemporaryDirectory() as tmpdir:
+            missing_path = os.path.join(tmpdir, "nonexistent.json")
+            data, mode = load_tournament_results(artifact_path=missing_path)
+        self.assertIsNone(data)
+        self.assertEqual(mode, DataMode.EMPTY)
+
+    def test_load_tournament_results_error_on_malformed_missing_keys(self):
+        """artifact 存在但缺少必要頂層欄位（如 champion_model_name）→ ERROR。"""
+        with tempfile.TemporaryDirectory() as tmpdir:
+            path = os.path.join(tmpdir, "malformed.json")
+            with open(path, "w", encoding="utf-8") as f:
+                json.dump({"leaderboard": [_valid_tournament_payload()["leaderboard"][0]]}, f)
+            data, mode = load_tournament_results(artifact_path=path)
+        self.assertIsNone(data)
+        self.assertEqual(mode, DataMode.ERROR)
+
+    def test_load_tournament_results_error_on_leaderboard_row_missing_field(self):
+        """artifact 頂層欄位齊全，但 leaderboard 列缺少必要欄位（如 macro_f1）→ ERROR。"""
+        payload = _valid_tournament_payload()
+        del payload["leaderboard"][0]["macro_f1"]
+        with tempfile.TemporaryDirectory() as tmpdir:
+            path = os.path.join(tmpdir, "bad_row.json")
+            with open(path, "w", encoding="utf-8") as f:
+                json.dump(payload, f)
+            data, mode = load_tournament_results(artifact_path=path)
+        self.assertIsNone(data)
+        self.assertEqual(mode, DataMode.ERROR)
+
+    def test_load_tournament_results_error_on_invalid_json(self):
+        """artifact 存在但不是合法 JSON → ERROR，不得拋出未捕捉例外。"""
+        with tempfile.TemporaryDirectory() as tmpdir:
+            path = os.path.join(tmpdir, "not_json.json")
+            with open(path, "w", encoding="utf-8") as f:
+                f.write("{this is not valid json")
+            data, mode = load_tournament_results(artifact_path=path)
+        self.assertIsNone(data)
+        self.assertEqual(mode, DataMode.ERROR)
+
+    def test_load_tournament_results_real_from_valid_artifact(self):
+        """合法 artifact → REAL，且回傳內容原樣保留供 UI 層渲染。"""
+        payload = _valid_tournament_payload()
+        with tempfile.TemporaryDirectory() as tmpdir:
+            path = os.path.join(tmpdir, "valid.json")
+            with open(path, "w", encoding="utf-8") as f:
+                json.dump(payload, f)
+            data, mode = load_tournament_results(artifact_path=path)
+        self.assertEqual(mode, DataMode.REAL)
+        self.assertEqual(data["champion_model_name"], "random_forest")
+        self.assertEqual(len(data["leaderboard"]), 1)
+
 
 class InteractiveChartsTests(unittest.TestCase):
     """測試 Plotly 雙 Y 軸互動圖表與策略曲線產生器"""
@@ -365,6 +437,35 @@ class UIComponentsTests(unittest.TestCase):
         """mode=ERROR 時安全渲染錯誤橫幅並回傳 None，不嘗試渲染空清單。"""
         self.assertIsNone(render_thematic_radar([], mode=DataMode.ERROR))
 
+    def test_render_tournament_leaderboard_empty_mode_no_crash(self):
+        """無 artifact（EMPTY）時安全顯示佔位說明，不嘗試對 None 資料建表。"""
+        self.assertIsNone(render_tournament_leaderboard(None, mode=DataMode.EMPTY))
+
+    def test_render_tournament_leaderboard_error_mode_no_crash(self):
+        """artifact 格式錯誤（ERROR）時安全顯示錯誤橫幅，不嘗試對 None 資料建表。"""
+        self.assertIsNone(render_tournament_leaderboard(None, mode=DataMode.ERROR))
+
+    def test_render_tournament_leaderboard_real_mode_structure(self):
+        """REAL 模式下對合法 payload 正常渲染，不拋出例外。"""
+        payload = {
+            "leaderboard": [
+                {"experiment_id": "EXP-RF-MM", "model_name": "random_forest", "feature_set": "MultiModal (18 Feat)",
+                 "macro_f1": 0.58, "accuracy": 0.6, "roc_auc": 0.61, "directional_hit_ratio": 0.58,
+                 "cumulative_return": 0.08, "sharpe_ratio": 1.1, "max_drawdown": 0.05},
+                {"experiment_id": "EXP-RF-TECH", "model_name": "random_forest", "feature_set": "PureTechnical (9 Feat)",
+                 "macro_f1": 0.53, "accuracy": 0.55, "roc_auc": 0.54, "directional_hit_ratio": 0.53,
+                 "cumulative_return": 0.03, "sharpe_ratio": 0.6, "max_drawdown": 0.07},
+            ],
+            "alpha_attribution": {"random_forest": {"delta_macro_f1": 0.05, "delta_cumulative_return": 0.05, "delta_hit_ratio": 0.05, "sentiment_effective": True}},
+            "champion_model_name": "random_forest",
+            "champion_score": 0.58,
+        }
+        self.assertIsNone(render_tournament_leaderboard(payload, mode=DataMode.REAL))
+
+    def test_render_tournament_leaderboard_real_mode_with_empty_leaderboard_falls_back_to_error(self):
+        """mode=REAL 但 leaderboard 為空清單時，視為契約不符，安全退回錯誤橫幅而非渲染空表。"""
+        self.assertIsNone(render_tournament_leaderboard({"leaderboard": []}, mode=DataMode.REAL))
+
 
 if __name__ == "__main__":
     unittest.main()
```

</details>

---

## 2. 產出 1：契約驗證原始輸出

```bash
python scripts/verify/gate0_contract_check.py
echo "EXIT=$?"
```

```
B1   PASS | 29 欄契約完整性
       migration 新增 22 + 既有 7 = 29
B2   PASS | 被引用欄位皆存在於契約（反查法）
       8 個被引用，缺失 0
B3   PASS | 社群欄位皆有 SOURCE_FAILED→NULL 規則（反查法）
       9 社群列全部標明 NULL
B4   PASS | raw 層留言計數欄無 DEFAULT（反查法）
       四欄型別: ['INTEGER']
B5   PASS | Triple-Barrier label domain 一致
       3/3 文件宣告；DDL CHECK=True
B6   PASS | Barrier anchor 一致為 Open[T+1]
       6 份使用；殘留舊 anchor 0
B7   PASS | 無「來源失敗→空 DataFrame」
       8 處提及，逐行判定全部為正當語境
B8   PASS | §19 需 PO 簽的決策皆有 ADR 承接
       6/6 存在
B9   PASS | Dcard SB 引用正確
       UG-G2-SB5 存在，無 UG-G3-SB1 誤引用
B10  PASS | 編號方案有唯一對照表
       FEATURE_REGISTRY.md §3.7 DB序號↔模型輸入索引對照
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:577 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂

==================================================
Part B: 11/11 PASS
EXIT=0
```

執行環境：container（`stock_prediction_system2_devcontainer-app-1`，`-u vscode`）。
本次新增與修改的 `DECISIONS.md`／`DOCUMENT_DRIFT_REMEDIATION.md`／`TRACEABILITY.md`
皆在 `DOC_PATHS` 掃描範圍內，重跑確認未破壞跨文件契約一致性。

---

## 3. 產出 2：執行環境 + 測試原始輸出 + 依賴狀態表

### 3a. 執行環境

| 欄位 | 內容 |
|------|------|
| 執行環境 | **container** |
| Python 版本 | `Python 3.14.6` |
| 容器名稱 | `stock_prediction_system2_devcontainer-app-1`（`-u vscode`） |

### 3b. 測試原始輸出

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python -m unittest discover -s tests -p "test_*.py"
```

```
Ran 189 tests in 9.960s

OK
```

189 = 173（SB2 commit `414fcc8` 基線）+ 16 個新增（SB3 讀取／渲染契約 9 個 +
`label_end_date` 型別回歸 3 個 + 資料量防線 4 個）。本文件 §0 列出的多輪往返
（實作、兩次缺陷修正）後全套測試**重複驗證均為 189/189 PASS**，非單次僥倖。

### 3c. 依賴狀態表

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode stock_prediction_system2_devcontainer-app-1 \
  python -c "import importlib.util as u; [print(f'{m:26}', 'PRESENT' if u.find_spec(m) else 'ABSENT') for m in ['numpy','pandas','streamlit','plotly','sklearn','lightgbm','xgboost','psycopg2','jieba','snownlp','tenacity','dotenv']]"
```

```
numpy                      PRESENT
pandas                     PRESENT
streamlit                  PRESENT
plotly                     PRESENT
sklearn                    PRESENT
lightgbm                   PRESENT
xgboost                    PRESENT
psycopg2                   PRESENT
jieba                      PRESENT
snownlp                    PRESENT
tenacity                   PRESENT
dotenv                     PRESENT
```

**12/12 PRESENT**——全部走真實路徑，無 fallback／mock 降級。本結果可支撐 ML／NLP／DB 路徑的宣稱。

---

## 4. 產出 3：檔案清單與逐檔授權稽核

```bash
git status --porcelain
```

```
 M app.py
 M doc/evidence/DECISIONS.md
 M doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
 M doc/evidence/TRACEABILITY.md
 M doc/governance/PROJECT_STATUS.md
 M doc/spec/SDD_Financial_Sentiment_System_v1.md
 M src/ui/components.py
 M src/ui/data_loader.py
 M tests/test_time_series_split.py
 M tests/test_ui_contracts.py
?? doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md
?? doc/upgrade/gates/SB3_GATE_B_SUBMISSION.md
?? scripts/generate_tournament_artifact.py
?? tests/test_generate_tournament_artifact.py
```

> **尚未 `git add`**，本表對照的是工作區變更，非 staged 內容。

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `src/ui/data_loader.py` | 在授權交付物內 | `SB3_GATE_A_PROPOSAL.md` §4.1 明列；`_stringify_date_columns` 為程式碼複閱要求的修正 |
| `src/ui/components.py` | 在授權交付物內 | 同上，`render_tournament_leaderboard(data, mode)` 簽章改造 |
| `app.py` | 在授權交付物內 | 呼叫處解包，§4.1 明列 |
| `scripts/generate_tournament_artifact.py`（新檔） | 在授權交付物內 | PO 核准方案 B 明確要求；未執行 |
| `tests/test_ui_contracts.py` | 在授權交付物內 | §5 驗證計畫既定四項測試 |
| `tests/test_time_series_split.py` | 在授權交付物內 | 程式碼複閱第一輪要求之回歸測試 |
| `tests/test_generate_tournament_artifact.py`（新檔） | 在授權交付物內 | 程式碼複閱第三輪要求之資料量防線測試 |
| `doc/evidence/DECISIONS.md` | 在授權交付物內 | Master Plan Brief「Documentation Sync」既定要求；新增 DEC-020，狀態依 PO §8 裁決 #3 改為 `APPROVED` |
| `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 在授權交付物內 | PO 裁決 #2（DRIFT-018 歸屬修正）明確要求 |
| `doc/evidence/TRACEABILITY.md` | 在授權交付物內 | 同 DECISIONS.md |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 在授權交付物內 | PO §8 裁決 #2 明確要求「這次跟 SB2 一起補上」 |
| `doc/governance/PROJECT_STATUS.md` | **不在明列清單，屬狀態追蹤慣例** | 與 SB1／SB2 各步驟的既有做法一致，非新增授權範圍 |
| `doc/upgrade/gates/SB3_GATE_A_PROPOSAL.md`（新檔） | 在授權交付物內 | 提案本體，PO 已核准其內容 |
| `doc/upgrade/gates/SB3_GATE_B_SUBMISSION.md`（新檔，本檔） | 在授權交付物內 | 本次 Gate B 送審文件本體 |

**本次無超出授權清單的檔案。**

---

## 5. 產出 4：格式／行尾夾帶偵測

### 5a. 本輪最終檢查結果

```bash
git diff --numstat > /tmp/ns_raw.txt
git diff --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

```
1c1
< 5	2	app.py
---
> 4	1	app.py
```

### 5b. app.py 落差說明（非格式夾帶，實質內容變更）

唯一落差在 Sidebar 摘要字串：

```diff
-        f"｜ AI熱詞 {_MODE_LABEL[keywords_mode]} ｜ 題材雷達 {_MODE_LABEL[radar_mode]}"
+        f"｜ AI熱詞 {_MODE_LABEL[keywords_mode]} ｜ 題材雷達 {_MODE_LABEL[radar_mode]} "
+        f"｜ 模型競技 {_MODE_LABEL[tournament_mode]}"
```

新增一個**字串內容裡的空格**（用來分隔「題材雷達」與下一段「模型競技」的顯示文字），
`git diff -w`（忽略所有空白差異）因此把這行判定為「未變更」，才會與 raw 版本產生 1 行的落差。
這是 f-string 字面值內的功能性字元，不是行尾／縮排格式問題，`-w` 在這裡的判定反而是誤報。

### 5c. 本輪自行攔截的一起格式夾帶事件（未演變為問題）

在把 `_fetch_real_stock_features_from_db()` 內的日期轉換提取為 `_stringify_date_columns()`
輔助函式時，`Edit` 操作把原本帶尾隨 8 個空格的兩行空白行改成了真空行——與 SB1／SB2
Gate B 記錄過的同型態格式夾帶同源，差別是**這次由本 SB 自己在準備 Gate B 文件時
主動 diff 核對發現，不是等 PO 逐行核對才抓到**。已用 Python 腳本以行號精確定位、
逐行還原為原始位元組（`        \n`，8 個空格），還原後 `data_loader.py` 的 numstat
落差歸零：

```
還原前：83  4  src/ui/data_loader.py（raw） vs 81  2（-w）→ 落差 2 行
還原後：83  4  src/ui/data_loader.py（raw） vs 83  4（-w）→ 無落差
```

還原後重跑 `py_compile` 與全套測試（189/189 PASS）確認無副作用。

### 5d. 還原後最終確認

```bash
git diff --check
```

```
warning: in the working copy of 'app.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/components.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/data_loader.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_time_series_split.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_ui_contracts.py', LF will be replaced by CRLF the next time Git touches it
```

（既有 CRLF 提示，無新增 trailing-whitespace 錯誤。依 `git-diff-check-blind-spot` 教訓，
本結果不單獨作為「無格式夾帶」的證據——§5a／§5c 的 numstat vs `-w` 逐行核對才是。）

---

## 6. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 不可重跑原因 |
|------|---------|--------------------------|
| contract-check 11/11 PASS | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py` |
| 全套測試 189/189 PASS（container，12/12 依賴齊備） | `VERIFIED THIS SESSION` | §3b 指令；本次已重跑多次（實作後、兩次缺陷修正後），結果一致 |
| 依賴表 12/12 PRESENT | `VERIFIED THIS SESSION` | §3c 指令 |
| `label_end_date`／`trade_date` 型別不一致既有 bug 已修正 | `VERIFIED THIS SESSION` | §7 known-FAIL 案例 1；`tests/test_time_series_split.py::StringifyDateColumnsRegressionTests` |
| 資料量防線正確攔截「零 Fold 但滿版零分排行榜」 | `VERIFIED THIS SESSION` | §7 known-FAIL 案例 2／3；`tests/test_generate_tournament_artifact.py` |
| `load_tournament_results()` 對 EMPTY／ERROR／REAL 三態行為正確 | `VERIFIED THIS SESSION` | `tests/test_ui_contracts.py::DataLoaderContractTests`（5 個）／`UIComponentsTests`（4 個） |
| `scripts/generate_tournament_artifact.py` 全程唯讀（不含 SQL、不呼叫 DBWriter 寫入方法） | `VERIFIED THIS SESSION` | 自我稽核 `grep`；審查員程式碼複閱通過（三輪，含兩次要求修正後的複閱） |
| RISK-013 綁定確認：目標為真實開發 DB（`localhost:5432/postgres`） | `VERIFIED THIS SESSION` | `DBWriter().db_config` 解析輸出；PO 已複查確認 |
| **真實 tournament artifact 已產出，排行榜顯示真實計算結果** | **`NOT VERIFIED`** | **未驗證範圍：`scripts/generate_tournament_artifact.py` 本次未執行，`models/` 目錄不存在。PO 裁示目前資料量不足以支撐 `WalkForwardSplitter` 預設 window，暫不執行；`load_tournament_results()` 因此回傳 `DataMode.EMPTY`，UI 正確顯示「尚未完成模型競技」——這是設計好用來反映此現況的行為，不是繞過驗收的手段。** |
| DRIFT-018 三個矛盾（排名自洽、分數重複、artifact 連結）已完全解決 | `NOT VERIFIED` | 未驗證範圍：矛盾 (1)(3) 已結構上消除（不再有字面常數）；矛盾 (2)（lightgbm/xgboost 同分）待真實 artifact 產出後才能實測確認是否真的不再重現 |
| §7 文件同步（DEC-020／DRIFT-018 歸屬／TRACEABILITY.md／PROJECT_STATUS.md）已完成 | `VERIFIED THIS SESSION` | 本文件 §1 diff 逐項可見 |

---

## 7. 產出 6：known-FAIL 案例對照表

| 檢查 / 機制 | known-FAIL 案例 | 實測結果 | 復原確認 |
|------------|----------------|---------|---------|
| **`label_end_date`／`trade_date` 型別一致性**（`_stringify_date_columns`） | 審查員以純合成資料（`FeatureAggregator` 直接呼叫，不連 DB）重建修正前狀態：只轉換 `trade_date` 為字串，刻意不轉換 `label_end_date`，餵進 `WalkForwardSplitter.split()` | `TypeError`——證實修正前的程式碼確實會在這個路徑上崩潰，不是理論疑慮 | 已修正（新增 `_stringify_date_columns()` 統一轉換兩欄位）；`tests/test_time_series_split.py::test_known_fail_unfixed_type_mismatch_raises_typeerror` 手動重建修正前狀態，確認 `assertRaises(TypeError)` 通過 |
| **資料量防線**（`check_sufficient_data`） | `check_sufficient_data(unique_dates=50, train_window_size=60, test_window_size=20)` | `RuntimeError`，訊息含「50」與「80」（60+20）——證實防線真的會攔截不足的資料量，且錯誤訊息可讀 | 無需復原（純函式呼叫，無副作用）；`test_known_fail_insufficient_data_is_blocked` |
| **「`leaderboard` 是否為空」判斷資料量是否足夠**（舊防線的失效示範） | 用 15 天合成資料（4 演算法 × 2 特徵集）直接呼叫 `evaluate_tournament()`，繞過新防線觀察舊邏輯的行為 | `leaderboard.empty == False`，回傳 8 列、每列 `macro_f1`／`directional_hit_ratio` 皆為 `0.0` 的「滿版但全部零分」表——證實舊防線（`if leaderboard_df.empty`）在這個情境下**完全不會觸發**，會讓一份看似正常實則從未訓練過的 artifact 被寫出 | 此為 known-FAIL 示範本身（舊防線的失效證明），不是需要復原的變更；已記錄於 §0 步驟回顧與 DEC-020 |
| **資料量足夠時的正向路徑** | 90 天合成資料，`train_window_size=30`／`test_window_size=10`，先過 `check_sufficient_data` 再跑 `evaluate_tournament()` | 產出 8 列非零結果（`macro_f1` 總和 > 0），證實防線通過後的路徑真的能訓練出東西，不是「沒被擋下」就等於「跑得動」 | 無需復原；`test_sufficient_synthetic_data_produces_real_nonzero_leaderboard` |
| **`load_tournament_results()` 對格式錯誤 artifact 的偵測力** | 分別構造：非法 JSON、缺頂層欄位、leaderboard 列缺欄位、leaderboard 為空清單四種案例 | 四種皆正確回傳 `(None, DataMode.ERROR)`，不拋出未捕捉例外 | 無需復原；`tests/test_ui_contracts.py` 對應四個測試 |
| `gate0_contract_check.py`（B1~B11 契約檢查） | 本次未重新示範；已於 Gate 0 與 SB1／SB2 Gate B 獨立確認過 | — | `PREVIOUSLY VERIFIED`，不在本次範圍內重複驗證 |

---

## 8. 尚未解決／請 PO 裁決事項

1. **（已裁決）真實 artifact 暫不產出**：PO 同意——等資料量足夠再說，不需要既定排程。
2. **（已解決）`SDD_Financial_Sentiment_System_v1.md` 同步**：PO 裁示這次與 SB2 一併補上。
   已更新 §2「應用與 ML 層」模組狀態（`dashboard.py` 規劃中佔位條目改為 `app.py`／`src/ui/`
   已實作，含 DataMode 與 artifact-driven 排行榜說明）與 §3 新增第 7 項工程亮點
   「UI 資料來源透明化與排行榜動態化」，涵蓋 DEC-012 與 DEC-020 兩項決策。
3. **（已裁決）DEC-020 狀態**：PO 於授權本次 commit 時一併核准，狀態已由 `Proposed`
   改為 `APPROVED`（`doc/evidence/DECISIONS.md` DEC-020，2026-08-26）。
4. **（已裁決）DRIFT-018 矛盾 (2) 待實測**：PO 同意標記為待未來真實 artifact 產出後
   才能實測確認，不是現在的阻塞項。

**commit 授權**：本文件為送審文件，不代表 commit 已獲授權。若 PO 決定放行，
請明確指出授權範圍（哪些檔案）；`gate-submit` skill 的自檢流程第 3～5 步
（`git add`、逐檔稽核、格式偵測）將在取得授權後於 commit 前重新針對實際 staged 內容執行一次。
