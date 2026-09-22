# UG-G2-SB6 Gate B 送審：Stock Universe 建立（Point-in-Time）

> **性質**：Gate B 送審文件，**非結案宣告**。Gate 通過與否是 PO 專屬權限。
> **提交日期**：2026-09-03
> **Gate A 核准**：PO 2026-09-03（「核准 Gate A，開始實作」）
> **相關 commit**：`9ca3429`（實作）、`44f63f3`（複查方第三輪的三項修正）
> **本文件依 `gate-submit` skill 的八項強制產出組裝。**

---

## 0. 本文件為何遲到【必須先寫】

**這份文件在實作完成、兩次 commit、兩輪複查之後才產生。** 正常順序是實作完成即產出。

**成因不是忘記**：本 SB 前後的工作節奏是
「做完 → 寫訊息給複查方 → 等回覆」的訊息迴圈，連續多輪都是這個形狀。
`small-batch-orchestrator` 階段二第 6 步要求「啟動 `gate-submit` skill 產出強制證據」，
而**我把訊息當成了交付物**。

**代價是實質的**：evidence JSON 在 git 裡，但**把它們串起來、
並明確宣告驗證邊界的那份文件不在**。
訊息只存在於複查方的 session，**沒有版控、不會進 `closed/`、Gate 2 收尾時找不到**。

> 這與本 SB 一路在抓的是同一形狀：
> **產物看起來齊備，缺的是那個把它們綁在一起、可被稽核的載體。**

`closed/` 內每一個 SB 都有 Gate B submission（SB1–SB4、SB5-DP5、SB8、SB9、Migration SB）；
唯一沒有的是 `G2_SB5`，因為它是 `DEFERRED WITH EVIDENCE`，從未走到 Gate B。
**所以缺這份是漏做，不是慣例。**

---

## 1. 交付內容

| 檔案 | 行數 | 說明 |
|------|------|------|
| `database/migrations/006_universe_snapshots.sql` | 134 | `schema_version` 5 → 6；三個 CHECK |
| `src/transform/universe_builder.py` | 354 | 純邏輯與 DB 存取層**刻意分離** |
| `tests/test_universe_builder.py` | 316 | 13 項，**零資料庫依賴** |
| `evidence/G2_SB6_union_count_calibration_pit.json` | 382 | §6 第 3 項的**現行**基準 |
| `evidence/G2_SB6_implementation_verification.json` | 187 | 本 SB 的量測總表 |

真實庫產出：**46 期快照**（`2022-11-01` ~ `2026-08-03`）、每期納入 **150**、**85,641 列**。

---

## 2. 【本 SB 最重要的發現】已核准的提案內部自相矛盾

寫 `liquidity_window()` 時必須決定 60 日窗要不要含 `effective_date` 當天。
**提案兩邊都有：**

| 立場 | 出處 |
|------|------|
| **嚴格早於** | 提案 §5 的 **P1** 逐字 `max(trade_date) < effective_date`；**DEC-017（`APPROVED`）**「每月 Universe 只能使用**生效日前已知**的 60 交易日成交資料」 |
| **含當日** | §6 第 3 項的校準 SQL `c.rk BETWEEN e.rk-59 AND e.rk`；§7 決策點 1 的 K = 1 措辭「必須在 `effective_date` **當天**出現」；K 校準 SQL 同樣是 `e.rk-59 AND e.rk` |

**裁定：採嚴格早於。** 依 `CLAUDE.md` §0.2，已核准 ADR（優先序 2）高於 Gate A 提案（過程文件）；
且**站在含當日那邊的是兩段 SQL 與一句措辭，不是決策**。ADR：**DEC-033**（`PROPOSED`）。

**為什麼不是文字之爭**：一份 `2022-11-01` 生效的快照若使用了當天的整日成交金額，
**要等到當天收盤後才算得出來** —— 在當天做任何決定時它並不存在。

**實測衝擊：46 列基準中 8 列改變，差 1~2 檔。**
**差異小到不會被列數總計發現** —— 那正是它危險的地方。
沿用舊基準，正確的實作會 FAIL 8 次，而那個 FAIL 指向的是**基準錯，不是實作錯**。

