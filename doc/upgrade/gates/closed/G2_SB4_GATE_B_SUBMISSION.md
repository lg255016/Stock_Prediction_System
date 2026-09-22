# UG-G2-SB4 Gate B 送審文件：留言接線與衍生特徵計算

> 狀態：**待 PO 審查**
> 日期：2026-08-28
> 對應提案：`doc/upgrade/gates/G2_SB4_GATE_A_PROPOSAL.md`（已核准，含 §14 判準修正與五項裁決）

---

## 1. 摘要

依核准之 §5 範圍（含 §14.2 五項裁決）完成實作：Migration 004（`comments_scraped_at`）、
留言計數 `write-once` 回填路徑、`main_etl_pipeline` 接線（含 URL 去重與跳過已有計數）、
`fetch_all_for_features()` 讀取端補欄、三個留言衍生特徵（只採直接個股文章）。
新增 DEC-024（時點有效性判準）與 DEC-025（聚合範圍），並將兩者寫入
`FEATURE_REGISTRY.md` §5.5／§5.6 契約本文。

隔離臨時 DB 完成端到端實證：**留言計數確實進入 `market_articles`，三個特徵確實由
DB 裡的真實留言數算出**（非僅公式驗證），並實測回報覆蓋率。

---

## 2. Diff 摘要（10 個檔案：6 modified + 4 new）

| 檔案 | 異動類型 | 行數（+/-） |
|------|---------|-------------|
| `database/migrations/004_comment_scrape_timestamp.sql` | 新增 | +44 / -0 |
| `doc/evidence/DECISIONS.md` | 修改（DEC-024、DEC-025） | +171 / -0 |
| `doc/upgrade/contracts/FEATURE_REGISTRY.md` | 修改（§5.5、§5.6 契約本文） | +46 / -0 |
| `doc/upgrade/gates/G2_SB4_GATE_A_PROPOSAL.md` | 新增（提案 + §14 修正記錄） | +346 / -0 |
| `doc/upgrade/gates/G2_SB4_GATE_B_SUBMISSION.md` | 新增（本文件） | — |
| `main_etl_pipeline.py` | 修改（接線 + 去重 + 跳過） | +49 / -0 |
| `src/loaders/db_writer.py` | 修改（write-once、待回填查詢、讀取端補欄、`fetch_data` params） | +72 / -3 |
| `src/transform/feature_aggregator.py` | 修改（聚合 + 時點過濾 + 三特徵） | +146 / -1 |
| `tests/test_comment_features.py` | 新增（13 個測試） | +284 / -0 |
| `tests/test_feature_aggregator_alignment.py` | 修改（NaN 比較修正，見 §9.1） | +10 / -2 |

---

## 3. 產出 1：契約驗證原始輸出

```bash
$ python scripts/verify/gate0_contract_check.py
...
Part B: 11/11 PASS
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂
```

---

## 4. 產出 2：執行環境、測試原始輸出

**Host（Windows，非支援環境，Python 3.10.11）**：

```bash
$ PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -p "test_*.py"
Ran 238 tests in 2.862s
OK
```

238 = 原 225 + 13 個本 SB 新增測試（`tests/test_comment_features.py`）。

---

## 5. 產出 3：E2E 驗證（隔離臨時 DB，非 `postgres-data` 掛載）

### 5.1 RISK-013 綁定確認（PO 已核可，並自行以 `assert_safe_migration_target()` 實測 `GUARD RESULT: PASS`）

```
db_config: {'host': 'g2sb4_comments_tmpdb', 'port': 5432,
            'database': 'g2sb4_comments_tmpdb', 'user': 'tmpuser', 'password': 'tmppass'}
BINDING（DB 端自陳）: ('g2sb4_comments_tmpdb', 'tmpuser', 5432)
```

驗證後已 `docker rm -f` 拆除。

### 5.2 Migration 004 套用與 Schema 驗證

