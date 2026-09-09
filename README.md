# FAERS Drug–ADR Signal Detection

A disproportionality-analysis pipeline for detecting adverse drug reaction
(ADR) signals, built on the FDA FAERS data schema (DEMO / DRUG / REAC tables
joined on `primaryid`).

## Files

- `faers_signal_detection.py` — main pipeline: loads FAERS-style tables,
  normalizes drug names and MedDRA terms, and computes **PRR**, **ROR**,
  chi-square, and 95% confidence intervals for every drug–event pair.
- `make_sample_data.py` — generates a small synthetic dataset (in FAERS
  schema) with a few known signals baked in, so you can test the pipeline
  immediately without downloading real data.
- `sample_data/` — output of the above (DEMO/DRUG/REAC CSVs).
- `signals.csv` — example output from running the pipeline on the sample data.

## Quick start

```bash
pip install pandas numpy scipy

# 1. generate test data (or skip this and point at real FAERS files, see below)
python make_sample_data.py

# 2. run signal detection
python faers_signal_detection.py \
    --demo sample_data/DEMO_sample.csv \
    --drug sample_data/DRUG_sample.csv \
    --reac sample_data/REAC_sample.csv \
    --min-cases 3 \
    --out signals.csv
```

Optional: filter to a single drug with `--drug-filter WARFARIN`.

## Using real FAERS data

Download quarterly ASCII files from the FDA:
https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-latest-quarterly-data-files

Each quarter's zip contains `DEMOyyQq.txt`, `DRUGyyQq.txt`, `REACyyQq.txt`
(pipe- or `$`-delimited, matching this pipeline's expected columns:
`primaryid`, `drugname`, `role_cod`, `pt`). Just point the `--demo/--drug/--reac`
flags at those files directly — no schema changes needed. Note: a single
quarter is ~1-2 GB uncompressed; for multi-quarter analysis you'll want to
concatenate files first and consider loading into DuckDB/Postgres rather than
pandas for memory reasons.

## How the statistics work

For each drug–event pair, a 2×2 contingency table is built:

|                    | Event of interest | All other events |
|--------------------|-------------------|-------------------|
| Drug of interest   | a                  | b                 |
| All other drugs    | c                  | d                 |

- **PRR** = (a/(a+b)) / (c/(c+d)) — how much more often this event is
  reported for this drug vs. all other drugs.
- **ROR** = (a×d) / (b×c) — odds-ratio equivalent, generally preferred
  statistically (more robust CI behavior).
- **Chi-square** (Yates-corrected) tests whether the association is
  statistically significant.
- A **signal** is flagged using the standard FDA/MHRA convention:
  PRR ≥ 2, chi-square ≥ 4, and case count ≥ 3 (the last is configurable via
  `--min-cases`).

## Known limitations / next steps

- **Reporting bias**: FAERS is spontaneous-report data — it reflects what
  gets reported, not true incidence. Signals need clinical review, not
  automatic trust.
- **Drug name normalization** here is basic (uppercase + salt-suffix
  stripping). For production use, map names through **RxNorm** to properly
  consolidate brand names, combination products, and generics.
- **MedDRA hierarchy** isn't used — this treats each Preferred Term
  independently. Grouping into MedDRA System Organ Classes / High-Level
  Terms would catch related-but-differently-worded reactions.
- **Confounding by indication** isn't controlled for (e.g., a drug given to
  sicker patients will show inflated signals for unrelated events). Stratified
  or multivariate methods (e.g., logistic regression, BCPNN) handle this
  better than simple PRR/ROR.
- No temporal analysis — trending signal strength over report quarters would
  help catch emerging safety issues.
