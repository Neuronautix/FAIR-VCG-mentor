"""Tests for the Template Fill backend helpers.

Covers the pure functions exposed by ``backend/template_completion.py``:

  - ``build_completion_report`` — per-field completion report assembly,
    section grouping (ARRIVE + PREPARE), severity buckets, paper hints,
    crosswalk auto-satisfaction.
  - ``fill_from_paper_extraction`` — bulk-fill of missing fields from a
    paper extraction payload, plus idempotency.
  - ``PREPARE_PROMPTS`` — drift check that the canonical prompts table
    covers every ``prepare_`` field in ``prepare-v1``.

The HTTP route smoke test (test_completion_route_returns_report) is
intentionally omitted: no existing ``backend/tests/*`` file wires up a
FastAPI ``TestClient`` against ``main.app`` (init wiring with sessions
+ save/load injection is non-trivial for a smoke test), and the task
brief explicitly allows skipping it when this is the case. The pure
functions exercised below are the substance of the new endpoints —
each route handler is a thin shim around them.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from template_completion import (  # noqa: E402
    PREPARE_PROMPTS,
    build_completion_report,
    fill_from_paper_extraction,
)
from template_engine import (  # noqa: E402
    load_templates,
    validate_against_template,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def templates():
    """Force a fresh load so we always pick up current YAML on disk."""
    return load_templates(force=True)


@pytest.fixture
def arrive_tpl(templates):
    return templates["arrive-v2"]


@pytest.fixture
def prepare_tpl(templates):
    return templates["prepare-v1"]


@pytest.fixture
def crosswalk_tpl(templates):
    return templates["arrive-prepare-crosswalk-v1"]


def _conformance(tpl, metadata):
    return validate_against_template(tpl, [], metadata)


# ── build_completion_report ──────────────────────────────────────────────────


def test_build_completion_report_arrive_only(arrive_tpl):
    """ARRIVE template with empty metadata → everything missing, zero satisfied."""
    report = _conformance(arrive_tpl, {})
    completion = build_completion_report(arrive_tpl, {}, [], None, report)

    totals = completion["totals"]
    assert totals["total"] == len(arrive_tpl.required_metadata)
    assert totals["missing"] == totals["total"]
    assert totals["satisfied_direct"] == 0
    assert totals["satisfied_via_crosswalk"] == 0
    assert totals["partial"] == 0

    # Sanity: shape matches the documented contract.
    assert completion["template_id"] == arrive_tpl.id
    assert completion["template_name"] == arrive_tpl.name
    assert isinstance(completion["fields"], list)
    assert len(completion["fields"]) == totals["total"]
    for f in completion["fields"]:
        assert f["status"] == "missing"
        assert f["via_crosswalk"] is False
        assert f["source"] is None
        assert f["satisfied_by_field"] is None


def test_build_completion_report_crosswalk_via_arrive(crosswalk_tpl):
    """ARRIVE field filled → satisfies its PREPARE sibling via crosswalk."""
    metadata = {"humane_endpoints": "Animals reaching 20% body weight loss"}
    report = _conformance(crosswalk_tpl, metadata)
    completion = build_completion_report(crosswalk_tpl, metadata, [], None, report)

    totals = completion["totals"]
    assert totals["satisfied_direct"] >= 1, totals
    assert totals["satisfied_via_crosswalk"] >= 1, totals

    by_id = {f["field_id"]: f for f in completion["fields"]}
    prepare_field = by_id["prepare_humane_endpoints"]
    assert prepare_field["status"] == "satisfied"
    assert prepare_field["via_crosswalk"] is True
    assert prepare_field["satisfied_by_field"] == "humane_endpoints"
    assert prepare_field["source"] == "crosswalk"
    # When satisfied via crosswalk, the value preview should reflect the
    # sibling field's actual value.
    assert prepare_field["value"] == "Animals reaching 20% body weight loss"

    arrive_field = by_id["humane_endpoints"]
    assert arrive_field["status"] == "satisfied"
    assert arrive_field["via_crosswalk"] is False
    assert arrive_field["source"] == "direct"


def test_completion_by_section_groups_dual_standards(crosswalk_tpl):
    """``by_section`` carries both ARRIVE and PREPARE buckets.

    A crosswalk-template field may have BOTH ``arrive_section`` and
    ``prepare_section`` populated (this is true for the 21 PREPARE
    entries that are also ARRIVE-aligned). The implementation emits one
    row per (kind, label) pair per field — so a field with both keys
    counts in **two** section buckets.

    Invariant (matches implementation in template_completion.py, lines
    192-212): the sum of ``total`` across ``by_section`` equals the
    number of (kind, label) memberships across all fields, NOT
    ``totals.total``. We assert this exactly: it is sum of (1 if
    arrive_section else 0) + (1 if prepare_section else 0) per field.
    """
    report = _conformance(crosswalk_tpl, {})
    completion = build_completion_report(crosswalk_tpl, {}, [], None, report)

    by_section = completion["by_section"]
    kinds = {b["kind"] for b in by_section}
    assert "arrive" in kinds
    assert "prepare" in kinds

    # Expected section memberships, computed directly from the template.
    expected_memberships = sum(
        (1 if m.arrive_section else 0) + (1 if m.prepare_section else 0)
        for m in crosswalk_tpl.required_metadata
    )
    actual = sum(b["total"] for b in by_section)
    assert actual == expected_memberships, (
        f"Expected {expected_memberships} section memberships, got {actual}. "
        f"This is greater than totals.total ({completion['totals']['total']}) "
        f"because crosswalk fields with BOTH arrive_section AND prepare_section "
        f"are counted once per (kind, label) pair."
    )
    # And it must be strictly greater than totals.total — confirming the
    # dual-counting behaviour rather than per-field deduplication.
    assert actual > completion["totals"]["total"]


def test_completion_fields_carry_prompts_for_prepare_missing(prepare_tpl):
    """Missing PREPARE field → ``prompt`` is a non-empty string.

    Satisfied field → ``prompt`` is None (set only when status != satisfied
    per template_completion.py line 144-146).
    """
    # Pick a PREPARE field we know has a prompt and is naturally missing.
    target_fid = "prepare_humane_endpoints"
    assert target_fid in PREPARE_PROMPTS  # sanity

    # All missing case
    report = _conformance(prepare_tpl, {})
    completion = build_completion_report(prepare_tpl, {}, [], None, report)
    by_id = {f["field_id"]: f for f in completion["fields"]}
    missing_field = by_id[target_fid]
    assert missing_field["status"] == "missing"
    assert isinstance(missing_field["prompt"], str)
    assert missing_field["prompt"]  # non-empty

    # Now satisfy it directly and re-check.
    metadata = {target_fid: "Pre-defined endpoint criteria"}
    report2 = _conformance(prepare_tpl, metadata)
    completion2 = build_completion_report(prepare_tpl, metadata, [], None, report2)
    by_id2 = {f["field_id"]: f for f in completion2["fields"]}
    sat_field = by_id2[target_fid]
    assert sat_field["status"] == "satisfied"
    assert sat_field["prompt"] is None


def test_completion_paper_hint_surfaces(arrive_tpl):
    """Paper-extraction hint shows up on missing ARRIVE field that maps to it.

    ARRIVE's ``outcome_measures`` field is one of the direct
    ``_PAPER_ARRIVE_KEYS`` entries — when present in the paper extraction
    it should surface as ``paper_hint`` on the (still-missing) template field.
    """
    paper_extraction = {
        "arrive": {
            "outcome_measures": {
                "value": "Tumour volume at day 28",
                "status": "found",
            },
        },
        "dataset_metadata": {},
    }
    report = _conformance(arrive_tpl, {})
    completion = build_completion_report(
        arrive_tpl, {}, [], paper_extraction, report
    )
    by_id = {f["field_id"]: f for f in completion["fields"]}

    om_field = by_id["outcome_measures"]
    assert om_field["status"] == "missing"
    assert om_field["paper_hint"] == "Tumour volume at day 28"


def test_completion_paper_hint_absent_when_already_satisfied(arrive_tpl):
    """Paper hints are only attached to missing/partial fields."""
    paper_extraction = {
        "arrive": {
            "outcome_measures": {
                "value": "Tumour volume at day 28",
                "status": "found",
            },
        },
        "dataset_metadata": {},
    }
    metadata = {"outcome_measures": "Already filled directly"}
    report = _conformance(arrive_tpl, metadata)
    completion = build_completion_report(
        arrive_tpl, metadata, [], paper_extraction, report
    )
    by_id = {f["field_id"]: f for f in completion["fields"]}
    om_field = by_id["outcome_measures"]
    assert om_field["status"] == "satisfied"
    assert om_field["paper_hint"] is None


# ── fill_from_paper_extraction ───────────────────────────────────────────────


def test_fill_from_paper_extraction_round_trip(arrive_tpl):
    """Empty metadata + paper extraction → fields populated; second call is no-op."""
    paper_extraction = {
        "arrive": {
            "ethics_statement": {"value": "Approved by IACUC", "status": "found"},
            "study_design": {"value": "Randomised controlled", "status": "found"},
            "randomisation": {"value": "Block randomisation", "status": "found"},
            "blinding": {"value": "Double-blind", "status": "found"},
            "outcome_measures": {"value": "Tumour volume", "status": "found"},
        },
        "dataset_metadata": {
            "title": "A study title",
            "creator": "Dr Smith",
        },
    }

    updated, filled = fill_from_paper_extraction(arrive_tpl, {}, paper_extraction)
    assert filled, "Expected at least one filled record from paper extraction"

    filled_ids = {r["field_id"] for r in filled}
    # These ARRIVE field_ids are populated via _FIELD_LOOKUP_MAP entries
    # in template_engine.py — either direct arrive-key matches (e.g.
    # outcome_measures) or sibling resolutions (e.g. study_title from
    # dataset_metadata.title, procedures_description from
    # arrive.study_design).
    for expected_fid in {
        "study_title",
        "primary_contact",
        "outcome_measures",
        "procedures_description",
        "surgical_procedures",
    }:
        assert expected_fid in filled_ids, (
            f"{expected_fid} should have been filled from the paper extraction; "
            f"got {filled_ids}"
        )
        assert updated[expected_fid], f"{expected_fid} should have a non-empty value"

    # Each filled record carries the documented metadata.
    for rec in filled:
        assert rec["label"]
        assert rec["value"]
        assert rec["source"]
        assert "arrive_section" in rec
        assert "prepare_section" in rec
        assert rec["severity"] in {"high", "medium", "low"}

    # Idempotency: applying the same paper extraction to the freshly-filled
    # metadata yields no new fills.
    updated2, filled2 = fill_from_paper_extraction(
        arrive_tpl, updated, paper_extraction
    )
    assert filled2 == [], (
        f"Second fill should be a no-op; got {len(filled2)} new fills: {filled2}"
    )
    assert updated2 == updated


@pytest.mark.parametrize(
    "paper_extraction",
    [
        None,
        {},
        {"arrive": None, "dataset_metadata": None},
        {"arrive": "not a dict", "dataset_metadata": "nope"},
    ],
)
def test_fill_from_paper_extraction_handles_empty_or_malformed(
    arrive_tpl, paper_extraction
):
    """Empty / malformed paper extraction must not raise; returns metadata unchanged."""
    md = {"existing_key": "keep me"}
    updated, filled = fill_from_paper_extraction(arrive_tpl, md, paper_extraction)
    assert filled == []
    assert updated == md


# ── PREPARE prompts drift guard ──────────────────────────────────────────────


def test_paper_hint_surfaces_for_prepare_only_fields(prepare_tpl):
    """Paper hints for PREPARE-only template fields must surface from the
    new ``paper_extraction['prepare']`` block, not just from the ARRIVE
    block. Multiple template sub-items share one topic-level extraction
    key (e.g. ``literature_searches`` feeds 5 prepare_* fields)."""
    paper = {
        "arrive": {},
        "dataset_metadata": {},
        "prepare": {
            "literature_searches": {
                "value": "Searched PubMed, EMBASE; 12 papers reviewed.",
                "status": "found",
            },
            "facility_evaluation": {
                "value": "AAALAC accredited; visited 2026-02",
                "status": "found",
            },
            "necropsy": {
                "value": "Standard gross pathology + histology",
                "status": "found",
            },
        },
    }
    rep = validate_against_template(prepare_tpl, [], {})
    cr = build_completion_report(prepare_tpl, {}, [], paper, rep)
    by_id = {f["field_id"]: f for f in cr["fields"]}

    # All 5 literature-searches sub-items share the same topic hint
    for fid in (
        "prepare_clear_hypothesis",
        "prepare_systematic_reviews",
        "prepare_search_strategy",
        "prepare_species_relevance",
        "prepare_reproducibility_translatability",
    ):
        assert by_id[fid]["paper_hint"] == "Searched PubMed, EMBASE; 12 papers reviewed."
    assert by_id["prepare_facility_inspection"]["paper_hint"] == (
        "AAALAC accredited; visited 2026-02"
    )
    assert by_id["prepare_necropsy_plan"]["paper_hint"] == (
        "Standard gross pathology + histology"
    )


def test_fill_from_paper_uses_prepare_block(prepare_tpl):
    """Bulk-fill must populate PREPARE-only fields from the prepare block."""
    paper = {
        "arrive": {},
        "dataset_metadata": {},
        "prepare": {
            "humane_killing": {"value": "CO2 chamber per AVMA", "status": "found"},
            "necropsy": {"value": "Gross pathology + histology", "status": "found"},
        },
    }
    new_md, filled = fill_from_paper_extraction(prepare_tpl, {}, paper)
    filled_ids = {r["field_id"] for r in filled}
    assert "prepare_necropsy_plan" in filled_ids
    assert "prepare_killing_methods" in filled_ids
    assert new_md["prepare_necropsy_plan"] == "Gross pathology + histology"
    # Source path uses the prepare.<topic_key> notation
    necropsy_rec = next(r for r in filled if r["field_id"] == "prepare_necropsy_plan")
    assert necropsy_rec["source"] == "prepare.necropsy"


def test_PREPARE_PROMPTS_covers_all_prepare_fields(prepare_tpl):
    """Every ``prepare_*`` field in prepare-v1 must have a non-empty prompt."""
    missing_prompts = []
    for meta_spec in prepare_tpl.required_metadata:
        fid = meta_spec.id
        if not fid.startswith("prepare_"):
            continue
        prompt = PREPARE_PROMPTS.get(fid)
        if not prompt or not isinstance(prompt, str):
            missing_prompts.append(fid)
    assert missing_prompts == [], (
        f"PREPARE_PROMPTS is missing entries for: {missing_prompts}. "
        f"prepare_engine._PROMPTS has drifted from prepare-v1.yaml."
    )