```
[apply_migrations] v1 → v2 → v3 → v4 皆已套用並 COMMIT。完成，已套用至 v4。

COMMENT COLUMNS（column_default 必須全為 None）：
   ('push_count', 'integer', None)
   ('boo_count', 'integer', None)
   ('neutral_count', 'integer', None)
   ('total_comments', 'integer', None)
   ('comments_scraped_at', 'timestamp without time zone', None)   ← 無 DEFAULT，符合設計
TOTAL COLUMN COUNT: 16
CHECK CONSTRAINTS: [('chk_comment_counts_nonneg',), ('chk_comments_scraped_at_consistency',)]
SCHEMA_VERSION: v1 / v2 / v3 / v4
```

冪等性：重跑 `apply_migrations.py` → `目前已套用版本：v4` / `無待執行遷移，已是最新版本。`

### 5.3 【DoD 要求】端到端實證：接線後留言計數確實進入 `market_articles`

走**真實**程式碼路徑（`clean_ptt_data` → `upsert_to_market_articles` →
`backfill_ptt_comment_counts` → 去重 → `fetch_articles_missing_comment_counts` →
`update_comment_counts`）與**真實** PostgreSQL；唯一以 stub 取代的是
`parse_article_comments()` 的網路請求本身（該函式對真實 PTT 網站的解析正確性已於
`UG-G2-SB2` 驗證過，見該 SB 的 Gate B §5.2）。

```
--- 第一次 backfill（傳入 4 個 URL，其中第一篇刻意重複）---
[Extract] 準備解析 3 篇文章內頁留言...
[Load] 準備回填 3 筆留言計數至 market_articles（write-once）...
[Load] 成功執行資料庫作業。已處理 3 筆資料。
內頁請求次數 = 3 （4 個 URL 去重後為 3 篇 → 決策點 4(a) 生效）

留言計數已進入 market_articles（title, push, boo, total, scraped_at IS NOT NULL）：
  ROW: ('文章1', 5, 1, 10, True)
  ROW: ('文章2', 20, 2, 30, True)
  ROW: ('文章3', 30, 5, 50, True)
```

### 5.4 `write-once` 真實 DB 實證（DEC-024 核心修法）

第二次 backfill 對同樣三個 URL，且**把 stub 回傳值改為 999**：

```
--- 第二次 backfill（數字已改為 999）---
[Extract] 留言計數已存在，跳過 3 篇（write-once，DEC-024）。
內頁請求次數 = 0 （全部已有計數 → 決策點 4(b) 生效，連請求都不發）
第一篇 write-once 後（應仍為 5 / 10，不是 999）： (5, 10)
```

兩層防護皆實證有效：呼叫端跳過（不發請求）+ SQL 層 `AND total_comments IS NULL`（不覆寫）。

### 5.5 【DoD 要求】三個特徵確實由 DB 裡的真實留言數算出

`fetch_all_for_features()` 取回的文章欄位（讀取端缺口已補）：

```
['article_id', 'post_time', 'fetch_keyword', 'sentiment_score',
 'push_count', 'boo_count', 'neutral_count', 'total_comments', 'comments_scraped_at']
```

由 DB 真實資料（push/boo/total = 5/1/10、20/2/30、30/5/50）算出：

| trade_date | comment_volume_ratio | comment_polarization | net_push_momentum |
|-----------|---------------------|---------------------|------------------|
| 2026-08-24 | `NaN`（暖機期無前日基準） | 0.673469 | `NaN`（無前日 push_ratio） |
| 2026-08-25 | 2.727273 | 0.387524 | 0.211180 |
| 2026-08-26 | 2.380952 | 0.517747 | -0.088164 |

**人工獨立核算對照**（不呼叫被測程式碼，另行以公式手算）：

```
day1: volume_ratio=None,              polarization=0.673469, momentum=None
day2: volume_ratio=2.727272727272727, polarization=0.387524, momentum=0.21118012422360255
day3: volume_ratio=2.380952380952381, polarization=0.517747, momentum=-0.08816425120772953
```

