# tests/test_first_daily_etl_cause_f_wiring.py
"""
§0.5 #32 成因 F 接線（PTT 失敗＋NLP 未完成 → SOURCE_FAILED）——Gate A v2 紅測。

見 `doc/upgrade/gates/FIRST_DAILY_ETL_CAUSE_F_WIRING_GATE_A_PROPOSAL.md`。

本檔測試的是**尚未實作**的行為，撰寫時全部預期 FAIL（`CLAUDE.md` §9A.2）：
- `DBWriter.fetch_failed_source_keys()`（新方法，`src/loaders/db_writer.py`）——覆蓋算術
  與 NLP cutoff 歸日全部在 Python 做（提案 §3.3），SQL 只負責撈原始列。五條查詢預計
  分別觸及 `etl_run_log`（`WHERE source='ptt'`）／`entity_mapping`／`theme_stock_mapping`／
  `stock_prices`／`market_articles`（`WHERE sentiment_score IS NULL`）五張表，**呼叫順序
  不固定**——測試用 `cursor.execute` 記錄 SQL 文字，`fetchall` 依 SQL 裡出現的表名分派
  對應的 fixture 列，換順序實作不會誤判 FAIL（PO 複核要求，見下方 `_mock_cursor`）。
- `main_etl_pipeline.py`：`run_feature_engineering_pipeline()` 呼叫
  `db_writer.fetch_failed_source_keys()` 並傳入 `generate_daily_features(
  failed_source_keys=...)`；呼叫時機在 NLP 階段之後。

全部合成資料，不連真實庫、不觸發任何網路請求。
"""
import datetime as _dt
import unittest
from unittest.mock import MagicMock, patch

import psycopg2


