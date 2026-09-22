---
name: gate-submit
description: >-
  Use this skill before submitting any Gate or Small Batch for Project Owner review, and before
  every git commit. Produces the six mandatory evidence artifacts: raw contract-check output,
  raw test output with dependency-status disclosure, a per-file authorization audit of the commit
  contents, whitespace/line-ending drift detection, an evidence-label table with rerun commands, and a known-FAIL case table proving each check can actually fail.
  Blocks reporting degraded-environment passes as full verification, and blocks checks with no failure capability from counting as evidence.
---

# gate-submit — 送審與 Commit 前自檢

本 Skill 定義向 Project Owner（PO）送審前、以及執行任何 `git commit` 前的**強制自檢程序**。

**核心原則**：PO 依報告做決策，不一定會展開 commit message 或自行重跑指令。
因此**報告本身**必須攜帶完整可稽核證據，不能把關鍵資訊藏在別處。

---

## 1. 何時啟動

- Gate 或 Small Batch 送審前
- 任何 `git commit` 之前
- PO 要求「回報驗證結果」時

---

## 2. 八項強制產出

以下七項**全部**都要出現在送審報告中。缺任一項即為不完整交接。

### 產出 1：契約驗證原始輸出

執行並**貼上原始輸出**：

```bash
python scripts/verify/gate0_contract_check.py
echo "EXIT=$?"
```

**規則**：

- 不得只寫「全綠」「全部通過」「11/11 PASS」等摘要而不附原始輸出。
- 若腳本有 `WARN` 行（例如已登錄的遺留項目），**必須一併貼出**，不得過濾。
- 若 exit code 非 0，**不得送審**。

### 產出 2：執行環境 + 測試原始輸出 + 依賴狀態表

> **未標示執行環境的測試結果一律視為無效證據。**

#### 2a. 執行環境（必填，缺一不可）

| 欄位 | 內容 |
|------|------|
| 執行環境 | `container` 或 `host`（二選一，必須明確標示）|
| Python 版本 | `python --version` 的原始輸出 |
| 容器名稱 | 若為 container，附容器名；若為 host，寫明「非支援環境」 |

```bash
python --version
```

**規則**：

- 本專案的**正式測試環境是 dev container**（見 `CLAUDE.md` §13.0）。
- 在容器內執行時**必須**加 `-u vscode`；以 root 執行會看到全部套件 `ABSENT`。
- **host 的結果不得支撐任何 ML／NLP／重試／LLM 路徑的宣稱**，
  回報時必須明確標註「host＝非支援環境」。

#### 2b. 測試原始輸出

執行並**貼上原始輸出**：

```bash
python -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -5
```

#### 2c. 依賴狀態表

```bash
python -c "import importlib.util as u; [print(f'{m:26}', 'PRESENT' if u.find_spec(m) else 'ABSENT') for m in ['numpy','pandas','streamlit','plotly','sklearn','lightgbm','xgboost','psycopg2','jieba','snownlp','tenacity','dotenv']]"
```

**規則**：

- 必須把 `ABSENT` 的套件對應到「哪些測試因此走 fallback 路徑」。
- **嚴禁**把降級環境的 `OK` 寫成「100% PASS」「全數驗證」「production-ready」。

**正確寫法範例（host）**：

> 執行環境：**host（非支援環境）**，Python 3.10.11。
> 全套測試 `OK`。但 `sklearn`／`lightgbm`／`xgboost` 缺席，ML 測試走純 NumPy fallback；
> `psycopg2` 缺席，DB 測試全走 mock。**本結果不支撐任何模型行為的宣稱。**

**正確寫法範例（container）**：

> 執行環境：**container**（`<name>`），Python 3.14.6，15 套件齊備。
> 全套測試 `OK`。ML 路徑走真實 sklearn／lightgbm／xgboost。
> DB 指向臨時資料庫（已確認 `current_database()` 與連線埠），未觸及開發資料。

#### 2d. 若在容器內連線資料庫

容器的 `network_mode: service:db` 使 `localhost:5432` 直達真實開發資料庫。
若測試會連線，**必須**以 `DB_HOST`／`DB_PORT` 覆寫指向臨時 DB，並回報綁定確認：

