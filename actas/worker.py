"""
actas_worker.py — launched by actas_map_extraction.py, one process per worker.

Env vars
--------
RUN_MODE   patch | update | force   (default: patch)

Args
----
argv[1]  worker_id  (1–5)

Output (per worker, in log/)
-----------------------------
actas_worker_N_results.jsonl  — all acta records for this chunk
actas_worker_N_jee.jsonl      — JEE-flagged actas only
actas_worker_N_errors.jsonl   — failed ubigeos
actas_worker_N_sys.log        — stdout (read by dashboard)
"""

import json
import logging
import os
import random
import shutil
import sys
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import UBIGEO_MAP, ROUND2, BACKUP_DIR as _BACKUP_DIR, LOG_DIR as _LOG_DIR, ACTAS_STOP_SIGNAL

# ── Identity ──────────────────────────────────────────────────────────────────
INPUT_FILE    = str(UBIGEO_MAP)
DISTRITAL     = str(ROUND2 / "agg_distrital.json")
BACKUP_DIR    = str(_BACKUP_DIR)
LOG_DIR       = str(_LOG_DIR)
STOP_FILE     = str(ACTAS_STOP_SIGNAL)
TOTAL_WORKERS = 5

os.makedirs(LOG_DIR, exist_ok=True)

def _get_worker_id() -> int:
    try:
        return int(sys.argv[1])
    except (IndexError, ValueError):
        print("Error: worker_id argument required.")
        sys.exit(1)

WORKER_ID = _get_worker_id()
RUN_MODE  = os.getenv("RUN_MODE", "patch")

RESULTS_FILE = os.path.join(LOG_DIR, f"actas_worker_{WORKER_ID}_results.jsonl")
JEE_FILE     = os.path.join(LOG_DIR, f"actas_worker_{WORKER_ID}_jee.jsonl")
ERROR_FILE   = os.path.join(LOG_DIR, f"actas_worker_{WORKER_ID}_errors.jsonl")
APP_LOG      = os.path.join(LOG_DIR, f"actas_worker_{WORKER_ID}_sys.log")

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [Worker {WORKER_ID}] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(APP_LOG, encoding="utf-8"),
    ],
)
log = logging.getLogger(f"ActasScraper_{WORKER_ID}")

# ── API config ─────────────────────────────────────────────────────────────────
BASE_URL = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/actas"
EXTRA_PARAMS: dict = {}   # add {"idEleccion": "..."} if needed after checking DevTools

# ── JEE detection ─────────────────────────────────────────────────────────────
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


