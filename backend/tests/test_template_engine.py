import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import template_engine
from template_engine import (
    _normalize_additional_terms,
    conformance_to_issues,
    generate_experiment_csv,
    get_template,
    load_templates,
    match_template,
    save_user_template,
    suggest_from_paper_extraction,
    suggest_templates,
    validate_against_template,
)


def _col(name, inferred_type="unknown", unit_guess=None, user_unit=None):
    return {
        "name": name,
        "inferred_type": inferred_type,
        "unit_guess": unit_guess,
        "user_unit": user_unit,
        "missing_pct": 0.0,
        "sample_values": [],
        "label": name,
    }


def _mnms_columns():
    return [
        _col("Unique_Animal_Identifier", inferred_type="identifier"),
        _col("Species"),
        _col("Strain_ILAR_Name"),
        _col("Sex"),
        _col("Date_of_Birth"),
        _col("Animal_Weight_at_Start", inferred_type="measurement", unit_guess="g"),
        _col("Weight_Unit"),
        _col("Animal_Vendor"),
        _col("XP_group"),
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


def test_load_builtin_templates():
    templates = load_templates(force=True)
    assert "arrive-v2" in templates
    assert "mnms-v1" in templates
    mnms = templates["mnms-v1"]
    assert "arrive-v2" in mnms.conforms_to
    parent_meta_ids = {m.id for m in templates["arrive-v2"].required_metadata}
    child_meta_ids = {m.id for m in mnms.required_metadata}
    assert parent_meta_ids.issubset(child_meta_ids)


def test_match_template_mnms():
    templates = load_templates(force=True)
    # Provide a realistic set of dataset-level metadata too so the score reflects
    # both the column match (70%) and metadata coverage (30%).
    mnms = templates["mnms-v1"]
    metadata = {m.id: f"value_for_{m.id}" for m in mnms.required_metadata}
    result = match_template(mnms, _mnms_columns(), metadata)
    assert result["score"] >= 0.9, f"Got score {result['score']} with reasons {result['reasons']}"
    # Even without metadata, full column match should still be the strong signal.
    result_no_meta = match_template(mnms, _mnms_columns(), {})
    assert result_no_meta["score"] >= 0.7


def test_match_template_unrelated():
    templates = load_templates(force=True)
    cols = [_col("foo"), _col("bar"), _col("baz"), _col("quux")]
    for tpl in templates.values():
        result = match_template(tpl, cols, {})
        assert result["score"] <= 0.5, f"{tpl.id} scored {result['score']}"


def test_suggest_templates_threshold():
    templates = load_templates(force=True)
    cols = _mnms_columns()
    out = suggest_templates(templates, cols, {})
    assert len(out) >= 1
    assert out[0]["id"] == "mnms-v1"
    assert out[0]["score"] >= out[-1]["score"]


def test_validate_satisfied():
    templates = load_templates(force=True)
    report = validate_against_template(templates["mnms-v1"], _mnms_columns(), {})
    column_entries = [r for r in report if r["is_column_field"]]
    missing_cols = [r for r in column_entries if r["status"] == "missing"]
    assert missing_cols == [], f"Unexpected missing columns: {[r['field_id'] for r in missing_cols]}"
    meta_entries = [r for r in report if not r["is_column_field"]]
    assert all(r["status"] == "missing" for r in meta_entries)


def test_validate_partial_unit():
    templates = load_templates(force=True)
    cols = [c for c in _mnms_columns() if c["name"] != "Weight_Unit"]
    weight = next(c for c in cols if c["name"] == "Animal_Weight_at_Start")
    weight["unit_guess"] = None
    weight["user_unit"] = None
    report = validate_against_template(templates["mnms-v1"], cols, {})
    weight_entry = next(r for r in report if r["field_id"] == "weight_start")
    assert weight_entry["status"] == "partial"


def test_conformance_to_issues_shape():
    templates = load_templates(force=True)
    report = validate_against_template(templates["mnms-v1"], [], {})
    issues = conformance_to_issues(report, "mnms-v1")
    assert issues, "Expected issues from empty columns/metadata"
    required_fields = {"id", "severity", "category", "column", "problem", "why_it_matters", "suggested_fix"}
    for issue in issues:
        assert required_fields.issubset(issue.keys())
        assert issue["category"] == "template_compliance"
        assert issue["id"].startswith("template_mnms-v1_")
        assert issue["severity"] in ("high", "medium", "low")


def test_user_template_upload(tmp_path, monkeypatch):
    fake_user_dir = tmp_path / "user"
    monkeypatch.setattr(template_engine, "USER_TEMPLATES_DIR", fake_user_dir)
    monkeypatch.setattr(template_engine, "_CACHE", {})
    yaml_body = """
id: test-custom-001
name: Test Custom
version: 0.1.0
description: Test custom template
required_columns:
  - id: my_col
    name_patterns: [my_special_col]
    severity: high
required_metadata:
  - id: my_meta
    severity: medium
"""
    tpl = save_user_template(yaml_body, source_format="yaml")
    assert tpl.id == "test-custom-001"
    assert tpl.source == "user"
    templates = load_templates(force=True)
    assert "test-custom-001" in templates
    saved_file = fake_user_dir / "test-custom-001.yaml"
    assert saved_file.exists()


def test_invalid_template_rejected(tmp_path, monkeypatch):
    fake_user_dir = tmp_path / "user"
    monkeypatch.setattr(template_engine, "USER_TEMPLATES_DIR", fake_user_dir)
    bad_yaml = """
name: Missing ID
version: 0.0.1
"""
    with pytest.raises((ValueError, Exception)):
        save_user_template(bad_yaml, source_format="yaml")


def test_user_template_collision_rejected(tmp_path, monkeypatch):
    fake_user_dir = tmp_path / "user"
    monkeypatch.setattr(template_engine, "USER_TEMPLATES_DIR", fake_user_dir)
    yaml_body = """
id: mnms-v1
name: Hijack
version: 0.0.1
"""
    with pytest.raises(ValueError):
        save_user_template(yaml_body, source_format="yaml")


def test_generate_experiment_csv_can_filter_selected_fields():
    tpl = load_templates(force=True)["mnms-v1"]
    extraction = {
        "dataset_metadata": {"species": "Mus musculus"},
        "vcg_hints": {
            "control_group_label": "Control",
            "treatment_group_label": "Treatment",
            "n_control": 2,
            "n_treatment": 2,
        },
    }
    csv_text = generate_experiment_csv(
        tpl,
        extraction,
        include_field_ids=["subject_id", "xp_group", "outcome"],
    )
    first_line = csv_text.splitlines()[0]
    assert first_line == "unique_animal_identifier,xp_group,outcome_measure"


def test_suggest_from_paper_extraction_uses_additional_terms():
    templates = load_templates(force=True)
    extraction = {
        "dataset_metadata": {"keywords": [], "study_type": None, "species": None},
        "arrive": {},
        "vcg_hints": {},
    }
    candidates = suggest_from_paper_extraction(extraction, templates, additional_terms=["arrive"])
    arrive_candidate = next(c for c in candidates if c["id"] == "arrive-v2")
    assert any("additional terms matched" in r for r in arrive_candidate["reasons"])


def test_normalize_additional_terms_deduplicates_and_trims():
    terms = _normalize_additional_terms(["  ARRIVE ", "arrive", "", "  in vivo "])
    assert terms == ["arrive", "in vivo"]
