# UG-G2-SB5 決策點 5 Gate B 送審：來源能力宣告

> 日期：2026-08-30
> Gate A 提案：`doc/upgrade/gates/closed/G2_SB5_DP5_GATE_A_PROPOSAL.md`（PO 2026-08-30 核准）
> 狀態：**待 PO 審查**。**尚未 commit。**

---

## 1. 交付摘要

修掉一個**與 Dcard 是否可用無關**的既有缺陷：聚合層有**兩道**把 `NULL` 壓成 `0`
的關卡，使「這個來源沒有推噓的概念」被算成「推噓各 0 則」，
產出 `comment_polarization = 1.0`（最大分歧）與 `net_push_momentum = 0.0`
——恆定的偽造強訊號，而且不會報錯。

| 交付物 | 內容 |
|--------|------|
| `src/transform/source_capabilities.py`（新建） | `COMMENT_DIRECTION_SOURCES`、`provides_comment_direction()` |
| `src/transform/feature_aggregator.py` | `required` 補 `source`；`fillna(0)` → 依來源能力過濾；`agg` 加 `min_count=1`；`has_comments` 拆為 `has_volume`／`has_direction` |
| `src/loaders/db_writer.py` | `fetch_all_for_features()` 的 SELECT 補 `source` |
| `tests/test_comment_features.py` | `SourceCapabilityTests`（6 個測試）；fixture 補 `source` 欄 |
| 四個既有測試檔 | `requests` stub 隔離缺陷修正（§6） |
| 文件 | `FEATURE_REGISTRY.md` §5.7、DEC-028、`TRACEABILITY.md` §3.2、RISK-016／RISK-017、`PROJECT_STATUS.md`、Master Plan |

---

## 2. 契約驗證原始輸出

```
$ python scripts/verify/gate0_contract_check.py     # dev container 內
...
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂

==================================================
Part B: 11/11 PASS

EXIT=0
```

---

## 3. 測試原始輸出與依賴狀態揭露

### 3.1 執行環境

| 項目 | 值 |
|------|-----|
| 環境 | **dev container**（`CLAUDE.md` §13.0 定義的正式測試環境） |
| Python | 3.14.6 |
| pandas / numpy | 3.0.5 / 2.5.2 |
| 資料庫 | **隔離臨時容器 `g2sb5dp5_tmpdb`**（`postgres:18`，匿名 volume，**非 `postgres-data` 掛載**，預設 bridge 網路，host port 55437），驗證後已拆除 |

**RISK-013 綁定確認（執行前）**：

```
current_database() = g2sb5dp5_tmpdb   ← 是臨時目標
DB_PORT(連線用)    = 55437            ← host 側對映埠
inet_server_port() = 5432             ← 容器內部埠（預期值，非證據）
public schema 表數 = 0                ← 全新空庫
掛載檢查            = 匿名 volume，無 postgres-data bind mount
網路                = bridge（非 compose 網路）
```

> `inet_server_port()` 回報容器內部的 5432 而非 55437 是**預期行為**，
> 它不能單獨作為「連到臨時庫」的證據。真正的證據是
> **資料庫名稱 + 空 schema + 掛載檢查**三者。

### 3.2 全套測試

```
$ DB_HOST=host.docker.internal DB_PORT=55437 POSTGRES_DB=g2sb5dp5_tmpdb \
  python -m unittest discover -s tests -p "test_*.py"
...
----------------------------------------------------------------------
Ran 269 tests in 11.586s

OK
EXIT=0
```

**基線變化**：263 / 26 檔 → **269 / 26 檔**（本次 +6，皆為決策點 5 的新測試）。
核對指令實測：`ls tests/test_*.py | wc -l` = 26、
`grep -ch "def test_" tests/test_*.py` 合計 = 269。

### 3.3 §0.5 未結義務 #8（`schema_smoke_ui_data_loader`）

```
$ python -m unittest tests.schema_smoke_ui_data_loader -v     # 同一臨時 DB
----------------------------------------------------------------------
Ran 4 tests in 0.059s

OK
```

**觸發條件如當初設計地生效**——`UG-G2-SB5` 的可用性驗證判定 `FAIL`、
根本沒起臨時 DB；**若當初綁的是 SB 編號，這條義務會再度落空**，
實際觸發它的是同一個 SB 的**決策點 5**。§0.5 第 8 項已標記結案。

### 3.4 依賴狀態揭露

本次全部在 **dev container** 內執行，`requirements.lock.txt` 的 15 個套件齊備，
**不涉及 host 降級路徑**（`CLAUDE.md` §13.3）。
本次改動不觸及 ML／NLP／重試／LLM 路徑。

