import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a scientific data management expert specialising in the FAIR data principles "
    "(Findable, Accessible, Interoperable, Reusable). You provide qualitative assessments "
    "that go beyond mechanical field-presence checks — you judge whether metadata is "
    "meaningful, specific, and useful for research data reuse."
)

_FAIR_COMMENTARY_TOOL = {
    "name": "fair_commentary",
    "description": (
        "Provide a qualitative FAIR assessment of a dataset based on its metadata, "
        "column profiles, and detected issues. Judge meaningfulness, not just presence."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "findable": {
                "type": "object",
                "description": (
                    "Assessment of how findable this dataset is. Consider: Is the title "
                    "descriptive and searchable? Are keywords relevant and specific to the "
                    "dataset content (not generic)? Does the description tell you what the "
                    "data actually contains?"
                ),
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["good", "adequate", "weak"],
                        "description": "Overall findability verdict.",
                    },
                    "commentary": {
                        "type": "string",
                        "description": "1-2 sentence qualitative commentary on findability.",
                    },
                },
                "required": ["verdict", "commentary"],
            },
            "accessible": {
                "type": "object",
                "description": (
                    "Assessment of how accessible this dataset is. Consider: Is the license "
                    "appropriate for research data reuse? Is contact information sufficient "
                    "for a researcher who needs access?"
                ),
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["good", "adequate", "weak"],
                        "description": "Overall accessibility verdict.",
                    },
                    "commentary": {
                        "type": "string",
                        "description": "1-2 sentence qualitative commentary on accessibility.",
                    },
                },
                "required": ["verdict", "commentary"],
            },
            "interoperable": {
                "type": "object",
                "description": (
                    "Assessment of how interoperable this dataset is. Consider: Are column "
                    "names clear and unambiguous? Are units consistent and standard? Are "
                    "semantic types plausible given the column names?"
                ),
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["good", "adequate", "weak"],
                        "description": "Overall interoperability verdict.",
                    },
                    "commentary": {
                        "type": "string",
                        "description": "1-2 sentence qualitative commentary on interoperability.",
                    },
                },
                "required": ["verdict", "commentary"],
            },
            "reusable": {
                "type": "object",
                "description": (
                    "Assessment of how reusable this dataset is. Consider: Are ARRIVE fields "
                    "filled meaningfully (not just present)? Is the protocol reference usable "
                    "for reproduction? Is provenance sufficient to understand data origin?"
                ),
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["good", "adequate", "weak"],
                        "description": "Overall reusability verdict.",
                    },
                    "commentary": {
                        "type": "string",
                        "description": "1-2 sentence qualitative commentary on reusability.",
                    },
                },
                "required": ["verdict", "commentary"],
            },
            "overall_assessment": {
                "type": "string",
                "description": (
                    "2-3 sentence overall qualitative assessment of the dataset's FAIR "
                    "readiness, highlighting the most significant strengths and gaps."
                ),
            },
            "top_priority": {
                "type": "string",
                "description": (
                    "The single most impactful thing the dataset owner should fix next "
                    "to improve FAIR compliance."
                ),
            },
        },
        "required": [
            "findable", "accessible", "interoperable", "reusable",
            "overall_assessment", "top_priority",
        ],
    },
}


def run_llm_fair_score(
    import_info: dict,
    columns: list,
    metadata: dict,
    issues: list,
    arrive_data: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Use Claude to provide qualitative FAIR commentary that goes beyond the rule-based
    rubric in fair_engine.py (which checks if fields are present, but not whether
    they're meaningful).

    Returns a dict with findable/accessible/interoperable/reusable verdicts +
    commentary, an overall_assessment, and a top_priority action.
    """
    from llm_service import call_haiku

    # Trim columns to the fields the LLM needs (keep tokens low)
    columns_slim = [
        {
            "name": c.get("name"),
            "label": c.get("label"),
            "inferred_type": c.get("inferred_type"),
            "user_unit": c.get("user_unit") or c.get("unit_guess"),
            "user_description": c.get("user_description"),
        }
        for c in columns[:40]
    ]

    # Extract just the problem strings from issues (max 15)
    issue_problems = [i.get("problem", str(i)) for i in issues[:15]]

    # Build the user prompt with the dataset context
    prompt_parts = [
        "Please assess the FAIR readiness of this dataset.\n",
        f"## Dataset Metadata\n{_fmt_dict(metadata)}\n",
        f"## Column Profiles ({len(columns_slim)} of {len(columns)} shown)\n{_fmt_list(columns_slim)}\n",
        f"## Detected Issues\n{_fmt_list(issue_problems)}\n",
    ]
    if arrive_data:
        prompt_parts.append(f"## ARRIVE 2.0 Fields (from paper extraction)\n{_fmt_dict(arrive_data)}\n")

    user_message = "".join(prompt_parts)

    return call_haiku(
        system_prompt=_SYSTEM_PROMPT,
        tool=_FAIR_COMMENTARY_TOOL,
        user_message=user_message,
        model_env="FAIR_SCORER_MODEL",
        max_tokens=1024,
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_dict(d: dict) -> str:
    """Compact key: value representation of a dict."""
    if not d:
        return "(empty)"
    lines = []
    for k, v in d.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        lines.append(f"- {k}: {v}")
    return "\n".join(lines) if lines else "(no non-empty fields)"


def _fmt_list(items: List[Any]) -> str:
    """Compact list representation."""
    if not items:
        return "(none)"
    return "\n".join(f"- {item}" for item in items)
