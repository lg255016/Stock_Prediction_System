# -*- coding: utf-8 -*-
"""UG-G2-SB7 收尾：時區政策 —— 生產程式碼不得使用 naive 的「現在」。

================================================================================
這條測試的由來：一個我自己造成的 look-ahead
================================================================================
`e67d3d6` 把 `market_articles.post_time` 改為由網址時間戳決定並顯式轉 **UTC+8**，
**卻沒有一併處理同一列的 `comments_scraped_at`** —— 後者仍是
`main_etl_pipeline.py` 的 `datetime.now()`，而 **dev container 的時區是 UTC**。

受控執行寫出來的那一列因此長成這樣：

```
post_time            2026-09-05 10:07:38   ← UTC+8
comments_scraped_at  2026-09-05 05:53:32   ← UTC
```

**留言看起來在文章發表前 4 小時就被抓走了。**

而 `feature_aggregator.py:768` 正是 DEC-024 的時點有效性判準：

```python
decision_point = trade_date + cutoff_time            # 15:30，台北收盤
df = df[df['comments_scraped_at'] <= decision_point]
```

> ⚠⚠ **偏差的方向是寬鬆的**：`comments_scraped_at` 被記早 8 小時，
> **所以它比應該的更容易通過那個過濾。**
> 一次台北 **20:00** 的抓取會被記成 **12:00**、通過 15:30 的 cutoff ——
> **只有在 20:00 才知道的留言數，被算進 15:30 就要下的決策。**
>
> **那是 `CLAUDE.md` §7.4 的 Look-ahead，
> 而它發生在一條「存在的唯一理由就是防前視」的過濾裡。**

================================================================================
為什麼是「政策 + 掃描」，不是「補那一處」
================================================================================
**修一半比不修更危險** —— 這句話是本 SB 在 TPEx `_find_market_table`
那次自己說的，而 `e67d3d6` 正是修了一半。

掃描（**不是列舉**）找到的不只 `comments_scraped_at`：

| 位置 | 後果 |
|------|------|
| `main_etl_pipeline` `started_at` | 寫進 `etl_run_log`，稽核時間基準不明 |
| `main_etl_pipeline` `comments_scraped_at` | **上述 look-ahead** |
| `main_etl_pipeline` `now.strftime("%Y%m01")` | 決定逐股取數抓**哪一個月** |
| **`market_report_fetcher.previous_business_day`** | 決定批次取數抓**哪一個交易日** |
| `data_cleaner` 的 `reference_time` 預設 | 跨年推論的基準（現為回退路徑） |

> **最後兩處都不在最初被指出的清單裡。**
> **台北時間每月最後一天的 16:00–24:00，UTC 還停在前一天** ——
> `%Y%m01` 會抓錯月份，`previous_business_day()` 會抓錯日期。
>
> **列舉四處，等於承認第五處不受保護。**

================================================================================
⚠ 用 AST，不用 grep
================================================================================
`data_cleaner.py` 的 docstring 裡就寫著「預設為 `datetime.now()`」——
**一個 grep 會把那句說明判成違規。**

**靜態字串掃描在原理上分不出「呼叫它」與「提到它」**，
同 `PROJECT_STATUS.md` §0.5 記載的 stub 稽核（分不出 `use` 與 `replace`）。
本檔因此解析 AST，只看真正的 `Call` 節點。

================================================================================
刻意**不**禁止的東西
================================================================================
- **`time.time()`** —— epoch 秒**沒有時區**，不會有基準問題。
  `main_etl_pipeline` 的 `since_ts = time.time() - N*86400` 拿去跟
  **網址內嵌的 epoch 時間戳**比較，兩邊同基準，**它是對的，不要改**。
- **`datetime.now(tz)`（帶參數）** —— 已指定時區。
- **`scripts/verify/` 與 `tests/`** —— 前者產出的是證據檔且已用
  `.astimezone()` 記下 offset，不寫入資料庫；後者是測試本身。
"""
import ast
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# **描述範圍，不列舉檔案** —— 列舉會讓下一個新增的檔案不受保護。
SCAN_ROOTS = [os.path.join(REPO, "src"), os.path.join(REPO, "main_etl_pipeline.py")]

# 唯一允許定義「現在」的地方。
POLICY_MODULE = os.path.join(REPO, "src", "common", "clock.py")

NAIVE_NOW = {"now", "today", "utcnow"}


def python_files():
    for root in SCAN_ROOTS:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, names in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for n in names:
                if n.endswith(".py"):
                    yield os.path.join(dirpath, n)


