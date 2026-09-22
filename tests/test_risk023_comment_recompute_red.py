"""
tests/test_risk023_comment_recompute_red.py — RISK-023／DEC-039 紅測（步驟一 Gate A 核准後）

涵蓋 `doc/upgrade/gates/RISK023_GATE_A_PROPOSAL.md` §四紅測清單第 1~8、10、12、13 條。
第 9 條（P6 不變式）另見 `scripts/verify/risk023_p6_invariant_check.py`（唯讀資料庫腳本，非本檔）。
第 11 條（既有 DEC-024 測試）於 `tests/test_comment_features.py` 內處理。

**本檔在實作前（DEC-039 尚未接線）預期全數 RED**——`_aggregate_direct_comment_counts()`
與 `generate_daily_features()` 尚未支援 `df_comments` 參數／逐則重算路徑，
現行程式碼仍是 `RISK-023_GATE_A_PROPOSAL.md` §一診斷的文章層級 `comments_scraped_at` 過濾。

目標介面（DEC-039 §二方案 A 設計）：
- `FeatureAggregator.generate_daily_features(..., df_comments: Optional[pd.DataFrame] = None)`
- `FeatureAggregator._aggregate_direct_comment_counts(df_arts_direct, cutoff_t, df_comments)`
  ——第三參數為新增，`df_arts_direct` 每列以 `market_articles.total_comments IS NOT NULL`
  作為「已擷取」旗標，實際推／噓／總數改由 `df_comments`（`article_comments` 逐則列）
  透過 `comment_timeline.counts_as_of()` 逐 (article, stock_id) 列重算。
"""

import sys
import types
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock

if "psycopg2" not in sys.modules:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock()
    psycopg2_extras = types.ModuleType("psycopg2.extras")
    psycopg2_extras.execute_values = MagicMock()
    psycopg2.extras = psycopg2_extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2_extras

import pandas as pd

from src.transform.feature_aggregator import FeatureAggregator, normalize_cutoff_time

MAPPING = pd.DataFrame([
    {"keyword": "台積電", "stock_id": "2330"},
    {"keyword": "鴻海", "stock_id": "2317"},
])


def _prices(stock_ids=("2330",), trade_dates=None):
    trade_dates = trade_dates or ["2026-08-24", "2026-08-25", "2026-08-26"]
    rows = []
    for sid in stock_ids:
        for i, d in enumerate(trade_dates):
            rows.append({"trade_date": d, "stock_id": sid,
                         "close_price": 100.0 + i, "volume": 1000 + i * 10})
    return pd.DataFrame(rows)


def _arts_direct(rows):
    """已展開、已指派 trade_date 的 (article, stock_id) 列——
    模擬 assign_trading_days_per_stock() 之後、_aggregate_direct_comment_counts()
    收到的輸入形狀。`total_comments` 只作為「已擷取」旗標（DEC-039 Decision 第 4 項），
    不再是計數的來源；`post_time`／`comments_scraped_at` 供 validate_comment_bounds() 用。
    """
    return pd.DataFrame([{
        "article_id": r["article_id"],
        "trade_date": r["trade_date"],
        "stock_id": r["stock_id"],
        "source": r.get("source", "ptt_stock"),
        "total_comments": r.get("total_comments", 0),
        "post_time": r.get("post_time"),
        "comments_scraped_at": r.get("comments_scraped_at"),
    } for r in rows])


def _comments(rows):
    """article_comments 逐則列。rows: dicts with article_id/seq/tag/comment_time。"""
    return pd.DataFrame([{
        "article_id": r["article_id"],
        "comment_seq": r["seq"],
        "comment_tag": r["tag"],
        "comment_time": r["comment_time"],
    } for r in rows])


CUTOFF = normalize_cutoff_time("15:30:00")


