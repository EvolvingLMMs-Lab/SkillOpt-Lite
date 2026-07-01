#!/usr/bin/env python3
"""Verifier-SC: independent fresh-context verifier judges 3 candidate analyses.

Loads each sample dir's predictions/<id>/target_user_prompt.txt (which already
contains the formatted Question + Choices) and the response from results.jsonl.
Presents 3 candidate analyses anonymously, in randomized order, to a
fresh-context gpt-5.4-medium verifier with no skill prompt.
"""
from __future__ import annotations
import argparse, json, os, sys, random, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from skillopt.model import (
    configure_azure_openai, set_target_backend, set_target_deployment,
    set_reasoning_effort, chat_target,
)

VERIFIER_SYSTEM = """You are an independent mathematical verifier.

You will see a research-level multiple-choice math question (5 options A-E) and three independent candidate analyses produced by separate attempts. Each candidate has a reasoning trace and a final answer label.

The candidates may all be wrong. Do NOT count votes and do not trust any candidate by default. Critically read each candidate's reasoning and independently decide which option (A-E) is best supported by the stated theorem/setting. Watch for: quantifier slips, scope flips across implications, overstated regularity, missing or invented equality cases, subject swaps (claim about a derived/restricted object), and unjustified class enlargements.

Output ONLY your final choice as `<answer>X</answer>` where X in {A, B, C, D, E}. No prose after the answer tag."""

VERIFIER_USER_TEMPLATE = """{question_and_choices}

## Candidate analyses (independent attempts; any may be wrong)

{candidates_block}

## Task
Independently determine which option (A-E) is best supported. Output ONLY `<answer>X</answer>`."""


def _trim(text, max_chars=6000):
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars // 2] + "\n\n...[truncated]...\n\n" + t[-max_chars // 2 :]


def extract_label(response):
    valid = {"A","B","C","D","E"}
    m = re.search(r"<answer>\s*([A-E])\s*</answer>", response or "", re.IGNORECASE)
    if m:
        return m.group(1).upper()
    for ch in reversed((response or "").strip().split()):
        cu = ch.strip(".,;:()[]<>{}*`").upper()
        if cu in valid:
            return cu
    return ""


def load_sample_dir(d):
    out = {}
    rj = os.path.join(d, "results.jsonl")
    if not os.path.exists(rj):
        return out
    with open(rj, errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            iid = str(r["id"])
            up_path = os.path.join(d, "predictions", iid, "target_user_prompt.txt")
            user_prompt = ""
            if os.path.exists(up_path):
                with open(up_path, errors="replace") as g:
                    user_prompt = g.read()
            out[iid] = {
                "response": r.get("response", ""),
                "predicted_label": r.get("predicted_label", "") or r.get("predicted_answer", ""),
                "correct_label": r.get("correct_label", ""),
                "user_prompt": user_prompt,
            }
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--samples", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--seed", type=int, default=2025)
    args = p.parse_args()

    configure_azure_openai(
        endpoint=os.environ["TARGET_AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("TARGET_AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        auth_mode=os.environ.get("TARGET_AZURE_OPENAI_AUTH_MODE", "azure_cli"),
    )
    set_target_backend("openai_chat")
    set_target_deployment("gpt-5.4")
    set_reasoning_effort("medium")

    sample_data = [load_sample_dir(d) for d in args.samples]
    for i, (d, s) in enumerate(zip(args.samples, sample_data)):
        print(f"  sample {i+1} ({d}): {len(s)} items")
    common = sorted(set.intersection(*[set(s) for s in sample_data]))
    print(f"[verifier-sc] common items: {len(common)}")

    os.makedirs(args.out, exist_ok=True)

    def _verify(iid):
        base = sample_data[0][iid]
        if not base["user_prompt"]:
            return iid, "", "MISSING_USER_PROMPT"
        cands = [(s[iid]["response"], s[iid]["predicted_label"]) for s in sample_data]
        rng_local = random.Random(args.seed + (hash(iid) & 0xFFFFFF))
        order = list(range(len(cands)))
        rng_local.shuffle(order)
        shuffled = [cands[i] for i in order]
        blocks = []
        for i, (reasoning, label) in enumerate(shuffled, 1):
            blocks.append(
                f"### Candidate {i}\n"
                f"Reasoning:\n{_trim(reasoning)}\n\n"
                f"Final answer: {label or '(no label)'}"
            )
        prompt = VERIFIER_USER_TEMPLATE.format(
            question_and_choices=base["user_prompt"].strip(),
            candidates_block="\n\n---\n\n".join(blocks),
        )
        try:
            resp, _ = chat_target(
                system=VERIFIER_SYSTEM, user=prompt,
                max_completion_tokens=16384, retries=3, stage="verifier", timeout=300,
            )
        except Exception as e:
            return iid, "", f"error: {e}"
        return iid, extract_label(resp), resp

    results = {}
    t0 = time.time()
    correct = 0
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_verify, iid): iid for iid in common}
        for fut in as_completed(futs):
            iid, pred, _ = fut.result()
            cor = sample_data[0][iid]["correct_label"]
            ok = (pred == cor)
            cand_labels = [sample_data[i][iid]["predicted_label"] for i in range(len(sample_data))]
            cand_hits = [int(l == cor) for l in cand_labels]
            results[iid] = {
                "id": iid, "verifier_pred": pred, "correct_label": cor,
                "hard": int(ok),
                "candidate_labels": cand_labels, "candidate_hits": cand_hits,
            }
            done += 1
            if ok: correct += 1
            if done % 10 == 0 or done == len(futs):
                print(f"  [verifier] {done}/{len(futs)}  acc={correct/done:.4f}  elapsed={time.time()-t0:.0f}s", flush=True)

    final = sum(r["hard"] for r in results.values()) / len(results) if results else 0.0
    print(f"\n[verifier-sc] FINAL hard={final:.4f}  n={len(results)}")

    with open(os.path.join(args.out, "verifier_results.jsonl"), "w") as f:
        for iid in sorted(results):
            f.write(json.dumps(results[iid], ensure_ascii=False) + "\n")
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({"hard": final, "n": len(results), "samples": args.samples}, f, indent=2)


if __name__ == "__main__":
    main()
