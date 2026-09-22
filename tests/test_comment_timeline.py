# -*- coding: utf-8 -*-
"""`PRE-G3-01` 第一部分：逐則留言時間戳（W1~W6）。

判準逐字取自 `doc/upgrade/gates/PRE_G3_01_GATE_A_PROPOSAL.md` §4，
**於實作之前寫死**（PO 2026-09-06 核准四個決策點）。

================================================================================
為什麼存逐則時間戳，而不是只存「截至 T 的計數」
================================================================================
`feature_aggregator.generate_daily_features`（`:278`）的 `cutoff_time`
**是一個參數，不是常數**；`map_timestamp_to_trading_day`（`:68`）與
`assign_trading_days_to_articles`（`:147`）更是 `str | time` 的**雙模式**參數。
而 `CLAUDE.md` §7.4 要求 Gate 3 之前先定義 Prediction Time Convention ——
**那個定義還沒有做。**

> **只存「截至 T 的計數」，等於把一個明確還開著的決定寫死進資料。**
> **這與 `stock_prices` 沒有 `source` 欄是同一個形狀：
> 一個寫入時沒有捕捉的維度，事後補不回來。**

**W5 是那個論證的可證偽形式。**

================================================================================
⚠ 本檔**不**改寫方向類特徵（決策點 2b 採 (乙)）
================================================================================
`comment_polarization`／`net_push_momentum` 仍由「取數當下」的彙總算出，
**不受 DEC-024 的 cutoff 保護** —— 已登記 `RISK-023`
與 `MULTI_SOURCE_DATA_CONTRACT.md` §3.3A。
**那個污染不是本 SB 造成的，它從 `UG-G2-SB4` 起就存在；
本 SB 只是把兄弟特徵（計數類）修好而讓它顯形。**
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TAIPEI = datetime.timezone(datetime.timedelta(hours=8))


def entries(*pairs):
    """`(tag, 'MM/DD HH:MM')` 序列 → 解析器的原始輸出形態。"""
    return [{"seq": i + 1, "tag": t, "raw_time": s}
            for i, (t, s) in enumerate(pairs)]


class W1PerCommentTimestampsAreParsed(unittest.TestCase):
    """**W1**：逐則時間戳被解析出來。

    **什麼輸入會讓它 FAIL**：沿用現行只數 `push-tag` 的實作 —— 回傳裡沒有這個欄位。
    """

    def test_parse_article_comments_returns_per_comment_entries(self):
        from bs4 import BeautifulSoup
        from unittest.mock import MagicMock
        from src.extractors.ptt_scraper import PttScraper

        html = ('<div class="article-metaline"><span class="article-meta-tag">時間'
                '</span><span class="article-meta-value">Thu Aug 15 16:48:24 2019'
                '</span></div>'
                '<div class="push"><span class="push-tag">推 </span>'
                '<span class="push-userid">a</span>'
                '<span class="push-content">: x</span>'
                '<span class="push-ipdatetime"> 08/15 16:49\n</span></div>'
                '<div class="push"><span class="push-tag">噓 </span>'
                '<span class="push-userid">b</span>'
                '<span class="push-content">: y</span>'
                '<span class="push-ipdatetime"> 08/16 09:02\n</span></div>')
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=html)
        out = s.parse_article_comments("https://www.ptt.cc/bbs/Stock/M.1.A.001.html")

        self.assertIn("comment_entries", out,
                      "**逐則資料必須被帶出來** —— 只回傳彙總計數，"
                      "任何 cutoff 下的重算就永遠做不到（見 W5）")
        self.assertEqual(len(out["comment_entries"]), 2)
        first = out["comment_entries"][0]
        self.assertEqual(first["seq"], 1)
        self.assertEqual(first["tag"], "推")
        self.assertIn("08/15 16:49", first["raw_time"])
        # 既有欄位不得因此改變
        self.assertEqual(out["push_count"], 1)
        self.assertEqual(out["boo_count"], 1)
        self.assertEqual(out["total_comments"], 2)


class W2CrossYearInference(unittest.TestCase):
    """**W2**（known-FAIL 主體）：跨年推論。

    **什麼輸入會讓它 FAIL**：不存在該邏輯 —— 現行程式把留言的年份當成發文年份。

    ================================================================
    規則與 §3.6 的差別
    ================================================================
    錨點是**文章發文時間**（年份已知，兩個獨立來源：網址時間戳、內頁 metaline），
    留言依序遞增，`MM/DD` 相對前一則回捲時年份 +1。

    > §3.6 的 ±1 年推論**失效是因為它沒有起點，只有「今年」**；
    > **這裡有一個確定的起點。**
    """

    def test_comment_after_new_year_gets_the_next_year(self):
        from src.transform.comment_timeline import infer_comment_times
        post = datetime.datetime(2019, 12, 28, 21, 0, 0)
        got = infer_comment_times(post, entries(
            ("推", "12/28 21:05"), ("推", "12/29 08:10"), ("噓", "01/03 11:20")))
        self.assertEqual([c["comment_time"].year for c in got],
                         [2019, 2019, 2020],
                         "留言依序遞增；MM/DD 回捲代表跨年 —— "
                         "**錨點是發文年份，不是「今年」**")
        self.assertEqual(got[2]["comment_time"],
                         datetime.datetime(2020, 1, 3, 11, 20))

    def test_two_wraps_give_two_increments(self):
        """**反向釘子**：回捲**兩次**要 +2 年，不是只加一次。

        ⚠ **本測試的第一版資料是 `12/30 → 01/02 → 01/05` —— 那只回捲一次。**
        known-FAIL 演練時，一個「只在第一次回捲時加年」的錯誤實作**通過了它** ——
        **測試名說的（兩次）與它量的（一次）不是同一件事**（§9A.1）。
        資料已改為真正跨兩年。
        """
        from src.transform.comment_timeline import infer_comment_times
        post = datetime.datetime(2019, 12, 30, 10, 0, 0)
        got = infer_comment_times(post, entries(
            ("推", "12/30 10:05"),   # 2019
            ("推", "01/02 09:00"),   # 2020 ← 第一次回捲
            ("推", "12/28 09:00"),   # 2020
            ("推", "01/03 09:00")))  # 2021 ← 第二次回捲
        self.assertEqual([c["comment_time"].year for c in got],
                         [2019, 2020, 2020, 2021])

    def test_no_wrap_keeps_the_post_year(self):
        """**反向釘子**：沒有回捲就不得加年 —— 探測到的那一篇正是這種。"""
        from src.transform.comment_timeline import infer_comment_times
        post = datetime.datetime(2019, 8, 15, 16, 48, 24)
        got = infer_comment_times(post, entries(
            ("推", "08/15 16:49"), ("推", "08/20 20:22")))
        self.assertEqual([c["comment_time"].year for c in got], [2019, 2019])

    def test_a_comment_is_never_before_the_post(self):
        """留言不得早於發文 —— 結構上成立，因此可以當斷言。"""
        from src.transform.comment_timeline import infer_comment_times
        post = datetime.datetime(2019, 12, 31, 23, 50, 0)
        got = infer_comment_times(post, entries(("推", "01/01 00:05")))
        self.assertGreater(got[0]["comment_time"], post)


class W3TaipeiTime(unittest.TestCase):
    """**W3**：`comment_time` 為台北時間 naive。

    **什麼輸入會讓它 FAIL**：以 UTC 解讀 —— 差 8 小時（同 §3.6B 的形狀）。
    """

    def test_naive_and_matches_the_page_wall_clock(self):
        from src.transform.comment_timeline import infer_comment_times
        post = datetime.datetime(2019, 8, 15, 16, 48, 24)
        got = infer_comment_times(post, entries(("推", "08/15 16:49")))[0]
        self.assertIsNone(got["comment_time"].tzinfo,
                          "欄位是 TIMESTAMP WITHOUT TIME ZONE，轉換在寫入前完成")
        self.assertEqual((got["comment_time"].hour, got["comment_time"].minute),
                         (16, 49),
                         "**頁面上的時刻就是台北牆上時鐘的時刻** —— 不做任何位移")


class W4CountsMustAgree(unittest.TestCase):
    """**W4**：`total_comments` 與逐則列數相等。

    **什麼輸入會讓它 FAIL**：解析器改了一半（只加了逐則、沒同步計數，或反之）。
    """

    def test_total_equals_number_of_entries(self):
        from bs4 import BeautifulSoup  # noqa: F401
        from unittest.mock import MagicMock
        from src.extractors.ptt_scraper import PttScraper
        pushes = "".join(
            '<div class="push"><span class="push-tag">%s </span>'
            '<span class="push-content">: x</span>'
            '<span class="push-ipdatetime"> 08/1%d 10:00\n</span></div>'
            % (tag, i) for i, tag in enumerate(["推", "噓", "→", "推"]))
        s = PttScraper()
        s._fetch_page = MagicMock(return_value=pushes)
        out = s.parse_article_comments("https://www.ptt.cc/bbs/Stock/M.1.A.001.html")
        self.assertEqual(out["total_comments"], len(out["comment_entries"]))
        self.assertEqual(out["total_comments"], 4)


class W5RecomputableAtAnyCutoff(unittest.TestCase):
    """**W5**（known-FAIL 主體）：**任一 cutoff 下的計數可由逐則時間戳重算**。

    **這是決策點 1 的可證偽形式** —— 只存彙總就算不出來。

    **什麼輸入會讓它 FAIL**：不提供這個能力（函式不存在），
    或它忽略 cutoff 直接回傳總數。
    """

    def _comments(self):
        from src.transform.comment_timeline import infer_comment_times
        post = datetime.datetime(2019, 8, 15, 16, 48, 24)
        return infer_comment_times(post, entries(
            ("推", "08/15 16:49"),   # 當日 15:30 之後
            ("推", "08/16 09:02"),
            ("噓", "08/16 20:00"),
            ("→", "08/20 20:22")))

    def test_counts_at_an_early_cutoff(self):
        from src.transform.comment_timeline import counts_as_of
        got = counts_as_of(self._comments(),
                           datetime.datetime(2019, 8, 16, 15, 30, 0))
        self.assertEqual(got, {"push_count": 2, "boo_count": 0,
                               "neutral_count": 0, "total_comments": 2})

    def test_counts_at_a_late_cutoff_equal_the_total(self):
        from src.transform.comment_timeline import counts_as_of
        got = counts_as_of(self._comments(),
                           datetime.datetime(2026, 1, 1, 0, 0, 0))
        self.assertEqual(got["total_comments"], 4)

    def test_two_different_cutoffs_give_different_answers(self):
        """**這一條才是重點** —— 若忽略 cutoff，兩者會相等而測試通過。

        **一個總是回傳總數的實作，在單一 cutoff 下與正確實作沒有差別。**
        """
        from src.transform.comment_timeline import counts_as_of
        c = self._comments()
        early = counts_as_of(c, datetime.datetime(2019, 8, 16, 15, 30))
        late = counts_as_of(c, datetime.datetime(2019, 8, 21, 15, 30))
        self.assertNotEqual(early, late)
        self.assertEqual(late["total_comments"], 4)

    def test_cutoff_boundary_is_inclusive(self):
        """邊界為 `<=` —— 與 `feature_aggregator:768` 的 `<= decision_point` 一致。"""
        from src.transform.comment_timeline import counts_as_of
        got = counts_as_of(self._comments(),
                           datetime.datetime(2019, 8, 15, 16, 49, 0))
        self.assertEqual(got["total_comments"], 1)


class W6YearInferredIsTruthful(unittest.TestCase):
    """**W6**：`year_inferred` 必須誠實。

    **什麼輸入會讓它 FAIL**：把推論值標成觀測值。

    ⚠ 本欄目前**全部為 `True`**（頁面只給 `MM/DD`）。
    它與 `etl_run_log` 的時區欄的差別是**可否由同列其他欄位重建** ——
    **沒有任何欄位記得頁面當時給了幾位數的年份**，故它是原始事實，不是衍生欄。
    """

    def test_all_true_because_the_page_never_gives_a_year(self):
        from src.transform.comment_timeline import infer_comment_times
        got = infer_comment_times(datetime.datetime(2019, 8, 15, 16, 48),
                                  entries(("推", "08/15 16:49"),
                                          ("推", "08/16 09:02")))
        self.assertTrue(all(c["year_inferred"] for c in got))

    def test_a_full_timestamp_would_not_be_inferred(self):
        """**反向釘子**：若頁面哪天給了完整年份，該列必須標 `False`。

        沒有這一條，`year_inferred` 就是一個永遠為 `True` 的常數欄 ——
        **而那正是我反對 `etl_run_log` 加時區欄的理由。**
        """
        from src.transform.comment_timeline import infer_comment_times
        got = infer_comment_times(datetime.datetime(2019, 8, 15, 16, 48),
                                  entries(("推", "2019/08/15 16:49")))
        self.assertFalse(got[0]["year_inferred"])
        self.assertEqual(got[0]["comment_time"],
                         datetime.datetime(2019, 8, 15, 16, 49))


class W7InferredTimesMustBeBoundedOnBothEnds(unittest.TestCase):
    """**W7**：每一個推論出來的 `comment_time` 必須夾在一個閉區間裡。

    ================================================================================
    為什麼需要它：`year` 是跨迭代累積的
    ================================================================================
    規則是 `if (mo, d) < prev_md: year += 1`，而 `year` **帶進下一輪**。

    | 情形 | 後果 |
    |------|------|
    | 一則留言的 `MM/DD` 意外早於前一則 | 觸發**假回捲** → `year += 1` |
    | 而 `year` 帶進下一輪 | **該篇之後的每一則都多一年** |

    > **一則異常不是污染一列，是污染整條尾巴。**

    「留言依時間遞增排列」是標了 `INFERENCE`、n = 1 的前提 ——
    **而一個被標示的前提，若沒有任何東西在它不成立時發出聲音，
    與一個沒被標示的前提在輸出上一樣。**

    ================================================================================
    兩個方向的可偵測性相反
    ================================================================================
    | 失效 | 時間偏向 | 可否偵測 |
    |------|---------|---------|
    | 超過一年沒新留言後又有 | **偏早** | **不可** —— 頁面沒有資訊可據以判斷 |
    | **假回捲（亂序）** | **偏晚** | **可以** —— 見下 |

    **上界的依據**：`comments_scraped_at`（migration 004）。

    > **一則留言不可能晚於它被抓下來的那一刻。**

    那是**結構上不可能為真**的狀態，與「留言必晚於發文」是同一類、只是另一端。
    **兩者合起來把每一個推論值夾在一個閉區間裡。**

    ⚠ **本檢查刻意不放進 `infer_comment_times`** —— 它拿不到 `comments_scraped_at`，
    而該函式**只需要 HTML 以外的一個錨點**，年份推論因此可完全離線測試。
    **那個分層不破壞。** 本函式獨立，由寫入路徑呼叫。

    **什麼輸入會讓它 FAIL**：不做上界檢查 —— 亂序造成的整條尾巴偏移會靜默寫入。
    """

    def _c(self, post, *pairs):
        from src.transform.comment_timeline import infer_comment_times
        return infer_comment_times(post, entries(*pairs))

    def test_a_mid_list_out_of_order_comment_is_caught(self):
        """**反向釘子的主體**：中間一則亂序 → 之後每一則都多一年。"""
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 15, 16, 48)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        # 第 3 則的 08/16 早於第 2 則的 08/18 → 假回捲 → 第 3、4 則變成 2020
        c = self._c(post, ("推", "08/15 16:49"), ("推", "08/18 09:00"),
                    ("推", "08/16 10:00"), ("推", "08/20 20:22"))
        self.assertEqual([x["comment_time"].year for x in c],
                         [2019, 2019, 2020, 2020],
                         "先確認假回捲確實發生 —— **不然這條測試就沒在測它以為的東西**")

        bad = validate_comment_bounds(c, post_time=post, scraped_at=scraped)
        self.assertEqual(len(bad), 2,
                         "**一則亂序污染的是整條尾巴** —— 兩列都要被抓到")
        self.assertEqual([b["seq"] for b in bad], [3, 4])
        self.assertEqual(bad[0]["violation"], "above_scraped_at")

    def test_clean_data_produces_no_violation(self):
        """**反向釘子**：正常資料不得被誤報。

        **什麼輸入會讓它 FAIL**：把上界寫成 `<` 或用錯基準 ——
        那樣每一篇都會被擋，而「全部擋下」與「正確擋下」在通過率上分不出來。
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 15, 16, 48)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = self._c(post, ("推", "08/15 16:49"), ("推", "08/20 20:22"))
        self.assertEqual(validate_comment_bounds(c, post, scraped), [])

    def test_boundary_is_inclusive_on_both_ends(self):
        """恰好等於邊界不算違反 —— 與 `counts_as_of` 的 `<=` 同一慣例。"""
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 15, 16, 49)
        scraped = datetime.datetime(2019, 8, 15, 16, 49)
        c = self._c(post, ("推", "08/15 16:49"))
        self.assertEqual(validate_comment_bounds(c, post, scraped), [])

    def test_same_minute_comment_is_not_a_violation(self):
        """⚠ **兩端的解析度不同，而截斷永遠讓值變早。**

        `post_time` 到**秒**（網址內嵌 unix 時間戳，§3.6A）；
        `comment_time` 只到**分**（頁面是 `MM/DD HH:MM`），秒數一律 `00`。

        > **同一分鐘內的留言，永遠會「早於」發文。**

        實測（探測到的那一篇，發文 `16:48:27`）：留言 `08/15 16:48`
        推論為 `16:48:00`，被判 `below_post_time` —— **而它完全正常，
        只是發在同一分鐘內。而熱門看板上「發文一分鐘內就有人推」不是罕見情形。**

        **在寫入路徑上這會放大**：非空即拒寫整篇 ——
        **一則合法的、快速的第一則留言，會讓整篇文章寫不進去。**

        ================================================================
        不對稱在哪 —— 只有下界要修
        ================================================================
        | 邊界 | 截斷方向 | 後果 |
        |------|---------|------|
        | 上界 `scraped_at` | 變早 → **更不容易違反** | **安全，不動它** |
        | **下界 `post_time`** | 變早 → **更容易違反** | **誤報** |

        ⚠ **不得用放寬上界的方式一起處理** —— 上界現在是對的，動它只會削弱它。

        **什麼輸入會讓它 FAIL**：下界直接拿帶秒的 `post_time` 比較（即修正前）。
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 15, 16, 48, 27)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = self._c(post, ("推", "08/15 16:48"), ("推", "08/15 16:49"))
        self.assertEqual(c[0]["comment_time"],
                         datetime.datetime(2019, 8, 15, 16, 48),
                         "先確認秒數確實被截成 00 —— **不然這條測試沒在測它以為的東西**")
        self.assertEqual(validate_comment_bounds(c, post, scraped), [],
                         "同一分鐘內的留言不是異常，**那是解析度差異**")

    def test_below_post_time_is_reachable_through_the_real_path(self):
        """**`below_post_time` 由真實產生路徑產得出來** —— 不是只有手工 dict 觸發得到。

        > **一個輸入永遠不會出現的檢查，是死碼。**
        > `test_a_comment_before_the_post_is_caught` 用的是手工組的 dict，
        > **它證明了檢查器會抓，沒有證明任何真實路徑會產出那種輸入。**

        機制：回捲只比較 `(月, 日)`、**不看時分** ——
        同日較早的留言不觸發回捲，於是落在發文之前。
        **而現行行為是對的**：同日較早的留言就該被當異常抓出來，
        **不該回捲成隔年**。

        ⚠ 與上一條的修法**不衝突**：上一條是同一分鐘（秒數差），
        本條是**同一天不同分鐘** —— **截到分之後 `09:00` 仍然早於 `10:00`，照樣被抓。**
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 20, 10, 0, 0)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = self._c(post, ("推", "08/20 09:00"))
        self.assertEqual(c[0]["comment_time"],
                         datetime.datetime(2019, 8, 20, 9, 0),
                         "同日較早不得觸發回捲")
        bad = validate_comment_bounds(c, post, scraped)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["violation"], "below_post_time")

    def test_upper_bound_has_no_tolerance(self):
        """**上界不得有容差** —— 晚一分鐘就是異常。

        ⚠ **這條是 known-FAIL 演練逼出來的。** 我原本構造的「削弱上界」案例是
        「把上界也截到分」，**而它沒有 FAIL** ——
        查下去發現那個變異**在行為上與原版等價**：
        截到分讓界線**變早**（更嚴格），而 `comment_time` 的秒數恆為 `00`，
        **`(floor(s), s]` 區間裡不存在任何分對齊的值。**

        > **我的案例沒有 FAIL，不是因為缺少防護，是因為我構造的變異什麼都沒改。**
        > **一個不改變行為的變異，證明不了任何檢查有沒有偵測能力。**

        真正會削弱上界的是**加容差**，那才是這條測試守的東西。

        **什麼輸入會讓它 FAIL**：`t > scraped_at + 容差`。
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 25, 9, 0)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = self._c(post, ("推", "08/25 10:01"))
        self.assertEqual(c[0]["comment_time"],
                         datetime.datetime(2019, 8, 25, 10, 1))
        bad = validate_comment_bounds(c, post, scraped)
        self.assertEqual(len(bad), 1, "晚一分鐘就是異常 —— **上界不得有容差**")
        self.assertEqual(bad[0]["violation"], "above_scraped_at")

    def test_a_comment_before_the_post_is_caught(self):
        """下界：留言不得早於發文 —— **`post_time` 錨點本身錯了也會被這一端擋下**。

        76/331 那批的形狀（`post_time` 差整年）**會讓整篇整體位移**，
        而位移的兩個方向各由一端擋住。
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 20, 10, 0)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = [{"seq": 1, "tag": "推",
              "comment_time": datetime.datetime(2019, 8, 15, 9, 0),
              "year_inferred": True}]
        bad = validate_comment_bounds(c, post, scraped)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["violation"], "below_post_time")

    def test_unparsed_rows_are_reported_not_ignored(self):
        """`comment_time is None` 要被回報，**不得靜默跳過**。

        **什麼輸入會讓它 FAIL**：`if t is None: continue` ——
        那會讓「讀不出來」在寫入路徑上長得像「沒問題」，
        而 `comment_time NOT NULL` 會在更下游以一個難懂的 DB 錯誤爆掉。
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 15, 16, 48)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = [{"seq": 1, "tag": "推", "comment_time": None, "year_inferred": None}]
        bad = validate_comment_bounds(c, post, scraped)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["violation"], "unparsed")

    def test_violation_carries_observable_detail(self):
        """違反紀錄必須帶可觀測的事實，不是「有問題」三個字。

        同 `etl_run_log` 的 `detail` 要求與 `universe_snapshots.exclusion_reason`。
        """
        from src.transform.comment_timeline import validate_comment_bounds
        post = datetime.datetime(2019, 8, 15, 16, 48)
        scraped = datetime.datetime(2019, 8, 25, 10, 0)
        c = self._c(post, ("推", "08/18 09:00"), ("推", "08/16 10:00"))
        bad = validate_comment_bounds(c, post, scraped)
        self.assertTrue(bad)
        d = bad[0]
        for k in ("seq", "violation", "comment_time", "bound", "raw_time"):
            self.assertIn(k, d, "違反紀錄缺少可觀測欄位：%s" % k)


if __name__ == "__main__":
    unittest.main()
