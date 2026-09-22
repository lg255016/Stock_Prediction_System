# UG-G1-SB1 Gate B 送審文件：Purged Walk-Forward

> **性質**：`gate-submit` skill 六項強制產出的整合文件。**不是** commit 授權本身 ——
> commit 授權留待 PO 讀完本文件後另行決定。本次未執行 `git add`／`git commit`。
> **執行日期**：2026-08-25
> **狀態**：步驟 0～5 全數完成；§8 三項 PO 裁決事項已於 2026-08-25 全數解決
> （含 T-PW-01/02/03 known-FAIL 補做）；`src/`、`tests/` 變更尚未 commit
> **證據標籤**：`VERIFIED THIS SESSION`（除另有標註者外，重跑指令見各節）

---

## 0. 步驟 0～5 完整回顧

| 步驟 | 內容 | 完成日期 | 證據位置 |
|------|------|---------|---------|
| 步驟 0 | 實測覆蓋歸因（runtime 而非 grep 推導的 A/B/C 分類） | 2026-08-24 | `SB1_STEP1_BEFORE_SNAPSHOT.md` §3、§4 |
| 步驟 1 | BEFORE 快照（154 tests / OK，逐測試結果 + Fold 特性） | 2026-08-24 | `SB1_STEP1_BEFORE_SNAPSHOT.md` §2、§5 |
| 步驟 2 | 保存修正前績效基線（`components.py` 8 值原文照錄 + 兩個污染源分流） | 2026-08-24 | `DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節 |
| 步驟 3 | 實作：`WalkForwardSplitter` 新增 Purge/Embargo；`generate_target_labels()` 新增 `label_end_date` | 2026-08-24（首版）／2026-08-25（PO 獨立驗證後修正） | 本文件 §1 完整 diff |
| 步驟 4 | AFTER 快照（163→164 tests / OK，逐檔案數量與 A/B/C 分類比對） | 2026-08-25 | `SB1_STEP4_AFTER_SNAPSHOT.md` |
| 步驟 5 | Sentinel：靜態呼叫點 10 處不變；runtime 攔截 9 次與 GOV-02 基線一致 | 2026-08-25 | `SB1_STEP4_AFTER_SNAPSHOT.md` §4 |

**步驟 3 的一次重大修正**（PO 2026-08-25 獨立驗證發現）：首版實作僅以全域唯一交易日索引反推
`label_end_date`，從未讀取 `feature_aggregator.generate_target_labels()` 產出的逐列真實值 ——
多股票交易日曆不對齊時（如個股停牌）會低估應被 Purge 的列。已修正為「df 含該欄位時逐列精確
判定，缺席時才退回全域近似法」，並新增重現測試與 fallback 精度限制的 docstring 揭露。

**本次 Gate B 整理過程中額外發現並補齊的缺口**（見 §3 授權稽核）：
1. `SB1_GATE_A_PROPOSAL.md` §5 明列的文件同步範圍（`DECISIONS.md` DEC-011、`TRACEABILITY.md`、
   `SYSTEM_UPGRADE_MASTER_PLAN.md`、`DOCUMENT_DRIFT_REMEDIATION.md` 的 DRIFT-012 狀態）先前**完全未執行**，
   本次一併補齊。`REMAINING_RISKS.md` 一項經檢查已由 RISK-014（既有）涵蓋，無需新增。
2. `min_train_size` 跳過 Fold 的行為（DoD 第 2 項、RISK-001 接受邊界）先前**零測試覆蓋**
   （僅以 `min_train_size=1` 迴避觸發），本次補上正向驗證測試。

---

## 1. 完整 Diff（最終全貌）

**檔案清單**（11 modified + 1 new，675 insertions(+), 52 deletions(-)）：

```
 doc/evidence/DECISIONS.md                      |  24 ++-
 doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md     |  63 +++++-
 doc/evidence/TRACEABILITY.md                   |   1 +
 doc/governance/PROJECT_STATUS.md               |   4 +-
 doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md      |  35 ++-
 doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md       |   7 +-
 doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md |  11 +-
 src/ml/time_series_split.py                    | 222 +++++++++++++++++--
 src/transform/feature_aggregator.py            |  17 +-
 tests/test_feature_aggregator_alignment.py     |  57 ++++++
 tests/test_time_series_split.py                | 286 ++++++++++++++++++++++++-
 11 files changed, 675 insertions(+), 52 deletions(-)
 + 1 個新檔（untracked）：doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md
```

**重跑指令**：`git diff` （工作區尚未 staged，此指令即可重現下方全部內容）

<details>
<summary>完整 diff 內容（點擊展開，1076 行）</summary>

```diff
diff --git a/doc/evidence/DECISIONS.md b/doc/evidence/DECISIONS.md
index aae885e..708a55c 100644
--- a/doc/evidence/DECISIONS.md
+++ b/doc/evidence/DECISIONS.md
@@ -1011,16 +1011,32 @@ V5 曾將 Embargo 定義為「從 Test 開頭移除 embargo 行」，這會刪
 
 ### Verification（驗證）
 
-- [ ] T-PW-01~05 五項測試（含 mutation test）
-- [ ] 所有 Fold 的核心斷言成立
+> **實測結果補充（2026-08-25，UG-G1-SB1 步驟 3～5）**。`src/` 變更尚未 commit；
+> 完整證據見 `doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`。
+
+- [x] T-PW-01~05 五項測試（含 mutation test）—— 另加 PO 2026-08-25 回報之停牌重現測試（第 6 項），共 6 項，`tests/test_time_series_split.py` `PurgedWalkForwardTests`，全數 PASS
+- [x] 所有 Fold 的核心斷言成立 —— `WalkForwardSplitter.assert_no_boundary_leakage()`，AFTER 快照全套 163 tests / OK
+
+**實作與原始設計的差異（PO 獨立驗證發現並要求修正）**：原始實作以全域唯一交易日索引
+反推 `label_end_date`，未讀取 `feature_aggregator.generate_target_labels()` 產出的逐列
+`label_end_date` 欄位，個股停牌等日曆不對齊情形會低估應被 Purge 的列（已以停牌重現測試證實）。
+已修正為 `split()` 優先採用 df 中逐列真實值，欄位缺席時才退回全域曆近似法（並於 docstring
+揭露此路徑的精度限制）。
 
 ### Remaining Risks（剩餘風險）
 
-- Purge 後訓練集可能不足 `min_train_size` → 該 Fold 跳過並記錄警告。
+- Purge 後訓練集可能不足 `min_train_size` → 該 Fold 跳過並記錄警告。**（已實作：`min_train_size`
+  未顯式指定時預設為 `train_window_size - label_horizon`，跳過時 `logger.warning`。）**
+- 無 `label_end_date` 欄位時的 fallback 近似法，假設面板內所有列共享同一份全域交易日曆；
+  個股停牌等造成日曆不對齊時可能低估應 Purge 的列（見上方「實作與原始設計的差異」）。
+  **建議一律透過 `FeatureAggregator.generate_target_labels()` 提供該欄位以取得精確結果**；
+  是否所有生產路徑（含 evaluator/trainer 呼叫 `WalkForwardSplitter.split()` 的實際入口）都已
+  正確傳入該欄位，尚待接 Gate 3 或 trainer 管線整合時逐一確認，PO 已同意此項延後處理。
 
 ### 證據文件
 
-`doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §2, §3
+`doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` §2, §3；
+`doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`
 
 ---
 
diff --git a/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md b/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
index 54d0419..3713491 100644
--- a/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
+++ b/doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
@@ -36,7 +36,7 @@
 | DRIFT-009 | **HIGH** | data_loader.py | `src/ui/data_loader.py:L31-40` | UI 應明確區分 DB 即時資料與離線模擬資料 | `generate_mock_stock_features()` 在 DB 連線失敗時被靜默呼叫作為 fallback，使用者無法從 UI 辨別當前顯示的是真實資料還是模擬資料。函式註解寫「供離線演示與 DB Fallback」但無任何告警機制。 | `VERIFIED — silent fallback, no warning` | 加入明確的 UI 告警橫幅（`st.warning`），當 fallback 至 mock 資料時顯示「目前顯示離線模擬資料」，並在日誌記錄 fallback 事件。 | UG-G1-SB2 |
 | DRIFT-010 | **HIGH** | Repository root | Repository root | 專案應有 README.md 提供快速入門指引 | `ls README.md` 回傳 exit code 2（檔案不存在）。整個 Repository 沒有任何頂層 README 文件。 | `VERIFIED — file not found` | 建立 `README.md`，涵蓋專案簡介、架構圖、快速啟動、測試執行與貢獻指引。 | UG-G1-SB5 |
 | DRIFT-011 | **HIGH** | Database / Schema | `database/schema.sql`, `src/loaders/db_writer.py` | 系統應具備資料庫遷移機制以支援 Schema 演進 | 專案中 `grep -r "schema_version\|ALTER TABLE" *.py *.sql` 回傳零結果。無任何 migration framework（如 Alembic）、`ALTER TABLE` 語句或 `schema_version` 追蹤表。Schema 變更只能透過 drop-and-recreate 執行。 | `VERIFIED — no migration infrastructure` | 導入輕量 migration 機制：建立 `schema_version` 表 + 有序 migration 腳本目錄 `database/migrations/`，或整合 Alembic。 | UG-G1-SB4 |
-| DRIFT-012 | **MEDIUM** | feature_aggregator.py / time_series_split | `src/transform/feature_aggregator.py:L459` | Target label 生成與 Walk-Forward 切分邊界應無洩漏 | `append_target_labels()` 使用 `shift(-1)` 在完整 DataFrame 上生成 `target_next_close`（L459），此操作在 Walk-Forward splitter 切分邊界處，最後一筆訓練資料的 target 可能洩漏測試集首筆收盤價。需驗證 splitter 是否在 target label 附加 **之後** 切分（安全）還是 **之前** 切分（洩漏風險）。 | `NEEDS AUDIT — boundary interaction unverified` | 稽核 `WalkForwardSplitter` 與 `append_target_labels()` 的呼叫順序，確認 train/test 邊界的 target label 不包含測試集資訊。若確認洩漏，在切分後移除邊界列。 | UG-G1-SB1 |
+| DRIFT-012 | **MEDIUM** | feature_aggregator.py / time_series_split | `src/transform/feature_aggregator.py:L459` | Target label 生成與 Walk-Forward 切分邊界應無洩漏 | `append_target_labels()` 使用 `shift(-1)` 在完整 DataFrame 上生成 `target_next_close`（L459），此操作在 Walk-Forward splitter 切分邊界處，最後一筆訓練資料的 target 可能洩漏測試集首筆收盤價。需驗證 splitter 是否在 target label 附加 **之後** 切分（安全）還是 **之前** 切分（洩漏風險）。 | `VERIFIED — 洩漏已於 SB1_STEP1_BEFORE_SNAPSHOT.md §5.1 實測確認存在（gap 全為週末、交易日隔離為零），並於 UG-G1-SB1 步驟 3 修正` | **已修正（2026-08-24/25，尚未 commit）**：`WalkForwardSplitter` 新增 `label_horizon`／`embargo_days`／Purge；`generate_target_labels()` 新增 `label_end_date` 欄位供逐列精確 Purge 判定。稽核與修正證據見 `SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、DEC-011。 | UG-G1-SB1（已完成步驟 0～5，待 commit） |
 | DRIFT-013 | **MEDIUM** | PROJECT_STATUS.md | `PROJECT_STATUS.md:L23` | 「Current HEAD: `a41a9ea`」 | `git log --oneline -1` 顯示實際 HEAD 為 **`680de6c`**（`test(ui): add comprehensive real article pipeline tests and sync traceability`）。文件落後至少 5 個 commit。 | `VERIFIED — HEAD mismatch` | 更新 PROJECT_STATUS.md Git State 區塊，反映最新 HEAD 與 branch 狀態。建議加入「此欄位為手動快照，實際狀態以 `git log` 為準」的免責聲明。 | UG-G1-SB5 |
 | DRIFT-014 | **MEDIUM** | ptt_scraper.py / 推噓文解析 | `src/extractors/ptt_scraper.py:L57-65` | PTT 文章應解析完整推噓文資訊以支援 comment feature engineering | `ptt_scraper.py:L57` 僅從列表頁的 `div.nrec` 擷取推噓計數（`push_tag`），未進入文章內頁解析個別推噓文的內容、類型（推/噓/→）與時間戳。`push_count` 為字串型態的粗略統計。 | `VERIFIED — list page nrec only, no inner page parsing` | Gate 2 擴充 PTT scraper 支援文章內頁推噓文解析，提取 `comment_type`（推/噓/→）、`comment_content` 與 `comment_time`，供 `COMMENT_ENHANCED_19` 特徵契約使用。 | UG-G2-SB2 |
 | DRIFT-015 | **CRITICAL** | DECISIONS.md (DEC-007), TRACEABILITY.md, SYSTEM_UPGRADE_MASTER_PLAN.md | DEC-007「Multi-Model Tournament & Alpha Attribution Protocol」；TRACEABILITY.md 之「8組平行實驗 Alpha 歸因」列 | 宣稱以 4 大模型（Logistic Regression／Random Forest／LightGBM／XGBoost）× 2 特徵集 = 8 組平行對照實驗，進行橫向競技與 Alpha 歸因 | GOV-02 實測（2026-08-23）：在 host 環境下 `PureTechnicalModelFactory` 對 `lightgbm` 與 `xgboost` **回傳同一個 `_FallbackTreeEnsembleClassifier` 類別**，`random_forest` 亦為同一 fallback 家族，僅 `logistic_regression` 為相異的 `_FallbackLinearClassifier`。四個模型名稱實際只對映**兩種**相異實作。容器內（15 套件齊備）則正確回傳 `sklearn.LogisticRegression`／`sklearn.RandomForestClassifier`／`lightgbm.LGBMClassifier`／`xgboost.XGBClassifier`。 | `VERIFIED — GOV-02 型別實測，host vs container 對照` | **影響範圍**：任何在 host 產出的模型橫向比較、Alpha 歸因與冠軍模型選拔結論**在方法論上不成立** —— 不是精度誤差，而是「比較」本身不存在（同一實作被當成三個不同模型比較）。須明確標註 DEC-007 的證據基礎僅在 dev container 內成立；所有既有 tournament 數據若來自 host，必須標為 `NOT VERIFIED` 並於容器內重跑後方可引用。 | UG-G1-SB5（文件標註）+ Gate 3 重跑（UG-G3-SB3/SB7） |
