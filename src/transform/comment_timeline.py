# -*- coding: utf-8 -*-
"""逐則留言的時間軸：年份推論與任一 cutoff 下的重算。

================================================================================
為什麼存逐則時間戳，而不是只存「截至 T 的計數」
================================================================================
`feature_aggregator` 的 cutoff 是**參數，不是常數**：

```
generate_daily_features        :278  cutoff_time: str = "15:30:00"
map_timestamp_to_trading_day   :68   cutoff_time: str | time = "15:30:00"
assign_trading_days_to_articles :147 cutoff_time: str | time = "15:30:00"
```

而 `CLAUDE.md` §7.4 要求 **Gate 3 之前先定義 Prediction Time Convention**
（模型在什麼時間點做預測、可使用哪些已知資料）—— **那個定義還沒有做。**

> **只存「截至 T 的計數」，等於把一個明確還開著的決定寫死進資料。**
> **這與 `stock_prices` 沒有 `source` 欄是同一個形狀：
> 一個寫入時沒有捕捉的維度，事後補不回來。**

`counts_as_of()` 是那個論證的可證偽形式（測試 W5）。

================================================================================
【2026-09-14 訂正，DEC-039】本模組現由 `feature_aggregator` 使用
================================================================================
`PRE-G3-01` 決策點 2b 當時刻意採 (乙)（不接線），理由見下方保留的原始說明。
**RISK-023 診斷發現 DEC-024 的文章層級 `comments_scraped_at` 過濾在本專案
實際排程常數下，穩定運作時通過率僅約 0.2%——NULL 比例恆定，不是回填期
特有的暫時現象。** `DEC-039`（修訂 DEC-024）改為 `_aggregate_direct_comment_counts()`
逐 `(article, stock_id)` 列呼叫 `counts_as_of()`／`validate_comment_bounds()`，
取代文章層級過濾。詳見 `doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md`。

以下為 (乙) 決策當時的原始理由，保留供對照：

**為什麼當初不順手一起改**：那會讓 Gate B 同時驗「擷取正確」與「重算正確」——
**任一項數字不符都分不出是誰造成的。**（`PRE-G3-01` 先把逐則時間戳的擷取與
推論正確性單獨驗完，`DEC-039` 才在那個已驗證的基礎上接線，兩件事沒有合併。）
"""
from __future__ import annotations

import datetime as _dt
import re

# PTT 留言行的時間格式：`08/15 16:49`（**沒有年份、沒有秒**）。
_SHORT = re.compile(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")
# 若頁面給了完整年份 —— 那不是推論值（見 `year_inferred`）。
#
# ⚠⚠ **本分支在現行 PTT 內頁上不會觸發。** 實測依據
# （`doc/upgrade/gates/evidence/PTT_INNER_PAGE_TIMESTAMP_PROBE_RESULT.json`，
#  2026-09-06，`article_id=169`）：
#
#   - `div.push` **281 則，push-ipdatetime 命中 281**，全部是 `08/15 16:49` 形態
#   - `P3.has_year = false`
#   - 內頁 metaline `Thu Aug 15 16:48:24 2019` **匹配不到本正規式**
#     （它要求四位數年份開頭），**而且它是「發文」時間，不是留言時間**
#
# **所以「遇到一個觀測值就重新錨定、誤差不會累積」在 PTT 上是一件不會發生的事。**
#
# > **誤差累積目前只靠 `year_inferred` 標示 + `validate_comment_bounds` 的上下界擋住，
# > 沒有任何重新錨定機制在運作。**
# > 一篇跨多次回捲的長文，推論鏈全程沒有校準點。
#
# **留著它是刻意的**：PTT 改版或改用其他來源時它就有用，成本是零。
# **但它是為來源變更保留的重新錨定點，不是現行誤差累積的防護** ——
# 寫在這裡是因為它讀起來像後者，**而複查方 2026-09-06 就是那樣讀的，
# 還把它寫進了核可意見。下一個人會犯同一個錯，除非這句話在這裡。**
#
# ⚠ 對應的 `test_a_full_timestamp_would_not_be_inferred` 的輸入是**手工組的** ——
# 它釘住的是本函式的契約，**不代表真實來源產得出那種輸入**。
_FULL = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})")

