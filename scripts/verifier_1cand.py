#!/usr/bin/env python3
"""1-candidate verifier: verifier sees question + 1 candidate analysis and
independently decides the final label. Tests whether a fresh-context verifier
can correct a single noisy candidate.
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

Do NOT trust the candidate by default. Critically read its reasoning and independently decide which option (A-E) is best supported by the stated theorem/setting. Watch for: quantifier slips, scope flips across implications, overstated regularity, missing or invented equality cases, subject swaps, unjustified class enlargements, and meta-option (E) misuse.

Output ONLY your final choice as `<answer>X</answer>` where X in {A, B, C, D, E}. No prose after the answer tag."""

USER_TPL = """{question_and_choices}

## Candidate analysis (may be wrong)

Reasoning:
{reasoning}

Final answer: {label}

## Task
Independently determine which option (A-E) is best supported. Output ONLY `<answer>X</answer>`."""


def _trim(t, n=8000):
    t = (t or "").strip()
    if len(t) <= n: return t
    return t[:n//2] + "\n\n...[truncated]...\n\n" + t[-n//2:]


def extract_label(response):
    m = re.search(r"<answer>\s*([A-E])\s*</answer>", response or "", re.IGNORECASE)
    if m: return m.group(1).upper()
    valid = {"A","B","C","D","E"}
    for ch in reversed((response or "").split()):
        cu = ch.strip(".,;:()[]<>{}*`").upper()
        if cu in valid: return cu
    return ""


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
    p.add_argument("--sample", required=True, help="single sample dir")
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
    print(f"[verifier-1cand] sample={args.sample} items={len(data)}")
    os.makedirs(args.out, exist_ok=True)

    def _verify(iid):
        r = data[iid]
        if not r["user_prompt"]:
            return iid, "", "MISSING"
        prompt = USER_TPL.format(
            question_and_choices=r["user_prompt"].strip(),
            reasoning=_trim(r["response"]),
            label=r["predicted_label"] or "(no label)",
        )
        try:
            resp, _ = chat_target(
                system=VERIFIER_SYSTEM, user=prompt,
                max_completion_tokens=16384, retries=3, stage="verifier1", timeout=300,
            )
        except Exception as e:
            return iid, "", f"error: {e}"
        return iid, extract_label(resp), resp

    results = {}
    t0 = time.time(); correct = 0; done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_verify, iid): iid for iid in data}
        for fut in as_completed(futs):
            iid, pred, _ = fut.result()
            r = data[iid]
            cor = r["correct_label"]
            cand_label = r["predicted_label"]
            ok = (pred == cor); cand_ok = (cand_label == cor)
            results[iid] = {
                "id": iid, "verifier_pred": pred, "candidate_pred": cand_label,
                "correct_label": cor, "hard": int(ok), "candidate_hard": int(cand_ok),
                "agree_with_candidate": int(pred == cand_label and pred != ""),
            }
            done += 1
            if ok: correct += 1
            if done % 10 == 0 or done == len(futs):
                print(f"  [verifier1] {done}/{len(futs)} acc={correct/done:.4f} elapsed={time.time()-t0:.0f}s", flush=True)

    final = sum(r["hard"] for r in results.values())/len(results) if results else 0.0
    cand_final = sum(r["candidate_hard"] for r in results.values())/len(results) if results else 0.0
    n_agree = sum(r["agree_with_candidate"] for r in results.values())
    # transitions
    cw_kw=sum(1 for r in results.values() if r["candidate_hard"] and r["hard"])
    cw_kl=sum(1 for r in results.values() if r["candidate_hard"] and not r["hard"])
    cl_kw=sum(1 for r in results.values() if not r["candidate_hard"] and r["hard"])
    cl_kl=sum(1 for r in results.values() if not r["candidate_hard"] and not r["hard"])
    print(f"\n[verifier-1cand] FINAL verifier={final:.4f}  candidate_only={cand_final:.4f}  agreement={n_agree}/{len(results)}")
    print(f"  transitions: cand_correct&ver_correct={cw_kw}  cand_correct&ver_wrong={cw_kl}  cand_wrong&ver_correct={cl_kw}  cand_wrong&ver_wrong={cl_kl}")

    with open(os.path.join(args.out, "verifier_results.jsonl"), "w") as f:
        for iid in sorted(results):
            f.write(json.dumps(results[iid], ensure_ascii=False)+"\n")
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({"verifier_hard": final, "candidate_hard": cand_final, "n": len(results),
                   "agreement": n_agree,
                   "cand_correct_verifier_correct": cw_kw,
                   "cand_correct_verifier_wrong": cw_kl,
                   "cand_wrong_verifier_correct": cl_kw,
                   "cand_wrong_verifier_wrong": cl_kl}, f, indent=2)


if __name__ == "__main__":
    main()
