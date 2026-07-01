#!/usr/bin/env python3
"""HITL v2 step 1: error attribution.

For each wrongly-answered TRAIN item under the current best HITL skill, ask a
reflector LLM (gpt-5.4 medium) to:
  1) name the SPECIFIC trap that the wrong reasoning fell into (short label),
  2) point at which existing skill rule SHOULD have caught it (rule name or "no rule covers"),
  3) propose a 1–2 sentence patch / new rule that would have caught it.

Then we cluster trap labels to find what's missing in the skill.
"""
from __future__ import annotations
import argparse, json, os, sys, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from skillopt.model import (
    configure_azure_openai, set_target_backend, set_target_deployment,
    set_reasoning_effort, chat_target,
)

HITL_TRAIN = "outputs/livemath_hitl_optMED_centralus_20260601_015633/steps/step_0005/selection_eval/results.jsonl"
HITL_PRED  = "outputs/livemath_hitl_optMED_centralus_20260601_015633/steps/step_0005/selection_eval/predictions"
SKILL_PATH = "outputs/livemath_hitl_optMED_centralus_20260601_015633/best_skill.md"

REFLECTOR_SYSTEM = """You are a meticulous mathematical-reasoning error analyst.

You will be given:
- The CURRENT SKILL document (a checklist used to answer research-level math multiple-choice questions),
- ONE question (with 5 options A–E),
- The WRONG analysis that the agent produced under this skill,
- The CORRECT answer letter and text.

Your job: produce a short, structured diagnosis. NO long prose.

Diagnose precisely:
1. trap_label — at most 5 words, a reusable category of error (e.g. "quantifier-flip-in-converse", "equality-case-dropped", "regularity-overstated-Holder-to-Lip", "meta-option-E-misapplied", "subject-swap-domain-to-image", "scope-flip-whenever-vs-iff", "class-enlargement-from-compact-to-closed").
   - Prefer a label that could match MULTIPLE errors across different questions.
2. rule_coverage — which existing rule/section of the skill SHOULD have caught it. Quote the exact section header or bullet from the skill (e.g. "Step 2 Pairwise strict ordering" or "Trap 7: bi-Lipschitz hierarchy"), OR write exactly "NO_RULE" if the skill has no rule that addresses this trap.
3. rule_failure_mode — pick exactly one:
   - "rule_exists_but_not_triggered" (skill has the rule, agent didn't apply it)
   - "rule_exists_but_too_vague" (rule there but doesn't pin down the action)
   - "rule_missing" (skill doesn't cover this trap)
4. patch — ONE concrete sentence the agent should follow to avoid this exact mistake. Phrased as an imperative rule that could be inserted into the skill. Be SPECIFIC (cite the math concept), not generic ("be careful").

Output as STRICT JSON:
{"trap_label": "...", "rule_coverage": "...", "rule_failure_mode": "...", "patch": "..."}

No prose, no markdown fences, just one JSON object."""

USER_TPL = """## CURRENT SKILL

{skill}

---

## QUESTION

{question_and_choices}

---

## AGENT'S WRONG ANALYSIS

{wrong_reasoning}

Agent's chosen option: **{picked_label}** ({picked_text})

---

## CORRECT ANSWER

**{correct_label}** ({correct_text})

---

Diagnose. Output the JSON object only."""


