#!/usr/bin/env python3
"""data/download.py — hydrate benchmark splits from HuggingFace.

Downloads splits from `yshenaw/SkillOpt_Lite_Benchmarks` into local
`data/<split_dir>/{train,val,test}/…` layouts matching each
`copilot_example/<env>/run.sh --split_dir`. Also fetches the DocVQA image
subset (`docvqa_images/`) and the AlfWorld game corpus subset
(`alfworld_games.tar.gz`, extracted to $ALFWORLD_DATA or ~/.cache/alfworld).

Usage:
    python data/download.py                          # all six benchmarks + corpora
    python data/download.py --config livemath        # one benchmark
    python data/download.py --skip-corpora           # manifests only (no images/games)
    python data/download.py --hf-repo my-user/my-fork

The HF repo has one config per benchmark: `searchqa`, `docvqa`, `alfworld`,
`officeqa`, `spreadsheetbench`, `livemath`. Each config has three splits
(`train`, `val`, `test`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_HF_REPO = os.environ.get("SKILLOPT_HF_REPO", "yshenaw/SkillOpt_Lite_Benchmarks")

# HF config name → (SPLIT_DIR relative to --out, per-split filename map).
# These directory names and filenames must match exactly what each env's
# `copilot_example/<env>/run.sh` passes as `--split_dir` and expects to load.
CONFIGS: dict[str, tuple[str, dict[str, str]]] = {
    "searchqa":         ("searchqa_split",
                         {"train": "train.json", "val": "val.json", "test": "test.json"}),
    "docvqa":           ("docvqa_id_split",
                         {"train": "items.json", "val": "items.json", "test": "items.json"}),
    "alfworld":         ("alfworld_split_200_140_134_seed42",
                         {"train": "train.json", "val": "val.json", "test": "test.json"}),
    "officeqa":         ("officeqa_split",
                         {"train": "items.csv", "val": "items.csv", "test": "items.csv"}),
    "spreadsheetbench": ("spreadsheetbench_split",
                         {"train": "items.json", "val": "items.json", "test": "items.json"}),
    "livemath":         ("ablation_splits/livemathematicianbench/2-2-6_seed42",
                         {"train": "items.json", "val": "items.json", "test": "items.json"}),
}

# Benchmarks that publish id manifests only (searchqa now ships full text).
# docvqa needs images fetched via --materialize; alfworld needs the game corpus.
MANIFEST_ONLY: set[str] = set()

# Columns that were JSON-encoded during parquet write and must be decoded
# back to native Python objects before writing local items.json.
_JSON_ENCODED_COLS = {
    "answers",         # searchqa: list[str]
    "choices",         # livemath: list[dict]
    "correct_choice",  # livemath: dict
    "theorem_type",    # livemath: list[str]
    "source_files",    # officeqa: list[str] (if present)
    "source_docs",     # officeqa: list[str] (if present)
}


def _decode_json_cols(rows: list[dict]) -> list[dict]:
    """Reverse the JSON stringification applied at parquet-build time."""
    for r in rows:
        for k in list(r.keys()):
            if k in _JSON_ENCODED_COLS and isinstance(r[k], str):
                s = r[k].strip()
                if s and s[0] in "[{":
                    try:
                        r[k] = json.loads(s)
                    except (ValueError, TypeError):
                        pass
    return rows

CORPUS_INSTRUCTIONS = {
    "alfworld_env": """\
The ALFWorld game/pddl/traj files are bundled in the HF dataset repo as
`alfworld_games.tar.gz`. The download script extracts them automatically
into `~/.cache/alfworld/` (override with $ALFWORLD_DATA). If you already
have alfworld installed with `alfworld-download`, the two layouts merge
without conflict — both target `json_2.1.1/<split>/<task>/<trial>/`.
""",
}


def _try_import_datasets():
    try:
        from datasets import load_dataset  # noqa: F401
        return True
    except ImportError:
        print("ERROR: `datasets` not installed. Install with:", file=sys.stderr)
        print("    pip install datasets", file=sys.stderr)
        return False


def _hydrate_docvqa_images(hf_repo: str, out_root: Path, rows_by_split: dict[str, list[dict]]) -> None:
    """Download `docvqa_images/` from HF and rewrite each row's image_path.

    HF stores images under `docvqa_images/q<qid>_d<did>.png`. We mirror
    them under `<out_root>/docvqa_images/` and rewrite each row's
    `image_path` to point at the local absolute path — which is what
    copilot_example/docvqa/rollout.py expects.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub required for image hydration.", file=sys.stderr)
        return
    print(f"[docvqa] pulling images from {hf_repo}:docvqa_images/ …")
    local_repo = snapshot_download(
        repo_id=hf_repo,
        repo_type="dataset",
        allow_patterns=["docvqa_images/*"],
    )
    src_dir = Path(local_repo) / "docvqa_images"
    dst_dir = out_root / "docvqa_images"
    dst_dir.mkdir(parents=True, exist_ok=True)
    # snapshot_download already fetched into HF cache; copy/symlink into out_root
    # so run.sh's SPLIT_DIR-relative code can find them via a stable path.
    import shutil
    copied = 0
    for src in src_dir.iterdir():
        if not src.is_file():
            continue
        dst = dst_dir / src.name
        if dst.exists() or dst.is_symlink():
            continue
        try:
            os.symlink(src.resolve(), dst)
        except OSError:
            shutil.copy2(src, dst)
        copied += 1
    print(f"[docvqa] {copied} new images linked → {dst_dir}")

    # Rewrite image_path in every docvqa split we just wrote. Use the
    # symlink path (not `.resolve()`) so items.json references the stable
    # `<out_root>/docvqa_images/…` location, not the HF cache blob hash.
    dirname, filename_by_split = CONFIGS["docvqa"]
    abs_dst_dir = dst_dir.absolute()
    for split, rows in rows_by_split.items():
        for r in rows:
            ip = r.get("image_path", "")
            if isinstance(ip, str) and ip:
                r["image_path"] = str(abs_dst_dir / Path(ip).name)
        _write_split(rows, out_root / dirname / split, filename_by_split[split])


