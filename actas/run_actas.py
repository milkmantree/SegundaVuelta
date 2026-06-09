"""
actas_map_extraction.py — Segunda Vuelta orchestrator

Launches 5 parallel actas_worker.py processes, shows a live dashboard,
then merges per-worker outputs into unified files and prints a JEE summary.

Usage
-----
    python actas_map_extraction.py                  # patch mode (default)
    python actas_map_extraction.py --mode update    # only districts with pct < 100
    python actas_map_extraction.py --mode force     # re-fetch everything
    python actas_map_extraction.py --mode analyze   # re-scan existing results, no scrape

Modes
-----
patch   Skip ubigeos already in worker results files; re-fetch only new ones.
update  Only fetch ubigeos where processed_results/agg_distrital.json shows
        pct_actas_contabilizadas < 100. Fastest for mid-count refresh.
force   Re-fetch every ubigeo regardless of cached state.
analyze Merge + JEE-filter existing per-worker files without hitting the network.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import LOG_DIR as _LOG_DIR, ACTAS_STOP_SIGNAL

WORKER_SCRIPT  = os.path.join(os.path.dirname(__file__), "worker.py")
TOTAL_WORKERS  = 5
LOG_DIR        = str(_LOG_DIR)
STOP_FILE      = str(ACTAS_STOP_SIGNAL)

# Merged output (written after all workers finish)
_ACTAS_DIR   = os.path.dirname(__file__)
RESULTS_FILE = os.path.join(_ACTAS_DIR, "actas_results.jsonl")
JEE_FILE     = os.path.join(_ACTAS_DIR, "actas_jee.jsonl")

# ── JEE detection (mirrors actas_worker.py — kept in sync manually) ───────────
_STATUS_FIELDS = {
    "estadoActa", "codigoEstadoActa", "descripcionEstadoActa",
    "estado", "codigoEstado", "descripcionEstado",
    "tipoResolucion", "estadoResolucion",
}
_JEE_KEYWORDS = {
    "jee", "jurado", "observ", "impugn", "revision", "revisión",
    "cuestion", "cuestión", "tacha", "nulidad",
}

def _is_jee(acta: dict) -> bool:
    for key, val in acta.items():
        if not isinstance(val, str):
            continue
        vl = val.lower()
        if key in _STATUS_FIELDS and any(kw in vl for kw in _JEE_KEYWORDS):
            return True
        if any(kw in vl for kw in _JEE_KEYWORDS):
            return True
    return False


# ── Per-worker file paths ─────────────────────────────────────────────────────
def _worker_results(n: int) -> str:
    return os.path.join(LOG_DIR, f"actas_worker_{n}_results.jsonl")

def _worker_jee(n: int) -> str:
    return os.path.join(LOG_DIR, f"actas_worker_{n}_jee.jsonl")

def _worker_sys_log(n: int) -> str:
    return os.path.join(LOG_DIR, f"actas_worker_{n}_sys.log")


# ── Dashboard ─────────────────────────────────────────────────────────────────
def _last_log_line(worker_id: int) -> str:
    path = _worker_sys_log(worker_id)
    if not os.path.exists(path):
        return "Initializing..."
    try:
        with open(path, "rb") as f:
            try:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b"\n":
                    f.seek(-2, os.SEEK_CUR)
            except OSError:
                f.seek(0)
            line = f.readline().decode("utf-8", errors="ignore").strip()
            if "]" in line:
                line = line.split("]")[-1].strip()
            return line or "Processing..."
    except Exception:
        return "Reading log..."


def _render_dashboard(processes: list, mode: str) -> None:
    cols, _ = shutil.get_terminal_size((80, 24))
    sys.stdout.write("\033[H")
    print(f"=== ONPE ACTAS CLUSTER [MODE: {mode.upper()}] ===\033[K")
    print(f"{'-' * min(cols, 90)}\033[K")

    running = 0
    for wid, p in enumerate(processes, 1):
        status = p.poll()
        if status is None:
            status_str = "\033[92mRUNNING\033[0m"
            running += 1
            action = _last_log_line(wid)
        elif status == 0:
            status_str = "\033[94mSUCCESS\033[0m"
            action = "Finished chunk."
        else:
            status_str = f"\033[91mCRASHED ({status})\033[0m"
            action = f"Check {_worker_sys_log(wid)}"

        max_len = max(10, cols - 38)
        if len(action) > max_len:
            action = action[:max_len - 3] + "..."
        print(f" Worker #{wid} (PID: {p.pid:<5d}) | {status_str:<18} | {action}\033[K")

    print(f"{'-' * min(cols, 90)}\033[K")
    print(f" Cluster: {running}/{TOTAL_WORKERS} running\033[K")
    print(" Ctrl+C to stop safely.\033[K")
    print("=" * min(cols, 90) + "\033[K")
    sys.stdout.flush()


# ── Merge + JEE summary ───────────────────────────────────────────────────────
def _merge_workers():
    """Concatenate per-worker result files into unified actas_results.jsonl / actas_jee.jsonl."""
    print("\n📦 Merging per-worker outputs...")

    total = jee_count = 0
    with open(RESULTS_FILE, "w", encoding="utf-8") as f_out, \
         open(JEE_FILE,     "w", encoding="utf-8") as f_jee:

        for n in range(1, TOTAL_WORKERS + 1):
            path = _worker_results(n)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as src:
                for line in src:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    f_out.write(line + "\n")
                    try:
                        acta = json.loads(line)
                        if _is_jee(acta):
                            f_jee.write(line + "\n")
                            jee_count += 1
                    except json.JSONDecodeError:
                        pass

    print(f"✅ Merged: {total:,} actas total | {jee_count} JEE-flagged")
    return jee_count


def _print_jee_summary():
    if not os.path.exists(JEE_FILE) or os.path.getsize(JEE_FILE) == 0:
        print("  (no JEE actas found)")
        return

    by_dept: dict[str, list] = {}
    with open(JEE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            dept = rec.get("departamento") or rec.get("_ubigeo_meta", {}).get("departamento", "?")
            by_dept.setdefault(dept, []).append(rec)

    total = sum(len(v) for v in by_dept.values())
    print(f"\n  ┌─ JEE ACTAS ({total} total) {'─'*48}┐")
    for dept in sorted(by_dept):
        actas = by_dept[dept]
        statuses: set[str] = set()
        for a in actas:
            for field in _STATUS_FIELDS:
                val = a.get(field, "")
                if val and isinstance(val, str):
                    statuses.add(val.upper())
        status_str = ", ".join(sorted(statuses)) if statuses else "—"
        print(f"  │  {dept:<20}  {len(actas):>4} actas   estados: {status_str}")
    print(f"  └{'─'*68}┘\n")


# ── Orchestrator ──────────────────────────────────────────────────────────────
def launch(mode: str) -> None:
    if not os.path.exists(WORKER_SCRIPT):
        print(f"❌ Worker script not found: {WORKER_SCRIPT}")
        sys.exit(1)

    os.makedirs(LOG_DIR, exist_ok=True)
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    processes = []
    log_files = []

    sys.stdout.write("\033[2J\033[?25l")
    sys.stdout.flush()

    try:
        for wid in range(1, TOTAL_WORKERS + 1):
            log_f = open(_worker_sys_log(wid), "w", encoding="utf-8")
            log_files.append(log_f)

            env = os.environ.copy()
            env["RUN_MODE"] = mode

            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["preexec_fn"] = os.setpgrp

            p = subprocess.Popen(
                [sys.executable, WORKER_SCRIPT, str(wid)],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=env,
                **kwargs,
            )
            processes.append(p)

        while True:
            _render_dashboard(processes, mode)
            if all(p.poll() is not None for p in processes):
                break
            time.sleep(0.3)

    except KeyboardInterrupt:
        sys.stdout.write("\033[?25h\n")
        print("\n[!] Interrupt — signalling workers to stop...")
        Path(STOP_FILE).write_text("STOP")
        while any(p.poll() is None for p in processes):
            running = sum(1 for p in processes if p.poll() is None)
            sys.stdout.write(f"\r  Waiting for {running} worker(s)...   ")
            sys.stdout.flush()
            time.sleep(0.3)
        print("\n  All workers stopped.")

    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        for lf in log_files:
            lf.close()
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)

    _merge_workers()
    _print_jee_summary()


def analyze() -> None:
    """Re-scan existing per-worker files for JEE actas (no network calls)."""
    print("🔍 Analyzing existing worker files for JEE actas...")
    _merge_workers()
    _print_jee_summary()


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ONPE Actas cluster — Segunda Vuelta"
    )
    parser.add_argument(
        "--mode",
        choices=["patch", "update", "force", "analyze"],
        default="patch",
        help=(
            "patch: skip already-fetched ubigeos | "
            "update: only districts with pct_actas < 100 | "
            "force: re-fetch all | "
            "analyze: re-scan existing files (no network)"
        ),
    )
    args = parser.parse_args()

    if args.mode == "analyze":
        analyze()
    else:
        launch(args.mode)
