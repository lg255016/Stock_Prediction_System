# RISK-023 Gate A 提案：方案 A（`article_comments` 逐則重算）＋ DEC-039 修訂 DEC-024

- 日期：2026-09-13（初版）；2026-09-14 多輪訂正（見內文 2026-09-14 標記處）
- 依循：`bug-fix-protocol`（獨立小案，不綁任何 Gate/SB）
- 前置：`RISK-023_diagnosis_report.md`（步驟一唯讀診斷）＋審查方複核訂正
- **本案已結案（2026-09-14）**：實作 commit `9c7f58e`（含 §八補件二項：`df_comments=None` 拒絕可驗證、P6 一致性守衛，見 `DECISIONS.md` DEC-039 Decision 第 10／11 項）、寫入腳本 commit `f122352`；真實庫 `postgres`@`localhost:5432` 已依 RISK-013 三步驟協議完成寫入（352 個 `(trade_date, stock_id)` 鍵、8 檔股票，證據 `doc/upgrade/gates/evidence/RISK023_comment_features_write.json`）。`DEC-039` 狀態 `APPROVED`；`DEC-024` 狀態轉 `SUPERSEDED`；`RISK-023` 追加 `MITIGATED`。本文件移入 `closed/`，內容為執行過程的完整存檔，不再更新。

---

## 一、診斷訂正版

### 1.1 P6 不變式定位（VERIFIED THIS SESSION，真實庫唯讀）

原診斷報告的「13 列落差」已定位：**全部來自單一篇文章 `article_id=1495`**。

```sql
SELECT article_id, total_comments, comments_scraped_at FROM market_articles WHERE article_id=1495;
-- (1495, 25, 2026-09-05 13:53:32.868583)
SELECT count(*) FROM article_comments WHERE article_id=1495;
-- (38,)
```

`1495` 是 RISK-023 登記當時（2026-09-06）唯一已擷取過留言的文章（`comments_scraped_at` = 本次診斷全庫範圍的最早值），代表它在 `PRE-G3-01` 的批次回補**之前**就被爬過一次。`total_comments=25` 是那次的快照；批次回補期間它被再次遇到，`market_articles.total_comments` 被 write-once 擋下（正確行為，防止覆寫），但 `article_comments` 是逐則 `INSERT`（依 `(article_id, comment_seq)`，非 upsert 聚合），因此新出現的 13 則留言被正常插入，兩表因此產生 25 vs 38 的落差。

**這不是資料錯誤，是兩種寫入語意的自然結果**——`market_articles.total_comments` 凍結於首次成功寫入，`article_comments` 隨每次擷取持續累積。它同時證明了**逐則表是更完整、更新的來源**，是本提案方案 A 的直接證據。

**補充旁證**（審查方複核指出，已獨立以 SQL 核實）：這新增的第 26～38 則（13 則），時間戳**全部**落在 2026-09-05 15:39 之後（第 25 則是 13:46，第 26／27 則同為 15:39，其後遞增至 09-06 08:43）。這代表這 13 則本來就是「決策點之後才出現」的留言——**若當初就採用逐則重算，這 13 則本應被 `counts_as_of` 自然排除，不需要 write-once 或任何額外機制介入**。這是方案 A「逐則重算比文章層級過濾更精確」的一個真實案例，不是假設。

**P6 不變式須改寫**（原「相等」不成立）：

> 舊：`article_comments` 列數 = Σ `market_articles.total_comments`
> 新：`article_comments` 列數 **≥** Σ `market_articles.total_comments`，且對每一篇文章：`count(article_comments WHERE article_id=x)` **≥** `market_articles.total_comments WHERE article_id=x`（等號成立於該文章只被擷取過一次）

此修訂寫入本提案 §四 RED 測試清單第 9 條，執行檔為新增的 `scripts/verify/risk023_p6_invariant_check.py`（見 §六），非 `gate0_contract_check.py`。

### 1.2 情況 3（穩定排程近界延遲）重新定性：`ASSUMPTION` → `INFERENCE`（VERIFIED THIS SESSION 前提，模擬本身可重跑）

原診斷報告項目 3 把「排程延遲」列為尚待觀測的 `ASSUMPTION`。審查方指出：這不需要等待觀測，可從已驗證常數**確定性推導**。獨立重跑複核如下。

**前提（逐項驗證）**：

| 常數 | 值 | 驗證位置 |
|---|---|---|
| 每日排程執行時刻 | `TARGET_HOUR=15, TARGET_MINUTE=35` | `scheduler.py:31-32`（`grep` 確認） |
| 特徵決策點 cutoff | `15:30:00`（預設值） | `feature_aggregator.py`（多處，`normalize_cutoff_time` 預設） |
| 爬蟲回看窗口 | `BOARD_LOOKBACK_DAYS=2` | `main_etl_pipeline.py:53`（`grep` 確認），對本推導無影響（見下） |
| write-once | 首次擷取即定案 | `db_writer.py:320-354`（`update_comment_counts`），已於前次診斷確認 |
| 文章層級過濾 | `comments_scraped_at <= decision_point` | `feature_aggregator.py:881`，已於前次診斷確認 |

