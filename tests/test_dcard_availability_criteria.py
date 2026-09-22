# -*- coding: utf-8 -*-
"""UG-G2-SB5：Dcard 可用性判準邏輯的 known-FAIL 案例（`CLAUDE.md` §9A.2）。

**本檔不對 Dcard 發出任何請求。**

分兩類：

1. **fixture 驅動**（`CriteriaFixtureTests`）——驗證 `evaluate()` 的判定與
   `NOT EXECUTED` 三態傳播。純函數，零網路。
2. **真實路徑驅動**（`AnonymityRealPathTests`）——A2 專用。
   fixture 對 A2 沒有意義：A2 判的是「requests 實際送出了什麼標頭」，
   而那是 `requests` 準備請求時才決定的，手工塞進 fixture 的字典**證明不了**
   正式執行時它擋得住任何東西（第二輪複查指出的阻擋項）。
   因此這一類**真的走一次 `fetch()`**，對象是本機臨時 HTTP server。

> **為什麼 A2 非得這樣測**：第二輪之前，`fetch()` 記錄的是我們**打算**送出的
> 本地字典。A2 判它 → 正式執行下 `auth_like` 恆為空 → **A2 恆等於 A1**，
> 結構上不可能失敗。而 `requests` 2.34.2 的 `Session.prepare_request()` 會呼叫
> `get_netrc_auth()`，在 `~/.netrc`（或 `NETRC` 環境變數指向的檔案）存在時補上
> `Authorization` —— 也就是說「真的送出了認證，卻回報未送出」是可能發生的。
> 本檔的 `test_netrc_credentials_make_a2_fail` 就是讓那件事真的發生一次。
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.verify.dcard_availability_check import (  # noqa: E402
    FAIL,
    INCONCLUSIVE,
    MEASURED,
    NOT_EXECUTED,
    PASS,
    RequestBudget,
    evaluate,
    fetch,
)

try:
    import requests  # noqa: F401
    HAS_REQUESTS = True
except ImportError:  # host 為降級環境（CLAUDE.md §13.3）
    HAS_REQUESTS = False


GOOD_ITEM = {
    "id": 258910234,
    "title": "台積電法說會心得分享",
    "createdAt": "2026-08-28T02:11:45.123Z",
    "likeCount": 42,
    "commentCount": 17,
    "excerpt": "...",
}
KEYWORDS = {
    "taken_at_utc": "2026-08-29T00:00:00+00:00",
    "keywords": [{"keyword": "台積電"}, {"keyword": "聯發科"}],
}


def base_observation():
    """一份「全部正常」的觀察紀錄。各測試由此複製後只破壞一處。"""
    return {
        "keywords": copy.deepcopy(KEYWORDS),
        "listing": {
            "attempted": True,
            "status_code": 200,
            "intended_headers": {"User-Agent": "x", "Accept": "application/json"},
            "sent_headers": {"User-Agent": "x", "Accept": "application/json",
                             "Accept-Encoding": "gzip, deflate", "Connection": "keep-alive"},
            "json_parsed": True,
            "top_level_type": "list",
            "item_count": 30,
            "first_item": copy.deepcopy(GOOD_ITEM),
            "titles": ["台積電法說會心得分享"] + ["今天大盤好可怕"] * 29,
        },
        "post": {"attempted": True, "status_code": 200, "json_parsed": True},
        "comments": {"attempted": True, "status_code": 200, "json_parsed": True},
    }


def _blind_listing(obs):
    """A1／A3 失敗後，後續端點根本不會被請求。"""
    obs["post"] = {"attempted": False}
    obs["comments"] = {"attempted": False}


class CriteriaFixtureTests(unittest.TestCase):
    """每一項判準至少一個會讓它 FAIL 的案例。"""

    def test_control_all_good_passes(self):
        result = evaluate(base_observation())
        self.assertEqual(result["overall"], PASS)
        for key in ("A1", "A2", "A3", "A4", "A5"):
            self.assertEqual(result["criteria"][key]["verdict"], PASS, key)

    def test_a1_fails_on_non_200(self):
        obs = base_observation()
        obs["listing"]["status_code"] = 403
        obs["listing"]["json_parsed"] = False
        obs["listing"]["titles"] = None
        _blind_listing(obs)
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A1"]["verdict"], FAIL)
        self.assertEqual(result["overall"], FAIL)

    def test_a3_fails_on_non_list_top_level(self):
        obs = base_observation()
        obs["listing"]["top_level_type"] = "dict"
        obs["listing"]["first_item"] = None
        obs["listing"]["titles"] = None
        _blind_listing(obs)
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A3"]["verdict"], FAIL)
        self.assertEqual(result["overall"], FAIL)

    def test_a3_fails_on_empty_list(self):
        obs = base_observation()
        obs["listing"]["item_count"] = 0
        obs["listing"]["first_item"] = None
        obs["listing"]["titles"] = []
        _blind_listing(obs)
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A3"]["verdict"], FAIL)
        self.assertEqual(result["overall"], FAIL)

    def test_a4_fails_on_missing_contract_field(self):
        """欄位消失 = 端點還在但契約過期。可修（改欄位映射）。"""
        obs = base_observation()
        obs["listing"]["first_item"].pop("likeCount")
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A4"]["verdict"], FAIL)
        self.assertFalse(result["criteria"]["A4"]["fields"]["likeCount"]["present"])
        self.assertEqual(result["overall"], FAIL)

    def test_a4_fails_on_wrong_type(self):
        obs = base_observation()
        obs["listing"]["first_item"]["commentCount"] = "17"
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A4"]["verdict"], FAIL)

    def test_a4_fails_on_unparseable_created_at(self):
        obs = base_observation()
        obs["listing"]["first_item"]["createdAt"] = "昨天下午"
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A4"]["verdict"], FAIL)

    def test_a5_fails_when_comments_endpoint_gone(self):
        obs = base_observation()
        obs["comments"].update({"status_code": 404, "json_parsed": False})
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A5"]["verdict"], FAIL)
        self.assertEqual(result["overall"], FAIL)


class NotExecutedPropagationTests(unittest.TestCase):
    """§3.2.1：「沒機會跑」不得記成「跑了不通過」，且必須歸因到**根因**。"""

    def test_a1_failure_blocks_everything_and_attributes_to_a1(self):
        obs = base_observation()
        obs["listing"]["status_code"] = 500
        obs["listing"]["json_parsed"] = False
        obs["listing"]["titles"] = None
        _blind_listing(obs)
        crit = evaluate(obs)["criteria"]
        for key in ("A2", "A3", "A4", "A5", "A6"):
            self.assertEqual(crit[key]["verdict"], NOT_EXECUTED, key)
            self.assertEqual(crit[key]["blocked_by"], "A1", "%s 應歸因根因 A1" % key)

    def test_a3_failure_blocks_a4_a5_a6_only(self):
        obs = base_observation()
        obs["listing"]["top_level_type"] = "dict"
        obs["listing"]["first_item"] = None
        obs["listing"]["titles"] = None
        _blind_listing(obs)
        crit = evaluate(obs)["criteria"]
        self.assertEqual(crit["A1"]["verdict"], PASS)
        self.assertEqual(crit["A2"]["verdict"], PASS)
        for key in ("A4", "A5", "A6"):
            self.assertEqual(crit[key]["verdict"], NOT_EXECUTED, key)
            self.assertEqual(crit[key]["blocked_by"], "A3", key)

    def test_a4_failure_does_not_block_a5(self):
        """`id` 仍在，A5 就有得跑——§3.2.1 表格末列。"""
        obs = base_observation()
        obs["listing"]["first_item"].pop("likeCount")
        crit = evaluate(obs)["criteria"]
        self.assertEqual(crit["A4"]["verdict"], FAIL)
        self.assertEqual(crit["A5"]["verdict"], PASS)


class A6MeasurementTests(unittest.TestCase):
    """A6 是量測項：不參與判定，且「沒東西可量」不得偽裝成「量了，是 0」。"""

    def test_a6_reports_hits(self):
        a6 = evaluate(base_observation())["criteria"]["A6"]
        self.assertEqual(a6["verdict"], MEASURED)
        self.assertEqual(a6["matched_articles"], 1)
        self.assertEqual(a6["matched_keywords"], ["台積電"])

    def test_zero_coverage_is_a_valid_measurement(self):
        obs = base_observation()
        obs["listing"]["titles"] = ["今天大盤好可怕"] * 30
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A6"]["matched_articles"], 0)
        self.assertEqual(result["overall"], PASS, "零覆蓋率不得影響 A1-A5 的判定")

    def test_no_titles_is_not_executed_not_zero_coverage(self):
        """空 list → NOT EXECUTED，不是「量了，覆蓋率 0」（第三輪複查指出）。"""
        obs = base_observation()
        obs["listing"]["item_count"] = 0
        obs["listing"]["first_item"] = None
        obs["listing"]["titles"] = []
        _blind_listing(obs)
        a6 = evaluate(obs)["criteria"]["A6"]
        self.assertEqual(a6["verdict"], NOT_EXECUTED)
        self.assertNotIn("matched_articles", a6)

    def test_a6_cannot_rescue_a_failing_overall(self):
        obs = base_observation()
        obs["listing"]["status_code"] = 403
        obs["listing"]["json_parsed"] = False
        _blind_listing(obs)
        self.assertEqual(evaluate(obs)["overall"], FAIL)

    def test_substring_rule_is_disclosed(self):
        """比對規則是子字串，數字型關鍵字會誤命中——證據中必須載明。"""
        obs = base_observation()
        obs["keywords"] = {"keywords": [{"keyword": "2330"}]}
        obs["listing"]["titles"] = ["12330 這檔是什麼", "23300 點大關"]
        a6 = evaluate(obs)["criteria"]["A6"]
        self.assertEqual(a6["matched_articles"], 2, "證實子字串會誤命中")
        self.assertIn("substring", a6["match_rule"])
        self.assertIn("12330", a6["match_rule_caveat"])


class InconclusiveTests(unittest.TestCase):
    """儀器沒產出證據時，整體必須是 INCONCLUSIVE，不是 FAIL。

    **為什麼這件事重要**：提案 §4.1 的整條處置路徑以「整體 FAIL」為觸發條件，
    而那條路徑會把「Dcard 經實測不可用」寫進 RISK-003、契約 §4、Master Plan
    與 PROJECT_STATUS —— 全都是永久治理紀錄。
    我們自己漏記一個 header，不該讓端點背這個紀錄。

    觸發條件是機械的：任一判準 `NOT EXECUTED` 且 `blocked_by is None`。
    目前只有兩個來源，兩個都是我們自己的問題，各有一個測試。
    """

    def test_missing_sent_headers_yields_inconclusive_not_fail(self):
        """觸發來源一：A2 沒拿到實際送出的標頭（腳本漏記）。"""
        obs = base_observation()
        obs["listing"]["sent_headers"] = None
        result = evaluate(obs)
        crit = result["criteria"]
        self.assertEqual(crit["A2"]["verdict"], NOT_EXECUTED)
        self.assertIsNone(crit["A2"]["blocked_by"])
        for key in ("A1", "A3", "A4", "A5"):
            self.assertEqual(crit[key]["verdict"], PASS, "%s 應不受影響" % key)
        self.assertEqual(result["overall"], INCONCLUSIVE)
        self.assertEqual(result["instrument_failures"], ["A2"])

    def test_listing_never_attempted_yields_inconclusive(self):
        """觸發來源二：列表請求根本沒發出（`attempted` 為 False）。"""
        obs = base_observation()
        obs["listing"] = {"attempted": False}
        obs["post"] = {"attempted": False}
        obs["comments"] = {"attempted": False}
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A1"]["verdict"], NOT_EXECUTED)
        self.assertIsNone(result["criteria"]["A1"]["blocked_by"])
        self.assertEqual(result["overall"], INCONCLUSIVE)
        self.assertEqual(result["instrument_failures"], ["A1"])

    def test_genuine_endpoint_failure_still_yields_fail(self):
        """反向守衛：端點自己答錯時，整體必須仍是 FAIL，不得被洗成 INCONCLUSIVE。

        沒有這個測試，「加一個比較溫和的狀態」很容易變成把真實失敗也一起吸收掉。
        """
        obs = base_observation()
        obs["listing"]["status_code"] = 403
        obs["listing"]["json_parsed"] = False
        obs["listing"]["titles"] = None
        _blind_listing(obs)
        result = evaluate(obs)
        self.assertEqual(result["overall"], FAIL)
        self.assertNotIn("instrument_failures", result)

    def test_upstream_blocked_criteria_do_not_trigger_inconclusive(self):
        """被上游擋住的 NOT EXECUTED（`blocked_by` 有值）仍屬端點問題 → FAIL。"""
        obs = base_observation()
        obs["listing"]["top_level_type"] = "dict"
        obs["listing"]["first_item"] = None
        obs["listing"]["titles"] = None
        _blind_listing(obs)
        result = evaluate(obs)
        crit = result["criteria"]
        self.assertEqual(crit["A4"]["verdict"], NOT_EXECUTED)
        self.assertEqual(crit["A4"]["blocked_by"], "A3")
        self.assertEqual(result["overall"], FAIL)

    def test_instrument_failure_wins_over_genuine_failure(self):
        """邊界案例：儀器故障與端點答錯同時發生時，INCONCLUSIVE 勝出。

        這是刻意的方向——儀器壞掉時，端點的答案（不論對錯）都沒有資格被寫進
        永久治理紀錄。原始的逐項 verdict 仍完整保留在證據裡，重跑後會得到乾淨的判定。
        """
        obs = base_observation()
        obs["listing"]["sent_headers"] = None          # 儀器故障
        obs["comments"].update({"status_code": 404, "json_parsed": False})  # 端點答錯
        result = evaluate(obs)
        self.assertEqual(result["criteria"]["A5"]["verdict"], FAIL,
                         "端點的答錯仍必須完整記錄在證據裡")
        self.assertEqual(result["overall"], INCONCLUSIVE)


# ---------------------------------------------------------------------------
# A2：真實路徑驅動。fixture 對 A2 沒有證明力（見本檔 docstring）。
# ---------------------------------------------------------------------------
class _JSONHandler(BaseHTTPRequestHandler):
    """回一份形狀正確的列表回應。不記錄、不對外連線。"""

    payload = [GOOD_ITEM]

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler 的介面)
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # 測試輸出保持乾淨


@unittest.skipUnless(HAS_REQUESTS, "requests 不存在（host 為降級環境，CLAUDE.md §13.3）")
class AnonymityRealPathTests(unittest.TestCase):
    """A2 的 known-FAIL 必須由**真實的 fetch() 呼叫**產生，不是手工 fixture。

    對象是本機臨時 HTTP server——**不對 Dcard 發出任何請求**。
    """

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _JSONHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://localhost:%d/posts" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _observe(self):
        budget = RequestBudget(1, 3)
        record = fetch(self.url, budget, "listing")
        return {"keywords": copy.deepcopy(KEYWORDS), "listing": record,
                "post": {"attempted": False}, "comments": {"attempted": False}}

    def test_clean_environment_yields_a2_pass(self):
        """對照組：環境無憑據時，實際送出的標頭不含認證 → A2 PASS。"""
        obs = self._observe()
        self.assertIsNotNone(obs["listing"]["sent_headers"],
                             "必須記錄實際送出的標頭，否則 A2 無從判定")
        crit = evaluate(obs)["criteria"]
        self.assertEqual(crit["A1"]["verdict"], PASS)
        self.assertEqual(crit["A2"]["verdict"], PASS)

    def test_netrc_credentials_make_a2_fail(self):
        """known-FAIL：`NETRC` 指向含憑據的檔案時，requests 會**自己**補上
        `Authorization`。這是修正前的 A2 完全看不到的那條路徑。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            netrc_path = os.path.join(tmpdir, "netrc")
            with open(netrc_path, "w", encoding="utf-8") as fh:
                fh.write("machine localhost login sb5user password sb5secret\n")
            os.chmod(netrc_path, 0o600)

            previous = os.environ.get("NETRC")
            os.environ["NETRC"] = netrc_path
            try:
                obs = self._observe()
            finally:
                if previous is None:
                    os.environ.pop("NETRC", None)
                else:
                    os.environ["NETRC"] = previous

        sent = obs["listing"]["sent_headers"] or {}
        self.assertIn("Authorization", sent,
                      "requests 應已由 netrc 補上 Authorization；"
                      "若此處失敗，代表本測試的前提已不成立，需重新設計而非放行")
        crit = evaluate(obs)["criteria"]
        self.assertEqual(crit["A1"]["verdict"], PASS, "端點仍可用，失敗的只該是 A2")
        self.assertEqual(crit["A2"]["verdict"], FAIL)
        self.assertIn("Authorization", crit["A2"]["detail"])
        self.assertEqual(evaluate(obs)["overall"], FAIL)

    def test_credential_values_never_reach_the_evidence(self):
        """憑據的**值**不得進入觀察紀錄（第四輪複查指出的預防性缺口）。

        證據檔會進 `evidence/` 並 commit。A2 的 known-FAIL 情境
        （netrc 讓 requests 自己補上 `Authorization`）會產生一個含憑據的標頭——
        若連值一起落檔，commit 後即違反 `CLAUDE.md` §11。

        **標頭名稱必須保留**（A2 靠它判定），只遮值。
        """
        secret = "sb5secret"
        with tempfile.TemporaryDirectory() as tmpdir:
            netrc_path = os.path.join(tmpdir, "netrc")
            with open(netrc_path, "w", encoding="utf-8") as fh:
                fh.write("machine localhost login sb5user password %s\n" % secret)
            os.chmod(netrc_path, 0o600)
            previous = os.environ.get("NETRC")
            os.environ["NETRC"] = netrc_path
            try:
                obs = self._observe()
            finally:
                if previous is None:
                    os.environ.pop("NETRC", None)
                else:
                    os.environ["NETRC"] = previous

        sent = obs["listing"]["sent_headers"]
        self.assertIn("Authorization", sent, "名稱必須保留，否則 A2 會再瞎一次")
        self.assertEqual(sent["Authorization"], "<redacted>")

        # 整份觀察紀錄序列化後，不得出現憑據的任何痕跡。
        serialized = json.dumps(obs, ensure_ascii=False, default=str)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("sb5user", serialized)
        self.assertNotIn("Basic ", serialized, "Base64 憑據字串也不得出現")

        # 遮蔽不得影響判定。
        self.assertEqual(evaluate(obs)["criteria"]["A2"]["verdict"], FAIL)

    def test_intended_headers_alone_cannot_detect_credentials(self):
        """釘住第二輪複查指出的缺陷本身：判「打算送出的字典」偵測不到 netrc。

        這個測試存在的意義是防止有人「順手」把 A2 改回去判 intended_headers。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            netrc_path = os.path.join(tmpdir, "netrc")
            with open(netrc_path, "w", encoding="utf-8") as fh:
                fh.write("machine localhost login sb5user password sb5secret\n")
            os.chmod(netrc_path, 0o600)
            previous = os.environ.get("NETRC")
            os.environ["NETRC"] = netrc_path
            try:
                obs = self._observe()
            finally:
                if previous is None:
                    os.environ.pop("NETRC", None)
                else:
                    os.environ["NETRC"] = previous

        intended = obs["listing"]["intended_headers"]
        sent = obs["listing"]["sent_headers"]
        self.assertNotIn("Authorization", intended,
                         "打算送出的字典裡永遠不會有它——這正是舊 A2 的盲點")
        self.assertIn("Authorization", sent)


if __name__ == "__main__":
    unittest.main()
