import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 值域見 FEATURE_REGISTRY.md 第 6 項 CHECK 約束、database/migrations/002_expand_ml_features.sql
REASON_AMBIGUOUS_DUAL_BARRIER = "ambiguous_dual_barrier"
REASON_INSUFFICIENT_DATA = "insufficient_data"
REASON_NO_ENTRY = "no_entry"


def generate_triple_barrier_labels(
    df: pd.DataFrame,
    upper_width: float = 0.02,
    lower_width: float = 0.015,
    holding_period: int = 5,
) -> pd.DataFrame:
    """
    生成 Triple-Barrier 三分類動態標籤（`PURGED_WALK_FORWARD_SPEC.md` §4）。

    Anchor = `Open[T+1]`（同時作為進場成交價與 barrier 計算基準）；
    評估區間 T+1 至 T+holding_period（含 T+1 當日）之 `High`/`Low`。

    Args:
        df: 需含 stock_id, trade_date, open_price, high_price, low_price
            （依個股自身交易日序列，非全域對齊；同 `generate_target_labels()` 既有慣例）。
        upper_width: 上界寬度（預設 2.0%，`PURGED_WALK_FORWARD_SPEC.md` §4.2 Static 模式）
        lower_width: 下界寬度（預設 1.5%，同上）
        holding_period: 持有期交易日數 H（預設 5）

    Returns:
        pd.DataFrame: 附加以下三欄的特徵矩陣（依 stock_id, trade_date 排序）：
            - target_triple_barrier: {-1, 0, 1} 或 NaN
            - label_reason: target_triple_barrier 為 NaN 時的成因
              （'ambiguous_dual_barrier' / 'insufficient_data' / 'no_entry'）；
              正常產生標籤時**缺值為 NaN**（本函式回傳的 `reasons` list 內容為
              `None`，但併入 DataFrame 後型別推斷可能將整欄推為字串型別、
              缺值改以 NaN 表示——實測 pandas 3.0.5 下 dtype 為 `str`、
              缺值為 `float('nan')`，非 `None`。**寫入 DB 前必須用
              `pd.isna()` 判斷、逐列轉為 `None` 再交給 driver**——直接把
              NaN 傳給 TEXT 欄位會被存成文字 `'NaN'`，觸發
              `chk_label_reason_consistency` CHECK 拒絕寫入（已觀測的
              失敗模式，見 `doc/upgrade/gates/evidence/
              UG_G3_SB1_disposable_write_validation.json`）。
              不變式：`pd.isna(label_reason)` ⟺ `target_triple_barrier` 非 NaN。
            - label_end_date_tb: trade_date[T + holding_period]（依個股自身序列）。
              與既有 `label_end_date`（T+1 標籤用）刻意分開為獨立欄位——
              兩者視野不同（H=1 vs H=holding_period），共用一欄會讓
              `WalkForwardSplitter` 的 Purge 邊界依賴到錯誤的標籤視野
              （見 `doc/upgrade/gates/UG_G3_SB1_GATE_A_PROPOSAL.md` §6.1，PO 裁決選項 A）。

    語意裁定（PO 2026-09-09，UG-G3-SB1 Gate A）：資料集末 holding_period 個交易日
    一律 NULL + 'insufficient_data'，**即使剩餘天數內已可觀察到觸線**——不採
    「先觸即定」。理由：後者會讓每檔序列尾端只可能出現 ±1 或 NULL（觸線可觀測、
    到期不可觀測的截斷偏差），字面規則把這個偏差整段消掉，與「算不出來就是
    NULL」的一貫原則同向。
    """
    if df is None or df.empty:
        return df

    df_res = df.sort_values(by=["stock_id", "trade_date"]).reset_index(drop=True)
    n = len(df_res)

    labels = np.full(n, np.nan, dtype=float)
    reasons = [None] * n

    open_arr = df_res["open_price"].astype(float).to_numpy()
    high_arr = df_res["high_price"].astype(float).to_numpy()
    low_arr = df_res["low_price"].astype(float).to_numpy()

    for _stock_id, group in df_res.groupby("stock_id", sort=False):
        idx = group.index.to_numpy()
        m = len(idx)

        for pos in range(m):
            i = idx[pos]
            remaining = m - pos - 1  # 該股票序列中，T 之後尚有幾列

            if remaining == 0:
                # Open[T+1] 不存在（序列末列——停牌／下市等造成無下一筆資料）
                reasons[i] = REASON_NO_ENTRY
                continue

            if remaining < holding_period:
                # 字面規則：末 H 日一律 insufficient_data，不因窗口內已觸線而改判
                # （PO 2026-09-09 語意裁定，見本函式 docstring）
                reasons[i] = REASON_INSUFFICIENT_DATA
                continue

            anchor = open_arr[idx[pos + 1]]
            if np.isnan(anchor):
                # Open[T+1] 存在該列，但值本身缺失（資料品質缺口，如 NULL 價格）——
                # 等同「無法進場」，不得讓 NaN 比較恆為 False 落入迴圈末端被誤判為 0
                # （審查方 2026-09-09 發現：現行真實庫零 NULL，屬潛伏缺陷）。
                reasons[i] = REASON_NO_ENTRY
                continue

            upper = anchor * (1.0 + upper_width)
            lower = anchor * (1.0 - lower_width)

            resolved = False
            for k in range(1, holding_period + 1):
                j = idx[pos + k]
                h, l = high_arr[j], low_arr[j]

                if np.isnan(h) or np.isnan(l):
                    # NaN 檢查必須先於觸線判定：若僅檢查非 NaN 的那一側，NaN 側原本
                    # 可能也會觸線而無法得知，逕行採信另一側等同偽造一個確定結果
                    # （審查方 2026-09-09 發現）。沿用「算不出來就是 NULL」原則，
                    # 不新增 reason 值，不動 migration 002 的 CHECK 域。
                    reasons[i] = REASON_INSUFFICIENT_DATA
                    resolved = True
                    break

                touch_up = h >= upper
                touch_lo = l <= lower

                if touch_up and touch_lo:
                    reasons[i] = REASON_AMBIGUOUS_DUAL_BARRIER
                    resolved = True
                    break
                if touch_up:
                    labels[i] = 1
                    resolved = True
                    break
                if touch_lo:
                    labels[i] = -1
                    resolved = True
                    break

            if not resolved:
                labels[i] = 0  # Timeout：持有期內未觸及任一 barrier

    df_res["target_triple_barrier"] = labels
    df_res["label_reason"] = reasons
    df_res["label_end_date_tb"] = df_res.groupby("stock_id")["trade_date"].shift(-holding_period)

    return df_res


