#!/usr/bin/env python3
"""
跨文件狀態一致性稽核（第 6 案）—— 反查法 (reverse-lookup)

方法論：從「每個治理物件應存在的狀態集」出發，逐一反查文件是否滿足，
        不從已知缺陷湊檢查。R1/R2 為互為反方向的一對——「比較已列出者」
        找不到「根本沒被列出」的缺陷，故每個方向都要有反方向。

範圍：doc/governance/PROJECT_STATUS.md ↔ doc/upgrade/gates/closed/ ↔
      doc/evidence/DECISIONS.md ↔ doc/evidence/TRACEABILITY.md ↔
      doc/upgrade/contracts/REMAINING_RISKS.md

R5（REMAINING_RISKS.md 解決性宣稱 → PROJECT_STATUS.md／DECISIONS.md）需要
語意判讀，不由本腳本產出——見 doc/upgrade/gates/evidence/
CROSS_DOC_CONSISTENCY_result.json 的人工核對表。

用法：python scripts/verify/cross_doc_consistency_check.py
輸出：R1~R4 逐項 PASS/FAIL 與細節；exit code 0 = 全通過。
"""
import re
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
PROJECT_STATUS = os.path.join(REPO, "doc", "governance", "PROJECT_STATUS.md")
CLOSED_DIR = os.path.join(REPO, "doc", "upgrade", "gates", "closed")
DECISIONS = os.path.join(REPO, "doc", "evidence", "DECISIONS.md")
TRACEABILITY = os.path.join(REPO, "doc", "evidence", "TRACEABILITY.md")

# 沿用 gate0_contract_check.py B13 的既有豁免集合，不重新裁定
STATUS_EXEMPT = {"DEC-001", "DEC-002", "DEC-003", "DEC-004"}

# R2 v2（PO 2026-09-08，第 6 案裁決）：索引式引用是刻意的文件經濟性設計，
# 不是遺漏——結案時只以單一 GATE_B_SUBMISSION.md 索引，子文件（Gate A 提案／
# 過程報告）不逐一列名。豁免表本身即揭露：每筆附理由字串，不是靜默跳過。
# ⚠ 不回頭改 closed/ 文件——這是對既有結案模式的追認，不是要求補寫歷史文件。
R2_EXEMPT = {
    "PRE_G3_01_GATE_A_PROPOSAL.md":
        "索引式引用：PRE_G3_01_GATE_B_SUBMISSION.md 為該結案唯一索引點，"
        "子文件不逐一列名（文件經濟性設計，第 6 案 R2 追認）",
    "PRE_G3_01_B1_PILOT_PROPOSAL.md":
        "索引式引用：同 PRE_G3_01_GATE_A_PROPOSAL.md",
    "PRE_G3_01_B1_PILOT_REPORT.md":
        "索引式引用：同 PRE_G3_01_GATE_A_PROPOSAL.md",
    "PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md":
        "索引式引用：PRE_G3_02_GATE_B_SUBMISSION.md 為該結案唯一索引點，"
        "子文件不逐一列名（文件經濟性設計，第 6 案 R2 追認）",
    "PRE_G3_02_COVERAGE_MEASUREMENT_REPORT.md":
        "索引式引用：同 PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md",
    "PRE_G3_02_INPUTS.md":
        "索引式引用：同 PRE_G3_02_COVERAGE_THRESHOLD_PROPOSAL.md",
    "PRE_G3_03_BACKFILL_PROPOSAL.md":
        "索引式引用：PRE_G3_03_GATE_B_SUBMISSION.md 為該結案唯一索引點，"
        "子文件不逐一列名（文件經濟性設計，第 6 案 R2 追認）",
    "STUB_AUDIT_GATE_A_PROPOSAL.md":
        "索引式引用：STUB_AUDIT_GATE_B_SUBMISSION.md 為該結案唯一索引點，"
        "子文件不逐一列名（文件經濟性設計，第 6 案 R2 追認）",
}

# R2 v2 間接查找（面向未來）：日後結案送審文件若依新規則
# （gate-submit skill 產出 8）含「本次移入清單」節，本檢查會在該節內
# 尋找子文件名，不必逐一加進 R2_EXEMPT——現有 closed/ 文件皆早於此規則，
# 該節不存在於任何既有文件，故此機制目前對既有 8 個豁免項無實際作用，
# 是面向未來的基礎設施，不是回頭修補。
MOVED_LIST_HEADING = re.compile(r"本次移入清單", re.MULTILINE)

results = []


def check(cid, name, ok, detail):
    results.append((cid, ok))
    print(f"{cid:4} {'PASS' if ok else 'FAIL'} | {name}\n       {detail}")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def parse_decisions_status(text):
    """回傳 {DEC-xxx: 狀態字首 token}，沿用 B13 的解析慣例。"""
    cur = None
    out = {}
    for ln in text.splitlines():
        m = re.match(r"^## (DEC-\d+)", ln)
        if m:
            cur = m.group(1)
        if not ln.startswith("- 狀態："):
            continue
        raw = ln[len("- 狀態："):].strip()
        m2 = re.match(r"^`?([A-Za-z]+)`?", raw)
        tok = m2.group(1) if m2 else ""
        if cur:
            out[cur] = tok.upper()
    return out


