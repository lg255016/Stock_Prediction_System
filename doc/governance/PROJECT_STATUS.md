# Project Status

> 此文件用於 Conversation Handoff（對話交接），不是規格或工程決策的替代品；新對話仍須重新核對 Git 與 Repository 實際狀態。
>
> **§0 為現行狀態（2026-08-24）。§1 以下為 PRE_CODEX 時期的舊紀錄，證據快照日期 2026-08-20，其 Gate 編號與現行升級專案不同名同義 —— 先讀 §0。**

## 0. 現行狀態（2026-08-24，UG 升級專案）

> **編號警告【務必先讀】**：本文件 §1 以下（含「Gate 0–6」「Phase 3／4」「Milestone B」）
> 記錄的是 **PRE_CODEX 時期的舊計畫**，其計畫書已封存於
> `doc/archive/PRE_CODEX_REMEDIATION_PLAN.md`。
> 那些 Gate 編號與現行升級專案的 `UG-Gate-0` ~ `UG-Gate-4` **是不同的東西但同名**。
> **現行狀態一律以本節（§0）為準。**

### 0.1 權威規則來源

**`CLAUDE.md`（Repository 根目錄）是現行權威** —— Claude Code 實際載入的專案規則。

`AGENTS.md` 已標記 **Deprecated**，僅作為相容錨點保留（已核准的 Gate 0 ADR 以 `§7.x`
形式引用其條文，故不刪除）。**新對話請先讀 `CLAUDE.md`，不要以 `AGENTS.md` 為準。**

文件地圖見 `doc/README.md` —— 回答「哪份文件屬於誰、還活著嗎」。

### 0.2 升級專案進度

| 單元 | 狀態 | 證據 |
|------|------|------|
| **UG-Gate-0**（文件與規格設計） | **CLOSED**（2026-08-23 PO 核准） | `3baa34f` |
| GOV-01 治理層（`CLAUDE.md` + 可載入 skills） | 完成 | `91f0166` |
| GOV-02 容器測試基線量測 | 完成 | `2e0a8a5`、`2d51faf` |
| GOV-03 依賴釘選與環境可重現性 | 完成 | `0269fb1` |
| GOV-04 pre-commit hook | 完成 | `fc7cead` |
| GOV-05 文件依歸屬與生命週期分類 | 完成 | `abfa743`、`7f7258e` |
| GOV-06 交接 | 完成 | **`7f8657e`** —— **本列原寫「本次｜本 commit」，2026-09-06 補正**。「本次」「本 commit」是**寫入當下的相對指涉**，離開那個 commit 就指不到任何東西（與 `MULTI_SOURCE_DATA_CONTRACT.md` §3.6B 原本的「見本節加入時的 commit」是同一個病，同日一併修正） |
| GOV-07 退役五角色模型，建立 `TEAM_PLAYBOOK.md` | 完成 | **`3268e81`** —— ⚠ **本 hash 是用建檔紀錄回推的**（`git log --diff-filter=A -- doc/governance/TEAM_PLAYBOOK.md`），**因為沒有任何 commit message 提到 GOV-07**。**其餘各案都能用 `--grep="GOV-xx"` 找到，GOV-07 不能** —— **若日後有人想用 grep 盤點 GOV 案，GOV-07 會靜默地不出現，而輸出看起來完全正常。** |
| GOV-08 `CLAUDE.md` §11A.1 區分 `git restore` 兩種形式 | 完成 | `735f623`、`3362add` |
| GOV-09 `CLAUDE.md` §16.3 補規則 5、6，移除硬編碼 SB 數 | 完成 | **`43f75ce`** —— ⚠ **不是 `bd5d516`**：後者是 Gate 2 結案 commit，只是**訊息裡提到** GOV-09。**`--grep` 找到的是「提到它的」，不是「它本身」** —— 同 AST／grep 分不出「呼叫」與「提到」的那個形狀 |
| GOV-10 `TEAM_PLAYBOOK` 兩處事實更正 | 完成 | `ca7cbd1` |
| GOV-11 收緊 RISK-013 覆蓋範圍措辭 | 完成 | `d477a8b` |
| GOV-12 pre-commit 檢查 2 具名出口 + `CLAUDE.md` §12.4 | 完成 | `2f0130b`、`7bd8879` —— ⚠ **上線兩天，「情況 (1) 不得使用具名出口」的但書用上了一次，且是被實作者自己攔下的**（B0 判準補正時 `json.dumps(indent=1)` 整檔重新縮排）。**具名出口的風險不是「有人惡意繞過」，是「一個誠實的人在誠實地填寫理由時，把一件他沒察覺的事情帶了進去」** |
| **UG-Gate-1** | **已核准，五個 Small Batch 全數 CLOSED（2026-08-26）** | 見下方五列 |
| └ **UG-G1-SB1** Purged Walk-Forward | **CLOSED**（2026-08-25 PO 核准結案） | commit `ccf0e52a9e8496bd8fb1733cd3748433dbcfd8fd`；證據見 `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_STEP4_AFTER_SNAPSHOT.md`、`doc/upgrade/gates/closed/SB1_GATE_B_SUBMISSION.md`；DEC-011、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-012）已同步 |
| └ **UG-G1-SB2** UI Demo/Real 模式分離 | **CLOSED**（2026-08-25 PO 核准結案；DEC-012 方案 B 裁決） | commit `414fcc81fccde57d84e883b4a44a9b0e50465500`；證據見 `doc/upgrade/gates/closed/SB2_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB2_STEP3_IMPLEMENTATION_REPORT.md`、`doc/upgrade/gates/closed/SB2_STEP0_4_5_RECORD.md`、`doc/upgrade/gates/closed/SB2_GATE_B_SUBMISSION.md`；DEC-012、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-009／HERM-A/B/C/E）已同步；過程中發現並修復 ERROR 模式 `StreamlitDuplicateElementId` 當機 bug |
| └ **UG-G1-SB3** 模型競技排行榜動態化 | **CLOSED**（2026-08-26 PO 核准結案；方案 B + 4 項附帶裁決，DEC-020 `APPROVED`） | commit `61016ee19c07caec990b51563f21b7f6571412b9`；證據見 `doc/upgrade/gates/closed/SB3_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB3_GATE_B_SUBMISSION.md`；DEC-020、`TRACEABILITY.md`、`DOCUMENT_DRIFT_REMEDIATION.md`（DRIFT-008／DRIFT-018 歸屬修正）、SDD UI 章節已同步；真實 artifact 因資料量不足暫未產出（`load_tournament_results()` 正確顯示 `EMPTY`）；過程中發現並修復兩個既有缺陷（`label_end_date`／`trade_date` 型別不一致、資料量防線設計缺陷） |
| └ **UG-G1-SB4** DB Migration 機制（含 RISK-013 根本解） | **CLOSED**（2026-08-26 PO 核准結案；兩階段皆完成，DEC-010 Verification 補齊、DEC-021 `APPROVED`） | 階段一 commit `d2a4d4894328d2ef5e186aa2aa45ec02a0fdea0b`；階段二 commit `0fdb9c50c774388b42842075bdf69b2c12e666e0`；證據見 `doc/upgrade/gates/closed/SB4_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB4_STEP1_GATE_B_SUBMISSION.md`、`doc/upgrade/gates/closed/SB4_STEP2_GATE_B_SUBMISSION.md`；DEC-010、DEC-021、`TRACEABILITY.md`、SDD、`DB_MIGRATION_PLAN.md`、`REMAINING_RISKS.md`（RISK-013 已解決／RISK-006 部分驗證）已同步 |
| └ **UG-G1-SB5** 文件全面校正（Gate 1 最後一個 SB） | **CLOSED**（2026-08-26 PO 核准結案） | commit `31f5507ce1fc0cecebd468d0065a63f90c984412`；證據見 `doc/upgrade/gates/closed/SB5_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/SB5_GATE_B_SUBMISSION.md`；DEC-022 新增、`DECISIONS.md`（DEC-003/004/006/007/008/009 補充註記）、`CHALLENGES.md`、`DOCUMENT_DRIFT_REMEDIATION.md`、PRD、SDD、根目錄 `README.md` 已同步；純文件修改，未動 `src/`／`database/` |
| **UG-Gate-2** | **已核准關閉（2026-09-06，PO 核准）**——九個 Small Batch + `UG-G2-MIG` 全數 CLOSED；關閉審查見 `doc/upgrade/gates/closed/GATE2_CLOSURE_REVIEW.md` | 見下方十列 |
| └ **UG-G2-SB1** `daily_ml_features` Schema 擴充（7→29 欄） | **CLOSED**（2026-08-27 PO 核准結案） | 實作 commit `ef029a6b5753d071e9c17f0227389d0772681097`；evidence-sync commit `014b372b7b03500c44d766e6e8d957d129973bac`；證據見 `doc/upgrade/gates/closed/G2_SB1_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/G2_SB1_GATE_B_SUBMISSION.md`；DEC-023 新增（`label_reason` 範圍延後至 Gate 3、`db_writer.py` NaN→NULL 轉換修正）、`TRACEABILITY.md`、Master Plan §15.1 已同步；隔離容器 `g2sb1_ml_features_tmpdb`（非 `postgres-data` 掛載）完成完整 E2E 驗證，已拆除 |
| └ **UG-G2-SB2** PTT 內頁留言解析 | **CLOSED**（2026-08-27 PO 核准結案） | commit `543beb4771a645f8eb208904316bdfdba63b79d2`；證據見 `doc/upgrade/gates/closed/G2_SB2_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/G2_SB2_GATE_B_SUBMISSION.md`；`SOURCE_DEGRADED`／`SOURCE_FAILED` Failure Semantics 拆分、`main_etl_pipeline.py` 捕捉例外、真實 PTT 網站唯讀驗證（審查員先審查、PO 核准後執行）已完成；過程中修復 4 個既有測試檔的 `bs4` stub 隔離缺陷；「Top-5 高讚留言擷取」已自 Master Plan 移除（無契約依據亦無消費者） |
| └ **UG-G2-SB3** `market_articles` Schema 擴充 | **CLOSED**（2026-08-27 PO 核准結案） | commit `db03541f31ffd6b7145a434d30a051caec8bf1ec`；證據見 `doc/upgrade/gates/closed/G2_SB3_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/G2_SB3_GATE_B_SUBMISSION.md`；Migration 003（15 欄、四個留言計數欄無 `DEFAULT`、`provider_article_id` 一般索引）、`db_writer.py` 13 欄寫入契約、`data_cleaner.build_ptt_provider_article_id()`；Gate A 階段 PO 發現並修正 `MULTI_SOURCE_DATA_CONTRACT.md` §2.2 的 `DEFAULT 0` 矛盾與 `gate0_contract_check.py` B4 檢查的結構性盲點；一併修掉 DEC-023 登記的 NaN→None 未稽核寫法；隔離容器 `g2sb3_articles_tmpdb`（非 `postgres-data` 掛載）完成 E2E 驗證，已拆除；**待辦已登記於 Master Plan `UG-G2-SB4` Brief**：`parse_article_comments()` 尚無呼叫端、`push_count` 雙語意型態陷阱 |
| └ **UG-G2-SB4** 留言接線與衍生特徵計算 | **CLOSED**（2026-08-28 PO 核准結案） | commit `3a470ec5430aa43f075fa0c152a7b22188ab82f2`；證據見 `doc/upgrade/gates/closed/G2_SB4_GATE_A_PROPOSAL.md`、`doc/upgrade/gates/closed/G2_SB4_GATE_B_SUBMISSION.md`；**DEC-024**（時點有效性判準——判準為「該數字在被歸屬交易日的決策時點是否已可見」，非「是否為發文當天數字」；約束**所有時間性會變動的特徵**，非僅留言計數）與 **DEC-025**（留言聚合只算直接個股文章，不套用 DEC-009 題材溢出）新增，兩者已寫入 `FEATURE_REGISTRY.md` §5.5／§5.6 契約本文；Migration 004（`comments_scraped_at`）+ write-once 回填路徑；隔離容器 `g2sb4_comments_tmpdb`（非 `postgres-data` 掛載）完成端到端實證（留言計數確實進 DB、URL 去重、write-once 兩層防護、三特徵由真實留言數算出且與人工核算逐位相符、時點過濾於真實 DB 路徑生效），已拆除；真實 Universe 覆蓋率標記 `NOT VERIFIED`（歸 RISK-015） |
| └ **UG-G2-SB5** Dcard Adapter（CONDITIONAL） | **`DEFERRED WITH EVIDENCE`**（2026-08-29 可用性驗證 `FAIL`；**不阻擋 Gate 2 關閉**） | 可用性驗證依 Gate A 提案 §3 的 A1–A5 判準執行（判準於執行前經 PO 核准且事後未調整）：**A1 回 HTTP 403**，回應為 HTML 挑戰頁（`<title>` = `Attention Required! | Cloudflare`、`Server: cloudflare`、`CF-RAY: a32a14aa2c2a8f15-TPE`、`set-cookie: __cf_bm=…`）——**Cloudflare 邊緣攔截，請求未觸及應用層**，因此 **A2～A6 全部 `NOT EXECUTED`**；**端點是否仍存在、契約 §4.3 五欄是否仍正確，本次未取得任何證據**。請求用量：邏輯 1／3、HTTP 嘗試 1／9，剩餘配額未使用（同一出口 IP 再打無鑑別力）；**未嘗試繞過**。原始證據：`doc/upgrade/gates/evidence/G2_SB5_availability_evidence.json`、`G2_SB5_keywords_snapshot.json`；提案與判定過程見 `doc/upgrade/gates/closed/G2_SB5_GATE_A_PROPOSAL.md` §17；DEC-026（兩處契約偏離）、DEC-027（可用性判定與延後）新增；RISK-003 由 `NOT VERIFIED` → **`OBSERVED`**，**未標為「已解決」**；契約 §4 已加註「暫停適用」（原文保留）。**未建立 `src/extractors/dcard_scraper.py`**（不留空殼檔案），`src/`／`database/` 未修改。**決策點 5（來源能力宣告，PO 裁定不分 PASS／FAIL 都要做）與本次 FAIL 無關，另走獨立 Gate B** |
| └ **UG-G2-MIG** 真實開發資料庫 Migration 同步（RISK-017） | **CLOSED**（2026-08-31 PO 核准 Gate B；**本格於 2026-09-06 補正**——原寫「待 Gate B 核准」，而 `closed/G2_MIGRATION_SB_GATE_B_SUBMISSION.md` 早已在 `closed/`，**三者無法同時為真；PO 確認核准屬實，本次僅補同步**。⚠ **與 DEC-030 同型：兩份文件對同一件事說法不同，而從文件本身分不出哪一份是對的——這是第二次**） | **本專案第一次真正的整合驗證**——至今所有 E2E 都在拋棄式容器裡。步驟 1：`pg_dump` 備份（36,506 bytes）並**實際還原至臨時容器驗證通過**（7 張表、逐表列數、10 欄、抽樣內容四項判準）——**RISK-006 的還原流程第一次實地驗證**；步驟 2：migration 001～004 套用至 `postgres`@`localhost:5432`（`MAX(version)=4`），`market_articles` 10→**16 欄**、`daily_ml_features` 7→**29 欄**、七張原表列數完全不變，`chk_comments_scraped_at_consistency` 由 331/331 列實測成立；步驟 3：`run_feature_engineering_pipeline()` 對真實庫**實際執行成功**（117 列寫入），§6.1 六項寫死的預期**全部相符**——其中**三個留言特徵 0/117 非 NULL**，在真實資料上證明 `UG-G2-SB5` 決策點 5 的修正有效（修正前會產出 117 列全是 `1.0` 的偽造訊號）；`market_articles` md5 逐字元未變。交付 `scripts/verify/check_schema_version.py`（RISK-017 緩解第 3 條，含兩個 known-FAIL 案例）。**步驟 2 揭露一項不符**：`market_articles` 實測 16 欄而提案寫死 15——**錯的是提案的算術（10+5+1=16），不是資料庫**，依規則停止回報後由 PO 核准修正；**預期先寫死抓到的不是 migration 的錯，是提案自己的錯**。RISK-017 → `MITIGATED`（**未標為已解決**：緩解第 2 條「DoD 措辭必須指名目標資料庫」是需要每個 SB 持續遵守的規則，非一次性動作）；RISK-019（`google.generativeai` 已停止支援）新增；RISK-013 措辭修正（守門僅覆蓋 `apply_migrations.py`，`DBWriter` 不受保護且基於結構理由不應加裝）。全套測試 269/OK（隔離臨時 DB，已拆除）；`src/` 未修改 |
| └ **UG-G2-SB8** CORE_16 四個平穩化特徵 | **CLOSED**（2026-08-31 PO 核准結案；DEC-029 新增本 SB、**DEC-030** NULL 策略修正） | 實作 commit `bd926a6`；證據見 `doc/upgrade/gates/closed/G2_SB8_GATE_A_PROPOSAL.md`、`G2_SB8_GATE_B_SUBMISSION.md`。依 PO 指示**逐一對照 `FEATURE_REGISTRY.md` §5A 檢視每一個 `fillna` 是否正當，不照抄契約**——結果**契約指定的四個 NULL 策略中有兩個不正當**，且其一**證偽了 §5A.1 對成因的窮盡性宣稱**：`volume_ratio_5d` 的 `MA5_Vol == 0` 既非暖機（W）亦非來源失敗（F），而是**第三種：資料齊備、視窗足夠，但公式在數學上未定義**（成因 `U`）。⚠ **DEC-030 的狀態欄在 `DECISIONS.md` 停在 `Proposed` 達五天**（`TRACEABILITY.md` 同日已記 `APPROVED`），2026-09-05 才補正——**成因是查詢用的樣式 `` `PROPOSED` `` 在檔案裡不存在**，已由 contract-check **B13** 機械化 |
| └ **UG-G2-SB9** 候選池價格資料取得 | **CLOSED**（2026-09-02 PO 核准結案，closure commit `088ff27`；DEC-031 新增本 SB 並修正 SB6／SB7 循環依賴、**DEC-032** 重試紀律） | 實作 commit `99f8566`（TWSE 階段一）、`e163d36`（TPEx 三年回補 740/740）；證據見 `doc/upgrade/gates/closed/G2_SB9_GATE_A_PROPOSAL.md`、`G2_SB9_GATE_B_SUBMISSION.md` 與十份段報告 `evidence/G2_SB9_tpex_backfill_seg*.json`。**編號 9 但執行順序在 SB6 之前**。⚠ **2026-09-03 執行 +1 年延伸**（PO 授權）：面板扣掉 SB6 的 60 日暖機後只有 **2.79 年**，不足 `PURGED_WALK_FORWARD_SPEC.md` §3.3 的 ≥3 年——**而 SB9 交付的價格資料本身的 3.04 年仍然為真**；**兩個數字量的是不同的東西**。**明文禁止縮短 60 日暖機來湊年數**（PO） |
| └ **UG-G2-SB6** Point-in-Time Stock Universe | **CLOSED**（2026-09-03 PO 核准結案，closure commit `8f1381d`；**DEC-033** 窗口邊界裁定） | 實作 commit `9ca3429`（migration 006 + `src/transform/universe_builder.py` + 13 項**零 DB 依賴**測試）、`e640979`（候選池匯入真實庫）；證據見 `doc/upgrade/gates/closed/G2_SB6_GATE_A_PROPOSAL.md`、`G2_SB6_GATE_B_SUBMISSION.md`。真實庫產出 **46 期 PIT 快照**、每期 150 檔、**85,641 列**，**逐月對號 46/46 逐一相等**，退出股兩類違規皆 0。⚠ **實作期發現已核准提案內部對 60 日窗邊界自相矛盾**，裁定以 DEC-017 為準，**46 列基準作廢重算、實測 8 列改變**——**差異小到不會被列數總計發現**。該裁定的 known-FAIL 已做成**離線可重現**，複查方據此獨立重跑確認 8/46 與 0/46。⚠ **本次結案漏了 §0.4 測試基線**（由複查方於下一輪指出）|
| └ **UG-G2-SB7** Batch ETL 與失敗容忍 | **CLOSED**（2026-09-05 PO 核准結案，closure commit `4c6e3f6`；**DEC-032** 生產落實、**DEC-034** 舊批排除） | 實作 commit `0047d98`（DEC-032 三處生產違反）、`4de6fae`（看板頁面模式）、`2de3ad3`（每日任務接線）、`bccffa9`（E3 修正）、`e67d3d6`（`post_time` 取自網址時間戳）、`87256e4`（時區政策）；證據見 `doc/upgrade/gates/closed/G2_SB7_GATE_A_PROPOSAL.md`、`G2_SB7_ROUND_B_DESIGN.md`、`G2_SB7_ITEM5_PROPOSAL.md`、`G2_SB7_GATE_B_SUBMISSION.md` 與四份 `evidence/G2_SB7_*.json`。每日取價由 **150 個請求變成 2 個**；社群取數與關鍵字數脫鉤（上限 25 頁）。**2026-09-05 單次受控執行**（暫緩僅解除一次，**不得用一次成功的執行去換一個常態授權**）：三態總和 = 項目數（2／4／26）、TWSE 1,085／TPEx 887 皆落在**取數前寫死**的區間。⚠ **收尾期間查出兩個 Look-ahead 家族的缺陷**：(i) `post_time` 331 篇中 76 篇錯（年份差 +1~+7），(ii) **`comments_scraped_at` 為 UTC 而 DEC-024 的 cutoff 是台北 15:30，偏差方向寬鬆**——已建立時區政策 `src/common/clock.py` + AST 掃描測試。⚠ **E3 假通過**：看板回溯被置底公告截斷、**回報 `OK` 而非 `SOURCE_DEGRADED`**，已修 |
| **Gate 3 準備工作**（`PRE-G3-*`，進入 Gate 3 正式啟動前的量測與資料整備） | **已完成，Gate 3 已啟動（見下方列）** | `PRE-G3-01`～`PRE-G3-04` 皆已 CLOSED；欠帳三件中兩件已收尾（stub 稽核，§0.5 #19；跨文件狀態一致性稽核，見下方列）；`gates/` 根層現為空（第四次清空，前三次分別為 Gate 2 關閉時、stub 稽核結案時、`PRE-G3-04` 結案時）；餘一（wrap-rule 精修）已排定為 **Gate 3 期間平行小案，不阻擋啟動**（PO 2026-09-08 裁定，2026-09-09 隨 Gate 3 啟動核准書面再確認） |
| **UG-Gate-3** | **已核准關閉（2026-09-16，PO 核准，`UG-G3-SB7` 結案即關閉；啟動時為「已核准啟動，逐 SB 授權（2026-09-09，PO 九項裁決）」，下欄原文保留不改）** | 啟動申請書 `94c2d01`；PO 完整九項裁決全文附於 `doc/upgrade/gates/GATE3_STARTUP_APPLICATION.md` §10（申請書依 `CLAUDE.md` §16.3 規則 5 留根層，Gate 3 關閉時移入 `closed/`）。裁決摘要：①Gate 3 啟動核准，逐 SB 授權（同 Gate 1／2 模式）；②rolling vs expanding——暫維持規格預設 rolling，兩模式對照列為 `UG-G3-SB3` 內建子實驗；③`embargo_days=0`——核准，**附失效條件**（現行 1 天標籤視野下成立；標籤視野一變即自動失效須重議，見下方 SB1 列）；④`min_train_size` 覆寫——不裁，條件未觸發（非「已解決」）；⑤RISK-020——**緩裁**，舊裁決依據的暖機佔比數字取自 137 列舊面板，3,713 列新面板下利害關係已變，需先唯讀重量測；⑥宇宙接線三層分離設計核准，路由補齊與落差查核併入 `UG-G3-SB2` Gate A；⑦D3 預測力對照實驗設計核准，執行時機併入 `UG-G3-SB3`；⑧RISK-005 唯讀計時核准，排在 `UG-G3-SB2` 收尾；⑨wrap-rule 平行小案書面確認。§0.5 #16 依此裁決更新狀態 |
| └ **UG-G3-SB1** Triple-Barrier Labeling | **CLOSED**（2026-09-09，PO 核准結案） | 完整 commit 序列見 `doc/upgrade/gates/closed/UG_G3_SB1_GATE_B_SUBMISSION.md`：`9d3b201`（Gate A 核准）→ `b24fc01`（紅）→ `d2e3f27`（綠，14/14）→ `874b3bf`（審查方發現 NaN 誤判修復，16/16）→ 文件同步／規格補齊／DoD 第 2/3 項 → `581950a`／`32250d2`（審查方發現字面密碼洩漏 x2，修正）→ `26f7bc0`→`453ac13`→`efd0205`（寫入腳本三輪硬化，累計 5 項 known-FAIL）→ `2d3e28e`（DoD 第 6 項：真實庫 3,713 列寫入，RISK-013 三項協議）→ `f5e24a5`（Gate B 送審）→ `6a3b4f3`（重送，補 RISK-025／DEC-035 evidence-sync）→ 結案 commit。`src/ml/triple_barrier.py` 16 項測試全綠；真實庫 `postgres`@`localhost:5432` 的 `daily_ml_features` 已完成 3,713 列 `target_triple_barrier`／`label_reason` 寫入，24 格逐檔統計與證據檔完全相符，備份與還原驗證皆完成（`stock_prediction_system2_PRE_g3_sb1_tb_labels_20260909_151621.dump`）。**DEC-035**（修訂 DEC-018 標籤條件邊界：剩餘天數優先於先觸即定；NaN 價格處理）`APPROVED`。**RISK-024**（`stock_prices` 允許 NaN 價格列）、**RISK-025**（Timeout 類三檔 <5%，觸發 DEC-018 揭露條款，排入 `UG-G3-SB3` D3 必答項）已登記。**未驗證清單**（有名字有去處，見結案文件 §7）：rolling vs expanding 對照、embargo>0 自相關滲漏疑慮（皆歸 `UG-G3-SB3`）；尾端 4 列每日重算歸屬未定（`UG-G3-SB2` Gate A 必答）；`pd.read_sql` UserWarning 已知限制 |
| └ **UG-G3-SB2** Panel Dataset 構建 | **CLOSED**（2026-09-10，PO 核准結案） | 完整 commit 序列見 `doc/upgrade/gates/closed/UG_G3_SB2_GATE_B_SUBMISSION.md`：三項子工作——PIT 面板讀取器（`src/ml/panel_dataset.py`）、`entity_mapping` 路由補齊（真實庫寫入 457 筆）、每日尾端重算掛點（已接線，未啟用）。`2c34059`（Gate A 第一版，PO 退回：PIT 量體維度算錯）→ `8c3e10d`（重送，訂正 458/46 數字 + DEC-036 拆分 `UG-G3-SB2a`，核准）→ 紅色測試三輪（`3104894`／`a39e966`／`2642b39`，共 13 項）→ `c48917c`（綠，審查方發現 PIT 過濾＋dtype 兩缺陷）→ `0e9b7c8`（修正）→ `dcac0fe`（routing 腳本，紅綠合併，流程偏差已接受不改寫）→ `d61549c`／`a2d7641`（routing 修正兩缺陷：0 筆誤判、缺總數檢查）→ `34bcc5f`（真實庫寫入 457 筆，惰性驗證發現追蹤宇宙 4→8 檔，PO 裁決接受不回滾）→ `655f740`／`7dd382c`（審查方發現證據檔字面密碼洩漏 x2，修正）→ `29aacc6`／`ae785bc`（每日掛點接線）→ 結案 commit。SB2 專屬測試 52/52、全套 559/559、contract-check 13/13。**DEC-036**（`UG-G3-SB2a` 拆分決策）`APPROVED`。**RISK-022（四）**（追蹤宇宙擴張的基準曝險）、**RISK-026**（`market_articles` 未來日期，順帶發現）已登記。§0.5 **#20 每日 ETL 執行閘門維持開啟**——本次結案不解除，綁 `UG-G3-SB2a` Gate B 通過。**未驗證清單**（有名字有去處，見結案文件 §7）：面板僅 3 檔台股有真實資料（458 檔回補歸 `UG-G3-SB2a`）；161 篇孤兒文章歸屬與 4 檔新股暖機期（閘門解除後）；`rolling` vs `expanding`、embargo>0 滲漏（歸 `UG-G3-SB3`） |
| └ **UG-G3-SB2a** 458 檔 Universe 資料回補 | **CLOSED**（2026-09-11，PO 核准結案） | 完整 15 commit 序列、DoD 逐項對號、揭露清單 11 項、十項觀察清單見 `doc/upgrade/gates/closed/UG_G3_SB2a_GATE_B_SUBMISSION.md`。**三段真實庫寫入全部完成**：段 1（`stock_prices` 458 檔皆補齊，`5318f16`）、段 2（`daily_ml_features` 458＋NVDA 檔特徵回補，449,263 列，`e14212b`）、段 3（Triple-Barrier 458＋NVDA 檔標籤全部重算，標籤計數 410,443／38,820，`0f6a428`）；另有候選池 8 天全市場缺口回補與段 1 重跑（`2ee8141`）。**五次真實庫寫入皆完整執行 RISK-013 三項協議**（binding confirmation、PRE/POST 備份、拋棄式容器還原驗證、獨立重查），無一次省略。過程中發現並登記 **RISK-027**（`feature_aggregator.py` 交易日曆跨市場聯集導致文章流失，獨立小案待修，段 2/3 現況帶著此已知限制）、**RISK-028**（TPEX 端間歇性 SSL 憑證驗證失敗，另案診斷，禁止關閉憑證驗證繞過）。**RISK-025 揭露**（Triple-Barrier 類別分布）：337/459 檔 Timeout <5%、`ambiguous_dual_barrier` 8.1%（偏高）、`-1:+1`≈1.4:1（偏空），歸 `UG-G3-SB3` D3 必答項。§0.5 **#20 每日 ETL 執行閘門已隨本 Gate B 核准解除**——解除 ≠ 執行，第一次執行需另一輪 binding confirmation，十項觀察清單（原提案六項＋執行經驗增補四項）為必答項。**未驗證清單**（有名字有去處，見結案文件 §6）：`rolling` vs `expanding`、embargo>0 滲漏、RISK-025 對模型預測力的實際影響（皆歸 `UG-G3-SB3`）；RISK-027 修復後段 2／3 是否需重跑（待獨立小案）；`UG-G2-SB9`／`UG-G2-SB7` 銜接缺口成因（`INFERENCE`，未對 SB9 證據確認）。**待另案裁決**：`TwseScraper` 模組去留（PO）、RISK-027 獨立小案（bug-fix-protocol，建議排在 `UG-G3-SB3` Gate A 前）。 |
| └ **`PRE-G3-01`** 逐則留言時間戳全鏈 + B0 探測 + B1 試點 | **CLOSED**（2026-09-08 PO 核准結案） | 完整 commit 序列與裁決索引見 `doc/upgrade/gates/closed/PRE_G3_01_GATE_B_SUBMISSION.md`。逐則留言時間戳（migration 008）+ `validate_comment_bounds` 上下界檢查；B0 歷史區間探測（8 請求，判準觸網前寫死）；B1 試點（PO 裁決 S1=全部，命中率 9.81%、B0 估計 0.69% 相差 14 倍——時代混淆）；發現並修正 `article_id=1495` 的時區地雷（`87256e4` 政策切換前寫入的 1 列）；40.8%→**59.2%** 零貢獻比例自我更正（全欄比對）。**未驗證清單**：wrap-rule 推論規則精修（未做，13 篇拒寫中 6 篇因此觸發）、單調性 `ASSUMPTION`（未升級）——皆有名字有去處，見結案文件 §4 |
| └ **`PRE-G3-02`** 覆蓋率門檻提案（D1~D5）+ 逐標的覆蓋率量測 + `RISK-015` 收案 | **CLOSED**（2026-09-08 PO 核准結案） | 完整 commit 序列、D1~D5 裁決索引見 `doc/upgrade/gates/closed/PRE_G3_02_GATE_B_SUBMISSION.md`。D3 錨定預測力對照（非先驗百分比）、D4 保留全部標的+模型原生處理 NaN、D5 空日 `sentiment_mean` NULL 化（**落地執行為 `PRE-G3-04`，另案**）；逐標的覆蓋率首次有真實數字（2330 86.30%、NVDA 57.23%、2382 22.60%、6488 8.33%，直接呼叫生產函式量測，未寫回資料庫）；`RISK-015` `HYPOTHESIS`→`OBSERVED`，**風險不關閉、轉為 Gate 3 實驗問題**（非訂門檻收案）。**未驗證清單**：D3 預測力對照未跑（需 `PRE-G3-04` 全量重算完成後才能進行）、`min_train_size` 三件事未解（併入 §0.5 #16）、NVDA 754<756 邊界情況——皆有名字有去處，見結案文件 §6 |
| └ **`PRE-G3-03`** 全量回補（DP1~DP4）+ 段 A 七段 + 評分 + 兩階段匯入 | **CLOSED**（2026-09-08 PO 核准結案） | 完整 commit 序列、裁決索引見 `doc/upgrade/gates/closed/PRE_G3_03_GATE_B_SUBMISSION.md`。三個瓶頸分開報價（台股價格 0 請求／NVDA 1 請求／PTT 情緒主體）；migration 009 `stock_prices.source`；`stock_prices` 137→**3,713** 列；段 A 七段（命中率序列 9.81→7.15→8.90→9.05→9.05→7.10→6.15→10.2%，累計拒寫 13 篇三種型態全生產觸發）；評分 1,250 篇零遺漏；兩階段匯入 `market_articles` 332→**1,330** 篇、`article_comments` 38→**136,185** 則。**兩次範圍變更皆以裁決形式收錄**：段數 8→7（段 1 實測密度回推）、段 7 傳輸層有界重試（`f21dfbe`，觸網前 commit，非「調整判準使其通過」）。**未驗證清單**：段 5 跨文章相同推文序列成因待查（已界定範圍，非系統性重複，未阻斷續跑）、wrap-rule 推論規則精修未做（與 `PRE-G3-01` 共用同一項）、單調性 `ASSUMPTION` 未升級（與 `PRE-G3-01` 共用）、`RISK-022` 面向（二）未動、`daily_ml_features` 未重算——皆有名字有去處，見結案文件 §6 |
| └ **`PRE-G3-04`（D5）** U 分支落地（`sentiment_mean` 空日 NULL 化 + `cumcount` 真暖機期判定）+ `daily_ml_features` 全量重算 | **CLOSED**（2026-09-08 PO 核准結案） | 完整 commit 序列、裁決索引見 `doc/upgrade/gates/closed/PRE_G3_04_GATE_B_SUBMISSION.md`：`fd0a889`（Gate A 提案）→ `0c53764`（紅）→ `6ecdb50`（綠）→ `246b430`（§0.5 #18 補登記）→ `87bd40e`（重算預期）→ `4aa86cc`（重算結果）→ `2949db1`（Gate B 送審）。三異動點：移除 `sentiment_mean` 早期 `fillna(0.5)`（成因 U）；`sentiment_3d_ma`／`5d_ma` 無需改動（nanmean 語意已實測驗證）；`sentiment_lag_1`／`lag_2` 加 `groupby.cumcount()` 判定真暖機期 vs U 傳播。`FEATURE_REGISTRY.md` §5A.2 補 U 分支、§5A.3 五欄加註子條件。**全量重算 `daily_ml_features` 137→3,713 列**，R1~R6 全數相符，其中 **R2 零成本交叉核對逐檔全中**（`sentiment_mean IS NOT NULL` = 2330=126/2382=33/6488=12/NVDA=91，與 `PRE-G3-02` 量測的覆蓋天數逐檔完全相符，兩條獨立路徑對同一批資料算出一致答案）；**R5 誠實快照**：`sentiment_mean` NULL 佔比 2330 87.2%、2382 96.7%、6488 98.8%、NVDA 87.9%（不美化）。RISK-013 三項完整執行（拋棄式容器 `g3_04_recalc_restore_check` 實測還原，12 表 + 指紋皆符，已拆除）；`b1_pilot_tmpdb`（`PRE-G3-01` 匯入回滾裁決保留）於本次驗收通過後依授權拆除（`docker rm -f -v`，容器與匿名卷皆確認移除）。**未驗證清單**：`model_trainer.py:161-169` 會靜默抹平本次建立的 U 語意（已登記 `PROJECT_STATUS.md` §0.5 #18，去處 `UG-G3-SB2`）、R4 抽樣限制（4 檔各 1 筆，2 筆因回補擴大覆蓋而轉 `SUCCESS`，已於結案文件揭露方法限制）、D3 預測力對照未跑（去處 Gate 3 第一個實驗）——皆有名字有去處，見結案文件 §7 |
| └ **跨文件狀態一致性稽核（第 6 案）** 反查法五份文件交叉宣稱 | **CLOSED**（2026-09-08 PO 核准結案） | 完整 commit 序列、裁決索引見 `doc/upgrade/gates/closed/CROSS_DOC_CONSISTENCY_GATE_B_SUBMISSION.md`：`7b789b3`（Gate A 提案）→ `e8a018a`（確認落地）→ `7bb9643`（腳本 + 初次結果）→ `8100556`（`TEAM_PLAYBOOK` A11）→ `633a336`（§0.5 #9 展開）→ `989206b`（R2 v2 豁免表）→ `64e9ae2`（`gate-submit` 更新）→ `bdf6036`（B13 根治 + 6 則 ADR 狀態修正）→ `4ababa1`（完整集合重跑）。新腳本 `scripts/verify/cross_doc_consistency_check.py`（R1~R4 可重跑，R5 人工核對鎖定四欄格式）。**初次執行 R2/R3 FAIL，皆為真實案例**：R2 九個孤兒（8 個索引式引用改豁免表附理由、1 個縮寫式展開全名）；R3 五個不合規查證後發現既有 `gate0_contract_check.py` B13 對這些 ADR **從未真正檢查過**（只計數 `- 狀態：` 開頭的行，格式不符者從未進入 `b13_seen`）——**§9A.1「只看已知沒問題的地方」教訓的第三個實例，這次在既有機制本身裡發現**。B13 修法（改逐則遍歷區塊、每則須恰一行可辨識狀態）與 6 則 ADR 資料修正（4+1 則舊格式正規化、DEC-009 由 PO 裁決補 `APPROVED`）同一 commit 入庫，規避自鎖（紅色證據於拋棄式 worktree 取得，新舊邏輯並排對照）。**執行中發現超出 PO 原列表的一項**（DEC-007 同類缺陷，比照處置，已揭露非擅自擴權）。完整集合重跑 R1~R4 4/4 PASS、B13 掃描 27 則不合規 0。順帶：背景執行失敗（零工具呼叫回報「完成」）登記進 `TEAM_PLAYBOOK.md` §5.1 A11。**未驗證清單**：R5 為常設方法非一次性動作，日後新增觸發風險依同格式核對；`cross_doc_consistency_check.py` 執行時機綁事件但未機械強制（同產出 7／8 既有揭露）——皆有名字有去處，見結案文件 §5 |
| └ **UG-G3-SB3** Specialist Models（RF／LightGBM／XGBoost）訓練與 D3 對照實驗 | **CLOSED**（2026-09-13 PO 核准結案） | 完整 26 個 commit 序列（編號 0～25）、五項必答最終答案、DoD 逐項對號、揭露清單見 `doc/upgrade/gates/closed/UG_G3_SB3_GATE_B_SUBMISSION.md`。三 Specialist（RF／LightGBM／XGBoost）× 兩對照臂（B 排除 LR）× 兩模式（rolling／expanding）× 兩 target，在凍結面板（`e4cae8a`）上完成 Purged Walk-Forward 訓練評估，四份證據 JSON 全量落地。**五項必答結論**：RISK-025——Timeout recall 0.163～0.301（macro F1 高於基線的部分主要來自這裡）、獲利出場 recall 0.020～0.080（F1 幾近零，貢獻可忽略），模型偏向多數類，調寬 barrier 或改 Dynamic 留待另案；rolling vs expanding——方向在兩個 target 上相反（`target_up_down` rolling 略高、`target_triple_barrier` expanding 略高），不下單一結論；`embargo_days=0`——28 組洩漏診斷 `flagged` 全數 `False`，維持有效；`sentiment_mean` 覆蓋率——新增 `signal_rows_subset`（列子集，`article_count>0` 或 `sentiment_5d_ma` 非 NULL，1,409/139,585＝1.01%）量化「B 臂真的多出資訊的列」有多稀少，進入測試集後僅 8/43 Fold 有非零列（`n_total` 1,298／1,034），**裁決：在此覆蓋率下無法區分兩臂，D3 對覆蓋率的回答是「不夠」，後續案為資料源擴充（RISK-015）**；面板凍結——POST 備份基準＋四份 JSON sha256 皆已記錄。**新 ADR** `DEC-038`（訊號列子集與多數類基線 tie-break 規則）**已 `APPROVED`**（PO 2026-09-13 核准）。`doc/upgrade/gates/UG_G3_SB3_GATE_A_PROPOSAL.md`／`UG_G3_SB3_GATE_B_SUBMISSION.md` 已 `git mv` 至 `closed/`（`gates/` 根層現只剩 `GATE3_STARTUP_APPLICATION.md`）。**待另案**：RISK-023（留言三欄逐則時間戳重算，本 Gate B 核准後、`UG-G3-SB4` 之前）、容器 `git` 環境設定常設化（`.devcontainer` 小案，待 PO 授權）。 |
| └ **UG-G3-SB4** OOF Stacking Meta-Learner | **CLOSED**（2026-09-15 PO 核准結案） | Gate A 提案三版（v1 退回→v2 訂正三層結構→v3 改判只用 Arm A）核准後，紅測 `e46a8a7`（35）→amended-red `69f6e35`（+4=39）→自我反查（+2=41）；實作 `dcf48c5` GREEN；審查方複核追加兩輪紅測：P1-P5 契約缺口 `a1abcf4`／`433cae0`、P6/P7 定義域核對 `da73153`／`a8fe533`；OOF/報告腳本 `9f86b88`（單折/28折探測）；審查方對真實面板重算發現三個正確性問題（守衛常數誤用原始列數、迴圈繞過 `iter_oof_folds()`、`argmax` 遇 NaN）→紅測 `e9ac8da`→修正 `c328805`（含 `return_retained_index` 契約擴張 P8）。**全量執行**（folds 0-32，兩個 target）與證據 commit `3ba80b6`：六項 OOF 守衛／四項報告守衛全數 PASS；`target_up_down` row_counts `{total:98917, meta_train:80818, meta_eval:17949, purged:150}`，`target_triple_barrier` `{total:91124, meta_train:73714, meta_eval:16730, purged:680}`（purge 數已訂正自原始列數 750）。Meta-Eval 段四者並列：up_down 的 `Meta(A)`（0.381/0.381）系統性劣於 Best Single（lgbm，0.465）；TB 的 `Meta(A)-LR`（0.318）略優於 Best Single（lr，0.304）。**新 ADR** `DEC-040`（Gate 3 Holdout 邊界落地）**已 `APPROVED`**（PO 2026-09-15 核准）。§0.5 #22／#23 新登記：Meta-Learner 幾乎未從 OOF 學到訊號（三項候選成因去處分派至 `UG-G3-SB5`／`SB6`）、`evaluator.py` 未依 Gate A 規劃擴充（登記後續小案，`UG-G3-SB7` 一併決定）。`RISK-009` 已更新殘餘風險量化文字（欠擬合觀察點）。`doc/upgrade/gates/UG_G3_SB4_GATE_A_PROPOSAL.md`／`UG_G3_SB4_GATE_B_SUBMISSION.md` 已 `git mv` 至 `closed/`（`gates/` 根層現只剩 `GATE3_STARTUP_APPLICATION.md`）。**下一步**：`UG-G3-SB5`（Probability Calibration）Gate A 提案，必答 §0.5 #22 的 (a)/(c) 兩項（`class_weight`、Specialist 共線性）。 |
| └ **UG-G3-SB5** Probability Calibration | **CLOSED**（2026-09-15 PO 核准結案） | Gate A（`5624e74`）核准後五輪訂正／紅測／實作：`cv="prefit"` 於 sklearn 1.9.0 移除，改手動 Isotonic／Platt（`22f685e` RED 30 項→`deb95cc` GREEN，GREEN 階段自行發現並訂正兩處紅測錯誤：多類別 Brier 代數關係、`test_tb_sigmoid_allowed` 參數錯誤）；Platt 改未正則化擬合（`89f9f33`，`PLATT_C=1e6`，紅→綠）；段級報告腳本 GREEN，實測發現 `assert_auc_preserved()` 的「AUC 必相等」假設對負斜率（Calib-fit 近零訊號時斜率正負號本身是雜訊）不成立，改鏡射容忍檢查，同時發現 TB 的 `evaluate_calibration_quality()` 從未被實際執行過的設計缺口，改為逐類別 OvR 各自評估；`calibration_not_meaningful` 旗標複核訂正為與方法無關（`7c65b4f` commit A → 乾淨樹重跑 → `b286ec5` commit B，比照 `UG-G3-SB4` `c328805`→`3ba80b6` 先例）。**主要發現，登記 `RISK-030`**：`target_up_down` 在折 27-32 全線（四個 Specialist 與 Meta(A)）無可偵測排序訊號（AUC 皆 ≈0.50-0.52），`target_triple_barrier` 的訊號集中於 Timeout 類（OvR AUC 0.83-0.91），`±1` 方向類同樣近零。**Gate B 核准（PO 2026-09-15），四項裁決落地**：(a) `UG-G3-SB6` 對 `target_up_down` 停做；(b) `UG-G3-SB6` 改以 TB／Timeout 類校準後機率為 gating 對象（產品形態「何時不交易」）；(c) 特徵層面方向預測改進案登記候補（見 §0.5 #24），排 `UG-G3-SB7` 之後，與 `RISK-015` 連動；(d) Master Plan §11.1 條件勝率 >60% 目標數字保留、加狀態註記。**新 ADR** `DEC-041`（Gate 3 方向轉軸：停做 up_down、改以 TB／Timeout 為 gating 對象）狀態 `PROPOSED`（依慣例於 `UG-G3-SB6` Gate B 通過時轉 `APPROVED`）。`REMAINING_RISKS.md` `RISK-030` 應對措施欄回填、`RISK-009` 追加交叉引用；`SYSTEM_UPGRADE_MASTER_PLAN.md` §9 SB5 Affected Components 訂正（`src/ml/predictor.py` 未觸及，實際為 `src/ml/calibration.py`＋`scripts/verify/ug_g3_sb5_calibration_report.py`）、§11.1 目標註記、SB6 Brief 加範圍調整說明。`doc/upgrade/gates/UG_G3_SB5_GATE_A_PROPOSAL.md`／`UG_G3_SB5_GATE_B_SUBMISSION.md` 已 `git mv` 至 `closed/`。**下一步**：`UG-G3-SB6`（Selective Inference & Regime Gating）Gate A 提案，範圍依 `DEC-041` 定案（TB／Timeout gating，非 up_down 方向預測）。 |
| └ **UG-G3-SB6** Timeout Gating | **CLOSED**（2026-09-16 PO 核准結案） | Gate A 提案三版（v1 審查方唯讀探測推翻量化判準→四項裁決＋六處訂正→v2 兩處再訂正：`θ` 差異真因為 OvR 正規化、可行區間選點規則於 Gate A 即釘住）核准 `83749de`。紅測 `900c616`（38 項，`src/ml/gating.py`）→實作 GREEN `09bcba9`（審查方複核 5 個突變體）。報告腳本紅測 `23e2039`（60 項，含 PM 訂正審查方原始診斷：`auc_calib_fit_raw` 鍵確實存在，為巢狀字典非單一浮點）→ GREEN `81def57`（`run_report()` 完整管線；PM 自我揭露 `_build_dual_curves()` 空殼未接主管線）→審查方複核判定揭露不足（`CLAUDE.md` §9A.1 第二例）→訂正紅測 `3eacb6f`／GREEN `cd5f69a`（簽章改為 LR／Ridge 各自 raw_eval）。**單折乾跑第一步 PM 自抓** `KeyError: 'oof_sha256'`（真實鍵名為 `oof_parquet_sha256`）→紅測 `217eb43`／GREEN `8ef8378`。乾跑通過驗收（除 `script_untracked_paths` 環境差異與網格量化誤差兩項揭露外全部相符）；`.gitignore` commit `627cca7`（host 使用者層級 `~/.config/git/ignore` 與容器環境差異，非工作樹真髒）；**全量執行**證據 `20af8c8`（`UG_G3_SB6_gating_report.json`，sha256 `aff85bd5…`）與乾跑 JSON 程式化逐鍵 diff，差異集合為空（排除預期鍵）。**主要結果**：`θ*=0.06907452098250194` 於 Calib-eval 達成裁決 (a) 三項量化目標（覆蓋率 80.00%、精準度提升 4.15×、召回 83.03%），落在覆蓋率地板邊界（相鄰網格點驗證非誤選）；`regime_diagnostic` 顯示被 gate 的列**全部**落在低波動三分位組（低／中／高波動組 coverage 0.4001／1.0／1.0），為 `UG-G3-SB5` Gate B §4 `INFERENCE`（Timeout 訊號集中於波動率水準）的第一個行為層證據，登記 `UG-G3-SB7` 必列波動率單變數基線比較（§0.5 新增）。兩處 commit 敘事訂正：延續 `fe30ef2`（§10／§11.1 筆誤兩事實並列）＋ 本輪 `20af8c8` commit body 低波動組 coverage 誤植 `0.4007`（正確 `0.4001`，JSON 本身無誤）。`DEC-041` **已 `APPROVED`**（2026-09-16）；`RISK-030` 應對措施欄回填 Gate B 結果；`TRACEABILITY.md` 條目 38 同步；Master Plan §9 SB6 Brief 更新（Affected Components 訂正為 `src/ml/gating.py`／`scripts/verify/ug_g3_sb6_gating_report.py`／`.gitignore`）、§11.1 追加達成句。`doc/upgrade/gates/UG_G3_SB6_GATE_A_PROPOSAL.md` 已 `git mv` 至 `closed/`；`UG_G3_SB6_GATE_B_SUBMISSION.md` 此前未 commit 過，結案 commit 內以新檔直接寫入 `closed/`（比照 `UG-G3-SB5` 先例）。**下一步**：`UG-G3-SB7`（Performance Benchmark）Gate A 提案。 |
| └ **UG-G3-SB7** Performance Benchmark（Holdout 最終驗證） | **CLOSED**（2026-09-16 PO 核准結案，Gate 3 一併關閉） | Gate A 提案 v2（六項裁決＋七處訂正，最重要一處：`iter_holdout_folds()` v1 用 `test_end_date>=boundary` 會把跨界折整個納入 Holdout，訂正為 `test_start_date>=boundary`）核准 `242b6bc`。紅測清單與 RED 本輪合併送審（趕交期）`c502e3b`（35 項）→ GREEN `ac73432`（乾跑階段 PM 自抓並修正 `target_up_down` 觀察用 AUC 誤拿 TB class+1 欄頂替的設計缺口）。**PO 複核 GREEN 的乾跑 JSON 發現**：`retained_direction_shift` 誤用 `target_up_down` 值域（恆為 0）→ 紅測 `e38a845` → GREEN `3a32314`（改複用既有 `compute_gating_metrics()`，新增 Specialist OOF 重生比對與 `frozen_artifacts` 十項寫入 JSON）。**PM 正式消費第一次嘗試自己撞到**：`_compute_up_down_observational_auc_holdout()` 無條件截斷面板到 `HOLDOUT_START_DATE` 之前，把正式消費要處理的折 33-42 資料自己濾光導致拋錯（無資料受影響，拋錯在任何寫入前）→ 紅測 `bb12966` → GREEN `0156d59`。**正式消費**（唯一一次）evidence `28bc1cd`：`folds_processed=[33..42]`、`holdout_row_count=24162`、`specialist_oof_regeneration_check.n_rows_compared=0`（與 SB4 OOF 折 0-32 無重疊，預期）。**Holdout 結果**：三項判準成立（覆蓋率 92.52%／精準度提升 10.73×／召回 80.28%，Timeout 基期由 Calib-eval 4.71% 降至 Holdout 1.76%，`INFERENCE`：lift 上升主要來自基期下降，需額外驗證）；波動率單變數基線與 Timeout gating 表現接近，未下結論，登記候補案（§0.5 新增）；`target_up_down` 觀察用 AUC（0.50～0.52）與樣本內三段一致，樣本外封閉，`RISK-030` 無排序訊號結論定案。**程序偏離揭露**：正式消費第二次修正（`bb12966`／`0156d59`）不在 PO 原授權條件內，PM 拋錯後自行修正再消費，非「拋錯後停下回報」的正確流程；複核確認 TB 主管線結果從未在第一次嘗試中被輸出或看到，無 `DEC-040` 意義污染，消費有效——「只讀一次」機制的已知限制（機械上只擋二次 `--write`，不擋崩潰後直接重跑）與此偏離模式如實記錄，不作先例。**已知缺口**：Gate A v2 §3.5(b) 要求的 Timeout 三分類 fixed-argmax macro F1 未實作（PM 寫 Gate B 時自查發現），PO 裁決不補（二次讀 Holdout 代價與揭露用指標的價值不成比例）；`RISK-020` 平行小案（`ma5`／`ma20_bias_ratio` 改 `NULL`）查無執行記錄，PO 對凍結面板重量測確認暖機列不在面板內、`volatility_20d`（Timeout gating 唯一依賴）零填值，對 SB3～SB7 結果無可量測影響，序列中段零值成因另立小案；`wrap-rule` 精修同樣查無執行記錄。`DEC-040`／`DEC-041` 更新、`RISK-030`／`RISK-020`／`RISK-005` 追加、Master Plan §9／§11.1、`PROJECT_STATUS.md` 本列同步。`GATE3_STARTUP_APPLICATION.md`／`UG_G3_SB7_GATE_A_PROPOSAL.md`／`UG_G3_SB7_GATE_B_SUBMISSION.md` 已 `git mv` 至 `closed/`。**下一步**：文件對齊輪（PRD／SDD 未反映 Gate 3、RISK-020 序列中段零值成因、wrap-rule 現況查證），其後視 PO 排程決定是否啟動 `UG-Gate-4`。 |
| **UG-Gate-3** | **CLOSED（2026-09-16，PO 核准）** | 七個 SB（含 `SB2a`）全數 CLOSED，見上方各列；`GATE3_STARTUP_APPLICATION.md` 依 `CLAUDE.md` §16.3 規則 5 移入 `closed/`。 |
| **首次每日 ETL 真實執行**（缺口自動追補＋§0.5 #30 n_lag 修法，Gate 3 關閉後、Gate 4 啟動前的獨立案） | **✅ 已完成（2026-09-17）** | 段 A（§0.5 #30 修法）`eccab3a`／`7a66153`／`048e975`；段 B（拋棄式庫演練）發現 md5 不符，唯讀診斷後判定為 `DECISIONS.md` DEC-039 題材情緒溢出全歷史重算的既有設計行為（非 bug），PO 訂正驗收條件；段 C（真實執行）20:04 開始，`exit code 0`，無例外無 429，四條訂正後驗收全數 PASS。完整證據見 `doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success.md`（另兩份：`_rehearsal_20260916.md`、`_real_run_20260917_aborted.md` 為過程文件）。§0.5 #20 本閘門項目結案，見該列。 |
| **第二次真實每日 ETL**（§0.5 #32 成因 F 接線首次真實生效——PTT 覆蓋缺口／NLP 未完成 → `SOURCE_FAILED`） | **✅ 已完成（2026-09-18）** | Gate A 提案核准 → 紅測 `431c2be`（11 條）→ 實作 `ee0b384`（GREEN，第一次執行即全數 PASS）→ 審查方複核追加子案例 `9079915` → 段 B 拋棄式庫演練（三方集合逐列相等）→ 段 C 真實執行 14:45 開始，`exit code 0`，無例外無 429，五條驗收全數 PASS（含新增列數 8=8、`SOURCE_FAILED` 翻轉列 47=47 逐列相等）。真實執行期間發現 `RISK-032` 子機制（AI 探索重寫既有映射權重）與 35 篇未來日期文章，皆已登記 §0.5 #33／#34。完整證據見 `doc/upgrade/gates/evidence/FIRST_DAILY_ETL_CAUSE_F_WIRING_real_run_20260918_success.md`（另兩份：`_rehearsal_20260918.md`、`_expectations.json` 為過程文件）。§0.5 #32 本項結案，見該列。 |
| **第三次真實每日 ETL**（§0.5 #31＋#33 Gemini 用量紀律首次真實生效——探索頻率縮減／每日配額分類／既有映射凍結） | **✅ 已完成（2026-09-19）** | Gate A 提案 v3（PO 核准）→ 紅測 `86ad3b1`（12 條，10 條自然 FAIL/ERROR）→ 實作 `9536771`（GREEN，四態回傳修復複核發現的「五個靜默 return」bug）→ 審查方複核 16 項突變 15 中、補測 3b `7861d14` → 段 B 拋棄式庫演練（五場景＋場景 1b 整條 `run_all_daily_tasks()` 真跑）→ 距今天數判準測試未封閉，系統日期推進後真實 FAIL 一次，修復 `63b4419`（`TEAM_PLAYBOOK.md` A16）→ 段 C 真實執行 2026-09-19 00:26 開始（RISK-013：新 PRE 因逾 30 分鐘重做一次），`exit code 0`，無例外，七條驗收全數 PASS（含 `theme_stock_mapping` 66 列執行前後完全相等、探索因 `last_probed=None` 真實撞到 504 逾時並正確分類為 `FETCH_FAILED`，證明四態設計修好的正是這種情況）。真實執行期間發現 NVDA 深夜執行寫入盤中快照、`trend_discover` 暫態判斷清單缺 `504`，已登記 §0.5 #35／#36。完整證據見 `doc/upgrade/gates/evidence/GEMINI_QUOTA_DISCIPLINE_real_run_20260919_success.md`（另三份：`_rehearsal_20260918.md`、`_expectations.json`、`_rehearsal_20260918_scenario1b_log.txt` 為過程文件）。§0.5 #31／#33 本項結案，見該兩列。 |

