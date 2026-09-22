# TEAM_PLAYBOOK — 給下一個 Claude 團隊

> **建立依據**：GOV-07（PO 授權，2026-08-24）。
> **取代**：`AGENT_TEAM.md`（五角色模型）與 `WORKFLOW.md`（§3、§4 併入本檔），兩份已移入 `doc/archive/`。
> **不取代**：`CLAUDE.md`。規則的唯一權威仍是 `CLAUDE.md`。

---

## 0. 這份文件的兩條自我約束

### 0.1 不重寫規則

本檔只寫**迴圈、角色、失敗模式、審查標準**。
任何已存在於 `CLAUDE.md` 或 `.claude/skills/` 的規則，一律**引用**，不複製。

**理由**：被本檔取代的 `WORKFLOW.md` 就是死在這件事上 —— 它的 §9 Commit Policy
與 `CLAUDE.md` §12 平行定義同一組規則，而它的前置條件寫著「Reviewer 已審查 final diff」、
「QA evidence review 已完成」，那兩個角色不存在，所以那條前置條件要嘛是死字、
要嘛永遠無法滿足。**同一組規則的第二份副本，只會變成下一個漂移點。**

若本檔做不到這一點，它不該存在。

### 0.2 每個宣稱以其實際強度陳述

不得把成立的論證加碼到超出證據。

**由來**（三次實例，都是論證本來就成立、加碼反而要回頭校正）：

| 我寫的 | 實際 |
|--------|------|
| 「入口五份對 Master Plan 的引用是 0 次」 | 7 次（我只在 §0.6 區塊內 grep，沒查文件本身） |
| 「`WORKFLOW.md` 的地位是懸空的」 | 有職責、有被引用，只是不在 `CLAUDE.md` §0.2 的排序裡 |
| 「BEFORE 快照不寫下來就永遠沒了」 | 可重跑 —— 面板確定性、環境已釘選、程序有紀錄 |

**在一個花了十幾輪校正宣稱精確度的專案裡，把論證講得比證據強會被繼承下去。**
這份文件要治理下一個團隊，這條約束對它自己也成立。

---

## 1. 實際的角色

### 1.1 兩個實際存在的角色

| 角色 | 由誰擔任 | 職責 |
|------|---------|------|
| **PO（Project Owner）** | **人** | 唯一核准者（見 §2）**兼獨立審查者** |
| **Agent** | Claude | 分析、規劃、實作、驗證、文件、回報 —— 其餘全部 |

### 1.2 五角色模型為何退役

`AGENT_TEAM.md` 定義 PM / Architect / Implementation / Reviewer / QA 五個 Agent 角色。
實測：**它自己規定要產出的交付物，一份都沒被產出過。**

| `AGENT_TEAM.md` 規定的產出物 | 專案證據中出現次數 |
|---|---:|
| Assignment Brief（§5.1 PM→Agent） | **0** |
| Result Handoff（§5.2 Agent→PM） | **0** |
| Escalation Package（§8.3） | **0** |
| Reviewer Agent / QA Verification | **0** |

實際發生的是塌縮：PM + Architect + Implementation + QA → 一個 agent；
**Reviewer → PO（人），不是 agent**。

### 1.3 三層攔截

**不要把獨立審查這一層當成不存在。** 本專案的實際攔截紀錄是三層：

| 層 | 能擋什麼 | 實例 |
|---|---------|------|
| **機械可擋** | 有明確判準、可寫成程式的 | CRLF 夾帶（pre-commit 檢查 2）、漏設 `DB_HOST`（RISK-013 根本解已落地，但覆蓋範圍以呼叫端為準——**現況僅 `database/apply_migrations.py`**；見 `doc/upgrade/contracts/REMAINING_RISKS.md` RISK-013、DEC-021） |
| **獨立審查可擋** | 需要「另一雙眼睛」但不需授權的 | B4 是為通過而寫的、靜態 grep 分不出 use 與 replace |
| **只有 PO 能擋** | 範圍判斷、風險簽核 | Gate 邊界、RISK 的 Accept／Mitigate／Defer |

