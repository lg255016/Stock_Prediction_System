"""
scheduler.py — 金融情緒與股價趨勢預測系統 本機自動定時排程器

功能說明：
1. 每個交易日 (週一至週五) 下午 15:35 (台股盤後收盤資料出爐時段) 自動觸發 ETL 全流程 (爬蟲、NLP、特徵工程與模型推論)。
2. 常駐背景守護行程 (低耗能精確休眠，時間一到自動喚醒)。
3. 支援命令列參數 `--run-now` 即時手動觸發執行。
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 確保專案根目錄納入 Python 搜尋路徑
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from main_etl_pipeline import ETLPipelineManager

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Scheduler")

TARGET_HOUR = 15
TARGET_MINUTE = 35


def is_trading_weekday(dt: datetime) -> bool:
    """判斷指定日期是否為週一至週五 (交易日)"""
    return dt.weekday() < 5  # 0: 週一, 4: 週五, 5: 週六, 6: 週日


def get_next_run_time(now: datetime, target_hour: int = TARGET_HOUR, target_minute: int = TARGET_MINUTE) -> datetime:
    """
    計算下一個排程觸發時間點：
    若今天為平日且尚未超過 target_time，則為今天 target_time；
    否則尋找下一個平日之 target_time。
    """
    candidate = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

    if is_trading_weekday(now) and now < candidate:
        return candidate

    # 尋找下一個平日
    next_day = now + timedelta(days=1)
    while not is_trading_weekday(next_day):
        next_day += timedelta(days=1)

    return next_day.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)


def execute_daily_pipeline() -> bool:
    """執行每日完整 ETL 與預測管線"""
    logger.info("🚀 [排程觸發] 開始執行每日全自動 ETL 與預測任務...")
    start_time = time.time()
    try:
        pipeline = ETLPipelineManager()
        pipeline.run_all_daily_tasks()
        elapsed = time.time() - start_time
        logger.info(f"🎉 [任務成功] 每日例行任務全數執行完畢！耗時: {elapsed:.2f} 秒。")
        return True
    except Exception as e:
        logger.error(f"❌ [任務失敗] 執行過程發生異常: {e}", exc_info=True)
        return False


def run_scheduler_daemon(target_hour: int = TARGET_HOUR, target_minute: int = TARGET_MINUTE):
    """
    啟動常駐排程守護行程。
    """
    print("=" * 70)
    print("⏰ 金融情緒與股價趨勢預測系統 — 本機自動定時排程守護行程")
    print(f"📌 設定觸發時間：每個交易日 (週一至週五) {target_hour:02d}:{target_minute:02d}")
    print("💡 按下 Ctrl + C 可安全停止守護行程")
    print("=" * 70)

    while True:
        now = datetime.now()
        next_run = get_next_run_time(now, target_hour, target_minute)
        wait_seconds = (next_run - now).total_seconds()
        hours, remainder = divmod(int(wait_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        logger.info(f"⏳ 下次預定執行時間：{next_run.strftime('%Y-%m-%d %H:%M:%S')} (距現在約 {hours} 小時 {minutes} 分鐘 {seconds} 秒)")

        # 循環休眠檢查 (每 30 秒檢查一次，以防止系統休眠喚醒造成的時間漂移)
        while datetime.now() < next_run:
            sleep_duration = min(30, (next_run - datetime.now()).total_seconds())
            if sleep_duration <= 0:
                break
            time.sleep(sleep_duration)

        # 時間到達，觸發執行
        logger.info("🔔 排程時間已到達，正在啟動任務...")
        execute_daily_pipeline()

        # 執行後稍作等待 (避免同一分鐘內重複觸發)
        time.sleep(65)


def main():
    parser = argparse.ArgumentParser(description="金融情緒與股價預測系統 定時排程器")
    parser.add_argument(
        "--run-now", "-r", action="store_true", help="立即手動執行一次每日全流程任務，不等待排程時間"
    )
    parser.add_argument(
        "--hour", type=int, default=TARGET_HOUR, help=f"排程觸發小時 (預設: {TARGET_HOUR})"
    )
    parser.add_argument(
        "--minute", type=int, default=TARGET_MINUTE, help=f"排程觸發分鐘 (預設: {TARGET_MINUTE})"
    )
    args = parser.parse_args()

    if args.run_now:
        logger.info("⚡ 接收到 --run-now 參數，立即啟動每日全流程任務...")
        execute_daily_pipeline()
    else:
        try:
            run_scheduler_daemon(target_hour=args.hour, target_minute=args.minute)
        except KeyboardInterrupt:
            print("\n🛑 排程守護行程已由使用者手動中止。")
            sys.exit(0)


if __name__ == "__main__":
    main()
