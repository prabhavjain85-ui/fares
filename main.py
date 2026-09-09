"""
Vercel-deployable FastAPI UI for FAERS drug–ADR signal detection.

Runs the existing disproportionality pipeline on synthetic sample data
(generated in-memory so the serverless bundle stays small). Sample CSVs
are also committed under sample_data/ for the offline CLI workflow.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from faers_signal_detection import build_case_level_table, compute_disproportionality
from make_sample_data import generate_sample_dataframes

app = FastAPI(
    title="FAERS ADR Signal Detection",
    description="Disproportionality analysis (PRR / ROR) on synthetic FAERS-style sample data.",
    version="1.0.0",
)


@lru_cache(maxsize=1)
def _sample_tables():
    return generate_sample_dataframes()


def run_analysis(min_cases: int = 3, signals_only: bool = False) -> list[dict[str, Any]]:
    demo, drug, reac = _sample_tables()
    pairs = build_case_level_table(demo, drug, reac)
    signals = compute_disproportionality(pairs, min_cases=min_cases)
    if signals_only and not signals.empty:
        signals = signals[signals["signal_detected"]]
    if signals.empty:
        return []
    # Convert numpy/pandas types for JSON
    records = signals.to_dict(orient="records")
    for row in records:
        for key, val in list(row.items()):
            if hasattr(val, "item"):
                row[key] = val.item()
            elif isinstance(val, bool):
                row[key] = bool(val)
    return records


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FAERS ADR Signal Detection</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --border: #2d3a4f;
      --text: #e7ecf3;
      --muted: #9aa8bc;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --signal: #22c55e;
      --nosignal: #64748b;
      --warn: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1e3a5f 0%, transparent 50%),
                  radial-gradient(900px 500px at 100% 0%, #1a2e1a 0%, transparent 45%),
                  var(--bg);
      color: var(--text);
      min-height: 100vh;
      line-height: 1.5;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 2rem 1.25rem 3rem; }
    header h1 { margin: 0 0 0.35rem; font-size: 1.75rem; letter-spacing: -0.02em; }
    header p { margin: 0; color: var(--muted); max-width: 48rem; }
    .badge {
      display: inline-block; margin-top: 0.75rem; padding: 0.2rem 0.55rem;
      border: 1px solid var(--border); border-radius: 999px; font-size: 0.75rem; color: var(--muted);
    }
    .panel {
      margin-top: 1.5rem; background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; padding: 1.1rem 1.2rem;
    }
    .controls {
      display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end;
    }
    label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.85rem; color: var(--muted); }
    input[type="number"] {
      width: 6rem; padding: 0.45rem 0.6rem; border-radius: 8px; border: 1px solid var(--border);
      background: var(--bg); color: var(--text);
    }
    .check { flex-direction: row; align-items: center; gap: 0.5rem; padding-bottom: 0.45rem; }
    button {
      padding: 0.55rem 1.1rem; border: none; border-radius: 8px; background: var(--accent);
      color: white; font-weight: 600; cursor: pointer;
    }
    button:hover { background: var(--accent-hover); }
    button:disabled { opacity: 0.6; cursor: wait; }
    .meta { margin-top: 0.85rem; color: var(--muted); font-size: 0.9rem; }
    .err { color: #f87171; margin-top: 0.75rem; }
    .table-wrap { overflow-x: auto; margin-top: 1rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th, td { padding: 0.55rem 0.65rem; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
    th { color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
    tr:hover td { background: rgba(59, 130, 246, 0.06); }
    .pill {
      display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600;
    }
    .pill.yes { background: rgba(34, 197, 94, 0.15); color: var(--signal); }
    .pill.no { background: rgba(100, 116, 139, 0.2); color: var(--nosignal); }
    footer { margin-top: 1.5rem; color: var(--muted); font-size: 0.8rem; }
    code { background: rgba(255,255,255,0.06); padding: 0.1rem 0.35rem; border-radius: 4px; }
    a { color: #93c5fd; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>FAERS ADR Signal Detection</h1>
      <p>
        Explore disproportionality signals (PRR, ROR, chi-square) for drug–adverse event pairs
        on synthetic FAERS-style DEMO / DRUG / REAC sample data. This is a demo for pharmacovigilance
        methods — not a clinical decision tool.
      </p>
      <span class="badge">Synthetic sample data · FDA/MHRA-style thresholds</span>
    </header>

    <section class="panel">
      <div class="controls">
        <label>
          Min cases
          <input id="minCases" type="number" min="1" max="50" value="3" />
        </label>
        <label class="check">
          <input id="signalsOnly" type="checkbox" checked />
          Signals only
        </label>
        <button id="runBtn" type="button">Run analysis</button>
      </div>
      <div class="meta" id="meta">Click <strong>Run analysis</strong> to compute signals.</div>
      <div class="err" id="err" hidden></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Drug</th>
              <th>Event</th>
              <th>PRR</th>
              <th>ROR</th>
              <th>Chi²</th>
              <th>Cases</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody id="tbody">
            <tr><td colspan="7" style="color:var(--muted)">No results yet.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <footer>
      Signal rule: PRR ≥ 2, chi-square ≥ 4, and case count ≥ min-cases.
      CLI: <code>python make_sample_data.py</code> then
      <code>python faers_signal_detection.py --demo sample_data/DEMO_sample.csv ...</code>
      · API: <a href="/api/signals"><code>/api/signals</code></a>
    </footer>
  </div>
  <script>
    const tbody = document.getElementById("tbody");
    const meta = document.getElementById("meta");
    const err = document.getElementById("err");
    const runBtn = document.getElementById("runBtn");

    function fmt(n) {
      if (typeof n !== "number") return n;
      return Number.isInteger(n) ? String(n) : n.toFixed(3);
    }

    async function run() {
      err.hidden = true;
      runBtn.disabled = true;
      meta.textContent = "Running analysis on sample data…";
      const minCases = document.getElementById("minCases").value || 3;
      const signalsOnly = document.getElementById("signalsOnly").checked;
      const qs = new URLSearchParams({
        min_cases: String(minCases),
        signals_only: String(signalsOnly),
      });
      try {
        const res = await fetch("/api/signals?" + qs.toString());
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        const rows = data.results || [];
        meta.textContent = `${rows.length} pair(s) · min_cases=${data.min_cases} · signals_only=${data.signals_only}`;
        if (!rows.length) {
          tbody.innerHTML = '<tr><td colspan="7" style="color:var(--muted)">No pairs matched the filters.</td></tr>';
          return;
        }
        tbody.innerHTML = rows.map(r => `
          <tr>
            <td>${r.drug}</td>
            <td>${r.adverse_event}</td>
            <td>${fmt(r.PRR)}</td>
            <td>${fmt(r.ROR)}</td>
            <td>${fmt(r.chi_square)}</td>
            <td>${r.case_count_a}</td>
            <td><span class="pill ${r.signal_detected ? "yes" : "no"}">${r.signal_detected ? "Yes" : "No"}</span></td>
          </tr>
        `).join("");
      } catch (e) {
        err.hidden = false;
        err.textContent = "Failed to run analysis: " + e.message;
        meta.textContent = "Error";
      } finally {
        runBtn.disabled = false;
      }
    }

    runBtn.addEventListener("click", run);
    // Auto-run on load for a useful first paint
    run();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/signals")
def api_signals(
    min_cases: int = Query(3, ge=1, le=100, description="Minimum case count for a pair"),
    signals_only: bool = Query(False, description="Return only flagged signals"),
) -> JSONResponse:
    results = run_analysis(min_cases=min_cases, signals_only=signals_only)
    return JSONResponse({
        "min_cases": min_cases,
        "signals_only": signals_only,
        "count": len(results),
        "results": results,
    })
