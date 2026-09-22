"""
tests/test_gemini_transient_keywords_unify.py — §0.5 #36 統一
`trend_discover.py`／`nlp_processor.py` 的 Gemini 暫態例外判斷清單
（`GEMINI_TRANSIENT_KEYWORDS_UNIFY_GATE_A_PROPOSAL.md` v3，PO 2026-09-21 核准）。

測試範疇（提案 §4，本檔 6 個測試函式）：
- 1：兩處 `_is_transient_exception` 皆委派同一個 `src.common.gemini_retry.
  is_transient_gemini_exception`，不是各自保留清單。
- 2／3：`deadline`／真實 504 訊息在**兩條路徑都判為非暫態**（PO 裁決：deadline
  類錯誤重送不會讓伺服器算得更快，不列為可重試）。紅燈落在 `nlp_processor`
  側（現行清單含 `deadline`），`trend_discover` 側對這兩條測試本來就 PASS。
- 4：`PerDay` 每日配額訊息在兩條路徑都不重試（呼叫次數為 1），
  釘住「`is_daily_quota_exhausted` 必須先於暫態判斷執行」這個硬條件——
  本案不能破壞的既有正確行為，對現行程式碼本來就 PASS，非本案要修的缺陷。
- 5：非暫態例外（`ValueError`）兩條路徑都立即拋出、不重試——同測項 4，
  防回歸鎖定，對現行程式碼本來就 PASS。
- 6：兩個模組的原始碼內不再各自保留字面 `retry_keywords = [...]` 清單。

**紅測預期讀法**：6 條中 4 條對現行程式碼 FAIL（1／2／3／6），2 條（4／5）
本來就 PASS。1 的 FAIL 是 `ImportError`（`src.common.gemini_retry` 尚不存在）；
2／3 的 FAIL 落在 `nlp_processor` 側，`trend_discover` 側本來就 PASS；
6 的 FAIL 是兩個模組都還有字面清單。
"""

import unittest
from unittest.mock import MagicMock, patch

# doc/upgrade/gates/evidence/GEMINI_QUOTA_DISCIPLINE_real_run_20260919_success.md
# 第 129-130 行原文——2026-09-19 第三次真實每日 ETL 探索階段實際撞到的
# DeadlineExceeded／504 訊息，不得自行編寫。
REAL_DEADLINE_504_TEXT = (
    "DeadlineExceeded: 504 Deadline expired before operation could complete."
)

# doc/upgrade/gates/evidence/FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_log.txt
# 第 404-425 行原文——2026-09-17 首次真實每日 ETL NLP 階段實際撞到的
# PerDay 每日配額訊息，不得自行編寫。
REAL_PERDAY_TEXT = (
    "429 You exceeded your current quota, please check your plan and billing "
    "details. For more information on this error, head to: "
    "https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current "
    "usage, head to: https://ai.dev/rate-limit. \n"
    "* Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash\n"
    "Please retry in 53.170503096s. [links {\n"
    "  description: \"Learn more about Gemini API quotas\"\n"
    "  url: \"https://ai.google.dev/gemini-api/docs/rate-limits\"\n"
    "}\n"
    ", violations {\n"
    "  quota_metric: \"generativelanguage.googleapis.com/generate_content_free_tier_requests\"\n"
    "  quota_id: \"GenerateRequestsPerDayPerProjectPerModel-FreeTier\"\n"
    "  quota_dimensions {\n"
    "    key: \"model\"\n"
    "    value: \"gemini-3.8-flash\"\n"
    "  }\n"
    "  quota_dimensions {\n"
    "    key: \"location\"\n"
    "    value: \"global\"\n"
    "  }\n"
    "  quota_value: 20\n"
    "}\n"
    ", retry_delay {\n"
    "  seconds: 53\n"
    "}\n"
    "])"
)


