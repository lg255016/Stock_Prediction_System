# -*- coding: utf-8 -*-
"""`PRE-G3-01` 第一部分：逐則留言的寫入路徑（W8）。

判準來自複查方 2026-09-06：

> 上界違反 → **該篇不寫入 + 記一筆可觀測的錯誤**
> （不是靜默丟棄，也不是截斷成上界）。

================================================================================
為什麼是「拒寫整篇」而不是「丟掉違反的那幾則」
================================================================================
`infer_comment_times` 的 `year` **跨迭代累積** —— 一則亂序造成的假回捲會讓
**該篇之後的每一則都多一年**。

> **一則異常不是污染一列，是污染整條尾巴。**
> **所以「丟掉違反的那幾則」丟掉的是症狀，留下的是原因** ——
> 剩下的列看起來乾淨，而它們的年份是同一個錯誤推論鏈算出來的。

⚠ **也不得截斷成上界**：那會把一個「我們不知道它是什麼時候」的值
變成一個**看起來精確的**值。同 `CLAUDE.md` 一貫的
「算不出來就是 NULL，不要給一個似是而非的數字」。
"""
import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

URL_OK = "https://www.ptt.cc/bbs/Stock/M.1565858907.A.FC0.html"    # 2019-08-15 16:48:27

# ⚠ **亂序的案例必須用「近期」文章**，理由見 `TheUpperBoundWeakensWithArticleAge`。
# 1788000000 → 2026-08-29 20:40（台北）
URL_RECENT = "https://www.ptt.cc/bbs/Stock/M.1788000000.A.AAA.html"
URL_BAD = URL_RECENT


def counts(entries, total=None):
    n = total if total is not None else len(entries)
    return {"push_count": n, "boo_count": 0, "neutral_count": 0,
            "total_comments": n, "engagement_metric": n,
            "full_datetime": "Thu Aug 15 16:48:24 2019",
            "comment_entries": entries}


def e(*pairs):
    return [{"seq": i + 1, "tag": t, "raw_time": s}
            for i, (t, s) in enumerate(pairs)]


class _Base(unittest.TestCase):
    def _manager(self):
        import main_etl_pipeline as mep
        patches = [patch.object(mep, n, MagicMock()) for n in
                   ("DBWriter", "TrendDiscover", "NLPProcessor",
                    "FeatureAggregator")]
        for p in patches:
            p.start()
        try:
            m = mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()
        m.db_writer = MagicMock()
        m.ptt_scraper = MagicMock()
        return m


class W8RefuseTheWholeArticleOnViolation(unittest.TestCase, ):
    """**W8**：邊界違反 → **該篇不寫入 + 記一筆可觀測的錯誤**。

    **什麼輸入會讓它 FAIL**：寫入路徑不呼叫 `validate_comment_bounds`，
    或呼叫了卻只丟掉違反的那幾則。
    """

    def _run(self, per_url):
        m = _Base._manager(self)
        m.db_writer.fetch_articles_missing_comment_counts.return_value = set(per_url)
        m.ptt_scraper.parse_article_comments.side_effect = \
            lambda u: per_url[u]
        m.backfill_ptt_comment_counts(list(per_url))
        return m

    def test_clean_article_writes_both_counts_and_comments(self):
        m = self._run({URL_OK: counts(e(("推", "08/15 16:49"),
                                        ("推", "08/16 09:02")))})
        self.assertTrue(m.db_writer.update_comment_counts.called)
        self.assertTrue(m.db_writer.upsert_article_comments.called,
                        "**逐則資料必須被寫入** —— 否則 W5 的重算永遠沒有輸入")
        rows = m.db_writer.upsert_article_comments.call_args.args[0]
        self.assertEqual(len(rows), 2)

    def test_out_of_order_article_is_refused_entirely(self):
        """**整篇拒寫** —— 不是只丟掉違反的那幾則。"""
        m = self._run({URL_BAD: counts(e(("推", "08/29 20:41"),
                                         ("推", "09/02 09:00"),
                                         ("推", "09/01 10:00"),   # 假回捲 → 2027
                                         ("推", "09/03 20:22")))})
        written = m.db_writer.upsert_article_comments.call_args
        rows = written.args[0] if written else []
        self.assertEqual([r for r in rows if r[0] == URL_BAD], [],
                         "**一則異常污染整條尾巴，所以丟掉那幾則留下的是原因** —— "
                         "整篇都不寫")
        sent = m.db_writer.update_comment_counts.call_args
        recs = sent.args[0] if sent else []
        self.assertEqual([r for r in recs if r[-1] == URL_BAD], [],
                         "計數也不得寫入 —— **兩者必須同進退**")

    def test_violation_is_reported_not_silent(self):
        """違反必須被回報，**不得靜默丟棄**。"""
        m = self._run({URL_BAD: counts(e(("推", "09/02 09:00"),
                                         ("推", "09/01 10:00")))})
        self.assertTrue(getattr(m, "last_comment_bound_violations", None),
                        "**必須留下可觀測的紀錄** —— "
                        "靜默丟棄與「那篇沒有留言」在輸出上長得一樣")
        v = m.last_comment_bound_violations[0]
        self.assertEqual(v["url"], URL_BAD)
        self.assertIn("violation", v)

    def test_one_bad_article_does_not_block_the_others(self):
        """**逐篇隔離** —— 同 `MULTI_SOURCE_DATA_CONTRACT.md` §3.5 的失敗語意。"""
        m = self._run({
            URL_OK: counts(e(("推", "08/15 16:49"))),
            URL_BAD: counts(e(("推", "09/02 09:00"), ("推", "09/01 10:00"))),
        })
        rows = m.db_writer.upsert_article_comments.call_args.args[0]
        self.assertEqual({r[0] for r in rows}, {URL_OK},
                         "乾淨的那篇仍須寫入")

    def test_same_minute_first_comment_is_not_refused(self):
        """**反向釘子**：同一分鐘的第一則留言不得讓整篇被拒。

        **什麼輸入會讓它 FAIL**：下界不截到分（見 `comment_timeline` 的解析度不對稱）。
        **在寫入路徑上那個誤報會放大成「整篇寫不進去」** ——
        而熱門看板上「發文一分鐘內就有人推」不是罕見情形。
        """
        m = self._run({URL_OK: counts(e(("推", "08/15 16:48"),
                                        ("推", "08/15 16:49")))})
        self.assertTrue(m.db_writer.upsert_article_comments.called)
        rows = m.db_writer.upsert_article_comments.call_args.args[0]
        self.assertEqual(len(rows), 2)