@@ -76,7 +76,7 @@ lock 只保證「照 lock 安裝會得到已驗證的版本組合」，並未修
 
 | Owner Gate/SB | 漂移 ID | 簡述 |
 |---------------|---------|------|
-| UG-G1-SB1 | DRIFT-012 | 時序邊界洩漏稽核 |
+| UG-G1-SB1（已修正，待 commit） | DRIFT-012 | 時序邊界洩漏稽核與修正 |
 | UG-G1-SB2 | DRIFT-009 | Silent mock fallback 告警 |
 | UG-G1-SB3 | DRIFT-008 | 靜態排行榜改動態 |
 | UG-G1-SB4 | DRIFT-011 | DB migration 機制 |
@@ -155,6 +155,65 @@ lock 只保證「照 lock 安裝會得到已驗證的版本組合」，並未修
 
 ---
 
+## UG-G1-SB1 步驟 2：修正前績效基線（已污染，保留供對照）
+
+> **來源**：`doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md` §3.3（PO 已核准，本文件為其落實）。
+> **性質**：**保存，不修改**。本節不覆寫、不刪除 DRIFT-018 或 `components.py` 現行內容，
+> 只是為 SB1 的 Purge 修正建立一份「污染前」對照錨點。矛盾分析的權威位置仍是 DRIFT-018，
+> 不在此重複（見下方 §3）。
+> **執行日期**：2026-08-24
+
+### 1. 原文照錄
+
+擷取自 `src/ui/components.py:129-138`（`render_tournament_leaderboard`），擷取日期 2026-08-24：
+
+| 排名 | 模型演算法 | 特徵集 | Macro F1 | 方向命中率 | 累積策略報酬 | ΔAlpha 增益 |
+|------|-----------|--------|---------:|----------:|------------:|-----------:|
+| 🏆 冠軍 | Random Forest | 多模態 (18 Feat) | 0.5820 | 58.4% | +8.2% | +4.7% |
+| 🥈 亞軍 | LightGBM | 多模態 (18 Feat) | 0.5910 | 59.2% | +9.6% | +5.5% |
+| 🥉 季軍 | XGBoost | 多模態 (18 Feat) | 0.5860 | 58.8% | +8.9% | +5.1% |
+| 第 4 名 | Logistic Regression | 多模態 (18 Feat) | 0.5480 | 54.2% | +4.8% | +2.7% |
+| 控制組 | LightGBM | 純價量 (9 Feat) | 0.5410 | 54.0% | +4.1% | 基準線 |
+| 控制組 | XGBoost | 純價量 (9 Feat) | 0.5380 | 53.9% | +3.8% | 基準線 |
+| 控制組 | Random Forest | 純價量 (9 Feat) | 0.5340 | 53.8% | +3.5% | 基準線 |
+| 控制組 | Logistic Regression | 純價量 (9 Feat) | 0.5120 | 51.5% | +2.1% | 基準線 |
+
+### 2. 質性宣稱原文與現況
+
+`doc/evidence/TRACEABILITY.md`（提案 §3.1 撰寫時位於 L164，本文件擷取時因既有編輯位移至 L170）：
+
+> ~~**8 組平行實驗 Alpha 歸因**：量化證明社群情緒融合模型相較純價量控制組帶來顯著之 ΔF1 與 ΔReturn 超額報酬。~~
+
+**現況**：該行**已由 DRIFT-018 標註撤回**（2026-08-24，PO 裁示），非本節新增動作 ——
+`TRACEABILITY.md` 現行內容本身已是刪除線＋撤回註記，不是原始強宣稱。
+本節照錄目的是保留「被撤回的原文是什麼」，供 §1 的數值與宣稱對照，本節不重複執行撤回。
+
+**版本落差揭露（PO 2026-08-24 獨立驗證發現）**：現行 `TRACEABILITY.md:170` 的實際字面
+已比本引文簡短（撤回編輯時一併精簡為「…顯著之超額報酬」，未同步登錄這項措辭變動）。
+本節保留的是**提案 §3.1／DRIFT-018 登錄時的原始措辭**，不是對 `TRACEABILITY.md`
+目前字面的逐字 grep 結果 —— 兩者不一致是已知落差，不是本節引用錯誤或捏造。
+
+### 3. 兩個獨立污染源，各自的修復排程不同
+
+> 完整三項矛盾分析、判定原則與標註規則見 DRIFT-018；本節只列污染源與排程，不重述矛盾細節。
+
+| 污染源 | 說明（一句話） | 修復排程 | 目前狀態 |
+|--------|---------------|---------|---------|
+| **邊界洩漏** | `train[T].label` 依賴 `test[T+1].close`；`SB1_STEP1_BEFORE_SNAPSHOT.md` §5.1 顯示 Fold `gap` 全為週末、train 末日與 test 首日相鄰、交易日隔離為零 | **UG-G1-SB1**（本 Gate A 授權範圍內） | 步驟 0、1 已完成；步驟 3（實作）未開始 |
+| **fallback 型別碰撞**（DRIFT-015） | host 上 `lightgbm`／`xgboost`／`random_forest` 對映同一個 `_FallbackTreeEnsembleClassifier`，四模型比較實為兩種實作互比 | UG-G1-SB5（文件標註）+ **Gate 3**（`UG-G3-SB3`／`UG-G3-SB7`，容器內重跑） | 兩者皆未開始；是否僅存在於 host 尚待容器內重跑 tournament 確認 |
+
+**因此**：即使 SB1 完成邊界洩漏修正，§1 的數值仍不可用 —— 第二個污染源獨立存在且修復排程在 Gate 3，
+兩者必須都解決才談得上重新量測。
+
+### 4. 使用限制【強制】
+
+- 本節任何數值**不得**引用為模型效能宣稱、baseline 或比較基準。
+- 本節**不是** SB1 的驗收依據 —— 驗收依據見 `SB1_STEP1_BEFORE_SNAPSHOT.md` §3（A 類 42 個方法）與 §6.1（splitter 證據不得由 aggregator 背書）。
+- `components.py` 現行內容**維持不動**；其處置屬 UG-G1-SB2（DRIFT-009 Demo/Real 分離）與 UG-G1-SB3（DRIFT-008 動態化），SB1 不修改 `src/ui/`。
+- 本節唯一用途：待兩個污染源皆修復後，供「污染前 vs. 污染源逐一移除後」的數值差異對照，作為 remediation 有效性的佐證 —— **不是**污染前數值本身正確性的佐證。
+
+---
+
 ## 審計方法論
 
 1. **程式碼逐行驗證**：對每筆漂移項目，直接讀取原始碼檔案並標記具體行號。
diff --git a/doc/evidence/TRACEABILITY.md b/doc/evidence/TRACEABILITY.md
index 651feb7..072921a 100644
--- a/doc/evidence/TRACEABILITY.md
+++ b/doc/evidence/TRACEABILITY.md
@@ -47,6 +47,7 @@
 | **Antweiler 輿情量化指標** | RES-001 / RES-002 | 2.3 Gate 5 特徵契約 | **DEC-006** (G5-SB1) | `src/transform/feature_aggregator.py` | `tests/test_research_features.py` | 4 tests | `VERIFIED THIS SESSION` (Gate 5 Closed) |
 | **技術動能與波動率指標** | RES-003 / 004 / 005 | 2.3 Gate 5 特徵契約 | **DEC-006** (G5-SB2) | `src/transform/feature_aggregator.py` | `tests/test_research_features.py` | 2 tests | `VERIFIED THIS SESSION` (Gate 5 Closed) |
 | **Walk-Forward 時序切分引擎** | Phase 3 時序交叉驗證 | 3.1 ML 時序防護 | **DEC-007** (P3-SB1) | `src/ml/time_series_split.py` | `tests/test_time_series_split.py` | 6 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
+| **Purged Walk-Forward（Purge/Embargo，邊界洩漏修正）** | 稽核報告 §1；PO 決策 §3.3 | `PURGED_WALK_FORWARD_SPEC.md` §2, §3 | **DEC-011**（UG-G1-SB1） | `src/ml/time_series_split.py`（`label_horizon`／`embargo_days`／`assert_no_boundary_leakage`）<br>`src/transform/feature_aggregator.py`（`label_end_date` 欄位） | `tests/test_time_series_split.py`（`PurgedWalkForwardTests`）<br>`tests/test_feature_aggregator_alignment.py`（`label_end_date` 測試） | 6 + 3 = 9 tests | `VERIFIED THIS SESSION`（`SB1_STEP4_AFTER_SNAPSHOT.md`；163/163 PASS；`src/` 尚未 commit） |
 | **純價量控制組基準模型工廠** | Phase 3 控制組對照實驗 | 3.2 基準模型定義 | **DEC-007** (P3-SB2) | `src/ml/baseline_models.py` | `tests/test_baseline_models.py` | 6 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
 | **多模態特徵融合與競技訓練** | Phase 3 多模型橫向競技 | 3.3 樹模型適配訓練 | **DEC-007** (P3-SB3) | `src/ml/model_trainer.py` | `tests/test_model_trainer.py` | 5 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
 | **8組平行實驗 Alpha 歸因與即時推論** | Phase 3 Alpha 歸因與推論 | 3.4 評估器與推論器 | **DEC-007** (P3-SB4) | `src/ml/evaluator.py`<br>`src/ml/predictor.py` | `tests/test_ml_evaluator.py` | 7 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