def main():
    ps_text = read(PROJECT_STATUS)
    dec_text = read(DECISIONS)
    tra_text = read(TRACEABILITY)

    # ---- R1: PROJECT_STATUS.md → gates/closed/ ----
    r1_bad = []
    r1_checked = 0
    for line in ps_text.splitlines():
        if "**CLOSED**" not in line:
            continue
        paths = re.findall(r"`(doc/upgrade/gates/closed/[^`]+\.md)`", line)
        for p in paths:
            r1_checked += 1
            full = os.path.join(REPO, p)
            if not os.path.exists(full):
                r1_bad.append(p)
    check("R1", "PROJECT_STATUS.md 引用的 closed/ 路徑皆存在（反查法）",
          not r1_bad,
          f"檢查 {r1_checked} 個路徑引用；不合規 {len(r1_bad)}"
          + (f"：{r1_bad}" if r1_bad else ""))

    # ---- R2: gates/closed/ → PROJECT_STATUS.md（孤兒偵測，R1 反方向）----
    closed_files = sorted(f for f in os.listdir(CLOSED_DIR) if f.endswith(".md"))
    # 間接查找：掃描每份 closed/ 文件本身，若含「本次移入清單」節，
    # 該節內提及的檔名視為間接被引用（面向未來，見 R2_EXEMPT 上方說明）。
    moved_list_referenced = set()
    for f in closed_files:
        text = read(os.path.join(CLOSED_DIR, f))
        m = MOVED_LIST_HEADING.search(text)
        if not m:
            continue
        section = text[m.start():]
        for other in closed_files:
            if other != f and other in section:
                moved_list_referenced.add(other)

    r2_orphans = []
    r2_exempted = []
    for f in closed_files:
        if f in ps_text or f in moved_list_referenced:
            continue
        if f in R2_EXEMPT:
            r2_exempted.append((f, R2_EXEMPT[f]))
        else:
            r2_orphans.append(f)
    check("R2", "closed/ 實體檔案皆被 PROJECT_STATUS.md 引用或有豁免理由（孤兒偵測，R1 反方向）",
          not r2_orphans,
          f"closed/ 共 {len(closed_files)} 檔；豁免 {len(r2_exempted)}（皆附理由）；孤兒 {len(r2_orphans)}"
          + (f"：{r2_orphans}" if r2_orphans else ""))
    for f, reason in r2_exempted:
        print(f"       [R2-豁免] {f}：{reason}")

    # ---- R3: PROJECT_STATUS.md 引用的 ADR → DECISIONS.md 狀態 ----
    dec_status = parse_decisions_status(dec_text)
    ps_adrs = sorted(set(re.findall(r"DEC-\d{3,}", ps_text)))
    r3_bad = []
    r3_checked = 0
    for adr in ps_adrs:
        if adr in STATUS_EXEMPT:
            continue
        r3_checked += 1
        tok = dec_status.get(adr)
        if tok != "APPROVED":
            r3_bad.append(f"{adr}: {'未於 DECISIONS.md 找到' if tok is None else tok}")
    check("R3", "PROJECT_STATUS.md 引用的 ADR，狀態皆為 APPROVED（反查法）",
          not r3_bad,
          f"PROJECT_STATUS.md 引用 {len(ps_adrs)} 個 ADR（扣豁免 {len(STATUS_EXEMPT & set(ps_adrs))}，實查 {r3_checked}）；不合規 {len(r3_bad)}"
          + (f"：{r3_bad}" if r3_bad else ""))

    # ---- R4: DECISIONS.md（APPROVED）→ TRACEABILITY.md §3 起始章節 ----
    approved_adrs = sorted(a for a, tok in dec_status.items()
                           if tok == "APPROVED" and a not in STATUS_EXEMPT)
    m3 = re.search(r"^### 3\.", tra_text, re.MULTILINE)
    tra_scope = tra_text[m3.start():] if m3 else tra_text
    r4_bad = [a for a in approved_adrs if a not in tra_scope]
    check("R4", "DECISIONS.md 中 APPROVED 的 ADR，皆見於 TRACEABILITY.md §3 起始章節（反查法）",
          not r4_bad,
          f"DECISIONS.md 中 APPROVED（非豁免）共 {len(approved_adrs)} 則；未見於 TRACEABILITY §3+ 者 {len(r4_bad)}"
          + (f"：{r4_bad}" if r4_bad else ""))

    print("\n" + "=" * 50)
    ok_count = sum(1 for _, ok in results if ok)
    print(f"R1~R4：{ok_count}/{len(results)} PASS")
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
