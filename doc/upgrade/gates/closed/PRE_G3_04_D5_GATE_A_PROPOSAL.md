# `PRE-G3-04`：D5 落地 —— 契約 U 分支 + 空日情緒 NULL 化 + 全量特徵重算

- 日期：2026-09-07
- 性質：**Gate A 提案。Plan-Before-Code —— 本檔未修改任何程式碼或契約文件，僅規劃。**
- 依據：`PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md` §1.6（D5 建議）、
  PO 2026-09-07 裁示「放行第 2 段」
- 前置 Gate：`PRE-G3-01`（B1 試點）、`PRE-G3-02`（覆蓋率門檻）、`PRE-G3-03`（回補與匯入）
  皆已完成並經 PO 裁決

---

## 0. 一句話

**`sentiment_mean` 在空日填 `0.5` 是編出來的，不是算出來的 —— 這裡把它改回 `NULL`，
並用同一次全量重算，把契約與現況同步。**

---

## 1. Goal

1. `FEATURE_REGISTRY.md` §5A.2 補上 `DEC-030`（2026-08-31）已宣告、但判定流程從未寫入的
   **U（數學未定義）分支**
2. 程式碼：空日（`article_count == 0`）的 `sentiment_mean` 及其四個衍生欄
   （`sentiment_3d_ma`／`sentiment_5d_ma`／`sentiment_lag_1`／`sentiment_lag_2`）
   由填補 `0.5` 改為保持 `NULL`（成因 U）；`article_count`／`bullishness_index`／
   `agreement_index` **維持不變**（它們是空日的真值，不是編出來的）
3. **全量重算 `daily_ml_features`**（一次做，含 D5 語意）—— `PRE_G3_02` §5、
   `PRE_G3_03` 結果檔皆已登記此為 Gate 3 阻斷項

## 2. Requirement Source

`PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md` §1.6 建議 2、4（PO 已裁決採行，
`5bfb3b8`）：

> 但 `sentiment_mean` 與其四個衍生欄在空日應為 NULL（成因 U），不是 `0.5`
> —— 依 §5A.1 的 U 定義與 DEC-030 的既有先例（`volume_ratio_5d` 的 `MA5_Vol == 0`）
>
> §5A.2 的判定流程需補 U 分支 —— 這是把 DEC-030 那次修訂做完

## 3. Current State（唯讀查證，本節無任何推測）

### 3.1 契約現況

`FEATURE_REGISTRY.md` §5A.1（`:322-351`）已含三種成因定義（W／F／U，DEC-030）；
§5A.2 判定流程（`:353-366`）**只有兩個分支**（`SOURCE_FAILED` → F；
`SUCCESS`/`SUCCESS_EMPTY`/`SOURCE_DEGRADED` → 依 §5A.3 處理 W）——**U 分支缺席**。

### 3.2 程式碼現況：三個精確異動點（皆已逐行讀過，非推測）

| 位置 | 現況 | 成因 |
|---|---|---|
| `feature_aggregator.py:539-540` | `sentiment_mean` 對所有非 `is_failed` 列 `.fillna(0.5)` | 空日與有資料日混填同一段 |
| `feature_aggregator.py:683-685` | `sentiment_3d_ma`／`sentiment_5d_ma` 為 `.rolling(min_periods=1).mean()`，**運算對象是已被上述填過的 `sentiment_mean`** | 若上游不填，本段**不需要改**（見 §5.2 實測） |
| `feature_aggregator.py:693-694` | `sentiment_lag_1`／`sentiment_lag_2` 為 `.where(is_failed, _lagN.fillna(0.5))` | 混合了「真暖機期」與「上一日是空日」兩種成因（見 §5.3） |

### 3.3 既有的「最後一道遮罩」機制（F 分支，本次沿用其架構）

`enforce_source_failed_nulls()`（`:36-63`）於 `generate_daily_features` 收尾處
（`:716`，晚於所有 rolling／shift 計算）對 `is_failed` 列強制把 8 個社群欄位設回
`NaN`。其 docstring 已寫明理由：「情緒欄經過填補、rolling、shift 三段處理，
每一段都可能把 NULL 補回去……集中在一個地方，契約要求才有一個可稽核的落點」。

