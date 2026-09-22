"""
tests/test_ml_feature_store_contract.py — UG-G2-SB1 daily_ml_features 29 欄契約專項測試

涵蓋：DBWriter.ML_FEATURE_COLUMNS 契約完整性、source_status 判定邏輯（PO 核准之
「direct_count>0 OR theme_count>0 → SUCCESS」規則，見 G2_SB1_GATE_A_PROPOSAL.md §7 決策點 1）、
以及尚未實作欄位（CORE_16／留言特徵／target_triple_barrier／label_reason）維持 NULL
而非被補 0 或中立值（CLAUDE.md §7.1 不變量）。
"""

import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock

# host 未安裝 psycopg2 時才用假模組占位；container 已安裝真實套件時必須用真的，
# 不得覆蓋——`"psycopg2" not in sys.modules` 判準看的是「有沒有被 import 過」，
# 不是「有沒有安裝」，單獨跑本檔時容器內真實 psycopg2 尚未被 import 就會被蓋掉
# （PO 2026-09-09 複審發現，於 tests/test_panel_dataset.py 一併修正）。
try:
    import psycopg2  # noqa: F401  能 import 就是真的裝了，直接用，不覆蓋
except ImportError:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = MagicMock()
    psycopg2_extras = types.ModuleType("psycopg2.extras")
    psycopg2_extras.execute_values = MagicMock()
    psycopg2.extras = psycopg2_extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2_extras

import pandas as pd

from src.loaders.db_writer import DBWriter
from src.transform.feature_aggregator import FeatureAggregator


class FeatureStoreColumnContractTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_feature_store_total_columns_29"""

    def test_feature_store_total_columns_29(self):
        self.assertEqual(len(DBWriter.ML_FEATURE_COLUMNS), 29)
        # 主鍵欄位必須存在且在最前面（與 daily_ml_features PRIMARY KEY (trade_date, stock_id) 一致）
        self.assertEqual(DBWriter.ML_FEATURE_COLUMNS[0], "trade_date")
        self.assertEqual(DBWriter.ML_FEATURE_COLUMNS[1], "stock_id")
        # 不得有重複欄位
        self.assertEqual(len(DBWriter.ML_FEATURE_COLUMNS), len(set(DBWriter.ML_FEATURE_COLUMNS)))

    def test_upsert_ml_features_converts_nan_to_none_in_pure_numeric_columns(self):
        """迴歸測試（UG-G2-SB1 隔離 DB E2E 驗證發現）：`target_up_down` 等欄位是純 float64
        型態（每檔股票最後一個交易日因 shift(-1) 產生 NaN，非缺欄位補值），
        `DataFrame.where(cond, None)` 對全數值欄位會把 None 折回 NaN 而非真正的 Python
        None——這種 NaN 送進 INTEGER 欄位時會被 psycopg2 判定為非法整數值。
        Known-FAIL 案例：改用舊版 `.where(pd.notnull(df), None)` 實作時，本測試最後一列的
        `target_up_down` 會斷言失敗（值為 `nan` 而非 `None`），已重現後才確認新版修正有效。"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        df = pd.DataFrame({
            "trade_date": [date(2026, 8, 24), date(2026, 8, 25)],
            "stock_id": ["2330", "2330"],
            "close_price": [100.0, 101.0],
            "volume": [10000, 11000],
            "source_status": ["SUCCESS", "SUCCESS"],
            # 純 float64 欄位，最後一列為 NaN（模擬每檔股票最後一個交易日無未來資料）
            "target_up_down": [1.0, float("nan")],
            "target_next_close": [101.0, float("nan")],
        })

        writer.upsert_ml_features(df)

        _, records = writer._execute_batch.call_args[0]
        target_up_down_idx = DBWriter.ML_FEATURE_COLUMNS.index("target_up_down")
        last_row_value = records[1][target_up_down_idx]
        self.assertIsNone(
            last_row_value,
            f"NaN 必須轉為 Python None 才能安全寫入 INTEGER 欄位，實際為 {last_row_value!r}"
            f"（型態 {type(last_row_value)}）",
        )

    def test_dbwriter_upsert_29_columns_with_full_dataframe(self):
        """輸入已含全部 29 欄時，寫入的 tuple 長度仍為 29，且欄位順序與 ML_FEATURE_COLUMNS 一致"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        row = {col: None for col in DBWriter.ML_FEATURE_COLUMNS}
        row.update({
            "trade_date": date(2026, 8, 26), "stock_id": "2330",
            "close_price": 1000.0, "volume": 30000, "source_status": "SUCCESS",
        })
        df = pd.DataFrame([row])

        writer.upsert_ml_features(df)

        writer._execute_batch.assert_called_once()
        query, records = writer._execute_batch.call_args[0]
        self.assertEqual(len(records[0]), 29)
        self.assertIn("source_status", query)
        self.assertIn("label_reason", query)


class LabelColumnsNotOverwrittenByFeatureUpsertTests(unittest.TestCase):
    """CHAL-010 迴歸測試：`upsert_ml_features()` 每日跑一次就會把 SB1／SB2 寫入的
    Triple-Barrier 標籤清空——`ON CONFLICT DO UPDATE SET` 對 29 欄全覆寫，而
    `feature_aggregator` 的輸出不含 `target_triple_barrier`／`label_reason`，
    兩欄因此在每次特徵 upsert 時被寫回 NULL（PO 2026-09-10 複審 SB2a 提案期間
    發現，`db_writer.py:714-722`；SB2 的每日尾端掛點只補回每檔最後
    `holding_period+1` 列，其餘列的標籤沒有任何機制補救）。

    修法：這兩欄由標籤寫入者（`UG-G3-SB1` 腳本／`UG-G3-SB2` 掛點／
    `UG-G3-SB2a` 段 3）擁有，`upsert_ml_features()` 的 `DO UPDATE SET` 不得
    觸碰；新列 `INSERT` 時兩欄仍為 `None`（新列本來就還沒有標籤，這是正確
    狀態，不是本修法要擋的東西）。
    """

    def test_do_update_set_excludes_label_owned_columns(self):
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()
        df = pd.DataFrame({
            "trade_date": [date(2026, 9, 1)],
            "stock_id": ["2330"],
            "close_price": [600.0],
            "volume": [1000],
            "source_status": ["SUCCESS"],
        })

        writer.upsert_ml_features(df)

        query, records = writer._execute_batch.call_args[0]
        insert_cols_part, update_part = query.split("DO UPDATE SET")

        # INSERT 欄位清單仍含兩欄（新列本來就該有這兩欄，值為 None）
        self.assertIn("target_triple_barrier", insert_cols_part)
        self.assertIn("label_reason", insert_cols_part)
        idx_tb = DBWriter.ML_FEATURE_COLUMNS.index("target_triple_barrier")
        idx_lr = DBWriter.ML_FEATURE_COLUMNS.index("label_reason")
        self.assertIsNone(records[0][idx_tb])
        self.assertIsNone(records[0][idx_lr])

        # 但 DO UPDATE SET 不得覆寫這兩欄——known-FAIL：修正前版本這兩項斷言會失敗
        self.assertNotIn(
            "target_triple_barrier = EXCLUDED.target_triple_barrier", update_part,
            "target_triple_barrier 不得出現在 DO UPDATE SET——每日特徵 upsert 會把"
            "既有 Triple-Barrier 標籤清空（CHAL-010）",
        )
        self.assertNotIn(
            "label_reason = EXCLUDED.label_reason", update_part,
            "label_reason 不得出現在 DO UPDATE SET，理由同上",
        )

    def test_feature_upsert_then_tail_hook_preserves_non_tail_labels(self):
        """整合式迴歸測試：模擬『特徵 upsert → 尾端掛點』兩步，斷言非尾端列的既有
        標籤在特徵 upsert 這一步不會被清空——這正是 SB2 三項斷言與 24/24 基線都
        驗不到的情境：它們驗的是掛點會不會跑，不是跑之前標籤還在不在。"""
        # 模擬一張已有 10 列標籤的 daily_ml_features（例如 UG-G3-SB1 全量寫入後的狀態）
        table = pd.DataFrame({
            "stock_id": ["2330"] * 10,
            "trade_date": pd.bdate_range("2026-01-01", periods=10).strftime("%Y-%m-%d"),
            "target_triple_barrier": [1.0, -1.0, 0.0, 1.0, -1.0, 1.0, -1.0, 0.0, 1.0, -1.0],
            "label_reason": [float("nan")] * 10,
        })
        before_labels = table["target_triple_barrier"].copy()

        # 步驟一：每日特徵 upsert（feature_aggregator 輸出不含標籤欄，同生產現況）
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()
        df_features = pd.DataFrame({
            "trade_date": table["trade_date"],
            "stock_id": table["stock_id"],
            "close_price": [100.0] * 10,
            "volume": [1000] * 10,
            "source_status": ["SUCCESS"] * 10,
        })
        writer.upsert_ml_features(df_features)
        query, records = writer._execute_batch.call_args[0]
        _, update_part = query.split("DO UPDATE SET")

        # 依實際產生的 SQL 判定 DO UPDATE SET 真正會覆寫哪些欄，值取自
        # upsert_ml_features() 真正建構出的 records（缺欄位時為 None，同生產
        # 行為）——**不得**只在 col 存在於 df_features.columns 時才套用，
        # 否則本測試對「值被覆寫成 None」這個實際故障模式結構上測不出來
        # （第一版正是這個錯：df_features 本來就不含這兩欄，迴圈因此永遠跳過
        # 它們，不論 DO UPDATE SET 有沒有覆寫，斷言都會通過——結構上無法
        # 失敗，§9A.1）。
        simulated = table.copy()
        for col in DBWriter.ML_FEATURE_COLUMNS:
            if f"{col} = EXCLUDED.{col}" in update_part:
                col_idx = DBWriter.ML_FEATURE_COLUMNS.index(col)
                simulated[col] = [row[col_idx] for row in records]

        pd.testing.assert_series_equal(
            simulated["target_triple_barrier"], before_labels,
            check_names=False,
        )


class SourceStatusDeterminationTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_source_status_*（UG-G2-SB1 §7 決策點 1）"""

    def setUp(self):
        self.aggregator = FeatureAggregator()
        self.trade_dates = [date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26)]

    def _prices(self, stock_id="2330"):
        return pd.DataFrame([
            {"trade_date": d, "stock_id": stock_id, "close_price": 100.0 + i, "volume": 10000}
            for i, d in enumerate(self.trade_dates)
        ])

    def test_source_status_success_when_direct_article_present(self):
        df_articles = pd.DataFrame([{
            "article_id": 1, "source": "ptt_stock", "fetch_keyword": "台積電",
            "post_time": pd.Timestamp("2026-08-24 09:00:00"), "sentiment_score": 0.7,
            "title": "台積電法說會樂觀",
        }])
        df_mapping = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])

        df_features = self.aggregator.generate_daily_features(
            self._prices(), df_articles, df_mapping, df_comments=pd.DataFrame()
        )

        row = df_features[df_features["trade_date"] == date(2026, 8, 24)].iloc[0]
        self.assertEqual(row["source_status"], "SUCCESS")
        self.assertGreater(row["article_count"], 0)

    def test_source_status_success_when_only_spillover_present(self):
        """零直接文章、僅靠題材溢出取得訊號時，依 PO 核准邏輯仍應標為 SUCCESS（非 SUCCESS_EMPTY）"""
        df_articles = pd.DataFrame([{
            "article_id": 1, "source": "ptt_stock", "fetch_keyword": "矽光子",
            "post_time": pd.Timestamp("2026-08-24 09:00:00"), "sentiment_score": 0.8,
            "title": "矽光子題材噴出",
        }])
        # 個股映射表刻意不含「矽光子」關鍵字 → 這篇文章不會被視為 2330 的直接文章
        df_mapping = pd.DataFrame([{"keyword": "台積電", "stock_id": "2330"}])
        df_theme_mapping = pd.DataFrame([{
            "theme_keyword": "矽光子", "stock_id": "2330", "relevance_weight": 0.8
        }])

        df_features = self.aggregator.generate_daily_features(
            self._prices(), df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
            df_comments=pd.DataFrame(),
        )

        row = df_features[df_features["trade_date"] == date(2026, 8, 24)].iloc[0]
        self.assertEqual(row["source_status"], "SUCCESS")
        self.assertGreater(row["article_count"], 0)

    def test_source_status_success_empty_when_no_articles_at_all(self):
        df_features = self.aggregator.generate_daily_features(
            self._prices(), pd.DataFrame(), pd.DataFrame(), df_comments=pd.DataFrame()
        )

        for _, row in df_features.iterrows():
            self.assertEqual(row["source_status"], "SUCCESS_EMPTY")
            self.assertEqual(row["article_count"], 0)


