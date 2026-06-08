"""
compare_actas_rounds.py

Compares the current second-round actas contabilizadas by department against
the equivalent first-round state at the same national coverage level.

The national coverage % from the live second-round data is used as the
reference; the script then walks the first-round timeline to find the moment
when the first round reached that same national %, and reports per-department
coverage for both rounds side by side.

Usage:
    python compare_actas_rounds.py
    python compare_actas_rounds.py --out comparison.csv
    python compare_actas_rounds.py --no-csv
"""

import argparse
import csv
import json
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

JSONL_PATH       = Path(__file__).parent / "inputs" / "all_actas_merged.jsonl"
SECOND_ROUND_AGG = Path(__file__).parent / "processed_results" / "agg_departamental.json"
SECOND_AMBITO    = Path(__file__).parent / "processed_results" / "agg_ambito.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize(name: str) -> str:
    """Strip accents and uppercase for fuzzy department name matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", name.upper())
        if unicodedata.category(c) != "Mn"
    )


def load_second_round():
    """
    Returns:
        national_pct   : float — overall % actas contabilizadas (ambito 1+2)
        dept_rows      : list[dict] — one entry per department with r2 data
    """
    with SECOND_AMBITO.open(encoding="utf-8") as f:
        ambito_data = json.load(f)

    total_counted = sum(r["actas_contabilizadas"] for r in ambito_data)
    total_actas   = sum(r["actas_total"]          for r in ambito_data)
    national_pct  = total_counted / total_actas * 100 if total_actas else 0.0

    with SECOND_ROUND_AGG.open(encoding="utf-8") as f:
        dept_data = json.load(f)

    dept_rows = [
        {
            "departamento":             r["departamento"],
            "ambito":                   r["ambito"],
            "r2_counted":               r["actas_contabilizadas"],
            "r2_total":                 r["actas_total"],
            "r2_pct":                   r["pct_actas_contabilizadas"],
            "_norm":                    normalize(r["departamento"]),
        }
        for r in dept_data
    ]

    return national_pct, total_counted, total_actas, dept_rows


def load_first_round_timeline():
    """
    Returns:
        actas_with_ts  : list[(ts_ms, dept_normalized, dept_raw)]
        total_by_norm  : dict[norm_name] -> (raw_name, total_count)
    """
    actas_with_ts = []
    total_by_norm: dict[str, list] = {}

    with JSONL_PATH.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            raw_dept  = d["ubigeoNivel01"]
            norm_dept = normalize(raw_dept)

            if norm_dept not in total_by_norm:
                total_by_norm[norm_dept] = [raw_dept, 0]
            total_by_norm[norm_dept][1] += 1

            ts = None
            for event in d.get("lineaTiempo", []):
                if event.get("codigoEstadoActa") == "C":
                    ts = event["fechaRegistro"]
                    break
            if ts is not None:
                actas_with_ts.append((ts, norm_dept))

    return actas_with_ts, total_by_norm


def find_r1_snapshot(target_pct: float, actas_with_ts: list, total_by_norm: dict):
    """
    Walk the sorted first-round timeline until national coverage >= target_pct.
    Returns per-dept counts and the timestamp reached.
    """
    total_actas   = sum(v[1] for v in total_by_norm.values())
    target_count  = target_pct / 100.0 * total_actas

    actas_sorted  = sorted(actas_with_ts, key=lambda x: x[0])
    dept_counted  = {norm: 0 for norm in total_by_norm}
    national_count = 0
    reached_ts    = None

    for ts, norm_dept in actas_sorted:
        dept_counted[norm_dept] += 1
        national_count += 1
        if national_count >= target_count:
            reached_ts = ts
            break

    actual_pct = national_count / total_actas * 100

    return {
        "reached_ts_ms":  reached_ts,
        "national_count": national_count,
        "total_actas":    total_actas,
        "actual_pct":     actual_pct,
        "dept_counted":   dept_counted,
    }


def build_comparison(dept_rows, r1_snap, total_by_norm):
    """
    Merges second-round per-dept data with first-round snapshot data.
    Returns list of row dicts, sorted by r2_pct descending.
    """
    rows = []
    for dr in dept_rows:
        norm = dr["_norm"]
        r1_info = total_by_norm.get(norm)

        if r1_info is None:
            r1_counted = None
            r1_total   = None
            r1_pct     = None
        else:
            r1_counted = r1_snap["dept_counted"].get(norm, 0)
            r1_total   = r1_info[1]
            r1_pct     = round(r1_counted / r1_total * 100, 3) if r1_total else 0.0

        rows.append({
            "departamento": dr["departamento"],
            "ambito":       dr["ambito"],
            "r2_counted":   dr["r2_counted"],
            "r2_total":     dr["r2_total"],
            "r2_pct":       dr["r2_pct"],
            "r1_counted":   r1_counted,
            "r1_total":     r1_total,
            "r1_pct":       r1_pct,
            "diff":         round(dr["r2_pct"] - r1_pct, 2) if r1_pct is not None else None,
        })

    rows.sort(key=lambda r: r["r2_pct"], reverse=True)
    return rows


def ts_to_lima(ts_ms):
    lima_tz = timezone(timedelta(hours=-5))
    return datetime.fromtimestamp(ts_ms / 1000, tz=lima_tz).strftime("%Y-%m-%d %H:%M")


def diff_str(diff):
    if diff is None:
        return "N/A"
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.2f}%"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_table(rows, r2_national_pct, r2_counted, r2_total, r1_snap):
    r1_ts_str = ts_to_lima(r1_snap["reached_ts_ms"]) if r1_snap["reached_ts_ms"] else "N/A"

    print()
    print("  ══════════════════════════════════════════════════════════════════════════════")
    print("   COMPARACIÓN DE AVANCE POR DEPARTAMENTO: 2ª VUELTA vs 1ª VUELTA")
    print("  ══════════════════════════════════════════════════════════════════════════════")
    print()
    print(f"  Avance nacional 2ª vuelta : {r2_national_pct:.3f}%  "
          f"({r2_counted:,} / {r2_total:,} actas)")
    print(f"  Referencia 1ª vuelta      : {r1_snap['actual_pct']:.3f}%  "
          f"({r1_snap['national_count']:,} / {r1_snap['total_actas']:,} actas)"
          f"  —  {r1_ts_str} (Lima)")
    print()

    W = 16
    print(
        f"  {'DEPARTAMENTO':<{W}}  "
        f"{'% 2ª VUELTA':>11}  {'(cont/total)':>18}  "
        f"{'% 1ª VUELTA':>11}  {'(cont/total)':>18}  "
        f"{'DIFER.':>8}"
    )
    sep = "─" * (W + 77)
    print("  " + sep)

    domestic = [r for r in rows if r["ambito"] == "1"]
    exterior = [r for r in rows if r["ambito"] == "2"]

    def _print_row(r):
        r2_detail = f"({r['r2_counted']:,}/{r['r2_total']:,})"
        if r["r1_pct"] is not None:
            r1_pct_str = f"{r['r1_pct']:6.2f}%"
            r1_detail  = f"({r['r1_counted']:,}/{r['r1_total']:,})"
        else:
            r1_pct_str = "    N/A"
            r1_detail  = ""
        diff = diff_str(r["diff"])
        print(
            f"  {r['departamento']:<{W}}  "
            f"{r['r2_pct']:>10.2f}%  {r2_detail:>18}  "
            f"{r1_pct_str:>11}  {r1_detail:>18}  "
            f"{diff:>8}"
        )

    print(f"\n  ── PERU ──")
    for r in domestic:
        _print_row(r)

    print(f"\n  ── EXTERIOR ──")
    for r in exterior:
        _print_row(r)

    print()


def write_csv(rows, out_path: Path):
    fieldnames = [
        "departamento", "ambito",
        "r2_actas_contabilizadas", "r2_actas_total", "r2_pct_contabilizadas",
        "r1_actas_contabilizadas", "r1_actas_total", "r1_pct_contabilizadas",
        "diferencia_pct",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "departamento":             r["departamento"],
                "ambito":                   r["ambito"],
                "r2_actas_contabilizadas":  r["r2_counted"],
                "r2_actas_total":           r["r2_total"],
                "r2_pct_contabilizadas":    r["r2_pct"],
                "r1_actas_contabilizadas":  r["r1_counted"] if r["r1_counted"] is not None else "",
                "r1_actas_total":           r["r1_total"]   if r["r1_total"]   is not None else "",
                "r1_pct_contabilizadas":    r["r1_pct"]     if r["r1_pct"]     is not None else "",
                "diferencia_pct":           r["diff"]       if r["diff"]       is not None else "",
            })
    print(f"  CSV written to: {out_path}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare second-round vs first-round acta coverage by department."
    )
    parser.add_argument("--out", metavar="FILE",
                        help="CSV output path (default: actas_comparacion_rondas.csv)")
    parser.add_argument("--no-csv", action="store_true", help="Skip CSV output")
    args = parser.parse_args()

    print("\nCargando datos de la 2ª vuelta ...")
    r2_national_pct, r2_counted, r2_total, dept_rows = load_second_round()
    print(f"  Avance nacional actual: {r2_national_pct:.3f}%")

    print(f"\nCargando timeline de la 1ª vuelta ({JSONL_PATH.name}) ...")
    actas_with_ts, total_by_norm = load_first_round_timeline()
    print(f"  {len(actas_with_ts):,} actas con timestamp de contabilización.")

    print(f"\nBuscando momento equivalente en 1ª vuelta ({r2_national_pct:.3f}%) ...")
    r1_snap = find_r1_snapshot(r2_national_pct, actas_with_ts, total_by_norm)

    rows = build_comparison(dept_rows, r1_snap, total_by_norm)
    print_table(rows, r2_national_pct, r2_counted, r2_total, r1_snap)

    if not args.no_csv:
        out_path = Path(args.out) if args.out else Path("actas_comparacion_rondas.csv")
        write_csv(rows, out_path)


if __name__ == "__main__":
    main()
