# -*- coding: utf-8 -*-
"""§0.5 #40 段 A：PTT 關鍵字擴展後情緒覆蓋率的離線重新比對（唯讀、零網路）。

Gate A 提案：doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md §3.1

本腳本只回答一個問題：若把 `entity_mapping`＋`theme_stock_mapping` 的全部關鍵字
聯集拿去重新比對既有 1,349 篇 PTT 文章的標題，覆蓋率上限（嚴格下界，見提案 §2.2）
是多少。**這是既有語料內的重新比對，不代表向 PTT 重新取數後的真正上限**——
真正上限需要段 B（頁面速率探測 + 全量看板掃頁）才能量到。

連線參數全走環境變數，不在本檔留下任何字面連線值（CHAL-008 教訓）。
全程只 `SELECT`，不 `INSERT`/`UPDATE`，不連線 PTT，不修改 `tracking_keywords`、
不寫入任何文章、不重算任何面板。

**三段式覆蓋率拆解（段 A 複核第一輪追加）**：凍結面板的 `article_count>0`（683／
2.79%）是用 09-12 當時的 `entity_mapping`／`theme_stock_mapping` 算出來的；本腳本
讀的是**今天**的映射表，兩者之間 `theme_stock_mapping` 已有列因每日 ETL 的 AI 探索
而新增／更新。若直接拿今天算出的「全關鍵字」覆蓋率去跟凍結基準比，差異裡會混入
「映射表漂移」與「關鍵字擴展」兩個不同成因。本腳本因此把**現行口徑（只用
`fetch_keyword`）也推過同一條管線重算一次**，三段式比較：

    凍結基準（09-12 映射表） → 現行口徑・今日映射表重算 → 全關鍵字・今日映射表重算
         683 / 2.79%                    846 / 3.46%                1005 / 4.11%
                    └── 映射表漂移 +163 ──┘         └── 關鍵字擴展 +159 ──┘

「現行口徑・今日映射表重算」同時是重用 `assign_trading_days_per_stock` 的正確性
證據：它對凍結基準的 683 格是**零遺漏的父集**（intersection=683，only-in-frozen=0）。

兩種主／次口徑刻意分開輸出，不得混用（提案 §3.1 第 4 點）：
- `coverage_raw_hit_*`：與面板 `article_count > 0` 同語意，是**主要比較對象**。
- `coverage_5d_ma_proxy_*`：對新命中套用與 `sentiment_5d_ma` 相同的滾動視窗機制
  （`groupby(stock_id).rolling(window=5, min_periods=1)`，見
  `src/transform/feature_aggregator.py:803-804`），**只是同一套視窗機制的類比**，
  不是真正重跑情緒分析——本腳本沒有任何情緒分數，只有「該股該日是否有命中」
  的二元指標。次要／選配指標，報告時必須與主要指標分開標示口徑。
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2

from src.transform.feature_aggregator import assign_trading_days_per_stock, normalize_cutoff_time

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")

PANEL_PATH = (
    "/workspaces/Database_Backups/Stock_Prediction_System2/ml_panels/"
    "panel_target_up_down_20260912.parquet"
)
PANEL_SHA256_EXPECTED = (
    "39dc6b8e6160add20f39a7265bad04de50c76199fa7ab81b979a7aabeabbd014"
)
PANEL_WINDOW_START = "2026-01-01"


def _derive_panel_freeze_date(panel_path: str) -> str:
    """面板凍結日期一律從 `PANEL_PATH` 的檔名反查，不另立手打常數（複核第二輪訂正）。

    上一版把日期手打成 `PANEL_FREEZE_DATE = "2026-09-12"`，註解宣稱「取自檔名」，
    但沒有任何程式碼真的從 `PANEL_PATH` 讀出它——哪天 `PANEL_PATH` 換成另一份面板，
    這個常數會原地不動，而 `theme_stock_mapping` 的漂移判定就會對錯凍結時點。
    """
    m = re.search(r"(\d{8})", Path(panel_path).name)
    if not m:
        raise RuntimeError(f"無法從面板檔名反查凍結日期：{panel_path}")
    raw = m.group(1)
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


PANEL_FREEZE_DATE = _derive_panel_freeze_date(PANEL_PATH)

OUTPUT_PATH = Path("doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_offline_rematch.json")

CUTOFF_TIME = "15:30:00"  # 與 feature_aggregator 預設值一致


def _load_db_config() -> dict:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"缺少必要環境變數：{missing}")
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def verify_panel_sha256(path: str, expected: str) -> str:
    """開檔前核對 sha256，不符即中止（提案 §3.1 第 3 點）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"面板 sha256 不符，中止（Gate 3 已凍結交付物不得在未核對下讀取）：\n"
            f"  expected={expected}\n  actual  ={actual}\n  path    ={path}"
        )
    return actual


