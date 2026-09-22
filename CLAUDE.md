# CLAUDE.md — 專案工作規則（現行權威）

> **文件性質**：本檔為本 Repository 對 Claude Code 生效的 Durable Project Guidance（持久專案指引）。
> **建立依據**：GOV-01 治理層例外授權（Gate 結構外，不消耗任何 Gate 授權）。
> **建立日期**：2026-08-23

---

## 0. Source-of-Truth 優先順序

### 0.1 CLAUDE.md 與 AGENTS.md 的過渡關係

| 檔案 | 地位 | 說明 |
|------|------|------|
| **`CLAUDE.md`（本檔）** | **現行權威** | Claude Code 實際載入的專案規則。規則衝突時以本檔為準。 |
| `AGENTS.md` | **相容錨點（Deprecated）** | 內文保留不動，因其 §7.x 編號正被已核准的 Gate 0 ADR 引用。待 `UG-G1-SB5` 完成引用改寫後除役。 |

> **為何不直接刪除 AGENTS.md**：`DECISIONS.md`（DEC-016）、`FEATURE_REGISTRY.md`、
> `MULTI_SOURCE_DATA_CONTRACT.md`、`TRACEABILITY.md`、`SYSTEM_UPGRADE_MASTER_PLAN.md`
> 均以 `AGENTS.md §7.1` 形式引用工程不變量。這些引用來自**已經 PO 核准**的 Gate 0 交付物，
> 依 GOV-01 邊界不得變更其內容。因此本檔採「整段遷入並保留原編號」策略（見 §7），
> 舊引用在改寫前仍可對應到正確條文。

### 0.2 規格衝突處理順序

當文件、研究、既有決策與程式碼互相矛盾時，**不得自行選一個版本當答案**。優先順序：

1. Project Owner 在當前任務中的明確指示
2. 已核准的 ADR（`doc/evidence/DECISIONS.md`，狀態為 `APPROVED`）
3. Gate 0 已核准交付物（`SYSTEM_UPGRADE_MASTER_PLAN.md`、`FEATURE_REGISTRY.md`、
   `MULTI_SOURCE_DATA_CONTRACT.md`、`DB_MIGRATION_PLAN.md`、`PURGED_WALK_FORWARD_SPEC.md`、
   `REMAINING_RISKS.md`、`DOCUMENT_DRIFT_REMEDIATION.md`）
4. `doc/spec/PRD_Financial_Sentiment_System_v1.md`（產品目標與需求）
5. `doc/spec/SDD_Financial_Sentiment_System_v1.md`（架構與模組責任）
6. Research Requirements（研究轉譯後的工程要求）
7. 現有程式碼 —— 僅代表 Current State（目前狀態），**不是自動的設計真理**

若高階來源之間本身矛盾：停止重大實作 → 列出衝突 → 說明影響 → 提供方案 → 等待 PO 決策。

### 0.3 治理文件分工

| 文件 | 回答的問題 |
|------|-----------|
| `CLAUDE.md`（本檔） | 每次工作都不能忽略的工程原則與完成標準 |
| `doc/governance/TEAM_PLAYBOOK.md` | 實際的角色與三層攔截、PO 專屬批准事項、Gate／Small Batch 迴圈、失敗模式目錄 |
| `doc/governance/PROJECT_STATUS.md` | 專案目前做到哪裡、哪個 Gate 已關閉 |

---

## 1. Project Mission（專案使命）

本 Repository 同時具有兩個目的：

1. 建立可執行的「金融情緒與股價趨勢預測系統」，完成從資料擷取、清洗、情緒分析、資料儲存、
   特徵工程、機器學習到 BI 視覺化的 End-to-End（端到端）流程。
2. 作為個人轉職與成果發表作品，保留足以說明工程能力的 Decision Evidence（決策證據）與
   Problem-Solving Evidence（問題解決證據）。

因此不得只追求「程式能跑」。重要修改必須能回答：為什麼要改？根據哪一項規格或實測證據？
有哪些替代方案？有什麼 Trade-off？如何驗證？

---

## 2. Language Policy（語言規則）

- 與使用者溝通預設使用繁體中文。
- 必須使用英文專業術語時，第一次出現寫成：`English Term（中文翻譯）`。
- 程式碼、套件名稱、API、SQL、檔名與正式技術名詞保留原文。

---

## 3. Development Environment（開發環境）

- VS Code + Dev Containers + Docker Compose
- Python / PostgreSQL 18（Docker container）
- PostgreSQL 開發資料透過 bind mount 持久化於本機 `.devcontainer/postgres-data/`

**未經 PO 明確要求，不得**：把開發資料庫遷移到雲端；刪除／重建／清空／修改
`.devcontainer/postgres-data/` 的實體資料檔；以「重建環境」為由執行破壞性資料庫操作；
假設 physical data directory 等同可攜式備份（備份需用 `pg_dump` logical backup）。

---

## 7. Engineering Invariants（不可輕易違反的工程原則）

> **編號說明**：本節自 `AGENTS.md §7` 整段遷入並**刻意保留原編號**（§7.1 仍是 §7.1）。
> 原因見 §0.1 —— 已核准的 Gate 0 交付物以 `§7.1` 形式引用這些條文，編號一改即全數斷鏈。
> 本節為這些引用的現行權威定義。

### 7.1 Database & ETL（資料庫與 ETL）

