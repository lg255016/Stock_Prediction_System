# `UG-G3-SB2a` Gate A 提案：458 檔 Universe 資料回補（重送版，2026-09-10）

## 0. 摘要

把 `universe_snapshots` PIT 聯集的 458 檔股票，從已齊備的 `candidate_prices`
（444,877 列，2022-08-03～2026-09-04，`UG-G2-SB9` 回補）搬遷進生產特徵管線
（`stock_prices` → `feature_aggregator.py` → Triple-Barrier 標籤），使
`daily_ml_features` 從現有 3 檔（2330/2382/6488，NVDA 不在台股宇宙）擴大至
458 檔。**本提案回答 PO 指定的六項必答**（§3），核准前不動 `src/`、
`database/`、真實庫（Plan-Before-Code）。

**本版變更**：(1) 修正初版三處事實錯誤（§3.3 誤植 NaN 應為 SQL NULL、
§3.2 全量比對數字改用 PO 已完成的實測結果、§3.6 誤植「150 檔」應為全市場
~2,024 檔）；(2) 併入 PO 對 §9 四項裁決的核准與四項附帶條件（§3.1）；
(3) 標記 `CHAL-010`（每日特徵 upsert 覆寫標籤缺陷）**已於 commit `1126fe5`
修復並經 `sps_project_reviewer` 複核通過**，本 SB 的每日 ETL 前置條件不再是
「待修復」而是「已滿足」。

## 1. Requirement Source

| 來源 | 內容 |
|------|------|
| `doc/evidence/DECISIONS.md` DEC-036（`APPROVED`） | `UG-G3-SB2a` 拆分決策：資料回補與 PIT 讀取器分開驗收 |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §9 UG-G3-SB2a Brief | 既有核心欄位（Goal/Dependency/In-Out Scope/Tests/DoD），本提案補完整 Brief |
| `doc/governance/PROJECT_STATUS.md` §0.5 #20 | 每日 ETL 執行閘門，綁本 SB Gate B 通過解除 |
| PO 2026-09-10（`UG-G3-SB2` Gate B 結案訊息） | 六項必答項逐字列出 |
| `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-022（面向一／二／四） | 價格基準混合 |
| `doc/evidence/CHALLENGES.md` CHAL-010（已解決） | 每日特徵 upsert 全欄覆寫清空 Triple-Barrier 標籤——已於 `1126fe5` 修復並複核通過（PO 2026-09-10），是本 SB Gate B 通過、§0.5 #20 閘門解除的前置條件 |

## 2. Current State（唯讀查證，2026-09-10）

```sql
SELECT count(*), count(DISTINCT cp.stock_id), min(cp.trade_date), max(cp.trade_date)
FROM candidate_prices cp
JOIN (SELECT DISTINCT stock_id FROM universe_snapshots WHERE included) u
  ON u.stock_id = cp.stock_id;
