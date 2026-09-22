# tests/test_risk027_cross_market_calendar.py
"""RISK-027 紅測（RED）——跨市場交易日曆聯集造成文章流失。

背景（`REMAINING_RISKS.md` RISK-027，2026-09-11 登記；bug-fix-protocol Gate A，
PO 2026-09-11 裁決採**方案 B**：文章依其對應股票自身的交易日曆做 Roll-Forward，
取代現行 `feature_aggregator.py:310` 的全市場聯集單一日曆）。

**根因**：`generate_daily_features()` 用所有股票 `trade_date` 的聯集當成唯一交易日曆，
`map_timestamp_to_trading_day()`（:133）因此把「任一檔有交易」誤判為「不是假日」。
當台股與美股（如 NVDA）混在同一批輸入時，只要該日美股有交易，台股的假日文章就不會
被滾動到下一個台股交易日，而是被釘死在一個台股根本不存在的日期——該篇文章之後在
與 `df_prices`（僅含各股自身真實交易日）合併時被靜默丟棄。

**已查證前提**（真實庫，唯讀，2026-09-11）：`theme_stock_mapping` 的「AI伺服器」題材
同時涵蓋 TWSE 股票與 NVDA——跨市場溢出是既有真實資料形狀，本檔的題材測試場景
並非虛構案例。

**本檔狀態**：方案 B 實作**前**，以下四個測試方法**必須全數 FAIL**（作為 Gate A
核准的診斷之可重現證據）；實作完成後必須全數 PASS，**不得為了通過而調整斷言**
（`CLAUDE.md` §9A.1）。控制組（NVDA）的斷言在修復前後皆應成立，用以證明修復
沒有改變美股自身不受影響的案例。
"""
import unittest
from datetime import date
from contextlib import redirect_stdout
import io

import pandas as pd

from src.transform.feature_aggregator import FeatureAggregator


# 2026-09-14，DEC-039：generate_daily_features() 現在要求 df_comments（不得省略）。
# 從本檔既有的彙總式 fixture（push_count/boo_count/total_comments）反推等價的
# 逐則留言列，讓既有測試在新引擎下維持相同語意。留言時間戳全部落在 post_time
# 之後的安全窗口內，不影響任何本檔測試原本要驗證的 Roll-Forward／跨市場行為。
def _comments_from_articles(df_articles):
    rows = []
    for _, art in df_articles.iterrows():
        total = art.get("total_comments")
        if total is None or pd.isna(total):
            continue
        total = int(total)
        push = int(art["push_count"]) if pd.notna(art.get("push_count")) else 0
        boo = int(art["boo_count"]) if pd.notna(art.get("boo_count")) else 0
        neutral = max(total - push - boo, 0)
        tags = ["推"] * push + ["噓"] * boo + ["→"] * neutral
        post_time = pd.to_datetime(art["post_time"])
        for i, tag in enumerate(tags):
            rows.append({
                "article_id": art["article_id"], "comment_seq": i + 1,
                "comment_tag": tag, "comment_time": post_time + pd.Timedelta(minutes=i + 1),
            })
    return pd.DataFrame(rows, columns=["article_id", "comment_seq", "comment_tag", "comment_time"])


