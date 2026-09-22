# Gate A 提案：從 git 歷史永久移除字面憑證（已歸檔，未執行）

> **PO 裁決不採用（2026-09-22）：改為 rotation ＋ 乾淨快照，理由見 `PROJECT_STATUS.md` §0.5 登記
> 與 `GIT_HISTORY_CLEAN_SNAPSHOT_GATE_A_PROPOSAL.md`。** 本提案的隔離操作原則、兩道獨立授權、
> 精確比對（不做全域取代）、排除拋棄式容器密碼等設計，已沿用到快照案，本檔本身不執行。
>
> **複核發現本檔曾多處直接寫出該預設值**（CHAL-008 同型漏洞的第五次實例），已全數改為
> `<dev-default>` 佔位符；以下內容為歸檔前的原始分析，數字與結論不變，僅置換字面值表示法。

## 0. 摘要

`DECISIONS.md` DEC-002「Security Incident / Risk Decision」已明文把 **`public repository release`** 列為必須重新開啟「Local development PostgreSQL password rotation」的觸發條件之一（`Accepted Risk / Deferred Remediation`，2026-08-19 記錄）。PO 現在決定把 `origin`（`https://github.com/lg255016/Stock_Prediction_System.git`）改為 public，觸發條件成立。

本案唯讀查證發現：全部 428 個 commit 的歷史中，**同一個字面憑證值（下稱 `<dev-default>`）**（本機 devcontainer 的 PostgreSQL 預設密碼，非真實外洩機密）以「密碼欄位＝`<dev-default>`」的語法形式，在 **8 個 commit** 裡出現過（含程式碼、evidence JSON、commit message 本文）——其中 **2 個已經公開在 GitHub 上**。本案要做的是：用 `git filter-repo` 把這個字面值從全部歷史裡永久置換為佔位符，然後 force-push 覆蓋已公開的舊歷史。

**明確排除**：不處理 RISK-013 拋棄式容器的隨機臨時密碼（如 `tmp_sb1`、`sb4_tmp_pass`）——這些容器早已銷毀、值本身無殘留意義，混進同一次歷史改寫只會擴大驗證面而不增加安全效益（§3.5 有完整理由）。也不處理 Gemini API key——DEC-002 已記載該 key 經 `docker inspect` 外洩至**工具紀錄**（非 git 檔案）、已由 PO 手動 revoke／replace、已標記 `CLOSED`；本案第 2 節的全歷史掃描確認該金鑰字串從未進入任何 git-tracked 檔案，故不在本案處理範圍內。

**這是一個破壞性操作**：改寫的 commit 及其之後的每一個 commit 都會得到新的 hash；已公開的 3 個 commit 需要 force-push 覆蓋。依 `CLAUDE.md` §11A，本案唯讀階段（本提案）不執行任何改寫，需 PO 明確核准後才進入執行階段；執行階段本身也拆兩步分別授權（見 §8）。

## 1. Requirement Source

PO 直接裁決（2026-09-22，回應本 session 的「上 GitHub 安全性評估」），選擇「history rewrite」而非「維持現狀」。技術依據見 `DECISIONS.md` DEC-002 §Security Incident / Risk Decision（2026-08-19，已核准）。

## 2. Current State（唯讀查證，`VERIFIED THIS SESSION`）

### 2.1 完整的字面憑證清單——8 個 commit，同一個值

逐一用 `git show <hash>` 核對內容確認，非樣本推估：

