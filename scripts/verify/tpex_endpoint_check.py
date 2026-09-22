# -*- coding: utf-8 -*-
"""UG-G2-SB9 附加步驟：TPEx（櫃買中心）端點驗證（C1-C6 判準 + C7-C10 量測）。

**判準於觸網前寫死，跑完只做比對。** 不因結果調整判準、不重試至成功。

**為什麼不沿用 TWSE 的 B1-B6**（判準文件 §0）：四個結構性盲點——
民國年日期格式、代號空間重疊、成交金額單位、主鍵碰撞。
其中第 3、4 項是**安靜地錯**：沒有錯誤訊息、沒有例外、資料表看起來完好。

用法：
    python scripts/verify/tpex_endpoint_check.py --out <path>
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
    _find_market_table, _match_fields,
)

PASS, FAIL, NOT_EXECUTED, INCONCLUSIVE = "PASS", "FAIL", "NOT EXECUTED", "INCONCLUSIVE"

# 【2026-09-01，PO 核准擴充 5 -> 6】**這不是「用完再多要一點」。**
# 原本的 5 次是照「依序試三個候選、每個測到 C1」估的，
# 而那條停止規則後來被判定為缺陷、改成「通過 C1~C6 才算成立」。
# **預算是照一條後來被修正的規則估的——基準改了，不是額度不夠用。**
# 6 為上限：候選 3 若需要測，是另一個決定，不是自動延續。
# 【2026-09-01 第二次擴充 6 -> 7，審查者核准】**這是最後一次。**
# 不論成功或失敗、不論歸因於端點或儀器，**都不再要第八個**。
# 且這一次只需要回答 C3a 與 C3b —— C1/C2/C6 已完成，
# C4/C5 可由已保存的欄名與樣本離線確立（`--replay`）。
REQUEST_BUDGET = 7
# HTTP 嘗試上限（含傳輸層重試）。**與邏輯請求分開計數**——
# 一個在 TLS 就失敗的請求沒有到達應用層，幾乎沒有造成負載，
# 卻會消耗掉一個「要問的問題」的額度。**預算要量它該量的東西。**
HTTP_ATTEMPT_BUDGET = 9
# 傳輸層錯誤（交握／連線／逾時）在同一個邏輯請求內重試的次數。
# **只在傳輸層錯誤、429 與 5xx 時重試**——4xx（除 429）代表端點明確回答了，
# 重試不會讓答案改變（沿用 UG-G2-SB5 腳本既有的重試慣例）。
TRANSPORT_RETRIES = 2
DELAY_RANGE = (3.0, 5.0)
TIMEOUT_SECONDS = 20
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

VERIFY_DATES = ["2026-08-21", "2026-08-20"]

# C3a：**只證明「回應沒被分頁或截斷」，不是對上櫃市場規模的宣稱。**
# 分頁通常數十列；200 遠高於任何合理單頁大小，也遠低於任何市場規模宣稱。
# 原判準寫 700，與量測項 C7「先寫一個數字再拿它當判準就是在猜」自相矛盾（PO 指出）。
MIN_ROWS_NOT_A_PAGE = 200

# C3b：本專案追蹤標的中已知的上櫃股。**缺席只可能是拿錯表**——
# 唯讀查證真實庫 stock_prices 確認 6488 於 2026-08-20（量 8,919,692）與
# 2026-08-21（量 5,732,166）皆有大量成交，故排除「當天沒交易」這個解釋。
# 前提不記錄，下一個人判讀 FAIL 時就得重新推導。
KNOWN_TPEX_STOCK = "6488"

# C5：成交金額 / (收盤價 x 成交股數)。落在 ~0.001 代表單位是千元。
UNIT_RATIO_MIN, UNIT_RATIO_MAX = 0.5, 2.0
UNIT_SAMPLE_MIN = 3

_COMMON = re.compile(r"^[1-9]\d{3}$")

_NULL_MARKERS = frozenset({"--", "-", "", "X", "x", "null", "None"})


class RequestBudget:
    """超出上限即拋例外。**不是提醒，是硬上限。**

    **雙軌計數**（2026-09-01，審查者裁示修正 2）：
    `used`＝**邏輯請求數**（要問的問題數），`http_attempts`＝**實際發出的 HTTP 嘗試數**。

    兩個數字都記，**不要只留一個**：前者是判準的分母（C2 需要兩個日期＝兩個邏輯請求），
    後者才是對政府單位服務造成的實際負載。只留一個就會有一種情況說不清楚。
    """

    def __init__(self, limit, attempt_limit=None, used=0, http_attempts=0):
        self.limit, self.used = limit, used
        self.attempt_limit = attempt_limit or limit
        self.http_attempts = http_attempts

    def spend(self, what):
        """開始一個**邏輯請求**。"""
        if self.used >= self.limit:
            raise RuntimeError("邏輯請求預算 %d 已用盡，拒絕發出：%s" % (self.limit, what))
        self.used += 1

    def attempt(self, what):
        """發出一次實際 HTTP 嘗試（重試也算）。"""
        if self.http_attempts >= self.attempt_limit:
            raise RuntimeError("HTTP 嘗試上限 %d 已用盡，拒絕發出：%s"
                               % (self.attempt_limit, what))
        self.http_attempts += 1


def to_roc(date_str):
    """2026-08-21 -> 115/08/21（民國年）。

    **這是 TWSE 判準結構上抓不到的第一個盲點**：送錯格式時，
    服務可能回空表或別的日期，而「HTTP 200」與「列數夠多」都會通過。
    """
    y, m, d = date_str.split("-")
    return "%d/%s/%s" % (int(y) - 1911, m, d)


def candidate_urls(date_str):
    """依序嘗試。三者皆為櫃買中心公開行情頁／開放資料，非未公開介面。

    **必須記錄哪一個成功、其餘各自為何失敗**（PO 指示 (b)）——
    否則「試到有一個能用」與「驗證了文件化的那一個」在證據上長得一樣。
    """
    return [
        ("openapi_daily_close_quotes",
         "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"),
        ("www_afterTrading_otc",
         "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
         "?date=%s&type=EW&response=json" % date_str.replace("-", "/")),
        ("web_stk_quote_result",
         "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/"
         "stk_quote_result.php?l=zh-tw&d=%s&o=json" % to_roc(date_str)),
    ]


# TPEx 的欄名與 TWSE 不同（openapi 用 `SecuritiesCompanyCode`／`Close`／
# `TradingShares`／`TransactionAmount`；行情頁用中文欄名）。
# **共用選表邏輯時必須連同欄位樣式一起傳入**——原封不動套用 TWSE 的樣式
# 會得到「找不到表」，而那又是一個歸因錯的 FAIL（審查者的提醒）。
# 【UG-G2-SB7】`TPEX_FIELD_PATTERNS` 已搬移至 `src/extractors/market_report_table.py`——
# 生產路徑需要同一份。**本檔的公開名稱與行為不變。**
from src.extractors.market_report_table import TPEX_FIELD_PATTERNS  # noqa: E402,F401


def extract_table(payload):
    """從回應中找出「欄位名 + 資料列」的表，並記錄找到的位置與形態。

    **2026-09-01 改為共用 `twse_market_endpoint_check._find_market_table()`**
    （審查者查出）：那個函式三天前就已處理 `tables` 這種 list-of-tables，
    還多了舊版 `fieldsN`/`dataN` 與選表邏輯，
    **而本腳本重新實作了一個較差的版本，結果把候選 2 判成不可用。**

    > 能力在同一個目錄、同一個人寫的檔案裡就有，卻被重新實作了一次。

    保留本函式僅為兩件事：**處理 openapi 的 list-of-dict 頂層形態**
    （`_find_market_table` 只吃 dict），以及**傳入 TPEx 的欄位樣式**。
    """
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        fields = list(payload[0].keys())
        rows = [[r.get(f) for f in fields] for r in payload]
        return fields, rows, {"top_level_type": "list", "top_level_keys": None,
                              "shape": "list_of_dict", "table_titles": []}
    fields, rows, diag = _find_market_table(payload, TPEX_FIELD_PATTERNS)
    diag["top_level_type"] = type(payload).__name__
    # C6 的「同日」前提需要資料日期。**它不是欄位，是表層 metadata**
    # （`tables[i].date`），所以逐列掃 `Date` 欄永遠找不到——
    # 前一次 `date_values_observed` 為 None 就是這個原因。
    if isinstance(payload, dict):
        m = re.match(r"tables\[(\d+)\]", str(diag.get("shape") or ""))
        if m:
            tbl = (payload.get("tables") or [])[int(m.group(1))]
            diag["table_date"] = tbl.get("date")
            diag["table_total_count"] = tbl.get("totalCount")
        diag["payload_date"] = payload.get("date")
    return fields, rows, diag


def _num(raw):
    """無法解析時回傳 None，**不回傳 0**（同 twse_market_report.parse_number）。"""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if s in _NULL_MARKERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _idx(fields, *names):
    for n in names:
        for i, f in enumerate(fields):
            if str(f).strip() == n:
                return i
    return None


def evaluate(obs):
    """**純函式**：只吃觀測、不發請求。known-FAIL 測試直接餵 fixture 進來。"""
    res = {}

    def put(k, verdict, detail, blocked_by=None):
        res[k] = {"verdict": verdict, "detail": detail, "blocked_by": blocked_by}

    ok_resp = obs.get("ok_response")
    if not ok_resp:
        att = obs.get("attempts", [])
        # 【2026-09-01 修訂】**「連不上」與「端點回了東西但不合契約」是兩件事。**
        #
        # 2026-09-01 的第三次嘗試以 `SSLError(CERTIFICATE_VERIFY_FAILED,
        # Missing Subject Key Identifier)` 失敗 —— **TLS 交握就沒完成，
        # 我們從來沒有觀測到那個端點的回應**。而同一個 URL 稍早成功回過兩次 200。
        # 把它記成 C1 FAIL，等於宣稱「該端點不合契約」，
        # **而我們根本沒看到它的回應** —— 這是本 SB 第四次同型的歸因錯誤。
        #
        # 三態語意在別處都已區分「未執行」與「失敗」，這裡必須一致：
        # 傳輸層失敗 → `NOT EXECUTED` + `blocked_by is None` → 整體 `INCONCLUSIVE`，
        # 而 `INCONCLUSIVE` 依既有規則**不得被讀成「可用」**。
        transport = [a for a in att if a.get("transport_failure")]
        if att and len(transport) == len(att):
            put("C1", NOT_EXECUTED,
                "**未觀測到任何回應**（傳輸層失敗，非端點不合契約）：%s"
                % [(a.get("endpoint_name"), a.get("error")) for a in att],
                blocked_by=None)
        else:
            put("C1", FAIL, "候選端點皆不成立：%s"
                % [(a.get("endpoint_name"), a.get("status_code"), a.get("error"))
                   for a in att])
        for k in ("C2", "C3a", "C3b", "C4", "C5", "C6"):
            put(k, NOT_EXECUTED, "無任何候選端點成功", blocked_by="C1")
        return res

    put("C1", PASS, "端點 %s 回 HTTP 200 且可解析為 JSON" % ok_resp["endpoint_name"])

    second = obs.get("second_date_response")
    if second is None:
        put("C2", NOT_EXECUTED, "未取得第二個日期的回應", blocked_by=None)
    else:
        same = (ok_resp.get("body_digest") == second.get("body_digest"))
        put("C2", FAIL if same else PASS,
            "兩個日期的回應內容%s（digest %s vs %s）"
            % ("**相同——日期參數未被吃進去**" if same else "不同",
               ok_resp.get("body_digest"), second.get("body_digest")))

    fields, rows = ok_resp.get("field_names"), ok_resp.get("rows")
    if not fields or not rows:
        for k in ("C3a", "C3b", "C4", "C5", "C6"):
            put(k, NOT_EXECUTED, "回應中找不到報價表", blocked_by="C1")
        return res

    # 同上：不得再用精確比對。`'代號'` 對不上 `'證券代號'` 是實測到的形態。
    i_code = _match_fields(fields, TPEX_FIELD_PATTERNS)[0].get("code")
    codes = set()
    if i_code is None:
        for k in ("C3a", "C3b"):
            put(k, NOT_EXECUTED, "找不到代號欄，無法判斷", blocked_by="C4")
    else:
        codes = {str(r[i_code]).strip() for r in rows}
        common = {c for c in codes if _COMMON.match(c)}
        put("C3a", PASS if len(common) >= MIN_ROWS_NOT_A_PAGE else FAIL,
            "4 碼非 0 開頭 %d 檔（下界 %d，**僅證明非分頁碎片，不宣稱市場規模**）"
            % (len(common), MIN_ROWS_NOT_A_PAGE))
        put("C3b", PASS if KNOWN_TPEX_STOCK in codes else FAIL,
            "%s %s於回應中（該檔於兩個驗證日皆有大量成交，故缺席只可能是拿錯表）"
            % (KNOWN_TPEX_STOCK, "存在" if KNOWN_TPEX_STOCK in codes else "**不存在**"))

    # 【2026-09-01 第二次修正】原本這裡用自己的 `_idx()`（**精確比對**），
    # 與 `extract_table()` 已改用的 `_match_fields()`（**正規化 + 樣式比對**）不一致
    # —— **同一個檔案裡的第二個欄位對映實作**。
    #
    # 後果：實際欄名 `'代號'`／`'名稱'`／`' 成交金額(元)'` 對不上
    # `'證券代號'`／`'證券名稱'`／`'成交金額'`，C4 判 FAIL、C3a/C3b/C5 連帶未執行，
    # **而端點明明八個欄位都有**。這是本 SB 第五次同型的歸因錯誤，
    # 且是我上一次只修了半邊所留下的。
    #
    # **一個模組裡不該有兩套欄位對映規則。** 統一走 `_match_fields`。
    mapping, missing_keys = _match_fields(fields, TPEX_FIELD_PATTERNS)
    _ZH = {"code": "代號", "close": "收盤", "volume": "成交股數", "open": "開盤",
           "high": "最高", "low": "最低", "amount": "成交金額"}
    missing = [_ZH[k] for k in missing_keys]
    put("C4", PASS if not missing else FAIL,
        ("缺少欄位：%s（實際欄位：%s）" % (missing, fields)) if missing
        else "七個必要語意鍵皆可對映：%s"
             % {_ZH[k]: fields[v] for k, v in mapping.items()})

    ic, iv, ia, icode = (mapping.get("close"), mapping.get("volume"),
                         mapping.get("amount"), mapping.get("code"))
    if None in (ic, iv, ia):
        put("C5", NOT_EXECUTED, "欄位對映不全，無法計算比值", blocked_by="C4")
    else:
        ratios = []
        for r in rows:
            c, v, a = _num(r[ic]), _num(r[iv]), _num(r[ia])
            # **抽樣自「收盤價非 NULL 且成交股數 > 0」的列**（PO 指示 (c)）：
            # 無價格列會讓比值無法計算，抽到就得到無意義結果而非 FAIL。
            if c is not None and v is not None and a is not None and c > 0 and v > 0:
                label = str(r[icode]).strip() if icode is not None else "?"
                ratios.append((label, a / (c * v)))
            if len(ratios) >= 10:
                break
        if len(ratios) < UNIT_SAMPLE_MIN:
            put("C5", NOT_EXECUTED,
                "可用樣本僅 %d 檔（需 %d）" % (len(ratios), UNIT_SAMPLE_MIN),
                blocked_by=None)
        else:
            bad = [x for x in ratios if not (UNIT_RATIO_MIN <= x[1] <= UNIT_RATIO_MAX)]
            put("C5", PASS if not bad else FAIL,
                "抽樣 %d 檔，比值 %s；超出 [%.1f, %.1f] 者 %d 檔%s"
                % (len(ratios), [(c, round(x, 5)) for c, x in ratios[:5]],
                   UNIT_RATIO_MIN, UNIT_RATIO_MAX, len(bad),
                   "（~0.001 量級代表單位是千元）" if bad else ""))

    twse = obs.get("twse_codes_same_day")
    if twse is None:
        put("C6", NOT_EXECUTED, "未提供同日 TWSE 代號集合", blocked_by=None)
    else:
        inter = sorted({c for c in codes if _COMMON.match(c)} & set(twse))
        # 【2026-09-01 修訂】C6 的通過條件寫的是「**同日**代號集合互斥」——
        # **日期是通過條件的一部分**，而第一次執行時 TPEx 快照的日期不明，
        # C6 卻仍然 PASS 了。**一個檢查通過了，但它通過的條件與它宣稱的條件不同**
        # —— 與本 SB 一路在處理的是同一個形狀。
        # 因此判定必須帶上前提是否成立，不得只印 PASS。
        put("C6", PASS if not inter else FAIL,
            "交集 %d 檔%s。%s"
            % (len(inter), ("：%s" % inter[:20]) if inter else "（互斥）",
               _c6_premise(obs)))
    return res


def _c6_premise(obs):
    """C6 的「同日」前提是否成立 —— **必須與判定一起印出來**。"""
    twse_d = obs.get("twse_codes_date") or "未指明"
    snap = obs.get("tpex_snapshot_dates")
    if not snap:
        return ("**前提未驗證**：TPEx 資料日期不明（本次未保存 `Date` 欄），"
                "比對對象為 TWSE %s。結論建立在「市場成員不逐日變動」這個假設上"
                % twse_d)
    snap = sorted(set(snap))
    if len(snap) == 1 and _same_day(snap[0], twse_d):
        return "**前提已驗證**：TPEx 資料日期 %s，與比對對象 TWSE %s 同日" % (snap[0], twse_d)
    return ("**前提不成立**：TPEx 資料日期 %s，比對對象為 TWSE %s，**非同日**。"
            "結論建立在「市場成員不逐日變動」這個假設上" % (snap if len(snap) > 1 else snap[0],
                                                          twse_d))


def _same_day(tpex_date, iso_date):
    """TPEx 的日期可能是民國年（1150821 / 115/08/21），比對前先正規化。"""
    a = re.sub(r"\D", "", str(tpex_date))
    b = re.sub(r"\D", "", str(iso_date))
    if len(b) != 8:
        return False
    roc = "%d%s" % (int(b[:4]) - 1911, b[4:])       # 20260821 -> 1150821
    return a in (b, roc)


CRITERIA_KEYS = ("C1", "C2", "C3a", "C3b", "C4", "C5", "C6")


def overall(res):
    if any(res[k]["verdict"] == FAIL for k in CRITERIA_KEYS):
        return FAIL
    # 儀器本身沒跑起來（非被上游判準擋住）→ INCONCLUSIVE，**不得讀成「可用」**
    if any(res[k]["verdict"] == NOT_EXECUTED and res[k].get("blocked_by") is None
           for k in CRITERIA_KEYS):
        return INCONCLUSIVE
    return PASS if all(res[k]["verdict"] == PASS for k in CRITERIA_KEYS) else INCONCLUSIVE


def _headline(dispositions):
    """**整體結果不得被寫成「TPEx PASS」。**

    日後有人讀到「TPEx 可用」，會去找那個 openapi 端點 ——
    **它是官方開放資料、看起來最正規，而且 C1/C3/C4/C5/C6 全過。
    只有 C2 擋得住它。** 那個 FAIL 是要留給下一個人的警告，
    不是一次失敗的嘗試紀錄，因此必須出現在最顯眼的欄位。
    """
    if not dispositions:
        return "未取得任何候選端點的完整判定。"
    parts = []
    for d in dispositions:
        if d["overall"] == PASS:
            parts.append("候選 `%s` **PASS**" % d["endpoint_name"])
        else:
            fails = [k for k, v in (d.get("criteria") or {}).items() if v == FAIL]
            parts.append("候選 `%s` **%s**%s"
                         % (d["endpoint_name"], d["overall"],
                            "（%s）" % "、".join(fails) if fails else ""))
    usable = [d["endpoint_name"] for d in dispositions if d["overall"] == PASS]
    tail = ("可用端點：`%s`。" % usable[0]) if usable else "**目前無可用端點。**"
    return tail + " 逐一結果：" + "；".join(parts) + "。"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--twse-codes", default=None,
                    help="同日 TWSE 4 碼代號清單檔（每行一個），供 C6 使用")
    ap.add_argument("--twse-codes-date", default=None,
                    help="上述代號集合的日期（ISO），C6 的『同日』前提要靠它判定")
    ap.add_argument("--only", default=None,
                    help="只測指定候選端點（其餘候選的既有結果由 --prior 帶入）")
    ap.add_argument("--single-date", action="store_true",
                    help="只取第一個日期；C2 沿用 --prior 中已觀測到的第二個日期 digest。"
                         "**已經問過的問題不必再花一個請求問一次。**")
    ap.add_argument("--replay", default=None,
                    help="從先前報告的 raw_capture 離線重評，**不發任何請求**。"
                         "儀器缺陷在事後才發現時，不必再為它花一次請求。")
    ap.add_argument("--prior", default=None,
                    help="先前的報告檔；用於承接已測候選的結果與已用請求數，"
                         "**避免為了重測已知結果而重複消耗預算**")
    a = ap.parse_args(argv)

    import hashlib
    import requests

    budget = RequestBudget(REQUEST_BUDGET, HTTP_ATTEMPT_BUDGET)
    obs = {"attempts": [], "ok_response": None, "second_date_response": None}
    only = a.only
    prior_dispositions, prior_report = [], None
    if a.prior and os.path.exists(a.prior):
        with open(a.prior, encoding="utf-8") as fh:
            prior_report = json.load(fh)
        # **預算跨執行累計**：先前已用的請求數要先扣掉，
        # 否則「上限 5 次」在每次執行時重置，等於沒有上限（此為前次已揭露的缺陷）。
        _p = prior_report.get("protocol", {})
        budget.used = _p.get("logical_requests_cumulative",
                             _p.get("requests_used_cumulative",
                                    _p.get("requests_used", 0)))
        budget.http_attempts = _p.get("http_attempts_cumulative", budget.used)
        prior_dispositions = prior_report.get("endpoint_disposition", [])
        if not prior_dispositions and prior_report.get("criteria"):
            att = prior_report.get("attempts") or [{}]
            prior_dispositions = [{
                "endpoint_name": att[0].get("endpoint_name"),
                "url": att[0].get("url"),
                "overall": prior_report.get("overall"),
                "criteria": {k: v["verdict"]
                             for k, v in prior_report["criteria"].items()},
                "note": prior_report["criteria"].get("C2", {}).get("detail")}]
        obs["attempts"].extend(prior_report.get("attempts", []))
    if a.twse_codes and os.path.exists(a.twse_codes):
        with open(a.twse_codes, encoding="utf-8") as fh:
            obs["twse_codes_same_day"] = [ln.strip() for ln in fh if ln.strip()]
        obs["twse_codes_date"] = a.twse_codes_date

    def fetch(name, url, label):
        """一個**邏輯請求**；傳輸層失敗時在其內重試，不另計邏輯配額。"""
        budget.spend(label)
        rec = None
        for i in range(1 + TRANSPORT_RETRIES):
            rec = _attempt_once(name, url, label, i)
            if not rec.get("transport_failure"):
                break
            if i < TRANSPORT_RETRIES:
                print("    傳輸層失敗（%s），同一邏輯請求內重試 %d/%d"
                      % (rec.get("error", "")[:60], i + 1, TRANSPORT_RETRIES))
                time.sleep(random.uniform(*DELAY_RANGE))
        return rec

    def _attempt_once(name, url, label, i):
        budget.attempt("%s #%d" % (label, i + 1))
        rec = {"endpoint_name": name, "url": url, "label": label,
               "attempt_index": i, "ok": False}
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                           "Accept": "application/json"},
                             timeout=TIMEOUT_SECONDS)
            rec["status_code"] = r.status_code
            rec["content_type"] = r.headers.get("Content-Type")
            if r.status_code in (403, 429) or r.status_code >= 500:
                rec["error"] = "HTTP %d —— 依判準立即停止，不重試" % r.status_code
                rec["fatal"] = True
                return rec
            r.raise_for_status()
            body = r.text
            rec["body_digest"] = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
            rec["body_bytes"] = len(body)
            # 【2026-09-01 取證修正 2】**保存原始 body 的動作必須在成功路徑之前。**
            #
            # 前一次：候選 2 回了 139,583 bytes，解析不了，然後那份回應沒有被保存
            # ——因為保存 sample_rows / date_values 的程式碼在解析成功之後。
            # **失敗時的回應資訊量最大，卻最不可能被保存**，
            # 而如果它被保存了，解析器的修正可以完全離線驗證，一次請求都不用花。
            #
            # 這是第三次同成因的取證缺口（快照日期不明 → 候選 2 的 body → 本次）。
            rec["body_head_verbatim"] = body[:4000]
            rec["body_tail_verbatim"] = body[-1000:] if len(body) > 5000 else None
            payload = r.json()
            f, rows, diag = extract_table(payload)
            rec["diag"] = diag
            rec["field_names"] = f
            rec["row_count"] = len(rows) if rows else 0
            rec["rows"] = rows
            rec["ok"] = bool(f and rows)
            # 【2026-09-01 取證修正】第一次執行只存了代號集合，**沒存任何一列樣本**，
            # 因此事後說不出那份快照的 `Date` 是哪一天，而那正是 C6 的前提。
            # **指名保存 `Date`**：只說「保存前幾列」不夠 ——
            # 樣本可能剛好不含該欄，或含了但沒人注意。
            if rec["ok"]:
                i_date = _idx(f, "Date", "日期", "資料日期", "trade_date")
                rec["date_field_index"] = i_date
                rec["date_values_observed"] = (
                    sorted({str(r[i_date]).strip() for r in rows})[:5]
                    if i_date is not None else None)
                rec["sample_rows_verbatim"] = [
                    dict(zip(f, r)) for r in rows[:3]]
                # 表層日期（C6 前提）——不是欄位，逐列掃永遠找不到
                rec["table_date"] = diag.get("table_date") or diag.get("payload_date")
                if rec["date_values_observed"] is None and rec["table_date"]:
                    rec["date_values_observed"] = [rec["table_date"]]
            if not rec["ok"]:
                rec["error"] = "回應可解析為 JSON，但找不到「欄位名 + 資料列」的表"
        except Exception as exc:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
            # **傳輸層失敗（交握／連線／逾時）代表「沒觀測到回應」，不是「端點不合契約」。**
            # 判斷依據是「有沒有拿到 status_code」，不是例外類別名稱——
            # 後者需要窮舉，而窮舉不完的那一項會被靜默歸錯類。
            rec["transport_failure"] = ("status_code" not in rec)
        return rec

    if a.replay:
        # **零請求**：用先前保存的原始列重跑判準。
        # 本 SB 已有五次「儀器缺陷被誤記成端點缺陷」，每一次都花掉請求才發現。
        # 保存原始列 + 可離線重評，是讓那個成本一次付清。
        with open(a.replay, encoding="utf-8") as fh:
            prev = json.load(fh)
        cap = prev.get("raw_capture") or {}
        if not cap.get("ok_response"):
            print("[ABORT] 該報告沒有 raw_capture，無法離線重評。")
            return 3
        robs = {"attempts": prev.get("attempts", []),
                "ok_response": cap["ok_response"],
                "second_date_response": cap.get("second_date_response"),
                "tpex_snapshot_dates": cap.get("tpex_snapshot_dates"),
                "twse_codes_same_day": obs.get("twse_codes_same_day"),
                "twse_codes_date": obs.get("twse_codes_date")}
        rres = evaluate(robs)
        rverdict = overall(rres)
        print("=" * 78)
        print("離線重評（--replay，零請求）")
        for k in CRITERIA_KEYS:
            print("  %-4s %-12s %s" % (k, rres[k]["verdict"], rres[k]["detail"]))
        print("  整體：%s" % rverdict)
        prev["criteria"] = rres
        prev["overall_this_candidate"] = rverdict
        prev["REPLAY_NOTE"] = ("本次為 `--replay` 離線重評，**未發出任何請求**；"
                               "計數欄維持先前值。")
        for d in prev.get("endpoint_disposition", []):
            if d.get("endpoint_name") == cap.get("endpoint_name"):
                d["overall"] = rverdict
                d["criteria"] = {k: rres[k]["verdict"] for k in CRITERIA_KEYS}
        prev["HEADLINE"] = _headline(prev.get("endpoint_disposition", []))
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(prev, fh, ensure_ascii=False, indent=2, default=str)
            fh.write(chr(10))
        print("報告已寫入：%s（零請求）" % a.out)
        return 0 if rverdict == PASS else 1

    print("=" * 78)
    print("TPEx 端點驗證｜邏輯請求 %d/%d｜HTTP 嘗試 %d/%d｜節流 %.1f-%.1f 秒"
          % (budget.used, REQUEST_BUDGET, budget.http_attempts,
             HTTP_ATTEMPT_BUDGET, *DELAY_RANGE))

    # 【2026-09-01 修訂】停止條件由「C1 層級成功」改為「**通過 C1~C6 才算成立**」。
    # 原實作把「成功一個即停止嘗試其餘」實作成「回得出一張表就停」，
    # 結果候選 1（當前快照、無日期參數，**結構上不可能通過 C2**）讓搜尋停下來，
    # 而候選 2、3 恰恰是帶日期參數的那兩個。
    # **這是實作缺陷，不是判準問題**：C2 的通過條件一個字都沒變，
    # 改的是「什麼算找完了」，不是「什麼算 PASS」。
    dispositions = list(prior_dispositions)
    res, verdict = None, None
    for name, url in candidate_urls(VERIFY_DATES[0]):
        if only and name != only:
            continue
        cand = {"attempts": [], "ok_response": None, "second_date_response": None,
                "twse_codes_same_day": obs.get("twse_codes_same_day"),
                "twse_codes_date": obs.get("twse_codes_date")}
        rec = fetch(name, url, "候選端點 %s @ %s" % (name, VERIFY_DATES[0]))
        cand["attempts"].append({k: v for k, v in rec.items() if k != "rows"})
        print("  [%s] status=%s ok=%s %s"
              % (name, rec.get("status_code"), rec.get("ok"), rec.get("error", "")))
        if rec.get("fatal"):
            print("[STOP] 限流／封鎖，立即停止，不重試、不調整節流後重跑。")
            obs["attempts"].extend(cand["attempts"])
            break
        if rec.get("ok"):
            cand["ok_response"] = rec
            cand["tpex_snapshot_dates"] = rec.get("date_values_observed")
            if a.single_date:
                # C2 已由先前觀測確立；**已經問過的問題不必再花一個請求問一次。**
                prev2 = next((x for x in reversed(obs["attempts"])
                              if x.get("endpoint_name") == name
                              and VERIFY_DATES[1] in str(x.get("label", ""))
                              and x.get("body_digest")), None)
                cand["second_date_response"] = prev2
                print("  [%s @ %s] 沿用先前觀測（digest %s），**未發出請求**"
                      % (name, VERIFY_DATES[1],
                         (prev2 or {}).get("body_digest", "無")))
                obs["attempts"].extend(cand["attempts"])
                res = evaluate(cand); verdict = overall(res)
                obs.update({k: v for k, v in cand.items() if k != "attempts"})
                dispositions.append({
                    "endpoint_name": name, "url": url, "overall": verdict,
                    "criteria": {k: res[k]["verdict"] for k in CRITERIA_KEYS},
                    "note": None})
                print("  -> 候選 %s 整體：%s" % (name, verdict))
                break
            time.sleep(random.uniform(*DELAY_RANGE))
            url2 = dict(candidate_urls(VERIFY_DATES[1]))[name]
            rec2 = fetch(name, url2, "同端點第二個日期 %s" % VERIFY_DATES[1])
            cand["second_date_response"] = rec2
            cand["attempts"].append({k: v for k, v in rec2.items() if k != "rows"})
            print("  [%s @ %s] status=%s ok=%s"
                  % (name, VERIFY_DATES[1], rec2.get("status_code"), rec2.get("ok")))
        obs["attempts"].extend(cand["attempts"])
        res = evaluate(cand)
        verdict = overall(res)
        obs.update({k: v for k, v in cand.items() if k != "attempts"})
        dispositions.append({"endpoint_name": name, "url": url, "overall": verdict,
                             "criteria": {k: res[k]["verdict"] for k in CRITERIA_KEYS},
                             "note": res["C2"]["detail"] if res["C2"]["verdict"] == FAIL
                                     else None})
        print("  -> 候選 %s 整體：%s" % (name, verdict))
        if verdict == PASS:
            break
        if budget.used + 2 > budget.limit:
            print("[STOP] 預算不足以完整測試下一個候選（C2 需要兩個日期）。"
                  "**不自行續下去** —— 擴充預算需 PO 另行放行。")
            break
        time.sleep(random.uniform(*DELAY_RANGE))

    # 【條件 (a)，審查者指定】**`raw_capture` 必須在評估之前寫出，並斷言非空。**
    #
    # 本 SB 已教過兩次：保存證據的程式碼若在成功路徑上，失敗時就不會執行；
    # 而 `docker cp` 那次證明**一個靜默失敗的保存動作，會讓報告看起來完整
    # 而實際上什麼都沒存**。若 `raw_capture` 又靜默失敗，我們會回到原點，
    # 而這是最後一個請求。**所以它寫不出來就中止，不產出報告。**
    raw_capture = None
    if obs.get("ok_response"):
        raw_capture = {
            "endpoint_name": obs["ok_response"]["endpoint_name"],
            "ok_response": dict(obs["ok_response"]),
            "second_date_response": (dict(obs["second_date_response"])
                                     if obs.get("second_date_response") else None),
            "tpex_snapshot_dates": obs.get("tpex_snapshot_dates"),
        }
        n_rows = len(raw_capture["ok_response"].get("rows") or [])
        if n_rows == 0:
            print("[ABORT] raw_capture 為空——拒絕寫出一份看起來完整的報告。")
            return 4
        _cap = os.path.splitext(os.path.abspath(a.out))[0] + "_raw_capture.json"
        os.makedirs(os.path.dirname(_cap), exist_ok=True)
        with open(_cap, "w", encoding="utf-8") as fh:
            json.dump(raw_capture, fh, ensure_ascii=False, default=str)
            fh.write(chr(10))
        _sz = os.path.getsize(_cap)
        if _sz < 1000:
            print("[ABORT] raw_capture 檔僅 %d bytes——保存顯然失敗。" % _sz)
            return 4
        print("  raw_capture 已寫出：%s（%d 列，%d bytes）" % (_cap, n_rows, _sz))

    if res is None:
        res = evaluate({"attempts": obs["attempts"]})
        verdict = overall(res)
    print("-" * 78)
    for k in CRITERIA_KEYS:
        print("  %-4s %-12s %s" % (k, res[k]["verdict"], res[k]["detail"]))
    print("  本次候選整體：%s" % verdict)
    for d in dispositions:
        print("  · %-30s %s" % (d["endpoint_name"], d["overall"]))

    report = {
        "purpose": "UG-G2-SB9 附加步驟：TPEx（櫃買中心）端點驗證",
        "environment": {"timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        "protocol": {"logical_request_budget": REQUEST_BUDGET,
                     "http_attempt_budget": HTTP_ATTEMPT_BUDGET,
                     "logical_requests_cumulative": budget.used,
                     "http_attempts_cumulative": budget.http_attempts,
                     "counting_note": "**兩個數字都記。** 邏輯請求＝要問的問題數"
                                      "（C2 需要兩個日期＝兩個邏輯請求）；"
                                      "HTTP 嘗試＝對政府單位服務造成的實際負載。"
                                      "傳輸層失敗在同一邏輯請求內重試，不另計邏輯配額"
                                      "——它沒有到達應用層。",
                     "delay_range_seconds": list(DELAY_RANGE),
                     "verify_dates": VERIFY_DATES,
                     "note": "判準於觸網前寫死；遇 403/429/5xx 立即停止，"
                             "不重試至成功、不調整節流後重跑。"
                             "**預算跨執行累計**（`--prior` 承接已用數），"
                             "否則上限在每次執行時重置等於沒有上限。"},
        "criteria": res, "overall_this_candidate": verdict,
        "endpoint_disposition": dispositions,
        "HEADLINE": _headline(dispositions),
        "attempts": obs["attempts"],
        "measurements": {},
        # **保存完整原始列**：TPEx 請求受預算限制、且本 SB 已五次因儀器缺陷
        # 誤判端點。有了它，判準修正可以完全離線重評（`--replay`）。
        # 依「重取成本」判準——重取需要 PO 另行放行請求，不是跑一次腳本的事。
        "raw_capture": raw_capture,
    }
    if obs["ok_response"] and obs["ok_response"].get("rows"):
        f, rows = obs["ok_response"]["field_names"], obs["ok_response"]["rows"]
        ic = _match_fields(f, TPEX_FIELD_PATTERNS)[0].get("code")
        if ic is not None:
            codes = [str(r[ic]).strip() for r in rows]
            common = sorted({c for c in codes if _COMMON.match(c)})
            report["measurements"]["C7_上櫃普通股家數"] = len(common)
            report["measurements"]["C7_註"] = (
                "**量測值，不是判準**——先寫一個數字再拿它當判準就是在猜。")
            report["measurements"]["C7_代號形態分佈"] = {
                "4碼非0開頭": len(common),
                "4碼0開頭": len({c for c in codes if re.fullmatch(r"0\d{3}", c)}),
                "5碼": len({c for c in codes if len(c) == 5}),
                "6碼": len({c for c in codes if len(c) == 6}),
            }
            report["measurements"]["C10_TPEx普通股代號集合"] = common
            report["measurements"]["C10_註"] = (
                "跨時間代號重疊（上櫃轉上市）需與 candidate_prices 的三年 TWSE 代號"
                "集合比對，該資料在 repo 外備份中。此處保存 TPEx 端的代號集合供比對，"
                "**完整比對與處置屬 UG-G2-SB6**。")
        i_pe = next((i for i, x in enumerate(f)
                     if re.search(r"本益比|PERatio", str(x))), None)
        if i_pe is not None:
            pes = [_num(r[i_pe]) for r in rows]
            report["measurements"]["C9_本益比為0的列數"] = sum(1 for v in pes if v == 0.0)
            report["measurements"]["C9_註"] = (
                "TPEx 未必沿用 TWSE 的 `0.00` sentinel 慣例，**不得假設**。")
        _m = _match_fields(f, TPEX_FIELD_PATTERNS)[0]
        ic_close, iv_ = _m.get("close"), _m.get("volume")
        if ic_close is not None and iv_ is not None:
            report["measurements"]["C8_無價格列數"] = sum(
                1 for r in rows if _num(r[ic_close]) is None)
            report["measurements"]["C8_零成交列數"] = sum(
                1 for r in rows if _num(r[iv_]) == 0.0)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    print("HEADLINE: %s" % report["HEADLINE"])
    print("報告已寫入：%s（邏輯請求 %d/%d｜HTTP 嘗試 %d/%d）"
          % (a.out, budget.used, REQUEST_BUDGET,
             budget.http_attempts, HTTP_ATTEMPT_BUDGET))
    return 0 if verdict == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
