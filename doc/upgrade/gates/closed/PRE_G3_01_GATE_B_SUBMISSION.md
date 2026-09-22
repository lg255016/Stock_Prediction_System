# `PRE-G3-01` Gate B 送審 —— 結案

- 日期：2026-09-08
- 涵蓋：逐則留言時間戳全鏈（解析／上下界／migration 008／寫入路徑／`1495` 重抓）
  + B0 歷史區間探測 + B1 試點
- 性質：**結案文件**，回顧性彙整既有已 commit 的工作，本文撰寫過程未觸網、未寫入資料庫
- PO 裁示：`gates/` 根層結案（見本次裁決訊息 §〇）

---

## 0. 一句話

**逐則留言時間戳從「只存截至 T 的計數」改成「存下每一則、cutoff 任選」，
過程中撞出四種違反型態、一個時區地雷、一次判準假通過 —— 而 B0／B1 兩次觸網
探測都在觸網前把停損寫死，沒有一次是先看結果再定門檻。**

---

## 1. 完整 commit 序列（依時間順序，皆為真實 hash）

### 1.1 前置：PTT 內頁時間戳探測

| commit | 內容 |
|---|---|
| `232c6dd` | 判準**觸網之前**寫死 |
| `2b1bd1e` | 探測結果 —— 一次請求，五項判準全部有答案 |

### 1.2 Gate A 提案

| commit | 內容 |
|---|---|
| `a44815f` | Gate A 提案 —— PTT 歷史回補（含逐則留言時間戳設計） |
| `00fdc8e` | 提案修訂：決策點 2b 採 (乙)，新增 RISK-023 與契約 §3.3A |

### 1.3 逐則留言時間戳實作（紅→綠，紅先於實作 commit）

| commit | 內容 |
|---|---|
| `c5ec415` | **W1~W6 紅** —— 實作之前 commit |
| `88765a1` | 實作 `comment_timeline` + 解析器帶出逐則資料 |
| `1a6362c` | **W7 紅** —— 推論值必須夾在閉區間裡（上界 = `comments_scraped_at`） |
| `25d6261` | 實作 `validate_comment_bounds` |
| `9e50491` | 下界的解析度不對稱誤報（紅）+ `below_post_time` 可達性 |
| `a223fa1` | 修正：下界比較前截到分；補上界的容差 |
| `66289c2` | 註明 `_FULL` 分支在現行 PTT 上不會觸發（非誤差累積防護） |
| `4c57483` | **migration 008** + 寫入路徑 —— 邊界違反時拒寫整篇 |
| `7f7827f` | migration 008 執行證據 —— `schema_version` 7 → 8 |
| `07b0c71` | §5 規模預期拆成三行（原寫法會產生假 FAIL） |

### 1.4 `§3.6B` 時區地雷與 `article_id=1495` 重抓

| commit | 內容 |
|---|---|
| `c0c4a7b` | 決策點 4 重抓（1 個請求）—— 2a **FAIL**，成因是 §3.6B 那一列 |
| `dc9825c` | 2a 記為 FAIL（判準不成立）；§3.6B 那 1 列升級為活的地雷 |
| `09438a4` | 時區列修正的預期 —— **UPDATE 之前** commit |
| `a28afea` | 時區列修正 —— `article_id=1495` 的 `comments_scraped_at` +8h（1 列，`rowcount=1`） |

⚠ **依賴的前置基礎設施**（已於 `UG-G2-SB7`／Gate 2 完成、非本 SB 交付，僅引用）：
`f2fa4f1`（時區政策紅）、`87256e4`（`src/common/clock.py`，10 處 naive「現在」改走
時區政策）——**§3.6B 的整組問題之所以能被發現與修正，建立在這兩個 commit 之上**，
本 SB 不重複列為自己的交付。

### 1.5 B0 歷史區間探測

| commit | 內容 |
|---|---|
| `8005f0d` | 判準**觸網之前**寫死 |
| `9104e8d` | 判準補正 A1~A3（新增 E6、單調性假設、E3 讀法——只補不改） |
| `e05643b` | 補記「404 vs 失敗」的已採用讀法（非改判準） |
| `ab08e04` | B0 探測結果 —— 8 個請求，其中兩項是空洞的通過 |

### 1.6 B1 試點

