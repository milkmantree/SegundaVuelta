# 🗳️ Statistical Methodology: Stratified Election Projection Engine

## 1. Overview
This model is designed to provide high-accuracy election forecasts using partial returns. Unlike simple running totals, this engine accounts for the **non-random nature** of election reporting (where urban areas often report faster than rural ones) by using a **Stratified Random Sampling** framework.

The electorate is partitioned into $L$ strata (Geographic levels: Department, Province, or District), ensuring that the final projection reflects the true weight of each region regardless of its reporting speed.

---

## 2. The Estimation Model (Imputation)
The total projected votes for a candidate ($\hat{V}_{total}$) is the sum of observed votes plus the estimated votes from pending (uncounted) tables.

$$\hat{V}_{party} = V_{observed} + \sum_{h=1}^{L} \left( E_{pending, h} \times R_{valid, h} \times P_{party, h} \right)$$

### Key Variables:
*   **$E_{pending, h}$**: Total eligible voters in tables that have not yet reported in stratum $h$.
*   **$R_{valid, h}$**: The observed ratio of valid votes to total voters within stratum $h$.
*   **$P_{party, h}$**: The current proportion of valid votes obtained by the party in stratum $h$.

---

## 3. Confidence Interval Calculation
The model calculates the **Margin of Error (MOE)** to define the range in which the final result will likely fall. This is based on the variance of a stratified population.

### A. Stratified Variance Formula
The national variance is the weighted sum of the variances of each individual stratum:

$$Var(\hat{p}) = \sum_{h=1}^{L} W_h^2 \left( 1 - f_h \right) \frac{\hat{p}_h(1 - \hat{p}_h)}{n_h - 1}$$

*   **Stratum Weight ($W_h$):** Calculated as $N_h / N$, representing the stratum's share of the total national tables.
*   **Finite Population Correction ($1 - f_h$):** Where $f_h = n_h / N_h$. This is critical; as a region reaches 100% reporting, its contribution to the national error drops to zero.
*   **Bessel's Correction ($n_h - 1$):** Used to provide an unbiased estimate of the variance from the sample of tables.

### B. Margin of Error & Bounds
The MOE is derived using a Z-score (standardized normal distribution):

$$MOE = z \times \sqrt{Var(\hat{p})}$$

*   **95% Confidence Level:** $z = 1.96$
*   **Upper Bound:** $\text{Projection} + MOE$
*   **Lower Bound:** $\text{Projection} - MOE$

---

## 4. Relevant Statistical Considerations

### Geographic Bias (The "Reporting Gap")
In many countries, such as Peru, geographic location is highly correlated with political preference.
*   **Urban vs. Rural:** If urban centers report 90% while rural areas report 10%, a simple count would be heavily biased.
*   **The Stratification Solution:** The model treats a 10% rural sample as an estimate for 100% of that specific region's total weight, "protecting" the rural vote in the national projection.

### The "N-1" Stability Requirement
Mathematically, a stratum must have at least **two tables reported** ($n_h \geq 2$) to calculate variance. 
*   **Initial Volatility:** In the very early stages of the count, the Confidence Intervals will be extremely wide (or undefined for certain regions) until the minimum sample size per stratum is met.

### Filtering "Noise"
To align with official electoral rules, the model dynamically filters:
1.  **Votos en Blanco** (Blank)
2.  **Votos Nulos** (Null/Void)
3.  **Votos Impugnados** (Challenged)

Proportions are calculated solely based on **Votos Válidos** to accurately reflect the percentage used to declare a winner.

### Convergence
As $n_h$ approaches $N_h$ (total tables), the term $(1 - f_h)$ approaches $0$. Consequently, the variance collapses, and the projected line "freezes" into the final official result.

---

## 5. Summary of Limitations
*   **Intra-stratum bias:** If the first 5% of a district to report is not representative of the whole district, the local estimate will be skewed until more data arrives.
*   **Homogeneity Assumption:** The model assumes that within a stratum (e.g., a specific District), the voting behavior is relatively consistent.