def load_keyword_stock_map(conn, panel_freeze_date: str):
    """回傳 (kw2stocks, drift_theme_keys, n_theme_total, n_theme_drift, n_theme_on_freeze_date)。

    `drift_theme_keys` 是 `theme_stock_mapping` 中 `updated_at` **日期**晚於
    `panel_freeze_date` 的 (theme_keyword, stock_id) 集合——這些列在凍結面板
    當時的映射表裡不存在，是之後每日 ETL 的 AI 探索寫入的（段 A 複核第一輪）。

    ⚠ 邊界警告（複核第二輪追加）：比較用的是**日期**（`pd.Timestamp(panel_freeze_date)`
    只有日期、無時刻，等同該日 00:00），不是面板實際產生的**時刻**。本次資料集
    `updated_at` 恰落在凍結日當天（`2026-09-12`）的列數為 0（`n_theme_on_freeze_date`
    可驗證此值），所以這次沒有誤判；但換一份資料集，若凍結當天真的有映射更新，
    這個以日期為粒度的比較就可能把「凍結之前」的更新誤判為「凍結之後」（或反之），
    需要換成面板實際生成的時刻而非只取日期才能消除這個邊界。
    """
    entity = pd.read_sql("SELECT keyword, stock_id FROM entity_mapping", conn)
    theme = pd.read_sql(
        "SELECT theme_keyword AS keyword, stock_id, updated_at FROM theme_stock_mapping", conn
    )
    freeze_ts = pd.Timestamp(panel_freeze_date)

    kw2stocks: dict[str, set] = {}
    drift_theme_keys: set = set()
    n_theme_on_freeze_date = 0
    for kw, sid in zip(entity["keyword"], entity["stock_id"]):
        kw2stocks.setdefault(kw, set()).add(sid)
    for kw, sid, updated_at in zip(theme["keyword"], theme["stock_id"], theme["updated_at"]):
        kw2stocks.setdefault(kw, set()).add(sid)
        ua = pd.Timestamp(updated_at)
        if ua.normalize() == freeze_ts.normalize():
            n_theme_on_freeze_date += 1
        if ua > freeze_ts:
            drift_theme_keys.add((kw, sid))

    return kw2stocks, drift_theme_keys, len(theme), len(drift_theme_keys), n_theme_on_freeze_date


def load_articles(conn) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT article_id, title, fetch_keyword, post_time FROM market_articles", conn
    )
    df["post_time"] = pd.to_datetime(df["post_time"], errors="coerce")
    return df


def build_hit_rows(articles: pd.DataFrame, kw2stocks: dict, drift_theme_keys: set, mode: str):
    """建構 (article_id, stock_id, post_time, via_drift_theme) 列。

    `mode="current"`：只用每篇文章自己的 `fetch_keyword`（提案 §3.1 第 2 點的「現行」口徑）。
    `mode="full"`：對標題做全關鍵字聯集的子字串比對（「全關鍵字」口徑）。

    `via_drift_theme` 標記該列命中是否**至少部分**經過凍結後才新增的 theme 映射
    ——同一篇文章命中同一檔股票可能同時透過多個關鍵字（含新舊映射），任一為
    drift 即標記 True，供 §drift_vs_expansion 的證據拆解使用。
    """
    rows = []
    for row in articles.itertuples(index=False):
        if pd.isna(row.post_time):
            continue
        title = row.title or ""

        if mode == "current":
            hit_stocks = kw2stocks.get(row.fetch_keyword, set())
            hit_kws_by_stock = {sid: {row.fetch_keyword} for sid in hit_stocks}
        elif mode == "full":
            hit_kws_by_stock: dict = {}
            for kw, stocks in kw2stocks.items():
                if kw and kw in title:
                    for sid in stocks:
                        hit_kws_by_stock.setdefault(sid, set()).add(kw)
        else:
            raise ValueError(f"未知 mode：{mode}")

        for sid, kws in hit_kws_by_stock.items():
            via_drift = any((kw, sid) in drift_theme_keys for kw in kws)
            rows.append(
                {
                    "article_id": row.article_id,
                    "stock_id": sid,
                    "post_time": row.post_time,
                    "via_drift_theme": via_drift,
                }
            )
    return pd.DataFrame(rows, columns=["article_id", "stock_id", "post_time", "via_drift_theme"])


