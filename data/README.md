# data/

Benchmark splits are hosted on HuggingFace at
[`yshenaw/SkillOpt_Lite_Benchmarks`](https://huggingface.co/datasets/yshenaw/SkillOpt_Lite_Benchmarks)
as a **multi-config** dataset. This directory is initially empty; run:

```bash
python data/download.py
```

to hydrate it. That fetches all six benchmarks × three splits into:

```
data/
├── searchqa/{train,val,test}/items.json           # id manifest
├── docvqa/{train,val,test}/items.json             # id manifest + image paths
├── alfworld/{train,val,test}/items.json           # id manifest + gamefile paths
├── officeqa/{train,val,test}/items.csv            # full QA
├── spreadsheetbench/{train,val,test}/items.json   # full instructions
└── livemath/{train,val,test}/items.json           # full theorem QA
```

Each `run.sh` picks the right file automatically via `--split_dir`.

## Corpora that don't ship in the manifests

Three benchmarks only publish **id manifests**; the underlying corpora must
be fetched from each benchmark's official source:

| Benchmark | Manifest fields | Corpus source |
|---|---|---|
| **SearchQA** | `id` (question hash) | Original SearchQA dataset (~1.4M QA); download & re-shard as instructed by `download.py --instructions searchqa`. |
| **DocVQA**   | `id`, `questionId`, `docId`, `image_path` | `lmms-lab/DocVQA` on HuggingFace; `download.py --materialize docvqa` re-encodes the images into `data/docvqa_images/`. |
| **ALFWorld** | `id`, `gamefile` (absolute path) | `pip install alfworld[full]` then `alfworld-download`; the gamefile paths in the manifest use `~/.cache/alfworld/json_2.1.1/…`. |

The remaining three (**OfficeQA**, **SpreadsheetBench**, **LiveMath**) publish
the full content on HF and need no extra download.

## Split ratios (train : val : test)

| Benchmark        | Train | Val | Test | Ratio  |
|------------------|------:|----:|-----:|--------|
| SearchQA         |  400 |  200 | 1400 | 2:1:7  |
| DocVQA           |  107 |   53 |  374 | 2:1:7  |
| ALFWorld         |  200 |  140 |  134 | seed42 stratified |
| OfficeQA         |  162 |  161 |  463 | seed42 stratified |
| SpreadsheetBench |   80 |   39 |  281 | 2:1:7 (stratified by `instruction_type`, seed42) |
| LiveMath         |  ~18 |   ~9 |  ~61 | 2:1:7 (by month) |

(Filled in by `hf_dataset/build_hf_repo.py`.)
