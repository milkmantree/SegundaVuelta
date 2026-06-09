#!/usr/bin/env python3
"""
Monitor specific provinces/countries for vote count updates every 30 seconds.
Alerts when actas_contabilizadas changes in any target area.
"""
import os, sys, json, time, datetime, subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import ROUND2

DISTRITAL = ROUND2 / "agg_distrital.json"
FP, JPP = "8", "10"
INTERVAL = 30

SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"

def notify(title, body):
    subprocess.Popen(["notify-send", "-u", "critical", "-t", "10000", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def play_sound():
    subprocess.Popen(["paplay", SOUND],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

TARGETS = [
    ("CUSCO",   "LA CONVENCIÓN"),
    ("LORETO",  "DATEM DEL MARAÑÓN"),
    ("EUROPA",  "ESPAÑA"),
    ("AMÉRICA", "ESTADOS UNIDOS DE ÁMERICA"),
]

def lima_now():
    return datetime.datetime.fromtimestamp(
        time.time() - 5 * 3600, datetime.UTC
    ).strftime("%d/%m %H:%M:%S")

def load_snapshot():
    data = json.loads(DISTRITAL.read_text(encoding="utf-8"))
    snap = {}
    for dept, prov in TARGETS:
        rows = [d for d in data if d["departamento"] == dept and d["provincia"] == prov]
        actas_done = sum(d["actas_contabilizadas"] for d in rows)
        actas_tot  = sum(d["actas_total"]          for d in rows)
        fp  = sum(d["votos_partidos"].get(FP,  0)  for d in rows)
        jpp = sum(d["votos_partidos"].get(JPP, 0)  for d in rows)
        pct = actas_done / actas_tot * 100 if actas_tot else 0.0
        snap[(dept, prov)] = {
            "done": actas_done, "total": actas_tot, "pct": pct,
            "fp": fp, "jpp": jpp,
        }
    return snap

def label(dept, prov):
    if prov == "LA CONVENCIÓN":       return "La Convención (Cusco)"
    if prov == "DATEM DEL MARAÑÓN":   return "Datem del Marañón (Loreto)"
    if prov == "ESPAÑA":              return "España"
    if prov == "ESTADOS UNIDOS DE ÁMERICA": return "EE.UU."
    return f"{prov} ({dept})"

def print_status(snap, changed_keys=None):
    print(f"\n[{lima_now()} Lima]")
    print(f"  {'Area':<28} {'Actas':>14}  {'Pct':>6}  {'FP':>8}  {'JPP':>8}  {'Net':>8}")
    print("  " + "─" * 80)
    for key in TARGETS:
        dept, prov = key
        s = snap[key]
        fin = s["fp"] + s["jpp"]
        h2h = f"{s['fp']/fin*100:.1f}%" if fin > 0 else "  —"
        net = s["fp"] - s["jpp"]
        flag = " ◄ UPDATED" if changed_keys and key in changed_keys else ""
        print(
            f"  {label(dept,prov):<28} {s['done']:>6}/{s['total']:<6}  "
            f"{s['pct']:>5.1f}%  {s['fp']:>8,}  {s['jpp']:>8,}  {net:>+8,}{flag}"
        )
    print()

def main():
    print("Watching: La Convención · Datem del Marañón · España · EE.UU.")
    print(f"Polling every {INTERVAL}s — Ctrl+C to stop\n")

    prev = load_snapshot()
    print_status(prev)

    while True:
        time.sleep(INTERVAL)
        curr = load_snapshot()
        changed = {k for k in TARGETS if curr[k]["done"] != prev[k]["done"]}

        if changed:
            lines = []
            for k in changed:
                dept, prov = k
                p, c = prev[k], curr[k]
                delta_actas = c["done"] - p["done"]
                delta_fp  = c["fp"]  - p["fp"]
                delta_jpp = c["jpp"] - p["jpp"]
                net = delta_fp - delta_jpp
                msg = (f"{label(dept,prov)}: +{delta_actas} actas  "
                       f"FP {delta_fp:+,}  JPP {delta_jpp:+,}  net {net:+,}")
                print(f"  *** CHANGE: {msg} ***")
                lines.append(msg)
            notify("ONPE Update", "\n".join(lines))
            play_sound()
            print_status(curr, changed)
            prev = curr
        else:
            print(f"  [{lima_now()}] no change", flush=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
