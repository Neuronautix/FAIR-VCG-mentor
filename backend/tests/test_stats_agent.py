import sys
import os
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vcg.agents.stats_agent import StatsAgent


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_matching_dfs(n_real=20, n_vcg=30, seed=0):
    """Produce real and VCG DataFrames from the same distribution."""
    rng = np.random.default_rng(seed)
    real = pd.DataFrame({
        "bw": rng.normal(250, 20, n_real),
        "alat": rng.lognormal(3.5, 0.4, n_real),
        "sex": rng.choice(["male", "female"], n_real),
    })
    vcg = pd.DataFrame({
        "bw": rng.normal(250, 20, n_vcg),
        "alat": rng.lognormal(3.5, 0.4, n_vcg),
        "sex": rng.choice(["male", "female"], n_vcg),
    })
    return real, vcg


def make_divergent_dfs(n_real=20, n_vcg=30, seed=1):
    """Produce real and VCG DataFrames from very different distributions."""
    rng = np.random.default_rng(seed)
    real = pd.DataFrame({"bw": rng.normal(250, 20, n_real)})
    vcg = pd.DataFrame({"bw": rng.normal(400, 20, n_vcg)})
    return real, vcg


# ── Return structure ───────────────────────────────────────────────────────────

def test_return_keys():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw", "alat"], ["sex"])
    for key in ("ks_pvalues", "effect_sizes", "reliability_score",
                "reliability_breakdown", "warnings", "diagnostic_plots",
                "per_endpoint_plots", "method_params"):
        assert key in result, f"Missing key: {key}"


def test_reliability_score_range():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw"], [])
    score = result["reliability_score"]
    assert 0.0 <= score <= 1.0


def test_ks_pvalues_all_columns():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw", "alat"], [])
    assert "bw" in result["ks_pvalues"]
    assert "alat" in result["ks_pvalues"]


def test_effect_sizes_all_columns():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw", "alat"], [])
    assert "bw" in result["effect_sizes"]
    assert "alat" in result["effect_sizes"]
    for col, es in result["effect_sizes"].items():
        assert "cohens_d" in es
        assert "interpretation" in es
        assert es["interpretation"] in ("negligible", "small", "medium", "large")


# ── Reliability breakdown ─────────────────────────────────────────────────────

def test_reliability_breakdown_structure():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw", "alat"], [])
    breakdown = result["reliability_breakdown"]
    assert "overall_score" in breakdown
    assert "per_endpoint" in breakdown
    assert "bw" in breakdown["per_endpoint"]
    ep = breakdown["per_endpoint"]["bw"]
    for field in ("mean_real", "std_real", "mean_vcg", "std_vcg",
                  "cohens_d", "ks_pvalue", "ci_lower", "ci_upper",
                  "interpretation", "interpretation_detail"):
        assert field in ep, f"Missing field in breakdown: {field}"


def test_reliability_breakdown_interpretation_values():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw"], [])
    interp = result["reliability_breakdown"]["per_endpoint"]["bw"]["interpretation"]
    assert interp in ("Excellent", "Good", "Acceptable", "Poor")


# ── Matching vs divergent distributions ───────────────────────────────────────

def test_matching_distributions_high_reliability():
    """Same distribution should yield a high reliability score."""
    real, vcg = make_matching_dfs(n_real=40, n_vcg=40, seed=99)
    result = StatsAgent().run(real, vcg, ["bw"], [])
    assert result["reliability_score"] > 0.55


def test_divergent_distributions_low_reliability():
    """Very different distributions should yield a low reliability score."""
    real, vcg = make_divergent_dfs(n_real=40, n_vcg=40, seed=99)
    result = StatsAgent().run(real, vcg, ["bw"], [])
    assert result["reliability_score"] < 0.6
    # Should also warn
    assert len(result["warnings"]) > 0


def test_divergent_large_effect_size():
    real, vcg = make_divergent_dfs()
    result = StatsAgent().run(real, vcg, ["bw"], [])
    d = result["effect_sizes"]["bw"]["cohens_d"]
    assert abs(d) > 2.0, f"Expected large Cohen's d, got {d}"


# ── Diagnostic plots ──────────────────────────────────────────────────────────

def test_diagnostic_plots_returned():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw"], [])
    plots = result["diagnostic_plots"]
    assert "dist_overlap" in plots
    assert "qq_plot" in plots
    # base64 strings should be non-empty
    assert len(plots["dist_overlap"]) > 100
    assert len(plots["qq_plot"]) > 100


def test_per_endpoint_plots_structure():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw", "alat"], [])
    ep_plots = result["per_endpoint_plots"]
    # Each endpoint with enough unique values should have density + qq
    for col in ("bw", "alat"):
        if col in ep_plots:
            assert "density" in ep_plots[col]
            assert "qq" in ep_plots[col]
            assert len(ep_plots[col]["density"]) > 100


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_no_valid_outcome_cols():
    real = pd.DataFrame({"bw": [1.0, 2.0]})
    vcg = pd.DataFrame({"bw": [1.0, 2.0]})
    result = StatsAgent().run(real, vcg, ["nonexistent"], [])
    # No valid columns → score defaults to the empty-dict fallback path
    assert 0.0 <= result["reliability_score"] <= 1.0


def test_single_row_each():
    """Single row per group should not crash."""
    real = pd.DataFrame({"bw": [250.0]})
    vcg = pd.DataFrame({"bw": [255.0]})
    result = StatsAgent().run(real, vcg, ["bw"], [])
    assert "reliability_score" in result


def test_power_estimates_returned():
    real, vcg = make_matching_dfs()
    result = StatsAgent().run(real, vcg, ["bw"], [])
    assert "power_estimates" in result
    assert "bw" in result["power_estimates"]
    pe = result["power_estimates"]["bw"]
    assert "achieved_power" in pe
    assert "n_for_80pct" in pe


def test_confidence_level_respected():
    """Different confidence levels should produce different CI widths."""
    real, vcg = make_matching_dfs(n_real=30, n_vcg=30)
    res90 = StatsAgent().run(real, vcg, ["bw"], [], confidence_level=0.90)
    res99 = StatsAgent().run(real, vcg, ["bw"], [], confidence_level=0.99)
    w90 = res90["reliability_breakdown"]["per_endpoint"]["bw"]["ci_width"]
    w99 = res99["reliability_breakdown"]["per_endpoint"]["bw"]["ci_width"]
    assert w99 > w90
