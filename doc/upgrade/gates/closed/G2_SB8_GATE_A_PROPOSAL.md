# UG-G2-SB8 Gate A 提案：CORE_16 四個平穩化特徵 + 讀取端缺口反查檢查

> 狀態：**Gate A 審查中**。**核准前不動 `src/`。**
> 日期：2026-08-31
> Gate：UG-Gate-2（PO 2026-08-31 指派編號並定序：MIG → **SB8** → SB6 → SB7 → Gate 2 關閉）
> 依據：DEC-029（PO 2026-08-31 核准）

---

## 0. 摘要

`UG-G2-MIG` 逐欄重驗時發現四個欄位全為 NULL，當時判定「契約標 `PLANNED`，不是缺陷」。
**那個判斷正確，但只到一半。**

這四欄是 **CORE_16 的模型輸入第 13–16 號**（`FEATURE_REGISTRY.md` §3.7）。
沒有它們，**CORE_16 實際只有 12 個特徵、COMMENT_ENHANCED_19 只有 15 個**——
整個升級計畫的目標特徵集建不出來。

而掃過 Gate 2 與 Gate 3 全部 Brief：**沒有任何一個 SB 負責計算它們**。
`PLANNED` 標的是「計畫要做」，但沒有任何地方寫著誰做、何時做。

**同時這是同一個讀取端缺口的第三次**（§2），因此本 SB 一併交付**機械化的反查檢查**。

---

## 1. Current State（逐項核實，`VERIFIED THIS SESSION`）

### 1.1 四欄的契約位置

`FEATURE_REGISTRY.md` §3.7 DB 欄位序號 ↔ 模型輸入索引對照（`:158` 起）：

| DB 序號 | 欄位 | LEGACY_17 | **CORE_16** | COMMENT_ENHANCED_19 |
|--------|------|-----------|------------|---------------------|
| 19 | `amplitude_ratio` | — | **13** | 13 |
| 20 | `ma5_bias_ratio` | — | **14** | 14 |
| 21 | `ma20_bias_ratio` | — | **15** | 15 |
| 22 | `volume_ratio_5d` | — | **16** | 16 |

`FEATURE_REGISTRY.md:14` 對 CORE_16 的定義：
「移除 open/high/low，保留 12 既有衍生特徵 **+ 新增 4 個平穩化特徵**」。

**四個平穩化特徵就是這四欄。** §3.4 的標題即為
「Engineered Features — CORE_16 新增平穩化特徵（4 欄）」。

### 1.2 實作狀態

| 事實 | 證據 |
|------|------|
| 契約 `Status` 欄標 **`PLANNED`**、Source 欄寫「待實作於 `feature_aggregator.py`」 | `FEATURE_REGISTRY.md:108-111` |
| `feature_aggregator.py` 中四個名字 **grep 零命中** | `grep -c` = 0 |
| DB 欄位**存在**（migration 002 已建） | 真實庫 `daily_ml_features` 29 欄 |
| 真實庫四欄 **0/117 非 NULL** | `UG-G2-MIG` 步驟 3 逐欄表 |
| `db_writer.py:531-534` 的「欄位不在 DataFrame 就填 `None`」使它們靜靜寫成 NULL | 該處程式碼 |
| **沒有任何 SB 負責**（掃過 Gate 2 與 Gate 3 全部 Brief） | Master Plan §8 |

### 1.3 【第三次】同型的讀取端缺口

`db_writer.py:488`：

```sql
SELECT trade_date, stock_id, close_price, volume FROM stock_prices;
```

而真實庫 `stock_prices` 的實際欄位是
`stock_id, trade_date, open_price, high_price, low_price, close_price, volume, created_at`，
且 **`high_price`／`low_price` 為 117/117 非 NULL**——**資料一直都在，是讀取端沒撈。**

**這是同一個形狀的第三次**：

| # | SB | 缺口 | 當時的紀錄 |
|---|----|------|-----------|
| 1 | `UG-G2-SB4` | `market_articles` 的四個留言計數欄 | `db_writer.py:489-493` 註解寫「**讀取端缺口**」 |
| 2 | `UG-G2-SB5` 決策點 5 | `source` 欄（`NOT NULL`，UI 路徑一直有撈） | 該處註解寫「這是同型缺口的**第二例**」 |
| 3 | **本次** | `high_price`／`low_price` | 本提案 |

**三次形狀完全相同，而且三次都是靠人偶然發現的。**
第三次尤其明顯：`UG-G2-MIG` 是為了驗證 migration 才逐欄看，
**不是任何檢查抓到的**。處置見 §4。

