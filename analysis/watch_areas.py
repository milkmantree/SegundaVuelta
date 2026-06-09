#!/usr/bin/env python3
"""
Monitor specific provinces/countries for vote count updates every 30 seconds.
Polls the ONPE API directly (province-level) rather than the local aggregate file.
Alerts when actas_contabilizadas changes in any target area.
"""
import os, sys, json, time, datetime, subprocess, urllib.request

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FP, JPP = "8", "10"
INTERVAL = 30
ID_ELECCION = "10"

SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")

URL_TOTALES       = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales"
URL_PARTICIPANTES = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/eleccion-presidencial/participantes-ubicacion-geografica-nombre"

# (dept_label, prov_label, ambito, dept_code, prov_code)
TARGETS = [
    ("CUSCO",   "LA CONVENCIÓN",             "1", "070000", "070900"),
    ("LORETO",  "DATEM DEL MARAÑÓN",         "1", "150000", "150700"),
    ("EUROPA",  "ESPAÑA",                    "2", "940000", "940900"),
    ("AMÉRICA", "ESTADOS UNIDOS DE ÁMERICA", "2", "920000", "921300"),
]

# Used as keys in the snapshot dict — just the first two fields
TARGET_KEYS = [(dept, prov) for dept, prov, *_ in TARGETS]


