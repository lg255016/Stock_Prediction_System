# -*- coding: utf-8 -*-
"""UG-G2-SB7 步驟 1：`post_time` 改由網址的 unix 時間戳決定。

================================================================================
這個缺陷是怎麼活下來的
================================================================================
`data_cleaner.clean_ptt_data` 的**相鄰三行**：

```
:192  df_clean['post_time']           = df_clean['date'].apply(self._parse_date)
:195  df_clean['provider_article_id'] = df_clean['url'].apply(build_ptt_provider_article_id)
```

上面用索引頁**沒有年份**的 `9/18`，下面用同一個 DataFrame 裡的 `url`；
而 `ptt_scraper.py` 的 `_URL_TIMESTAMP_RE` 註解逐字寫著那個時間戳
「同一個也是 `data_cleaner.build_ptt_provider_article_id` 的取值來源」。

> **專案早就知道 url 帶著權威時間，只是拿它做 ID、沒拿它做時間。兩者相隔三行。**

`parse_ptt_datetime` 的跨年推論只處理 **±1 年**邊界 ——
**而 `/search?q=` 回傳的是全站歷史，跨越七年。**

> **跨年推論的前提是「這些文章都是最近的」，而搜尋結果從來不是。
> 那個假設從沒被寫下來，因此也從沒被檢查。**

實測（2026-09-05，`postgres`@`localhost:5432`）：331 篇中 **96 篇** `post_time`
與網址時間戳不同日，年份差 +1 至 **+7**；其中 **26 篇**落在
`daily_ml_features` 的日期窗內 —— **2019~2025 年的文章被聚合進 2026 年的特徵列。**

================================================================================
⚠ 本檔**不修既有 331 列**
================================================================================
只影響新寫入（PO 2026-09-05 裁決）。既有列的處置在受控執行之後另議。
**因此「新資料正確、舊資料已知污染」是一個刻意的混合狀態，不是疏漏。**
"""
import datetime
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ptt_url(ts, n="001"):
    return "https://www.ptt.cc/bbs/Stock/M.%d.A.%s.html" % (ts, n)


# 2019-09-17 19:20:48 UTC ＝ **2019-09-18 03:20:48 台北時間（UTC+8）**。
#
# ⚠ 這是本檔自造的固定值，**不是**某一列的實測時間戳 ——
# 第一版的註解寫成「實測樣本 article_id=834 的真實時間戳」，
# **那是我沒有查證就寫下的出處，已更正**。
# 缺陷的實測數字在 commit message 與 Gate B，不在這個常數上。
TS_2019 = 1568748048

# PTT 是台灣的看板，`M.<unix>` 是真正的 epoch 秒。
# **必須顯式轉 UTC+8，不得用 `datetime.fromtimestamp()` 的機器本地時區。**
TAIPEI = datetime.timezone(datetime.timedelta(hours=8))


def taipei(ts):
    return datetime.datetime.fromtimestamp(ts, TAIPEI).replace(tzinfo=None)


