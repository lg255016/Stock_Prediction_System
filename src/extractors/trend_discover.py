# src/extractors/trend_discover.py
import json
import os
import time
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

from src.common.gemini_retry import is_transient_gemini_exception
from src.config import GEMINI_MODEL_NAME
from src.transform.nlp_processor import GeminiDailyQuotaExhausted, is_daily_quota_exhausted


class TrendDiscover:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        else:
            print("[TrendDiscover][WARNING] 找不到 API Key，AI 探索模組將無法運作。")
            
        self.base_url = "https://www.ptt.cc"
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.cookies = {"over18": "1"}

    def _fetch_recent_hot_titles(self, pages=3, min_push=20) -> list:
        """爬取 PTT 股板首頁，過濾出推文數大於門檻的熱門文章標題"""
        print(f"[Discover] 正在掃描 PTT 股板最新 {pages} 頁尋找熱門話題...")
        hot_titles = []
        current_url = f"{self.base_url}/bbs/Stock/index.html"
        
        for _ in range(pages):
            try:
                res = requests.get(current_url, headers=self.headers, cookies=self.cookies)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")
                
                entries = soup.find_all("div", class_="r-ent")
                for entry in entries:
                    # 解析推文數
                    push_tag = entry.find("div", class_="nrec").text.strip()
                    push_count = 0
                    if push_tag == '爆': push_count = 100
                    elif push_tag.startswith('X'): push_count = -10
                    elif push_tag.isdigit(): push_count = int(push_tag)
                    
                    # 只抓取熱門文章的標題
                    if push_count >= min_push:
                        title_tag = entry.find("div", class_="title").find("a")
                        if title_tag:
                            # 過濾掉公告性質的文章
                            title = title_tag.text.strip()
                            if "公告" not in title and "盤後" not in title:
                                hot_titles.append(title)
                
                # 找上一頁
                paging_div = soup.find("div", class_="btn-group btn-group-paging")
                prev_page_url = paging_div.find_all("a")[1]["href"]
                current_url = self.base_url + prev_page_url
                time.sleep(1) # 禮貌性延遲
                
            except Exception as e:
                print(f"[Discover][WARNING] 掃描時發生錯誤: {e}")
                return None
                
        return hot_titles

    @staticmethod
    def _is_transient_exception(exc: Exception) -> bool:
        """§0.5 #36：委派 `src.common.gemini_retry`，不再各自維護清單——
        兩處清單曾是真包含關係，deadline 類錯誤的判定結果因此不一致，
        見該模組 docstring。"""
        return is_transient_gemini_exception(exc)

    def _generate_with_retry(self, prompt: str, max_retries: int = 5):
        """具備 429 退避重試的 Gemini 呼叫器"""
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return self.model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )
            except GeminiDailyQuotaExhausted:
                # 已是分類完成的每日配額例外（例如上層測試直接構造）——
                # 不重試，原樣往上拋，由 run_discovery() 接住。
                raise
            except Exception as exc:
                # §0.5 #31：每日配額耗盡必須排在一般 quota 判斷之前，
                # 理由同 nlp_processor.py 的同型改法。
                if is_daily_quota_exhausted(exc):
                    raise GeminiDailyQuotaExhausted(str(exc)) from exc
                last_exc = exc
                if not self._is_transient_exception(exc) or attempt == max_retries:
                    raise exc
                sleep_sec = min(2 ** attempt, 16)
                print(f"[Discover][WARNING] 遭遇 API 暫態限制 ({exc})，將於 {sleep_sec} 秒後重試...")
                time.sleep(sleep_sec)
        if last_exc:
            raise last_exc

    def run_discovery(self, db_writer, max_new_keywords=3):
        """核心邏輯：抓取標題 -> 呼叫 LLM 萃取題材與成分股 -> 寫入資料庫

        §0.5 #31：回傳 `(outcome, detail)` 四態元組，對應
        `doc/upgrade/gates/GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md` §3.1——
        例外（含每日配額耗盡）不跨越本函式邊界，呼叫端不需要再包 try/except。

        | outcome | 情況 |
        |---|---|
        | `"OK"` | 正常寫入至少 1 個關鍵字或映射 |
        | `"NO_DATA"` | 請求成功但無新內容（熱門標題為空；Gemini 回應有效但無可新增的詞） |
        | `"FETCH_FAILED"` | 缺 API key；PTT 掃頁出錯；Gemini 回應無效或萃取失敗 |
        | `"REFUSED"` | 每日配額耗盡（服務主動叫停，非我方抓取失敗） |
        """
        if not self.api_key:
            print("[Discover][WARNING] 缺少 Gemini API Key，本次探索已略過。")
            return "FETCH_FAILED", "GEMINI_API_KEY 未設定"
            
        titles = self._fetch_recent_hot_titles()
        if titles is None:
            print("[Discover][ERROR] PTT 熱門標題擷取失敗，本次探索未寫入資料庫。")
            return "FETCH_FAILED", "PTT 熱門標題擷取失敗（掃頁時發生錯誤）"
        if not titles:
            print("沒有找到足夠的熱門文章標題。")
            return "NO_DATA", None
            
        print(f"[Discover] 收集到 {len(titles)} 篇熱門標題，正在呼叫 Gemini 分析題材趨勢與成分股...")
        
        prompt = f"""
        你是一位敏銳的台灣股市量化分析師。請閱讀以下近期的 PTT 股板熱門標題，並萃取出最多 {max_new_keywords} 個
        「當前市場討論度最高的產業題材/概念詞」（例如：矽光子、散熱模組、CoWoS、AI伺服器），
        並針對每個題材列出 2~4 檔在台股或美股中最具代表性的核心概念成分股代號與名稱。

        【嚴格要求】：
        1. 強制回傳 JSON 格式。
        2. 格式規範如下：
           {{
             "trends": [
               {{
                 "theme": "矽光子",
                 "stocks": [
                   {{"stock_id": "3081", "name": "聯亞", "weight": 1.0}},
                   {{"stock_id": "6442", "name": "光聖", "weight": 1.0}},
                   {{"stock_id": "2330", "name": "台積電", "weight": 0.8}}
                 ]
               }}
             ]
           }}
           
        輸入標題：
        {json.dumps(titles, ensure_ascii=False)}
        """
        
        new_keywords = []
        mapping_records = []
        try:
            response = self._generate_with_retry(prompt)
            result = json.loads(response.text)
            if not isinstance(result, dict):
                raise ValueError("Gemini 回應必須是 JSON object")

            # 1. 優先解析現代 trends 結構 (題材 + 成分股)
            if "trends" in result and isinstance(result["trends"], list):
                for item in result["trends"][:max_new_keywords]:
                    if not isinstance(item, dict):
                        continue
                    theme = item.get("theme", "").strip()
                    if theme and theme not in new_keywords:
                        new_keywords.append(theme)
                        stocks = item.get("stocks", [])
                        if isinstance(stocks, list):
                            for s in stocks:
                                if isinstance(s, dict):
                                    s_id = str(s.get("stock_id", "")).strip()
                                    s_name = str(s.get("name", s_id)).strip()
                                    weight = float(s.get("weight", 1.0))
                                    if s_id:
                                        mapping_records.append((theme, s_id, s_name, weight))

            # 2. 向下相容傳統 keywords 結構
            elif "keywords" in result and isinstance(result["keywords"], list):
                raw_keywords = result.get("keywords")
                if any(not isinstance(k, str) or not k.strip() for k in raw_keywords):
                    raise ValueError("keywords 必須是非空字串陣列")
                new_keywords = list(
                    dict.fromkeys(keyword.strip() for keyword in raw_keywords)
                )[:max_new_keywords]
            else:
                raise ValueError("Gemini 回應缺少 trends 或 keywords 欄位")

        except GeminiDailyQuotaExhausted as exc:
            return "REFUSED", str(exc)[:500]
        except Exception as e:
            print(f"[Discover][ERROR] AI 萃取熱門詞彙失敗: {type(e).__name__}")
            return "FETCH_FAILED", ("%s: %s" % (type(e).__name__, e))[:500]

        if not new_keywords:
            print("[Discover] Gemini 未回傳可新增的熱門詞彙，本次未寫入資料庫。")
            return "NO_DATA", None

        print(f"[Discover] AI 探索完成！本日熱門題材：{new_keywords}")
        if mapping_records:
            print(f"[Discover] 成功辨識 {len(mapping_records)} 筆題材成分股關聯：{mapping_records}")

        # DB write 不在 external-service catch 中；設定寫入失敗必須停止 pipeline。
        db_writer.insert_discovered_keywords(new_keywords)
        if mapping_records:
            db_writer.upsert_theme_stock_mapping(mapping_records)
        return "OK", None
