import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hitl import add_suggestion, approve_and_apply
from schema_agent_loop import rank_schema_questions, should_stop_schema_agent


def _session():
    return {
        "columns": [
            {"name": "animal_id", "inferred_type": "identifier", "unit_guess": None},
            {"name": "dose_mg_kg", "inferred_type": "measurement", "unit_guess": "mg/kg"},
            {"name": "group", "inferred_type": "experimental_condition", "sample_values": ["control", "drug"]},
        ],
        "metadata": {},
    }


def test_new_hitl_categories_accept_draft_payloads():
    cases = [
        ("schema_field", "dose_mg_kg", {"field_name": "dose", "description": "Dose administered"}),
        ("schema_conflict", "group", {"conflict": "group values disagree", "options": ["control", "vehicle"]}),
        ("ontology_mapping", "animal_id", {"source_label": "mouse", "curie": "NCBITaxon:10090"}),
        ("unit_normalization", "dose_mg_kg", {"source_unit": "mpk", "target_unit": "mg/kg"}),
        ("vcg_assumption", "treatment_col", {"role": "treatment_col", "value": "group"}),
        ("corpus_schema_approval", "mnms-v1", {"schema_id": "mnms-v1", "decision": "needs_review"}),
    ]

    for category, target, payload in cases:
        suggestion = add_suggestion(
            _session(),
            category=category,
            target=target,
            source="test",
            title=f"{category} draft",
            rationale="test rationale",
            payload=payload,
            confidence=0.6,
        )
        assert suggestion["status"] == "pending", suggestion["validation"]


def test_new_hitl_categories_reject_empty_or_invalid_payloads():
    invalid_cases = [
        ("schema_field", "dose_mg_kg", {}),
        ("schema_conflict", "group", {"options": []}),
        ("ontology_mapping", "animal_id", {"source_label": "mouse"}),
        ("unit_normalization", "dose_mg_kg", {"source_unit": "mpk"}),
        ("vcg_assumption", "unknown", {"role": "not_a_vcg_role"}),
        ("corpus_schema_approval", "mnms-v1", {"schema_id": "mnms-v1", "decision": "maybe"}),
    ]

    for category, target, payload in invalid_cases:
        suggestion = add_suggestion(
            _session(),
            category=category,
            target=target,
            source="test",
            title=f"{category} draft",
            rationale="test rationale",
            payload=payload,
            confidence=0.6,
        )
        assert suggestion["status"] == "invalid"
        assert suggestion["validation"]["errors"]


def test_schema_planning_approval_records_note():
    session = _session()
    suggestion = add_suggestion(
        session,
        category="vcg_assumption",
        target="treatment_col",
        source="test",
        title="Treatment assumption",
        rationale="group looks like the treatment column",
        payload={"role": "treatment_col", "value": "group"},
        confidence=0.7,
    )

    applied, result = approve_and_apply(session, suggestion["id"])

    assert applied["status"] == "applied"
    assert result["applied"] is True
    assert session["schema_planning"]["approved_notes"][0]["category"] == "vcg_assumption"


def test_rank_schema_questions_by_impact_and_confidence_semantics():
    ranked = rank_schema_questions([
        {
            "id": "low-confidence-low-impact",
            "category": "schema_field",
            "field": "notes",
            "scientific_impact": "low",
            "confidence": 0.05,
        },
        {
            "id": "conflict",
            "category": "schema_conflict",
            "field": "group",
            "scientific_impact": "high",
            "confidence": 0.95,
        },
        {
            "id": "safe-draft",
            "category": "schema_field",
            "field": "lab_notes",
            "scientific_impact": "low",
            "confidence": 0.95,
        },
        {
            "id": "vcg-critical",
            "category": "vcg_assumption",
            "field": "treatment_col",
            "confidence": 0.8,
            "vcg_critical": True,
        },
    ])

    decisions = {question["id"]: question["decision"] for question in ranked}
    assert decisions["conflict"] == "must_ask"
    assert decisions["vcg-critical"] == "must_ask"
    assert decisions["safe-draft"] == "auto_accept"
    assert decisions["low-confidence-low-impact"] == "reject"
    assert ranked[0]["decision"] == "must_ask"


def test_stopping_rule_requires_no_must_ask_and_resolved_vcg_fields():
    questions = [
        {"field": "treatment_col", "confidence": 0.7, "vcg_critical": True},
        {"field": "outcome_cols", "confidence": 0.95, "status": "approved", "vcg_critical": True},
    ]

    decision = should_stop_schema_agent(
        questions,
        resolved_fields={"subject_id", "outcome_cols"},
        required_vcg_fields={"subject_id", "treatment_col", "outcome_cols"},
        iteration=2,
        max_iterations=5,
    )
    assert decision["stop"] is False
    assert decision["reason"] == "needs_questions"
    assert "treatment_col" in decision["unresolved_vcg_fields"]
    assert decision["unresolved_must_ask"]

    resolved = [
        {"field": "treatment_col", "confidence": 0.7, "status": "approved", "vcg_critical": True},
        {"field": "outcome_cols", "confidence": 0.95, "status": "approved", "vcg_critical": True},
    ]
    ready = should_stop_schema_agent(
        resolved,
        resolved_fields={"subject_id"},
        required_vcg_fields={"subject_id", "treatment_col", "outcome_cols"},
        iteration=3,
        max_iterations=5,
    )
    assert ready["stop"] is True
    assert ready["reason"] == "ready"


def test_stopping_rule_iteration_cap_stops_loop():
    decision = should_stop_schema_agent(
        [{"field": "treatment_col", "confidence": 0.2, "vcg_critical": True}],
        resolved_fields=set(),
        required_vcg_fields={"treatment_col"},
        iteration=6,
        max_iterations=6,
    )

    assert decision["stop"] is True
    assert decision["reason"] == "iteration_cap"
