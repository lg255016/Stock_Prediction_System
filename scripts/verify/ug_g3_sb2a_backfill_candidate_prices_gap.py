# -*- coding: utf-8 -*-
"""
UG-G3-SB2a 段 2 前置：`candidate_prices` 8 交易日全市場缺口回補
（2026-08-24～2026-08-28、2026-08-31～2026-09-02）。

**背景**：`UG-G3-SB2a` 段 2 既有 4 檔基線比對期間，PO 唯讀量到
`candidate_prices` 在上述 8 個交易日 TWSE＋TPEX **零列**（08-21 有 1,972
檔、09-03 有 1,972 檔，中間全空）。已以 TWSE 官方休市日期表（web search
交叉核對三個獨立來源）確認：**這 8 天皆非休市日**——2026 年 8 月僅有
一般週末，9 月僅 25 日（中秋節）、28 日（教師節）為假日，皆不落在此
區間，故此為真實的資料缺口，非市場休市。

另查證 2026-07-10（星期五）：**確認為颱風巴威（Bawei）造成的全日休市**
（多家新聞來源交叉核實：工商時報、經濟日報、自由財經、PChome、Yahoo奇摩
股市皆報導台股 7/10 因颱風休市一天），`candidate_prices` 該日無列**正確
反映市場實況，不是缺口，不需回補**。

**成因推測（未查證，供 PO 參考）**：`UG-G2-SB9` 四年候選池回補停在
2026-08-21，`UG-G2-SB7` 每日批次（`run_price_batch`）從 2026-09-03 才開始
執行，中間這段窗口沒有任何機制補上——一次性回補與每日增量之間有一段
時間差沒人銜接。

**設計**：逐日呼叫既有生產函式 `ETLPipelineManager.run_price_batch()`
（`main_etl_pipeline.py`，`UG-G2-SB7`），**不重新發明批次抓取邏輯**——
與 `run_all_daily_tasks()` 每日使用的是同一個函式，差別只在於本腳本可以
指定歷史日期（`run_all_daily_tasks()` 固定用
`previous_business_day()`，抓不到已經過去一段時間的缺口）。

**RISK-013**：這是**真實庫寫入**（`candidate_prices`，透過
`upsert_to_candidate_prices()` 的 `ON CONFLICT DO NOTHING`，冪等、不覆寫
既有列），需要 PRE 備份 + binding confirmation，比照段 1 全套協議。
**DEC-032 refusal 語意照舊**：任何一天遇到 `ServiceRefusedError`（429/403
等），**立即停止、不繼續後續日期**，把已完成與未完成的日期清楚回報，
不靜默略過、不自動重試。

**請求量估算**：8 天 × 2 市場（TWSE／TPEX）＝ **16 個邏輯請求**（`run_price_batch`
每市場 1 個邏輯請求，`UG-G2-SB7` 既有設計）。

⚠ 本腳本尚未對真實庫執行 `--write`——這是送 PO 複核的 runbook 草案，
首次執行需 binding confirmation（RISK-013 三項協議），比照
`UG-G3-SB1`／`UG-G3-SB2`／`UG-G3-SB2a` 段 1 流程。
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import psycopg2

REQUIRED_ENV = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
_MAX_BACKUP_AGE_SECONDS = 24 * 3600

# 8 個缺口交易日（PO 2026-09-11 唯讀量測確認：候選池全市場零列，且經
# TWSE 官方休市日期表交叉核對確認非休市日）。**刻意寫死清單，不用日期
# range 自動生成**——避免程式碼把一個尚未查證過的日期誤判為「缺口」而
# 自動納入；新缺口如有發現需先唯讀查證、更新這份清單，不是自動擴大範圍。
GAP_TRADE_DATES = [
    "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    "2026-08-31", "2026-09-01", "2026-09-02",
]

EXPECTED_ROWS_PER_DAY_APPROX = 1972  # 比照 08-21／09-03 既有量測（僅供合理性檢查參考）

ALL_MARKETS = ("twse", "tpex")


def _validate_dates_subset(dates_arg):
    """`--dates` 只能是 `GAP_TRADE_DATES` 的子集——這是**重試**工具，不是
    一般用途的任意日期批次抓取器。範圍外的日期一律拒絕執行，不猜測、
    不自動擴大（例如 2026-09-11 提案發現的 08-25／08-26 TPEX 重試場景，
    就是本參數存在的理由；任何不在原始查證清單內的日期都需要另外走
    唯讀查證流程，不能直接餵給本腳本）。"""
    if dates_arg is None:
        return list(GAP_TRADE_DATES)
    requested = [d.strip() for d in dates_arg.split(",") if d.strip()]
    invalid = [d for d in requested if d not in GAP_TRADE_DATES]
    if invalid:
        print(f"ERROR：--dates 含不在 GAP_TRADE_DATES 清單內的日期：{invalid}"
              f"（合法清單：{GAP_TRADE_DATES}）。拒絕執行。")
        sys.exit(1)
    return requested


def _validate_markets_subset(markets_arg):
    """`--markets` 只能是 `twse`／`tpex` 的子集。"""
    if markets_arg is None:
        return ALL_MARKETS
    requested = tuple(m.strip().lower() for m in markets_arg.split(",") if m.strip())
    invalid = [m for m in requested if m not in ALL_MARKETS]
    if invalid:
        print(f"ERROR：--markets 含不支援的市場：{invalid}"
              f"（合法值：{ALL_MARKETS}）。拒絕執行。")
        sys.exit(1)
    return requested


def _load_db_config() -> dict:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError("缺少必要資料庫環境變數：" + ", ".join(missing))
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def _check_backup_or_exit(backup_path: str) -> None:
    p = Path(backup_path)
    if not p.exists():
        print(f"ERROR：--backup 指向的檔案不存在：{backup_path}")
        sys.exit(1)
    size = p.stat().st_size
    if size == 0:
        print(f"ERROR：--backup 指向的檔案為空（0 bytes）：{backup_path}")
        sys.exit(1)
    age_seconds = time.time() - p.stat().st_mtime
    if age_seconds > _MAX_BACKUP_AGE_SECONDS:
        print(
            f"ERROR：--backup 檔案 mtime 為 {age_seconds / 3600:.1f} 小時前，"
            f"超過 {_MAX_BACKUP_AGE_SECONDS / 3600:.0f} 小時上限，拒絕執行：{backup_path}"
        )
        sys.exit(1)
    print(f"備份檔檢查通過：{backup_path}（{size:,} bytes，{age_seconds / 60:.1f} 分鐘前）")


def preview_gap(conn, target_dates=GAP_TRADE_DATES) -> None:
    """唯讀預覽：逐日印出候選池現有列數，確認清單裡的日期現在確實是缺口
    （防止 runbook 撰寫與實際執行之間若有其他人已經補過、本腳本重複補）。
    """
    import datetime as dt
    with conn.cursor() as cur:
        for d in target_dates:
            cur.execute(
                "SELECT count(*) FROM candidate_prices WHERE trade_date = %s;",
                (dt.date.fromisoformat(d),))
            n = cur.fetchone()[0]
            status = "缺口（待補）" if n == 0 else f"已有 {n} 列（不需補，將跳過）"
            print(f"  {d}: {status}")


def run_gap_backfill(manager, run_log_writer, gap_dates=GAP_TRADE_DATES,
                      markets=ALL_MARKETS):
    """逐日呼叫 `manager.run_price_batch()`。**DEC-032**：遇到
    `ServiceRefusedError` 立即停止、不繼續後續日期、不吞掉例外。

    `markets` 參數（2026-09-11 追加）：支援只重跑單一市場——08-25／08-26
    的 TWSE 端已成功，只有 TPEX 端 `FETCH_FAILED`（SSL 憑證錯誤），
    重試不該再打一次已經成功的 TWSE 端。

    抽成獨立函式（不直接寫在 `main()` 裡）是為了讓測試能注入 mock
    `manager`，不必每次測試都真的觸網或連真實庫。

    Returns:
        `(completed, refused_at)`——`completed` 為
        `[(date_str, counts), ...]`，`refused_at` 為觸發拒絕的日期字串，
        或全數完成時為 `None`。
    """
    import datetime as dt
    from src.extractors.market_report_fetcher import ServiceRefusedError

    completed, refused_at = [], None
    for d_str in gap_dates:
        d = dt.date.fromisoformat(d_str)
        print(f"\n========== 回補 {d_str}（市場：{markets}）==========")
        try:
            counts = manager.run_price_batch(
                d, markets=markets, throttle=True,
                run_log_writer=run_log_writer)
            print(f"  {d_str} 完成：{counts}")
            completed.append((d_str, counts))
        except ServiceRefusedError as exc:
            print(f"  {d_str} 被服務拒絕（{exc}）——立即停止，不繼續後續日期。")
            refused_at = d_str
            break
    return completed, refused_at


def verify_gap_filled(conn, gap_dates) -> bool:
    """寫入後核對（PO 2026-09-11 要求）：逐日印出 TWSE／TPEX 各自列數。

    硬性規則：**每天兩市場都必須 > 0 列**，且**每日合計落在
    `EXPECTED_ROWS_PER_DAY_APPROX` ± 5% 內**，否則印 `FAIL`。

    ⚠ **不 rollback**——批次路徑（`run_price_batch` → 逐市場
    `upsert_to_candidate_prices`）本來就是逐市場各自 `commit`，資料已經
    寫進去了；這裡的職責是誠實回報「寫了什麼、對不對」，不是假裝可以
    撤銷已經 commit 的資料（如實揭露，不偽裝）。

    只驗證**實際執行過**的日期（`gap_dates` 傳入 `completed` 的日期子集，
    若因 DEC-032 提早停止，未執行的日期不該被誤判為「驗證失敗」）。

    Returns: `True` 代表傳入的全部日期皆通過。
    """
    import datetime as dt
    lower = EXPECTED_ROWS_PER_DAY_APPROX * 0.95
    upper = EXPECTED_ROWS_PER_DAY_APPROX * 1.05
    all_ok = True
    with conn.cursor() as cur:
        for d_str in gap_dates:
            d = dt.date.fromisoformat(d_str)
            cur.execute(
                "SELECT source, count(*) FROM candidate_prices "
                "WHERE trade_date = %s GROUP BY source;", (d,))
            by_source = dict(cur.fetchall())
            twse_n = by_source.get("twse_mi_index", 0)
            tpex_n = by_source.get("tpex_daily_quotes", 0)
            total = twse_n + tpex_n
            ok = twse_n > 0 and tpex_n > 0 and lower <= total <= upper
            status = "PASS" if ok else "FAIL"
            print(f"  {d_str}: twse={twse_n}, tpex={tpex_n}, "
                  f"total={total}（預期 {lower:.0f}~{upper:.0f}）[{status}]")
            if not ok:
                all_ok = False

        cur.execute(
            "SELECT count(*) FROM etl_run_log WHERE batch_key = ANY(%s) "
            "AND source IN ('twse_mi_index', 'tpex_daily_quotes');",
            (gap_dates,))
        n_log = cur.fetchone()[0]
    print(f"\netl_run_log 新增（實際查得）：{n_log} 筆歷史 batch_key "
          f"（預期 {len(gap_dates) * 2} = {len(gap_dates)} 天 × 2 市場）")
    return all_ok


def main(write: bool, backup_path: str, dates_arg=None, markets_arg=None) -> None:
    target_dates = _validate_dates_subset(dates_arg)
    markets = _validate_markets_subset(markets_arg)

    if write and not backup_path:
        print("ERROR：--write 必須同時提供 --backup <path>（RISK-013 第二項協議機械化檢查）")
        sys.exit(1)
    if write:
        _check_backup_or_exit(backup_path)

    db_config = _load_db_config()
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user, inet_server_port();")
    conn_info = cur.fetchone()
    current_db = conn_info[0]
    print("CONN CHECK:", conn_info)

    print(f"\n候選池缺口清單（{len(target_dates)} 天，市場 {markets}，唯讀預覽）：")
    preview_gap(conn, target_dates)

    if not write:
        print("\n【唯讀模式】僅唯讀連線，不呼叫 run_price_batch、不觸網、"
              "不執行任何寫入。加 --write --backup <path> 執行實際回補。")
        conn.close()
        return

    typed = input(f"即將對資料庫 '{current_db}' 執行 {len(target_dates)} 天、"
                  f"{markets} 市場的批次取價（觸網＋寫入）。請輸入資料庫名稱以確認：")
    if typed != current_db:
        print(f"ERROR：輸入 '{typed}' 與目標資料庫 '{current_db}' 不符，拒絕執行。")
        conn.close()
        sys.exit(1)

    conn.close()  # ETLPipelineManager 自行管理連線，不共用本檔的唯讀連線

    from main_etl_pipeline import ETLPipelineManager

    manager = ETLPipelineManager()
    run_log_writer = manager._run_log_writer()

    completed, refused_at = run_gap_backfill(
        manager, run_log_writer, gap_dates=target_dates, markets=markets)

    print("\n=== 回補結果摘要 ===")
    completed_dates = [d for d, _ in completed]
    print(f"完成：{completed_dates}")
    if refused_at:
        remaining = target_dates[target_dates.index(refused_at):]
        print(f"因服務拒絕中止於：{refused_at}；未執行：{remaining}")

    if completed_dates:
        print(f"\n=== 寫入後核對（{len(completed_dates)} 天已執行）===")
        verify_conn = psycopg2.connect(**db_config)
        try:
            all_ok = verify_gap_filled(verify_conn, completed_dates)
        finally:
            verify_conn.close()
        if not all_ok:
            print("\nFAIL：至少一天核對不通過——資料已寫入（批次路徑逐市場各自 "
                  "commit，無法回滾），但如實回報不通過，須人工排查。")
            sys.exit(1)
        print("\n已執行的日期全數核對通過。")

    if refused_at:
        sys.exit(1)
    else:
        print(f"\n{len(target_dates)} 天全數完成，無服務拒絕中止。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", default=None)
    parser.add_argument(
        "--dates", default=None,
        help="逗號分隔日期子集（須為 GAP_TRADE_DATES 的子集，否則拒絕執行）。"
             "不提供時為全部 8 天。用於單日／少數日期重試（如 SSL 憑證"
             "暫時性錯誤重跑）。")
    parser.add_argument(
        "--markets", default=None,
        help="逗號分隔市場子集（twse／tpex）。不提供時為兩者皆執行。"
             "用於只重試單一市場（如某天 TWSE 已成功、只有 TPEX 失敗）。")
    args = parser.parse_args()
    main(write=args.write, backup_path=args.backup,
         dates_arg=args.dates, markets_arg=args.markets)
