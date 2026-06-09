#!/usr/bin/env python3
"""
Generate a standalone static dashboard HTML with all data embedded inline.
The output file requires no server — open it directly in a browser.

Usage:
    source .venv/bin/activate
    python generate_static_dashboard.py [output_path]

Default output: dashboard_static.html
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import ROUND1, ROUND2


class _Encoder(json.JSONEncoder):
    """Handle numpy scalars that may come from model outputs."""
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_round(base_dir, is_final):
    from pathlib import Path as _P
    base = _P(base_dir)
    file_paths = {
        "ambito":        base / "agg_ambito.json",
        "departamental": base / "agg_departamental.json",
        "parties":       base / "idx_codigo_nombre_partido.json",
    }
    missing = [str(p) for p in file_paths.values() if not p.exists()]
    if missing:
        print(f"  Warning: missing files in {base}: {missing}")
        return None
    return {
        "ambito":        _read(str(file_paths["ambito"])),
        "departamental": _read(str(file_paths["departamental"])),
        "parties":       _read(str(file_paths["parties"])),
        "last_updated":  os.path.getmtime(str(file_paths["departamental"])),
        "is_final":      is_final,
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "dashboard_static.html"

    print("Loading round data...")
    first  = load_round(ROUND1, is_final=True)
    second = load_round(ROUND2, is_final=False)

    print("Running propagation model...")
    try:
        from models.propagation import get_projection_data
        prop = get_projection_data()
        print(f"  OK — {len(prop.get('parties', []))} parties")
    except Exception as exc:
        print(f"  Warning: {exc}")
        prop = None

    print("Running propagation model (by dept)...")
    try:
        from models.propagation import get_projection_data_by_dept
        prop_dept = get_projection_data_by_dept()
        print(f"  OK — {len(prop_dept.get('departments', {}))} departments")
    except Exception as exc:
        print(f"  Warning: {exc}")
        prop_dept = None

    print("Running migration model...")
    try:
        from models.migration import get_migration_data
        migr = get_migration_data()
        status = migr.get("status", "ok") if migr else "error"
        print(f"  OK — status={status}")
    except Exception as exc:
        print(f"  Warning: {exc}")
        migr = None

    print("Running migration model (by dept)...")
    try:
        from models.migration import get_migration_data_by_dept
        migr_dept = get_migration_data_by_dept()
        status = migr_dept.get("status", "ok") if migr_dept else "error"
        print(f"  OK — status={status}, {len(migr_dept.get('departments', {}))} departments")
    except Exception as exc:
        print(f"  Warning: {exc}")
        migr_dept = None

    # Build the static API map — mirrors the exact shapes the dashboard JS expects
    static_map = {
        "/api/round/first":            {"ok": True,  "data": first}     if first     else {"ok": False, "error": "No data"},
        "/api/round/second":           {"ok": True,  "data": second}    if second    else {"ok": False, "error": "No data"},
        "/api/model/propagation":      {"ok": True,  "data": prop}      if prop      else {"ok": False, "error": "Model unavailable"},
        "/api/model/propagation/dept": {"ok": True,  "data": prop_dept} if prop_dept else {"ok": False, "error": "Model unavailable"},
        "/api/model/migration":        migr      if migr      else {"ok": False, "error": "Model unavailable"},
        "/api/model/migration/dept":   migr_dept if migr_dept else {"ok": False, "error": "Model unavailable"},
    }

    static_json = json.dumps(static_map, ensure_ascii=False, cls=_Encoder)

    # Fetch-override shim: intercepts the four API calls and returns embedded data
    ts_label = time.strftime("%d %b %Y %H:%M", time.localtime())
    shim = f"""<script>
/* ── Snapshot generated {ts_label} by generate_static_dashboard.py ── */
(function () {{
  var STATIC = {static_json};
  var _real = window.fetch.bind(window);
  window.fetch = function (url) {{
    if (Object.prototype.hasOwnProperty.call(STATIC, url)) {{
      var payload = STATIC[url];
      return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(payload); }} }});
    }}
    return _real(url);
  }};
}})();
</script>
"""

    template = Path("dashboard.html").read_text(encoding="utf-8")

    # Inject shim right before the main <script> block
    injection_marker = "<script>\n// ─── State"
    if injection_marker not in template:
        print("ERROR: could not find injection point in dashboard.html")
        sys.exit(1)

    html = template.replace(injection_marker, shim + injection_marker, 1)

    # Replace live indicators with static ones
    html = html.replace(
        '<div class="live-dot"><span class="pulse"></span> En vivo</div>',
        f'<div class="live-dot" style="background:rgba(255,255,255,.08);color:rgba(255,255,255,.55)">'
        f'📸 Snapshot · {ts_label}</div>',
    )
    html = html.replace(
        '<button id="btn-refresh" class="btn btn-ghost" onclick="refreshAll()">↻ Actualizar</button>',
        '',
    )

    # Update page title
    html = html.replace(
        "<title>Elecciones Generales 2026 · Dashboard</title>",
        f"<title>Elecciones Generales 2026 · Dashboard — {ts_label}</title>",
    )

    Path(out_path).write_text(html, encoding="utf-8")
    size_kb = Path(out_path).stat().st_size / 1024
    print(f"\nGenerated: {out_path}  ({size_kb:.1f} KB)")
    print("Share this file — it opens in any browser with no server needed.")
    print("Note: Chart.js is still loaded from CDN (requires internet).")


if __name__ == "__main__":
    main()
