#!/usr/bin/env python3
"""
Gate 0 跨文件契約驗證 (Part B) — 契約反查法 (contract-driven)

方法論：從「契約要求」出發列舉所有應受約束的對象，逐一反查文件是否滿足。
        不從已知答案出發湊 grep —— 那種寫法結構上無法發現未知的同型缺陷。

用法：  python scripts/verify/gate0_contract_check.py
輸出：  每項檢查的 PASS/FAIL 與依據；結尾為總計。exit code 0 = 全通過。
"""
import re, sys, io, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DOC_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "doc")

# GOV-05：文件依歸屬與生命週期分資料夾後，本腳本受驗的 7 份文件不再同處一層，
#         因此由單一 DOC_DIR 改為逐檔路徑對映。鍵仍為裸檔名，下游 D[...] 用法不變。
DOC_PATHS = {
    "SYSTEM_UPGRADE_MASTER_PLAN.md": os.path.join(DOC_ROOT, "upgrade"),
    "FEATURE_REGISTRY.md":           os.path.join(DOC_ROOT, "upgrade", "contracts"),
    "PURGED_WALK_FORWARD_SPEC.md":   os.path.join(DOC_ROOT, "upgrade", "contracts"),
    "MULTI_SOURCE_DATA_CONTRACT.md": os.path.join(DOC_ROOT, "upgrade", "contracts"),
    "DB_MIGRATION_PLAN.md":          os.path.join(DOC_ROOT, "upgrade", "contracts"),
    "DECISIONS.md":                  os.path.join(DOC_ROOT, "evidence"),
    "TRACEABILITY.md":               os.path.join(DOC_ROOT, "evidence"),
}
FILES = list(DOC_PATHS)


def strip_meta_sections(text, fname):
    """
    移除「meta 章節」—— 這些章節本來就會引用舊字串或範例來說明問題，
    不應計入活規格掃描。若不移除，驗證表自己會污染驗證結果
    （這正是 V7 Part A 數字不可重現的原因，Part B 同樣適用）。

    Master Plan: §0.1 版本修正對照 / §16 舊版問題對照 / §18 驗證證據
    """
    if fname != "SYSTEM_UPGRADE_MASTER_PLAN.md":
        return text
    out, skip = [], False
    for line in text.split("\n"):
        if re.match(r"^### 0\.1 ", line) or re.match(r"^## 16\. ", line) or re.match(r"^## 18\. ", line):
            skip = True
        elif re.match(r"^## 1\. ", line) or re.match(r"^## 17\. ", line) or re.match(r"^## 19\. ", line):
            skip = False
        if not skip:
            out.append(line)
    return "\n".join(out)


D = {f: strip_meta_sections(open(os.path.join(DOC_PATHS[f], f), encoding="utf-8").read(), f)
     for f in FILES}

results = []
def check(cid, name, ok, detail):
    results.append((cid, ok))
    print(f"{cid:4} {'PASS' if ok else 'FAIL'} | {name}\n       {detail}")

mig = D["DB_MIGRATION_PLAN.md"]
dml_cols = set(re.findall(r"ALTER TABLE daily_ml_features ADD COLUMN IF NOT EXISTS (\w+)", mig))
art_cols = set(re.findall(r"ALTER TABLE market_articles ADD COLUMN IF NOT EXISTS (\w+)", mig))
EXISTING_7 = {"trade_date", "stock_id", "close_price", "volume",
              "article_count", "sentiment_mean", "sentiment_3d_ma"}
contract = dml_cols | EXISTING_7

# B1 — 契約完整性
check("B1", "29 欄契約完整性", len(contract) == 29,
      f"migration 新增 {len(dml_cols)} + 既有 7 = {len(contract)}")

# B2 — 反查：被引用欄位是否都存在（此檢查會抓到 BLOCK-3 類型的缺陷）
referenced = {}
for fname, text in D.items():
    for pat in [r"df\[['\"](\w+)['\"]\]", r"df\.loc\[[^,\]]+,\s*['\"](\w+)['\"]\]",
                r"df_features\[['\"](\w+)['\"]\]", r"df_features\.loc\[[^,\]]+,\s*['\"](\w+)['\"]\]"]:
        for m in re.findall(pat, text):
            referenced.setdefault(m, set()).add(fname)
missing = {k for k in referenced if k not in contract | art_cols}
check("B2", "被引用欄位皆存在於契約（反查法）", not missing,
      f"{len(referenced)} 個被引用，缺失 {len(missing)}" + (f": {sorted(missing)}" if missing else ""))

# B3 — 反查：所有社群來源欄位是否都有 SOURCE_FAILED→NULL 規則（會抓到 BLOCK-2）
sect = D["FEATURE_REGISTRY.md"].split("### 5A.3")[1].split("\n###")[0]
rows = re.findall(
    r"^\| \*?\*?`?([\w /`]+?)`?\*?\*? *\| *\*?\*?(價量|社群|社群留言)\*?\*? *\|([^|]*)\|([^|]*)\|",
    sect, re.M)
