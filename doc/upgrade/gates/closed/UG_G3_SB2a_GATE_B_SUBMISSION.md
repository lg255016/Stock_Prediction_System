# UG-G3-SB2a Gate B 送審——458 檔（＋NVDA）歷史資料回補，三段全部完成

> **狀態**：**Gate B 已核准結案（2026-09-11，PO 核准）**。
> **對應 Gate A 提案**：`doc/upgrade/gates/closed/UG_G3_SB2a_GATE_A_PROPOSAL.md`（重送版，commit `f668503`）。
> **閘門**：`PROJECT_STATUS.md` §0.5 #20（每日 ETL 執行閘門）**已隨本 Gate B 核准解除**（解除 ≠ 執行，第一次執行需另一輪 binding confirmation，見 §5 十項觀察清單）。

---

## 1. 完整 Commit 序列

依時間序，每項附一句話與本 SB 產出的證據檔／備份檔路徑。

| # | Commit | 內容 | 證據／備份 |
|---|--------|------|-----------|
| 0 | `1126fe5` | **前置條件**：CHAL-010 修復——`upsert_ml_features()` 全欄覆寫會清空既有 Triple-Barrier 標籤，改為 `ON CONFLICT DO UPDATE SET` 排除標籤兩欄。經 `sps_project_reviewer` 獨立複核通過（PO 2026-09-10） | 拋棄式 Postgres 容器種列/回讀驗證（已拆除）；`postgres`@`localhost:5432` 僅唯讀核對（3,713／3,529／184，未寫入） |
| 1 | `f668503` | Gate A 提案重送版——七點訂正＋PO 複核後八點訂正 | — |
| 2 | `ce2efcc` | 方案 B 紅色測試——TWSE 逐股路徑改走 `candidate_prices` 複製（Gate A 提案 §6 五項紅色測試清單） | — |
| 3 | `138bfc8` | 方案 B 實作——`main_etl_pipeline.py` 逐股路徑統一，`run_twse_pipeline` 移除，四條件皆落實 | — |
| 4 | `961b69f` | 段 1 回補腳本＋單元測試（`ug_g3_sb2a_backfill_stock_prices.py`） | — |
| 5 | `5318f16` | **段 1 真實庫寫入**：`stock_prices` 441,922 列新增、445,635 列總數、458 檔皆補齊 | PRE `..._PRE_g3_sb2a_stock_prices_20260910_231049.dump`；POST `..._POST_g3_sb2a_stock_prices_20260910_231920.dump`；`UG_G3_SB2a_stage1_real_db_write.json` |
| 6 | `debeb0d` | 段 2 前置三處訂正（PO 複核追加）：缺口回補腳本補寫入後核對、DEC-032 停止語意測試、基線比對腳本加 `--allow-diff-after`／`--allow-diff-stocks`；**RISK-027 登記於本 commit** | — |
| 7 | `e37455d` | 缺口回補腳本加 `--dates`／`--markets` 重試參數（因應 TPEX SSL 間歇性失敗需分批重試） | — |
| 8 | `c54246c` | 基線比對**方法**改版——`compare_columns()` 區分「孤兒列」與「新鍵」，修正段 1 先於段 2 執行時的比對語意（此 commit 修的是比對方法本身，**不是** RISK-027；RISK-027 本身尚未修復，見 §4 揭露清單第 1 項） | — |
| 9 | `2ee8141` | **段 2 前置真實庫寫入**：候選池 8 天全市場缺口回補（`candidate_prices` 1,825,814→1,841,594）；`stock_prices` 段 1 重跑補齊對應 8 天（445,635→449,263）；**RISK-028 登記於本 commit** | PRE `..._PRE_g3_sb2a_cp_gap_20260911_010029.dump`；POST `..._POST_g3_sb2a_cp_gap_20260911_080543.dump`（同時作為 stock_prices 重跑的 PRE）；POST `..._POST_g3_sb2a_stock_prices_rerun_20260911_080855.dump`；`UG_G3_SB2a_stage2_gap_and_baseline.json` |
| 10 | `679e26e` | *（與本 SB 無關的插曲）* 開發環境 `docker-compose.yml` 加 `restart:unless-stopped` 與 CPU/記憶體上限——當日主機發生兩次硬體瞬斷電＋一次顯示卡驅動 BSOD，診斷過程中順帶處理；不影響任何真實資料，列於此僅為完整揭露 commit 序列 | — |
| 11 | `49aef94` | 段 2（458＋NVDA 檔特徵回補）腳本＋測試；審查員 dry-run 期間發現並要求併入兩處修正（`_values_differ` 的 `decimal.Decimal` 型別、唯讀預覽的常數過期守衛＋記憶體不變式） | — |
| 12 | `e14212b` | **段 2 真實庫寫入**：`daily_ml_features` 10 批全 OK，新增 445,550 列、更新 3,713 列，總列數 449,263 | PRE `..._PRE_g3_sb2a_features_20260911_103413.dump`；POST `..._POST_g3_sb2a_features_20260911_110211.dump`；`UG_G3_SB2a_stage2_features_write.json` |
| 13 | `837a0c0` | 段 3（458＋NVDA 檔 Triple-Barrier 標籤重算）腳本＋測試；審查員第二輪要求收緊（既有 3 檔差異改「相等」非「子集」）＋補標籤分布對帳 | — |
| 14 | `0f6a428` | **段 3 真實庫寫入**：`daily_ml_features` 10 批全 OK，標籤計數 410,443／38,820；`FEATURE_REGISTRY.md` #6／#29 同步 | PRE `..._PRE_g3_sb2a_labels_20260911_140624.dump`；POST `..._POST_g3_sb2a_labels_20260911_141614.dump`；`UG_G3_SB2a_stage3_labels_write.json` |

