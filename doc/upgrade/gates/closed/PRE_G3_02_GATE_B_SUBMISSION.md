# `PRE-G3-02` Gate B 送審 —— 結案

- 日期：2026-09-08
- 涵蓋：覆蓋率門檻提案（D1~D5 裁決）+ 逐標的覆蓋率量測 + `RISK-015` 收案
- 性質：**結案文件**，回顧性彙整既有已 commit 的工作

---

## 0. 一句話

**RISK-015 不是被一個百分比門檻關閉的 —— 它帶著四個真實數字進 Gate 3，
由 D3 的預測力對照決定「夠不夠」，這就是它的收案形式。**

---

## 1. 完整 commit 序列

| commit | 內容 |
|---|---|
| `74b89df` | `PRE_G3_02_INPUTS.md` 輸入打包（含 `PRE-G3-01` 報告三處更正） |
| `5bfb3b8` | **覆蓋率門檻提案**（D1~D5 裁決）—— 空集合的平均數不是 0.5 |
| `4ddfcc6` | `PRE_G3_02_INPUTS.md` 收錄 `PRE-G3-03` 段 A 執行結果（八點命中率、404 窮盡範圍、拒寫史） |
| `898f9b0` | `PRE_G3_02_INPUTS.md` 同步匯入完成狀態 |
| `00a21f6` | **逐標的覆蓋率量測**（匯入後回補完整重算） |
| `e6a5bf4` | **`RISK-015` 收案登記** —— 帶著數字進 Gate 3 |

---

## 2. D1~D5 裁決摘要（`5bfb3b8` 全文為權威，本表僅索引）

| # | 決策點 | 裁決 |
|---|---|---|
| **D1** | `min_train_size` | 不填一個數字——併入 `PROJECT_STATUS.md` §0.5 #16 已登錄的三件事（rolling/expanding、embargo、覆寫值），Gate 3 啟動前一次解決 |
| **D2** | 3 年 vs 120 交易日下界 | **不是二選一**：3 年維持契約權威（Gate 0 交付物，改需 ADR）；120 日記為算術下界（「低於它一定不行」，非「到了它就夠」） |
| **D3** | 覆蓋率門檻的錨 | **預測力對照**（有／無情緒特徵的 walk-forward 對照）—— 與 (B) 總經詞裁決同一把尺，不雙標 |
| **D4** | 不過門檻標的的處理 | **NULL + 原生處理 NaN 的模型**（非「加指標欄保留全部模型」）—— 依 PO 原則：特徵要對應現實，模型不適用就換模型 |
| **D5** | 空日 `sentiment_mean` NULL 化 | 空日應為 NULL（成因 U），非 `0.5`；§5A.2 補 U 分支——**落地執行見 `PRE-G3-04`（另案，Gate A 已核准、尚未動工）** |

⚠ **本檔撰寫時的兩處自我更正**（`5bfb3b8` §9 完整記錄，不重寫）：
`RandomForest` 是否收 NaN 的錯誤宣稱（實測後更正，四模型僅 1 個真正出局）；
`min_train_size` 誤寫成「空格」（實為 `time_series_split.py:94` 已推導，
且 `PROJECT_STATUS.md` §0.5 #16 早於本提案登錄——**兩個錯都朝著支持自己
建議的方向，非隨機**）。

---

## 3. 逐標的覆蓋率量測（`00a21f6`）

**方法**：直接呼叫生產函式 `DBWriter.fetch_all_for_features()` +
`FeatureAggregator.generate_daily_features()`（與 `main_etl_pipeline.py:544-557`
生產路徑逐行相同），不自行重寫合併邏輯，未寫回資料庫。窗口
2026-01-17~2026-09-06（`PRE-G3-03` 回補實際涵蓋區間）。

| 標的 | 窗口內交易日 | 有覆蓋日數 | 覆蓋率 |
|---|---|---|---|
| 2330 | 146 | 126 | **86.30%** |
| 2382 | 146 | 33 | **22.60%** |
| 6488 | 144 | 12 | **8.33%** |
| NVDA | 159 | 91 | **57.23%** |

原始逐月分佈：`evidence/PRE_G3_02_coverage_measurement.json`（權威在此，
不重複複製）。

**與 D2 兩個門檻對照**：價格深度（`PRE-G3-03` 已確立）四檔皆超過 120 日
與 3 年門檻（NVDA 754 接近但未過 756，差 2 日）；**情緒覆蓋深度**（本次量測）
僅 2330（126）超過 120 日下界，其餘三檔未過——**此為量測結果的陳述，
不是「夠不夠」的結論**（那是 D3 的範圍）。

---

## 4. `RISK-015` 收案（`e6a5bf4`）