RISK-001 `Accept`、RISK-010 `Defer`（至 Gate 3）、RISK-012 `Mitigate`、
RISK-013 **根本解已落地**（2026-08-26，`db_target_guard.py`，commit `d2a4d48`）、
RISK-015 **`Defer`（至 Gate 3 啟動前正式檢視）**——見
`doc/upgrade/contracts/REMAINING_RISKS.md`。

### 0.3 明確未授權項目

| 項目 | 狀態 |
|------|------|
| **UG-Gate-1** | **已於 2026-08-26 全數 CLOSED**（五個 Small Batch SB1～SB5 皆已 PO 核准結案，見 §0.2）。不再是「未授權」項目，自本次更新起自本表移除 |
| **UG-Gate-2** | **已於 2026-09-06 核准關閉**（五條准出條件全數滿足，見 `closed/GATE2_CLOSURE_REVIEW.md`）。不再是「未授權」項目，**自本次更新起自本表移除**（同 UG-Gate-1 的處置）。<br><br>**【2026-09-06 更正】以下為 2026-08-31 當時的敘述，其中「SB9 待 Gate B」「→ UG-G2-SB7 →」等進度描述**已過期**——**九個 SB 與 `UG-G2-MIG` 現已全數 CLOSED**（逐列見 §0.2），Gate 關閉審查已送審（`GATE2_CLOSURE_REVIEW.md`）待 PO 裁決。**原文保留不改**：它記錄的是當時的排序與理由，改寫等於竄改治理紀錄（同 §16.2 對 `archive/` 的原則）。⚠ **本格過期六次無人發現的成因見 §0.3A。**<br><br>**已核准啟動（2026-08-26），採逐 SB 授權**——SB1～SB4 已 CLOSED（見 §0.2）；**SB5 可用性驗證 `FAIL` → `DEFERRED WITH EVIDENCE`**（2026-08-29，不阻擋 Gate 2 關閉），**決策點 5（來源能力宣告）已實作完成待 Gate B**（2026-08-30）；**後續順序（PO 2026-08-31 更新）：決策點 5 ✅ → Migration SB ✅ → **UG-G2-SB8**（CORE_16 四個平穩化特徵 + 讀取端缺口反查檢查，2026-08-31 新增，DEC-029）✅ → **UG-G2-SB9 ✅**（候選池價格資料取得，2026-08-31 新增，DEC-031；**2026-09-02 完成待 Gate B**：TWSE 766,506 列／1,099 檔 + TPEx 623,384 列／912 檔 = **1,389,890 列**，兩者皆 740 交易日、2023-08-07 ~ 2026-08-21（**3.04 年**），滿足 `PURGED_WALK_FORWARD_SPEC.md:147` 的 ≥3 年要求。**【2026-09-03 延伸回補】** 上述三年數字**對 SB9 交付的價格資料仍然為真**，但**面板**（扣 SB6 的 60 日暖機後）只有 680 交易日 = **2.79 年，不足 §3.3 的 ≥3 年**。已執行 **+1 年延伸**（PO 授權）：現為 **1,821,870 列**、TWSE 1,003,070／1,104 檔 + TPEx 818,800／919 檔，兩市場各 **983 交易日**、`2022-08-03` ~ `2026-08-21`（**4.05 年**），**面板 923 交易日 = 3.79 年，達標**。**上界已知**：`G2_SB6_historical_range_probe.json` 的 **E2_tpex FAIL** —— TPEx 現行端點不回 2022-08 以前，**再往前需要另一個資料來源**。⚠ **資料在 repo 外備份**（`..._twse_tpex_4y_20260903_015900.dump`，69.7 MB，**已實測還原**：`G2_SB6_dump_restore_verification.json`）。**2026-09-03 已進入真實庫**（`postgres`@`localhost:5432`，PO 重新授權；`schema_version` 5，46 列逐月對號 46/46 相等；`G2_SB6_realdb_import_verification.json`）——**編號 9 但執行順序在 SB6 之前**：SB6 的流動性排名需要它的產出。原 Master Plan 中 SB6 需要 SB7 的「股價批次下載」能力、SB7 卻依賴 SB6，**循環依賴，而「取得候選池價格資料」兩個 SB 都沒有負責**）→ **UG-G2-SB6 ✅ CLOSED**（2026-09-03，PO 核准 Gate B。Gate A 同日核准：migration 006 + `src/transform/universe_builder.py` + 13 項零 DB 依賴測試；真實庫產出 **46 期 PIT 快照**、每期納入 150、總計 85,641 列；**逐月對號 46/46 逐一相等**；退出股兩類違規皆 0。⚠ **實作期發現已核准提案內部對 60 日窗邊界自相矛盾**，裁定以 DEC-017 為準（**DEC-033，`APPROVED`**），46 列基準作廢重算、實測 8 列改變。**該裁定的 known-FAIL 已做成離線可重現**（`G2_SB6_monthly_reconciliation_knownfail.json`）——**複查方據此獨立重跑並確認 8/46 與 0/46，是本專案少數不需要容器即可複核的證據**。⚠ **V2（7 天尖峰）不成立**，依事前寫下的處置只記錄為觀測） → UG-G2-SB7 → Gate 2 關閉 → `google-genai` 遷移 SB（RISK-019）→ Gate 3**。**SB8 排在 SB6／SB7 之前**：SB7 是把 pipeline 大規模跑起來，先把特徵集補完，SB7 跑的才是完整的 CORE_16，不用事後重跑。**Gate 2 關閉條件已新增兩項**：第五項「真實開發資料庫與 migration 狀態同步，且 pipeline 已對其實際執行過一次」——原本四項全部都能在拋棄式臨時 DB 裡滿足，等於可以關掉一個從來沒跑起來過的系統（RISK-017）；**第六項「CORE_16 的 16 個特徵全部可計算」**（2026-08-31，DEC-029）；**並將既有的「Universe 建立」措辭收緊為可證偽形式**（2026-08-31，DEC-031——原措辭是那種**在 4 檔股票上也能宣稱達成**的寫法，與 SB1「有 29 欄」沒說哪個資料庫同型；改為明確涵蓋規模與歷史深度：候選池涵蓋台股上市全市場 ≥ 500 檔、歷史深度 ≥ 3 年、且已產出至少一個 PIT Universe Snapshot）（2026-08-31，DEC-029——四個平穩化特徵已在契約與 schema 中宣告但從未被計算，沒有它們 CORE_16 實際只有 12 個特徵、COMMENT_ENHANCED_19 只有 15 個；**一個宣稱交付 16 個核心特徵的 Gate，若關閉時有 4 個算不出來，交付的就不是它宣稱的東西**） |
| **UG-Gate-3** | **已於 2026-09-16 全數 CLOSED**（七個 Small Batch，含 `SB2a`，皆已 PO 核准結案，`UG-G3-SB7` 結案即關閉 Gate 3，見 §0.2）。不再是「未授權」項目，自本次更新起自本表移除（同 `UG-Gate-1`／`UG-Gate-2` 先例） |
| **UG-Gate-4** | **未核准，不得啟動** |
| `database/`（Schema／DDL 本身） | 升級專案至今**未執行破壞性變更**；UG-G1-SB4 已新增 additive migration 機制（`schema_version`、`apply_migrations.py`），僅限已核准的 additive DDL |