def compute_date_level_pairs(current_hits: pd.DataFrame, full_hits: pd.DataFrame) -> dict:
    """提案 §3.1 第 2 點：重現 §2.1 的兩種口徑，配對單位為 (stock_id, post_time 的日曆日期)。

    這一段刻意**不**經過交易日 roll-forward——它的目的是跟 §2.1 已用原生 SQL
    獨立驗算過的 1,502/30、1,714/86 做一致性核對，不是套進面板視窗（那是
    `compute_panel_window_coverage` 的職責，兩者的「日期」語意不同，不可混用）。
    """
    def _to_pairs(df):
        pairs = set(zip(df["stock_id"], df["post_time"].dt.date))
        return len(pairs), len(set(df["stock_id"]))

    cur_pairs, cur_stocks = _to_pairs(current_hits)
    full_pairs, full_stocks = _to_pairs(full_hits)
    return {
        "current_pairs": cur_pairs,
        "current_stocks": cur_stocks,
        "full_pairs": full_pairs,
        "full_stocks": full_stocks,
    }


def map_hits_to_panel(hit_rows: pd.DataFrame, panel: pd.DataFrame, trading_days_by_stock: dict):
    """把一批 hit_rows 經 roll-forward 映射進面板交易日，回傳映射結果與丟棄拆解。"""
    panel_stock_universe = set(panel["stock_id"].unique())

    if hit_rows.empty:
        empty = hit_rows.copy()
        empty["trade_date"] = pd.Series(dtype="object")
        return empty, {
            "not_in_panel_458_universe": 0,
            "stocks_not_in_panel_458_universe": [],
            "in_universe_after_global_last_trade_date": 0,
            "in_universe_after_global_last_trade_date_cutoff_boundary": 0,
            "in_universe_after_own_calendar_last_not_global": 0,
            "in_universe_before_own_calendar_first": 0,
        }

    not_in_universe_mask = ~hit_rows["stock_id"].isin(panel_stock_universe)
    stocks_not_in_panel_universe = sorted(
        hit_rows.loc[not_in_universe_mask, "stock_id"].unique().tolist()
    )
    in_universe_rows = hit_rows.loc[~not_in_universe_mask].reset_index(drop=True)

    mapped = assign_trading_days_per_stock(in_universe_rows, trading_days_by_stock, cutoff_time=CUTOFF_TIME)

    dropped_idx = in_universe_rows.set_index(["article_id", "stock_id"]).index.difference(
        mapped.set_index(["article_id", "stock_id"]).index
    )
    dropped = in_universe_rows.set_index(["article_id", "stock_id"]).loc[dropped_idx].reset_index()

    global_last = panel["trade_date"].max()
    cutoff_t = normalize_cutoff_time(CUTOFF_TIME)

    n_after_global = 0
    n_after_global_cutoff_boundary = 0
    n_after_own_last_not_global = 0
    n_before_own_first = 0
    for row in dropped.itertuples(index=False):
        days = trading_days_by_stock.get(row.stock_id, [])
        if not days:
            continue
        own_last, own_first = max(days), min(days)
        post_date = row.post_time.date()
        if row.post_time.time() <= cutoff_t:
            eff_date = post_date
        else:
            eff_date = (pd.Timestamp(post_date) + pd.Timedelta(days=1)).date()

        if eff_date > global_last:
            n_after_global += 1
            if post_date == global_last and row.post_time.time() > cutoff_t:
                n_after_global_cutoff_boundary += 1
        elif eff_date > own_last:
            n_after_own_last_not_global += 1
        elif eff_date < own_first:
            n_before_own_first += 1

    return mapped, {
        "not_in_panel_458_universe": int(not_in_universe_mask.sum()),
        "stocks_not_in_panel_458_universe": stocks_not_in_panel_universe,
        "in_universe_after_global_last_trade_date": n_after_global,
        "in_universe_after_global_last_trade_date_cutoff_boundary": n_after_global_cutoff_boundary,
        "in_universe_after_own_calendar_last_not_global": n_after_own_last_not_global,
        "in_universe_before_own_calendar_first": n_before_own_first,
    }