diff --git a/doc/governance/PROJECT_STATUS.md b/doc/governance/PROJECT_STATUS.md
index 9838bff..3b7519e 100644
--- a/doc/governance/PROJECT_STATUS.md
+++ b/doc/governance/PROJECT_STATUS.md
@@ -33,7 +33,7 @@
 | GOV-05 文件依歸屬與生命週期分類 | 完成 | `abfa743`、`7f7258e` |
 | GOV-06 交接 | 本次 | 本 commit |
 | **UG-Gate-1** | **已核准，採逐 SB 授權** | — |
-| └ **UG-G1-SB1** Purged Walk-Forward | Gate A 已核准；**步驟 0、1 完成；步驟 2、3 未開始** | `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md` |
+| └ **UG-G1-SB1** Purged Walk-Forward | Gate A 已核准；**步驟 0～5 完成；步驟 6（送 Gate B）未開始** | `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`；步驟 2 見 `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節；`src/` 變更尚未 commit |
 
 RISK-001 `Accept`、RISK-010 `Defer`（至 Gate 3）、RISK-012 `Mitigate`、
 RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RISKS.md`。
@@ -44,7 +44,7 @@ RISK-013 `Mitigate`（2026-08-24）——見 `doc/upgrade/contracts/REMAINING_RI
 |------|------|
 | **UG-G1-SB2 ~ SB5** | **未授權**。Gate 1 採逐 SB 授權，SB1 尚未結案 |
 | **UG-Gate-2、UG-Gate-3、UG-Gate-4** | **未核准，不得啟動** |
-| SB1 步驟 2（保存修正前績效基線）、步驟 3（實作） | 在已核准的 Gate A 範圍內，但**尚未執行** |
+| SB1 步驟 6（送 Gate B、commit） | 在已核准的 Gate A 範圍內，但**尚未執行**；步驟 0～5 已於 2026-08-24/25 完成，`src/` 變更尚未 commit，需另行取得 commit scope 授權 |
 | `src/`、`tests/`、`database/` | 升級專案至今**一行未改** |
 
 ### 0.4 測試基線
diff --git a/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md b/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
index b108a53..c472322 100644
--- a/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
+++ b/doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
@@ -495,17 +495,22 @@ UG-Gate-4 (XAI, Export & UI) — 5 SBs
 | Proposed Change | 新增 `label_horizon` + `embargo_days` 參數 (交易日計)；切分時 Purge 訓練集中 `label_end_date >= test_start_date` 的行；新增 `label_end_date` 欄位 |
 | In Scope | `WalkForwardSplitter` 修改; `feature_aggregator.py` 新增 label_end_date; 迴歸測試 |
 | Out of Scope | Triple-Barrier 標籤本身 (Gate-3); 模型重訓練 |
-| Affected Components | `src/ml/time_series_split.py`, `src/transform/feature_aggregator.py`, `tests/test_time_series_split.py` |
+| Affected Components | `src/ml/time_series_split.py`, `src/transform/feature_aggregator.py`, `tests/test_time_series_split.py`, `tests/test_feature_aggregator_alignment.py`（實作時追加：`label_end_date` 為 `feature_aggregator.py` 新欄位，其既有測試需同步覆蓋） |
 | Data/API/Schema Contract | label_end_date = trade_date + H 交易日 |
 | Failure Semantics | Purge 後訓練集不足 min_train_size → 該 Fold 跳過並 log warning |
 | Risks & Trade-offs | Purge 減少訓練資料量；Embargo 減少可用訓練候選 |
-| Tests | `test_no_future_data_in_train`, `test_purge_removes_label_overlapping_rows`, `test_embargo_excludes_post_test_train_candidates`, `test_future_data_mutation` |
-| E2E Verification | LEGACY_17 baseline + Purged WF 全流程跑通，Fold 數 ≥ 3 |
-| Documentation Sync | SDD §3.1; DECISIONS.md (DEC-011); TRACEABILITY.md |
+| Tests | `test_purge_removes_label_overlapping_rows`（T-PW-01）, `test_purge_h5_removes_five_days`（T-PW-02）, `test_embargo_excludes_post_test_train_candidates`（T-PW-03）, `test_core_assertion_holds`（T-PW-04）, `test_future_data_mutation`（T-PW-05）, `test_purge_uses_per_stock_label_end_date_for_calendar_misalignment`（PO 2026-08-25 回報重現測試，第 6 項） |
+| E2E Verification | 於 GOV-03 釘選環境 + 空臨時 DB 執行，依 A／B／C 三類證據分割（見 `SB1_STEP1_BEFORE_SNAPSHOT.md` §4.2）；Fold 數 ≥ 3；不得以「163/163 OK」單獨作為 SB1 驗收結論 |
+| Documentation Sync | SDD §3.1; DECISIONS.md (DEC-011); TRACEABILITY.md; DOCUMENT_DRIFT_REMEDIATION.md (DRIFT-012) |
 | Rollback | Revert commit; 舊 WalkForwardSplitter 無需 Migration |
-| Definition of Done | 所有 Fold 的 max(train.label_end_date) < min(test.trade_date); 全套測試 PASS |
-| Gate A | PO 審查計畫 |
-| Gate B | PO 授權 Commit |
+| Definition of Done | 1) 所有 Fold 的 `max(train.label_end_date) < min(test.trade_date)`；2) Purge 後訓練集不足 `min_train_size` 時該 Fold 跳過並記錄警告，嚴禁縮小 Purge 範圍保留 Fold（RISK-001 接受邊界）；3) A 類證據 before/after 對照完成且差異均有解釋；4) Sentinel 檢查通過：`connect()` 靜態呼叫點仍為 10 處；5) 修正前基線已保存並標註污染來源（見 §2） |
+| Gate A | PO 審查計畫 —— **已核准（2026-08-23）** |
+| Gate B | PO 授權 Commit —— 步驟 0～5 已完成（2026-08-24/25），送審中；`src/` 尚未 commit |
+
+> **本 Gate 所有 SB 的測試執行環境**：dev container（Python 3.14.6，GOV-03 釘選之
+> `requirements.lock.txt`），**非 host**。host 執行結果不得作為驗收證據（`CLAUDE.md` §13.0）。
+> 涉及 DB 的驗證須指向空臨時資料庫並附綁定確認。（`SB1_GATE_A_PROPOSAL.md` §2.4，PO 已核准
+> 採「集中一處」陳述，各 SB 的 Tests 欄不重複此段。）
 
 #### UG-G1-SB2: UI Demo/Real 模式分離
 
@@ -515,7 +520,7 @@ UG-Gate-4 (XAI, Export & UI) — 5 SBs
 | Requirement Source | 稽核報告 §2; AGENTS.md §10; DRIFT-009 |
 | Current State | `data_loader.py:L31-40` 靜默回退 `generate_mock_stock_features()`; `logger.debug()` 不對終端使用者可見 |
 | Proposed Change | 定義 `DataMode` enum 四狀態: REAL/DEMO/EMPTY/ERROR; 每個 UI 元件接收 DataMode; DEMO 模式醒目標示（Banner + 浮水印）|
-| In Scope | `data_loader.py` 回傳 `(DataFrame, DataMode)` 元組; `components.py` 各元件根據 mode 渲染; `app.py` 全局 mode 追蹤 |
+| In Scope | `data_loader.py` 回傳 `(DataFrame, DataMode)` 元組; `components.py` 各元件根據 mode 渲染; `app.py` 全局 mode 追蹤；併同修復 HERM-01~09 的測試封閉性，使該 9 個測試不再依賴環境憑證與 DB 內容（`SB1_GATE_A_PROPOSAL.md` §2.3，PO 已核准） |
 | Out of Scope | 排行榜動態化 (SB3); 回測真實化 (Gate-4); 新增 DB 連線重試邏輯 |
 | Affected Components | `src/ui/data_loader.py`, `src/ui/components.py`, `app.py` |
 | Data/API/Schema Contract | DataMode enum: REAL (DB 成功回傳非空) / DEMO (Mock fallback) / EMPTY (DB 成功但無資料) / ERROR (DB 連線失敗) |
@@ -1016,6 +1021,20 @@ Embargo:
 | T+1 漲跌 | 1 | 移除 Train 中 label_end_date >= test_start 的行 (通常末 1 天) |
 | Triple-Barrier 5 日 | 5 | 移除 Train 中 label_end_date >= test_start 的行 (通常末 5 天) |
 
+### 13.4 實作對齊（UG-G1-SB1 步驟 3～5，2026-08-24/25）
+
+`src/ml/time_series_split.py`／`src/transform/feature_aggregator.py` 已依 §13.1～§13.3 實作，
+`WalkForwardSplitter` 新增 `label_horizon`、`embargo_days`、`assert_no_boundary_leakage()`；
+`generate_target_labels()` 新增 `label_end_date` 欄位。完整證據見
+`doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`。
+
+**規格未明訂、實作時需補充定義的一點**：§13.2 定義 `label_end_date[T] = trade_date[T + label_horizon]`，
+但未指明當面板內多檔股票的實際交易日曆不對齊時（例如個股停牌），此定義應以**全域**交易日序列
+還是**個股自身**交易日序列計算。PO 2026-08-25 獨立驗證發現，以全域序列近似會在停牌情境下低估
+應被 Purge 的列（已以重現測試證實），因此實作採**個股自身交易日曆**為準（`generate_target_labels()`
+逐股 `groupby('stock_id')['trade_date'].shift(-label_horizon)`），`WalkForwardSplitter.split()`
+優先讀取該逐列真實值，僅在欄位缺席時才退回全域近似法並於 docstring 揭露精度限制。
+
 ---
 
 ## 14. 剩餘風險清冊
diff --git a/doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md b/doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md
index 4dd3b4b..839810e 100644
--- a/doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md
+++ b/doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md
@@ -11,7 +11,12 @@
 > 那比沒有檢查更糟**。兩處已更正為 10，並要求 runtime 攔截數與靜態呼叫點數分開陳述。
 >
 > **步驟 1 已完成**，實測結果見 `SB1_STEP1_BEFORE_SNAPSHOT.md`（含依實測重建的 A／B／C 分類與 Gate B 追加證據要求）。
-> **步驟 2、3 尚未開始。**
+> **步驟 2 已完成（2026-08-24）**，見 `DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節。
+> **步驟 3 已完成（2026-08-24/25）**：`time_series_split.py` 新增 Purge/Embargo；PO 2026-08-25 獨立驗證
+> 發現並要求修正「Purge 僅用全域曆近似、未讀取 `feature_aggregator` 產出的逐列 `label_end_date`」的
+> 正確性問題，已修正為「df 含該欄位時逐列精確判定，缺席時才退回近似法」。
+> **步驟 4、5 已完成（2026-08-25）**，見 `SB1_STEP4_AFTER_SNAPSHOT.md`。
+> **步驟 6（送 Gate B）尚未開始。**
 
 ---
 
diff --git a/doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md b/doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md
index 17a7556..eaf6b5f 100644
--- a/doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md
+++ b/doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md
@@ -3,7 +3,8 @@
 > **性質**：`SB1_GATE_A_PROPOSAL.md` §4.3 步驟 0 與步驟 1 的**必要產出物**。
 > 不是交接文件 —— 步驟 1 要求的就是產出此快照，沒有它 Gate B 無可比對。
 > **執行日期**：2026-08-24
-> **狀態**：`src/`、`tests/`、`database/` 一行未動；**步驟 2、3 尚未開始**
+> **狀態**：步驟 2～5 已完成（見下方「下一步」表）；`src/` 變更為 `time_series_split.py`、
+> `feature_aggregator.py`，尚未 commit
 > **證據標籤**：`VERIFIED THIS SESSION`（重跑程序見 §7）
 
 ---
@@ -310,8 +311,8 @@ docker rm -f -v sb1_before_tmpdb
 |------|------|
 | 步驟 0 覆蓋歸因 | **完成**（§3、§4） |
 | 步驟 1 BEFORE 快照 | **完成**（§2、§5） |
