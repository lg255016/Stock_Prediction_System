# RESEARCH_REQUIREMENTS.md — 金融研究轉譯與特徵工程需求規格書

> **文件定位**：本文件依據 `doc/research/股價與情緒關聯研究.pdf` 深度研究報告，將行為金融學（Behavioral Finance）與社群輿情量化之學術理論，轉譯為具體的機器學習特徵工程（Feature Engineering）與模型驗證規格。
> 本文件為 Phase 3 機器學習模型訓練之**特徵工程單一真實規格來源（Feature Single Source of Truth）**。

---

## 1. 理論基礎與文獻溯源 (Theoretical Foundations)

本系統之核心假說建立於三大現代金融學與計算社會科學研究之上：

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                      三大核心金融理論基石                                │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. DSSW (1990) 雜訊交易者模型 (Noise Trader Risk Model)                  │
│    • 套利限制 (Limits to Arbitrage)：理性套利者承擔基本面與雜訊雙重風險   │
│    • 散戶非理性情緒形成系統性定價偏誤，導致短期股價偏離內在價值             │
│                                                                         │
│ 2. Antweiler & Frank (2004) 論壇情緒量化模型 (Journal of Finance)       │
│    • 分析 150 萬篇股票論壇訊息，證實發文量顯著預測市場波動性 (Volatility) │
│    • 首創「看多指數 (Bullishness)」與「一致性指數 (Agreement)」量化公式   │
│                                                                         │
│ 3. Bollen, Mao & Zeng (2011) 社群情緒預測模型 (J. of Comput. Science)   │
│    • 證實社群情緒維度可提前 3 到 4 日預測指數漲跌方向 (Directional Accuracy)│
│    • 格蘭傑因果檢定 (Granger Causality)：情緒對股價具顯著領先因果關係     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.1 台灣股市結構特性 (Taiwan Market Nuance)
- **散戶成交比重高**：台股散戶成交佔比長期維持在 55% 至 65%，為典型的「散戶主導型市場（Retail-dominated Market）」，雜訊交易者效應格外顯著。
- **PTT Stock 板之指標性**：批踢踢股板（Stock）是台灣最大、討論密度最高的散戶聚集地，具備即時發酵、高群體極化（Polarization）與顯著的羊群效應（Herding Behavior）。

---

## 2. 特徵工程需求清單 (Feature Engineering Requirements: RES-001 ~ RES-007)

### RES-001: 看多指數 (Bullishness Index, $B_t$)
- **理論來源**：Antweiler & Frank (2004), Equation (1)
- **業務意義**：衡量社群輿情在特定交易日的多空相對懸殊強度。
- **數學定義**：
  $$B_t = \ln \left( \frac{1 + M_t^{\text{Pos}}}{1 + M_t^{\text{Neg}}} \right)$$
  - $M_t^{\text{Pos}}$：$T$ 日（經 Roll-Forward 歸併後）看多文章數（情緒分數 $s \ge 0.55$ 或標籤為正向）。
  - $M_t^{\text{Neg}}$：$T$ 日（經 Roll-Forward 歸併後）看空文章數（情緒分數 $s \le 0.45$ 或標籤為負向）。
  - **Laplace 平滑（+1 因子）**：分子分母均加 1，確保在零文章或單邊極端情況下不會產生 $\ln(0)$ 或除以零錯誤。
- **值域與詮釋**：
  - $B_t > 0$：多頭情緒佔優勢（$M_t^{\text{Pos}} > M_t^{\text{Neg}}$）。
  - $B_t = 0$：多空勢均力敵（$M_t^{\text{Pos}} = M_t^{\text{Neg}}$）或當日無討論（$M_t^{\text{Pos}} = M_t^{\text{Neg}} = 0$）。
  - $B_t < 0$：空頭情緒佔優勢（$M_t^{\text{Pos}} < M_t^{\text{Neg}}$）。

---

### RES-002: 一致性指數 (Agreement Index, $A_t$)
- **理論來源**：Antweiler & Frank (2004), Equation (2)
- **業務意義**：衡量社群討論的情緒共識度（Consensus vs. Dispersion）。高一致性代表群體觀點高度集中；低一致性代表多空意見強烈紛歧。
- **數學定義**：
  $$A_t = 1 - \sqrt{1 - \left( \frac{M_t^{\text{Pos}} - M_t^{\text{Neg}}}{M_t^{\text{Pos}} + M_t^{\text{Neg}}} \right)^2}$$
- **極端值與邊界處理**：
  - 若 $M_t^{\text{Pos}} + M_t^{\text{Neg}} = 0$（當日無有效多空文章）：定義 $A_t = 0.0$（無共識）。
  - 若全為看多文章（$M_t^{\text{Neg}} = 0, M_t^{\text{Pos}} > 0$）或全為看空文章（$M_t^{\text{Pos}} = 0, M_t^{\text{Neg}} > 0$）：比值為 $\pm 1 \implies A_t = 1 - \sqrt{1 - 1} = 1.0$（完全共識）。
  - 若多空文章數完全相等（$M_t^{\text{Pos}} = M_t^{\text{Neg}} > 0$）：比值為 $0 \implies A_t = 1 - \sqrt{1 - 0} = 0.0$（最大分歧）。