# ============================================================================
# 測項 1：兩處委派同一個共用函式
# ============================================================================
class SharedTransientClassifierTests(unittest.TestCase):
    """§4 測項 1：`trend_discover._is_transient_exception` 與
    `nlp_processor._is_transient_exception` 皆委派同一個
    `src.common.gemini_retry.is_transient_gemini_exception`。

    known-FAIL：`src.common.gemini_retry` 尚不存在 → `ModuleNotFoundError`
    （`ImportError` 子類別）。

    複核第三輪追加的身分比對（`assertIs`）：`call_count==2` 的斷言只證明
    「兩處各自有一個同名可呼叫物件、且被呼叫了」，**不證明那兩個名字指向
    同一個物件**——若 GREEN 之後有人把共用函式複製回兩個模組各自定義
    （清單變數改名躲過測項 6 的字面清單比對），`call_count==2` 與測項 6
    仍會雙雙 PASS，放行「兩份獨立複本」這個 #36 本來要防的回歸。`from X
    import Y` 不影響身分比對——名字綁到同一個物件，`is` 依然成立，只有
    patch 目標的選擇才受這個匯入方式影響。"""

    def test_1_both_modules_delegate_to_shared_function(self):
        from src.common.gemini_retry import is_transient_gemini_exception  # noqa: F401

        from src.extractors.trend_discover import TrendDiscover
        from src.transform.nlp_processor import NLPProcessor

        fake = MagicMock(return_value=True)
        with patch("src.extractors.trend_discover.is_transient_gemini_exception", fake), \
             patch("src.transform.nlp_processor.is_transient_gemini_exception", fake):
            self.assertTrue(TrendDiscover._is_transient_exception(Exception("x")))
            self.assertTrue(NLPProcessor._is_transient_exception(Exception("x")))

        self.assertEqual(
            fake.call_count, 2,
            "兩處各自的 _is_transient_exception 都必須委派同一個共用函式，"
            "不是各自保留一份清單")

        import src.common.gemini_retry as gr
        import src.extractors.trend_discover as td
        import src.transform.nlp_processor as nlp

        self.assertIs(
            td.is_transient_gemini_exception, gr.is_transient_gemini_exception,
            "trend_discover 的 is_transient_gemini_exception 必須是共用模組的"
            "同一個物件，不是各自複製的獨立定義")
        self.assertIs(
            nlp.is_transient_gemini_exception, gr.is_transient_gemini_exception,
            "nlp_processor 的 is_transient_gemini_exception 必須是共用模組的"
            "同一個物件，不是各自複製的獨立定義")


# ============================================================================
# 測項 2／3：deadline／504 兩路徑皆判非暫態
# ============================================================================
class DeadlineNotTransientTests(unittest.TestCase):
    """§4 測項 2／3：PO 裁決 deadline／504 類錯誤不可重試（同一份 payload 重送
    不會讓伺服器端 deadline 變短）。兩條路徑都必須判為非暫態。

    known-FAIL：對現行 `nlp_processor._is_transient_exception`，清單含
    `deadline`，會誤判為 `True` → FAIL。`trend_discover` 側對這兩條測試
    本來就 PASS（現行清單本來就沒有 `deadline`/`504`），僅 NLP 側預期 FAIL。
    """

    def test_2_real_504_message_non_transient_both_paths(self):
        from src.extractors.trend_discover import TrendDiscover
        from src.transform.nlp_processor import NLPProcessor

        self.assertFalse(
            TrendDiscover._is_transient_exception(Exception(REAL_DEADLINE_504_TEXT)),
            "探索側：現行清單本來就沒有 504/deadline，應為 False（此斷言對現行碼預期 PASS）")
        self.assertFalse(
            NLPProcessor._is_transient_exception(Exception(REAL_DEADLINE_504_TEXT)),
            "NLP 側：現行清單含 deadline 會誤判為 True，此斷言對現行碼預期 FAIL")

    def test_3_synthetic_deadline_message_non_transient_both_paths(self):
        msg = "DeadlineExceeded"  # 不含數字 504，隔離變因，只測 deadline 這個詞
        from src.extractors.trend_discover import TrendDiscover
        from src.transform.nlp_processor import NLPProcessor

        self.assertFalse(
            TrendDiscover._is_transient_exception(Exception(msg)),
            "探索側：現行清單本來就沒有 deadline，應為 False（此斷言對現行碼預期 PASS）")
        self.assertFalse(
            NLPProcessor._is_transient_exception(Exception(msg)),
            "NLP 側：現行清單含 deadline 會誤判為 True，此斷言對現行碼預期 FAIL")


