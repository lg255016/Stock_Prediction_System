# UG-Gate-2 啟動申請

> ## ⚠ 2026-09-01 超越註記 —— **本文為 2026-08-26 的申請快照**
>
> **Gate 2 的現行範圍以 `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 為準**
> —— 已由 7 個增為 **9 個 Small Batch**（`UG-G2-SB8` 見 DEC-029、`UG-G2-SB9` 見 DEC-031）。
> 另有一個獨立的 Migration SB（`UG-G2-MIG`，因 RISK-017 而生），亦不在本文的 7 個之內。
>
> **本文內的表格與數字刻意保持原樣，不予更新。** 它記錄的是
> **2026-08-26 當時申請了什麼**，那是一份治理紀錄；改寫它等於摧毀那個紀錄
> （同 §16.2 對 `archive/` 的原則、與契約 §4 那次的處置一致）。
>
> 要知道「現在有幾個 SB」，看 Master Plan §5.2；
> 要知道「當初申請了幾個」，看本文。**兩者都需要，而且必須是兩份文件。**

> **性質**：Gate 啟動申請，非實作授權。
> **提交日期**：2026-08-26
> **提交前狀態**：`src/` 與 `tests/` 未動（本次僅修改 `doc/upgrade/`；diff 為文件異動）
> **前置 Gate**：UG-Gate-1 已於 2026-08-26 由 PO 核准關閉（五個 Small Batch 全數 CLOSED，
> 最終 commit `1e469043e93b39f51b3655c72c6d70d227261904`）
> **准入條件覆核**：依 `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.1，UG-Gate-2 准入條件僅「UG-Gate-1 關閉」，
> 已滿足。UG-Gate-3 准入條件另加 RISK-015 情緒資料覆蓋率正式檢視，與本次 Gate 2 啟動無關

---

## 1. 申請範圍

UG-Gate-2「Feature Store & Data Pipeline」的 7 個 Small Batch。**逐個 SB 送審、逐個取得授權**，
不申請一次性授權全部 7 個——與 Gate 1 相同的逐批治理方式。

| SB | 名稱 | 主要影響 | Dependency |
|----|------|----------|-----------|
| UG-G2-SB1 | `daily_ml_features` Schema 擴充（7→29 欄） | `database/migrations/002_expand_ml_features.sql`（新）、`src/loaders/db_writer.py`、`src/transform/feature_aggregator.py` | UG-G1-SB4（Migration 機制） |
| UG-G2-SB2 | PTT 內頁留言解析 | `src/extractors/ptt_scraper.py` | 無 |
| UG-G2-SB3 | `market_articles` Schema 擴充 | `database/migrations/003_expand_articles.sql`（新）、`src/loaders/db_writer.py` | UG-G1-SB4（Migration 機制） |
| UG-G2-SB4 | 留言衍生特徵計算 | `src/transform/feature_aggregator.py`、`src/loaders/db_writer.py` | UG-G2-SB2 + UG-G2-SB3 |
| UG-G2-SB5 | Dcard Adapter（**CONDITIONAL**，不阻擋 Gate 2 關閉） | `src/extractors/dcard_scraper.py`（新）、`main_etl_pipeline.py` | Gate 0 交付物 D；若需新欄位另依賴 UG-G2-SB3 |
| UG-G2-SB6 | Stock Universe 建立（Point-in-Time） | `src/transform/universe_builder.py`（新）、`database/`（universe 相關表） | UG-G2-SB1 |
| UG-G2-SB7 | 批次化 ETL 引擎 | `main_etl_pipeline.py`、`src/extractors/twse_scraper.py`／`yfinance_api.py`／`ptt_scraper.py` | UG-G2-SB6 |

**建議執行順序**：維持 Master Plan 編號順序 SB1 → SB2 → SB3 → SB4 → SB5 → SB6 → SB7。
依上表 Dependency 欄核對，此順序滿足所有相依關係（SB4 需 SB2+SB3 皆已完成；SB6 需 SB1；
SB7 需 SB6；SB5 除 Gate 0 交付物 D 外無強制排序）。與 Gate 1 一致，維持逐 SB 授權，
不因這裡列出建議順序而跳過任何一批的個別 Gate A 審查。

---

## 2. 七個 SB 的 16／17 項 Brief 完整度稽核

### 2.1 稽核結果 —— 與 Gate 1 起始狀態的關鍵差異

**核心欄位集**（同 Gate 1 申請書 §2.1）：`Goal`／`Requirement Source`／`Current State`／
`Proposed Change`／`In Scope`／`Out of Scope`／`Affected Components`／`Data/API/Schema Contract`／
`Failure Semantics`／`Risks & Trade-offs`／`Tests`／`E2E Verification`／`Documentation Sync`／
`Rollback`／`Definition of Done`／`Gate A`／`Gate B`（共 17 項）。

