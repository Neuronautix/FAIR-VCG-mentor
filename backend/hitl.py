"""
Human-in-the-loop (HITL) suggestion queue.

LLM features in this app NEVER directly mutate user-visible state.
They emit suggestions that land in the session's HITL queue, where
the user must approve, edit, or reject them.

Stored in `session["hitl"] = {"suggestions": [...]}` so it is persisted
alongside the rest of the session via the existing SQLite layer.

Each suggestion has:
    id           — uuid4
    category     — column_metadata | dataset_metadata | vcg_config |
                   fair_recommendation | issue_fix
    target       — string key the suggestion applies to (e.g. column name)
    source       — "llm:claude-haiku-4-5" | "rule:<engine>"
    confidence   — 0..1 (model self-rated, used for sorting only)
    title        — short headline shown to the user
    rationale    — one-paragraph explanation
    payload      — category-specific data to apply
    status       — pending | approved | rejected | edited | applied | invalid
    created_at   — epoch seconds
    applied_at   — epoch seconds or None
    validation   — {"ok": bool, "errors": [...]} from applier dry-run

Apart from `applied`, suggestions are kept in the queue so the user has
a transparent audit trail.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fair_engine import detect_issues


HITL_CATEGORIES = {
    "column_metadata",
    "dataset_metadata",
    "vcg_config",
    "fair_recommendation",
    "issue_fix",
    "schema_extension",   # propose new vocabulary terms (units, controlled values, etc.)
}

HITL_STATUSES = {"pending", "approved", "rejected", "edited", "applied", "invalid", "stale"}


def ensure_hitl(session: Dict[str, Any]) -> Dict[str, Any]:
    if "hitl" not in session or not isinstance(session.get("hitl"), dict):
        session["hitl"] = {"suggestions": []}
    return session["hitl"]


def list_suggestions(
    session: Dict[str, Any],
    *,
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    hitl = ensure_hitl(session)
    out = hitl["suggestions"]
    if status:
        out = [s for s in out if s.get("status") == status]
    if category:
        out = [s for s in out if s.get("category") == category]
    return list(out)


def get_suggestion(session: Dict[str, Any], suggestion_id: str) -> Optional[Dict[str, Any]]:
    for s in ensure_hitl(session)["suggestions"]:
        if s.get("id") == suggestion_id:
            return s
    return None


def add_suggestion(
    session: Dict[str, Any],
    *,
    category: str,
    target: str,
    source: str,
    title: str,
    rationale: str,
    payload: Dict[str, Any],
    confidence: float = 0.0,
) -> Dict[str, Any]:
    if category not in HITL_CATEGORIES:
        raise ValueError(f"Unknown HITL category: {category}")

    from vocabulary import ensure_vocabulary
    schema_version = int(ensure_vocabulary(session).get("version", 0))

    validation = _dry_run_validate(session, category, target, payload)
    suggestion = {
        "id": str(uuid.uuid4()),
        "category": category,
        "target": target,
        "source": source,
        "confidence": float(confidence),
        "title": title,
        "rationale": rationale,
        "payload": payload,
        "status": "pending" if validation["ok"] else "invalid",
        "validation": validation,
        "schema_version": schema_version,
        "created_at": time.time(),
        "applied_at": None,
    }
    ensure_hitl(session)["suggestions"].append(suggestion)
    return suggestion


def mark_stale_for_version(session: Dict[str, Any], current_version: int) -> int:
    """
    Mark every pending/edited suggestion stamped with an older schema_version
    as 'stale'. Applied/rejected suggestions are left alone — they are history.
    Returns number of suggestions marked.
    """
    marked = 0
    for s in ensure_hitl(session)["suggestions"]:
        sv = int(s.get("schema_version") or 0)
        if sv < current_version and s.get("status") in ("pending", "edited", "invalid"):
            s["status"] = "stale"
            marked += 1
    return marked


def add_suggestions(session: Dict[str, Any], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bulk add; each item is the kwargs dict for add_suggestion."""
    return [add_suggestion(session, **item) for item in items]


def update_status(
    session: Dict[str, Any], suggestion_id: str, new_status: str
) -> Dict[str, Any]:
    if new_status not in HITL_STATUSES:
        raise ValueError(f"Unknown status: {new_status}")
    s = get_suggestion(session, suggestion_id)
    if not s:
        raise KeyError(suggestion_id)
    s["status"] = new_status
    if new_status == "applied":
        s["applied_at"] = time.time()
    return s


def edit_payload(
    session: Dict[str, Any], suggestion_id: str, new_payload: Dict[str, Any]
) -> Dict[str, Any]:
    s = get_suggestion(session, suggestion_id)
    if not s:
        raise KeyError(suggestion_id)
    s["payload"] = new_payload
    s["validation"] = _dry_run_validate(session, s["category"], s["target"], new_payload)
    s["status"] = "edited" if s["validation"]["ok"] else "invalid"
    return s


