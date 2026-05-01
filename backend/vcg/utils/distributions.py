import warnings as _warnings

import numpy as np
import pandas as pd
from scipy import stats
from typing import Tuple, Any


def fit_best_distribution(series: pd.Series) -> Tuple[str, Any]:
    """
    Fits the best scipy distribution to a numeric series.
    Tests: norm, lognorm, gamma.
    Uses Shapiro-Wilk: if series is all-positive and W < 0.95, try lognorm.
    Returns (dist_name, fitted_params) where params is what scipy.stats.dist.fit() returns.
    """
    clean = pd.to_numeric(series, errors="coerce").dropna()

    if len(clean) < 3:
        # Fallback to normal if not enough data
        params = stats.norm.fit(clean) if len(clean) > 0 else (0.0, 1.0)
        return "norm", params

    # Shapiro-Wilk test (only reliable for N < 5000)
    test_data = clean.values[:5000]
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            w_stat, _ = stats.shapiro(test_data[:min(len(test_data), 5000)])
    except Exception:
        w_stat = 1.0

    all_positive = (clean > 0).all()

    # If data deviates from normality and is all-positive, try lognorm
    if all_positive and w_stat < 0.95:
        try:
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")
                lognorm_params = stats.lognorm.fit(clean.values, floc=0)
            return "lognorm", lognorm_params
        except Exception:
            pass

    # Try gamma if all-positive
    if all_positive and len(clean) >= 5:
        try:
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")
                gamma_params = stats.gamma.fit(clean.values, floc=0)
            return "gamma", gamma_params
        except Exception:
            pass

    # Default to normal
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        norm_params = stats.norm.fit(clean.values)
    return "norm", norm_params


def sample_from_distribution(
    dist_name: str,
    params: Any,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Draws n samples from the fitted distribution using the rng.
    Uses scipy.stats.{dist_name}.rvs(*params, size=n, random_state=rng_int)
    """
    # Convert rng to an integer seed for scipy compatibility
    rng_int = int(rng.integers(0, 2**31))

    dist_map = {
        "norm": stats.norm,
        "lognorm": stats.lognorm,
        "gamma": stats.gamma,
    }
    dist = dist_map.get(dist_name, stats.norm)

    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            samples = dist.rvs(*params, size=n, random_state=rng_int)
    except Exception:
        # Fallback to normal sampling using rng
        samples = rng.normal(0, 1, size=n)

    return np.asarray(samples, dtype=float)


def gaussian_copula_sample(
    marginal_dists: list,  # list of (dist_name, params) tuples, one per column
    corr_matrix: np.ndarray,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generates n rows of correlated samples preserving marginal distributions via Gaussian copula.
    Algorithm:
    1. Sample from multivariate_normal(mean=zeros, cov=corr_matrix) -> shape (n, k)
    2. Apply normal CDF to each column -> uniform [0,1]
    3. Apply inverse CDF of each marginal -> final samples
    Returns shape (n, k) array.
    """
    k = len(marginal_dists)

    if k == 0:
        return np.empty((n, 0))

    # Ensure the correlation matrix is positive semi-definite
    # Add small jitter to diagonal for numerical stability
    corr = corr_matrix.copy()
    np.fill_diagonal(corr, 1.0)
    corr = (corr + corr.T) / 2.0  # symmetrise
    min_eig = np.linalg.eigvalsh(corr).min()
    if min_eig < 1e-8:
        corr += np.eye(k) * (abs(min_eig) + 1e-6)
        # Re-normalise to correlation matrix
        d = np.sqrt(np.diag(corr))
        corr = corr / np.outer(d, d)

    mean = np.zeros(k)
    rng_int = int(rng.integers(0, 2**31))

    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            mvn_samples = stats.multivariate_normal.rvs(
                mean=mean, cov=corr, size=n, random_state=rng_int
            )
        if n == 1:
            mvn_samples = mvn_samples.reshape(1, -1)
    except Exception:
        # Fallback to independent normal samples
        mvn_samples = rng.multivariate_normal(mean, corr, size=n)

    # Shape guard: ensure (n, k)
    if mvn_samples.ndim == 1:
        mvn_samples = mvn_samples.reshape(n, k)

    # Step 2: apply normal CDF -> uniform [0, 1]
    uniform_samples = stats.norm.cdf(mvn_samples)  # shape (n, k)

    # Step 3: apply inverse CDF of each marginal
    dist_map = {
        "norm": stats.norm,
        "lognorm": stats.lognorm,
        "gamma": stats.gamma,
    }

    result = np.empty((n, k))
    for j, (dist_name, params) in enumerate(marginal_dists):
        dist = dist_map.get(dist_name, stats.norm)
        u_col = np.clip(uniform_samples[:, j], 1e-9, 1 - 1e-9)
        try:
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")
                result[:, j] = dist.ppf(u_col, *params)
        except Exception:
            result[:, j] = rng.normal(0, 1, size=n)

    return result
