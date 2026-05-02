import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict, List
import warnings as _warnings


class SyntheticVCGAgent:
    """
    Generates synthetic controls by independently sampling each column's
    marginal distribution (KDE for N>=15, Normal for N<15).
    Simpler than bootstrap but does not preserve correlations.
    """

    def run(
        self,
        control_df: pd.DataFrame,
        outcome_cols: List[str],
        covariate_cols: List[str],
        config: dict,
    ) -> pd.DataFrame:
        """
        Returns DataFrame with n_synthetic rows.

        For each numeric outcome col:
        - If N >= 15: use scipy.stats.gaussian_kde, sample from it
        - If N < 15: fit scipy.stats.norm, sample from it
        - Shapiro-Wilk test: if p < 0.05 and all values > 0, use lognorm instead

        For each categorical covariate: sample from empirical PMF.

        Add vcg=True, vcg_method="synthetic", vcg_seed=seed.
        """
        n_synthetic = config.get("n_synthetic", 30)
        seed = config.get("seed", 42)
        rng = np.random.default_rng(seed)

        rows: Dict[str, np.ndarray] = {}

        # Process numeric outcome columns
        for col in outcome_cols:
            if col not in control_df.columns:
                continue

            numeric = pd.to_numeric(control_df[col], errors="coerce").dropna()

            if len(numeric) == 0:
                # No data — use standard normal as fallback
                rows[col] = rng.standard_normal(n_synthetic)
                continue

            values = numeric.values.astype(float)
            n = len(values)
            all_positive = bool((values > 0).all())

            # Shapiro-Wilk test for normality (N must be >= 3 for scipy)
            use_lognorm = False
            if all_positive and n >= 3:
                try:
                    with _warnings.catch_warnings():
                        _warnings.simplefilter("ignore")
                        _, sw_p = stats.shapiro(values[:min(n, 5000)])
                    if sw_p < 0.05:
                        use_lognorm = True
                except Exception:
                    pass

            if use_lognorm:
                # Fit log-normal
                try:
                    with _warnings.catch_warnings():
                        _warnings.simplefilter("ignore")
                        lognorm_params = stats.lognorm.fit(values, floc=0)
                    rng_int = int(rng.integers(0, 2**31))
                    samples = stats.lognorm.rvs(*lognorm_params, size=n_synthetic, random_state=rng_int)
                    rows[col] = samples.astype(float)
                    continue
                except Exception:
                    pass  # Fall through to other methods

            if n >= 15:
                # KDE sampling
                try:
                    with _warnings.catch_warnings():
                        _warnings.simplefilter("ignore")
                        kde = stats.gaussian_kde(values)
                    rng_int = int(rng.integers(0, 2**31))
                    samples = kde.resample(n_synthetic, seed=rng_int).flatten()
                    rows[col] = samples.astype(float)
                except Exception:
                    # Fallback to normal
                    mu = float(np.mean(values))
                    sigma = float(np.std(values, ddof=1)) if n > 1 else 1.0
                    rows[col] = rng.normal(mu, max(sigma, 1e-9), size=n_synthetic)
            else:
                # Normal distribution for small N
                mu = float(np.mean(values))
                sigma = float(np.std(values, ddof=1)) if n > 1 else 1.0
                rows[col] = rng.normal(mu, max(sigma, 1e-9), size=n_synthetic)

        # Process categorical covariates
        for col in covariate_cols:
            if col not in control_df.columns:
                continue

            col_data = control_df[col].dropna()
            if len(col_data) == 0:
                rows[col] = np.array([""] * n_synthetic, dtype=object)
                continue

            # Try numeric first
            numeric = pd.to_numeric(col_data, errors="coerce")
            if numeric.notna().mean() > 0.8:
                # Treat as numeric — use normal or KDE
                values = numeric.dropna().values.astype(float)
                n = len(values)
                if n >= 15:
                    try:
                        with _warnings.catch_warnings():
                            _warnings.simplefilter("ignore")
                            kde = stats.gaussian_kde(values)
                        rng_int = int(rng.integers(0, 2**31))
                        rows[col] = kde.resample(n_synthetic, seed=rng_int).flatten().astype(float)
                        continue
                    except Exception:
                        pass
                mu = float(np.mean(values))
                sigma = float(np.std(values, ddof=1)) if n > 1 else 1.0
                rows[col] = rng.normal(mu, max(sigma, 1e-9), size=n_synthetic)
            else:
                # Categorical PMF sampling
                value_counts = col_data.value_counts(normalize=True)
                categories = value_counts.index.tolist()
                probs = value_counts.values
                indices = rng.choice(len(categories), size=n_synthetic, p=probs)
                rows[col] = np.array([categories[i] for i in indices])

        # Build DataFrame
        result_df = pd.DataFrame(rows)

        # Consistent column order
        ordered_cols = (
            [c for c in outcome_cols if c in result_df.columns]
            + [c for c in covariate_cols if c in result_df.columns and c not in outcome_cols]
        )
        result_df = result_df[ordered_cols] if ordered_cols else result_df

        # Add metadata columns
        result_df["vcg"] = True
        result_df["vcg_method"] = "synthetic"
        result_df["vcg_seed"] = seed

        return result_df
