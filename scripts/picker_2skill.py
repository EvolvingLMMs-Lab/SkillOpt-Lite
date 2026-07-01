#!/usr/bin/env python3
"""Picker agent: given a question and TWO candidate analyses (one from HITL
skill, one from Copilot skill), choose which one to trust.

We shuffle A/B per item to avoid positional bias, then map back. No own answer
is requested — the picker only votes for A or B.
"""
from __future__ import annotations
import argparse, json, os, sys, time, re, random, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from skillopt.model import (
    configure_azure_openai, set_target_backend, set_target_deployment,
    set_reasoning_effort, chat_target,
)

HITL_TEST = "outputs/livemath_hitl_optMED_centralus_20260601_015633/test_eval/results.jsonl"
COP_TEST  = "outputs/copilot_oneshot_v1_valid_unseen_20260601_090254/results.jsonl"
HITL_PRED_DIR = "outputs/livemath_hitl_optMED_centralus_20260601_015633/test_eval/predictions"
COP_PRED_DIR  = "outputs/copilot_oneshot_v1_valid_unseen_20260601_090254/predictions"

PICKER_SYSTEM = """You are an expert mathematical adjudicator.

You will see ONE research-level multiple-choice math question (5 options A–E) and TWO independent candidate analyses, labeled "Analysis A" and "Analysis B". Each analysis ends with a chosen option letter.

Your task: decide which of the two analyses is more trustworthy — that is, which one's chosen option is better supported by correct, careful reasoning about the actual theorem/setting in the question.

How to judge (in priority order):
1. Look for concrete, identifiable errors: quantifier flip (∀↔∃, "for all" ↔ "there exists"), scope flip ("whenever" ≠ "if and only if"), overstated regularity (e.g. continuous ⇒ differentiable), invented or dropped equality cases, subject swap (talking about the wrong object), unjustified class enlargement, mishandling of meta-option E ("none of the above" / "all of the above").
2. Prefer the analysis that explicitly checks the hypothesis on the actual claim, rather than one that reasons by analogy or vague intuition.
3. If both analyses arrive at the same option letter, prefer the one whose argument is more directly tied to the precise statement.
4. If both look bad, pick the LESS bad one — you must pick exactly one.

Do NOT compute your own answer. Do NOT explain at length. Do NOT compare reasoning styles unrelated to correctness.

Output ONLY one of:
<pick>A</pick>
<pick>B</pick>"""

USER_TPL = """{question_and_choices}

---

## Analysis A

{reasoning_A}

Final answer (A): **{label_A}**

---

## Analysis B

{reasoning_B}

Final answer (B): **{label_B}**

---

## Decision

Output ONLY `<pick>A</pick>` or `<pick>B</pick>`."""


