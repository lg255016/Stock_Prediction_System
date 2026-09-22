# src/ml/stacking.py
"""`UG-G3-SB4` OOF Stacking Meta-Learner（PO 2026-09-14 核准實作，Gate A
`doc/upgrade/gates/UG_G3_SB4_GATE_A_PROPOSAL.md` `be64f9b` §4／§6／§13，
紅測 `e46a8a7`／`69f6e35`／`a1abcf4`）。

**2026-09-15 補件（PO 複核 `dcf48c5` 後，審查方五個探針發現五處「靜默
通過」）**：`build_meta_learner_input()` 現在要求 `META_REGIME_FEATURE_COLS`
全部存在（不是「有就用、沒有就跳過」）、機率欄須恰為 4 模型 × 完整類別
集合；`assemble_oof_matrix()` 現在拒絕重複的 `(model, stock_id,
trade_date)` 鍵與長度不一致的序列（不得靜默截斷）；
`select_best_specialist()` 現在要求模型集合恰為 `EXPECTED_MODEL_NAMES`，
且新增 `target_column` 參數，`f1_score()` 依此傳固定 `labels=`（避免
某 Specialist 段內缺席某類別真實列時，macro 分母跨模型不一致而不可比）。

本模組只處理**折 0～32**（Meta-Train ＋ Meta-Eval）範圍內、**Arm A** 四個
Specialist（LogisticRegression／RandomForest／LightGBM／XGBoost）的 OOF
（樣本外）預測堆疊。Arm B 在折 0～32 範圍內情緒訊號為 0（Gate A §3.1
實測），結構性排除，不在本模組任何函式的正常路徑上出現。Holdout（折
33～42，`trade_date >= HOLDOUT_START_DATE`）全程不被本模組讀取、訓練、
評估或用於選擇——這是 Gate 3 已核准規格（`PURGED_WALK_FORWARD_SPEC.md`
§3.3、`SYSTEM_UPGRADE_MASTER_PLAN.md` §10／§11.3）的直接落地，保留給
`UG-G3-SB7` 做最終績效宣稱。

本模組含：
- 三個專屬例外類別（`MetaInputContractError`／`HoldoutViolation`／
  `SelectionSourceError`）——**彼此不互相繼承**（PO 2026-09-14 第三輪
  複核明確要求），皆直接繼承共同基底 `StackingContractError`，供呼叫端
  視需要以基底類型統一攔截，但個別型別之間不構成子型別關係，避免
  `assertRaises(某型別)` 被另一型別的例外意外滿足。
- `assemble_oof_matrix()`——把逐 Fold 的 Specialist 預測（含機率）組成
  寬格式 OOF 矩陣，結構性拒絕任何 Arm B 紀錄與不完整的 4 組模型。
- `apply_second_stage_purge()`——Meta-Train 段內、`label_end_date`（或
  `label_end_date_tb`）晚於或等於 Meta-Eval 起點的列標為 `purged`；規則
  只作用於 `split_segment == "meta_train"` 的列，不觸碰 `meta_eval`／
  既有 `purged` 列（PO 第三輪複核追加，比照 SB3 `6dcbdc7` 的盲點修補）。
- `reject_rows_at_or_after()`——Holdout 守衛，`trade_date >= 邊界`
  （含端點）即拋 `HoldoutViolation`。
- `select_best_specialist()`——只接受 `split_segment == "meta_train"`
  的資料，依模組層級常數 `SELECTION_METRIC` 排序，回傳
  `(best_model_name, ranking_df)`，`ranking_df` 含完整排名與各 Specialist
  的樣本數（`n_rows`），不只第一名。
- `build_meta_learner_input()`——Meta-Learner 輸入矩陣組裝，欄位限定
  OOF 機率欄 ∪ `META_REGIME_FEATURE_COLS`；預設只消費
  `split_segment == "meta_train"` 的列（訓練路徑的安全預設值）；任何
  欄含 `NaN` 的列排除並逐欄計數回報，不插補、不填 0（比照 SB3 規則 (b)）。
- `iter_oof_folds()`——包裝 `WalkForwardSplitter.split()`，只產出整折
  測試窗完全落在 Holdout 邊界之前的折（`test_end_date < HOLDOUT_START_DATE`
  才產出，整折跨界即丟棄，不切半折，PO 2026-09-14 明確裁決）。
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


# ==============================================================================
# 例外類別（三者互不繼承，PO 第三輪複核明確要求）
# ==============================================================================

class StackingContractError(Exception):
    """本模組所有契約違規的共同基底，供呼叫端視需要統一攔截。
    **不得**被下面三個具體例外類別互相繼承使用——它們各自代表不同的
    違規類別，混淆會讓 `assertRaises(某具體型別)` 失去分辨力。"""


class MetaInputContractError(StackingContractError):
    """Meta-Learner／OOF 矩陣的輸入或輸出違反欄位契約——含不允許的欄位、
    不完整的 (model, arm) 組合、或不該出現的 Arm B 紀錄。"""


class HoldoutViolation(StackingContractError):
    """任何操作觸碰到 Gate 3 Holdout（`trade_date >= HOLDOUT_START_DATE`，
    含端點本身）。"""


class SelectionSourceError(StackingContractError):
    """`select_best_specialist()` 收到的資料不合格——含非
    `split_segment == "meta_train"` 的列，或模型集合不是恰好
    `EXPECTED_MODEL_NAMES` 四組（2026-09-15 審查方複核 P5 追加）。"""


# ==============================================================================
# 常數（三層結構與選型的邊界依據，Gate A §4.3／§4.4／§4.6，PO 已核准）
# ==============================================================================

#: Meta-Learner 選出「最佳單一 Specialist」的唯一排序指標——模組層級
#: 常數，`select_best_specialist()` 的介面刻意不接受任何覆寫參數（Gate A
#: §3.4，PO 2026-09-14 追加要求）。
SELECTION_METRIC = "macro_f1"

#: Gate 3 Holdout 的起點（折 33 測試窗第一天，`VERIFIED THIS SESSION`
#: 對凍結面板重跑 `WalkForwardSplitter` 實測）。`trade_date >= 此值`
#: （含端點本身）一律視為 Holdout，`UG-G3-SB4`～`UG-G3-SB6` 全程不得
#: 讀取、訓練、評估或用於選擇。
HOLDOUT_START_DATE = pd.Timestamp("2025-10-23")

#: Meta-Eval 段的起點（折 27 測試窗第一天，`VERIFIED THIS SESSION`）。
#: `apply_second_stage_purge()` 以此為界，把 Meta-Train 中標籤結算日期
#: 晚於或等於此值的列標為 `purged`。
META_EVAL_START_DATE = pd.Timestamp("2025-05-02")

#: `assemble_oof_matrix()` 要求恰好齊全的 4 組 Specialist（Arm A only，
#: 短代碼——與 `src/ml/specialist_training.py::MODEL_NAMES` 的完整模型
#: 名稱是兩個不同的命名空間，呼叫端在組 `fold_results` 前需自行透過
#: `MODEL_NAME_SHORT_CODES` 轉換）。
EXPECTED_MODEL_NAMES = frozenset({"lr", "rf", "lgbm", "xgb"})

#: `MODEL_NAMES`（完整模型名稱）→ OOF 欄名短代碼的對照表，供 OOF 產生
#: 腳本（實作下一段）組 `fold_results` 時使用，本模組內部不直接依賴此
#: 常數（`assemble_oof_matrix()` 只認短代碼），集中定義以避免各腳本各自
#: 發明一套縮寫。
MODEL_NAME_SHORT_CODES: Dict[str, str] = {
    "logistic_regression": "lr",
    "random_forest": "rf",
    "lightgbm": "lgbm",
    "xgboost": "xgb",
}

#: 兩個 target 各自的類別定義域（遞增排序）——`assemble_oof_matrix()`
#: 依此在輸出矩陣中固定產生每個類別的欄位，缺席類別填 `NaN`，欄數不隨
#: 個別折的訓練集實際出現的類別而變動。
TARGET_CLASS_DOMAINS: Dict[str, List[int]] = {
    "target_up_down": [0, 1],
    "target_triple_barrier": [-1, 0, 1],
}

#: OOF 矩陣中屬於「稽核用中介欄位」、不進入 Meta-Learner 輸入矩陣、但
#: 也不算違反欄位契約的欄名——`build_meta_learner_input()` 會先剝除
#: 這些欄位再檢查剩下的欄是否都落在允許清單內。
OOF_METADATA_COLS = frozenset({
    "stock_id", "trade_date", "fold_id", "split_segment",
    "label_end_date", "label_end_date_tb",
    "target_up_down", "target_triple_barrier",
})

_PROB_COL_PATTERN = re.compile(r"^(lr|rf|lgbm|xgb)_A_p")


def _class_token(target_column: str, cls: int) -> str:
    """類別值 → OOF 欄名的類別後綴。`target_triple_barrier` 的負數類別
    以 `m1` 表示（欄名避免出現減號）；`target_up_down` 直接用類別值本身
    （`0`／`1`）。"""
    if target_column == "target_triple_barrier":
        mapping = {-1: "m1", 0: "0", 1: "p1"}
        if cls not in mapping:
            raise MetaInputContractError(
                f"target_triple_barrier 出現未知類別: {cls}（僅接受 -1/0/1）")
        return mapping[cls]
    return str(int(cls))


# ==============================================================================
# assemble_oof_matrix
# ==============================================================================

def assemble_oof_matrix(
    fold_results: Iterable[Dict[str, Any]],
    target_column: str,
) -> pd.DataFrame:
    """把逐 Fold、逐 Specialist 的機率預測組成寬格式 OOF 矩陣。

    Args:
        fold_results: 每筆為一個 `(model_name, arm, fold_id)` 在某折測試窗
            的預測結果，至少含 `model_name`（`EXPECTED_MODEL_NAMES` 之一的
            短代碼）、`arm`（必須為 `"A"`）、`fold_id`、`stock_id`（序列）、
            `trade_date`（序列）、`y_proba`（`shape=(n, k)`）、
            `proba_classes`（該筆預測實際出現的類別，遞增排序）。
        target_column: `TARGET_CLASS_DOMAINS` 的鍵之一，決定輸出矩陣要
            固定產生哪些類別欄位。

    Returns:
        寬格式 `pd.DataFrame`，含 `stock_id`／`trade_date`／`fold_id` 與
        逐 `(model, class)` 的機率欄（`<model>_A_p<class_token>`）。缺席
        類別（該折訓練集未出現）填 `NaN`，不得填 `0`。

    Raises:
        MetaInputContractError: `target_column` 未知；任何紀錄的 `arm`
            不是 `"A"`；`fold_results` 涵蓋的模型組合不是恰好
            `EXPECTED_MODEL_NAMES` 四組；同一筆紀錄的 `stock_id`／
            `trade_date`／`y_proba` 列數不一致（2026-09-15 補件，不得
            靜默截斷）；同一 `(model, stock_id, trade_date)` 出現兩次
            （2026-09-15 補件，同一列不可能來自兩折）。
    """
    fold_results = list(fold_results)

    if target_column not in TARGET_CLASS_DOMAINS:
        raise MetaInputContractError(
            f"未知的 target_column: {target_column!r}（僅接受 "
            f"{sorted(TARGET_CLASS_DOMAINS)}）")
    class_domain = TARGET_CLASS_DOMAINS[target_column]

    bad_arms = [r for r in fold_results if r.get("arm") != "A"]
    if bad_arms:
        raise MetaInputContractError(
            f"本 SB 只用 Arm A（折 0～32 情緒訊號為 0，Gate A §3.1 裁決），"
            f"發現 {len(bad_arms)} 筆非 A 臂紀錄："
            f"{[(r.get('model_name'), r.get('arm')) for r in bad_arms]}")

    model_names = {r["model_name"] for r in fold_results}
    if model_names != EXPECTED_MODEL_NAMES:
        missing = EXPECTED_MODEL_NAMES - model_names
        extra = model_names - EXPECTED_MODEL_NAMES
        raise MetaInputContractError(
            f"OOF 組裝需要恰好 4 組 Specialist {sorted(EXPECTED_MODEL_NAMES)}："
            f"缺 {sorted(missing) or '無'}，多出不認得的 {sorted(extra) or '無'}")

    records: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    seen_keys: set = set()
    for entry in fold_results:
        model = entry["model_name"]
        proba_classes = list(entry["proba_classes"])
        y_proba = np.asarray(entry["y_proba"])
        stock_ids = list(entry["stock_id"])
        trade_dates = list(entry["trade_date"])
        fold_id = entry.get("fold_id")

        # P4（2026-09-15 補件）：三個序列長度必須一致，不得讓 zip() 靜默
        # 截斷成較短者的長度——那會悄悄丟掉資料，且不留下任何痕跡。
        if not (len(stock_ids) == len(trade_dates) == y_proba.shape[0]):
            raise MetaInputContractError(
                f"model={model!r} 的 stock_id（{len(stock_ids)} 筆）／"
                f"trade_date（{len(trade_dates)} 筆）／y_proba 列數"
                f"（{y_proba.shape[0]} 列）長度不一致，不得靜默截斷")

        for row_i, (sid, td) in enumerate(zip(stock_ids, trade_dates)):
            # P3（2026-09-15 補件）：同一 (model, stock_id, trade_date)
            # 不可能出現兩次——每個 (stock_id, trade_date) 只會落在唯一
            # 一折的測試窗內，重複鍵代表上游折切分或呼叫端組資料時出錯，
            # 靜默覆寫會讓這個錯誤完全無法被發現。
            dedup_key = (model, sid, td)
            if dedup_key in seen_keys:
                raise MetaInputContractError(
                    f"重複的 (model, stock_id, trade_date) 鍵：{dedup_key}"
                    f"——同一列不可能來自兩折，上游折切分或資料組裝有誤")
            seen_keys.add(dedup_key)

            rec_key = (sid, td)
            rec = records.setdefault(
                rec_key, {"stock_id": sid, "trade_date": td, "fold_id": fold_id})
            for cls in class_domain:
                col = f"{model}_A_p{_class_token(target_column, cls)}"
                if cls in proba_classes:
                    cls_idx = proba_classes.index(cls)
                    rec[col] = float(y_proba[row_i, cls_idx])
                else:
                    rec[col] = np.nan

    return pd.DataFrame(list(records.values()))


# ==============================================================================
# apply_second_stage_purge
# ==============================================================================

def apply_second_stage_purge(
    oof_df: pd.DataFrame,
    meta_eval_start_date,
    label_end_col: str,
) -> pd.DataFrame:
    """折 0～32 之內的巢狀切分（Meta-Train／Meta-Eval）本身需要它自己的
    Purge——這一刀不在折的邊界上，`WalkForwardSplitter` 每折之間的一階
    Purge 管不到。規則**只作用於 `split_segment == "meta_train"` 的
    列**：`label_end_col`（`label_end_date` 或 `label_end_date_tb`）
    晚於或等於 `meta_eval_start_date` 者改標為 `"purged"`；不觸碰
    `"meta_eval"` 或本已是 `"purged"` 的列——`meta_eval` 列的標籤結算
    日期依定義必然晚於或等於這個邊界（它們就是從那天起算的），若規則
    不分 segment 一律套用，會把整個 Meta-Eval 段誤標為 `purged`（PO
    第三輪複核追加的盲點修補，見 `tests/test_ug_g3_sb4_stacking_red.py`
    `test_purge_rule_only_applies_to_meta_train_rows`）。

    列不刪除，只改標籤——`purged` 列仍保留在輸出中供稽核查核。
    """
    boundary = pd.Timestamp(meta_eval_start_date)
    out = oof_df.copy()

    is_meta_train = out["split_segment"] == "meta_train"
    late_enough = pd.to_datetime(out[label_end_col]) >= boundary
    purge_mask = is_meta_train & late_enough

    out.loc[purge_mask, "split_segment"] = "purged"
    return out


# ==============================================================================
# reject_rows_at_or_after（Holdout 守衛）
# ==============================================================================

def reject_rows_at_or_after(
    df: pd.DataFrame,
    date_col: str,
    boundary_date,
) -> pd.DataFrame:
    """`df[date_col] >= boundary_date`（含端點本身）的任何一列存在，即
    結構性拒絕。原樣回傳 `df`（不做任何過濾）供呼叫端鏈式使用——本函式
    的目的是「檢查後放行或拋例外」，不是「過濾掉違規列後悄悄放行」。
    """
    boundary = pd.Timestamp(boundary_date)
    violating = df[pd.to_datetime(df[date_col]) >= boundary]
    if len(violating) > 0:
        raise HoldoutViolation(
            f"{len(violating)} 列的 {date_col} 落在 Holdout 邊界"
            f"（{boundary.date()}，含端點本身）之後，結構性拒絕。"
            f"Gate 3 Holdout（{boundary.date()} 起）全程不得被 "
            f"UG-G3-SB4～SB6 讀取、訓練、評估或用於選擇。")
    return df


# ==============================================================================
# select_best_specialist
# ==============================================================================

def select_best_specialist(
    meta_train_df: pd.DataFrame,
    target_column: str,
) -> Tuple[str, pd.DataFrame]:
    """只接受 `split_segment == "meta_train"` 的資料，依模組層級常數
    `SELECTION_METRIC`（固定為 `"macro_f1"`，不接受呼叫端覆寫——介面上
    刻意不提供任何指標參數）排序四個 Specialist（Arm A），回傳
    `(best_model_name, ranking_df)`。`ranking_df` 含完整排名（不只
    第一名）與各 Specialist 的樣本數 `n_rows`（PO 2026-09-14 複核要求：
    若因缺類別 NaN 排除列數不同，排名要能看出是在多少列上算的）。

    Args:
        meta_train_df: 至少含 `model_name`／`y_true`／`y_pred`／
            `split_segment` 欄。
        target_column: `TARGET_CLASS_DOMAINS` 的鍵之一，**必填、無預設值**
            （2026-09-15 補件，P7）——舊版預設 `"target_up_down"` 曾被
            審查方用 Triple-Barrier 型態資料（`y_true` 含 `-1`）呼叫但
            不傳此參數實測：不報錯，`labels=[0,1]` 靜默忽略 `-1` 類，
            算出一個看似合理、實則用錯定義域的分數——預設值把一個必須
            明講的選擇藏起來了，改為必填杜絕此路徑。`f1_score()` 依此
            傳固定 `labels=`（2026-09-15 審查方複核追加）——若某
            Specialist 的 Meta-Train 段剛好沒有某個類別的真實列（例如
            Triple-Barrier 的 Timeout），sklearn 預設只用 `y_true`／
            `y_pred` 聯集決定要平均哪些類別，會讓這個 Specialist 的
            macro 分母比其他模型少一項，排名因此不可比。

    Raises:
        SelectionSourceError: 任何一列的 `split_segment` 不是
            `"meta_train"`；模型集合不是恰好 `EXPECTED_MODEL_NAMES`
            四組（2026-09-15 審查方複核 P5 追加，缺一組即拒絕，不得
            靜默用不完整的排名代替）；`target_column` 未知；
            `y_true`／`y_pred` 出現不在該 `target_column` 定義域內的值
            （2026-09-15 補件，P7，不得靜默把定義域外的值排除在 macro
            平均之外算出一個貌似合理的分數）。
    """
    if not (meta_train_df["split_segment"] == "meta_train").all():
        bad_values = sorted(
            meta_train_df.loc[
                meta_train_df["split_segment"] != "meta_train", "split_segment"
            ].unique().tolist())
        raise SelectionSourceError(
            f"select_best_specialist() 只接受 split_segment == 'meta_train' "
            f"的資料，發現其他值：{bad_values}")

    model_set = set(meta_train_df["model_name"].unique())
    if model_set != EXPECTED_MODEL_NAMES:
        missing = EXPECTED_MODEL_NAMES - model_set
        extra = model_set - EXPECTED_MODEL_NAMES
        raise SelectionSourceError(
            f"select_best_specialist() 需要恰好 4 組 Specialist "
            f"{sorted(EXPECTED_MODEL_NAMES)}：缺 {sorted(missing) or '無'}，"
            f"多出不認得的 {sorted(extra) or '無'}")

    if target_column not in TARGET_CLASS_DOMAINS:
        raise SelectionSourceError(
            f"未知的 target_column: {target_column!r}（僅接受 "
            f"{sorted(TARGET_CLASS_DOMAINS)}）")
    labels = TARGET_CLASS_DOMAINS[target_column]

    # P7（2026-09-15 補件）：y_true／y_pred 出現的值必須落在宣告的
    # target_column 定義域內——TB 資料誤配 target_up_down 這類錯誤，
    # 不靠這層檢查會靜默把定義域外的值排除在 macro 平均之外，算出一個
    # 看似合理、實則基準錯誤的分數。
    observed_values = (
        set(meta_train_df["y_true"].unique())
        | set(meta_train_df["y_pred"].unique()))
    out_of_domain = observed_values - set(labels)
    if out_of_domain:
        raise SelectionSourceError(
            f"y_true／y_pred 出現不在 target_column={target_column!r} "
            f"定義域（{sorted(labels)}）內的值：{sorted(out_of_domain)}"
            f"——target_column 選錯了")

    from sklearn.metrics import f1_score

    rows = []
    for model_name, group in meta_train_df.groupby("model_name"):
        score = f1_score(group["y_true"], group["y_pred"], labels=labels, average="macro")
        rows.append({
            "model_name": model_name,
            SELECTION_METRIC: score,
            "n_rows": len(group),
        })

    ranking_df = (
        pd.DataFrame(rows)
        .sort_values(SELECTION_METRIC, ascending=False)
        .reset_index(drop=True)
    )
    best_model = ranking_df.iloc[0]["model_name"]
    return best_model, ranking_df


# ==============================================================================
# build_meta_learner_input
# ==============================================================================

def build_meta_learner_input(
    oof_df: pd.DataFrame,
    segment: str = "meta_train",
    regime_cols: Optional[List[str]] = None,
    target_column: Optional[str] = None,
    return_retained_index: bool = False,
):
    """組 Meta-Learner 的輸入矩陣。欄位限定為 OOF 機率欄
    （`^(lr|rf|lgbm|xgb)_A_p`）∪ `META_REGIME_FEATURE_COLS`——任何其他
    欄（原始特徵、其他中介欄）一律拒絕。**預設只消費
    `split_segment == segment`（預設 `"meta_train"`）的列**——訓練路徑
    的安全預設值，避免呼叫端忘記傳參數就靜默訓練在 `meta_eval`／
    `purged` 列上（PO 2026-09-14 第三輪複核追加的盲點修補）。任何輸入
    欄含 `NaN` 的列（機率欄因缺席類別產生的 `NaN`，或 regime 欄因暖機期
    產生的 `NaN`）一律排除，**不插補、不填 0**（比照 `UG-G3-SB3` 規則
    (b)）。

    Args:
        oof_df: `assemble_oof_matrix()` 的輸出（或等義結構），至少含
            OOF 機率欄、`META_REGIME_FEATURE_COLS`、`split_segment`。
        segment: 只消費此 `split_segment` 值的列，預設 `"meta_train"`。
        regime_cols: 允許的非 OOF 輸入欄清單，預設
            `META_REGIME_FEATURE_COLS`。
        target_column: `TARGET_CLASS_DOMAINS` 的鍵之一，選用（預設
            `None` 不核對）。**跨模型一致性檢查（見下）測不出「四個
            模型一致缺同一類別欄」的情況**——四者互相比對完全相同時，
            一致性本身無法暴露缺陷。傳入此參數時，額外核對機率欄的
            類別集合是否等於該 target 真正的定義域（2026-09-15 補件，
            P6）。OOF 產生腳本應一律傳入此參數。
        return_retained_index: `True` 時額外回傳一個 `pd.Index`（P8，
            2026-09-15 補件）——`oof_df` 原始索引標籤中真正保留下來的
            那些（排除違規列之前的標籤，非位置）。呼叫端可用
            `oof_df.loc[retained_index, 其他欄]` 精確對齊其他欄（例如
            真實標籤 `y`），不需自行重算 segment／NaN 兩層遮罩——重算
            是風險：兩次獨立計算「長度相等」不保證「同一批列」。預設
            `False`，既有呼叫端的 2-tuple 回傳零改動。

    Returns:
        預設（`return_retained_index=False`）：`(matrix_df,
        exclusion_counts)`。`return_retained_index=True` 時：
        `(matrix_df, exclusion_counts, retained_index)`。`matrix_df` 為
        排除違規列後的乾淨輸入矩陣（不含任何 `NaN`）；`exclusion_counts`
        為逐項排除計數的字典——`"segment_mismatch"` 鍵記錄因
        `split_segment` 不符被排除的列數，其餘鍵為各欄位名稱，記錄該欄
        含 `NaN` 而被排除的列數，供證據 JSON 稽核。

    Raises:
        MetaInputContractError: `oof_df` 含任何不在允許清單內的欄位；
            `oof_df` 缺少 `regime_cols` 允許清單中的任一欄（2026-09-15
            補件——允許清單是「該有的都要有」，不是「有就用、沒有就
            跳過」）；機率欄不是恰為 `EXPECTED_MODEL_NAMES` 四模型、
            且每個模型的類別欄集合彼此不一致（2026-09-15 補件，缺一欄
            即代表資料不完整，不得默默少算一個模型或一個類別）。
    """
    if regime_cols is None:
        from .baseline_models import META_REGIME_FEATURE_COLS
        regime_cols = META_REGIME_FEATURE_COLS

    disallowed = [
        c for c in oof_df.columns
        if c not in OOF_METADATA_COLS
        and c not in regime_cols
        and not _PROB_COL_PATTERN.match(c)
    ]
    if disallowed:
        raise MetaInputContractError(
            f"欄位不在允許清單內（OOF 機率欄 ∪ META_REGIME_FEATURE_COLS）："
            f"{disallowed}")

    # P1（2026-09-15 補件）：regime_cols 是允許清單，不是「有就用、沒有
    # 就跳過」——缺任一欄即代表 Meta-Learner 少看了一個市場機制特徵，
    # 必須拒絕，不能默默用較窄的矩陣繼續跑。
    missing_regime = [c for c in regime_cols if c not in oof_df.columns]
    if missing_regime:
        raise MetaInputContractError(
            f"缺少 META_REGIME_FEATURE_COLS 允許清單中的欄位：{missing_regime}")

    # P2（2026-09-15 補件）：機率欄必須恰為 EXPECTED_MODEL_NAMES 四模型、
    # 且每個模型的類別欄集合彼此一致——缺一欄（例如某模型少一個類別）
    # 代表資料不完整，不得默默用較窄的矩陣繼續跑。
    prob_cols = [c for c in oof_df.columns if _PROB_COL_PATTERN.match(c)]
    model_class_tokens: Dict[str, set] = {}
    for c in prob_cols:
        m = _PROB_COL_PATTERN.match(c)
        model = m.group(1)
        token = c[m.end():]
        model_class_tokens.setdefault(model, set()).add(token)

    model_set = set(model_class_tokens.keys())
    if model_set != EXPECTED_MODEL_NAMES:
        missing = EXPECTED_MODEL_NAMES - model_set
        extra = model_set - EXPECTED_MODEL_NAMES
        raise MetaInputContractError(
            f"機率欄的模型集合不完整：缺 {sorted(missing) or '無'}，"
            f"多出不認得的 {sorted(extra) or '無'}")

    token_sets = list(model_class_tokens.values())
    if any(s != token_sets[0] for s in token_sets[1:]):
        detail = {m: sorted(t) for m, t in model_class_tokens.items()}
        raise MetaInputContractError(
            f"各模型的機率欄類別集合不一致（可能有模型缺欄）：{detail}")

    # P6（2026-09-15 補件）：上面的一致性檢查只保證「四個模型彼此相同」，
    # 保證不了「與 target 真正的類別定義域相同」——四個模型一致地都缺
    # 同一類別欄時，彼此比對完全相同，測不出來。有傳 target_column 時
    # 才做這層額外核對（選用，不強制，因為某些呼叫情境可能真的只想核對
    # 跨模型一致性本身）。
    if target_column is not None:
        if target_column not in TARGET_CLASS_DOMAINS:
            raise MetaInputContractError(
                f"未知的 target_column: {target_column!r}（僅接受 "
                f"{sorted(TARGET_CLASS_DOMAINS)}）")
        expected_tokens = {
            _class_token(target_column, cls)
            for cls in TARGET_CLASS_DOMAINS[target_column]
        }
        actual_tokens = token_sets[0]
        if actual_tokens != expected_tokens:
            raise MetaInputContractError(
                f"機率欄的類別集合（{sorted(actual_tokens)}）與 "
                f"target_column={target_column!r} 的定義域"
                f"（{sorted(expected_tokens)}）不符——四個模型可能一致地"
                f"缺同一個類別欄，跨模型一致性檢查無法偵測此情況")

    matrix_cols = prob_cols + list(regime_cols)

    exclusion_counts: Dict[str, int] = {}

    segment_mask = oof_df["split_segment"] == segment
    n_segment_excluded = int((~segment_mask).sum())
    if n_segment_excluded:
        exclusion_counts["segment_mismatch"] = n_segment_excluded

    working = oof_df.loc[segment_mask, matrix_cols].copy()

    for col in matrix_cols:
        n_nan = int(working[col].isna().sum())
        if n_nan:
            exclusion_counts[col] = n_nan

    nan_mask = working.isna().any(axis=1)
    retained_index = working.index[~nan_mask]
    clean = working.loc[~nan_mask].reset_index(drop=True)

    if return_retained_index:
        return clean, exclusion_counts, retained_index
    return clean, exclusion_counts


# ==============================================================================
# iter_oof_folds
# ==============================================================================

def iter_oof_folds(splitter, panel: pd.DataFrame, holdout_start_date):
    """包裝 `WalkForwardSplitter.split()`，只產出**整折**測試窗完全落在
    Holdout 邊界之前的折——`test_end_date < holdout_start_date` 才產出，
    跨界的整折直接丟棄，不切半折（PO 2026-09-14 明確裁決）。Holdout 折
    的 Specialist 因此**從未被 `fit`／`predict`**——不是「訓練了但不用
    其輸出」，是訓練迴圈本身的折迭代範圍就不包含這些折。

    Args:
        splitter: `WalkForwardSplitter` 實例。
        panel: 傳給 `splitter.split()` 的面板 DataFrame。
        holdout_start_date: Holdout 邊界（含端點視為 Holdout）。

    Yields:
        與 `splitter.split()` 相同的 `(train_indices, test_indices,
        fold_metadata)` 三元組，僅限測試窗完全落在邊界之前的折。
    """
    boundary = pd.Timestamp(holdout_start_date)
    panel_reset = panel.reset_index(drop=True)

    for train_idx, test_idx, fold_metadata in splitter.split(panel_reset):
        test_dates = panel_reset.loc[test_idx, splitter.date_col]
        test_end_date = pd.Timestamp(test_dates.max())
        if test_end_date < boundary:
            yield train_idx, test_idx, fold_metadata
        # 刻意不在第一次跨界時 break——面板日期理論上應單調遞增，但用
        # continue（此處體現為單純不 yield）逐折檢查更穩健，不對輸入
        # 面板的日期排序做隱性假設。


def iter_holdout_folds(splitter, panel: pd.DataFrame, holdout_start_date):
    """`iter_oof_folds()` 的互補迭代器——只產出**整折**測試窗起點落在
    `holdout_start_date`（含）之後的折：`test_start_date >= boundary`
    才產出（`UG-G3-SB7` Gate A v2 訂正 1）。

    **v1 缺陷（審查方複核發現，不得重犯）**：v1 原設計用
    `test_end_date >= boundary` 當納入條件——`iter_oof_folds()` 的排除
    條件正是 `test_end_date >= boundary`，若本函式也用它當納入條件，
    會把跨界折（`test_start < boundary <= test_end`）**整個**納入
    Holdout，讓邊界之前的列混進 Holdout 評估。改用 `test_start_date`
    後，跨界折在兩個迭代器裡都不會被 yield——對跨界折達成一致排除，
    不是誤入其中一邊。

    Args:
        splitter: `WalkForwardSplitter` 實例。
        panel: 傳給 `splitter.split()` 的面板 DataFrame。
        holdout_start_date: Holdout 邊界（含端點視為 Holdout）。

    Yields:
        與 `splitter.split()` 相同的 `(train_indices, test_indices,
        fold_metadata)` 三元組，僅限測試窗起點落在邊界（含）之後的折。
    """
    boundary = pd.Timestamp(holdout_start_date)
    panel_reset = panel.reset_index(drop=True)

    for train_idx, test_idx, fold_metadata in splitter.split(panel_reset):
        test_dates = panel_reset.loc[test_idx, splitter.date_col]
        test_start_date = pd.Timestamp(test_dates.min())
        if test_start_date >= boundary:
            yield train_idx, test_idx, fold_metadata
