# GOV-13 提案：pre-commit 檢查 3 增加 staged 內容層秘密掃描

- 提出日期：2026-09-10（第一版）；修正：2026-09-10（PO 複審四點）→ 2026-09-10
  （PO 二次複審：寬樣式 + `-i` 取代 PCRE lookbehind，已實作並驗證）→ 2026-09-10
  （PO 三次複審核准，狀態轉 `APPROVED`；命中值遮罩後續已補）
- 狀態：**`APPROVED`（PO 2026-09-10）**——設計已實作於 `.githooks/pre-commit`／
  `CLAUDE.md` §12.4／`DB_MIGRATION_PLAN.md:380`，以 11 項情境全部通過驗證
  （見 §7，含命中值遮罩）。
- 觸發：`doc/evidence/CHALLENGES.md` CHAL-008，四次同型漏洞

---

## 1. Context（背景）

`CLAUDE.md` §12.4 的 pre-commit hook 檢查 3「秘密檔案偵測」自 GOV-04 上線以來，
判準**只看 staged 檔案的檔名**（`.env`／`.env.*`／`settings.local.json`／`*.pem`／
`*.key`／`id_rsa*`），從未涵蓋**檔案內容**。這個範圍邊界在 hook 檔頭與 CLAUDE.md
§12.4「刻意不放進 hook 的東西」都有明文——**不是缺陷，是設計時就劃定的範圍**。

問題不在 hook 本身，在於**這個範圍邊界會被誤認為已涵蓋內容層**。本專案這一輪
（`UG-G3-SB2`）連續四次把真實開發庫的字面密碼寫進證據檔／文件內容，四次都是
檔名完全正常的 `.md`／`.json` 檔，hook 從未攔下任何一次：

| # | 外洩 Commit | 修正 Commit | 位置 |
|---|------------|------------|------|
| 1 | `ed6f38e` | `581950a` | 證據 JSON `rerun_instructions`（本機開發預設密碼） |
| 2 | `581950a`（修正 #1 時自己引述外洩內容又寫出字面值） | `32250d2` | `CHALLENGES.md` CHAL-008 §1 |
| 3 | `34bcc5f` | `655f740` | `UG_G3_SB2_routing_real_db_write.json` 兩處（`PGPASSWORD`／`POSTGRES_PASSWORD`） |
| 4 | `655f740`（修正 #3 時自己引述外洩內容又寫出字面值） | `7dd382c` | `CHALLENGES.md` CHAL-008 §6 |

**四次都是同一個人（同一個 PM／agent 角色）用同一雙眼睛複查，也都沒抓到**——
第 2、4 次尤其值得注意：**修正一個外洩的動作本身又製造了一次外洩**，因為
「描述外洩內容」與「複製外洩內容」在文字層面長得一樣。這正是 `CLAUDE.md` §9A.1
的教訓套用在「人眼複查」而非「機械檢查」上的版本：**人眼複查若拿著同一把有洞的
尺（同一種疏忽模式），一樣量不出洞在哪裡**——需要換一把尺，也就是本提案要做的事。

**本提案第一版修正過程本身又發生第五次**（描述事故 #3 時同樣把字面值
「postgres」寫了進去，撰稿階段用 `grep`（非 `git grep`——未追蹤的新檔案
`git grep` 預設抓不到）發現並修正，未進 commit 歷史）。這件事本身寫進 §4.1
的設計理由：**掃描機制必須掃描 staged 內容，而不能只依賴 `git grep`。**

## 2. Problem（問題）

若不處理，下一次任何人（包含未來的我）在證據檔或文件裡貼真實連線指令、日誌
片段或錯誤訊息時，只要不是這五次已經學到教訓的具體場景，同一類疏忽會再發生。
**機制層的防線目前完全依賴人眼**，而人眼已經證明在這個特定任務上不可靠
（5/5 沒抓到，其中 3 次是「修正／描述前一次事故時又犯」）。

## 3. Alternatives Considered（考慮方案）

1. **只加強人眼複查的提醒**——已經做過兩次（CHAL-008 原案 + §6 追記），結果是
   第三、四、五次照樣發生。人眼複查對這個任務的失敗率已有實測數據。
2. **把檢查 3 擴充為掃描 staged 內容**（本提案採用）——machine-enforced。
3. **完全交給人工複查，不機械化**——與方案 1 同一個問題。

## 4. Decision（已實作，待 PO 核准狀態）

