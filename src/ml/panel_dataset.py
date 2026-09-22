import pandas as pd


def build_panel_dataset(
    df_universe_snapshots: pd.DataFrame,
    df_daily_ml_features: pd.DataFrame,
    df_stock_prices: pd.DataFrame,
    target_column: str = "target_up_down",
    as_of=None,
    holding_period: int = 5,
) -> pd.DataFrame:
    """
    構建 Point-in-Time 跨股票面板資料集（`UG-G3-SB2` Gate A 提案 §5/§6）。

    Universe 過濾為 PIT，且為**全域**判定：每個 `trade_date`，先在**所有**
    `universe_snapshots.effective_date`（跨全部股票）中取 `<= trade_date` 的
    最大值，作為該 `trade_date` 的「適用期」；該股票必須在**那一期**有列且
    `included=True` 才留在面板。股票若在適用期完全缺席（下市、退出候選池——
    `candidate_prices` 消失後 `universe_snapshots` 就不會再有它的列，是下市股
    的真實長相），視同未入選，**不得沿用該股票自己最後一次出現那期的
    `included=True`**（PO 2026-09-09 複審發現：早期實作以「該股票自己的快照
    列」取最近一期，缺席時會沿用舊期判定，逃過排除）。`trade_date` 早於全域
    最早一期 `effective_date` 時無任何適用期，該列不出現在面板（不默默沿用
    第一期回填）。

    刻意不接受 `df_entity_mapping` 參數——面板股票範圍完全取自
    `universe_snapshots.included`，不受 `entity_mapping` 是否有路由列影響
    （Gate 3 `GATE3_STARTUP_APPLICATION.md` §4.2 裁決）。

    Args:
        df_universe_snapshots: 需含 effective_date, stock_id, included，且
            `(effective_date, stock_id)` 必須唯一（真實表有此 PK，但本函式
            接受任意 DataFrame，不保證來源已符合——重複時 raise `ValueError`，
            不默默去重，PO 2026-09-09 複審要求）。
        df_daily_ml_features: 需含 stock_id, trade_date, target_up_down,
            target_triple_barrier（及其餘既有欄位，原樣保留於輸出）。
        df_stock_prices: 需含 stock_id, trade_date——用於即時計算
            `label_end_date_tb` 與 `label_end_date`（不從 daily_ml_features
            讀，因為兩欄皆未持久化到 DB，Gate A §6.1 選項 A 裁決）。計算式
            與 `triple_barrier.generate_triple_barrier_labels()` 內部相同的
            `groupby("stock_id")["trade_date"].shift(-holding_period)`——
            直接對價格表的 `trade_date` 做位移，不呼叫整個觸線評估迴圈
            （該迴圈是為了算 target，這裡只需要一個日期欄位，PO 2026-09-09
            複審指出兩者混用會讓面板每次構建都多跑一次不必要的迴圈）。
            `label_end_date`（T+1，`UG-G3-SB3` PO 2026-09-12 複核新增）用
            相同機制、`shift(-1)`——**計算基準同樣是 `df_stock_prices`
            （該股票完整、未經 PIT 過濾的真實交易日序列），不是面板自身
            （PIT 過濾後可能因下市／退出候選池而有缺口）的 `trade_date`**：
            若改用面板自身序列位移，會重蹈 RISK-027「用了錯的日曆序列」
            同一種錯誤形狀。兩欄共用同一份 `groupby` 排序物件，各自
            `shift` 一次，不重複掃描價格表。
        target_column: "target_up_down" 或 "target_triple_barrier"，選定的
            目標會複製到輸出的 `target` 欄；兩個原始欄位皆保留於輸出。
        as_of: 面板輸出 `trade_date` 的上界；所用 universe_snapshots 快照
            `effective_date <= as_of`。
        holding_period: 與 `generate_triple_barrier_labels()` 的
            `holding_period` 意義相同，僅用於 `label_end_date_tb` 的位移量。

    Returns:
        pd.DataFrame: long-format 面板，附加 `label_end_date`（T+1，供
            `WalkForwardSplitter(label_end_date_col="label_end_date")`
            用於 `target_up_down`）、`label_end_date_tb`（供
            `WalkForwardSplitter(label_end_date_col="label_end_date_tb")`
            用於 `target_triple_barrier`）與 `target` 三欄，皆為
            `datetime64` dtype（前兩者）或原樣複製（`target`）。
            `label_end_date_tb` 存在但對應 `target_triple_barrier`／
            `label_reason` 為 NULL 的情形是已知、預期的時點落差（每日
            尾端重算掛點尚未對該批資料執行），讀取器不因此拋錯或丟棄該列。
    """
    us = df_universe_snapshots.copy()
    us["effective_date"] = pd.to_datetime(us["effective_date"])
    feat = df_daily_ml_features.copy()
    feat["trade_date"] = pd.to_datetime(feat["trade_date"])

    if as_of is not None:
        as_of_ts = pd.to_datetime(as_of)
        us = us[us["effective_date"] <= as_of_ts]
        feat = feat[feat["trade_date"] <= as_of_ts]

    dup_mask = us.duplicated(subset=["effective_date", "stock_id"], keep=False)
    if dup_mask.any():
        dup_keys = (
            us.loc[dup_mask, ["effective_date", "stock_id"]]
            .drop_duplicates()
            .to_dict("records")
        )
        raise ValueError(
            "df_universe_snapshots 存在重複的 (effective_date, stock_id)，"
            f"面板構建無法唯一判定 included：{dup_keys}"
        )

    if us.empty or feat.empty:
        return feat.assign(label_end_date=pd.NaT, label_end_date_tb=pd.NaT, target=pd.NA).iloc[0:0]

    # 全域適用期：對每一列 feat，取所有快照 effective_date 中 <= trade_date 的
    # 最大值（merge_asof direction="backward"）。早於全域首期者得 NaT，隨後被
    # dropna 排除——這就是「無 PIT 名單可用，不默默回填第一期」。
    global_periods = pd.DataFrame(
        {"effective_date": sorted(us["effective_date"].unique())}
    )
    feat_sorted = feat.sort_values("trade_date").reset_index(drop=True)
    feat_with_period = pd.merge_asof(
        feat_sorted, global_periods,
        left_on="trade_date", right_on="effective_date",
        direction="backward",
    )
    applicable = feat_with_period.dropna(subset=["effective_date"]).copy()

    # 該股票是否在「適用期」有 included=True 的列；完全缺席 → left join 產生
    # NaN → 視為未入選，不沿用該股票自己其他期的舊值。
    merged = applicable.merge(
        us[["effective_date", "stock_id", "included"]],
        on=["effective_date", "stock_id"], how="left",
    )
    merged["included"] = merged["included"].fillna(False).astype(bool)

    panel = merged.loc[merged["included"]].drop(columns=["effective_date", "included"])
    panel = panel.reset_index(drop=True)

    if df_stock_prices is None or df_stock_prices.empty:
        panel["label_end_date"] = pd.NaT
        panel["label_end_date_tb"] = pd.NaT
    else:
        prices = df_stock_prices[["stock_id", "trade_date"]].copy()
        prices["trade_date"] = pd.to_datetime(prices["trade_date"])
        prices = prices.sort_values(["stock_id", "trade_date"])
        grouped_trade_date = prices.groupby("stock_id")["trade_date"]
        prices["label_end_date"] = grouped_trade_date.shift(-1)
        prices["label_end_date_tb"] = grouped_trade_date.shift(-holding_period)
        panel = panel.merge(
            prices[["stock_id", "trade_date", "label_end_date", "label_end_date_tb"]],
            on=["stock_id", "trade_date"], how="left",
        )

    panel["target"] = panel[target_column]

    return panel.reset_index(drop=True)