### 0.2A UG-Gate-2 交付摘要（2026-09-06 關閉）

| 項目 | 起 | 迄 |
|------|-----|-----|
| 候選池 `candidate_prices` | 不存在 | **2,016 檔／4.09 年／1,823,842 列** |
| PIT Universe | 不存在 | **46 個快照／85,641 列** |
| `daily_ml_features` | **7 欄** | **29 欄** |
| ETL 稽核 | 無 | `etl_run_log` **四態 outcome** 落地 |
| 每日取價請求數 | **150**（逐股） | **2**（每市場 1 個報表） |
| 測試 | **154**（GOV-02 基線） | **447** |

> ⚠ **但真正的交付不是上面任何一個數字，是「失敗不再長得像沒有資料」。**
>
> `UG-G2-SB7` 的 Gate A 才把那條鏈診斷出來 —— 它有四段，而**四段都是斷的**：
> extractor 拋出的例外被 pipeline 吞掉、`source_status` 只產得出兩態、
> `SOURCE_FAILED` 的列被 `fillna` 填成中立值、moving average 用
> `min_periods=1` 在失敗日給出看起來合理的數字。
>
> **每一段單獨看都像小瑕疵；四段連起來，一次取數失敗會變成一列
> 「那天沒人討論」的正常資料，而模型會學它。**
>
> **候選池從 4 檔追蹤標的長到 2,016 檔，是規模；那條鏈修完，是這個 Gate 的實質。**

---

### 0.3A ⚠ 「更新 `PROJECT_STATUS.md`」不是一個動作，是**至少三個**

| # | 位置 | 回答什麼 |
|---|------|---------|
| 1 | **§0.2 的 SB 狀態表** | 那個 SB 結案了沒、commit 是哪個 |
| 2 | **§0.3 的 Gate 摘要行** | 這個 Gate 現在走到哪 |
| 3 | **§0.4 的測試基線** | 涵蓋範圍是多少 |

**2026-08-31 ~ 09-06 的六次結案，每一次都只做了其中一部分。**

- `UG-G2-SB6` 結案：做了 §16.3 的搬檔，**漏了 §0.4**
- `UG-G2-SB6`~`SB9` 結案：做了 **§0.4**，**漏了 §0.2 的四列與 §0.3 的摘要行**

> **兩半剛好對調，而每一次都以為自己更新完了。**
>
> ⚠ **為什麼六次都沒有人發現**：每一次都更新了 §0.4，**而那一行是準確的**。
> **所以這份文件看起來是有在維護的。**
> **一份被部分維護的文件，比一份完全沒動的更難發現過期 ——
> 因為「最近改過」這個訊號還在，而它指向的是另一個章節。**

**這一段寫在本文件裡、不寫在 Gate 關閉報告裡**：關閉報告會進 `closed/`，
**而下一個要更新這份文件的人不會去讀它**（理由同 `UG-G2-SB7` 第 5 項對 V7 的判斷——
三個 `source` 值要寫進契約，不能只寫在會被歸檔的提案裡）。

---

### 0.4 測試基線

**`441 tests / 41 檔`**（標準測試指令實際涵蓋範圍，截至 UG-G2-SB7 結案）**（不含刻意不被 discover 的 `tests/schema_smoke_ui_data_loader.py`，見 §0.5 #8）**。
> **【2026-09-03 更正】原寫 32 檔。** `ls tests/*.py` 是 32，`ls tests/test_*.py`（**discover 實際涵蓋的範圍**）是 31。**32 把那支刻意不被 discover 的 smoke test 算了進來，而括號裡的標籤明寫「標準測試指令實際涵蓋範圍」** ——
> **數字換了它在數的東西，標籤沒換。**
> 這一次特別值得記：**那支檔案不被 discover 是刻意的設計**（PO 指示，§0.5 #8），把它算進「涵蓋範圍」等於**在文件上抹掉那個設計**。
**`UG-G2-SB6` +13**（`test_universe_builder.py`，**零資料庫依賴**——PIT 的正確性不能靠一個在沒有 DB 時就悄悄跳過的測試守）。**332 + 13 = 345，逐項吻合。**
**`UG-G2-SB7` +96／+10 檔**（`test_batch_etl_boundary.py` **21**、`test_ptt_board_pages.py` **18**、`test_etl_run_log.py` **9**、`test_source_failed_nulls.py` **9**、`test_extractor_retry_discipline.py` **8**、`test_feature_source_allowlist.py` **8**、`test_ptt_post_time_from_url.py` **8**、`test_ptt_failure_is_recorded.py` **6**、`test_yfinance_no_retry.py` **5**、`test_aa_network_guard.py` **4**）。**345 + 96 = 441，逐項吻合。**
> ⚠ **96 同時是「新增檔案的測試總數」與「441 − 345」** ——
> 兩者相等代表**既有檔案的測試數淨零變動**。
> `test_ptt_failure_is_recorded.py`（第 5 項改寫，淨 +2）與 `test_operational_ux.py`（僅改 mock）
> 都在 SB7 內被編輯過，**而它們的變動不是「順手加測試」，是接縫改變的連帶**（§0.5 #17）。
歷程：GOV-02 基線 154 → Gate 1 收尾 200（`UG-G1-SB1`～`SB4` 新增，`SB5` 為純文件修改未動）
→ Gate 2 累計 269（`UG-G2-SB1` +8、`SB2` +6、`SB3` +11、`SB4` +13、
`SB5` 可用性驗證 +25、`SB5` 決策點 5 +6、`SB8` +9、**`SB9` +54**）。**SB9 逐檔拆分**：`test_twse_market_report.py` **20**（含 `SharedTableFinderDefaultPathTests` 3 條——`_find_market_table()` 一般化後，**不帶參數的預設路徑正是三年回補所依賴的那條**，而「行為不變」原本只隔著推理）、`test_tpex_endpoint_criteria.py` **26**（C1~C6 的 known-FAIL，含 `BaselinePassTests` 反向守衛與 `test_real_fields_match_raw_capture_verbatim`）、`test_tpex_market_report.py` **8**。**278 + 54 = 332，逐項吻合。** 取數方式：容器內 `python -m unittest discover -s tests -p "test_*.py"` 的實際輸出（`Ran 332 tests / OK`）與 `defaultTestLoader.discover()` 的逐模組計數，**非 `grep "def test_"`** —— 本格記的是「標準測試指令實際涵蓋範圍」，兩者這次剛好相同，但**相同是結果，不是可以互相取代的理由**（§0.5 #8 的非發現性缺口即源於此差別）。

> **`SB5` 的 +25 來源是「判準邏輯的 known-FAIL 測試」，不是 adapter 測試。**
> `UG-G2-SB5` 的可用性驗證判定 `FAIL`，**`src/extractors/dcard_scraper.py` 從未建立**，
> Master Plan Brief 所列的 `test_dcard_fetch_articles`／`test_dcard_dedup_key`／
> `test_dcard_failure_isolation` **一個都不存在**。
> 新增的 `tests/test_dcard_availability_criteria.py` 測的是
> `scripts/verify/dcard_availability_check.py` 的**判準邏輯本身**
> （A1–A5 各自的 known-FAIL、`NOT EXECUTED` 根因歸因、`INCONCLUSIVE` 觸發與反向守衛、
> A2 的真實路徑匿名性檢查、憑據不得落檔）。

**上表數字每次 SB 收尾都需重新核對**——`164`（`UG-G1-SB1` 當時）、`200`（Gate 1 收尾當時）
、`238`（`UG-G2-SB4` 收尾當時）、`263`（`UG-G2-SB5` 可用性驗證收尾當時）與 `269`（決策點 5 收尾當時）皆已過期，
**不要引用**；
§1 記載的「133/133」是 2026-08-20 的舊數字，**已過期**。
**host 為降級環境**，其結果不得支撐任何 ML／NLP／重試／LLM 路徑的宣稱
（`CLAUDE.md` §13.0、§13.3）。

**核對指令（注意 `test_*.py` 與 `*.py` 會得到不同數字，兩者都對，量的是不同東西）**：

```bash
# A. 標準測試指令實際涵蓋的範圍（= 上方 278 / 27 的來源）
ls tests/test_*.py | wc -l                                        # 27
grep -ch "def test_" tests/test_*.py | awk '{s+=$1} END {print s}' # 278

# B. tests/ 底下所有 .py（含不符命名慣例、discover 撿不到的檔案）
ls tests/*.py | wc -l                                             # 28
grep -ch "def test_" tests/*.py | awk '{s+=$1} END {print s}'      # 282
```

**A 與 B 的 1 檔／4 個測試差額，來源是 `tests/schema_smoke_ui_data_loader.py`**——
檔名**刻意**不含 `test_` 前綴，使
`python -m unittest discover -s tests -p "test_*.py"` 不會自動撿到它
（`UG-G1-SB2` 依 PO 指示的設計，見 `doc/upgrade/gates/closed/SB2_GATE_A_PROPOSAL.md` §5.1.3
與該檔案開頭 docstring）。

**排除的理由**：它是 **schema 相容性 smoke test，需要真實 PostgreSQL 臨時 DB**——
mock 只能驗證「程式碼假設的欄位名稱」，驗證不了「這些欄位在真實 schema 裡還存不存在」。
若讓它進入 discover，一般測試執行（未啟動臨時 DB 時）會因連線失敗而整批紅燈。

**執行時機（本次補上——原本只寫了「怎麼執行」，沒寫「什麼時候該執行」）**：
凡是**已經為了 E2E 驗證啟動隔離臨時 DB 的 SB**（動到 `schema.sql`／新增 migration／
變更 `db_writer` 讀寫欄位者），都應在同一個臨時 DB 內順帶執行一次：

```bash
python -m unittest tests.schema_smoke_ui_data_loader -v
```

> ⚠ **已知缺口（UG-G2-SB4 收尾時揭露）**：本檔自 `UG-G1-SB2`（commit `414fcc81`）
> 執行過一次後，**`UG-G2-SB1`／`SB3`／`SB4` 三次臨時 DB E2E 均未執行它**——
> 這三次都動了 schema（migration 002／003／004）與 `db_writer` 的讀寫欄位，
> 正是它最該發揮作用的時機。目前它**不是設計上不跑，而是沒有任何機制觸發它**，
> 因此自 SB2 以來的 schema 變更未受其保護。上方「執行時機」即為補救；
> **補跑本身已列為 §0.5 未結義務 #8**，觸發條件為「下一次啟動隔離臨時 DB 的 SB」，
> 刻意不綁定 SB 編號（理由見該列）。

### 0.5 未結義務清單

