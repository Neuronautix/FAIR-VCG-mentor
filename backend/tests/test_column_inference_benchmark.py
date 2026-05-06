from pathlib import Path

from tests.column_inference_benchmark import run_benchmark


def test_column_inference_benchmark_stage0_baseline():
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "test_data"

    summary = run_benchmark(data_dir)

    # Stage 0 baseline floor: conservative guardrail to ensure benchmark stays healthy.
    assert summary.evaluated_columns >= 25
    assert summary.micro_precision >= 0.60
    assert summary.micro_recall >= 0.60


def test_column_inference_benchmark_dataset_coverage():
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "test_data"

    summary = run_benchmark(data_dir)
    names = {d.filename for d in summary.per_dataset}

    assert "FAIR-VCG_example_data.csv" in names
    assert "preclinical_study.csv" in names
    assert "future_control_records_template.csv" in names
    assert "THY_Tau22_VCG_experimental_metadata_fields.csv" in names
