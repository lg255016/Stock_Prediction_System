# -*- coding: utf-8 -*-
"""證交所「每日收盤行情(全部)」報表的解析與候選股過濾（UG-G2-SB9）。

**本模組的職責是把一份含全部有價證券的報表，變成 DEC-017 定義的候選股清單，
並忠實記錄每一列的實際狀態——不是預先過濾掉「看起來怪」的列。**

排除「停止交易」是 `UG-G2-SB6` 建構 Universe 時的職責（DEC-017 排除清單），
本模組只負責**讓那個判斷有依據可用**。
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 代號形態過濾（DEC-017：排除 ETF、ETN、權證）
# ---------------------------------------------------------------------------
# **為什麼這是一條有測試的規則，不是解析時順手做掉的一步**：
# 端點回傳的是「每日收盤行情(全部)」。實測 20260821 共 32,751 列——
#   6 碼（權證等）      31,523
#   4 碼、非 0 開頭      1,085   ← 候選股
#   5 碼                  135
#   4 碼、0 開頭（ETF）      8
# 也就是說 **96% 不是候選股**。
#
# B2 判準的「列數 ≥ 500」通過得毫無阻力（32,751 遠超門檻），
# **但門檻擋不住「拿到的不是我要的東西」**——它只確認回應沒被截斷。
# 過濾規則因此必須自己被驗證，而不是依賴上游判準。
#
# 台股普通股代號慣例：4 碼數字，首碼非 0（0 開頭為 ETF／ETN 類）。
_COMMON_STOCK_CODE = re.compile(r"^[1-9]\d{3}$")

# 端點在「當日未成交」時對價格欄回傳的標記（實測形態）。
# `--` 不是價格，**必須成為 NULL，不得成為 0**。
_NO_TRADE_MARKERS = frozenset({"--", "-", "", "X", "x"})

# 全形數字 → 半形（端點回應曾出現全形字元的可能性，B4 判準要求記錄實際形式）
_FULLWIDTH = str.maketrans("０１２３４５６７８９．－", "0123456789.-")


def is_common_stock_code(code) -> bool:
    """是否為台股普通股代號（DEC-017 候選空間）。

    未通過者包含 ETF／ETN（`0` 開頭 4 碼）、權證（6 碼）、
    以及其他非 4 碼形態。**預設排除**——與 `source_capabilities`
    的「未登錄一律視為不提供方向」同一個取捨方向：
    **漏放行的後果是少一檔候選（可被發現），誤放行的後果是
    權證混進流動性排名（安靜地錯）。**
    """
    return bool(_COMMON_STOCK_CODE.match(str(code).strip()))


def parse_number(raw):
    """把報表欄位轉為數值；無法解析時回傳 None（**不回傳 0**）。

    報表數值含千分位，且未成交時為 `--`。
    **`--` → None 而非 0**：0 代表「發生了，值為 0」，
    None 代表「沒有發生過，無值可記」——兩者語意相反
    （`FEATURE_REGISTRY.md` §5A.1）。
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("　", "").replace(" ", "")
    s = s.translate(_FULLWIDTH)
    if s in _NO_TRADE_MARKERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _num_or_none(row, i):
    """索引不存在或值不可解析時回傳 None——**不回傳 0**（同 parse_number 的理由）。"""
    if i is None:
        return None
    return parse_number(row[i])


def _int_or_none(row, i):
    v = _num_or_none(row, i)
    return int(v) if v is not None else None