- ETL 重複執行應維持 Idempotency（冪等性）。
- Database Error（資料庫錯誤）**不得被偽裝成 Empty Result（沒有資料）**。
- 失敗與「真的沒有資料」必須可區分。
- 修改 Database Schema（資料庫綱要）前，先檢查 `schema.sql`、`init_db.py`、DBWriter
  與所有依賴欄位的模組。
- 不得同時維護兩套互相不一致的 Schema 定義。
- 不得做 destructive migration（破壞性遷移）除非使用者明確同意，且已有備份／回復方案。
- 任何 fallback（備援）資料源都必須符合明確 Data Contract（資料契約），不得將
  provider-specific ID（資料提供者專用代碼）直接當成系統唯一識別碼而未經設計。

### 7.2 NLP / Checkpoint / Cache（NLP、檢查點與快取）

- Batch Checkpointing（批次檢查點）只有在一筆工作「確實成功完成」後才能推進。
- LLM 呼叫失敗時，不得把未完成的 fallback 分數誤標示為完成，除非規格明確定義
  fallback 分數就是正式結果。
- Cache Hit（快取命中）代表已取得可重用結果時，不應因分數仍落在 fuzzy range（模糊區間）
  而再次呼叫 LLM；若要例外，必須有版本或品質策略。
- 快取失敗、LLM 失敗與 NLP 計算失敗要能被觀測、測試與重試。

### 7.3 Tracking Keywords（追蹤關鍵字）

- `is_active = FALSE` 的 Soft Delete（軟刪除）狀態不得被 AI Trend Discovery
  （AI 熱門詞探索）無意重新啟用。
- 停用關鍵字不得意外改變原本的 category（分類）。
- Hard Delete（硬刪除）可能破壞 Data Lineage（資料血緣），執行前必須取得明確許可。

### 7.4 Time-Series & ML（時間序列與機器學習）

- 不得使用會讓未來資料進入訓練集的隨機時間序列切分方式。
- Phase 3 驗證應使用 Walk-Forward Validation（滾動前向驗證）或其他明確保持時間順序的方法。
- 必須防止 Look-ahead Bias（前視偏誤／未來資料洩漏）。
- 在建立 target label（目標標籤）與 feature（特徵）前，先定義 Prediction Time Convention
  （預測時間約定）：模型在什麼時間點做預測，可使用哪些已知資料。
- 不得只用 Accuracy（準確率）宣稱模型有效；評估方式要與研究要求、資料不平衡與實際目標相符。
- 不得因研究報告提到某演算法，就把它當成一定優於其他方法。Research Evidence（研究證據）
  與本專案實測結果要分開陳述。

---

## 8. Research-to-Code Discipline（研究到程式碼的轉譯規則）

Research（研究）不是直接翻譯成 Code（程式碼）。重要研究結論應經過：

`Research Evidence → Engineering Interpretation → Requirement → Design → Implementation → Test`

對每一項研究驅動的重大修改，至少說明：研究指出什麼？是否真的適用本專案資料與市場？
這是 Required／Candidate／Hypothesis 還是 Background？哪個模組負責？如何驗證？

若證據不足，不得把 Engineering Judgment（工程判斷）寫成「學術已證明」。

---

## 9. Evidence Labels（證據標籤）

所有交接、審查與 Gate 報告的量化描述都必須標註證據標籤。
**每個標籤必須附上可重跑指令；不可重跑者必須說明原因。**

| 標籤 | 定義 | 可重跑指令 / 不可重跑原因 |
|------|------|--------------------------|
| `VERIFIED THIS SESSION` | 本次工作中由回報者直接執行並取得結果 | **必須附完整指令與原始輸出**。例：全套測試指令、契約驗證指令（見 §13.1） |
| `PREVIOUSLY VERIFIED` | 先前已有可追溯驗證紀錄，本次未重跑 | **必須指出紀錄位置**（哪個 Gate closure、哪個 commit hash）。不可重跑原因：屬歷史狀態，當前環境已改變 |
| `IMPLEMENTATION EVIDENCE` | 程式碼、diff 或實作執行結果支持 | 附 `git show <hash> --stat` 或檔案:行號。**不等於獨立驗證** |
| `REPORTED, NOT INDEPENDENTLY VERIFIED` | 由他人回報，本次未獨立查證 | **不可重跑**：回報來源不在本次可控範圍。必須標明回報者與回報位置 |
| `INFERENCE` | 由已知證據推導 | **不可重跑**：推論非執行結果。必須列出推論依據的已驗證前提 |
| `ASSUMPTION` | 為推進工作暫時採用，證據不足 | **不可重跑**：假設尚未驗證。必須列出驗證此假設所需的條件 |
| `ENGINEERING JUDGMENT` | 基於工程經驗的選擇或評估 | **不可重跑**：判斷非事實。不得宣稱為研究事實或實測結果 |
| `NOT VERIFIED` | 尚未驗證或證據不足 | **不可重跑**：明確宣告未驗證。必須說明未驗證的具體範圍 |

### 9.1 使用規則

- 使用 `VERIFIED THIS SESSION` 時**必須同時說明驗證範圍**。
  例：fresh initialization 已驗證，不等於 migration、production 或 cloud deployment 已驗證。
- **降級環境的通過不得寫成「全數驗證」**：若套件缺席使測試走 fallback 路徑，
  必須明確標示哪些路徑未經真實驗證（見 §13.3）。

### 9.2 禁用詞

無對應驗證證據時嚴禁使用：
`100% reliable`、`perfect`、`enterprise-grade`、`production-ready`、`guaranteed`、
`completely prevents`、`永遠不會`、`完美解決`、`零誤差`

---

## 9A. Verification Design（驗證的設計）

