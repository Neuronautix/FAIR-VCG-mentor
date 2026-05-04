import pandas as pd
import numpy as np
from typing import Dict, List, Any

from vcg.utils.distributions import fit_best_distribution, fit_best_distribution_with_diagnostics, gaussian_copula_sample


class BootstrapVCGAgent:
    """
    Generates synthetic control subjects using a Gaussian copula with
    fitted marginal distributions. Preserves inter-endpoint correlations.
    """

    def __init__(self):
        self.method_diagnostics: dict = {}

    def run(
        self,
        control_df: pd.DataFrame,
        outcome_cols: List[str],
        covariate_cols: List[str],
        config: dict,
    ) -> pd.DataFrame:
        """
        Returns a DataFrame with n_synthetic rows containing outcome_cols + covariate_cols
        plus metadata columns: vcg=True, vcg_method="bootstrap", vcg_seed=seed.

        Algorithm:
        1. Extract numeric outcome columns from control_df.
        2. Compute Spearman correlation matrix for outcomes.
        3. For each outcome: fit best distribution using distributions.fit_best_distribution.
        4. Generate n_synthetic samples via distributions.gaussian_copula_sample.
        5. For each covariate (categorical): sample with replacement from empirical distribution
           in control_df (stratified to match original proportions).
        6. Combine outcomes + covariates into a DataFrame.
        7. Add vcg=True, vcg_method="bootstrap", vcg_seed=seed columns.

        Use config["seed"] for reproducibility.
        """
        n_synthetic = config.get("n_synthetic", 30)
        seed = config.get("seed", 42)
        rng = np.random.default_rng(seed)

        # Filter to valid numeric outcome columns
        valid_outcome_cols = []
        for col in outcome_cols:
            if col not in control_df.columns:
                continue
            numeric = pd.to_numeric(control_df[col], errors="coerce")
            if numeric.notna().sum() >= 2:
                valid_outcome_cols.append(col)

        rows: Dict[str, np.ndarray] = {}

        if valid_outcome_cols:
            # Step 1: Build numeric outcome matrix
            outcome_data = pd.DataFrame()
            for col in valid_outcome_cols:
                outcome_data[col] = pd.to_numeric(control_df[col], errors="coerce")

            # Drop rows where ALL outcomes are NaN
            outcome_data = outcome_data.dropna(how="all")

            if len(outcome_data) < 2:
                # Too few rows after NaN drop — fall back to per-column normal
                for col in valid_outcome_cols:
                    series = pd.to_numeric(control_df[col], errors="coerce").dropna()
                    mu = float(series.mean()) if len(series) > 0 else 0.0
                    sigma = float(series.std(ddof=1)) if len(series) > 1 else 1.0
                    rows[col] = rng.normal(mu, max(sigma, 1e-9), size=n_synthetic)
            else:
                # Separate zero-variance columns — copula/ppf breaks for constant series
                variable_cols = []
                for col in valid_outcome_cols:
                    series = outcome_data[col].dropna()
                    if series.std(ddof=1) > 1e-10:
                        variable_cols.append(col)
                    else:
                        # Constant column: just repeat the single value
                        rows[col] = np.full(n_synthetic, float(series.iloc[0]) if len(series) > 0 else 0.0)

                if not variable_cols:
                    pass  # all rows already filled above
                else:
                    # Step 2: Spearman correlation matrix (variable columns only)
                    corr_data = outcome_data[variable_cols].copy()
                    for col in variable_cols:
                        corr_data[col] = corr_data[col].fillna(corr_data[col].median())

                    if len(variable_cols) == 1:
                        corr_matrix = np.array([[1.0]])
                    else:
                        try:
                            corr_matrix = corr_data.corr(method="spearman").values
                            corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
                            np.fill_diagonal(corr_matrix, 1.0)
                        except Exception:
                            corr_matrix = np.eye(len(variable_cols))

                    # Step 3: Fit distributions (variable columns only)
                    marginal_dists = []
                    fit_diagnostics: Dict[str, Any] = {}
                    for col in variable_cols:
                        series = outcome_data[col].dropna()
                        dist_name, params, diag = fit_best_distribution_with_diagnostics(series)
                        marginal_dists.append((dist_name, params))
                        fit_diagnostics[col] = diag

                    # Step 4: Gaussian copula sampling
                    try:
                        samples = gaussian_copula_sample(marginal_dists, corr_matrix, n_synthetic, rng)
                        for j, col in enumerate(variable_cols):
                            rows[col] = samples[:, j]
                    except Exception:
                        from vcg.utils.distributions import sample_from_distribution
                        for j, col in enumerate(variable_cols):
                            dist_name, params = marginal_dists[j]
                            rows[col] = sample_from_distribution(dist_name, params, n_synthetic, rng)

                    self.method_diagnostics = {
                        "method": "gaussian_copula_bootstrap",
                        "n_control": len(outcome_data),
                        "fitted_distributions": fit_diagnostics,
                    }

        # Step 5: Categorical covariates — sample with replacement from empirical PMF
        for col in covariate_cols:
            if col not in control_df.columns:
                continue

            col_data = control_df[col].dropna()
            if len(col_data) == 0:
                rows[col] = np.array([""] * n_synthetic, dtype=object)
                continue

            # Compute empirical PMF
            value_counts = col_data.value_counts(normalize=True)
            categories = value_counts.index.tolist()
            probs = value_counts.values

            # Sample using rng integers to pick indices
            indices = rng.choice(len(categories), size=n_synthetic, p=probs)
            rows[col] = np.array([categories[i] for i in indices])

        # Step 6: Combine into DataFrame
        result_df = pd.DataFrame(rows)

        # Ensure columns are in a consistent order: outcomes first, then covariates
        ordered_cols = (
            [c for c in valid_outcome_cols if c in result_df.columns]
            + [c for c in covariate_cols if c in result_df.columns and c not in valid_outcome_cols]
        )
        result_df = result_df[ordered_cols] if ordered_cols else result_df

        # Step 7: Add metadata columns
        result_df["vcg"] = True
        result_df["vcg_method"] = "bootstrap"
        result_df["vcg_seed"] = seed

        return result_df
