"""
paths.py — single source of truth for every file path in the project.

Import this in any script instead of hardcoding strings:

    from paths import ROUND2, INPUTS, LOG_DIR
    distrital = json.load(open(ROUND2 / "agg_distrital.json"))
"""

from pathlib import Path

ROOT = Path(__file__).parent

# ── Data directories ──────────────────────────────────────────────────────────
DATA   = ROOT / "data"

INPUTS = DATA / "inputs"       # static reference files — never modified
ROUND1 = DATA / "round1"       # first-round final results  — frozen, never overwrite
ROUND2 = DATA / "round2"       # second-round live results  — updated by pipeline

# ── Runtime directories ───────────────────────────────────────────────────────
LOG_DIR    = ROOT / "log"      # per-worker JSONL and log files
BACKUP_DIR = ROOT / "backups"  # auto-backups created on each scraper run

# ── Static input files ────────────────────────────────────────────────────────
UBIGEO_MAP        = INPUTS / "onpe_ubigeo_map.json"
VOTER_ROLLS       = INPUTS / "ubigeo_votos_habiles.json"
MIGRATION_CLUSTERS = INPUTS / "migration_cluster_map.json"
EXTERIOR_2021_CSV = INPUTS / "segunda_vuelta_2021.csv"

# ── Pipeline output files (written by scraper + merge step) ──────────────────
COMBINED_RESULTS = ROOT / "onpe_combined_results.jsonl"
COMBINED_ERRORS  = ROOT / "onpe_combined_errors.jsonl"

# ── Prediction history (written by web server) ────────────────────────────────
PREDICTION_HISTORY = ROOT / "prediction_history.jsonl"

# ── Stop-signal files (IPC between orchestrator and workers) ──────────────────
SCRAPER_STOP_SIGNAL = LOG_DIR / ".stop_signal"
ACTAS_STOP_SIGNAL   = LOG_DIR / ".actas_stop_signal"
