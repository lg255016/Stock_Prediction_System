# §0.5 #31＋#33 Gemini 用量縮減／探索不改既有權重——Gate A 提案 v3

## 0. 摘要

> **v3 修訂**（複核第二輪，「探索五個靜默 return」）：`run_discovery()` 現況除了
> v2 已修過的第 173 行例外生吞外，**還有五種情況會靜默 `return`、不拋例外**——
> 缺 API key、PTT 掃頁失敗、無熱門標題、Gemini 回應無效、Gemini 回應有效但無新
> 詞。v2 的 `else` 分支「呼叫回來就記 OK」會把這五種全記成 `OK`，其中三種其實是
> 失敗。**v3 改為 `run_discovery()` 回傳 `(outcome, detail)` 四態元組**，例外
> （含配額）不跨越函式邊界，呼叫端依回傳值記錄，取代 v2「`except
> GeminiDailyQuotaExhausted: raise`」的連帶修正（少一層 raise/catch）。「上次
> 成功」判準改為最近一列 `outcome ∈ {OK, NO_DATA}`（`NO_DATA` 也算問過）。
> 紅測由 9 條增為 12 條。詳見 §3.1、§4、§6。
>
> **v2 修訂**（保留記錄）：依 PO 複核裁決三處：(1) 決策點 A 不採 A1/A2/A3，改採
> **A4——跳過不寫任何列**（v3 不變）；(2) 配額耗盡的 outcome 由 `FETCH_FAILED`
> 訂正為 `REFUSED`（v3 沿用，實作方式改為函式內部接住，見 §3.1）；(3) 補兩個
> 實作陷阱（NLP run log 的 `batch_key` 改由呼叫端傳入；紅測 fixture 用 09-17
> 真實 log 原文，不得自編）——這兩項 v3 不變，見 §3.2、§4。

兩案合一：#31（探索頻率降為每週一次、每日配額耗盡不再無意義重試、模型名釘死）與
#33（AI 探索寫入 `theme_stock_mapping` 時不得改動既有列的權重）——理由是兩者都改
`run_all_daily_tasks()` 的 AI 探索段與 `upsert_theme_stock_mapping()`，分兩案做
會對同一段程式改兩次。本案**不動排程器**（08:30 雙時點是下一案），但依 PO 指示
在 `run_all_daily_tasks(run_discovery: bool = True)` 留一個參數給它。

唯讀查證確認 PO 陳述的現況全部屬實（見 §2），但發現兩個 PO 訊息未提及、
實作時必須處理的既有事實：

1. `run_discovery()` 目前**任何分支都不寫 `etl_run_log`**——2.1 的「距上次成功 N 天」
   判準若要成立，必須先補上成功路徑的落地紀錄，這不是 PO 訊息漏寫，是必然的實作前提。
2. （v1 曾提出的決策點 A 已由 PO 裁決為 A4，見 §3.1；v1 的 A1/A2/A3 選項與其比較表
   移除，不再保留於本版。）

其餘 2.2～2.8 唯讀查證與 PO 陳述完全一致，設計照 PO 訊息原樣提案，僅補上
具體程式碼位置與 known-FAIL 構造法。

## 1. Requirement Source

- PO 訊息（本次開案，2026-09-18）：`doc/governance/PROJECT_STATUS.md` §0.5 #31、#33
- RISK-031（Gemini 用量共用者不明——本案確認只有本專案在用，見 §2.4）
- RISK-032（題材溢出全歷史重算——本案不解決，但 #33 的權重凍結減少其**新增**觸發次數）
- DEC-039（題材溢出全歷史重算機制）、DEC-042（成因 F 失敗鍵推導，Python 端決策/SQL
  端只取資料的架構先例，本案 §3.1 沿用同一分工）

## 2. Current State（唯讀查證，2026-09-18，容器內程式碼閱讀）

### 2.1 模型名——確認 PO 陳述屬實

```
src/extractors/trend_discover.py:17:   self.model = genai.GenerativeModel('gemini-flash-latest')
src/transform/nlp_processor.py:27:     self.model = genai.GenerativeModel('gemini-flash-latest')
```

兩處字面重複，無共用常數。09-17 真實執行 log（`FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_
20260917_log.txt:405,415`）證實 `gemini-flash-latest` 當時解析為 `gemini-3.8-flash`
（`model: gemini-3.8-flash`），與 PO 陳述一致。

### 2.2 探索呼叫——確認無條件、例外只 print

```python
# main_etl_pipeline.py:842-847
print("\n========== 啟動 AI 熱門趨勢探索 ==========")
try:
    self.trend_discover.run_discovery(self.db_writer, max_new_keywords=3)
except Exception as e:
    print(f"[WARNING] AI 趨勢探索異常: {e}")
```

`run_discovery()` 本身（`trend_discover.py:173-175`）也有一層 `except Exception`，
同樣只 `print` 後 `return`，**兩層都不寫 `etl_run_log`**——見上方摘要的缺口 1。
`run_discovery()` 沒有任何參數可以讓呼叫端要求跳過（PO 陳述「無條件」屬實，
且比 PO 描述的更徹底：現在連失敗都不落地）。

