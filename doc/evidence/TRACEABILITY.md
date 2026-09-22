# TRACEABILITY.md — 全系統端到端追溯矩陣 (End-to-End Traceability Matrix)

> **文件使命**：本文件建立從「金融學術理論／產品規劃（PRD）」、「系統架構設計（SDD）」、「架構決策紀錄（ADR/DEC）」、「原始碼實作（Code）」到「自動化測試套件（Test Suite）」與「驗證證據（Evidence）」的完整雙向追溯鏈。
> 本文件為個人轉職與成果發表作品集之**核心決策鏈與工程嚴謹性證明（Portfolio Evidence Trail）**。

---

## 1. 追溯鏈架構總覽 (Traceability Chain Overview)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          端到端工程證據閉環鏈條                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. 理論與需求層 (Theory & PRD)                                               │
│    • DSSW 雜訊交易者模型 / Antweiler & Frank (2004) / Bollen (2011)          │
│    • PRD: 異質資料收集、Hybrid NLP、雙模式預測、多模型競技、BI 視覺化       │
│                               ▼                                             │
│ 2. 架構設計與決策層 (SDD & ADR)                                              │
│    • SDD: Extract / Transform / Load / Feature / ML / UI 分層模組責任       │
│    • DEC-001 至 DEC-008: 涵蓋 Schema、失敗語意、軟刪除、時序防洩漏、ML、UI  │
│                               ▼                                             │
│ 3. 程式碼實作層 (Implementation)                                             │
│    • src/extractors/, src/transform/, src/loaders/, src/ml/, src/ui/, app.py│
│                               ▼                                             │
│ 4. 自動化測試防護網 (Automated Tests - 124 Tests PASS)                       │
│    • tests/ (12 大專項測試套件，涵蓋單元、整合、邊界、時序防洩漏與 UI 契約) │
│                               ▼                                             │
│ 5. 驗證證據 (Verified Evidence)                                              │
│    • 證據分級：VERIFIED THIS SESSION / PREVIOUSLY VERIFIED / NOT VERIFIED    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 端到端追溯矩陣表 (Complete Traceability Matrix)