-| 步驟 2 保存修正前績效基線 | **未開始** —— 見 `SB1_GATE_A_PROPOSAL.md` §3.3 |
-| 步驟 3 實作 | **未開始** |
-| 步驟 4 AFTER 快照 | 未開始 —— 比對點見 §5.2、§6.1 |
-| 步驟 5 Sentinel | 未開始 —— 基線 10 處，見 §6.3 |
+| 步驟 2 保存修正前績效基線 | **完成**（2026-08-24）—— 見 `DOCUMENT_DRIFT_REMEDIATION.md`「UG-G1-SB1 步驟 2」節 |
+| 步驟 3 實作 | **完成**（2026-08-24/25）—— `time_series_split.py`／`feature_aggregator.py`；含 PO 2026-08-25 回報之精確路徑修正 |
+| 步驟 4 AFTER 快照 | **完成**（2026-08-25）—— 見 `SB1_STEP4_AFTER_SNAPSHOT.md` |
+| 步驟 5 Sentinel | **完成**（2026-08-25）—— 靜態 10 處不變；runtime 攔截 9 次與 GOV-02 基線一致，見 `SB1_STEP4_AFTER_SNAPSHOT.md` §4 |
 | 步驟 6 送 Gate B | 未開始 |
diff --git a/src/ml/time_series_split.py b/src/ml/time_series_split.py
index a93dd52..cad5693 100644
--- a/src/ml/time_series_split.py
+++ b/src/ml/time_series_split.py
@@ -18,7 +18,14 @@ class WalkForwardSplitter:
     3. 支援雙模式（Dual Mode）：
        - 'rolling'（滾動窗口）：固定訓練天數，隨時間向前平移。
        - 'expanding'（擴展窗口）：固定起點，隨時間逐步累積全部歷史數據。
-    4. 零前視偏誤防護（Zero Look-ahead Bias）：自動驗證各 Fold 訓練集與測試集索引無交集。
+    4. 零前視偏誤防護（Zero Look-ahead Bias）：自動驗證各 Fold 訓練集與測試集索引無交集；
+       並以 Purge（依 label_end_date 移除訓練集中與測試集標籤重疊的列）與
+       Embargo（依 embargo_days 排除前一 Fold 測試窗結束後的訓練候選天數）
+       防止標籤邊界洩漏（見 `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md`）。
+       Purge 優先採用 df 中逐列的 `label_end_date` 欄位（例如
+       `FeatureAggregator.generate_target_labels()` 產出，依個股自身交易日曆計算，
+       可正確處理停牌等造成個股曆與全域曆不同步的情形）；欄位不存在時退回以
+       全域唯一交易日索引 + label_horizon 反推的近似值（見 split() docstring 的精度限制）。
     """
 
     def __init__(
@@ -28,7 +35,10 @@ class WalkForwardSplitter:
         step_size: Optional[int] = None,
         mode: str = "rolling",
         min_train_size: Optional[int] = None,
-        date_col: str = "trade_date"
+        date_col: str = "trade_date",
+        label_horizon: int = 1,
+        embargo_days: int = 0,
+        label_end_date_col: str = "label_end_date"
     ):
         """
         初始化 Walk-Forward 時序切分器。
@@ -38,8 +48,18 @@ class WalkForwardSplitter:
             test_window_size: 測試/評估窗口交易日天數 (預設 20 交易日，約 1 個月)
             step_size: 每次向前平移之交易日天數 (若為 None 則預設為 test_window_size，無縫銜接)
             mode: 切分模式 ('rolling' 滾動窗口 或 'expanding' 擴展窗口)
-            min_train_size: 最小訓練天數 (預設等於 train_window_size)
+            min_train_size: Purge 後最小可接受訓練天數 (若為 None，預設為
+                train_window_size - label_horizon，即容許正常 Purge 造成的縮減，
+                但不容許 Purge/Embargo 疊加造成的額外縮減)
             date_col: 交易日期欄位名稱 (預設 'trade_date')
+            label_horizon: 標籤依賴的未來交易日數 (預設 1，對應現行 T+1 標籤)。
+                用於 Purge：移除訓練集中 label_end_date = trade_date[T + label_horizon]
+                落在測試集開始日期（含）之後的天數。傳入 0 停用 Purge。
+            embargo_days: 測試窗結束後應排除的訓練候選交易日數 (預設 0，
+                嚴格單向 Walk-Forward 合法值；見 PURGED_WALK_FORWARD_SPEC.md §2.4)
+            label_end_date_col: 逐列 label_end_date 欄位名稱 (預設 'label_end_date')。
+                若 df 含此欄位，Purge 直接採用逐列真實值（正確處理個股停牌等
+                日曆不對齊情形）；欄位不存在時退回全域交易日索引近似法。
         """
         if train_window_size <= 0:
             raise ValueError(f"train_window_size 必須大於 0，收到: {train_window_size}")
@@ -57,11 +77,26 @@ class WalkForwardSplitter:
             raise ValueError(f"step_size 必須大於 0，收到: {self.step_size}")
 
         self.mode = mode
-        self.min_train_size = int(min_train_size) if min_train_size is not None else self.train_window_size
+
+        if label_horizon < 0:
+            raise ValueError(f"label_horizon 不得為負數，收到: {label_horizon}")
+        self.label_horizon = int(label_horizon)
+
+        if embargo_days < 0:
+            raise ValueError(f"embargo_days 不得為負數，收到: {embargo_days}")
+        self.embargo_days = int(embargo_days)
+
+        if min_train_size is not None:
+            self.min_train_size = int(min_train_size)
+        else:
+            # 預設容許 Purge 造成的正常縮減 (train_window_size - label_horizon)，
+            # 但不容許 Purge/Embargo 疊加造成的額外縮減。
+            self.min_train_size = max(1, self.train_window_size - self.label_horizon)
         if self.min_train_size <= 0:
             raise ValueError(f"min_train_size 必須大於 0，收到: {self.min_train_size}")
 
         self.date_col = str(date_col)
+        self.label_end_date_col = str(label_end_date_col)
 
     def _extract_sorted_unique_dates(self, df: pd.DataFrame) -> List[Any]:
         """從 DataFrame 抽取並遞增排序的唯一交易日期清單"""
@@ -76,7 +111,13 @@ class WalkForwardSplitter:
         return sorted_dates
 
     def get_n_splits(self, df: pd.DataFrame) -> int:
-        """計算在給定 DataFrame 下可產生的總 Fold 數量"""
+        """
+        計算在給定 DataFrame 下、依訓練/測試窗口大小可產生的 Fold 數量上界。
+
+        注意：本方法僅計算窗口是否「排得下」，不考慮 Purge/Embargo 造成的
+        訓練集縮減。若 Purge 後訓練天數低於 min_train_size，`split()` 會跳過
+        該 Fold 並記錄警告 —— 屆時 `split()` 實際產出的 Fold 數可能小於本方法回傳值。
+        """
         unique_dates = self._extract_sorted_unique_dates(df)
         n_dates = len(unique_dates)
 
@@ -96,6 +137,37 @@ class WalkForwardSplitter:
 
         return n_splits
 
+    @staticmethod
+    def assert_no_boundary_leakage(
+        train_label_end_dates: List[Any],
+        test_start_date: Any,
+        fold_idx: Optional[int] = None
+    ) -> None:
+        """
+        核心斷言 (PURGED_WALK_FORWARD_SPEC.md §2.6)：
+        max(train.label_end_date) < min(test.trade_date)
+
+        Args:
+            train_label_end_dates: 訓練集各列的 label_end_date（可含 None/NaT，代表
+                該列標籤依賴的未來日期超出資料集範圍，不計入比較）
+            test_start_date: 該 Fold 測試集最小交易日
+            fold_idx: 供錯誤訊息標明 Fold 編號 (可省略)
+
+        Raises:
+            RuntimeError: 若任何訓練列的 label_end_date >= test_start_date
+        """
+        valid_dates = [d for d in train_label_end_dates if d is not None and not pd.isna(d)]
+        if not valid_dates:
+            return
+
+        max_train_label_end = max(valid_dates)
+        if max_train_label_end >= test_start_date:
+            fold_desc = "" if fold_idx is None else f" (Fold {fold_idx})"
+            raise RuntimeError(
+                f"Purge 邊界洩漏{fold_desc}：train label_end_date "
+                f"({max_train_label_end}) >= test_start_date ({test_start_date})"
+            )
+
     def split(
         self,
         df: pd.DataFrame
@@ -104,13 +176,26 @@ class WalkForwardSplitter:
         執行時序前向滾動切分生成器。
 
         Args:
-            df: 包含特徵與 trade_date 欄位的特徵矩陣 DataFrame
+            df: 包含特徵與 trade_date 欄位的特徵矩陣 DataFrame。若含
+                `label_end_date_col`（預設 'label_end_date'）欄位，Purge 會逐列採用該
+                真實值；否則以全域唯一交易日索引 + label_horizon 反推近似值。
+
+        Purge 精度限制（無 label_end_date 欄位時的 fallback 路徑）：
+            近似法假設 df 中所有列共享同一份全域交易日曆（即同一 trade_date 的所有列，
+            其 label_end_date 皆等於該全域交易日索引 + label_horizon 對應的日期）。
+            若面板內個別股票存在停牌等造成其自身交易日曆與全域曆不同步的情形，
+            該股在停牌期間之後的 label_end_date 實際上會比近似值更晚，
+            近似法可能低估應被 Purge 的列、導致殘留邊界洩漏。
+            **建議一律透過 `FeatureAggregator.generate_target_labels()` 提供
+            逐列 label_end_date 欄位，取得精確結果；fallback 僅供該欄位缺席時的
+            最低限度防護，不應作為正式驗收依據。**
 
         Yields:
             Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
-                - train_indices: 訓練集在 df 中的整數列索引 (np.ndarray)
+                - train_indices: 訓練集在 df 中的整數列索引 (np.ndarray)，已套用 Purge/Embargo
                 - test_indices: 測試集在 df 中的整數列索引 (np.ndarray)
-                - fold_metadata: 該 Fold 的時序元資料字典 (含日期區間、天數、樣本數)
+                - fold_metadata: 該 Fold 的時序元資料字典 (含日期區間、天數、樣本數、
+                  Purge/Embargo 統計)
         """
         if df is None or df.empty:
             return
@@ -126,6 +211,9 @@ class WalkForwardSplitter:
             )
             return
 
+        # 日期 -> 全域索引位置 (用於 Purge/Embargo 的交易日計算)
+        date_to_gidx: Dict[Any, int] = {d: i for i, d in enumerate(unique_dates)}
+
         # 預先建立 日期 -> DataFrame 整數列索引 的倒排索引映射 (極速 O(1) 查找)
         date_to_indices: Dict[Any, np.ndarray] = {}
         # 確保以 reset_index 基準取整數位置
@@ -133,6 +221,13 @@ class WalkForwardSplitter:
         for date_val, group in df_reset.groupby(self.date_col, sort=False):
             date_to_indices[date_val] = group.index.to_numpy(dtype=np.int64)
 
+        # Purge 精確路徑：df 是否含逐列 label_end_date 欄位 (見 split() docstring)
+        has_label_end_date_col = self.label_end_date_col in df_reset.columns
+        label_end_series = df_reset[self.label_end_date_col] if has_label_end_date_col else None
+
+        # 記錄先前 Fold 的 (test_end_gidx, embargo_end_gidx]，供後續 Fold 的 Embargo 排除
+        embargoed_ranges: List[Tuple[int, int]] = []
+
         fold_idx = 0
         start_idx = 0
 
@@ -143,29 +238,109 @@ class WalkForwardSplitter:
             if test_end > n_dates:
                 break
 
-            # 決定訓練與測試日期區間
+            # 決定訓練與測試日期區間 (Purge/Embargo 之前)
             if self.mode == "rolling":