> **編號說明**：沿用 §11A 的作法插入而不重編。**不佔用 §10** ——
> `AGENTS.md §10`（Evidence & Claim Discipline）已被已核准的 Gate 0 交付物引用
> （`doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §7.1 Small Batch Briefs 的 Requirement Source 欄），
> 佔用會造成同名不同物。
>
> **與 §9 的關係**：§9 管的是**「證據要怎麼標示」**；本節管的是
> **「什麼東西才有資格成為證據」**。一個不可能失敗的檢查，通過了也不產出證據。

### 9A.1 驗證必須為偵測而寫，不是為通過而寫【強制】

> **結構上無法失敗的檢查不是檢查。**

**判準**：寫完一個檢查後，必須能回答「有哪一種輸入會讓它 FAIL？」
若答案是「沒有」，或想不出來，它產出的就不是證據，是**通過的外觀**。

**本規則的由來**（UG-Gate-0 V8，PO 判定）：

跨文件契約驗證的 B4 檢查原本寫成

```bash
grep "fillna" FEATURE_REGISTRY.md | grep -iE "comment|push"
```

第二個 `grep` 把搜尋範圍限制在留言與推文欄位 —— 而當時真正的缺陷在**情緒欄位**。
**該檢查結構上就不可能發現那個缺陷。** 它每次都通過，因為它只看已知沒問題的地方。

> PO 的原話：「B4 是為了通過而寫的，不是為了偵測而寫的。」

改採**契約反查法**（從契約要求出發列舉所有應受約束的對象，逐一反查文件是否滿足，
而非從已知答案出發湊 grep）之後，新增的 B8 檢查**立刻 FAIL**，抓出三個缺漏的 ADR。

同型錯誤在本專案出現過第二次：以檔案粒度的靜態 `grep` 判斷「哪些測試覆蓋某模組」，
把「測試把該模組換成 stub」讀成「測試覆蓋該模組」——
靜態掃描在原理上分不出 `use` 與 `replace`。改用 runtime 歸因後，
A 類證據由 97 個縮為 42 個（見 `doc/upgrade/gates/closed/SB1_STEP1_BEFORE_SNAPSHOT.md` §4）。

### 9A.2 每項驗證必須附一個已知會 FAIL 的案例【強制】

宣稱一項檢查「有效」時，必須能出示**一個會讓它 FAIL 的具體案例，並實際執行過**。

- **出示不了 known-FAIL 案例的檢查，不計入證據。**
- 適用範圍：pre-commit hook、驗證腳本、測試斷言，以及任何形式的把關機制。
- 送審時的對應要求見 `gate-submit` skill 產出 6。

**為什麼**：一個**從未失敗過**的檢查，與一個**永遠不會失敗**的檢查，
在輸出上完全無法區分 —— 兩者都只印 PASS。
能區分兩者的唯一方式，是刻意讓它失敗一次。

**實例**（GOV-04）：四項 pre-commit 檢查各建立一個 known-FAIL 案例。
其中**檢查 2 第一次回報的「通過」是假的** ——
測試用的 LF→CRLF 變更被 `core.autocrlf` 在 `git add` 時正規化掉了，
commit 實際上是被「沒有 staged 內容」擋下，**不是被檢查 2 擋下**。
改用尾隨空白重建（61/61 vs 無落差）才真正觸發該檢查。

> **若當時沒有要求 known-FAIL 案例，那個假通過會被當成「驗證完成」。**

同一次驗證還證實了 hook 的 `trap` 是承重的：移除後，被截斷的 commit
在契約已被破壞的情況下**仍會成功建立**（orphan commit `8e00b08`）。
沒有刻意製造失敗，這件事不會被發現。

---

## 11. Repository Safety（Repository 安全規則）

- 不要讀出、回傳、commit 或顯示 `.env` 中的 secret value（秘密值）。
- 不要 commit API key、token、password 或其他 credential。
- `.devcontainer/postgres-data/` 不得 commit。
- 不要修改 `.git/` 內部檔案。
- 未經 PO 明確要求，不要 force push、rebase public history、`reset --hard` 或刪除 branch。
- 需要新增 production dependency 時，先說明原因與替代方案。

---

## 11A. Destructive Git Command Discipline（破壞性 Git 指令紀律）

> **與 §11 的關係**：§11 管的是**「不得 commit 什麼」**（內容邊界）；
> 本節管的是**「不得怎麼執行」**（操作邊界）。兩者互補，不可互相取代 ——
> 一個乾淨的 commit 內容，仍可能是用會摧毀他人工作的方式產生的。

### 11A.1 受管制指令清單

> **本節 2026-08-31 修訂**：區分 `git restore` 的兩種形式（**GOV-08**，PO 授權）。

以下指令會改寫歷史、丟棄工作或不可逆地變更狀態：

| 指令 | 風險 |
|------|------|
| `git reset --hard` | 丟棄工作區與索引的所有未提交變更 |
| `git reset --soft` | 移動 HEAD，撤銷 commit |
| `git reset --mixed`（預設） | 移動 HEAD 並重置索引 |
| `git checkout -- <path>` | 丟棄該路徑的未提交變更 |
| `git restore <path>`（**不帶 `--staged`**） | 丟棄該路徑的未提交變更——以索引覆蓋工作區 |
| `git clean -f` / `-fd` / `-fdx` | 刪除未追蹤檔案（`-x` 連 gitignore 的也刪） |
| `git push --force` / `--force-with-lease` | 改寫遠端歷史 |
| `git branch -D` | 強制刪除分支 |
| `git rebase` | 改寫歷史 |
| `git commit --amend` | 改寫既有 commit |

> **⚠ 形似但「不」受管制**：`git restore --staged <path>`
>
> 它**只把索引項目退回 HEAD，工作區一個位元組都不動，沒有任何東西會遺失**。
> **不適用** §11A.2 的事前宣告與單行執行要求。
> 但**仍須依 §12.3 在報告中揭露**——它改變了 commit 的實際內容。
>
> **為何特別列出**（GOV-08，2026-08-31，`UG-G2-SB8` 收尾時發現）：
> 原文此列僅寫「同上」，未區分兩種形式。拆 commit 必須用 `--staged` 退出暫存，
> 若把它當受管制指令，每次拆 commit 都要走一輪宣告（摩擦成本、零安全收益）；
> 若因此把兩者當成同一件事，某天執行不帶 `--staged` 的形式就會真的毀掉工作。
> **兩個方向都有代價，因此明確分開。**

### 11A.2 執行規則【強制】

在**驗證、測試或除錯情境**下：

1. **上述指令不得出現在鏈式寫法中。**
   鏈式包含：`&&`、`;`、`||`、子 shell `( )`、`$( )`、迴圈內、
   以及任何「前一個指令的結果決定是否執行」的結構。
2. **必須單行執行**，一個指令一次工具呼叫。
3. **必須事前宣告**：執行前說明要做什麼、為什麼、預期結果。
4. 執行前先 `git status`；若有未提交工作，先確認是否需要保存。

### 11A.3 為何是「鏈式」而不只是「小心」

**這條規則來自一次實際事故（GOV-04, 2026-08-24）**：

```bash
# 事故指令（簡化）
... && [ "$B" != "$A" ] && git reset --soft HEAD~1 && git restore --staged <file>; ...
```

該鏈式條件在**非預期的分支**被觸發，撤銷了前一個 Gate 的 commit（GOV-03 的 `0269fb1`）。
當時的意圖是「只有在測試建立了 commit 時才撤銷」，但變數在鏈中的求值時機與預期不符。

**問題不在於執行者不小心，而在於鏈式結構讓「是否執行破壞性操作」變成一個
難以在讀取時驗證的條件。** 單行執行讓每次破壞性操作都是一個明確、可見、
可在事前攔截的決定。

（該次事故已完整復原，無工作遺失。）

### 11A.4 驗證流程的正面規範

**驗證與測試流程優先使用 Python 腳本，不使用 shell 鏈式條件。**

理由：

| | shell 鏈式 | Python 腳本 |
|---|---|---|
| 控制流可讀性 | 條件散在 `&&`／`\|\|` 中，求值時機易誤判 | 明確的 `if`／`try`／`finally` |
| 清理保證 | 前段失敗常導致後段清理不執行 | `finally` 可保證還原 |
| 狀態檢查 | 需靠 `$?`／`PIPESTATUS`，在子 shell 中語意易錯 | 直接取 `returncode` |
| 可稽核性 | 需逐段推敲 | 可逐行閱讀、可加註解 |

GOV-04 的驗證在改用 Python 腳本後，四項檢查的測試才得以在
「每次都保證還原、HEAD 不變」的前提下完成。

### 11A.5 例外

若確有必要在鏈式中使用受管制指令（例如已充分測試的自動化腳本），
必須事前向 PO 說明理由與防護措施並取得授權。

---

## 12. Commit Policy（提交政策）

### 12.1 授權

- Commit 需 PO 明確授權。授權針對**特定 scope**，對一項工作的授權不自動延伸到鄰近工作。
- 以檔名逐一 `git add`，**不使用** `git add -A` 或 `git add .`。
- Commit 前執行 `git status` 完整檢視 staging 內容。

### 12.2 格式／編碼／行尾變更也算 Scope【強制】

> **「內容無損」不等於「不需授權」—— 它變的是可追溯性。**

- 任何檔案的**編碼、行尾（CRLF/LF）、縮排或格式化變更，即使內容一字未改，
  仍屬 scope 變更，必須事前向 PO 揭露並取得授權。**
- **嚴禁**把格式正規化夾帶在有實質內容的 commit 裡。若確有必要統一格式，
  必須作為獨立提案、獨立 commit 執行。

**Commit 前強制檢查**（`gate-submit` skill 第 4 項）：

```bash
git diff --cached --numstat > /tmp/ns_raw.txt
git diff --cached --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

