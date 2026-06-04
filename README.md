# Segunda Vuelta — Peru 2026 Live Election Results System

A production-grade election intelligence platform targeting the ONPE (Oficina Nacional de Procesos Electorales) API. Scrapes live vote tallies across all 2,102 Peruvian districts, aggregates results in real time, and projects final outcomes using two independent statistical models — all surfaced through a self-contained web dashboard.

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

## Architecture

```
ONPE API
    │
    ▼
run_cluster.py          ← 5 parallel workers, live TUI dashboard
    │ writes
    ▼
log/onpe_combined_results_worker_N.jsonl
    │
merge_workers.py        ← merges worker outputs
    │
onpe_combined_results.jsonl
    │
processData.py          ← builds hierarchical aggregates
    │
processed_results/      ← live segunda vuelta data (read by dashboard + models)
    │
    ├── propagation_model.py   ← stratified projection, 95% CI
    ├── migration_model.py     ← WLS migration model, 95% CI
    └── app.py                 ← Flask API + dashboard.html
```

`first_round_agg_results/` holds the complete frozen primera vuelta archive (90,223 domestic actas, 16.4M valid votes across 38 parties) and is never modified by the pipeline.

---

## Statistical Models

### Propagation Model (`propagation_model.py`)

Dynamic Per-District Stratified Sampling. Each of the 2,102 districts is assessed for stability:

- **Stable** (`≥50%` actas reported OR `≥14` actas counted): uses its own observed vote share
- **Unstable**: falls back to the provincial trend, then departmental, then national

Variance is pooled across strata using Bessel's correction. Output: projected national vote share with 95% CI error bars. At 100% count, MOE collapses to 0.

### Migration Model (`migration_model.py`)

Five-stage pipeline predicting how the 38 first-round parties' votes split between the two second-round finalists:

1. **Significance filter** — candidates below 1.5% of province emitted votes are collapsed into a `tail` group
2. **Hellinger clustering** — candidate vote-share vectors are sqrt-transformed (making Euclidean = Hellinger distance) and Ward-clustered. `k = min(sig_candidates, ⌊√n_districts⌋, 6)` per scope
3. **Hierarchical fallback** — provinces with <8 districts inherit cluster definitions from department or global scope
4. **Share-space WLS** — features are R1 group votes / R1 valid (dimensionless shares); targets are R2 finalist votes / R2 valid. Solved via BVLS (`scipy.optimize.lsq_linear`, bounds [0,1]). Regression pools at department level if ≥8 districts reported, otherwise global
5. **FPC ratio estimator** — `P̂ = (obs + pred_unreported) / (obs_valid + pred_valid_unreported)`. Variance uses `(1 − n/N)` finite population correction with department-clustered Huber-White sandwich SE. CI uses Student's t with `n−1` df

The cluster map (273 provinces, 30 departments, 6 global clusters) is precomputed once from first-round data and held constant throughout the live count for stable regression pools.

> **Design invariant:** The model operates in share space, not raw counts. Regressing raw counts with a simplex constraint `Σβ ≤ 1` makes it mathematically impossible to predict finalists receiving more votes than their largest single feature group — a guarantee that is routinely violated in runoffs. Share-space normalization removes this ceiling.

---

## Setup

**Requirements:** Python 3.10+, virtual environment

```bash
git clone <repo-url>
cd segundaVuelta

python -m venv .venv
source .venv/bin/activate

pip install requests pandas numpy plotly flask scipy
```

**Pre-election — build the cluster map once:**

```bash
python migration_model.py --build
```

Reads `first_round_agg_results/` and writes `inputs/migration_cluster_map.json`. Do not run again during a live count.

---

## Running the Pipeline

