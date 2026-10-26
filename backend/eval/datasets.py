"""Eval dataset registry + ground-truth semantic-type annotations.

Ground truth is the curated semantic role for key columns of the repository's
sample datasets (`test_data/*.csv`). These are the same expectations used by
the deterministic column-inference benchmark, promoted here to a canonical,
importable location so both the benchmark and the masked-metadata harness
score against one source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# repo_root/test_data — eval lives at backend/eval, so go up two levels.
TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"

# The nine canonical FAIR-VCG semantic types (mirrors vocabulary.DEFAULT_VOCABULARY
# and CLAUDE.md). A predicted type outside this set is counted as a hallucination.
ALLOWED_SEMANTIC_TYPES = frozenset(
    {
        "identifier",
        "biological_descriptor",
        "experimental_condition",
        "measurement",
        "time_variable",
        "free_text_note",
        "metadata_field",
        "categorical",
        "unknown",
    }
)


@dataclass(frozen=True)
class EvalDataset:
    """A sample dataset + its ground-truth semantic types for key columns."""

    filename: str
    ground_truth: Dict[str, str] = field(default_factory=dict)

    def path(self) -> Path:
        return TEST_DATA_DIR / self.filename

    def exists(self) -> bool:
        return self.path().exists()

    def read_bytes(self) -> bytes:
        return self.path().read_bytes()


EVAL_DATASETS: List[EvalDataset] = [
    EvalDataset(
        "FAIR-VCG_example_data.csv",
        {
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
    ),
    EvalDataset(
        "preclinical_study.csv",
        {
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
    ),
    EvalDataset(
        "future_control_records_template.csv",
        {
            "study.study_id": "identifier",
            "design.experiment_id": "identifier",
            "design.cohort_id": "identifier",
            "animal.animal_uid": "identifier",
            "procedure.date": "time_variable",
            "outcome.value": "measurement",
            "vcg.control_record_id": "identifier",
            "provenance.created_at": "time_variable",
        },
    ),
    EvalDataset(
        # Biological-descriptor-rich dataset. Under blind masking (headers → var_N)
        # the rule-based profiler loses the column-name signal, but the KG recovers
        # species/strain/sex/compound/tissue from the controlled *values*. This is
        # the fixture that demonstrates the KG blind-mode accuracy lift.
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
    ),
    EvalDataset(
        "THY_Tau22_VCG_experimental_metadata_fields.csv",
        {
            "field_id": "identifier",
            "field_label": "metadata_field",
            "definition": "free_text_note",
            "data_type": "metadata_field",
            "unit": "metadata_field",
            "required_for_vcg": "metadata_field",
            "notes": "free_text_note",
        },
    ),
]


def available_datasets() -> List[EvalDataset]:
    """Eval datasets whose CSV is present on disk."""
    return [d for d in EVAL_DATASETS if d.exists()]