-                train_dates = unique_dates[start_idx:test_start]
+                train_dates = list(unique_dates[start_idx:test_start])
             else:  # expanding
-                train_dates = unique_dates[0:test_start]
+                train_dates = list(unique_dates[0:test_start])
 
             test_dates = unique_dates[test_start:test_end]
+            test_start_date = test_dates[0]
+            test_end_date = test_dates[-1]
+            test_end_gidx = date_to_gidx[test_end_date]
 
-            # 嚴格斷言：時序不交叉
+            # 嚴格斷言：時序不交叉 (窗口本身的基本時間順序，先於 Purge/Embargo 檢查)
             max_train_date = train_dates[-1]
-            min_test_date = test_dates[0]
+            min_test_date = test_start_date
             if max_train_date >= min_test_date:
                 raise RuntimeError(
                     f"時序交錯異常！Fold {fold_idx}: Train 最大日 ({max_train_date}) >= Test 最小日 ({min_test_date})"
                 )
 
-            # 提取對應的 DataFrame 行索引
+            # --- Embargo: 排除先前 Fold 測試窗結束後 embargo_days 天內的訓練候選日 ---
+            purged_by_embargo = 0
+            if self.embargo_days > 0 and embargoed_ranges:
+                kept = []
+                for d in train_dates:
+                    gidx = date_to_gidx[d]
+                    if any(lo < gidx <= hi for lo, hi in embargoed_ranges):
+                        purged_by_embargo += 1
+                    else:
+                        kept.append(d)
+                train_dates = kept
+
+            # 提取 Embargo 後的候選訓練列索引與測試列索引
             train_idx_list = [date_to_indices[d] for d in train_dates if d in date_to_indices]
             test_idx_list = [date_to_indices[d] for d in test_dates if d in date_to_indices]
-
-            train_indices = np.concatenate(train_idx_list) if train_idx_list else np.empty(0, dtype=np.int64)
+            candidate_train_indices = (
+                np.concatenate(train_idx_list) if train_idx_list else np.empty(0, dtype=np.int64)
+            )
             test_indices = np.concatenate(test_idx_list) if test_idx_list else np.empty(0, dtype=np.int64)
 
+            # --- Purge: 逐列移除 label_end_date >= test_start_date 的訓練候選列 ---
+            if self.label_horizon > 0 and len(candidate_train_indices) > 0:
+                if has_label_end_date_col:
+                    # 精確路徑：逐列真實 label_end_date（依個股自身交易日曆）。
+                    # 缺值 (NaT，代表該股尚無足夠未來資料驗證安全性) 保守視為需 Purge。
+                    row_label_ends = label_end_series.iloc[candidate_train_indices].tolist()
+                    purge_flags = [
+                        (v is None) or pd.isna(v) or (v >= test_start_date)
+                        for v in row_label_ends
+                    ]
+                else:
+                    # 近似路徑：全域交易日索引 + label_horizon 反推 (見 split() docstring 精度限制)
+                    row_dates = df_reset[self.date_col].iloc[candidate_train_indices].tolist()
+                    purge_flags = [
+                        (date_to_gidx[d] + self.label_horizon) >= test_start
+                        for d in row_dates
+                    ]
+                purge_mask = np.array(purge_flags, dtype=bool)
+                purged_indices = candidate_train_indices[purge_mask]
+                train_indices = candidate_train_indices[~purge_mask]
+            else:
+                purged_indices = np.empty(0, dtype=np.int64)
+                train_indices = candidate_train_indices
+
+            purged_samples = int(len(purged_indices))
+            purged_dates_set = (
+                set(df_reset[self.date_col].iloc[purged_indices].tolist()) if purged_samples else set()
+            )
+            purged_days = len(purged_dates_set)
+
+            surviving_dates = (
+                sorted(set(df_reset[self.date_col].iloc[train_indices].tolist()))
+                if len(train_indices) else []
+            )
+            train_days = len(surviving_dates)
+
+            if train_days < self.min_train_size:
+                logger.warning(
+                    f"[WalkForwardSplitter] Fold {fold_idx} Purge/Embargo 後訓練天數 ({train_days}) "
+                    f"低於 min_train_size ({self.min_train_size})，跳過此 Fold。"
+                    f"依 RISK-001 接受邊界，不縮小 Purge 範圍或放寬 label_end_date 判定以保留 Fold。"
+                )
+                if self.embargo_days > 0:
+                    embargo_end_gidx = min(test_end_gidx + self.embargo_days, n_dates - 1)
+                    embargoed_ranges.append((test_end_gidx, embargo_end_gidx))
+                fold_idx += 1
+                start_idx += self.step_size
+                continue
+
+            # 核心斷言：max(train.label_end_date) < min(test.trade_date)
+            # (Purge 已保證此條件，此處為防禦性重驗，符合 CLAUDE.md §9A 之防呆設計原則)
+            if self.label_horizon > 0:
+                if has_label_end_date_col:
+                    train_label_end_dates = label_end_series.iloc[train_indices].tolist()
+                else:
+                    train_label_end_dates = [
+                        unique_dates[date_to_gidx[d] + self.label_horizon]
+                        if date_to_gidx[d] + self.label_horizon < n_dates else None
+                        for d in df_reset[self.date_col].iloc[train_indices].tolist()
+                    ]
+            else:
+                train_label_end_dates = []
+            self.assert_no_boundary_leakage(train_label_end_dates, test_start_date, fold_idx)
+
             # 嚴格斷言：索引零交集
             intersection = np.intersect1d(train_indices, test_indices)
             if len(intersection) > 0:
@@ -176,17 +351,26 @@ class WalkForwardSplitter:
             metadata: Dict[str, Any] = {
                 "fold": fold_idx,
                 "mode": self.mode,
-                "train_start_date": train_dates[0],
-                "train_end_date": train_dates[-1],
+                "label_horizon": self.label_horizon,
+                "embargo_days": self.embargo_days,
+                "train_start_date": surviving_dates[0],
+                "train_end_date": surviving_dates[-1],
                 "test_start_date": test_dates[0],
                 "test_end_date": test_dates[-1],
-                "train_days": len(train_dates),
+                "train_days": train_days,
                 "test_days": len(test_dates),
                 "train_samples": len(train_indices),
                 "test_samples": len(test_indices),
+                "purged_days": purged_days,
+                "purged_samples": purged_samples,
+                "embargoed_days": purged_by_embargo,
             }
 
             yield train_indices, test_indices, metadata
 
+            if self.embargo_days > 0:
+                embargo_end_gidx = min(test_end_gidx + self.embargo_days, n_dates - 1)
+                embargoed_ranges.append((test_end_gidx, embargo_end_gidx))
+
             fold_idx += 1
             start_idx += self.step_size
diff --git a/src/transform/feature_aggregator.py b/src/transform/feature_aggregator.py
index 7e8a55a..deb045f 100644
--- a/src/transform/feature_aggregator.py
+++ b/src/transform/feature_aggregator.py
@@ -436,21 +436,27 @@ class FeatureAggregator:
         print("[INFO] [Feature] 特徵表聚合完成！")
         return df_features[final_cols]
 
-    def generate_target_labels(self, df_features: pd.DataFrame) -> pd.DataFrame:
+    def generate_target_labels(self, df_features: pd.DataFrame, label_horizon: int = 1) -> pd.DataFrame:
         """
         為時間序列特徵表生成監督式機器學習預測目標 (Target Labels)。
         嚴格遵循防前視偏誤 (Zero Look-ahead Bias) 約定：
-        - 預測目標以 T+1 交易日收盤表現為基準。
+        - 預測目標以 T+1 交易日收盤表現為基準 (與 label_horizon 參數無關，恆為 T+1)。
         - 每檔股票的最後一個交易日目標為 NaN (因為未來資料尚未發生)。
 
         Args:
             df_features: 包含基本價量特徵的 DataFrame (含 trade_date, stock_id, close_price)
+            label_horizon: 標籤依賴的未來交易日數 (預設 1，對應 target_up_down 的 T+1 依賴)。
+                用於計算 label_end_date = trade_date[T + label_horizon]，供
+                Purged Walk-Forward (`WalkForwardSplitter`) 的 Purge 邊界判定使用；
+                不影響 target_next_close / target_return_1d / target_up_down 本身。
 
         Returns:
-            pd.DataFrame: 附加 target_next_close, target_return_1d, target_up_down 的特徵矩陣
+            pd.DataFrame: 附加 target_next_close, target_return_1d, target_up_down, label_end_date 的特徵矩陣
         """
         if df_features is None or df_features.empty:
             return df_features
+        if label_horizon < 1:
+            raise ValueError(f"label_horizon 必須大於等於 1，收到: {label_horizon}")
 
         df_res = df_features.copy()
         df_res = df_res.sort_values(by=['stock_id', 'trade_date']).reset_index(drop=True)
@@ -468,4 +474,9 @@ class FeatureAggregator:
             lambda r: 1 if r > 0 else (0 if pd.notna(r) else np.nan)
         )
 
+        # 4. label_end_date = trade_date[T + label_horizon]（依個股自身交易日序列，非全域對齊）。
+        #    供 WalkForwardSplitter 的 Purge 判定使用；每檔股票尾端 label_horizon 天為 NaT
+        #    (超出該股票已知資料範圍，未來尚未發生，見 PURGED_WALK_FORWARD_SPEC.md §2.1)。
+        df_res['label_end_date'] = df_res.groupby('stock_id')['trade_date'].shift(-label_horizon)
+
         return df_res
\ No newline at end of file
diff --git a/tests/test_feature_aggregator_alignment.py b/tests/test_feature_aggregator_alignment.py
index 7009cde..3ae332f 100644
--- a/tests/test_feature_aggregator_alignment.py
+++ b/tests/test_feature_aggregator_alignment.py
@@ -199,6 +199,63 @@ class TargetLabelGenerationTests(unittest.TestCase):
         self.assertTrue(pd.isna(row_3["target_return_1d"]))
         self.assertTrue(pd.isna(row_3["target_up_down"]))
 
+    def test_label_end_date_defaults_to_t_plus_1(self):
+        """UG-G1-SB1：預設 label_horizon=1 時，label_end_date 應等於個股下一交易日"""
+        df_features = pd.DataFrame({
+            "trade_date": [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)],
+            "stock_id": ["2330", "2330", "2330"],
+            "close_price": [100.0, 110.0, 105.0],
+            "volume": [1000, 1200, 1100],
+            "sentiment_mean": [0.7, 0.8, 0.3]
+        })
+
+        df_target = self.aggregator.generate_target_labels(df_features)
+
+        self.assertEqual(df_target.iloc[0]["label_end_date"], date(2026, 8, 4))
+        self.assertEqual(df_target.iloc[1]["label_end_date"], date(2026, 8, 5))
+        self.assertTrue(pd.isna(df_target.iloc[2]["label_end_date"]))
+
+    def test_label_end_date_respects_explicit_label_horizon(self):
+        """UG-G1-SB1：label_horizon=2 時，label_end_date 應為 T+2 交易日；供 Purge/Triple-Barrier 對齊"""
+        df_features = pd.DataFrame({
+            "trade_date": [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6)],
+            "stock_id": ["2330"] * 4,
+            "close_price": [100.0, 110.0, 105.0, 108.0],
+            "volume": [1000, 1200, 1100, 1300],
+            "sentiment_mean": [0.7, 0.8, 0.3, 0.5]
+        })
+
+        df_target = self.aggregator.generate_target_labels(df_features, label_horizon=2)
+
+        self.assertEqual(df_target.iloc[0]["label_end_date"], date(2026, 8, 5))
+        self.assertEqual(df_target.iloc[1]["label_end_date"], date(2026, 8, 6))
+        self.assertTrue(pd.isna(df_target.iloc[2]["label_end_date"]))
+        self.assertTrue(pd.isna(df_target.iloc[3]["label_end_date"]))
+
+        with self.assertRaises(ValueError):
+            self.aggregator.generate_target_labels(df_features, label_horizon=0)
+
+    def test_label_end_date_computed_per_stock_calendar(self):
+        """UG-G1-SB1：多股票時 label_end_date 依各股自身交易日序列計算，不互相干擾"""
+        df_features = pd.DataFrame({
+            "trade_date": [
+                date(2026, 8, 3), date(2026, 8, 4),
+                date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)
+            ],
+            "stock_id": ["2330", "2330", "2382", "2382", "2382"],
+            "close_price": [100.0, 110.0, 50.0, 52.0, 51.0],
+            "volume": [1000, 1200, 800, 850, 900],
+            "sentiment_mean": [0.7, 0.8, 0.6, 0.5, 0.4]
+        })
+
+        df_target = self.aggregator.generate_target_labels(df_features)
+
+        row_2330 = df_target[(df_target["stock_id"] == "2330") & (df_target["trade_date"] == date(2026, 8, 3))].iloc[0]
+        self.assertEqual(row_2330["label_end_date"], date(2026, 8, 4))
+
+        row_2382 = df_target[(df_target["stock_id"] == "2382") & (df_target["trade_date"] == date(2026, 8, 4))].iloc[0]
+        self.assertEqual(row_2382["label_end_date"], date(2026, 8, 5))
+
 
 class ZeroLookAheadBiasStrictVerificationTests(unittest.TestCase):
     """嚴格驗證零前視偏誤 (Zero Look-ahead Bias: 修改未來資料對當日特徵完全無影響)"""
