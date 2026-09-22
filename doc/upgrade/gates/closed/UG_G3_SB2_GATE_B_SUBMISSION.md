# `UG-G3-SB2`（Panel Dataset 構建）Gate B 送審

## 0. 一句話

三項子工作（PIT 面板讀取器、`entity_mapping` 路由補齊 457 筆真實庫寫入、每日尾端
重算掛點接線）皆已完成，52 項專屬測試 + 全套 559 項測試全綠；審查方複核期間
獨立抓出並修正六個實質缺陷（PIT 過濾邏輯、`label_end_date_tb` dtype、routing
腳本兩處空防護、證據檔字面密碼洩漏兩次），並發現一項推翻原提案宣稱的真實
副作用（路由補齊使追蹤宇宙由 4 檔變 8 檔）——已如實訂正、登記風險與閘門，
請 PO 核准結案。**面板本身目前只有 3 檔台股有真實資料**（458 檔回補是
`UG-G3-SB2a` 的範圍，尚未開始），詳見 §7。

## 1. 完整 commit 序列（依時間順序，皆為真實 hash）

| commit | 內容 |
|---|---|
| `2c34059` | Gate A 提案第一版——**PO 退回**：量體看錯維度（用最新單期 150 檔，未用 PIT 跨期聯集 458 檔），選項 C 撞已核准裁決（路由不得再拆） |
| `8c3e10d` | Gate A 重送——PIT 全期數字訂正（46 期、458 檔），新增 DEC-036 拆分 `UG-G3-SB2a`（458 檔資料回補），核准進入實作 |
| `3104894` | 紅色測試：13 項（`panel_dataset.py` 尚未存在），含提案三處小修正 |
| `a39e966` | 補三項紅色測試——**審查方發現**：冪等測試結構上不會失敗（純函式呼叫兩次必過），改走 `apply_tail_labels()`；H+1 邊界原本只斷言不證明，改由建構證明 |
| `2642b39` | 補多股票掛點測試 + dtype 陷阱測試（第 13 項），核准轉綠 |
| `c48917c` | 綠色實作：`panel_dataset.py`／`triple_barrier.py` 兩函式／`main_etl_pipeline.py` 掛點（未啟用）——**審查方發現兩個真實缺陷**：PIT 過濾只看該股票自身快照列（股票從後期快照缺席時不排除）；`label_end_date_tb` dtype 與 `trade_date` 不一致（餵 `WalkForwardSplitter` 會 `TypeError`） |
| `0e9b7c8` | 修正上述兩缺陷（改全域適用期判定＋`merge_asof`；`label_end_date_tb` 改直接 `groupby.shift` 並轉 `datetime64`），另修正 psycopg2 stub 覆蓋真實套件的測試盲點 + 重複快照列 raise |
| `dcac0fe` | `entity_mapping` 路由補齊腳本（唯讀預覽），紅綠合併一個 commit（**流程偏差，PO 裁定接受、不改寫歷史**，見 §7） |
| `36687a0` | 補記 `dcac0fe` 的先紅證據 + known-FAIL 彙整，修正流程偏差 |
| `d61549c` | 紅色測試：`execute_write_and_verify()` 尚不存在（**真正兩階段紅綠，修正上次偏差**） |
| `a2d7641` | 綠色實作：修正兩個真實缺陷——**審查方在拋棄式庫端到端發現**：0 筆新增時誤判失敗（dtype 不一致的 `.equals()` 誤判）；讀回核對缺總列數檢查 |
| `34bcc5f` | `entity_mapping` 路由補齊 457 筆真實庫寫入完成——**惰性驗證發現追蹤宇宙由 4 變 8 檔**，推翻提案 §5「完全惰性」宣稱，PO 裁決接受不回滾；**本 commit 證據 JSON 內含字面密碼（第三次同型漏洞）** |
| `655f740` | **審查方發現**：`34bcc5f` 證據 JSON 字面密碼，修正為佔位符 |
| `29aacc6` | 紅色測試：每日尾端重算掛點呼叫順序（`run_all_daily_tasks()` 尚未呼叫） |
| `ae785bc` | 綠色實作：接線一行（`self.run_triple_barrier_tail_recompute()`），三項斷言（順序／WARNING／無真實連線）通過 |
| `7dd382c` | **審查方發現**：`655f740` 引述外洩內容時再次寫出字面值（第四次同型漏洞），修正 |
| `85e68dc`→`f6c459a` | **GOV-13**（獨立治理提案，非 SB2 交付物本身，由 SB2 過程觸發）：pre-commit 檢查 3 擴充為內容層秘密掃描，核准為 `APPROVED`，詳見 `doc/governance/GOV_013_PROPOSAL_secret_content_scan.md` |

