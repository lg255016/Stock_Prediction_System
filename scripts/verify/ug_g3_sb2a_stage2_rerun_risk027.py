# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 2 重跑（RISK-027 修復後）：只更新受跨市場交易日曆修法
（DEC-037，方案 B）影響的情緒／留言欄，不做全表 upsert。

⚠ **本腳本自 DEC-039（2026-09-14）起不可重跑，僅供歷史對照**：
`compute_new_full_recompute()` 呼叫的 `FeatureAggregator.generate_daily_features()`
現在要求必要參數 `df_comments`，本腳本未同步更新（工作已於 2026-09-12 完成，
不預期重跑），直接執行會因缺少該參數而失敗。

**設計核准**：PO 2026-09-12（段 2 重跑改為「只更新差異鍵」，理由見下方
「為何不做全表 upsert」）。

================================================================================
背景
================================================================================
`RISK-027` 修復（commit `e21d3c6`）改變了 `feature_aggregator.py` 的
Roll-Forward 交易日曆語意（全市場聯集 → 依股票自身）。真實庫唯讀重算
（PO 2026-09-12）顯示：458＋NVDA 檔全量重算對現有 `daily_ml_features`
只有 **132 個 `(stock_id, trade_date)` 鍵**、**14 檔股票**有差異，全部集中
在情緒／留言相關欄；價格衍生欄與 Triple-Barrier 標籤欄**零差異**（本來就
應該——RISK-027 修法完全不動價格計算路徑）。

================================================================================
為何不做全表 upsert（改為「只更新差異鍵」）
================================================================================
`ug_g3_sb2a_write_triple_barrier_labels.py`（段 3）與
`ug_g3_sb2a_backfill_features.py`（段 2 原始寫入）都是「全表重算 + 全表
upsert」，但那是**當時的正確設計**：段 2 原始寫入的前提是 458 檔全部沒有
既有特徵列，本來就要整批寫入。**本次前提不同**——`daily_ml_features` 已有
正確的 449,263 列，只有 132 列的 12 個欄位需要更新。若沿用全表 upsert，
`EXISTING_ROWS_BEFORE=3713`／`EXISTING_LABEL_COUNTS=(3529,184)` 這類「開工前
現況」常數本來就是段 2 原始腳本專屬、早已過期（現況是 449,263 列、
標籤 (410443,38820)）；即使改寫這些常數以求全表重算能跑，全表 upsert
仍會**觸碰 132 萬列裡的 449,131 列其實毫無變化的資料**，稽核與復原成本
與「只更新 132 列」不成比例。**兩條路都要改腳本，因此選寫入面最小的**
（PO 2026-09-12 裁決）。

================================================================================
核心機制：預期影響集不用手抄，用「舊版 vs 新版」機械算出
================================================================================
與段 3 的 `compute_expected_relabel_impact()` 同一設計哲學（機械算出預期
影響範圍，不猜日期），但比對對象不同：段 3 比的是「回補前序列 vs 現在
序列」（同一份程式碼、不同輸入），本腳本比的是「**舊版程式碼 vs 新版
程式碼**（同一份輸入，即現在的完整真實庫內容）」——因為 RISK-027 是
**程式碼**修法，不是資料變化。

1. 用 `git show 0da87d9:src/transform/feature_aggregator.py`
   （RED 測試 commit，`feature_aggregator.py` 內容與修法前完全相同）
   在記憶體中載入舊版 `FeatureAggregator`——**不落地成檔案、不改動
   `sys.path` 上的正式模組**，只用於本次比對。
2. 同一份真實庫輸入（全量 `stock_prices`／`market_articles`／
   `entity_mapping`／`theme_stock_mapping`），分別跑舊版與新版
   `generate_daily_features()`，逐欄比對 12 個情緒／留言欄——
   分岔的 `(stock_id, trade_date)` 集合即為**機械算出的預期影響集**
   （連同每個鍵實際分岔的欄位子集）。
