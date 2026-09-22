# Engineering Workflow Governance（工程工作流程治理）

> 本文件定義本 Repository 的 Gate Lifecycle（關卡生命週期）、Small Batch（小批次）、Review（審查）、Verification（驗證）、Documentation Sync（文件同步）與 Commit Policy（提交政策）。它描述「工作如何流動」，不取代根目錄 `AGENTS.md` 的持久規則、不重新定義 Agent 角色，也不宣告目前 Gate 狀態。

## 1. 文件定位與適用順序

| 文件 | 主要責任 |
|---|---|
| `AGENTS.md` | Durable Repository Rules（持久 Repository 規則）、工程 invariants（不可輕易違反原則）與 Source-of-Truth Precedence（真實來源優先順序） |
| `doc/governance/AGENT_TEAM.md` | 五個 Agent 角色、授權邊界、交接、審查與升級治理 |
| `doc/governance/WORKFLOW.md` | Gate 與 Small Batch 從規劃、實作、審查、驗證、文件同步到提交的流程 |
| `doc/governance/PROJECT_STATUS.md` | 目前 Phase、Gate、Git、已驗證事項、延後風險與下一步候選 |

若文件互相矛盾，依 `AGENTS.md` 的 precedence 處理。`PROJECT_STATUS.md` 只能記錄狀態，不能創造新需求或批准；本文件只能定義流程，不能取代 Human approval（人工批准）。

## 2. Workflow Invariants（流程不變原則）

1. Human（使用者／Project Owner）是 Gate read-only audit authorization（唯讀稽核授權）、active Gate／implementation start approval（進行中 Gate／實作啟動批准）、Gate close、重大決策與 commit 的最終批准者。Audit authorization 不等於 implementation approval。
2. 每次只處理一個已批准 Gate；Gate 內每次只處理一個主要問題的 Small Batch。
3. 未獲批准的 recommendation（建議）不是 requirement（需求），未獲批准的候選 Gate 不是 active Gate（進行中 Gate）。
4. Architect analysis、Implementation evidence、Reviewer verdict 與 QA result 是不同證據，不得互相替代。
5. `FAIL` 必須保存；修正後的 `PASS` 不得抹去原始 failure evidence（失敗證據）。
6. Read-only（唯讀）不代表 non-sensitive（非敏感）；所有 inspection（檢查）遵循 least disclosure（最少揭露）。
7. 發現範圍外問題時登錄 follow-up（後續事項）；只有 blocker（阻礙）或必要 Human decision 才中止當前流程。
8. 未完成 Review、Verification、Evidence Review、Documentation Sync 與 Human close approval，不得宣稱 Gate `CLOSED`。
9. Fresh initialization、unit test 或單一 happy path（正常路徑）通過，不得外推為 migration safety、End-to-End、production 或 cloud readiness。

## 3. Gate Lifecycle（Gate 生命週期）

### 3.1 標準流程

```text
Candidate Gate（候選 Gate）
→ Human Audit Authorization（人工唯讀稽核授權）
→ Read-only Audit（唯讀稽核）
→ Architect Analysis（架構分析）
→ Human Decision / Active Gate & Implementation Start Approval（人工決策／進行中 Gate 與實作啟動批准）
→ Implementation Small Batch（小批次實作）
→ Reviewer Review（獨立審查）
→ QA / Verification（品質保證／驗證）
→ Reviewer Evidence Review（證據審查）
→ Documentation Sync（文件同步）
→ Final Gate Review（最終 Gate 審查）
→ Human Close Approval（人工關閉批准）
→ Closure Record Finalization & Reviewer Delta Check（關閉紀錄定稿與 Reviewer 差異核對）
→ Commit（提交）
```

不得跳過中間階段，也不得因前一個 Gate 已通過而自動啟動下一個 Gate。

### 3.2 Gate 狀態

| 狀態 | 意義 | 允許行為 |
|---|---|---|
| `CANDIDATE` | 整頓計畫或 PM 提出的下一個候選 | 只可整理既有狀態與提出 audit authorization request；不得自行展開 Repository audit |
| `AUDIT` | Human 已允許唯讀稽核／planning，但未批准實作 | 讀文件、程式、Git 與非敏感證據；不得改 business logic |
| `AWAITING DECISION` | Architect 已提出需要 Human 決定的方案 | 等待決策；只可繼續不受該決策影響的唯讀工作 |
| `APPROVED` | Human 已批准明確 Gate scope 與第一個 Small Batch | PM 可派 Implementation；不得擴張到未批准 batch |
| `IMPLEMENTING` | 核准 Small Batch 實作中 | 僅修改 approved paths／behaviors |
| `REVIEW` | Reviewer 查證 scope、diff 與 claims | Reviewer 不修改 implementation |
| `VERIFYING` | QA 執行已批准 verification plan | 依隔離與安全條件執行測試，保留 PASS／FAIL |
| `DOCUMENTING` | 行為與證據已穩定，進行文件同步 | 不藉文件同步引入新 requirement 或 code change |
| `FINAL REVIEW` | PM 彙整最終 diff、驗證、文件與剩餘風險 | Reviewer 提出 final verdict；PM 提出 close recommendation |
| `CLOSED` | Human 已明確批准關閉，且 closure 記錄完成 | 依批准執行 commit；下一 Gate 仍需另行批准 |
| `BLOCKED` | 缺少必要決策、權限、環境或可接受證據 | 依 `AGENT_TEAM.md` 升級，不得假裝完成 |

