"""Diagnose OfficeQA scoring vs predicted answers."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skillopt.envs.officeqa.evaluator import normalize_answer  # type: ignore


def analyze(out_root: str, label: str):
    path = Path(out_root) / "selection_eval_baseline" / "results.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    print(f"\n=== {label}  ({len(rows)} items) ===")
    print(f"  hard sum: {sum(r['hard'] for r in rows)}/{len(rows)}")
    print(f"  soft mean: {sum(r['soft'] for r in rows)/len(rows):.4f}")

    empty = [r for r in rows if not r.get("predicted_answer", "").strip()]
    timeout = [r for r in rows if r.get("fail_reason", "").startswith("timeout")
               or "TIMEOUT" in r.get("fail_reason", "")
               or r.get("turns") is None]
    print(f"  empty prediction: {len(empty)}")
    print(f"  timeout/no-turns: {len(timeout)}")

    near_miss = []  # normalized pred contains gold as substring or vice-versa
    very_close = []  # tokens overlap >= 0.3
    purely_wrong = []
    fmt_only = []  # would EM=1 if compared loosely
    for r in rows:
        pred = r.get("predicted_answer", "")
        gold = r.get("ground_truth", "")
        np_, ng = normalize_answer(pred), normalize_answer(gold)
        if np_ == ng:
            continue  # already EM=1
        if ng and np_ and ng in np_.split():
            fmt_only.append((r["id"], pred, gold, np_, ng))
        elif r.get("soft", 0) >= 0.3:
            very_close.append((r["id"], pred, gold, r["soft"]))
        else:
            purely_wrong.append((r["id"], pred, gold))

    print(f"  format-only failures (gold token present in normalized pred): {len(fmt_only)}")
    for ex in fmt_only[:5]:
        print(f"      [{ex[0]}] pred={ex[1][:80]!r}  gold={ex[2]!r}")
        print(f"          normalized pred={ex[3][:80]!r}  norm gold={ex[4]!r}")
    print(f"  near-miss (soft>=0.3): {len(very_close)}")
    for ex in very_close[:5]:
        print(f"      [{ex[0]}] soft={ex[3]:.2f} pred={ex[1][:80]!r}  gold={ex[2]!r}")
    print(f"  purely wrong: {len(purely_wrong)}")
    for ex in purely_wrong[:8]:
        print(f"      [{ex[0]}] pred={ex[1][:80]!r}  gold={ex[2]!r}")

    # turns distribution
    turns = Counter(r.get("turns") for r in rows)
    print(f"  turns distribution: {dict(turns)}")


if __name__ == "__main__":
    for out, lab in (
        ("outputs/skillopt_officeqa_gpt-5.4-nano_2026-03-17_20260610_093325", "NANO (full run baseline)"),
        ("outputs/skillopt_officeqa_gpt-5.4-mini_2026-03-17_20260610_105741", "MINI (full run baseline)"),
    ):
        if Path(out).exists():
            analyze(out, lab)
