# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Peru 2026 segunda vuelta election intelligence platform. Scrapes live vote tallies from the ONPE (Oficina Nacional de Procesos Electorales) API by district (ubigeo), aggregates them into hierarchical JSON files, and projects final results using two independent statistical models (propagation + vote migration). Results are served via a Flask dashboard with real-time 95% CI charts.

**Finalists:** FUERZA POPULAR (party ID `"8"`) vs JUNTOS POR EL PERÚ (party ID `"10"`).

---

## Directory Layout

```
segundaVuelta/
├── paths.py                        # Single source of truth for ALL file paths
├── pipeline/
│   ├── run_scraper.py              # Orchestrator — spawns 5 workers, live TUI
│   ├── scraper.py                  # Worker — scrapes one ubigeo chunk
│   ├── merge.py                    # Merges per-worker JSONL into unified file
│   └── aggregate.py                # Builds district/province/dept/ambito aggregates
├── models/
│   ├── propagation.py              # Dynamic stratified projection, 95% CI
│   └── migration.py                # Hellinger-clustered WLS regression, 95% CI
├── web/
│   ├── server.py                   # Flask API server
│   ├── generate_static.py          # Generates self-contained dashboard_static.html
│   └── templates/
│       └── dashboard.html          # Single-file frontend (Chart.js, inline CSS/JS)
├── actas/
│   ├── run_actas.py                # Orchestrator for JEE challenged-ballot tracker
│   └── worker.py                   # Worker — fetches acta status per ubigeo
├── analysis/
│   ├── acid_test.py                # Worst-case JPP-sweep stress test
│   ├── exterior_sensitivity.py     # 2D sensitivity: participation × FP share → margin
│   ├── exterior_comparison.py      # 2026 vs 2021 exterior result comparison
│   ├── simulate.py                 # Generates synthetic segunda vuelta data
│   ├── compare_actas_rounds.py     # R1 vs R2 actas coverage by department
│   └── watch_areas.py              # 30s polling monitor for key provinces/countries
└── data/
    ├── inputs/                     # Static reference — never modified at runtime
    │   ├── onpe_ubigeo_map.json
    │   ├── ubigeo_votos_habiles.json
    │   ├── migration_cluster_map.json
    │   └── segunda_vuelta_2021.csv
    ├── round1/                     # FROZEN — complete primera vuelta archive
    └── round2/                     # LIVE — written by pipeline on election night
```

Runtime directories (`log/`, `backups/`) and pipeline outputs (`onpe_combined_results.jsonl`, `prediction_history.jsonl`) are gitignored.

---

## Path Management — `paths.py`