**獨立模擬**（`risk023_steady_state_simulation.py`，不連資料庫、純日期運算，可重跑）：模擬一整週（含週末）每一分鐘發文，依 Roll-Forward 規則算 `trade_date`，依「排程只在交易日 15:35 執行，執行當下已存在的文章即為首次擷取」算 `comments_scraped_at`，套用現行過濾判準。

```
總分鐘數：10,080
通過現行過濾的分鐘數：25
通過率：0.248%
通過案例：僅發文時刻落在「交易日 15:31～15:35」這個 5 分鐘窗口內、
          且該文章因晚於當日 15:30 cutoff 而被歸屬到下一個交易日的情況
          （decision_point 是隔天 15:30，比今天 15:35 的擷取晚了一整天，故能通過）
```

本次獨立重跑得到 **25/10080（0.248%）**，與審查方提出的 **20/10080（0.20%）**在數量級與結構上一致（差異出於邊界分鐘 15:35 本身是否計入「已存在」的極小實作慣例差異，非推論方向的分歧）。**兩次獨立推導都指向同一結論**：在目前的排程設計（每日僅執行一次、執行時刻晚於決策點 5 分鐘）下，**任何文章都不會落在能通過的窗口，除非它剛好在那極窄的 5 分鐘內發文**——不管系統穩定運作多久，留言三欄的 NULL 比例會**恆定**維持在 99.75%~99.8%，不是回填期特有的暫時現象。

**修訂結論**：

- DEC-024 Decision 段「在穩定的每日排程下，一篇文章的第一次爬取本來就發生在它所歸屬的那個交易日的決策時點」與 Trade-offs 段「`NULL` 應為少數而非多數」——**這兩句話的前提在本專案實際排程參數下不成立**，證據標籤 `INFERENCE`（前提逐項 `VERIFIED THIS SESSION`，推導本身可用上列腳本重跑）。
- 這不是「發現一個新的邊界案例」，而是**發現該 ADR 賴以成立的核心假設，在本專案自己的排程常數下，結構性地不成立**——嚴重度高於原診斷報告的評估（原報告誤判為「情況 2 回填期為主、情況 3 尚無實例」）。

---

## 二、方案 A 設計

### 2.1 讀取路徑變更

`db_writer.py::fetch_all_for_features()`（現行 625-655 行）目前只 `SELECT` `market_articles` 五個已聚合欄位（`push_count`／`boo_count`／`neutral_count`／`total_comments`／`comments_scraped_at`），完全不讀 `article_comments`。

**變更**：新增一條 `SELECT article_id, comment_seq, comment_tag, comment_time, year_inferred FROM article_comments`，回傳給 `feature_aggregator.py`。

### 2.2 聚合邏輯變更

`_aggregate_direct_comment_counts()`（`feature_aggregator.py:845-905`）現行對每篇文章讀「已聚合好的」`push_count`／`boo_count`／`total_comments`，套用文章層級 `comments_scraped_at <= decision_point` 過濾。

**變更**：改為對每個 **(article, stock_id) 列**（而非每篇文章）呼叫既有的 `comment_timeline.counts_as_of(comments, decision_point)`——這個函式已存在（`PRE-G3-01` 建立）且已有完整的文件化行為（`<=` 邊界、`comment_time is None` 不計入任何格），只是至今未被生產路徑呼叫。

**⚠ 決策點是 per (article, stock_id)，不是 per article**（審查方複核指出）：RISK-027 之後 `trade_date` 由 `assign_trading_days_per_stock()` 對 `(article, stock_id)` 列指派，同一篇文章對不同股票**可能**有不同 `trade_date`／`decision_point`（現行直接映射的 779 列已用 SQL 核實 0 篇一對多——`GROUP BY article_id HAVING count(DISTINCT stock_id) > 1` 查得 0 列——但這是現況資料的巧合，函式邏輯必須正確處理一對多，不能假設現況會一直成立）。聚合流程改為：

```
只對「直接映射」的 (article, stock_id) 列重算（entity_mapping 關鍵字直接對應）；
題材溢出列依 DEC-025 維持不計入成分股——本案不改這點，
_aggregate_direct_comment_counts() 名字裡的 direct 就是這個界線。
        → decision_point = combine(該列的 trade_date, cutoff_time)
        → 取該 article_id 的 article_comments 全部列
        → counts_as_of(comments, decision_point)
        → {push_count, boo_count, neutral_count, total_comments}（逐列重算值，取代 market_articles 的聚合欄位）
        → groupby(['trade_date', 'stock_id']).agg(...)  # 沿用現行分組聚合
```

既有測試 `test_theme_article_comments_do_not_leak_into_constituent_stocks` 作為本案的回歸測試——確認方案 A 上線後題材溢出文章的留言依然不會滲入成分股，DEC-025 的邊界不因本案位移。