**本提案的 U 分支設計沿用同一個原則**（見 §5）。

### 3.4 既有測試鎖住了即將改變的行為

`tests/test_source_failed_nulls.py:211-218` 的
`test_success_empty_keeps_the_neutral_fill`：

```python
self.assertTrue((df["sentiment_mean"] == 0.5).all(),
                "SUCCESS_EMPTY 的填值屬 RISK-020，排定 Gate 3 啟動前裁決 —— "
                "B 輪不提前動它")
```

**這個測試明確斷言「填 0.5」，且註解自己說這是暫定、待裁決** ——
本 SB 是那個裁決發生的時刻，**該測試的斷言方向需要整個反過來**
（`== 0.5` → `.isna()`）。

⚠ 該測試的註解把此事歸給 `RISK-020` ——**核對後這是不精確的**：
`RISK-020` 是**價量欄位**（`ma5_bias_ratio` 等）的暖機期填值裁決，
與本次的**社群情緒**填值是不同風險項。此為既有文件的小瑕疵，
**本 SB 一併修正該測試的註解指向**，不歸咎於任何人，只是連帶處理。

---

## 4. In Scope

1. `FEATURE_REGISTRY.md` §5A.2 補 U 分支
2. `feature_aggregator.py` 三處異動（§5 詳列）
3. `tests/test_source_failed_nulls.py` 的 `test_success_empty_keeps_the_neutral_fill`
   改寫斷言方向；新增本 SB 專屬測試（§7）
4. 全量重算 `daily_ml_features`（RISK-013 三項）
5. `REMAINING_RISKS.md`：RISK-020 的既有測試誤指向連帶修正

## 5. Out of Scope（明確排除，不在本輪動）

- **`RISK-020` 本身的裁決**（價量欄位暖機期填值是否為事件值）—— 不同風險項，Gate 3 啟動前另案
- **`RISK-023`**（`comment_polarization`／`net_push_momentum` 不受 DEC-024 保護）—— 契約已明訂「保持 NULL」，本次不變動
- **`SOURCE_DEGRADED` 的接線**（`:568-582` 已記載為刻意延後的設計決定）—— 與 U 分支無關，不順手做
- **`UG-G3-SB2`**（訓練排除邏輯，讀 `daily_ml_features` 的消費端）—— 本 SB 只管 NULL 語意，不管訓練端如何使用

---

## 5. 程式碼變更設計（精確到欄位，含實測依據）

### 5.1 `sentiment_mean`（`:539-540`）

**變更**：移除該行的 `.fillna(0.5)`。空日（無 `daily_direct`／`daily_theme` 匹配）
的列在 `merge` 後 `sentiment_mean` 自然為 `NaN`，維持不填。

**不變**：同段的 `article_count`／`bullishness_index`／`agreement_index` 三個
`fillna` **維持不動**——它們在空日是真值（見 `PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md`
§1.4 逐欄對照表：`bullishness_index` 有 Laplace 平滑定義、`agreement_index`
公式明文定義 `Pos+Neg==0 → 0.0`）。

### 5.2 `sentiment_3d_ma`／`sentiment_5d_ma`（`:683-685`）

**變更：無**（實測驗證，非推測）。

```python
>>> s = pd.Series([0.6, nan, 0.4, nan, nan, 0.8])
>>> s.rolling(3, min_periods=1).mean()
[0.6, 0.6, 0.5, 0.4, 0.4, 0.8]
```

`rolling(window, min_periods=1).mean()` 對 `NaN` 的處理是 **nanmean 語意**——
`min_periods=1` 計的是窗內**非 NaN 觀測值數量**，不是原始列數。**移除 §5.1
的早期填補後，本段的行為自動變成「窗內有值的日子取平均，全為空則本身為 NaN」**，
不需要任何程式碼改動。

