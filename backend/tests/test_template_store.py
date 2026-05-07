import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from template_store import (
    apply_template,
    load_template,
    low_confidence_columns,
    record_corrections,
    save_template,
)


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def _cols():
    return [
        {
            "name": "animal_id",
            "label": "Animal ID",
            "inferred_type": "identifier",
            "confidence": 0.95,
            "user_type": None,
            "user_unit": None,
            "unit_guess": None,
            "user_label": None,
            "user_description": None,
            "uri": None,
            "allowed_values": None,
            "required": False,
            "description": None,
            "reason_codes": ["name:identifier_pattern"],
        },
        {
            "name": "mystery_col",
            "label": "Mystery Col",
            "inferred_type": "unknown",
            "confidence": 0.40,
            "user_type": None,
            "user_unit": None,
            "unit_guess": None,
            "user_label": None,
            "user_description": None,
            "uri": None,
            "allowed_values": None,
            "required": False,
            "description": None,
            "reason_codes": ["fallback:no_signal"],
        },
    ]


def test_save_and_load_roundtrip(db_path):
    cols = _cols()
    cols[1]["user_type"] = "metadata_field"
    cols[1]["user_label"] = "Confirmed metadata"

    save_template(db_path, "sig123", cols, source_filename="study.csv")

    loaded = load_template(db_path, "sig123")
    assert loaded is not None
    assert loaded["signature"] == "sig123"
    assert loaded["source_filename"] == "study.csv"
    assert "mystery_col" in loaded["mappings"]
    assert loaded["mappings"]["mystery_col"]["user_type"] == "metadata_field"


def test_load_missing_returns_none(db_path):
    assert load_template(db_path, "does-not-exist") is None


def test_apply_template_marks_columns(db_path):
    template = {
        "mystery_col": {
            "user_type": "metadata_field",
            "user_label": "Confirmed metadata",
            "inferred_type": "metadata_field",
        },
    }
    cols = _cols()
    n = apply_template(cols, template)
    assert n == 1
    mystery = next(c for c in cols if c["name"] == "mystery_col")
    assert mystery["user_type"] == "metadata_field"
    assert mystery["confidence"] == 1.0
    assert "template:applied" in mystery["reason_codes"]


def test_low_confidence_columns_filters_correctly():
    cols = _cols()
    out = low_confidence_columns(cols, threshold=0.65)
    assert len(out) == 1
    assert out[0]["name"] == "mystery_col"


def test_low_confidence_skips_user_overridden():
    cols = _cols()
    cols[1]["user_type"] = "metadata_field"
    out = low_confidence_columns(cols)
    assert out == []


def test_low_confidence_skips_template_applied():
    cols = _cols()
    cols[1]["reason_codes"] = ["template:applied"]
    out = low_confidence_columns(cols)
    assert out == []


def test_record_corrections_counts_type_and_label():
    session = {"columns": _cols()}
    updates = [
        {
            "name": "mystery_col",
            "user_type": "metadata_field",
            "user_label": "Renamed",
            "user_unit": "g",
        }
    ]
    metrics = record_corrections(session, updates)
    assert metrics["total_updates"] == 1
    assert metrics["type_corrections"] == 1
    assert metrics["label_corrections"] == 1
    assert metrics["unit_corrections"] == 1


def test_record_corrections_ignores_matching_values():
    session = {"columns": _cols()}
    # Setting user_type equal to inferred_type is not a correction.
    updates = [{"name": "animal_id", "user_type": "identifier"}]
    metrics = record_corrections(session, updates)
    assert metrics["total_updates"] == 1
    assert metrics["type_corrections"] == 0
