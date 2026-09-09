"""
Vercel-deployable FastAPI UI for FAERS drug-ADR signal detection.

Committed sample data is the default. Small real FAERS extracts can be uploaded
and are retained only in this Python process until reset or process shutdown.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from drug_mapping import drug_map_summary
from faers_signal_detection import (
    build_case_level_table,
    compute_disproportionality,
    load_table,
    normalize_drug_name,
)
from make_sample_data import generate_sample_dataframes

app = FastAPI(
    title="FAERS ADR Signal Detection",
    description="FAERS drug-ADR disproportionality analysis with small-file ingest.",
    version="3.0.0",
)

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "sample_data"
DEMO_CSV = SAMPLE_DIR / "DEMO_sample.csv"
DRUG_CSV = SAMPLE_DIR / "DRUG_sample.csv"
REAC_CSV = SAMPLE_DIR / "REAC_sample.csv"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024

# Upload state is process-local by design. The lock makes state replacement and
# cache invalidation atomic within one server process.
_data_lock = RLock()
_uploaded_tables: tuple[Any, Any, Any] | None = None
_uploaded_files: dict[str, str] = {}


def _jsonify_records(df) -> list[dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return []
    records = df.to_dict(orient="records")
    for row in records:
        for key, value in list(row.items()):
            if hasattr(value, "item"):
                row[key] = value.item()
            elif isinstance(value, bool):
                row[key] = bool(value)
    return records


@lru_cache(maxsize=1)
def _load_tables():
    """Use the active upload, then committed samples, then generated samples."""
    with _data_lock:
        if _uploaded_tables is not None:
            demo, drug, reac = _uploaded_tables
            return demo, drug, reac, "upload", dict(_uploaded_files)

    if DEMO_CSV.is_file() and DRUG_CSV.is_file() and REAC_CSV.is_file():
        demo = load_table(str(DEMO_CSV))
        drug = load_table(str(DRUG_CSV))
        reac = load_table(str(REAC_CSV))
        source = "sample_data"
        files = {
            "DEMO": "sample_data/DEMO_sample.csv",
            "DRUG": "sample_data/DRUG_sample.csv",
            "REAC": "sample_data/REAC_sample.csv",
        }
    else:
        demo, drug, reac = generate_sample_dataframes()
        # Generated frames predate load_table's column cleanup, so normalize here.
        for frame in (demo, drug, reac):
            frame.columns = [str(column).strip().lower() for column in frame.columns]
        source = "generated"
        files = {"DEMO": "generated", "DRUG": "generated", "REAC": "generated"}
    return demo, drug, reac, source, files


@lru_cache(maxsize=1)
def _pairs_and_meta():
    demo, drug, reac, source, files = _load_tables()
    pairs = build_case_level_table(demo, drug, reac)
    meta = {
        "source": source,
        "demo_rows": int(len(demo)),
        "drug_rows": int(len(drug)),
        "reac_rows": int(len(reac)),
        "case_count": int(demo["primaryid"].nunique()),
        "pair_count": int(len(pairs)),
        "files": files,
    }
    return pairs, meta


@lru_cache(maxsize=8)
def _all_signals(min_cases: int = 3) -> list[dict[str, Any]]:
    pairs, _ = _pairs_and_meta()
    return _jsonify_records(compute_disproportionality(pairs, min_cases=min_cases))


def _invalidate_caches() -> None:
    _all_signals.cache_clear()
    _pairs_and_meta.cache_clear()
    _load_tables.cache_clear()


def _drug_stats() -> list[dict[str, Any]]:
    pairs, _ = _pairs_and_meta()
    signals = _all_signals(3)
    signal_by_drug: dict[str, int] = {}
    adr_by_drug: dict[str, int] = {}
    for row in signals:
        drug_name = row["drug"]
        adr_by_drug[drug_name] = adr_by_drug.get(drug_name, 0) + 1
        if row.get("signal_detected"):
            signal_by_drug[drug_name] = signal_by_drug.get(drug_name, 0) + 1

    if pairs.empty:
        return []
    counts = (
        pairs.groupby("drugname")["primaryid"]
        .nunique()
        .reset_index(name="report_count")
        .sort_values("drugname")
    )
    return [{
        "drug": row["drugname"],
        "report_count": int(row["report_count"]),
        "adr_count": int(adr_by_drug.get(row["drugname"], 0)),
        "signal_count": int(signal_by_drug.get(row["drugname"], 0)),
    } for _, row in counts.iterrows()]


async def _parse_upload(
    upload: UploadFile,
    table_name: str,
    required_columns: set[str],
):
    """Bound an upload, parse it through load_table, and validate its schema."""
    temporary_path: Path | None = None
    try:
        suffix = Path(upload.filename or "").suffix[:16]
        size = 0
        with NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"{table_name} exceeds the 5 MB upload limit",
                    )
                temporary.write(chunk)

        try:
            frame = load_table(str(temporary_path))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not parse {table_name}: {exc}",
            ) from exc

        missing = sorted(required_columns - set(frame.columns))
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"{table_name} missing required columns: {', '.join(missing)}",
            )
        return frame
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await upload.close()


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
    return JSONResponse({
        **meta,
        "drug_count": len(drugs),
        "drugs": [drug["drug"] for drug in drugs],
    })


@app.post("/api/ingest")
async def api_ingest(
    demo: UploadFile = File(..., description="FAERS DEMO CSV/TXT"),
    drug: UploadFile = File(..., description="FAERS DRUG CSV/TXT"),
    reac: UploadFile = File(..., description="FAERS REAC CSV/TXT"),
) -> JSONResponse:
    """Activate validated DEMO/DRUG/REAC uploads in this process."""
    parsed_demo = await _parse_upload(demo, "DEMO", {"primaryid"})
    parsed_drug = await _parse_upload(drug, "DRUG", {"primaryid", "drugname"})
    parsed_reac = await _parse_upload(reac, "REAC", {"primaryid", "pt"})

    global _uploaded_tables, _uploaded_files
    with _data_lock:
        _uploaded_tables = (
            parsed_demo.copy(deep=True),
            parsed_drug.copy(deep=True),
            parsed_reac.copy(deep=True),
        )
        _uploaded_files = {
            "DEMO": demo.filename or "uploaded DEMO",
            "DRUG": drug.filename or "uploaded DRUG",
            "REAC": reac.filename or "uploaded REAC",
        }
        _invalidate_caches()

    return api_dataset()


@app.post("/api/reset")
def api_reset() -> JSONResponse:
    """Discard process-local uploads and return to committed sample data."""
    global _uploaded_tables, _uploaded_files
    with _data_lock:
        _uploaded_tables = None
        _uploaded_files = {}
        _invalidate_caches()
    return api_dataset()


@app.get("/api/drug-map")
def api_drug_map() -> JSONResponse:
    return JSONResponse(drug_map_summary())


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
    results = [row for row in _all_signals(min_cases) if row["drug"] == name]
    if signals_only:
        results = [row for row in results if row.get("signal_detected")]
    if not results and name not in {drug["drug"] for drug in _drug_stats()}:
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
        wanted = normalize_drug_name(drug)
        results = [row for row in results if row["drug"] == wanted]
    if signals_only:
        results = [row for row in results if row.get("signal_detected")]
    return JSONResponse({
        "min_cases": min_cases,
        "signals_only": signals_only,
        "drug": normalize_drug_name(drug) if drug else None,
        "count": len(results),
        "results": results,
    })


@app.get("/api/compare")
def api_compare(
    drugs: str = Query(..., description="Comma-separated list of two or three drugs"),
    min_cases: int = Query(3, ge=1, le=100),
    signals_only: bool = Query(False),
) -> JSONResponse:
    """Return full per-drug rows and a matrix of events shared by selected drugs."""
    selected: list[str] = []
    for raw_name in drugs.split(","):
        raw_name = raw_name.strip()
        if not raw_name:
            continue
        canonical = normalize_drug_name(unquote(raw_name))
        if canonical not in selected:
            selected.append(canonical)
    if not 2 <= len(selected) <= 3:
        raise HTTPException(status_code=400, detail="Select two or three unique drugs")

    available = {drug["drug"] for drug in _drug_stats()}
    missing = [drug for drug in selected if drug not in available]
    if missing:
        raise HTTPException(status_code=404, detail=f"Drug not found: {', '.join(missing)}")

    rows = _all_signals(min_cases)
    if signals_only:
        rows = [row for row in rows if row.get("signal_detected")]
    selected_rows = {
        drug: [row for row in rows if row["drug"] == drug]
        for drug in selected
    }
    per_drug = [{
        "drug": drug,
        "count": len(selected_rows[drug]),
        "results": selected_rows[drug],
    } for drug in selected]

    by_event: dict[str, dict[str, dict[str, Any]]] = {}
    for drug, drug_rows in selected_rows.items():
        for row in drug_rows:
            by_event.setdefault(row["adverse_event"], {})[drug] = row

    matrix = []
    for event, event_rows in by_event.items():
        if len(event_rows) < 2:
            continue
        values = {}
        for drug in selected:
            row = event_rows.get(drug)
            values[drug] = None if row is None else {
                "case_count_a": row["case_count_a"],
                "PRR": row["PRR"],
                "ROR": row["ROR"],
                "chi_square": row["chi_square"],
                "signal_detected": row["signal_detected"],
            }
        matrix.append({
            "adverse_event": event,
            "drug_count": len(event_rows),
            "values": values,
        })
    matrix.sort(key=lambda row: (
        -row["drug_count"],
        -max(value["PRR"] for value in row["values"].values() if value is not None),
        row["adverse_event"],
    ))

    return JSONResponse({
        "drugs": selected,
        "min_cases": min_cases,
        "signals_only": signals_only,
        "per_drug": per_drug,
        "shared_event_count": len(matrix),
        "shared_event_matrix": matrix,
    })
