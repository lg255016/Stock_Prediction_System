---
name: bug-fix-protocol
description: >-
  Use this skill whenever investigating, diagnosing, or fixing bugs, errors, or unexpected runtime
  behavior. Enforces a two-Human-Gate protocol: diagnose and report root cause with impact analysis
  and verification plan while staying read-only, wait for explicit approval before editing, then
  report diffs plus test results with dependency-status disclosure and wait for explicit approval
  before committing. Requires contract-check when the bug touches a data contract.
---

# bug-fix-protocol — 除錯與修復標準作業流程

本 Skill 定義所有錯誤排查、Bug 修復與異常診斷的**強制程序**。

**核心目標**：杜絕未經溝通的擅自修改、杜絕隱蔽副作用，並確保每次修復都有
可稽核的驗證證據與授權閉環。

---

## 1. 核心不可違反原則

1. **先診斷回報，絕不私自改程式碼**
   使用者回報錯誤、提供 Traceback 或要求找問題時，**第一階段僅能唯讀調查**。
   **未取得 PO 明確批准前，嚴禁使用任何檔案編輯或寫入工具。**

2. **完整影響與回歸風險評估**
   診斷報告必須說明「為什麼會錯」「預計怎麼改」「會影響哪些模組／資料表」
   「是否有潛在副作用」。

3. **兩道 Human Gate**
   - **Gate A（修改准許）**：PO 同意修正方案後才能動手改程式碼。
   - **Gate B（Commit 授權）**：修改與測試完成後回報，PO 明確同意後才能 commit。

4. **端到端防回歸測試**
   除局部單元測試外，必須涵蓋上下游全流程，防範「修好 A 卻破壞 B」。
   **驗收標準見 §3。**

5. **非瑣碎問題強制歸檔**
   涉及架構彈性、限速、快取、並發或資料契約的 Bug，修復後必須依 `evidence-sync` skill
   歸檔至 `doc/evidence/CHALLENGES.md`。

---

## 2. 四步驟流程

```
使用者回報錯誤
      │
      ▼
步驟一：唯讀排查與診斷（嚴禁改任何檔案）
      │
      ▼
呈報診斷簡報：根因 / 建議方案 / 影響與副作用 / 驗證計畫
      │
      ▼
   🛑 Gate A：等待 PO 批准 ──── 未批准 ──▶ 回步驟一
      │ 已批准
      ▼
步驟二：實作 + 防回歸測試 + Challenge 歸檔
      │
      ▼
呈報修復報告：diff 摘要 / 測試結果與依賴狀態 / 歸檔紀錄
      │
      ▼
   🛑 Gate B：等待 PO 授權 Commit ──── 未授權 ──▶ 回步驟二
      │ 已授權
      ▼
步驟四：執行 Commit
```

### 步驟一：診斷與影響分析（唯讀）

**執行約束：維持唯讀，嚴禁修改任何檔案。**

1. 檢視 Traceback、日誌與相關原始程式碼，定位根因。
2. 評估資料流與上下游依賴（資料庫欄位、API 契約、模組介面）。
3. 呈報**Bug 診斷與修正建議簡報**：
   - **問題定位與根因**：哪個檔案、哪一行、觸發的精確條件
   - **預計修正方案**：如何修改、有無替代方案及其 Trade-off
   - **潛在影響與副作用**：是否影響其他模組、資料庫綱要或現有測試
   - **驗證計畫**：預計新增什麼測試案例
4. **🛑 停止，等待 PO 指示。**

### 步驟二：核准後實作、測試與歸檔

**執行約束：只有在 PO 明確批准後才能執行。**

1. 嚴格依核准方案進行最小範圍修改。
2. 撰寫端到端防回歸測試，驗證上下游連鎖反應。
3. 執行 §3 的驗收檢查。
4. 若為非瑣碎問題，依 `evidence-sync` skill 歸檔 Challenge。

### 步驟三：成果回報與請求 Commit 授權

**執行約束：嚴禁在此階段擅自 commit。**

依 `gate-submit` skill 產出五項強制證據，並包含：

- **修改檔案與變更摘要**
- **測試結果與依賴狀態揭露**（見 §3）
- **Challenge 歸檔紀錄編號**