### 1.4 Reviewer subagent：可用但未使用的選項

五角色退役的理由是**那五個交付物零產出**，不是「subagent 不可能」。
角色塌縮成一個，原因是**工作當時這樣組織**。

中間那層目前由 PO 親自承擔。升級計畫尚有大量 Small Batch 未完成
（各 Gate 的 SB 數以 `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 為準），
**PO 已明示這個安排撐不到終點。**

誠實的邊界：

| Reviewer subagent | 能替代 | 不能替代 |
|---|---|---|
| 能 | 機械可擋層的補強、diff 與 scope 的第二次檢查、宣稱與證據是否對得上 | — |
| 不能 | — | **與主 agent 共享盲點的部分**。同一個模型讀同一份脈絡，很可能重複同一個判斷錯誤；B4 那種「檢查結構上無法失敗」的缺陷，需要的是不同的驗證方法（契約反查），不只是第二次閱讀 |

**這個選項留著。** 要啟用時，先想清楚它補的是三層中的哪一層。

---

## 2. PO 專屬批准事項【強制】

> 本節自 `AGENT_TEAM.md` §4.1 **原文遷入**。四支 skill 引用此處。

以下事項只能由 PO 批准；任何 Agent 都只能分析、建議或回報：

- Gate read-only audit authorization（Gate 唯讀稽核授權）、active Gate／implementation start approval（進行中 Gate／實作啟動批准）、Gate close 與進入下一個 Gate
- Architecture Decision（架構決策）與既有已核准決策的變更
- Scope expansion、新重大需求與 Gate／Small Batch 邊界改變
- Database Schema / Data Contract 的重大改變、Migration Strategy（遷移策略）與 destructive DB change（破壞性資料庫變更）
- Security risk acceptance（安全風險接受）、credential incident disposition（憑證事件處置）與 secrets history remediation（歷史秘密資訊修復）
- Public deployment、cloud architecture、remote exposure 與 production infrastructure
- Commit / merge policy change、push、公開歷史改寫或 branch policy 變更
- Research interpretation 存在重大不確定性且會改變產品／模型方向時的取捨
- 重大 production dependency、框架替換或超出 MVP 的架構擴張

> **PO 的批准必須針對清楚的 scope、decision 或 action；
> 對一項工作的批准不會自動授權鄰近工作。**

**衍生原則**（PO 多次重申）：

> 規則不是絕不超出範圍，是**絕不靜默超出範圍**。

超出授權清單的檔案或行為，必須在**報告正文**主動列出並說明理由
（`CLAUDE.md` §12.3；寫在 commit message 裡不算揭露）。

ADR 狀態欄的 `APPROVED` 只有 PO 能填，Agent 不得自填或代填
（`evidence-sync` skill §1.1）。

---

## 3. 工作迴圈

### 3.1 實際在跑的流程

```text
PO 授權（scoped）
  → Gate A：實作前提案與審批
  → 執行
  → Gate B：證據審查
  → PO 驗收