-- 444877 | 458 | 2022-08-03 | 2026-09-04
```

- **458 檔、444,877 列、2022-08-03～2026-09-04（~4.08 年，平均每檔 971 列）**
  已在 `candidate_prices`，零外部請求即可搬遷。
- 既有 3 檔（2330/2382/6488）`stock_prices` 987/987/985 列；`daily_ml_features`
  同步；NVDA 754 列（美股，走獨立管線，不在本 SB 範圍）。
- 既有 3 檔與 `candidate_prices` **日期重疊列數**（未做逐欄值比對）：
  2330/2382/6488 各 985 列——見 §3.2，此數字只證明「日期對得上」，**不等於
  「值相同」**，兩者是不同的問題。

## 3. 六項必答

### 3.1 `stock_prices` 價格基準政策（RISK-022 面向二＋四）——**方案 B（PO 2026-09-10 核准，附四條件）**

**現況（已讀程式碼確認，`main_etl_pipeline.py`）**：

| 路徑 | 來源優先序 | 寫入 `source` |
|------|-----------|---------------|
| 每日批次（`UG-G2-SB7`，全市場） | `candidate_prices`（原始交易所價） | `twse_mi_index`／`tpex_daily_quotes`（帶原值過去） |
| 逐股每日路徑・TPEX（`run_tpex_pipeline_from_candidate_prices`） | 複製當日 `candidate_prices` 列 | 帶 `candidate_prices` 原值過去 |
| 逐股每日路徑・TWSE（`run_twse_pipeline`） | 自建爬蟲 `STOCK_DAY`（原始價）優先，失敗才落 **yfinance（`auto_adjust=True`，還原價）** | `twse_stock_day` 或 `yfinance_auto_adjusted` |

**問題**：TWSE 逐股路徑的 yfinance 備援是**還原價**，與 `candidate_prices`／
`twse_stock_day`（原始價）基準不同。458 檔回補若採 `candidate_prices` 原始價
作為歷史基底，但之後**每日**更新走 `run_twse_pipeline` 舊路徑，遇到自建
爬蟲失敗時就會把還原價寫進一張歷史全是原始價的股票序列——同一支股票的
時間序列裡混入不同基準，比現有 3 檔的問題規模擴大 153 倍（458/3）。

**方案比較**：

| 方案 | 做法 | 優點 | 缺點 |
|------|------|------|------|
| A：維持現狀 | 458 檔比照既有 3 檔，daily 走 `run_twse_pipeline`（爬蟲＋yfinance 備援） | 不改既有程式碼 | 基準混合風險按檔數線性放大；`source` 欄看得見混合但不解決它 |
| **B（建議）：TWSE 逐股路徑比照 TPEX，改為複製當日 `candidate_prices`** | 458 檔（含既有 3 檔）每日更新一律走「複製 `UG-G2-SB7` 批次階段已寫入的 `candidate_prices` 當日列」，不再呼叫 `run_twse_pipeline` 的爬蟲／yfinance 邏輯 | 基準單一（全部原始交易所價，`twse_mi_index`／`tpex_daily_quotes`）；批次階段本已對全市場請求一次，逐股不再重複觸網（比現狀更省請求）；`source` 值域不再需要 `twse_stock_day`／`yfinance_auto_adjusted` 兩種變體並存於同一檔股票 | 需要批次階段當日必須先於逐股階段完成（**現有編排已如此**，`run_all_daily_tasks()` §0 批次先行，逐股迴圈依賴批次結果，`test_batch_stage_runs_before_per_stock_stage` 已釘住順序）；`run_twse_pipeline`／`run_tpex_pipeline_from_candidate_prices` 兩套邏輯合併需要改動既有函式，非純資料操作 |
| C：458 檔用 A、既有 3 檔不動 | 只有新回補的 458 檔採方案 B，既有 3 檔維持舊路徑 | 改動範圍最小 | **兩套政策同時存在，是另一種混合**——「哪些股票走哪條路徑」本身要有人記得，且既有 3 檔的既有問題永遠不會被修 |

**核准**：**方案 B**，理由是它同時解決「新增的 458 檔」與「既有的 3 檔」
兩個面向，且與 `UG-G2-SB7` 已有的批次先行設計自然契合（批次已經抓過一次，
逐股沒有必要再抓一次、還可能抓到不同基準）。**方案 B 需要修改
`main_etl_pipeline.py` 的逐股迴圈邏輯**（把 TWSE／TPEX 統一成同一種「從
`candidate_prices` 複製」路徑），**這是本 SB 唯一觸及既有生產程式碼邏輯
的項目**，其餘皆為新增。

**PO 核准方案 B 時附帶四項條件（2026-09-10），皆為 In Scope，逐項落實**：

| # | 條件 | 落實方式 |
|---|------|---------|
| (a) | 邏輯改動（`main_etl_pipeline.py` 逐股路徑統一）與資料回補分開，**紅色測試先行、綠色實作後行，各自獨立 commit**，不得併成一個 red+green commit | §6 新增紅色測試清單；實作 commit 待紅色測試經 PO 確認為真實 RED 後才動工 |
| (b) | 逐股路徑改為複製 `candidate_prices` 後，**完全沿用 `run_tpex_pipeline_from_candidate_prices`（`main_etl_pipeline.py:260-309`）既有的批次 outcome 歸因語意**，不另立新規則：批次 `OK` 但當日無該股票列 → `NO_DATA`（該股當日未出現於報表，含停牌，與「批次真的失敗」明確區分，符合 `CLAUDE.md` §7.1「失敗與真的沒有資料必須可區分」）；批次未成功（`REFUSED`／`FETCH_FAILED`）→ 拋例外並帶上游 outcome。**唯一新增的核心條件：任何情況下都不落回 yfinance 或任何其他來源自行補值**——避免修掉一個基準混合問題卻另開一個「有時複製、有時仍用還原價」的新缺口 | §6 新增對應紅色測試（拆兩案：(i) 批次 `OK` 無列 → `NO_DATA` 且未呼叫 yfinance；(ii) 批次 `REFUSED`／`FETCH_FAILED` 無列 → 例外帶對應 outcome 且未呼叫 yfinance） |
| (c) | `run_twse_pipeline`（舊有的爬蟲＋yfinance 備援路徑）確認無其他呼叫點後**直接刪除**，不保留成死碼／不用 feature flag 暫留。**只刪 `run_twse_pipeline`，`run_us_stock_pipeline`（NVDA 美股路徑，`:310-318`）不動**——美股逐股路徑本就走 yfinance，不屬本 SB「TWSE 逐股路徑基準混合」問題範圍 | 實作 commit 內連同刪除；§6 新增「`run_twse_pipeline` 已刪除，無殘留引用，`run_us_stock_pipeline` 未受影響」檢查 |
| (d) | `stock_prices.source` 值域（migration 009 建立的 CHECK 約束）**不收窄**，`twse_stock_day`／`yfinance_auto_adjusted` 兩個既有值維持合法值域成員，**既有列不回填、不刪除**——方案 B 只影響「以後怎麼寫」，不重寫歷史 | §4 In Scope／Out of Scope 已載明，本節不重複 |

**`source` 值域影響**：方案 B 只動**台股逐股路徑（TWSE／TPEX）**，下方陳述
限定此範圍——**台股逐股路徑新寫入的列**只會出現 `twse_mi_index`／
`tpex_daily_quotes` 兩值（`twse_stock_day` 成為純歷史值，依條件 (d) 不回填、
不刪除，CHECK 約束不收窄）。**NVDA 走獨立的 `run_us_stock_pipeline`
（`:310-318`），每日仍寫 `yfinance_auto_adjusted`（真實庫現有 679 列即此
路徑產出）——方案 B 不動這條路徑，`yfinance_auto_adjusted` 不會因此收斂
成純歷史值。**

### 3.2 既有 3 檔重疊區處理

**歷史子集比對**（migration 009 header，`PRE-G3-03` 全欄比對，2026-09-07）：
137 列（migration 009 之前寫入、`source IS NULL`）中 58 列可比對（79 列
`candidate_prices` 無對應），33 列完全相符、24 列僅 `volume` 粒度差異
（上櫃張數 vs 股數，成因已查明，差幅 0.13%~0.35%）、1 列（6488@2026-08-21）
未解（volume 差 23%，價格欄亦不同）——**這只是 137 列子集，不是現有 985 列
全部**。

**全量比對結果**（PO 2026-09-10 唯讀查證，`stock_prices` 現有 985×3 列 vs
`candidate_prices` 同日列，逐欄 open/high/low/close/volume）：

| 股票 | 比對列數 | 完全相符 | 差異 |
|---|---|---|---|
| 2330 | 985 | 985 | 0 |
| 2382 | 985 | 985 | 0 |
| 6488 | 985 | **960** | **25 列 volume 差（其中 1 列同時價格差）**——985 − 25 = 960。
與 `PRE-G3-03` 已登記的 137 列子集內同一筆 6488@2026-08-21 未解差異、及 24 列
volume 粒度差異一致，非新發現 |

**另發現一項批次覆蓋缺口（非重疊區「值不同」問題，記入 §3.6 觀察清單）**：
2330／2382 於 2026-09-01／2026-09-02 兩日**存在於 `stock_prices`、但不存在於
`candidate_prices`**——即既有 3 檔在這兩日走的是逐股路徑（非批次階段
`UG-G2-SB9` 回補的候選池），本 SB 回補時這兩個股票在這兩日不會有
`candidate_prices` 列可複製，屬「來源本身缺席」而非「值衝突」。

> **⚠⚠ 訂正（PO 2026-09-11，段 2 基線比對期間發現，範圍遠大於上述兩檔
> 兩日）**：`candidate_prices` 實際存在**全市場（TWSE＋TPEX）8 個交易日
> 的完整缺口**——2026-08-24～08-28、08-31～09-02，這 8 天**所有** 458 檔
> 皆零列，不只 2330／2382 兩檔兩日。已以 TWSE 官方休市日期表（三個獨立
> 來源交叉核對）確認這 8 天皆非休市日，屬真實資料缺口，成因與上述批次
> 覆蓋缺口相同（`UG-G2-SB9` 一次性回補停在 2026-08-21、`UG-G2-SB7` 每日
> 批次自 2026-09-03 才開始執行，中間窗口無銜接機制——**待對 `UG-G2-SB9`
> 證據確認**，本提案未逐一查證該次回補的收尾記錄）。另查證 2026-07-10
> 為颱風巴威造成的全日休市，該日無列正確，非缺口。**此缺口已於段 2 前置
> 作業中補齊**（`scripts/verify/ug_g3_sb2a_backfill_candidate_prices_gap.py`，
> 三輪 binding confirmation，`candidate_prices` 1,825,814→1,841,594），
> 隨後重跑段 1 腳本補齊 `stock_prices` 對應的 8 天（445,635→449,263）。
> 完整過程與證據見
> `doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_gap_and_baseline.json`。

**處理規則（定案）**：
- 完全相符（2330／2382 全數、6488 960/985）：無需動作，回補其餘 455 檔即可。
- 僅 volume 粒度差異（6488 的 24 列）：**保留既有列不覆寫**（`stock_prices`
  是生產表，已被下游特徵與標籤消費過；`candidate_prices` 的張數粒度本身也
  不是「更對」，只是「不同」）。
- 未解差異（6488@2026-08-21，1 列）：**保留既有列，登記但不処理**——同
  migration 009 header 的既定態度，不因本 SB 回補而重新追查成因。
- 2330／2382 的 2026-09-01／09-02 批次覆蓋缺口：**不在本 SB 處理**——這是
  逐股路徑歷史寫入與批次階段候選池不同步的既有現象，登記於 §3.6 觀察清單，
  待方案 B 實作後（逐股路徑改為複製批次候選池）由設計本身消除，不需回補
  動作。
- **2026-08-24～09-02 全市場 8 天缺口：已回補**（見上方訂正框）——與
  2330／2382 的兩日缺口性質不同（那是「來源本身缺席」，這是「候選池
  尚未涵蓋」），本次已用既有生產函式 `run_price_batch()` 逐日補齊，
  非本 SB 設計範圍內的既定行為，是唯讀查證期間發現的前置缺口，補齊後
  才能讓段 2 基線比對正確對齊 458 檔的完整交易日曆。
- **一般規則：`candidate_prices → stock_prices` 回補只補「既有列缺席的
  日期」（`DO NOTHING`／先查再插），不使用 `ON CONFLICT DO UPDATE`
  覆寫既有列**——比照 `PRE-G3-03` 回補路徑既有原則（migration 009 header
  已引用），避免任何一次回補靜默抹掉已被消費過的生產資料。

### 3.3 458 檔範圍內的 SQL NULL 價格列規模（唯讀量測，⚠ 非 RISK-024）

> **訂正**：初版此節誤把 SQL `NULL` 寫成「NaN」。兩者不是同一件事——
> `= 'NaN'::numeric` 在 458 檔範圍內查詢結果為 **0 列**；本節談的是
> `IS NULL`（該欄位完全沒有值），與 RISK-024 登記的「`daily_ml_features`
> 現有 1 列 NVDA `NaN`」是**兩個不同分類的現象**，不應合併討論或用同一個
> 分母做同量級推廣。本節獨立處理，不再引用 RISK-024。

```sql
SELECT count(*), count(DISTINCT cp.stock_id) FROM candidate_prices cp
JOIN (SELECT DISTINCT stock_id FROM universe_snapshots WHERE included) u
  ON u.stock_id = cp.stock_id
