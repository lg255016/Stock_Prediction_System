# -*- coding: utf-8 -*-
"""UG-G2-SB7 B 輪（§0.3 的鏈第 3、4 段）：`SOURCE_FAILED` 列的情緒欄必須 NULL。

================================================================================
本檔釘住的四件事
================================================================================
1. **`SOURCE_FAILED` 可達** —— 先前 `source_status` 只由 `article_count > 0` 決定，
   **只產得出兩態**，而 `002_expand_ml_features.sql:86` 的 CHECK 允許四態。
2. **該態的列上，§5A.3「社群情緒」八欄全部 NULL** —— 契約 `:321` 逐字要求
   「該來源當日特徵保持 NULL；**不得**寫入 0 或中立值」。
3. **`SUCCESS_EMPTY` 的填值不變** —— 那是 RISK-020 的題目，**排定 Gate 3 啟動前裁決**，
   B 輪不提前動它。
4. **欄位清單不得在程式裡被複製** —— `SOCIAL_SENTIMENT_COLUMNS` 必須與
   `FEATURE_REGISTRY.md` §5A.3 逐欄相符，**由本檔解析該表格驗證**。

================================================================================
第 4 項為什麼要解析文件
================================================================================
複查方 2026-09-04 要求「八欄的處置由 §5A.3 驅動，程式裡不得再出現一份複製的欄位清單」。

**但程式終究需要知道是哪八欄** —— 完全不放清單做不到。
**能做到的是：讓那份清單與契約的落差會被抓到。**

> 這一輪的起因正是一份短了三欄的清單（複查方寫的、我照抄的）。
> **一個「指向 §5A.3」的承諾，若沒有任何東西在檢查它，
> 與一份複製的清單在輸出上完全一樣。**

⚠ **已知限制**：本檢查驗證的是「程式的清單 == 文件的清單」，
**不驗證那八欄的處置是否正確** —— 後者由本檔其餘測試負責。
"""
import io
import os
import re
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(REPO, "doc", "upgrade", "contracts", "FEATURE_REGISTRY.md")


def parse_registry_social_columns():
    """由 `FEATURE_REGISTRY.md` §5A.3 解析「社群」群組中標「必須 NULL」的欄位。

    **刻意解析文件而非硬編碼** —— 見模組 docstring 第 4 項。

    ⚠ 只取第二欄**恰為**「社群」者：「社群留言」是另一個群組
    （`comment_volume_ratio`／`comment_polarization`），**它們本來就不填補、已合規**，
    不屬本輪範圍。
    """
    cols = []
    for line in io.open(REGISTRY, encoding="utf-8"):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        group = cells[1].replace("*", "").strip()
        rule = cells[3].replace("*", "").strip()
        if group != "社群" or "必須 NULL" not in rule:
            continue
        for name in re.findall(r"`([a-z0-9_]+)`", cells[0]):
            cols.append(name)
    return cols


class TheColumnListMustNotDriftFromTheContract(unittest.TestCase):
    """**程式的清單與 §5A.3 逐欄相符。**

    **什麼輸入會讓它 FAIL**：契約增列一欄而程式沒跟上（或反之）——
    **正是這一輪的起因**（一份短了三欄的清單）。
    """

    def test_registry_lists_exactly_eight_social_columns(self):
        """⚠ **這裡的 `8` 是釘子，不是契約要求。**

        **「§5A.3 必須恰好八欄」不是規定** —— 契約可以增列。
        這個數字的作用是：**日後若增列，有人必須有意識地承認那個變化**，
        而不是無聲跟上。**測試變紅就是那個「必須承認」的時刻。**

        （複查方 2026-09-04 指出：一個硬編碼的 `8` 出現在一組
        「防止硬編碼清單」的測試裡，**若不寫明它是釘子，
        下一個人會把它讀成規定** —— 同 A 輪對「四態欄位」的那句話。）
        """
        cols = parse_registry_social_columns()
        self.assertEqual(len(cols), 8,
                         "§5A.3 的『社群情緒』群組解析得 %r —— "
                         "**若契約確實增列了，改這個數字並在此說明；"
                         "本斷言是釘子，不是契約要求**" % cols)

    def test_code_constant_matches_the_registry(self):
        from src.transform.feature_aggregator import SOCIAL_SENTIMENT_COLUMNS
        self.assertEqual(sorted(SOCIAL_SENTIMENT_COLUMNS),
                         sorted(parse_registry_social_columns()),
                         "程式的清單與 FEATURE_REGISTRY.md §5A.3 不一致 —— "
                         "**一個『指向 §5A.3』的承諾，若沒有東西在檢查它，"
                         "與一份複製的清單在輸出上完全一樣**")

    def test_comment_group_is_deliberately_out_of_scope(self):
        """`comment_*` 兩欄不在本輪範圍 —— 它們本來就不填補，已合規。"""
        cols = parse_registry_social_columns()
        self.assertNotIn("comment_volume_ratio", cols)
        self.assertNotIn("comment_polarization", cols)


