# `PRE-G3-04`（D5）Gate B 送審

- 日期：2026-09-08
- 涵蓋：U 分支落地（紅→綠）+ `PROJECT_STATUS.md` §0.5 補登記 + `daily_ml_features` 全量重算
- 性質：**送審文件**。依 PO 糾正過的正確順序執行——**送審 → 複查 → PO 核准 → 結案 commit**。
  本文件本身尚未移入 `closed/`；核准前 `gates/` 根層維持本檔與 Gate A 提案並存。

---

## 0. 一句話

**`sentiment_mean` 空日填 `0.5` 是編出來的，這裡把它改回 `NULL`；
全量重算後，兩條獨立路徑（覆蓋率量測與本次重算）對同一批資料算出完全相同的答案——
這是 3,713 列面板品質目前最硬的一條證據。**

---

## 1. 完整 commit 序列（依時間順序，皆為真實 hash）

| commit | 內容 |
|---|---|
| `fd0a889` | D5 Gate A 提案（純規劃，未動任何程式碼）——先前已核准 |
| `0c53764` | **紅**：反轉/新增 5 項斷言（T1 改寫、連帶修正、T2/T3/T4 新增），容器內實測 `FAILED (failures=5)`，逐項核對 FAIL 數值與舊版無條件 `fillna(0.5)` 邏輯吻合 |
| `6ecdb50` | **綠**：`feature_aggregator.py` 三個異動點落地（移除 `sentiment_mean` 早期 fillna；3d_ma/5d_ma 免動；`lag_1`/`lag_2` 加 `cumcount()` 真暖機期判定）+ `FEATURE_REGISTRY.md` §5A.2/§5A.3 契約同步 + 連帶修正 `test_thematic_feature_spillover.py` 一項必然的收斂測試 |
| `246b430` | `PROJECT_STATUS.md` §0.5 補登記 #18：`model_trainer.py:161-169` 會靜默抹平 D5 建立的 U 語意，去處 `UG-G3-SB2` |
| `87bd40e` | 全量重算預期先寫死（觸庫前 commit），含指紋方法自我更正的完整記錄 |
| `4aa86cc` | 全量重算結果，R1~R6 全數相符 |

---

## 2. 三個精確異動點（設計摘要，`6ecdb50` 全文為權威）

| 位置 | 變更 |
|---|---|
| `sentiment_mean` | 移除早期 `.fillna(0.5)`。空日（`article_count==0`）是成因 U（數學未定義），非成因 F——資料確實拿到了，只是那天沒有討論 |
| `sentiment_3d_ma`／`sentiment_5d_ma` | **無程式碼變更**（已實測驗證）：`rolling(min_periods=1).mean()` 對 `NaN` 是 nanmean 語意，上游不再早期填補後行為自動正確 |
| `sentiment_lag_1`／`sentiment_lag_2` | 新增 `groupby('stock_id').cumcount()` 判定真暖機期（`cumcount() < N`，仍填 0.5）vs U 傳播（保持 `NULL`）——`shift()` 的 `NaN` 本身無法分辨這兩種成因 |

契約同步：`FEATURE_REGISTRY.md` §5A.2 補 U 分支判定流程（`DEC-030` 已宣告、判定流程從未寫入的部分）；§5A.3 對照表五欄加註 U 子條件。皆為 Gate A 提案 §6 已核准草稿的落地，非新設計。

---

## 3. 全量重算：R1~R6 結果（`4aa86cc` 全文為權威）

**方法**：完全比照生產路徑 `main_etl_pipeline.py:544-557`
（`fetch_all_for_features` → `generate_daily_features` → `generate_target_labels` → `upsert_ml_features`），
寫回真實庫 `postgres@localhost:5432`。

| # | 結果 |
|---|---|
| R1（列數） | 3,713（2330=987, 2382=987, 6488=985, NVDA=754），與 `stock_prices` 逐檔分佈完全相符，取代舊 137 列而非疊加 |
| R2（PO 指定的零成本交叉核對） | `sentiment_mean IS NOT NULL` 逐檔 = 2330=126, 2382=33, 6488=12, NVDA=91 —— **與 `PRE-G3-02` 量測的覆蓋天數逐檔完全相符**。兩條獨立路徑（量測與重算）對同一批未變動資料算出一致答案 |
| R3 | `source_status` 僅 `SUCCESS`/`SUCCESS_EMPTY` 兩態（呼叫路徑未傳 `failed_source_keys`，與量測同一限制），`SUCCESS` 列數與 R2 逐檔相同 |
| R4（抽樣） | 舊 137 列中 4 檔各 1 筆原 `SUCCESS_EMPTY` 者：2 筆（2382/6488）維持 `SUCCESS_EMPTY`，`sentiment_mean` 由 0.5 變 `NULL`，直接證實 D5 語意已取代舊值；另 2 筆（2330/NVDA）因全量回補後文章覆蓋擴大而轉為 `SUCCESS`（真實計算值）——此為回補範圍擴大的預期結果，抽樣方法（取重算前 137 列中的 `SUCCESS_EMPTY` 首列）本就不保證重算後仍為空日，非缺陷 |
| R5（NULL 佔比，U 語意上線後第一張誠實快照） | **2330 87.2%（861/987）、2382 96.7%（954/987）、6488 98.8%（973/985）、NVDA 87.9%（663/754）**——它不好看，它誠實，照登不美化 |
| R6 | 其餘十二張表列數重算前後逐表相同 |

