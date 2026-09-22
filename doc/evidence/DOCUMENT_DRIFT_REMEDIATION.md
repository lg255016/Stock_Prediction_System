# DOCUMENT_DRIFT_REMEDIATION.md — 文件與證據漂移對照表

> Gate 0 交付物 A  
> 日期: 2026-08-22  
> 狀態: READY FOR PO REVIEW  
> 稽核基準: forensic code audit 2026-08-21, HEAD `680de6c`

---

## 概述

本表列出 2026-08-21 法證式程式碼稽核（forensic code audit）所發現的「文件宣稱 vs. 程式碼/倉庫實際狀態」漂移項目。每筆漂移均標明嚴重度、原始文件位置、程式碼證據與建議修復工單。

### 嚴重度定義

| 等級 | 定義 |
|------|------|
| **CRITICAL** | 影響 ML 推論正確性、資料契約完整性或系統架構真實性 |
| **HIGH** | 影響可追溯性、文件可信度或開發者認知正確性 |
| **MEDIUM** | 影響維運效率、邊界正確性或開發者體驗 |

---

## 漂移對照表

| ID | Severity | Document | Location | Documented Claim | Code/Repo Fact | Evidence Label | Remediation | Owner Gate/SB |
|----|----------|----------|----------|------------------|----------------|----------------|-------------|---------------|
| DRIFT-001 | **CRITICAL** | PRD, SDD, DECISIONS.md (DEC-006, DEC-007, DEC-008, DEC-009), CHALLENGES.md | PRD:L65,L68; SDD:L229,L246; DECISIONS.md:L551,L577,L607,L617,L654,L677,L701,L724,L729,L763; CHALLENGES.md:L211（**修正範圍已於 UG-G1-SB5 擴充**：原登錄僅 5 處，2026-08-26 對 `doc/evidence/` 完整 grep 後確認共 15 處，見 DEC-022） | 「18 欄位特徵契約」/ `ALL_MULTIMODAL_FEATURE_COLS` 為 18 項 | `src/ml/model_trainer.py:L17-41` 實際定義 **17** 項特徵（5 基礎價量 + 2 技術動能 + 2 風險波動 + 4 社群輿情 + 4 時序滯後 = 17）。註解本身也寫「完整 18 欄位」但清單只有 17 行。 | `VERIFIED — code count = 17` | 導入版本化特徵契約：`LEGACY_17`（現狀 17 欄）、`CORE_16`（移除 OHLCV 中的 open/high/low 後）、`COMMENT_ENHANCED_19`（加入 comment_volume_ratio 與 comment_polarization 後）。所有文件統一引用契約名稱而非硬編碼數字。 | **CLOSED（UG-G1-SB5）**：`doc/spec/`（PRD／SDD）15 處中的 4 處直接改為引用 `LEGACY_17`；`doc/evidence/DECISIONS.md`（10 處）與 `CHALLENGES.md`（1 處）依 PO 決策點 1（方案 C）原文不動、逐點插入 `📌 SB5 補充註記`，並於 `DECISIONS.md` 新增 DEC-022 總覽索引 |
| DRIFT-002 | **CRITICAL** | SDD | `SDD:L68,L77-79` | `trend_discover.py` 標記「⏳ 規劃中」；`model_trainer.py` 標記「⏳ 規劃中 - Phase 3」；`dashboard.py` 標記「⏳ 規劃中 - Phase 4」 | `src/extractors/trend_discover.py` 已實作且有測試；`src/ml/model_trainer.py` 已實作 `MultiModalTrainer` 並通過測試；`src/ui/` 已實作完整 Streamlit 儀表板（含 `components.py`, `data_loader.py` 等）。全專案共 **154** 項測試通過。 | `VERIFIED — modules exist, 154 tests pass` | 更新 SDD 模組狀態為「✅ 已實作」，補充實作版本與對應 Gate/Phase 資訊。 | **CLOSED（UG-G1-SB5）**：`model_trainer.py`／`app.py` 已於 SB3 收尾同步改為 ✅；`trend_discover.py`（本次重新核對發現的剩餘 1 處，位於「收集層」章節，SB3 未覆蓋）已於 SB5 改為 ✅。全部 3 處均已修正 |
| DRIFT-003 | **CRITICAL** | db_writer.py / Feature Store 契約 | `src/loaders/db_writer.py:L416-438` | 特徵工程產出 17 欄位（文件宣稱 18），Feature Store 目標為 27 欄位完整持久化 | `db_writer.py:L416-438` 僅寫入 **7** 個欄位至 `daily_ml_features`：`trade_date, stock_id, close_price, volume, article_count, sentiment_mean, sentiment_3d_ma`。註解明確寫「擷取對應 daily_ml_features schema 定義的 7 個主要欄位（避免 18 特徵欄位數量不匹配）」。 | `VERIFIED — INSERT INTO 只含 7 columns` | Gate 2 Schema Migration（UG-G2-SB1）擴充 `daily_ml_features` 至完整特徵契約，配合 `ALTER TABLE ADD COLUMN` 與 `schema_version` 機制。 📌 **UG-G2-SB1 補充註記（2026-08-26）**：本列「27 欄位」為 Gate 0 早期數字，`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 V8 修正說明已改為權威值 **29 欄**（含 `source_status`／`label_reason` 兩個 metadata 欄，`DB_MIGRATION_PLAN.md` §4.2）。本列原文保留不動（`CLAUDE.md` §16.1），執行時一律以 29 為準，見 `G2_SB1_GATE_A_PROPOSAL.md` §6、§7 決策點 2。 | UG-G2-SB1（Gate A 已核准，實作中） |
| DRIFT-004 | **HIGH** | PROJECT_STATUS.md | `PROJECT_STATUS.md:L8` | 「133/133 tests PASS」 | `grep -r "def test_" tests/` 統計實際測試函式數量為 **154**。最新 commits 新增了 real article pipeline tests 等多項測試。 | `VERIFIED — grep count = 154` | 更新 PROJECT_STATUS.md 測試計數為 154/154，並新增各測試套件明細。 | **CLOSED（UG-G1-SB5）**：真實現況比登錄時更複雜——`PROJECT_STATUS.md` §0.4（現行狀態區塊）當時寫的是 SB1 收尾時的「164」，SB2／SB3／SB4 之後未再同步，落後真實值（`grep -ch "def test_" tests/test_*.py` 現行為 200）。已改為「200」並改採指令化免責聲明寫法（不寫死會再度過期的數字）。§1 之「133/133」為刻意保留之 PRE_CODEX 舊紀錄快照，依既有慣例不修正 |
| DRIFT-005 | **HIGH** | DECISIONS.md (DEC-003) | `DECISIONS.md:L197-200` | DEC-003 應包含完整的 NLP Completion Contract 決策（Options, Decision, Rationale, Affected Components, Verification） | L197「NLP Completion Contract」章節僅殘留 Option A 單行描述（「非 fuzzy SnowNLP result 可完成」），其後直接跳至 L201 的 DEC-004，缺少 Decision、Rationale、Affected Components 與 Verification 區塊。 | `VERIFIED — content ends abruptly at L199` | 從 Git 歷史或原始草稿還原 DEC-003 NLP Completion Contract 完整內容。 | **CLOSED（UG-G1-SB5，改採 PO 決策點 1 方案 C）**：Git 歷史查無可還原之原始草稿；PO 裁示 `DECISIONS.md` 既有 ADR 不回改原文，改為緊接截斷處插入 `📌 SB5 補充註記`，指向現行權威依據（`CLAUDE.md` §7.2 與三份 NLP 測試檔），非本欄原建議之「還原內容」 |
| DRIFT-006 | **HIGH** | DECISIONS.md (DEC-004) | `DECISIONS.md:L315-432` | DEC-004 應為單一連貫決策記錄 | L315-432 包含 DEC-004 Context/Problem/Alternatives/Decision/Rationale/Trade-offs/Affected Components/Verification 的 **完整重複副本**（與 L206-313 的內容幾乎相同，僅細節措辭略有不同）。造成文件長度膨脹且容易誤引。 | `VERIFIED — diff shows duplicate structure` | 移除 L315-432 的重複內容，保留 L206-313 的權威版本。 | **CLOSED（UG-G1-SB5，改採 PO 決策點 1 方案 C）**：`DECISIONS.md` 既有 ADR 不刪除既有內容；改為在權威版本（L201-313）結尾與草稿版本（L315-432）開頭之間插入 `📌 SB5 補充註記`，明確標示下方為過期草稿、上方為權威版本，非本欄原建議之「移除重複內容」 |
| DRIFT-007 | **HIGH** | DECISIONS.md (DEC-006, DEC-007, DEC-008, DEC-009) | `DECISIONS.md:L551,L577,L607,L617,L654,L677,L701,L724,L729,L763`（修正範圍擴充說明同 DRIFT-001） | DEC-006:「FeatureAggregator 輸出 18 項標準特徵矩陣」; DEC-007:「多模態 18 欄位特徵」「多模態 18 特徵」 | 同 DRIFT-001：實際為 17 項。此處文件引用與程式碼不一致。 | `VERIFIED — cross-ref DRIFT-001` | 統一改用版本化契約名稱（`LEGACY_17` / `CORE_16` / `COMMENT_ENHANCED_19`），消除硬編碼數字。 | **CLOSED（UG-G1-SB5）**：與 DRIFT-001 同批處理，見該列 Remediation 欄與 `DECISIONS.md` DEC-022 |
| DRIFT-008 | **HIGH** | components.py | `src/ui/components.py:L128-141` | 排行榜應反映真實 Walk-Forward 實驗結果 | `render_tournament_leaderboard()` 使用 **硬編碼 Python dict list** 作為 8 組實驗排行榜資料（L129-138），數據為靜態假值而非從模型訓練結果或資料庫動態載入。 | `VERIFIED — static dict at L129-138` | 改為從 `models/` 目錄載入最新實驗 metadata JSON，或從 DB 查詢歷史訓練結果，實現動態排行榜。 | UG-G1-SB3 |
| DRIFT-009 | **HIGH** | data_loader.py | `src/ui/data_loader.py:L31-40` | UI 應明確區分 DB 即時資料與離線模擬資料 | `generate_mock_stock_features()` 在 DB 連線失敗時被靜默呼叫作為 fallback，使用者無法從 UI 辨別當前顯示的是真實資料還是模擬資料。函式註解寫「供離線演示與 DB Fallback」但無任何告警機制。 | `VERIFIED — 已修正（2026-08-25，尚未 commit）：src/ui/data_loader.py 逐一驗證確認四個公開函式皆已改為 (value, DataMode) 回傳，ERROR 不再自動呼叫 generate_mock_stock_features()` | **已修正，採 DEC-012 方案 B（PO 2026-08-25 裁示）**：與本列原建議的「加告警橫幅但保留自動 fallback」不同——PO 判定連線失敗時**不應**自動顯示模擬資料，改為 ERROR 模式僅顯示「⚠️ 資料來源目前無法連線」，不渲染任何數值；`demo=True` 成為 DEMO 模式的唯一顯式入口。證據見 `SB2_STEP3_IMPLEMENTATION_REPORT.md`、DEC-012。 | UG-G1-SB2 — **CLOSED**（commit `414fcc81fccde57d84e883b4a44a9b0e50465500`） |
| DRIFT-010 | **HIGH** | Repository root | Repository root | 專案應有 README.md 提供快速入門指引 | `ls README.md` 回傳 exit code 2（檔案不存在）。整個 Repository 沒有任何頂層 README 文件。 | `VERIFIED — file not found` | 建立 `README.md`，涵蓋專案簡介、架構圖、快速啟動、測試執行與貢獻指引。 | **CLOSED（UG-G1-SB5）**：已建立 Repository 根目錄 `README.md`，涵蓋架構概覽、Dev Container 快速啟動、測試執行指令與文件地圖指標 |
| DRIFT-011 | **HIGH** | Database / Schema | `database/schema.sql`, `src/loaders/db_writer.py` | 系統應具備資料庫遷移機制以支援 Schema 演進 | 專案中 `grep -r "schema_version\|ALTER TABLE" *.py *.sql` 回傳零結果。無任何 migration framework（如 Alembic）、`ALTER TABLE` 語句或 `schema_version` 追蹤表。Schema 變更只能透過 drop-and-recreate 執行。 | `VERIFIED — no migration infrastructure` | 導入輕量 migration 機制：建立 `schema_version` 表 + 有序 migration 腳本目錄 `database/migrations/`，或整合 Alembic。 | UG-G1-SB4 |
| DRIFT-012 | **MEDIUM** | feature_aggregator.py / time_series_split | `src/transform/feature_aggregator.py:L459` | Target label 生成與 Walk-Forward 切分邊界應無洩漏 | `append_target_labels()` 使用 `shift(-1)` 在完整 DataFrame 上生成 `target_next_close`（L459），此操作在 Walk-Forward splitter 切分邊界處，最後一筆訓練資料的 target 可能洩漏測試集首筆收盤價。需驗證 splitter 是否在 target label 附加 **之後** 切分（安全）還是 **之前** 切分（洩漏風險）。 | `VERIFIED — 洩漏已於 SB1_STEP1_BEFORE_SNAPSHOT.md §5.1 實測確認存在（gap 全為週末、交易日隔離為零），並於 UG-G1-SB1 步驟 3 修正` | **已修正（2026-08-24/25，尚未 commit）**：`WalkForwardSplitter` 新增 `label_horizon`／`embargo_days`／Purge；`generate_target_labels()` 新增 `label_end_date` 欄位供逐列精確 Purge 判定。稽核與修正證據見 `SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、DEC-011。 | UG-G1-SB1 — **CLOSED**（commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`） |
| DRIFT-013 | **MEDIUM** | PROJECT_STATUS.md | `PROJECT_STATUS.md:L23` | 「Current HEAD: `a41a9ea`」 | `git log --oneline -1` 顯示實際 HEAD 為 **`680de6c`**（`test(ui): add comprehensive real article pipeline tests and sync traceability`）。文件落後至少 5 個 commit。 | `VERIFIED — HEAD mismatch` | 更新 PROJECT_STATUS.md Git State 區塊，反映最新 HEAD 與 branch 狀態。建議加入「此欄位為手動快照，實際狀態以 `git log` 為準」的免責聲明。 | **重新分類為排除（UG-G1-SB5，2026-08-26 重新核對）**：`PROJECT_STATUS.md` 文件開頭（§0 前言）已明文宣告「§1 以下為 PRE_CODEX 時期的舊紀錄」，本欄所指的「Current HEAD」欄位（現行位置為「## 2. Git State」）落在「§1 以下」範圍內，與 §1 的「133/133」測試計數同屬同一份刻意保留的舊快照，非現行追蹤欄位（現行 Git 狀態改由 §0.2 的逐 SB commit hash 表追蹤，已隨每個 SB 收尾更新）。依 PO 已核准之慣例（同一份文件內 §1 快照數字不修正），本項**不予修正**，維持原文 `a41a9ea` 不動 |
| DRIFT-014 | **MEDIUM** | ptt_scraper.py / 推噓文解析 | `src/extractors/ptt_scraper.py:L57-65` | PTT 文章應解析完整推噓文資訊以支援 comment feature engineering | `ptt_scraper.py:L57` 僅從列表頁的 `div.nrec` 擷取推噓計數（`push_tag`），未進入文章內頁解析個別推噓文的內容、類型（推/噓/→）與時間戳。`push_count` 為字串型態的粗略統計。 | `VERIFIED — list page nrec only, no inner page parsing` | Gate 2 擴充 PTT scraper 支援文章內頁推噓文解析，提取 `comment_type`（推/噓/→）、`comment_content` 與 `comment_time`，供 `COMMENT_ENHANCED_19` 特徵契約使用。 | UG-G2-SB2 |
| DRIFT-015 | **CRITICAL** | DECISIONS.md (DEC-007), TRACEABILITY.md, SYSTEM_UPGRADE_MASTER_PLAN.md | DEC-007「Multi-Model Tournament & Alpha Attribution Protocol」；TRACEABILITY.md 之「8組平行實驗 Alpha 歸因」列 | 宣稱以 4 大模型（Logistic Regression／Random Forest／LightGBM／XGBoost）× 2 特徵集 = 8 組平行對照實驗，進行橫向競技與 Alpha 歸因 | GOV-02 實測（2026-08-23）：在 host 環境下 `PureTechnicalModelFactory` 對 `lightgbm` 與 `xgboost` **回傳同一個 `_FallbackTreeEnsembleClassifier` 類別**，`random_forest` 亦為同一 fallback 家族，僅 `logistic_regression` 為相異的 `_FallbackLinearClassifier`。四個模型名稱實際只對映**兩種**相異實作。容器內（15 套件齊備）則正確回傳 `sklearn.LogisticRegression`／`sklearn.RandomForestClassifier`／`lightgbm.LGBMClassifier`／`xgboost.XGBClassifier`。 | `VERIFIED — GOV-02 型別實測，host vs container 對照` | **影響範圍**：任何在 host 產出的模型橫向比較、Alpha 歸因與冠軍模型選拔結論**在方法論上不成立** —— 不是精度誤差，而是「比較」本身不存在（同一實作被當成三個不同模型比較）。須明確標註 DEC-007 的證據基礎僅在 dev container 內成立；所有既有 tournament 數據若來自 host，必須標為 `NOT VERIFIED` 並於容器內重跑後方可引用。 | **文件標註部分 CLOSED（UG-G1-SB5）**：已於 `DECISIONS.md` DEC-007 Verification 段末插入 `📌 SB5 補充註記`，明確標註 host 環境下 4 模型實際只有 2 種相異實作、方法論僅在 dev container 內成立。**容器內重跑產出真實 tournament 數據**仍待 Gate 3（UG-G3-SB3/SB7），非 SB5 範圍 |
| DRIFT-016 | **HIGH** | requirements.txt | `requirements.txt:L1-15` | GOV-02 將 dev container 定為正式測試環境並建立基線，隱含「依賴組合可重現」 | 實測 15 個套件中：**6 個完全無版本約束**（`requests`, `beautifulsoup4`, `pandas`, `yfinance`, `psycopg2-binary`, `tenacity`）；**9 個僅有下界無上界**（`jieba>=0.42.1` 等）；**0 個有上界**；**0 個精確鎖版（`==`）**。同一份 `requirements.txt` 在 host 與 container 已解析出主版本差距（`pandas` 2.3.3 vs 3.0.5）。 | `VERIFIED — requirements.txt 逐行解析` | **風險性質**：與 host 靜默降級同型 —— `pip install -r requirements.txt` 在未來任一時點可能裝出不同版本組合，使今日基線失效，且**不會產生任何訊號**（測試數與結果可能完全相同）。**GOV-03 已加入 `requirements.lock.txt`（commit 見 GOV-03），但 lock 是「緩解」而非「根治」**：
| DRIFT-017 | **HIGH** | Repository 完整性／版控紀律 | `tests/__pycache__/test_stationary_features_and_panel.cpython-310.pyc`（已於 2026-08-23 刪除） | 版控歷史應完整反映曾執行過的工程工作；`tests/` 內的測試應可追溯 | 發現一個**孤兒 bytecode**：無對應 `.py`、`git log --all` 全歷史查無此檔 —— **從未進過版控**。刪除前萃取其程式碼物件，內容為：
| DRIFT-018 | **CRITICAL** | `src/ui/components.py`；`TRACEABILITY.md` | `components.py:129-138`（`render_tournament_leaderboard`）；`TRACEABILITY.md:164` | 「8 組平行實驗 Alpha 歸因：量化證明社群情緒融合模型相較純價量控制組帶來顯著之 ΔF1 與 ΔReturn 超額報酬」；UI 排行榜呈現冠亞季軍與各項績效指標 | 排行榜的 8 個數值存在**三個互相獨立的矛盾**：
**(1) 排名與自身數字牴觸** —— 冠軍 Random Forest（Macro F1 `0.5820`／命中率 `58.4%`／報酬 `+8.2%`）在**全部三個指標**上同時輸給亞軍 LightGBM（`0.5910`／`59.2%`／`+9.6%`）與季軍 XGBoost（`0.5860`／`58.8%`／`+8.9%`）。
**(2) 同一實作有兩個分數** —— 依 DRIFT-015，host 上 `lightgbm` 與 `xgboost` 回傳同一個 `_FallbackTreeEnsembleClassifier`（實測 `type(a) is type(b) == True`），同一段程式碼卻被記錄為 `0.5910` 與 `0.5860`。
**(3) 無任何實驗產出物連結** —— 全部為 UI 檔內的字面常數；`render_tournament_leaderboard` 不讀取任何檔案、JSON 或 artifact（實測確認）。 | `VERIFIED — 三項矛盾逐一實測` | **標註原則（PO 2026-08-24 裁示）**：不得標為「含洩漏」—— 該說法預設它們是有已知瑕疵的**真實量測**，但目前沒有任何證據支持它們曾被量測出來。**應標註為「未經驗證的展示值，證據待補」**。本專案不宣稱這些數字是捏造的（無證據），但**主張它們是量測結果的一方負舉證責任，而目前舉不出來**。
**歸屬修正（PO 2026-08-25 裁示）**：原歸屬 UG-G1-SB2 僅完成「標註為未經驗證展示值」的標籤化處理，
三個矛盾本身未修正；SB2 已於 2026-08-25 CLOSED。實際修正改記於 **UG-G1-SB3**。

**UG-G1-SB3 修正現況（2026-08-26，尚未 commit）**：新增 `load_tournament_results()`／
`render_tournament_leaderboard(data, mode)`，排行榜資料源改為讀取
`models/artifacts/tournament_results.json`（由 `MLEvaluator.evaluate_tournament()` 產出）。
矛盾 (1)(3) **結構上已消除**——不再有任何字面常數，排名邏輯改為由真實分數即時排序；
矛盾 (2) 待真實 artifact 產出後才能實測確認（container 內 lightgbm／xgboost 是不同真實實作，
理論上不會重現）。**真實 artifact 尚未產出**——`models/` 目錄不存在，資料量不足以支撐
`WalkForwardSplitter` 預設 window（見 `SB3_GATE_A_PROPOSAL.md` §3.1 方案 B 與
`SB3_GATE_B_SUBMISSION.md` §6 NOT VERIFIED 項）；目前 UI 正確顯示 `DataMode.EMPTY`
「尚未完成模型競技」，不是繞過驗收。 | UG-G1-SB3 |
・類別 `StationaryFeaturesAndPanelTests`
・4 個測試 `test_stationary_features_computation`(L51)、`test_target_label_deadband_filtering`(L66)、`test_aggregate_cross_sectional_dataset`(L80)、`test_trainer_fit_with_stationary_features`(L96)
・符號 `STATIONARY_MULTIMODAL_FEATURE_COLS`（現行程式碼中不存在；現行為 `ALL_MULTIMODAL_FEATURE_COLS`）
・模組 docstring：「特徵平穩化、死區過濾標籤與跨截面面板資料集測試 **(SB-OPT1)**」
**`SB-OPT1` 這個 Small Batch 編號在任何現行文件與完整版控歷史中均不存在。**「死區過濾」概念僅出現於 `ML_ACCURACY_RESEARCH_AND_SYSTEM_IMPACT_ASSESSMENT.md:91` 的「預計修改之核心模組清單」，屬**尚未實作**的研究建議。 | `VERIFIED — pyc 解析 + git log --all -S 全歷史搜尋` | **已處理**：孤兒 bytecode 已刪除；全 repo 複掃確認 84 個 `.pyc` 中孤兒歸零，無其他未追蹤產物。
**登錄的觀察**：本專案曾有**在版控之外執行測試工作**的先例。該次工作的主題（平穩化特徵、死區過濾標籤、跨截面 Panel）正是目前仍標記為 `PLANNED` 的 CORE_16 新增特徵（UG-G2-SB1）與 Panel Dataset（UG-G3-SB2）。原始碼無法救回，只能確認「做過」而無法確認「做成什麼樣」。
**風險含意**：專案經手過兩個前任 Agent 團隊，此類版控外工作可能不只一次；任何「這個功能還沒做過」的假設都應以版控證據為準，不得僅憑文件狀態欄。 | 已於 GOV-03 後處理完畢（清除 + 登錄）；持續性防護待 PO 決定是否需要 |
lock 只保證「照 lock 安裝會得到已驗證的版本組合」，並未修正 `requirements.txt` 本身的約束缺口 —— 任何人若仍執行 `pip install -r requirements.txt`（而非 lock），依舊會裝出未受控的版本組合。
**意圖檔的約束補強屬另案，範圍與策略由 PO 決定**（可能選項：`==` 全鎖／補上界／改以 lock 為唯一安裝來源並將 requirements.txt 降為文件）。 | 緩解：GOV-03（lock）；根治：待 PO 指定 |

---

## 統計摘要

| 嚴重度 | 數量 |
|--------|------|
| CRITICAL | 5 |
| HIGH | 10 |
| MEDIUM | 3 |
| **合計** | **18** |

> DRIFT-015、DRIFT-016 為 GOV-02 容器基線量測（2026-08-23）追加，非 2026-08-21 原始稽核所發現。

---

## 修復工單對照

| Owner Gate/SB | 漂移 ID | 簡述 |
|---------------|---------|------|
| UG-G1-SB1 — **CLOSED**（commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`） | DRIFT-012 | 時序邊界洩漏稽核與修正 |
| UG-G1-SB2 — **CLOSED**（commit `414fcc81fccde57d84e883b4a44a9b0e50465500`） | DRIFT-009 | Silent mock fallback 告警 → DEC-012 方案 B 移除自動 fallback |
| UG-G1-SB3 — **CLOSED**（commit `61016ee19c07caec990b51563f21b7f6571412b9`） | DRIFT-008 | 靜態排行榜改動態 |
| UG-G1-SB4 — **CLOSED**（階段一 commit `d2a4d4894328d2ef5e186aa2aa45ec02a0fdea0b`；階段二 commit `0fdb9c50c774388b42842075bdf69b2c12e666e0`） | DRIFT-011 | DB migration 機制 |
| UG-G1-SB5 — **CLOSED**（見 `SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 回填之 commit hash） | DRIFT-001, DRIFT-002, DRIFT-004, DRIFT-005, DRIFT-006, DRIFT-007, DRIFT-010 | 文件同步與修復（特徵契約名稱裸寫改註記／直接引用、SDD 模組狀態、測試計數、DEC-003／DEC-004 補充註記、README） |
| 排除，維持不動 | DRIFT-013 | 「Current HEAD」欄位落在 `PROJECT_STATUS.md` §1 以下的 PRE_CODEX 舊快照範圍內，依既有慣例不修正（詳見上表 DRIFT-013 列） |
| UG-G2-SB1 | DRIFT-003 | DB Schema Migration 擴充 daily_ml_features |
| UG-G2-SB2 | DRIFT-014 | PTT 內頁推噓文解析 |
| UG-G1-SB5（文件標註部分 **CLOSED**） + UG-G3-SB3/SB7（容器內重跑，未開始） | DRIFT-015 | DEC-007 證據基礎標註 + 容器內重跑 tournament |
| GOV-03（緩解）／待 PO 指定（根治）| DRIFT-016 | `requirements.lock.txt` 已加入為緩解；意圖檔約束補強待 PO 決定 |
| 已處理（2026-08-23）| DRIFT-017 | 孤兒 bytecode 已清除並登錄；版控外工作先例已記錄 |
| UG-G1-SB3 — **CLOSED**（commit `61016ee19c07caec990b51563f21b7f6571412b9`；讀取機制已完成，矛盾(2)待真實 artifact 產出後才能實測） | DRIFT-018 | 排行榜三項矛盾；歸屬由 UG-G1-SB2 修正為 UG-G1-SB3（SB2 僅標籤化，未實際修正） |

---

## GOV-02 追加發現：測試封閉性（Test Hermeticity）

> **來源**：GOV-02 容器內測試基線量測，2026-08-23。
> **性質**：本節為**只列不修**的發現登錄。GOV-02 授權明文禁止修改 `tests/` 與 `src/`。
> **量測方法**：以可攔截的 sentinel `psycopg2` 佔位 `sys.modules`，在 dev container 內
> （Python 3.14.6、15 套件齊備、憑證齊備、DB 在旁）執行全套測試並記錄所有 `connect()` 呼叫堆疊。

### 核心發現

先前三輪被引用的 `154 tests / OK`（含 Gate 0 關閉裁決、`TRACEABILITY.md` §3A.2、GOV-01 完成報告）
**全部執行於 Windows host**，該環境 15 個套件僅安裝 6 個。

其中 **9 個測試呼叫不具封閉性（non-hermetic）**：它們的行為取決於執行環境是否具備資料庫憑證，
以及資料庫當下的內容。在 host 上這一點**永遠測不出來** —— 因為 `dotenv` 是 stub、
`load_dotenv()` 空轉、憑證從未載入，連線在被呼叫前就注定失敗。

### 不具封閉性的測試清單

| ID | 測試 | 觸發的程式碼路徑 | SQL 性質 |
|----|------|-----------------|---------|
| HERM-01 | `test_operational_ux.py:74` `test_load_ai_discovered_keywords_fallback` | `src/loaders/db_writer.py:270` `fetch_ai_discovered_keywords` | SELECT |
| HERM-02 | `test_real_articles_pipeline.py:130` `test_load_stock_articles_returns_clean_contract` | `src/ui/data_loader.py:230` `_fetch_real_stock_articles_from_db` | SELECT |
| HERM-03 | `test_ui_contracts.py:77` `test_load_stock_features_returns_18_columns` | `src/ui/data_loader.py:145` `_fetch_real_stock_features_from_db` | SELECT |
| HERM-04 | `test_ui_contracts.py:89` `test_load_stock_articles_returns_expected_columns` | `src/ui/data_loader.py:230` | SELECT |
| HERM-05 | `test_ui_contracts.py:96` `test_get_champion_predictor_inference` | `src/ui/data_loader.py:145` | SELECT |
| HERM-06 | `test_ui_contracts.py:152` `test_load_thematic_radar_data_structure` | `src/ui/data_loader.py:417` `load_thematic_radar_data` | SELECT |
| HERM-07 | `test_ui_contracts.py:174` `test_render_price_sentiment_candlestick_chart_structure` | `src/ui/data_loader.py:145` | SELECT |
| HERM-08 | `test_ui_contracts.py:179` `test_render_pnl_equity_curve_chart_structure` | `src/ui/data_loader.py:145` | SELECT |
| HERM-09 | `test_ui_contracts.py:222` `test_render_thematic_radar_component_structure` | `src/ui/data_loader.py:417` | SELECT |

每次呼叫的連線參數皆為 `KEYS=database,host,password,port,user` —— 憑證確實被載入並傳入。
全部為唯讀 `SELECT`；經全檔掃描確認**無任何** `INSERT`／`UPDATE`／`DELETE`／`TRUNCATE`／`ALTER`。
（掃描一度誤報 `DROP`，查證為 pandas 的 `reset_index(drop=True)` 與 `drop_duplicates()`，非 SQL。）

### 衍生問題

| ID | Severity | 問題 | 證據 | Remediation |
|----|----------|------|------|-------------|
| HERM-A | **HIGH** | 9 個測試行為隨環境憑證與 DB 內容改變，不具封閉性 | 上表；sentinel 堆疊紀錄 | **已修正（2026-08-25）**：9 個測試皆已改為 `unittest.mock` 隔離，不再連真實 DB。GOV-02 sentinel 重跑確認 runtime `connect()` 攔截數由 9 降為 0（PO 與 PM 各自重跑確認一致）。證據見 `SB2_STEP3_IMPLEMENTATION_REPORT.md`。 | UG-G1-SB2 — **CLOSED**（commit `414fcc81fccde57d84e883b4a44a9b0e50465500`） |
| HERM-B | **HIGH** | `test_load_ai_discovered_keywords_fallback` 名稱明示測 fallback，但在有真實資料的環境下測到的**不是** fallback 路徑 | `test_operational_ux.py:74` | **已修正**：拆為 `test_load_ai_discovered_keywords_returns_real_mode_when_db_has_data`（mock 出 REAL 路徑）與 `test_load_ai_discovered_keywords_falls_back_when_db_fails`（mock 出 ERROR 路徑），兩者皆確定性命中各自宣稱的路徑，不再受環境影響。 | UG-G1-SB2 — **CLOSED**（commit `414fcc81fccde57d84e883b4a44a9b0e50465500`） |
| HERM-C | **HIGH** | `test_load_stock_features_returns_18_columns` 對 live 資料硬斷言 `assertEqual(len(df), 30)`；真實 DB 若該股不足 30 日資料即失敗，且無法區分「程式壞了」與「當日資料不足」 | `test_ui_contracts.py:77` | **已修正**：改名為 `test_load_stock_features_returns_real_mode_with_mocked_db`，斷言改為「mock 回傳幾列，就該回傳幾列」（n_rows=5），不再依賴真實 DB 當日資料量。 | UG-G1-SB2 — **CLOSED**（commit `414fcc81fccde57d84e883b4a44a9b0e50465500`） |
| HERM-D | **MEDIUM** | 同一測試名稱中的「18 欄位」為 DRIFT-001 的過期數字（實際 `ALL_MULTIMODAL_FEATURE_COLS` 為 17，目標契約為 29） | 同上；參照 DRIFT-001 | **CLOSED（UG-G1-SB5）**：測試名稱已隨 HERM-C 改名為 `test_load_stock_features_returns_real_mode_with_mocked_db`，不再含「18」字樣；本項與 DRIFT-001／007 同批處理 |
| HERM-E | **HIGH** | 靜默回退：`src/ui/data_loader.py:214-215` 以 `logger.debug` 吞掉連線例外後 `return None`，上層改用 mock，測試照樣通過。與已登錄的 DRIFT-009 同一根因 | `data_loader.py:214-215` | **已修正**：`logger.debug` 提升為 `logger.warning`；例外不再被吞掉後靜默回傳 `None`，改為拋出 `DataSourceError` 並由公開函式明確轉換為 `DataMode.ERROR`，上層不再自動改用 mock（DEC-012 方案 B）。 | UG-G1-SB2 — **CLOSED**（併入 DRIFT-009，commit `414fcc81fccde57d84e883b4a44a9b0e50465500`） |

### 環境降級的可見性差異

| 情境 | 是否可見 |
|------|---------|
| host 缺 `numpy` → 13 檔 Import Error → 只剩 66 tests | **看得見**（測試數驟降） |
| host 缺 `sklearn`／`lightgbm`／`xgboost` → 走 fallback 實作 | **看不見**（模組內 `try/except ImportError` 條件式 import，18 檔照樣載入、154 tests 照樣全過） |

`src/ml/baseline_models.py:97-145` 與 `src/ml/model_trainer.py:100-108` 的條件式 import
使降級不留任何痕跡於測試輸出。

### GOV-02 衍生的兩筆主表 DRIFT

本次量測另外觸發兩筆登錄於主漂移對照表的項目：

| ID | 摘要 | 為何嚴重 |
|----|------|---------|
| **DRIFT-015** | host 上 `lightgbm` 與 `xgboost` 對映同一個 `_FallbackTreeEnsembleClassifier` | DEC-007 宣稱的「4 模型 × 2 特徵集 = 8 組平行對照」在 host 上實際只有**兩種**相異實作。這不是精度問題 —— **比較本身不成立**，因為同一個實作被當成三個不同模型互相比較。任何來自 host 的 tournament 結論與冠軍模型選拔皆須標為 `NOT VERIFIED`。 |
| **DRIFT-016** | `requirements.txt` 零鎖版（6 個無約束、9 個僅下界、0 個上界、0 個 `==`）| GOV-02 剛把 container 定為正式環境並建立基線，但同一份 requirements 在不同時點會解析出不同版本組合（host 2.3.3 vs container 3.0.5 的 `pandas` 主版本差距已是實例）。**今日基線明日可能失效且不產生任何訊號** —— 與 host 靜默降級同型，只是換到依賴層。**僅登錄，鎖版策略由 PO 另行決定。** |

---

## UG-G1-SB1 步驟 2：修正前績效基線（已污染，保留供對照）

> **來源**：`doc/upgrade/gates/SB1_GATE_A_PROPOSAL.md` §3.3（PO 已核准，本文件為其落實）。
> **性質**：**保存，不修改**。本節不覆寫、不刪除 DRIFT-018 或 `components.py` 現行內容，
> 只是為 SB1 的 Purge 修正建立一份「污染前」對照錨點。矛盾分析的權威位置仍是 DRIFT-018，
> 不在此重複（見下方 §3）。
> **執行日期**：2026-08-24

### 1. 原文照錄

擷取自 `src/ui/components.py:129-138`（`render_tournament_leaderboard`），擷取日期 2026-08-24：

| 排名 | 模型演算法 | 特徵集 | Macro F1 | 方向命中率 | 累積策略報酬 | ΔAlpha 增益 |
|------|-----------|--------|---------:|----------:|------------:|-----------:|
| 🏆 冠軍 | Random Forest | 多模態 (18 Feat) | 0.5820 | 58.4% | +8.2% | +4.7% |
| 🥈 亞軍 | LightGBM | 多模態 (18 Feat) | 0.5910 | 59.2% | +9.6% | +5.5% |
| 🥉 季軍 | XGBoost | 多模態 (18 Feat) | 0.5860 | 58.8% | +8.9% | +5.1% |
| 第 4 名 | Logistic Regression | 多模態 (18 Feat) | 0.5480 | 54.2% | +4.8% | +2.7% |
| 控制組 | LightGBM | 純價量 (9 Feat) | 0.5410 | 54.0% | +4.1% | 基準線 |
| 控制組 | XGBoost | 純價量 (9 Feat) | 0.5380 | 53.9% | +3.8% | 基準線 |
| 控制組 | Random Forest | 純價量 (9 Feat) | 0.5340 | 53.8% | +3.5% | 基準線 |
| 控制組 | Logistic Regression | 純價量 (9 Feat) | 0.5120 | 51.5% | +2.1% | 基準線 |

### 2. 質性宣稱原文與現況

`doc/evidence/TRACEABILITY.md`（提案 §3.1 撰寫時位於 L164，本文件擷取時因既有編輯位移至 L170）：

> ~~**8 組平行實驗 Alpha 歸因**：量化證明社群情緒融合模型相較純價量控制組帶來顯著之 ΔF1 與 ΔReturn 超額報酬。~~

**現況**：該行**已由 DRIFT-018 標註撤回**（2026-08-24，PO 裁示），非本節新增動作 ——
`TRACEABILITY.md` 現行內容本身已是刪除線＋撤回註記，不是原始強宣稱。
本節照錄目的是保留「被撤回的原文是什麼」，供 §1 的數值與宣稱對照，本節不重複執行撤回。

**版本落差揭露（PO 2026-08-24 獨立驗證發現）**：現行 `TRACEABILITY.md:170` 的實際字面
已比本引文簡短（撤回編輯時一併精簡為「…顯著之超額報酬」，未同步登錄這項措辭變動）。
本節保留的是**提案 §3.1／DRIFT-018 登錄時的原始措辭**，不是對 `TRACEABILITY.md`
目前字面的逐字 grep 結果 —— 兩者不一致是已知落差，不是本節引用錯誤或捏造。

### 3. 兩個獨立污染源，各自的修復排程不同

> 完整三項矛盾分析、判定原則與標註規則見 DRIFT-018；本節只列污染源與排程，不重述矛盾細節。

| 污染源 | 說明（一句話） | 修復排程 | 目前狀態 |
|--------|---------------|---------|---------|
| **邊界洩漏** | `train[T].label` 依賴 `test[T+1].close`；`SB1_STEP1_BEFORE_SNAPSHOT.md` §5.1 顯示 Fold `gap` 全為週末、train 末日與 test 首日相鄰、交易日隔離為零 | **UG-G1-SB1**（本 Gate A 授權範圍內） | 步驟 0、1 已完成；步驟 3（實作）未開始 |
| **fallback 型別碰撞**（DRIFT-015） | host 上 `lightgbm`／`xgboost`／`random_forest` 對映同一個 `_FallbackTreeEnsembleClassifier`，四模型比較實為兩種實作互比 | UG-G1-SB5（文件標註）+ **Gate 3**（`UG-G3-SB3`／`UG-G3-SB7`，容器內重跑） | 兩者皆未開始；是否僅存在於 host 尚待容器內重跑 tournament 確認 |

**因此**：即使 SB1 完成邊界洩漏修正，§1 的數值仍不可用 —— 第二個污染源獨立存在且修復排程在 Gate 3，
兩者必須都解決才談得上重新量測。

### 4. 使用限制【強制】

- 本節任何數值**不得**引用為模型效能宣稱、baseline 或比較基準。
- 本節**不是** SB1 的驗收依據 —— 驗收依據見 `SB1_STEP1_BEFORE_SNAPSHOT.md` §3（A 類 42 個方法）與 §6.1（splitter 證據不得由 aggregator 背書）。
- `components.py` 現行內容**維持不動**；其處置屬 UG-G1-SB2（DRIFT-009 Demo/Real 分離）與 UG-G1-SB3（DRIFT-008 動態化），SB1 不修改 `src/ui/`。
- 本節唯一用途：待兩個污染源皆修復後，供「污染前 vs. 污染源逐一移除後」的數值差異對照，作為 remediation 有效性的佐證 —— **不是**污染前數值本身正確性的佐證。

---

## 審計方法論

1. **程式碼逐行驗證**：對每筆漂移項目，直接讀取原始碼檔案並標記具體行號。
2. **自動化計數**：使用 `grep -r "def test_" tests/` 統計測試函式總數。
3. **Git 狀態比對**：以 `git log --oneline -1` 驗證 HEAD commit。
4. **檔案存在性檢查**：以 `ls` 驗證 README.md 是否存在。
5. **模式搜尋**：以 `grep` 搜尋 `schema_version` 與 `ALTER TABLE` 確認 migration 機制缺失。

> 本文件為 Gate 0 交付物 A，須經 PO Review 後方可進入 Gate 1 實施階段。

---

## 追加漂移項目（Gate 0 之後，2026-09-14）

> 以下項目非 2026-08-21 法證式稽核所發現，是後續工作期間新發現的同型漂移，
> 依 §16.1「只增不減」原則附加於文件末尾，不插入上方原始稽核表格（避免打亂
> 該表既有列與後續補充註記之間已建立的行號引用關係）。

| ID | Severity | Document | Location | Documented Claim | Code/Repo Fact | Evidence Label | Remediation | Owner Gate/SB |
|----|----------|----------|----------|------------------|----------------|----------------|-------------|---------------|
| DRIFT-019 | **HIGH** | `DECISIONS.md`（多則 `APPROVED` 狀態 ADR） | `DECISIONS.md` 各則 `### Verification` 區塊 | ADR 狀態為 `APPROVED` 隱含其 `Verification` 清單已全數完成（打勾） | PO 2026-09-14 發現 `DEC-036` 已 `APPROVED` 但 `Verification` 仍列「`UG-G3-SB2a` 自己的 Gate A 提案（待開）」——實際上該 Gate A 早已核准（`f668503`）、Gate B 已結案（`5dc8d75`），字面卻停留在核准當下的措辭，從未回頭更新。全文重新掃描後同型情況共 **8 則**：`DEC-013`／`016`／`017`（Gate 0，`A1`-`A10` 具名測試已不存在、部分項目從未回頭核對）、`DEC-033`／`034`（SB6／SB7，K=1 重測／`SUCCESS` 實測等項目留白從未處置）、`DEC-036`（如上）、`DEC-012`／`020`（Streamlit 肉眼確認、真實 artifact 產出，兩者皆誠實地保留未勾，非漂移，但格式與其餘 6 則不一致） | `VERIFIED — 逐則人工核對 2026-09-14` | **根因是制度性的**：`PROJECT_STATUS.md` §0.5 #10 讓 ADR 狀態轉換（`Proposed`→`APPROVED`）綁定 Gate B 事件，但 `Verification` 清單的勾選**沒有對應的綁定規則**；`gate0_contract_check.py` B13 只查「停在 `PROPOSED` 的 ADR」，結構上不會查「`APPROVED` 卻含未勾項」的 ADR——B13 對這個問題是一個「結構上不可能失敗的檢查」（`CLAUDE.md` §9A.1）。**處置**：(a) 8 則逐項核對現行 commit／測試後補勾附證據，測試類確實未做的改寫為 `- [ ] NOT VERIFIED → 去處：...` 格式（8 則已於 `DECISIONS.md` 本次一併訂正，隨 RISK-023 收尾 commit）；(b) 本則登記；(c) `gate0_contract_check.py` 新增機械檢查：`APPROVED` 的 ADR 不得含無標 `NOT VERIFIED` 去處的裸 `- [ ]` 未勾項，附 known-FAIL（見該檢查 docstring）。 | RISK-023 收尾 commit（PO 2026-09-14 裁決併入） |