### 2.3 每分鐘與每日配額不分——確認 PO 陳述屬實

```python
# nlp_processor.py:95-102
retry_keywords = [
    "429", "quota", "rate limit", "resourceexhausted", "resource_exhausted",
    "503", "unavailable", "timeout", "deadline", "connection error",
]
return any(k in exc_str for k in retry_keywords)
```

`"quota"` 同時匹配「每分鐘限速」與「每日配額耗盡」兩種錯誤——09-17 真實錯誤字串
（同上 log:404）含 `"You exceeded your current quota"`，被判為暫態，重試 5 次後才放棄，
`quota_id: "GenerateRequestsPerDayPerProjectPerModel-FreeTier"`——**`"PerDay"`
確實存在於這個 ID 字串中**（大小寫：`PerDay`，與 PO 訊息一致），可作為每日配額的
判斷依據。`trend_discover.py:68-71` 的 `_is_transient_exception` 是同一套關鍵字，
同樣的問題也存在於探索路徑。

### 2.4 NLP 管線目前完全不攔截例外——比 PO 陳述更嚴重

```python
# main_etl_pipeline.py:904-905
# 3. 執行 NLP 情緒運算管線 (Phase 2)
self.run_nlp_sentiment_pipeline(batch_size=500)
```

`run_nlp_sentiment_pipeline()` 本體（507-541 行）**沒有任何 try/except**，
`process_batch_hybrid()` 拋出的例外（含 5 次重試耗盡後的每日配額例外）會直接
**穿透 `run_all_daily_tasks()` 整個方法**中止執行——這正是 09-17 真實執行中止的
機制（RISK-031）。PO 訊息 2.2 的因果描述準確。

### 2.5 既有映射被探索改權重——確認 PO 陳述屬實

```python
# db_writer.py:732-740
query = """
    INSERT INTO theme_stock_mapping (theme_keyword, stock_id, stock_name, relevance_weight)
    VALUES %s
    ON CONFLICT (theme_keyword, stock_id)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        relevance_weight = EXCLUDED.relevance_weight,
        updated_at = CURRENT_TIMESTAMP;
"""
```

`ON CONFLICT DO UPDATE` 對既有配對三欄全改——這正是 09-18 真實執行把
`AI伺服器／2382` 從 1.00 改成 0.90、回溯改寫 13 天 `bullishness_index` 的機制
（DEC-039、RISK-032，見 §0.5 #32 結案 commit `0c9f169` 的訂正段落）。

### 2.6 Gemini key 共用者——PO 已自行查證，本案僅登記結論

PO 訊息陳述已查過 Google 用量主控台，確認只有本專案使用該 key。
本案標記為 `REPORTED, NOT INDEPENDENTLY VERIFIED`（回報者：PO，回報位置：本次開案訊息）
——用量主控台不在本次可控查證範圍內，依 `CLAUDE.md` §9 誠實標示，不冒充已獨立驗證。

### 2.7 `etl_run_log` 的 `source` 欄無列舉限制——新增來源值不需要 migration

```sql
-- database/migrations/007_etl_run_log.sql:74-85
source          VARCHAR(40) NOT NULL,   -- 'twse_mi_index' / 'tpex_daily_quotes' / 'ptt'
```

`source` 只是註解建議值，**沒有 `CHECK` 約束**（與 `outcome` 欄相反，見 §2.8）。
`'ai_discovery'`（12 字）、`'nlp_gemini'`（10 字）皆在 `VARCHAR(40)` 內。
**本案不需要新的 migration 檔**，純屬應用層新增來源標記。

`db_writer.py` 的 `fetch_failed_source_keys()`（§0.5 #32）查詢明確限定
`WHERE source='ptt'`，新增的兩個來源值不會被該查詢誤讀。

### 2.8 `outcome`／`detail` 有 DB 層雙向 `CHECK`——§3.1／§3.2 設計的根據

```sql
-- database/migrations/007_etl_run_log.sql:106-121
CHECK (
    (outcome IN ('FETCH_FAILED', 'REFUSED') AND detail IS NOT NULL)
    OR
    (outcome NOT IN ('FETCH_FAILED', 'REFUSED') AND detail IS NULL)
)
```

`RunLogEntry.__init__`（`etl_run_log.py:71-78`）在應用層重覆同一條規則，
兩層都會擋下「`NO_DATA` 帶 `detail`」的寫入。migration 007 的欄位語意註解
（74-95 行）明講這條約束是 **2026-09-04 PO／複查方的雙向裁決**，且該檔另一段
註解（92-95 行）特別警告過「窮舉是刻意的……下一個人就會寫出 `'SKIPPED'`」——
即新增第五個 outcome 這條路，先前已被同一批裁決預先否決過一次。

## 3. 設計提案

### 3.1 探索頻率判準——決策點 A 採 A4；`run_discovery()` 改回傳四態（v3）

