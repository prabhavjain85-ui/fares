"""
Generates small synthetic datasets that mimic the FDA FAERS file schema
(DEMO / DRUG / REAC tables joined on primaryid) so the pipeline can be
tested without downloading the real (multi-GB) FAERS quarterly files.

Real FAERS ASCII data: https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-latest-quarterly-data-files
Files are pipe-delimited ($ in older quarters), named e.g. DEMO24Q1.txt,
DRUG24Q1.txt, REAC24Q1.txt. Column names match what's used below.
"""
import pandas as pd
import numpy as np
import random

random.seed(42)
np.random.seed(42)

N_CASES = 4000

drugs = [
    "IBUPROFEN", "ATORVASTATIN", "METFORMIN", "LISINOPRIL", "OMEPRAZOLE",
    "WARFARIN", "SIMVASTATIN", "AMOXICILLIN", "CLOPIDOGREL", "PREDNISONE",
]

reactions = [
    "NAUSEA", "HEADACHE", "RASH", "DIZZINESS", "FATIGUE", "VOMITING",
    "MYALGIA", "PRURITUS", "DYSPNOEA", "GASTROINTESTINAL HAEMORRHAGE",
    "ANGIOEDEMA", "ANAPHYLACTIC REACTION", "HEPATIC FAILURE", "RHABDOMYOLYSIS",
]

# Bake in a few "true" signals so PRR/ROR has something real to detect:
# WARFARIN -> GASTROINTESTINAL HAEMORRHAGE, CLOPIDOGREL -> GASTROINTESTINAL HAEMORRHAGE,
# SIMVASTATIN -> RHABDOMYOLYSIS, AMOXICILLIN -> ANAPHYLACTIC REACTION
boosted_pairs = {
    ("WARFARIN", "GASTROINTESTINAL HAEMORRHAGE"): 0.35,
    ("CLOPIDOGREL", "GASTROINTESTINAL HAEMORRHAGE"): 0.30,
    ("SIMVASTATIN", "RHABDOMYOLYSIS"): 0.25,
    ("AMOXICILLIN", "ANAPHYLACTIC REACTION"): 0.20,
    ("PREDNISONE", "HEPATIC FAILURE"): 0.15,
}

demo_rows, drug_rows, reac_rows = [], [], []

for case_id in range(1, N_CASES + 1):
    primaryid = 100000 + case_id
    age = np.random.randint(18, 90)
    sex = random.choice(["M", "F"])
    event_dt = f"2024{random.randint(1,4):02d}{random.randint(1,28):02d}"
    demo_rows.append({
        "primaryid": primaryid, "caseid": case_id, "age": age,
        "sex": sex, "event_dt": event_dt,
        "occr_country": "US",
    })

    case_drugs = random.sample(drugs, k=random.randint(1, 2))
    for d in case_drugs:
        drug_rows.append({"primaryid": primaryid, "caseid": case_id, "drugname": d, "role_cod": "PS"})

    n_reac = random.randint(1, 3)
    case_reactions = set(random.sample(reactions, k=n_reac))

    # inject boosted signal reactions probabilistically
    for d in case_drugs:
        for (bd, br), p in boosted_pairs.items():
            if d == bd and random.random() < p:
                case_reactions.add(br)

    for r in case_reactions:
        reac_rows.append({"primaryid": primaryid, "caseid": case_id, "pt": r})

demo = pd.DataFrame(demo_rows)
drug = pd.DataFrame(drug_rows)
reac = pd.DataFrame(reac_rows)

demo.to_csv("sample_data/DEMO_sample.csv", index=False)
drug.to_csv("sample_data/DRUG_sample.csv", index=False)
reac.to_csv("sample_data/REAC_sample.csv", index=False)

print(f"DEMO: {len(demo)} rows | DRUG: {len(drug)} rows | REAC: {len(reac)} rows")
print("Written to sample_data/")
