"""
FAERS Adverse Drug Reaction Signal Detection Pipeline
======================================================

Computes disproportionality signals (PRR, ROR) for drug-adverse event pairs
from FDA FAERS-style data (DEMO / DRUG / REAC tables joined on primaryid).

Works on:
  1. The synthetic sample data in sample_data/ (run make_sample_data.py first), or
  2. Real FAERS quarterly ASCII files downloaded from:
     https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-latest-quarterly-data-files
     (Just point --demo/--drug/--reac at the real DEMOyyQq.txt / DRUGyyQq.txt /
      REACyyQq.txt files; they use the same column names, pipe-delimited.)

Usage:
    python faers_signal_detection.py \
        --demo sample_data/DEMO_sample.csv \
        --drug sample_data/DRUG_sample.csv \
        --reac sample_data/REAC_sample.csv \
        --min-cases 3 \
        --out signals.csv
"""
import argparse
import sys
import pandas as pd
import numpy as np
from scipy import stats


def load_table(path: str) -> pd.DataFrame:
    """Load a FAERS table, auto-detecting delimiter (real FAERS files use $ or |)."""
    for sep in [",", "$", "|", "\t"]:
        try:
            df = pd.read_csv(path, sep=sep, dtype=str, low_memory=False)
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    raise ValueError(f"Could not parse {path} with any known FAERS delimiter")


def normalize_drug_name(name: str) -> str:
    """Basic drug-name normalization: uppercase, strip whitespace/salts.
    For production use, map through RxNorm to consolidate brand -> generic names."""
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    # strip common salt/formulation suffixes for cleaner grouping
    for suffix in [" HYDROCHLORIDE", " HCL", " SODIUM", " SULFATE", " TABLETS", " CAPSULES"]:
        name = name.replace(suffix, "")
    return name.strip()


def normalize_pt(term: str) -> str:
    """Normalize MedDRA Preferred Term text."""
    if pd.isna(term):
        return term
    return str(term).strip().upper()


def build_case_level_table(demo: pd.DataFrame, drug: pd.DataFrame, reac: pd.DataFrame) -> pd.DataFrame:
    """Collapse to one row per (case, drug, reaction) — the unit disproportionality
    analysis is computed over."""
    drug = drug.copy()
    reac = reac.copy()

    drug["drugname"] = drug["drugname"].apply(normalize_drug_name)
    reac["pt"] = reac["pt"].apply(normalize_pt)

    # Keep only suspect/primary-suspect drugs (role_cod PS/SS) if that column exists —
    # concomitant drugs (C) and interacting drugs (I) shouldn't be blamed for the event.
    if "role_cod" in drug.columns:
        drug = drug[drug["role_cod"].isin(["PS", "SS"])]

    merged = drug.merge(reac, on="primaryid", how="inner", suffixes=("_drug", "_reac"))
    merged = merged.drop_duplicates(subset=["primaryid", "drugname", "pt"])
    return merged


