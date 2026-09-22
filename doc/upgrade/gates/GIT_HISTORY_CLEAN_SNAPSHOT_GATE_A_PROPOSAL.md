# Gate A 提案：乾淨快照公開（取代歷史改寫）

> **本檔全程不得出現任何真實憑證的字面值**——密碼、金鑰一律以 `<dev-default>`／`<redacted>`
> 這類佔位符表示。這條規則本身就是本案要解決的問題的一部分（`CHALLENGES.md` CHAL-008）。

## 0. 摘要

PO 裁決（2026-09-22）：不對現有 428 個 commit 的私有歷史做 `git filter-repo` 改寫（原提案
`GIT_HISTORY_CREDENTIAL_PURGE_GATE_A_PROPOSAL.md` 已歸檔、不執行——改寫會讓治理與證據文件裡
**329 個相異、共約 936 處**的真實 commit hash 引用全數失效，代價遠高於一個本機開發預設密碼的
殘留風險）。改採：**rotation（讓歷史裡的舊值失效）＋ 建一個沒有歷史的乾淨快照 commit 推去
public repo（讓舊值連存在的痕跡都不留在公開版裡）**。

本案是這個裁決的第二部分：快照本身。私有的 428 個 commit（含完整決策證據鏈）**繼續留在本機
與私有 remote，不會被這個小案改動或刪除**；本案只建立、驗證、（經 PO 另外授權後）推送**一個
獨立的、無父 commit 的快照**去取代 `origin/main` 現有的 3 個 commit。

第三部分（GOV-13 hook 的 `pass(word)?=` 樣式漏掉 `:` 分隔符）另案處理，可平行進行。

## 1. Requirement Source

PO 裁決（2026-09-22），回應「歷史改寫代價過高」的複核發現。前提：`§2 rotation` 已完成
（`DECISIONS.md` DEC-002 的 `Deferred Remediation` 改為已處理狀態）——**本案不得在 rotation
完成前推送**，理由：若 rotation 未完成，快照裡現行程式碼讀到的 `.env` 邏輯雖然正確，但
**歷史裡舊值對應的憑證如果還是活的**，快照公開後任何看得懂 `docker-compose.yml` 結構的人
都能推得出這個 repo 曾經用過的本機開發預設密碼慣例，進而去猜當下的值——rotation 讓這個推測
失去意義。

## 2. Current State（唯讀查證，`VERIFIED THIS SESSION`）

- `origin/main` 目前只有 3 個 commit（`f489122`／`ff66be5`／`9b922b4`），是本案要取代的目標。
- 本機 `main`／`fix/gate1-schema-source-of-truth` 共 428 個 commit，**不在本案的推送範圍內**，
  私有 remote（如果之後要設）或純本機保留即可。
- `.gitignore` 已排除 `doc/progress/`、`scripts/verify/evidence_local/`、`.env`、
  `.devcontainer/postgres-data/`、`*.dump`、`*.backup`——這些從未進過 git index，快照的
  來源（`HEAD` 的 tracked tree）本來就不含它們，**不需要額外的排除步驟**，只需要確認這件事
  （見 §4 驗證項 1）。
- `LICENSE` 檔案不存在——不是本案範圍，僅記錄於 §7 留意。

## 3. 設計提案

### 3.1 隔離原則（沿用已歸檔提案的設計，未變動）

在**獨立的臨時目錄**用 `git clone --no-local` 建立本 repo 的新副本，全部操作在這個副本裡
執行，本 working copy 不受影響。

### 3.2 建立無歷史快照

```bash
cd <isolated-clone>
git checkout --orphan public-snapshot
git add -A
git commit -m "<訊息內容見 §3.4>"
```

`--orphan` 建立的分支沒有任何 parent；`git add -A` 在乾淨 clone 的工作目錄裡只會加進
**當時 `HEAD` 實際 track 的檔案**（未 track 的檔案從未進到 clone 的工作目錄裡，不存在
「漏排除」的問題）。這個 commit 的 tree 內容等於現在 `HEAD` 的 tree，但**沒有父 commit、
沒有 428 筆歷史**。

### 3.3 值無關的秘密掃描——掃樣式，不掃已知值；樣式定義與 hook 共用同一份

不能重複原提案的錯誤（鎖定「已知的字面值」去搜，結果漏掉分隔符不同的寫法）。改用**樣式**，
且**輸出本身不得印出比對到的值**。

**PO 裁定（2026-09-22，GOV-14 第二輪 hook 複核通過後）**：樣式**不得**在本掃描腳本內
另寫一份，必須直接從 `.githooks/pre-commit` 讀出 `PASS_PATTERN`／`WHITELIST_SUFFIX` 兩個
變數來用——「一個定義、兩個用途，永遠不會分岔」（同 GOV-14 §0.5 #40 段 B2 沿用段 B1
函式的原則）。hook 修法或擴充白名單時，本掃描自動跟著改，不需要記得同步兩份。