def approve_and_apply(
    session: Dict[str, Any], suggestion_id: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply a suggestion to the session. Returns (suggestion, apply_result)."""
    s = get_suggestion(session, suggestion_id)
    if not s:
        raise KeyError(suggestion_id)
    if s["status"] in ("applied", "rejected"):
        raise ValueError(f"Suggestion is already {s['status']}.")

    # Re-validate at apply time — the session may have changed since creation.
    s["validation"] = _dry_run_validate(session, s["category"], s["target"], s["payload"])
    if not s["validation"]["ok"]:
        s["status"] = "invalid"
        return s, {"applied": False, "errors": s["validation"]["errors"]}

    result = _apply(session, s["category"], s["target"], s["payload"])
    s["status"] = "applied"
    s["applied_at"] = time.time()
    return s, result


# ── Per-category validation (dry-run, called by add/edit/approve) ───────────

def _dry_run_validate(
    session: Dict[str, Any], category: str, target: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    errors: List[str] = []
    columns = session.get("columns") or []
    col_names = {c["name"] for c in columns}

    if category == "column_metadata":
        if target not in col_names:
            errors.append(f"Column '{target}' does not exist in dataset.")
        allowed_keys = {
            "user_label", "user_description", "user_type", "user_unit",
            "data_type", "allowed_values",
        }
        for k in payload:
            if k not in allowed_keys:
                errors.append(f"Field '{k}' is not editable via HITL.")

    elif category == "dataset_metadata":
        if not isinstance(payload, dict):
            errors.append("dataset_metadata payload must be a dict.")

    elif category == "vcg_config":
        df = session.get("df")
        if df is None:
            errors.append("Dataset is not loaded — cannot validate VCG config.")
        else:
            roles = payload.get("column_roles", {})
            treatment_col = roles.get("treatment_col")
            if treatment_col and treatment_col not in df.columns:
                errors.append(f"treatment_col '{treatment_col}' is not a real column.")
            elif treatment_col:
                vals = {str(v) for v in df[treatment_col].dropna().unique().tolist()}
                cv = roles.get("control_value")
                if cv is not None and str(cv) not in vals:
                    errors.append(
                        f"control_value '{cv}' was not found in '{treatment_col}'."
                    )
                tv = roles.get("treatment_value")
                if tv is not None and str(tv) not in vals:
                    errors.append(
                        f"treatment_value '{tv}' was not found in '{treatment_col}'."
                    )
            for c in roles.get("outcome_cols", []):
                if c not in col_names:
                    errors.append(f"outcome_cols entry '{c}' is not a real column.")
            for c in roles.get("covariate_cols", []):
                if c not in col_names:
                    errors.append(f"covariate_cols entry '{c}' is not a real column.")

    elif category in ("fair_recommendation", "issue_fix"):
        # Free-form text guidance — always ok unless empty.
        if not (payload.get("recommendation") or payload.get("text") or payload.get("metadata_patch")):
            errors.append("Suggestion payload is empty.")

    elif category == "schema_extension":
        valid_keys = {"units", "metadata_keys", "licenses", "study_types"}
        key = payload.get("key")
        values = payload.get("values")
        if not (key in valid_keys or (isinstance(key, str) and key.startswith("controlled_values:"))):
            errors.append(
                "schema_extension payload.key must be one of "
                f"{sorted(valid_keys)} or 'controlled_values:<column>'."
            )
        if not isinstance(values, list) or not values:
            errors.append("schema_extension payload.values must be a non-empty list.")
        if isinstance(key, str) and key.startswith("controlled_values:"):
            col = key.split(":", 1)[1]
            if col not in col_names:
                errors.append(f"controlled_values target column '{col}' does not exist.")

    return {"ok": not errors, "errors": errors}


# ── Per-category appliers ───────────────────────────────────────────────────

def _apply(
    session: Dict[str, Any], category: str, target: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    if category == "column_metadata":
        return _apply_column_metadata(session, target, payload)
    if category == "dataset_metadata":
        return _apply_dataset_metadata(session, payload)
    if category == "vcg_config":
        return _apply_vcg_config(session, payload)
    if category in ("fair_recommendation", "issue_fix"):
        # Optional metadata patch piggybacked on a free-text recommendation.
        patch = payload.get("metadata_patch") or {}
        if patch:
            return _apply_dataset_metadata(session, patch)
        return {"applied": True, "note": "Marked as acknowledged; no state change."}
    if category == "schema_extension":
        return _apply_schema_extension(session, payload)
    return {"applied": False, "errors": [f"Unknown category {category}"]}


def _apply_schema_extension(session: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    from vocabulary import extend_terms
    key = payload["key"]
    values = payload["values"]
    source = payload.get("source") or "hitl_apply"
    result = extend_terms(session, key, values, source=source)
    # Stamp older pending suggestions as stale — they referenced an older schema.
    new_version = int(result["version"])
    marked = mark_stale_for_version(session, new_version)
    return {"applied": True, "added": result["added"], "schema_version": new_version, "marked_stale": marked}


def _apply_column_metadata(
    session: Dict[str, Any], col_name: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    for col in session["columns"]:
        if col["name"] == col_name:
            for k, v in payload.items():
                col[k] = v
            session.pop("fair_score", None)
            session.pop("uri_suggestions", None)
            session["issues"] = detect_issues(
                session["import_info"], session["columns"], session["table_structure"]
            )
            return {"applied": True, "column": col_name, "updated_fields": list(payload.keys())}
    return {"applied": False, "errors": [f"Column '{col_name}' vanished from session."]}


def _apply_dataset_metadata(
    session: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Any]:
    session.setdefault("metadata", {}).update(payload)
    session.pop("fair_score", None)
    return {"applied": True, "updated_fields": list(payload.keys())}


def _apply_vcg_config(session: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if "vcg" not in session:
        from vcg.context_model import DEFAULT_VCG_SESSION
        session["vcg"] = DEFAULT_VCG_SESSION()
    for key in ("column_roles", "vcg_config", "research_context"):
        if key in payload:
            session["vcg"][key].update(payload[key])
    return {"applied": True, "updated": list(payload.keys())}