`PASS WITH NOTES` 是 review verdict（審查結論），不是 Gate 狀態；它仍需 Human 判斷 notes 與 deferred risks 是否可接受。

### 3.3 Gate Planning Package（Gate 規劃封包）

在要求 Human start approval 前，PM 與 Architect 至少提供：

1. Goal（目標）與待解決的 major problem（主要問題）。
2. Current State（目前狀態），區分文件記載、程式證據與本次實測。
3. Source of Truth（真實來源）：相關 DEC / ADR、PRD、SDD、Research Requirements、程式與測試。
4. In Scope／Out of Scope（範圍內／範圍外）。
5. Alternatives、recommendation、rationale 與 trade-offs。
6. Human decision points（人工決策點）。
7. Small Batch sequence（小批次順序）與每批 approved paths 候選。
8. Verification plan、test isolation、negative cases 與 regression risks。
9. Data、security、migration 與 rollback／recovery considerations（回復考量）。
10. Documentation impact 與預期 Decision／Challenge evidence。

資料不足時必須標示 `NOT VERIFIED`、`ASSUMPTION` 或 `ENGINEERING JUDGMENT`，不得以確定語氣補齊未知資訊。

## 4. Small Batch Governance（小批次治理）

### 4.1 Small Batch 定義

合格的 Small Batch 必須同時具備：

- One major problem at a time（一批只處理一個主要問題）。
- 明確的 expected behavior（預期行為）與完成判準。
- 明確的 approved paths／interfaces／data contracts。
- 可逆、可 review、可測試，且能在不開始下一批的情況下獨立交付證據。
- 不包含 unrelated cleanup、repository-wide normalization 或順手重構。

若一批同時需要重大 Schema、Data Contract、NLP fallback、migration 與 deployment 變更，代表 scope 過大，必須重新拆分並回到 Architect／Human。

### 4.2 Small Batch Brief

PM 指派 Implementation 前，brief 至少包含：

```text
Gate / Batch ID:
Objective:
Approved decision:
In-scope behavior:
Approved paths:
Out-of-scope:
Required tests / checks:
Safety / isolation constraints:
Expected evidence:
Stop / escalation conditions:
```

### 4.3 Implementation 規則

- Implementation Agent 只能處理 brief 內的 behavior 與 paths。
- 發現鄰近缺陷時不得順手修正；回報 PM 為 follow-up。
- 若原方案無法在批准範圍內安全完成，回報 `BLOCKED` 或要求重新決策，不得自行 redesign。
- 執行必要 static checks，但 Implementation 自測不等於獨立 Review／QA。
- 若先建立 failing test（失敗測試）再修復，交接必須保存 failure reproduction 與修正後結果。

### 4.4 Batch Completion

Small Batch 只有在下列條件成立時才能進入下一批：

- Implementation handoff 完整。
- Reviewer verdict 為 `PASS` 或 Human 可接受的 `PASS WITH NOTES`。
- QA 已完成適用的驗證，或明確說明本批次為何不需 runtime verification。
- Reviewer 已完成 evidence review。
- 文件影響已同步或有經審查的「不需同步」理由。
- PM 已確認剩餘事項未被誤當成本批次完成內容。
- 下一批已明確包含於 Human 批准的 batch sequence、scope 與 paths；若未包含，必須先提交新的 Small Batch brief 並取得 Human approval。

這不等於 Gate close；Gate 可能包含多個經 Human 批准的 Small Batch。

## 5. Review Workflow（審查流程）

### 5.1 Review Inputs

Reviewer 至少取得：

- Human-approved scope 與 Small Batch brief。
- Relevant DEC / ADR、PRD、SDD 或 Research Requirement IDs。
- Git status、base revision、changed paths 與完整 diff。
- Implementation handoff、checks、原始 failures 與尚未驗證事項。

### 5.2 Review Focus

Reviewer 依 `AGENT_TEAM.md` 檢查：

