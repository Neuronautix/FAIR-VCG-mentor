"""Tests for the masked-metadata validation harness (backend/eval).

All offline: the deterministic predictor and the masking/scoring logic need no
network. The LLM predictor is exercised only via a fake (CallablePredictor) so
the scoring, hallucination, and calibration maths are verified without a model.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval import (  # noqa: E402
    CallablePredictor,
    DeterministicPredictor,
    EvalDataset,
    Prediction,
    ScoreCard,
)
from eval.datasets import available_datasets  # noqa: E402
from eval.run_eval import evaluate  # noqa: E402
from eval.masking import mask_dataset  # noqa: E402
from eval.scoring import (  # noqa: E402
    accuracy,
    hallucination_rate,
    score_predictions,
)


# ── Masking ──────────────────────────────────────────────────────────────────

_CSV = b"animal_id,body_weight_g,group\nA1,21.3,Control\nA2,22.0,Dose\n"


def test_mask_raw_is_identity():
    masked, name_map = mask_dataset(_CSV, "raw")
    assert masked == _CSV
    assert name_map == {"animal_id": "animal_id", "body_weight_g": "body_weight_g", "group": "group"}


def test_mask_blind_anonymizes_headers_keeps_values():
    masked, name_map = mask_dataset(_CSV, "blind")
    text = masked.decode()
    header = text.splitlines()[0]
    assert header == "var_1,var_2,var_3"
    # name_map translates emitted -> original, in order
    assert name_map == {"var_1": "animal_id", "var_2": "body_weight_g", "var_3": "group"}
    # values are untouched
    assert "A1,21.3,Control" in text
    assert "A2,22.0,Dose" in text


def test_mask_unknown_level_raises():
    with pytest.raises(ValueError):
        mask_dataset(_CSV, "scrambled")


# ── Scoring maths (fake predictions) ─────────────────────────────────────────

def test_score_predictions_accuracy_and_hallucination():
    gt = {"a": "identifier", "b": "measurement", "c": "measurement"}
    preds = {
        "a": Prediction("identifier", 0.9),       # correct
        "b": Prediction("measurement", 0.8),       # correct
        "c": Prediction("not_a_real_type", 0.5),   # wrong + hallucinated
    }
    results = score_predictions("ds", "raw", gt, preds)
    assert accuracy(results) == pytest.approx(2 / 3)
    assert hallucination_rate(results) == pytest.approx(1 / 3)


def test_missing_prediction_counts_as_wrong_but_not_hallucination():
    gt = {"a": "identifier", "b": "measurement"}
    preds = {"a": Prediction("identifier", 0.9)}  # 'b' missing entirely
    results = score_predictions("ds", "raw", gt, preds)
    assert accuracy(results) == pytest.approx(0.5)
    # MISSING is an absence, not an invented type → excluded from hallucination denom
    assert hallucination_rate(results) == 0.0


# ── ScoreCard aggregation + rendering ────────────────────────────────────────

def _fake_perfect(columns):
    # Echo each column as a correct 'identifier' — only meaningful with matching GT.
    return {c["name"]: Prediction("identifier", 0.95) for c in columns}


def test_scorecard_from_fake_predictor_structure():
    ds = EvalDataset(
        "FAIR-VCG_example_data.csv",
        {"animal_id": "identifier"},  # single-column GT so the echo predictor is correct
    )
    predictor = CallablePredictor(_fake_perfect, name="echo", provider="fake")
    card = evaluate(predictor, datasets=[ds], levels=["raw"])
    assert isinstance(card, ScoreCard)
    assert card.predictor_name == "echo"
    assert card.overall_accuracy() == 1.0
    assert card.overall_hallucination_rate() == 0.0
    d = card.to_dict()
    assert d["evaluated_columns"] == 1
    assert "by_level" in d and "raw" in d["by_level"]
    md = card.to_markdown()
    assert "Masked-metadata scorecard" in md
    assert "By masking level" in md


# ── Deterministic baseline on real fixtures (CI guardrail) ───────────────────

@pytest.mark.skipif(not available_datasets(), reason="no eval datasets on disk")
def test_deterministic_baseline_accuracy_and_zero_hallucination():
    card = evaluate(DeterministicPredictor(), levels=["raw", "blind"])
    assert card.evaluated_columns() >= 25
    # The rule-based profiler only ever emits allowed semantic types.
    assert card.overall_hallucination_rate() == 0.0
    by_level = card.by_level()
    # With real column names the deterministic profiler should be reasonably strong.
    assert by_level["raw"]["accuracy"] >= 0.6
    # Blind (anonymized headers) is expected to be no better than raw — this is
    # the signal that quantifies name-pattern reliance.
    assert by_level["blind"]["accuracy"] <= by_level["raw"]["accuracy"] + 1e-9


def test_deterministic_predictor_reads_profile_fields():
    cols = [
        {"name": "x", "inferred_type": "measurement", "confidence": 0.8, "unit_guess": "g"},
        {"name": "y", "inferred_type": "identifier", "confidence": 0.9, "unit_guess": None},
    ]
    preds = DeterministicPredictor().predict(cols)
    assert preds["x"].semantic_type == "measurement"
    assert preds["x"].unit == "g"
    assert preds["y"].confidence == 0.9