TAGS = ("推", "噓", "→")


def infer_comment_times(post_time, entries):
    """由發文時間錨定，逐則推論留言的年份。

    Args:
        post_time: 文章發文時間（naive 台北時間）。**年份已知** ——
            兩個獨立來源：網址內嵌的 unix 時間戳、內頁 `時間` metaline
            （`MULTI_SOURCE_DATA_CONTRACT.md` §3.6A）。
        entries: `[{"seq": int, "tag": str, "raw_time": str}, ...]`，
            **依頁面順序**。

    Returns:
        每則加上 `comment_time`（naive 台北時間）與 `year_inferred`（bool）。

    ================================================================
    規則
    ================================================================
    留言依序遞增；由發文年份起，**`MM/DD` 相對前一則回捲時年份 +1**。

    ⚠ **標籤 `INFERENCE`**，依據兩點：
      1. PTT 留言在頁面上依時間遞增排列
         （2026-09-06 探測：281 則實測遞增，**n = 1**）
      2. 留言必**晚於**發文（結構上成立）

    > **與 `§3.6` 那個「±1 年、假設文章是最近的」推論的差別：
    > 這裡有一個確定的起點。**
    > §3.6 的失效正是因為它沒有起點，只有「今年」——
    > 而 `/search?q=` 回傳的是跨越七年的全站歷史。

    ⚠⚠ **已知失效模式**：若一篇文章**超過一年沒有新留言、然後又有**，
    `MM/DD` 回捲會被算成 **+1 年而非 +2 年**。
    **本規則無法涵蓋該情形，也無法從頁面資訊區分**
    （頁面只有 `MM/DD`，沒有任何可據以判斷跨了幾年的資訊）。
    處置：`year_inferred = True` 已標示該值為推論 —— **不假裝它是精確的。**
    """
    out = []
    year = post_time.year
    prev_md = (post_time.month, post_time.day)
    for e in entries:
        raw = (e.get("raw_time") or "").strip()

        m_full = _FULL.search(raw)
        if m_full:
            y, mo, d, hh, mm = (int(g) for g in m_full.groups())
            out.append(dict(e, comment_time=_dt.datetime(y, mo, d, hh, mm),
                            year_inferred=False))
            year, prev_md = y, (mo, d)
            continue

        m = _SHORT.search(raw)
        if not m:
            # **解析失敗不得靜默丟棄，也不得猜一個時間** ——
            # 兩者都會讓「讀不出來」長得像「有這個值」。
            out.append(dict(e, comment_time=None, year_inferred=None))
            continue

        mo, d, hh, mm = (int(g) for g in m.groups())
        if (mo, d) < prev_md:
            # 回捲 = 跨年。**逐則比較，所以回捲兩次就加兩年。**
            year += 1
        prev_md = (mo, d)
        out.append(dict(e, comment_time=_dt.datetime(year, mo, d, hh, mm),
                        year_inferred=True))
    return out