兩者有落差即代表存在純空白／行尾變更，**必須在報告中揭露**，不得逕行 commit。

> **本規則的由來**：commit `3baa34f` 在 Gate 0 收尾時意外把 `DECISIONS.md` 的行尾
> 由 CRLF 正規化為 LF。內容無損（`git diff -w` 驗證），但整檔 `git blame` 被壓成單一 commit，
> 且違反 DEC-001 明文的「Gate 0 不執行 line-ending normalization」。
> 機制成因：`core.autocrlf=true` 在 `git add` 時，對原本異常以 CRLF 儲存的 blob 進行正規化。

### 12.3 報告揭露義務

向 PO 回報 commit 結果時，**必須主動列出超出授權清單的檔案**，
不得僅寫在 commit message 中。逐檔標註「在授權交付物內／超出（附理由）」。

---

### 12.4 Pre-commit Hook（GOV-04）

本專案在 `.githooks/pre-commit` 提供機械化的 commit 前檢查，
把 §12.1~§12.3 的規則從「需要記得遵守」變成「不遵守就 commit 不了」。

#### 啟用（新 clone 或容器重建後必須執行一次）

```bash
git config core.hooksPath .githooks
```

> **這條指令是必要的，且會在下列情況失效**：新 clone、容器重建、換機器。
> `core.hooksPath` 是本機 git 設定，不隨版控傳遞。
>
> **刻意不使用 `.git/hooks/`**：該目錄不受版控，容器重建或換機後 hook 會**靜默消失**，
> 而且沒有任何訊號告訴你保護已經不在了。放在 `.githooks/` 至少讓 hook 本身可被審查、
> 可被 diff、可被追溯。

