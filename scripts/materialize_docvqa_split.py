#!/usr/bin/env python3
"""materialize_docvqa_split.py — turn the public DocVQA id-manifest into a
runnable split tree (CSV rows + PNG images) for SkillOpt's docvqa env.

Source of question text + gold answers + page images:
    lmms-lab/DocVQA  (HF dataset, gated=False)
    revision: 539088ef8a8ada01ac8e2e6d4e372586748a265e
    config:   DocVQA
    split:    validation                      (6 parquet shards, 5349 rows)

Source of which rows belong to which split:
    data/docvqa_id_split/{train,val,test}/items.json
    (107 / 53 / 374 questionIds — a 10% subset of DocVQA validation)

Output layout (matches skillopt/envs/docvqa/dataloader.py expectations):

    <out_dir>/{train,val,test}/items.csv      # one row per question
    <images_dir>/q<questionId>_d<docId>.png   # one PNG per question

CSV columns:
    questionId, docId, question, answer (stringified python list of strings),
    topic, image_path, ucsf_document_id, ucsf_document_page_no, source_split

Idempotent: existing image files are not re-written; existing CSVs are
overwritten so a re-run picks up manifest changes.

Usage
-----
    python scripts/materialize_docvqa_split.py             # defaults below
    python scripts/materialize_docvqa_split.py --limit 5   # smoke test (val only)
    python scripts/materialize_docvqa_split.py --splits val test
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

# Deferred imports (heavy): only loaded when needed inside main().

HF_REPO = "lmms-lab/DocVQA"
HF_REVISION = "539088ef8a8ada01ac8e2e6d4e372586748a265e"
HF_CONFIG = "DocVQA"
HF_SPLIT = "validation"
HF_NUM_SHARDS = 6

CSV_COLUMNS = [
    "questionId",
    "docId",
    "question",
    "answer",
    "topic",
    "image_path",
    "ucsf_document_id",
    "ucsf_document_page_no",
    "source_split",
]


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id_split", default=str(project_root / "data" / "docvqa_id_split"),
                    help="Directory holding {train,val,test}/items.json (default: data/docvqa_id_split).")
    ap.add_argument("--out_dir", default=str(project_root / "data" / "docvqa_id_split"),
                    help="Where to write {train,val,test}/items.csv. Default: same as --id_split.")
    ap.add_argument("--images_dir", default=str(project_root / "data" / "docvqa_images"),
                    help="Where to write PNGs (default: data/docvqa_images). Must match the image_path "
                         "values in items.json; if you change this, also rewrite image_path or run from "
                         "the project root.")
    ap.add_argument("--splits", nargs="+", default=["train", "val", "test"],
                    choices=["train", "val", "test"],
                    help="Which splits to materialize. Default: all three.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Per-split row cap for smoke tests (0 = all).")
    ap.add_argument("--cache_dir", default=None,
                    help="Optional HF cache dir override (else uses $HF_HOME / default).")
    ap.add_argument("--overwrite_images", action="store_true",
                    help="Re-write image PNGs even if they already exist on disk.")
    return ap.parse_args()


def load_id_manifest(id_split_dir: Path, split: str) -> list[dict]:
    p = id_split_dir / split / "items.json"
    if not p.exists():
        raise FileNotFoundError(f"id manifest missing: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"expected list in {p}, got {type(data).__name__}")
    return data


def build_hf_index(cache_dir: str | None, wanted_qids: set[str]) -> dict[str, dict]:
    """Return {questionId: {question, answers_list, image_bytes, ...}} for all wanted_qids.

    Iterates the 6 validation parquets, keeping only rows whose questionId is in
    wanted_qids so we don't blow up RAM holding 5349 PIL images.
    """
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq

    index: dict[str, dict] = {}
    remaining = set(wanted_qids)
    for shard in range(HF_NUM_SHARDS):
        fname = f"{HF_CONFIG}/{HF_SPLIT}-{shard:05d}-of-{HF_NUM_SHARDS:05d}.parquet"
        print(f"[hf] downloading {fname} ...", flush=True)
        fp = hf_hub_download(
            repo_id=HF_REPO,
            repo_type="dataset",
            revision=HF_REVISION,
            filename=fname,
            cache_dir=cache_dir,
        )
        table = pq.read_table(fp)
        rows = table.to_pylist()
        hit = 0
        for r in rows:
            qid = str(r["questionId"])
            if qid in remaining:
                index[qid] = r
                remaining.discard(qid)
                hit += 1
        print(f"[hf] shard {shard}: matched {hit} (cum={len(index)}, remaining={len(remaining)})")
        if not remaining:
            break
    if remaining:
        raise RuntimeError(
            f"Could not locate {len(remaining)} questionId(s) in {HF_REPO}@{HF_REVISION}/{HF_CONFIG}/{HF_SPLIT}. "
            f"Sample missing: {sorted(remaining)[:5]}"
        )
    return index


def write_image(hf_row: dict, target_path: Path, *, overwrite: bool) -> bool:
    """Write the page PNG. Returns True if a file was written, False if skipped."""
    if target_path.exists() and not overwrite:
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    img = hf_row["image"]
    raw = img["bytes"] if isinstance(img, dict) else None
    if raw is None:
        raise RuntimeError(f"missing image bytes for questionId={hf_row.get('questionId')}")
    # Re-encode to PNG (HF often stores JPEG bytes; the manifest's image_path uses .png).
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        if im.mode not in ("RGB", "RGBA", "L"):
            im = im.convert("RGB")
        im.save(target_path, format="PNG", optimize=False)
    return True


def materialize_split(
    *,
    split: str,
    id_split_dir: Path,
    out_dir: Path,
    images_dir: Path,
    hf_index: dict[str, dict],
    limit: int,
    overwrite_images: bool,
) -> dict[str, int]:
    items = load_id_manifest(id_split_dir, split)
    if limit and limit < len(items):
        items = items[:limit]

    csv_path = out_dir / split / "items.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    n_img_written = n_img_skipped = 0
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for it in items:
            qid = str(it["questionId"])
            hf_row = hf_index[qid]
            doc_id = str(it.get("docId") or hf_row.get("docId") or "")
            img_path = (images_dir / f"q{qid}_d{doc_id}.png")
            wrote = write_image(hf_row, img_path, overwrite=overwrite_images)
            if wrote:
                n_img_written += 1
            else:
                n_img_skipped += 1
            answers_list = hf_row.get("answers") or []
            if not isinstance(answers_list, list):
                answers_list = [str(answers_list)]
            answers_list = [str(a) for a in answers_list]
            # topic: prefer manifest's topic (may be "handwritten|form"), fall back to HF question_types
            topic = it.get("topic")
            if not topic:
                qt = hf_row.get("question_types") or []
                topic = "|".join(str(x) for x in qt) if qt else ""
            w.writerow({
                "questionId": qid,
                "docId": doc_id,
                "question": str(hf_row.get("question") or ""),
                # ast.literal_eval-friendly: repr a list of strings
                "answer": repr(answers_list),
                "topic": topic,
                "image_path": it.get("image_path") or f"data/docvqa_images/q{qid}_d{doc_id}.png",
                "ucsf_document_id": str(it.get("ucsf_document_id") or hf_row.get("ucsf_document_id") or ""),
                "ucsf_document_page_no": str(it.get("ucsf_document_page_no") or hf_row.get("ucsf_document_page_no") or ""),
                "source_split": str(it.get("source_split") or hf_row.get("data_split") or HF_SPLIT),
            })
    return {
        "rows": len(items),
        "images_written": n_img_written,
        "images_skipped_existing": n_img_skipped,
        "csv_path": str(csv_path),
    }


def main() -> int:
    args = parse_args()
    id_split_dir = Path(args.id_split).resolve()
    out_dir = Path(args.out_dir).resolve()
    images_dir = Path(args.images_dir).resolve()

    # Collect wanted question IDs across all requested splits in one pass over HF.
    manifests = {s: load_id_manifest(id_split_dir, s) for s in args.splits}
    wanted: set[str] = set()
    for s, items in manifests.items():
        rows = items[: args.limit] if args.limit else items
        wanted.update(str(it["questionId"]) for it in rows)
    print(f"[plan] splits={args.splits} → {len(wanted)} unique questionIds to fetch")
    print(f"[plan] id_split={id_split_dir}")
    print(f"[plan] out_dir ={out_dir}")
    print(f"[plan] images  ={images_dir}")

    hf_index = build_hf_index(cache_dir=args.cache_dir, wanted_qids=wanted)

    summary: dict[str, dict] = {}
    for split in args.splits:
        print(f"\n[split={split}] materializing ...")
        summary[split] = materialize_split(
            split=split,
            id_split_dir=id_split_dir,
            out_dir=out_dir,
            images_dir=images_dir,
            hf_index=hf_index,
            limit=args.limit,
            overwrite_images=args.overwrite_images,
        )
        s = summary[split]
        print(f"  → rows={s['rows']}  imgs_written={s['images_written']}  imgs_skipped={s['images_skipped_existing']}")
        print(f"    csv: {s['csv_path']}")

    print("\nDone.")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
