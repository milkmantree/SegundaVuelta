"""
exterior_comparison.py

Side-by-side comparison of segunda vuelta exterior results:
  2021 (Castillo vs Keiko)  vs  2026 (JPP/Sánchez vs FP/Fujimori)

Both elections are runoffs where one candidate is Keiko Fujimori (FP) and the
other is the left challenger.  The 2021 CSV stores head-to-head shares as
percentages.  The 2026 data comes from processed_results/agg_distrital.json.

Output
------
  - Per-district side-by-side table (reported districts only)
  - Region-level summary
  - Top movers table (largest absolute swing in FP h2h share)

Usage
-----
    python exterior_comparison.py
    python exterior_comparison.py --top 20        # show top-20 movers (default 15)
    python exterior_comparison.py --min-votes 50  # hide tiny districts (default 10)
    python exterior_comparison.py --unmatched      # show districts that couldn't be matched
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import EXTERIOR_2021_CSV, ROUND2

ROOT = Path(__file__).parent

CSV_2021   = EXTERIOR_2021_CSV
DISTRITAL  = ROUND2 / "agg_distrital.json"

FP_ID  = "8"
JPP_ID = "10"


# ── Name normalisation ────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    """Lowercase, strip accents, collapse spaces, remove parentheticals."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s*\(.*?\)", "", s)   # remove (CUENCA), (CHARLOTTE), etc.
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


# ── Load 2021 CSV ─────────────────────────────────────────────────────────────

def load_2021() -> dict[str, dict]:
    """
    Returns dict: norm_name → {raw_name, castillo_pct, keiko_pct}
    Keiko's share is the FP share in 2021.
    """
    data: dict[str, dict] = {}
    with open(CSV_2021, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        name_col = [k for k in reader.fieldnames if k not in ("Castillo", "Keiko")][0]
        for row in reader:
            raw  = row[name_col].strip()
            norm = _norm(raw)
            if not norm:
                continue
            def _pct(v):
                try:
                    return float(v.strip().rstrip("%"))
                except (ValueError, AttributeError):
                    return None
            cas = _pct(row.get("Castillo", ""))
            kei = _pct(row.get("Keiko", ""))
            data[norm] = {"raw": raw, "castillo_pct": cas, "keiko_pct": kei}
    return data


# ── Load 2026 R2 exterior districts ───────────────────────────────────────────

def load_2026() -> dict[str, dict]:
    """
    Returns dict: norm_name → {raw_name, dept, fp_pct, jpp_pct, fp_votes,
                                jpp_votes, valid, pct_actas, reported}
    Only includes ambito==2 (exterior) districts.
    """
    with open(DISTRITAL, encoding="utf-8") as f:
        rows = json.load(f)

    data: dict[str, dict] = {}
    for r in rows:
        if str(r.get("ambito", "1")) != "2":
            continue
        raw  = r.get("distrito", "").strip()
        norm = _norm(raw)
        if not norm:
            continue
        vp   = r.get("votos_partidos", {})
        fp   = int(vp.get(FP_ID,  0))
        jpp  = int(vp.get(JPP_ID, 0))
        tot  = fp + jpp
        pct  = r.get("pct_actas_contabilizadas", 0) or 0
        data[norm] = {
            "raw":       raw,
            "dept":      r.get("departamento", ""),
            "fp_votes":  fp,
            "jpp_votes": jpp,
            "valid":     r.get("votos_validos", 0) or 0,
            "fp_pct":    fp / tot * 100 if tot else None,
            "jpp_pct":   jpp / tot * 100 if tot else None,
            "pct_actas": float(pct),
            "reported":  float(pct) > 0 and tot > 0,
        }
    return data


# ── Match ─────────────────────────────────────────────────────────────────────

def match(csv21: dict, r26: dict) -> tuple[list[dict], list[str], list[str]]:
    """
    Join on normalised name.  Returns (matched_rows, unmatched_csv, unmatched_r2).
    matched_rows includes ALL matched pairs (reported flag on r26 side).
    """
    matched, only_csv, only_r2 = [], [], []
    used_r2: set[str] = set()

    for norm, c21 in csv21.items():
        if norm in r26:
            r2 = r26[norm]
            matched.append({
                "norm":         norm,
                "raw_csv":      c21["raw"],
                "raw_r2":       r2["raw"],
                "dept":         r2["dept"],
                "keiko21":      c21["keiko_pct"],
                "castillo21":   c21["castillo_pct"],
                "fp26":         r2["fp_pct"],
                "jpp26":        r2["jpp_pct"],
                "fp_votes26":   r2["fp_votes"],
                "jpp_votes26":  r2["jpp_votes"],
                "valid26":      r2["valid"],
                "pct_actas":    r2["pct_actas"],
                "reported":     r2["reported"],
            })
            used_r2.add(norm)
        else:
            only_csv.append(c21["raw"])

    for norm, r2 in r26.items():
        if norm not in used_r2:
            only_r2.append(r2["raw"])

    return matched, only_csv, only_r2


# ── Formatting helpers ────────────────────────────────────────────────────────

def _pct_str(v) -> str:
    if v is None:
        return "   —  "
    return f"{v:>5.1f}%"

def _diff_str(fp26, keiko21) -> str:
    if fp26 is None or keiko21 is None:
        return "     —"
    d = fp26 - keiko21
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:>5.1f}pp"

