# UG-G2-SB2 Gate B 送審文件：PTT 內頁留言解析

> 狀態：**待 PO 審查**
> 日期：2026-08-27
> 對應提案：`doc/upgrade/gates/G2_SB2_GATE_A_PROPOSAL.md`（已核准，含 §15 PO 核准與修正記錄）

---

## 1. 摘要

依核准之 §7 範圍（含決策點 1-3 三項調整）完成實作：`parse_article_comments()` 新方法、
`scrape_ptt_stock_by_keyword()` 的 Failure Semantics 拆分（`SOURCE_DEGRADED`／
`SOURCE_FAILED`）、內頁完整時間戳記接線、內頁請求額外節流、`main_etl_pipeline.py`
捕捉 `SOURCE_FAILED` 例外。真實 PTT 網站唯讀驗證已完成（審查員先審過程式碼、PO 核准後執行）。

**過程中發現並修復一個既有測試隔離缺陷**（非本 SB 原始範圍，但直接擋住驗證）：
`test_canonical_stock_id.py`／`test_feature_aggregator_alignment.py`／
`test_research_features.py`／`test_time_alignment.py` 四個既有測試檔對 `bs4` 的 stub
判斷式用的是 `if "bs4" not in sys.modules:`，而非本專案其他套件（如 `psycopg2`）
一律採用的 `try: import X except ModuleNotFoundError:` 正確寫法。host 上其實真的裝了
`bs4`，但只要這四個檔案中任一個先於其他檔案載入，就會不分青紅皂白把 `sys.modules["bs4"]`
永久換成 `MagicMock()` 假貨且無任何清理機制，導致後續所有測試檔案（含本次新增的
`test_ptt_comments.py`）拿到的都是假的 `BeautifulSoup`。已修正這四個檔案的判斷式，
僅改判斷條件，測試邏輯本身未變更。

---

## 2. Diff 摘要

| 檔案 | 異動類型 | 行數（+/-） |
|------|---------|-------------|
| `src/extractors/ptt_scraper.py` | 修改 | +107 / -19 |
| `main_etl_pipeline.py` | 修改 | +13 / -3 |
| `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` | 修改（Top-5 留言擷取移除＋Affected Components 更新，決策點 1/3） | +5 / -5 |
| `tests/test_ptt_comments.py` | 新增 | +149 / -0 |
| `tests/test_canonical_stock_id.py` | 修改（bs4 stub 修正） | +3 / -1 |
| `tests/test_db_read_semantics.py` | 修改（ptt_scraper stub 補 `PttSourceUnavailableError`） | +6 / -1 |
| `tests/test_feature_aggregator_alignment.py` | 修改（bs4 stub 修正） | +3 / -1 |
| `tests/test_nlp_checkpoint_semantics.py` | 修改（ptt_scraper stub 補 `PttSourceUnavailableError`） | +5 / -0 |
| `tests/test_research_features.py` | 修改（bs4 stub 修正） | +3 / -1 |
| `tests/test_time_alignment.py` | 修改（bs4 stub 修正） | +3 / -1 |
| `doc/upgrade/gates/G2_SB2_GATE_A_PROPOSAL.md` | 新增（Gate A 提案，含 §15 核准記錄） | +262 / -0 |
| `doc/upgrade/gates/G2_SB2_GATE_B_SUBMISSION.md` | 新增（本文件） | — |

---

## 3. 產出 1：契約驗證原始輸出

```bash
$ python scripts/verify/gate0_contract_check.py
...
B11  PASS | 全文件契約數字宣告一致（反查法）
       掃描 7 份文件；違規 0；已登錄遺留 1
       [WARN 已登錄遺留] DECISIONS.md:599 n=18 (欄) — DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂
==================================================
Part B: 11/11 PASS
```

---

## 4. 產出 2：執行環境、測試原始輸出、依賴狀態

**Host（Windows，非支援環境，Python 3.10.11）**：

```bash
$ PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -p "test_*.py"
Ran 214 tests in 2.793s
OK
```

214 = 原 208 + 6 個本 SB 新增測試（`tests/test_ptt_comments.py`）。

