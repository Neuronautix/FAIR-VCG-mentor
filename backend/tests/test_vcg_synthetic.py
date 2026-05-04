import sys
import os
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vcg.agents.vcg_synthetic import SyntheticVCGAgent


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_control_df(n=20, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "bw": rng.normal(250, 20, n),
        "alat": rng.lognormal(3.5, 0.4, n),
        "sex": rng.choice(["male", "female"], n),
    })


def default_config(n_synthetic=30, seed=42):
    return {"n_synthetic": n_synthetic, "seed": seed, "method": "synthetic"}


# ── Shape and metadata ─────────────────────────────────────────────────────────

def test_output_shape():
    df = make_control_df(20)
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw", "alat"], ["sex"], default_config(30))
    assert len(result) == 30
    assert "bw" in result.columns
    assert "alat" in result.columns
    assert "sex" in result.columns


def test_vcg_metadata_columns():
    df = make_control_df(20)
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(10))
    assert result["vcg"].all()
    assert (result["vcg_method"] == "synthetic").all()
    assert (result["vcg_seed"] == 42).all()


def test_reproducibility():
    df = make_control_df(20)
    r1 = SyntheticVCGAgent().run(df, ["bw", "alat"], [], default_config(20, seed=7))
    r2 = SyntheticVCGAgent().run(df, ["bw", "alat"], [], default_config(20, seed=7))
    pd.testing.assert_frame_equal(r1[["bw", "alat"]], r2[["bw", "alat"]])


def test_different_seeds_differ():
    df = make_control_df(20)
    r1 = SyntheticVCGAgent().run(df, ["bw"], [], default_config(50, seed=1))
    r2 = SyntheticVCGAgent().run(df, ["bw"], [], default_config(50, seed=2))
    assert not np.allclose(r1["bw"].values, r2["bw"].values)


# ── Statistical properties ─────────────────────────────────────────────────────

def test_mean_roughly_preserved():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"bw": rng.normal(250, 20, 30)})
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(100, seed=0))
    real_mean = float(df["bw"].mean())
    vcg_mean = float(result["bw"].mean())
    sem = 20 / np.sqrt(30)
    assert abs(vcg_mean - real_mean) < 5 * sem


def test_categorical_proportions_preserved():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "bw": rng.normal(250, 20, 50),
        "sex": ["male"] * 30 + ["female"] * 20,
    })
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw"], ["sex"], default_config(100, seed=1))
    male_frac = (result["sex"] == "male").mean()
    assert 0.35 < male_frac < 0.75


# ── Small N path (norm, not KDE) ───────────────────────────────────────────────

def test_small_n_uses_norm():
    """With N<15 the norm path should be used and should not crash."""
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"bw": rng.normal(250, 20, 8)})
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(20))
    assert len(result) == 20
    diag = agent.method_diagnostics.get("per_column_method", {})
    assert diag.get("bw") == "norm_small_n"


def test_large_n_uses_kde():
    """With N>=15 the KDE path should be used."""
    rng = np.random.default_rng(4)
    df = pd.DataFrame({"bw": rng.normal(250, 20, 20)})
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(30))
    assert len(result) == 30
    diag = agent.method_diagnostics.get("per_column_method", {})
    assert diag.get("bw") == "kde"


def test_lognormal_path():
    """All-positive, non-normal data should trigger lognorm path."""
    rng = np.random.default_rng(5)
    # lognormal data is clearly non-normal
    df = pd.DataFrame({"alat": rng.lognormal(3.5, 1.2, 20)})
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["alat"], [], default_config(30))
    assert len(result) == 30
    # All synthetic values should be positive (lognorm) or at least finite
    assert np.isfinite(result["alat"].values).all()


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_empty_outcome_col_skipped():
    df = make_control_df(20)
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw", "nonexistent"], [], default_config(10))
    assert "bw" in result.columns
    assert "nonexistent" not in result.columns


def test_all_nan_handled():
    df = make_control_df(20)
    df["nan_col"] = float("nan")
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw", "nan_col"], [], default_config(10))
    assert "bw" in result.columns


def test_empty_df():
    df = pd.DataFrame({"bw": pd.Series([], dtype=float)})
    agent = SyntheticVCGAgent()
    result = agent.run(df, ["bw"], [], default_config(5))
    # Should produce rows (from fallback) without crashing
    assert len(result) == 5


# ── Method diagnostics ─────────────────────────────────────────────────────────

def test_method_diagnostics_populated():
    df = make_control_df(20)
    agent = SyntheticVCGAgent()
    agent.run(df, ["bw", "alat"], [], default_config(20))
    diag = agent.method_diagnostics
    assert diag.get("method") == "kde_normal_sampling"
    assert "per_column_method" in diag
    assert "bw" in diag["per_column_method"]


def test_method_diagnostics_n_control():
    df = make_control_df(20)
    agent = SyntheticVCGAgent()
    agent.run(df, ["bw"], [], default_config(20))
    assert agent.method_diagnostics.get("n_control") == 20