class PostTimeMustComeFromTheUrlTimestamp(unittest.TestCase):
    """**known-FAIL 主體**：索引頁的 `9/18` 會把 2019 年的文章記成今年。"""

    def _clean(self, rows):
        from src.transform.data_cleaner import DataCleaner
        return DataCleaner().clean_ptt_data(pd.DataFrame(rows))

    def test_a_2019_article_is_not_dated_this_year(self):
        """**什麼輸入會讓它 FAIL**：沿用 `date` 欄的 `9/18`。

        差七年不是邊界問題 —— **它是「假設沒被寫下來」的直接後果。**
        """
        out = self._clean([{
            "source": "ptt_keyword_search", "fetch_keyword": "光學鏡頭",
            "date": "9/18", "title": "[新聞] 光學鏡頭出貨", "push_count": "10",
            "author": "u", "url": ptt_url(TS_2019),
        }])
        got = pd.Timestamp(out.iloc[0]["post_time"])
        self.assertEqual(got.year, 2019,
                         "網址時間戳是該篇的建立時刻，**不是推論** —— "
                         "而索引頁的 `9/18` 沒有年份")
        self.assertEqual((got.month, got.day), (9, 18))

    def test_time_of_day_is_preserved_not_flattened_to_noon(self):
        """**時刻也救回來了**：索引頁完全沒有時刻，舊路徑一律填 12:00。

        `nlp` 與特徵對齊用的是 `post_time`，而 `feature_aggregator` 的
        `cutoff_time` 預設 `15:30:00` —— **一律 12:00 會讓每一篇都落在收盤前**，
        真實時刻則不一定。
        """
        out = self._clean([{
            "source": "ptt_keyword_search", "fetch_keyword": "光學鏡頭",
            "date": "9/18", "title": "t", "push_count": "0",
            "author": "u", "url": ptt_url(TS_2019),
        }])
        got = pd.Timestamp(out.iloc[0]["post_time"])
        self.assertEqual((got.hour, got.minute),
                         (taipei(TS_2019).hour, taipei(TS_2019).minute))

    def test_the_result_does_not_depend_on_the_machine_timezone(self):
        """**時區不得由機器決定** —— 這一條是施工中量出來的，不是設計時想到的。

        dev container 的 `time.tzname` 是 `('UTC', 'UTC')`（實測 2026-09-05），
        而 PTT 是台灣的看板。用 `datetime.fromtimestamp()` 的**本地**時區，
        `TS_2019` 會得到 `2019-09-17 19:20`，**而正確答案是 `2019-09-18 03:20`。**

        > **日期會整個差一天，而且差多少取決於容器怎麼設。**
        > 那不是「時刻不準」——`feature_aggregator` 的 `cutoff_time` 是 `15:30`，
        > **八小時的位移足以讓一篇文章從收盤後變成收盤前。**

        **什麼輸入會讓它 FAIL**：實作用 `datetime.fromtimestamp(ts)`（無 tz）。
        """
        out = self._clean([{
            "source": "ptt_keyword_search", "fetch_keyword": "光學鏡頭",
            "date": "9/18", "title": "t", "push_count": "0",
            "author": "u", "url": ptt_url(TS_2019),
        }])
        got = pd.Timestamp(out.iloc[0]["post_time"])
        self.assertEqual((got.year, got.month, got.day, got.hour),
                         (2019, 9, 18, 3),
                         "PTT 的 epoch 秒必須以 **UTC+8** 解讀，"
                         "**不是機器的本地時區** —— 本容器是 UTC")
        self.assertIsNone(got.tzinfo,
                          "寫進 DB 的是 naive datetime（欄位為 TIMESTAMP "
                          "WITHOUT TIME ZONE），**轉換在寫入前完成**")

    def test_falls_back_to_the_index_date_when_the_url_has_no_timestamp(self):
        """**取不到時間戳時回退到舊解析，不得整列丟掉。**

        PTT 有少數文章的網址不是 `M.<unix>.A.<n>` 形態。
        **回退是誠實的降級；丟掉那一列會讓「解析失敗」長得像「沒有這篇文章」**
        （§7.1 換一個粒度）。
        """
        out = self._clean([{
            "source": "ptt_keyword_search", "fetch_keyword": "台積電",
            "date": "9/18", "title": "t", "push_count": "0",
            "author": "u", "url": "https://www.ptt.cc/bbs/Stock/index.html",
        }])
        self.assertEqual(len(out), 1)
        self.assertIsNotNone(out.iloc[0]["post_time"])

    def test_provider_article_id_still_derives_from_the_same_url(self):
        """**反向釘子**：兩欄取自同一個 url，改一個不得動到另一個。"""
        out = self._clean([{
            "source": "ptt_keyword_search", "fetch_keyword": "台積電",
            "date": "9/18", "title": "t", "push_count": "0",
            "author": "u", "url": ptt_url(TS_2019, "123"),
        }])
        self.assertEqual(out.iloc[0]["provider_article_id"],
                         "ptt_Stock_M.%d.A.123" % TS_2019)

    def test_board_page_mode_rows_also_go_through_this(self):
        """看板模式的列同樣受惠 —— 兩種模式共用 `clean_ptt_data`。"""
        out = self._clean([{
            "source": "ptt_board_pages", "fetch_keyword": "台積電",
            "date": "9/05", "title": "[標的] 台積電", "push_count": "5",
            "author": "u", "url": ptt_url(TS_2019),
        }])
        self.assertEqual(pd.Timestamp(out.iloc[0]["post_time"]).year, 2019)


class TheOldParserIsStillReachableAndUnchanged(unittest.TestCase):
    """`parse_ptt_datetime` 本身不動 —— 它仍是回退路徑與內頁解析在用的。

    **什麼輸入會讓它 FAIL**：順手把跨年推論一起改掉。
    """

    def test_full_timestamp_format_unchanged(self):
        from src.transform.data_cleaner import parse_ptt_datetime
        got = parse_ptt_datetime("Wed Aug 20 14:25:36 2026")
        self.assertEqual((got.year, got.month, got.day), (2026, 8, 20))

    def test_short_date_inference_unchanged(self):
        from src.transform.data_cleaner import parse_ptt_datetime
        ref = datetime.datetime(2026, 1, 2, 10, 0, 0)
        got = parse_ptt_datetime("12/31", reference_time=ref)
        self.assertEqual(got.year, 2025,
                         "±1 年的跨年推論仍然有效 —— "
                         "它是回退路徑，**本輪不動它**")


if __name__ == "__main__":
    unittest.main()