| 需求／理論來源 | 產品需求 (PRD) | 系統設計 (SDD) | 架構決策 (ADR) | 實作檔案 (Code Path) | 測試驗證檔案 (Test Suite) | 測試數量 | 驗證證據狀態 |
|---|---|---|---|---|---|---|---|
| **單一真實來源 DDL** | Phase 1 ETL 資料庫管理 | 2.1 儲存層架構 | **DEC-001** / **DEC-002** | `database/schema.sql`<br>`database/init_db.py` | `database/init_db.py`<br>(Isolated 18.6 PG Verification) | 獨立沙盒測試 | `PREVIOUSLY VERIFIED` (Gate 1 Closed) |
| **失敗傳遞與空值分離** | Phase 1 異常告警防呆 | 2.4 DB 讀取語意 | **DEC-003** (G2-SB1) | `src/loaders/db_writer.py`<br>`main_etl_pipeline.py` | `tests/test_db_read_semantics.py` | 14 tests | `VERIFIED THIS SESSION` (Gate 2 Closed) |
| **精準快取命中機制** | Phase 2 節省 API 成本 | 2.2 NLP 快取架構 | **DEC-003** (G2-SB2) | `src/transform/nlp_processor.py` | `tests/test_nlp_cache_semantics.py` | 8 tests | `VERIFIED THIS SESSION` (Gate 2 Closed) |
| **嚴格 NLP 批次檢查點** | Phase 2 Checkpoint 續傳 | 2.3 嚴格檢查點契約 | **DEC-003** (G2-SB3) | `src/transform/nlp_processor.py`<br>`main_etl_pipeline.py` | `tests/test_nlp_checkpoint_semantics.py` | 11 tests | `VERIFIED THIS SESSION` (Gate 2 Closed) |
| **軟刪除完整性防護** | Phase 1 AI 動態探索 | 2.3 設定生命週期 | **DEC-004** (G3-SB1) | `src/loaders/db_writer.py`<br>`src/extractors/trend_discover.py` | `tests/test_tracking_keyword_integrity.py` | 15 tests | `VERIFIED THIS SESSION` (Gate 3 Closed) |
| **標準股票代碼契約** | Phase 1 多市場代碼對齊 | 2.3 股票識別邊界 | **DEC-004** (G3-SB2) | `src/transform/data_cleaner.py`<br>`main_etl_pipeline.py` | `tests/test_canonical_stock_id.py` | 17 tests | `VERIFIED THIS SESSION` (Gate 3 Closed) |
| **雙模式預測與時間對齊** | Phase 3 ML 時間窗口規劃 | 2.3 Gate 4 雙模式邊界 | **DEC-005** (G4-SB1) | `src/transform/data_cleaner.py`<br>`src/transform/feature_aggregator.py` | `tests/test_time_alignment.py` | 13 tests | `VERIFIED THIS SESSION` (Gate 4 Closed) |
| **零前視偏誤 Target 生成** | Phase 3 ML 預測目標 | 2.3 Gate 4 時序邊界 | **DEC-005** (G4-SB2) | `src/transform/feature_aggregator.py` | `tests/test_feature_aggregator_alignment.py` | 5 tests | `VERIFIED THIS SESSION` (Gate 4 Closed) |
| **Antweiler 輿情量化指標** | RES-001 / RES-002 | 2.3 Gate 5 特徵契約 | **DEC-006** (G5-SB1) | `src/transform/feature_aggregator.py` | `tests/test_research_features.py` | 4 tests | `VERIFIED THIS SESSION` (Gate 5 Closed) |
| **技術動能與波動率指標** | RES-003 / 004 / 005 | 2.3 Gate 5 特徵契約 | **DEC-006** (G5-SB2) | `src/transform/feature_aggregator.py` | `tests/test_research_features.py` | 2 tests | `VERIFIED THIS SESSION` (Gate 5 Closed) |
| **Walk-Forward 時序切分引擎** | Phase 3 時序交叉驗證 | 3.1 ML 時序防護 | **DEC-007** (P3-SB1) | `src/ml/time_series_split.py` | `tests/test_time_series_split.py` | 6 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
| **Purged Walk-Forward（Purge/Embargo，邊界洩漏修正）** | 稽核報告 §1；PO 決策 §3.3 | `PURGED_WALK_FORWARD_SPEC.md` §2, §3 | **DEC-011**（UG-G1-SB1） | `src/ml/time_series_split.py`（`label_horizon`／`embargo_days`／`assert_no_boundary_leakage`）<br>`src/transform/feature_aggregator.py`（`label_end_date` 欄位） | `tests/test_time_series_split.py`（`PurgedWalkForwardTests`）<br>`tests/test_feature_aggregator_alignment.py`（`label_end_date` 測試） | 6 + 3 = 9 tests | `VERIFIED THIS SESSION`（`SB1_STEP4_AFTER_SNAPSHOT.md`；163/163 PASS；`src/` 尚未 commit） |
| **純價量控制組基準模型工廠** | Phase 3 控制組對照實驗 | 3.2 基準模型定義 | **DEC-007** (P3-SB2) | `src/ml/baseline_models.py` | `tests/test_baseline_models.py` | 6 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
| **多模態特徵融合與競技訓練** | Phase 3 多模型橫向競技 | 3.3 樹模型適配訓練 | **DEC-007** (P3-SB3) | `src/ml/model_trainer.py` | `tests/test_model_trainer.py` | 5 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
| **8組平行實驗 Alpha 歸因與即時推論** | Phase 3 Alpha 歸因與推論 | 3.4 評估器與推論器 | **DEC-007** (P3-SB4) | `src/ml/evaluator.py`<br>`src/ml/predictor.py` | `tests/test_ml_evaluator.py` | 7 tests | `VERIFIED THIS SESSION` (Phase 3 Closed) |
| **Streamlit BI 終端與互動圖表** | Phase 4 視覺化與 XAI | 4.1 BI 與圖表架構 | **DEC-008** (P4-SB1~4) | `app.py`<br>`src/ui/` | `tests/test_ui_contracts.py` | 14 tests | `VERIFIED THIS SESSION` (Phase 4 Closed) |
| **自動排程、動態 ETL 與 UI 自選** | 維運與使用者體驗優化 | 5.1 排程與自選管理 | **DEC-008** / Operations | `scheduler.py`<br>`main_etl_pipeline.py`<br>`src/ui/` | `tests/test_operational_ux.py` | 10 tests | `VERIFIED THIS SESSION` (Enhanced) |
| **Gemini 429 彈性退避與 E2E 防回歸** | NLP 容錯與彈性排程 | 2.2 NLP 彈性架構 | **CHAL-007** / DEC-003 | `src/transform/nlp_processor.py` | `tests/test_nlp_resilience_e2e.py` | 2 tests | `VERIFIED THIS SESSION` (Resilience) |
| **AI 題材概念股映射與知識庫** | 題材全系統升級 (SB-TH1) | 2.1 儲存與探索架構 | **DEC-009** (SB-TH1) | `src/extractors/trend_discover.py`<br>`src/loaders/db_writer.py` | `tests/test_thematic_mapping.py` | 4 tests | `VERIFIED THIS SESSION` (Thematic) |
| **題材情緒溢出加權特徵引擎** | 題材全系統升級 (SB-TH2) | 2.3 題材特徵邊界 | **DEC-009** (SB-TH2) | `src/transform/feature_aggregator.py`<br>`main_etl_pipeline.py` | `tests/test_thematic_feature_spillover.py` | 5 tests | `VERIFIED THIS SESSION` (Thematic) |
| **三重查詢真實文章與空狀態透明化** | 輿情明細透明化 (SB-ART1~3) | 4.1 輿情明細架構 | **DEC-008** / REAL-ART | `src/ui/data_loader.py`<br>`src/ui/components.py` | `tests/test_real_articles_pipeline.py` | 4 tests | `VERIFIED THIS SESSION` (Real Articles) |
| **UI 四狀態資料來源透明化（REAL/DEMO/EMPTY/ERROR）** | 稽核報告 §2；AGENTS.md §10；DRIFT-009 | 7.1 UI Demo/Real 模式分離 | **DEC-012**（UG-G1-SB2） | `src/ui/data_loader.py`（`DataMode`／`DataSourceError`）<br>`src/ui/components.py`（`render_data_mode_banner`）<br>`src/ui/charts.py`（佔位圖／浮水印）<br>`app.py`（mode 分流與全域追蹤） | `tests/test_ui_contracts.py`<br>`tests/test_operational_ux.py`<br>`tests/test_real_articles_pipeline.py`<br>`tests/schema_smoke_ui_data_loader.py`（不進正式套件） | 9 個新增測試 + 4 個 schema smoke test | `VERIFIED THIS SESSION`（`SB2_STEP3_IMPLEMENTATION_REPORT.md`；173/173 PASS；HERM runtime 攔截數 9→0；`src/` 尚未 commit） |
| **模型競技排行榜動態化（Artifact-Driven Leaderboard）** | 稽核報告 §2；DRIFT-008；DRIFT-018 | 7.1 UI 排行榜動態化 | **DEC-020**（UG-G1-SB3） | `src/ui/data_loader.py`（`load_tournament_results`／`_stringify_date_columns`）<br>`src/ui/components.py`（`render_tournament_leaderboard(data, mode)`）<br>`app.py`（呼叫處解包）<br>`scripts/generate_tournament_artifact.py`（新檔，未執行） | `tests/test_ui_contracts.py`<br>`tests/test_time_series_split.py`（`label_end_date` 型別回歸）<br>`tests/test_generate_tournament_artifact.py`（資料量防線） | 9 個讀取/渲染測試 + 3 個型別回歸測試 + 4 個防線測試 | `VERIFIED THIS SESSION`（`SB3_GATE_B_SUBMISSION.md`；189/189 PASS；真實 artifact 尚未產出，`NOT VERIFIED`——見該文件 §6；`src/` 尚未 commit） |
| **RISK-013 根本解（DB 連線目標守門）** | RISK-013（PO 2026-08-24 簽核）；PO 2026-08-26 裁示須為 SB4 第一步驟 | 不適用（風險緩解機制，非產品需求章節） | **DEC-021**（UG-G1-SB4 階段一） | `database/db_target_guard.py`（`assert_safe_migration_target`） | `tests/test_db_target_guard.py` | 5 個案例（3 known-FAIL + 2 正向） | `VERIFIED THIS SESSION`（`SB4_STEP1_GATE_B_SUBMISSION.md`；194/194 PASS；commit `d2a4d48`） |
| **Schema Version & Migration 機制（Additive DDL + Runner）** | 稽核報告 §4；AGENTS.md §7.1；DRIFT-011；`DB_MIGRATION_PLAN.md` | 資料庫章節 | **DEC-010**（UG-G1-SB4 階段二） | `database/schema.sql`（新增 `schema_version` DDL）<br>`database/migrations/001_baseline.sql`<br>`database/apply_migrations.py`（強制呼叫 `assert_safe_migration_target`） | `tests/test_apply_migrations.py` | 6 個 mock 單元測試 + 4 項 E2E 隔離容器驗證（含新增第 4 項：真實 DB 座標未確認即被拒絕） | `VERIFIED THIS SESSION`（`SB4_STEP2_GATE_B_SUBMISSION.md`；隔離容器 `sb4_migration_tmpdb`，非 `postgres-data` 掛載，已拆除；`src/`／`database/` 變更尚未 commit） |
| **`daily_ml_features` 29 欄擴充 + `label_reason` 範圍延後 + NaN→NULL 轉換修正** | `DB_MIGRATION_PLAN.md` §4.2；DRIFT-003 | 資料庫章節；`FEATURE_REGISTRY.md` §2 | **DEC-023**（UG-G2-SB1） | `database/migrations/002_expand_ml_features.sql`（新）<br>`src/loaders/db_writer.py`（`ML_FEATURE_COLUMNS`／`upsert_ml_features`）<br>`src/transform/feature_aggregator.py`（`source_status` 判定）<br>`main_etl_pipeline.py`（新增 `generate_target_labels()` 呼叫） | `tests/test_ml_feature_store_contract.py`（新，含 NaN→None known-FAIL 迴歸案例）<br>`tests/test_apply_migrations.py`／`test_nlp_resilience_e2e.py`／`test_operational_ux.py`（既有測試因 7→29 欄更新斷言） | 8 個新增測試 + 3 個既有測試更新 | `VERIFIED THIS SESSION`（`G2_SB1_GATE_B_SUBMISSION.md`；208/208 PASS；隔離容器 `g2sb1_ml_features_tmpdb`，非 `postgres-data` 掛載，已拆除；commit `ef029a6b5753d071e9c17f0227389d0772681097`） |
| **來源能力宣告：方向類留言特徵只由提供推／噓標記的來源計算** | PO 2026-08-28 Gate A 裁決（`UG-G2-SB5` 決策點 5）；PO 2026-08-30 核准實作 | `FEATURE_REGISTRY.md` §5.7 | **DEC-028**（UG-G2-SB5 決策點 5） | `src/transform/source_capabilities.py`（新）<br>`src/transform/feature_aggregator.py`（`_aggregate_direct_comment_counts` 依來源過濾＋`min_count=1`；`has_comments` 拆為 `has_volume`／`has_direction`）<br>`src/loaders/db_writer.py`（`fetch_all_for_features` SELECT 補 `source`） | `tests/test_comment_features.py::SourceCapabilityTests` | 6 tests（含 2 個 known-FAIL、1 個反向守衛） | `VERIFIED THIS SESSION`（隔離臨時 DB `g2sb5dp5_tmpdb`，非 `postgres-data` 掛載，已拆除；全套 269/269 PASS；E2E 走真實 DB 讀取路徑，五項與人工核算逐位相符） |
| **留言計數的時點有效性：以「決策時點是否已可見」為準** | PO 2026-08-28 Gate A 裁決（`UG-G2-SB4` 決策點 1） | `FEATURE_REGISTRY.md` §5.5 | **DEC-024**（UG-G2-SB4） | `database/migrations/004_comment_scrape_timestamp.sql`（新）<br>`src/loaders/db_writer.py`（`update_comment_counts()` write-once）<br>`src/transform/feature_aggregator.py`（`comments_scraped_at <= decision_point` 過濾） | `tests/test_comment_features.py::CommentTimingValidityTests` | 2 tests | `PREVIOUSLY VERIFIED`（`G2_SB4_GATE_B_SUBMISSION.md`；隔離容器 `g2sb4_comments_tmpdb`，已拆除） |
| **留言計數聚合只採用直接個股文章，不套用題材溢出** | PO 2026-08-28 Gate A 裁決（`UG-G2-SB4` 決策點 2 選項 C） | `FEATURE_REGISTRY.md` §5.6 | **DEC-025**（UG-G2-SB4） | `src/transform/feature_aggregator.py`（`_aggregate_direct_comment_counts` 僅取 `df_arts_direct`） | `tests/test_comment_features.py::ThemeSpilloverExcludedFromCommentsTests` | 1 test | `PREVIOUSLY VERIFIED`（`G2_SB4_GATE_B_SUBMISSION.md`） |
| **對 Gate 0 交付物的兩處偏離明示登記，原文保留不改寫** | PO 2026-08-28／08-29 裁決（`UG-G2-SB5`） | — | **DEC-026**（UG-G2-SB5） | `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`（SB5 Brief 加註）<br>`doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §4.5（加註） | `scripts/verify/gate0_contract_check.py` | Part B 11/11 | `VERIFIED THIS SESSION`（contract-check `exit 0`；commit `eca2f8c`／`a0e4248`） |
| **Dcard 可用性判定 `FAIL` → `DEFERRED WITH EVIDENCE`，RISK-003 不標為已解決** | `REMAINING_RISKS.md` RISK-003；PO 2026-08-28 核准之 §3 判準 | `MULTI_SOURCE_DATA_CONTRACT.md` §4（章首加註「暫停適用」） | **DEC-027**（UG-G2-SB5） | `scripts/verify/dcard_availability_check.py`（新）<br>`scripts/verify/snapshot_tracking_keywords.py`（新） | `tests/test_dcard_availability_criteria.py` | 25 tests | `VERIFIED THIS SESSION`（A1 HTTP 403／Cloudflare 邊緣攔截，A2–A6 `NOT EXECUTED`；原始證據 `doc/upgrade/gates/evidence/G2_SB5_availability_evidence.json`） |
| **CORE_16 平穩化特徵可計算（振幅比／MA 乖離／量能比）** | Phase 3 特徵工程 | 2.5 特徵聚合層 | **DEC-029** / **DEC-030** (G2-SB8) | `src/transform/feature_aggregator.py`<br>`src/loaders/db_writer.py`（`high_price`／`low_price`） | `tests/test_feature_aggregator.py` | 見全套 | **已驗證**：四個欄位由 `PLANNED` 轉為可計算；`amplitude_ratio` 於高低價缺漏時維持 NULL（成因 F）、MA 乖離僅於暖機期填 0.0（成因 W）、`volume_ratio_5d` 於 `MA5_Vol == 0` 時 NULL（**成因 U，DEC-030 新增**） |
| **讀取端欄位缺口的反查檢查（防止「漏改查詢」靜默失敗）** | Phase 1 ETL 契約 | 2.4 DB 讀取語意 | **DEC-029** (G2-SB8) | `scripts/verify/gate0_contract_check.py` Part B 檢查 12 | 同檔（契約檢查即測試） | 12/12 PASS | **已驗證，附 known-FAIL**：**第一個 known-FAIL 案例沒有 FAIL**——檢查掃到了自己的註解裡的 `high_price`。改為只掃非註解行後才真正觸發。**這是 §9A.1 的失效模式發生在一個為了防止它而寫的檢查裡** |
| **候選池價格資料（上市 + 上櫃，≥3 年）** | Phase 3 Universe 建構前置 | 2.1 儲存層架構 | **DEC-031** (G2-SB9) | `database/migrations/005_candidate_prices.sql`<br>`src/extractors/twse_market_report.py`<br>`src/extractors/tpex_market_report.py`<br>`scripts/verify/fetch_candidate_prices.py` | `tests/test_twse_market_report.py`<br>`tests/test_tpex_market_report.py` | 20 tests | **已驗證（拋棄式容器，複查方需先還原 dump）**：TWSE **1,003,070** 列／**1,104** 檔 + TPEx **818,800** 列／**919** 檔 = **1,821,870 列**，兩者皆 **983 交易日**、**4.05 年**（`2022-08-03` ~ `2026-08-21`）。**PK 碰撞全段 0**。**含 2026-09-03 的 +1 年延伸**：`UG-G2-SB9` 原交付 740 天／3.04 年，扣 SB6 的 60 日暖機後**面板僅 2.79 年、不足 §3.3 的 ≥3 年**，故延伸；現面板 923 交易日 = **3.79 年**。dump 還原已實測（`G2_SB6_dump_restore_verification.json`）。**2026-09-03 已進入真實庫**（`postgres`@`localhost:5432`，`schema_version` = 5，1,821,870 列 / 983 交易日，46 列逐月對號 46/46 相等）：`evidence/G2_SB6_realdb_import_verification.json` |
| **Point-in-Time Stock Universe（月度快照、流動性排名）** | Phase 3 回測前置 | 2.1 儲存層架構 | **DEC-017** (G2-SB6)、**DEC-033** (窗口邊界) | `database/migrations/006_universe_snapshots.sql`<br>`src/transform/universe_builder.py` | `tests/test_universe_builder.py` | 13 tests | **已驗證（真實庫 `postgres`@`localhost:5432`）**：**46 期快照**（`2022-11-01` ~ `2026-08-03`）、每期納入 **150**、總計 **85,641 列**。**逐月對號 46/46 逐一相等**（比對現行基準 `G2_SB6_union_count_calibration_pit.json`，管線走自己的路徑去數）。退出股兩類違規皆 **0**，且 **4 檔退出股在退出前確實被納入過 41 期**（P4 的正面證據）。P1、P3 各出示一個實際跑出的 FAIL。⚠ **V2（7 天尖峰）不成立**，7 天尖峰只記錄為觀測、不作為分類依據。證據：`evidence/G2_SB6_implementation_verification.json` |
| **端點可用性判準（TWSE B1–B6／TPEx C1–C6）與其 known-FAIL** | Phase 1 資料擷取 | 2.4 來源契約 | **DEC-031** (G2-SB9) | `scripts/verify/twse_market_endpoint_check.py`<br>`scripts/verify/tpex_endpoint_check.py` | `tests/test_tpex_endpoint_criteria.py` | 25 tests | **已驗證**：TPEx 候選 1 **C2 FAIL**（當前快照、URL 無日期參數，其餘六項全 PASS——**只有 C2 擋得住它**）；候選 2 C1–C6 全 PASS。含 `BaselinePassTests` 反向守衛與逐字取自實測回應的欄名 fixture |
| **特徵取樣 regime 的允許清單** | Phase 2 特徵工程 | 2.4 來源契約 | **DEC-034** (G2-SB7) | `src/transform/source_capabilities.py`（`FEATURE_SOURCE_ALLOWLIST`／`source_enters_features()`）<br>`src/loaders/db_writer.py`（`fetch_all_for_features`） | `tests/test_feature_source_allowlist.py` | 8 tests | **已驗證（known-FAIL 對照，容器內）**：改寫成 `source <> 'ptt_stock'` → `'source IN' not found`／`'<>' unexpectedly found`；把 `ptt_stock` 登錄進允許清單 → `True is not false`（兩處）**且「兩張表不同」那條也響**。⚠ **生效後 `SUCCESS` 由 38 降為 0**（改動前寫死，`evidence/G2_SB7_exclusion_expectations.json`）——**那不是回歸，是現況的真實樣貌**：先前的 38 由日期錯置的舊文撐起。生效時點為下一次 `run_feature_engineering_pipeline` |
| **對外取數的重試紀律（403／429 vs 5xx／傳輸層）** | Phase 1 資料擷取 | 2.4 來源契約 | **DEC-032** (G2-SB9) | `scripts/verify/fetch_candidate_prices.py`（`TRANSPORT_RETRIES`／`SERVER_ERROR_RETRIES`／`_get()`） | 十份段報告 `evidence/G2_SB9_tpex_backfill_seg*.json` | 實測非單元測試 | **已驗證（known-FAIL 對照）**：同一起點 `20260615`，`TRANSPORT_RETRIES=2` → **0 天**；改為 5 + 遞增退避 → **105 天且該日第一次嘗試就通過**。403／429 全程 **0 次** |
| **Triple-Barrier 三分類標籤（anchor=Open[T+1]，H=5）** | `PURGED_WALK_FORWARD_SPEC.md` §4；DEC-018 | `PURGED_WALK_FORWARD_SPEC.md` §4.3/§4.6 | **DEC-018**（UG-G3-SB1）、**DEC-035**（邊界修訂，`APPROVED`） | `src/ml/triple_barrier.py`（新建） | `tests/test_triple_barrier.py` | 16 tests（T-TB-01~17，T-TB-07 Out of Scope） | `VERIFIED THIS SESSION`（`UG_G3_SB1_GATE_B_SUBMISSION.md`；507/507 PASS；真實庫 `postgres`@`localhost:5432` 3,713 列已寫入，見 `UG_G3_SB1_real_db_write.json`） |
| **PIT 面板讀取器 + `entity_mapping` 路由補齊 + 每日尾端重算掛點** | `SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2 Brief | 不適用（Gate 3 升級專案產物，非原始 SDD 章節） | **DEC-036**（`UG-G3-SB2` 拆分 `UG-G3-SB2a`，`APPROVED`） | `src/ml/panel_dataset.py`（新建）<br>`src/ml/triple_barrier.py`（`recompute_tail_labels`／`apply_tail_labels`）<br>`scripts/verify/ug_g3_sb2_backfill_entity_mapping.py`（新建）<br>`main_etl_pipeline.py`（掛點接線，未啟用） | `tests/test_panel_dataset.py`<br>`tests/test_entity_mapping_backfill.py`<br>`tests/test_daily_hook_wiring.py` | 52 tests | `VERIFIED THIS SESSION`（`UG_G3_SB2_GATE_B_SUBMISSION.md`；559/559 PASS；真實庫 `postgres`@`localhost:5432` `entity_mapping` 457 列已寫入，見 `UG_G3_SB2_routing_real_db_write.json`；每日尾端重算掛點僅接線未啟用，`run_all_daily_tasks()` 執行受 `PROJECT_STATUS.md` §0.5 #20 閘門） |
| **總計 (Total)** | - | - | **9 大核心 ADR + 7 大挑戰** | **18 大核心生產模組** | **17 大測試套件檔案** | **154 項測試** | **100% PASS (~1.80s)** |