**RISK-013 三項**：綁定確認（`postgres`/`5432`）；新鮮 `pg_dump` 落
`D:\Python\Database_Backups\Stock_Prediction_System2\stock_prediction_system2_PRE_g3_04_recalc_20260908_030605.dump`；
拋棄式容器 `g3_04_recalc_restore_check` 實測還原（12 表逐表列數 + `daily_ml_features` 指紋皆與寫入前相符），驗證後已拆除。

**指紋方法的自我更正**（記於 `87bd40e`，不隱藏）：第一次確認舊指紋誤用 Python 側
`hashlib.md5(repr(rows))`，得到與既有記錄不同的值——非資料變動，是自建方法與既有記錄的
SQL 側 `concat_ws`/`md5` 方法不同。改用既有方法後與歷次記錄完全相符（`4fc208b9...`）。
本 SB 第二次同型自我更正（第一次見 `PRE_G3_03_import_result.json` 手寫欄位清單事件），
本次已將完整 SQL 方法寫入 `PRE_G3_04_recalc_expectations.json` 供下次直接重跑，
避免第三次。

**新基準**（供下一次 `daily_ml_features` 操作的指紋比對）：
`ec91c76d44bae74e83c52a3edf07b629` / 3,713 列。

---

## 4. `b1_pilot_tmpdb` 拆除紀錄

`b1_pilot_tmpdb` 為 `PRE-G3-01` B1 試點匯入完成當輪的**明確裁決保留**：
保留至第 2 段（特徵重算）驗收通過為止，作為匯入的回滾參照，非未拆除的遺留。

**R1~R6 通過 = 保留條件到期**。依原裁決（「說一聲即可」）於本輪執行拆除：

```
docker rm -f -v b1_pilot_tmpdb
```

容器與其資料卷（匿名卷 `8158fa4c15fc...`）皆已移除，已確認 `docker ps -a` 與
`docker volume ls` 皆不再列出。匯入的回滾能力現由 §7A.1 位置的 `pg_dump` 承接。

---

## 5. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 / 依據 |
|---|---|---|
| 5 項紅斷言 FAIL 且與舊邏輯數值吻合 | `VERIFIED THIS SESSION`（撰寫當時） | `python -m unittest tests.test_source_failed_nulls -v`（`0c53764` 前） |
| 三異動點落地後全綠、`sentiment_3d_ma`/`5d_ma` 無需改動 | `VERIFIED THIS SESSION` | `python -m unittest discover -s tests -p "test_*.py"`；`6ecdb50` 全文 |
| `rolling(min_periods=1).mean()` 為 nanmean 語意 | `VERIFIED THIS SESSION`（Gate A 提案撰寫當時） | `PRE_G3_04_D5_GATE_A_PROPOSAL.md` §5.2 實測片段 |
| R1~R6 全數數字 | `VERIFIED THIS SESSION` | `doc/upgrade/gates/evidence/PRE_G3_04_recalc_result.json`；重算腳本未進版控（慣例），邏輯即 `DBWriter.fetch_all_for_features` + `FeatureAggregator.generate_daily_features/generate_target_labels` + `upsert_ml_features` |
| RISK-013 還原驗證（12 表 + 指紋相符） | `VERIFIED THIS SESSION` | 拋棄式容器已拆除，指紋方法見 `PRE_G3_04_recalc_expectations.json` |
| `model_trainer.py:161-169` 無條件 `fillna` 存在 | `VERIFIED THIS SESSION`（複查方核實） | `sed -n '161,169p' src/ml/model_trainer.py` |

---

## 6. Known-FAIL 對照（`CLAUDE.md` §9A.2）

