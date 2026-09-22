# -*- coding: utf-8 -*-
"""UG-G2-SB9 附加步驟：TPEx 判準的 known-FAIL 案例（CLAUDE.md §9A.2）。

**每一項判準都必須出示一個會讓它 FAIL 的具體案例，並實際執行過。**
一個**從未失敗過**的檢查，與一個**永遠不會失敗**的檢查，在輸出上完全無法區分——
兩者都只印 PASS。能區分兩者的唯一方式，是刻意讓它失敗一次。

**本檔全部 fixture 驅動，不發出任何網路請求。**
依 PO 指示，known-FAIL 測試必須在觸網之前先跑過。

三項判準抓的都是「安靜地錯」那一類：
  C2  日期參數根本沒被吃進去 —— 但 HTTP 200、列數夠多，全都會通過
  C5  成交金額單位是千元 —— 數值本身完全「正常」，只是全部差 1000 倍
  C6  代號與 TWSE 碰撞 —— PK 衝突讓 ON CONFLICT DO NOTHING 靜默丟棄整列
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.verify.twse_market_endpoint_check import (  # noqa: E402
    _normalise_field_name,
)
from scripts.verify.tpex_endpoint_check import (  # noqa: E402
    FAIL, INCONCLUSIVE, NOT_EXECUTED, PASS,
    KNOWN_TPEX_STOCK, MIN_ROWS_NOT_A_PAGE,
    evaluate, extract_table, overall, to_roc,
)

FIELDS = ['證券代號', '證券名稱', '開盤價', '最高價', '最低價', '收盤價',
          '成交股數', '成交金額', '本益比']


def row(code, name='某公司', close=100.0, vol=1000, amt=None, pe='15.00'):
    """amt 預設為 close*vol（單位：元），即 C5 比值 = 1.0。"""
    if amt is None:
        amt = close * vol
    return [code, name, str(close), str(close), str(close), str(close),
            str(vol), str(amt), pe]


def make_rows(n, start=1000, **kw):
    """產生 n 檔 4 碼非 0 開頭的普通股列。"""
    return [row(str(start + i), **kw) for i in range(n)]


def obs_ok(rows, fields=FIELDS, digest_a='aaa', digest_b='bbb',
           twse_codes=None, second=True):
    o = {"attempts": [],
         "ok_response": {"endpoint_name": "fixture", "field_names": fields,
                         "rows": rows, "body_digest": digest_a}}
    if second:
        o["second_date_response"] = {"body_digest": digest_b}
    if twse_codes is not None:
        o["twse_codes_same_day"] = twse_codes
    return o


BASE_ROWS = make_rows(MIN_ROWS_NOT_A_PAGE) + [row(KNOWN_TPEX_STOCK, '環球晶', 935.0, 5000)]


class BaselinePassTests(unittest.TestCase):
    """反向守衛：**沒有這一組，所有 known-FAIL 都可能是因為判準永遠 FAIL 而通過。**"""

    def test_clean_fixture_passes_everything(self):
        res = evaluate(obs_ok(BASE_ROWS, twse_codes=['2330', '2382']))
        for k in ('C1', 'C2', 'C3a', 'C3b', 'C4', 'C5', 'C6'):
            self.assertEqual(res[k]['verdict'], PASS,
                             '%s 應 PASS 但得 %s：%s' % (k, res[k]['verdict'],
                                                        res[k]['detail']))
        self.assertEqual(overall(res), PASS)


class C2KnownFailTests(unittest.TestCase):
    """C2：兩個日期的回應內容相同 → 日期參數根本沒被吃進去。

    **這是 TWSE 判準結構上抓不到的盲點**：送錯日期格式時，
    服務可能回空表或別的日期，而 C1（HTTP 200）與 C3a（列數夠多）**都會通過**。
    """

    def test_identical_digests_fail(self):
        res = evaluate(obs_ok(BASE_ROWS, digest_a='same', digest_b='same',
                              twse_codes=[]))
        self.assertEqual(res['C2']['verdict'], FAIL)
        self.assertIn('相同', res['C2']['detail'])
        self.assertEqual(overall(res), FAIL)

    def test_missing_second_response_is_not_executed_not_pass(self):
        """**沒取到第二個日期不等於通過。** 未執行必須與通過可區分。"""
        res = evaluate(obs_ok(BASE_ROWS, twse_codes=[], second=False))
        self.assertEqual(res['C2']['verdict'], NOT_EXECUTED)
        self.assertIsNone(res['C2']['blocked_by'])
        self.assertEqual(overall(res), INCONCLUSIVE,
                         '儀器沒跑起來時必須是 INCONCLUSIVE，不得讀成「可用」')


class C5KnownFailTests(unittest.TestCase):
    """C5：成交金額單位是千元 → 比值落在 ~0.001。

    **錯了整批 DEC-017 流動性排名失效，而數值本身完全「正常」。**
    """

    def test_thousand_yuan_unit_fails(self):
        rows = make_rows(MIN_ROWS_NOT_A_PAGE, close=100.0, vol=1000, amt=100.0)
        rows.append(row(KNOWN_TPEX_STOCK, '環球晶', 935.0, 5000, amt=4675.0))
        res = evaluate(obs_ok(rows, twse_codes=[]))
        self.assertEqual(res['C5']['verdict'], FAIL)
        self.assertIn('千元', res['C5']['detail'])

    def test_sampling_skips_null_price_rows(self):
        """PO 指示 (c)：抽樣必須排除無價格列。

        **沒有這條，抽到 `--` 列會得到一個無意義的結果而不是 FAIL。**
        這裡把前 20 列做成無價格列，若抽樣沒排除它們，C5 會拿不到樣本。
        """
        bad = [[str(2000 + i), '停牌', '--', '--', '--', '--', '0', '0', '0.00']
               for i in range(20)]
        rows = bad + BASE_ROWS
        res = evaluate(obs_ok(rows, twse_codes=[]))
        self.assertEqual(res['C5']['verdict'], PASS,
                         '無價格列應被跳過，不應影響單位判定：%s' % res['C5']['detail'])

    def test_too_few_samples_is_not_executed(self):
        rows = [[str(2000 + i), '停牌', '--', '--', '--', '--', '0', '0', '0.00']
                for i in range(MIN_ROWS_NOT_A_PAGE + 1)]
        res = evaluate(obs_ok(rows, twse_codes=[]))
        self.assertEqual(res['C5']['verdict'], NOT_EXECUTED)
        self.assertIsNone(res['C5']['blocked_by'])


class C6KnownFailTests(unittest.TestCase):
    """C6：代號與同日 TWSE 集合有交集 → PK 碰撞。

    `candidate_prices` 的 PK 是 `(stock_id, trade_date)`，寫入用
    `ON CONFLICT DO NOTHING`。**交集非空代表 TPEx 那列會被靜默丟棄**——
    沒有錯誤訊息、沒有例外、資料表看起來完好。
    """

    def test_overlapping_codes_fail(self):
        rows = BASE_ROWS + [row('2330', '台積電', 2375.0, 1000)]
        res = evaluate(obs_ok(rows, twse_codes=['2330', '2382']))
        self.assertEqual(res['C6']['verdict'], FAIL)
        self.assertIn('2330', res['C6']['detail'])

    def test_missing_twse_set_is_not_executed_not_pass(self):
        res = evaluate(obs_ok(BASE_ROWS))
        self.assertEqual(res['C6']['verdict'], NOT_EXECUTED)
        self.assertEqual(overall(res), INCONCLUSIVE)


class C3KnownFailTests(unittest.TestCase):
    """C3a 只擋分頁碎片；C3b 才擋「拿錯表」。**兩者必須分別會失敗。**"""

    def test_paginated_fragment_fails_c3a(self):
        rows = make_rows(30) + [row(KNOWN_TPEX_STOCK, '環球晶', 935.0, 5000)]
        res = evaluate(obs_ok(rows, twse_codes=[]))
        self.assertEqual(res['C3a']['verdict'], FAIL)
        self.assertEqual(res['C3b']['verdict'], PASS,
                         'C3b 不該因為列數少而失敗——兩者測的是不同的事')

    def test_wrong_table_fails_c3b_even_when_large(self):
        """**列數足夠但拿錯表** —— 這正是 C3a 結構上抓不到的情況。

        TWSE 那次的教訓：B2 的 `>=500` 被 32,751 列輕鬆通過，
        而其中 96% 不是候選股。**門檻擋不住「拿到的不是我要的東西」。**
        """
        rows = make_rows(MIN_ROWS_NOT_A_PAGE + 300)  # 沒有 6488
        res = evaluate(obs_ok(rows, twse_codes=[]))
        self.assertEqual(res['C3a']['verdict'], PASS, '列數足夠，C3a 通過')
        self.assertEqual(res['C3b']['verdict'], FAIL, '但 6488 缺席，C3b 必須擋下')
        self.assertEqual(overall(res), FAIL)


class C4KnownFailTests(unittest.TestCase):
    def test_missing_amount_column_fails(self):
        f = [x for x in FIELDS if x != '成交金額']
        rows = [r[:7] + r[8:] for r in BASE_ROWS]
        res = evaluate(obs_ok(rows, fields=f, twse_codes=[]))
        self.assertEqual(res['C4']['verdict'], FAIL)
        self.assertIn('成交金額', res['C4']['detail'])
        self.assertEqual(res['C5']['verdict'], NOT_EXECUTED)
        self.assertEqual(res['C5']['blocked_by'], 'C4',
                         '被上游判準擋住的未執行，必須與「儀器沒跑起來」可區分')


class C1KnownFailTests(unittest.TestCase):
    def test_no_endpoint_succeeds(self):
        res = evaluate({"attempts": [
            {"endpoint_name": "a", "status_code": 404, "error": "Not Found"},
            {"endpoint_name": "b", "status_code": 403, "error": "Forbidden"},
            {"endpoint_name": "c", "error": "JSONDecodeError"}]})
        self.assertEqual(res['C1']['verdict'], FAIL)
        for k in ('C2', 'C3a', 'C3b', 'C4', 'C5', 'C6'):
            self.assertEqual(res[k]['verdict'], NOT_EXECUTED)
            self.assertEqual(res[k]['blocked_by'], 'C1')
        self.assertEqual(overall(res), FAIL)


class TransportFailureIsNotEndpointFailureTests(unittest.TestCase):
    """**「連不上」與「端點回了東西但不合契約」是兩件事。**

    2026-09-01 第三次嘗試以 `SSLError(CERTIFICATE_VERIFY_FAILED,
    Missing Subject Key Identifier)` 失敗 —— **TLS 交握就沒完成，
    從來沒有觀測到那個端點的回應**，而同一個 URL 稍早成功回過兩次 200。

    把它記成 C1 FAIL，等於宣稱「該端點不合契約」，**而我們根本沒看到它的回應**。
    這是本 SB 第四次同型的歸因錯誤（前三次：候選 2 的解析器、
    欄名尾隨空格、把「成功」定義成 C1 層級）。
    """

    def test_all_transport_failures_is_not_executed(self):
        res = evaluate({"attempts": [
            {"endpoint_name": "a", "error": "SSLError: CERTIFICATE_VERIFY_FAILED",
             "transport_failure": True}]})
        self.assertEqual(res['C1']['verdict'], NOT_EXECUTED,
                         '沒觀測到回應 → 未執行，不是失敗')
        self.assertIsNone(res['C1']['blocked_by'])
        self.assertEqual(overall(res), INCONCLUSIVE,
                         'INCONCLUSIVE 依既有規則不得被讀成「可用」')

    def test_mixed_transport_and_http_failure_stays_fail(self):
        """**反向守衛**：只要有一個嘗試真的拿到了回應，就仍是 FAIL。

        沒有這一半，任何一次連線問題都會把真實的契約失敗洗成「未執行」。
        """
        res = evaluate({"attempts": [
            {"endpoint_name": "a", "error": "SSLError", "transport_failure": True},
            {"endpoint_name": "b", "status_code": 200,
             "error": "找不到表", "transport_failure": False}]})
        self.assertEqual(res['C1']['verdict'], FAIL)
        self.assertEqual(overall(res), FAIL)


class RealPayloadShapeTests(unittest.TestCase):
    """**欄名逐字取自 2026-09-01 實際保存的候選 2 回應**（139,583 bytes）。

    不是想像的形態。欄名帶尾隨空格、前導空格與 `<br>`：
    `"收盤 "`、`"成交股數  "`、`" 成交金額(元)"`、`"最後買量<br>(張數)"`。

    **錨定樣式（`^收盤$`）對 `"收盤 "` 不成立，而失敗的形式是「找不到表」**
    —— 與「端點不可用」在輸出上一模一樣。這條測試釘住那個陷阱。

    ⚠ **界限**：本 fixture 的欄名與資料列逐字為真，但**只有前幾列**
    （保存的是 body 前 4000 字）。它證明欄位對映成立，
    **不證明整份回應可用**——那需要重測，而重測需要預算。
    """

    REAL_FIELDS = ["代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低",
                   "成交股數  ", " 成交金額(元)", " 成交筆數 ", "最後買價",
                   "最後買量<br>(張數)", "最後賣價", "最後賣量<br>(張數)",
                   "發行股數 ", "次日漲停價 ", "次日跌停價"]
    REAL_ROWS = [
        ["00679B", "元大美債20年", "25.84", "持平", "25.90", "25.90", "25.81",
         "14,170,000", "366,159,720", "2,838", "25.84", "95", "25.85", "652",
         "6,243,692,000", "9,999.95", "0.01"],
        ["00687B", "國泰20年美債", "27.19", "-0.24", "27.24", "27.24", "27.14",
         "21,076,000", "572,581,980", "2,225", "27.18", "351", "27.19", "564",
         "4,267,380,380", "9,999.95", "0.01"],
    ]

    def _payload(self):
        return {"tables": [{"title": "上櫃股票每日收盤行情(不含定價)",
                            "date": "115/08/21", "totalCount": 1011,
                            "fields": self.REAL_FIELDS, "data": self.REAL_ROWS}],
                "date": "115/08/21", "stat": "ok", "flagField": None}

    def test_real_field_names_now_map(self):
        f, rows, diag = extract_table(self._payload())
        self.assertIsNotNone(f, "欄名正規化後必須找得到表：%s" % diag)
        self.assertEqual(diag['shape'], 'tables[0].fields/data')
        self.assertEqual(diag['table_titles'], ['上櫃股票每日收盤行情(不含定價)'])
        self.assertEqual(len(rows), 2)

    def test_padded_close_column_is_matched(self):
        """釘住那一個字：`"收盤 "` 帶尾隨空格。"""
        self.assertEqual(_normalise_field_name("收盤 "), "收盤")
        self.assertEqual(_normalise_field_name("成交股數  "), "成交股數")
        self.assertEqual(_normalise_field_name(" 成交金額(元)"), "成交金額(元)")
        # ⚠ **本行對 `(千股)`／`(張數)` 提供零證據** —— 正規化會砍掉 `<br>`
        #   之後的一切，兩者都得到 `最後買量`。能分辨的是
        #   `test_real_fields_match_raw_capture_verbatim`（逐字對照證據檔）。
        self.assertEqual(_normalise_field_name("最後買量<br>(張數)"), "最後買量")

    def test_real_fields_match_raw_capture_verbatim(self):
        """**`REAL_FIELDS` 必須與 `raw_capture` 的 `field_names` 逐字相等。**

        為什麼需要這一條（審查者 2026-09-01 指出）：
        `test_padded_close_column_is_matched` 的 docstring 宣稱「釘住那一個字」，
        **但它結構上做不到** —— `_normalise_field_name` 會砍掉 `<br>` 之後的一切，
        所以 `(千股)` 與 `(張數)` 餵哪一個進去都得到 `最後買量`、都通過。

        > **它不是釘住那一個字，它對那個字提供零證據**，
        > 卻用一句 docstring 宣稱自己釘住了 —— 這就是 §9A.1。

        本條直接對照證據檔本身，**是唯一能分辨兩者的斷言**。
        （已實際製造失敗：修正前 `REAL_FIELDS` 寫 `(千股)`，本條 FAIL；
        而 `raw_capture` 中 `千股` 出現 0 次、`張數` 22 次。）
        """
        import json
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'doc', 'upgrade', 'gates', 'evidence',
                         'G2_SB9_tpex_endpoint_evidence_raw_capture.json')
        with open(p, encoding='utf-8') as fh:
            cap = json.load(fh)
        self.assertEqual(self.REAL_FIELDS, cap['ok_response']['field_names'],
                         '欄名 fixture 與實測證據不符——**它宣稱自己是逐字的**')

    def test_unpadded_names_still_match(self):
        """反向守衛：正規化不得讓原本就乾淨的 TWSE 欄名失配。"""
        for n in ("證券代號", "收盤價", "成交金額", "成交股數"):
            self.assertEqual(_normalise_field_name(n), n)

    def test_evaluate_maps_the_real_field_names(self):
        """**C4 必須對得上實測欄名。**

        2026-09-01 的第四次請求：C1 PASS、C2 PASS，**但 C4 FAIL**，
        理由是 `evaluate()` 用自己的精確比對 `_idx()`：
        `'代號'` 對不上 `'證券代號'`、`'名稱'` 對不上 `'證券名稱'`、
        `' 成交金額(元)'` 對不上 `'成交金額'`。

        **而端點明明八個欄位都有。** 這是本 SB 第五次同型的歸因錯誤，
        且是「同一個檔案裡有兩套欄位對映規則」造成的——
        `extract_table()` 已改用 `_match_fields()`，`evaluate()` 卻沒有。

        **一個模組裡不該有兩套欄位對映規則。**
        """
        rows = [
            ["6488", "環球晶", "935.00", "-58.00", "990.00", "992.00", "930.00",
             "5,732,166", "5,392,564,000", "9,999", "935.00", "10", "936.00",
             "5", "435,000,000", "1,028.00", "842.00"],
        ] + [[str(2000 + i), "某公司", "10.00", "0.00", "10.00", "10.00", "10.00",
              "1,000", "10,000", "5", "10.00", "1", "10.01", "1",
              "1,000,000", "11.00", "9.00"]
             for i in range(MIN_ROWS_NOT_A_PAGE)]
        obs = {"attempts": [],
               "ok_response": {"endpoint_name": "www_afterTrading_otc",
                               "field_names": self.REAL_FIELDS, "rows": rows,
                               "body_digest": "aaa"},
               "second_date_response": {"body_digest": "bbb"},
               "twse_codes_same_day": ["2330", "2382"],
               "twse_codes_date": "2026-08-21",
               "tpex_snapshot_dates": ["115/08/21"]}
        res = evaluate(obs)
        self.assertEqual(res['C4']['verdict'], PASS,
                         'C4 必須對得上實測欄名：%s' % res['C4']['detail'])
        self.assertEqual(res['C3a']['verdict'], PASS)
        self.assertEqual(res['C3b']['verdict'], PASS, '6488 在列中')
        self.assertEqual(res['C5']['verdict'], PASS,
                         '成交金額單位應為元：%s' % res['C5']['detail'])
        self.assertEqual(res['C6']['verdict'], PASS)
        self.assertIn('前提已驗證', res['C6']['detail'],
                      '有了表層日期，C6 的「同日」前提就不再是未驗證')


class RocDateTests(unittest.TestCase):
    """民國年換算：**送錯格式是 C2 要抓的東西，換算本身也要對。**"""

    def test_roc_conversion(self):
        self.assertEqual(to_roc('2026-08-21'), '115/08/21')
        self.assertEqual(to_roc('2023-01-05'), '112/01/05')


class ExtractTableTests(unittest.TestCase):
    """三種候選端點的回應形態不同，取表邏輯要都能處理，且失敗時要說得出原因。"""

    def test_list_of_dict_shape(self):
        f, rows, diag = extract_table([{'Code': '6488', 'Close': '935'}])
        self.assertEqual(f, ['Code', 'Close'])
        self.assertEqual(diag['shape'], 'list_of_dict')

    def test_fields_data_shape(self):
        f, rows, diag = extract_table(
            {'fields': ['代號', '收盤價'], 'data': [['6488', '935.00']]})
        self.assertEqual(diag['shape'], 'fields/data')

    def test_table_with_unmappable_fields_is_rejected_and_says_so(self):
        """**有表、但欄名對不上必要語意鍵** —— 必須拒絕，且要說得出看過哪些候選表。

        沒有 `candidate_shapes`，這種情況與「回應裡根本沒有表」在輸出上一樣，
        而兩者的處置完全不同：前者要改欄位樣式，後者要換端點。
        **這正是候選 2 那次歸因錯誤的一般化形式。**
        """
        f, rows, diag = extract_table(
            {'fields': ['甲', '乙'], 'data': [['1', '2']]})
        self.assertIsNone(f)
        self.assertIsNone(diag['shape'])
        self.assertEqual(diag['candidate_shapes'], ['fields/data'])

    def test_unrecognised_shape_records_keys_not_silently_empty(self):
        """§7.1：錯誤不得被偽裝成空結果。**找不到表時要記下看到了什麼。**

        **這條測試在實戰中救了一次判定**：候選 2 被判 C1 FAIL 時，
        正是靠 `diag.top_level_keys` 記下的 `['date','flagField','stat','tables']`
        才看出「表在 `tables` 底下、解析器讀不到」，而不是端點不可用。
        **一個歸因錯的 FAIL 與一個真的 FAIL，在輸出上長得一樣。**
        """
        f, rows, diag = extract_table({'stat': 'OK', 'message': 'no data'})
        self.assertIsNone(f)
        self.assertIsNone(diag['shape'])
        self.assertEqual(diag['top_level_keys'], ['message', 'stat'])

    def test_list_of_tables_shape(self):
        """`tables` 是 list of tables —— 候選 2 的實際形態。

        ⚠ **本 fixture 依實測到的 `top_level_keys` 推測而來，
        尚未對真實回應驗證**（修補時請求預算已用 3/5）。屬 `ASSUMPTION`。
        """
        payload = {'date': '20260821', 'stat': 'ok', 'flagField': None,
                   'tables': [{'title': '上櫃股票每日收盤行情',
                               'fields': ['代號', '名稱', '收盤'],
                               'data': [['6488', '環球晶', '935.00']]}]}
        f, rows, diag = extract_table(payload)
        self.assertEqual(f, ['代號', '名稱', '收盤'])
        self.assertEqual(rows, [['6488', '環球晶', '935.00']])
        self.assertEqual(diag['shape'], 'tables[0].fields/data')
        self.assertEqual(diag['table_titles'], ['上櫃股票每日收盤行情'])

    def test_list_of_empty_tables_still_not_found(self):
        """反向守衛：`tables` 存在但沒有資料列時，**不得謊報找到表**。"""
        f, rows, diag = extract_table(
            {'date': '20260821', 'tables': [{'fields': ['a'], 'data': []}]})
        self.assertIsNone(f)
        self.assertIsNone(diag['shape'])


if __name__ == '__main__':
    unittest.main()