---

## 3. 架構決策紀錄 (ADR) 快速索引

### 3.1 已核准 ADR（Gate 0-6 / Phase 3-4）

1. **DEC-001**: Single Source of Truth for Database Schema（資料庫單一真實來源，淘汰 embedded DDL）。
2. **DEC-002**: Seed Conflict Policy & DDL Error Propagation（初始資料冪等衝突與資料庫異常向上拋出）。
3. **DEC-003**: Failure Semantics & Strict NLP Pipeline（失敗傳遞、Exact-Title 快取命中判定、Strict Batch Checkpointing）。
4. **DEC-004**: Configuration Lifecycle & Bare Canonical Stock ID Contract（軟刪除防 AI 復活、標準純代碼持久化契約）。
5. **DEC-005**: Dual-Mode Prediction Architecture & Time Alignment Convention（雙模式預測架構、次一交易日 Roll-Forward 歸併、零前視偏誤目標標籤）。
6. **DEC-006**: Institutional Feature Engineering & Antweiler-Wilder Protocol（Antweiler 看多/一致性指數、Wilder's RSI-14、5D/20D 滾動年化波動率、純向量化特徵契約）。
7. **DEC-007**: Multi-Model Tournament & Alpha Attribution Protocol（Walk-Forward 時序切分、4 大模型 8 組平行對照實驗、Scaler 內部 Fit 防洩漏、Top 3 驅動因子即時推論）。
8. **DEC-008**: Streamlit Institutional Visual Architecture, Dual-Axis Interactive Charts & Zero-Dependency Fallback（彭博終端級深色模式、台美股色彩自適應、Plotly 雙層雙 Y 軸互動圖表、零依賴平滑回退安全網）。
9. **DEC-009**: Thematic Concept Basket Mapping, Sentiment Spillover & Radar UI（1-to-N 概念股知識映射表、70/30 動態加權情緒溢出特徵引擎、Streamlit 頂部題材雷達與一鍵選股預測連動）。

