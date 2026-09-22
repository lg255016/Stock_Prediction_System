# UG-G2-SB8 Gate B 送審：CORE_16 四個平穩化特徵 + 讀取端缺口反查檢查

> 日期：2026-08-31
> Gate A 提案：`doc/upgrade/gates/G2_SB8_GATE_A_PROPOSAL.md`（PO 2026-08-31 核准，含四項決策裁決）
> 狀態：**待 PO 審查。尚未 commit。**

---

## 1. 交付摘要

CORE_16 的第 13–16 號模型輸入從此可計算。在本 SB 之前，
**CORE_16 實際只有 12 個特徵、COMMENT_ENHANCED_19 只有 15 個**。

| 交付物 | 內容 |
|--------|------|
| `src/loaders/db_writer.py` | 股價查詢補 `high_price`／`low_price`（**同型讀取端缺口第三次**） |
| `src/transform/feature_aggregator.py` | 四個公式 + 依 DEC-030 的 NULL 策略 |
| `scripts/verify/gate0_contract_check.py` | **Part B 第 12 項**：讀取端缺口反查檢查 |
| `tests/test_stationarity_features.py` | 9 個測試（含 2 個 known-FAIL、2 個反向／互補守衛） |
| `FEATURE_REGISTRY.md` | §3.4 兩欄 NULL 策略、**§5A.1 新增成因 U**、§5A.3 兩列 |
| DEC-030（`Proposed`）、RISK-020 | NULL 策略修正與未解問題登記 |

---

## 2. 契約驗證原始輸出

```
B12  PASS | 特徵契約需要的 DB 欄位，讀取端皆有 SELECT（反查法）
       契約需求 13 欄；讀取端缺 0；未涵蓋 2 類
       [未涵蓋] 四個 CORE_16 平穩化特徵的「資料來源」欄為「待實作於 feature_aggregator.py」——自然語言，無法對應到具體 DB 欄位
       [未涵蓋] 題材溢出（theme_stock_mapping）與 entity_mapping 的欄位需求——由獨立查詢取得，不在 fetch_all_for_features 的兩句 SELECT 內

==================================================
Part B: 12/12 PASS      EXIT=0
```

---

## 3. 測試原始輸出與依賴狀態揭露

| 項目 | 值 |
|------|-----|
| 環境 | **dev container**（`CLAUDE.md` §13.0 的正式測試環境），Python 3.14.6 |
| 資料庫 | 隔離臨時容器 **`sb8_tmpdb`**（`postgres:18`，匿名 volume，**非 `postgres-data` 掛載**，bridge 網路，host port 55447），已套用 001～004，**已拆除** |
| RISK-013 綁定確認 | `current_database() = sb8_tmpdb`、`DB_PORT = 55447`、掛載為匿名 volume |

```
$ python -m unittest discover -s tests -p "test_*.py"
----------------------------------------------------------------------
Ran 278 tests in 12.190s

OK
```

**基線變化**：269 / 26 檔 → **278 / 27 檔**（本次 +9，全部為新檔
`tests/test_stationarity_features.py`）。

**依賴狀態**：全部在 dev container 內執行，不涉及 host 降級路徑（§13.3）。
本次改動不觸及 ML／NLP／重試／LLM 路徑。

---

## 4. known-FAIL 案例（`CLAUDE.md` §9A.2）

### 4.1 實作**前**：9 個測試全部 FAIL

```
ERROR: test_amplitude_ratio_formula ... KeyError: 'amplitude_ratio'
ERROR: test_missing_high_low_does_not_fabricate_zero_amplitude ... KeyError: 'amplitude_ratio'
ERROR: test_zero_amplitude_is_a_real_observation_not_null ... KeyError: 'amplitude_ratio'
ERROR: test_ma5_bias_ratio_formula_after_warmup ... KeyError: 'ma5_bias_ratio'
ERROR: test_warmup_fills_zero_per_contract ... KeyError: 'ma20_bias_ratio'
...
EXIT=1
```

四個欄位當時**根本不存在於輸出**——這是「特徵沒有被計算」最直接的證據。

### 4.2 四個測試的失敗能力對照