`counts_as_of` 的呼叫次數＝ `(article, stock_id)` 列數，不是文章數——同一篇文章若對到多檔股票，會被呼叫多次（每次用該列自己的 `decision_point`），這是必要的重複計算，不是效能疏漏。

`source`／`provides_comment_direction` 的方向類欄位判斷（`feature_aggregator.py:892-894`）**不變**——那是「這個來源結構上提不提供推噓標記」的判斷，與時點過濾無關。

**NULL／0 語意**（審查方複核訂正，原稿的「有沒有 `article_comments` 列」判準會誤判）：

- **已擷取旗標** = `market_articles.total_comments IS NOT NULL`（不是「是否有 `article_comments` 列」——已用 SQL 核實真實庫有 3 篇 `total_comments=0` 且 `article_comments` 確實 0 列，這 3 篇是「已擷取、觀測到零留言」，不是「未擷取」）。
- **未擷取**（`total_comments IS NULL`）：維持 NULL——語意是「未知」，符合 `FEATURE_REGISTRY.md` §5A 成因 F。
- **已擷取但無 `article_comments` 列**（即上述 3 篇）：`counts_as_of` 對空列表回傳全 0——這是**觀測到的 0**，不是 NULL。
- **已擷取、有 `article_comments` 列，但 `counts_as_of` 在決策點前算出全 0**：同樣是**觀測到的 0**。

三種情況的判準統一為：**先看 `total_comments IS NULL` 決定 NULL／非 NULL，非 NULL 的一律呼叫 `counts_as_of`（無論該文章實際有沒有逐則列，空列表本來就會正確回傳全 0）**——不需要額外分支判斷「有沒有列」。

### 2.3 效能估計

目前 `article_comments` 136,185 列、1,234 篇。`counts_as_of()` 是純 Python 迴圈（每則留言比較一次時間戳），對單篇文章的留言數（平均 136,185/1,234 ≈ 110 則）而言可忽略；全量 1,234 篇 × 平均 110 則 ≈ 136,185 次比較，量級與現行 458 檔股票、449,263 列特徵的既有全量重算（RISK-027 段 2 實測約 4 秒）相比微不足道。**待正式實作時以真實計時佐證**，本節僅為量級估計（`ENGINEERING JUDGMENT`）。

### 2.4 與情況 1（write-once）的關係

write-once（`db_writer.update_comment_counts()`）**保留**，但角色改變：不再是特徵計算依賴的唯一資料來源保護機制，而是 `market_articles` 聚合欄位（供稽核、P6 新版不變式、非特徵用途的展示查詢）的一致性保護。特徵計算改為直接依賴 `article_comments`（逐則表本身不做 upsert，只做 append，不會被覆寫，天然不需要 write-once 保護）。

---

## 三、DEC-039 草稿（狀態：`PROPOSED`，待 PO 核准後轉 `APPROVED`）

> ⚠ 依 `evidence-sync` skill：本狀態欄位一律填 `PROPOSED`（全大寫，符合 `gate0_contract_check.py` B13 的 `STATUS_VOCAB`——本專案於本次診斷期間才發現並回報這條規則與 skill 模板範例本身的落差，本次依正確詞彙撰寫）。Agent 不自行核准。

## DEC-039：留言特徵時點有效性改依逐則時間戳重算，取代文章層級擷取時點過濾（修訂 DEC-024）

- 日期：2026-09-13
- 狀態：`PROPOSED`（待 PO 核准）
- 觸發：RISK-023（`bug-fix-protocol` 獨立小案，Gate A 提案）

### Context（背景）

DEC-024 建立了留言特徵的時點有效性判準，並以「穩定運作下，一篇文章的第一次爬取本來就發生在它所歸屬的那個交易日的決策時點」為前提，設計了 `comments_scraped_at <= decision_point` 的文章層級過濾，預期 `NULL` 只出現在系統開跑前的回填期、且應為少數。

RISK-023 Gate A 診斷（本文件 §一）以本專案已驗證的實際排程常數（`scheduler.py:31-32` 每日 15:35 執行一次；`feature_aggregator.py` 決策點 cutoff 15:30）獨立模擬穩定運作下一整週的發文情境，發現該前提**結構性不成立**：通過率僅 0.20%~0.25%，NULL 比例恆定維持在 99.75%~99.8%，不會隨系統穩定運作而降低。

同時，`PRE-G3-01` 已建立 `article_comments` 逐則留言時間戳表與 `comment_timeline.counts_as_of()` 重算函式（本次診斷之前完成，但未接入生產路徑），使 DEC-024 情況 2（回填期）「無法對齊決策時點」的前提也不再成立——只要留言的個別時間戳被保留，回填期文章一樣可以逐則重算出決策時點當下合法可見的計數。

### Problem（問題）