---

## 4. known-FAIL 案例（`CLAUDE.md` §9A.2）

### 4.1 實作**前**的原始輸出

```
FAIL: test_direction_null_survives_aggregation
AssertionError: False is not true : 全 NaN 群組的 push_sum 必須是 NaN；sum() 預設回 0.0，需 min_count=1

FAIL: test_no_direction_source_yields_null_not_fabricated_signal
AssertionError: False is not true : 無方向來源不得產出 comment_polarization，補 0 會造出 1.0 這個偽造的最大分歧訊號

Ran 4 tests in 0.144s
FAILED (failures=2)
```

**同一次執行中，`test_zero_push_ptt_article_is_not_null` 與
`test_volume_ratio_still_uses_all_sources` 是 PASS 的**——
這證明那兩個 FAIL 是被特定缺陷觸發的，不是測試本身寫壞。

### 4.2 六個測試與各自的失敗能力

| # | 測試 | 什麼輸入會讓它 FAIL | 實作前 |
|---|------|-------------------|-------|
| 1 | `test_no_direction_source_yields_null_not_fabricated_signal` | 第一道關卡未修（`fillna(0)` 仍在） | **FAIL** |
| 2 | `test_direction_null_survives_aggregation` | 第二道關卡未修（`agg` 缺 `min_count=1`） | **FAIL** |
| 3 | `test_zero_push_ptt_article_is_not_null` | 修法把真實零推文誤判為無方向 | PASS（反向守衛） |
| 4 | `test_unregistered_source_defaults_to_no_direction` | 未登錄來源被當成有方向 | 新能力 |
| 5 | `test_volume_ratio_still_uses_all_sources` | 方向拆分波及數量類特徵 | PASS（回歸守衛） |
| 6 | `test_required_columns_missing_source_returns_empty` | 缺 `source` 時崩潰或當成有方向 | 新行為 |

**為什麼需要兩個 known-FAIL 而不是一個**：兩道關卡各自獨立會把 `NULL` 壓成 `0`。
只寫測試 1 的話，修好第一道之後測試**仍然 FAIL**，
除錯者很可能誤判為「修法方向錯誤」而回頭改設計。

**為什麼需要測試 3**：本次同時動兩處，**最容易的失敗方式是把「真正零推文」
一起誤判成「無方向」**——而那個退化不會有任何錯誤訊號，
只會讓一批 PTT 特徵安靜地變成 `NULL`。

---

## 5. E2E 驗證（走真實 DB 讀取路徑，非 mock）

資料實際寫入臨時 DB 的 `market_articles`，
再經 `DBWriter.fetch_all_for_features()`（pipeline 用的同一條路）撈出，
交給 `FeatureAggregator.generate_daily_features()` 計算。

```
fetch_all_for_features() 回傳文章欄位：
['article_id', 'source', 'post_time', 'fetch_keyword', 'sentiment_score',
 'push_count', 'boo_count', 'neutral_count', 'total_comments', 'comments_scraped_at']

trade_date stock_id  comment_volume_ratio  comment_polarization  net_push_momentum
2026-08-24     2330                   NaN                   NaN                NaN
2026-08-25     2330              1.176471                   NaN                NaN
2026-08-26     2330                   NaN                   NaN                NaN
2026-08-24     2454                   NaN              1.000000                NaN
2026-08-25     2454              1.000000              0.840000           0.400000
2026-08-26     2454             33.846154              0.621302           0.215385
```

| # | 驗證項 | 結果 |
|---|--------|------|
| 1 | 無方向來源（`dcard_stock`）方向類特徵為 `NULL` | ✅ `polarization`／`momentum` 皆 NaN |
| 2 | 同一列數量類特徵仍有值 | ✅ `volume_ratio = 1.176471` |
| 3 | 真實零推文 PTT 文章 `polarization` **有值** | ✅ `1.0` |
| 4 | 混合日 `polarization` 只由 PTT 20 則算出 | ✅ 實得 `0.621301775`，人工核算 `1-(8/13)² = 0.621301775` |
| 5 | 混合日 `volume_ratio` 含兩來源共 220 則 | ✅ 實得 `33.846153846`，人工核算 `220/6.5 = 33.846153846` |

