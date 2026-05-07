import io
import csv
import sys
import os
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from csv_profiler import (
    categorical_cardinality,
    dataset_signature,
    profile_csv,
    values_are_numeric,
    values_look_like_dates,
    values_look_like_identifiers,
)

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"


def make_csv(*rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────────

BASIC_CSV = make_csv(
    ["animal_id", "sex", "body_weight_g"],
    ["A001", "male", "25.3"],
    ["A002", "female", "22.1"],
    ["A003", "male", "27.8"],
    ["A004", "female", "24.0"],
    ["A005", "male", "26.5"],
)


def _col(result, name):
    """Return the column dict for a given column name."""
    return next(c for c in result["columns"] if c["name"] == name)


# ── Basic profiling ────────────────────────────────────────────────────────────

def test_profile_basic():
    result = profile_csv(BASIC_CSV, "test.csv")
    assert "import_info" in result
    assert "columns" in result
    assert "df" in result
    assert "content" in result
    assert result["import_info"]["n_rows"] == 5
    assert result["import_info"]["n_columns"] == 3


# ── Semantic type inference ────────────────────────────────────────────────────

def test_identifier_detected():
    result = profile_csv(BASIC_CSV, "test.csv")
    col = _col(result, "animal_id")
    assert col["inferred_type"] == "identifier"
    assert col["confidence"] >= 0.9


def test_measurement_detected():
    result = profile_csv(BASIC_CSV, "test.csv")
    col = _col(result, "body_weight_g")
    assert col["inferred_type"] == "measurement"


def test_biological_descriptor_detected():
    result = profile_csv(BASIC_CSV, "test.csv")
    col = _col(result, "sex")
    assert col["inferred_type"] == "biological_descriptor"


def test_time_variable_detected():
    data = make_csv(
        ["animal_id", "timepoint", "body_weight_g"],
        ["A001", "day0", "25.3"],
        ["A001", "day7", "27.1"],
        ["A002", "day0", "22.0"],
    )
    result = profile_csv(data, "test.csv")
    col = _col(result, "timepoint")
    assert col["inferred_type"] == "time_variable"


# ── Unit guessing ──────────────────────────────────────────────────────────────

def test_unit_guess_grams():
    result = profile_csv(BASIC_CSV, "test.csv")
    col = _col(result, "body_weight_g")
    assert col["unit_guess"] == "g"


def test_unit_guess_none():
    data = make_csv(
        ["animal_id", "treatment"],
        ["A001", "vehicle"],
        ["A002", "drug_A"],
        ["A003", "vehicle"],
    )
    result = profile_csv(data, "test.csv")
    col = _col(result, "treatment")
    assert col["unit_guess"] is None


# ── Missing values ─────────────────────────────────────────────────────────────

def test_missing_values_counted():
    data = make_csv(
        ["animal_id", "body_weight_g"],
        ["A001", "25.3"],
        ["A002", ""],
        ["A003", "27.8"],
        ["A004", ""],
        ["A005", "26.5"],
    )
    result = profile_csv(data, "test.csv")
    col = _col(result, "body_weight_g")
    assert col["missing_values"] == 2
    assert col["missing_pct"] > 0


# ── Delimiter detection ────────────────────────────────────────────────────────

def test_semicolon_delimiter():
    content = "animal_id;sex;body_weight_g\nA001;male;25.3\nA002;female;22.1\nA003;male;27.8\n"
    data = content.encode("utf-8")
    result = profile_csv(data, "test.csv")
    assert result["import_info"]["delimiter"] == ";"
    assert result["import_info"]["n_columns"] == 3
    assert result["import_info"]["n_rows"] == 3


# ── Data type inference ────────────────────────────────────────────────────────

def test_integer_data_type():
    data = make_csv(
        ["animal_id", "litter_size"],
        ["A001", "8"],
        ["A002", "6"],
        ["A003", "9"],
        ["A004", "7"],
        ["A005", "8"],
    )
    result = profile_csv(data, "test.csv")
    col = _col(result, "litter_size")
    assert col["data_type"] == "integer"


def test_categorical_data_type():
    # 3 distinct values across 18 rows → unique_ratio = 3/18 ≈ 0.167 < 0.20 → categorical
    rows = [["animal_id", "group"]]
    groups = ["control", "low_dose", "high_dose"]
    for i in range(18):
        rows.append([f"A{i:03d}", groups[i % 3]])
    data = make_csv(*rows)
    result = profile_csv(data, "test.csv")
    col = _col(result, "group")
    assert col["data_type"] == "categorical"


# ── Error handling ─────────────────────────────────────────────────────────────

def test_empty_file_raises():
    with pytest.raises((ValueError, Exception)):
        profile_csv(b"", "empty.csv")


# ── Stage 1: value-shape validators ────────────────────────────────────────────

def test_values_look_like_identifiers_positive():
    s = pd.Series(["SD-001", "SD-002", "SD-003", "SD-004"])
    assert values_look_like_identifiers(s) is True


def test_values_look_like_identifiers_negative():
    s = pd.Series(["male", "female", "male"])
    assert values_look_like_identifiers(s) is False


def test_values_look_like_dates_positive():
    s = pd.Series(["2024-03-11", "2024-03-12", "2024-03-13"])
    assert values_look_like_dates(s) is True


def test_values_look_like_dates_negative():
    s = pd.Series(["A", "B", "C"])
    assert values_look_like_dates(s) is False


def test_values_are_numeric_positive():
    s = pd.Series(["25.3", "22.1", "27.8"])
    assert values_are_numeric(s) is True


def test_values_are_numeric_negative_paths():
    # File-path values should NOT be considered numeric, so a measurement-named
    # column with these values gets flagged as a conflict.
    s = pd.Series(["mock_raw_counts/WT_M_7mo_001.mtx", "file.mtx"])
    assert values_are_numeric(s) is False


def test_categorical_cardinality():
    s = pd.Series(["a", "a", "b", "b", "c"])
    n_unique, ratio = categorical_cardinality(s)
    assert n_unique == 3
    assert 0.5 < ratio <= 0.7


# ── Stage 1: reason codes ──────────────────────────────────────────────────────

def test_reason_codes_present():
    result = profile_csv(BASIC_CSV, "test.csv")
    for col in result["columns"]:
        assert isinstance(col.get("reason_codes"), list)
        assert len(col["reason_codes"]) >= 1


def test_reason_codes_identifier():
    result = profile_csv(BASIC_CSV, "test.csv")
    col = _col(result, "animal_id")
    assert any("identifier" in r for r in col["reason_codes"])


def test_reason_codes_numeric_value_signal():
    result = profile_csv(BASIC_CSV, "test.csv")
    col = _col(result, "body_weight_g")
    assert any("numeric" in r or "measurement" in r for r in col["reason_codes"])


def test_unit_value_consistency_conflict_flagged():
    # Column name suggests grams but values are non-numeric → conflict reason.
    data = make_csv(
        ["body_weight_g"],
        ["unknown"],
        ["pending"],
        ["to_be_filled"],
        ["to_be_filled"],
    )
    result = profile_csv(data, "test.csv")
    col = _col(result, "body_weight_g")
    assert any("conflict" in r for r in col["reason_codes"])


# ── Stage 1: dataset signature ────────────────────────────────────────────────

def test_dataset_signature_stable_under_reorder():
    a = dataset_signature(["animal_id", "sex", "body_weight_g"])
    b = dataset_signature(["body_weight_g", "ANIMAL_ID", "sex"])
    assert a == b


def test_dataset_signature_changes_with_columns():
    a = dataset_signature(["animal_id", "sex"])
    b = dataset_signature(["animal_id", "sex", "weight"])
    assert a != b


def test_profile_includes_signature():
    result = profile_csv(BASIC_CSV, "test.csv")
    assert "signature" in result["import_info"]
    assert isinstance(result["import_info"]["signature"], str)
    assert len(result["import_info"]["signature"]) == 32


# ── Stage 1: end-to-end on real test_data CSVs ────────────────────────────────

@pytest.mark.parametrize("filename", [
    "FAIR-VCG_example_data.csv",
    "preclinical_study.csv",
])
def test_preclinical_csv_inference(filename):
    path = TEST_DATA_DIR / filename
    result = profile_csv(path.read_bytes(), filename)
    by_name = {c["name"]: c for c in result["columns"]}

    assert by_name["animal_id"]["inferred_type"] == "identifier"
    assert by_name["sex"]["inferred_type"] == "biological_descriptor"
    assert by_name["strain"]["inferred_type"] == "biological_descriptor"
    assert by_name["group"]["inferred_type"] == "experimental_condition"
    assert by_name["dose_mg_kg"]["inferred_type"] == "experimental_condition"
    assert by_name["body_weight_start_g"]["inferred_type"] == "measurement"
    assert by_name["body_weight_end_g"]["inferred_type"] == "measurement"
    assert by_name["liver_weight_g"]["inferred_type"] == "measurement"
    assert by_name["operator"]["inferred_type"] == "metadata_field"
    assert by_name["collection_date"]["inferred_type"] == "time_variable"

    # Clinical-chemistry markers (case varies between the two files).
    assay_keys = {"alt_u_l", "ast_u_l", "creatinine_umol_l",
                  "ALT_U_L", "AST_U_L", "creatinine_umol_L"}
    seen_assay = [k for k in by_name if k in assay_keys]
    assert seen_assay, "expected clinical-chemistry columns to be present"
    for k in seen_assay:
        assert by_name[k]["inferred_type"] == "measurement"


def test_future_control_records_template_inference():
    path = TEST_DATA_DIR / "future_control_records_template.csv"
    result = profile_csv(path.read_bytes(), "future_control_records_template.csv")
    by_name = {c["name"]: c for c in result["columns"]}

    assert by_name["study.study_id"]["inferred_type"] == "identifier"
    assert by_name["design.experiment_id"]["inferred_type"] == "identifier"
    assert by_name["design.cohort_id"]["inferred_type"] == "identifier"
    assert by_name["animal.animal_uid"]["inferred_type"] == "identifier"
    assert by_name["procedure.date"]["inferred_type"] == "time_variable"
    assert by_name["outcome.value"]["inferred_type"] == "measurement"
    assert by_name["vcg.control_record_id"]["inferred_type"] == "identifier"
    assert by_name["provenance.created_at"]["inferred_type"] == "time_variable"


def test_metadata_template_inference():
    path = TEST_DATA_DIR / "THY_Tau22_VCG_experimental_metadata_fields.csv"
    result = profile_csv(path.read_bytes(),
                          "THY_Tau22_VCG_experimental_metadata_fields.csv")
    by_name = {c["name"]: c for c in result["columns"]}

    assert by_name["field_id"]["inferred_type"] == "identifier"
    assert by_name["field_label"]["inferred_type"] == "metadata_field"
    assert by_name["definition"]["inferred_type"] == "free_text_note"
    assert by_name["data_type"]["inferred_type"] == "metadata_field"
    assert by_name["unit"]["inferred_type"] == "metadata_field"
    assert by_name["required_for_vcg"]["inferred_type"] == "metadata_field"
    assert by_name["notes"]["inferred_type"] == "free_text_note"


def test_high_confidence_majority_on_test_data():
    """Smoke check: of columns we *did* assign a type to, most should be
    above the ambiguity threshold.  Columns that fell through to
    ``unknown`` are excluded — that label is itself an honest low-
    confidence signal and triggers a wizard prompt downstream."""
    csv_files = list(TEST_DATA_DIR.glob("*.csv"))
    assert csv_files, "no fixture CSVs found"

    decided = 0
    confident = 0
    for path in csv_files:
        result = profile_csv(path.read_bytes(), path.name)
        for col in result["columns"]:
            if col.get("inferred_type") == "unknown":
                continue
            decided += 1
            if float(col.get("confidence", 0.0) or 0.0) >= 0.65:
                confident += 1

    assert decided > 0
    assert confident / decided >= 0.80
