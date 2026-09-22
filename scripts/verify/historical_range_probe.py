# -*- coding: utf-8 -*-
"""UG-G2-SB6 延伸回補前置：歷史區間端點形態探測（E1–E4）。

**判準於觸網前寫死，跑完只做比對。** 不因結果調整判準、不重試至成功。

**為什麼需要這一步**：`UG-G2-SB9` 只驗證了端點在 **2023-08 之後**的回應格式。
**2022 與 2021 的欄名、日期格式、表結構是否相同，完全未知。**
直接把 SB9 的解析器套到歷史區間，等於假設「格式沒變過」——
而那個假設**一旦不成立，失敗的形式會是「找不到表」或「欄位對不上」，
與「端點不可用」在輸出上一模一樣**（本專案已有多次同型紀錄）。

**為什麼連 2021 一起探**：四次請求就能知道天花板在哪。
若 2021 也乾淨，日後要推到 `PURGED_WALK_FORWARD_SPEC.md` §3.3 的理想值（5 年），
**成本就是已知的，不必再探一次**。
**這一次探測，是為了讓下一次決定不需要探測。**

用法：
    python scripts/verify/historical_range_probe.py --out <path>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.verify.twse_market_endpoint_check import (  # noqa: E402
    DELAY_RANGE, ENDPOINT as TWSE_ENDPOINT, TIMEOUT_SECONDS, USER_AGENT,
    _find_market_table,
)
from scripts.verify.tpex_endpoint_check import (  # noqa: E402
    TPEX_FIELD_PATTERNS, candidate_urls as tpex_candidate_urls, extract_table,
)

PASS, FAIL, NOT_EXECUTED, INCONCLUSIVE = "PASS", "FAIL", "NOT EXECUTED", "INCONCLUSIVE"

# ---------------------------------------------------------------------------
# 執行參數（觸網前寫死，不得於執行時調整）
# ---------------------------------------------------------------------------
# **硬上限 4**：TWSE／TPEx × 兩個歷史日期。逾此拋例外。
REQUEST_BUDGET = 4
TRANSPORT_RETRIES = 5
TRANSPORT_BACKOFF = (5, 10, 20, 40, 60)
SERVER_ERROR_RETRIES = 1
SERVER_ERROR_BACKOFF = 60

# 探測日期。2022-08-01 與 2021-08-02 皆為週一。
# **若當日非交易日**，回應會是空表——那是探測結果，不是端點失敗，
# 依賴資料列的判準記 NOT_EXECUTED，不記 FAIL。
PROBE_DATES = ["2022-08-01", "2021-08-02"]

# ---------------------------------------------------------------------------
# E2 的比對基準：SB9 實測的欄名，**逐字**
# ---------------------------------------------------------------------------
# TWSE：`G2_SB9_twse_endpoint_evidence.json` 的 field_names（16 欄）
TWSE_BASELINE_FIELDS = [
    "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價",
    "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價",
    "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
]
# TPEx：`G2_SB9_tpex_endpoint_evidence_raw_capture.json` 的 field_names（17 欄）
# **注意欄名帶前後空白與 `<br>`** —— 那是實測形態，比對必須逐字。
TPEX_BASELINE_FIELDS = [
    "代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低",
    "成交股數  ", " 成交金額(元)", " 成交筆數 ", "最後買價",
    "最後買量<br>(張數)", "最後賣價", "最後賣量<br>(張數)",
    "發行股數 ", "次日漲停價 ", "次日跌停價",
]

_COMMON = re.compile(r"^[1-9]\d{3}$")


class RequestBudget:
    """超出上限即拋例外。**不是提醒，是硬上限。**"""

    def __init__(self, limit):
        self.limit, self.used, self.http_attempts = limit, 0, 0

    def spend(self, what):
        if self.used >= self.limit:
            raise RuntimeError("邏輯請求預算 %d 已用盡，拒絕發出：%s" % (self.limit, what))
        self.used += 1


def evaluate(obs):
    """**純函式**：只吃觀測、不發請求。可用 fixture 測試（§9A.2）。"""
    res = {}

    def put(k, verdict, detail, blocked_by=None):
        res[k] = {"verdict": verdict, "detail": detail, "blocked_by": blocked_by}

    for mkt in ("twse", "tpex"):
        m = obs.get(mkt) or {}
        base = TWSE_BASELINE_FIELDS if mkt == "twse" else TPEX_BASELINE_FIELDS
        a, b = m.get(PROBE_DATES[0]) or {}, m.get(PROBE_DATES[1]) or {}

        # --- E1 可取得 ---
        oks = [d for d in (a, b) if d.get("status_code") == 200 and d.get("json_ok")]
        if not oks:
            put("E1_" + mkt, FAIL,
                "兩個歷史日期皆未取得可解析的 200：%s"
                % [(d.get("date"), d.get("status_code"), d.get("error")) for d in (a, b)])
            for k in ("E2_", "E3_"):
                put(k + mkt, NOT_EXECUTED, "E1 未通過", blocked_by="E1_" + mkt)
            continue
        put("E1_" + mkt, PASS,
            "%d/2 個歷史日期回 HTTP 200 且可解析" % len(oks))

        # --- E2 欄名逐字相同 ---
        withrows = [d for d in oks if d.get("field_names")]
        if not withrows:
            put("E2_" + mkt, NOT_EXECUTED,
                "回應可解析但無資料表（可能為非交易日：%s）"
                % [(d.get("date"), d.get("stat")) for d in oks], blocked_by=None)
        else:
            bad = [(d["date"], d["field_names"]) for d in withrows
                   if d["field_names"] != base]
            put("E2_" + mkt, PASS if not bad else FAIL,
                "欄名與 SB9 基準逐字相同" if not bad else
                "**欄名不同**，解析器不可直接沿用：%s" % bad)

        # --- E2b 解析器接不接得住（與 E2 並存，問的是不同的問題）---
        #
        # **E2 是偵測器**（回應形態變了就叫）；**E2b 是閘門**（接不住就停）。
        # 把 E2 改成 E2b 等於用閘門取代偵測器 —— 那才是「放寬判準」的真正代價：
        # 不是程序問題，而是**永久少一個能發現未知變更的東西**。
        #
        # E2 FAIL 記錄了「回應變了」，卻沒有任何一條判準記錄「而我們仍然接得住」。
        # 沒有 E2b，下一個人讀到 `E2 FAIL` 加一句「已評估影響為零」，
        # **只能選擇相信那句評估**。
        samples = [d for d in oks if d.get("sample_rows_verdict") is not None]
        if not samples:
            put("E2b_" + mkt, NOT_EXECUTED, "無樣本可供解析", blocked_by=None)
        else:
            bad = [(d["date"], d["sample_rows_verdict"]) for d in samples
                   if not d["sample_rows_verdict"].get("ok")]
            put("E2b_" + mkt, PASS if not bad else FAIL,
                "解析器對歷史樣本：語意鍵全數對映且 stats 守恆"
                if not bad else "**解析器接不住**：%s" % bad)

        # --- E3 日期正確對映 ---
        if len(withrows) < 2:
            put("E3_" + mkt, NOT_EXECUTED,
                "需兩個日期皆有資料表才能比對（實得 %d）" % len(withrows),
                blocked_by=None)
        else:
            same = withrows[0].get("body_digest") == withrows[1].get("body_digest")
            dates_ok = all(_date_matches(d.get("table_date"), d["date"])
                           for d in withrows if d.get("table_date"))
            detail = ("兩個日期回應內容%s；回應內日期%s"
                      % ("**相同——日期參數未被吃進去**" if same else "不同",
                         "與請求相符" if dates_ok else "**與請求不符**"))
            put("E3_" + mkt, FAIL if (same or not dates_ok) else PASS, detail)

    # --- E4 同日代號互斥（只用第一個探測日）---
    d0 = PROBE_DATES[0]
    ta = ((obs.get("twse") or {}).get(d0) or {})
    tb = ((obs.get("tpex") or {}).get(d0) or {})
    if not ta.get("codes") or not tb.get("codes"):
        put("E4", NOT_EXECUTED, "需兩市場於 %s 皆有資料表" % d0, blocked_by=None)
    else:
        inter = sorted({c for c in ta["codes"] if _COMMON.match(c)}
                       & {c for c in tb["codes"] if _COMMON.match(c)})
        put("E4", PASS if not inter else FAIL,
            "交集 %d 檔%s" % (len(inter), ("：%s" % inter[:20]) if inter else "（互斥）"))
        # **保存交集結果**，使 `--replay` 可以重算 E4。
        # 2026-09-03 事件：報告只存 `code_set_sizes`（大小），不存交集，
        # 於是 replay 把一個已取得的 PASS 降成 NOT EXECUTED 並覆蓋了原判定。
        # **實跑必須保存足以重算每一條判準的東西** —— 大小不夠，交集才夠。
        res["E4"]["intersection"] = inter
    return res


def _date_matches(observed, iso):
    """回應內日期可能是民國年（115/08/21）或西元（20220801）。"""
    a = re.sub(r"\D", "", str(observed))
    b = re.sub(r"\D", "", str(iso))
    if len(b) != 8:
        return False
    roc = "%d%s" % (int(b[:4]) - 1911, b[4:])
    return a in (b, roc)


REQUIRED_SEMANTIC_KEYS = ("amount", "ask", "bid", "close", "code",
                          "high", "low", "name", "open", "txn", "volume")


def check_parser(market, field_names, rows, trade_date):
    """E2b：解析器接不接得住。**純函式，可用 fixture 測試。**

    known-FAIL：刪掉樣本中的「成交金額(元)」欄 → 必須回傳 ok=False。
    """
    out = {"market": market}
    try:
        if market == "tpex":
            from src.extractors.tpex_market_report import _map_fields, parse_tpex_report
            mapping = _map_fields(field_names)
            missing = [k for k in REQUIRED_SEMANTIC_KEYS if k not in mapping]
            recs, st = parse_tpex_report(field_names, rows, trade_date)
        else:
            from src.extractors.twse_market_report import parse_market_report
            recs, st = parse_market_report(field_names, rows, trade_date)
            missing = []
        conserved = (st["rows_common_stock"] + st["rows_excluded_by_code_shape"]
                     == st["rows_total"])
        out.update({"mapped_keys_missing": missing, "stats_conserved": conserved,
                    "rows_in": len(rows), "records_out": len(recs),
                    "ok": (not missing) and conserved})
    except Exception as exc:
        out.update({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    return out


CRITERIA_ORDER = ("E1_twse", "E2_twse", "E2b_twse", "E3_twse",
                  "E1_tpex", "E2_tpex", "E2b_tpex", "E3_tpex", "E4")


def overall(res):
    if any(res[k]["verdict"] == FAIL for k in CRITERIA_ORDER):
        return FAIL
    if any(res[k]["verdict"] == NOT_EXECUTED and res[k].get("blocked_by") is None
           for k in CRITERIA_ORDER):
        return INCONCLUSIVE
    return PASS if all(res[k]["verdict"] == PASS for k in CRITERIA_ORDER) else INCONCLUSIVE


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", default=None,
                    help="從先前的探測報告離線重評，**零請求**。"
                         "用於新增判準後不必重新觸網。")
    a = ap.parse_args(argv)

    if a.replay:
        # **replay 的輸出不得寫回輸入路徑** —— 2026-09-03 事件的直接成因。
        if os.path.abspath(a.replay) == os.path.abspath(a.out):
            print("[ABORT] --replay 的輸入與 --out 相同。"
                  "重評若無法重算某條判準，會靜默覆蓋掉實跑取得的判定。")
            return 3
        with open(a.replay, encoding="utf-8") as fh:
            prev = json.load(fh)
        robs = {}
        for mkt, days in (prev.get("observations") or {}).items():
            robs[mkt] = {}
            for iso, rec in days.items():
                rec = dict(rec)
                f = rec.get("field_names")
                sm = rec.get("sample_rows_verbatim")
                if f and sm:
                    rec["sample_rows_verdict"] = check_parser(
                        mkt, f, [[s.get(k) for k in f] for s in sm],
                        _dt.datetime.strptime(iso, "%Y-%m-%d").date())
                robs[mkt][iso] = rec
        rres = evaluate(robs)
        # **E4 需要完整代號集合，而報告刻意不保存 `codes`（避免膨脹）。**
        # 若 replay 算不出來，**沿用實跑時的判定並標明來源** ——
        # 讓它降成 NOT EXECUTED 會把一個已經取得的 PASS 弄丟，
        # 那是 replay 引入的回歸，不是新發現。
        prev_e4 = (prev.get("criteria") or {}).get("E4")
        if rres["E4"]["verdict"] == NOT_EXECUTED and prev_e4 and                 prev_e4.get("verdict") != NOT_EXECUTED:
            rres["E4"] = dict(prev_e4)
            rres["E4"]["detail"] = (
                prev_e4["detail"] + "　⟵ **沿用實跑判定，非本次重評**："
                "報告刻意不保存完整 `codes`（避免膨脹），故 replay 無法重算。"
                "代號集合大小仍記於 `code_set_sizes`。")
        rv = overall(rres)
        print("=" * 78)
        print("離線重評（--replay，零請求）")
        for k in CRITERIA_ORDER:
            print("  %-9s %-12s %s" % (k, rres[k]["verdict"], rres[k]["detail"][:100]))
        print("  整體：%s" % rv)
        prev["criteria"] = rres
        prev["overall"] = rv
        prev["REPLAY_NOTE"] = ("本次為 `--replay` 離線重評（新增 E2b 後），**未發出任何請求**；"
                               "計數欄維持先前值。")
        for mkt, days in (prev.get("observations") or {}).items():
            for iso, rec in days.items():
                v = robs[mkt][iso].get("sample_rows_verdict")
                if v is not None:
                    rec["sample_rows_verdict"] = v
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(prev, fh, ensure_ascii=False, indent=2, default=str)
            fh.write(chr(10))
        print("報告已寫入：%s（零請求）" % a.out)
        return 0 if rv == PASS else 1
    import hashlib
    import requests

    budget = RequestBudget(REQUEST_BUDGET)
    obs = {"twse": {}, "tpex": {}}

    def _get(url, label):
        """傳輸層失敗於同一邏輯請求內有界重試；5xx 退避後最多再試 1 次。"""
        last = None
        for i in range(1 + TRANSPORT_RETRIES):
            budget.http_attempts += 1
            try:
                return requests.get(url, headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"},
                                    timeout=TIMEOUT_SECONDS)
            except Exception as exc:
                last = exc
                if i < TRANSPORT_RETRIES:
                    w = TRANSPORT_BACKOFF[min(i, len(TRANSPORT_BACKOFF) - 1)]
                    print("    傳輸層失敗（%s…），退避 %d 秒後重試 %d/%d"
                          % (str(exc)[:60], w, i + 1, TRANSPORT_RETRIES))
                    time.sleep(w)
        raise RuntimeError("傳輸層失敗，重試 %d 次後仍未取得回應：%s"
                           % (TRANSPORT_RETRIES, last))

    def probe(mkt, iso):
        budget.spend("%s @ %s" % (mkt, iso))
        rec = {"market": mkt, "date": iso, "json_ok": False}
        url = (TWSE_ENDPOINT.format(date=iso.replace("-", "")) if mkt == "twse"
               else dict(tpex_candidate_urls(iso))["www_afterTrading_otc"])
        rec["url"] = url
        try:
            r = _get(url, rec["date"])
            if r.status_code in (403, 429):
                rec["status_code"] = r.status_code
                rec["error"] = "HTTP %d（服務拒絕）—— 硬停" % r.status_code
                rec["fatal"] = True
                return rec
            if r.status_code >= 500:
                print("    %s %s HTTP %d —— 退避 %d 秒後再試 1 次"
                      % (mkt, iso, r.status_code, SERVER_ERROR_BACKOFF))
                time.sleep(SERVER_ERROR_BACKOFF)
                r = _get(url, rec["date"])
            rec["status_code"] = r.status_code
            rec["content_type"] = r.headers.get("Content-Type")
            r.raise_for_status()
            body = r.text
            rec["body_digest"] = hashlib.sha256(body.encode()).hexdigest()[:16]
            rec["body_bytes"] = len(body)
            # **失敗路徑也保存原始 body**（SB9 的教訓：失敗時資訊量最大，卻最不可能被保存）
            rec["body_head_verbatim"] = body[:4000]
            payload = r.json()
            rec["json_ok"] = True
            if mkt == "twse":
                f, rows, diag = _find_market_table(payload)
                rec["stat"] = payload.get("stat") if isinstance(payload, dict) else None
            else:
                f, rows, diag = extract_table(payload)
                rec["stat"] = payload.get("stat") if isinstance(payload, dict) else None
            rec["diag"] = diag
            rec["field_names"] = f
            rec["row_count"] = len(rows) if rows else 0
            rec["table_date"] = (diag or {}).get("table_date") or (diag or {}).get("payload_date")
            if rows and f:
                rec["sample_rows_verbatim"] = [dict(zip(f, r_)) for r_ in rows[:3]]
                rec["sample_rows_verdict"] = check_parser(
                    mkt, f, rows[:200],
                    _dt.datetime.strptime(iso, "%Y-%m-%d").date())
                ic = next((i for i, x in enumerate(f)
                           if re.search(r"證券代號|股票代號|^代號$", str(x).strip())), None)
                if ic is not None:
                    rec["codes"] = sorted({str(r_[ic]).strip() for r_ in rows})
        except Exception as exc:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        return rec

    print("=" * 78)
    print("歷史區間探測｜邏輯請求上限 %d｜節流 %.1f-%.1f 秒" % (REQUEST_BUDGET, *DELAY_RANGE))
    print("探測日期：%s" % PROBE_DATES)
    stop = False
    for mkt in ("twse", "tpex"):
        for iso in PROBE_DATES:
            rec = probe(mkt, iso)
            obs[mkt][iso] = rec
            print("  [%s %s] status=%s rows=%s %s"
                  % (mkt, iso, rec.get("status_code"), rec.get("row_count"),
                     rec.get("error", "")))
            if rec.get("fatal"):
                print("[STOP] 服務拒絕，硬停並回報。")
                stop = True
                break
            time.sleep(random.uniform(*DELAY_RANGE))
        if stop:
            break

    res = evaluate(obs)
    verdict = overall(res)
    print("-" * 78)
    for k in CRITERIA_ORDER:
        print("  %-8s %-12s %s" % (k, res[k]["verdict"], res[k]["detail"][:110]))
    print("  整體：%s" % verdict)

    slim = {m: {d: {k: v for k, v in r.items() if k != "codes"}
                for d, r in obs[m].items()} for m in obs}
    report = {
        "purpose": "UG-G2-SB6 延伸回補前置：歷史區間端點形態探測",
        "environment": {"timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        "protocol": {"logical_request_budget": REQUEST_BUDGET,
                     "logical_requests_used": budget.used,
                     "http_attempts": budget.http_attempts,
                     "probe_dates": PROBE_DATES,
                     "note": "判準於觸網前寫死。403/429 硬停；5xx／傳輸層有界重試。"},
        "baseline_fields": {"twse": TWSE_BASELINE_FIELDS, "tpex": TPEX_BASELINE_FIELDS},
        "criteria": res, "overall": verdict, "observations": slim,
        "code_set_sizes": {m: {d: len(r.get("codes") or []) for d, r in obs[m].items()}
                           for m in obs},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
        fh.write(chr(10))
    print("報告已寫入：%s（邏輯請求 %d/%d｜HTTP 嘗試 %d）"
          % (a.out, budget.used, REQUEST_BUDGET, budget.http_attempts))
    return 0 if verdict == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