### 2.1 順序宣稱的證據等級【複查方 2026-09-03 判定】

我曾宣稱「修正後的判準於實作首次執行**之前**落檔」，並請複查方特別查證。
**那件事查不了**：

- `mtime` 記的是**最後一次寫入**，不是**首次執行** —— 兩者不是同一件事
- `mtime` 本身可被改寫
- 兩個檔在**同一個 commit** 裡，git 歷史不帶順序

**標籤：`REPORTED, NOT INDEPENDENTLY VERIFIED`（回報者：PM）。**
**不可重跑原因：產物不記錄事件發生的先後。**

> **這不影響本次結論** —— 判準的正確性建立在 DEC-017 的逐字條文上，
> **與它何時被寫下無關**。**有風險的不是判準錯，是無法證明過程是乾淨的。**

**機制化**（DEC-033 §Decision 第 6 條）：往後判準在實作期被修改時，
**修正後的判準單獨 commit 一次，然後才跑** —— git 歷史即帶順序，與任何人的說法無關。
這是同型問題的第三次（前兩次：`prior_common_supplied` 的來源、「已實測還原」寫在實測之前），
**而正解在第一次就被講出來了：真正的修法是讓來源被記下來，而不是事後論證。**

---

## 3. 產出 1：契約驗證原始輸出

```
B5   PASS | Triple-Barrier label domain 一致
       3/3 文件宣告；DDL CHECK=True
B6   PASS | Barrier anchor 一致為 Open[T+1]
       6 份使用；殘留舊 anchor 0
B7   PASS | 無「來源失敗→空 DataFrame」
       8 處提及，逐行判定全部為正當語境
B8   PASS | §19 需 PO 簽的決策皆有 ADR 承接
       6/6 存在
B9   PASS | Dcard SB 引用正確
       UG-G2-SB5 存在，無 UG-G3-SB1 誤引用
B10  PASS | 編號方案有唯一對照表
       FEATURE_REGISTRY.md §3.7 DB序號↔模型輸入索引對照
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂
B12  PASS | 特徵契約需要的 DB 欄位，讀取端皆有 SELECT（反查法）
       契約需求 13 欄；讀取端缺 0；未涵蓋 2 類
       [未涵蓋] 四個 CORE_16 平穩化特徵的「資料來源」欄為「待實作於 feature_aggregator.py」——自然語言，無法對應到具體 DB 欄位
       [未涵蓋] 題材溢出（theme_stock_mapping）與 entity_mapping 的欄位需求——由獨立查詢取得，不在 fetch_all_for_features 的兩句 SELECT 內

==================================================
Part B: 12/12 PASS
EXIT=0
```

**`WARN` 與「未涵蓋」三行照貼，未過濾** —— 它們是既有的已登錄遺留項，非本 SB 產生。

---

## 4. 產出 2：執行環境 + 測試原始輸出 + 依賴狀態

### 4a. 執行環境

| 欄位 | 內容 |
|------|------|
| 執行環境 | **container**（本專案唯一的正式測試環境，`CLAUDE.md` §13.0） |
| 容器名稱 | `stock_prediction_system2_devcontainer-app-1` |
| Python 版本 | `Python 3.14.6` |
| 執行身分 | `-u vscode`（不可省略，否則套件全部 ABSENT） |

### 4b. 測試原始輸出

```
..............................
----------------------------------------------------------------------
Ran 345 tests in 12.553s

OK
```

指令：
```bash
docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  -e DB_HOST=127.0.0.1 -e DB_PORT=59999 \
  stock_prediction_system2_devcontainer-app-1 \
  python -m unittest discover -s tests -p "test_*.py"
```

### 4c. 依賴狀態表

```
numpy                      PRESENT
pandas                     PRESENT
streamlit                  PRESENT
plotly                     PRESENT
sklearn                    PRESENT
lightgbm                   PRESENT
xgboost                    PRESENT
psycopg2                   PRESENT
jieba                      PRESENT
snownlp                    PRESENT
tenacity                   PRESENT
dotenv                     PRESENT
```