---

## 2. Requirement Source

- **DEC-029**（PO 2026-08-31 核准）——新增本 SB 於 Gate 2 的決策與理由
- `FEATURE_REGISTRY.md` §3.4（四欄定義）、§3.7（模型輸入索引）、
  `:14`（CORE_16 定義）、`:108-111`（公式與 NULL 策略）
- `FEATURE_REGISTRY.md` **§5A**（全欄位 NULL 語意規則）——§3 的判準來源
- `CLAUDE.md` §9A.1（契約反查法）、§9A.2（known-FAIL 案例）

---

## 3. 【核心】NULL 策略逐一檢視——**不照抄契約**

PO 指示：**逐一對照 §5A 判斷每一個 `fillna` 是否正當，不要因為契約寫了就照抄。**

### 3.1 §5A.1 的判準

| 成因 | 定義 | 處理 |
|------|------|------|
| **W 暖機期不足** | 資料**確實存在**，但時序視窗尚未累積足夠歷史 | **允許填補**中立值 |
| **F 來源失敗** | 資料**根本沒取得** | **必須保持 NULL**，嚴禁填補 |

> 契約原文：「這兩者在數學上可能落到同一個值，但語意完全不同：
> 前者是『已知的中立』，後者是『未知』。**把後者填成前者，
> 等同於讓模型讀到一個從未觀測到的訊號。**」

### 3.2 逐欄檢視結果

| 欄位 | 公式 | 契約指定 | 有暖機期嗎 | 本提案判定 |
|------|------|---------|-----------|-----------|
| `amplitude_ratio` | `(High − Low) / Close` | `fillna(0.0)` | **沒有**（同日資料，不需歷史） | **決策點 1——建議改為保持 NULL** |
| `ma5_bias_ratio` | `(Close − MA5) / MA5` | `fillna(0.0)` | 有（< 5 日） | **決策點 2** |
| `ma20_bias_ratio` | `(Close − MA20) / MA20` | `fillna(0.0)` | 有（< 20 日） | **決策點 2** |
| `volume_ratio_5d` | `Volume / MA5_Vol` | `fillna(1.0)` | 有（< 5 日）＋分母為零 | **決策點 3** |

### 3.3 【決策點 1】`amplitude_ratio` 的 `fillna(0.0)` **只可能在成因 F 時觸發**

`(High − Low) / Close` **全部是同日資料，不需要任何歷史**——
**它沒有暖機期。**

因此它唯一可能為 NULL 的情境是 **`high_price` 或 `low_price` 取不到**，
而那是**成因 F（資料根本沒取得）**，依 §5A.1 **必須保持 NULL、嚴禁填補**。

契約 `:108` 的 NULL Handling 欄自己寫著「`fillna(0.0)`；**需 high/low/close**」——
**那個「需 high/low/close」正是線索**：會觸發填補的唯一情況，就是它依賴的資料不存在。

**而 `fillna(0.0)` 的語意是「當日振幅為零」**——一個**真實且有意義的觀測值**
（漲跌停鎖死、或整日無成交）。把「取不到高低價」填成「振幅為零」，
就是 §5A.1 明文禁止的「**把未知填成已知的中立**」。

**這與本專案已修掉三次的病同型**：`DEFAULT 0` 禁令、
`fillna(0)` 偽造 `comment_polarization = 1.0`、`sum()` 把全 NaN 變 0。

> **建議**：`amplitude_ratio` 改為**保持 NULL**，並在 §3.4／§5A.3 修正該欄的 NULL 策略。
> **本提案不自行改契約**——依 PO 指示列為決策點。

### 3.4 【決策點 2】`ma5_bias_ratio`／`ma20_bias_ratio` 的暖機期填補是正當的，但值得確認

這兩欄**確實有暖機期**（MA5 需 5 日、MA20 需 20 日），
暖機期不足屬**成因 W**，依 §5A.1 **允許填補**。

**但 `0.0` 是否為適當的中立值，值得單獨確認**：
`(Close − MA5) / MA5 = 0` 的語意是「**收盤價恰好等於 5 日均線**」——
那同樣是一個**真實且有意義的觀測值**（價格貼合均線），不是「無資訊」。

**與 `rsi_14 → fillna(50.0)` 的對照**：RSI 的 50 是該指標值域 `[0,100]` 的
**結構中點**，「中性」是它的內建語意；而 bias ratio 的 0 是「價格等於均線」，
是一個**事件**，不是值域中點（值域為 `(-inf, +inf)`，0 只是恰好在中間）。

