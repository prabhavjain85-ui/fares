# FAERS Drug–ADR Signal Detection

A disproportionality-analysis pipeline for detecting adverse drug reaction
(ADR) signals, built on the FDA FAERS data schema (DEMO / DRUG / REAC tables
joined on `primaryid`). Includes a polished multi-step web workflow with a
**static frontend** (Vercel) and a **FastAPI** computation backend (Railway,
Render, Fly.io, or local uvicorn), with **sample FAERS CSVs committed in the repo**.

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
- `main.py` — FastAPI API backend (ingest / reset / compare / signals).
- `workflow.html` — source for the multi-step UI (upload, single-drug, compare, SVG charts).
- `public/index.html` — static workflow UI deployed to Vercel.
- `public/config.js` — sets `window.FARES_API_BASE_URL` for cross-origin API calls.
- `vercel.json` — static-only Vercel config (`outputDirectory: public`).
- `Procfile` — process entry for Railway/Render (`uvicorn` on `0.0.0.0:$PORT`).

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

### Upload limits & backend memory

- Each uploaded file is capped at **~5 MB** (`413` if larger; `400` on parse /
  missing columns).
- Uploaded frames are stored in **module-level process memory** and LRU signal
  caches are cleared after ingest/reset.
- On a hosted Python backend, uploads persist for the lifetime of the process
  (until reset or restart). Prefer small extracts for demos; for large quarterly
  FAERS files use the CLI locally.

## Deployment architecture

The app is split into two deploy targets:

| Component | Host | Serves |
|-----------|------|--------|
| **Frontend** | Vercel | Static files from `public/` (`index.html`, `config.js`) |
| **Backend** | Railway / Render / Fly.io / local | `main.py` FastAPI API + sample data |

```
Browser (Vercel)  ──fetch──▶  Python host (FastAPI)
  public/index.html              main.py + sample_data/
  public/config.js               /api/*
```

### 1. Deploy the Python backend

1. Create a service on [Railway](https://railway.app), [Render](https://render.com),
   or [Fly.io](https://fly.io) pointing at this repo.
2. Start command (also in `Procfile`):

   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

3. Set environment variable **`FRONTEND_ORIGIN`** to your Vercel URL(s), comma-separated:

   ```
   FRONTEND_ORIGIN=https://your-app.vercel.app,https://your-app-*.vercel.app
   ```

   If unset, CORS allows only local dev origins (`localhost` / `127.0.0.1` on
   ports 8000, 3000, 5173) — not `*`.

4. Note the public backend URL (e.g. `https://fares-api.up.railway.app`).

### 2. Deploy the static frontend on Vercel

1. Push this repo to GitHub.
2. In [Vercel](https://vercel.com): **Add New Project** → import this GitHub repo.
3. Framework preset: **Other** (static). `vercel.json` sets `framework: null` and
   `outputDirectory: public`.
4. Before deploying, edit `public/config.js` and set the backend URL:

   ```js
   window.FARES_API_BASE_URL = 'https://your-python-backend.example.com';
   ```

   Leave empty (`''`) only when frontend and API share the same origin (local uvicorn).

5. Deploy. Vercel serves `public/index.html` for all routes; **no Python function**
   is created (`main.py` is listed in `.vercelignore`).

### Local full-stack (single origin)

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://127.0.0.1:8000 — uvicorn serves `workflow.html` and `config.js`; API
calls use same-origin (`FARES_API_BASE_URL` defaults to empty).

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
- Uploaded datasets on the backend are process-local (see above).