def naive_now_calls(path):
    """回傳 `[(lineno, 原始碼片段), ...]`。

    **只看 AST 的 `Call` 節點** —— docstring 與註解裡提到 `datetime.now()`
    不算違規（見模組 docstring）。
    """
    src = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:      # pragma: no cover
        raise AssertionError("%s 無法解析：%s" % (path, exc))
    lines = src.splitlines()
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr not in NAIVE_NOW:
            continue
        # `datetime.now(TAIPEI)` 已指定時區 —— 放行。
        # `utcnow()` 即使無參數也一律禁止（它回傳 naive UTC，是最容易誤用的一個）。
        if fn.attr != "utcnow" and (node.args or node.keywords):
            continue
        hits.append((node.lineno, lines[node.lineno - 1].strip()[:90]))
    return hits


class NoNaiveNowInProductionCode(unittest.TestCase):
    """**known-FAIL 主體**：任何一處 naive 的「現在」都要讓它紅。"""

    def test_no_naive_now_anywhere_in_src_or_pipeline(self):
        bad = []
        for path in python_files():
            if os.path.abspath(path) == os.path.abspath(POLICY_MODULE):
                continue
            for lineno, text in naive_now_calls(path):
                bad.append("%s:%d  %s" % (os.path.relpath(path, REPO),
                                          lineno, text))
        self.assertEqual(
            bad, [],
            "生產程式碼不得使用 naive 的「現在」——容器時區是 UTC，"
            "而本專案的所有業務基準是台北時間（UTC+8）。\n"
            "請改用 `src/common/clock.py` 的 `now_taipei()`／`today_taipei()`。\n"
            "違規處：\n  " + "\n  ".join(bad))

    def test_the_scan_actually_covers_the_files_we_think_it_does(self):
        """**反向釘子**：掃描範圍不得縮成空集合。

        **什麼輸入會讓它 FAIL**：`SCAN_ROOTS` 被改成一個不存在的路徑 ——
        那時上面那條會「通過」，而它什麼都沒看。
        **一個掃了零個檔案的掃描，與一個沒有違規的掃描，輸出完全一樣。**
        """
        files = list(python_files())
        self.assertGreater(len(files), 15, "掃描到的檔案太少，範圍可能壞了")
        rel = {os.path.relpath(f, REPO).replace("\\\\", "/") for f in files}
        self.assertIn("main_etl_pipeline.py", rel)
        self.assertTrue(any(r.startswith("src/transform") for r in rel))
        self.assertTrue(any(r.startswith("src/extractors") for r in rel))
        self.assertTrue(any(r.startswith("src/loaders") for r in rel))

    def test_ast_does_not_flag_prose_mentions(self):
        """**反向釘子**：docstring 裡提到 `datetime.now()` 不算違規。

        **什麼輸入會讓它 FAIL**：改用 grep —— `data_cleaner.py` 的 docstring
        逐字寫著「預設為 `datetime.now()`」，會被判成違規。
        """
        import tempfile
        src = ('"""說明：預設為 datetime.now()，見文件。"""\n'
               "# 註解裡也提到 datetime.now()\n"
               "x = 1\n")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(src)
            tmp = fh.name
        try:
            self.assertEqual(naive_now_calls(tmp), [],
                             "AST 不得把文字說明判成呼叫")
        finally:
            os.unlink(tmp)


class ThePolicyModuleItself(unittest.TestCase):
    """單一入口的行為。"""

    def test_now_taipei_is_utc_plus_8_and_naive(self):
        from src.common.clock import now_taipei
        import datetime as dt
        got = now_taipei()
        self.assertIsNone(got.tzinfo,
                          "寫進 DB 的欄位是 TIMESTAMP WITHOUT TIME ZONE，"
                          "**轉換在寫入前完成**")
        expected = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
        self.assertLess(abs((got - expected.replace(tzinfo=None)).total_seconds()),
                        5)

    def test_today_taipei_matches_now_taipei(self):
        from src.common.clock import now_taipei, today_taipei
        self.assertEqual(today_taipei(), now_taipei().date())

    def test_it_does_not_depend_on_the_machine_timezone(self):
        """**這是重點** —— 容器是 UTC，而答案必須是台北時間。"""
        import datetime as dt
        import time as _time
        from src.common.clock import now_taipei
        utc_now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        delta = (now_taipei() - utc_now).total_seconds()
        if _time.tzname[0] in ("UTC", "GMT"):
            self.assertAlmostEqual(delta, 8 * 3600, delta=5,
                                   msg="容器為 UTC 時，now_taipei() 必須比它快 8 小時")
        self.assertAlmostEqual(delta, 8 * 3600, delta=5)


if __name__ == "__main__":
    unittest.main()
