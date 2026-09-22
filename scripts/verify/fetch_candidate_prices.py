# -*- coding: utf-8 -*-
"""UG-G2-SB9 階段一：取得候選池價格資料（最近 N 個交易日）。

**每一日取數後立即比對提案 §6.2a 的逐日預期，任一項不符即停止**——
不累積到最後才檢查，也不自行解釋。

節流 3.0–5.0 秒（比 PTT 的 1.5–3.0 保守：對象是政府單位服務）。
**非交易日不消耗交易日配額**，但仍計入請求數並記錄。

用法：
    python scripts/verify/fetch_candidate_prices.py --days 60 --end 20260821 \\
        --out doc/upgrade/gates/evidence/G2_SB9_phase1_ingest_report.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.verify.twse_market_endpoint_check import (  # noqa: E402
    DELAY_RANGE, ENDPOINT, TIMEOUT_SECONDS, USER_AGENT, _find_market_table,
)
from scripts.verify.tpex_endpoint_check import (  # noqa: E402
    candidate_urls as tpex_candidate_urls, extract_table,
)
from src.extractors.twse_market_report import parse_market_report  # noqa: E402
from src.extractors.tpex_market_report import parse_tpex_report  # noqa: E402

# ---------------------------------------------------------------------------
# 提案 §6.2a 逐日預期（**取數前寫死，跑完只做比對**）
# ---------------------------------------------------------------------------
# 【2026-09-01 修正，PO 裁示 1】原為絕對區間 `1085 ± 20`。
# 那是**兩天觀測**推出來的，**在跨年度資料上必然誤報**——
# 3 年前的市場規模不會與今天相同（實測 60 天內就已在 1081~1088 之間移動）。
# 改為**相對判準**：與前一交易日相比的變動率。
#
# 上市／下市在單日通常是 0~2 檔（60 天實測：每日 1081~1088，最大單日差 ~3 檔）。
# 2% ≈ 21 檔／日，遠高於正常異動，但**足以攔下「回應被截斷」**
# （那會是數量級的掉落，不是幾檔）。
MAX_DAILY_CHANGE_RATIO = 0.02
# 首日無前一日可比，改用絕對下界（同 B2 的精神：低於此代表拿到的不是全市場）。
# 800 而非 1065：3 年前的上市家數本來就比今天少，下界要能容納那個事實。
FIRST_DAY_MIN_COMMON = 800
EXPECT_MEDIAN_MIN, EXPECT_MEDIAN_MAX = 1e6, 1e8        # 成交金額中位數量級

# 【2026-09-01 PO 條件二】櫃買的首日下界**不得沿用 TWSE 的 800**，
# 也**不得把 C7 的量測值 887 寫成絕對門檻**——那正是 C7 註記自己反對的
# 「先寫一個數字再拿它當判準就是在猜」。
#
# 200 的角色與 TPEx 判準 C3a 完全相同：**只擋分頁碎片，不是對市場規模的宣稱**。
# 分頁通常數十列；200 遠高於任何合理單頁大小，也遠低於任何市場規模宣稱。
# 逐日判準沿用**相對變動率**（`MAX_DAILY_CHANGE_RATIO`），與 TWSE 同一條。
FIRST_DAY_MIN_COMMON_TPEX = 200

# 三年約 740 交易日 + 非交易日（TWSE 實際為 795）。**逾預算即停止回報，不自行加碼。**
REQUEST_BUDGET = 850
# 傳輸層錯誤（TLS 交握／連線／逾時）在**同一個邏輯請求內**重試的次數。
#
# 【2026-09-01】此規則審查者已於 TPEx 端點驗證時裁示並實作於
# `tpex_endpoint_check.py`，**但我沒有把它傳播到本檔** ——
# 結果本檔第一個請求就死在 `SSLError(CERTIFICATE_VERIFY_FAILED,
# Missing Subject Key Identifier)`，740 天一天都沒取到。
# **一條規則實作在一個地方而不是另一個地方，是本 SB 第六次同型的問題。**
#
# 規則本身不變：**只在傳輸層錯誤、429 與 5xx 時重試**；
# 4xx（除 429）代表端點明確回答了，重試不會讓答案改變。
# 且**傳輸層失敗不消耗邏輯請求配額** —— 它沒有到達應用層，幾乎沒造成負載。
# 【2026-09-02 審查者裁示】由 2 提高到 5（共 6 次嘗試），退避改遞增。
#
# **20260615 連敗 4 次不代表那個日期特殊——結構上不可能。**
# TLS 交握是對 `www.tpex.org.tw:443` 做的，**在任何 path 或 query 送出之前**；
# SNI 只帶主機名。**憑證驗證失敗的那一刻，伺服器還不知道我們要問哪一天。**
#
# 真正的成因是**選擇效應**：每一段都從中斷點起跑，
# 所以每一次邊緣節點的隨機失敗都必然落在同一個日期上。
# **20260615 是失敗累積的地方，不是失敗的原因** ——
# 一個看起來像訊號的數字，其實是取樣方式的產物。
#
# 據此：**段數是拿來計「邏輯進度停滯」的，不該拿去吸收 TLS 抖動。**
# 提高的是傳輸層重試，不是段數。仍有上限、有退避、每次入帳，
# **不是「重試至成功」**；且傳輸層失敗不消耗邏輯請求配額。
TRANSPORT_RETRIES = 5
TRANSPORT_BACKOFF_SECONDS = (5, 10, 20, 40, 60)
# 【2026-09-01 審查者裁示】**403/429 與 5xx／傳輸層是兩件事，不得綁在同一條。**
#
#   403 / 429  —— **服務在叫你停**。硬停，一次都不重試。
#                  那條紀律真正要防的就是這個：重試至成功會把封鎖訊號磨掉。
#   5xx / 傳輸層 —— 服務**沒能回答**，與我方行為無關（520 是邊緣層的暫時性錯誤，
#                  **不是櫃買在拒絕我們**）。有界重試：延長退避後最多再試 1 次。
#
# **60 秒退避、上限 1 次、每次嘗試全程入帳** —— 「重試至成功」與「把失敗藏起來」
# 兩者都沒有被違反。仍失敗則**停止本段並記下該日期**。
SERVER_ERROR_RETRIES = 1
SERVER_ERROR_BACKOFF_SECONDS = 60

INSERT_SQL = """
INSERT INTO candidate_prices
  (stock_id, trade_date, security_name, open_price, high_price, low_price,
   close_price, volume, turnover_amount, transactions,
   best_bid_price, best_bid_volume, best_ask_price, best_ask_volume,
   pe_ratio, source)
