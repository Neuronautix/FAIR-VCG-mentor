"""Anthropic service layer — in-memory key management, mirrors openai_service.py.

Priority: in-memory key set via Settings UI > ANTHROPIC_API_KEY env var.
"""
from __future__ import annotations

import os

_api_key: str | None = None

ANTHROPIC_MODEL = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")


def set_key(key: str) -> None:
    global _api_key
    _api_key = key.strip() if key else None


def clear_key() -> None:
    global _api_key
    _api_key = None


def get_key() -> str | None:
    """In-memory key first, then fall back to env var."""
    return _api_key or os.getenv("ANTHROPIC_API_KEY") or None


def is_configured() -> bool:
    return bool(get_key())


def get_status() -> dict:
    return {"configured": is_configured(), "model": ANTHROPIC_MODEL}


def _require_client():
    key = get_key()
    if not key:
        raise RuntimeError("Anthropic API key is not configured.")
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise RuntimeError("'anthropic' package is not installed.") from exc
    return anthropic.Anthropic(api_key=key)


def test_connection() -> dict:
    try:
        client = _require_client()
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply with the single word 'ok'."}],
        )
        text = resp.content[0].text if resp.content else ""
        return {"ok": True, "response": text.strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