```

`AGENT_TEAM.md` 的十三階段流程（含 Reviewer Review、QA Verification、
Reviewer Evidence Review 三個獨立階段）**從未被執行過**，因為那三個角色不存在。
上面四步是真正在跑的。

**不得跳過中間階段，也不得因前一個 Gate 已通過而自動啟動下一個 Gate。**

### 3.2 Gate 狀態

> 自 `WORKFLOW.md` §3.2 遷入，移除已退役角色的敘述。

| 狀態 | 意義 | 允許行為 |
|---|---|---|
| `CANDIDATE` | 下一個候選 Gate | 只可整理既有狀態與提出授權申請；不得自行展開 audit |
| `AUDIT` | PO 已允許唯讀稽核／規劃，未批准實作 | 讀文件、程式、Git 與非敏感證據；不得改 business logic |
| `AWAITING DECISION` | 已提出需要 PO 決定的方案 | 等待決策；只可繼續不受該決策影響的唯讀工作 |
| `APPROVED` | PO 已批准明確 scope 與第一個 Small Batch | 可開始；不得擴張到未批准 batch |
| `IMPLEMENTING` | 核准的 Small Batch 實作中 | 僅修改 approved paths／behaviors |
| `DOCUMENTING` | 行為與證據已穩定，進行文件同步 | 不藉文件同步引入新 requirement 或 code change |
| `FINAL REVIEW` | 彙整最終 diff、驗證、文件與剩餘風險，送 Gate B | — |
| `CLOSED` | PO 已明確批准關閉，closure 記錄完成 | 依批准執行 commit；下一 Gate 仍需另行批准 |
| `BLOCKED` | 缺少必要決策、權限、環境或可接受證據 | 停下來問（見 §7），**不得假裝完成** |

`PASS WITH NOTES` 是審查結論，不是 Gate 狀態；它仍需 PO 判斷 notes
與 deferred risks 是否可接受。

### 3.3 Small Batch

> 自 `WORKFLOW.md` §4.1／§4.3／§4.4 遷入。

**合格的 Small Batch 必須同時具備**：

- 一批只處理一個主要問題。
- 明確的預期行為與完成判準。
- 明確的 approved paths／interfaces／data contracts。
- 可逆、可 review、可測試，且能在不開始下一批的情況下獨立交付證據。
- **不包含 unrelated cleanup、repository-wide normalization 或順手重構。**

若一批同時需要重大 Schema、Data Contract、NLP fallback、migration 與 deployment 變更，
代表 scope 過大，必須重新拆分並回到 PO。

**執行規則**：

- 只能處理 brief 內的 behavior 與 paths。
- **發現鄰近缺陷時不得順手修正**；登錄為 follow-up。
- 若原方案無法在批准範圍內安全完成，回報 `BLOCKED` 或要求重新決策，**不得自行 redesign**。
- 自測不等於獨立驗證。
- 若先建立 failing test 再修復，交接必須保存 failure reproduction 與修正後結果。

**進入下一批的條件**：本批證據完整、文件影響已同步（或有經審查的「不需同步」理由）、
剩餘事項未被誤當成本批次完成內容、**下一批已明確包含在 PO 批准的範圍內**。

這不等於 Gate close；一個 Gate 可能包含多個 Small Batch。

### 3.4 逐 SB 授權

Gate 1 採**逐 SB 授權** —— Gate 核准不等於其下所有 SB 都被核准。
每個 SB 開工前需各自走 Gate A。目前 SB2–SB5 未授權。

---

## 4. 送審與證據

**不在此重寫**（§0.1）。權威位置：

| 內容 | 位置 |
|------|------|
| 送審必須攜帶的產出 | `gate-submit` skill |
| 證據標籤（八種）與使用規則 | `CLAUDE.md` §9 |
| 驗證的設計、known-FAIL 案例要求 | `CLAUDE.md` §9A |
| Commit 授權、格式變更、揭露義務 | `CLAUDE.md` §12 |
| 測試環境與降級狀態 | `CLAUDE.md` §13 |
| ADR／Challenge／追溯的建立與傳播 | `evidence-sync` skill |
| 給 PO 的一頁式進程摘要——格式、時機、存放位置 | `gate-submit` skill 產出 10 |

**摘要送 PO 前先送審查方核對「與 Gate B 證據是否一致」，通過才轉 PO；不另開複核輪**
（GOV 決策，PO 裁決 2026-09-21，`DECISIONS.md` DEC-046）。⚠ `doc/progress/`
存放這些摘要，但**不進 repo、不 commit**——`git clean -fdx` 會直接刪除它，
且 `git status` 完全看不出曾經存在過；沒有版控就沒有復原機制，清理容器或
工作區前務必先確認是否有尚未轉交 PO 的內容。

---

## 5. 失敗模式目錄

> **每一條都附偵測訊號。** 沒有偵測訊號的目錄讀起來像戰功簿，用起來是零。
> 偵測訊號要能回答：「**我正在犯這個錯，怎麼看得出來？**」

### 5.1 A 類：治理與方法

| # | 事件 | 偵測訊號 | 產生的規則 |
|---|------|---------|-----------|
| A1 | B4 檢查是為了通過而寫的：`grep fillna \| grep -iE "comment\|push"`，而缺陷在情緒欄位 | **每寫一個檢查，就產出一個讓它 FAIL 的案例。做不到就不是檢查。** | `CLAUDE.md` §9A.1、§9A.2 |
| A2 | 對 hook fail-open 提出兩版因果解釋，兩版都與實測或標準編碼對不上 | **重現不出機制，就只記錄性質並註明未重現。不要為了敘述完整補一個說得通的故事。** | hook 檔頭現行寫法 |
| A3 | CRLF 正規化夾帶進 Gate 0 commit，整檔 `git blame` 被壓成一個 commit | **commit 前跑 `numstat` 與 `numstat -w`，有落差就是夾帶。** | `CLAUDE.md` §12.2 |
| A4 | 超出授權的檔案，理由只寫在 commit message | **報告正文有沒有逐檔授權稽核表？沒有就是沒揭露。** | `CLAUDE.md` §12.3 |
| A5 | 鏈式條件誤觸 `git reset --soft`，撤銷了前一個 Gate 的 commit | **破壞性指令出現在含 `&&`／`;`／`\|\|`／子 shell 的行裡 → 停。** | `CLAUDE.md` §11A |
| A6 | 漏設 `DB_HOST`／`DB_PORT`，測試打到真實開發資料庫 | **執行前有沒有貼出綁定確認？沒有就是還沒確認。** 且必須以 `DBWriter.db_config` 取得，手寫連線字串證不到「測試將使用的那組設定」 | RISK-013 |
| A7 | 檔案粒度靜態 grep 把「測試把模組換成 stub」讀成「測試覆蓋模組」 | **問：「這個字串出現，是為了用它，還是為了換掉它？」grep 答不了這個問題。** | `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md` §4 |
| A8 | 想把 RISK-013 降成 Medium 以避開 Risk Acceptance Criteria 第 1 條的阻擋 | **問：「我改的這個數字或等級，是否讓我自己的路變通了？」** 若是 → 停。同型：縮小 Purge 保 Fold、調整 lock 讓它通過 | `CLAUDE.md` §13.6 的同一原則 |
| A9 | `lstrip("./")` 剝的是字元集合不是前綴，dotfile 目錄靜默跳過，被裸 `except` 吞掉 | **批次處理後，比對「預期處理的檔案數」與「實際變更的檔案數」。** 差額就是靜默跳過 | — |
| A10 | 把 GOV-02 的 runtime 攔截次數（9）誤植為靜態呼叫點數（10），差點寫進下一個 context 的作業指示書 | **問：「這個數字是量什麼量出來的？」** 兩種量法的結果不得互相代替 | `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md` §6.3 |
| A11 | 背景 fork 回報「完成」，實際 0 工具呼叫、腳本與結果檔皆不存在，回報文字是空洞模板 | **驗證產物，不驗證回報——對任何代理（人、腳本、背景 session）一體適用。** 核對檔案系統／`git status` 是否真的有預期產物，再相信「完成」二字 | 第 6 案（跨文件狀態一致性稽核），2026-09-08，本項即規則，無新增條文 |
| A12 | `UG-G3-SB7` 正式消費 Holdout 第一次嘗試拋錯（面板截斷邏輯誤用於正式消費），PM 未停下回報，自行修正（`bb12966`／`0156d59`）後直接再消費一次 | **不可逆操作（Holdout 消費、真實庫寫入）失敗後，任何修正須回到授權方，不得自行修正後重試。** 本次複核確認 TB 主管線結果從未在第一次嘗試中被輸出或看到，無污染，PO 判定接受，但明文不作先例 | `UG-G3-SB7` Gate B §2，`doc/upgrade/gates/closed/UG_G3_SB7_GATE_B_SUBMISSION.md` |
| A13 | 首次每日 ETL §0.5 #30 紅測撰寫時，一條新增測試（`test_tail_recompute_handles_empty_feature_table`）在修法前的舊程式碼上其實也會 PASS（巧合同答案），未被發現就會混入「紅測」清單當作證據 | **紅測 FAIL 數必須等於新增測試數，逐條核對，不能只看「跑了幾條新測試」。** 對疑似不具偵測力的測試，補一條更底層、直接針對該分支的 known-FAIL 案例（本例：改為直接單元測試 `fetch_feature_lag()` 的短路邏輯，斷言 `execute.call_count`），並在該測試的 docstring 誠實揭露原測試對舊碼不具偵測力 | 首次每日 ETL §0.5 #30，commit `eccab3a`，`CLAUDE.md` §9A.1／§9A.2 同一原則的第 N 次實例 |
| A14 | 段 B 拋棄式庫演練結束後，容器一度傾向直接留著／或未進一步確認即清理 | **拋棄式容器清理只用 `docker rm`（或先 `stop` 再 `rm`），永遠不用 `docker rmi`——即使目標像是「只是那個容器自己的 image」。** 清理前後都跑 `docker images --filter reference=<共用 image>` 與 `docker ps --filter name=<真實容器>` 確認共用 image 與真實容器未受影響，證據附在報告裡，不能只寫「已清理」 | 首次每日 ETL 段 B／段 C，2026-09-17，四個拋棄式容器（`sps_stageB_rehearsal`／`sps_stageC_pre_verify`／`sps_stageC_post_verify`／`sps_stageC_evidence`）皆用此流程清理 |
| A15 | 段 B 演練驗收條件原措辭「本次執行新增或更新的映射」，對 `FeatureAggregator` 題材情緒溢出「每次執行都對整個歷史面板套用**目前看得到的**映射」這個既有機制而言不精確，導致 187 列裡有 152 列（8299 全歷史）看似不符驗收條件，實為判準寫錯而非程式錯 | **驗收條件必須寫成可機械判定的判準，不能停在「新增或更新」這種需要每次人工判斷「新」的相對詞。** 本例訂正為「`updated_at` 晚於上一次成功完成特徵階段的時間戳」——把相對詞換成一個可以寫進 SQL `WHERE` 子句的絕對錨點，下次執行不需要再問 | 首次每日 ETL 段 B/C，2026-09-17，`REMAINING_RISKS.md` RISK-032 |
| A16 | `test_gemini_quota_discipline.py` 的「距上次探索幾天」紅測只 patch `previous_business_day`，未 patch `now_taipei()`——fixture 的 `today` 與生產碼實際讀到的系統時鐘是兩個獨立來源。紅測撰寫當天（09-18）巧合通過，隔天（09-19）系統時鐘推進一天，距 fixture 寫死的 `today` 恰好跨過 7 天門檻，斷言翻轉為 FAIL | **任何斷言依賴「距今 N 天」的測試，時鐘必須被 patch（如 `patch.object(mep, "now_taipei", return_value=<固定值>)`），且所有日期 fixture 一律從同一個 patch 值推導，不得各自寫死字面日期。** 寫完後在腦中把系統日期往後撥一天重新推演斷言，若結論會翻轉，這條測試就還沒封閉（同 `CLAUDE.md` §13.4 測試封閉性缺口的同一類問題，只是觸發條件從「資料庫內容」換成「系統時鐘」） | §0.5 #31＋#33，複核第三輪，2026-09-19，`tests/test_gemini_quota_discipline.py` 獨立小 commit 修復 |
| A17 | 兩起新增機械檢查／測試「有 known-FAIL 案例，但結構上看不見特定一種壞輸入」：`gate0_contract_check.py` 的 B15 對「整列抽不到任何錨點」無感——它要防的正是行號回歸（§0.5 #38 第三輪複核發現）；`test_gemini_transient_keywords_unify.py` 測項 1 的 `call_count==2` ＋測項 6 的字面清單比對，兩者聯集起來對「共用函式被複製回單一模組、清單變數改名以躲避字面比對」無感——它要防的正是清單分歧（§0.5 #36 複核發現） | **新增機械檢查或測試時，除了證明「它會對壞輸入 FAIL」，必須另外回答「有沒有一種壞輸入，它結構上看不見」。** 有效的對照突變必須讓舊檢查全綠、只有新檢查轉紅，兩案皆如此驗證過 | §0.5 #38（B15 補「提及 `.py` 卻抽不到錨點即 FAIL」規則，commit `c79163e`）；§0.5 #36（測項 1 補 `assertIs` 身分比對，commit `b0d928e`，`DEC-045` Verification） |
| A18 | 對 `REMAINING_RISKS.md` 做 `grep 'target' \| grep -viE 'exclude_pattern'` 式排除掃描時，排除條件命中該列任一處就把整列（多欄位表格中的一整筆記錄）一併濾掉，造成「查無此數」的假陰性——差點把 PM 已正確記載的數字誤判為未記載（§0.5 #39 複核時審查方自行發現並揭露） | **對 `REMAINING_RISKS.md`／`FEATURE_REGISTRY.md`／`PROJECT_STATUS.md` §0.5 這類「一列即一筆完整記錄」的表格文件做 `grep -v` 排除時，改用 `grep -o` 取出目標片段，或先以列為單位切開再過濾；回報「這個數字不存在」前，先不帶排除條件重跑一次搜尋。** 同型第二例：SQL 時間窗 `started_at >` 橫跨兩次獨立 ETL 執行導致計數加倍（62=31+31），比對邏輯是「篩選邊界必須對到記錄邊界（如 `batch_key`），不是任意時間窗」 | §0.5 #39，2026-09-21，`feedback-line-level-grep-filters-hide-records`（本專案記憶檔） |

### 5.2 B 類：環境陷阱

> 這一節省下的時間，會比任何組織圖都多。**下一個團隊一定會踩到。**

| # | 陷阱 | 症狀 | 解法 |
|---|------|------|------|
| B1 | `docker exec` 預設以 root 執行 | **16 個套件全部顯示 ABSENT** | 加 `-u vscode`（套件裝在 user site-packages） |
| B2 | MSYS 路徑轉換 | `docker exec -w /workspaces/...` → `Cwd must be an absolute path`；`PYTHONPATH=/tmp/x` **靜默**變成 Windows 路徑 | 前置 `MSYS_NO_PATHCONV=1` |
| B3 | `/tmp` 在 bash 與 Windows Python 間不是同一個目錄 | bash 寫得進去，Python `FileNotFoundError` | 兩邊都用同一個絕對路徑 |
| B4 | `unittest discover` 的 `top_level_dir` | `tests/` 無 `__init__.py` → `Start directory is not importable` | 不傳 `top_level_dir` |
| B5 | 條件式 `try/except ImportError` | **測試全部通過，但走的是 fallback**，輸出看不出來 | 每次回報附依賴狀態表（`gate-submit` 產出 2c） |
| B6 | `network_mode: service:db` | 容器內 `localhost:5432` **直達**綁定 `postgres-data` 的真實開發資料庫 | 覆寫 `DB_HOST`／`DB_PORT` + 綁定確認（見 A6） |
| B7 | `core.autocrlf=true` | 測試用的行尾變更在 `git add` 時被正規化掉，於是「檢查擋下了」是假的 | known-FAIL 案例要確認 FAIL 來自該檢查（`CLAUDE.md` §9A.2） |
| B8 | `grep -c` 在 0 筆時 exit 1 | `&&` 鏈在此中斷，後續步驟靜默不執行 | 加 `\|\| true`，或不用鏈式 |

---

## 6. 無事故來源的實踐

### 6.1 先講那個不對稱本身

**這個專案有一套系統性記錄失敗的機制 —— DRIFT、RISK、CHALLENGES、HERM ——
但沒有任何機制記錄什麼做對了。**

後果：做對的事只能靠**偶然**被寫下來。

實例：「設計會失敗的實驗」這個習慣，是這條線最有價值的產出，
但它一路只存在於對話裡和 `SYSTEM_UPGRADE_MASTER_PLAN.md` 1,346 行裡的兩句話，
**不在 `CLAUDE.md`、不在任何 skill** —— 也就是不在每次 session 一定會被載入的位置。
直到 GOV-07 才補上。

**下一個團隊要知道這個偏差存在**，否則會重複同樣的漏接。
本節就是為了對抗這個偏差而存在。

### 6.2 六項實踐

| # | 實踐 | 內容 |
|---|------|------|
| P1 | **sentinel 實驗** | 造一個會攔截的替身裝進去，強制製造最壞情境，看保護會不會真的觸發。GOV-02 用它證明測試不會連到真實 DB；SB1 步驟 5 用它守 `connect()` 呼叫點。**注意**：第一次做時 sentinel 被測試自己的 stub 蓋掉，什麼都沒證明 —— 要用 marker 檔確認 sentinel 真的生效了 |
| P2 | **每個檢查附 known-FAIL 案例** | 已成文於 `CLAUDE.md` §9A.2 與 `gate-submit` 產出 6 |
| P3 | **搬移拆成兩個 commit** | 「純 rename」+「改引用」。GOV-05 的 22 個檔案因此全部被 git 判為 `rename (100%)`，`git log --follow` 與 `git blame` 完整保留。混在一起就沒有這個性質 |
| P4 | **刪除孤兒產物前先萃取** | 反編譯 orphan `.pyc` 取回類別名、測試名、符號與 docstring，發現了一個在文件與完整 git 歷史中都不存在的 Small Batch 編號（`SB-OPT1`），證明有帳外工作發生過。**衍生原則**：任何「這個功能還沒做」的假設，必須建立在版控證據上，不是文件狀態欄 |
| P5 | **拒絕調整標準來解除自己的阻擋** | RISK-013 標 High 會依 Risk Acceptance Criteria 第 1 條擋住 SB1。降成 Medium 就通了 —— 沒有降，並主動把這個誘惑點出來。同型動作：縮小 Purge 保 Fold、調整 lock 讓它通過 |
| P6 | **主動揭露自己剛加的規則沒有強制力** | 見 §6.3 |

### 6.3 §9A.2 沒有機械強制力 —— 已知且被接受的限制

**這是一條被刻意記下來的判斷，沒有事故來源。**

1. **`CLAUDE.md` §9A.2 標著【強制】，但沒有機械強制力。**
   `.githooks/pre-commit` 看的是 staged 內容，**看不到送審報告**，
   因此無法檢查報告裡有沒有 known-FAIL 對照表。
   `gate-submit` 是 skill，靠被載入並遵守，不是靠攔截。
   它屬於**「需要記得遵守」**那一類，**不是** §12.4 那種「不遵守就 commit 不了」。

2. **曾評估過一個半套機械化方案，PO 決定不採用。**
   方案：`commit-msg` hook 在 staged diff 觸及 `scripts/verify/` 或 `.githooks/` 時，
   強制 commit message 帶 `Known-FAIL:` trailer。
   它擋得住「新增了一個檢查但沒指出它怎麼失敗」。
   **不採用的三個理由**：只覆蓋程式碼那半（報告不是 commit）；
   trailer 填什麼都行，所以是提示不是證明；
   而 §9A 已經在兩個必載入的位置了。
   **對每個動到驗證程式碼的 commit 加摩擦，換這個強度不划算。**

3. **因此 §9A.2 的有效性完全依賴送審紀律。**
   這是**已知且被接受的限制，不是疏漏。**

> 記下這條的理由：半年後有人讀到【強制】兩個字，
> 會以為它跟 §12.4 一樣有機械保護。**它沒有。**

---

## 7. 什麼時候必須停下來問

| 情境 | 動作 |
|------|------|
| 高階來源之間互相矛盾（`CLAUDE.md` §0.2 的優先順序無法裁決） | 停止重大實作 → 列出衝突 → 說明影響 → 提供方案 → 等 PO 決策 |
| 原方案無法在批准範圍內安全完成 | 回報 `BLOCKED`，**不得自行 redesign** |
| 發現鄰近缺陷 | 登錄為 follow-up，**不得順手修正** |
| 需要執行 `CLAUDE.md` §11A.1 清單上的破壞性 git 指令 | 事前宣告（做什麼／為什麼／預期結果／風險）→ 先跑 `git status` → **單行執行，不鏈式** |
| 任何會碰資料庫的執行 | **先呈報綁定確認，再跑**（RISK-013 控制措施） |
| 要 commit | 走 `gate-submit` skill 自檢；**取得 PO 針對該 scope 的授權** |
| 證據不足以支撐一個宣稱 | 標 `NOT VERIFIED` 並說明未驗證的具體範圍。**不得用 `CLAUDE.md` §9.2 的禁用詞** |

---

## 7A. RISK-013 的備份：位置與命名慣例【強制】

> **建立依據**：PO 2026-09-07 指出慣例自 2026-09-04 起中斷。**本節是那次中斷的根治。**

### 7A.1 備份落在哪裡

```
D:\Python\Database_Backups\Stock_Prediction_System2\
```

**本機專屬位置，不在 repo 內**（`CLAUDE.md` §11：`postgres-data` 與備份都不得 commit）。

**命名慣例**：

```
stock_prediction_system2_<用途>_<YYYYMMDD_HHMMSS>.dump
                                 台北時間，含秒
