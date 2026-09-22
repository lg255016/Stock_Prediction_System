# -*- coding: utf-8 -*-
"""UG-G2-SB9 階段二·櫃買：TPEx 報表解析的守衛。

**欄名與資料列逐字取自 2026-09-01 實測回應**（`raw_capture`，1011 列），
不是想像的形態。三組守衛：

1. **欄名帶空白與 `<br>`** —— 錨定比對會失敗，而失敗的形式是「找不到欄位」，
   **與「來源不提供該欄位」在輸出上一模一樣**（本 SB 的第五次歸因錯誤）
2. **`pe_ratio` 必須是 NULL，不得是 0**（PO 2026-09-01 條件三）
3. **買賣量必須是 NULL** —— 櫃買欄名逐字為 `(張數)`（`千股` 為推導，非直述），
   而 TWSE 側四個欄名**均不帶單位標註**
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extractors.tpex_market_report import (  # noqa: E402
    SOURCE, normalise_field_name, parse_tpex_report,
)

# 逐字取自實測回應
FIELDS = ['代號', '名稱', '收盤 ', '漲跌', '開盤 ', '最高 ', '最低',
          '成交股數  ', ' 成交金額(元)', ' 成交筆數 ', '最後買價',
          '最後買量<br>(張數)', '最後賣價', '最後賣量<br>(張數)',
          '發行股數 ', '次日漲停價 ', '次日跌停價']

ROW_6488 = ['6488', '環球晶', '935.00', '-58.00', '990.00', '992.00', '930.00',
            '5,732,166', '5,392,564,000', '9,999', '935.00', '10', '936.00',
            '5', '435,000,000', '1,028.00', '842.00']
ROW_ETF = ['00679B', '元大美債20年', '25.84', '持平', '25.90', '25.90', '25.81',
           '14,170,000', '366,159,720', '2,838', '25.84', '95', '25.85', '652',
           '6,243,692,000', '9,999.95', '0.01']
ROW_NO_TRADE = ['1234', '某停牌股', '--', '--', '--', '--', '--',
                '0', '0', '0', '--', '0', '--', '0', '1,000,000', '--', '--']

D = date(2026, 8, 21)


class FieldNameNormalisationTests(unittest.TestCase):
    """欄名帶前後空白與 `<br>` —— **實測形態，不是防禦性寫法**。"""

    def test_padded_and_br_names(self):
        self.assertEqual(normalise_field_name('收盤 '), '收盤')
        self.assertEqual(normalise_field_name('成交股數  '), '成交股數')
        self.assertEqual(normalise_field_name(' 成交金額(元)'), '成交金額(元)')
        self.assertEqual(normalise_field_name('最後買量<br>(張數)'), '最後買量')

    def test_real_fields_all_map(self):
        recs, _ = parse_tpex_report(FIELDS, [ROW_6488], D)
        r = recs[0]
        self.assertEqual(r['stock_id'], '6488')
        self.assertEqual(r['security_name'], '環球晶')
        self.assertAlmostEqual(r['close_price'], 935.0)
        self.assertAlmostEqual(r['open_price'], 990.0)
        self.assertEqual(r['volume'], 5732166)
        self.assertEqual(r['turnover_amount'], 5392564000)
        self.assertEqual(r['transactions'], 9999)

    def test_missing_required_field_raises(self):
        """§7.1：錯誤不得被偽裝成空結果。"""
        bad = [f for f in FIELDS if f.strip() != '收盤']
        with self.assertRaises(ValueError) as ctx:
            parse_tpex_report(bad, [ROW_6488[:2] + ROW_6488[3:]], D)
        self.assertIn('close', str(ctx.exception))


class PeRatioMustBeNullTests(unittest.TestCase):
    """**PO 2026-09-01 條件三：明確禁止填 0。**

    該端點的 17 個欄位裡**沒有本益比**。若填 0，`candidate_prices.pe_ratio`
    同一欄就會有三種語意 —— 真實 P/E、TWSE 的「不適用」sentinel（`0.00`）、
    TPEx 的「來源不提供」—— **而且全部長成同一個數字**。
    """

    def test_pe_ratio_is_none_not_zero(self):
        recs, _ = parse_tpex_report(FIELDS, [ROW_6488, ROW_ETF], D)
        for r in recs:
            self.assertIsNone(r['pe_ratio'], 'TPEx 無本益比欄位，必須是 NULL')
            self.assertNotEqual(r['pe_ratio'], 0, '**明確禁止填 0**')


class BidAskVolumeMustBeNullTests(unittest.TestCase):
    """買賣「量」必須 NULL —— **兩邊單位不一致或未知**。

    櫃買欄名**逐字**為 `最後買量<br>(張數)`（raw capture 中 `張數` 22 處、
    `千股` 0 處）；「單位是千股」是由「1 張 = 1000 股」推得的 `INFERENCE`。
    TWSE 側四個欄名**均不帶單位標註**。

    把兩個單位不同（或其中之一未知）的值寫進同一欄，
    正是本 SB 一路在防的「一欄兩義」。**價格沒有這個問題，故照存。**
    """

    def test_volumes_null_prices_kept(self):
        recs, _ = parse_tpex_report(FIELDS, [ROW_6488], D)
        r = recs[0]
        self.assertIsNone(r['best_bid_volume'])
        self.assertIsNone(r['best_ask_volume'])
        self.assertAlmostEqual(r['best_bid_price'], 935.0, msg='價格單位無歧義，應保留')
        self.assertAlmostEqual(r['best_ask_price'], 936.0)


class CodeShapeAndNoTradeTests(unittest.TestCase):
    """與 TWSE 側同契約：ETF 排除、`--` → NULL 而非 0、零成交量保留為 0。"""

    def test_etf_excluded_and_counted(self):
        recs, s = parse_tpex_report(FIELDS, [ROW_6488, ROW_ETF], D)
        self.assertEqual(s['rows_total'], 2)
        self.assertEqual(s['rows_excluded_by_code_shape'], 1, '00679B 是 ETF')
        self.assertEqual(s['rows_common_stock'], 1)
        self.assertEqual(len(recs), 1)

    def test_no_trade_row_prices_null_volume_zero(self):
        recs, s = parse_tpex_report(FIELDS, [ROW_NO_TRADE], D)
        r = recs[0]
        for k in ('open_price', 'high_price', 'low_price', 'close_price'):
            self.assertIsNone(r[k], '`--` 不是價格')
        self.assertEqual(r['volume'], 0, '零成交是真實觀測，必須保留為 0')
        self.assertEqual(r['turnover_amount'], 0)
        self.assertEqual(s['rows_without_prices'], 1)
        self.assertEqual(s['rows_zero_volume'], 1)
        self.assertEqual(s['rows_no_trade_at_all'], 1)


class SourceTagTests(unittest.TestCase):
    """`source` 指向**哪一份報表**，不是哪個機構（PO 裁示）。"""

    def test_source_value(self):
        recs, _ = parse_tpex_report(FIELDS, [ROW_6488], D)
        self.assertEqual(recs[0]['source'], 'tpex_daily_quotes')
        self.assertEqual(SOURCE, 'tpex_daily_quotes')
        self.assertNotEqual(recs[0]['source'], 'tpex',
                            '不用機構名——日後換報表就分不出來')


if __name__ == '__main__':
    unittest.main()