social = [r for r in rows if r[1] in ("社群", "社群留言")]
bad = [r for r in social if "NULL" not in r[3]]
check("B3", "社群欄位皆有 SOURCE_FAILED→NULL 規則（反查法）", not bad,
      f"{len(social)} 社群列全部標明 NULL" + (f"；缺失: {[b[0] for b in bad]}" if bad else ""))

# B4 — 反查：raw 層留言計數欄不得有 DEFAULT（會抓到 BLOCK-1）
#
# 為何跨全部文件掃描、且不要求 "ALTER TABLE market_articles ADD COLUMN" 同一行：
# 舊版只掃 DB_MIGRATION_PLAN.md、且正則要求整句在同一行，MULTI_SOURCE_DATA_CONTRACT.md §2.2
# 的多行 ALTER TABLE 寫法（"ALTER TABLE market_articles" 與 "ADD COLUMN IF NOT EXISTS ..."
# 分行）結構上不可能被舊版抓到——即使該份文件當時確實寫著 DEFAULT 0。
# 這正是 CLAUDE.md §9A.1 警告的「只看已知沒問題的地方」（UG-G2-SB3，PO 2026-08-27 實測發現）。
COMMENT_COUNT_COLS = {"push_count", "boo_count", "neutral_count", "total_comments"}
col_types, viol = {}, []
for fname, text in D.items():
    for m in re.finditer(r"ADD COLUMN IF NOT EXISTS\s+(\w+)\s+([^,;\n]+)", text):
        col, decl = m.group(1), m.group(2).strip()
        if col not in COMMENT_COUNT_COLS:
            continue
        col_types.setdefault(col, set()).add(decl)
        if "DEFAULT" in decl.upper():
            viol.append(f"{fname}:{col}={decl}")
check("B4", "raw 層留言計數欄無 DEFAULT（反查法，跨全部文件、支援多行 ALTER TABLE）", not viol,
      f"四欄型別: { {c: sorted(v) for c, v in col_types.items()} }"
      + (f"；違規: {viol}" if viol else ""))

# B5 — label domain 一致
DOMAIN_DOCS = ["SYSTEM_UPGRADE_MASTER_PLAN.md", "FEATURE_REGISTRY.md", "PURGED_WALK_FORWARD_SPEC.md"]
declared = [f for f in DOMAIN_DOCS if "{-1, 0, 1" in D[f]]
has_ck = "target_triple_barrier IN (-1, 0, 1)" in mig
check("B5", "Triple-Barrier label domain 一致", len(declared) == 3 and has_ck,
      f"{len(declared)}/3 文件宣告；DDL CHECK={has_ck}")

# B6 — barrier anchor 一致
anchored = [f for f in D if "Open[T+1]" in D[f]]
stale = [f for f in D if "Close[T] × (1" in D[f]]
check("B6", "Barrier anchor 一致為 Open[T+1]", len(anchored) >= 4 and not stale,
      f"{len(anchored)} 份使用；殘留舊 anchor {len(stale)}")

# B7 — 逐行判定失敗語意
hits = []
for fname, text in D.items():
    for line in text.split("\n"):
        if "回傳空 DataFrame" in line or "article_count = 0" in line:
            ok = any(k in line for k in ["不得", "不回傳", "SUCCESS_EMPTY", "只在"])
            hits.append((fname, ok, line.strip()[:70]))
check("B7", "無「來源失敗→空 DataFrame」", all(h[1] for h in hits),
      f"{len(hits)} 處提及，逐行判定全部為正當語境"
      + ("" if all(h[1] for h in hits) else f"；違規: {[h for h in hits if not h[1]]}"))

# B8 — 反查：§19 需 PO 簽的決策是否都有 ADR 承接
REQUIRED_ADRS = ["DEC-010", "DEC-011", "DEC-013", "DEC-016", "DEC-017", "DEC-018"]
found = {a: (f"## {a}" in D["DECISIONS.md"]) for a in REQUIRED_ADRS}
check("B8", "§19 需 PO 簽的決策皆有 ADR 承接", all(found.values()),
      f"{sum(found.values())}/{len(REQUIRED_ADRS)} 存在"
      + (f"；缺失: {[a for a in REQUIRED_ADRS if not found[a]]}" if not all(found.values()) else ""))

# B9 — SB 引用正確
check("B9", "Dcard SB 引用正確",
      "UG-G3-SB1" not in D["MULTI_SOURCE_DATA_CONTRACT.md"]
      and "UG-G2-SB5" in D["MULTI_SOURCE_DATA_CONTRACT.md"],
      "UG-G2-SB5 存在，無 UG-G3-SB1 誤引用")

# B10 — 編號方案唯一對照表
check("B10", "編號方案有唯一對照表", "### 3.7" in D["FEATURE_REGISTRY.md"],
      "FEATURE_REGISTRY.md §3.7 DB序號↔模型輸入索引對照")