**本提案傾向維持契約的 `fillna(0.0)`**，理由：暖機期屬成因 W、
契約已明示、且影響僅限每檔股票的前 4／19 個交易日。
**但把上述區別記錄下來**——若 PO 認為「價格貼合均線」這個訊號不該被暖機期偽造，
改為保持 NULL 同樣合理，代價是每檔前 19 日的 `ma20_bias_ratio` 不可用。

### 3.5 【決策點 3】`volume_ratio_5d` 的 `fillna(1.0)` 混了兩種成因

契約 `:111` 寫「`fillna(1.0)`；**暖機期分母為零時**」——這句話把兩件事寫在一起：

| 情境 | 成因 | `fillna(1.0)` 是否正當 |
|------|------|---------------------|
| 前 4 個交易日，MA5_Vol 尚未累積 | **W 暖機期** | 正當（依 §5A.1） |
| **MA5_Vol = 0**（連續 5 日零成交，如停牌） | **不是暖機期**——那是**真實觀測到的零成交** | **不正當** |

第二種情境下，`1.0` 的語意是「**今日成交量等於 5 日均量**」，
而事實是「**過去 5 日完全沒有成交**」。這不是中立值，是**與事實相反的值**。

> **建議**：拆成兩種處置——暖機期 → `fillna(1.0)`（成因 W）；
> **MA5_Vol = 0 → 保持 NULL**（不是暖機期，也不是中立）。
> 並於契約 `:111` 修正該欄措辭，使兩種情境不再被寫成同一件事。

### 3.6 三個決策點的共同性質

**契約在這四欄上寫的 NULL 策略，是在四欄都還沒實作時寫的。**
現在要實作了，才第一次有人逐欄去問「這個 `fillna` 會在什麼情況下觸發」。

**這正是 §9A.1 的精神**：一個從未被觸發過的填補規則，
與一個永遠正確的填補規則，在文件上看起來完全一樣。

---

## 4. 讀取端缺口反查檢查（PO 指示一併交辦）

### 4.1 為什麼要機械化

**同一個缺口出現三次，每次都靠人偶然發現。**
第三次尤其明顯：是為了驗證 migration 才逐欄看到的，**不是任何檢查抓到的**。

### 4.2 作法——契約反查法（§9A.1）

> 從**契約要求**出發列舉所有應受約束的對象，逐一反查實作是否滿足，
> **而不是從已知答案出發湊一個會通過的檢查。**

拿 `FEATURE_REGISTRY.md` 每個特徵的「資料來源」欄，
**反查 `fetch_all_for_features()` 實際 SELECT 的欄位集合**，缺的就 FAIL。

### 4.3 位置：`gate0_contract_check.py` Part B 第 12 項

**不做成測試。** 理由：`.githooks/pre-commit` 的檢查 1 會跑 contract-check，
**這樣每一次 commit 都會驗**——那是唯一能在第四次發生前抓到它的位置。
**測試只有在有人跑測試時才會跑。**

### 4.4 known-FAIL 案例（§9A.2）

**用真實缺陷，不用人造案例**：
**把 `db_writer.py:488` 的 `high_price` 拿掉，確認檢查 FAIL**——
那正是本次的真實缺口。

### 4.5 一項預先揭露的設計難點

「資料來源」欄是**自然語言**（例如「待實作於 feature_aggregator.py」、
「`stock_prices.high_price`」），不是結構化欄位。
反查需要一個從該欄推導出「需要哪些 DB 欄位」的規則，
而**那個規則本身可能不完備**。

**本提案的處置**：先涵蓋能明確對應到 `stock_prices`／`market_articles`
欄位名稱的項目，**無法機械解析者明確列為「未涵蓋」並輸出**，
而不是靜默略過——**一個宣稱涵蓋全部卻實際跳過一半的檢查，比沒有檢查更危險**。

---

## 5. In / Out of Scope

**In Scope**：
1. `db_writer.py:488` 的股價查詢補 `high_price`／`low_price`
2. 於 `feature_aggregator.py` 實作四個公式
3. NULL 策略依 §3 決策點裁示落地（含契約條文修正）
4. `gate0_contract_check.py` Part B 第 12 項反查檢查 + known-FAIL 案例
5. 對應測試
6. Gate 2 關閉條件新增「CORE_16 的 16 個特徵全部可計算」
7. Master Plan §5.2（7→8 SBs）、§8 新增 Brief、`PROJECT_STATUS.md` 同步

