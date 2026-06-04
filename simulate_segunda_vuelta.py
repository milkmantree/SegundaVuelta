"""
simulate_segunda_vuelta.py
==========================
Generates synthetic segunda vuelta data in processed_results/ for end-to-end
testing of the vote migration model and dashboard.

Usage:
    python simulate_segunda_vuelta.py          # write simulated data
    python simulate_segunda_vuelta.py --restore # restore original files from backup
    python simulate_segunda_vuelta.py --check   # show current state

Simulation design:
  - Only parties 8 (FUERZA POPULAR) and 10 (JUNTOS POR EL PERÚ) appear in R2
  - Migration rates per R1 party encode realistic political-affinity assumptions
  - Turnout declines ~7% from R1
  - ~62% of districts have partial or full results (rest unreported)
  - Geographic variation: northern regions lean more toward party 10,
    southern/urban regions slightly more toward party 8
  - National simulated outcome: ~50.8% party 10 vs ~49.2% party 8 (close race)
"""

import json
import math
import os
import shutil

import numpy as np
import pandas as pd

SEED = 42
rng  = np.random.default_rng(SEED)

OUT_DIR    = "processed_results"
BACKUP_DIR = "processed_results_backup_r1"

# ── Migration rates: fraction of each R1 party's votes that go to R2 finalist ─
# Each entry: (to_F1=party8, to_F2=party10, to_blank, to_null)
# Remaining fraction represents abstention (voter drops out entirely)
# These simulate a plausible ideological-affinity structure.
MIGRATION = {
    "8":  (0.910, 0.030, 0.030, 0.020, 0.010),  # F1 base: high retention
    "10": (0.025, 0.910, 0.030, 0.020, 0.015),  # F2 base: high retention
    "35": (0.620, 0.140, 0.110, 0.060, 0.070),  # Renovación Popular → mostly F1
    "16": (0.320, 0.430, 0.130, 0.060, 0.060),  # Buen Gobierno → slightly F2
    "14": (0.380, 0.380, 0.120, 0.060, 0.060),  # Cívico Obras → split
    "1":  (0.270, 0.490, 0.130, 0.060, 0.050),  # Alianza → slightly F2
    "27": (0.090, 0.680, 0.120, 0.060, 0.050),  # Perú Libre → strongly F2
    "20": (0.300, 0.400, 0.150, 0.080, 0.070),  # Somos Perú → slightly F2
    "23": (0.430, 0.330, 0.130, 0.060, 0.050),  # País Para Todos → slightly F1
    "33": (0.310, 0.390, 0.150, 0.080, 0.070),  # Primero la Gente → slightly F2
    "32": (0.410, 0.340, 0.130, 0.060, 0.060),  # Podemos Perú → slightly F1
    "12": (0.250, 0.480, 0.140, 0.070, 0.060),  # APRA → slightly F2
    "22": (0.450, 0.300, 0.140, 0.060, 0.050),  # Partido Morado → slightly F1
    "7":  (0.480, 0.280, 0.130, 0.060, 0.050),  # Avanza País → F1
    "2":  (0.350, 0.360, 0.140, 0.080, 0.070),  # Ahora Nación → split
    "24": (0.360, 0.360, 0.140, 0.080, 0.060),  # Patriótico → split
    "80": (0.200, 0.170, 0.500, 0.050, 0.080),  # R1 blancos → mostly stay blank
    "81": (0.080, 0.080, 0.060, 0.720, 0.060),  # R1 nulos → mostly stay null
}
# Default for any party not listed above
MIGRATION_DEFAULT = (0.330, 0.340, 0.140, 0.080, 0.110)

# tuple positions: (f1_rate, f2_rate, blank_rate, null_rate, abstain_rate)
F1, F2, BL, NU, AB = 0, 1, 2, 3, 4

# Geographic lean: departments that lean slightly toward F2 (left / rural north)
F2_LEAN_DEPTS = {
    "AMAZONAS", "SAN MARTIN", "LORETO", "UCAYALI", "MADRE DE DIOS",
    "HUÁNUCO", "PASCO", "JUNIN", "APURÍMAC", "AYACUCHO", "HUANCAVELICA",
}
F1_LEAN_DEPTS = {
    "LIMA", "AREQUIPA", "ICA", "TACNA", "MOQUEGUA",
    "LA LIBERTAD", "LAMBAYEQUE", "PIURA",
}
GEO_LEAN_F2 =  0.025   # additive shift on F2 migration rates in F2-lean depts
GEO_LEAN_F1 = -0.015   # same for F1-lean depts


