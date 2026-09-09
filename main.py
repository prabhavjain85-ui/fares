"""
Vercel-deployable FastAPI UI for FAERS drug–ADR signal detection.

Multi-step workflow: Dataset → Choose drug → Per-drug / overview ADR results.
Prefers committed sample_data/*.csv when present; falls back to in-memory generation.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from faers_signal_detection import (
    build_case_level_table,
    compute_disproportionality,
    load_table,
    normalize_drug_name,
)
from make_sample_data import generate_sample_dataframes

app = FastAPI(
    title="FAERS ADR Signal Detection",
    description="Per-drug ADR disproportionality (PRR / ROR) on synthetic FAERS-style sample data.",
    version="2.0.0",
)

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "sample_data"
DEMO_CSV = SAMPLE_DIR / "DEMO_sample.csv"
DRUG_CSV = SAMPLE_DIR / "DRUG_sample.csv"
REAC_CSV = SAMPLE_DIR / "REAC_sample.csv"


def _jsonify_records(df) -> list[dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return []
    records = df.to_dict(orient="records")
    for row in records:
        for key, val in list(row.items()):
            if hasattr(val, "item"):
                row[key] = val.item()
            elif isinstance(val, bool):
                row[key] = bool(val)
    return records


@lru_cache(maxsize=1)
def _load_tables():
    """Prefer committed sample_data CSVs; fall back to in-memory generation."""
    if DEMO_CSV.is_file() and DRUG_CSV.is_file() and REAC_CSV.is_file():
        demo = load_table(str(DEMO_CSV))
        drug = load_table(str(DRUG_CSV))
        reac = load_table(str(REAC_CSV))
        source = "sample_data"
    else:
        demo, drug, reac = generate_sample_dataframes()
        source = "generated"
    return demo, drug, reac, source


@lru_cache(maxsize=1)
def _pairs_and_meta():
    demo, drug, reac, source = _load_tables()
    pairs = build_case_level_table(demo, drug, reac)
    meta = {
        "source": source,
        "demo_rows": int(len(demo)),
        "drug_rows": int(len(drug)),
        "reac_rows": int(len(reac)),
        "case_count": int(demo["primaryid"].nunique()) if "primaryid" in demo.columns else int(len(demo)),
        "pair_count": int(len(pairs)),
        "files": {
            "DEMO": "sample_data/DEMO_sample.csv",
            "DRUG": "sample_data/DRUG_sample.csv",
            "REAC": "sample_data/REAC_sample.csv",
        },
    }
    return pairs, meta


@lru_cache(maxsize=8)
def _all_signals(min_cases: int = 3) -> list[dict[str, Any]]:
    pairs, _ = _pairs_and_meta()
    signals = compute_disproportionality(pairs, min_cases=min_cases)
    return _jsonify_records(signals)


def _drug_stats() -> list[dict[str, Any]]:
    pairs, _ = _pairs_and_meta()
    signals = _all_signals(3)
    signal_by_drug: dict[str, int] = {}
    adr_by_drug: dict[str, int] = {}
    for row in signals:
        d = row["drug"]
        adr_by_drug[d] = adr_by_drug.get(d, 0) + 1
        if row.get("signal_detected"):
            signal_by_drug[d] = signal_by_drug.get(d, 0) + 1

    counts = (
        pairs.groupby("drugname")["primaryid"]
        .nunique()
        .reset_index(name="report_count")
        .sort_values("drugname")
    )
    out = []
    for _, row in counts.iterrows():
        name = row["drugname"]
        out.append({
            "drug": name,
            "report_count": int(row["report_count"]),
            "adr_count": int(adr_by_drug.get(name, 0)),
            "signal_count": int(signal_by_drug.get(name, 0)),
        })
    return out


INDEX_HTML = (
    (ROOT / "workflow.html").read_text(encoding="utf-8")
    if (ROOT / "workflow.html").is_file()
    else "<!DOCTYPE html><html><body><h1>Step 1 Dataset</h1><p>workflow.html missing from bundle.</p></body></html>"
)



@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dataset")
def api_dataset() -> JSONResponse:
    _, meta = _pairs_and_meta()
    drugs = _drug_stats()
    payload = {
        **meta,
        "drug_count": len(drugs),
        "drugs": [d["drug"] for d in drugs],
    }
    return JSONResponse(payload)


@app.get("/api/drugs")
def api_drugs() -> JSONResponse:
    drugs = _drug_stats()
    return JSONResponse({"count": len(drugs), "drugs": drugs})


@app.get("/api/drugs/{drug_name}/adrs")
def api_drug_adrs(
    drug_name: str,
    min_cases: int = Query(3, ge=1, le=100, description="Minimum case count for a pair"),
    signals_only: bool = Query(False, description="Return only flagged signals"),
) -> JSONResponse:
    name = normalize_drug_name(unquote(drug_name))
    results = [r for r in _all_signals(min_cases) if r["drug"] == name]
    if signals_only:
        results = [r for r in results if r.get("signal_detected")]
    if not results and name not in {d["drug"] for d in _drug_stats()}:
        raise HTTPException(status_code=404, detail=f"Drug not found: {drug_name}")
    return JSONResponse({
        "drug": name,
        "min_cases": min_cases,
        "signals_only": signals_only,
        "count": len(results),
        "results": results,
    })


@app.get("/api/signals")
def api_signals(
    min_cases: int = Query(3, ge=1, le=100, description="Minimum case count for a pair"),
    signals_only: bool = Query(False, description="Return only flagged signals"),
    drug: str | None = Query(None, description="Optional drug filter"),
) -> JSONResponse:
    results = _all_signals(min_cases)
    if drug:
        want = normalize_drug_name(drug)
        results = [r for r in results if r["drug"] == want]
    if signals_only:
        results = [r for r in results if r.get("signal_detected")]
    return JSONResponse({
        "min_cases": min_cases,
        "signals_only": signals_only,
        "drug": normalize_drug_name(drug) if drug else None,
        "count": len(results),
        "results": results,
    })
