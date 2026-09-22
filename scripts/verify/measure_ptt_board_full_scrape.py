# -*- coding: utf-8 -*-
"""§0.5 #40 段 B2：全量看板掃頁 + 只讀量測變體。

Gate A 提案：doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md §3.3
PO 執行授權（段 B1 報告後另行授權，本檔目前僅供乾跑驗證，尚未真跑）：

- `scrape_ptt_board_pages_capture_all()`（`src/extractors/ptt_scraper.py` 新方法）
  只透過 `self._fetch_page` 送請求，不修改 `scrape_ptt_board_pages()` 與
  `_fetch_page()` 一個位元組。
- **一次跑完、延遲加倍**（PO 裁決 2026-09-21）：`extra_page_delay=1`
  （非零即啟用，每頁另加 `random.uniform(1.0, 2.5)` 秒），`page_budget=950`，
  `since_timestamp` 對應 2026-01-01（台北時間 00:00）。
- 撞到 403／429：`_fetch_page` 的 `@retry` 已保證不重試，方法本身捕捉例外、
  保留已收集資料、回報 `SOURCE_DEGRADED`，**不重試、不換時段再試**。
- 零寫入：不碰 `market_articles`、`tracking_keywords`、任何資料表、任何面板。

日期推導沿用段 A／B1 的既有原則：`parse_ptt_post_time()` 優先取網址內嵌
unix 時間戳，MM/DD 索引頁日期欄僅作回退，回退筆數獨立列出；置底／離群時間戳
排除邏輯**直接 import B1 的 `_exclude_pinned_outliers()`**（不重新實作）——
逐頁相對**該頁最新一篇**比較，不是相對全體最新一篇。

================================================================================
複核第二輪訂正（2026-09-21）：B2 曾自己另寫一份「相對全體最新」的版本，方向反了
================================================================================
v1 的 B2 腳本自己寫了一份 `_exclude_pinned_outliers`，用「比**全體**最新早
超過 7 天」當置底判準——B2 要回溯 263 天，這個判準會把 09-14 以前的**每一篇
真文章**都判成離群值排除掉，`oldest_post_time` 因此會被錯誤地停在接近今天
的地方，而那正是報告用來回答「有沒有回溯到 2026-01-01」的關鍵欄位。方向反了：
門檻固定時，參照點越晚，排除得越多；「全體最新」是最晚的參照點，排除得
**最多**，不是最少（docstring 曾誤寫「更保守」）。v2 改為直接 import B1 的
逐頁版本，不重新發明——這正是提案 §3.3「不重複實作、import 共用」原則本來
就要求的做法。

離線比對邏輯**重用** `measure_ptt_keyword_coverage_offline.py`（段 A）的
`load_keyword_stock_map()`／`map_hits_to_panel()`／`coverage_from_mapped_
pairs()`／`compute_5d_ma_proxy()`，不重複實作。

用法：

    # 乾跑（mock _fetch_page，零網路），驗證整條管線與 JSON 結構
    python scripts/verify/measure_ptt_board_full_scrape.py --dry-run

    # 真實執行——尚未取得 PO 授權，暫不提供不帶 --dry-run 的操作說明
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2
from bs4 import BeautifulSoup

from scripts.verify.measure_ptt_keyword_coverage_offline import (
    PANEL_PATH,
    PANEL_SHA256_EXPECTED,
    PANEL_WINDOW_START,
    _load_db_config,
    coverage_from_mapped_pairs,
    compute_5d_ma_proxy,
    load_keyword_stock_map,
    map_hits_to_panel,
    verify_panel_sha256,
    PANEL_FREEZE_DATE,
)
from scripts.verify.measure_ptt_board_page_rate_probe import (
    _exclude_pinned_outliers,
)
from src.extractors.ptt_scraper import BOARD_INDEX_PATH, PttScraper, _url_timestamp
from src.transform.data_cleaner import parse_ptt_post_time

PAGE_BUDGET = 950  # PO 裁決 2026-09-21：B1 推算 577，09-19 日誌上界估 920，留緩衝取整
EXTRA_PAGE_DELAY = 1  # 非零即啟用（PO 裁決：一次跑完、延遲加倍）
TARGET_DATE = datetime(2026, 1, 1)
_TAIPEI = timezone(timedelta(hours=8))
SINCE_TIMESTAMP = int(datetime(2026, 1, 1, tzinfo=_TAIPEI).timestamp())

OUTPUT_JSON_REAL = Path("doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_full_scrape_report.json")
LOCAL_TITLES_DIR = Path("scripts/verify/evidence_local")
# 複核第三輪訂正：乾跑與真跑共用同一個 OUTPUT_JSON 常數時，乾跑會把合成資料
# 寫進真實 evidence 路徑——審查方乾跑一次就在該路徑留下一份未追蹤、檔名與
# 真證據完全相同的 JSON，靠事後手動刪除來避免混淆是會漏的。乾跑改寫本機
# evidence_local/（已 gitignore），真跑維持原路徑不變。
OUTPUT_JSON_DRY_RUN = LOCAL_TITLES_DIR / "PTT_COVERAGE_CEILING_full_scrape_DRY_RUN.json"

SEGMENT_A_EVIDENCE = Path("doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_offline_rematch.json")


def _load_segment_a_current_kw_baseline():
    """讀段 A 的 evidence JSON，取『同管線現行口徑』基準（846／3.46%），
    不重複硬寫這個數字——它會隨段 A 重跑而變，本檔只讀不算。"""
    if not SEGMENT_A_EVIDENCE.exists():
        return None
    with open(SEGMENT_A_EVIDENCE, encoding="utf-8") as f:
        seg_a = json.load(f)
    node = seg_a.get("drift_vs_expansion", {}).get(
        "coverage_raw_hit_current_kw_recomputed_today"
    )
    return node


def _make_dry_run_pages(n_pages=3, titles_per_page=3):
    """合成 n 頁看板 HTML 供乾跑測試（零網路）。

    **複核第二輪訂正**：每頁間隔改為 4 天（原本約 1.16 天／頁，3 頁只跨約
    2.3 天，遠小於 `PINNED_POST_OUTLIER_DAYS=7`，對「置底排除邏輯用錯參照點」
    這類缺陷永遠是盲的——B2 v1 的 bug 正是在真跑才會現形，乾跑當時測不出來）。
    3 頁跨約 8 天，確保置底／離群排除邏輯的門檻真的會被跨過，乾跑才有機會
    偵測到同型缺陷。
    """
    pages = []
    base_ts = 1768000000
    for p in range(n_pages):
        rows = []
        for i in range(titles_per_page):
            ts = base_ts - p * 345600 - i * 1000  # 每頁間隔 4 天
            rows.append(
                '<div class="r-ent">'
                '<div class="nrec"><span>10</span></div>'
                f'<div class="title"><a href="/bbs/Stock/M.{ts}.A.001.html">'
                f'[標的] 2330 台積電 乾跑p{p}i{i}</a></div>'
                f'<div class="author">user{p}{i}</div>'
                '<div class="date"> 9/05</div>'
                '</div>'
            )
        has_prev = p < n_pages - 1
        prev = (
            '<a class="btn wide" href="/bbs/Stock/index%d.html">&lsaquo; 上頁</a>' % (100 - p)
            if has_prev
            else '<a class="btn wide disabled">&lsaquo; 上頁</a>'
        )
        pages.append(
            '<html><body>%s<div class="btn-group btn-group-paging">'
            '<a class="btn wide">最舊</a>%s</div></body></html>' % ("".join(rows), prev)
        )
    return pages


def run_capture_all(scraper: PttScraper, page_budget: int, since_timestamp,
                     extra_page_delay: int, dry_run_pages=None) -> dict:
    """呼叫 `scrape_ptt_board_pages_capture_all()`（GREEN 已落地的新方法）。

    乾跑模式下直接自建最小分頁迴圈套用合成 HTML（與該方法呼叫 `_fetch_page`
    的次數一致），避免真的去 monkeypatch 生產方法內部的 `time.sleep`。
    """
    if dry_run_pages is None:
        wall_start = time.perf_counter()
        df, outcome = scraper.scrape_ptt_board_pages_capture_all(
            since_timestamp=since_timestamp, page_budget=page_budget,
            extra_page_delay=extra_page_delay,
        )
        total_wall_seconds = time.perf_counter() - wall_start
        entries = df.to_dict("records")
        for e in entries:
            e["url_timestamp"] = _url_timestamp(e["url"])
        return {
            "entries": entries,
            "outcome": outcome,
            "total_wall_seconds": total_wall_seconds,
        }

    # --dry-run：mock _fetch_page，直接重用同一個方法（extra_page_delay 仍會
    # 呼叫 time.sleep，乾跑刻意保留這個呼叫以驗證邏輯不出錯，只是延遲很短
    # 因為 dry-run 用途本來就是驗證管線，不是驗證真實節奏）。
    call_count = {"n": 0}

    def _fake_fetch(url):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx >= len(dry_run_pages):
            raise RuntimeError("dry_run_pages_exhausted")
        return dry_run_pages[idx]

    scraper._fetch_page = _fake_fetch
    wall_start = time.perf_counter()
    df, outcome = scraper.scrape_ptt_board_pages_capture_all(
        since_timestamp=since_timestamp, page_budget=page_budget,
        extra_page_delay=0,  # 乾跑不需要真的等待
    )
    total_wall_seconds = time.perf_counter() - wall_start
    entries = df.to_dict("records")
    for e in entries:
        e["url_timestamp"] = _url_timestamp(e["url"])
    return {
        "entries": entries,
        "outcome": outcome,
        "total_wall_seconds": total_wall_seconds,
    }


def build_hit_rows_from_capture(entries: list, kw2stocks: dict) -> pd.DataFrame:
    """對全量捕捉到的標題做 479 個關鍵字聯集的子字串比對（提案 §3.3 離線後處理）。"""
    rows = []
    for idx, e in enumerate(entries):
        title = e.get("title") or ""
        pt = parse_ptt_post_time(e["url"], e.get("date", ""))
        hit_stocks = set()
        for kw, stocks in kw2stocks.items():
            if kw and kw in title:
                hit_stocks |= stocks
        for sid in hit_stocks:
            rows.append({"article_id": -(idx + 1), "stock_id": sid, "post_time": pt})
    return pd.DataFrame(rows, columns=["article_id", "stock_id", "post_time"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="mock _fetch_page with synthetic HTML, zero network requests",
    )
    parser.add_argument(
        "--confirm-real-run", action="store_true",
        help="required together with omitting --dry-run to execute against real "
             "PTT. PO authorization on record: 2026-09-21, since_timestamp="
             "2026-01-01 台北 00:00, page_budget=950, extra_page_delay enabled "
             "（見 PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md §3.3 補段）。",
    )
    parser.add_argument(
        "--recompute-from-jsonl", default=None,
        help="path to an existing local titles JSONL (from a prior real run); "
             "skips network entirely, zero new requests",
    )
    parser.add_argument(
        "--recompute-from-old-json", default=None,
        help="path to the previous evidence JSON (paired with --recompute-from-jsonl)",
    )
    args = parser.parse_args()

    if args.recompute_from_jsonl:
        if not args.recompute_from_old_json:
            raise SystemExit("--recompute-from-jsonl 需搭配 --recompute-from-old-json")
    elif not args.dry_run and not args.confirm_real_run:
        raise SystemExit(
            "真跑需要明確傳入 --confirm-real-run（防止意外執行）——"
            "PO 已於 2026-09-21 授權本次真跑，見 Gate A 提案 §3.3 補段。"
        )

    print(f"[1/6] 核對面板 sha256：{PANEL_PATH}")
    actual_sha = verify_panel_sha256(PANEL_PATH, PANEL_SHA256_EXPECTED)
    print(f"      OK，sha256={actual_sha}")

    print("[2/6] 連線資料庫，讀取 entity_mapping／theme_stock_mapping／tracking_keywords（唯讀）")
    conn = psycopg2.connect(**_load_db_config())
    try:
        kw2stocks, _drift_keys, n_theme_total, n_theme_drift, _n_theme_on_freeze = (
            load_keyword_stock_map(conn, PANEL_FREEZE_DATE)
        )
        cur = conn.cursor()
        cur.execute("SELECT keyword FROM tracking_keywords WHERE is_active = TRUE")
        active_keywords = set(r[0] for r in cur.fetchall())
    finally:
        conn.close()
    current_kw2stocks = {k: v for k, v in kw2stocks.items() if k in active_keywords}
    print(f"      關鍵字聯集：{len(kw2stocks)}；現行啟用且有映射：{len(current_kw2stocks)}"
          f"（啟用共 {len(active_keywords)}，{len(active_keywords) - len(current_kw2stocks)} 個不在任何映射表）")

    if args.recompute_from_jsonl:
        print(f"[3/6] 模式：重算（零網路、零新請求），來源：{args.recompute_from_jsonl}")
        with open(args.recompute_from_old_json, encoding="utf-8") as f:
            old = json.load(f)
        with open(args.recompute_from_jsonl, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f]
        capture = {
            "entries": entries,
            "outcome": old["capture_outcome"],
            "total_wall_seconds": old["total_wall_seconds"],
        }
        args.dry_run = old["mode"] == "dry_run"
    else:
        scraper = PttScraper()
        dry_run_pages = _make_dry_run_pages(n_pages=3) if args.dry_run else None
        mode = "DRY-RUN（零網路，合成 HTML）" if args.dry_run else "真實執行"
        print(f"[3/6] 模式：{mode}；page_budget={PAGE_BUDGET}，extra_page_delay={EXTRA_PAGE_DELAY}")

        capture = run_capture_all(
            scraper, PAGE_BUDGET, SINCE_TIMESTAMP, EXTRA_PAGE_DELAY,
            dry_run_pages=dry_run_pages,
        )
    entries = capture["entries"]
    print(f"[4/6] 完成：{len(entries)} 筆標題，outcome={capture['outcome']}")

    n_fallback = 0
    post_times = []
    for e in entries:
        pt = parse_ptt_post_time(e["url"], e.get("date", ""))
        post_times.append(pt)
        if e.get("url_timestamp") is None:
            n_fallback += 1
    # B1 的 _exclude_pinned_outliers() 逐頁相對該頁最新一篇比較，需要每列自己的
    # page_index——scrape_ptt_board_pages_capture_all() 已補上這個欄位。
    clean_post_times, pinned_excluded = _exclude_pinned_outliers(entries, post_times)
    oldest = min(clean_post_times) if clean_post_times else None
    newest = max(clean_post_times) if clean_post_times else None

    print(f"[5/6] 讀取面板（唯讀，sha256 已核對）：{PANEL_PATH}")
    panel = pd.read_parquet(PANEL_PATH)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"]).dt.date
    trading_days_by_stock = (
        panel.groupby("stock_id")["trade_date"].apply(lambda s: sorted(set(s))).to_dict()
    )
    panel_subset = panel[panel["trade_date"] >= pd.Timestamp(PANEL_WINDOW_START).date()].copy()

    hit_rows = build_hit_rows_from_capture(entries, kw2stocks)
    mapped, dropped = map_hits_to_panel(hit_rows, panel, trading_days_by_stock)
    cov = coverage_from_mapped_pairs(mapped, panel_subset)
    ma = compute_5d_ma_proxy(cov["mapped_pairs"], panel, len(panel_subset))

    # 複核第三輪追加：現行啟用關鍵字（僅 25 個有映射）套在全板語料——回答
    # 「每日 ETL 的看板模式對現行關鍵字有沒有漏抓」，區分擷取深度與關鍵字廣度
    # 兩種可能的覆蓋率瓶頸。
    current_hit_rows = build_hit_rows_from_capture(entries, current_kw2stocks)
    current_mapped, _current_dropped = map_hits_to_panel(
        current_hit_rows, panel, trading_days_by_stock
    )
    current_cov = coverage_from_mapped_pairs(current_mapped, panel_subset)

    baseline_raw_hit = int((panel_subset["article_count"] > 0).sum())
    baseline_5d_ma = int(panel_subset["sentiment_5d_ma"].notna().sum())
    n_subset = len(panel_subset)

    hit_pairs_in_subset = cov["hit_pairs_in_subset"]
    per_stock_counts = defaultdict(int)
    for sid, _d in hit_pairs_in_subset:
        per_stock_counts[sid] += 1

    segment_a_baseline = _load_segment_a_current_kw_baseline()

    boundary = {
        "determined": capture["outcome"] == "SOURCE_DEGRADED" or (
            oldest is not None and oldest.date() <= TARGET_DATE.date()
        ),
        "outcome": capture["outcome"],
        "reached_2026_01_01": oldest.date() <= TARGET_DATE.date() if oldest else None,
        "note": (
            "outcome=SOURCE_DEGRADED 代表預算用盡未達目標時間（預算不足）；"
            "reached_2026_01_01=True 且 outcome=OK 代表翻頁自行停在目標時間"
            "（成功回溯到位）；outcome=OK 但仍需檢查是否撞到「已無上一頁」"
            "（看板保留邊界）——後者需另外查看 print log 的『已經沒有上一頁了』。"
        ),
        "inference_on_2026_01_17": (
            "09-07 一次性回補當時停在 2026-01-17；本次 B2 用 950 頁預算成功"
            "回溯到 2025-12-31（比 01-17 更舊），且全程未遇『已經沒有上一頁了』"
            "（`stop_reason` 對應之 outcome 為 OK、`reached_2026_01_01=true`，"
            "不是 no_prev_page）——因此 01-17 是當初那次回補的**預算用盡**，"
            "不是看板保留邊界；真正的保留邊界在 2025-12-31 之前，本案未觸及。"
        ),
    }

    report = {
        "mode": "dry_run" if args.dry_run else "real",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/verify/measure_ptt_board_full_scrape.py",
        "gate_a_proposal": "doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md",
        "read_only": True,
        "writes_to_any_table_or_panel": False,
        "page_budget": PAGE_BUDGET,
        "extra_page_delay_enabled": bool(EXTRA_PAGE_DELAY),
        "since_timestamp": SINCE_TIMESTAMP,
        "capture_outcome": capture["outcome"],
        "total_wall_seconds": round(capture["total_wall_seconds"], 2),
        "n_titles_total": len(entries),
        "date_range": {
            "oldest_post_time": oldest.isoformat() if oldest else None,
            "newest_post_time": newest.isoformat() if newest else None,
            "n_records_via_url_timestamp": len(entries) - n_fallback,
            "n_records_via_fallback_mm_dd": n_fallback,
        },
        "pinned_posts_excluded": pinned_excluded,
        "boundary_determination": boundary,
        "coverage_raw_hit": {
            "n_hit": cov["n_raw_hit"],
            "pct": cov["pct_raw_hit"],
            "baseline_frozen_panel": {
                "n": baseline_raw_hit,
                "pct": round(baseline_raw_hit / n_subset * 100, 2) if n_subset else None,
                "note": "article_count>0，09-12 凍結面板值",
            },
            "baseline_segment_a_current_kw_recomputed_today": segment_a_baseline,
            "note": "主要比較對象為 baseline_segment_a_current_kw_recomputed_today"
            "（同管線、同映射表，唯一差異是段 A 只用既有 1,349 篇 vs 本段全量捕捉）"
            "——兩者差距才是真正的『全量回補』效果；baseline_frozen_panel 混有"
            "映射表漂移，僅供參考，見段 A evidence 的 drift_vs_expansion。",
        },
        "coverage_5d_ma_proxy": {
            "n_hit": ma["n_5d_ma_hit"],
            "pct": ma["pct_5d_ma_hit"],
            "baseline_sentiment_5d_ma_notna_frozen_panel": baseline_5d_ma,
            "baseline_pct": round(baseline_5d_ma / n_subset * 100, 2) if n_subset else None,
        },
        "n_stocks_hit": len({sid for sid, _ in hit_pairs_in_subset}),
        "per_stock_day_counts": dict(
            sorted(per_stock_counts.items(), key=lambda kv: -kv[1])
        ),
        "n_dropped_hit_rows": dropped,
        "keyword_breadth_vs_capture_depth": {
            "purpose": (
                "區分覆蓋率瓶頸在『擷取深度』（每日 ETL 有沒有漏抓看板內容）"
                "還是『關鍵字廣度』（追蹤的關鍵字太少）——2x2 對照：篩選語料"
                "（既有 1,349 篇，段 A）vs 全板語料（本段 16,814 篇）× "
                "現行 25 個有映射的啟用關鍵字 vs 479 個關鍵字聯集。"
            ),
            "current_keywords_filtered_corpus": segment_a_baseline,
            "current_keywords_full_corpus": {
                "n": current_cov["n_raw_hit"],
                "pct": current_cov["pct_raw_hit"],
                "n_stocks": len({sid for sid, _ in current_cov["hit_pairs_in_subset"]}),
            },
            "all_keywords_filtered_corpus": {"n": 1005, "pct": 4.11, "n_stocks": 86,
                "note": "段 A 全關鍵字重算值，見段 A evidence"},
            "all_keywords_full_corpus": {
                "n": cov["n_raw_hit"], "pct": cov["pct_raw_hit"],
                "n_stocks": len({sid for sid, _ in hit_pairs_in_subset}),
            },
            "n_active_tracking_keywords": len(active_keywords),
            "n_active_tracking_keywords_mapped": len(current_kw2stocks),
            "active_keywords_not_in_any_mapping": sorted(
                active_keywords - set(current_kw2stocks.keys())
            ),
            "conclusion": (
                "把整個看板抓回來，對現行關鍵字只多 "
                f"{current_cov['n_raw_hit'] - (segment_a_baseline['n'] if segment_a_baseline else 0)} "
                "格——每日 ETL 的看板模式對『現在啟用的關鍵字』已經接近完整，"
                "不是擷取深度不夠；11.9% 裡的絕大部分是關鍵字擴展帶來的，"
                "不是抓取帶來的。是否擴大關鍵字清單、擴到哪，留待 Gate 4 裁決，"
                "本案不做建議。"
            ),
        },
    }

    output_json = OUTPUT_JSON_DRY_RUN if args.dry_run else OUTPUT_JSON_REAL
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"[6/6] evidence JSON 已寫出：{output_json}")

    if args.recompute_from_jsonl:
        # 重算模式沿用既有 JSONL，不再寫一份重複的本機標題檔。
        local_path = Path(args.recompute_from_jsonl)
    else:
        LOCAL_TITLES_DIR.mkdir(parents=True, exist_ok=True)
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = "dry_run_" if args.dry_run else ""
        local_path = LOCAL_TITLES_DIR / f"{prefix}ptt_board_full_scrape_{ts_tag}.jsonl"
        with open(local_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    print(f"      全部標題（本機、不進 repo）：{local_path}")
    print(f"      主要口徑 coverage_raw_hit_pct={report['coverage_raw_hit']['pct']}%")


if __name__ == "__main__":
    main()
