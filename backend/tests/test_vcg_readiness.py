import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vcg_readiness import assess_vcg_readiness


def test_readiness_blocks_missing_required_vcg_fields():
    result = assess_vcg_readiness({
        "columns": [{"name": "animal_id", "role": "identifier"}],
    })

    assert result["ready"] is False
    assert result["score"] < 100
    assert "Missing VCG-critical field: treatment_col." in result["blocking"]
    assert "Missing VCG-critical field: control_value." in result["blocking"]
    assert "Missing VCG-critical field: outcome_cols." in result["blocking"]
    assert any("reference arm" in item for item in result["consequences"])
    assert any("no endpoint" in item for item in result["consequences"])


def test_readiness_blocks_invalid_role_references():
    result = assess_vcg_readiness({
        "columns": [{"name": "animal_id", "role": "identifier"}],
        "vcg_roles": {
            "treatment_col": "missing_group",
            "control_value": "vehicle",
            "outcome_cols": ["missing_endpoint"],
        },
    })

    assert result["ready"] is False
    assert "vcg_roles.treatment_col references unknown column 'missing_group'." in result["blocking"]
    assert "vcg_roles.outcome_cols references unknown column 'missing_endpoint'." in result["blocking"]
    assert any("Invalid role references" in item for item in result["consequences"])


def test_readiness_warns_for_vcg_risks_but_can_be_ready():
    result = assess_vcg_readiness({
        "columns": [
            {
                "name": "animal_id",
                "role": "identifier",
                "confidence": 0.95,
                "review_status": "approved",
                "evidence": ["ev_subject"],
            },
            {
                "name": "group",
                "role": "treatment",
                "confidence": 0.95,
                "review_status": "approved",
                "evidence": ["ev_group"],
            },
            {
                "name": "tumor_volume",
                "role": "outcome",
                "confidence": 0.40,
                "review_status": "must_ask",
            },
        ],
        "vcg_roles": {"control_value": "vehicle"},
        "evidence": [
            {"id": "ev_subject", "supports": ["animal_id"], "quote": "Animals were tracked by ID."},
            {"id": "ev_group", "supports": ["group"], "quote": "Treatment groups were assigned."},
        ],
    })

    assert result["ready"] is True
    assert result["blocking"] == []
    assert "No covariate columns selected for VCG adjustment." in result["warnings"]
    assert "Outcome column 'tumor_volume' is missing a known unit." in result["warnings"]
    assert "VCG-critical column 'tumor_volume' for outcome_cols has low confidence (0.40)." in result["warnings"]
    assert "VCG-critical column 'tumor_volume' for outcome_cols has review status 'must_ask'." in result["warnings"]
    assert "VCG-critical column 'tumor_volume' for outcome_cols has no evidence." in result["warnings"]
    assert any("endpoint harmonization" in item for item in result["consequences"])
    assert result["score"] < 100


def test_readiness_is_high_when_required_roles_are_evidenced_and_units_known():
    result = assess_vcg_readiness({
        "columns": [
            {
                "name": "animal_id",
                "role": "identifier",
                "confidence": 0.95,
                "review_status": "approved",
                "evidence": ["ev_subject"],
            },
            {
                "name": "group",
                "role": "treatment",
                "confidence": 0.95,
                "review_status": "approved",
                "evidence": ["ev_group"],
            },
            {
                "name": "body_weight",
                "role": "outcome",
                "unit": "g",
                "confidence": 0.95,
                "review_status": "approved",
                "evidence": ["ev_outcome"],
            },
            {
                "name": "sex",
                "role": "covariate",
                "confidence": 0.95,
                "review_status": "approved",
                "evidence": ["ev_covariate"],
            },
        ],
        "vcg_roles": {"control_value": "vehicle"},
        "evidence": [
            {"id": "ev_subject", "quote": "Animal identifiers were recorded."},
            {"id": "ev_group", "quote": "Groups were assigned."},
            {"id": "ev_outcome", "quote": "Body weight was measured in grams."},
            {"id": "ev_covariate", "quote": "Sex was recorded."},
        ],
    })

    assert result == {
        "ready": True,
        "score": 100,
        "blocking": [],
        "warnings": [],
        "consequences": [],
    }
