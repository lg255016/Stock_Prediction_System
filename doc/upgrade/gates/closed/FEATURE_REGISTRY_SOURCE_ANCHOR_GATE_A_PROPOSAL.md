# `FEATURE_REGISTRY.md` Source 欄改函式名稱錨點——Gate A 提案 v2

## 0. 摘要

> **v2 修訂**：依複核第一輪意見，(1) 第 12 列（`sentiment_mean`）從「已帶
> 函式名」組移到「需補函式名」組——它原本錨定的 `_fuse_sentiment` 是巢狀
> 閉包，不是穩定的頂層錨點，且該欄位的實際賦值行本來就在
> `generate_daily_features()` 內；(2) 錨定類別方法（`generate_daily_
> features()`／`generate_target_labels()`）的錨點補上類別名前綴
> `FeatureAggregator.`；(3) `Source` 欄改動範圍加入 CORE_16 四列（原提案
> 列為建議，v2 納入範圍）；(4) 新增 Decision 規則：錨點只准指向頂層函式或
> 類別方法，不得指向巢狀函式／閉包／lambda，需要標示實作細節時寫成錨點
> 外的括號散文備註。見 §2.2、§3.1、§3.2。
>
> **v2 計數訂正**：複核意見原文以「5＋10＝13」「13＋4＝17」描述本次改動
> 列數，但逐列列舉後實際為 (A) 5 列＋(B) 10 列＋(C) 4 列＝**19 列**（`5+10=15`
> `15+4=19`，非 13／17）。本提案採用逐列列舉後的實際數字，不採信摘要口徑的
> 加總結果——這是本次獨立複核發現的一處小算術落差，附帶揭露，不影響 §2.2
> 對照表本身（列舉內容雙方一致，只有加總數字需要訂正）。

`FEATURE_REGISTRY.md`（`UG-Gate-0` 已核准交付物）的 `Source` 欄以行號指向
`feature_aggregator.py`，15 處引用中 **14 處已經指到與該欄位完全無關的程式碼**
（§0.5 #38 唯讀查證），因為行號當錨點結構上保證會隨程式碼插入而漂移，且
`gate0_contract_check.py` 沒有任何一項檢查驗證這件事。PO 裁決採方案 (a)：
把 `Source` 欄改成 `<檔案>::<函式>()` 格式的函式名稱錨點，並在 contract-check
新增一項機械檢查（函式存在性），本提案為該規格變更的 Gate A。**本提案本身
不修改 `FEATURE_REGISTRY.md` 或 `gate0_contract_check.py` 任何一行**，核准後
才進紅測。

## 1. Requirement Source

- `PROJECT_STATUS.md` §0.5 #38（審查方唯讀查證發現，2026-09-20）
- PO 裁決訊息（本次開案，2026-09-20）：採方案 (a)，函式名稱錨點＋機械檢查
- `CLAUDE.md` §0.2 第 3 順位：`FEATURE_REGISTRY.md` 是 `UG-Gate-0` 已核准交付物，
  `Source` 欄格式屬規格變更，需獨立 Gate A 提案
- `CLAUDE.md` §9A.1／§9A.2：驗證必須為偵測而寫，且需附 known-FAIL 案例

## 2. Current State（唯讀查證，2026-09-20，容器內程式碼閱讀）

### 2.1 本文件已有兩列使用函式名稱錨點，且至今仍正確

`Source` 欄第 6 列（`label_reason`）與第 29 列（`target_triple_barrier`）：

```
由 `src/ml/triple_barrier.py::generate_triple_barrier_labels()` 寫入（UG-G3-SB1）
```

格式為 `<檔案>::<函式>()`，指向 `triple_barrier.py`（不是 `feature_aggregator.py`），
`UG-G3-SB1` 時期新增（2026-09-09），至今（2026-09-20）仍正確——**函式名不會因為
上方插入程式碼而失效，這正是行號會失效、函式名不會的直接對照組**。方案 (a)
是把本文件已經證明有效、且已在用的慣例，套用到還在用行號的那些列，不是
引進新格式。

### 2.2 需要改動的 19 列，逐列核對（`VERIFIED THIS SESSION`）

**縮排／性質核對（複核第二輪要求，七個錨點目標全數量過，`VERIFIED THIS
SESSION`）**：

