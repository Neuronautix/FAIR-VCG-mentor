"""
Vocabulary discovery from a PDF or free text.

Asks Claude Haiku to mine candidate terms (units, study types, license,
controlled values) from a paper that ARE NOT YET in the validated
vocabulary. Returns proposed extensions as HITL `schema_extension`
suggestions so the user can approve / reject each one.

The tool input schema is closed (`additionalProperties: false`) and
restricts categories to the four lists managed by `vocabulary.py`.
Column-targeted controlled_values are post-filtered against real column
names.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List

from llm_service import LLMUnavailable, call_haiku
from vocabulary import ensure_vocabulary, schema_prompt_block

_PDF_MAX_BYTES = 32 * 1024 * 1024

SYSTEM_PROMPT = (
    "You are a research-data curation assistant. Mine the provided document "
    "for terms that would extend the user's controlled vocabulary. Focus on: "
    "(a) units of measurement actually used in the study, (b) study types / "
    "designs (e.g. randomised_controlled_trial, dose_response), (c) license "
    "statements, (d) controlled values that appear in tabular data described "
    "in the paper. Only propose terms that you can ground in a specific "
    "passage. Do not invent terms; if you cannot justify a term, omit it."
)


def _build_tool(vocab: Dict[str, Any]) -> Dict[str, Any]:
    col_enum = vocab["column_names"] or ["__unused__"]
    return {
        "name": "propose_vocabulary_extensions",
        "description": (
            "Propose new vocabulary terms drawn from the document. Existing "
            "terms in the validated vocabulary MUST NOT be repeated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "extensions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "enum": [
                                    "units", "study_types", "licenses", "metadata_keys",
                                    "controlled_values",
                                ],
                                "description": (
                                    "Which vocabulary list to extend. Use "
                                    "'controlled_values' together with target_column."
                                ),
                            },
                            "target_column": {
                                "anyOf": [{"enum": col_enum}, {"type": "null"}],
                                "description": (
                                    "Required when key='controlled_values'; the column "
                                    "name (from vocabulary.column_names) that this set "
                                    "of values belongs to."
                                ),
                            },
                            "values": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "1+ new terms not already in the vocabulary.",
                            },
                            "evidence": {
                                "type": "string",
                                "description": (
                                    "Short quote or page reference grounding this proposal."
                                ),
                            },
                            "confidence": {
                                "type": "number",
                                "description": "0-1 self-rated confidence.",
                            },
                        },
                        "required": ["key", "target_column", "values", "evidence", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "summary": {"type": "string"},
            },
            "required": ["extensions", "summary"],
            "additionalProperties": False,
        },
    }


def discover_from_pdf(session: Dict[str, Any], pdf_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    if len(pdf_bytes) > _PDF_MAX_BYTES:
        raise LLMUnavailable(
            f"PDF is {len(pdf_bytes) // (1024*1024)} MB — limit is 32 MB."
        )
    vocab = ensure_vocabulary(session)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    user_content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        },
        {
            "type": "text",
            "text": (
                "Read the paper and propose new vocabulary terms. Do not repeat "
                "terms already present in the validated vocabulary above. Be conservative."
            ),
        },
    ]
    raw = call_haiku(
        system_prompt=SYSTEM_PROMPT,
        tool=_build_tool(vocab),
        user_message=user_content,
        model_env="VOCAB_DISCOVERY_MODEL",
        max_tokens=2048,
        extra_system_blocks=[{"text": schema_prompt_block(session)}],
    )
    return _post_filter(raw.get("extensions") or [], vocab, source_label=f"pdf:{filename}")


def discover_from_text(session: Dict[str, Any], text: str, source_label: str = "text") -> List[Dict[str, Any]]:
    """Same as discover_from_pdf but the input is plain text (e.g. dataset description)."""
    vocab = ensure_vocabulary(session)
    raw = call_haiku(
        system_prompt=SYSTEM_PROMPT,
        tool=_build_tool(vocab),
        user_message=text[:60_000],
        model_env="VOCAB_DISCOVERY_MODEL",
        max_tokens=2048,
        extra_system_blocks=[{"text": schema_prompt_block(session)}],
    )
    return _post_filter(raw.get("extensions") or [], vocab, source_label=source_label)


def _post_filter(
    raw_extensions: List[Dict[str, Any]],
    vocab: Dict[str, Any],
    *,
    source_label: str,
) -> List[Dict[str, Any]]:
    """Remove duplicates against current vocabulary; deduplicate hallucinated controlled_values columns."""
    out: List[Dict[str, Any]] = []
    column_names = set(vocab["column_names"])
    existing_by_key: Dict[str, set] = {
        "units": set(vocab.get("units") or []),
        "study_types": set(vocab.get("study_types") or []),
        "licenses": set(vocab.get("licenses") or []),
        "metadata_keys": set(vocab.get("metadata_keys") or []),
    }
    existing_controlled = {
        col: set(vals) for col, vals in (vocab.get("controlled_values") or {}).items()
    }

    for ext in raw_extensions:
        key = ext.get("key")
        values = [str(v) for v in (ext.get("values") or []) if v]
        if not values:
            continue
        if key == "controlled_values":
            target_col = ext.get("target_column")
            if not target_col or target_col not in column_names:
                continue
            existing = existing_controlled.get(target_col, set())
            new_vals = [v for v in values if v not in existing]
            if not new_vals:
                continue
            out.append({
                "hitl_key": f"controlled_values:{target_col}",
                "values": new_vals,
                "evidence": ext.get("evidence") or "",
                "confidence": float(ext.get("confidence") or 0.0),
                "source_label": source_label,
                "human_key": f"controlled values for `{target_col}`",
            })
        elif key in existing_by_key:
            new_vals = [v for v in values if v not in existing_by_key[key]]
            if not new_vals:
                continue
            out.append({
                "hitl_key": key,
                "values": new_vals,
                "evidence": ext.get("evidence") or "",
                "confidence": float(ext.get("confidence") or 0.0),
                "source_label": source_label,
                "human_key": key,
            })
    return out


def extension_to_hitl_payload(ext: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a filtered extension to hitl.add_suggestion kwargs."""
    return {
        "category": "schema_extension",
        "target": ext["hitl_key"],
        "source": "llm:claude-haiku-4-5",
        "title": f"Extend {ext['human_key']} with {len(ext['values'])} term(s)",
        "rationale": (
            (ext.get("evidence") or "Proposed from document.")
            + f" (source: {ext.get('source_label')})"
        ),
        "payload": {
            "key": ext["hitl_key"],
            "values": ext["values"],
            "source": ext.get("source_label"),
        },
        "confidence": float(ext.get("confidence") or 0.0),
    }