def counts_as_of(comments, cutoff):
    """**任一 cutoff 下的推／噓／中性計數**，由逐則時間戳重算。

    Args:
        comments: `infer_comment_times()` 的輸出。
        cutoff: naive 台北時間。**邊界為 `<=`** ——
            與 `feature_aggregator.py:768` 的 `comments_scraped_at <= decision_point`
            一致，**不製造第二種邊界慣例**。

    Returns:
        `{"push_count", "boo_count", "neutral_count", "total_comments"}`

    > **這個函式是「存逐則時間戳」那個決定的可證偽形式**（測試 W5）：
    > **只存彙總，它就寫不出來。**

    ⚠ `comment_time` 為 `None` 的列（解析失敗）**不計入任何一格** ——
    它們既不是「在 cutoff 之前」也不是「之後」，**是不知道**。
    """
    push = boo = neutral = 0
    for c in comments:
        t = c.get("comment_time")
        if t is None or t > cutoff:
            continue
        tag = (c.get("tag") or "").strip()
        if "推" in tag:
            push += 1
        elif "噓" in tag:
            boo += 1
        elif "→" in tag:
            neutral += 1
    return {"push_count": push, "boo_count": boo, "neutral_count": neutral,
            "total_comments": push + boo + neutral}


def _floor_minute(dt):
    """把 datetime 截到分（秒與微秒歸零）。

    ⚠ **只給下界用。** 見 `validate_comment_bounds` 的「解析度不對稱」一節。
    """
    return dt.replace(second=0, microsecond=0)


def validate_comment_bounds(comments, post_time, scraped_at):
    """把每一個推論出來的 `comment_time` 夾在 `[post_time, scraped_at]` 裡。

    Args:
        comments: `infer_comment_times()` 的輸出。
        post_time: 文章發文時間（naive 台北）。**下界。**
        scraped_at: 內頁被抓取的時刻（naive 台北，即 `comments_scraped_at`）。**上界。**

    Returns:
        違反清單（空 list = 全部合格）。每筆帶
        `seq`／`violation`／`comment_time`／`bound`／`raw_time`。

    ================================================================
    為什麼需要它：`year` 是跨迭代累積的
    ================================================================
    `infer_comment_times` 的規則是 `if (mo, d) < prev_md: year += 1`，
    而 `year` **帶進下一輪**。一則留言的 `MM/DD` 意外早於前一則就會觸發
    **假回捲**，於是：

    > **一則異常不是污染一列，是污染整條尾巴。**

    「留言依時間遞增排列」是標了 `INFERENCE`、n = 1 的前提 ——
    **而一個被標示的前提，若沒有任何東西在它不成立時發出聲音，
    與一個沒被標示的前提在輸出上一樣。**

    ================================================================
    兩個失效方向的可偵測性相反
    ================================================================
    | 失效 | 時間偏向 | 可否偵測 |
    |------|---------|---------|
    | 超過一年沒新留言後又有（見 `infer_comment_times`） | **偏早** | **不可** |
    | **假回捲（亂序）** | **偏晚** | **可以，就是本函式** |

    上界的依據：**一則留言不可能晚於它被抓下來的那一刻。**
    那是**結構上不可能為真**的狀態，與下界（留言必晚於發文）是同一類、
    只是另一端。**兩者合起來把每一個推論值夾在一個閉區間裡。**

    ================================================================
    ⚠ 解析度不對稱 —— **下界比較前把 `post_time` 截到分**
    ================================================================
    `post_time` 有**秒**解析度（網址內嵌的 unix 時間戳，§3.6A）；
    `comment_time` 只有**分**（頁面是 `MM/DD HH:MM`），推論值的秒數一律 `00`。

    > **截斷永遠讓值變早，因此只有下界會因此誤報。**

    | 邊界 | 截斷方向 | 後果 |
    |------|---------|------|
    | 上界 `scraped_at` | 變早 → **更不容易違反** | **安全，刻意不動** |
    | **下界 `post_time`** | 變早 → **更容易違反** | **誤報，故截到分** |

    實例（探測到的 `article_id=169`，發文 `16:48:27`）：
    留言 `08/15 16:48` 推論為 `16:48:00`，未截斷前被判 `below_post_time` ——
    **而它完全正常，只是發在同一分鐘內。**
    **在寫入路徑上（非空即拒寫整篇），一則合法的、快速的第一則留言
    會讓整篇文章寫不進去** ——而熱門看板上那不是罕見情形。

    ⚠ **刻意不用「放寬上界」的方式一起處理** —— 上界現在是對的，
    動它只會削弱它。**兩端的問題不同，處置也不該相同。**

    ⚠ **截到分不會讓下界失去偵測能力**：同一天不同分鐘的異常
    （如發文 `10:00`、留言 `09:00`）**照樣被抓** ——
    那是回捲只比較 `(月, 日)`、不看時分造成的，且現行行為是對的
    （同日較早的留言就該被當異常，不該回捲成隔年）。

    ⚠ **下界順帶蓋住另一件事**：`post_time` 這個錨點本身若錯了
    （`market_articles` 舊批 76/331 的形狀，年份差 +1~+7），
    **整篇會整體位移 —— 而位移的兩個方向各由一端擋住。**

    ================================================================
    為什麼不放進 `infer_comment_times`
    ================================================================
    那個函式**只需要 HTML 以外的一個錨點**（發文時間），
    因此年份推論可以完全離線測試、不需要任何 HTML 或資料庫欄位。
    `scraped_at` 是寫入時才知道的東西 —— **把它塞進去會破壞那個分層。**

    **本函式由寫入路徑呼叫**，那裡兩個值都在手上。
    """
    bad = []
    for c in comments:
        t = c.get("comment_time")
        seq = c.get("seq")
        raw = c.get("raw_time")
        if t is None:
            # **回報，不靜默跳過** —— 否則「讀不出來」在寫入路徑上會長得像
            # 「沒問題」，而 `article_comments.comment_time NOT NULL`
            # 會在更下游以一個難懂的 DB 錯誤爆掉。
            bad.append({"seq": seq, "violation": "unparsed", "comment_time": None,
                        "bound": None, "raw_time": raw})
            continue
        if scraped_at is not None and t > scraped_at:
            bad.append({"seq": seq, "violation": "above_scraped_at",
                        "comment_time": t, "bound": scraped_at, "raw_time": raw})
        elif post_time is not None and t < _floor_minute(post_time):
            bad.append({"seq": seq, "violation": "below_post_time",
                        "comment_time": t, "bound": _floor_minute(post_time),
                        "raw_time": raw})
    return bad


