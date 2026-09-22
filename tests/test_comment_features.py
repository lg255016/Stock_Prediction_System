"""
tests/test_comment_features.py — UG-G2-SB4 留言接線與衍生特徵專項測試

涵蓋：FEATURE_REGISTRY.md §5.1~§5.4 四條公式、§5A.5 的 NULL 語意、
DEC-024 時點有效性判準（`comments_scraped_at` 過濾 + write-once）、
DEC-025 只採用直接個股文章（題材溢出文章的留言不計入成分股）。
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

from src.loaders.db_writer import DBWriter
from src.transform.feature_aggregator import (
    FeatureAggregator,
    compute_push_ratio,
    normalize_cutoff_time,
)

TRADE_DATES = ["2026-08-24", "2026-08-25", "2026-08-26"]


def _prices(stock_id="2330"):
    return pd.DataFrame({
        "trade_date": TRADE_DATES,
        "stock_id": [stock_id] * 3,
        "close_price": [100.0, 101.0, 102.0],
        "volume": [1000, 1100, 1200],
    })


def _articles(rows):
    """rows: list of dicts with post_time/push/boo/total/scraped_at"""
    return pd.DataFrame([{
        "article_id": i + 1,
        # UG-G2-SB5 決策點 5：聚合層改以 source 判定該來源是否提供留言方向，
        # 因此 fixture 必須帶 source。預設 ptt_stock 使既有測試行為完全不變。
        "source": r.get("source", "ptt_stock"),
        "fetch_keyword": r.get("keyword", "台積電"),
        "post_time": r["post_time"],
        "sentiment_score": 0.6,
        "push_count": r.get("push"),
        "boo_count": r.get("boo"),
        "neutral_count": r.get("neutral", 0),
        "total_comments": r.get("total"),
        "comments_scraped_at": r.get("scraped_at"),
    } for i, r in enumerate(rows)])


MAPPING = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])


# 2026-09-14，DEC-039：留言特徵改依逐則時間戳重算，`generate_daily_features()`
# 現在要求 df_comments（不得省略）。以下輔助函式從既有的「彙總式」fixture
# （_articles() 的 push/boo/neutral/total）反推等價的逐則留言列，讓既有測試
# 在新引擎下維持相同語意，不必逐一改寫每個測試的斷言。
#
# 每篇文章的留言全部落在 post_time 之後的安全窗口內（不觸及
# comments_scraped_at 上界，也不觸及決策點——是否早於決策點由各測試自己的
# post_time／scraped_at／trade_date 設計決定，與本函式無關，這只是把
# 「彙總計數」翻譯成「一組逐則留言」，不改變任何時點判準）。
def _comments_from_articles(arts):
    rows = []
    for _, art in arts.iterrows():
        total = art.get("total_comments")
        if pd.isna(total):
            continue
        total = int(total)
        push = int(art["push_count"]) if pd.notna(art.get("push_count")) else 0
        boo = int(art["boo_count"]) if pd.notna(art.get("boo_count")) else 0
        neutral = max(total - push - boo, 0)
        tags = ["推"] * push + ["噓"] * boo + ["→"] * neutral
        post_time = pd.to_datetime(art["post_time"])
        for i, tag in enumerate(tags):
            rows.append({
                "article_id": art["article_id"],
                "comment_seq": i + 1,
                "comment_tag": tag,
                "comment_time": post_time + pd.Timedelta(minutes=i + 1),
            })
    return pd.DataFrame(rows, columns=["article_id", "comment_seq", "comment_tag", "comment_time"])


class PushRatioFormulaTests(unittest.TestCase):
    """FEATURE_REGISTRY.md §5.1"""

    def test_push_ratio_laplace_smoothing_prevents_division_by_zero(self):
        self.assertEqual(compute_push_ratio(pd.Series([0]), pd.Series([0])).iloc[0], 0.0)

    def test_push_ratio_sign_and_range(self):
        # 全推：(10-0)/(10+0+1) = 0.909...，落在 (-1, 1) 內
        bullish = compute_push_ratio(pd.Series([10]), pd.Series([0])).iloc[0]
        bearish = compute_push_ratio(pd.Series([0]), pd.Series([10])).iloc[0]
        self.assertGreater(bullish, 0)
        self.assertLess(bearish, 0)
        self.assertLess(abs(bullish), 1.0)
        self.assertLess(abs(bearish), 1.0)


class CommentFeatureNullSemanticsTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_null_when_no_comments（§5A.5）"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_null_when_no_comments(self):
        """完全沒有留言資料時，三個特徵一律 NULL——不得為 0，
        更不得讓 comment_polarization 變成 1.0（偽造的「最大分歧」強訊號）。"""
        arts = _articles([{"post_time": "2026-08-24 10:00:00"}])  # 留言欄全 None
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=_comments_from_articles(arts))

        for col in ["comment_volume_ratio", "comment_polarization", "net_push_momentum"]:
            self.assertTrue(feats[col].isna().all(), f"{col} 應全為 NULL，實際：{feats[col].tolist()}")

    def test_zero_comments_is_not_null(self):
        """已解析且確實零則留言時，polarization 可正當計算（push_ratio=0 → 1-0²=1.0）。
        這與上一個測試互補：兩種狀態都要能正確表達，否則 NULL 語意就沒有意義。"""
        arts = _articles([
            {"post_time": "2026-08-24 10:00:00", "push": 0, "boo": 0, "total": 0,
             "scraped_at": datetime(2026, 8, 24, 14, 0)},
        ])
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=_comments_from_articles(arts))
        row = feats[feats["trade_date"] == date(2026, 8, 24)].iloc[0]
        self.assertEqual(row["comment_polarization"], 1.0)


class CommentVolumeRatioTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_comment_volume_ratio_uses_rolling_baseline"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_comment_volume_ratio_uses_rolling_baseline_of_prior_days_only(self):
        """§5.2：分母是 t-5..t-1 的均值，**不含當日**——若誤含當日即為前視偏誤。
        Day1 total=10（暖機期，無前日基準 → NULL）；
        Day2 total=30 → 30/(10+1) = 2.727...；
        Day3 total=50 → 50/(mean(10,30)+1) = 50/21 = 2.380..."""
        arts = _articles([
            {"post_time": "2026-08-24 10:00:00", "push": 5, "boo": 1, "total": 10,
             "scraped_at": datetime(2026, 8, 24, 14, 0)},
            {"post_time": "2026-08-25 10:00:00", "push": 20, "boo": 2, "total": 30,
             "scraped_at": datetime(2026, 8, 25, 14, 0)},
            {"post_time": "2026-08-26 10:00:00", "push": 30, "boo": 5, "total": 50,
             "scraped_at": datetime(2026, 8, 26, 14, 0)},
        ])
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=_comments_from_articles(arts)
        ).sort_values("trade_date")

        vals = feats["comment_volume_ratio"].tolist()
        self.assertTrue(pd.isna(vals[0]), "首日無前日基準，應為 NULL（暖機期不足）")
        self.assertAlmostEqual(vals[1], 30 / (10 + 1), places=6)
        self.assertAlmostEqual(vals[2], 50 / (((10 + 30) / 2) + 1), places=6)


class NetPushMomentumTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_momentum_is_delta_not_ratio"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_momentum_is_delta_not_ratio(self):
        """§5.4：net_push_momentum = push_ratio_t - push_ratio_{t-1}（差，不是比）。
        Day1 push_ratio = (10-0)/11；Day2 = (0-10)/11；
        Day2 momentum 應為兩者相減（負值），若誤寫成相除會是正值。"""
        arts = _articles([
            {"post_time": "2026-08-24 10:00:00", "push": 10, "boo": 0, "total": 10,
             "scraped_at": datetime(2026, 8, 24, 14, 0)},
            {"post_time": "2026-08-25 10:00:00", "push": 0, "boo": 10, "total": 10,
             "scraped_at": datetime(2026, 8, 25, 14, 0)},
        ])
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=_comments_from_articles(arts)
        ).sort_values("trade_date")

        day1_ratio, day2_ratio = 10 / 11, -10 / 11
        vals = feats["net_push_momentum"].tolist()
        self.assertTrue(pd.isna(vals[0]), "首日無前日 push_ratio，應為 NULL")
        self.assertAlmostEqual(vals[1], day2_ratio - day1_ratio, places=6)
        self.assertLess(vals[1], 0, "由全推轉為全噓，動量必須為負——若為正代表寫成了比值")


class PolarizationBoundaryTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_polarization_boundary"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_polarization_boundary(self):
        """§5.3：1 - push_ratio²，值域 [0.0, 1.0]。
        多空均衡（push≈boo）→ 接近 1.0（最大分歧）；一面倒 → 接近 0.0（高度共識）。"""
        balanced = _articles([{"post_time": "2026-08-24 10:00:00", "push": 50, "boo": 50,
                               "total": 100, "scraped_at": datetime(2026, 8, 24, 14, 0)}])
        onesided = _articles([{"post_time": "2026-08-24 10:00:00", "push": 100, "boo": 0,
                               "total": 100, "scraped_at": datetime(2026, 8, 24, 14, 0)}])

        p_balanced = self.aggregator.generate_daily_features(
            _prices(), balanced, MAPPING, df_comments=_comments_from_articles(balanced))
        p_onesided = self.aggregator.generate_daily_features(
            _prices(), onesided, MAPPING, df_comments=_comments_from_articles(onesided))

        v_balanced = p_balanced[p_balanced["trade_date"] == date(2026, 8, 24)].iloc[0]["comment_polarization"]
        v_onesided = p_onesided[p_onesided["trade_date"] == date(2026, 8, 24)].iloc[0]["comment_polarization"]

        self.assertGreater(v_balanced, 0.99)
        self.assertLess(v_onesided, 0.05)
        for v in (v_balanced, v_onesided):
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


class CommentTimingValidityTests(unittest.TestCase):
    """DEC-024（原判準）→ DEC-039（2026-09-14 修訂，取代文章層級過濾）時點有效性判準。

    【改寫說明】這兩個測試原本斷言「文章擷取完成時刻晚於決策點 → 整篇排除」。
    RISK-023 診斷發現該判準的前提（穩定運作下第一次擷取天然早於決策點）在本
    專案實際排程常數下結構性不成立，DEC-039 因此改為逐則時間戳重算，取代
    文章層級 `comments_scraped_at` 過濾——原 `test_comment_count_scraped_after_
    decision_point_is_excluded` 的斷言（整篇排除為 NULL）在新判準下**不再
    成立**，若原樣保留會與 DEC-039 的設計矛盾，故非改寫不可，不是可選項
    （測試名稱也一併更名，見下方兩個方法）。

    新舊斷言差異：舊測試驗證「文章擷取時刻晚於決策點 → 排除」；新測試驗證
    「即使文章擷取時刻晚於決策點，只要個別留言的時間戳本身早於決策點，
    仍應收錄」（DEC-039 §一情況 2／3 的核心修法）；另一測試驗證「留言時間戳
    晚於決策點 → 排除」，取代舊測試「擷取時刻早於決策點 → 收錄」，因為新架構
    下唯一有意義的排除判準是逐則時間戳本身，不再是文章擷取完成時刻。
    """

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_late_scrape_recovered_when_comment_itself_precedes_decision_point(self):
        """【新】文章擷取完成時刻晚兩天，但留言本身的時間戳早於決策點
        （合法可見）——DEC-039 應予收錄，不再因文章擷取時刻晚而整篇排除。

        對照舊測試的情境：舊版斷言這種情況必須排除為 NULL；
        新版斷言相反——這正是 DEC-039 修訂 DEC-024 的核心（見 Gate A 提案 §一）。
        """
        arts = _articles([
            {"post_time": "2026-08-24 10:00:00", "push": 100, "boo": 5, "total": 200,
             "scraped_at": datetime(2026, 8, 26, 9, 0)},  # 文章擷取完成時刻晚兩天
        ])
        # 留言本身的時間戳落在發文當天、決策點（08-24 15:30）之前——合法可見
        comments = _comments_from_articles(arts)
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=comments)
        row = feats[feats["trade_date"] == date(2026, 8, 24)].iloc[0]

        self.assertFalse(pd.isna(row["comment_polarization"]),
                         "留言本身時間戳早於決策點，即使文章擷取完成時刻晚，"
                         "DEC-039 下仍應收錄，不得因文章層級擷取時刻晚而整篇排除")

    def test_comment_time_after_decision_point_excluded_from_count(self):
        """【新】留言本身的時間戳晚於決策點 → 該則排除，不計入 counts_as_of。

        取代舊測試「擷取時刻早於決策點 → 收錄」：新架構下判準的對象是逐則
        時間戳，不是文章擷取完成時刻，所以互補案例也要換成逐則層級的情境。
        """
        arts = _articles([
            {"post_time": "2026-08-24 10:00:00", "push": 0, "boo": 0, "total": 0,
             "scraped_at": datetime(2026, 8, 24, 20, 0)},
        ])
        # 手動指定一則晚於決策點（08-24 15:30）的留言
        comments = pd.DataFrame([{
            "article_id": 1, "comment_seq": 1, "comment_tag": "推",
            "comment_time": datetime(2026, 8, 24, 16, 0),
        }])
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=comments)
        row = feats[feats["trade_date"] == date(2026, 8, 24)].iloc[0]

        self.assertEqual(row["comment_polarization"], 1.0,
                         "唯一一則留言晚於決策點被排除，決策點前留言數為 0，"
                         "push_ratio=0 → polarization=1.0（觀測到的 0，非 NULL）")


class ThemeSpilloverExcludedFromCommentsTests(unittest.TestCase):
    """DEC-025 決策點 2 選項 C：題材溢出文章的留言不計入成分股"""

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_theme_article_comments_do_not_leak_into_constituent_stocks(self):
        """一篇矽光子題材文章有 500 則留言，2330 只是其成分股之一、無直接文章——
        該檔的留言特徵必須為 NULL，不得繼承題材文章的留言量。

        若計入，多檔成分股的 comment_polarization 與 net_push_momentum 會幾乎完全相同
        （兩者都是 push_ratio 的函數），模型會看到看似獨立、實則同源的樣本，
        製造假的相關性——比 NULL 有害。"""
        arts = _articles([
            {"post_time": "2026-08-24 10:00:00", "keyword": "矽光子", "push": 400, "boo": 20,
             "total": 500, "scraped_at": datetime(2026, 8, 24, 14, 0)},
        ])
        theme_mapping = pd.DataFrame([{"theme_keyword": "矽光子", "stock_id": "2330",
                                       "relevance_weight": 0.8}])

        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_theme_mapping=theme_mapping,
            df_comments=_comments_from_articles(arts),
        )
        row = feats[feats["trade_date"] == date(2026, 8, 24)].iloc[0]

        # 情緒仍應受題材溢出影響（DEC-009 未變）
        self.assertGreater(row["article_count"], 0, "題材溢出對情緒欄位的既有行為不應改變")
        # 但留言特徵不得繼承
        for col in ["comment_volume_ratio", "comment_polarization", "net_push_momentum"]:
            self.assertTrue(pd.isna(row[col]), f"{col} 不得繼承題材文章的留言量（DEC-025）")


class CommentCountWriteOnceTests(unittest.TestCase):
    """DEC-024 write-once：已有計數者不覆寫（消滅「舊文章重複爬取被覆寫」的洩漏）"""

    def test_update_comment_counts_is_write_once(self):
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()
        writer.update_comment_counts([(1, 2, 3, 6, datetime(2026, 8, 26, 9, 0), "https://x/a.html")])

        query, records = writer._execute_batch.call_args[0]
        self.assertIn("AND market_articles.total_comments IS NULL", query,
                      "write-once 條件缺失——舊文章重複爬取時會用今天的留言數覆寫過去的交易日")
        self.assertIn("comments_scraped_at", query)
        self.assertEqual(len(records[0]), 6)

    def test_update_comment_counts_noop_on_empty(self):
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()
        writer.update_comment_counts([])
        writer._execute_batch.assert_not_called()


class FetchAllForFeaturesTests(unittest.TestCase):
    """§1.2 讀取端缺口迴歸：SELECT 必須包含四個留言計數欄與擷取時點"""

    def test_fetch_all_for_features_includes_comment_columns(self):
        writer = DBWriter.__new__(DBWriter)
        writer.fetch_data = MagicMock(return_value=pd.DataFrame())
        writer.fetch_all_for_features()

        article_query = writer.fetch_data.call_args_list[1][0][0]
        for col in ["push_count", "boo_count", "neutral_count",
                    "total_comments", "comments_scraped_at"]:
            self.assertIn(col, article_query,
                          f"{col} 不在 SELECT 清單中——接線完成後特徵層仍看不到留言資料")


if __name__ == "__main__":
    unittest.main()


class SourceCapabilityTests(unittest.TestCase):
    """UG-G2-SB5 決策點 5：來源能力宣告（FEATURE_REGISTRY.md §5.7、DEC-028）。

    修的是一個與 Dcard 是否可用無關的既有缺陷：聚合層有**兩道**把 NULL 壓成 0
    的關卡，使「這個來源沒有推噓的概念」被算成「推噓各 0 則」，
    產出 comment_polarization = 1.0（最大分歧）這種恆定的偽造強訊號。
    """

    def setUp(self):
        self.aggregator = FeatureAggregator()

    def test_no_direction_source_yields_null_not_fabricated_signal(self):
        """第一道關卡（fillna(0)）：無方向來源的方向類特徵必須是 NULL。

        Known-FAIL：現行程式碼 `fillna(0)` 使 push_ratio = (0-0)/(0+0+1) = 0，
        於是 comment_polarization = 1 - 0² = 1.0——「散戶意見最大分歧」，
        而該來源根本沒有推噓的概念。net_push_momentum 同樣被偽造成 0.0。
        """
        arts = _articles([
            {"source": "dcard_stock", "post_time": "2026-08-24 10:00:00",
             "push": None, "boo": None, "total": 50,
             "scraped_at": datetime(2026, 8, 24, 14, 0)},
            {"source": "dcard_stock", "post_time": "2026-08-25 10:00:00",
             "push": None, "boo": None, "total": 60,
             "scraped_at": datetime(2026, 8, 25, 14, 0)},
        ])
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=_comments_from_articles(arts))
        row = feats[feats["trade_date"] == date(2026, 8, 25)].iloc[0]

        self.assertTrue(pd.isna(row["comment_polarization"]),
                        "無方向來源不得產出 comment_polarization，"
                        "補 0 會造出 1.0 這個偽造的最大分歧訊號")
        self.assertTrue(pd.isna(row["net_push_momentum"]),
                        "無方向來源不得產出 net_push_momentum，"
                        "補 0 會造出「方向毫無變化」的偽造訊號")

    def test_suspect_group_total_sum_survives_aggregation_as_null(self):
        """第二道關卡（groupby.agg('sum')）：全 NaN 群組聚合後必須仍是 NaN。

        【2026-09-14 隨 DEC-039 改寫】舊版用人工構造的 `push_count=None`
        （配上正常 `total_comments`）直接測試 `push_sum` 的 `min_count=1`。
        新架構下 `push_count`／`boo_count`／`total_comments` 都是逐則重算的
        衍生值，不再有「push_count 獨立為 None、total_comments 正常」這種
        輸入形狀——但 `suspect` 守衛（RISK-029）讓 `total_comments` 也可能
        整組為 NaN，這是舊架構沒有的新風險：`total_sum` 原本刻意不加
        `min_count`（因為過濾後必然有值），現在必須補上，否則 suspect 篇的
        NULL 會在 `groupby.sum()` 被悄悄變回 0.0。

        Known-FAIL：拿掉 `total_sum` 聚合的 `min_count=1`，此測試會 FAIL
        （`total_sum` 變成 `0.0` 而非 `NaN`）。
        """
        df = pd.DataFrame([{
            "article_id": 1, "trade_date": date(2026, 8, 24), "stock_id": "2330",
            "source": "ptt_stock", "total_comments": 2,
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 14, 0),
        }])
        # comment_seq 2 的時間早於 comment_seq 1——觸發 suspect 守衛
        comments = pd.DataFrame([
            {"article_id": 1, "comment_seq": 1, "comment_tag": "推",
             "comment_time": datetime(2026, 8, 24, 10, 5)},
            {"article_id": 1, "comment_seq": 2, "comment_tag": "推",
             "comment_time": datetime(2026, 8, 24, 10, 1)},
        ])
        agg = self.aggregator._aggregate_direct_comment_counts(
            df, normalize_cutoff_time("15:30:00"), comments)

        self.assertFalse(agg.empty, "suspect 仍是已擷取文章，聚合結果不應為空")
        self.assertTrue(pd.isna(agg.iloc[0]["push_sum"]),
                        "suspect 群組的 push_sum 必須是 NaN")
        self.assertTrue(pd.isna(agg.iloc[0]["total_sum"]),
                        "suspect 群組的 total_sum 必須是 NaN；"
                        "sum() 預設回 0.0，需 min_count=1")

    def test_zero_push_ptt_article_is_not_null(self):
        """反向守衛：真實零推文的 PTT 文章（整數 0）必須**有值**，不得變成 NULL。

        本次修法同時動兩處，最容易的失敗方式就是把「真正零推文」
        一起誤判成「無方向」——而那個退化不會有任何錯誤訊號，
        只會讓一批 PTT 特徵安靜地變成 NULL。
        """
        arts = _articles([
            {"source": "ptt_stock", "post_time": "2026-08-24 10:00:00",
             "push": 0, "boo": 0, "total": 5,
             "scraped_at": datetime(2026, 8, 24, 14, 0)},
        ])
        feats = self.aggregator.generate_daily_features(
            _prices(), arts, MAPPING, df_comments=_comments_from_articles(arts))
        row = feats[feats["trade_date"] == date(2026, 8, 24)].iloc[0]

        self.assertFalse(pd.isna(row["comment_polarization"]),
                         "0 是「已解析、確實零推文」，與「無方向概念」不同，"
                         "必須正當計算（FEATURE_REGISTRY.md:384-394）")

    def test_volume_ratio_still_uses_all_sources(self):
        """數量可以跨來源相加——方向的拆分不得波及數量類特徵。

        混合來源日：PTT 文章 20 則（有方向：10 推 2 噓 8 中性）＋
        無方向來源文章 200 則 → 數量基礎為 220，方向只由 PTT 貢獻。
        """
        df = pd.DataFrame([
            {"article_id": 1, "trade_date": date(2026, 8, 24), "stock_id": "2330",
             "source": "ptt_stock", "total_comments": 20,
             "post_time": datetime(2026, 8, 24, 10, 0),
             "comments_scraped_at": datetime(2026, 8, 24, 14, 0)},
            {"article_id": 2, "trade_date": date(2026, 8, 24), "stock_id": "2330",
             "source": "dcard_stock", "total_comments": 200,
             "post_time": datetime(2026, 8, 24, 10, 0),
             "comments_scraped_at": datetime(2026, 8, 24, 14, 0)},
        ])
        comments = pd.DataFrame(
            [{"article_id": 1, "comment_seq": i + 1,
              "comment_tag": (["推"] * 10 + ["噓"] * 2 + ["→"] * 8)[i],
              "comment_time": datetime(2026, 8, 24, 10, 5)} for i in range(20)]
            + [{"article_id": 2, "comment_seq": i + 1, "comment_tag": "→",
                "comment_time": datetime(2026, 8, 24, 10, 5)} for i in range(200)]
        )
        agg = self.aggregator._aggregate_direct_comment_counts(
            df, normalize_cutoff_time("15:30:00"), comments)

        self.assertEqual(agg.iloc[0]["total_sum"], 220,
                         "數量含全部來源")
        self.assertEqual(agg.iloc[0]["push_sum"], 10,
                         "方向只由有方向能力的來源貢獻（FEATURE_REGISTRY.md §5.7）")

    def test_unregistered_source_defaults_to_no_direction(self):
        """未登錄的來源預設**不提供方向**——釘住這個刻意選擇的預設方向。

        漏登錄的後果是特徵為 NULL（誠實地少）；
        反過來設計的後果是偽造訊號（安靜地錯）。
        RISK-004 的 Threads 將來同樣沒有推噓，這不是 Dcard 的個案。
        """
        from src.transform.source_capabilities import (
            COMMENT_DIRECTION_SOURCES,
            provides_comment_direction,
        )

        self.assertTrue(provides_comment_direction("ptt_stock"))
        for unknown in ("threads", "dcard_stock", "", None, "PTT_STOCK"):
            self.assertFalse(provides_comment_direction(unknown),
                             "未登錄來源 %r 必須預設為不提供方向" % (unknown,))
        self.assertIn("ptt_stock", COMMENT_DIRECTION_SOURCES)

    def test_required_columns_missing_source_returns_empty(self):
        """`source` 缺席時走既有的空表路徑，不得崩潰、也不得當成有方向。

        這是讀取端契約的守衛：若日後有人改了 SELECT 又忘了 source，
        特徵會是 NULL（可被發現），而不是拿一個不存在的欄位去猜。
        """
        df = pd.DataFrame([{
            "article_id": 1,
            "trade_date": date(2026, 8, 24),
            "stock_id": "2330",
            "total_comments": 20,
            "post_time": datetime(2026, 8, 24, 10, 0),
            "comments_scraped_at": datetime(2026, 8, 24, 14, 0),
        }])
        agg = self.aggregator._aggregate_direct_comment_counts(
            df, normalize_cutoff_time("15:30:00"), pd.DataFrame())

        self.assertTrue(agg.empty, "缺 source 欄時應回空聚合表（欄位齊備供 left join）")
        self.assertIn("push_sum", agg.columns)