def compute_disproportionality(pairs: pd.DataFrame, min_cases: int = 3) -> pd.DataFrame:
    """
    For each drug-event pair, build the standard 2x2 contingency table and
    compute PRR, ROR, chi-square, and 95% CIs.

                        Event of interest   All other events
    Drug of interest           a                   b
    All other drugs            c                   d

    PRR = (a/(a+b)) / (c/(c+d))
    ROR = (a*d) / (b*c)

    Common FAERS signal thresholds (FDA/MHRA convention): PRR >= 2, chi-square >= 4,
    and a (case count) >= 3 are jointly required to flag a signal.
    """
    total_reports = pairs["primaryid"].nunique()
    drug_totals = pairs.groupby("drugname")["primaryid"].nunique()
    event_totals = pairs.groupby("pt")["primaryid"].nunique()

    pair_counts = (
        pairs.groupby(["drugname", "pt"])["primaryid"]
        .nunique()
        .reset_index(name="a")
    )
    pair_counts = pair_counts[pair_counts["a"] >= min_cases]

    results = []
    for _, row in pair_counts.iterrows():
        drug_name, pt, a = row["drugname"], row["pt"], row["a"]
        drug_total = drug_totals[drug_name]
        event_total = event_totals[pt]

        b = drug_total - a                      # this drug, other events
        c = event_total - a                     # other drugs, this event
        d = total_reports - drug_total - event_total + a  # other drugs, other events

        if b <= 0 or c <= 0 or d <= 0:
            continue

        prr = (a / (a + b)) / (c / (c + d))
        ror = (a * d) / (b * c)

        # chi-square with Yates' continuity correction (standard for PRR signal detection)
        contingency = np.array([[a, b], [c, d]])
        chi2, p_value, _, _ = stats.chi2_contingency(contingency, correction=True)

        # 95% CI for ROR (log-scale, Woolf's method)
        se_log_ror = np.sqrt(1/a + 1/b + 1/c + 1/d)
        log_ror = np.log(ror)
        ror_ci_low = np.exp(log_ror - 1.96 * se_log_ror)
        ror_ci_high = np.exp(log_ror + 1.96 * se_log_ror)

        is_signal = (prr >= 2) and (chi2 >= 4) and (a >= min_cases)

        results.append({
            "drug": drug_name,
            "adverse_event": pt,
            "case_count_a": a,
            "drug_total_reports": drug_total,
            "event_total_reports": event_total,
            "PRR": round(prr, 3),
            "ROR": round(ror, 3),
            "ROR_95CI_low": round(ror_ci_low, 3),
            "ROR_95CI_high": round(ror_ci_high, 3),
            "chi_square": round(chi2, 3),
            "p_value": round(p_value, 6),
            "signal_detected": is_signal,
        })

    out = pd.DataFrame(results).sort_values("PRR", ascending=False)
    return out


def main():
    parser = argparse.ArgumentParser(description="FAERS drug-ADR signal detection (PRR/ROR)")
    parser.add_argument("--demo", required=True, help="Path to DEMO table (case demographics)")
    parser.add_argument("--drug", required=True, help="Path to DRUG table (case-drug links)")
    parser.add_argument("--reac", required=True, help="Path to REAC table (case-reaction links)")
    parser.add_argument("--min-cases", type=int, default=3, help="Minimum case count to consider a pair")
    parser.add_argument("--out", default="signals.csv", help="Output CSV path")
    parser.add_argument("--drug-filter", default=None, help="Only show signals for this drug (optional)")
    args = parser.parse_args()

    print("Loading tables...")
    demo = load_table(args.demo)
    drug = load_table(args.drug)
    reac = load_table(args.reac)
    print(f"  DEMO: {len(demo)} rows | DRUG: {len(drug)} rows | REAC: {len(reac)} rows")

    print("Building case-level drug-event pairs...")
    pairs = build_case_level_table(demo, drug, reac)
    print(f"  {len(pairs)} drug-event case pairs after cleaning")

    print("Computing PRR / ROR / chi-square signals...")
    signals = compute_disproportionality(pairs, min_cases=args.min_cases)

    if args.drug_filter:
        signals = signals[signals["drug"] == normalize_drug_name(args.drug_filter)]

    signals.to_csv(args.out, index=False)
    print(f"\nWrote {len(signals)} drug-event pairs to {args.out}")

    flagged = signals[signals["signal_detected"]]
    print(f"\n{len(flagged)} pairs meet FDA/MHRA-style signal threshold (PRR>=2, chi2>=4, cases>={args.min_cases}):\n")
    if len(flagged):
        print(flagged[["drug", "adverse_event", "case_count_a", "PRR", "ROR", "chi_square"]]
              .head(20).to_string(index=False))
    else:
        print("  (none — try lowering --min-cases or check data volume)")


if __name__ == "__main__":
    main()
