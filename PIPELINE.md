# Pipeline Documentation

This project scrapes live ONPE election results, projects the final outcome using two independent statistical models, and serves an interactive dashboard. It is structured around two election rounds — a frozen first-round archive and a live second-round feed.

---

## Directory Layout

```
segundaVuelta/
│
├── paths.py                  ← single source of truth for all file paths
│
├── data/
│   ├── inputs/               ← static reference files (never modified at runtime)
│   │   ├── onpe_ubigeo_map.json        all 2,312 districts with ubigeo codes
│   │   ├── ubigeo_votos_habiles.json   pre-computed eligible voter counts per district
│   │   ├── migration_cluster_map.json  Hellinger clusters (built once before election night)
│   │   └── segunda_vuelta_2021.csv     2021 runoff exterior results (analysis only)
│   │
│   ├── round1/               ← FROZEN — final primera vuelta aggregates
│   │   ├── agg_ambito.json
│   │   ├── agg_departamental.json
│   │   ├── agg_provincial.json
│   │   ├── agg_distrital.json
│   │   └── idx_codigo_nombre_partido.json
│   │
│   └── round2/               ← LIVE — updated by the pipeline on election night
│       └── (same schema as round1/)
│
├── log/                      ← per-worker JSONL + log files (runtime only)
├── backups/                  ← auto-backups created at each scraper run
│
├── pipeline/                 ← data ingestion (scraping → merging → aggregating)
├── models/                   ← statistical projection (propagation + migration)
├── actas/                    ← JEE acta tracker (parallel scraper for challenged actas)
├── analysis/                 ← standalone analysis scripts
└── web/                      ← Flask server + dashboard HTML
```

---

## The Full Pipeline (4 steps)

Run these in order on election night. Each step feeds the next.

### Step 1 — Scrape

```bash
python pipeline/run_scraper.py --mode patch
```

**What it does:** Launches 5 parallel worker processes (`pipeline/scraper.py`), each responsible for a modulo-assigned slice of the 2,312 ubigeos. Workers poll the ONPE API endpoint and write results to `log/onpe_combined_results_worker_N.jsonl`.

**Run modes:**

| Mode | Behavior |
|------|----------|
| `patch` | Skips ubigeos already successfully fetched. Retries only those in the errors file. Use this for incremental runs throughout the night. |
| `update` | Re-fetches any district where `pct_actas_contabilizadas < 100%`. Use this when you want to refresh partial counts. |
| `force` | Re-fetches everything regardless of cached state. Slow — use only at the start. |

**Worker output per worker N:**
- `log/onpe_combined_results_worker_N.jsonl` — fetched district records
- `log/onpe_combined_errors_worker_N.jsonl` — failed ubigeos
- `log/scraper_worker_N.log` — human-readable progress log
- `log/worker_N_sys.log` — last-line status (read by the TUI dashboard)

The orchestrator renders a live terminal dashboard showing each worker's status. Press `Ctrl+C` to send a stop signal; workers finish their current request and exit cleanly.

**Auto-backup:** On startup, each worker copies its existing results file to `backups/` with a timestamp.

---

### Step 2 — Merge

```bash
python pipeline/merge.py
```

**What it does:** Concatenates all 5 per-worker JSONL files into two unified files at the project root:
- `onpe_combined_results.jsonl` — all scraped district records
- `onpe_combined_errors.jsonl` — all failed ubigeos

These unified files are the canonical scraped dataset.

---

### Step 3 — Aggregate

```bash
python pipeline/aggregate.py
```

**What it does:** Reads the merged JSONL and builds hierarchical aggregation tables in `data/round2/`:

| Output file | Description |
|-------------|-------------|
| `agg_distrital.json` | One row per district (2,312 rows). Input to both models. |
| `agg_provincial.json` | Aggregated by province |
| `agg_departamental.json` | Aggregated by department (25 domestic + 5 exterior = 30 rows) |
| `agg_ambito.json` | Two rows: domestic (ámbito 1) and exterior (ámbito 2) |
| `idx_codigo_nombre_partido.json` | Flat dict: party ID → party name |

Each row has the same schema:
```json
{
  "ubigeo": "010101",
  "departamento": "AMAZONAS",
  "actas_total": 84,
  "actas_contabilizadas": 34,
  "pct_actas_contabilizadas": 40.48,
  "votos_emitidos": 12000,
  "votos_validos": 11000,
  "votos_habiles": 18000,
  "votos_partidos": { "8": 4500, "10": 3800, "80": 1200, "81": 500 }
}
```

> **Important:** `processData.py` always writes to `data/round2/`. The `data/round1/` directory is frozen — never run the aggregation step against it.

---

### Step 4 — Project (done automatically by the web server)

The two projection models are not run from the command line during election night — the web server calls them on demand and caches results for 60 seconds.

See the **Models** section below for details.

---

## The Web Server

```bash
source .venv/bin/activate
python web/server.py          # port 5000
python web/server.py 8080     # custom port
```

The server serves the dashboard at `/` and exposes the following API:

| Endpoint | Source | Notes |
|----------|--------|-------|
| `GET /api/round/first` | `data/round1/` | Primera vuelta final results |
| `GET /api/round/second` | `data/round2/` | Segunda vuelta live results |
| `GET /api/model/propagation` | propagation model | 60s cache |
| `GET /api/model/propagation/dept` | propagation model (per dept) | 60s cache |
| `GET /api/model/migration` | migration model | 60s cache |
| `GET /api/model/migration/dept` | migration model (per dept) | 60s cache |
| `GET /api/model/unreported` | both models | per-district table for dashboard |
| `GET /api/history` | `prediction_history.jsonl` | Evolución tab time series |
| `POST /api/cache/clear` | — | Invalidates all cached model results |

**Cache invalidation:** Call `/api/cache/clear` with `X-Admin-Token` header after each pipeline run to force the models to recompute on the next request. The TTL (60s dev / 600s prod) is a safety net only.

**Snapshot recording:** After every successful model cache fill where all four model caches are simultaneously warm, the server appends a record to `prediction_history.jsonl` — but only if national coverage has moved by ≥ 0.05% since the last record. This powers the Evolución chart.

---

## The Two Projection Models

Both models read `data/round2/agg_distrital.json` and project the final vote totals for unreported districts. They are independent — the dashboard shows both side by side.

### Model 1 — Dynamic Stratified Propagation (`models/propagation.py`)

**Entry points:** `get_projection_data()`, `get_projection_data_by_dept()`

**How it works:**

1. For each district, evaluate *stability*: a district is stable if it has ≥50% of actas reported **or** ≥14 actas counted.
2. Stable districts contribute their observed vote shares directly.
3. Unstable districts fall back in order: try the *provincial* trend, then the *departmental* trend, to impute a vote share.
4. Multiply each district's imputed share by its estimated remaining valid votes (`E_pending_h × r_valid`) to get projected vote counts.
5. Sum observed + projected across all districts.
6. Confidence intervals use a 95% z-score (1.96) on the variance of imputed shares.

**Exterior correction:** Exterior districts (ámbito 2) have `votos_emitidos = 0` in the ONPE feed (overseas circuits are not reported live). Without a correction, `E_pending_h = votos_habiles × (1 − f_h)` would represent the full registered overseas population and be multiplied by `r_valid ≈ 0.94` — a ~3–4× overcount. The model applies the actual R1 participation rate per exterior department (loaded from `data/round1/agg_departamental.json`) as a scaling factor. Fallback rate: 32%.

**Key caveat:** Because of the structural zero for exterior `votos_emitidos`, the propagation model projects **exactly 0 additional votes for all 210 exterior districts**. The exterior contribution in this model is purely from already-counted overseas actas.

**`projected_share` is in valid-vote space** — it divides projected votes by `votos_validos` (which includes blancos). The two finalists together sum to ~75–85%, not 100%. The dashboard converts to head-to-head on the client side.

---

### Model 2 — Vote Migration WLS (`models/migration.py`)

**Entry points:** `get_migration_data()`, `get_migration_data_by_dept()`

**Setup (run once before election night):**
```bash
python migration_model.py --build
# saves data/inputs/migration_cluster_map.json
```

**How it works:**

1. **Significance filter:** For each province, identify which R1 parties passed 1.5% of emitted votes. The rest are collapsed into a `tail` group. Finalists and blank/null votes are excluded from the pool.

2. **Hellinger clustering:** The significant parties' vote-share vectors across districts are sqrt-transformed (converting Euclidean distance to Hellinger distance) and Ward-linked into k clusters, where `k = min(n_sig_candidates, ⌊√n_districts⌋, 6)`. This produces `data/inputs/migration_cluster_map.json` — a static file that must not be regenerated during the count.

3. **Hierarchical fallback:** Provinces with fewer than 8 districts inherit cluster *definitions* (not vote averages) from their department, or globally if the department also has < 8.

4. **Share-space WLS regression:** For each finalist separately, fit a bounded constrained regression (BVLS via `scipy.optimize.lsq_linear`) with:
   - **Features (X):** R1 group votes / R1 total valid — dimensionless shares
   - **Target (y):** R2 finalist votes / R2 total valid — also a share
   - **Weights:** `actas_contabilizadas` per reported district
   - **Pool:** department-level if ≥8 reported districts, otherwise global
   
   This produces one coefficient per cluster group (βs ∈ [0,1]) representing how much of each R1 bloc migrates to this finalist.

5. **FPC ratio estimator:** Project the share each finalist gets of the R2 valid votes in each unreported district, multiply by estimated R2 valid, sum. Apply a Finite Population Correction factor `(1 − n/N)` to the variance. CI uses Student's t with `n−1` df and department-clustered Huber-White sandwich standard errors.

**`projected_share` is head-to-head** (F1 / (F1 + F2) × 100). CI bounds are also in H2H space. No client-side conversion needed.

**Exterior:** The migration model *does* project exterior. It estimates R2 valid votes for overseas districts using `R1_valid × r2_over_r1_valid_ratio` derived from reported domestic districts.