3. 另外獨立算一次「新版重算 vs 現有 `daily_ml_features`」的**實際差異集**
   （連同分岔欄位子集）。
4. **斷言兩者相等**——鍵集合相等，且逐鍵的分岔欄位子集也相等。任一不等，
   代表「新版重算 vs 庫」的差異不能完全歸因於本次修法（庫裡藏著本修法
   以外的其他漂移），**拒絕寫入**，不得逕行採用較寬鬆的一方。

================================================================================
前置守衛（任一不符 → 拒絕，唯讀預覽與 `--write` 皆拒絕）
================================================================================
1. `daily_ml_features` 總列數 = 449,263。
2. 標籤現況 `(count(target_triple_barrier), count(label_reason))` =
   `(410443, 38820)`——段 2 重跑不動標籤欄，此數字須維持不變；若已變化，
   代表有本腳本未預期的其他寫入介入，拒絕執行。
3. 價格衍生 13 欄（`close_price`…`target_up_down`）新版重算 vs 庫
   **零差異**——RISK-027 修法不動這條路徑，任何差異代表另一個問題。
4. 留言三欄（`comment_volume_ratio`／`comment_polarization`／
   `net_push_momentum`）新版重算 vs 庫**零差異**——真實庫的留言資料
   全部因 DEC-024 時點過濾而不通過（1,330 篇有情緒分數的文章，留言
   全在 09-05～09-07 回補期擷取，晚於所有決策時點），本修法對留言路徑
   的效果**只由合成測試證明**，真實資料無法驗證，此處零差異是預期
   現況，不是「已驗證留言路徑修復」的證據。
5. `compare_columns()` 的 `__right_only__`／`__left_only__` 皆須為空
   （449,263 列應與 `stock_prices` 完全對齊，段 1／段 2／段 3 皆已完成）。

================================================================================
寫入範圍
================================================================================
只寫 `article_count`／`sentiment_mean`／`sentiment_3d_ma`／
`sentiment_5d_ma`／`sentiment_lag_1`／`sentiment_lag_2`／
`bullishness_index`／`agreement_index`／`comment_volume_ratio`／
`comment_polarization`／`net_push_momentum`／`source_status`
（12 欄，`SENTIMENT_WRITE_COLUMNS`）；只寫預期影響集內的鍵（單一交易，
`execute_values` + `RETURNING`，不用 `cur.rowcount`——132 列會被 psycopg2
`execute_values` 預設 `page_size=100` 分頁，`rowcount` 只反映最後一頁，
段 1／段 3 已踩過這個陷阱）。**不碰標籤欄、不碰價格欄**——刻意用手寫
`UPDATE ... FROM (VALUES %s)`，不重用 `db_writer.upsert_ml_features()`
（後者是 `INSERT ... ON CONFLICT DO UPDATE`，會覆寫全部 27 欄）。

================================================================================
不做的事
================================================================================
- 不動 `stock_prices`（本腳本不含任何對該表的寫入敘述；`--write` 前後各
  量一次列數＋內容雜湊供外部稽核，見 `compute_stock_prices_fingerprint`）。
- 不動 `target_triple_barrier`／`label_reason`（RISK-027 修法不影響
  Triple-Barrier，段 3 不需重跑，此為文件與 DEC-037 已載明的結論，本腳本
  的段級核對僅覆核標籤欄計數未變，不重新計算標籤本身）。
