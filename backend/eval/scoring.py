"""Scoring primitives: per-column results + aggregate metrics.

The scored target is the column **semantic type**. Three metrics matter for the
grant's ~90 % goal:

- **accuracy** — fraction of evaluated columns whose predicted type matches
  ground truth.
- **hallucination rate** — fraction of predictions whose type is not one of the
  allowed semantic types (always 0 for the deterministic baseline; the key
  safety signal for LLMs).
- **calibration** — accuracy bucketed by predicted confidence, to check whether
  a model "knows when it knows".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

from .datasets import ALLOWED_SEMANTIC_TYPES
from .predictors import Prediction

# Sentinel used when a predictor returns nothing for a ground-truth column.
MISSING = "__missing__"

_BUCKET_EDGES = (
    ("0.0-0.5", 0.0, 0.5),
    ("0.5-0.65", 0.5, 0.65),
    ("0.65-0.8", 0.65, 0.8),
    ("0.8-0.9", 0.8, 0.9),
    ("0.9-1.0", 0.9, 1.0001),
)


@dataclass(frozen=True)
class ColumnResult:
    dataset: str
    level: str
    column: str
    expected: str
    predicted: str
    confidence: float
    correct: bool
    hallucinated: bool


def bucket_for(confidence: float) -> str:
    for label, lo, hi in _BUCKET_EDGES:
        if lo <= confidence < hi:
            return label
    return _BUCKET_EDGES[-1][0]


def bucket_labels() -> List[str]:
    return [label for label, _, _ in _BUCKET_EDGES]


def score_predictions(
    dataset: str,
    level: str,
    ground_truth: Mapping[str, str],
    predictions: Mapping[str, Prediction],
) -> List[ColumnResult]:
    """Compare predictions to ground truth for one (dataset, level) run."""
    results: List[ColumnResult] = []
    for column, expected in ground_truth.items():
        pred = predictions.get(column)
        if pred is None:
            results.append(
                ColumnResult(dataset, level, column, expected, MISSING, 0.0, False, False)
            )
            continue
        predicted = pred.semantic_type
        results.append(
            ColumnResult(
                dataset=dataset,
                level=level,
                column=column,
                expected=expected,
                predicted=predicted,
                confidence=float(pred.confidence or 0.0),
                correct=(predicted == expected),
                hallucinated=(predicted not in ALLOWED_SEMANTIC_TYPES),
            )
        )
    return results


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def accuracy(results: List[ColumnResult]) -> float:
    return _safe_div(sum(1 for r in results if r.correct), len(results))


def hallucination_rate(results: List[ColumnResult]) -> float:
    # MISSING is an absence, not an invented type — exclude it from the denominator.
    scored = [r for r in results if r.predicted != MISSING]
    return _safe_div(sum(1 for r in scored if r.hallucinated), len(scored))


def calibration(results: List[ColumnResult]) -> Dict[str, Dict[str, float]]:
    """Per-confidence-bucket count + accuracy."""
    out: Dict[str, Dict[str, float]] = {
        label: {"count": 0, "correct": 0, "accuracy": 0.0} for label in bucket_labels()
    }
    for r in results:
        b = out[bucket_for(r.confidence)]
        b["count"] += 1
        if r.correct:
            b["correct"] += 1
    for b in out.values():
        b["accuracy"] = _safe_div(b["correct"], b["count"])
    return out