def _swing_label(fp26, keiko21) -> str:
    if fp26 is None or keiko21 is None:
        return ""
    d = fp26 - keiko21
    if abs(d) < 2:
        return ""
    return "▲FP" if d > 0 else "▼FP"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top",        type=int, default=15, help="N largest movers to show")
    parser.add_argument("--min-votes",  type=int, default=10, help="Min 2026 votes to include in tables")
    parser.add_argument("--unmatched",  action="store_true",   help="Print unmatched district names")
    args = parser.parse_args()

    csv21 = load_2021()
    r26   = load_2026()
    matched, only_csv, only_r2 = match(csv21, r26)

    # Only districts with actual 2026 data for the comparison tables
    reported   = [m for m in matched if m["reported"] and (m["fp_votes26"] + m["jpp_votes26"]) >= args.min_votes]
    unreported = [m for m in matched if not m["reported"]]

    W = 100
    print()
    print("  " + "═" * W)
    print("   COMPARACIÓN VOTO EXTERIOR: 2021 vs 2026  (Segunda Vuelta)")
    print("  " + "═" * W)
    print(f"  Distritos en CSV 2021       : {len(csv21)}")
    print(f"  Distritos ext. 2026         : {len(r26)}")
    print(f"  Emparejados                 : {len(matched)}")
    print(f"  Con datos 2026 (≥{args.min_votes} votos): {len(reported)}")
    print(f"  Sin datos 2026 aún          : {len(unreported)}")

    # ── Tendency analysis ─────────────────────────────────────────────────────
    swingable = [m for m in reported if m["fp26"] is not None and m["keiko21"] is not None]
    deltas     = [m["fp26"] - m["keiko21"] for m in swingable]
    votes      = [m["fp_votes26"] + m["jpp_votes26"] for m in swingable]
    total_v    = sum(votes)

    n_up   = sum(1 for d in deltas if d >  1.0)
    n_down = sum(1 for d in deltas if d < -1.0)
    n_flat = len(deltas) - n_up - n_down

    mean_d    = sum(deltas) / len(deltas) if deltas else 0
    w_mean_d  = sum(d * v for d, v in zip(deltas, votes)) / total_v if total_v else 0
    sorted_d  = sorted(deltas)
    median_d  = sorted_d[len(sorted_d) // 2] if sorted_d else 0

    # vote-weighted FP totals
    fp_tot26  = sum(m["fp_votes26"]  for m in swingable)
    jpp_tot26 = sum(m["jpp_votes26"] for m in swingable)
    grand26   = fp_tot26 + jpp_tot26
    fp_obs_pct  = fp_tot26  / grand26 * 100 if grand26 else 0
    jpp_obs_pct = jpp_tot26 / grand26 * 100 if grand26 else 0

    # 2021 weighted baseline (weighted by 2026 vote counts for apples-to-apples)
    w_kei21 = sum(m["keiko21"] * v for m, v in zip(swingable, votes)) / total_v if total_v else 0

    # swing distribution buckets
    buckets = [
        ("< −10pp",    sum(1 for d in deltas if d < -10)),
        ("−10 a −5pp", sum(1 for d in deltas if -10 <= d < -5)),
        ("−5 a −2pp",  sum(1 for d in deltas if -5  <= d < -2)),
        ("±2pp",       sum(1 for d in deltas if -2  <= d <=  2)),
        ("+2 a +5pp",  sum(1 for d in deltas if  2  <  d <=  5)),
        ("+5 a +10pp", sum(1 for d in deltas if  5  <  d <= 10)),
        ("> +10pp",    sum(1 for d in deltas if  d  > 10)),
    ]
    bar_scale = 30 / max(n for _, n in buckets) if any(n for _, n in buckets) else 1

    # Pearson correlation between keiko21 and fp26 (do strongholds hold?)
    import statistics
    if len(swingable) >= 3:
        xs = [m["keiko21"] for m in swingable]
        ys = [m["fp26"]    for m in swingable]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num  = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        denom = (sum((x - mx)**2 for x in xs) * sum((y - my)**2 for y in ys)) ** 0.5
        corr = num / denom if denom else 0
    else:
        corr = float("nan")

    def _pp(v): return ("+" if v >= 0 else "") + f"{v:.1f}"

    print()
    print(f"  ┌─ TENDENCIA GENERAL ({'─'*77}┐")
    print(f"  │")
    print(f"  │  Resultados observados (distritos con datos 2026, ≥{args.min_votes} votos):")
    print(f"  │")
    print(f"  │  {'FP  2026':>20} : {fp_obs_pct:>5.1f}%   ({fp_tot26:,} votos)")
    print(f"  │  {'JPP 2026':>20} : {jpp_obs_pct:>5.1f}%   ({jpp_tot26:,} votos)")
    print(f"  │  {'Keiko 2021 (pond.)':>20} : {w_kei21:>5.1f}%   (base de comparación, ponderada por votos 2026)")
    print(f"  │  {'Δ FP ponderado':>20} : {_pp(fp_obs_pct - w_kei21):>6}pp")
    print(f"  │")
    print(f"  │  Distritos FP mejor    : {n_up:>3}  ({n_up/len(deltas)*100:.0f}%)")
    print(f"  │  Distritos estables    : {n_flat:>3}  ({n_flat/len(deltas)*100:.0f}%  cambio ≤ ±1pp)")
    print(f"  │  Distritos FP peor     : {n_down:>3}  ({n_down/len(deltas)*100:.0f}%)")
    print(f"  │")
    print(f"  │  Swing medio (no pond.): {_pp(mean_d):>6}pp    Mediana: {_pp(median_d):>6}pp")
    print(f"  │  Swing ponderado votos : {_pp(w_mean_d):>6}pp    (correlación Keiko21↔FP26: r={corr:.2f})")
    print(f"  │")
    print(f"  │  Distribución de cambios:")
    for label, n in buckets:
        bar = "█" * round(n * bar_scale)
        print(f"  │    {label:>12}  {bar:<32} {n:>3}")
    print(f"  │")

    tendency = "NEUTRAL" if abs(w_mean_d) < 1 else ("FP GANA TERRENO" if w_mean_d > 0 else "FP PIERDE TERRENO")
    caveat   = ""
    if len(swingable) < 30:
        caveat = f"  ⚠ Solo {len(swingable)} distritos — muestra parcial, interpretar con cautela."
    print(f"  │  Tendencia: {tendency}  (swing pond. {_pp(w_mean_d)}pp vs 2021)")
    if caveat:
        print(f"  │  {caveat}")
    print(f"  └{'─'*99}┘")

    # ── Per-district table ────────────────────────────────────────────────────
    dept_order = ["AMÉRICA", "EUROPA", "ASIA", "OCEANÍA", "ÁFRICA"]
    def _dept_sort(m):
        dept = m["dept"]
        try:
            return (dept_order.index(dept), m["raw_r2"])
        except ValueError:
            return (99, m["raw_r2"])

    reported_sorted = sorted(reported, key=_dept_sort)

    col_d  = 26   # district name
    col_c  = 8    # candidate share cols
    print()
    print(f"  ┌─ RESULTADOS POR DISTRITO (con datos 2026) {'─'*(W-45)}┐")
    hdr = (
        f"  │  {'Distrito':<{col_d}}  {'Región':^10}  "
        f"{'──── 2021 ────':^19}  {'──── 2026 ────':^19}  "
        f"{'Δ FP':>8}  {'Actas':>6}"
    )
    print(hdr)
    print(f"  │  {'':^{col_d}}  {'':^10}  "
          f"{'Castillo':^{col_c}}  {'Keiko':^{col_c}}  "
          f"{'JPP':^{col_c}}  {'FP':^{col_c}}  "
          f"{'':>8}  {'':>6}")
    print(f"  ├{'─'*(W-2)}┤")

    current_dept = None
    for m in reported_sorted:
        if m["dept"] != current_dept:
            if current_dept is not None:
                print(f"  │  {'·'*(W-4)}")
            current_dept = m["dept"]
            print(f"  │  ── {m['dept']} ──")

        swing = _swing_label(m["fp26"], m["keiko21"])
        diff  = _diff_str(m["fp26"], m["keiko21"])
        name  = m["raw_r2"][:col_d]

        print(
            f"  │  {name:<{col_d}}  {m['dept']:^10}  "
            f"{_pct_str(m['castillo21']):^{col_c}}  {_pct_str(m['keiko21']):^{col_c}}  "
            f"{_pct_str(m['jpp26']):^{col_c}}  {_pct_str(m['fp26']):^{col_c}}  "
            f"{diff:>8}  {m['pct_actas']:>5.0f}%  {swing}"
        )

    print(f"  └{'─'*(W-2)}┘")

    # ── Region summary ────────────────────────────────────────────────────────
    print()
    print(f"  ┌─ RESUMEN POR REGIÓN {'─'*(W-22)}┐")
    print(f"  │  {'Región':<12}  {'Dist.rep/tot':>13}  "
          f"{'Castillo21':>11}  {'Keiko21':>8}  "
          f"{'JPP26':>6}  {'FP26':>6}  {'Δ FP':>8}  {'Votos26':>9}")
    print(f"  ├{'─'*(W-2)}┤")

    for dept in dept_order:
        rows_d = [m for m in reported if m["dept"] == dept]
        all_d  = [m for m in matched  if m["dept"] == dept]
        if not all_d:
            continue

        fp26_v   = sum(m["fp_votes26"]  for m in rows_d)
        jpp26_v  = sum(m["jpp_votes26"] for m in rows_d)
        tot26    = fp26_v + jpp26_v

        # Weighted 2021 shares using 2026 reported-district vote counts as weight
        # (best proxy we have for relative district size)
        w_kei = w_cas = w_sum = 0.0
        for m in rows_d:
            w = m["fp_votes26"] + m["jpp_votes26"]
            if m["keiko21"] is not None:
                w_kei += m["keiko21"] * w
                w_cas += (m["castillo21"] or 0) * w
                w_sum += w

        fp26_pct  = fp26_v  / tot26 * 100 if tot26 else None
        jpp26_pct = jpp26_v / tot26 * 100 if tot26 else None
        kei21_w   = w_kei / w_sum if w_sum else None
        cas21_w   = w_cas / w_sum if w_sum else None
        diff      = _diff_str(fp26_pct, kei21_w)

        n_rep = len(rows_d)
        n_tot = len(all_d)

        print(
            f"  │  {dept:<12}  {n_rep:>5}/{n_tot:<6}   "
            f"{_pct_str(cas21_w):>11}  {_pct_str(kei21_w):>8}  "
            f"{_pct_str(jpp26_pct):>6}  {_pct_str(fp26_pct):>6}  "
            f"{diff:>8}  {tot26:>9,}"
        )

    # All-exterior aggregate
    fp_tot   = sum(m["fp_votes26"]  for m in reported)
    jpp_tot  = sum(m["jpp_votes26"] for m in reported)
    grand    = fp_tot + jpp_tot
    fp_agg   = fp_tot  / grand * 100 if grand else None
    jpp_agg  = jpp_tot / grand * 100 if grand else None
    w_kei = w_sum = 0.0
    for m in reported:
        w = m["fp_votes26"] + m["jpp_votes26"]
        if m["keiko21"] is not None:
            w_kei += m["keiko21"] * w
            w_sum += w
    kei_agg = w_kei / w_sum if w_sum else None

    print(f"  ├{'─'*(W-2)}┤")
    print(
        f"  │  {'TOTAL EXT':<12}  {len(reported):>5}/{len(matched):<6}   "
        f"{'':>11}  {_pct_str(kei_agg):>8}  "
        f"{_pct_str(jpp_agg):>6}  {_pct_str(fp_agg):>6}  "
        f"{_diff_str(fp_agg, kei_agg):>8}  {grand:>9,}"
    )
    print(f"  └{'─'*(W-2)}┘")
    print(f"  Nota: Keiko21/Castillo21 son ponderados por votos 2026 de los distritos reportados.")

    # ── Top movers ────────────────────────────────────────────────────────────
    swings = [
        m for m in reported
        if m["fp26"] is not None and m["keiko21"] is not None
    ]
    swings.sort(key=lambda m: abs(m["fp26"] - m["keiko21"]), reverse=True)

    print()
    print(f"  ┌─ TOP {args.top} MAYORES CAMBIOS (|Δ FP h2h| vs 2021) {'─'*(W-50)}┐")
    print(f"  │  {'Distrito':<{col_d}}  {'Región':^12}  "
          f"{'Keiko21':>8}  {'FP26':>6}  {'Δ FP':>8}  {'Votos26':>9}  {'Actas':>6}")
    print(f"  ├{'─'*(W-2)}┤")

    for m in swings[: args.top]:
        d    = m["fp26"] - m["keiko21"]
        sign = "+" if d >= 0 else ""
        flag = "▲▲" if d > 10 else ("▲" if d > 0 else ("▼▼" if d < -10 else "▼"))
        name = m["raw_r2"][:col_d]
        print(
            f"  │  {name:<{col_d}}  {m['dept']:^12}  "
            f"{_pct_str(m['keiko21']):>8}  {_pct_str(m['fp26']):>6}  "
            f"{sign}{d:>5.1f}pp  {m['fp_votes26']+m['jpp_votes26']:>9,}  "
            f"{m['pct_actas']:>5.0f}%  {flag}"
        )

    print(f"  └{'─'*(W-2)}┘")
    print(f"  ▲▲/▲ = FP stronger in 2026   ▼▼/▼ = FP weaker in 2026")
    print(f"  Δ FP = FP 2026 h2h% − Keiko 2021 h2h%  (positive = FP improved)")

    # ── Missing district bias ─────────────────────────────────────────────────
    # Unreported = matched districts with no 2026 data yet.
    # We know their 2021 Keiko share; compare against the reported average
    # to see if the pending districts lean FP or JPP in 2021.
    missing_with_data = [m for m in unreported if m["keiko21"] is not None]

    if missing_with_data:
        mk_missing = [m["keiko21"] for m in missing_with_data]
        mk_reported = [m["keiko21"] for m in swingable]

        mean_missing  = sum(mk_missing)  / len(mk_missing)
        mean_reported = sum(mk_reported) / len(mk_reported)
        diff_miss     = mean_missing - mean_reported

        # Group missing districts by region
        missing_by_dept: dict[str, list] = {}
        for m in missing_with_data:
            missing_by_dept.setdefault(m["dept"], []).append(m)

        print()
        print(f"  ┌─ SESGO DE DISTRITOS PENDIENTES ({'─'*66}┐")
        print(f"  │")
        print(f"  │  {len(missing_with_data)} distritos emparejados aún sin datos 2026.")
        print(f"  │")
        print(f"  │  Keiko 2021 promedio en distritos YA reportados : {mean_reported:>5.1f}%")
        print(f"  │  Keiko 2021 promedio en distritos AÚN PENDIENTES: {mean_missing:>5.1f}%")
        print(f"  │  Diferencia                                      : {_pp(diff_miss):>6}pp")
        if diff_miss > 2:
            bias_label = f"▲ Los distritos pendientes fueron más FP en 2021 (+{diff_miss:.1f}pp de ventaja Keiko)"
        elif diff_miss < -2:
            bias_label = f"▼ Los distritos pendientes fueron más JPP en 2021 ({diff_miss:.1f}pp menos Keiko)"
        else:
            bias_label = "≈ Los distritos pendientes son representativos de los ya reportados"
        print(f"  │  → {bias_label}")
        print(f"  │")
        print(f"  │  Por región (pendientes):")
        print(f"  │  {'Región':<12}  {'N pend':>7}  {'Keiko21 prom':>13}  {'vs reportados':>14}  Distritos destacados")
        print(f"  ├{'─'*99}┤")

        for dept in sorted(missing_by_dept.keys()):
            rows_m = missing_by_dept.get(dept, [])
            rows_r = [m for m in swingable if m["dept"] == dept]
            if not rows_m:
                continue
            avg_m = sum(m["keiko21"] for m in rows_m) / len(rows_m)
            avg_r = sum(m["keiko21"] for m in rows_r) / len(rows_r) if rows_r else None
            d_str = f"{_pp(avg_m - avg_r)}pp" if avg_r is not None else "  n/a "
            # top 3 most FP-leaning pending districts in this region
            top3 = sorted(rows_m, key=lambda m: m["keiko21"], reverse=True)[:3]
            top3_str = ", ".join(f"{m['raw_csv']} ({m['keiko21']:.0f}%K)" for m in top3)
            print(f"  │  {dept:<12}  {len(rows_m):>7}  {avg_m:>12.1f}%  {d_str:>14}  {top3_str}")

        # Flag whether pending bias reinforces or offsets observed tendency
        print(f"  │")
        if diff_miss > 2 and w_mean_d < 0:
            note = "El exterior pendiente es más FP que los reportados → si mantiene la tendencia de -1.5pp,  el resultado final será más FP que el observado hasta ahora."
        elif diff_miss < -2 and w_mean_d < 0:
            note = "El exterior pendiente es más JPP que los reportados → la tendencia de pérdida de FP puede acentuarse al llegar esos datos."
        elif diff_miss > 2 and w_mean_d > 0:
            note = "El exterior pendiente es más FP que los reportados → la ganancia de FP observada puede mantenerse o aumentar."
        else:
            note = "No hay un sesgo claro en los pendientes respecto a los reportados."
        # wrap at 90 chars
        words = note.split()
        line, lines = [], []
        for w in words:
            if sum(len(x)+1 for x in line) + len(w) > 90:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        for l in lines:
            print(f"  │  {l}")
        print(f"  └{'─'*99}┘")

    # ── Unmatched ─────────────────────────────────────────────────────────────
    if args.unmatched:
        print()
        print(f"  ┌─ NO EMPAREJADOS ────────────────────────────────────────────────────────┐")
        print(f"  │  Solo en CSV 2021 ({len(only_csv)}):")
        for name in sorted(only_csv):
            print(f"  │    {name}")
        print(f"  │  Solo en R2 2026 ({len(only_r2)}):")
        for name in sorted(only_r2):
            print(f"  │    {name}")
        print(f"  └{'─'*(W-2)}┘")

    print()
    print("  " + "═" * W)
    print()


if __name__ == "__main__":
    main()
