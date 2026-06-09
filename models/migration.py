"""
Vote Migration Model — Segunda Vuelta Projection
=================================================
Stages:
  1. Data ingestion & volume-based significance filtering
  2. Hellinger-distance Ward clustering of orphan candidates
  3. Hierarchical fallback circuit (province → department → global)
  4. Simplex-constrained WLS vote migration regression
  5. FPC ratio estimator with department-clustered sandwich SE

Entry points:
  build_cluster_map()   — run once, reads first-round data, saves cluster definitions
  get_migration_data()  — call live, returns JSON-serializable projection dict
"""

import json
import math
import os
import time
import warnings

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy import stats as sp_stats

# ── Paths ─────────────────────────────────────────────────────────────────────
FIRST_ROUND_DISTRITAL  = "first_round_agg_results/agg_distrital.json"
FIRST_ROUND_MAPPING    = "first_round_agg_results/idx_codigo_nombre_partido.json"
CLUSTER_MAP_PATH       = "inputs/migration_cluster_map.json"
SECOND_ROUND_DISTRITAL = "processed_results/agg_distrital.json"
SECOND_ROUND_MAPPING   = "processed_results/idx_codigo_nombre_partido.json"

# ── Constants ─────────────────────────────────────────────────────────────────
BLANK_NULL       = {"80", "81"}
SIG_THRESHOLD    = 0.015   # 1.5% of scope emitted votes for candidate to enter clustering
MIN_DISTRICTS    = 8       # T — minimum districts for stable local covariance
PSI              = {"province": 1.0, "department": 0.75, "global": 0.40}

_META_COLS = {
    "ubigeo", "ambito", "departamento", "provincia", "distrito",
    "actas_total", "actas_contabilizadas", "pct_actas_contabilizadas",
    "pct_participacion", "votos_emitidos", "votos_validos", "votos_habiles",
}


# ══════════════════════════════════════════════════════════════════════════════
# Data loading helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_df(distrital_path, mapping_path):
    df = pd.read_json(distrital_path)
    with open(mapping_path, encoding="utf-8") as f:
        mapping = json.load(f)
    parties_df = pd.json_normalize(df["votos_partidos"])
    df = pd.concat([df.drop(columns=["votos_partidos"]), parties_df], axis=1)
    for pid in mapping:
        if pid not in df.columns:
            df[pid] = 0.0
        else:
            df[pid] = df[pid].fillna(0.0).astype(float)
    return df, mapping


def _determine_finalists(df, mapping):
    """Top 2 candidates by total valid votes — determined dynamically, never hardcoded."""
    totals = {
        pid: float(df[pid].sum())
        for pid in mapping
        if pid not in BLANK_NULL and pid in df.columns
    }
    return [pid for pid, _ in sorted(totals.items(), key=lambda x: x[1], reverse=True)[:2]]


# ══════════════════════════════════════════════════════════════════════════════
# Stage 2: Hellinger-distance Ward clustering
# ══════════════════════════════════════════════════════════════════════════════