def _trim(t, n=10000):
    t = (t or "").strip()
    if len(t) <= n: return t
    return t[:n//2] + "\n\n...[truncated]...\n\n" + t[-n//2:]


def extract_json(s):
    if not s: return None
    # strip code fences if any
    s = re.sub(r"^```(?:json)?", "", s.strip(), flags=re.I)
    s = re.sub(r"```\s*$", "", s.strip())
    # find first { ... last }
    i = s.find("{"); j = s.rfind("}")
    if i < 0 or j < 0 or j < i: return None
    try: return json.loads(s[i:j+1])
    except Exception: return None


def load_user_prompt(iid):
    p = os.path.join(HITL_PRED, iid, "target_user_prompt.txt")
    if os.path.exists(p):
        with open(p, errors="replace") as f: return f.read()
    return ""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--reasoning", default="medium")
    args = p.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or f"outputs/hitl_v2_diagnose_{ts}"
    os.makedirs(out_dir, exist_ok=True)

    configure_azure_openai(
        endpoint=os.environ["TARGET_AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("TARGET_AZURE_OPENAI_API_VERSION","2024-12-01-preview"),
        auth_mode=os.environ.get("TARGET_AZURE_OPENAI_AUTH_MODE","azure_cli"),
    )
    set_target_backend("openai_chat")
    set_target_deployment("gpt-5.4")
    set_reasoning_effort(args.reasoning)

    with open(SKILL_PATH) as f: skill = f.read()
    rows = [json.loads(l) for l in open(HITL_TRAIN, errors="replace")]
    wrong = [r for r in rows if not r.get("hard")]
    print(f"[diagnose] train n={len(rows)}  wrong={len(wrong)}", flush=True)

    def _one(r):
        iid = str(r["id"])
        q = load_user_prompt(iid)
        if not q:
            return iid, {"id": iid, "error": "no_question"}
        prompt = USER_TPL.format(
            skill=skill,
            question_and_choices=q.strip(),
            wrong_reasoning=_trim(r.get("response","")),
            picked_label=r.get("predicted_label",""),
            picked_text=r.get("predicted_text",""),
            correct_label=r.get("correct_label",""),
            correct_text=r.get("correct_text",""),
        )
        try:
            resp, _ = chat_target(
                system=REFLECTOR_SYSTEM, user=prompt,
                max_completion_tokens=2048, retries=3, stage="diagnose", timeout=240,
            )
        except Exception as e:
            return iid, {"id": iid, "error": f"call: {e}"}
        obj = extract_json(resp)
        if not obj:
            return iid, {"id": iid, "raw": (resp or "")[-400:], "error": "no_json"}
        obj["id"] = iid
        obj["task_type"] = r.get("task_type","UNK")
        obj["picked_label"] = r.get("predicted_label","")
        obj["correct_label"] = r.get("correct_label","")
        return iid, obj

    results = {}; t0 = time.time(); done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_one, r): str(r["id"]) for r in wrong}
        for fut in as_completed(futs):
            iid, rec = fut.result()
            results[iid] = rec
            done += 1
            if done % 5 == 0 or done == len(futs):
                print(f"  [diagnose] {done}/{len(futs)} elapsed={time.time()-t0:.0f}s", flush=True)

    # Save raw
    with open(os.path.join(out_dir,"diagnoses.jsonl"),"w") as f:
        for iid in sorted(results):
            f.write(json.dumps(results[iid], ensure_ascii=False)+"\n")

    ok = [r for r in results.values() if not r.get("error")]
    err = [r for r in results.values() if r.get("error")]
    print(f"\n[diagnose] parsed ok={len(ok)} errors={len(err)}")

    # Cluster by trap_label (normalize lower + strip)
    def norm(s): return re.sub(r"\s+","-",(s or "").strip().lower()).strip("-")
    trap_counts = Counter(norm(r.get("trap_label","")) for r in ok)
    mode_counts = Counter(r.get("rule_failure_mode","UNK") for r in ok)
    rule_counts = Counter((r.get("rule_coverage") or "NO_RULE").strip() for r in ok)

    print(f"\n=== Top trap labels (n={len(ok)} diagnosed errors) ===")
    for lbl, c in trap_counts.most_common(20):
        print(f"  {c:>3}  {lbl}")
    print(f"\n=== Rule failure mode ===")
    for m, c in mode_counts.most_common():
        print(f"  {c:>3}  {m}")
    print(f"\n=== Top rule_coverage citations (where rule was supposed to help) ===")
    for r, c in rule_counts.most_common(15):
        print(f"  {c:>3}  {r[:80]}")

    # Save aggregated
    agg = {
        "n_wrong": len(wrong),
        "n_diagnosed": len(ok),
        "n_errors": len(err),
        "trap_label_counts": dict(trap_counts),
        "rule_failure_mode_counts": dict(mode_counts),
        "rule_coverage_counts": dict(rule_counts),
    }
    with open(os.path.join(out_dir,"aggregated.json"),"w") as f:
        json.dump(agg, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_dir}/")


if __name__ == "__main__":
    main()