| 測試 | 什麼輸入會讓它 FAIL | 性質 |
|------|-------------------|------|
| `test_missing_high_low_does_not_fabricate_zero_amplitude` | 沿用契約原本的 `fillna(0.0)` | **known-FAIL（決策 1）** |
| `test_zero_volume_baseline_is_not_filled_as_one` | 沿用契約原本的 `fillna(1.0)` | **known-FAIL（決策 3）** |
| `test_zero_amplitude_is_a_real_observation_not_null` | 修法把真實的 `High == Low` 也變成 NULL | **反向守衛** |
| `test_warmup_fills_one_per_contract` | 把暖機期也一起變成 NULL | **互補守衛** |

**兩個守衛是必要的**：決策 1／3 的修法最容易的失敗方式，
就是把「真的是 0」與「暖機期」一起變成 NULL——
而那個退化**不會產生任何錯誤訊號**，只會讓一批特徵安靜地消失。

### 4.3 【重要】Part B 第 12 項的 known-FAIL **第一次沒有 FAIL**

依 §9A.2 用**真實缺陷**（移除 `db_writer.py` SELECT 裡的 `high_price`）測試新檢查：

```
契約需求 13 欄；讀取端缺 0；未涵蓋 2 類
Part B: 12/12 PASS       ← **缺陷已注入，檢查卻仍然通過**
```

**成因**：檢查在 `fetch_all_for_features` 起算的 2500 字元視窗上搜尋欄位名，
而**緊鄰的註解裡也寫著 `high_price`**（那段註解正是在說明「本次補上 high/low」）。
**檢查掃到了註解，不是 SQL。**

> **這正是 `CLAUDE.md` §9A.1 記載的 B4 grep 失敗模式——
> 而它發生在一支「為了防止該模式而寫」的檢查上。**
>
> 若沒有依 §9A.2 實際跑一次 known-FAIL，這支檢查會以「12/12 PASS」的外觀
> **永遠通過**，並讓第四次讀取端缺口照樣溜過去。
> **一個從未失敗過的檢查，與一個永遠不會失敗的檢查，在輸出上完全無法區分。**

**修法**：只掃**非註解行**。註解裡提到欄位名是說明，不是 SELECT。
修正後重跑同一個 known-FAIL：

```
契約需求 13 欄；讀取端缺 1；未涵蓋 2 類
       [VIOLATION] 讀取端未 SELECT: high_price（amplitude_ratio；FEATURE_REGISTRY §3.4 (High - Low) / Close）
Part B: 11/12 PASS       ← 現在真的會 FAIL，且指出是哪一欄、為何需要
```

真實缺陷已還原，檢查回到 12/12。**此一經過已寫入該檢查的程式碼註解**，
使後續維護者不會把註解行掃描的排除當成可有可無的細節。

---

## 5. E2E 驗證（走真實 DB 讀取路徑，非 mock）

Fixture 涵蓋四種情境寫入臨時 DB 的 `stock_prices`，
再經 `DBWriter.fetch_all_for_features()` 撈出交給 `FeatureAggregator` 計算。

```
fetch_all_for_features() 股價欄位：
['trade_date', 'stock_id', 'high_price', 'low_price', 'close_price', 'volume']
```

| # | 驗證項 | 結果 |
|---|--------|------|
| 1 | `amplitude_ratio` 公式 | ✅ 實得 `0.040000000`，人工核算 `(102−98)/100` |
| 2 | **high/low 缺席 → NULL** | ✅ NaN（DEC-030 決策 1，成因 F） |
| 3 | 同一檔其他日仍有值（不得整欄變 NULL） | ✅ 5/5 列非 NULL |
| 4 | **`MA5_Vol == 0` → NULL** | ✅ NaN（DEC-030 決策 3，**成因 U**） |
| 5 | 暖機期 → `1.0` | ✅ 1.0（成因 W，維持契約） |
| 6 | 基準恢復後為真實比值 | ✅ 實得 `6.000000000`，人工核算 `6000/1000` |
| 7 | `ma5_bias_ratio` 公式 | ✅ 實得 `0.038461538`，人工核算 `(108−104)/104` |
| 8 | `ma20_bias_ratio` 暖機期 → `0.0` | ✅（維持契約，RISK-020 已登記） |

