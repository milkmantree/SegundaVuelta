import json
import math
import os
import sys
import time

from flask import Flask, jsonify, send_file

app = Flask(__name__)

_cache: dict = {}
CACHE_TTL = 60  # seconds before model result is recomputed

HISTORY_FILE = "prediction_history.jsonl"
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
    return send_file("dashboard.html")


def _round_payload(base: str, is_final: bool):
    paths = {
        "ambito":       f"{base}/agg_ambito.json",
        "departamental":f"{base}/agg_departamental.json",
        "parties":      f"{base}/idx_codigo_nombre_partido.json",
    }
    missing = [p for p in paths.values() if not os.path.exists(p)]
    if missing:
        return None, missing
    data = {
        "ambito":       _read(paths["ambito"]),
        "departamental":_read(paths["departamental"]),
        "parties":      _read(paths["parties"]),
        "last_updated": os.path.getmtime(paths["departamental"]),
        "is_final":     is_final,
    }
    return data, None


@app.route("/api/round/first")
def api_first_round():
    data, missing = _round_payload("first_round_agg_results", is_final=True)
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {missing}"}), 404
    return jsonify({"ok": True, "data": data})


@app.route("/api/round/second")
@app.route("/api/observed")          # keep old path working
def api_second_round():
    data, missing = _round_payload("processed_results", is_final=False)
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {missing}"}), 404
    return jsonify({"ok": True, "data": data})


@app.route("/api/model/propagation")
def api_model_propagation():
    now = time.time()
    if "prop" in _cache and now - _cache["prop"]["ts"] < CACHE_TTL:
        return jsonify({"ok": True, "data": _cache["prop"]["data"]})
    try:
        from propagation_model import get_projection_data
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
        from propagation_model import get_projection_data_by_dept
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
        from migration_model import get_migration_data_by_dept
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
        from migration_model import get_migration_data
        data = get_migration_data()
        _cache["migr"] = {"ts": now, "data": data}
        _record_snapshot()
        return jsonify(data)
    except Exception as exc:
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
