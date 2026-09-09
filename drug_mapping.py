"""
RxNorm-style brand/generic normalization for FAERS drug names.

The mapping is deliberately data-driven: add aliases to
DRUG_ALIAS_TO_CANONICAL or suffixes to DRUG_SUFFIXES without changing the
signal-computation pipeline.  This is a lightweight demo mapping, not a full
RxNorm terminology service.
"""
from __future__ import annotations

from typing import Dict, Final

# Brand / alias -> canonical generic. Keys and values are uppercase.
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
    # Identity entries make canonical generics discoverable via the API.
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

# Repeatedly removed from the end, longest first. This handles values such as
# "METFORMIN HYDROCHLORIDE TABLETS" as well as the common abbreviated salts.
DRUG_SUFFIXES: Final[tuple[str, ...]] = tuple(sorted({
    "EXTENDED RELEASE",
    "HYDROCHLORIDE",
    "HYDROBROMIDE",
    "MONOHYDRATE",
    "POTASSIUM",
    "PHOSPHATE",
    "SUCCINATE",
    "TARTRATE",
    "MESYLATE",
    "BESYLATE",
    "MALEATE",
    "ACETATE",
    "CALCIUM",
    "SODIUM",
    "SULFATE",
    "CAPSULES",
    "CAPSULE",
    "TABLETS",
    "TABLET",
    "HCL",
}, key=len, reverse=True))


def strip_drug_suffixes(name: str) -> str:
    """Uppercase a drug string and remove known trailing salts/formulations."""
    cleaned = " ".join(str(name).strip().upper().split())
    changed = True
    while cleaned and changed:
        changed = False
        for suffix in DRUG_SUFFIXES:
            marker = f" {suffix}"
            if cleaned.endswith(marker):
                cleaned = cleaned[:-len(marker)].strip()
                changed = True
                break
    return cleaned


def canonicalize_drug(name: str) -> str:
    """Normalize salts/formulations, then map an alias to its canonical generic."""
    if name is None:
        return name
    key = strip_drug_suffixes(name)
    return DRUG_ALIAS_TO_CANONICAL.get(key, key)


def drug_map_summary() -> dict:
    """Return alias groups and supported suffix stripping for API/UI display."""
    groups: Dict[str, list[str]] = {}
    for alias, canonical in sorted(DRUG_ALIAS_TO_CANONICAL.items()):
        groups.setdefault(canonical, [])
        if alias != canonical and alias not in groups[canonical]:
            groups[canonical].append(alias)
    aliases = {
        canonical: sorted(values)
        for canonical, values in sorted(groups.items())
        if values
    }
    return {
        "alias_count": sum(len(values) for values in aliases.values()),
        "canonical_count": len(groups),
        "map": aliases,
        "stripped_suffixes": list(DRUG_SUFFIXES),
    }
