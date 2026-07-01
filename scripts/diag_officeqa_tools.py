"""Inspect OfficeQA rollouts to see if tool use is the bottleneck."""
import json
import re
import sys
from collections import Counter
from pathlib import Path


def analyze_conversation(conv_path: Path) -> dict:
    """Extract tool-call stats from a single conversation.json."""
    msgs = json.loads(conv_path.read_text())
    tool_calls = Counter()
    tool_results = []
    text_search_queries = []
    final_answer = ""
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content", "")
        if role == "assistant":
            if isinstance(content, str):
                # extract <search_queries>...</search_queries> tags
                for s in re.findall(r"<search_queries>(.*?)</search_queries>", content, re.DOTALL | re.IGNORECASE):
                    text_search_queries.append(s.strip()[:200])
                m_ans = re.search(r"<answer>(.*?)</answer>", content, re.DOTALL | re.IGNORECASE)
                if m_ans:
                    final_answer = m_ans.group(1).strip()
            for tc in m.get("tool_calls") or []:
                fn = (tc.get("function") or {}).get("name") or tc.get("name") or "?"
                tool_calls[fn] += 1
        elif role == "tool":
            content_str = str(content)[:200]
            tool_results.append(content_str)
    return {
        "tool_calls": dict(tool_calls),
        "n_tool_results": len(tool_results),
        "n_search_queries": len(text_search_queries),
        "final_answer": final_answer[:160],
    }


def scan(out_root: str, label: str, only_wrong: bool = True, sample: int = 10):
    test_dir = Path(out_root) / "test_eval"
    results = [json.loads(l) for l in (test_dir / "results.jsonl").read_text().splitlines() if l.strip()]
    pred_dir = test_dir / "predictions"
    print(f"\n=== {label} ===")
    print(f"  rollouts: {len(results)}")

    # Aggregate tool usage across ALL rollouts
    total_calls = Counter()
    no_tool_rollouts = 0
    rollouts_by_pattern = []
    convo_files = list(pred_dir.rglob("conversation.json"))
    if not convo_files:
        print(f"  [no conversation.json in {pred_dir}]")
        return
    # Build id -> convo path
    id_to_convo = {}
    for cp in convo_files:
        # parent dir name is UIDxxxx
        uid = cp.parent.name
        id_to_convo[uid] = cp

    for r in results:
        uid = r.get("id") or r.get("uid")
        cp = id_to_convo.get(uid)
        if cp is None:
            continue
        try:
            info = analyze_conversation(cp)
        except Exception as e:
            continue
        for k, v in info["tool_calls"].items():
            total_calls[k] += v
        if not info["tool_calls"] and info["n_search_queries"] == 0:
            no_tool_rollouts += 1
        rollouts_by_pattern.append((r, info))

    print(f"  total tool calls (across all rollouts): {dict(total_calls)}")
    print(f"  rollouts with 0 tool/search activity: {no_tool_rollouts}/{len(results)}")

    # Avg tool calls for PASS vs FAIL
    pass_calls = [sum(info['tool_calls'].values()) for r, info in rollouts_by_pattern if r['hard']]
    fail_calls = [sum(info['tool_calls'].values()) for r, info in rollouts_by_pattern if not r['hard']]
    if pass_calls:
        print(f"  avg tool calls for PASS ({len(pass_calls)} items): {sum(pass_calls)/len(pass_calls):.2f}")
    if fail_calls:
        print(f"  avg tool calls for FAIL ({len(fail_calls)} items): {sum(fail_calls)/len(fail_calls):.2f}")

    # Sample some FAILed rollouts, show tool pattern
    print(f"\n  --- sample {sample} FAILED rollouts ---")
    fail_rollouts = [(r, info) for r, info in rollouts_by_pattern if not r['hard']]
    for r, info in fail_rollouts[:sample]:
        print(f"  [{r['id']}] pred={info['final_answer'][:80]!r}  gold={r['ground_truth'][:60]!r}")
        print(f"           tool_calls={info['tool_calls']}  text_search_queries={info['n_search_queries']}")

    # Look at sample of PASSed rollouts to see "what works"
    pass_rollouts = [(r, info) for r, info in rollouts_by_pattern if r['hard']]
    print(f"\n  --- sample 5 PASSED rollouts ---")
    for r, info in pass_rollouts[:5]:
        print(f"  [{r['id']}] pred={info['final_answer'][:60]!r}  gold={r['ground_truth'][:40]!r}")
        print(f"           tool_calls={info['tool_calls']}")


if __name__ == "__main__":
    for out, lab in (
        ("outputs/skillopt_officeqa_gpt-5.4-mini_2026-03-17_20260610_105741", "MINI test"),
        ("outputs/skillopt_officeqa_gpt-5.4-nano_2026-03-17_20260610_093325", "NANO test"),
    ):
        scan(out, lab)