class RecomputeRecoversBackfillPeriodArticle(unittest.TestCase):
    """紅測 1：情況 2（回填期）—— 文章擷取完成時刻遠晚於決策點，
    但逐則留言本身的時間戳落在決策點之前。現行文章層級過濾會判 NULL；
    逐則重算後應為非 NULL（DEC-039 Decision 第 2 項：情況 2 的 NULL 處置已取消）。
    """

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_counts_as_of_recovers_backfill_period_article(self):
        arts_direct = _arts_direct([{
            "article_id": 9001, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 1,
            "post_time": datetime(2026, 8, 24, 10, 0),
            # 回填期：擷取完成時刻晚了 90 天，現行機制會判整篇 NULL
            "comments_scraped_at": datetime(2026, 11, 22, 9, 0),
        }])
        comments = _comments([
            {"article_id": 9001, "seq": 1, "tag": "推",
             "comment_time": datetime(2026, 8, 24, 11, 0)},  # 早於決策點 15:30，合法可見
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        self.assertFalse(agg.empty, "已擷取且有逐則留言，聚合結果不應為空")
        row = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertFalse(pd.isna(row["total_sum"]),
                          "回填期文章的決策點前留言應被逐則重算收錄，不得因文章層級擷取時刻晚而整篇 NULL")
        self.assertEqual(row["total_sum"], 1)


class RecomputeRecoversNearMissScheduledArticle(unittest.TestCase):
    """紅測 2：情況 3（穩定排程近界延遲）—— 文章擷取完成時刻只晚決策點幾分鐘
    （模擬每日 15:35 排程 vs 15:30 決策點），但留言本身時間戳仍早於決策點。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_counts_as_of_recovers_near_miss_scheduled_article(self):
        arts_direct = _arts_direct([{
            "article_id": 9002, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 1,
            "post_time": datetime(2026, 8, 24, 10, 0),
            # 近界延遲：只晚 5 分鐘（15:35 排程 vs 15:30 決策點）
            "comments_scraped_at": datetime(2026, 8, 24, 15, 35),
        }])
        comments = _comments([
            {"article_id": 9002, "seq": 1, "tag": "噓",
             "comment_time": datetime(2026, 8, 24, 12, 0)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertEqual(row["total_sum"], 1,
                          "近界延遲不應影響決策點前留言的收錄——現行文章層級過濾會把整篇判 NULL")


class RecomputeYearRolloverBoundary(unittest.TestCase):
    """紅測 3：跨年邊界——決策點落在新年年初，留言時間戳落在去年年底，
    `counts_as_of` 的 `<=` 比較必須正確跨年，不得因型別或字串比較出錯。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_counts_as_of_year_rollover_boundary(self):
        arts_direct = _arts_direct([{
            "article_id": 9003, "trade_date": date(2026, 1, 2), "stock_id": "2330",
            "total_comments": 2,
            "post_time": datetime(2025, 12, 31, 20, 0),
            "comments_scraped_at": datetime(2026, 1, 2, 15, 30),
        }])
        comments = _comments([
            {"article_id": 9003, "seq": 1, "tag": "推",
             "comment_time": datetime(2025, 12, 31, 23, 59)},  # 決策點前，跨年
            {"article_id": 9003, "seq": 2, "tag": "推",
             "comment_time": datetime(2026, 1, 2, 16, 0)},  # 決策點後，應排除
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 1, 2)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertEqual(row["total_sum"], 1,
                          "跨年決策點前只有 1 則合法留言，跨年比較不得算錯")


class UnfetchedArticleStaysNull(unittest.TestCase):
    """紅測 4：`total_comments IS NULL`（未擷取）→ 維持 NULL，不得變 0。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_unfetched_article_stays_null(self):
        arts_direct = _arts_direct([{
            "article_id": 9004, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": None,  # 未擷取
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": None,
        }])
        comments = _comments([])  # 無逐則留言（未擷取，本來就不會有）
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        self.assertTrue(agg.empty or pd.isna(
            agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]["total_sum"]
        ), "未擷取文章必須維持 NULL，不得因為 df_comments 沒有列而被當成觀測到的 0")


class FetchedArticleWithNoCommentRowsIsObservedZero(unittest.TestCase):
    """紅測 5：`total_comments` 非 NULL（已擷取）但 `article_comments` 無列
    ——真實案例 `article_id ∈ {1772, 1872, 2117}`——應為觀測到的 0，非 NULL。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_fetched_article_with_no_comment_rows_is_observed_zero(self):
        arts_direct = _arts_direct([{
            "article_id": 1772, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 0,  # 已擷取，觀測到零留言
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 12, 0),
        }])
        comments = _comments([])  # article_comments 確實 0 列
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        self.assertFalse(agg.empty, "已擷取的文章不得因為 df_comments 空表而被當成未擷取")
        row = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertFalse(pd.isna(row["total_sum"]), "已擷取、觀測到零留言，必須是 0，不是 NULL")
        self.assertEqual(row["total_sum"], 0)


class FetchedArticleAllAfterCutoffIsObservedZero(unittest.TestCase):
    """紅測 6：已擷取、有逐則留言，但全部落在決策點之後 → 觀測到的 0。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_fetched_article_with_comments_all_after_cutoff_is_observed_zero(self):
        arts_direct = _arts_direct([{
            "article_id": 9006, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 3,
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 16, 0),
        }])
        comments = _comments([
            {"article_id": 9006, "seq": i + 1, "tag": "推",
             "comment_time": datetime(2026, 8, 24, 15, 40)}  # 全部晚於 15:30 決策點
            for i in range(3)
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertFalse(pd.isna(row["total_sum"]), "決策點前全部排除後仍是觀測到的 0，不是 NULL")
        self.assertEqual(row["total_sum"], 0)


class CommentTimeOutOfBoundsExcludedFromCount(unittest.TestCase):
    """紅測 7：留言時間戳落在 `[post_time, comments_scraped_at]` 之外
    ——真實案例 `article_id=1495` 第 26~38 則，`above_scraped_at`——
    `validate_comment_bounds()` 判為落界，不計入 `counts_as_of` 任何一格。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_comment_time_out_of_bounds_excluded_from_count(self):
        """⚠ 決策點刻意設在 `comments_scraped_at` 之後很久（09-10，而擷取凍結
        於 09-05），使落界留言（seq 26，晚於 `comments_scraped_at` 但仍早於
        決策點）**只會被 `validate_comment_bounds` 擋下，不會被 `counts_as_of`
        的決策點比較連帶擋下**——若決策點與擷取時刻同一天，這則留言會被
        兩種機制同時排除，測試就分不出是哪一個在起作用（mutation 2 驗證時
        發現過這個假通過，已訂正）。"""
        arts_direct = _arts_direct([{
            # total_comments 對齊本測試實際提供的 2 則逐則列（P6 一致性守衛要求，
            # 見 P6ConsistencyGuardMarksSuspectAndNull）——不是真實案例 1495 的
            # 25，此處僅借用真實案例的 article_id 與落界形狀。
            "article_id": 1495, "trade_date": date(2026, 9, 10), "stock_id": "2330",
            "total_comments": 2,
            "post_time": datetime(2026, 9, 5, 8, 0),
            "comments_scraped_at": datetime(2026, 9, 5, 13, 53, 32),  # 首次擷取凍結時刻
        }])
        comments = _comments([
            {"article_id": 1495, "seq": 1, "tag": "推",
             "comment_time": datetime(2026, 9, 5, 9, 0)},  # 合法：早於 scraped_at
            {"article_id": 1495, "seq": 26, "tag": "推",
             # 落界：晚於 comments_scraped_at（09-05 13:53），但早於決策點
             # （09-10 15:30）——只有 validate_comment_bounds 擋得住這則
             "comment_time": datetime(2026, 9, 5, 15, 39)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 9, 10)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertEqual(row["total_sum"], 1,
                          "落界留言（晚於 comments_scraped_at）必須被 validate_comment_bounds 排除，不計入總數")


class SameArticleDifferentStockUsesOwnDecisionPoint(unittest.TestCase):
    """紅測 8：同一篇文章對到兩檔不同交易日曆的股票，
    兩個 (article, stock_id) 列應各自以自己的 decision_point 呼叫 counts_as_of，結果可不同。
    """

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_same_article_different_stock_uses_own_decision_point(self):
        # 2330 的交易日曆含 08-24；2317 的交易日曆該日為假日、下一交易日是 08-25
        arts_direct = _arts_direct([
            # total_comments=1 對齊本測試實際提供的單一則逐則列（P6 一致性守衛要求）
            {"article_id": 9008, "trade_date": date(2026, 8, 24), "stock_id": "2330",
             "total_comments": 1, "post_time": datetime(2026, 8, 24, 10, 0),
             "comments_scraped_at": datetime(2026, 8, 24, 16, 0)},
            {"article_id": 9008, "trade_date": date(2026, 8, 25), "stock_id": "2317",
             "total_comments": 1, "post_time": datetime(2026, 8, 24, 10, 0),
             "comments_scraped_at": datetime(2026, 8, 24, 16, 0)},
        ])
        comments = _comments([
            # 落在 2330 決策點（08-24 15:30）之後，但落在 2317 決策點（08-25 15:30）之前
            {"article_id": 9008, "seq": 1, "tag": "推", "comment_time": datetime(2026, 8, 24, 16, 0)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row_2330 = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        row_2317 = agg[(agg["trade_date"] == date(2026, 8, 25)) & (agg["stock_id"] == "2317")].iloc[0]
        self.assertEqual(row_2330["total_sum"], 0,
                          "2330 的決策點（08-24 15:30）早於留言時間，該留言對 2330 不可見")
        self.assertEqual(row_2317["total_sum"], 1,
                          "2317 的決策點（08-25 15:30）晚於留言時間，同一則留言對 2317 合法可見——"
                          "兩檔股票不應共用同一個 decision_point")


class FetchAllForFeaturesReadsArticleComments(unittest.TestCase):
    """紅測 10：`fetch_all_for_features()` 新增 `article_comments` 讀取，
    且與現有文章 SELECT 使用相同的範圍過濾，不整表載入。"""

    def test_fetch_all_for_features_reads_article_comments_with_shared_filter(self):
        from src.loaders.db_writer import DBWriter
        writer = DBWriter.__new__(DBWriter)
        writer.fetch_data = MagicMock(return_value=pd.DataFrame())
        writer.fetch_all_for_features()

        queries = [c[0][0] for c in writer.fetch_data.call_args_list]
        comment_queries = [q for q in queries if "article_comments" in q]
        self.assertTrue(comment_queries, "fetch_all_for_features() 尚未新增 article_comments 的 SELECT")
        comment_query = comment_queries[0]
        self.assertNotIn("SELECT *", comment_query, "不得整表載入 article_comments")
        self.assertTrue(
            "sentiment_score" in comment_query or "JOIN" in comment_query.upper(),
            "article_comments 的 SELECT 必須與文章 SELECT 共用範圍過濾（JOIN 或子查詢限縮），不得整表載入")


class TimeResetArticleMarkedSuspectAndNull(unittest.TestCase):
    """紅測 12：留言時間依 comment_seq 出現回退 → 標記 suspect，
    涉及 (article, stock_id) 列留言三欄一律 NULL（DEC-039 Decision 第 9 項，RISK-029）。

    known-FAIL 案例：拿掉 suspect 守衛時，`counts_as_of` 會把回退後的重複區塊也算入，
    對本案例（4 則推文，其中 2 則因回退而重複）會算出 total_sum=4 而非 NULL，
    虛高地產出一個看似合法的非 NULL 計數。
    """

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_time_reset_article_marked_suspect_and_null(self):
        arts_direct = _arts_direct([{
            "article_id": 1815, "trade_date": date(2026, 7, 3), "stock_id": "2330",
            "total_comments": 4,
            "post_time": datetime(2026, 7, 3, 12, 7, 49),
            "comments_scraped_at": datetime(2026, 9, 7, 14, 37, 25),
        }])
        # 模擬真實案例的回退形狀：seq 1-2 正常遞增，seq 3-4 回退到更早的時間
        comments = _comments([
            {"article_id": 1815, "seq": 1, "tag": "噓", "comment_time": datetime(2026, 7, 3, 12, 9)},
            {"article_id": 1815, "seq": 2, "tag": "推", "comment_time": datetime(2026, 7, 3, 12, 19)},
            {"article_id": 1815, "seq": 3, "tag": "推", "comment_time": datetime(2026, 7, 3, 12, 9)},  # 回退
            {"article_id": 1815, "seq": 4, "tag": "推", "comment_time": datetime(2026, 7, 3, 12, 19)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 7, 3)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertTrue(pd.isna(row["total_sum"]),
                         "comment_seq 時間回退的文章必須標記 suspect，留言三欄給 NULL，"
                         "不得把回退後的重複區塊也算入計數")


class MonotonicArticleNotMarkedSuspect(unittest.TestCase):
    """紅測 13：對照案例——留言時間依 comment_seq 正常遞增，不應被誤標 suspect。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_monotonic_article_not_marked_suspect(self):
        arts_direct = _arts_direct([{
            "article_id": 9013, "trade_date": date(2026, 7, 3), "stock_id": "2330",
            "total_comments": 2,
            "post_time": datetime(2026, 7, 3, 12, 0),
            "comments_scraped_at": datetime(2026, 7, 3, 16, 0),
        }])
        comments = _comments([
            {"article_id": 9013, "seq": 1, "tag": "推", "comment_time": datetime(2026, 7, 3, 12, 9)},
            {"article_id": 9013, "seq": 2, "tag": "推", "comment_time": datetime(2026, 7, 3, 12, 19)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 7, 3)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertFalse(pd.isna(row["total_sum"]),
                          "時間正常遞增的文章不應被誤標 suspect，不應被平白判成 NULL")
        self.assertEqual(row["total_sum"], 2)


class MissingDfCommentsRaisesNotSilentlyFallsBack(unittest.TestCase):
    """紅測 14（PO 2026-09-14 補充要求）：`generate_daily_features()` 收到
    直接映射的文章列，但呼叫端未提供 `df_comments`（`None`）時，必須**拒絕**
    （拋例外），不得靜默退回已被 RISK-023 診斷判定為結構性缺陷的舊文章層級
    `comments_scraped_at` 過濾。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_missing_df_comments_raises_not_silently_falls_back(self):
        arts = pd.DataFrame([{
            "article_id": 9014, "source": "ptt_stock", "fetch_keyword": "台積電",
            "post_time": "2026-08-24 10:00:00", "sentiment_score": 0.6,
            "push_count": 1, "boo_count": 0, "neutral_count": 0, "total_comments": 1,
            "comments_scraped_at": datetime(2026, 8, 24, 14, 0),
        }])
        with self.assertRaises(Exception):
            self.aggregator.generate_daily_features(_prices(), arts, MAPPING)  # df_comments 未傳

    def test_aggregate_function_itself_raises_when_df_comments_is_none(self):
        """PO 2026-09-14 複核指出：拿掉 `_aggregate_direct_comment_counts()` 內部
        自己的 `raise` 時，全套 31 條既有測試沒有一條 FAIL——因為所有既有測試
        都經由 `generate_daily_features()` 呼叫，而後者自己的前置檢查會**先**
        擋下 `None`，`_aggregate_direct_comment_counts()` 內部那道 `raise` 從未
        被任何測試真正觸發過，是一個結構上無法失敗的檢查（`CLAUDE.md` §9A.1）。
        本測試直接呼叫該函式本身，繞過 `generate_daily_features()` 的前置檢查，
        真正觸及內部這道 `raise`。"""
        arts_direct = _arts_direct([{
            "article_id": 9015, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 1,
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 14, 0),
        }])
        with self.assertRaises(ValueError):
            self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, None)


class P6ConsistencyGuardMarksSuspectAndNull(unittest.TestCase):
    """紅測（PO 2026-09-14 複核要求）：`total_comments`（`market_articles` 凍結
    快照）與 `df_comments`（呼叫端傳入的逐則資料）是兩個獨立來源。若逐則列數
    **少於** `total_comments`，代表 P6 不變式被違反，或呼叫端傳了不完整的
    `df_comments`——這種情況下逐則重算會算出一個偏低的「觀測值」甚至 0，
    那不是真的觀測到的 0，是資料不一致，必須標 `suspect` 給 NULL，而不是
    照樣算出一個看似合法的偏低計數。"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_fewer_comment_rows_than_total_comments_marked_suspect(self):
        arts_direct = _arts_direct([{
            "article_id": 9016, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 5,  # market_articles 宣稱有 5 則
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 14, 0),
        }])
        comments = _comments([  # 但只給了 3 則——P6 不一致
            {"article_id": 9016, "seq": 1, "tag": "推", "comment_time": datetime(2026, 8, 24, 10, 5)},
            {"article_id": 9016, "seq": 2, "tag": "推", "comment_time": datetime(2026, 8, 24, 10, 6)},
            {"article_id": 9016, "seq": 3, "tag": "推", "comment_time": datetime(2026, 8, 24, 10, 7)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertTrue(pd.isna(row["total_sum"]),
                         "逐則列數（3）少於 total_comments（5）——P6 不一致，必須標 suspect 給 NULL，"
                         "不得算出一個偏低的偽觀測值")

    def test_comment_rows_matching_total_comments_not_marked_suspect(self):
        """對照案例：逐則列數與 `total_comments` 一致（相等），不應被誤標 suspect。"""
        arts_direct = _arts_direct([{
            "article_id": 9017, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "total_comments": 5,
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 14, 0),
        }])
        comments = _comments([
            {"article_id": 9017, "seq": i + 1, "tag": "推",
             "comment_time": datetime(2026, 8, 24, 10, 5 + i)} for i in range(5)
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(arts_direct, CUTOFF, comments)
        row = agg[(agg["trade_date"] == date(2026, 8, 24)) & (agg["stock_id"] == "2330")].iloc[0]
        self.assertEqual(row["total_sum"], 5,
                          "逐則列數與 total_comments 一致，不應被誤標 suspect")


if __name__ == "__main__":
    unittest.main()
