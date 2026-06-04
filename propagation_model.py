import numpy as np
import pandas as pd


def run_stratified_projection(
    df, stratum_col, candidate_cols, fallback_col=None, z_score=1.96
):
    """Executes an election projection using Stratified Random Sampling.

    Parameters:
    -----------
    df : pd.DataFrame
        The input election dataset containing reporting data per unit.
    stratum_col : str
        The primary column used for stratification (e.g., 'distrito',
        'provincia').
    candidate_cols : list
        List of strings representing candidate columns (valid votes only).
    fallback_col : str, optional
        The larger geographic tier to fall back on if N-1 requirement fails.
    z_score : float
        Z-score for Confidence Intervals (default 1.96 for 95%).
    """
    # 1. Base Aggregations at the Stratum Level
    # Summing up key tracking metrics
    strata_metrics = (
        df.groupby(stratum_col)
        .agg(
            N_h=("actas_total", "sum"),
            n_h=("actas_contabilizadas", "sum"),
            voters_total=("votos_habiles", "sum"),
            v_observed_valid=("votos_validos", "sum"),
            v_emitted=("votos_emitidos", "sum"),
        )
        .reset_index()
    )

    # 2. Check "N-1" Stability Requirements
    # If a stratum has fewer than 2 reported tables, it can fail variance calculation.
    failed_strata = strata_metrics[strata_metrics["n_h"] < 2][stratum_col]

    if not failed_strata.empty and fallback_col:
        print(
            f"⚠️ Warning: Stratum tier '{stratum_col}' has regions with < 2 tables reporting."
        )
        print(
            f"Falling back to higher regional tier: '{fallback_col}' for those areas."
        )
        # Shift stratification strategy dynamically to the higher tier
        stratum_col = fallback_col
        strata_metrics = (
            df.groupby(stratum_col)
            .agg(
                N_h=("actas_total", "sum"),
                n_h=("actas_contabilizadas", "sum"),
                voters_total=("votos_habiles", "sum"),
                v_observed_valid=("votos_validos", "sum"),
                v_emitted=("votos_emitidos", "sum"),
            )
            .reset_index()
        )

    # Total tables across the selected geographical ecosystem
    N_total = strata_metrics["N_h"].sum()

    # 3. Core Stratum Ratios & Weights
    # Weight of stratum (W_h = N_h / N)
    strata_metrics["W_h"] = strata_metrics["N_h"] / N_total
    # Finite Population Correction term (1 - f_h) where f_h = n_h / N_h
    strata_metrics["f_h"] = strata_metrics["n_h"] / strata_metrics["N_h"]
    strata_metrics["FPC"] = 1 - strata_metrics["f_h"]

    # Observed Turnout / Valid Vote Factor (R_valid,h)
    # Handles division by zero gracefully if no tables are reported yet
    strata_metrics["R_valid_h"] = np.where(
        strata_metrics["n_h"] > 0,
        strata_metrics["v_observed_valid"] / strata_metrics["v_emitted"],
        0,
    )

    # Calculate remaining unseen eligible voters (E_pending,h)
    # Assumes proportional breakdown of voters per table
    strata_metrics["E_pending_h"] = strata_metrics["voters_total"] * (
        1 - strata_metrics["f_h"]
    )

    # Candidate Specific Imputations
    projections = {}

    for candidate in candidate_cols:
        # Sum total candidate votes observed in stratum so far
        candidate_stratum_votes = df.groupby(stratum_col)[candidate].sum().values

        # Current proportion of valid votes obtained by the party in stratum (P_party,h)
        strata_metrics["P_party_h"] = np.where(
            strata_metrics["v_observed_valid"] > 0,
            candidate_stratum_votes / strata_metrics["v_observed_valid"],
            0,
        )

        # Apply Imputation Formula: V_observed + Sum(E_pending_h * R_valid_h * P_party_h)
        observed_total_votes = df[candidate].sum()
        estimated_pending_votes = (
            strata_metrics["E_pending_h"]
            * strata_metrics["R_valid_h"]
            * strata_metrics["P_party_h"]
        ).sum()

        projected_votes = observed_total_votes + estimated_pending_votes

        # 4. Stratified Variance Calculation
        # Var(p) = Sum( W_h^2 * (1 - f_h) * [p_h(1-p_h) / (n_h - 1)] )
        p_h = strata_metrics["P_party_h"]
        bessels_correction = strata_metrics["n_h"] - 1

        # Check safety bounds for variance math (requires n_h > 1)
        variance_terms = np.where(
            bessels_correction > 0,
            (strata_metrics["W_h"] ** 2)
            * strata_metrics["FPC"]
            * ((p_h * (1 - p_h)) / bessels_correction),
            0,
        )

        national_variance = variance_terms.sum()

        # 5. Calculate Margins of Error
        margin_of_error = z_score * np.sqrt(national_variance)

        # Store calculations converts underlying variance back into comparable vote units
        # for clean visual interpretations
        total_projected_valid_votes = (
            strata_metrics["v_observed_valid"].sum()
            + (
                strata_metrics["E_pending_h"] * strata_metrics["R_valid_h"]
            ).sum()
        )

        moe_in_votes = margin_of_error * total_projected_valid_votes

        projections[candidate] = {
            "Observed Votes": int(observed_total_votes),
            "Projected Votes": int(projected_votes),
            "MOE (Votes)": int(moe_in_votes),
            "Lower Bound (Votes)": max(0, int(projected_votes - moe_in_votes)),
            "Upper Bound (Votes)": int(projected_votes + moe_in_votes),
        }

    return pd.DataFrame(projections).T