# ---------------------------------------------------------------------------
# B11 — 反查：全文件的「N 欄契約 / N 條斷言」宣告是否都與權威值一致
#
# 為何需要這條：V8 的 C-1~C-4 缺陷（DECISIONS.md 與 TRACEABILITY.md 仍寫 27 欄／8 條斷言）
# 能存活到 PO 審查，是因為舊檢查有兩個盲點——
#   B1 是拿 Migration DDL 跟自己對，不看治理層文件怎麼「宣告」；
#   B8 只查 ADR 是否存在，不查 ADR 內容是否與規格一致。
# 本檢查改為掃描**所有**文件中的數字宣告，反查是否等於權威值。
# ---------------------------------------------------------------------------
AUTHORITATIVE_COLUMNS = 29
AUTHORITATIVE_ASSERTIONS = 10

COL_PATTERNS = [r"(\d+)\s*欄(?:位)?\s*(?:資料)?契約", r"固定\s*(\d+)\s*欄",
                r"擴[充展]至\s*\*?\*?(\d+)\s*欄"]
ASSERT_PATTERNS = [r"(\d+)\s*條\s*(?:測試)?斷言", r"(\d+)\s*項\s*斷言"]

# 已知的既有 ADR 遺留宣告：屬 Phase 3 舊契約，已登錄為 DRIFT-007，
# 排定由 UG-G1-SB5「文件全面校正」處理（Master Plan §15.2 修訂既有 ADR）。
# 列在此處是為了讓債務**可見**，不是為了讓它消失。
LEGACY_ALLOWLIST = {
    ("DECISIONS.md", "18"): "DEC-007 (Phase 3 舊契約) — DRIFT-007，排定 UG-G1-SB5 修訂",
}

violations, warnings = [], []
for fname, text in D.items():
    for lineno, line in enumerate(text.split(chr(10)), 1):
        for pat, expect, kind in ([(p, AUTHORITATIVE_COLUMNS, "欄") for p in COL_PATTERNS]
                                  + [(p, AUTHORITATIVE_ASSERTIONS, "斷言") for p in ASSERT_PATTERNS]):
            for m in re.finditer(pat, line):
                n = m.group(1)
                if int(n) == expect:
                    continue
                key = (fname, n)
                if key in LEGACY_ALLOWLIST:
                    warnings.append(f"{fname}:{lineno} n={n} ({kind}) — {LEGACY_ALLOWLIST[key]}")
                else:
                    violations.append(f"{fname}:{lineno} 宣告 {n} {kind}（權威值 {expect}）: {line.strip()[:60]}")

detail = f"掃描 {len(D)} 份文件；違規 {len(violations)}；已登錄遺留 {len(warnings)}"
check("B11", "全文件契約數字宣告一致（反查法）", not violations, detail)
for w in warnings:
    print(f"       [WARN 已登錄遺留] {w}")
for v in violations:
    print(f"       [VIOLATION] {v}")

# ---------------------------------------------------------------------------
# B12 — 反查：FEATURE_REGISTRY 宣告需要的 DB 欄位，讀取端是否真的 SELECT 了
#
# 【為何需要這條】同一個「讀取端缺口」在本專案出現**三次**，每次都靠人偶然發現：
#   1. UG-G2-SB4  — market_articles 的四個留言計數欄（SB3 已建欄，讀取端沒撈）
#   2. UG-G2-SB5  — source 欄（NOT NULL 且 UI 路徑一直有撈，特徵路徑沒撈）
#   3. UG-G2-SB8  — high_price / low_price（真實庫 117/117 非 NULL，就是沒撈）
# 三次形狀完全相同：**資料一直都在，是讀取端的 SELECT 沒撈**。
# 第三次尤其明顯——是 UG-G2-MIG 為了驗證 migration 才逐欄看到的，不是檢查抓到的。
#
# 這是 CLAUDE.md §9A.1 的**契約反查法**：從契約要求出發列舉所有應受約束的對象，
# 逐一反查實作是否滿足，而不是從已知答案出發湊一個會通過的檢查。
#
# 放在 contract-check 而非測試：.githooks/pre-commit 檢查 1 會跑本檔，
# **每一次 commit 都會驗**——那是唯一能在第四次發生前抓到它的位置。
# ---------------------------------------------------------------------------
DB_WRITER_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "src", "loaders", "db_writer.py")