def coverage_from_mapped_pairs(mapped: pd.DataFrame, panel_subset: pd.DataFrame):
    """算主要口徑（raw hit）與次要口徑（5d-ma 視窗機制類比）在面板窗口內的覆蓋數。"""
    n_subset = len(panel_subset)
    mapped_pairs = set(zip(mapped["stock_id"], mapped["trade_date"])) if not mapped.empty else set()

    subset_pairs = list(zip(panel_subset["stock_id"], panel_subset["trade_date"]))
    hit_mask = [p in mapped_pairs for p in subset_pairs]
    n_raw_hit = sum(hit_mask)

    pairs_df = pd.DataFrame(list(mapped_pairs), columns=["stock_id", "trade_date"])
    if not pairs_df.empty:
        pairs_df["hit"] = 1.0
    return {
        "n_raw_hit": n_raw_hit,
        "pct_raw_hit": round(n_raw_hit / n_subset * 100, 2) if n_subset else None,
        "mapped_pairs": mapped_pairs,
        "hit_pairs_in_subset": [p for p, h in zip(subset_pairs, hit_mask) if h],
    }


def compute_5d_ma_proxy(mapped_pairs: set, panel: pd.DataFrame, panel_subset_len: int):
    pairs_df = pd.DataFrame(list(mapped_pairs), columns=["stock_id", "trade_date"])
    pairs_df["hit"] = 1.0
    panel_full = panel.merge(pairs_df, on=["stock_id", "trade_date"], how="left")
    panel_full = panel_full.sort_values(["stock_id", "trade_date"]).reset_index(drop=True)
    panel_full["hit_5d_ma"] = panel_full.groupby("stock_id")["hit"].transform(
        lambda x: x.rolling(window=5, min_periods=1).mean()
    )
    panel_full_subset = panel_full[
        panel_full["trade_date"] >= pd.Timestamp(PANEL_WINDOW_START).date()
    ]
    n_5d_ma_hit = int(panel_full_subset["hit_5d_ma"].notna().sum())
    return {
        "n_5d_ma_hit": n_5d_ma_hit,
        "pct_5d_ma_hit": round(n_5d_ma_hit / panel_subset_len * 100, 2) if panel_subset_len else None,
    }


