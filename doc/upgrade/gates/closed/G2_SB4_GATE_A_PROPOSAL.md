# UG-G2-SB4 Gate A 提案：留言接線與衍生特徵計算

> 狀態：**Gate A 審查中**（尚未實作，未動 `src/`）
> 日期：2026-08-27
> Gate：UG-Gate-2（已核准啟動，逐 SB 授權）
> 前置：UG-G2-SB2（CLOSED，`543beb4`）、UG-G2-SB3（CLOSED，`db03541`）

---

## 0. 摘要

Master Plan 的 `UG-G2-SB4` Brief（已於 SB3 結案時補正）要求本 SB **先接線、後算特徵**。
本次重新核對現況時，除了已登記的兩項待辦（接線缺口、`push_count` 雙語意陷阱）之外，
**又發現三個 Gate 0 契約未涵蓋的缺口**，其中 §1.3 是**前視偏誤（Look-ahead Bias）**問題，
直接觸及 `CLAUDE.md` §7.4 的工程不變量，**必須在寫任何特徵公式之前先決定怎麼處理**——
公式本身（`FEATURE_REGISTRY.md` §5.1~§5.4）已由 Gate 0 核准、無需重新設計，
真正的風險不在算式，而在**餵進算式的數字是哪一天的**。

---

## 1. Current State（重新對實際檔案核對）

### 1.1 接線缺口（已登記，本次確認仍然成立）

`grep -rn "parse_article_comments" src/ main_etl_pipeline.py` 僅命中定義本身。
`run_ptt_pipeline()` 現行流程仍是
`scrape_ptt_stock_by_keyword() → clean_ptt_data() → upsert_to_market_articles()`，
全程不進內頁。`market_articles` 的四個留言計數欄目前全為 `NULL`。

### 1.2 讀取路徑也沒接（**新發現，本次核對才看到**）

即使寫入端接好，特徵端仍拿不到資料——`db_writer.fetch_all_for_features()`（L429）的
SQL 是：

```sql
SELECT article_id, post_time, fetch_keyword, sentiment_score
FROM market_articles WHERE sentiment_score IS NOT NULL;
```

**四個留言計數欄根本不在 SELECT 清單裡**。SB3 已登記的待辦只提到「寫入端接線」，
漏了讀取端；本 SB 兩端都要改，否則接線完成後 `feature_aggregator` 依然看不到留言資料。

附帶注意：`WHERE sentiment_score IS NOT NULL` 使留言特徵**隱性耦合於 NLP 完成度**——
一篇已解析留言但 NLP 尚未跑完的文章，其留言計數不會進入特徵計算。這是既有查詢的行為，
非本 SB 引入，但會影響留言特徵的實際覆蓋率，應在 Gate B 明確揭露。

### 1.3 【最嚴重】留言計數是「爬取當下快照」，卻被歸屬到「發文交易日」——前視偏誤風險

> ⛔ **本節的判準框架有誤，已由 PO 於 Gate A 審查時修正——請先讀 §14.1 再讀本節。**
> 本節把「留言數不是發文當天數的」直接等同於洩漏，這個等式**不成立**：Roll-Forward
> Mapping 本來就會把週五盤後與週末的文章歸屬到週一，週一早上爬到的留言數是週一決策時點
> 當下真實可見的數字，屬合法特徵。正確判準與修正後的結論（含「大量 NULL」預期為誤判）
> 見 §14.1，本節原文保留以呈現推理過程。

這是本次核對最重要的發現，也是唯一一個會讓**特徵本身在方法論上不成立**的問題。

**機制**：

| 事件 | 時間 | 系統紀錄 |
|------|------|---------|
| 文章發布 | T 日 | `post_time = T` |
| 首次爬取（列表頁） | T 日 | 文章寫入，四個留言計數欄 `= NULL` |
| 留言計數回填（獨立 `UPDATE` 路徑，§2.3） | **T+3 日**（或任何之後的時點） | `total_comments = <T+3 當下的累計留言數>` |
| 特徵聚合 | 任意時點 | `assign_trading_days_to_articles()` 依 `post_time` 把該文章歸屬到**交易日 T** |

結果：**T+3 才存在的留言數，被當成 T 日的特徵值**。若模型用 T 日特徵預測 T+1 漲跌，
它使用了 T+1、T+2、T+3 才發生的資訊——這正是 `CLAUDE.md` §7.4「必須防止 Look-ahead Bias」
與 DEC-011（Purged Walk-Forward）整套機制要防的東西，只是這次從**資料擷取時點**這條路徑進來，
Purge／Embargo 完全攔不到（它們處理的是標籤與訓練集的邊界，不是特徵值本身的時點污染）。

**而且目前無法量測嚴重程度**：`market_articles` **沒有任何欄位記錄「留言計數是何時擷取的」**
（`VERIFIED` — `grep scraped_at|parsed_at` 於 `schema.sql`／三個 migration／
`MULTI_SOURCE_DATA_CONTRACT.md` 全部零命中；`created_at` 記的是文章列的插入時間，
不是留言回填時間）。也就是說，就算接受這個偏誤，也**無法計算它有多大**、
無法在評估時把受污染的樣本標記出來。

情緒分數（`sentiment_score`）沒有同樣問題：它由 NLP 對**標題**計算，標題在 T 日就已定案，
之後不會變。留言數會持續累積，是本質不同的時間性質。

### 1.4 留言計數與題材溢出（DEC-009）的交互作用未定義（新發現）

`daily_ml_features` 的留言特徵是 **per (trade_date, stock_id)**，但 `push_count` 等是
**per article**，中間必須有聚合步驟。而本專案的文章→股票映射有兩條路徑（DEC-009）：

| 路徑 | 既有前例（`feature_aggregator.py`） |
|------|-------------------------------------|
| 直接個股文章 | `direct_count` |
| 題材溢出文章（一篇文章對應多檔成分股，含 `relevance_weight`） | `theme_count` |

既有兩個欄位處理方式**並不一致**：`article_count = direct_count + theme_count`（未加權直接相加，
L333）；`sentiment_mean` 走 70/30 動態加權融合（`_fuse_sentiment()`）。

**`FEATURE_REGISTRY.md` §5.1~§5.4 的四條公式只寫「當日推文數 push_t」，沒有定義
題材溢出文章的留言數要不要算進成分股、要不要乘 `relevance_weight`**
（`VERIFIED` — 全 `doc/upgrade/contracts/` grep「留言.*溢出」「comment.*theme」零命中）。
這會直接改變數值：一篇矽光子熱門文章有 500 則留言，若無條件計入 4 檔成分股，
每檔的 `comment_volume_ratio` 都會被同一篇文章灌爆。

### 1.5 已登記的 `push_count` 雙語意陷阱（SB3 登記，本次確認仍成立）

scraper 層 `push_count` 是列表頁徽章字串（「爆」「X3」），DB 層是 `INTEGER`。
Master Plan 的 SB4 Brief 已有警告區塊。本 SB 接線時必須確保寫進 DB 的是
`parse_article_comments()` 回傳的內頁解析結果，不是 scraper 的原始 DataFrame。

---

## 2. Requirement Source

- `doc/upgrade/contracts/FEATURE_REGISTRY.md` §5.1~§5.4（四條公式，已核准）、§5A.5（NULL 語意對上游的約束）
- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §2.3（留言回填走獨立 `UPDATE` 路徑）、§3.5（Failure Semantics）
- `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §8 `UG-G2-SB4` Brief（SB3 結案時補正之版本）
- `CLAUDE.md` §7.4（Look-ahead Bias 防護）、§7.1（失敗不得偽裝成空結果）
- `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-002（PTT Rate Limit，`OBSERVED`）

---

## 3. Proposed Change（依 §6 決策點結果調整）

1. **寫入端接線**：`run_ptt_pipeline()` 於列表頁爬取後，對各篇文章呼叫
   `parse_article_comments()`，經獨立 `UPDATE ... WHERE url=...` 路徑寫回四個計數欄
   （§2.3 契約，不併入 `upsert_to_market_articles()` 的 `ON CONFLICT`）。
2. **讀取端補齊**：`fetch_all_for_features()` 的 SELECT 補上四個留言計數欄。
3. **聚合層**：`feature_aggregator.py` 依 §6 決策點 2 之裁決，將 per-article 計數聚合為
   per (trade_date, stock_id)，再套用 `FEATURE_REGISTRY.md` §5.1~§5.4 四條公式。
4. **前視偏誤處置**：依 §6 決策點 1 之裁決實作。
5. **NULL 語意**：依 §5A.5，raw 層 `NULL`（尚未解析）→ 三個留言特徵一律 `NULL`，
   不得補 0 或中立值；暖機期不足（`comment_volume_ratio` 首日、`net_push_momentum` 首日）
   同樣保持 `NULL`。

---

## 4. Risks & Trade-offs

| 風險 | 說明 | 因應 |
|------|------|------|
| **前視偏誤（§1.3）** | 若不處理，本 SB 產出的三個特徵在方法論上不成立，且會污染 Gate 3 之後所有使用 `COMMENT_ENHANCED_19` 的模型評估結果 | §6 決策點 1；**本提案立場：這不是可以「先做再說」的項目** |
| RISK-002（`OBSERVED`） | 接線後每篇文章多一次內頁請求 | §6 決策點 4（節流策略）；`UG-G2-SB2` 已在 `parse_article_comments()` 內建 1.5~3.5 秒延遲，是否足夠需明確評估 |
| 留言特徵覆蓋率可能極低 | 受 §1.2 的 `sentiment_score IS NOT NULL` 耦合 + 歷史文章全為 `NULL` 影響，短期內大量樣本的三個特徵會是 `NULL` | 與 RISK-015（情緒覆蓋率）同一類問題；Gate B 需實測回報覆蓋率，不得只回報「公式正確」 |

---

## 5. In / Out of Scope

**In Scope**：寫入端接線（含 §6 決策點 3 的失敗語意、決策點 4 的節流）；讀取端
`fetch_all_for_features()` 補欄；per-article → per-(date, stock) 聚合（決策點 2）；
`FEATURE_REGISTRY.md` §5.1~§5.4 四條公式實作；§6 決策點 1 之前視偏誤處置。

**Out of Scope**：NLP 情緒重算；新增模型訓練；Dcard/Threads 留言（`UG-G2-SB5`）；
`COMMENT_ENHANCED_19` 契約本身的模型輸入切換（屬 Gate 3）。

---

## 6. PO 決策點

### 決策點 1【最重要】：§1.3 前視偏誤如何處置

- **選項 A（新增擷取時點欄位，本提案建議）**：`market_articles` 新增
  `comments_scraped_at TIMESTAMP`（Migration 004），回填留言計數時一併寫入擷取時點；
  特徵聚合時**只採用 `comments_scraped_at` 落在該交易日收盤前的留言計數**，
  其餘視為「該交易日當下未知」→ 三個特徵 `NULL`。
  代價：需要多一個 Migration；且在系統每日固定排程尚未穩定運作前，
  幾乎所有歷史文章都會落在「當下未知」而產生大量 `NULL`——但這是**誠實的 `NULL`**，
  比一個看似有值、實際偷看未來的數字好。
- **選項 B（接受偏誤但明確標註）**：不新增欄位，照 `post_time` 歸屬，
  但在 `FEATURE_REGISTRY.md` 與 DEC 中明確記載「本特徵含已知擷取時點偏誤，
  不得用於 Gate 3 之後的正式回測績效宣稱」。代價：`COMMENT_ENHANCED_19` 契約
  等同帶著一個已知缺陷進入 Gate 3。
- **選項 C（延後整個 SB4）**：先不做留言特徵，等每日排程穩定（爬取時點≈發文時點）後再做。

**本提案建議選項 A**，理由：`CLAUDE.md` §7.4 是工程不變量，且本專案已為此投入
DEC-011 整套 Purged Walk-Forward 機制；在同一個專案裡一邊嚴防標籤洩漏、
一邊放行特徵時點污染，是不一致的。**但選項 A 會擴大本 SB 範圍（多一個 Migration），
需要你明確核准。**

### 決策點 2：題材溢出文章的留言計數如何聚合（§1.4）

- **選項 A（比照 `article_count`，未加權相加）**：溢出文章的留言數直接計入所有成分股。
  最簡單，但一篇熱門題材文章會同時灌大所有成分股的留言量。
- **選項 B（比照 `sentiment_mean`，加權）**：溢出部分乘 `relevance_weight` 後計入。
  與情緒欄位的既有處理一致。
- **選項 C（只算直接文章）**：留言特徵只採用直接個股文章的留言，題材文章不計入。
  數值最保守、語意最乾淨（「這檔股票本身被討論的留言熱度」），但會讓小型概念股的
  留言特徵大量為 `NULL`（與 RISK-015 的擔憂同向）。

本提案**傾向選項 C**（語意最明確、不會讓單一熱門文章跨股灌水），但這會影響覆蓋率，
與 RISK-015 的評估直接相關，請你裁決。

### 決策點 3：單篇內頁請求失敗（`SOURCE_DEGRADED`）時的處置

該篇文章的留言計數保持 `NULL`（文章本身已寫入，僅計數欄留空）——本提案建議此做法，
與 §5A.5 的 `NULL` 語意一致，且不影響同批其他文章。請確認是否同意，
或希望改為「整篇文章跳過不寫入」。

### 決策點 4：請求量節流策略

`parse_article_comments()` 已內建 1.5~3.5 秒延遲（`UG-G2-SB2`）。接線後每日請求量
≈ 追蹤關鍵字數 × 每關鍵字文章數。是否需要額外設定「每次執行的內頁請求上限」
（例如只回填最近 N 天內、或每次最多 M 篇），避免單次執行對 PTT 產生過大流量？

---

## 7. Affected Components

`main_etl_pipeline.py`（接線）、`src/loaders/db_writer.py`（讀取端補欄 + 留言計數
`UPDATE` 路徑）、`src/transform/feature_aggregator.py`（聚合 + 四條公式）；
依決策點 1 結果，可能新增 `database/migrations/004_*.sql` 與對應 Schema 變更。

---

## 8. Tests

- `test_comment_volume_ratio_uses_rolling_baseline`（Master Plan 既定名稱）
- `test_polarization_boundary`（既定名稱，含 `push_ratio` 值域邊界）
- `test_momentum_is_delta_not_ratio`（既定名稱）
- `test_null_when_no_comments`（既定名稱，對應 §5A.5）
- `test_comment_counts_reach_market_articles`（**接線實證**，對應 Brief 的 Definition of Done）
- `test_fetch_all_for_features_includes_comment_columns`（§1.2 讀取端缺口迴歸）
- 依決策點 1 結果：前視偏誤防護的 known-FAIL 案例（構造一筆「擷取時點晚於交易日」的資料，
  確認該筆特徵為 `NULL` 而非被計入）
- 依決策點 2 結果：題材溢出聚合的對應斷言

---

## 9. E2E Verification Plan

比照 `UG-G2-SB1`／`SB3`：獨立隔離臨時 DB（非 `postgres-data` 掛載），
需 PO 依 RISK-013 協定確認綁定目標後才可執行。驗證項目除 Schema 外，
**必須包含「接線後留言計數確實進入 `market_articles`」與「特徵確實由真實留言數算出」的
端到端實證**（Brief 的 Definition of Done 明確要求，不接受只驗證公式）。
若涉及真實 PTT 請求，比照 `UG-G2-SB2` 慣例：程式碼先經審查員複查、PO 核准後才執行。

---

## 10. Documentation Sync

`FEATURE_REGISTRY.md`（三項特徵狀態由 `PLANNED` 更新；依決策點 1／2 結果補上時點語意與
溢出聚合規則——**這兩項目前契約皆未定義，本 SB 會是它們的首次落定**）；
依決策點 1 結果可能需新增 DEC；`PROJECT_STATUS.md`。

---

## 11. Rollback

見 `DB_MIGRATION_PLAN.md` §7；若決策點 1 採選項 A，新增的 Migration 為純加法 DDL，
L1～L4 已足夠因應。

---

## 12. Definition of Done

- 接線完成，**留言計數實證進入 `market_articles`**（非僅能力就緒）。
- 讀取端補欄完成，`feature_aggregator` 實際取得留言資料。
- 三項特徵可重算，公式與 `FEATURE_REGISTRY.md` §5.1~§5.4 一致。
- 無留言／未解析／暖機期不足時保持 `NULL`（§5A.5），不補 0 或中立值。
- 依決策點 1 之裁決完成前視偏誤處置，並附 known-FAIL 案例。
- §8 測試 PASS；契約驗證與既有測試無回歸。
- Gate B 實測回報留言特徵的**實際覆蓋率**（多少比例的 (date, stock) 有非 NULL 值），
  不得只回報公式正確。

---

## 13. 待 PO 裁決事項彙總

1. **決策點 1【最重要】**：§1.3 前視偏誤處置——選項 A（新增 `comments_scraped_at` + 時點過濾，**建議**，但擴大範圍需核准）／選項 B（接受並標註）／選項 C（延後 SB4）。
2. **決策點 2**：題材溢出文章的留言計數聚合——未加權相加／加權／只算直接文章（**傾向後者**）。
3. **決策點 3**：單篇內頁失敗時該篇留言計數保持 `NULL`（**建議**）是否同意。
4. **決策點 4**：是否需要額外的內頁請求量上限。
5. 是否核准依 §5 範圍開始實作。

---

## 14. PO 核准與修正記錄（2026-08-28）

### 14.1 §1.3 判準框架修正【本次最重要的修正】

**本提案 §1.3 的判準有誤。** 正確判準不是「留言數是不是發文那天數的」，而是：

> **這個數字，在它被歸屬的那個交易日的決策時點，是不是已經看得到了？**

**為什麼原判準不成立**：Roll-Forward Mapping（`assign_trading_days_to_articles()`）
本來就會把週五盤後、週六、週日的文章歸屬到**週一**。因此週一早上爬到那篇週六文章有
500 則留言——那是**週一決策時點當下真實可見**的數字，拿它當週一的特徵完全合法，不是洩漏。
更進一步：模型本來就應該學到「假日後的開盤日，留言數天生比平日多」——那是真實存在、
每週重複、預測當下確實可得的規律；把它當污染抹掉等於丟掉有效訊號。
原提案把「留言數不是發文當天數的」直接等同於洩漏，這個等式不成立，因為
**文章歸屬的交易日本來就常常不是發文那天**。

**修正框架後，真正的洩漏只剩兩種情況**：

| # | 情況 | 說明 |
|---|------|------|
| 1 | **舊文章被重複爬取並覆寫**（主要問題） | `search?q={keyword}` 每次回傳最近約 20 篇、橫跨數日。三天前那篇今天又被抓一次，`UPDATE` 把留言數覆寫成**今天**的累計值，寫進的卻是**三天前**那個交易日的列——這才是真的偷看未來 |
| 2 | 歷史文章的第一次爬取（回填期） | 系統尚未開始跑、或新增追蹤關鍵字時，今天第一次抓到四天前的文章——即使不覆寫，這第一次的值也已經晚了四天 |

**`write-once` 是核心修法，不只是可重現性問題**：在穩定的每日排程下，一篇文章的
**第一次爬取本來就發生在它所歸屬的那個交易日的決策時點**。只要不覆寫，第一次拿到的值
就是正確時點的值——`write-once` 直接消滅情況 1。

