"""
scripts/generate_tournament_artifact.py

UG-G1-SB3：一次性腳本 —— 對真實歷史資料執行 MLEvaluator.evaluate_tournament()，
把結果寫成 UI 排行榜讀取的 JSON artifact（models/artifacts/tournament_results.json）。

**唯讀保證**：本腳本不包含任何 SQL 字串，資料完全透過
`src/ui/data_loader.py` 既有的 `_fetch_real_stock_features_from_db()`
（SB1／SB2 全程使用、已大量驗證的同一條唯讀路徑，內部僅 `pd.read_sql` + `conn.close()`）
取得。不匯入、不呼叫 `DBWriter` 任何寫入方法，不執行 INSERT／UPDATE／DELETE／DDL。

**執行前置條件**（PO 2026-08-25 裁示，比照但高於 SB1/SB2 隔離臨時 DB 慣例）：
1. 依 CLAUDE.md RISK-013 協定，先以 `DBWriter().db_config` 解析並呈報綁定確認
   （目標 host／port／database），供 PO 過目後才可執行。
2. 本檔完整程式碼須先交審查員複閱，確認全程唯讀後才可執行——這是本次「第一次真正
   碰真實開發 DB」而非臨時 DB，因此比照升一級。

執行方式（容器內，取得上述兩項確認後）：
    MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
      stock_prediction_system2_devcontainer-app-1 python scripts/generate_tournament_artifact.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.ui.data_loader import _fetch_real_stock_features_from_db, DEFAULT_STOCKS, DataSourceError
from src.ml.evaluator import MLEvaluator
from src.ml.time_series_split import WalkForwardSplitter

ARTIFACT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "artifacts", "tournament_results.json"
)

# WalkForwardSplitter 建構參數：四項皆沿用其類別 __init__ 預設值
# （train_window_size=60, test_window_size=20, label_horizon=1, embargo_days=0），
# 與 SB1 驗證時使用的設定一致，未額外調整。
TRAIN_WINDOW_SIZE = 60
TEST_WINDOW_SIZE = 20
LABEL_HORIZON = 1
EMBARGO_DAYS = 0


def fetch_full_panel() -> pd.DataFrame:
    """
    唯讀取得全部預設股票（DEFAULT_STOCKS）的完整歷史特徵矩陣並合併為單一 Panel。

    僅呼叫既有唯讀函式 `_fetch_real_stock_features_from_db()`（傳入極大 days 值以取得
    全部歷史，不做任何截斷），不包含任何新的 SQL。
    """
    frames = []
    for stock_id in DEFAULT_STOCKS:
        try:
            df = _fetch_real_stock_features_from_db(stock_id, days=99999)
        except DataSourceError as e:
            print(f"[WARN] {stock_id} 讀取失敗，略過：{e}")
            continue
        if df is None or df.empty:
            print(f"[WARN] {stock_id} 無可用資料，略過")
            continue
        frames.append(df)

    if not frames:
        raise RuntimeError("所有預設股票（DEFAULT_STOCKS）皆無可用歷史資料，無法建立 Panel。")

    panel = pd.concat(frames, ignore_index=True)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel.sort_values(["trade_date", "stock_id"]).reset_index(drop=True)
    return panel


def _to_native(value):
    """numpy 純量轉為原生 Python 型別，確保 json.dump 不因 numpy 型別拋錯。"""
    return value.item() if hasattr(value, "item") else value


def check_sufficient_data(unique_dates: int, train_window_size: int, test_window_size: int) -> None:
    """
    資料量防線（PO 2026-08-26 裁示）：執行前明確檢查唯一交易日數是否足夠產生至少一個 Fold。

    **為什麼不能只靠「leaderboard 是否為空」判斷**：`MLEvaluator.evaluate_tournament()`
    對 `splitter.split(df)` 產生零個 Fold 的情況並不會回傳空 DataFrame——`compute_financial_
    strategy_metrics([], [])` 在輸入為空時回傳一組全為 0 的合法指標字典，`evaluate_tournament()`
    仍會照常為 4 個演算法 × 2 個特徵集組出 8 列。也就是說零 Fold 產生的是一份**滿版但全部
    是零分的排行榜**，不是空排行榜——舊版本只檢查「leaderboard 是否為空」完全攔不住這個情況，
    會讓一份看起來正常、實際上什麼都沒訓練過的 artifact 被寫出去。

    本檢查在呼叫 evaluate_tournament() 之前，直接針對「資料量是否足夠」這個真正的前提條件
    把關，不依賴下游計算結果的形狀去反推。

    Raises:
        RuntimeError: 唯一交易日數不足以支撐至少一個 train_window_size + test_window_size 的 Fold。
    """
    required = train_window_size + test_window_size
    if unique_dates < required:
        raise RuntimeError(
            f"資料量不足，需要至少 {required} 天（train_window_size={train_window_size} + "
            f"test_window_size={test_window_size}），目前只有 {unique_dates} 天。"
            "拒絕執行模型競技評估，不寫出 artifact。"
        )


def main() -> None:
    print("=== UG-G1-SB3 模型競技 Artifact 產生腳本 ===")

    panel = fetch_full_panel()
    unique_dates = panel["trade_date"].nunique()
    print(
        f"Panel 大小：{len(panel)} 列，股票：{sorted(panel['stock_id'].unique().tolist())}，"
        f"唯一交易日數：{unique_dates}，"
        f"日期範圍：{panel['trade_date'].min().date()} ~ {panel['trade_date'].max().date()}"
    )

    check_sufficient_data(unique_dates, TRAIN_WINDOW_SIZE, TEST_WINDOW_SIZE)

    splitter = WalkForwardSplitter(
        train_window_size=TRAIN_WINDOW_SIZE,
        test_window_size=TEST_WINDOW_SIZE,
        mode="rolling",
        label_horizon=LABEL_HORIZON,
        embargo_days=EMBARGO_DAYS,
    )

    evaluator = MLEvaluator(random_state=42)
    result = evaluator.evaluate_tournament(panel, splitter)

    leaderboard_df = result["leaderboard"]
    if leaderboard_df is None or leaderboard_df.empty:
        raise RuntimeError(
            "evaluate_tournament 回傳空排行榜——可能是可用資料不足以產生任何 Fold。"
            "本腳本拒絕寫出空 artifact，請先確認 Panel 資料量是否足夠（見上方 Panel 大小輸出）。"
        )

    leaderboard_records = [
        {k: _to_native(v) for k, v in row.items()}
        for row in leaderboard_df.to_dict(orient="records")
    ]

    payload = {
        "leaderboard": leaderboard_records,
        "alpha_attribution": result["alpha_attribution"],
        "champion_model_name": result["champion_model_name"],
        "champion_score": _to_native(result["champion_score"]),
        "generated_from": {
            "panel_rows": int(len(panel)),
            "stock_ids": sorted(panel["stock_id"].unique().tolist()),
            "unique_trading_dates": int(unique_dates),
            "date_range": [str(panel["trade_date"].min().date()), str(panel["trade_date"].max().date())],
            "train_window_size": TRAIN_WINDOW_SIZE,
            "test_window_size": TEST_WINDOW_SIZE,
            "label_horizon": LABEL_HORIZON,
            "embargo_days": EMBARGO_DAYS,
        },
    }

    os.makedirs(os.path.dirname(ARTIFACT_PATH), exist_ok=True)
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"已寫入 artifact：{ARTIFACT_PATH}")
    print(f"冠軍模型：{payload['champion_model_name']}（綜合分數 {payload['champion_score']}）")


if __name__ == "__main__":
    main()
