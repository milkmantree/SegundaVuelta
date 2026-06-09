"""
exterior_analysis.py

Sensibilidad del voto exterior sobre el resultado nacional.

Punto de partida fijo:
  - Doméstico (ámbito 1): proyección del modelo de propagación dinámica
  - Exterior observado (ámbito 2): votos ya contabilizados en processed_results/

Análisis de sensibilidad:
  Tabla 2D — filas: tasa de participación exterior supuesta
              columnas: % de votos válidos que obtendría FP del exterior restante
  Celda: margen FP − JPP al final del escurutinio (positivo = FP gana)

Usage:
    python exterior_analysis.py
    python exterior_analysis.py --skip-model   # usa 0 como proyección doméstica
"""

import argparse, json, math, sys, io, os
from pathlib import Path
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import ROUND1, ROUND2

ROOT             = Path(__file__).parent
R1_DEPARTAMENTAL = ROUND1 / "agg_departamental.json"
R2_AMBITO        = ROUND2 / "agg_ambito.json"

EXTERIOR_DEPTS = {"AMERICA", "AMÉRICА", "EUROPA", "ASIA", "OCEANIA", "OCEANÍA", "AFRICA", "ÁFRICA"}

FP_ID  = "8"
JPP_ID = "10"


# ── helpers ──────────────────────────────────────────────────────────────────

def _pct(n, d):
    return n / d * 100 if d else 0.0

def _sign(x):
    return f"+{x:,.0f}" if x >= 0 else f"{x:,.0f}"

def _winner(fp, jpp):
    return "FP" if fp > jpp else ("JPP" if jpp > fp else "EMPATE")


# ── Step 1: observed exterior ─────────────────────────────────────────────────

def load_observed_exterior():
    """Return (fp_votes, jpp_votes, valid_votes) from processed_results/ ámbito 2."""
    if not R2_AMBITO.exists():
        return 0, 0, 0
    rows = json.loads(R2_AMBITO.read_text(encoding="utf-8"))
    fp = jpp = valid = 0
    for r in rows:
        if str(r.get("ambito", "1")) == "2":
            vp     = r.get("votos_partidos", {})
            fp    += int(vp.get(FP_ID,  0))
            jpp   += int(vp.get(JPP_ID, 0))
            valid += r.get("votos_validos", 0)
    return fp, jpp, valid


# ── Step 2: R1 exterior participation baseline ────────────────────────────────

REGION_ORDER = ["AMÉRICA", "EUROPA", "ASIA", "OCEANÍA", "ÁFRICA"]
_NORM = str.maketrans("ÉÁÓÍÚ", "EAOIU")

def _norm(s):
    return s.upper().strip().translate(_NORM)


def load_r1_exterior_by_region():
    """
    Returns a dict region_name → {hab, emit, valid, part_rate, valid_rate}
    using display names from REGION_ORDER (with accents).
    """
    if not R1_DEPARTAMENTAL.exists():
        return {}
    rows = json.loads(R1_DEPARTAMENTAL.read_text(encoding="utf-8"))
    regions = {}
    for r in rows:
        if str(r.get("ambito", "1")) != "2":
            continue
        raw = r.get("departamento", "")
        key = _norm(raw)
        if key not in EXTERIOR_DEPTS:
            continue
        # find display name
        display = next((d for d in REGION_ORDER if _norm(d) == key), raw.upper())
        hab   = r.get("votos_habiles",  0)
        emit  = r.get("votos_emitidos", 0)
        valid = r.get("votos_validos",  0)
        regions[display] = {
            "hab":        hab,
            "emit":       emit,
            "valid":      valid,
            "part_rate":  emit / hab  if hab  else 0.0,
            "valid_rate": valid / emit if emit else 0.749,
        }
    return regions


def load_r1_exterior_baseline():
    """Aggregate totals across all exterior regions."""
    regions = load_r1_exterior_by_region()
    hab = emit = valid = 0
    for v in regions.values():
        hab   += v["hab"]
        emit  += v["emit"]
        valid += v["valid"]
    valid_rate = valid / emit if emit else 0.749
    return hab, valid_rate, emit, valid


def load_observed_exterior_by_region():
    """
    Returns a dict region_name → {fp, jpp, valid} from processed_results/ agg_departamental.json.
    Falls back to zeros if file absent.
    """
    dept_file = ROUND2 / "agg_departamental.json"
    if not dept_file.exists():
        return {}
    rows = json.loads(dept_file.read_text(encoding="utf-8"))
    obs = {}
    for r in rows:
        if str(r.get("ambito", "1")) != "2":
            continue
        raw = r.get("departamento", "")
        key = _norm(raw)
        if key not in EXTERIOR_DEPTS:
            continue
        display = next((d for d in REGION_ORDER if _norm(d) == key), raw.upper())
        vp = r.get("votos_partidos", {})
        obs[display] = {
            "fp":    int(vp.get(FP_ID,  0)),
            "jpp":   int(vp.get(JPP_ID, 0)),
            "valid": r.get("votos_validos", 0),
        }
    return obs


