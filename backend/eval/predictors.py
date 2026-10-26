"""Pluggable metadata predictors for the validation harness.

A predictor maps profiled columns to a semantic-type prediction per column:

    predict(columns: list[dict]) -> dict[column_name, Prediction]

``columns`` is the ``profile_csv(...)["columns"]`` list. Predictors receive the
neutral profile (name, data_type, sample values, …); the deterministic baseline
reads the rule-based inference already computed by the profiler, while the LLM
predictor sends a neutral payload to whichever provider ``llm_service`` is
configured for (Anthropic or a local OpenAI-compatible endpoint).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .datasets import ALLOWED_SEMANTIC_TYPES


@dataclass
class Prediction:
    semantic_type: str
    confidence: float = 0.0
    unit: Optional[str] = None


# ── Deterministic (rule-based) baseline ──────────────────────────────────────


class DeterministicPredictor:
    """Reads the profiler's own rule-based inference. Fully offline, CI-safe."""

    name = "deterministic"
    provider = "rule-based"

    def predict(self, columns: List[Dict[str, Any]]) -> Dict[str, Prediction]:
        out: Dict[str, Prediction] = {}
        for c in columns:
            out[c["name"]] = Prediction(
                semantic_type=str(c.get("inferred_type") or "unknown"),
                confidence=float(c.get("confidence") or 0.0),
                unit=c.get("unit_guess"),
            )
        return out


# ── Test/double predictor ────────────────────────────────────────────────────


class CallablePredictor:
    """Wraps an arbitrary function as a predictor (used for tests/fakes)."""

    def __init__(
        self,
        fn: Callable[[List[Dict[str, Any]]], Dict[str, Prediction]],
        name: str = "fake",
        provider: str = "fake",
    ) -> None:
        self._fn = fn
        self.name = name
        self.provider = provider

    def predict(self, columns: List[Dict[str, Any]]) -> Dict[str, Prediction]:
        return self._fn(columns)


# ── LLM predictor (provider-agnostic via llm_service) ────────────────────────


_LLM_SYSTEM_PROMPT = (
    "You are a data-curation assistant for preclinical research datasets. For "
    "each column you are given its header, data type, and a few example values. "
    "Assign the single best semantic type from the allowed list. Base your "
    "decision on the values when the header is uninformative. Do not invent "
    "types outside the allowed list; use 'unknown' when genuinely unsure."
)


def _build_llm_tool() -> Dict[str, Any]:
    return {
        "name": "predict_semantic_types",
        "description": "Predict the semantic type of each dataset column.",
        "input_schema": {
            "type": "object",
            "properties": {
                "predictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column_name": {"type": "string"},
                            "semantic_type": {
                                "type": "string",
                                "enum": sorted(ALLOWED_SEMANTIC_TYPES),
                            },
                            "unit": {"type": ["string", "null"]},
                            "confidence": {"type": "number"},
                        },
                        "required": ["column_name", "semantic_type", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["predictions"],
            "additionalProperties": False,
        },
    }


class LLMPredictor:
    """Asks the configured LLM provider to predict semantic types.

    Provider-agnostic: routes through ``llm_service.call_haiku`` so the same
    predictor scores Anthropic, LM Studio, or any OpenAI-compatible local model.
    Hallucinated column names (not in the real dataset) are dropped.
    """

    def __init__(self, model_env: str = "COLUMN_ENRICHER_MODEL", max_samples: int = 6) -> None:
        from llm_service import provider_info

        info = provider_info()
        self.name = "llm"
        self.provider = info.get("provider") or "unknown"
        self.model = info.get("model")
        self._model_env = model_env
        self._max_samples = max_samples

    def _extra_system_blocks(self, columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Hook for subclasses to append extra system blocks (e.g. KG grounding).
        The base predictor adds none, so its behaviour is unchanged."""
        return []

    def predict(self, columns: List[Dict[str, Any]]) -> Dict[str, Prediction]:
        from llm_service import call_haiku

        real_names = {c["name"] for c in columns}
        payload = [
            {
                "name": c.get("name"),
                "data_type": c.get("data_type"),
                "samples": [str(v) for v in (c.get("sample_values") or [])[: self._max_samples]],
            }
            for c in columns
        ]
        call_kwargs: Dict[str, Any] = dict(
            system_prompt=_LLM_SYSTEM_PROMPT,
            tool=_build_llm_tool(),
            user_message=json.dumps({"columns": payload}),
            model_env=self._model_env,
            max_tokens=2048,
        )
        extra_blocks = self._extra_system_blocks(columns)
        if extra_blocks:
            call_kwargs["extra_system_blocks"] = extra_blocks
        raw = call_haiku(**call_kwargs)

        out: Dict[str, Prediction] = {}
        for item in raw.get("predictions") or []:
            name = item.get("column_name")
            if name not in real_names:
                continue  # drop hallucinated column references
            try:
                confidence = float(item.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            out[name] = Prediction(
                semantic_type=str(item.get("semantic_type") or "unknown"),
                confidence=max(0.0, min(1.0, confidence)),
                unit=item.get("unit"),
            )
        return out


# ── KG-grounded predictors ───────────────────────────────────────────────────


class KGPredictor:
    """Deterministic hybrid: rule-based profiler inference + knowledge-graph override.

    For each column it starts from the profiler's own inference (same fields the
    ``DeterministicPredictor`` reads). When the offline KG retriever matches the
    column to a concept — by NAME keyword or, crucially, by sample VALUE — the
    concept's curated ``semantic_type`` overrides the base prediction and the
    confidence is raised to ~0.9. Under blind masking (headers anonymised) the
    value-based match is what recovers species/strain/sex/compound/tissue that the
    name-pattern profiler can no longer see.

    Fully offline / CI-safe. A KG import or lookup failure degrades gracefully to
    the base profiler prediction.
    """

    name = "kg"
    provider = "kg+rule-based"

    _KG_CONFIDENCE = 0.9

    def predict(self, columns: List[Dict[str, Any]]) -> Dict[str, Prediction]:
        # Base prediction = profiler's own rule-based inference (never overridden
        # away on failure — the KG only ever *adds* signal).
        out: Dict[str, Prediction] = {
            c["name"]: Prediction(
                semantic_type=str(c.get("inferred_type") or "unknown"),
                confidence=float(c.get("confidence") or 0.0),
                unit=c.get("unit_guess"),
            )
            for c in columns
        }

        try:
            from knowledge.retriever import match_columns
            from knowledge.kg import load_kg

            kg = load_kg()
            for m in match_columns(columns, kg):
                concept = kg.concept(m.concept_id)
                if concept is None or m.column not in out:
                    continue
                base = out[m.column]
                out[m.column] = Prediction(
                    semantic_type=str(concept.semantic_type),
                    confidence=self._KG_CONFIDENCE,
                    unit=base.unit,
                )
        except Exception:
            # Any KG failure → keep the base profiler predictions. Offline-safe.
            return out

        return out


class KGGroundedLLMPredictor(LLMPredictor):
    """LLM predictor that injects the KG grounding block as an extra system block.

    On-demand LLM path (not CI-tested). Identical to ``LLMPredictor`` except it
    retrieves ``knowledge.retriever.grounding_block(columns)`` and, when non-empty,
    appends it as a system block so the model is grounded in the curated
    concept→semantic_type mappings for the columns it actually sees.
    """

    name = "kg-llm"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.provider = f"kg+{self.provider}"

    def _extra_system_blocks(self, columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            from knowledge.retriever import grounding_block

            block = grounding_block(columns)
        except Exception:
            block = ""
        if not block:
            return []
        return [{"type": "text", "text": block}]