diff --git a/tests/test_time_series_split.py b/tests/test_time_series_split.py
index 4952a6e..cdf55e1 100644
--- a/tests/test_time_series_split.py
+++ b/tests/test_time_series_split.py
@@ -1,8 +1,12 @@
+import io
 import unittest
+from contextlib import redirect_stdout
+
 import numpy as np
 import pandas as pd
 
 from src.ml.time_series_split import WalkForwardSplitter
+from src.transform.feature_aggregator import FeatureAggregator
 
 
 class WalkForwardSplitterUnitTests(unittest.TestCase):
@@ -16,6 +20,12 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
         self.assertEqual(splitter.step_size, 20)
         self.assertEqual(splitter.mode, "rolling")
 
+        # 1a. UG-G1-SB1：label_horizon / embargo_days 預設值 (DEC-011)
+        self.assertEqual(splitter.label_horizon, 1)
+        self.assertEqual(splitter.embargo_days, 0)
+        # min_train_size 未顯式指定時，預設容許 Purge 造成的縮減 (60 - 1 = 59)
+        self.assertEqual(splitter.min_train_size, 59)
+
         # 2. 異常參數防護
         with self.assertRaises(ValueError):
             WalkForwardSplitter(train_window_size=0)
@@ -29,6 +39,12 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
         with self.assertRaises(ValueError):
             WalkForwardSplitter(step_size=0)
 
+        with self.assertRaises(ValueError):
+            WalkForwardSplitter(label_horizon=-1)
+
+        with self.assertRaises(ValueError):
+            WalkForwardSplitter(embargo_days=-1)
+
     def test_rolling_mode_splits_and_temporal_invariants(self):
         # 建立 100 天交易日資料 (單檔股票)
         dates = pd.date_range("2026-01-01", periods=100, freq="D").strftime("%Y-%m-%d")
@@ -51,13 +67,18 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
         folds = list(splitter.split(df))
         self.assertEqual(len(folds), 3)
 
+        # UG-G1-SB1（Purged Walk-Forward）：預設 label_horizon=1，訓練窗尾端 1 天
+        # 因 Purge 被移除（40 天窗口實得 39 天）。Purge 本身的專屬測試見
+        # PurgedWalkForwardTests；本測試維持既有窗口/步長邏輯的迴歸覆蓋。
+        expected_train_days_per_fold = 40 - 1
+
         # 逐 Fold 驗證嚴格時間約束
         prev_test_end = None
         for fold_idx, (train_idx, test_idx, meta) in enumerate(folds):
             self.assertEqual(meta["fold"], fold_idx)
-            self.assertEqual(meta["train_days"], 40)
+            self.assertEqual(meta["train_days"], expected_train_days_per_fold)
             self.assertEqual(meta["test_days"], 20)
-            self.assertEqual(len(train_idx), 40)
+            self.assertEqual(len(train_idx), expected_train_days_per_fold)
             self.assertEqual(len(test_idx), 20)
 
             # 1. 索引絕對無交集 (Zero Overlap)
@@ -69,8 +90,8 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
             test_dates = df.iloc[test_idx]["trade_date"].tolist()
             self.assertLess(max(train_dates), min(test_dates))
 
-            # 3. 滾動模式：訓練窗口固定為 40 天
-            self.assertEqual(len(train_dates), 40)
+            # 3. 滾動模式：訓練窗口固定為 40 天，Purge 後為 39 天
+            self.assertEqual(len(train_dates), expected_train_days_per_fold)
 
             # 4. 驗證 step_size 無縫銜接
             if prev_test_end is not None:
@@ -102,7 +123,8 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
         # Fold 0: train 0~29 (30天), test 30~44 (15天)
         # Fold 1: train 0~44 (45天), test 45~59 (15天)
         # Fold 2: train 0~59 (60天), test 60~74 (15天)
-        expected_train_days = [30, 45, 60]
+        # UG-G1-SB1：預設 label_horizon=1，各 Fold 訓練窗尾端 1 天因 Purge 被移除。
+        expected_train_days = [29, 44, 59]
         for fold_idx, (train_idx, test_idx, meta) in enumerate(folds):
             self.assertEqual(meta["train_days"], expected_train_days[fold_idx])
             self.assertEqual(meta["test_days"], 15)
@@ -129,12 +151,13 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
         n_splits = splitter.get_n_splits(df)
         self.assertEqual(n_splits, 3)  # (50 - 20 - 10) / 10 + 1 = 3
 
+        # UG-G1-SB1：預設 label_horizon=1，訓練窗尾端 1 天因 Purge 被移除 (20 天 -> 19 天)。
         for fold_idx, (train_idx, test_idx, meta) in enumerate(splitter.split(df)):
-            self.assertEqual(meta["train_days"], 20)
+            self.assertEqual(meta["train_days"], 19)
             self.assertEqual(meta["test_days"], 10)
 
-            # 每檔股票每天有 1 筆，因此 train_samples 應為 20 * 3 = 60
-            self.assertEqual(len(train_idx), 60)
+            # 每檔股票每天有 1 筆，Purge 後 train_samples 應為 19 * 3 = 57
+            self.assertEqual(len(train_idx), 57)
             self.assertEqual(len(test_idx), 30)
 
             train_df = df.iloc[train_idx]
@@ -166,5 +189,252 @@ class WalkForwardSplitterUnitTests(unittest.TestCase):
             splitter.get_n_splits(df_wrong)
 
 
