# `UG-G3-SB1`（Triple-Barrier Labeling）Gate B 送審

## 0. 一句話

Triple-Barrier 三分類標籤已實作、16 項測試全綠、真實庫 3,713 列已寫入完成，
Gate A §11 DoD 六項全數關閉；審查方獨立複核三輪、逐項抓出並修正三個實質缺陷
（NaN 價格靜默誤判、證據檔字面密碼洩漏兩次、寫入腳本比對盲點兩層），最終版本
與真實庫已通過交叉核對，請 PO 核准結案。

## 1. 完整 commit 序列（依時間順序，皆為真實 hash）

| commit | 內容 |
|---|---|
| `9d3b201` | Gate 3 啟動登記 + `UG-G3-SB1` Gate A 提案（含 §3 embargo/purge/min_train_size 重議、§6.1 label_end_date 歸屬三選項）核准 |
| `b24fc01` | 紅色測試：13 項（後補為 14→16 項），`src/ml/triple_barrier.py` 尚未存在，`ModuleNotFoundError` |
| `d2e3f27` | 綠色實作：`generate_triple_barrier_labels()`，14/14 測試轉綠，含 PO 語意裁定測試（末 H 日優先於先觸即定） |
| `874b3bf` | **審查方發現**：NaN 價格靜默誤判為 Timeout（§7.1 違反），修復 + 2 項新測試（16/16） |
| `bb5747e` | 文件同步：`FEATURE_REGISTRY.md`／`TRACEABILITY.md`／Master Plan |
| `28ed5ca` | `PURGED_WALK_FORWARD_SPEC.md` §4.3/§4.6 補齊語意裁定與判斷順序（GOV-12 情況 2 具名跳過） |
| `ed6f38e` | Gate A §11 DoD 第 3 項：Ambiguous 比例與分布報告（唯讀，真實庫） |
| `581950a` | **審查方發現**：證據 JSON 字面密碼洩漏（第一次），修正 + NULL/NaN 措辭訂正 |
| `a201f33` | 登記 RISK-024（`stock_prices` 允許 NUMERIC NaN 價格列） |
| `cba16c9` | Gate A §11 DoD 第 2 項：隔離拋棄式容器寫入驗證 |
| `32250d2` | **審查方發現**：CHAL-008 自己又寫回字面密碼（第二次），改為樣式敘述 |
| `26f7bc0` | 真實庫寫入腳本初版，拋棄式容器端到端驗證通過 |
| `453ac13` | **審查方發現**：列數/讀回不符仍照樣 commit，六項硬化（rollback+exit、分布快篩、`--backup` 檢查、二次確認等） |
| `efd0205` | **審查方發現**：分布快篩對 target 值/日期錯位是盲的，補逐列精確比對，五項 known-FAIL 累計驗證 |
| `29b5d5e` | e2e JSON 補記已知邊界（轉換邏輯共用） |
| `2d3e28e` | Gate A §11 DoD 第 6 項完成：真實庫寫入（PO binding confirmation，RISK-013 三項協議） |

**15 個 SB1 實作／文件 commit（`b24fc01`→`2d3e28e`）+ 1 個前置的 Gate A 核准 commit
（`9d3b201`，非 SB1 實作本身）**，15 個之中 5 個是審查方獨立複核發現的實質缺陷修正
（NaN 誤判、密碼洩漏 x2、寫入腳本比對盲點 x2）——這不是缺點，是「先送審查員審查」
流程按設計運作的紀錄。

## 2. 設計摘要（`d2e3f27`＋`874b3bf` 全文為權威）

`src/ml/triple_barrier.py::generate_triple_barrier_labels()`：anchor=`Open[T+1]`，
Static 模式 `upper=+2.0%`／`lower=+1.5%`，H=5。四層依序短路判斷（`PURGED_WALK_FORWARD_SPEC.md`
§4.6，`28ed5ca` 補齊）：

1. 剩餘天數 == 0 → `no_entry`
2. 剩餘天數 < H → `insufficient_data`（**即使窗口內已觀察到觸線也不例外**，PO 語意裁定）
3. anchor（`Open[T+1]`）為 NaN → `no_entry`（`874b3bf` 修復）
4. 逐日 High/Low 為 NaN → `insufficient_data`（`874b3bf` 修復，NaN 檢查先於觸線判定）
5. 同日雙觸 → `ambiguous_dual_barrier`；先觸 upper → `1`；先觸 lower → `-1`；皆未觸 → `0`

`label_end_date_tb` 為獨立欄位（DataFrame 層，非 DB 欄位，Gate A §6.1 選項 A 裁決），
與既有 `label_end_date`（T+1 標籤用）分開，避免 `WalkForwardSplitter` 的 Purge 邊界
誤用錯誤的標籤視野。

## 3. Gate A §11 DoD 六項現況