```bash
source .venv/bin/activate

# 1. Scrape (5 parallel workers, live TUI)
python run_cluster.py --mode patch

# 2. Merge worker outputs
python merge_workers.py

# 3. Build aggregates
python processData.py

# 4. Start dashboard
python app.py                # http://127.0.0.1:5000
python app.py 8080           # custom port
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

**Segunda Vuelta** — live results with auto-detected coverage. KPI row, progress bar, bar chart, department table, and two model cards:

| Model Card | Source | Updates |
|---|---|---|
| Propagation | `/api/model/propagation` | 60s cache |
| Migration | `/api/model/migration` | 60s cache |

Both model cards handle three states automatically: loading spinner → active projection with CI → error box. The migration card also handles `waiting` (primera vuelta data still in `processed_results/`) and `insufficient_data` (<4 districts reporting).

**Refresh:** Click **Actualizar** to immediately expire the model cache and re-run both projections.

---

## API Endpoints

| Route | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/round/first` | Primera vuelta aggregates |
| `GET /api/round/second` | Segunda vuelta aggregates (live) |
| `GET /api/observed` | Alias for `/api/round/second` |
| `GET /api/model/propagation` | Stratified projection payload |
| `GET /api/model/migration` | Migration WLS projection payload |

All endpoints return `{ "ok": true, "data": ... }` or `{ "ok": false, "error": "..." }`.

---

## Project Layout

```
.
├── scraper.py                      # Worker — scrapes one ubigeo chunk
├── run_cluster.py                  # Orchestrator — spawns 5 workers, TUI
├── merge_workers.py                # Merges per-worker JSONL into unified file
├── processData.py                  # Builds aggregation hierarchy
├── propagation_model.py            # Stratified projection model
├── migration_model.py              # WLS migration model
├── app.py                          # Flask server + API
├── dashboard.html                  # Single-file frontend (Chart.js, inline CSS/JS)
├── simulate_segunda_vuelta.py      # Test utility — synthetic segunda vuelta data
│
├── inputs/
│   ├── onpe_ubigeo_map.json        # All 2,102 districts with ubigeo codes
│   ├── ubigeo_votos_habiles.json   # Eligible voter counts per district (static)
│   └── migration_cluster_map.json  # Precomputed Hellinger clusters (built once)
│
├── first_round_agg_results/        # Frozen primera vuelta archive — never modify
│   ├── agg_ambito.json
│   ├── agg_departamental.json
│   ├── agg_distrital.json
│   ├── agg_provincial.json
│   └── idx_codigo_nombre_partido.json
│
├── processed_results/              # Live segunda vuelta data — updated by pipeline
│   └── (same schema as above)
│
├── log/                            # Per-worker JSONL and system logs
└── backups/                        # Timestamped auto-backups per scraper run
```

---

## Testing

Generate synthetic segunda vuelta data for end-to-end validation:

```bash
python simulate_segunda_vuelta.py          # write simulated data (~62% districts)
python simulate_segunda_vuelta.py --check  # show current state of processed_results/
python simulate_segunda_vuelta.py --restore  # restore primera vuelta data
```

The simulator encodes politically realistic migration rates by ideology and department (e.g., Renovación Popular → 62% to FUERZA POPULAR; Perú Libre → 68% to JUNTOS POR EL PERÚ) and produces a simulated national outcome near 56/44.

---

## Key Constraints

- **`first_round_agg_results/` is immutable.** The pipeline always writes to `processed_results/`. Never pass `first_round_agg_results/` as an output target to `processData.py`.
- **Party IDs `"80"` and `"81"`** (blancos/nulos) are excluded from all charts and model calculations. They are present in `votos_partidos` dicts and included in `votos_validos` but are never treated as candidates.
- **Finalists are determined dynamically** — by top-2 valid votes in `migration_model.py` and by sorted party totals in the dashboard JS. Party IDs `"8"` and `"10"` are not hardcoded anywhere.
- **Do not regenerate `inputs/migration_cluster_map.json` during a live count.** Stable cluster definitions are required for consistent regression pools throughout the night.

---

## Election Night Runbook

See [`ELECTION_NIGHT_GUIDE.md`](./ELECTION_NIGHT_GUIDE.md) for the complete step-by-step operations guide covering pre-election setup, live pipeline operation, dashboard interpretation, and post-count archival.

---

## Data Source

All vote data is sourced from the official ONPE public API. This project does not store or redistribute raw ballots — it reads publicly available tally records and aggregates them for statistical analysis.
