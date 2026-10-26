"""Tests for the KG-grounded predictor and its blind-mode accuracy lift.

All offline / CI-safe: the KGPredictor is a deterministic hybrid (rule-based
profiler + knowledge-graph value override) and needs no network or LLM. The
fixture ``synthetic_biological_descriptors.csv`` is rich in controlled
biological values (species / strain / sex / compound / tissue) so that, once the
headers are anonymised under ``blind`` masking, the KG's value-based recovery
beats the name-pattern profiler — the lift this milestone has to demonstrate.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval import DeterministicPredictor, EvalDataset, KGPredictor  # noqa: E402
from eval.run_eval import evaluate  # noqa: E402


# Build the dataset inline (also registered in eval.datasets.EVAL_DATASETS).
SYNTH = EvalDataset(
    "synthetic_biological_descriptors.csv",
    {
        "subject_id": "identifier",
        "species": "biological_descriptor",
        "strain": "biological_descriptor",
        "sex": "biological_descriptor",
        "compound": "experimental_condition",
        "tissue": "biological_descriptor",
        "body_weight_g": "measurement",
        "timepoint": "time_variable",
    },
)

LEVELS = ["raw", "blind"]


@pytest.mark.skipif(not SYNTH.exists(), reason="synthetic fixture missing")
def test_kg_predictor_lifts_blind_accuracy():
    det = evaluate(DeterministicPredictor(), datasets=[SYNTH], levels=LEVELS)
    kg = evaluate(KGPredictor(), datasets=[SYNTH], levels=LEVELS)

    det_levels = det.by_level()
    kg_levels = kg.by_level()

    # (a) Blind-mode: the KG recovers species/strain/sex/compound/tissue from
    # the values once headers are blinded → strictly better than the profiler.
    assert kg_levels["blind"]["accuracy"] > det_levels["blind"]["accuracy"], (
        f"expected KG blind lift; det={det_levels['blind']['accuracy']:.3f} "
        f"kg={kg_levels['blind']['accuracy']:.3f}"
    )

    # (b) The KG only ever emits curated, allowed semantic types → no hallucination.
    assert kg.overall_hallucination_rate() == 0.0

    # (c) Raw-mode: the KG never regresses below the profiler when names are present.
    assert kg_levels["raw"]["accuracy"] >= det_levels["raw"]["accuracy"]


@pytest.mark.skipif(not SYNTH.exists(), reason="synthetic fixture missing")
def test_kg_predictor_metadata():
    kg = KGPredictor()
    assert kg.name == "kg"
    assert kg.provider == "kg+rule-based"


def test_kg_predictor_degrades_to_base_on_empty_columns():
    # No columns → no matches; should not raise and returns empty mapping.
    assert KGPredictor().predict([]) == {}
