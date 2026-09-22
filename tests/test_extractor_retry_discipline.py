# -*- coding: utf-8 -*-
"""UG-G2-SB7：對外取數的重試紀律（DEC-032）在**生產 extractor** 上的守衛。

================================================================================
本檔的存在理由：DEC-032 已核准，而生產程式碼三處違反
================================================================================
DEC-032（`APPROVED`，2026-09-02）的適用範圍逐字為
「**專案級**——所有對外部端點取數的腳本，含 `UG-G2-SB6`／`UG-G2-SB7`」。

它的規則是：

| 類別 | 語意 | 處置 |
|------|------|------|
| **403 / 429** | 服務**在叫你停** | **硬停，一次都不重試** |
| **5xx** | 服務**沒能回答** | 退避後**有界**重試 |
| 傳輸層失敗 | 服務**連我們問了什麼都還不知道** | 同一邏輯請求內**有界**重試 |

而 `tenacity.retry` **未給 `retry=` 條件時對任何例外都重試**，
搭配 `response.raise_for_status()` 就使 403／429 被重試三次 ——
**`ptt_scraper.py:31` 的 docstring 自己寫著「遇到 429 或 500 等錯誤會自動等待
2s, 4s, 8s 重試」。這不需要推論，程式自己記載了它在做 DEC-032 禁止的事。**

================================================================================
⚠ 本檔在修正前先建立，且**刻意先跑出 FAIL**
================================================================================
`CLAUDE.md` §13.5：「新增 bug fix 時，若可行應先建立會重現問題的測試，再修復。」
§9A.2：出示不了 known-FAIL 案例的檢查，不計入證據。

**V1 對修正前的程式碼會 FAIL，那個 FAIL 的原始輸出是本 SB 的 known-FAIL 證據。**

================================================================================
為何不打真實網路
================================================================================
全部以 `unittest.mock` 替換 `requests.get`／`requests.Session.get`。
**判準量的是「我們發了幾次請求」，那不需要對方真的存在** ——
而對政府單位或社群網站發 429 來測試自己的重試行為，本身就是 DEC-032 要防的行為。
"""
import os
import sys
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extractors.ptt_scraper import PttScraper  # noqa: E402
from src.extractors.twse_scraper import TwseScraper  # noqa: E402


def make_response(status_code, text="", json_body=None):
    """造一個能通過 `raise_for_status()` 判定的假回應。"""
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = (text or "").encode("utf-8")
    resp.url = "https://example.invalid/"
    if json_body is not None:
        resp._content = __import__("json").dumps(json_body).encode("utf-8")
        resp.headers["Content-Type"] = "application/json"
    return resp


class _Counter:
    """記錄實際發出的 HTTP 嘗試次數（DEC-032 雙軌計數的第二軌）。"""

    def __init__(self, response_factory):
        self.attempts = 0
        self._factory = response_factory

    def __call__(self, *args, **kwargs):
        self.attempts += 1
        return self._factory()


class V1RefusalIsNotRetried(unittest.TestCase):
    """**V1**：403／429 硬停，一次都不重試。

    **什麼輸入會讓它 FAIL**：任何對 403／429 重試的實作。
    修正前 `@retry(stop=stop_after_attempt(3))` 無 `retry=` 條件，
    `raise_for_status()` 對 429 拋 `HTTPError`，因此**嘗試 3 次** → 本測試 FAIL。

    ⚠ **斷言的是「嘗試次數恰為 1」，不是「有拋例外」** ——
    後者在重試三次後也成立，**分不出有沒有重試**。
    """

    def test_v1_twse_scraper_does_not_retry_429(self):
        counter = _Counter(lambda: make_response(429))
        with patch("src.extractors.twse_scraper.requests.get", counter):
            with self.assertRaises(Exception):
                TwseScraper()._fetch_json("https://example.invalid/x")
        self.assertEqual(
            counter.attempts, 1,
            "429 是「服務在叫你停」，DEC-032 要求一次都不重試；實際嘗試 %d 次"
            % counter.attempts)

    def test_v1_twse_scraper_does_not_retry_403(self):
        counter = _Counter(lambda: make_response(403))
        with patch("src.extractors.twse_scraper.requests.get", counter):
            with self.assertRaises(Exception):
                TwseScraper()._fetch_json("https://example.invalid/x")
        self.assertEqual(counter.attempts, 1,
                         "403 同 429；實際嘗試 %d 次" % counter.attempts)

    def test_v1_ptt_scraper_does_not_retry_429(self):
        counter = _Counter(lambda: make_response(429))
        with patch("src.extractors.ptt_scraper.requests.get", counter):
            with self.assertRaises(Exception):
                PttScraper()._fetch_page("https://example.invalid/x")
        self.assertEqual(
            counter.attempts, 1,
            "PTT 是社群網站，對一個叫我們停的 429 做三次指數退避，"
            "正是 DEC-032 要防的行為；實際嘗試 %d 次" % counter.attempts)


