import json
import math
import os
import sys
import time

from flask import Flask, jsonify, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import ROUND1, ROUND2, PREDICTION_HISTORY

app = Flask(__name__)

_cache: dict = {}
CACHE_TTL = 60  # seconds before model result is recomputed

HISTORY_FILE = str(PREDICTION_HISTORY)
_last_recorded_coverage: float | None = None


def _sanitize(obj):
    """Recursively replace NaN/Inf floats with None so JSON serialization is browser-safe."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _record_snapshot() -> None:
    """Append a snapshot to history when both models are cached and coverage changed."""
    global _last_recorded_coverage

    prop     = _cache.get("prop",      {}).get("data")
    migr     = _cache.get("migr",      {}).get("data")
    prop_dept = _cache.get("prop_dept", {}).get("data")
    migr_dept = _cache.get("migr_dept", {}).get("data")

    if not prop or not migr or not prop_dept or not migr_dept:
        return
    if migr.get("status") != "ok" or not migr.get("ok"):
        return

    coverage_pct = migr.get("pct_coverage", 0.0)
    if _last_recorded_coverage is not None and abs(coverage_pct - _last_recorded_coverage) < 0.05:
        return

    BN = {"80", "81"}
    prop_parties = [
        {k: p[k] for k in ("id", "name", "projected_votes", "projected_share",
                            "lower_bound", "upper_bound", "moe", "observed_votes")}
        for p in prop.get("parties", [])
        if p.get("id") not in BN
    ]
    migr_finalists = [
        {k: f[k] for k in ("id", "name", "projected_votes", "projected_share",
                            "lower_bound", "upper_bound", "moe", "valid_share",
                            "observed_votes")}
        for f in migr.get("finalists", [])
    ]

    record: dict = {
        "ts":           time.time(),
        "coverage_pct": coverage_pct,
        "n_reported":   migr.get("n_districts_reported", 0),
        "n_total":      migr.get("n_districts_total", 0),
        "prop":         prop_parties,
        "migr":         migr_finalists,
    }

    if prop_dept and prop_dept.get("departments"):
        record["prop_dept"] = {
            dept: {
                "n_reported": dd.get("n_reported"),
                "n_total":    dd.get("n_total"),
                "parties": [
                    {k: p[k] for k in ("id", "projected_votes", "projected_share",
                                       "lower_bound", "upper_bound", "moe")}
                    for p in dd.get("parties", [])
                ],
            }
            for dept, dd in prop_dept["departments"].items()
        }

    if migr_dept and migr_dept.get("departments"):
        record["migr_dept"] = {
            dept: {
                "n_reported": dd.get("n_reported"),
                "n_total":    dd.get("n_total"),
                "parties": [
                    {k: f[k] for k in ("id", "projected_share", "lower_bound",
                                       "upper_bound", "moe", "valid_share")}
                    for f in (dd.get("finalists") or dd.get("parties", []))
                ],
            }
            for dept, dd in migr_dept["departments"].items()
        }

    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_sanitize(record), ensure_ascii=False) + "\n")

    _last_recorded_coverage = coverage_pct


def _read(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    return render_template("dashboard.html")


def _round_payload(base_dir, is_final: bool):
    from pathlib import Path
    base = Path(base_dir)
    file_paths = {
        "ambito":        base / "agg_ambito.json",
        "departamental": base / "agg_departamental.json",
        "parties":       base / "idx_codigo_nombre_partido.json",
    }
    missing = [str(p) for p in file_paths.values() if not p.exists()]
    if missing:
        return None, missing
    data = {
        "ambito":        _read(str(file_paths["ambito"])),
        "departamental": _read(str(file_paths["departamental"])),
        "parties":       _read(str(file_paths["parties"])),
        "last_updated":  os.path.getmtime(str(file_paths["departamental"])),
        "is_final":      is_final,
    }
    return data, None


@app.route("/api/round/first")
def api_first_round():
    data, missing = _round_payload(ROUND1, is_final=True)
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {missing}"}), 404
    return jsonify({"ok": True, "data": data})


@app.route("/api/round/second")
@app.route("/api/observed")          # keep old path working
def api_second_round():
    data, missing = _round_payload(ROUND2, is_final=False)
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {missing}"}), 404
    return jsonify({"ok": True, "data": data})


@app.route("/api/model/propagation")
def api_model_propagation():
    now = time.time()
    if "prop" in _cache and now - _cache["prop"]["ts"] < CACHE_TTL:
        return jsonify({"ok": True, "data": _cache["prop"]["data"]})
    try:
        from models.propagation import get_projection_data
        data = get_projection_data()
        _cache["prop"] = {"ts": now, "data": data}
        _record_snapshot()
        return jsonify({"ok": True, "data": data})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/model/propagation/dept")
def api_model_propagation_dept():
    now = time.time()
    if "prop_dept" in _cache and now - _cache["prop_dept"]["ts"] < CACHE_TTL:
        return jsonify({"ok": True, "data": _cache["prop_dept"]["data"]})
    try:
        from models.propagation import get_projection_data_by_dept
        data = get_projection_data_by_dept()
        _cache["prop_dept"] = {"ts": now, "data": data}
        _record_snapshot()
        return jsonify({"ok": True, "data": data})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/model/migration/dept")
def api_model_migration_dept():
    now = time.time()
    if "migr_dept" in _cache and now - _cache["migr_dept"]["ts"] < CACHE_TTL:
        return jsonify(_cache["migr_dept"]["data"])
    try:
        from models.migration import get_migration_data_by_dept
        data = get_migration_data_by_dept()
        _cache["migr_dept"] = {"ts": now, "data": data}
        _record_snapshot()
        return jsonify(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/model/migration")
def api_model_migration():
    now = time.time()
    if "migr" in _cache and now - _cache["migr"]["ts"] < CACHE_TTL:
        return jsonify(_cache["migr"]["data"])
    try:
        from models.migration import get_migration_data
        data = get_migration_data()
        _cache["migr"] = {"ts": now, "data": data}
        _record_snapshot()
        return jsonify(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/model/unreported")
def api_model_unreported():
    now = time.time()
    if "unreported" in _cache and now - _cache["unreported"]["ts"] < CACHE_TTL:
        return jsonify(_cache["unreported"]["data"])
    try:
        from models.propagation import get_projection_data_by_dept
        from models.migration import get_migration_data_by_dept

        r2_districts = _read(str(ROUND2 / "agg_distrital.json"))
        r1_index = {d["ubigeo"]: d for d in _read(str(ROUND1 / "agg_distrital.json"))}

        prop_dept = get_projection_data_by_dept()
        migr_dept = get_migration_data_by_dept()

        prop_depts = prop_dept.get("departments", {})
        migr_depts = migr_dept.get("departments", {}) if migr_dept.get("ok") else {}

        def dept_h2h(depts, dept_name, finalist_id):
            d = depts.get(dept_name)
            if not d:
                return None, None, None
            parties = d.get("parties") or d.get("finalists") or []
            total = sum(p["projected_votes"] for p in parties)
            if total == 0:
                return None, None, None
            hit = next((p for p in parties if p["id"] == finalist_id), None)
            if not hit:
                return None, None, None
            h2h = hit["projected_votes"] / total * 100
            scale = h2h / hit["projected_share"] if hit.get("projected_share", 0) > 0 else 1
            return h2h, hit.get("lower_bound", h2h) * scale, hit.get("upper_bound", h2h) * scale

        # R2/R1 valid ratio from reported districts (used to estimate R2 valid for unreported)
        agg_ambito = _read(str(ROUND2 / "agg_ambito.json"))
        r2_valid_obs = sum(a["votos_validos"] for a in agg_ambito)
        reported_r1_valid = sum(
            r1_index[d["ubigeo"]]["votos_validos"]
            for d in r2_districts
            if d.get("pct_actas_contabilizadas", 0) > 0 and d["ubigeo"] in r1_index
               and r1_index[d["ubigeo"]]["votos_validos"] > 0
        )
        r2_r1_ratio = r2_valid_obs / reported_r1_valid if reported_r1_valid > 0 else 1.0

        # Determine finalist IDs once from migration dept data
        fin_ids = []
        for md in migr_depts.values():
            parties = md.get("parties") or md.get("finalists") or []
            if parties:
                fin_ids = [p["id"] for p in parties]
                break
        if not fin_ids:
            for pd2 in prop_depts.values():
                parties = pd2.get("parties") or []
                if parties:
                    fin_ids = [p["id"] for p in sorted(parties, key=lambda x: -x["projected_votes"])[:2]]
                    break

        rows = []
        for d in r2_districts:
            pct = d.get("pct_actas_contabilizadas", d.get("totales", {}).get("pct_actas_contabilizadas", 0))
            if pct >= 100:
                continue
            ubigeo = d["ubigeo"]
            r1 = r1_index.get(ubigeo)
            if not r1 or r1["votos_validos"] == 0:
                continue
            dept_name = r1["departamento"]
            r1v    = r1["votos_validos"]
            vp     = r1["votos_partidos"]
            actas_total = d.get("actas_total", d.get("totales", {}).get("actas_total", 0))
            actas_cont  = d.get("actas_contabilizadas", d.get("totales", {}).get("actas_contabilizadas", 0))
            ambito = d.get("ambito", "1")

            # Remaining fraction of actas not yet counted
            remaining_frac = 1.0 - pct / 100.0

            # Estimated R2 valid votes still to arrive from this district
            est_valid = round(r1v * r2_r1_ratio * remaining_frac)
            if est_valid == 0:
                continue

            row = {
                "ubigeo":       ubigeo,
                "dept":         dept_name,
                "prov":         r1["provincia"],
                "dist":         r1["distrito"],
                "ambito":       ambito,
                "pct_reported": round(pct, 2),
                "actas_total":  actas_total,
                "actas_cont":   actas_cont,
                "actas_remain": actas_total - actas_cont,
                "r1_habiles":   r1.get("votos_habiles", 0),
                "r1_valid":     r1v,
                "est_valid":    est_valid,
            }
            for i, pid in enumerate(fin_ids[:2]):
                key = "f1" if i == 0 else "f2"
                r1_sh = int(vp.get(pid, 0)) / r1v * 100
                row[f"{key}_id"]       = pid
                row[f"{key}_r1_share"] = round(r1_sh, 2)

                h2h, lb, ub = dept_h2h(prop_depts, dept_name, pid)
                row[f"{key}_prop_h2h"]   = round(h2h, 2) if h2h is not None else None
                row[f"{key}_prop_lb"]    = round(lb, 2)  if lb  is not None else None
                row[f"{key}_prop_ub"]    = round(ub, 2)  if ub  is not None else None
                row[f"{key}_prop_votes"] = round(h2h / 100 * est_valid) if h2h is not None else None

                h2h, lb, ub = dept_h2h(migr_depts, dept_name, pid)
                row[f"{key}_migr_h2h"]   = round(h2h, 2) if h2h is not None else None
                row[f"{key}_migr_lb"]    = round(lb, 2)  if lb  is not None else None
                row[f"{key}_migr_ub"]    = round(ub, 2)  if ub  is not None else None
                row[f"{key}_migr_votes"] = round(h2h / 100 * est_valid) if h2h is not None else None

            rows.append(row)

        # Attach names from idx
        idx = _read(str(ROUND2 / "idx_codigo_nombre_partido.json"))
        for row in rows:
            row["f1_name"] = idx.get(row.get("f1_id"), row.get("f1_id", ""))
            row["f2_name"] = idx.get(row.get("f2_id"), row.get("f2_id", ""))

        rows.sort(key=lambda r: -r["actas_remain"])

        # Pre-aggregate by department for chart consumption
        dept_agg: dict = {}
        for row in rows:
            dept = row["dept"]
            if dept not in dept_agg:
                dept_agg[dept] = {
                    "dept": dept, "ambito": row["ambito"],
                    "f1_id": row.get("f1_id"), "f2_id": row.get("f2_id"),
                    "f1_name": row.get("f1_name"), "f2_name": row.get("f2_name"),
                    "n_districts": 0, "actas_remain": 0,
                    "f1_prop_votes": 0, "f2_prop_votes": 0,
                    "f1_migr_votes": 0, "f2_migr_votes": 0,
                }
            da = dept_agg[dept]
            da["n_districts"]  += 1
            da["actas_remain"] += row["actas_remain"]
            for model in ("prop", "migr"):
                for fk in ("f1", "f2"):
                    v = row.get(f"{fk}_{model}_votes")
                    if v is not None:
                        da[f"{fk}_{model}_votes"] += v

        # Net margin per dept (f1 - f2), positive = f1 leads
        for da in dept_agg.values():
            da["prop_net"] = da["f1_prop_votes"] - da["f2_prop_votes"]
            da["migr_net"] = da["f1_migr_votes"] - da["f2_migr_votes"]

        data = {
            "ok": True,
            "districts": rows,
            "n": len(rows),
            "r2_r1_ratio": round(r2_r1_ratio, 4),
            "dept_chart": sorted(dept_agg.values(), key=lambda x: -x["actas_remain"]),
            "f1_id": fin_ids[0] if fin_ids else None,
            "f2_id": fin_ids[1] if len(fin_ids) > 1 else None,
        }
        _cache["unreported"] = {"ts": now, "data": data}
        return jsonify(data)
    except Exception as exc:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/cache/clear", methods=["POST"])
def api_cache_clear():
    _cache.clear()
    return jsonify({"ok": True})


@app.route("/api/history")
def api_history():
    if not os.path.exists(HISTORY_FILE):
        return jsonify({"ok": True, "data": []})
    records = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(_sanitize(json.loads(line)))
                except json.JSONDecodeError:
                    pass
    return jsonify({"ok": True, "data": records})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"Dashboard → http://127.0.0.1:{port}")
    app.run(debug=False, port=port, host="127.0.0.1")
