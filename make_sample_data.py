"""
Generates small synthetic datasets that mimic the FDA FAERS file schema
(DEMO / DRUG / REAC tables joined on primaryid) so the pipeline can be
tested without downloading the real (multi-GB) FAERS quarterly files.

Real FAERS ASCII data: https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-latest-quarterly-data-files
Files are pipe-delimited ($ in older quarters), named e.g. DEMO24Q1.txt,
DRUG24Q1.txt, REAC24Q1.txt. Column names match what's used below.

Some rows intentionally use brand names (COUMADIN, LIPITOR, …) so the
RxNorm-style alias map in drug_mapping.py is demonstrable end-to-end.
"""
import os
import random

import numpy as np
import pandas as pd

N_CASES = 200

# Canonical generics used for signal baking
drugs = [
    "IBUPROFEN", "ATORVASTATIN", "METFORMIN", "LISINOPRIL", "OMEPRAZOLE",
    "WARFARIN", "SIMVASTATIN", "AMOXICILLIN", "CLOPIDOGREL", "PREDNISONE",
]

# When emitting DRUG rows, sometimes write a brand alias instead of the generic
BRAND_EMIT = {
    "WARFARIN": ["WARFARIN", "COUMADIN", "COUMADIN"],
    "ATORVASTATIN": ["ATORVASTATIN", "LIPITOR", "LIPITOR"],
    "METFORMIN": ["METFORMIN", "GLUCOPHAGE"],
    "OMEPRAZOLE": ["OMEPRAZOLE", "PRILOSEC", "LOSEC"],
    "CLOPIDOGREL": ["CLOPIDOGREL", "PLAVIX"],
    "SIMVASTATIN": ["SIMVASTATIN", "ZOCOR"],
    "AMOXICILLIN": ["AMOXICILLIN", "AMOXIL"],
}

reactions = [
    "NAUSEA", "HEADACHE", "RASH", "DIZZINESS", "FATIGUE", "VOMITING",
    "MYALGIA", "PRURITUS", "DYSPNOEA", "GASTROINTESTINAL HAEMORRHAGE",
    "ANGIOEDEMA", "ANAPHYLACTIC REACTION", "HEPATIC FAILURE", "RHABDOMYOLYSIS",
]

# Bake in a few "true" signals so PRR/ROR has something real to detect
# (keys are canonical generics — brands collapse via normalize_drug_name)
boosted_pairs = {
    ("WARFARIN", "GASTROINTESTINAL HAEMORRHAGE"): 0.35,
    ("CLOPIDOGREL", "GASTROINTESTINAL HAEMORRHAGE"): 0.30,
    ("SIMVASTATIN", "RHABDOMYOLYSIS"): 0.25,
    ("AMOXICILLIN", "ANAPHYLACTIC REACTION"): 0.20,
    ("PREDNISONE", "HEPATIC FAILURE"): 0.15,
}


def _emit_drug_name(canonical: str) -> str:
    choices = BRAND_EMIT.get(canonical, [canonical])
    return random.choice(choices)


def generate_sample_dataframes(n_cases: int = N_CASES, seed: int = 42):
    """Return (demo, drug, reac) DataFrames with deterministic synthetic FAERS data."""
    random.seed(seed)
    np.random.seed(seed)

    demo_rows, drug_rows, reac_rows = [], [], []

    for case_id in range(1, n_cases + 1):
        primaryid = 100000 + case_id
        age = np.random.randint(18, 90)
        sex = random.choice(["M", "F"])
        event_dt = f"2024{random.randint(1, 4):02d}{random.randint(1, 28):02d}"
        demo_rows.append({
            "primaryid": primaryid, "caseid": case_id, "age": age,
            "sex": sex, "event_dt": event_dt,
            "occr_country": "US",
        })

        case_drugs = random.sample(drugs, k=random.randint(1, 2))
        for d in case_drugs:
            drug_rows.append({
                "primaryid": primaryid, "caseid": case_id,
                "drugname": _emit_drug_name(d), "role_cod": "PS",
            })

        n_reac = random.randint(1, 3)
        case_reactions = set(random.sample(reactions, k=n_reac))

        for d in case_drugs:
            for (bd, br), p in boosted_pairs.items():
                if d == bd and random.random() < p:
                    case_reactions.add(br)

        for r in case_reactions:
            reac_rows.append({"primaryid": primaryid, "caseid": case_id, "pt": r})

    return pd.DataFrame(demo_rows), pd.DataFrame(drug_rows), pd.DataFrame(reac_rows)


def main():
    demo, drug, reac = generate_sample_dataframes()
    os.makedirs("sample_data", exist_ok=True)
    demo.to_csv("sample_data/DEMO_sample.csv", index=False)
    drug.to_csv("sample_data/DRUG_sample.csv", index=False)
    reac.to_csv("sample_data/REAC_sample.csv", index=False)
    print(f"DEMO: {len(demo)} rows | DRUG: {len(drug)} rows | REAC: {len(reac)} rows")
    brands = drug["drugname"].value_counts()
    print("Drug name frequencies (includes brands before canonicalization):")
    print(brands.to_string())
    print("Written to sample_data/")


if __name__ == "__main__":
    main()