**PO 裁決理由（A4，逐字覆核，成立）**：migration 007 第 42 行對 `NO_DATA` 的
定義是「**請求成功**（拿到 2xx 且可解析），但內容為空」——策略性跳過根本沒有
發出請求，記成 `NO_DATA` 就是把「沒問」寫成「問了沒東西」，是 §0.5 #32 才剛清除
過的同型混淆（`SUCCESS_EMPTY` 與 `SOURCE_FAILED` 的區分）。`etl_run_log` 記的是
「發出去的請求得到什麼」，依規則不發出的請求不是一筆觀測，沒有 outcome 可記。
v1 的 A1/A2/A3 三案全部作廢。

**v3 追加問題（複核第二輪發現）**：`run_discovery()` 現況有**五種情況會靜默
`return`、不拋任何例外**：

| # | 情況 | 現行程式位置 |
|---|------|-------------|
| 1 | 沒有 API key | `trend_discover.py:97-99` |
| 2 | `_fetch_recent_hot_titles()` 掃頁出錯回 `None` | `trend_discover.py:102-104` |
| 3 | 熱門標題為空 | `trend_discover.py:105-107` |
| 4 | Gemini 回應無效或萃取失敗 | `trend_discover.py:173-175`（既有 `except Exception`） |
| 5 | Gemini 回答有效但沒有可新增的詞 | `trend_discover.py:177-179` |

v2 設計「呼叫回來就記 `OK`」（見上版 `else:` 分支）會把上述五種**全部**記成
`OK`——其中 1／2／4 其實是失敗，這正是 migration 007 第 53 行「`NO_DATA` 與
`FETCH_FAILED` 不得互相取代」在探索路徑上的版本，且比典型情況更嚴重（連 `OK`
都混進來了）：一次網路失敗會讓探索照 7 天規則停一整週，而 run log 上寫的卻是
成功。

**改法：`run_discovery()` 回傳 `(outcome, detail)`，四態對應 migration 007 的
定義；例外（含配額）不跨越這個函式邊界，取代 v2 的「`except
GeminiDailyQuotaExhausted: raise`」連帶修正（少一層 raise/catch）**：

```python
# trend_discover.py（改寫，回傳值取代原本的隱式 None）
def run_discovery(self, db_writer, max_new_keywords=3) -> tuple[str, str | None]:
    if not self.api_key:
        return "FETCH_FAILED", "GEMINI_API_KEY 未設定"

    titles = self._fetch_recent_hot_titles()
    if titles is None:
        return "FETCH_FAILED", "PTT 熱門標題擷取失敗（掃頁時發生錯誤）"
    if not titles:
        return "NO_DATA", None

    prompt = f"""..."""  # 不變

    new_keywords, mapping_records = [], []
    try:
        response = self._generate_with_retry(prompt)
        result = json.loads(response.text)
        # ... 既有解析邏輯不變 ...
    except GeminiDailyQuotaExhausted as exc:
        return "REFUSED", str(exc)[:500]
    except Exception as e:
        return "FETCH_FAILED", ("%s: %s" % (type(e).__name__, e))[:500]

    if not new_keywords:
        return "NO_DATA", None

    db_writer.insert_discovered_keywords(new_keywords)
    if mapping_records:
        db_writer.upsert_theme_stock_mapping(mapping_records)
    return "OK", None
```

`_fetch_recent_hot_titles()` 第 61 行既有的 `except Exception: return None` 保留
不動——它已經用 `None` 區分「掃頁失敗」與「掃到但是空」，正好對應情況 2／3，
是本次唯一不需要改的既有防護。

**判準邏輯（Python 端，沿用 DEC-042 的分工：SQL 只取資料，判斷在 Python）——
「上次成功」改為最近一列 `outcome ∈ {OK, NO_DATA}`**（複核裁決：`NO_DATA` 是
請求成功、內容為空，也算試過；`FETCH_FAILED`／`REFUSED` 不算，隔天即可再試，
恰好對上配額隔天重置的週期）：

```python
# db_writer.py 新增方法
def fetch_last_discovery_probed_date(self) -> date | None:
    """回傳最近一次 source='ai_discovery' item_key='discovery'
    outcome IN ('OK', 'NO_DATA')（有實際發出請求且拿到回應）的 batch_key
    （解析為 date）；從未問過回傳 None。"""
    query = """
        SELECT MAX(batch_key) FROM etl_run_log
        WHERE source = 'ai_discovery' AND item_key = 'discovery'
          AND outcome IN ('OK', 'NO_DATA');
    """
    ...
```