+class PurgedWalkForwardTests(unittest.TestCase):
+    """
+    UG-G1-SB1：Purged Walk-Forward 測試 (PURGED_WALK_FORWARD_SPEC.md §5.1, T-PW-01~05)。
+    驗證 Purge / Embargo / 核心斷言，涵蓋邊界洩漏修正的正向與失敗路徑。
+    """
+
+    def test_purge_removes_label_overlapping_rows(self):
+        """T-PW-01: H=1 時，train 尾端 1 天被移除"""
+        dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
+        df = pd.DataFrame({
+            "trade_date": dates,
+            "stock_id": ["2330"] * 30,
+            "close_price": np.linspace(100, 130, 30)
+        })
+
+        splitter = WalkForwardSplitter(
+            train_window_size=10, test_window_size=5, step_size=5,
+            mode="rolling", label_horizon=1, min_train_size=1
+        )
+
+        train_idx, test_idx, meta = next(splitter.split(df))
+
+        self.assertEqual(meta["train_days"], 9)
+        self.assertEqual(meta["purged_days"], 1)
+        self.assertEqual(meta["purged_samples"], 1)
+        self.assertEqual(len(train_idx), 9)
+
+        train_dates = set(df.iloc[train_idx]["trade_date"])
+        # 未 Purge 前訓練窗尾端應為第 10 天 (index 9)；Purge 後不得出現於 train
+        self.assertNotIn(dates[9], train_dates)
+        self.assertIn(dates[8], train_dates)
+
+    def test_fold_skipped_with_warning_when_purge_drops_below_min_train_size(self):
+        """
+        Gate A DoD 第 2 項 / RISK-001 接受邊界：Purge 後訓練集不足 min_train_size 時，
+        該 Fold 跳過並記錄警告 —— 嚴禁縮小 Purge 範圍或放寬 label_end_date 判定以保留 Fold。
+        本測試先前為此行為的覆蓋缺口（僅以 min_train_size=1 迴避觸發），現補上正向驗證。
+        """
+        dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
+        df = pd.DataFrame({
+            "trade_date": dates,
+            "stock_id": ["2330"] * 30,
+            "close_price": np.linspace(100, 130, 30)
+        })
+
+        # train_window=10, label_horizon=1 -> Purge 後每個 Fold 恆為 9 天；
+        # min_train_size=10 使其恆低於門檻，驗證「跳過並警告」而非「縮小 Purge 保留 Fold」。
+        splitter = WalkForwardSplitter(
+            train_window_size=10, test_window_size=5, step_size=5,
+            mode="rolling", label_horizon=1, min_train_size=10
+        )
+
+        with self.assertLogs("src.ml.time_series_split", level="WARNING") as log_ctx:
+            folds = list(splitter.split(df))
+
+        # 每個 Fold 的 Purge 後訓練天數恆為 9 < min_train_size=10，故全部跳過，產出 0 個 Fold
+        self.assertEqual(folds, [])
+        self.assertGreaterEqual(len(log_ctx.output), 1)
+        warning_text = log_ctx.output[0]
+        self.assertIn("Fold 0", warning_text)
+        self.assertIn("9", warning_text)  # 實際 Purge 後訓練天數
+        self.assertIn("10", warning_text)  # min_train_size 門檻
+        self.assertIn("不縮小 Purge 範圍", warning_text)
+
+        # get_n_splits() 只算窗口是否排得下，不知道 Purge 會使 Fold 全數被跳過 ——
+        # 與 split() 實際產出的落差正是 get_n_splits() docstring 明示的行為。
+        self.assertGreater(splitter.get_n_splits(df), 0)
+
+    def test_purge_h5_removes_five_days(self):
+        """T-PW-02: H=5 時，train 尾端 5 天被移除"""
+        dates = pd.date_range("2026-01-01", periods=35, freq="D").strftime("%Y-%m-%d")
+        df = pd.DataFrame({
+            "trade_date": dates,
+            "stock_id": ["2330"] * 35,
+            "close_price": np.linspace(100, 135, 35)
+        })
+
+        splitter = WalkForwardSplitter(
+            train_window_size=20, test_window_size=10, step_size=10,
+            mode="rolling", label_horizon=5, min_train_size=1
+        )
+
+        train_idx, test_idx, meta = next(splitter.split(df))
+
+        self.assertEqual(meta["train_days"], 15)
+        self.assertEqual(meta["purged_days"], 5)
+        self.assertEqual(meta["purged_samples"], 5)
+
+        train_dates = set(df.iloc[train_idx]["trade_date"])
+        for purged_pos in range(15, 20):
+            self.assertNotIn(dates[purged_pos], train_dates)
+        self.assertIn(dates[14], train_dates)
+
+    def test_embargo_excludes_post_test_train_candidates(self):
+        """T-PW-03: embargo_days > 0 時，前一 Fold 測試窗結束後的天數被排除於後續 Fold 訓練候選"""
+        dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
+        df = pd.DataFrame({
+            "trade_date": dates,
+            "stock_id": ["2330"] * 30,
+            "close_price": np.linspace(100, 130, 30)
+        })
+
+        # label_horizon=0 停用 Purge，隔離 Embargo 的效果單獨驗證；
+        # step_size(8) > test_window_size(5) 使第二個 Fold 的訓練窗延伸到
+        # 第一個 Fold 測試窗結束之後，才有 Embargo 可排除的候選日。
+        splitter = WalkForwardSplitter(
+            train_window_size=10, test_window_size=5, step_size=8,
+            mode="rolling", label_horizon=0, embargo_days=3, min_train_size=1
+        )
+
+        folds = list(splitter.split(df))
+        self.assertGreaterEqual(len(folds), 2)
+
+        fold0_train_idx, fold0_test_idx, fold0_meta = folds[0]
+        self.assertEqual(fold0_meta["test_end_date"], dates[14])
+
+        fold1_train_idx, fold1_test_idx, fold1_meta = folds[1]
+        # 未 Embargo 前，Fold 1 訓練窗為 positions 8~17 (10 天)；
+        # Embargo 排除 test_end (position14) 之後 3 天 (15,16,17)，故剩 7 天。
+        self.assertEqual(fold1_meta["train_days"], 7)
+        self.assertEqual(fold1_meta["embargoed_days"], 3)
+
+        fold1_train_dates = set(df.iloc[fold1_train_idx]["trade_date"])
+        for excluded_pos in (15, 16, 17):
+            self.assertNotIn(dates[excluded_pos], fold1_train_dates)
+        self.assertIn(dates[14], fold1_train_dates)
+
+    def test_core_assertion_holds(self):
+        """T-PW-04: 所有 Fold 的 max(train.label_end_date) < min(test.trade_date) 恆成立"""
+        dates = pd.date_range("2026-01-01", periods=100, freq="D").strftime("%Y-%m-%d")
+        df = pd.DataFrame({
+            "trade_date": dates,
+            "stock_id": ["2330"] * 100,
+            "close_price": np.linspace(100, 200, 100)
+        })
+        date_to_gidx = {d: i for i, d in enumerate(dates)}
+
+        splitter = WalkForwardSplitter(
+            train_window_size=30, test_window_size=10, step_size=10,
+            mode="rolling", label_horizon=3
+        )
+
+        folds = list(splitter.split(df))
+        self.assertGreater(len(folds), 0)
+
+        for train_idx, test_idx, meta in folds:
+            last_train_gidx = date_to_gidx[meta["train_end_date"]]
+            label_end_gidx = last_train_gidx + splitter.label_horizon
+            self.assertLess(label_end_gidx, len(dates))
+            label_end_date = dates[label_end_gidx]
+            # DoD／PURGED_WALK_FORWARD_SPEC.md §2.6 核心斷言
+            self.assertLess(label_end_date, meta["test_start_date"])
+
+    def test_future_data_mutation(self):
+        """T-PW-05: 注入 label_end_date >= test_start_date 的洩漏資料 -> assert_no_boundary_leakage 拋出異常"""
+        # 正常情況：所有 label_end_date 皆早於 test_start_date -> 不拋出
+        WalkForwardSplitter.assert_no_boundary_leakage(
+            train_label_end_dates=["2026-01-08", "2026-01-09", None],
+            test_start_date="2026-01-10",
+        )
+
+        # 已知會 FAIL 的案例：注入一筆 label_end_date 等於 test_start_date (邊界相等亦視為洩漏)
+        with self.assertRaises(RuntimeError):
+            WalkForwardSplitter.assert_no_boundary_leakage(
+                train_label_end_dates=["2026-01-08", "2026-01-10"],
+                test_start_date="2026-01-10",
+            )
+
+        # 已知會 FAIL 的案例：注入一筆晚於 test_start_date 的「未來」資料（模擬資料被竄改／洩漏）
+        with self.assertRaises(RuntimeError):
+            WalkForwardSplitter.assert_no_boundary_leakage(
+                train_label_end_dates=["2026-01-08", "2026-01-15"],
+                test_start_date="2026-01-10",
+                fold_idx=2,
+            )
+
+    def test_purge_uses_per_stock_label_end_date_for_calendar_misalignment(self):
+        """
+        PO 2026-08-25 回報：split() 若僅以全域唯一交易日索引近似 label_end_date，
+        個股停牌等造成日曆不對齊時會低估應被 Purge 的列。本測試重現該情境
+        （股票 B 於 train 尾端前一天停牌），驗證：
+        1. df 含 FeatureAggregator 產出的逐列 label_end_date 欄位時，Purge 正確抓到洩漏列；
+        2. 缺該欄位、退回全域曆近似法時，同一筆洩漏列會被誤判為安全（示範舊行為的缺陷，
+           呼應 split() docstring 的精度限制揭露）。
+        """
+        dates = pd.date_range("2026-01-01", periods=20, freq="D").strftime("%Y-%m-%d")
+
+        # 股票 A：連續交易 20 天，無停牌
+        df_a = pd.DataFrame({
+            "trade_date": dates,
+            "stock_id": ["A"] * 20,
+            "close_price": np.linspace(100, 119, 20)
+        })
+        # 股票 B：於 dates[9]（train 窗口尾端）停牌，只有 19 筆
+        b_dates = [d for i, d in enumerate(dates) if i != 9]
+        df_b = pd.DataFrame({
+            "trade_date": b_dates,
+            "stock_id": ["B"] * 19,
+            "close_price": np.linspace(50, 68, 19)
+        })
+        df_features = pd.concat([df_a, df_b], ignore_index=True)
+
+        with redirect_stdout(io.StringIO()):
+            aggregator = FeatureAggregator()
+        df_target = aggregator.generate_target_labels(df_features, label_horizon=1)
+
+        # 股票 B 在 dates[8] 那筆的真實 label_end_date：因 dates[9] 停牌，
+        # 其個股自身下一交易日是 dates[10] (= test_start_date)，依 §2.6 應被 Purge。
+        b_row_at_8 = df_target[(df_target["stock_id"] == "B") & (df_target["trade_date"] == dates[8])]
+        self.assertEqual(len(b_row_at_8), 1)
+        self.assertEqual(b_row_at_8.iloc[0]["label_end_date"], dates[10])
+
+        splitter = WalkForwardSplitter(
+            train_window_size=10, test_window_size=5, step_size=5,
+            mode="rolling", label_horizon=1, min_train_size=1
+        )
+
+        # --- 1. 精確路徑 (df 含 label_end_date)：B 在 dates[8] 的列必須被 Purge ---
+        train_idx, test_idx, meta = next(splitter.split(df_target))
+        train_rows = df_target.iloc[train_idx]
+        b_leaking_row_present = (
+            (train_rows["stock_id"] == "B") & (train_rows["trade_date"] == dates[8])
+        ).any()
+        self.assertFalse(
+            b_leaking_row_present,
+            "股票 B 於 dates[8] 的列 label_end_date == test_start_date，必須被 Purge"
+        )
+        # A 在 dates[8] 的列無停牌干擾，真實 label_end_date=dates[9] < test_start，應保留
+        a_row_present = (
+            (train_rows["stock_id"] == "A") & (train_rows["trade_date"] == dates[8])
+        ).any()
+        self.assertTrue(a_row_present)
+
+        # --- 2. Fallback 路徑 (無 label_end_date 欄位)：同一筆列會被誤判為安全，示範修正前缺陷 ---
+        df_no_label_end = df_target.drop(columns=["label_end_date"])
+        fallback_train_idx, _, _ = next(splitter.split(df_no_label_end))
+        fallback_train_rows = df_no_label_end.iloc[fallback_train_idx]
+        b_leaking_row_present_fallback = (
+            (fallback_train_rows["stock_id"] == "B") & (fallback_train_rows["trade_date"] == dates[8])
+        ).any()
+        self.assertTrue(
+            b_leaking_row_present_fallback,
+            "Fallback 近似法假設全域曆對齊，無法偵測股票 B 的個股停牌，"
+            "會誤將洩漏列判為安全 —— 此為 docstring 明示的精度限制，非本測試斷言錯誤"
+        )
+
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

執行環境：host（Python 3.10.11）—— 本檢查為純文件與 git 層次的靜態檢查，不涉及 ML/DB，符合 `CLAUDE.md` §13.0 host 允許用途。

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
Ran 164 tests in 7.604s

OK
```

（154 基線 + 5 個 T-PW + 1 個 PO 回報之停牌重現測試 + 3 個 `label_end_date` 測試 + 1 個本次補上的
`min_train_size` 跳過驗證測試 = 164；`tests.test_time_series_split` 單獨執行為 13 tests / OK，
`tests.test_feature_aggregator_alignment` 單獨執行為 8 tests / OK，逐檔結果已於 §0 步驟 4 交叉核對）

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  stock_prediction_system2_devcontainer-app-1 python -m py_compile \
  src/ml/time_series_split.py src/transform/feature_aggregator.py \
  tests/test_time_series_split.py tests/test_feature_aggregator_alignment.py
echo "PY_COMPILE_EXIT=$?"
```
`PY_COMPILE_EXIT=0`

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

**12/12 PRESENT** —— 全部走真實路徑，無 fallback／mock 降級。**本結果可支撐 ML／NLP／DB 路徑的宣稱**
（`CLAUDE.md` §13.3 對照表：容器內應全數 PRESENT，與此結果一致）。

### 3d. 資料庫（本次 SB1 未涉及）

`src/ml/time_series_split.py`、`src/transform/feature_aggregator.py` 純 pandas 運算，
無 `connect()` 呼叫（見 §5 Sentinel）。全套測試中唯一會連 DB 的路徑是既有 HERM-01~09（與 SB1 無關），
AFTER 快照（`SB1_STEP4_AFTER_SNAPSHOT.md`）已針對這 9 個測試單獨完成臨時 DB 綁定確認與執行；
本文件不重複那次的臨時 DB 程序。

---

## 4. 產出 3：檔案清單與逐檔授權稽核

```bash
git status --porcelain
```

```
 M doc/evidence/DECISIONS.md
 M doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md
 M doc/evidence/TRACEABILITY.md
 M doc/governance/PROJECT_STATUS.md
 M doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md
 M doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md
 M doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md
 M src/ml/time_series_split.py
 M src/transform/feature_aggregator.py
 M tests/test_feature_aggregator_alignment.py
 M tests/test_time_series_split.py
?? doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md
```

> **尚未 `git add`**，本表對照的是工作區（working tree）變更，非 staged 內容 ——
> PO 指示本次僅整理文件、不動 `git add`／`git commit`。

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `src/ml/time_series_split.py` | 在授權交付物內 | Master Plan Affected Components 明列 |
| `src/transform/feature_aggregator.py` | 在授權交付物內 | Master Plan Affected Components 明列 |
| `tests/test_time_series_split.py` | 在授權交付物內 | Master Plan Affected Components 明列 |
| `tests/test_feature_aggregator_alignment.py` | **原始 Master Plan 未列，本次 Gate B 整理時追加註記** | `label_end_date` 是 `feature_aggregator.py` 的新欄位，其既有測試類必然需要同步覆蓋；已於本次一併更新 Master Plan 的 Affected Components 欄位揭露此追加，**非隱藏**，但仍提請 PO 明確確認是否視為 SB1 範圍內 |
| `doc/evidence/DECISIONS.md` | 在授權交付物內 | `SB1_GATE_A_PROPOSAL.md` §5 明列（DEC-011 Verification 更新） |
| `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 在授權交付物內 | §5 明列（§3.3 基線保存 + DRIFT-012 狀態更新） |
| `doc/evidence/TRACEABILITY.md` | 在授權交付物內 | §5 明列（新增 Purged WF 追溯列） |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | 在授權交付物內，**但屬「Gate A 核准後才可修改」的文件** | §5 明列（§7 Brief 調整、§13 對齊）；提案原文寫「提請核准後才修改 Master Plan」，此處讀作「隨 Gate A 整體核准與後續步驟核准一併生效」，**提請 PO 確認此讀法正確** |
| `doc/governance/PROJECT_STATUS.md` | **不在 §5 明列清單，屬狀態追蹤慣例** | 與 SB1 步驟 2/3/4 的既有做法一致（持續同步「現在做到哪裡」），非新增授權範圍 |
| `doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md` | **不在 §5 明列清單，屬狀態追蹤慣例** | 標頭的步驟完成狀態列，非提案本文異動 |
| `doc/upgrade/gates/SB1_STEP1_BEFORE_SNAPSHOT.md` | **不在 §5 明列清單，屬狀態追蹤慣例** | §8「下一步」表同步，非 BEFORE 量測數據本身異動 |
| `doc/upgrade/gates/SB1_STEP4_AFTER_SNAPSHOT.md`（新檔） | 在授權交付物內 | `SB1_GATE_A_PROPOSAL.md` §4.3 步驟 4 明文要求的必要產出物 |

**經檢查未變更、但屬 §5 清單一員的項目**：`doc/upgrade/contracts/REMAINING_RISKS.md`。
§5 要求「新增一筆 digest 釘選風險」，經查該筆（RISK-014）**已存在**（非本次新增，推測為
GOV-03 相關工作留下），內容已涵蓋觸發條件與應對，故本次判斷無需變更，未列入異動清單。

---

## 5. 產出 4：格式／行尾夾帶偵測

```bash
git diff --numstat > /tmp/ns_raw.txt
git diff --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

