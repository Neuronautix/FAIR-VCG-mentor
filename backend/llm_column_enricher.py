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


SYSTEM_PROMPT = (
    "You are a research-data curation assistant specialising in life-sciences "
    "tabular datasets. You suggest concise, accurate metadata for columns "
    "based on the column name, sample values, and surrounding context. "
    "If you cannot make a confident inference for a field, return null — "
    "do NOT invent units, ranges, or controlled vocabularies."
)


SEMANTIC_TYPES = [
    "identifier", "biological_descriptor", "experimental_condition",
    "measurement", "time_variable", "free_text_note",
    "metadata_field", "categorical", "unknown",
]


_TOOL = {
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
                            "type": "string",
                            "description": "Exact column name from the input list.",
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
                            "type": "string",
                            "enum": SEMANTIC_TYPES,
                            "description": "Best-fit semantic type.",
                        },
                        "unit": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": (
                                "SI or domain-standard unit (e.g. kg, mg/kg, mm, °C, "
                                "s, %, count). null if the column is non-numeric or "
                                "you are not confident."
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
) -> List[Dict[str, Any]]:
    """
    Returns a list of validated suggestions:
        [{column_name, label, description, semantic_type, unit, confidence, rationale}]

    Columns not in the dataset are filtered out (anti-hallucination guard).
    """
    target = [c for c in columns if not only_columns or c["name"] in set(only_columns)]
    if not target:
        return []

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
        tool=_TOOL,
        user_message=user_msg,
        model_env="COLUMN_ENRICHER_MODEL",
        max_tokens=2048,
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
