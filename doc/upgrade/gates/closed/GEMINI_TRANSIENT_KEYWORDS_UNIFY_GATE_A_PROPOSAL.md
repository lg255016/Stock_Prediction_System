# Gate A 提案：統一 `trend_discover.py`／`nlp_processor.py` 的 Gemini 暫態例外判斷清單（§0.5 #36）

## 0. 摘要

`trend_discover.py`／`nlp_processor.py` 各自維護一份「哪些例外算暫態、值得退避重試」的關鍵字清單，兩份清單是**真包含關係**（前者是後者的子集）。2026-09-19 第三次真實每日 ETL 撞到 `DeadlineExceeded: 504 Deadline expired before operation could complete.` 時，`nlp_processor` 端的清單含 `deadline`、會判為暫態退避重試，`trend_discover` 端不含、直接拋出——**同一類錯誤在兩條路徑上結果不一致，這是本案要修的問題**。

修法**不是**把兩份清單合一後補上 `504`／`deadline`（v1 曾這樣提，經 PO 裁決推翻，見 §3.2）。`DeadlineExceeded` 是同一份 prompt 跑超過期限，用一模一樣的內容重送沒有理由變快——最可能的結果是把重試次數全部燒在注定再次逾時的請求上，直接抵銷 #31 才剛省下來的每日配額。**裁決結果：`deadline`／`504` 兩條路徑都判為非暫態、都不重試**，做法是清單取 `nlp_processor` 現有 10 項的聯集後**移除 `deadline`**、**不新增 `504`**（`504` 這個數字本來就不在任一份現行清單裡，維持不新增）。

修法本身仍是「兩處改為共用同一份判斷邏輯」——不一致的問題照樣解決，只是解決方向從「兩邊都能重試」反過來變成「兩邊都不重試」。共用邏輯抽成獨立模組，**刻意不**塞進既有的 `retry_policy.py`（見 §3.1，塞入會讓 Gemini 例外被系統性誤判為不可重試，比兩份清單不一致更嚴重）。

本案純程式碼＋單元測試，不寫入真實庫，不需要段 B 拋棄式演練。

## 1. Requirement Source

`PROJECT_STATUS.md` §0.5 #36（2026-09-19，第三次真實每日 ETL，PO 複核唯讀查證發現）；本次開案工作單（2026-09-20/21，審查方唯讀查證＋PO 轉達，見 §3 逐項設計要求）。

## 2. Current State（唯讀查證，容器內程式碼閱讀，`VERIFIED THIS SESSION`）

### 2.1 兩份清單的實際內容與真包含關係——確認工作單陳述屬實

```python
# src/extractors/trend_discover.py:73
retry_keywords = ["429", "quota", "rate limit", "resourceexhausted", "503", "timeout"]

# src/transform/nlp_processor.py:112-115
retry_keywords = [
    "429", "quota", "rate limit", "resourceexhausted", "resource_exhausted",
    "503", "unavailable", "timeout", "deadline", "connection error"
]
```

`trend_discover` 的 6 個關鍵字全部存在於 `nlp_processor` 的 10 個關鍵字中，逐一比對確認：**是真子集，不是各有長短**。兩份清單**都不含 `"504"`**（逐字掃描確認，非子字串誤判——`resourceexhausted`／`unavailable` 等詞本身不含 `504` 這個數字序列）。

### 2.2 每日配額判斷的呼叫順序——`nlp_processor` 端已正確，`trend_discover` 端透過 import 共用同一份，兩邊順序皆正確

```python
# src/transform/nlp_processor.py:23-27
def is_daily_quota_exhausted(exc: Exception) -> bool:
    """判斷順序上的前提：必須排在一般 `quota` 關鍵字判斷之前呼叫——
    每日配額訊息同時含 "quota" 與 "PerDay"，若順序反過來，一般 quota
    判斷會先命中，這個分支永遠執行不到"""
    return "PerDay" in str(exc)
```

`src/extractors/trend_discover.py:11` 直接 `from src.transform.nlp_processor import GeminiDailyQuotaExhausted, is_daily_quota_exhausted`——**這個共用函式已經存在跨模組共用的precedent**：`trend_discover` 從 `nlp_processor` import 它，而不是各自維護一份。這是 DEC-043（決策 3）的落地，本案不動。

