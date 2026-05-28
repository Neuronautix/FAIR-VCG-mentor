"""OpenAI service layer for FAIR Mentor demo.

The API key is stored ONLY in the module-level variable below.
It is never written to SQLite, never logged, never returned in any response.
"""
from __future__ import annotations

import os
from typing import Any

# In-memory key store — never persisted anywhere
_api_key: str | None = None

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ── Key management ────────────────────────────────────────────────────────────

def set_key(key: str) -> None:
    """Store the OpenAI API key in memory only."""
    global _api_key
    _api_key = key.strip() if key else None


def clear_key() -> None:
    """Remove the stored OpenAI API key."""
    global _api_key
    _api_key = None


def is_configured() -> bool:
    """Return True if an API key has been stored."""
    return bool(_api_key)


def get_status() -> dict:
    """Return configuration status — never exposes the key itself."""
    return {"configured": is_configured(), "model": OPENAI_MODEL}


# ── Internal helper ───────────────────────────────────────────────────────────

def _require_client():
    """Return an openai.OpenAI client, or raise RuntimeError if key not set."""
    if not _api_key:
        raise RuntimeError("OpenAI API key is not configured.")
    try:
        import openai  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai package is not installed.") from exc
    return openai.OpenAI(api_key=_api_key)


def _chat(messages: list[dict], max_tokens: int = 512) -> str:
    """Single-turn chat completion; returns the assistant text."""
    client = _require_client()
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


# ── Public suggestion functions ───────────────────────────────────────────────

def test_connection() -> dict:
    """Send a minimal API call to verify the key works.

    Returns {"ok": True} or {"ok": False, "error": str}.
    """
    try:
        client = _require_client()
        import openai  # type: ignore
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "Reply with the single word 'ok'."}],
            max_tokens=5,
        )
        text = response.choices[0].message.content or ""
        return {"ok": True, "response": text.strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def suggest_dataset_metadata(
    title: str | None,
    description: str | None,
    issues: list[dict],
) -> dict[str, Any]:
    """Suggest improvements for dataset-level metadata.

    Only title, description, and a summary of issue categories are sent.
    Raw data is never included.
    """
    issue_summary = []
    for issue in issues[:10]:
        issue_summary.append({
            "category": issue.get("category", ""),
            "severity": issue.get("severity", ""),
            "problem": issue.get("problem", ""),
        })

    prompt = (
        "You are a research data management expert. Based on the metadata and issues "
        "below, suggest concrete improvements to the dataset title and description. "
        "Return a JSON object with keys: 'title_suggestion', 'description_suggestion', "
        "'rationale'. Keep suggestions concise and scientific."
    )
    user_msg = (
        f"Current title: {title or '(none)'}\n"
        f"Current description: {description or '(none)'}\n"
        f"Detected issues ({len(issue_summary)} shown): {issue_summary}"
    )
    try:
        import json
        raw = _chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ], max_tokens=512)
        # Try to parse JSON from response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return {"title_suggestion": None, "description_suggestion": None, "rationale": raw}
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc


def suggest_column_descriptions(
    column_samples: list[dict],
) -> dict[str, str]:
    """Suggest descriptions for columns based on name, type, and sample values.

    column_samples: list of dicts with keys: name, data_type, sample_values (up to 3)
    Returns a dict mapping column name to suggested description.
    Never includes full dataset rows.
    """
    import json as _json

    # Send only name, type, and first 3 sample values per column
    safe_cols = []
    for col in column_samples:
        safe_cols.append({
            "name": col.get("name", ""),
            "data_type": col.get("data_type", ""),
            "sample_values": (col.get("sample_values") or [])[:3],
        })

    prompt = (
        "You are a research data management expert. For each column below, write a "
        "concise one-sentence description suitable for a data dictionary. Return a "
        "JSON object where each key is the column name and the value is the description. "
        "Be specific about what the column likely represents based on the name and samples."
    )
    user_msg = f"Columns: {_json.dumps(safe_cols)}"
    try:
        raw = _chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ], max_tokens=1024)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            result = _json.loads(raw[start:end])
            # Ensure all values are strings
            return {str(k): str(v) for k, v in result.items()}
        return {}
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc


def suggest_improvement_checklist(
    fair_score: dict,
    arrive_issues: list[dict],
    prepare_issues: list[dict],
) -> str:
    """Generate a prioritised improvement checklist as Markdown.

    Sends only the FAIR score breakdown and issue categories — never raw data.
    """
    import json as _json

    score_summary = {
        "total": fair_score.get("fair_score"),
        "findable": {
            "score": fair_score.get("findable", {}).get("score"),
            "max": fair_score.get("findable", {}).get("max_score"),
            "weakness": fair_score.get("findable", {}).get("main_weakness"),
        },
        "accessible": {
            "score": fair_score.get("accessible", {}).get("score"),
            "max": fair_score.get("accessible", {}).get("max_score"),
            "weakness": fair_score.get("accessible", {}).get("main_weakness"),
        },
        "interoperable": {
            "score": fair_score.get("interoperable", {}).get("score"),
            "max": fair_score.get("interoperable", {}).get("max_score"),
            "weakness": fair_score.get("interoperable", {}).get("main_weakness"),
        },
        "reusable": {
            "score": fair_score.get("reusable", {}).get("score"),
            "max": fair_score.get("reusable", {}).get("max_score"),
            "weakness": fair_score.get("reusable", {}).get("main_weakness"),
        },
        "recommendations": fair_score.get("main_recommendations", [])[:5],
    }

    arrive_summary = [
        {"field_id": i.get("id", ""), "severity": i.get("severity", "")}
        for i in arrive_issues[:10]
    ]
    prepare_summary = [
        {"field_id": i.get("id", ""), "severity": i.get("severity", "")}
        for i in prepare_issues[:10]
    ]

    prompt = (
        "You are a research data management expert specialising in FAIR data principles, "
        "ARRIVE 2.0 reporting, and PREPARE study planning. "
        "Generate a prioritised checklist (Markdown format) of concrete improvement actions "
        "based on the FAIR score and compliance gaps provided. "
        "Group by priority: High, Medium, Low. "
        "Note: ARRIVE is a reporting completeness assessment; PREPARE is a study planning "
        "readiness assessment. Neither is regulatory validation."
    )
    user_msg = (
        f"FAIR Score breakdown: {_json.dumps(score_summary)}\n"
        f"ARRIVE gaps ({len(arrive_summary)} shown): {_json.dumps(arrive_summary)}\n"
        f"PREPARE gaps ({len(prepare_summary)} shown): {_json.dumps(prepare_summary)}"
    )
    try:
        return _chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ], max_tokens=1024)
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc
