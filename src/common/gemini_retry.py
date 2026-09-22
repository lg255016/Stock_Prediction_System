# -*- coding: utf-8 -*-
"""Gemini 暫態例外判斷：本專案「哪些錯誤值得重試」的唯一入口。

================================================================================
為什麼需要這個模組
================================================================================
`src/extractors/trend_discover.py` 與 `src/transform/nlp_processor.py` 原本
各自維護一份「哪些例外算暫態、值得退避重試」的關鍵字清單——兩份清單是真包含
關係，且都缺 `504`。2026-09-19 第三次真實每日 ETL 撞到 `DeadlineExceeded`
（504）時，兩條路徑的判定結果不一致：`nlp_processor` 判為暫態、退避重試；
`trend_discover` 判為非暫態、直接拋出。同一類錯誤在兩條路徑上不該有不同結果
（`PROJECT_STATUS.md` §0.5 #36）。

================================================================================
為什麼不放進 src/extractors/retry_policy.py
================================================================================
`retry_policy.is_retriable()` 是 DEC-032 的落地，第一道判斷就是
`isinstance(exc, requests.exceptions.RequestException)`——Gemini SDK
（`google.generativeai`）拋出的例外不是這個型別的子類別，若把 Gemini 暫態
例外丟進 `is_retriable()`，會無條件命中這個 `if`、回傳 `False`，所有
Gemini 暫態錯誤都會被系統性誤判為不可重試。這不是「兩種語意混在一份判準裡
不乾淨」，是塞進去就會產生錯誤行為，因此本模組獨立於 `retry_policy.py`。

================================================================================
判別依據：清單內容為什麼移除 deadline、保留 timeout、不新增 504
================================================================================
PO 2026-09-21 裁決：`DeadlineExceeded` 代表同一份 prompt 已經跑到逾時上限——
用一模一樣的內容原地重送，**沒有機制讓伺服器端在期限內算得更快**，重試换來
的期望結果是再次逾時，白白燒掉配額（免費層每日僅 20 次請求）。這與 429
（等待期過了配額就恢復）、503（伺服器忙完就正常）性質不同：後兩者的「稍等
重試」有明確的物理機制支持會變好，deadline 沒有。

保留 `timeout`：連線層逾時（TCP handshake、TLS 交握、等待首個 byte）可能在
請求根本還沒送達 Gemini 伺服器、伺服器完全不知道我們問了什麼的階段就發生，
這種情況下重試不是「用同樣的內容再求一次已經跑不完的運算」，而是「再給一次
連線機會」，與 `retry_policy.py`（DEC-032）對「拿不到 `status_code`」歸類為
可重試的邏輯同構。`deadline` 則是請求已經被伺服器接手、只是沒能在期限內做
完——兩者發生的層次不同，值得重試的理由也不同。

不新增 `504`：`504` 這個數字字串本來就不在任一份現行清單裡。`504` 對應的
`DeadlineExceeded` 已經被 `deadline` 這個詞面判準涵蓋（真實訊息「小寫後含
`504` 也含 `deadline`」）——加了 `504` 反而會讓 504 訊息透過數字字串命中
變成暫態，與移除 `deadline` 的決策矛盾，兩件事必須一起做才自洽，見
`GEMINI_TRANSIENT_KEYWORDS_UNIFY_GATE_A_PROPOSAL.md` §3.2 與 DEC-045。

================================================================================
本模組不負責的事
================================================================================
- **不判斷每日配額耗盡** —— 那是 `nlp_processor.is_daily_quota_exhausted()`
  的職責（DEC-043 決策 3 已落地），且呼叫端必須排在本模組的判斷**之前**
  呼叫（PerDay 訊息同時含 `quota`，順序反過來這個分支永遠執行不到）。本模組
  故意不重複、不依賴那個判斷，維持兩者各自獨立、呼叫順序由呼叫端保證。
- **不決定重試次數與退避秒數** —— 那是呼叫端的 `max_retries`／
  `sleep_sec = min(2 ** attempt, 16)`，本案不動。
"""

GEMINI_TRANSIENT_KEYWORDS = [
    "429", "quota", "rate limit", "resourceexhausted", "resource_exhausted",
    "503", "unavailable", "timeout", "connection error",
]


def is_transient_gemini_exception(exc: Exception) -> bool:
    """判斷 Gemini 例外是否值得退避重試。

    Returns:
        True  —— 429／503／連線層暫態問題，重試有機會變好。
        False —— 含 deadline／504（同一份請求重送不會變快）或任何未列入
                  清單的例外。
    """
    exc_str = str(exc).lower()
    return any(keyword in exc_str for keyword in GEMINI_TRANSIENT_KEYWORDS)