**逐項相符**（`comment_volume_ratio` 的分母確認只用 t-5..t-1：
day2 = 30/(10+1)、day3 = 50/(mean(10,30)+1)，**不含當日**）。

### 5.6 DEC-024 時點過濾的真實 DB 實證

把 `comments_scraped_at` 改為「隔日 09:00」（晚於各自交易日 15:30 決策時點）後重跑：

```
改為隔日擷取後： post_time=2026-08-24 10:00, comments_scraped_at=2026-08-25 09:00

trade_date  comment_volume_ratio  comment_polarization  net_push_momentum
2026-08-24  NaN                   NaN                   NaN
2026-08-25  NaN                   NaN                   NaN
2026-08-26  NaN                   NaN                   NaN
```

同一批留言計數，僅因擷取時點晚於決策時點即全部轉為 `NULL`——時點過濾在真實 DB 路徑
上確實生效，非僅單元測試層面。

### 5.7 `chk_comments_scraped_at_consistency` 實證

```
UPDATE market_articles SET comments_scraped_at = NULL WHERE total_comments IS NOT NULL;
→ ENFORCED: new row for relation "market_articles"
   violates check constraint "chk_comments_scraped_at_consistency"
```

---

## 6. 【DoD 要求】留言特徵實際覆蓋率實測

| 情境 | `comment_volume_ratio` | `comment_polarization` | `net_push_momentum` |
|------|----------------------|----------------------|-------------------|
| 留言計數齊備且時點合法（§5.5） | 2/3 = **66.7%** | 3/3 = **100%** | 2/3 = **66.7%** |
| 留言計數時點不合法（§5.6，模擬回填期） | 0/3 = **0%** | 0/3 = **0%** | 0/3 = **0%** |

**覆蓋率的正確解讀（重要，避免誤判）**：

- 上表是**受控合成資料**的覆蓋率，**不是**真實 Universe 的覆蓋率宣稱。
- `comment_volume_ratio` 與 `net_push_momentum` 的 66.7% 是**暖機期造成的結構性缺口**
  （首日無前日基準／無前日 `push_ratio`），非資料不足——樣本數越長，此比例越接近 100%。
- **真實覆蓋率無法在本 SB 量測**：需要系統實際每日運作累積資料後才有意義，
  且會同時受 DEC-025（只算直接個股文章）與 `WHERE sentiment_score IS NOT NULL`
  兩個條件壓低。此為 RISK-015 於 Gate 3 啟動前正式檢視的範圍，**本 SB 標記為
  `NOT VERIFIED`**，不以合成資料的數字冒充真實覆蓋率。

---

## 7. 產出 4：格式／行尾夾帶偵測

```bash
$ git diff --numstat > raw.txt && git diff --numstat -w > nows.txt && diff raw.txt nows.txt
（無輸出）
DIFF_EXIT=0
```

**本次零落差**，10 個檔案皆無純空白差異。（依 PO 要求，此項已於實作完成回報時
主動附上，非等到 Gate B 文件。）

---