### 4.1 掃描樣式——兩輪實測後採寬樣式 + `-i`

**第一輪（PO 原建議）**：`(^|[^A-Za-z_])pass(word)?\s*=\s*\S+`（`-i`）。
**實測（Python `re`）**：不誤擋 `bypass=<…>`／`compass=<…>`，但**也不匹配
`PGPASSWORD=<…>`／`POSTGRES_PASSWORD=<…>`——本案實際外洩的樣式本身**。採用會複現
要修的漏洞，見本文件修正歷史。

**第二輪（PM 提出）**：`grep -P` lookbehind `(?<![a-z])(pass(word)?|PASS(WORD)?)`
（不加 `-i`，明確列出大小寫兩形式）。**PO 複審實測發現**：漏 camelCase
（`dbPassword=`／`myPassword=`）與 `Password = <值>`（首字大寫），且誤擋
`BYPASS=<1>`（全大寫英文字）——lookbehind 只排除小寫字母，對大寫／camelCase
邊界的處理不一致。

**第三輪（PO 裁定，採用）**：**寬樣式 + `-i`，不用 lookbehind 邊界條件**：

```bash
PASS_PATTERN='pass(word)?[[:space:]]*=[[:space:]]*'
git diff --cached -U0 \
    | grep -E  '^\+' \
    | grep -vE '^\+\+\+ ' \
    | grep -iE "${PASS_PATTERN}[^[:space:]]+" \
    | grep -viE "${PASS_PATTERN}<"
```

五段管線：

0. `git diff --cached -U0` —— 只看這次 commit 真正新增／變更的內容
1. `grep -E '^\+'` —— 只看新增行
2. `grep -vE '^\+\+\+ '` —— 排除 diff 的 `+++ b/<path>` 檔名標頭（見 §4.2(b)）
3. `grep -iE "${PASS_PATTERN}[^[:space:]]+"` —— 寬樣式命中，不分大小寫
4. `grep -viE "${PASS_PATTERN}<"` —— 白名單：值以 `<` 開頭者放行（第 4 段
   同樣要 `-i`，否則 `PGPASSWORD=<value>` 的大寫形式不會被正確排除——
   PM 第一次寫漏了這個 `-i`，PO 複審指出）

**取捨（PO 裁定的方向）**：寬樣式會誤擋 `bypass=<…>`／`compass=<…>` 等英文字，但
**假陽性看得見、一行改 `<value>` 就解；假陰性看不見，下一次事故才知道**——
`CLAUDE.md` §5「寧可誤擋，不可誤放」。repo 現況掃描 `bypass=<…>`／`compass=<…>`
零筆（唯一命中的是本文件自己的說明文字，已改寫避開，見下）。

**實測結果**（VERIFIED，10 項情境，見 §7 完整清單與原始輸出）：全部攔下
`PGPASSWORD=<…>`／`POSTGRES_PASSWORD=<…>`／`password=<…>`／`Password = <值>`／
`dbPassword=<…>`（camelCase）／`bypass=<1>`（接受的假陽性）；全部放行 `<value>`
佔位符、檔名含 `PASSWORD=<…>` 但內容無關、`git mv` 純搬移、移除含密碼的行。

**⚠ 不得用命令替換 `$(...)` 包住整條管線再讀 `PIPESTATUS`**——命令替換會讓
`PIPESTATUS` 只留一個元素（實測驗證：直接管線得到 5 個元素，包住
`$(...)` 後只剩 1 個）。正確作法：先以 `> /dev/null` 取得逐段 `PIPESTATUS`
（`/dev/null` 是裝置而非檔案，不違反 hook「不寫入任何檔案」的約束），確認
乾淨後才用命令替換重跑一次以取得命中內容供顯示（見 §4.3、`.githooks/pre-commit`
實際程式碼）。

**範圍**：只處理 `password` 家族。`api_key=<…>`／`token=<…>`／連線字串裡的
`://user:pw@host` 留待未來需要時再擴充，不在本提案一次做完。

### 4.2 已知假陽性與對應處理

**(a) 白名單機制——只認尖括號佔位符**

原案「同一行含 `throwaway` 字樣即放行」是一個洞（PO 2026-09-10 第一次複審
指出）——四次事故的拋棄式容器字面值就等於真實開發庫密碼，任何人加註
`# throwaway` 就能通過。**規則：命中樣式的行，等號後的值必須以 `<` 開頭，
否則一律 abort。**

**現況掃描到的合法例外**：