# 契約中以「表.欄位」明確可解析的需求。
# 【誠實揭露】FEATURE_REGISTRY 的「資料來源」欄是**自然語言**（例如
# 「待實作於 feature_aggregator.py」），無法一律機械解析。本檢查只涵蓋能明確對應到
# DB 欄位名稱的項目，**其餘明確列為「未涵蓋」並輸出**，不靜默略過——
# 一個宣稱涵蓋全部卻實際跳過一半的檢查，比沒有檢查更危險（§9A.1 的 B4 教訓）。
REQUIRED_DB_COLUMNS = {
    # 欄位名: (需要它的特徵, 契約依據)
    "high_price":          ("amplitude_ratio", "FEATURE_REGISTRY §3.4 (High - Low) / Close"),
    "low_price":           ("amplitude_ratio", "FEATURE_REGISTRY §3.4 (High - Low) / Close"),
    "close_price":         ("多個價量特徵", "FEATURE_REGISTRY §3.3/§3.4"),
    "volume":              ("volume_ratio_5d", "FEATURE_REGISTRY §3.4 Volume / MA5_Vol"),
    "source":              ("留言方向類特徵", "FEATURE_REGISTRY §5.7 來源能力宣告"),
    "push_count":          ("comment_polarization", "FEATURE_REGISTRY §5.1/§5.3"),
    "boo_count":           ("comment_polarization", "FEATURE_REGISTRY §5.1/§5.3"),
    "neutral_count":       ("留言總數組成", "FEATURE_REGISTRY §5.2"),
    "total_comments":      ("comment_volume_ratio", "FEATURE_REGISTRY §5.2"),
    "comments_scraped_at": ("時點有效性過濾", "FEATURE_REGISTRY §5.5 (DEC-024)"),
    "sentiment_score":     ("情緒類特徵", "FEATURE_REGISTRY §3.3"),
    "fetch_keyword":       ("entity_mapping join", "FEATURE_REGISTRY §3.3"),
    "post_time":           ("交易日對齊", "FEATURE_REGISTRY §5.5"),
}
# 契約中無法機械解析、因此本檢查**不涵蓋**的項目（必須被輸出，不得隱藏）
UNCOVERED = [
    "四個 CORE_16 平穩化特徵的「資料來源」欄為「待實作於 feature_aggregator.py」"
    "——自然語言，無法對應到具體 DB 欄位",
    "題材溢出（theme_stock_mapping）與 entity_mapping 的欄位需求"
    "——由獨立查詢取得，不在 fetch_all_for_features 的兩句 SELECT 內",
]

try:
    with io.open(DB_WRITER_PATH, encoding="utf-8") as fh:
        _dbw = fh.read()
    _start = _dbw.index("def fetch_all_for_features")
    _window = _dbw[_start:_start + 2500]
    # 【本檢查的第一版在此處失敗過，記錄以免重演】
    # 初版直接在整段原始碼上搜尋欄位名，結果 known-FAIL 案例（移除 SELECT 裡的
    # high_price）**沒有 FAIL**——因為緊鄰的註解裡也寫著 "high_price"，
    # 檢查掃到了註解而不是 SQL。
    #
    # 那正是 CLAUDE.md §9A.1 記載的 B4 grep 失敗模式，
    # 而它發生在一支**為了防止該模式而寫的檢查**上。
    # 若沒有依 §9A.2 實際跑一次 known-FAIL，這支檢查會以「12/12 PASS」的外觀
    # 永遠通過，並讓第四次讀取端缺口照樣溜過去。
    #
    # 修法：只看**非註解行**。註解裡提到欄位名是說明，不是 SELECT。
    _reader_src = chr(10).join(
        line for line in _window.split(chr(10))
        if not line.lstrip().startswith("#")
    )
    missing = [f"{c}（{REQUIRED_DB_COLUMNS[c][0]}；{REQUIRED_DB_COLUMNS[c][1]}）"
               for c in REQUIRED_DB_COLUMNS if c not in _reader_src]
    b12_detail = (f"契約需求 {len(REQUIRED_DB_COLUMNS)} 欄；"
                  f"讀取端缺 {len(missing)}；未涵蓋 {len(UNCOVERED)} 類")
    b12_ok = not missing
except Exception as exc:  # noqa: BLE001
    missing = [f"無法讀取 db_writer.py: {type(exc).__name__}: {exc}"]
    b12_detail = "讀取端來源檔無法解析"
    b12_ok = False

check("B12", "特徵契約需要的 DB 欄位，讀取端皆有 SELECT（反查法）", b12_ok, b12_detail)
for u in UNCOVERED:
    print(f"       [未涵蓋] {u}")
for m in missing:
    print(f"       [VIOLATION] 讀取端未 SELECT: {m}")