### 3.2 Upgrade Gate 0 ADR（狀態：`APPROVED` — 2026-08-23 由 Project Owner 核准）

10. **DEC-010**: Schema Version & Additive Migration Strategy（`schema_version` 表、Additive DDL、`apply_migrations.py` runner、5 層 Rollback 策略、禁止 DROP schema_version）。
11. **DEC-013**: Feature Registry as Single Source of Truth（版本化特徵契約 `LEGACY_17` / `CORE_16` / `COMMENT_ENHANCED_19`、OHLC 移出 Feature Store、**29 欄**資料契約含 2 個 Metadata/Lineage 欄、**10 條**測試斷言、§5A 全欄位 NULL 語意規則）。
12. **DEC-016**: Multi-Source Comment Data Contract（PTT/Dcard/Threads 獨立契約、Provider-prefixed ID、失敗語意三態 `SUCCESS_EMPTY`/`SOURCE_DEGRADED`/`SOURCE_FAILED`、Dcard Conditional 不阻擋 Gate 2）。
13. **DEC-011**: Purged Walk-Forward with Purge / Gap / Embargo（三者職責分離、全部以交易日計、禁用 `embargo_pct`、新增 `label_end_date`、核心斷言 `max(train.label_end_date) < min(test.trade_date)`）。
14. **DEC-017**: Stock Universe Definition & Point-in-Time Liquidity Ranking（前 150/500 大、60 交易日成交金額中位數、月度重建、Snapshot 保存、防 Survivorship Bias、新上市／下市／停牌／代碼異動處理）。
15. **DEC-018**: Triple-Barrier 三分類標籤、`Open[T+1]` Anchor 與 Ambiguous = NULL（進場價＝Barrier anchor 統一為 `Open[T+1]`、標籤 `{1, -1, 0}` + NULL、止損與 Timeout 分離、`label_reason` 追蹤三種 NULL 成因）。

> **狀態說明**：以上 6 份 ADR（DEC-010/011/013/016/017/018）已於 2026-08-23 由 Project Owner 核准 Gate 0 Closure Review 時一併核准，
> 狀態均更新為 `APPROVED`，`Approved by: Project Owner`，核准日期 2026-08-23。
> **DEC-011**（Purged Walk-Forward）、**DEC-017**（Point-in-Time Stock Universe）、**DEC-018**（Triple-Barrier 三分類與 `Open[T+1]` anchor）
> 因屬 Gate 0 Closure Review 需 PO 當下核准的決策，已於 V8 一併以 `Proposed` 寫入 `DECISIONS.md`，見上方第 13-15 項。
> 其餘規劃中的 ADR（DEC-012/014/015/019）方於各自觸發 Gate 啟動時正式撰寫。

### 3.3 Gate 1／Gate 2 SB 實作期間新增 ADR

