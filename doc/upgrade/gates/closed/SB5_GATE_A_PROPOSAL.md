# UG-G1-SB5 Gate A 提案：文件全面校正（Gate 1 最後一個 Small Batch）

> 狀態：**Gate A 審查中**（尚未實作，未動 `src/`／`database/`／schema）
> 日期：2026-08-26
> 前置：UG-G1-SB1～SB4 均已 `CLOSED`（見 `doc/governance/PROJECT_STATUS.md` §0.2）
> 本提案撰寫依據：**逐項對實際檔案重新核對**，不沿用 `SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 的 Gate-0 時期 Brief 文字（理由見 §1）

---

## 0. 摘要

SB5 是 Gate 1 最後一個 Small Batch，範圍**純文件修正**，不改 `src/`、不改 `database/`、不改任何 Schema，
不涉及任何寫入路徑或執行邏輯。目標是修復 `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` 登錄、且**現行仍歸屬
UG-G1-SB5** 的文件漂移項目。

**核心結論（先講重點）**：`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 對 SB5 的既有 Brief 文字**已過期**——
它是 Gate 0（2026-08-22／23）當時寫的，此後 SB1～SB4 四個 Small Batch 的收尾文件同步已經：
(a) 提前修掉了原本 14 項漂移中的 4 項（DRIFT-008、009、012、018 的部分）、
(b) 把另外 2 項移出 SB5 範圍（DRIFT-003 → UG-G2-SB1；DRIFT-014 → UG-G2-SB2）、
(c) 讓「測試數＝154」「14 項漂移」這兩個 Brief 本身依賴的數字雙雙變成新的過期宣稱。

依 `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md` 目前的「修復工單對照」表（第 94 行），
SB5 現行**實際**owned 範圍是：

| 漂移 ID | 嚴重度 | 現況（本次重新核對） |
|---------|--------|----------------------|
| DRIFT-001 | CRITICAL | **仍開放** |
| DRIFT-002 | CRITICAL | **部分已修**（SB3 順帶修掉 2/3，剩 1 處仍開放） |
| DRIFT-004 | HIGH | **仍開放，且比登錄時更嚴重**（見 §2.3） |
| DRIFT-005 | HIGH | **仍開放** |
| DRIFT-006 | HIGH | **仍開放** |
| DRIFT-007 | HIGH | **仍開放** |
| DRIFT-010 | HIGH | **仍開放** |
| DRIFT-013 | MEDIUM | **仍開放，且比登錄時更嚴重**（見 §2.6） |
| DRIFT-015 | CRITICAL（僅文件標註部分歸 SB5） | **仍開放** |

**不在 SB5 範圍**（已於 SB1～SB4 收尾時處理，或已被工單對照表改派）：DRIFT-003、008、009、011、012、014、016、017、018——
詳見 §2.9。

---

## 1. 為何不能直接照抄 §7.1 Brief（重新核實的必要性）

`SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1（UG-G1-SB5 章節，第 583～604 行）目前寫的是：

```
Requirement Source | 交付物 A (DOCUMENT_DRIFT_REMEDIATION.md); DRIFT-001~014
Current State       | 14 項漂移：3 CRITICAL + 8 HIGH + 3 MEDIUM
Tests                | grep 驗證: 禁用詞 = 0; 特徵數引用均附契約名; 測試數 = 154; SDD 模組狀態 = 已實作
Definition of Done   | A 表所有 Critical/Major 項目關閉; grep 驗證通過; 全套現有 154 測試仍 PASS
```

這段文字寫於 Gate 0 核准當下（PO 於 2026-08-23 核准），**在 SB1～SB4 四個 Small Batch 展開之前**。
這四個 SB 的收尾工作各自順帶同步了部分文件（`DECISIONS.md`、`TRACEABILITY.md`、
`DOCUMENT_DRIFT_REMEDIATION.md` 本身、`PROJECT_STATUS.md`、`SDD_Financial_Sentiment_System_v1.md`），
其中一些同步**恰好覆蓋了原本規劃要留給 SB5 做的項目**（例如 SB3 收尾時已把 SDD 的
`model_trainer.py`／`app.py` 規劃中標記改成已實作，這原是 DRIFT-002 的一部分）。

依 `CLAUDE.md` §9A.1（「驗證必須為偵測而寫，不是為通過而寫」）同一原則類推到文件盤點：
**若直接照抄一份四個 SB 之前寫的清單當作本次的 Current State，這份清單結構上就不可能反映
中間四次側寫已經造成的變化**——它只會不斷重複同一批陳舊數字。因此本提案的 §2 全部
重新對實際檔案做過 `grep`／`Read` 核對，而非引用 Brief 或 `DOCUMENT_DRIFT_REMEDIATION.md`
登錄時的舊敘述。

---

## 2. 逐項現況重新核對

### 2.1 DRIFT-001／DRIFT-007（CRITICAL／HIGH）—— 特徵數裸寫「18 欄位」

**登錄原文宣稱**：`model_trainer.py:L17-41` 實際定義 17 項特徵，但 PRD/SDD/DECISIONS.md 多處仍寫死「18 欄位」。

**本次重新核對（`VERIFIED THIS SESSION`）**：

| 位置 | 現況 | 精確引用 |
|------|------|---------|
| `PRD_Financial_Sentiment_System_v1.md:L65` | 仍為裸數字 | 「機構級特徵矩陣 **(18 欄位契約)**」 |
| `PRD_Financial_Sentiment_System_v1.md:L68` | 仍為裸數字 | 「運用 **18 欄位**歷史特徵矩陣」 |
| `SDD_Financial_Sentiment_System_v1.md:L246` | 仍為裸數字（**且同時命中禁用詞，見 §2.7**） | 「特徵矩陣嚴格維持 **18 欄位契約**與型態……推論 **100%** **零誤差**相容」 |
| `DECISIONS.md:L551`（DEC-006） | 仍為裸數字 | 「FeatureAggregator 輸出 **18 項**標準特徵矩陣」 |
| `DECISIONS.md:L607`（DEC-007） | 仍為裸數字 | 「純價量 9 特徵 vs 多模態 **18 特徵**」 |
| `DECISIONS.md:L617`（DEC-007） | 仍為裸數字 | 「實驗組：……多模態 **18 欄位**特徵」 |
| `DECISIONS.md:L724, L729`（DEC-009） | 仍為裸數字（**L729 同時命中禁用詞，見 §2.7**） | 「破壞 Phase 3 嚴格建立的 **18 欄位** ML 資料契約」；「**18 欄位**特徵契約與數值型態 **100%** 保持不變……**零誤差**無縫推論」 |

**已存在、可直接引用的權威版本化契約**（Gate 0 已核准，SB5 不需重新設計）：
`doc/upgrade/contracts/FEATURE_REGISTRY.md` 已完整定義 `LEGACY_17`（17，現行）／`CORE_16`（16，計劃中）／
`COMMENT_ENHANCED_19`（19，計劃中），以及 29 欄完整契約。SB5 的工作**只是把上述 7 處裸寫的「18」
改成引用這三個版本化契約名稱**，不是重新設計契約。

**額外佐證**：`gate0_contract_check.py` 的 B11 檢查（`SYSTEM_UPGRADE_MASTER_PLAN.md:L1225`）
本身已把 `DECISIONS.md:577`（即 DEC-007 附近）登記為已知遺留、排定 UG-G1-SB5 修訂的 WARN 項，
不是本次新發現，而是 Gate 0 當時就已經預見並排入 SB5 範圍。

**PRD/SDD 屬於「現行文件」（`doc/spec/`），可直接修正**。`DECISIONS.md` 屬於 `doc/evidence/`，
修正方式見 §4 PO 決策點 1。

---

### 2.2 DRIFT-002（CRITICAL）—— SDD 模組狀態標記

**登錄原文宣稱**：`trend_discover.py`、`model_trainer.py`、`dashboard.py` 三處標記「⏳ 規劃中」，
但三個模組事實上都已實作並有測試。

**本次重新核對（`VERIFIED THIS SESSION`）**：

```bash
grep -n "規劃中\|⏳" doc/spec/SDD_Financial_Sentiment_System_v1.md
```

全檔僅剩**一處**命中：

```
68:*   **⏳ `trend_discover.py` (規劃中 - TrendDiscover)**：整合 AI 自動探索熱門財經詞彙……
```

`model_trainer.py`／`app.py`（原登錄的 `dashboard.py`，專案實際採 `app.py` + `src/ui/` 架構，並無
獨立 `dashboard.py` 檔案）兩處已在 **UG-G1-SB3 收尾時**改為 ✅（`SDD_Financial_Sentiment_System_v1.md`
「應用與ML層」章節，SB3 Gate B 已完整記錄該次修正）。

**確認 `trend_discover.py` 確實已實作、非規劃階段**：

```bash
ls src/extractors/trend_discover.py               # 存在
grep -rln "trend_discover\|TrendDiscover" tests/   # 被 5 份測試檔引用
```

命中：`test_db_read_semantics.py`、`test_nlp_checkpoint_semantics.py`、`test_operational_ux.py`、
`test_thematic_mapping.py`、`test_tracking_keyword_integrity.py`。

**結論**：DRIFT-002 現況為**部分已修**——2/3 已在 SB3 順帶修正，剩 `trend_discover.py` 這一處（位於
SDD「收集層」章節，與 SB3 動到的「應用與ML層」章節不同段落，因此未被 SB3 覆蓋）仍需 SB5 處理。

---

### 2.3 DRIFT-004（HIGH）—— PROJECT_STATUS.md 測試計數

**登錄原文宣稱**：`PROJECT_STATUS.md:L8` 寫「133/133 tests PASS」，實際 grep 出 154。

**本次重新核對（`VERIFIED THIS SESSION`）**：

```bash
grep -ch "def test_" tests/test_*.py | awk '{s+=$1} END {print s}'   # 200
ls tests/test_*.py | wc -l                                            # 21
```

**現況比登錄時更複雜**——`PROJECT_STATUS.md` 目前**同時存在三個互相矛盾的數字**，
沒有一個等於真實的 200：

| 行號 | 文字 | 數字 | 狀態 |
|------|------|------|------|
| L58 | 「§1 記載的「133/133」是 2026-08-20 的舊數字，**已過期**」 | 133 | 已自行標註過期（§1 舊紀錄本身不需改，見下方說明） |
| L55-56 | 「**164 tests / OK**……較 GOV-02 基線 154 增加 10 個」 | 164 | 這是 §0.4，**當前現行狀態區塊**，SB1 收尾時寫定，未再更新 |
| L748 | 「全套測試增至 **154 項**」 | 154 | 舊版描述，SB1 之前的狀態 |

即：**§1 是刻意保留的舊紀錄快照（PRE_CODEX 時期，文件開頭已聲明「先讀 §0，§1 以下為舊紀錄」），
不需要修正**；真正需要修正的是 **§0.4**（現行狀態區塊）的「164」，因為 SB2／SB3／SB4 三個 SB
之後又各自新增了測試，此數字從未在後續 SB 收尾時同步更新，目前落後真實值 36 個。

**修正方式建議沿用 §0.4 既有的免責聲明模式**（「請以下列指令重新核對，不要引用文件裡的舊數字」），
把數字改為 200，並維持「附可重跑指令」的寫法，而不是寫死一個未來仍會再度過期的數字。

---

### 2.4 DRIFT-005（HIGH）—— DEC-003 內容截斷

**登錄原文宣稱**：DEC-003「NLP Completion Contract」段落在 Option A 單行描述後直接截斷，
缺 Decision／Rationale／Affected Components／Verification。

**本次重新核對（`VERIFIED THIS SESSION`）**：`Read doc/evidence/DECISIONS.md:170-201`，
確認內容確實在第 199-200 行戛然而止：

```
199	1. **Option A — Strict LLM Completion（嚴格 LLM 完成）**：非 fuzzy SnowNLP result 可完成
200
201	## DEC-004：Gate 3 設定生命週期與 MVP 股票識別邊界
```

第 199 行本身是不完整句子（無句號、無下文）。**仍完全開放，SB1～SB4 均未觸碰 DEC-003**。

修正涉及是否可編輯 `doc/evidence/DECISIONS.md` 既有 ADR 內文，見 §4 PO 決策點 1。

---

### 2.5 DRIFT-006（HIGH）—— DEC-004 重複區塊

**登錄原文宣稱**：`DECISIONS.md:L315-432` 與 `L206-313` 幾乎逐段重複。

**本次重新核對（`VERIFIED THIS SESSION`）**：`Read doc/evidence/DECISIONS.md:239-434` 全文比對，
確認**不是逐字重複，而是同一決策的兩個不同時間點快照被前後相鄰保留**：

- 第 240-313 行：**較新版本**——狀態為「G3-SB1 與 G3-SB2 均已實作」「正式 `COMPLETE`」，
  Affected Components 同時列出 G3-SB1 與 G3-SB2 的異動路徑。
- 第 315-432 行：**較舊版本**——狀態為「G3-SB1 已實作／測試」但 Canonical ID
  「尚未實作或驗證」，Gate 3 標為 `ACTIVE` 未關閉，只列 G3-SB1 的異動路徑（不含 G3-SB2）。

即：舊草稿在後、定案版本在前，中間銜接處直接從新版本跳回舊版本重述一次 Context/Problem/
Alternatives/Decision/Rationale/Trade-offs/Affected Components/Verification 全套結構。**仍完全
開放，SB1～SB4 均未觸碰 DEC-004**。

---

### 2.6 DRIFT-010（HIGH）—— 缺少頂層 README.md

**本次重新核對（`VERIFIED THIS SESSION`）**：

```bash
ls README.md   # No such file or directory
```

**仍完全開放**，Repository 根目錄至今無任何 `README.md`。

---

### 2.7 DRIFT-013（MEDIUM）—— PROJECT_STATUS.md「Current HEAD」快照落後

**登錄原文宣稱**：`PROJECT_STATUS.md:L23`（現行位置為 `L115`）寫死 `a41a9ea`，
實際 HEAD 已是 `680de6c`。

**本次重新核對（`VERIFIED THIS SESSION`）**：

```bash
git log --oneline -1
# 5fa50d1 docs(governance): close UG-G1-SB4, archive gate docs per CLAUDE.md §16.3
```

**現況比登錄時更落後**——登錄時的「實際 HEAD」`680de6c` 本身現在也已經過期，
中間又經過 SB2／SB3／SB4 共十餘個 commit，目前真實 HEAD 是 `5fa50d1`。這**印證了
登錄建議的修正方向本身是對的**（`DOCUMENT_DRIFT_REMEDIATION.md` 對此項的建議：
「加入『此欄位為手動快照，實際狀態以 `git log` 為準』的免責聲明」）——與其每次 SB
收尾都手動追這個數字、每次都會再度過期，不如直接改成指令化免責聲明（沿用 §0.4
已經在用的模式）。

---

### 2.8 DRIFT-015（CRITICAL，僅文件標註部分歸 SB5）—— DEC-007 證據基礎標註

**登錄原文宣稱**：DEC-007「多模型橫向競技」宣稱 4 大模型×2 特徵集＝8 組平行對照實驗，
但 GOV-02 實測發現 host 環境下 `lightgbm`／`xgboost`／`random_forest` 三個模型名稱
實際對映到同一個 fallback 類別，方法論上「比較」本身不成立（除非在 dev container 內執行）。

**本次重新核對**：SB3 已經處理了排行榜的**呈現機制**（`load_tournament_results()` 動態載入 +
`DataMode.EMPTY` 正確反映「尚無真實 artifact」），但**尚未在真實 artifact 產出**（資料量不足，
`models/` 目錄不存在，SB3 Gate B 已明確標註為 `NOT VERIFIED`）。因此 DRIFT-015 原本擔心的
「host 產出的誤導性數字流入 UI」目前**不存在**（因為根本沒有任何 tournament 數字被產出、
無論來自 host 或 container）。

但 DRIFT-015 真正登錄的問題不是「UI 現在有沒有顯示假數字」，而是 **`DECISIONS.md` 的 DEC-007
本文**——它敘述 8 組實驗的方法論時完全沒有標註「此方法論只在 dev container 內成立，host 環境
下 4 模型實際只有 2 種相異實作」這個 GOV-02 已驗證的限制。SB5 owned 的部分僅止於**在 DEC-007
或鄰近位置補上這個標註**，不含 UG-G3-SB3/SB7 負責的「容器內重跑並產出真實數據」。

修正涉及是否可編輯 `DECISIONS.md` 既有 ADR 內文，同樣見 §4 PO 決策點 1。

---

### 2.9 不在 SB5 範圍的項目（確認排除，避免重工）

| 漂移 ID | 現況 | 排除理由 |
|---------|------|---------|
| DRIFT-003 | 已改派 | 工單對照表明確歸 `UG-G2-SB1`（Feature Store Schema 擴充，屬 Gate 2） |
| DRIFT-008 | 已於 SB3 收尾修正 | 排行榜靜態→動態，`PROJECT_STATUS.md` SB3 列已記錄同步 |
| DRIFT-009 | 已於 SB2 收尾修正 | DEC-012 方案 B，`data_loader.py` 四函式改回傳 `(value, DataMode)` |
| DRIFT-011 | 已於 SB4 收尾修正 | Migration 機制（`schema_version` + `apply_migrations.py`） |
| DRIFT-012 | 已於 SB1 收尾修正 | Purged Walk-Forward，DEC-011 |
| DRIFT-014 | 已改派 | 工單對照表明確歸 `UG-G2-SB2`（PTT 內頁留言解析，屬 Gate 2） |
| DRIFT-016 | 已改派 | GOV-03 已緩解（`requirements.lock.txt`），根治待 PO 另外指定，非 SB5 範圍 |
| DRIFT-017 | 已處理 | 孤兒 bytecode 已於 2026-08-23 清除並登錄 |
| DRIFT-018 | 已於 SB3 收尾修正（讀取機制部分） | 歸屬已由 SB2 改判給 SB3；矛盾之一待真實 artifact 產出後才能實測，非 SB5 範圍 |

**注意**：`DOCUMENT_DRIFT_REMEDIATION.md` 本身的「修復工單對照」表對 DRIFT-012／009／008／011
四列目前仍標「已修正，**尚未 commit**」/「待 commit」字樣（第 90-93 行），但這四項實際上
**已經各自完成 Gate B 並 commit**（分別是 `ccf0e52a`、`414fcc81`、`61016ee1`、`d2a4d489`/`0fdb9c50`）。
這是否一併於 SB5 更新為「CLOSED（commit hash）」，屬 §4 PO 決策點 2。

---

## 3. 新發現、不在原始漂移登錄中的項目

以下是本次重新核對過程中發現、但 `DOCUMENT_DRIFT_REMEDIATION.md` 原始 18 項登錄未涵蓋的問題。
是否併入 SB5 範圍，列為 §4 PO 決策點 3。

### 3.1 禁用詞命中（`CLAUDE.md` §9.2）

```bash
grep -rniE "100% reliable|perfect|enterprise-grade|production-ready|guaranteed|completely prevents|永遠不會|完美解決|零誤差" doc/spec doc/governance doc/evidence
```

命中兩處，**均與 DRIFT-001／007 的裸寫「18 欄位」同一句**（見 §2.1 表格已標註）：

- `SDD_Financial_Sentiment_System_v1.md:246` ——「……**100%** 零誤差相容」
- `DECISIONS.md:729` ——「……**100%** 保持不變……**零誤差**無縫推論」

這兩處沒有對應的實測證據支撐「100%」「零誤差」這種絕對化宣稱（沒有任何一次驗證記錄
逐一比對過新舊特徵矩陣在所有數值上零誤差），屬於 §9.2 明文禁用詞。SDD 那一處屬於
`doc/spec/` 現行文件，可直接修正；`DECISIONS.md` 那一處同樣落入 §4 PO 決策點 1。

### 3.2 SDD 檔案清單表未列出 SB4 新增的兩個 Migration 相關檔案

`SDD_Financial_Sentiment_System_v1.md` 的「Schema Migration Boundary」敘述性小節
（SB4 收尾時新增）已經提到 `apply_migrations.py`／`db_target_guard.py`，但 SDD §2
「專案目錄與檔案說明」的逐檔案表格本身**沒有**把 `database/apply_migrations.py`、
`database/db_target_guard.py`、`database/migrations/001_baseline.sql` 列為獨立條目
（其他模組如 `data_cleaner.py`、`trend_discover.py` 都是表格逐條列出）。

這是敘述性文字已涵蓋、但表格化清單遺漏的**輕微**不一致，非阻擋級問題，建議可一併順手補上
（成本低，SDD 該表格本來就是 SB5 這次會動到的檔案）。

---

## 4. PO 決策點

### 決策點 1：`doc/evidence/DECISIONS.md` 既有 ADR 內文是否可編輯

`CLAUDE.md` §16.1 明定 `doc/evidence/` 生命週期為「只增不減」，且本 session 迄今對
`doc/evidence/*.md` 的處理慣例，是「只增補新內容（新 DEC 條目、新增章節），不回頭改寫
既有條目的敘述文字」。但 `DOCUMENT_DRIFT_REMEDIATION.md` 自身對 DRIFT-005／006／007／015
開出的修復建議，明確要求**修改既有 ADR 的內文本身**：

- DRIFT-005：「從 Git 歷史或原始草稿還原 DEC-003 NLP Completion Contract 完整內容」
- DRIFT-006：「移除 L315-432 的重複內容，保留 L206-313 的權威版本」
- DRIFT-007：「（DEC-006/DEC-007）統一改用版本化契約名稱，消除硬編碼數字」
- DRIFT-015：「須明確標註 DEC-007 的證據基礎僅在 dev container 內成立」

這是 `CLAUDE.md` §0.2 定義的「規格衝突」情境（§16.1 的『只增不減』字面上與 Gate 0 已核准的
`DOCUMENT_DRIFT_REMEDIATION.md` 修復計畫互相矛盾），依規則不得自行選一個版本當答案。

**需要 PO 選擇下列其中一種處理方式**：

- **方案 A**：`DECISIONS.md` 既有 ADR 內文視為可修正對象——DRIFT-005 補回截斷內容、
  DRIFT-006 刪除重複區塊、DRIFT-007 改用版本化契約名稱、DRIFT-015 於 DEC-007 補標註。
  這是 `DOCUMENT_DRIFT_REMEDIATION.md` 原始建議的做法。
- **方案 B**：`DECISIONS.md` 既有 ADR 內文視為歷史記錄不可回改——改為**新增一則 DEC**
  （例如 DEC-022「歷史 ADR 記錄缺陷登錄」），在新條目中指出 DEC-003 截斷、DEC-004 重複、
  DEC-006/007 特徵數裸寫、DEC-007 證據基礎限制這四件事，並附上正確資訊，但不動 DEC-003/004/006/007/009
  原文一個字。
- **方案 C**：兩者混合——`doc/spec/`（PRD/SDD）與 `PROJECT_STATUS.md`／`TRACEABILITY.md` 等
  「現行文件」全部直接修正（無此爭議，本來就會持續更新）；僅 `DECISIONS.md` 既有 ADR 段落
  採方案 B 的新增條目做法。

若無 PO 明確選擇，SB5 預設**不修改** `DECISIONS.md` 既有 ADR 內文（採方案 B 的保守路線），
僅新增一則說明性 DEC 條目。

### 決策點 2：`DOCUMENT_DRIFT_REMEDIATION.md` 的「修復工單對照」表是否於本次一併更新

§2.9 提到的四列（DRIFT-012／009／008／011）目前仍寫「待 commit」，但實際已 CLOSED。
是否於 SB5 一併把這四列的狀態欄位更新為對應 commit hash？此為低風險的表格欄位更新
（不涉及該文件本身的『只增不減』爭議，因為只是更新既有欄位的狀態值，不刪除任何列）。

### 決策點 3：§3 新發現項目是否併入 SB5 範圍

§3.1（禁用詞，兩處各屬 `doc/spec/` 與 `doc/evidence/`，`doc/spec/` 那處無爭議可直接修，
`doc/evidence/` 那處併入決策點 1 處理）與 §3.2（SDD 檔案清單表補齊 3 個檔案條目）
是否併入本次 SB5，或另開一個更小的 Small Batch／留待下次 Gate 收尾時再做。

---

## 5. 範圍邊界

### In Scope

- `doc/spec/PRD_Financial_Sentiment_System_v1.md`：L65、L68 裸寫「18 欄位」改為引用版本化契約名稱。
- `doc/spec/SDD_Financial_Sentiment_System_v1.md`：L68 `trend_discover.py` 狀態標記改為 ✅；
  L246 裸寫「18 欄位」與禁用詞「100%／零誤差」修正；（視決策點 3）§2 檔案清單表補齊 3 個檔案條目。
- `doc/governance/PROJECT_STATUS.md`：§0.4 測試計數 164→200；Current HEAD 快照更新，並改為
  指令化免責聲明寫法（不寫死會再度過期的數字）。
- `doc/evidence/TRACEABILITY.md`：若有殘留裸寫特徵數引用，一併統一為版本化契約名稱
  （本次核對未發現殘留，DEC-013 列已正確使用版本化名稱；若審查時發現遺漏，一併修正）。
- `doc/evidence/DECISIONS.md`：依決策點 1 選定的方案處理 DEC-003／004／006／007／009。
- 新建 `README.md`（Repository 根目錄）：專案簡介、架構、快速啟動、測試執行指引。
- （視決策點 2）`doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`：工單對照表四列狀態欄位更新。

### Out of Scope（明確排除）

- 任何 `src/`、`database/`、`main_etl_pipeline.py` 等程式碼變更。
- 任何 Schema／Migration 變更。
- Gate 2 及以後範圍的項目（DRIFT-003、014、016）。
- 真實 tournament artifact 產出（DEC-020／DRIFT-015 的容器內重跑部分，屬 UG-G3-SB3/SB7）。
- `doc/archive/` 內任何文件（§16.2 明文不可修改）。

---

## 6. 驗證計畫

依 `CLAUDE.md` §9A，每項檢查需能回答「什麼輸入會讓它 FAIL」，並準備至少一個 known-FAIL 案例。

| # | 檢查 | 通過條件 | Known-FAIL 案例（證明檢查非「結構上不可能失敗」） |
|---|------|---------|--------------------------------------------------|
| V1 | 禁用詞掃描 | `grep -rniE "<禁用詞清單>" doc/spec doc/governance doc/evidence` 結果為 0 | 修正前先重跑一次本指令，應命中 §3.1 列出的 2 處；修正後應為 0 |
| V2 | 特徵數裸寫掃描 | `grep -rn "18 欄位\|18欄\|18 特徵\|18 features" doc/spec doc/evidence` 結果為 0（或僅剩決策點 1 選方案 B 時保留的 `DECISIONS.md` 舊條目，需明確排除清單） | 修正前應命中 §2.1 列出的 7 處；修正後（依決策點 1 結果）應降至 0 或僅剩明確排除項 |
| V3 | SDD 規劃中標記掃描 | `grep -n "規劃中\|⏳" doc/spec/SDD_Financial_Sentiment_System_v1.md` 不含任何已實作模組 | 修正前應命中 L68；修正後應為 0（除非該模組真的仍未實作——本案不適用） |
| V4 | 測試計數一致性 | `PROJECT_STATUS.md` §0.4 數字與 `grep -ch "def test_" tests/test_*.py \| awk '{s+=$1} END {print s}'` 實測值相等 | 修正前應為 164 ≠ 200（FAIL）；修正後應相等 |
| V5 | README 存在性 | `ls README.md` 成功 | 修正前應為 exit code 2（FAIL）；修正後應成功且非空檔 |
| V6 | `gate0_contract_check.py` 全綠 | `python scripts/verify/gate0_contract_check.py` exit 0，含 B11 對 `DECISIONS.md:577` 的 WARN 項按決策點 1 結果轉為 PASS 或維持有意登錄的 WARN | 執行本指令記錄修正前後的完整原始輸出，附於 Gate B |
| V7 | 全套現有測試不受影響 | `python -m unittest discover -s tests -p "test_*.py"`（dev container 內）維持 200/200 | 純文件修改理論上不影響測試；仍需實際重跑一次作為回歸證據，而非僅憑「純文件修改」這個推論跳過 |

---

## 7. Definition of Done

- §2.1～§2.8 九項 SB5-owned 漂移項目，狀態全部從「開放」轉為「已修正」或「已依 PO 決策標記為
  刻意保留並附理由」。
- §4 三個 PO 決策點均有明確裁決記錄。
- V1～V7 全數執行且附原始輸出（`VERIFIED THIS SESSION`），其中 V1～V5 需附修正前的 FAIL 輸出
  作為 known-FAIL 證據。
- 未新增、未刪除、未修改任何 `src/`、`database/` 檔案。
- `DOCUMENT_DRIFT_REMEDIATION.md` 對應列狀態更新為 `CLOSED`（依決策點 2 範圍）。
- 依 `CLAUDE.md` §16.3，本提案文件與對應 Gate B 文件於 PO 核准結案後移入 `doc/upgrade/gates/closed/`，
  且移動前已於 `SYSTEM_UPGRADE_MASTER_PLAN.md` 回填 Gate A/B 狀態列（含本次修正的 commit hash）。

---

## 8. 待 PO 裁決事項彙總

1. **決策點 1**：`DECISIONS.md` 既有 ADR 內文處理方式——方案 A（直接改寫）／方案 B（新增說明性 DEC，不動原文）／方案 C（`doc/spec/` 直接改，`DECISIONS.md` 走方案 B）。
2. **決策點 2**：`DOCUMENT_DRIFT_REMEDIATION.md` 工單對照表的 4 列「待 commit」是否於本次一併更新為 CLOSED + commit hash。
3. **決策點 3**：§3 新發現的兩項（禁用詞的 `doc/spec/` 部分已無爭議會修；SDD 檔案清單表補 3 條目）是否併入本次範圍。
4. 是否核准依 §5 範圍開始實作（純文件修改，仍請依 Plan-Before-Code 待本提案核准後才動筆）。

---

## 9. PO 核准與修正記錄（2026-08-26）

### 9.1 PO 裁決

- **範圍補漏**：PO 指出 §2.1 的「7 處」清單不完整，審查員重新 grep 找出額外 5 處
  （`SDD:L229`、`DECISIONS.md:L654/677/701` 屬 DEC-008、`DECISIONS.md:L763` 屬 DEC-009），
  要求納入 DRIFT-001／007 修正範圍，並要求對整個 `doc/evidence/` 重新跑一次完整 grep
  確認無其他遺漏（不要只重看 DEC-006／DEC-007／DEC-009 附近）。
- **決策點 1**：選**方案 C**（`doc/spec/` 直接改；`DECISIONS.md` 走方案 B）。但方案 B 的執行方式
  調整為：不只加孤立新 DEC，改為**在每處問題原文旁邊插入緊鄰的補充註記區塊**（不刪不改原文
  一個字），新 DEC 條目作為總覽索引，比照本專案既有的 DEC-018／DRIFT-018 撤回註記慣例
  （`TRACEABILITY.md:176`：`~~原文~~` + `⛔ 撤回註記` 緊鄰插入的既有模式）。
- **決策點 2**：核准，`DOCUMENT_DRIFT_REMEDIATION.md` 工單對照表 4 列一併更新為 CLOSED + commit hash。
- **決策點 3**：核准併入本次範圍。
- PRD/SDD 之外，`PROJECT_STATUS.md` 「18 欄位」多處命中（L587/593/659/730/733/767）確認全落在
  §1（PRE_CODEX 舊紀錄快照），維持既有排除慣例，不修正。

### 9.2 重新 grep 結果（`VERIFIED THIS SESSION`）

依 PO 指示對整個 `doc/evidence/` 執行完整 grep（非僅 DEC-006／007／009 附近）：

```bash
grep -rnE "18[[:space:]]*(欄|項|特徵|features?|columns?|col)" doc/evidence/
grep -rn "十八" doc/evidence/          # 0 命中，排除其他數字寫法
```

**確認完整清單共 15 處，比 PO 提供的「7＋5＝12 處」多出 2 處未經任何人事先發現**：

| # | 位置 | 來源 |
|---|------|------|
| 1-7 | PRD:L65,L68; SDD:L246; DECISIONS.md:L551,L607,L617,L724+L729 | 原提案 §2.1 已列 |
| 8-12 | SDD:L229; DECISIONS.md:L654,L677,L701（DEC-008）; DECISIONS.md:L763（DEC-009） | PO 本次指出 |
| 13 | **DECISIONS.md:L577**（DEC-006 Verification 段） | **本次完整 grep 新發現**——原提案 §2.1 末段曾提及 B11 已將此行登記為「已知遺留」，但當時未列入 §2.1 表格，也從未在此提案中以精確位置呈現 |
| 14 | **CHALLENGES.md:L211** | **本次完整 grep 新發現，此前無人（含 PO 審查員與本 Agent）發現**——`DOCUMENT_DRIFT_REMEDIATION.md` 的 DRIFT-001／007 登錄位置原本從未涵蓋 `CHALLENGES.md`，本次一併補上旁註並更新 DRIFT-001 的 Location 欄 |

第 13、14 項已依方案 C／B 同等原則處理（`doc/evidence/` 原文不動、插入補充註記）。

### 9.3 額外發現：DRIFT-013 分類修正

實作 PROJECT_STATUS.md §0.4 測試計數修正時，重新檢視 §2.7 對「Current HEAD」欄位的修正建議，
發現該欄位（現行位置為「## 2. Git State」）實際落在 `PROJECT_STATUS.md` 自身在檔案開頭明文宣告的
「§1 以下為 PRE_CODEX 舊紀錄」範圍內，與同一份文件裡「133/133」已確立排除的舊快照屬同一類，
不應視為需要修正的現行欄位。**此為本提案 §2.7 原分析的錯誤，已於實作階段修正**——
`DOCUMENT_DRIFT_REMEDIATION.md` 的 DRIFT-013 狀態改標「排除，維持不動」而非「已修正」，
現行 Git 狀態改由 `PROJECT_STATUS.md` §0.2 的逐 SB commit hash 表追蹤（已隨每個 SB 收尾更新）。

### 9.4 核准開始實作

PO 已核准依修正後範圍開始純文件實作，完成後依 SB1～SB4 慣例格式送 Gate B 審查。