| # | commit | 日期 | 位置 | 已公開？ |
|---|---|---|---|---|
| 1 | `ff66be5` | 2026-08-15 | `.devcontainer/docker-compose.yml`：`POSTGRES_PASSWORD: <dev-default>` | **是（`origin/main`）** |
| 2 | `9b922b4` | 2026-08-15 | `src/loaders/db_writer.py`：`"password": "<dev-default>"`（`DB_CONFIG` dict，兩處） | **是（`origin/main`）** |
| 3 | `ed6f38e` | 2026-09-09 | `doc/upgrade/gates/evidence/UG_G3_SB1_ambiguous_ratio_report.json` 的 `rerun_instructions`：`password='<dev-default>'` | 否 |
| 4 | `581950a` | 2026-09-09 | 修正 #3 的檔案內容，但 **commit message 本文**原樣引述 `password='<dev-default>'` | 否 |
| 5 | `32250d2` | 2026-09-09 | 修正 #4 的 message 重演（`CHALLENGES.md` CHAL-008 §1／§4 再次寫入字面值） | 否 |
| 6 | `34bcc5f` | 2026-09-09 | `doc/upgrade/gates/evidence/UG_G3_SB2_routing_real_db_write.json`：`PGPASSWORD=<dev-default>`、`POSTGRES_PASSWORD=<dev-default>`（docker 指令） | 否 |
| 7 | `655f740` | 2026-09-10 | 修正 #6 的檔案內容，但 `CHALLENGES.md` CHAL-008 §6 新增段落再次原樣寫入 | 否 |
| 8 | `7dd382c` | 2026-09-10 | 修正 #7 的 `CHALLENGES.md` 重演（第四次同型漏洞，專案自己的追記） | 否 |

**成因是同一個遞迴模式**：每次「修正」都把外洩內容原樣抄進描述外洩的文字裡，變成下一次外洩——`CHALLENGES.md` CHAL-008 §1、§4、§6 已把這個模式記錄了三次。本案要一次把 8 個 commit 全部處理掉，不要再重演第五次。

**現行程式碼已無此問題**：`HEAD` 的 `db_writer.py`、`docker-compose.yml` 皆已改為讀環境變數（`env_file: ../.env`／`os.environ[...]`），`.env` 本身從未被 commit（全歷史 `--diff-filter=A` 掃描確認）。本案處理的**純粹是歷史紀錄**，不是現行程式碼缺陷。

### 2.2 範圍確認——沒有真正的機密外洩到 git

- `AIzaSy`（Google API key 格式）、`sk-proj`（OpenAI 格式）：全歷史 pickaxe 搜尋零命中。
- `.env` 本身：全歷史 `--diff-filter=A` 掃描，只有 `.env.example`（純佔位符）曾被加入，`.env` 從未進 index。
- `.dump`／`.backup`／`.devcontainer/postgres-data/`：全歷史 `git ls-tree` 掃描，從未被 track。
- 歷史中出現過的 3 份 PDF（規劃書／研究文件）已逐份開檔核對內容，皆為 AI 協助生成的專案規劃／文獻回顧，無姓名、學號、電話、地址等個資。
- repo 體積 34MB，無 push 大小疑慮。

### 2.3 工具

- `git version 2.53.0.windows.2`（host），支援 `git filter-repo` 所需版本。
- `git-filter-repo` 尚未安裝，為 pip 可裝的單檔 Python 工具（Git 官方文件建議取代 `filter-branch`／BFG 的現行做法）。

## 3. 設計提案

### 3.1 隔離原則——比照本專案既有的拋棄式容器紀律

**絕不直接對現在使用中的 repo 執行 `git filter-repo`**——這是該工具自己的文件明文警告，也與本專案 RISK-013「先拋棄式驗證、再對真實目標動手」的既有紀律同構：

