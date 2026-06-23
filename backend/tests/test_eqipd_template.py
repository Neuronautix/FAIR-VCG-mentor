"""Tests for the EQIPD Quality System template (eqipd-v1).

EQIPD is filled through the generic Template Fill workspace, so these
tests verify (a) the template loads with all 18 Core Requirements as
``required_metadata``, (b) each requirement carries an ``eqipd_section``
category and inline ``guidance`` text, and (c) the completion report
surfaces the EQIPD section grouping and uses the guidance as the
per-field prompt that the LLM-suggest endpoint also forwards to the model.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from template_completion import (  # noqa: E402
    build_completion_report,
    fields_to_llm_prompt,
)
from template_engine import (  # noqa: E402
    load_templates,
    suggest_from_paper_extraction,
    validate_against_template,
)

# The 7 EQIPD categories and the expected number of Core Requirements in each.
EXPECTED_SECTIONS = {
    "Research team": 2,
    "Quality culture": 3,
    "Data integrity": 4,
    "Research processes": 5,
    "Continuous improvement": 3,
    "Sustainability": 1,
}
EXPECTED_TOTAL = sum(EXPECTED_SECTIONS.values())  # 18


@pytest.fixture
def eqipd_tpl():
    return load_templates(force=True)["eqipd-v1"]


def _conformance(tpl, metadata):
    return validate_against_template(tpl, [], metadata)


def test_eqipd_template_loads_with_18_requirements(eqipd_tpl):
    assert eqipd_tpl.id == "eqipd-v1"
    assert eqipd_tpl.required_columns == []
    assert len(eqipd_tpl.required_metadata) == EXPECTED_TOTAL


def test_every_requirement_has_section_and_guidance(eqipd_tpl):
    sections: dict[str, int] = {}
    for meta in eqipd_tpl.required_metadata:
        assert meta.id.startswith("eqipd_"), meta.id
        assert meta.eqipd_section, f"{meta.id} missing eqipd_section"
        assert meta.guidance and meta.guidance.strip(), f"{meta.id} missing guidance"
        assert meta.severity in {"high", "medium", "low"}
        sections[meta.eqipd_section] = sections.get(meta.eqipd_section, 0) + 1
    assert sections == EXPECTED_SECTIONS


def test_conformance_all_missing_carries_eqipd_section(eqipd_tpl):
    report = _conformance(eqipd_tpl, {})
    assert len(report) == EXPECTED_TOTAL
    for entry in report:
        assert entry["status"] == "missing"
        assert entry["is_column_field"] is False
        assert entry["arrive_section"] is None or isinstance(entry["arrive_section"], str)
        assert entry["eqipd_section"], entry
        # The legacy ``section`` falls back to the EQIPD category.
        assert entry["section"] == entry["eqipd_section"] or entry["arrive_section"]


def test_completion_report_surfaces_eqipd_sections_and_guidance(eqipd_tpl):
    report = _conformance(eqipd_tpl, {})
    completion = build_completion_report(eqipd_tpl, {}, [], None, report)

    assert completion["totals"]["total"] == EXPECTED_TOTAL
    assert completion["totals"]["missing"] == EXPECTED_TOTAL

    # by_section carries EQIPD buckets covering all 7 categories.
    eqipd_buckets = [b for b in completion["by_section"] if b["kind"] == "eqipd"]
    assert {b["label"] for b in eqipd_buckets} == set(EXPECTED_SECTIONS)
    assert {b["label"]: b["total"] for b in eqipd_buckets} == EXPECTED_SECTIONS

    # Each missing field exposes its EQIPD section + the Core Requirement
    # guidance as the prompt (so the user/LLM sees what it asks for).
    for f in completion["fields"]:
        assert f["eqipd_section"] in EXPECTED_SECTIONS
        assert isinstance(f["prompt"], str) and f["prompt"]


def test_satisfied_field_drops_prompt(eqipd_tpl):
    target = "eqipd_process_owner"
    metadata = {target: "Dr Jane Doe, QA lead, recorded in the unit QMS."}
    report = _conformance(eqipd_tpl, metadata)
    completion = build_completion_report(eqipd_tpl, metadata, [], None, report)
    by_id = {f["field_id"]: f for f in completion["fields"]}
    assert by_id[target]["status"] == "satisfied"
    assert by_id[target]["prompt"] is None


def test_llm_prompt_payload_includes_guidance(eqipd_tpl):
    field_ids = [m.id for m in eqipd_tpl.required_metadata]
    payloads = fields_to_llm_prompt(eqipd_tpl, field_ids, {}, [], "")
    assert len(payloads) == EXPECTED_TOTAL
    for p in payloads:
        assert p["eqipd_section"] in EXPECTED_SECTIONS
        assert p["guidance"] and p["guidance"].strip()


# ── Cross-standard crosswalk auto-satisfaction ───────────────────────────────

# EQIPD requirement → an ARRIVE/PREPARE field (declared in eqipd-v1 crosswalks)
# whose presence in shared session metadata should auto-satisfy it.
CROSSWALK_CASES = {
    "eqipd_legislation_compliance": "ethics_statement",
    "eqipd_knowledge_claim_declaration": "prepare_clear_hypothesis",
    "eqipd_personnel_training": "personnel_training",
    "eqipd_protocols_available": "procedures_description",
    "eqipd_risk_assessment": "prepare_risk_assessment",
}


def test_eqipd_autosatisfies_from_other_standard_metadata(eqipd_tpl):
    """Filling an ARRIVE/PREPARE field in shared metadata auto-satisfies the
    EQIPD requirement that crosswalks to it — even though those fields are not
    declared in the standalone EQIPD template."""
    metadata = {sibling: f"value for {sibling}" for sibling in CROSSWALK_CASES.values()}
    report = _conformance(eqipd_tpl, metadata)
    by_id = {e["field_id"]: e for e in report}

    for eqipd_id, sibling in CROSSWALK_CASES.items():
        entry = by_id[eqipd_id]
        assert entry["status"] == "satisfied", f"{eqipd_id} should be satisfied"
        assert entry["satisfied_by"] == {"metadata": sibling, "via_crosswalk": True}

    # Completion report reflects the crosswalk + borrows the sibling's value.
    completion = build_completion_report(eqipd_tpl, metadata, [], None, report)
    cfields = {f["field_id"]: f for f in completion["fields"]}
    f = cfields["eqipd_personnel_training"]
    assert f["via_crosswalk"] is True
    assert f["satisfied_by_field"] == "personnel_training"
    assert f["value"] == "value for personnel_training"
    assert f["source"] == "crosswalk"


def test_eqipd_non_crosswalked_fields_stay_missing(eqipd_tpl):
    """Requirements without a crosswalk are unaffected by sibling metadata."""
    metadata = {"personnel_training": "Annual GLP refresher completed."}
    report = _conformance(eqipd_tpl, metadata)
    by_id = {e["field_id"]: e for e in report}
    assert by_id["eqipd_personnel_training"]["status"] == "satisfied"
    # A data-integrity requirement has no honest crosswalk → still missing.
    assert by_id["eqipd_data_storage_security"]["status"] == "missing"


# ── Paper-based auto-suggestion ──────────────────────────────────────────────


def _eqipd_in(candidates):
    return next((c for c in candidates if c["id"] == "eqipd-v1"), None)


def test_eqipd_suggested_for_preclinical_paper(eqipd_tpl):
    """EQIPD surfaces as a candidate for an in vivo paper, ranked below a true
    reporting template (ARRIVE), and never auto-assigns (no required columns)."""
    extraction = {
        "arrive": {
            "study_design": {"value": "Randomised controlled", "status": "found"},
            "outcome_measures": {"value": "Tumour volume", "status": "found"},
        },
        "dataset_metadata": {
            "species": "Mus musculus",
            "keywords": ["reproducibility", "data integrity"],
        },
        "vcg_hints": {},
    }
    templates = load_templates(force=True)
    candidates = suggest_from_paper_extraction(extraction, templates)
    eqipd = _eqipd_in(candidates)
    assert eqipd is not None, "EQIPD should be suggested for a preclinical paper"
    assert eqipd["score"] > 0
    arrive = next((c for c in candidates if c["id"] == "arrive-v2"), None)
    assert arrive is not None
    assert arrive["score"] >= eqipd["score"], "ARRIVE should outrank EQIPD here"


def test_eqipd_quality_keywords_boost_score(eqipd_tpl):
    """Explicit quality-system keywords raise EQIPD's score vs a bare paper."""
    base = {
        "arrive": {},
        "dataset_metadata": {"species": "Rattus norvegicus", "keywords": []},
        "vcg_hints": {},
    }
    boosted = {
        "arrive": {},
        "dataset_metadata": {
            "species": "Rattus norvegicus",
            "keywords": ["quality assurance", "SOP", "audit trail"],
        },
        "vcg_hints": {},
    }
    templates = load_templates(force=True)
    base_score = _eqipd_in(suggest_from_paper_extraction(base, templates))["score"]
    boosted_score = _eqipd_in(suggest_from_paper_extraction(boosted, templates))["score"]
    assert boosted_score > base_score