"""
import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from scripts.verify.ug_g3_sb2a_stage2_baseline_comparison import (
    COMPARE_COLUMNS,
    compare_columns,
    fetch_all_prices,
    fetch_full_articles_and_mappings,
)

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")

TOTAL_ROWS_EXPECTED = 449263
EXISTING_LABEL_COUNTS = (410443, 38820)  # (count(target_triple_barrier), count(label_reason))

PRICE_DERIVED_COLUMNS = COMPARE_COLUMNS[:13]
SENTIMENT_WRITE_COLUMNS = COMPARE_COLUMNS[13:]
COMMENT_COLUMNS = ("comment_volume_ratio", "comment_polarization", "net_push_momentum")

assert len(PRICE_DERIVED_COLUMNS) == 13
assert len(SENTIMENT_WRITE_COLUMNS) == 12
assert set(COMMENT_COLUMNS) <= set(SENTIMENT_WRITE_COLUMNS)

# RED 測試 commit——`feature_aggregator.py` 內容於此 commit 與 RISK-027
# 修法前完全相同（該 commit 只新增測試檔，未觸碰 feature_aggregator.py）。
OLD_FEATURE_AGGREGATOR_COMMIT = "0da87d9"

_MAX_BACKUP_AGE_SECONDS = 24 * 3600


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


def _check_backup_or_exit(backup_path: str) -> None:
    from scripts.verify.ug_g3_sb2a_backfill_candidate_prices_gap import (
        _check_backup_or_exit as _impl,
    )
    _impl(backup_path)


# ==============================================================================
# 舊版 FeatureAggregator 的記憶體載入（不落地、不動 sys.path 上的正式模組）
# ==============================================================================

def load_old_feature_aggregator_class(commit: str = OLD_FEATURE_AGGREGATOR_COMMIT,
                                       repo_root: Path = None):
    """用 `git show <commit>:src/transform/feature_aggregator.py` 把修法前的
    `FeatureAggregator` 載入成一個獨立、不落地的模組物件，回傳其
    `FeatureAggregator` 類別。

    刻意用 `exec()` 建立獨立 module 命名空間，**不寫入任何暫存檔**、
    **不插入或修改 `sys.path`**——正式的 `src.transform.feature_aggregator`
    模組完全不受影響，可與新版同時在同一個 process 內使用。
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    # `-c safe.directory=<repo_root>` 是為了不依賴容器/主機是否已執行過
    # 一次性的 `git config --global --add safe.directory`——bind mount
    # 造成的檔案擁有者與容器內使用者不一致時，git 2.35+ 預設會拒絕在
    # 該目錄下操作（"detected dubious ownership"）。這裡明確用命令列
    # 覆寫，範圍僅限本次呼叫，不修改任何全域或本機 git 設定。
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}",
         "show", f"{commit}:src/transform/feature_aggregator.py"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`git show {commit}:src/transform/feature_aggregator.py` 失敗："
            f"{result.stderr}")
    src = result.stdout
    if "class FeatureAggregator" not in src:
        raise RuntimeError(
            f"commit {commit} 的 feature_aggregator.py 內容看起來不對"
            "（找不到 FeatureAggregator 類別定義），拒絕使用。")

    module_name = f"_risk027_old_feature_aggregator_{commit}"
    spec = importlib.util.spec_from_loader(module_name, loader=None)
    old_module = importlib.util.module_from_spec(spec)
    exec(compile(src, f"<git show {commit}:feature_aggregator.py>", "exec"),
         old_module.__dict__)
    return old_module.FeatureAggregator


# ==============================================================================
# 差異集計算（鍵 + 分岔欄位子集）
# ==============================================================================

def diff_keys_and_columns(diffs: dict, columns) -> dict:
    """把 `compare_columns()` 的輸出（`{欄名: DataFrame}`）攤平成
    `{(stock_id, trade_date): frozenset(分岔的欄名)}`。只看 `columns`
    參數列出的欄，忽略 `__left_only__`／`__right_only__`（那兩把由呼叫端
    另外處理，不屬於「哪些欄分岔」的問題）。
    """
    result = {}
    for col in columns:
        df = diffs.get(col)
        if df is None or df.empty:
            continue
        for sid, td in zip(df["stock_id"], df["trade_date"]):
            result.setdefault((sid, td), set()).add(col)
    return {k: frozenset(v) for k, v in result.items()}