```sql
SELECT current_database(), current_user, inet_server_port();
```

確認打的是臨時目標而非真實 DB，才可執行。

### 產出 3：Commit 檔案清單 + 逐檔授權稽核

```bash
git diff --cached --name-only
```

把結果與 PO 的**明確授權清單**逐檔比對，產出下表：

| 檔案 | 授權狀態 | 說明 |
|------|---------|------|
| `<path>` | 在授權交付物內 | — |
| `<path>` | **超出授權清單** | 理由：⋯⋯ |

**規則**：

- 任何不在授權清單上的檔案，**必須在報告正文中明確標出**。
- 寫在 commit message 裡**不算**揭露（`CLAUDE.md` §12.3）。
- 若有超出項目而無法說明理由，**不得 commit**，應先請示 PO。
- **證據檔內容掃描**：新增／修改的證據檔（`doc/upgrade/gates/evidence/` 等）跑
  `git grep -n -i -E "pass(word)?\s*=\s*\S+"`，結果零命中或逐行說明為佔位符
  （`<…>`）／拋棄式臨時值，不得省略（`CHALLENGES.md` CHAL-008 §6：字面憑證已
  在證據檔裡出現過三次，帶引號、不帶引號的寫法都撞過）。

### 產出 4：格式／行尾夾帶偵測

```bash
git diff --cached --numstat > /tmp/ns_raw.txt
git diff --cached --numstat -w > /tmp/ns_nows.txt
diff /tmp/ns_raw.txt /tmp/ns_nows.txt
```

**判讀**：

- `diff` 無輸出 → 無格式夾帶，可繼續。
- `diff` 有輸出 → **偵測到純空白／行尾變更**。必須：
  1. 在報告中揭露受影響檔案與行數差異
  2. 說明成因（常見成因：`core.autocrlf=true` 對原以 CRLF 儲存的 blob 正規化）
  3. **取得 PO 事前授權**才能 commit（`CLAUDE.md` §12.2）

補充檢查單一檔案的實際行尾：

```bash
git show HEAD:<path> | file -
file <path>
```

### 產出 5：證據標籤表

報告中每一項量化宣稱都必須附標籤與重跑方式：

| 宣稱 | 證據標籤 | 可重跑指令 / 不可重跑原因 |
|------|---------|--------------------------|
| ⋯⋯ | `VERIFIED THIS SESSION` | `<完整指令>` |
| ⋯⋯ | `PREVIOUSLY VERIFIED` | 紀錄位置：`<commit hash / Gate closure>`；本次未重跑 |
| ⋯⋯ | `NOT VERIFIED` | 未驗證範圍：⋯⋯ |

標籤定義與完整規則見 `CLAUDE.md` §9。

---

### 產出 6：known-FAIL 案例對照表

> **出示不了 known-FAIL 案例的檢查，不計入證據**（`CLAUDE.md` §9A.2）。

報告中每一項被當作「把關機制」的檢查，都必須列出一個**已實際執行過、會讓它 FAIL 的案例**：

| 檢查 | known-FAIL 案例 | 實測結果 | 復原確認 |
|------|----------------|---------|---------|
| `<檢查名稱>` | `<具體構造方式>` | `<FAIL 的原始輸出>` | `<案例已還原，HEAD 未變>` |

**規則**：

- 案例必須**實際執行過**，不得只描述「應該會失敗」。
- 必須貼出該案例的**原始 FAIL 輸出**，不得只寫「已驗證會擋下」。
- 案例造成的變更必須**還原**，並確認 `HEAD` 與工作區狀態未受影響。
- 若某項檢查**無法構造出 FAIL 案例**，必須明確標示
  「**本檢查無失敗能力，不計入證據**」，不得列為已驗證。

**判準**（`CLAUDE.md` §9A.1）：寫完一個檢查後，必須能回答
「有哪一種輸入會讓它 FAIL？」。答不出來的，產出的不是證據，是通過的外觀。

