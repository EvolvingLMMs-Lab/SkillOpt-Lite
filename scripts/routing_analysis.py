#!/usr/bin/env python3
"""#8 per-task-type skill routing analysis.

For each task_type, compute hard-accuracy of HITL skill vs Copilot skill on
train (valid_seen, 89 items). Then build router that picks per task_type the
skill with higher train accuracy, evaluate on test (valid_unseen, 88 items),
and compare to each single skill.
"""
from __future__ import annotations
import json, os, sys
from collections import defaultdict

HITL_TRAIN = "outputs/livemath_hitl_optMED_centralus_20260601_015633/steps/step_0005/selection_eval/results.jsonl"
HITL_TEST  = "outputs/livemath_hitl_optMED_centralus_20260601_015633/test_eval/results.jsonl"
COP_TRAIN  = "outputs/copilot_oneshot_v1_valid_seen_20260601_090253/results.jsonl"
COP_TEST   = "outputs/copilot_oneshot_v1_valid_unseen_20260601_090254/results.jsonl"


def load(path):
    rows = []
    with open(path, errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: rows.append(json.loads(ln))
            except Exception: pass
    out = {}
    for r in rows:
        iid = str(r["id"])
        out[iid] = {
            "task_type": r.get("task_type","UNK"),
            "hard": int(r.get("hard", int(r.get("predicted_label","")==r.get("correct_label","")))),
            "predicted_label": r.get("predicted_label",""),
            "correct_label": r.get("correct_label",""),
        }
    return out


def per_type_acc(d):
    by = defaultdict(list)
    for r in d.values():
        by[r["task_type"]].append(r["hard"])
    return {k: (sum(v)/len(v), len(v)) for k,v in by.items()}


def main():
    H_tr = load(HITL_TRAIN); H_te = load(HITL_TEST)
    C_tr = load(COP_TRAIN);  C_te = load(COP_TEST)
    print(f"HITL train n={len(H_tr)} test n={len(H_te)}")
    print(f"Copilot train n={len(C_tr)} test n={len(C_te)}")

    # Overall
    def acc(d): return sum(r["hard"] for r in d.values())/max(1,len(d))
    print(f"\nOverall acc:")
    print(f"  HITL    train={acc(H_tr):.4f} test={acc(H_te):.4f}")
    print(f"  Copilot train={acc(C_tr):.4f} test={acc(C_te):.4f}")

    # Per task_type on TRAIN (used to decide routing)
    H_tr_t = per_type_acc(H_tr); C_tr_t = per_type_acc(C_tr)
    types = sorted(set(H_tr_t)|set(C_tr_t), key=lambda t: -(H_tr_t.get(t,(0,0))[1]))
    print(f"\nPer task_type TRAIN acc (n is train count):")
    print(f"  {'type':<35} {'n':>4}  HITL    Copilot  pick")
    routes = {}  # task_type -> 'H' or 'C'
    for t in types:
        h_a, h_n = H_tr_t.get(t,(0.0,0)); c_a, c_n = C_tr_t.get(t,(0.0,0))
        pick = "H" if h_a >= c_a else "C"  # tie -> HITL (slightly better overall)
        routes[t] = pick
        print(f"  {t:<35} {h_n:>4}  {h_a:.3f}   {c_a:.3f}    {pick}")

    # Apply router to TEST
    common_ids = set(H_te) & set(C_te)
    print(f"\nTest common ids: {len(common_ids)}")
    n_pick_H = n_pick_C = 0
    correct = 0
    per_type_test = defaultdict(lambda: [0,0])  # type -> [correct, total]
    routed_picks = []
    for iid in common_ids:
        tt = H_te[iid]["task_type"]
        # If task_type unseen in train (rare), default to HITL
        pick = routes.get(tt, "H")
        if pick == "H":
            hard = H_te[iid]["hard"]; n_pick_H += 1
        else:
            hard = C_te[iid]["hard"]; n_pick_C += 1
        correct += hard
        per_type_test[tt][0] += hard; per_type_test[tt][1] += 1
        routed_picks.append({"id": iid, "task_type": tt, "pick": pick, "hard": hard})

    router_acc = correct / max(1,len(common_ids))
    # Pure baselines on the same common set
    h_acc_common = sum(H_te[i]["hard"] for i in common_ids)/len(common_ids)
    c_acc_common = sum(C_te[i]["hard"] for i in common_ids)/len(common_ids)
    # Oracle per item (any-of-2)
    oracle = sum(max(H_te[i]["hard"], C_te[i]["hard"]) for i in common_ids)/len(common_ids)

    print(f"\n=== TEST RESULTS (n={len(common_ids)}) ===")
    print(f"  HITL only       : {h_acc_common:.4f}")
    print(f"  Copilot only    : {c_acc_common:.4f}")
    print(f"  Router (per-type): {router_acc:.4f}   (HITL chosen {n_pick_H}x, Copilot {n_pick_C}x)")
    print(f"  Oracle (any-of-2): {oracle:.4f}  (upper bound for 2-skill routing)")

    print(f"\nPer task_type TEST after routing:")
    print(f"  {'type':<35} pick  corr/n   acc")
    for t in sorted(per_type_test, key=lambda x: -per_type_test[x][1]):
        c,n = per_type_test[t]
        print(f"  {t:<35} {routes.get(t,'H'):<4} {c}/{n}      {c/max(1,n):.3f}")

    os.makedirs("outputs/routing_analysis", exist_ok=True)
    with open("outputs/routing_analysis/summary.json","w") as f:
        json.dump({
            "routes": routes,
            "test_n": len(common_ids),
            "hitl_only": h_acc_common,
            "copilot_only": c_acc_common,
            "router_acc": router_acc,
            "oracle": oracle,
            "n_pick_hitl": n_pick_H, "n_pick_copilot": n_pick_C,
        }, f, indent=2)
    with open("outputs/routing_analysis/per_item.jsonl","w") as f:
        for r in routed_picks: f.write(json.dumps(r)+"\n")
    print("\nSaved to outputs/routing_analysis/")


if __name__ == "__main__":
    main()
