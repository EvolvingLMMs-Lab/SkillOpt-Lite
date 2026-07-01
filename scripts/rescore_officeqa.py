"""Re-score saved OfficeQA results.jsonl with the fixed evaluator."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skillopt.envs.officeqa.evaluator import evaluate  # type: ignore


def rescore(out_root: str, label: str):
    path = Path(out_root) / "selection_eval_baseline" / "results.jsonl"
    if not path.exists():
        print(f"[skip] {path} not found")
        return
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    old_hard = sum(r["hard"] for r in rows)
    old_soft = sum(r["soft"] for r in rows) / len(rows)
    new_hard = 0
    new_soft_sum = 0.0
    flipped = []
    for r in rows:
        ev = evaluate(r.get("predicted_answer", ""), r.get("ground_truth", ""))
        new_hard += int(ev["em"])
        new_soft_sum += ev["f1"]
        if int(ev["em"]) != r["hard"]:
            flipped.append((r["id"], r.get("predicted_answer", ""), r.get("ground_truth", ""), r["hard"], int(ev["em"])))
    print(f"\n=== {label} ({len(rows)} items) ===")
    print(f"  OLD: hard={old_hard}/{len(rows)} ({old_hard/len(rows):.4f})  soft={old_soft:.4f}")
    print(f"  NEW: hard={new_hard}/{len(rows)} ({new_hard/len(rows):.4f})  soft={new_soft_sum/len(rows):.4f}")
    print(f"  flipped: {len(flipped)}")
    for f in flipped:
        print(f"    [{f[0]}] {f[3]} -> {f[4]}  pred={f[1][:70]!r}  gold={f[2]!r}")


if __name__ == "__main__":
    for out, lab in (
        ("outputs/skillopt_officeqa_gpt-5.4-nano_2026-03-17_20260610_093325", "NANO baseline"),
        ("outputs/skillopt_officeqa_gpt-5.4-mini_2026-03-17_20260610_105741", "MINI baseline (currently running)"),
        ("outputs/skillopt_officeqa_gpt-5.4-nano_2026-03-17_20260610_083239", "NANO smoke (sel=8)"),
    ):
        rescore(out, lab)
