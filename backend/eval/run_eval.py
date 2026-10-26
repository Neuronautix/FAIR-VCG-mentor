"""Run the masked-metadata harness and emit a provider scorecard.

Programmatic entry point: ``evaluate(predictor, ...)`` returns a ``ScoreCard``.
CLI:

    python -m eval.run_eval --predictor deterministic
    python -m eval.run_eval --predictor llm --out scorecard.md

The deterministic predictor runs fully offline. The ``llm`` predictor uses
whichever provider ``llm_service`` is configured for (Anthropic or a local
OpenAI-compatible endpoint); it requires that provider to be reachable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Iterable, List, Optional

# Allow `python backend/eval/run_eval.py` as well as `python -m eval.run_eval`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.datasets import EvalDataset, available_datasets  # noqa: E402
from eval.masking import MASKING_LEVELS, mask_dataset  # noqa: E402
from eval.predictors import (  # noqa: E402
    DeterministicPredictor,
    KGGroundedLLMPredictor,
    KGPredictor,
    LLMPredictor,
)
from eval.scorecard import ScoreCard  # noqa: E402
from eval.scoring import score_predictions  # noqa: E402


def evaluate(
    predictor,
    datasets: Optional[Iterable[EvalDataset]] = None,
    levels: Iterable[str] = MASKING_LEVELS,
) -> ScoreCard:
    """Run ``predictor`` over the datasets at each masking level → ScoreCard."""
    from csv_profiler import profile_csv

    datasets = list(datasets) if datasets is not None else available_datasets()
    results = []
    for ds in datasets:
        if not ds.exists():
            continue
        raw_bytes = ds.read_bytes()
        for level in levels:
            masked_bytes, name_map = mask_dataset(raw_bytes, level)
            profile = profile_csv(masked_bytes, ds.filename)
            columns = profile["columns"]
            masked_preds = predictor.predict(columns)
            # Translate masked headers back to original column names for scoring.
            preds = {name_map.get(k, k): v for k, v in masked_preds.items()}
            results.extend(score_predictions(ds.filename, level, ds.ground_truth, preds))

    return ScoreCard(
        predictor_name=getattr(predictor, "name", "predictor"),
        provider=getattr(predictor, "provider", "unknown"),
        results=results,
    )


def _make_predictor(kind: str):
    if kind == "deterministic":
        return DeterministicPredictor()
    if kind == "kg":
        return KGPredictor()
    if kind == "llm":
        return LLMPredictor()
    if kind == "kg-llm":
        return KGGroundedLLMPredictor()
    raise SystemExit(
        f"unknown predictor: {kind!r} (expected 'deterministic', 'kg', 'llm', or 'kg-llm')"
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Masked-metadata validation harness.")
    parser.add_argument(
        "--predictor",
        default="deterministic",
        choices=["deterministic", "kg", "llm", "kg-llm"],
    )
    parser.add_argument(
        "--levels",
        default=",".join(MASKING_LEVELS),
        help="comma-separated masking levels (raw,blind)",
    )
    parser.add_argument("--format", default="markdown", choices=["markdown", "json"])
    parser.add_argument("--out", default=None, help="write the scorecard to this path")
    args = parser.parse_args(argv)

    levels = [lv.strip() for lv in args.levels.split(",") if lv.strip()]
    predictor = _make_predictor(args.predictor)
    card = evaluate(predictor, levels=levels)

    rendered = json.dumps(card.to_dict(), indent=2) if args.format == "json" else card.to_markdown()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"Wrote scorecard to {args.out}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
