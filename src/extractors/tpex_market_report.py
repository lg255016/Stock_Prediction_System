# -*- coding: utf-8 -*-
"""櫃買中心「上櫃股票每日收盤行情」報表的解析與候選股過濾（UG-G2-SB9 階段二·櫃買）。

**輸出契約與 `twse_market_report.parse_market_report()` 完全相同** ——
同樣的 `records` 欄位、同樣的 `stats` 鍵。差別只在報表形態與欄名。

**刻意共用而非重寫** `parse_number()` 與 `is_common_stock_code()`：
本 SB 已有五次歸因錯誤的成因是「同一個概念有兩個實作」
（`extract_table` vs `_find_market_table`、`_idx` vs `_match_fields`、
以及「成功」在文件與程式中的兩個定義）。**不再製造第六個。**
"""
from __future__ import annotations

import re

from src.extractors.twse_market_report import is_common_stock_code, parse_number

SOURCE = "tpex_daily_quotes"

# 實測欄名（2026-09-01，raw_capture 逐字）：
#   '代號' '名稱' '收盤 ' '漲跌' '開盤 ' '最高 ' '最低' '成交股數  '
#   ' 成交金額(元)' ' 成交筆數 ' '最後買價' '最後買量<br>(張數)'
#   '最後賣價' '最後賣量<br>(張數)' '發行股數 ' '次日漲停價 ' '次日跌停價'
#
# **欄名帶前後空白與 `<br>`**，錨定比對會失敗（GOV-09 那輪的教訓），
# 故一律先正規化再比對。
_FIELD_PATTERNS = {
    "code":   r"^代號$",
    "name":   r"^名稱$",
    "open":   r"^開盤",
    "high":   r"^最高$",
    "low":    r"^最低$",
    "close":  r"^收盤$",
    "volume": r"^成交股數$",
    "amount": r"^成交金額",
    "txn":    r"^成交筆數$",
    "bid":    r"^最後買價$",
    "ask":    r"^最後賣價$",
}


def normalise_field_name(name):
    """去除前後空白（含全形）與 `<br>` 之後的內容。

    與 `twse_market_endpoint_check._normalise_field_name()` 同一規則。
    **這不是防禦性寫法，是實測形態**：`'收盤 '` 帶尾隨空格。
    """
    s = re.sub(r"<br\s*/?>.*", "", str(name), flags=re.IGNORECASE)
    return re.sub(r"[\s　]+", "", s)


def _map_fields(field_names):
    mapping = {}
    for key, pat in _FIELD_PATTERNS.items():
        for i, raw in enumerate(field_names or []):
            if re.search(pat, normalise_field_name(raw)):
                mapping[key] = i
                break
    return mapping


def parse_tpex_report(field_names, rows, trade_date, source=SOURCE):
    """把櫃買報表列轉為 `candidate_prices` 的寫入記錄。

    Returns:
        (records, stats) —— 與 `parse_market_report()` 同契約。

    **本函式刻意不寫入的欄位，以及理由**：

    `pe_ratio` → **一律 `None`**（PO 2026-09-01 條件三，明確禁止填 0）。
      該端點的 17 個欄位裡**沒有本益比**。若填 0，`candidate_prices.pe_ratio`
      同一欄就會有三種語意——真實 P/E、TWSE 的「不適用」sentinel（`0.00`）、
      TPEx 的「來源不提供」——而且**全部長成同一個數字**。
      NULL 與 0 的區分正是 §5A.1 的核心。

    `best_bid_volume` / `best_ask_volume` → **一律 `None`**（見下方 UNIT 說明）。
    """
    m = _map_fields(field_names)
    missing = [k for k in ("code", "open", "high", "low", "close", "volume", "amount")
               if k not in m]
    if missing:
        raise ValueError("報表缺少必要欄位：%s（實際欄位：%s）" % (missing, field_names))

    records = []
    stats = {"rows_total": len(rows), "rows_common_stock": 0,
             "rows_excluded_by_code_shape": 0,
             "rows_without_prices": 0,
             "rows_zero_volume": 0,
             "rows_no_trade_at_all": 0,
             "rows_unparseable_volume_or_amount": 0}

    for row in rows:
        code = str(row[m["code"]]).strip()
        if not is_common_stock_code(code):
            stats["rows_excluded_by_code_shape"] += 1
            continue
        stats["rows_common_stock"] += 1

        vol = parse_number(row[m["volume"]])
        amt = parse_number(row[m["amount"]])
        if vol is None or amt is None:
            stats["rows_unparseable_volume_or_amount"] += 1
            continue

        o, h = parse_number(row[m["open"]]), parse_number(row[m["high"]])
        l, c = parse_number(row[m["low"]]), parse_number(row[m["close"]])
        no_prices = (o is None and h is None and l is None and c is None)
        zero_vol = (vol == 0)
        if no_prices:
            stats["rows_without_prices"] += 1
        if zero_vol:
            stats["rows_zero_volume"] += 1
        if no_prices and zero_vol:
            stats["rows_no_trade_at_all"] += 1

        def _num(key):
            i = m.get(key)
            return parse_number(row[i]) if i is not None else None

        def _int(key):
            v = _num(key)
            return int(v) if v is not None else None

        records.append({
            "stock_id": code, "trade_date": trade_date,
            "open_price": o, "high_price": h, "low_price": l, "close_price": c,
            "volume": int(vol), "turnover_amount": int(amt),
            "transactions": _int("txn"),
            "security_name": (str(row[m["name"]]).strip()
                              if "name" in m else None),
            "best_bid_price": _num("bid"),
            "best_ask_price": _num("ask"),
            # ⚠ UNIT：櫃買買賣量欄名**逐字**為 `最後買量<br>(張數)`
            #   （`G2_SB9_tpex_endpoint_evidence_raw_capture.json` 中 `張數` 22 處、
            #   `千股` **0 處**）。由「普通股 1 張 = 1000 股」推得單位為千股 ——
            #   **這是 `INFERENCE`，不是欄名直述。**
            #
            #   TWSE 側 `最後揭示買量` 四個欄名**均不帶單位標註**
            #   （`G2_SB9_twse_endpoint_evidence.json`），
            #   `005_candidate_prices.sql:100` 亦無單位註解 ——
            #   **「未經驗證」是查得到的事實，不是推託。**
            #
            #   兩邊單位不一致（或其一未知）時寫入同一欄，即「一欄兩義」，
            #   故一律 NULL。**TWSE 側單位查證屬 `UG-G2-SB6`。**
            #
            #   ⚠ 本決定只保護**接下來寫入的列**：`best_bid_volume` 裡
            #   已有三年份單位未經驗證的 TWSE 值（`twse_market_report.py:167`
            #   無換算、無標註）。**NULL 沒有讓既有資料變乾淨**——見 RISK-022。
            "best_bid_volume": None,
            "best_ask_volume": None,
            # PO 2026-09-01 條件三：TPEx 一律 NULL，**明確禁止填 0**。
            "pe_ratio": None,
            "source": source,
        })
    return records, stats
