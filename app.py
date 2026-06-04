import json
import os
import sys
import time

from flask import Flask, jsonify, send_file

app = Flask(__name__)

_cache: dict = {}
CACHE_TTL = 60  # seconds before model result is recomputed


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
        return jsonify({"ok": True, "data": data})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"Dashboard → http://127.0.0.1:{port}")
    app.run(debug=False, port=port, host="127.0.0.1")
