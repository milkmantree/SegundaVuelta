# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Peru election results scraper and statistical projection system targeting the ONPE (Oficina Nacional de Procesos Electorales) API. It scrapes live vote tallies by district (ubigeo), aggregates them, and projects final results using a dynamic stratified sampling model.

## Pipeline Execution Order

The full pipeline runs in four steps:

```bash
# 1. Scrape: Launch 5 parallel workers (modes: patch | update | force)
python run_cluster.py --mode patch

# 2. Merge worker outputs into unified files
python merge_workers.py

# 3. Aggregate scraped data into hierarchical JSON files
python processData.py

# 4. Run the projection model and generate the dashboard
python propagation_model.py
```

## Key Files

| File | Role |
|---|---|
| `scraper.py` | Worker process — scrapes one ubigeo chunk, writes to `log/` |
| `run_cluster.py` | Orchestrator — spawns 5 workers, renders live TUI dashboard |
| `merge_workers.py` | Merges per-worker JSONL files into unified `onpe_combined_results.jsonl` |
| `processData.py` | Builds district/province/department/ámbito aggregation tables |
| `propagation_model.py` | Runs dynamic stratified projection; exposes `get_projection_data()` for API |
| `migration_model.py` | Vote migration model (Hellinger clustering + share-space WLS + FPC); exposes `get_migration_data()` and `build_cluster_map()` |
| `app.py` | Flask server — serves dashboard and all API endpoints |
| `dashboard.html` | Single-file frontend (Chart.js, inline CSS/JS) |
| `simulate_segunda_vuelta.py` | Test utility — generates synthetic segunda vuelta data for end-to-end testing |
| `inputs/onpe_ubigeo_map.json` | Master list of all districts with ubigeo codes |
| `inputs/ubigeo_votos_habiles.json` | Pre-computed eligible voter counts per ubigeo (static baseline) |
| `inputs/migration_cluster_map.json` | Precomputed Hellinger cluster definitions — generated once from first-round data |

## Directory Layout

- `log/` — per-worker JSONL output during scraping (`onpe_combined_results_worker_N.jsonl`)
- `processed_results/` — aggregated JSON outputs from `processData.py`
- `backups/` — timestamped auto-backups created on each scraper run
- `inputs/` — static reference data (ubigeo map, voter baseline)

## Scraper Run Modes

The `RUN_MODE` environment variable (or `--mode` flag) controls caching behavior:

- `patch` (default) — skips already-successful ubigeos, retries only those logged in `errors.jsonl`
- `update` — skips only districts where `pct_actas_contabilizadas >= 100%`, re-fetches all partial results
- `force` — ignores all cached data, re-fetches everything

## Propagation Model Architecture

The projection in `propagation_model.py` uses **Dynamic Per-District Stratified Sampling** (documented in `Modelo de propagacion.md`). Key behavior:

- Each district is evaluated for stability: passes if `≥50%` actas reported OR `≥14` actas counted
- Unstable districts fall back to provincial or departmental vote share trends for imputation
- Party codes `80` and `81` are excluded (blank/null votes)
- Output is `election_projection_dashboard.html` — a self-contained Plotly chart with 95% CI error bars

## Dependencies

Uses a `.venv` virtual environment. Core dependencies: `requests`, `pandas`, `numpy`, `plotly`, `flask`, `scipy`.

```bash
source .venv/bin/activate
```

## Data Contract

Scraped records (JSONL) have this shape:
```json
{
  "ubigeo": "010101",
  "ambito": "1",
  "meta": {"dep": "...", "prov": "...", "dist": "..."},
  "participantes": [{"partido": "...", "id": "12", "votos": 1234}],
  "totales": {"pct_actas_contabilizadas": 100.0, "actas_total": 5, ...}
}
```

`ambito` is `"1"` for Peru (domestic) and `"2"` for exterior.

---

## Project State & Architecture

### Two-Round Data Model

The project is now structured around **two election rounds** with separate, immutable data directories:

| Directory | Round | State | Consumer |
|---|---|---|---|
| `first_round_agg_results/` | Primera vuelta (38 parties) | **Frozen — never overwrite** | Dashboard tab 1 |
| `processed_results/` | Segunda vuelta (2 candidates) | **Live — updated by pipeline** | Dashboard tab 2 + models |

`first_round_agg_results/` contains the complete, final first-round aggregates. It is the stable source of truth and must never be regenerated or modified. The pipeline (`scraper.py` → `merge_workers.py` → `processData.py`) always writes to `processed_results/` only.

When the segunda vuelta scraping begins, `processed_results/` will contain data for exactly 2 candidates (party IDs for FUERZA POPULAR `"8"` and JUNTOS POR EL PERÚ `"10"`). The dashboard and propagation model are designed to handle any number of parties, so no code changes are needed when this transition happens.

### First-Round Final Results (Reference)

Top candidates by national valid vote share (combined ambito 1+2):

| Rank | Party ID | Party Name | Share |
|---|---|---|---|
| 1 | `8` | FUERZA POPULAR | 17.19% |
| 2 | `10` | JUNTOS POR EL PERÚ | 12.04% |
| 3 | `35` | RENOVACIÓN POPULAR | 11.91% |
| 4 | `16` | PARTIDO DEL BUEN GOBIERNO | 10.98% |
| 5 | `14` | PARTIDO CÍVICO OBRAS | 10.15% |

**IDs `"8"` and `"10"` are the segunda vuelta finalists.** These are not hardcoded anywhere in the codebase — the dashboard always computes the top 2 dynamically from whatever data is in the respective directory.

### Aggregated Data Schema

All files in `first_round_agg_results/` and `processed_results/` share the same schema:

**`agg_ambito.json`** — array of 2 objects (ambito `"1"` = Peru, `"2"` = exterior):
```json
{
  "ambito": "1",
  "actas_total": 90223,
  "actas_contabilizadas": 90223,
  "pct_actas_contabilizadas": 100.0,
  "pct_participacion": 75.653,
  "votos_emitidos": 19756668,
  "votos_validos": 16430347,
  "votos_habiles": 26114918,
  "votos_partidos": { "8": 2825224, "10": 2007120, "80": 2298103, ... }
}
```

**`agg_departamental.json`** — same fields plus `departamento` string. 25 domestic + 5 exterior = 30 rows.

**`agg_distrital.json`** — adds `ubigeo`, `provincia`, `distrito`. 2102 rows. This is the input to `propagation_model.py`.

**`idx_codigo_nombre_partido.json`** — flat dict mapping party ID string → party name string. Party IDs `"80"` (blancos) and `"81"` (nulos) are present in all aggregates but **excluded from all charts and model calculations**.

### Web Dashboard (`app.py` + `dashboard.html`)

Run with:
```bash
source .venv/bin/activate && python app.py        # default port 5000
python app.py 8080                                 # custom port
```

#### API Endpoints

| Route | Source | Cache |
|---|---|---|
| `GET /api/round/first` | `first_round_agg_results/` | none |
| `GET /api/round/second` | `processed_results/` | none |
| `GET /api/observed` | `processed_results/` | none (backward-compat alias) |
| `GET /api/model/propagation` | `propagation_model.get_projection_data()` | 60s in-memory |
| `GET /api/model/migration` | `migration_model.get_migration_data()` | 60s in-memory |

Round endpoints return `{ "ok": true, "data": { ambito, departamental, parties, last_updated, is_final } }`. Model endpoints return their own payload shapes (see contracts below). All return `{ "ok": false, "error": "..." }` on failure.

Both model results are **cached in memory for 60 seconds** (`CACHE_TTL` in `app.py`). Invalidate by restarting the server.

#### Dashboard Structure

`dashboard.html` is a single self-contained HTML file (CSS + JS inline, Chart.js via CDN). Two top-level sections toggled by the round switcher tab bar:

- **`#section-primera`** — loads `/api/round/first`, renders KPIs, finalists banner, Chart.js bar chart, department table. Shows "Resultados definitivos" badge.
- **`#section-segunda`** — loads `/api/round/second`, renders KPIs with live progress bar, chart, **propagation model card** (`#prop-body`), **migration model card** (`#migr-body`), department table.