- **值域**：$A_t \in [0.0, 1.0]$。

---

### RES-003: 歷史對數報酬率與滯後報酬 (Historical Log Returns)
- **理論來源**：Campbell, Lo, and MacKinlay (1997) 金融時間序列計量經濟學
- **業務意義**：相較於百分比報酬，對數報酬率具備跨時間「可加性（Time Additivity）」與近似常態分佈特性，能有效消除價格尺度的非平穩性。
- **數學定義**：
  $$r_t = \ln \left( \frac{\text{Close}_t}{\text{Close}_{t-1}} \right)$$
  - 滯後特徵：$r_{t-1} = r_{t-1}, r_{t-2} = r_{t-2}$（過去第 1 天與第 2 天的已知歷史報酬）。
- **補值規則**：歷史初始第一天（無 $T-1$ 價位）補 $0.0$。

---

### RES-004: 相對強弱指標 (Relative Strength Index, RSI-14)
- **理論來源**：J. Welles Wilder Jr. (1978) 動能技術指標
- **業務意義**：衡量過去 14 個交易日內買方與賣方力量的消長，捕捉短期超買（Overbought, RSI > 70）與超賣（Oversold, RSI < 30）之均值回歸動能。
- **數學定義**：
  $$\Delta P_t = \text{Close}_t - \text{Close}_{t-1}$$
  $$\text{Gain}_t = \max(\Delta P_t, 0), \quad \text{Loss}_t = \max(-\Delta P_t, 0)$$
  $$\overline{\text{Gain}}_{t, 14} = \text{EMA}_{14}(\text{Gain}), \quad \overline{\text{Loss}}_{t, 14} = \text{EMA}_{14}(\text{Loss})$$
  $$\text{RS}_t = \frac{\overline{\text{Gain}}_{t, 14}}{\overline{\text{Loss}}_{t, 14}}, \quad \text{RSI}_{t, 14} = 100 - \frac{100}{1 + \text{RS}_t}$$
- **補值規則**：資料前 14 天因歷史長度不足，補中立基準值 $50.0$。

---

### RES-005: 滾動歷史波動率 (Rolling Volatility, 5D / 20D)
- **理論來源**：Antweiler & Frank (2004) 訊息量與波動度關聯假說
- **業務意義**：散戶情緒暴增往往伴隨股價波動度劇烈放大。以 5 日（週線）與 20 日（月線）的滾動標準差量化當前市場風險水平。
- **數學定義**：
  $$\sigma_{t, 5} = \text{std}(r_{t-4:t}) \times \sqrt{252}$$
  $$\sigma_{t, 20} = \text{std}(r_{t-19:t}) \times \sqrt{252}$$
  - 採年化波動率或日滾動標準差；$r_t$ 為歷史對數報酬率。
- **補值規則**：初始樣本不足時（`min_periods=2`），以可用樣本計算；完全無樣本時補 $0.0$。

---

### RES-006: 多期情緒滑動與滯後特徵 (Sentiment Lags & Rolling MAs)
- **理論來源**：Bollen et al. (2011) 情緒預測衰減期（Decay Profile）研究
- **業務意義**：散戶情緒對股價的影響並非瞬間結束，通常具備 1 到 5 天的持續發酵與動能衰退期。
- **特徵矩陣**：
  1. `sentiment_3d_ma`：過去 3 天平均情緒滾動均值。
  2. `sentiment_5d_ma`：過去 5 天平均情緒滾動均值。
  3. `sentiment_lag_1`：$T-1$ 日平均情緒。
  4. `sentiment_lag_2`：$T-2$ 日平均情緒。
  5. `sentiment_lag_3`：$T-3$ 日平均情緒。
  6. `sentiment_lag_5`：$T-5$ 日平均情緒。
- **補值規則**：缺乏前期資料時一律補中立分數 $0.5$。

---

### RES-007: 滾動前向驗證 (Walk-Forward Validation Protocol)
- **理論來源**：Pardo (2008) 交易系統設計與時間序列交叉驗證規範
- **核心禁令**：**嚴禁使用 K-Fold Random Split**（隨機切分會將未來資料混入訓練集，造成虛假高準確率）。
- **驗證規範**：
  - 採用前向滑動窗口（Expanding / Rolling Window Validation）：
    ```text
    Fold 1: [ Train: M1 -> M6 ] -> [ Test: M7 ]
    Fold 2: [ Train: M1 -> M7 ] -> [ Test: M8 ]
    Fold 3: [ Train: M1 -> M8 ] -> [ Test: M9 ]
    ```
  - 嚴格保證測試集時間點永遠在訓練集之後（$T_{\text{test}} > T_{\text{train}}$）。