def assert_expected_equals_actual(expected_diffs: dict, actual_diffs: dict):
    """斷言「舊版 vs 新版」的分岔（expected）與「新版 vs 庫」的分岔
    （actual）**逐鍵、逐欄集合完全相等**。回傳 `(ok, detail_dict)`；
    `ok=False` 時 `detail_dict` 列出鍵集合差異與逐鍵欄位集合不符者，
    供呼叫端印出排查、且**必須拒絕寫入**——不得因為只是「多一點/少一點」
    就自行判定可接受。
    """
    expected_keys = set(expected_diffs.keys())
    actual_keys = set(actual_diffs.keys())
    only_expected = expected_keys - actual_keys
    only_actual = actual_keys - expected_keys
    common = expected_keys & actual_keys
    column_mismatches = {
        k: (expected_diffs[k], actual_diffs[k])
        for k in common if expected_diffs[k] != actual_diffs[k]
    }
    ok = not only_expected and not only_actual and not column_mismatches
    return ok, {
        "only_in_expected": only_expected,
        "only_in_actual": only_actual,
        "column_mismatches": column_mismatches,
    }


# ==============================================================================
# 前置守衛
# ==============================================================================

def check_total_row_count(conn, expected=TOTAL_ROWS_EXPECTED):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM daily_ml_features;")
        n = cur.fetchone()[0]
    return n == expected, n


def check_label_counts(conn, expected=EXISTING_LABEL_COUNTS):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(target_triple_barrier), count(label_reason) "
            "FROM daily_ml_features;")
        counts = tuple(cur.fetchone())
    return counts == tuple(expected), counts


def fetch_existing_features_full(conn, columns) -> pd.DataFrame:
    """全表讀取（不限股票）——與段 3 的「全表兩欄重算 vs 庫內逐列相等」
    同一設計，本腳本比對範圍是 25 欄而非 2 欄。"""
    cols = ["trade_date", "stock_id"] + list(columns)
    df = pd.read_sql(
        "SELECT %s FROM daily_ml_features;" % ", ".join(cols), conn)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def compute_stock_prices_fingerprint(conn):
    """`stock_prices` 全表列數＋內容雜湊。本腳本不含任何對 `stock_prices`
    的寫入敘述——這裡是外部可稽核的證明，不是防禦措施；`--write` 前後
    各呼叫一次，斷言相等。"""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_prices;")
        n = cur.fetchone()[0]
        cur.execute(
            "SELECT md5(string_agg(t::text, '' ORDER BY stock_id, trade_date)) "
            "FROM stock_prices t;")
        checksum = cur.fetchone()[0]
    return n, checksum


def select_by_keys(df: pd.DataFrame, keys: set) -> pd.DataFrame:
    """向量化篩選 `(stock_id, trade_date)` 屬於 `keys` 集合的列——避免
    `DataFrame.apply(..., axis=1)` 在 449,263 列上逐列跑 Python callable。"""
    mask = pd.Series(list(zip(df["stock_id"], df["trade_date"])), index=df.index).isin(keys)
    return df.loc[mask]


# ==============================================================================
# 核心計算：預期影響集（機械算出）＋實際差異集，兩者斷言相等
# ==============================================================================