1. Scope compliance 與 Scope Creep（範圍蔓延）。
2. Implementation claims 是否可由 diff／code／checks 支持。
3. Architecture、Schema、Data Contract 與 error semantics 是否一致。
4. Security、secret、database、migration、idempotency 與 data lineage 風險。
5. Tests 是否驗證 requirement，而不是只重複 implementation。
6. 文件是否 overclaim，Evidence／Inference／Assumption／Judgment 是否混淆。
7. 是否存在未說明的 regression risk 或 unrelated change。

Reviewer 只能給出 `PASS`、`PASS WITH NOTES`、`NEEDS CORRECTION` 或 `BLOCKED`，不能直接修檔。

### 5.3 Correction Loop

`NEEDS CORRECTION` 時：

1. PM 判斷修正是否仍在原批准 scope。
2. 若在 scope 內，重新指派 Implementation，保留前次 findings 與 FAIL evidence。
3. Reviewer 重新審查新的完整 diff，不只看最後一小段修正。
4. 受影響的 QA cases 必須重跑。
5. 若需要新決策、範圍擴張或高風險操作，停止 correction loop 並升級 Human。

## 6. Verification Workflow（驗證流程）

### 6.1 Verification Plan

每個非微小 Small Batch 應在實作前定義：

- Requirement／risk 對應的 test cases。
- Happy path、empty path、failure path 與 negative cases。
- Mock／fixture 或隔離 PostgreSQL 的策略。
- 不得接觸的真實資料、secret 與外部服務。
- Expected result、failure signal 與 cleanup plan。
- Regression scope 與不能由本次驗證支持的 claims。

### 6.2 Database Isolation

- 不得把 `.devcontainer/postgres-data/` 或目前 development database 當成可任意寫入的測試目標。
- 需要 PostgreSQL runtime verification 時，使用獨立 test database、temporary database 或 temporary container，並先確認沒有 development bind mount／host port collision。
- 任何 destructive verification 都需 Human 明確批准與備份／回復方案。
- 驗證後回報 cleanup status 與 development environment non-interference；不得輸出完整 environment 或 credential values。

### 6.3 External Services

- Gemini API、yfinance、TWSE、PTT 或其他不可控外部服務不得成為唯一測試依據。
- 優先使用 mock、fixture 與 deterministic response（可重現回應）。
- 若執行 live verification，必須事先說明成本、rate limit、資料隱私與不確定性，並取得所需批准。

### 6.4 QA Result

QA 回報使用：

- `PASS`：批准範圍內的 expected behavior 與 relevant regressions 通過。
- `FAIL`：存在可重現的不符合行為；保存命令、expected vs actual 與影響。
- `PARTIAL`：部分驗證完成，但仍有明確未驗證區域。
- `BLOCKED`：環境、權限、決策或隔離條件不足，無法取得可靠結果。

QA 不修改 implementation。`FAIL` 回到 PM，由 PM 決定原 scope correction 或升級 Human。

### 6.5 Reviewer Evidence Review

QA 後由 Reviewer 獨立確認：

- 測試是否覆蓋已批准 requirement 與原始風險。
- 測試隔離、資料非干擾與 cleanup 是否有證據。
- FAIL 是否被完整保留，PASS 是否被過度外推。
- 測試結果、diff 與文件聲明是否互相一致。

## 7. Documentation Sync（文件同步）

### 7.1 同步時點

Implementation behavior 與 verification evidence 穩定後才進行文件同步。不得先修改文件宣稱預期結果已達成，再以文件作為實作完成證據。

### 7.2 文件責任

依變更內容評估：

- `doc/evidence/DECISIONS.md`：架構、Schema、Data Contract、fallback、reliability、ML validation 或重大 scope／trade-off 決策。
- `doc/evidence/CHALLENGES.md`：具工程學習價值的 symptom、investigation、root cause、failed attempts、solution 與 verification。
- `doc/governance/PROJECT_STATUS.md`：目前 Gate、Git、已驗證、未驗證、deferred risks 與下一步候選。
- PRD：產品目標、需求或 scope 經 Human 批准後的變更。
- SDD：已核准架構、模組責任、Data Contract 與 initialization／migration boundary。
- Research Requirements／TRACEABILITY：研究證據到 requirement、design、code、test 的追溯。
- README／portfolio material：只能使用已驗證或清楚標示限制的 claims。

### 7.3 Evidence Discipline

文件必須區分：

- `VERIFIED THIS SESSION`
- `PREVIOUSLY VERIFIED`
- `IMPLEMENTATION EVIDENCE`
- `REPORTED, NOT INDEPENDENTLY VERIFIED`
- `INFERENCE`
- `ASSUMPTION`
- `ENGINEERING JUDGMENT`
- `NOT VERIFIED`

不得使用沒有 measurement／test／log 支持的 `perfect`、`production-ready`、`guaranteed`、`100%` 或等價絕對描述。

### 7.4 Documentation Review

Reviewer 檢查文件是否：