| # | 項目 | 狀態 |
|---|---|---|
| 1 | `triple_barrier.py` + 測試 PASS | **完成**（16/16，`tests/test_triple_barrier.py`，T-TB-01~17 對照 `PURGED_WALK_FORWARD_SPEC.md` §5.2） |
| 2 | 隔離拋棄式容器寫入驗證 | **完成**（`cba16c9`，`float64`→`Int64`→`INTEGER` 轉型 + 3 個 DB CHECK known-FAIL） |
| 3 | Ambiguous 比例與分布報告 | **完成**（`ed6f38e`，四檔皆 <10%：0.7%/4.2%/6.1%/7.3%） |
| 4 | §3 embargo/purge/min_train_size 重議 | **完成**（Gate A §12，PO 裁決：embargo=0 於 H≤5 維持核准，失效條件更新） |
| 5 | §6.1 label_end_date_tb 落地 | **完成**（選項 A，DataFrame 層獨立欄位） |
| 6 | 真實庫寫入 | **完成**（`2d3e28e`，PO binding confirmation，見 §4） |

## 4. 真實庫寫入結果（`UG_G3_SB1_real_db_write.json` 全文為權威）

RISK-013 三項協議：

1. **備份**：`pg_dump -Fc` → `D:\Python\Database_Backups\Stock_Prediction_System2\
   stock_prediction_system2_PRE_g3_sb1_tb_labels_20260909_151621.dump`
   （71,826,690 bytes，exit 0，與同期既有 dump 同量級）
2. **寫入**：`scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py`（`efd0205`
   版本，執行期間未修改）`--write --backup <上述檔案>`，三道核對（列數／分布快篩／
   逐列精確比對）全過，`COMMIT 完成`，exit 0
3. **還原驗證**：拋棄式容器還原該 dump，`stock_prices`／`daily_ml_features` 皆
   3,713 列，`target_triple_barrier`／`label_reason` 全為 NULL（確認備份忠實記錄
   寫入前狀態），驗後拆除

**寫入後真實庫（`postgres`@`localhost:5432`）逐檔逐格統計**（24 格，與
`UG_G3_SB1_ambiguous_ratio_report.json` 逐格核對相符）：

| 股票 | +1（止盈） | −1（止損） | 0（Timeout） | ambiguous | insufficient | no_entry |
|---|---|---|---|---|---|---|
| 2330 | 411 | 490 | 74 | 7 | 4 | 1 |
| 2382 | 404 | 513 | 24 | 41 | 4 | 1 |
| 6488 | 361 | 532 | 27 | 60 | 4 | 1 |
| NVDA | 296 | 391 | 6 | 55 | 4 | 2 |

`SELECT COUNT(*) FROM daily_ml_features WHERE target_triple_barrier IS NULL AND label_reason IS NULL` = **0**（無遺漏）。

## 5. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 |
|---|---|---|
| 16 項測試 PASS | `VERIFIED THIS SESSION` | `docker exec -u vscode -w /workspaces/Stock_Prediction_System2 <container> python -m unittest tests.test_triple_barrier -v` |
| contract-check 13/13 | `VERIFIED THIS SESSION` | `python scripts/verify/gate0_contract_check.py`（本次 exit 0） |
| 全套測試 507/507 | `VERIFIED THIS SESSION` | 容器內（Python 3.14.6）`python -m unittest discover -s tests -p "test_*.py"` |
| 四檔 Ambiguous ratio | `VERIFIED THIS SESSION` | 見 `UG_G3_SB1_ambiguous_ratio_report.json` rerun_instructions |
| 拋棄式容器寫入驗證 | `VERIFIED THIS SESSION` | 見 `UG_G3_SB1_disposable_write_validation.json` |
| 寫入腳本 5 項 known-FAIL | `VERIFIED THIS SESSION` | 見 `UG_G3_SB1_write_script_e2e_validation.json` |
| 真實庫寫入結果 | `VERIFIED THIS SESSION`（回報者本次執行） | 見 `UG_G3_SB1_real_db_write.json`；PO、審查方後續亦各自獨立重跑複核，結果相符（各自標籤各自的執行，非同一次） |
| 審查方三輪獨立複核 | `REPORTED, NOT INDEPENDENTLY VERIFIED`（由 PM 角度）／實為審查方 `VERIFIED THIS SESSION` | 各輪回覆訊息記錄於本次對話 |

## 6. Known-FAIL 對照（`CLAUDE.md` §9A.2）

| 檢查 | known-FAIL 案例 | 結果 |
|---|---|---|
| `test_tb_anchor_is_next_open` | 誤用 `Close[T]` 為 anchor 的錯誤實作 | `AssertionError`，正確結果應為 1，錯誤實作得 -1 |
| `test_tb_insufficient_data_overrides_early_touch` | 「先觸即定」錯誤語意 | `AssertionError: False is not true` |
| `test_tb_anchor_nan_is_no_entry`／`test_tb_window_nan_is_insufficient_data` | 修復前的 `d2e3f27` 舊實作本身（`874b3bf` 是修復本身，非被測對象） | 兩項皆 `AssertionError: False is not true` |
| 拋棄式容器 DB CHECK 約束 | 注入不變式/target 值域/reason 值域三種違規 INSERT | 三項皆 `CheckViolation`，合法對照組正常寫入 |
| 寫入腳本列數核對 | 少種 1 列 `daily_ml_features` 基底列 | `rollback，不 commit`，exit 1 |
| 寫入腳本分布快篩 | reason 突變體（`__LABELED__`→`insufficient_data`） | `rollback，不 commit`，exit 1 |
| 寫入腳本逐列精確比對 | 正負號翻轉突變體 | 分布快篩「通過」，逐列比對攔下 3398/3713 筆 |
| 寫入腳本逐列精確比對 | 日期錯位突變體（相鄰列互換） | 分布快篩「通過」，逐列比對攔下 1594/3713 筆 |