| SB | 實際欄位數 | 現有欄位 | 缺少的核心欄位 |
|----|-----------|---------|---------------|
| UG-G2-SB1 | 8 | Goal／Dependency／In Scope／Out of Scope／Affected Components／Tests／Rollback／Definition of Done | Requirement Source／Current State／Proposed Change／Data-API-Schema Contract／Failure Semantics／Risks & Trade-offs／E2E Verification／Documentation Sync／Gate A／Gate B（共 10 項；`Dependency` 非核心欄位集之一，但為既有慣例保留） |
| UG-G2-SB2 | 8 | 同上 | 同上 |
| UG-G2-SB3 | 8 | 同上 | 同上 |
| UG-G2-SB4 | 8 | 同上 | 同上 |
| UG-G2-SB5 | 8 | 同上 | 同上 |
| UG-G2-SB6 | 8 | 同上（+ 本次新增之 RISK-015 提醒 blockquote，非表格欄位） | 同上 |
| UG-G2-SB7 | 8 | 同上 | 同上 |

**與 Gate 1 申請書的關鍵差異，必須誠實指出**：Gate 1 申請時，五個 SB 已各有 17～18 項
完整欄位（§2.1 稽核結果為「缺少的核心欄位：無」）。**Gate 2 並非如此**——
`SYSTEM_UPGRADE_MASTER_PLAN.md` §8 前言原文即明寫：

> 「Brief 完整度說明：以下 SB briefs 列出核心設計意圖（至少 8 項）。**完整 16 項 Brief 在
> Gate 2 規劃階段產出。**」

也就是說，文件本身在 Gate 0 時期就已經承認 Gate 2 的 Brief 是**故意留白**、要等到
「Gate 2 規劃階段」才補齊——而現在正是那個階段。這不是遺漏，是既定的分階段設計
（`small-batch-orchestrator` skill §2：「後續 Gate 只需核心欄位，各 Gate 開工前才補成完整 Brief」）。

### 2.2 本次不在這份申請書裡把 7 份 Brief 補到 17 項的理由

依 `small-batch-orchestrator` skill 的既有規則，完整 Brief 應「經 PO 審查」，且 §4 明文
「一次一個 SB」——若在本次啟動申請裡一口氣把 7 個 SB 的 Requirement Source、Data/API/Schema
Contract、Failure Semantics、E2E Verification 等實質內容全部寫完，等同一次做完 7 個 SB
的 Gate A 等級規劃工作，違反逐批攔截的精神，也會讓您在單一份文件裡要消化過多決策點。

**因此比照 Gate 1 申請書 §2.2 的既定作法**：本次啟動申請只做**完整度稽核**與
**已知需調整項**（見 §2.3），**不在此補齊 7 份完整 Brief**——每個 SB 的完整 16／17 項
內容，將於**該 SB 自己的 Gate A 提案階段**個別產出、個別審查，與 Gate 1 每個 SB 的
實際運作方式一致。

### 2.3 Gate 1 收尾後發現、需要回頭補進 Gate 2 Brief 的項目

比照 Gate 1 啟動申請書 §2.2 的做法，逐一核對 Gate 1 五個 SB 收尾後新增的機制／契約，
是否已反映在 Gate 2 現有的 8 項精簡 Brief 中：