**12/12 PRESENT，無 fallback 路徑。**

### 4d. 資料庫綁定確認（測試）

測試以 `DB_HOST=127.0.0.1 DB_PORT=59999` 覆寫 —— **該埠沒有任何服務**。
容器的 `network_mode: service:db` 使未覆寫的 `localhost:5432` 直達真實開發庫（§13.4），
覆寫使測試在**原理上**碰不到它。

> ⚠ **本 SB 新增的 13 項測試不連任何資料庫**（純函式），
> 上述覆寫是為了保護**既有**的 9 個非封閉測試（HERM-01~09）。

### 4e. 實際寫入真實庫的操作（與測試分開陳述）

| 操作 | 目標 | 前置備份 |
|------|------|---------|
| migration 006 | `postgres`@`localhost:5432` | `..._PRE_sb6_migration006_20260903_115218.dump`（69,792,360 bytes） |
| `universe_builder` 寫入 46 期 | 同上 | 同上 |

執行前綁定確認（唯讀）：`current_database()` = `postgres`、`current_setting('port')` = `5432`、
`current_user` = `postgres`、`schema_version` = 5、`to_regclass('universe_snapshots')` = NULL、
`daily_ml_features` / `stock_prices` = 117 / 117。

---

## 5. 產出 3：Commit 檔案清單 + 逐檔授權稽核

**授權範圍**：PO 2026-09-03「核准 Gate A，開始實作」——
即提案 §3 In Scope 的六項，加上 `evidence-sync` 與 `small-batch-orchestrator` 要求的同步。

### commit `9ca3429`（10 檔）

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `database/migrations/006_universe_snapshots.sql` | 在授權內 | In Scope 第 1 項 |
| `src/transform/universe_builder.py` | 在授權內 | In Scope 第 2、3 項 |
| `tests/test_universe_builder.py` | 在授權內 | In Scope 第 6 項 |
| `evidence/G2_SB6_union_count_calibration_pit.json` | 在授權內 | In Scope 第 5 項的判準 |
| `evidence/G2_SB6_implementation_verification.json` | 在授權內 | In Scope 第 4、5 項的結果 |
| `doc/evidence/DECISIONS.md` | **超出 In Scope** | DEC-033。`evidence-sync` §1 要求新決策建 ADR；**若不寫，窗口裁定就只存在於 commit message** |
| `doc/evidence/TRACEABILITY.md` | **超出 In Scope** | `evidence-sync` 傳播清單第 4、5 項（§3.2 索引 + §3A 矩陣） |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | **超出 In Scope** | 傳播清單第 1 項；§3.1 決策表的「過去 60 交易日」未載明窗口邊界 |
| `doc/governance/PROJECT_STATUS.md` | **超出 In Scope** | `small-batch-orchestrator` 階段二第 4 步（單一狀態來源）+ §0.4 測試基線 |
| `doc/upgrade/gates/G2_SB6_GATE_A_PROPOSAL.md` | **超出 In Scope** | 就地加註實作期發現（§16.2：原文不改寫） |

### commit `44f63f3`（6 檔）

全部為複查方 2026-09-03 第三輪指定的三項修正 + 一項自補，**皆為文件**：
`DECISIONS.md`、`TRACEABILITY.md`、`PROJECT_STATUS.md`、
`G2_SB6_GATE_A_PROPOSAL.md`、兩個 evidence JSON。

> **五個「超出 In Scope」的檔案全部是 skill 強制要求的同步**，
> 不是順手改的。**但它們確實超出提案 §3 的字面清單，故在此逐檔列出**（§12.3）。

---

## 6. 產出 4：格式／行尾夾帶偵測

兩個 commit 的 `--numstat` 與 `--numstat -w` **皆無落差**。
pre-commit 檢查 2 兩次皆 PASS。`git diff --check` `exit 0`。

**但有一件事必須主動揭露**：我用 Python 改寫這些 `.md`／`.json` 時，
**工作區的 EOL 由 CRLF 變成 LF**。

