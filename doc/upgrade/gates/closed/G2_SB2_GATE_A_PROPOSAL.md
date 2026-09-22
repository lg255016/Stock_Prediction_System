# UG-G2-SB2 Gate A 提案：PTT 內頁留言解析

> 狀態：**Gate A 審查中**（尚未實作，未動 `src/`）
> 日期：2026-08-27
> Gate：UG-Gate-2（已核准啟動，逐 SB 授權）
> 前置：UG-G2-SB1（`daily_ml_features` Schema 擴充）已 CLOSED（commit `ef029a6`）

---

## 0. 摘要

`src/extractors/ptt_scraper.py` 目前只做**列表頁**爬取（`scrape_ptt_stock_by_keyword`），
從 `div.nrec` 擷取的 `push_count` 只是一個彙總徽章（「爆」「數字」「X幾」），不是逐則推噓文。
本 SB 依 Gate 0 已核准的 `MULTI_SOURCE_DATA_CONTRACT.md` §3.3 進入文章**內頁**解析真正的
推／噓／→ 逐則留言，同時修正現行程式碼一個與 §3.5 Failure Semantics 直接牴觸的缺陷——
目前所有例外一律吞掉並靜默回傳部分資料，**結構上不可能產生 `SOURCE_FAILED`**。

**這也是 `UG-G2-SB1`（`source_status` 判定邏輯）留下的軟性依賴**：`SOURCE_DEGRADED`／
`SOURCE_FAILED` 兩態要能真正出現在 `daily_ml_features.source_status`，前提是本 SB 先讓
`ptt_scraper.py` 具備區分「單篇解析失敗」與「整個來源不可用」的能力
（`G2_SB1_GATE_A_PROPOSAL.md` §1.3 已預告此缺口）。

---

## 1. Current State（重新對實際檔案核對）

### 1.1 `ptt_scraper.py` 現況（`VERIFIED THIS SESSION`，全檔僅 83 行）

- 唯一方法：`scrape_ptt_stock_by_keyword(keyword, max_pages)` —— 只爬列表頁。
- `push_count`（L57-58）：`entry.find("div", class_="nrec").text.strip()`，是列表頁的彙總徽章
  字串（如「爆」「12」「X3」），**不是**進入內頁解析出的逐則推／噓／→ 計數。
- **例外處理（L79-81）**：

  ```python
  except Exception as e:
      print(f"❌ [Extract] 爬取過程發生錯誤：{e}")
      break
  ```

  所有例外類型一視同仁：印出訊息、跳出迴圈、回傳目前已收集的（可能為空的）DataFrame。
  **結構上不存在任何拋出例外的路徑**——這與 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5 要求的
  「PTT 完全不可用 → 拋出可觀測例外，不回傳空 DataFrame」直接牴觸。
- 時間解析：`src/transform/data_cleaner.py` 的 `parse_ptt_datetime()`
  **已經支援**完整時間戳記（如 `'Wed Aug 20 14:25:36 2026'`）、ISO 格式與
  `MM/DD` 跨年推論三種輸入——這個函式本身不需要新開發。問題純粹是
  `ptt_scraper.py` 目前完全不進入內頁，沒有機會把內頁 `<meta>` 的完整時間字串
  傳給這個已存在的函式，只能餵給它列表頁的 `MM/DD` 短格式。

### 1.2 下游消費者只需要「計數」，不需要留言內容（`VERIFIED THIS SESSION`）

核對 `FEATURE_REGISTRY.md` §3（`comment_volume_ratio`／`comment_polarization`／
`net_push_momentum` 三項 `COMMENT_ENHANCED_19` 特徵）的公式定義：

```
comment_volume_ratio_t = total_comments_t / (rolling_mean(total_comments, t-5..t-1) + 1)
comment_polarization_t = 1 - push_ratio_t^2
net_push_momentum_t    = push_ratio_t - push_ratio_{t-1}
```

三者皆只需要 `push_count`／`boo_count`／`neutral_count`／`total_comments` 四個**數字**，
不需要留言的實際文字內容。但 Master Plan §8 UG-G2-SB2 精簡 Brief 的 `In Scope` 欄寫著
「Top-5 高讚留言擷取」——這在 `MULTI_SOURCE_DATA_CONTRACT.md` §3.3（Gate 0 已核准之留言
解析契約）裡**完全沒有對應規格**，也沒有任何現有或計畫中的下游消費者。見 §6 決策點 1。

