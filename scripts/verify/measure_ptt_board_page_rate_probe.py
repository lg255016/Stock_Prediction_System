# -*- coding: utf-8 -*-
"""§0.5 #40 段 B1：PTT 看板頁面速率探測（小量網路，只讀不寫）。

Gate A 提案：doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md §3.2
PO 執行授權：2026-09-21，硬性條件：

- `page_budget=30`（`PAGE_BUDGET` 常數），硬上限，不得因任何理由放寬。
- **只透過 `PttScraper()._fetch_page` 送請求**，本檔自建最小抓取函式，**不呼叫
  `scrape_ptt_board_pages()`**（會讓請求數平白加倍，違反提案 §3.2 訂正）。
  不新開任何 HTTP 入口，不修改 `scrape_ptt_board_pages()` 與 `_fetch_page()`。
- 請求間隔沿用 `_fetch_page()` 既有的 1.0～2.5 秒隨機禮貌性延遲，不加碼不縮短。
- 撞到 403／429：`_fetch_page` 的 `@retry` 已保證不重試——本腳本捕捉例外、記錄
  已完成頁數與例外訊息、**正常結束**（不視為腳本錯誤，視為觀測）。**不重試、
  不換時段再試**。
- 零寫入：不碰 `market_articles`、`tracking_keywords`、任何資料表、任何面板。
- 不執行段 B2（`scrape_ptt_board_pages_capture_all()` 不在本檔範圍內）。

用法：

    # 乾跑（mock _fetch_page，零網路），驗證整條管線與 JSON 結構
    python scripts/verify/measure_ptt_board_page_rate_probe.py --dry-run

    # 真實執行（對 PTT 送出請求，只做一次）
    python scripts/verify/measure_ptt_board_page_rate_probe.py

    # 用既有本機 JSONL 重算（零網路、零新請求）——複核第一輪訂正後使用
    python scripts/verify/measure_ptt_board_page_rate_probe.py \
        --recompute-from-jsonl scripts/verify/evidence_local/ptt_rate_probe_titles_<ts>.jsonl \
        --recompute-from-old-json doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_rate_probe.json

================================================================================
複核第一輪訂正（2026-09-21）：置底公告污染了「最舊文章」的判斷
================================================================================
v1 對「內容涵蓋的最舊時間」用 `min(全部條目的時間戳)`，而 PTT 的置底公告
（板規／異常回報區等）只出現在**最新一頁**、時間戳卻很舊——這正是
`ptt_scraper.py` E3 修正（2026-09-05 受控執行）與 `tests/test_ptt_board_pages.py`
V13 已經記錄過的同一個坑：`min` 會被置底文一次擊沉。`scrape_ptt_board_pages()`
的正式邏輯用**每頁 `max`** 判斷回溯進度，從不需要「全體最舊」這個量；本探測
腳本因為要報告「內容範圍」才需要它，而 v1 抄了翻頁骨架、沒抄「用 max 不用 min」
這個理由。

v2 修法：逐頁判定離群值——同一頁內，若某篇時間戳比該頁**最新一篇**早超過
`PINNED_POST_OUTLIER_DAYS`（7 天，遠大於任何一頁的正常內容跨度，也遠小於
置底公告動輒數月的年齡），判為置底／離群，排除出「內容涵蓋範圍」的計算，
另列 `pinned_posts_excluded`（不丟棄，只是不算進日期範圍）。
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup

from src.extractors.ptt_scraper import BOARD_INDEX_PATH, PttScraper, _url_timestamp
from src.transform.data_cleaner import parse_ptt_post_time

PAGE_BUDGET = 30  # PO 授權硬上限（2026-09-21），不得放寬
PINNED_POST_OUTLIER_DAYS = 7  # 見上方「複核第一輪訂正」
TARGET_DATE = datetime(2026, 1, 1)

OUTPUT_JSON = Path("doc/upgrade/gates/evidence/PTT_COVERAGE_CEILING_rate_probe.json")
LOCAL_TITLES_DIR = Path("scripts/verify/evidence_local")


def _make_dry_run_pages(n_pages=3, titles_per_page=3):
    """合成 n 頁看板 HTML 供乾跑測試（零網路）。

    比照 `tests/test_ptt_board_pages.py` 的 `board_page_html()` 既有寫法：
    URL 內嵌 unix 時間戳、索引頁日期欄固定 ` 9/05`（僅回退路徑會用到，本乾跑
    資料的時間戳全部可解析，用於驗證「回退筆數＝0」這條路徑本身跑得通）。
    """
    pages = []
    base_ts = 1768000000  # 2026-01-10 附近，任意選定，只求可被 _url_timestamp 解析
    for p in range(n_pages):
        rows = []
        for i in range(titles_per_page):
            ts = base_ts - p * 100000 - i * 1000
            rows.append(
                '<div class="r-ent">'
                '<div class="nrec"><span>10</span></div>'
                f'<div class="title"><a href="/bbs/Stock/M.{ts}.A.001.html">'
                f'[心得] 乾跑測試標題 p{p}i{i}</a></div>'
                f'<div class="author">user{p}{i}</div>'
                '<div class="date"> 9/05</div>'
                '</div>'
            )
        # 最後一篇故意留一個「已刪除」條目（title div 存在、無 <a>），驗證跳過計數
        rows.append(
            '<div class="r-ent"><div class="nrec"></div>'
            '<div class="title">(本文已被刪除)</div>'
            '<div class="author"></div><div class="date"> 9/05</div></div>'
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


def run_probe(scraper: PttScraper, page_budget: int, dry_run_pages=None) -> dict:
    """自建最小抓取函式：只透過 `scraper._fetch_page`，不呼叫 `scrape_ptt_board_pages()`。

    複製該方法既有的翻頁骨架（同一種「上一頁」連結解析方式），但不做關鍵字
    比對——本探測要捕捉每頁**全部** `r-ent` 條目，不是被關鍵字篩選過的子集。
    """
    current_url = scraper.base_url + BOARD_INDEX_PATH
    pages_fetched = 0
    per_page_title_counts = []
    per_page_elapsed_seconds = []
    all_entries = []
    seen_urls = set()
    n_deleted_skipped = 0
    stop_reason = None
    exception_message = None

    for i in range(page_budget):
        page_start = time.perf_counter()
        try:
            if dry_run_pages is not None:
                if i >= len(dry_run_pages):
                    stop_reason = "dry_run_pages_exhausted"
                    break
                html_text = dry_run_pages[i]
            else:
                html_text = scraper._fetch_page(current_url)
        except Exception as e:
            exception_message = f"{type(e).__name__}: {e}"
            stop_reason = "fetch_exception"
            break

        per_page_elapsed_seconds.append(time.perf_counter() - page_start)
        pages_fetched += 1
        soup = BeautifulSoup(html_text, "html.parser")

        page_title_count = 0
        for entry in soup.find_all("div", class_="r-ent"):
            title_div = entry.find("div", class_="title")
            title_tag = title_div.find("a") if title_div else None
            if not title_tag:
                n_deleted_skipped += 1
                continue

            title = title_tag.text.strip()
            link = scraper.base_url + title_tag["href"]
            date_div = entry.find("div", class_="date")
            date_str = date_div.text.strip() if date_div else ""
            author_div = entry.find("div", class_="author")
            author = author_div.text.strip() if author_div else ""
            push_div = entry.find("div", class_="nrec")
            push_count = push_div.text.strip() if push_div else "0"

            page_title_count += 1
            seen_urls.add(link)
            all_entries.append(
                {
                    "page_index": i,
                    "title": title,
                    "url": link,
                    "date": date_str,
                    "author": author,
                    "push_count": push_count,
                    "url_timestamp": _url_timestamp(link),
                }
            )

        per_page_title_counts.append(page_title_count)

        try:
            paging_div = soup.find("div", class_="btn-group btn-group-paging")
            prev_tag = paging_div.find_all("a")[1]
            if "href" not in prev_tag.attrs:
                stop_reason = "no_prev_page"
                break
            current_url = scraper.base_url + prev_tag["href"]
        except Exception as e:
            exception_message = f"pagination parse: {type(e).__name__}: {e}"
            stop_reason = "pagination_parse_failed"
            break
    else:
        stop_reason = "page_budget_exhausted"

    return {
        "pages_fetched": pages_fetched,
        "per_page_title_counts": per_page_title_counts,
        "per_page_elapsed_seconds": per_page_elapsed_seconds,
        "all_entries": all_entries,
        "n_deleted_skipped": n_deleted_skipped,
        "n_distinct_urls": len(seen_urls),
        "stop_reason": stop_reason,
        "exception_message": exception_message,
    }


def _classify_boundary(stop_reason: str) -> dict:
    """提案 §3.4：段 B1 僅有條件回報，不得留白（複核第二輪訂正）。"""
    if stop_reason == "no_prev_page":
        return {
            "determined": True,
            "conclusion": "PAGE_RETENTION_BOUNDARY_OBSERVED",
            "note": "30 頁預算內翻頁自行中斷（無「上一頁」連結）——PTT 看板本身在此處到底，"
            "不是預算用盡。",
        }
    if stop_reason == "fetch_exception":
        return {
            "determined": True,
            "conclusion": "BLOCKED_BEFORE_BUDGET_EXHAUSTED",
            "note": "30 頁預算內因請求例外（403／429 或傳輸層失敗且重試耗盡）中止——"
            "這是站方層級的限制，不是 PTT 看板本身的保留邊界，也不是預算用盡。",
        }
    return {
        "determined": False,
        "conclusion": "INSUFFICIENT_BUDGET",
        "note": "本段預算不足以判定，留待段 B2。",
    }


def _exclude_pinned_outliers(entries, post_times):
    """逐頁排除置底／離群時間戳（複核第一輪訂正）。

    同一頁內，若某篇時間戳比**該頁最新一篇**早超過 `PINNED_POST_OUTLIER_DAYS`，
    判為置底／離群，排除出「內容涵蓋範圍」的計算，另列 `pinned_posts_excluded`
    （不丟棄，只是不算進日期範圍與頁/天推算）。

    不依賴「置底文只會出現在 page 0」這個位置假設——逐頁各自判定，對任何
    頁面出現的離群值都成立。
    """
    by_page = defaultdict(list)
    for e, pt in zip(entries, post_times):
        by_page[e["page_index"]].append((e, pt))

    clean_post_times = []
    pinned_excluded = []
    threshold = timedelta(days=PINNED_POST_OUTLIER_DAYS)
    for page_idx, items in by_page.items():
        page_max = max(pt for _, pt in items)
        for e, pt in items:
            if (page_max - pt) > threshold:
                pinned_excluded.append(
                    {
                        "page_index": page_idx,
                        "title": e["title"],
                        "url": e["url"],
                        "post_time": pt.isoformat(),
                    }
                )
            else:
                clean_post_times.append(pt)
    return clean_post_times, pinned_excluded


def build_report(probe: dict, total_wall_seconds: float) -> dict:
    entries = probe["all_entries"]

    n_fallback = 0
    post_times = []
    for e in entries:
        pt = parse_ptt_post_time(e["url"], e["date"])
        post_times.append(pt)
        if e["url_timestamp"] is None:
            n_fallback += 1

    clean_post_times, pinned_excluded = _exclude_pinned_outliers(entries, post_times)

    oldest_post_time = min(clean_post_times) if clean_post_times else None
    newest_post_time = max(clean_post_times) if clean_post_times else None

    pages_fetched = probe["pages_fetched"]
    pages_per_second = pages_fetched / total_wall_seconds if total_wall_seconds > 0 else None

    pages_per_day = None
    pages_needed_for_2026_01_01 = None
    if oldest_post_time and newest_post_time and pages_fetched > 0:
        span_days = (newest_post_time.date() - oldest_post_time.date()).days
        if span_days > 0:
            pages_per_day = pages_fetched / span_days
            days_to_target = (oldest_post_time.date() - TARGET_DATE.date()).days
            if days_to_target > 0:
                pages_needed_for_2026_01_01 = round(days_to_target * pages_per_day, 1)
            else:
                pages_needed_for_2026_01_01 = 0

    boundary = _classify_boundary(probe["stop_reason"])

    distinct_titles = len({e["title"] for e in entries})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/verify/measure_ptt_board_page_rate_probe.py",
        "gate_a_proposal": "doc/upgrade/gates/PTT_COVERAGE_CEILING_MEASUREMENT_GATE_A_PROPOSAL.md",
        "read_only": True,
        "writes_to_any_table_or_panel": False,
        "page_budget": PAGE_BUDGET,
        "fetch_path": "PttScraper()._fetch_page only (self-built pagination, "
        "scrape_ptt_board_pages() not called)",
        "request_rate": {
            "pages_fetched": pages_fetched,
            "total_wall_seconds": round(total_wall_seconds, 2),
            "pages_per_second": round(pages_per_second, 4) if pages_per_second else None,
            "pages_per_day_extrapolated": round(pages_per_day, 2) if pages_per_day else None,
            "pages_needed_for_2026_01_01": pages_needed_for_2026_01_01,
            "note": "etl_run_log.http_attempts 對 PTT 全為 NULL，不可依賴；本欄為腳本自己"
            "計數的頁數，是段 B2 page_budget 推算的唯一依據。",
        },
        "date_range": {
            "oldest_post_time": oldest_post_time.isoformat() if oldest_post_time else None,
            "newest_post_time": newest_post_time.isoformat() if newest_post_time else None,
            "reached_2026_01_01": (
                oldest_post_time.date() <= TARGET_DATE.date() if oldest_post_time else None
            ),
            "n_records_via_url_timestamp": len(entries) - n_fallback,
            "n_records_via_fallback_mm_dd": n_fallback,
            "note": "日期一律經 parse_ptt_post_time(url, date_str) 推導，優先取網址內嵌"
            "unix 時間戳，MM/DD 索引頁日期欄僅作回退；回退路徑筆數獨立列出，"
            "不與網址時間戳可靠推導出的記錄混在一起計入。oldest/newest 已排除"
            "pinned_posts_excluded 列出的置底／離群項目。",
        },
        "pinned_posts_excluded": pinned_excluded,
        "per_page_title_counts": probe["per_page_title_counts"],
        "n_titles_total": len(entries),
        "n_distinct_titles": distinct_titles,
        "n_distinct_urls": probe["n_distinct_urls"],
        "n_deleted_articles_skipped": probe["n_deleted_skipped"],
        "stop_reason": probe["stop_reason"],
        "exception_message": probe["exception_message"],
        "boundary_determination": boundary,
        "revision_note": (
            "v1（本次複核前）用 min(全部條目的時間戳) 當「最舊文章」，被置底公告"
            "（板規／異常回報區等，只出現在最新一頁、時間戳卻很舊）污染，"
            "pages_per_day 因此低估約 20 倍（0.12 vs 訂正後約 2.3）。"
            "v2 改為逐頁排除離群值（PINNED_POST_OUTLIER_DAYS=7），"
            "與 ptt_scraper.py E3 修正（2026-09-05 受控執行、V13 測試）同一個坑，"
            "此為第三次出現，已補測試防第四次（tests/test_measure_ptt_board_page_rate_probe.py）。"
        ),
    }


def load_probe_from_previous_run(old_evidence_json_path: str, jsonl_path: str):
    """從既有本機 JSONL＋舊 evidence JSON 重建 probe 字典，不發任何新請求。

    只有 `build_report()` 的日期範圍計算有錯（v1 的 pinned-post 污染），
    頁面抓取本身的事實（頁數、耗時、每頁標題數、丟棄計數、停止原因）不受
    影響，直接從舊 JSON 帶過來即可，避免重新請求 PTT。
    """
    with open(old_evidence_json_path, encoding="utf-8") as f:
        old = json.load(f)
    with open(jsonl_path, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f]
    probe = {
        "pages_fetched": old["request_rate"]["pages_fetched"],
        "per_page_title_counts": old["per_page_title_counts"],
        "all_entries": entries,
        "n_deleted_skipped": old["n_deleted_articles_skipped"],
        "n_distinct_urls": old["n_distinct_urls"],
        "stop_reason": old["stop_reason"],
        "exception_message": old["exception_message"],
    }
    return probe, old["request_rate"]["total_wall_seconds"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mock _fetch_page with synthetic HTML, zero network requests",
    )
    parser.add_argument(
        "--recompute-from-jsonl",
        default=None,
        help="path to an existing local titles JSONL; skips network entirely",
    )
    parser.add_argument(
        "--recompute-from-old-json",
        default=None,
        help="path to the previous evidence JSON (paired with --recompute-from-jsonl)",
    )
    args = parser.parse_args()

    if args.recompute_from_jsonl:
        if not args.recompute_from_old_json:
            raise SystemExit("--recompute-from-jsonl 需搭配 --recompute-from-old-json")
        print(f"[1/3] 模式：重算（零網路、零新請求），來源：{args.recompute_from_jsonl}")
        probe, total_wall_seconds = load_probe_from_previous_run(
            args.recompute_from_old_json, args.recompute_from_jsonl
        )
        local_titles_path = Path(args.recompute_from_jsonl)  # 沿用既有檔，不再寫一份新的
    else:
        scraper = PttScraper()
        dry_run_pages = _make_dry_run_pages(n_pages=3) if args.dry_run else None

        mode = "DRY-RUN（零網路，合成 HTML）" if args.dry_run else "真實執行（對 PTT 送出請求）"
        print(f"[1/3] 模式：{mode}；page_budget={PAGE_BUDGET}")

        wall_start = time.perf_counter()
        probe = run_probe(scraper, PAGE_BUDGET, dry_run_pages=dry_run_pages)
        total_wall_seconds = time.perf_counter() - wall_start

        LOCAL_TITLES_DIR.mkdir(parents=True, exist_ok=True)
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = "dry_run_" if args.dry_run else ""
        local_titles_path = LOCAL_TITLES_DIR / f"{prefix}ptt_rate_probe_titles_{ts_tag}.jsonl"
        with open(local_titles_path, "w", encoding="utf-8") as f:
            for e in probe["all_entries"]:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

    print(
        f"[2/3] 完成：{probe['pages_fetched']} 頁，{len(probe['all_entries'])} 筆標題，"
        f"stop_reason={probe['stop_reason']}"
    )
    if probe["exception_message"]:
        print(f"      例外訊息：{probe['exception_message']}")

    report = build_report(probe, total_wall_seconds)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"[3/3] evidence JSON 已寫出：{OUTPUT_JSON}")
    print(f"      全部標題（本機、不進 repo）：{local_titles_path}")

    print(f"      主要口徑：pages_per_day={report['request_rate']['pages_per_day_extrapolated']}，"
          f"pages_needed_for_2026_01_01={report['request_rate']['pages_needed_for_2026_01_01']}")
    print(f"      置底／離群排除：{len(report['pinned_posts_excluded'])} 筆")
    print(f"      邊界判定：{report['boundary_determination']['conclusion']}")


if __name__ == "__main__":
    main()