**Out of Scope**：`open_price`（CORE_16 明文「移除 open/high/low」作為**直接特徵**，
本 SB 只把 high/low 當作 `amplitude_ratio` 的**輸入**，不將它們寫入 `daily_ml_features`）；
`rsi_14 → fillna(50.0)` 等既有欄位的 NULL 策略複審（另案）；
RISK-016／RISK-018 的修法。

---

## 6. Tests

| # | 測試 | 釘住什麼 |
|---|------|---------|
| 1 | `test_amplitude_ratio_formula` | `(High − Low) / Close` 與人工核算相符 |
| 2 | `test_ma_bias_ratios_formula` | MA5／MA20 偏離率公式 |
| 3 | `test_volume_ratio_5d_formula` | `Volume / MA5_Vol` |
| 4 | `test_warmup_period_null_or_fill_per_ruling` | 暖機期行為依決策點 2／3 裁示 |
| 5 | **`test_missing_high_low_does_not_fabricate_zero_amplitude`** | **決策點 1 的驗收**：high/low 缺席時不得產出 `0.0` |
| 6 | **`test_zero_volume_baseline_is_not_filled_as_one`** | **決策點 3 的驗收**：MA5_Vol = 0 時不得填 `1.0` |
| 7 | `test_price_query_selects_high_low` | 讀取端契約：SELECT 必須含 high/low |
| 8 | 反查檢查的 known-FAIL | 移除 `high_price` → Part B 第 12 項 FAIL |

**第 5、6 項在裁示為「保持 NULL」時是 known-FAIL**，
須**先寫、先確認 FAIL、留原始輸出**，才動 `src/`（§13.5、§9A.2）。

---

## 7. E2E Verification Plan

隔離臨時 DB（RISK-013 綁定確認先行），灌入涵蓋以下情境的 fixture：
正常交易日、暖機期（前 4／19 日）、**high/low 缺席**、**連續 5 日零成交**。
走真實 DB 讀取路徑驗證四欄的值與人工核算逐位相符。

**額外**：本 SB 完成後，`postgres`@`localhost:5432` 的 `daily_ml_features`
四欄應由 0/117 變為有值（暖機期與缺資料列除外）——
**但對真實庫重跑 pipeline 需另行授權**，不在本 SB 自動進行。

---

## 8. Definition of Done（**每一項指名資料庫**，`gate-submit` 產出 7）

- [ ] `db_writer.py` 的股價查詢含 `high_price`／`low_price`。
- [ ] 四個公式已實作，測試全過。
- [ ] NULL 策略依裁示落地；契約條文（§3.4／§5A.3）同步修正。
- [ ] 第 5、6 項 known-FAIL **實作前已確認 FAIL 並留存原始輸出**。
- [ ] `gate0_contract_check.py` Part B **12/12 PASS**，反查檢查含 known-FAIL 實測輸出。
- [ ] 全套測試於**隔離臨時 DB** 通過，附實際輸出與 `current_database()` 確認。
- [ ] E2E 於**隔離臨時 DB** 完成，四欄值與人工核算逐位相符。
- [ ] Gate 2 關閉條件已新增；Master Plan §5.2／§8 與 `PROJECT_STATUS.md` 已同步。
- [ ] `PROJECT_STATUS.md` §0.4 基線數字重新核對。
- [ ] contract-check `exit 0`；無夾帶格式／行尾變更。

> **未列入 DoD**：`postgres`@`localhost:5432` 的四欄實際填值——
> 那需要對真實庫重跑 pipeline，**須另行授權**，不併入本 SB。

---

## 9. PO 決策點

| # | 事項 | 本提案建議 |
|---|------|-----------|
| 1 | `amplitude_ratio` 的 `fillna(0.0)`——**它沒有暖機期，該填補只可能在成因 F 時觸發** | **改為保持 NULL**，並修正契約 |
| 2 | `ma5_bias_ratio`／`ma20_bias_ratio` 暖機期填 `0.0` | **維持契約**，但記錄「0 是事件不是值域中點」的區別 |
| 3 | `volume_ratio_5d` 的 `fillna(1.0)` 混了暖機期與 MA5_Vol=0 兩種成因 | **拆開**：暖機期填 `1.0`、**MA5_Vol=0 保持 NULL**，並修正契約措辭 |
| 4 | 反查檢查對無法機械解析項目的處置 | **明確輸出「未涵蓋」清單**，不靜默略過 |

---

## 10. 待 PO 裁決

| # | 事項 | 狀態 |
|---|------|------|
| 決策點 1～4 | 見 §9 | **待裁決** |
| — | 本提案整體是否核准進入實作 | **待裁決**（核准前不動 `src/`） |