呼叫端順序核對：`nlp_processor.py:139`（`is_daily_quota_exhausted` 判斷）在 `nlp_processor.py:144`（`_is_transient_exception` 判斷）**之前**；`trend_discover.py:95-96` 同樣先判 `is_daily_quota_exhausted` 才進入退避重試迴圈。兩邊順序皆正確，**本案新增的合併清單不得破壞這個既有順序**（見 §3.2 硬條件）。

### 2.3 退避參數——兩邊完全相同，非本案要改的部分

```python
# 兩處皆為：
sleep_sec = min(2 ** attempt, 16)   # attempt=1..5 → 2,4,8,16,16
max_retries: int = 5                 # trend_discover._generate_with_retry
                                      # nlp_processor._generate_content_with_retry
```

單次事件若每次重試都撞暫態錯誤，最多重試 5 次、總退避時間 2+4+8+16+16=46 秒——與工作單描述一致。

### 2.4 `retry_policy.py` 不適合收留本案——確認工作單陳述屬實，且實際後果比工作單描述的更嚴重

```python
# src/extractors/retry_policy.py:54,61
def is_retriable(exc) -> bool:
    if not isinstance(exc, requests.exceptions.RequestException):
        # 解析錯誤、程式錯誤等：重試不會改變結果。
        return False
    ...
```

`is_retriable()` 的第一道判斷就是 `isinstance(exc, requests.exceptions.RequestException)`——Gemini SDK（`google.generativeai`）拋出的例外**不是** `requests.exceptions.RequestException` 的子類別。這意味著：**若直接把 Gemini 的暫態例外丟進 `is_retriable()` 判斷，會無條件命中第一個 `if`、回傳 `False`**——所有 Gemini 暫態錯誤（含 429／503／504／deadline）都會被系統性誤判為「不可重試」。

這不只是「兩種語意混在一份判準裡不乾淨」（工作單原本的說法），是**會產生實際錯誤行為的後果**：如果哪個呼叫端誤以為 `is_retriable()` 對 Gemini 例外也適用，Gemini 路徑的重試會整條失效。本案不修改 `retry_policy.py`，也不讓 Gemini 判斷邏輯依賴它。

### 2.5 兩處目前皆無直接單元測試覆蓋 `_is_transient_exception` 本身

`tests/` 內與這兩個模組相關的測試集中在 `tests/test_gemini_quota_discipline.py`，其中僅 `test_3_per_day_message_raises_once_without_retry`／`test_3b_discovery_retry_classifies_raw_per_day_message` 涉及例外分類，且只測 `PerDay` 分支。**清單本身（哪些字算暫態）目前完全沒有直接測試**——這正是兩份清單漂移到真包含關係、且都漏 `504`，卻在 #31/#33 整個 Gate/SB 週期與段 B 拋棄式演練中都未被發現的原因：沒有任何測試斷言過清單的具體內容。

### 2.6 真實例外原文（供 §4 fixture 使用，`VERIFIED THIS SESSION`）

**504／DeadlineExceeded**（`doc/upgrade/gates/evidence/GEMINI_QUOTA_DISCIPLINE_real_run_20260919_success.md:129-130`，2026-09-19 第三次真實每日 ETL 探索階段實際撞到）：

```
DeadlineExceeded: 504 Deadline expired before operation could complete.
```

**PerDay 每日配額**（`doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_log.txt:404-425`，2026-09-17 首次真實每日 ETL NLP 階段實際撞到，節錄關鍵片段）：

```
429 You exceeded your current quota, please check your plan and billing details. ...
* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash
Please retry in 53.170503096s. [links {...}
, violations {
  quota_metric: "generativelanguage.googleapis.com/generate_content_free_tier_requests"
  quota_id: "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
  quota_dimensions { key: "model" value: "gemini-3.8-flash" }
  quota_dimensions { key: "location" value: "global" }
  quota_value: 20
}
, retry_delay { seconds: 53 }
])
```

## 3. 設計提案

### 3.1 共用實作的位置——新建 `src/common/gemini_retry.py`，不放 `src/config.py`，不放 `retry_policy.py`

**三個候選與判定：**