## 文件對齊輪追加漂移項目（2026-09-16，段1唯讀盤點）

> 以下 15 項（`DRIFT-020`～`DRIFT-034`）為「文件對齊輪」段1唯讀盤點依審查方 24 項清單
> 逐項獨立重跑指令查證後登記，PO 逐段核准，段3 分五個固定 commit 執行。

| ID | Severity | Document | Location | Documented Claim | Code/Repo Fact | Evidence Label | Remediation | Owner Gate/SB |
|----|----------|----------|----------|------------------|----------------|----------------|-------------|---------------|
| DRIFT-020 | Medium | `PROJECT_STATUS.md` | §0.3，`UG-Gate-3、UG-Gate-4` 列 | Gate 3／4 並列「未核准，不得啟動」 | Gate 3 已於 2026-09-16 關閉 | `VERIFIED THIS SESSION` | Gate 3 自「明確未授權項目」表移除，改列說明性 CLOSED 列（同 Gate 1／2 先例） | `a1eaaa2`（文件對齊輪 commit 1/5） |
| DRIFT-021 | Low | `PROJECT_STATUS.md` | §0.2，SB1／SB2／SB2a 列 | 狀態欄寫「Gate B 已核准結案」，同表 SB3～SB7 用「CLOSED」 | 同一狀態兩種寫法，表內不一致 | `VERIFIED THIS SESSION` | 三列統一改為「CLOSED（日期，PO 核准結案）」 | `a1eaaa2` |
| DRIFT-022 | Low | `PROJECT_STATUS.md` | §0.5 #22 延續段 | 引用「是否把 Gate 3 後續主線改為…」的舊措辭 | `DEC-041` 已裁決，原文未追加說明 | `VERIFIED THIS SESSION` | 段末追加「已裁決，見 `DEC-041`」一句，原文保留 | `a1eaaa2` |
| DRIFT-023 | Low | `PROJECT_STATUS.md` | §0.5 #26 | 括號僅寫「PM 乾跑發現」 | 「持續性」判斷是審查方複核推翻 PM「暫態」判斷後確立，原文未反映 | `VERIFIED THIS SESSION` | 訂正為「PM 乾跑發現未追蹤檔；審查方複核確認行尾差異為持續性」 | `a1eaaa2` |
| DRIFT-024 | Medium | `PROJECT_STATUS.md` | §0.5 #20 | 觸發條件未提及 `RISK-005` | `RISK-005` 已單向改綁 #20，但 #20 未反向提及（段1發現與審查方清單原判定「已修」不同，重新查證後成立） | `VERIFIED THIS SESSION` | 觸發條件追加 RISK-005 150 檔計時回填要求 | `a1eaaa2` |
| DRIFT-025 | Low | `SYSTEM_UPGRADE_MASTER_PLAN.md` | §7/§8/§9 各 SB Brief | 多數已 CLOSED 的 SB Brief 無「狀態」列 | `PROJECT_STATUS.md` §0.2 有完整狀態記錄，兩份不對稱 | `VERIFIED THIS SESSION` | 18 個已 CLOSED 的 Brief 逐一補「狀態」列（Gate 1 五個、Gate 2 八個、Gate 3 五個） | `048bf87`（文件對齊輪 commit 2/5） |
| DRIFT-026 | Low | `SYSTEM_UPGRADE_MASTER_PLAN.md` | §7/§8 標題 | Gate 1／2 標題無關閉狀態 | Gate 1（2026-08-26）、Gate 2（2026-09-06）皆已關閉，Gate 3 標題已於 `4af5886` 補過 | `VERIFIED THIS SESSION` | 標題下補關閉狀態與 closure 文件路徑 | `048bf87` |
| DRIFT-027 | Low | `SYSTEM_UPGRADE_MASTER_PLAN.md` | §5.2，Gate 2 依賴樹狀圖 | 審查方清單原述「`UG-G3-SB2a` 未列於樹狀圖」 | 段1重讀全文查證：**SB2a 其實已在 Gate 3 樹內**（訂正審查方原判定）；真正缺口是 Gate 2 標題寫「9 SBs」但樹只列 7 個縮排項目，`UG-G2-SB8`／`SB9`／`UG-G2-MIG` 皆未列入 | `VERIFIED THIS SESSION` | Gate 2 樹狀圖補上 SB8／SB9／MIG 三項 | `048bf87` |
| DRIFT-028 | High | `doc/spec/PRD_Financial_Sentiment_System_v1.md` | 全文 | 產品定義為方向性雙模式預測，0 次提及 Gate 3 轉向 | `DEC-041` 已把主線改為 Timeout gating；`grep -c -i "timeout\|gating\|holdout"` = 0 | `VERIFIED THIS SESSION` | §1 追加「Gate 3 轉向」段落，§3 雙模式段落加「原規劃／現況」對照 | `8f68cdf`（PRD v2 commit，文件對齊輪 commit 4/5，PO 2026-09-16 核准草案 v2） |
| DRIFT-029 | Medium | `doc/spec/SDD_Financial_Sentiment_System_v1.md` | §2 模組表 | 無 Gate 3 ML 管線模組 | `src/ml/stacking.py` 等 5 個模組、`scripts/verify/ug_g3_*` 未入表（`grep "src/ml"` 僅命中 `model_trainer.py`） | `VERIFIED THIS SESSION` | §2 模組表補五個模組；新增「UG-Gate-3 ML 管線」小節 | `68d78ba`（SDD v2 commit，文件對齊輪 commit 5/5，PO 2026-09-16 核准草案 v2） |
| DRIFT-030 | Medium | `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 172～236 行（原清單僅提 172～207 行，段1盤點重讀全文發現範圍應擴至 236 行） | 「Gate 2」「Gate 3」「Gate 4」「Gate 5」四節標題為前任團隊 Phase Gate 編號，與 UG-Gate 同名不同物 | 207 行「2026-08-20 關閉 Gate 3」與 `UG-Gate-3`（2026-09-16 關閉）撞名；Legacy Gate 4 撞尚未啟動的 `UG-Gate-4`，風險更高 | `VERIFIED THIS SESSION` | 文件開頭加命名對照表；四節標題加「Legacy Phase Gate N」前綴，內文一字不改 | `68d78ba`（SDD v2 commit，文件對齊輪 commit 5/5，PO 2026-09-16 核准草案 v2） |
| DRIFT-031 | Low | `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 資料流／資料庫相關節 | 0 次提及 `DEC-03x` | `grep -n "DEC-03"` = 0 命中；Gate 2 九個 SB 落地未反映 | `VERIFIED THIS SESSION` | 新增「UG-Gate-2 Feature Store 落地」小節，`DEC-029～034`／`039` 逐條列 SB 落地引用 | `68d78ba`（SDD v2 commit，文件對齊輪 commit 5/5，PO 2026-09-16 核准草案 v2） |
| DRIFT-032 | Low | `DECISIONS.md` | `DEC-040` Verification 未勾項 | 「去處待 `UG-G3-SB7` 開工前確認」 | SB7 已開工並結案，措辭時序矛盾；`closed/UG_G3_SB7_GATE_A_PROPOSAL.md` §2.1 已確認面板 sha 未變 | `VERIFIED THIS SESSION` | 未勾項追加日期註記，原句不改 | `eaa31f2`（文件對齊輪 commit 3/5） |
| DRIFT-033 | Medium | `doc/upgrade/contracts/REMAINING_RISKS.md` | `RISK-001／009／010／011／012` 狀態欄 | 裸 `HYPOTHESIS`／`PLANNED`，無日期戳 | 去處 SB 皆已 CLOSED；`RISK-009`／`011`／`012` 有可引用的實測依據，`RISK-001`／`010` 查無直接量測（誠實維持 `HYPOTHESIS`，非漂移） | `VERIFIED THIS SESSION` | `RISK-009` 改 `OBSERVED`（交叉核對 SB7 Holdout 未劣化）；`RISK-011` 改 `OBSERVED`（`UG-G3-SB2a` 實測 8.1%，仍標「偏高」）；`RISK-012` 改 `MITIGATED`（`UG-G2-SB6` PIT 實作已交付）；`RISK-001`／`010` 維持 `HYPOTHESIS`，加查證日期與誠實說明 | `eaa31f2`（文件對齊輪 commit 3/5） |
| DRIFT-034 | Low | `PROJECT_STATUS.md` | §0.5 #23 延續段；§13 | 「Gate B 送審中」＋根層路徑（段1自查新增，不在審查方 24 項清單內） | `UG-G3-SB3` 已 CLOSED；檔案已 `git mv` 至 `closed/`，原路徑斷鏈；§13 另兩份 Gate 0 SB1 文件同型斷鏈 | `VERIFIED THIS SESSION` | 狀態訂正為「已 CLOSED」，兩處路徑補 `closed/` 前綴 | `a1eaaa2` |
| DRIFT-035 | Low | `FEATURE_REGISTRY.md` | 第 132 列，`target_up_down` 的 Source 欄 | `feature_aggregator.py L467-469` | 實際定義於 `feature_aggregator.py:1064-1065`（`grep` 核對），行號因該檔多次插入新程式碼而漂移；同一份表相鄰兩列（`target_next_close` L459、`target_return_1d` L462-464）唯讀核對後也已過期（實際約 L1056、L1059-1061），本則僅訂正審查方明確指出的第 132 列，另兩列不在本次授權範圍內，留待下次一併處理 | `VERIFIED THIS SESSION` | 第 132 列行號訂正為 `L1064-1065` | §0.5 #31＋#33 結案後、#37 登記同批（審查方唯讀查證，2026-09-20）**【2026-09-20 結清】**：§0.5 #38（審查方複核 #37 訂正後發現全表 15 處中 14 處行號皆已漂移，非僅本則的另兩列）已改用函式／方法名稱錨點取代行號，`target_next_close`／`target_return_1d`（連同本則的 `target_up_down`）皆已改為 `feature_aggregator.py::FeatureAggregator.generate_target_labels()`，見 `DEC-044`——本則「留待下次」的兩列已在同一批處理，不再是獨立待辦 |