| 位置 | 值 | 性質 |
|------|-----|------|
| `DB_MIGRATION_PLAN.md:380` | `POSTGRES_PASSWORD=<test 字樣>` | 文件範例，非真實憑證——**已修正為 `<value>`** |
| `doc/upgrade/gates/closed/` 5 處 | `tmp_sb1`／`tmp_sb1_after`／`sb4_tmp_pass` 等 | 已拆除拋棄式容器的臨時密碼，記載於已關閉的 Gate 過程文件——**不需白名單，見 (c)** |
| 寬樣式新增的假陽性：`bypass=<…>`／`compass=<…>` 等英文字 | — | repo 現況零筆（僅本文件說明文字提及，已用 `<…>` 形式書寫避開自我觸發） |

**不建立「值等於已知字典裡的常見測試字串就放行」的啟發式規則**——只認 `<`
開頭一種語法，其餘一律 abort，要求人工確認後才能改寫或用 `--no-verify`
（需 PO 授權）。

**(b) `+++ b/<path>` 檔名標頭誤擋——已實測證實會發生，已修正**

`git diff --cached -U0` 的 `+++ b/<path>` 這一行以 `+` 開頭；若檔名剛好含
`PASSWORD=<值>` 這種形狀的文字，樣式會命中檔名標頭而非真正的內容。

**實測**（隔離拋棄式 git repo，不動本專案任何檔案）：建立檔名為
`PASSWORD＝leftover_test_value.txt`（全形等號僅為避免本文件自我觸發，
實際測試檔名用半形 `=`；檔名本身即為測試對象，不受本文件
自身合規要求約束——它是被掃描的『內容』，不是本文件的敘述文字）、內容為
`hello`（與密碼完全無關）的檔案：未加 `grep -vE '^\+\+\+ '` 排除時，該檔名
出現在 diff 的 `+++ b/<path>` 標頭而被誤判命中（`grep` exit 0，會誤擋一個
與密碼無關的 commit）；加上排除後 exit 1，不誤擋；同一環境下對真正的內容
洩漏重新驗證，排除規則**不影響**真實洩漏仍被抓到。兩個方向都驗證過。

**(c) `git mv` 進 `doc/upgrade/gates/closed/`——路徑排除規則不需要**

**實測**：對一個內容含歷史密碼字面值的既有檔案執行純 `git mv`（無內容變更，
100% similarity rename），`git diff --cached -U0` 只有 rename 中繼資料
（`similarity index 100%`／`rename from`／`rename to`），**零 `+` 內容行**。

**結論：不需要路徑排除規則**。本檢查的設計（只看 `-U0` 輸出裡的 `^\+` 行）
已經結構性地只掃描「這次 commit 真正新增或變更的內容」，不會重新掃描檔案
裡未變動的既有行——不論那個檔案在哪個目錄。加一條路徑排除規則只是徒增一條
「看起來合理但沒對應到真正風險」的規則，拿掉它設計更簡單、保護力不變。

⚠ **實作驗證過程中的插曲**：第一次驗證此情境時，測試用「歷史密碼」寫成
`PGPASSWORD=<old_throwaway 字樣，未加 `<` 前綴>`（即不合規寫法）——**這個值本身會被本檢查正確
攔下**，導致模擬「歷史 commit」那一步先被擋，git mv 那一步因此看到的是
「尚未真正提交、只是重新 staged 的新檔案」而非「重命名」，`git status`
顯示 `A`（新增）而非 `R`（重命名），一度誤判為「hook 破壞了 git 的重命名
偵測」。**修正測試方法**（對建立歷史前提的那個 commit 使用 `--no-verify`，
模擬「內容早於本檢查存在」，git mv 那一步不加 `--no-verify`）後，正確重現
純 rename 且零 `+` 行。**這件事本身也是一個提醒**：本檢查上線後，任何人
都無法再對新內容使用不帶 `<` 的歷史式寫法，即使目的地是 `closed/`。

### 4.3 Fail-closed（已實作三分支判斷）

`grep` 本身異常（不存在、執行失敗、權限問題等）時必須 abort，不得 fail open。

**實測**（隔離環境，PATH 最前插入一個永遠 `exit 2` 的 `grep` 頂替腳本，
保留真實 Git Bash 環境其餘部分完整——直接砍掉整個 PATH 會連 `bash.exe`
自己都因缺相依 DLL 崩潰，`STATUS_DLL_NOT_FOUND`，那不是本場景要測的東西）：

