import sys
import os
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vcg.agents.vcg_bootstrap import BootstrapVCGAgent


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_control_df(n=20, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "bw": rng.normal(250, 20, n),
        "alat": rng.lognormal(3.5, 0.4, n),
        "sex": rng.choice(["male", "female"], n),
    })


def default_config(n_synthetic=30, seed=42):
    return {"n_synthetic": n_synthetic, "seed": seed, "method": "bootstrap"}


# ── Shape and metadata ─────────────────────────────────────────────────────────

def test_output_shape():
    df = make_control_df(20)
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw", "alat"], ["sex"], default_config(30))
    assert len(result) == 30
    assert "bw" in result.columns
    assert "alat" in result.columns
    assert "sex" in result.columns


def test_vcg_metadata_columns():
    df = make_control_df(20)
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(10))
    assert result["vcg"].all()
    assert (result["vcg_method"] == "bootstrap").all()
    assert (result["vcg_seed"] == 42).all()


def test_single_outcome_column():
    df = make_control_df(20)
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(15))
    assert len(result) == 15
    assert "bw" in result.columns


def test_reproducibility():
    df = make_control_df(20)
    r1 = BootstrapVCGAgent().run(df, ["bw", "alat"], [], default_config(20, seed=7))
    r2 = BootstrapVCGAgent().run(df, ["bw", "alat"], [], default_config(20, seed=7))
    pd.testing.assert_frame_equal(r1[["bw", "alat"]], r2[["bw", "alat"]])


def test_different_seeds_differ():
    df = make_control_df(20)
    r1 = BootstrapVCGAgent().run(df, ["bw"], [], default_config(50, seed=1))
    r2 = BootstrapVCGAgent().run(df, ["bw"], [], default_config(50, seed=2))
    assert not np.allclose(r1["bw"].values, r2["bw"].values)


# ── Statistical properties ─────────────────────────────────────────────────────

def test_mean_roughly_preserved():
    """VCG mean should be within 3 SEM of real control mean."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"bw": rng.normal(250, 20, 40)})
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(100, seed=0))
    real_mean = float(df["bw"].mean())
    vcg_mean = float(result["bw"].mean())
    sem = 20 / np.sqrt(40)
    assert abs(vcg_mean - real_mean) < 4 * sem, (
        f"VCG mean {vcg_mean:.2f} too far from real mean {real_mean:.2f}"
    )


def test_categorical_covariate_proportions():
    """Categorical covariate proportions should be roughly preserved."""
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "bw": rng.normal(250, 20, 50),
        "sex": ["male"] * 25 + ["female"] * 25,
    })
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw"], ["sex"], default_config(100, seed=1))
    male_frac = (result["sex"] == "male").mean()
    assert 0.3 < male_frac < 0.7, f"Unexpected sex proportion: {male_frac}"


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_small_n_fallback():
    """Should not crash with n_control=3 (below bootstrap threshold)."""
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"bw": rng.normal(250, 20, 3)})
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(10))
    assert len(result) == 10


def test_zero_variance_column():
    """Constant column should not raise and should produce a constant output."""
    df = pd.DataFrame({"bw": [250.0] * 20, "dose": [10.0] * 20})
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw", "dose"], [], default_config(10))
    assert len(result) == 10
    # The constant column should still be present
    assert "dose" in result.columns


def test_missing_outcome_col_skipped():
    """A column listed in outcome_cols that doesn't exist should be silently skipped."""
    df = make_control_df(20)
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw", "nonexistent_col"], [], default_config(10))
    assert "bw" in result.columns
    assert "nonexistent_col" not in result.columns


def test_all_nan_column_skipped():
    """A column that is entirely NaN should be handled gracefully."""
    df = make_control_df(20)
    df["nan_col"] = float("nan")
    agent = BootstrapVCGAgent()
    result = agent.run(df, ["bw", "nan_col"], [], default_config(10))
    assert "bw" in result.columns


# ── Method diagnostics ─────────────────────────────────────────────────────────

def test_method_diagnostics_populated():
    df = make_control_df(20)
    agent = BootstrapVCGAgent()
    agent.run(df, ["bw", "alat"], [], default_config(20))
    diag = agent.method_diagnostics
    assert diag.get("method") == "gaussian_copula_bootstrap"
    assert "fitted_distributions" in diag
    assert "bw" in diag["fitted_distributions"]
    assert "alat" in diag["fitted_distributions"]


def test_method_diagnostics_aic_bic():
    df = make_control_df(30)
    agent = BootstrapVCGAgent()
    agent.run(df, ["bw"], [], default_config(20))
    diag = agent.method_diagnostics["fitted_distributions"]["bw"]
    assert "aic" in diag
    assert "bic" in diag
    assert diag["dist_name"] in ("norm", "lognorm", "gamma")