**假通過的實例**：GOV-04 驗證 pre-commit 檢查 2（格式夾帶偵測）時，
第一次的 known-FAIL 案例用 LF→CRLF 變更構造，回報「成功擋下」。
**那是假的** —— 該變更被 `core.autocrlf` 在 `git add` 時正規化掉，
commit 實際是被「沒有 staged 內容」擋下，檢查 2 根本沒被觸發。
改用尾隨空白重建（numstat 61/61 vs 無落差）才真正觸發。

> 這說明 known-FAIL 案例本身也要檢查：**要確認 FAIL 是被那項檢查擋下的，
> 而不是被其他原因擋下的。**

---

## 3. 失敗範例（本 Skill 必須能擋下的東西）

以下是**已知會 FAIL** 的報告寫法。任一出現即應退回重做。

### 失敗範例 A：把降級環境寫成全數驗證

> ❌ 「全套測試 154/154 PASS，系統已完整驗證，可進入下一 Gate。」

**為何 FAIL**：`sklearn`／`lightgbm`／`xgboost`／`psycopg2` 缺席，這些路徑走 fallback 或 mock，
從未真實執行。「完整驗證」是不成立的宣稱，且違反 `CLAUDE.md` §9.1 與 §13.3。

**可用產出 2 的指令重現此判定**：依賴表會顯示多個 `ABSENT`。

### 失敗範例 B：只寫摘要不附原始輸出

> ❌ 「contract-check 全綠。」

**為何 FAIL**：無法稽核。PO 無從得知是 11 項全過還是腳本根本沒跑完，
也看不到 `WARN` 行揭露的已登錄遺留項目。違反產出 1。

### 失敗範例 C：超出授權的檔案只寫在 commit message

> ❌ 報告列出檔案清單，但未標註哪些超出授權；理由寫在 commit message 第三段。

**為何 FAIL**：PO 依報告做決策。違反 `CLAUDE.md` §12.3。
實際案例：commit `3baa34f` 有兩份非授權清單文件，理由僅在 commit message 中。

### 失敗範例 D：忽略 numstat 落差

> ❌ 產出 4 的 `diff` 有輸出，但報告未提及，直接 commit。

**為何 FAIL**：這是未揭露的 scope 變更。
實際案例：commit `3baa34f` 把 `DECISIONS.md` 行尾由 CRLF 正規化為 LF，
內容無損但整檔 `git blame` 被壓成單一 commit，且違反 DEC-001 明文禁令。

---

### 失敗範例 E：把沒有失敗能力的檢查當成證據

> ❌ 「pre-commit hook 四項檢查全部通過，commit policy 已機械化強制執行。」

**為何 FAIL**：未出示任何 known-FAIL 案例。一個**從未失敗過**的檢查與一個
**永遠不會失敗**的檢查，在輸出上完全無法區分 —— 兩者都只印 PASS。
違反 `CLAUDE.md` §9A.2 與本 skill 產出 6。

**實際案例**：GOV-04 的 hook 在移除 `trap` 後，被截斷的 commit 於契約已被破壞的
情況下**仍會成功建立**（orphan commit `8e00b08`）。該 hook 當時「四項全過」。
**沒有刻意製造失敗，這件事不會被發現。**

---

### 產出 7：DoD 措辭必須指名目標資料庫

**任何會動 schema 或資料庫的 SB，其 Definition of Done 的每一項都必須指名目標資料庫。**

寫「`daily_ml_features` 在 `postgres`@`localhost:5432` 有 29 欄」，
**不要**寫「`daily_ml_features` 有 29 欄」。

#### 為什麼——這是 RISK-017 的成因，不是虛構案例

`UG-G2-SB1` 的 DoD 原文是「`daily_ml_features` **有 29 欄**」。

**它沒說哪一個資料庫。** 因此在隔離臨時容器 `g2sb1_ml_features_tmpdb` 裡達成
就算滿足——而那個容器在 Gate B 結案時已被拆除。
`UG-G2-SB3`（`g2sb3_articles_tmpdb`）、`UG-G2-SB4`（`g2sb4_comments_tmpdb`）
同一套寫法。

**結果**：三個 SB 各自新增 migration、各自「驗證通過」、各自結案，
而**真實開發資料庫從未套用過任何一次 migration**，落後四個版本，
直到 `UG-G2-SB5` 決策點 5 為了核對一個無關的小問題順手查了真實庫才撞到
（RISK-017，High）。