| # | 義務 | 期限／歸屬 |
|---|------|-----------|
| 1 | ~~**RISK-013 根本解**：「驗證腳本在偵測到指向真實 DB 時拒絕執行」~~ | **已解決（2026-08-26，UG-G1-SB4 階段一，commit `d2a4d48`，DEC-021）**：`database/db_target_guard.py` 的 `assert_safe_migration_target()`，`apply_migrations.py` 建立連線前強制呼叫。已實測：以真實 DB 座標未確認執行 → 連線前即被拒絕。剩餘缺口（機制依賴呼叫端主動呼叫，未強制耦合於 `DBWriter` 寫入方法本身）已記錄於 DEC-021 Trade-offs，PO 同意本次不要求改設計 |
| 2 | GOV-04 三項補件（hook 檔頭、檢查目標不一致、§11A 規則化） | 已完成，隨 GOV-06 落盤 |
| 3 | DRIFT-018：`src/ui/components.py` 排行榜八個寫死數值 | UG-G1-SB2。標註為「**未經驗證的展示值，證據待補**」，**不得**標為「含洩漏」—— 後者預設它們是有已知瑕疵的真實量測，而無證據顯示曾被量測過 |
| 4 | ~~`doc/upgrade/gates/closed/` 缺 `.gitkeep`~~ | **已解決（2026-08-25，隨 SB2 結案一併處理）**：義務 7 的搬移已執行，`closed/` 現含 8 份檔案，git 因非空目錄自然追蹤，`.gitkeep` 已無必要 |
| 5 | ~~「24 個 Small Batch」硬編碼於 `doc/README.md` 與 `CLAUDE.md` §16.3~~ **已解決（2026-09-01，GOV-09）**：**兩處皆已移除數字**，改為指向 `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2。`CLAUDE.md` §16.3 於 commit `43f75ce`（GOV-09 授權範圍內）、`doc/README.md` §3 於本次文件衛生 commit。**只改一處不算解決**，故待兩處皆完成才劃掉。 | 該數字的唯一權威來源是 `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`；複製一份即為下一個 DRIFT。**本項預測成真**：`UG-G2-SB8`／`SB9` 使實際數量成為 **26**（Gate 1 五、Gate 2 九、Gate 3 七、Gate 4 五），而登記在案的「24」無人更新。**且 `UG-G2-MIG` 不在任何編號序列裡——連「幾個」都不是一個穩定的問題**，這正是「改成 26」不是正解、「把數字拿掉」才是的理由。**發現時機**：GOV-09 正要編輯 §16.3 那一段，**不修就是明知故留**。（2026-09-01 追記：另於 `doc/governance/TEAM_PLAYBOOK.md:79` 發現第三處，以 GOV-10 修正。本項當初以**列舉地點**書寫，因此結構上涵蓋不到未被列舉的地點——**義務應描述性質，不應列舉地點**。這件事本身就是它自己的示範：一條「不要硬編碼數字」的義務，**自己是用硬編碼的地點清單寫的**。與 §0.5 #7／#10 的對比同型——**列舉的漏掉，描述性質的沒漏**。GOV-11 續：同型第四處為 `gate-submit` 產出數硬編碼於 TEAM_PLAYBOOK `:203`／`:313`，已一併移除數字。**判別法：數字的權威若在同一畫面內**（如 §6.2「六項實踐」下方即為 P1–P6 六列表格），**不屬本型，不得一併移除**——規則不是「不要寫數字」，是「不要複製一個權威在別的檔案裡的數字」。） |
| 6 | 本文件 §1–§15 的 PRE_CODEX 舊內容未改寫 | 與現行升級專案的關係見 §0 開頭的編號警告 |
| 7 | ~~`CLAUDE.md` §16.3【強制】：SB 通過 Gate B 後，提案文件應移入 `doc/upgrade/gates/closed/`~~ | **已解決（2026-08-25）**：PO 於 SB2 結案時明確指出「上次 SB1 結案時揭露了這義務但沒有執行」，本次一併搬移 SB1（4 份）與 SB2（4 份）共 8 份文件至 `doc/upgrade/gates/closed/`；同時更新 `SYSTEM_UPGRADE_MASTER_PLAN.md` Brief（§16.3 規則 2 的前置條件）與所有引用路徑（`CLAUDE.md`、`TEAM_PLAYBOOK.md`、本文件、`tests/schema_smoke_ui_data_loader.py`）。`evidence/` 下（`DECISIONS.md`／`TRACEABILITY.md`／`DOCUMENT_DRIFT_REMEDIATION.md`）既有段落的舊路徑引用**刻意未動**——該資料夾依 §16.1 為「只增不減」的證據記錄，逐一改寫歷史段落的路徑視為對既有證據的編輯，本次未取得此授權；若 PO 認為仍應更新，請另行明確授權 |
| 8 | ~~**`tests/schema_smoke_ui_data_loader.py` 補跑**（UG-G2-SB4 揭露之缺口）~~ **已解決（2026-08-30，UG-G2-SB5 決策點 5）**：於隔離臨時 DB `g2sb5dp5_tmpdb`（非 `postgres-data` 掛載，已拆除）內執行 `python -m unittest tests.schema_smoke_ui_data_loader -v` → **`Ran 4 tests` / `OK`**。觸發條件如當初所設計地生效——**綁事件而非綁 SB 編號是對的**：`UG-G2-SB5` 的可用性驗證判定 `FAIL`、根本沒起臨時 DB，若當初綁了編號這條義務會再度落空；實際觸發它的是同一個 SB 的**決策點 5**。原文如下： | **觸發條件：下一次啟動隔離臨時 DB 的 SB**（不綁定特定 SB 編號——`UG-G2-SB5` 為 CONDITIONAL，若 Dcard 不可用而標記 `DEFERRED WITH EVIDENCE`、根本沒起臨時 DB，綁編號就會再度落空，那與本缺口本身是同一種失敗模式：有規則、沒有觸發機制）。**背景**：本檔自 `UG-G1-SB2`（commit `414fcc81`）跑過一次後，`UG-G2-SB1`／`SB3`／`SB4` 三次臨時 DB E2E 均未執行它，而那三次都動了 schema（migration 002／003／004）與 `db_writer` 讀寫欄位——這道專門偵測「UI 讀取層與真實 schema 脫節」的防線，在唯一該生效的三次變更中一次都沒生效。**風險評估（PO 2026-08-28）**：不高——002／003／004 全為 `ADD COLUMN` 純加法，無 `DROP` 或改名，加欄位不會使既有欄位消失，補跑幾乎確定會過；因此不值得為此單獨走一輪 RISK-013 綁定確認 + 起容器 + 拆容器。**執行方式**：在該次臨時 DB 內順帶 `python -m unittest tests.schema_smoke_ui_data_loader -v`，並於該 SB 的 Gate B 回報結果——這同時是 §0.4「執行時機」規則的第一次實地演練，順便驗證那條規則本身可行 |
| 9 | ~~**`G2_SB5_GATE_A_PROPOSAL.md` 移入 `gates/closed/`**（`CLAUDE.md` §16.3）~~ **已解決（2026-08-31）**：決策點 5 的獨立 Gate B 於 2026-08-30 通過，觸發條件成立。本次一併移入 `gates/closed/` 共 **5 份**——`G2_SB5_GATE_A_PROPOSAL.md`、`G2_SB5_DP5_GATE_A_PROPOSAL.md`／`G2_SB5_DP5_GATE_B_SUBMISSION.md`（2026-09-08 展開全名，原為縮寫「／`_GATE_B_SUBMISSION.md`」，機械掃描抓不到，見第 6 案 R2）、`G2_MIGRATION_SB_GATE_A_PROPOSAL.md`／`_GATE_B_SUBMISSION.md`，並同步更新 `DECISIONS.md`（3 處）、本檔（1 處）與兩份送審文件內的路徑引用。`scripts/verify/gate0_contract_check.py` 的 `DOC_PATHS` **不含任何 Gate 提案檔**，故 §16.4 的連帶義務不適用（已查證）。**`gates/` 根層現只剩兩份 Gate 層級啟動申請書**，符合 §16.3 規則 4。原文如下： | **觸發條件：決策點 5（來源能力宣告）的獨立 Gate B 通過時**——**綁事件，不綁 SB 編號、不綁 commit**。**為何現在不搬**：`UG-G2-SB5` 的可用性驗證雖已判定 `FAIL`／`DEFERRED WITH EVIDENCE`，但該 SB **尚未結束**——PO 2026-08-28 裁定決策點 5「不分 PASS／FAIL 都要做」，該實作動 `src/`，走獨立 Gate B。§16.3 規則 4「`gates/` 根層永遠只保留審查中的 SB」因此仍然成立。**特別的風險**：`DEFERRED WITH EVIDENCE` **看起來像結案了，其實沒有**——這比 #7 當初的情況多一層混淆，若不綁死觸發事件，很可能重演 SB1 那次「揭露了卻沒有執行」。搬移時同步更新引用路徑（比照 #7 的作法）|
| 10 | **SB 新增的 ADR 於該 SB Gate B 通過時一併轉 `APPROVED` 並補進 `TRACEABILITY.md` §3.2** | **觸發條件：每一個 SB 的 Gate B 通過時**——**綁事件，不綁清單**。**病因（`evidence-sync` §2.1 已命名為 C-5）**：Master Plan §19.1 的「核准後收尾程序」**只針對 Gate 0 且寫死 6 則 ADR**，Gate 1／2 沒有對應程序。實務結果：DEC-020／021／022 靠各自 Gate B 臨時核准僥倖處理，**DEC-023／024／025 就這樣停在 `Proposed`**，且 DEC-024 的 CHECK 約束已隨 migration 004 在資料庫生效。**這是 C-5 第三次發生。** 綁清單必然重演——下一則 DEC-028 會用一模一樣的方式漏掉。**實質暴露**：`CLAUDE.md` §0.2 把「已核准的 ADR」排在第 2 順位、高於 Gate 0 交付物，而 `Proposed` 的 ADR **根本不在那個優先順序裡**——一份已核准的交付物若加註引用未核准的 ADR 當授權依據，該引用沒有位階。**執行內容**：(a) 該 SB 新增的 ADR 狀態改 `APPROVED`（僅 PO 可為之，Agent 不得自行填寫）；(b) 補進 `TRACEABILITY.md` **§3.2 ADR 快速索引與 §2 端到端追溯矩陣**（**2026-08-31 修補**：原規則只寫 §3.2，未涵蓋 §2；`UG-G2-SB5` 決策點 5 是本規則第一次生效，**第二次生效時就露出缺口**——DEC-024／025／026／027 當時在 §2 的出現次數各為 0。不補則 DEC-029 會用一模一樣的方式漏掉，**那正是 C-5 的形狀**。四則已於 `UG-G2-MIG` 回填）——**不在索引裡比狀態是 `Proposed` 更嚴重：前者是根本不知道有這則 ADR 存在** |
| — | **（本項延續，非新條目）** | **2026-09-09 生效第 N 次，仍未漏**：`UG-G3-SB1` Gate B 核准結案時，`DEC-035`（Gate B 送審期間新增，修訂 DEC-018）於同一個結案 commit 內轉 `APPROVED`，並補進 `TRACEABILITY.md` §2 端到端追溯矩陣列與 §3.4 索引列（本則自 §3.3 起已改用逐 Gate 分節而非單一 §3.2，§3.4 為 Gate 3 對應分節，同一義務延續適用）。 |
| — | **（本項延續，非新條目）** | **2026-09-10 生效第 N+1 次，仍未漏**：`UG-G3-SB2` Gate B 核准結案時，`DEC-036`（Gate A 送審期間新增，`UG-G3-SB2a` 拆分決策）於同一個結案 commit 內轉 `APPROVED`，並補進 `TRACEABILITY.md` §2 端到端追溯矩陣列與 §3.4 索引列。 |
| 11 | **`TRACEABILITY.md` §2「總計」列更新**（另案） | **觸發條件：另案處理，不綁本 SB。** `:66` 仍為 `9 大核心 ADR + 7 大挑戰｜18 大核心生產模組｜17 大測試套件檔案｜154 項測試｜100% PASS (~1.80s)`，而現行基線為 **269／26 檔**、ADR 已到 **028**。**本次刻意不修**——該列其他欄位需重新盤點才能一致，**半修比不修更誤導**。**動手前必須先套用的判準（PO 2026-08-31 指定）**：**§2 裡的數字要先分成「當前狀態宣稱」與「歷史執行紀錄」，前者必須更新，後者絕對不能動。** `:66` 的總計列是**當前狀態宣稱**，必須更新；而 `:164-165` 的 `Ran 154 tests in 1.486s / OK` 加上「PO 獨立複驗得 1.643s」是**某一次執行的歷史紀錄**，改它就是**竄改證據**。沒有這個判準，「更新總計」很容易變成把歷史紀錄一起改掉 |
| 12 | ~~**「DoD 措辭必須指名目標資料庫」需要一個具名的觸發點**（RISK-017 緩解第 2 條）~~ **已解決（2026-08-31）** | **PO 2026-08-31 更正了本項原本的登記方式，理由值得留著**：§0.5 是**未結義務清單**，裡面的項目是**會被結案的**（第 1／4／7／8 項現已劃掉）。而「DoD 措辭必須指名目標資料庫」是一條**永遠不會結案的常設標準**——放進來它會永遠掛著像沒做完，**並稀釋整個清單的訊號**：若有些項目本來就不會關，「還剩幾項未結」就不再是有意義的數字。**正確的切法是把「標準」與「動作」分開**：(a) **常設標準本身**留在 **RISK-017 緩解第 2 條**——它正是該風險維持開啟的原因，風險登記簿本來就是承載「尚未內化的標準」的地方；(b) **一次性動作**（把該標準寫進 `gate-submit` 檢查清單）就是本項，做完即結案；(c) **提醒發生的時點**放在 `.claude/skills/gate-submit/SKILL.md`——**已新增為「產出 7：DoD 措辭必須指名目標資料庫」**，並同步將「六項強制產出」改為七項、自檢流程補入第 8 步。**為何是 `gate-submit` 而非 `small-batch-orchestrator`**：後者是撰寫 DoD 的時點、理論上更早，但它只會多一個「要記得」的地方；`gate-submit` 是**會被實際執行的關卡**。§9A.1 的整個教訓就是——**一個會跑的檢查勝過一條要記得的規則**。**誠實揭露的限制**：`gate-submit` 是 skill（指示）不是腳本，本項讓規則**在對的時點被讀到**，但**未使其成為機械強制**；真正機械化是 `gate0_contract_check.py` 的題目，需另外設計判準，**刻意不順手做——做不好會變成一個永遠通過的檢查** |
| 13 | **`REMAINING_RISKS.md` 狀態欄混著兩個軸**（另案） | **觸發條件：另案處理，不綁任何 SB。** 該欄現有詞彙為 `HYPOTHESIS`／`NOT VERIFIED`／`OBSERVED`／`VERIFIED`／`VERIFIED（部分）`／`PLANNED`／`MITIGATED`，其中 **`PLANNED` 與 `MITIGATED` 是處置狀態，其餘是證據狀態**——**一欄混著兩個軸**。**這不是 `UG-G2-MIG` 引入的**（`PLANNED` 早於本 SB 即存在），本 SB 的 `MITIGATED` 只是延續。**本次刻意不順手統一整欄**——那需要先決定要不要拆成兩欄（證據狀態／處置狀態），在未決定前統一只是把混淆換個形式。**過渡作法**：RISK-017 採「`OBSERVED`（實測日）→ `MITIGATED`（處置日）」並列寫法，理由是它是 High、會被反覆閱讀，兩個資訊都該留著 |
| 14 | ~~**`UG-G2-SB8` 的過程文件與 `GATE1_STARTUP_APPLICATION.md` 未移入 `gates/closed/`**~~ **已解決（2026-09-01）**：`git mv` 三份（`G2_SB8_GATE_A_PROPOSAL.md`、`G2_SB8_GATE_B_SUBMISSION.md`、`GATE1_STARTUP_APPLICATION.md`），diff 皆為 **`R100` 純 rename**，內容零變更。`gate0_contract_check.py` 的 `DOC_PATHS` **不含任何 Gate 提案或啟動申請檔**（已查證），故 §16.4 連帶義務不適用。`gates/` 根層現只剩 `G2_SB9_GATE_A_PROPOSAL.md`（審查中）與 `GATE2_STARTUP_APPLICATION.md`（Gate 2 未關閉），符合 §16.3 規則 4。`GATE2_STARTUP_APPLICATION.md` **加超越註記但不改表格**——它是 2026-08-26 的申請快照，改寫等於摧毀「當時申請了什麼」這個治理紀錄（同 §16.2 對 `archive/` 的原則）。 | **依 §0.5 #12 的切法登記**（PO 2026-08-31 親自更正過的方式）：**常設標準不進本清單，一次性動作才進**。(a) **常設標準**（「任何 SB 的 Gate B 通過時、任何 Gate 關閉時，對應文件即移入 `closed/`」）**其歸屬地是 `CLAUDE.md` §16.3**——現行 §16.3 的 `root → closed/` 只為 SB 提案設計，**Gate 層級的啟動申請書沒有對應生命週期**，所以 `GATE1_STARTUP_APPLICATION.md` 一直留在根層。**該條文的修訂需 PO 明確授權（比照 GOV-08），本次未取得，故未動 `CLAUDE.md`。**(b) **一次性動作**（本次搬移）即本項，做完即結案。(c) **提醒發生的時點**已加入 `.claude/skills/gate-submit/SKILL.md` 的**產出 8**，並將「七項強制產出」改為八項、自檢流程補入第 9 步。**為何是 `gate-submit`**：同 #12 的理由——`small-batch-orchestrator` 是規劃時點、理論上更早，但它只會多一個「要記得」的地方；`gate-submit` 是**會被實際執行的關卡**。**本項的病因**：同一個義務漏了兩次——`UG-G2-SB1` 結案時揭露了卻沒執行（#7）、補規則後 `UG-G2-SB5` 靠 #9 的個案觸發條件才沒漏、**而 `UG-G2-SB8` 結案時沒有人替它登記，於是又漏了**。**同一份清單裡就有對照組：#10 是通則，所以 DEC-029～031 一個都沒漏。綁事件的那條運作正常，綁個案的那條漏了兩次。** |
| 15 | **`UG-G2-SB9` 三年候選池資料的還原目標未定** | **觸發條件：`UG-G2-SB6` 啟動時**——**綁事件，不綁編號**。**1,821,870 列**（TWSE + TPEx，**4.05 年**，含 2026-09-03 的 +1 年延伸）目前只存在於 repo 外備份 `..._candidate_prices_twse_tpex_4y_20260903_015900.dump`（69,742,758 bytes）。**已實測還原**（`G2_SB6_dump_restore_verification.json`，拋棄式容器 `sb6_restore_check`：還原前 0 列／2 個 CHECK，還原後 1,821,870 列、983 天、TPEx 三項寫入守衛全為 0、`schema_version` = 5）。⚠ **原三年 dump（53,338,453 bytes）仍保留**，但**已非現行基準**。~~**真實庫的 `schema_version` 仍是 4、`candidate_prices` 不存在**——本 SB 全程未對真實庫寫入任何候選池資料（DoD 第 3 項）。~~ **【2026-09-03 已解決，本項可視為關閉】** 決策點 2 經 PO **重新授權**後執行（原授權點名 1,389,890 列，延伸後為 1,821,870 列 —— **授權範圍是用那個數字界定的，所以需要重新給，不是自動延伸**）。真實庫 `postgres`@`localhost:5432` 現況：`schema_version` = **5**、`candidate_prices` = **1,821,870 列 / 983 交易日**、兩個 CHECK 存在、`daily_ml_features` 與 `stock_prices` **維持 117 / 117 未變**。**匯入忠實性以 46 列逐月對號驗證，46/46 逐一相等、零不符** —— 列數總計相同仍可能有列跑到錯的日期或錯的來源，那種錯誤過不了這個檢查。證據：`evidence/G2_SB6_realdb_import_verification.json`。⚠ **但本項登記的風險並未因此消失**：dump 仍是唯一的離線副本、無版控、無校驗碼，而**真實庫的實體資料檔同樣不是可攜式備份**（CLAUDE.md §3）。**為何現在不決定**：SB6 的 Universe 建構規則會決定要不要保留全部 1,099 + 912 檔、要不要保留零成交列，**先進庫再篩等於先做一個可能要重做的決定**。**風險**：一份只存在於單一 `.dump` 的 **182 萬列**資料，**沒有版控、沒有校驗、且產生它的臨時容器已拆除**；重取需約 800 次對政府單位服務的請求，且端點不穩定（本 SB 實測 SSL／520 十餘次）。**2026-09-03 更新**：延伸回補的實際成本為 TWSE 263 次 + TPEx 約 268 次請求（各在 300 次／市場預算內），TPEx 側需分 6 段並依賴有界重試。**還原可行性已由 `G2_SB6_dump_restore_verification.json` 實測，但「單一檔案、無版控、無校驗」這個風險本身未改變** —— **還原成功證明的是這一次能還原，不是這個檔案不會遺失或損壞。**重跑用的 SQL 與判準保存於 `evidence/G2_SB9_crossmarket_and_null_semantics.json` |
| 16 | **`PURGED_WALK_FORWARD_SPEC.md` §3.3 的兩個判準在預設下互相衝突，且其一在嚴格 WF 下零訊號** | **觸發條件：Gate 3 啟動前**——**綁事件，不綁編號**。§3.3 逐字為「最少 Fold 數｜≥ 3 個完整 (Train, Test) 組合」與「最少訓練樣本｜每 Fold purge 後仍需 ≥ `min_train_size` 天」。**`min_train_size` 不在 §3.1 的六個參數預設表裡**，整份規格沒有給它數值；但 `src/ml/time_series_split.py:94` 推導為 `max(1, train_window_size − label_horizon)`，而該檔 `:51-53` 的 docstring 逐字說明了理由：**「即容許正常 Purge 造成的縮減，但不容許 Purge/Embargo 疊加造成的額外縮減」**。**所以它不是判準空著，也不是結構上不可能失敗——它是判準與情境相依，而情境沒有被寫出來**：它偵測的**只有**「Purge/Embargo 疊加」這一件事。**實測**（`WalkForwardSplitter(60, 20, label_horizon=1)`，740 個交易日；`min_train_size = 59`）：`embargo_days=0`（§3.1 預設）→ **34 個 fold、purge 後訓練天數全部是 59、無一低於門檻**——**該判準通過，但零訊號**；`embargo_days=1` → **僅 2 個 fold**（32 個被跳過）；`=5` → 2；`=10` → 2。**只要開任何 embargo，fold 數就掉到 2，低於同一張表自己要求的 ≥ 3。** **兩個判準在 §3.1 的預設下無法同時滿足**：不開 embargo 則 `min_train_size` 不產出證據，開了則 fold 數不合格。**Gate 3 的實質後果**：若走嚴格 WF（`embargo_days=0`），**「`min_train_size` 檢查通過」不得被當成資料量充足的證據**——它在該情境下恆真。**刻意不現在填數字、不調參數**——那正是「先寫一個數字再拿它當判準」與「調整到通過為止」。需 PO 於 Gate 3 啟動前裁決：`min_train_size` 的實質值與依據、以及 embargo 與 fold 數的取捨。（量測於 `pd.bdate_range` 產生的 740 個工作日索引上，**該衝突是演算法的結構性質，非本專案資料的特性**） **補充（2026-09-02，複查方實測 + PM 獨立重現）**：該衝突**僅存在於 `mode='rolling'`**（§3.1 預設值）。`mode='expanding'` 在 `embargo_days = 0/1/5/10/20` **皆維持 34 個 fold**。**此事實用於界定問題範圍，不得作為「改用 expanding」的理由** —— rolling 與 expanding 的選擇是**建模決定**（是否保留 regime shift 前的舊資料），必須以證據回答，**不得由「哪個設定能讓 fold 數過關」決定**。用驗證守衛去決定建模方式，是 `TEAM_PLAYBOOK` §6.2 P5「拒絕調整標準來解除自己的阻擋」**換一個方向做的同一個錯誤**。**且 expanding 並未逃過代價，只是沒有觸發檢查**（PM 實測）：最後一個 fold 的訓練天數隨 embargo 遞減 —— `embargo=0` → **719 天**、`=5` → 559、`=10` → 399、**`=20` → 80 天（少了 89%）**，而 `min_train_size = 59` 因 80 > 59 **完全沒有反應**。**守衛在 expanding 下也近乎失明，只抓得到最極端的情況** —— 它會**通過檢查的同時安靜地丟掉大部分訓練資料**。 **Gate 3 啟動前實際要決定的是三件事，不是一件**：**(1)** 本專案採 rolling 還是 expanding？—— **建模決定**，需證據（regime shift 的影響）；**(2)** 採嚴格單向 WF（`embargo_days=0`）還是 CV 場景？—— 規格 §3.2 已說嚴格 WF 下 0 是合法的；**(3)** 若 (1) 選 rolling 且 (2) 選 `embargo>0`，`min_train_size` 要覆寫成多少？—— **需要一個有依據的數字，不是隨手填**。**只有三者都回答了，§3.3 那兩列才同時有意義。** **【2026-09-09 三件事皆已裁決，本項可視為關閉】**：PO 隨 Gate 3 啟動核准九項裁決之②③④——(1) rolling **暫維持**，與 expanding 的對照列為 `UG-G3-SB3` 內建子實驗（非另跑一輪）；(2) `embargo_days=0` **核准**，附明文失效條件（成立於現行 1 天標籤視野；標籤視野一變即自動失效須重議）；(3) `min_train_size` 覆寫**不裁——條件未觸發**（rolling+embargo=0 下公式推導值照舊，非「已解決」，見 `GATE3_STARTUP_APPLICATION.md` §10）。**結構性衝突本身未消失**（rolling 疊加 embargo>0 仍會使 fold 數崩到 2，這是演算法性質，不會因為裁決而改變）——變的是「Gate 3 現在能不能開工」這件事已有答案，不是那個結構性質本身被修正。⚠ **裁決③的失效條件在 `UG-G3-SB1`（Triple-Barrier，H=5）字面上立即觸發**——已用真實 `WalkForwardSplitter` 唯讀重測：H=1→H=5 時 `min_train_size` 預設值 59→55（`max(1, 60−label_horizon)`），fold 數與崩潰模式（`embargo=0`→34/46 fold；`embargo>0`→2 fold）**在四檔股票的實際列數下完全相同**，expanding 模式最後一個 fold 訓練天數僅減少 4 天（719→715，−0.6%）——**H=5 對 purge 算術的實際影響遠小於原先假設的「整組改變」**，量測見 `doc/upgrade/gates/UG_G3_SB1_GATE_A_PROPOSAL.md`。理論上的自相關滲漏疑慮（非本量測能回答）仍依 PO 原裁決延後至 `UG-G3-SB3` 洩漏診斷處理。 |
| — | **（本項延續，非新條目）** | **2026-09-13：`UG-G3-SB3` 洩漏診斷與 rolling/expanding 對照結果登記**（`UG-G3-SB3` 已於 2026-09-13 CLOSED，見 `doc/upgrade/gates/closed/UG_G3_SB3_GATE_B_SUBMISSION.md`）。**洩漏診斷（決定點③失效條件已於 `UG-G3-SB1` H=5 觸發，本 SB 為責任落地）**：28 組（3 模型×2 臂×2 模式×2 target 排列，B 排除 LR）逐 Fold 邊界窗/內部窗診斷，`leakage_summary.flagged` 全數 `False`（`frac_positive` 實測 0.44～0.53、`median_delta` 實測接近 0，皆未達 0.70／0.05 雙門檻）——**本次量測未發現邊界窗系統性異常，`embargo_days=0` 維持有效**。**rolling vs expanding（內建子實驗，不產出單一結論）**：`target_up_down` rolling 略高（macro F1 中位數 0.468～0.490 vs expanding 0.447～0.457）、`target_triple_barrier` expanding 略高（0.347～0.366 vs rolling 0.340～0.356）——方向在兩個 target 上相反，**不足以支持任一模式的普遍優越性**，最終選擇仍是 PO 的建模決定。 |
| — | **（本項延續，非新條目）** | **2026-09-13：RISK-023（留言三欄逐則時間戳重算）排程登記**——排在 `UG-G3-SB3` Gate B 核准後、`UG-G3-SB4` 之前，走 `bug-fix-protocol` 獨立小案，寫入方式比照 `RISK-027` 段 2 重跑（只更新留言三欄有差異的鍵，非全表 upsert）。**候補（待 PO 授權）**：容器內 `git` 環境設定常設化——`.devcontainer/devcontainer.json` 的 `postCreateCommand` 加 `git config --global --add safe.directory`／`core.autocrlf=true` 兩行，避免每次容器重建都重現 `UG-G3-SB3` 報告腳本撞到的 dubious ownership／CRLF 誤判兩個環境坑；比照 `679e26e` 環境小案模式，本次僅登記不動工。 |
| — | **（本項延續，非新條目）** | **2026-09-14：RISK-023 獨立小案已完成，含真實庫寫入——`bug-fix-protocol` 走完診斷（Step 1，唯讀）→ Gate A（PO 裁決採方案 A：逐則重算取代文章層級過濾；新 ADR `DEC-039` 修訂 `DEC-024`）→ 紅測（`66114c2`，含 P6 一致性守衛與 `df_comments=None` 拒絕的可驗證性補件，共 15 項）→ 實作（`9c7f58e`，`_aggregate_direct_comment_counts()` 逐 (article, stock_id) 列呼叫 `counts_as_of()`／`validate_comment_bounds()`，`comment_seq` 時間回退 `suspect` 守衛，全套 812/843 視測試檔範圍、contract-check 13/13，六項突變測試逐一確認）→ 寫入腳本（`f122352`，比照 `RISK-027` 段 2 重跑機制）→ Gate B（PO／審查方複核通過，拋棄式容器乾跑＋known-FAIL 示範）。真實庫寫入依 RISK-013 三步驟協議對 `postgres`@`localhost:5432` 完成：**352 個 `(trade_date, stock_id)` 鍵、8 檔股票**（2330:129／NVDA:86／2454:54／2382:25／8069:18／3008:16／2059:12／6488:12）的留言三欄由全 NULL 變為觀測值；PRE 備份 `stock_prediction_system2_PRE_risk023_comment_features_20260914_130807.dump`、POST 備份 `stock_prediction_system2_POST_risk023_comment_features_20260914_130807.dump`（`D:\Python\Database_Backups\Stock_Prediction_System2\`）；寫入前後 22 個非留言欄與標籤欄零差異、`stock_prices` 指紋不變（獨立以 PRE 備份拋棄式容器還原比對真實庫重新推導，不只信任腳本自身記憶體結果）。完整證據見 `doc/upgrade/gates/evidence/RISK023_comment_features_write.json`。`DEC-039` → `APPROVED`；`DEC-024` → `SUPERSEDED`；`RISK-023` → `MITIGATED`（並列）。診斷期間發現並登記 **RISK-029**（留言擷取器單次解析產生重複／交錯留言區塊，另案處理，本案內僅加 `suspect` 守衛，不修擷取器）；另發現並獨立排查一項未併入本案的資料一致性小落差（PRE-G3-03 P6 不變式 13 列落差，已定位成因為 `article_id=1495` 的 write-once 凍結，見 Gate A 提案 §1.1）。`doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md` 已 `git mv` 至 `doc/upgrade/gates/closed/`。**待處理，有名字有去處（更新自上一則）**：(1) ~~RISK-023 獨立小案~~ **已完成**；(2) `TwseScraper` 模組去留——PO 另案裁決；(3) 每日 ETL 第一次執行——時點由 PO 決定，另一輪 binding confirmation；(4) RISK-029 根因診斷——另案，未排程；(5) ADR 驗證勾選漂移（8 則 `APPROVED` 卻含未勾項，PO 2026-09-14 裁決併入本案結案 commit）——見下一則。 |
| — | **（本項延續，非新條目）** | **2026-09-14：ADR 驗證勾選漂移登記（PO 裁決併入 RISK-023 收尾 commit）**——PO 發現 `DEC-036` 已 `APPROVED` 但 `Verification` 仍有未勾選項（「SB2a Gate A 待開」，實際 09-10 核准、09-11 結案）。掃描全部 ADR，同型情況共 8 則：`DEC-013`／`016`／`017`（Gate 0，contract-check PASS、Registry 29 欄、universe 三條測試等）、`DEC-033`／`034`（SB6／SB7，流動性窗測試、允許清單測試、K=1 重測、`SUCCESS` 實測）、`DEC-036`（SB2a Gate A）、`DEC-012`／`020`（Streamlit 肉眼確認、真實 artifact）。**根因是制度性的**：§0.5 #10 讓狀態轉換綁 Gate B 事件，但 `Verification` 勾選沒有對應規則；`gate0_contract_check.py` B13 只查停在 `PROPOSED` 的 ADR，不查「`APPROVED` 卻含未勾項」。**處置**：(a) 8 則逐項核對現行 commit／測試後打勾附 hash，測試類若未做則改寫成 `NOT VERIFIED`＋去處；(b) `DOCUMENT_DRIFT_REMEDIATION.md` 登記新 DRIFT；(c) `gate0_contract_check.py` 新增一項機械檢查：`APPROVED` 的 ADR 不得含無標 `NOT VERIFIED` 去處的未勾項，附 known-FAIL（先跑必 FAIL 抓出當時的 8 則，處置後轉 PASS）。**觸發條件：RISK-023 收尾 commit 內或緊鄰的獨立 commit，本案結案前完成**——尚未執行，另見本節下一批 commit。 |
| 17 | **編排測試與 `run_all_daily_tasks` 的契約耦合** —— **判斷法（複查方 2026-09-04）**：「**改動 `run_all_daily_tasks` 的契約時，需不需要編輯不測試 `run_all_daily_tasks` 的檔案？**」**現在的答案是「需要」。修好之後應該是「不需要」。** | **觸發條件：測試基礎設施另案（與 stub 稽核同一家族）**，不擋任何功能，故不在 `UG-G2-SB7` 內做 | **現況**：`tests/test_operational_ux.py` 與 `tests/test_db_read_semantics.py` 各自複製六個 `MagicMock()` 來隔離 `run_all_daily_tasks` 的階段。**`UG-G2-SB7` 一個 SB 之內就觸發了四次**：（1）接線新增批次階段（**表現形式是單元測試對政府單位的服務發出請求**）、（2）新增 run log writer、（3）`run_price_batch` 的回傳契約新增 `outcomes_by_item`、（4）`run_ptt_pipeline` 新增回傳契約（A 輪）。**重點不是「四次」，是「四次都在同一個 SB 內」** —— **那代表該耦合由日常工作觸發，不是罕見事件。**一個 SB 觸發四次的耦合，**不會等到「有空的時候」才出問題**。⚠ **四次全是「回傳契約改變」或「新增階段」，兩者都是正常演進** —— 這正是共用 test double 會解掉、而逐項 mock 不會的那一類。⚠ 順帶：`RunLogEntry` 的 outcome 窮舉**四次都把 mock 的不完整變成響的**，**而它不是為此設計的** —— **窮舉式驗證的價值常常在它原本的目的之外。****「mock 不完整」只是表現形式，耦合才是缺陷** —— 一個測「DB 讀取語意」的檔案，不應該因為 ETL 編排的回傳契約改變而壞掉。**下一次它會用另一種形式出現。** **建議修法**：一份共用的 test double（實作各階段契約）取代兩檔各六個 mock —— 新增階段時只改一個地方；契約改變時**一個地方壞掉，而且立刻壞**，而不是兩個檔案的 mock 各自靜默過期。⚠ **它與 SB7 新增的嚴格檢查是互補品不是替代品**：double 負責「符合契約」，嚴格檢查負責「double 漂移時會響」——本次已證明後者會響（兩個不完整的 mock 立刻被抓到）。⚠ **`autospec` 不夠**：它只管簽章不管回傳值。**Python 沒有便宜的機械檢查能驗證「mock 的回傳值符合被 mock 對象的契約」**，故本項的判準刻意寫成一個**每次改動都能重新問一次的問題**，而不是一個工具。**（2026-09-05，第 5 項追記——第五次，而且這次量得出來）**：改動的是 `run_all_daily_tasks` 的**取數方式**（逐關鍵字搜尋 → 一次看板抓取），**13 個 mock 落點、5 個檔案，實際破 4 個測試、需編輯 2 個檔案**（`test_ptt_failure_is_recorded.py`、`test_operational_ux.py`）。⚠⚠ **值得記的是為什麼另外 9 個沒破**：`test_batch_etl_boundary.py`（4）、`test_db_read_semantics.py`（2）、`test_aa_network_guard.py`（1）等**多 mock 了一層** —— 它們連 `ptt_scraper` 一起換掉，所以接縫由 `run_ptt_pipeline` 移到 `scrape_ptt_board_pages` 時打不到它們。**擋住這次連鎖的是「mock 得更深」，不是「耦合更少」——下一次接縫再往下移一層，它們一樣會破。****那 9 個沒破的測試不是安全的，只是這一次沒被打到**（複查方 2026-09-05：「這是 #17 到目前為止最好的證據」）。⚠ 另一面在 host 上：`tests/test_ptt_board_pages.py` 單獨執行會 `ModuleNotFoundError: tenacity`，而全套 `discover` 會過 —— **因為別的測試檔先塞了 tenacity stub**。**同一個耦合，一邊讓改動打破無關的檔案，一邊讓無關的檔案替改動遮住失敗。** **（2026-09-08 升級，測試 Stub 稽核 Gate B 實測）**：上面那句「host 上」的描述**需要升級**——`tests/test_ptt_comments.py`（非 `test_ptt_board_pages.py`，不同檔案）獨立執行在**容器內**（非 host）同樣撞上 `ImportError: cannot import name 'retry_if_exception' from 'tenacity'`，根因是該檔的 stub guard 只檢查 `sys.modules` 是否已登錄、不像其他檔案先真的 `try/except import`。**`discover` 會過關是匯入順序的偶然結果，不是設計保證**——這不是 host 降級環境獨有的現象，是**任何環境下、只要匯入順序不巧就會發作的結構性缺陷**。詳見 `doc/upgrade/gates/evidence/STUB_AUDIT_result.json` 的 `independent_import_defect_found`。**修復去處（綁事件，不綁排程）**：下一次修改 `tests/test_ptt_comments.py` 或 `src/extractors/ptt_scraper.py` 的任一 SB，一併把 stub guard 改為 `try/except ModuleNotFoundError` 形態，本項不單獨開案搶修。 | **第三次是門檻** —— 兩次可以是巧合，三次是形狀。PM 主動指出「這是同兩個檔案第三次」，**那個計數就是把它從個案變成案由的東西** |
| 18 | **`PRE-G3-04`／D5 建立的 U 語意會在訓練消費端被靜默抹平** | **✅ 已修復（2026-09-12，`UG-G3-SB3` commit `cae860f`，PO 核准）**——`extract_multimodal_features()` 改用 `SENTIMENT_FEATURE_COLS` 判斷跳過 `fillna`，8 欄（含本項原文未提及、同樣落在 `else` 分支的 `article_count`／`bullishness_index`／`agreement_index`／`sentiment_3d_ma`／`sentiment_5d_ma`）一律保留 `NaN`；`rsi_14` 的 `fillna(50.0)` 不動。實際落地的 SB 是 `UG-G3-SB3`，非本項原文登記的 `UG-G3-SB2`（觸發條件登記時的預判與後續 SB 拆分不完全一致，記於此供追溯）。以下為原文，保留供追溯：**觸發條件：`UG-G3-SB2`**（訓練排除邏輯，讀 `daily_ml_features` 的消費端；`PRE_G3_04_D5_GATE_A_PROPOSAL.md` §5 已明確排除本次範圍）。**現況（`PRE-G3-04` 綠 commit `6ecdb50` 複查時發現）**：`src/ml/model_trainer.py:161-169` 的 `MultiModalTrainer.extract_multimodal_features()` 對 `sentiment_mean`／`sentiment_lag_1`／`sentiment_lag_2` 有無條件 `fillna(0.5)`（`rsi_14` 另有 `fillna(50.0)`，其餘欄位 `fillna(0.0)`）——D5 剛在 `feature_aggregator.py` 建立的成因 U（`NULL`）語意，目前會在這個訓練特徵擷取邊界被靜默填回中立值，等同於在消費端重演 D5 剛移除的「把未知填成已知」問題。**本項刻意不在 `PRE-G3-04` 內修**——`extract_multimodal_features()` 是訓練消費端，屬 `UG-G3-SB2` 的範圍，不是特徵聚合端的 NULL 語意本身。 |
| 19 | ~~**測試 Stub 稽核**（第 5 案，`G2_SB7_GATE_B_SUBMISSION.md` §7 項目 5 的「另案」）~~ **一次性動作已收尾（2026-09-08 PO 核准 Gate B）** | **依 §0.5 #12／#14 的切法**（常設標準與一次性動作分開登記）：**(a) 一次性動作**——11 個候選檔案（非文件原記載的「九個」，落差已查明為計算誤植）AS-IS runtime 驗證全數完成，證據見 `doc/upgrade/gates/closed/STUB_AUDIT_GATE_B_SUBMISSION.md`；**(b) 常設規則**（本項不真正關閉，是轉為規則，故劃線但不寫「已解決」）：日後任何 SB 修改這 11 檔中任一檔或其受測模組時，該檔的逐測試裁決比對隨該 SB 一併執行，規則本文留存於 `doc/upgrade/gates/evidence/STUB_AUDIT_result.json` 的 `PO_DECISION_2026_09_08` 節，**不綁排程輪次**（PO 原話：「§0.5 的教訓：綁事件的規則零漏，綁個案的漏了兩次」）；**(c)** 過程中獨立撞見一個既有缺陷（`test_ptt_comments.py` tenacity 假 stub 在容器內獨立執行仍 `ImportError`，非 host 降級環境獨有），已升級記入 §0.5 #17，去處同樣綁事件 |
| 20 | **每日 ETL 執行閘門**（`UG-G3-SB2` routing 真實庫寫入，2026-09-09 PO 裁決） | **✅ 已解除（2026-09-11，`UG-G3-SB2a` Gate B `f479e14` 核准）**——**解除 ≠ 執行**：`run_all_daily_tasks()`／`scheduler.py` 第一次真實執行仍需另一輪 binding confirmation，`UG_G3_SB2a_GATE_B_SUBMISSION.md` §5 的十項觀察清單（原提案六項＋Gate B 執行經驗增補四項：CHAL-010 真實資料迴歸、RISK-027 可預期流失、RISK-028 outcome 檢查、缺口偵測常設化）為必答項；時點由 PO 另行決定，建議排在 RISK-027 獨立小案修復後（避免 `UG-G3-SB3` 的實驗建立在會變的特徵上）。以下為原文，保留供追溯：**觸發條件（解除）：`UG-G3-SB2a` Gate B 通過時**——**綁事件，不綁排程輪次**。**成因**：`entity_mapping` 路由補齊 457 筆後，`fetch_active_stock_targets()` 追蹤宇宙由 4 檔變 8 檔（新增 `2059`／`2454`／`3008`／`8069`），其中 3 檔（TWSE）下次每日 ETL（`run_all_daily_tasks`）會經 `run_twse_pipeline` 日常路徑（未還原基準）寫入 `stock_prices`，搶在 `UG-G3-SB2a` 的價格基準政策定案之前，見 RISK-022（四）、`doc/evidence/CHALLENGES.md` CHAL-009。**現況**：`scheduler.py` 本未在執行（app 容器無該程序），故本閘門現階段成本為零，防的是往後任何手動或排程觸發。**解除條件**：`UG-G3-SB2a` Gate B 通過（價格基準政策定案）。**本項不擋** `UG-G3-SB2` 的掛點啟用（`run_triple_barrier_tail_recompute()` 接線）本身——啟用只是把函式定義接上呼叫點，閘門管的是 `run_all_daily_tasks()` 整體是否被執行，兩者是不同層級的動作。**【2026-09-16 追加，`UG-G3-SB7` 結案裁決⑧】首次執行的觸發條件加一項：同次執行完成 `RISK-005` 150 檔 ETL 計時，結果回填 `doc/upgrade/contracts/REMAINING_RISKS.md`（該檔已改綁本項，見 `RISK-005` 應對措施欄）——不再另安排唯讀計時，這次執行本身就是對 150 檔的真實計時。** **【2026-09-17 追加】首次真實執行已嘗試（2026-09-17 00:41 台北，依 PO 條件式綁定授權自動觸發，PTT 兩次探測皆 200，前置步驟全數通過），於 NLP 情緒運算階段因 Gemini 免費層級**每日**配額（`GenerateRequestsPerDayPerProjectPerModel-FreeTier`，limit 20）耗盡、5 次重試後仍 429，`ResourceExhausted` 中止（TEAM_PLAYBOOK A12 適用：已停止、未重跑、未修正程式碼）。**真實庫現處於「股價／候選池已補到 09-16、`daily_ml_features` 仍停在 09-04、10 篇新文章尚未評分」的中間狀態——這是預期中可由下一次乾淨執行自然接上的過渡狀態，任何人不得手動補跑單一階段（NLP／特徵工程／尾端掛點）去「湊齊」它。** PRE 備份 `stock_prediction_system2_PRE_first_daily_etl_20260917_002832.dump`、POST 備份 `stock_prediction_system2_POST_first_daily_etl_20260917_0107_partial_nlp_quota_failure.dump`（檔名刻意標記 partial，避免誤認成功快照）。完整證據見 `doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_aborted.md`。新登記 **RISK-031**（Gemini 免費層每日配額由 AI 熱門趨勢探索與 NLP 共用、模型別名 `gemini-flash-latest` 未釘版）。**下次真實執行前必修**：`n_new_days` 的計算來源需從「`candidate_prices` 價格缺口」改為「`daily_ml_features` 落後 `stock_prices` 幾個交易日」，否則下次執行會因價格缺口已歸零而把尾端視窗誤算回預設的 6 列，蓋不到這次遺留的 8 天新列（詳見證據文件「零、關鍵發現先講」第 2 項）。 **【2026-09-17 20:04 追加，已執行】** §0.5 #30（n_lag 必修）先完成（`eccab3a`／`7a66153`／`048e975`），段 B 拋棄式庫演練通過後 PO 給 binding confirmation，`run_all_daily_tasks()` **已執行，`exit code 0`，全程無例外，無 Gemini 429**（AI 探索 1 次＋NLP 1 次，共 2 次）。PRE 備份 `stock_prediction_system2_PRE_first_daily_etl_20260917_1948.dump`、POST 備份 `stock_prediction_system2_POST_first_daily_etl_20260917_2009.dump`。真實庫最終狀態：`stock_prices`＝`daily_ml_features`＝449,326 列，兩表 `MAX(trade_date)` 皆 `2026-09-16`（特徵表落後歸零）；10 篇待評分文章全數完成評分（`market_articles` 未評分數 10→0）；`sentiment_cache` 36→42；`theme_stock_mapping` 53→63（AI 探索本次新增 10 筆，3 個新題材：高頻寬記憶體(HBM)／銅箔基板(CCL)／營建營造）；啟用關鍵字 28→31。**兩輪真實庫異動的完整記錄**（之前只記了股價／文章，本次補登映射與關鍵字）：前一次中止真跑（09-17 00:45 台北）**唯讀查證 `theme_stock_mapping.updated_at` 後實際為 12 筆**（記憶體 4／AI伺服器與運算 4／蘋果供應鏈 4，2 個新關鍵字：AI伺服器與運算、蘋果供應鏈——`VERIFIED THIS SESSION`，複核訊息原文載明 10 筆，經 SQL 逐列核對更正為 12 筆，與 aborted 證據文件既有記載一致）；本次真跑（09-17 20:05 台北）10 筆（見上）。兩輪加總 22 筆映射、5 個新關鍵字，加上此前既有 41 筆，累計 63 筆與 `theme_stock_mapping` 現況逐位相符。四條驗收條件（PO 訂正後版本）全數 PASS。完整證據見 `doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success.md`。**本閘門項目結案**——首次每日 ETL 真實執行已完成，往後執行不再需要本項的一次性 binding confirmation 程序，改依常態排程/手動觸發的既有規範（§0.5 #31／#32／雙時點排程等候補案仍照原順序進行，本次不動）。 |
| — | **（本項延續，非新條目）** | **2026-09-10 進度**：`UG-G3-SB2a` 方案 B（TWSE 逐股路徑改走 `candidate_prices` 複製，`138bfc8`）已實作完成；段 1（`stock_prices` ← `candidate_prices` 回補）已完成真實庫寫入——441,922 列新增、445,635 列總數、458 檔皆補齊且逐股列數核對通過，`postgres`@`localhost:5432`，`961b69f` 版本腳本，binding confirmation 由 PO 核准（RISK-013 三項協議全數執行，含拋棄式容器還原驗證）。PRE 備份 `stock_prediction_system2_PRE_g3_sb2a_stock_prices_20260910_231049.dump`、POST 備份 `stock_prediction_system2_POST_g3_sb2a_stock_prices_20260910_231920.dump`（`D:\Python\Database_Backups\Stock_Prediction_System2\`），完整證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage1_real_db_write.json`。**本閘門解除條件不變**（`UG-G3-SB2a` **Gate B** 通過，非段 1 完成）——段 2（既有 3 檔基線比對＋458 檔特徵計算）、段 3（Triple-Barrier 標籤回補）尚未執行。 |
| — | **（本項延續，非新條目）** | **2026-09-11 進度**：段 2 既有 3 檔（實為 4 檔，含 NVDA）基線比對期間發現 `candidate_prices` 於 2026-08-24～09-02 共 8 個交易日全市場（TWSE＋TPEX）零列——非休市日（WebSearch 交叉核對 TWSE 官方休市日期表），為真實資料缺口（成因：`UG-G2-SB9` 一次性回補停在 08-21、`UG-G2-SB7` 每日批次 09-03 才開始，中間無銜接機制，待對 SB9 證據確認）。經三輪 binding confirmation 執行 `scripts/verify/ug_g3_sb2a_backfill_candidate_prices_gap.py`（`e37455d`）完整補齊 8 天（`candidate_prices` 1,825,814→1,841,594），過程中發現並登記 **RISK-028**（TPEX 端間歇性 SSL 憑證驗證失敗）；隨後重跑段 1 腳本補齊 `stock_prices` 對應的 8 天（445,635→449,263，`961b69f` 版本未改）；基線比對腳本因此發現並修正 **RISK-027**（`feature_aggregator.py` 交易日曆跨市場聯集導致文章流失）、並改版區分「孤兒列」與「段 2 尚未執行的新鍵」語意（`c54246c`），對修正後資料重跑：20 個新鍵恰好等於預期集合，25 個比對欄位的 88 筆差異全數落在允許範圍（既有 3 檔台股、日期 >= 2026-08-21），PASS。完整證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_gap_and_baseline.json`。**閘門解除條件仍不變**（`UG-G3-SB2a` Gate B 通過）——段 2 寫入腳本（458 檔特徵回補）、段 3（Triple-Barrier 標籤回補）尚未執行。 |
| — | **（本項延續，非新條目）** | **2026-09-11 進度：段 2 寫入腳本（458＋NVDA 檔特徵回補）已完成真實庫寫入**。設計核准後，審查員 dry-run（拋棄式庫）期間發現兩處缺陷並要求併入修正：(1) `_values_differ` 對 `psycopg2` 原生 `decimal.Decimal` 型別漏接、落到字串比較，極小值會誤判為差異；(2) 唯讀預覽補上「常數過期守衛」（真實庫現況與 `EXISTING_ROWS_BEFORE`／`EXPECTED_LABEL_COUNTS` 不符即拒絕執行）與「記憶體不變式先跑一次」（7 項不變式在寫入前就對計算結果驗證，不必等寫完才發現算錯）。兩處修正＋腳本＋測試（35 個，含批次切分、批次失敗即停、標籤計數回歸偵測、預覽零寫入、常數過期守衛、預覽不變式守衛，皆附 known-FAIL 案例）commit `49aef94`，審查員複核通過。binding confirmation 執行結果：PRE 備份 `stock_prediction_system2_PRE_g3_sb2a_features_20260911_103413.dump`（還原驗證：`daily_ml_features` 3,713／3,529／184、`stock_prices` 449,263，PASS）；10 批全 OK（49,636～49,285 列／批，末批 9 檔 8,691 列，總計新增 445,550 列、更新 3,713 列）；段級核對 5 項（腳本自身回報）與獨立重查 6 項（本次寫入完成後另用 SQL 直接查真實庫核對，不只信任腳本回報）皆 PASS：總列數 449,263；標籤 3,529／184；`stock_prices` md5 寫入前後完全相同（`ce23c629a461359689cb63f53fd7573d`，證明段 2 未觸及 `stock_prices`）；459 檔逐股列數 `daily_ml_features`=`stock_prices` 全對（0 不符）；455 檔新股標籤全 NULL（0 違規）；既有 4 檔 3,713 列的標籤兩欄 md5 寫入前後完全相同（`b3719c82231acf82fd0ca94e0baa6660`，另用拋棄式容器重新還原 PRE 備份獨立算出同一個值比對，非同一份記憶體狀態）。POST 備份 `stock_prediction_system2_POST_g3_sb2a_features_20260911_110211.dump`。**誠實揭露（關聯 RISK-015）**：`sentiment_mean` 全表 NULL 佔比 0.998（`source_status` 分布 `SUCCESS_EMPTY` 448,490／`SUCCESS` 773）——多數股票多數交易日無社群文章討論，情緒特徵稀疏是現況，不是本次寫入造成的缺陷。完整證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_features_write.json`。**對段 3 的交接**：既有 2330／2382／6488 在 2026-08-21 之後（涵蓋缺口回補窗口）的既有標籤已因缺口回補過期，段 3 須對 458 檔全部重算，不是只補 455 檔新股。**閘門解除條件仍不變**（`UG-G3-SB2a` Gate B 通過）——段 3（Triple-Barrier 標籤回補）尚未執行。 |
| — | **（本項延續，非新條目）** | **2026-09-11 進度：段 3（458＋NVDA 檔 Triple-Barrier 標籤重算）已完成真實庫寫入——`UG-G3-SB2a` 三段全部完成**。設計核准含一項必改（重建段 1 回補前序列改用 `stock_prices.created_at` 判斷，不硬寫日期清單）與四項補充（互補集合檢查、SB1 三道檢查改分批寫法、80 列 NULL 對照、RISK-025 揭露）。審查員自行對真實庫跑唯讀預覽＋拋棄式庫 dry-run 複核，要求第二輪收緊：既有 3 檔差異改用「相等」（非僅子集）當 PASS 條件、段級輸出補標籤分布與算術對帳。腳本＋測試（30 個，含合成缺口 known-FAIL、NVDA 零差異對照組、相等斷言收緊的 known-FAIL）commit `837a0c0`，審查員複核通過。binding confirmation 執行結果：PRE 備份 `stock_prediction_system2_PRE_g3_sb2a_labels_20260911_140624.dump`（還原驗證 PASS）；10 批全 OK；段級核對（腳本自身回報）與獨立重查（另用拋棄式容器重新還原 PRE 備份取得寫入前原始值，逐列比對，不只信任腳本回報）皆 PASS：總列數 449,263 不變；標籤計數 410,443／38,820；一致性 0 違規；25 個特徵欄 md5 寫入前後完全相同（`c48c0167c7a3ae9bbaa9f15ec349cc1d`，證明段 3 只動標籤兩欄）；`stock_prices` md5 未變；NVDA 標籤 md5 寫入前後完全相同（`1ee746dddbbf66cf2eb48e265fc03c1d`，對照組驗證通過）；既有 3 檔（2330/2382/6488）25 個變動鍵逐列列出前值→後值，精確符合機制推導（2330／2382 各 7、6488 11）。POST 備份 `stock_prediction_system2_POST_g3_sb2a_labels_20260911_141614.dump`。**誠實揭露（SB3 D3 裁決輸入）**：標籤分布 `-1`226,956／`+1`162,288／`0`21,199／`ambiguous_dual_barrier`36,388（8.1%，偏高）／`insufficient_data`1,892／`no_entry`540；`-1:+1`≈1.4:1 明顯偏空；RISK-025：337/459 檔 Timeout 佔比 <5%（只揭露不把關）。完整證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage3_labels_write.json`。**`FEATURE_REGISTRY.md` #6／#29 已同步更新**（3,713 列→449,263 列）。**閘門解除條件仍不變**（`UG-G3-SB2a` **Gate B** 通過）——§0.5 #20 維持到 Gate B 正式核准；下一步為 Gate B 送審（含 RISK-027／028 揭露、`TwseScraper` 模組去留裁決、RISK-025 分布、閘門 #20 解除條件檢核）。 |
| — | **（本項延續，非新條目）** | **2026-09-11：`UG-G3-SB2a` Gate B 核准結案（`f479e14`，PO 核准）**——三段真實庫寫入、五次 RISK-013 協議全數完成，§0.5 #20 已解除（見上）。`doc/upgrade/gates/UG_G3_SB2a_GATE_A_PROPOSAL.md`／`UG_G3_SB2a_GATE_B_SUBMISSION.md` 已 `git mv` 至 `doc/upgrade/gates/closed/`（`gates/` 根層現只剩 `GATE3_STARTUP_APPLICATION.md`）；`SYSTEM_UPGRADE_MASTER_PLAN.md` §9 SB2a Brief 補狀態區塊。**結案後待處理，有名字有去處**：(1) **RISK-027 獨立小案**——走 `bug-fix-protocol`（診斷→核准→實作→回歸），修好後段 2／段 3 各重跑一次（約 1 分鐘，仍走 RISK-013），**建議排在 `UG-G3-SB3` Gate A 之前**，避免 SB3 的實驗建立在會變的特徵上；(2) **`TwseScraper` 模組去留**（保留供未來單檔回補使用／移除）——PO 另案裁決；(3) 每日 ETL 第一次執行——見上方 #20，時點由 PO 決定；(4) `UG-G3-SB3` Gate A 提案——下一個 SB。 |
| — | **（本項延續，非新條目）** | **2026-09-12：RISK-027 獨立小案已完成，含段 2 重跑真實庫寫入**——`bug-fix-protocol` 走完診斷（Step 1，唯讀）→ Gate A（PO 裁決採方案 B，候選方案 C 前提經真實庫唯讀查證推翻）→ 紅測（`0da87d9`，4/4 FAIL）→ 實作（`e21d3c6`，`assign_trading_days_per_stock()`，4/4 GREEN，全套 696/696，contract-check 13/13）→ Gate B（PO／審查方複核通過）。段 2 重跑改為「只更新差異鍵」（非全表 upsert，理由見 DEC-037）：腳本＋測試（`2962f64`，28 項）機械算出「舊版 vs 新版」預期影響集，與「新版 vs 現有庫」實際差異集斷言相等（**132 鍵、14 檔股票**：2330/2344/2408/5289/2454/NVDA/2382/2317/3008/3081/3163/3363/6442/6669）後，依 RISK-013 三步驟協議對 `postgres`@`localhost:5432` 完成寫入。commit 前後核對與審查方獨立三份狀態（真實庫／PRE 還原／POST 還原）逐列雜湊比對全數通過。PRE 備份 `stock_prediction_system2_PRE_g3_sb2a_stage2_rerun_risk027_20260912_120202.dump`、POST 備份 `stock_prediction_system2_POST_g3_sb2a_stage2_rerun_risk027_20260912_121252.dump`（`D:\Python\Database_Backups\Stock_Prediction_System2\`）。**留言三欄（`comment_volume_ratio`／`comment_polarization`／`net_push_momentum`）全部 132 鍵新舊值皆為 NaN**——真實資料的留言全因 DEC-024 時點過濾不通過，留言路徑的修復僅由合成測試證明。段 3（Triple-Barrier）為純價格計算不受影響，未重跑。`DEC-037` → `APPROVED`（PO 2026-09-12）。完整證據見 `doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_rerun_risk027.json`。**待處理，有名字有去處（更新自上一則）**：(1) ~~RISK-027 獨立小案~~ **已完成**；(2) `TwseScraper` 模組去留——PO 另案裁決；(3) 每日 ETL 第一次執行——時點由 PO 決定，另一輪 binding confirmation；(4) `UG-G3-SB3` Gate A 提案——下一個 SB，必答 RISK-025 D3 處置、rolling vs expanding、embargo、`sentiment_mean` NULL 0.998（RISK-015）、面板凍結時點。 |
| 21 | **Gate 2 tournament 的 `LR × MultiModal` 組，自 §0.5 #18 修復（`cae860f`）起依設計失效** | **觸發條件：`UG-G3-SB7`（Benchmark 重建時依 Gate 3 §5 重定義）**——**綁事件，不綁排程輪次**。**成因**：`MLEvaluator.evaluate_tournament()`（`scripts/generate_tournament_artifact.py` 使用）固定跑 4 模型 × 2 特徵集 = 8 組，其中 `logistic_regression × MultiModalTrainer` 這組在 #18 修復（情緒欄保留 `NaN`，不再填補）後會收到 NaN 特徵；真實面板 `sentiment_mean` 99.8% NULL，這組在真實資料上必定觸發（已於 `UG-G3-SB3` 加 fail-fast，`train_and_predict_fold()` 對登記於 `NAN_INTOLERANT_MODELS` 的模型—目前僅 `logistic_regression`—於特徵含 NaN 時拋帶脈絡的 `ValueError`，取代 sklearn 原生不含脈絡的錯誤訊息）。**這不是回歸，是設計的自然後果**：Gate 3 §5（D3 對照實驗設計，`GATE3_STARTUP_APPLICATION.md`）已裁定 LogisticRegression 只配對照臂 A（無情緒）特徵、不得為它插補情緒欄——`generate_tournament_artifact.py` 的 8 組全配對從未依此區分特徵集與模型的相容性，這組實驗依設計本來就不該存在。**現況**：`generate_tournament_artifact.py` 尚未在真實面板上執行過（沿用舊版無 NaN 合成資料的既有測試全線 PASS，看不出問題，`744/744` 綠燈不代表這組在真實資料上能跑）。**解除條件**：`UG-G3-SB7` 依 Gate 3 §5 重新定義 Benchmark 的模型×特徵集配對（LR 僅配對照臂 A），或明確決定保留／移除 tournament 這個 8 組全配對格式。**不另立 RISK**（PM 判斷，非風險——它是已知的設計後果而非未預期的缺陷，登記於此已足夠追蹤）。 |
| 22 | **Meta-Learner 幾乎未從 OOF 學到訊號**（`UG-G3-SB4` Gate B §3(d)，2026-09-15，`INFERENCE`） | **觸發條件：`UG-G3-SB5` Gate A 提案階段**——**綁事件，不綁排程輪次**。`UG-G3-SB4` 全量執行後，Meta-Eval 段實測顯示 up_down 的 `Meta(A)-LogisticRegression`／`Meta(A)-RidgeClassifier`（macro F1 0.381／0.381）皆系統性劣於單一最佳 Specialist（lgbm，0.465），少數類 recall 僅 0.047 對 0.234。PM 獨立重現審查方觀察：標準化後 8 個 OOF 機率欄的 LR 係數絕對值全 <0.05（實測最大 0.0396），`predict_proba` 在 Meta-Eval 段的 class-1 機率 73%（13,140/17,949）緊縮於 (0.45,0.55) 窄帶。三項候選成因與各自去處（PO 2026-09-15 裁決，不在 SB4 內處理）：**(a)** 類別不平衡未加權——探測顯示 Meta-Train 段 up_down 類別平衡（53.46%/46.54%），對 up_down 支持較弱，驗證方式（`class_weight="balanced"` 重 fit）**歸 `UG-G3-SB5` Gate A 必答項**；**(b)** `argmax` 硬門檻對 SB6 前的評估不利——探測支持較強（機率分布緊縮），驗證方式（precision-recall 曲線／不同門檻下的 recall）**歸 `UG-G3-SB5` Gate A 必答項**（決定校準對象是哪個 Meta-Learner 前必須先回答）；**(c)** Specialist 之間高度相關——探測顯示 4 個 Specialist 的 class-1 OOF 機率兩兩相關 0.61～0.93（lgbm-xgb 最高 0.93），支持較強，驗證方式（VIF／降維後重 fit）**歸 `UG-G3-SB5` Gate A 必答項**；信心門檻／軟門控本身**歸 `UG-G3-SB6`**。完整探測數字見 `doc/upgrade/gates/closed/UG_G3_SB4_GATE_B_SUBMISSION.md` §3(d)；`RISK-009` 同步更新殘餘風險量化（欠擬合，非傳統過擬合）。 |
| 23 | **`src/ml/evaluator.py` 未依 Gate A 規劃擴充**（`UG-G3-SB4` Gate B §7，2026-09-15） | **觸發條件（2026-09-16 更新，原文保留於下）：`UG-Gate-4` 啟動前**——**綁事件，不綁排程輪次**。`UG-G3-SB7` Gate A v2 §3.8 已裁決：`evaluator.py`／`predictor.py` 的 gating 決策整合移交 Gate-4 或獨立候補案，不併入 `UG-G3-SB7`（決定如何接入與驗證 Holdout 上是否成立是兩件不同性質的工作，後者才是 SB7 的任務）。**原文（2026-09-15）**：`UG-G3-SB4` Gate A §5 In Scope 第 5 項原列「`src/ml/evaluator.py`：擴充消費 `y_proba` 的評估路徑」（視需要擴充的條件式規劃），**實際實作未觸及此檔**：段級報告的評估邏輯（`select_best_specialist`、per-class 指標、Meta-Learner 訓練/評估）全部寫在獨立腳本 `scripts/verify/ug_g3_sb4_meta_learner_report.py` 內，未經過 `evaluator.py` 共用模組。**不構成違反 Gate A 範圍**（原文為條件式），登記為後續小案：是否需要回頭統一評估路徑，留待 `UG-G3-SB7` Benchmark 的評估需求明確後一併決定，不在 `UG-G3-SB4`～`SB6` 範圍內處理。 |
| — | **（本項延續，非新條目，回應 #22）** | **2026-09-15：`UG-G3-SB5` Gate A 對 (a)(b)(c) 三項候選成因的真實驗證結果**（Meta-Train 內部切分：`calib_fit`=折 0-20 擬合、`calib_val`=折 21-26 驗證，未動 Meta-Eval，`VERIFIED THIS SESSION`）：**(a)** `class_weight="balanced"` 重 fit——recall(0) 0.8577→0.5465、recall(1) **0.2020→0.5170**、macro F1 **0.4866→0.5313**（+0.0447），**強力支持**（比 #22 原文「探測數字不支持」的粗判更明確）；**(b)** 門檻曲線——預設 0.50 門檻僅 3,026/17,850 列判正類（recall 0.202），降至 0.45 達 13,799 列（recall 0.797／precision 0.470，僅略高於基期 0.456），**中等偏強支持**；**(c)** VIF（自我發現並訂正一次量測錯誤：`_A_p0`／`_A_p1` 兩欄同時納入必然全部 `inf`，因二分類 `p0=1-p1` 恆等式與 Specialist 共線無關，已改只取 4 個 `_A_p1` 欄＋2 regime 欄）——`lgbm_A_p1`=7.15、`xgb_A_p1`=7.00（皆 >5 常用門檻）、`rf_A_p1`=4.31、`lr_A_p1`=1.82，**中等支持**，與 #22 原文的兩兩相關 0.61～0.93（lgbm-xgb 最高 0.93）一致。**PO 裁決（2026-09-15）：(a)(c) 不在 `UG-G3-SB5` 內處理，不重訓 Meta-Learner**（重訓屬 Meta-Learner 訓練方式變更，超出「校準既有模型」的 SB5 範圍）。**觸發條件（最終版，取代 #22 原文「歸 SB5 必答項」）**：`UG-G3-SB6` 門檻選定後，若少數類 recall 仍明顯低於 (a) 探測到的水準（`class_weight="balanced"` 的 recall(1)=0.517），開獨立候補案（暫名 `SB4a`）重訓 Meta-Learner；否則視為已由 SB6 門檻工作回收，關閉此觀察。**理由**：(b) 已證明原始分數確有排序訊號，`class_weight` 的效果本質接近移動決策切點，`UG-G3-SB6` 的門檻選擇工作可以回收這個效果，不一定需要重訓模型。完整數字見 `doc/upgrade/gates/UG_G3_SB5_GATE_A_PROPOSAL.md` §2.3。 |
| — | **（本項延續，非新條目，回應 #22，2026-09-15 追加）** | **`RISK-030` 登記後，上列觸發條件的前提本身需要重新檢視**——`UG-G3-SB5` 段級報告腳本開發期間發現（`RISK-030`，`PROJECT_STATUS.md` 本節與 `REMAINING_RISKS.md` 並列登記）：`target_up_down` 的近零排序訊號**不是 Meta-Learner 訓練方式的問題，是四個 Specialist 的 OOF 輸入本身在折 27-32 就已經沒有可偵測的排序訊號**（Meta-Train 段 AUC 僅 0.515～0.526，`Calib-fit`／`Calib-eval` 更低至 0.492～0.510）。**這代表 (a)(c) 觸發條件裡「重訓 Meta-Learner（`SB4a`）」這個候選解法的前提可能不成立**——若 Specialist 層級本身就沒有訊號可堆疊，改變 Meta-Learner 的訓練方式（`class_weight`、降低共線）不會產生輸入端不存在的訊號。`UG-G3-SB6` 門檻選定後若少數類 recall 仍偏低，需要的判斷可能不是「開 `SB4a` 重訓」，而是「`RISK-030` 去處欄位所述：SB5 Gate B 裁決是否把 Gate 3 後續主線改為 `target_triple_barrier`／Timeout，或重開特徵層面的案」——兩條路徑分岔的依據，觸發後應優先參照 `RISK-030` 而非本項單獨重新評估。**（2026-09-15 稍後已裁決，見 `DEC-041`：Gate 3 主線改以 `target_triple_barrier`／Timeout 為對象；`UG-G3-SB6` 對 `target_up_down` 停做）** |
| — | **（本項延續，非新條目）** | **2026-09-14／15：`UG-G3-SB4` Gate A 三輪核准過程與紅測、實作進度登記**——RISK-023 結案後開啟 `UG-G3-SB4`（OOF Stacking Meta-Learner）Gate A 提案。v1 退回：誤把已核准的 Gate 3 Holdout 規格（`PURGED_WALK_FORWARD_SPEC.md` §3.3）當成本 SB 自由裁量選項，漏答「OOF 覆蓋哪些 target × mode」。v2 訂正：三層結構（Holdout＝折 33～42、Meta-Train＝折 0～26、Meta-Eval＝折 27～32，對 `UG-G3-SB3` 凍結面板重跑 `WalkForwardSplitter` 實測邊界，`VERIFIED THIS SESSION`）＋二階 Purge＋Data Contract，但審查方獨立查證發現折 0～32 內 `sentiment_mean` 非 NULL＝**0**（SB3 全部情緒訊號集中於 2026-01-19 之後、全數落在 Holdout），讓「Arm B 納入」的裁決失效。v3 改判：**只用 Arm A**（4 組 OOF：LR／RF／LightGBM／XGBoost），段級報告並列 `Meta(A)` 與 `Best Single Specialist`（選法：Meta-Train 段排序選出、只在 Meta-Eval 段報告，避免選擇偏誤），Arm B 貢獻登記為 RISK-015 後續驗證項。**Gate A 核准**（PO 2026-09-14，`be64f9b`），核准時追加三點：選法排序指標固定為模組常數＋報告完整排名（非僅第一名）、`split_segment` 新增第三值 `purged`（二階 Purge 排除的列保留可查核）、`LogisticRegression`／`RidgeClassifier` 只並列不互相淘汰（避免污染 `UG-G3-SB5` 的校準集）。紅測 `e46a8a7`（35 項，全 RED，既有 843 個測試零受影響）→ 審查方複核發現盲點：二階 Purge 的測試夾具全是純 `meta_train`，未測混入真正 `meta_eval` 列的情境，一個不檢查 `split_segment` 的實作會把整個 Meta-Eval 段誤標為 `purged` 卻仍全數通過原有測試（`CLAUDE.md` §9A.1）→ amended-red `69f6e35`（+4 項，含盲點修補與三個專屬例外類別互不繼承的檢查，39 項）。**實作階段（GREEN）自我反查法追加發現並訂正**：(a) `ProbabilityAlignmentTests` 只測 `fit_predict_specialist_fold()` 本身，未涵蓋 `assemble_oof_matrix()` 的機率欄索引對齊，且既有 known-FAIL 用對稱機率值（0.5/0.5）測不出索引錯位——已補 `test_assemble_oof_matrix_probability_values_align_with_declared_classes`（不對稱值 0.3/0.7）；(b) `iter_oof_folds()` 的 Holdout 半折洩漏測試原本用任意天數偏移構造邊界，湊巧沒有任何折真的跨界，突變體因此僥倖通過——已補 `test_straddling_fold_is_excluded_entirely`（用真實折邊界精確算出邊界落在某折測試窗中點）；(c) 發現並訂正 `NanExclusionInMetaLearnerInputTests` 夾具本身的錯誤（兩個「不同欄各自 NaN」的案例被誤植在同一列索引，非實作缺陷）。四項突變體驗證（purge 不看 segment、機率欄序調換、Holdout 半折放行、`purged` 列進訓練）於實作完成後逐一構造並確認皆被正確攔截，全數還原。41 項測試全綠，容器內全套 884 個測試 `OK`，`gate0_contract_check.py` 14/14 PASS。新 ADR `DEC-040`（Gate 3 Holdout 邊界落地）狀態 `PROPOSED`，隨本 SB Gate B 一併請 PO 核准。**待處理，有名字有去處**：(1) OOF 產生腳本與段級報告腳本（實作下一段，另行送審）；(2) 腳本層守衛（真實面板 150／750 二階 Purge 迴歸基準、折 27／33 起日等於常數、面板 sha256）在該段落實；(3) RISK-015 後續驗證項（Arm B 對堆疊的貢獻，待資料源擴充後另案評估）。 |
| — | **（本項延續，非新條目）** | **2026-09-15：OOF 產生腳本／段級報告腳本第三輪訂正、全量執行、Gate B 核准結案**——審查方對真實凍結面板重算發現三個正確性問題：守衛 4/5 常數誤用面板原始列數（應為 `prepare_fold_data()` 規則(a)(b)後的保留列數，TB purge 750 應訂正為 680）、訓練迴圈手寫等義邏輯繞過 `iter_oof_folds()` 的紅測保護、`build_long_format_for_selection()` 的 `argmax` 未排除 NaN 機率列 → 紅測 `e9ac8da` → 修正 `c328805`（三項訂正＋`build_meta_learner_input()` 新增 `return_retained_index` 契約擴張 P8，取代呼叫端獨立重算遮罩）。**全量執行**（folds 0-32，兩個 target，容器內）：`target_up_down` 33 折 22.10s，`row_counts {total:98917, meta_train:80818, meta_eval:17949, purged:150}`；`target_triple_barrier` 33 折 31.83s，`row_counts {total:91124, meta_train:73714, meta_eval:16730, purged:680}`；六項 OOF 守衛與四項報告守衛（兩個 target）皆全數 PASS，證據 commit `3ba80b6`（4 份 JSON，body 含兩份 OOF parquet 路徑與 sha256，parquet 不進版控）。**TB 額外發現**：類別定義域為 `{-1,0,1}` 三類（12 個機率欄，非 up_down 的 8 欄），12 欄全數 0 個 NaN——33 折 × 4 模型 × 3 類別逐一檢查，無任何一折任何模型缺席任何類別，與 PO 原先「本 target 會有缺席類別 NaN」的預期不符，如實回報並附工程判斷（60 天訓練窗池化約 150 檔股票，Timeout 類別雖單股稀有但池化後單折仍有數十至數百筆）。**段級報告**：`ranking_df` 選中 up_down=lgbm（Meta-Train macro F1 0.4894）、TB=lr（0.3961）；Meta-Eval 四者並列（Majority／Meta(A)-LR／Meta(A)-Ridge／Best Single）數字並列不下結論。**Gate B 草稿**（`doc/upgrade/gates/UG_G3_SB4_GATE_B_SUBMISSION.md`）審查方逐節讀完並獨立重現 §3(d) 探測數字，**內容無需訂正**。**PO 核准（2026-09-15）**：§3(d) 三項候選成因不在 SB4 內處理，分派至 `UG-G3-SB5`／`SB6`（§0.5 #22）；`evaluator.py` 未擴充不構成違規，登記後續小案（§0.5 #23）；`DEC-040` → `APPROVED`；`RISK-009` 採更新文字（欠擬合觀察點）。**`UG-G3-SB4` CLOSED**，下一步 `UG-G3-SB5`（Probability Calibration）Gate A。 |
| 24 | **特徵層面方向預測改進案**（`UG-G3-SB5` Gate B 裁決 (c)，2026-09-15，PO 裁決） | **【2026-09-16 更新】觸發條件已成立**（`UG-G3-SB7` 已於 2026-09-16 CLOSED）；**PO 裁決：現在不開獨立案，評估併入 `UG-Gate-4` 啟動申請書一併規劃**——理由：`UG-Gate-4` 尚未啟動，特徵層面的案需要新資料源（`RISK-015`）與交易目標重新定義，適合在 Gate 4 規劃時一併檢視；原「`UG-G3-SB7` 之後」的觸發條件文字保留於下方供追溯。**（原文，保留供追溯）觸發條件：`UG-G3-SB7` 之後**——**綁事件，不綁排程輪次**。`RISK-030` 確立 `target_up_down` 在折 27-32 對全部 4 個 Specialist 皆無可偵測 OOF 排序訊號（AUC ≈0.50-0.52），且 `DEC-041` 已裁定 `UG-G3-SB6` 起 Gate 3 主線改以 `target_triple_barrier`／Timeout 為 gating 對象、對 `target_up_down` 停做。本項不是「重訓 Meta-Learner」或「換模型」式的解法（§0.5 #22/#23 已排除此路徑前提，見 #22 2026-09-15 追加項），而是**特徵層面**的候補案——現有特徵集本身可能不含足以區分漲跌方向的訊號，需要新特徵（不限於情緒特徵）才可能改變 up_down 的可預測性。**與 `RISK-015` 連動**：`RISK-015`（情緒資料覆蓋率不足，`OBSERVED`）是本案候選解法之一（擴充資料源、提升情緒覆蓋率），但本案範圍不限於情緒特徵，是否還有其他特徵面向待 `UG-G3-SB7` Benchmark 明確後一併規劃。**排序理由**：`UG-G3-SB7`（Benchmark 重建）完成後，才有穩定的比較基準可評估任何新特徵集是否真的改善方向預測力；在此之前開案時機過早。 |
| 25 | **波動率單變數基線待列入 `UG-G3-SB7` 必列比較項**（`UG-G3-SB6` Gate B，2026-09-16，PO 裁決） | **觸發條件：`UG-G3-SB7` Gate A 提案階段**——**綁事件，不綁排程輪次**。`UG-G3-SB6` 的 `regime_diagnostic` 顯示 `θ*` 選出的 gate 集合全部落在低波動三分位組（中、高波動組零列被 gate），代表現行 Timeout gating 在行為上近似「低波動期不交易」。一個**只用 `volatility_20d` 分位數、不訓練任何模型**的規則是否能達到接近的 gating 效果，是尚未回答的問題——若接近，代表整條 Meta-Learner／校準管線對這個具體任務的邊際貢獻有限。`UG-G3-SB7` Gate A 提案必須將此基線與 Timeout gating 並列比較，不得只比較既有的 Always-Up／Majority／Logistic Regression 分類基準。見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md` §3。 |
| 26 | **候補小案：repo 無 `.gitattributes`，容器與 host 對行尾判定不一致**（`UG-G3-SB6` Gate B，2026-09-16，PM 乾跑發現未追蹤檔；審查方複核確認行尾差異為持續性） | **觸發條件：下一次有人在容器內執行依賴 `git status`／`git diff` 判斷工作樹狀態的 git 操作（非只跑既有腳本）**——**綁事件，不綁排程輪次**。host 端 `core.autocrlf=true` 令工作樹以 CRLF 存檔，容器內 git 未設 `core.autocrlf`，對約 48 個既有追蹤檔案造成真實、持續的行尾差異（`touch` 強制重新比對後 `git diff` 顯示整檔逐行變更，`-w` 版本則為空，證實差異僅止於行尾非內容）。是否加 `.gitattributes` 統一行尾規則，另案評估，**不在 `UG-G3-SB6` 處理**；既有報告腳本已用 `-c core.autocrlf=true` 呼叫 git 規避此問題，不受影響。見 `doc/upgrade/gates/closed/UG_G3_SB6_GATE_B_SUBMISSION.md` §7。 |
| — | **（本項延續，非新條目，回應 #25）** | **2026-09-16：`UG-G3-SB7` 對 #25「波動率單變數基線 vs Timeout gating」的最終回答**——Holdout（折 33-42）上，波動率單變數基線（覆蓋率對齊版）與 Timeout gating 表現接近（precision 0.182 vs 0.189、recall 0.822 vs 0.803、lift 10.30 vs 10.73），**如實記錄接近，不下「管線無用」或「管線有效」的結論**。是否簡化為波動率單變數規則，登記為新候補案 #27，去處 Gate 4 啟動前裁決。見 `doc/upgrade/gates/closed/UG_G3_SB7_GATE_B_SUBMISSION.md` §5。 |
| 27 | **候補案：Timeout gating 是否可簡化為波動率單變數規則**（`UG-G3-SB7` Gate B，2026-09-16，回應 #25） | **觸發條件：`UG-Gate-4` 啟動前**——**綁事件，不綁排程輪次**。`UG-G3-SB7` 在 Holdout 上實測波動率單變數基線（覆蓋率對齊版切點 `0.23116970731839864`）與 Timeout gating 三項指標接近（見上方延續列），若正式檢驗確認等效，代表整條 Meta-Learner／校準管線對本任務的邊際貢獻有限，是否簡化為單一規則需要 Gate 4 啟動前正式裁決，本 SB 不代為決定。 |
| 28 | **候補案：交易模擬引擎**（`UG-G3-SB7` Gate A v2 裁決，2026-09-16） | **觸發條件：待排程**——**綁事件，不綁排程輪次**。`Master Plan §11.1` 的「淨累積報酬 >Buy & Hold」與排名基準（Equal Weight Top-K／Random Top-K）依 Gate A v2 裁決列為 Out of Scope——系統目前沒有回測／損益計算模組。若要落地，需要先設計成交規則、多檔股票資金配置邏輯、是否允許放空等，工作量不小，需獨立 Gate A 提案，不與任何既有 SB 綁定時程。 |
| 29 | **候補小案：`ma5_bias_ratio`／`ma20_bias_ratio` 序列中段零值成因未定**（`UG-G3-SB7` Gate B，2026-09-16，PO 對凍結面板重量測發現） | **觸發條件：文件對齊輪之後**——**綁事件，不綁排程輪次**。`RISK-020` 原登記的暖機期填值問題經 `UG-G3-SB7` 結案查證：面板起點早於暖機期視窗，面板內結構上不含任何暖機列，原登記的疑慮不成立；但重量測發現 `ma5_bias_ratio`／`ma20_bias_ratio` 在序列**中段**仍有低比例零值（0.82%／0.33%，全面板），與暖機期無關，成因未定（與當日平盤重合比例 13.9%，非唯一解釋）。`Timeout gating` 唯一依賴的 `volatility_20d` 全面板零填值，本項對 `UG-G3-SB3`～`SB7` 結果無可量測影響，不阻擋任何已完成工作，純粹登記待查。見 `doc/upgrade/contracts/REMAINING_RISKS.md` `RISK-020`。 |
| 30 | **必修案：`n_new_days` 計算來源改為「特徵表落後股價的交易日數」**（首次每日 ETL 真實首跑中止，2026-09-17，PO 對執行後真實庫狀態複核發現） | **✅ CLOSED（2026-09-17，PO 核准，`eccab3a`／`7a66153`／`048e975`）**——~~觸發條件：本案下一次真實執行前~~——**必修，不是候補**。現行 `run_all_daily_tasks()` 從 `candidate_prices` 的價格缺口算 `n_new_days`；2026-09-17 首次真實執行（於 NLP 階段因 `RISK-031` 中止）已把價格／候選池補到 09-16，下次執行時價格缺口會歸零，`n_new_days` 算成 0、尾端掛點視窗退回預設的 `holding_period+1=6` 列——但 `daily_ml_features` 仍停在 09-04，特徵工程屆時要一次為追蹤 8 檔 INSERT 09-05～09-16 共 8 天新列，且既有 08-28～09-04 的 `insufficient_data` 列也需一併重算，6 列蓋不到。改法：特徵階段前取 `daily_ml_features.max(trade_date)`，逐股階段後取 `stock_prices.max(trade_date)`，兩者之間的交易日數才是尾端該覆蓋的新增列數。**需紅測**：用真實庫現在的形狀當 known-FAIL 案例（價格缺口 0、特徵落後 8 天 → `tail_window` 應為 `5+8`，現行程式碼會傳 `None`）。詳見 `doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_aborted.md`「零、關鍵發現先講」第 2 項。**【2026-09-17 追加，已完成】** 紅測 `eccab3a`（含審查方複核 M3 呼叫時機釘住補測 `048e975`）→ 實作 `7a66153`（GREEN）。容器內唯讀執行 `fetch_feature_lag()` 對真實庫確認 F=09-04／P=09-16／n_lag=8，與現在真實庫形狀完全相符。全套測試 1094 OK、contract-check 14/14、numstat/-w 無落差。真實執行已驗證 `tail_window=13` 正確傳入，尾端重算 5,967 列、`n_updated==len(tail)`，見 `FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_success.md`。 |
| 31 | **候補小案：Gemini 用量縮減**（首次每日 ETL 真實首跑中止，2026-09-17，PO 裁決「降低用量」，回應 `RISK-031`） | **✅ CLOSED（2026-09-19，PO 核准，`86ad3b1`／`9536771`／`7861d14`；小修 `63b4419`）**——~~觸發條件：本案第 30 項修好、下次真實執行之前~~——**綁事件，不綁排程輪次**。原三項改動 (a)(b)(c) 與 #33（AI 探索不改既有映射權重）合案處理，見 #33 列的完整記錄；DEC-043 統一記錄兩案的五條決策。 |
| 32 | **成因 F 接線範圍擴大：涵蓋 NLP 未完成，不只 PTT 失敗**（首次每日 ETL 真實首跑中止，2026-09-17，PO 裁決，擴大原登記的「成因 F 接線」小案範圍） | **✅ CLOSED（2026-09-18，PO 核准，`431c2be`／`ee0b384`／`9079915`）**——~~觸發條件：與 #31 同一案，排在本案下次真實執行之前~~——**綁事件，不綁排程輪次**。原登記（2026-09-16，`UG-G3-SB7` 結案裁決⑧脈絡下的拋棄式容器演練發現）只涵蓋「PTT 來源失敗」一種情形；2026-09-17 真實首跑證實 NLP 也可能整批未完成（本次是配額耗盡，5 次重試後中止）。範圍擴大為：PTT 失敗**與** NLP 未完成，兩者都要讓受影響的 `(股票, 交易日)` 在 `daily_ml_features` 記 `source_status=SOURCE_FAILED`，特徵階段才可以在其中任一失敗後安全繼續執行，而不把「來源沒抓到」與「當天真的沒人討論」寫成同一個 `SUCCESS_EMPTY` 值。**【2026-09-18 追加，已完成】** Gate A 提案核准（含起算點 `MIN(batch_key) WHERE source='ptt'`、§3.2a 資格過濾選 A、多關鍵字任一覆蓋語意，皆 PO 裁定）→ 紅測 `431c2be`（11 條，對現行程式碼全數 FAIL/ERROR）→ 實作 `ee0b384`（GREEN，11 條第一次執行即全數 PASS）→ 審查方複核追加子案例 `9079915`（超出交易日曆的 NLP 文章不得崩潰）→ 段 B 拋棄式庫演練（Python／SQL／實際翻轉三方集合逐列相等，47 列；強制 PTT 整日失敗與合成種子列驗證「當日」效果，`FIRST_DAILY_ETL_CAUSE_F_WIRING_rehearsal_20260918.md`）→ 段 C 真實庫首次生效（第二次真實每日 ETL，2026-09-18 14:4x，`exit code 0`，五條驗收全數 PASS，含新增列數精確吻合 8=8、`SOURCE_FAILED` 翻轉列 47=47 逐列相等，`FIRST_DAILY_ETL_CAUSE_F_WIRING_real_run_20260918_success.md`）。PRE 備份 `stock_prediction_system2_PRE_second_daily_etl_20260918_1442.dump`、POST 備份 `stock_prediction_system2_POST_second_daily_etl_20260918_1450.dump`。新 ADR `DEC-042`（Proposed，待 PO 核准戳記）。真實執行期間發現 `RISK-032` 的一個子機制（AI 探索重寫既有映射權重，非僅新增映射，也會觸發全歷史欄位改變，見 `REMAINING_RISKS.md` RISK-032 補充段落與下方新增候補）與 35 篇 `post_time` 在未來的舊文章（年份推斷未回修，見下方新增候補）。 |
| 33 | **候補：AI 探索重寫既有映射權重的影響範圍**（第二次真實每日 ETL，2026-09-18，`RISK-032` 子機制真實案例發現） | **✅ CLOSED（2026-09-19，PO 核准，`86ad3b1`／`9536771`／`7861d14`；小修 `63b4419`）**——~~觸發條件：與 #31 同一案考量，尚未排定優先序~~——與 #31（Gemini 用量縮減）合案處理，理由：兩案都改 `run_all_daily_tasks()` 的 AI 探索段與 `upsert_theme_stock_mapping()`。**裁決結果**：`upsert_theme_stock_mapping()` 改 `ON CONFLICT (theme_keyword, stock_id) DO NOTHING`——既有映射的 `relevance_weight`／`stock_name`／`updated_at` 不再被探索結果覆寫，只有全新配對會被插入（候選方向裡的「只 bump updated_at 不改權重」與「權重變更需 PO 核准」皆未採，選擇最直接的「既有列完全不動」）。Gate A 提案 `GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md` v3（PO 核准）→ 紅測 `86ad3b1`（12 條，10 條自然 FAIL/ERROR、2 條既有行為防回歸鎖定）→ 實作 `9536771`（GREEN，四條決策一併落地，含探索四態回傳修復複核發現的「五個靜默 return」bug）→ 審查方複核 16 項突變 15 中、補測 3b `7861d14` → 段 B 拋棄式庫演練（五場景＋場景 1b 整條管線真跑，`GEMINI_QUOTA_DISCIPLINE_rehearsal_20260918.md`）→ 段 C 真實庫首次生效（第三次真實每日 ETL，2026-09-19 00:26，`exit code 0`，七條驗收全數 PASS，含 `theme_stock_mapping` 66 列執行前後完全相等，`GEMINI_QUOTA_DISCIPLINE_real_run_20260919_success.md`）。PRE 備份 `stock_prediction_system2_PRE_third_daily_etl_20260919_0020.dump`、POST 備份 `stock_prediction_system2_POST_third_daily_etl_20260919_0046.dump`。新 ADR `DEC-043`（APPROVED，PO 2026-09-19 直接核准戳記）。真實執行期間發現兩項附帶事實，登記 §0.5 #35／#36（見下）；另修復一條測試自身未封閉的缺陷（距今天數判準未 patch 系統時鐘，`TEAM_PLAYBOOK.md` A16）。 |
| 34 | **候補：35 篇 `post_time` 在未來的舊文章年份回修**（第二次真實每日 ETL，2026-09-18，PO 複核唯讀查證發現） | **觸發條件：獨立小案，走 `bug-fix-protocol`，未排定優先序**——`market_articles` 有 35 篇文章 `post_time` 落在未來（2026-09-18～2026-12-29），是舊資料的年份推斷結果；現行 `parse_ptt_post_time()` 已改用網址時間戳推年份，但這批文章沒被回修。目前因超出交易日曆被特徵層丟棄（不影響已完成的驗收），但等日期到了會被算進錯的年份。需要真實庫寫入，比照 `bug-fix-protocol` 兩道 Gate 走。 |
| 35 | **候補：`run_us_stock_pipeline` 在美股交易時段內執行會寫入盤中快照**（第三次真實每日 ETL，2026-09-19，PO 複核唯讀查證發現） | **觸發條件：與 08:30 雙時點排程案一併評估，未排定優先序**——`period="3mo"` 呼叫 yfinance 會把「進行中的當日 K 棒」一併回傳；09-19 00:26 台北（美東 09-18 12:26，美股仍在交易中）執行時，NVDA 09-18 的 `close_price`／`volume` 皆為盤中即時值（成交量僅平常六成），非真正收盤價。下次執行的 3 個月視窗會自動覆蓋修正，不需人工介入，驗收條件 1 本來就排除 NVDA 故不受影響——**是深夜執行的固有副作用，不是本次新增的 bug**，之前兩次真實執行皆在美股收盤後未曾現形。候選方向：`run_us_stock_pipeline` 只保留 session 已收盤的 K 棒（丟掉 `trade_date` ≥ 美東當日的列，或改用 `end=` 參數）——08:30 台北時間執行不受此影響（抓的是完整的前一美股交易日），是否繼續允許深夜執行由 PO 另決。見 `GEMINI_QUOTA_DISCIPLINE_real_run_20260919_success.md` §零.0.1。 |
| 36 | **統一兩個 Gemini 呼叫器的暫態例外判斷清單**（第三次真實每日 ETL，2026-09-19，PO 複核唯讀查證發現） | **✅ CLOSED（2026-09-21，PO 裁決：`deadline`／`504` 不列為可重試）**——~~觸發條件：改行為前需獨立評估，未排定優先序~~。原登記：`trend_discover._is_transient_exception()`（`429／quota／rate limit／resourceexhausted／503／timeout`）與 `nlp_processor._is_transient_exception()`（多了 `deadline`／`unavailable`／`connection error`）兩份關鍵字清單真包含關係，且**都缺 `504`**。09-19 真實執行的 `DeadlineExceeded`（504）因此在 `trend_discover` 端未進退避重試、第一次呼叫失敗即直接拋出（本次是好事，省了配額，也是條件 6 PASS 的原因之一，見 DEC-043）。**【2026-09-21 追加，已完成】** Gate A 提案 v1（兩清單合一後補 504）經審查方複核推翻前提：`DeadlineExceeded` 是同一份 payload 重送不會讓伺服器端 deadline 變短，重試只會白燒配額，不列為可重試。v2/v3 改為清單取聯集後**移除 `deadline`、不新增 `504`**，影響面驗證從語料掃描（三種掃法得到 190／127／27 段候選、對應 1／9／8 段互相矛盾的變化數）改為封閉式證明（`OLD=NEW∪{"deadline"}`，500,000 組隨機合成訊息窮舉核對，不一致 0 次）——審查方核准。紅測 `6b0eb37`（6 條，4 條 FAIL/ERROR、2 條防回歸鎖定 PASS，逐條與 docstring 預期吻合）→ GREEN：新建 `src/common/gemini_retry.py`，兩模組改為委派；複核追加測項 1 身分比對（`assertIs`），`/tmp` mirror 構造 known-FAIL 證明舊版 `call_count==2`＋測項 6 聯集仍會放行「共用函式複製回模組、清單改名」的回歸，新增比對正確擋下。新 ADR `DEC-045`（記錄 deadline／504 不可重試的核心論點，狀態 `PROPOSED`，待 PO 核准戳記）。 |
| 37 | **候補案：`target_up_down` 的平盤日歸類與 DEC-018 tie 原則不一致**（2026-09-20，審查方唯讀查證發現） | **觸發條件：`UG-Gate-4` 啟動前，與 #27（Timeout gating 是否可簡化為波動率單變數規則）一併評估**——**綁事件，不綁排程輪次**。`feature_aggregator.py:1064-1065` 的 `target_up_down = 1 if r > 0 else (0 if pd.notna(r) else np.nan)` 把報酬恰為零的平盤日歸類為「跌」；真實庫 `daily_ml_features` 448,729 筆非空 `target_return_1d` 中，漲 211,157（47.06%）、平盤 24,350（**5.43%**）、跌 213,222（47.52%）——真正的漲跌幾乎對半，**多數類的地位完全由那 5.43% 的平盤日決定**（歸 0 則 47.06% 對 52.94%；若歸 1，多數類會翻面成 52.48% 對 47.52%）。`FEATURE_REGISTRY.md` 第 132 列已記載此公式，**不是未記載的實作細節**，缺的是後果分析：這條規則本身決定了「全猜多數類」退化基準的方向、四個模型偏猜跌的程度（`UG_G3_SB3_report_target_up_down_rolling.json` 逐類召回率推估「預測為跌」比例落在 72.6%～75.1%），以及一項標籤雜訊問題——**平盤（沒動）與下跌是不同語意，被併成一類**。`DECISIONS.md` `DEC-018`（APPROVED）對 Triple-Barrier 同日觸雙線的原則是「標記 `NULL` 排除訓練；禁止 forward-fill、補 0、指定方向或任意 tie-breaker」——`target_up_down` 對平盤日做的正是這條原則明文禁止的事（指定方向），同一專案的兩個標籤處置相反，只有三分類遵守了自己訂的原則。上述推論皆為 `INFERENCE`，**不改變 Gate 3 第 9 章任何既有結論**（方向訊號不存在的結論建立在 AUC 上，AUC 不受預測比例影響）。**明確不做**：不改標籤定義（Gate 3 面板已凍結、`panel_sha256` 已記錄於 `UG_G3_SB7_holdout_report.json`，Holdout 已消費完畢無法重測，這是 Gate 4 之後的設計問題）；不重算任何既有證據檔；不自行選定處置方向——三個選項留給 PO 在 Gate 4 啟動前裁決：(a) 維持現狀但補齊文件說明；(b) 平盤改標 `NULL` 排除訓練，與 `DEC-018` 一致；(c) 改為三分類（漲／平／跌）。`data_loader.py:186` 用 `np.where(target_return > 0, 1.0, 0.0)`，與特徵管線定義一致，無兩套定義問題，不用改。交叉引用 `REMAINING_RISKS.md` `RISK-033`。 |
| 38 | **候補案：`FEATURE_REGISTRY.md` 的 Source 欄以行號為錨點，15 處中 14 處已漂移且無機械檢查**（2026-09-20，審查方對 #37 訂正第 132 列後逐列複核全表發現） | **✅ CLOSED（2026-09-20，PO 裁決採方案 (a)）**——~~觸發條件：`UG-Gate-4` 啟動前~~——**綁事件，不綁排程輪次**。`FEATURE_REGISTRY.md` 全部 15 處指向 `feature_aggregator.py` 的 `Source` 欄行號引用，逐列對回原始碼核對（`VERIFIED THIS SESSION`），**14 處指向與該欄位完全無關的程式碼**，僅 #37 剛訂正的第 132 列（`target_up_down`，`L1064-1065`）現在正確。逐列對照——欄位／原引用行號／該行實際內容：`return_1d`／L398-400／處理文章情緒的區塊註解；`rsi_14`／L142-168／`return None`；`volatility_5d`／L171-180／空行；`volatility_20d`／L171-180／空行（與上列同一段錯誤引用）；`article_count`／L333／`vol = return_series.rolling(...)`；`sentiment_mean`／L321-332／`res = pd.Series(rsi, ...)`；`bullishness_index`／L108-119／空行；`agreement_index`／L122-139／「判斷是否超過當日 Cutoff」註解；`sentiment_3d_ma`／L414-415／註解行；`sentiment_5d_ma`／L416-417／「決定 trade_date」註解；`sentiment_lag_1`／L420／`right_on='keyword'`；`sentiment_lag_2`／L421／`how='inner'`；`target_next_close`／L459／`daily_comments = self._aggregate_...`；`target_return_1d`／L462-464／空行。**每一列的證據欄都標著 `VERIFIED`**——此表宣稱「已驗證」，但其追溯指標 93%（14/15）指向錯的地方。**成因**：行號當文件錨點結構上就保證會漂移——`feature_aggregator.py` 任何位置插入程式碼，下方所有引用一起失效，且 `gate0_contract_check.py` 的 B 系列 14 項檢查沒有任何一項驗證 `Source` 欄行號，多久失效都不會被發現（`CLAUDE.md` §9A.1 的情況：一個從來不失敗的檢查與一個不存在的檢查，輸出上無法區分——這裡是後者）。**明確不做**：不逐列修——逐列修只會讓它在下次有人動該檔案時再次全數失效，且因為剛修過，下一個人更不會去懷疑它；**本項不修改 `FEATURE_REGISTRY.md` 任何一列**，包括 #37 已發現、DRIFT-035 註記過的那兩列。**兩個候選方向，不自行選定，留待 PO 裁決**：(a) `Source` 欄行號換成函式名稱錨點（如 `generate_target_labels()`），插入程式碼不會使其失效，另在 contract-check 增一項機械檢查確認每個被引用的函式名在原始碼中存在；(b) 維持行號，但 contract-check 增一項檢查，逐列驗證引用行區間內確實出現該欄位名，不符即 FAIL。**⚠ `FEATURE_REGISTRY.md` 是 `UG-Gate-0` 已核准交付物（`CLAUDE.md` §0.2 第 3 順位），改動 `Source` 欄格式屬規格變更，需要獨立 Gate A 提案與 PO 核准，不是文件維護。** 本案落地後，`DOCUMENT_DRIFT_REMEDIATION.md` `DRIFT-035` 的「另兩列留待下次」註記可一併結清。**【2026-09-20 追加，已完成】** Gate A 提案 v2（審查方複核修訂：第 12 列從巢狀閉包錨點改為外層方法、(B)(C) 組類別方法補 `FeatureAggregator.` 前綴、v1「13→17」加總算術訂正為「5+10+4=19」）核准 → 紅測 `c9ed87d`（新增 `gate0_contract_check.py` B15，對現行文件掃描 4 個既有錨點、0 不合規，PASS——`/tmp` 拋棄式副本 known-FAIL 改名 `compute_rsi` 確認檢查會 FAIL，復原後零殘留）→ 實作：`FEATURE_REGISTRY.md` 19 列 `Source` 欄改為函式／方法名稱錨點（5 列頂層函式、14 列 `FeatureAggregator` 類別方法），GREEN 後 B15 掃描 23 個錨點（4 既有＋19 新改）、0 不合規，`gate0_contract_check.py` Part B 15/15 PASS，全套測試 1117 條無回歸。新 ADR `DEC-044`（記錄「錨點只准指向頂層函式或類別方法，不得指向巢狀函式／閉包／lambda」規則，狀態 `PROPOSED`，待 PO 核准戳記）。`DRIFT-035` 已結清。**複核第三輪補強，見 commit `c79163e`**——審查方發現 B15 原始版本的迴圈結構對「Source 欄整列抽不到任何錨點」的情形零檢查、零違規記錄，PASS 照樣成立（本案整個要防的行號回歸，自己攔不住），補上「提及 `.py` 卻抽不到錨點即 FAIL」規則，對現行文件試算零誤報，`/tmp` 完整 `doc`＋`scripts`＋`src` mirror 內 known-FAIL 確認會正確 FAIL、復原後 PASS，事後整個刪除未觸碰真實 repo；DEC-044 Verification／Remaining Risks 同步新增記錄。 |
| 39 | **候補案：情緒覆蓋率 1.01% 的三層成因，其中一層可零成本改善**（2026-09-21，審查方唯讀查證發現） | **觸發條件：`UG-Gate-4` 啟動前，與 `#27`、`#37` 同批裁決**——**綁事件，不綁排程輪次**。報告 §10.5 與 `RISK-015` 現行僅記載「面板列子集覆蓋率」這一層數字（`article_count>0` 口徑，683/139,585=0.49%，`UG-G3-SB3` 既有量測），未拆解成因；本項獨立唯讀查證出**三層**，其中第一層完全未被記載：<br><br>**第一層：時間（影響最大，全未記載）**——直接讀凍結面板 `panel_target_up_down_20260912.parquet`（`VERIFIED THIS SESSION`，`sentiment_5d_ma notna` 口徑，與 `article_count>0` 口徑不同，見下方訂正）：全期間 139,585 列、訊號列 1,409、覆蓋率 1.01%；**2026-01-01 之前 115,135 列，訊號列 0，覆蓋率 0.00%**；2026-01-01 之後 24,450 列，訊號列 1,409，**覆蓋率 5.76%**。`market_articles`（`VERIFIED THIS SESSION`，`postgres`@`localhost:5432` 唯讀查詢）`MIN(post_time)=2026-01-01`、`MAX(post_time)=2026-12-29`、1,349 篇全數落在 2026 年；`BOARD_PAGE_BUDGET=25`（`ptt_scraper.py:29`）、`BOARD_LOOKBACK_DAYS=2`（`main_etl_pipeline.py:64`）使 PTT 看板模式無法回溯至 2022–2025。**窗內真實覆蓋率 5.76%，約為全期間口徑 1.01% 的六倍**——兩者都低，但成因與可改善性完全不同，不可混用。<br><br>**第二層：關鍵字（459 檔股票的關鍵字已存在，只啟用 8 個）**——`entity_mapping` 462 個關鍵字、涵蓋 459 檔股票（`VERIFIED THIS SESSION`）；`tracking_keywords` 共 32 筆（`core_stock` 5，4 啟用／`theme` 4／`macro` 2／`ai_discovered` 21），其中出現在 `entity_mapping` 的僅 **8 個**（`VERIFIED THIS SESSION`，逐項 SQL 核對）。**關鍵事實**：`ptt_scraper.py::scrape_ptt_board_pages()` 抓一次看板頁面後，在記憶體中以 `for kw in keywords: if kw not in title`（`ptt_scraper.py:266-267`，`VERIFIED THIS SESSION` 逐行核對）逐一比對，**請求數與關鍵字數完全脫鉤**——`UG-G2-SB7` 第 5 項那次重構的目的正是解除這個限制。09-19 真實執行實測：7 頁請求、31 個關鍵字、12 筆命中（`GEMINI_QUOTA_DISCIPLINE_real_run_20260919_log.txt:98-100`，`VERIFIED THIS SESSION`）。<br><br>**第三層：比對方式（只比對標題，內文不參與）**——PTT 個股討論常不在標題寫出股名，即使關鍵字放寬，命中率仍受此上限壓制。<br><br>**架構觀察（比「關鍵字太少」本身更值得記錄）**：`UG-G2-SB7` 把擷取從「每關鍵字各打一次搜尋」改成「抓一次看板、記憶體比對」，請求數因此與關鍵字數脫鉤——**那次優化解除了一個限制，但受該限制驅動的保守關鍵字清單沒有跟著調整**。第二層在架構上是零成本可改善的（多加關鍵字不需要多打任何一次 PTT 請求），第一與第三層則否。**明確不做**：不得啟用 `entity_mapping` 其餘 454 個關鍵字——會改變 `tracking_keywords` 內容，進而改變**未來所有執行**的擷取行為與 `daily_ml_features` 情緒欄，屬資料源擴充決策，Gate 4 範圍，需 PO 裁決；不得修改 `ptt_scraper.py` 比對邏輯（第三層）；不得重算任何面板或既有證據檔（Gate 3 面板已凍結，`panel_sha256` 已記錄）；不自行選定處置方向——可能方向（啟用全部股票名稱、擴大回看天數與頁數預算、改為內文比對）各有代價，本次不比較、不建議，留給 Gate 4 啟動申請書。交叉引用 `REMAINING_RISKS.md` `RISK-015`。 |
| 40 | **PTT 回補極限下 458 檔情緒覆蓋率上限量測**（2026-09-21，PO 開案；`§0.5 #40` Gate A 提案 `PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md` v3 核准） | **✅ CLOSED（2026-09-21，PO 核准結案）**——段 A（`b131bbf`，離線重新比對既有 1,349 篇，零網路）：凍結基準 683/2.79% → 現行口徑同管線重算 846/3.46% → 全關鍵字重算 1,005/4.11%（映射漂移 +163 格、關鍵字擴展真實效果 +159 格，見 #41），**嚴格下界，非真正上限**。段 B1（真實對 PTT 執行一次，30 頁）：實測 `pages_per_day≈2.31`，v1 推導誤把置底公告當成最舊文章、低估約 20 倍，訂正後回溯到 2026-01-01 約需 577～920 頁。段 B2（真實對 PTT 執行**恰好一次**，950 頁預算、延遲加倍、842 頁、16,814 篇、58.5 分鐘、零撞 403/429、零資料表寫入）：**自然回溯到 2026-01-01 停止，給出精確上限——`coverage_raw_hit` 2,910/24,450＝11.9%（凍結基準 2.79%、段 A 全關鍵字 4.11%）、`coverage_5d_ma_proxy` 8,596/24,450＝35.16%（基準 5.76%）、197 檔股票命中**（現行 `tracking_keywords` 僅追蹤約 30 檔）。**2×2 對照關鍵發現**：現行 25 個有映射關鍵字套全板語料僅 864 格（3.53%）、21 檔，比段 A 篩選語料的 846 格只多 18 格——**每日 ETL 擷取深度已接近完整，11.9% 裡的 2,046 格差額幾乎全來自關鍵字擴展，瓶頸在關鍵字廣度不在擷取**。**§3.4 邊界判定**：09-07 舊回補停在 2026-01-17，B2 回溯到 2025-12-31 全程未撞看板保留邊界，證實 01-17 為**當初預算用盡**、非真實邊界；真實邊界在 2025-12-31 之前，本案未觸及。是否擴大關鍵字清單留待 Gate 4 裁決，本案不做建議。交叉引用 `REMAINING_RISKS.md` `RISK-015`（已附完整量測結論）。證據：`PTT_COVERAGE_CEILING_offline_rematch.json`（段 A）／`_rate_probe.json`（段 B1）／`_full_scrape_report.json`（段 B2）。 |
| 41 | **候補案：凍結面板的情緒覆蓋率基準會隨每日 ETL 探索寫入的 `theme_stock_mapping` 漂移**（2026-09-21，`#40` 段 A 唯讀量測發現） | **觸發條件：下次需要比較「新舊情緒覆蓋率」時，先查證本項是否影響——綁事件，不綁排程輪次**。`theme_stock_mapping` 每日 ETL 的 AI 探索持續寫入新列；`#40` 段 A 實測：凍結面板（`panel_target_up_down_20260912.parquet`）的 `article_count>0` 基準 683 格，凍結後四天內（09-16～09-18）該表 66 列中有 28 列 `updated_at` 更新（`VERIFIED THIS SESSION`），若直接拿今日映射表重算「現行口徑」（不含任何新關鍵字、只用既有 `fetch_keyword`）比對凍結基準，數字已從 683 升到 846——這 163 格全部是映射表漂移，不是任何量測案本身的效果；`#40` 案要量測的「全關鍵字擴展」真實效果（846→1,005，+159 格）只占「683→1,005」總差異的一半。**推廣規則**：比較任何「凍結產物 vs 新管線重算」的覆蓋率之前，必須先把未改動的輸入（現行口徑）推過同一條新管線，確認能零遺漏重現凍結值（自我檢查：`intersection` 應等於凍結基準的格數、`only_in_frozen_baseline` 應為 0），差額才能歸因於新管線本身，否則會把漂移誤記為效果。交叉引用 `RISK-032`——同一機制的另一面：`RISK-032` 管的是「AI 探索改寫既有映射的權重」，本項管的是「AI 探索新增映射，讓任何以舊面板為基準的歷史覆蓋率比較失真」。見 `doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_offline_rematch.json` 的 `drift_vs_expansion` 區塊。 |
| 42 | **候補案：跨文件一致性反查既有缺口批次**（2026-09-21，§0.5 #40 GOV 摘要案 commit 前跑 `cross_doc_consistency_check.py` 產出 9 發現） | **觸發條件：下次動 `PROJECT_STATUS.md` §0.5 索引結構時一併處理**——**綁事件，不綁排程輪次**。R2：`gates/closed/` 共 80 檔中 5 個孤兒未被 `PROJECT_STATUS.md` 引用（`FEATURE_REGISTRY_SOURCE_ANCHOR_GATE_A_PROPOSAL.md`／`FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`／`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`／`GEMINI_TRANSIENT_KEYWORDS_UNIFY_GATE_A_PROPOSAL.md`／`UG_G3_SB2_GATE_A_PROPOSAL.md`）——是索引結構問題，要決定這些引用該放進哪一節，不該順手補。R3：`PROJECT_STATUS.md` 引用已轉 `SUPERSEDED` 的 `DEC-024`——需逐處判斷該引用是歷史敘述（保留合理）還是現行依據（該改指到取代它的 `DEC-039`），不可一律替換。皆非本次 GOV commit 造成，發現時機純屬本次順帶跑 `gate-submit` 產出 9 反查。 |

