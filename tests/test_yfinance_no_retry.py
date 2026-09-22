# -*- coding: utf-8 -*-
"""UG-G2-SB7 §0.1a 的第二段：`yfinance` 路徑不重試，且**不宣稱符合 DEC-032**。

================================================================================
本檔釘住的是一個「刻意不做某件事」的決定
================================================================================
`yfinance_api.py` 先前有 `@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))`
**且無 `retry=` 條件**，而其 `except` 逐字寫著
`raise e  # 觸發 Tenacity 的重試機制` —— **程式自己記載了它在對任何例外
（包含可能的 429）重試三次**，那是 DEC-032 禁止的行為。

**修法不是「改成只對 5xx 重試」** —— 那個判別在這裡做不到：
`Ticker.history()` 把 HTTP 細節吞掉，**拿不到 `status_code`**，
而 DEC-032 的判別依據逐字就是那個。

**採「不重試，失敗一律 `FETCH_FAILED`」** ——
⚠ **那不是合規實作，是無法判別時的最保守行為。**

> **一個「刻意不做」的決定，若沒有測試釘住，會在下一次重構時被「補回來」** ——
> 而補回來的人會覺得自己在修一個缺少重試的路徑。
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extractors.yfinance_api import AUTO_ADJUST, YFinanceAPI  # noqa: E402


class YFinanceMustNotRetry(unittest.TestCase):
    """**失敗只嘗試一次。**

    **什麼輸入會讓它 FAIL**：任何形式的重試裝飾器 —— 呼叫次數 > 1。
    修正前是 3。
    """

    def test_failure_is_attempted_exactly_once(self):
        ticker = MagicMock()
        ticker.history.side_effect = RuntimeError("simulated provider failure")
        with patch("src.extractors.yfinance_api.yf.Ticker",
                   MagicMock(return_value=ticker)):
            with self.assertRaises(RuntimeError):
                YFinanceAPI().fetch_yfinance_data("NVDA")
        self.assertEqual(
            ticker.history.call_count, 1,
            "拿不到 status_code 就無法分辨『服務在叫你停』與『服務沒能回答』，"
            "**因此一次都不重試** —— 修正前是 3 次")

    def test_no_retry_decorator_is_attached(self):
        """直接檢查函式沒有被 tenacity 包住。

        **與上一項互補**：上一項量行為，這一項量結構 ——
        **有人若把裝飾器加回來但設 `stop_after_attempt(1)`，上一項會通過**，
        而那仍然是一個等著被調大的旋鈕。
        """
        fn = YFinanceAPI.fetch_yfinance_data
        self.assertFalse(hasattr(fn, "retry"),
                         "tenacity 會在被包住的函式上掛 `.retry`")
        self.assertFalse(hasattr(fn, "retry_with"))

    def test_empty_result_is_not_a_failure(self):
        """`NO_DATA` 與 `FETCH_FAILED` 必須可區分（§7.1）。

        查無資料回傳 `None`（不 raise）；取數失敗 raise（不回 `None`）。
        **把兩者處置成同一件事，就是「失敗被偽裝成沒有資料」。**
        """
        import pandas as pd
        ticker = MagicMock()
        ticker.history.return_value = pd.DataFrame()
        with patch("src.extractors.yfinance_api.yf.Ticker",
                   MagicMock(return_value=ticker)):
            self.assertIsNone(YFinanceAPI().fetch_yfinance_data("NVDA"))


class AutoAdjustIsOurDecisionNotTheirDefault(unittest.TestCase):
    """提案 §0.1b：`auto_adjust` 必須明確傳入。

    **什麼輸入會讓它 FAIL**：回到 `stock.history(period=period)` ——
    那樣 `auto_adjust` 會是第三方的預設值，
    **而 `Ticker.history` 的簽章是 `(self, *args, **kwargs)`，呼叫端讀不出來**。
    """

    def test_auto_adjust_is_passed_explicitly(self):
        import pandas as pd
        ticker = MagicMock()
        ticker.history.return_value = pd.DataFrame({"Close": [1.0]})
        with patch("src.extractors.yfinance_api.yf.Ticker",
                   MagicMock(return_value=ticker)):
            YFinanceAPI().fetch_yfinance_data("NVDA", "1mo")
        _, kwargs = ticker.history.call_args
        self.assertIn("auto_adjust", kwargs,
                      "不明確傳入的話，價格是否已還原權值取決於一個"
                      "我們從未設定、且無版本約束保護的第三方預設值")
        self.assertEqual(kwargs["auto_adjust"], AUTO_ADJUST)


class TheModuleMustNotClaimCompliance(unittest.TestCase):
    """**docstring 必須讓下一個人無法誤讀。**

    這條檢查的是文件而非行為 —— 刻意如此：
    **這條路徑的風險不在它會做錯什麼，而在下一個人以為它已經合規。**
    """

    def test_docstring_states_it_is_not_dec032_compliant(self):
        import src.extractors.yfinance_api as mod
        doc = mod.__doc__ or ""
        self.assertIn("不符合 DEC-032", doc)
        self.assertIn("也不宣稱符合", doc)
        self.assertIn("最保守的行為", doc)
        self.assertNotIn("已合規", doc)


if __name__ == "__main__":
    unittest.main()