```python
# main_etl_pipeline.py run_all_daily_tasks() 內，AI 探索段之前
DISCOVERY_INTERVAL_DAYS = 7  # 業務常數，與 BOARD_LOOKBACK_DAYS 同一慣例放在檔案頂部

print("\n========== 啟動 AI 熱門趨勢探索 ==========")
should_run_discovery = False
if run_discovery:
    last_probed = self.db_writer.fetch_last_discovery_probed_date()
    should_run_discovery = (
        last_probed is None
        or (now.date() - last_probed).days >= DISCOVERY_INTERVAL_DAYS
    )

if should_run_discovery:
    outcome, detail = self.trend_discover.run_discovery(self.db_writer, max_new_keywords=3)
    kwargs = {"detail": detail} if outcome in (FETCH_FAILED, REFUSED) else {}
    entries = [RunLogEntry(SOURCE_AI_DISCOVERY, tracked_batch_key, "discovery",
                            outcome, **kwargs)]
    run_log_writer.write(entries, started_at)
# else（A4）：run_discovery=False 或距上次「有問過」（OK／NO_DATA）不足 7 天
# ——不寫任何列。「跳過」與「探索前就已中止（例如逐股階段整個掛掉）」如何從
# run log 事後區分：看同一個 batch_key 底下 SOURCE_PTT／SOURCE_TRACKED_DAILY
# 有沒有列——後面階段有列、ai_discovery 沒列，就是規則性跳過；連後面階段都
# 沒有列，才是探索前中止。這是查詢技巧，不是本案要新增的程式碼或測試。
```

`run_discovery()` 現在四態都在函式內部接住並回傳，理論上不會再向呼叫端拋出
例外；呼叫端這段不再需要 `try/except`——若未來 `run_discovery()` 本身出現
本提案未預期的例外（實作缺陷），應讓它自然中止 `run_all_daily_tasks()`，
不得另外加一層吞掉，否則又會重蹈「不落地」的覆轍。

### 3.2 每日配額不重試——outcome 依複核訂正為 `REFUSED`

> **v2 訂正**：v1 草稿把配額耗盡寫成 `FETCH_FAILED`。PO 複核指出 migration 007
> 第 45 行 `REFUSED` 的定義是「服務在叫我們停（403／429，DEC-032）」，第 44 行
> `FETCH_FAILED` 是「傳輸層失敗、5xx 重試耗盡、解析失敗」——每日配額 429 正是
> 服務主動叫停，不是我方抓取失敗。**兩處都改（探索見 §3.1，NLP 見下方）。**
> 這也讓 09-17 那次真實中止（`FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_
> aborted.md`）在 run log 語彙裡有正確的歸類。

```python
# nlp_processor.py 新增
class GeminiDailyQuotaExhausted(RuntimeError):
    """每日配額已耗盡（quota_id 含 PerDay）——重試無意義，須等隔天配額重置。"""


@staticmethod
def _is_daily_quota_exhausted(exc: Exception) -> bool:
    return "PerDay" in str(exc)
```

`_generate_content_with_retry` 在 `except Exception as exc:` 分支最前面插入：

```python
if self._is_daily_quota_exhausted(exc):
    raise GeminiDailyQuotaExhausted(str(exc)) from exc
```

放在 `_is_transient_exception` 判斷之前——每日配額訊息同時含 `"quota"` 與
`"PerDay"`，若判斷順序反過來，`"quota"` 會先命中，永遠走不到這個分支
（紅測 §4 第 3 條的 known-FAIL 構造法就是驗證這個順序；PO 複核已覆核此順序正確）。

`trend_discover.py` 的 `_generate_with_retry` 比照同一改法（同一 exception 類別，
從 `nlp_processor` import 或另放共用位置——提案傾向放在 `nlp_processor.py`，
`trend_discover.py` 已 import 該模組所在的 `src.transform` 套件路徑不衝突，
細節留給實作階段，不影響本提案的行為契約）。**v3 訂正**：`run_discovery()`
內部直接 `except GeminiDailyQuotaExhausted as exc: return "REFUSED", str(exc)[:500]`
接住（見 §3.1），不再需要 v2 提出的「`except GeminiDailyQuotaExhausted: raise`
連帶修正」——四態改為函式回傳值而非例外傳遞後，這個問題不存在了。

`run_nlp_sentiment_pipeline()` 需要新增 try/except（目前完全沒有，見 §2.4），
且依複核意見改為**三個必要參數皆預設 `None`，只在真正用到時才驗證**——
這樣既有三個測試檔（不觸發配額耗盡路徑的既有測試）呼叫端不必先改：

