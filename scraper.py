import os
import sys
import json
import time
import random
import shutil
import logging
from typing import Dict, Any, Tuple, List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# --- GLOBAL ONPE CONFIGURATION ---
ID_ELECCION = "10"  
TOTAL_WORKERS = 5

INPUT_FILE = "inputs/onpe_ubigeo_map.json"
BACKUP_DIR = "backups"
LOG_DIR = "log"

os.makedirs(LOG_DIR, exist_ok=True)

def get_worker_id() -> int:
    if len(sys.argv) < 2:
        print("Error: Missing worker instance ID argument.")
        sys.exit(1)
    try:
        return int(sys.argv[1])
    except ValueError:
        print("Error: Worker ID must be an integer.")
        sys.exit(1)

WORKER_ID = get_worker_id()
RUN_MODE = os.getenv("RUN_MODE", "patch")  

# Signal file path that tells this worker to wrap up and exit safely
STOP_SIGNAL_FILE = os.path.join(LOG_DIR, ".stop_signal")

RESULTS_FILE = os.path.join(LOG_DIR, f"onpe_combined_results_worker_{WORKER_ID}.jsonl")
ERROR_FILE = os.path.join(LOG_DIR, f"onpe_combined_errors_worker_{WORKER_ID}.jsonl")
APP_LOG_FILE = os.path.join(LOG_DIR, f"scraper_worker_{WORKER_ID}.log")

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [Worker {WORKER_ID}] [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(APP_LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger(f"ONPEScraper_{WORKER_ID}")

URL_PARTICIPANTES = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/eleccion-presidencial/participantes-ubicacion-geografica-nombre"
URL_TOTALES = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales"


def load_completed_state(mode: str) -> Dict[str, Dict[str, Any]]:
    completed_ubigeos = {}
    all_raw_records = {}

    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    ubigeo = record.get("ubigeo")
                    if ubigeo:
                        all_raw_records[ubigeo] = record
        except Exception as e:
            logger.warning(f"Could not parse results ledger smoothly: {e}")

    if mode == "patch":
        logger.info("Strategy: [Method 1] Bypassing all safe items. Target ONLY errors.jsonl entries.")
        error_ubigeos = set()
        if os.path.exists(ERROR_FILE):
            try:
                with open(ERROR_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        err_record = json.loads(line)
                        ubigeo_err = err_record.get("ubigeo_final") or err_record.get("ubigeo")
                        if ubigeo_err:
                            error_ubigeos.add(ubigeo_err.strip())
            except Exception as e:
                logger.warning(f"Error ledger tracking unreadable: {e}")

        for ubigeo, record in all_raw_records.items():
            if ubigeo.strip() not in error_ubigeos:
                completed_ubigeos[ubigeo] = record

    elif mode == "update":
        logger.info("Strategy: [Method 2] Bypassing exactly 100% items. Updating active counts.")
        for ubigeo, record in all_raw_records.items():
            totales = record.get("totales", {}) or {}
            pct_str = totales.get("pct_actas_contabilizadas")
            try:
                pct = float(pct_str) if pct_str is not None else 0.0
            except (ValueError, TypeError):
                pct = 0.0

            if pct >= 100.0:
                completed_ubigeos[ubigeo] = record

    elif mode == "force":
        logger.info("Strategy: [Method 3] Force mode. Ignoring cache layer, hitting network for everything.")
        pass
        
    return completed_ubigeos


def get_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
    # The "Identity" - Updated for April 2026
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    
    # Modern Chrome "Client Hints" (Crucial for bypassing modern bot detection)
    "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    
    # Navigation and Content Types
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    
    # Origin and Security
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://resultadoelectoral.onpe.gob.pe/",
    "Connection": "keep-alive"
    })
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def build_payloads(entry: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    u3 = entry['ubigeo_final'].strip()
    u2 = f"{u3[:4]}00"
    u1 = f"{u3[:2]}0000"
    ambito = "1" if entry['ambito'].strip().lower() == "peru" else "2"
    
    return {
        "tipoFiltro": "ubigeo_nivel_03", "idAmbitoGeografico": ambito,
        "ubigeoNivel1": u1, "ubigeoNivel2": u2, "ubigeoNivel3": u3, "idEleccion": ID_ELECCION
    }, {
        "idAmbitoGeografico": ambito, "idEleccion": ID_ELECCION, "tipoFiltro": "ubigeo_nivel_03",
        "idUbigeoDepartamento": u1, "idUbigeoProvincia": u2, "idUbigeoDistrito": u3
    }


def request_endpoint(session: requests.Session, url: str, params: Dict[str, str]) -> Dict[str, Any]:
    base_sleep = random.uniform(0.4, 1.2)
    if random.random() < 0.03:
        base_sleep += random.uniform(4.0, 8.0)
    time.sleep(base_sleep)
    
    max_backoff_attempts = 4
    for attempt in range(max_backoff_attempts):
        try:
            response = session.get(url, params=params, timeout=30)
            if response.status_code in [429, 403]:
                cooling_time = (15 * (2 ** attempt)) + random.uniform(2.0, 7.0)
                logger.warning(f"Rate limit hit. Cooling down {cooling_time:.2f}s...")
                time.sleep(cooling_time)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            if attempt == max_backoff_attempts - 1:
                raise exc
            time.sleep(5 * (attempt + 1))
            
    raise requests.exceptions.RequestException("Max backoff limits exhausted.")


def clean_and_compress_data(entry: Dict[str, Any], raw_p: Dict[str, Any], raw_t: Dict[str, Any], ambito_id: str) -> Dict[str, Any]:
    compressed_participantes = []
    raw_candidates_list = raw_p.get("data", []) or []
    for cand in raw_candidates_list:
        compressed_participantes.append({
            "partido": cand.get("nombreAgrupacionPolitica"),
            "id": cand.get("codigoAgrupacionPolitica"),
            "votos": cand.get("totalVotosValidos")
        })
        
    raw_totals_data = raw_t.get("data", {}) or []
    if isinstance(raw_totals_data, list) and len(raw_totals_data) > 0:
        raw_totals_data = raw_totals_data[0]
    elif not isinstance(raw_totals_data, dict):
        raw_totals_data = {}

    return {
        "ubigeo": entry['ubigeo_final'].strip(),
        "ambito": ambito_id,
        "meta": {
            "dep": entry.get("departamento", "").strip(),
            "prov": entry.get("provincia", "").strip(),
            "dist": entry.get("distrito", "").strip()
        },
        "participantes": compressed_participantes,
        "totales": {
            "pct_actas_contabilizadas": raw_totals_data.get("actasContabilizadas"),
            "actas_total": raw_totals_data.get("totalActas"),
            "actas_contabilizadas": raw_totals_data.get("contabilizadas"),
            "pct_participacion": raw_totals_data.get("participacionCiudadana"),
            "votos_emitidos": raw_totals_data.get("totalVotosEmitidos"),
            "votos_validos": raw_totals_data.get("totalVotosValidos"),
            "pct_votos_emitidos": raw_totals_data.get("porcentajeVotosEmitidos"),
            "pct_votos_validos": raw_totals_data.get("porcentajeVotosValidos")
        }
    }


def run_pipeline(items: List[Dict[str, Any]], completed_states: Dict[str, Dict[str, Any]]) -> None:
    total_items = len(items)
    success_count = 0
    skipped_count = 0
    interrupted = False
    
    session = get_http_session()
    TEMP_RESULTS = f"{RESULTS_FILE}.tmp"
    
    with open(TEMP_RESULTS, "w", encoding="utf-8") as f_out, \
         open(ERROR_FILE, "w", encoding="utf-8") as f_err:
        
        for idx, entry in enumerate(items, 1):
            # Check the poison pill exit flag file before running the next network call
            if os.path.exists(STOP_SIGNAL_FILE):
                logger.warning("Stop signal file identified. Committing data collected so far and closing...")
                interrupted = True
                break
                
            distrito = entry.get('distrito', 'Unknown')
            ubigeo_code = entry.get('ubigeo_final', '000000').strip()
            
            if ubigeo_code in completed_states:
                f_out.write(json.dumps(completed_states[ubigeo_code], ensure_ascii=False) + "\n")
                skipped_count += 1
                if idx % 20 == 0 or idx == total_items:
                    logger.info(f"[{idx}/{total_items}] Check: {distrito} ({ubigeo_code}) -> BYPASSED")
                continue
            
            try:
                params_p, params_t = build_payloads(entry)
                raw_p = request_endpoint(session, URL_PARTICIPANTES, params_p)
                raw_t = request_endpoint(session, URL_TOTALES, params_t)
                
                processed_record = clean_and_compress_data(entry, raw_p, raw_t, params_p["idAmbitoGeografico"])
                f_out.write(json.dumps(processed_record, ensure_ascii=False) + "\n")
                f_out.flush()
                
                success_count += 1
                logger.info(f"[{idx}/{total_items}] Progress: {distrito} ({ubigeo_code}) -> FETCH SUCCESS")
                
            except Exception as error:
                error_log = {
                    "ubigeo_final": ubigeo_code, "ambito": entry.get('ambito', 'Peru'), "distrito": distrito,
                    "error": str(error), "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                f_err.write(json.dumps(error_log, ensure_ascii=False) + "\n")
                f_err.flush()
                logger.error(f"[{idx}/{total_items}] Fault at {distrito} ({ubigeo_code}) -> {error}")

    # Process save logic whether loop finishes or gets interrupted
    if os.path.exists(TEMP_RESULTS):
        if os.path.exists(RESULTS_FILE):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(RESULTS_FILE, os.path.join(BACKUP_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_results_worker_{WORKER_ID}.jsonl"))
        
        shutil.move(TEMP_RESULTS, RESULTS_FILE)
        logger.info("Atomic update finalized. Data safely committed.")

    if interrupted:
        sys.exit(0)


def get_worker_chunk(all_items: List[Any], worker_idx: int, total_workers: int) -> List[Any]:
    return [item for idx, item in enumerate(all_items) if (idx % total_workers) == (worker_idx - 1)]


def extract_all() -> None:
    if not os.path.exists(INPUT_FILE):
        return
        
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        ubigeo_map = json.load(f)
        
    worker_chunk = get_worker_chunk(ubigeo_map, WORKER_ID, TOTAL_WORKERS)
    completed_states = load_completed_state(RUN_MODE)
    run_pipeline(worker_chunk, completed_states)


if __name__ == "__main__":
    extract_all()