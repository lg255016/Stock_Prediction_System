# -*- coding: utf-8 -*-
"""UG-G2-SB9 階段一：證交所全市場日報表端點可用性驗證（B1–B5 判準 + B6 量測）。

**判準在寫下之前就已定死**（Gate A 提案 §5，PO 2026-08-31 核准），
**不得因結果不理想而調整判準後重跑**。

設計與 `dcard_availability_check.py` 同一套，理由相同：

1. **判定邏輯與網路存取完全分離**——`evaluate()` 是純函數，
   因此判準可以在**一次請求都沒發生**的情況下被測試（`CLAUDE.md` §9A.2）。
2. **`--dry-run` 吃 fixture 檔**，走與正式執行完全相同的 `evaluate()`。
3. **請求預算是會拋例外的物件**，不是一段要記得遵守的註解。

**B6 是量測項，不參與判定**——它的產出要當
「停牌／零成交列不得被當成 0 元成交金額」那個測試的 fixture，
**用真實觀察到的形態，不用想像的形態**。

用法：
    python scripts/verify/twse_market_endpoint_check.py --date 20260821 \\
        --out doc/upgrade/gates/evidence/G2_SB9_twse_endpoint_evidence.json
    python scripts/verify/twse_market_endpoint_check.py --dry-run fixture.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import random
import re
import sys
import time

# ---------------------------------------------------------------------------
# 固定執行參數（提案 §5.1；不得於執行時調整）
# ---------------------------------------------------------------------------
# 候選端點：證交所「每日收盤行情」全市場日報表。
# 現有 twse_scraper 用的是 STOCK_DAY（一次一檔、回傳該檔一個月），
# 用它取全市場需要 檔數 × 月數 次請求（1000 檔 × 3 年 ≈ 36,000 次），不可行。
ENDPOINT = ("https://www.twse.com.tw/exchangeReport/MI_INDEX"
            "?response=json&date={date}&type=ALL")

TIMEOUT_SECONDS = 15
MAX_RETRIES = 3
BACKOFF_SECONDS = (2, 4, 8)
DELAY_RANGE = (3.0, 5.0)          # 比 PTT 的 1.5–3.0 保守：對象是政府單位服務
MAX_LOGICAL_REQUESTS = 3
MAX_HTTP_ATTEMPTS = MAX_LOGICAL_REQUESTS * MAX_RETRIES
MIN_ROWS = 500                    # B2：全市場規模的下界

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

PASS, FAIL, NOT_EXECUTED, MEASURED = "PASS", "FAIL", "NOT EXECUTED", "MEASURED"
INCONCLUSIVE = "INCONCLUSIVE"

# 欄位語意 → 可能的中文欄名（證交所欄名以中文表示）。
# **刻意不寫死單一名稱**：欄名若變動，證據要能區分「端點還在但欄名變了」
# 與「端點消失」——前者可修，後者不可修（提案 §5.3）。
# 【UG-G2-SB7】`FIELD_PATTERNS`／`_normalise_field_name`／`_match_fields`／
# `_find_market_table` 已**搬移**至 `src/extractors/market_report_table.py`——
# 生產路徑（`market_report_fetcher`）需要同一份實作，而複製一份到 `src/`
# 就是 DEC-032 §Remaining Risks 那句「同一個規則實作在一支腳本而不在另一支」。
# **本檔的公開名稱與行為皆不變**，呼叫端（含 `tpex_endpoint_check.extract_table`）無需修改。
from src.extractors.market_report_table import (  # noqa: E402
    FIELD_PATTERNS, _find_market_table, _match_fields, _normalise_field_name,
)


def _is_parseable_number(raw):
    """證交所數值欄含千分位、可能出現 `--`／`X`／全形字元。

    **回傳 (可解析, 正規化後的字串)** —— 不可解析時保留原字串，
    因為 B4 要求記錄「非數值標記的**實際出現形式**」，
    那些東西不會讓解析報錯，只會讓數字**安靜地錯**。
    """
    if raw is None:
        return False, None
    s = str(raw).strip().replace(",", "").replace("　", "").replace(" ", "")
    # 全形數字轉半形
    s = s.translate(str.maketrans("０１２３４５６７８９．－", "0123456789.-"))
    if s in ("", "--", "-", "X", "x"):
        return False, str(raw)
    try:
        float(s)
        return True, s
    except ValueError:
        return False, str(raw)


def evaluate(obs: dict) -> dict:
    """由觀察紀錄推出 B1–B5 三態 + B6 量測。純函數。"""
    res = {}
    r = obs.get("request") or {}

    # --- B1 端點連通性 ---
    if not r.get("attempted"):
        res["B1"] = {"verdict": NOT_EXECUTED, "blocked_by": None,
                     "detail": "請求未發出"}
    else:
        res["B1"] = {"verdict": PASS if r.get("status_code") == 200 else FAIL,
                     "detail": "HTTP %s" % r.get("status_code")}

    # --- B2 可解析且非空 ---
    rows = r.get("rows")
    if res["B1"]["verdict"] != PASS:
        res["B2"] = {"verdict": NOT_EXECUTED, "blocked_by": "B1", "detail": "B1 未通過"}
    elif not r.get("json_parsed"):
        res["B2"] = {"verdict": FAIL, "detail": "回應無法以 JSON 解析"}
    elif rows is None:
        res["B2"] = {"verdict": FAIL,
                     "detail": "找不到全市場報價資料表（頂層 keys: %s）"
                               % (r.get("top_level_keys") or [])}
    elif len(rows) < MIN_ROWS:
        res["B2"] = {"verdict": FAIL,
                     "detail": "資料列數 %d < %d —— 拿到的可能不是全市場"
                               % (len(rows), MIN_ROWS)}
    else:
        res["B2"] = {"verdict": PASS, "detail": "資料列數 %d" % len(rows)}

    # --- B3 欄位齊備 ---
    fields = r.get("field_names")
    if res["B2"]["verdict"] != PASS:
        res["B3"] = {"verdict": NOT_EXECUTED, "blocked_by": _root(res, "B2"),
                     "blocked_chain": "B2", "detail": "B2 未通過，無資料可檢"}
        mapping = {}
    else:
        mapping, missing = _match_fields(fields)
        core_missing = [m for m in missing if m != "amount"]   # amount 由 B5 單獨判
        res["B3"] = {
            "verdict": PASS if not core_missing else FAIL,
            "detail": ("證券代號／收盤價／成交股數／開高低價皆可對映"
                       if not core_missing else "缺少語意欄位：%s" % core_missing),
            "field_mapping": mapping,
        }

    # --- B4 型別可用 ---
    if res["B3"]["verdict"] != PASS:
        res["B4"] = {"verdict": NOT_EXECUTED, "blocked_by": _root(res, "B3"),
                     "blocked_chain": "B3", "detail": "B3 未通過"}
    else:
        sample = rows[0]
        checks, markers = {}, {}
        for key in NUMERIC_FIELDS:
            if key not in mapping:
                continue
            ok, norm = _is_parseable_number(sample[mapping[key]])
            checks[key] = {"raw": sample[mapping[key]], "parseable": ok,
                           "normalized": norm}
        # 掃描全表，記錄非數值標記的**實際出現形式**（B4 的核心要求）
        for key in NUMERIC_FIELDS:
            if key not in mapping:
                continue
            seen = {}
            for row in rows:
                ok, _ = _is_parseable_number(row[mapping[key]])
                if not ok:
                    v = str(row[mapping[key]])
                    seen[v] = seen.get(v, 0) + 1
            if seen:
                markers[key] = seen
        code_ok = mapping.get("code") is not None and \
            isinstance(str(sample[mapping["code"]]), str)
        bad = [k for k, v in checks.items() if not v["parseable"]]
        res["B4"] = {
            "verdict": PASS if (code_ok and not bad) else FAIL,
            "detail": ("首列數值欄皆可解析，代號可轉 str"
                       if (code_ok and not bad) else "首列不可解析欄位：%s" % bad),
            "first_row_checks": checks,
            "non_numeric_markers": markers,   # ← 實際出現形式，不是想像的
        }

    # --- B5 成交金額（本 SB 最重要的判準）---
    if res["B3"]["verdict"] == NOT_EXECUTED:
        res["B5"] = {"verdict": NOT_EXECUTED, "blocked_by": _root(res, "B3"),
                     "blocked_chain": "B3", "detail": "無資料可檢"}
    elif "amount" not in mapping:
        res["B5"] = {
            "verdict": FAIL,
            "detail": "回應未直接提供成交金額欄位。**不得自行改用 close × volume**"
                      "——那是近似而非等價（真實成交金額由盤中逐筆價累計），"
                      "而流動性排名正是要區分「大額成交」與「小額頻繁成交」。停止並回報 PO。",
        }
    else:
        ok, norm = _is_parseable_number(rows[0][mapping["amount"]])
        res["B5"] = {"verdict": PASS if ok else FAIL,
                     "detail": "成交金額欄存在且首列可解析（%s）" % norm if ok
                               else "成交金額欄存在但首列不可解析：%r"
                                    % rows[0][mapping["amount"]],
                     "field_name": (r.get("field_names") or [None] * 99)[mapping["amount"]]}

    # --- 整體判定：先看儀器，再看端點（比照 dcard 的 INCONCLUSIVE）---
    keys = ("B1", "B2", "B3", "B4", "B5")
    instrument = [k for k in keys
                  if res[k]["verdict"] == NOT_EXECUTED and res[k].get("blocked_by") is None]
    if instrument:
        overall = INCONCLUSIVE
    elif all(res[k]["verdict"] == PASS for k in keys):
        overall = PASS
    else:
        overall = FAIL

    # --- B6 停牌／零成交列的形態（量測項，不參與判定）---
    res["B6"] = _measure_halted(rows, mapping) if res["B3"].get("verdict") == PASS else {
        "verdict": NOT_EXECUTED, "blocked_by": _root(res, "B3"),
        "detail": "無資料可量測"}

    out = {"criteria": res, "overall": overall,
           "overall_note": "B6 為量測項，不參與整體判定"}
    if instrument:
        out["instrument_failures"] = instrument
        out["inconclusive_reason"] = "以下判準無上游阻斷卻仍未執行：%s" % instrument
    return out


def _root(res, proximate):
    """回溯根因判準而非最近一層（與 dcard 檢查同一設計）。"""
    seen, cur = [], proximate
    while cur and res.get(cur, {}).get("verdict") == NOT_EXECUTED:
        seen.append(cur)
        nxt = res[cur].get("blocked_by")
        if not nxt or nxt in seen:
            break
        cur = nxt
    return cur


def _measure_halted(rows, mapping) -> dict:
    """B6：停牌／零成交列的**實際**形態。

    這份輸出要當「停牌／零成交不得被當成 0 元成交金額」那個測試的 fixture。
    **停牌股的「成交金額 0」與「無資料」必須可區分**——否則流動性排名會把
    停牌股當成「流動性極低但有效」的樣本，而**排名結果看起來完全正常**。
    """
    if not rows or "volume" not in mapping:
        return {"verdict": NOT_EXECUTED, "detail": "無資料可量測"}
    zero_vol, non_numeric, samples = 0, 0, []
    for row in rows:
        ok, norm = _is_parseable_number(row[mapping["volume"]])
        is_zero = ok and float(norm) == 0.0
        if not ok:
            non_numeric += 1
        elif is_zero:
            zero_vol += 1
        if (not ok or is_zero) and len(samples) < 5:
            samples.append({
                "code": row[mapping["code"]] if "code" in mapping else None,
                "raw_row": row,
            })
    return {
        "verdict": MEASURED,
        "rows_examined": len(rows),
        "zero_volume_rows": zero_vol,
        "non_numeric_volume_rows": non_numeric,
        "samples": samples,
        "note": "量測項，不參與判定。samples 為真實觀察到的形態，"
                "供 §9 第 4 項測試作為 fixture——不得改用想像的形態。",
    }


# ---------------------------------------------------------------------------
# 網路存取
# ---------------------------------------------------------------------------
class RequestBudget:
    """把「還能發幾次請求」變成會拋例外的物件，而不是要記得遵守的註解。"""

    def __init__(self, max_logical, max_attempts):
        self.max_logical, self.max_attempts = max_logical, max_attempts
        self.logical_used = self.attempts_used = 0

    def take_logical(self, label):
        if self.logical_used >= self.max_logical:
            raise RuntimeError("邏輯請求已達上限 %d（嘗試 %s）" % (self.max_logical, label))
        self.logical_used += 1

    def take_attempt(self):
        if self.attempts_used >= self.max_attempts:
            raise RuntimeError("HTTP 嘗試次數已達上限 %d" % self.max_attempts)
        self.attempts_used += 1

    def as_dict(self):
        return {"logical_requests_used": self.logical_used,
                "logical_requests_max": self.max_logical,
                "http_attempts_used": self.attempts_used,
                "http_attempts_max": self.max_attempts}



def collect(date_str: str) -> dict:
    import requests

    budget = RequestBudget(MAX_LOGICAL_REQUESTS, MAX_HTTP_ATTEMPTS)
    url = ENDPOINT.format(date=date_str)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    rec = {"attempted": True, "url": url, "date": date_str,
           "intended_headers": dict(headers), "sent_headers": None,
           "attempts": 0, "status_code": None, "elapsed_seconds": None,
           "json_parsed": False, "error": None}

    budget.take_logical("market_report")
    for attempt in range(1, MAX_RETRIES + 1):
        budget.take_attempt()
        rec["attempts"] = attempt
        t0 = time.time()
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except Exception as exc:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
            rec["elapsed_seconds"] = round(time.time() - t0, 3)
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SECONDS[attempt - 1])
                continue
            return {"request": rec, "budget": budget.as_dict()}

        rec["elapsed_seconds"] = round(time.time() - t0, 3)
        rec["status_code"] = resp.status_code
        rec["final_url"] = resp.url
        rec["response_headers"] = dict(resp.headers)
        try:
            rec["sent_headers"] = dict(resp.request.headers)
        except AttributeError:
            rec["sent_headers"] = None

        # 限流／封鎖：立即停止。**不重試至成功、不調整節流參數後重跑**（提案 §5.5）。
        if resp.status_code in (403, 429) or resp.status_code >= 500:
            rec["error"] = "HTTP %d —— 依提案 §5.5 立即停止，不重試至成功" % resp.status_code
            rec["body_prefix"] = resp.text[:500]
            return {"request": rec, "budget": budget.as_dict()}

        try:
            payload = resp.json()
            rec["json_parsed"] = True
        except Exception as exc:
            rec["parse_error"] = "%s: %s" % (type(exc).__name__, exc)
            rec["body_prefix"] = resp.text[:500]
            low = rec["body_prefix"].lower()
            if "<title>" in low:
                s = low.index("<title>") + 7
                e = low.find("</title>", s)
                rec["html_title"] = rec["body_prefix"][s:e if e > 0 else None]
            return {"request": rec, "budget": budget.as_dict()}

        fields, rows, diag = _find_market_table(payload)
        rec.update(diag)
        rec["stat"] = payload.get("stat") if isinstance(payload, dict) else None
        rec["field_names"] = fields
        rec["rows"] = rows
        if rows:
            rec["row_count"] = len(rows)
            rec["first_row"] = rows[0]
        return {"request": rec, "budget": budget.as_dict()}

    return {"request": rec, "budget": budget.as_dict()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print(result, obs):
    print("=" * 74)
    print("UG-G2-SB9 階段一：證交所全市場端點驗證")
    print("=" * 74)
    for k in ("B1", "B2", "B3", "B4", "B5"):
        it = result["criteria"][k]
        b = it.get("blocked_by")
        print("  %-3s %-13s %s%s" % (k, it["verdict"], it.get("detail", ""),
                                     "（阻斷來源：%s）" % b if b else ""))
    b6 = result["criteria"]["B6"]
    if b6.get("verdict") == MEASURED:
        print("  B6  MEASURED      零成交 %s 列、非數值 %s 列 / 共 %s 列（不參與判定）"
              % (b6["zero_volume_rows"], b6["non_numeric_volume_rows"], b6["rows_examined"]))
    else:
        print("  B6  %-13s %s（不參與判定）" % (b6.get("verdict"), b6.get("detail", "")))
    print("-" * 74)
    print("  整體判定：%s" % result["overall"])
    if obs.get("budget"):
        bd = obs["budget"]
        print("  請求用量：邏輯 %d/%d，HTTP 嘗試 %d/%d"
              % (bd["logical_requests_used"], bd["logical_requests_max"],
                 bd["http_attempts_used"], bd["http_attempts_max"]))
    print("=" * 74)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UG-G2-SB9 證交所全市場端點驗證")
    ap.add_argument("--date", help="交易日，格式 YYYYMMDD")
    ap.add_argument("--out", help="證據輸出路徑（JSON）")
    ap.add_argument("--dry-run", dest="dry_run", help="以 fixture 驅動判定邏輯，不觸網")
    a = ap.parse_args(argv)

    if a.dry_run:
        with open(a.dry_run, encoding="utf-8") as fh:
            obs = json.load(fh)
        r = evaluate(obs)
        _print(r, obs)
        print("  [DRY RUN] 未發出任何網路請求。")
        return 0

    if not a.date:
        ap.error("正式執行必須提供 --date YYYYMMDD")
    obs = collect(a.date)
    r = evaluate(obs)
    _print(r, obs)

    ev = {
        "purpose": "UG-G2-SB9 階段一端點驗證原始證據（提案 §5.3）",
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "in_container": os.path.exists("/.dockerenv"),
            "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "timestamp_local": _dt.datetime.now().astimezone().isoformat(),
            "local_timezone": _dt.datetime.now().astimezone().tzname(),
        },
        "parameters": {
            "endpoint_template": ENDPOINT, "timeout_seconds": TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES, "delay_range": list(DELAY_RANGE),
            "max_logical_requests": MAX_LOGICAL_REQUESTS,
            "max_http_attempts": MAX_HTTP_ATTEMPTS, "min_rows": MIN_ROWS,
        },
        "scope_disclosure": (
            "階段一只驗證上市（證交所）端點。依 DEC-017，候選空間為上市 + 上櫃"
            "（排除興櫃）——**上櫃在本 SB 範圍內，延後至階段二**，不是被排除。"
        ),
        "observations": obs, "result": r,
    }
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(ev, fh, ensure_ascii=False, indent=2, default=str)
            fh.write("\n")
        print("  證據已寫入：%s" % a.out)
    # 退出碼不表達 PASS/FAIL —— FAIL 是合法結果，不是腳本執行失敗。
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("[ABORT] %s" % exc, file=sys.stderr)
        raise SystemExit(3)
