# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 2 基準比對（§3.5、DoD #3a）：既有 4 檔（2330/2382/6488/NVDA）
與現行 `feature_aggregator.py` 對**全量** `stock_prices` 重算的結果逐欄比對。

**純唯讀，不寫入任何資料庫**——不呼叫 `upsert_ml_features()`。這是擴大到
458 檔前的關卡：只有本比對通過，段 2 寫入腳本才可以開工。

================================================================================
⚠⚠ 初版設計錯誤，本版已訂正（PO 2026-09-11 複核）
================================================================================
初版把重算的輸入**限定成 2330/2382/6488 三檔台股**，理由寫成「避免把段 1
之後的 445,635 列全部讀進來、拖長執行時間」。**這個限定本身就是缺陷來源**：

`feature_aggregator.py:310` 的交易日曆 `unique_trading_days` 取自**輸入價格
表的 `trade_date` 聯集**——production 的實際輸入含 NVDA（美股），日曆因此
含美股獨有交易日（台股休市但美股照常，如 02-12/13、02-16~20、04-06、
07-10、08-25~28、08-31）。初版重算把 NVDA 排除在輸入之外，日曆缺少這些
美股獨有日，使台股假期文章的 roll-forward 落點與 production 不同，
造成 36 個 `(trade_date, stock_id)` 的情緒/留言欄「假差異」——那不是
`UG-G3-SB2a` 或 `UG-G3-SB2` routing 造成的，是**比對方法本身的輸入範圍
錯誤**。已登記為 **RISK-027**（`feature_aggregator.py` 交易日曆未依市場
分開，跨市場輸入時會使部分市場的假期文章流失）。

初版的「歸因線索 2」（比對文章 `comments_scraped_at` 分布，指向
`PRE-G3-03` 匯入事件）**是錯誤歸因**：時序不對（`daily_ml_features`
現有 3,713 列是 `PRE-G3-04`，2026-09-08 全量重算寫入，晚於 `PRE-G3-03`
的 09-07 匯入，理應已包含該次匯入的文章)，且該線索的判準對**任何**輸入
日期集合都會命中（全庫 1,330 篇有情緒分數的文章裡有 1,236 篇
`comments_scraped_at` 落在 09-06/07），**structurally 不具鑑別力**——
違反 `CLAUDE.md` §9A.1「檢查必須為偵測而寫，不是為通過而寫」。已刪除。

**訂正做法**：重算改為對**全量** `stock_prices`（與段 2 寫入腳本將使用的
同一份輸入，含 NVDA 與段 1 已回補的 458 檔）執行——不再限定子集；
比對範圍仍限定在既有 4 檔（有歷史基準可比對），但輸入範圍不再限定。
PO 已用此訂正做法唯讀重跑過一次，確認 29 欄契約中 `FeatureAggregator`
實際產出的欄位全數零差異。

================================================================================
比對範圍與通過標準
================================================================================
`daily_ml_features` 29 欄契約中，`target_triple_barrier`／`label_reason`
兩欄由標籤寫入者擁有（`UG-G3-SB1` 腳本／`UG-G3-SB2` 尾端掛點／段 3），
`FeatureAggregator` 從不產出這兩欄（CHAL-010）——**結構上不在本比對範圍
內**，比對的是其餘 27 欄扣掉兩個鍵（`trade_date`／`stock_id`）= 25 個
資料欄。**全部 25 欄現在都是硬性零差異要求**（NaN 對 NaN 視為相同）——
不再有「允許差異但須歸因」的分類：既然 RISK-027 是比對方法的輸入範圍
錯誤，修正輸入範圍後，既有 4 檔的重算應與生產快照精確重現，任何差異
即為真缺陷，停下來查。

輸出：全量重算耗時（供 458 檔段 2 寫入分批策略抓量體依據）；每欄差異
列數；有差異即印出前 10 列供排查。

================================================================================
⚠⚠ 二版修正（PO 2026-09-11）：鍵不對齊拆成「孤兒列」與「新鍵」兩類
================================================================================
候選池 8 天缺口回補（段 1 已重跑）後，`stock_prices` 對既有 3 檔台股多出
8 個交易日，而 `daily_ml_features` 還沒有——**段 2（特徵回補）此刻尚未
執行**，這是預期中的狀態，不是異常。初版把任何鍵不對齊都當成阻斷性
錯誤，無法區分「重算比 daily_ml_features 多出的新鍵（段 2 尚未執行，
預期如此）」與「daily_ml_features 有、重算生不出來的孤兒列（永遠異常）」。

