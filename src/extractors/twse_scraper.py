import requests
import pandas as pd
import time
import random
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.extractors.retry_policy import is_retriable

class TwseScraper:
    def __init__(self):
        # 加上 headers 偽裝成瀏覽器，降低被阻擋的機率
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    # DEC-032（`APPROVED`）：**403／429 硬停，一次都不重試**；
    # 5xx 與傳輸層失敗才有界重試。`retry=` 條件不可省略——
    # tenacity 未給條件時對**任何**例外重試，而 `raise_for_status()` 對 429
    # 也會拋 `HTTPError`，等於對一個叫我們停的訊號做三次指數退避。
    @retry(retry=retry_if_exception(is_retriable),
           stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=2, min=3, max=10),
           reraise=True)
    def _fetch_json(self, url: str) -> dict:
        """負責執行 HTTP GET 並解析 JSON。

        重試紀律依 DEC-032：傳輸層失敗與 5xx 有界重試；**4xx（含 403／429）硬停**。
        """
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        # 針對證交所，給予較長的隨機延遲 (2 ~ 4 秒)
        time.sleep(random.uniform(2.0, 4.0))
        return response.json()

    def fetch_twse_stock_data(self, stock_id: str, date_str: str) -> pd.DataFrame:
        """從台灣證交所抓取個股日成交資訊"""
        print(f"\n[Extract] 正在向 TWSE 請求 {stock_id} 於 {date_str} 的資料...")
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={stock_id}"
        
        try:
            data = self._fetch_json(url)
            
            if data.get("stat") != "OK":
                print(f"❌ [Extract] 抓取失敗，證交所回傳狀態：{data.get('stat')}")
                return None
                
            columns = data["fields"]
            records = data["data"]
            df = pd.DataFrame(records, columns=columns)
            
            # [Transform 階段]：處理台灣特有的髒資料
            df = df[['日期', '開盤價', '最高價', '最低價', '收盤價', '成交股數']]
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            
            def convert_roc_date(roc_date):
                parts = roc_date.split('/')
                year = int(parts[0]) + 1911
                return f"{year}-{parts[1]}-{parts[2]}"
                
            df['date'] = df['date'].apply(convert_roc_date)
            df['date'] = pd.to_datetime(df['date'])
            
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                df[col] = df[col].astype(str).str.replace(',', '').astype(float)
                
            print("[Extract] TWSE 資料抽取與清洗完成！")
            return df
            
        except Exception as e:
            print(f"❌ [Extract] TWSE 爬蟲執行錯誤: {e}")
            return None
        
if __name__ == '__main__':
    twse_scraper = TwseScraper()
    df = twse_scraper.fetch_twse_stock_data('2330','2026/08/01')
    print(df)