```
（本次最終狀態：無輸出，WSDIFF_EXIT=0）
```

**過程揭露（步驟 3 執行期間發生、已修正）**：實作 `time_series_split.py` 時使用 `Write`
工具整檔重寫，該工具將原檔第 13 行「4 個空白字元的空行」正規化為真空行（單一位元組差異）。
本檢查於當時**即時偵測到**此落差（`numstat` 顯示 `149 14` vs `-w` 顯示 `148 13`），
以 Python 腳本精確定位該行後手動還原原始位元組，重新比對確認 `WSDIFF_EXIT=0`。
此為本檢查機制在本次 SB1 工作中**實際攔下過一次夾帶**的紀錄，同時作為本檢查的
known-FAIL 案例（見 §7）。

---

## 6. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 不可重跑原因 |
|------|---------|--------------------------|
| contract-check 11/11 PASS | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py` |
| 全套測試 164/164 PASS（container，15 套件齊備） | `VERIFIED THIS SESSION` | §3b 指令 |
| 依賴表 12/12 PRESENT | `VERIFIED THIS SESSION` | §3c 指令 |
| `py_compile` 4 檔 exit 0 | `VERIFIED THIS SESSION` | §3b 指令 |
| numstat vs `-w` 無落差（最終狀態） | `VERIFIED THIS SESSION` | §5 指令 |
| 靜態 `connect()` 呼叫點 10 處，未增加 | `VERIFIED THIS SESSION` | `grep -rn "\.connect(" src/loaders/db_writer.py src/ui/data_loader.py` |
| Runtime 攔截數 9 次，與 GOV-02 基線一致 | `VERIFIED THIS SESSION` | `SB1_STEP4_AFTER_SNAPSHOT.md` §6 完整腳本 |
| AFTER 快照 163/163 PASS，逐檔數量比對 BEFORE 零意外落差 | `VERIFIED THIS SESSION` | `SB1_STEP4_AFTER_SNAPSHOT.md` §6 |
| BEFORE 快照 154/154 PASS，Fold 洩漏基線可見 | `PREVIOUSLY VERIFIED` | 記錄位置：`SB1_STEP1_BEFORE_SNAPSHOT.md`（2026-08-24 執行），本次未重跑，僅引用其數字做比對基準 |
| GOV-02 runtime 攔截基線為 9 次 | `PREVIOUSLY VERIFIED` | 記錄位置：`DOCUMENT_DRIFT_REMEDIATION.md`「GOV-02 追加發現」節（2026-08-23），本次獨立重跑後數字相符 |
| Purge/Embargo/斷言的正確性（一般情形） | `VERIFIED THIS SESSION` | T-PW-01~06 + `test_fold_skipped_...`，共 7 個新測試，全數 PASS，見 §3b |
| feature_aggregator 的 `label_end_date` 精度優於全域近似 | `VERIFIED THIS SESSION` | `test_purge_uses_per_stock_label_end_date_for_calendar_misalignment` 直接對照兩條路徑的行為差異 |
| 所有生產路徑（evaluator/trainer）都已正確傳入 `label_end_date` 欄位給 `split()` | `NOT VERIFIED` | 未驗證範圍：本次僅驗證 `WalkForwardSplitter` 與 `FeatureAggregator` 本身的正確性；`src/ml/evaluator.py` 等實際呼叫端目前呼叫 `splitter.split(df)` 時，`df` 是否已含 `label_end_date` 欄位未逐一追蹤，PO 已同意延後至 Gate 3／trainer 管線整合時確認 |
| RISK-001（修正洩漏後模型準確率可能下降）的實際影響 | `NOT VERIFIED` | 未驗證範圍：需 Gate 3 以無污染 Panel Dataset 重跑 tournament 才能量測；本 SB 僅完成修正本身，不改變 RISK-001 的 `HYPOTHESIS` 狀態 |
| `SB1_GATE_A_PROPOSAL.md` §5 文件同步範圍已全數完成 | `VERIFIED THIS SESSION` | 見 §4 授權稽核逐項核對；`REMAINING_RISKS.md` 一項為既有 RISK-014 涵蓋，非本次新增 |

---

## 7. 產出 6：known-FAIL 案例對照表

| 檢查 / 機制 | known-FAIL 案例 | 實測結果 | 復原確認 |
|------------|----------------|---------|---------|
| `assert_no_boundary_leakage()` 邊界嚴格性（`>=` 而非 `>`） | 以 `train_label_end_dates=["2026-01-08","2026-01-10"]`, `test_start_date="2026-01-10"`（邊界相等）呼叫；並額外以記憶體內的「錯誤版本」（比較運算子改為 `>`）重跑同一輸入 | 正確版：`RuntimeError: Purge 邊界洩漏：train label_end_date (2026-01-10) >= test_start_date (2026-01-10)`；錯誤版：未拋出例外（原始輸出見本次工具紀錄） | 錯誤版僅存在於一次性 Python 腳本記憶體中，未寫入任何追蹤檔案；`git status` 於前後皆為同一組已知變更檔案，未受影響 |
| Purge／Embargo 機制（`label_end_date >= test_start_date` → 移除；停牌情境） | `test_purge_uses_per_stock_label_end_date_for_calendar_misalignment` 第 2 段：拿掉 `label_end_date` 欄位、退回 fallback 近似法，用同一筆停牌重現資料重跑 | Fallback 路徑下，股票 B 於 `dates[8]` 的洩漏列**未被 Purge**（`assertTrue(b_leaking_row_present_fallback)` 通過，證實這是真實會發生的失敗模式，不是假設） | 為測試套件的一部分，不涉及檔案還原 |
| `min_train_size` 跳過 Fold 的機制 | `test_fold_skipped_with_warning_when_purge_drops_below_min_train_size`：刻意設 `min_train_size=10`（恆高於 Purge 後可得的 9 天），驗證跳過行為與警告訊息內容 | `folds == []`；`logger.warning` 訊息含 `"Fold 0"`、`"9"`、`"10"`、`"不縮小 Purge 範圍"`，全數符合預期 | 為測試套件的一部分，不涉及檔案還原 |
| numstat vs `-w` 格式夾帶偵測 | **實際發生的organic 案例**：步驟 3 以 `Write` 整檔重寫 `time_series_split.py` 時，工具把原檔一行「4 個空白的空行」正規化為真空行 | `git diff --numstat` 回報 `149 14`，`-w` 版回報 `148 13`，兩者有落差，**本檢查當場攔到** | 已用 Python 腳本讀回原始位元組還原該行，重新執行本檢查確認 `WSDIFF_EXIT=0`；`git log`／HEAD 未變（工作區變更，非 commit） |
| `gate0_contract_check.py`（B1~B11 契約檢查） | **本次未重新示範**；該腳本 known-FAIL 能力已於 Gate 0（B4/B8 校正事件，見 `CLAUDE.md` §9A.1）獨立確認過 | — | `PREVIOUSLY VERIFIED`，不在本次範圍內重複驗證 |
| T-PW-01／T-PW-02（Purge 的 fallback 路徑日期截斷邏輯） | **PO 2026-08-25 要求補做，已完成**：暫時把 `split()` fallback 路徑的 Purge 比較運算子從 `>=` 改為 `>`（`src/ml/time_series_split.py` 當時的 L294），單行 Edit，未鏈式操作 | 兩測試皆變為 **ERROR**（被 `assert_no_boundary_leakage()` 的防禦性重驗攔下，而非測試自身斷言）：`RuntimeError: Purge 邊界洩漏 (Fold 0)：train label_end_date (2026-01-11) >= test_start_date (2026-01-11)`（T-PW-01）；`(2026-01-21) >= (2026-01-21)`（T-PW-02）。證實這是真實會被抓到的 off-by-one，且證實了 Purge 與防禦性斷言兩層防護皆有效 | 已用 Edit 改回 `>=`；`git diff --stat` 與注入前逐檔逐行數字完全相同（`src/ml/time_series_split.py \| 222 +++++++++++++++++--`，11 files changed, 675 insertions(+), 52 deletions(-)）；`numstat` vs `-w` 於還原後仍 `WSDIFF_EXIT=0`；還原後全套 164/164 PASS |
| T-PW-03（Embargo 排除區間邊界） | **PO 2026-08-25 要求補做，已完成**：上述 Purge bug 還原後，另對 Embargo 判斷式注入邊界 bug——`if any(lo < gidx <= hi ...)` 改為 `if any(lo < gidx < hi ...)`（漏掉區間右端點，單行 Edit） | `AssertionError: 8 != 7`（`fold1_meta["train_days"]`）—— 少排除了 embargo 區間最後一天，直接證實此測試真的會抓到「Embargo 右端點漏排除」這類邊界錯誤 | 已用 Edit 改回 `<=`；`git diff --stat` 與注入前完全相同；還原後全套 164/164 PASS |

---

## 8. PO 裁決紀錄

1. ~~T-PW-01/02/03 缺 known-FAIL 獨立示範~~ —— **PO 2026-08-25 要求補做，已完成**。
   見 §7 更新後的兩列：Purge 的 fallback 比較運算子（`>=`→`>`）與 Embargo 區間右端點
   （`<=`→`<`）分別注入 bug，T-PW-01/02/03 三個測試全數證實會 FAIL，且已用 Edit 逐一改回、
   `git diff --stat` 與注入前完全相同、還原後全套 164/164 PASS。
2. ~~`tests/test_feature_aggregator_alignment.py` 是否視為 SB1 授權範圍~~ —— **PO 2026-08-25 已核准**：
   視為 SB1 授權範圍內（`label_end_date` 是 `feature_aggregator.py` 新欄位，既有測試同步更新屬實作的自然延伸）。
3. ~~`SYSTEM_UPGRADE_MASTER_PLAN.md` 的修改時機讀法~~ —— **PO 2026-08-25 已核准**：
   「隨 Gate A 核准與後續步驟核准一併生效」讀法正確，不需要另一輪核准。
4. **生產路徑尚未逐一確認是否正確傳入 `label_end_date`**（§6 證據標籤表 `NOT VERIFIED` 項）：
   已依 PO 先前指示延後至 Gate 3／trainer 管線整合時處理，此處僅重申以免遺漏。

**commit 授權**：本文件為送審文件，不代表 commit 已獲授權。§8 事項 1～3 已於 2026-08-25 全數解決；
若 PO 決定放行，請明確指出授權範圍（哪些檔案）；`gate-submit` skill 的自檢流程第 3～5 步
（`git add`、逐檔稽核、格式偵測）將在取得授權後於 commit 前重新針對實際 staged 內容執行一次。