DEC-024 的文章層級過濾機制，其設計依據的兩個假設（「穩定運作下第一次擷取天然早於決策點」「回填期無法對齊」）都已被證明不成立或不再成立。繼續依賴這個機制，留言特徵三欄（`comment_volume_ratio`／`comment_polarization`／`net_push_momentum`）在生產環境會**恆定為 99.8% NULL**，而非 DEC-024 原本預期的「少數」——這實質上等同於這三個特徵從未真正上線過。

### Alternatives Considered（考慮方案）

1. **調整排程時間（單獨採用，不採納為唯一方案）**：把每日執行時刻提前到 15:30 之前。**缺陷**：無法解決「文章本身歸屬到當日、但只有在當日排程執行時才第一次被看見」這個結構性時序——只要排程是「一天一次、事後才看見當天的文章」，就必然有一個決策點早於「合理執行時刻」的窗口；且排程耗時可能隨資料量成長而變動，不是一個可長期穩定維持的解。
2. **文章層級過濾 + 放寬 cutoff／排程對齊規則（不採納）**：治標不治本，仍然是「整篇文章要嘛全通過要嘛全排除」的粗粒度判斷，無法反映「留言逐則到達」的真實時序。
3. **改依 `article_comments` 逐則時間戳重算（採納，見 Decision）**：直接以留言本身的時間戳判斷是否落在決策點之前，不受「文章擷取整體完成時刻」這個代理變數（proxy）拖累。

### Decision（決策）

1. **特徵計算改為逐則重算**：`_aggregate_direct_comment_counts()` 改用 `comment_timeline.counts_as_of(comments, decision_point)`，取代對 `market_articles` 已聚合欄位的文章層級 `comments_scraped_at` 過濾（見本文件 §二方案 A 設計）。
2. **DEC-024 情況 2（回填期 → NULL）的前提已不成立，其處置隨之取消**：回填期與穩定期的文章一體適用逐則重算，不再因「擷取時機在回填期」而強制 NULL。
3. **DEC-024 情況 1（write-once）保留**，但角色限縮為 `market_articles` 聚合欄位（稽核、非特徵用途查詢）的一致性保護，不再是特徵計算依賴的資料來源。
4. **NULL／0 語意**（沿用 `FEATURE_REGISTRY.md` §5A，不新增規則，但判準改正）：已擷取旗標 = `market_articles.total_comments IS NOT NULL`；未擷取 → NULL（成因 F）；已擷取（無論該文章實際有無 `article_comments` 列）→ 呼叫 `counts_as_of`，回傳值即為觀測到的計數（含 0）。
5. **決策點以 (article, stock_id) 列為單位**，非以文章為單位——同一篇文章對到不同股票時，各自用該列的 `trade_date` 算 `decision_point`，`counts_as_of` 各自呼叫一次。
6. **`year_inferred` 落界留言的處置現在就定，不留到實作階段**：接上既有的 `validate_comment_bounds()`，凡推斷出的 `comment_time` 落在 `[post_time, comments_scraped_at]` 之外者，**排除計數**（不計入 `counts_as_of` 的任何一格）。

   **【2026-09-14 訂正，實作前唯讀量測結果，取代先前用粗略 SQL 比對得出的「312 則／202 篇」】**：先前用未截斷的原始 SQL（`comment_time < post_time`）比對，會把「留言與發文同一分鐘」誤判成落界——`validate_comment_bounds()` 的 docstring 明文記載這個假陽性機制，並刻意把下界比較對象 `post_time` 截到分來避免它。**改用生產函式本身、對全庫 1,237 篇逐篇重跑**，結果：落界則數 **13**、涉及篇數 **1**、違規類型全部是 `above_scraped_at`（上界違規，不是年份推斷的下界違規）。這 13 則**正是** §1.1 已定位的 `article_id=1495` 第 26～38 則——與 P6 落差是**同一組列在兩個檢查角度下的同一個成因**（write-once 凍結 `comments_scraped_at`，`article_comments` 之後再擷取又新增留言），不是新增的獨立問題。**本次量測沒有發現任何 `below_post_time`（年份推斷）違規**——`year_inferred=TRUE` 100% 的 136,185 則裡，沒有一則被判定為年份推斷錯誤。
7. **P6 不變式改寫**：`article_comments` 列數 ≥ Σ `market_articles.total_comments`（逐文章不等式，理由見本文件 §1.1）。**驗證機制改放 `scripts/verify/` 下的唯讀資料庫腳本**（見本文件 §四），不放 `gate0_contract_check.py`（後者是純文件契約檢查，不連資料庫）。
8. `comments_scraped_at`／`market_articles` 聚合欄位**不廢除**——它們仍是稽核與「這篇文章是否已完成擷取」的判斷依據（`total_comments IS NOT NULL` 仍是「已擷取」旗標的權威來源）。
9. **`comment_seq` 時間回退防禦性守衛（`suspect` 標記，不去重）**：呼叫 `counts_as_of` 前，先檢查該篇文章的留言時間依 `comment_seq` 排序是否非遞減；出現任何回退，該篇標記 `suspect`，其涉及的所有 `(article, stock_id)` 列留言三欄一律給 NULL（成因 F 近親：擷取內容本身不可信，不是未擷取，但同樣不可用），不嘗試去重或猜測正確順序（理由與現況規模見本文件 §九，根因另立 **RISK-029**、不在本案修擷取器）。