# 2026-09-14，DEC-039：generate_daily_features() 現在要求 df_comments（不得省略）。
# 本檔多處 fixture 用 push_count=5/boo_count=1/total_comments=6（article_id=1，
# post_time 2026-09-01 10:00:00）——這裡是對應的逐則留言（5 推 1 噓，皆在
# post_time 之後幾分鐘，早於任何決策點與 comments_scraped_at）。本檔測試都不
# 斷言留言特徵的值，這裡只需要滿足介面契約，不影響任何既有斷言。
_ARTICLE_1_COMMENTS = pd.DataFrame(
    [{"article_id": 1, "comment_seq": i + 1, "comment_tag": "推",
      "comment_time": pd.Timestamp("2026-09-01 10:00:00") + pd.Timedelta(minutes=i + 1)}
     for i in range(5)]
    + [{"article_id": 1, "comment_seq": 6, "comment_tag": "噓",
        "comment_time": pd.Timestamp("2026-09-01 10:06:00")}]
)


class SourceFailedRowsMustHaveNullSentiment(unittest.TestCase):
    """契約 `:321`：`SOURCE_FAILED` 時該來源當日特徵**全部 NULL**。"""

    def _frame(self):
        """兩檔股票、三天；其中 (2330, D2) 為來源失敗。"""
        rows = []
        for sid in ("2330", "2382"):
            for i, d in enumerate(pd.to_datetime(
                    ["2026-09-01", "2026-09-02", "2026-09-03"])):
                rows.append({"stock_id": sid, "trade_date": d,
                             "open_price": 100.0 + i, "high_price": 101.0 + i,
                             "low_price": 99.0 + i, "close_price": 100.5 + i,
                             "volume": 1000 + i})
        return pd.DataFrame(rows)

    def _articles(self):
        # 欄名沿用 `tests/test_feature_aggregator_alignment.py` 的實測形態
        # （`fetch_keyword` 是聚合器 join 的鍵，不是 `keyword`）。
        return pd.DataFrame([{
            "article_id": 1, "fetch_keyword": "台積電",
            "post_time": pd.Timestamp("2026-09-01 10:00:00"),
            "sentiment_score": 0.8, "push_count": 5, "boo_count": 1,
            "neutral_count": 0, "total_comments": 6, "title": "t", "url": "u",
        }])

    def _mapping(self):
        return pd.DataFrame([{"keyword": "台積電", "stock_id": "2330",
                              "market": "TWSE"}])

    def _run(self, failed=None):
        from src.transform.feature_aggregator import FeatureAggregator
        return FeatureAggregator().generate_daily_features(
            self._frame(), self._articles(), self._mapping(),
            failed_source_keys=failed, df_comments=_ARTICLE_1_COMMENTS)

    def test_source_failed_is_reachable(self):
        """**known-FAIL**：先前 `source_status` 只產得出兩態。"""
        df = self._run(failed={("2330", "2026-09-02")})
        got = set(df["source_status"].dropna().unique())
        self.assertIn("SOURCE_FAILED", got,
                      "先前只由 article_count > 0 決定，**只產得出兩態** —— "
                      "而 DB 的 CHECK 允許四態")

    def test_all_eight_columns_are_null_on_failed_rows(self):
        from src.transform.feature_aggregator import SOCIAL_SENTIMENT_COLUMNS
        df = self._run(failed={("2330", "2026-09-02")})
        row = df[(df["stock_id"] == "2330")
                 & (df["trade_date"].astype(str) == "2026-09-02")]
        self.assertEqual(len(row), 1)
        for col in SOCIAL_SENTIMENT_COLUMNS:
            self.assertTrue(
                pd.isna(row.iloc[0][col]),
                "%s 在 SOURCE_FAILED 列上必須 NULL —— 契約 :321 逐字："
                "「該來源當日特徵保持 NULL；**不得**寫入 0 或中立值」" % col)

    def test_moving_averages_are_null_on_failed_rows(self):
        """**MA 的 NULL 是契約要求，不是本輪的設計選擇。**

        `rolling(min_periods=1)` 會跳過 NaN，**在失敗日仍給出一個由鄰近日
        推出的、看起來合理的數字** —— 那比它取代的 `0.5` 更難發現。
        """
        df = self._run(failed={("2330", "2026-09-02")})
        row = df[(df["stock_id"] == "2330")
                 & (df["trade_date"].astype(str) == "2026-09-02")].iloc[0]
        self.assertTrue(pd.isna(row["sentiment_3d_ma"]))
        self.assertTrue(pd.isna(row["sentiment_5d_ma"]))

    def test_article_count_is_null_not_zero_on_failed_rows(self):
        """**`article_count = 0` 就是「失敗長得像沒資料」本身。**

        它是這條鏈最直接的表現形式 —— **`0` 是一個看起來完全正常的計數**。
        """
        df = self._run(failed={("2330", "2026-09-02")})
        row = df[(df["stock_id"] == "2330")
                 & (df["trade_date"].astype(str) == "2026-09-02")].iloc[0]
        self.assertTrue(pd.isna(row["article_count"]),
                        "0 與 NULL 在這裡的差別，就是「沒有文章」與「不知道有沒有文章」")


