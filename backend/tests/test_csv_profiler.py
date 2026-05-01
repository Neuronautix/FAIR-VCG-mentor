import io
import csv
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from csv_profiler import profile_csv


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