def is_time_reset(comments):
    """依 `comment_seq` 順序（呼叫端保證輸入已依此排序）偵測留言時間是否回退。

    **由來（RISK-029、DEC-039 Decision 第 9 項）**：`article_id ∈ {1815, 2662}`
    兩篇真實文章的 `article_comments` 出現同一批留言被重複解析、或兩段交錯的
    留言流被串接，兩者的共同表徵都是**依 `comment_seq` 排序後，時間戳不是
    非遞減的**。`validate_comment_bounds()` 抓不到這個形態——兩篇的時間戳
    本身都落在 `[post_time, comments_scraped_at]` 合法範圍內，只是重複或交錯，
    不是越界。

    本函式**只偵測「時間回退」**，偵測不到「時間仍遞增但內容重複／交錯」的
    其他形態——這是已知的偵測邊界（見 `RISK023_GATE_A_PROPOSAL.md` 的
    Remaining Risks），根因診斷另立 **RISK-029**，本函式不嘗試修復或去重，
    只負責標記可疑、交由呼叫端決定如何處置（DEC-039：整篇涉及的
    `(article, stock_id)` 列留言三欄一律 NULL）。

    Args:
        comments: 依 `comment_seq` 遞增排序的留言列表，每則為
            `{"comment_time": datetime | None, ...}`。`comment_time` 為 `None`
            的列（解析失敗）不參與比較，跳過不影響前後兩側的判斷。

    Returns:
        `True` 代表偵測到時間回退（該篇應標記 `suspect`）；`False` 代表
        時間戳非遞減，無異常。空列表視為無異常（`False`）。
    """
    prev = None
    for c in comments:
        t = c.get("comment_time")
        if t is None:
            continue
        if prev is not None and t < prev:
            return True
        prev = t
    return False
