# Stock Prediction System 2 — 金融情緒與股價趨勢預測系統

從 PTT／股市資料擷取、情緒分析、特徵工程、機器學習訓練到 Streamlit BI 視覺化的
End-to-End 金融情緒與股價趨勢預測系統。同時作為個人轉職作品，保留完整的
Decision Evidence（決策證據）與 Problem-Solving Evidence（問題解決證據）。

> 本檔僅提供快速入門。**專案的權威規則、規格與治理制度不在本檔**，見下方「文件地圖」。

---

## 架構概覽

```
extractors/  →  transform/  →  loaders/  →  main_etl_pipeline.py  →  ml/  →  ui/ (app.py)
（外部資料擷取）  （清洗／特徵工程）  （資料庫寫入）  （ETL 總指揮官）  （模型訓練／推論）  （Streamlit 儀表板）
```

| 目錄 | 責任 |
|------|------|
| `src/extractors/` | 向外部取得原始資料（yfinance、TWSE、PTT、AI 熱門詞探索） |
| `src/transform/` | 資料清洗、NLP 情緒分析、特徵工程 |
| `src/loaders/` | PostgreSQL 讀寫（`DBWriter`） |
| `src/ml/` | 時序切分、多模型訓練與競技、即時推論 |
| `src/ui/` | Streamlit 前端（`app.py` 為進入點） |
| `database/` | Schema DDL（`schema.sql`）與 Migration（`apply_migrations.py`） |
| `main_etl_pipeline.py` | ETL 總指揮官，串接 Extract → Transform → Load |

完整模組責任見 `doc/spec/SDD_Financial_Sentiment_System_v1.md`。

---

## 快速啟動（Dev Container）

本專案的**正式開發與測試環境**是 VS Code Dev Container（見 `CLAUDE.md` §3、§13.0）。
Windows host 為輔助環境，缺多項 Python 套件，其測試結果不支撐 ML／NLP／DB 路徑的宣稱。

1. 以 VS Code 開啟本專案，選擇「Reopen in Container」（需 Docker Desktop）。
2. 容器啟動後，啟用 pre-commit hook（新 clone／容器重建後必須執行一次，見 `CLAUDE.md` §12.4）：

   ```bash
   git config core.hooksPath .githooks
   ```

3. 初始化資料庫（首次或全新資料庫時）：

   ```bash
   python database/init_db.py
   ```

4. 啟動 Streamlit 儀表板：

   ```bash
   streamlit run app.py
   ```

---

## 執行測試

```bash
python -m unittest discover -s tests -p "test_*.py"
```

測試檔數與測試數請以下列指令重新核對，不要引用任何文件裡寫死的舊數字（測試持續新增，數字會變動）：

```bash
ls tests/test_*.py | wc -l
grep -ch "def test_" tests/test_*.py | awk '{s+=$1} END {print s}'
```

跨文件契約驗證（涉及資料契約的變更後必跑）：

```bash
python scripts/verify/gate0_contract_check.py
```

本專案沒有 pytest／lint（ruff、flake8、black）／型別檢查（mypy）／coverage／CI，
詳見 `CLAUDE.md` §13.2。

---

## 文件地圖

不確定該讀哪份文件時，先看 `doc/README.md`——回答「這份文件屬於誰、還活著嗎」。

| 先讀 | 回答什麼 |
|------|---------|
| `CLAUDE.md`（根目錄） | 每次工作都不能忽略的工程原則、環境、證據標籤、Commit／Git 紀律 |
| `doc/README.md` | 文件地圖：哪份文件屬於誰、還活著嗎 |
| `doc/governance/PROJECT_STATUS.md` §0 | 專案現在做到哪裡、哪個 Gate／Small Batch 已關閉 |
| `doc/governance/TEAM_PLAYBOOK.md` | 角色分工、PO 專屬批准事項、Gate／Small Batch 迴圈 |
| `doc/spec/PRD_Financial_Sentiment_System_v1.md` | 產品需求：系統要做什麼 |
| `doc/spec/SDD_Financial_Sentiment_System_v1.md` | 系統設計：模組責任與架構 |

---

## 開發環境

- Python（版本以 dev container 為準，見 `.devcontainer/`）+ PostgreSQL 18（Docker container）
- 依賴清單：`requirements.txt`（意圖檔）／`requirements.lock.txt`（GOV-03 已驗證之精確版本，重現性依據）
- 開發資料庫透過 bind mount 持久化於本機 `.devcontainer/postgres-data/`，**不得**於未經 PO 明確要求下刪除／重建

## 授權與貢獻

本專案目前為單人開發之作品集專案，暫無外部貢獻流程。

---

## 關於本 Repository 的歷史

本 repository 是完整開發歷史的**單一快照**。完整的逐步決策紀錄、Gate／Small Batch
治理過程與證據鏈保存在私有歷史中；本快照之後的文件內容如果引用了 commit hash，
該 hash 指向的是私有歷史，不在這個公開快照裡能找到。
