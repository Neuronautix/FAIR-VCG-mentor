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
    validate_against_template,
)

# The 7 EQIPD categories and the expected number of Core Requirements in each.
EXPECTED_SECTIONS = {
    "Research team": 2,
    "Quality culture": 3,
    "Data integrity": 4,
    "Research processes": 5,
    "Continuous performance": 3,
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