Both sections render on page load via `Promise.all([fetchRound('primera'), fetchRound('segunda')])`. Both models fetch in the background without blocking. The refresh button (`refreshAll()`) resets both model caches.

**Key JS state object:**
```js
const S = {
  data:    { primera: null, segunda: null },  // raw API payloads
  prop:    null,                               // propagation model payload
  migr:    null,                               // migration model payload
  ambito:  { primera: 'total', segunda: 'total' },
  showAll: { primera: false, segunda: false },
  dept:    { primera: { key, asc }, segunda: { key, asc } },
};
const charts = { primera: null, segunda: null };
```

**Rendering functions:** `renderProp()` writes into `#prop-body`. `renderMigr()` writes into `#migr-body`. Both handle three states: loading spinner → content → error box. `renderMigr()` also handles `status: "waiting"` (segunda vuelta data not yet available) and `status: "insufficient_data"` (< 4 districts reported).

**Party color system:** `FIXED` dict for ~18 known parties, auto-assigned from a 10-color palette for the rest. Colors key off party ID and are consistent across rounds.

### Propagation Model API Contract

`propagation_model.get_projection_data()` returns:
```json
{
  "model": "dynamic_stratified_propagation",
  "z_score": 1.96,
  "confidence_level": "95%",
  "parties": [
    {
      "name": "FUERZA POPULAR",
      "id": "8",
      "observed_votes": 2877678,
      "projected_votes": 2877678,
      "projected_share": 17.19,
      "moe": 0.0,
      "lower_bound": 17.19,
      "upper_bound": 17.19
    }
  ]
}
```

Sorted descending by `projected_share`. Excludes party IDs `"80"` and `"81"`. `projected_share` is share of valid votes across all parties (sums to 100% excluding blancos/nulos). At 100% count, `moe` is `0.0`.

The function signature `run_dynamic_stratified_projection(..., generate_html=True)` controls whether the standalone Plotly HTML is written. The API path passes `generate_html=False`.

### Vote Migration Model Architecture

Full specification in `Modelo de migracion.md`. Implementation in `migration_model.py`. New dependency: **`scipy`** (added to `.venv`).

#### Key Files

| File | Role |
|---|---|
| `migration_model.py` | Full 5-stage pipeline: cluster map builder + live projection API |
| `inputs/migration_cluster_map.json` | Static precomputed cluster definitions (13k lines, never regenerated during a live count) |
| `simulate_segunda_vuelta.py` | Test utility — generates synthetic segunda vuelta data in `processed_results/` |

#### Two-Phase Usage

**Phase 1 — Before election night** (run once):
```bash
source .venv/bin/activate
python migration_model.py --build
```
Reads `first_round_agg_results/agg_distrital.json`, computes Hellinger-distance Ward clusters at province/department/global levels, saves to `inputs/migration_cluster_map.json`. This file is static and must not be regenerated mid-count.

**Phase 2 — During election night** (called live via API):
`migration_model.get_migration_data()` reads the cluster map + live `processed_results/agg_distrital.json`, fits share-space WLS per department, projects unreported districts, applies FPC ratio estimator.

#### Pipeline Stages

1. **Significance filter**: Candidates below 1.5% of province emitted votes are collapsed into a single `tail` feature. Finalists (`"8"`, `"10"`) and blancos/nulos are excluded from the orphan pool entirely.

2. **Hellinger clustering**: Candidate vote-share vectors across districts are sqrt-transformed (making Euclidean distance = Hellinger distance), then Ward agglomerative clustering is applied. `k = min(n_sig_candidates, ⌊√n_districts⌋, 6)` clusters per scope.

3. **Hierarchical fallback**: Province → department → global. Provinces with < 8 districts inherit cluster *definitions* (not vote averages) from higher strata. The fallback level is encoded in each province entry of `migration_cluster_map.json` as `"fallback": "department" | "global" | null`.

