# src/extractors/market_report_table.py
"""全市場報表回應的**表格定位與欄名對映**（TWSE `MI_INDEX` 與 TPEx 皆用同一份）。

================================================================================
本模組是**搬移**過來的，不是新寫的
================================================================================
原本位於 `scripts/verify/twse_market_endpoint_check.py`，
由 `scripts/verify/tpex_endpoint_check.py` 的 `extract_table()` 共用
（`UG-G2-SB9`，2026-09-01 合併為一份）。

`UG-G2-SB7` 需要在**生產路徑**做同一件事。
**若在 `src/` 另寫一份，就是 DEC-032 §Remaining Risks 那句話換一個對象**：

> **同一個規則實作在一支腳本而不在另一支，是本 SB 第六次同型缺陷。**

故採**搬移**：本模組成為唯一實作，驗證腳本改為 import，
**公開名稱不變**（`_match_fields`／`_find_market_table`），其呼叫端一行都不用改。

================================================================================
為何刻意不寫死回應結構
================================================================================
`find_market_table()` 逐一嘗試多種已知形態並回傳診斷。
**找不到表時要能分辨「回應裡沒有表」與「有表但欄名對不上」** ——
兩者在「回傳 None」上長得一樣，而成因完全不同。
生產路徑同樣需要這個區別：**端點改版與端點掛掉不是同一件事。**
"""

import re

FIELD_PATTERNS = {
    "code":   [r"證券代號", r"股票代號", r"代號"],
    "close":  [r"收盤價"],
    "volume": [r"成交股數"],
    "open":   [r"開盤價"],
    "high":   [r"最高價"],
    "low":    [r"最低價"],
    "amount": [r"成交金額"],          # ← B5，本 SB 最重要的判準
}
NUMERIC_FIELDS = ("close", "volume", "open", "high", "low", "amount")


# ---------------------------------------------------------------------------
# 純判定邏輯
# ---------------------------------------------------------------------------
# 【UG-G2-SB7，2026-09-04】TPEx 的欄名與 TWSE 不同，**必須用自己的樣式**。
#
# ⚠ **本區塊是第二次搬移，而第一次只搬了一半。**
#   本模組建立時把 `FIELD_PATTERNS`（TWSE）搬了過來，
#   **卻把 `TPEX_FIELD_PATTERNS` 留在 `scripts/verify/tpex_endpoint_check.py`**。
#   結果：生產路徑用 TWSE 的欄名樣式去對 TPEx 的表，`require=("code","close")`
#   對不上，`find_market_table` 回 None —— 表**找到了**（`tables[0].fields/data`，
#   標題「上櫃股票每日收盤行情(不含定價)」），**只是欄名沒對上**。
#
#   **這是 UG-G2-SB7 STEP 1 抓到的**：對一個答案已知的日子（2026-08-21）執行，
#   TWSE 1085 列相符、TPEx 卻 FETCH_FAILED。
#   **若第一次跑的是「答案未知」的日子，這個缺陷會被讀成端點問題。**
#
#   > 搬一半比不搬更危險：不搬時兩邊各自完整，搬一半時生產端**看起來有**
#   > 那個能力，實際用的是另一個市場的樣式。
TPEX_FIELD_PATTERNS = {
    "code":   [r"證券代號", r"股票代號", r"^代號$", r"SecuritiesCompanyCode", r"^Code$"],
    "close":  [r"收盤價", r"^收盤$", r"^Close$"],
    "volume": [r"成交股數", r"成交量", r"TradingShares"],
    "open":   [r"開盤價", r"^開盤$", r"^Open$"],
    "high":   [r"最高價", r"^最高$", r"^High$"],
    "low":    [r"最低價", r"^最低$", r"^Low$"],
    "amount": [r"成交金額", r"成交值", r"TransactionAmount"],
}


def _normalise_field_name(name):
    """欄名正規化後才比對樣式。

    **這不是防禦性寫法，是實測到的形態**（2026-09-01，TPEx 候選 2 的回應逐字）：

        "代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低",
        "成交股數  ", " 成交金額(元)", "最後買量<br>(張數)"

    欄名帶尾隨空格、前導空格與 `<br>` 標記。錨定樣式（`^收盤$`）對 `"收盤 "`
    **不成立**，而失敗的形式是「找不到表」——
    **與「端點不可用」在輸出上一模一樣**。這是同一個歸因陷阱的第三次現身。
    """
    s = re.sub(r"<br\s*/?>.*", "", str(name), flags=re.IGNORECASE)
    return re.sub(r"[\s　]+", "", s)


