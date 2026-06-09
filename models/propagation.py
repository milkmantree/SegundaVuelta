import json
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from paths import ROUND1, ROUND2

# Fallback participation rate applied to exterior districts when no R1 data
# can be inferred. Exterior turnout is ~25–34% vs ~73% domestic, so without
# this correction the model fabricates ~3–4× too many pending overseas votes.
_EXT_PART_FALLBACK = 0.32
_R1_DEPT_PATH = str(ROUND1 / "agg_departamental.json")


def _load_r1_ext_part_rates():
    """Return dict: exterior dept name → R1 participation rate (emit/hab)."""
    try:
        rows = json.load(open(_R1_DEPT_PATH, encoding="utf-8"))
        rates = {}
        for r in rows:
            if str(r.get("ambito", "1")) != "2":
                continue
            hab  = r.get("votos_habiles",  0)
            emit = r.get("votos_emitidos", 0)
            if hab > 0:
                rates[r.get("departamento", "")] = emit / hab
        return rates
    except Exception:
        return {}


def preprocess_electoral_data(json_filepath, party_mapping_filepath):
    """Loads raw aggregated distrital JSON data, flattens the nested party votes,

    and isolates valid candidate columns by excluding blank and null codes.
    """
    print("📥 Loading and flattening raw electoral data...")
    df_raw = pd.read_json(json_filepath)

    if "votos_partidos" in df_raw.columns:
        df_parties = pd.json_normalize(df_raw["votos_partidos"])
        df_flat = pd.concat(
            [df_raw.drop(columns=["votos_partidos"]), df_parties], axis=1
        )
    else:
        df_flat = df_raw.copy()

    with open(party_mapping_filepath, "r") as f:
        party_mapping = json.load(f)

    candidate_cols = [
        code for code in party_mapping.keys() if code not in ["80", "81"]
    ]

    for col in candidate_cols:
        if col not in df_flat.columns:
            df_flat[col] = 0
        else:
            df_flat[col] = df_flat[col].fillna(0).astype(int)

    print(
        f"✅ Preprocessing complete: Matrix has {df_flat.shape[0]} rows and {len(candidate_cols)} candidate IDs isolated.\n"
    )
    return df_flat, candidate_cols, party_mapping


