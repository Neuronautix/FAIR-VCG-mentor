import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fair_engine import compute_fair_score
from template_engine import get_template, load_templates, validate_against_template
from vcg.vcg_engine import _run_template_analyses
from vcg.vcg_router import _apply_template_defaults
from vcg.vcg_wizard import infer_column_roles


# ── Helpers ──────────────────────────────────────────────────────────────────

def _col(name, inferred_type="unknown", unit_guess=None, user_unit=None, sample_values=None):
    return {
        "name": name,
        "label": name,
        "inferred_type": inferred_type,
        "data_type": "string",
        "unit_guess": unit_guess,
        "user_unit": user_unit,
        "user_description": None,
        "missing_pct": 0.0,
        "missing_values": 0,
        "sample_values": sample_values or [],
        "allowed_values": None,
        "confidence": 0.8,
        "user_label": None,
        "user_type": None,
        "required": False,
        "uri": None,
    }


def _mnms_columns():
    return [
        _col("Unique_Animal_Identifier", inferred_type="identifier"),
        _col("Species"),
        _col("Strain_ILAR_Name"),
        _col("Sex", inferred_type="biological_descriptor"),
        _col("Date_of_Birth"),
        _col("Animal_Weight_at_Start", inferred_type="measurement", unit_guess="g"),
        _col("Weight_Unit"),
        _col("Animal_Vendor"),
        _col("XP_group", inferred_type="experimental_condition", sample_values=["Vehicle", "DrugA"]),
        _col("DVC Cage Identifier"),
        _col("Outcome_Measure", inferred_type="measurement", unit_guess="cm"),
        _col("Unit_of_Measurement"),
        _col("treatment_date"),
        _col("housing_density"),
        _col("anaesthesia"),
        _col("analgesia"),
        _col("humane_endpoint"),
        _col("adverse_event"),
        _col("inclusion_flag"),
        _col("exclusion_flag"),
        _col("randomisation"),
        _col("blinding"),
    ]


def _table_structure():
    return {
        "table_shape": "one_row_per_entity",
        "row_represents": "animal",
        "primary_entity": "animal",
        "secondary_entity": None,
        "detected_identifiers": [],
        "detected_measurements": [],
        "detected_categoricals": [],
        "detected_time_vars": [],
    }


def _import_info():
    return {
        "filename": "study.csv",
        "n_rows": 30,
        "n_columns": 22,
        "delimiter": ",",
        "encoding": "utf-8",
        "has_header": True,
        "empty_columns": [],
        "duplicate_columns": [],
        "malformed_rows": [],
    }


# ── A. Wizard prefill override ───────────────────────────────────────────────

def test_wizard_prefill_applies_template_defaults():
    columns = _mnms_columns()
    prefill = infer_column_roles(columns, _table_structure(), {})
    templates = load_templates(force=True)
    tpl = templates["mnms-v1"]

    merged = _apply_template_defaults(prefill, tpl, columns)

    assert merged["column_roles"]["treatment_col"] == "XP_group"
    outcomes = merged["column_roles"]["outcome_cols"]
    assert any(name in ("Outcome_Measure", "Value") for name in outcomes), outcomes
    assert merged["template_locked"], "Expected non-empty template_locked"
    assert merged.get("clustering_unit") == "DVC Cage Identifier"
    assert merged.get("clustering_warning"), "Expected clustering_warning to be set"


def test_wizard_prefill_no_template_preserves_heuristics():
    columns = _mnms_columns()
    prefill = infer_column_roles(columns, _table_structure(), {})

    # No template applied: just ensure the helper still leaves a sane shape.
    merged = _apply_template_defaults(prefill, None, columns)

    assert merged["template_locked"] == []
    assert "clustering_warning" not in merged
    assert "clustering_unit" not in merged
    # Heuristic-detected fields should still be present.
    assert "column_roles" in merged
    assert merged["column_roles"]["treatment_col"] == "XP_group"


# ── B. Predefined analyses ───────────────────────────────────────────────────