第 4 與第 6 項並列尤其重要：**同一檔股票，`MA5_Vol == 0` 那一天是 NULL，
基準恢復後那一天是真實比值 6.0**——證明修法沒有把整欄變成 NULL。

---

## 6. NULL 策略：逐欄檢視的結果（DEC-030）

PO 指示「不要因為契約寫了就照抄」。檢視結果是**契約四項策略中有兩項不正當**：

| 欄位 | 契約原指定 | 本 SB | 理由 |
|------|-----------|------|------|
| `amplitude_ratio` | `fillna(0.0)` | **保持 NULL** | 三個輸入同列、**無暖機期**，該填補唯一可能觸發的情境是成因 F，而 §5A.1 對 F 明文禁止填補 |
| `volume_ratio_5d` | `fillna(1.0)`；暖機期分母為零時 | **W → 1.0；`MA5_Vol == 0` → NULL** | 原文把兩種成因寫成同一件事 |
| `ma5_bias_ratio` | `fillna(0.0)` | **維持** | 暖機期屬 W，允許填補；「事件值 vs 結構中點」問題涵蓋兄弟欄位 → RISK-020 |
| `ma20_bias_ratio` | `fillna(0.0)` | **維持** | 同上 |

### 6.1 §5A.1 的窮盡性宣稱被證偽——新增成因 U

`MA5_Vol == 0`（過去 5 日完全沒有成交）**既不是 W 也不是 F**：

- 不是 W——§5A.1 對 W 的定義是「資料**確實存在**，但時序視窗尚未累積足夠歷史」，**視窗是足的**
- 不是 F——§5A.1 對 F 的定義是「資料**根本沒取得**」，**資料取得了，就是 0**

而 §5A.1 原文寫的是「任何欄位出現空值，**只可能是**以下兩種成因之一」。

**已新增成因 U（Undefined，數學未定義）**：
資料齊備、視窗足夠，但公式在該點數學上未定義。處理為**保持 NULL，嚴禁填補**
——填補值必然是一個**與事實相反**的陳述。

### 6.2 為何不沿用 Laplace 平滑

`compute_push_ratio()` 對零除用 Laplace（分母 +1），PO 指示「權衡後選一個，不要繼承」。

**不採用**。Laplace 的 `+1` 只有在**分母的自然尺度與 1 可比**時才是平滑：
推噓數是 0～數百的小整數，`+1` 是輕微擾動；
而成交量以股／張計，量級 10³–10⁹，**對零基準加 1 股不會正則化**，
只會讓比值等於**今日原始成交量**——那已經不是一個比值。

> **同一個技巧不因為本專案用過就適用。**

### 6.3 契約未指定、由本 SB 決定的一件事

契約只寫 `Volume / MA5_Vol` 與 `(Close − MA_n) / MA_n`，**未指定 MA 是否含當日**：

| 特徵 | 決定 | 理由 |
|------|------|------|
| `ma5/ma20_bias_ratio` | **含當日** | 標準均線偏離率；MA 不含當日會變成另一個指標 |
| `volume_ratio_5d` | **不含當日**（`t-5..t-1`） | 沿用同族 `comment_volume_ratio` 的既有慣例（§5.2 明文）。基準含當日會讓今日成交量出現在自己的分母裡，壓抑本要偵測的放量訊號 |

**這是實作決定，不是契約既有內容**，已寫入 DEC-030 與程式碼註解。

---

## 7. RISK-020 的關鍵輸入——實測結果比預估更值得注意

PO 預估「4 檔股票約各 29 列 → 約 65%」。**實測（真實庫 `stock_prices`，唯讀）**：

| 股票 | 總列數 | MA20 暖機列數 | 佔比 |
|------|--------|--------------|------|
| **2330** | 14 | 14 | **100.0%** |
| **2382** | 14 | 14 | **100.0%** |
| 6488 | 25 | 19 | 76.0% |
| NVDA | 64 | 19 | 29.7% |
| **合計** | **117** | **66** | **56.4%** |

（`ma5_bias_ratio` 暖機期 4 日 → 整體 16/117 = **13.7%**。）

> **最重要的不是 56.4% 這個平均，而是 2330 與 2382 的 100%。**
> 那兩檔股票的 `ma20_bias_ratio` **每一個值都是填補出來的 `0.0`**，
> 沒有任何一列是真實計算的結果。
> 模型若使用該特徵，對這兩檔學到的是一個**完全由暖機期規則產生的常數**。