def run_dynamic_stratified_projection(
    df, candidate_cols, party_mapping, z_score=1.96, generate_html=True
):
    """Executes an election projection evaluating stability DYNAMICALLY per district.

    Falls back row-by-row to provincial or departmental trends if a district
    has < 50% reporting AND < 14 tables counted.
    """
    print("⚡ Initiating Dynamic Per-District Stratification Engine...")

    # -----------------------------------------------------------------
    # 1. Precalculate Macro-Tier Fallback Profiles (Trends)
    # -----------------------------------------------------------------
    # Provincial Trend Blends
    prov_totals = df.groupby("provincia")[
        ["votos_validos", "votos_emitidos"] + candidate_cols
    ].sum()
    prov_valid = prov_totals["votos_validos"].to_dict()
    prov_emitted = prov_totals["votos_emitidos"].to_dict()

    # Departmental Trend Blends (Absolute safe fallback)
    dept_totals = df.groupby("departamento")[
        ["votos_validos", "votos_emitidos"] + candidate_cols
    ].sum()
    dept_valid = dept_totals["votos_validos"].to_dict()
    dept_emitted = dept_totals["votos_emitidos"].to_dict()

    # Total tables counted per macro-tier for pooled variance DoF
    prov_tables = df.groupby("provincia")["actas_contabilizadas"].sum().to_dict()
    dept_tables = df.groupby("departamento")["actas_contabilizadas"].sum().to_dict()

    # -----------------------------------------------------------------
    # 2. Evaluate Stability and Map Fallbacks Row-by-Row
    # -----------------------------------------------------------------
    df["pct_reporting"] = df["actas_contabilizadas"] / df["actas_total"]
    df["rule_1_passed"] = df["pct_reporting"] >= 0.50
    df["rule_2_passed"] = df["actas_contabilizadas"] >= 14
    df["is_stable"] = df["rule_1_passed"] | df["rule_2_passed"]

    # Drop districts with no actas at all — they contribute nothing and cause 0/0 NaN
    df = df[df["actas_total"] > 0].copy()

    # Global weights and infrastructure metrics
    N_total = df["actas_total"].sum()
    df["W_h"] = df["actas_total"] / N_total
    df["f_h"] = df["actas_contabilizadas"] / df["actas_total"]
    df["FPC"] = 1 - df["f_h"]
    df["E_pending_h"] = df["votos_habiles"] * (1 - df["f_h"])

    # Exterior participation rate correction.
    # E_pending_h represents registered voters in pending precincts. For
    # domestic districts the downstream r_valid = valid/emitted implicitly
    # captures participation because emitted ≈ hab × part_rate. For exterior,
    # ONPE does not report votos_emitidos proportionally (only ~7–8% of
    # habilitados have voted so far), so r_valid ≈ 0.94 (valid/emitted) and
    # does NOT include the participation rate. Without correction the model
    # overcounts exterior pending votes by ~1/part_rate ≈ 3–4×.
    # Fix: scale E_pending_h by the expected exterior participation rate.
    # Source: R1 per-department rates from first_round_agg_results/; fall back
    # to _EXT_PART_FALLBACK (32%) for any exterior dept not in that file.
    if "ambito" in df.columns:
        r1_ext_rates = _load_r1_ext_part_rates()
        is_ext  = df["ambito"].astype(str) == "2"
        mapped  = df["departamento"].map(r1_ext_rates)
        factor  = np.where(is_ext, mapped.fillna(_EXT_PART_FALLBACK), 1.0)
        df["E_pending_h"] = df["E_pending_h"] * factor

    # -----------------------------------------------------------------
    # 3. Dynamic Mathematical Modeling Loop
    # -----------------------------------------------------------------
    total_projected_valid_votes = df["votos_validos"].sum()
    projections = {}

    # Pre-calculate projected valid vectors dynamically per row
    pending_valid_shares = []
    for idx, row in df.iterrows():
        if row["is_stable"] and row["votos_emitidos"] > 0:
            r_valid = row["votos_validos"] / row["votos_emitidos"]
        elif prov_emitted.get(row["provincia"], 0) > 0:
            r_valid = (
                prov_valid[row["provincia"]] / prov_emitted[row["provincia"]]
            )
        else:
            r_valid = (
                dept_valid[row["departamento"]]
                / dept_emitted[row["departamento"]]
                if dept_emitted.get(row["departamento"], 0) > 0
                else 0
            )

        pending_valid_votes = row["E_pending_h"] * r_valid
        pending_valid_shares.append(pending_valid_votes)
        total_projected_valid_votes += pending_valid_votes

    df["projected_pending_valid"] = pending_valid_shares

    # Calculate Candidate Shares & Variance
    for candidate in candidate_cols:
        observed_total_votes = df[candidate].sum()
        estimated_pending_votes = 0
        national_variance = 0

        # Track tier assignments for execution logging summary
        tier_counts = {"district": 0, "provincia": 0, "departamento": 0}

        for idx, row in df.iterrows():
            # Determine dynamic share prior (p_h) and Sample Size (n_pooled)
            if row["is_stable"] and row["votos_validos"] > 0:
                p_h = row[candidate] / row["votos_validos"]
                n_pooled = row["actas_contabilizadas"]
                tier_counts["district"] += 1
            else:
                # Local baseline failed, look to Provincia trend
                p_prov_denom = prov_valid.get(row["provincia"], 0)
                if p_prov_denom > 0:
                    p_h = prov_totals.loc[row["provincia"], candidate] / p_prov_denom
                    n_pooled = prov_tables.get(row["provincia"], 0)
                    tier_counts["provincia"] += 1
                else:
                    # Provincial baseline failed, look to Departamento trend
                    p_dept_denom = dept_valid.get(row["departamento"], 0)
                    p_h = (
                        dept_totals.loc[row["departamento"], candidate]
                        / p_dept_denom
                        if p_dept_denom > 0
                        else 0
                    )
                    n_pooled = dept_tables.get(row["departamento"], 0)
                    tier_counts["departamento"] += 1

            # Accumulate pending projected votes
            estimated_pending_votes += row["projected_pending_valid"] * p_h

            # Dynamic Variance Mitigation (Bessel's correction adjustment)
            bessels_correction = n_pooled - 1
            if bessels_correction > 0:
                variance_term = (
                    (row["W_h"] ** 2)
                    * row["FPC"]
                    * ((p_h * (1 - p_h)) / bessels_correction)
                )
                national_variance += variance_term

        projected_votes = observed_total_votes + estimated_pending_votes
        margin_of_error = z_score * np.sqrt(max(0.0, national_variance))

        projected_share = (
            (projected_votes / total_projected_valid_votes) * 100
            if total_projected_valid_votes > 0
            else 0
        )
        moe_share = margin_of_error * 100
        party_name = party_mapping.get(candidate, f"PARTY {candidate}")

        projections[party_name] = {
            "ID": candidate,
            "Observed Votes": int(observed_total_votes),
            "Projected Votes": int(projected_votes),
            "Projected Share (%)": round(projected_share, 2),
            "MOE (%)": round(moe_share, 2),
            "Lower Bound Share (%)": round(max(0, projected_share - moe_share), 2),
            "Upper Bound Share (%)": round(projected_share + moe_share, 2),
        }

    print(
        f"✅ Dynamic calculations completed. Resolution footprint summary: {tier_counts}"
    )

    results_df = pd.DataFrame(projections).T
    results_df.index.name = "Political Organization"

    if generate_html:
        create_interactive_dashboard(results_df, "Dynamic Per-District Stratum")
    return results_df.sort_values(by="Projected Share (%)", ascending=False)