- repo blob 本來就是 LF（`core.autocrlf=true`），故 **commit 的 diff 未受影響**
- 兩個 commit 的 diff 分別是 1509/5 與 21/7 —— **純內容編輯，無全檔規模的漂移**

> **仍然揭露，因為 `git diff --check` 只抓新增的尾隨空白，
> 單靠它不足以清掉一次整檔改寫。**

---

## 7. 產出 5：證據標籤表

| 宣稱 | 標籤 | 可重跑指令 / 不可重跑原因 |
|------|------|--------------------------|
| 46 期快照、每期 150、85,641 列 | `VERIFIED THIS SESSION` | `SELECT count(DISTINCT effective_date), count(*) FROM universe_snapshots;` |
| 逐月對號 46/46 逐一相等 | `VERIFIED THIS SESSION` | **離線**：`evidence/G2_SB6_monthly_reconciliation_knownfail.json` 的 `comparison_table` 自帶三欄 46 列，逐列比對即可，**不需要資料庫**。**連庫**：該檔 `sql_verbatim` 三段 |
| `median_turnover` 2.5×10⁸ ~ 9.3×10¹⁰ | `VERIFIED THIS SESSION` | `SELECT min(median_turnover), max(median_turnover) FROM universe_snapshots WHERE included;` |
| 相鄰重疊 85.33 / 90.21 / 94.67% | `VERIFIED THIS SESSION` | `evidence/G2_SB6_implementation_verification.json` 的 `5_adjacent_overlap` |
| 退出股兩類違規皆 0；4 檔曾被納入 41 期 | `VERIFIED THIS SESSION` | 同上 `6_exit_stocks`（SQL 見 scratchpad `exit_check.sql`，已納入證據檔敘述） |
| V2 不成立（80 上跳／14 下跳／22 不動） | `VERIFIED THIS SESSION` | 同上 `V1_V2_SEVEN_DAY_SPIKE` |
| DoD 停牌配對數 = 1，且該筆是退出非停牌 | `VERIFIED THIS SESSION` | 同上 `DOD_SUSPENSION_PAIRS` |
| 全套測試 345 / OK；contract-check exit 0 | `VERIFIED THIS SESSION` | §3、§4 的原始輸出 |
| §6 第 3 項這項檢查**有失敗能力** | `VERIFIED THIS SESSION` | `evidence/G2_SB6_monthly_reconciliation_knownfail.json` —— 用已作廢的含當日基準比對同一份管線輸出，**實跑 8/46 FAIL** |
| 前置備份可還原且內容與遷移前狀態相符 | `VERIFIED THIS SESSION` | 拋棄式容器 `sb6_pre006_check`：`pg_restore` 後 `schema_version` = 5、`universe_snapshots` 不存在、`candidate_prices` 1,821,870、117/117/331/26 |
| **判準修正早於實作首次執行** | **`REPORTED, NOT INDEPENDENTLY VERIFIED`** | **不可重跑：產物不記錄事件發生的先後**（見 §2.1） |
| K = 1 在**排他窗**下仍零誤判 | **`INFERENCE`** | **不可重跑：換算而非重測。** 已知前提：原校準 K 1~15 零誤判、新語意相當於原度量的 `gap <= 1`。**未驗證前提：排名基礎已由含當日改為排他，名次輕微變動時該落在哪一格未量測** |
| 32 檔退出股 → 43 檔 | `VERIFIED THIS SESSION` | 見證據檔 `6_exit_stocks`；原 32 為 SB9 三年資料 |
| `not_common_stock_code` 分支在生產資料上正確 | **`NOT VERIFIED`** | **未驗證範圍**：真實資料一次都沒觸發該分支（取數層已過濾）。**只有測試覆蓋** |

---

## 8. 產出 6：known-FAIL 案例對照表