class TheUpperBoundWeakensWithArticleAge(unittest.TestCase):
    """⚠ **已知限制**：`above_scraped_at` 的偵測力**隨文章年齡衰減**。

    ================================================================================
    實測（2026-09-06）
    ================================================================================
    同一組亂序輸入，只換文章的年份：

    | 文章 | 假回捲推到 | `scraped_at`（= now） | 是否被抓 |
    |------|-----------|---------------------|---------|
    | **2019**（回補的主要對象） | 2020 | 2026 | **否** |
    | **2026**（每日路徑） | 2027 | 2026 | **是** |

    > **上界只擋得住「被推過現在」的假回捲。**
    > **一篇 2019 年的文章要連續假回捲七次才會撞到上界** ——
    > **而回補正好操作在它最弱的那一端。**

    ================================================================================
    為什麼仍然留著這個上界
    ================================================================================
    它是**結構上不可能為真**的那一個（留言不可能晚於抓取時刻），
    **零誤報**。每日路徑（新文章）在它的守備範圍內，而每日路徑是常態。

    ⚠ **但不得因為它存在就宣稱「亂序已被守住」** ——
    **本測試就是為了讓那個宣稱說不出口而寫的。**

    ================================================================================
    可能的補強（尚未實作，需裁決）
    ================================================================================
    **真正的跨年回捲必然是「12 月 → 1 月」。** 一個 `08/18 → 08/16` 的回捲
    要嘛是排序異常、要嘛是**超過一年的休眠**（而後者本來就已知會被推論成 +1 年
    而非 +2 年，見 `infer_comment_times` 的已知失效模式）——
    **兩者都是推論不可靠的情形，標記出來是誠實的。**

    **本測試釘住現況。若日後加了那條規則，本測試會變紅 ——
    那正是它該發生的時候。**
    """

    def test_an_old_articles_false_wrap_is_not_caught(self):
        from src.common.clock import now_taipei, to_taipei
        from src.transform.comment_timeline import (
            infer_comment_times, validate_comment_bounds)
        anchor = to_taipei(1565858907)          # 2019-08-15 16:48:27
        c = infer_comment_times(anchor, e(("推", "08/15 16:49"),
                                          ("推", "08/18 09:00"),
                                          ("推", "08/16 10:00")))
        self.assertEqual(c[2]["comment_time"].year, 2020,
                         "先確認假回捲確實發生 —— **不然這條測試沒在測它以為的東西**")
        self.assertEqual(validate_comment_bounds(c, anchor, now_taipei()), [],
                         "**這是已知限制，不是預期行為** —— "
                         "2020 遠早於現在，上界擋不住它")

    def test_a_recent_articles_false_wrap_is_caught(self):
        """**對照組** —— 同一種異常，近期文章就抓得到。"""
        import datetime as _dt
        from src.common.clock import now_taipei
        from src.transform.comment_timeline import (
            infer_comment_times, validate_comment_bounds)
        anchor = now_taipei() - _dt.timedelta(days=5)
        md = lambda d: (anchor + _dt.timedelta(days=d)).strftime("%m/%d 10:00")
        # ⚠ 全部取 anchor 之後的日子 —— `md()` 用固定的 10:00，
        # 若取 `md(0)` 會在同一天但更早的時刻，觸發的是 `below_post_time`
        # 而不是本測試要驗的 `above_scraped_at`。
        c = infer_comment_times(anchor, e(("推", md(1)), ("推", md(4)), ("推", md(2))))
        bad = validate_comment_bounds(c, anchor, now_taipei())
        self.assertTrue(bad, "近期文章的假回捲會被推過現在 —— 抓得到")
        self.assertEqual(bad[0]["violation"], "above_scraped_at")


if __name__ == "__main__":
    unittest.main()