- **天真判斷**（`exit code == 0 ? ABORT : PASS`）：`grep` 異常時管線最終
  exit code 非 0（可能是 2 或其他值），天真判斷會**誤判為「未命中→PASS」**
  ——grep 根本沒正常跑，commit 卻被判定通過。
- **修正判斷**（三分支：`0`→abort；`1`→pass；**其餘**→abort 並印出
  「工具鏈執行異常，fail-closed」）：實測 `PIPESTATUS` 為 `0 2 2 2 2`
  （`git diff` 正常、四段 `grep` 皆因頂替腳本回傳 2），正確走 fail-closed
  分支，commit 被 abort。

### 4.4 命中值遮罩（PO 2026-09-10 三次複審追加，已實作）

**問題**：終版實作把命中的 `$CONTENT_HITS`（含字面值）原樣 `echo` 到終端——
第一版提案 §4.2(a) 原文「不印出完整內容」在實作階段消失了。本案四次外洩裡
兩次的路徑正是「終端輸出被抄進文件」（CHAL-008 §1／§6），hook 自己把值印
出來，等於替下一次抄寫備好材料。

**修正**：印出前先以 `sed -E "s/(${PASS_PATTERN})[^[:space:]]+/\1***/I"`
遮罩，只留欄位名（`PGPASSWORD=<…>`／`password=<…>` 等），值一律顯示為 `***`：

```bash
echo "$CONTENT_HITS" | sed -E "s/(${PASS_PATTERN})[^[:space:]]+/\1***/I" | sed 's/^/        /'
```

**實測**（host 與容器皆確認可用）：`+PGPASSWORD=<real 字樣>` → 印出
`+PGPASSWORD＝***`（全形僅為避免本文件自我觸發，見 §7）；
`+Password = <值>` → `+Password ＝ ***`（同上）。

## 5. Trade-offs（取捨）

- **False negative**：`passwd=` 縮寫、其他憑證家族（API key、token、連線
  字串 `://user:pw@host`）本提案不處理，之後需要各自驗證才能擴充——寧可
  範圍窄但確定有效。
- **False positive 需要人工介入**：`bypass=<…>`／`compass=<…>` 等英文字會被誤擋，
  改寫成 `<…>` 形式或避開 `pass` 與 `=` 直接相鄰的寫法即可解——這是刻意的摩擦，
  比照 hook 既有其他檢查「寧可誤擋，不可誤放」的取捨。
- **效能**：`git diff --cached -U0` 對大型 diff 仍屬毫秒級。

## 6. Affected Components（已完成）

- `.githooks/pre-commit`：檢查 3 擴充為「檔名層 + 內容層」，含五段管線與
  fail-closed 三分支判斷。
- `CLAUDE.md` §12.4：四項檢查表格檢查 3 那一列、繞過說明對應句，各加一句
  說明內容層（PO 明確授權範圍，僅此兩處）。
- `DB_MIGRATION_PLAN.md:380`：`POSTGRES_PASSWORD=<test 字樣>` → `POSTGRES_PASSWORD=<value>`。

## 7. Verification（已執行，VERIFIED THIS SESSION）

**方法**：Python 腳本驅動的隔離拋棄式 git repo（比照 `CLAUDE.md` §11A.4——
不用 shell 鏈式條件；每個情境各自獨立的 `tempfile.mkdtemp()` 目錄，
`shutil.rmtree()` 保證還原，不影響本專案任何檔案）。每個情境把
`.githooks/pre-commit`（實際檔案，非重寫的複本）複製進臨時 repo、設定
`core.hooksPath`，實際執行 `git commit` 觀察真實 hook 行為。

