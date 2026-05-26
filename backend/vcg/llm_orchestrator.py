"""
Claude Haiku-driven VCG chat orchestrator.

Replaces the rigid finite-state machine in `orchestrator.py` with a free-form
conversation that nonetheless emits a structured configuration through a
forced tool call. The model is asked to:

  1. Hold a natural dialogue with the user about the study.
  2. Extract column role assignments using ONLY column names that exist
     in the dataset (passed in the system prompt).
  3. Decide whether enough information has been gathered to build the VCG.

Anti-hallucination guards:
  - Column names are validated against `session.columns` after every turn.
  - control_value / treatment_value must appear in the actual `df` values.
  - When the model declares `ready_to_build`, the proposed config is queued
    as a HITL suggestion. The user must approve it explicitly before
    `run_vcg_pipeline` runs.

This module does NOT modify session["vcg"] directly; it returns a chat
turn dict (same shape as the rule-based orchestrator) plus an optional
hitl_suggestion dict the router places in the HITL queue.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from llm_service import LLMUnavailable, call_haiku, llm_source_label, validate_columns_exist
from vcg.constants import CONTROL_KEYWORDS
from vocabulary import enum_array, enum_or_null, ensure_vocabulary, schema_prompt_block

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a VCG (Virtual Control Group) configuration assistant. "
    "You help researchers configure a synthetic control group from a real "
    "concurrent control. Be concise (1–3 short paragraphs per message), "
    "ask one focused question at a time, and use Markdown sparingly.\n\n"
    "STRICT RULES — NEVER VIOLATE:\n"
    "1. Use ONLY column names from the 'AVAILABLE COLUMNS' list. Never invent "
    "   column names. If the user mentions a column that isn't in the list, "
    "   ask them to clarify which of the listed columns they meant.\n"
    "2. Use ONLY values that appear in the column's 'sample_values' for "
    "   control_value / treatment_value.\n"
    "3. Set ready_to_build=true only after the user has explicitly confirmed "
    "   the configuration in your most recent summary. Do not assume.\n"
    "4. If unsure, say so and ask. Do not fabricate sample sizes or units."
)


def _build_tool(vocab: Dict[str, Any]) -> Dict[str, Any]:
    col_enum = vocab["column_names"] or ["__unused__"]
    # Union of every controlled value seen across columns — narrows
    # the model's options for control/treatment values even before it
    # commits to a specific treatment_col.
    value_union: List[str] = []
    for vals in (vocab.get("controlled_values") or {}).values():
        for v in vals:
            if v not in value_union:
                value_union.append(v)

    study_types = vocab.get("study_types") or []
    return {
        "name": "vcg_chat_turn",
        "description": (
            "Produce the next assistant message and the current best-guess VCG "
            "configuration. Re-emit the full configuration on every turn — fields "
            "you haven't established yet should be null or empty arrays."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "assistant_message": {
                    "type": "string",
                    "description": "Markdown message to display to the user.",
                },
                "quick_reply_options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "0–6 short button-friendly options the user may click.",
                },
                "column_roles": {
                    "type": "object",
                    "properties": {
                        "subject_id": {"anyOf": [{"enum": col_enum}, {"type": "null"}]},
                        "treatment_col": {"anyOf": [{"enum": col_enum}, {"type": "null"}]},
                        "control_value": enum_or_null(value_union),
                        "treatment_value": enum_or_null(value_union),
                        "outcome_cols": enum_array(vocab["column_names"]),
                        "covariate_cols": enum_array(vocab["column_names"]),
                        "time_col": {"anyOf": [{"enum": col_enum}, {"type": "null"}]},
                        "exclude_cols": enum_array(vocab["column_names"]),
                    },
                    "required": [
                        "subject_id", "treatment_col", "control_value",
                        "treatment_value", "outcome_cols", "covariate_cols",
                        "time_col", "exclude_cols",
                    ],
                },
                "vcg_config": {
                    "type": "object",
                    "properties": {
                        "method": {"enum": ["auto", "bootstrap", "synthetic"]},
                        "n_synthetic": {"type": "integer", "minimum": 5, "maximum": 1000},
                        "seed": {"type": "integer"},
                        "confidence_level": {"type": "number"},
                    },
                    "required": ["method", "n_synthetic", "seed", "confidence_level"],
                },
                "research_context": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string"},
                        "study_type": (
                            {"enum": study_types} if study_types else {"type": "string"}
                        ),
                        "design": {"type": "string"},
                    },
                    "required": ["domain", "study_type", "design"],
                },
                "ready_to_build": {
                    "type": "boolean",
                    "description": "True only after explicit user confirmation of the summary.",
                },
            },
            "required": [
                "assistant_message", "quick_reply_options",
                "column_roles", "vcg_config", "research_context", "ready_to_build",
            ],
        },
    }


def _column_summary(columns: List[Dict[str, Any]]) -> str:
    lines = ["AVAILABLE COLUMNS (use these names verbatim only):"]
    for c in columns[:80]:
        samples = ", ".join(str(v) for v in (c.get("sample_values") or [])[:6])
        itype = c.get("user_type") or c.get("inferred_type") or "?"
        unit = c.get("user_unit") or c.get("unit_guess") or ""
        unit_s = f", unit={unit}" if unit else ""
        lines.append(f"  - {c['name']} (type={itype}{unit_s}) samples=[{samples}]")
    if len(columns) > 80:
        lines.append(f"  ... ({len(columns) - 80} more columns omitted)")
    return "\n".join(lines)


def _build_dataset_context(session: Dict[str, Any]) -> str:
    import_info = session.get("import_info", {})
    ts = session.get("table_structure", {})
    md = session.get("metadata", {})
    lines = [
        "DATASET CONTEXT",
        f"  rows={import_info.get('n_rows')}, columns={import_info.get('n_columns')}",
        f"  primary_entity={ts.get('primary_entity')}, shape={ts.get('table_shape')}",
    ]
    if md.get("species"):
        lines.append(f"  species={md.get('species')}")
    if md.get("study_type"):
        lines.append(f"  study_type={md.get('study_type')}")
    return "\n".join(lines)


def _conversation_history(session: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for msg in session.get("vcg", {}).get("conversation", []):
        role = "assistant" if msg.get("role") == "agent" else "user"
        out.append({"role": role, "content": str(msg.get("content", ""))})
    return out


def _enforce_grounding(
    raw: Dict[str, Any], session: Dict[str, Any]
) -> Dict[str, Any]:
    """Strip hallucinated column names and unknown values from a tool output."""
    columns = session.get("columns") or []
    df = session.get("df")
    real_names = [c["name"] for c in columns]

    roles = dict(raw.get("column_roles") or {})

    def keep_if_exists(value):
        return value if (value and value in real_names) else None

    roles["subject_id"] = keep_if_exists(roles.get("subject_id"))
    roles["treatment_col"] = keep_if_exists(roles.get("treatment_col"))
    roles["time_col"] = keep_if_exists(roles.get("time_col"))
    roles["outcome_cols"] = validate_columns_exist(roles.get("outcome_cols") or [], real_names)["valid"]
    roles["covariate_cols"] = validate_columns_exist(roles.get("covariate_cols") or [], real_names)["valid"]
    roles["exclude_cols"] = validate_columns_exist(roles.get("exclude_cols") or [], real_names)["valid"]

    treatment_col = roles.get("treatment_col")
    if treatment_col and df is not None and treatment_col in df.columns:
        actual_vals = {str(v) for v in df[treatment_col].dropna().astype(str).unique().tolist()}
        cv = roles.get("control_value")
        tv = roles.get("treatment_value")
        roles["control_value"] = str(cv) if (cv is not None and str(cv) in actual_vals) else None
        roles["treatment_value"] = str(tv) if (tv is not None and str(tv) in actual_vals) else None
    else:
        roles["control_value"] = None
        roles["treatment_value"] = None

    raw["column_roles"] = roles
    return raw


def _build_summary_markdown(roles: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    rows = [
        f"| Treatment column | `{roles.get('treatment_col') or '_not set_'}` |",
        f"| Control group | `{roles.get('control_value') or '_not set_'}` |",
        f"| Treatment group | `{roles.get('treatment_value') or '_not set_'}` |",
        f"| Outcomes | {', '.join(f'`{c}`' for c in roles.get('outcome_cols', [])) or '_none_'} |",
        f"| Covariates | {', '.join(f'`{c}`' for c in roles.get('covariate_cols', [])) or '_none_'} |",
        f"| Subjects to generate | {cfg.get('n_synthetic')} |",
        f"| Method | {cfg.get('method')} |",
    ]
    return "**Proposed VCG configuration:**\n\n| Parameter | Value |\n|---|---|\n" + "\n".join(rows)


def llm_turn(session: Dict[str, Any], user_message: str | None) -> Dict[str, Any]:
    """
    Run one LLM-driven chat turn.

    Returns:
        {
          "agent_msg": {role, content, state, options, ready_to_build, timestamp},
          "raw": {...},                    # the full tool output (grounded)
          "hitl_suggestion": {...} | None  # kwargs for hitl.add_suggestion when ready_to_build
        }
    """
    columns = session.get("columns") or []
    if not columns:
        raise LLMUnavailable("No columns available — upload a CSV first.")

    conv = session.setdefault("vcg", {}).setdefault("conversation", [])
    if user_message is not None:
        conv.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat(),
        })

    prelude = (
        _build_dataset_context(session) + "\n\n" + _column_summary(columns) + "\n\n"
        "CONVERSATION SO FAR (you replied as 'agent'):"
    )

    history_msgs = _conversation_history(session)
    if not history_msgs:
        # first call — no user message yet
        history_msgs = [{"role": "user", "content": "Hello, please get started."}]
    elif history_msgs[-1]["role"] != "user":
        history_msgs.append({"role": "user", "content": "(continue)"})

    user_content = [
        {"type": "text", "text": prelude + "\n" + _format_history(history_msgs)}
    ]

    vocab = ensure_vocabulary(session)
    raw = call_haiku(
        system_prompt=SYSTEM_PROMPT,
        tool=_build_tool(vocab),
        user_message=user_content,
        model_env="VCG_ORCHESTRATOR_MODEL",
        max_tokens=1024,
        extra_system_blocks=[{"text": schema_prompt_block(session)}],
    )
    raw = _enforce_grounding(raw, session)

    msg_text = raw.get("assistant_message") or "..."
    options = list(raw.get("quick_reply_options") or [])[:6]
    ready = bool(raw.get("ready_to_build"))

    # Default suggested control_value from CONTROL_KEYWORDS if model returned null
    # but treatment_col looks valid.
    roles = raw["column_roles"]
    if roles.get("treatment_col") and not roles.get("control_value"):
        df = session.get("df")
        if df is not None and roles["treatment_col"] in df.columns:
            for v in df[roles["treatment_col"]].dropna().astype(str).unique().tolist():
                if any(k in v.lower() for k in CONTROL_KEYWORDS):
                    roles["control_value"] = v
                    break

    hitl_suggestion = None
    if ready:
        # Refuse to declare ready if required fields are still missing — instead
        # downgrade and ask the user.
        missing = _missing_required(roles)
        if missing:
            ready = False
            msg_text += (
                "\n\nI still need: " + ", ".join(f"`{m}`" for m in missing) + "."
            )
        else:
            summary = _build_summary_markdown(roles, raw["vcg_config"])
            hitl_suggestion = {
                "category": "vcg_config",
                "target": "vcg_chat",
                "source": llm_source_label("VCG_ORCHESTRATOR_MODEL"),
                "title": "Approve LLM-proposed VCG configuration",
                "rationale": (
                    "The chat assistant believes it has gathered enough information "
                    "to generate the VCG. Review the proposed mapping below and approve, "
                    "edit, or reject."
                ),
                "payload": {
                    "column_roles": raw["column_roles"],
                    "vcg_config": raw["vcg_config"],
                    "research_context": raw["research_context"],
                },
                "confidence": 0.8,
            }
            msg_text = (
                msg_text
                + "\n\n"
                + summary
                + "\n\n_This configuration has been queued for your approval. "
                "Click **Approve** in the HITL panel to start generation._"
            )

    agent_msg = {
        "role": "agent",
        "content": msg_text,
        "state": "LLM_CHAT",
        "options": options,
        "ready_to_build": False,  # never auto-trigger; HITL approval gates this
        "timestamp": datetime.now().isoformat(),
        "source": llm_source_label("VCG_ORCHESTRATOR_MODEL"),
    }
    conv.append(agent_msg)

    return {"agent_msg": agent_msg, "raw": raw, "hitl_suggestion": hitl_suggestion}


def _format_history(history: List[Dict[str, str]]) -> str:
    lines = []
    for m in history:
        prefix = "USER" if m["role"] == "user" else "AGENT"
        lines.append(f"[{prefix}] {m['content']}")
    return "\n".join(lines)


def _missing_required(roles: Dict[str, Any]) -> List[str]:
    missing = []
    if not roles.get("treatment_col"):
        missing.append("treatment_col")
    if not roles.get("control_value"):
        missing.append("control_value")
    if not roles.get("outcome_cols"):
        missing.append("outcome_cols")
    return missing
