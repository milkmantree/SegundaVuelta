# Segunda Vuelta — Peru 2026 Live Election Results System

A production-grade election intelligence platform targeting the ONPE (Oficina Nacional de Procesos Electorales) API. Scrapes live vote tallies across all 2,312 Peruvian districts, aggregates results in real time, and projects final outcomes using two independent statistical models — all surfaced through a self-contained web dashboard.

---

## What It Does

**Scrapes** → **Aggregates** → **Projects** → **Displays**

1. Five parallel workers scrape ONPE's district-level (`ubigeo`) API concurrently, with smart caching to avoid redundant requests
2. Raw records are merged and aggregated into hierarchical JSON files (district → province → department → national)
3. Two independent projection models run live against the incoming data:
   - **Propagation model** — dynamic stratified sampling with per-district stability fallback
   - **Migration model** — Hellinger-clustered WLS regression predicting how first-round votes migrate to the two finalists
4. A Flask dashboard serves both rounds of results, both model projections with 95% confidence intervals, and department-level breakdowns

---

## Project Layout

```
segundaVuelta/
│
├── paths.py                        # Single source of truth for all file paths
├── requirements.txt
│
├── pipeline/                       # Data ingestion
│   ├── run_scraper.py              # Orchestrator — spawns 5 workers, live TUI
│   ├── scraper.py                  # Worker — scrapes one ubigeo chunk
│   ├── merge.py                    # Merges per-worker JSONL into unified file
│   └── aggregate.py                # Builds district/province/dept/ambito aggregates
│
├── models/                         # Statistical projection
│   ├── propagation.py              # Dynamic stratified sampling, 95% CI
│   └── migration.py                # Hellinger-clustered WLS regression, 95% CI
│
├── web/                            # Dashboard server
│   ├── server.py                   # Flask API
│   ├── generate_static.py          # Generates self-contained dashboard_static.html
│   └── templates/
│       └── dashboard.html          # Single-file frontend (Chart.js, inline CSS/JS)
│
├── actas/                          # JEE acta tracker (challenged ballots)
│   ├── run_actas.py                # Orchestrator — 5 parallel workers
│   └── worker.py                   # Worker — fetches acta status per ubigeo
│
├── analysis/                       # Standalone analysis scripts
│   ├── acid_test.py                # Worst-case scenario stress test
│   ├── exterior_sensitivity.py     # 2D sensitivity table for overseas votes
│   ├── exterior_comparison.py      # 2026 vs 2021 exterior results comparison
│   ├── simulate.py                 # Generates synthetic segunda vuelta data
│   ├── compare_actas_rounds.py     # R1 vs R2 actas coverage by department
│   ├── actas_by_dept_at_coverage.py
│   └── watch_exterior.py
│
└── data/
    ├── inputs/                     # Static reference files — never modified at runtime
    │   ├── onpe_ubigeo_map.json    # All 2,312 districts with ubigeo codes
    │   ├── ubigeo_votos_habiles.json  # Eligible voter counts per district
    │   ├── migration_cluster_map.json # Precomputed Hellinger clusters (built once)
    │   └── segunda_vuelta_2021.csv    # 2021 runoff exterior results (analysis only)
    │
    ├── round1/                     # FROZEN — complete primera vuelta archive
    │   ├── agg_ambito.json
    │   ├── agg_departamental.json
    │   ├── agg_provincial.json
    │   ├── agg_distrital.json
    │   └── idx_codigo_nombre_partido.json
    │
    └── round2/                     # LIVE — updated by pipeline on election night
        └── (same schema as round1/)
```

Runtime directories (`log/`, `backups/`) and pipeline output files (`onpe_combined_results.jsonl`, `prediction_history.jsonl`) are gitignored.

---

## Architecture

```
ONPE API
    │
    ▼
pipeline/run_scraper.py     ← 5 parallel workers, live TUI dashboard
    │ writes
    ▼
log/onpe_combined_results_worker_N.jsonl
    │
pipeline/merge.py           ← merges worker outputs
    │
onpe_combined_results.jsonl
    │
pipeline/aggregate.py       ← builds hierarchical aggregates
    │
data/round2/                ← live segunda vuelta data
    │
    ├── models/propagation.py   ← stratified projection, 95% CI
    ├── models/migration.py     ← WLS migration model, 95% CI
    └── web/server.py           ← Flask API + dashboard
```

`data/round1/` holds the complete frozen primera vuelta archive and is never modified by the pipeline.

---

## Statistical Models

### Propagation Model (`models/propagation.py`)

Dynamic Per-District Stratified Sampling. Each district is assessed for stability:

- **Stable** (`≥50%` actas reported OR `≥14` actas counted): uses its own observed vote share
- **Unstable**: falls back to the provincial trend, then departmental

Variance is pooled across strata using Bessel's correction. Output: projected national vote share with 95% CI. At 100% count, MOE collapses to 0.

**Exterior correction:** Overseas districts report `votos_emitidos = 0` in the ONPE feed. The model applies actual R1 participation rates per exterior department (loaded from `data/round1/`) to avoid a ~3–4× overcount of pending overseas votes. Fallback rate: 32%.

### Migration Model (`models/migration.py`)

Five-stage pipeline predicting how the 38 first-round parties' votes split between the two finalists:

1. **Significance filter** — candidates below 1.5% of province emitted votes are collapsed into a `tail` group
2. **Hellinger clustering** — candidate vote-share vectors are sqrt-transformed and Ward-clustered. `k = min(sig_candidates, ⌊√n_districts⌋, 6)` per scope
3. **Hierarchical fallback** — provinces with <8 districts inherit cluster definitions from department or global scope
4. **Share-space WLS** — features are R1 group votes / R1 valid; targets are R2 finalist votes / R2 valid. Solved via BVLS (`scipy.optimize.lsq_linear`, bounds [0,1]). Regression pools at department level if ≥8 districts reported, otherwise global
5. **FPC ratio estimator** — variance uses `(1 − n/N)` finite population correction with department-clustered Huber-White sandwich SE. CI uses Student's t with `n−1` df

> **Design invariant:** The model operates in share space, not raw counts. Regressing raw counts with a simplex constraint makes it impossible to predict finalists receiving more votes than their largest single feature group — a guarantee routinely violated in runoffs. Share-space normalization removes this ceiling.

---

## Setup

**Requirements:** Python 3.10+

```bash
git clone <repo-url>
cd segundaVuelta

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

**Pre-election — build the cluster map once:**

```bash
python models/migration.py --build
```

Reads `data/round1/agg_distrital.json` and writes `data/inputs/migration_cluster_map.json`. Do not run again during a live count.

---

## Running the Pipeline

```bash
source .venv/bin/activate

# 1. Scrape (5 parallel workers, live TUI)
python pipeline/run_scraper.py --mode patch

# 2. Merge worker outputs
python pipeline/merge.py

# 3. Build aggregates
python pipeline/aggregate.py

# 4. Start dashboard
python web/server.py            # http://127.0.0.1:5000
python web/server.py 8080       # custom port
```

Steps 1–3 repeat throughout the night. The dashboard reads fresh data on every model request (60-second cache).

### Scraper Modes

| Mode | Behavior |
|---|---|
| `patch` | Skip successful districts, retry only errors — **default for live counts** |
| `update` | Skip only fully-counted districts (`pct_actas = 100%`), re-fetch all partials |
| `force` | Ignore all cache, re-fetch everything |

---

## Dashboard

Two-tab interface toggled by a round switcher:

**Primera Vuelta** — frozen final results, 38 parties, 100% counted. Finalists banner, bar chart, department table.

**Segunda Vuelta** — live results with auto-detected coverage. KPI row, progress bar, bar chart, department table, and two model cards with 95% CI. Sub-tabs: Resumen · Por Departamento · Evolución.

**Refresh:** Click **Actualizar** to immediately expire the model cache and re-run both projections.

**Static snapshot:**
```bash
python web/generate_static.py       # → dashboard_static.html (no server needed)
```

---

## API Endpoints

| Route | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/round/first` | Primera vuelta aggregates |
| `GET /api/round/second` | Segunda vuelta aggregates (live) |
| `GET /api/model/propagation` | Stratified projection — national |
| `GET /api/model/propagation/dept` | Stratified projection — per department |
| `GET /api/model/migration` | Migration WLS projection — national |
| `GET /api/model/migration/dept` | Migration WLS projection — per department |
| `GET /api/history` | Prediction history time series |
| `POST /api/cache/clear` | Invalidate model cache (requires `X-Admin-Token` header) |

All endpoints return `{ "ok": true, "data": ... }` or `{ "ok": false, "error": "..." }`.

---

## Testing

Generate synthetic segunda vuelta data for end-to-end validation:

```bash
python analysis/simulate.py           # write simulated data (~62% districts)
python analysis/simulate.py --check   # show current state of data/round2/
python analysis/simulate.py --restore # restore primera vuelta data
```

---

## Analysis Scripts

| Script | Purpose |
|---|---|
| `analysis/acid_test.py` | Forces worst-case JPP splits on remaining districts to find the margin of victory threshold |
| `analysis/exterior_sensitivity.py` | 2D sensitivity table: overseas participation rate × FP share → national margin |
| `analysis/exterior_comparison.py` | District-level comparison of 2026 exterior results vs 2021 (Keiko vs Castillo) |
| `analysis/compare_actas_rounds.py` | R2 actas coverage by department vs equivalent R1 coverage level |

---

## Key Constraints

- **`data/round1/` is immutable.** The pipeline always writes to `data/round2/`. Never use `data/round1/` as an output target.
- **Party IDs `"80"` and `"81"`** (blancos/nulos) are excluded from all charts and model calculations.
- **Finalists are determined dynamically** — top-2 valid votes in `models/migration.py` and sorted party totals in dashboard JS. IDs `"8"` and `"10"` are not hardcoded anywhere.
- **Do not regenerate `data/inputs/migration_cluster_map.json` during a live count.** Stable cluster definitions are required for consistent regression pools.

---

## Documentation

- [`PIPELINE.md`](./PIPELINE.md) — full pipeline walkthrough, model architecture, API contracts, deployment guide
- [`CLAUDE.md`](./CLAUDE.md) — codebase instructions for AI-assisted development

---

## Data Source

All vote data is sourced from the official ONPE public API. This project does not store or redistribute raw ballots — it reads publicly available tally records and aggregates them for statistical analysis.