| # | 情境 | 預期 | 實測結果 |
|---|------|------|---------|
| 1 | `+PGPASSWORD=<real 字樣>` | BLOCKED | ✅ exit 1，ABORT 訊息含該行 |
| 2 | `+Password = <x 字樣>` | BLOCKED | ✅ exit 1 |
| 3 | `+dbPassword=<x 字樣>`（camelCase） | BLOCKED | ✅ exit 1 |
| 4 | `+bypass=<1 字樣>`（接受的假陽性） | BLOCKED | ✅ exit 1 |
| 5 | `+PGPASSWORD=<依 .env>` | ALLOWED | ✅ exit 0 |
| 6 | `+POSTGRES_PASSWORD=<random>` | ALLOWED | ✅ exit 0 |
| 7 | 檔名含 `PASSWORD=<…>`、內容無關 | ALLOWED | ✅ exit 0 |
| 8 | `git mv` 歷史密碼進 `closed/`（純 rename） | ALLOWED | ✅ exit 0，diff 確認零 `+` 行、`similarity index 100%` |
| 9 | 移除一行含 `password=<…>` 的內容 | ALLOWED | ✅ exit 0（`-` 行不受檢） |
| 10 | `grep` 異常（頂替腳本 exit 2） | ABORT（fail-closed） | ✅ exit 1，`PIPESTATUS: 0 2 2 2 2`，印出「工具鏈執行異常，fail-closed」 |
| 11 | `+PGPASSWORD=<字面值>`（§4.4 命中值遮罩） | BLOCKED，且輸出不含該字面值 | ✅ exit 1，輸出中該值出現次數為 0 |

**11/11 通過**。原始輸出（情境 1、10、11 節錄，其餘同型）：

```
[3/4] 秘密偵測（檔名／內容）
      ABORT — staged 新增內容疑似含字面密碼（內容判準，GOV-13）：
        +PGPASSWORD＝***   （原始輸出為半形 =；遮罩後的 *** 本身仍會被本檢查
                             判定為「非 < 開頭的值」而命中，本文件改全形 ＝
                             僅為避免自我觸發，不影響遮罩機制本身的正確性）

      值若非真實憑證，改為 <value> 佔位符後重新 commit。
```

```
[3/4] 秘密偵測（檔名／內容）
      ABORT — 內容秘密掃描工具鏈執行異常（PIPESTATUS: 0 2 2 2 2），fail-closed
```

**驗證環境問題與修正**（誠實揭露）：

1. 驗證腳本第一版用 `shutil.rmtree(tmp, ignore_errors=True)` 清理臨時 repo，
   `ignore_errors=True` 靜默吞掉了刪除失敗——第一輪跑完後 Windows temp 目錄
   下留有約 60 個未清除的 `gov13_*` 資料夾。**已發現並手動清除，確認清空**。
   這是本次驗證過程自己的一個「靜默失敗被當成成功」案例，記在這裡而不是
   悄悄修掉不提。
2. 情境 10（`grep` 異常）第一版直接清空整個 `PATH`，導致 `bash.exe` 因缺
   相依 DLL 崩潰（`STATUS_DLL_NOT_FOUND`），得到空白輸出，一度誤判「已驗證
   fail-closed」——**實際上什麼都沒測到**。改為只在 PATH 最前插入頂替
   `grep` 腳本、保留真實環境其餘部分後，才真正驗證到 fail-closed 分支。

## 8. Remaining Risks

- 白名單語法（尖括號佔位符）本身仍可能被誤用（例如把真實密碼的一部分字元
  換成尖括號、其餘保留）——這是機制信任邊界的取捨；真正的防線仍是「不要在
  文件裡寫真實連線指令」這個更上游的習慣。
- 本提案通過後，過去的事故不會被追溯攔下（§11A 不改寫歷史）。
- 已知殘留缺口（`passwd=` 縮寫、其他憑證家族）非遺漏，是刻意縮小驗證範圍
  的結果，需要之後另案擴充驗證。

---

## 附錄：GOV-14（2026-09-22）——樣式只認 `=`，YAML／JSON 的 `:` 分隔符是盲的

**觸發**：專案要把 repo 改為 public，唯讀查證私有歷史時發現：已經公開在
`origin/main` 的 2 個 commit（`.devcontainer/docker-compose.yml` 的
`POSTGRES_PASSWORD: <值>`、`src/loaders/db_writer.py` 的 `"password": "<值>"`）
用的正是**冒號分隔**語法——`PASS_PATTERN='pass(word)?[[:space:]]*=[[:space:]]*'`
只認 `=`，對這兩種寫法結構上是瞎的。**檢查 3 對它剛好要擋的那兩個實際案例
沒有偵測力**，是 §9A.1「結構上無法失敗的檢查不是檢查」的又一個實例——只是
這次不是「從未失敗過」，是「面對兩種特定寫法必然不會觸發」。

**修法**：`PASS_PATTERN` 改為 `pass(word)?['"]?[[:space:]]*[:=][[:space:]]*`
（欄位名後允許一個可有可無的引號，分隔符同時接受 `:` 與 `=`）；白名單
（第 4 段）同步從 `${PASS_PATTERN}<` 改為 `${PASS_PATTERN}['"]?<`，理由見下方
「自己犯的兩次」。