4. **Share-space WLS**: Features are R1 group votes / R1 total valid (dimensionless shares). Targets are R2 finalist votes / R2 total valid. Regression pools at department level if dept has ≥ 8 reported districts, otherwise global. Solved with `scipy.optimize.lsq_linear` (BVLS) with `bounds=(0, 1)`.

5. **FPC ratio estimator**: `P̂ = (obs_F1 + pred_F1_unreported) / (obs_valid + pred_valid_unreported)`. Variance uses FPC factor `(1 - n/N)` with department-clustered Huber-White sandwich SE. CI uses Student's t with `n-1` df.

#### Critical Design Decision: Share Space, Not Raw Counts

**Never regress raw vote counts against raw vote counts with a simplex constraint.** The constraint `sum(β) ≤ 1` on raw-count features makes it mathematically impossible for the model to predict a finalist getting more votes than their single largest feature group. In a runoff, finalists routinely receive 2–3× their first-round vote total, which violates this ceiling. The SLSQP solver converges to a degenerate uniform solution (~1/k for all betas) in this case.

The correct formulation: normalize both features and targets by their respective total valid votes before fitting. Predictions are converted back to vote counts by multiplying the predicted share by the projected R2 valid votes.

#### Migration Model API Contract

`migration_model.get_migration_data()` returns one of three shapes:

**Waiting (segunda vuelta data not yet in `processed_results/`):**
```json
{ "ok": false, "status": "waiting", "message": "...", "finalists": [] }
```

**Insufficient data (< 4 districts reporting):**
```json
{ "ok": true, "status": "insufficient_data", "message": "...", "finalists": [] }
```

**Active projection:**
```json
{
  "ok": true,
  "status": "ok",
  "model": "vote_migration_wls",
  "confidence_level": "95%",
  "n_districts_reported": 1301,
  "n_districts_total": 2102,
  "pct_coverage": 61.89,
  "finalists": [
    {
      "id": "8",
      "name": "FUERZA POPULAR",
      "observed_votes": 4965952,
      "projected_votes": 7367153,
      "projected_share": 56.13,
      "valid_share": 42.32,
      "moe": 4.98,
      "lower_bound": 51.15,
      "upper_bound": 61.11
    }
  ]
}
```

`projected_share` = **F1/(F1+F2) × 100** — the head-to-head percentage that sums to 100% across both finalists. `valid_share` = share of all valid votes including blancos (does NOT sum to 100% between finalists — displayed as secondary context in the UI). Sorted descending by `projected_share`.

**Detection logic**: `get_migration_data()` checks `processed_results/idx_codigo_nombre_partido.json`. If it contains parties other than `{"8","10","80","81"}`, it returns `status: "waiting"`. This is the live gate — no other code change is needed when segunda vuelta scraping begins.

#### Cluster Map JSON Structure

`inputs/migration_cluster_map.json` has four top-level keys:

```json
{
  "_meta": {
    "finalists": ["8", "10"],
    "finalist_names": { "8": "FUERZA POPULAR", "10": "JUNTOS POR EL PERÚ" },
    "significance_threshold": 0.015,
    "min_districts_for_local": 8,
    "generated_at": "2026-06-04T..."
  },
  "global": { "n_districts": 2102, "n_clusters": 6, "significant_orphans": [...], "tail": [...], "clusters": [...], "candidate_to_cluster": {...} },
  "departments": {
    "AMAZONAS": { "n_districts": 84, "n_clusters": 6, ... },
    ...
  },
  "provinces": {
    "BONGARÁ": { "n_districts": 12, "department": "AMAZONAS", "fallback": null, ... },
    "BAGUA":   { "n_districts": 6,  "department": "AMAZONAS", "fallback": "department", ... },
    ...
  }
}
```

Each cluster entry: `{ "id": 0, "members": ["14", "35"] }`. `"fallback": null` means the province has its own local cluster map. `"fallback": "department"` or `"global"` means the province inherits from that level at runtime.

#### Test Utility: `simulate_segunda_vuelta.py`

