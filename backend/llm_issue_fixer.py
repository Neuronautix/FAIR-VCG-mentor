"""
Use Claude Haiku to propose concrete, actionable fixes for FAIR issues
detected by `fair_engine.detect_issues`.

Each LLM suggestion is queued as a HITL "issue_fix" suggestion so the
user can review the proposed remediation before any state changes occur.
A suggestion may include an optional `metadata_patch` that, if approved,
is applied to `session["metadata"]`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from llm_service import call_haiku, fmt_columns_for_prompt
from vocabulary import ensure_vocabulary, schema_prompt_block


SYSTEM_PROMPT = (
    "You are a FAIR data assistant. Given a list of detected issues and the "
    "dataset's current metadata, propose concrete, minimal fixes. Prefer "
    "fixes that can be applied as a metadata patch using ONLY keys from the "
    "VALIDATED VOCABULARY metadata_keys list and license / study_type values "
    "from the same vocabulary. For issues that need user-side work, explain "
    "what the user must do in one sentence. Be conservative: do not invent "
    "author names, institutions, DOIs, or license URIs."
)


def _build_tool(vocab: Dict[str, Any]) -> Dict[str, Any]:
    metadata_keys = vocab.get("metadata_keys") or []
    patch_properties: Dict[str, Any] = {}
    for k in metadata_keys:
        if k == "license":
            patch_properties[k] = {
                "anyOf": [{"enum": vocab.get("licenses") or []}, {"type": "null"}],
                "description": "SPDX identifier from vocabulary.licenses.",
            }
        elif k == "study_type":
            patch_properties[k] = {
                "anyOf": [{"enum": vocab.get("study_types") or []}, {"type": "null"}],
                "description": "Study type from vocabulary.study_types.",
            }
        elif k == "keywords":
            patch_properties[k] = {"type": "array", "items": {"type": "string"}}
        else:
            patch_properties[k] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "name": "suggest_fair_fixes",
        "description": "Produce one suggestion per input issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "issue_id": {
                                "type": "string",
                                "description": "Exact issue.id from the input.",
                            },
                            "recommendation": {
                                "type": "string",
                                "description": "1-2 sentence concrete remediation.",
                            },
                            "metadata_patch": {
                                "type": "object",
                                "properties": patch_properties,
                                "additionalProperties": False,
                                "description": (
                                    "Optional dict to merge into dataset metadata if "
                                    "approved. Only keys from vocabulary.metadata_keys "
                                    "are allowed. Leave empty if no patch is safe."
                                ),
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Self-rated 0-1 confidence.",
                            },
                        },
                        "required": ["issue_id", "recommendation", "metadata_patch", "confidence"],
                    },
                },
            },
            "required": ["suggestions"],
        },
    }


def suggest_issue_fixes(
    issues: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    columns: List[Dict[str, Any]],
    max_issues: int = 12,
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Returns a list of LLM-proposed fixes, one per relevant issue."""
    issues = [i for i in issues if i.get("id")]
    if not issues:
        return []

    issues_block = "\n".join(
        f"- id={i['id']} severity={i.get('severity')} column={i.get('column') or '-'} "
        f"problem={i.get('problem')}"
        for i in issues[:max_issues]
    )

    md_block = "\n".join(
        f"- {k}: {v}" for k, v in (metadata or {}).items() if v not in (None, "", [], {})
    ) or "(empty)"

    user_msg = (
        "## Current metadata\n" + md_block
        + "\n\n## Detected issues (limit "
        + str(max_issues) + ")\n" + issues_block
        + "\n\n## Column overview (for context)\n"
        + fmt_columns_for_prompt(columns, limit=20)
    )

    if session is None:
        session = {"columns": columns, "metadata": metadata or {}}
    vocab = ensure_vocabulary(session)

    raw = call_haiku(
        system_prompt=SYSTEM_PROMPT,
        tool=_build_tool(vocab),
        user_message=user_msg,
        model_env="ISSUE_FIXER_MODEL",
        max_tokens=2048,
        extra_system_blocks=[{"text": schema_prompt_block(session)}],
    )

    issue_ids = {i["id"] for i in issues}
    allowed_keys = set(vocab.get("metadata_keys") or [])
    valid: List[Dict[str, Any]] = []
    for s in raw.get("suggestions", []) or []:
        if s.get("issue_id") in issue_ids and s.get("recommendation"):
            patch = s.get("metadata_patch") or {}
            # Server-side belt-and-braces: tool schema already restricts keys,
            # but re-filter in case future schema edits widen it.
            patch = {k: v for k, v in patch.items() if k in allowed_keys and v not in (None, "", [])}
            s["metadata_patch"] = patch
            valid.append(s)
    return valid


def fix_to_hitl_payload(fix: Dict[str, Any], issue: Dict[str, Any]) -> Dict[str, Any]:
    from llm_service import llm_source_label

    payload: Dict[str, Any] = {"recommendation": fix["recommendation"]}
    if fix.get("metadata_patch"):
        payload["metadata_patch"] = fix["metadata_patch"]
    return {
        "category": "issue_fix",
        "target": fix["issue_id"],
        "source": llm_source_label("ISSUE_FIXER_MODEL"),
        "title": f"Fix: {issue.get('problem', fix['issue_id'])[:120]}",
        "rationale": fix["recommendation"],
        "payload": payload,
        "confidence": float(fix.get("confidence") or 0.0),
    }