**All file paths in every module must come from `paths.py`.** Never hardcode paths. Every subdirectory module inserts the project root into `sys.path` before importing:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import ROUND1, ROUND2, INPUTS, ...
```

`paths.py` exports:
```python
ROOT    = Path(__file__).parent
DATA    = ROOT / "data"
INPUTS  = DATA / "inputs"
ROUND1  = DATA / "round1"       # frozen first-round archive
ROUND2  = DATA / "round2"       # live second-round results
LOG_DIR = ROOT / "log"
BACKUP_DIR = ROOT / "backups"
UBIGEO_MAP          = INPUTS / "onpe_ubigeo_map.json"
VOTER_ROLLS         = INPUTS / "ubigeo_votos_habiles.json"
MIGRATION_CLUSTERS  = INPUTS / "migration_cluster_map.json"
EXTERIOR_2021_CSV   = INPUTS / "segunda_vuelta_2021.csv"
COMBINED_RESULTS    = ROOT / "onpe_combined_results.jsonl"
COMBINED_ERRORS     = ROOT / "onpe_combined_errors.jsonl"
PREDICTION_HISTORY  = ROOT / "prediction_history.jsonl"
SCRAPER_STOP_SIGNAL = LOG_DIR / ".stop_signal"
ACTAS_STOP_SIGNAL   = LOG_DIR / ".actas_stop_signal"
```

---

## Pipeline Execution Order

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

### Scraper Modes

| Mode | Behavior |
|---|---|
| `patch` | Skip successful districts, retry only errors — **default** |
| `update` | Skip only fully-counted districts, re-fetch all partials |
| `force` | Ignore all cache, re-fetch everything |

---

## Data Contract

### Scraped JSONL records

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

### Aggregated JSON schema (shared by `data/round1/` and `data/round2/`)

**`agg_ambito.json`** — 2 objects (one per ambito):
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

**`agg_departamental.json`** — same fields + `departamento`. 25 domestic + 5 exterior = 30 rows.

**`agg_distrital.json`** — adds `ubigeo`, `provincia`, `distrito`. 2102 rows (1892 domestic + 210 exterior). Primary input to both models.

**`idx_codigo_nombre_partido.json`** — flat dict: party ID string → party name string.

---

## Two-Round Data Model

| Directory | Round | State | Consumer |
|---|---|---|---|
| `data/round1/` | Primera vuelta (38 parties) | **Frozen — never overwrite** | Dashboard tab 1 |
| `data/round2/` | Segunda vuelta (2 candidates) | **Live — updated by pipeline** | Dashboard tab 2 + models |

### First-Round Final Results (Reference)

Top candidates by national valid vote share (combined ambito 1+2):

| Rank | Party ID | Party Name | Share |
|---|---|---|---|
| 1 | `8` | FUERZA POPULAR | 17.19% |
| 2 | `10` | JUNTOS POR EL PERÚ | 12.04% |
| 3 | `35` | RENOVACIÓN POPULAR | 11.91% |
| 4 | `16` | PARTIDO DEL BUEN GOBIERNO | 10.98% |
| 5 | `14` | PARTIDO CÍVICO OBRAS | 10.15% |

---

## Web Dashboard (`web/server.py` + `web/templates/dashboard.html`)

```bash
source .venv/bin/activate && python web/server.py        # port 5000
python web/server.py 8080                                 # custom port
```

Flask resolves templates from `web/templates/` because `app = Flask(__name__)` and `__name__` resolves to the `web` package. **Use `render_template("dashboard.html")`, never `send_file`.** `send_file` bypasses Jinja2 and breaks `ADMIN_TOKEN` injection.

### API Endpoints

| Route | Source | Cache |
|---|---|---|
| `GET /` | `web/templates/dashboard.html` | — |
| `GET /api/round/first` | `data/round1/` | none |
| `GET /api/round/second` | `data/round2/` | none |
| `GET /api/model/propagation` | `models/propagation.get_projection_data()` | 60s |
| `GET /api/model/propagation/dept` | `models/propagation.get_projection_data_by_dept()` | 60s |
| `GET /api/model/migration` | `models/migration.get_migration_data()` | 60s |
| `GET /api/model/migration/dept` | `models/migration.get_migration_data_by_dept()` | 60s |
| `GET /api/history` | `prediction_history.jsonl` | none |
| `POST /api/cache/clear` | wipes `_cache` dict | requires `X-Admin-Token` header |

Cache keys: `"prop"`, `"prop_dept"`, `"migr"`, `"migr_dept"`. All return `{ "ok": true, "data": ... }` or `{ "ok": false, "error": "..." }`.

### Dashboard Structure

Two top-level sections toggled by the round switcher:

- **`#section-primera`** — loads `/api/round/first`, renders KPIs, finalists banner, Chart.js bar chart, department table.
- **`#section-segunda`** — sub-tab bar `[Resumen | Por Departamento | Evolución]`:
  - **`#s2-tab-resumen`** — KPIs, progress bar, chart, propagation card (`#prop-body`), migration card (`#migr-body`), raw dept table.
  - **`#s2-tab-dept`** — 8-column `#p2-dept-models` table (both models per dept). Exterior in collapsible `🌐 EXTERIOR` toggle. Department name click → `#dept-modal`.
  - **`#s2-tab-evolucion`** — Chart.js line chart with CI bands from `prediction_history.jsonl`.

**Key JS state object:**
```js
const S = {
  data:        { primera: null, segunda: null },
  prop:        null, migr: null, propDept: null, migrDept: null,
  history:     null,
  activeRound: 'primera',
  activeS2Tab: 'resumen',
  modalDept:   null,
  ambito:      { primera: 'total', segunda: 'total' },
  showAll:     { primera: false, segunda: false },
  dept: {
    primera:    { key: 'first_share', asc: false },
    segunda:    { key: 'first_share', asc: false },
    deptModels: { key: 'dept', asc: true },
  },
};
const charts = { primera: null, segunda: null, evo: null };
```