⚠ **這與 F 分支不同**：`enforce_source_failed_nulls` 對 `is_failed` 列仍會在
最後把這兩欄強制設回 `NaN`（即使窗內有其他有效值）——**U 分支刻意不做同等的
強制清空**，因為「3 日內至少一天有真實情緒」本身是一個誠實可用的訊號，
不是編造。**這是本提案唯一一處 U 與 F 處理方式不同的地方，需要 PO 明確確認。**

### 5.3 `sentiment_lag_1`／`sentiment_lag_2`（`:693-694`）

**這是三個異動點裡唯一需要新邏輯的一處**，因為 `shift(1)` 產生的 `NaN`
**無法從結果本身分辨兩種成因**：

```python
>>> df.groupby('stock_id')['sentiment_mean'].shift(1)
```

—— 對「該股票序列的第一列」（真暖機期，前面沒有任何一天）與
「前一天本身是空日（U 已生效，`sentiment_mean[T-1]` 為 `NaN`）」，
**兩者的 `shift(1)` 結果同樣是 `NaN`，肉眼與程式都分不出來**（已實測驗證）。

**設計**：改用 `groupby('stock_id').cumcount()` 判定**真暖機期**（與 `NaN` 的
成因無關的獨立判準）：

```python
_is_true_warmup_lag1 = df.groupby('stock_id').cumcount() < 1   # 序列第 1 列
_is_true_warmup_lag2 = df.groupby('stock_id').cumcount() < 2   # 序列前 2 列
```

- **真暖機期**（`cumcount() < N`）→ **填 `0.5`**（W，既有行為維持）
- **非真暖機期但仍是 `NaN`**（即 T-N 那天本身是空日）→ **保持 `NaN`**（U 的傳播，
  不填）

> **這保留了資訊，不是保守起見的過度清空**：若前一天確實有討論、只是今天沒有，
> `sentiment_lag_1[今天]` 仍應誠實反映「昨天有討論、分數是多少」——
> **這件事我們真的知道，填成 NULL 才是錯的方向。**

### 5.4 三處變更後，`enforce_source_failed_nulls` 是否需要修改

**不需要**。它作用於 `is_failed` 列，對 8 欄一律強制 `NaN`，與 U 分支的判定邏輯
（`article_count == 0` 且非 `is_failed`）互斥，不會互相覆寫或衝突。

---

## 6. 契約變更（`FEATURE_REGISTRY.md` §5A.2）

新增第三分支，草稿（**待 PO 核准後才寫入契約**）：

```
elif source_status in ('SUCCESS', 'SUCCESS_EMPTY', 'SOURCE_DEGRADED'):
    → 依 §5A.3 對照表處理暖機期（成因 W）
    → 若 article_count == 0（無論 SUCCESS 或 SUCCESS_EMPTY）：
        sentiment_mean 及其四個衍生欄（3d_ma／5d_ma／lag_1／lag_2）
        保持 NULL（成因 U），除非該列落在序列前 1～2 列（真暖機期，填中立值）
        article_count／bullishness_index／agreement_index 不受影響（真值）
    → 留言三欄若「未啟用／無推噓資料」仍為 NULL（成因 F 的子類）
```

`§5A.3` 對照表的「暖機期處理」欄需同步加註：`sentiment_mean` 等 5 欄的 W 分支
**現在有一個子條件**（真暖機期 vs U 傳播），不再是單純的「允許填補」。

`PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md` §1.4 的逐欄對照表**已經是這份契約
修訂的草稿**（PO 已核可其內容，`5bfb3b8` 裁決 D5「隨 D5 一併寫入」）——本 SB
把它從提案文件搬進正式契約，不是重新設計。

---

## 7. Failure Semantics & 測試計畫

### 7.1 需要的測試（新增或改寫）

