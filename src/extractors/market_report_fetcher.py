# src/extractors/market_report_fetcher.py
"""全市場報表的**生產取數器**（TWSE `MI_INDEX` 與 TPEx 盤後行情）。

================================================================================
為什麼 SB7 要有這個模組
================================================================================
`UG-G2-SB7` 的 Brief 寫「將**逐股票**爬取改為批次化」，
而 `UG-G2-SB9` 已經證明：**一天一個請求就拿到整個市場**。

所以「批次抓 150 檔」是錯的問法 —— 正確的是**抓一次市場、過濾出 universe**：

| 路徑 | 端點 | 取 150 檔的請求數 |
|------|------|------------------|
| 逐股（`twse_scraper`） | `exchangeReport/STOCK_DAY?stockNo=` | **150** |
| 全市場（本模組） | `MI_INDEX` / TPEx 盤後行情 | **1** |

**對政府單位的服務而言，這差兩個數量級。**

================================================================================
與 `scripts/verify/fetch_candidate_prices.py` 的關係
================================================================================
那支腳本在 `UG-G2-SB9` 取得了 983 個交易日、1,821,870 列，
**其取數紀律是本模組的來源**（DEC-032 的實作值：`TRANSPORT_RETRIES`／
`SERVER_ERROR_RETRIES`／退避表／雙軌計數）。

⚠ **那支腳本刻意不動** —— 它是 SB9 的已驗證交付物，且其職責是
「一次回補數百個交易日、逐日比對提案判準」；本模組的職責是
「每日增量取一天」。**兩者的失敗語意不同**：前者失敗要停止整段並記下日期，
後者失敗只需把該日該市場記為 `FETCH_FAILED` 並讓其餘批次繼續。

**表格定位共用 `market_report_table`，沒有第二份實作。**

================================================================================
DEC-032（`APPROVED`）的實作
================================================================================
| 類別 | 判別 | 處置 |
|------|------|------|
| 傳輸層失敗 | **拿不到 `status_code`** | 同一邏輯請求內有界重試（5 次，退避 5／10／20／40／60 秒），**不消耗邏輯請求配額** |
| 5xx | 服務沒能回答 | 退避 60 秒後有界重試 1 次 |
| **403／429** | **服務在叫你停** | **硬停，一次都不重試**，拋 `ServiceRefusedError` |

**雙軌計數**：`logical_requests`（我們想問的問題數）與 `http_attempts`
（造成的實際負載）分開回報 —— 少了後者就無法回答「這次執行對對方造成多少負擔」。
"""

import datetime as _dt
import random
import time

import requests

from src.extractors.market_report_table import (
    TPEX_FIELD_PATTERNS, _find_market_table,
)
from src.extractors.tpex_market_report import parse_tpex_report
from src.extractors.twse_market_report import parse_market_report
from src.common.clock import today_taipei

TWSE_ENDPOINT = ("https://www.twse.com.tw/exchangeReport/MI_INDEX"
                 "?response=json&date={date}&type=ALLBUT0999")


def tpex_url(iso_date):
    """`UG-G2-SB9` 的 TPEx 候選 2（C1–C6 全 PASS 的那一個）。

    ⚠ **候選 1（openapi）在 C2 FAIL** —— 它是當前快照、URL 無日期參數，
    **只給得出「今天」**。生產路徑需要指定日期，故不可用。
    """
    return ("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
            "?date=%s&type=EW&response=json" % iso_date.replace("-", "/"))


USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT_SECONDS = 15
# 比 PTT 的 1.5–3.0 保守：**對象是政府單位的服務**。
DELAY_RANGE = (3.0, 5.0)

# DEC-032 的實作值，逐字沿用 `UG-G2-SB9` 在 983 個交易日上驗證過的那一組。
TRANSPORT_RETRIES = 5
TRANSPORT_BACKOFF_SECONDS = (5, 10, 20, 40, 60)
SERVER_ERROR_RETRIES = 1
SERVER_ERROR_BACKOFF_SECONDS = 60

MARKETS = ("twse", "tpex")
SOURCE_BY_MARKET = {"twse": "twse_mi_index", "tpex": "tpex_daily_quotes"}


class ServiceRefusedError(RuntimeError):
    """403／429 —— **服務在叫你停**。

    **刻意與 `FetchFailedError` 分成兩個型別**：兩者在「這一批沒拿到資料」上
    長得一樣，但**處置完全不同** —— 前者必須停止並請示，
    後者只需記下該項目並讓其餘批次繼續（DEC-032）。
    合成同一個型別，呼叫端就分不出來了。

    ⚠ **`outcomes_by_item` 讓那個區別跨得過例外邊界**（2026-09-04 修正）。
    先前 `run_price_batch` 算對了逐項 outcome、寫進了 run log，
    **然後 raise 把它整個丟掉** —— 下游只好把上櫃標的記成 `FETCH_FAILED`。

    > **型別上分開了，outcome 欄上又合回去** ——
    > 「合成同一個型別，呼叫端就分不出來了」那句話在那裡逐字成立，只是換了一層。

    **預設為空 dict 而非 `None`**：呼叫端不必再分辨「沒帶」與「帶了空的」。
    """

    def __init__(self, *args, **kwargs):
        self.outcomes_by_item = dict(kwargs.pop("outcomes_by_item", None) or {})
        super(ServiceRefusedError, self).__init__(*args, **kwargs)