> **本節於 UG-G2-SB1 evidence-sync 傳播時新增**：核對發現 DEC-012（UG-G1-SB2）、
> DEC-020（UG-G1-SB3）、DEC-021（UG-G1-SB4）、DEC-022（UG-G1-SB5）四則 ADR 早於本節建立即已存在於
> `DECISIONS.md`，但從未被列入本快速索引——此為先前各 SB 收尾時 evidence-sync 傳播清單的
> 遺漏，非本次新增之缺陷，隨 DEC-023 一併回填以避免同一問題持續累積。

16. **DEC-012**: UI Four-State Data Mode（`REAL`/`DEMO`/`EMPTY`/`ERROR` 四狀態資料來源透明化、方案 B——連線失敗不自動退回模擬資料）。狀態：`APPROVED`（PO 2026-08-25 核准）。
17. **DEC-020**: 模型競技排行榜動態化（`load_tournament_results()` 讀取 `models/artifacts/tournament_results.json`、資料量不足防線）。狀態：`APPROVED`（PO 2026-08-26 核准）。
18. **DEC-021**: RISK-013 根本解（`database/db_target_guard.py` 之 `assert_safe_migration_target()`，連線前守門）。狀態：`APPROVED`（PO 2026-08-26 核准）。
19. **DEC-022**: 歷史 ADR 記錄缺陷登錄（DEC-003/004/006/007/008/009 之補充註記總覽索引，`doc/evidence/` 原文不動）。狀態：`APPROVED`（PO 2026-08-26 核准）。
20. **DEC-023**: `label_reason` 判定範圍延後至 Gate 3 + `db_writer.py` NaN→NULL 轉換修正（UG-G2-SB1 實作階段即時裁決）。狀態：`APPROVED`（PO 2026-08-29 核准）。
21. **DEC-024**: 時點有效性判準——判準為「該數字在被歸屬交易日的決策時點是否已可見」，非「是否為發文當天數字」；約束**所有時間性會變動的特徵**，非僅留言計數。落地為 `comments_scraped_at`（migration 004）+ write-once 回填路徑 + `chk_comments_scraped_at_consistency` CHECK 約束（UG-G2-SB4）。狀態：`APPROVED`（PO 2026-08-29 核准）。
22. **DEC-025**: 留言計數聚合只採用直接個股文章，不套用 DEC-009 題材溢出（避免同源留言計入多檔成分股製造假的橫斷面相關性）（UG-G2-SB4）。狀態：`APPROVED`（PO 2026-08-29 核准）。
23. **DEC-026**: UG-G2-SB5 對 Gate 0 交付物的兩處偏離——(i) adapter 不接入 `main_etl_pipeline.py`（Master Plan Brief 加註）；(ii) 契約 §4.5 Feasibility Gate 由 A1–A5 強化取代、參數對齊 §4.2 正式端點。原文保留、加註說明，不刪改（UG-G2-SB5）。狀態：`APPROVED`（PO 2026-08-29 核准）。
24. **DEC-027**: Dcard 可用性驗證判定 `FAIL`（A1 HTTP 403，Cloudflare 邊緣攔截，A2–A6 `NOT EXECUTED`）→ 來源標記 `DEFERRED WITH EVIDENCE`，不建立 adapter；RISK-003 `NOT VERIFIED` → `OBSERVED`，**未標為已解決**；附重新評估觸發條件（UG-G2-SB5）。狀態：`APPROVED`（PO 2026-08-29 核准）。
25. **DEC-028**: 來源能力宣告（`source_capabilities.py` 的 `COMMENT_DIRECTION_SOURCES`／`provides_comment_direction()`）——方向類留言特徵只由結構上提供推／噓標記的來源計算，未登錄來源預設不提供方向；聚合層兩道把 `NULL` 壓成 `0` 的關卡（`fillna(0)` 與 `agg(sum)` 缺 `min_count=1`）一併處理；`has_comments` 拆為 `has_volume`／`has_direction`（UG-G2-SB5 決策點 5）。狀態：`APPROVED`（PO 2026-08-30 核准）。
26. **DEC-029**: 新增 `UG-G2-SB8`（CORE_16 四個平穩化特徵 + 讀取端缺口反查檢查）。狀態：`APPROVED`（PO 2026-08-31 核准）。
27. **DEC-030**: CORE_16 四個平穩化特徵的 NULL 策略修正，並新增第三種 NULL 成因 `U`（數學上未定義）——`MA5_Vol == 0` 既非暖機（W）亦非來源失敗（F），§5A.1 的窮舉性宣稱因此被推翻。狀態：`APPROVED`（PO 2026-08-31 核准）。
28. **DEC-031**: 新增 `UG-G2-SB9`（候選池價格資料取得），並修正 SB6／SB7 的循環依賴（**編號 9 但執行順序在 SB6 之前**）。狀態：`APPROVED`（PO 2026-08-31 核准）。
29. **DEC-032**: 對外取數的重試紀律——**403／429（服務在叫你停）硬停不重試；5xx／傳輸層（服務沒能回答）有界重試**。判別依據是「有沒有拿到 `status_code`」，不是例外類別名稱。狀態：`APPROVED`（PO 2026-09-02 核准，隨 `UG-G2-SB9` Gate B）。
30. **DEC-033**: 60 日流動性窗**嚴格早於** `effective_date`（DEC-017 的「生效日前已知」勝過提案內兩段含當日的校準 SQL），**§6 第 3 項的 46 列基準隨之作廢重算**——實測 8 列改變，**差異小到不會被列數總計發現**。狀態：`APPROVED`（PO 2026-09-03 核准，隨 `UG-G2-SB6` Gate B）。
31. **DEC-034**: 舊批 PTT 文章（`source = 'ptt_stock'`，331 列）以**允許清單排除**出特徵，**而非修正或刪除**——**就算 76 列錯誤的 `post_time` 修對了，那批仍是另一種取樣**（逐關鍵字搜尋橫跨七年 vs 看板固定頁面）；**修正日期只解決「哪一天」，不解決「怎麼取到的」**。允許清單而非排除清單，判準同 DEC-028（**漏登錄的後果應是「誠實地少」，不是「安靜地錯」**）。**資料一列未動，排除只發生在讀取端。** 規則見 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5B（**本則刻意不重述，避免 DEC-030 那種兩地漂移**）。狀態：`APPROVED`（PO 2026-09-05 核准，隨 `UG-G2-SB7` Gate B）。

---

### 3.4 Gate 3 SB 實作期間新增 ADR

