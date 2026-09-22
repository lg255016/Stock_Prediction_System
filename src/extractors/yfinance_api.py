"""yfinance 取價（**美股專用**，UG-G2-SB7 (iii) 之後）。

================================================================================
⚠⚠ 本模組**不符合 DEC-032**，也不宣稱符合
================================================================================
**這一段必須先讀，否則下一個人會以為這條路徑已經合規。**

DEC-032（`APPROVED`）的判別依據逐字是：

> **判別依據是「有沒有拿到 `status_code`」，不是例外類別名稱**
> ——後者需要窮舉，而窮舉不完的那一項會被靜默歸錯類。

**而 `yfinance` 是函式庫，不是我們控制的 HTTP client。**
`Ticker.history()` 把 HTTP 細節吞掉了 —— **我們拿不到 `status_code`**，
因此**那條判別依據在這裡不適用**。

三條路都不好：

| 選項 | 為何不採 |
|------|---------|
| (i) 全部當傳輸層失敗、有界重試 | 會對 Yahoo 的 429 做退避重試，**仍違反 DEC-032 的精神** |
| (ii) 檢查例外訊息字串來分類 | **那正是 DEC-032 明文拒絕的窮舉法** |
| **(iii) 不重試，失敗一律記 `FETCH_FAILED`** | **採用** |

> **(iii) 不是 DEC-032 的合規實作，是「在無法判別時選擇最保守的行為」。**
>
> **本模組不宣稱符合 DEC-032。** 它宣稱的只有一件事：
> **它不會重試一個可能是 429 的東西。**
>
> 若日後有辦法拿到 `status_code`（例如改用直接的 HTTP 呼叫），
> **那時才談得上合規** —— 在那之前，這裡是一個**已知的、被記錄的缺口**，
> 不是一個已解決的項目。

**適用範圍在 UG-G2-SB7 (iii) 之後縮小了**：上櫃標的改由 `candidate_prices` 供應，
**本模組因此只服務美股標的**（目前為 `NVDA`，且 RISK-021 已排定 Gate 3 啟動前檢視）。

⚠ **(iii) 沒有讓 DEC-032 的問題消失，只是把它縮到一條路徑上。**

================================================================================
`auto_adjust` 明確傳入的理由（提案 §0.1b）
================================================================================
先前這裡是 `stock.history(period=period)` —— **從未明確傳入 `auto_adjust`**。

而 `REMAINING_RISKS.md` 的 RISK-022 面向一宣稱
「yfinance 路徑 `auto_adjust=True` **會**還原，證交所原始價**不會**」。

**該宣稱對 yfinance 1.6.0 是對的，但它對的方式很脆弱**：
`Ticker.history` 的簽章是 `(self, *args, **kwargs)`，**在呼叫端讀不出任何預設值**；
真正的預設藏在 `PriceHistory.history`。而 `requirements.txt` 對該套件**無版本約束**。

> **也就是說：`stock_prices` 的價格是否已還原權值，取決於一個我們從未設定、
> 呼叫端讀不出來、且無版本約束保護的第三方預設值。**
> **那個值若在某次升級後改變，價格基準會靜默翻轉，而沒有任何檢查會發現。**

**明確傳入 `True` 使它成為我們的決定，而不是別人的預設。**
⚠ 這**不是**在解決 RISK-022 —— 該表仍無 `source` 欄、仍無還原基準欄，
**權值基準仍不可知**。這裡做的只是**讓其中一個未知變成已知**。
"""
import pandas as pd
import yfinance as yf

# **與 RISK-022 面向一的宣稱一致**，且刻意寫死而非沿用第三方預設（見模組 docstring）。
AUTO_ADJUST = True


class YFinanceAPI:
    def __init__(self):
        pass

    # ⚠ **刻意沒有 `@retry`**（UG-G2-SB7，2026-09-04）。
    #
    # 先前是 `@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))` **無 `retry=` 條件**，
    # 而下方的 `except` 逐字寫著 `raise e  # 觸發 Tenacity 的重試機制` ——
    # **程式自己記載了它在對任何例外（包含可能的 429）重試三次**，
    # 那是 DEC-032 禁止的行為。
    #
    # **不是改成「只對 5xx 重試」，因為那個判別在這裡做不到**（拿不到 `status_code`）。
    # 失敗一律往上傳，由呼叫端記為 `FETCH_FAILED`。
    def fetch_yfinance_data(self, ticker_symbol: str, period: str = "1mo") -> pd.DataFrame:
        """從 yfinance 抓取股票歷史資料。

        Returns:
            `pd.DataFrame`；**查無資料時回傳 `None`**。

        Raises:
            Exception: 取數失敗 —— **不重試**，由呼叫端記為 `FETCH_FAILED`。

        ⚠ **回傳 `None` 與 raise 是兩件不同的事**：
        前者是「查詢成功但沒有列」（`NO_DATA`），後者是「沒能查成功」（`FETCH_FAILED`）。
        **呼叫端不得把兩者處置成同一件事**（`CLAUDE.md` §7.1）。
        """
        print(f"\n[Extract] 正在透過 yfinance 抓取 {ticker_symbol} 的資料...")
        try:
            stock = yf.Ticker(ticker_symbol)
            df = stock.history(period=period, auto_adjust=AUTO_ADJUST)

            if df.empty:
                print(f"⚠️ [Extract] 警告：{ticker_symbol} 查無資料（NO_DATA，非失敗）。")
                return None

            df = df.reset_index()
            print(f"✅ [Extract] {ticker_symbol} 原始資料抓取成功！")
            return df

        except Exception as e:
            # **不重試**（見上方註解）。往上傳，讓呼叫端記為 FETCH_FAILED——
            # **吞掉它會讓取數失敗長得像「查無資料」**，那正是 §7.1 禁止的。
            print(f"❌ [Extract] 抓取過程中發生錯誤（不重試，將記為 FETCH_FAILED）：{e}")
            raise


if __name__ == '__main__':
    yf_scraper = YFinanceAPI()
    # ⚠ 示範改用美股標的：UG-G2-SB7 (iii) 之後，**上櫃標的不再走本模組**
    #   （原示範為 `6488.TWO`，那正是「本模組服務台股」的證據之一）。
    df = yf_scraper.fetch_yfinance_data('NVDA', '1mo')
    print(df)