# ============================================================================
# 測項 4：PerDay 配額判斷順序（硬條件，防回歸鎖定）
# ============================================================================
class DailyQuotaOrderingRegressionTests(unittest.TestCase):
    """§4 測項 4：兩條路徑都必須先判 `is_daily_quota_exhausted()` 才判
    `_is_transient_exception()`——PerDay 訊息同時含 `quota`，順序反過來會被
    暫態判斷先攔截，重試次數就不會是 1。

    本案不能破壞的既有正確行為，對現行程式碼本來就 PASS，非本案要修的缺陷，
    不計入紅燈。"""

    def test_4_perday_message_raises_once_without_retry_both_paths(self):
        from src.extractors.trend_discover import TrendDiscover
        from src.transform.nlp_processor import GeminiDailyQuotaExhausted, NLPProcessor

        discover = TrendDiscover.__new__(TrendDiscover)
        discover.model = MagicMock()
        discover.model.generate_content.side_effect = Exception(REAL_PERDAY_TEXT)
        with self.assertRaises(GeminiDailyQuotaExhausted):
            discover._generate_with_retry("prompt")
        self.assertEqual(discover.model.generate_content.call_count, 1,
                          "探索側：每日配額耗盡不應重試")

        processor = NLPProcessor.__new__(NLPProcessor)
        processor.model = MagicMock()
        processor.model.generate_content.side_effect = Exception(REAL_PERDAY_TEXT)
        with self.assertRaises(GeminiDailyQuotaExhausted):
            processor._generate_content_with_retry("prompt")
        self.assertEqual(processor.model.generate_content.call_count, 1,
                          "NLP 側：每日配額耗盡不應重試")


# ============================================================================
# 測項 5：非暫態例外立即拋出（防回歸鎖定）
# ============================================================================
class NonTransientFailFastRegressionTests(unittest.TestCase):
    """§4 測項 5：非暫態例外（如邏輯錯誤）兩條路徑都必須立即拋出、不重試。

    本案不能破壞的既有正確行為，對現行程式碼本來就 PASS，非本案要修的缺陷，
    不計入紅燈。"""

    def test_5_non_transient_exception_raises_immediately_both_paths(self):
        from src.extractors.trend_discover import TrendDiscover
        from src.transform.nlp_processor import NLPProcessor

        discover = TrendDiscover.__new__(TrendDiscover)
        discover.model = MagicMock()
        discover.model.generate_content.side_effect = ValueError("bad json")
        with self.assertRaises(ValueError):
            discover._generate_with_retry("prompt")
        self.assertEqual(discover.model.generate_content.call_count, 1,
                          "探索側：非暫態例外不應重試")

        processor = NLPProcessor.__new__(NLPProcessor)
        processor.model = MagicMock()
        processor.model.generate_content.side_effect = ValueError("bad json")
        with self.assertRaises(ValueError):
            processor._generate_content_with_retry("prompt")
        self.assertEqual(processor.model.generate_content.call_count, 1,
                          "NLP 側：非暫態例外不應重試")


# ============================================================================
# 測項 6：原始碼不再各自保留字面清單
# ============================================================================
class NoLiteralKeywordListRemainsTests(unittest.TestCase):
    """§4 測項 6：兩個模組的原始碼內不再各自保留字面
    `retry_keywords = [...]` 清單，皆改為引用共用函式。

    known-FAIL：對現行程式碼，兩處都還有字面清單 → FAIL。"""

    def test_6_no_literal_keyword_list_in_either_module(self):
        import inspect
        from src.extractors import trend_discover as td_module
        from src.transform import nlp_processor as nlp_module

        td_source = inspect.getsource(td_module)
        nlp_source = inspect.getsource(nlp_module)

        self.assertNotIn(
            "retry_keywords = [", td_source,
            "trend_discover.py 不應再保留字面清單，應改為引用共用函式")
        self.assertNotIn(
            "retry_keywords = [", nlp_source,
            "nlp_processor.py 不應再保留字面清單，應改為引用共用函式")


if __name__ == "__main__":
    unittest.main()