32. **DEC-035**: 修訂 DEC-018 的 Triple-Barrier 標籤條件表——補上兩個規格原文未言明優先序的邊界情況：(a) 剩餘天數 < H 一律 `insufficient_data`，即使窗口內已觀察到觸線也不例外（避免序列尾端標籤系統性偏向極端走勢的截斷偏差）；(b) anchor／窗口內 High-Low 為 NUMERIC NaN 時分別判 `no_entry`／`insufficient_data`，NaN 檢查須先於觸線判定（`UG-G3-SB1` 綠色實作首版未處理，真實庫 NVDA `2026-06-04` 一列命中，非假設情境）。不新增 `label_reason` 值域。狀態：`APPROVED`（PO 2026-09-09 核准，隨 `UG-G3-SB1` Gate B）。
33. **DEC-036**: 新增 `UG-G3-SB2a`（458 檔 Universe 資料回補），自 `UG-G3-SB2` 拆分——`UG-G3-SB2` Gate A 唯讀查證發現 `universe_snapshots` 46 期跨期去重 458 檔（非僅最新一期 150 檔，面板為 PIT），455 檔無 `entity_mapping` 路由、但 458/458 檔已存在於 `candidate_prices`（價格資料已齊備，只是未搬進生產管線）。資料回補（`SB2a`）與讀取器工程（`SB2` 本體）分開驗收；路由補齊（455 筆）不隨拆分移出，維持在 `SB2` 本體（依 Gate 3 啟動書 §12 裁決⑥）；`UG-G3-SB3` 依賴兩者皆完成。狀態：`APPROVED`（`UG-G3-SB2` Gate B 核准結案時一併核准，2026-09-10）。
34. **DEC-037**: Roll-Forward 交易日曆改依股票自身，取代全市場聯集（RISK-027 方案 B，`bug-fix-protocol` 獨立小案）——`feature_aggregator.py` 原本的 `unique_trading_days` 取輸入價格表 `stock_id` 聯集，跨市場（含 NVDA）時把台股文章滾動到台股不存在的交易日、合併時靜默流失。新增 `assign_trading_days_per_stock()`：文章先展開成 `(article, stock_id)` 列，再依該列 `stock_id` 自身交易日曆做 Roll-Forward。候選方案 C（兩階段折衷）的前提「一文不會同時對到 TW 與 US」經真實庫唯讀查證（`theme_stock_mapping` 「AI伺服器」題材同時涵蓋 TWSE 與 NVDA）被推翻，故不採。`UG-G3-SB2a` 段 2 修復後須依 RISK-013 協議重跑，NVDA 不得作為零差異對照組；段 3（Triple-Barrier）為純價格計算不受影響。狀態：`APPROVED`（PO 2026-09-12 核准，隨 `UG-G3-SB2a` 段 2 重跑真實庫寫入完成——
132 鍵／14 檔股票，見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_rerun_risk027.json`）。

35. **DEC-038**: D3 對照實驗的兩種情緒覆蓋率子集口徑，與多數類基線 tie-break 規則（`UG-G3-SB3`）——`sentiment_subset`（股票子集，較寬）與 `signal_rows_subset`（列子集，較精確——`article_count>0` 或 `sentiment_5d_ma` 非 `NULL` 的列本身）兩者互補並列，不得只取其一；多數類基線票數並列時取數值最小者，確保可重現。兩者定義字串皆寫入報告 JSON 本身（`subset_definitions`／`aggregate.majority_baseline.rule`），不只留在原始碼。狀態：`APPROVED`（隨 `UG-G3-SB3` Gate B 核准結案，PO 2026-09-13）。

36. **DEC-039**: 留言特徵時點有效性改依逐則時間戳重算，取代文章層級擷取時點過濾，修訂 DEC-024（RISK-023，`bug-fix-protocol`）——RISK-023 診斷以已驗證的排程常數（`scheduler.py` 每日 15:35 執行一次、決策點 cutoff 15:30）獨立模擬穩定運作情境，發現 DEC-024「第一次擷取天然早於決策點」的前提結構性不成立，穩定運作下通過率僅約 0.2%。`_aggregate_direct_comment_counts()` 改為逐 `(article, stock_id)` 列呼叫 `comment_timeline.counts_as_of()`／`validate_comment_bounds()`，並新增 `comment_seq` 時間回退防禦性守衛（`suspect` → NULL，RISK-029，不去重）。真實庫唯讀全量重算實測：留言三欄現行全 NULL→新版至少一欄非 NULL 的組數 352、涉及股票數 8。狀態：`APPROVED`（2026-09-14，PO，真實庫寫入複核通過；DEC-024 同時轉 `SUPERSEDED`）。程式碼：`src/loaders/db_writer.py`、`src/transform/feature_aggregator.py`、`src/transform/comment_timeline.py`。測試：`tests/test_risk023_comment_recompute_red.py`（15 項，容器內全綠）；`tests/test_risk023_write_comment_features.py`（31 項）；`scripts/verify/risk023_p6_invariant_check.py`（新版 P6 不變式，唯讀資料庫腳本）。真實庫寫入：`scripts/verify/risk023_write_comment_features.py --write`，352 列（8 檔股票），證據 `doc/upgrade/gates/evidence/RISK023_comment_features_write.json`。見 `doc/upgrade/gates/closed/RISK023_GATE_A_PROPOSAL.md`。
37. **DEC-040**: Gate 3 Holdout 邊界落地（`UG-G3-SB4`，OOF Stacking Meta-Learner）——`PURGED_WALK_FORWARD_SPEC.md` §3.3／`SYSTEM_UPGRADE_MASTER_PLAN.md` §9／§11.3（2026-09-16 forward-fix，原誤引 §10，見 `DECISIONS.md` DEC-040）已核准的 Holdout 規格（最近 6～12 個月保留、不得用於模型／門檻選擇）首次落地成具體折序號與日期：對 `UG-G3-SB3` 凍結面板（兩個 target，sha256 已驗證）實測 `WalkForwardSplitter` 43 折，**Holdout = 折 33～42**（測試窗 2025-10-23～2026-08-20，約 10 個月），以 `HOLDOUT_START_DATE`（`2025-10-23`）常數表達，涵蓋 10 折本身與折 42 之後 1,650 列缺口。`UG-G3-SB4`～`SB6` 全程不得讀取／訓練／評估／選擇 Holdout 資料，`UG-G3-SB7` 為唯一消費者，已於 2026-09-16 完成消費（見條目 38）。狀態：`APPROVED`（`UG-G3-SB4` Gate B 核准，2026-09-15）。程式碼：`src/ml/stacking.py`（`HOLDOUT_START_DATE`／`META_EVAL_START_DATE` 常數、`iter_oof_folds()`）。測試：`tests/test_ug_g3_sb4_stacking_red.py::ConstantsPinnedTests`／`HoldoutFoldsNeverIteratedTests`（含半折洩漏 known-FAIL）；`UG-G3-SB4` 全量執行（folds 0-32）對兩個 target 的 OOF parquet 皆二次確認零 Holdout 列，`VERIFIED THIS SESSION`。見 `doc/upgrade/gates/closed/UG_G3_SB4_GATE_A_PROPOSAL.md` §2.5／§4.4、`closed/UG_G3_SB4_GATE_B_SUBMISSION.md` §6。
38. **DEC-041**: Gate 3 後續主線改以 `target_triple_barrier`／Timeout 為對象（`UG-G3-SB5`，Probability Calibration）——實測發現 `target_up_down` 在折 27-32 全線無可偵測的 OOF 排序訊號（四個 Specialist 與 Meta(A) AUC 皆 ≈0.50，`RISK-030`），`target_triple_barrier` 的 Timeout 類則有實質訊號（OvR AUC 0.82～0.91）。裁決：`UG-G3-SB6` 對 `target_up_down` 停做；改以 Timeout 類校準後機率為 gating 對象（產品形態「何時不交易」）；方向預測特徵改進登記候補案，排 `UG-G3-SB7` 之後，與 `RISK-015` 連動；`SYSTEM_UPGRADE_MASTER_PLAN.md` §11.1 條件勝率目標保留數字、加狀態註記。狀態：`APPROVED`（`UG-G3-SB6` Gate B 核准，2026-09-16）。測試：`src/ml/gating.py`（38 項紅測 `900c616`→GREEN `09bcba9`）與 `scripts/verify/ug_g3_sb6_gating_report.py`（60 項紅測 `23e2039`→GREEN `81def57`，簽章訂正 `3eacb6f`／`cd5f69a`，鍵名訂正 `217eb43`／`8ef8378`）；全量執行證據 `doc/upgrade/gates/evidence/UG_G3_SB6_gating_report.json`（`θ*=0.06907`，覆蓋率 80.00%／精準度提升 4.15×／召回 83.03%）。**`UG-G3-SB7` Holdout 驗證（2026-09-16，`VERIFIED THIS SESSION`）**：三項判準於 Holdout（折 33-42）成立（覆蓋率 0.9252／精準度提升 10.73×／召回 0.8028）；波動率單變數基線與 Timeout gating 表現接近，未下結論，登記候補案。見 `doc/upgrade/gates/closed/UG_G3_SB5_GATE_B_SUBMISSION.md` §2／§5、`doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md`、`doc/upgrade/gates/closed/UG_G3_SB7_GATE_B_SUBMISSION.md`、`doc/upgrade/gates/evidence/UG_G3_SB7_holdout_report.json`。
39. **DEC-042**: §0.5 #32 成因 F 失敗鍵推導規則（PTT 覆蓋缺口＋NLP 未完成 → `SOURCE_FAILED`）——`FeatureAggregator.generate_daily_features()` 已支援 `failed_source_keys` 參數，但生產呼叫點 `main_etl_pipeline.py` 從未傳入，PTT 來源失敗與 NLP 未完成兩種「沒觀測到」的情形，特徵表一律寫成 `SUCCESS_EMPTY`，把「沒查到」與「查了、真的沒有」混為同一個值。起算點 `MIN(batch_key) WHERE source='ptt'`、多關鍵字任一覆蓋語意皆 PO 裁定。狀態：`APPROVED`（Approved by: Project Owner，2026-09-21）。測試：紅測 `431c2be`（11 條）→GREEN `ee0b384`→複核追加子案例 `9079915`（超出交易日曆的 NLP 文章不得崩潰）。段 B 拋棄式庫演練與段 C 真實庫首次生效（第二次真實每日 ETL，2026-09-18，五條驗收全數 PASS，新增列數 8=8、`SOURCE_FAILED` 翻轉列 47=47 逐列相等）。見 `doc/upgrade/gates/closed/FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`。
40. **DEC-043**: §0.5 #31＋#33 Gemini 用量紀律（探索頻率／每日配額分類／既有映射凍結）——`upsert_theme_stock_mapping()` 改 `ON CONFLICT (theme_keyword, stock_id) DO NOTHING`，既有映射的 `relevance_weight`／`stock_name`／`updated_at` 不再被探索結果覆寫，只有全新配對會被插入。狀態：`APPROVED`（Approved by: Project Owner，2026-09-19）。測試：紅測 `86ad3b1`（12 條）→GREEN `9536771`→審查方複核 16 項突變 15 中、補測 3b `7861d14`。段 B 五場景演練與段 C 真實庫首次生效（第三次真實每日 ETL，2026-09-19，七條驗收全數 PASS，`theme_stock_mapping` 66 列執行前後完全相等）。見 `doc/upgrade/gates/closed/GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md`。
41. **DEC-044**: `FEATURE_REGISTRY.md` `Source` 欄改函式／方法名稱錨點，禁止指向巢狀函式（§0.5 #38，`gate0_contract_check.py` 新增 B15）——15 處行號引用中 14 處已漂移指到無關程式碼，行號當錨點結構上保證隨程式碼插入而失效；改為函式／方法名稱（19 列，5 頂層函式＋14 類別方法），並新增機械檢查 B15 反查每個錨點是否存在於原始碼，複核第三輪追加「提及 `.py` 卻抽不到任何錨點即 FAIL」規則（防整列零錨點的行號回歸盲區）。狀態：`APPROVED`（Approved by: Project Owner，2026-09-21）。程式碼：`scripts/verify/gate0_contract_check.py`（B15）。測試：紅測 `c9ed87d`（含複核第三輪補強）。見 `doc/upgrade/gates/closed/FEATURE_REGISTRY_SOURCE_ANCHOR_GATE_A_PROPOSAL.md`。
42. **DEC-045**: 統一 Gemini 暫態例外判斷清單，`deadline`／`504` 不列為可重試（§0.5 #36）——`trend_discover.py`／`nlp_processor.py` 兩份清單真包含關係且皆缺 `504`；新建 `src/common/gemini_retry.py` 為唯一共用來源，取聯集後移除 `deadline`（同一份 payload 重送不會讓伺服器端 deadline 變短，重試只會白燒配額）、不新增 `504`（`504` 訊息本已含 `deadline` 字面詞，涵蓋不新增才自洽）。狀態：`APPROVED`（Approved by: Project Owner，2026-09-21）。程式碼：`src/common/gemini_retry.py`（新建）、`src/extractors/trend_discover.py`／`src/transform/nlp_processor.py`（改委派）。測試：紅測 `6b0eb37`→GREEN `b0d928e`（含複核追加的 `assertIs` 身分比對）。見 `doc/upgrade/gates/closed/GEMINI_TRANSIENT_KEYWORDS_UNIFY_GATE_A_PROPOSAL.md`。
43. **DEC-046**: 給 PO 的一頁式進程摘要——格式、時機、存放位置（`doc/progress/`，本機不版控，GOV 決策）——Gate B 報告對 PO 是雜訊，PO 需要概念層說明；八節固定格式（含「未驗證假設」「動了哪個前提」兩項必填，對應盲點提早浮現的需求），存 `doc/progress/`，加入 `.gitignore`、不進 `DOC_PATHS`、不維護、不回填，綁進 `gate-submit` skill 產出 10（綁事件不綁個案，同 GOV-09 教訓）。狀態：`APPROVED`（Approved by: Project Owner，2026-09-21，本次裁決直接核准）。影響範圍：`.gitignore`／`doc/README.md`／`.claude/skills/gate-submit/SKILL.md`／`doc/governance/TEAM_PLAYBOOK.md`。見 `DECISIONS.md` DEC-046。

---

## 3A. Upgrade Gate 0 交付物追溯矩陣 (Gate 0 Deliverable Traceability)

> Gate 0 為**純文件 Gate**，交付物為規格與契約文件，尚無對應程式碼與測試。
> 追溯鏈為：`PO 決策／稽核發現 → Gate 0 交付物 → 提案 ADR → 未來實作 SB → 未來測試`。

| 交付物 | 文件路徑 | 來源依據 | 對應 ADR | 未來實作 SB | 未來測試 | 狀態 |
|--------|---------|---------|----------|-------------|----------|------|
| **A** 文件漂移對照表 | `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` | 2026-08-21 深度程式碼稽核 | — | UG-G1-SB5 | grep 驗證（禁用詞／特徵數／測試數） | `READY FOR PO REVIEW` |
| **B** Gate 0 規格 | `SYSTEM_UPGRADE_MASTER_PLAN.md` §5-6 | PO Gate 0 授權 | — | — | §18 Part A/B 驗證 | `READY FOR PO REVIEW` |
| **C** Feature Registry | `doc/upgrade/contracts/FEATURE_REGISTRY.md` | 特徵數漂移（17/15/18/19 矛盾） | **DEC-013** | UG-G2-SB1, UG-G2-SB4 | `test_feature_store_total_columns_29`（UG-G2-SB1 實作時修正，見 §2 追溯矩陣 DEC-023 列；此處與 `SYSTEM_UPGRADE_MASTER_PLAN.md`／`DOCUMENT_DRIFT_REMEDIATION.md` DRIFT-003 同批 27→29 修正之殘留，本次一併處理）、A1-A8 斷言 | `READY FOR PO REVIEW` |
| **D** Multi-Source Data Contract | `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` | PO 多來源優先序決策 + AGENTS.md §7.1 失敗語意原則 | **DEC-016** | UG-G2-SB2, UG-G2-SB3, UG-G2-SB5 | `test_source_failed_raises`、`test_success_empty_valid`、`test_dcard_failure_isolation` | `READY FOR PO REVIEW` |
| **E** DB Migration & Rollback Plan | `doc/upgrade/contracts/DB_MIGRATION_PLAN.md` | 稽核發現「無 Migration 機制」 + DEC-002 重新評估條件成立 | **DEC-010** | UG-G1-SB4, UG-G2-SB1, UG-G2-SB3 | `test_migration_idempotency`、`test_version_check`、`test_rollback_on_failure` | `READY FOR PO REVIEW` |
| **F** Purged Walk-Forward Spec + Triple-Barrier Contract | `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md` | 稽核發現時序邊界洩漏 + PO Triple-Barrier 決策（`Open[T+1]` anchor、三分類標籤） | **DEC-011**（`APPROVED`）、**DEC-018**（`APPROVED`） | UG-G1-SB1, UG-G3-SB1 | T-PW-01~05、T-TB-01~17（T-TB-13~17 為 `UG-G3-SB1` Gate A 執行期新增，見規格 §5.2）、T-INT-01~02 | `READY FOR PO REVIEW` |
| **G** Gate & SB 矩陣 | `SYSTEM_UPGRADE_MASTER_PLAN.md` §5, §7-10 | PO 批次拆分要求 | — | 全部 24 個後續 SB | 各 SB 自帶測試清單 | `READY FOR PO REVIEW` |
| **H** 修訂版 Master Plan | `SYSTEM_UPGRADE_MASTER_PLAN.md` | PO V5 審查 10 項 Required Corrections | — | — | §18 Part A（12 項） | `READY FOR PO REVIEW` |
| **I** ADR 清單 | `doc/evidence/DECISIONS.md`（DEC-010/013/016）+ Master Plan §15 | Gate 0 觸發之架構決策 | DEC-010, DEC-013, DEC-016, DEC-011, DEC-017, DEC-018 | 各觸發 Gate | §18 Part B — B8 驗證 | `CLOSED`（狀態 `APPROVED`，2026-08-23）|
| **J** 剩餘風險清冊 | `doc/upgrade/contracts/REMAINING_RISKS.md` | 稽核 + PO 決策衍生風險 | — | 各風險對應 Gate | 風險接受準則審查 | `READY FOR PO REVIEW` |

### 3A.1 Gate 0 決策鏈（PO 決策 → 文件落地）

| PO 決策 | 落地文件與章節 | 對應 ADR |
|---------|---------------|----------|
| Stock Universe 前 150/500 大、Point-in-Time、月度重建 | Master Plan §3.1；UG-G2-SB6 Brief | **DEC-017**（`APPROVED`） |
| 多來源優先序 PTT > Dcard > Threads，Dcard 為 Conditional | Master Plan §3.2；`MULTI_SOURCE_DATA_CONTRACT.md` §4, Appendix A | **DEC-016** |
| Triple-Barrier `Open[T+1]` anchor、三分類 `{1,-1,0}`、同日觸雙線 NULL | Master Plan §3.3；`PURGED_WALK_FORWARD_SPEC.md` §4 | **DEC-018**（`APPROVED`） |
| 版本化特徵契約、OHLC 移出 Feature Store | Master Plan §3.4, §4；`FEATURE_REGISTRY.md` 全文 | **DEC-013** |
| Migration 分層 Rollback、禁止 DROP schema_version | Master Plan §12.4；`DB_MIGRATION_PLAN.md` §7 | **DEC-010** |
| Purge/Gap/Embargo 以交易日計，非百分比 | Master Plan §13.2；`PURGED_WALK_FORWARD_SPEC.md` §2 | **DEC-011**（`APPROVED`） |
| Benchmark 至少 3 年 + Holdout 6-12 個月、基準三分類 | Master Plan §11；UG-G3-SB7 Brief | — |
| 來源失敗不得偽裝成空結果；留言特徵失敗保持 NULL | `MULTI_SOURCE_DATA_CONTRACT.md` §7；`FEATURE_REGISTRY.md` §3.5, §5A | **DEC-016** |

### 3A.2 Gate 0 證據邊界

- Gate 0 交付物為**規格文件**，其正確性由 Master Plan §18 的三組驗證支持：
  Part A（12 項單一文件正確性）、Part B（**10 項**跨文件契約反查）、Part C（測試套件執行證據）。
- Gate 0 **不包含**任何業務程式碼修改或資料庫遷移；上表「未來測試」欄為各 SB 實作時的驗收目標，目前狀態一律為 `PLANNED`。
- Gate 0 **確實執行了既有測試套件**以驗證文件修訂未造成回歸（見下方）。

#### 測試執行證據（`VERIFIED THIS SESSION`）

| 項目 | 內容 |
|------|------|
| 執行日期 | 2026-08-23 |
| 執行指令 | `python -m unittest discover -s tests -p "test_*.py"` |
| 環境 | Windows 本機 Python 3.10.11（**非** Dev Container） |
| **結果** | **`Ran 154 tests in 1.486s` / `OK`** |
| 獨立複驗 | Project Owner 於審查時自行執行，得 `Ran 154 tests in 1.643s` / `OK` |

#### 證據邊界（必須與 Master Plan §18.3 一致）

| 標籤 | 範圍 |
|------|------|
| `VERIFIED THIS SESSION` | 154 項測試在 `numpy` / `pandas` / `streamlit` / `plotly` 齊備的環境下全數通過 |
| `PREVIOUSLY VERIFIED` | Gate 0-6 / Phase 3-4 各 Gate 關閉時的人工審查與 QA 結論 |
| **`NOT VERIFIED`** | `sklearn` / `lightgbm` / `xgboost` 本次環境**缺席**，相關測試走程式內建的純 NumPy fallback 路徑 — **不等於**真實 ML 套件行為已驗證 |
| **`NOT VERIFIED`** | `psycopg2` 缺席，所有 DB 存取皆為 `@patch` 替身 — 未觸及真實 PostgreSQL |
| **`NOT VERIFIED`** | Dev Container 環境（Python 3.14.6 + 完整依賴）本次未執行；Live Gemini API、真實 PTT 爬蟲皆未觸及 |

- 跨文件契約驗證（Part B）另有可重跑腳本 `scripts/verify/gate0_contract_check.py`，
  2026-08-23 執行結果 **10/10 PASS, exit 0**。

---

## 4. 驗證證據與邊界守衛 (Evidence Boundary Defense)

本專案對所有成果之宣稱均遵循嚴謹的科學證據標籤：

1. **已獲嚴格驗證（VERIFIED THIS SESSION / PREVIOUSLY VERIFIED）**：
   - **154 項自動化測試**：host（Windows Python 3.10.11）與 dev container（Python 3.14.6）均全數通過。
     **執行時間 host ~1.5s／container 6.1~10.1s**。
     ⚠ **更正（GOV-02, 2026-08-23）**：本行原稱兩環境「均全數極速通過（~1.80s）」，
     但 GOV-02 確認 2026-08-23 是**史上第一次**有人在容器內執行測試 —— 在此之前所有紀錄皆來自 host。
     `~1.80s` 是 host 的時間；容器實測為 6.1~10.1s。
     ⚠ **證據邊界**：host 缺 `sklearn`／`lightgbm`／`xgboost`／`psycopg2`／`jieba`／`snownlp`／`tenacity`／`dotenv`，
     相關路徑走 fallback 或 mock。host 的通過**不支撐任何 ML／NLP／重試／LLM 路徑的宣稱**（見 `CLAUDE.md` §13.0）。
   - **全流程零前視偏誤**：透過 Walk-Forward 時序切分、Roll-Forward 交易日對齊、Scaler 嚴格 Train Set Fit 與 Target 標籤最後一日 NaN 斷言守衛。
   - ~~**8 組平行實驗 Alpha 歸因**：量化證明社群情緒融合模型相較純價量控制組帶來顯著之超額報酬。~~
     ⛔ **本項宣稱已撤回（DRIFT-018, 2026-08-24）**。被「量化證明」的正是 `components.py:129-138`
     的 8 個字面常數，而該組數值存在三項矛盾：冠軍在所有指標輸給亞軍與季軍；
     `lightgbm` 與 `xgboost` 在 host 上是同一個 fallback 類別卻有兩個分數；且不連結任何實驗產出物。
     現行標註為**「未經驗證的展示值，證據待補」** —— 不宣稱其為捏造，
     但主張其為量測結果的一方負舉證責任，目前舉不出來。歸屬 UG-G1-SB2 處理。
   - **真實文章三重查詢與空狀態透明化**：個股、題材與標題模糊比對全面打通，空資料透明提示不造假。

2. **明確標記未驗證邊界（NOT VERIFIED）**：
   - 實體生產環境 PostgreSQL 長期每日定時排程（已規劃 GitHub Actions / Cloud Cron 方案，目前開發維持本機容器）。
   - 外部 PTT 即時爬蟲連線與 Live Gemini API 費用消耗（測試全面採用隔離 Mock / 離線 Fallback）。
