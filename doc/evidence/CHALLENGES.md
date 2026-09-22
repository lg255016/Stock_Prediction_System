# CHALLENGES.md — 工程挑戰與問題解決紀錄 (Engineering Challenges & Problem-Solving Log)

> **文件使命**：本文件記錄系統在架構設計、資料管線、NLP 與機器學習特徵工程中遇到的重大技術難題。
> 每一筆紀錄均包含現象、根因排查、失敗嘗試、最終架構解法、驗證證據與面試亮點，展示深度的工程分析與除錯能力。

---

## 快速索引 (Challenges Index)

- [CHAL-001: NLP Checkpointing 斷點續傳「假成功」與資料永久遺失風險](#chal-001-nlp-checkpointing-斷點續傳假成功與資料永久遺失風險)
- [CHAL-002: Exact-Title 模糊情緒快取穿透與中立分數重複調用 LLM](#chal-002-exact-title-模糊情緒快取穿透與中立分數重複調用-llm)
- [CHAL-003: 軟刪除（Soft Delete）防 AI 熱門詞探索「死灰復燃」與類別竄改](#chal-003-軟刪除soft-delete防-ai-熱門詞探索死灰復燃與類別竄改)
- [CHAL-004: PTT 發文時間跨年年份穿越與週末社群情緒遺漏](#chal-004-ptt-發文時間跨年年份穿越與週末社群情緒遺漏)
- [CHAL-005: 機器學習時序特徵工程的致命前視偏誤（Zero Look-ahead Bias 防護）](#chal-005-機器學習時序特徵工程的致命前視偏誤zero-look-ahead-bias-防護)
- [CHAL-006: 機構級情緒指標與技術動能之純向量化實作（零 C 編譯依賴防護）](#chal-006-機構級情緒指標與技術動能之純向量化實作零-c-編譯依賴防護)
- [CHAL-007: Gemini API 429 Rate Limit 彈性重試與指數退避協議](#chal-007-gemini-api-429-rate-limit-彈性重試與指數退避協議)

---

## CHAL-001: NLP Checkpointing 斷點續傳「假成功」與資料永久遺失風險

- **關聯關卡 / 模組**：Gate 2 (G2-SB3) / `src/transform/nlp_processor.py`, `main_etl_pipeline.py`
- **關聯決策**：DEC-003

### 1. 現象與衝擊 (Symptom & Impact)
在初期實作中，當 Gemini LLM API 呼叫失敗（如 429 速率限制、網路逾時、JSON 解析失敗）時，NLP 模組會將失敗文章填入 fallback 預設值（0.5 中立分數），並直接回傳給上層 ETL。上層 Orchestrator 將此 DataFrame 視為「成功處理」並寫入資料庫推進 Checkpoint。
**致命衝擊**：文章一旦被賦予 0.5 並存入 DB，未來系統重啟時會將其視為「已處理文章」，導致未成功呼叫 LLM 的重要社群情緒被永久掩蓋，無法重新嘗試。

### 2. 根因排查 (Investigation & Root Cause)
- Checkpointing 設計混淆了「非預期錯誤（API 失敗）」與「有效的中立分數」。
- 缺乏 Transactional Checkpointing 概念，在整批資料未獲 100% 驗證前，就提早對記憶體 DataFrame 進行了突變（Mutation）。

### 3. 失敗嘗試與權衡 (Failed Attempts)
- *嘗試一：在 API 失敗時標記 `sentiment_score = NULL`*。缺點：DataFrame 內夾雜 NULL，下游聚合特徵時會引發大量 `NaN` 例外。
- *嘗試二：在 loop 內針對失敗單筆重試*。缺點：破壞 Batching 經濟效益，並可能引發 API 阻塞。

### 4. 最終解決方案 (Solution — Strict Transactional Checkpointing)
1. **嚴格不突變原則（No-Mutation Before Verification）**：在整批 JSON 回應通過全量 ID 映射、分數值域 $[0.0, 1.0]$ 與結構驗證前，絕對不修改 DataFrame 中的任何一行。
2. **失敗立即中斷**：遇到非預期錯誤（DB 失敗、SnowNLP 崩潰、Gemini 逾時）時立即拋出例外，終止當前批次，確保 Checkpoint 絕不前進。
3. **原子性寫入**：只有當快取寫入與文章分數更新全數成功時，才持久化寫入 DB。

### 5. 驗證證據 (Verification)
- 撰寫 `tests/test_nlp_checkpoint_semantics.py`（11 項測試），模擬無效 JSON、ID 缺失、分數越界與 DB 寫入失敗，確認 100% 阻斷 Checkpoint 推進。

### 6. 面試總結 (Lesson Learned)
> 「在分散式與批次 ETL 管線中，**『快速失敗（Fail Fast）』永遠優於『偽造成功（Silent Fallback）』**。未完成的工作絕不能被 Checkpoint 標記為完成。」

---

## CHAL-002: Exact-Title 模糊情緒快取穿透與中立分數重複調用 LLM

- **關聯關卡 / 模組**：Gate 2 (G2-SB2) / `src/transform/nlp_processor.py`
- **關聯決策**：DEC-003

### 1. 現象與衝擊 (Symptom & Impact)
系統設計以 `sentiment_cache` 資料表節省 Gemini API Token。但實測發現：當一篇文章標題經 LLM 判定為中立分數（如 0.50）並寫入快取後，下一次遇到相同標題時，系統因為分數仍落在模糊區間（$0.40 \le s \le 0.60$），竟再次發起 Gemini API 呼叫！
**衝擊**：快取機制形同虛設，浪費大量 API 額度與時間。

### 2. 根因排查 (Investigation & Root Cause)
- 快取判定邏輯直接綁定在「情緒分數是否在模糊區間」的條件分支內，混淆了**「快取鍵是否存在（Cache Membership）」**與**「分數數值（Score Value）」**。

### 3. 最終解決方案 (Solution — Exact-Title Cache Membership)
1. **快取責任前置**：在進入 SnowNLP 模糊篩選前，先以文章標題比對 `sentiment_cache`。
2. **鍵存在即命中（Key Exists == Cache Hit）**：只要 `title in cache_dict`，無論其分數是 0.0、0.5 還是 1.0，直接取用快取值，絕對不再呼叫 Gemini API。

### 4. 驗證證據 (Verification)
- 撰寫 `tests/test_nlp_cache_semantics.py`（8 項測試），驗證已快取的中立 0.50 分數重複輸入時，Gemini API 呼叫次數精確為 0。

### 5. 面試總結 (Lesson Learned)
> 「快取的本質是 **『計算結果的持久化重用』**。快取命中的判斷必須基於 Key 的存在性，絕不能受到 Value 內容的數值範圍干擾。」

---

## CHAL-003: 軟刪除（Soft Delete）防 AI 熱門詞探索「死灰復燃」與類別竄改

- **關聯關卡 / 模組**：Gate 3 (G3-SB1) / `src/loaders/db_writer.py`, `src/extractors/trend_discover.py`
- **關聯決策**：DEC-004

### 1. 現象與衝擊 (Symptom & Impact)
管理者手動將特定標的停用（例如將 `高端` 設為 `is_active = FALSE`，保留歷史資料血緣但不爬取）。然而當背景執行的 AI 熱門詞探索（`trend_discover.py`）從 PTT 再次發現「高端」熱門時，執行 `INSERT ... ON CONFLICT (keyword) DO UPDATE SET is_active = TRUE, category = 'ai_discovered'`，導致：
1. 已停用關鍵字被 AI 動態重新啟用（死灰復燃）。
2. 原始分類（如 `core_stock`）被錯誤竄改為 `ai_discovered`。

### 2. 根因排查 (Investigation & Root Cause)
- 寫入合約（Write Contract）未劃清「管理者生命週期控制」與「AI 自動擴充」的權限邊界。`ON CONFLICT DO UPDATE` 盲目覆蓋了所有欄位。

### 3. 最終解決方案 (Solution — Strict Lifecycle Write Contract)
1. **AI 探索採 Insert-only（`ON CONFLICT (keyword) DO NOTHING`）**：AI 只能新增「系統中完全不存在」的新詞。若關鍵字已存在（不論 active 為 TRUE 或 FALSE），AI 一律無權修改其狀態或分類。
2. **管理者停用採 Update-only（`UPDATE tracking_keywords SET is_active = FALSE WHERE keyword = %s`）**：停用操作僅修改生命週期狀態，絕不竄改其原始分類（Category）。

### 4. 驗證證據 (Verification)
- 撰寫 `tests/test_tracking_keyword_integrity.py`（15 項測試），驗證停用標的無法被 AI 復活、非 active 核心標的 category 永遠不變。

### 5. 面試總結 (Lesson Learned)
> 「在多 Agent 或自動化爬蟲協同系統中，**『寫入權限的邊界隔離』是維持資料一致性的關鍵**。AI 探索應作為探索者（Prober），而非決策者（Admin）。」

---

## CHAL-004: PTT 發文時間跨年年份穿越與週末社群情緒遺漏

- **關聯關卡 / 模組**：Gate 4 (G4-SB1) / `src/transform/data_cleaner.py`, `src/transform/feature_aggregator.py`
- **關聯決策**：DEC-005

### 1. 現象與衝擊 (Symptom & Impact)
1. **跨年年份穿越**：PTT 列表頁時間僅顯示 `MM/DD`（如 `12/31`）。若爬蟲於隔年 1 月初執行，直接補上執行年份 `2026-12-31`，導致文章時間穿越到未來 12 個月後！
2. **週末情緒遺漏**：股市週末休市（無 `stock_prices`）。若直接將文章日期 Left Join 交易日，週六與週日發酵的重磅輿情（如週末降息或突發戰爭）會因為沒有對應交易日而被全數拋棄（Drop）！

### 2. 根因排查 (Investigation & Root Cause)
- 日期時間解析缺乏參考時間上下文（Reference Time Context）。
- 忽略了金融市場「非交易日資訊會累積反應於次一開盤日」的經濟學規律。

### 3. 最終解決方案 (Solution — Smart Year Inference & Roll-Forward Mapping)
1. **智慧跨年年份推論**：在 `parse_ptt_datetime` 中引入 `reference_time`。當爬蟲在 1 月抓取到 12 月文章時（月差 $> 6$），自動推論其為前一年（`Year - 1`）。
2. **次一交易日歸併演算法（Roll-Forward Trading Day Mapping）**：
   - 建立有效交易日曆列表。
   - 採用 `bisect_left` 二分搜尋：若發文時間超過當日 Cutoff（15:30:00）或發布於休假日（週六、週日、國定連假），一律無損向後滾動歸併至下一個有效開盤日。
   - 週五盤後與週末文章全數累積至週一特徵列中！

### 4. 驗證證據 (Verification)
- 撰寫 `tests/test_time_alignment.py`（13 項測試），涵蓋跨年時間解析、週五盤後滾動、週六週日累積至週一、國定連假歸併驗證。

### 5. 面試總結 (Lesson Learned)
> 「金融時間序列對齊不能只做簡單的字串比對，必須理解市場運作規律。**『Roll-Forward 歸併』確保了重大週末事件的社群情緒 100% 被次日模型捕捉。**」

---

## CHAL-005: 機器學習時序特徵工程的致命前視偏誤（Zero Look-ahead Bias 防護）

- **關聯關卡 / 模組**：Gate 4 (G4-SB2) / `src/transform/feature_aggregator.py`
- **關聯決策**：DEC-005

### 1. 現象與衝擊 (Symptom & Impact)
若在特徵工程中，直接將當日所有文章與當日收盤價結合來預測當日表現，或者讓當日特徵包含盤後資訊（如 20:00 發文）卻假裝是在盤中做的預測，會產生嚴重的**前視偏誤（Look-ahead Bias / Data Leakage）**。
**衝擊**：回測時模型績效極佳，但一旦實盤推論立刻崩潰。

### 2. 最終解決方案 (Solution — Dual-Mode Cutoff & Label Decoupling)
1. **雙模式預測約定（Dual-Mode Prediction Convention）**：
   - **模式一（盤前即時反應，08:30 Cutoff）**：特徵僅取至 08:30 前文章，預測當日開盤與跳空。
   - **模式二（盤後動能延續，15:30 Cutoff）**：特徵取當日 15:30 前完整價量與文章，預測次一交易日（$T+1$）收盤報酬。
2. **特徵與目標嚴格解耦（$X_T$ vs $Y_T$）**：
   - $X_T$ 只包含 $T$ 日及以前已知特徵。
   - 預測目標 $Y_T = \ln(\text{Close}_{T+1} / \text{Close}_T)$。
   - **最後一個交易日目標強制為 `NaN`**（因為未來尚未發生）。
3. **多股票分組隔離**：所有時序滑動（Rolling MA、Lagged Features）嚴格在 `groupby('stock_id')` 內執行。

### 3. 驗證證據 (Verification — Future Data Mutation Test)
- 撰寫 `tests/test_feature_aggregator_alignment.py`：設計**未來資料篡改測試（Mutation Testing）**，劇烈修改 $T+1$ 與 $T+2$ 的股價與文章，驗證 $T$ 日的特徵矩陣數值完全沒有產生任何變動（100% 零洩漏證明）。

### 4. 面試總結 (Lesson Learned)
> 「時序機器學習的靈魂在於 **『嚴格遵守時間之箭』**。透過數學證明與篡改測試驗證零前視偏誤，是量化工程師最重要的職業操守。」

---

## CHAL-006: 機構級情緒指標與技術動能之純向量化實作（零 C 編譯依賴防護）

- **關聯關卡 / 模組**：Gate 5 (G5-SB1 / G5-SB2) / `src/transform/feature_aggregator.py`
- **關聯決策**：DEC-006

### 1. 現象與衝擊 (Symptom & Impact)
1. **外部編譯依賴脆弱性**：金融常用的技術指標庫（如 `TA-Lib`）底層依賴 C/C++ 二進位編譯，在 Windows、Dev Container 或 CI/CD 雲端環境安裝時極易因編譯器缺失而建置失敗。
2. **學術公式邊界崩潰**：Antweiler & Frank (2004) 看多指數 $B_t = \ln(M^{\text{Pos}} / M^{\text{Neg}})$ 在遇到「零看空文章」或「零討論日」時，會直接引發除以零或 $\ln(0)$ 數學崩潰。

### 2. 最終解決方案 (Solution — Pure Vectorized Mathematics & Laplace Smoothing)
1. **Laplace 平滑係數防護（RES-001）**：
   $$B_t = \ln \left( \frac{1 + M_t^{\text{Pos}}}{1 + M_t^{\text{Neg}}} \right)$$
   分子分母強制加 1，確保值域永遠平滑，零文章日精準收斂至 $0.0$。
2. **一致性指數有界防護（RES-002）**：
   $$A_t = 1 - \sqrt{1 - \left( \frac{M_t^{\text{Pos}} - M_t^{\text{Neg}}}{M_t^{\text{Pos}} + M_t^{\text{Neg}}} \right)^2}$$
   加入 `np.clip` 與分母為零判斷，嚴格保證值域落在 $[0.0, 1.0]$。
3. **純 NumPy / Pandas 向量化 RSI-14 與滾動年化波動率**：
   - 以純 Pandas `ewm(alpha=1/14)` 實作 Wilder's RSI，初期不足 14 天補中立值 $50.0$。
   - 以純向量化標準差乘上 $\sqrt{252}$ 實作滾動年化波動率。
   - **完全淘汰外部 C-Extension**，跨平台相容性達到 100%。

### 3. 驗證證據 (Verification)
- 撰寫 `tests/test_research_features.py`（6 項測試），全套 89 項測試執行時間僅需 **0.49 秒**。

### 4. 面試總結 (Lesson Learned)
> 「在工程選型上，**『高可攜性、輕量化純向量化實作』往往優於『引進龐大外部 C 編譯依賴』**。良好的數學邊界設計能讓系統在極端市場情境下依然堅如磐石。」

---

## CHAL-007: Gemini API 429 Rate Limit 彈性重試與指數退避協議

- **關聯關卡 / 模組**：Operational & UX Enhancement / `src/transform/nlp_processor.py`, `main_etl_pipeline.py`
- **關聯決策**：DEC-003, DEC-008

### 1. 現象與衝擊 (Symptom & Impact)
當每日排程（`scheduler.py`）自動執行時，PTT 爬蟲成功獲取數百篇最新文章，其中數十篇經 SnowNLP 初篩落在 $0.40 \le s \le 0.60$ 模糊區間且未曾建立快取。系統向 Google Gemini API 發出批次情緒評分請求時，遭遇 Google 免費層（Free Tier）對 Flash 模型嚴格的 5~15 RPM 請求上限，拋出：
```text
google.api_core.exceptions.ResourceExhausted: 429 You exceeded your current quota, please retry in 1.7s
```
**衝擊**：由於 `nlp_processor.py` 缺乏重試機制，排程任務直接在中途崩潰失敗，無法自動推進至特徵工程與資料庫寫入。

### 2. 根因排查 (Investigation & Root Cause)
- **暫態異常（Transient Fault）**：雲端 LLM API 的 Quota 限速是量化資料管線中極常見的短暫流量限制，通常在 1~3 秒冷卻後即可恢復。
- **無退避直接崩潰（Zero-Backoff Failure）**：原程式直接呼叫 `model.generate_content()`，在遇到短暫 429 限速時直接向外拋出異常，未做任何主動退避與重試。

### 3. 最終解決方案 (Solution — Zero-Dependency Exponential Backoff & Strict Error Boundary)
1. **智慧暫態例外判斷（Transient Fault Classifier）**：
   精準識別 `429`、`Quota`、`ResourceExhausted`、`503` 與網路逾時等暫態錯誤；若是語法或型態錯誤（如無效 JSON）則維持 Fail-Fast 立即中斷。
2. **純 Python 零外部依賴指數退避重試（Zero-Dependency Exponential Backoff）**：
   以 $\min(2^{\text{attempt}}, 16)$ 秒（2s ➔ 4s ➔ 8s ➔ 16s）進行最多 5 次自動退避重試，在 Google 免費配額冷卻（1.7s~3s）後自動無縫恢復計算，兼具 100% 跨平台可攜性。
3. **模型選型與呼叫間隔保護**：
   依 PRD 規範指定最新 `gemini-flash-latest`，並於每次呼叫後保留 4 秒冷卻保護時間。
4. **DEC-003 嚴格檢查點不變性（Strict Invariant Guarantee）**：
   若連續 5 次重試耗盡仍未成功，系統絕不標記假性成功，強制拋出顯式異常並拒絕推進 Checkpoint，確保資料庫零髒資料。

### 4. 驗證證據 (Verification — Full End-to-End Resilience Pipeline Test)
- 撰寫 `tests/test_nlp_resilience_e2e.py`（2 項測試）：
  * **端到端全流程驗證**：模擬「文章輸入 ➔ 遭遇 429 限速 ➔ 自動退避重試成功 ➔ 快取寫入 ➔ Checkpoint 推進 ➔ 18 欄位特徵工程 ➔ 7 欄位入庫」端到端無縫執行。

> 📌 **SB5 補充註記（UG-G1-SB5，2026-08-26，DRIFT-001／007／見 `doc/evidence/DECISIONS.md` DEC-022 總覽）**：
> 本行「18 欄位特徵工程」為舊契約數字，現行為 `LEGACY_17`（17 欄，見
> `doc/upgrade/contracts/FEATURE_REGISTRY.md`）。本檔案原未被 `DOCUMENT_DRIFT_REMEDIATION.md`
> 登錄為 DRIFT-001／007 的引用位置，本次對整個 `doc/evidence/` 完整 grep 後新發現，一併補上
> 旁註；原文保留不動。
  * **嚴格阻斷驗證**：模擬連續 5 次 429 失敗，驗證系統安全拋出異常、100% 不寫入偽造快取、不推進 Checkpoint。
- 全套 **136 項測試全數通過（136/136 PASS，耗時 1.43s）**。

### 5. 面試總結 (Lesson Learned)
> 「面對雲端 API 的配額限速（429 Rate Limit），**『指數退避自動重試（Exponential Backoff Retry）』是保障管線高可用性的防禦裝甲，而『重試耗盡後嚴格拒絕推進 Checkpoint』則是守護資料真實性的最後底線**。」

---

## CHAL-008: pre-commit hook 檢查 3（秘密檔案偵測）只看檔名，內容層 credential 靠人眼——第一次漏過

- **關聯關卡 / 模組**：`UG-G3-SB1` / `.githooks/pre-commit`（GOV-04 檢查 3）、`doc/upgrade/gates/evidence/UG_G3_SB1_ambiguous_ratio_report.json`
- **關聯決策**：GOV-04（pre-commit hook）、`CLAUDE.md` §11、§12.4

### 1. 現象與衝擊 (Symptom & Impact)
`UG_G3_SB1_ambiguous_ratio_report.json` 的 `rerun_instructions` 欄位為求「可重跑」，
把容器內實測用的完整連線指令原樣抄入，其中包含字面 `password=` 值（此處不
重複，本機開發環境的預設密碼字面值）。commit `ed6f38e` 順利通過 pre-commit hook 四項檢查
（含檢查 3「秘密檔案偵測」）並成功入庫，直到審查方複查證據檔內容時才發現。

**衝擊**：違反 `CLAUDE.md` §11「不要 commit API key、token、password 或其他
credential」，且**沒有「dev 預設值除外」的例外**——hook 本應是這條規則的機械化
防線（GOV-04），但這次它沒有攔下。

### 2. 根因排查 (Investigation & Root Cause)
- **檢查 3 的判準是檔名，不是內容**：`.githooks/pre-commit` 檢查 3 比對 staged
  檔案清單是否含 `.env`／`.env.*`（`.env.example` 除外）／`settings.local.json`／
  `*.pem`／`*.key`／`id_rsa*`——一份**檔名完全正常**的 `.json` 證據檔，無論內容寫了
  什麼字面密碼，都不在這個判準能看見的範圍內。
- **這不是 hook 故障，是設計範圍之外**：hook 從未宣稱要做內容層掃描；這次踩到的
  是「範圍邊界」而非「實作缺陷」——與 §9A.1「結構上不可能失敗的檢查」同一種
  形狀的反面教材：**檢查 3 對『檔名帶密碼』這件事有偵測能力，對『內容帶密碼』
  這件事結構上就看不見**，而回報方（含審查方複查前）都下意識假設它涵蓋了後者。
- **證據檔的性質放大了風險**：`doc/upgrade/gates/evidence/` 下的檔案為了「可重跑」
  刻意保留完整指令，這個目的本身會鼓勵貼上真實可執行的連線參數——與一般程式碼
  不同，證據檔的存在理由恰好與「不要留下可執行的憑證」的原則有摩擦。

### 3. 最終解決方案 (Solution)
- 本案：新 commit 修正該檔 `rerun_instructions`，連線參數改為讀容器既有環境變數
  （`POSTGRES_DB`／`POSTGRES_USER`／`POSTGRES_PASSWORD`），不在檔案內重複記錄
  字面值；歷史 commit（`ed6f38e`）**不改寫**——§11A 不對已入庫歷史做破壞性操作，
  且該值本身是本機 dev 預設值，PO 判定不需要撤銷歷史。
- **本案不修改 hook 本身**：把檢查 3 擴充為掃描 staged 內容的 `password=`／
  `api_key=`／`token=` 字樣屬獨立的機制變更（需要自己的 false-positive 評估與
  GOV 案授權），刻意不在本次順手做——同 §9A.1 的教訓：**做不好的機械化檢查，
  比沒有檢查更危險**（會讓人誤以為「內容層也被涵蓋了」）。

### 4. 驗證證據 (Verification)
- `git grep -n -E "password\s*=\s*['\"][^'\"]+['\"]"`（樣式比對，指令本身不含
  任何密碼字面值）：staged 狀態下重跑，見本 commit 回報中貼出的原始輸出。
- 訂正後的 `rerun_instructions` 已對照容器 `env | grep POSTGRES` 確認三個環境
  變數（`POSTGRES_DB`／`POSTGRES_USER`／`POSTGRES_PASSWORD`）存在，指令本身
  仍可重跑（不在此重複確認其字面值，以免又留下一份可比對出密碼的紀錄）。

### 5. 面試總結 (Lesson Learned)
> 「機械化檢查的可信度取決於**它的判準範圍是否被誠實理解**，而不是它有沒有在跑。
> 『秘密檔案偵測』這個名字容易讓人以為涵蓋了所有形式的秘密外洩，但一個看檔名的
> 檢查，對內容層的外洩結構上就是盲的——**發現這個盲點的不是機制本身，是人眼複查**，
> 這正是為什麼獨立複查（而非只信任自己或機制的回報）不可省略。」

### 6. 追記（2026-09-10）：本案自己的 grep 樣式也有盲點——引號外形式

`UG_G3_SB2_routing_real_db_write.json` 建立時，兩處字面密碼（`docker exec -e
PGPASSWORD=<值> …`、`docker run … -e POSTGRES_PASSWORD=<值> …`）逃過
了本案第 4 節列出的樣式：`git grep -n -E "password\s*=\s*['\"][^'\"]+['\"]"`。

**成因**：該樣式**要求值被引號包住**（`['"][^'"]+['"]`）。`PGPASSWORD=<值>`
與 `POSTGRES_PASSWORD=<值>` 是 shell 環境變數賦值，**不帶引號**，且欄位名稱
是**大寫**（樣式本身不分大小寫沒問題，但引號要求本身就把它濾掉了）——結構上
落在樣式的偵測範圍之外，跟 CHAL-008 原案「檢查 3 只看檔名」是同一種形狀的第二個
實例：**一個只看某種寫法的檢查，對其他寫法是盲的。**

**回報方複查時用的是同一個樣式**，因此也漏了同一批——這印證了本案第 5 節「發現
盲點的不是機制本身，是人眼複查」還需要再加一句：**人眼複查若拿著同一把有洞的
尺，一樣量不出洞在哪裡。**

**修正**：

1. 本案兩處字面密碼改為佔位符（`<依 .env>`、`<臨時值，容器已拆>`），新 commit
   修正，不改寫 `34bcc5f`（§11A，同本案第 3 節原則）。
2. **grep 樣式擴大**為 `git grep -n -i -E "pass(word)?\s*=\s*\S+"`——不分大小寫、
   不要求引號，`PGPASSWORD`／`POSTGRES_PASSWORD`／`password` 一網打盡。**結果必須
   逐行人眼判**，佔位符（`<…>`、`${…}`、`os.environ[...]`）才可放行——**不得**
   建立一條「含佔位符就自動排除」的過濾規則再套用，那只是把「樣式看不見」換成
   「規則自動濾掉」，同一種盲點換了個位置。
3. `.claude/skills/gate-submit/SKILL.md` 產出 3 追加一行：commit 前對新增／修改的
   證據檔內容跑上述擴大樣式，逐行確認零真實憑證或已說明為佔位符／拋棄式臨時值。
4. **機制層的修法（增加 hook 檢查 3 的內容掃描）另立 GOV 案，不在此案處理**——
   已知會撞到的合法例外（`DB_MIGRATION_PLAN.md` 文件範例、既有證據檔的拋棄式臨時
   值等）需要先定白名單機制，同 §9A.1 的教訓：**做不好的機械化檢查，比沒有檢查
   更危險。**

**本節初版（`655f740`）引述時再次寫出字面值，本 commit 改掉**——**描述一個外洩
時把外洩內容原樣抄進描述，就是第二次外洩**，CHAL-008 §1 已經犯過一次
（`581950a` 引述外洩內容時原樣抄出值，`32250d2` 才改掉）。四次都是同一個人用
同一雙眼睛判——這不是再提醒一次能解決的，機制層修法見上方第 4 點。

**後續（2026-09-10）：GOV-13 已上線（`cdac61b`），內容層改由 hook 機械攔截**——
本案第 4 點原本刻意排除的機制層修法，已提案（`81acb02`）並經 PO 核准為
`APPROVED`：`.githooks/pre-commit` 檢查 3 新增內容層判準（寬樣式 + `-i`，
白名單只認 `<…>` 佔位符，命中值印出前遮罩為 `***`），11 項情境驗證通過，
詳見 `doc/governance/GOV_013_PROPOSAL_secret_content_scan.md`。本案記載的
四次（現為五次，含本節初版）人眼複查失敗，往後同型疏漏改由機械檢查在
commit 前攔下，不再只依賴人眼。

**再後續（2026-09-22）：機械檢查上線後，同一個病灶換了兩個新形狀出現**——

1. **檢查本身對它剛好要擋的兩個真實案例是瞎的**：專案決定把 repo 改為
   public、回頭唯讀查證私有歷史時發現，已經公開的 2 個 commit
   （`docker-compose.yml` 的 YAML 賦值、`db_writer.py` 的 JSON 賦值）用的
   分隔符是 `:` 不是 `=`——GOV-13 的樣式 `pass(word)?\s*=\s*` 只認 `=`，
   對這兩種寫法結構上必然不會命中。修法見 `GOV-14`
   （`doc/governance/GOV_013_PROPOSAL_secret_content_scan.md` 附錄），
   `.githooks/pre-commit`：`PASS_PATTERN` 改認 `[:=]` 兩種分隔符。
2. **這是本案的第六次同型漏洞，第一次不是發生在 commit message，是發生在
   一份分析文件的草稿裡**：為了具體列出「哪些 commit 用了哪種寫法」而寫的
   Gate A 提案初版（`GIT_HISTORY_CREDENTIAL_PURGE_GATE_A_PROPOSAL.md`），
   把該預設值原樣寫了十幾處——複核時被 PO 抓到，全部改為 `<dev-default>`
   佔位符。證明這個病灶不限於「修 bug 時的 commit message」，任何回顧歷史
   事故的新文件都可能重演；GOV-14 的修法上線後，這類文件在 commit 前會被
   機械檢查本身攔下，不必再靠人眼第七次抓到。

**第三後續（2026-09-22 同日）：複核方獨立全 tree 掃描把第一版修法退回，
修好之後、機械檢查本身第一次真的把「第七次」攔下**——

1. **第一版修法本身不夠，複核方獨立掃描發現 48 筆假陽性**：`PASS_PATTERN`
   的 `(word)?` 可選讓單獨「pass」四字母也算命中，`E3_IS_A_FALSE_PASS`、
   `why_not_adjusting_to_pass` 這類把 PASS 當子字串的既有識別字、以及
   `os.environ["POSTGRES_PASSWORD"]` 這種讀值寫法全部被誤擋；白名單也只認
   `<` 開頭，漏掉 `$`／`os.environ`／`os.getenv`／`%(` 等合法值形狀。
   修法：鍵名樣式加前置邊界、只認完整 `password`／`[A-Z_]*PASSWORD`；白名單
   擴為五種前綴。詳見 `GOV_013_PROPOSAL_secret_content_scan.md` 附錄二。
2. **撰寫附錄二本身，被機械檢查自己攔下三次**——這次抓到的不是人眼，是
   `.githooks/pre-commit` 對本檔工作區 diff 的獨立模擬掃描：known-FAIL 表格
   裡示範「應被擋下」案例（A／B／E／G）原本寫的是看起來逼真的假密碼字串
   （如一段逼真的英數混合字串），文中描述 `docker-compose.yml` 沒有展開行的
   句子把鍵名與緊接的冒號寫在同一個反引號區塊裡、以及描述 evidence JSON
   拋棄式容器密碼修改的句子把舊字面值原樣寫出——三處都命中同一套樣式，
   改用既有的 `<非佔位符字面值>` 描述法（見 GOV-14 附錄一）或拆開反引號、
   改為敘述性文字才通過。**這是本案第七次同型漏洞，但這次連測試用的假字串
   都會被攔下**——機制沒有能力區分「示範一個假密碼長什麼樣子」與「真的洩漏
   一個密碼」，這是它該有的樣子（fail-closed，見 CLAUDE.md §9A.1），不是
   過度敏感；真正的教訓是**任何描述密碼形狀的新文字，寫完都要跑一次同一套
   掃描再送審**，不能假設「這次寫的是假的就安全」。
3. **第八次就發生在寫第七次紀錄的當下**：本節第 2 點的初稿在描述「鍵名與
   冒號寫在同一個反引號區塊裡」這個觸發形狀時，直接把那個形狀原樣打了
   一次，又被同一套獨立模擬掃描攔下——改為敘述「鍵名與緊接的冒號」才過。
   **連「正在寫一份記錄自己被攔下幾次的文件」都不能免疫**，這比前七次更
   直接地證明：防線是機制，不是「這次應該會小心」。
4. **第九次，PO 複核回饋要求 GOV_013 附錄補上「複核方多測的邊界案例」時**：
   描述複核方額外測出「鍵名字首大寫也會被擋下」這個結果的句子，把「字首
   大寫的鍵名＋緊鄰冒號」原樣寫進同一個反引號區塊，第三度被同一套獨立
   模擬掃描攔下——改為分開敘述鍵名與「緊鄰冒號」才過。九次裡有三次
   （第七、八、九次）都出在同一份文件的同一輪修訂裡，且全部發生在
   **描述這個檢查本身如何運作**的句子，不是描述任何其他外洩——**檢查
   的行為本身，現在是本專案裡最常誘發這個病灶的內容**，這點值得記著。

## CHAL-009: 一句沒做過反向查核的「惰性」宣稱，在文件裡長得跟查過的一樣

- **關聯關卡 / 模組**：`UG-G3-SB2` / `scripts/verify/ug_g3_sb2_backfill_entity_mapping.py`、`entity_mapping`、`tracking_keywords`
- **關聯決策**：`UG_G3_SB2_GATE_A_PROPOSAL.md` §5（路由補齊惰性宣稱）、`GATE3_STARTUP_APPLICATION.md` §4.2（宇宙接線三層分離設計）、RISK-022（四）

### 1. 現象與衝擊 (Symptom & Impact)
`entity_mapping` 路由補齊 457 筆真實庫寫入後，RISK-013 三項協議第 5 步「惰性驗證」
（寫入前後比對 `fetch_active_stock_targets()`）發現結果**由 4 筆變 8 筆**——新增
`2059`（川湖）／`2454`（聯發科）／`3008`（大立光）／`8069`（元太）。這與 Gate A 提案
§5 的明文宣稱矛盾：「路由列在補齊當下是惰性的……新增的 457 筆路由列在對應股票被
排入 `tracking_keywords` 之前完全不影響任何既有每日流程」。

**衝擊**：若當時直接信任這句宣稱、略過惰性驗證這一步，這次寫入會在無人察覺的情況下
把每日 ETL 的追蹤宇宙從 4 檔悄悄擴大到 8 檔，其中 3 檔（TWSE）會經 `run_twse_pipeline`
日常路徑寫入 `stock_prices`，搶在 `UG-G3-SB2a` 的價格基準政策定案之前——見 RISK-022（四）。

### 2. 根因排查 (Investigation & Root Cause)
- **宣稱本身有一個沒做過的反向查核**：「路由列要嘛惰性、要嘛等 `tracking_keywords`
  排入」這句話隱含一個前提——「新增路由的股票，其 keyword 目前都不在 active
  `tracking_keywords` 裡」。**這個前提從未被查證過**；真正的查法是一條 SQL：
  `新增 keyword 集合 ∩ tracking_keywords(is_active=TRUE)`。
- **反向查核的結果**：457 筆新路由中，keyword 已存在於 active `tracking_keywords`
  的恰 **4 筆**，全部 `category='ai_discovered'`（`updated_at` 2026-08-17～21，
  早於本 SB）——AI 熱門詞探索機制早就在追蹤這 4 個關鍵字並已抓下 161 篇文章
  （川湖 19／聯發科 100／大立光 22／元太 20），但因為當時沒有路由，這些文章一直
  是「抓了但接不到任何股票」的孤兒。路由一補上，`entity_mapping ⋈
  tracking_keywords(is_active=TRUE)` 就立刻多解出這 4 檔——**不是新增了什麼，
  是修好了一個原本就存在的接不上的缺口，只是這個缺口平時看不出來**。
- **與 §9A.1 同型**：一個沒有做過反向查核的宣稱，在文件裡跟一個查過的宣稱長得一模
  一樣——兩者都只是一段肯定語氣的文字。**能區分兩者的唯一方式，是真的去查一次
  反例**，而這正是 known-FAIL 判準（§9A.1／§9A.2）在「宣稱」而非「檢查」上的
  同一個道理：沒有反向查核的宣稱，產出的不是結論，是結論的外觀。
- **審查方也照單接受了**：Gate A 提案審查時，這句「惰性」宣稱被列為「本子項可以
  安全獨立動手的前提」而通過，**審查當時同樣沒有要求反向查核**——說明這不是單一
  個人的疏漏，是流程本身沒有把「宣稱需要反向查核」變成一個會被檢查的步驟。

### 3. 最終解決方案 (Solution)
- **本案**：PO 裁決接受寫入、不回滾——457 筆資料本身正確，回滾不會讓這 4 個
  active AI 詞與 161 篇孤兒文章消失，下次任何形式的路由補齊都會再撞到同一件事；
  「AI 探索詞 → 路由 → 追蹤宇宙」正是 Gate 3 §4.2 三層分離設計的本意，不是缺陷。
  訂正的是**提案 §5 的宣稱本身**：改為區分「keyword 尚未進入 active
  `tracking_keywords`」（惰性成立）與「keyword 已在 active `tracking_keywords`」
  （立即生效，本次 4 檔），並附上反向查核 SQL 與結果（4／0）。
- **登記閘門**：`UG-G3-SB2a` 基準政策定案前，不執行每日 ETL（見 RISK-022（四）），
  防止新擴大的 3 檔 TWSE 股經舊路徑（未還原基準）寫入 `stock_prices`。
- **保留步驟 5（惰性驗證）作為所有路由變更的固定步驟**——這正是抓到本案的機制，
  不因為這次「查了才發現宣稱是錯的」而在下次省略；反而更確立它不可省略。
- **不修改的部分**：`fetch_active_stock_targets()`、`check_keyword_collisions()`
  等既有機制設計正確、如常運作，問題出在提案文件的一句敘述，不在程式碼。

### 4. 驗證證據 (Verification)
- 惰性驗證原始輸出（寫入前 4 筆／寫入後 8 筆）：`doc/upgrade/gates/evidence/UG_G3_SB2_routing_real_db_write.json`。
- 反向查核 SQL 與結果（457 筆中 4 筆已在 active `tracking_keywords`，`is_active=FALSE`
  者 0 筆——4 即為完整曝險範圍）：同上證據檔。
- 孤兒文章計數（161 篇，逐關鍵字拆分）：同上證據檔。
- 副作用尚未實際發生的查證（`stock_prices` 仍 4 檔、`scheduler.py` 未在執行）：同上證據檔。

### 5. 面試總結 (Lesson Learned)
> 「『這個東西是惰性的』是一句需要反向查核才能宣稱的話，不是一句憑直覺就能寫進提案
> 的話——反向查核只需要一條 SQL，但沒有人問過那條 SQL 該怎麼寫，直到 RISK-013
> 協議裡『寫入前後比對』這一步把答案硬生生逼出來。**機制設計對了（惰性驗證這一步
> 留住了），宣稱錯了（沒人反向查過），而讓機制真正發揮作用的，是『任一步不符即
> 停、回報、不進下一步』這條紀律——沒有它，8 筆會被輕描淡寫地當成 4 筆的近似值
> 略過去。**」

## CHAL-010: 每日特徵 upsert 的 `ON CONFLICT DO UPDATE SET` 全欄覆寫，會把 Triple-Barrier 標籤清空

- **關聯關卡 / 模組**：`UG-G3-SB2a` Gate A 送審期間發現，成因在 `UG-G2-SB1`（`upsert_ml_features` 29 欄契約）與 `UG-G3-SB1`/`UG-G3-SB2`（標籤寫入者）之間的介面
- **關聯決策**：DEC-023（29 欄契約）、DEC-018/DEC-035（Triple-Barrier）

### 1. 現象與衝擊 (Symptom & Impact)
`src/loaders/db_writer.py::upsert_ml_features()` 對 `daily_ml_features` 的
`INSERT ... ON CONFLICT (trade_date, stock_id) DO UPDATE SET` 對 29 欄**全欄
覆寫**（`update_cols` 排除主鍵外的全部欄位），而 `feature_aggregator.py`
的輸出從不包含 `target_triple_barrier`／`label_reason`（兩欄由獨立的標籤
寫入者負責）——**每一次每日特徵 upsert，都會把這兩欄覆寫成 `NULL`**，
不論該列原本是否已有標籤。

**衝擊規模**：`UG-G3-SB2` 的每日尾端重算掛點只補回每檔股票**最後
`holding_period+1`（6）列**的標籤。閘門解除後第一次 `run_all_daily_tasks()`
執行，`run_feature_engineering_pipeline()` 讀取**全部** `stock_prices`
並對全部列跑 `upsert_ml_features()`——**真實庫現有 3,529 個已寫入的
Triple-Barrier 標籤（3,713 列扣掉 no_entry／insufficient_data 等 NULL
成因列）會被清空，只剩每檔尾端 6 列**。`UG-G3-SB2a` 段 2（對既有 3 檔
重跑特徵）會踩到同一個坑。

### 2. 根因排查 (Investigation & Root Cause)
- `upsert_ml_features()`（`UG-G2-SB1`，DEC-023）建立時，`daily_ml_features`
  的 29 欄**全部**由同一個管線（`feature_aggregator.py`）產出，全欄覆寫
  是當時唯一合理的語意——**沒有欄位分屬不同寫入者**這個概念。
- `UG-G3-SB1`（Triple-Barrier 標籤生成器）與 `UG-G3-SB2`（每日尾端重算掛點）
  引入了**第二個、第三個寫入者**，各自只更新 29 欄裡的一小部分——但
  `upsert_ml_features()` 的欄位所有權模型從未跟著更新，仍假設「一次
  upsert 就是這一列的完整真相」。
- **這是一個跨 SB 邊界的介面契約沒有被重新檢視的案例**：`UG-G3-SB1`／
  `UG-G3-SB2` 各自的紅綠測試都只驗證「自己這條寫入路徑對不對」，沒有
  一項測試驗證「別人（`feature_aggregator`）的寫入路徑會不會動到我」——
  兩個方向都對，交集處沒人看。
- **SB2 既有的三項斷言與 24/24 基線都抓不到**：它們驗的是「掛點會不會跑、
  跑完尾端列對不對」，不是「掛點跑之前，特徵管線有沒有先把非尾端列的
  標籤清空」——**時間順序上的副作用，不在任何一項既有檢查的視野裡**。
- **審查方複審 SB2 時同樣沒有查到**：PO 2026-09-10 明確記載「接受了『排在
  特徵寫入之後』就沒問『特徵寫入會不會把標籤欄清掉』」——這不是單一個人
  的疏漏，兩層複核（實作＋審查）都被同一個問題繞過。

### 3. 最終解決方案 (Solution)
`upsert_ml_features()` 的 `DO UPDATE SET` **排除** `target_triple_barrier`／
`label_reason`（`LABEL_OWNED_COLUMNS`）——這兩欄視為由標籤寫入者（`UG-G3-SB1`
腳本／`UG-G3-SB2` 掛點／`UG-G3-SB2a` 段 3）擁有，`upsert_ml_features()`
不得覆寫。`INSERT` 欄位清單仍含這兩欄（新列本來就還沒有標籤，值為 `None`
是正確狀態，不是本次要擋的東西）——**只有 `ON CONFLICT` 分支的行為改變**。

### 4. 驗證證據 (Verification)
- `tests/test_ml_feature_store_contract.py::LabelColumnsNotOverwrittenByFeatureUpsertTests`
  兩項：
  - `test_do_update_set_excludes_label_owned_columns`：斷言 `DO UPDATE SET`
    不含這兩欄的 `col = EXCLUDED.col`，`INSERT` 欄位清單仍含。known-FAIL：
    修正前版本本斷言失敗（`target_triple_barrier = EXCLUDED.target_triple_barrier`
    確實出現在查詢字串裡）。
  - `test_feature_upsert_then_tail_hook_preserves_non_tail_labels`：整合式
    迴歸測試，模擬「已有 10 列標籤的表 → 走一次特徵 upsert」，斷言標籤不變。
    **第一版此測試結構上不會失敗**（迴圈判斷 `col in df_features.columns`，
    而 `df_features` 本來就不含這兩欄，迴圈永遠跳過它們，不論 `DO UPDATE SET`
    有沒有覆寫，斷言都會通過）——修正為依 `records`（`upsert_ml_features()`
    實際建構出的值，缺欄位時為 `None`，同生產行為）判定，known-FAIL 為
    `dtype` 不符（`object` vs `float64`，因全部列被覆寫成 `None`）。
- 全套測試 561/561 OK；`gate0_contract_check.py` 13/13 PASS exit 0；容器內
  9 項關鍵依賴（numpy/pandas/sklearn/lightgbm/xgboost/psycopg2/jieba/snownlp/
  tenacity）全部 `PRESENT`，無 fallback 路徑。

### 5. 面試總結 (Lesson Learned)
> 「兩個各自正確的寫入路徑，交集處未必正確——`upsert_ml_features()` 對它
> 負責的 29 欄全覆寫是對的，`UG-G3-SB1`／`UG-G3-SB2` 只更新標籤欄也是對的，
> 但『全覆寫』與『只更新一部分』疊在同一張表、同一組主鍵上，就是一個沒人
> 讀過的組合。**每個 SB 的測試都在驗證自己的輸入輸出，沒有一項在驗證
> 『這次寫入之後，上一個寫入者留下的東西還在不在』**——這正是『整合測試』
> 這個詞該負責的範圍，而它在兩個 SB 的邊界上被漏掉了。**閘門救了一次**：
> 若不是每日 ETL 從未真的跑過，這個缺陷會在第一次啟用時，把三千多筆真實
> 標籤資料在無人察覺的情況下清空。」

## CHAL-011: 跨市場交易日曆聯集——「加回 NVDA 差異歸零」如何找到真根因

- **關聯關卡 / 模組**：`UG-G3-SB2a` 段 2 唯讀基線比對期間發現（RISK-027 登記），
  獨立小案走 `bug-fix-protocol` 修復（`src/transform/feature_aggregator.py`）
- **關聯決策**：DEC-037（方案 B）

### 1. 現象與衝擊 (Symptom & Impact)
`UG-G3-SB2a` 段 2 唯讀基線比對（既有 3 檔台股重算 vs `daily_ml_features` 現有列）
的原始腳本只用台股 3 檔（無 NVDA）重算，與含 NVDA 的生產快照比對出 **36 個
`(trade_date, stock_id)` 差異**。加回 NVDA 重跑後，**29 欄、3,713 列全部零差異**
——差異完全由「重算輸入少了 NVDA」造成，不是特徵計算邏輯本身有 bug。這個排查
過程本身**意外揭露了一個獨立於本次比對目的之外的真實缺陷**：`feature_aggregator.py`
的交易日曆取自輸入價格表 `stock_id` 的**聯集**，不分市場。生產快照的輸入含 NVDA
（美股），日曆因此含美股獨有交易日（台股休市但美股照常）。台股假期期間發布的
PTT 文章經 Roll-Forward 演算法被對齊到這些「美股有、台股沒有」的日期，而台股
股票在這些日期的 `daily_ml_features` 沒有對應價格列——**文章因此在合併時靜默
流失**，不進入任何交易日的 `article_count`／`sentiment_*`。

### 2. 根因排查 (Investigation & Root Cause)
- **最初的錯誤歸因（PRE-G3-03）**：36 個差異最先被假設為「文章匯入時間差」
  （回補期間新文章持續進站，兩次查詢之間資料已變）。**這個假設的判準對任何
  輸入都會命中，不具鑑別力**（`CLAUDE.md` §9A.1 的「結構上無法失敗的檢查」
  同一種盲點，只是這次盲點在假設本身，不是某個既有的機械檢查）。
- PO 複核差異列表時發現：差異的**日期分布與美股獨有交易日一一對應**
  （02-12/13、02-16~20、02-27、04-06、07-10、08-25~28、08-31）——這不是
  隨機的時間差雜訊，是一個結構性的模式。
- 加回 NVDA 重跑後 29 欄、3,713 列全部零差異，**證實根因**：差異純粹來自
  「重算輸入的股票組成」，而非某次查詢之間文章有沒有新增。
- 追根到 `feature_aggregator.py:310`（修復前）：
  `unique_trading_days = sorted(df_prices_clean['trade_date'].unique())`——
  交易日曆直接取自**輸入價格表的日期聯集**，未分市場。
- **`bug-fix-protocol` Step 1 診斷階段查證的候選修法之一（方案 C：兩階段折衷）
  奠基於一個未驗證假設**——「一篇文章不會同時對到 TW 與 US 股票」。PO 2026-09-11
  裁決 Gate A 前，指示先查證此假設：真實庫唯讀查詢 `theme_stock_mapping` 顯示
  **「AI伺服器」題材同時涵蓋 TWSE 股票與 NVDA**——一篇 AI 伺服器題材文章會
  同時溢出到台股與美股成分股。**假設不成立，方案 C 出局**，改採方案 B（文章
  依其對應股票自身的交易日曆做 Roll-Forward）。

### 3. 最終解決方案 (Solution)
`feature_aggregator.py` 新增 `assign_trading_days_per_stock()`：文章先與
`df_mapping`／`df_theme_mapping` 合併展開成 `(article, stock_id)` 列（直接路由
與題材溢出同一規則），**再**依該列 `stock_id` 自身在 `stock_prices` 的交易日曆
做 Roll-Forward——順序是承重的，不能像修復前那樣在合併之前就用單一聯集日曆
決定 `trade_date`。`_aggregate_direct_comment_counts()` 不需另外修改：它讀的
是 `df_arts_direct` 的 `trade_date`，該欄已在合併與指派順序調整後自動正確。
詳見 DEC-037。

### 4. 驗證證據 (Verification)
- `tests/test_risk027_cross_market_calendar.py` 四項測試：直接路由、題材溢出、
  留言方向計數各自的「跨市場撞期不得流失」斷言，加上
  `test_mixed_market_input_matches_single_market_input_for_each_stock`
  （不變性判準：混合市場輸入下每檔的輸出必須等於該檔單獨輸入時的輸出，
  不依賴任何手算常數）。**修復前 4/4 FAIL**，失敗點精確落在預測的斷言
  （如 `article_count` 實際 `0.0` 非預期 `1`），非例外或找不到列；
  **修復後 4/4 GREEN**。
- 全套測試 696/696 OK；`gate0_contract_check.py` 13/13 PASS exit 0。
- `UG-G3-SB2a` 段 2（既有特徵重算）另走 RISK-013 三步驟協議重跑，本次修復
  本身不動真實資料庫。
- **2026-09-12 段 2 重跑真實庫寫入完成**：`scripts/verify/ug_g3_sb2a_stage2_rerun_risk027.py --write`
  對 `postgres`@`localhost:5432` 只更新「舊版（`git show 0da87d9` 載入）vs
  新版」機械算出的預期影響集，與「新版重算 vs 現有庫」實際差異集斷言相等
  （**132 鍵、14 檔股票**）後的 132 列 12 個情緒／留言欄。commit 前後核對
  （RETURNING 鍵集合、交易內讀回、標籤計數未變、全表 25 欄重算 vs 庫零差異、
  `stock_prices` 列數＋md5 寫入前後相同）全數 PASS。**審查方獨立複核**：對
  真實庫唯讀全表重算（25 欄、449,263 列 0 差異）、還原 PRE／POST 備份至
  拋棄式容器、與真實庫做三份狀態的逐列雜湊比對——**PRE 還原 vs 真實庫**：
  價格 13 欄＋標籤 2 欄 0 列不同、情緒 12 欄恰好 **132 列**不同（逐股票分布
  與影響集完全一致）；**POST 還原 vs 真實庫**：**0 列不同**。三份狀態互相
  印證，確認寫入只碰了該碰的 132 列 × 12 欄，未擴及範圍外任何列或欄。
  證據：`doc/upgrade/gates/evidence/UG_G3_SB2a_stage2_rerun_risk027.json`。

### 5. 面試總結 (Lesson Learned)
> 「一個為了解釋『兩次查詢差異』而提出的假設，如果它的判準對任何輸入都會
> 命中，它就不具鑑別力——真正讓我們找到根因的不是『假設聽起來合理』，是
> 『加回 NVDA 之後差異真的歸零了』這個可重現的操作。同一次排查裡還有第二層
> 教訓：候選修法（方案 C）也可能奠基在一個沒人查過的假設上——『兩階段折衷』
> 聽起來比『全面依股票重構』風險更小，但它的正確性完全取決於『一文不會同時
> 對到兩個市場』是否成立，而那句話在被查證之前只是一個沒被戳破的直覺。
> 兩次，`AI伺服器` 這個題材都是那個戳破直覺的真實資料形狀。」