```bash
eval "$(grep -m1 '^PASS_PATTERN=' .githooks/pre-commit)"
eval "$(grep -m1 '^WHITELIST_SUFFIX=' .githooks/pre-commit)"
grep -rInE "${PASS_PATTERN}[^[:space:]]+" . --exclude-dir=.git \
  | grep -viE "${PASS_PATTERN}${WHITELIST_SUFFIX}"
```

（`PGPASSWORD` 已含在 `PASS_PATTERN`（`[A-Z_]*PASSWORD` 分支）內；`AIzaSy`、`sk-`、
`BEGIN .* PRIVATE KEY` 是另外三條與密碼無關的金鑰樣式，同一份掃描腳本內、各自獨立於
`PASS_PATTERN` 之外，不與本節混用。）

**輸出格式**：只印 `檔名:行號:比對到的值長度`，不印值本身——用一個小腳本把 grep 結果的
比對片段換算成字元數再印出，原始比對內容留在腳本的記憶體變數裡，不寫進任何輸出、log 或
本檔。逐一人眼核對每一筆的「檔名＋長度」是否合理（例如：長度 1～2 通常是佔位符或說明文字，
長度明顯像一組真實金鑰則要停下來追查，但追查時仍不把值印到終端機或寫進任何檔案，只確認
「這是不是已知的某個佔位符」）。

**豁免表（PO 核准，2026-09-22）**——這些命中不是要放行的秘密，是已結案的歷史紀錄，
依同一份 `git checkout -- <path>` 討論確立的原則（改寫已核准的歷史等同竄改歷史）不予改寫，
本掃描以固定清單豁免（同 `gate0_contract_check.py` 的 `LEGACY_ALLOWLIST` 機制：讓債務
可見，不是讓它消失）：

| 位置 | 命中筆數 | 理由 | 核准日期 |
|---|---|---|---|
| `doc/upgrade/gates/closed/*.md`（`G2_SB1_GATE_B_SUBMISSION.md`、`G2_SB3_GATE_B_SUBMISSION.md`、`G2_SB4_GATE_B_SUBMISSION.md`、`SB1_STEP1_BEFORE_SNAPSHOT.md`、`SB1_STEP4_AFTER_SNAPSHOT.md`、`SB2_GATE_B_SUBMISSION.md`、`SB2_STEP3_IMPLEMENTATION_REPORT.md`、`SB4_STEP2_GATE_B_SUBMISSION.md`） | 26 | 已結案 Gate 的 Gate B 送審文件，記錄當時實際執行的拋棄式容器指令與測試 diff 摘錄，屬歷史事實；依 CLAUDE.md §16.3 為過程文件的既有生命週期終點，改寫等同竄改已核准歷史——與本會期稍早被否決的「歷史改寫」提案同一類疑慮 | 2026-09-22 |
| `doc/evidence/CHALLENGES.md:233,259` | 2 | CHAL-008 既有段落，引述歷史外洩事故本身（描述當時把完整連線指令原樣抄入、以及檢查 3 擴充範圍的既有文字），非任何一輪新增內容 | 2026-09-22 |
| `doc/upgrade/gates/evidence/G2_SB6_dump_restore_verification.json:20` | 1 | UG-G2-SB6 結案證據，拋棄式容器 `sb6_restore_check`（驗證後已拆除）的測試密碼，非真實憑證；PM 本輪曾誤改為佔位符，PO 指出「同一原則不能在 `.md` 適用、在 `.json` 不適用」後以 `git checkout --` 還原，改列入本豁免表而非改寫證據 | 2026-09-22 |

**通過標準**：扣除豁免表後零命中，或每一筆的比對片段都以白名單前綴開頭（`<`／`$`／
`os.environ`／`os.getenv`／`%(`）。任一筆不符即中止，不得往下一步。

### 3.4 Commit message──不帶 session 追蹤 trailer

**PO 明確指示**（2026-09-22）：這個快照 commit **不**加 `Co-Authored-By` 與
`Claude-Session` trailer——這是私有工作流程的內部追蹤資訊，264 個私有歷史 commit 都有，
公開版一個都不需要帶出去。這條指示只適用於本案這**一個**快照 commit，不改變本 session
之後在私有 repo 建立的其他 commit 的既有慣例。

Commit message 內容：簡短說明這是專案的公開快照版本，指向 README 的完整說明（見 §3.5）。

### 3.5 README 增補

在快照裡的 `README.md`（若原本沒有，新建一份最小版本）加一段：

> 本 repository 是完整開發歷史的**單一快照**。完整的逐步決策紀錄、Gate／Small Batch
> 治理過程與證據鏈保存在私有歷史中；本快照之後的文件內容如果引用了 commit hash，
> 該 hash 指向的是私有歷史，不在這個公開快照裡能找到。

### 3.6 推送——需要 PO 另一次獨立授權