| 檢查 | known-FAIL 案例 | 實測結果 | 復原確認 |
|---|---|---|---|
| T1（`test_success_empty_keeps_the_neutral_fill`） | 未改實作前執行，斷言方向已反轉 | `FAILED`，實際值 `sentiment_mean` 全為 `0.5`（舊行為），與新斷言 `isna()` 不符 | 實作完成後轉綠，`HEAD` 未受影響 |
| T2（`test_lag1_true_warmup_vs_u_propagation`） | 同上 | `FAILED`：`lag_1[第3列]` 應 `NULL`，舊邏輯給出 `0.5` | 同上 |
| T3（`test_3d_ma_partial_window_uses_nanmean_not_polluted_average`） | 同上 | `FAILED`：實際值 `0.6 = mean(0.8,0.5,0.5)`，與預期 `0.8` 不符，數值吻合舊邏輯 | 同上 |
| T4（`test_failed_clears_article_count_but_u_does_not`） | 同上 | `FAILED`：U 分支列 `sentiment_mean` 未為 `NULL`（舊邏輯仍填 0.5） | 同上 |
| R1~R6 重算判準 | 若指紋比對用了錯誤方法（本輪已實際發生一次） | `40ed8548...` ≠ 既有記錄 `4fc208b9...`，觸發停下查明，而非逕行採信 | 換回正確方法後確認一致，未回滾（無寫入發生） |

---

## 7. 未驗證清單（有名字、有去處）

| # | 項目 | 現況 | 去處 |
|---|---|---|---|
| 1 | **`model_trainer.py:161-169` 會靜默抹平 D5 建立的 U 語意** | 已登記 `PROJECT_STATUS.md` §0.5 #18（`246b430`） | `UG-G3-SB2`（訓練排除邏輯，讀 `daily_ml_features` 的消費端） |
| 2 | **R4 抽樣限制**：4 檔各僅 1 筆抽樣，且抽樣方法不保證重算後仍為 `SUCCESS_EMPTY`（2/4 因覆蓋擴大轉 `SUCCESS`） | 已於 `4aa86cc` 與本檔 §3 明確揭露，非隱藏 | 不需要額外去處——僅 2 筆有效對照已足以證實 D5 語意生效；若需要更強的全量核對，屬 Gate 3 資料品質審視範圍 |
| 3 | **D3 預測力對照未跑**（有／無情緒特徵的 walk-forward 對照） | `PRE-G3-02` D3 已裁決錨定機制，尚未執行；本次全量重算是其前置條件之一，現已具備 | Gate 3 第一個實驗 |
| 4 | **§5.2 的 U/F 不對稱**（U 分支不強制清空 `3d_ma`/`5d_ma`，F 分支強制清空） | Gate A 已核准此不對稱，非未決 | 已落地，僅存於此列作追溯 |
| 5 | **`min_train_size` 三件事未解**（`PROJECT_STATUS.md` §0.5 #16） | 與本次無關，先前已登記 | Gate 3 啟動前 |

---

## 8. 裁決索引

| 裁決 | 裁決者 | commit/位置 |
|---|---|---|
| D5 Gate A 三點確認（U/F 不對稱、`cumcount` 設計、全量覆寫授權） | PO 2026-09-07 | `fd0a889` §12 |
| D5 暫緩、先清三份 Gate B | PO 2026-09-08 | 本 session 訊息，已執行於 `f57cc8a`/`f91d125`/`b789cc8` |
| 三份 Gate B 追認核准 + 程序揭露補記 | PO 2026-09-08 | `a6891ff` |
| 紅→綠複查通過，重算授權（含零成本交叉核對加項） | 複查方／PO 2026-09-08 | 本輪訊息 |
| §0.5 #18 補登記要求 | 複查方 2026-09-08 | `246b430` |
| 重算複查通過（R1~R6 核可）；`b1_pilot_tmpdb` 拆除授權生效 | 複查方／PO 2026-09-08 | 本輪訊息，執行見本檔 §4 |

---

## 9. `DOC_PATHS` 檢查

已核對，本檔與 `PRE_G3_04_D5_GATE_A_PROPOSAL.md` 皆不在 `gate0_contract_check.py` 的
`DOC_PATHS` 清單內，日後移入 `closed/` 時無需同步。

---

## 10. 送審聲明

`PRE-G3-04`（D5）的紅→綠實作、契約同步、`PROJECT_STATUS.md` §0.5 補登記、
`daily_ml_features` 全量重算，以及 `b1_pilot_tmpdb` 拆除，皆已完成並如上列出完整證據。

**本文件為送審文件，尚未結案**。核准後才執行結案 commit：
`PRE_G3_04_D5_GATE_A_PROPOSAL.md` 與本檔一併移入 `closed/`，
`PROJECT_STATUS.md` §0.2 登記 `PRE-G3-04` 為 **CLOSED**（含真實 commit hash，非「本 commit」）。
