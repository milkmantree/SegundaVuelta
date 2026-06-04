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
| `propagation_model.py` | Runs dynamic stratified projection, exports interactive HTML dashboard |
| `inputs/onpe_ubigeo_map.json` | Master list of all districts with ubigeo codes |
| `inputs/ubigeo_votos_habiles.json` | Pre-computed eligible voter counts per ubigeo (static baseline) |

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

Uses a `.venv` virtual environment. Core dependencies: `requests`, `pandas`, `numpy`, `plotly`, `flask`.

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

| Route | Source | `is_final` |
|---|---|---|
| `GET /api/round/first` | `first_round_agg_results/` | `true` |
| `GET /api/round/second` | `processed_results/` | `false` |
| `GET /api/observed` | `processed_results/` | `false` (alias for backward compat) |
| `GET /api/model/propagation` | Runs `propagation_model.get_projection_data()` on `processed_results/` | — |

All data endpoints return `{ "ok": true, "data": { ambito, departamental, parties, last_updated, is_final } }` or `{ "ok": false, "error": "..." }`.

The propagation model result is **cached in memory for 60 seconds** (`CACHE_TTL` in `app.py`). Invalidate by restarting the server or reducing the TTL.

#### Dashboard Structure

`dashboard.html` is a single self-contained HTML file (CSS + JS inline, Chart.js via CDN). It has two top-level sections toggled by the round switcher tab bar:

- **`#section-primera`** — loads `/api/round/first`, renders KPIs, finalists banner, Chart.js horizontal bar chart, department table. No model section. Shows "Resultados definitivos" badge.
- **`#section-segunda`** — loads `/api/round/second`, renders KPIs with live progress bar, chart, propagation model card, vote migration model placeholder, department table.

Both sections are rendered independently on page load via `Promise.all([fetchRound('primera'), fetchRound('segunda')])`. The propagation model fetches in the background without blocking.

**Key JS state object:**
```js
const S = {
  data:    { primera: null, segunda: null },  // raw API payloads
  prop:    null,                               // propagation model payload
  ambito:  { primera: 'total', segunda: 'total' },  // active tab per round
  showAll: { primera: false,   segunda: false },     // expand all parties
  dept:    { primera: { key, asc }, segunda: { key, asc } }, // sort state
};
const charts = { primera: null, segunda: null };  // Chart.js instances
```

**Rendering functions are round-aware** — they accept a `round` string (`'primera'` or `'segunda'`) and write into ID-prefixed containers (`p1-kpi`, `p2-kpi`, `p1-chart`, `p2-chart`, etc.).

**Party color system:** `FIXED` dict for ~18 known parties, auto-assigned from a 10-color palette for the rest. Colors are consistent across both rounds because they key off party ID.

#### Adding the Second Model (Vote Migration)

When the migration model is ready:
1. Add `GET /api/model/migration` to `app.py` — same cache pattern as `/api/model/propagation`.
2. In `dashboard.html`, replace the `.model-card.dim` placeholder's body with a `fetchMigration()` call and a `renderMigration()` function that writes into a dedicated element.
3. Change the placeholder card's `badge-off` to `badge-on` and remove the `dim` class.

No structural changes to the layout are needed.

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

Sorted descending by `projected_share`. Excludes party IDs `"80"` and `"81"`. At 100% count, `moe` will be `0.0` and projected = observed.

The function signature `run_dynamic_stratified_projection(..., generate_html=True)` controls whether the standalone Plotly `election_projection_dashboard.html` is also written. The API path passes `generate_html=False`.

### Strict Constraints

- **Never run `processData.py` with `first_round_agg_results/` as the output target.** That directory is the frozen first-round archive. `processData.py` always writes to `processed_results/`.
- **Do not hardcode party IDs `"8"` or `"10"`** as the segunda vuelta finalists anywhere in the codebase. The dashboard computes the top 2 dynamically. This keeps it correct if data changes.
- **Party IDs `"80"` (blancos) and `"81"` (nulos)** must always be excluded from charts, vote share calculations, and model inputs. They appear in `votos_partidos` dicts but are not candidates.
- **`votos_habiles`** (eligible voters) is either taken directly from `inputs/ubigeo_votos_habiles.json` (preferred) or estimated via `votos_emitidos / (pct_participacion / 100)`. The dashboard's participation % and the model's pending vote estimates both depend on this being accurate. If ONPE's `participacionCiudadana` field is wrong on election night, `votos_habiles` will be wrong — see the dev log for this known risk.
- **The scraper's `RUN_MODE`** must be set correctly before election night: use `patch` for incremental patching, `update` for refreshing partial districts, `force` only if a full re-scrape is needed.

### Current State (as of end of Objective 1)

**Done:**
- Full scraping pipeline operational (5 parallel workers, stop-signal interrupt, atomic JSONL writes)
- `processData.py` produces district/province/department/ámbito aggregates with `votos_habiles` integration
- `propagation_model.py` implements dynamic stratified projection with per-district fallback to provincial/departmental trends and Bessel's-corrected variance pooling; exports both a Plotly HTML and a JSON API via `get_projection_data()`
- `first_round_agg_results/` populated with final first-round data (100% counted, 38 parties, 2102 districts)
- Interactive dashboard (`app.py` + `dashboard.html`) with two-round tab navigation, finalists banner, Chart.js observed results, live propagation model card, and department table

**Next objective:**
- Define and implement the **vote migration model** (`Modelo de Migración de Votos`) for segunda vuelta projection. This model estimates how votes from the 36 eliminated first-round candidates redistribute between FUERZA POPULAR and JUNTOS POR EL PERÚ in the runoff. The methodology is still in definition phase (see dev log). The dashboard placeholder card is already wired up and waiting for `/api/model/migration`.