- 與實際 diff、tests 與 Human decisions 一致。
- 沒有把 planned behavior 寫成 completed。
- 沒有把 fresh／unit／local evidence 外推到 migration／End-to-End／production。
- 保存 remaining risks、failed evidence 與 deferred items。
- 不含 secret value、敏感 runtime output 或無法追溯的研究主張。

## 8. Final Gate Review 與 Human Close

### 8.1 Final Gate Package

PM 向 Human 提交：

1. Gate objective 與 Human-approved decisions。
2. 各 Small Batch 的 scope、changed paths 與結果。
3. Reviewer verdicts 與 QA results。
4. Verified evidence、previous evidence、not verified 與 limitations。
5. Documentation sync 結果。
6. Security、database、migration、regression 與 deferred risks。
7. Git status、commit scope 候選與 PM close recommendation。

### 8.2 Close 條件

只有 Human 明確批准後，PM 才能把 Gate 記為 `CLOSED`。Human 若只批准修正、補測或文件調整，不等於 close approval。

Gate close 後：

- 將 Documentation Sync 階段預先建立、且僅標示 `PENDING HUMAN CLOSE` 的 closure draft，機械性更新為 Human 實際批准的 closure outcome；不得加入新 claims、decision 或 scope。
- Reviewer 對 close 後的 `PROJECT_STATUS.md` delta、final diff 與 commit scope 進行最後核對；任何非機械性變更都必須退回 Documentation Review，而不是直接 commit。
- 確認完成 delta check 後的 final diff 等同將被 commit 的內容。
- 依 Human 授權進入 commit；不得自動 merge、push 或啟動下一 Gate。

## 9. Commit Policy（提交政策）

### 9.1 Commit 前置條件

Commit 前必須全部成立：

- Human 已批准 Gate close 與 commit scope。
- Reviewer 已審查 final diff，包含 Human close 後 closure record 的機械性 delta；QA evidence 已完成適用的 evidence review。
- Documentation Sync 已完成。
- Working tree 中使用者既有／無關變更已被識別，不會被混入。
- `git diff --check` 與批准的 tests／checks 已完成，或 failure／exception 已明確由 Human 接受。
- 沒有 secret、physical DB data、dump、temporary artifacts 或範圍外檔案被 stage。

### 9.2 Staging 與 Commit Scope

- 只 stage Human 批准且 Reviewer 已看過的 paths／hunks。
- 禁止以 `git add -A` 等方式盲目納入整個 working tree。
- Commit message 應描述主要 problem／outcome，不使用 `perfect`、`fully fixed` 等 overclaim。
- 一個 commit 優先對應一個可審查 Gate closure 或明確 Small Batch；若需拆分 commit，先由 Human 批准策略。
- Commit 後核對 commit hash、parent、name-status 與 working tree。

### 9.3 未授權行為

未經 Human 明確要求，不得：

- commit、amend、merge、push、rebase、reset 或改寫 history。
- 建立／刪除 branch 或 tag 作為流程捷徑。
- 因遠端落後就自行同步或公開 Repository。
- 將 Gate close approval 解讀為 merge／push／deployment approval。

### 9.4 Commit 後

- `PROJECT_STATUS.md` 若無法預先包含自身 closure commit hash，應明確記錄 parent／scope，並在下一次 handoff 以 Git 唯讀查詢核對 HEAD。
- Commit 是歷史記錄，不代表下一 Gate 已獲批准。
- Merge、push、release 與 deployment 各自需要符合當前 Human instruction 與安全條件。

## 10. Exceptions、Blockers 與 Scope Change

- 可在原批准 scope 內修正的 defect：走 correction loop。
- 需要新 architecture／requirement／major dependency／Schema／migration／security acceptance：停止並升級 Human。
- 環境暫時不可用：保留 evidence，標示 `BLOCKED` 或 `PARTIAL`，不得降低驗證標準來取得 PASS。
- 非阻塞的範圍外問題：登錄 follow-up，不插入目前 Small Batch。
- 任何例外都不得默默改變本文件、`AGENT_TEAM.md` 或 commit policy；流程治理變更需 Human 明確批准。

## 11. Workflow Definition of Done（流程完成定義）

一次 Gate-level 工作只有在下列條件成立時才完成：

- Scope、decision 與 Human approval 可追溯。
- Implementation、Review、QA 與 Evidence Review 均完成且角色分離。
- 必要文件已同步，claims 未超出證據。
- FAIL、limitations、not verified 與 deferred risks 均被保留。
- 沒有未處理的資料破壞、安全或 migration 風險需要 Human 決策。
- Human 已明確批准 Gate close。
- Commit 僅在額外授權與 final scope 核對後執行。

本文件的建立或更新不會自動啟動任何 Gate；Active Gate 與 next approved action 必須由 `PROJECT_STATUS.md`、本次 Git 證據及 Human 明確指示共同確認。