# ── HTTP session ──────────────────────────────────────────────────────────────
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://resultadosegundavuelta.onpe.gob.pe/",
        "Connection": "keep-alive",
    })
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _get(session: requests.Session, params: dict, timeout: int = 20) -> dict:
    """GET with rate-limit backoff."""
    for attempt in range(4):
        time.sleep(random.uniform(0.1, 0.25))
        try:
            r = session.get(BASE_URL, params=params, timeout=timeout)
            if r.status_code in (429, 403):
                wait = (15 * (2 ** attempt)) + random.uniform(2, 7)
                log.warning(f"Rate limit. Cooling {wait:.1f}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise requests.RequestException("Max retries exhausted.")


# ── State loading ─────────────────────────────────────────────────────────────
def _load_pending_ubigeos() -> set[str] | None:
    """
    For 'update' mode: return the set of ubigeos with pct_actas < 100
    from processed_results/agg_distrital.json.  Returns None if file absent.
    """
    if not os.path.exists(DISTRITAL):
        log.warning(f"agg_distrital.json not found at {DISTRITAL}; will process all ubigeos.")
        return None
    with open(DISTRITAL, encoding="utf-8") as f:
        rows = json.load(f)
    pending = {
        str(r["ubigeo"])
        for r in rows
        if float(r.get("pct_actas_contabilizadas") or 0) < 100.0
    }
    log.info(f"Update mode: {len(pending)} ubigeos with pct_actas < 100.")
    return pending


def _load_completed_ubigeos() -> set[str]:
    """
    For 'patch' mode: return ubigeos already present in our results file.
    """
    done: set[str] = set()
    if not os.path.exists(RESULTS_FILE):
        return done
    with open(RESULTS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ub = rec.get("_ubigeo_meta", {}).get("ubigeo") or rec.get("ubigeo", "")
                if ub:
                    done.add(ub)
            except json.JSONDecodeError:
                pass
    log.info(f"Patch mode: {len(done)} ubigeos already in results file (will skip).")
    return done


# ── Core fetch ────────────────────────────────────────────────────────────────
def _fetch(session: requests.Session, ubigeo: str, ambito: str, meta: dict):
    """
    Returns (actas_list, n_jee).  Each acta annotated with _ubigeo_meta.
    """
    base = {"idAmbitoGeografico": ambito, "idUbigeo": ubigeo, **EXTRA_PARAMS}

    total = _get(session, {**base, "pagina": 0, "tamanio": 1}).get("data", {}).get("totalRegistros", 0)
    if total == 0:
        return [], 0

    content = _get(session, {**base, "pagina": 0, "tamanio": total}, timeout=30).get("data", {}).get("content", [])
    for acta in content:
        acta["_ubigeo_meta"] = meta
    n_jee = sum(1 for a in content if _is_jee(a))
    return content, n_jee


# ── Pipeline ──────────────────────────────────────────────────────────────────
def run(items: list[dict], skip: set[str]) -> None:
    session   = _session()
    total     = len(items)
    n_ok = n_skip = n_err = n_jee_total = 0
    TEMP = RESULTS_FILE + ".tmp"

    with open(TEMP,       "w", encoding="utf-8") as f_out, \
         open(JEE_FILE,   "w", encoding="utf-8") as f_jee, \
         open(ERROR_FILE, "w", encoding="utf-8") as f_err:

        for idx, entry in enumerate(items, 1):
            if os.path.exists(STOP_FILE):
                log.warning("Stop signal detected. Committing and exiting.")
                break

            ubigeo   = entry["ubigeo_final"].strip()
            ambito   = "1" if entry["ambito"].strip().lower() == "peru" else "2"
            distrito = entry.get("distrito", "?")
            meta = {
                "ubigeo":       ubigeo,
                "ambito":       entry["ambito"],
                "departamento": entry.get("departamento", ""),
                "provincia":    entry.get("provincia", ""),
                "distrito":     distrito,
            }

            if ubigeo in skip:
                n_skip += 1
                if idx % 50 == 0:
                    log.info(f"[{idx}/{total}] SKIP {distrito} ({ubigeo})")
                continue

            try:
                actas, n_jee = _fetch(session, ubigeo, ambito, meta)

                for acta in actas:
                    f_out.write(json.dumps(acta, ensure_ascii=False) + "\n")
                    if _is_jee(acta):
                        f_jee.write(json.dumps(acta, ensure_ascii=False) + "\n")

                f_out.flush()
                f_jee.flush()
                n_ok += 1
                n_jee_total += n_jee

                jee_tag = f" ⚠ {n_jee} JEE" if n_jee else ""
                log.info(f"[{idx}/{total}] OK {distrito} ({ubigeo}) {len(actas)} actas{jee_tag}")

            except Exception as exc:
                err = {**meta, "error": str(exc), "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
                f_err.write(json.dumps(err, ensure_ascii=False) + "\n")
                f_err.flush()
                n_err += 1
                log.error(f"[{idx}/{total}] ERR {distrito} ({ubigeo}): {exc}")

    # Atomic swap with backup
    if os.path.exists(TEMP):
        if os.path.exists(RESULTS_FILE):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(RESULTS_FILE, os.path.join(
                BACKUP_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_actas_worker_{WORKER_ID}.jsonl"
            ))
        shutil.move(TEMP, RESULTS_FILE)

    log.info(f"Done. ok={n_ok} skip={n_skip} err={n_err} jee={n_jee_total}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(INPUT_FILE):
        log.error(f"Ubigeo map not found: {INPUT_FILE}")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        all_ubigeos = json.load(f)

    # Each worker takes every Nth item (same modulo pattern as scraper.py)
    chunk = [e for i, e in enumerate(all_ubigeos) if i % TOTAL_WORKERS == WORKER_ID - 1]
    log.info(f"Worker {WORKER_ID}/{TOTAL_WORKERS} — mode={RUN_MODE} — chunk={len(chunk)} ubigeos")

    if RUN_MODE == "update":
        pending = _load_pending_ubigeos()
        if pending is not None:
            chunk = [e for e in chunk if e["ubigeo_final"].strip() in pending]
            log.info(f"After update filter: {len(chunk)} ubigeos with pending actas.")
        skip: set[str] = set()

    elif RUN_MODE == "patch":
        skip = _load_completed_ubigeos()

    else:  # force
        log.info("Force mode: processing all ubigeos in chunk.")
        skip = set()

    run(chunk, skip)


if __name__ == "__main__":
    main()