## 8. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 說明 |
|------|---------|-------------------|
| Migration 004 套用成功且冪等 | `VERIFIED THIS SESSION` | §5.2（container，`g2sb4_comments_tmpdb`，已拆除） |
| `comments_scraped_at` 無 `DEFAULT` | `VERIFIED THIS SESSION` | §5.2，`information_schema.columns.column_default = None` |
| 接線後留言計數確實進入 `market_articles` | `VERIFIED THIS SESSION` | §5.3，真實 DB 查詢結果 |
| URL 去重生效（決策點 4a） | `VERIFIED THIS SESSION` | §5.3，4 個 URL → 3 次請求 |
| `write-once` 兩層防護生效 | `VERIFIED THIS SESSION` | §5.4，第二次 backfill 0 次請求、值未被 999 覆寫 |
| 三特徵由真實 DB 留言數算出且與人工核算相符 | `VERIFIED THIS SESSION` | §5.5，逐項對照 |
| DEC-024 時點過濾在真實 DB 路徑生效 | `VERIFIED THIS SESSION` | §5.6 |
| `chk_comments_scraped_at_consistency` 生效 | `VERIFIED THIS SESSION` | §5.7 |
| 全套測試 238/238 OK（host） | `VERIFIED THIS SESSION` | §4 |
| `parse_article_comments()` 對真實 PTT 網站的解析正確性 | `PREVIOUSLY VERIFIED` | `UG-G2-SB2` Gate B §5.2（commit `543beb4`）；本次 E2E 以 stub 取代該網路請求，未重跑 |
| **真實 Universe 的留言特徵覆蓋率** | **`NOT VERIFIED`** | 見 §6：需系統實際運作累積資料後才可量測，屬 RISK-015 於 Gate 3 啟動前的檢視範圍 |

---

## 9. 產出 6：Known-FAIL 案例對照表

| # | 檢查 | Known-FAIL 案例 | 實測結果 | 復原確認 |
|---|------|-----------------|---------|---------|
| 1 | DEC-024 時點過濾 | 移除 `df = df[df['comments_scraped_at'] <= decision_point]` | `test_comment_count_scraped_after_decision_point_is_excluded` **FAIL**（`False is not true`）；**互補測試 `..._is_used` 仍 PASS**——同時證明過濾器承重、且互補測試不是靠「反正全部排除」蒙混 | 已還原；`grep KNOWN-FAIL` 無殘留；238/238 OK。PO 亦獨立重現 |
| 2 | `write-once` | 移除 `AND market_articles.total_comments IS NULL` | `test_update_comment_counts_is_write_once` **FAIL**（條件字串不在 query 中） | 已還原；PO 亦獨立重現 |
| 3 | `chk_comments_scraped_at_consistency` | 對真實 DB 執行 `SET comments_scraped_at = NULL WHERE total_comments IS NOT NULL` | `CheckViolation` | 該筆已 `rollback()` |
| 4 | 時點過濾（真實 DB 路徑） | 將 `comments_scraped_at` 改為隔日 09:00 後重跑特徵聚合 | 三特徵全部轉為 `NaN`（§5.6） | 容器已拆除 |

---

## 10. 與提案的差異／需揭露事項

### 9.1 修改了既有的前視偏誤防護測試（已於實作回報時說明，此處存檔）

`tests/test_feature_aggregator_alignment.py::test_future_data_mutation_does_not_alter_past_features`
原本以 `assertEqual` 逐欄比對 base 與 mutated 的特徵值。三個留言特徵在無留言資料時
**合法地**為 `NaN`，而 `NaN != NaN`，導致「兩邊都正確地是 `NULL`」被誤判為洩漏。

已改為：**僅當兩邊皆為 `NaN` 時 `continue`**；若基準為 `NaN` 而變異後變成數字
（真的洩漏了），`assertEqual` 照樣執行、照樣失敗，反之亦然。
**這是修掉 `NaN != NaN` 的比較方式瑕疵，不是放寬檢查。** PO 已逐行複查確認。

### 9.2 `parse_article_comments()` 的網路請求在本次 E2E 以 stub 取代

理由與邊界見 §5.3 與 §8 證據標籤表。本 SB 驗證的是**接線與資料流**，
內頁解析對真實 PTT HTML 的正確性屬 `UG-G2-SB2` 已驗證範圍，未重複執行真實請求
（亦因此本次無需 PO 事前複查網路程式碼）。

### 9.3 `fetch_data()` 新增 `params` 參數（既有函式簽名擴充）

`fetch_articles_missing_comment_counts()` 需要 `url = ANY(%s)` 繫結查詢。
`fetch_data()` 原本不接受參數，已擴充為 `fetch_data(query, params=None)`——
既有呼叫端不傳此參數，行為完全不變。在處理外部爬取而來的 URL 的路徑上，
一律經 psycopg2 參數化，不以字串拼接組 SQL。

