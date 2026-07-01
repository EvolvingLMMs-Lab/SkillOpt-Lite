#!/usr/bin/env python3
"""make_samples.py — convert SkillOpt run outputs into .skillopt/samples/*.md.

Reads a `results.jsonl` (from `skillopt/envs/<env>/evaluator.py` outputs) and
writes one markdown file per row under a target workspace, in the layout the
SkillOpt VS Code plugin expects:

    <workspace>/.skillopt/samples/failed/<id>.md
    <workspace>/.skillopt/samples/passed/<id>.md

Each file is markdown + YAML frontmatter — diff-friendly, Copilot-readable.

Usage
-----
    python make_samples.py \\
        --results /path/to/test_eval/results.jsonl \\
        --workspace /tmp/my_agent_repo \\
        --env livemath \\
        [--limit 50] [--only failed|passed|both]

The script is intentionally schema-tolerant: it tries common SkillOpt fields
(question, predicted_text, correct_text, hard, soft, fail_reason, ...) and
falls back gracefully if some are missing — so it also works for searchqa
and alfworld results with minimal extra logic.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize_id(raw: Any) -> str:
    s = str(raw) if raw is not None else "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:80]


def _truncate(s: str, n: int = 4000) -> str:
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    if len(s) <= n:
        return s
    return s[:n] + f"\n\n...[truncated {len(s) - n} chars]"


def _score(row: dict) -> float:
    for k in ("hard", "score", "soft", "reward"):
        v = row.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _status(row: dict, env: str) -> str:
    s = _score(row)
    # alfworld uses 'success'; searchqa/livemath use 'hard'
    if env == "alfworld" and "success" in row:
        return "passed" if bool(row["success"]) else "failed"
    # spreadsheetbench: hard is 0/1 (all cases pass), soft is fraction of cases pass
    if env == "spreadsheetbench":
        return "passed" if int(row.get("hard", 0)) >= 1 else "failed"
    return "passed" if s >= 0.5 else "failed"


def _input_field(row: dict, env: str) -> str:
    if env == "alfworld":
        for k in ("task", "goal", "task_description", "instruction"):
            if row.get(k):
                return str(row[k])
    if env == "searchqa":
        q = row.get("question", "")
        ctx = row.get("context") or row.get("passages") or ""
        if ctx:
            return f"{q}\n\n## Context\n{_truncate(ctx, 2000)}"
        return q
    if env == "spreadsheetbench":
        instr = row.get("task_description") or row.get("instruction", "")
        itype = row.get("instruction_type", "")
        ttype = row.get("task_type", "")
        n_cases = row.get("n_cases", "?")
        bits = [str(instr)]
        meta = [f"task_type={ttype}", f"instruction_type={itype}", f"n_cases={n_cases}"]
        bits.append("\n_meta_: " + ", ".join(m for m in meta if m and not m.endswith("=")))
        return "\n".join(bits)
    if env == "officeqa":
        q = row.get("question", "")
        ttype = row.get("task_type", "")
        srcs = row.get("source_files") or row.get("resolved_source_paths") or []
        if isinstance(srcs, str):
            srcs = [srcs]
        oracle_chars = row.get("oracle_parsed_pages_chars", 0)
        bits = [str(q)]
        meta = [
            f"task_type={ttype}" if ttype else "",
            f"n_sources={len(srcs)}",
            f"oracle_chars={oracle_chars}",
        ]
        bits.append("\n_meta_: " + ", ".join(m for m in meta if m))
        if srcs:
            shown = ", ".join(str(s).split("/")[-1] for s in srcs[:4])
            more = f" (+{len(srcs) - 4} more)" if len(srcs) > 4 else ""
            bits.append(f"_sources_: {shown}{more}")
        return "\n".join(bits)
    if env == "docvqa":
        q = row.get("question", "")
        ttype = row.get("task_type", "") or row.get("subtask", "")
        imgs = row.get("image_paths") or ([] if not row.get("image_path") else [row["image_path"]])
        if isinstance(imgs, str):
            imgs = [imgs]
        bits = [str(q)]
        meta = [f"task_type={ttype}" if ttype else "", f"n_images={len(imgs)}"]
        bits.append("\n_meta_: " + ", ".join(m for m in meta if m))
        if imgs:
            shown = ", ".join(str(s).split("/")[-1] for s in imgs[:4])
            more = f" (+{len(imgs) - 4} more)" if len(imgs) > 4 else ""
            bits.append(f"_images_: {shown}{more}")
        return "\n".join(bits)
    # default / livemath
    return str(row.get("question", ""))


def _expected_field(row: dict, env: str) -> str:
    if env == "docvqa":
        ga = row.get("gold_answer")
        if isinstance(ga, list) and ga:
            return " | ".join(str(x) for x in ga)
        if isinstance(ga, str) and ga:
            return ga
    for k in ("correct_text", "answer", "gold", "expected", "correct_label", "ground_truth"):
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _output_field(row: dict) -> str:
    for k in ("predicted_text", "predicted_answer", "response", "output", "prediction", "agent_output"):
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _trace_field(row: dict) -> str:
    """Long trajectory dumps — wrap in <details> so Copilot doesn't waste tokens."""
    for k in ("trajectory", "trace", "turns", "messages"):
        v = row.get(k)
        if v in (None, ""):
            continue
        if isinstance(v, str):
            text = v
        else:
            text = json.dumps(v, indent=2, ensure_ascii=False)
        return text
    return ""