| # | 測試 | 內容 | Known-FAIL 案例 |
|---|---|---|---|
| T1 | `test_success_empty_keeps_the_neutral_fill` **改寫** | 斷言方向反轉：`SUCCESS_EMPTY` 且 `article_count==0` 的列，`sentiment_mean`／`3d_ma`／`5d_ma`／`lag_1`／`lag_2` 皆 `.isna()`；`article_count==0`／`bullishness_index==0.0`／`agreement_index==0.0` **不變** | 還原成舊斷言（`==0.5`）即 FAIL——證明測試真的在測新行為，不是恆真 |
| T2 | 真暖機期 vs U 傳播區分 | 建構一檔股票：第 1 列有資料、第 2 列空、第 3 列空 —— 斷言 `lag_1[第2列]` = 第1列的值（非 NULL，真實已知）；`lag_1[第3列]` 為 NULL（U 傳播，第2列本身未知） | 若誤用「`NaN` 即填 0.5」的舊邏輯，`lag_1[第3列]` 會變成 0.5，測試 FAIL |
| T3 | `sentiment_3d_ma` 視窗內部分有值 | 3 日視窗中 1 日有資料、2 日空 —— 斷言結果為該 1 日的值（非 NULL、非 0.5 平均），驗證 §5.2 的 nanmean 語意 | 若上游仍填 0.5，結果會被 0.5 污染，測試 FAIL |
| T4 | `is_failed` 與 U 互斥 | 同一批資料，部分列 `is_failed=True`、部分 `article_count==0` 但非 failed —— 斷言兩者的 8 欄／5 欄清空範圍不同（F 清 8 欄含 `article_count`；U 只清 5 欄，`article_count` 仍為 0 非 NULL） | 若 U 分支誤用 F 的遮罩函式，`article_count` 會被錯誤清成 NULL，測試 FAIL |

### 7.2 §5A.2 補 U 分支後，契約反查測試

**已查證**（`gate0_contract_check.py:83`）：B 系列只有 B3 依賴 §5A.3（不是 §5A.2）——
以正則解析該表格每列的「社群」／「社群留言」分類與第 4 欄（F 分支處理）是否含
`NULL` 字樣。**本提案 §6 的契約修訂只在 W 欄位加註子條件，不觸碰 F 欄位文字**，
B3 的解析對象不受影響。§5A.2 本身**沒有任何自動化反查**依賴其分支數量——
**本 SB 不新增此類檢查**，避免製造一個目前沒有消費者的機制。

---

## 8. 全量重算：預期先算死

### 8.1 列數（**已獨立驗證，非估算**）

```sql
SELECT count(*), count(DISTINCT (stock_id,trade_date)) FROM stock_prices;
-- 3713, 3713（(stock_id, trade_date) 為 UNIQUE 約束，無重複）
```

`generate_daily_features` 以 `LEFT JOIN` 建立在 `df_prices_clean` 之上
（`:merge(..., on=['trade_date','stock_id'], how='left')`），`daily_sentiment`／
`daily_theme` 皆經 `groupby(['trade_date','stock_id'])` 保證每組至多一列，
**不會產生笛卡爾積增列**；`generate_target_labels` 只做 `shift(-1)` 賦值，
**不刪除任何列**。

> **預期：重算後 `daily_ml_features` = 3,713 列**（現況 137 列）。
> **這會是本專案第一次有真正規模的特徵面板** —— 27 倍於現況。

逐檔分佈（= `stock_prices` 逐檔列數，已知）：`2330=987、2382=987、6488=985、NVDA=754`。

### 8.2 RISK-013 三項

| # | 要求 |
|---|---|
| 1 | 綁定確認 |
| 2 | 新鮮 `pg_dump`，落 `TEAM_PLAYBOOK.md` §7A.1 位置 |
| 3 | 拋棄式容器實測還原；**指紋比對務必用動態 `information_schema.columns` 欄位清單**（`PRE_G3_03_import_result.json` 已記過一次手寫欄位清單造成的假警報，不得重蹈） |

### 8.3 重算方式

`main_etl_pipeline.py:544-557` 的 `run_feature_engineering_pipeline()` 邏輯
（`fetch_all_for_features` → `generate_daily_features` → `generate_target_labels`
→ `upsert_ml_features`）——**與 `PRE_G3_02_coverage_measurement.json` 的量測
使用同一個聚合函式**，差別只在於這次要 `upsert_ml_features` 寫回。

