"""Human-in-the-loop review hook for SkillOpt training.

File-based IPC. When `hitl` is enabled, after the rewriter produces a
candidate skill, we write a pending review file and block until the user
fills in a decision header line and saves the file.

Decision header (first non-blank line of the file must be one of):
  # ACCEPT          → use candidate_skill as-is, proceed to gate
  # REJECT          → discard candidate_skill, fall back to current_skill
                      (gate will be skipped, marked action=hitl_reject)
  # EDIT            → use the edited candidate (see EDITED SKILL section)
                      proceed to gate
  # SKIP            → no human decision; auto pipeline continues as if
                      HITL was off
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional


_VALID_DECISIONS = {"ACCEPT", "REJECT", "EDIT", "SKIP", "SELECT"}

_PENDING_TEMPLATE = """\
# REVIEW
# step={step}/{total_steps}  batch acc={batch_acc:.4f}  skill: {current_len} → {cand_len} chars
#
# INSTRUCTIONS — replace the first line of this file with one of:
#   # ACCEPT          (use candidate as-is, run gate)
#   # REJECT          (discard candidate, keep current skill, skip gate)
#   # EDIT            (use the EDITED SKILL section below, run gate)
#   # SELECT          (keep only the edits whose box is checked [x] below, run gate)
#   # SKIP            (no decision; let the auto gate decide)
# Save the file. Training will resume.
#
# Lines starting with '#' are ignored by the parser.

============================== SUMMARY ==============================
{summary_block}

============================== APPLIED EDITS ==============================
{edits_block}
{dropped_block}
============================ WORST {n_worst} FAILURES (this batch) ============================
{worst_block}

============================== RAW DIFF ==============================
{diff_text}

============================ CURRENT SKILL ============================
{current_skill}

=========================== CANDIDATE SKILL ===========================
{candidate_skill}

============================ EDITED SKILL ============================
(only used when decision is # EDIT — paste the skill you want to apply
 between the BEGIN/END markers below; leave as-is to use candidate)
