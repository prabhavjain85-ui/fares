# FAERS Drug–ADR Signal Detection

A disproportionality-analysis pipeline for detecting adverse drug reaction
(ADR) signals, built on the FDA FAERS data schema (DEMO / DRUG / REAC tables
joined on `primaryid`). Includes a polished **FastAPI** multi-step web workflow
that runs on **Vercel**, with **sample FAERS CSVs committed in the repo**.

## Platform upgrades (v3)

1. **Real FAERS ingest** — upload DEMO / DRUG / REAC (CSV/TXT; comma / `$` / `|`)
   via the UI or `POST /api/ingest`. Uploads live in **process memory** only;
   use **Reset to sample** (`POST /api/reset`) to restore committed sample data.
2. **RxNorm-style drug mapping** — brand aliases (COUMADIN→WARFARIN, LIPITOR→
   ATORVASTATIN, …) collapse in `normalize_drug_name` via `drug_mapping.py`.
3. **Drug compare + charts** — select 2–3 drugs, `GET /api/compare`, side-by-side
   shared-ADR table, plus pure SVG bar charts (no npm).

## Files

- `faers_signal_detection.py` — main pipeline: loads FAERS-style tables,
  normalizes drug names (salts + brand→generic) and MedDRA terms, computes
  **PRR**, **ROR**, chi-square, and 95% CIs.
- `drug_mapping.py` — alias → canonical generic map used by normalization.
- `make_sample_data.py` — generates synthetic DEMO/DRUG/REAC data; intentionally
  emits some brand-name strings so mapping is demonstrable.
- `sample_data/` — **included in the repo**: `DEMO_sample.csv`,
  `DRUG_sample.csv`, `REAC_sample.csv` (~200 cases).
- `main.py` — FastAPI app with workflow UI + JSON API (ingest / reset / compare).
- `workflow.html` — multi-step dark UI (upload, single-drug, compare, SVG charts).
- `vercel.json` — Vercel function config (`maxDuration` for the Python entrypoint).

## Web workflow

1. **Dataset** — sample FAERS tables load by default. Optionally upload DEMO /
   DRUG / REAC extracts (≤ ~5 MB each) or reset to sample.
2. **Choose drug** — single-drug cards (canonical generics) or **Compare 2–3**
   mode; plus an **All drugs** overview.
3. **Results** — ADR table with PRR / ROR / χ² / cases / signal badges, filters,
   horizontal SVG bar chart of top PRR signals, and (in compare mode) shared-ADR
   bars across selected drugs.

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

Optional: filter to a single drug with `--drug-filter WARFARIN` (also matches
COUMADIN rows after canonicalization).

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
| `GET /api/dataset` | Row counts + `source` (`sample_data` \| `generated` \| `upload`) |
| `POST /api/ingest` | Multipart upload: fields `demo`, `drug`, `reac` (≤5 MB each) |
| `POST /api/reset` | Clear upload cache; restore sample/default |
| `GET /api/drug-map` | Brand/alias → canonical summary |
| `GET /api/drugs` | All drugs with report / ADR / signal counts |
| `GET /api/drugs/{name}/adrs` | Per-drug ADR rows (`min_cases`, `signals_only`) |
| `GET /api/signals` | Overview of pairs (`min_cases`, `signals_only`, optional `drug`) |
| `GET /api/compare` | `?drugs=WARFARIN,CLOPIDOGREL&min_cases=3&signals_only=false` — per-drug rows + shared-event matrix |

Required columns on ingest: DEMO `primaryid`; DRUG `primaryid`, `drugname`;
REAC `primaryid`, `pt`. `role_cod` is optional (when present, only PS/SS kept).

### Upload limits & Vercel memory

- Each uploaded file is capped at **~5 MB** (`413` if larger; `400` on parse /
  missing columns).
- Uploaded frames are stored in **module-level process memory** and LRU signal
  caches are cleared after ingest/reset.
- On **Vercel**, serverless memory is **ephemeral**: uploads do **not** persist
  across cold starts, scale-out to another instance, or redeploys. Prefer small
  extracts for demos; for large quarterly FAERS files use the CLI locally.

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
at those files directly, or upload a small extract via the web UI.

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
- Drug-name mapping is a demo alias table, not a full RxNorm service.
- MedDRA hierarchy / SOCs are not grouped.
- Confounding by indication is not controlled for.
- Uploaded datasets on Vercel are ephemeral (see above).