⚠ **已查證**（`db_writer.py:717-721`）：`upsert_ml_features` 為
`INSERT ... ON CONFLICT (trade_date, stock_id) DO UPDATE`。

> **這次的「覆寫」是預期行為，不是 `PRE-G3-03` §3.4 那種要避免的意外覆寫。**

理由：本次是**全量**重算全部 3,713 列，範圍**含蓋**既有 137 列所在的
`(stock_id, trade_date)`——重算的目的正是要用 D5 語意（U 分支）**取代**這 137 列
既有的、含填補 `0.5` 的舊值。`PRE-G3-03` 的「既有列不碰」原則適用於**價格回補**
（新舊資料代表同一份事實，覆寫等於銷毀證據）；**本次不同**：新值本來就是要
取代舊值的正確版本，覆寫是目的本身，不是意外。**此處先行揭露以免與先前案例的
原則混淆**——兩者看起來都是「DO UPDATE」，但對應到完全不同的裁決。

---

## 9. Risks & Trade-offs

| 風險 | 說明 | 緩解 |
|---|---|---|
| §5.3 的 `cumcount` 設計若寫錯 | 真暖機期與 U 傳播判斷反了，會讓已知資訊變 NULL 或未知資訊變 0.5 | T2 測試直接鎖住這個邊界情況 |
| 全量重算耗時 | 3,713 列 vs 現況 137 列，執行時間預期顯著增加 | 屬預期，非風險；RISK-013 的還原驗證同樣需要重跑一次相同規模的比對 |
| `RISK-020` 誤指向 | 既有測試把本議題錯記成 RISK-020 | §3.4 已識別，本 SB 一併修正註解 |
| U 分支與 F 分支的「3d_ma／5d_ma 是否強制清空」不同調 | §5.2 刻意讓 U 分支不做同等清空 | 已於 §5.2 明確標注，**需 PO 確認是否同意這個不對稱** |

---

## 10. E2E Verification

1. 單元測試（T1~T4）全綠，且逐項出示 known-FAIL（§7.1 已列）
2. `gate0_contract_check.py` 全過
3. 重算後獨立查證：`daily_ml_features` 列數 = 3,713（逐檔核對）；
   抽樣若干 `SUCCESS_EMPTY` 列確認 `sentiment_mean IS NULL`；
   抽樣若干真暖機期列確認仍為 `0.5`
4. 既有 F 分支行為不受影響（`enforce_source_failed_nulls` 相關既有測試維持全綠）

## 11. Documentation Sync

- `FEATURE_REGISTRY.md` §5A.2／§5A.3（本提案 §6 草稿）
- `tests/test_source_failed_nulls.py`（T1 改寫 + T2~T4 新增）
- `REMAINING_RISKS.md`：無需新增風險項（本 SB 是既有 D5 裁決的落地執行，
  不產生新風險），但 §3.4 的 RISK-020 誤指向於實作時一併修正註解
- `PROJECT_STATUS.md`：待 Gate B 通過後同步（§16.3 規則 3）

---

## 12. 待 PO 於 Gate A 核准時確認的三點

1. **§5.2 的不對稱**（U 分支不強制清空 `3d_ma`／`5d_ma`，F 分支強制清空）是否同意
2. **§5.3 的 `cumcount` 設計**（真暖機期 vs U 傳播分開判定）是否同意此複雜度，
   或接受更簡單但會損失資訊的替代方案（例如統一用 §5.2 同款「不強制清空」處理
   `lag_1`／`lag_2`，放棄真暖機期填補——**如此設計更簡單，但既有暖機期填補的
   既有測試行為會改變，需評估影響**）
3. **§8.3 的全量重算覆寫**是否需要額外授權措辭（區別於 `PRE-G3-03` 的「既有列不碰」
   原則——本次是刻意的全量覆寫，範圍不同）
