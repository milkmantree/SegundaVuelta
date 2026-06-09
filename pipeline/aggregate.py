import os
import json
import glob
import pandas as pd
from typing import Dict, Any, List

LOG_DIR = "log"
INPUT_DIR = "inputs"
OUTPUT_DIR = "processed_results"
VOTOS_HABILES_FILE = os.path.join(INPUT_DIR, "ubigeo_votos_habiles.json")
PARTY_INDEX_FILE = os.path.join(OUTPUT_DIR, "idx_codigo_nombre_partido.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_ubigeo_votos_habiles_map() -> Dict[str, int]:
    """Loads the pre-computed cleaned static baseline voter matrix."""
    if not os.path.exists(VOTOS_HABILES_FILE):
        print(f"[-] Environment Warning: '{VOTOS_HABILES_FILE}' was not located.")
        print("    Pipeline will fall back to using algebraic estimation coefficients.")
        return {}
        
    print(f"[+] Loading baseline voter metrics from {VOTOS_HABILES_FILE}...")
    try:
        with open(VOTOS_HABILES_FILE, "r", encoding="utf-8") as f:
            votos_map = json.load(f)
        return {str(k).strip(): int(v) for k, v in votos_map.items()}
    except Exception as e:
        print(f"[-] Error parsing explicit voter baseline data map: {e}")
        return {}

def load_all_worker_data() -> List[Dict[str, Any]]:
    """Scans and reads all operational worker JSONL logs inside the log directory."""
    records = []
    search_path = os.path.join(LOG_DIR, "onpe_combined_results_worker_*.jsonl")
    target_files = glob.glob(search_path)
    
    if not target_files:
        print(f"[-] No results files found matching pattern: {search_path}")
        return []
        
    print(f"[+] Found {len(target_files)} worker files to aggregate.")
    for file_path in target_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
        except Exception as e:
            print(f"[-] Error reading file {file_path}: {e}")
            
    return records

def build_base_district_metrics(
    raw_records: List[Dict[str, Any]], 
    baseline_votos_map: Dict[str, int]
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    Calculates district layer variables, integrates the baseline explicit votos_habiles layer,
    and extracts a flat master index mapping party codes to party names.
    """
    districts = {}
    party_name_index = {}  # Map: code_id -> clean_party_name
    
    for record in raw_records:
        ubigeo = str(record.get("ubigeo", "")).strip()
        meta = record.get("meta", {}) or {}
        totales = record.get("totales", {}) or {}
        participantes = record.get("participantes", []) or []
        
        dep_name = meta.get("dep", "UNKNOWN").strip().upper()
        prov_name = meta.get("prov", "UNKNOWN").strip().upper()
        dist_name = meta.get("dist", "UNKNOWN").strip().upper()
        ambito = str(record.get("ambito", "1")).strip()
        
        actas_total = int(totales.get("actas_total", 0))
        actas_contabilizadas = int(totales.get("actas_contabilizadas", 0))
        votos_emitidos = int(totales.get("votos_emitidos", 0))
        votos_validos = int(totales.get("votos_validos", 0))
        
        try:
            pct_part = float(totales.get("pct_participacion", 0.0))
        except (ValueError, TypeError):
            pct_part = 0.0
            
        try:
            pct_actas = float(totales.get("pct_actas_contabilizadas", 0.0))
        except (ValueError, TypeError):
            pct_actas = 0.0

        # Votos Hábiles Explicit Matching Layer
        if ubigeo in baseline_votos_map:
            votos_habiles = baseline_votos_map[ubigeo]
        else:
            if pct_part > 0:
                votos_habiles = int(round(votos_emitidos / (pct_part / 100.0)))
            else:
                votos_habiles = votos_emitidos

        # Re-map candidate structures to a flat party token index tracking map
        votos_partidos = {}
        for p in participantes:
            p_id = str(p.get("id", "")).strip()
            # CHANGED: 'partido' matches the actual key inside your logs
            p_name = str(p.get("partido", "")).strip()
            
            if p_id:
                votos_partidos[p_id] = int(p.get("votos", 0))
                
                # Dynamically compile political party text signatures if not yet tracked
                if p_id not in party_name_index and p_name:
                    party_name_index[p_id] = p_name

        districts[ubigeo] = {
            "ubigeo": ubigeo,
            "ambito": ambito,
            "departamento": dep_name,
            "provincia": prov_name,
            "distrito": dist_name,
            "actas_total": actas_total,
            "actas_contabilizadas": actas_contabilizadas,
            "pct_actas_contabilizadas": pct_actas,
            "pct_participacion": pct_part,
            "votos_emitidos": votos_emitidos,
            "votos_validos": votos_validos,
            "votos_habiles": votos_habiles,
            "votos_partidos": votos_partidos
        }
        
    return districts, party_name_index

def roll_up_aggregation(districts: Dict[str, Dict[str, Any]], group_by_keys: List[str]) -> List[Dict[str, Any]]:
    """Generic aggregation engine that builds upper waterfall layers from the ground up."""
    aggregates = {}
    
    for dist in districts.values():
        group_val = tuple(dist[k] for k in group_by_keys)
        
        if group_val not in aggregates:
            aggregates[group_val] = {
                "actas_total": 0,
                "actas_contabilizadas": 0,
                "votos_emitidos": 0,
                "votos_validos": 0,
                "votos_habiles": 0,
                "votos_partidos": {}
            }
            
        tgt = aggregates[group_val]
        tgt["actas_total"] += dist["actas_total"]
        tgt["actas_contabilizadas"] += dist["actas_contabilizadas"]
        tgt["votos_emitidos"] += dist["votos_emitidos"]
        tgt["votos_validos"] += dist["votos_validos"]
        tgt["votos_habiles"] += dist["votos_habiles"]
        
        for p_id, v_count in dist["votos_partidos"].items():
            tgt["votos_partidos"][p_id] = tgt["votos_partidos"].get(p_id, 0) + v_count

    output_list = []
    for group_val, data in aggregates.items():
        h_votes = data["votos_habiles"]
        t_actas = data["actas_total"]
        
        pct_part = round((data["votos_emitidos"] / h_votes) * 100, 3) if h_votes > 0 else 0.0
        pct_actas = round((data["actas_contabilizadas"] / t_actas) * 100, 3) if t_actas > 0 else 0.0
        
        row = {}
        for idx, k in enumerate(group_by_keys):
            row[k] = group_val[idx]
            
        row.update({
            "actas_total": data["actas_total"],
            "actas_contabilizadas": data["actas_contabilizadas"],
            "pct_actas_contabilizadas": pct_actas,
            "pct_participacion": pct_part,
            "votos_emitidos": data["votos_emitidos"],
            "votos_validos": data["votos_validos"],
            "votos_habiles": data["votos_habiles"],
            "votos_partidos": data["votos_partidos"]
        })
        output_list.append(row)
        
    return output_list

def main():
    baseline_votos_map = load_ubigeo_votos_habiles_map()
    
    raw_data = load_all_worker_data()
    if not raw_data:
        return

    # 1. Base Layer Integration & Party Extraction
    district_map, party_name_index = build_base_district_metrics(raw_data, baseline_votos_map)
    district_list = list(district_map.values())
    
    # 2. Sequential Higher Rollups via Cascade Waterfall
    provincia_list = roll_up_aggregation(district_map, ["ambito", "departamento", "provincia"])
    departamento_list = roll_up_aggregation(district_map, ["ambito", "departamento"])
    ambito_list = roll_up_aggregation(district_map, ["ambito"])

    # File Export Target Matrix Layout
    output_targets = {
        "agg_distrital.json": district_list,
        "agg_provincial.json": provincia_list,
        "agg_departamental.json": departamento_list,
        "agg_ambito.json": ambito_list
    }
    
    print("\n[+] Exporting structural hierarchy aggregate tables to processed_results/ ...")
    for file_name, data_payload in output_targets.items():
        full_path = os.path.join(OUTPUT_DIR, file_name)
        with open(full_path, "w", encoding="utf-8") as out:
            json.dump(data_payload, out, ensure_ascii=False, indent=2)
        print(f" -> Generated {full_path} | Rows: {len(data_payload)}")

    # 3. Export Political Party Relational Index Reference File
    print(f"\n[+] Exporting political party reference index...")
    with open(PARTY_INDEX_FILE, "w", encoding="utf-8") as pf:
        json.dump(party_name_index, pf, ensure_ascii=False, indent=2)
    print(f" -> Generated {PARTY_INDEX_FILE} | Indexed Parties: {len(party_name_index)}")

    # --- CROSS CHECK DATA SHEET COMPLIANCE RUN ---
    sum_dist_voters = sum(d["votos_habiles"] for d in district_list)
    sum_prov_voters = sum(p["votos_habiles"] for p in provincia_list)
    sum_dept_voters = sum(m["votos_habiles"] for m in departamento_list)
    sum_ambi_voters = sum(a["votos_habiles"] for a in ambito_list)
    
    print("\n================== PIPELINE CONSISTENCY VERIFICATION DIAGNOSTIC ==================")
    print(f" Clean Baseline Map Registered Sum:   {sum(baseline_votos_map.values()):,}")
    print("----------------------------------------------------------------------------------")
    print(f" District Layer (agg_distrital)   Total Votos Hábiles:  {sum_dist_voters:,}")
    print(f" Provincia Layer (agg_provincial) Total Votos Hábiles:  {sum_prov_voters:,}")
    print(f" Dept Layer (agg_departamental)   Total Votos Hábiles:  {sum_dept_voters:,}")
    print(f" Ámbito Layer (agg_ambito)         Total Votos Hábiles:  {sum_ambi_voters:,}")
    print("----------------------------------------------------------------------------------")
    
    if sum_dist_voters == sum_prov_voters == sum_dept_voters == sum_ambi_voters:
        print("[✓] STRUCTURAL INTEGRITY PASSED: Mathematical balances reconcile across all matrix layers.")
    else:
        print("[!] STRUCTURAL INTEGRITY WARNING: Numerical variance detected during data path rollup calculation.")

if __name__ == "__main__":
    main()