def _migration_rates(party_id, dept):
    base = MIGRATION.get(party_id, MIGRATION_DEFAULT)
    f1, f2, bl, nu, ab = base

    if dept in F2_LEAN_DEPTS:
        f2 = min(f2 + GEO_LEAN_F2, 0.99)
        f1 = max(f1 - GEO_LEAN_F2 * 0.7, 0.0)
    elif dept in F1_LEAN_DEPTS:
        f1 = min(f1 + abs(GEO_LEAN_F1) * 0.7, 0.99)
        f2 = max(f2 + GEO_LEAN_F1, 0.0)

    # Re-normalise to sum = 1
    total = f1 + f2 + bl + nu + ab
    return f1/total, f2/total, bl/total, nu/total, ab/total


def _simulate_district(r1_row, all_party_cols, reported: bool, partial_frac: float):
    """
    Produce a simulated R2 district record from a R1 row.

    reported:     whether this district has any actas counted
    partial_frac: fraction of actas counted (1.0 = fully counted)
    """
    dept = r1_row["departamento"]

    # Turnout: R2 participation rate is slightly lower than R1
    r1_part_rate = r1_row["pct_participacion"] / 100.0
    r2_part_rate = r1_part_rate * rng.uniform(0.90, 0.97)  # 90-97% of R1 turnout
    r2_part_rate = min(r2_part_rate, 0.99)

    votos_habiles = float(r1_row["votos_habiles"])
    r2_emitidos   = int(votos_habiles * r2_part_rate)

    # Apply migration from each R1 party
    sim_f1    = 0.0
    sim_f2    = 0.0
    sim_blank = 0.0
    sim_null  = 0.0

    r1_votes_dict = r1_row.get("votos_partidos", {})
    for col in all_party_cols:
        r1_votes = float(r1_votes_dict.get(col, 0))
        if r1_votes <= 0:
            continue
        mf1, mf2, mbl, mnu, _ = _migration_rates(col, dept)

        # Add district-level noise (multiplicative, log-normal with σ≈0.08)
        noise_f1 = rng.lognormal(0, 0.08)
        noise_f2 = rng.lognormal(0, 0.08)

        sim_f1    += r1_votes * mf1 * noise_f1
        sim_f2    += r1_votes * mf2 * noise_f2
        sim_blank += r1_votes * mbl
        sim_null  += r1_votes * mnu

    # Round to integers
    sim_f1    = max(0, int(round(sim_f1)))
    sim_f2    = max(0, int(round(sim_f2)))
    sim_blank = max(0, int(round(sim_blank)))
    sim_null  = max(0, int(round(sim_null)))

    total_valid    = sim_f1 + sim_f2 + sim_blank + sim_null
    total_emitidos = max(r2_emitidos, total_valid)

    actas_total = int(r1_row["actas_total"])

    if not reported:
        return {
            "ubigeo":                    r1_row["ubigeo"],
            "ambito":                    r1_row["ambito"],
            "departamento":              dept,
            "provincia":                 r1_row["provincia"],
            "distrito":                  r1_row["distrito"],
            "actas_total":               actas_total,
            "actas_contabilizadas":      0,
            "pct_actas_contabilizadas":  0.0,
            "pct_participacion":         0.0,
            "votos_emitidos":            0,
            "votos_validos":             0,
            "votos_habiles":             int(votos_habiles),
            "votos_partidos":            {"8": 0, "10": 0, "80": 0, "81": 0},
        }

    # Partial reporting: scale down counts proportionally
    actas_counted = max(1, int(round(actas_total * partial_frac)))
    scale         = actas_counted / actas_total

    sf1    = max(0, int(round(sim_f1    * scale)))
    sf2    = max(0, int(round(sim_f2    * scale)))
    sblank = max(0, int(round(sim_blank * scale)))
    snull  = max(0, int(round(sim_null  * scale)))

    valid_counted    = sf1 + sf2 + sblank + snull
    emitidos_counted = max(int(round(total_emitidos * scale)), valid_counted)
    pct_actas        = round(actas_counted / actas_total * 100, 3)
    pct_part         = round(emitidos_counted / votos_habiles * 100, 3) if votos_habiles > 0 else 0.0

    return {
        "ubigeo":                    r1_row["ubigeo"],
        "ambito":                    r1_row["ambito"],
        "departamento":              dept,
        "provincia":                 r1_row["provincia"],
        "distrito":                  r1_row["distrito"],
        "actas_total":               actas_total,
        "actas_contabilizadas":      actas_counted,
        "pct_actas_contabilizadas":  pct_actas,
        "pct_participacion":         pct_part,
        "votos_emitidos":            emitidos_counted,
        "votos_validos":             valid_counted,
        "votos_habiles":             int(votos_habiles),
        "votos_partidos":            {"8": sf1, "10": sf2, "80": sblank, "81": snull},
    }