驗證是否已啟用：

```bash
git config --get core.hooksPath      # 應輸出 .githooks
```

#### 四項檢查

| # | 檢查 | 失敗行為 |
|---|------|---------|
| 1 | `scripts/verify/gate0_contract_check.py` | 非零 → abort |
| 2 | `git diff --cached --numstat` 與 `--numstat -w` 不一致 | abort，列出落差檔案 |
| 3 | staged 檔名含 `.env`／`.env.*`（`.env.example` 除外）／`settings.local.json`／`*.pem`／`*.key`／`id_rsa*`；**或** staged 新增內容含 `pass(word)?=` 樣式且值非 `<…>` 佔位符（GOV-13，2026-09-10，檔名判準與內容判準互補，非取代） | abort |
| 4 | 列印 staged 檔案完整清單 | 僅顯示，不擋 |

#### 刻意不放進 hook 的東西

**測試套件不在 hook 內執行。** commit 在 Windows host 上進行，
而 §13.0 已確立 host 是降級環境 —— 在 hook 裡跑測試等於強制執行一批
GOV-02 已認定為無效證據的結果，還會製造「已驗證」的錯覺。
測試屬 `gate-submit` skill 的職責，在 dev container 內執行。

hook 內也不進行任何寫入或網路操作。

#### Fail closed

hook 設有 `trap 'exit 1' PIPE HUP INT TERM`。若 hook 因輸出被截斷
（例如 `git commit | head`）或其他訊號中途死亡，一律以非零退出。

**這不是理論考量**：GOV-04 的受控實驗證實，移除該 trap 後，
`git commit | head -4` 在契約已被破壞的情況下**仍會成功建立 commit** ——
hook 印出 ABORT 卻沒擋住，也就是 fail open。
trap handler 本身**不得寫入任何輸出**，否則寫入已關閉的管道會再次觸發 SIGPIPE，
使 handler 死在 `exit` 之前（同樣 fail open）。

> 一個被中斷時會 fail open 的檢查，比沒有檢查更危險 —— 它提供的是安全的錯覺。

#### 繞過（GOV-12 修訂，2026-09-06，PO 授權）

**兩種方式，範圍與授權要求都不同。⚠ 兩者不等價。**

| 方式 | 範圍 | 授權 |
|------|------|------|
| **【偏好】具名出口** `SKIP_CHECK2_REASON="…"` | **只跳過檢查 2**；檢查 1／3／4 照常執行且照常擋 | **情況 (2)／(3) 不需事前授權**；理由字串**必須指名情況分類** |
| **【最後手段】** `git commit --no-verify` | **停用全部四項，含檢查 3 秘密偵測（檔名與內容兩層）** | **必須 PO 明確授權** |

```bash
# 偏好：只跳過檢查 2
SKIP_CHECK2_REASON="情況(2)：註解內縮排 4→8 格，1 行，零內容變動" git commit ...

# 最後手段：停用四項
git commit --no-verify
```

**兩者使用後都必須在回報中主動揭露原因與範圍**（§12.3）。

##### 情況分類（判準見 `.githooks/pre-commit` 檔頭的「已知限制」）

| 情況 | 內容 | 可否用具名出口 |
|------|------|--------------|
| **(1)** | **真的有純空白／行尾變更** | **不可** —— 那是 §12.2 的 scope 變更，**走原本的揭露與授權流程** |
| (2) | 重構造成的縮排位移 | 可 |
| (3) | `-w` 改變了 diff 的配對結果（**根本沒有空白變更**） | 可 |

##### 為什麼 (2)／(3) 不需事前授權，而這**不是**一項放寬

**§12.2 從來就沒有涵蓋情況 (2)／(3)。** 它要求授權的對象是
「編碼、行尾、縮排或格式化變更」，**而 (2)／(3) 的定義就是沒有那種變更** ——
`-w` 的落差是配對演算法的產物。

> **本 hook 上線後的六次繞過裡，五次是在為一件 §12.2 根本沒管的事情申請授權。**
>
> **這不是把 §12.2 放鬆，是停止把授權花在它管不到的地方。**
> **情況 (1) 那一次（`84e1598`）的授權要求，一個字都沒動。**

##### ⚠ 強制條件：理由字串必須指名情況分類

**分類由使用者自己做，而分類錯誤與分類正確，在輸出上長得一樣。**

因此 `SKIP_CHECK2_REASON` 的內容**必須指名是情況 (2) 還是 (3)，並附逐行查明的結論**。

> **分類要留在 commit 裡，不是只留在報告裡。**
> **報告會被讀一次，`git log` 會被讀很多次。**
> **寫在報告裡的分類，日後沒有人能不重新查一遍就知道當時判了哪一類。**

⚠ **hook 不檢查這件事** —— 它的長度下限是摩擦裝置，不是語意檢查
（見該處註解）。**檢查的人是複查方，每一次。**

---

## 13. Testing（測試）

