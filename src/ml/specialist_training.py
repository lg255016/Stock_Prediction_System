# src/ml/specialist_training.py
"""`UG-G3-SB3` Specialist Models 訓練支援函式（PO 2026-09-12 核准實作）。

本模組含：
- `prepare_fold_data()`——D3 對照臂 A／B 共用的 NaN／NULL 標籤處理規則
  （`UG_G3_SB3_GATE_A_PROPOSAL.md` §5 規則 (a)(b)(c)，第二輪複核訂正版）。
- `run_fold_for_arms()`——一個 Fold 對 A／B 兩臂呼叫 `prepare_fold_data()`
  並交叉驗證保留列索引集合相等。
- `iter_model_arm_pairs()`——D3 對照實驗的模型×對照臂配對表（LR 只配 A）。
- `compute_per_class_metrics()`／`compute_boundary_interior_metrics()`／
  `summarize_leakage_diagnosis()`——per-class 指標、單 Fold 邊界窗/內部窗
  診斷、跨 Fold 彙總判準（§3.3 洩漏診斷）。邊界窗/內部窗的 Δ 比較一律走
  `*_macro_f1_for_delta`（兩窗 `y_true` 支持類別交集），不得用兩側各自
  `macro_f1`——後者類別組成不同時不可比（PO 2026-09-12 複核訂正）。
- `fit_predict_specialist_fold()`——對 `prepare_fold_data()` 的輸出實際
  fit/predict 一個 Fold（PO 2026-09-13 核准，兩項必修）：(1) 標籤一律經
  `LabelEncoder` 編碼（`XGBClassifier` 對 Triple-Barrier 原始 `{-1,0,1}`
  標籤會直接拋 `ValueError`，RF／LightGBM／LR 雖不會但統一走同一條路徑，
  不做模型別分支）；(2) 特徵一律經 `create_scaler("robust")` 做 train-only
  fit 的縮放（`rsi_14`〔0～100〕與 `volume_ratio_5d`〔無上界〕等欄尺度差
  過大，未縮放的 LR 在弱相依標籤資料上會撞滿 `max_iter` 且發
  `ConvergenceWarning`；樹模型對尺度不變，多此一步無害，只留一條程式
  路徑）。

段級報告腳本讀取凍結面板、逐 Specialist×對照臂×模式呼叫上述函式，排在
後續 commit（`scripts/verify/ug_g3_sb3_specialist_report.py`，PO 已核准
命名）。
"""
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .baseline_models import NAN_INTOLERANT_MODELS
from .model_trainer import create_scaler