# ============================================================
# 2-4, 6, 8a, 8b, 9, 10：DBWriter.fetch_failed_source_keys() 單元測試
# ============================================================
class FetchFailedSourceKeysMethodTests(unittest.TestCase):
    """對應提案 §4 測項 2、3、4、5、6、8a、8b、9、10：`fetch_failed_source_keys()`
    本身的覆蓋算術、起算點、題材路徑、NLP 未完成、錯誤傳播、空表防護、型別一致性。

    `_mock_cursor()`（PO 複核訂正版）：不依賴查詢順序。`cursor.execute` 記錄最近一次
    SQL 文字，`fetchall` 依該 SQL 裡出現的表名分派 fixture；`etl_run_log` 那張表額外
    斷言 SQL 含 `source='ptt'` 的過濾（字串含 `'ptt'`），確保實作真的把來源縮小到 PTT，
    不會不小心把 `tracked_stocks_daily`／`twse_mi_index` 等其他 `etl_run_log` 來源的列
    也撈進來。
    """

    TABLE_MARKERS = (
        "etl_run_log", "entity_mapping", "theme_stock_mapping",
        "stock_prices", "market_articles",
    )

    def _mock_cursor(self, table_rows):
        """table_rows: {table_marker: [rows...]}——缺的表視為空列表。"""
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        state = {"sql": ""}

        def _execute(sql, *args, **kwargs):
            state["sql"] = sql

        def _fetchall():
            sql = state["sql"]
            matched = [m for m in self.TABLE_MARKERS if m in sql]
            self.assertEqual(
                len(matched), 1,
                "SQL 必須恰好命中五張表名之一，本次匹配到 %r，SQL=%r" % (matched, sql))
            table = matched[0]
            if table == "etl_run_log":
                self.assertIn(
                    "ptt", sql,
                    "查 etl_run_log 的 SQL 必須過濾 source='ptt'，"
                    "否則會撈進 tracked_stocks_daily／twse_mi_index 等其他來源的列")
            return table_rows.get(table, [])

        cursor.execute.side_effect = _execute
        cursor.fetchall.side_effect = _fetchall
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        return conn

    def _writer(self):
        from src.loaders.db_writer import DBWriter
        return DBWriter(db_config={"database": "d", "user": "u", "password": "<test>"})

    def _call(self, ptt_rows=(), entity_rows=(), theme_rows=(), price_rows=(),
              nlp_rows=()):
        conn = self._mock_cursor({
            "etl_run_log": list(ptt_rows),
            "entity_mapping": list(entity_rows),
            "theme_stock_mapping": list(theme_rows),
            "stock_prices": list(price_rows),
            "market_articles": list(nlp_rows),
        })
        writer = self._writer()
        with patch("src.loaders.db_writer.psycopg2.connect", return_value=conn):
            return writer.fetch_failed_source_keys()

    def test_cross_day_persistence_and_window_boundary(self):
        """§4 測項 2：跨日存續＋覆蓋視窗 `[B-2, B]` 邊界，一個函式五個子案例。

        stock '1101' 只映射關鍵字 'K'。origin 批次 `batch_key='2026-09-01'`
        （`FETCH_FAILED`，本身不覆蓋任何日期，只用來建立起算點）。D='2026-09-05'。

        **known-FAIL (i)**：實作若只看「最新一筆」批次而非掃描全部歷史列，子案例
        (d) 會 FAIL（覆蓋它的批次 batch_key=09-06 不是清單裡最後一筆）。
        **known-FAIL (ii)**：覆蓋視窗寫成 `[B, B]`（子案例 b 會 FAIL，09-07 這筆
        單獨不覆蓋 09-05）、`[B-3, B]`（子案例 c 會 FAIL，09-08 這筆不該覆蓋到
        09-05，寫太寬會誤判為覆蓋）、或 `[B-2, B+1]`（子案例 e 會 FAIL，09-04 這筆
        不該把 D 也一起涵蓋進去）。
        """
        entity_rows = [("K", "1101")]
        price_rows = [("1101", _dt.date(2026, 9, 1)), ("1101", _dt.date(2026, 9, 5))]
        origin_row = ("K", "2026-09-01", "FETCH_FAILED")
        D = ("1101", "2026-09-05")

        # (a) 沒有任何批次覆蓋 D → D 失敗
        result = self._call(ptt_rows=[origin_row], entity_rows=entity_rows,
                             price_rows=price_rows)
        self.assertIn(D, result, "(a) 無覆蓋時 D 應判定為未覆蓋")

        # (b) batch_key=D+2=09-07 的 OK 批次涵蓋 [09-05, 09-07] → D 被覆蓋
        result = self._call(
            ptt_rows=[origin_row, ("K", "2026-09-07", "OK")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertNotIn(D, result, "(b) batch_key=D+2 的 OK 批次應覆蓋 D（視窗下界）")

        # (c) batch_key=D+3=09-08 的 OK 批次涵蓋 [09-06, 09-08]，不含 D → D 仍未覆蓋
        result = self._call(
            ptt_rows=[origin_row, ("K", "2026-09-08", "OK")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertIn(D, result, "(c) batch_key=D+3 不該覆蓋 D（視窗上界之外）")

        # (d) 覆蓋 D 的批次（09-06）不是清單裡「最新」的一筆（09-20 更晚但不覆蓋 D）
        #     ——用來殺「只看最新一筆」而非掃描全部歷史列的突變（known-FAIL i）
        result = self._call(
            ptt_rows=[origin_row, ("K", "2026-09-06", "OK"),
                      ("K", "2026-09-20", "NO_DATA")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertNotIn(
            D, result,
            "(d) 09-06 那筆（非清單最後一筆）覆蓋 D=[09-04,09-06]，"
            "必須掃描全部歷史列，不能只看最新一筆（09-20 那筆不覆蓋 D）",
        )

        # (e)【PO 複核追加】batch_key=D-1=09-04 的 OK 批次涵蓋 [09-02, 09-04]，
        #    不含 D（09-05）——用來殺視窗寫成 [B-2, B+1]（多算一天到未來）的突變
        result = self._call(
            ptt_rows=[origin_row, ("K", "2026-09-04", "OK")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertIn(
            D, result,
            "(e) batch_key=D-1 的批次涵蓋 [D-3,D-1]，不得覆蓋 D"
            "（殺視窗誤寫成 [B-2, B+1] 往未來多算一天的突變）",
        )

    def test_origin_point_not_retroactive(self):
        """§4 測項 3：起算點之前的交易日不套用缺口定義，起算點用 `MIN(batch_key)
        WHERE source='ptt'`（PO 裁定，不是 `started_at`）。

        origin batch_key='2026-09-05'（FETCH_FAILED，本身不覆蓋，只建立起算點）。
        stock '1101' 映射關鍵字 'K'。09-03（起算點之前）即使無覆蓋也不得出現；
        09-05（起算點當天，含）無覆蓋則出現。

        **known-FAIL**：拿掉起算點過濾（對全部歷史套用缺口定義）→ 09-03 也被誤標，
        斷言 FAIL。
        """
        entity_rows = [("K", "1101")]
        price_rows = [("1101", _dt.date(2026, 9, 3)), ("1101", _dt.date(2026, 9, 5))]
        result = self._call(
            ptt_rows=[("K", "2026-09-05", "FETCH_FAILED")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertNotIn(
            ("1101", "2026-09-03"), result,
            "起算點（09-05）之前的交易日不得出現在失敗鍵集合裡")
        self.assertIn(
            ("1101", "2026-09-05"), result,
            "起算點當天（含）若無覆蓋，仍應判定為未覆蓋")

    def test_never_ran_counts_as_uncovered_and_stock_id_type_normalized(self):
        """§4 測項 4：某交易日完全沒有任何 `source='ptt'` 的 `etl_run_log` 列
        （不是失敗，是沒跑）→ 該日映射到的股票仍標 `SOURCE_FAILED`。

        origin batch_key='2026-09-01'（OK，覆蓋到 09-01 為止）。D='2026-09-10'
        附近完全沒有任何 PTT run log 列（不是 FETCH_FAILED，是壓根不存在）。

        **known-FAIL**：實作若只在「存在對應 log 列」時才觸發缺口判斷（例如以
        `etl_run_log` 的列去驅動迴圈，而非以 `stock_prices` 的完整交易日集合去驅動），
        D 會被跳過，斷言 FAIL。

        **【PO 複核追加】型別混合**：`stock_prices` 回傳的 `stock_id` 是整數 `1101`
        （真實庫兩邊都是文字型別，但 pandas／psycopg2 轉型路徑多，這裡故意混一個整數
        釘住一次），`entity_mapping` 回傳字串 `'1101'`——結果鍵仍須是字串
        `('1101', ...)`，兩張表的 `stock_id` 要能對得上、且聚合器慣用的字串鍵格式
        不能因為來源型別不同而漏配。
        """
        entity_rows = [("K", "1101")]
        price_rows = [(1101, _dt.date(2026, 9, 1)), (1101, _dt.date(2026, 9, 10))]
        result = self._call(
            ptt_rows=[("K", "2026-09-01", "OK")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertIn(
            ("1101", "2026-09-10"), result,
            "完全沒有任何 PTT run log 列覆蓋到的交易日，必須視為未覆蓋（沒跑＝未覆蓋）；"
            "鍵須為字串 '1101'，證明整數 stock_id 與字串映射表對得上")

    def test_nlp_incomplete_marks_failed_and_self_heals(self):
        """§4 測項 5：NLP 未完成——一篇未評分文章對到股票 s、依 cutoff 歸日到 D，
        (s, D) 標 `SOURCE_FAILED`；補上分數後重算（模擬：不再有該篇未評分文章）回到
        未命中。一個函式三個子案例（PO 複核追加滾動歸日、題材路徑，測試數維持 11
        不新增函式）。

        stock '2330' 經 entity_mapping 關鍵字'台積電'。PTT 路徑本身在 09-10／09-11
        皆有完整覆蓋（batch_key=09-11 一筆 OK，涵蓋 [09-09,09-11]），排除 PTT 路徑
        對這兩個鍵的干擾，確保命中的原因只能是 NLP 未完成路徑。

        **known-FAIL（基本行為）**：`fetch_failed_source_keys()` 只做 PTT (a) 不做
        NLP (b)（不查 `market_articles`）→ 子案例 1 補分前的斷言 FAIL（鍵不會出現）。
        **known-FAIL（滾動歸日）**：實作若直接用 `post_time.date()` 當 D、忽略
        cutoff（不是呼叫既有的 `map_timestamp_to_trading_day()`，提案 §3.3b 複用該
        函式的全部理由就是這個）→ 子案例 2 兩條斷言皆 FAIL（鍵算成 09-10 而非
        09-11）。
        **known-FAIL（題材路徑）**：NLP 路徑合併映射時漏掉 `theme_stock_mapping`、
        只查 `entity_mapping`（提案 §3.3b 明寫 NLP 路徑判斷依據是「文章確實存在」，
        與 PTT 有沒有抓過這個關鍵字無關，不套用 §3.2a 資格過濾）→ 子案例 3 '8888'
        沒有任何映射可用，鍵不會出現，斷言 FAIL。
        **known-FAIL（審查方複核追加，超出交易日曆防護）**：`map_timestamp_to_
        trading_day()` 對超出該股交易日曆的文章時間回傳 `None`（15:35 執行時，
        當天發文對應的交易日還沒有股價列——批次抓的是 T-1，這是 NLP 未完成路徑
        每天都會走到的正常情形，不是邊角案例）。實作必須用 `if mapped_date is not
        None:` 防護後才寫入鍵。子案例 4：股票只有一個交易日（09-10）在日曆裡，
        文章卻晚一天發文（09-11，未過 cutoff）→ `map_timestamp_to_trading_day()`
        回 `None`，本函式不得拋例外、也不得寫入任何鍵。拿掉這個防護（改成
        `if True:`）→ `AttributeError`（對 `None` 呼叫 `.isoformat()`）。
        """
        entity_rows = [("台積電", "2330")]
        price_rows = [("2330", _dt.date(2026, 9, 10)), ("2330", _dt.date(2026, 9, 11))]
        ptt_rows = [("台積電", "2026-09-01", "OK"), ("台積電", "2026-09-11", "OK")]

        # --- 子案例 1：基本行為＋自我修復 ---
        key = ("2330", "2026-09-10")
        # 補分前：有一篇未評分文章，15:30 cutoff 前發文、同日歸日
        nlp_rows = [(1, "台積電", _dt.datetime(2026, 9, 10, 10, 0, 0))]
        result = self._call(ptt_rows=ptt_rows, entity_rows=entity_rows,
                             price_rows=price_rows, nlp_rows=nlp_rows)
        self.assertIn(key, result, "未評分文章對到的 (股票, 歸日日期) 應標記為失敗")
        # 補分後：該篇已評分，market_articles 查詢不會再撈到它（模擬全歷史重算）
        result = self._call(ptt_rows=ptt_rows, entity_rows=entity_rows,
                             price_rows=price_rows)
        self.assertNotIn(key, result, "文章評分完成後，重算應自然不再命中（自我修復）")

        # --- 子案例 2【PO 複核追加】：滾動歸日，post_time 過 cutoff (15:30) ---
        nlp_rows_late = [(2, "台積電", _dt.datetime(2026, 9, 10, 16, 0, 0))]
        result = self._call(ptt_rows=ptt_rows, entity_rows=entity_rows,
                             price_rows=price_rows, nlp_rows=nlp_rows_late)
        self.assertIn(
            ("2330", "2026-09-11"), result,
            "過 cutoff 的發文須滾動到下一個交易日（09-11），不是原始發文日")
        self.assertNotIn(
            ("2330", "2026-09-10"), result,
            "原始發文日（09-10）本身不應被標記——歸日後的交易日是 09-11")

        # --- 子案例 3【PO 複核追加】：只經 theme_stock_mapping 對到，
        #     且該關鍵字從未出現在 PTT run log（證明 NLP 路徑不受 §3.2a 資格過濾）---
        theme_rows = [("K3", "8888")]
        price_rows_theme = [("8888", _dt.date(2026, 9, 10))]
        ptt_rows_no_k3 = [("其他關鍵字", "2026-09-01", "OK")]
        nlp_rows_theme = [(3, "K3", _dt.datetime(2026, 9, 10, 10, 0, 0))]
        result = self._call(ptt_rows=ptt_rows_no_k3, theme_rows=theme_rows,
                             price_rows=price_rows_theme, nlp_rows=nlp_rows_theme)
        self.assertIn(
            ("8888", "2026-09-10"), result,
            "只經 theme_stock_mapping 對到、且關鍵字從未被 PTT 抓過的股票，"
            "NLP 未完成路徑仍應命中（不套用 §3.2a 資格過濾）")

        # --- 子案例 4【審查方複核追加】：文章時間超出該股交易日曆 ---
        entity_rows_d = [("K4", "9090")]
        price_rows_d = [("9090", _dt.date(2026, 9, 10))]  # 日曆只有這一天
        nlp_rows_d = [(4, "K4", _dt.datetime(2026, 9, 11, 10, 0, 0))]  # 隔天發文
        try:
            result = self._call(entity_rows=entity_rows_d, price_rows=price_rows_d,
                                 nlp_rows=nlp_rows_d)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                "文章時間超出該股交易日曆時不得拋例外（map_timestamp_to_trading_day() "
                "回 None 是正常情形，見 §3.3b），實際拋出：%r" % (exc,))
        self.assertFalse(
            any(sid == "9090" for sid, _ in result),
            "超出交易日曆的未評分文章本次不得產生任何鍵；"
            "待該日股價列存在後，若仍未評分，下次重算自然納入")

    def test_theme_only_keyword_path(self):
        """§4 測項 6：股票只經 `theme_stock_mapping`（非 `entity_mapping`）對到未覆蓋
        的關鍵字，仍應命中（PTT 覆蓋缺口路徑，會套用 §3.2a 資格過濾——與上面 NLP
        路徑的題材測試不同，這裡的 'K2' 必須曾出現在 PTT run log 裡才有資格）。

        stock '9999' 完全沒有 `entity_mapping` 列，只經題材關鍵字 'K2' 對到。

        **known-FAIL**：合併股票-關鍵字映射時漏掉 `theme_stock_mapping`、只查
        `entity_mapping` → '9999' 連「曾被抓過關鍵字」的資格都拿不到，斷言 FAIL。
        """
        theme_rows = [("K2", "9999")]
        price_rows = [("9999", _dt.date(2026, 9, 1))]
        result = self._call(
            ptt_rows=[("K2", "2026-09-01", "FETCH_FAILED")],
            theme_rows=theme_rows, price_rows=price_rows)
        self.assertIn(
            ("9999", "2026-09-01"), result,
            "只經 theme_stock_mapping 對到的股票，其未覆蓋關鍵字仍應使其命中")

    def test_never_crawled_keyword_stays_untouched(self):
        """§4 測項 8a：股票只映射「從未出現在 PTT run log」的關鍵字 → 本案不動，
        維持現狀（不標 `SOURCE_FAILED`）。PO 裁決選 A（§3.2a）。

        stock '5555' 只映射關鍵字'神秘關鍵字'（從未出現在 ptt_rows 的 item_key 裡）。
        對照組：stock '1101' 映射'K'（有出現在 ptt_rows，且未覆蓋），必須命中——
        證明過濾是選擇性的，不是把全部股票都排除掉了。

        **known-FAIL**：拿掉「曾被抓過關鍵字」的資格過濾（對全部股票一視同仁套用
        缺口定義）→ '5555' 也被誤標，斷言 FAIL。
        """
        entity_rows = [("神秘關鍵字", "5555"), ("K", "1101")]
        price_rows = [("5555", _dt.date(2026, 9, 1)), ("1101", _dt.date(2026, 9, 1))]
        result = self._call(
            ptt_rows=[("K", "2026-09-01", "FETCH_FAILED")],
            entity_rows=entity_rows, price_rows=price_rows)
        self.assertNotIn(
            ("5555", "2026-09-01"), result,
            "映射到的關鍵字從未出現在 PTT run log，本案不動，不得標記 SOURCE_FAILED")
        self.assertIn(
            ("1101", "2026-09-01"), result,
            "對照組：關鍵字曾被抓過且未覆蓋，必須命中（證明過濾不是全面排除）")

    def test_multi_keyword_any_coverage_suffices(self):
        """§4 測項 8b：一檔股票映射多個關鍵字時，任一關鍵字有覆蓋即算覆蓋
        （PO 裁決，§3.2a）。

        stock '7777' 映射 'K1'（有覆蓋 D）與 'K2'（未覆蓋）。

        **known-FAIL**：改成「全部關鍵字都要覆蓋才算覆蓋」→ K2 未覆蓋導致整體判定
        為未覆蓋，斷言 FAIL。
        """
        entity_rows = [("K1", "7777"), ("K2", "7777")]
        price_rows = [("7777", _dt.date(2026, 9, 5))]
        ptt_rows = [
            ("K1", "2026-09-05", "OK"),          # 覆蓋 [09-03, 09-05]，含 D
            ("K2", "2026-09-01", "FETCH_FAILED"),  # 不覆蓋，且本身就是失敗
        ]
        result = self._call(ptt_rows=ptt_rows, entity_rows=entity_rows,
                             price_rows=price_rows)
        self.assertNotIn(
            ("7777", "2026-09-05"), result,
            "K1 已覆蓋 D，即使 K2 未覆蓋，該股票這天仍應算覆蓋（任一關鍵字即可）")

    def test_database_error_propagates_not_swallowed(self):
        """§4 測項 9（PO 複核追加）：查詢拋例外時必須往外傳播，不得回傳空集合
        讓特徵階段誤以為「今天沒有失敗」（`CLAUDE.md` §7.1）。

        **known-FAIL**：把查詢包在 `try/except: return set()` 裡 → 不會拋例外，
        `assertRaises` 斷言 FAIL。
        """
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.execute.side_effect = psycopg2.OperationalError("connection lost")
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        writer = self._writer()
        with patch("src.loaders.db_writer.psycopg2.connect", return_value=conn):
            with self.assertRaises(psycopg2.OperationalError):
                writer.fetch_failed_source_keys()

    def test_empty_ptt_log_returns_empty_not_crash_and_nlp_path_still_runs(self):
        """§4 測項 10（PO 複核追加）：PTT run log 完全空表時，(a) 應貢獻 0 個鍵，
        (b) 照常計算，不得因為 `min()` 對空序列拋 `ValueError` 而崩潰；且不得用
        `if not ptt_rows: return set()` 這種提早返回，讓 (b) 也跟著失效。

        **known-FAIL（崩潰）**：`origin = min(batch_key for ... in ptt_rows)` 未防
        空序列，對空 `ptt_rows` 直接呼叫會拋 `ValueError`，第一段斷言不拋例外會 FAIL。
        **known-FAIL（提早返回）【PO 複核追加】**：`ptt_rows` 為空時，一篇未評分文章
        仍應貢獻 (b) 的鍵；若實作用 `if not ptt_rows: return set()` 提早出場，
        第二段斷言（鍵存在）會 FAIL。
        """
        result = self._call()
        self.assertEqual(result, set(), "PTT run log 全空時應回傳空集合，不得拋例外")

        entity_rows = [("台積電", "2330")]
        price_rows = [("2330", _dt.date(2026, 9, 10))]
        nlp_rows = [(4, "台積電", _dt.datetime(2026, 9, 10, 10, 0, 0))]
        result = self._call(entity_rows=entity_rows, price_rows=price_rows,
                             nlp_rows=nlp_rows)
        self.assertIn(
            ("2330", "2026-09-10"), result,
            "PTT run log 為空不得讓 (b) NLP 未完成路徑跟著提早返回失效")


# ============================================================
# 1, 7：main_etl_pipeline.py 接線與呼叫時機
# ============================================================
class CauseFWiringIntegrationTests(unittest.TestCase):
    """對應提案 §4 測項 1、7：接線本身（值有沒有真的傳進去）與呼叫時機
    （必須排在 NLP 階段之後）。
    """

    def _manager(self, mep):
        patches = (
            patch.object(mep, "DBWriter", MagicMock()),
            patch.object(mep, "TrendDiscover", MagicMock()),
            patch.object(mep, "NLPProcessor", MagicMock()),
            patch.object(mep, "FeatureAggregator", MagicMock()),
        )
        for p in patches:
            p.start()
        try:
            return mep.ETLPipelineManager()
        finally:
            for p in patches:
                p.stop()

    def test_failed_source_keys_wired_into_generate_daily_features(self):
        """§4 測項 1：`run_feature_engineering_pipeline()` 必須呼叫
        `db_writer.fetch_failed_source_keys()`，並把回傳值原樣傳進
        `generate_daily_features(failed_source_keys=...)`。

        **known-FAIL**：現行程式碼從未呼叫 `fetch_failed_source_keys()`，
        也從未傳 `failed_source_keys` 這個關鍵字引數 → 斷言 FAIL。
        """
        import main_etl_pipeline as mep

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        expected_keys = {("2330", "2026-09-10")}
        manager.db_writer.fetch_failed_source_keys.return_value = expected_keys
        manager.db_writer.fetch_all_for_features.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        manager.feature_aggregator = MagicMock()

        manager.run_feature_engineering_pipeline()

        manager.db_writer.fetch_failed_source_keys.assert_called_once()
        call = manager.feature_aggregator.generate_daily_features.call_args
        self.assertEqual(
            call.kwargs.get("failed_source_keys"), expected_keys,
            "generate_daily_features() 必須原樣收到 fetch_failed_source_keys() 的回傳值")

    def test_fetch_failed_source_keys_called_after_nlp_stage(self):
        """§4 測項 7：`fetch_failed_source_keys()` 必須排在 NLP 階段
        （`run_nlp_sentiment_pipeline`）之後——否則本次剛評完分的文章仍會被算成
        未完成（比照 §0.5 #30 `test_feature_lag_measured_after_per_stock_stage`
        的 `attach_mock` 手法）。

        **known-FAIL**：現行程式碼從未呼叫 `fetch_failed_source_keys()`，
        `mock_calls` 裡找不到它，斷言 FAIL（`assertIn` 本身就會失敗，不需要額外突變）。
        """
        import main_etl_pipeline as mep
        from src.loaders.etl_run_log import OK

        manager = self._manager(mep)
        manager.db_writer = MagicMock()
        manager.db_writer.fetch_active_stock_targets.return_value = [
            {"stock_id": "2330", "market": "TWSE"}]
        manager.db_writer.fetch_active_keywords.return_value = ["AI"]
        manager.db_writer.fetch_candidate_prices_max_date_by_market.return_value = {
            "twse": _dt.date(2026, 9, 16), "tpex": _dt.date(2026, 9, 16),
        }
        manager.db_writer.fetch_feature_lag.return_value = {
            "feature_max_date": _dt.date(2026, 9, 4),
            "price_max_date": _dt.date(2026, 9, 16),
            "n_lag": 8,
        }
        manager.db_writer.fetch_failed_source_keys.return_value = set()
        manager.db_writer.fetch_all_for_features.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        manager.trend_discover = MagicMock()
        # §0.5 #31：同機制的必然連帶影響（見 test_daily_hook_wiring.py 同型註解），
        # 僅補 mock，不改動任何既有斷言。
        manager.db_writer.fetch_last_discovery_probed_date.return_value = None
        manager.trend_discover.run_discovery.return_value = ("OK", None)
        manager.run_ptt_board_pipeline = MagicMock(return_value={"AI": (OK, None)})
        manager.run_us_stock_pipeline = MagicMock()
        manager.run_twse_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_tpex_pipeline_from_candidate_prices = MagicMock(return_value=OK)
        manager.run_triple_barrier_tail_recompute = MagicMock()
        manager.run_price_batch = MagicMock()
        manager.feature_aggregator = MagicMock()
        # attach_mock() 要求目標本身已是 Mock——真正的 bound method 不行，
        # 先替換成 MagicMock 再掛上 parent（比照上一案 M3 測試的做法）。
        manager.run_nlp_sentiment_pipeline = MagicMock()

        parent = MagicMock()
        parent.attach_mock(manager.run_nlp_sentiment_pipeline, "nlp")
        parent.attach_mock(manager.db_writer.fetch_failed_source_keys, "fetch_failed")
        parent.attach_mock(manager.feature_aggregator.generate_daily_features, "gen_features")

        with patch.object(mep, "previous_business_day",
                           return_value=_dt.date(2026, 9, 16)), \
             patch.object(mep.ETLPipelineManager, "_run_log_writer",
                           lambda self: MagicMock()):
            manager.run_all_daily_tasks()

        names = [c[0] for c in parent.mock_calls]
        for required in ("nlp", "fetch_failed", "gen_features"):
            self.assertIn(required, names, "%s 未被呼叫，無法比較呼叫順序" % required)

        idx_nlp = names.index("nlp")
        idx_fetch_failed = names.index("fetch_failed")
        idx_gen_features = names.index("gen_features")
        self.assertLess(
            idx_nlp, idx_fetch_failed,
            "fetch_failed_source_keys() 必須排在 NLP 階段之後")
        self.assertLess(
            idx_fetch_failed, idx_gen_features,
            "fetch_failed_source_keys() 必須排在 generate_daily_features() 之前")


if __name__ == "__main__":
    unittest.main()