目標：現有 `origin`（`https://github.com/lg255016/Stock_Prediction_System.git`）的 `main`。
方式：`git push --force origin public-snapshot:main`（用快照分支覆蓋 `origin/main` 現有的
3 個 commit）。**私有的 428 個 commit 不推、不出現在任何 remote 的公開分支上。**

這是 `CLAUDE.md` §11 的 force push，即使 PO 已在 §0 的裁決裡定了方向，執行推送前仍要一則
**獨立**於「快照建立完成」的訊息明確授權——比照本 session 段 B1／B2 的兩道授權紀律，「做完
準備」與「真的送出去」永遠是兩個不同的決定點。推送後 `git ls-remote origin` 確認遠端 hash
已更新。

## 4. 驗證計畫

在隔離 clone 上，快照建立後逐項確認：

| # | 檢查 | 通過標準 |
|---|---|---|
| 1 | 快照的 tree 不含 `doc/progress/`／`scripts/verify/evidence_local/`／`.env`／`*.dump` | `git ls-tree -r public-snapshot --name-only` 逐一 grep 確認零命中 |
| 2 | §3.3 的值無關掃描 | 零命中，或全部比對片段以 `<` 開頭 |
| 3 | **Known-FAIL**：掃描腳本本身有沒有偵測力 | 在**另一個拋棄式副本**（不是要推送的那份快照）裡，故意加一行 `password=<非佔位符任意字串>`，重跑 §3.3 的掃描，確認會被抓到、輸出「檔名:行號:長度」；復原後確認要推送的那份快照未受影響 |
| 4 | Commit message 沒有 `Co-Authored-By`／`Claude-Session` | `git log -1 --format=%B public-snapshot` 逐行檢查 |
| 5 | 快照內容與 `HEAD` 現行 tree 一致（沒有意外少檔案或多檔案） | `git diff HEAD public-snapshot --stat` 應為空（zero diff，因為快照就是 `HEAD` 的 tree，只是沒有歷史） |
| 6 | 容器內全套測試／contract-check 在快照 checkout 出來的副本上仍通過 | 全套 OK；exit 0 |

推送前（§3.6），把上述 6 項驗證的原始輸出整理成報告送審查方複核，複核通過才送 PO 做推送的
獨立授權。

## 5. Affected Components

- **新建**：`origin/main` 上的 1 個快照 commit（取代現有 3 個）
- **不動**：私有本機的 428 個 commit、`fix/gate1-schema-source-of-truth` 分支、任何現行原始碼

## 6. 剩餘風險

- GitHub 端可能對已 force-push 覆蓋的舊 commit（`f489122`／`ff66be5`／`9b922b4`）保留一段
  快取時間；這 3 個 commit 本身**不含真正機密**（已於前一輪查證確認，唯一的字面值是本機
  開發預設密碼，rotation 完成後即失效），殘留風險評估極低。
- 快照建立後，**之後任何一次對私有歷史的修改都不會自動反映到公開快照**——這是刻意的設計
  （快照就是單一時間點的公開版本），但意味著要更新公開版時，本案的 §3.2～§3.6 需要重跑
  一次，不是自動同步。這件事需要寫進 §7 DoD 讓下次執行的人知道。

## 7. Definition of Done

- [ ] §2 的前提（rotation 完成，`DECISIONS.md` DEC-002 已更新）已確認成立
- [ ] 隔離 clone 建立，快照 commit 完成
- [ ] §4 六項驗證全數通過，原始輸出附在報告裡（含 known-FAIL 的實際輸出）
- [ ] 驗證報告送審查方複核通過
- [ ] PO 獨立授權推送
- [ ] `git push --force` 完成，`git ls-remote origin` 確認
- [ ] 快照裡的 README 已包含 §3.5 的說明段落
- [ ] （建議，非必要）補一份 `LICENSE`
- [ ] `PROJECT_STATUS.md` §0.5 登記本案（rotation／快照／hook 三件事的狀態），交叉引用
      `DECISIONS.md` DEC-002
- [ ] `GIT_HISTORY_CREDENTIAL_PURGE_GATE_A_PROPOSAL.md`（已歸檔的舊提案）與本檔，於快照案
      的第一個私有 commit 一起 `git mv` 進 `gates/closed/`——先 `git add` 新路徑再比對
      `--cached` 內容，確認搬移前後內容一致（A19 教訓：`git mv` 對已有未 staged 修改的檔案
      只會用 index 裡的舊內容更新新路徑，必須額外 `git add` 一次撿回 working tree 的真實內容）

## 8. 流程

本提案先送審查方複核；通過後送 PO 核准提案本身。核准後：§2 rotation 需已完成（PO 前提）
→ §3.1～§3.5（隔離 clone、建快照、掃描、驗證）可直接執行，全程不碰 `origin`，風險最低
→ §4 驗證報告送審查方複核 → 複核通過送 PO 做**推送的獨立授權**（§3.6）→ 執行 force push
→ 結案報告（含 §7 DoD 逐項勾選）送審查方複核 → 整理給 PO。
