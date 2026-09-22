# src/config.py
# §0.5 #31：Gemini 模型名稱單一來源——原本 trend_discover.py 與 nlp_processor.py
# 各自硬寫 'gemini-flash-latest' 兩份，改為兩處共同引用本常數（見
# GEMINI_QUOTA_DISCIPLINE_GATE_A_PROPOSAL.md §3.3）。
#
# 09-17 真實執行 log（FIRST_DAILY_ETL_GAP_AUTOFILL_real_run_20260917_log.txt:405,415）
# 證實 'gemini-flash-latest' 當時解析為 'gemini-3.8-flash'，直接釘死該版本，
# 不再依賴 Google 端 'latest' alias 的隱性解析。
GEMINI_MODEL_NAME = "gemini-3.8-flash"
