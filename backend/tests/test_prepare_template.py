"""Tests for the PREPARE template + ARRIVE/PREPARE crosswalk template.

Covers:
 - Loading of the two new builtin templates.
 - YAML shape of prepare-v1 (42 entries, all carry prepare_section).
 - conforms_to merge into arrive-prepare-crosswalk-v1.
 - Crosswalk auto-satisfaction (PREPARE → ARRIVE, one-directional).
 - Conformance entry shape additions (arrive_section / prepare_section keys).
 - ARRIVE-only regression: assigning arrive-v2 still yields 47 entries with
   arrive_section populated and prepare_section None.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
def prepare_tpl(templates):
    return templates["prepare-v1"]


@pytest.fixture
def crosswalk_tpl(templates):
    return templates["arrive-prepare-crosswalk-v1"]


@pytest.fixture
def arrive_tpl(templates):
    return templates["arrive-v2"]


# ── Loading & YAML shape ─────────────────────────────────────────────────────


def test_prepare_templates_load(templates):
    """Both new builtin templates are picked up by load_templates."""
    assert "prepare-v1" in templates
    assert "arrive-prepare-crosswalk-v1" in templates
    # Sanity: prior templates still load alongside.
    assert "arrive-v2" in templates


def test_prepare_v1_yaml_shape(prepare_tpl):
    """prepare-v1 declares 42 required_metadata items, each with prepare_section."""
    assert len(prepare_tpl.required_metadata) == 42
    missing_section = [
        m.id for m in prepare_tpl.required_metadata if not m.prepare_section
    ]
    assert missing_section == [], (
        f"PREPARE entries without prepare_section: {missing_section}"
    )
    # All PREPARE field_ids share the `prepare_` prefix, which the engine relies
    # on to disambiguate from ARRIVE ids.
    bad_prefix = [
        m.id for m in prepare_tpl.required_metadata if not m.id.startswith("prepare_")
    ]
    assert bad_prefix == [], (
        f"PREPARE entries without prepare_ prefix: {bad_prefix}"
    )


def test_crosswalk_inherits_both_parents(arrive_tpl, prepare_tpl, crosswalk_tpl):
    """conforms_to=[arrive-v2, prepare-v1] merges full field sets into crosswalk."""
    arrive_ids = {m.id for m in arrive_tpl.required_metadata}
    prepare_ids = {m.id for m in prepare_tpl.required_metadata}
    crosswalk_ids = {m.id for m in crosswalk_tpl.required_metadata}

    assert arrive_ids.issubset(crosswalk_ids), "Missing ARRIVE ids in crosswalk"
    assert prepare_ids.issubset(crosswalk_ids), "Missing PREPARE ids in crosswalk"
    # IDs are disjoint by design (prepare_ prefix), so the union equals the merge.
    assert crosswalk_ids == (arrive_ids | prepare_ids)


# ── Crosswalk auto-satisfaction ──────────────────────────────────────────────


def test_crosswalk_arrive_satisfies_prepare(crosswalk_tpl):
    """ARRIVE field filled auto-satisfies a PREPARE entry that lists it in crosswalk."""
    report = validate_against_template(
        crosswalk_tpl, [], {"humane_endpoints": "Animals reaching 20% body weight loss"}
    )

    by_id = {r["field_id"]: r for r in report}

    arrive_entry = by_id["humane_endpoints"]
    assert arrive_entry["status"] == "satisfied"
    assert arrive_entry["satisfied_by"] == {"metadata": "humane_endpoints"}

    prepare_entry = by_id["prepare_humane_endpoints"]
    assert prepare_entry["status"] == "satisfied"
    assert prepare_entry["satisfied_by"] is not None
    assert prepare_entry["satisfied_by"].get("via_crosswalk") is True
    assert prepare_entry["satisfied_by"].get("metadata") == "humane_endpoints"


def test_crosswalk_prepare_does_not_satisfy_arrive(crosswalk_tpl):
    """Crosswalk is one-directional (PREPARE → ARRIVE) per the prepare-v1 YAML.

    The crosswalk lists live on PREPARE entries (pointing at ARRIVE sibling ids),
    so filling the PREPARE side alone leaves the ARRIVE counterpart unsatisfied.
    """
    report = validate_against_template(
        crosswalk_tpl,
        [],
        {"prepare_humane_endpoints": "Pre-defined endpoint criteria"},
    )
    by_id = {r["field_id"]: r for r in report}

    # PREPARE entry is directly satisfied by its own metadata key.
    prepare_entry = by_id["prepare_humane_endpoints"]
    assert prepare_entry["status"] == "satisfied"
    # No via_crosswalk flag — this was a direct hit, not a crosswalk resolution.
    assert prepare_entry["satisfied_by"] == {"metadata": "prepare_humane_endpoints"}

    # ARRIVE entry stays missing — crosswalk does NOT propagate PREPARE → ARRIVE.
    arrive_entry = by_id["humane_endpoints"]
    assert arrive_entry["status"] == "missing"
    assert arrive_entry["satisfied_by"] is None


@pytest.mark.parametrize(
    "arrive_field,prepare_field",
    [
        ("humane_endpoints", "prepare_humane_endpoints"),
        ("severity_classification", "prepare_severity_classification"),
        ("personnel_training", "prepare_staff_competence"),
    ],
)
def test_crosswalk_auto_satisfaction_parametrised(
    crosswalk_tpl, arrive_field, prepare_field
):
    """Filling any ARRIVE field listed in a PREPARE entry's crosswalk satisfies it."""
    report = validate_against_template(
        crosswalk_tpl, [], {arrive_field: "value"}
    )
    by_id = {r["field_id"]: r for r in report}
    entry = by_id[prepare_field]
    assert entry["status"] == "satisfied", (
        f"Expected {prepare_field} satisfied via {arrive_field}, got {entry}"
    )
    assert entry["satisfied_by"].get("via_crosswalk") is True
    assert entry["satisfied_by"].get("metadata") == arrive_field


# ── Conformance entry shape ──────────────────────────────────────────────────


def test_conformance_entry_shape_includes_section_keys(crosswalk_tpl):
    """Every entry has both arrive_section and prepare_section keys (may be None),
    plus the legacy `section` field populated for backward compatibility."""
    report = validate_against_template(crosswalk_tpl, [], {})
    assert report, "Crosswalk template should yield a non-empty conformance report"

    for entry in report:
        assert "arrive_section" in entry, (
            f"Missing arrive_section key in entry: {entry}"
        )
        assert "prepare_section" in entry, (
            f"Missing prepare_section key in entry: {entry}"
        )
        assert "section" in entry, (
            f"Missing legacy section key in entry: {entry}"
        )
        # `section` should be a non-empty string when either subsection is set.
        if entry["arrive_section"] or entry["prepare_section"]:
            assert isinstance(entry["section"], str) and entry["section"], (
                f"Empty section despite arrive/prepare subsection set: {entry}"
            )


# ── ARRIVE-only regression ───────────────────────────────────────────────────


def test_arrive_only_validation_unchanged(arrive_tpl):
    """Assigning arrive-v2 alone yields 47 entries, all with arrive_section
    populated and prepare_section None — no regression from the new fields."""
    report = validate_against_template(arrive_tpl, [], {})
    assert len(report) == 47

    for entry in report:
        # is_column_field is False for all ARRIVE entries (metadata-only template).
        assert entry["is_column_field"] is False
        assert entry["arrive_section"], (
            f"ARRIVE entry missing arrive_section: {entry}"
        )
        # prepare_section key must be present, value None for pure ARRIVE entries.
        assert "prepare_section" in entry
        assert entry["prepare_section"] is None
