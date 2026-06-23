"""ScoreCard: aggregates ColumnResults and renders JSON / Markdown."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .scoring import (
    ColumnResult,
    accuracy,
    calibration,
    hallucination_rate,
)


def _group(results: List[ColumnResult], key) -> Dict[str, List[ColumnResult]]:
    out: Dict[str, List[ColumnResult]] = {}
    for r in results:
        out.setdefault(key(r), []).append(r)
    return out


@dataclass
class ScoreCard:
    predictor_name: str
    provider: str
    results: List[ColumnResult] = field(default_factory=list)

    # ── aggregate metrics ────────────────────────────────────────────────────

    def overall_accuracy(self) -> float:
        return accuracy(self.results)

    def overall_hallucination_rate(self) -> float:
        return hallucination_rate(self.results)

    def evaluated_columns(self) -> int:
        return len(self.results)

    def by_level(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for level, rows in _group(self.results, lambda r: r.level).items():
            out[level] = {
                "evaluated": len(rows),
                "accuracy": accuracy(rows),
                "hallucination_rate": hallucination_rate(rows),
            }
        return out

    def by_dataset(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for ds, rows in _group(self.results, lambda r: r.dataset).items():
            out[ds] = {
                "evaluated": len(rows),
                "accuracy": accuracy(rows),
                "hallucination_rate": hallucination_rate(rows),
            }
        return out

    def calibration(self) -> Dict[str, Dict[str, float]]:
        return calibration(self.results)

    def mistakes(self) -> List[ColumnResult]:
        return [r for r in self.results if not r.correct]

    # ── serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predictor": self.predictor_name,
            "provider": self.provider,
            "evaluated_columns": self.evaluated_columns(),
            "overall_accuracy": round(self.overall_accuracy(), 4),
            "hallucination_rate": round(self.overall_hallucination_rate(), 4),
            "by_level": self.by_level(),
            "by_dataset": self.by_dataset(),
            "calibration": self.calibration(),
            "mistakes": [
                {
                    "dataset": m.dataset,
                    "level": m.level,
                    "column": m.column,
                    "expected": m.expected,
                    "predicted": m.predicted,
                    "confidence": round(m.confidence, 3),
                }
                for m in self.mistakes()
            ],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Masked-metadata scorecard — `{self.predictor_name}` ({self.provider})",
            "",
            f"- Evaluated columns: **{self.evaluated_columns()}**",
            f"- Overall accuracy: **{self.overall_accuracy():.1%}**",
            f"- Hallucination rate: **{self.overall_hallucination_rate():.1%}**",
            "",
            "## By masking level",
            "",
            "| Level | Evaluated | Accuracy | Hallucination |",
            "| --- | ---: | ---: | ---: |",
        ]
        for level, m in self.by_level().items():
            lines.append(
                f"| {level} | {m['evaluated']} | {m['accuracy']:.1%} | {m['hallucination_rate']:.1%} |"
            )
        lines += ["", "## By dataset", "", "| Dataset | Evaluated | Accuracy | Hallucination |", "| --- | ---: | ---: | ---: |"]
        for ds, m in self.by_dataset().items():
            lines.append(
                f"| {ds} | {m['evaluated']} | {m['accuracy']:.1%} | {m['hallucination_rate']:.1%} |"
            )
        lines += ["", "## Confidence calibration", "", "| Bucket | Count | Accuracy |", "| --- | ---: | ---: |"]
        for bucket, m in self.calibration().items():
            lines.append(f"| {bucket} | {int(m['count'])} | {m['accuracy']:.1%} |")
        mistakes = self.mistakes()
        if mistakes:
            lines += ["", "## Misclassifications", "", "| Dataset | Level | Column | Expected | Predicted | Conf |", "| --- | --- | --- | --- | --- | ---: |"]
            for m in mistakes:
                lines.append(
                    f"| {m.dataset} | {m.level} | {m.column} | {m.expected} | {m.predicted} | {m.confidence:.2f} |"
                )
        return "\n".join(lines) + "\n"