| SB | 需調整處 | 原因 |
|----|---------|------|
| **UG-G2-SB1** | `In Scope` 應明確引用 `database/apply_migrations.py`（UG-G1-SB4 建立）作為套用 `002_expand_ml_features.sql` 的機制，而非讓 Migration 檔案懸空、未指明由誰執行 | 原文僅寫「`002_expand_ml_features.sql` Migration」，未點名執行路徑。UG-G1-SB4 已建立 `assert_safe_migration_target()` 強制護欄，任何新 Migration 都應透過 `apply_migrations.py` 套用，才能享有該護欄保護 |
| **UG-G2-SB3** | 同上——`003_expand_articles.sql` 同樣應明確透過 `apply_migrations.py` 套用 | 同上 |
| **UG-G2-SB1**、**UG-G2-SB3** | `Risks & Trade-offs`（待補齊時）應引用 RISK-006（Migration 失敗風險，`REMAINING_RISKS.md`）現況——隔離容器驗證與 Transaction rollback 已驗證，pg_dump 備份還原**尚未驗證**；這兩個 SB 是 Gate 1 之後第一批新增的真實 Migration，該剩餘缺口與它們直接相關 | RISK-006 於 UG-G1-SB4 收尾時已標註「部分驗證」，其未驗證範圍會在下一次真正需要 rollback 到 pg_dump 備份的情境下才會被觸發，SB1／SB3 是最早可能踩到此缺口的 SB |
| **UG-G2-SB6** | ✅ 已於本次一併處理——見 §5.1（RISK-015 情緒資料覆蓋率提醒） | 使用者本次明確指示的項目 |
| **UG-G2-SB1** | 澄清用小提醒（非缺陷）：Brief 中的「29 欄」與 SB5（Gate 1）修正過的「18→`LEGACY_17`」是**兩個不同的數字**，不應混淆——29 是 `daily_ml_features` 的**總欄位數**（`FEATURE_REGISTRY.md` §2，含 context／features／metadata），17 是**模型輸入特徵數**（`LEGACY_17`）。`gate0_contract_check.py` 的 `AUTHORITATIVE_COLUMNS=29` 與 `AUTHORITATIVE_ASSERTIONS=10` 兩個常數也是針對這個 29 欄契約，非 17 欄契約 | Gate 1 SB5 才剛處理過一輪「18 欄位」裸寫混淆問題，這裡先澄清避免 Gate 2 開工後重蹈類似的數字混淆 |
| 全部 7 個 SB | `Tests` 欄／未來補齊之 E2E Verification 欄，執行環境須比照 Gate 1 慣例標明為 dev container（`CLAUDE.md` §13.0），非 host | 與 Gate 1 申請書 §2.2 第三項相同的既有慣例，此處延續適用 |

**本申請不修改各 SB 現有的 8 項精簡 Brief 內容本身**（`In Scope` 等欄位文字維持原樣）——
上述調整待 PO 核准 Gate 2 後，於各 SB 的 Gate A 階段撰寫完整 Brief 時一併納入，
與 Gate 1 申請書 §2.2 的處理方式相同。**已直接處理的例外**：RISK-015 相關的 SB6
提醒與 Gate 3 准入條件已於本次一併寫入 `SYSTEM_UPGRADE_MASTER_PLAN.md`（§5.1、§8 SB6 段），
因為這是使用者本次明確指示要做的部分，不宜再推遲到 SB6 自己的 Gate A 階段。

---

## 3. High 風險處置說明

依 `REMAINING_RISKS.md` 準則 1，High 風險須 PO 明確簽核 Accept／Mitigate／Defer。

### 3.1 適用範圍釐清

| 風險 | 影響 Gate | 是否阻擋 Gate 2 開工 |
|------|----------|---------------------|
| **RISK-012** | UG-G2-SB6 | **是**——直接落在本 Gate，且已有明確設計解法 |
| **RISK-015**（本次新增） | UG-G2-SB6, Gate 3 啟動前 | **否**——量測能力可在 Gate 2 內建立，但「覆蓋率是否足夠」的判斷本身明確延後至 Gate 3 啟動前，不阻擋 Gate 2 SB6 依流動性排名建立 Universe |

### 3.2 RISK-012：未採 Point-in-Time Universe 導致存活偏誤

| 項目 | 內容 |
|------|------|
| 現況標籤 | `PLANNED` |
| 建議處置 | **Mitigate（緩解，已有設計）——延續 Gate 1 啟動申請書 §3.4 的既有裁決** |

`doc/governance/PROJECT_STATUS.md` §0.2 已記載「RISK-012 `Mitigate`」為既定狀態（該裁決發生於
Gate 1 核准當時，本申請書僅重申並延續，非重新裁決）。緩解措施仍是 DEC-017（PIT Snapshot、
`universe_effective_date`、歷史回測載入當期 Universe），驗收條件仍是 UG-G2-SB6 的三項 PIT
測試（`test_universe_point_in_time_no_future_data` 等）通過。**此裁決在 Gate 2 實際開工
UG-G2-SB6 前無需重新提出，除非 PO 認為情況有變。**

### 3.3 RISK-015：情緒／討論資料覆蓋率未知（本次新增）

| 項目 | 內容 |
|------|------|
| 現況標籤 | `HYPOTHESIS` |
| 建議處置 | **Defer（延後至 Gate 3 啟動前正式檢視）** |

**理由**（與使用者本次裁決一致，完整內容見 `REMAINING_RISKS.md` RISK-015）：

1. 覆蓋率是否結構性不足，**只有在真實資料透過 `source_status` 累積一段時間後才能量測**。
   Gate 2 完全不做「情緒資料是否足夠」的判斷，只建立量測能力（`source_status` 值域）。