def main():
    print(f"[1/6] 核對面板 sha256：{PANEL_PATH}")
    actual_sha = verify_panel_sha256(PANEL_PATH, PANEL_SHA256_EXPECTED)
    print(f"      OK，sha256={actual_sha}")

    print("[2/6] 連線資料庫，讀取 entity_mapping／theme_stock_mapping／market_articles（唯讀）")
    conn = psycopg2.connect(**_load_db_config())
    try:
        (
            kw2stocks,
            drift_theme_keys,
            n_theme_total,
            n_theme_drift,
            n_theme_on_freeze_date,
        ) = load_keyword_stock_map(conn, PANEL_FREEZE_DATE)
        articles = load_articles(conn)
    finally:
        conn.close()
    n_keyword_union = len(kw2stocks)
    print(f"      關鍵字聯集：{n_keyword_union}；文章數：{len(articles)}")
    print(
        f"      theme_stock_mapping：{n_theme_total} 列，其中 {n_theme_drift} 列晚於面板凍結日 "
        f"{PANEL_FREEZE_DATE}（恰落在凍結當天的列數：{n_theme_on_freeze_date}）"
    )

    print("[3/6] 建構命中列（現行口徑／全關鍵字口徑，皆含 via_drift_theme 標記）")
    current_hits = build_hit_rows(articles, kw2stocks, drift_theme_keys, mode="current")
    full_hits = build_hit_rows(articles, kw2stocks, drift_theme_keys, mode="full")

    print("[4/6] §2.1 一致性核對（post_time 日曆日期配對，未經 roll-forward）")
    date_level = compute_date_level_pairs(current_hits, full_hits)
    print(f"      現行：{date_level['current_pairs']} pairs / {date_level['current_stocks']} stocks")
    print(f"      全關鍵字：{date_level['full_pairs']} pairs / {date_level['full_stocks']} stocks")

    print(f"[5/6] 讀取面板（唯讀，sha256 已核對）：{PANEL_PATH}")
    panel = pd.read_parquet(PANEL_PATH)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"]).dt.date
    trading_days_by_stock = (
        panel.groupby("stock_id")["trade_date"].apply(lambda s: sorted(set(s))).to_dict()
    )
    panel_subset = panel[panel["trade_date"] >= pd.Timestamp(PANEL_WINDOW_START).date()].copy()
    n_subset = len(panel_subset)

    mapped_current, dropped_current = map_hits_to_panel(current_hits, panel, trading_days_by_stock)
    mapped_full, dropped_full = map_hits_to_panel(full_hits, panel, trading_days_by_stock)

    cov_current = coverage_from_mapped_pairs(mapped_current, panel_subset)
    cov_full = coverage_from_mapped_pairs(mapped_full, panel_subset)

    ma_current = compute_5d_ma_proxy(cov_current["mapped_pairs"], panel, n_subset)
    ma_full = compute_5d_ma_proxy(cov_full["mapped_pairs"], panel, n_subset)

    baseline_raw_hit = int((panel_subset["article_count"] > 0).sum())
    baseline_raw_hit_pct = round(baseline_raw_hit / n_subset * 100, 2) if n_subset else None
    baseline_5d_ma = int(panel_subset["sentiment_5d_ma"].notna().sum())
    baseline_5d_ma_pct = round(baseline_5d_ma / n_subset * 100, 2) if n_subset else None

    # 凍結基準 vs 現行口徑重算：驗證 assign_trading_days_per_stock 對凍結面板零遺漏地重現
    frozen_pairs = set(
        zip(panel_subset.loc[panel_subset["article_count"] > 0, "stock_id"],
            panel_subset.loc[panel_subset["article_count"] > 0, "trade_date"])
    )
    current_recompute_pairs = set(cov_current["hit_pairs_in_subset"])
    only_in_frozen = frozen_pairs - current_recompute_pairs
    only_in_current_recompute = current_recompute_pairs - frozen_pairs

    print(
        f"[6/6] 主要口徑：凍結基準 {baseline_raw_hit}({baseline_raw_hit_pct}%) → "
        f"現行口徑重算 {cov_current['n_raw_hit']}({cov_current['pct_raw_hit']}%) → "
        f"全關鍵字重算 {cov_full['n_raw_hit']}({cov_full['pct_raw_hit']}%)"
    )

    # 逐股票明細（提案 §3.1 第 5 點）：全關鍵字口徑的每檔命中日數，並標註 via_drift_theme。
    # mapped_full 是 in_universe_rows（已含 via_drift_theme）經 assign_trading_days_per_stock
    # 只新增 trade_date 欄、其餘欄位原樣保留而來，不需要再合併一次。
    full_hit_pairs_in_subset = set(cov_full["hit_pairs_in_subset"])
    mapped_full_with_flag = mapped_full
    per_stock_counts: dict[str, int] = {}
    per_stock_drift_days: dict[str, int] = {}
    for sid, td in full_hit_pairs_in_subset:
        per_stock_counts[sid] = per_stock_counts.get(sid, 0) + 1
        rows_here = mapped_full_with_flag[
            (mapped_full_with_flag["stock_id"] == sid) & (mapped_full_with_flag["trade_date"] == td)
        ]
        if not rows_here.empty and bool(rows_here["via_drift_theme"].any()):
            per_stock_drift_days[sid] = per_stock_drift_days.get(sid, 0) + 1

    print(f"寫出 evidence JSON：{OUTPUT_PATH}")
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/verify/measure_ptt_keyword_coverage_offline.py",
        "gate_a_proposal": "doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md",
        "read_only": True,
        "network_requests_to_ptt": 0,
        "panel_path": PANEL_PATH,
        "panel_sha256": actual_sha,
        "panel_freeze_date": PANEL_FREEZE_DATE,
        "n_keyword_union": n_keyword_union,
        "n_articles": len(articles),
        "date_level_pairs": {
            "current": {"pairs": date_level["current_pairs"], "stocks": date_level["current_stocks"]},
            "full_keyword_rematch": {"pairs": date_level["full_pairs"], "stocks": date_level["full_stocks"]},
            "note": (
                "配對單位為 (stock_id, post_time 日曆日期)，未經交易日 roll-forward；"
                "用於與提案 §2.1 已用原生 SQL 獨立驗算過的 1,502/30、1,714/86 做一致性核對，"
                "不是套進面板視窗後的覆蓋率（那是 panel_window_coverage／drift_vs_expansion 的職責）。"
            ),
        },
        "panel_window_coverage": {
            "panel_subset_rows": n_subset,
            "coverage_raw_hit": {
                "n_hit": cov_full["n_raw_hit"],
                "pct": cov_full["pct_raw_hit"],
                "baseline_article_count_gt0_frozen_panel": baseline_raw_hit,
                "baseline_pct": baseline_raw_hit_pct,
                "note": (
                    "主要比較對象；與 article_count>0 同語意（提案 §3.1 第 4 點）。"
                    "baseline 是 09-12 凍結面板的值，與本欄用今日映射表重算的值之間"
                    "混有映射表漂移與關鍵字擴展兩種成因，正確拆解見 drift_vs_expansion。"
                ),
            },
            "coverage_5d_ma_proxy": {
                "n_hit": ma_full["n_5d_ma_hit"],
                "pct": ma_full["pct_5d_ma_hit"],
                "baseline_sentiment_5d_ma_notna_frozen_panel": baseline_5d_ma,
                "baseline_pct": baseline_5d_ma_pct,
                "note": (
                    "次要／選配指標，僅套用與 sentiment_5d_ma 相同的滾動視窗機制"
                    "（rolling(window=5, min_periods=1) on binary hit indicator），"
                    "不是重跑情緒分析；不得與主要指標混用同一數字比較；"
                    "baseline 同樣是凍結值，漂移／擴展拆解見 drift_vs_expansion。"
                ),
            },
            "n_full_hit_rows_dropped": {
                "total": sum(v for k, v in dropped_full.items() if k in (
                    "not_in_panel_458_universe",
                    "in_universe_after_global_last_trade_date",
                    "in_universe_after_own_calendar_last_not_global",
                    "in_universe_before_own_calendar_first",
                )),
                "not_in_panel_458_universe": dropped_full["not_in_panel_458_universe"],
                "stocks_not_in_panel_458_universe": dropped_full["stocks_not_in_panel_458_universe"],
                "in_universe_after_global_last_trade_date": dropped_full["in_universe_after_global_last_trade_date"],
                "in_universe_after_global_last_trade_date_cutoff_boundary": dropped_full[
                    "in_universe_after_global_last_trade_date_cutoff_boundary"
                ],
                "in_universe_after_own_calendar_last_not_global": dropped_full[
                    "in_universe_after_own_calendar_last_not_global"
                ],
                "in_universe_before_own_calendar_first": dropped_full["in_universe_before_own_calendar_first"],
                "note": (
                    "三種互斥原因（段 A 複核第一輪訂正，不再合併為「多半」）："
                    "(1) not_in_panel_458_universe——命中股票代碼本身不在 458 檔面板宇宙內"
                    "（例：美股代碼、非本專案追蹤範圍個股），定義上不可能貢獻面板覆蓋率，不是量測缺陷；"
                    "(2) in_universe_after_global_last_trade_date——該篇文章 roll-forward 後的"
                    "有效日期晚於面板全域最後交易日（2026-09-04），其中"
                    "in_universe_after_global_last_trade_date_cutoff_boundary 是恰好卡在最後一天、"
                    "但發文時間晚於 15:30 cutoff 而滾到次日的邊界案例（此為前者的子集，非另加）；"
                    "(3) in_universe_after_own_calendar_last_not_global——不晚於全域最後交易日，"
                    "但晚於該股自身交易日曆的最後一天，是 RISK-027 方案 B「逐股票日曆」機制"
                    "本身的正常行為（該股在面板結束前已離開 PIT 宇宙），不是缺陷。"
                ),
            },
            "per_stock_raw_hit_day_counts": dict(
                sorted(per_stock_counts.items(), key=lambda kv: -kv[1])
            ),
            "per_stock_hit_days_via_drift_theme_mapping": dict(
                sorted(
                    {k: v for k, v in per_stock_drift_days.items() if v > 0}.items(),
                    key=lambda kv: -kv[1],
                )
            ),
            "trading_day_mapping": {
                "function": "src.transform.feature_aggregator.assign_trading_days_per_stock",
                "cutoff_time": CUTOFF_TIME,
                "trading_days_source": "panel 全期逐股票 trade_date（非全市場聯集日曆，RISK-027 方案 B）",
            },
        },
        "drift_vs_expansion": {
            "purpose": (
                "凍結面板基準與今日映射表重算之間，混有「映射表漂移」（凍結後每日 ETL 的 "
                "AI 探索新增了 theme 映射）與「關鍵字擴展」（本案要量測的效果）兩種成因。"
                "拿新管線比一個凍結產物之前，先把「沒改的輸入」（現行口徑）推過新管線，"
                "看它是否重現凍結值——重現了，差異才全歸新輸入；沒重現，差多少就是漂移。"
            ),
            "coverage_raw_hit_frozen_baseline": {"n": baseline_raw_hit, "pct": baseline_raw_hit_pct},
            "coverage_raw_hit_current_kw_recomputed_today": {
                "n": cov_current["n_raw_hit"], "pct": cov_current["pct_raw_hit"]
            },
            "coverage_raw_hit_full_kw_recomputed_today": {
                "n": cov_full["n_raw_hit"], "pct": cov_full["pct_raw_hit"]
            },
            "frozen_baseline_reproduced_by_current_kw_pipeline": {
                "intersection": len(frozen_pairs & current_recompute_pairs),
                "only_in_frozen_baseline": len(only_in_frozen),
                "only_in_current_kw_recompute": len(only_in_current_recompute),
                "note": (
                    "intersection 應等於 frozen_baseline 的 n（零遺漏），"
                    "only_in_frozen_baseline 應為 0——若非 0，代表重用的映射管線"
                    "漏掉了凍結面板實際存在的格子，需要另外排查。"
                ),
            },
            "drift_cells": len(only_in_current_recompute),
            "expansion_cells": cov_full["n_raw_hit"] - cov_current["n_raw_hit"],
            "coverage_5d_ma_proxy_frozen_baseline": {"n": baseline_5d_ma, "pct": baseline_5d_ma_pct},
            "coverage_5d_ma_proxy_current_kw_recomputed_today": {
                "n": ma_current["n_5d_ma_hit"], "pct": ma_current["pct_5d_ma_hit"]
            },
            "coverage_5d_ma_proxy_full_kw_recomputed_today": {
                "n": ma_full["n_5d_ma_hit"], "pct": ma_full["pct_5d_ma_hit"]
            },
            "evidence": {
                "theme_stock_mapping_rows_total": n_theme_total,
                "theme_stock_mapping_rows_updated_after_panel_freeze": n_theme_drift,
                "theme_stock_mapping_rows_updated_exactly_on_panel_freeze_date": n_theme_on_freeze_date,
                "panel_freeze_date": PANEL_FREEZE_DATE,
                "panel_freeze_date_source": (
                    f"從 PANEL_PATH 檔名反查（{Path(PANEL_PATH).name} → {PANEL_FREEZE_DATE}），"
                    "非手打常數。"
                ),
                "boundary_caveat": (
                    "漂移判定用的是 updated_at 的日期（等同凍結日 00:00 起算），不是面板實際"
                    "生成的時刻。本次資料集 theme_stock_mapping_rows_updated_exactly_on_panel_"
                    "freeze_date 為 0，凍結後最早一次更新是 2026-09-16 16:45，故本次結果不受"
                    "此邊界影響；但換一份資料集，若凍結當天真的有映射更新，以日期為粒度的比較"
                    "就可能誤判，屆時需改用面板實際生成的時刻而非只取日期。"
                ),
            },
        },
        "known_limitation": (
            "本結果是既有語料內的重新比對，是嚴格下界，不是真正上限（提案 §2.2）。"
            "真正上限需段 B（頁面速率探測 + 全量看板掃頁）向 PTT 重新取數才能量到。"
            "「關鍵字擴展的真實效果」請看 drift_vs_expansion.expansion_cells，"
            "不要直接拿 coverage_raw_hit.pct 減 baseline_pct。"
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print("      完成。")


if __name__ == "__main__":
    main()