### 0.6 新對話的入口路徑

依序讀這五份，不需要任何對話上下文即可接手：

| # | 檔案 | 回答什麼 |
|---|------|---------|
| 1 | `CLAUDE.md` | 規則、環境、證據標籤、§16 文件結構 |
| 2 | `doc/README.md` | 哪份文件屬於誰、還活著嗎 |
| 2A | `doc/governance/TEAM_PLAYBOOK.md` | **給下一個 Claude 團隊**：實際角色、PO 專屬批准事項、Gate／SB 迴圈、失敗模式與環境陷阱目錄 |
| 3 | `doc/governance/PROJECT_STATUS.md` §0 | 現在做到哪裡（本節） |
| 4 | `doc/upgrade/gates/`（根層） | **目前無審查中的 SB**：Gate 1 全部五個 SB 皆已 CLOSED；Gate 2 已核准啟動，`UG-G2-SB1`～`SB4` 皆已 CLOSED（見 §0.2），文件皆已移入 `gates/closed/`；`UG-G2-SB5`（Dcard Adapter，**CONDITIONAL** —— 依 §8 不阻擋 Gate 2 關閉）為下一個候選 SB，**尚未送 Gate A** |
| 5 | `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §8（Gate 2 各 SB Brief） | `UG-G2-SB5`～`SB7` 的 SB 邊界規劃（僅核心欄位，細節待各自 Gate A 階段補齊完整 Brief，見 `GATE2_STARTUP_APPLICATION.md` §2.2）——**尚未送 Gate A，PO 尚未審查**。`UG-G2-SB5` 為 CONDITIONAL：Dcard 可用性驗證 FAIL 時標記 `DEFERRED WITH EVIDENCE`，不阻擋 Gate 2 關閉 |

執行前務必確認 `git config --get core.hooksPath` 輸出 `.githooks`
（`CLAUDE.md` §12.4；此設定不隨版控傳遞，新 clone 或容器重建後會失效）。

---

## 1. Current Phase

- 目前階段：**Milestone B COMPLETED / PRODUCTION READY**（維運自動排程與使用者體驗優化達成）。
- 全套自動化測試狀態：**133/133 tests PASS**（覆蓋 Gate 2 至 Gate 5、Phase 3、Phase 4 以及 Operational &amp; UX 之 13 大測試套件檔案，耗時 ~1.26s）。
- Operational &amp; UX Status：`COMPLETE`（2026-08-20 自動排程、動態日期、UI 自選股與 AI 探索熱詞全數就緒）。
- Phase 4 Status：`CLOSED（已關閉）`（2026-08-20 Human Approved，Commit `6cb38af`）。
- Phase 3 Status：`CLOSED（已關閉）`（2026-08-20 Human Approved，Commit `76986de`）。
- Gate 6 Status：`CLOSED（已關閉）`。
- Gate 5 Status：`CLOSED（已關閉）`。
- Gate 4 Status：`CLOSED（已關閉）`。
- Gate 3 Status：`CLOSED（已關閉）`。
- Gate 2 Status：`CLOSED（已關閉）`。
- Gate 1 Status：`CLOSED（已關閉）`。
- Gate 0 Status：`CLOSED（已關閉）`。

## 2. Git State

- Current branch：`fix/gate1-schema-source-of-truth`
- Current HEAD：`a41a9ea`（`docs: finalize end-to-end traceability matrix and milestone b status`）。
- Pre-Codex baseline commit：`71fc6c75e54c076377360b2462a3e78bd073ab44`
- Current modified paths：`doc/evidence/TRACEABILITY.md`、`doc/governance/PROJECT_STATUS.md`。
- 目前沒有 untracked files，working tree 乾淨。

## 3. Completed Work

- Gate 0 已完成可回復 Git baseline、Repository 外 PostgreSQL logical backup（邏輯備份）、秘密資訊／實體資料 ignore 防護，以及 Dev Container dependency installation reproducibility（相依套件安裝可重現性）驗證。
- Gate 1 Read-only Architecture Audit（唯讀架構稽核）已完成人工 Review：`schema.sql`、舊 `init_db.py` 與實際 PostgreSQL Schema 的差異已確認。
- Gate 1 Small Batch 1 已通過人工 Review：seed conflict policy（初始資料衝突政策）、DEC-001 Audit Correction（稽核更正）與 DEC-002 已核准並納入 closure commit scope。
- Gate 1 Small Batch 2 已通過人工 Review：`init_db.py` 已改為 canonical `schema.sql` 的 thin executor，移除 embedded DDL、autocommit 與 hard-coded database credential。
- 靜態檢查已執行：Dev Container 內 `python -m py_compile database/init_db.py` 成功，`git diff --check` 無錯誤。
- Isolated PostgreSQL 18.6 functional verification 已完成並通過人工 Review：fresh initialization、第二次重跑、runtime configuration preservation、Schema Fingerprint stability、failure exit semantics、transaction rollback 與 development environment non-interference 均有本次證據支持。
- Gate 1 Documentation Sync 已完成；DEC-002 與 SDD 已反映已核准決策、驗證證據、Initialization／Migration boundary 及 security incident outcome。
- Reviewer Final Recommendation：`PASS WITH NOTES — READY FOR HUMAN CLOSE / COMMIT APPROVAL`。
- Human Final Review 已完成並批准 Gate 1 close／commit；Gate 1 正式 `CLOSED`。

## 4. Approved Decisions

- DEC-001：保留正式 Pre-Codex baseline；baseline 代表可追蹤、可回復的現況，不代表既有業務邏輯完全正確。
- DEC-002：`database/schema.sql` 是 Database DDL Single Source of Truth（資料庫 DDL 單一真實來源）；`init_db.py` 僅負責設定、連線、交易與執行 canonical schema（標準綱要）。
- Bootstrap seed（初始化預設資料）只服務新資料庫；`tracking_keywords` 與 `entity_mapping` 使用 `ON CONFLICT DO NOTHING`，不得覆蓋 runtime configuration（執行期設定）。既有 seed 更新屬 migration（遷移）責任。
- Initialization（初始化）不等於 Migration（遷移）；Gate 1 不修改目前開發 DB、不處理 legacy `daily_model_features`、不新增 FK、不處理 Canonical Stock ID，也不導入 migration framework。
- Security incident：Gemini API key 已由使用者手動 revoke／replace；local development PostgreSQL password 未 rotation，依使用者決策記為 `Accepted Risk（已接受風險） / Deferred Remediation（延後修復）`。
- 完整背景、替代方案與取捨以 `doc/evidence/DECISIONS.md` 為準。
- DEC-003：Gate 2 採 DB read exception propagation、exact-title cache membership 與 Option A — Strict LLM Completion（嚴格 LLM 完成語意）；三個 Small Batches、Documentation Review、Final Gate Review 與 Human Close 均已完成，Gate 2 正式 `CLOSED`。
- 2026-08-19 Human 接受 G2-SB1 `PASS WITH NOTES` 並批准標記正式完成；同時批准 G2-SB2 依第 8.2 節進入 Implementation，但不批准 G2-SB3。
- 2026-08-19 Human 接受 G2-SB2 `PASS WITH NOTES` 並批准標記正式完成；同時批准 G2-SB3 依第 8.3 節進入 Implementation。
- 2026-08-19 Human 接受 G2-SB3 `PASS WITH NOTES` 與已記錄的 unit／mock evidence boundaries，批准將 G2-SB3 標記為 `COMPLETE`；這不是 Gate 2 close 或 commit approval。
- Human 已接受 `AGENT_TEAM.md`／`WORKFLOW.md` 的 governance `PASS WITH NOTES` 及證據邊界，並批准在 Gate 2 commit 完成後，以這兩個 paths 建立獨立 governance commit；不得混入其他檔案。
- Human 授權 PM 依工作因果關係動態決定 Reviewer／QA 是否平行；implementation diff 必須先凍結，發生 correction 時受影響 QA 必須重跑，Reviewer Evidence Review／Documentation Sync 仍等待最終 Review 與 QA。此為目前工作授權，不等同永久修改 `WORKFLOW.md`。
- DEC-004：Human 於 2026-08-20 核准 Gate 3 的 Soft Delete lifecycle、MVP bare canonical ID contract、market-aware yfinance／direct TPEx deferred，以及最小唯讀 development DB audit。架構方向已批准，但 Canonical ID mapping ownership／傳遞與 implementation 尚待獨立 Small Batch brief／Human approval。
- Historical TPEx experiment 維持 `REPORTED, NOT INDEPENDENTLY VERIFIED`，不得當作目前 Repository 已支援 direct TPEx 的證據。

## 5. Current Findings

### Confirmed Facts（已確認事實）

- Gate 1 唯讀稽核確認：實際 PostgreSQL 的六張 public tables 與 `schema.sql` 在已稽核的 tables、columns、PK、UNIQUE、indexes 與 defaults 範圍內一致；程式使用 `daily_ml_features`。
- Gate 1 closure commit `d76def2` 已包含 Human-approved 的五個 Gate 1 paths；其 scope 沒有擴張到其他檔案。
- Gate 1 closure commit 中的 Small Batch 1 只調整兩組 seed 的 conflict policy，並新增 DEC-001 correction／DEC-002。
- Gate 1 closure commit 中的 Small Batch 2 已使 `init_db.py` 移除 embedded DDL（內嵌 DDL）、autocommit 與硬編碼資料庫憑證，改由環境變數取得設定並以 `Path(__file__)` 讀取 UTF-8 `schema.sql`；它具備 commit、rollback、exception propagation（例外傳遞）與明確 resource cleanup（資源清理）。
- 隔離 PostgreSQL 18.6 首次與第二次 initialization 均 exit 0；六張 canonical tables 存在，`daily_model_features` 不存在，bootstrap seed row count 與 keys／values 符合 `schema.sql`。
- Runtime override 在第二次 initialization 後保留，row count 未增加且 duplicate query 為空。
- 第二次執行前後的 normalized catalog Schema Fingerprint 相同；missing environment、bad connection 與 invalid SQL 均產生 non-zero exit，invalid SQL transaction 未留下 rollback probe 或 partial public schema。
- Temporary container、anonymous volume 與 `/tmp` artifacts 已清除；development PostgreSQL container ID、StartedAt、network、bind mount 與 running state 未改變。
- G3-SB1 frozen diff 在 `src/loaders/db_writer.py`、`src/extractors/trend_discover.py` 與 `tests/test_tracking_keyword_integrity.py` 實作 purpose-specific discovery insert-only、disable update-only、external exploration failure observable／skip，以及 DB configuration write exception propagation；public user upsert behavior 未改。
- G3-SB1 Reviewer Review、Reviewer Evidence Review 與 Documentation Review 均為 `PASS WITH NOTES`，QA 為 `PASS — approved mock/static scope`；Human 已接受 notes／limitations 並批准 G3-SB1 正式 `COMPLETE`。
- Independent minimal read-only development DB audit 已完成並 rollback／close；結果見第 9.3 節。這項 audit 不支持 G3-SB1 live write semantics，也不授權 existing-data correction。

### Security Incident Status（安全事件狀態）

- Incident：Gate 1 isolated verification 曾使用範圍過大的 Docker runtime inspection，使 container environment 中的 credential values 進入工具紀錄；本文件不保存任何 value。
- Root cause：Read-only inspection 不代表 non-sensitive inspection；完整 runtime output 違反 least-disclosure principle（最少揭露原則）。
- Gemini API key：`ROTATED / CLOSED`（由使用者手動 revoke／replace）。
- Development `POSTGRES_PASSWORD`：`NOT ROTATED / ACCEPTED RISK / DEFERRED`。
- 接受風險限於目前 local-only development database、無 host port publishing、非 production／cloud environment；這不表示 credential 沒有風險或已安全。
- 必須在 cloud deployment、remote exposure、public repository release、shared／multi-user environment，或 CI/CD／automation 使用相同 credential 前重新開啟 remediation。

### Known Risks（已知風險）

- Existing database migration safety 尚未驗證；fresh initialization PASS 不代表 migration safety。
- Legacy schema upgrade 與 `daily_model_features` migration 維持 Deferred（延後）。
- Pre-Codex Git history 可能仍含舊 database credential；Repository 在必要的 Credential Rotation（憑證輪替）與 History Sanitization（歷史秘密資訊清理）前不適合公開。不得搜尋或顯示舊值。
- `git diff` 仍可能提示 Gate 1 檔案發生 LF → CRLF 轉換；目前禁止 repository-wide normalization（全儲存庫正規化）。

### Deferred Issues（延後事項）

- G3-SB1 已完成 Soft Delete lifecycle 的限定範圍，但 live PostgreSQL write semantics 仍未驗證；hard delete、structured observability 與更完整 configuration ownership 仍為 Deferred。
- Canonical Stock ID 的 bare-ID architecture direction 已批准，但 market-provider mapping responsibility／傳遞、approved paths、tests 與 implementation 仍待下一個 Small Batch brief；FK redesign／Schema migration 未批准。
- Gate 2 read-only audit／Architect analysis、G2-SB1／SB2／SB3、Documentation Sync 與 Reviewer Documentation Review 均已完成；結果與限制見 DEC-003、SDD 與第 8 節。
- 時間對齊、Prediction Time Convention 與 broader automated test safety net 依整頓計畫留待後續 Gate。
- SDD 的 Gate 2 Documentation Sync 已移除 Hybrid NLP production suitability、完整 429 protection、精準續跑與全面冪等等未受目前證據支持的強式描述；real pandas／Gemini／PostgreSQL／End-to-End 限制仍明確保留。

## 6. Current Scope

### Allowed（目前允許）

- 對 G3-SB1 Documentation Review correction 做三份既有文件的純狀態同步與唯讀 diff／scope／whitespace checks。
- 以唯讀分析準備 Canonical ID Small Batch brief 供 Human 審批；準備 brief 不等於 implementation approval。

### Out of Scope（目前禁止）

- 修改 G3-SB1 code／tests、PRD、PRE plan、governance、Schema、migration 或其他未批准 paths。
- 開始 Canonical Stock ID／market-provider mapping implementation，修改 existing data，或新增 direct TPEx extractor／fallback。
- 執行 `database/init_db.py`、`schema.sql`、任何 DB write／ETL／temporary PostgreSQL；不得呼叫真實 PTT、Gemini 或其他外部網站，也不得讀取 `.env` runtime secrets。
- 修改目前 PostgreSQL、`.devcontainer/postgres-data/`、bind mount、PostgreSQL image 或進行 restore。
- 關閉 Gate 3、開始 Canonical ID implementation、stage／commit、push、merge、rebase 或 reset；這些均需後續明確授權。

## 7. Gate 1 Closure Record


| Path                                       | Gate 1 content                                                   | Closure state                                           |
| ------------------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------- |
| `database/schema.sql`                      | Seed conflict policy                                             | Review／verification approved；included in closure commit |
| `database/init_db.py`                      | Thin executor refactor 與 hard-coded credential removal           | Review／verification approved；included in closure commit |
| `doc/evidence/DECISIONS.md`             | DEC-001 correction、DEC-002、verification 與 security risk decision | Final Review approved；included in closure commit        |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | Schema authority、initializer boundary 與 seed policy              | Final Review approved；included in closure commit        |
| `doc/governance/PROJECT_STATUS.md`        | Gate 1 closure 與 handoff state                                   | Human approval recorded；included in closure commit      |


## 8. Gate 2 Small Batch Briefs

### 8.1 G2-SB1 — DB Read Failure Contract（已批准實作）

```text
Gate / Batch ID:
Gate 2 / G2-SB1