class CrossMarketCalendarRollForwardTests(unittest.TestCase):
    """合成資料：一檔台股（2330）＋一檔美股（NVDA），2026-08-17（週一）為
    台股假日、美股正常交易日。"""

    def setUp(self):
        # 2330（TWSE）：8/14（五）、8/18（二）有交易；8/17（一）休市。
        # NVDA（US）：8/14、8/17、8/18 皆有交易。
        self.df_prices = pd.DataFrame({
            "trade_date": [
                "2026-08-14", "2026-08-18",
                "2026-08-14", "2026-08-17", "2026-08-18",
            ],
            "stock_id": ["2330", "2330", "NVDA", "NVDA", "NVDA"],
            "close_price": [1000.0, 1010.0, 120.0, 121.0, 122.0],
            "volume": [10_000, 10_500, 5_000_000, 5_100_000, 5_200_000],
        })
        self.df_mapping = pd.DataFrame({
            "keyword": ["台積電", "NVDA"],
            "stock_id": ["2330", "NVDA"],
        })
        with redirect_stdout(io.StringIO()):
            self.aggregator = FeatureAggregator()

    def _run(self, df_articles, df_theme_mapping=None):
        with redirect_stdout(io.StringIO()):
            return self.aggregator.generate_daily_features(
                self.df_prices, df_articles, self.df_mapping,
                df_theme_mapping=df_theme_mapping,
                df_comments=_comments_from_articles(df_articles),
            )

    def test_direct_article_routes_to_each_stocks_own_trading_day(self):
        # 兩篇直接個股文章，皆發在 8/17 09:00（台股假日、美股交易日）。
        df_articles = pd.DataFrame({
            "article_id": [1, 2],
            "fetch_keyword": ["台積電", "NVDA"],
            "post_time": ["2026-08-17 09:00:00", "2026-08-17 09:00:00"],
            "sentiment_score": [0.8, 0.6],
        })
        df_features = self._run(df_articles)

        # 2330：8/17 非台股交易日，應滾動歸入下一個台股交易日 8/18。
        row_2330 = df_features[
            (df_features["stock_id"] == "2330")
            & (df_features["trade_date"] == date(2026, 8, 18))
        ]
        self.assertEqual(len(row_2330), 1, "2330 於 8/18 應有一列")
        row_2330 = row_2330.iloc[0]
        self.assertEqual(
            row_2330["article_count"], 1,
            "2330 的文章不得因台股假日與美股交易日撞期而流失"
        )
        self.assertAlmostEqual(row_2330["sentiment_mean"], 0.8)

        # NVDA（控制組）：8/17 本來就是 NVDA 交易日，應直接歸入當天，
        # 此斷言在修復前後皆應成立。
        row_nvda = df_features[
            (df_features["stock_id"] == "NVDA")
            & (df_features["trade_date"] == date(2026, 8, 17))
        ].iloc[0]
        self.assertEqual(row_nvda["article_count"], 1)
        self.assertAlmostEqual(row_nvda["sentiment_mean"], 0.6)

    def test_theme_spillover_article_splits_to_each_stocks_own_trading_day(self):
        # 題材溢出：同一篇「AI伺服器」文章同時對 2330 與 NVDA 有效，
        # 對應真實庫的 theme_stock_mapping 形狀（見檔頭已查證前提）。
        df_theme_mapping = pd.DataFrame({
            "theme_keyword": ["AI伺服器", "AI伺服器"],
            "stock_id": ["2330", "NVDA"],
            "relevance_weight": [1.0, 1.0],
        })
        df_articles = pd.DataFrame({
            "article_id": [3],
            "fetch_keyword": ["AI伺服器"],
            "post_time": ["2026-08-17 09:30:00"],
            "sentiment_score": [0.9],
        })
        df_features = self._run(df_articles, df_theme_mapping=df_theme_mapping)

        row_2330 = df_features[
            (df_features["stock_id"] == "2330")
            & (df_features["trade_date"] == date(2026, 8, 18))
        ]
        self.assertEqual(len(row_2330), 1)
        row_2330 = row_2330.iloc[0]
        self.assertEqual(
            row_2330["article_count"], 1,
            "跨市場題材溢出對 2330 的貢獻不得因撞期流失"
        )
        self.assertAlmostEqual(row_2330["sentiment_mean"], 0.9)

        row_nvda = df_features[
            (df_features["stock_id"] == "NVDA")
            & (df_features["trade_date"] == date(2026, 8, 17))
        ].iloc[0]
        self.assertEqual(row_nvda["article_count"], 1)
        self.assertAlmostEqual(row_nvda["sentiment_mean"], 0.9)

    def test_comment_counts_follow_same_per_stock_trading_day(self):
        # 留言方向計數（push/boo）必須跟情緒欄用同一條 trade_date 指派規則，
        # 不能只修情緒欄、漏了 _aggregate_direct_comment_counts()。
        df_articles = pd.DataFrame({
            "article_id": [1, 2],
            "fetch_keyword": ["台積電", "NVDA"],
            "post_time": ["2026-08-17 09:00:00", "2026-08-17 09:00:00"],
            "sentiment_score": [0.8, 0.6],
            "source": ["ptt_stock", "ptt_stock"],
            "total_comments": [20, 30],
            "comments_scraped_at": ["2026-08-17 10:00:00", "2026-08-17 10:00:00"],
            "push_count": [15, 20],
            "boo_count": [5, 10],
        })
        df_features = self._run(df_articles)

        row_2330 = df_features[
            (df_features["stock_id"] == "2330")
            & (df_features["trade_date"] == date(2026, 8, 18))
        ].iloc[0]
        # push_ratio = (15-5)/(15+5+1) = 10/21；comment_polarization = 1 - push_ratio^2
        self.assertFalse(
            pd.isna(row_2330["comment_polarization"]),
            "2330 的留言方向資料不得隨情緒資料一起流失"
        )
        self.assertAlmostEqual(row_2330["comment_polarization"], 1 - (10 / 21) ** 2, places=6)

        row_nvda = df_features[
            (df_features["stock_id"] == "NVDA")
            & (df_features["trade_date"] == date(2026, 8, 17))
        ].iloc[0]
        self.assertFalse(pd.isna(row_nvda["comment_polarization"]))
        self.assertAlmostEqual(row_nvda["comment_polarization"], 1 - (10 / 31) ** 2, places=6)

    def test_mixed_market_input_matches_single_market_input_for_each_stock(self):
        """不變性判準（PO 補充，2026-09-12）：混合市場輸入下每檔的輸出，
        必須等於該檔單獨輸入時的輸出。不依賴任何手算常數，只依賴這個不變量，
        因此無法透過「調整期望值」通過——這條測試的正確性判準就是它自己的結構。
        """
        df_theme_mapping = pd.DataFrame({
            "theme_keyword": ["AI伺服器", "AI伺服器"],
            "stock_id": ["2330", "NVDA"],
            "relevance_weight": [1.0, 1.0],
        })
        df_articles = pd.DataFrame({
            "article_id": [1, 2, 3],
            "fetch_keyword": ["台積電", "NVDA", "AI伺服器"],
            "post_time": [
                "2026-08-17 09:00:00",
                "2026-08-17 09:00:00",
                "2026-08-17 09:30:00",
            ],
            "sentiment_score": [0.8, 0.6, 0.9],
            "source": ["ptt_stock", "ptt_stock", None],
            "total_comments": [20, 30, None],
            "comments_scraped_at": [
                "2026-08-17 10:00:00", "2026-08-17 10:00:00", None,
            ],
            "push_count": [15, 20, None],
            "boo_count": [5, 10, None],
        })

        comments = _comments_from_articles(df_articles)
        with redirect_stdout(io.StringIO()):
            df_mixed = self.aggregator.generate_daily_features(
                self.df_prices, df_articles, self.df_mapping,
                df_theme_mapping=df_theme_mapping, df_comments=comments,
            )
            df_prices_2330_only = self.df_prices[
                self.df_prices["stock_id"] == "2330"
            ].reset_index(drop=True)
            df_single = self.aggregator.generate_daily_features(
                df_prices_2330_only, df_articles, self.df_mapping,
                df_theme_mapping=df_theme_mapping, df_comments=comments,
            )

        compare_cols = [
            "article_count", "sentiment_mean", "bullishness_index", "agreement_index",
            "comment_volume_ratio", "comment_polarization", "net_push_momentum",
        ]
        row_mixed = df_mixed[df_mixed["stock_id"] == "2330"] \
            .sort_values("trade_date").reset_index(drop=True)
        row_single = df_single[df_single["stock_id"] == "2330"] \
            .sort_values("trade_date").reset_index(drop=True)

        self.assertEqual(list(row_mixed["trade_date"]), list(row_single["trade_date"]))
        for col in compare_cols:
            pd.testing.assert_series_equal(
                row_mixed[col].reset_index(drop=True),
                row_single[col].reset_index(drop=True),
                check_names=False,
                obj=f"2330 的 {col}（混合市場 vs 單一市場）",
            )


if __name__ == "__main__":
    unittest.main()