def parse_market_report(field_names, rows, trade_date, source="twse_mi_index"):
    """把報表列轉為 `candidate_prices` 的寫入記錄。

    Returns:
        (records, stats) —— `records` 為候選股列；`stats` 記錄每一步的
        列數變化，供逐日預期比對（提案 §6.1）。**過濾掉多少必須被看見**，
        不能只回傳結果。
    """
    def idx(*names):
        for n in names:
            if n in field_names:
                return field_names.index(n)
        return None

    i_code = idx("證券代號", "股票代號")
    i_vol = idx("成交股數")
    i_amt = idx("成交金額")
    i_open, i_high = idx("開盤價"), idx("最高價")
    i_low, i_close = idx("最低價"), idx("收盤價")
    i_txn = idx("成交筆數")
    # 排名用不到、但「現在不存就得重抓 800 次」的欄位（PO 2026-08-31 指示）
    i_name = idx("證券名稱")
    i_bidp, i_bidv = idx("最後揭示買價"), idx("最後揭示買量")
    i_askp, i_askv = idx("最後揭示賣價"), idx("最後揭示賣量")
    i_pe = idx("本益比")

    missing = [n for n, i in (("證券代號", i_code), ("成交股數", i_vol),
                              ("成交金額", i_amt), ("開盤價", i_open),
                              ("最高價", i_high), ("最低價", i_low),
                              ("收盤價", i_close)) if i is None]
    if missing:
        raise ValueError("報表缺少必要欄位：%s（實際欄位：%s）" % (missing, field_names))

    records = []
    # 【2026-08-31 修正】原本只有一個 `rows_no_trade`，把兩件事當成同一件。
    # 20260820 實測推翻了那個假設：
    #   1538 正峰：成交股數 451、成交金額 3,922，**但開高低收全是 `--`**
    #   2321 東訊：成交股數 726、成交金額 10,040，同樣無價格
    # 而同日「成交股數 = 0」的普通股是 **0 檔**。
    # 也就是說「無價格」與「零成交」是**獨立的兩件事**——
    # 形態符合變更交易方法／盤後定價交易（有成交但無盤中開高低收）。
    # **兩個計數必須分開**，否則「有成交量卻無價格」這種列會被歸類成
    # 「沒有交易」，而它明明交易了。
    stats = {"rows_total": len(rows), "rows_common_stock": 0,
             "rows_excluded_by_code_shape": 0,
             "rows_without_prices": 0,      # 價格四欄皆 `--`（不論成交量）
             "rows_zero_volume": 0,         # 成交股數 == 0（不論有無價格）
             "rows_no_trade_at_all": 0,     # 兩者同時成立
             "rows_unparseable_volume_or_amount": 0}

    for row in rows:
        code = str(row[i_code]).strip()
        if not is_common_stock_code(code):
            stats["rows_excluded_by_code_shape"] += 1
            continue
        stats["rows_common_stock"] += 1

        vol, amt = parse_number(row[i_vol]), parse_number(row[i_amt])
        if vol is None or amt is None:
            # 成交量／金額無法解析 —— 不猜、不補 0，跳過並計數。
            # 這是必須被看見的事：它代表報表形態與預期不同。
            stats["rows_unparseable_volume_or_amount"] += 1
            continue

        o, h, l, c = (parse_number(row[i_open]), parse_number(row[i_high]),
                      parse_number(row[i_low]), parse_number(row[i_close]))
        no_prices = (o is None and h is None and l is None and c is None)
        zero_vol = (vol == 0)
        if no_prices:
            # 價格四欄皆 `--` → 全部 NULL。**不得填 0**——`--` 不是價格。
            # 注意：**這不等於「沒有交易」**（見 stats 的說明）。
            stats["rows_without_prices"] += 1
        if zero_vol:
            stats["rows_zero_volume"] += 1
        if no_prices and zero_vol:
            stats["rows_no_trade_at_all"] += 1
        records.append({
            "stock_id": code, "trade_date": trade_date,
            "open_price": o, "high_price": h, "low_price": l, "close_price": c,
            "volume": int(vol), "turnover_amount": int(amt),
            "transactions": _int_or_none(row, i_txn),
            "security_name": str(row[i_name]).strip() if i_name is not None else None,
            "best_bid_price": _num_or_none(row, i_bidp),
            "best_bid_volume": _int_or_none(row, i_bidv),
            "best_ask_price": _num_or_none(row, i_askp),
            "best_ask_volume": _int_or_none(row, i_askv),
            # 本益比 `0.00` 是 **sentinel，不是量測值** —— 一律轉 NULL。
            # 本益比 = 股價 / EPS；要讓它「等於 0.00」需要股價為 0（上市股不可能）
            # 或 EPS 大到股價的兩百倍以上（實務上不存在）。
            # 交易所在 EPS ≤ 0 或無法計算時填 `0.00`。
            #
            # **PO 原本推測它只在「無收盤價」時出現，20260820 的資料推翻了那個推測**：
            # 1085 檔普通股中本益比 = 0.00 者 **217 檔，其中 216 檔有收盤價**
            # （例：1101 台泥 收盤 24.8、1304 台聚 收盤 11.8）。
            # 也就是說它**與有無價格無關**，是一個獨立的「不適用」標記。
            # 因此**不做條件式轉換**（只在無價時轉），而是一律轉 NULL。
            #
            # 與本 SB 已處理的另外兩個同型陷阱一致：
            #   `成交金額 '0'` 可解析，訊號在 `開高低收 '--'`
            #   `本益比 '0.00'` 可解析，但它的意思是「算不出來」
            # **一個能被解析的數字，不會有任何解析錯誤，但它不是量測結果。**
            "pe_ratio": (lambda v: None if v == 0.0 else v)(_num_or_none(row, i_pe)),
            "source": source,
        })
    return records, stats
