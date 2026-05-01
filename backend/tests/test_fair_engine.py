import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fair_engine import compute_fair_score, detect_issues


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_col(
    name,
    inferred_type="unknown",
    data_type="string",
    missing_pct=0,
    unit_guess=None,
    user_unit=None,
    user_description=None,
    allowed_values=None,
):
    return {
        "name": name,
        "label": name,
        "description": None,
        "inferred_type": inferred_type,
        "data_type": data_type,
        "unique_values": 5,
        "missing_values": 0,
        "missing_pct": missing_pct,
        "sample_values": [],
        "unit_guess": unit_guess,
        "confidence": 0.8,
        "user_label": None,
        "user_description": user_description,
        "user_unit": user_unit,
        "user_type": None,
        "allowed_values": allowed_values,
        "required": False,
        "uri": None,
    }


def make_import_info():
    return {
        "filename": "test.csv",
        "n_rows": 10,
        "n_columns": 3,
        "delimiter": ",",
        "encoding": "utf-8",
        "has_header": True,
        "empty_columns": [],
        "duplicate_columns": [],
        "malformed_rows": [],
    }


def make_table_structure():
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


# ── FAIR score: no metadata → low score ───────────────────────────────────────

def test_score_with_no_metadata():
    columns = [make_col("value")]
    result = compute_fair_score(make_import_info(), columns, make_table_structure(), {}, [])
    # No title, no creator, no license, no description — must be very low
    assert result["fair_score"] < 30


# ── FAIR score: full metadata → higher score ──────────────────────────────────

def test_score_with_full_metadata():
    columns = [
        make_col("animal_id", inferred_type="identifier", user_description="Unique animal ID"),
        make_col("body_weight_g", inferred_type="measurement", unit_guess="g",
                 user_description="Body weight in grams"),
    ]
    metadata = {
        "title": "Body Weight Study",
        "description": "Longitudinal body weight measurements in rats.",
        "creator": "Jane Smith",
        "contact_email": "jane@example.com",
        "license": "CC BY 4.0",
        "date_created": "2025-01-15",
        "protocol_reference": "doi:10.1234/protocol.1",
        "keywords": ["body weight", "rat", "pharmacology"],
        "base_uri": "https://example.com/datasets/bw-study",
        "institution": "Example University",
        "access_conditions": "Freely available",
    }
    result = compute_fair_score(make_import_info(), columns, make_table_structure(), metadata, [])
    assert result["fair_score"] >= 50


# ── Column descriptions improve score ─────────────────────────────────────────

def test_column_descriptions_improve_score():
    base_metadata = {"title": "Study", "license": "CC BY 4.0"}
    cols_without = [
        make_col("animal_id", inferred_type="identifier"),
        make_col("body_weight_g", inferred_type="measurement", unit_guess="g"),
    ]
    cols_with = [
        make_col("animal_id", inferred_type="identifier", user_description="Unique animal ID"),
        make_col("body_weight_g", inferred_type="measurement", unit_guess="g",
                 user_description="Body weight in grams"),
    ]
    ts = make_table_structure()
    score_without = compute_fair_score(make_import_info(), cols_without, ts, base_metadata, [])["fair_score"]
    score_with = compute_fair_score(make_import_info(), cols_with, ts, base_metadata, [])["fair_score"]
    assert score_with > score_without


# ── Issue detection ────────────────────────────────────────────────────────────

def test_no_identifier_issue():
    columns = [
        make_col("body_weight_g", inferred_type="measurement", unit_guess="g"),
        make_col("sex", inferred_type="biological_descriptor"),
    ]
    issues = detect_issues(make_import_info(), columns, make_table_structure())
    ids = [i["id"] for i in issues]
    assert "no_identifier" in ids
    no_id_issue = next(i for i in issues if i["id"] == "no_identifier")
    assert no_id_issue["severity"] == "high"


def test_missing_unit_issue():
    columns = [
        make_col("animal_id", inferred_type="identifier"),
        # measurement with no unit_guess and no user_unit
        make_col("response", inferred_type="measurement", unit_guess=None, user_unit=None),
    ]
    issues = detect_issues(make_import_info(), columns, make_table_structure())
    ids = [i["id"] for i in issues]
    assert any(i.startswith("missing_unit_") for i in ids)


def test_high_missing_values_issue():
    columns = [
        make_col("animal_id", inferred_type="identifier"),
        make_col("body_weight_g", inferred_type="measurement", unit_guess="g", missing_pct=25),
    ]
    issues = detect_issues(make_import_info(), columns, make_table_structure())
    ids = [i["id"] for i in issues]
    assert any(i.startswith("high_missing_") for i in ids)


def test_ambiguous_name_issue():
    columns = [
        make_col("animal_id", inferred_type="identifier"),
        make_col("value"),
    ]
    issues = detect_issues(make_import_info(), columns, make_table_structure())
    ids = [i["id"] for i in issues]
    assert any(i.startswith("ambiguous_name_") for i in ids)


def test_no_issues_when_all_good():
    # Provide identifier + measurement with unit — no_identifier should be absent
    columns = [
        make_col("animal_id", inferred_type="identifier"),
        make_col("body_weight_g", inferred_type="measurement", unit_guess="g"),
    ]
    issues = detect_issues(make_import_info(), columns, make_table_structure())
    ids = [i["id"] for i in issues]
    assert "no_identifier" not in ids