**17 個 SB2 實作／文件 commit（`2c34059`→`f8c71ea`，含本檔送審 commit 本身，
不含 GOV-13）+ 5 個 GOV-13 commit（`85e68dc`→`f6c459a`，觸發自 SB2 過程但
屬獨立治理軌道）**（PO 2026-09-10 複核訂正：原文誤植為 19／6，已用
`git log 2c34059~1..HEAD` 逐一核對重數；表格本身無漏列 hash，是本句的總數
算錯）。SB2 的 17 個之中，多個是審查方獨立複核發現的實質缺陷修正或流程
偏差修正——逐項見上表標記「審查方發現」／「PO 複審發現」／「流程偏差」
字樣的列，不在此重複斷言一個籠統數字（同一類籠統數字先前已算錯一次）。
同 SB1 的模式，「先送審查員審查」流程按設計運作的紀錄。

## 2. 設計摘要

### 2.1 Panel 讀取器（`src/ml/panel_dataset.py::build_panel_dataset`）

PIT Universe 過濾：對每個 `trade_date`，取所有快照 `effective_date <= trade_date`
的**全域**最大值作為適用期（`merge_asof` + left join），股票須在該期有列且
`included=True` 才留在面板——股票在適用期缺席（下市／退出候選池）視同未入選，
不沿用其自身舊期判定（`c48917c` 缺陷、`0e9b7c8` 修正）。`label_end_date_tb`
即時計算（`groupby("stock_id")["trade_date"].shift(-holding_period)`），
`datetime64` dtype，可直接餵 `WalkForwardSplitter`。刻意不接受
`df_entity_mapping` 參數（Gate 3 §4.2 裁決）。`(effective_date, stock_id)`
重複時 `raise ValueError`，不默默去重。

### 2.2 每日尾端重算掛點（`src/ml/triple_barrier.py`）

`recompute_tail_labels()`（純函式）+ `apply_tail_labels()`（套用到表上）：
每檔股票只重算尾端 `holding_period + 1` 列，逐股票處理，合併鍵
`(stock_id, trade_date)`。`main_etl_pipeline.py::run_triple_barrier_tail_recompute()`
已接上 `run_all_daily_tasks()`（緊接 `run_feature_engineering_pipeline()` 之後），
**但 `run_all_daily_tasks()` 本身受 `PROJECT_STATUS.md` §0.5 #20 閘門，
`UG-G3-SB2a` Gate B 通過前不得執行**（見 §7）。

### 2.3 `entity_mapping` 路由補齊（`scripts/verify/ug_g3_sb2_backfill_entity_mapping.py`）

主策略：`keyword = candidate_prices.security_name`（去星號）→ `stock_id`。
`market` 取該股 `candidate_prices` 中 `MAX(trade_date)` 那列的 `source` 映射
（封閉映射，未知來源 raise）。真改名（6111／8932）各出 2 個 keyword，區分
現名／舊名 description。既有股票以 `stock_id` 明確排除，純 `INSERT`（禁用
`ON CONFLICT`）。寫入前機械撞名檢查（新增列彼此／對既有／對宇宙外）。

## 3. Gate A §10 DoD 現況