# --------------------------------------------------------------------------
# B13 — `DECISIONS.md` 的狀態欄必須是可機械檢查的詞彙
# --------------------------------------------------------------------------
# **本檢查的 known-FAIL 案例是一件真實發生過的事**，不是構造出來的：
#
#   DEC-030 於 2026-08-31 經 PO 核准，`TRACEABILITY.md` 同日記為 `APPROVED`，
#   **而 `DECISIONS.md` 的狀態欄寫成 `Proposed（…）` 並停在那裡五天。**
#   兩次獨立查證都用 `grep '狀態：`PROPOSED`'`（反引號＋全大寫）——
#   **那個樣式在檔案裡不存在，所以兩次都回報零命中。**
#
#   > 依 `CLAUDE.md` §0.2，`DECISIONS.md` 是權威 —— 而權威的那一份是舊的。
#   > **不是查得不夠仔細，是查對了地方而那個地方是錯的。**
#
#   **診斷完那一輪之後，下一則新增的 ADR（DEC-034）又用了同一個格式。**
#   成因很具體：那個格式沒有任何東西在擋，而人會寫出自己剛讀過的樣子。
#
# --------------------------------------------------------------------------
# 本檢查要求什麼、刻意不要求什麼
# --------------------------------------------------------------------------
# **要求**：狀態值的字首必須是**全大寫**的詞彙成員。
#          `Proposed（…）` 因此 FAIL —— **而它正是藏了五天的那個寫法。**
#          若只做大小寫無關的詞彙比對，那個寫法會通過，本檢查就白寫了（§9A.1）。
#
# **刻意不要求**：反引號。
#          六則 Gate 0 ADR（DEC-011／013／016／017／018／019）寫的是
#          無反引號的 `APPROVED（Gate 0 交付物 X — 由 Project Owner 核准）`。
#          **它們是正確的狀態，只是沒有反引號。**
#
#          統一那六則的格式是**內容無損但屬 scope 的變更**（`CLAUDE.md` §12.2），
#          **需要事前向 PO 揭露並取得授權** —— 而且它們是已核准的 Gate 0 交付物。
#          **不統一，而且這是一個結論、不是待辦**（PO 2026-09-05 裁決）：
#
#          > 想要反引號的**唯一理由是可 grep**。
#          > **而本檢查已經取代了那個 grep**（見下方「誠實揭露邊界」）。
#          > **所以統一那六則現在是純粹的外觀變更，
#          > 卻要對六份已核准的 Gate 0 交付物做 §12.2 的 scope 變更 ——
#          > 代價還在，收益沒了。**
#
#          **記在這裡是為了讓下一個人不必再提一次** ——
#          否則他會覺得自己是在做整理。
#          （一個「順手」的格式正規化正是 §12.2 那條規則的由來，commit `3baa34f`。）
#
# ⚠ **誠實揭露本檢查的邊界**：反引號可選，代表
# `grep '`PROPOSED`'` 仍可能找不到一個寫成裸 `PROPOSED` 的狀態。
# **本檢查取代那個 grep，不是補強它** —— 要查待轉的 ADR 請跑本腳本，不要 grep。
STATUS_VOCAB = {"APPROVED", "PROPOSED", "SUPERSEDED", "REJECTED"}

# ⚠ **豁免：前一團隊留下的四則描述性狀態。**
#
# DEC-001 `Completed`／DEC-002 `Completed`／DEC-003 `Implemented`／
# DEC-004 `Architecture Decision APPROVED；…` —— 它們記的是
# 「那個 Gate 當時做完了什麼」，**不是 ADR 生命週期狀態**，且不待核准。
#
# **為什麼用列舉而不是描述性質**（與 `PROJECT_STATUS.md` §0.5 #5 的教訓相反）：
# 那一條說「義務應描述性質，不應列舉地點」，因為**被列舉的東西會繼續成長**。
# **這裡剛好相反 —— 這個集合必須是封閉的。**
# 若改用「凡描述性狀態皆豁免」這種性質式寫法，
# **下一則新 ADR 就能寫 `Completed` 並通過檢查**，
# 等於承認第二套平行的狀態模型。
#
# **列舉在這裡是正確的，因為「不再增加」正是我們要強制的事。**
STATUS_EXEMPT = {"DEC-001", "DEC-002", "DEC-003", "DEC-004"}

_dec = D["DECISIONS.md"]
# R3 修法（PO 2026-09-08，第 6 案，跨文件狀態一致性稽核）：逐則遍歷
# `## DEC-` 條目建立區塊，每則必須解析出恰一行可辨識狀態；缺席或格式不可
# 辨識 → FAIL。子集合盲掃在結構上不再可能——舊版只在遇到 `^- 狀態：`
# 開頭的行時才計數，DEC-005/006/007/008/009/022 因格式不符或欄位缺席，
# 從未進入 b13_seen，過去回報的「PASS」是在對這 6 則視而不見的子集合上
# 通過的（見 doc/upgrade/gates/evidence/CROSS_DOC_CONSISTENCY_B13_fix_evidence.json
# 的新舊邏輯並排輸出）。這正是本專案 §9A.1「只看已知沒問題的地方」教訓的
# 第三個實例，這次在既有機制本身裡發現。
_blocks = {}
_cur = None
_buf = []
for _ln in _dec.splitlines():
    _m = re.match(r"^## (DEC-\d+)", _ln)
    if _m:
        if _cur is not None:
            _blocks[_cur] = _buf
        _cur = _m.group(1)
        _buf = []
    elif _cur is not None:
        _buf.append(_ln)
if _cur is not None:
    _blocks[_cur] = _buf

b13_bad = []
b13_pending = []
b13_seen = 0
for _adr in sorted(_blocks, key=lambda x: int(x.split("-")[1])):
    if _adr in STATUS_EXEMPT:
        continue
    b13_seen += 1
    _status_lines = [l for l in _blocks[_adr] if l.startswith("- 狀態：")]
    if len(_status_lines) != 1:
        b13_bad.append("%s: %s" % (_adr,
            "找不到可辨識狀態行" if not _status_lines
            else "找到 %d 行，應恰一行" % len(_status_lines)))
        continue
    _raw = _status_lines[0][len("- 狀態："):].strip()
    # 反引號可選（見上方說明）；**大小寫不可選**。
    _m2 = re.match(r"^`?([A-Za-z]+)`?", _raw)
    _tok = _m2.group(1) if _m2 else ""
    if _tok.upper() not in STATUS_VOCAB or _tok != _tok.upper():
        b13_bad.append("%s: %s" % (_adr, _raw[:60]))
    elif _tok == "PROPOSED":
        b13_pending.append("%s %s" % (_adr, _raw[len(_tok) + 2:][:70]))