def test_predefined_analyses_arrive_completeness():
    templates = load_templates(force=True)
    tpl = templates["mnms-v1"]
    # Mix of statuses across two standards
    template_validation = [
        {"standard": "ARRIVE", "status": "satisfied", "field_id": "species", "severity": "high"},
        {"standard": "ARRIVE", "status": "missing", "field_id": "sex", "severity": "high"},
        {"standard": "ARRIVE", "status": "partial", "field_id": "weight", "severity": "medium"},
        {"standard": "MNMS", "status": "satisfied", "field_id": "xp_group", "severity": "high"},
        {"standard": "MNMS", "status": "missing", "field_id": "subject_id", "severity": "high"},
    ]
    session = {
        "template_id": "mnms-v1",
        "template_validation": template_validation,
        "df": pd.DataFrame(),
        "vcg": {"column_roles": {}},
    }

    out = _run_template_analyses(session, {})
    arrive = next((a for a in out if a["id"] == "arrive_completeness"), None)
    assert arrive is not None
    assert arrive["status"] == "ok"
    res = arrive["result"]
    assert "by_standard" in res
    assert res["by_standard"]["ARRIVE"]["satisfied"] == 1
    assert res["by_standard"]["ARRIVE"]["missing"] == 1
    assert res["by_standard"]["ARRIVE"]["partial"] == 1
    assert res["by_standard"]["MNMS"]["satisfied"] == 1
    assert res["by_standard"]["MNMS"]["missing"] == 1
    assert "essential_10_satisfied" in res
    assert "essential_10_total" in res


def test_predefined_analyses_cage_effect():
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "DVC Cage Identifier": (["C1"] * 6) + (["C2"] * 6),
        "Outcome_Measure": np.concatenate([
            rng.normal(10, 1, 6),
            rng.normal(15, 1, 6),
        ]),
    })
    session = {
        "template_id": "mnms-v1",
        "template_validation": [],
        "df": df,
        "vcg": {"column_roles": {"outcome_cols": ["Outcome_Measure"]}},
    }
    out = _run_template_analyses(session, {})
    cage = next((a for a in out if a["id"] == "cage_effect_check"), None)
    assert cage is not None, out
    assert cage["status"] == "ok", cage
    res = cage["result"]
    for key in ("icc", "interpretation", "outcome_col", "cluster_col", "n_clusters"):
        assert key in res
    assert res["n_clusters"] == 2
    assert res["outcome_col"] == "Outcome_Measure"
    assert res["cluster_col"] == "DVC Cage Identifier"


def test_predefined_analyses_failure_isolated():
    # No matching cluster/outcome column in df -> analysis fails, others still ok
    df = pd.DataFrame({"some_col": [1, 2, 3]})
    session = {
        "template_id": "mnms-v1",
        "template_validation": [
            {"standard": "ARRIVE", "status": "satisfied", "field_id": "species", "severity": "high"},
        ],
        "df": df,
        "vcg": {"column_roles": {"outcome_cols": []}},
    }
    out = _run_template_analyses(session, {})
    by_id = {a["id"]: a for a in out}
    # arrive_completeness still ok
    assert by_id["arrive_completeness"]["status"] == "ok"
    # cage_effect_check should fail without crashing
    assert by_id["cage_effect_check"]["status"] == "error"
    assert by_id["cage_effect_check"]["error"]


# ── C. FAIR score template bonus ─────────────────────────────────────────────

def _base_metadata():
    return {
        "title": "Body Weight Study",
        "description": "BW measurements in rats.",
        "creator": "Jane Smith",
        "contact_email": "jane@example.com",
        "license": "CC BY 4.0",
        "date_created": "2025-01-15",
        "protocol_reference": "doi:10.1234/protocol.1",
        "keywords": ["body weight"],
        "base_uri": "https://example.com/datasets/bw",
        "institution": "Example U",
        "access_conditions": "Freely available",
    }


def test_fair_score_template_bonus():
    columns = [
        _col("animal_id", inferred_type="identifier"),
        _col("body_weight_g", inferred_type="measurement", unit_guess="g"),
    ]
    columns[0]["user_description"] = "Unique animal ID"
    columns[1]["user_description"] = "Body weight in grams"

    metadata = _base_metadata()
    issues: list = []

    fully_satisfied = [
        {"status": "satisfied", "field_id": "f1", "standard": "ARRIVE", "severity": "high"},
        {"status": "satisfied", "field_id": "f2", "standard": "ARRIVE", "severity": "medium"},
    ]
    res = compute_fair_score(
        _import_info(), columns, _table_structure(), metadata, issues,
        template_validation=fully_satisfied,
    )
    reusable = res["reusable"]
    assert reusable["criteria"].get("declares_template_conformance") is True
    assert reusable["score"] >= 30 - 5  # at minimum gained the 5 pts
    # The template criterion contributed 5 points

    res_none = compute_fair_score(
        _import_info(), columns, _table_structure(), metadata, issues,
        template_validation=[],
    )
    reusable_none = res_none["reusable"]
    assert reusable_none["criteria"].get("declares_template_conformance") is False
    # The score from the no-template case should be 5 points lower (criterion went 5 -> 0)
    assert reusable["score"] - reusable_none["score"] == 5
