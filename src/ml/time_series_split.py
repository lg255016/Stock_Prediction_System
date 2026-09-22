import logging
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class WalkForwardSplitter:
    """
    金融時序滾動前向交叉驗證切分器 (Walk-Forward Cross Validation Splitter)。
    
    核心特性：
    1. 嚴格遵守時間之箭（Arrow of Time）：確保所有訓練集時間戳記嚴格小於測試集時間戳記。
    2. 全域交易日對齊（Global Date Alignment）：按唯一交易日（Unique Trading Dates）切分，
       保證多股票（Multi-Stock）在同一個 Fold 內共享相同的時序邊界，杜絕跨股票時間偏誤。
    3. 支援雙模式（Dual Mode）：
       - 'rolling'（滾動窗口）：固定訓練天數，隨時間向前平移。
       - 'expanding'（擴展窗口）：固定起點，隨時間逐步累積全部歷史數據。
    4. 零前視偏誤防護（Zero Look-ahead Bias）：自動驗證各 Fold 訓練集與測試集索引無交集；
       並以 Purge（依 label_end_date 移除訓練集中與測試集標籤重疊的列）與
       Embargo（依 embargo_days 排除前一 Fold 測試窗結束後的訓練候選天數）
       防止標籤邊界洩漏（見 `doc/upgrade/contracts/PURGED_WALK_FORWARD_SPEC.md`）。
       Purge 優先採用 df 中逐列的 `label_end_date` 欄位（例如
       `FeatureAggregator.generate_target_labels()` 產出，依個股自身交易日曆計算，
       可正確處理停牌等造成個股曆與全域曆不同步的情形）；欄位不存在時退回以
       全域唯一交易日索引 + label_horizon 反推的近似值（見 split() docstring 的精度限制）。
    """

    def __init__(
        self,
        train_window_size: int = 60,
        test_window_size: int = 20,
        step_size: Optional[int] = None,
        mode: str = "rolling",
        min_train_size: Optional[int] = None,
        date_col: str = "trade_date",
        label_horizon: int = 1,
        embargo_days: int = 0,
        label_end_date_col: str = "label_end_date",
        require_label_end_date: bool = False
    ):
        """
        初始化 Walk-Forward 時序切分器。

        Args:
            train_window_size: 訓練窗口交易日天數 (預設 60 交易日，約 1 季)
            test_window_size: 測試/評估窗口交易日天數 (預設 20 交易日，約 1 個月)
            step_size: 每次向前平移之交易日天數 (若為 None 則預設為 test_window_size，無縫銜接)
            mode: 切分模式 ('rolling' 滾動窗口 或 'expanding' 擴展窗口)
            min_train_size: Purge 後最小可接受訓練天數 (若為 None，預設為
                train_window_size - label_horizon，即容許正常 Purge 造成的縮減，
                但不容許 Purge/Embargo 疊加造成的額外縮減)
            date_col: 交易日期欄位名稱 (預設 'trade_date')
            label_horizon: 標籤依賴的未來交易日數 (預設 1，對應現行 T+1 標籤)。
                用於 Purge：移除訓練集中 label_end_date = trade_date[T + label_horizon]
                落在測試集開始日期（含）之後的天數。傳入 0 停用 Purge。
            embargo_days: 測試窗結束後應排除的訓練候選交易日數 (預設 0，
                嚴格單向 Walk-Forward 合法值；見 PURGED_WALK_FORWARD_SPEC.md §2.4)
            label_end_date_col: 逐列 label_end_date 欄位名稱 (預設 'label_end_date')。
                若 df 含此欄位，Purge 直接採用逐列真實值（正確處理個股停牌等
                日曆不對齊情形）；欄位不存在時退回全域交易日索引近似法。
            require_label_end_date: 為 True 時，`label_end_date_col` 指定
                欄名不存在於傳入的 `df` 即拋 `KeyError`，**拒絕**落入近似
                fallback（`UG-G3-SB3`，PO 2026-09-12 核准）。預設 `False`，
                維持既有呼叫端（依賴 fallback）的既有行為不變——本參數
                刻意設計成「選擇性收緊」，不是全面禁止 fallback：fallback
                本身仍保留給刻意選擇它的既有呼叫端。無論本參數為何，
                `split()` 產出的每個 Fold 之 `fold_metadata` 皆含
                `purge_mode`（`"exact"` 或 `"approximate"`），誠實回報
                該次切分實際走了哪條路徑。
        """
        if train_window_size <= 0:
            raise ValueError(f"train_window_size 必須大於 0，收到: {train_window_size}")
        if test_window_size <= 0:
            raise ValueError(f"test_window_size 必須大於 0，收到: {test_window_size}")

        mode = mode.lower()
        if mode not in ("rolling", "expanding"):
            raise ValueError(f"mode 必須為 'rolling' 或 'expanding'，收到: {mode}")

        self.train_window_size = int(train_window_size)
        self.test_window_size = int(test_window_size)
        self.step_size = int(step_size) if step_size is not None else self.test_window_size
        if self.step_size <= 0:
            raise ValueError(f"step_size 必須大於 0，收到: {self.step_size}")

        self.mode = mode

        if label_horizon < 0:
            raise ValueError(f"label_horizon 不得為負數，收到: {label_horizon}")
        self.label_horizon = int(label_horizon)

        if embargo_days < 0:
            raise ValueError(f"embargo_days 不得為負數，收到: {embargo_days}")
        self.embargo_days = int(embargo_days)

        if min_train_size is not None:
            self.min_train_size = int(min_train_size)
        else:
            # 預設容許 Purge 造成的正常縮減 (train_window_size - label_horizon)，
            # 但不容許 Purge/Embargo 疊加造成的額外縮減。
            self.min_train_size = max(1, self.train_window_size - self.label_horizon)
        if self.min_train_size <= 0:
            raise ValueError(f"min_train_size 必須大於 0，收到: {self.min_train_size}")

        self.date_col = str(date_col)
        self.label_end_date_col = str(label_end_date_col)
        self.require_label_end_date = bool(require_label_end_date)

    def _extract_sorted_unique_dates(self, df: pd.DataFrame) -> List[Any]:
        """從 DataFrame 抽取並遞增排序的唯一交易日期清單"""
        if df is None or df.empty:
            return []
        if self.date_col not in df.columns:
            raise KeyError(f"DataFrame 缺少指定的日期欄位: '{self.date_col}'")

        # 轉為字串或原生日期並排序
        unique_dates = df[self.date_col].dropna().unique()
        sorted_dates = sorted(unique_dates)
        return sorted_dates

    def get_n_splits(self, df: pd.DataFrame) -> int:
        """
        計算在給定 DataFrame 下、依訓練/測試窗口大小可產生的 Fold 數量上界。

        注意：本方法僅計算窗口是否「排得下」，不考慮 Purge/Embargo 造成的
        訓練集縮減。若 Purge 後訓練天數低於 min_train_size，`split()` 會跳過
        該 Fold 並記錄警告 —— 屆時 `split()` 實際產出的 Fold 數可能小於本方法回傳值。
        """
        unique_dates = self._extract_sorted_unique_dates(df)
        n_dates = len(unique_dates)

        if n_dates < (self.train_window_size + self.test_window_size):
            return 0

        # 計算能夠切出多少個完整的 (train, test) 組合
        n_splits = 0
        start_idx = 0
        while True:
            test_start = start_idx + self.train_window_size
            test_end = test_start + self.test_window_size
            if test_end > n_dates:
                break
            n_splits += 1
            start_idx += self.step_size

        return n_splits

    @staticmethod
    def assert_no_boundary_leakage(
        train_label_end_dates: List[Any],
        test_start_date: Any,
        fold_idx: Optional[int] = None
    ) -> None:
        """
        核心斷言 (PURGED_WALK_FORWARD_SPEC.md §2.6)：
        max(train.label_end_date) < min(test.trade_date)

        Args:
            train_label_end_dates: 訓練集各列的 label_end_date（可含 None/NaT，代表
                該列標籤依賴的未來日期超出資料集範圍，不計入比較）
            test_start_date: 該 Fold 測試集最小交易日
            fold_idx: 供錯誤訊息標明 Fold 編號 (可省略)

        Raises:
            RuntimeError: 若任何訓練列的 label_end_date >= test_start_date
        """
        valid_dates = [d for d in train_label_end_dates if d is not None and not pd.isna(d)]
        if not valid_dates:
            return

        max_train_label_end = max(valid_dates)
        if max_train_label_end >= test_start_date:
            fold_desc = "" if fold_idx is None else f" (Fold {fold_idx})"
            raise RuntimeError(
                f"Purge 邊界洩漏{fold_desc}：train label_end_date "
                f"({max_train_label_end}) >= test_start_date ({test_start_date})"
            )

    def split(
        self,
        df: pd.DataFrame
    ) -> Generator[Tuple[np.ndarray, np.ndarray, Dict[str, Any]], None, None]:
        """
        執行時序前向滾動切分生成器。

        Args:
            df: 包含特徵與 trade_date 欄位的特徵矩陣 DataFrame。若含
                `label_end_date_col`（預設 'label_end_date'）欄位，Purge 會逐列採用該
                真實值；否則以全域唯一交易日索引 + label_horizon 反推近似值。

        Purge 精度限制（無 label_end_date 欄位時的 fallback 路徑）：
            近似法假設 df 中所有列共享同一份全域交易日曆（即同一 trade_date 的所有列，
            其 label_end_date 皆等於該全域交易日索引 + label_horizon 對應的日期）。
            若面板內個別股票存在停牌等造成其自身交易日曆與全域曆不同步的情形，
            該股在停牌期間之後的 label_end_date 實際上會比近似值更晚，
            近似法可能低估應被 Purge 的列、導致殘留邊界洩漏。
            **建議一律透過 `FeatureAggregator.generate_target_labels()` 提供
            逐列 label_end_date 欄位，取得精確結果；fallback 僅供該欄位缺席時的
            最低限度防護，不應作為正式驗收依據。**

        Yields:
            Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
                - train_indices: 訓練集在 df 中的整數列索引 (np.ndarray)，已套用 Purge/Embargo
                - test_indices: 測試集在 df 中的整數列索引 (np.ndarray)
                - fold_metadata: 該 Fold 的時序元資料字典 (含日期區間、天數、樣本數、
                  Purge/Embargo 統計)
        """
        if df is None or df.empty:
            return

        unique_dates = self._extract_sorted_unique_dates(df)
        n_dates = len(unique_dates)
        n_splits = self.get_n_splits(df)

        if n_splits == 0:
            logger.warning(
                f"[WalkForwardSplitter] 唯一交易日數 ({n_dates}) 不足 "
                f"train ({self.train_window_size}) + test ({self.test_window_size})，無法生成任何 Fold。"
            )
            return

        # 日期 -> 全域索引位置 (用於 Purge/Embargo 的交易日計算)
        date_to_gidx: Dict[Any, int] = {d: i for i, d in enumerate(unique_dates)}

        # 預先建立 日期 -> DataFrame 整數列索引 的倒排索引映射 (極速 O(1) 查找)
        date_to_indices: Dict[Any, np.ndarray] = {}
        # 確保以 reset_index 基準取整數位置
        df_reset = df.reset_index(drop=True)
        for date_val, group in df_reset.groupby(self.date_col, sort=False):
            date_to_indices[date_val] = group.index.to_numpy(dtype=np.int64)

        # Purge 精確路徑：df 是否含逐列 label_end_date 欄位 (見 split() docstring)
        has_label_end_date_col = self.label_end_date_col in df_reset.columns
        if self.require_label_end_date and not has_label_end_date_col:
            raise KeyError(
                f"label_end_date_col='{self.label_end_date_col}' 不存在於傳入的 df，"
                "且 require_label_end_date=True——拒絕落入近似 Purge fallback。"
                "呼叫端需先確保逐列 label_end_date 欄位存在（見 __init__ 參數說明）。"
            )
        label_end_series = df_reset[self.label_end_date_col] if has_label_end_date_col else None

        # 記錄先前 Fold 的 (test_end_gidx, embargo_end_gidx]，供後續 Fold 的 Embargo 排除
        embargoed_ranges: List[Tuple[int, int]] = []

        fold_idx = 0
        start_idx = 0

        while True:
            test_start = start_idx + self.train_window_size
            test_end = test_start + self.test_window_size

            if test_end > n_dates:
                break

            # 決定訓練與測試日期區間 (Purge/Embargo 之前)
            if self.mode == "rolling":
                train_dates = list(unique_dates[start_idx:test_start])
            else:  # expanding
                train_dates = list(unique_dates[0:test_start])

            test_dates = unique_dates[test_start:test_end]
            test_start_date = test_dates[0]
            test_end_date = test_dates[-1]
            test_end_gidx = date_to_gidx[test_end_date]

            # 嚴格斷言：時序不交叉 (窗口本身的基本時間順序，先於 Purge/Embargo 檢查)
            max_train_date = train_dates[-1]
            min_test_date = test_start_date
            if max_train_date >= min_test_date:
                raise RuntimeError(
                    f"時序交錯異常！Fold {fold_idx}: Train 最大日 ({max_train_date}) >= Test 最小日 ({min_test_date})"
                )

            # --- Embargo: 排除先前 Fold 測試窗結束後 embargo_days 天內的訓練候選日 ---
            purged_by_embargo = 0
            if self.embargo_days > 0 and embargoed_ranges:
                kept = []
                for d in train_dates:
                    gidx = date_to_gidx[d]
                    if any(lo < gidx <= hi for lo, hi in embargoed_ranges):
                        purged_by_embargo += 1
                    else:
                        kept.append(d)
                train_dates = kept

            # 提取 Embargo 後的候選訓練列索引與測試列索引
            train_idx_list = [date_to_indices[d] for d in train_dates if d in date_to_indices]
            test_idx_list = [date_to_indices[d] for d in test_dates if d in date_to_indices]
            candidate_train_indices = (
                np.concatenate(train_idx_list) if train_idx_list else np.empty(0, dtype=np.int64)
            )
            test_indices = np.concatenate(test_idx_list) if test_idx_list else np.empty(0, dtype=np.int64)

            # --- Purge: 逐列移除 label_end_date >= test_start_date 的訓練候選列 ---
            if self.label_horizon > 0 and len(candidate_train_indices) > 0:
                if has_label_end_date_col:
                    # 精確路徑：逐列真實 label_end_date（依個股自身交易日曆）。
                    # 缺值 (NaT，代表該股尚無足夠未來資料驗證安全性) 保守視為需 Purge。
                    row_label_ends = label_end_series.iloc[candidate_train_indices].tolist()
                    purge_flags = [
                        (v is None) or pd.isna(v) or (v >= test_start_date)
                        for v in row_label_ends
                    ]
                else:
                    # 近似路徑：全域交易日索引 + label_horizon 反推 (見 split() docstring 精度限制)
                    row_dates = df_reset[self.date_col].iloc[candidate_train_indices].tolist()
                    purge_flags = [
                        (date_to_gidx[d] + self.label_horizon) >= test_start
                        for d in row_dates
                    ]
                purge_mask = np.array(purge_flags, dtype=bool)
                purged_indices = candidate_train_indices[purge_mask]
                train_indices = candidate_train_indices[~purge_mask]
            else:
                purged_indices = np.empty(0, dtype=np.int64)
                train_indices = candidate_train_indices

            purged_samples = int(len(purged_indices))
            purged_dates_set = (
                set(df_reset[self.date_col].iloc[purged_indices].tolist()) if purged_samples else set()
            )
            purged_days = len(purged_dates_set)

            surviving_dates = (
                sorted(set(df_reset[self.date_col].iloc[train_indices].tolist()))
                if len(train_indices) else []
            )
            train_days = len(surviving_dates)

            if train_days < self.min_train_size:
                logger.warning(
                    f"[WalkForwardSplitter] Fold {fold_idx} Purge/Embargo 後訓練天數 ({train_days}) "
                    f"低於 min_train_size ({self.min_train_size})，跳過此 Fold。"
                    f"依 RISK-001 接受邊界，不縮小 Purge 範圍或放寬 label_end_date 判定以保留 Fold。"
                )
                if self.embargo_days > 0:
                    embargo_end_gidx = min(test_end_gidx + self.embargo_days, n_dates - 1)
                    embargoed_ranges.append((test_end_gidx, embargo_end_gidx))
                fold_idx += 1
                start_idx += self.step_size
                continue

            # 核心斷言：max(train.label_end_date) < min(test.trade_date)
            # (Purge 已保證此條件，此處為防禦性重驗，符合 CLAUDE.md §9A 之防呆設計原則)
            if self.label_horizon > 0:
                if has_label_end_date_col:
                    train_label_end_dates = label_end_series.iloc[train_indices].tolist()
                else:
                    train_label_end_dates = [
                        unique_dates[date_to_gidx[d] + self.label_horizon]
                        if date_to_gidx[d] + self.label_horizon < n_dates else None
                        for d in df_reset[self.date_col].iloc[train_indices].tolist()
                    ]
            else:
                train_label_end_dates = []
            self.assert_no_boundary_leakage(train_label_end_dates, test_start_date, fold_idx)

            # 嚴格斷言：索引零交集
            intersection = np.intersect1d(train_indices, test_indices)
            if len(intersection) > 0:
                raise RuntimeError(
                    f"訓練集與測試集索引發生洩漏重疊！重疊筆數: {len(intersection)}"
                )

            metadata: Dict[str, Any] = {
                "fold": fold_idx,
                "mode": self.mode,
                "label_horizon": self.label_horizon,
                "embargo_days": self.embargo_days,
                "train_start_date": surviving_dates[0],
                "train_end_date": surviving_dates[-1],
                "test_start_date": test_dates[0],
                "test_end_date": test_dates[-1],
                "train_days": train_days,
                "test_days": len(test_dates),
                "train_samples": len(train_indices),
                "test_samples": len(test_indices),
                "purged_days": purged_days,
                "purged_samples": purged_samples,
                "embargoed_days": purged_by_embargo,
                "purge_mode": "exact" if has_label_end_date_col else "approximate",
            }

            yield train_indices, test_indices, metadata

            if self.embargo_days > 0:
                embargo_end_gidx = min(test_end_gidx + self.embargo_days, n_dates - 1)
                embargoed_ranges.append((test_end_gidx, embargo_end_gidx))

            fold_idx += 1
            start_idx += self.step_size
