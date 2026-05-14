"""
Use Claude Haiku to suggest richer metadata (label, description, semantic
type, unit) for columns the rule-based profiler is uncertain about.

Outputs are returned as HITL suggestions — they never directly mutate the
session. Column names returned by the model are filtered against the real
dataset to prevent hallucinated identifiers from reaching the user.
"""

from __future__ import annotations

from typing import Any, Dict, List

from llm_service import call_haiku, fmt_columns_for_prompt, validate_columns_exist
from vocabulary import (
    SEMANTIC_TYPES,
    enum_array,
    enum_or_null,
    ensure_vocabulary,
    schema_prompt_block,
)


SYSTEM_PROMPT = (
    "You are a research-data curation assistant specialising in life-sciences "
    "tabular datasets. You suggest concise, accurate metadata for columns "
    "based on the column name, sample values, and surrounding context. "
    "If you cannot make a confident inference for a field, return null — "
    "do NOT invent units, ranges, or controlled vocabularies. Stick to the "
    "VALIDATED VOCABULARY in the next system block."
)


def _build_tool(vocab: Dict[str, Any]) -> Dict[str, Any]:
    """Dynamically build a vocabulary-constrained tool schema."""
    column_enum = enum_array(vocab["column_names"])
    return {
        "name": "enrich_columns",
        "description": (
            "Suggest richer metadata (label, description, semantic type, unit) "
            "for the listed columns. Only return entries for columns you were "
            "asked about. Use exact column names as keys."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column_name": {
                                "enum": vocab["column_names"] or ["__unused__"],
                                "description": "Exact column name from the validated vocabulary.",
                            },
                            "label": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "description": "Short human-readable label (Title Case).",
                            },
                            "description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "description": "One-sentence description of what the column represents.",
                            },
                            "semantic_type": {
                                "enum": vocab["semantic_types"],
                                "description": "Best-fit semantic type (from vocabulary).",
                            },
                            "unit": {
                                **enum_or_null(vocab["units"]),
                                "description": (
                                    "Unit drawn from the validated vocabulary, or null "
                                    "if the column is non-numeric. To request a new unit, "
                                    "set this to null and explain in rationale."
                                ),
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Self-rated 0-1 confidence in the suggestion.",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "One-sentence rationale based on column name + samples.",
                            },
                        },
                        "required": [
                            "column_name", "label", "description",
                            "semantic_type", "unit", "confidence", "rationale",
                        ],
                    },
                },
            },
            "required": ["suggestions"],
        },
    }


def suggest_column_metadata(
    columns: List[Dict[str, Any]],
    only_columns: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """
    Returns a list of validated suggestions:
        [{column_name, label, description, semantic_type, unit, confidence, rationale}]

    Output is double-gated: enum-constrained tool schema (vocabulary) +
    post-call validation against actual columns.
    """
    target = [c for c in columns if not only_columns or c["name"] in set(only_columns)]
    if not target:
        return []

    if session is None:
        session = {"columns": columns, "metadata": metadata or {}}
    vocab = ensure_vocabulary(session)

    context_lines = []
    if metadata:
        bits = []
        for key in ("title", "description", "species", "study_type"):
            v = metadata.get(key)
            if v:
                bits.append(f"{key}={v}")
        if bits:
            context_lines.append("Dataset context: " + "; ".join(bits))

    user_msg = "\n".join(
        context_lines
        + [
            "Suggest metadata for the following columns. Use only the "
            "column names exactly as listed below.",
            "",
            fmt_columns_for_prompt(target, limit=40),
        ]
    )

    raw = call_haiku(
        system_prompt=SYSTEM_PROMPT,
        tool=_build_tool(vocab),
        user_message=user_msg,
        model_env="COLUMN_ENRICHER_MODEL",
        max_tokens=2048,
        extra_system_blocks=[{"text": schema_prompt_block(session)}],
    )

    real_names = [c["name"] for c in columns]
    validated: List[Dict[str, Any]] = []
    for item in raw.get("suggestions", []) or []:
        name = item.get("column_name")
        check = validate_columns_exist([name], real_names) if name else {"valid": [], "hallucinated": []}
        if not check["valid"]:
            continue  # hallucinated column name — drop silently
        if item.get("semantic_type") not in SEMANTIC_TYPES:
            item["semantic_type"] = "unknown"
        validated.append(item)
    return validated


def suggestion_to_hitl_payload(s: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one LLM suggestion to the kwargs of hitl.add_suggestion."""
    payload = {}
    if s.get("label"):
        payload["user_label"] = s["label"]
    if s.get("description"):
        payload["user_description"] = s["description"]
    if s.get("semantic_type") and s["semantic_type"] != "unknown":
        payload["user_type"] = s["semantic_type"]
    if s.get("unit"):
        payload["user_unit"] = s["unit"]

    label_bit = s.get("label") or s["column_name"]
    title = f"Enrich {s['column_name']} → {label_bit}"
    rationale = s.get("rationale") or "AI-suggested metadata."
    return {
        "category": "column_metadata",
        "target": s["column_name"],
        "source": "llm:claude-haiku-4-5",
        "title": title,
        "rationale": rationale,
        "payload": payload,
        "confidence": float(s.get("confidence") or 0.0),
    }
