"""Scan OfficeQA test results for potential false negatives that would benefit from LLM-judge."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skillopt.envs.officeqa.evaluator import evaluate, normalize_answer  # type: ignore


def is_numeric_token(tok: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", tok))


def looks_like_format_only_match(pred: str, gold: str) -> bool:
    """Heuristic: pred contains gold as exact token, with extra context.

    Examples that should match:
      pred="The range is 926 million dollars."  gold="926"   -> True
      pred="$2,602"                              gold="2602"  -> True (already EM via normalizer)
      pred="approximately 0.717"                 gold="0.717" -> True
      pred="It is about 39.3%."                  gold="39.31" -> False (different number)
    """
    np = normalize_answer(pred)
    ng = normalize_answer(gold).strip()
    if not ng:
        return False
    # Gold is a single token: must appear as standalone token in normalized pred
    if " " not in ng:
        return ng in np.split()
    # Multi-token gold: must appear as contiguous substring
    return ng in np


def numeric_close(pred: str, gold: str, *, rel: float = 0.005) -> bool:
    """Is there a number in pred within 0.5% of gold's first number?"""
    def first_num(s: str):
        m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
        return float(m.group(0)) if m else None

    p = None
    np_ = normalize_answer(pred)
    # Try each numeric token in pred
    for tok in np_.split():
        if is_numeric_token(tok):
            v = float(tok)
            g = first_num(gold)
            if g is None:
                return False
            if g == 0:
                if abs(v) < 1e-9:
                    return True
            elif abs(v - g) / abs(g) <= rel:
                return True
    return False


def scan(out_root: str, label: str):
    test_dir = Path(out_root) / "test_eval"
    if not test_dir.exists():
        # Some runs put best test under a versioned subdir
        candidates = list((Path(out_root)).glob("test_eval_*"))
        if candidates:
            test_dir = sorted(candidates)[-1]
        else:
            # Find the latest results.jsonl referenced as final test
            jsonl = list(Path(out_root).rglob("results.jsonl"))
            # Pick the largest (test set is biggest)
            jsonl.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
            if not jsonl:
                print(f"[skip] no results.jsonl found in {out_root}")
                return
            test_dir = jsonl[0].parent
    path = test_dir / "results.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    print(f"\n=== {label} ===")
    print(f"  source: {path}")
    print(f"  items:  {len(rows)}")
    hard = sum(r["hard"] for r in rows)
    print(f"  hard:   {hard}/{len(rows)} ({hard/len(rows):.4f})")

    # Re-evaluate with current evaluator (% fix already applied)
    fixed_hard = 0
    format_only_misses = []
    numeric_close_misses = []
    purely_wrong = []
    empties = 0
    for r in rows:
        pred = r.get("predicted_answer", "")
        gold = r.get("ground_truth", "")
        if not pred.strip():
            empties += 1
        ev = evaluate(pred, gold)
        fixed_hard += int(ev["em"])
        if ev["em"]:
            continue
        if looks_like_format_only_match(pred, gold):
            format_only_misses.append((r["id"], pred, gold))
        elif numeric_close(pred, gold):
            numeric_close_misses.append((r["id"], pred, gold))
        else:
            purely_wrong.append((r["id"], pred, gold, ev["f1"]))

    print(f"  fixed evaluator hard: {fixed_hard}/{len(rows)} ({fixed_hard/len(rows):.4f})")
    print(f"  empty predictions: {empties}")
    print(f"\n  >>> potential false negatives (gold appears as token in pred, but EM=0):")
    print(f"  format-only misses: {len(format_only_misses)}")
    for ex in format_only_misses[:15]:
        print(f"    [{ex[0]}] pred={ex[1][:90]!r}")
        print(f"             gold={ex[2]!r}")
    print(f"\n  numeric-close (within 0.5%) but EM=0: {len(numeric_close_misses)}")
    for ex in numeric_close_misses[:8]:
        print(f"    [{ex[0]}] pred={ex[1][:90]!r}  gold={ex[2]!r}")
    print(f"\n  purely wrong: {len(purely_wrong)}  (mean F1: {sum(x[3] for x in purely_wrong)/max(len(purely_wrong),1):.3f})")


if __name__ == "__main__":
    for out, lab in (
        ("outputs/skillopt_officeqa_gpt-5.4-nano_2026-03-17_20260610_093325", "NANO test eval"),
        ("outputs/skillopt_officeqa_gpt-5.4-mini_2026-03-17_20260610_105741", "MINI test eval"),
    ):
        scan(out, lab)