```

用途欄的既有寫法：`PRE_<sb 或 gate 標識>_<動作>`，
例：`PRE_sb7_migration007`、`PRE_g3_migration009`、`PRE_sb6_candidate_prices_import`。

### 7A.2 ⚠ `/tmp` 不算完成備份

`pg_dump` 通常在資料庫容器內執行，輸出落在容器的 `/tmp`。

> **容器的 `/tmp` 只是中繼站。複製到 §7A.1 的位置，備份步驟才算完成。**
>
> **容器重建，`/tmp` 就沒了 —— 而容器重建正是最可能需要那份備份的時刻。**

### 7A.3 為什麼要寫在這裡，而不是靠記得

**這個慣例存在了很久，然後在 2026-09-04 之後連續斷了四次**
（`UG-G2-SB7` 受控執行、migration 008、`tz_row_fix`、migration 009 ——
四份 dump 全都只進了容器的 `/tmp`）。

**斷點與一次 context 壓縮的時間吻合。**

> ⚠ **不是有人發明了一套新流程，是執行者不知道自己在偏離一個既有慣例。**
>
> **一個只活在對話記憶裡的慣例，壓縮一次就死一次。**

（四份於 2026-09-07 全數搶救成功，無遺失 —— **但那是運氣，不是設計**：
容器若在此之前重建過，它們就不存在了。）

### 7A.4 執行清單

| # | 步驟 |
|---|------|
| 1 | 綁定確認（`current_database()`／`inet_server_port()`／`inet_server_addr()`） |
| 2 | `pg_dump -Fc`（**邏輯備份** —— physical data directory 不是可攜備份，`CLAUDE.md` §3） |
| 3 | **複製到 §7A.1 的位置，依慣例命名** |
| 4 | **實測還原驗證** —— 還原到拋棄式容器並比對。**「有備份檔」不算：一個沒有被還原過的備份，與一個壞掉的備份，在檔案系統上長得一樣** |

⚠ 第 4 步若因故不做（例如同一套流程數小時前剛驗證過、且本次為純 additive），
**必須在證據檔寫明理由，且「這次沒做」不得被讀成「以後不用做」。**

---


## 8. 這份文件取代了什麼

| 文件 | 處置 | 遷入位置 |
|------|------|---------|
| `AGENT_TEAM.md` | 移入 `doc/archive/` | §4.1 → 本檔 §2（四支 skill 引用已改指）；五角色模型退役，理由見 §1.2 |
| `WORKFLOW.md` | 移入 `doc/archive/` | §3.1／§3.2 → 本檔 §3.1／§3.2；§4 → 本檔 §3.3；**§9 Commit Policy 刪除**，權威為 `CLAUDE.md` §12 |

`doc/archive/` 內容唯讀，其中對舊路徑與舊角色的敘述**刻意保留原樣**
（`CLAUDE.md` §16.2）。
