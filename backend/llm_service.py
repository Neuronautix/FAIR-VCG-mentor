"""
Central wrapper around LLM providers (Anthropic Claude Haiku or OpenAI).

All LLM calls in the app should funnel through `call_haiku` so we get
consistent error handling, ephemeral system-prompt caching, and a
single place to enforce anti-hallucination guards on tool outputs.

Provider selection (in priority order):
1. ANTHROPIC_API_KEY set → use Anthropic Claude Haiku (preferred)
2. OpenAI key configured via openai_service → use OpenAI function calling
3. Neither → raise LLMUnavailable

Anti-hallucination strategy:
- Tool inputs are constrained by JSON schema (forced via tool_choice).
- After the call, `validate_against_columns` filters out any column
  names the model invented that are not in the real dataset.
- Risky outputs (column type changes, metadata writes, VCG configs)
  are NEVER auto-applied — they are placed in the HITL queue for the
  user to approve, edit, or reject.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when no LLM provider is configured or a call fails."""


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504, 529)


def llm_enabled() -> bool:
    """True if ANY LLM provider is available."""
    import openai_service  # imported here to avoid circular import at module load
    return bool(os.getenv("ANTHROPIC_API_KEY")) or openai_service.is_configured()


def _anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not configured. Set this environment "
            "variable to enable Haiku-powered features."
        )
    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailable(
            "The 'anthropic' package is not installed."
        ) from exc
    return anthropic.Anthropic(api_key=api_key)


def _call_anthropic(
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
    """Call Anthropic Claude with a forced tool. Returns parsed tool input dict."""
    client = _anthropic_client()
    model = os.getenv(model_env, DEFAULT_MODEL)

    if isinstance(user_message, str):
        user_content: Any = user_message
    else:
        user_content = user_message

    system_block: List[Dict[str, Any]] = [{"type": "text", "text": system_prompt}]
    if cache_system:
        system_block[0]["cache_control"] = {"type": "ephemeral"}
    for extra in extra_system_blocks or []:
        block = {"type": "text", "text": extra["text"]} if isinstance(extra, dict) and "text" in extra else None
        if block is None:
            continue
        if cache_system:
            block["cache_control"] = {"type": "ephemeral"}
        system_block.append(block)

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_block,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": user_content}],
            )
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                    return dict(block.input or {})
            raise LLMUnavailable("Model returned no tool_use block.")
        except LLMUnavailable:
            raise
        except Exception as exc:  # anthropic.APIError etc.
            last_err = exc
            status = getattr(exc, "status_code", None)
            if attempt < max_retries and (status is None or status in _RETRYABLE_STATUS):
                delay = 5 * (2 ** attempt) if status == 529 else 0.5 * (2 ** attempt)
                time.sleep(delay)
                continue
            break

    raise LLMUnavailable(f"Haiku call failed: {last_err}")


def _call_openai(
    *,
    system_prompt: str,
    tool: Dict[str, Any],
    user_message: Any,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call OpenAI with function calling, mirroring call_haiku's interface."""
    import openai_service  # imported here to avoid circular import
    import openai

    if not openai_service.is_configured():
        raise LLMUnavailable("OpenAI API key not configured.")

    client = openai.OpenAI(api_key=openai_service._api_key)

    # Translate Anthropic tool format → OpenAI function format
    oai_tool = {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }

    # Build messages — OpenAI uses system message in messages list
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    if isinstance(user_message, str):
        messages.append({"role": "user", "content": user_message})
    else:
        # user_message is a list of content blocks (e.g. Anthropic format with PDF)
        # For OpenAI, convert to text-only (extract text blocks)
        text_parts = []
        for block in user_message:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "document":
                    # Anthropic native PDF block — extract any text available
                    source = block.get("source", {})
                    if source.get("type") == "text":
                        text_parts.append(source.get("data", ""))
        messages.append({"role": "user", "content": "\n".join(text_parts) or "(no text extracted)"})

    resp = client.chat.completions.create(
        model=openai_service.OPENAI_MODEL,
        max_tokens=max_tokens,
        tools=[oai_tool],
        tool_choice={"type": "function", "function": {"name": tool["name"]}},
        messages=messages,
        temperature=0.2,
    )

    for choice in resp.choices:
        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            if tc.function.name == tool["name"]:
                return _json.loads(tc.function.arguments)

    raise LLMUnavailable("OpenAI returned no function call result.")


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
    Call an LLM with a single forced tool, return the parsed tool input dict.

    Dispatches to Anthropic if ANTHROPIC_API_KEY is set, otherwise falls back
    to OpenAI if an OpenAI key has been configured via openai_service.

    `user_message` may be a string or a list of content blocks (e.g. for PDF input).
    `extra_system_blocks` lets callers append additional cached system blocks
    (e.g. the validated vocabulary). Each must be a `{"type": "text", "text": ...}`
    dict; cache_control is added automatically when cache_system is True.

    Raises LLMUnavailable on auth/network failure after retries are exhausted.
    """
    import openai_service  # imported here to avoid circular import

    if os.getenv("ANTHROPIC_API_KEY"):
        return _call_anthropic(
            system_prompt=system_prompt,
            tool=tool,
            user_message=user_message,
            model_env=model_env,
            max_tokens=max_tokens,
            cache_system=cache_system,
            max_retries=max_retries,
            extra_system_blocks=extra_system_blocks,
        )
    elif openai_service.is_configured():
        return _call_openai(
            system_prompt=system_prompt,
            tool=tool,
            user_message=user_message,
            max_tokens=max_tokens,
        )
    else:
        raise LLMUnavailable(
            "No AI provider configured. Set ANTHROPIC_API_KEY or add an OpenAI key in Settings."
        )


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