def compute_new_full_recompute(df_prices, df_articles, df_mapping, df_theme_mapping):
    """新版（現行、已修復）`FeatureAggregator` 對全量輸入重算，只需
    `generate_daily_features()`——本次比對範圍限於情緒／留言欄，
    不需要 `generate_target_labels()`（那是段 3 的範圍，不受 RISK-027 影響，
    段級守衛另外核對其計數不變即可，不必重新產生標籤欄本身）。"""
    from src.transform.feature_aggregator import FeatureAggregator
    agg = FeatureAggregator()
    df = agg.generate_daily_features(
        df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping)
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def compute_old_full_recompute(df_prices, df_articles, df_mapping, df_theme_mapping,
                                old_commit=OLD_FEATURE_AGGREGATOR_COMMIT):
    OldFeatureAggregator = load_old_feature_aggregator_class(old_commit)
    agg = OldFeatureAggregator()
    df = agg.generate_daily_features(
        df_prices, df_articles, df_mapping, df_theme_mapping=df_theme_mapping)
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def compute_expected_impact(df_new: pd.DataFrame, df_old: pd.DataFrame) -> dict:
    """舊版 vs 新版（同一份輸入）——分岔即為機械算出的預期影響集。
    回傳 `{(stock_id, trade_date): frozenset(分岔欄位)}`。"""
    diffs = compare_columns(df_new, df_old, SENTIMENT_WRITE_COLUMNS)
    if "__left_only__" in diffs or "__right_only__" in diffs:
        raise AssertionError(
            "舊版與新版對同一份輸入產生的 (stock_id, trade_date) 鍵集合不一致"
            "——兩版程式碼理應對同一份 stock_prices 產生完全相同的鍵集合"
            "（RISK-027 修法不改變哪些列存在，只改變情緒／留言欄的值）。"
            f" left_only={len(diffs.get('__left_only__', []))}，"
            f" right_only={len(diffs.get('__right_only__', []))}")
    return diff_keys_and_columns(diffs, SENTIMENT_WRITE_COLUMNS)


def compute_actual_diff(df_new: pd.DataFrame, df_existing: pd.DataFrame) -> dict:
    """新版 vs 現有 `daily_ml_features`——分岔即為實際差異集。"""
    diffs = compare_columns(df_new, df_existing, SENTIMENT_WRITE_COLUMNS)
    return diff_keys_and_columns(diffs, SENTIMENT_WRITE_COLUMNS)


# ==============================================================================
# 寫入
# ==============================================================================

_WRITE_TEMPLATE = (
    "(%s, %s::date, %s::integer, %s::numeric, %s::numeric, %s::numeric, "
    "%s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric, "
    "%s::numeric, %s::numeric, %s::text)"
)


def build_write_records(df_new: pd.DataFrame, impact_keys: set) -> list:
    """從 `df_new`（新版重算的記憶體結果）挑出 `impact_keys` 內的列，
    轉成 `execute_values` 用的 record tuple：
    `(stock_id, trade_date, article_count, sentiment_mean, sentiment_3d_ma,
    sentiment_5d_ma, sentiment_lag_1, sentiment_lag_2, bullishness_index,
    agreement_index, comment_volume_ratio, comment_polarization,
    net_push_momentum, source_status)`。NaN → `None`（`psycopg2` 對純數值
    欄位的 NaN 需要顯式轉 `None` 才會寫成 SQL NULL，不會被送成非法數值
    ——沿用 `db_writer.upsert_ml_features()` 已驗證的作法）。
    """
    subset = select_by_keys(df_new, impact_keys)
    cols = ["stock_id", "trade_date"] + list(SENTIMENT_WRITE_COLUMNS)
    records = []
    for row in subset[cols].itertuples(index=False, name=None):
        stock_id, trade_date, *values = row
        article_count = values[0]
        rest = values[1:]
        article_count_val = None if pd.isna(article_count) else int(article_count)
        rest_vals = [None if pd.isna(v) else v for v in rest]
        records.append((stock_id, trade_date, article_count_val, *rest_vals))
    return records