證據標籤 `HYPOTHESIS` → `OBSERVED`（2026-09-07）。**風險不關閉，轉為 Gate 3
的一個實驗問題**——收案形式是「覆蓋率如實登記 → 進 Gate 3 → 由 D3 的
預測力對照給出答案」，理由鏈三點（空日可訓練使覆蓋率不決定面板大小；
D4 低覆蓋標的不剔除；D3 門檻錨定預測力對照）已完整寫入
`REMAINING_RISKS.md` RISK-015 條目，本檔不重複。

**補充資料源（Dcard／新聞）刻意延後**：先用 2330 的 86.3% 驗證情緒特徵
有無預測力，若最好的覆蓋下都量不出訊號，補到 86% 也不會有。

---

## 5. 證據標籤表

| 宣稱 | 標籤 | 可重跑指令 / 依據 |
|---|---|---|
| D1~D5 裁決內容 | `PREVIOUSLY VERIFIED`（PO 裁決本身不可重跑，記錄於 `5bfb3b8`） | 讀取 commit 全文 |
| Fold 算術下界 120 日、交叉驗證 §0.5 #16 的 34 折 | `VERIFIED THIS SESSION`（撰寫當時） | `⌊(N-80)/20⌋+1` 公式代入 N=740 得 34，與 §0.5 #16 實測相符 |
| RF 接受 NaN、LR 不接受 | `VERIFIED THIS SESSION` | 容器內 sklearn 1.9.0 實測（`5bfb3b8` §9.1） |
| 四檔覆蓋率四個數字 | `VERIFIED THIS SESSION` | `evidence/PRE_G3_02_coverage_measurement.json`；`python _coverage.py`（腳本未進版控，邏輯即 `DBWriter.fetch_all_for_features + FeatureAggregator.generate_daily_features`） |
| 2382 題材溢出量化證據（33 trading-day > 24 direct-only calendar-day） | `VERIFIED THIS SESSION` | 輕量交叉核對，`00a21f6` commit message 附原始查詢 |

---

## 6. 未驗證清單（有名字、有去處）

| # | 項目 | 現況 | 去處 |
|---|---|---|---|
| 1 | **D3 預測力對照未跑**（有／無情緒特徵的 walk-forward 對照） | 門檻錨定機制已裁決，**尚未執行** | Gate 3 第一個實驗；需先完成 `PRE-G3-04` 的全量重算 |
| 2 | **`min_train_size` 三件事未解**（D1） | 併入 `PROJECT_STATUS.md` §0.5 #16 | Gate 3 啟動前 |
| 3 | **NVDA 754<756 邊界情況** | 差 2 個交易日，未裁決如何處理 | Gate 3 設計時 |
| 4 | **`failed_source_keys=None` 的量測限制** | 本次量測未區分 `SOURCE_FAILED`，因歷史回補資料無對應即時 `etl_run_log` | 已於 `PRE_G3_02_COVERAGE_MEASUREMENT_REPORT.md` §0 揭露，屬量測範圍限制非缺陷 |
| 5 | **`daily_ml_features` 未重算**（仍 137 列，未反映 D5 語意與完整回補） | `PRE-G3-04` Gate A 已核准、尚未動工 | 待 `PRE-G3-04` 完成 |

---

## 7. 裁決索引

| 裁決 | 裁決者 | commit |
|---|---|---|
| D1~D5 全部五項 | PO 2026-09-07 | `5bfb3b8` |
| RISK-015 收案形式（帶數字進 Gate 3，非訂門檻） | PO 2026-09-07 | `e6a5bf4` |
| 補充源延後 | PO 2026-09-07，理由：把不可逆支出排在可逆判斷之後（DP2 同一原則第三次適用） | `e6a5bf4` |

---

## 8. `DOC_PATHS` 檢查

已核對，`PRE-G3-02` 的搬移文件（`PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md`、
`PRE_G3_02_COVERAGE_MEASUREMENT_REPORT.md`、`PRE_G3_02_INPUTS.md`）皆不在
`gate0_contract_check.py` 的 `DOC_PATHS` 清單內，本次搬移無需同步。

`PRE_G3_02_INPUTS.md` 是否因後續引用需留在根層：**已查證**（`grep` 全文）
僅被 `PRE-G3-02` 自己的兩份姊妹文件引用（`COVERAGE_MEASUREMENT_REPORT.md`、
`COVERAGE_THRESHOLD_PROPOSAL.md`），無跨 SB 引用——**三份一併移入 `closed/`，
不留例外**。

---

## 9. 結案聲明

`PRE-G3-02`（覆蓋率門檻提案 + 量測 + `RISK-015` 收案）已完成。
**根層三份文件隨本次結案 commit 一併移入 `closed/`。**

> **程序揭露**：結案 commit 先於 PO 核准執行（成因：交辦訊息合併時遺失順序行）；
> PO 於 2026-09-08 審閱複查結果後追認。