| 檢查 | known-FAIL 案例 | 實測結果 | 復原確認 |
|------|----------------|---------|---------|
| **P1 前視偏誤防護** | 把 `effective_date` 當天與之後的觀測餵進 `build_snapshot()` | `LookaheadError` 兩次（`test_p1_...` 的兩個 `assertRaises`） | 測試內建，無需復原 |
| **P3 歷史不受後續資料影響** | `survivor_filtered` —— 只保留「今日仍存在」的股票 | 斷言其輸出**必須**與正確快照不同，且 `1101` 必須消失；實際跑出差異 | 同上 |
| **P4 退出股不得回溯移除** | 移除 `1101` 的實作會讓 `assertIn` 失敗 | 測試通過（含正面證據：真實資料 4 檔退出股被納入 41 期） | 同上 |
| **P5 停牌不等於退出** | 停牌股整列不寫入會讓 `assertIn('1102')` 失敗 | 測試通過；並斷言理由為 `no_recent_activity` 而**非** `delisted` | 同上 |
| **§6 第 3 項逐月對號** | **用已作廢的「含當日」基準比對管線輸出** | **實際跑出 8/46 不符。完整八筆與三欄 46 列對照落檔於 `evidence/G2_SB6_monthly_reconciliation_knownfail.json`**，見下方 §8.1 | 唯讀查詢，未改任何資料 |
| **RISK-013 遷移守門** | 在**不設** `CONFIRM_REAL_DB_MIGRATION_TARGET` 的情況下執行 `apply_migrations.py` | **實際拒絕**：「偵測到連線目標疑似為真實開發 DB (host=localhost, port=5432, database=postgres)，拒絕執行。」 | 未套用任何 migration；設變數後才成功 |
| migration 006 的三個 CHECK | *未構造* | — | **本項無 known-FAIL 案例，不計入證據**（見下） |

### 8.1 逐月對號的 known-FAIL —— **已改為離線可重現**

**原本的寫法有三個問題**（複查方 2026-09-03 指出）：
八筆只列了三筆、第四欄不是可重跑指令、**且沒有任何證據檔記錄那次執行**。
而 §7 把這項標 `VERIFIED THIS SESSION`、可重跑欄寫「見 §8」——**§8 沒有指令**。

> **一份證明「其他檢查會失敗」的證據，自己不可重跑。**
> **這與本 SB 一路在抓的形狀完全相同，只是這一次落在最上層。**

已落檔 `evidence/G2_SB6_monthly_reconciliation_knownfail.json`，自帶：

- 兩份基準的**窗口定義逐字**（`e.rk-59 AND e.rk` vs `e.rk-60 AND e.rk-1`）與三段 `sql_verbatim`
- **46 列三欄對照**（含當日基準／排他基準／管線輸出）
- **完整八筆不符，不省略**

| effective_date | 含當日基準 | 管線 | 差 |
|---|---|---|---|
| 2023-03-01 | 1782 | 1781 | −1 |
| 2024-05-02 | 1829 | 1830 | +1 |
| 2024-09-02 | 1848 | 1846 | −2 |
| 2024-10-01 | 1856 | 1855 | −1 |
| 2025-04-01 | 1890 | 1891 | +1 |
| 2025-07-01 | 1902 | 1903 | +1 |
| 2026-02-02 | 1949 | 1948 | −1 |
| 2026-07-01 | 1976 | 1977 | +1 |

**為什麼這一版比原本強**：兩份基準都已在 git 裡，管線輸出也落了檔，
所以這個 known-FAIL **不依賴任何容器、任何人、任何時點** ——
讀 JSON 逐列比對就能重驗。
⚠ 但 `calibration_4y.json` **只有分市場兩欄、沒有 `union_all`**，
故新檔是含當日 `union_all` 的**唯一版控紀錄**；
交叉核對已做：新檔的排他欄與 `calibration_pit.json` **逐列相符（不符 0 列）**。

⚠ **本案例證明的是「有失敗能力」，不是「能抓到所有錯誤」** ——
它對「窗口邊界差一天」敏感（1~2 檔），這不等於它對任何一種計算錯誤都敏感。