**Rendering functions:**
- `renderProp()` → `#prop-body`. `renderMigr()` → `#migr-body`.
- `renderDeptModels()` → `#p2-dept-models`. Separates Peru vs exterior via `S.data.segunda.departamental[i].ambito`.
- `openDeptModal(deptName)` → `#dept-modal`. Shows tier resolution bar (propagation) and transfer coefficient table (migration) from the `details` block.
- `renderEvolucion()` — three datasets per candidate × model: `_ub_` (`fill: '+1'`), `_lb_` (`fill: false`), then main line. **This ordering is load-bearing — do not reorder.** Chart.js `fill: '+1'` resolves relative to dataset index.

**Evolución X-axis (Lima time):** `new Date((ts - 5*3600) * 1000)` with `getUTC*()` accessors to avoid browser timezone interference.

**Propagation h2h conversion in Evolución:**
```js
const totalProj = propSrc.reduce((s, p) => s + (p.projected_votes || 0), 0);
const h2h   = totalProj > 0 ? (p.projected_votes / totalProj) * 100 : p.projected_share;
const scale = p.projected_share > 0 ? h2h / p.projected_share : 1;
// lb_h2h = p.lower_bound * scale, ub_h2h = p.upper_bound * scale
```

### Static Dashboard Generator

```bash
source .venv/bin/activate
python web/generate_static.py           # → dashboard_static.html
python web/generate_static.py out.html  # custom path
```

Injects a `window.fetch` shim over all API responses. Replaces live-dot + refresh button with a snapshot label.

---

## Propagation Model (`models/propagation.py`)

Dynamic Per-District Stratified Sampling:
- **Stable** district: `≥50%` actas reported OR `≥14` actas counted → uses own observed share.
- **Unstable** district: falls back to provincial trend, then departmental.

Variance pooled across strata with Bessel's correction. MOE collapses to 0 at 100% count.

**Exterior correction:** Exterior districts report `votos_emitidos = 0` in the ONPE feed. The model applies actual R1 participation rates per exterior department (loaded from `data/round1/`) to avoid a ~3–4× overcount. Fallback rate: 32%. Without this correction, the model would treat the full `votos_habiles` as the pending pool.

### National API contract — `get_projection_data()`

```json
{
  "model": "dynamic_stratified_propagation",
  "z_score": 1.96,
  "confidence_level": "95%",
  "parties": [
    {
      "name": "FUERZA POPULAR", "id": "8",
      "observed_votes": 2877678,
      "projected_votes": 2877678,
      "projected_share": 17.19,
      "moe": 0.0, "lower_bound": 17.19, "upper_bound": 17.19
    }
  ]
}
```

**`projected_share` is in valid-vote space** (denominator = `votos_validos` including blancos). In segunda vuelta both finalists together sum to ~75–85%, not 100%. Always convert to h2h client-side: `projected_votes / sum(all_candidate_projected_votes)`.

### Department API contract — `get_projection_data_by_dept()`

Runs the model independently on each department's subset of `agg_distrital.json` (30 runs). `projected_share` here is **head-to-head** (not valid-space). `valid_share` is the raw model output. `moe` and CI bounds are in h2h space, scaled via `h2h_scale = total_projected_valid / total_candidate_projected`.

---

## Migration Model (`models/migration.py`)

Hellinger-clustered share-space WLS regression predicting how R1 party votes migrate to R2 finalists.

### Pre-election setup (run once, before live count):

```bash
python models/migration.py --build
```

Reads `data/round1/agg_distrital.json`, builds Hellinger-distance Ward clusters at province/department/global levels, saves to `data/inputs/migration_cluster_map.json`. **Never regenerate during a live count.**

### Pipeline stages