改為：`compare_columns()` 回傳 `"__right_only__"`（孤兒列，永遠阻斷）與
`"__left_only__"`（新鍵，交由呼叫端用 `compute_expected_new_keys()` 算出
的預期集合核對——多一個、少一個都阻斷，不得逕行放行）。逐欄比對只在
兩邊皆有的交集鍵上進行。

================================================================================
⚠⚠ 三版修正（審查員 2026-09-11 複核，段 2 寫入腳本 dry-run 期間發現）：
`_values_differ` 補上 `decimal.Decimal` 型別
================================================================================
`_values_differ` 原本只把 `int`／`float` 當數值比較，其餘型別（含
`decimal.Decimal`）落到 `str(a) != str(b)`。`psycopg2` 的
`cursor.fetchone()` 對 NUMERIC 欄回傳原生 `Decimal`，本腳本與段 2 寫入
腳本的抽樣回讀都會撞到這個型別。多數值的 `Decimal`／`float` 字串表示法
剛好相同，bug 沒有在既有測試現形；但極小值（<1e-4）兩者字串表示法不同
（Python `float` repr 用科學記號、`Decimal` 不用），會被誤判為差異。
詳見 `_values_differ` 函式本身的說明與 `tests/test_sb2a_stage2_baseline_comparison.py`
的 known-FAIL 案例。
"""
import argparse
import decimal
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")

DEFAULT_COMPARE_STOCK_IDS = ("2330", "2382", "6488", "NVDA")

# `FeatureAggregator` 實際產出、與 daily_ml_features 現有列比對的全部欄位
# （29 欄契約扣掉 trade_date／stock_id 兩個鍵、扣掉兩個標籤擁有欄）。
# 全部視為硬性零差異要求（不再分「允許差異」類別，見檔頭說明）。
COMPARE_COLUMNS = [
    "close_price", "volume", "return_1d", "rsi_14",
    "volatility_5d", "volatility_20d", "amplitude_ratio",
    "ma5_bias_ratio", "ma20_bias_ratio", "volume_ratio_5d",
    "target_next_close", "target_return_1d", "target_up_down",
    "article_count", "sentiment_mean", "sentiment_3d_ma", "sentiment_5d_ma",
    "sentiment_lag_1", "sentiment_lag_2", "bullishness_index",
    "agreement_index", "comment_volume_ratio", "comment_polarization",
    "net_push_momentum", "source_status",
]

# 結構上不在本比對範圍——標籤由 SB1／SB2 尾端掛點／段 3 擁有（CHAL-010）。
# `FeatureAggregator` 從不產出這兩欄，比對它們只會恆常顯示「全部不符」，
# 那不是本腳本要偵測的東西。
LABEL_OWNED_COLUMNS_SKIPPED = ("target_triple_barrier", "label_reason")

_NUMERIC_TOLERANCE = 1e-6


def _load_db_config() -> dict:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError("缺少必要資料庫環境變數：" + ", ".join(missing))
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def fetch_all_prices(conn) -> pd.DataFrame:
    """全量 `stock_prices` 讀取——**刻意不加 `WHERE stock_id`**。這正是
    段 2 寫入腳本將使用的同一份輸入，且是 RISK-027 的修正核心：日曆必須
    看到全部市場（含 NVDA）的交易日聯集，才能與 production 的 roll-forward
    結果一致。"""
    return pd.read_sql(
        "SELECT trade_date, stock_id, high_price, low_price, close_price, "
        "volume FROM stock_prices;",
        conn,
    )


def fetch_full_articles_and_mappings(conn):
    """文章／個股映射／題材映射／留言逐則資料，查詢語句比照
    `DBWriter.fetch_all_for_features()`（RISK-023／DEC-039 新增 df_comments）。"""
    from src.transform.source_capabilities import FEATURE_SOURCE_ALLOWLIST
    _allow = ", ".join("'%s'" % s for s in sorted(FEATURE_SOURCE_ALLOWLIST))
    df_articles = pd.read_sql(
        "SELECT article_id, source, post_time, fetch_keyword, sentiment_score, "
        "push_count, boo_count, neutral_count, total_comments, comments_scraped_at "
        "FROM market_articles WHERE sentiment_score IS NOT NULL "
        "AND source IN (%s);" % _allow,
        conn,
    )
    df_mapping = pd.read_sql("SELECT keyword, stock_id FROM entity_mapping;", conn)
    df_theme_mapping = pd.read_sql(
        "SELECT theme_keyword, stock_id, relevance_weight FROM theme_stock_mapping;",
        conn,
    )
    df_comments = pd.read_sql(
        "SELECT ac.article_id, ac.comment_seq, ac.comment_tag, ac.comment_time "
        "FROM article_comments ac "
        "JOIN market_articles ma ON ma.article_id = ac.article_id "
        "WHERE ma.sentiment_score IS NOT NULL "
        "AND ma.source IN (%s);" % _allow,
        conn,
    )
    return df_articles, df_mapping, df_theme_mapping, df_comments


def fetch_existing_features(conn, stock_ids) -> pd.DataFrame:
    cols = ["trade_date", "stock_id"] + COMPARE_COLUMNS
    query = "SELECT %s FROM daily_ml_features WHERE stock_id = ANY(%%(ids)s);" % (
        ", ".join(cols))
    df = pd.read_sql(query, conn, params={"ids": list(stock_ids)})
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def recompute_features_full(conn) -> pd.DataFrame:
    """對**全量** `stock_prices`（不限股票）呼叫現行 `FeatureAggregator`
    重算。純記憶體運算，不寫入。回傳含全部股票的特徵表——呼叫端自行篩選
    要比對的子集。"""
    from src.transform.feature_aggregator import FeatureAggregator

    df_prices = fetch_all_prices(conn)
    df_articles, df_mapping, df_theme_mapping, df_comments = fetch_full_articles_and_mappings(conn)

    aggregator = FeatureAggregator()
    df_features = aggregator.generate_daily_features(
        df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping,
        df_comments=df_comments)
    df_features = aggregator.generate_target_labels(df_features)

    df_features = df_features.copy()
    df_features["trade_date"] = pd.to_datetime(df_features["trade_date"]).dt.date
    return df_features


_NUMERIC_TYPES = (int, float, decimal.Decimal)


def _values_differ(a, b) -> bool:
    """兩值是否視為不同。NaN 對 NaN 視為相同（不是差異）；一個 NaN
    一個不是則為差異；數值型比較容許 `_NUMERIC_TOLERANCE` 浮點誤差；
    其餘型別轉字串比較。

    ⚠ **`decimal.Decimal` 修正**（審查員 2026-09-11 複核，段 2 腳本
    dry-run 期間發現）：`psycopg2` 的 `cursor.fetchone()` 對 NUMERIC 欄
    回傳原生 `decimal.Decimal`，不是 `int`／`float`——原本的
    `isinstance(a, (int, float))` 判斷會漏接，落到 `str(a) != str(b)`
    的字串比較。`Decimal` 與 `float` 的字串表示法在多數值上剛好相同
    （如 `'603.0'`），這個 bug 才沒有在既有測試與第一次 dry-run 中現形；
    但極小值（<1e-4）Python 的 `float` repr 用科學記號、`Decimal` 不用
    （`daily_ml_features` 現表就有 2 個這種值），抽樣回讀到就會誤判為
    不符、讓段 2 寫入腳本在寫完一批後才失敗停止——`_NUMERIC_TYPES` 加入
    `decimal.Decimal` 後，經 `float()` 轉換走數值容差比較，不再落到
    字串比較。"""
    a_null, b_null = pd.isna(a), pd.isna(b)
    if a_null and b_null:
        return False
    if a_null != b_null:
        return True
    if isinstance(a, _NUMERIC_TYPES) and isinstance(b, _NUMERIC_TYPES):
        return abs(float(a) - float(b)) > _NUMERIC_TOLERANCE
    return str(a) != str(b)


def compare_columns(df_recomputed: pd.DataFrame, df_existing: pd.DataFrame,
                     columns) -> dict:
    """逐欄比對，回傳 `{欄名: DataFrame[trade_date, stock_id, recomputed, existing]}`
    （只含有差異的列；欄若無差異則該欄不出現在回傳字典裡）。逐欄比對只在
    兩邊都有的鍵（交集）上做。

    `(trade_date, stock_id)` 鍵不對齊拆成兩類（PO 2026-09-11 複核修正）：

    - **`"__right_only__"`**：`df_existing` 有、`df_recomputed` 沒有——
      `daily_ml_features` 裡有一列，重算（依現行 `stock_prices`）卻生不出
      對應列。這**永遠是異常**（孤兒列），呼叫端必須阻斷，不得放行。
    - **`"__left_only__"`**：`df_recomputed` 有、`df_existing` 沒有——
      重算比 `daily_ml_features` 多出的鍵。**這不是異常本身**：段 1
      （價格回補）先於段 2（特徵回補）執行時，`stock_prices` 已有的新
      日期理所當然還沒進 `daily_ml_features`（段 2 的工作）。是否合理
      由呼叫端對照一個「預期新鍵集合」判斷（見 `compute_expected_new_keys`），
      不是本函式的職責——本函式只負責如實回報「這些鍵只在一邊出現」。
    """
    merged = df_recomputed.merge(
        df_existing, on=["trade_date", "stock_id"], how="outer",
        suffixes=("_recomputed", "_existing"), indicator=True)

    diffs = {}
    right_only = merged.loc[merged["_merge"] == "right_only"]
    if not right_only.empty:
        diffs["__right_only__"] = right_only[["trade_date", "stock_id"]]
    left_only = merged.loc[merged["_merge"] == "left_only"]
    if not left_only.empty:
        diffs["__left_only__"] = left_only[["trade_date", "stock_id"]]

    both = merged.loc[merged["_merge"] == "both"]
    for col in columns:
        rc, ec = f"{col}_recomputed", f"{col}_existing"
        if rc not in both.columns or ec not in both.columns:
            continue
        mask = both.apply(lambda r: _values_differ(r[rc], r[ec]), axis=1)
        if mask.any():
            diffs[col] = both.loc[mask, ["trade_date", "stock_id", rc, ec]].rename(
                columns={rc: "recomputed", ec: "existing"})
    return diffs


def compute_expected_new_keys(compare_stock_ids, df_existing: pd.DataFrame) -> set:
    """段 1（價格回補）先於段 2（特徵回補）執行時，`compare_columns()` 的
    `"__left_only__"` 預期恰好等於：**回補股票子集 × 缺口交易日**
    （`GAP_TRADE_DATES`，從缺口回補腳本 import，不重抄一份權威清單）
    扣掉 `daily_ml_features` 已經有的鍵（例如 2330／2382 的
    2026-09-01／09-02，那兩天在缺口回補之前就已存在，不是新鍵）。

    回傳 `{(stock_id, date), ...}` 集合，供呼叫端與實際的 `"__left_only__"`
    比對——多一個、少一個都代表「重算多出的鍵」不只是段 2 尚未執行這個
    已知原因，必須 FAIL 並列出差集，不得逕行放行。
    """
    from scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap import (
        GAP_TRADE_DATES)
    import datetime as _dt

    gap_dates = {_dt.date.fromisoformat(d) for d in GAP_TRADE_DATES}
    existing_keys = set(zip(df_existing["stock_id"], df_existing["trade_date"]))
    all_candidates = {
        (sid, d) for sid in compare_stock_ids for d in gap_dates
    }
    return all_candidates - existing_keys


def attribute_sb2_routing(conn, diff_dates_stocks) -> pd.DataFrame:
    """歸因線索（保留，供未來段 2 實際處理 455 新檔時可能用到）：交叉比對
    `UG-G3-SB2` 新增路由（`entity_mapping` `description` 前綴
    `[auto:UG-G3-SB2]`）當天是否有對應文章。

    ⚠ **對既有 4 檔（2330/2382/6488/NVDA）預期找不到東西，這是正常的**——
    `UG-G3-SB2` 的路由回補以 `exclude_already_routed_stock_ids()` 明確
    排除既有已路由股票，這 4 檔的 keyword 集合本就沒被那次回補動過。
    保留本函式是因為段 2 日後處理**新** 455 檔時，這條線索才會真正派上
    用場——新股票的文章計數確實可能因 SB2 路由而變化。**本次（既有 4 檔）
    修正 RISK-027 之後應該零差異，這條線索理論上用不到。**
    """
    if diff_dates_stocks.empty:
        return pd.DataFrame()
    new_routed = pd.read_sql(
        "SELECT keyword, stock_id FROM entity_mapping "
        "WHERE description LIKE '[auto:UG-G3-SB2]%%';", conn)
    if new_routed.empty:
        return pd.DataFrame()
    stock_ids = tuple(diff_dates_stocks["stock_id"].unique())
    keywords = tuple(new_routed.loc[
        new_routed["stock_id"].isin(stock_ids), "keyword"].unique())
    if not keywords:
        return pd.DataFrame()
    dates = tuple(diff_dates_stocks["trade_date"].unique())  # date 物件，非字串
    articles = pd.read_sql(
        "SELECT fetch_keyword, post_time::date AS post_date, count(*) AS n "
        "FROM market_articles WHERE fetch_keyword = ANY(%(kw)s) "
        "AND post_time::date = ANY(%(dates)s::date[]) "
        "GROUP BY fetch_keyword, post_date;",
        conn, params={"kw": list(keywords), "dates": list(dates)},
    )
    return articles.merge(new_routed, left_on="fetch_keyword", right_on="keyword")


def split_allowed_diffs(diff_df: pd.DataFrame, allow_diff_after, allow_diff_stocks):
    """把一欄的差異列拆成「允許」與「不允許」兩份。

    允許的條件（**兩者皆須成立**）：`stock_id` 在 `allow_diff_stocks` 集合
    內，**且** `trade_date >= allow_diff_after`。任一條件不成立即為不允許
    ——不允許的差異仍是 FAIL，即使發生在允許的股票或允許的日期之後
    （只滿足其中一半不算數，見 `tests/test_sb2a_stage2_baseline_comparison.py`
    的邊界測試）。

    `allow_diff_after` 為 `None` 時（未提供 `--allow-diff-after`），
    一律視為不允許——沒有指定基準日期就不該有任何差異被放行。
    """
    if allow_diff_after is None or not allow_diff_stocks:
        return diff_df.iloc[0:0], diff_df
    mask = (
        diff_df["stock_id"].isin(allow_diff_stocks)
        & (diff_df["trade_date"] >= allow_diff_after)
    )
    return diff_df.loc[mask], diff_df.loc[~mask]


def main(compare_stock_ids, allow_diff_after=None, allow_diff_stocks=None) -> None:
    db_config = _load_db_config()
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user, inet_server_port();")
    print("CONN CHECK:", cur.fetchone())
    print("【唯讀比對】不執行任何 INSERT／UPDATE。全量重算，比對子集：",
          compare_stock_ids)

    t_start = time.time()
    df_recomputed_full = recompute_features_full(conn)
    t_elapsed = time.time() - t_start
    n_stocks_full = df_recomputed_full["stock_id"].nunique()
    print(f"\n全量重算耗時：{t_elapsed:.2f} 秒（{n_stocks_full} 檔，"
          f"{len(df_recomputed_full)} 列）——供 458 檔段 2 寫入分批策略"
          f"抓量體依據")

    df_recomputed = df_recomputed_full.loc[
        df_recomputed_full["stock_id"].isin(compare_stock_ids)].reset_index(drop=True)
    df_existing = fetch_existing_features(conn, compare_stock_ids)
    print(f"重算子集（比對用）：{len(df_recomputed)} 列；"
          f"現有 daily_ml_features：{len(df_existing)} 列")

    diffs = compare_columns(df_recomputed, df_existing, COMPARE_COLUMNS)

    if "__right_only__" in diffs:
        print("\n⚠⚠ daily_ml_features 有列、重算生不出對應列（孤兒列）——"
              "永遠是異常，阻斷：")
        print(diffs["__right_only__"].to_string(index=False))
        conn.close()
        sys.exit(1)

    if "__left_only__" in diffs:
        expected_new_keys = compute_expected_new_keys(compare_stock_ids, df_existing)
        actual_new_keys = set(
            zip(diffs["__left_only__"]["stock_id"],
                diffs["__left_only__"]["trade_date"]))
        missing = expected_new_keys - actual_new_keys
        extra = actual_new_keys - expected_new_keys
        if missing or extra:
            print("\n⚠⚠ 重算多出的鍵與預期集合（回補股票子集 × 缺口交易日，"
                  "扣掉既有鍵）不相符——阻斷：")
            if missing:
                print(f"  預期有、實際沒有（{len(missing)}）：{sorted(missing)}")
            if extra:
                print(f"  實際有、預期沒有（{len(extra)}）：{sorted(extra)}")
            conn.close()
            sys.exit(1)
        print(f"\n重算多出 {len(actual_new_keys)} 個鍵，恰好等於預期集合"
              f"（段 2 尚未執行，daily_ml_features 對這些新日期本來就還沒有"
              f"列，不是異常）：{sorted(actual_new_keys)}")

    if allow_diff_after is not None:
        print(f"\n允許差異範圍：股票 {allow_diff_stocks}、"
              f"日期 >= {allow_diff_after}（例如候選池缺口回補後，08-21 "
              f"之後的滾動窗口／文章歸屬合理改變）——**兩條件須同時成立**，"
              f"不滿足的差異仍算 FAIL。")

    print("\n=== 逐欄比對（全部視為硬性零差異要求，允許範圍內的差異另計）===")
    failures = []
    allowed_diff_total = 0
    for col in COMPARE_COLUMNS:
        col_diffs = diffs.get(col)
        if col_diffs is None or col_diffs.empty:
            print(f"  {col}: 0 列差異 [PASS]")
            continue
        allowed, disallowed = split_allowed_diffs(
            col_diffs, allow_diff_after, allow_diff_stocks)
        allowed_diff_total += len(allowed)
        if disallowed.empty:
            print(f"  {col}: {len(allowed)} 列差異，全部在允許範圍內 [PASS]")
        else:
            print(f"  {col}: {len(disallowed)} 列不允許的差異"
                  f"（另有 {len(allowed)} 列在允許範圍內）[FAIL]")
            failures.append(col)
            print(disallowed.head(20).to_string(index=False))
        if not allowed.empty:
            print(f"    允許範圍內差異列（{col}，完整列出）：")
            print(allowed.to_string(index=False))

    if failures:
        all_diff_rows = pd.concat(
            [diffs[c][["trade_date", "stock_id"]] for c in failures]).drop_duplicates()
        attribution = attribute_sb2_routing(conn, all_diff_rows)
        if not attribution.empty:
            print("\n歸因線索（UG-G3-SB2 新增路由 keyword 命中的文章日期）：")
            print(attribution.to_string(index=False))
        else:
            print("\n歸因線索（UG-G3-SB2 新增路由）：無命中——"
                  "若修正 RISK-027 後仍有不允許範圍的差異，須人工排查根因，"
                  "不得逕行判定為正常。")

    print("\n=== 結論 ===")
    if failures:
        print(f"FAIL：{len(failures)} 欄有不允許範圍的差異：{failures}")
        print("段 2 不可擴大到 458 檔——先排查上述欄位。")
    else:
        msg = (f"PASS：{len(COMPARE_COLUMNS)} 個比對欄位皆無不允許範圍的差異"
               f"（{len(compare_stock_ids)} 檔、{len(df_existing)} 列）。")
        if allowed_diff_total:
            msg += f" 允許範圍內差異共 {allowed_diff_total} 筆（見上方逐欄列表）。"
        print(msg)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compare-stock-ids", default=",".join(DEFAULT_COMPARE_STOCK_IDS),
        help="逗號分隔的股票代號子集，僅影響比對範圍（重算永遠是全量輸入），"
             "預設既有 4 檔")
    parser.add_argument(
        "--allow-diff-after", default=None,
        help="ISO 日期（如 2026-08-21）。與 --allow-diff-stocks 搭配："
             "該日期（含）之後、屬於允許股票集合的差異視為預期內，不計入 "
             "FAIL——用於候選池缺口回補後重跑基線，既有台股 3 檔在缺口"
             "期間之後的合理改變。未提供時等同於不允許任何差異。")
    parser.add_argument(
        "--allow-diff-stocks", default=None,
        help="逗號分隔股票代號，僅這些股票的差異可被允許（仍須同時滿足 "
             "--allow-diff-after）")
    args = parser.parse_args()

    _allow_after = None
    if args.allow_diff_after:
        import datetime as _dt
        _allow_after = _dt.date.fromisoformat(args.allow_diff_after)
    _allow_stocks = None
    if args.allow_diff_stocks:
        _allow_stocks = tuple(
            s.strip() for s in args.allow_diff_stocks.split(",") if s.strip())

    main(tuple(s.strip() for s in args.compare_stock_ids.split(",") if s.strip()),
         allow_diff_after=_allow_after, allow_diff_stocks=_allow_stocks)