def _match_fields(field_names, field_patterns=None):
    """把實際欄名對映到語意鍵；回傳 {語意鍵: 索引} 與未對映到的語意鍵。

    `field_patterns` 於 2026-09-01 一般化（見 `_find_market_table` 的說明）：
    TPEx 的欄名與 TWSE 不同（例如 openapi 用 `SecuritiesCompanyCode`／`Close`），
    **寫死 TWSE 欄名會讓共用變成「找不到表」的歸因錯 FAIL。**
    """
    mapping, missing = {}, []
    for key, pats in (field_patterns or FIELD_PATTERNS).items():
        idx = None
        for i, name in enumerate(field_names or []):
            if any(re.search(p, _normalise_field_name(name)) for p in pats):
                idx = i
                break
        if idx is None:
            missing.append(key)
        else:
            mapping[key] = idx
    return mapping, missing


def _find_market_table(payload, field_patterns=None, require=("code", "close")):
    """從回應中找出全市場報價資料表，並回傳 (field_names, rows, 診斷)。

    **刻意不寫死結構**：找不到時要能說出頂層有哪些 key——
    那是區分「端點還在但格式變了」與「端點消失」的依據（提案 §5.3）。

    **2026-09-01 一般化以供 TPEx 驗證共用**（審查者指出）：
    `tpex_endpoint_check.py` 原本自己重新實作了一個較差的版本
    （不處理 `tables` 這種 list-of-tables、沒有舊版 `fieldsN`/`dataN`、
    沒有選表邏輯），結果把候選端點判成「不可用」，
    **而真正的原因是那份新實作讀不到它**。

    參數化 `field_patterns` 與 `require` 是必要的，不是彈性：
    TPEx 的欄名與 TWSE 不同，**原封不動套用會得到一個「找不到表」的結果，
    而那又是一個歸因錯的 FAIL。**
    """
    diag = {"top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
            "table_titles": [], "shape": None}
    if not isinstance(payload, dict):
        return None, None, diag

    candidates = []
    # 新版格式：tables: [{title, fields, data}, ...]
    for i, tbl in enumerate(payload.get("tables") or []):
        if isinstance(tbl, dict) and tbl.get("fields") and tbl.get("data"):
            diag["table_titles"].append(tbl.get("title"))
            candidates.append((tbl.get("fields"), tbl.get("data"),
                               "tables[%d].fields/data" % i))
    # 舊版格式：fields9 / data9 之類
    for k in sorted(payload.keys()):
        m = re.fullmatch(r"fields(\d+)", str(k))
        if m and ("data" + m.group(1)) in payload:
            diag["table_titles"].append("fields%s/data%s" % (m.group(1), m.group(1)))
            candidates.append((payload[k], payload["data" + m.group(1)],
                               "fields%s/data%s" % (m.group(1), m.group(1))))
    # 單表格式：fields / data（aaData）
    for fk, rk in (("fields", "data"), ("fields", "aaData"), ("Fields", "Data")):
        if isinstance(payload.get(fk), list) and isinstance(payload.get(rk), list) \
                and payload[rk]:
            candidates.append((payload[fk], payload[rk], "%s/%s" % (fk, rk)))

    # 取「欄位能對映到必要語意鍵，且列數最多」的那張表
    best = None
    for fields, data, shape in candidates:
        mapping, _ = _match_fields(fields, field_patterns)
        if all(k in mapping for k in require):
            if best is None or len(data) > len(best[1]):
                best = (fields, data, shape)
    if best is None:
        # **找不到表時，把看過哪些候選表記下來**——否則無從分辨
        # 「回應裡沒有表」與「有表但欄名對不上 require」。
        diag["candidate_shapes"] = [c[2] for c in candidates]
        return None, None, diag
    diag["shape"] = best[2]
    return best[0], best[1], diag