```python
def run_nlp_sentiment_pipeline(self, batch_size: int = 500, run_log_writer=None,
                                started_at=None, batch_key=None):
    """
    batch_key：**由呼叫端傳入，不在本方法內自行推導**——
    v1 草稿曾用 `started_at.date().isoformat()`；`started_at` 來自
    `now_taipei()` 所以今天不會錯，但這段程式碼與 `run_all_daily_tasks()`
    既有的 `tracked_batch_key` 是分開算的兩份日期，一旦日後有人把
    `started_at` 的來源改成 UTC，兩者就會錯開一天而不易察覺
    （同 §0.5 #32 起算點的教訓：時間衍生值只能有一個計算點）。
    生產路徑改傳 `run_all_daily_tasks()` 既有的 `tracked_batch_key`。
    """
    ...
    while True:
        df_raw = self.db_writer.fetch_data(query)
        if df_raw is None or df_raw.empty:
            break
        try:
            df_processed = self.nlp_processor.process_batch_hybrid(df_raw, self.db_writer)
        except GeminiDailyQuotaExhausted as exc:
            if run_log_writer is None or started_at is None or batch_key is None:
                # 生產路徑一定會傳這三項；缺任一項代表接線沒做完，
                # **靜默不落地比拋錯更危險**（配額耗盡會被誤讀成「今天沒新文章」）。
                raise ValueError(
                    "run_nlp_sentiment_pipeline() 撞到每日配額耗盡，但呼叫端未傳 "
                    "run_log_writer／started_at／batch_key，無法落地稽核紀錄——"
                    "生產路徑必須完整傳入這三項。"
                ) from exc
            remaining = self.db_writer.fetch_data(
                "SELECT COUNT(*) AS n FROM market_articles WHERE sentiment_score IS NULL;"
            )
            n_remaining = int(remaining.iloc[0]["n"]) if remaining is not None else -1
            run_log_writer.write(
                [RunLogEntry(SOURCE_NLP_GEMINI, batch_key, "daily_quota", REFUSED,
                             detail=f"剩餘 {n_remaining} 篇未評分，每日配額耗盡：{exc}"[:500])],
                started_at)
            print(f"[WARNING] NLP 每日配額耗盡，本次停止，剩餘 {n_remaining} 篇留待下次：{exc}")
            return
        self.db_writer.update_sentiment_scores(df_processed)
        ...
```

呼叫端（`run_all_daily_tasks()`）改為：

```python
self.run_nlp_sentiment_pipeline(batch_size=500, run_log_writer=run_log_writer,
                                 started_at=started_at, batch_key=tracked_batch_key)
```

`剩餘篇數` 用即時 `COUNT(*)` 查詢，不用 `len(df_raw)` 估——後者只反映本批次
（`LIMIT batch_size`），配額耗盡當下實際剩餘可能更多，`detail` 只能寫可觀測事實
（`etl_run_log.py` 的既有紀律），不能用推估值冒充精確數字。

`REFUSED` 帶 `detail` 符合 `chk_etl_run_log_detail`（`FETCH_FAILED`／`REFUSED`
皆要求 `detail`），不受 §3.1 決策影響。

**紅測 fixture 的例外訊息必須用 09-17 真實 log 原文**（複核意見，陷阱 2）：
`doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_log.txt`
第 404～426 行的完整原始例外字串（含 `quota_id: "GenerateRequestsPerDayPer
ProjectPerModel-FreeTier"` 那幾行），逐字複製進紅測 fixture，**不得自行編寫
一段「看起來含 PerDay」的訊息**——這是為了先確認 google 套件真實拋出的
`ResourceExhausted.__str__()` 確實包含 `quota_id` 字串本身，而不是只存在於
某個 `.args` 或需要額外屬性存取的欄位裡。

### 3.3 模型名釘死

新增常數（提案位置：`src/config.py`，本專案目前沒有這個檔案，需新建；
或退而求其次放 `main_etl_pipeline.py` 頂部再由兩處 import——提案傾向新建
`src/config.py`，因為 `trend_discover.py` 與 `nlp_processor.py` 之間目前沒有
互相 import 也沒有共同的第三方模組，新建一個小型設定檔比互相 import 更乾淨）：

```python
# src/config.py（新檔）
GEMINI_MODEL_NAME = "gemini-3.8-flash"
```

兩處改為：

```python
self.model = genai.GenerativeModel(GEMINI_MODEL_NAME)
```

### 3.4 既有映射不改權重

```python
# db_writer.py:735-739
ON CONFLICT (theme_keyword, stock_id)
DO NOTHING;
```

`INSERT ... VALUES %s ON CONFLICT (theme_keyword, stock_id) DO NOTHING` ——
`stock_name`／`relevance_weight`／`updated_at` 三欄在既有列上完全不變，
新配對正常插入。函式其餘部分（`if not records: return`、`print` 訊息）不動。

### 3.5 接線點彙總

`run_all_daily_tasks(self, run_discovery: bool = True)`——`run_discovery`
參數只影響 §3.1 的判斷分支，下一案（08:30 雙時點）會在呼叫端傳入 `False`，
本案不寫呼叫端。

## 4. Tests（先紅後綠，紅 FAIL 數＝新增測試數，逐條核對，`TEAM_PLAYBOOK.md` A13）

v3：9 條增為 **12 條**（複核第二輪追加 1b／6b／6c）。逐條標記檔案與 known-FAIL
構造法（送審前記憶體內突變照 PO 原訊息六項＋複核追加兩項，共八項，各執行一次）：