| 候選 | 判定 | 理由 |
|------|------|------|
| `src/extractors/retry_policy.py` | **不採納** | §2.4 已證實：`is_retriable()` 的 `isinstance` 守門會讓 Gemini 例外被誤判為不可重試，不是「混合兩種語意」而是「塞進去就是錯的」 |
| `src/config.py` | **不採納** | 現有內容只有常數（`GEMINI_MODEL_NAME` 等，見 #31/#33），本案要放的是**判斷邏輯**（一個函式），與該檔既有定位不符——加進去會讓 `config.py` 從「純常數設定檔」變成「常數＋邏輯混合檔」，是本案自己要避免的那種不一致的翻版 |
| **`src/common/gemini_retry.py`（新建）** | **採納** | 見下方理由 |

**採用新建模組的理由**：

1. `src/common/` 目前尚不存在對應的 Gemini 共用邏輯目錄（`src/common/clock.py` 是既有先例，本案是同一種「跨模組共用、不屬於任何單一 pipeline 階段」的定位）。
2. `nlp_processor.py`（`src/transform/`）與 `trend_discover.py`（`src/extractors/`）分屬不同 pipeline 階段，**新模組不偏向任一邊**——若把清單放進 `nlp_processor.py`（延續 §2.2 已有的 import 先例），會讓 `trend_discover` 對 `nlp_processor` 的依賴從「只借用配額例外類別」擴大成「連暫態判斷邏輯都靠它」，兩個依賴的性質不同（前者是共用資料型別，後者是共用行為邏輯），混在一起會讓 `nlp_processor.py` 承擔它名稱之外的職責。
3. **明確不做**：不把 `GeminiDailyQuotaExhausted`／`is_daily_quota_exhausted()` 從 `nlp_processor.py` 一併搬過去——那是 DEC-043 已核准、真實庫已驗證過的穩定機制，本案範圍是「統一暫態關鍵字清單」，搬動既有穩定機制屬於範圍外變更，且會讓本次 diff 混入與 #36 無關的改動。

### 3.2 清單內容——`nlp_processor` 現有 10 個關鍵字移除 `deadline`，不新增 `504`；`PerDay` 判斷順序為硬條件（PO 2026-09-21 裁決，推翻 v1 的「合一後補 504」方向）

```python
# src/common/gemini_retry.py（新建）
GEMINI_TRANSIENT_KEYWORDS = [
    "429", "quota", "rate limit", "resourceexhausted", "resource_exhausted",
    "503", "unavailable", "timeout", "connection error",
]

def is_transient_gemini_exception(exc: Exception) -> bool:
    exc_str = str(exc).lower()
    return any(k in exc_str for k in GEMINI_TRANSIENT_KEYWORDS)
```

九項，逐項核對來源：`nlp_processor` 現行 10 項（§2.1）扣除 `deadline`（`VERIFIED THIS SESSION`：`set(original) - set(proposed) == {"deadline"}`，`set(proposed) - set(original) == set()`，無其他增減）。`trend_discover` 現行清單本來就是這 10 項的子集，此次同樣適用聯集邏輯——只是聯集的結果現在是「扣除 deadline 後的九項」，兩路徑統一採用。

**本次修改的影響面——封閉式證明，不採語料掃描**（`VERIFIED THIS SESSION`）：語料掃描（對既有 log／文件裡出現過的真實訊息逐條套用新舊清單比對）曾被考慮作為佐證，但**這是抽樣，不是證明**——掃描結果會隨掃描範圍（掃哪些檔案、正則寬窄、是否去重）而變動（三種掃法分別得到 190／127／27 段候選、對應 1／9／8 段變化，彼此不一致），無法作為「除了 deadline 沒有其他錯誤類型受影響」這個宣稱的可重跑證據，故不採用、不寫入本提案。

正確的證明是封閉式的，因為 `OLD = NEW ∪ {"deadline"}`（上段已驗算）且判定式是 `any(k in msg.lower() for k in 清單)`——集合聯集下 `any(...)` 具單調性，故：

```
old_match(msg) = new_match(msg) or ("deadline" in msg.lower())
```

兩者的判定結果不同，**若且唯若** `msg` 含 `"deadline"` 字串、且不含九項保留關鍵字中的任何一個：

```python
changed = ("deadline" in msg.lower()) and not any(k in msg.lower() for k in NEW)
```

用 500,000 組隨機合成訊息（含真實關鍵字混合、隨機雜訊子字串）窮舉核對 `old_match(msg) != new_match(msg)` 與上式是否一致，**不一致次數為 0**。四個邊界案例逐一核對：

