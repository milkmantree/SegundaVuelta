#!/usr/bin/env python3
"""Poll ONPE exterior (ambito 2) totals and alert when actas > 1.
When the count changes, reads onpe_combined_results.jsonl to identify
which countries/districts newly started reporting.
"""

import json
import subprocess
import threading
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL_TOTALS   = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales"
PARAMS_EXT   = {"idEleccion": "10", "tipoFiltro": "ambito_geografico", "idAmbitoGeografico": "2"}
POLL_INTERVAL = 30  # seconds
ALERT_SOUND   = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"

JSONL_PATH = Path(__file__).parent / "onpe_combined_results.jsonl"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://resultadoelectoral.onpe.gob.pe/",
        "Connection": "keep-alive",
    })
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def desktop_alert(title: str, message: str) -> None:
    try:
        subprocess.run(["notify-send", "-u", "critical", "-t", "0", title, message], check=False)
    except FileNotFoundError:
        pass
    try:
        subprocess.Popen(["paplay", ALERT_SOUND])
    except FileNotFoundError:
        pass
    print(f"\a\a\a*** ALERT: {title} — {message} ***")


def extract_actas(data: dict) -> tuple[int, int]:
    payload = data.get("data", data) if isinstance(data, dict) else {}
    if "contabilizadas" in payload:
        return int(payload["contabilizadas"]), int(payload.get("totalActas", 0))
    if "actasContabilizadas" in payload:
        return int(payload["actasContabilizadas"]), int(payload.get("totalActas", payload.get("actasTotal", 0)))
    return -1, -1


def read_exterior_from_jsonl() -> dict[str, dict]:
    """Read onpe_combined_results.jsonl and return exterior districts with actas > 0.
    Returns {ubigeo: {country, district, region, actas_cont, actas_total}} for actas_cont > 0.
    """
    reporting: dict[str, dict] = {}
    if not JSONL_PATH.exists():
        return reporting
    with open(JSONL_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ambito") != "2":
                continue
            totales = r.get("totales", {})
            cont  = totales.get("actas_contabilizadas", 0)
            total = totales.get("actas_total", 0)
            if cont and int(cont) > 0:
                ubigeo = r.get("ubigeo", "")
                meta   = r.get("meta", {})
                reporting[ubigeo] = {
                    "ubigeo":     ubigeo,
                    "region":     meta.get("dep", "?"),      # e.g. AMÉRICA
                    "country":    meta.get("prov", "?"),     # e.g. ARGENTINA
                    "district":   meta.get("dist", "?"),     # e.g. MENDOZA
                    "actas_cont": int(cont),
                    "actas_total": int(total),
                }
    return reporting


def format_reporting(districts: dict[str, dict]) -> str:
    if not districts:
        return "  (ningún distrito en JSONL)"
    lines = []
    for d in sorted(districts.values(), key=lambda x: -x["actas_cont"]):
        lines.append(
            f"  {d['region']:8s} › {d['country']:15s} › {d['district']:25s} "
            f"{d['actas_cont']}/{d['actas_total']} actas"
        )
    return "\n".join(lines)


def main() -> None:
    session = make_session()
    print(f"Polling ONPE exterior every {POLL_INTERVAL}s. Ctrl-C to stop.\n")

    prev_count = -1
    known_ubigeos: set[str] = set()

    while True:
        ts = time.strftime("%H:%M:%S")
        try:
            resp = session.get(URL_TOTALS, params=PARAMS_EXT, timeout=20)
            resp.raise_for_status()
            actas_cont, actas_total = extract_actas(resp.json())

            if actas_cont == -1:
                print(f"[{ts}] Unknown response shape: {resp.text[:200]}")
            else:
                pct = actas_cont / actas_total * 100 if actas_total > 0 else 0.0
                changed = actas_cont != prev_count and prev_count >= 0

                print(f"[{ts}] Exterior: {actas_cont}/{actas_total} ({pct:.2f}%)"
                      + (" [CAMBIO]" if changed else ""))

                if actas_cont > 1 and changed:
                    delta = actas_cont - prev_count

                    # Fire alert immediately — do NOT block on identification
                    desktop_alert(
                        "ONPE Exterior — actas llegando!",
                        f"+{delta} actas · {actas_cont}/{actas_total} ({pct:.2f}%) · identificando origen…",
                    )

                    # Identify countries in background so alert is never delayed
                    def identify(delta=delta, actas_cont=actas_cont, actas_total=actas_total,
                                 pct=pct, ts=ts):
                        current = read_exterior_from_jsonl()
                        newly   = {k: v for k, v in current.items() if k not in known_ubigeos}
                        known_ubigeos.update(current.keys())

                        if newly:
                            newly_str = ", ".join(
                                f"{v['country']} ({v['district']})"
                                for v in sorted(newly.values(), key=lambda x: -x["actas_cont"])
                            )
                            print(f"[{ts}] NUEVOS DISTRITOS:\n{format_reporting(newly)}")
                            print(f"[{ts}] TODOS REPORTANDO:\n{format_reporting(current)}")
                            desktop_alert("ONPE Exterior — origen identificado", newly_str)
                        else:
                            note = (", ".join(
                                f"{v['country']} ({v['district']})"
                                for v in sorted(current.values(), key=lambda x: -x["actas_cont"])
                            ) or "ejecuta el scraper para identificar origen")
                            print(f"[{ts}] Sin nuevos en JSONL (pipeline aún no corrió).")
                            print(f"[{ts}] Actualmente en JSONL:\n{format_reporting(current)}")
                            desktop_alert("ONPE Exterior — origen (JSONL previo)", note)

                    threading.Thread(target=identify, daemon=True).start()

                elif actas_cont > 1 and prev_count < 0:
                    # First poll and already > 1 — show current state
                    current = read_exterior_from_jsonl()
                    known_ubigeos.update(current.keys())
                    if current:
                        print(f"[{ts}] Ya reportando (desde JSONL):\n{format_reporting(current)}")

                prev_count = actas_cont

        except requests.RequestException as exc:
            print(f"[{ts}] Request error: {exc}")
        except Exception as exc:
            print(f"[{ts}] Unexpected error: {exc}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