def write_impact_rows(conn, records: list) -> list:
    """`execute_values` 批次 `UPDATE ... FROM (VALUES %s) ... RETURNING`，
    只執行、不 commit（呼叫端負責 commit 前核對）。回傳 `RETURNING`
    收集到的 `(stock_id, trade_date)` 鍵列表——**不用 `cur.rowcount`**
    （132 列會被 `execute_values` 預設 `page_size=100` 分頁，`rowcount`
    只反映最後一頁，段 1／段 3 已踩過這個陷阱）。"""
    set_clause = ",\n            ".join(
        f"{c} = v.{c}" for c in SENTIMENT_WRITE_COLUMNS)
    value_cols = ", ".join(SENTIMENT_WRITE_COLUMNS)
    query = f"""
        UPDATE daily_ml_features AS d
        SET {set_clause}
        FROM (VALUES %s) AS v(stock_id, trade_date, {value_cols})
        WHERE d.stock_id = v.stock_id AND d.trade_date = v.trade_date
        RETURNING d.stock_id, d.trade_date;
    """
    with conn.cursor() as cur:
        returned = execute_values(
            cur, query, records, template=_WRITE_TEMPLATE, fetch=True)
    return [(sid, td) for sid, td in returned]


# ==============================================================================
# 揭露性輸出
# ==============================================================================

def print_impact_preview(df_new: pd.DataFrame, impact_keys: set) -> None:
    print(f"\n=== 預期影響集逐列舊→新值（共 {len(impact_keys)} 鍵）===")
    cols = ["stock_id", "trade_date"] + list(SENTIMENT_WRITE_COLUMNS)
    subset = select_by_keys(df_new, impact_keys)[cols].sort_values(["stock_id", "trade_date"])
    print(subset.to_string(index=False))