| 位置 | 名稱 | 縮排 | 性質 |
|---|---|---|---|
| L233 | `compute_bullishness_index` | 0 | 頂層函式 |
| L247 | `compute_agreement_index` | 0 | 頂層函式 |
| L296 | `compute_rsi` | 0 | 頂層函式 |
| L325 | `compute_rolling_volatility` | 0 | 頂層函式 |
| L337 | `class FeatureAggregator:` | 0 | 類別定義 |
| L341 | `generate_daily_features` | 4 | `FeatureAggregator` 類別方法 |
| L1030 | `generate_target_labels` | 4 | `FeatureAggregator` 類別方法 |
| L536 | `_fuse_sentiment` | 20 | 巢狀閉包（定義於 `generate_daily_features()` 內部） |

三種穩定度：頂層函式（改名要考慮呼叫端）、類別方法（同樣是模組對外介面，
但需要類別名才能定位）、巢狀閉包（純實作細節，任何人重構時可直接內聯掉，
不需要跟任何人打招呼）——只有前兩種適合當受核准契約的追溯錨點，見 §3.1
新增的 Decision 規則。

**(A) 已帶函式名、只需刪除過期行號，錨定頂層函式（5 列）——函式皆已確認
存在**：

| # | 欄位 | 現行 Source 欄 | 改為 |
|---|---|---|---|
| 8 | `rsi_14` | `L142-168, compute_rsi()` | `feature_aggregator.py::compute_rsi()` |
| 9 | `volatility_5d` | `L171-180, compute_rolling_volatility()` | `feature_aggregator.py::compute_rolling_volatility()` |
| 10 | `volatility_20d` | 同上 | 同上 |
| 13 | `bullishness_index` | `L108-119, compute_bullishness_index()` | `feature_aggregator.py::compute_bullishness_index()` |
| 14 | `agreement_index` | `L122-139, compute_agreement_index()` | `feature_aggregator.py::compute_agreement_index()` |

**(B) 只有行號或錨定巢狀閉包、需補（或訂正）函式名，錨定 `FeatureAggregator`
類別方法（10 列）——以「賦值行所屬方法」逐一判定，賦值行號已重新獨立核對
（`VERIFIED THIS SESSION`）**：

