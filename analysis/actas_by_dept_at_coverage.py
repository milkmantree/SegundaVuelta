"""
actas_by_dept_at_coverage.py

Given a target national % of actas contabilizadas, finds the earliest moment
in the first-round count when that coverage level was reached, then reports
the per-department breakdown of % actas contabilizadas at that instant.

Usage:
    python actas_by_dept_at_coverage.py 50
    python actas_by_dept_at_coverage.py 75.5 --out results.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

JSONL_PATH = Path(__file__).parent / "inputs" / "all_actas_merged.jsonl"


def load_actas(path: Path):
    """
    Returns (actas_with_ts, total_by_dept).

    actas_with_ts: list of (contabilizada_ts_ms, department) for every acta
                   that has a "C" event in lineaTiempo.
    total_by_dept: dict[dept] -> total actas in that department (all statuses).
    """
    actas_with_ts = []
    total_by_dept: dict[str, int] = {}

    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            dept = d["ubigeoNivel01"]
            total_by_dept[dept] = total_by_dept.get(dept, 0) + 1

            ts = None
            for event in d.get("lineaTiempo", []):
                if event.get("codigoEstadoActa") == "C":
                    ts = event["fechaRegistro"]
                    break
            if ts is not None:
                actas_with_ts.append((ts, dept))

    return actas_with_ts, total_by_dept


def find_snapshot(target_pct: float, actas_with_ts: list, total_by_dept: dict):
    """
    Sorts actas by their contabilizada timestamp, walks the list until the
    national coverage hits target_pct, and returns the per-department counts
    at that moment plus metadata.
    """
    total_actas = sum(total_by_dept.values())
    target_count = target_pct / 100.0 * total_actas

    actas_sorted = sorted(actas_with_ts, key=lambda x: x[0])

    dept_counted: dict[str, int] = {d: 0 for d in total_by_dept}
    reached_ts = None
    national_count = 0

    for ts, dept in actas_sorted:
        dept_counted[dept] += 1
        national_count += 1
        if national_count >= target_count:
            reached_ts = ts
            break

    actual_national_pct = national_count / total_actas * 100

    return {
        "reached_ts_ms":       reached_ts,
        "national_count":      national_count,
        "total_actas":         total_actas,
        "actual_national_pct": actual_national_pct,
        "dept_counted":        dept_counted,
    }


def build_rows(snapshot: dict, total_by_dept: dict) -> list[dict]:
    rows = []
    for dept in sorted(total_by_dept):
        counted = snapshot["dept_counted"][dept]
        total   = total_by_dept[dept]
        pct     = counted / total * 100 if total > 0 else 0.0
        rows.append({
            "departamento":           dept,
            "actas_contabilizadas":   counted,
            "actas_total":            total,
            "pct_actas_contabilizadas": round(pct, 2),
        })
    # Sort by % descending
    rows.sort(key=lambda r: r["pct_actas_contabilizadas"], reverse=True)
    return rows


def print_table(rows: list[dict], snapshot: dict, target_pct: float):
    from datetime import datetime, timezone, timedelta

    lima_tz = timezone(timedelta(hours=-5))
    ts_s = snapshot["reached_ts_ms"] / 1000
    dt_lima = datetime.fromtimestamp(ts_s, tz=lima_tz)
    dt_str = dt_lima.strftime("%Y-%m-%d %H:%M:%S") + " (Lima)"

    print()
    print(f"  Target coverage  : {target_pct:.2f}%")
    print(f"  Actual coverage  : {snapshot['actual_national_pct']:.4f}%")
    print(f"  Actas counted    : {snapshot['national_count']:,} / {snapshot['total_actas']:,}")
    print(f"  Timestamp reached: {dt_str}")
    print()

    col_dept  = max(len(r["departamento"]) for r in rows)
    col_dept  = max(col_dept, 20)
    header = (
        f"  {'DEPARTAMENTO':<{col_dept}}  "
        f"{'CONTABILIZADAS':>16}  "
        f"{'TOTAL':>8}  "
        f"{'% CONTABILIZADAS':>18}"
    )
    print(header)
    print("  " + "-" * (col_dept + 50))

    for r in rows:
        bar_filled = int(r["pct_actas_contabilizadas"] / 100 * 20)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        print(
            f"  {r['departamento']:<{col_dept}}  "
            f"{r['actas_contabilizadas']:>16,}  "
            f"{r['actas_total']:>8,}  "
            f"{r['pct_actas_contabilizadas']:>17.2f}%  {bar}"
        )

    print()


def write_csv(rows: list[dict], snapshot: dict, out_path: Path):
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["departamento", "actas_contabilizadas", "actas_total", "pct_actas_contabilizadas"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV written to: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Per-department acta coverage at a given national % in the first round."
    )
    parser.add_argument(
        "target_pct",
        type=float,
        help="Target national %% of actas contabilizadas (e.g. 50 or 75.5)",
    )
    parser.add_argument(
        "--out",
        metavar="FILE",
        help="Optional path to write CSV output (default: actas_dept_<pct>.csv)",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip CSV output",
    )
    args = parser.parse_args()

    if not (0 < args.target_pct <= 100):
        print("Error: target_pct must be between 0 and 100.", file=sys.stderr)
        sys.exit(1)

    print(f"\nLoading {JSONL_PATH} ...")
    actas_with_ts, total_by_dept = load_actas(JSONL_PATH)
    print(f"  {len(actas_with_ts):,} actas with contabilizada timestamp out of {sum(total_by_dept.values()):,} total.")

    snapshot = find_snapshot(args.target_pct, actas_with_ts, total_by_dept)
    rows = build_rows(snapshot, total_by_dept)
    print_table(rows, snapshot, args.target_pct)

    if not args.no_csv:
        if args.out:
            out_path = Path(args.out)
        else:
            safe_pct = f"{args.target_pct:.2f}".replace(".", "_")
            out_path = Path(f"actas_dept_{safe_pct}pct.csv")
        write_csv(rows, snapshot, out_path)


if __name__ == "__main__":
    main()