> **第 3 項的 `1.0` 與被消除的偽造訊號同值，但性質完全不同**：
> 這裡是 `push=0, boo=0` → `push_ratio=0` → `1-0²=1.0` 的**正當計算結果**
> （全中立留言）。被消除的是「來源根本沒有方向概念卻算出 1.0」那一種。
> 兩者在 DB 層本來就可區分（`0` vs `NULL`），會把它們壓平的只有聚合層。
> 已寫入 `FEATURE_REGISTRY.md` §5.7.5。

> **第 5 項同時是 RISK-016 的實地重現**：`33.846154` 這個值裡，
> 來源組成變化的貢獻遠大於關注度變化。本 SB 刻意不修，已登記。

---

## 6. 【本次發現】全套測試揭露一個既有的測試隔離缺陷

**單獨跑新測試檔時全過，併入全套後出現 4 個 error。**
這正是複查堅持要跑全套的理由。

```
TypeError: '>=' not supported between instances of 'MagicMock' and 'int'
Ran 269 tests ... FAILED (errors=4)
```

**成因**：四個既有測試檔以

```python
if "requests" not in sys.modules:
    sys.modules["requests"] = <stub>
```

塞 stub。**「已安裝」不等於「已被 import」**——容器裡 `requests` 雖已安裝，
但在這些模組載入的當下通常還不在 `sys.modules`，因此判斷幾乎必然成立，
**stub 永久取代真實 `requests`，影響同一個 process 內後續所有測試模組**
（`unittest discover` 是同一個 process）。

**這與 `UG-G2-SB2` 修掉的 4 個 `bs4` stub 隔離缺陷是同一類問題**——
而且**同一個檔案裡 `bs4` 用的已經是正確寫法**，只有 `requests` 沒改到。

**修法**：改用該檔自己對 `bs4` 已在使用的寫法（`try/except ModuleNotFoundError`）。
四個檔案各改一處，**未改任何斷言**。

> **同一 pattern 仍存在於 `tenacity`／`yfinance` 的 stub 區塊。本次不改**——
> 目前沒有測試需要真實的它們，在沒有失敗案例的情況下動既有測試，
> 等於做一個無法驗證的修改。**在此登記**，下一個需要真實
> `tenacity` 或 `yfinance` 的測試會撞到同一件事。

---

## 7. 既有測試的改動（逐項說明）

**沒有任何斷言被修改。** 改動只有兩類：

| 檔案 | 改了什麼 | 為什麼正確 |
|------|---------|-----------|
| `tests/test_comment_features.py` | `_articles()` fixture 補 `"source": r.get("source", "ptt_stock")` | 聚合層新增 `source` 為必要欄。預設 `ptt_stock` 使**既有 13 個測試的行為完全不變**（PTT 本來就提供方向）——實測該檔既有測試全數維持 PASS |
| 四個測試檔 | `requests` stub 由全域永久替換改為 `try/except ModuleNotFoundError` | §6。這是**測試隔離缺陷的修正**，不是為了讓新測試通過而放寬既有斷言；四個檔案自己的測試全數維持 PASS |

---

## 8. 逐檔授權稽核（§12.3）

**Gate A 提案 §5 In Scope 涵蓋範圍**：宣告表與聚合改動、守衛拆分、
`db_writer` SELECT、兩個 known-FAIL 測試、`FEATURE_REGISTRY.md` §5.7、風險登記。

| 檔案 | 變更 | 授權狀態 |
|------|------|---------|
| `src/transform/source_capabilities.py` | 新建 | In Scope（§3.1） |
| `src/transform/feature_aggregator.py` | +30 −7 | In Scope（§3.2、§3.3） |
| `src/loaders/db_writer.py` | +5 −1 | In Scope（§3.2 第 2 項） |
| `tests/test_comment_features.py` | +159 −1 | In Scope（§6.1）＋ fixture 補欄（§7） |
| `doc/upgrade/contracts/FEATURE_REGISTRY.md` | +72 | In Scope（§10） |
| `doc/evidence/DECISIONS.md` | +102 | In Scope（DEC-028，PO 指派） |
| `doc/evidence/TRACEABILITY.md` | +1 | In Scope（§10） |
| `doc/upgrade/contracts/REMAINING_RISKS.md` | +7 −5 | In Scope（RISK-016／017，PO 指派） |
| `doc/governance/PROJECT_STATUS.md` | +10 −8 | In Scope（§10） |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | +7 −1 | Gate 2 關閉條件新增一項——**PO 2026-08-30 明文指示**（提案 §10 未列，於此主動揭露） |
| `tests/test_canonical_stock_id.py` | +8 −1 | **超出提案 §5 列舉範圍**——§6 的測試隔離缺陷修正。**理由**：不修則全套測試無法通過，而全套測試是本 SB 的 Gate B 硬性要求 |
| `tests/test_feature_aggregator_alignment.py` | +8 −1 | 同上 |
| `tests/test_research_features.py` | +8 −1 | 同上 |
| `tests/test_time_alignment.py` | +8 −1 | 同上 |
| `doc/upgrade/gates/closed/G2_SB5_DP5_GATE_A_PROPOSAL.md` | 新增 | 過程文件 |
| `doc/upgrade/gates/closed/G2_SB5_DP5_GATE_B_SUBMISSION.md` | 新增（本檔） | 過程文件 |