**🛑 停止，明確請求 PO Commit 授權。**

### 步驟四：授權後提交

1. 依 Conventional Commits 規範執行 commit。
2. 執行 `gate-submit` 的格式夾帶偵測，確認無未揭露的行尾／空白變更。
3. 確認 `git status` 乾淨，回報 commit hash。

---

## 3. 測試驗收標準【本節取代舊版的「100% PASS」】

> 舊版本要求「全套測試必須 100% PASS」。該說法在本專案的實際環境下**會產生誤導**：
> 多個關鍵套件缺席，部分測試走 fallback 或 mock 路徑，從未真實執行。
> 把這種情況寫成「100% PASS」違反 `CLAUDE.md` §9.1 與 §13.3。

修復完成的驗收條件為以下三項**全部**成立：

### 3.1 全套測試通過

```bash
python -m unittest discover -s tests -p "test_*.py"
```

不得有 `FAILED` 或 `ERROR`。**貼出原始輸出**，不得只寫摘要。

### 3.2 環境依賴狀態揭露

```bash
python -c "import importlib.util as u; [print(f'{m:26}', 'PRESENT' if u.find_spec(m) else 'ABSENT') for m in ['numpy','pandas','sklearn','lightgbm','xgboost','psycopg2','jieba','snownlp','tenacity']]"
```

報告必須附此表。

### 3.3 明確標示走 fallback 未真實驗證的路徑

把 `ABSENT` 的套件對應到「哪些測試因此走 fallback 或 mock」，並明確標示這些路徑
**未經真實驗證**。

**正確寫法範例**：

> 全套測試通過。惟 `psycopg2` 缺席，本次修復涉及的 DB 寫入路徑全部走 `MagicMock` 替身，
> **真實 PostgreSQL 行為未驗證**；建議在 Dev Container 內補跑一次確認。

**禁止寫法**：

> ❌ 「全套測試 100% PASS，修復已完整驗證。」

### 3.4 資料契約相關 Bug 須併跑 contract-check

若 Bug 涉及欄位定義、資料契約、Schema 或跨文件規格：

```bash
python scripts/verify/gate0_contract_check.py
```

**exit 必須為 0**。此檢查會偵測單元測試抓不到的跨文件契約不一致。

---

## 4. 失敗範例（本 Skill 必須能擋下的東西）

### 失敗範例 A：跳過 Gate A 直接改程式碼

> ❌ 使用者貼上 Traceback，Agent 直接編輯檔案修復並回報「已修好」。

**為何 FAIL**：違反原則 1 與 3。PO 失去審查修正方案的機會，
也無從得知有哪些替代方案被放棄。

### 失敗範例 B：把降級環境的通過寫成完整驗證

> ❌ 「全套測試 154/154 PASS，Bug 已完整修復。」

**為何 FAIL**：違反 §3.2、§3.3 與 `CLAUDE.md` §9.1。

**偵測**：執行 §3.2 的指令，若有 `ABSENT` 而報告未揭露，即為違規。

### 失敗範例 C：資料契約 Bug 未跑 contract-check

> ❌ 修復了欄位對應錯誤，只跑單元測試就送審。

**為何 FAIL**：違反 §3.4。單元測試不會發現規格文件與 DDL 之間的不一致。

### 失敗範例 D：Gate B 未取得授權即 commit

> ❌ 測試通過後直接 commit，然後回報「已修復並提交」。

**為何 FAIL**：違反原則 3。Commit 授權是 PO 專屬權限
（`doc/governance/TEAM_PLAYBOOK.md` §2）。

---

## 5. 觸發時機

當使用者提及以下情況時，**立即啟動本 Skill**：

- 「我執行 ⋯ 出錯了」
- 「幫我找問題／修 Bug」
- 「這段程式碼好像有問題」
- 任何 runtime Exception 或非預期行為

---

## 6. 相關規則

- `CLAUDE.md` §9 — 證據標籤
- `CLAUDE.md` §13.3 — 環境依賴缺口
- `CLAUDE.md` §12 — Commit Policy
- `doc/governance/TEAM_PLAYBOOK.md` §2 — PO 專屬批准事項
- `gate-submit` skill — 送審前五項強制證據
- `evidence-sync` skill — Challenge 歸檔與傳播