Objective:
為三個 DB read methods 建立共同且可觀測的 failure contract，讓 successful empty result 與 DB failure 不再共用相同回傳值或假成功流程。

Approved decision:
- fetch_data() 成功且零筆資料時維持 empty DataFrame；DB exception 必須向上傳遞。
- fetch_cached_scores() 成功且零筆 matching rows 時維持 {}；DB exception 或無效 cache value（非數值、NaN、Infinity 或不在 0.0～1.0）必須向上傳遞，不得變成 cache miss。
- fetch_active_keywords() 成功且零筆資料時維持 []；DB exception 必須向上傳遞，不得變成正常的零個 active keywords。
- 上述 failure 必須停止目前 Pipeline，且不得輸出「所有文章完成」、「取得 0 個關鍵字」、「所有 ETL 任務完成」或其他由 failure 推導出的假成功訊息。

In-scope behavior:
- 只修改三個 read methods 的 exception propagation 與必要 resource cleanup。
- 建立 deterministic unittest／mock，覆蓋 successful empty、connection／execute failure、無效 cache value與 Pipeline failure propagation。
- 允許把 main_etl_pipeline.py 當成唯讀測試目標；預期不需修改它。

Approved paths:
- src/loaders/db_writer.py
- tests/test_db_read_semantics.py（new）

