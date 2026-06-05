# Election Night Operations Guide — Segunda Vuelta

This guide covers everything you need to do from the hour before polls close through the end of the count. Follow the steps in order.

---

## Pre-Election Checklist (Run Before Polls Close)

### 1. Restore first-round data in `processed_results/`

If you ran the simulation at any point, `processed_results/` currently contains synthetic data. You must restore the real first-round data before the scraper begins overwriting it with segunda vuelta results:

```bash
source .venv/bin/activate
python simulate_segunda_vuelta.py --restore
```

Confirm with:
```bash
python simulate_segunda_vuelta.py --check
```

You should see 38 parties listed. If you see only parties `8`, `10`, `80`, `81` you are still on simulated data — run `--restore` again.

### 2. Verify the cluster map is present

The vote migration model requires a precomputed cluster map. Check it exists:

```bash
ls -lh inputs/migration_cluster_map.json
```

It should be ~1MB and dated before election night. **Never regenerate this file during a live count.** If it is missing, run:

```bash
python migration_model.py --build
```

This reads `first_round_agg_results/` (which is frozen and correct) and writes `inputs/migration_cluster_map.json`. This is a one-time operation.

### 3. Clear old scraper logs and prediction history

```bash
rm -f log/*.jsonl log/*.log log/.stop_signal
rm -f prediction_history.jsonl
```

The first command prevents stale scraper data from being merged into the live count. The second clears the projection history log so the **Evolución** tab in the dashboard starts fresh with real election night data — not test or simulation snapshots.

### 4. Start the dashboard server

In a dedicated terminal tab that you will leave running all night:

```bash
source .venv/bin/activate
python app.py
```

The dashboard is at `http://127.0.0.1:5000`. Open it in your browser now and confirm:
- The **Primera Vuelta** tab shows 38 parties, 100% of actas counted
- The **Segunda Vuelta** tab shows "Esperando datos de segunda vuelta..." in both model cards

If the Segunda Vuelta tab is already showing data, the restore step above did not complete correctly.

---

## Election Night: When Results Start Rolling

### Phase 1 — First actas appear (0–5% coverage)

ONPE begins publishing results. The scraper detects only `8`, `10`, `80`, and `81` in the data — this is the live gate that switches the dashboard from first-round mode to live segunda vuelta mode automatically. No code change is needed.

**Start the scraper in `patch` mode** (this is the default and the correct mode for a live count):

```bash
source .venv/bin/activate
python run_cluster.py --mode patch
```

This launches 5 parallel workers. The TUI dashboard in the terminal shows each worker's status and progress. Leave this running.

**`patch` mode behavior:** Workers skip districts already logged as successful (100% `pct_actas_contabilizadas`) and retry only those logged in `errors.jsonl`. This is the correct mode for all-night operation.

### Phase 2 — After each scraper run, refresh the aggregates

The scraper writes raw JSONL records. To update the model and dashboard, you must run the merge + process pipeline after each scraper pass:

```bash
# Run after each scraper cycle completes
python merge_workers.py
python processData.py
```

The dashboard reads from the files `processData.py` writes. The model endpoints cache results for 60 seconds — after running the pipeline, wait up to 60 seconds for the dashboard to reflect the new data, or click the **Actualizar** button on the dashboard to force a cache refresh.

**History snapshots are automatic.** Each time the model cache expires and all four model endpoints are called (which happens on every manual refresh or whenever the browser reloads), a timestamped snapshot is appended to `prediction_history.jsonl`. The **Evolución** tab plots this series over time with 95% CI bands. No extra step is needed — just keep refreshing the dashboard at a regular cadence throughout the night.

**Recommended cadence during the count:**

| Coverage | Suggested pipeline frequency |
|---|---|
| 0–25% | Every 15–20 minutes |
| 25–75% | Every 10 minutes |
| 75–100% | Every 5–10 minutes |

The scraper itself can run continuously — it is safe to run `run_cluster.py` again before the previous pass has fully finished, as long as you wait for `merge_workers.py` to complete before running it again.

### Phase 3 — Handling partial results (districts that update)

Once ONPE begins publishing final counts for districts that were previously partial, switch to `update` mode:

```bash
python run_cluster.py --mode update
```

`update` mode re-fetches any district where `pct_actas_contabilizadas < 100%` — catching districts that updated from partial to final. Use this when you notice the overall progress percentage on the dashboard has stalled despite knowing ONPE is publishing new results.

Only use `force` mode if you have reason to believe the local cache is corrupted:

```bash
python run_cluster.py --mode force   # Full re-scrape — use sparingly
```

---

## Full Pipeline Command Reference

```
# Order matters. Always run in this sequence:
python run_cluster.py --mode patch     # 1. Scrape (leave running)
python merge_workers.py                # 2. Merge worker outputs
python processData.py                  # 3. Aggregate into JSON files
# Dashboard auto-refreshes within 60s  # 4. Frontend updates automatically
```

The propagation model (`propagation_model.py`) and migration model (`migration_model.py`) are called live by `app.py` when the dashboard requests `/api/model/propagation` and `/api/model/migration`. You do not need to run them manually.

