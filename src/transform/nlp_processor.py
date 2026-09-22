import json
import math
import os
import time
import pandas as pd
import jieba
from snownlp import SnowNLP
import google.generativeai as genai
from dotenv import load_dotenv

from src.common.gemini_retry import is_transient_gemini_exception
from src.config import GEMINI_MODEL_NAME

# 載入 .env 檔案中的環境變數
load_dotenv()


class GeminiDailyQuotaExhausted(RuntimeError):
    """§0.5 #31：每日配額已耗盡（quota_id 含 `PerDay`）——重試無意義，
    須等隔天配額重置。與一般 429／分鐘限速分開判斷（見 `is_daily_quota_exhausted`），
    見 GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.2。"""


def is_daily_quota_exhausted(exc: Exception) -> bool:
    """判斷順序上的前提：必須排在一般 `quota` 關鍵字判斷**之前**呼叫——
    每日配額訊息同時含 `"quota"` 與 `"PerDay"`，若順序反過來，一般 `quota`
    判斷會先命中，這個分支永遠執行不到（提案 §3.2 known-FAIL 構造法）。"""
    return "PerDay" in str(exc)


class NLPProcessor:
    def __init__(self):
        # 1. 載入財經字典 (保護關鍵字)
        financial_terms = ["殖利率", "量縮價跌", "量價齊揚", "漲停", "跌停", "均線", "做多", "放空"]
        for term in financial_terms:
            jieba.add_word(term)
            
        # 2. 初始化 Gemini API
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            print("[NLPProcessor] 已成功初始化 Gemini 混合管線 (%s)" % GEMINI_MODEL_NAME)
        else:
            print("[NLPProcessor][WARNING] 找不到 GEMINI_API_KEY，LLM 節點將失效，僅使用 SnowNLP。")

    def _calc_snownlp(self, text: str) -> float:
        """第一關：快速初篩 (免費)"""
        if not text or pd.isna(text):
            return 0.5
        words = jieba.lcut(str(text))
        return round(SnowNLP(" ".join(words)).sentiments, 4)

    @staticmethod
    def _reject_duplicate_json_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Gemini 回應包含重複 ID：{key!r}")
            result[key] = value
        return result

    @staticmethod
    def _expected_response_key_map(expected_ids):
        expected_ids = list(expected_ids)
        if len(set(expected_ids)) != len(expected_ids):
            raise ValueError("LLM candidate IDs 必須唯一。")

        expected_by_json_key = {}
        for expected_id in expected_ids:
            json_key = str(expected_id)
            if json_key in expected_by_json_key:
                raise ValueError("LLM candidate IDs 轉成 JSON key 後發生衝突。")
            expected_by_json_key[json_key] = expected_id
        return expected_by_json_key

    @classmethod
    def _validate_llm_results(cls, expected_ids, raw_results):
        expected_ids = list(expected_ids)
        expected_by_json_key = cls._expected_response_key_map(expected_ids)

        if not isinstance(raw_results, dict):
            raise ValueError("Gemini 回應頂層必須是 JSON object。")

        expected_id_set = set(expected_ids)
        raw_key_set = set(raw_results)
        if raw_key_set == expected_id_set:
            response_key_map = {expected_id: expected_id for expected_id in expected_ids}
        else:
            if not all(isinstance(key, str) for key in raw_results):
                raise ValueError("Gemini 回應 ID 無法對應本次 candidates。")
            if raw_key_set != set(expected_by_json_key):
                raise ValueError("Gemini 回應 ID 集合與本次 candidates 不完全一致。")
            response_key_map = expected_by_json_key

        validated_results = {}
        for response_key, raw_score in raw_results.items():
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise ValueError(f"Gemini 分數不是數值：{response_key!r}")
            score = float(raw_score)
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"Gemini 分數必須是 0.0 到 1.0 的有限數值：{response_key!r}"
                )
            validated_results[response_key_map[response_key]] = score

        return validated_results

    @staticmethod
    def _is_transient_exception(exc: Exception) -> bool:
        """判斷是否為可重試的暫態異常 (如 429 Rate Limit、配額限速、503 伺服器忙碌、網路逾時等)。

        §0.5 #36：委派 `src.common.gemini_retry`，不再各自維護清單——
        原清單含 `deadline`，PO 2026-09-21 裁決 deadline 類錯誤（同一份
        payload 重送不會讓伺服器端 deadline 變短）不列為可重試，已移除，
        見該模組 docstring 與 DEC-045。"""
        return is_transient_gemini_exception(exc)

    def _generate_content_with_retry(self, prompt: str, max_retries: int = 5):
        """
        純 Python 實作之指數退避重試呼叫 (Zero-Dependency Exponential Backoff)。
        遇到 429 限速或暫態網路異常時，自動退避重試 (2s -> 4s -> 8s -> 16s)，最多重試 5 次。
        若為非暫態邏輯錯誤，則立即中斷拋出。
        """
        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                return self.model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.0 # 確保針對相同標題給出穩定一致的分數
                    )
                )
            except Exception as exc:
                # §0.5 #31：每日配額耗盡（quota_id 含 PerDay）必須排在一般
                # quota 判斷之前——訊息同時含兩者，順序反過來這個分支永遠
                # 執行不到（GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.2）。
                # 重試無意義，直接拋出，不進入下方的退避重試。
                if is_daily_quota_exhausted(exc):
                    raise GeminiDailyQuotaExhausted(str(exc)) from exc

                last_exception = exc
                # 若非 429/Quota/網路暫態異常，直接向上拋出 (Fail-Fast)
                if not self._is_transient_exception(exc):
                    raise exc

                if attempt == max_retries:
                    print(f"[Gemini API][ERROR] 遭遇 429 暫態異常且已達最大重試次數 ({max_retries} 次)，終止重試: {exc}")
                    raise exc
                
                # 指數退避延遲計算：min(2 ** attempt, 16) 秒
                sleep_sec = min(2 ** attempt, 16)
                print(f"[Gemini API][WARNING] 遭遇 API 暫態限制或 429 限速 ({exc})，將於 {sleep_sec} 秒後進行第 {attempt + 1}/{max_retries} 次重試...")
                time.sleep(sleep_sec)

        if last_exception:
            raise last_exception

    def _batch_llm_api(self, texts_dict: dict) -> dict:
        """第三關：呼叫 Gemini API 進行批次運算 (支援 429 智慧指數退避重試)"""
        if not texts_dict:
            return {}
        if not self.api_key:
            raise RuntimeError("缺少 GEMINI_API_KEY，無法完成 fuzzy candidates。")

        self._expected_response_key_map(texts_dict)
            
        print(f"[Gemini API] 正在批次處理 {len(texts_dict)} 筆複雜標題 (具備 429 指數退避防護)...")
        
        # 建立嚴格的 System Prompt
        prompt = f"""
        你是一位專業的台灣股市量化分析師。請針對以下財經標題進行情緒評分。
        0.0=極度悲觀 (如跌停、利空、出貨), 1.0=極度樂觀 (如漲停、利多、業績大增), 0.5=中立或無關。
        
        【嚴格要求】：回傳格式必須是 JSON 物件。Keys 為標題對應的 ID (字串)，Values 為情緒分數 (浮點數)。
        
        輸入資料：
        {json.dumps(texts_dict, ensure_ascii=False)}
        """
        
        try:
            response = self._generate_content_with_retry(prompt)
            
            try:
                raw_results = json.loads(
                    response.text,
                    object_pairs_hook=self._reject_duplicate_json_keys,
                )
            except Exception as exc:
                raise ValueError("Gemini 回應不是有效且無重複 ID 的 JSON。") from exc
            return self._validate_llm_results(texts_dict, raw_results)
        finally:
            # 保護機制：Gemini 免費版 API 冷卻保護
            time.sleep(4)

    def process_batch_hybrid(self, df: pd.DataFrame, db_writer) -> pd.DataFrame:
        """
        執行雪球式混合管線的核心方法。
        需要傳入 db_writer 來讓 NLPProcessor 有能力去查快取。
        """
        if df.empty or 'title' not in df.columns:
            return df
            
        # 先在本機結果中完成所有運算與驗證，避免失敗時留下部分 DataFrame 結果。
        snow_scores = df['title'].apply(self._calc_snownlp)
        final_scores = snow_scores.to_dict()
        original_fuzzy_indices = [
            idx
            for idx in df.index
            if 0.4 <= final_scores[idx] <= 0.6
        ]

        if not original_fuzzy_indices:
            df['sentiment_score'] = [final_scores[idx] for idx in df.index]
            return df
            
        # ==========================================
        # 階段二：比對資料庫快取 (Cache Lookup)
        # ==========================================
        fuzzy_titles = list(dict.fromkeys(
            df.at[idx, 'title'] for idx in original_fuzzy_indices
        ))
        cached_scores = db_writer.fetch_cached_scores(fuzzy_titles)
        
        # Cache hit 以 exact-title membership 判定，分數為 0.0 或仍在 fuzzy
        # range 都是有效 hit，且同標題的所有 original-fuzzy rows 都要套用。
        for idx in original_fuzzy_indices:
            title = df.at[idx, 'title']
            if title in cached_scores:
                final_scores[idx] = cached_scores[title]
        
        # ==========================================
        # 階段三：批次呼叫 LLM (只針對 original fuzzy cache misses)
        # ==========================================
        llm_candidate_indices = [
            idx
            for idx in original_fuzzy_indices
            if df.at[idx, 'title'] not in cached_scores
        ]
        
        if llm_candidate_indices:
            llm_input = {
                idx: df.at[idx, 'title']
                for idx in llm_candidate_indices
            }
            if len(llm_input) != len(llm_candidate_indices):
                raise ValueError("LLM candidate IDs 必須唯一。")

            # _batch_llm_api 只會在整份 response 完整驗證後回傳。
            llm_results = self._batch_llm_api(llm_input)

            new_cache_records = [
                (df.at[idx, 'title'], llm_results[idx])
                for idx in llm_candidate_indices
            ]
            for idx in llm_candidate_indices:
                final_scores[idx] = llm_results[idx]

            # 完整驗證後才允許寫 cache；cache write failure 仍向上傳遞。
            db_writer.upsert_sentiment_cache(new_cache_records)

        df['sentiment_score'] = [final_scores[idx] for idx in df.index]
        return df
