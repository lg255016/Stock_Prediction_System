# -*- coding: utf-8 -*-
"""UG-G2-SB5：Dcard 端點可用性驗證（A1-A5 判準 + A6 量測）。

**這支腳本的判準在寫下之前就已定死**（Gate A 提案 §3，PO 2026-08-28 核准），
且它是 `MULTI_SOURCE_DATA_CONTRACT.md` §4.5 既有 Feasibility Gate 的**可執行化超集**
（對照表見提案 §1.10）。**不得因為結果不理想而調整判準後重跑**——
若判準本身有缺陷，必須帶著原始執行結果回到 PO 重新核准。

三個設計約束，每一個都是為了讓「結果」無法反過來污染「判準」：

1. **判定邏輯與網路存取完全分離**。`evaluate()` 是純函數，吃一份觀察紀錄、吐三態結果。
   因此判準可以在**一次網路請求都沒發生**的情況下被測試——
   包含那些「必須會 FAIL」的案例（`CLAUDE.md` §9A.2）。
2. **`--dry-run` 吃 fixture 檔**，走與正式執行完全相同的 `evaluate()`。
   known-FAIL 案例靠它產生，不靠對真實端點製造失敗。
3. **請求預算硬上限**。邏輯請求 3 次（提案 §3.1），
   加上重試後的實際 HTTP 嘗試次數另有天花板，且**兩者都會被記錄**。

**A6 是量測項，不是判準項**——它不參與整體判定，也沒有 PASS 門檻
（PO：單一時點 30 篇撐不起數字門檻，設一個只會是假精確）。

用法：
    # 正式執行（會發出網路請求；需 PO 核准且腳本已複查）
    python scripts/verify/dcard_availability_check.py \
        --keywords doc/upgrade/gates/evidence/G2_SB5_keywords_snapshot.json \
        --out doc/upgrade/gates/evidence/G2_SB5_availability_evidence.json

    # 不觸網，以 fixture 驗證判準邏輯本身
    python scripts/verify/dcard_availability_check.py --dry-run fixture.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import random
import sys
import time

# ---------------------------------------------------------------------------
# 固定執行參數（提案 §3.1；不得於執行時調整）
# ---------------------------------------------------------------------------
BASE = "https://www.dcard.tw/service/api/v2"
# §3.2.2：對齊契約 §4.2 的正式端點參數（`popular=true&limit=30`），
# 而非 §4.5 的最小探測（`limit=1`）。理由：A6 若量的是「最新 30 篇」，
# 而決策點 6 方案 (a) 實際會抓「熱門 30 篇」，覆蓋率數字描述的就是另一個母體——
# 量錯母體的數字，其誤導性大於沒有數字。
LIST_URL = BASE + "/forums/stock/posts?popular=true&limit=30"
POST_URL = BASE + "/posts/{post_id}"
COMMENTS_URL = BASE + "/posts/{post_id}/comments?limit=1"

TIMEOUT_SECONDS = 15
MAX_RETRIES = 3                 # 每個邏輯請求的重試上限
BACKOFF_SECONDS = (2, 4, 8)     # 指數退避
DELAY_RANGE = (1.5, 3.0)        # 契約 §4.4 的請求間隔
MAX_LOGICAL_REQUESTS = 3        # 提案 §3.1 的總請求上限（端點數）
MAX_HTTP_ATTEMPTS = MAX_LOGICAL_REQUESTS * MAX_RETRIES  # 含重試的實際 GET 天花板

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REQUIRED_FIELDS = ("id", "title", "createdAt", "likeCount", "commentCount")

# 落檔時必須遮蔽**值**的標頭（第四輪複查指出）。
#
# `sent_headers` 原本連值一起存，而證據檔會進 `evidence/` 並 commit。
# 本次執行的環境沒有憑據，所以沒有事故——但 A2 的 known-FAIL 測試模擬的正是
# 「netrc 存在時 requests 自己補上 `Authorization`」，屆時那個**值**會原封不動
# 寫進證據檔，commit 後即違反 `CLAUDE.md` §11（不得 commit token／credential）。
#
# **判定只需要標頭名稱**（A2 判的是 `k.lower() in (...)`），值沒有任何判定用途。
# 因此在**記錄當下**就遮蔽，而不是等到寫檔——讓憑據的值連進入觀察字典的機會都沒有。
# **只套用在請求標頭上。** 回應標頭刻意不遮蔽——
# 本次的 `set-cookie: __cf_bm=…` 正是 Cloudflare 攔截的關鍵證據之一，
# 遮掉它等於毀掉證據。回應標頭是**端點產生的**，不是我們的憑據。
SENSITIVE_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie",
    "x-api-key", "api-key", "x-auth-token", "authentication",
})
REDACTED = "<redacted>"


def redact_headers(headers) -> dict:
    """保留標頭名稱與順序，把認證類標頭的值換成 `<redacted>`。

    名稱必須保留——A2 靠它判定，遮掉名稱等於讓 A2 又瞎一次。
    """
    if headers is None:
        return None
    return {
        k: (REDACTED if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in dict(headers).items()
    }

PASS, FAIL, NOT_EXECUTED, MEASURED = "PASS", "FAIL", "NOT EXECUTED", "MEASURED"

# 第三個**整體**狀態（第四輪複查指定）。
#
# 觸發條件是機械的：任一判準 `verdict == NOT EXECUTED` 且 `blocked_by is None`
# ——也就是**沒有上游判準擋住它，它卻仍然沒能執行**。那只有一種可能：
# 儀器（本腳本）自己沒產出證據。
#
# 為什麼需要它：§4.1 的整條處置路徑以「整體 FAIL」為觸發條件——
# RISK-003 由 `NOT VERIFIED` 改記 `OBSERVED`（語意是「已實測」）、
# 契約 §4 加註「暫停適用——實測 A_n 失敗」、新增 DEC、Master Plan 與
# PROJECT_STATUS 回填。**這些都是永久治理紀錄。**
# 若我們自己漏記一個 header 就把 `FAIL` 寫進去，
# 記下的會是「Dcard 經實測不可用」——而事實可能是端點五題全答對。
#
# 這是 §3.2.1 已建立、但原本只停在「單項」層級的區分，現在抬到「整體」層級：
#   端點答錯                    → FAIL（端點的問題）
#   上游判準擋住、沒機會跑        → 整體 FAIL（仍是端點的問題）
#   儀器沒產出證據、端點本身沒答錯 → INCONCLUSIVE（我們的問題）
#
# **INCONCLUSIVE 不是 PASS 與 FAIL 之間的中間值**，因此不違反 §3 的
# 「不設中間狀態」——§3 禁的是「部分通過／有條件通過」那種把壞結果洗成好結果的
# 中間值；INCONCLUSIVE 說的是「這次執行根本沒產出可用的觀察」，比 FAIL 更嚴格。
# **它同樣不得被讀成「可用」。**
INCONCLUSIVE = "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# 純判定邏輯——不碰網路，可被 fixture 完整驅動
# ---------------------------------------------------------------------------
def _can_str(value):
    try:
        str(value)
        return True, None
    except Exception as exc:  # pragma: no cover - str() 幾乎不會失敗
        return False, "無法轉為 str: %s" % exc


def _parseable_datetime(value):
    if not isinstance(value, str):
        return False, "非 str，無法當 ISO 8601 時間解析"
    try:
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True, None
    except ValueError:
        return False, "無法以 ISO 8601 解析"


def _check_fields(payload: dict) -> dict:
    """A4：逐欄檢查存在性與型別，回傳每一欄的檢查結果。

    刻意逐欄回報而非只回一個布林值：提案 §3.3 要求證據必須能區分
    「端點還在但契約過期」與「端點消失」——前者可修（改欄位映射），後者不可修。
    只回 True/False 的話，這兩種 FAIL 在證據上長得一模一樣。
    """
    result = {}
    for field in REQUIRED_FIELDS:
        if field not in payload:
            result[field] = {"present": False, "type_ok": False, "reason": "欄位不存在"}
            continue
        value = payload[field]
        if field == "id":
            ok, reason = _can_str(value)
        elif field == "title":
            ok, reason = isinstance(value, str), "非 str"
        elif field == "createdAt":
            ok, reason = _parseable_datetime(value)
        else:  # likeCount / commentCount
            ok = isinstance(value, int) and not isinstance(value, bool)
            reason = "非 int"
        result[field] = {
            "present": True,
            "type_ok": bool(ok),
            "observed_type": type(value).__name__,
            "reason": None if ok else reason,
        }
    return result


def measure_keyword_coverage(listing: dict, keywords_snapshot: dict) -> dict:
    """A6：30 篇標題中命中 is_active 追蹤關鍵字的篇數與命中詞。

    **零命中是一個合法的量測結果**，不是錯誤——它正是決策點 6 選項 (a)
    「覆蓋率可能極低」需要被量到的那個數字。
    """
    titles = listing.get("titles")
    kw_list = [k["keyword"] for k in keywords_snapshot.get("keywords", [])]
    if not titles:
        # 空清單與 None 一律視為「沒東西可量」。
        # **不記成「量了，覆蓋率 0」**——「量了，沒命中」與「根本沒東西可量」
        # 在證據上長得一樣的話，§3.2.1 分開這兩件事的努力就白費了。
        return {"verdict": NOT_EXECUTED, "detail": "沒有可用的標題清單，無從量測"}
    if not kw_list:
        return {"verdict": MEASURED, "titles_examined": len(titles),
                "keyword_count": 0, "matched_articles": 0, "matched_keywords": [],
                "detail": "關鍵字快照為空——覆蓋率必然為 0，"
                          "且該 0 不代表 Dcard 沒有相關文章"}

    hits, matched_kw = [], set()
    for title in titles:
        found = [kw for kw in kw_list if kw and kw in title]
        if found:
            hits.append({"title": title, "matched": found})
            matched_kw.update(found)
    return {
        "verdict": MEASURED,
        "titles_examined": len(titles),
        "keyword_count": len(kw_list),
        "matched_articles": len(hits),
        "coverage_ratio": round(len(hits) / len(titles), 4) if titles else None,
        "matched_keywords": sorted(matched_kw),
        "hits": hits,
        "keyword_snapshot_taken_at": keywords_snapshot.get("taken_at_utc"),
        "match_rule": "substring（kw in title），區分大小寫，不做斷詞",
        "match_rule_caveat": (
            "子字串比對會讓數字型關鍵字誤命中：'2330' 命中 '12330'、'23300'。"
            "量測當時 tracking_keywords 的 is_active 詞彙全為中文詞，實際風險低；"
            "但 AI 熱門詞探索會動態加詞，日後若出現數字型關鍵字，此數字會偏高。"
        ),
        "note": "量測項，不參與整體判定。母體為契約 §4.2 的正式端點參數"
                "（popular=true&limit=30），與決策點 6 方案 (a) 實際會抓的母體一致。",
    }


def _root_blocker(res: dict, proximate: str) -> str:
    """回溯出**根因**判準，而不是最近的那一個。

    為什麼要多這幾行：A1 連不上時，A3 記 `blocked_by = A1`、A4 記 `blocked_by = A3`。
    每一格單看都對，但讀證據的人會以為 A4 是被「回應格式問題」擋住的——
    實際上根本沒有回應。§3.2.1 的整個用意是讓「沒機會跑」不被誤讀成別的東西，
    只記最近一層等於把誤讀換了個位置。這裡同時保留 `blocked_chain`，
    讓最近一層也不會消失。
    """
    seen, current = [], proximate
    while current and res.get(current, {}).get("verdict") == NOT_EXECUTED:
        seen.append(current)
        nxt = res[current].get("blocked_by")
        if not nxt or nxt in seen:
            break
        current = nxt
    return current


def evaluate(obs: dict) -> dict:
    """由觀察紀錄推出 A1-A5 三態 + A6 量測。純函數。

    `obs` 的形狀刻意與 fixture 檔一致，因此 `--dry-run` 走的是完全相同的路徑。
    """
    res = {}
    listing = obs.get("listing") or {}

    # --- A1 端點連通性 ---
    if listing.get("attempted"):
        res["A1"] = {
            "verdict": PASS if listing.get("status_code") == 200 else FAIL,
            "detail": "HTTP %s" % listing.get("status_code"),
        }
    else:
        res["A1"] = {"verdict": NOT_EXECUTED, "blocked_by": None,
                     "detail": "列表請求未發出"}

    # --- A2 匿名性自我檢查 ---
    #
    # **A2 的性質（第三輪修正）**：它**不是**對端點的探測。
    # 「免登入可存取」在原理上無法獨立於 A1 判定——要真的測，得帶認證與不帶認證
    # 各打一次做對照，而那超出本 SB 的授權（提案 §3.1 的 3 次上限與探測範圍）。
    # A2 實際上是**對我們自己執行紀律的自我檢查**：確認這次 A1 的 200
    # 不是靠環境裡某個認證憑據換來的。
    #
    # 因此它判的必須是**實際送出的標頭**（`sent_headers`），不是我們打算送的字典——
    # 後者是自己寫的常數，判它結構上不可能失敗（`CLAUDE.md` §9A.1）。
    if res["A1"]["verdict"] != PASS:
        res["A2"] = {"verdict": NOT_EXECUTED, "blocked_by": "A1", "detail": "A1 未通過"}
    elif listing.get("sent_headers") is None:
        # 沒有記錄到實際送出的標頭 = 沒有證據。沒有證據不能算通過。
        res["A2"] = {"verdict": NOT_EXECUTED, "blocked_by": None,
                     "detail": "未記錄實際送出的標頭，無從判定匿名性"}
    else:
        sent = listing["sent_headers"]
        auth_like = sorted(
            k for k in sent
            if k.lower() in ("cookie", "authorization", "proxy-authorization")
        )
        res["A2"] = {
            "verdict": PASS if not auth_like else FAIL,
            "detail": ("實際送出的標頭中不含認證資訊"
                       if not auth_like else "實際送出了認證標頭：%s" % auth_like),
            "checked_object": "sent_headers（resp.request.headers）",
            "note": "自我檢查：確認 A1 的 200 不是靠環境憑據換來的；非對端點的探測",
        }

    # --- A3 回應可解析且非空 ---
    first = None
    if res["A1"]["verdict"] != PASS:
        res["A3"] = {"verdict": NOT_EXECUTED, "blocked_by": "A1", "detail": "A1 未通過"}
    elif not listing.get("json_parsed"):
        res["A3"] = {"verdict": FAIL, "detail": "回應無法以 JSON 解析"}
    elif listing.get("top_level_type") != "list":
        res["A3"] = {"verdict": FAIL,
                     "detail": "頂層型別為 %s，契約要求 list" % listing.get("top_level_type")}
    elif not listing.get("item_count"):
        res["A3"] = {"verdict": FAIL, "detail": "list 為空（len = 0）"}
    else:
        res["A3"] = {"verdict": PASS, "detail": "list，len = %d" % listing["item_count"]}
        first = listing.get("first_item")

    # --- A4 欄位契約相符 ---
    if res["A3"]["verdict"] != PASS:
        res["A4"] = {"verdict": NOT_EXECUTED,
                     "blocked_by": _root_blocker(res, "A3"),
                     "blocked_chain": "A3",
                     "detail": "A3 未通過，無元素可檢"}
    else:
        field_report = _check_fields(first or {})
        bad = [f for f, r in field_report.items() if not r["type_ok"]]
        res["A4"] = {
            "verdict": PASS if not bad else FAIL,
            "detail": "五欄齊備且型別可用" if not bad else "不合格欄位：%s" % bad,
            "fields": field_report,
        }

    # --- A5 單篇與留言端點 ---
    post = obs.get("post") or {}
    comments = obs.get("comments") or {}
    if not post.get("attempted") and not comments.get("attempted"):
        proximate = "A3" if res["A3"]["verdict"] != PASS else "A4"
        res["A5"] = {"verdict": NOT_EXECUTED,
                     "blocked_by": _root_blocker(res, proximate),
                     "blocked_chain": proximate,
                     "detail": "無可用的 post id，兩個端點皆未請求"}
    else:
        ok = (post.get("status_code") == 200 and post.get("json_parsed")
              and comments.get("status_code") == 200 and comments.get("json_parsed"))
        res["A5"] = {
            "verdict": PASS if ok else FAIL,
            "detail": "單篇 HTTP %s / 留言 HTTP %s" % (
                post.get("status_code"), comments.get("status_code")),
        }

    # --- 整體判定 ---
    #
    # 順序有意義：**先看儀器有沒有壞**，再看端點答得對不對。
    # 儀器壞掉時，端點的答案（不論對錯）都沒有資格被寫進永久治理紀錄。
    criteria_keys = ("A1", "A2", "A3", "A4", "A5")
    instrument_failures = [
        k for k in criteria_keys
        if res[k]["verdict"] == NOT_EXECUTED and res[k].get("blocked_by") is None
    ]
    verdicts = [res[k]["verdict"] for k in criteria_keys]

    if instrument_failures:
        overall = INCONCLUSIVE
    elif all(v == PASS for v in verdicts):
        overall = PASS
    else:
        overall = FAIL

    # --- A6 量測（不參與判定） ---
    # A6 依賴 A3 的回應內容，因此同樣適用 §3.2.1 的 NOT EXECUTED 規則，
    # 且同樣要歸因到**根因**而非最近一層（第三輪修正：原本硬寫 "A3"）。
    if res["A3"]["verdict"] != PASS:
        res["A6"] = {"verdict": NOT_EXECUTED,
                     "blocked_by": _root_blocker(res, "A3"),
                     "blocked_chain": "A3",
                     "detail": "A3 未通過，沒有可量測的標題"}
    else:
        res["A6"] = measure_keyword_coverage(listing, obs.get("keywords") or {})

    result = {
        "criteria": res,
        "overall": overall,
        "overall_note": "A6 為量測項，不參與整體判定",
    }
    if instrument_failures:
        result["instrument_failures"] = instrument_failures
        result["inconclusive_reason"] = (
            "以下判準無上游阻斷卻仍未執行，代表本次執行未產出可用觀察："
            + "、".join("%s（%s）" % (k, res[k].get("detail", "")) for k in instrument_failures)
        )
        result["inconclusive_handling"] = (
            "INCONCLUSIVE **不走提案 §4.1**（那條路徑會把「已實測不可用」寫進永久治理紀錄）。"
            "改為呈報 PO，由 PO 決定是否授權重跑——重跑消耗新的請求配額，本就需要授權。"
            "**INCONCLUSIVE 不得被讀成「可用」。**"
        )
    return result


# ---------------------------------------------------------------------------
# 網路存取——與判定邏輯嚴格分離
# ---------------------------------------------------------------------------
class RequestBudget:
    """把「還能發幾次請求」變成一個會拋例外的物件，而不是一段要記得遵守的註解。

    提案 §3.1 的上限若只寫在文件裡，執行時沒有任何東西會擋它。
    這個類別讓超限成為 RuntimeError——驗證會中止，而不是安靜地變成一次小規模爬取。
    """

    def __init__(self, max_logical: int, max_attempts: int):
        self.max_logical = max_logical
        self.max_attempts = max_attempts
        self.logical_used = 0
        self.attempts_used = 0

    def take_logical(self, label: str) -> None:
        if self.logical_used >= self.max_logical:
            raise RuntimeError(
                "邏輯請求已達上限 %d（嘗試發出 %s）——提案 §3.1 的硬上限"
                % (self.max_logical, label))
        self.logical_used += 1

    def take_attempt(self) -> None:
        if self.attempts_used >= self.max_attempts:
            raise RuntimeError("HTTP 嘗試次數已達上限 %d（含重試）" % self.max_attempts)
        self.attempts_used += 1

    def as_dict(self) -> dict:
        return {
            "logical_requests_used": self.logical_used,
            "logical_requests_max": self.max_logical,
            "http_attempts_used": self.attempts_used,
            "http_attempts_max": self.max_attempts,
        }


def fetch(url: str, budget: RequestBudget, label: str) -> dict:
    """發出一個邏輯請求（含重試），回傳觀察紀錄。

    重試只在**傳輸層錯誤、429 與 5xx** 時發生——4xx（除 429）代表端點明確回答了，
    重試不會讓答案改變，只會多打對方伺服器。
    """
    import requests  # 延後 import：--dry-run 路徑不需要它

    budget.take_logical(label)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    record = {
        "label": label,
        "attempted": True,
        "url": url,
        # 我們**打算**送出的標頭。留著是為了與實際送出的對照，
        # **A2 不判這個** —— 判它等於拿自己寫的字典驗證自己，結構上不可能失敗。
        "intended_headers": dict(headers),
        # 實際送出的標頭，來自 `resp.request.headers`。
        # requests 2.34.2 的 `Session.prepare_request()` 會呼叫 `get_netrc_auth()`，
        # 在 `~/.netrc` 存在時補上 `Authorization`；env proxy 也可能補
        # `Proxy-Authorization`。這兩者都不會出現在上面那個本地字典裡——
        # 也就是說「真的送出了認證，卻回報未送出」是可能發生的。A2 判的是這一個。
        "sent_headers": None,
        "attempts": 0,
        "status_code": None,
        "elapsed_seconds": None,
        "json_parsed": False,
        "error": None,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        budget.take_attempt()
        record["attempts"] = attempt
        started = time.time()
        try:
            # 不建立 Session、不帶 cookies：A2 要驗證的正是「免登入可存取」
            resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except Exception as exc:
            record["error"] = "%s: %s" % (type(exc).__name__, exc)
            record["elapsed_seconds"] = round(time.time() - started, 3)
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SECONDS[attempt - 1])
                continue
            return record

        record["elapsed_seconds"] = round(time.time() - started, 3)
        record["status_code"] = resp.status_code
        record["final_url"] = resp.url
        record["response_headers"] = dict(resp.headers)
        # 實際送出的標頭（requests 準備完畢後的最終形態）——A2 判的就是它。
        # 記錄當下即遮蔽認證類標頭的**值**（見 SENSITIVE_HEADERS 的說明）。
        try:
            record["sent_headers"] = redact_headers(resp.request.headers)
        except AttributeError:
            record["sent_headers"] = None

        if resp.status_code == 429 or resp.status_code >= 500:
            record["error"] = "HTTP %d，可重試" % resp.status_code
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SECONDS[attempt - 1])
                continue

        _record_body(record, resp)
        return record

    return record


def _record_body(record: dict, resp) -> None:
    """把回應 body 化為證據。§3.3 要求的內容都在這裡產生。"""
    try:
        payload = resp.json()
        record["json_parsed"] = True
    except Exception as exc:
        record["json_parsed"] = False
        record["parse_error"] = "%s: %s" % (type(exc).__name__, exc)
        record["body_prefix"] = resp.text[:500]
        lowered = record["body_prefix"].lower()
        if "<title>" in lowered:
            start = lowered.index("<title>") + len("<title>")
            end = lowered.find("</title>", start)
            record["html_title"] = record["body_prefix"][start:end if end > 0 else None]
        return

    record["top_level_type"] = type(payload).__name__
    if isinstance(payload, list):
        record["item_count"] = len(payload)
        if payload and isinstance(payload[0], dict):
            record["first_item"] = payload[0]
            # §3.3：完整 key 清單，不只是缺哪一個——
            # 它讓「端點還在但契約過期」與「端點消失」兩種 FAIL 可以被區分。
            record["first_item_keys"] = sorted(payload[0].keys())
        record["titles"] = [
            item.get("title") for item in payload
            if isinstance(item, dict) and isinstance(item.get("title"), str)
        ]
    else:
        record["item_count"] = None
        record["body_prefix"] = resp.text[:500]


def collect(keywords_snapshot: dict) -> dict:
    """執行實際觀察。最多 3 個邏輯請求。"""
    budget = RequestBudget(MAX_LOGICAL_REQUESTS, MAX_HTTP_ATTEMPTS)
    obs = {
        "keywords": keywords_snapshot,
        "listing": fetch(LIST_URL, budget, "listing"),
        "post": {"attempted": False},
        "comments": {"attempted": False},
    }

    first = obs["listing"].get("first_item") or {}
    post_id = first.get("id")
    if post_id is None:
        obs["budget"] = budget.as_dict()
        return obs

    time.sleep(random.uniform(*DELAY_RANGE))
    obs["post"] = fetch(POST_URL.format(post_id=post_id), budget, "post")
    time.sleep(random.uniform(*DELAY_RANGE))
    obs["comments"] = fetch(COMMENTS_URL.format(post_id=post_id), budget, "comments")
    obs["budget"] = budget.as_dict()
    return obs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _environment() -> dict:
    """§3.3 要求記錄 UTC 與本地兩個時間戳。

    **陷阱（第四輪複查指出）**：容器未設 `TZ`，`datetime.now().astimezone()`
    因此回傳的仍是 UTC —— 一個**宣稱自己是本地時間、實際不是**的欄位。
    技術上沒錯，但讀者會以為那是執行者所在時區的壁鐘時間。
    改為同時記錄時區名稱，並在兩者相同時明講原因。
    """
    local = _dt.datetime.now().astimezone()
    tz_name = local.tzname() or "unknown"
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "in_container": os.path.exists("/.dockerenv"),
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "timestamp_local": local.isoformat(),
        "local_timezone": tz_name,
        "timezone_note": (
            "容器未設定 TZ，因此本地時間即 UTC——"
            "`timestamp_local` 與 `timestamp_utc` 相同是預期行為，不是重複記錄。"
            "執行者所在時區的壁鐘時間需另行換算。"
            if tz_name == "UTC" else
            "容器時區為 %s" % tz_name
        ),
    }


def _print_report(result: dict, obs: dict) -> None:
    print("=" * 72)
    print("UG-G2-SB5 Dcard 可用性驗證")
    print("=" * 72)
    for key in ("A1", "A2", "A3", "A4", "A5"):
        item = result["criteria"][key]
        blocked = item.get("blocked_by")
        suffix = "（阻斷來源：%s）" % blocked if blocked else ""
        print("  %-3s %-12s %s%s" % (key, item["verdict"], item.get("detail", ""), suffix))
    a6 = result["criteria"]["A6"]
    if a6.get("verdict") == MEASURED:
        print("  A6  MEASURED     %s/%s 篇命中，命中詞 %s（不參與判定）" % (
            a6.get("matched_articles"), a6.get("titles_examined"),
            a6.get("matched_keywords")))
    else:
        print("  A6  %-12s %s（不參與判定）" % (a6.get("verdict"), a6.get("detail", "")))
    print("-" * 72)
    print("  整體判定：%s" % result["overall"])
    if result.get("instrument_failures"):
        print("  [INCONCLUSIVE] %s" % result["inconclusive_reason"])
        print("  這是**我們自己的問題**，不是端點的問題——不走 §4.1，呈報 PO 決定是否授權重跑。")
        print("  INCONCLUSIVE 不得被讀成「可用」。")
    budget = obs.get("budget")
    if budget:
        print("  請求用量：邏輯 %d/%d，HTTP 嘗試 %d/%d" % (
            budget["logical_requests_used"], budget["logical_requests_max"],
            budget["http_attempts_used"], budget["http_attempts_max"]))
    print("=" * 72)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="UG-G2-SB5 Dcard 可用性驗證")
    parser.add_argument("--keywords", help="關鍵字快照檔（A6 的輸入；正式執行時必要）")
    parser.add_argument("--out", help="證據輸出路徑（JSON）")
    parser.add_argument("--dry-run", dest="dry_run",
                        help="以 fixture 檔驅動判定邏輯，**不發出任何網路請求**")
    args = parser.parse_args(argv)

    if args.dry_run:
        with open(args.dry_run, encoding="utf-8") as fh:
            obs = json.load(fh)
        result = evaluate(obs)
        _print_report(result, obs)
        print("  [DRY RUN] 未發出任何網路請求；本次僅驗證判定邏輯。")
        return 0

    if not args.keywords:
        parser.error("正式執行必須提供 --keywords（A6 需要關鍵字快照，"
                     "且本腳本刻意不連 DB）")
    with open(args.keywords, encoding="utf-8") as fh:
        keywords_snapshot = json.load(fh)

    obs = collect(keywords_snapshot)
    result = evaluate(obs)
    _print_report(result, obs)

    evidence = {
        "purpose": "UG-G2-SB5 Dcard 可用性驗證原始證據（提案 §3.3）",
        "environment": _environment(),
        "parameters": {
            "list_url": LIST_URL,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES,
            "backoff_seconds": list(BACKOFF_SECONDS),
            "delay_range": list(DELAY_RANGE),
            "max_logical_requests": MAX_LOGICAL_REQUESTS,
            "max_http_attempts": MAX_HTTP_ATTEMPTS,
        },
        "scope_disclosure": (
            "只驗證股票板（stock）。契約 §4.1 的目標板塊為 stock + money 兩個板，"
            "本次未驗 money 板（提案 §1.9）。PASS 只能讀成「股票板於驗證當下可用」。"
        ),
        "observations": obs,
        "result": result,
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=2, default=str)
            fh.write("\n")
        print("  證據已寫入：%s" % args.out)
    else:
        print("  [注意] 未指定 --out，證據未落檔。")

    # 退出碼刻意不用來表達 PASS/FAIL：FAIL 是一個合法且可能正確的結果，
    # 不是腳本執行失敗。非零只保留給「腳本自己出錯」。
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("[ABORT] %s" % exc, file=sys.stderr)
        raise SystemExit(3)