b13_detail = ("逐則遍歷（反查法）：掃描 %d 則；豁免 %d 則（DEC-001~004 為前一團隊的描述性狀態）；"
              "不合規 %d 則" % (b13_seen, len(STATUS_EXEMPT), len(b13_bad)))
check("B13", "DECISIONS.md 狀態欄字首為全大寫的詞彙成員（反查法）",
      not b13_bad, b13_detail)
for _b in b13_bad:
    print("       [VIOLATION] 狀態欄非詞彙成員或非全大寫: %s" % _b)

# --------------------------------------------------------------------------
# 待轉清單 —— **印，不擋**
# --------------------------------------------------------------------------
# **B13 的詞彙檢查只解決了 DEC-030 那件事的一半。**
#
#   (1) 它寫成 `Proposed`（**格式**）——詞彙檢查修好了
#   (2) `UG-G2-SB8` 結案時沒有人注意到它還沒轉（**可見性**）——詞彙檢查碰不到
#
# **若 DEC-030 當初寫的是正確的 `PROPOSED`，詞彙檢查會讓它通過，
# 而它一樣會躺五天。**
#
# **印，不擋**：一則 `PROPOSED` 的 ADR 在 SB 進行中是正當的，
# 擋它會卡住所有工作。這與 `.githooks/pre-commit` 檢查 4
# （列印 staged 清單、不擋）是同一種校準。
#
# **價值在出現的時機**：contract-check 在 pre-commit 裡跑，
# **所以每一次 commit 都會把「還有哪幾則待轉」放到正在結案的那個人眼前。**
# **DEC-030 缺的正是這個。**
if b13_pending:
    print("       [待轉] 以下 ADR 仍為 PROPOSED，SB／Gate 結案時應一併轉 "
          "`APPROVED`（PROJECT_STATUS.md §0.5 #10）：")
    for _p in b13_pending:
        print("              %s" % _p)
else:
    print("       [待轉] 無 —— 目前沒有停在 PROPOSED 的 ADR")

# --------------------------------------------------------------------------
# B14 — APPROVED 的 ADR 不得含未標 NOT VERIFIED 去處的未勾項（反查法）
# --------------------------------------------------------------------------
# **由來（DRIFT-019，PO 2026-09-14）**：ADR 狀態轉 `APPROVED` 綁定 Gate B
# 事件（`PROJECT_STATUS.md` §0.5 #10），但 `Verification` 清單的勾選**沒有
# 對應規則**。PO 發現 `DEC-036` 已 `APPROVED`，但 `Verification` 仍列著
# 核准當下寫的未勾項（「`UG-G3-SB2a` 自己的 Gate A 提案（待開）」）——
# 實際上早已核准並結案，只是沒有人回頭勾。全文重新掃描發現同型情況共
# **8 則**（見 `DOCUMENT_DRIFT_REMEDIATION.md` DRIFT-019）。B13 對這個問題
# 是一個結構上不可能失敗的檢查——它只查「停在 `PROPOSED` 的 ADR」，
# 不查「`APPROVED` 卻含未勾項」的 ADR，兩者是不同的失效模式（`CLAUDE.md`
# §9A.1）。
#
# **判準**（反查法）：對每一則狀態為 `APPROVED` 的 ADR，掃描其區塊內容，
# 任何一行 `- [ ]`（未勾）若不是**同時**含 `NOT VERIFIED` 與 `去處` 兩個字樣，
# 即為違規——`APPROVED` 的 ADR 允許保留誠實未勾的項目（如需要人工肉眼確認、
# 刻意延後的項目），但必須明講是 `NOT VERIFIED` **並附去處**，不得留一句
# 看起來像「忘記處理」的裸未勾項，也不得只標 `NOT VERIFIED` 卻不說去處是什麼。
#
# **判準訂正紀錄（2026-09-14，複核發現）**：上線版本只查 `NOT VERIFIED` 單一
# 字樣。這與本節前段文字宣稱的「必須明講是 `NOT VERIFIED` 並附去處」不一致
# ——程式從未真的檢查「去處」。同時，用訂正前的 `DECISIONS.md` 對舊判準
# 重新測試，只抓到 7 則（不是本節原先宣稱的 8 則）：`DEC-020` 的原文本來就
# 含 `NOT VERIFIED` 字樣（但沒附去處），舊判準因此從未把它判為違規。改成
# 雙字樣判準後，對訂正前的 `DECISIONS.md` 重新測試抓到正確的 8 則
# （含 `DEC-020`），對訂正後的版本則 0 則、14/14 PASS——見下方 known-FAIL。
#
# **known-FAIL**：本檢查上線前，`DECISIONS.md` 確實含 8 則這樣的違規
# （即 `DEC-013`／`016`／`017`／`033`／`034`／`036`／`012`／`020`，
# `DOCUMENT_DRIFT_REMEDIATION.md` DRIFT-019 登記的那 8 則）；訂正後
# （8 則皆已補勾附證據，或改寫為 `NOT VERIFIED → 去處：` 格式）本檢查
# 轉 PASS。若日後新增 ADR 時複製了裸 `- [ ]` 未勾項又忘記回頭處理，
# 本檢查會在下一次 commit 前重新 FAIL——這正是它被設計要抓的東西。
b14_bad = []
b14_seen = 0
for _adr in sorted(_blocks, key=lambda x: int(x.split("-")[1])):
    if _adr in STATUS_EXEMPT:
        continue
    _status_lines = [l for l in _blocks[_adr] if l.startswith("- 狀態：")]
    if len(_status_lines) != 1:
        continue  # 格式問題由 B13 負責回報，此處不重複
    _raw = _status_lines[0][len("- 狀態："):].strip()
    _m2 = re.match(r"^`?([A-Za-z]+)`?", _raw)
    _tok = _m2.group(1) if _m2 else ""
    if _tok != "APPROVED":
        continue
    b14_seen += 1
    _unchecked = [l for l in _blocks[_adr] if l.strip().startswith("- [ ]")]
    _bad_lines = [l for l in _unchecked if not ("NOT VERIFIED" in l and "去處" in l)]
    if _bad_lines:
        b14_bad.append("%s: %d 項未勾且未標 NOT VERIFIED" % (_adr, len(_bad_lines)))