> 本節內容為 **2026-08-23 GOV-02 實測結果**，非規劃或宣稱。所有指令可重跑核對。

### 13.0 正式環境定義【最重要】

| 環境 | 地位 | 組成 |
|------|------|------|
| **Dev Container** | **本專案的正式測試環境** | Python 3.14.6 + `requirements.txt` 全部 15 個套件 + `postgres:18` |
| Windows host | **輔助環境，非支援環境** | Python 3.10.11，15 個套件僅安裝 6 個 |

**強制規則**：

- 測試與驗證**預設在 dev container 內執行**。§13.1 的所有指令均以容器為預設執行環境。
- **host 的執行結果不得支撐任何關於 ML、NLP、重試邏輯或 LLM 路徑的宣稱。**
  host 缺 `sklearn`／`lightgbm`／`xgboost`／`jieba`／`snownlp`／`tenacity`／`google-generativeai`，
  這些路徑在 host 上走的是程式內建的 fallback 實作，**從未真實執行過**。
- host 執行的正當用途僅限於：語法回歸、文件契約檢查、不依賴上述套件的純邏輯測試。

**在容器內執行的方式**（容器名以實際為準）：

```bash
docker exec -u vscode -w /workspaces/Stock_Prediction_System2 \
  <app-container> python -m unittest discover -s tests -p "test_*.py"
```

> `-u vscode` 不可省略：`postCreateCommand` 以 `vscode` 身分安裝套件至 user site-packages，
> 以 root 執行會看到**全部套件 ABSENT**。

### 13.1 可用指令（預設在容器內執行）

```bash
# 全套測試（本專案唯一可用的測試指令）
python -m unittest discover -s tests -p "test_*.py"

# 跨文件契約驗證（Gate 0 交付物，exit 0 = 全通過）
python scripts/verify/gate0_contract_check.py

# 靜態語法檢查（逐檔）
python -m py_compile <file.py>

# 空白字元檢查
git diff --check
```

**2026-08-23 實測（容器內）**：全套測試 `OK`；contract-check `exit 0`。

本節的測試檔數與測試數可能隨開發推進而變動，用以下指令重新核對，
**不要引用本檔的舊數字**：

```bash
ls tests/*.py | wc -l
grep -ch "def test_" tests/*.py | awk '{s+=$1} END {print s}'
```

### 13.2 工具鏈缺口（兩個環境皆缺）

| 項目 | 狀態 | 影響 |
|------|------|------|
| `pytest` | **不存在** | 只能用 `unittest discover`，無法使用 pytest 專屬語法或外掛 |
| Lint（`ruff` / `flake8` / `black`） | **全部不存在**，且無 `pyproject.toml`／`setup.cfg`／`.flake8` | **本專案沒有 lint 檢查**。不得宣稱「已通過 lint」 |
| 型別檢查（`mypy`） | **不存在** | 無靜態型別保證 |
| Coverage（`coverage`） | **不存在** | **無法量測測試覆蓋率**。不得宣稱任何覆蓋率數字 |
| CI（`.github/workflows/`） | **不存在** | 無自動化驗證，所有檢查均為手動執行 |

### 13.3 host 的降級狀態【嚴禁據此宣稱】

以下為 **2026-08-23 實測**的 Windows host（Python 3.10.11）狀態：

| 套件 | host | 對測試的影響 |
|------|------|-------------|
| `numpy` / `pandas` / `streamlit` / `plotly` / `requests` / `bs4` / `yfinance` | PRESENT | 走真實路徑 |
| `sklearn` / `lightgbm` / `xgboost` | **ABSENT** | ML 測試走純 NumPy fallback 實作 |
| `psycopg2` | **ABSENT** | DB 測試走 `MagicMock` 替身，不觸及任何資料庫 |
| `jieba` / `snownlp` | **ABSENT** | NLP 分詞與情緒測試走 fallback |
| `tenacity` / `google-generativeai` / `python-dotenv` | **ABSENT** | 重試、LLM 呼叫、環境變數載入皆走替身 |

**降級的實際後果**（GOV-02 實測，非推論）：

| 模型名稱 | host 實際型別 | 容器實際型別 |
|----------|--------------|-------------|
| `logistic_regression` | `_FallbackLinearClassifier` | `sklearn.LogisticRegression` |
| `random_forest` | `_FallbackTreeEnsembleClassifier` | `sklearn.RandomForestClassifier` |
| `lightgbm` | `_FallbackTreeEnsembleClassifier` | `lightgbm.LGBMClassifier` |
| `xgboost` | `_FallbackTreeEnsembleClassifier` | `xgboost.XGBClassifier` |

> 在 host 上，`lightgbm` 與 `xgboost` 對映到**同一個** fallback 類別 ——
> 所謂「四模型競技」在 host 上實際只有兩種相異實作。

**強制規則**：

- **嚴禁**把 host 的通過寫成「100% PASS」「全數驗證」「production-ready」。
- host 的降級是**靜默的**：`src/ml/baseline_models.py` 與 `src/ml/model_trainer.py`
  使用模組內 `try/except ImportError` 條件式 import，因此測試檔照樣全部載入、
  測試照樣全過，輸出裡看不出真實模型路徑一次都沒跑過。
- 回報測試結果時**必須標明執行環境與 Python 版本**（見 `gate-submit` skill 第 2 項）。
  未標示環境的測試結果一律視為無效證據。

### 13.4 測試封閉性缺口