> 本專案對「驗了什麼、在哪裡驗的」紀律極嚴（`CLAUDE.md` §9 整套證據標籤），
> 但**沒有任何機制追蹤「哪個環境還沒收到這個變更」**——
> **前者記得再完整也推導不出後者。**

#### 檢查方式

逐項讀 DoD，問：**「這一項在哪個資料庫上達成才算數？」**
答不出來，或答案是「任何一個都行」，就是這個缺陷。

`UG-G2-MIG` 的 DoD 是第一個正確示範。

#### 本項的限制【誠實揭露】

**這是 skill 指示，不是機械強制。** 它讓規則**在對的時點被讀到**，
但沒有讓它變成不遵守就過不了的關卡。
若要真正機械化，那是 `gate0_contract_check.py` 的題目，
需要另外設計判準——**不要順手做，做不好會變成一個永遠通過的檢查**（§9A.1）。

---

### 產出 8：Gate B 通過時，過程文件即移入 `gates/closed/`

**通過 Gate B 之後、回報結案之前**，逐項確認並在報告中列出：

| # | 問題 |
|---|------|
| 1 | 本 SB 的 Gate A 提案與 Gate B 送審文件，**是否已 `git mv` 至 `doc/upgrade/gates/closed/`**？ |
| 2 | `git diff --cached --name-status` 是否顯示為 **`R100`（純 rename）**？非 R100 代表夾帶了內容變更 |
| 3 | 若本次關閉的是**整個 Gate**：該 Gate 的**啟動申請書**是否也一併移入？ |
| 4 | 被搬移的檔案是否出現在 `gate0_contract_check.py` 的 `DOC_PATHS`？**若有，必須在同一個 commit 內更新**（`CLAUDE.md` §16.4） |
| 5 | `doc/README.md` 的逐份文件表是否需要同步？ |
| 6 | Gate B 送審文件**是否含「本次移入清單」節**，逐一列名本次一併移入 `closed/` 的全部檔案（含 Gate A 提案與任何子報告，不只自身）？ |

**第 6 項的由來**（PO 2026-09-08，跨文件狀態一致性稽核第 6 案 R2）：
反查稽核發現 8 個 `closed/` 文件是**索引式引用**的孤兒——結案時只以單一
`GATE_B_SUBMISSION.md` 索引，子文件（Gate A 提案／過程報告）不逐一列名。
**這是刻意的文件經濟性設計，PO 已追認為慣例**，但代價是這些子文件對純文字
掃描「不可見」。**第 6 項不要求回頭補寫既有文件**——那 8 個已進 `R2_EXEMPT`
豁免表（`scripts/verify/cross_doc_consistency_check.py`）；**只要求日後的
Gate B 送審文件固定含這一節**，讓 `cross_doc_consistency_check.py` 的 R2
間接查找機制能自動辨識，不必每次手動加豁免項。

**綁事件，不綁編號，不綁個案。**

**為什麼放在這裡**（同產出 7 的理由）：`small-batch-orchestrator` 是規劃時點、
理論上更早，但它只會多一個「要記得」的地方；**`gate-submit` 是會被實際執行的關卡**。

**本項的由來**——同一個義務**漏了兩次**：

- `UG-G2-SB1` 結案時**揭露了卻沒有執行**（§0.5 #7，PO 於 SB2 結案時指出）
- 補了規則之後，`UG-G2-SB5` 特地綁了 §0.5 #9 的觸發條件才沒漏
- **但 `UG-G2-SB8` 結案時沒有人替它登記，於是又漏了**（2026-09-01 發現，
  當時 `gates/` 根層仍留著 SB8 的兩份文件）

**同一份清單裡就有對照組**：§0.5 **#10 是通則**（「每個 SB 的 Gate B 通過時，
該 SB 新增的 ADR 一併轉 `APPROVED`」）——**所以 DEC-029～031 一個都沒漏。**

> **綁事件的那條運作正常，綁個案的那條漏了兩次。**

**另一個缺口**：`CLAUDE.md` §16.3 的 `root → closed/` **只為 SB 提案設計**，
**Gate 層級的啟動申請書沒有對應的生命週期**，所以 `GATE1_STARTUP_APPLICATION.md`
一直留在根層。本產出的第 3 項補上這個情況。