class FetchFailedError(RuntimeError):
    """傳輸層失敗、5xx 重試耗盡，或回應中找不到可用的表。

    ⚠ **這不是「沒有資料」** —— 呼叫端必須把它記為 `FETCH_FAILED`，
    **不得**寫成 `NO_DATA`（`CLAUDE.md` §7.1：失敗與真的沒有資料必須可區分）。
    """


class FetchResult(object):
    """一次「一市場一日」取數的結果。

    `records` 為空**不代表失敗** —— 非交易日的報表本來就沒有資料列。
    呼叫端據此區分 `OK`（有列）與 `NO_DATA`（請求成功但無列）。
    """

    def __init__(self, market, trade_date, records, stats,
                 logical_requests, http_attempts, diagnostics=None):
        self.market = market
        self.trade_date = trade_date
        self.records = records
        self.stats = stats
        self.logical_requests = logical_requests
        self.http_attempts = http_attempts
        self.diagnostics = diagnostics or {}

    @property
    def outcome(self):
        """`OK`／`NO_DATA` —— **本類別不會回傳 `FETCH_FAILED`**，那是例外的職責。"""
        return "OK" if self.records else "NO_DATA"


def _sleep(seconds):
    """獨立函式，方便測試以 `patch` 取代而不必真的等。"""
    time.sleep(seconds)


def _http_get(url, counter):
    """發出一次 HTTP 請求，**傳輸層失敗在內部有界重試**。

    `counter` 是一個單元素 list，用來累計 HTTP 嘗試次數（雙軌計數的第二軌）。

    ⚠ 判別依據是**有沒有拿到回應物件**，不是例外類別名稱 ——
    後者需要窮舉，而窮舉不完的那一項會被靜默歸錯類（DEC-032 §Decision）。
    """
    last_exc = None
    for i in range(1 + TRANSPORT_RETRIES):
        counter[0] += 1
        try:
            return requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=TIMEOUT_SECONDS)
        except Exception as exc:      # noqa: BLE001 —— 見上方判別依據說明
            last_exc = exc
            if i < TRANSPORT_RETRIES:
                _sleep(TRANSPORT_BACKOFF_SECONDS[
                    min(i, len(TRANSPORT_BACKOFF_SECONDS) - 1)])
    raise FetchFailedError(
        "傳輸層失敗，重試 %d 次後仍未取得回應：%s" % (TRANSPORT_RETRIES, last_exc))


def _fetch_payload(url, counter):
    """取得 JSON payload，套用 DEC-032 的三分處置。"""
    resp = _http_get(url, counter)
    if resp.status_code in (403, 429):
        raise ServiceRefusedError(
            "HTTP %d（服務拒絕）—— 硬停，一次都不重試" % resp.status_code)
    if resp.status_code >= 500:
        for _ in range(SERVER_ERROR_RETRIES):
            _sleep(SERVER_ERROR_BACKOFF_SECONDS)
            resp = _http_get(url, counter)      # 走同一個入口，傳輸層保護一致
            if resp.status_code in (403, 429):
                raise ServiceRefusedError(
                    "HTTP %d（服務拒絕）—— 硬停，一次都不重試" % resp.status_code)
            if resp.status_code < 500:
                break
        if resp.status_code >= 500:
            raise FetchFailedError(
                "HTTP %d —— 退避重試 %d 次後仍失敗"
                % (resp.status_code, SERVER_ERROR_RETRIES))
    if resp.status_code >= 400:
        # 其餘 4xx：服務明確回答了，重試不會讓答案改變。
        raise FetchFailedError("HTTP %d" % resp.status_code)
    try:
        return resp.json()
    except ValueError as exc:
        raise FetchFailedError("回應不是可解析的 JSON：%s" % exc)


def fetch_market_report(market, trade_date, throttle=True):
    """取一個市場、一個交易日的全市場報表。

    Args:
        market: `'twse'` 或 `'tpex'`。
        trade_date: `datetime.date`。
        throttle: 取數後是否加隨機延遲（測試時關閉）。

    Returns:
        FetchResult

    Raises:
        ServiceRefusedError: 403／429 —— **停止並請示，不自行續行**。
        FetchFailedError: 傳輸層失敗／5xx 耗盡／回應無可用表。
        ValueError: `market` 不是支援的值。
    """
    if market not in MARKETS:
        raise ValueError("不支援的市場：%r（可用：%s）" % (market, ", ".join(MARKETS)))

    counter = [0]
    if market == "twse":
        url = TWSE_ENDPOINT.format(date=trade_date.strftime("%Y%m%d"))
    else:
        url = tpex_url(trade_date.strftime("%Y-%m-%d"))

    payload = _fetch_payload(url, counter)
    # ⚠ **欄名樣式必須依市場給** —— TPEx 的欄名與 TWSE 不同，
    # 用錯的一份會讓「表找到了但欄名對不上」長得像「端點沒有資料」。
    # （2026-09-04 STEP 1 實際發生過一次，見 `market_report_table` 的註解。）
    patterns = TPEX_FIELD_PATTERNS if market == "tpex" else None
    fields, rows, diagnostics = _find_market_table(payload, patterns)
    if fields is None:
        # ⚠ **找不到表不等於沒有資料** —— 端點改版與端點無資料在這裡分岔，
        # 而診斷資訊是唯一能分辨它們的東西。
        raise FetchFailedError(
            "回應中找不到可用的報表（診斷：%s）" % diagnostics)

    if market == "twse":
        records, stats = parse_market_report(fields, rows, trade_date)
    else:
        records, stats = parse_tpex_report(fields, rows, trade_date)

    if throttle:
        _sleep(random.uniform(*DELAY_RANGE))
    return FetchResult(market, trade_date, records, stats,
                       logical_requests=1, http_attempts=counter[0],
                       diagnostics=diagnostics)