## 7. 未驗證清單（有名字、有去處）

| 項目 | 狀態 | 去處 |
|---|---|---|
| rolling vs expanding 對照 | 未做 | `UG-G3-SB3` 內建子實驗（Gate A §12 裁決①） |
| embargo>0 的自相關滲漏疑慮 | 理論疑慮未答，本 SB 量測範圍外 | `UG-G3-SB3` 洩漏診斷，出現折邊界異常才開 ADR |
| Dynamic barrier 模式 | Out of Scope（PO 裁決） | Ambiguous ratio > 10% 才自動叫回（§4.4 升級條件），四檔皆遠低於門檻，暫無觸發 |
| RISK-024（`stock_prices` 允許 NaN 價格列入庫） | 已登記，未處理（不在 SB1 範圍） | 獨立小案，處置對象是擷取端 |
| `_expected_rows` 與 UPDATE 迴圈共用同一套轉換邏輯的已知邊界 | 已知且接受 | 記於 `UG_G3_SB1_write_script_e2e_validation.json`，`generate_triple_barrier_labels()` 本身正確性由測試獨立覆蓋 |
| `model_trainer.py` 靜默抹平 U 語意（§0.5 #18） | 未解 | `UG-G3-SB2`（訓練消費端範圍，非本 SB） |
| RISK-025（Timeout 類為極少數，觸發 DEC-018 <5% 揭露條款） | 已登記，未處理（不在 SB1 範圍） | `UG-G3-SB3` D3 實驗必答項；SB2 面板構建會凍結此分布，若 SB3 決定調整需全量重算 |
| 尾端 4 列的每日重算歸屬未定——本腳本是一次性回填，每日 ETL 新增 `stock_prices` 後尾端 `insufficient_data` 列會變成可判定，但沒有機制會主動重算 | 未解，機制缺口 | `UG-G3-SB2` Gate A **必答項**（誰、何時重算尾端列） |
| `pd.read_sql` 直接吃 psycopg2 連線的 `UserWarning`（pandas 僅正式支援 SQLAlchemy／sqlite3） | 已知限制，目前可正常運作 | 若未來 pandas 版本改為拒絕，`scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py` 需改用 SQLAlchemy engine（腳本 docstring 已記） |

## 8. 裁決索引

- Gate A §12：embargo=0 於 H≤5 維持核准（失效條件更新）；`label_end_date_tb` 選項 A；
  Dynamic barrier Out of Scope；提案核准
- PO 語意裁定（2026-09-09）：末 H 日一律 `insufficient_data`，不採「先觸即定」；
  收錄為 DEC-035（修訂 DEC-018，`Proposed`，待本次結案時一併轉 `APPROVED`）
- 審查方發現＋PO 追認：NaN 價格處理修復（`874b3bf`）；證據 JSON 密碼洩漏修正
  x2（`581950a`、`32250d2`）；寫入腳本硬化 x2（`453ac13`、`efd0205`）
- PO 送審複審裁定（2026-09-09）：DEC-018 <5% 揭露條款觸發，登記 RISK-025，排入
  `UG-G3-SB3` D3 必答項；DEC-018 evidence-sync 補齊（Verification 打勾、風險條款
  加註）；Gate B 文件錯漏訂正（§6 commit 歸屬、§5 證據標籤主詞、§7 補兩項）
- PO binding confirmation（2026-09-09）：真實庫寫入授權，RISK-013 三項協議執行順序

## 9. `DOC_PATHS` 檢查

`scripts/verify/gate0_contract_check.py` 的 `DOC_PATHS` 不含任何 Gate 提案／送審檔或
`gates/evidence/` 下的證據檔（已查證，同既有慣例），故本次結案搬移不觸發 §16.4 連帶義務。

## 10. 送審聲明

- `src/ml/triple_barrier.py`、`scripts/verify/ug_g3_sb1_write_triple_barrier_labels.py`
  皆已完成，容器內 Python 3.14.6、15 套件齊備
- 全套測試 507/507 OK；contract-check 13/13 PASS
- 真實庫 `postgres`@`localhost:5432` 的 `daily_ml_features` 已完成 3,713 列寫入，
  RISK-013 三項協議完整執行，備份可還原且忠實記錄寫入前狀態
- `stock_prices`、schema 皆未修改；未新增 migration
- 請 PO 審核並裁決是否核准結案
