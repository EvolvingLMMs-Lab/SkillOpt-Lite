"""Check what fraction of OfficeQA test failures have gold answer present in:
  (a) the oracle parsed page already in the user prompt, vs
  (b) the cited source local file, vs
  (c) any local file at all.

This tells us whether tools (glob/read/grep) could have helped, or whether
the data itself is missing.
"""
import json
import re
import sys
from pathlib import Path

OUT = Path("outputs/skillopt_officeqa_gpt-5.4-mini_2026-03-17_20260610_105741")
DOCS_ROOT = Path("data/officeqa_docs_official/transformed")


def _norm_num(s: str) -> str:
    return s.replace(",", "").replace(" ", "").strip()


def gold_in_text(gold: str, text: str) -> bool:
    g = gold.strip()
    if not g:
        return True
    if g in text:
        return True
    # Numeric: try without commas
    g_no = _norm_num(g)
    if g_no and g_no in _norm_num(text):
        return True
    # Try the leading number (handles e.g. "1608.80%" vs "1608.80")
    m = re.search(r"-?\d+(?:\.\d+)?", g_no)
    if m:
        return m.group(0) in _norm_num(text)
    return False


def gold_in_file(gold: str, txt_path: Path) -> bool:
    try:
        return gold_in_text(gold, txt_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False


def main():
    results = [json.loads(l) for l in (OUT / "test_eval" / "results.jsonl").read_text().splitlines() if l.strip()]
    fails = [r for r in results if not r["hard"]]
    print(f"FAILED: {len(fails)} / {len(results)} (mini)")

    oracle_has_gold = 0
    cited_file_has_gold = 0
    any_local_has_gold = 0
    nothing = []

    all_local_files = list(DOCS_ROOT.glob("*.txt"))

    for r in fails[:60]:  # sample
        uid = r["id"]
        gold = r["ground_truth"]
        # 1) oracle: user prompt
        prompt_path = OUT / "test_eval" / "predictions" / uid / "target_user_prompt.txt"
        if prompt_path.exists() and gold_in_text(gold, prompt_path.read_text(encoding="utf-8", errors="ignore")):
            oracle_has_gold += 1
        # 2) cited source file
        src_files = r.get("source_files") or []
        if isinstance(src_files, str):
            src_files = [src_files]
        cited_hit = any(gold_in_file(gold, DOCS_ROOT / s) for s in src_files if (DOCS_ROOT / s).exists())
        if cited_hit:
            cited_file_has_gold += 1
        # 3) any local file
        if cited_hit:
            any_local_has_gold += 1
        else:
            # quick scan: only mark hit if a small number of files match
            any_hit = False
            for f in all_local_files[:50]:  # sample only first 50 to keep cost low — biased
                if gold_in_file(gold, f):
                    any_hit = True
                    break
            if any_hit:
                any_local_has_gold += 1
            else:
                nothing.append((uid, gold[:40], r.get("predicted_answer", "")[:60]))

    n = min(60, len(fails))
    print(f"  oracle page contains gold      : {oracle_has_gold}/{n} = {oracle_has_gold/n:.1%}")
    print(f"  cited local txt contains gold  : {cited_file_has_gold}/{n} = {cited_file_has_gold/n:.1%}")
    print(f"  any local file contains gold   : {any_local_has_gold}/{n} = {any_local_has_gold/n:.1%}")
    print(f"  gold not found anywhere checked: {len(nothing)}/{n}")
    print("\n  examples of unreachable gold (first 10):")
    for u, g, p in nothing[:10]:
        print(f"    [{u}] gold={g!r}  pred={p!r}")


if __name__ == "__main__":
    main()