> **`chk_universe_snapshots_*` 三個 CHECK 沒有 known-FAIL 案例。**
> 它們在程式層有對應斷言（`test_universe_snapshot_saved` 檢查
> `included == (exclusion_reason is None)`、`test_universe_size` 檢查排除者 rank 為 None），
> **但 CHECK 本身沒有被實際違反過一次。**
> 依 §9A.2，**它們目前產出的不是證據，是通過的外觀** ——
> 一個從未失敗過的約束與一個永遠不會失敗的約束，在輸出上無法區分。
> **明確標示為不計入證據，不列為已驗證。**

---

## 9. 產出 7：DoD 逐項指名目標資料庫

**目標資料庫一律為 `postgres`@`localhost:5432`（真實開發庫），除測試外。**

| # | DoD 項目 | 目標 | 狀態 |
|---|---------|------|------|
| 1 | §7 三個決策點經 PO 裁決後才實作 | — | ✅ K=1、匯入、150 皆於 2026-09-02~03 裁決 |
| 2 | `universe_snapshots` 建立於決策點 2 指定的資料庫；前置 `pg_dump` 已完成並實測還原 | **`postgres`@`localhost:5432`** | ✅ 建表完成；前置備份 69,792,360 bytes，**已實測還原**（見 §9.1）——標籤由 `NOT VERIFIED` 升為 `VERIFIED THIS SESSION` |
| 3 | 46 期快照已產出，逐月符合 §6 | **`postgres`@`localhost:5432`** | ✅ 46/46 |
| 4 | P1–P5 全部通過，且 P3、P4 各出示一個實際跑出的 FAIL | 無（純函式，不連 DB） | ✅ P1、P3 已跑出 FAIL；**P4 的 FAIL 是斷言方向而非 raise**，見 §8 |
| 5 | V1／V2 已執行並記錄，含「不成立」時的處置 | **`postgres`@`localhost:5432`**（唯讀） | ✅ **V2 不成立**，依事前處置只記錄為觀測 |
| 6 | 停牌配對數已量出 | **`postgres`@`localhost:5432`**（唯讀） | ✅ **1**，且該筆是退出非停牌 |
| 7 | `daily_ml_features` 與 `stock_prices` 維持 117 列 | **`postgres`@`localhost:5432`** | ✅ 117 / 117 |
| 8 | 全套測試通過；contract-check exit 0；無夾帶格式變更 | **container** | ✅ 345 / OK；exit 0；無落差 |
| 9 | 過程文件於 PO 核准後的結案 commit 移入 `gates/closed/` | — | ⏳ **尚未執行**，見 §10 |

### 9.1 前置備份的還原實測【2026-09-03 補做】

**原本這一項我自己標了 `NOT VERIFIED`，標得對 —— 但那是一個 DoD 項目，不是一個限制**
（複查方 2026-09-03）。DoD 第 2 項逐字要求「前置 `pg_dump` 備份已完成**並實測還原驗證**」，
**未達成的 DoD，照它自己的定義就不是 done。**

> 「反正 `universe_snapshots` 是衍生資料、可整表重建」是真的，
> **但那正是會讓人跳過驗證的推理** —— 這份備份守的是 `schema_version` 5→6 那一步，
> **那一步不是衍生的。**

拋棄式容器 `sb6_pre006_check`（`--rm`、無 volume、不進 compose 網路，驗後已拆除）：

| 檢查 | 結果 |
|---|---|
| dump 位元組數（host vs 容器內） | 69,792,360 = 69,792,360 |
| `schema_version` | **5**（正確 —— 備份早於 migration 006） |
| `to_regclass('universe_snapshots')` | **NULL（表不存在）** —— 正確反映遷移前狀態 |
| `candidate_prices` | **1,821,870** |
| `daily_ml_features` / `stock_prices` | **117 / 117** |
| `market_articles` / `tracking_keywords` | 331 / 26 |
| `candidate_prices` 的 CHECK | `chk_candidate_prices_nonneg`、`chk_candidate_prices_ohlc_consistency` |

> ⚠ **`pg_restore` 報 10 個錯誤，逐條看過：10 條全部是 `ALTER TABLE ... OWNER TO postgres`**，
> 失敗原因是拋棄式容器裡沒有 `postgres` 這個 role（測試用戶 `chk`）。
> **測試容器的產物，不是 dump 的缺陷**；還原回真實庫不會發生。**資料本體零錯誤。**