def _hydrate_alfworld_games(hf_repo: str, out_root: Path, rows_by_split: dict[str, list[dict]]) -> None:
    """Download `alfworld_games.tar.gz` and extract into $ALFWORLD_DATA or ~/.cache/alfworld/.

    Also rewrites each row's `gamefile` to the local absolute path so
    copilot_example/alfworld/rollout.py can load them without env-var
    juggling.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub required for alfworld hydration.", file=sys.stderr)
        return
    import tarfile

    cache_root = Path(os.environ.get("ALFWORLD_DATA", str(Path.home() / ".cache" / "alfworld"))).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    marker = cache_root / "json_2.1.1"
    marker.mkdir(exist_ok=True)

    print(f"[alfworld] pulling alfworld_games.tar.gz from {hf_repo} …")
    tar_local = hf_hub_download(
        repo_id=hf_repo,
        filename="alfworld_games.tar.gz",
        repo_type="dataset",
    )
    print(f"[alfworld] extracting → {cache_root}")
    with tarfile.open(tar_local, "r:gz") as tf:
        # Guard against path traversal — enforce that every member is
        # under json_2.1.1/ (no ../ or absolute paths).
        safe = []
        for m in tf.getmembers():
            if m.name.startswith("/") or ".." in m.name.split("/"):
                print(f"[alfworld] skip unsafe entry: {m.name}")
                continue
            if not m.name.startswith("json_2.1.1/"):
                print(f"[alfworld] skip out-of-tree entry: {m.name}")
                continue
            safe.append(m)
        tf.extractall(cache_root, members=safe)
    print(f"[alfworld] extracted {len(safe)} files")

    # Rewrite gamefile to absolute local path.
    dirname, filename_by_split = CONFIGS["alfworld"]
    for split, rows in rows_by_split.items():
        for r in rows:
            gf = r.get("gamefile", "")
            if isinstance(gf, str) and gf:
                r["gamefile"] = str((cache_root / gf).resolve())
        _write_split(rows, out_root / dirname / split, filename_by_split[split])


def _write_split(rows: list[dict], out_path: Path, filename: str) -> None:
    out_path.mkdir(parents=True, exist_ok=True)
    dest = out_path / filename
    if filename.endswith(".json"):
        dest.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    elif filename.endswith(".csv"):
        import csv
        if not rows:
            dest.write_text("")
            return
        keys = list(rows[0].keys())
        with dest.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    else:
        raise ValueError(f"unknown filename ext: {filename}")
    print(f"  wrote {dest}  ({len(rows)} rows)")


def _download_config(hf_repo: str, cfg: str, out_root: Path) -> dict[str, list[dict]]:
    """Load one config's splits from HF, write items.{json,csv}, return the rows.

    The returned dict is used by hydrators (docvqa, alfworld) to rewrite
    path columns to local absolute paths after the raw corpora are fetched.
    """
    from datasets import load_dataset

    dirname, filename_by_split = CONFIGS[cfg]
    print(f"[{cfg}] loading from {hf_repo} …")
    rows_by_split: dict[str, list[dict]] = {}
    for split in ("train", "val", "test"):
        try:
            ds = load_dataset(hf_repo, cfg, split=split)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {split}: {e}")
            rows_by_split[split] = []
            continue
        rows = ds.to_list() if hasattr(ds, "to_list") else [dict(r) for r in ds]
        rows = _decode_json_cols(rows)
        rows_by_split[split] = rows
        _write_split(rows, out_root / dirname / split, filename_by_split[split])
    return rows_by_split


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hf-repo", default=DEFAULT_HF_REPO,
                    help=f"HuggingFace dataset repo (default: {DEFAULT_HF_REPO})")
    ap.add_argument("--config", choices=sorted(CONFIGS), default=None,
                    help="Only download one benchmark (default: all)")
    ap.add_argument("--out", default="data",
                    help="Output root (default: ./data)")
    ap.add_argument("--skip-corpora", action="store_true",
                    help="Skip fetching docvqa_images/ + alfworld_games.tar.gz; "
                         "keep manifests only.")
    args = ap.parse_args()

    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if not _try_import_datasets():
        return 1

    cfgs = [args.config] if args.config else sorted(CONFIGS)
    for cfg in cfgs:
        rows_by_split = _download_config(args.hf_repo, cfg, out_root)
        if args.skip_corpora:
            continue
        if cfg == "docvqa":
            _hydrate_docvqa_images(args.hf_repo, out_root, rows_by_split)
        elif cfg == "alfworld":
            _hydrate_alfworld_games(args.hf_repo, out_root, rows_by_split)
            print(CORPUS_INSTRUCTIONS["alfworld_env"])

    print()
    print("Done. Now try:")
    print("    bash copilot_example/livemath/run.sh --eval_limit 5 --limit 5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
