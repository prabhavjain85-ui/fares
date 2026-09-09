# FAERS Drug–ADR Signal Detection

A disproportionality-analysis pipeline for detecting adverse drug reaction
(ADR) signals, built on the FDA FAERS data schema (DEMO / DRUG / REAC tables
joined on `primaryid`). Includes a polished **FastAPI** multi-step web workflow
that runs on **Vercel**, with **sample FAERS CSVs committed in the repo**.

## Files

- `faers_signal_detection.py` — main pipeline: loads FAERS-style tables,
  normalizes drug names and MedDRA terms, and computes **PRR**, **ROR**,
  chi-square, and 95% confidence intervals for every drug–event pair.
- `make_sample_data.py` — generates synthetic DEMO/DRUG/REAC data for
  10 drugs with known signals baked in.
- `sample_data/` — **included in the repo**: `DEMO_sample.csv`,
  `DRUG_sample.csv`, `REAC_sample.csv` (~200 cases). Regenerate anytime
  with `python make_sample_data.py`.
- `signals.csv` — example output from running the pipeline on the sample data.
- `main.py` — FastAPI app (`app`) with a browser workflow and JSON API.
- `workflow.html` — multi-step dark UI loaded by `main.py`.
- `vercel.json` — Vercel function config (`maxDuration` for the Python entrypoint).

## Web workflow

Open the UI and walk a product-style flow:

1. **Dataset** — confirms sample FAERS DEMO / DRUG / REAC is loaded (row counts).
2. **Choose drug** — grid of all sample drugs (IBUPROFEN, ATORVASTATIN,
   METFORMIN, LISINOPRIL, OMEPRAZOLE, WARFARIN, SIMVASTATIN, AMOXICILLIN,
   CLOPIDOGREL, PREDNISONE) plus an **All drugs** overview.
3. **Results** — polished ADR table with PRR / ROR / χ² / cases / signal badges,
   sorted by PRR, with filters (signals only, min cases). Auto-loads on open.

## Quick start (CLI)

```bash
pip install -r requirements.txt

# sample_data/ CSVs are already committed; regenerate if you like:
python make_sample_data.py

python faers_signal_detection.py \
    --demo sample_data/DEMO_sample.csv \
    --drug sample_data/DRUG_sample.csv \
    --reac sample_data/REAC_sample.csv \
    --min-cases 3 \
    --out signals.csv
```

Optional: filter to a single drug with `--drug-filter WARFARIN`.

## Local web UI

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://127.0.0.1:8000 — the workflow auto-loads the dataset and drug picker.

### API

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Liveness |
| `GET /api/dataset` | Row counts + source (`sample_data` or generated) |
| `GET /api/drugs` | All drugs with report / ADR / signal counts |
| `GET /api/drugs/{name}/adrs` | Per-drug ADR rows (`min_cases`, `signals_only`) |
| `GET /api/signals` | Overview of pairs (`min_cases`, `signals_only`, optional `drug`) |

The app prefers committed `sample_data/*.csv` and falls back to in-memory
`generate_sample_dataframes()` if the CSVs are missing.

## Deploy on Vercel

1. Push this repo to GitHub.
2. In [Vercel](https://vercel.com): **Add New Project** → import this GitHub repo.
3. Framework preset: **FastAPI** / **Python** (auto-detected from `main.py`).
4. Root Directory: `.` (project root).
5. Deploy. Vercel installs `requirements.txt` and serves the `app` instance in `main.py`.

`vercel.json` sets `maxDuration: 60`. Committed sample CSVs ship with the
function; if absent at runtime, the app generates equivalent frames in memory.

## Using real FAERS data

Download quarterly ASCII files from the FDA:
https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-latest-quarterly-data-files

Each quarter's zip contains `DEMOyyQq.txt`, `DRUGyyQq.txt`, `REACyyQq.txt`
(pipe- or `$`-delimited, matching this pipeline's expected columns:
`primaryid`, `drugname`, `role_cod`, `pt`). Point `--demo/--drug/--reac`
at those files directly. A single quarter is ~1–2 GB uncompressed.

## How the statistics work

For each drug–event pair, a 2×2 contingency table is built:

|                    | Event of interest | All other events |
|--------------------|-------------------|-------------------|
| Drug of interest   | a                  | b                 |
| All other drugs    | c                  | d                 |

- **PRR** = (a/(a+b)) / (c/(c+d))
- **ROR** = (a×d) / (b×c)
- **Chi-square** (Yates-corrected) for significance
- A **signal** uses the FDA/MHRA convention: PRR ≥ 2, chi-square ≥ 4,
  and case count ≥ 3 (`--min-cases` / UI filter)

## Known limitations

- FAERS is spontaneous-report data — signals need clinical review.
- Drug-name normalization is basic; production use should map through RxNorm.
- MedDRA hierarchy / SOCs are not grouped.
- Confounding by indication is not controlled for.