### Rationale（理由）

- 逐則時間戳是比「文章擷取完成時刻」更精確的判斷依據——後者只是前者的一個粗糙代理，會把「決策點前已存在的合法留言」與「決策點後才出現的留言」混在同一個文章層級判斷裡，不管代理變數本身多接近事實，都無法避免這種混淆，除非代理變數與真實留言到達時間完全同步（本次模擬證明兩者在本專案實際排程下幾乎從不同步）。
- 與 `CLAUDE.md` §7.4（防止 Look-ahead Bias）一致：`counts_as_of` 的 `<=` 邊界與 DEC-024 原判準（決策時點可見性）語意完全相同，只是判斷粒度從「整篇文章」改為「逐則留言」，不改變判準本身。
- `comment_timeline.py` 模組與 `counts_as_of()` 函式已存在、已有既定行為與文件，不需要新建機制，只需要接線。

### Trade-offs（取捨）

- 特徵計算的讀取路徑變重：需要載入 `article_comments`（現有 136,185 列，持續成長）而非只讀已聚合的五欄；效能估計見本文件 §2.3，正式實作時需附真實計時。
- `year_inferred` 為 `TRUE` 的留言（本次診斷確認現有 136,185 列 100%）其推斷時間戳的可信度依賴 `infer_comment_times()` 的年份推斷邏輯；`validate_comment_bounds()`（`comment_timeline.py` 既有函式）目前未被任何生產路徑呼叫，本次一併接上讀取路徑。**處置已定**：落界留言（`comment_time` 落在 `[post_time, comments_scraped_at]` 之外）**排除計數**，不計入 `counts_as_of` 任何一格；段級報告需揭露落界則數與涉及篇數。**實測結果**（見 Decision 第 6 項）：全庫僅 13 則違規、集中於單一已知文章（`article_id=1495`），且成因與 §1.1 的 write-once 凍結問題相同，不是新的年份推斷缺陷。
- `market_articles` 的聚合欄位與 `article_comments` 逐則表並存，兩者語意不再完全對應（`total_comments` 可能落後於逐則表，見 §1.1），未來任何直接查詢 `market_articles.total_comments` 的用途（非特徵計算）需注意這個落差已是預期行為，不是資料錯誤。

### Affected Components（影響範圍）