def _spreadsheet_trace(row: dict, results_path: Path) -> str:
    """For spreadsheetbench/officeqa: load conversation.json from
    out_root/predictions/<id>/. Same layout — reuse for both envs."""
    task_id = str(row.get("id", ""))
    if not task_id:
        return ""
    out_root = results_path.parent
    conv = out_root / "predictions" / task_id / "conversation.json"
    if not conv.exists():
        return ""
    try:
        return conv.read_text(encoding="utf-8")
    except OSError:
        return ""


def _tags(row: dict, env: str) -> list[str]:
    tags = []
    if env == "livemath":
        if row.get("task_type"):
            tags.append(str(row["task_type"]))
    if env == "spreadsheetbench":
        ttype = row.get("task_type")
        if ttype:
            tags.append(str(ttype))
        phase = row.get("phase")
        if phase and phase not in ("agent", "setup"):
            tags.append(_sanitize_id(phase)[:30])
    if env == "officeqa":
        ttype = row.get("task_type")
        if ttype:
            tags.append(str(ttype))  # easy / medium / hard
        if row.get("use_local_tools"):
            tags.append("local_tools")
        if not row.get("agent_ok", True):
            tags.append("agent_failed")
    if env == "docvqa":
        ttype = row.get("task_type") or row.get("subtask")
        if ttype:
            # topic strings can contain '|' or '/'; sanitize for tag use
            tags.append(_sanitize_id(str(ttype))[:40])
        if not row.get("agent_ok", True):
            tags.append("agent_failed")
    if row.get("fail_reason"):
        tags.append(_sanitize_id(row["fail_reason"])[:30])
    return tags


# ── Core ─────────────────────────────────────────────────────────────────────

def row_to_md(row: dict, env: str, results_path: Path | None = None) -> tuple[str, str]:
    """Return (status, markdown_text)."""
    sid = _sanitize_id(row.get("id") or row.get("idx") or row.get("uid") or "noid")
    status = _status(row, env)
    score = _score(row)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tags = _tags(row, env)

    front = [
        "---",
        f"id: {sid}",
        f"status: {status}",
        f"score: {score}",
        f"timestamp: {ts}",
        f"env: {env}",
    ]
    if tags:
        front.append(f"tags: [{', '.join(tags)}]")
    front.append("---")

    body = [
        f"# Sample {sid} — {status.upper()} (env={env}, score={score})",
        "",
        "## Input",
        _truncate(_input_field(row, env), 4000),
        "",
        "## Expected",
        _truncate(_expected_field(row, env), 1500),
        "",
        "## Agent output",
        _truncate(_output_field(row), 4000),
    ]
    trace = _trace_field(row)
    if not trace and env in ("spreadsheetbench", "officeqa") and results_path is not None:
        trace = _spreadsheet_trace(row, results_path)
    if trace:
        body += [
            "",
            "## Trace",
            "<details>",
            "<summary>Full trajectory</summary>",
            "",
            "```",
            _truncate(trace, 8000),
            "```",
            "</details>",
        ]
    fail = row.get("fail_reason")
    if fail:
        body += ["", "## Notes", f"`fail_reason`: {fail}"]
    return status, "\n".join(front) + "\n\n" + "\n".join(body) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="Path to results.jsonl")
    ap.add_argument("--workspace", required=True, help="Target workspace root")
    ap.add_argument("--env", required=True, choices=["livemath", "searchqa", "alfworld", "spreadsheetbench", "officeqa", "docvqa"])
    ap.add_argument("--limit", type=int, default=0, help="Max samples (0=all)")
    ap.add_argument("--only", choices=["failed", "passed", "both"], default="both")
    args = ap.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        sys.exit(f"results not found: {results_path}")

    ws = Path(args.workspace)
    failed_dir = ws / ".skillopt" / "samples" / "failed"
    passed_dir = ws / ".skillopt" / "samples" / "passed"
    failed_dir.mkdir(parents=True, exist_ok=True)
    passed_dir.mkdir(parents=True, exist_ok=True)

    n_written = {"failed": 0, "passed": 0, "skipped": 0}
    with results_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                n_written["skipped"] += 1
                continue
            status, text = row_to_md(row, args.env, results_path)
            if args.only != "both" and status != args.only:
                continue
            out_dir = failed_dir if status == "failed" else passed_dir
            sid = _sanitize_id(row.get("id") or "noid")
            (out_dir / f"{sid}.md").write_text(text, encoding="utf-8")
            n_written[status] += 1
            total = n_written["failed"] + n_written["passed"]
            if args.limit and total >= args.limit:
                break

    print(f"Wrote: failed={n_written['failed']} passed={n_written['passed']} skipped={n_written['skipped']}")
    print(f"Target: {ws}/.skillopt/samples/")


if __name__ == "__main__":
    main()