**環境備註（與本 SB 內容無關，但影響本次測試指令的執行方式）**：host 上執行本測試套件
需加上 `PYTHONIOENCODING=utf-8`，否則本檔（`ptt_scraper.py`，含既有的與本次新增的
`❌`／`⚠️` 表情符號 log 訊息）在部分 Windows 終端機（cp950 等非 UTF-8 codepage）
會觸發 `UnicodeEncodeError` 而非測試失敗。已實測確認：不加此環境變數時，即使是
`print('❌ test')` 這種與本專案程式碼無關的裸指令也會在本機出現同樣錯誤，證實這是
host 終端機編碼環境的既有限制，非本次程式碼引入的問題；dev container（UTF-8 原生）
不受影響。

**Container（`stock_prediction_system2_devcontainer-app-1`，真實 `tenacity`／`requests`／
`bs4` 路徑）**：用於 §5 真實 PTT 網站驗證。

---

## 5. 產出 3：真實 PTT 網站唯讀驗證（PO 核准後執行）

審查員已先複查 `src/extractors/ptt_scraper.py` 全文，確認全檔僅一處 HTTP 呼叫
（`requests.get()`）、`parse_article_comments()` 同樣只讀取無寫入，PO 核准後執行如下：

### 5.1 列表頁真實爬取

```
$ scraper.scrape_ptt_stock_by_keyword('台積電', max_pages=1)
ARTICLES FOUND: 20
```

20 篇真實文章成功解析（標題、URL、日期、作者、push_count 徽章）。

### 5.2 內頁留言解析（2 篇真實文章）+ 人工獨立核對

| 文章 | `parse_article_comments()` 回傳 | 人工獨立核對（重新用最原始方式逐一計數，非重跑同一函式） |
|------|--------------------------------|----------------------------------------------------------|
| M.1787643158.A.FE2 | `push=18, boo=3, neutral=7, total=28, engagement=15, full_datetime='Tue Aug 25 15:32:36 2026'` | `TOTAL PUSH DIVS: 28`；獨立逐一分類：`push=18, boo=3, neutral=7, other=0`；`META TAG '時間' VALUE: 'Tue Aug 25 15:32:36 2026'`——**完全一致** |
| M.1787057105.A.875 | `push=17, boo=1, neutral=5, total=23, engagement=16, full_datetime='Tue Aug 18 20:45:03 2026'` | 已執行 `parse_article_comments()` 取得（未另外重複人工核對第二篇，第一篇已證明解析邏輯與真實 HTML 結構相符） |

第一篇的人工獨立核對**不是**重跑 `parse_article_comments()` 本身，而是重新以
`soup.find_all('div', class_='push')` 取得全部 28 個 push div，逐一用獨立的計數邏輯
分類 push-tag 文字，結果與函式回傳值逐項相符，證明解析邏輯正確對應真實 PTT 頁面結構。

---

## 6. 產出 4：格式／行尾夾帶偵測

```bash
$ git diff --numstat > raw.txt && git diff --numstat -w > nows.txt && diff raw.txt nows.txt
3,4c3,4
< 13	3	main_etl_pipeline.py
< 107	19	src/extractors/ptt_scraper.py
---
> 12	2	main_etl_pipeline.py
> 93	5	src/extractors/ptt_scraper.py
```

**兩個檔案有純空白差異，需要你事前授權（`CLAUDE.md` §12.2）**：

- `main_etl_pipeline.py`：1 行純空白差異。
- `src/extractors/ptt_scraper.py`：14 行純空白差異——本檔案這次用 Write 工具整檔重寫
  （新增 `PttSourceUnavailableError`、`parse_article_comments()`、拆分 Failure Semantics
  需要大幅調整既有函式結構，逐行 Edit 已不敷使用），原檔案內散落多處**帶行尾空格的空白行**
  （縮排層級 8～24 個空格不等），重寫後的空白行皆為真正的空行（無行尾空格），因而產生此差異。
  內容邏輯無任何損失，純屬重寫過程的附帶清理，與 `UG-G2-SB1` 的 `db_writer.py` 6 行事件
  同一類性質。

其餘 9 個修改／新增檔案的 numstat 與 `-w` 版本完全一致，無格式夾帶。

---

## 7. 產出 5：證據標籤表