---

## Dashboard: What You're Looking At

### Segunda Vuelta Tab

- **KPI row**: Total actas, % contabilizadas, votos válidos — pulled live from `processed_results/`
- **Progress bar**: Percentage of actas counted
- **Bar chart**: Raw observed vote shares for both finalists (+ blancos/nulos)
- **Propagation model card**: Dynamic stratified projection with 95% CI. Districts with <50% actas or <14 actas counted are imputed from provincial/departmental trends
- **Migration model card**: Vote migration WLS projection. Shows `projected_share` (head-to-head: F1 vs F2, sums to 100%) and `valid_share` (share of all valid votes, context only). Confidence intervals use FPC-corrected clustered standard errors

### Model card states

| State shown | Meaning |
|---|---|
| Spinner | Still loading or cache not yet expired |
| "Esperando datos de segunda vuelta..." | `processed_results/` still has primera vuelta data (>2 parties) |
| "Datos insuficientes..." | Fewer than 4 districts reported — model cannot fit yet |
| Results with CI bars | Model is active and projecting |

### Refreshing the cache manually

Click the **Actualizar** button in the dashboard header. This resets the 60-second model cache and immediately re-runs both models against the latest data on disk. Use this after running `merge_workers.py` + `processData.py` if you don't want to wait for the automatic cache expiry.

Each manual refresh also triggers a new history snapshot (if coverage has changed by ≥0.05% since the last one), so clicking **Actualizar** after each pipeline run is both the fastest way to see updated results and the way to build up the evolution chart.

---

## Stopping the Scraper

To send a clean stop signal to all 5 workers (they finish their current district before stopping):

```bash
touch log/.stop_signal
```

The workers check for this file between requests and exit gracefully. The TUI dashboard will show workers transitioning to `DONE` status.

To stop immediately: `Ctrl+C` in the terminal running `run_cluster.py`.

---

## Troubleshooting

### Dashboard shows no segunda vuelta data after the scraper ran

1. Check that `merge_workers.py` and `processData.py` have been run since the last scraper pass
2. Check `processed_results/idx_codigo_nombre_partido.json` — if it still lists 38 parties, `processData.py` did not write new data. Re-run it
3. Check `log/` for `onpe_combined_results_worker_*.jsonl` files — if they are empty, the scraper has not successfully fetched any records yet

### Model card shows an error instead of results

The most common cause is `processed_results/agg_distrital.json` being empty or malformed. Check:
```bash
python -c "import json; d=json.load(open('processed_results/agg_distrital.json')); print(len(d), 'districts')"
```

If this errors or returns 0, re-run `processData.py`.

### Propagation model shows 0% MOE before 100% counted

This is expected behavior only at exactly 100%. If you see 0% MOE at partial coverage, check that `inputs/ubigeo_votos_habiles.json` is present — the model uses it to estimate pending votes.

### ONPE API returning malformed JSON

The scraper logs these to `onpe_combined_errors.jsonl`. In `patch` mode, it will retry these automatically on the next run. In `update` mode it will also retry. You can inspect errors with:

```bash
wc -l onpe_combined_errors.jsonl   # count of error records
tail -5 onpe_combined_errors.jsonl # most recent errors
```

### Migration model CI is very wide early in the count

This is normal. The FPC-corrected sandwich standard errors are intentionally conservative when n/N is small. The CI will narrow as coverage increases. Below 25% coverage, treat the migration model projection as directional only.

---

## Files Written During the Count

| File | Written by | Notes |
|---|---|---|
| `log/onpe_combined_results_worker_N.jsonl` | `run_cluster.py` | Raw per-worker records; overwritten each run |
| `log/worker_N_sys.log` | `run_cluster.py` | Worker stdout/stderr for debugging |
| `onpe_combined_results.jsonl` | `merge_workers.py` | Unified record set; input to `processData.py` |
| `onpe_combined_errors.jsonl` | `merge_workers.py` | Scrape failures for retry |
| `processed_results/*.json` | `processData.py` | Aggregates read by the dashboard and models |
| `prediction_history.jsonl` | `app.py` (auto) | Timestamped model snapshots; powers the Evolución tab |
| `backups/` | `run_cluster.py` | Timestamped auto-backups created at each run start |

**Never touch `first_round_agg_results/` during the count.** That directory is frozen.

---

## After the Count Is Complete

When `pct_actas_contabilizadas` reaches 100% for both ambieres:

1. Stop the scraper: `touch log/.stop_signal`
2. Run the pipeline one final time: `python merge_workers.py && python processData.py`
3. Click **Actualizar** on the dashboard to record a final history snapshot
4. Generate the final standalone projection chart:
   ```bash
   python propagation_model.py
   ```
   This writes `election_projection_dashboard.html` — a self-contained Plotly file you can share or archive
5. The dashboard will show MOE = 0.0% and all model projections will converge to observed values

The `processed_results/` directory now contains the final segunda vuelta aggregates. Archive it alongside `first_round_agg_results/` for the historical record.