1. 建立完整備份：`git bundle create` 或 `tar` 整個 `.git`，存到 repo 外部路徑（`D:\Python\Database_Backups\` 同一備份慣例位置）。
2. 在**隔離的臨時目錄**（非本 working copy）建立本 repo 的**新 clone**（`git clone --no-local` 或 `--mirror`，確保是獨立副本，不是同一個 `.git` 的硬連結）。
3. 全部 `git filter-repo` 操作在這個隔離 clone 裡執行，本 working copy 全程不受影響、可隨時繼續其他工作。

### 3.2 置換規則——精確比對「欄位＝`<dev-default>`」，不是全域取代該字串

`postgres` 這個字在本專案裡到處合法出現（資料庫產品名稱、DB 名稱本身、hostname 的一部分）。**絕不能整串取代**，只能精確比對「密碼欄位剛好等於 `<dev-default>`」這個語法形狀，且必須逐一針對 §2.1 列出的 8 個 commit 裡實際出現過的寫法（六種欄位＋分隔符組合，值本身不在此重複列出）：

```
password='<dev-default>'          ==> password='<redacted>'
password="<dev-default>"          ==> password="<redacted>"
"password": "<dev-default>"       ==> "password": "<redacted>"
POSTGRES_PASSWORD: <dev-default>  ==> POSTGRES_PASSWORD: <redacted>
POSTGRES_PASSWORD=<dev-default>   ==> POSTGRES_PASSWORD=<redacted>
PGPASSWORD=<dev-default>          ==> PGPASSWORD=<redacted>
```

六條規則皆為**字面字串**（非正規表示式），套用 `git filter-repo --replace-text <規則檔>`，同時作用於 blob 內容與 commit message（`git filter-repo` 預設兩者皆處理，執行階段會先在隔離 clone 上實測確認這個行為，不假設）。

**執行前逐一核對**：這 6 條規則字面比對 §2.1 表格裡 8 個 commit 的實際內容，確認每一筆都能被其中一條規則命中——若有第 9 種寫法本次沒抓到，寧可先發現、再補規則，不能等改寫完才知道漏了。

### 3.3 明確排除的範圍（§0 已提過，此處記錄理由）

- **RISK-013 拋棄式容器的隨機臨時密碼**（`tmp_sb1`、`sb4_tmp_pass`、`test`、`rc` 等）：容器早已 `docker rm`，值本身連對應的服務都不存在了，殘留風險為零。納入同一次歷史改寫，會讓「哪些字串該被當成密碼處理」的判準從「精確語法比對」退化成「任何看起來像密碼的字串都清」——後者正是 `CLAUDE.md` §9A.1 警告的「做不好的機械化檢查比沒有檢查更危險」。**這批不動，除非 PO 另外要求**。
- **Gemini API key**：已於 §0／§2.1 說明，從未進入任何 git-tracked 檔案，本案的工具（`git filter-repo`）處理的是 git 物件，管不到「已進工具紀錄」這件事，不在本案範圍。

### 3.4 執行順序（本提案核准後，仍需 §8 的兩道獨立授權才能真正動手）

1. 備份（bundle／tar）。
2. 隔離 clone，套用 §3.2 的 6 條規則。
3. **驗證**（見第 4 節），在隔離 clone 上完成，**未通過全部驗證項前不觸碰真實 repo 與 `origin`**。
4. 驗證通過後，PO 第一次授權：把隔離 clone 驗證過的結果應用到本機真實 repo（取代本機 `.git`，或用等效方式讓本機分支指向改寫後的歷史）。
5. 本機驗證（全套測試、contract-check、`git log`／`git status` 檢查）再過一次。
6. PO 第二次獨立授權：`git push --force` 覆蓋 `origin/main`（`CLAUDE.md` §11「未經PO明確要求不得force push」——這裡是明確要求，但仍要求這是**獨立於步驟 4 的另一次確認**，因為這一步之後任何已經 clone 過 `origin` 的第三方都會與新歷史分岔，且無法保證 GitHub 端不曾快取舊物件）。

## 4. 驗證計畫（`CLAUDE.md` §9A：每項檢查要能回答「什麼輸入會讓它 FAIL」）

在隔離 clone 上，改寫後逐項確認：

| # | 檢查 | 通過標準 | Known-FAIL 對照 |
|---|---|---|---|
| 1 | 8 個已知 commit 的字面憑證是否清除 | 對改寫後的 tree 用 `git log --all -p` 重新 grep §3.2 的 6 條字面字串，**零命中** | 若規則寫錯（例如漏了某個引號變體），對應的字面字串仍會被 grep 到——這就是這項檢查真正能抓到問題的情況，不是形式測試 |
| 2 | 合法的 `postgres` 用法有沒有被誤傷 | 改寫前後，任取 5 個**不含**密碼值的檔案（如 `schema.sql`、`README` 提及 PostgreSQL 之處）逐位元組比對，須完全相同 | 若規則不小心比對到過寬的樣式（如純 `postgres` 三個字），這裡會出現非預期差異 |
| 3 | commit 數量與作者資訊 | 改寫後 `git rev-list --count --all` 與改寫前相同；`git log --format="%an %ae"` 逐筆比對作者不變 | `git filter-repo` 預設會改寫 commit hash 但保留 metadata；若數量對不上，代表規則或執行方式有問題 |
| 4 | 現行測試與契約檢查在改寫後的 clone 上仍通過 | 容器內全套測試 OK；`gate0_contract_check.py` exit 0 | 若改寫過程意外損毀了某個檔案內容（不只是密碼那幾行），測試會在這裡現形 |
| 5 | 新 commit 的父子關係與原歷史一致（只有 hash 變、拓樸不變） | `git log --graph --oneline --all` 的分支拓樸結構與改寫前對照相同 | 若 `git filter-repo` 的 `--replace-refs` 等參數用錯，可能意外丟失某條分支或合併關係 |

**§3.4 步驟 4／6 執行前**，把上述 5 項驗證的原始輸出整理成報告先送審查方複核，複核通過才送 PO 決定是否授權。

## 5. Affected Components

- `.git` 內部物件（全部歷史，`ff66be5` 之後的每個 commit 都會有新 hash）
- `origin/main`（force-push 後覆蓋）
- **不動**：任何現行原始碼、任何現行文件內容、`.env`（本來就不在 git 裡）、`.devcontainer/postgres-data/`（本來就不在 git 裡）

## 6. 剩餘風險（誠實揭露，不自行決定如何處置）

- **GitHub 端快取**：force-push 覆蓋後，理論上舊物件可能在 GitHub 端有殘留快取時間，且若這段期間已有任何自動化掃描器（bot）造訪過這個 repo，無法百分之百保證舊字串完全沒被記錄過。鑑於這個值本身是全世界通用的 PostgreSQL Docker 預設密碼、對應的服務從未對外開放埠、且已經改寫成佔位符，殘留風險評估為極低，但**不是零**，這一點需要 PO 知情後才算完整揭露。
- **改寫後所有 commit hash 改變**：任何外部工具、書籤、或先前貼過的 commit 連結會全部失效。本 session 至今所有回報過的 commit hash（`b131bbf`／`313581e`／`2c4c075`／`d3cfde4` 等）在改寫後都會變成新的 hash——**這件事本身不影響已完成工作的內容，只影響引用方式**，執行完成後我會在報告中列出舊 hash → 新 hash 的對照，供之後追溯。
- **本機 reflog 過期後不可逆**：改寫前的舊歷史在本機 reflog 中還能找一段時間，但 `git gc` 或時間久了會被清除；§3.4 步驟 1 的獨立備份（bundle／tar）才是真正的長期復原手段，不依賴 reflog。

## 7. Definition of Done

- [ ] §3.1 備份完成，存放路徑已記錄
- [ ] 隔離 clone 上完成 §3.2 全部 6 條規則套用
- [ ] §4 五項驗證全數通過，原始輸出附在報告裡
- [ ] 驗證報告送審查方複核通過
- [ ] PO 第一次授權（套用到本機真實 repo）
- [ ] 本機驗證重跑一次（測試、contract-check、`git status`）
- [ ] PO 第二次獨立授權（`git push --force` 覆蓋 `origin/main`）
- [ ] force-push 完成後，`git ls-remote origin` 確認遠端 hash 已更新為新歷史
- [ ] 舊 hash → 新 hash 對照表寫入報告
- [ ] `DECISIONS.md` DEC-002 補記本次處置結果，「Deferred Remediation」項改為已處理狀態

## 8. 流程

本提案先送審查方複核；通過後送 PO 核准**提案本身**（此時仍不執行任何操作）。核准後：**§3.4 步驟 1～3（備份＋隔離 clone＋驗證）可直接執行**，不涉及本機真實 repo 與遠端，风险最低。驗證報告送審查方複核，通過後送 PO 做**第一次獨立授權**（套用到本機真實 repo，步驟 4～5）。本機驗證完成後，送 PO 做**第二次獨立授權**（`git push --force`，步驟 6）——兩次授權不得合併成一次，中間至少間隔一次 PO 的明確確認動作，比照本 session 段 B1／B2 的既有紀律。