class SuccessEmptyFillingMustNotChange(unittest.TestCase):
    """**D5（`PRE-G3-04`）落地**：`SUCCESS_EMPTY` 空日的 `sentiment_mean`
    由填 `0.5` 改為保持 `NULL`（成因 U）——`0.5` 是編出來的，不是算出來的。

    ⚠ **本類別的舊註解曾誤指向 `RISK-020`**——核對後 `RISK-020` 是**價量欄位**
    （`ma5_bias_ratio` 等）的暖機期填值裁決，與這裡的**社群情緒**填值是不同風險項。
    此為既有文件的小瑕疵，隨 D5 一併修正指向，不歸咎於任何人。

    **什麼輸入會讓 `test_success_empty_keeps_the_neutral_fill` FAIL**：
    還原成舊斷言（`sentiment_mean == 0.5`）——證明本測試真的在測 D5 的新行為，
    不是恆真。
    """

    def _run_no_failure(self):
        from src.transform.feature_aggregator import FeatureAggregator
        prices = pd.DataFrame([
            {"stock_id": "2330", "trade_date": pd.Timestamp("2026-09-01"),
             "open_price": 100.0, "high_price": 101.0, "low_price": 99.0,
             "close_price": 100.5, "volume": 1000},
            {"stock_id": "2330", "trade_date": pd.Timestamp("2026-09-02"),
             "open_price": 101.0, "high_price": 102.0, "low_price": 100.0,
             "close_price": 101.5, "volume": 1100},
        ])
        return FeatureAggregator().generate_daily_features(
            prices, pd.DataFrame(), pd.DataFrame(
                [{"keyword": "台積電", "stock_id": "2330", "market": "TWSE"}]))

    def test_success_empty_keeps_the_neutral_fill(self):
        """**T1**（斷言方向反轉）：`sentiment_mean`／`3d_ma`／`5d_ma` 皆 `NULL`；
        `lag_1`／`lag_2` 除序列前 1～2 列的真暖機期（`cumcount()` 判定，仍填 `0.5`）外
        亦保持 `NULL`；`article_count`／`bullishness_index`／`agreement_index`
        是空日真值，維持填 `0`／`0.0` 不變。
        """
        df = self._run_no_failure().sort_values(
            "trade_date").reset_index(drop=True)
        self.assertTrue((df["source_status"] == "SUCCESS_EMPTY").all())

        self.assertTrue(
            df["sentiment_mean"].isna().all(),
            "SUCCESS_EMPTY 的 sentiment_mean 應為 NULL（成因 U）—— "
            "D5 落地後 0.5 是編出來的，不是算出來的")
        self.assertTrue(df["sentiment_3d_ma"].isna().all())
        self.assertTrue(df["sentiment_5d_ma"].isna().all())

        # lag_1：本股票序列只有 2 列。第 1 列（cumcount=0）是真暖機期，填 0.5；
        # 第 2 列（cumcount=1）非真暖機期，其 shift(1) 來自第 1 列（本身是 U），
        # 屬 U 傳播，保持 NULL。
        self.assertEqual(df.iloc[0]["sentiment_lag_1"], 0.5)
        self.assertTrue(pd.isna(df.iloc[1]["sentiment_lag_1"]))
        # lag_2：兩列的 cumcount（0、1）皆 < 2，皆為真暖機期，皆填 0.5。
        self.assertEqual(df.iloc[0]["sentiment_lag_2"], 0.5)
        self.assertEqual(df.iloc[1]["sentiment_lag_2"], 0.5)

        self.assertTrue((df["article_count"] == 0).all())
        self.assertTrue((df["bullishness_index"] == 0.0).all())
        self.assertTrue((df["agreement_index"] == 0.0).all())

    def test_default_call_without_failed_keys_is_unchanged(self):
        """**未傳 `failed_source_keys` 時，判定 U／F 的邏輯路徑不變**——

        `source_status` 永遠不為 NULL；`sentiment_mean` 在空日（U）為 NULL
        本身是 D5 之後的正確行為，**不再是「必為 0」**（那正是本測試修訂前
        鎖住的舊行為）。
        """
        df = self._run_no_failure()
        self.assertEqual(int(df["sentiment_mean"].isna().sum()), 2,
                         "兩列皆為 SUCCESS_EMPTY（成因 U），D5 之後應皆為 NULL")
        self.assertEqual(int(df["source_status"].isna().sum()), 0)