**Known-FAIL（在 `/tmp` 拋棄式 repo 實際構造並執行，非猜測）**：

| 案例 | 內容 | 修法前 | 修法後 |
|---|---|---|---|
| A | `POSTGRES_PASSWORD: <非佔位符>` | 不擋（漏） | **擋** |
| B | `{"password": "<非佔位符>"}` | 不擋（漏） | **擋** |
| C | `{"password": "<dev-default>"}`（佔位符） | 不擋 | 仍不擋（無迴歸） |
| D | `POSTGRES_PASSWORD: <placeholder>`（佔位符） | 不擋 | 仍不擋（無迴歸） |
| E | `password='<placeholder>'`（既有寫法） | 不擋 | 仍不擋（無迴歸） |
| F | `PGPASSWORD=<placeholder>`（既有寫法） | 不擋 | 仍不擋（無迴歸） |
| G | `password='<非佔位符>'`（既有寫法） | 擋 | 仍擋（無迴歸） |

**自己犯的兩次，都是替這次修法本身跑 known-FAIL 時才發現，不是理論推演**：

1. 第一版只加了 `[:=]`，用案例 B 實測：**仍然不擋**。原因是 JSON 把欄位名
   包在引號裡（`"password"` 後面才接冒號），欄位名與分隔符之間多了一個
   收尾引號，`pass(word)?` 後面直接接 `[:=]` 抓不到那個引號。改為
   `pass(word)?['"]?`。
2. 改完案例 B 能擋了，但案例 C（`"password": "<dev-default>"`，本檔與
   `GIT_HISTORY_CREDENTIAL_PURGE_GATE_A_PROPOSAL.md` 都用這個寫法）**被
   誤擋**——白名單原樣式要求值緊接著 `<`，但 JSON／單引號寫法的值外面
   還包一層引號，白名單抓不到那層引號，把合法佔位符判成危險。白名單樣式
   同步加 `['"]?`。

**CHAL-008 的第五次實例，就是本案自己**：查證這件事並寫成 Gate A 提案
（`GIT_HISTORY_CREDENTIAL_PURGE_GATE_A_PROPOSAL.md` 初版）時，為了具體列出
「8 個 commit 各自的字面值出現在哪」，把該預設值原樣寫了十幾處——複核時
被 PO 用本案（GOV-14）修好的樣式判準抓到，全部改為 `<dev-default>` 佔位符。
**同一個「描述外洩時把外洩內容原樣抄進描述」的形狀，這次不是發生在
commit message，是發生在一份分析文件的草稿裡**——證明這個病灶不限於
「修 bug 時的 commit message」這個場景，任何回顧歷史事故的新文件都可能
重演。

**驗證**：容器內 `gate0_contract_check.py` exit 0；全套測試不受影響（本案
只動 `.githooks/pre-commit`，不動任何 Python 原始碼）。

---

## 附錄二：GOV-14 第二輪（2026-09-22）——複核方回退第一版修法，48 筆假陽性

**觸發**：第一版修法（只加 `[:=]` 與收尾引號）送審查方複核後，複核方獨立對
整個受版控樹（排除 `.md`）跑同一套樣式，得到 **48 筆非白名單命中**，
全部是本專案自己的合法寫法，不是外部樣式：

1. `os.environ["POSTGRES_PASSWORD"]` 讀值（`scripts/verify/measure_ptt_keyword_coverage_offline.py:94`、
   `database/init_db.py:30` 等）——真正原因不是這行本身危險，是舊樣式
   `pass(word)?` 的 `(word)?` 可選，讓單獨「pass」四個字母也算命中，
   於是 `E3_IS_A_FALSE_PASS`（`doc/upgrade/gates/evidence/G2_SB7_controlled_run_results.json:34`）、
   `why_not_adjusting_to_pass`（`doc/upgrade/gates/evidence/PRE_G3_03_ptt_segment_A_criteria.json`）、
   `WHY_NOT_REWRITTEN_AS_PASS`（`doc/upgrade/gates/evidence/PRE_G3_01_refetch_1495.json:99`）
   這類把 PASS 當子字串的既有識別字全部誤中，`os.environ[...]` 只是剛好
   跟在同一行的欄位名後面被一起抓進去。
2. 白名單只認值以 `<` 開頭，漏掉 `${VAR}` 展開、`os.environ`／`os.getenv`
   呼叫、`%(name)s` 舊式格式化字串——這些都是「有值但非字面密碼」的合法
   寫法，樣式沒有對應分支。