1. **Significance filter** — candidates below 1.5% of province emitted votes → `tail` group. Finalists and blancos/nulos excluded from orphan pool.
2. **Hellinger clustering** — sqrt-transform vote-share vectors, Ward agglomeration. `k = min(n_sig_candidates, ⌊√n_districts⌋, 6)`.
3. **Hierarchical fallback** — provinces with <8 districts inherit cluster *definitions* (not vote averages) from department or global scope. Encoded as `"fallback": "department" | "global" | null` in `migration_cluster_map.json`.
4. **Share-space WLS** — features: R1 group votes / R1 total valid. targets: R2 finalist votes / R2 total valid. Pooled at department if ≥8 reported districts, otherwise global. Solved with `scipy.optimize.lsq_linear` (BVLS, bounds [0, 1]).
5. **FPC ratio estimator** — `P̂ = (obs_F1 + pred_F1_unreported) / (obs_valid + pred_valid_unreported)`. Variance: FPC factor `(1 - n/N)` + department-clustered Huber-White sandwich SE. CI: Student's t, `n-1` df.

### Critical: share space, not raw counts

**Never regress raw vote counts with a simplex constraint.** `sum(β) ≤ 1` on raw counts makes it mathematically impossible to predict a finalist receiving more votes than their single largest feature group. In a runoff, finalists typically receive 2–3× their R1 total — a guarantee that violates this ceiling. The SLSQP solver degenerates to ~1/k uniform betas. Normalize both features and targets by their respective total valid votes before fitting.

### National API contract — `get_migration_data()`

Three possible response shapes:

**Waiting** (R2 data not yet present — idx_codigo_nombre_partido.json contains >4 parties):
```json
{ "ok": false, "status": "waiting", "message": "...", "finalists": [] }
```

**Insufficient data** (<4 districts reporting):
```json
{ "ok": true, "status": "insufficient_data", "message": "...", "finalists": [] }
```

**Active projection:**
```json
{
  "ok": true, "status": "ok",
  "model": "vote_migration_wls",
  "confidence_level": "95%",
  "n_districts_reported": 1301, "n_districts_total": 2102, "pct_coverage": 61.89,
  "finalists": [
    {
      "id": "8", "name": "FUERZA POPULAR",
      "observed_votes": 4965952, "projected_votes": 7367153,
      "projected_share": 56.13, "valid_share": 42.32,
      "moe": 4.98, "lower_bound": 51.15, "upper_bound": 61.11
    }
  ]
}
```

`projected_share` = **head-to-head** F1/(F1+F2) × 100 (sums to 100% across both finalists). `valid_share` = share of all valid including blancos.

### Department API contract — `get_migration_data_by_dept()`

Same envelope plus `departments` dict. Per-dept CI uses dept-level FPC and dept residuals (ddof=1), scaled from valid-space to finalist-space via `scale = dept_total_valid / dept_total_finalist`.