class TrueWarmupIsDistinguishedFromUnknownPropagation(unittest.TestCase):
    """D5：`sentiment_lag_1`／`sentiment_lag_2` 的 `NULL` 不再是單一成因。

    `groupby().shift(1)` 產生的 `NaN` 分不出「序列第一列（真暖機期，W）」與
    「前一列本身是空日（U 已生效）」——`groupby().cumcount()` 是與 `NaN` 成因
    無關的獨立判準，本類別鎖住這個區分本身。
    """

    def _frame(self):
        return pd.DataFrame([
            {"stock_id": "2330", "trade_date": d,
             "open_price": 100.0, "high_price": 101.0, "low_price": 99.0,
             "close_price": 100.5, "volume": 1000}
            for d in pd.to_datetime(
                ["2026-09-01", "2026-09-02", "2026-09-03"])
        ])

    def _articles_day1_only(self):
        return pd.DataFrame([{
            "article_id": 1, "fetch_keyword": "台積電",
            "post_time": pd.Timestamp("2026-09-01 10:00:00"),
            "sentiment_score": 0.8, "push_count": 5, "boo_count": 1,
            "neutral_count": 0, "total_comments": 6, "title": "t", "url": "u",
        }])

    def _mapping(self):
        return pd.DataFrame([{"keyword": "台積電", "stock_id": "2330",
                              "market": "TWSE"}])

    def _run(self):
        from src.transform.feature_aggregator import FeatureAggregator
        return FeatureAggregator().generate_daily_features(
            self._frame(), self._articles_day1_only(), self._mapping(),
            df_comments=_ARTICLE_1_COMMENTS,
        ).sort_values("trade_date").reset_index(drop=True)

    def test_lag1_true_warmup_vs_u_propagation(self):
        """**T2**：第 1 列有資料、第 2、3 列空。

        `lag_1[第 2 列]` = 第 1 列的值（真實已知，非 NULL）；
        `lag_1[第 3 列]` 為 NULL（第 2 列本身未知，U 傳播，不是真暖機期）。

        **known-FAIL**：若誤用「`NaN` 即填 0.5」的舊邏輯，
        `lag_1[第 3 列]` 會變成 `0.5`，本斷言 FAIL。
        """
        df = self._run()
        self.assertAlmostEqual(df.iloc[1]["sentiment_lag_1"], 0.8)
        self.assertTrue(
            pd.isna(df.iloc[2]["sentiment_lag_1"]),
            "第 3 列的 lag_1 該保持 NULL —— 第 2 列本身是空日（U），"
            "不是真暖機期，填 0.5 會把「不知道」偽裝成「昨天中立」")

    def test_lag1_row0_is_true_warmup_and_still_filled(self):
        """第 1 列（`cumcount()==0`）沒有前一天，這是**真暖機期**（W），維持填 0.5。"""
        df = self._run()
        self.assertEqual(df.iloc[0]["sentiment_lag_1"], 0.5)

    def test_3d_ma_partial_window_uses_nanmean_not_polluted_average(self):
        """**T3**：3 日視窗中僅 1 日有資料、2 日空。

        結果應為該 1 日的原始值（`rolling(min_periods=1)` 的 nanmean 語意），
        不是「與 0.5 混合」的平均。

        **known-FAIL**：若上游仍對空日填 0.5 再取平均，
        第 3 列會得到 `(0.8+0.5+0.5)/3` 而非 `0.8`，本斷言 FAIL。
        """
        df = self._run()
        self.assertAlmostEqual(df.iloc[2]["sentiment_3d_ma"], 0.8)