---

## 11. Definition of Done 對照

- [x] 接線完成，**留言計數實證進入 `market_articles`**（§5.3，非僅能力就緒）。
- [x] 讀取端補欄完成，`feature_aggregator` 實際取得留言資料（§5.5）。
- [x] 三項特徵可重算，公式與 `FEATURE_REGISTRY.md` §5.1~§5.4 一致（§5.5 人工核算逐項相符）。
- [x] 無留言／未解析／暖機期不足時保持 `NULL`，不補 0 或中立值。
- [x] DEC-024 前視偏誤處置完成，附 known-FAIL 案例（§9 #1、#4）。
- [x] DEC-025 只採直接個股文章（`tests/test_comment_features.py::ThemeSpilloverExcludedFromCommentsTests`）。
- [x] 決策點 4 兩項零成本控制（URL 去重、跳過已有計數）皆實證生效（§5.3、§5.4）。
- [x] §8 測試 PASS（238/238）；契約驗證 11/11 PASS，無回歸。
- [x] DEC-024／DEC-025 已寫入 `DECISIONS.md`；時點語意與聚合規則已寫入
      `FEATURE_REGISTRY.md` §5.5／§5.6 **契約本文**（非僅 ADR）。
- [x] Gate B 實測回報覆蓋率（§6），並明確區分合成資料覆蓋率與真實 Universe 覆蓋率
      （後者標記 `NOT VERIFIED`）。

---

## 12. 待 PO 裁決事項

1. 是否核准本次 commit（10 個檔案：6 modified + 4 new，清單見 §2）。
2. §6 對覆蓋率的處理方式（合成資料數字如實回報，真實 Universe 覆蓋率標記
   `NOT VERIFIED` 並歸入 RISK-015 於 Gate 3 前的檢視範圍）是否認可。
3. ~~決策點 4 提到「做完去重與跳過後再評估是否還需要硬性上限」~~ ——
   **PO 已裁決（2026-08-28）：不需要硬性上限。** 依 §5.3／§5.4 實證，兩層控制都生效
   （4 URL → 3 請求、第二次 backfill 0 請求），穩定期請求量會自然收斂。
   **再加硬性上限反而有害**——它會在某天文章較多時靜默丟掉資料，而那種丟失
   同樣不會有徵兆，與 DEC-024 指出的「太緊」問題屬同一類（過度保守的錯誤是沉默的）。

   > ⚠ **此決定不是永久豁免，是「目前證據支持不需要」。**
   > **若未來 RISK-002 再次被觀測到（PTT 回 429 或封鎖），此決定須重新評估。**

---

## 13. 補充：Gate 3 檢視 RISK-015 時必須併同說明的事（PO 2026-08-28 提醒）

到 Gate 3 檢視 RISK-015 時，`coverage_ratio` 量的是
**「這檔股票有沒有任何可用訊號」，不是「原生討論量有多少」**——
這個區別必須跟數字一起講，否則覆蓋率會看起來比實際健康。

成因有二，皆為已核准的設計選擇，非缺陷：

| # | 來源 | 效果 |
|---|------|------|
| 1 | `source_status = SUCCESS` 的判定（`UG-G2-SB1` 決策點 1）納入題材溢出訊號 | 只靠題材借來的訊號也算「有覆蓋」，**高估**原生討論量 |
| 2 | 留言特徵只算直接個股文章（DEC-025）＋ `WHERE sentiment_score IS NOT NULL` 耦合 | 留言特徵的覆蓋率會**低於**情緒特徵的覆蓋率 |

即：同一份資料在情緒層與留言層的覆蓋率**本來就不會相同**，且兩者衡量的東西不同。
Gate 3 的 RISK-015 評估必須分開報，不得合併成單一「覆蓋率」數字。
