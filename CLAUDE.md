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

Uses a `.venv` virtual environment. Core dependencies: `requests`, `pandas`, `numpy`, `plotly`.

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