def _trim(t, n=8000):
    t = (t or "").strip()
    if len(t) <= n: return t
    return t[:n//2] + "\n\n...[truncated for picker]...\n\n" + t[-n//2:]


def load(path):
    out = {}
    with open(path, errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: r = json.loads(ln)
            except Exception: continue
            iid = str(r["id"])
            out[iid] = {
                "task_type": r.get("task_type","UNK"),
                "hard": int(r.get("hard", int(r.get("predicted_label","")==r.get("correct_label","")))),
                "predicted_label": r.get("predicted_label","") or r.get("predicted_answer",""),
                "correct_label": r.get("correct_label",""),
                "response": r.get("response",""),
            }
    return out


def load_user_prompt(pred_dir, iid):
    p = os.path.join(pred_dir, iid, "target_user_prompt.txt")
    if os.path.exists(p):
        with open(p, errors="replace") as f: return f.read()
    return ""


def extract_pick(resp):
    m = re.search(r"<pick>\s*([AB])\s*</pick>", resp or "", re.IGNORECASE)
    if m: return m.group(1).upper()
    # fallback: last standalone A or B
    s = (resp or "").strip().upper()
    if s.endswith("A"): return "A"
    if s.endswith("B"): return "B"
    # crude heuristic
    if "PICK>A" in s.replace(" ",""): return "A"
    if "PICK>B" in s.replace(" ",""): return "B"
    return ""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None)
    p.add_argument("--workers", type=int, default=24)
    p.add_argument("--reasoning", default="medium")
    args = p.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or f"outputs/picker_2skill_{ts}"
    os.makedirs(out_dir, exist_ok=True)

    configure_azure_openai(
        endpoint=os.environ["TARGET_AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("TARGET_AZURE_OPENAI_API_VERSION","2024-12-01-preview"),
        auth_mode=os.environ.get("TARGET_AZURE_OPENAI_AUTH_MODE","azure_cli"),
    )
    set_target_backend("openai_chat")
    set_target_deployment("gpt-5.4")
    set_reasoning_effort(args.reasoning)

    H = load(HITL_TEST); C = load(COP_TEST)
    common = sorted(set(H) & set(C))
    print(f"[picker] common items: {len(common)}", flush=True)

    def _one(iid):
        h = H[iid]; c = C[iid]
        q = load_user_prompt(HITL_PRED_DIR, iid) or load_user_prompt(COP_PRED_DIR, iid)
        if not q:
            return iid, {"error":"no_question"}
        # deterministic shuffle by iid hash
        rng = random.Random(int(hashlib.md5(iid.encode()).hexdigest(),16) & 0xFFFFFFFF)
        a_is_hitl = rng.random() < 0.5
        if a_is_hitl:
            cand_A, cand_B = h, c
        else:
            cand_A, cand_B = c, h
        prompt = USER_TPL.format(
            question_and_choices=q.strip(),
            reasoning_A=_trim(cand_A["response"]),
            label_A=cand_A["predicted_label"] or "(none)",
            reasoning_B=_trim(cand_B["response"]),
            label_B=cand_B["predicted_label"] or "(none)",
        )
        try:
            resp, _ = chat_target(
                system=PICKER_SYSTEM, user=prompt,
                max_completion_tokens=4096, retries=3, stage="picker", timeout=240,
            )
        except Exception as e:
            return iid, {"error": f"call: {e}", "a_is_hitl": a_is_hitl}
        pick = extract_pick(resp)
        if pick not in ("A","B"):
            # default: pick A
            pick = "A"
            err = "no_pick_parsed"
        else:
            err = ""
        picked = cand_A if pick == "A" else cand_B
        picked_skill = "HITL" if (pick == "A") == a_is_hitl else "Copilot"
        return iid, {
            "id": iid,
            "task_type": h["task_type"],
            "a_is_hitl": a_is_hitl,
            "pick_AB": pick,
            "picked_skill": picked_skill,
            "picked_label": picked["predicted_label"],
            "correct_label": h["correct_label"],
            "picked_hard": int(picked["predicted_label"] == h["correct_label"]),
            "hitl_hard": h["hard"],
            "copilot_hard": c["hard"],
            "raw_response_tail": (resp or "")[-400:],
            "err": err,
        }

    results = {}
    t0 = time.time(); done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_one, iid): iid for iid in common}
        for fut in as_completed(futs):
            iid, rec = fut.result()
            results[iid] = rec
            done += 1
            if done % 10 == 0 or done == len(futs):
                ok = sum(1 for r in results.values() if r.get("picked_hard"))
                print(f"  [picker] {done}/{len(futs)} acc={ok/done:.3f} elapsed={time.time()-t0:.0f}s", flush=True)

    # Aggregate
    n = len(results)
    picker_correct = sum(r.get("picked_hard",0) for r in results.values())
    hitl_correct   = sum(r.get("hitl_hard",0) for r in results.values())
    cop_correct    = sum(r.get("copilot_hard",0) for r in results.values())
    oracle_correct = sum(max(r.get("hitl_hard",0), r.get("copilot_hard",0)) for r in results.values())

    n_hitl_pick = sum(1 for r in results.values() if r.get("picked_skill")=="HITL")
    n_cop_pick  = sum(1 for r in results.values() if r.get("picked_skill")=="Copilot")

    # Disagreement-only analysis: where HITL != Copilot label
    disagreements = [r for r in results.values() if (r.get("hitl_hard")!=r.get("copilot_hard")) or False]
    # better: by label disagreement; reload
    # Determine label disagreement directly from the loaded data
    disagr_ids = [iid for iid in results if H[iid]["predicted_label"] != C[iid]["predicted_label"]]
    n_disagr = len(disagr_ids)
    # On disagreements: how often picker picks the correct one?
    disagr_correct = 0
    disagr_oracle = 0
    for iid in disagr_ids:
        disagr_correct += results[iid].get("picked_hard",0)
        disagr_oracle += max(H[iid]["hard"], C[iid]["hard"])

    # Per task_type
    per_t = defaultdict(lambda: [0,0])
    for r in results.values():
        per_t[r.get("task_type","UNK")][0] += r.get("picked_hard",0)
        per_t[r.get("task_type","UNK")][1] += 1

    print(f"\n=== PICKER RESULT (n={n}) ===")
    print(f"  HITL only      : {hitl_correct/n:.4f}  ({hitl_correct}/{n})")
    print(f"  Copilot only   : {cop_correct/n:.4f}  ({cop_correct}/{n})")
    print(f"  Picker         : {picker_correct/n:.4f}  ({picker_correct}/{n})    picks HITL={n_hitl_pick}, Copilot={n_cop_pick}")
    print(f"  Oracle (any-of-2): {oracle_correct/n:.4f}  ({oracle_correct}/{n})")
    print(f"\nDisagreement subset (label differs): n={n_disagr}")
    if n_disagr:
        print(f"  picker correct on disagreements : {disagr_correct}/{n_disagr} = {disagr_correct/n_disagr:.3f}")
        print(f"  oracle correct on disagreements : {disagr_oracle}/{n_disagr} = {disagr_oracle/n_disagr:.3f}")
        print(f"  random-guess baseline on disagrs: ~0.500")

    print(f"\nPer task_type picker acc:")
    for t in sorted(per_t, key=lambda x: -per_t[x][1]):
        c, nn = per_t[t]
        print(f"  {t:<35} {c}/{nn}  {c/max(1,nn):.3f}")

    with open(os.path.join(out_dir,"picker_results.jsonl"),"w") as f:
        for iid in sorted(results):
            f.write(json.dumps(results[iid], ensure_ascii=False)+"\n")
    with open(os.path.join(out_dir,"summary.json"),"w") as f:
        json.dump({
            "n": n,
            "hitl_only": hitl_correct/n,
            "copilot_only": cop_correct/n,
            "picker": picker_correct/n,
            "oracle_2": oracle_correct/n,
            "n_pick_hitl": n_hitl_pick,
            "n_pick_copilot": n_cop_pick,
            "n_disagreement": n_disagr,
            "picker_acc_on_disagreement": disagr_correct/max(1,n_disagr),
            "oracle_on_disagreement": disagr_oracle/max(1,n_disagr),
            "reasoning_effort": args.reasoning,
        }, f, indent=2)
    print(f"\nSaved to {out_dir}/")


if __name__ == "__main__":
    main()