- `src/loaders/db_writer.py`（`fetch_all_for_features()` 新增 `article_comments` 讀取，與既有文章 SELECT 同一過濾範圍）
- `src/transform/feature_aggregator.py`（`_aggregate_direct_comment_counts()` 改用 `counts_as_of()`，聚合單位改為 per (article, stock_id)）
- `src/transform/comment_timeline.py`（`counts_as_of()` 由未使用狀態轉為生產路徑依賴；`validate_comment_bounds()` 一併接入，落界留言排除計數；新增 `comment_seq` 時間回退檢查，供 `suspect` 標記使用）
- `scripts/verify/risk023_p6_invariant_check.py`（新增，P6 新版不等式的唯讀資料庫驗證）
- `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.5（時點有效性判準改寫，移除「NULL 應為少數」的錯誤預期）、§5A（視需要補「已擷取零列」與「`suspect`→NULL」成因說明）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §3.3A（RISK-023 契約記載處同步）
- `doc/upgrade/contracts/REMAINING_RISKS.md`（RISK-029 已登記；RISK-023 列已追加 Gate A 核准註記）
- `doc/evidence/DECISIONS.md`（DEC-024 標記 `Superseded by DEC-039`，本身狀態與內文保留供對照歷史推理過程，不刪除）

### Verification（驗證）

- [ ] 情況 3（近界延遲）合成案例：文章擷取時間晚於決策點數分鐘，但個別留言時間戳早於決策點——逐則重算後應為非 NULL。
- [ ] 情況 2（回填期）合成案例：文章擷取時間晚於決策點數月——逐則重算後同樣應為非 NULL（因 DEC-024 情況 2 的處置已取消）。
- [ ] `year_inferred` 跨年邊界合成案例（1 月文章、12 月留言的推斷正確性）。
- [ ] 未擷取文章（`total_comments IS NULL`）→ 維持 NULL。
- [ ] 已擷取但無 `article_comments` 列的文章（真實案例：`article_id ∈ {1772, 1872, 2117}`）→ 觀測到的 0，非 NULL。
- [ ] 已擷取、有留言列，但決策點前逐則重算為 0 → 觀測到的 0。
- [ ] 留言時間戳落在 `[post_time, comments_scraped_at]` 之外（真實案例：`article_id=1495` 第 26～38 則，`above_scraped_at`）→ `validate_comment_bounds()` 判為落界，排除計數，不計入 `counts_as_of` 任何一格。
- [ ] 同一篇文章對到兩檔不同交易日曆的股票 → 兩個 `(article, stock_id)` 列各自以自己的 `decision_point` 呼叫 `counts_as_of`，結果可不同。
- [ ] P6 新版不變式（逐文章不等式）——**放在 `scripts/verify/` 下的唯讀資料庫腳本**（比照 `ug_g3_sb2a_stage2_baseline_comparison.py` 的連線與唯讀模式），不放 `gate0_contract_check.py`。
- [ ] `comment_seq` 時間回退的文章標記 `suspect`、涉及列給 NULL（真實案例：`article_id ∈ {1815, 2662}`）；時間正常遞增的文章不受影響。
- [ ] `tests/test_comment_features.py` 既有兩項 DEC-024 驗證測試（`test_comment_count_scraped_after_decision_point_is_excluded`／`test_comment_count_scraped_before_decision_point_is_used`）重新檢視——這兩項測試斷言的是文章層級過濾行為，方案 A 上線後需要更新或以等價的逐則版本取代，不得放著兩份互相矛盾的斷言並存。

### Remaining Risks（剩餘風險）

- 排程本身（15:35 執行）不因本 ADR 改動——本 ADR 解決的是特徵計算對擷取時機的敏感度，不是排程設計本身。若未來需要更即時的特徵（例如盤中留言動態），排程時機仍是獨立議題。
- `validate_comment_bounds()` 排除落界留言後，若某篇文章的留言**全部**被排除（極端情況），該篇該股該日的計數會是「觀測到的 0」而非 NULL——語意上正確（確實沒有可信的留言資料早於決策點），但需要在段級報告特別揭露這類「全數排除」的篇數，避免與「原本就沒有留言」的 0 混淆而在報告中失去可解釋性。
- `article_comments` 依 `(article_id, comment_seq)` 追加寫入。若上游（PTT 原始頁面）刪除了某則留言，導致同一篇文章再次擷取時序號位移，會產生錯位列（同一 `comment_seq` 在不同時間對應到不同實際留言）。**目前無實例**（已用 SQL 核實：全庫 0 篇文章序號不連續），本 ADR 不處理，登記為已知風險，待出現實例再另案處置。
- **`suspect` 守衛只偵測「時間回退」，偵測不到「時間仍遞增但內容重複／交錯」的其他形態**——本次能發現 `1815`／`2662` 純粹是因為它們剛好也造成了時間回退；若未來出現一種重複／交錯但時間戳仍保持非遞減的異常，本守衛偵測不到。這是 `suspect` 守衛的已知偵測邊界，不是本 ADR 要解決的問題（根因診斷見 **RISK-029**）。
- 交叉引用：**RISK-029**（留言擷取器單次解析產生重複／交錯留言區塊，根因未定位，另案處理）。

### 證據文件

`RISK-023_diagnosis_report.md`（步驟一唯讀診斷）、`RISK023_GATE_A_PROPOSAL.md`（本文件）§一～§二、`risk023_steady_state_simulation.py`（可重跑模擬）、`FEATURE_REGISTRY.md` §5.5、**DEC-025**（留言計數只採用直接個股文章，本案不變更此邊界，見 §2.2）

---

## 四、紅測清單（Gate A 核准後，步驟二執行前先寫）

1. `test_counts_as_of_recovers_backfill_period_article`（情況 2，原本 NULL → 非 NULL）
2. `test_counts_as_of_recovers_near_miss_scheduled_article`（情況 3，模擬排程近界延遲）
3. `test_counts_as_of_year_rollover_boundary`（跨年推斷邊界，`year_inferred` 交互作用）
4. `test_unfetched_article_stays_null`（`total_comments IS NULL` → NULL，不得變 0）
5. `test_fetched_article_with_no_comment_rows_is_observed_zero`（`total_comments` 非 NULL 但 `article_comments` 無列——真實案例 `article_id ∈ {1772, 1872, 2117}`——→ 觀測到的 0，不得變 NULL）
6. `test_fetched_article_with_comments_all_after_cutoff_is_observed_zero`（有列但決策點前皆為 0 → 觀測到的 0）
7. `test_comment_time_out_of_bounds_excluded_from_count`（留言時間戳落在 `[post_time, comments_scraped_at]` 之外——真實案例 `article_id=1495` 第 26～38 則，`above_scraped_at`——`validate_comment_bounds()` 判為落界，不計入 `counts_as_of` 任何一格）
8. `test_same_article_different_stock_uses_own_decision_point`（同一篇文章對到兩檔不同交易日曆的股票，各自的 `(article, stock_id)` 列使用自己的 `decision_point`，`counts_as_of` 結果可不同）
9. `test_p6_invariant_article_comments_gte_total_comments`（新版不等式，含 `article_id=1495` 這個已知真實案例作為對照）——**執行位置見本文件 §六 P6 驗證腳本**，非本節單元測試
10. `fetch_all_for_features()` 新增 `article_comments` 讀取的介面測試（欄位齊備、空表情境、與現有文章 SELECT 使用相同的 `sentiment_score IS NOT NULL`／`FEATURE_SOURCE_ALLOWLIST` 過濾，避免整表載入）
11. `test_comment_count_scraped_after_decision_point_is_excluded`／`test_comment_count_scraped_before_decision_point_is_used`（DEC-024 既有測試）：確認更新後仍表達正確語意，不留矛盾斷言
12. `test_time_reset_article_marked_suspect_and_null`（合成一篇留言時間依 `comment_seq` 出現回退——**known-FAIL**：拿掉守衛時，`counts_as_of` 會把回退後的重複／交錯區塊也算入，產生虛高的非 NULL 計數；加上守衛後，該篇涉及的 `(article, stock_id)` 列留言三欄應為 NULL）
13. `test_monotonic_article_not_marked_suspect`（對照案例：留言時間依 `comment_seq` 正常遞增的文章，不應被誤標 `suspect`，計數照常呼叫 `counts_as_of`）

**實作前的唯讀量測（已完成並經 PO／審查方複核，結果見 §三 Decision 第 6／9 項與 §九）**：
- 完整 `validate_comment_bounds()` 邊界重新量測：全庫 13 則違規、1 篇（`article_id=1495`），全部是已知的 write-once 凍結成因，非年份推斷問題；`comment_time < post_time` 的 312 則差距全部 < 60 秒（最大 48 秒），以 `date_trunc('minute', post_time)` 為下界則 0 則違規，確認是分鐘/秒解析度落差造成的假陽性，非真實的年份推斷缺陷。
- `comment_seq` 時間回退的 2 篇（`article_id ∈ {1815, 2662}`）逐項比對：`1815` 是同一批留言被重複解析寫入兩次（22/22 相同）；`2662` 是兩段交錯的留言流（0/24 相同），成因不同、未明——**不是**留言編輯，**不是**跨年推斷錯誤。已裁決：另立 RISK-029（根因診斷），RISK-023 內加 `suspect` 守衛給 NULL、不去重（見 §九）。

## 五、真實庫寫入計畫（比照 RISK-027 段 2／RISK-013 三步驟協議）

1. **PRE 備份**：`pg_dump` logical backup 存 `D:\Python\Database_Backups\Stock_Prediction_System2\`。
2. **記憶體預期影響集**：以修復後的邏輯全量重算 `daily_ml_features` 留言三欄，與現行庫值比對，產出「預期差異鍵集合」（預期規模：以本次診斷 353 組／8 檔為量級參考，正式重算前不視為定案數字）。
3. **binding confirmation**：確認連線目標為 `postgres`@`localhost:5432`（`current_database()`／`inet_server_port()`）。
4. **執行寫入**：只 `UPDATE` 三欄「新版重算值 ≠ 現行庫值」的鍵，非全表覆寫。
5. **獨立驗證**（審查方執行，比照 RISK-027 段 2 模式）：PRE 還原 vs 真實庫的差異 = 記憶體算出的預期影響集；POST 還原 vs 真實庫的差異 = 0。
6. **POST 備份**。
7. 段級檢查：全表重算相等斷言（新版重算值 == POST 真實庫值，逐列）；並揭露 §四「實作前唯讀量測待辦」的落界則數／篇數與非單調案例判定結果。

## 六、P6 新不變式驗證腳本（獨立於 `gate0_contract_check.py`）

`gate0_contract_check.py` 是純文件契約檢查（不連資料庫），P6 是資料庫不變式，不適合放在同一個腳本。改為新增 `scripts/verify/risk023_p6_invariant_check.py`（唯讀，連線模式比照 `ug_g3_sb2a_stage2_baseline_comparison.py`）：

- 檢查：逐篇 `count(article_comments WHERE article_id=x) >= market_articles.total_comments WHERE article_id=x`（`total_comments IS NOT NULL` 者）。
- **known-FAIL 案例**：在**拋棄式容器**（獨立 `postgres:18`、隨機密碼、獨立網段、用完即拆，不得在真實 server 建臨時 database——2026-09-14 PO 複核訂正，見 `risk023_p6_invariant_check.py` 開頭的訂正記錄）裡，對某一篇文章的 `article_comments` 刪除一列使其低於 `total_comments`，確認腳本回報 `VIOLATION` 且 exit 非 0；還原後確認 exit 0。
- 正式驗收：對 `postgres`@`localhost:5432` 執行 exit 0（含 `article_id=1495` 這個已知「大於」案例——不等式而非等式，1495 不應被誤判為違規）。

## 七、Definition of Done

- `daily_ml_features` 在 `postgres`@`localhost:5432` 的留言三欄改依逐則重算產生，且與記憶體全量重算結果逐列相等。
- 紅測清單（§四）全部項目在 dev container 內 `OK`。
- `scripts/verify/gate0_contract_check.py` exit 0（文件契約，不含 P6）。
- `scripts/verify/risk023_p6_invariant_check.py` 對 `postgres`@`localhost:5432` exit 0（見 §六）。
- DEC-039 由 PO 核准並轉 `APPROVED`；DEC-024 標記 `Superseded by DEC-039`；`FEATURE_REGISTRY.md` §5.5、§5A（視是否需要補「已擷取零列」一行）、`MULTI_SOURCE_DATA_CONTRACT.md` §3.3A、`REMAINING_RISKS.md` RISK-023 列同步更新為已處置。
- PRE／POST 備份與獨立驗證紀錄存檔，證據見 `doc/upgrade/gates/evidence/`。

## 八、順手補的小項（審查方複核指出，已納入設計）

- `fetch_all_for_features()` 新增的 `article_comments` SELECT **必須**與現有文章 SELECT 使用同一個過濾（`sentiment_score IS NOT NULL` 且 `source` 在 `FEATURE_SOURCE_ALLOWLIST`），以 JOIN 或 `article_id = ANY(...)` 限縮範圍，不得整表載入 `article_comments`。
- 時間非單調的 2 篇（`article_id ∈ {1815, 2662}`，各 1 則）：實作前已逐項比對，`1815` 為同批留言重複解析（22/22 相同）、`2662` 為兩段交錯留言流（0/24 相同），非年份推斷錯誤（見 §九）。已裁決另立 RISK-029，RISK-023 內加 `suspect` 守衛，段級報告揭露 `suspect` 篇數與涉及列數。
- 文件同步清單：`MULTI_SOURCE_DATA_CONTRACT.md` §3.3A（RISK-023 契約記載處）、`FEATURE_REGISTRY.md` §5A（NULL／0 成因表視需要補「已擷取零列」一行）。

## 九、`comment_seq` 時間回退異常——已裁決：另立 RISK-029，RISK-023 內加 `suspect` 守衛（不去重）

**【2026-09-14 PO／審查方複核訂正】**：本節原稿判斷兩篇異常文章是「重新擷取時把已抓過的留言又當新留言插入」，**此判斷不成立**——已用 SQL 核實 `article_id=1815`（`total_comments=139`＝逐則列數 139）與 `article_id=2662`（`total_comments=94`＝逐則列數 94）兩篇的 `total_comments` 與逐則列數完全相等；`total_comments` 是 write-once、首次擷取即凍結，故異常區塊必是**同一次解析事件內產生**，不是再擷取追加（再擷取追加的形狀是 `article_id=1495` 那種「`total_comments`＜逐則列數」，見 §1.1）。

**逐項精確比對**（非肉眼判斷——本文件初稿在此犯過一次方法論錯誤：只憑列印輸出的時間遞增樣式肉眼判斷「內容與時間幾乎逐則對應」，未做逐項比對，導致對 `article_id=2662` 的判斷有誤，已改正）：

| 篇 | 回退點 | 逐項 `(tag, comment_time)` 比對 | 判斷 |
|---|---|---|---|
| `1815` | `comment_seq` 24 | `seq 2～23` vs `24～45`：**22/22 完全相同** | 同一批留言被重複解析寫入兩次 |
| `2662` | `comment_seq` 25 | `seq 1～24` vs `25～48`：**0/24 相同** | 不是重複，是兩段各自遞增、彼此交錯的留言流被串接，成因與 1815 不同、未明 |

`validate_comment_bounds()` 對這兩篇的完整量測皆為 **0 違規**——時間戳本身都落在 `[post_time, comments_scraped_at]` 合法範圍內，只是重複或交錯，不是年份推斷或時點過濾問題。

**裁決（PO 2026-09-14）**：

1. **新增 RISK-029**（`doc/upgrade/contracts/REMAINING_RISKS.md`，已登記）：留言擷取器單次解析產生重複／交錯留言區塊的根因（`parse_article_comments()` 走訪方式、頁面 HTML 結構）**另案診斷，不在 RISK-023 內修擷取器**。
2. **RISK-023／DEC-039 只加防禦性守衛，不去重**：逐則重算前，檢查該篇留言時間依 `comment_seq` 是否非遞減；出現回退即標記該文章為 `suspect`，其涉及的所有 `(article, stock_id)` 列留言三欄一律給 **NULL**（語意：不可信，`FEATURE_REGISTRY.md` §5A 成因 F 的近親），段級報告揭露 `suspect` 篇數與涉及列數。**不做去重**——`article_comments` 未儲存留言文字，任何去重規則都是猜測：`1815` 的 22/22 恰好可猜，`2662` 的 0/24 完全猜不出交錯的正確順序，貿然去重的風險高於保守給 NULL。
3. **現況規模**（已用 SQL 核實）：全庫 1,234 篇有逐則留言的文章中，僅 **2 篇**（`1815`、`2662`）出現此異常。

本節內容已同步移到 §三 DEC-039 Decision 與 §四 紅測清單（新增 2 條），此處保留完整訂正過程供稽核。

## 十、獨立待查項（維持登記，不併入本案）

- RISK-026（`post_time` 未來日期）——本次診斷過程中再次確認範圍未查證，不在本案處理。