**「大量 NULL」的預期為誤判**：本提案 §6 決策點 1 寫「短期內會產生大量 NULL」，
在修正框架下**只對回填期成立**。穩定運作後，每篇文章的第一次爬取天然滿足時點條件，
`NULL` 應為少數而非多數；大量 `NULL` 只出現在系統開始運作之前的歷史資料上——
那部分本來就沒救，標 `NULL` 是誠實。因此 `comments_scraped_at` 的角色**不是**
「過濾掉大部分資料的篩子」，而是**驗證對齊的稽核欄位**，順便把回填期無法對齊的舊資料
誠實標記出來。**實作時不得因為預期「反正大部分都會是 NULL」而寫得過度保守。**

**cutoff 模式的例外**（實作時須知道機制在保護什麼，但不需寫特例）：

| Cutoff | 週五 10:00 的文章歸屬 | 週一早上爬到的 500 則 |
|--------|---------------------|---------------------|
| `15:30`（`main_etl_pipeline.py` L131-133 未傳參數，production 實際走此預設值） | 週五 | ❌ 洩漏（週五收盤時只有 50 則） |
| `08:30`（盤前模式） | 週一 | ✅ 合法 |

`comments_scraped_at` 的時點比對會自動處理這個差異，無需為 cutoff 模式寫特例邏輯。

### 14.2 五項裁決

1. **決策點 1**：**選項 A**，但定義修正為「`comments_scraped_at` **+ 留言計數 write-once**」
   （`UPDATE ... WHERE url=... AND total_comments IS NULL`，已有非 `NULL` 值者不再覆寫），
   且預期改為「穩定運作下 `NULL` 為少數」。**核准擴大範圍（Migration 004）**。
2. **決策點 2**：**選項 C（只算直接文章）**。PO 補充的理由比本提案原本寫的更強：
   `comment_polarization` 與 `net_push_momentum` **都是 `push_ratio` 的函數**，一篇矽光子
   文章的留言若計入 4 檔成分股，這 4 檔的這兩個特徵會**幾乎完全相同**——模型會看到 4 筆
   看似獨立、實則同源的樣本，這**不只是稀疏，是製造假的相關性，比 `NULL` 有害**。
   另外 DEC-009 對情緒走 70/30 是合理的，因為**情緒是方向訊號可以外溢**；
   **留言數量是量級**，「這篇題材文有 500 則留言」不等於「每檔成分股各獲得 500 則討論」，
   性質不同，不該套用同一個先例。
3. **決策點 3**：同意——單篇內頁失敗時該篇留言計數保持 `NULL`、文章本身照寫。
4. **決策點 4**：需要控制，但**先做兩件零成本的事**：
   - **(a) 整批 URL 去重再抓內頁**——同一篇文章會出現在多個關鍵字的搜尋結果裡
     （「台積電」與「AI」可能撈到同一篇），本提案漏了這點。
   - **(b) `write-once` 之後，已有計數的文章直接跳過。**

   粗估目前 6 關鍵字 × 20 篇 = 120 次內頁請求、每篇 2.5–6 秒，總計 5–12 分鐘，
   **已超過 RISK-005 的「ETL > 5 分鐘」觸發條件**；做完去重與跳過後，穩定期每天只需抓新文章，
   請求量會大幅下降。做完這兩項再評估是否還需要硬性上限。
5. 核准依 §5 範圍開始實作（含 Migration 004）。

### 14.3 決策紀錄義務（兩處都要，PO 明確要求）

- **`doc/evidence/DECISIONS.md` 新增一則 ADR**：記錄「留言計數的時點有效性判準」。
  Context 須完整寫下推理過程——包含最初判斷為根本性缺陷、釐清 Roll-Forward 歸屬後
  發現正常運作下天然正確、以及 `write-once` 為何是核心修法。
  **此判準會約束未來所有時間性會變動的特徵**（Dcard 留言、按讚數等），非一次性決定。
- **`doc/upgrade/contracts/FEATURE_REGISTRY.md`**：時點語意與題材溢出聚合規則
  （決策點 2 的裁決）須寫進**契約本文**——本提案 §10 已寫「本 SB 會是它們的首次落定」，
  那就要真的落定，不能只留在 ADR 裡。
