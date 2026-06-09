"""
acid_test.py

Acid test for remaining domestic votes across both projection models.

For districts with a strong JPP (Sánchez) lead in R1, replace the model's
estimate with a forced split and show the resulting domestic margin.

Usage:
    python acid_test.py                        # default threshold 60% JPP H2H
    python acid_test.py --threshold 70         # only districts >70% JPP H2H in R1
    python acid_test.py --threshold 50 60 70   # run multiple thresholds
"""

import argparse, json, sys, io, os
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import ROUND1, ROUND2

ROOT = Path(__file__).parent
JPP, FP = "10", "8"

SCENARIOS = [
    ("Baseline (modelos)",  None),
    ("100% Sánchez",        1.00),
    ("90/10 Sánchez",       0.90),
    ("80/20 Sánchez",       0.80),
]


def load_models():
    buf = io.StringIO()
    with redirect_stdout(buf):
        from models.propagation import get_projection_data_by_dept
        from models.migration import get_migration_data_by_dept
        prop = get_projection_data_by_dept()
        migr = get_migration_data_by_dept()
    return prop, migr


def model_h2h(depts, dept_name, finalist_id):
    d = depts.get(dept_name)
    if not d:
        return None
    parties = d.get("parties") or d.get("finalists") or []
    total = sum(p.get("projected_votes", 0) for p in parties)
    if not total:
        return None
    hit = next((p for p in parties if p["id"] == finalist_id), None)
    if not hit or not hit.get("projected_votes"):
        return None
    return hit["projected_votes"] / total


def build_remaining(r2_districts, r1_index, r2_r1_ratio, prop_depts, migr_depts):
    rows = []
    for d in r2_districts:
        pct = d.get("pct_actas_contabilizadas", 0)
        if pct >= 100:
            continue
        ubigeo = d["ubigeo"]
        r1 = r1_index.get(ubigeo)
        if not r1 or r1["votos_validos"] == 0:
            continue
        if str(r1.get("ambito", "1")) == "2":
            continue  # domestic only
        dept = r1["departamento"]
        vp = r1["votos_partidos"]
        jpp_r1 = int(vp.get(JPP, 0))
        fp_r1  = int(vp.get(FP,  0))
        fin_tot = jpp_r1 + fp_r1
        if fin_tot == 0:
            continue
        jpp_h2h_r1 = jpp_r1 / fin_tot
        est_valid = r1["votos_validos"] * r2_r1_ratio * (1 - pct / 100)
        if est_valid < 1:
            continue
        rows.append({
            "dept":        dept,
            "dist":        r1["distrito"],
            "pct":         pct,
            "jpp_h2h_r1":  jpp_h2h_r1,
            "est_valid":   est_valid,
            "prop_jpp":    model_h2h(prop_depts, dept, JPP),
            "migr_jpp":    model_h2h(migr_depts, dept, JPP),
        })
    return rows


def run_acid_test(remaining, threshold, obs_fp, obs_jpp):
    big  = [x for x in remaining if x["jpp_h2h_r1"] >= threshold]
    rest = [x for x in remaining if x["jpp_h2h_r1"] <  threshold]

    ev_big  = sum(x["est_valid"] for x in big)
    ev_rest = sum(x["est_valid"] for x in rest)
    ev_total = ev_big + ev_rest

    print(f"\n  ┌─ THRESHOLD: JPP R1 H2H > {threshold*100:.0f}% "
          f"─────────────────────────────────────────────┐")
    print(f"  │  Distritos 'big differential': {len(big):>4}  "
          f"({ev_big:>10,.0f} est. votos válidos restantes)")
    print(f"  │  Otros distritos restantes:    {len(rest):>4}  "
          f"({ev_rest:>10,.0f} est. votos válidos restantes)")
    print(f"  │  Total restante doméstico:      {len(remaining):>4}  "
          f"({ev_total:>10,.0f} est. votos válidos restantes)")
    print(f"  ├{'─'*72}┤")
    print(f"  │  {'Escenario':<24} {'Modelo':<14} {'FP':>12}  {'JPP':>12}  {'Margen':>10}  Ganador dom.")
    print(f"  ├{'─'*72}┤")

    for label, jpp_shock in SCENARIOS:
        for model_label, model_key in [("Propagación", "prop_jpp"), ("Migración", "migr_jpp")]:
            add_fp = add_jpp = 0.0
            for x in big:
                h2h_jpp = jpp_shock if jpp_shock is not None else x[model_key]
                if h2h_jpp is None:
                    continue
                add_jpp += x["est_valid"] * h2h_jpp
                add_fp  += x["est_valid"] * (1 - h2h_jpp)
            for x in rest:
                h2h_jpp = x[model_key]
                if h2h_jpp is None:
                    continue
                add_jpp += x["est_valid"] * h2h_jpp
                add_fp  += x["est_valid"] * (1 - h2h_jpp)

            proj_fp  = obs_fp  + add_fp
            proj_jpp = obs_jpp + add_jpp
            margin   = proj_fp - proj_jpp
            winner   = "FP" if margin > 0 else "JPP"
            sign     = "+" if margin >= 0 else ""
            print(f"  │  {label:<24} {model_label:<14} {proj_fp:>12,.0f}  {proj_jpp:>12,.0f}  "
                  f"{sign}{margin:>9,.0f}  {winner}")

        if label != SCENARIOS[-1][0]:
            print(f"  │  {'·'*70}")

    print(f"  └{'─'*72}┘")


