# -*- coding: utf-8 -*-
"""UG-G2-SB9：候選股過濾與零成交列處理（DEC-017、提案 §9）。

**本檔的核心是第 4 項守衛**：停牌／零成交列不得被當成有效的價格觀測。
fixture 用 **20260821 實際觀察到的形態**，不用想像的形態——
`1538 正峰` 的那一列：成交股數 `'0'`、成交金額 `'0'`、開高低收全為 `'--'`。

**那個陷阱的實體是**：`成交金額` 是一個**可以解析的 `'0'`**，
不會有任何解析錯誤；真正的訊號在**價格欄全是 `'--'`**。
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extractors.twse_market_report import (  # noqa: E402
    is_common_stock_code, parse_market_report, parse_number,
)

# 20260821 實際回應的欄位順序（逐字）
FIELDS = ['證券代號', '證券名稱', '成交股數', '成交筆數', '成交金額', '開盤價',
          '最高價', '最低價', '收盤價', '漲跌(+/-)', '漲跌價差', '最後揭示買價',
          '最後揭示買量', '最後揭示賣價', '最後揭示賣量', '本益比']

# 20260821 實際觀察到的零成交列（逐字，未經修改）
ROW_1538_NO_TRADE = ['1538', '正峰', '0', '0', '0', '--', '--', '--', '--',
                     '<p> </p>', '0.00', '8.26', '1', '9.97', '1', '0.00']
# 20260821 實際觀察到的正常列（首列，逐字）
ROW_00400A_ETF = ['00400A', '主動國泰動能高息', '37,141,690', '10,421', '536,788,644',
                  '14.61', '14.61', '14.29', '14.46',
                  '<p style= color:green>-</p>', '0.20', '14.46', '10', '14.47',
                  '423', '0.00']
ROW_2330 = ['2330', '台積電', '16,967,737', '30,000', '40,000,000,000',
            '2365.00', '2375.00', '2350.00', '2375.00', '<p>+</p>', '10.00',
            '2375.00', '100', '2380.00', '50', '25.00']
ROW_WARRANT = ['031234', '某某購01', '0', '0', '0', '--', '--', '--', '--',
               '<p> </p>', '0.00', '--', '0', '--', '0', '0.00']

D = date(2026, 8, 21)


class CodeShapeFilterTests(unittest.TestCase):
    """DEC-017：排除 ETF、ETN、權證。實測 20260821 共 32,751 列中 96% 不是候選股。"""

    def test_common_stock_codes_accepted(self):
        for code in ('2330', '2382', '6488', '1538', '9110'):
            self.assertTrue(is_common_stock_code(code), code)

    def test_etf_and_warrant_codes_rejected(self):
        for code in ('0050', '0056', '00400A', '031234', '00679B', '12345'):
            self.assertFalse(is_common_stock_code(code), code)

    def test_default_is_exclusion(self):
        """未知形態一律排除——與 `source_capabilities` 同一個取捨方向。

        **漏放行的後果是少一檔候選（可被發現）；
        誤放行的後果是權證混進流動性排名（安靜地錯）。**
        """
        for weird in ('', '   ', None, '2330A', '２３３０', 'ABCD'):
            self.assertFalse(is_common_stock_code(weird), repr(weird))


class NumberParsingTests(unittest.TestCase):
    """B4 判準實測到的形態：千分位、`--`。"""

    def test_thousand_separator(self):
        self.assertEqual(parse_number('16,967,737'), 16967737.0)

    def test_no_trade_marker_is_none_not_zero(self):
        """**`--` → None，不是 0。**

        0 代表「發生了，值為 0」；None 代表「沒有發生過，無值可記」
        ——兩者語意相反（`FEATURE_REGISTRY.md` §5A.1）。
        """
        for marker in ('--', '-', '', 'X'):
            self.assertIsNone(parse_number(marker), marker)

    def test_real_zero_stays_zero(self):
        """反向守衛：真實的 `'0'` 必須是 0，不得變成 None。"""
        self.assertEqual(parse_number('0'), 0.0)


class NoTradeRowTests(unittest.TestCase):
    """**本檔最重要的一組**（提案 §9 第 4 項）。"""

    def test_no_trade_row_prices_are_null_not_zero(self):
        """停牌／零成交列的價格必須是 NULL，不得是 0。

        存 0 等於宣稱「當日成交價為 0 元」——
        §5A.1 禁止的「把未知填成已知」。
        """
        recs, _ = parse_market_report(FIELDS, [ROW_1538_NO_TRADE], D)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        for k in ('open_price', 'high_price', 'low_price', 'close_price'):
            self.assertIsNone(r[k], "%s 必須是 NULL：'--' 不是價格" % k)

    def test_no_trade_row_volume_and_amount_are_real_zero(self):
        """互補守衛：成交量與金額的 0 是**真實觀測**，必須保留為 0。

        沒有這一半，把整列都變成 NULL 也會通過上一個測試——
        而那會抹掉「這檔股票當天確實沒有成交」這個事實，
        使 UG-G2-SB6 無從判斷該不該排除它。
        """
        recs, _ = parse_market_report(FIELDS, [ROW_1538_NO_TRADE], D)
        self.assertEqual(recs[0]['volume'], 0)
        self.assertEqual(recs[0]['turnover_amount'], 0)

    def test_no_trade_row_is_counted_and_visible(self):
        """零成交列必須被計數——**過濾掉多少必須被看見**。"""
        recs, stats = parse_market_report(
            FIELDS, [ROW_1538_NO_TRADE, ROW_2330], D)
        self.assertEqual(stats['rows_no_trade_at_all'], 1)
        self.assertEqual(stats['rows_common_stock'], 2)
        self.assertEqual(len(recs), 2, "零成交列仍要寫入——排除是 SB6 的職責，不是本層")

    def test_normal_row_prices_preserved(self):
        recs, _ = parse_market_report(FIELDS, [ROW_2330], D)
        r = recs[0]
        self.assertAlmostEqual(r['close_price'], 2375.0)
        self.assertEqual(r['volume'], 16967737)
        self.assertEqual(r['turnover_amount'], 40000000000)


class ReportStatsTests(unittest.TestCase):
    """逐日預期比對所需的統計（提案 §6.1）。"""

    def test_stats_account_for_every_row(self):
        rows = [ROW_2330, ROW_1538_NO_TRADE, ROW_00400A_ETF, ROW_WARRANT]
        recs, s = parse_market_report(FIELDS, rows, D)
        self.assertEqual(s['rows_total'], 4)
        self.assertEqual(s['rows_excluded_by_code_shape'], 2, "ETF 與權證應被排除")
        self.assertEqual(s['rows_common_stock'], 2)
        self.assertEqual(len(recs), 2)
        # 每一列都要有去處：候選 + 被排除 == 總數
        self.assertEqual(s['rows_common_stock'] + s['rows_excluded_by_code_shape'],
                         s['rows_total'])

    def test_missing_required_field_raises_not_silently_skips(self):
        """欄位缺失必須拋例外，**不得靜默略過**（§7.1：錯誤不得偽裝成空結果）。"""
        bad = [f for f in FIELDS if f != '成交金額']
        with self.assertRaises(ValueError) as ctx:
            parse_market_report(bad, [ROW_2330[:4] + ROW_2330[5:]], D)
        self.assertIn('成交金額', str(ctx.exception))



# 20260820 實際觀察到的形態：**有成交量、有成交金額，但價格四欄全是 `--`**
# （形態符合變更交易方法／盤後定價交易——有成交但無盤中開高低收）
ROW_1538_TRADED_NO_PRICE = ['1538', '正峰', '451', '9', '3,922', '--', '--',
                            '--', '--', '<p> </p>', '0.00', '8.26', '1',
                            '9.20', '1', '0.00']


class TradedWithoutPricesTests(unittest.TestCase):
    """【2026-08-31 新增】「無價格」與「零成交」是獨立的兩件事。

    本提案第一版把兩者當成同一件事（單一個 `rows_no_trade` 計數）。
    **20260820 的真實資料推翻了那個假設**：
    同日「成交股數 = 0」的普通股是 **0 檔**，
    但 `1538 正峰`（451 股／3,922 元）與 `2321 東訊`（726 股／10,040 元）
    **都有成交、都沒有價格**。

    若不分開，這種列會被歸類成「沒有交易」——**而它明明交易了**。
    """

    def test_traded_without_prices_keeps_volume_and_amount(self):
        recs, _ = parse_market_report(FIELDS, [ROW_1538_TRADED_NO_PRICE], D)
        r = recs[0]
        self.assertEqual(r['volume'], 451, "確實有成交，不得歸零")
        self.assertEqual(r['turnover_amount'], 3922)
        self.assertIsNone(r['close_price'], "`--` 不是價格，必須 NULL")

    def test_two_conditions_counted_separately(self):
        """有量無價、有價有量、無量無價——三種形態必須分別計數。"""
        recs, s = parse_market_report(
            FIELDS, [ROW_1538_TRADED_NO_PRICE, ROW_2330, ROW_1538_NO_TRADE], D)
        self.assertEqual(s['rows_without_prices'], 2, "1538 兩列都無價格")
        self.assertEqual(s['rows_zero_volume'], 1, "只有 20260821 那列是零成交")
        self.assertEqual(s['rows_no_trade_at_all'], 1, "兩者同時成立的只有一列")
        self.assertEqual(len(recs), 3)

    def test_no_price_does_not_imply_zero_volume(self):
        """釘住那個被推翻的假設本身，防止有人把兩個計數又合併回去。"""
        _, s = parse_market_report(FIELDS, [ROW_1538_TRADED_NO_PRICE], D)
        self.assertEqual(s['rows_without_prices'], 1)
        self.assertEqual(s['rows_zero_volume'], 0,
                         "有成交量卻無價格——不得被算成零成交")


class PeRatioSentinelTests(unittest.TestCase):
    """`本益比 0.00` 是 sentinel，不是量測值（2026-08-31 實測確認）。

    要讓本益比等於 0.00，需股價為 0（上市股不可能）或 EPS 大到股價的兩百倍以上。
    交易所在 EPS ≤ 0 或無法計算時填 `0.00`。

    **PO 原本推測它只在「無收盤價」時出現，20260820 的資料推翻了那個推測**：
    1085 檔中 `0.00` 者 217 檔，**其中 216 檔有收盤價**。
    故不做條件式轉換，一律轉 NULL。
    """

    def test_zero_pe_becomes_null_even_with_price(self):
        """有收盤價、本益比 0.00 —— 216/217 是這種形態，必須也轉 NULL。"""
        row = ['1101', '台泥', '1,000', '10', '24,800', '24.80', '24.90',
               '24.70', '24.80', '<p>+</p>', '0.10', '24.80', '1', '24.85',
               '1', '0.00']
        recs, _ = parse_market_report(FIELDS, [row], D)
        self.assertIsNotNone(recs[0]['close_price'], "此列有收盤價")
        self.assertIsNone(recs[0]['pe_ratio'],
                          "0.00 是「不適用」的標記，不是量測到的本益比")

    def test_real_pe_preserved(self):
        """反向守衛：真實本益比必須保留，不得被一起清成 NULL。"""
        recs, _ = parse_market_report(FIELDS, [ROW_2330], D)
        self.assertAlmostEqual(recs[0]['pe_ratio'], 25.0)


class SharedTableFinderDefaultPathTests(unittest.TestCase):
    """`_find_market_table(payload)` **不帶參數**時的 TWSE 行為——迴歸守衛。

    **為什麼這條測試必須存在**（2026-09-01，審查者指定為 commit 前條件）：

    `_find_market_table()` 於 2026-09-01 為了供 TPEx 驗證共用而一般化，
    新增了 `field_patterns` 與 `require` 兩個參數，並在比對前加了
    `_normalise_field_name()`。而 `scripts/verify/fetch_candidate_prices.py`
    **以不帶參數的形式呼叫它**——三年回補（766,506 列）完全依賴那條預設路徑。

    「預設行為不變」原本**只隔著推理**。而本專案已有四次紀錄證明
    看起來對的推理會失敗：`fillna(0)` 偽造 polarization、
    標著 ±10% 卻用 11% 的查詢、掃到自己註解的 grep、
    以及把「成功」定義成 C1 層級而讓一個端點被誤判不可用。
    **前三次都跑得完全正常。**

    本測試同時驗證**選表邏輯**：payload 含兩張表，只有一張是報價表。
    """

    QUOTE_TABLE = {
        "title": "每日收盤行情(全部)",
        "fields": FIELDS,
        "data": [ROW_2330, ROW_1538_NO_TRADE, ROW_00400A_ETF],
    }
    # 同一份回應裡的另一張表（指數類），**欄名對映不到 code + close**
    INDEX_TABLE = {
        "title": "大盤統計資訊",
        "fields": ["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)"],
        "data": [["發行量加權股價指數", "24,000.00", "<p>+</p>", "100.00", "0.42"]],
    }

    def _payload(self):
        return {"stat": "OK", "date": "20260821",
                "tables": [self.INDEX_TABLE, self.QUOTE_TABLE]}

    def test_default_call_finds_the_quote_table(self):
        """不帶參數呼叫，必須挑出報價表而不是指數表。"""
        from scripts.verify.twse_market_endpoint_check import _find_market_table
        fields, rows, diag = _find_market_table(self._payload())
        self.assertIsNotNone(fields, "預設參數必須仍找得到 TWSE 報價表：%s" % diag)
        self.assertEqual(fields, FIELDS)
        self.assertEqual(len(rows), 3)
        self.assertEqual(diag["shape"], "tables[1].fields/data",
                         "必須挑中第 2 張表（報價表），不是第 1 張（指數表）")
        self.assertIn("大盤統計資訊", diag["table_titles"])

    def test_default_mapping_covers_code_and_close(self):
        """語意鍵對映必須涵蓋 code 與 close —— `require` 的預設值就是這兩個。"""
        from scripts.verify.twse_market_endpoint_check import _match_fields
        mapping, missing = _match_fields(FIELDS)
        for key in ("code", "close", "open", "high", "low", "volume", "amount"):
            self.assertIn(key, mapping, "語意鍵 %s 對映不到（missing=%s）" % (key, missing))
        self.assertEqual(FIELDS[mapping["code"]], "證券代號")
        self.assertEqual(FIELDS[mapping["close"]], "收盤價")
        self.assertEqual(FIELDS[mapping["amount"]], "成交金額")

    def test_end_to_end_default_path_still_parses(self):
        """把預設路徑接到 `parse_market_report()` —— 三年回補實際走的那條。"""
        from scripts.verify.twse_market_endpoint_check import _find_market_table
        fields, rows, _ = _find_market_table(self._payload())
        recs, stats = parse_market_report(fields, rows, D)
        self.assertEqual(stats["rows_total"], 3)
        self.assertEqual(stats["rows_excluded_by_code_shape"], 1, "00400A 應被排除")
        self.assertEqual(len(recs), 2)
        self.assertAlmostEqual(recs[0]["close_price"], 2375.0)
        self.assertIsNone(recs[1]["close_price"], "1538 零成交列價格仍須為 NULL")


if __name__ == '__main__':
    unittest.main()