class FailedAndEmptyClearanceScopesAreDisjoint(unittest.TestCase):
    """**T4**：F 分支（`SOURCE_FAILED`）清 8 欄，含 `article_count`；
    U 分支（空日但非失敗）只清 5 欄，`article_count` 仍為 0（真值）。
    """

    def _frame(self):
        rows = []
        for sid in ("2330", "2382"):
            for d in pd.to_datetime(["2026-09-01", "2026-09-02"]):
                rows.append({"stock_id": sid, "trade_date": d,
                             "open_price": 100.0, "high_price": 101.0,
                             "low_price": 99.0, "close_price": 100.5,
                             "volume": 1000})
        return pd.DataFrame(rows)

    def _mapping(self):
        return pd.DataFrame([
            {"keyword": "台積電", "stock_id": "2330", "market": "TWSE"},
            {"keyword": "聯電", "stock_id": "2382", "market": "TWSE"},
        ])

    def _run(self):
        from src.transform.feature_aggregator import FeatureAggregator
        # 2330 於 2026-09-02 為來源失敗（F）；2382 兩天皆無文章、非失敗（U）。
        # 兩檔皆完全無文章資料，故本次不傳 df_articles（維持既有測試慣例：
        # 完全無文章觸發 daily_sentiment 全空的分支，見 :475-480）。
        return FeatureAggregator().generate_daily_features(
            self._frame(), pd.DataFrame(), self._mapping(),
            failed_source_keys={("2330", "2026-09-02")})

    def test_failed_clears_article_count_but_u_does_not(self):
        from src.transform.feature_aggregator import SOCIAL_SENTIMENT_COLUMNS
        df = self._run()
        failed_row = df[(df["stock_id"] == "2330")
                        & (df["trade_date"].astype(str) == "2026-09-02")].iloc[0]
        u_row = df[(df["stock_id"] == "2382")
                   & (df["trade_date"].astype(str) == "2026-09-02")].iloc[0]

        for col in SOCIAL_SENTIMENT_COLUMNS:
            self.assertTrue(pd.isna(failed_row[col]),
                            "F 分支：%s 必須 NULL（含 article_count）" % col)

        self.assertTrue(pd.isna(u_row["sentiment_mean"]),
                        "U 分支：sentiment_mean 應為 NULL")
        self.assertEqual(
            u_row["article_count"], 0,
            "U 分支：article_count 是空日的真值 0，不是 NULL —— "
            "與 F 分支的清空範圍不同，這正是本測試要鎖住的差異")


if __name__ == "__main__":
    unittest.main()