| # | 項目 | 狀態 |
|---|---|---|
| 1 | `panel_dataset.py` 建立，PIT 正確，測試 PASS | **完成** |
| 2 | Universe 過濾正確使用 `universe_snapshots` | **完成**（全域適用期判定，`0e9b7c8` 修正後） |
| 3 | 訓練目標配置切換正確 | **完成** |
| 4 | `entity_mapping` 路由補齊 455 檔（457 筆）完成 | **完成**（`34bcc5f`，真實庫寫入，RISK-013 三項協議全走完） |
| 5 | 每日尾端重算掛點 | **接線完成**（`ae785bc`）；**「首次啟用」不在本 SB 範圍**，受 §0.5 #20 閘門 |
| 6 | §3 三項必答落地 | **完成**（見 §2.2 掛點歸屬、RISK-025 關聯、`label_end_date_tb` 即時計算不持久化） |

## 4. 真實庫寫入結果（`UG_G3_SB2_routing_real_db_write.json` 全文為權威）

RISK-013 三項協議：備份 `stock_prediction_system2_PRE_g3_sb2_routing_20260909_232124.dump`
（71,828,551 bytes）→ `--write` 457 筆（455 檔）→ 寫入後唯讀查證六項全部相符
→ 拋棄式容器還原驗證（`entity_mapping` 5 列，寫入前狀態）。

**寫入後真實庫**（`postgres`@`localhost:5432`）：`entity_mapping` 總列數 **462**
（既有 5 + 新增 457）；`[auto:UG-G3-SB2]` 前綴 457；舊簡稱 2；`market` 分布
TPEX 130／TWSE 327；既有 4 檔 5 列逐字未變；無星號 keyword。

**惰性驗證發現的副作用**（RISK-013 步驟 5，非預期但已妥善處理）：
`fetch_active_stock_targets()` 由 4 檔變 8 檔（新增 2059／2454／3008／8069）
——根因是這 4 檔的 keyword 早於本 SB 已是 `tracking_keywords` 的 active
`ai_discovered` 列（161 篇孤兒文章）。PO 裁決接受、不回滾；訂正提案 §5
惰性宣稱，登記 RISK-022（四）、RISK-026、`PROJECT_STATUS.md` §0.5 #20
每日 ETL 執行閘門，CHAL-009 記載根因排查。