```bash
source .venv/bin/activate

python simulate_segunda_vuelta.py          # write simulated segunda vuelta data
python simulate_segunda_vuelta.py --check  # show current state of processed_results
python simulate_segunda_vuelta.py --restore  # restore original primera vuelta data
```

Writes synthetic segunda vuelta records (only parties 8, 10, 80, 81) to all five `processed_results/` files. Simulates ~62% of districts reporting, with party-specific migration rates encoding political affinity (e.g., Renovación Popular → 62% to F1; Perú Libre → 68% to F2) and geographic lean by department. Backs up originals to `processed_results_backup_r1/` on first run. Simulated national outcome: ~56% F1 vs ~44% F2 of finalist votes.

### Strict Constraints

- **Never run `processData.py` with `first_round_agg_results/` as the output target.** That directory is the frozen first-round archive. `processData.py` always writes to `processed_results/`.
- **Do not hardcode party IDs `"8"` or `"10"`** anywhere in the codebase. Finalists are determined dynamically — by `_determine_finalists()` in `migration_model.py` (top 2 by first-round valid votes) and by sorted party totals in the dashboard JS.
- **Party IDs `"80"` (blancos) and `"81"` (nulos)** must always be excluded from charts, vote share calculations, and model candidate columns. They are present in `votos_partidos` dicts and ARE included in `votos_validos` (blancos count as valid in Peru's system), but are never treated as candidates.
- **`votos_habiles`** is taken from `inputs/ubigeo_votos_habiles.json` or estimated via `votos_emitidos / (pct_participacion / 100)`. Both models depend on it for pending-vote projection. If ONPE's participation field is wrong on election night, projections will be wrong.
- **The scraper's `RUN_MODE`** must be set correctly before election night: `patch` for incremental, `update` for refreshing partials, `force` only for full re-scrape.
- **Never regenerate `inputs/migration_cluster_map.json` during a live count.** It must be precomputed from first-round data and held constant so regression pools are stable throughout the night.
- **Migration WLS must operate in share space.** Raw-count regression with a simplex constraint is broken for this problem (see architecture note above). Do not revert to raw counts.

### Current State (as of end of Objective 2)

**Done:**
- Full scraping pipeline operational (5 parallel workers, stop-signal interrupt, atomic JSONL writes)
- `processData.py` produces district/province/department/ámbito aggregates with `votos_habiles` integration
- `propagation_model.py`: dynamic stratified projection with per-district fallback to provincial/departmental trends and Bessel's-corrected variance pooling; exports Plotly HTML and JSON API
- `first_round_agg_results/` populated with final first-round data (100% counted, 38 parties, 2102 districts)
- `migration_model.py`: full 5-stage pipeline (Hellinger clustering → hierarchical fallback → share-space WLS → FPC ratio estimator with clustered sandwich SE); tested against simulated data
- `inputs/migration_cluster_map.json`: precomputed cluster definitions (273 provinces, 30 departments, global)
- `simulate_segunda_vuelta.py`: test utility for end-to-end validation
- `app.py`: both model endpoints live (`/api/model/propagation`, `/api/model/migration`), both with 60s cache
- `dashboard.html`: both model cards active ("Activo" badge), `renderMigr()` handles waiting/insufficient/active states, `projected_share` displays head-to-head (F1 vs F2, sums to 100%), `valid_share` shown as secondary context

**Current `processed_results/` state:** Simulated segunda vuelta data is loaded (from `simulate_segunda_vuelta.py`). Run `python simulate_segunda_vuelta.py --restore` before the real election to put first-round data back, then let the scraper pipeline overwrite with real segunda vuelta data.

**Next objective:**
- Validate model accuracy and confidence interval behavior as coverage increases (run sensitivity analysis across simulated coverage levels: 10%, 25%, 50%, 75%, 100%)
- Tune model for election night: verify the 60s cache TTL is appropriate, confirm `--mode patch` scraper behavior with segunda vuelta API endpoints
- Monitor for data quality issues on election night: ONPE sometimes returns malformed JSON or stale actas counts mid-scrape