**主動揭露超出提案列舉範圍者：5 個檔案**（Master Plan＋四個測試檔），理由如上表。

---

## 9. 格式／行尾檢查（§12.2）

```
$ git diff --numstat > raw.txt ; git diff --numstat -w > nows.txt ; diff raw.txt nows.txt
（無輸出 —— 無純空白／行尾差異）
```

逐檔行尾核對：**13 個被修改檔案的 HEAD blob 全部為 LF**；
worktree 中 8 份為 CRLF、5 份為 LF，`core.autocrlf=true` 的 clean filter
會在 `git add` 時統一轉為 LF，**worktree 的行尾到不了 blob**。

---

## 10. 證據標籤

| 宣稱 | 標籤 | 可重跑指令 |
|------|------|-----------|
| contract-check 11/11 PASS、exit 0 | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py`（容器內） |
| 全套測試 269 / OK | `VERIFIED THIS SESSION` | 見 §3.2（需臨時 DB） |
| schema smoke 4 tests / OK | `VERIFIED THIS SESSION` | 見 §3.3 |
| 兩個 known-FAIL 實作前確實 FAIL | `VERIFIED THIS SESSION` | 見 §4.1（需 revert `src/` 才能重現） |
| E2E 五項與人工核算逐位相符 | `VERIFIED THIS SESSION` | 見 §5（需臨時 DB） |
| RISK-017 的真實 DB 現況 | `VERIFIED THIS SESSION` | 唯讀查詢，見 Gate A 提案 §1.6 |
| `tenacity`／`yfinance` 仍有同型 stub 隔離缺陷 | `IMPLEMENTATION EVIDENCE` | `grep -n 'not in sys.modules' tests/*.py`。**未獨立驗證其實際影響**——目前無測試需要真實的它們 |
| Migration SB 執行後 pipeline 能對真實庫跑完 | `NOT VERIFIED` | 尚未執行。範圍：整個真實開發資料庫路徑 |

---

## 11. Definition of Done 對照

| DoD 項目 | 狀態 |
|---------|------|
| 六個測試存在；第 1、2 項先確認 FAIL 並留原始輸出，修後轉綠 | ✅ §4 |
| 117 個既有測試全部通過；斷言修改逐項說明 | ✅ 全套 269 OK；**未修改任何斷言**，改動說明見 §7 |
| 全套測試實際執行輸出已附（臨時 DB，含綁定確認） | ✅ §3 |
| §0.5 #8 已於同一臨時 DB 補跑並回報 | ✅ §3.3，該項已標記結案 |
| `FEATURE_REGISTRY.md` §5.7、DEC-028、`TRACEABILITY.md` §2 與 §3.2 | ✅ §5.7 與 DEC-028、§3.2 已同步；**§2 追溯矩陣未新增列**——見下方揭露 |
| RISK-016 與 RISK-017 都已登記 | ✅ 含 Risk Summary 計數同步 |
| `PROJECT_STATUS.md` §0.4 基線更新 | ✅ 269 / 26，四個行內數字實測核對 |
| 未夾帶格式／行尾變更；contract-check exit 0 | ✅ §9、§2 |

> **主動揭露一項未完成**：DoD 列了「`TRACEABILITY.md` §2 追溯矩陣新增列」，
> 本次**只補了 §3.2 的 ADR 索引，未新增 §2 的矩陣列**。
> 原因是 §2 的每一列對應一個「文件漂移項 → 修正」的追溯關係，
> 而 DEC-028 是**新增契約條文**、不對應任何既有 DRIFT 編號，
> 硬塞一列需要先決定它掛在哪個漂移項下。**請 PO 裁示**：
> 是否需要為此新增一個 DRIFT 編號，或 §2 本來就不涵蓋這類新增條文。

---

## 12. PO 裁示與收尾（2026-08-30）

| # | 事項 | 裁示 | 處置 |
|---|------|------|------|
| 1 | commit | **核准，拆兩個**（`src/`＋測試一個、文件一個） | 已執行 |
| 2 | `TRACEABILITY.md` §2 矩陣列 | **不新增 DRIFT 編號**——§2 第一欄本來就接受 PO 決策作為來源（現成先例：`稽核報告 §1；PO 決策 §3.3`）。為了填滿欄位而發明一個 DRIFT 編號，等於在證據系統裡放一筆不存在的事實 | 已新增一列，來源填「PO 2026-08-28 Gate A 裁決（決策點 5）」 |
| 3 | DEC-028 | **`APPROVED`**，`Approved by: Project Owner`、`核准日期：2026-08-30` | 已更新；`TRACEABILITY.md` §3.2 索引狀態同步。**這是 §0.5 第 10 項規則第一次實地生效** |
| 4 | Master Plan 的 Gate 2 關閉條件 | **不需另立偏離登記**——DEC-026 記的是「實作與已核准文件不符」，本次是 PO 修改自己核准過的計畫，性質不同；原文已加註日期與理由，§8 亦主動揭露 | 無需追加 |

### 12.1 【新指派】RISK-018

PO 認為 §5.7.5 那個「僅登記」的觀察比登記更嚴重，並實跑了 §5.3 的公式。
本次獨立重現（容器內）：

| 情境 | `push_ratio` | `comment_polarization` |
|------|------------|----------------------|
| 真實推噓對半 `push=5, boo=5` | 0.0000 | **1.0000** |
| 全中立留言 `push=0, boo=0`（`neutral=20`） | 0.0000 | **1.0000** |
| 一面倒看多 `push=20, boo=0` | 0.9524 | 0.0930 |
| 一面倒看空 `push=0, boo=20` | −0.9524 | 0.0930 |

**兩種語意完全不同的情境得到同一個值，且都是該指標的最大值。**

**與 DEC-028 修掉的缺陷是同一個形狀**——不會報錯的偽造「最大分歧」強訊號，
只是從另一道門進來：DEC-028 那道是「來源沒有方向的概念」，
本項這道是「有方向能力的來源，但這篇沒有方向性留言」。
**差別在於本項今天就會在真實 PTT 資料上發生，不需要第二個來源。**

已登記 **RISK-018**（Medium-High，Gate 3 啟動前必須裁決），
並於 `FEATURE_REGISTRY.md` §5.3 加註指向它。
§5.7.5 亦補上一句：**本節說明的是「哪一種 1.0 被消除了」，
不是「剩下的 1.0 都沒問題」**——原本的寫法會讓讀者以為現況沒問題。

### 12.2 複查方的獨立重跑

複查方自起隔離臨時 DB（`sb5dp5_review_tmpdb`、port 55439、匿名 volume、
未掛 `postgres-data`），`init_db.py` + `apply_migrations.py`（001～004 套用至 v4）後
執行全套 → **`Ran 269 tests in 11.188s / OK`**，容器已拆除。

**對 Migration SB 有用的旁證：001～004 在乾淨 schema 上套用全程無誤。**
真實庫有 331 筆資料，情況不完全相同，但 DDL 本身沒問題。

### 12.3 複查方主動更正的一次誤判（記錄備查）

複查方一度以為 `test_tracking_keyword_integrity.py:30` 也有同樣的 `requests` stub 缺陷，
核對後發現**該檔是用 `with patch.dict(sys.modules, dependency_stubs):`（`:52`）**，
有作用域、離開即還原，**不是同一個缺陷**。

> **靜態 `grep` 分不出 `use` 與 `replace`** —— 這與 `CLAUDE.md` §9A.1
> 記載的「以檔案粒度靜態 grep 判斷測試覆蓋」是同一個原理上的限制，
> 本專案第三次遇到它。

---

## 13. 本次額外揭露（未處理，登記備查）

1. **`TRACEABILITY.md` §2 矩陣缺的不只 DEC-028**：DEC-024／025／026／027
   同樣不在 §2（本次只依裁示補了 DEC-028 一列）。
   §0.5 第 10 項的規則只寫「補進 §3.2」，未涵蓋 §2——**規則本身有缺口**。
2. **§2 的「總計」列已過期**：仍寫 `154 項測試`／`17 大測試套件檔案`／`100% PASS (~1.80s)`，
   而現行基線是 **269 / 26 檔**。本次**未修**——
   該列的其他欄位（「9 大核心 ADR」「18 大核心生產模組」）需要重新盤點才能一致，
   半修比不修更誤導。建議另案處理。