`details` block per finalist: `pool_level` ("department" or "global"), `features[]` in WLS design-matrix order (index 0 = finalist's own R1 votes, 1..k = cluster groups, last = tail), `beta` = BVLS coefficient.

### Cluster map structure (`data/inputs/migration_cluster_map.json`)

Four top-level keys: `_meta`, `global`, `departments`, `provinces`. Each province entry: `"fallback": null | "department" | "global"`. Each cluster entry: `{ "id": 0, "members": ["14", "35"] }`.

---

## Exterior Vote Architecture

**Propagation model — structural zero:**
Exterior districts have `votos_emitidos = 0` in the R2 ONPE feed. The model projects exactly 0 additional votes for all 210 exterior districts. This is a known structural limitation, not a bug.

**Migration model — exterior IS projected:**
Uses R1 valid votes × `r2_over_r1_valid` ratio estimated from reported domestic districts. R1 exterior participation was ~25.4% of habilitados — use this as the scaling basis, not `votos_habiles × national_participation_rate` (the latter massively overestimates overseas contribution).

| Model | Exterior | Mechanism |
|---|---|---|
| Propagation | 0 (structural) | `r_valid = 0` — `votos_emitidos = 0` |
| Migration | Projected via WLS | R1 valid × `r2_over_r1_valid` ratio |

This asymmetry makes the two models non-comparable at low exterior coverage. Propagation systematically understates FP's projected total when exterior strongly favors FP.

**Exterior acta arrival patterns (from R1 `all_actas_merged.jsonl` and R2 prediction history):**
- First exterior actas arrive election night ~H+0 (19:00 Lima)
- EUROPA, ASIA, ÁFRICA arrive simultaneously in a single batch — this is **not** correlated with distance. It's a centralized upload from Lima; consulate size (# actas) is the main predictor of reporting speed (Pearson r = −0.234 between log(actas) and coverage%), not geographic distance.
- EE.UU. arrives gradually (more consulates, processed independently)
- 50% of exterior in by ~H+39 (June 10)
- 90% of exterior in by ~H+76 (June 12)
- Bulk EUROPA surge: ~H+61–69 (June 11 daytime Lima)
- Total R2 exterior valid votes: ~293,000 (~1.8% of national valid)
- Observed R2 exterior FP h2h: **65.4%** — use this (not R1 finalist h2h) for scenario math

**Watch areas for exterior updates:** `analysis/watch_areas.py` monitors España and EE.UU. (as well as La Convención and Datem del Marañón) every 30s with desktop notification + bell sound.

---

## Prediction History System

`prediction_history.jsonl` — append-only JSONL, one record per snapshot. **Written only by `web/server.py:_record_snapshot()`.** Never write manually.

**Trigger:** All four model caches simultaneously warm AND `coverage_pct` changed ≥0.05% since last record.

**Record schema:**
```json
{
  "ts": 1234567890.123,
  "coverage_pct": 61.8,
  "n_reported": 1299, "n_total": 2102,
  "prop":  [{ "id": "8", "projected_votes": 5200000, "projected_share": 41.48,
              "lower_bound": 39.10, "upper_bound": 43.86, "moe": 2.38, "observed_votes": 3100000 }],
  "migr":  [{ "id": "8", "projected_votes": 7367153, "projected_share": 56.15,
              "lower_bound": 51.17, "upper_bound": 61.13, "moe": 4.98,
              "valid_share": 42.32, "observed_votes": 4965952 }],
  "prop_dept": { "LIMA": { "n_reported": 412, "n_total": 441, "parties": [...] } },
  "migr_dept": { "LIMA": { "n_reported": 412, "n_total": 441, "parties": [...] } }
}
```

`prop[].projected_share` — **valid-vote space** (not h2h). Convert via `projected_votes / sum(projected_votes)`.
`migr[].projected_share` — **already head-to-head**. CI bounds also in h2h space.
Both `prop_dept` and `migr_dept` normalize candidates under key `"parties"`.

---

## Strict Constraints

- **`data/round1/` is immutable.** The pipeline always writes to `data/round2/` only. Never use `data/round1/` as an output target.
- **Do not hardcode party IDs `"8"` or `"10"`.** Finalists are determined dynamically by `_determine_finalists()` in `models/migration.py` and sorted party totals in dashboard JS.
- **Party IDs `"80"` (blancos) and `"81"` (nulos)** must be excluded from all charts, vote share calculations, and model candidate columns. They ARE included in `votos_validos` (blancos count as valid in Peru's system) but are never candidates.
- **Never divide projected vote totals by observed partial `votos_emitidos`.** Incompatible bases — always produces >100% at low coverage. Use the model's `projected_share` or compute h2h explicitly.
- **`projected_share` from the national propagation API is NOT head-to-head.** It uses `votos_validos` (including blancos) as denominator. The two R2 finalists together sum to ~75–85%, not 100%. Always convert h2h client-side.
- **Migration CI residuals must use `y_hat` (per-district WLS prediction), not the national mean.** Using the national mean inflates variance 400×+ because Lima's high vote share is captured by features, not model error.
- **Partially-counted districts must be scaled by `actas_total / actas_contabilizadas`** in the migration model's obs accumulation loop. A district with 1 of 20 actas counted is not fully reported.
- **Never regenerate `data/inputs/migration_cluster_map.json` during a live count.** Stable cluster definitions are required for regression pool consistency across the night.
- **Migration WLS must operate in share space.** Do not revert to raw counts.
- **`render_template`, not `send_file`** for the dashboard route in `web/server.py`. `send_file` bypasses Jinja2 and breaks `ADMIN_TOKEN` injection.
- **Do not reorder the 3-dataset sequence** (`_ub_` → `_lb_` → main) in `buildDatasets()` in the Evolución chart. `fill: '+1'` is index-relative.
- **Never write to `prediction_history.jsonl` outside `_record_snapshot()`.** Deduplication logic depends on `_last_recorded_coverage` being in sync with the file.
- **All new modules in subdirectories must use the `sys.path.insert(0, root)` + `from paths import ...` pattern.** No hardcoded paths anywhere.

---

## Deployment (Cloudflare Tunnel + gunicorn)

Production: **gunicorn** (2 workers, `127.0.0.1:5000`) behind **Cloudflare Tunnel** with **Cloudflare Access** (email allowlist).

```bash
ADMIN_TOKEN=secret gunicorn -w 2 --timeout 120 -b 127.0.0.1:5000 web.server:app
```

- **`ADMIN_TOKEN`** gates `/api/cache/clear`. Never commit to git. Injected as `const ADMIN_TOKEN = "{{ admin_token }}"` in the dashboard template.
- **`CACHE_TTL` = 600s** in production. Explicitly invalidated after each pipeline run: `curl -X POST -H "X-Admin-Token: $TOKEN" https://.../api/cache/clear`.
- **Do not raise worker count above 2.** Each gunicorn worker has its own `_cache` dict — cross-worker cache sharing requires Redis (out of scope).
- **Never expose gunicorn directly to the internet.** Cloudflare Tunnel is the only ingress.

---

## Current Status (June 9, 2026 — Day After Election)

**As of ~12:00 Lima:**

| Scope | Actas | FP | JPP | Margin |
|---|---|---|---|---|
| Domestic (ambito 1) | 97.81% | 8,832,571 | 8,879,755 | **−47,184 JPP** |
| Exterior (ambito 2) | 30.20% | 57,875 | 30,555 | **+27,320 FP** |
| **Combined** | 93.34% districts | **8,890,446** | **8,910,310** | **−19,864 JPP** |

Both models project FP wins: **~50.12% h2h** (migration), **~50.16% valid-space** (propagation).

### Key remaining volumes (as of last run)

| Province | Remaining actas | R1 FP h2h | Est. valid | Net FP |
|---|---|---|---|---|
| Lima (prov.) | 883 | 86.5% | 186,154 | **+135,777** |
| La Convención (Cusco/VRAEM) | 238 | 17.1% | 32,545 | **−21,426** |
| Datem del Marañón (Loreto) | 169 | 30.3% | 13,965 | **−5,513** |
| Callao | 69 | 87.8% | 13,726 | **+10,367** |

### Projected vote arrival timeline

| Stage | FP | JPP | Margin | Batch net |
|---|---|---|---|---|
| NOW | 8,890,446 | 8,910,310 | **−19,864 JPP** | — |
| + Cusco & Loreto | 8,909,401 | 8,953,703 | **−44,302 JPP** | −24,438 |
| + Extranjero | 9,056,823 | 9,031,534 | **+25,289 FP** | +69,591 |
| + Resto doméstico | 9,277,336 | 9,092,426 | **+184,910 FP** | +159,621 |

The race flips to FP once exterior completes. Exterior at 30.2% already shows 65.4% FP h2h. España is only 4.0% counted (18/446 actas) — the EUROPA bulk upload surge is still pending.

### Active monitors

`analysis/watch_areas.py` — polls every 30s for changes in:
- La Convención (Cusco) — VRAEM, JPP-heavy, 62.3% done
- Datem del Marañón (Loreto) — remote jungle, JPP-heavy, 15.1% done
- España — FP-heavy, only 4.0% done, bulk surge expected
- EE.UU. — FP-heavy, 52.6% done

Fires desktop notification (`notify-send`) + bell sound (`paplay`) on any acta change.

### Next objectives

1. Monitor `watch_areas.py` for the España/EUROPA bulk upload surge.
2. When exterior completes or nears completion, re-run the timeline simulation to confirm the flip margin.
3. If desired: generate a static dashboard snapshot (`python web/generate_static.py`) once results are near-final.