Out-of-scope:
- src/transform/nlp_processor.py 與 NLP／SnowNLP／Gemini 行為。
- cache membership／neutral cache hit candidate selection。
- sentiment_cache write、checkpoint、Schema、migration、dependency、ETL scheduling 與任何無關 cleanup／refactor。
- 修改 main_etl_pipeline.py；若證明必須修改，立即停止並回報 PM／Human 重新批准 path。

Required tests / checks:
- fetch_data(): successful zero rows -> empty DataFrame；connect／execute failure -> raises；connection cleanup 可查證。
- fetch_cached_scores(): empty input 與 successful zero rows -> {}；connect／execute failure及非數值、NaN、Infinity、<0 或 >1 的 cache row -> raises，不回傳 {}。
- fetch_active_keywords(): successful zero rows -> []；connect／execute failure -> raises，不回傳 []。
- run_nlp_sentiment_pipeline(): fetch_data failure 向上傳遞，update_sentiment_scores() 不被呼叫，且沒有「所有文章情緒分數計算完畢」訊息。
- run_all_daily_tasks(): active keyword read failure 向上傳遞，後續 NLP／feature steps 不執行，且沒有「取得 0 個追蹤關鍵字」或「所有 ETL 任務執行完畢」訊息。
- python -m unittest discover -s tests -v
- python -m py_compile src/loaders/db_writer.py tests/test_db_read_semantics.py
- git diff --check 與 approved-scope diff review。

Safety / isolation constraints:
- 全部自動化測試使用 unittest.mock；不得建立真實 DB connection、呼叫 Gemini／外部網站、讀取 .env 或輸出 credential／完整 environment。
- 不連接或修改 development database，不掛載或修改 .devcontainer/postgres-data/。
- 本批預期不需要 isolated PostgreSQL；若 mock 無法提供可信證據，先停止並由 PM 判斷是否啟用已批准的隔離 PostgreSQL 18 QA 條件。
- 不 stage、commit、push 或 merge。

Expected evidence:
- 保留修正前最小 failing-test evidence 與修正後 unittest／py_compile／diff-check 結果。
- Implementation handoff 列出 actual changed paths、測試命令、原始結果、未驗證範圍與範圍外發現。
- Reviewer verdict、QA result 及 Reviewer Evidence Review 各自獨立回報。

Stop / escalation conditions:
- 需要修改 approved paths 以外檔案或新增 dependency。
- 需要變更 public return type、Schema、Data Contract、NLP／cache-hit／checkpoint 行為。
- 無法在 mock 隔離下證明 failure 不產生假成功，或測試會接觸 development DB／真實外部服務。
- 發現 secret disclosure、資料破壞風險、unrelated working-tree change 或原批准語意互相衝突。
```

#### G2-SB1 Result / Evidence Status

- Implementation：`COMPLETE`。實際 implementation paths 僅為 `src/loaders/db_writer.py` 與 `tests/test_db_read_semantics.py`；`main_etl_pipeline.py` 僅作唯讀測試目標，沒有修改。
- Reviewer Review：`PASS WITH NOTES`。未發現需修正的功能、scope creep、Schema／migration／dependency 或 SB2／SB3 越界。
- QA：`PASS — approved unit/mock scope`，附本節 limitations／notes；這是 `WORKFLOW.md` 定義的 canonical QA result，不把 notes 誤當成另一種 QA 狀態。
- Reviewer Evidence Review：`PASS WITH NOTES`；QA evidence 足以支持 G2-SB1 核准範圍。
- Documentation Sync：`COMPLETE`；Reviewer Documentation Re-review：`PASS`。這不代表 Gate 2 close。
- Human notes acceptance：`ACCEPTED`；G2-SB1：`COMPLETE`。這不代表 Gate 2 close 或 commit approval。

`VERIFIED THIS SESSION`：

- Windows Python 3.10 的 `unittest` 兩次各為 14 tests／`OK`，`py_compile` exit 0。
- 隔離 Dev Container Python 3.14.6 的相同 14 tests／`OK`，`py_compile` exit 0。
- `git diff --check` exit 0；只有既有 LF → CRLF working-copy warning，沒有進行 repository-wide normalization。
- 測試覆蓋三個 DB read methods 的 successful empty、connect／execute failure propagation 與 connection cleanup。
- Cache value 測試覆蓋非數值、`None`、NaN、正負 Infinity、低於 0、高於 1；`0.0`、`0.5`、`1.0` 為有效 boundaries。
- NLP read failure 不呼叫 processor／`update_sentiment_scores()` 且不輸出全部完成；active-keyword read failure 不執行後續 PTT／NLP／feature steps，也不輸出零關鍵字或全部 ETL 完成。

Evidence boundaries／notes：

- 修正前精確「7 failures、4 errors」及 CP950 `UnicodeEncodeError` 只有 Implementation handoff 摘要，標為 `REPORTED, NOT INDEPENDENTLY VERIFIED`；base source 已獨立確認三個 methods 原本吞掉 DB exceptions，且 cache 未拒絕 NaN／Infinity。
- QA 保留 WindowsApps version／pip process failure、第一次 container wrong-workdir failure 與 sandbox `docker -w` denial；修正命令路徑後才取得 PASS，沒有隱藏這些 harness failures。
- 沒有 cache-read failure 的完整 NLP orchestration 專用測試；method-level raise 與唯讀 control-flow inspection 支持本批 contract，完整 cache-hit／checkpoint 行為仍屬 G2-SB2／G2-SB3。
- 所有 DB calls 均為 mock；未啟動 PostgreSQL 臨時環境，未接觸 development DB、`.devcontainer/postgres-data/`、ETL、Gemini、外部網站、`.env` 或 credential。Cleanup：`NOT APPLICABLE`。
- PostgreSQL integration、transaction behavior、End-to-End 與 production readiness：`NOT VERIFIED`。

### 8.2 G2-SB2 — Cache Hit Identity &amp; Cache Read Integrity（已批准實作）

```text
Gate / Batch ID:
Gate 2 / G2-SB2

Objective:
將 LLM candidate selection 從「套用快取後的分數是否仍 fuzzy」改為明確 cache membership，確保有效 neutral cache hit 被重用且 cache read failure 不會引發 Gemini。

Approved decision:
- 有效 exact-title cache hit，不論分數是否為 0.45、0.50 或 0.55，都不得再次呼叫 Gemini。
- 只有 original fuzzy 且未 cache hit 的項目才是 LLM candidate。
- Gemini 回傳 0.5 的正式成功語意留待 G2-SB3 完整驗證；本批不改 checkpoint failure contract。

In-scope behavior:
- 在 NLP processor 中保存 cache membership／provenance，不能由數值區間反推 cache hit。
- 以 mock 驗證 valid cache hit、cache miss、非 fuzzy 與 propagated cache read failure 的 candidate selection。

Approved editable paths:
- src/transform/nlp_processor.py
- tests/test_nlp_cache_semantics.py（new）

Out-of-scope:
- Gemini response completeness／key／score validation、SnowNLP exception policy、checkpoint atomicity、cache write ordering。
- DB Schema、cache key redesign／versioning／TTL、migration、main orchestrator redesign 與新增 dependency。

Required tests / checks:
- cached 0.45／0.50／0.55 fuzzy rows -> Gemini 不被呼叫且 cached score 被保留。
- mixed batch -> Gemini 只收到 original fuzzy cache misses。
- non-fuzzy rows -> 不查詢／不呼叫不必要的 Gemini path（依現有批次 contract 查證）。
- fetch_cached_scores() propagated failure -> Gemini 不被呼叫，failure 向上傳遞。
- duplicate titles／empty input 的既有語意不被意外改變；若發現 identity ambiguity，停止並升級。
- unittest、py_compile、git diff --check 與 approved-scope diff review。

Safety / isolation constraints:
- 只用 unittest.mock／deterministic DataFrame；不連 DB、不呼叫真實 Gemini／外部網站、不新增 dependency。
- 不 stage、commit、push、merge，不修改 development data。

Expected evidence:
- 原 neutral cache hit 會重呼 Gemini 的 failing evidence、修正後 candidate-call evidence，以及完整 changed-path／regression handoff。

Regression risks:
- membership 與 title normalization 不一致，造成 false hit／miss。
- mixed batch index／ID 對應錯誤或 cached score 覆寫錯 row。
- 無意間提前實作 SB3 的 fail-fast／checkpoint contract。

Stop / escalation conditions:
- 需要 cache key／Schema／Data Contract redesign、標題 normalization 新規格或修改 approved paths 以外檔案。
- 無法在不改 Gemini completion／checkpoint semantics 下獨立完成。
- cache mapping 出現 duplicate／invalid identity，現有 exact-title contract 無法明確處理。
```

#### G2-SB2 Result / Evidence Status

- Implementation：`COMPLETE`。實際 SB2 paths 僅為 `src/transform/nlp_processor.py` 與 `tests/test_nlp_cache_semantics.py`；沒有修改 DBWriter、main orchestrator、Schema、dependency 或 G2-SB3 completion semantics。
- Reviewer Review：`PASS WITH NOTES`。未發現需修正的功能缺陷、scope creep 或提前實作 G2-SB3。
- QA：`PASS — deterministic unit/mock scope`。
- Reviewer Evidence Review：`PASS WITH NOTES`；QA evidence 足以支持 Human 批准的 G2-SB2 範圍。
- Documentation Sync：`COMPLETE`；Reviewer Documentation Review：`PASS`。這不代表 G2-SB2／Gate 2 已完成或關閉。
- Human notes acceptance：`ACCEPTED`；G2-SB2：`COMPLETE`。這不代表 Gate 2 close 或 commit approval。

`VERIFIED THIS SESSION`：

- Windows Python 3.10 與 Dev Container Python 3.14.6 的完整 suite 均為 22 tests／`OK`，包含 G2-SB1 14 tests 與 G2-SB2 8 tests。
- 兩個環境對 SB1／SB2 四個 code／test paths 的 `py_compile` 均 PASS；`git diff --check` exit 0，只有既有 LF → CRLF warnings。
- Cache hit 使用 exact-title membership，不使用 cached score range 或 truthiness；`0.0`、`0.45`、`0.50`、`0.55` 均為有效 hit且不呼叫 LLM。
- Mixed batch 只把 original-fuzzy cache misses 送往 LLM，並保持非預設 DataFrame index 的 ID-to-title mapping。
- Duplicate cached title 會套用到所有 fuzzy rows；duplicate-title miss 仍保留每列不同 index。
- Legitimate empty cache mapping 會把所有 original-fuzzy rows送往 LLM；cache read exception 向上傳遞且不呼叫 LLM／cache write。
- Non-fuzzy、empty 與 missing-title paths 維持 no-op／不必要外部呼叫為零；測試亦核對 columns、row count 與 index association。

Evidence boundaries／notes：

- 修正前精確「22 tests、3 failures」為 `REPORTED, NOT INDEPENDENTLY VERIFIED`；base code inspection 已獨立支持 neutral cache hit、duplicate title 與 mixed candidate regressions。
- Dev Container 沒有 pandas，real-pandas ad-hoc verification 因 `ModuleNotFoundError` 未能執行；沒有為此安裝 dependency。`INFERENCE`：執行測試的 container Python environment 未安裝 Repository runtime dependencies，或與預期開發 interpreter environment 不同；未另行稽核原因。Real pandas semantics：`NOT VERIFIED`。
- SB2 tests 使用 deterministic FakeDataFrame，可驗證核准的 membership／mapping／shape invariants，但不能代表完整 pandas／ETL integration。
- 目前行為假設 DataFrame index 唯一；duplicate title 已驗證，duplicate index 未驗證。現有 `fetch_data()` 一般產生 unique RangeIndex，但這尚不是顯式 Data Contract。
- Windows `py -3.10 --version` diagnostic 仍失敗，但同 selector 的核准 unittest／py_compile commands 可成功執行。
- 未連接 DB、執行 ETL、呼叫 Gemini／網站、讀 `.env`、輸出 credential 或接觸 development data；未啟動臨時 PostgreSQL，cleanup：`NOT APPLICABLE`。
- Missing／partial Gemini result、Gemini exception、SnowNLP exception、cache-write ordering 與 atomic checkpoint 在 G2-SB2 完成當時為 `NOT VERIFIED／OUT OF SCOPE`；目前已由第 8.3 節 technically completed 的 G2-SB3 evidence 涵蓋，不得倒推為 G2-SB2 evidence。
- PostgreSQL、real Pipeline、End-to-End 與 production behavior：`NOT VERIFIED`。

### 8.3 G2-SB3 — Strict NLP Batch Completion（已批准實作）

```text
Gate / Batch ID:
Gate 2 / G2-SB3

Objective:
落實 Option A strict completion 與 atomic current-batch checkpoint：所有預期 fuzzy results 完整驗證成功前，不得寫 cache 或更新任何 article sentiment checkpoint。

Approved decision:
- 非 fuzzy SnowNLP 結果可以完成；fuzzy 項目只有有效 cache hit 或完整有效 Gemini result 才能完成。
- 缺 API key、Gemini exception、malformed／partial response、缺少或無法對應 ID、NaN／Infinity／非 numeric／超出 0.0～1.0，或 SnowNLP 非預期 exception，整批 fail-fast。
- 完整有效代表涵蓋本次所有預期項目、key／ID 精確對應、每個分數為有限數值且在 0.0～1.0。
- 整份回應驗證前不得先寫任何部分 sentiment_cache；任一 candidate 失敗時不得呼叫 update_sentiment_scores()，DB score 保持 NULL。
- Gemini 正式回傳 0.5 是成功結果。

In-scope behavior:
- 讓 SnowNLP／Gemini failure 可觀測並向上傳遞。
- 對整份 Gemini response 執行 exact expected-ID set、型別、finite 與 range validation，再形成 cache writes／processed batch。
- 保證 processor failure 先於 article checkpoint update；只在必要時對 orchestrator 加入最小 fail-fast 防護。

Approved editable paths:
- src/transform/nlp_processor.py
- tests/test_nlp_checkpoint_semantics.py（new）
- tests/test_nlp_cache_semantics.py（僅限 `test_duplicate_cache_miss_preserves_per_row_llm_identity` 與 `test_legitimate_empty_cache_mapping_sends_all_fuzzy_rows_to_llm` 補入完整有效 mocked LLM results；不得移除或弱化原 candidate-selection assertions）

Read-only test target (not approved for modification):
- main_etl_pipeline.py

Out-of-scope:
- Schema／migration、processing_status／sentiment_source 欄位、fallback state、retry scheduler、partial-success persistence、cache versioning、模型品質重新計算與新增 dependency。
- Dcard／Threads、時間對齊、Feature Engineering 或其他 Gate。

Required tests / checks:
- missing API key、Gemini exception、malformed JSON／wrong top-level type、partial／extra／unmappable IDs、non-numeric、NaN、Infinity、<0、>1 -> raises；cache write與 article update 均未呼叫。
- 完整 response（包含 0.5）-> 所有預期項目完成驗證後才允許 cache write與 article update。
- SnowNLP unexpected exception -> raises，無 cache／article write。
- 有效 cache hit + 非 fuzzy + Gemini candidates 的 mixed batch 保持正確 ID／row 對應。
- empty input 為安全 no-op；失敗不形成 busy retry loop於同一 invocation。
- unittest、py_compile、git diff --check 與 approved-scope diff review。

Safety / isolation constraints:
- Gemini、sleep、SnowNLP、DB writer 全部 mock；不呼叫真實服務或 development DB，不讀 secrets，不新增 dependency。
- 如 Reviewer 初審後確有 runtime DB evidence 必要，只能依 Human 已批准的完全隔離 PostgreSQL 18 條件執行並回報 cleanup／non-interference。
- 不 stage、commit、push、merge。

Expected evidence:
- 每種 failure path 對應的 exception、zero cache writes、zero article updates；完整成功 path 的驗證順序與寫入呼叫證據。
- Implementation／Reviewer／QA／Evidence Review 分離的結果，以及 Option A remaining trade-offs。

Regression risks:
- expected ID 型別正規化造成合法 response 被拒或錯誤對應。
- batch fail-fast 降低 Gemini outage 時的可用性；已完成的非 fuzzy／cache rows 會隨 batch 重試。
- cache write成功但 article update失敗時，下次由 cache 重用；跨兩次 DB write不是單一 DB transaction。
- 現有 Schema 無法持久追溯 SnowNLP／cache／Gemini provenance，此風險不在本批擴張解決。

