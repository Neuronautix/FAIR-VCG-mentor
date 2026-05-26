import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vcg.vcg_router import _apply_project_schema_defaults


def test_project_schema_defaults_fill_empty_vcg_prefill_roles():
    prefill = {
        "column_roles": {
            "subject_id": None,
            "treatment_col": None,
            "control_value": None,
            "treatment_value": None,
            "outcome_cols": [],
            "covariate_cols": [],
            "time_col": None,
            "exclude_cols": [],
        },
        "warnings": [],
    }
    session = {
        "study_corpus": {
            "consensus_schema": {
                "source": "expert",
                "schema": {
                    "columns": [
                        {"name": "animal_id", "role": "identifier"},
                        {"name": "group", "role": "treatment"},
                        {"name": "body_weight", "role": "outcome"},
                        {"name": "sex", "role": "covariate"},
                    ],
                    "vcg_roles": {
                        "control_value": "vehicle",
                        "treatment_value": "drug",
                    },
                },
            }
        }
    }

    out = _apply_project_schema_defaults(prefill, session)

    assert out["column_roles"]["subject_id"] == "animal_id"
    assert out["column_roles"]["treatment_col"] == "group"
    assert out["column_roles"]["control_value"] == "vehicle"
    assert out["column_roles"]["treatment_value"] == "drug"
    assert out["column_roles"]["outcome_cols"] == ["body_weight"]
    assert out["column_roles"]["covariate_cols"] == ["sex"]
    assert set(out["project_schema_applied"]) >= {
        "subject_id", "treatment_col", "control_value", "treatment_value",
        "outcome_cols", "covariate_cols",
    }


def test_project_schema_defaults_do_not_override_existing_or_template_values():
    prefill = {
        "column_roles": {
            "subject_id": "existing_id",
            "treatment_col": "existing_group",
            "control_value": "control",
            "outcome_cols": ["existing_endpoint"],
            "covariate_cols": [],
        },
        "template_locked": ["treatment_col", "control_value"],
    }
    session = {
        "study_corpus": {
            "consensus_schema": {
                "schema": {
                    "columns": [
                        {"name": "animal_id", "role": "identifier"},
                        {"name": "group", "role": "treatment"},
                        {"name": "body_weight", "role": "outcome"},
                        {"name": "age", "role": "covariate"},
                    ],
                    "vcg_roles": {"control_value": "vehicle"},
                },
            }
        }
    }

    out = _apply_project_schema_defaults(prefill, session)

    assert out["column_roles"]["subject_id"] == "existing_id"
    assert out["column_roles"]["treatment_col"] == "existing_group"
    assert out["column_roles"]["control_value"] == "control"
    assert out["column_roles"]["outcome_cols"] == ["existing_endpoint"]
    assert out["column_roles"]["covariate_cols"] == ["age"]
    assert out["template_locked"] == ["treatment_col", "control_value"]