def create_interactive_dashboard(results_df, resolved_tier):
    """Generates an interactive Plotly HTML file containing the results chart."""
    plot_df = results_df.sort_values(by="Projected Share (%)", ascending=True)

    candidates = plot_df.index.tolist()
    shares = plot_df["Projected Share (%)"].tolist()
    moe = plot_df["MOE (%)"].tolist()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=shares,
            y=candidates,
            orientation="h",
            text=[f"{s}%" for s in shares],
            textposition="auto",
            error_x=dict(type="data", array=moe, visible=True, color="#EF553B"),
            marker=dict(
                color="#1F77B4", line=dict(color="rgba(0, 0, 0, 0.3)", width=1)
            ),
            hovertemplate="<b>Party:</b> %{y}<br>"
            + "<b>Projected Share:</b> %{x}%<br>"
            + "<b>Margin of Error:</b> ±%{error_x.array}%<extra></extra>",
        )
    )

    fig.update_layout(
        title={
            "text": f"<b>Dynamic Stratified Election Projection</b><br><span style='font-size:12px;color:gray;'>Resolved Stratification Tier: <b>{resolved_tier.upper()}</b> | 95% Confidence Intervals</span>",
            "y": 0.95,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top",
        },
        xaxis_title="Projected Vote Share (% of Valid Votes)",
        yaxis_title="Candidates / Political Organizations",
        template="plotly_white",
        height=max(500, len(candidates) * 22),
        margin=dict(l=300, r=50, t=100, b=50),
        xaxis=dict(range=[0, min(100, max(shares) + max(moe) + 5)]),
    )

    filename = str(ROUND2.parent.parent / "election_projection_dashboard.html")
    pio.write_html(fig, file=filename, auto_open=False)
    print(f"🌐 Interactive dashboard exported successfully as '{filename}'")