| # | 測試 | 檔案（提案） | known-FAIL 構造法 |
|---|------|-------------|-------------------|
| 1 | 最近一列 `outcome=OK` 距今 6 天跳過／7 天以上執行／從未探索過執行 | 新檔 `tests/test_gemini_quota_discipline.py` | mock `fetch_last_discovery_probed_date` 回傳 `today-6`／`today-7`／`None` 三種 fixture；**斷言（A4）**：`run_discovery()` 未被呼叫**且** `run_log_writer.write` 完全未收到任何 `ai_discovery` 列；`today-7` 與 `None` 兩案則相反（有呼叫、有寫列）。known-FAIL：故意讓跳過分支仍呼叫 `run_log_writer.write([...])`，斷言「不應有列」FAIL |
| 1b（複核 v3 新增） | 最近一列 `outcome=NO_DATA` 距今 6 天 → 跳過；最近一列 `outcome=FETCH_FAILED` 距今 1 天 → 執行（`NO_DATA` 算試過、`FETCH_FAILED` 不算） | 同上 | 把 `fetch_last_discovery_probed_date` 的查詢改成只認 `outcome='OK'`（不含 `NO_DATA`），第一個子案例（`NO_DATA` 距今 6 天應跳過）變成誤判執行，FAIL |
| 2 | `run_discovery=False` 不呼叫 `run_discovery()`，也不寫任何列 | 同上 | 不傳參數（用預設值 `True`）跑同一斷言，FAIL |
| 3 | `PerDay` 訊息只呼叫一次即拋 `GeminiDailyQuotaExhausted` | 同上（對應 `nlp_processor.py`） | 把 `_is_daily_quota_exhausted` 判斷式移到 `_is_transient_exception` 判斷**之後**，重試 5 次才拋，mock `generate_content` 呼叫次數斷言從 1 變 5，FAIL |
| 4 | 每分鐘 429（不含 `PerDay`）仍重試 | 同上 | 反向構造：故意讓 `_is_daily_quota_exhausted` 永遠回 `True`，一般 429 也被誤判成每日配額不重試，斷言「應重試多次」FAIL |
| 5 | NLP 撞配額：`etl_run_log` 有 `nlp_gemini/daily_quota/REFUSED`，流程繼續到 `generate_daily_features`，`fetch_failed_source_keys` 在其後被呼叫 | 同上 | 拿掉 try/except（模擬未修復前狀態），例外直接穿透，`attach_mock` 斷言不到後續呼叫，FAIL |
| 5b | `run_log_writer`／`started_at`／`batch_key` 任一為 `None` 時撞配額 → 拋 `ValueError`（而非靜默吞掉不落地） | 同上 | 把 `if ... is None: raise ValueError(...)` 改成 `pass`（靜默略過），斷言「應拋出 ValueError」FAIL |
| 6 | 探索撞配額：`run_discovery()` 內部接住並回傳 `("REFUSED", detail)`，呼叫端記 `ai_discovery/REFUSED`，流程繼續 | 同上 | 讓 `run_discovery()` 的 `except GeminiDailyQuotaExhausted` 分支改成不 `return`、繼續往下跑（模擬漏接），斷言「應立刻回傳 REFUSED」FAIL |
| 6b（複核 v3 新增） | 探索非配額失敗（mock `_fetch_recent_hot_titles` 回 `None`，或 mock `_generate_with_retry` 拋非配額例外）→ `run_discovery()` 回傳 `("FETCH_FAILED", detail)`，呼叫端記 `ai_discovery/FETCH_FAILED` 帶 detail，流程繼續 | 同上 | 用現行（v2 以前）的靜默 `return` 邏輯跑同一 fixture，呼叫端誤記成 `OK`，斷言「應為 FETCH_FAILED」FAIL |
| 6c（複核 v3 新增） | Gemini 回答有效但無可新增詞（`new_keywords` 為空）→ `run_discovery()` 回傳 `("NO_DATA", None)` | 同上 | 同 6b，用現行邏輯跑，誤記成 `OK`，FAIL |
| 7 | 兩處模型名同一常數、不含 `latest` | 同上 | 其中一處改回硬寫字串，斷言兩個 `.model` 的來源常數相等，FAIL；另加 `assert "latest" not in GEMINI_MODEL_NAME` |
| 8 | 既有映射 upsert 不改權重／新配對正常插入（同一 fixture 兩種列） | `tests/test_thematic_mapping.py`（已有同主題測試，延續而非新開檔） | 改回 `DO UPDATE`，既有列權重被 mock 回傳值覆蓋，斷言 FAIL |
| 9 | 非配額例外仍中止（**僅適用 NLP 路徑**——探索路徑的所有例外已在 `run_discovery()` 內部被四態分類接住，不會再向外拋出，見 §3.1） | `tests/test_gemini_quota_discipline.py` | 把 `GeminiDailyQuotaExhausted` 的 `except` 子句改成裸 `except Exception`，非配額例外也被吞掉，斷言「例外應向上傳遞」FAIL |

第 3、5、6 條的例外訊息 fixture 一律使用 `FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_
20260917_log.txt:404-426` 的原文（§3.2 複核意見陷阱 2），不得自行編寫。

**送審前記憶體內突變清單**（八項，各實際執行一次並貼原始 FAIL 輸出）：仍重試 5
次、`PerDay` 判斷反向、跳過探索不記 log（v3：改為「跳過仍寫列」，見測試 1）、
`DO NOTHING` 改回 `DO UPDATE`、參數 `False` 仍呼叫探索、NLP 例外仍拋出中止、
**（v3 新增）五個 `return` 任一改回靜默 `return`**、**（v3 新增）成功查詢只認
`OK`（不含 `NO_DATA`）**。

## 5. Affected Components