def prepare_fold_data(
    panel: pd.DataFrame,
    indices: Iterable[int],
    feature_cols: List[str],
    sentiment_cols: List[str],
    target_col: str = "target",
    arm: str = "A",
    trade_date_col: str = "trade_date",
) -> Dict[str, Any]:
    """對一個 Fold 的候選列套用 NaN／NULL 標籤處理規則 (a)(b)(c)。

    規則（`UG_G3_SB3_GATE_A_PROPOSAL.md` §5，PO 2026-09-12 第二輪複核訂正）：

    (a) `target_col` 為 `NULL` 的列剔除，計入 `n_target_null_excluded`。
    (b) **非情緒特徵欄**（`feature_cols` 中不在 `sentiment_cols` 者）含
        `NaN` 的列剔除、計入 `n_feature_null_excluded`——**不得 `fillna`
        掩蓋**。此規則對照臂 A／B 一視同仁：D3 判準是「B 相對 A 的樣本外
        表現提升」，兩臂每個 Fold 必須用完全相同的列，若剔除規則不一致，
        差異裡會混著樣本差異，不是純粹的特徵差異。
    (c) 情緒欄（`sentiment_cols`）的 `NaN` 允許保留，不剔除、不填補——
        交給 RF／LightGBM／XGBoost 原生處理。剔除規則 (b) 執行後，若非
        情緒欄仍殘留 `NaN`（結構上不應發生），拋 `ValueError`——這是
        防禦性斷言，不是規則 (c) 本身的判斷分支（`ValueError` 不再用於
        「對照臂 B 遇到非情緒欄 NaN」這個情境，那已改為規則 (b) 的剔除）。

    `arm="A"` 時 `sentiment_cols` 必須為空——避免對照臂 A 不小心帶入情緒
    欄，混淆「無情緒基準」的實驗設計。

    Args:
        panel: 完整面板（`build_panel_dataset()` 輸出或其子集）。
        indices: 本 Fold 候選列在 `panel` 中的整數位置（`WalkForwardSplitter.split()`
            回傳的 `train_indices`／`test_indices`）。
        feature_cols: 本對照臂使用的特徵欄清單（`ARM_A_FEATURE_COLS` 或
            `ARM_B_FEATURE_COLS`）。
        sentiment_cols: `feature_cols` 中屬於情緒欄的子集（`arm="A"` 時
            必須為空；`arm="B"` 時通常等於 `SENTIMENT_FEATURE_COLS` 與
            `feature_cols` 的交集）。
        target_col: 目標欄名稱（面板的 `target` 欄）。
        arm: `"A"` 或 `"B"`。
        trade_date_col: 面板的交易日欄名稱，供 `retained_index`／
            `trade_date` 供邊界窗/內部窗洩漏診斷（§3.3）使用。

    Returns:
        dict，含 `X`（特徵矩陣）、`y`（目標）、`retained_index`（剔除後
        保留列在 `panel` 中的原始索引）、`trade_date`（保留列的交易日，
        與 `retained_index` 對齊）、`n_target_null_excluded`、
        `n_feature_null_excluded`。
    """
    if arm not in ("A", "B"):
        raise ValueError(f"arm 必須為 'A' 或 'B'，收到: {arm!r}")
    if arm == "A" and len(list(sentiment_cols)) > 0:
        raise ValueError(
            "對照臂 A 不得含情緒欄——sentiment_cols 必須為空，"
            f"收到: {list(sentiment_cols)}"
        )

    sub = panel.iloc[list(indices)]

    # 規則 (a)：target 為 NULL 的列剔除。剔除後轉回 int——面板 target 欄
    # 因含 NaN 而是 float dtype，剔除後若不轉型，np.unique(y) 等下游會
    # 產生 float 標籤（如 0.0），與 compute_per_class_metrics() 用
    # cfg["labels"]（int）算出的 per_class 鍵（"0"）字面不一致
    # （PO 2026-09-13 複核指出）。
    target_null_mask = sub[target_col].isna()
    n_target_null_excluded = int(target_null_mask.sum())
    sub = sub.loc[~target_null_mask]
    sub = sub.assign(**{target_col: sub[target_col].astype(int)})

    # 規則 (b)：非情緒特徵欄含 NaN 的列剔除（對兩臂一致）。
    sentiment_cols_set = set(sentiment_cols)
    non_sentiment_cols = [c for c in feature_cols if c not in sentiment_cols_set]
    if non_sentiment_cols:
        feature_null_mask = sub[non_sentiment_cols].isna().any(axis=1)
    else:
        feature_null_mask = pd.Series(False, index=sub.index)
    n_feature_null_excluded = int(feature_null_mask.sum())
    sub = sub.loc[~feature_null_mask]

    # 規則 (c) 的防禦性斷言：剔除後非情緒欄不應再有 NaN（結構上不應發生）。
    if non_sentiment_cols and sub[non_sentiment_cols].isna().any().any():
        still_bad = sub[non_sentiment_cols].isna().any()
        bad_cols = still_bad[still_bad].index.tolist()
        raise ValueError(
            "prepare_fold_data() 內部不變式被違反：規則 (b) 剔除後，"
            f"以下非情緒欄仍殘留 NaN：{bad_cols}"
        )

    return {
        "X": sub[feature_cols],
        "y": sub[target_col],
        "retained_index": sub.index.to_numpy(),
        "trade_date": sub[trade_date_col].to_numpy(),
        "n_target_null_excluded": n_target_null_excluded,
        "n_feature_null_excluded": n_feature_null_excluded,
    }


