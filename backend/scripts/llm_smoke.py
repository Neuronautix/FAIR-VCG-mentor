#!/usr/bin/env python3
"""Live smoke check for the configured LLM provider.

Prints the active provider configuration, then makes ONE real `call_haiku`
request using a tiny forced tool ("echo_check") and prints the parsed dict.

Exit codes:
  0  success — the endpoint answered and returned a parseable tool object.
  1  failure — provider unavailable / misconfigured / call failed (a clear
     message is printed; no traceback).

Usage:
  # from the repository root
  python backend/scripts/llm_smoke.py

  # from the backend/ directory
  python scripts/llm_smoke.py

Configure the provider first (e.g. copy backend/.env.local-llm.example to
backend/.env and start LM Studio's local server on :1234), or export
LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL in your shell.
"""
from __future__ import annotations

import json
import os
import sys

# Make `import llm_service` work whether run from repo root or backend/.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from llm_service import LLMUnavailable, call_haiku, llm_enabled, provider_info  # noqa: E402


ECHO_TOOL = {
    "name": "echo_check",
    "description": "Echo back a fixed confirmation string.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ok": {
                "type": "string",
                "description": "Set this to the string 'ok'.",
            }
        },
        "required": ["ok"],
    },
}


def main() -> int:
    info = provider_info()
    print("Provider configuration:")
    print(json.dumps(info, indent=2))

    if not llm_enabled():
        print(
            "\nFAILURE: the configured provider is not enabled. "
            "Set the required env vars (e.g. LLM_PROVIDER=openai with "
            "LLM_BASE_URL and LLM_MODEL, or ANTHROPIC_API_KEY for anthropic).",
            file=sys.stderr,
        )
        return 1

    print("\nMaking one live call_haiku request (tool='echo_check')...")
    try:
        result = call_haiku(
            system_prompt=(
                "You are a connectivity probe. Respond with the echo_check tool "
                "and set 'ok' to the literal string 'ok'."
            ),
            tool=ECHO_TOOL,
            user_message="Reply with ok.",
            max_tokens=64,
        )
    except LLMUnavailable as exc:
        print(f"\nFAILURE: LLM endpoint unavailable: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — keep the smoke check traceback-free
        print(f"\nFAILURE: unexpected error during call: {exc}", file=sys.stderr)
        return 1

    print("Parsed tool result:")
    print(json.dumps(result, indent=2))
    print("\nSUCCESS: endpoint answered and returned a parseable tool object.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