**Detection logic:** `get_migration_data()` checks `data/round2/idx_codigo_nombre_partido.json`. If it contains parties other than `{8, 10, 80, 81}`, the model returns `status: "waiting"` — it knows it's still looking at primera vuelta data.

---

## Pre-Election Setup Checklist

These steps must be done **before** election night, not during:

```bash
# 1. Activate the virtual environment
source .venv/bin/activate

# 2. Build the migration cluster map from primera vuelta data
#    (reads data/round1/agg_distrital.json — must already exist)
python models/migration.py --build

# 3. Clear prediction history from any previous run
rm -f prediction_history.jsonl

# 4. (Optional) Simulate segunda vuelta data for end-to-end testing
python analysis/simulate.py              # writes synthetic data to data/round2/
python analysis/simulate.py --restore    # restores original files
```

---

## Actas JEE Tracker (`actas/`)

A parallel scraper that monitors actas sent to the JEE (Jurado Electoral Especial) for official review or challenge. Independent from the main vote-count pipeline.

```bash
python actas/run_actas.py --mode update   # fetch only districts with pct < 100%
python actas/run_actas.py --mode patch    # skip already-fetched districts
python actas/run_actas.py --mode force    # re-fetch everything
python actas/run_actas.py --mode analyze  # re-scan existing files, no network
```

Same 5-worker parallel architecture as the main scraper. Output:
- `log/actas_worker_N_results.jsonl` — all acta records
- `log/actas_worker_N_jee.jsonl` — JEE-flagged actas only
- `actas/actas_results.jsonl` — merged output after all workers finish
- `actas/actas_jee.jsonl` — merged JEE-only output

JEE detection is keyword-based — scans status fields for terms like "JEE", "observado", "impugnado", "nulo".

---

## Analysis Scripts (`analysis/`)

Standalone scripts for deeper investigation. None modify pipeline data.

| Script | Purpose |
|--------|---------|
| `acid_test.py` | Forces worst-case vote splits for JPP-heavy remaining districts; shows how extreme the assumption needs to be for either candidate to win domestically |
| `exterior_comparison.py` | Compares 2026 exterior results district-by-district against 2021 Keiko vs Castillo; shows swing, Pearson r, pending district bias |
| `exterior_sensitivity.py` | 2D sensitivity table: rows = assumed exterior participation rate, columns = assumed FP share of remaining overseas votes; cells = projected national margin |
| `compare_actas_rounds.py` | Compares current R2 actas-contabilizadas coverage by department against where R1 stood at the same national coverage level |
| `simulate.py` | Generates synthetic segunda vuelta data in `data/round2/` for testing. `--restore` reverts. |
| `watch_exterior.py` | Live watcher: prints exterior coverage as it arrives |
| `actas_by_dept_at_coverage.py` | Snapshot of actas coverage by department at a given national % |

---

## Static Dashboard Snapshot

Generate a fully self-contained HTML file with all data embedded — no server required:

```bash
source .venv/bin/activate
python web/generate_static.py                  # → dashboard_static.html
python web/generate_static.py out.html         # custom output path
```

The script loads all four model outputs, injects them into a `window.fetch` override shim inside `web/templates/dashboard.html`, and replaces the live-dot and refresh button with a static "📸 Snapshot" label.

---

## Data Flow Diagram

```
ONPE API
    │
    ▼
pipeline/run_scraper.py  ──spawns──▶  pipeline/scraper.py × 5 workers
                                              │
                                    log/onpe_combined_results_worker_N.jsonl
                                              │
                                    pipeline/merge.py
                                              │
                                    onpe_combined_results.jsonl
                                              │
                                    pipeline/aggregate.py
                                              │
                                    data/round2/agg_*.json
                                         │           │
                              ┌──────────┘           └──────────┐
                              ▼                                  ▼
                  models/propagation.py              models/migration.py
                  (stratified imputation)            (WLS vote migration)
                              │                                  │
                              └──────────────┬───────────────────┘
                                             ▼
                                      web/server.py
                                      Flask API + cache
                                             │
                                  web/templates/dashboard.html
                                  (Chart.js, two rounds, four models)
```

---

## Key Invariants

- **Never overwrite `data/round1/`** — it is the frozen, complete primera vuelta archive.
- **Never hardcode party IDs `"8"` or `"10"`** anywhere — finalists are determined dynamically.
- **Party IDs `"80"` (blancos) and `"81"` (nulos)** are always excluded from charts and model candidate columns. They are present in `votos_partidos` and counted in `votos_validos`, but never treated as candidates.
- **Never regenerate `data/inputs/migration_cluster_map.json` during a live count** — cluster definitions must be held constant throughout the night for regression pools to be stable.
- **Migration WLS must operate in share space** — raw-count regression with a simplex constraint is mathematically broken for this problem (see `models/migration.py` docstring).
- **`projected_share` from the propagation model is NOT head-to-head** — it divides by `votos_validos` which includes blancos. Always convert H2H client-side: `projected_votes / sum(all_finalist_projected_votes)`.
