"""
Central wrapper around the configured LLM provider.

All LLM calls in the app should funnel through `call_haiku` so we get
consistent error handling, a single provider seam, and one place to enforce
anti-hallucination guards on tool outputs.

Two providers are supported, selected by the `LLM_PROVIDER` env var:

- ``anthropic`` (default) — Anthropic Claude via the official SDK, using a
  forced single-tool call and ephemeral system-prompt caching.
- ``openai`` — any OpenAI-compatible endpoint (e.g. LM Studio serving a local
  model such as Gemma or APERTUS). The forced-tool pattern is mapped onto a
  structured-output ``response_format`` built from the tool's ``input_schema``,
  which is far more reliable on local models than tool-calling. PDFs are
  converted to text locally (pdfminer.six) because text-only local models do
  not accept native document blocks.

Both providers return the same shape: a dict equal to the tool's input object,
so the ten call sites are provider-agnostic.

Anti-hallucination strategy:
- Tool inputs are constrained by JSON schema (forced via tool_choice or
  structured output).
- After the call, `validate_columns_exist` filters out any column names the
  model invented that are not in the real dataset.
- Risky outputs (column type changes, metadata writes, VCG configs) are NEVER
  auto-applied — they are placed in the HITL queue for the user to approve.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from env_loader import load_local_env

logger = logging.getLogger(__name__)
load_local_env()


class LLMUnavailable(RuntimeError):
    """Raised when the configured provider is missing/misconfigured or a call fails."""


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504, 529)
_DEFAULT_MAX_DOC_CHARS = 60000


# ── Provider selection ───────────────────────────────────────────────────────

def _provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def llm_enabled() -> bool:
    """True when the configured provider has the minimum config to be callable."""
    if _provider() == "openai":
        return bool(os.getenv("LLM_BASE_URL") and (os.getenv("LLM_MODEL") or os.getenv("HAIKU_MODEL")))
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def provider_info() -> Dict[str, Any]:
    """Lightweight description of the active provider for /api/llm/status."""
    provider = _provider()
    if provider == "openai":
        return {
            "provider": "openai",
            "model": os.getenv("LLM_MODEL"),
            "base_url": os.getenv("LLM_BASE_URL"),
            "enabled": llm_enabled(),
        }
    return {
        "provider": "anthropic",
        "model": os.getenv("HAIKU_MODEL", DEFAULT_MODEL),
        "base_url": None,
        "enabled": llm_enabled(),
    }


# ── Public entry point ───────────────────────────────────────────────────────

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
    Call the configured LLM with a single forced tool; return the parsed tool input dict.

    `user_message` may be a string or a list of content blocks (e.g. for PDF input
    via an Anthropic `document` block). `extra_system_blocks` lets callers append
    additional system blocks (e.g. the validated vocabulary); each must be a
    `{"type": "text", "text": ...}` dict.

    Raises LLMUnavailable on auth/network/parse failure after retries are exhausted.
    """
    if _provider() == "openai":
        return _call_openai(
            system_prompt=system_prompt,
            tool=tool,
            user_message=user_message,
            model_env=model_env,
            max_tokens=max_tokens,
            max_retries=max_retries,
            extra_system_blocks=extra_system_blocks,
        )
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


# ── Anthropic provider ───────────────────────────────────────────────────────

def _anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not configured. Set this environment "
            "variable to enable Claude-powered features."
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
    model_env: str,
    max_tokens: int,
    cache_system: bool,
    max_retries: int,
    extra_system_blocks: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    client = _anthropic_client()
    model = os.getenv(model_env, DEFAULT_MODEL)

    user_content: Any = user_message

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

    raise LLMUnavailable(f"Anthropic call failed: {last_err}")


# ── OpenAI-compatible provider (LM Studio / local models) ────────────────────

