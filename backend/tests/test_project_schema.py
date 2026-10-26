import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from project_schema import (
    DEFAULT_PROJECT_SCHEMA,
    normalize_project_schema,
    project_schema_vcg_roles,
    validate_project_schema,
)


def test_default_project_schema_has_required_layers():
    schema = DEFAULT_PROJECT_SCHEMA()

    assert schema["schema_version"] == 1
    assert schema["metadata_fields"] == {}
    assert schema["columns"] == []
    assert schema["vcg_roles"]["outcome_cols"] == []
    assert schema["vcg_readiness"]["ready"] is False
    assert schema["evidence"] == []


def test_normalizes_legacy_fields_into_project_schema_contract():
    schema = normalize_project_schema({
        "name": "oncology_project",
        "metadata": {"species": {"value": "Mus musculus", "required": True, "source": "paper"}},
        "fields": [
            {"name": "animal_id", "role": "identifier", "confidence": 0.95},
            {"name": "group", "role": "treatment"},
            {"name": "tumor_volume", "role": "outcome", "unit": "mm3"},
        ],
        "vcg_roles": {"control_value": "vehicle"},
        "evidence": [{"id": "ev_1", "paper_id": "paper_1", "quote": "Tumor volume was measured."}],
    })

    assert schema["name"] == "oncology_project"
    assert schema["metadata_fields"]["species"]["value"] == "Mus musculus"
    assert schema["columns"][2]["name"] == "tumor_volume"
    assert schema["vcg_roles"]["subject_id"] == "animal_id"
    assert schema["vcg_roles"]["treatment_col"] == "group"
    assert schema["vcg_roles"]["outcome_cols"] == ["tumor_volume"]
    assert schema["vcg_roles"]["control_value"] == "vehicle"


def test_validation_rejects_vcg_roles_referencing_unknown_columns():
    result = validate_project_schema({
        "columns": [{"name": "animal_id", "role": "identifier"}],
        "vcg_roles": {
            "treatment_col": "missing_group",
            "control_value": "vehicle",
            "outcome_cols": ["missing_endpoint"],
        },
    })

    assert result["ok"] is False
    assert "vcg_roles.treatment_col references unknown column 'missing_group'." in result["errors"]
    assert "vcg_roles.outcome_cols references unknown column 'missing_endpoint'." in result["errors"]


def test_validation_warns_for_missing_vcg_critical_fields_and_bad_evidence_refs():
    result = validate_project_schema({
        "columns": [{"name": "animal_id", "role": "identifier", "evidence": ["ev_missing"]}],
        "evidence": [],
    })

    assert result["ok"] is True
    assert "columns.animal_id.evidence references unknown evidence id 'ev_missing'." in result["warnings"]
    assert "VCG-critical field missing: treatment_col." in result["warnings"]
    assert "VCG-critical field missing: control_value." in result["warnings"]
    assert "VCG-critical field missing: outcome_cols." in result["warnings"]


def test_project_schema_vcg_roles_returns_wizard_shape():
    roles = project_schema_vcg_roles({
        "columns": [
            {"name": "animal_id", "role": "identifier"},
            {"name": "group", "role": "treatment"},
            {"name": "body_weight", "role": "outcome"},
            {"name": "sex", "role": "covariate"},
        ],
        "vcg_roles": {"control_value": "vehicle", "treatment_value": "drug"},
    })

    assert roles["subject_id"] == "animal_id"
    assert roles["treatment_col"] == "group"
    assert roles["control_value"] == "vehicle"
    assert roles["treatment_value"] == "drug"
    assert roles["outcome_cols"] == ["body_weight"]
    assert roles["covariate_cols"] == ["sex"]