GOV-02 量測發現 **9 個測試不具封閉性**，其行為取決於環境是否具備資料庫憑證與 DB 內容。
完整清單與衍生問題見 `doc/evidence/DOCUMENT_DRIFT_REMEDIATION.md`
的「GOV-02 追加發現：測試封閉性」章節（HERM-01 ~ HERM-09、HERM-A ~ HERM-E）。

**在容器內執行測試時的必要防護**：容器的 `network_mode: service:db` 使 `localhost:5432`
直達綁定 `postgres-data` 的真實開發資料庫。若要在容器內跑測試，
**必須以 `DB_HOST`／`DB_PORT` 覆寫指向臨時資料庫**，並在執行前確認
`current_database()` 與連線埠確實是臨時目標。

### 13.5 測試原則

- 測試不應依賴真實 Gemini API 或不可控外部網站作為唯一驗證方式；優先 mock / fixture。
- Integration Test 需要 PostgreSQL 時，必須避免破壞開發用真實資料。
- 測試資料庫與本機實際開發資料要明確隔離。
- 新增 bug fix 時，若可行應先建立會重現問題的測試，再修復。

---

### 13.6 環境可重現性（GOV-03）

> §13.0 把 dev container 定為正式環境，但**「正式」不等於「可重現」**。
> 本節說明使 GOV-02 基線能在未來重現的機制。

#### lock 檔的角色

| 檔案 | 性質 | 內容 |
|------|------|------|
| `requirements.txt` | **意圖檔** | 宣告專案需要哪些套件。**不是**可重現性保證 —— 多數項目無版本上界，部分完全無約束（見 DRIFT-016）。 |
| `requirements.lock.txt` | **事實檔** | 宣告 GOV-02 驗證當時實際裝出的**精確版本**（含傳遞依賴）。這是重現基線的依據。 |

兩者**並存**。`requirements.txt` 的約束補強屬另案，GOV-03 未處理。

#### 環境釘選的三層

| 層級 | 機制 | 位置 |
|------|------|------|
| 基底映像 | digest 釘選 | `.devcontainer/Dockerfile` 的 `FROM ...@sha256:` |
| Python 套件 | 精確版本 `==` | `requirements.lock.txt` |
| 安裝身分 | `vscode`（非 root） | `devcontainer.json` 的 `postCreateCommand` |

> 第三層不可省略：以 root 安裝會裝到系統 site-packages，而 `vscode` 身分執行時看不到，
> 導致「套件全部 ABSENT」的假象（GOV-02 實測踩過此坑）。

#### 如何重新產生 lock

**前提**：必須從一個**已驗證可用**的容器產出，不是從任意環境。

```bash
docker exec -u vscode <app-container> python -m pip freeze
```

`-u vscode` 不可省略 —— 以 root 執行只會得到基底映像自帶的少數套件。

#### 何時該更新 lock

| 觸發情境 | 動作 |
|----------|------|
| 新增或移除直接依賴 | 先改 `requirements.txt`（意圖），再重建容器，再重新產生 lock |
| 需要套件安全性更新 | 刻意提升版本後重新產生 lock |
| 需要更新基底映像 | 改 Dockerfile 的 digest，重建，重新產生 lock |
| **例行開發** | **不更新**。lock 漂移應是刻意行為，不是副作用 |

#### 更新後必須執行淨重建驗證

**未經淨重建驗證的 lock 只是一份未經證實的清單。** 任何 lock 或 digest 變更後：

1. 以 `Dockerfile` + `requirements.lock.txt` 建立**全新的拋棄式容器**
   （獨立名稱、不掛 `postgres-data`、不進 compose 網路、不干擾運行中的開發容器）
2. 在其中執行全套測試 —— 結果須與更新前的基線一致
3. 在其中重跑模型型別對照 —— 六列須與 §13.3 的 container 欄完全一致
4. 比對 `python --version` 與 `pip freeze`
5. 驗證後**拆除**拋棄式容器與映像

> **任一項不符時，回報不符本身，不得調整 lock 使其通過。**
> 不符代表某個版本已無法取得或行為已改變 —— 那是必須被知道的資訊，
> 調整 lock 只會把它藏起來。

#### GOV-03 淨重建驗證結果（2026-08-23）

| 項目 | 結果 |
|------|------|
| 全套測試 | `Ran 154 tests` / `OK` |
| 六列型別對照 | 全部 MATCH |
| `python --version` | 3.14.6（與 GOV-02 相同） |
| `pip freeze` | 87 套件，與 GOV-02 **逐行完全相同** |

---

---

## 14. Definition of Done（完成定義）

一個非微小任務只有在以下條件成立時才算 Done：

- 行為符合已確認的 requirement。
- 相關測試或可接受的驗證已通過，**且已揭露驗證邊界與依賴狀態**。
- 沒有已知未說明的資料破壞風險。
- 沒有偷偷改變 public behavior 或 Database Schema。
- **沒有夾帶未揭露的格式／行尾變更**（§12.2）。
- 相關文件已同步，或明確說明為什麼不需更新。
- 有意義的 Decision / Challenge 已留下證據（見 `evidence-sync` skill）。
- 最終摘要明確區分「已驗證」與「尚未驗證」，並附證據標籤（§9）。

對 ML 任務額外要求：時間順序與資料可用時間已明確；無已知 Look-ahead Bias；
Evaluation 不只依賴單一 Accuracy；結果能與合理 baseline 比較。

---

## 15. Skills（技能）

本專案的強制 SOP 以 Claude Code skill 形式提供，位於 `.claude/skills/`：

