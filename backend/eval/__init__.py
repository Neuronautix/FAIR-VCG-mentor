"""Masked-metadata validation harness for FAIR-VCG Mentor (grant Milestone C).

This package quantifies how well a metadata predictor — the deterministic
rule-based profiler, a cloud LLM, or a local LLM — recovers column semantic
types from datasets whose metadata has been *masked*. It produces a provider
scorecard (accuracy, hallucination rate, confidence calibration) so we can
compare Anthropic vs local models (Gemma / APERTUS) toward the ~90 % target.

Design: predictors are pluggable (`predictors.py`); the deterministic baseline
and the scoring/masking logic run fully offline (CI-safe). LLM predictors run
on demand against whichever provider `llm_service` is configured for.
"""

from .datasets import ALLOWED_SEMANTIC_TYPES, EVAL_DATASETS, EvalDataset
from .predictors import (
    CallablePredictor,
    DeterministicPredictor,
    KGGroundedLLMPredictor,
    KGPredictor,
    LLMPredictor,
    Prediction,
)
from .scorecard import ScoreCard

# Note: `evaluate` lives in `eval.run_eval` and is intentionally not re-exported
# here — importing it in this package __init__ triggers a runpy warning when the
# module is run via `python -m eval.run_eval`. Import it from `eval.run_eval`.

__all__ = [
    "ALLOWED_SEMANTIC_TYPES",
    "EVAL_DATASETS",
    "EvalDataset",
    "Prediction",
    "DeterministicPredictor",
    "LLMPredictor",
    "KGPredictor",
    "KGGroundedLLMPredictor",
    "CallablePredictor",
    "ScoreCard",
]