# ── Step 3: domestic projection ───────────────────────────────────────────────

def load_domestic_projection():
    """
    Run propagation model and return (fp_proj_domestic, jpp_proj_domestic).
    The model's projected_votes includes observed exterior, so we subtract it.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        from propagation_model import get_projection_data
        result = get_projection_data()

    parties = {p["id"]: p for p in result.get("parties", [])}
    fp_all  = parties.get(FP_ID,  {}).get("projected_votes", 0)
    jpp_all = parties.get(JPP_ID, {}).get("projected_votes", 0)

    # subtract already-counted exterior so we have domestic-only projection
    ext_fp, ext_jpp, _ = load_observed_exterior()
    return fp_all - ext_fp, jpp_all - ext_jpp


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-model", action="store_true",
                        help="Skip propagation model (use 0 as domestic projection)")
    args = parser.parse_args()

    # ── Observed exterior ─────────────────────────────────────────────────────
    ext_fp_obs, ext_jpp_obs, ext_valid_obs = load_observed_exterior()
    ext_h2h_obs = _pct(ext_fp_obs, ext_fp_obs + ext_jpp_obs)

    # ── R1 exterior baseline ──────────────────────────────────────────────────
    r1_hab, r1_valid_rate, r1_emit, r1_valid = load_r1_exterior_baseline()
    r1_part_rate = r1_emit / r1_hab if r1_hab else 0.0

    # ── Domestic projection ───────────────────────────────────────────────────
    if args.skip_model:
        dom_fp, dom_jpp = 0, 0
        model_label = "(omitido — usa 0)"
    else:
        print("  Cargando modelo de propagación dinámica...", flush=True)
        dom_fp, dom_jpp = load_domestic_projection()
        model_label = "propagación dinámica"

    # ── Fixed starting point ──────────────────────────────────────────────────
    fixed_fp  = dom_fp  + ext_fp_obs
    fixed_jpp = dom_jpp + ext_jpp_obs
    fixed_gap = fixed_fp - fixed_jpp    # positive = FP leads

    # ── Print ─────────────────────────────────────────────────────────────────
    W = 82
    print()
    print("  " + "═" * W)
    print("   ANÁLISIS DE SENSIBILIDAD — VOTO EXTERIOR")
    print("  " + "═" * W)

    print()
    print(f"  ┌─ PUNTO DE PARTIDA (fijo) ─────────────────────────────────────────────┐")
    print(f"  │  Modelo doméstico : {model_label}")
    print(f"  │  {'':42}  {'FP':>12}   {'JPP':>12}")
    print(f"  │  {'Doméstico proyectado (prop.)':<42}  {dom_fp:>12,}   {dom_jpp:>12,}")
    print(f"  │  {'Exterior observado (ámbito 2)':<42}  {ext_fp_obs:>12,}   {ext_jpp_obs:>12,}")
    if ext_valid_obs > 0:
        print(f"  │    ({ext_valid_obs:,} votos válidos ext. contabilizados — FP {ext_h2h_obs:.1f}% h2h)")
    print(f"  │  {'─'*64}")
    print(f"  │  {'TOTAL PUNTO DE PARTIDA':<42}  {fixed_fp:>12,}   {fixed_jpp:>12,}")
    print(f"  │  {'Brecha actual':<42}  {_sign(fixed_gap):>12}   ({_winner(fixed_fp, fixed_jpp)} lidera)")
    print(f"  └───────────────────────────────────────────────────────────────────────┘")

    print()
    print(f"  ┌─ BASE EXTERIOR R1 ────────────────────────────────────────────────────┐")
    print(f"  │  Habilitados exterior (R1)  : {r1_hab:>10,}")
    print(f"  │  Participación R1           : {r1_part_rate*100:>9.1f}%  ({r1_emit:,} emitidos)")
    print(f"  │  Tasa válidos/emitidos R1   : {r1_valid_rate:>9.3f}  ({r1_valid:,} válidos)")
    print(f"  │  Exterior ya contabilizado  : {ext_valid_obs:>10,}  votos válidos")
    print(f"  └───────────────────────────────────────────────────────────────────────┘")

    # ── Sensitivity table ─────────────────────────────────────────────────────
    # Rows: participation rates
    # Columns: FP% of remaining exterior valid votes
    part_rates = [0.10, 0.15, 0.20, 0.25, 0.30, r1_part_rate, 0.35, 0.40]
    part_rates = sorted(set(round(p, 4) for p in part_rates))

    fp_pcts = [0.55, 0.60, 0.65, 0.67, 0.70, 0.75]

    print()
    print(f"  Tabla de sensibilidad: votos NETOS para FP del exterior restante (FP − JPP)")
    print(f"  Filas = tasa de participación exterior supuesta")
    print(f"  Columnas = % de votos válidos restantes del exterior que obtiene FP")
    print(f"  Brecha a cubrir: {_sign(fixed_gap)} votos  ({_winner(fixed_fp, fixed_jpp)} lidera el punto de partida)")
    print()

    # Header
    col_w = 10
    hdr_cols = "  ".join(f"FP={int(p*100)}%".center(col_w) for p in fp_pcts)
    bk_w = 11
    print(f"  {'Part%':>6}  {'V.resto':>9}  {'Breakeven':>{bk_w}}  {hdr_cols}")
    print("  " + "─" * (6 + 2 + 9 + 2 + bk_w + 2 + len(hdr_cols) + 2))

    for pt in part_rates:
        is_r1    = abs(pt - r1_part_rate) < 0.0001
        label    = f"{pt*100:.0f}%{'*' if is_r1 else ' '}"
        v_total  = r1_hab * pt * r1_valid_rate
        v_remain = max(0.0, v_total - ext_valid_obs)

        # Breakeven: FP% of remaining votes such that net_ext cancels the gap
        if v_remain > 0:
            bk = 0.5 + (fixed_jpp - fixed_fp) / (2.0 * v_remain)
            if bk <= 0:
                bk_s = "<0% (ya ganó)"
            elif bk > 1:
                bk_s = ">100% (imposible)"
            else:
                bk_s = f"{bk*100:.1f}%"
        else:
            bk_s = "—"

        cells = []
        for fp_p in fp_pcts:
            # Net votes FP gains from remaining exterior = fp_add - jpp_add
            net_ext = (2 * fp_p - 1) * v_remain
            # Final national margin = fixed_gap + net_ext
            final   = fixed_gap + net_ext
            sym = "▲" if final > 0 else ("▼" if final < 0 else "=")
            cell = f"{sym}{net_ext/1000:>+5.1f}k".center(col_w)
            cells.append(cell)

        tag = " ← R1" if is_r1 else ""
        print(f"  {label:>6}  {v_remain:>9,.0f}  {bk_s:>{bk_w}}  {'  '.join(cells)}{tag}")

    print()
    print(f"  Valores = votos netos FP del exterior restante (FP − JPP de esas papeletas)")
    print(f"  ▲ = margen final FP positivo (FP gana nacional)   ▼ = JPP gana nacional")
    print(f"  * participación R1 exterior ({r1_part_rate*100:.1f}%)")
    print(f"  V.resto = votos válidos exteriores restantes estimados (total proyectado − ya contabilizados)")
    print()
    print(f"  Nota: 'votos válidos' incluye blancos — el % de FP es sobre válidos, no h2h.")

    # ── Net exterior votes for FP (standalone, no domestic gap) ─────────────
    print()
    print(f"  Votos netos del exterior para FP (FP − JPP, miles de votos)")
    print(f"  Filas = tasa de participación exterior supuesta")
    print(f"  Columnas = % de votos válidos restantes del exterior que obtiene FP")
    print()

    col_w2 = 10
    fp_hdr2 = "  ".join(f"FP={int(p*100)}%".center(col_w2) for p in fp_pcts)
    print(f"  {'Part%':>6}  {'V.resto':>9}  {fp_hdr2}")
    print("  " + "─" * (6 + 2 + 9 + 2 + len(fp_hdr2) + 2))

    for pt in part_rates:
        is_r1    = abs(pt - r1_part_rate) < 0.0001
        label    = f"{pt*100:.0f}%{'*' if is_r1 else ' '}"
        v_total  = r1_hab * pt * r1_valid_rate
        v_remain = max(0.0, v_total - ext_valid_obs)

        cells = []
        for fp_p in fp_pcts:
            net = (2 * fp_p - 1) * v_remain
            cells.append(f"{net/1000:>+.1f}k".center(col_w2))

        tag = " ← R1" if is_r1 else ""
        print(f"  {label:>6}  {v_remain:>9,.0f}  {'  '.join(cells)}{tag}")

    print()
    print(f"  * participación R1 exterior ({r1_part_rate*100:.1f}%)")
    print(f"  V.resto = votos válidos exteriores restantes (total proyectado − ya contabilizados)")
    print(f"  Neto positivo = FP gana el exterior   Neto negativo = JPP gana el exterior")
    print("  " + "═" * W)
    print()


if __name__ == "__main__":
    main()