- `src/extractors/trend_discover.py`（模型常數；`run_discovery()` 改回傳
  `(outcome, detail)` 四態，五個靜默 `return` 全部改寫；`_generate_with_retry`
  加 `GeminiDailyQuotaExhausted` 判斷）
- `src/transform/nlp_processor.py`（模型常數、`GeminiDailyQuotaExhausted` 類別與判斷）
- `main_etl_pipeline.py`（`run_all_daily_tasks` 探索段改寫為讀取 `run_discovery()`
  回傳值並記錄、`run_nlp_sentiment_pipeline` 加 try/except 與 run_log 寫入、
  新增 `SOURCE_AI_DISCOVERY`／`SOURCE_NLP_GEMINI` 常數）
- `src/loaders/db_writer.py`（`upsert_theme_stock_mapping` 改 `DO NOTHING`；新增
  `fetch_last_discovery_probed_date()`）
- `src/config.py`（新檔，`GEMINI_MODEL_NAME`）
- 測試：`tests/test_gemini_quota_discipline.py`（新檔）、`tests/test_thematic_mapping.py`（延續）

**不改**：`etl_run_log` 的 migration（§2.7 已確認不需要）、排程器（下一案）、
`feature_aggregator.py`（DEC-039 機制本身不變，只是減少 #33 這個新增觸發源）。

## 6. 段 B（拋棄式庫演練，從最新 POST 備份還原）

依 PO 訊息 2.6 四項照辦，依決策點 A（A4）與 §3.2 REFUSED 訂正調整驗收措辭：

1. 配額耗盡整日執行：5 篇文章 `sentiment_score` 設回 `NULL`（合成操作，報告揭露）
   → NLP 只嘗試 1 次、`etl_run_log` 有 `nlp_gemini/daily_quota/REFUSED` 列、
   特徵階段完成、5 篇對應鍵 `SOURCE_FAILED`、exit 0。
2. 探索——v3 拆為三個子場景（複核 v3 要求）：
   - 2a 距上次「有問過」（`OK`／`NO_DATA`）不足 7 天 → 0 次探索呼叫、`etl_run_log`
     **不出現** `ai_discovery` 列（A4）。
   - 2b mock `_fetch_recent_hot_titles` 回 `None`（掃頁失敗）→ `etl_run_log` 有
     `ai_discovery/FETCH_FAILED` 列且帶 `detail`。
   - 2c mock Gemini 回應有效但無新詞（`{"trends": []}`）→ `etl_run_log` 有
     `ai_discovery/NO_DATA` 列、`detail` 為 `None`。
   演練報告需逐一列出 1、2a、2b、2c 四種情況各自的 `etl_run_log` 查詢結果對照。
3. 映射不改：既有映射權重改 0.50，mock 探索回傳同配對權重 0.90 → 執行後仍 0.50、
   `updated_at` 不變。
4. 零真實 Gemini 呼叫（全程 mock）；容器只 `docker rm`（§11A，絕不 `docker rmi`）。
5.（複核第三輪追加）**整條管線場景 1b**：1～4 都只直接呼叫被測方法本身，
   未驗證呼叫端接線（探索閘門段落、`run_log_writer`／`started_at`／
   `tracked_batch_key` 傳入 `run_nlp_sentiment_pipeline()` 那一行）——這些只有
   單元測試用 mock 走過。比照 §0.5 #32 段 B 第 2 項的配方：批次取價／逐股／
   `run_us_stock_pipeline`／`run_ptt_board_pipeline` 全部 mock 掉，探索與 NLP
   對拋棄式庫真跑完整 `run_all_daily_tasks()`。合成 1 篇文章 `sentiment_score`
   設回 `NULL`；NLP `generate_content` 拋 `PerDay` 原始訊息；探索因
   `last_probed=None` 真的走到 `run_discovery()`，其 `generate_content` mock
   回 `{"trends": []}`。預期：`ai_discovery/NO_DATA` 一列、
   `nlp_gemini/daily_quota/REFUSED` 一列且 `batch_key` 為當天台北日期
   （證明傳的是 `tracked_batch_key`）、特徵與尾端階段完成、exit 0。

## 7. 段 C（下一次真實每日執行）

> **v3 段 B 複核後訂正**：v3 原文預期「探索 0 次（距 09-18 不足 7 天）」不成立——
> 段 B 演練發現真實庫從未寫過任何一列 `source='ai_discovery'`（本 SB 09-18
> 第二次每日 ETL 執行時尚未接線），`fetch_last_discovery_probed_date()` 在
> 段 C 第一次真實執行時會是 `None`，依設計就是要探索一次。這是判準正確運作
> 的結果，PO 明確裁決**不得**為了讓舊預期成立而在真實庫預先插一列 OK 偽造
> 觀測。預期改寫如下。