### 1.3 `db_writer.py` 尚無對應寫入路徑（確認非本 SB 範圍，非遺漏）

`market_articles` 目前沒有 `push_count`／`boo_count`／`neutral_count`／`total_comments`／
`provider_article_id` 欄位——這些由 `UG-G2-SB3`（`market_articles` Schema 擴充）新增。
Master Plan §8 UG-G2-SB2 精簡 Brief 的 `Affected Components` 也**不包含** `db_writer.py`，
與此一致。本 SB 的成果（`parse_article_comments()` 回傳的計數）在 `UG-G2-SB3` 完成前
**無處可寫入 DB**，這是刻意的 SB 邊界（先有解析能力，Schema 就緒後 `UG-G2-SB4` 才計算特徵），
不是本提案遺漏。

---

## 2. Requirement Source

- `doc/upgrade/contracts/MULTI_SOURCE_DATA_CONTRACT.md` §3.3（留言解析契約）、
  §3.5（Failure Semantics）、§3.6（時間解析）——Gate 0 已核准
- `doc/upgrade/contracts/FEATURE_REGISTRY.md`（`COMMENT_ENHANCED_19` 契約，下游消費者）
- `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-002（PTT Rate Limit 風險，本 SB 顯著提高
  請求量，見 §5）
- `G2_SB1_GATE_A_PROPOSAL.md` §1.3（`source_status` 四態依賴本 SB 才能完整）

---

## 3. Proposed Change

### 3.1 新增 `parse_article_comments(article_url)` 方法

進入文章內頁，解析 `<div class="push">` 區塊：

- `push-tag` 含「推」→ 累加 `push_count`
- `push-tag` 含「噓」→ 累加 `boo_count`
- `push-tag` 含「→」→ 累加 `neutral_count`
- `total_comments = push_count + boo_count + neutral_count`
- `engagement_metric`（向後相容）= `push_count - boo_count`

### 3.2 Failure Semantics 全面改寫（§3.5 逐項對應）

| 情境 | 現行行為 | 修正後行為 |
|------|---------|-----------|
| 搜尋成功但無結果 | 回傳空 DataFrame | 不變（`SUCCESS_EMPTY`，已符合契約） |
| 單篇文章解析失敗（如內頁結構異常） | 整批 `break`，遺失後續文章 | `except` 僅捕捉該篇，記錄 warning，**繼續處理下一篇**（`SOURCE_DEGRADED`） |
| 整頁列表抓取失敗（3 次重試耗盡） | `break`，回傳部分資料，無警告分類 | 回傳已收集的部分資料 + 明確 `SOURCE_DEGRADED` 標記／log |
| PTT 完全不可用（連線失敗、認證失效等） | 同上，被同一個 `except Exception` 吞掉 | **拋出可觀測例外**（新增 `PttSourceUnavailableError`），不回傳空 DataFrame |

關鍵設計：現行單一 `except Exception` 需拆分為至少兩層——「這篇文章解析失敗」（可續爬，
`SOURCE_DEGRADED`）與「整個來源不可達」（不可續爬，`SOURCE_FAILED`，向上拋出）。

### 3.3 內頁時間戳記接線（§3.6，非新開發解析邏輯）

`data_cleaner.py` 的 `parse_ptt_datetime()` 已支援完整時間戳記格式，本 SB 只需從內頁
`<meta>` 標籤取出完整 datetime 字串並傳給這個既有函式；解析失敗時 fallback 回列表頁
`MM/DD` + 跨年推論（同一函式已處理，呼叫端不需分支邏輯）。

---

## 4. Data/API/Schema Contract

不涉及 Schema 變更（`market_articles` 新欄位為 `UG-G2-SB3` 範圍）。`parse_article_comments()`
回傳結構依 `MULTI_SOURCE_DATA_CONTRACT.md` §3.3：`{push_count, boo_count, neutral_count,
total_comments}` 四個整數（依決策點 1 結果，可能額外含 Top-N 留言清單）。

---

## 5. Risks & Trade-offs

| 風險 | 說明 | 因應 |
|------|------|------|
| **RISK-002 惡化**（既有登錄風險） | 本 SB 讓每篇文章多一次內頁請求，若 `max_pages` 掃到的文章數為 N，請求量從 「N/篇均攤的列表頁請求」變成「列表頁請求 + N 次內頁請求」，顯著提高觸發 Rate Limit 的機率 | 沿用既有 `@retry` + 禮貌性延遲機制；是否需要額外的內頁請求節流（如每篇間固定 sleep）列為 §6 決策點 2 |
| `SOURCE_FAILED` 例外向上傳遞後，`main_etl_pipeline.py` 目前無對應 catch 邏輯 | `run_ptt_pipeline()`（`main_etl_pipeline.py:67`）目前直接呼叫 scraper，若本 SB 讓 scraper 在特定情境下拋出例外，未捕捉會使整個 daily pipeline 中斷 | 需確認 `main_etl_pipeline.py` 是否要新增 catch（記錄後跳過 PTT、其餘來源照常）——見 §6 決策點 3 |
| 內頁請求量增加可能使既有測試（依賴請求次數的 mock 斷言）需要調整 | 未逐一稽核 `tests/` 現有 PTT 相關測試 | 開工時盤點所有現有 mock 是否假設「一次列表頁請求＝一篇文章」 |

---

## 6. PO 決策點

### 決策點 1：「Top-5 高讚留言擷取」是否納入本 SB

Master Plan 精簡 Brief 寫了這項，但 Gate 0 已核准的 `MULTI_SOURCE_DATA_CONTRACT.md` §3.3
沒有對應規格，`FEATURE_REGISTRY.md` 的三個留言特徵也都只需要計數、不需要留言內容。

- **建議方案**：本 SB 只做計數（`push_count`／`boo_count`／`neutral_count`），不擷取留言
  文字內容。理由：無任何已核准契約或下游消費者需要它，避免無需求的擴大實作。
- **替代方案**：一併實作留言內容擷取（供未來 UI 展示個股熱門留言等尚未規劃的用途），
  但需另外定義儲存位置（`market_articles` 沒有留言內容欄位）與展示規格。

### 決策點 2：內頁請求的額外節流

是否在每篇文章的內頁請求之間，額外加上比列表頁更保守的 sleep 區間（例如列表頁沿用
1.0-2.5 秒，內頁改用更長區間），降低本 SB 顯著提高的請求量觸發 PTT 封鎖的機率？

### 決策點 3：`main_etl_pipeline.py` 是否需要新增 `SOURCE_FAILED` 例外的 catch 邏輯

本 SB 讓 `SOURCE_FAILED` 情境真正拋出例外後，若 `run_ptt_pipeline()` 或其呼叫端沒有對應
`except`，會使該次 daily pipeline 執行中斷（而非「PTT 這次跳過，其餘照常」）。是否本 SB
一併加上這個 catch（`main_etl_pipeline.py` 不在 Master Plan 精簡 Brief 的
`Affected Components` 清單內，屬於範圍擴充，需明確核准）？

---

## 7. In / Out of Scope

**In Scope**（依 §15 PO 核准之最終範圍）：`parse_article_comments()` 新方法；
`scrape_ptt_stock_by_keyword` 內的例外處理拆分為 `SOURCE_DEGRADED`／`SOURCE_FAILED` 兩層；
內頁完整時間戳記接線至既有 `parse_ptt_datetime()`；內頁請求額外節流（決策點 2）；
`main_etl_pipeline.py` 捕捉 `SOURCE_FAILED` 例外（決策點 3，契約必要項非範圍擴充）。

**Out of Scope**：留言文字內容擷取（決策點 1 核准移除，僅留計數）；`market_articles`
Schema 變更（`UG-G2-SB3`）；`db_writer.py` 寫入路徑（待 `UG-G2-SB3` Schema 就緒）；
留言衍生特徵計算（`UG-G2-SB4`）。

---

## 8. Affected Components

`src/extractors/ptt_scraper.py`；`main_etl_pipeline.py`（`SOURCE_FAILED` catch）；
新增 `tests/test_ptt_comments.py`（Master Plan 既定測試檔名）；
依決策點 3 結果，可能包含 `main_etl_pipeline.py`。

---

## 9. Tests

依 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5 逐情境對應：

- `test_parse_push`／`test_parse_boo`／`test_parse_neutral`（Master Plan 既定測試名稱）
- `test_parse_failure_keeps_null`（單篇解析失敗時不污染其他文章的計數）
- `test_rate_limit_backoff`（既有 retry 機制不受影響）
- `test_source_degraded_on_single_article_failure`（known-FAIL：構造單篇 HTML 結構異常，
  確認繼續處理其餘文章而非整批中斷）
- `test_source_failed_raises_exception_not_empty_dataframe`（known-FAIL：構造完全不可達情境，
  確認拋出例外而非回傳空 DataFrame——直接對應現行 L79-81 的缺陷）
- `test_full_datetime_from_inner_page_meta`

---

## 10. E2E Verification Plan

本 SB 不涉及資料庫，E2E 驗證方式與 Gate 1／`UG-G2-SB1` 的隔離 DB 模式不同——改為對
**真實 PTT 網站**的唯讀請求驗證（沿用 `UG-G1-SB3` 對讀取型真實網路請求的既有審查慣例：
執行前完整程式碼先給審查員看過，確認只有 GET 請求、無任何寫入）。驗證項目：對 1-2 篇
真實文章執行 `parse_article_comments()`，確認解析結果與人工肉眼核對的推噓文數一致。

---

## 11. Documentation Sync

`FEATURE_REGISTRY.md`（`COMMENT_ENHANCED_19` 三項特徵狀態欄，若決策點確認資料來源已可用，
標註「上游解析已就緒，特徵計算待 `UG-G2-SB4`」）；`PROJECT_STATUS.md`（SB 進度）。

---

## 12. Rollback

`Revert commit`（Master Plan 既定 Rollback 策略），不涉及 Schema 或資料庫，風險層級低。

---

## 13. Definition of Done

- `parse_article_comments()` 正確解析推／噓／→ 三類 push-tag。
- 例外處理正確區分 `SOURCE_DEGRADED`（單篇失敗，續爬）與 `SOURCE_FAILED`（整體不可用，
  拋出例外，不回傳空 DataFrame）。
- 內頁完整時間戳記解析生效，列表頁 `MM/DD` 邏輯作為 fallback 保留。
- §9 全部測試 PASS，含至少 2 個 known-FAIL 案例（`SOURCE_DEGRADED`／`SOURCE_FAILED` 各一）。
- 依決策點 1-3 結果調整範圍後仍全部完成。
- `market_articles`／`db_writer.py` 未被觸碰（除非決策點另有核准）。

---

## 14. 待 PO 裁決事項彙總

1. **決策點 1**：是否納入「Top-5 高讚留言擷取」（建議：不納入，無契約依據亦無消費者）。
2. **決策點 2**：內頁請求是否需要額外、更保守的節流區間。
3. **決策點 3**：`main_etl_pipeline.py` 是否一併新增 `SOURCE_FAILED` 例外的 catch 邏輯。
4. 是否核准依 §7 範圍開始實作（純規劃階段，待核准後才動筆）。

---

## 15. PO 核准與修正記錄（2026-08-27）

**四項裁決全部核准**：

1. **決策點 1**：核准不納入留言內容擷取。Master Plan §8 UG-G2-SB2 精簡 Brief 的
   「Top-5 高讚留言擷取」文字已同步移除並加註理由（比照 `UG-G2-SB1` 對 27→29 殘留漂移
   「發現了就一起修」的處理方式，不留下與已核准契約對不上的規格文字）。
2. **決策點 2**：核准內頁請求加更保守的節流區間。理由：RISK-002 現況標籤為
   `OBSERVED`（非假設性風險，`REMAINING_RISKS.md` 已記錄真實發生過），內頁請求量
   顯著增加時不應省略此防護。
3. **決策點 3**：核准納入 `main_etl_pipeline.py` 的 `SOURCE_FAILED` catch 邏輯，
   **PO 明確裁示這不是範圍擴充，是契約必要項**——`MULTI_SOURCE_DATA_CONTRACT.md` §3.5
   原文最後一句即寫明「下游 pipeline 應捕獲此例外後記錄並跳過該來源」。若本 SB 讓
   `SOURCE_FAILED` 真的拋出例外卻無人接住，daily pipeline 會整個中斷，比現狀（吞掉例外
   但至少跑得完）更糟，且直接違反 Gate 0 已核准的契約文字。`main_etl_pipeline.py` 已列入
   Affected Components。
4. 核准依 §7 範圍（含上述三點調整）開始實作。

**送審方式**：實作完成後先送 Gate B 審查，本 SB 不碰 DB，不需要對真實 DB 執行任何動作。
§10 對真實 PTT 網站的唯讀驗證，執行前需先把完整程式碼交給 PO 審查，確認只有 GET 請求、
無任何寫入動作，比照 `UG-G1-SB3` 當時的審查方式。