def _aggregate(records, group_keys):
    """Aggregate a list of district dicts into a higher-level summary."""
    from collections import defaultdict

    groups = defaultdict(list)
    for r in records:
        key = tuple(r[k] for k in group_keys)
        groups[key].append(r)

    out = []
    for key, recs in sorted(groups.items()):
        agg_actas_total  = sum(r["actas_total"] for r in recs)
        agg_actas_cnt    = sum(r["actas_contabilizadas"] for r in recs)
        agg_emitidos     = sum(r["votos_emitidos"] for r in recs)
        agg_validos      = sum(r["votos_validos"] for r in recs)
        agg_habiles      = sum(r["votos_habiles"] for r in recs)

        pct_actas = round(agg_actas_cnt / agg_actas_total * 100, 3) if agg_actas_total > 0 else 0.0
        pct_part  = round(agg_emitidos / agg_habiles * 100, 3) if agg_habiles > 0 else 0.0

        party_totals = {"8": 0, "10": 0, "80": 0, "81": 0}
        for r in recs:
            for pid, v in r["votos_partidos"].items():
                party_totals[pid] = party_totals.get(pid, 0) + v

        row = {k: v for k, v in zip(group_keys, key)}
        row.update({
            "actas_total":               agg_actas_total,
            "actas_contabilizadas":      agg_actas_cnt,
            "pct_actas_contabilizadas":  pct_actas,
            "pct_participacion":         pct_part,
            "votos_emitidos":            agg_emitidos,
            "votos_validos":             agg_validos,
            "votos_habiles":             agg_habiles,
            "votos_partidos":            party_totals,
        })
        out.append(row)
    return out