⚠ **誠實揭露的限制**：本項與產出 7 同樣是 skill（指示）而非腳本，
**未使其成為機械強制**。真正機械化（例如讓 contract-check 檢查
「已結案 SB 的提案是否仍在根層」）需要一份「哪些 SB 已結案」的權威來源，
而那份來源目前只存在於 `PROJECT_STATUS.md` 的散文中——
**刻意不順手做：做不好會變成一個永遠通過的檢查**（§9A.1）。

---

### 產出 9：結案類 commit 前，跑跨文件狀態一致性反查

**適用範圍：結案類 commit**（Gate B 通過移入 `closed/`、Gate 關閉、
或任何會改動 `PROJECT_STATUS.md` §0.2／§0.5 CLOSED／APPROVED 宣稱的 commit）。
**不適用於一般開發 commit**——刻意不掛進 `.githooks/pre-commit`。

**為什麼不掛進每次 commit**（`CROSS_DOC_CONSISTENCY_GATE_A_PROPOSAL.md`
Gate A 核准時 PO 補充的理由，比提案原文 §7.3 再多一層）：

> **治理狀態的一致性是「事件時不變量」，不是「每次 commit 不變量」。**
> 送審中的 SB（根層有檔、`PROJECT_STATUS` 尚無列）是**合法的過渡態**——
> 掛進每次 commit 的 hook，就會在合法過渡態上誤擋，然後大家學會繞過它——
> **一個常誤報的檢查比沒有檢查更糟。**

**執行方式**：

```bash
python scripts/verify/cross_doc_consistency_check.py
```

（腳本已建立並可重跑，2026-09-08，commit `989206b`。R5（`REMAINING_RISKS.md`
解決性宣稱的語意核對）不由腳本產出，機械部分見腳本輸出，人工判讀部分依
`doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_criteria.json` 鎖定的
四欄格式另行核對）。

**判讀**：R1~R4 任一不合規（`PROJECT_STATUS.md` 宣稱 CLOSED 但 `closed/` 無對應檔案；
`closed/` 有檔案但未被任何文件引用；引用的 ADR 未達 `APPROVED`；`APPROVED` 的 ADR
未進 `TRACEABILITY.md` 索引），**必須在報告中列出，不得逕行結案 commit**——
先補正引用或說明例外，取得 PO 確認後才可繼續。R5 依同提案 §二鎖定的四欄格式
（宣稱原文／證據位置／判定三態／機械可驗或人工判讀）附上。

**本項的由來**——同一種「規則只活在對話記憶裡」的損耗（同產出 7、8 的病灶家族）：
本 SB（第 6 案）核准當下若不把執行時機寫進一個會被實際執行的關卡，
它就是下一個「有規則、沒有觸發機制」的義務，重演 `TEAM_PLAYBOOK.md` §7A.3
（備份慣例連續斷了四次）與 `CLAUDE.md` §16.3 規則 4／5（`gates/` 根層清空義務
漏了兩次）的同型故事。**綁進 `gate-submit` 是因為它是會被實際執行的關卡**，
不是規劃時點（同產出 7、8 的既有理由，不重複展開）。

---

### 產出 10：結案 commit 完成後，寫一份給 PO 的一頁式進程摘要

**適用範圍**：每個 SB／小案／bug 走完 Gate B **且結案 commit 已完成之後**，
一案一份。**分段執行的案子**（例如一個案子拆成段 A／B1／B2 分次授權執行）
**只在全案結束時寫一份，不逐段**。

**目的**（PO 裁決，2026-09-21，`DECISIONS.md` DEC-046）：Gate B 報告是給審查方
的證據文件，動輒 150～280 行，hash／路徑／逐項驗收對 PO 是雜訊。PO 需要的是
**概念式**說明：這案要做什麼、中途出了什麼事、成果如何、還剩什麼。

**格式**：一頁、硬上限 60 行，八節：