第三次真實每日 ETL，RISK-013 協議＋綁定確認。預期 Gemini：探索 **1** 次
（`last_probed=None`，真實呼叫）＋ NLP 依新文章數 1～2 次，合計 ≤ 3 次。
探索結果不論 `OK`／`NO_DATA` 都會寫一列，寫下之後 7 天內再次執行會跳過。
若探索撞每日配額，記 `REFUSED`、流程繼續（**不是**中止）——這是本案第一次
在真實庫走這條新路徑，若真的發生，仍照 §四.4 停下回報，不逕行判定為預期內。
驗收沿用既有五條，加：`etl_run_log` 出現 **恰 1** 列 `ai_discovery`
（`OK` 或 `NO_DATA`）且**無** `nlp_gemini` 列（除非真的撞配額）；
`theme_stock_mapping`——因 `DO NOTHING` 已生效，若探索回傳既有配對則零變動，
若為新配對才會插入（新股票的情緒欄變動落在既有驗收條件 2(a) 範圍內，
不是本案新增的驗收項）；既有映射列的 `updated_at` 最大值必須維持不變
（`pg_restore --data-only` 對照 PRE／POST，同 §0.5 #32 的驗證手法）。

## 8. 文件

- `REMAINING_RISKS.md`：RISK-031 改狀態，措辭：「已確認僅本專案使用該 Gemini
  key（PO 2026-09-18 查用量主控台，`REPORTED, NOT INDEPENDENTLY VERIFIED`）；
  用量縮減已落地（本案 DEC-043）」
- `PROJECT_STATUS.md`：#31、#33 → CLOSED
- 新 ADR `DEC-043`，Decision 五條（v3 增列第 5 條）：
  1. 探索頻率改每週一次（`DISCOVERY_INTERVAL_DAYS=7`，以最近一列
     `outcome ∈ {OK, NO_DATA}`（「有問過」）的 `batch_key` 計算，見 §3.1；
     `NO_DATA` 也算試過，`FETCH_FAILED`／`REFUSED` 不算、隔天即可再試）
  2. 規則性跳過（未達週期或呼叫端關閉）**不寫 `etl_run_log`**（決策點 A，
     PO 裁決 A4——理由：`NO_DATA` 語意是「請求成功但無內容」，跳過不構成一次
     請求，沒有 outcome 可記；v1 曾提出的 A1/A2/A3 已否決）。**與第 1 條的
     差異**：跳過不寫列，但「探索有跑、內容剛好是空」要寫 `NO_DATA`——兩者
     外觀都是「沒有新東西」，但一個是我方沒問，一個是問了沒有，語意不同
     （見第 5 條）。
  3. 每日配額耗盡（訊息含 `PerDay`）：不重試，`outcome=REFUSED`（服務主動
     叫停，非抓取失敗），流程繼續（探索與 NLP 各自的下游階段不因此中止）
  4. `upsert_theme_stock_mapping()` 改 `ON CONFLICT DO NOTHING`——既有映射的
     權重／名稱／`updated_at` 不再被探索結果覆寫
  5. **`run_discovery()` 改為回傳 `(outcome, detail)` 四態，例外不跨越函式
     邊界**（複核第二輪發現：原有五種靜默 `return` 全部會被呼叫端誤記成
     `OK`，其中三種其實是失敗——缺 API key、PTT 掃頁失敗、Gemini 回應無效
     三者記 `FETCH_FAILED`；熱門標題為空、Gemini 回應有效但無新詞兩者記
     `NO_DATA`；正常寫入記 `OK`；配額耗盡記 `REFUSED`）

  模型名常數化（`src/config.py::GEMINI_MODEL_NAME`）屬實作細節，寫在
  Consequences／Trade-offs，不列為單獨的 Decision 條目。
- `SYSTEM_UPGRADE_MASTER_PLAN.md`：若有探索頻率的既有描述，同步

## 9. Definition of Done

- 全套測試 `OK`（容器內，`python -m unittest discover -s tests -p "test_*.py"`）
- `gate0_contract_check.py` exit 0
- 段 B 四項演練全部通過，含 known-FAIL 案例已實際執行並復原確認
- 段 C 真實執行五條驗收 PASS，含 `etl_run_log`／`theme_stock_mapping` 的
  `postgres`@`localhost:5432` 上實測（依 `gate-submit` 產出 7，指名資料庫）
- DEC-043 已建立（狀態 `PROPOSED`，待 PO 核准）
- RISK-031 狀態更新；#31／#33 於 `PROJECT_STATUS.md` 標記 CLOSED（待 PO 裁決後）

## 10. 流程

v2 已依複核第一輪意見修訂決策點 A（採 A4）、配額耗盡 outcome（`FETCH_FAILED`→
`REFUSED`）、`run_nlp_sentiment_pipeline()` 的 `batch_key` 來源與 `ValueError`
設計、紅測 fixture 來源（09-17 真實 log 原文）。v3 依複核第二輪意見修訂
`run_discovery()` 的五個靜默 `return`，改為回傳四態元組，「上次成功」判準改為
`OK`／`NO_DATA` 皆算，紅測 9 條增為 12 條，段 B 探索演練拆為四個子場景。
本版再送 `sps_project_reviewer` 複核，依複核意見「這輪只看第二節有沒有落實」，
複核通過後請 PO 核准，核准後才進紅測（「紅測寫完先回報」慣例不變）。