def get_session():
    s = requests.Session()
    s.headers.update({
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
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


SESSION = get_session()


def fetch_province(ambito, dept_code, prov_code):
    """Returns (actas_done, actas_total, fp_votes, jpp_votes) for a province."""
    base_params = {
        "idEleccion": ID_ELECCION,
        "tipoFiltro": "ubigeo_nivel_02",
        "idAmbitoGeografico": ambito,
        "idUbigeoDepartamento": dept_code,
        "idUbigeoProvincia": prov_code,
    }

    # totales
    r_t = SESSION.get(URL_TOTALES, params=base_params, timeout=20)
    r_t.raise_for_status()
    t_data = r_t.json().get("data", {})
    if isinstance(t_data, list):
        t_data = t_data[0] if t_data else {}
    actas_done  = int(t_data.get("contabilizadas") or 0)
    actas_total = int(t_data.get("totalActas")     or 0)

    # participantes — uses ubigeoNivel* keys at this endpoint
    p_params = {
        "idEleccion": ID_ELECCION,
        "tipoFiltro": "ubigeo_nivel_02",
        "idAmbitoGeografico": ambito,
        "ubigeoNivel1": dept_code,
        "ubigeoNivel2": prov_code,
    }
    r_p = SESSION.get(URL_PARTICIPANTES, params=p_params, timeout=20)
    r_p.raise_for_status()
    candidates = r_p.json().get("data", []) or []
    votes = {str(c.get("codigoAgrupacionPolitica")): int(c.get("totalVotosValidos") or 0)
             for c in candidates}

    return actas_done, actas_total, votes.get(FP, 0), votes.get(JPP, 0)


def load_snapshot():
    snap = {}
    for dept, prov, ambito, dept_code, prov_code in TARGETS:
        key = (dept, prov)
        try:
            done, total, fp, jpp = fetch_province(ambito, dept_code, prov_code)
            pct = done / total * 100 if total else 0.0
            snap[key] = {"done": done, "total": total, "pct": pct, "fp": fp, "jpp": jpp}
        except Exception as e:
            print(f"  [warn] {label(dept, prov)}: API error — {e}")
            snap[key] = None   # caller must handle None (keep prev)
    return snap


def discord_notify(title, body):
    if not DISCORD_WEBHOOK:
        return
    payload = json.dumps({"content": f"**{title}**\n{body}"}).encode()
    req = urllib.request.Request(DISCORD_WEBHOOK, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (watch_areas, 1.0)",
    })
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        print(f"  [discord] HTTP {e.code}: {e.read().decode(errors='replace')}")
    except Exception as e:
        print(f"  [discord] failed: {e}")


def notify(title, body):
    subprocess.Popen(["notify-send", "-u", "critical", "-t", "10000", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def play_sound():
    subprocess.Popen(["paplay", SOUND],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def label(dept, prov):
    if prov == "LA CONVENCIÓN":              return "La Convención (Cusco)"
    if prov == "DATEM DEL MARAÑÓN":          return "Datem del Marañón (Loreto)"
    if prov == "ESPAÑA":                     return "España"
    if prov == "ESTADOS UNIDOS DE ÁMERICA":  return "EE.UU."
    return f"{prov} ({dept})"


def lima_now():
    return datetime.datetime.fromtimestamp(
        time.time() - 5 * 3600, datetime.UTC
    ).strftime("%d/%m %H:%M:%S")


def h2h_str(fp, jpp):
    fin = fp + jpp
    if fin == 0:
        return "  —"
    return f"FP {fp/fin*100:.1f}%"


def print_status(snap, changed_keys=None):
    print(f"\n[{lima_now()} Lima]")
    print(f"  {'Area':<28} {'Actas':>14}  {'Pct':>6}  {'FP':>8}  {'JPP':>8}  {'Net':>8}  {'H2H':>8}")
    print("  " + "─" * 90)
    for dept, prov, *_ in TARGETS:
        key = (dept, prov)
        s = snap.get(key)
        if s is None:
            print(f"  {label(dept, prov):<28}  — API error —")
            continue
        net = s["fp"] - s["jpp"]
        flag = " ◄ UPDATED" if changed_keys and key in changed_keys else ""
        print(
            f"  {label(dept,prov):<28} {s['done']:>6}/{s['total']:<6}  "
            f"{s['pct']:>5.1f}%  {s['fp']:>8,}  {s['jpp']:>8,}  {net:>+8,}  {h2h_str(s['fp'], s['jpp']):>8}{flag}"
        )
    print()


def main():
    print("Watching: La Convención · Datem del Marañón · España · EE.UU.")
    print(f"Polling ONPE API every {INTERVAL}s — Ctrl+C to stop\n")

    prev = load_snapshot()
    print_status(prev)

    while True:
        time.sleep(INTERVAL)
        curr = load_snapshot()

        changed = set()
        for key in TARGET_KEYS:
            c, p = curr.get(key), prev.get(key)
            if c is not None and p is not None and c["done"] != p["done"]:
                changed.add(key)

        if changed:
            lines = []
            for key in changed:
                dept, prov = key
                p, c = prev[key], curr[key]
                delta_actas = c["done"] - p["done"]
                delta_fp    = c["fp"]   - p["fp"]
                delta_jpp   = c["jpp"]  - p["jpp"]
                net = delta_fp - delta_jpp
                batch_fin = delta_fp + delta_jpp
                batch_h2h = f"FP {delta_fp/batch_fin*100:.1f}% of batch" if batch_fin > 0 else ""
                cumul_h2h = h2h_str(c["fp"], c["jpp"])
                msg = (f"{label(dept,prov)}: +{delta_actas} actas  "
                       f"FP {delta_fp:+,}  JPP {delta_jpp:+,}  net {net:+,}"
                       + (f"  [{batch_h2h} | cumul {cumul_h2h}]" if batch_h2h else f"  [cumul {cumul_h2h}]"))
                print(f"  *** CHANGE: {msg} ***")
                lines.append(msg)
            notify("ONPE Update", "\n".join(lines))
            discord_notify("ONPE Update", "\n".join(lines))
            play_sound()
            print_status(curr, changed)
            # only update prev for areas that successfully returned data
            for key in TARGET_KEYS:
                if curr.get(key) is not None:
                    prev[key] = curr[key]
        else:
            print(f"  [{lima_now()}] no change", flush=True)
            for key in TARGET_KEYS:
                if curr.get(key) is not None:
                    prev[key] = curr[key]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