| 節 | 內容 | 規則 |
|---|---|---|
| 1. 為什麼做 | 一句話：解決什麼問題、被什麼事件觸發 | |
| 2. 做了什麼 | 概念層：改了哪個機制、資料流從哪到哪 | **零 hash**；檔名只在 PO 需要親自打開時出現 |
| 3. 中途發生什麼 | 意外發現、設計被改的地方、**被複核退回的原因、自己抓到的錯** | |
| 4. 成果 | 關鍵數字 **≤ 5 個**，每個附一句「在現實裡代表什麼」 | |
| 5. 沒做的與沒驗證的 | 範圍外、已知限制、**本案依賴但未驗證的上游假設** | **必填**；寫「無」要說明為何確信 |
| 6. 改變了什麼前提 | 本案動了哪個前提；**哪些其他機制建立在那個前提上** | 對應 §5.1 A13 家族（新測試巧合 PASS 混入紅測證據）同型的「看不見自己盲點」病灶 |
| 7. 新登記的候補與風險 | 編號＋一句話，不展開 | |
| 8. PO 接下來要決定的事 | 沒有就寫「無」 | |

**讀者測試**：一個沒看過 repo 的人讀完能複述第 1、2、4 節。

**存放**：`doc/progress/`，檔名 `YYYY-MM-DD_<案號>_<slug>.md`。**不 commit、
不上 GitHub**（`.gitignore` 已排除 `doc/progress/`）、**不進
`gate0_contract_check.py` 的 `DOC_PATHS`**。寫完放著當證據檔，只有當下發現
錯誤才改；之後任何文件同步都不包含它；已結案的不回填。

**審查**：摘要送審查方核對「與 Gate B 證據是否一致」，通過才轉 PO；不另開複核輪。

**⚠ 沒有版控保護**：`doc/progress/` 不在 repo 裡，`git clean -fdx`
會直接刪除它且 `git status` 完全看不出曾經存在過——沒有 commit 就沒有
`git reflog`／`git fsck` 可以復原。清理容器或工作區前，若不確定 `doc/progress/`
是否有尚未轉交 PO 的內容，先確認過再執行。

**為什麼放在 skill 而不是另立規則**：理由同產出 7、8、9——**綁事件、不綁
個案**（GOV-09 的教訓：綁個案的規則漏了兩次，綁事件的一次都沒漏）。
`gate-submit` 是結案 commit 完成後**一定會被執行**的關卡，不是規劃時點。

---

## 4. 自檢流程

```
1. 執行產出 1（contract-check）        → exit != 0 則停止
2. 執行產出 2（測試 + 依賴表）          → 有 FAIL 則停止
3. git add（逐檔，不用 -A）
4. 執行產出 3（授權稽核）              → 有未說明的超出項則停止，請示 PO
5. 執行產出 4（格式夾帶偵測）           → diff 有輸出則停止，請示 PO
6. 產出 5（證據標籤表）
7. 產出 6（known-FAIL 案例對照表）  → 有檢查出示不了案例則標示「不計入證據」
8. 產出 7（DoD 指名目標資料庫）     → 僅適用會動 schema／資料庫的 SB；
                                      有任一項答不出「在哪個資料庫上達成才算數」則回去改 DoD
9. 產出 8（過程文件移入 closed/）  → 僅適用 Gate B 通過時；
                                      rename 必須是 R100，夾帶內容變更即停止
10. 產出 9（跨文件狀態一致性反查） → 僅適用結案類 commit；
                                      R1~R4 任一不合規則停止，先補正或取得 PO 確認
11. 組裝報告 —— **九項齊備**才送審
12. 取得 PO commit 授權後才執行 commit
13. 產出 10（一頁式進程摘要） → 結案 commit 完成後才寫，不影響 commit 本身；
                                      分段案子只在全案結束時寫一份；送審查方核對一致性後轉 PO
```

---

## 5. 相關規則

- `CLAUDE.md` §9 — 證據標籤定義與使用規則
- `CLAUDE.md` §9A — 驗證的設計：為偵測而寫、known-FAIL 案例要求
- `CLAUDE.md` §12 — Commit Policy（授權、格式變更、揭露義務）
- `CLAUDE.md` §13 — 測試指令、工具鏈缺口、環境依賴缺口
- `doc/governance/TEAM_PLAYBOOK.md` §2、§4 — PO 專屬批准事項與證據權威位置