所有備份檔位於 `D:\Python\Database_Backups\Stock_Prediction_System2\`。**五次真實庫寫入**（段 1、候選池缺口回補、段 1 重跑、段 2、段 3）皆完整執行 RISK-013 三項協議（binding confirmation → PRE 備份＋拋棄式容器還原驗證 → 執行＋寫入後獨立核對 → POST 備份），無一次省略或簡化。

---

## 2. Definition of Done 逐項對號

| # | 項目 | 狀態 | 對應 |
|---|------|------|------|
| 0 | CHAL-010 修復（前置條件） | ✅ **已完成** | `1126fe5`，`sps_project_reviewer` 複核通過（PO 2026-09-10） |
| 1 | §3.1 方案 B 已實作（`main_etl_pipeline.py` 逐股路徑統一，四條件皆落實） | ✅ **已完成** | `ce2efcc`（紅）→`138bfc8`（實作）。四條件：(a) 複製邏輯逐欄一致 (b) `source` 值域收斂為 `twse_mi_index`／`tpex_daily_quotes`，NVDA 不受影響 (c) `run_twse_pipeline` 移除、零殘留引用（`grep` 靜態掃描通過） (d) migration 009 CHECK 約束未收窄 |
| 2 | §3.2 既有 3 檔 `stock_prices` 重疊區全量比對已完成，處理規則已定案並執行 | ✅ **已完成** | 提案 §3.2 全量比對結果：2330／2382 各 985 列零差異；6488 960 列相同＋25 列 `volume` 差＋1 列價格差。處理規則「只補缺席日期、不覆寫既有列」已落實於段 1 腳本並經 `5318f16` 真實庫寫入驗證（既有列 md5 逐次核對未變）。**與 RISK-027、`c54246c` 無關**（RISK-027 是段 2 特徵計算的交易日曆缺陷，非 `stock_prices` 重疊區比對範疇） |
| 3 | §3.3 458 檔範圍 SQL NULL 80 列成因分類已完成 | ✅ **已完成** | 段 3 唯讀預覽逐列印出 DEC-035 對照（`837a0c0`），4562／4583 兩列異常已於段 2 前置人工抽審（`2ee8141` 證據） |
| 3a | §3.5 段 2 基線比對：既有 3 檔重跑段 2 特徵計算，與現行 `daily_ml_features` 逐欄比對無非預期差異 | ✅ **已完成** | 本比對過程中**發現 RISK-027**（初版比對只用台股 3 檔重算、日曆缺美股獨有交易日，比出 36 個假差異；加回 NVDA 使日曆正確後重跑歸零）；`c54246c`（比對方法改版：孤兒列／新鍵拆分，處理段 1 先於段 2 執行的鍵不對齊語意）後再重跑：25 欄比對、20 新鍵恰等於預期集合、0 孤兒、0 非預期差異（`2ee8141` 證據），段 2 因此獲准擴大到 458 檔。**RISK-027 根因（`feature_aggregator.py` 日曆邏輯本身）未修復**，段 2/3 現況帶著此已知限制（見 §4 揭露清單第 1 項） |
| 4 | `stock_prices` 458 檔皆有資料（段 1） | ✅ **已完成** | `5318f16`（458 檔皆補齊，逐股列數核對通過） |
| 5 | `daily_ml_features` 458 檔皆有特徵（段 2） | ✅ **已完成** | `e14212b`（449,263 列，25 特徵欄；459 檔逐股列數與 `stock_prices` 全對） |
| 6 | `daily_ml_features` 458 檔皆有 Triple-Barrier 標籤（段 3） | ✅ **已完成** | `0f6a428`（449,263 列，標籤計數 410,443／38,820；一致性 0 違規） |
| 7 | `PROJECT_STATUS.md` §0.5 #20 閘門解除 | ⏳ **待核准當下生效** | 本文件核准後才執行；**不在本次 commit 範圍內先行解除** |

---

## 3. 驗證環境與結果

**執行環境**：容器（`stock_prediction_system2_devcontainer-app-1`），Python 3.14.6，HEAD `0f6a428`。

**依賴狀態**（9 項，`python -c "import importlib.util as u; [print(f'{m:20}', 'PRESENT' if u.find_spec(m) else 'ABSENT') for m in ['numpy','pandas','sklearn','lightgbm','xgboost','psycopg2','jieba','snownlp','tenacity']]"`）：全部 `PRESENT`，無 fallback／mock 路徑，ML／DB 相關測試皆走真實實作。

**全套測試**（`python -m unittest discover -s tests -p "test_*.py"`）：

```
Ran 692 tests in 39.387s
OK
```

**跨文件契約驗證**（`python scripts/verify/gate0_contract_check.py`）：`Part B: 13/13 PASS`，`echo $?` → `0`。

**格式／秘密掃描**：本 Gate B 涉及的 15 個 commit，每一個在建立當下皆經 `.githooks/pre-commit`（GOV-04）機械檢查（跨文件契約驗證、`numstat` 與 `-w` 一致性、GOV-13 秘密偵測——檔名與內容雙層）攔截，四項檢查逐次皆為 PASS 才允許 commit 建立；非事後回溯核對，是建立當下即時擋下的機制。

**known-FAIL 案例**（各段測試檔，逐一為真的會失敗的案例，非通過的外觀）：

| 段 | 測試檔 | 代表性 known-FAIL 案例 |
|---|--------|------------------------|
| 方案 B 路由 | `tests/test_ug_g3_sb2a_planb_twse_route.py` | `source` 值域收斂與批次 outcome 歸因（Gate A 提案 §6 五項紅色測試） |
| 段 1（`stock_prices` 回補） | `tests/test_sb2a_stock_prices_backfill.py` | `test_raises_and_rolls_back_when_total_count_mismatch`、`test_2330_shape_would_fail_under_old_formula_but_passes_under_new_one` |
| 缺口回補 | `tests/test_sb2a_backfill_candidate_prices_gap.py` | `test_stopping_is_load_bearing`（`break`→`continue` 變異，證明 DEC-032 停止語意是承重的） |
| 段 2 基線比對 | `tests/test_sb2a_stage2_baseline_comparison.py` | `test_decimal_handling_is_load_bearing`、`test_extra_left_only_key_outside_expected_is_detected` |
| 段 2 特徵回補 | `tests/test_sb2a_backfill_features.py` | `test_guard_removed_is_load_bearing`（唯讀預覽零寫入 guard） |
| 段 3 標籤重算 | `tests/test_sb2a_write_triple_barrier_labels.py` | `test_known_fail_shifting_gap_by_one_position_changes_impact_set`（合成缺口）、`test_known_fail_strict_subset_without_equality_now_fails`（相等斷言收緊）、`test_guard_removed_is_load_bearing` |

---

## 4. 揭露清單

以下事項皆與本 Gate B 相關但**不阻擋核准**，逐項標明去處：

1. **RISK-027**（`feature_aggregator.py` 交易日曆跨市場聯集，台股假期文章被 roll-forward 到不存在的交易日造成流失）——`OBSERVED`，`UG-G3-SB2a` Gate B 後獨立小案修復，不擋本 Gate B。段 2/3 現況**照現行語意寫**（帶著此已知限制）。
2. **RISK-028**（`market_report_fetcher` 對 TPEX 端間歇性 `SSL: CERTIFICATE_VERIFY_FAILED`）——`OBSERVED`。已確認的事實：Python 3.14 `ssl.create_default_context()` 預設對 tpex.org.tw 憑證鏈（缺 Subject Key Identifier）**3/3 必定失敗**（嚴格模式）；`requests`／urllib3 2.7 走非嚴格模式，多數請求能通過。**間歇性失敗的實際觸發條件尚未定位**——不得寫成「已定位」。另案診斷，不綁 SB，**禁止關閉憑證驗證繞過**。本次受影響的 8 天缺口已全數補齊，未造成資料缺口。
3. **RISK-025 分布**（Triple-Barrier 類別不平衡，DEC-018 揭露條款）——段 3 實測：337/459 檔 Timeout 佔比 <5%；`ambiguous_dual_barrier` 8.1%（36,388/449,263，偏高）；`-1:+1`≈226,956:162,288≈1.4:1（明顯偏空）。**歸 `UG-G3-SB3` D3 實驗必答項**，本段只如實記錄，不調整 barrier 寬度或標籤邏輯。
4. **`sentiment_mean` NULL 佔比 0.998**（RISK-015 延續）——`SUCCESS_EMPTY` 448,490／`SUCCESS` 773。多數股票多數交易日無社群文章討論，情緒特徵結構性稀疏，是資料現況而非本次寫入造成的缺陷。
5. **`TwseScraper` 模組零生產呼叫者但仍有測試**——方案 B 實作後，`main_etl_pipeline.py` 不再匯入／呼叫 `src/extractors/twse_scraper.py`（模組本身保留，供未來單檔歷史回補腳本直接匯入），但 `tests/test_extractor_retry_discipline.py` 等既有測試仍測該模組的重試邏輯。**模組去留（保留供未來使用／移除）由 PO 另案裁決**，本 Gate B 不預先決定。
6. **`UG-G3-SB2` 每日尾端掛點（`run_triple_barrier_tail_recompute()`）仍未啟用**——函式已接線但未被 `run_all_daily_tasks()` 呼叫，首次啟用需比照本 SB 的 RISK-013 協議另做 binding confirmation。
7. **三次意外重開機／Docker Desktop 背景重啟事件與資料一致性核對**——2026-09-11 當日主機發生兩次硬體瞬斷電（`BugcheckCode=0`，非藍屏）與一次顯示卡驅動 BSOD（`0x119`），另有 Docker Desktop 背景重啟兩次；**每次事件後皆對真實庫執行獨立核對**（總列數、標籤計數、關鍵表 md5），全部與事件前一致，資料未受影響。診斷過程中順帶完成 Docker 資源上限設定（`679e26e`，與 fluora 專案共用主機協議）。
8. **段 2 唯讀預覽曾誤查庫內舊值**（已修）——`compute_risk025_table()`／`print_null_price_label_context()`／段 3 同類函式初版誤吃 DB 連線查詢寫入前現況，導致唯讀預覽階段（`--write` 前）看到的是舊值而非即將寫入的計算結果；真實 dry-run 期間自行發現並改為吃記憶體中剛算出的 DataFrame，修正已併入對應 commit。
9. **缺口回補 TPEX 三輪嘗試**——8 天候選池缺口回補期間，TPEX 端因 RISK-028 失敗 2 次後於第 3 次成功（08-25）、失敗 1 次後重試成功（08-26），最終 8 天全數補齊，過程完整記錄於 `UG_G3_SB2a_stage2_gap_and_baseline.json`。
10. **`compute_expected_new_keys()`／`compute_expected_relabel_impact()` 的隱含假設**——段 2 基線比對腳本的 `compute_expected_new_keys()` 用「股票 × 缺口日」笛卡兒積算預期新鍵，隱含「每檔在每個缺口日都有列」的假設，對零成交日無列的股票會誤報，下次動該腳本時一併改為「直接比對 `stock_prices` 與 `daily_ml_features` 的鍵集合」。段 3 的 `compute_expected_relabel_impact()` 沒有笛卡兒積假設問題（拿實際存在的列重算兩次比較），但有**另一個隱含假設**：`SEGMENT1_RERUN_CUTOFF = "2026-09-11"` 把「當日 `created_at`」等同「段 1 今日重跑插入的列」——這在本次執行是一次性成立的條件（因為段 1 重跑確實只發生在 2026-09-11 這一天），並非通用機制；若未來同一腳本被重複使用於不同時間點的重跑，這個寫死的日期邊界需要重新設計（例如改吃參數或改用其他方式標記「本次重跑批次」）。

---

## 5. 閘門 §0.5 #20 解除條件檢核

**解除條件**（`PROJECT_STATUS.md` §0.5 #20 表格本文，逐字）：「`UG-G3-SB2a` Gate B 通過（價格基準政策定案）」。

**解除條件的展開說明**（Gate A 提案 §3.6 原文，非 §0.5 #20 本身文字，屬提案對該條件的詮釋）：本 SB Gate B 通過——即 §3.1 基準政策**已實作**（方案 B 四條件皆落實），458 檔資料回補三段皆完成且驗證通過。

| 條件 | 檢核 |
|------|------|
| 方案 B 已實作 | ✅ `138bfc8`，四條件逐一對應：(a) `ce2efcc` 紅色測試 (b) `source` 值域收斂測試通過 (c) `grep -rn "run_twse_pipeline"` 靜態掃描零殘留 (d) migration 009 CHECK 約束核對未收窄 |
| 段 1（`stock_prices` 458 檔） | ✅ `5318f16` |
| 段 2（`daily_ml_features` 458 檔特徵） | ✅ `e14212b` |
| 段 3（`daily_ml_features` 458 檔標籤） | ✅ `0f6a428` |

**四條件皆滿足，本 Gate B 核准後方可解除閘門。**

**解除後第一次執行（`run_all_daily_tasks()`）的觀察清單**（Gate A 提案 §3.6 原文帶入，非本 SB 執行範圍，供解除閘門時的另一輪 binding confirmation 使用）：

1. `entity_mapping` 路由指向的 161 篇孤兒文章（`UG-G3-SB2` CHAL-009 登記）是否正確歸屬到 2059／2454／3008／8069 四檔的 `direct_count`。
2. 4 檔新追蹤股票首次寫入 `stock_prices` 的來源是否符合方案 B 定案政策（應全數為 `twse_mi_index`／`tpex_daily_quotes`，零 `yfinance_auto_adjusted`）。
3. 滾動特徵在新股票暖機期（<20 個交易日歷史）的 NULL／預設值行為是否符合既有 W／F／U 成因分類，不得新增未分類情形。
4. 批次階段（`UG-G2-SB7`）處理 458 檔規模時的請求數與耗時，與現行全市場批次規模（約 2,024 檔）既有量測基準比較，確認未觸發任何來源的 rate limit。
5. `stock_prices` 中 2330／2382 於 2026-09-01／09-02 兩日（§3.2 發現的批次覆蓋缺口）方案 B 實作後是否已能正常從 `candidate_prices` 取得對應列。
6. **2026-08-24～09-02 全市場 8 天缺口**（本 Gate B 已回補）：確認方案 B 實作後的每日增量不會再產生同類窗口——批次階段與逐股階段的銜接是否有機制保證「批次一旦中斷或延遲啟動，缺口會被自動偵測並回補」，或僅能依賴人工唯讀查證發現（如本次）。

**本 Gate B 三段執行經驗直接推出的四項增補**（PO 2026-09-11 複核追加）：

7. **CHAL-010 真實資料迴歸**：第一次每日執行後，`target_triple_barrier`／`label_reason` 計數應仍為 410,443／38,820 加上尾端掛點的改動（掛點啟用前為零改動）；差一列就是 CHAL-010 回歸。
8. **RISK-027 的可預期流失**：第一次執行若落在台股假期前後，台股標的的 `article_count` 會少算——那是已登記的既有限制（§4 揭露清單第 1 項），不得誤讀成爬蟲失敗。
9. **RISK-028**：`etl_run_log` 逐市場 outcome 必看；TPEX `FETCH_FAILED` 要走 `--dates`／`--markets` 重試流程，不得靜默接受缺日。
10. **缺口偵測常設化**：執行後跑一次「`candidate_prices` 逐日全市場列數」查詢（就是這次抓到 8 天缺口的那條），連同 `stock_prices` 宇宙逐日覆蓋一起列印——缺口回補的教訓不是「補了」，是「沒有機制會自己發現」。

**⚠ 解除 ≠ 執行**：本 Gate B 核准只解除「不得執行 `run_all_daily_tasks()`／`scheduler.py`」的閘門，**不等於授權立即執行**。第一次真實執行仍需另一輪 binding confirmation（比照本 SB 各段協議），屆時上述十項觀察清單（原提案六項＋本 Gate B 執行經驗增補四項）為必答項。

---

## 6. 未驗證清單（有名字有去處）

| 項目 | 去處 |
|------|------|
| Triple-Barrier `rolling` vs `expanding` 模式選擇 | `UG-G3-SB3` D3 實驗 |
| Purged Walk-Forward embargo>0 滲漏檢驗 | `UG-G3-SB3` |
| 標籤分布不平衡（RISK-025）對模型預測力的實際影響 | `UG-G3-SB3` D3 實驗 |
| RISK-027 修復後，段 2／段 3 是否需要重跑 | 待 RISK-027 獨立小案修復後另行評估，目前段 2/3 產出**帶著此已知限制**，已明確揭露（§4 第 1 項） |
| `UG-G2-SB9` 一次性回補停在 08-21、`UG-G2-SB7` 每日批次 09-03 才開始，中間 8 天缺口的根本成因 | 尚未對 `UG-G2-SB9` 自身證據確認，目前為 `INFERENCE`（見 `UG_G3_SB2a_stage2_gap_and_baseline.json`） |
| `TwseScraper` 模組去留（保留供未來單檔回補使用／移除） | PO 另案裁決（見 §4 揭露清單第 5 項） |

---

## 7. 證據標籤

- 本文件第 1、2、5 節列出的所有 commit hash、檔案路徑、真實庫數字，凡標註「✅ 已完成」者，其底層驗證動作（binding confirmation 執行、獨立重查 SQL、拋棄式容器還原）皆為 **`VERIFIED THIS SESSION`**，可重跑指令與原始輸出見各段對應的 `doc/upgrade/gates/evidence/*.json`。
- 審查員（`sps_project_reviewer`）在**五次真實庫寫入**（段 1、候選池缺口回補、段 1 重跑、段 2、段 3）**每一次前後**都各自獨立對真實庫執行過複核（唯讀重查、全表重算比對、dump 還原、含自行計算 md5），不只段 2、段 3——這些數字在本文件中標註為 **`REPORTED, NOT INDEPENDENTLY VERIFIED`**（回報者：審查方，PM 未重新驗證審查方自己的計算過程，僅核對其回報的最終數字與 PM 自己算出的數字一致）。
- 第 4 節「揭露清單」中標記 `OBSERVED` 的風險項，其發現脈絡與量測數字引自 `REMAINING_RISKS.md` 既有登記，屬 **`PREVIOUSLY VERIFIED`**（記錄位置：`REMAINING_RISKS.md` 對應風險列）。

---

## 8. 核准後動作（本文件送審階段不執行，Gate B 核准後才做）

依 `CLAUDE.md` §16.3、`gate-submit` skill 產出 8：

1. `git mv` 本文件（`UG_G3_SB2a_GATE_B_SUBMISSION.md`）與對應 Gate A 提案（`UG_G3_SB2a_GATE_A_PROPOSAL.md`）至 `doc/upgrade/gates/closed/`。
2. 確認 `git diff --cached --name-status` 顯示為 `R100`（純 rename），無夾帶內容變更。
3. 檢查搬移後的檔案是否出現在 `scripts/verify/gate0_contract_check.py` 的 `DOC_PATHS`，若有則同一 commit 內更新。
4. 同步 `doc/README.md` 的逐份文件表。
5. `PROJECT_STATUS.md` §0.5 #20 標記解除，附核准日期與本 Gate B commit hash。
6. `doc/evidence/DECISIONS.md`／`TRACEABILITY.md`：若本 Gate B 產生新 ADR（目前未有），依 `evidence-sync` skill 傳播清單同步；若無新 ADR，本項略過。

**本 Gate B 已經 `sps_project_reviewer` 複核通過、PO 核准結案（2026-09-11）。§8 核准後動作已執行完畢，本文件移入 `closed/`。**