**修法（複核方提出，本檔獨立以 `/tmp` 拋棄式 repo 重測，未在真實 repo 測試）**：

- 鍵名樣式由 `pass(word)?` 改為 `(^|[^A-Za-z0-9_])(password|[A-Z_]*PASSWORD)`：
  要求完整比對 `password` 或 `[A-Z_]*PASSWORD`（`-i` 下大小寫皆可），不再
  接受單獨 `pass`；並加前置邊界，避免子字串誤中。`[A-Z_]*` 讓
  `POSTGRES_PASSWORD`／`PGPASSWORD` 這類底線前綴或緊貼前綴仍可完整比對。
- 白名單獨立成 `WHITELIST_SUFFIX`（與 `PASS_PATTERN` 分開定義、兩處 grep
  呼叫共用同一個變數，不會各自維護一份而漂移），值前綴由僅 `<` 擴為
  `<`／`$`／`os.environ`／`os.getenv`／`%(` 五種。

**擴大樣式仍不足以歸零**：全 tree 掃描（排除 `.md`）在套用新樣式後，
剩餘命中全部是既有測試 fixture、evidence JSON、`src/loaders/db_writer.py`
的 `required_env` 角色說明字典裡的字面短值（如欄位名接冒號，值只是單一
短字母，未包 `<>`）——這些不是白名單能安全放寬的「合法值形狀」，是
「本來就該寫成佔位符卻沒寫」的既有債務。依 CLAUDE.md §9A.1（寧可誤擋，
假陽性一行改 `<value>` 就解）的哲學，選擇逐一改寫成佔位符，而非放寬樣式
去遷就它們（放寬到能吸收這些，會重新打開子字串誤判的路）。改寫的 11 處：
`tests/test_ui_contracts.py`、`tests/test_real_articles_pipeline.py`、
`tests/test_first_daily_etl_gap_autofill.py`、
`tests/test_first_daily_etl_cause_f_wiring.py`、`tests/test_panel_dataset.py`、
`tests/test_sb2a_backfill_features.py`、
`tests/test_sb2a_write_triple_barrier_labels.py`、
`tests/test_db_read_semantics.py`、`tests/test_tracking_keyword_integrity.py`、
`src/loaders/db_writer.py`（`required_env` 字典值）、
`doc/upgrade/gates/evidence/G2_SB6_dump_restore_verification.json`
（`docker run` 指令裡拋棄式容器的密碼參數，原為兩字元字面值，已改為
`<disposable-test-value>`）。全部是測試替身或已結束容器的無意義佔位值，
非真實憑證。

**全 tree 掃描結果（本檔獨立重跑，VERIFIED THIS SESSION）**：

```
git ls-files -z -- . ':!*.md' | xargs -0 grep -InE "${PASS_PATTERN}[^[:space:]]+" \
  | grep -viE "${PASS_PATTERN}${WHITELIST_SUFFIX}"
```

排除 `.md` 後：**0 筆**。含 `.md` 另跑一次額外查證，見下方「範圍說明」。

**範圍說明——為何排除 `.md` 才是本次「歸零」的正確範圍**：含 `.md` 重跑
得到 28 筆，全部落在兩處：(a) `doc/upgrade/gates/closed/*.md`——已結案 Gate
的 Gate B 送審文件，內容是**歷史事實**（當時實際執行的拋棄式容器指令、
當時的測試 diff 摘錄），依 §16.3 屬過程文件的既有生命週期終點，不是
本輪要改動的對象；改寫它們等於竄改已核准的歷史紀錄，與本次會期稍早
被 PO 否決的「歷史改寫」提案是同一類疑慮。(b) `doc/evidence/CHALLENGES.md`
既有兩行（233、259 行，均為既有內容，非本輪新增——已用
`git diff -- doc/evidence/CHALLENGES.md | grep '^\+' | grep -i password`
核對為空、確認不在本輪 diff 內）。這些既有內容不會被本輪 commit 重新
staged，hook 實際只掃 `git diff --cached -U0` 的新增行，因此不影響本輪
commit 能否通過——已用「模擬 hook 對本輪實際 working-tree diff 的檢查 3」
驗證為 0 筆命中。

**Known-FAIL 第二輪（在 `/tmp` 拋棄式 repo 實際構造並執行，含真實專案程式碼行，
事後已 `rm -rf` 整個拋棄式 repo）**：