| 訊息 | `old_match` | `new_match` | 是否改變 |
|---|---|---|---|
| `DeadlineExceeded: 504 Deadline expired before operation could complete.`（§2.6 真實訊息） | `True` | `False` | **改變**（含 `deadline`，九項皆不命中） |
| `deadline exceeded after timeout` | `True` | `True` | 不變（`timeout` 命中，九項判準仍成立） |
| `429 quota exceeded` | `True` | `True` | 不變（不含 `deadline`） |
| `503 Service Unavailable` | `True` | `True` | 不變（不含 `deadline`） |

這個論證不依賴任何語料樣本、不隨掃描範圍改變，任何人重跑同一段程式碼都得到同一個結論：**本次修改只會改變「含 `deadline` 且不含其餘九項關鍵字」的訊息分類，不會影響任何其他類型的錯誤判定。**

**為什麼移除 `deadline`（決策理由，非結果陳述）**：`DeadlineExceeded` 代表同一份 prompt 已經跑到逾時上限——**用一模一樣的內容原地重送，沒有機制讓伺服器端在期限內算得更快**，重試换来的期望結果是再次逾時，白白燒掉配額。這與 429（等待期過了配額就恢復）、503（伺服器忙完就正常）性質不同：後兩者的「稍等重試」有明確的物理機制支持會變好，deadline 沒有。09-19 真實事件已經證實「不重試」的路徑可行——探索撞 504 未重試、記成 `FETCH_FAILED`（不算「已問過」）、後續階段全部完成、`exit 0`；`FETCH_FAILED` 語意誠實，下週探索排程會自然再試一次，NLP 端同理靠既有 checkpoint／`SOURCE_FAILED` 機制自然回補，**不重試的代價是有界且已知的**，不是未知風險。

**為什麼保留 `timeout`（避免與上一段自相矛盾）**：`timeout` 與 `deadline` 語意不同——連線層逾時（TCP handshake、TLS 交握、等待首個 byte）可能在請求根本還沒送達 Gemini 伺服器、伺服器完全不知道我們問了什麼的階段就發生，這種情況下重試不是「用同樣的內容再求一次已經跑不完的運算」，而是「再給一次連線機會」，與 `retry_policy.py`（DEC-032）對「拿不到 `status_code`」歸類為可重試的邏輯同構（§2.4）。`deadline` 則是請求已經被伺服器接手、只是沒能在期限內做完——兩者發生的層次不同，值得重試的理由也不同，因此保留 `timeout`、移除 `deadline`。

**不新增 `504`**：`504` 這個數字字串本來就不在任一份現行清單裡，本次修法不新增它——`504` 對應的 `DeadlineExceeded` 已經被 `deadline` 這個詞面判準涵蓋（§2.6 真實訊息「小寫後含 `504` 也含 `deadline`」），加了 `504` 反而會讓 504 訊息透過數字字串命中變成暫態，與移除 `deadline` 的決策矛盾，所以兩件事一起做才自洽。

**硬條件（不可違反，不變）**：兩處呼叫端必須維持「先判 `is_daily_quota_exhausted()`，再判 `is_transient_gemini_exception()`」的既有順序（§2.2）。本案**不改動** `is_daily_quota_exhausted()` 的定義或位置，只改動 `_is_transient_exception` 這一段邏輯的來源。

### 3.3 配額取捨——v1 的三選項連同其前提一併撤回

v1 §3.3 曾列三個選項（維持 `max_retries=5`／降為 3／504 單獨設更低上限），三者共同前提是「504 應該重試，只是重試幾次」。PO 裁決不接受這個前提（§3.2）——`deadline`／504 兩路徑都不重試，`max_retries` 因此**維持 5 不動**，不需要在 429／503 這些確實值得等待的錯誤上讓步重試韌性。v1 §3.3 的量化分析（免費層 20 次/日、探索每週一次、退避序列 2/4/8/16/16）本身沒有錯，只是建立在一個已被推翻的前提上，故不再作為裁決依據保留，僅留紀錄於本節標題供追溯。

### 3.4 兩處呼叫端改為引用共用函式

```python
# src/extractors/trend_discover.py
from src.common.gemini_retry import is_transient_gemini_exception

@staticmethod
def _is_transient_exception(exc: Exception) -> bool:
    return is_transient_gemini_exception(exc)

# src/transform/nlp_processor.py 同樣改法
```

