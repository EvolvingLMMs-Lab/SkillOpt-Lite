# Data

## Where splits live

Benchmark train/val/test splits are hosted as a single **multi-config**
HuggingFace dataset:

- Repo: [`yshenaw/SkillOpt_Lite_Benchmarks`](https://huggingface.co/datasets/yshenaw/SkillOpt_Lite_Benchmarks)
- Configs: `searchqa`, `docvqa`, `alfworld`, `officeqa`, `spreadsheetbench`, `livemath`
- Splits per config: `train`, `val`, `test`

You can load them directly with `datasets`:

```python
from datasets import load_dataset
ds = load_dataset("yshenaw/SkillOpt_Lite_Benchmarks", "livemath", split="val")
print(ds[0])
```

For SkillOpt_Lite itself, `data/download.py` mirrors the HF layout into local
files that each `run.sh` expects.

## Hydrating locally

```bash
python data/download.py                     # all six benchmarks
python data/download.py --config livemath   # one benchmark
python data/download.py --config alfworld --instructions
```

Result:

```
data/
├── searchqa/{train,val,test}/items.json
├── docvqa/{train,val,test}/items.json
├── alfworld/{train,val,test}/items.json
├── officeqa/{train,val,test}/items.csv
├── spreadsheetbench/{train,val,test}/items.json
└── livemath/{train,val,test}/items.json
```

## Manifest-only benchmarks

Three of the six benchmarks publish only **id manifests** because the
underlying data is either (a) too large for a dataset repo, (b)
license-restricted, or (c) requires runtime installation.

### SearchQA

Manifest rows: `{ "id": "<question-hash>" }`.
To hydrate the question text, follow the original SearchQA data card at
<https://github.com/nyu-dl/dl4ir-searchQA> (or the CodaLab mirror).
`download.py --instructions searchqa` prints current URLs.

### DocVQA

Manifest rows include `image_path` under `data/docvqa_images/`. Re-encode
from HF:

```bash
python data/download.py --materialize docvqa
```

This joins the id manifest with `lmms-lab/DocVQA` (config `DocVQA`, split
`validation`, ~5349 rows) and writes PNGs to `data/docvqa_images/`.
Idempotent — skips existing files.

### ALFWorld

Manifest rows include an absolute `gamefile` path under
`~/.cache/alfworld/json_2.1.1/…`. Install and download:

```bash
pip install alfworld[full]
alfworld-download                 # takes several minutes; ~1 GB
```

## Full-content benchmarks

**OfficeQA**, **SpreadsheetBench**, **LiveMathematicianBench** publish the
full QA content directly. `download.py` writes them to their canonical
paths (`items.csv` / `items.json`).

SpreadsheetBench additionally references spreadsheet files under
`spreadsheet/<id>/`. Grab those from the original repo at
<https://github.com/RUCKBReasoning/SpreadsheetBench>.

## Contributing new splits

If you add a benchmark, drop a `data/<env>/{train,val,test}/items.json`
(or `.csv`) with the same shape as the existing envs, then update
`hf_dataset/build_hf_repo.py` to include the new config. The HF dataset
card auto-picks it up from `configs:` YAML.
