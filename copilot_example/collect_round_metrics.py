from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

TS_FMT = "%Y%m%d_%H%M%S"
HISTORY_RE = re.compile(r"^round(?P<round>\d+)__(?P<ts>\d{8}_\d{6})__(?P<tag>before|after|best)\.md$")


@dataclass
class EvalRun:
    run_id: str
    ts: datetime
    split: str
    n_items: int | None
    hard: float | None
    soft: float | None
    path: Path


@dataclass
class RoundWindow:
    round_idx: int
    start: datetime | None
    end: datetime | None


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, TS_FMT)
    except Exception:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_eval_runs(eval_root: Path) -> list[EvalRun]:
    runs: list[EvalRun] = []
    if not eval_root.exists():
        return runs
    for child in sorted(eval_root.iterdir()):
        if not child.is_dir():
            continue
        run_id = child.name
        ts = _parse_ts(run_id)
        if ts is None:
            continue
        summary_path = child / "eval_summary.json"
        summary = _read_json(summary_path)
        split = "unknown"
        n_items: int | None = None
        hard: float | None = None
        soft: float | None = None
        if isinstance(summary, dict):
            split = str(summary.get("split") or "unknown")
            try:
                n_items = int(summary.get("n_items")) if summary.get("n_items") is not None else None
            except Exception:
                n_items = None
            try:
                hard = float(summary.get("hard")) if summary.get("hard") is not None else None
            except Exception:
                hard = None
            try:
                soft = float(summary.get("soft")) if summary.get("soft") is not None else None
            except Exception:
                soft = None
        runs.append(
            EvalRun(
                run_id=run_id,
                ts=ts,
                split=split,
                n_items=n_items,
                hard=hard,
                soft=soft,
                path=child,
            )
        )
    return sorted(runs, key=lambda x: x.ts)


def load_round_windows(history_root: Path, runs: list[EvalRun]) -> list[RoundWindow]:
    markers: dict[int, dict[str, datetime]] = defaultdict(dict)
    if history_root.exists():
        for p in history_root.iterdir():
            m = HISTORY_RE.match(p.name)
            if not m:
                continue
            ridx = int(m.group("round"))
            ts = _parse_ts(m.group("ts"))
            if ts is None:
                continue
            tag = m.group("tag")
            markers[ridx][tag] = ts

    if not markers:
        # Fallback: create pseudo-rounds by pairing consecutive train/val runs.
        windows: list[RoundWindow] = []
        round_idx = 0
        start: datetime | None = None
        for r in runs:
            if start is None:
                start = r.ts
            if r.split == "val":
                windows.append(RoundWindow(round_idx=round_idx, start=start, end=r.ts))
                round_idx += 1
                start = None
        if start is not None and runs:
            windows.append(RoundWindow(round_idx=round_idx, start=start, end=runs[-1].ts))
        return windows

    windows: list[RoundWindow] = []
    round_ids = sorted(markers)

    # Main rule: runs for round R are those in [before(R), before(R+1)).
    # This is robust even when before/after snapshots are created in the same second.
    round_before: dict[int, datetime] = {
        ridx: markers[ridx]["before"]
        for ridx in round_ids
        if "before" in markers[ridx]
    }

    if round_before:
        ordered = sorted(round_before.items(), key=lambda kv: kv[1])

        # Optional pseudo-round0 before first recorded round marker.
        if runs and ordered and runs[0].ts < ordered[0][1]:
            windows.append(
                RoundWindow(
                    round_idx=min(round_before) - 1 if min(round_before) > 0 else 0,
                    start=None,
                    end=ordered[0][1],
                )
            )

        for i, (ridx, start_ts) in enumerate(ordered):
            end_ts = ordered[i + 1][1] if i + 1 < len(ordered) else (runs[-1].ts if runs else None)
            windows.append(RoundWindow(round_idx=ridx, start=start_ts, end=end_ts))
        return windows

    # Fallback when history exists but no before markers are parseable.
    for ridx in round_ids:
        start = markers[ridx].get("best") or markers[ridx].get("after")
        end = None
        windows.append(RoundWindow(round_idx=ridx, start=start, end=end))
    return windows


def build_round_metrics(windows: list[RoundWindow], runs: list[EvalRun]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for w in windows:
        in_window = [
            r for r in runs
            if (w.start is None or r.ts >= w.start)
            and (w.end is None or r.ts <= w.end)
        ]

        by_split: dict[str, list[EvalRun]] = defaultdict(list)
        for r in in_window:
            by_split[r.split].append(r)

        row: dict[str, Any] = {
            "round": w.round_idx,
            "window_start": w.start.strftime(TS_FMT) if w.start else None,
            "window_end": w.end.strftime(TS_FMT) if w.end else None,
        }

        for split in ("train", "val", "test"):
            cand = by_split.get(split, [])
            chosen = cand[-1] if cand else None
            row[f"{split}_run"] = chosen.run_id if chosen else None
            row[f"{split}_n_items"] = chosen.n_items if chosen else None
            row[f"{split}_hard"] = chosen.hard if chosen else None
            row[f"{split}_soft"] = chosen.soft if chosen else None

        # Keep all run ids for traceability.
        row["runs_in_window"] = [r.run_id for r in in_window]
        rows.append(row)

    return sorted(rows, key=lambda x: int(x["round"]))


def write_outputs(skillopt_root: Path, rows: list[dict[str, Any]]) -> None:
    jsonl_path = skillopt_root / "round_metrics.jsonl"
    csv_path = skillopt_root / "round_metrics.csv"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    fieldnames = [
        "round",
        "window_start",
        "window_end",
        "train_run",
        "train_n_items",
        "train_hard",
        "train_soft",
        "val_run",
        "val_n_items",
        "val_hard",
        "val_soft",
        "test_run",
        "test_n_items",
        "test_hard",
        "test_soft",
        "runs_in_window",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            rr = dict(r)
            rr["runs_in_window"] = ";".join(rr.get("runs_in_window", []))
            writer.writerow(rr)


def process_example_dir(example_dir: Path) -> tuple[bool, str]:
    skillopt_root = example_dir / "workspace" / ".skillopt"
    eval_root = skillopt_root / "_eval_run"
    history_root = skillopt_root / "history"

    if not eval_root.exists():
        return False, f"{example_dir.name}: skipped (no {eval_root})"

    runs = load_eval_runs(eval_root)
    if not runs:
        return False, f"{example_dir.name}: skipped (no parseable eval runs)"

    windows = load_round_windows(history_root, runs)
    rows = build_round_metrics(windows, runs)
    write_outputs(skillopt_root, rows)
    return True, f"{example_dir.name}: wrote {len(rows)} rounds -> {skillopt_root / 'round_metrics.jsonl'}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate round-level train/val/test metrics from .skillopt runs.")
    parser.add_argument("--root", default="copilot_example", help="Root directory containing example env subdirs.")
    parser.add_argument("--dirs", nargs="*", default=None, help="Optional specific subdirs to process.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"root not found: {root}")
        return 2

    if args.dirs:
        targets = [root / d for d in args.dirs]
    else:
        targets = [p for p in sorted(root.iterdir()) if p.is_dir() and (p / "workspace").exists()]

    ok = 0
    for d in targets:
        success, msg = process_example_dir(d)
        print(msg)
        if success:
            ok += 1

    print(f"done: {ok}/{len(targets)} directories processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