| Skill | 用途 |
|-------|------|
| `gate-submit` | Gate／SB 送審前與 commit 前的自檢與證據產出 |
| `evidence-sync` | ADR（`DECISIONS.md`）、Challenge（`CHALLENGES.md`）與追溯矩陣的建立與傳播 |
| `small-batch-orchestrator` | Gate／Small Batch 的規劃、執行循環與結案 |
| `bug-fix-protocol` | 除錯與修復的兩道 Human Gate 流程 |

> `.agents/skills/` 為**已棄用路徑**（Claude Code 不載入該路徑），僅保留為歷史錨點。
> 各檔已加棄用標頭指向新路徑；既有文件中的舊路徑引用改寫排入 `UG-G1-SB5`。

---

## 16. Document Structure & Lifecycle（文件結構與生命週期）

> **建立依據**：GOV-05（PO 授權，2026-08-24）。
> **完整文件地圖見 `doc/README.md`** —— 該檔回答「這份文件屬於誰、還活著嗎」。

### 16.1 資料夾語意

| 資料夾 | 歸屬 | 生命週期 |
|--------|------|---------|
| `doc/spec/` | 全專案 | 長青（PRD、SDD） |
| `doc/governance/` | 全專案 | 長青（團隊、流程、現況） |
| `doc/evidence/` | 全專案 | **只增不減**（ADR、Challenge、追溯、漂移登錄） |
| `doc/research/` | 全專案 | 長青（研究輸入） |
| `doc/upgrade/` | **現行升級計畫** | 進行中 |
| `doc/archive/` | 前任團隊 | **已結束，唯讀** |

判斷法則：**`upgrade/` 是現在正在做的事；`archive/` 是已結束的事；其餘跨計畫共用。**

### 16.2 `archive/` 不得修改【強制】

`doc/archive/` 內的文件記錄的是**當時的計畫與當時的結構**。竄改它們等於竄改歷史紀錄。
其中對舊路徑（如 `doc/engineering/`）的引用**刻意保留原樣**，不予更新。

### 16.3 Gate／SB 提案的生命週期【強制】

> **本節 2026-09-01 修訂**：補上 Gate 層級文件的生命週期，並移除硬編碼的 SB 數量
> （**GOV-09**，PO 授權）。

Gate 1–4 的 Small Batch 數量以 `doc/upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` §5.2 為準
（**該處為唯一權威**）。若每個 SB 的提案與報告都永久留在 `doc/upgrade/gates/`，
該資料夾會比整頓前的 `doc/engineering/` 更難讀 ——
**分類只是把成長裝進盒子，不會讓它變少。**

| # | 規則 |
|---|------|
| 1 | Gate A 提案與 Gate B 報告是**過程文件**，不是永久資產 |
| 2 | SB 通過 Gate B 後，結論已分別吸收進 `evidence/DECISIONS.md`、`evidence/TRACEABILITY.md`、`upgrade/contracts/` 與 `upgrade/SYSTEM_UPGRADE_MASTER_PLAN.md` |
| 3 | 此時該提案文件**移入 `doc/upgrade/gates/closed/`** |
| 4 | **`gates/` 根層永遠只保留審查中的 SB**（通常 1–2 份） |
| 5 | **Gate 層級的啟動申請書（`GATE*_STARTUP_APPLICATION.md`）沿用同一生命週期** —— 該 Gate 關閉時移入 `closed/`。**不另創類別。** |
| 6 | 規則 3、5 的搬移是**該次收尾的一部分**，不是事後補做。執行檢查見 `gate-submit` skill 產出 8 |

> **為何補規則 5、6**（GOV-09，2026-09-01）：原四條規則**只涵蓋 SB 提案**，
> Gate 層級的啟動申請書沒有對應生命週期 ——
> **這正是 `GATE1_STARTUP_APPLICATION.md` 在 Gate 1 關閉後仍留在根層的成因。**
>
> 而規則 3 在 `UG-G2-SB8` 結案時**已經存在**，§0.5 #7 也記載過同一義務曾在
> `UG-G1-SB1` 結案時「揭露了卻沒有執行」—— **仍然漏了第二次。**
>
> **對照組就在 §0.5 同一份清單裡**：**#10 是通則**（「每個 SB 的 Gate B 通過時，
> 該 SB 新增的 ADR 一併轉 `APPROVED`」），**所以 DEC-029～031 一個都沒漏**。
>
> **綁事件的那條運作正常，綁個案的那條漏了兩次。**

> **為何移除「24 個」**：該數字已經過期（實際為 26：Gate 1 五個、Gate 2 九個、
> Gate 3 七個、Gate 4 五個），而且 `UG-G2-MIG` 不在任何一個編號序列裡，
> **連「幾個」都不是一個穩定的問題**。
> `PROJECT_STATUS.md` §0.5 #5 早已登記「複製一份即為下一個 DRIFT」——
> **預測成真了。修法不是把 24 改成 26，是把數字拿掉。**

要知道「現在在做什麼」，打開 `doc/upgrade/gates/` 就是答案。

### 16.4 搬移受驗文件時的連帶義務【強制】

`scripts/verify/gate0_contract_check.py` 以 `DOC_PATHS` 逐檔對映受驗文件路徑。

**搬移任何受驗文件時，必須在同一個 commit 內同步更新 `DOC_PATHS`。**
否則 contract-check 失敗，`.githooks/pre-commit` 檢查 1 會擋下所有後續 commit。

新增文件時亦須同步更新 `doc/README.md` 的逐份文件表 —— 
一份沒有登錄在地圖上的文件，等同於下一份「不知道屬於誰」的文件。