| 宣稱 | 證據標籤 | 可重跑指令 / 說明 |
|------|---------|-------------------|
| Failure Semantics 三態正確對應 §3.5 | `VERIFIED THIS SESSION` | `tests/test_ptt_comments.py::ScrapeFailureSemanticsTests`（host，含 2 個 known-FAIL 案例）+ 審查員獨立複查程式碼確認邏輯對應正確 |
| 推/噓/→ 計數解析正確 | `VERIFIED THIS SESSION` | §5.2 真實 PTT 文章 + 獨立人工核對，逐項相符 |
| 內頁完整時間戳記解析正確 | `VERIFIED THIS SESSION` | §5.2，`full_datetime` 與頁面 `article-meta-value` 逐字相符 |
| 全檔僅 GET 請求、無寫入 | `VERIFIED THIS SESSION` | 審查員逐行複查 + `grep -n "requests\.\|\.post(\|\.put(\|\.delete(\|\.patch("` 僅命中一次 `requests.get` |
| 全套測試 214/214 OK（host，回歸確認） | `VERIFIED THIS SESSION` | §4，非 ML／NLP／DB 路徑宣稱 |
| `bs4` stub 缺陷已修復 | `VERIFIED THIS SESSION` | 修復前重跑全套測試出現 4 個失敗（`push_count` 等斷言為 0）；修復後 214/214 OK |
| numstat 除已揭露兩檔外無格式夾帶 | `VERIFIED THIS SESSION` | §6 |

---

## 8. 產出 6：Known-FAIL 案例對照表

| # | 檢查 | Known-FAIL 案例 | 實測結果 | 復原確認 |
|---|------|-----------------|---------|---------|
| 1 | `SOURCE_DEGRADED`（單篇解析失敗續爬） | `test_source_degraded_on_single_article_failure_continues_others`：構造三篇文章（正常／缺 `date` 欄位／正常），缺欄位那篇排在中間 | 修正前（單一 `except Exception: break`）在第二篇崩潰時直接跳出整個分頁迴圈，第三篇永遠不會被處理，結果只剩第一篇（`len=1`）；修正後正確跳過第二篇、繼續處理第三篇，保留第一與第三篇（`len=2`）。**本案例最初版本用「正常＋缺欄位排最後」兩篇 fixture，PO 於 Gate B 審查時實測發現：舊程式碼在該 fixture 下也會得到一模一樣的 `len=1` 結果——第一篇早在崩潰前就已 append，`except: break` 剛好「順便」保住它，測試結構上不可能偵測到新舊行為差異，屬 `CLAUDE.md` §9A.1 警告的無效檢查。已改為三篇排列並重新驗證** | 測試已納入正式套件，非暫時案例；known-FAIL 已用兩種 fixture 都實測過（原兩篇版證實無偵測力，修正後三篇版證實有偵測力） |
| 2 | `SOURCE_FAILED`（來源不可達拋例外） | `test_source_failed_raises_exception_not_empty_dataframe`：`_fetch_page` 第一次呼叫即拋例外 | 修正前會回傳空 DataFrame，呼叫端無法區分「PTT 不可達」與「這個關鍵字真的沒有文章」；修正後正確拋出 `PttSourceUnavailableError` | 同上 |
| 3 | `bs4` stub 缺陷 | 暫時還原 4 個測試檔的舊版 `if "bs4" not in sys.modules:` 判斷，重跑全套測試 | `FAIL`：4 個 `test_ptt_comments.py` 測試因 `BeautifulSoup` 被 `MagicMock()` 取代而斷言失敗（`push_count` 等皆為 0） | 已還原為修正版；還原後全套 214/214 OK |

---

## 9. Definition of Done 對照

- [x] `parse_article_comments()` 正確解析推／噓／→ 三類 push-tag（含真實網站驗證）。
- [x] Failure Semantics 正確區分 `SOURCE_DEGRADED`／`SOURCE_FAILED`。
- [x] 內頁完整時間戳記解析生效（含真實網站驗證，逐字相符）。
- [x] 內頁請求額外節流（決策點 2）。
- [x] `main_etl_pipeline.py` 捕捉 `SOURCE_FAILED`（決策點 3）。
- [x] 留言文字內容擷取未實作（決策點 1，已移除 Master Plan 對應文字）。
- [x] §9（提案）全部測試 PASS，含 2 個納入正式套件的 known-FAIL 案例。
- [x] `market_articles`／`db_writer.py` 未被觸碰。
- [x] 兩處格式夾帶已於本文件 §6 揭露，待你授權。

---

## 10. 待 PO 裁決事項

1. 是否核准本次 commit（12 個檔案：9 modified + 3 new，清單見 §2）。
2. §6 已揭露的兩處純空白差異（`main_etl_pipeline.py` 1 行、`ptt_scraper.py` 14 行）是否同意隨本次一併 commit。
3. `bs4` stub 缺陷修復（4 個既有測試檔）是否認可為本次範圍內必要的附帶修復。
