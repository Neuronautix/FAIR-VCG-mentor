import json
import os
import sys

TEST_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(TEST_DIR, ".."))
sys.path.insert(0, TEST_DIR)

from fixtures.project_schemas import (
    complete_vcg_ready_schema,
    conflicting_aliases_units_schema_draft,
    hallucinated_role_reference_schema,
)
from project_schema import normalize_project_schema, validate_project_schema


def test_complete_vcg_ready_fixture_validates_and_serializes():
    result = validate_project_schema(complete_vcg_ready_schema())

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["warnings"] == []

    schema = result["schema"]
    assert schema["status"] == "approved"
    assert schema["vcg_readiness"]["ready"] is True
    assert schema["vcg_roles"]["subject_id"] == "animal_id"
    assert schema["vcg_roles"]["treatment_col"] == "treatment_group"
    assert schema["vcg_roles"]["control_value"] == "vehicle"
    assert schema["vcg_roles"]["outcome_cols"] == ["tumor_volume_mm3"]
    assert schema["vcg_roles"]["covariate_cols"] == ["baseline_weight_g"]

    tumor_volume = next(col for col in schema["columns"] if col["name"] == "tumor_volume_mm3")
    assert tumor_volume["evidence"] == ["ev_paper_1_tumor"]

    serialized = json.dumps(schema, sort_keys=True)
    assert json.loads(serialized)["name"] == "vcg_ready_oncology_project"


def test_conflicting_aliases_units_fixture_normalizes_and_warns_for_missing_evidence():
    result = validate_project_schema(conflicting_aliases_units_schema_draft())

    assert result["ok"] is True
    assert result["errors"] == []
    assert "columns.dose_mg_per_kg.evidence references unknown evidence id 'ev_missing_dose_column'." in result["warnings"]
    assert "units.dose_mg_per_kg.evidence references unknown evidence id 'ev_missing_dose_unit'." in result["warnings"]
    assert "controlled_values.treatment_group.evidence references unknown evidence id 'ev_missing_alias_source'." in result["warnings"]

    schema = result["schema"]
    assert schema["status"] == "draft"
    assert schema["vcg_roles"]["subject_id"] == "animal_id"
    assert schema["vcg_roles"]["treatment_col"] == "treatment_group"
    assert schema["vcg_roles"]["outcome_cols"] == ["tumor_volume"]
    assert schema["units"]["dose_mg_per_kg"]["accepted_units"] == ["mg/kg", "mg kg-1", "mg"]
    assert schema["units"]["drug_concentration"]["accepted_units"] == ["mg/ml", "mg"]
    assert schema["controlled_values"]["treatment_group"]["aliases"]["vehicle"] == "drug_a"

    serialized = json.dumps(schema, sort_keys=True)
    assert json.loads(serialized)["controlled_values"]["treatment_group"]["canonical_values"] == [
        "vehicle",
        "drug_a",
        "drug_b",
    ]


def test_hallucinated_role_reference_fixture_errors_but_remains_json_serializable():
    result = validate_project_schema(hallucinated_role_reference_schema())

    assert result["ok"] is False
    assert "vcg_roles.subject_id references unknown column 'mouse_identifier_from_llm'." in result["errors"]
    assert "vcg_roles.outcome_cols references unknown column 'imagined_response_score'." in result["errors"]
    assert "vcg_roles.covariate_cols references unknown column 'baseline_weight_from_unseen_table'." in result["errors"]
    assert result["warnings"] == []

    schema = result["schema"]
    assert schema["vcg_roles"]["treatment_col"] == "treatment_group"
    assert schema["vcg_roles"]["outcome_cols"] == ["tumor_volume", "imagined_response_score"]
    assert json.loads(json.dumps(schema, sort_keys=True))["status"] == "needs_review"


def test_project_schema_fixtures_return_deep_copies():
    first = normalize_project_schema(complete_vcg_ready_schema())
    second = normalize_project_schema(complete_vcg_ready_schema())

    first["columns"][0]["name"] = "mutated"

    assert second["columns"][0]["name"] == "animal_id"