WHERE cp.open_price IS NULL OR cp.high_price IS NULL
   OR cp.low_price IS NULL OR cp.close_price IS NULL;
-- 80 列，38 檔股票（分母 444,877，佔比 0.018%）
```

**分類**（PO 2026-09-10 唯讀查證，80 列逐列讀出後分類）：

| 分類 | 列數 | 說明 |
|---|---|---|
| `volume = 0` | 78 | 當日候選池有紀錄但零成交，`candidate_prices` 對零成交日以價格全 NULL 表示——與 `UG-G2-SB9` 建立候選池時的既定表示法一致，非本 SB 新發現的資料品質問題 |
| `volume > 0` 但價格全 NULL（**異常**） | 2 | `4562@2023-10-30`（volume=102）、`4583@2022-09-19`（volume=100）——見下段成因排查 |

**2 列異常成因排查**（唯讀，讀前後各 5 個交易日對照）：兩列的共同特徵是
（1）成交量遠低於相鄰交易日（4562：102 vs 相鄰日千餘至逾十萬股量級；
4583：100 vs 相鄰日千餘至逾五萬股量級——數字隨查詢時點的相鄰日窗口而異，
此處僅陳述量級落差，不逐一列出易過期的具體數字），（2）皆為單日孤立事件，
前後日價格與量體正常，
（3）`source` 皆為 `twse_mi_index`（月成交資訊來源檔，非爬蟲即時單股頁）。
**推論**（`ENGINEERING JUDGMENT`，未逐一回溯 TWSE 原始來源檔案確認，
不可重跑——僅是本次唯讀量測範圍內的最佳解釋）：型態與「當日該股僅有極少量
零股／人工管制撮合、月成交資訊來源檔記錄到成交量但未產生可用收盤價格」的
已知 TWSE 資料揭露方式一致，非本專案 ETL 管線邏輯缺陷。**本 SB 不因此新增
防禦邏輯**——`UG-G3-SB1` 的 Triple-Barrier 消費端已正確處理此類 NULL
（NaN High/Low → `insufficient_data`；NaN anchor → `no_entry`，`874b3bf`
修復），80 列（含此 2 列）回補後走既有路徑即可，不需要額外分支。若日後
需要對原始來源檔案做逐列覆核，屬另案，不在本 SB 範圍。

### 3.4 回補腳本設計（比照 `UG-G3-SB1`／`UG-G3-SB2` 寫入腳本模式）

三段管線，**各自獨立的一次性腳本**，各自的 RISK-013 三項協議（獨立備份、
獨立 binding confirmation，不得合併成一次寫入）：

| 段 | 腳本（新建） | 讀 | 寫 | 備份檔名慣例 |
|---|---|---|---|---|
| 1 | `scripts/verify/ug_g3_sb2a_backfill_stock_prices.py` | `candidate_prices`（458 檔） | `stock_prices`（純新增，`DO NOTHING` 排除既有日期，見 §3.2） | `..._PRE_g3_sb2a_stock_prices_<ts>.dump` |
| 2 | `scripts/verify/ug_g3_sb2a_backfill_features.py` | `stock_prices`（458 檔全量） | `daily_ml_features`（呼叫既有 `feature_aggregator.py`，邏輯不變，只是規模擴大） | `..._PRE_g3_sb2a_features_<ts>.dump` |
| 3 | `scripts/verify/ug_g3_sb2a_backfill_labels.py` | `stock_prices`（458 檔） | `daily_ml_features.target_triple_barrier`／`label_reason`（呼叫既有 `generate_triple_barrier_labels()`，沿用 `UG-G3-SB1` 寫入腳本硬化後的四道核對：列數／分布快篩／逐列精確比對／備份新鮮度） | `..._PRE_g3_sb2a_labels_<ts>.dump` |

**每段皆遵循已驗證過的既定模式**：環境變數連線（不留字面連線值）、唯讀
預覽為預設、`--write --backup <path>`（存在／非空／24h 新鮮度機械檢查）、
stdin 庫名二次確認、**每批一個交易內完成寫入與影響列數核對**（段 1 僅一批、
即一個交易；段 2／3 依 §3.5 分批，每批各自一個交易）、commit 前逐列讀回
精確比對、rollback on mismatch（回滾範圍限該批，不影響已成功批次）。
**第 3 段直接沿用 `UG-G3-SB1` 腳本已證明過的核對邏輯，不重新發明。**

### 3.5 量體與時間估算、分批策略

- **總量**：458 檔 × 平均 971 列 ≈ **444,877 列**（候選池已有的量，非估計，
  §2 已查證）。
- **段 1（價格搬遷）**：純資料庫內操作，零外部請求，預期為秒級～分鐘級
  （INSERT 44.5 萬列，單一交易）。**不需分批**——沒有觸網成本，分批只會
  增加多次 RISK-013 協議的摩擦，不增加安全性。
- **段 2（特徵計算）**：`feature_aggregator.py` 對每列計算技術指標（含
  滾動窗口），444,877 列的運算量遠大於現有 3,713 列（約 120 倍）。**建議
  分批**——按 `universe_snapshots` 的 46 期或依股票代碼字母／數字分段，
  每批寫入後獨立驗證（列數核對），避免單一交易時間過長、也讓失敗時的
  影響範圍可控。**批次大小待實測段 2 單批（如 20 檔）的實際耗時後才能
  定案**，本提案不先估算未量測過的執行時間。
  **PO 2026-09-10 裁決**：擴大到 458 檔前，**先只對既有 3 檔（2330／2382／
  6488）重新跑一次段 2 邏輯（同一套 `feature_aggregator.py`，不擴大範圍），
  逐欄比對輸出與現行 `daily_ml_features` 是否一致**——這是規模放大前的
  基準比對關卡，只有 3 檔基準比對通過（無非預期差異）才可繼續擴大到全部
  458 檔。此步驟獨立於既有 3 檔的段 1 重疊區處理（§3.2），段 1 談的是
  `stock_prices` 原始價格列，此處談的是段 2 特徵計算輸出本身的正確性。
- **段 3（Triple-Barrier 標籤）**：純向量化計算（`generate_triple_barrier_labels`
  對 458 檔 groupby 迭代），量體與段 2 同源，可與段 2 同批次策略。
- **原則（PO 2026-09-10 裁決，§9 事項 3）**：**每段（非每批）一次備份、
  逐批獨立驗證、每批各自一個交易**——段 2／段 3 皆為 `daily_ml_features` 的
  欄位更新，同一張表同一段內的多個批次共用該段的一次 `pg_dump` 備份
  （存放於 `D:\Python\Database_Backups\Stock_Prediction_System2\`），但每批
  各自在**自己的一個交易**內完成寫入與影響列數核對，**失敗只回滾該批**，
  不影響同段內已成功的其他批次；驗證頻率不因共用備份而放寬。

### 3.6 閘門解除條件與解除後觀察清單

**解除條件**：本 SB（`UG-G3-SB2a`）Gate B 通過——即 §3.1 基準政策**已實作**
（`main_etl_pipeline.py` 逐股路徑改為統一複製 `candidate_prices`，方案 B
四條件皆落實），458 檔資料回補三段皆完成且驗證通過。

**解除後第一次執行（`run_all_daily_tasks()`）的觀察清單**（非本 SB 執行，
記於此供解除閘門時的另一輪 binding confirmation 使用）：

1. `entity_mapping` 路由指向的 161 篇孤兒文章（`UG-G3-SB2` CHAL-009 登記）
   是否正確歸屬到 2059／2454／3008／8069 四檔的 `direct_count`
2. 4 檔新追蹤股票（含這四檔與後續 AI 探索新增者）首次寫入 `stock_prices`
   的來源是否符合 §3.1 定案的政策（方案 B，應全數為
   `twse_mi_index`／`tpex_daily_quotes`，零 `yfinance_auto_adjusted`）
3. 滾動特徵（`volatility_5d`／`volatility_20d`／`ma5_bias_ratio` 等）在
   新股票暖機期（<20 個交易日歷史）的 NULL／預設值行為是否符合既有
   W／F／U 成因分類（`FEATURE_REGISTRY.md` §5A），不得新增未分類情形
4. 批次階段（`UG-G2-SB7`）處理 458 檔規模時的請求數與耗時，與現行**全市場
   批次規模（約 2,024 檔，`UG-G2-SB7` 本即全市場批次）**的既有量測基準比較，
   確認未觸發任何來源的 rate limit——
   **訂正**：初版此項誤寫「現行 150 檔」。150 並非追蹤宇宙規模（`
   tracking_keywords` 實際 27 列），而是 `SYSTEM_UPGRADE_MASTER_PLAN.md`
   `UG-G2-SB7` DoD 與 RISK-010（`:803-809`、`:1190`）記載的**規劃階段數字**
   「150 檔批次 ETL」／「台股前 150 檔」，實作時已擴大為全市場，予以更正
5. `stock_prices` 中 2330／2382 於 2026-09-01／09-02 兩日（§3.2 發現的批次
   覆蓋缺口）方案 B 實作後是否已能正常從 `candidate_prices` 取得對應列
   （即該缺口是否已由設計本身消除，而非仍需另案回補）
6. **2026-08-24～09-02 全市場 8 天缺口**（§3.2 訂正框發現、已回補）：
   確認方案 B 實作後的每日增量不會再產生同類窗口——批次階段
   （`UG-G2-SB7`）與逐股階段的銜接是否有機制保證「批次一旦中斷或延遲
   啟動，缺口會被自動偵測並回補」，或僅能依賴人工唯讀查證發現（如本次）

## 4. In Scope / Out of Scope

**前置條件（已滿足）**：`CHAL-010`（每日特徵 upsert 全欄覆寫清空既有
Triple-Barrier 標籤）已於 commit `1126fe5` 修復，並經 `sps_project_reviewer`
獨立複核通過（PO 2026-09-10）。本 SB 段 2（特徵計算，呼叫
`upsert_ml_features()`）可安全對 458 檔規模執行，不會重蹈同一缺陷——
此為段 2 動工與 Gate B 通過的前置條件，**現已滿足，非待辦項**。

**In Scope**：§3 六項必答對應的三段回補腳本；`main_etl_pipeline.py`
逐股路徑統一（方案 B，§3.1 四條件，紅色測試與實作分開 commit）；
`stock_prices`／`daily_ml_features` 兩表的資料本身（非 schema 變更）。

**Out of Scope**：
- `entity_mapping`／`tracking_keywords`——路由與追蹤宇宙擴大已在
  `UG-G3-SB2` 完成，本 SB 不動
- PIT 面板讀取器邏輯本身——`UG-G3-SB2` 已完成，本 SB 只是讓它讀到的資料
  從 3 檔變 458 檔
- 每日 ETL 閘門解除後的**執行**——閘門解除是本 SB 的 DoD，但解除後第一次
  真實執行需要另一輪 binding confirmation（§3.6），不在本 SB commit 範圍
- `RISK-022` 面向三（成交量單位混合，`best_bid_volume`／`best_ask_volume`）
  ——潛在風險，現無消費端，不因本 SB 而變成活躍風險

## 5. Affected Components

`database/`（`stock_prices`／`daily_ml_features` 資料，非 schema）、
`scripts/verify/`（三個新建回補腳本）、`main_etl_pipeline.py`
（方案 B，`run_twse_pipeline` 移除、逐股迴圈邏輯統一為複製
`candidate_prices`）。

## 6. Tests（規劃）

- 沿用既有 `tests/test_panel_dataset.py`／`tests/test_triple_barrier.py`
  邏輯測試——**不新增邏輯，只新增執行規模**，這些測試已覆蓋正確性
- 三個回補腳本各自的單元測試（MagicMock，比照
  `tests/test_entity_mapping_backfill.py` 模式）：讀取/白名單/核對/
  fail-closed 邏輯
- **方案 B 紅色測試清單**（§3.1 條件 (a)，須先 RED、經 PO 確認後才動工實作，
  與實作分開 commit）：
  1. TWSE 逐股路徑改走複製邏輯：斷言當日 `candidate_prices` 有該股票列時，
     `stock_prices` 寫入值與來源逐欄一致，`source` 沿用 `candidate_prices`
     的原值（`twse_mi_index`／`tpex_daily_quotes`）
  2. **台股逐股路徑**（TWSE／TPEX）`source` 值域收斂：斷言新寫入列的
     `source` 只會是 `twse_mi_index`／`tpex_daily_quotes` 兩者之一，不再
     產生 `twse_stock_day`；**明確排除美股路徑**——同時斷言
     `run_us_stock_pipeline` 寫入的 NVDA 列 `source` 仍為
     `yfinance_auto_adjusted`（未受影響，非收斂範圍）
  3. 批次 outcome 歸因語意（條件 (b)，沿用 `run_tpex_pipeline_from_candidate_prices`
     既有語意，拆兩案）：
     - (i) 批次 `OK` 但當日無該股票列 → 逐股路徑回傳 `NO_DATA`，且**沒有**
       呼叫 yfinance 或其他來源補值
     - (ii) 批次 `REFUSED`／`FETCH_FAILED` 且當日無該股票列 → 逐股路徑拋出
       例外並帶對應上游 outcome，且**沒有**呼叫 yfinance 或其他來源補值
  4. `run_twse_pipeline` 移除後無殘留引用（條件 (c)）：靜態掃描
     `grep -rn "run_twse_pipeline" --include="*.py"` 確認移除後只在
     `CHANGELOG`／歷史文件中出現，程式碼內零引用；同時斷言
     `run_us_stock_pipeline` 未被誤刪、呼叫路徑不變
  5. `source` 值域 CHECK 約束未被收窄（條件 (d)）：讀 migration 009 的
     CHECK 約束定義，斷言 `twse_stock_day`／`yfinance_auto_adjusted`
     仍在合法值域內

## 7. Rollback / RISK-013

每段獨立 `pg_dump` 備份 + 拋棄式容器還原驗證，比照 `UG-G3-SB1`／
`UG-G3-SB2` 已執行過的協議。三段皆為真實庫寫入，**無一段可省略 RISK-013**
（不因規模大小或"只是複製"而簡化）。

## 8. Definition of Done

| # | 項目 | 目標資料庫 |
|---|---|---|
| 0 | `CHAL-010` 修復（前置條件）——**已於 `1126fe5` 完成並複核通過** | 拋棄式 Postgres（`sps_project_reviewer` 複核用種列／回讀驗證，容器 `tmp_chal010@127.0.0.1:59998`，驗證後已拆除）；`postgres`@`localhost:5432` 僅唯讀核對（3,713／3,529／184，未寫入） |
| 1 | §3.1 方案 B 已實作（`main_etl_pipeline.py` 逐股路徑統一，四條件皆落實，紅色測試先行） | 不涉及寫入（政策已定案），實作含 `main_etl_pipeline.py` 變更 |
| 2 | §3.2 既有 3 檔全量比對已完成，處理規則已定案並執行 | `postgres`@`localhost:5432`，唯讀查證 + 依規則寫入 |
| 3 | §3.3 458 檔範圍 SQL NULL 80 列成因分類已完成（78 列零成交、2 列異常已排查） | `postgres`@`localhost:5432`，唯讀 |
| 3a | §3.5 段 2 基線比對：既有 3 檔重跑段 2 特徵計算，與現行 `daily_ml_features` 逐欄比對無非預期差異，**通過後才可擴大到 458 檔** | `postgres`@`localhost:5432`，唯讀比對 |
| 4 | `stock_prices` 458 檔皆有資料（段 1） | `postgres`@`localhost:5432`，RISK-013 |
| 5 | `daily_ml_features` 458 檔皆有特徵（段 2） | `postgres`@`localhost:5432`，RISK-013 |
| 6 | `daily_ml_features` 458 檔皆有 Triple-Barrier 標籤（段 3） | `postgres`@`localhost:5432`，RISK-013 |
| 7 | `PROJECT_STATUS.md` §0.5 #20 閘門解除 | 治理文件，非資料庫 |

## 9. PO 裁決事項（2026-09-10 已裁決）

| # | 事項 | 裁決 |
|---|---|---|
| 1 | §3.1 基準政策：方案 A／B／C | **方案 B 核准，附四條件（§3.1 表）** |
| 2 | §3.2 既有 3 檔全量比對：核准先做這項唯讀量測 | **核准，已完成（§3.2 全量比對結果）** |
| 3 | §3.5 段 2/3 分批策略：每批各自備份，或整個 SB 共用一次備份＋逐批驗證 | **每段（非每批）各自一次備份＋逐批獨立驗證＋每批各自一個交易，失敗只回滾該批**——與 §3.5「原則」段一致，備份存放 `D:\Python\Database_Backups\Stock_Prediction_System2\` |
| 4 | 三段是否可在同一輪 Gate B 內依序 binding confirmation，或每段各自一輪 | **同一 Gate B 內，三段各自 binding confirmation，依序（段 1→2→3）執行；每段完成並經審查方複核後才進下一段**；段 2 額外增設「既有 3 檔基線比對通過」為擴大到 458 檔前的關卡（§3.5、DoD #3a） |

Plan-Before-Code：本提案核准前，不修改 `src/`、`database/`，不對真實庫
執行任何寫入。§3.2／§3.3 的唯讀量測（已完成，見上）以及 §9 的四項裁決
（PO 2026-09-10）皆已確定，**本提案重送版待 PO 核准後即可依序進入
段 1（`stock_prices` 回補）**。