| commit | 內容 |
|---|---|
| `9b03d48` | B1 試點提案 —— 只要試點授權，不要全量 |
| `b87ea64` | 依三項裁決修訂：改寫隔離臨時 DB，RISK-013 搬家 |
| `62f00db` | S1（50 頁）—— 命中率 9.81%，落在 B0 估計的 CI 之外，**停止** |
| `7a03feb` | B1 試點報告（**S1 = 全部**，PO 裁決）—— 兩個比命中率更重要的發現 |
| `74b89df` | 試點報告三處更正（40.8%→59.2% 零貢獻，全欄比對修正） |

---

## 2. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 / 依據 |
|---|---|---|
| `comment_timeline.infer_comment_times`／`validate_comment_bounds` 通過 W1~W8 | `VERIFIED THIS SESSION`（撰寫當時） | `python -m unittest tests.test_comment_timeline tests.test_comment_write_path` |
| migration 008 套用成功，`schema_version` 7→8 | `VERIFIED THIS SESSION` | `PRE_G3_01_migration008_execution.json` |
| `article_id=1495` 的 `comments_scraped_at` 修正前後值 | `VERIFIED THIS SESSION` | `PRE_G3_01_tz_row_fix_result.json`；`daily_ml_features` 指紋前後一致（`4fc208b9...`，137 列） |
| B0：8 個請求、單調性窮盡檢驗（50 頁範圍） | `VERIFIED THIS SESSION`（撰寫當時，範圍限定） | `PRE_G3_01_B0_PROBE_RESULT.json` |
| B1 S1：命中率 9.81%（CI 8.12~11.81%） | `VERIFIED THIS SESSION` | `PRE_G3_01_B1_pilot_S1.json` |
| B0 估計 0.69%（CI 0.12~3.80%）與 S1 不相交，時代混淆 14 倍 | `VERIFIED THIS SESSION`（兩次量測比對） | 兩份 JSON 交叉比對，見 `7a03feb` 內文 |
| 40.8%／59.2% 命中文章零貢獻 | `VERIFIED THIS SESSION` → `74b89df` **更正為 59.2%**（全欄比對） | `PRE_G3_01_B1_PILOT_REPORT.md` §0A／§5.3A |
| `daily_ml_features` 指紋在時區修正前後不變 | `VERIFIED THIS SESSION` | 同一段動態欄位清單方法，兩次執行比對 |
| 逐標的天數（2330 58.3%／2382・6488 各 4.2%） | `VERIFIED THIS SESSION`，n 極小 | 已於報告明確標註「n 極小，不足以支撐門檻決策」 |

---

## 3. Known-FAIL 對照（`CLAUDE.md` §9A.2）

| 檢查 | Known-FAIL 案例 | 結果 |
|---|---|---|
| `validate_comment_bounds` 上界 | wrap-rule 首則回捲產生 `above_scraped_at` | 段 A 生產環境第一次真實觸發（`75cbb84`，段 1；歸屬見 `PRE-G3-03` 結案） |
| `validate_comment_bounds` 下界 | `below_post_time`（留言早於文章） | 段 5 生產觸發（`d942464`；歸屬見 `PRE-G3-03` 結案） |
| B0 判準「404 vs 失敗」讀法 | 若讀法錯誤會使二分搜尋無法終止 | 已於 `e05643b` 明文記錄採用的讀法，非執行時調整 |
| 2a 決策點 | 修正前應為 FAIL | `c0c4a7b` 實測 FAIL，成因記錄；修正後 `a28afea` 重驗 PASS |
| GOV-12 具名出口情況 (1) 判定 | B0 判準補正時 `json.dumps(indent=1)` 整檔重新縮排，觸發情況 (1)，**未使用具名出口，改用 2-space 重新序列化** | 已於 `9104e8d` 附近的工作記錄；本身即是「具名出口誤用」的 known-FAIL 案例（見 `CLAUDE.md` §12.4 GOV-12 段落） |

---

## 4. 未驗證清單（有名字、有去處，不是「還有一些事沒做」）