def _cluster_scope(scope_df, finalists):
    """
    For a set of districts, compute candidate groupings via Hellinger-based Ward clustering.

    Uses sqrt-transformed share vectors so that Euclidean (Ward) distance equals
    the Hellinger distance up to a constant — mathematically correct.

    Returns a cluster-info dict or None if data is insufficient.
    """
    n = len(scope_df)
    if n == 0:
        return None

    orphan_cols = [
        c for c in scope_df.columns
        if c not in _META_COLS and c not in BLANK_NULL and c not in finalists
    ]

    total_emitted = float(scope_df["votos_emitidos"].sum())
    if total_emitted <= 0:
        return None

    # Stage 1 significance filter
    significant, tail = [], []
    for c in orphan_cols:
        share = float(scope_df[c].sum()) / total_emitted
        (significant if share >= SIG_THRESHOLD else tail).append(c)

    if not significant:
        return {
            "n_districts": n, "significant_orphans": [],
            "tail": orphan_cols, "clusters": [],
            "n_clusters": 0, "candidate_to_cluster": {},
        }

    if len(significant) == 1:
        return {
            "n_districts": n, "significant_orphans": significant,
            "tail": tail,
            "clusters": [{"id": 0, "members": significant}],
            "n_clusters": 1,
            "candidate_to_cluster": {significant[0]: 0},
        }

    # Compute share of each significant candidate in the "active orphan vote" per district
    orphan_totals = scope_df[significant].sum(axis=1).values  # (n_districts,)

    # sqrt-transformed share matrix: shape (n_candidates, n_districts)
    # Ward's method on Euclidean distances of sqrt-vectors = Hellinger clustering
    n_sig = len(significant)
    share_sqrt = np.zeros((n_sig, n))
    for i, c in enumerate(significant):
        with np.errstate(invalid="ignore", divide="ignore"):
            raw_shares = np.where(orphan_totals > 0,
                                  scope_df[c].values / orphan_totals, 0.0)
        share_sqrt[i] = np.sqrt(np.clip(raw_shares, 0.0, 1.0))

    k = min(n_sig, max(1, int(math.sqrt(n))), 6)

    try:
        Z = linkage(share_sqrt, method="ward")
        labels = fcluster(Z, k, criterion="maxclust")
    except Exception:
        labels = np.ones(n_sig, dtype=int)

    c_to_cluster = {}
    members_by_cluster = {}
    for i, c in enumerate(significant):
        cid = int(labels[i]) - 1  # 0-indexed
        c_to_cluster[c] = cid
        members_by_cluster.setdefault(cid, []).append(c)

    clusters = [
        {"id": cid, "members": mems}
        for cid, mems in sorted(members_by_cluster.items())
    ]

    return {
        "n_districts": n,
        "significant_orphans": significant,
        "tail": tail,
        "clusters": clusters,
        "n_clusters": len(clusters),
        "candidate_to_cluster": c_to_cluster,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Stage 1+2 public entry point: build_cluster_map
# ══════════════════════════════════════════════════════════════════════════════

def build_cluster_map(save_path=CLUSTER_MAP_PATH):
    """
    Build static cluster definitions from first-round data.

    Computes province/department/global Hellinger-based candidate groupings
    and writes the result to inputs/migration_cluster_map.json.
    """
    print("Building vote migration cluster map from first-round data...")
    df, mapping = _load_df(FIRST_ROUND_DISTRITAL, FIRST_ROUND_MAPPING)
    finalists = _determine_finalists(df, mapping)
    print(f"  Finalists: {finalists} → {[mapping[f] for f in finalists]}")

    # Global level
    print("  Computing global clusters...")
    global_info = _cluster_scope(df, finalists)

    # Department level
    print("  Computing per-department clusters...")
    departments = {}
    dept_n = df.groupby("departamento").size().to_dict()
    for dept, ddf in df.groupby("departamento"):
        info = _cluster_scope(ddf, finalists)
        if info:
            departments[dept] = info

    # Province level
    print("  Computing per-province clusters...")
    provinces = {}
    for (dept, prov), pdf in df.groupby(["departamento", "provincia"]):
        n = len(pdf)
        if n >= MIN_DISTRICTS:
            info = _cluster_scope(pdf, finalists)
            if info:
                info["department"] = dept
                info["fallback"] = None
                provinces[prov] = info
        else:
            fb = "department" if dept_n.get(dept, 0) >= MIN_DISTRICTS else "global"
            provinces[prov] = {
                "n_districts": n, "department": dept, "fallback": fb,
                "significant_orphans": [], "tail": [], "clusters": [],
                "n_clusters": 0, "candidate_to_cluster": {},
            }

    result = {
        "_meta": {
            "finalists": finalists,
            "finalist_names": {f: mapping[f] for f in finalists},
            "significance_threshold": SIG_THRESHOLD,
            "min_districts_for_local": MIN_DISTRICTS,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "global": global_info,
        "departments": departments,
        "provinces": provinces,
    }

    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    n_full  = sum(1 for p in provinces.values() if not p.get("fallback"))
    n_dept  = sum(1 for p in provinces.values() if p.get("fallback") == "department")
    n_glob  = sum(1 for p in provinces.values() if p.get("fallback") == "global")
    g_k     = global_info["n_clusters"] if global_info else 0
    print(f"  Saved → {save_path}")
    print(f"  Provinces: {n_full} local | {n_dept} dept-fallback | {n_glob} global-fallback")
    print(f"  Departments: {len(departments)} | Global clusters: {g_k}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3: Hierarchical fallback — effective cluster info lookup
# ══════════════════════════════════════════════════════════════════════════════

def _effective_cluster_info(cluster_map, province, department):
    """Return (cluster_info, fallback_level_str) with province → dept → global fallback."""
    prov_info = cluster_map["provinces"].get(province, {})
    if prov_info and not prov_info.get("fallback"):
        return prov_info, "province"
    dept_info = cluster_map["departments"].get(department)
    if dept_info:
        return dept_info, "department"
    return cluster_map["global"], "global"


# ══════════════════════════════════════════════════════════════════════════════
# Stage 4: Design matrix + Simplex-constrained WLS
# ══════════════════════════════════════════════════════════════════════════════

def _build_x(r1_row, finalist, cluster_info, normaliser=None):
    """
    Build design-matrix row in share space.

    Each element = group's R1 vote count / normaliser (R1 total valid votes).
    If normaliser is None or 0, returns raw counts (used internally before dividing).
    """
    raw = [float(r1_row.get(finalist, 0.0))]
    for cl in cluster_info.get("clusters", []):
        raw.append(sum(float(r1_row.get(m, 0.0)) for m in cl["members"]))
    raw.append(sum(float(r1_row.get(c, 0.0)) for c in cluster_info.get("tail", [])))
    x = np.array(raw, dtype=float)
    if normaliser and normaliser > 0:
        x = x / normaliser
    return x


def _fit_wls(X_shares, y_shares, weights):
    """
    Share-space box-constrained WLS via scipy lsq_linear.

    X_shares: each feature column is group's R1 vote share of district total valid.
    y_shares: each target is finalist's R2 vote share of district total valid.
    Constraint: 0 ≤ beta_i ≤ 1  (Conservation of Mass — no group can transfer
    more than 100% or negative votes).  The simplex sum(beta)≤1 is NOT imposed
    on raw-count features; the share formulation ensures predictions stay in [0,1].

    Uses scipy.optimize.lsq_linear (active-set, globally convergent for QP).
    """
    from scipy.optimize import lsq_linear

    n_p = X_shares.shape[1]
    if n_p == 0 or len(y_shares) < 2:
        return np.zeros(n_p)

    w_sqrt = np.sqrt(np.asarray(weights, dtype=float))
    w_sqrt /= w_sqrt.sum()  # normalise so large districts don't dominate scale

    A = X_shares * w_sqrt[:, np.newaxis]
    b = y_shares * w_sqrt

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = lsq_linear(A, b, bounds=(0.0, 1.0), method="bvls",
                         tol=1e-12, max_iter=2000)

    return np.clip(res.x, 0.0, 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# Stage 4+5: Per-finalist projection with FPC ratio estimator
# ══════════════════════════════════════════════════════════════════════════════

def _project_finalist(r1_df, r2_df, cluster_map, finalists, finalist_idx):
    """
    Fit regression and project for one finalist.

    Regression pools: department-level WLS if dept has ≥ MIN_DISTRICTS reported
    districts; otherwise global pool (using global cluster map).
    Both pools guarantee consistent design-matrix dimensions within each pool.
    """
    finalist = finalists[finalist_idx]

    # Count reported districts per department (needed to decide pool assignment)
    dept_reported = {}
    for ubigeo in r1_df.index:
        if ubigeo in r2_df.index and r2_df.loc[ubigeo, "actas_contabilizadas"] > 0:
            dept = r1_df.loc[ubigeo, "departamento"]
            dept_reported[dept] = dept_reported.get(dept, 0) + 1

    # Observed aggregate stats (from R2) — raw counts only; the pending fraction
    # of partial districts is handled later by a separate projection loop (option 2).
    obs_finalist_raw = 0.0
    obs_r2_valid_sum = 0.0
    obs_r2_emit_sum  = 0.0
    obs_r1_valid_sum = 0.0
    obs_r1_emit_sum  = 0.0
    for ubigeo in r1_df.index:
        if ubigeo in r2_df.index and r2_df.loc[ubigeo, "actas_contabilizadas"] > 0:
            r2_row  = r2_df.loc[ubigeo]
            obs_finalist_raw += float(r2_row.get(finalist, 0.0))
            obs_r2_valid_sum += float(r2_row.get("votos_validos", 0.0))
            obs_r2_emit_sum  += float(r2_row.get("votos_emitidos", 0.0))
            obs_r1_valid_sum += float(r1_df.loc[ubigeo, "votos_validos"])
            obs_r1_emit_sum  += float(r1_df.loc[ubigeo, "votos_emitidos"])

    # Share normalisation: observed average ratio of R2 valid / R1 valid
    r2_over_r1_valid = (obs_r2_valid_sum / obs_r1_valid_sum
                        if obs_r1_valid_sum > 0 else 0.90)
    r2_valid_ratio   = (obs_r2_valid_sum / obs_r2_emit_sum
                        if obs_r2_emit_sum > 0 else 0.87)

    # Assign each district to its pool and build SHARE-SPACE features.
    # X_shares[j] = group_j_R1_votes / R1_total_valid (dimensionless)
    # y_shares    = R2_finalist_votes / R2_total_valid (dimensionless)
    # Beta then represents the migration rate for each group share.
    dept_pool   = {}   # dept → list of dicts
    global_pool = []
    unobserved  = []

    for ubigeo, r1_row in r1_df.iterrows():
        dept = r1_row["departamento"]

        if dept_reported.get(dept, 0) >= MIN_DISTRICTS:
            ci    = cluster_map["departments"].get(dept, cluster_map["global"])
            level = "department"
        else:
            ci    = cluster_map["global"]
            level = "global"

        r1_valid  = max(float(r1_row.get("votos_validos", 0.0)), 1.0)
        r1_emit   = max(float(r1_row.get("votos_emitidos", 1.0)), 2.0)
        x_shares  = _build_x(r1_row, finalist, ci, normaliser=r1_valid)
        weight    = PSI[level] * math.log(r1_emit)
        is_rep    = ubigeo in r2_df.index and r2_df.loc[ubigeo, "actas_contabilizadas"] > 0

        if is_rep:
            r2_row    = r2_df.loc[ubigeo]
            actas_c   = float(r2_row.get("actas_contabilizadas", 0.0))
            actas_t   = float(r2_row.get("actas_total", actas_c))
            r2_valid  = max(float(r2_row.get("votos_validos", 0.0)), 1.0)
            r2_emit   = float(r2_row.get("votos_emitidos", 0.0))
            y_share   = float(r2_row.get(finalist, 0.0)) / r2_valid
            y_raw     = float(r2_row.get(finalist, 0.0))
            item = {
                "x_s":       x_shares,
                "y_s":       y_share,
                "y":         y_raw,
                "y_raw":     y_raw,
                "w":         weight,
                "r2_valid":  r2_valid,
                "r2_emitted":r2_emit,
                "r1_valid":  r1_valid,
                "r1_emitted":r1_emit,
                "dept":      dept,
                "level":     level,
                "actas_c":   actas_c,
                "actas_t":   actas_t,
            }
            if level == "department":
                dept_pool.setdefault(dept, []).append(item)
            else:
                global_pool.append(item)
        else:
            unobserved.append({
                "x_s":       x_shares,
                "w":         weight,
                "r1_valid":  r1_valid,
                "r1_emitted":r1_emit,
                "dept":      dept,
                "level":     level,
            })

    all_reported = [it for pool in dept_pool.values() for it in pool] + global_pool
    n_reported   = len(all_reported)

    if n_reported < 4:
        return None

    # Fit share-space WLS per dept pool
    dept_betas = {}
    for dept, items in dept_pool.items():
        if len(items) >= 2:
            X_s = np.stack([it["x_s"] for it in items])
            y_s = np.array([it["y_s"] for it in items])
            w   = np.array([it["w"]   for it in items])
            dept_betas[dept] = _fit_wls(X_s, y_s, w)

    # Global fallback
    global_beta = None
    if len(global_pool) >= 2:
        X_s = np.stack([it["x_s"] for it in global_pool])
        y_s = np.array([it["y_s"] for it in global_pool])
        w   = np.array([it["w"]   for it in global_pool])
        global_beta = _fit_wls(X_s, y_s, w)

    def _beta_for(item):
        if item["level"] == "department":
            return dept_betas.get(item["dept"], global_beta)
        return global_beta

    # Per-pool share-space residual variance (for prediction uncertainty)
    pool_sigma2 = {}
    for dept, items in dept_pool.items():
        beta = dept_betas.get(dept, global_beta)
        if beta is not None:
            resids = [it["y_s"] - float(it["x_s"] @ beta) for it in items]
            pool_sigma2[dept] = float(np.var(resids, ddof=1)) if len(resids) > 1 else 0.0
    if global_pool and global_beta is not None:
        g_resids = [it["y_s"] - float(it["x_s"] @ global_beta) for it in global_pool]
        pool_sigma2["__global__"] = float(np.var(g_resids, ddof=1)) if len(g_resids) > 1 else 0.0
    global_sigma2 = pool_sigma2.get("__global__", 0.0)

    # Predict unreported districts: convert share prediction back to vote counts
    pred_finalist    = 0.0
    pred_r2_valid    = 0.0
    pred_residual_var = 0.0

    # Per-department accumulators for dept-level API
    dept_obs     = {}   # dept → observed finalist votes (raw counts)
    dept_obs_raw = {}   # dept → same as dept_obs; kept for API compatibility
    dept_pred  = {}   # dept → predicted finalist votes (unreported)
    dept_obs_valid  = {}
    dept_pred_valid = {}
    dept_pred_var   = {}
    dept_n_total    = {}

    for ubigeo, r1_row in r1_df.iterrows():
        dept_n_total[r1_row["departamento"]] = (
            dept_n_total.get(r1_row["departamento"], 0) + 1
        )

    for it in all_reported:
        d = it["dept"]
        dept_obs[d]       = dept_obs.get(d, 0.0)       + it["y"]
        dept_obs_raw[d]   = dept_obs_raw.get(d, 0.0)   + it["y_raw"]
        dept_obs_valid[d] = dept_obs_valid.get(d, 0.0) + it["r2_valid"]

    for item in unobserved:
        beta = _beta_for(item)
        if beta is None:
            continue
        y_share_pred = max(0.0, float(item["x_s"] @ beta))
        # Projected R2 valid votes for this district
        proj_r2_valid_d = item["r1_valid"] * r2_over_r1_valid
        pred_finalist += y_share_pred * proj_r2_valid_d
        pred_r2_valid += proj_r2_valid_d
        # Prediction variance in VOTE space: sigma_share^2 * (proj_valid)^2
        sigma2_share = pool_sigma2.get(item["dept"], global_sigma2)
        pred_residual_var += sigma2_share * (proj_r2_valid_d ** 2)

        d = item["dept"]
        dept_pred[d]       = dept_pred.get(d, 0.0)       + y_share_pred * proj_r2_valid_d
        dept_pred_valid[d] = dept_pred_valid.get(d, 0.0) + proj_r2_valid_d
        dept_pred_var[d]   = dept_pred_var.get(d, 0.0)   + sigma2_share * (proj_r2_valid_d ** 2)

    # Project the unreported fraction of partial districts.
    # Each partial district (0 < actas_c < actas_t) contributes its counted votes
    # to obs and its pending actas to pred — using the same WLS betas as for fully
    # unreported districts, scaled by the pending fraction of R1 valid votes.
    for it in all_reported:
        actas_c = it.get("actas_c", 0.0)
        actas_t = it.get("actas_t", actas_c)
        if actas_t <= 0 or actas_c >= actas_t:
            continue
        pending_frac      = (actas_t - actas_c) / actas_t
        beta              = _beta_for(it)
        if beta is None:
            continue
        y_share_pred      = max(0.0, float(it["x_s"] @ beta))
        proj_r2_valid_pnd = it["r1_valid"] * pending_frac * r2_over_r1_valid
        pred_finalist    += y_share_pred * proj_r2_valid_pnd
        pred_r2_valid    += proj_r2_valid_pnd
        sigma2_share      = pool_sigma2.get(it["dept"], global_sigma2)
        pred_residual_var += sigma2_share * (proj_r2_valid_pnd ** 2)

        d = it["dept"]
        dept_pred[d]       = dept_pred.get(d, 0.0)       + y_share_pred * proj_r2_valid_pnd
        dept_pred_valid[d] = dept_pred_valid.get(d, 0.0) + proj_r2_valid_pnd
        dept_pred_var[d]   = dept_pred_var.get(d, 0.0)   + sigma2_share * (proj_r2_valid_pnd ** 2)

    # Residuals in vote space for FPC formula
    reported_with_resid = []
    dept_resids = {}
    for it in all_reported:
        beta = _beta_for(it)
        y_hat = (float(it["x_s"] @ beta) * it["r2_valid"]
                 if beta is not None else it["y"])
        reported_with_resid.append({**it, "y_hat": y_hat})
        d = it["dept"]
        dept_resids.setdefault(d, []).append(it["y"] - y_hat)

    return {
        "finalist":           finalist,
        "obs_finalist":       obs_finalist_raw,
        "obs_finalist_raw":   obs_finalist_raw,
        "pred_finalist":      pred_finalist,
        "obs_r2_valid":       obs_r2_valid_sum,
        "pred_r2_valid":      pred_r2_valid,
        "pred_residual_var":  pred_residual_var,
        "n_reported":         n_reported,
        "n_total":            len(r1_df),
        "reported_items":     reported_with_resid,
        # dept-level aggregates
        "dept_obs":       dept_obs,
        "dept_obs_raw":   dept_obs_raw,
        "dept_pred":      dept_pred,
        "dept_obs_valid": dept_obs_valid,
        "dept_pred_valid":dept_pred_valid,
        "dept_pred_var":  dept_pred_var,
        "dept_n_total":   dept_n_total,
        "dept_resids":    dept_resids,
        "r2_over_r1_valid": r2_over_r1_valid,
        # regression coefficients + pool metadata (for details popup)
        "dept_betas":      {d: b.tolist() for d, b in dept_betas.items()},
        "global_beta":     global_beta.tolist() if global_beta is not None else None,
        "pool_sigma2":     pool_sigma2,
        "dept_pool_sizes": {d: len(items) for d, items in dept_pool.items()},
    }


# ══════════════════════════════════════════════════════════════════════════════
# Stage 5: FPC ratio variance + department-clustered sandwich SE
# ══════════════════════════════════════════════════════════════════════════════

def _compute_variance(pr, projected_share, total_r2_valid):
    """
    FPC ratio variance with department-level Huber-White clustering.

    Var(P_hat) ≈ FPC * clustered_ratio_var + prediction_var
    """
    reported = pr["reported_items"]
    n        = len(reported)
    N        = pr["n_total"]
    if n < 2 or total_r2_valid <= 0:
        return 0.0

    fpc    = 1.0 - n / N
    V_bar  = pr["obs_r2_valid"] / n  # average valid votes per reported district
    if V_bar <= 0:
        return 0.0

    # Residuals for model-assisted sandwich estimator: e_d = y_d - ŷ_d (regression prediction).
    # Using projected_share * V_d here would be ~450x larger per department because it treats
    # each department's geographic lean as model error — the WLS already captures that via features.
    residuals_by_dept = {}
    for it in reported:
        e_d  = it["y"] - it["y_hat"]
        residuals_by_dept.setdefault(it["dept"], []).append(e_d)

    # Department-clustered sum of squared cluster-level residuals
    G           = len(residuals_by_dept)
    cluster_sum = 0.0
    for dept, resids in residuals_by_dept.items():
        E_g = sum(resids)  # sum within-dept residuals
        cluster_sum += E_g ** 2

    # HC cluster correction factor (degrees-of-freedom adjusted)
    if G > 1:
        hc_factor = (n / (n - 1)) * (G / (G - 1))
    else:
        hc_factor = 1.0

    ratio_var  = fpc * hc_factor * cluster_sum / max((n * V_bar) ** 2, 1.0)
    pred_var   = pr["pred_residual_var"] / max(total_r2_valid ** 2, 1.0)

    return max(ratio_var + pred_var, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# Main API
# ══════════════════════════════════════════════════════════════════════════════

def _is_segunda_vuelta(r2_mapping, finalists):
    """True when processed_results contains only the two runoff finalists (+blancos/nulos)."""
    r2_parties = set(r2_mapping.keys()) - BLANK_NULL
    return r2_parties.issubset(set(finalists))


def get_migration_data(cluster_map_path=CLUSTER_MAP_PATH):
    """
    Return migration model projection as a JSON-serializable dict.

    Called by /api/model/migration — results are cached in app.py.
    """
    if not os.path.exists(cluster_map_path):
        return {"ok": False, "error": "Cluster map not found — run build_cluster_map() first."}

    if not os.path.exists(SECOND_ROUND_DISTRITAL):
        return {"ok": False, "error": "Second-round data not available."}

    with open(cluster_map_path, encoding="utf-8") as f:
        cluster_map = json.load(f)

    finalists      = cluster_map["_meta"]["finalists"]
    finalist_names = cluster_map["_meta"]["finalist_names"]

    r2_df, r2_mapping = _load_df(SECOND_ROUND_DISTRITAL, SECOND_ROUND_MAPPING)

    if not _is_segunda_vuelta(r2_mapping, finalists):
        return {
            "ok":      False,
            "status":  "waiting",
            "message": "Segunda vuelta data not yet available in processed_results.",
            "finalists": [],
        }

    r1_df, _ = _load_df(FIRST_ROUND_DISTRITAL, FIRST_ROUND_MAPPING)
    r1_df = r1_df.set_index("ubigeo")
    r2_df = r2_df.set_index("ubigeo")

    n_reported = int((r2_df["actas_contabilizadas"] > 0).sum())
    n_total    = len(r1_df)
    pct_cover  = round(n_reported / n_total * 100, 2) if n_total > 0 else 0.0

    if n_reported < 4:
        return {
            "ok":      True,
            "status":  "insufficient_data",
            "message": f"{n_reported} distritos con datos — se necesitan al menos 4 para correr el modelo.",
            "n_districts_reported": n_reported,
            "n_districts_total":    n_total,
            "finalists": [],
        }

    # Fit + project both finalists
    proj = []
    for idx in range(2):
        res = _project_finalist(r1_df, r2_df, cluster_map, finalists, idx)
        if res is None:
            return {"ok": False, "error": "WLS fitting failed — insufficient data."}
        proj.append(res)

    # FPC ratio: share of total projected valid votes (used for variance)
    total_r2_valid    = max(proj[0]["obs_r2_valid"] + proj[0]["pred_r2_valid"], 1.0)
    proj_votes        = [pr["obs_finalist"] + pr["pred_finalist"] for pr in proj]
    finalist_total    = max(sum(proj_votes), 1.0)

    output_finalists = []
    for pr, total_proj in zip(proj, proj_votes):
        # Share of all valid votes — used internally for variance estimation
        valid_share = total_proj / total_r2_valid
        var         = _compute_variance(pr, valid_share, total_r2_valid)

        df_t   = max(pr["n_reported"] - 1, 1)
        t_crit = float(sp_stats.t.ppf(0.975, df=df_t))
        moe_valid = t_crit * math.sqrt(var)

        # Finalist-only share: F1/(F1+F2) — the number that sums to 100%
        # MOE rescaled from valid-space to finalist-space via the chain rule:
        # d(F1/(F1+F2))/d(F1/V) = V/(F1+F2) → scale factor = total_r2_valid/finalist_total
        scale        = total_r2_valid / finalist_total
        proj_share   = total_proj / finalist_total
        moe          = moe_valid * scale

        output_finalists.append({
            "id":              pr["finalist"],
            "name":            finalist_names.get(pr["finalist"], f"Partido {pr['finalist']}"),
            "observed_votes":  int(pr["obs_finalist_raw"]),
            "projected_votes": int(total_proj),
            "projected_share": round(proj_share * 100, 2),
            "valid_share":     round(valid_share * 100, 2),
            "moe":             round(moe * 100, 2),
            "lower_bound":     round(max(0.0, proj_share - moe) * 100, 2),
            "upper_bound":     round(min(1.0, proj_share + moe) * 100, 2),
        })

    output_finalists.sort(key=lambda x: x["projected_share"], reverse=True)

    return {
        "ok":                    True,
        "status":                "ok",
        "model":                 "vote_migration_wls",
        "confidence_level":      "95%",
        "n_districts_reported":  n_reported,
        "n_districts_total":     n_total,
        "pct_coverage":          pct_cover,
        "finalists":             output_finalists,
    }


def get_migration_data_by_dept(cluster_map_path=CLUSTER_MAP_PATH):
    """
    Returns per-department migration model projections.
    Reuses the national WLS fit; accumulates per-dept obs+pred sums.
    """
    if not os.path.exists(cluster_map_path):
        return {"ok": False, "error": "Cluster map not found."}
    if not os.path.exists(SECOND_ROUND_DISTRITAL):
        return {"ok": False, "error": "Second-round data not available."}

    with open(cluster_map_path, encoding="utf-8") as f:
        cluster_map = json.load(f)

    finalists      = cluster_map["_meta"]["finalists"]
    finalist_names = cluster_map["_meta"]["finalist_names"]

    r2_df, r2_mapping = _load_df(SECOND_ROUND_DISTRITAL, SECOND_ROUND_MAPPING)
    if not _is_segunda_vuelta(r2_mapping, finalists):
        return {"ok": False, "status": "waiting", "departments": {}}

    r1_df, _ = _load_df(FIRST_ROUND_DISTRITAL, FIRST_ROUND_MAPPING)
    r1_df = r1_df.set_index("ubigeo")
    r2_df = r2_df.set_index("ubigeo")

    n_reported = int((r2_df["actas_contabilizadas"] > 0).sum())
    if n_reported < 4:
        return {"ok": True, "status": "insufficient_data", "departments": {}}

    # Run both finalists — we need their dept-level results
    proj = []
    for idx in range(2):
        res = _project_finalist(r1_df, r2_df, cluster_map, finalists, idx)
        if res is None:
            return {"ok": False, "error": "WLS fitting failed."}
        proj.append(res)

    # For each finalist, total projected votes per dept
    # dept_total_votes[dept][finalist_id] = obs + pred
    all_depts = set(proj[0]["dept_n_total"].keys()) | set(proj[1]["dept_n_total"].keys())

    # National finalist total for reference (used to normalise valid_share)
    total_r2_valid = max(
        proj[0]["obs_r2_valid"] + proj[0]["pred_r2_valid"], 1.0
    )

    departments = {}
    for dept in sorted(all_depts):
        dept_finalists = []
        dept_total_proj = 0.0
        dept_total_obs_valid = 0.0

        # Collect totals for both finalists in this dept
        for pr in proj:
            obs  = pr["dept_obs"].get(dept, 0.0)
            pred = pr["dept_pred"].get(dept, 0.0)
            dept_total_proj += obs + pred
            dept_total_obs_valid += pr["dept_obs_valid"].get(dept, 0.0)

        dept_total_proj = max(dept_total_proj, 1.0)

        # Compute per-finalist head-to-head share + CI
        for pr in proj:
            fid  = pr["finalist"]
            obs  = pr["dept_obs"].get(dept, 0.0)
            pred = pr["dept_pred"].get(dept, 0.0)
            total_f = obs + pred

            # Head-to-head projected share for this finalist in this dept
            proj_share = total_f / dept_total_proj

            # Dept-level obs valid votes (for valid_share reference)
            obs_valid_d    = pr["dept_obs_valid"].get(dept, 0.0)
            pred_valid_d   = pr["dept_pred_valid"].get(dept, 0.0)
            total_valid_d  = max(obs_valid_d + pred_valid_d, 1.0)
            valid_share    = total_f / total_valid_d

            # Dept-level CI: FPC-adjusted prediction variance + residual variance
            n_d  = len(pr["dept_resids"].get(dept, []))
            N_d  = pr["dept_n_total"].get(dept, 1)
            fpc  = 1.0 - n_d / N_d if N_d > 0 else 1.0

            resids  = pr["dept_resids"].get(dept, [0.0])
            sigma2  = float(np.var(resids, ddof=1)) if len(resids) > 1 else float(np.mean([r**2 for r in resids]) if resids else 0.0)
            pred_var_d = pr["dept_pred_var"].get(dept, 0.0)

            # Ratio variance scaled to share space
            total_valid_sq = max(total_valid_d ** 2, 1.0)
            var_share = (fpc * sigma2 * max(n_d, 1) / total_valid_sq
                         + pred_var_d / total_valid_sq)

            df_t   = max(n_d - 1, 1)
            t_crit = float(sp_stats.t.ppf(0.975, df=df_t))
            # Scale from valid-space to finalist-space via chain rule
            scale  = total_valid_d / dept_total_proj
            moe    = t_crit * math.sqrt(max(var_share, 0.0)) * scale

            dept_finalists.append({
                "id":              fid,
                "name":            finalist_names.get(fid, f"Partido {fid}"),
                "observed_votes":  int(pr["dept_obs_raw"].get(dept, 0.0)),
                "projected_votes": int(total_f),
                "projected_share": round(proj_share * 100, 2),
                "valid_share":     round(valid_share * 100, 2),
                "moe":             round(moe * 100, 2),
                "lower_bound":     round(max(0.0,   proj_share - moe) * 100, 2),
                "upper_bound":     round(min(1.0,   proj_share + moe) * 100, 2),
            })

        dept_finalists.sort(key=lambda x: x["projected_share"], reverse=True)

        n_rep   = len(pr["dept_resids"].get(dept, []))  # from last finalist (same coverage)
        n_total_d = proj[0]["dept_n_total"].get(dept, 0)
        departments[dept] = {
            "n_reported":   n_rep,
            "n_total":      n_total_d,
            "pct_coverage": round(n_rep / n_total_d * 100, 2) if n_total_d > 0 else 0.0,
            "parties":      dept_finalists,
        }

    # ── Second pass: enrich each dept with popup details ──────────────────────
    with open(FIRST_ROUND_MAPPING, encoding="utf-8") as f:
        r1_names = json.load(f)

    for dept in departments:
        dept_details_finalists = {}
        for pr in proj:
            fid = pr["finalist"]
            pool_level = "department" if dept in pr["dept_betas"] else "global"
            beta = pr["dept_betas"].get(dept) or pr["global_beta"]
            n_pool = pr["dept_pool_sizes"].get(dept, 0)
            sigma2_val = pr["pool_sigma2"].get(dept, pr["pool_sigma2"].get("__global__", 0.0))
            residual_std = round(math.sqrt(max(sigma2_val, 0.0)), 4)

            # Determine cluster_info for this dept
            n_rep_dept = len(pr["dept_resids"].get(dept, []))
            if n_rep_dept >= MIN_DISTRICTS:
                ci = cluster_map["departments"].get(dept, cluster_map["global"])
            else:
                ci = cluster_map["global"]

            # Build features list matching _build_x structure
            features = []
            if beta is not None:
                beta_list = beta if isinstance(beta, list) else beta.tolist()
                # index 0 = finalist's own first-round votes
                features.append({
                    "label":   f"{finalist_names.get(fid, fid)} (propio)",
                    "members": [fid],
                    "beta":    beta_list[0] if len(beta_list) > 0 else 0.0,
                })
                # indices 1..k = clusters
                for i, cl in enumerate(ci.get("clusters", []), start=1):
                    mems = cl.get("members", [])
                    label_parts = [r1_names.get(m, m) for m in mems[:3]]
                    label = ", ".join(label_parts) + ("…" if len(mems) > 3 else "")
                    features.append({
                        "label":   label,
                        "members": mems,
                        "beta":    beta_list[i] if i < len(beta_list) else 0.0,
                    })
                # last index = tail
                tail = ci.get("tail", [])
                if tail:
                    tail_idx = len(ci.get("clusters", [])) + 1
                    features.append({
                        "label":   f"Cola ({len(tail)} partidos)",
                        "members": tail,
                        "beta":    beta_list[tail_idx] if tail_idx < len(beta_list) else 0.0,
                    })

            dept_details_finalists[fid] = {
                "pool_level":    pool_level,
                "n_pool":        n_pool,
                "residual_std":  residual_std,
                "features":      features,
            }

        # pool_level for the dept is from the first finalist (same decision for both)
        top_pool_level = dept_details_finalists[proj[0]["finalist"]]["pool_level"] if proj else "global"
        departments[dept]["details"] = {
            "pool_level": top_pool_level,
            "finalists":  dept_details_finalists,
        }

    return {
        "ok":               True,
        "status":           "ok",
        "model":            "vote_migration_wls",
        "confidence_level": "95%",
        "departments":      departments,
    }


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if "--build" in sys.argv or not os.path.exists(CLUSTER_MAP_PATH):
        build_cluster_map()
    else:
        print("Cluster map already exists. Use --build to rebuild.")
        print("Testing get_migration_data()...")
        result = get_migration_data()
        print(json.dumps({k: v for k, v in result.items() if k != "finalists"}, indent=2))
        if result.get("finalists"):
            for f in result["finalists"]:
                print(f"  {f['name']}: {f['projected_share']}% ± {f['moe']}%  "
                      f"[{f['lower_bound']}, {f['upper_bound']}]")