2. UG-G2-SB6 維持流動性排名為**暫定標準**，非以覆蓋率為依據，文件已明確標註此為暫定。
3. 現在做 Accept 或 Mitigate 決策都缺乏依據——與 Gate 1 申請書 §3.3 RISK-010 的判斷邏輯
   相同（不同的是 RISK-010 談的是股價資料樣本量，RISK-015 談的是情緒資料覆蓋率，
   兩者都要等 Panel Dataset／Universe 實際建立後才有數字）。

**Defer 的具體條件**：於 Gate 3 啟動前，以 UG-G2-SB1／SB6 累積之真實 `source_status`
資料重新評估並提交 PO 簽核，方可進入 Gate 3。已寫入 `SYSTEM_UPGRADE_MASTER_PLAN.md` §5.1
Gate 3 准入條件欄，非僅存在於風險登錄表。

---

## 4. 已知的驗證方法論注意事項（非阻擋項，供預覽）

Gate 1 的 UG-G1-SB1 曾發現「HERM 測試在空 DB 環境下走 mock 路徑、對真正修改的模組零證據價值」
這個結構性陷阱（詳見 `GATE1_STARTUP_APPLICATION.md` §4）。UG-G2-SB1／SB3（Schema 擴充後
`db_writer.py` 的寫入路徑）與 UG-G2-SB6（Universe 建構）同樣涉及真實 DB 互動路徑，
**可能重現同一類「測試在孤立環境下繞過真正修改的程式碼」問題**。

本申請**不在此預先設計對應方案**——依 Gate 1 的既有經驗，這類問題需要在該 SB 實際
盤點測試覆蓋歸屬時才能確認是否真的發生（不能用假設推論）。列在此處僅作為**開工提醒**，
供各 SB 自己的 Gate A 階段評估測試計畫時參考，非本次裁決事項。

---

## 5. 本次一併處理的項目（先於各 SB 個別 Gate A 完成）

### 5.1 RISK-015：情緒資料覆蓋率風險登錄（使用者本次明確指示）

已完成，非本申請書待辦：

- `doc/upgrade/contracts/REMAINING_RISKS.md`：新增 RISK-015（HYPOTHESIS，High），
  納入風險摘要（By Severity／By Category）與頁首「Gate 0 後追加項目」清單。
- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`：
  - §5.1 Gate 總覽表，UG-Gate-3 准入條件欄新增「RISK-015 情緒資料覆蓋率正式檢視」。
  - §8 UG-G2-SB6 Brief 表格後新增 RISK-015 提醒 blockquote。
  - §9 UG-Gate-3 前言新增「准入前置條件」blockquote，說明 Gate 3 開工前須以真實
    `source_status` 資料重新評估，而非沿用 Gate 2 規劃時的假設。
- `source_status`（`SUCCESS`／`SUCCESS_EMPTY`）在題材溢出情形下的標記邏輯，
  依使用者裁決**不在此定案**，留待 UG-G2-SB1 Gate A 提案隨量測邏輯實際設計一併處理。

---

## 6. 請求 PO 裁決事項

| # | 事項 | 需要的決定 |
|---|------|-----------|
| 1 | RISK-012 處置 | 確認延續 Gate 1 既有裁決（Mitigate），本次不重新裁決 |
| 2 | **RISK-015** 處置 | Accept／Mitigate／Defer（建議 Defer 至 Gate 3 啟動前，§3.3） |
| 3 | Gate 2 啟動 | 是否核准；若核准，是否採「逐 SB 授權」（本申請的預設，與 Gate 1 相同） |
| 4 | SB 執行順序 | 是否維持 SB1 → SB2 → SB3 → SB4 → SB5 → SB6 → SB7（§1 已核對滿足依賴矩陣） |
| 5 | Brief 完整度處理方式 | 是否認可「本次不補齊 7 份完整 Brief，各 SB 於自己的 Gate A 階段個別補齊」的處理方式（§2.2），而非現在一次寫完 7 份 |
| 6 | §2.3 列出的需調整項 | 是否認可這些項目（`apply_migrations.py` 引用、RISK-006 引用、29 vs 17 澄清）於各 SB 自己的 Gate A 階段一併納入，而非現在就修改 Master Plan 的 8 項精簡 Brief 內容 |

---

## 7. 未獲核准前的自我約束

- 不修改 `src/`、`tests/`、`database/`
- 不修改 Master Plan 各 SB 的 8 項精簡 Brief 內容本身（§2.3 列出的調整待核准後，於各 SB
  Gate A 階段提出；RISK-015 相關的 SB6 提醒與 Gate 3 准入條件為使用者本次明確指示之例外，
  已直接處理，見 §5.1）
- 不執行任何 DB migration
- 不 Commit（本申請文件、`REMAINING_RISKS.md`、`SYSTEM_UPGRADE_MASTER_PLAN.md` 之異動除外，
  且需 PO 授權）