---

## 3. 實作架構規範 (Implementation Architecture & Constraints)

### 3.1 零外部 C 編譯依賴（Zero Heavy Dependency）
- **規範**：所有指標（包含 RSI-14、波動率、EMA、Antweiler 公式）一律使用 **純 NumPy 與 Pandas 向量化運算** 實作。
- **理由**：避免引入 `TA-Lib` 等需要本機 C 編譯器（C/C++ Build Tools）的沉重第三方套件，確保跨 Windows、Dev Container、Linux CI/CD 的 100% 部署一致性與輕量化。

### 3.2 跨股票多維隔離（Multi-Stock Isolation）
- **規範**：所有滾動（`rolling`）、滯後（`shift`）、EMA 及差分運算，必須在 `groupby('stock_id')` 的分組脈絡下執行。
- **防護**：股票 A（如 2330）的歷史序列絕對不得溢出或污染股票 B（如 NVDA）的特徵矩陣。

### 3.3 零前視偏誤保護（Zero Look-ahead Guarantee）
- 特徵矩陣 $X_T$ 產出時，絕對不包含 $T+1$ 交易日的開高低收量與未來輿情。
- 預測標籤 $Y_T$ 由獨立函式 `generate_target_labels()` 生成，並將最後一個交易日標籤設為 `NaN`。

---

## 4. 特徵輸出資料契約 (Output Data Contract)

特徵聚合模組 `FeatureAggregator` 在 Gate 5 完成後，將輸出包含以下 18 項機構級特徵的標準 DataFrame：

| 欄位名稱 | 資料型態 | 特徵類別 | 描述與公式 |
|---|---|---|---|
| `trade_date` | `DATE` | 識別 | 交易日期 |
| `stock_id` | `VARCHAR` | 識別 | 標準股票代碼（如 2330, NVDA） |
| `open_price` | `NUMERIC` | 價量 | 當日開盤價 |
| `high_price` | `NUMERIC` | 價量 | 當日最高價 |
| `low_price` | `NUMERIC` | 價量 | 當日最低價 |
| `close_price` | `NUMERIC` | 價量 | 當日收盤價 |
| `volume` | `BIGINT` | 價量 | 當日成交量 |
| `return_1d` | `NUMERIC` | 動能 | 當日對數報酬率 $\ln(\text{Close}_T / \text{Close}_{T-1})$ |
| `rsi_14` | `NUMERIC` | 技術 | 14 日相對強弱指標 (0 到 100) |
| `volatility_5d` | `NUMERIC` | 風險 | 5 日滾動歷史波動率 |
| `volatility_20d` | `NUMERIC` | 風險 | 20 日滾動歷史波動率 |
| `article_count` | `INTEGER` | 輿情 | 當日聚合文章總數 |
| `sentiment_mean` | `NUMERIC` | 輿情 | 當日平均情緒分數 (0 到 1) |
| `bullishness_index` | `NUMERIC` | 輿情 | Antweiler 看多指數 $B_t = \ln(\frac{1+M^+}{1+M^-})$ |
| `agreement_index` | `NUMERIC` | 輿情 | Antweiler 一致性指數 $A_t$ (0 到 1) |
| `sentiment_3d_ma` | `NUMERIC` | 時序 | 3 日情緒移動平均 |
| `sentiment_5d_ma` | `NUMERIC` | 時序 | 5 日情緒移動平均 |
| `sentiment_lag_1` | `NUMERIC` | 時序 | $T-1$ 日情緒分數 |
| `sentiment_lag_2` | `NUMERIC` | 時序 | $T-2$ 日情緒分數 |

---

## 5. 追溯矩陣 (Traceability Matrix)

| 研究需求 ID | 文獻來源 | 責任模組 | 驗證測試檔案 |
|---|---|---|---|
| **RES-001** | Antweiler & Frank (2004) Eq. 1 | `FeatureAggregator` | `tests/test_research_features.py` |
| **RES-002** | Antweiler & Frank (2004) Eq. 2 | `FeatureAggregator` | `tests/test_research_features.py` |
| **RES-003** | Campbell et al. (1997) | `FeatureAggregator` | `tests/test_feature_aggregator_alignment.py` |
| **RES-004** | Wilder (1978) | `FeatureAggregator` | `tests/test_research_features.py` |
| **RES-005** | Antweiler & Frank (2004) | `FeatureAggregator` | `tests/test_research_features.py` |
| **RES-006** | Bollen et al. (2011) | `FeatureAggregator` | `tests/test_feature_aggregator_alignment.py` |
| **RES-007** | Pardo (2008) | `src/ml/` (Phase 3) | `tests/test_ml_validation.py` |