保留各自的 `_is_transient_exception` 方法名（呼叫端介面不變，只換內部實作來源）——避免同時改動呼叫端方法簽章，縮小本次 diff 範圍。

## 4. Tests（先紅後綠，紅 FAIL 數＝新增測試數，`TEAM_PLAYBOOK.md` A13）

新測試檔：`tests/test_gemini_transient_keywords_unify.py`

| # | 測試 | Fixture 來源 | Known-FAIL 構造法（對現行程式碼） |
|---|------|-------------|------------------------------|
| 1 | `trend_discover._is_transient_exception` 與 `nlp_processor._is_transient_exception` 皆呼叫同一個 `is_transient_gemini_exception`（用 `unittest.mock.patch` 替換 `src.common.gemini_retry.is_transient_gemini_exception` 後，確認兩處呼叫都命中 mock，而非用 `is` 比較函式物件——兩處各自是 `staticmethod`，比較的應是它們內部呼叫的目標） | — | 對現行程式碼：`src.common.gemini_retry` 模組不存在，`ImportError`，FAIL |
| 2 | §2.6 的真實 504 原文（`DeadlineExceeded: 504 Deadline expired before operation could complete.`）在**兩條路徑都判為非暫態**（`VERIFIED THIS SESSION`：該原文小寫後含 `504`／`deadline`，不含 `timeout`／`quota`／`429`／`503`，對新清單九項逐一比對皆不命中） | §2.6 | **對現行 `trend_discover._is_transient_exception`：PASS**（現行清單本來就缺 `504`／`deadline`，本來就回傳 `False`，行為不變）。**對現行 `nlp_processor._is_transient_exception`：FAIL**（現行清單含 `deadline`，會誤判為 `True`）——**本案這條測試的紅燈落在 NLP 側，不是探索側**，與 v1 提案的預期方向相反，紅測報告需明確標註 |
| 3 | `deadline` 訊息在**兩條路徑都判為非暫態**（不依賴 `504`，只依賴 `deadline` 這個詞本身，隔離變因） | 合成訊息 `"DeadlineExceeded"`（不含數字 504） | **對現行 `trend_discover._is_transient_exception`：PASS**（現行清單本來就缺 `deadline`，行為不變）。**對現行 `nlp_processor._is_transient_exception`：FAIL**（現行清單含 `deadline`，會誤判為 `True`）——同測試 2，紅燈落在 NLP 側 |
| 4 | §2.6 的真實 PerDay 原文在**兩條路徑**都不重試、直接拋 `GeminiDailyQuotaExhausted`，且底層 mock 的呼叫次數為 1（釘住 §3.2 硬條件：`is_daily_quota_exhausted` 必須先於暫態判斷執行） | §2.6 | 對現行程式碼：兩處目前已正確處理 PerDay（§2.2），此測試預期本來就 PASS——**作為順序不被破壞的防回歸鎖定，非本案要修的缺陷**，紅測階段此條不計入「新增測試數＝FAIL 數」的紅燈；需在提案與紅測報告中明確標註此條的角色 |
| 5 | 非暫態例外（`ValueError("bad json")`）在兩條路徑都立即拋出、不重試 | 合成 | 對現行程式碼：已正確（同上，防回歸鎖定，非紅燈） |
| 6 | 兩個模組的原始碼內**不再**各自保留字面 `retry_keywords = [...]` 清單（讀取 `trend_discover.py`／`nlp_processor.py` 原始碼文字，斷言舊清單字面量已被替換為對 `is_transient_gemini_exception`／`GEMINI_TRANSIENT_KEYWORDS` 的引用） | — | 對現行程式碼：兩處都還有字面清單，FAIL |

**紅測結果的預期讀法**：新增 6 條測試中，**4 條對現行程式碼會 FAIL**（#1 ImportError、#2、#3、#6），**2 條（#4、#5）預期本來就 PASS**——因為它們鎖定的是「本案不能破壞的既有正確行為」而非「本案要修的缺陷」。**#2／#3 的 FAIL 來自 `nlp_processor` 側（該模組現行清單含 `deadline`，會誤判為暫態），`trend_discover` 側對這兩條測試本來就 PASS（現行清單本來就沒有 `deadline`）**——紅測報告必須逐條標明是哪一側 FAIL，不得只報告「#2/#3 FAIL」的總數，避免與 v1 提案「FAIL 在探索側」的舊預期混淆。若 #4／#5 在紅測階段意外 FAIL，代表對現行程式碼的理解有誤，需停下查明而非調整斷言。