| # | 項目 | 現況 | 去處 |
|---|---|---|---|
| 1 | **wrap-rule 推論規則精修**（跨年 `(月,日)` 回捲判定） | 已知有缺陷，13 篇拒寫中 6 篇因此觸發（`above_scraped_at`），採**整篇拒寫**而非修正推論——**刻意選擇「拒寫已知有問題的資料」優先於「即時修好推論規則」** | 排入 Gate 3 前的技術債清單；三個子形狀（首則回捲／中途回捲／不需回捲即違反）已於 `PRE-G3-03` 段 4 完整記錄，**修復設計待另案** |
| 2 | **單調性 `ASSUMPTION`**（PTT 頁面可存取性隨頁碼單調） | B0 僅 50 頁窮盡檢驗（0.5%）；`PRE-G3-03` 段 A 擴大至 750 頁（7.2%），連續區間零 404 | **仍是 `ASSUMPTION`**，是否升級留給 `PRE-G3-02`／Gate 3 判斷，本 SB 不代為升級 |
| 3 | **時代混淆的量級**（14 倍，B0 vs S1） | 已量測，但只是**兩個時間點**的比較，非連續趨勢 | `PRE-G3-03` 的八點命中率序列部分緩解（見 `PRE-G3-02` 結案文件），完整趨勢仍待更長時間軸的資料 |
| 4 | **`counts_as_of` 是否已在生產路徑實際被消費** | `comment_timeline.counts_as_of()` 已寫成、已測試，**但截至本 SB 結案，尚無生產程式碼呼叫端**（`grep` 零命中，若有變動以實測為準） | Gate 3 的 panel dataset 建構（`UG-G3-SB2`）預期會是第一個消費端 |
| 5 | **`article_id=1495` 修正的下游影響**（ii）：修正不改變特徵值 | 標 `INFERENCE`（程式路徑分析），非直接驗證——`daily_ml_features` 是物化輸出，`UPDATE market_articles` 不會自動傳播 | 已於 `PRE_G3_01_tz_row_fix_expectations.json` 3(b) 明確標註「指紋不變只代表沒有人重跑」，Gate 3 全量重算（`PRE-G3-04`）時一併驗證 |

---

## 5. 裁決索引

| 裁決 | 內容 | 裁決者／依據 | commit |
|---|---|---|---|
| B1 範圍變更 | S1（50 頁）即為試點全部，不跑 S2/S3/S4 | PO 2026-09-06，理由：精度對預算無意義（CI 跨度 1.46 倍 vs 跑滿 1.21 倍，代價 3 倍請求） | `7a03feb` |
| E3 修正 | 停止基準由「首個 `r-ent`」改為 `max` 時間戳（置底文修正） | PO 裁決，成因：置底文時間戳拉低 `min`、永遠不拉高 `max` | 已於 `PRE_G3_01_B1_PILOT_PROPOSAL.md` 記錄，實作於 `ptt_scraper.py` |
| 決策點 2b | 採 (乙)：`comment_tag` 現在不抓、回補完再重算，不與擷取正確性混在一次驗收 | PO 裁決，理由：混在一起會分不出是誰造成的差異 | `00fdc8e` |
| 決策點 4 | 舊列處置：重抓 1 個請求驗證，優於逕行相信 UTC/台北推論 | PO 裁決 | `c0c4a7b` |
| 舊值處置 | `article_id=1495` 的 `comments_scraped_at` +8h，**逐字不得外推**，僅此 1 列 | PO 2026-09-06 明確授權範圍 | `09438a4`／`a28afea` |
| 40.8%→59.2% 更正 | 零貢獻比例改用全欄比對，非單欄 `close_price` | 自我發現並更正，PO 認可保留原文加註 | `74b89df` |

---

## 6. `DOC_PATHS` 檢查

`scripts/verify/gate0_contract_check.py` 的 `DOC_PATHS` 為 7 份固定契約文件
（`SYSTEM_UPGRADE_MASTER_PLAN.md`／`FEATURE_REGISTRY.md`／`PURGED_WALK_FORWARD_SPEC.md`／
`MULTI_SOURCE_DATA_CONTRACT.md`／`DB_MIGRATION_PLAN.md`／`DECISIONS.md`／`TRACEABILITY.md`）——
**已核對，`PRE-G3-01` 的搬移文件皆不在此清單內，本次搬移無需同步 `DOC_PATHS`。**

---

## 7. 結案聲明

`PRE-G3-01` 的實質工作（逐則留言時間戳全鏈、B0 探測、B1 試點）**已於各自的觸網前
判準與 PO 逐輪裁決下完成**。本文件為結案彙整；**根層提案文件隨本次結案 commit
一併移入 `closed/`**（見同一 commit 的 `git mv`）。

> **程序揭露**：結案 commit 先於 PO 核准執行（成因：交辦訊息合併時遺失順序行）；
> PO 於 2026-09-08 審閱複查結果後追認。