**這證明 migration 006 的回退路徑是真的可用的**，不只是「理論上可以」。

> **另一次的還原實測不能代替這一次**：`G2_SB6_dump_restore_verification.json`
> 驗的是候選池那份 dump。**同一個標準，一次做一次不做，下次就不知道哪次算數。**

---

## 10. 產出 8：過程文件移入 `closed/` —— **尚未執行，且刻意不做**

| # | 問題 | 回答 |
|---|------|------|
| 1 | Gate A 提案與本文件是否已 `git mv` 至 `closed/`？ | **否，且刻意不做** |
| 2 | rename 是否為 `R100`？ | 不適用（尚未搬移） |
| 3 | 是否關閉整個 Gate？ | 否，Gate 2 尚有 SB7 |
| 4 | 被搬移檔案是否在 `DOC_PATHS`？ | 搬移時需檢查（`gate0_contract_check.py` 目前不含這兩份） |
| 5 | `doc/README.md` 是否需同步？ | 搬移時一併檢查 |

> **為何刻意不做**：`CLAUDE.md` §16.3 規則 3 的觸發條件是「**SB 通過 Gate B 後**」，
> 而 Gate B 是否通過是 PO 專屬權限，**現在尚未通過**。
>
> **這個錯誤我在 `UG-G2-SB9` 犯過** —— 當時提前把文件移入 `closed/`，
> 同時違反了規則 4 的不變式（根層只保留審查中的 SB）。
> **搬移是結案 commit 的一部分，不是送審的一部分。**

---

## 11. 已知限制（先寫下來，不等 PO 問）

1. **`UniverseBuilder`（DB 存取層）沒有單元測試覆蓋。** 13 項測試全在純函式上。
   該層由 46 期實際執行與 §6 逐項比對負責，**是不同種類的證據，不得混為一談**。
2. **三個 CHECK 約束沒有 known-FAIL 案例**，依 §9A.2 不計入證據（§8）。
3. **分市場的逐月對號未納入管線驗證** —— `universe_snapshots` 沒有 `source` 欄，
   要分市場就得回頭 join `candidate_prices`，**那就是重跑校準 SQL，會變成拿自己比自己**。
4. **K = 1 在排他窗下未重測**（`INFERENCE`，已登記於 DEC-033 剩餘風險）。
5. **V2 不成立**，停牌成因退回「無外部資料源即無法判定」。
6. **§6 第 5 項最小值 85.33%，距門檻僅 0.33 個百分點。** 通過，
   **但它不是一條寬鬆的線** —— SB7 不得據此放寬。
7. ~~**本次 migration 前的備份未做還原實測**（§9 第 2 項）。~~
   **2026-09-03 已補做，見 §9.1。** 保留原文加刪除線，**因為「送審時它確實是一個限制」是紀錄的一部分**。
8. RISK-022 未解；`best_bid_volume`／`best_ask_volume` 仍不得使用。
9. 代號本身變更的追蹤未實作（提案 §8 第 1 項）。

---

## 12. 交給 SB7／Gate 3 的兩個觀察

1. **§6 第 5 項的餘裕極薄**（見上）。
2. **`2888 新光金` 是三個獨立量測的唯一例外**：K 校準唯一 `gap > 0`、
   末見日是三年來成交最大的一天、停牌配對數的唯一那筆。
   > **一檔股票同時是三個不同量測的唯一例外，那不是雜訊，
   > 是那檔股票在制度上發生了什麼事**（複查方 2026-09-03）。
   > Gate 3 若要處理退出事件，**它是唯一一個已知有完整紀錄的樣本**。

---

## 13. 請 PO 裁決的事項

1. **UG-G2-SB6 Gate B 是否通過。**
2. **DEC-033 是否核准**（現為 `PROPOSED`；依 §0.5 #10，Gate B 通過時一併轉 `APPROVED`）。
3. 若通過，授權結案 commit：本文件與 Gate A 提案 `git mv` 至 `gates/closed/`（§10）。