def print_stock_breakdown(impact_keys: set) -> None:
    by_stock = {}
    for sid, _ in impact_keys:
        by_stock[sid] = by_stock.get(sid, 0) + 1
    print(f"\n=== 影響集逐股票列數（{len(by_stock)} 檔）===")
    for sid, n in sorted(by_stock.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {sid}: {n}")


# ==============================================================================
# main
# ==============================================================================

def main(write: bool, backup_path: str) -> None:
    if write and not backup_path:
        print("ERROR：--write 必須同時提供 --backup <path>（RISK-013 第二項協議機械化檢查）")
        sys.exit(1)
    if write:
        _check_backup_or_exit(backup_path)

    db_config = _load_db_config()
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user, inet_server_port();")
    conn_info = cur.fetchone()
    current_db = conn_info[0]
    print("CONN CHECK:", conn_info)

    print("\n=== 前置守衛 ===")
    ok_rows, actual_rows = check_total_row_count(conn)
    ok_labels, actual_labels = check_label_counts(conn)
    print(f"daily_ml_features 總列數：{actual_rows}（預期 {TOTAL_ROWS_EXPECTED}）"
          f"[{'PASS' if ok_rows else 'FAIL'}]")
    print(f"標籤現況：{actual_labels}（預期 {EXISTING_LABEL_COUNTS}）"
          f"[{'PASS' if ok_labels else 'FAIL'}]")
    if not (ok_rows and ok_labels):
        print("ERROR：真實庫現況與常數不符——拒絕執行（唯讀預覽與 --write 皆拒絕）。")
        conn.close()
        sys.exit(1)

    print("\n讀取全量 stock_prices／market_articles／entity_mapping／theme_stock_mapping...")
    df_prices = fetch_all_prices(conn)
    df_articles, df_mapping, df_theme_mapping = fetch_full_articles_and_mappings(conn)

    t0 = time.time()
    df_new = compute_new_full_recompute(df_prices, df_articles, df_mapping, df_theme_mapping)
    t_new = time.time() - t0
    print(f"新版（現行）全量重算耗時：{t_new:.2f} 秒（{df_new['stock_id'].nunique()} 檔、"
          f"{len(df_new)} 列）")

    t0 = time.time()
    df_old = compute_old_full_recompute(df_prices, df_articles, df_mapping, df_theme_mapping)
    t_old = time.time() - t0
    print(f"舊版（commit {OLD_FEATURE_AGGREGATOR_COMMIT}）全量重算耗時：{t_old:.2f} 秒")

    expected_diffs = compute_expected_impact(df_new, df_old)
    print(f"\n預期影響集（舊版 vs 新版，機械算出）：{len(expected_diffs)} 鍵")

    df_existing = fetch_existing_features_full(conn, COMPARE_COLUMNS)
    all_diffs = compare_columns(df_new, df_existing, COMPARE_COLUMNS)

    if "__right_only__" in all_diffs:
        print(f"\nERROR：daily_ml_features 有 {len(all_diffs['__right_only__'])} 列孤兒列"
              "（重算生不出對應列）——拒絕執行。")
        conn.close()
        sys.exit(1)
    if "__left_only__" in all_diffs:
        print(f"\nERROR：重算多出 {len(all_diffs['__left_only__'])} 個未預期的鍵"
              "——拒絕執行。")
        conn.close()
        sys.exit(1)

    price_violations = {c: all_diffs[c] for c in PRICE_DERIVED_COLUMNS if c in all_diffs}
    if price_violations:
        print("\nERROR：價格衍生欄新版重算 vs 庫出現差異（RISK-027 修法不應影響這條路徑）"
              "——拒絕執行：")
        for c, df in price_violations.items():
            print(f"  {c}: {len(df)} 列")
        conn.close()
        sys.exit(1)

    comment_violations = {c: all_diffs[c] for c in COMMENT_COLUMNS if c in all_diffs}
    if comment_violations:
        print("\nERROR：留言三欄新版重算 vs 庫出現差異（真實資料預期零差異，"
              "見模組 docstring 前置守衛第 4 點）——拒絕執行：")
        for c, df in comment_violations.items():
            print(f"  {c}: {len(df)} 列")
        conn.close()
        sys.exit(1)

    actual_diffs = compute_actual_diff(df_new, df_existing)
    ok, detail = assert_expected_equals_actual(expected_diffs, actual_diffs)
    print(f"\n預期影響集 vs 實際差異集（新版 vs 庫）相等：{'是' if ok else '否'}"
          f"[{'PASS' if ok else 'FAIL'}]")
    if not ok:
        print("ERROR：預期影響集與實際差異集不相等——拒絕執行。")
        if detail["only_in_expected"]:
            print(f"  只在預期集（舊版 vs 新版有差異，但庫已與新版一致）："
                  f"{sorted(detail['only_in_expected'])[:20]}")
        if detail["only_in_actual"]:
            print(f"  只在實際差異集（庫與新版不同，但舊版 vs 新版無差異——"
                  f"代表庫裡有本修法以外的漂移）：{sorted(detail['only_in_actual'])[:20]}")
        if detail["column_mismatches"]:
            print(f"  逐鍵欄位集合不符（{len(detail['column_mismatches'])} 鍵）："
                  f"{list(detail['column_mismatches'].items())[:10]}")
        conn.close()
        sys.exit(1)

    impact_keys = set(actual_diffs.keys())

    print_stock_breakdown(impact_keys)
    print_impact_preview(df_new, impact_keys)

    if not write:
        print("\n【唯讀模式】僅計算與唯讀查詢，不執行任何 UPDATE。"
              "加 --write --backup <path> 執行實際回補。")
        conn.close()
        return

    n_before, checksum_before = compute_stock_prices_fingerprint(conn)
    print(f"\nstock_prices 寫入前指紋：{n_before} 列，md5={checksum_before}")

    typed = input(
        f"即將對資料庫 '{current_db}' 執行 {len(impact_keys)} 列 UPDATE"
        f"（12 個情緒／留言欄）。請輸入資料庫名稱以確認：")
    if typed != current_db:
        print(f"ERROR：輸入 '{typed}' 與目標資料庫 '{current_db}' 不符，拒絕執行。")
        conn.close()
        sys.exit(1)

    records = build_write_records(df_new, impact_keys)
    returned_keys = set(write_impact_rows(conn, records))

    print("\n=== commit 前核對 ===")
    all_ok = True

    ok_a = returned_keys == impact_keys
    print(f"(a) RETURNING 鍵集合＝預期影響集：{'PASS' if ok_a else 'FAIL'}"
          f"（RETURNING {len(returned_keys)} 鍵，預期 {len(impact_keys)} 鍵）")
    all_ok = all_ok and ok_a

    # 逐列讀回：SQL 端用 stock_id = ANY(...) 縮小範圍（避免整表讀回），
    # 精確的 (stock_id, trade_date) 交集在 Python 端用 impact_keys 過濾——
    # psycopg2 對 (stock_id, trade_date) IN ((...), (...)) 這種複合鍵 IN
    # 子句沒有原生的 execute_values 支援，兩階段過濾比手刻該子句更不易出錯。
    df_readback = pd.read_sql(
        "SELECT stock_id, trade_date, %s FROM daily_ml_features "
        "WHERE stock_id = ANY(%%(ids)s);" % ", ".join(SENTIMENT_WRITE_COLUMNS),
        conn, params={"ids": list({sid for sid, _ in impact_keys})})
    df_readback["trade_date"] = pd.to_datetime(df_readback["trade_date"]).dt.date
    df_readback_impacted = select_by_keys(df_readback, impact_keys)
    readback_diffs = compare_columns(df_new, df_readback_impacted, SENTIMENT_WRITE_COLUMNS)
    readback_mismatches = {c: readback_diffs[c] for c in SENTIMENT_WRITE_COLUMNS
                            if c in readback_diffs}
    ok_b = not readback_mismatches
    print(f"(b) 逐列讀回與記憶體 df_new 相等（交易內）：{'PASS' if ok_b else 'FAIL'}")
    if not ok_b:
        for c, df in readback_mismatches.items():
            print(f"    {c}: {len(df)} 列不符")
    all_ok = all_ok and ok_b

    ok_c, labels_after_write = check_label_counts(conn)
    print(f"(c) 標籤欄計數未變：{labels_after_write}（預期 {EXISTING_LABEL_COUNTS}）"
          f"[{'PASS' if ok_c else 'FAIL'}]")
    all_ok = all_ok and ok_c

    if not all_ok:
        conn.rollback()
        print("\nFAIL：commit 前核對未通過——已 rollback，未寫入任何資料。")
        conn.close()
        sys.exit(1)

    conn.commit()
    print("\ncommit 完成。")

    print("\n=== 段級核對（commit 後）===")
    seg_ok = True

    df_existing_after = fetch_existing_features_full(conn, COMPARE_COLUMNS)
    final_diffs = compare_columns(df_new, df_existing_after, COMPARE_COLUMNS)
    remaining = {c: final_diffs[c] for c in COMPARE_COLUMNS if c in final_diffs}
    ok_d = not remaining and "__left_only__" not in final_diffs and "__right_only__" not in final_diffs
    print(f"1. 全表 25 欄重算 vs 庫：{'PASS' if ok_d else 'FAIL'}"
          f"（不符欄位：{list(remaining.keys())}）")
    seg_ok = seg_ok and ok_d

    ok_e, labels_final = check_label_counts(conn)
    print(f"2. 標籤欄計數：{labels_final}（預期 {EXISTING_LABEL_COUNTS}）"
          f"[{'PASS' if ok_e else 'FAIL'}]")
    seg_ok = seg_ok and ok_e

    n_after, checksum_after = compute_stock_prices_fingerprint(conn)
    ok_f = (n_after, checksum_after) == (n_before, checksum_before)
    print(f"3. stock_prices 未變：{n_after} 列，md5={checksum_after}"
          f"（寫入前 {n_before} 列，md5={checksum_before}）[{'PASS' if ok_f else 'FAIL'}]")
    seg_ok = seg_ok and ok_f

    conn.close()

    if not seg_ok:
        print("\nFAIL：段級核對未通過——資料已 commit，須人工排查，不得自動回滾已提交的資料。")
        sys.exit(1)
    print("\n全部核對通過。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", default=None)
    args = parser.parse_args()
    main(write=args.write, backup_path=args.backup)