def main():
    parser = argparse.ArgumentParser(
        description="Acid test for remaining domestic districts under extreme JPP scenarios."
    )
    parser.add_argument(
        "--threshold", type=float, nargs="+", default=[60.0],
        metavar="PCT",
        help="JPP R1 H2H threshold(s) defining 'big differential' districts (default: 60)"
    )
    args = parser.parse_args()
    thresholds = [t / 100 if t > 1 else t for t in args.threshold]

    print("\n  Cargando modelos...", flush=True)
    prop_dept, migr_dept = load_models()
    prop_depts = prop_dept.get("departments", {})
    migr_depts = migr_dept.get("departments", {}) if migr_dept.get("ok") else {}

    r2_districts = json.loads((ROUND2 / "agg_distrital.json").read_text())
    r1_index     = {d["ubigeo"]: d
                    for d in json.loads((ROUND1 / "agg_distrital.json").read_text())}
    agg_ambito   = json.loads((ROUND2 / "agg_ambito.json").read_text())

    # Domestic observed only (ambito 1)
    obs_fp  = sum(a["votos_partidos"].get(FP,  0) for a in agg_ambito if str(a.get("ambito", "1")) == "1")
    obs_jpp = sum(a["votos_partidos"].get(JPP, 0) for a in agg_ambito if str(a.get("ambito", "1")) == "1")

    # R2/R1 ratio from reported domestic districts
    r2_valid_dom = sum(a["votos_validos"] for a in agg_ambito if str(a.get("ambito", "1")) == "1")
    rep_r1_valid = sum(
        r1_index[d["ubigeo"]]["votos_validos"]
        for d in r2_districts
        if d.get("pct_actas_contabilizadas", 0) > 0
        and d["ubigeo"] in r1_index
        and r1_index[d["ubigeo"]]["votos_validos"] > 0
        and str(r1_index[d["ubigeo"]].get("ambito", "1")) != "2"
    )
    r2_r1_ratio = r2_valid_dom / rep_r1_valid if rep_r1_valid else 1.0

    remaining = build_remaining(r2_districts, r1_index, r2_r1_ratio, prop_depts, migr_depts)

    W = 76
    print()
    print("  " + "═" * W)
    print("   ACID TEST — VOTO DOMÉSTICO RESTANTE")
    print("  " + "═" * W)
    print(f"\n  Observado doméstico actual:")
    print(f"    FP  (Fujimori):  {obs_fp:>12,}")
    print(f"    JPP (Sánchez):   {obs_jpp:>12,}   margen {obs_fp - obs_jpp:+,}")
    print(f"  R2/R1 ratio: {r2_r1_ratio:.4f}  |  Distritos domésticos restantes: {len(remaining)}")
    print(f"\n  Escenarios para distritos 'big differential':")
    print(f"    Baseline   — estimación del modelo sin modificar")
    print(f"    100%       — todos los votos al JPP")
    print(f"    90/10      — 90% JPP / 10% FP")
    print(f"    80/20      — 80% JPP / 20% FP")
    print(f"  Distritos restantes (no big-diff): estimación del modelo sin modificar")

    for t in thresholds:
        run_acid_test(remaining, t, obs_fp, obs_jpp)

    print()
    print("  " + "═" * W)
    print()


if __name__ == "__main__":
    main()