VALUES %s
ON CONFLICT (stock_id, trade_date) DO NOTHING
RETURNING stock_id;
"""
COLS = ("stock_id", "trade_date", "security_name", "open_price", "high_price",
        "low_price", "close_price", "volume", "turnover_amount", "transactions",
        "best_bid_price", "best_bid_volume", "best_ask_price", "best_ask_volume",
        "pe_ratio", "source")


def check_day(stats, records, date_str, prev_common=None,
              first_day_floor=FIRST_DAY_MIN_COMMON):
    """§6.2a 六項逐日比對。回傳 (ok, 不符清單, 中位數)。

    `first_day_floor` 依市場不同（PO 2026-09-01 條件二）：
    TWSE 800、TPEx 200。**逐日判準本身（相對變動率）兩個市場相同** ——
    絕對值會隨市場與年份漂移，相對變動率量的是不連續，不會。
    """
    bad = []
    n = stats["rows_common_stock"]
    if prev_common is None:
        if n < first_day_floor:
            bad.append("首日普通股列數 %d < 下界 %d" % (n, first_day_floor))
    else:
        ratio = abs(n - prev_common) / float(prev_common)
        if ratio > MAX_DAILY_CHANGE_RATIO:
            bad.append("普通股列數 %d 相對前一交易日 %d 變動 %.2f%% > %.0f%%"
                       % (n, prev_common, ratio * 100, MAX_DAILY_CHANGE_RATIO * 100))
    if stats["rows_common_stock"] + stats["rows_excluded_by_code_shape"] != stats["rows_total"]:
        bad.append("列數不守恆：%d + %d != %d" % (
            stats["rows_common_stock"], stats["rows_excluded_by_code_shape"],
            stats["rows_total"]))
    if stats["rows_unparseable_volume_or_amount"] != 0:
        bad.append("出現無法解析的成交量／金額 %d 列（B4 未觀察到的形態）"
                   % stats["rows_unparseable_volume_or_amount"])
    if len(records) != n - stats["rows_unparseable_volume_or_amount"]:
        bad.append("寫入列數 %d 與解析結果不一致" % len(records))
    amts = sorted(r["turnover_amount"] for r in records)
    median = amts[len(amts) // 2] if amts else 0
    if not (EXPECT_MEDIAN_MIN <= median <= EXPECT_MEDIAN_MAX):
        bad.append("成交金額中位數 %s 跨出量級 [1e6, 1e8]" % median)
    return (not bad), bad, median


# 每個邏輯請求實際發出的 HTTP 嘗試數（含傳輸層重試），供雙軌計數。
_ATTEMPTS = []


def _ca_bundle_path():
    """回傳目前使用的 CA bundle 路徑（診斷用）。

    ⚠ **只讀不改。** `verify=False`／`--insecure`／任何放寬憑證驗證的做法
    **明確禁止**——那不是修好，是把偵測拿掉。
    """
    try:
        import certifi
        return certifi.where()
    except Exception:
        return "unknown"


def fetch_day(date_str, market="twse"):
    """一個**邏輯請求**。回傳 (fields, rows, stat, diag)。

    **兩個市場共用同一支取數器**，只有 URL 與取表的欄位樣式不同 ——
    本 SB 已有五次歸因錯誤的成因是「同一個概念有兩個實作」，不再製造第六個。
    """
    import requests
    if market == "twse":
        url = ENDPOINT.format(date=date_str)
    else:
        # 櫃買行情頁（TPEx 端點驗證的候選 2，C1~C6 全 PASS）。
        # `date` 參數格式為 `YYYY/MM/DD`（西元），**不是民國年**——
        # C2 已實測：兩個日期回應不同，日期參數確實生效。
        iso = "%s-%s-%s" % (date_str[:4], date_str[4:6], date_str[6:])
        url = dict(tpex_candidate_urls(iso))["www_afterTrading_otc"]
    # 【2026-09-01 修補，第八次同型】原本只有**第一次**請求包在傳輸層重試裡，
    # 而 5xx 退避後的那次是**裸 `requests.get`** —— 同一件事（發出 HTTP 請求）
    # 有兩個實作，其中一個沒有保護。
    # 實測後果（段三 20260615）：520 退避後那次撞上 `SSLError`，
    # **直接把整段停掉**，而錯誤訊息是原始 SSLError 而非「傳輸層失敗，重試 N 次後」——
    # **訊息對不上，正是「有兩個實作」的指紋。**
    # 抽成單一入口，兩個呼叫點都走它。
    attempts = 0

    def _get():
        """發出一次 HTTP 請求，**傳輸層失敗在內部有界重試**。回傳 resp。"""
        nonlocal attempts
        last_exc = None
        for i in range(1 + TRANSPORT_RETRIES):
            attempts += 1
            try:
                return requests.get(url, headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"},
                                    timeout=TIMEOUT_SECONDS)
            except Exception as exc:
                # **沒拿到 status_code ⇒ 傳輸層失敗 ⇒ 未觀測到回應。**
                # 判斷依據是「有沒有回應物件」，不是例外類別名稱——
                # 後者需要窮舉，而窮舉不完的那一項會被靜默歸錯類。
                last_exc = exc
                if i < TRANSPORT_RETRIES:
                    wait = TRANSPORT_BACKOFF_SECONDS[
                        min(i, len(TRANSPORT_BACKOFF_SECONDS) - 1)]
                    print("    %s 傳輸層失敗（%s…），退避 %d 秒後於同一邏輯請求內"
                          "重試 %d/%d"
                          % (date_str, str(exc)[:70], wait, i + 1, TRANSPORT_RETRIES))
                    time.sleep(wait)
        # 失敗時記錄 TLS 環境作為診斷證據（審查者允許項）。
        # **不做任何放寬**——只是把「失敗當下的環境」留下來。
        import ssl as _ssl
        raise RuntimeError(
            "傳輸層失敗，重試 %d 次後仍未取得回應（OpenSSL: %s；CA bundle: %s）：%s"
            % (TRANSPORT_RETRIES, _ssl.OPENSSL_VERSION,
               _ca_bundle_path(), last_exc))

    resp = _get()
    if resp.status_code in (403, 429):
        # **服務在叫你停** —— 硬停，一次都不重試。
        raise RuntimeError("HTTP %d（服務拒絕）—— 硬停，不重試，需 PO 裁示"
                           % resp.status_code)
    if resp.status_code >= 500:
        # 服務**沒能回答**。有界重試：60 秒退避後最多再試 1 次。
        for j in range(SERVER_ERROR_RETRIES):
            print("    %s HTTP %d —— 退避 %d 秒後再試 %d/%d（**上限 1 次**）"
                  % (date_str, resp.status_code, SERVER_ERROR_BACKOFF_SECONDS,
                     j + 1, SERVER_ERROR_RETRIES))
            time.sleep(SERVER_ERROR_BACKOFF_SECONDS)
            resp = _get()          # ← 走同一個入口，傳輸層保護一致
            if resp.status_code in (403, 429):
                raise RuntimeError("HTTP %d（服務拒絕）—— 硬停，不重試，需 PO 裁示"
                                   % resp.status_code)
            if resp.status_code < 500:
                break
        if resp.status_code >= 500:
            raise RuntimeError("HTTP %d —— 退避重試 %d 次後仍失敗，停止本段"
                               % (resp.status_code, SERVER_ERROR_RETRIES))
    resp.raise_for_status()
    payload = resp.json()
    _ATTEMPTS.append(attempts)
    if market == "twse":
        fields, rows, diag = _find_market_table(payload)
        return fields, rows, payload.get("stat"), diag
    fields, rows, diag = extract_table(payload)
    return fields, rows, (payload.get("stat") if isinstance(payload, dict) else None), diag


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--end", required=True, help="起算日 YYYYMMDD（往回取）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--market", choices=("twse", "tpex"), default="twse")
    ap.add_argument("--prior-common", type=int, default=None,
                    help="續跑時帶入前一段最後一天的普通股家數，讓接縫那天照樣走 "
                         "2%% 連續性判準。**不帶則本段首日只走下界檢查**，"
                         "報告會記明未做連續性比對。")
    ap.add_argument("--prior-common-source", default=None,
                    help="這個數字**從哪裡來**。複查方 2026-09-03 要求："
                         "報告只記下值，讀者無法分辨它是查來的真值，還是本段自己"
                         "首日的值——後者是拿自己比自己，**必然通過**。"
                         "例：'query on 2023-08-07 in temp DB'。")
    a = ap.parse_args(argv)
    is_tpex = (a.market == "tpex")
    first_day_floor = FIRST_DAY_MIN_COMMON_TPEX if is_tpex else FIRST_DAY_MIN_COMMON

    import psycopg2
    from psycopg2.extras import execute_values

    cfg = dict(host=os.getenv("DB_HOST", "localhost"),
               port=int(os.getenv("DB_PORT", "5432")),
               database=os.environ["POSTGRES_DB"],
               user=os.environ["POSTGRES_USER"],
               password=os.environ["POSTGRES_PASSWORD"])
    conn = psycopg2.connect(**cfg)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT current_database();")
        dbname = cur.fetchone()[0]
    print("寫入目標：%s @ %s:%s" % (dbname, cfg["host"], cfg["port"]))
    if "tmp" not in dbname and "test" not in dbname:
        print("[ABORT] 目標不是臨時資料庫——階段一不得寫入真實庫", file=sys.stderr)
        return 3

    cursor_date = _dt.datetime.strptime(a.end, "%Y%m%d").date()
    collected, requests_made, log = 0, 0, []
    pk_collisions, http_attempts = 0, 0
    # 【2026-09-01 審查者裁示】`prev_common` 每次執行都重置，
    # 所以逐日 2% 連續性判準**不會跨段執行**。以目前的中斷頻率，
    # 740 天會切成很多段，**每一個接縫都是一次沒被檢查的跳變** ——
    # 而那條判準正是「拿到的表變了」的主要防線。
    prev_common = a.prior_common
    print("=" * 78)
    while collected < a.days:
        if cursor_date.weekday() >= 5:          # 週末不發請求
            cursor_date -= _dt.timedelta(days=1)
            continue
        ds = cursor_date.strftime("%Y%m%d")
        if requests_made >= REQUEST_BUDGET:
            print("[STOP] 邏輯請求預算 %d 已用盡 —— **不自行加碼**，停止並回報。"
                  % REQUEST_BUDGET, file=sys.stderr)
            log.append({"date": ds, "outcome": "BUDGET_EXHAUSTED"})
            break
        requests_made += 1
        try:
            fields, rows, stat, diag = fetch_day(ds, a.market)
        except Exception as exc:
            http_attempts += 1 + TRANSPORT_RETRIES
            print("[STOP] %s 取得失敗：%s" % (ds, exc))
            log.append({"date": ds, "outcome": "ERROR", "detail": str(exc)})
            break
        http_attempts += _ATTEMPTS.pop() if _ATTEMPTS else 1
        if not rows:
            print("  %s  非交易日／無報價表（stat=%s）——不計入交易日配額" % (ds, stat))
            log.append({"date": ds, "outcome": "NO_TRADING_DAY", "stat": stat})
            cursor_date -= _dt.timedelta(days=1)
            time.sleep(random.uniform(*DELAY_RANGE))
            continue

        records, stats = (parse_tpex_report(fields, rows, cursor_date) if is_tpex
                          else parse_market_report(fields, rows, cursor_date))
        ok, bad, median = check_day(stats, records, ds, prev_common, first_day_floor)
        entry = {"date": ds, "outcome": "OK" if ok else "EXPECTATION_MISMATCH",
                 "stats": stats, "written": len(records), "median_turnover": median}
        if not ok:
            entry["mismatches"] = bad
            log.append(entry)
            print("  %s  **不符預期**：%s" % (ds, "；".join(bad)))
            print("[STOP] 依提案 §6.2a，不符即停止並回報，不自行解釋。")
            break

        # 【2026-09-01 PO 條件一】原本印的「寫入」是 `len(records)`——
        # **那是「嘗試寫入」的列數，不是實際插入的列數**，而 `cur.rowcount`
        # 從頭到尾沒有被讀取。
        #
        # TWSE 那輪不會出事：臨時 DB 是空的、同一天內代號唯一，兩數必然相等。
        # **但櫃買這輪條件變了**——目標庫裡已有 TWSE 的三年資料，
        # 而 PK 是 `(stock_id, trade_date)`。只要出現一組同代號同日，
        # `ON CONFLICT DO NOTHING` 會**靜默丟掉那一列，而日誌照樣印出完整數字**。
        #
        # C6 只證明了**單一一天**互斥（20260821，交集 0 檔）。
        # **740 天不是 1 天的 740 倍**——上櫃轉上市的過渡期就在這三年裡（C10 已指出）。
        #
        # 與 SB4 的 `push_count`、SB3 的一欄兩義、B4 的 grep 是同一個病：
        # **一個標籤說的事，和它實際量的事不是同一件。**
        # ⚠ **`cur.rowcount` 在 `execute_values` 之後不是「插入的列數」。**
        #   `execute_values` 預設 `page_size=100`，會把 887 列切成 9 個 statement，
        #   而 `rowcount` **只反映最後一批**。實測（2026-09-01，本檔第一版）：
        #   887 列全部成功寫入（DB 列數 766,506 → 767,393，差額 0、真實碰撞 0），
        #   `rowcount` 卻回報 87 —— 恰好是 887 - 800 = 最後一批的大小，
        #   於是檢查回報「800 列被靜默丟棄」，**而一列都沒被丟**。
        #
        #   **我寫來偵測「標籤與它實際量的事不同」的檢查，自己就是那個病。**
        #   這是本 SB 第七次同型。
        #
        #   改用 `RETURNING stock_id` + `fetch=True`：`DO NOTHING` 不會為衝突列
        #   產生 RETURNING 輸出，故回傳筆數**就是實際插入的列數**，且跨批正確。
        with conn.cursor() as cur:
            returned = execute_values(
                cur, INSERT_SQL,
                [tuple(r[c] for c in COLS) for r in records], fetch=True)
            inserted = len(returned)
        if inserted != len(records):
            # **不是警告，是停止**：靜默丟列在事後無法重建。
            gap = len(records) - inserted
            print("[STOP] %s 嘗試 %d 列、實際插入 %d 列，差額 %d ——"
                  "PK 碰撞，依提案不自行解釋，停止並回報"
                  % (ds, len(records), inserted, gap), file=sys.stderr)
            entry["outcome"] = "PK_COLLISION"
            entry["attempted"], entry["inserted"], entry["gap"] = (
                len(records), inserted, gap)
            log.append(entry)
            pk_collisions += 1
            break
        entry["attempted"], entry["inserted"] = len(records), inserted
        collected += 1
        prev_common = stats["rows_common_stock"]
        log.append(entry)
        # **「嘗試」與「插入」分兩欄印**——不要再用一個「寫入」蓋住兩件事。
        print("  %s  普通股 %4d｜嘗試 %4d｜插入 %4d｜無價 %d｜零量 %d｜中位數 %s  (%d/%d)"
              % (ds, stats["rows_common_stock"], len(records), inserted,
                 stats["rows_without_prices"], stats["rows_zero_volume"],
                 "{:,}".format(median), collected, a.days))
        cursor_date -= _dt.timedelta(days=1)
        time.sleep(random.uniform(*DELAY_RANGE))

    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT stock_id), "
                    "count(DISTINCT trade_date), min(trade_date), max(trade_date) "
                    "FROM candidate_prices;")
        summary = cur.fetchone()
    conn.close()

    print("=" * 78)
    print("交易日 %d／%d｜總請求 %d｜DB 列數 %s｜相異股票 %s｜相異日期 %s｜%s ~ %s"
          % (collected, a.days, requests_made, *summary))

    report = {
        "purpose": "UG-G2-SB9 階段一取數報告",
        "target_database": {"name": dbname, "host": cfg["host"], "port": cfg["port"],
                            "is_temporary": True},
        "environment": {"timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        "market": a.market,
        "segment": {
            "prior_common_supplied": a.prior_common,
            "prior_common_source": a.prior_common_source,
            "first_day_continuity_checked": a.prior_common is not None,
            "PROVENANCE_WARNING": (
                None if a.prior_common is None or a.prior_common_source
                else "⚠ **未記錄 `--prior-common` 的來源。** 這個值若取自本段"
                     "自己的首日，接縫就是拿自己比自己、**必然通過**；"
                     "若取自前一段的真值，才是真的檢查。"
                     "**兩者在報告輸出上完全相同** —— 故來源必須另外記。"),
            "note": ("本段首日已與前一段最後一天做 2%% 連續性比對（前值 %s）。"
                     % a.prior_common) if a.prior_common is not None else
                    ("⚠ **本段首日未做連續性比對**（未提供 `--prior-common`），"
                     "只走了下界檢查。續跑時應帶入前一段最後一天的普通股家數，"
                     "否則接縫是一次沒被檢查的跳變。"),
        },
        "expectations": {
            "max_daily_change_ratio": MAX_DAILY_CHANGE_RATIO,
            "first_day_min_common": first_day_floor,
            "first_day_floor_note": ("**只擋分頁碎片，不是對市場規模的宣稱。** "
                                     "TPEx 用 200（同判準 C3a），"
                                     "**刻意不用 C7 的量測值 887** —— "
                                     "先寫一個數字再拿它當判準就是在猜。"
                                     if is_tpex else
                                     "TWSE 800：3 年前的上市家數本來就較少，"
                                     "下界要能容納那個事實。"),
            "median_turnover": [EXPECT_MEDIAN_MIN, EXPECT_MEDIAN_MAX],
            "note": "提案 §6.2a，取數前寫死。2026-09-01 由絕對區間改為相對變動率"
                    "——絕對區間是兩天觀測推出來的，在跨年度資料上必然誤報。"},
        "trading_days_collected": collected, "trading_days_requested": a.days,
        # **雙軌計數**（沿用 TPEx 端點驗證的寫法）：邏輯請求＝要問的問題數；
        # HTTP 嘗試＝對政府單位服務造成的實際負載。**兩個都記，不要只留一個。**
        "logical_requests_made": requests_made,
        "http_attempts_made": http_attempts,
        "logical_request_budget": REQUEST_BUDGET,
        # **PK 碰撞次數**：預期 0。非 0 代表 `ON CONFLICT DO NOTHING` 靜默丟過列，
        # 而那在事後無法重建 —— 故一發生即停止。
        "pk_collisions": pk_collisions,
        "db_summary": {"rows": summary[0], "distinct_stocks": summary[1],
                       "distinct_dates": summary[2],
                       "min_date": str(summary[3]), "max_date": str(summary[4])},
        "per_day_log": log,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    print("報告已寫入：%s" % a.out)
    return 0 if collected == a.days else 1


if __name__ == "__main__":
    raise SystemExit(main())