class V5ServerErrorIsRetriedButBounded(unittest.TestCase):
    """**V5**：5xx 與傳輸層失敗**有界**重試，且最終仍失敗。

    **什麼輸入會讓它 FAIL**：無上限重試 —— 那會讓本測試**永遠不結束**。
    ⚠ **「測試不會結束」在此明確定義為 FAIL**，不是留成一個會卡住的測試。
    上限以 `MAX_HTTP_ATTEMPTS` 表達，實作若超過即 FAIL。
    """

    MAX_HTTP_ATTEMPTS = 3   # 現行 `stop_after_attempt(3)`；修正後不得放大

    def test_v5_twse_scraper_bounded_on_500(self):
        counter = _Counter(lambda: make_response(500))
        with patch("src.extractors.twse_scraper.requests.get", counter):
            with self.assertRaises(Exception):
                TwseScraper()._fetch_json("https://example.invalid/x")
        self.assertGreater(counter.attempts, 1, "5xx 是『服務沒能回答』，應重試")
        self.assertLessEqual(
            counter.attempts, self.MAX_HTTP_ATTEMPTS,
            "重試必須有上限；實際嘗試 %d 次" % counter.attempts)

    def test_v5_ptt_scraper_bounded_on_500(self):
        counter = _Counter(lambda: make_response(500))
        with patch("src.extractors.ptt_scraper.requests.get", counter):
            with self.assertRaises(Exception):
                PttScraper()._fetch_page("https://example.invalid/x")
        self.assertGreater(counter.attempts, 1)
        self.assertLessEqual(counter.attempts, self.MAX_HTTP_ATTEMPTS,
                             "實際嘗試 %d 次" % counter.attempts)

    def test_v5_transport_failure_is_retried_but_bounded(self):
        """傳輸層失敗（連線／TLS）—— 服務**連我們問了什麼都還不知道**。"""
        def boom():
            raise requests.exceptions.ConnectionError("simulated TLS handshake failure")
        counter = _Counter(boom)
        with patch("src.extractors.twse_scraper.requests.get", counter):
            with self.assertRaises(Exception):
                TwseScraper()._fetch_json("https://example.invalid/x")
        self.assertGreater(counter.attempts, 1,
                           "傳輸層失敗應重試——它與『服務拒絕』無關")
        self.assertLessEqual(counter.attempts, self.MAX_HTTP_ATTEMPTS,
                             "實際嘗試 %d 次" % counter.attempts)


class SuccessPathUnaffected(unittest.TestCase):
    """**反向守衛**：加上 `retry=` 條件後，成功路徑不得改變。

    **沒有這一組，V1／V5 全綠也可能只代表「重試被整個拿掉了」** ——
    那會同時讓 5xx 不再重試，而那是 DEC-032 明文允許的行為。
    """

    def test_twse_success_returns_json_with_single_attempt(self):
        counter = _Counter(lambda: make_response(200, json_body={"stat": "OK"}))
        with patch("src.extractors.twse_scraper.requests.get", counter), \
             patch("src.extractors.twse_scraper.time.sleep"):
            data = TwseScraper()._fetch_json("https://example.invalid/x")
        self.assertEqual(data, {"stat": "OK"})
        self.assertEqual(counter.attempts, 1)

    def test_ptt_success_returns_text_with_single_attempt(self):
        counter = _Counter(lambda: make_response(200, text="<html>ok</html>"))
        with patch("src.extractors.ptt_scraper.requests.get", counter), \
             patch("src.extractors.ptt_scraper.time.sleep"):
            html = PttScraper()._fetch_page("https://example.invalid/x")
        self.assertIn("ok", html)
        self.assertEqual(counter.attempts, 1)


if __name__ == "__main__":
    unittest.main()
