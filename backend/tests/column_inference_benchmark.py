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
class ColumnPrediction:
    filename: str
    column: str
    expected: str
    predicted: str
    confidence: float
    correct: bool


@dataclass(frozen=True)
class DatasetBenchmark:
    filename: str
    evaluated_columns: int
    correct: int
    accuracy: float
    ambiguity_rate: float
    predictions: Tuple[ColumnPrediction, ...] = ()


@dataclass(frozen=True)
class BenchmarkSummary:
    evaluated_columns: int
    correct: int
    micro_precision: float
    micro_recall: float
    ambiguity_rate: float
    per_dataset: Tuple[DatasetBenchmark, ...]
    confidence_buckets: Mapping[str, int] = None  # type: ignore[assignment]
    mistakes: Tuple[ColumnPrediction, ...] = ()


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _profile_dataset(data_dir: Path, filename: str) -> Mapping[str, Dict[str, object]]:
    path = data_dir / filename
    result = profile_csv(path.read_bytes(), filename)
    return {c["name"]: c for c in result["columns"]}


_BUCKET_EDGES = (
    ("0.0-0.5", 0.0, 0.5),
    ("0.5-0.65", 0.5, 0.65),
    ("0.65-0.8", 0.65, 0.8),
    ("0.8-0.9", 0.8, 0.9),
    ("0.9-1.0", 0.9, 1.0001),
)


def _bucket_for(confidence: float) -> str:
    for label, lo, hi in _BUCKET_EDGES:
        if lo <= confidence < hi:
            return label
    return _BUCKET_EDGES[-1][0]


def run_benchmark(
    data_dir: Path,
    expected_roles: Mapping[str, Mapping[str, str]] = EXPECTED_KEY_ROLES,
    ambiguity_threshold: float = 0.65,
) -> BenchmarkSummary:
    total_evaluated = 0
    total_correct = 0
    total_ambiguous = 0
    per_dataset: List[DatasetBenchmark] = []
    buckets: Dict[str, int] = {label: 0 for label, _, _ in _BUCKET_EDGES}
    mistakes: List[ColumnPrediction] = []

    for filename, expectations in expected_roles.items():
        profiled = _profile_dataset(data_dir, filename)
        evaluated = 0
        correct = 0
        ambiguous = 0
        dataset_predictions: List[ColumnPrediction] = []

        for col_name, expected_role in expectations.items():
            column = profiled.get(col_name)
            if column is None:
                continue

            evaluated += 1
            predicted_role = str(column.get("inferred_type", "unknown"))
            confidence = float(column.get("confidence", 0.0) or 0.0)
            is_correct = predicted_role == expected_role

            if is_correct:
                correct += 1
            else:
                mistakes.append(
                    ColumnPrediction(
                        filename=filename,
                        column=col_name,
                        expected=expected_role,
                        predicted=predicted_role,
                        confidence=confidence,
                        correct=False,
                    )
                )
            if confidence < ambiguity_threshold:
                ambiguous += 1

            buckets[_bucket_for(confidence)] += 1
            dataset_predictions.append(
                ColumnPrediction(
                    filename=filename,
                    column=col_name,
                    expected=expected_role,
                    predicted=predicted_role,
                    confidence=confidence,
                    correct=is_correct,
                )
            )

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
                predictions=tuple(dataset_predictions),
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
        confidence_buckets=buckets,
        mistakes=tuple(mistakes),
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

    if summary.confidence_buckets:
        lines.append("")
        lines.append("Confidence distribution:")
        for label, _, _ in _BUCKET_EDGES:
            count = summary.confidence_buckets.get(label, 0)
            pct = _safe_div(count, summary.evaluated_columns) * 100
            lines.append(f"  {label:>9s}: {count:3d} ({pct:5.1f}%)")

    if summary.mistakes:
        lines.append("")
        lines.append("Misclassifications:")
        for m in summary.mistakes:
            lines.append(
                f"  {m.filename}::{m.column} expected={m.expected} got={m.predicted} confidence={m.confidence:.2f}"
            )

    return "\n".join(lines)
