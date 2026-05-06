from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple

from csv_profiler import profile_csv


# Curated expectations for key columns across repository sample datasets.
EXPECTED_KEY_ROLES: Dict[str, Dict[str, str]] = {
    "FAIR-VCG_example_data.csv": {
        "animal_id": "identifier",
        "group": "experimental_condition",
        "dose_mg_kg": "experimental_condition",
        "body_weight_start_g": "measurement",
        "body_weight_end_g": "measurement",
        "liver_weight_g": "measurement",
        "kidney_weight_g": "measurement",
        "operator": "metadata_field",
        "collection_date": "time_variable",
    },
    "preclinical_study.csv": {
        "animal_id": "identifier",
        "group": "experimental_condition",
        "dose_mg_kg": "experimental_condition",
        "body_weight_start_g": "measurement",
        "body_weight_end_g": "measurement",
        "liver_weight_g": "measurement",
        "kidney_weight_g": "measurement",
        "operator": "metadata_field",
        "collection_date": "time_variable",
    },
    "future_control_records_template.csv": {
        "study.study_id": "identifier",
        "design.experiment_id": "identifier",
        "design.cohort_id": "identifier",
        "animal.animal_uid": "identifier",
        "procedure.date": "time_variable",
        "outcome.value": "measurement",
        "vcg.control_record_id": "identifier",
        "provenance.created_at": "time_variable",
    },
    "THY_Tau22_VCG_experimental_metadata_fields.csv": {
        "field_id": "identifier",
        "field_label": "metadata_field",
        "definition": "free_text_note",
        "data_type": "metadata_field",
        "unit": "metadata_field",
        "required_for_vcg": "metadata_field",
        "notes": "free_text_note",
    },
}


@dataclass(frozen=True)
class DatasetBenchmark:
    filename: str
    evaluated_columns: int
    correct: int
    accuracy: float
    ambiguity_rate: float


@dataclass(frozen=True)
class BenchmarkSummary:
    evaluated_columns: int
    correct: int
    micro_precision: float
    micro_recall: float
    ambiguity_rate: float
    per_dataset: Tuple[DatasetBenchmark, ...]


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _profile_dataset(data_dir: Path, filename: str) -> Mapping[str, Dict[str, object]]:
    path = data_dir / filename
    result = profile_csv(path.read_bytes(), filename)
    return {c["name"]: c for c in result["columns"]}


def run_benchmark(
    data_dir: Path,
    expected_roles: Mapping[str, Mapping[str, str]] = EXPECTED_KEY_ROLES,
    ambiguity_threshold: float = 0.65,
) -> BenchmarkSummary:
    total_evaluated = 0
    total_correct = 0
    total_ambiguous = 0
    per_dataset: List[DatasetBenchmark] = []

    for filename, expectations in expected_roles.items():
        profiled = _profile_dataset(data_dir, filename)
        evaluated = 0
        correct = 0
        ambiguous = 0

        for col_name, expected_role in expectations.items():
            column = profiled.get(col_name)
            if column is None:
                continue

            evaluated += 1
            predicted_role = str(column.get("inferred_type", "unknown"))
            confidence = float(column.get("confidence", 0.0) or 0.0)

            if predicted_role == expected_role:
                correct += 1
            if confidence < ambiguity_threshold:
                ambiguous += 1

        total_evaluated += evaluated
        total_correct += correct
        total_ambiguous += ambiguous

        per_dataset.append(
            DatasetBenchmark(
                filename=filename,
                evaluated_columns=evaluated,
                correct=correct,
                accuracy=_safe_div(correct, evaluated),
                ambiguity_rate=_safe_div(ambiguous, evaluated),
            )
        )

    micro = _safe_div(total_correct, total_evaluated)
    return BenchmarkSummary(
        evaluated_columns=total_evaluated,
        correct=total_correct,
        micro_precision=micro,
        micro_recall=micro,
        ambiguity_rate=_safe_div(total_ambiguous, total_evaluated),
        per_dataset=tuple(per_dataset),
    )


def format_summary(summary: BenchmarkSummary) -> str:
    lines = [
        "Column inference benchmark",
        "--------------------------",
        f"Evaluated columns: {summary.evaluated_columns}",
        f"Correct predictions: {summary.correct}",
        f"Micro precision: {summary.micro_precision:.3f}",
        f"Micro recall: {summary.micro_recall:.3f}",
        f"Ambiguity rate: {summary.ambiguity_rate:.3f}",
        "",
        "Per dataset:",
    ]
    for ds in summary.per_dataset:
        lines.append(
            f"- {ds.filename}: accuracy={ds.accuracy:.3f}, ambiguity={ds.ambiguity_rate:.3f}, evaluated={ds.evaluated_columns}"
        )
    return "\n".join(lines)