| 案例 | 內容 | 應為 | 實測 |
|---|---|---|---|
| A | `password = "<非佔位符字面值>"` | 擋 | **擋**（exit=1） |
| B | `{"password": "<非佔位符字面值>"}` | 擋 | **擋**（exit=1） |
| E | `PASSWORD: <非佔位符字面值>`（無引號，YAML 裸值形） | 擋 | **擋**（exit=1） |
| G | `PGPASSWORD=<非佔位符字面值>` | 擋 | **擋**（exit=1） |
| C | `{"password": "<dev-default>"}`（佔位符） | 不擋 | 不擋（exit=0） |
| D | `password = '<placeholder>'`（佔位符） | 不擋 | 不擋（exit=0） |
| H | `"password": os.environ["POSTGRES_PASSWORD"],`（真實碼，`measure_ptt_keyword_coverage_offline.py:94`／`init_db.py:30` 同型） | 不擋 | 不擋（exit=0） |
| I | `"E3_IS_A_FALSE_PASS": {`（真實碼，`G2_SB7_controlled_run_results.json:34`） | 不擋 | 不擋（exit=0） |
| J | `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`（**代表性建構，非真實碼**——僅驗證白名單 `$` 分支機制本身有效，見下方「案例 J 的釐清」） | 不擋 | 不擋（exit=0） |
| K | `"password": os.getenv("POSTGRES_PASSWORD")`（**代表性建構，測試 `os.getenv` 白名單分支**） | 不擋 | 不擋（exit=0） |

C／D／H／I／J／K 六個「不擋」案例均已確認**實際 commit 成功建立**（不只是
印出 PASS），再整個 `rm -rf` 拋棄式 repo 還原。

**案例 J 的釐清（PO 2026-09-22 裁定：是複核方寫錯，PM 查對了）**：複核方原引用
「`POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}` —— compose 的變數展開」並指為
`docker-compose.yml` 的展開行，但那是**憑印象舉例，沒有查證**。獨立查證
`git grep -nE '\$\{.*PASSWORD'` 全樹**零命中**，`.devcontainer/docker-compose.yml`
目前兩個服務都用 `env_file` 指向 `../.env`，沒有任何以 `PASSWORD` 為鍵、
inline 冒號接變數的展開行。**裁定：J 維持代表性建構**，表中已明確標示
「驗證白名單 `$` 分支機制，非真實碼」，不必為了湊真實案例而編造一行專案裡
不存在的程式碼。複核方已將此記入自身失敗模式（憑印象引用而未查證的既有碼）。

**第三輪：複核方獨立以拋棄式 repo 對 14 個案例逐一實測（`VERIFIED THIS SESSION`，
複核方執行）**，PASS——本文件表列的 10 案全部覆核一致，複核方另外多測兩個表外
案例，結果同樣正確：

- 鍵名字首大寫的 YAML 裸值形（`Password` 接緊鄰冒號）——**正確擋下**。
- `"why_not_adjusting_to_pass":`（真實碼，`doc/upgrade/gates/evidence/PRE_G3_03_ptt_segment_A_criteria.json`）——**正確放行**（不含完整 `PASSWORD` 字面）。

**已知限制（設計外邊界，記錄不修）**：`passwd = <值>`（`password` 的縮寫）**不會**
被鍵名樣式攔下——`password|[A-Z_]*PASSWORD` 兩個分支都不比對「passwd」這個縮寫。
本專案目前沒有任何檔案使用這種縮寫寫法（已用同一套樣式的全 tree 掃描間接佐證：
若存在，會以完全不同的字元序列出現，不在既有 48／28 筆假陽性清單內）。**不修**，
理由：擴大樣式去涵蓋一個本專案從未出現過的縮寫寫法，只會重新增加誤判面（`passwd`
比 `password` 更容易出現在無關識別字裡，例如 `passwd_file_reader`）；一旦專案內
真的出現 `passwd=` 寫法，屆時再依同一套「known-FAIL 實測＋全 tree 歸零」流程補上，
不預先猜測。

**驗證**：容器內（Python 3.14.6，15 套件全 PRESENT）`gate0_contract_check.py`
`exit=0`，Part B 15/15 PASS，1 個既有登錄的 WARN（DRIFT-007，與本案無關）；
全套測試 `Ran 1140 tests` / `OK`；`git diff --numstat` 與 `-w` 無落差，無格式／
行尾夾帶。