b14_detail = ("逐則遍歷 APPROVED 的 ADR（反查法）：掃描 %d 則；不合規 %d 則"
              % (b14_seen, len(b14_bad)))
check("B14", "APPROVED 的 ADR 不得含未標 NOT VERIFIED 去處的未勾項（反查法，DRIFT-019）",
      not b14_bad, b14_detail)
for _b in b14_bad:
    print("       [VIOLATION] %s" % _b)

# B15 — FEATURE_REGISTRY.md 的 Source 欄函式/方法名錨點必須存在於原始碼
# --------------------------------------------------------------------------
# **由來**（§0.5 #38，審查方唯讀查證，2026-09-20）：`FEATURE_REGISTRY.md`
# 的 `Source` 欄原本以行號指向 `feature_aggregator.py`，15 處引用中 14 處
# 已經指到與該欄位完全無關的程式碼——行號當錨點結構上保證會隨程式碼插入
# 而漂移，而本檔案先前沒有任何一項檢查驗證這件事。`FEATURE_REGISTRY_SOURCE_
# ANCHOR_GATE_A_PROPOSAL.md`（PO 核准）改用函式／方法名稱錨點取代行號，
# 本檢查是該規格變更的機械防線。
#
# **格式**：`` `<檔案>::<函式名>()` `` 或 `` `<檔案>::<類別名>.<方法名>()` ``，
# 必須整段落在同一組反引號內——錨點後方若有括號散文備註（例：說明某個
# 巢狀閉包的實作細節），備註在反引號**之外**，不參與本檢查抽取。
#
# **判準**：對每一個抽到的錨點，確認 `<檔案>` 在 repo 內存在（含 `/` 的視為
# 相對 repo root 的路徑；純檔名則在 `src/`／`scripts/` 下搜尋，唯一命中才算
# 解析成功），且該檔案內存在 `def <函式或方法名>(`（正則允許前導縮排，
# 天然涵蓋模組層級函式與類別方法）。
#
# **刻意不做的事**（提案 §3.2、§3.3 已載明，範圍界定而非疏漏）：
#   - 不驗證函式內是否真的賦值了對應的欄位名——某些欄位透過迴圈變數間接
#     賦值（例：`ma5_bias_ratio`／`ma20_bias_ratio`），字面搜尋欄位名會對
#     合法寫法誤報。
#   - 不驗證 `<類別名>` 前綴是否與函式實際所屬的類別相符——只驗方法名本身
#     存在，`WrongClass.generate_daily_features()` 這種類別名寫錯的情況
#     仍會 PASS。要驗類別歸屬需要解析 AST，是另一個量級的工作，且本案要
#     修的是「指都指錯地方」，不是「指對地方但歸屬標錯」。
#   - 不驗證函式簽章不變但整個邏輯被替換、或欄位被賦值到錯誤變數上的情況
#     ——這與行號漂移是不同類型的問題（那是「連指都指錯地方」，這裡是
#     「指的地方對，但內容可能不符」）。
#
# **與 Decision 規則的分工**：錨點只准指向頂層函式或類別方法，不得指向
# 巢狀函式／閉包／lambda（`DECISIONS.md` 新 ADR）——本檢查的存在性判斷
# 天然涵蓋巢狀函式（`grep`／正則不管縮排），**檢查在這一點上是盲的，
# 只能靠這條人工規則在源頭堵住**，機械檢查與人工規則各自負責不同層面。
#
# **known-FAIL**（提案核准前已在 `/tmp` 拋棄式副本上驗證，未觸碰真實檔案）：
# 把 `feature_aggregator.py` 的 `compute_rsi` 改名為 `compute_rsi_v2` 後，
# 對錨點 `` `feature_aggregator.py::compute_rsi()` `` 執行本檢查邏輯，
# 正確回報 `找不到 def compute_rsi(`；復原後（刪除 `/tmp` 副本）`git diff
# --stat` 對真實 repo 顯示零變更。
#
# **補強（複核第三輪發現，2026-09-20）**：原始版本的判斷邏輯是「對每一個
# 抽到的錨點做驗證」——若某列的 Source 欄**一個錨點都抽不到**（例如被
# 改回行號參照 `feature_aggregator.py L142-168`，或改回裸檔名），內層迴圈
# 完全不會碰到這一列，本檢查對它零檢查、零違規記錄，PASS 照樣成立。
# 也就是說，**#38 這整個規格變更（禁止行號參照）要防的那種回歸，本檢查
# 自己攔不住**——這正是 `CLAUDE.md` §9A.1「結構上無法失敗的檢查不是檢查」
# 的典型形狀，且不在上方「刻意不做的事」清單內（那三項是已宣告的範圍
# 界定，這項是未被發現的缺口）。
#
# 補強規則：Source 欄的儲存格內若提及 `.py`，即代表該列宣稱有原始碼依據，
# 此時**必須**至少抽到一個合規錨點；提及 `.py` 卻抽不到任何錨點即 FAIL。
# 對現行文件試算：29 列中 21 列有錨點、8 列 Source 欄完全不提 `.py`
# （`stock_prices.*` 欄位或「待實作」列），提及 `.py` 卻無錨點者為 0 個
# ——補強後現行文件仍全數 PASS，零誤報。
#
# **known-FAIL（本次補強）**：在 `/tmp` 拋棄式副本上把第 8 列（`rsi_14`）
# 的錨點 `` `feature_aggregator.py::compute_rsi()` `` 換回行號字串
# `feature_aggregator.py L142-168`，本檢查正確回報
# `#8 rsi_14: Source 欄提及 .py 檔卻抽不到函式/方法名錨點（可能是行號或
# 裸檔名格式殘留）`；復原後（刪除 `/tmp` 副本）`git diff --stat` 對真實
# repo 顯示零變更。
FEATURE_REGISTRY_ANCHOR_RE = re.compile(
    r"`([\w./]+\.py)::((?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*)\(\)`"
)
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _b15_parse_source_rows(text):
    rows = []
    for line in text.split("\n"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if not re.match(r"^\d+$", cells[0]):
            continue
        rows.append((int(cells[0]), cells[1], cells[5]))
    return rows


def _b15_extract_anchors(source_cell):
    out = []
    for m in FEATURE_REGISTRY_ANCHOR_RE.finditer(source_cell):
        file_part, name_part = m.group(1), m.group(2)
        method = name_part.rsplit(".", 1)[-1]
        out.append((file_part, method))
    return out


def _b15_resolve_repo_file(file_part):
    if "/" in file_part:
        candidate = os.path.normpath(os.path.join(_REPO_ROOT, file_part))
        return candidate if os.path.isfile(candidate) else None
    matches = []
    for base in ("src", "scripts"):
        base_path = os.path.normpath(os.path.join(_REPO_ROOT, base))
        for dirpath, _dirnames, filenames in os.walk(base_path):
            if file_part in filenames:
                matches.append(os.path.join(dirpath, file_part))
    return matches[0] if len(matches) == 1 else None


def _b15_function_exists(filepath, method_name):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    return re.search(r"^\s*def %s\(" % re.escape(method_name), content, re.MULTILINE) is not None


b15_bad = []
b15_seen = 0
for _row_num, _col_name, _source_cell in _b15_parse_source_rows(D["FEATURE_REGISTRY.md"]):
    _anchors = _b15_extract_anchors(_source_cell)
    if not _anchors:
        if ".py" in _source_cell:
            b15_bad.append(
                "#%d %s: Source 欄提及 .py 檔卻抽不到函式/方法名錨點"
                "（可能是行號或裸檔名格式殘留）" % (_row_num, _col_name)
            )
        continue
    for _file_part, _method in _anchors:
        b15_seen += 1
        _resolved = _b15_resolve_repo_file(_file_part)
        if _resolved is None:
            b15_bad.append("#%d %s: 檔案 %s 不存在或無法唯一解析" % (_row_num, _col_name, _file_part))
            continue
        if not _b15_function_exists(_resolved, _method):
            b15_bad.append("#%d %s: %s 找不到 def %s(" % (_row_num, _col_name, _file_part, _method))

b15_detail = "掃描 %d 個 Source 欄函式/方法名錨點；不合規 %d 個" % (b15_seen, len(b15_bad))
check("B15", "FEATURE_REGISTRY.md Source 欄的函式/方法名錨點皆存在於原始碼",
      not b15_bad, b15_detail)
for _b in b15_bad:
    print("       [VIOLATION] %s" % _b)

passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 50)
print(f"Part B: {passed}/{len(results)} PASS")
sys.exit(0 if passed == len(results) else 1)
