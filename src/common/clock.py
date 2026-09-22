# -*- coding: utf-8 -*-
"""時區政策：本專案「現在」的**唯一**入口。

================================================================================
為什麼需要這個模組
================================================================================
**dev container 的時區是 UTC**（`time.tzname == ('UTC', 'UTC')`，實測 2026-09-05），
**而本專案所有的業務基準都是台北時間**：

- 台股交易日與收盤時間
- `feature_aggregator` 的 `cutoff_time = 15:30`（DEC-024 的決策時點）
- PTT 文章的發文時刻（`MULTI_SOURCE_DATA_CONTRACT.md` §3.6A）

**`datetime.now()` 回傳的是機器的本地時間** —— 在容器裡就是 UTC，
比台北慢 8 小時。**它不會報錯，只會讓每一個時間戳都早 8 小時。**

================================================================================
它造成過什麼（不是假想的）
================================================================================
`UG-G2-SB7` 的受控執行寫出這樣一列：

```
post_time            2026-09-05 10:07:38   ← UTC+8（`e67d3d6` 改的）
comments_scraped_at  2026-09-05 05:53:32   ← UTC（`datetime.now()`）
```

**留言看起來在文章發表前 4 小時就被抓走了。**

而 `feature_aggregator.py` 的 DEC-024 判準是
`comments_scraped_at <= trade_date + 15:30`：

> ⚠⚠ **偏差方向是寬鬆的。** 時間戳被記早 8 小時，**比應該的更容易通過那個過濾**。
> 一次台北 **20:00** 的抓取會被記成 **12:00**、通過 15:30 的 cutoff ——
> **只有在 20:00 才知道的留言數，被算進 15:30 就要下的決策。**
>
> **那是 `CLAUDE.md` §7.4 的 Look-ahead，
> 發生在一條「存在的唯一理由就是防前視」的過濾裡。**

同一次掃描還找到兩處**決定「抓哪一天／哪一個月」**的呼叫
（`previous_business_day()` 與 `now.strftime("%Y%m01")`）——
**台北時間每月最後一天的 16:00–24:00，UTC 還停在前一天。**

================================================================================
使用規則
================================================================================
- **`src/` 與 `main_etl_pipeline.py` 內，一律不得出現 naive 的「現在」。**
  由 `tests/test_timezone_policy.py` 以 **AST 掃描**強制（不是 grep ——
  grep 分不出「呼叫它」與「docstring 裡提到它」）。
- **沒有例外清單。** 連 `src/ui/data_loader.py` 的 demo 資料產生器也走這裡：
  **一個絕對的規則不需要維護豁免，而豁免清單會漏掉下一個新增的地方。**
- **`time.time()` 不受限** —— epoch 秒沒有時區。
  `scrape_ptt_board_pages` 的回溯目標拿它跟**網址內嵌的 epoch** 比較，
  兩邊同基準，**那是對的**。

================================================================================
為什麼回傳 naive datetime
================================================================================
`market_articles.post_time`／`comments_scraped_at`、`etl_run_log.started_at`
等欄位都是 `TIMESTAMP WITHOUT TIME ZONE`。
**轉換在寫入前完成**，寫進去的是「台北牆上時鐘的時間」——
與 `trade_date + cutoff_time` 這類基準可以直接比較。

⚠ **這是一個刻意的取捨**：naive 值本身不帶基準資訊，
**所以基準必須靠這個模組是唯一入口來保證**。
若日後改為 `TIMESTAMPTZ`，本模組是唯一要改的地方。
"""
from __future__ import annotations

import datetime as _dt

# 台北時間 UTC+8。**台灣不實施日光節約時間**（1980 年後未再實施），
# 故固定偏移正確，不需要 tz database。
TAIPEI = _dt.timezone(_dt.timedelta(hours=8), name="Asia/Taipei")


def now_taipei() -> _dt.datetime:
    """現在的台北時間，**naive**（見模組 docstring 末段）。"""
    return _dt.datetime.now(TAIPEI).replace(tzinfo=None)


def today_taipei() -> _dt.date:
    """今天的台北日期。

    **決定「抓哪一天」的程式碼必須用它** —— 用機器本地日期，
    台北時間每天 00:00–08:00 會落在前一天（容器為 UTC 時）。
    """
    return now_taipei().date()


def to_taipei(ts: float) -> _dt.datetime:
    """把 epoch 秒轉成台北時間的 naive datetime。

    PTT 網址內嵌的 `M.<unix>.A.<n>` 走這條
    （`MULTI_SOURCE_DATA_CONTRACT.md` §3.6A）。
    """
    return _dt.datetime.fromtimestamp(ts, TAIPEI).replace(tzinfo=None)