樣本增長後平均佔比會下降，**但新上市或新納入追蹤的股票必然重現此形狀**。
已寫入 RISK-020。

---

## 8. 逐檔授權稽核（§12.3）

| 檔案 | 變更 | 授權狀態 |
|------|------|---------|
| `src/transform/feature_aggregator.py` | 四公式 + NULL 策略 + `final_cols` | In Scope（Gate A §5.1-2） |
| `src/loaders/db_writer.py` | 股價查詢補 high/low | In Scope（Gate A §5.1） |
| `tests/test_stationarity_features.py` | 新建，9 tests | In Scope（Gate A §6） |
| `scripts/verify/gate0_contract_check.py` | Part B 第 12 項 | In Scope（Gate A §4） |
| `doc/upgrade/contracts/FEATURE_REGISTRY.md` | §3.4／§5A.1／§5A.3 | In Scope（Gate A §5.3） |
| `doc/upgrade/contracts/REMAINING_RISKS.md` | RISK-020 + Summary 計數 | In Scope（PO 指派） |
| `doc/evidence/DECISIONS.md` | DEC-030（`Proposed`） | In Scope（PO 指示） |
| `doc/upgrade/gates/G2_SB8_GATE_A_PROPOSAL.md`／本檔 | 過程文件 | — |

**同批但屬 `UG-G2-MIG` 收尾、非本 SB 範圍者**（主動揭露）：
`.claude/skills/gate-submit/SKILL.md`（產出 7 + 數字修正）、
`doc/governance/PROJECT_STATUS.md`（§0.5 #9／#12 結案 + SB8 排序）、
`doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md`（§5.2／§8／關閉條件，DEC-029）、
`doc/evidence/DECISIONS.md`（DEC-029）、5 份 `gates/` → `closed/` 搬移。

**超出授權清單者：無。**

---

## 9. Definition of Done 對照（**每一項指名資料庫**）

| DoD | 狀態 |
|-----|------|
| `db_writer` 股價查詢含 `high_price`／`low_price` | ✅ |
| 四個公式已實作，測試全過 | ✅ 9/9 |
| NULL 策略依裁示落地；契約條文同步修正 | ✅ §6 |
| 兩個 known-FAIL **實作前已確認 FAIL 並留存原始輸出** | ✅ §4.1 |
| Part B **12/12 PASS**，反查檢查含 known-FAIL 實測輸出 | ✅ §2、§4.3 |
| 全套測試於**隔離臨時 DB `sb8_tmpdb`** 通過 | ✅ 278 / OK |
| E2E 於**隔離臨時 DB `sb8_tmpdb`** 完成，值與人工核算逐位相符 | ✅ §5 |
| Gate 2 關閉條件已新增；Master Plan 與 `PROJECT_STATUS.md` 已同步 | ✅（隨 DEC-029） |
| `PROJECT_STATUS.md` §0.4 基線重新核對 | ✅ 269/26 → **278/27** |
| contract-check `exit 0`；無夾帶格式／行尾變更 | ✅ |

> **未列入 DoD**：`postgres`@`localhost:5432` 的四欄實際填值——
> 需對真實庫重跑 pipeline，**須另行授權**，不併入本 SB。
> 目前真實庫四欄仍為 0/117 非 NULL。

---

## 10. 驗證邊界【必讀】

- 本次驗證的是**公式正確性與 NULL 策略行為**，
  **不是**四欄在真實 117 列上的實際值——真實庫尚未重跑 pipeline。
- `ma20_bias_ratio` 的 100% 暖機期佔比意味著：**即使重跑，2330 與 2382 的該欄
  仍會全部是填補值**。那不是 bug，是 RISK-020 要裁決的事。
- Part B 第 12 項**明確不涵蓋**兩類需求（§2 輸出中列出），不得讀成「全部涵蓋」。

---

## 11. 待 PO 決定

1. 是否核准 commit（建議拆兩個：`src/`＋測試＋檢查腳本一個、文件一個）。
2. 是否授權對真實庫重跑 pipeline 以填入四欄（本 SB 未做）。