def get_projection_data_by_dept(data_path=None, mapping_path=None, z_score=1.96):
    """Returns per-department projection results as a JSON-serializable dict."""
    import io, contextlib

    if data_path is None:
        data_path = str(ROUND2 / "agg_distrital.json")
    if mapping_path is None:
        mapping_path = str(ROUND2 / "idx_codigo_nombre_partido.json")

    if not os.path.exists(data_path) or not os.path.exists(mapping_path):
        return {"error": "Data files not found", "departments": {}}

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        df_flat, candidate_cols, party_mapping = preprocess_electoral_data(
            data_path, mapping_path
        )

    departments = {}
    for dept_name, dept_df in df_flat.groupby("departamento"):
        dept_df    = dept_df.copy()
        n_total    = len(dept_df)
        n_reported = int((dept_df["actas_contabilizadas"] > 0).sum())
        pct_cover  = round(n_reported / n_total * 100, 2) if n_total > 0 else 0.0

        with contextlib.redirect_stdout(sink):
            results_df = run_dynamic_stratified_projection(
                dept_df, candidate_cols, party_mapping, z_score, generate_html=False
            )

        # Head-to-head projected shares (exclude blancos/nulos from denominator)
        cand_rows = [
            (name, row)
            for name, row in results_df.iterrows()
            if str(row["ID"]) not in ("80", "81")
        ]
        total_proj = sum(int(row["Projected Votes"]) for _, row in cand_rows) or 1

        # Infer total projected valid votes from the first candidate to scale MOE
        # projected_share (from model) = proj_votes / total_valid → total_valid = proj_votes / (share/100)
        first_ps  = float(cand_rows[0][1]["Projected Share (%)"]) if cand_rows else 1.0
        first_pv  = int(cand_rows[0][1]["Projected Votes"])       if cand_rows else 1
        total_val = (first_pv / (first_ps / 100.0)) if first_ps > 0 else total_proj
        h2h_scale = total_val / total_proj  # ~1.0 for 2-party, slightly >1 if blancos present

        parties = []
        for name, row in cand_rows:
            pid        = str(row["ID"])
            proj_votes = int(row["Projected Votes"])
            proj_head  = round(proj_votes / total_proj * 100, 2)
            valid_sh   = round(float(row["Projected Share (%)"]), 2)
            moe        = round(float(row["MOE (%)"]) * h2h_scale, 2)
            parties.append({
                "id":             pid,
                "name":           name,
                "observed_votes": int(row["Observed Votes"]),
                "projected_votes": proj_votes,
                "projected_share": proj_head,
                "valid_share":    valid_sh,
                "moe":            moe,
                "lower_bound":    round(max(0.0,   proj_head - moe), 2),
                "upper_bound":    round(min(100.0, proj_head + moe), 2),
            })

        # Compute tier_counts: how many districts resolved at each fallback level
        prov_valid_d = dept_df.groupby("provincia")["votos_validos"].sum()
        has_prov = dept_df["provincia"].map(lambda p: float(prov_valid_d.get(p, 0.0)) > 0)
        tier_district = int(dept_df["is_stable"].sum())
        tier_prov     = int((~dept_df["is_stable"] & has_prov).sum())
        tier_dept_n   = n_total - tier_district - tier_prov

        departments[dept_name] = {
            "n_reported":   n_reported,
            "n_total":      n_total,
            "pct_coverage": pct_cover,
            "parties": sorted(parties, key=lambda x: x["projected_share"], reverse=True),
            "tier_counts": {
                "district":    tier_district,
                "provincia":   tier_prov,
                "departamento": tier_dept_n,
            },
        }

    return {
        "model":            "dynamic_stratified_propagation",
        "confidence_level": "95%",
        "departments":      departments,
    }


def get_projection_data(data_path=None, mapping_path=None, z_score=1.96):
    """Returns projection results as a JSON-serializable dict for the web API."""
    if data_path is None:
        data_path = str(ROUND2 / "agg_distrital.json")
    if mapping_path is None:
        mapping_path = str(ROUND2 / "idx_codigo_nombre_partido.json")

    if not os.path.exists(data_path) or not os.path.exists(mapping_path):
        return {"error": "Data files not found", "parties": []}

    df_flat, candidate_cols, party_mapping = preprocess_electoral_data(data_path, mapping_path)
    results_df = run_dynamic_stratified_projection(
        df_flat, candidate_cols, party_mapping, z_score, generate_html=False
    )

    parties_data = []
    for name, row in results_df.iterrows():
        parties_data.append({
            "name": name,
            "id": str(row["ID"]),
            "observed_votes": int(row["Observed Votes"]),
            "projected_votes": int(row["Projected Votes"]),
            "projected_share": float(row["Projected Share (%)"]),
            "moe": float(row["MOE (%)"]),
            "lower_bound": float(row["Lower Bound Share (%)"]),
            "upper_bound": float(row["Upper Bound Share (%)"]),
        })

    return {
        "model": "dynamic_stratified_propagation",
        "z_score": z_score,
        "confidence_level": "95%",
        "parties": sorted(parties_data, key=lambda x: x["projected_share"], reverse=True),
    }


if __name__ == "__main__":
    DATA_PATH = str(ROUND2 / "agg_distrital.json")
    MAPPING_PATH = str(ROUND2 / "idx_codigo_nombre_partido.json")

    if os.path.exists(DATA_PATH) and os.path.exists(MAPPING_PATH):
        processed_results, candidate_columns, party_mapping_dict = (
            preprocess_electoral_data(DATA_PATH, MAPPING_PATH)
        )

        projection_summary = run_dynamic_stratified_projection(
            df=processed_results,
            candidate_cols=candidate_columns,
            party_mapping=party_mapping_dict,
            z_score=1.96,
        )

        print("\n🏆 Final Election Projection Summary (Sorted by Share):")
        print(
            projection_summary[
                [
                    "ID",
                    "Observed Votes",
                    "Projected Votes",
                    "Projected Share (%)",
                    "MOE (%)",
                ]
            ].head(10)
        )
    else:
        print("❌ Missing workspace data payloads. Check file paths.")