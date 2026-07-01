#!/usr/bin/env python3
"""Verifier-as-gate: judge a single (question, candidate) as ACCEPT or REJECT.

Iterative protocol (simulated by post-hoc reuse of pre-computed sample dirs):
  for k in 1..K:
    cand_k = generator(seed=k)  [already computed offline]
    verdict_k = verifier(question, cand_k)   <-- this script
    if verdict_k == ACCEPT: return cand_k
  return cand_K

This script runs verifier on every (item, sample) pair independently so the
acceptance simulation can be done from saved verdicts.
"""
from __future__ import annotations
import argparse, json, os, sys, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from skillopt.model import (
    configure_azure_openai, set_target_backend, set_target_deployment,
    set_reasoning_effort, chat_target,
)

VERIFIER_SYSTEM = """You are an independent mathematical verifier.

You will see a research-level multiple-choice math question (5 options A-E) and ONE candidate analysis produced by a previous attempt. The candidate may be wrong.

Your job is NOT to give your own answer. Your job is to AUDIT the candidate and decide whether to ACCEPT or REJECT it.

ACCEPT means: the candidate's chosen option is well-justified by the stated theorem/setting, the reasoning has no obvious quantifier slip, scope flip, overstated regularity, missing/invented equality case, subject swap, or unjustified class enlargement, and the meta-option (E) is handled correctly.

REJECT means: there is at least one specific identifiable error in the reasoning, OR the candidate seems to converge on the wrong option, OR the reasoning is too vague to verify.

When in doubt, REJECT. It is cheaper to ask for a retry than to accept a flawed answer.

Output ONLY:
<verdict>ACCEPT</verdict>
or
<verdict>REJECT</verdict>
No prose, no answer letter, no critique."""

USER_TPL = """{question_and_choices}

## Candidate analysis (may be wrong)

Reasoning:
{reasoning}

Final answer: {label}

## Task
Output ONLY `<verdict>ACCEPT</verdict>` or `<verdict>REJECT</verdict>`."""


def _trim(t, n=8000):
    t = (t or "").strip()
    if len(t) <= n: return t
    return t[:n//2] + "\n\n...[truncated]...\n\n" + t[-n//2:]


def extract_verdict(response):
    m = re.search(r"<verdict>\s*(ACCEPT|REJECT)\s*</verdict>", response or "", re.IGNORECASE)
    if m: return m.group(1).upper()
    s = (response or "").upper()
    if "ACCEPT" in s and "REJECT" not in s: return "ACCEPT"
    if "REJECT" in s and "ACCEPT" not in s: return "REJECT"
    return "REJECT"  # default cautious


def load_sample_dir(d):
    out = {}
    rj = os.path.join(d, "results.jsonl")
    if not os.path.exists(rj): return out
    with open(rj, errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: r = json.loads(ln)
            except Exception: continue
            iid = str(r["id"])
            up = os.path.join(d, "predictions", iid, "target_user_prompt.txt")
            user_prompt = ""
            if os.path.exists(up):
                with open(up, errors="replace") as g: user_prompt = g.read()
            out[iid] = {
                "response": r.get("response",""),
                "predicted_label": r.get("predicted_label","") or r.get("predicted_answer",""),
                "correct_label": r.get("correct_label",""),
                "user_prompt": user_prompt,
            }
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=32)
    args = p.parse_args()

    configure_azure_openai(
        endpoint=os.environ["TARGET_AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("TARGET_AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        auth_mode=os.environ.get("TARGET_AZURE_OPENAI_AUTH_MODE", "azure_cli"),
    )
    set_target_backend("openai_chat")
    set_target_deployment("gpt-5.4")
    set_reasoning_effort("medium")

    data = load_sample_dir(args.sample)
    print(f"[gate] sample={args.sample} items={len(data)}", flush=True)
    os.makedirs(args.out, exist_ok=True)

    def _judge(iid):
        r = data[iid]
        if not r["user_prompt"]: return iid, "REJECT", "MISSING"
        prompt = USER_TPL.format(
            question_and_choices=r["user_prompt"].strip(),
            reasoning=_trim(r["response"]),
            label=r["predicted_label"] or "(no label)",
        )
        try:
            resp, _ = chat_target(
                system=VERIFIER_SYSTEM, user=prompt,
                max_completion_tokens=4096, retries=3, stage="gate", timeout=180,
            )
        except Exception as e:
            return iid, "REJECT", f"error: {e}"
        return iid, extract_verdict(resp), resp

    results = {}
    t0 = time.time(); done = 0; n_acc = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_judge, iid): iid for iid in data}
        for fut in as_completed(futs):
            iid, verdict, _ = fut.result()
            r = data[iid]
            cand_ok = int(r["predicted_label"] == r["correct_label"])
            results[iid] = {
                "id": iid, "verdict": verdict,
                "candidate_label": r["predicted_label"], "correct_label": r["correct_label"],
                "candidate_hard": cand_ok,
            }
            done += 1
            if verdict == "ACCEPT": n_acc += 1
            if done % 20 == 0 or done == len(futs):
                print(f"  [gate] {done}/{len(futs)}  accept_rate={n_acc/done:.3f}  elapsed={time.time()-t0:.0f}s", flush=True)

    # Calibration: among ACCEPTed, how many were actually correct?
    acc_corr = sum(1 for r in results.values() if r["verdict"]=="ACCEPT" and r["candidate_hard"])
    rej_corr = sum(1 for r in results.values() if r["verdict"]=="REJECT" and r["candidate_hard"])
    acc_n = sum(1 for r in results.values() if r["verdict"]=="ACCEPT")
    rej_n = sum(1 for r in results.values() if r["verdict"]=="REJECT")
    print(f"\n[gate] FINAL")
    print(f"  ACCEPT n={acc_n}, of those correct={acc_corr} (precision={acc_corr/max(1,acc_n):.3f})")
    print(f"  REJECT n={rej_n}, of those correct={rej_corr} (would-have-kept-wrongly rate={rej_corr/max(1,rej_n):.3f})")

    with open(os.path.join(args.out, "gate_verdicts.jsonl"), "w") as f:
        for iid in sorted(results):
            f.write(json.dumps(results[iid], ensure_ascii=False)+"\n")
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({
            "n": len(results),
            "n_accept": acc_n, "n_reject": rej_n,
            "accept_precision_correct": acc_corr/max(1,acc_n),
            "reject_kept_correct_rate": rej_corr/max(1,rej_n),
        }, f, indent=2)


if __name__ == "__main__":
    main()
