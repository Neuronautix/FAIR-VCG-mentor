"""Headless end-to-end integration test (Milestone D).

Exercises the REAL pipeline — CSV profiling → FAIR scoring → VCG generation →
statistics — with NO HTTP layer and WITHOUT importing fastapi/main (which is
broken in this environment). Engine functions are called directly.

Dataset: ``test_data/FAIR-VCG_example_data.csv`` has a ``group`` column with
control value ``Vehicle`` (10 rows) and treatment ``CompoundA`` (30 rows), plus
numeric outcome columns (organ weights, clinical chemistry).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from csv_profiler import profile_csv
from entity_detector import detect_entity_structure
from fair_engine import compute_fair_score, detect_issues
from vcg.context_model import (
    ColumnRoles,
    VCGConfig,
    DEFAULT_VCG_SESSION,
    roles_to_dict,
    config_to_dict,
)
from vcg.vcg_engine import run_vcg_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = REPO_ROOT / "test_data" / "FAIR-VCG_example_data.csv"

CONTROL_VALUE = "Vehicle"
TREATMENT_COL = "group"
OUTCOME_COLS = [
    "body_weight_end_g",
    "liver_weight_g",
    "kidney_weight_g",
    "alt_u_l",
    "ast_u_l",
    "creatinine_umol_l",
]


@pytest.fixture(scope="module")
def profile():
    assert DATA_FILE.exists(), f"missing test dataset: {DATA_FILE}"
    return profile_csv(DATA_FILE.read_bytes(), DATA_FILE.name)


# ── Profiling ─────────────────────────────────────────────────────────────────


def test_profiling_returns_columns_and_df(profile):
    assert "columns" in profile and isinstance(profile["columns"], list)
    assert len(profile["columns"]) > 0
    df = profile["df"]
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert TREATMENT_COL in df.columns
    # Control value really is present in the group column.
    assert CONTROL_VALUE in set(df[TREATMENT_COL].astype(str))


# ── FAIR scoring ──────────────────────────────────────────────────────────────


def test_fair_score_is_valid(profile):
    columns = profile["columns"]
    df = profile["df"]
    table_structure = detect_entity_structure(df, columns)
    issues = detect_issues(profile["import_info"], columns, table_structure)
    score = compute_fair_score(
        import_info=profile["import_info"],
        columns=columns,
        table_structure=table_structure,
        metadata={},
        issues=issues,
    )
    assert isinstance(score, dict)
    total = score["fair_score"]
    assert isinstance(total, (int, float))
    # Sum of dimension maxima is 105 in this rubric.
    assert 0 <= total <= 105
    for dim in ("findable", "accessible", "interoperable", "reusable"):
        assert 0 <= score[dim]["score"] <= score[dim]["max_score"]


# ── VCG pipeline end-to-end ───────────────────────────────────────────────────


def _build_session(profile) -> dict:
    session = {
        "df": profile["df"],
        "columns": profile["columns"],
        "vcg": DEFAULT_VCG_SESSION(),
    }
    roles = ColumnRoles(
        treatment_col=TREATMENT_COL,
        control_value=CONTROL_VALUE,
        treatment_value="CompoundA",
        outcome_cols=list(OUTCOME_COLS),
        covariate_cols=[],
    )
    # Deterministic config; n_control = 10 (< 15) so 'auto' selects synthetic.
    cfg = VCGConfig(method="auto", n_synthetic=30, seed=123)
    session["vcg"]["column_roles"] = roles_to_dict(roles)
    session["vcg"]["vcg_config"] = config_to_dict(cfg)
    return session


@pytest.mark.slow
def test_vcg_pipeline_end_to_end(profile):
    session = _build_session(profile)
    sessions_dict: dict = {}

    run_vcg_pipeline("test-ds", session, sessions_dict, save_fn=None)

    vcg = session["vcg"]
    assert vcg["vcg_status"] == "done", f"pipeline failed: {vcg.get('vcg_error')}"

    results = vcg["vcg_results"]
    assert results is not None

    # Synthetic dataframe / CSV with rows > 0.
    csv_text = results["vcg_csv"]
    assert isinstance(csv_text, str) and csv_text.strip()
    from io import StringIO

    vcg_df = pd.read_csv(StringIO(csv_text))
    assert len(vcg_df) > 0
    assert len(vcg_df) == results["n_subjects_vcg"]

    # Expected outcome columns are present in the synthetic output.
    for col in OUTCOME_COLS:
        assert col in vcg_df.columns, f"missing outcome column {col} in VCG output"

    # Reliability score is a valid probability.
    rel = results["reliability_score"]
    assert isinstance(rel, (int, float))
    assert 0.0 <= rel <= 1.0

    # The session was stored back into the sessions dict by the pipeline.
    assert sessions_dict.get("test-ds") is session


@pytest.mark.slow
def test_vcg_pipeline_is_deterministic(profile):
    s1 = _build_session(profile)
    s2 = _build_session(profile)
    run_vcg_pipeline("ds1", s1, {}, save_fn=None)
    run_vcg_pipeline("ds2", s2, {}, save_fn=None)
    assert s1["vcg"]["vcg_status"] == "done"
    assert s2["vcg"]["vcg_status"] == "done"
    assert s1["vcg"]["vcg_results"]["vcg_csv"] == s2["vcg"]["vcg_results"]["vcg_csv"]