def run_simulation():
    # ── 1. Load R1 source ────────────────────────────────────────────────────
    print("Loading first-round district data...")
    with open("first_round_agg_results/agg_distrital.json", encoding="utf-8") as f:
        r1_records = json.load(f)
    with open("first_round_agg_results/idx_codigo_nombre_partido.json", encoding="utf-8") as f:
        r1_mapping = json.load(f)

    all_party_cols = list(r1_mapping.keys())

    # ── 2. Back up current processed_results ─────────────────────────────────
    if not os.path.exists(BACKUP_DIR):
        print(f"Backing up processed_results → {BACKUP_DIR}/")
        shutil.copytree(OUT_DIR, BACKUP_DIR)
    else:
        print(f"Backup already exists at {BACKUP_DIR}/ — skipping backup.")

    # ── 3. Assign reporting status per district ───────────────────────────────
    # Domestic (ambito=1): 62% of districts have results
    # Exterior (ambito=2): 45% of districts have results
    # Geographic clusters: some departments are more advanced
    FAST_DEPTS = {
        "LIMA", "AREQUIPA", "ICA", "TACNA", "MOQUEGUA",
        "LA LIBERTAD", "LAMBAYEQUE",
    }
    SLOW_DEPTS = {"LORETO", "UCAYALI", "MADRE DE DIOS", "AMAZONAS"}

    def _report_probability(ambito, dept):
        if ambito == "2":   return 0.45
        if dept in FAST_DEPTS: return 0.78
        if dept in SLOW_DEPTS: return 0.42
        return 0.62

    def _partial_frac(ambito, dept):
        """Return fraction of actas counted (1.0 = fully counted)."""
        p = rng.random()
        if p < 0.70:   # 70% of reporting districts are fully counted
            return 1.0
        return rng.uniform(0.50, 0.99)  # rest are partial

    # ── 4. Simulate district records ─────────────────────────────────────────
    print("Simulating segunda vuelta district records...")
    simulated = []
    for r1 in r1_records:
        amb  = r1["ambito"]
        dept = r1["departamento"]
        p    = _report_probability(amb, dept)
        rep  = rng.random() < p
        frac = _partial_frac(amb, dept) if rep else 0.0
        simulated.append(_simulate_district(r1, all_party_cols, rep, frac))

    # ── 5. Aggregate ─────────────────────────────────────────────────────────
    print("Aggregating into higher-level files...")
    agg_ambito     = _aggregate(simulated, ["ambito"])
    agg_dept       = _aggregate(simulated, ["ambito", "departamento"])
    agg_provincial = _aggregate(simulated, ["ambito", "departamento", "provincia"])

    # ── 6. New party mapping (segunda vuelta only) ────────────────────────────
    new_mapping = {
        "8":  "FUERZA POPULAR",
        "10": "JUNTOS POR EL PERÚ",
        "80": "VOTOS EN BLANCO",
        "81": "VOTOS NULOS",
    }

    # ── 7. Write files ────────────────────────────────────────────────────────
    def _write(path, data):
        with open(path, "w", encoding="utf-8") as fout:
            json.dump(data, fout, ensure_ascii=False, indent=2)
        print(f"  Wrote {path}")

    _write(f"{OUT_DIR}/agg_distrital.json",             simulated)
    _write(f"{OUT_DIR}/agg_ambito.json",                agg_ambito)
    _write(f"{OUT_DIR}/agg_departamental.json",         agg_dept)
    _write(f"{OUT_DIR}/agg_provincial.json",            agg_provincial)
    _write(f"{OUT_DIR}/idx_codigo_nombre_partido.json", new_mapping)

    # ── 8. Summary ────────────────────────────────────────────────────────────
    rep_recs   = [r for r in simulated if r["actas_contabilizadas"] > 0]
    n_total    = len(simulated)
    n_reported = len(rep_recs)
    f1_total   = sum(r["votos_partidos"]["8"]  for r in rep_recs)
    f2_total   = sum(r["votos_partidos"]["10"] for r in rep_recs)
    finalist_total = max(f1_total + f2_total, 1)

    print(f"\n✅ Simulation complete")
    print(f"   Districts:  {n_reported}/{n_total} reporting ({n_reported/n_total*100:.1f}%)")
    print(f"   F1 (party 8)  share of observed finalist votes: {f1_total/finalist_total*100:.2f}%")
    print(f"   F2 (party 10) share of observed finalist votes: {f2_total/finalist_total*100:.2f}%")
    print(f"\nRun: source .venv/bin/activate && python app.py")
    print(f"To restore R1 data: python simulate_segunda_vuelta.py --restore")


def restore():
    if not os.path.exists(BACKUP_DIR):
        print(f"No backup found at {BACKUP_DIR}/ — nothing to restore.")
        return
    print(f"Restoring processed_results from {BACKUP_DIR}/...")
    shutil.rmtree(OUT_DIR)
    shutil.copytree(BACKUP_DIR, OUT_DIR)
    print("✅ Restored.")


def check():
    with open(f"{OUT_DIR}/idx_codigo_nombre_partido.json") as f:
        m = json.load(f)
    parties = set(m.keys()) - {"80", "81"}
    with open(f"{OUT_DIR}/agg_ambito.json") as f:
        a = json.load(f)
    pct = {x["ambito"]: x["pct_actas_contabilizadas"] for x in a}

    print(f"Parties in processed_results: {sorted(parties)}")
    print(f"Coverage: {pct}")
    if parties <= {"8", "10"}:
        print("→ Currently loaded: SEGUNDA VUELTA (simulated)")
    else:
        print("→ Currently loaded: PRIMERA VUELTA (original)")
    print(f"Backup exists: {os.path.exists(BACKUP_DIR)}")


if __name__ == "__main__":
    import sys
    if "--restore" in sys.argv:
        restore()
    elif "--check" in sys.argv:
        check()
    else:
        run_simulation()
