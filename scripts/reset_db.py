"""
scripts/reset_db.py — 資料庫安全清空重設工具

用於清空測試期間產生的股價、輿情文章、情緒快取與每日特徵髒資料，
並重新恢復乾淨的種子設定 (tracking_keywords 與 entity_mapping)。
"""
import sys
from pathlib import Path

# 將專案根目錄加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.init_db import reset_database


def main():
    print("=" * 60)
    print("🧹 金融情緒與股價預測系統 — 資料庫安全清空重設")
    print("=" * 60)
    try:
        reset_database(keep_seeds=True)
        print("🎉 資料庫已恢復乾淨基線狀態！")
    except Exception as e:
        print(f"❌ 資料庫重設失敗：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