def run_fold_for_arms(
    panel: pd.DataFrame,
    train_indices: Iterable[int],
    test_indices: Iterable[int],
    feature_cols_a: List[str],
    feature_cols_b: List[str],
    sentiment_cols: List[str],
    target_col: str = "target",
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """對一個 Fold 的 train／test 候選列，分別為對照臂 A／B 呼叫
    `prepare_fold_data()`，並交叉驗證兩臂剔除後保留的列索引集合相等。

    `prepare_fold_data()` 的規則 (b) 本身已保證「對照臂 A／B 剔除後保留的
    列索引集合相等」（兩臂共用同一組非情緒特徵欄判斷剔除）——**本函式的
    交叉驗證是防禦性的第二道檢查**，不是重新判斷剔除邏輯：若兩個獨立呼叫
    的結果不一致，代表 `prepare_fold_data()` 本身或呼叫端傳入的欄位清單
    出了問題，必須在這裡被攔下，而不是讓 D3 的兩臂比較悄悄建立在不同的
    樣本集合上。

    Returns:
        `{"A": {"train": <prepare_fold_data 回傳值>, "test": ...},
          "B": {"train": ..., "test": ...}}`

    Raises:
        ValueError: 若 A／B 兩臂剔除後保留的列索引集合不相等。
    """
    result_a_train = prepare_fold_data(
        panel, train_indices, feature_cols_a, [], target_col=target_col, arm="A")
    result_a_test = prepare_fold_data(
        panel, test_indices, feature_cols_a, [], target_col=target_col, arm="A")
    result_b_train = prepare_fold_data(
        panel, train_indices, feature_cols_b, sentiment_cols, target_col=target_col, arm="B")
    result_b_test = prepare_fold_data(
        panel, test_indices, feature_cols_b, sentiment_cols, target_col=target_col, arm="B")

    for split_name, result_a, result_b in (
        ("train", result_a_train, result_b_train),
        ("test", result_a_test, result_b_test),
    ):
        set_a = set(result_a["retained_index"].tolist())
        set_b = set(result_b["retained_index"].tolist())
        if set_a != set_b:
            raise ValueError(
                f"對照臂 A／B 的 {split_name} 集合剔除後保留的列索引不相等"
                f"（A：{len(set_a)} 列，B：{len(set_b)} 列）——D3 判準要求"
                "兩臂逐 Fold 比較同一批列，這代表 prepare_fold_data() 在"
                "兩臂之間的剔除結果出現不一致，須排查。"
            )

    return {
        "A": {"train": result_a_train, "test": result_a_test},
        "B": {"train": result_b_train, "test": result_b_test},
    }


# `UG-G3-SB3` D3 對照實驗支援的模型清單（`GATE3_STARTUP_APPLICATION.md` §5，
# 與 `baseline_models.PureTechnicalModelFactory.SUPPORTED_MODELS` 一致）。
MODEL_NAMES = ("logistic_regression", "random_forest", "lightgbm", "xgboost")


def iter_model_arm_pairs():
    """D3 對照實驗的模型×對照臂配對表：LogisticRegression 只配對照臂 A
    （原生不支援 `NaN`，Gate 3 §5 規定不得為它插補情緒欄）；RF／LightGBM／
    XGBoost 兩臂皆配（原生支援 `NaN`）。

    直接重用既有 `NAN_INTOLERANT_MODELS` 常數判斷，不在此重複硬寫模型
    名稱清單——若日後該常數變動（例如新增另一個不支援 NaN 的模型），
    這裡的配對表自動跟著正確，不需要兩處同步維護。

    Yields:
        `(model_name, arm)` tuple，`arm` 為 `"A"` 或 `"B"`。
    """
    for model_name in MODEL_NAMES:
        yield (model_name, "A")
        if model_name not in NAN_INTOLERANT_MODELS:
            yield (model_name, "B")


def compute_per_class_metrics(
    y_true: Iterable[Any],
    y_pred: Iterable[Any],
    labels: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """逐類別 Precision／Recall／F1／Support，另附 Macro F1。

    Args:
        y_true, y_pred: 真值與預測值。
        labels: 類別清單；`None` 時取 `y_true`／`y_pred` 聯集後遞增排序。

    Returns:
        `{str(label): {"precision":..,"recall":..,"f1":..,"support":..}, ...,
          "macro_f1": ...}`——鍵名用 `str(label)` 是因為類別值可能是
        `int`（如 Triple-Barrier 的 -1/0/1），JSON 序列化時字典鍵必須是
        字串，這裡在計算階段就統一，避免段級報告輸出時另外轉換。
    """
    from sklearn.metrics import f1_score, precision_recall_fscore_support

    y_true_arr = np.asarray(list(y_true))
    y_pred_arr = np.asarray(list(y_pred))
    if labels is None:
        labels = sorted(set(np.unique(y_true_arr).tolist()) | set(np.unique(y_pred_arr).tolist()))

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true_arr, y_pred_arr, labels=labels, zero_division=0)

    result: Dict[str, Any] = {}
    for label, p, r, f, s in zip(labels, precision, recall, f1, support):
        result[str(label)] = {
            "precision": float(p),
            "recall": float(r),
            "f1": float(f),
            "support": int(s),
        }
    result["macro_f1"] = float(
        f1_score(y_true_arr, y_pred_arr, labels=labels, average="macro", zero_division=0)
    )
    return result


def compute_boundary_interior_metrics(
    trade_date: Iterable[Any],
    y_true: Iterable[Any],
    y_pred: Iterable[Any],
    holding_period: int,
) -> Dict[str, Any]:
    """單一 Fold 的邊界窗／內部窗洩漏診斷（`UG_G3_SB3_GATE_A_PROPOSAL.md`
    §3.3）：**邊界窗 = 測試窗前 `holding_period` 個「交易日」，不是前
    `holding_period` 列**——面板是跨股票 long-format，同一天有多檔股票、
    多列，若誤用列數切分會把邊界窗切得過窄（甚至切不到一整天）。

    Args:
        trade_date: 與 `y_true`／`y_pred` 對齊的交易日序列（測試窗內的列）。
        holding_period: Triple-Barrier 的 H（或其他標籤視野），決定邊界窗
            涵蓋的交易日數。

    Returns:
        `{"boundary": {**compute_per_class_metrics 輸出（該窗自己的類別
          集合）, "n": ...}, "interior": {...},
          "labels_used_for_delta": [...], "labels_dropped": {"boundary": [...],
          "interior": [...]}, "boundary_macro_f1_for_delta": float|None,
          "interior_macro_f1_for_delta": float|None}`；某一側無列時該側為
        `{"n": 0, "macro_f1": None}`。

        `boundary`／`interior` 的 `macro_f1` 各自用該窗自己的類別集合算，
        供完整 per-class 揭露；**不得用它們直接算 Δ**——兩窗剛好缺席不同
        類別時（Timeout 小樣本常見），類別數不同的 macro 平均不可比，會把
        類別組成差異算成假滲漏訊號（PO 2026-09-12 複核指出）。跨窗比較
        一律改用 `*_for_delta` 這兩個欄位，兩者是在**兩窗 `y_true` 皆有
        支持（support>0）的類別交集**上算的 macro F1，`labels_used_for_delta`
        揭露交集內容、`labels_dropped` 揭露哪一側因缺席被排除的類別——
        段級報告應印出這兩項，讓「是否發生」可被看見，不是靜默處理。
    """
    dates = pd.to_datetime(pd.Series(list(trade_date)))
    unique_sorted_dates = sorted(dates.unique())
    boundary_dates = set(unique_sorted_dates[:holding_period])
    is_boundary = dates.isin(boundary_dates).to_numpy()

    y_true_arr = np.asarray(list(y_true))
    y_pred_arr = np.asarray(list(y_pred))

    result: Dict[str, Any] = {}
    masks = {"boundary": is_boundary, "interior": ~is_boundary}
    true_labels_by_side: Dict[str, set] = {}
    for name, mask in masks.items():
        n = int(mask.sum())
        if n == 0:
            result[name] = {"n": 0, "macro_f1": None}
            true_labels_by_side[name] = set()
        else:
            metrics = compute_per_class_metrics(y_true_arr[mask], y_pred_arr[mask])
            metrics["n"] = n
            result[name] = metrics
            true_labels_by_side[name] = set(np.unique(y_true_arr[mask]).tolist())

    common_labels = sorted(true_labels_by_side["boundary"] & true_labels_by_side["interior"])
    result["labels_used_for_delta"] = common_labels
    result["labels_dropped"] = {
        "boundary": sorted(true_labels_by_side["boundary"] - set(common_labels)),
        "interior": sorted(true_labels_by_side["interior"] - set(common_labels)),
    }

    from sklearn.metrics import f1_score

    for name, mask in masks.items():
        n = int(mask.sum())
        if not common_labels or n == 0:
            result[f"{name}_macro_f1_for_delta"] = None
        else:
            result[f"{name}_macro_f1_for_delta"] = float(
                f1_score(
                    y_true_arr[mask], y_pred_arr[mask],
                    labels=common_labels, average="macro", zero_division=0,
                )
            )
    return result


# 跨 Fold 洩漏彙總判準（`UG_G3_SB3_GATE_A_PROPOSAL.md` §3.3，PO 2026-09-12
# 核准）：**工程判斷，不是統計檢定**——門檻本身沒有 p-value 或顯著水準的
# 理論依據，是「多少比例的 Fold 都偏向同一個方向、偏移量級是否值得注意」
# 的實務判斷。兩個門檻是 AND，缺一不可：只看比例會被「全部 Fold 都偏一點
# 點」誤判為滲漏；只看中位數會被「少數 Fold 偏很多、大多數 Fold 不偏」
# 誤判為滲漏。
LEAKAGE_FRAC_POSITIVE_THRESHOLD = 0.70
LEAKAGE_MEDIAN_DELTA_THRESHOLD = 0.05


def summarize_leakage_diagnosis(per_fold_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """跨 Fold 彙總邊界窗／內部窗洩漏診斷，回答「邊界窗是否**系統性**
    偏離內部窗（非單一 Fold 隨機波動）」——不能只靠人眼看單一 Fold 的
    數字（`UG_G3_SB3_GATE_A_PROPOSAL.md` §3.3 判準）。

    Args:
        per_fold_results: 每個 Fold 呼叫 `compute_boundary_interior_metrics()`
            的回傳值列表。Δ 一律取 `boundary_macro_f1_for_delta` 與
            `interior_macro_f1_for_delta`（兩窗 `y_true` 支持類別交集上算
            的 macro F1，而非兩側各自類別集合的 `macro_f1`——後者在兩窗
            類別組成不同時不可比，見 `compute_boundary_interior_metrics()`
            docstring，PO 2026-09-12 複核指出）。某 Fold 若任一 `*_for_delta`
            為 `None`（該側無列，或兩窗無共同支持類別），該 Fold 不計入
            Δ 分布。

    Returns:
        `{"n_folds": 納入計算的 Fold 數,
          "deltas": 逐 Fold 的 Δ = boundary_macro_f1 − interior_macro_f1,
          "median_delta": Δ 中位數,
          "frac_positive": Δ>0 的 Fold 比例,
          "flagged": bool（frac_positive >= 門檻 且 median_delta >= 門檻）,
          "threshold_frac_positive": ..., "threshold_median_delta": ...}`

        若無任何 Fold 可計入 Δ 分布，`n_folds=0`、`median_delta`／
        `frac_positive` 為 `None`、`flagged=False`。
    """
    deltas = []
    for fold_result in per_fold_results:
        boundary_f1 = fold_result["boundary_macro_f1_for_delta"]
        interior_f1 = fold_result["interior_macro_f1_for_delta"]
        if boundary_f1 is None or interior_f1 is None:
            continue
        deltas.append(boundary_f1 - interior_f1)

    if not deltas:
        return {
            "n_folds": 0,
            "deltas": [],
            "median_delta": None,
            "frac_positive": None,
            "flagged": False,
            "threshold_frac_positive": LEAKAGE_FRAC_POSITIVE_THRESHOLD,
            "threshold_median_delta": LEAKAGE_MEDIAN_DELTA_THRESHOLD,
        }

    delta_arr = np.asarray(deltas, dtype=float)
    median_delta = float(np.median(delta_arr))
    frac_positive = float((delta_arr > 0).mean())
    flagged = (
        frac_positive >= LEAKAGE_FRAC_POSITIVE_THRESHOLD
        and median_delta >= LEAKAGE_MEDIAN_DELTA_THRESHOLD
    )

    return {
        "n_folds": len(deltas),
        "deltas": deltas,
        "median_delta": median_delta,
        "frac_positive": frac_positive,
        "flagged": flagged,
        "threshold_frac_positive": LEAKAGE_FRAC_POSITIVE_THRESHOLD,
        "threshold_median_delta": LEAKAGE_MEDIAN_DELTA_THRESHOLD,
    }


def fit_predict_specialist_fold(
    model_name: str,
    train_prepared: Dict[str, Any],
    test_prepared: Dict[str, Any],
    random_state: int = 42,
    return_proba: bool = False,
) -> Dict[str, Any]:
    """對 `prepare_fold_data()` 的輸出（`train_prepared`／`test_prepared`）
    實際 fit/predict 一個 Fold。**不做任何欄位轉換或 fillna**——NaN 處理
    已在規則 (a)(b)(c) 完成，這裡只管 fit/predict。

    兩項統一處理（PO 2026-09-13 核准，皆用真實工廠模型於容器內實測驗證）：

    1. **標籤經 `LabelEncoder` 編碼**（`fit` 在訓練集 `y` 上，預測後
       `inverse_transform` 還原）：`XGBClassifier.fit()` 對 Triple-Barrier
       原始 `{-1, 0, 1}` 標籤會直接拋
       `ValueError: Invalid classes inferred from unique values of y.
       Expected: [0 1 2], got [-1 0 1]`（實測確認）；RF／LightGBM／LR
       不會，但四個模型統一走同一條編碼路徑，不對 xgboost 開特例分支。
    2. **特徵經 `create_scaler("robust")` 縮放**（`fit_transform` 在訓練集，
       `transform` 在測試集——train-only fit，比照 `MultiModalTrainer`
       既有紀律）：對照臂 A 的 `rsi_14`（0～100）與 `volume_ratio_5d`
       （無上界）等欄尺度差過大，未縮放的 LR 在真實形狀的資料（多特徵、
       其中一欄尺度放大、標籤與特徵僅弱相依）上會撞滿 `max_iter=500`
       且發 `ConvergenceWarning`（實測確認：8 特徵/300 列/一欄×1e4/
       三類弱相依標籤，`n_iter_=500`；縮放後 `n_iter_=14`）。樹模型對
       尺度不變，多此一步無害，只留一條程式路徑。

       `create_scaler` 在**模組頂層**匯入（不是函式內 lazy import）——
       測試以 `patch("src.ml.specialist_training.create_scaler", ...)`
       替換為 spy 驗證「只在訓練集 fit」，頂層匯入才會在模組命名空間
       留下可被 patch 的名字；函式內 `from .model_trainer import
       create_scaler` 只會建立函式區域變數，patch 對它沒有作用。

    Args:
        model_name: `MODEL_NAMES` 之一。
        train_prepared／test_prepared: `prepare_fold_data()` 的回傳值
            （至少含 `X`／`y`；`test_prepared` 另用到 `trade_date`／
            `retained_index`，此處原樣透傳供下游邊界窗/內部窗診斷使用）。
        random_state: 傳給 `PureTechnicalModelFactory.create_model()`。
        return_proba: `UG-G3-SB4`（PO 2026-09-14 核准）新增——`True` 時
            額外呼叫 `model.predict_proba()`，回傳字典**新增** `y_proba`／
            `proba_classes` 兩鍵，其餘既有鍵與計算結果不變。**預設
            `False`，既有呼叫端（`UG-G3-SB3`）零改動**：不傳此參數時，
            回傳字典的鍵集合與 SB3 既有行為逐鍵相同。

    Returns:
        `{"model_name", "y_true"（原始標籤空間）, "y_pred"（原始標籤空間）,
          "trade_date", "retained_index", "n_train", "n_test",
          "train_classes"（訓練集出現的原始類別，遞增排序）,
          "scaler_type", "n_iter_"（LR 等有此屬性的模型；否則 `None`）,
          "y_proba"（僅 `return_proba=True` 時存在，`shape=(n_test,
          n_classes)`，欄序對齊 `proba_classes`）,
          "proba_classes"（僅 `return_proba=True` 時存在，與
          `train_classes` 同一來源、同一順序——該折訓練集實際出現的類別，
          遞增排序；小折若缺席某類別，此陣列會忠實反映缺席，不假設固定
          類別數，下游組 OOF 矩陣時需按此陣列對齊，不得假設欄數固定）}`
    """
    from sklearn.preprocessing import LabelEncoder

    from .baseline_models import PureTechnicalModelFactory

    X_train = train_prepared["X"]
    y_train_raw = train_prepared["y"]
    X_test = test_prepared["X"]
    y_test_raw = test_prepared["y"]

    label_encoder = LabelEncoder()
    y_train_encoded = label_encoder.fit_transform(y_train_raw)
    train_classes = label_encoder.classes_.tolist()

    scaler = create_scaler("robust")
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = PureTechnicalModelFactory.create_model(model_name, random_state=random_state)
    model.fit(X_train_scaled, y_train_encoded)
    y_pred_encoded = model.predict(X_test_scaled)
    y_pred = label_encoder.inverse_transform(y_pred_encoded)

    n_iter_attr = getattr(model, "n_iter_", None)
    n_iter_ = int(np.asarray(n_iter_attr).max()) if n_iter_attr is not None else None

    result = {
        "model_name": model_name,
        "y_true": np.asarray(y_test_raw),
        "y_pred": np.asarray(y_pred),
        "trade_date": test_prepared["trade_date"],
        "retained_index": test_prepared["retained_index"],
        "n_train": len(y_train_raw),
        "n_test": len(y_test_raw),
        "train_classes": train_classes,
        "scaler_type": "robust",
        "n_iter_": n_iter_,
    }

    if return_proba:
        # `label_encoder.classes_` 是遞增排序的原始類別陣列，
        # `predict_proba()` 的欄序精確對應這個陣列的索引順序
        # （sklearn／LightGBM／XGBoost 皆依 `classes_` 順序輸出機率）——
        # `proba_classes` 與 `train_classes` 因此是同一份資料的兩個名字，
        # 刻意都保留在回傳字典中，供呼叫端依語境選用。
        result["y_proba"] = model.predict_proba(X_test_scaled)
        result["proba_classes"] = train_classes

    return result