class UnimplementedColumnsStayNullTests(unittest.TestCase):
    """對應 Master Plan Brief 既定測試名稱：test_null_not_zero_for_unimplemented_columns

    CLAUDE.md §7.1：Database Error 不得被偽裝成 Empty Result；同理，「尚未實作」不得被
    偽裝成「已知為 0／中立值」。CORE_16、留言特徵、target_triple_barrier、label_reason
    在 UG-G2-SB1 完成後仍應為 NULL，直到各自負責的 SB／Gate 補上計算邏輯。
    """

    UNIMPLEMENTED_COLUMNS = [
        "amplitude_ratio", "ma5_bias_ratio", "ma20_bias_ratio", "volume_ratio_5d",
        "comment_volume_ratio", "comment_polarization", "net_push_momentum",
        "target_triple_barrier", "label_reason",
    ]

    def test_unimplemented_columns_written_as_null_not_zero(self):
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        df = pd.DataFrame([{
            "trade_date": date(2026, 8, 26), "stock_id": "2330",
            "close_price": 1000.0, "volume": 30000, "source_status": "SUCCESS",
        }])
        writer.upsert_ml_features(df)

        _, records = writer._execute_batch.call_args[0]
        for col in self.UNIMPLEMENTED_COLUMNS:
            idx = DBWriter.ML_FEATURE_COLUMNS.index(col)
            self.assertIsNone(
                records[0][idx],
                f"{col} 應為 NULL（尚未實作），不得被補 0 或其他預設值",
            )

    def test_label_reason_stays_null_when_target_triple_barrier_not_yet_computed(self):
        """label_reason／target_triple_barrier 一致性：Gate 3 前兩者皆應為 NULL
        （對應 database/migrations/002_expand_ml_features.sql 的 chk_label_reason_consistency
        第三分支「尚未計算標籤」，非 Triple-Barrier 演算法判定後的 ambiguous/insufficient/no_entry）"""
        writer = DBWriter.__new__(DBWriter)
        writer._execute_batch = MagicMock()

        df = pd.DataFrame([{
            "trade_date": date(2026, 8, 26), "stock_id": "2330",
            "close_price": 1000.0, "volume": 30000, "source_status": "SUCCESS",
        }])
        writer.upsert_ml_features(df)

        _, records = writer._execute_batch.call_args[0]
        label_reason_idx = DBWriter.ML_FEATURE_COLUMNS.index("label_reason")
        triple_barrier_idx = DBWriter.ML_FEATURE_COLUMNS.index("target_triple_barrier")
        self.assertIsNone(records[0][label_reason_idx])
        self.assertIsNone(records[0][triple_barrier_idx])


if __name__ == "__main__":
    unittest.main()