| # | 欄位 | 現行 | 賦值行（獨立核對） | 改為 |
|---|---|---|---|---|
| 7 | `return_1d` | `L398-400` | 701：`df_features['return_1d'] = df_features.groupby('stock_id')['close_price'] \` | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` |
| 11 | `article_count` | `L333` | 548：`merged_sent['article_count'] = merged_sent['direct_count'] + merged_sent['theme_count']` | 同上 |
| **12** | **`sentiment_mean`** | `L321-332, _fuse_sentiment()` | **547：`merged_sent['sentiment_mean'] = merged_sent.apply(_fuse_sentiment, axis=1).astype(float)`** | `feature_aggregator.py::FeatureAggregator.generate_daily_features()`（融合規則在其內的 `_fuse_sentiment` 閉包，見 §5.5） |
| 15 | `sentiment_3d_ma` | `L414-415` | 801：`df_features['sentiment_3d_ma'] = df_features.groupby('stock_id')['sentiment_mean'] \` | 同上 |
| 16 | `sentiment_5d_ma` | `L416-417` | 803：同上句型（window=5） | 同上 |
| 17 | `sentiment_lag_1` | `L420` | 824：`df_features['sentiment_lag_1'] = _lag1.where(` | 同上 |
| 18 | `sentiment_lag_2` | `L421` | 826：`df_features['sentiment_lag_2'] = _lag2.where(` | 同上 |
| 26 | `target_next_close` | `L459` | 1056：`df_res['target_next_close'] = df_res.groupby('stock_id')['close_price'].shift(-1)` | `feature_aggregator.py::FeatureAggregator.generate_target_labels()` |
| 27 | `target_return_1d` | `L462-464` | 1059：`df_res['target_return_1d'] = np.log(` | 同上 |
| 28 | `target_up_down` | `L1064-1065`（#38 剛訂正，現為正確行號） | 1064（同一行） | `feature_aggregator.py::FeatureAggregator.generate_target_labels()`——**與 #38 的訂正結果不同**：即使行號現在正確，仍改為函式名，理由見下 |

**第 12 列的處置（複核第二輪訂正，取代 v1 把它放在 (A) 組的判斷）**：
`_fuse_sentiment` 是 20 格縮排、每次呼叫 `generate_daily_features()` 都重新
定義的巢狀閉包，不具備頂層函式或類別方法的穩定性契約——把受核准契約的
追溯指標綁在這種東西上，等於把行號問題換一種形式重現（失效觸發條件從
「插入程式碼」變成「重構閉包」）。且 `sentiment_mean` 的**實際賦值**不在
閉包裡（閉包只算融合規則），而在 L547 的 `generate_daily_features()` 內——
按 (B) 組「賦值行所屬方法」的同一把尺，第 12 列本來就該歸類到 (B) 組。
`_fuse_sentiment` 改寫成錨點**之外**的括號散文備註，不參與機械檢查抽取
（見 §3.2 正則規格）。

**第 28 列的處置**：PO 裁決「雖然行號正確，仍要一併改成函式名錨點，否則會
留下一列格式不一致的例外，下一個人不知道該遵循哪一種」——本提案採納此裁決，
列入變更範圍，不因為它「現在恰好是對的」就排除在外。

**(C) CORE_16 四列（19–22，v2 由「建議」納入範圍）——現行只有檔名，無行號
無函式名，錨定 `generate_daily_features()`**：

| # | 欄位 | 現行 | 賦值方式（獨立核對） | 改為 |
|---|---|---|---|---|
| 19 | `amplitude_ratio` | `feature_aggregator.py`（UG-G2-SB8 已實作） | L738：`df_features['amplitude_ratio'] = (` — 字面欄名直接賦值 | `feature_aggregator.py::FeatureAggregator.generate_daily_features()` |
| 20 | `ma5_bias_ratio` | 同上 | **L754 迴圈**：`for _win, _col in ((5, 'ma5_bias_ratio'), (20, 'ma20_bias_ratio')): ... df_features[_col] = _bias.where(~_warmup, 0.0)` — 透過迴圈變數 `_col` 賦值，**不是字面欄名** | 同上 |
| 21 | `ma20_bias_ratio` | 同上 | 同一迴圈，`_col` 第二次疊代取值 `'ma20_bias_ratio'` | 同上 |
| 22 | `volume_ratio_5d` | 同上 | L786：`df_features['volume_ratio_5d'] = _vol_ratio.where(~_warmup_vol, 1.0)` — 字面欄名直接賦值 | 同上 |

`ma5_bias_ratio`／`ma20_bias_ratio` 透過迴圈變數賦值這件事，只影響「機械
檢查要不要進一步驗證欄名字面出現」這個問題（§3.2 已決定不做這件事），
不影響「該欄位是否確實由 `generate_daily_features()` 賦值」這個事實判斷
本身——兩者是不同層次的問題，本提案只處理前者（`Source` 欄該寫什麼）。

**(D) 不動的列**：1–4（指向 `stock_prices` 資料庫欄本身，非程式碼錨點）、
5（敘述性條目）、6／29（已是正確格式，不動）、23–25（標記「待實作」，
沒有函式可指，維持現狀）。

**本次改動總計 19 列**：(A) 5 列＋(B) 10 列＋(C) 4 列。

## 3. 設計提案

### 3.1 `Source` 欄格式

統一為 `<相對路徑檔名>::<函式或方法名>()`，類別方法額外標註類別名：
`<相對路徑檔名>::<類別名>.<方法名>()`，例：`feature_aggregator.py::compute_
rsi()`（頂層函式）、`feature_aggregator.py::FeatureAggregator.generate_
daily_features()`（類別方法）。**既有第 6／29 列**（`generate_triple_
barrier_labels()`）**維持原樣不動**——它指向的是 `triple_barrier.py`
的頂層函式（複核第二輪已核對 `L14` 無縮排），不是類別方法，本來就不需要
類別名前綴，v2 不因為新規則而回頭改這兩列。

**Decision 新規則（複核第二輪要求，本案真正的產出，不只是格式統一）**：
**錨點只准指向頂層函式或類別方法，不得指向巢狀函式、閉包或 lambda。**
需要標示實作細節（例如「融合規則在某個巢狀函式裡」）時寫成錨點**之外**
的括號散文備註，不進錨點本身。理由見 §2.2 第 12 列的處置與下方 §3.2
的正則規格——`grep`／`def <名稱>(` 這類存在性檢查不管縮排，結構上無法
分辨「頂層函式」與「巢狀閉包」，**檢查在這一點上是盲的，只能靠這條規則
在源頭堵住**，這個分工本身要留在 Decision 的理由欄，不能只放在提案裡。

### 3.2 `gate0_contract_check.py` 新增機械檢查（B 系列，暫編號 B15，
最終編號依提案核准時的最新序號重新核對，不假設中間沒有其他變動）

**檢查內容**：

1. 掃描 `FEATURE_REGISTRY.md` 的 `Source` 欄，用正則抽出**反引號內**、
   符合 `<檔案>::<名稱>()` 或 `<檔案>::<類別名>.<方法名>()` 形式的錨點。
   **只抽取反引號 code span 內的內容**——錨點後面若有括號散文備註（例：
   第 12 列的「（融合規則在其內的 `_fuse_sentiment` 閉包，見 §5.5）」），
   那段文字在反引號**之外**，正則不得跨出反引號邊界去抽取，備註裡出現的
   `_fuse_sentiment` 不參與本檢查。
2. 對每一個抽到的錨點：確認 `<檔案>` 在 repo 內存在；把 `::` 右側依最後一個
   `.` 切開，**取最後一段（`.` 之後、`()` 之前的部分）當函式／方法名**，
   類別名（`.` 之前的部分，若有）**當作可選前綴，不參與存在性判斷**——
   即只檢查該檔案內是否存在 `def <方法名>(`（正則允許前導縮排，天然涵蓋
   模組層級函式與類別方法，這也是為什麼本檢查結構上驗不出「函式在哪個
   類別裡」，見 §3.3 的盲區延伸說明）。
3. 任一條件不成立即 FAIL，列出是哪一列（欄位名）、哪個錨點字串、缺的是
   檔案還是函式。

**刻意不做的事**（§9A.1 意義下的範圍界定，不是偷懶）：

- 不驗證「函式內是否真的賦值了那個欄位名」。理由：(C) 組的 `ma5_bias_
  ratio`／`ma20_bias_ratio` 透過迴圈變數 `_col` 間接賦值，字面搜尋欄位
  名字串在函式原始碼裡找不到，若檢查驗到這一層會對合法寫法誤報 FAIL。
  行號漂移的成因是「插入程式碼使行號位移」，函式名稱錨點會失效的成因是
  「函式被改名或刪除」——本檢查瞄準後者，範圍寫窄但確實會 FAIL，不是
  寫寬然後靠不驗證來避免誤報。
- 不驗證「類別名前綴是否與函式實際所屬的類別相符」（例如錨點寫成
  `WrongClass.generate_daily_features()` 也會 PASS，只要 `generate_daily_
  features` 這個名字本身存在於檔案裡）。這是 §3.1 規則（只准頂層函式或
  類別方法）換來的直接副作用：把類別名放在可選前綴、只驗方法名，才能用
  同一條正則同時涵蓋 (A) 組的頂層函式與 (B)(C) 組的類別方法，代價是類別
  名本身不受檢查保護。與 §3.1 新規則（人工紀律：不得指向巢狀函式）合起來
  看，這是「機械檢查負責存在性、人工規則負責錨點該指向哪一層」的分工，
  不是遺漏。

### 3.3 已知的檢查盲區（誠實揭露，不在本案範圍內解決）

若函式簽章不變但整個函式邏輯被替換、或欄位被賦值到錯誤的變數上，本檢查
測不出來——它只驗證「錨點指到的函式存在」，不驗證「函式做的事符合文件
描述」。這與行號漂移是不同類型的問題（行號漂移是「連指都指錯地方」，這裡
是「指的地方對，但內容可能不符」），本案的範圍是修前者。

## 4. Tests（先紅後綠，紅 FAIL 數＝新增測試數）

紅測目標：對**現行未修改的** `FEATURE_REGISTRY.md` 執行新檢查，預期結果需要
在提案核准後、寫紅測前**先確認一次**，而非假設——PO 訊息已指出這點，紅測
撰寫時第一步就是這個確認：

```bash
python scripts/verify/gate0_contract_check.py
```

**預期推演（待紅測時以真實執行結果為準，不得逕行採信此處推演）**：現行
`FEATURE_REGISTRY.md` 只有第 6／29 兩列已是 `<檔案>::<函式>()` 格式，其餘
19 列尚未改。新檢查若只掃描「已符合 `<檔案>::<函式>()` 格式」的錨點做驗證，
現行文件會是 **PASS**（因為只有 2 列符合格式可供檢查，且這 2 列本身正確）——
這種結果代表檢查對「其餘 19 列還沒改」這件事沒有偵測力，是 PO 提醒的
「如果是 PASS 就代表檢查寫得沒有偵測力，要重新設計」的情況。

**因應設計**：紅測不能只驗證「新檢查邏輯本身正確」，還要驗證「新檢查+
現行文件」的組合行為有意義。具體作法：

1. **測項 1**：新檢查函式本身的單元測試——對一個構造出的假 `FEATURE_
   REGISTRY.md`（或直接測試被抽出的檢查函式，傳入字串內容）：合法錨點
   （檔案與函式皆存在）→ PASS；檔案不存在 → FAIL 附正確訊息；函式不存在
   → FAIL 附正確訊息。
2. **測項 2**（複核第二輪新增）：類別方法錨點 `<檔案>::<類別名>.<方法名>()`
   的解析——`<類別名>` 前綴須被正確剝除、只取 `<方法名>` 去比對，且**故意
   把類別名寫錯**（如 `WrongClass.generate_daily_features()`）仍應 PASS
   （§3.2 已決定不驗類別名，見該節說明），確認實作沒有偷偷加上未經提案
   核准的類別名驗證。
3. **測項 3**（複核第二輪新增）：括號散文備註不參與抽取——構造一列 Source
   欄為 `` `feature_aggregator.py::FeatureAggregator.generate_daily_
   features()`（見 `_fuse_sentiment`，見 §5.5） ``，斷言檢查只抽到反引號
   內的錨點，**不會**誤把備註裡的 `_fuse_sentiment` 當成另一個要驗證的
   函式名（若誤抽，會對這個實際不存在對應頂層引用的名字產生不該有的
   FAIL 或誤判）。
4. **測項 4**（known-FAIL 主案，`CLAUDE.md` §9A.2 強制）：在 `/tmp` 副本上
   把 `compute_rsi` 改名（例如改成 `compute_rsi_v2`，不動真實檔案），對這份
   副本執行檢查邏輯，斷言 FAIL 且訊息指名 `compute_rsi` 缺席。**不對真實
   `feature_aggregator.py` 做任何暫時修改**，全程在 `/tmp` 副本上進行，
   比照 §0.5 #31＋#33 那輪的記憶體內突變測試慣例。
5. **測項 5**：實作完成、`FEATURE_REGISTRY.md` 19 列皆已改為函式／方法名
   錨點後，對**真實檔案**執行 `gate0_contract_check.py`，確認新檢查 PASS
   且涵蓋 21 個錨點（19 個新改＋既有 2 個），不是只涵蓋新增的 19 個。

## 5. Affected Components

- `doc/upgrade/contracts/FEATURE_REGISTRY.md`（19 列 `Source` 欄，見 §2.2
  (A)(B)(C) 三組）
- `scripts/verify/gate0_contract_check.py`（新增機械檢查）
- 對應的 contract-check 測試（若該腳本有獨立測試檔，核准後查證並列入；
  若無獨立測試檔，機械檢查本身即以腳本執行結果為證據，比照既有 B 系列
  慣例）

**不改**：`FEATURE_REGISTRY.md` 的欄位定義、編號、NULL 策略、契約版本、
`DOC_PATHS`（本案不搬檔案）；`feature_aggregator.py` 的任何函式名稱或邏輯
（文件跟隨程式碼，不反過來）。

## 6. Definition of Done

- 21 個 `Source` 欄錨點（含既有 2 個、新改 19 個）皆為 `<檔案>::<函式>()`
  或 `<檔案>::<類別名>.<方法名>()` 格式，逐一核對於 `postgres`@
  `localhost:5432`（若涉及）或直接對原始碼（本案不涉及資料庫，指名
  「對 `src/transform/feature_aggregator.py` 與 `src/ml/triple_barrier.py`
  原始碼」）
- `gate0_contract_check.py` 新檢查對修改後的 `FEATURE_REGISTRY.md` PASS
- known-FAIL 案例（測項 4）已實際執行並確認 FAIL，復原後 `git diff --stat`
  乾淨
- 全套測試無回歸
- `DOCUMENT_DRIFT_REMEDIATION.md` `DRIFT-035` 的「另兩列留待下次」註記
  已結清（本案落地後這兩列已包含在 (B) 組內一併修正）
- `DECISIONS.md` 新增 ADR，記錄「錨點只准指向頂層函式或類別方法」這條規則
  （§3.1）與其理由（機械檢查對巢狀函式是結構性盲區，只能靠人工規則堵住）

## 7. 流程

本提案送 `sps_project_reviewer` 複核，複核通過後請 PO 核准，核准後才進紅測
（「紅測寫完先回報」慣例不變）。核准範圍僅限本提案 §2.2 列出的 19 列、
§3.1 的新增 Decision 規則、與 §3.2 的機械檢查設計（含類別名可選前綴、
括號備註不參與抽取兩項規格）；(C) 組迴圈變數賦值的處置方式（§2.2 (C) 揭露）
留待 PO 複核時一併確認是否
需要在 Decision 裡特別寫明，或維持本提案的處置（一併列入、不特別標註）。