Stop / escalation conditions:
- 需要新增 Schema／migration／正式 fallback state、改成 partial-success checkpoint，或引入 retry／scheduler。
- 無法在已批准 Option A 下定義無歧義 ID contract，或需要修改 main_etl_pipeline.py／其他 candidate paths 以外檔案／新增 dependency。
- 測試必須呼叫真實 Gemini、讀 secret 或接觸 development DB 才能成立。
```

#### G2-SB3 Result / Evidence Status

- Implementation：`COMPLETE`。實際 production path 為 `src/transform/nlp_processor.py`，新增 `tests/test_nlp_checkpoint_semantics.py`；依 Human 追加授權，`tests/test_nlp_cache_semantics.py` 僅有 `test_duplicate_cache_miss_preserves_per_row_llm_identity` 與 `test_legitimate_empty_cache_mapping_sends_all_fuzzy_rows_to_llm` 補入完整有效 mocked LLM results，原 candidate-selection assertions 未移除或弱化。
- Reviewer Review：`PASS WITH NOTES`。未發現需修正的功能缺陷、未授權 scope expansion 或提前處理其他 Gate。
- QA：`PASS — deterministic unit/mock scope`。
- Reviewer Evidence Review：`PASS WITH NOTES`；平行 QA 期間受測 hashes 未變，證據適用於 Reviewer 審查的同一 frozen diff。
- Small Batch result documentation：`COMPLETE`；Reviewer Documentation Correction Re-review：`PASS`。
- Human notes acceptance：`ACCEPTED`；G2-SB3：`COMPLETE`。這不代表 Gate 2 已關閉或取得 commit approval。
- Gate-level Documentation Sync：`COMPLETE`；Reviewer Documentation Review：`PASS`。這不代表 Gate 2 close 或 commit approval。

`VERIFIED THIS SESSION`：

- Windows Python 3.10 與 Dev Container Python 3.14.6 的完整 suite 均為 33 tests／`OK`：G2-SB1 14、G2-SB2 8、G2-SB3 11。
- 兩個環境的相關 code／test paths `py_compile` 均 PASS；diff／untracked whitespace checks PASS，只有既有 LF → CRLF warnings。
- SnowNLP 非預期 exception、missing API key、Gemini exception、malformed JSON、wrong top-level type、duplicate JSON keys、partial／missing／extra／unmappable IDs 均 fail-fast。
- Bool、字串數字、`None`、NaN、正負 Infinity、低於 0 或高於 1 的 Gemini scores 均被拒絕；完整有效 `0.5` 為正式成功結果。
- Exact string／integer response keys 均能正確映射；candidate IDs 必須唯一，轉成 JSON key 後衝突會被拒絕。
- 整份 response 驗證完成前不修改 DataFrame、不寫 cache；cache write failure 向上傳遞，article checkpoint 尚未推進。
- Processor failure 時 main pipeline 不呼叫 `update_sentiment_scores()`、不在同一 invocation retry、也不輸出所有文章完成；non-fuzzy、fully cached、empty／missing-title paths 保持通過。

Evidence boundaries／notes：

- 初始「33 tests、18 failures、1 error」及中間「31 pass、2 errors」為 `REPORTED, NOT INDEPENDENTLY VERIFIED`；中間兩項 errors 來自舊 SB2 mocks 回傳 `{}`，經 Human 批准只補完整 mock results 後，原 candidate assertions 保留。
- QA 保留 ad-hoc probe 的 PowerShell quoting、sandbox Docker route、V8 `TextEncoder` 與首次 `sys.path` failures；修正測試執行路徑後才取得 PASS，沒有隱藏 harness failures。
- Tests 使用 deterministic FakeDataFrame 與 mocked Gemini／SnowNLP／sleep／DBWriter；real pandas、real Gemini SDK／service、PostgreSQL 與 End-to-End behavior：`NOT VERIFIED`。
- DataFrame unique index 仍是既有假設；duplicate candidate IDs 會被拒絕，但任意 duplicate-index DataFrame 不是已驗證輸入。
- Cache write 與 article update 是分開的 DB operations，不是跨表 ACID transaction。Cache 成功但 article update 或後續 DataFrame assignment 失敗時，cache 可能保留並在下次重用。
- 現有 Schema 不持久記錄 SnowNLP／cache／Gemini sentiment provenance。
- 未連接 DB、執行 ETL、呼叫 Gemini／網站、讀 `.env` 或接觸 development data；未建立臨時 PostgreSQL，cleanup：`NOT APPLICABLE`。

### 8.4 Gate 2 Closure Record

- 2026-08-19 Human 接受 Gate 2 `PASS WITH NOTES` 與已揭露的 verification limitations，批准 Gate 2 正式 `CLOSED`。
- Human 批准的 Gate 2 commit scope 嚴格限定為下列八個 paths；不包含 governance 文件或其他檔案：


| Path                                       | Gate 2 content                                                        | Closure state                                            |
| ------------------------------------------ | --------------------------------------------------------------------- | -------------------------------------------------------- |
| `src/loaders/db_writer.py`                 | DB read failure semantics 與 cache value validation                    | Review／verification approved；included in closure commit  |
| `src/transform/nlp_processor.py`           | Exact-title cache membership 與 strict NLP batch completion            | Review／verification approved；included in closure commit  |
| `tests/test_db_read_semantics.py`          | G2-SB1 deterministic unit／mock coverage                               | Evidence Review approved；included in closure commit      |
| `tests/test_nlp_cache_semantics.py`        | G2-SB2 cache membership coverage 與 Human-approved SB3 mock adjustment | Evidence Review approved；included in closure commit      |
| `tests/test_nlp_checkpoint_semantics.py`   | G2-SB3 strict completion／checkpoint coverage                          | Evidence Review approved；included in closure commit      |
| `doc/evidence/DECISIONS.md`             | DEC-003 architecture decision 與 evidence boundaries                   | Documentation Review approved；included in closure commit |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | Gate 2 design／failure contract synchronization                        | Documentation Review approved；included in closure commit |
| `doc/governance/PROJECT_STATUS.md`        | Gate 2 Human Close 與 closure handoff state                            | Human approval recorded；included in closure commit       |


## 9. Gate 3 Active Work &amp; Closure Record

### 9.1 G3-SB1 — Soft Delete Integrity

- G3-SB1 implementation／Reviewer／QA／Evidence Review／Documentation Review stages：已完成。
- Reviewer Review：`PASS WITH NOTES`。
- QA：`PASS — approved mock/static scope`（15 項測試通過）。
- Reviewer Evidence Review：`PASS WITH NOTES`。
- Documentation Review：`PASS WITH NOTES`。
- Human notes acceptance：`ACCEPTED`；G3-SB1 正式 `COMPLETE`。

### 9.2 G3-SB2 — Canonical Stock ID &amp; Provider Mapping Integrity

- G3-SB2 implementation／Reviewer／QA／Evidence Review／Documentation Review stages：已完成。
- Reviewer Review：`PASS WITH NOTES`。
- QA：`PASS — approved unit/mock scope`（17 項測試通過，全套 65 項測試通過）。
- Reviewer Evidence Review：`PASS WITH NOTES`。
- Documentation Review：`PASS WITH NOTES`。
- Human notes acceptance：`ACCEPTED`；G3-SB2 正式 `COMPLETE`。

### 9.3 Gate 3 Closure Record

- 2026-08-20 Human 接受 Gate 3 結案審查報告（Final Gate Review）與已揭露的 verification limitations，正式宣布 Gate 3 `CLOSED`。
- Human 批准的 Gate 3 commit scope 限定為下列九個 paths：


| Path                                       | Gate 3 content                                | Closure state                                            |
| ------------------------------------------ | --------------------------------------------- | -------------------------------------------------------- |
| `src/loaders/db_writer.py`                 | 探索 Insert-only、停用 Update-only 與 DB write 異常傳遞 | Review／verification approved；included in closure commit  |
| `src/extractors/trend_discover.py`         | 探索失敗 Observable 與 skip write 語意               | Review／verification approved；included in closure commit  |
| `src/transform/data_cleaner.py`            | format_provider_symbol 與清洗時 Canonical ID 保證   | Review／verification approved；included in closure commit  |
| `main_etl_pipeline.py`                     | 市場參數傳遞與 yfinance 備援 mapping 調度                | Review／verification approved；included in closure commit  |
| `tests/test_tracking_keyword_integrity.py` | G3-SB1 15 項軟刪除與生命週期單元測試                       | Evidence Review approved；included in closure commit      |
| `tests/test_canonical_stock_id.py`         | G3-SB2 17 項標準代碼與多市場特徵 Join 測試                 | Evidence Review approved；included in closure commit      |
| `doc/evidence/DECISIONS.md`             | DEC-004 架構決策與證據紀錄                             | Documentation Review approved；included in closure commit |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 系統設計規格與資料契約邊界同步                               | Documentation Review approved；included in closure commit |
| `doc/governance/PROJECT_STATUS.md`        | Gate 3 Human Close 與 closure handoff state    | Human approval recorded；included in closure commit       |


## 10. Gate 4 Active Work &amp; Closure Record

### 10.1 G4-SB1 — PTT Time Parsing &amp; Roll-Forward Trading Day Mapping

- G4-SB1 實作／測試／Reviewer／QA 階段：已完成。
- Reviewer Review：`PASS WITH NOTES`。
- QA：`PASS — approved unit/mock scope`（13 項測試通過）。
- Human notes acceptance：`ACCEPTED`；G4-SB1 正式 `COMPLETE`。

### 10.2 G4-SB2 — Zero Look-ahead Feature Aggregation &amp; Target Generation

- G4-SB2 實作／測試／Reviewer／QA 階段：已完成。
- Reviewer Review：`PASS WITH NOTES`。
- QA：`PASS — zero look-ahead bias verified`（5 項時序防洩漏測試通過，全套 83/83 tests PASS）。
- DEC-005 與 SDD v1 同步：已完成。
- Human notes acceptance：`ACCEPTED`；G4-SB2 正式 `COMPLETE`。

### 10.3 Gate 4 Closure Record

- 2026-08-20 Human 接受 Gate 4 結案審查報告（Final Gate Review）與零前視偏誤驗證，正式宣布 Gate 4 `CLOSED`。
- Human 批准的 Gate 4 commit scope 限定為下列八個 paths：


| Path                                         | Gate 4 content                             | Closure state                                            |
| -------------------------------------------- | ------------------------------------------ | -------------------------------------------------------- |
| `src/transform/data_cleaner.py`              | PTT 精確時間戳記與智慧跨年推論解析器                       | Review／verification approved；included in closure commit  |
| `src/transform/feature_aggregator.py`        | Roll-Forward 交易日歸併、時序滾動特徵、Target 生成器       | Review／verification approved；included in closure commit  |
| `tests/test_time_alignment.py`               | G4-SB1 13 項時間解析與交易日對齊測試                    | Evidence Review approved；included in closure commit      |
| `tests/test_feature_aggregator_alignment.py` | G4-SB2 5 項防洩漏、多日滾動與 Target 測試              | Evidence Review approved；included in closure commit      |
| `doc/evidence/DECISIONS.md`               | DEC-005 雙模式預測架構與時間對齊約定                     | Documentation Review approved；included in closure commit |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md`   | 系統設計規格與時間對齊邊界同步                            | Documentation Review approved；included in closure commit |
| `doc/governance/PROJECT_STATUS.md`          | Gate 4 Human Close 與 closure handoff state | Human approval recorded；included in closure commit       |
| `PRE_CODEX_REMEDIATION_PLAN.md`              | 整頓計畫序號與治理歷程校準                              | Human approval recorded；included in closure commit       |


## 11. Gate 5 Active Work &amp; Closure Record

### 11.1 G5-SB1 — Antweiler Bullishness &amp; Agreement Indices

- G5-SB1 實作／測試／Reviewer／QA 階段：已完成。
- Reviewer Review：`PASS WITH NOTES`。
- QA：`PASS — approved unit/mock scope`（4 項測試通過）。
- Human notes acceptance：`ACCEPTED`；G5-SB1 正式 `COMPLETE`。

### 11.2 G5-SB2 — Technical &amp; Risk Features (RSI-14 &amp; Rolling Volatility 5D/20D)

- G5-SB2 實作／測試／Reviewer／QA 階段：已完成。
- Reviewer Review：`PASS WITH NOTES`。
- QA：`PASS — approved unit/mock scope`（2 項測試通過，全套 89/89 tests PASS）。
- DEC-006、RESEARCH_REQUIREMENTS.md 與 SDD v1 特徵契約同步：已完成。
- Human notes acceptance：`ACCEPTED`；G5-SB2 正式 `COMPLETE`。

### 11.3 Gate 5 Closure Record

- 2026-08-20 Human 接受 Gate 5 結案審查報告（Final Gate Review）與 18 欄位特徵契約驗證，正式宣布 Gate 5 `CLOSED`。
- Human 批准的 Gate 5 commit scope 限定為下列六個 paths：


| Path                                       | Gate 5 content                             | Closure state                                            |
| ------------------------------------------ | ------------------------------------------ | -------------------------------------------------------- |
| `src/transform/feature_aggregator.py`      | Antweiler 指標、RSI-14、波動率與 18 欄位特徵契約         | Review／verification approved；included in closure commit  |
| `tests/test_research_features.py`          | G5-SB1 &amp; G5-SB2 6 項專項單元與整合測試           | Evidence Review approved；included in closure commit      |
| `doc/research/RESEARCH_REQUIREMENTS.md`    | 金融研究轉譯與特徵工程需求規格書                           | Human approval recorded；included in closure commit       |
| `doc/evidence/DECISIONS.md`             | DEC-006 機構級特徵工程架構決策                        | Documentation Review approved；included in closure commit |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 系統設計規格與特徵工程邊界同步                            | Documentation Review approved；included in closure commit |
| `doc/governance/PROJECT_STATUS.md`        | Gate 5 Human Close 與 closure handoff state | Human approval recorded；included in closure commit       |


## 12. Gate 6 Active Work

### 12.1 TRACEABILITY.md（端到端追溯矩陣）

- 建立 `Research -> PRD -> SDD -> ADR (DEC-001 ~ DEC-006) -> Code -> Test Suite (89 Tests) -> Evidence` 完整追溯閉環。
- 確立 89 項測試與各架構決策之對應關係。

### 12.2 CHALLENGES.md（重大工程挑戰紀錄）

- 完整收錄 6 大經典難題：
  1. **CHAL-001**: Strict Transactional NLP Checkpointing（防假成功與斷點續傳保護）。
  2. **CHAL-002**: Exact-Title Cache Membership（模糊快取穿透修復與中立分數保護）。
  3. **CHAL-003**: Strict Soft Delete Write Contract（防 AI 探索復活已停用標的與類別竄改）。
  4. **CHAL-004**: Smart Year Inference &amp; Roll-Forward Trading Day Mapping（跨年時間穿越與週末情緒無損歸併）。
  5. **CHAL-005**: Zero Look-ahead Bias Prevention &amp; Target Decoupling（雙模式時間約定與未來資料篡改驗證）。
  6. **CHAL-006**: Pure Vectorized Antweiler &amp; Technical Features（純向量化運算與零外部 C 編譯依賴防護）。

### 12.3 文檔全對齊 (Documentation Reconciliation)

- `doc/spec/PRD_Financial_Sentiment_System_v1.md`：同步 Phase 2 機構特徵工程、Phase 3 雙模式架構與零前視偏誤驗證。
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`：更新 Gate 3 Canonical ID 完工狀態、Gate 4 雙模式時間對齊邊界與 Gate 5 特徵契約。

### 12.4 Gate 6 Closure Record

- 2026-08-20 Human 接受 Gate 6 文件審查報告，正式宣布 Gate 6 `CLOSED`。
- Human 批准的 Gate 6 commit scope 限定為下列五個 paths：


| Path                                       | Gate 6 content                                                                            | Closure state                                      |
| ------------------------------------------ | ----------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `doc/evidence/TRACEABILITY.md`          | 全系統端到端追溯矩陣 (Research -&gt; PRD -&gt; SDD -&gt; ADR -&gt; Code -&gt; Tests -&gt; Evidence) | Human approval recorded；included in closure commit |
| `doc/evidence/CHALLENGES.md`            | CHAL-001 ~ CHAL-006 六大工程挑戰與問題解決紀錄                                                         | Human approval recorded；included in closure commit |
| `doc/spec/PRD_Financial_Sentiment_System_v1.md` | 產品需求文件規格全同步                                                                               | Human approval recorded；included in closure commit |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 系統設計文件規格全對齊                                                                               | Human approval recorded；included in closure commit |
| `doc/governance/PROJECT_STATUS.md`        | Gate 6 Human Close 與 closure handoff state                                                | Human approval recorded；included in closure commit |


## 13. Phase 3 Active Work

### 13.1 P3-SB1 — Walk-Forward 時序切分引擎

- `src/ml/time_series_split.py` 實作 `WalkForwardSplitter`。
- 支援滾動窗口（Rolling Window）與擴展窗口（Expanding Window）。
- 支援多股票全域日期對齊（Global Date Alignment）與倒排索引加速。
- 邊界嚴格驗證：$\max(\text{Train Dates}) < \min(\text{Test Dates})$，訓練集與測試集索引零交集。
- 專項測試：`tests/test_time_series_split.py`（6 項單元與邊界測試全數 PASS）。
- P3-SB1 狀態：`COMPLETE`。

### 13.2 P3-SB2 — 四大基準模型與純價量控制組建立

- `src/ml/baseline_models.py` 實作 `DummyBaselineClassifier`（買入持有/多數類別基準）、`PureTechnicalModelFactory` 與 `TechnicalBaselineSuite`。
- 支援四大模型：`LogisticRegression`, `RandomForest`, `LightGBM`, `XGBoost`。
- 0 輿情污染保證（Zero Sentiment Contamination）：嚴格過濾並鎖定 9 欄位純價量特徵（OHLCV + return_1d + rsi_14 + volatility_5d/20d），完全排除 8 欄位社群情緒特徵。
- 專項測試：`tests/test_baseline_models.py`（6 項單元與 Walk-Forward 整合測試全數 PASS）。
- P3-SB2 狀態：`COMPLETE`。

### 13.3 P3-SB3 — 多模態特徵融合與多模型橫向競技管線

- `src/ml/model_trainer.py` 實作 `MultiModalTrainer`，整合 18 欄位完整特徵矩陣（價量 + RSI + 波動率 + Antweiler 看多/一致性指數 + 情緒滯後）。
- 支援四大模型（LR/RF/LGBM/XGB）橫向競技與擬合。
- 嚴格 Scaler 內部擬合防洩漏流程（`RobustScaler` / `StandardScaler` 嚴格在 Train Set Fit，再 Transform Test Set）。
- 實作特徵重要性矩陣（Feature Importance Rankings），量化 Antweiler 指標權重貢獻，並支援完整模型與 Scaler 序列化保存（`save_artifact` / `load_artifact`）。
- 專項測試：`tests/test_model_trainer.py`（5 項專項單元、防洩漏與序列化測試全數 PASS）。
- P3-SB3 狀態：`COMPLETE`。

### 13.4 P3-SB4 — 8 組平行實驗 Alpha 歸因評估、橫向排行榜與即時推論引擎

- `src/ml/evaluator.py` 實作 `MLEvaluator`、`compute_classification_metrics` 與 `compute_financial_strategy_metrics`。
- 產出 8 組平行實驗對照排行榜（Multi-Model Leaderboard），量化 $\Delta \text{F1}$、$\Delta \text{Return}$ 與 Directional Hit Ratio，自動評選 Champion Model。
- `src/ml/predictor.py` 實作 `StockTrendPredictor`，支援單日最新 1 筆特徵即時推論，輸出明日漲跌（UP/DOWN）、信心機率（0.0 ~ 1.0）與前 3 大驅動特徵（Top Drivers）。
- 專項測試：`tests/test_ml_evaluator.py`（7 項單元與整合測試全數 PASS）。
- P3-SB4 狀態：`COMPLETE`。

### 13.5 P4-SB1 — 應用骨架、資料載入器與深色主題樣式

- `app.py` 搭建 Streamlit 主入口，配置機構級深色模式與側邊欄控制項（標的、時序區間、台美股色彩切換）。
- `src/ui/styles.py` 實作深色金融 CSS 樣式與自訂 KPI 卡片 HTML 渲染器。
- `src/ui/data_loader.py` 實作特徵載入器，支援 PostgreSQL 讀取與離線 Fallback 高仿真資料產生，並串接冠軍模型即時推論。
- 專項測試：`tests/test_ui_contracts.py`（6 項樣式與資料契約測試全數 PASS）。
- P4-SB1 狀態：`COMPLETE`。

### 13.6 P4-SB2 — Plotly 雙 Y 軸 K 線與情緒多維互動圖表

- `src/ui/charts.py` 實作多維互動金融圖表：
  - `render_price_sentiment_candlestick_chart()`（雙 Y 軸日 K 線 + MA5/20 + 社群情緒長條圖 + 0.5 基準線，支援 Tooltip 懸停同步顯示開高低收與情緒 Bt）。
  - `render_pnl_equity_curve_chart()`（AI 多模態量化策略累積報酬率曲線 vs. Buy &amp; Hold 基準）。
  - `render_feature_importance_bar_chart()`（Top 8 驅動特徵重要性橫向長條圖，醒目標記輿情指標）。
- `app.py` 嵌入主圖表區與量化回測/特徵重要性子圖表區。
- 專項測試：`tests/test_ui_contracts.py`（3 項圖表結構專項測試全數 PASS）。
- P4-SB2 狀態：`COMPLETE`。

### 13.7 P4-SB3 — AI 預測推論面板、多模型排行榜與 PTT 輿情明細表

- `src/ui/components.py` 實作可解釋性與明細元件：
  - `render_prediction_panel()`：明日漲跌（UP/DOWN）、信心機率進度條（Confidence %）與前 3 大驅動因子卡片（Top 3 Drivers，標注中文可讀名稱、當前數值與貢獻權重）。
  - `render_tournament_leaderboard()`：8 組平行對照實驗多模型排行榜（LR / RF / LightGBM / XGBoost 之 PureTech vs MultiModal 與 $\Delta \text{Alpha}$ 增益表）。
  - `render_raw_article_table()`：PTT 原始輿情文章明細表，支援依情緒高低排序、多空標籤篩選與關鍵字即時搜尋。
- `app.py` 完整組裝推論決策面板、排行榜與文章表格。
- 專項測試：`tests/test_ui_contracts.py`（2 項元件資料契約與篩選邏輯測試全數 PASS）。
- P4-SB3 狀態：`COMPLETE`。

### 13.8 P4-SB4 — UI 整合驗證、決策紀錄歸檔與 Phase 4 結案審查

- 執行全系統回歸測試：覆蓋 Gate 2 至 Gate 5、Phase 3 以及 Phase 4 全套 124 項測試（124/124 PASS，耗時 0.933s）。
- 架構決策歸檔：於 `doc/evidence/DECISIONS.md` 完整建立 **DEC-008: Streamlit 機構級視覺化架構、雙 Y 軸互動圖表與零依賴平滑回退設計**。
- 產出 Phase 4 結案審查報告與本機啟動指南（`streamlit run app.py`）。
- P4-SB4 狀態：`COMPLETE`。

### 13.9 Operational &amp; UX Enhancements（維運自動排程與使用者體驗優化）

- `scheduler.py`：實作交易日（週一至週五）15:35 盤後自動排程守護行程，支援 `--run-now` 即時手動觸發。
- `scripts/reset_db.py` &amp; `database/init_db.py`：實作 `reset_database()`，安全清空歷史測試髒資料並重設種子配置。
- `main_etl_pipeline.py`：動態使用 `datetime.now()` 計算時序資料，並動態自 DB 撈取所有啟用之股票標的（`fetch_active_stock_targets()`）。
- `app.py` &amp; `src/ui/`：實作自選股動態管理（`custom_stocks`）與 AI 熱門探索詞（`render_ai_trend_discovery_badge`）即時視覺化。
- 專項測試：`tests/test_operational_ux.py`（10 項測試）與 `tests/test_nlp_resilience_e2e.py`（2 項全流程端到端測試全數 PASS）。
- 挑戰紀錄歸檔：`doc/evidence/CHALLENGES.md` 建立 **CHAL-007: Gemini API 429 Rate Limit 彈性重試與指數退避協議**。
- 除錯規範固化：升級 `.agents/skills/interactive-bug-fix-protocol/SKILL.md`，強制規範 E2E 全流程防回歸測試與非瑣碎 Bug 挑戰歸檔。
- 狀態：`COMPLETE`。

### 13.10 Thematic Trends Extension: SB-TH1 — 概念知識庫與 AI 自動映射

- `database/schema.sql` & `database/init_db.py`：新增 `theme_stock_mapping` 獨立表與 4 大熱門題材種子資料（矽光子、散熱模組、CoWoS、AI伺服器）。
- `src/loaders/db_writer.py`：實作 `upsert_theme_stock_mapping()` 與 `fetch_all_theme_baskets()`。
- `src/extractors/trend_discover.py`：升級 Gemini Prompt 支援單次請求同步辨識題材詞與 2~4 檔代表概念股（`{"trends": [{"theme": ..., "stocks": [...]}]}`），並向下相容傳統結構。
- 專項測試：`tests/test_thematic_mapping.py`（4 項 Schema、DBWriter 與 AI 解析測試全數 PASS，全套測試增至 **141 項**）。
- 狀態：`COMPLETE`。

### 13.11 Thematic Trends Extension: SB-TH2 — 題材情緒溢出特徵引擎

- `src/transform/feature_aggregator.py`：實作「直接個股情緒 + 題材溢出情緒」原位動態加權融合演算法（直接與題材兼備時 70/30 加權融合；無直接文章時 100% 題材溢出補位；嚴格維持 18 欄位契約與數值型態）。
- `src/loaders/db_writer.py` & `main_etl_pipeline.py`：擴充 `fetch_all_for_features()` 支援題材映射表讀取與特徵管線串接。
- `src/ui/data_loader.py`：特徵讀取邏輯同步支援題材溢出加權。
- 專項測試：`tests/test_thematic_feature_spillover.py`（4 項加權數學、補位、18 欄位契約與 ML 冠軍模型推論測試全數 PASS，全套測試增至 **145 項**）。
- 狀態：`COMPLETE`。

### 13.12 Thematic Trends Extension: SB-TH3 — Streamlit 題材雷達與一鍵選股 UI

- `src/ui/components.py`：實作 `render_thematic_radar()` 高質感深色題材雷達卡片（聲量、看多指數、多空情緒標籤與概念成分股點選按鈕）。
- `src/ui/data_loader.py`：實作 `load_thematic_radar_data()` 支援 PostgreSQL 題材與文章統計聚合，並提供精選離線 Fallback。
- `app.py`：頂部嵌入題材雷達卡片，支援點擊成分股按鈕秒速自動連動側邊欄與全畫面預測圖表（延遲 < 10ms）。
- 專項測試：`tests/test_ui_contracts.py`（新增題材雷達資料契約與元件渲染測試全數 PASS，全套測試增至 **147 項**）。
- 狀態：`COMPLETE`。

### 13.13 Real Articles & Transparency Extension: SB-ART1 ~ SB-ART3

- `src/ui/data_loader.py`：實作「個股實體 + 題材關聯 + 標題全域模糊比對」三重真實文章查詢引擎，徹底解決查無資料誤觸假模板問題。
- `src/ui/components.py`：淘汰偽造假文章內容模板，升級為透明化 Empty State 資訊卡片，並支援原文連結點擊。
- 專項測試：`tests/test_real_articles_pipeline.py`（新增 4 項三階查詢、去重與空資料契約測試全數 PASS，全套測試增至 **154 項**）。
- 狀態：`COMPLETE`。

## 14. Next Action

**Milestone B 已圓滿達成（Gate 0 至 Gate 6、Phase 3 與 Phase 4 全數關閉）**：

1. 本次更新將 `TRACEABILITY.md` 與 `PROJECT_STATUS.md` 最終治理狀態同步至 Git。
2. 產出 **「最終成果報告與求職作品集亮點總結（Executive Portfolio Summary）」**。
3. 專案具備完整 End-to-End 閉環，隨時可進行 GitHub 開源展示、面試技術展示與實體部署。

## 15. Deferred Risks / Technical Debt

- Gate 1：Implementation、functional verification、documentation sync 與 Final Gate Review 均已完成；Human Approval 已核准，Gate 1 `CLOSED`。
- Existing database migration safety（既有資料庫遷移安全）為 `NOT VERIFIED`；initializer 不得被當作 migration tool、legacy schema upgrade engine 或 repair tool。
- Legacy `daily_model_features` migration 與 FK redesign 仍為 Deferred。
- Gate 2：G2-SB1／G2-SB2／G2-SB3、Documentation Sync、Reviewer Documentation Review、Final Gate Review 與 Human Close 均已完成，Gate 2 `CLOSED`；real pandas、real Gemini、PostgreSQL integration 與 End-to-End behavior 仍為 `NOT VERIFIED`。
- Gate 3：G3-SB1／G3-SB2、Documentation Sync、Final Gate Review 與 Human Close 均已完成，Gate 3 `CLOSED`；live PostgreSQL writes、structured observability、direct TPEx official scraper 仍為 Deferred。Historical TPEx experiment 為 `REPORTED, NOT INDEPENDENTLY VERIFIED`。
- Gate 4：G4-SB1／G4-SB2、Documentation Sync、Final Gate Review 均已完成，Gate 4 `CLOSED`。
- Gate 5：G5-SB1／G5-SB2、Documentation Sync 均已完成；89 項測試通過。18 欄位特徵矩陣寫入 PostgreSQL（`daily_ml_features` Schema 升級與 DBWriter 擴充）依 Human 決策延後至 BI 儀表板 / Phase 3 階段再行評估與實作。目前維持現有 Database Schema 不變，避免在特徵工程探索階段擴大資料庫遷移範圍。Live 實體資料庫特徵持久化與 Phase 3 模型交叉驗證為 `NOT VERIFIED`。
- Human 指定每日固定時間抓取資料的 scheduling／operations decision 延至 Gate 6 之後再討論，屆時 PM 必須提醒 Human；目前不導入 scheduler／orchestration platform。
- Production security hardening（正式環境安全強化）仍包括 service-specific secrets；目前 Gate 0 決策保留 app／db 共用 `.env`。Local development PostgreSQL password rotation 為 Accepted Risk／Deferred Remediation，並受上述重新開啟 triggers 約束。

## 12. Safety Invariants

- 不讀出、顯示、記錄或提交 `.env` 的 secret value；`.env.example` 只能保留安全 placeholder。
- 不刪除、移動、改權限或修改 `.devcontainer/postgres-data/`；不得變更已核准的 PostgreSQL 18 bind mount／host persistence。
- Database backup 必須保存在 Repository 外；不得將 dump／backup 或 physical data 加入 Git。
- 未經明確批准，不 stage、commit、push、merge 或改寫 Git history。
- 每次只處理已批准 Gate／Small Batch；不得跨 Gate 順手修正。
- 完整且長期有效的安全規則以 Repository 根目錄 **`CLAUDE.md`** 為準（§11 Repository Safety、§11A 破壞性 Git 指令紀律、§12 Commit Policy）。
  `AGENTS.md` 已 Deprecated，僅為相容錨點，**不得作為現行規則依據**。

## 13. Read First in New Conversation

> **本節已由 §0.6 取代。** 舊清單第 1 項為 `AGENTS.md`（已 Deprecated），第 4 項的計畫書已封存至 `doc/archive/`。以下為更正後版本。

1. **`CLAUDE.md`** — 現行權威規則（取代舊清單的 `AGENTS.md`）
2. `doc/README.md` — 文件地圖
3. `doc/governance/PROJECT_STATUS.md` **§0** — 現行狀態
4. `doc/upgrade/gates/closed/SB1_GATE_A_PROPOSAL.md` 與 `closed/SB1_STEP1_BEFORE_SNAPSHOT.md` — 已於 Gate 0 完成並移入 `closed/`，本節整體已由 §0.6 取代，路徑僅供追溯
5. `doc/evidence/DECISIONS.md`
6. `doc/spec/PRD_Financial_Sentiment_System_v1.md`、`doc/spec/SDD_Financial_Sentiment_System_v1.md`
7. `src/transform/feature_aggregator.py`
8. `src/transform/data_cleaner.py`
9. `.env.example` 與目前 `git diff`／`git status`