<<<BEGIN_EDIT>>>
{candidate_skill}
<<<END_EDIT>>>
"""


@dataclass
class HITLDecision:
    action: str            # one of ACCEPT, REJECT, EDIT, SKIP, SELECT
    edited_skill: Optional[str] = None
    review_seconds: float = 0.0
    selected_indices: Optional[list[int]] = None


def _unified_diff(current: str, candidate: str) -> str:
    import difflib
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="current_skill.md",
        tofile="candidate_skill.md",
        n=3,
    )
    return "".join(diff) or "(no textual change)"


def _format_worst(rollout_results: list[dict], n: int = 3) -> str:
    """Render the N hardest failures with predicted vs gold labels + texts."""
    if not rollout_results:
        return "(no rollout results captured)"
    sorted_r = sorted(rollout_results, key=lambda r: float(r.get("hard", 0)))
    worst = sorted_r[:n]
    lines = []
    for i, r in enumerate(worst, 1):
        rid = r.get("item_id") or r.get("id") or r.get("env_id") or "?"
        hard = r.get("hard", 0)
        q = r.get("question") or r.get("prompt") or r.get("query") or ""
        if isinstance(q, str) and len(q) > 320:
            q = q[:317] + "..."
        pred_lbl = r.get("predicted_label") or r.get("predicted_answer") or r.get("prediction") or ""
        gold_lbl = r.get("correct_label") or r.get("gold") or r.get("correct_choice") or ""
        pred_text = r.get("predicted_text") or ""
        gold_text = r.get("correct_text") or ""
        fail = r.get("fail_reason") or ""

        def _short(s, limit=260):
            s = str(s)
            return s if len(s) <= limit else s[:limit - 3] + "..."

        mark = "✓" if float(hard) >= 1.0 else "✗"
        lines.append(f"──── worst #{i}  id={rid}  predicted={pred_lbl}  gold={gold_lbl}  {mark}")
        if q:
            lines.append(f"  Q:    {q}")
        if pred_text:
            lines.append(f"  Pred: {_short(pred_text)}")
        if gold_text:
            lines.append(f"  Gold: {_short(gold_text)}")
        if fail:
            lines.append(f"  Why:  {fail}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _load_provenance(out_root: str, step: int) -> dict:
    """Load per-step JSON artifacts that explain where each edit came from.

    Returns dict with keys: merged (merged_patch.json), ranked (ranked_edits.json),
    applied (edit_apply_report.json), patches (list of per-minibatch analyst
    patches). Missing files yield empty values; never raises.
    """
    step_dir = os.path.join(out_root, "steps", f"step_{step:04d}")
    out: dict = {"step_dir": step_dir, "merged": None, "ranked": None,
                 "applied": None, "patches": []}

    def _try_load(name: str):
        p = os.path.join(step_dir, name)
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    out["merged"] = _try_load("merged_patch.json")
    out["ranked"] = _try_load("ranked_edits.json")
    out["applied"] = _try_load("edit_apply_report.json")

    patches_dir = os.path.join(step_dir, "patches")
    if os.path.isdir(patches_dir):
        for name in sorted(os.listdir(patches_dir)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(patches_dir, name)) as f:
                    data = json.load(f)
                data["_minibatch_name"] = name[:-5]
                out["patches"].append(data)
            except Exception:
                continue
    return out


def _content_key(content: str) -> str:
    """Stable key for matching the same edit across merged/ranked/patches."""
    return (content or "").strip()[:80]


def _find_source_patch(edit_content: str, patches: list[dict]) -> Optional[dict]:
    """Find which analyst minibatch produced this edit; matched by content prefix."""
    key = _content_key(edit_content)
    if not key:
        return None
    for p in patches:
        for e in (p.get("patch", {}).get("edits", []) or []):
            if _content_key(e.get("content", "")) == key:
                return p
    return None


def _indent(text: str, prefix: str = "   ") -> str:
    if not text:
        return ""
    return "\n".join(prefix + line for line in text.splitlines())


def _format_edit_card(idx: int, total: int, edit: dict, prov: dict) -> str:
    """Render one APPLIED edit as a card with source / analyst / ranker info."""
    op = edit.get("op", "?")
    target = edit.get("target", "")
    content = edit.get("content", "") or ""
    src = (edit.get("source_type") or "?").upper()
    support = edit.get("support_count")
    support_str = f" · {support} trajectories voted" if support is not None else ""

    if op == "append":
        where = "append to end of skill"
    elif op == "insert_after":
        where = f"insert after `{target}`" if target else "insert"
    elif op == "replace":
        where = f"replace under `{target}`"
    else:
        where = f"op={op} target=`{target}`"

    lines = [f"[x] EDIT {idx}/{total}  ────  [{src}{support_str}]   (toggle to [ ] to drop when decision is # SELECT)",
             f"Where:  {where}",
             "New content:",
             _indent(content.strip(), "   "),
             ""]

    src_patch = _find_source_patch(content, prov.get("patches", []))
    if src_patch:
        mb_name = src_patch.get("_minibatch_name", "?")
        mb_size = src_patch.get("batch_size", "?")
        analyst_reason = (src_patch.get("patch") or {}).get("reasoning", "")
        lines.append(f"Analyst (from {mb_name}, {mb_size} trajectories):")
        lines.append(_indent(analyst_reason, "   ") or "   (no reasoning recorded)")
        # Optional: surface the failure_summary / success_patterns for failure / success patches
        fs = src_patch.get("failure_summary")
        if fs and isinstance(fs, list):
            lines.append("   Failure types in this minibatch:")
            for f in fs:
                lines.append(f"     - {f.get('failure_type','?')} (x{f.get('count','?')}): {f.get('description','')}")
        sp = src_patch.get("success_patterns")
        if sp and isinstance(sp, list):
            lines.append("   Success patterns in this minibatch:")
            for p in sp:
                lines.append(f"     - {p}")
        lines.append("")
    return "\n".join(lines)


def _format_dropped_block(prov: dict) -> str:
    """List edits that were merged but NOT selected by the ranker."""
    merged = (prov.get("merged") or {}).get("edits") or []
    ranked = (prov.get("ranked") or {}).get("edits") or []
    ranking_details = (prov.get("ranked") or {}).get("ranking_details") or {}
    if not merged or not ranked:
        return ""
    kept_keys = {_content_key(e.get("content", "")) for e in ranked}
    dropped = [e for e in merged if _content_key(e.get("content", "")) not in kept_keys]
    if not dropped:
        return ""
    lines = ["", "============================== DROPPED EDITS ==============================",
             f"({len(dropped)} edit(s) merged but not selected by ranker)", ""]
    for i, e in enumerate(dropped, 1):
        src = (e.get("source_type") or "?").upper()
        support = e.get("support_count")
        support_str = f" · {support} trajectories voted" if support is not None else ""
        op = e.get("op", "?")
        target = e.get("target", "")
        where = f"append" if op == "append" else f"insert after `{target}`" if op == "insert_after" else f"{op} `{target}`"
        lines.append(f"──── DROPPED {i} ────  [{src}{support_str}]")
        lines.append(f"Where:  {where}")
        lines.append("Proposed content:")
        lines.append(_indent((e.get("content", "") or "").strip(), "   "))
        lines.append("")
    rd = ranking_details.get("reasoning") if isinstance(ranking_details, dict) else None
    if rd:
        lines.append("Ranker (overall reasoning for selection):")
        lines.append(_indent(rd, "   "))
        lines.append("")
    return "\n".join(lines)


def _format_summary(prov: dict, current_skill: str, candidate_skill: str,
                    batch_acc: float) -> str:
    ranked_edits = (prov.get("ranked") or {}).get("edits") or []
    merged_edits = (prov.get("merged") or {}).get("edits") or []
    applied = prov.get("applied") or []
    n_applied = sum(1 for r in applied if str(r.get("status", "")).startswith("applied"))
    n_failed = len(applied) - n_applied if applied else 0
    src_counts: dict[str, int] = {}
    for e in ranked_edits:
        s = (e.get("source_type") or "?").lower()
        src_counts[s] = src_counts.get(s, 0) + 1
    src_str = ", ".join(f"{v} {k}" for k, v in src_counts.items()) or "n/a"
    lines = [
        f"Batch hard accuracy:  {batch_acc:.4f}",
        f"Skill size:           {len(current_skill)} → {len(candidate_skill)} chars  (Δ={len(candidate_skill)-len(current_skill):+d})",
        f"Edits proposed → kept → applied:  {len(merged_edits)} → {len(ranked_edits)} → {n_applied}"
        + (f" ({n_failed} failed to apply)" if n_failed else ""),
        f"Edit sources (kept): {src_str}",
    ]
    return "\n".join(lines)


def _parse_decision(text: str) -> tuple[str, Optional[str], Optional[list[int]]]:
    """Read first non-blank, non-comment-style header line.

    Returns (action, edited_skill_or_None, selected_edit_indices_or_None).
    action is upper-cased and must be one of _VALID_DECISIONS; otherwise
    raises ValueError. For SELECT, the third element is the list of 1-based
    indices whose checkbox is `[x]`.
    """
    # find first non-blank line
    first = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        first = s
        break
    if not first or not first.startswith("#"):
        raise ValueError(
            f"first line must start with '#' followed by decision, got {first!r}"
        )
    tokens = first.lstrip("#").strip().split()
    if not tokens:
        raise ValueError("decision token missing after '#'")
    action = tokens[0].upper()
    if action not in _VALID_DECISIONS:
        raise ValueError(
            f"unknown decision {action!r}; must be one of {sorted(_VALID_DECISIONS)}"
        )

    edited = None
    selected: Optional[list[int]] = None
    if action == "EDIT":
        # extract content between BEGIN_EDIT / END_EDIT markers
        begin = "<<<BEGIN_EDIT>>>"
        end = "<<<END_EDIT>>>"
        i = text.find(begin)
        j = text.find(end)
        if i < 0 or j < 0 or j <= i:
            raise ValueError("EDIT decision requires BEGIN_EDIT/END_EDIT markers")
        edited = text[i + len(begin):j].strip("\n")
        if not edited.strip():
            raise ValueError("EDIT section is empty")
    elif action == "SELECT":
        import re
        # match "[x] EDIT 1/4", "[X] EDIT 2/4", "[ ] EDIT 3/4"
        all_idx: list[int] = []
        kept: list[int] = []
        for m in re.finditer(r"\[([ xX])\]\s+EDIT\s+(\d+)\s*/\s*\d+", text):
            idx = int(m.group(2))
            all_idx.append(idx)
            if m.group(1).lower() == "x":
                kept.append(idx)
        if not all_idx:
            raise ValueError("SELECT decision found no `[ ] EDIT N/M` checkboxes")
        if not kept:
            raise ValueError("SELECT decision but no edits checked; "
                             "use `# REJECT` to drop everything")
        # dedupe + sort
        selected = sorted(set(kept))
    return action, edited, selected


def human_review(
    *,
    step: int,
    total_steps: int,
    out_root: str,
    current_skill: str,
    candidate_skill: str,
    batch_acc: float,
    rollout_results: list[dict],
    poll_interval_s: float = 1.0,
) -> HITLDecision:
    """Block until the user fills in a decision.

    Writes ``out_root/hitl_review/step_{step:04d}_pending.md`` with the
    candidate diff + worst-N traces, then polls the file until the first
    non-blank line is a valid decision header. After parsing, the file is
    renamed to ``step_{step:04d}_decided.md`` for the audit trail.
    """
    review_dir = os.path.join(out_root, "hitl_review")
    os.makedirs(review_dir, exist_ok=True)
    pending = os.path.join(review_dir, f"step_{step:04d}_pending.md")
    decided = os.path.join(review_dir, f"step_{step:04d}_decided.md")

    diff_text = _unified_diff(current_skill, candidate_skill)
    worst_block = _format_worst(rollout_results, n=3)

    prov = _load_provenance(out_root, step)
    summary_block = _format_summary(prov, current_skill, candidate_skill, batch_acc)
    ranked_edits = (prov.get("ranked") or {}).get("edits") or []
    if ranked_edits:
        edits_block = "\n".join(
            _format_edit_card(i, len(ranked_edits), e, prov)
            for i, e in enumerate(ranked_edits, 1)
        )
    else:
        edits_block = "(no ranked_edits.json found — provenance artifacts unavailable)"
    dropped_block = _format_dropped_block(prov)

    payload = _PENDING_TEMPLATE.format(
        step=step,
        total_steps=total_steps,
        batch_acc=batch_acc,
        current_len=len(current_skill),
        cand_len=len(candidate_skill),
        summary_block=summary_block,
        edits_block=edits_block,
        dropped_block=dropped_block,
        diff_text=diff_text,
        n_worst=3,
        worst_block=worst_block,
        current_skill=current_skill,
        candidate_skill=candidate_skill,
    )
    with open(pending, "w") as f:
        f.write(payload)

    # Terminal bell (\a) → VS Code flashes the terminal tab + plays the system
    # sound when "terminal.integrated.enableBell" is on.
    # OSC 9 → VS Code shows a toast notification (works over SSH too).
    import sys
    msg = f"HITL waiting: step {step}/{total_steps}"
    sys.stdout.write("\a")
    sys.stdout.write(f"\033]9;{msg}\007")
    sys.stdout.flush()

    # Best-effort: auto-open the review file in the user's editor.
    # Skipped silently if `code` CLI is unavailable.
    import shutil, subprocess
    editor_cmd = os.environ.get("SKILLOPT_HITL_EDITOR", "code")
    if shutil.which(editor_cmd):
        try:
            subprocess.Popen(
                [editor_cmd, pending],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            print(f"  [hitl] could not auto-open editor ({exc})")

    print()
    print("  ┌─ HITL REVIEW ────────────────────────────────────────────────────────")
    print(f"  │ Open & edit:  {pending}")
    print(f"  │ First line:   # ACCEPT  |  # REJECT  |  # EDIT  |  # SELECT  |  # SKIP")
    print(f"  │ Save the file to resume training.")
    print("  └────────────────────────────────────────────────────────────")
    print()

    t0 = time.time()
    last_mtime = os.path.getmtime(pending)
    decision: Optional[HITLDecision] = None
    while True:
        try:
            mtime = os.path.getmtime(pending)
        except FileNotFoundError:
            time.sleep(poll_interval_s)
            continue
        if mtime <= last_mtime:
            time.sleep(poll_interval_s)
            continue
        # file was saved; try to parse
        try:
            with open(pending) as f:
                text = f.read()
            action, edited, selected = _parse_decision(text)
        except ValueError as exc:
            print(f"  [hitl] cannot parse decision: {exc}; waiting for save...")
            last_mtime = mtime
            time.sleep(poll_interval_s)
            continue

        # For SELECT: rebuild candidate by applying only the chosen edits.
        if action == "SELECT":
            try:
                ranked = (_load_provenance(out_root, step).get("ranked") or {}).get("edits") or []
                if not ranked:
                    raise ValueError("no ranked_edits.json found; cannot apply SELECT")
                kept = [ranked[i - 1] for i in (selected or []) if 1 <= i <= len(ranked)]
                if not kept:
                    raise ValueError("none of the checked indices match ranked edits")
                from skillopt.optimizer.skill import apply_patch
                edited = apply_patch(current_skill, {"edits": kept})
                if not edited.endswith("\n"):
                    edited += "\n"
            except Exception as exc:
                print(f"  [hitl] SELECT could not be applied: {exc}; waiting for save...")
                last_mtime = mtime
                time.sleep(poll_interval_s)
                continue

        decision = HITLDecision(
            action=action,
            edited_skill=edited,
            review_seconds=round(time.time() - t0, 1),
            selected_indices=selected,
        )
        break

    # archive
    try:
        os.replace(pending, decided)
    except OSError:
        pass

    # log
    log_path = os.path.join(review_dir, "decisions.jsonl")
    with open(log_path, "a") as f:
        f.write(json.dumps({
            "step": step,
            "action": decision.action,
            "review_seconds": decision.review_seconds,
            "edited_chars": len(decision.edited_skill or ""),
            "selected_indices": decision.selected_indices,
            "candidate_chars": len(candidate_skill),
            "current_chars": len(current_skill),
            "batch_acc": batch_acc,
        }) + "\n")

    print(f"  [hitl] decision={decision.action} review={decision.review_seconds}s")
    return decision
