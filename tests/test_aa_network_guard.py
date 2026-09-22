# -*- coding: utf-8 -*-
"""測試套件的**全域對外網路守衛**（UG-G2-SB7，複查方 2026-09-04 指定）。

================================================================================
為什麼需要它：一次事故，以及一個會重演的修法
================================================================================
`UG-G2-SB7` 把 `run_price_batch` 接進 `run_all_daily_tasks` 之後，
`test_operational_ux` 與 `test_db_read_semantics` 兩個**單元測試**
**真的對政府單位的服務發出了請求** —— 它們呼叫 `run_all_daily_tasks()`，
而那個函式新增了一個會觸網的階段。

**紅字是後果，不是偵測**：traceback 停在 run log 寫入，
代表 fetch 那一段**已經跑完了**，請求早就出去了。

當時的修法是往那兩個測試各補一行 mock —— 它們的隔離方式是**一份逐項列舉的清單**：

    pipeline.run_twse_pipeline_from_candidate_prices = MagicMock()
    pipeline.run_us_stock_pipeline            = MagicMock()
    pipeline.run_ptt_pipeline                 = MagicMock()
    pipeline.run_nlp_sentiment_pipeline       = MagicMock()
    pipeline.run_feature_engineering_pipeline = MagicMock()
    pipeline.run_price_batch                  = MagicMock()   <- 補上的第六個

> **往清單裡再加一項，沒有讓偵測出現，只是讓這一次的後果消失。**
> **下一個新增的階段會完全重演這件事。**

本專案抓過同一個形狀很多次：`PROJECT_STATUS.md` §0.5 #5 列了兩個地點漏掉第三個、
GOV-10 把「驗證腳本」寫成已覆蓋、`UG-G2-SB6` §11 的摘要落後本體。

> **列舉的會漏，描述性質的不會。**

判準因此不是「哪些方法要 mock」，而是 **「這一輪測試有沒有向外開連線」**。

================================================================================
⚠ 為什麼守衛在這裡，而不是 `tests/__init__.py`
================================================================================
**第一版寫在 `tests/__init__.py`，那是死碼。**
本專案的標準測試指令是 `python -m unittest discover -s tests -p "test_*.py"`
（`CLAUDE.md` §13.1），而 `discover` 以 `tests/` 為 top-level dir，
**不會匯入該套件**。實測：`'tests' in sys.modules` 為 `False`。

> **一個放錯位置的守衛，與沒有守衛在輸出上完全一樣** —— 兩者都只印 OK。
> 第一版的 known-FAIL 案例**通過了**，那正是它被發現是死碼的方式。

改放在一個測試模組裡，於 import 時安裝。

⚠⚠ **檔名的 `aa` 前綴不是正確性的依據。** 它只是讓本模組盡量早被匯入；
**即使它排在最後，所有測試方法仍然受保護**（理由見下一段）。
把 `aa` 當成防護的來源，會讓下一個人以為改檔名就會失效 —— 那是錯的擔心，
而錯的擔心會排擠掉對的擔心（真正的限制列在最後一節）。

**排序依賴的實際範圍比看起來小**：`unittest discover` **先匯入全部模組、
再執行測試**，所以任一模組在 import 時裝上守衛，**所有測試方法都受保護**。
排序只影響**其他模組在 import 時期**的網路行為 —— 故取名 `test_aa_*` 讓它盡量早。

⚠ 這仍是排序依賴，**與 `test_canonical_stock_id.py` 的 stub 同一種脆弱**。
差別在於：stub 靠排序**取代**真實套件（贏了才有害），
本守衛靠排序**提早保護**（早了才更有用），**方向相反**。

================================================================================
已知限制【誠實揭露】
================================================================================
1. **只擋 `socket` 層的連線。** 子行程（`curl`）、已存在的連線、UDP `sendto` 看不到。
2. **`getaddrinfo`（DNS）不擋** —— 解析不是連線，擋它會讓失敗訊息落在錯的地方。
   **代價：只做 DNS 而不連線的測試不會被抓到。**
3. **直接 `python tests/test_x.py` 不經過 discover，該路徑不受保護。**
4. **loopback 刻意放行**：`127.0.0.1`／`::1` 是資料庫，那是**另一條軸**
   （§13.4 的封閉性缺口 HERM-01~09）。
   **兩條軸混在一起，會讓失敗訊息無法歸因。**
"""
import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})


class OutboundNetworkBlocked(RuntimeError):
    """單元測試嘗試對外開連線。

    **這個例外存在的意義是它會被丟出來** —— 一個只寫在文件裡的
    「測試不應觸網」，在被違反時不會發出任何聲音（§9A.1）。
    """


def _host_of(address):
    if isinstance(address, (tuple, list)) and address:
        return address[0]
    return address


def _is_loopback(host):
    if not isinstance(host, str):
        return False
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def _blocked(address, verb):
    raise OutboundNetworkBlocked(
        "單元測試不得對外開連線：%s(%r)。\n"
        "  若這是新增的管線階段造成的，**正確處置是在測試中隔離該階段**，\n"
        "  不是在此開旁路。\n"
        "  （UG-G2-SB7：一次 unittest discover 曾真的對政府單位的服務發出請求。）"
        % (verb, address))


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) \
            and not _is_loopback(_host_of(address)):
        _blocked(address, "connect")
    return _REAL_CONNECT(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) \
            and not _is_loopback(_host_of(address)):
        _blocked(address, "connect_ex")
    return _REAL_CONNECT_EX(self, address)


# **安裝於 import 時** —— 見上方「為什麼守衛在這裡」。
socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex


class NetworkGuardIsInstalled(unittest.TestCase):
    """守衛自身的 known-FAIL：**證明它會擋，不只是存在**。

    ⚠ 這些斷言**不觸網** —— 用的是 `203.0.113.1`（RFC 5737 TEST-NET-3，
    保留給文件用途、不可路由）。**守衛在連線建立之前就 raise，
    所以連 SYN 都不會送出。**
    """

    TEST_NET_3 = "203.0.113.1"

    def test_outbound_connect_is_blocked(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(OutboundNetworkBlocked):
                s.connect((self.TEST_NET_3, 443))
        finally:
            s.close()

    def test_outbound_connect_ex_is_blocked(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(OutboundNetworkBlocked):
                s.connect_ex((self.TEST_NET_3, 443))
        finally:
            s.close()

    def test_requests_cannot_reach_out(self):
        """**這一項最接近真實事故的形狀** —— 走 `requests` 而非裸 socket。"""
        import requests
        with self.assertRaises(Exception) as ctx:
            requests.get("https://203.0.113.1/", timeout=2)
        # requests 會把底層例外包成 ConnectionError；訊息裡仍帶得到守衛的字樣。
        self.assertIn("單元測試不得對外開連線", str(ctx.exception))

    def test_loopback_is_deliberately_allowed(self):
        """loopback 放行 —— 資料庫是另一條軸（§13.4）。

        **不驗證能否連上**（沒有服務在聽），只驗證**守衛沒有攔它**：
        失敗必須是連線層的錯誤，**不是 `OutboundNetworkBlocked`**。
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            with self.assertRaises(OSError) as ctx:
                s.connect(("127.0.0.1", 59999))
            self.assertNotIsInstance(ctx.exception, OutboundNetworkBlocked)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