def previous_business_day(reference=None):
    """回傳 `reference`（預設今天）之前最近的一個平日。

    ⚠ **只跳過週末，不知道國定假日** —— 那正是為什麼
    「請求成功但報表無列」必須是 `NO_DATA` 而不是 `FETCH_FAILED`：
    **假日的空報表是正確答案，不是失敗。**
    """
    # ⚠ 這個值決定批次取數**抓哪一個交易日**。
    # **台北時間每天 00:00–08:00，UTC 還停在前一天**（容器為 UTC）——
    # 用機器本地日期會整個錯開一天。時區政策見 `src/common/clock.py`。
    d = (reference or today_taipei()) - _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d


# ==================================================================
# 首次每日 ETL 缺口自動追補（`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`）
# ==================================================================
# ⚠ `previous_business_day()` 本身不變（見上）——它只回答「抓哪一天」，
# 不知道自己上次成功是什麼時候。缺口偵測是另一層，故意不混進同一個函式：
# 兩者的失敗語意不同，前者結構上不可能失敗，後者需要能拒絕執行。

MAX_BACKFILL_BUSINESS_DAYS = 30


class BackfillWindowExceededError(Exception):
    """缺口超過上界，拒絕自動追補，需要人工處理。

    刻意整個拒絕、不回傳被截斷的部分序列——呼叫端若誤用部分序列，
    會把「只補了一部分」當成「已經補完」，那比拒絕執行更危險。

    ⚠ **本例外在任何 `run_price_batch()` 呼叫之前就 raise，`etl_run_log`
    不會有任何一列**——這是設計上的 fail closed（審查方段 B 複核，2026-09-16
    登記）：日後若在 `etl_run_log` 找不到某次執行的紀錄，不代表沒有嘗試過，
    要先檢查 stderr／執行結束碼是否命中這兩個例外之一（見
    `MissingBackfillOriginError`，同一個限制）。
    """

    def __init__(self, gap_days, max_days):
        self.gap_days = gap_days
        self.max_days = max_days
        super().__init__(
            "缺口 %d 個平日超過上界 %d，拒絕自動追補，需人工處理"
            % (gap_days, max_days))


class MissingBackfillOriginError(Exception):
    """某市場在 candidate_prices 沒有任何既有列，沒有可推進的起點，拒絕自動追補。

    與 `BackfillWindowExceededError` 是不同的失敗模式：前者「不知道從哪裡開始」，
    後者「知道從哪裡開始，但太遠」——兩者都拒絕執行，但原因不同，不得共用同一個
    例外類別（`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md` §3.1）。

    ⚠ 同 `BackfillWindowExceededError`：**本例外在任何 `run_price_batch()`
    呼叫之前就 raise，`etl_run_log` 不會有任何一列**——這兩種拒絕只留在
    stderr 與非零結束碼，不留 run log（審查方段 B 複核，2026-09-16 登記，
    fail closed 的既定設計，不是遺漏）。
    """

    def __init__(self, market):
        self.market = market
        super().__init__(
            "市場 %r 在 candidate_prices 沒有任何既有列，無法計算缺口起點，"
            "拒絕自動追補，需人工處理" % (market,))


def compute_gap_backfill_dates(last_date, target_date, max_days=MAX_BACKFILL_BUSINESS_DAYS):
    """回傳 `last_date` 次日起、跳過週末，至 `target_date`（含）為止的平日序列。

    Args:
        last_date: 該市場在 `candidate_prices` 現有最新日期（`datetime.date`）。
        target_date: 追補終點，通常是 `previous_business_day()` 的回傳值（含）。
        max_days: 序列長度上界；超過則整個拒絕（見 `BackfillWindowExceededError`
            docstring），不回傳部分結果。

    Returns:
        List[datetime.date]，由舊到新排序；`last_date == target_date` 時為空列表。
    """
    dates = []
    d = last_date + _dt.timedelta(days=1)
    while d <= target_date:
        if d.weekday() < 5:
            dates.append(d)
        d += _dt.timedelta(days=1)
    if len(dates) > max_days:
        raise BackfillWindowExceededError(len(dates), max_days)
    return dates