def _openai_client():
    base_url = os.getenv("LLM_BASE_URL")
    if not base_url:
        raise LLMUnavailable(
            "LLM_BASE_URL is not configured for the local (openai) provider. "
            "Point it at your LM Studio endpoint, e.g. http://localhost:1234/v1."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMUnavailable(
            "The 'openai' package is not installed. Add it to requirements.txt "
            "to enable the local LLM provider."
        ) from exc
    api_key = os.getenv("LLM_API_KEY") or "lm-studio"
    return OpenAI(base_url=base_url, api_key=api_key)


def _call_openai(
    *,
    system_prompt: str,
    tool: Dict[str, Any],
    user_message: Any,
    model_env: str,
    max_tokens: int,
    max_retries: int,
    extra_system_blocks: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    client = _openai_client()
    model = os.getenv(model_env) or os.getenv("LLM_MODEL")
    if not model:
        raise LLMUnavailable(
            "No local model is configured. Set LLM_MODEL (or the per-feature "
            f"{model_env}) to the model id served by your local endpoint."
        )

    schema = tool.get("input_schema") or {"type": "object"}

    sys_text = system_prompt
    for extra in extra_system_blocks or []:
        if isinstance(extra, dict) and "text" in extra:
            sys_text += "\n\n" + str(extra["text"])
    sys_text += (
        f"\n\nRespond ONLY with a single JSON object that conforms to the required "
        f"schema for '{tool['name']}'. Do not include any prose, markdown, or code "
        f"fences — return JSON only."
    )

    user_text = _blocks_to_text(user_message)
    messages = [
        {"role": "system", "content": sys_text},
        {"role": "user", "content": user_text},
    ]

    # First attempt uses a strict json_schema response format; subsequent
    # attempts fall back to plain json_object, which more local servers accept.
    response_formats = [
        {"type": "json_schema", "json_schema": {"name": tool["name"], "schema": schema}},
        {"type": "json_object"},
    ]

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        rf = response_formats[min(attempt, len(response_formats) - 1)]
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                messages=messages,
                response_format=rf,
            )
            content = resp.choices[0].message.content or ""
            return _parse_json_object(content)
        except LLMUnavailable:
            raise
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
            break

    raise LLMUnavailable(f"Local LLM call failed: {last_err}")


def _parse_json_object(content: str) -> Dict[str, Any]:
    """Parse a JSON object from a (possibly fenced/noisy) model response."""
    text = (content or "").strip()
    if not text:
        raise ValueError("empty response from local model")
    if text.startswith("```"):
        text = text.strip("`").strip()
        text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()
    try:
        return dict(json.loads(text))
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return dict(json.loads(match.group(0)))
        raise ValueError("could not parse a JSON object from the model response")


def _blocks_to_text(user_message: Any) -> str:
    """Flatten an Anthropic-style content list into plain text for local models.

    Native `document` (PDF) blocks are converted to text locally via
    pdfminer.six, since text-only local models cannot ingest document blocks.
    """
    if isinstance(user_message, str):
        return user_message
    parts: List[str] = []
    for block in user_message or []:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(str(block.get("text") or ""))
        elif btype == "document":
            src = block.get("source") or {}
            if src.get("type") == "base64" and "pdf" in str(src.get("media_type") or ""):
                parts.append(_extract_pdf_text(str(src.get("data") or "")))
            else:
                parts.append("[unsupported document block omitted]")
        else:
            # image or other block types are not supported by text-only models
            continue
    return "\n\n".join(p for p in parts if p)


def _extract_pdf_text(data_b64: str) -> str:
    import base64
    import io

    try:
        from pdfminer.high_level import extract_text
    except ImportError as exc:
        raise LLMUnavailable(
            "pdfminer.six is required to process PDFs with a local model."
        ) from exc
    try:
        raw = base64.b64decode(data_b64)
        text = extract_text(io.BytesIO(raw)) or ""
    except Exception as exc:
        raise LLMUnavailable(f"Failed to extract text from PDF locally: {exc}")
    max_chars = _int_env("LLM_MAX_DOC_CHARS", _DEFAULT_MAX_DOC_CHARS)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text


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