def recompute_tail_labels(df: pd.DataFrame, holding_period: int = 5,
                          tail_window: int = None) -> pd.DataFrame:
    """
    每日尾端重算掛點（`UG-G3-SB2` Gate A 提案 §3.1）的計算層——純函式，不碰
    任何既有表。對每檔股票只回傳尾端 `tail_window` 列（預設 `holding_period + 1`）的
    `generate_triple_barrier_labels()` 重算結果，供 `apply_tail_labels()`
    只 UPDATE 這些列。

    **逐股票處理**：用 `groupby("stock_id").tail(...)`，不是全域
    `df.tail(...)`——面板本身是多股票、日期可能重疊的，全域 tail 在單股票
    測資上不會露出這個錯誤（`UG-G3-SB2` Gate A 送審期間審查方指出）。

    邊界（`holding_period + 1`，不是 `holding_period`）：新增一列後，唯一
    可能從 `insufficient_data` 變為可判定的是「新列加入前 `remaining ==
    holding_period - 1`」的那一列，它在新列加入後排在倒數第
    `holding_period + 1` 位——往前的列即使重跑，窗口內容未變，結果必然相同；
    往後（含新列本身）當然也要重算。

    Args:
        tail_window: 要重算的尾端列數。**與 `holding_period` 是兩個獨立的概念，
            不得共用同一個值**（`FIRST_DAILY_ETL_GAP_AUTOFILL_GATE_A_PROPOSAL.md`
            §3.6）——`holding_period` 決定 Triple-Barrier 本身的持有期窗口（進場後
            最多看幾天），是業務常數，不因為一次追補了幾天新資料就改變；
            `tail_window` 只決定「選取範圍」。預設 `None` 時退化為現行行為
            （`holding_period + 1`），呼叫端不傳這個參數時輸出與修改前逐位相同。
            首次每日 ETL 缺口自動追補案：一次追補 n 個新交易日時，呼叫端傳
            `tail_window=holding_period+n`（`n` 含 `NO_DATA`／`FETCH_FAILED` 的日子），
            `holding_period` 本身不變。
    """
    full = generate_triple_barrier_labels(df, holding_period=holding_period)
    window = tail_window if tail_window is not None else holding_period + 1
    tail_idx = full.groupby("stock_id").tail(window).index
    return full.loc[tail_idx].reset_index(drop=True)


def apply_tail_labels(df_features: pd.DataFrame, df_tail: pd.DataFrame) -> pd.DataFrame:
    """
    每日尾端重算掛點的套用層——把 `recompute_tail_labels()` 的結果套用到既有
    `daily_ml_features` 風格的 DataFrame 上，依 `(stock_id, trade_date)` 只
    更新 `target_triple_barrier`／`label_reason` 兩欄，其餘欄位與其餘列逐位
    元組不變。冪等：對同一份 `df_tail` 套用任意次數，結果相同。

    **合併鍵必須是 `(stock_id, trade_date)`，不能只用 `trade_date`**——多股票
    面板日期本來就會重疊，只用 `trade_date` 當鍵會讓不同股票的值互相覆蓋
    （`UG-G3-SB2` Gate A 送審期間審查方指出）。

    **dtype 陷阱（已觀測，見 tests/test_panel_dataset.py 撰寫階段紀錄）**：
    `label_reason` 欄若在呼叫端全為 NaN，pandas 會把整欄推斷為 `float64`；
    之後對其賦值字串會 `TypeError: Invalid value ... for dtype 'float64'`。
    本函式內部自行轉為 `object` dtype 再賦值，呼叫端不需要先手動轉型。

    **`df_tail` 含有 `df_features` 沒有的 `(stock_id, trade_date)` 組合時
    會 `KeyError`**——刻意不吞掉、不建立新列。與
    `db_writer.update_triple_barrier_tail_labels()` 對「目標列不存在」一律
    視為前提被違反的語意一致（`CLAUDE.md` §7.1「失敗不得偽裝成正常結果」）。
    """
    df_out = df_features.copy()
    if df_out["label_reason"].dtype != object:
        df_out["label_reason"] = df_out["label_reason"].astype(object)

    df_out = df_out.set_index(["stock_id", "trade_date"])
    tail_indexed = df_tail.set_index(["stock_id", "trade_date"])

    df_out.loc[tail_indexed.index, "target_triple_barrier"] = tail_indexed["target_triple_barrier"]
    df_out.loc[tail_indexed.index, "label_reason"] = tail_indexed["label_reason"].astype(object)

    return df_out.reset_index()
