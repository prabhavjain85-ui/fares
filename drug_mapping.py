"""
RxNorm-style brand/generic alias map for demo FAERS drug names.

Maps common brand names (and a few spelling variants) to canonical generic
names used for signal aggregation. Salt/formulation stripping remains in
normalize_drug_name; this module supplies the alias → canonical step.
"""
from __future__ import annotations

from typing import Dict

# Brand / alias → canonical generic (all uppercase, post salt-strip keys)
DRUG_ALIAS_TO_CANONICAL: Dict[str, str] = {
    # Anticoagulants / antiplatelets
    "COUMADIN": "WARFARIN",
    "JANTOVEN": "WARFARIN",
    "PLAVIX": "CLOPIDOGREL",
    # Statins
    "LIPITOR": "ATORVASTATIN",
    "ZOCOR": "SIMVASTATIN",
    # Diabetes / GI / antibiotics / BP
    "GLUCOPHAGE": "METFORMIN",
    "PRILOSEC": "OMEPRAZOLE",
    "LOSEC": "OMEPRAZOLE",
    "AMOXIL": "AMOXICILLIN",
    "NORVASC": "AMLODIPINE",
    # Identity entries so the map is self-describing for generics already in sample
    "WARFARIN": "WARFARIN",
    "CLOPIDOGREL": "CLOPIDOGREL",
    "ATORVASTATIN": "ATORVASTATIN",
    "SIMVASTATIN": "SIMVASTATIN",
    "METFORMIN": "METFORMIN",
    "OMEPRAZOLE": "OMEPRAZOLE",
    "AMOXICILLIN": "AMOXICILLIN",
    "AMLODIPINE": "AMLODIPINE",
    "IBUPROFEN": "IBUPROFEN",
    "LISINOPRIL": "LISINOPRIL",
    "PREDNISONE": "PREDNISONE",
}


def canonicalize_drug(name: str) -> str:
    """Map a cleaned (uppercase, salt-stripped) drug string to its canonical form."""
    if name is None:
        return name
    key = str(name).strip().upper()
    return DRUG_ALIAS_TO_CANONICAL.get(key, key)


def drug_map_summary() -> dict:
    """Return alias groups for API/UI display (canonical → [aliases])."""
    groups: Dict[str, list] = {}
    for alias, canon in sorted(DRUG_ALIAS_TO_CANONICAL.items()):
        groups.setdefault(canon, [])
        if alias != canon and alias not in groups[canon]:
            groups[canon].append(alias)
    return {
        "alias_count": sum(len(v) for v in groups.values()),
        "canonical_count": len(groups),
        "map": {k: sorted(v) for k, v in sorted(groups.items()) if v},
    }