**送審前突變測試（記憶體內，不落地）**：
- **把 `deadline` 加回新清單**，確認測試 #2／#3 轉為 FAIL（兩條測試的「兩路徑皆非暫態」斷言會在 `deadline` 存在時被打破——`nlp_processor` 側原本就會 FAIL 的邏輯不變，但此時 `trend_discover` 側也會一併轉為 FAIL，等於驗證這兩條測試確實鎖定了「兩路徑都不含 deadline」這件事，而不是只鎖定單一側）。
- 把 `is_daily_quota_exhausted` 判斷搬到 `is_transient_gemini_exception` 判斷之後，確認測試 #4 轉為 FAIL（因為 PerDay 訊息同時含 `quota`，會被暫態判斷先攔截，重試次數不再是 1）。
- 讓兩處各自保留一份獨立清單字面量（不改為引用共用函式），確認測試 #6 轉為 FAIL。

## 5. Affected Components

- `src/common/gemini_retry.py`（新建）
- `src/extractors/trend_discover.py`（`_is_transient_exception` 改為委派，移除本地清單）
- `src/transform/nlp_processor.py`（同上）
- `tests/test_gemini_transient_keywords_unify.py`（新建）

**明確不動**：`src/extractors/retry_policy.py`（§3.1 已排除）、`src/config.py`（§3.1 已排除）、`is_daily_quota_exhausted()`／`GeminiDailyQuotaExhausted`（§3.1 點 3 已排除）、兩處的 `max_retries` 數值（§3.3，PO 裁決維持 5 不動，不隨本案調整）。

## 6. Definition of Done

- [ ] 紅測：6 條測試中 4 條對現行程式碼 FAIL（#1/#2/#3/#6），2 條 PASS（#4/#5，防回歸鎖定），逐條核對，非籠統宣稱；**#2/#3 的 FAIL 需標明落在 `nlp_processor` 側，`trend_discover` 側對這兩條本來就 PASS**
- [ ] 綠燈後 6 條全數 PASS
- [ ] 送審前 3 項記憶體內突變（§4 末段）逐一驗證會被對應測試抓到
- [ ] 全套測試 `python -m unittest discover -s tests -p "test_*.py"` 無回歸
- [ ] `python scripts/verify/gate0_contract_check.py` exit 0（本案不動任何契約文件，預期無影響，仍需執行確認）
- [ ] numstat／`-w` 無落差
- [ ] 綠燈 commit 同時新增 ADR（狀態 `PROPOSED`），Decision 理由欄需包含 PO 裁決的核心論點——**「同一份 payload 重送不會讓伺服器端 deadline 變短，因此 deadline／504 類錯誤不列為可重試」**——這是本案真正的判斷依據，不是清單長短的問題；日後若有人想把 `504`／`deadline` 加回可重試清單，需先在該 ADR 的基礎上提出推翻理由，而非直接改程式碼

## 7. 流程

本提案 v2（依審查方第二輪複核＋PO 2026-09-21 裁決修訂：§3.2 清單方向反轉為移除 `deadline`／不加 `504`、§3.3 三選項因前提被推翻而撤回、§4 測試 2/3 反向、突變清單第一項反向）送審查方複核，v2 三處修訂核准。v3（本次修訂）：§3.2 影響面證據從語料掃描改為封閉式證明（審查方發現語料掃描數字不可重跑，三種掃法得到互相矛盾的候選／變化段數，故撤下改用集合論證＋隨機窮舉驗證，不依賴任何語料樣本）。審查方已對此項變更預先核准，不需再送複核一輪，本輪直接送 PO 核准。核准後：紅測 → 送複核 → 綠燈（含新 ADR）→ 送複核 → 結案（無需段 B 拋棄式演練、無需段 C 真實執行——PO 已裁定 08:30 雙時點排程與 #34 一併暫停，本案是本輪唯一在途項目，且全程可用單元測試層合成例外訊息覆蓋，不需要動用真實 DB 或真實 API 呼叫驗證行為）。
