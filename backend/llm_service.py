"""
Compatibility wrapper for LLM-powered HITL calls.

All LLM calls in the app should funnel through `call_haiku` so we get
consistent error handling, ephemeral system-prompt caching, and a
single place to enforce anti-hallucination guards on tool outputs.

Anti-hallucination strategy:
- Tool inputs are constrained by JSON schema (forced via tool_choice).
- After the call, `validate_against_columns` filters out any column
  names the model invented that are not in the real dataset.
- Risky outputs (column type changes, metadata writes, VCG configs)
  are NEVER auto-applied — they are placed in the HITL queue for the
  user to approve, edit, or reject.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from llm_providers import (
    DEFAULT_ANTHROPIC_MODEL,
    LLMOptions,
    LLMRequest,
    LLMUnavailable,
    create_provider,
)

logger = logging.getLogger(__name__)


DEFAULT_MODEL = DEFAULT_ANTHROPIC_MODEL


def llm_enabled() -> bool:
    return create_provider().healthcheck().available


def llm_source_label(model_env: Optional[str] = None) -> str:
    meta = create_provider(model_env=model_env).metadata
    return f"llm:{meta.name}:{meta.model}"


def call_haiku(
    *,
    system_prompt: str,
    tool: Dict[str, Any],
    user_message: Any,
    model_env: str = "HAIKU_MODEL",
    max_tokens: int = 1024,
    cache_system: bool = True,
    max_retries: int = 2,
    extra_system_blocks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Call Claude Haiku with a single forced tool, return the parsed tool input dict.

    `user_message` may be a string or a list of content blocks (e.g. for PDF input).
    `extra_system_blocks` lets callers append additional cached system blocks
    (e.g. the validated vocabulary). Each must be a `{"type": "text", "text": ...}`
    dict; cache_control is added automatically when cache_system is True.

    Raises LLMUnavailable on auth/network failure after retries are exhausted.
    """
    provider = create_provider(model_env=model_env)
    resp = provider.complete(
        LLMRequest(
            system_prompt=system_prompt,
            user_message=user_message,
            tool=tool,
            model_env=model_env,
            extra_system_blocks=extra_system_blocks or [],
        ),
        LLMOptions(
            max_tokens=max_tokens,
            cache_system=cache_system,
            max_retries=max_retries,
        ),
    )
    return dict(resp.tool_input or {})


# ── Anti-hallucination helpers ───────────────────────────────────────────────

def validate_columns_exist(
    suggested: List[str],
    real_columns: List[str],
) -> Dict[str, List[str]]:
    """
    Split a list of suggested column names into those that exist in the dataset
    and those the model hallucinated.

    Returns: {"valid": [...], "hallucinated": [...]}.
    """
    real_set = {c for c in real_columns}
    valid = [c for c in suggested or [] if c in real_set]
    bad = [c for c in suggested or [] if c not in real_set]
    if bad:
        logger.warning("LLM produced unknown column names: %s", bad)
    return {"valid": valid, "hallucinated": bad}


def value_exists_in_column(
    df_value_set: List[str],
    suggested: Any,
) -> bool:
    """True if `suggested` is one of the actual values seen in a column."""
    if suggested is None:
        return False
    return str(suggested) in {str(v) for v in df_value_set}


def fmt_columns_for_prompt(columns: List[Dict[str, Any]], limit: int = 50) -> str:
    """Compact column summary suitable for LLM input. Keeps tokens low."""
    lines = []
    for c in columns[:limit]:
        name = c.get("name")
        itype = c.get("user_type") or c.get("inferred_type") or "?"
        dtype = c.get("data_type") or "?"
        samples = ", ".join(str(v) for v in (c.get("sample_values") or [])[:4])
        unit = c.get("user_unit") or c.get("unit_guess") or ""
        unit_s = f", unit={unit}" if unit else ""
        lines.append(f"- {name} (type={itype}, dtype={dtype}{unit_s}) samples=[{samples}]")
    if len(columns) > limit:
        lines.append(f"... ({len(columns) - limit} more columns not shown)")
    return "\n".join(lines)