## 5. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 |
|---|---|---|
| SB2 專屬測試 52/52 | `VERIFIED THIS SESSION` | 容器內 `python -m unittest tests.test_panel_dataset tests.test_entity_mapping_backfill tests.test_daily_hook_wiring -v` |
| 全套測試 559/559 | `VERIFIED THIS SESSION` | 容器內（Python 3.14.6）`python -m unittest discover -s tests -p "test_*.py"` |
| contract-check 13/13 | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py`（本次 exit 0） |
| 路由真實庫寫入結果 | `VERIFIED THIS SESSION` | 見 `UG_G3_SB2_routing_real_db_write.json`；PO 亦獨立重跑複核，結果相符 |
| 惰性驗證 4→8 檔 | `VERIFIED THIS SESSION`（雙方各自獨立執行） | 同上證據檔；PO 另補查反向查核 SQL（4／0） |
| 每日尾端重算掛點基線比對（24/24 相符） | `VERIFIED THIS SESSION` | `recompute_tail_labels()` 對真實庫 `stock_prices` 輸出 vs `daily_ml_features` 現值逐列比對 |
| GOV-13 hook 驗證 11/11 | `VERIFIED THIS SESSION` | 見 `GOV_013_PROPOSAL_secret_content_scan.md` §7 |
| 審查方多輪獨立複核 | `REPORTED, NOT INDEPENDENTLY VERIFIED`（回報者：審查方；由 PM 角度非本次自行執行，不得代標 `VERIFIED THIS SESSION`；審查方自身角度則為其各自的 `VERIFIED THIS SESSION`） | 各輪回覆訊息記錄於本次對話（不可重跑，屬他方歷史執行紀錄） |

## 6. Known-FAIL 對照（`CLAUDE.md` §9A.2，節錄；完整清單散見各 commit 說明）

| 檢查 | known-FAIL 案例 | 結果 |
|---|---|---|
| `test_daily_hook_is_idempotent`（原版） | 結構上不會失敗的冪等測試 | 審查方指出：純函式呼叫兩次比相等，任何確定性函式必過 |
| `test_tail_boundary_is_exactly_h_plus_1_by_construction` | 邊界改 H／H+2 | 兩個方向皆 `AssertionError`，H+1 唯一使兩類斷言同時成立 |
| `test_tail_hook_is_per_stock` | 全域 `tail()`／只用 `trade_date` 合併 | 前者 `6 != 12`；後者 `ValueError: duplicate labels` |
| `test_panel_excludes_stock_absent_from_applicable_snapshot` | 修正前 PIT 過濾邏輯 | `AssertionError: 'A' unexpectedly found` |
| `test_panel_label_end_date_tb_dtype_matches_trade_date` | 修正前 dtype 邏輯 | `dtype=str`，餵 `WalkForwardSplitter` 會 `TypeError` |
| routing `market` 判定 | 取第一列而非最新列 | `AssertionError: 'TPEX' != 'TWSE'` |
| routing `clean_keyword` | 只 strip 尾端 `*` | `'矽力*-KY' != '矽力-KY'` |
| routing `clean_keyword` | 額外剝除 `-KY`/`-DR` | `'世芯' != '世芯-KY'` |
| routing 撞名檢查 vs `ON CONFLICT DO NOTHING` | 對照組示範 | 後者不拋錯、`n_inserted` 數量落差事後才發現，看不出撞誰 |
| `execute_write_and_verify` 0 筆新增 | 修正前邏輯（`.equals()` dtype 不一致） | 忠實重現得到與 PO 複審報告逐字相同訊息 |
| `execute_write_and_verify` 總數核對 | 缺此檢查的版本 | 無法偵測「多出不在任何集合內的列」 |
| GOV-13 hook 內容層 | 4 個真實樣式 mutant + 1 個 grep 異常 mutant | 全部正確 abort（詳見 GOV-13 提案 §7） |

## 7. 未驗證清單 + 已知偏差清單（誠實揭露）

### 7.1 未驗證 / 待後續處理

| 項目 | 狀態 | 去處 |
|---|---|---|
| 面板真實資料僅 3 檔台股（2330/2382/6488），458 檔要等資料回補 | 已知，非缺陷——本 SB 只交付「讀取器」，資料本體是 `UG-G3-SB2a` 範圍 | `UG-G3-SB2a`（DEC-036） |
| NVDA 不在台股宇宙（美股，`universe_snapshots` 不含） | 已知設計，非缺口 | — |
| 每日 ETL 受 §0.5 #20 閘門，掛點已接線、從未執行過 | 未驗證「啟用後真實跑一次」的行為，僅驗證接線本身（唯讀基線 24/24、單元測試三項斷言） | `UG-G3-SB2a` Gate B 通過後另行 binding confirmation |
| DEC-036（`UG-G3-SB2a` 拆分決策）狀態仍為 `PROPOSED` | 待本次 Gate B 核准結案時一併轉 `APPROVED` | 本次結案動作 |
| 161 篇孤兒文章（2059/2454/3008/8069 對應關鍵字）尚未歸屬到任何股票的特徵 | 需等每日 ETL 閘門解除、`run_feature_engineering_pipeline()` 真正跑過這 4 檔後才會第一次歸屬；歸屬結果本身未驗證 | 閘門解除後，`UG-G3-SB2a` 或後續 SB |
| 4 檔新追蹤股票（2059/2454/3008/8069）無 `stock_prices` 歷史價格 | 首次 ETL 啟用時只會抓 1 個月資料（`run_twse_pipeline` 當月邏輯），滾動特徵（`volatility_20d` 等）需要暖機期，暖機期間特徵品質未驗證 | 閘門解除後 |
| `label_end_date_tb` 與 `daily_ml_features` 現有 `target_triple_barrier`/`label_reason` 之間的時點落差 | 設計上容許（`test_panel_tolerates_label_end_date_target_mismatch` 已覆蓋），但落差的實際分佈（多少列有此落差）未在真實 458 檔資料上量測，因為資料本身尚未回補 | `UG-G3-SB2a` 後 |
| `rolling` vs `expanding`、embargo>0 自相關滲漏 | 延續 SB1 既有未驗證項 | `UG-G3-SB3` |
| RISK-025（Timeout 為少數，DEC-018 <5% 揭露條款） | 已登記，面板構建會凍結此標籤分布 | `UG-G3-SB3` D3 必答項 |

### 7.2 已知流程偏差（誠實揭露，皆已修正）

| # | 偏差 | 修正 |
|---|------|------|
| 1 | `dcac0fe` 紅綠合成一個 commit（要求的是紅色測試先行、單獨 commit） | PO 裁定：接受、不改寫歷史（§11A）；先紅證據事後補進 `UG_G3_SB2_routing_backfill_validation.json`（`36687a0`）；下一輪（`d61549c`→`a2d7641`）改回真正兩階段 |
| 2 | `34bcc5f` 證據 JSON 含字面密碼（第三次同型漏洞，CHAL-008） | `655f740` 修正 |
| 3 | `655f740` 描述漏洞時再次寫出字面值（第四次同型漏洞） | `7dd382c` 修正；後續（GOV-13 撰寫過程）又發生第五、六次，皆於 staging 前發現並修正，未進 commit 歷史 |
| 4 | GOV-12 具名出口分類理由第一次只寫在回報未寫進 commit message（`cdac61b`） | `f6c459a` 補記，不 amend |

## 8. 裁決索引

- Gate A：`2c34059`→`8c3e10d` PIT 量體訂正 + DEC-036 拆分核准
- PO 複審：`c48917c`／`a2d7641` 兩輪各兩個真實缺陷，皆已修正並複核通過
- PO 裁決：路由惰性副作用接受不回滾（`34bcc5f`），訂正提案宣稱，登記
  RISK-022（四）／RISK-026／§0.5 #20／CHAL-009
- PO binding confirmation：路由真實庫寫入（RISK-013）；每日掛點接線（僅接線）
- GOV-13：內容層秘密掃描提案 → 核准 `APPROVED`（`f6c459a`）

## 9. `DOC_PATHS` 檢查

`scripts/verify/gate0_contract_check.py` 的 `DOC_PATHS` 不含任何 Gate 提案／
送審檔或 `gates/evidence/` 下的證據檔（已查證，同既有慣例），故本次結案
搬移不觸發 §16.4 連帶義務。

## 10. 結案動作預告（§16.3，核准後執行）

1. 本檔＋ `UG_G3_SB2_GATE_A_PROPOSAL.md` `git mv` 至 `doc/upgrade/gates/closed/`
2. `PROJECT_STATUS.md` 同步：SB2 狀態轉結案，§0.2 追加一列
3. DEC-036 狀態 `PROPOSED` → `APPROVED`（僅 PO），補進 `TRACEABILITY.md`
4. `TRACEABILITY.md` §2／對應分節索引列補齊（同 SB1 結案模式）
5. `gates/` 根層清空至僅剩審查中的 SB（若無新 SB 待審則為空）

## 11. 送審聲明

- `src/ml/panel_dataset.py`、`src/ml/triple_barrier.py`（新增函式）、
  `main_etl_pipeline.py`（接線）、`scripts/verify/ug_g3_sb2_backfill_entity_mapping.py`
  皆已完成，容器內 Python 3.14.6、15 套件齊備
- 全套測試 559/559 OK；contract-check 13/13 PASS
- 真實庫 `postgres`@`localhost:5432` 的 `entity_mapping` 已完成 457 筆寫入，
  RISK-013 三項協議完整執行，備份可還原且忠實記錄寫入前狀態
- `stock_prices`、`tracking_keywords`、schema 皆未修改；未新增 migration
- 每日 ETL 執行受 §0.5 #20 閘門，本 SB 結案**不代表**閘門解除
- 請 PO 審核並裁決是否核准結案
