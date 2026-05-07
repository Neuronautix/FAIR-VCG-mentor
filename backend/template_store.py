"""
Template memory for column-role mappings.

Stage 2 of the column-understanding roadmap. Once a user has confirmed
column roles for a dataset, we persist that mapping keyed by a stable
signature derived from the column-name set.  Subsequent uploads of a
structurally identical dataset can re-apply the saved mapping
automatically, eliminating the need to re-confirm low-confidence columns.

Persistence uses the same SQLite database as the session store; the
table is created lazily on first read/write.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Mapping, Optional

# Fields persisted per column — only the user-confirmable subset.
_TEMPLATE_FIELDS = (
    "label",
    "description",
    "inferred_type",
    "user_type",
    "user_unit",
    "unit_guess",
    "user_label",
    "user_description",
    "uri",
    "allowed_values",
    "required",
)

LOW_CONFIDENCE_THRESHOLD = 0.65


def _init_table(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS column_templates ("
            "  signature TEXT PRIMARY KEY, "
            "  mappings_json TEXT NOT NULL, "
            "  source_filename TEXT, "
            "  updated_at REAL NOT NULL"
            ")"
        )


def _columns_to_template(columns: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for col in columns:
        name = col.get("name")
        if not name:
            continue
        out[name] = {f: col.get(f) for f in _TEMPLATE_FIELDS if f in col}
    return out


def save_template(
    db_path: str,
    signature: str,
    columns: List[Dict[str, Any]],
    source_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist the user-confirmed column mapping for `signature`."""
    _init_table(db_path)
    mapping = _columns_to_template(columns)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO column_templates "
            "(signature, mappings_json, source_filename, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (signature, json.dumps(mapping), source_filename, time.time()),
        )
    return {"signature": signature, "n_columns": len(mapping)}


def load_template(db_path: str, signature: str) -> Optional[Dict[str, Any]]:
    """Return the saved template for `signature`, or None."""
    _init_table(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT mappings_json, source_filename, updated_at "
            "FROM column_templates WHERE signature = ?",
            (signature,),
        ).fetchone()
    if not row:
        return None
    return {
        "signature": signature,
        "mappings": json.loads(row[0]),
        "source_filename": row[1],
        "updated_at": row[2],
    }


def apply_template(
    columns: List[Dict[str, Any]],
    template: Mapping[str, Mapping[str, Any]],
) -> int:
    """In-place merge of `template` into `columns`.

    For each column whose name appears in the template, fields stored in
    the template override the inferred ones, and confidence is bumped to
    1.0 with a ``template:applied`` reason code so downstream consumers
    know the value came from a saved decision rather than inference.

    Returns the number of columns that were updated.
    """
    updated = 0
    for col in columns:
        saved = template.get(col.get("name"))
        if not saved:
            continue
        for field, value in saved.items():
            if value is not None:
                col[field] = value
        col["confidence"] = 1.0
        existing_reasons = list(col.get("reason_codes") or [])
        if "template:applied" not in existing_reasons:
            existing_reasons.append("template:applied")
        col["reason_codes"] = existing_reasons
        updated += 1
    return updated


# ── Low-confidence prompts ───────────────────────────────────────────────────


def low_confidence_columns(
    columns: List[Dict[str, Any]],
    threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Return the subset of columns whose inferred role is below `threshold`,
    formatted for the wizard prompt.  Columns where the user has already
    overridden the type are excluded."""
    out: List[Dict[str, Any]] = []
    for col in columns:
        if col.get("user_type"):
            continue
        if "template:applied" in (col.get("reason_codes") or []):
            continue
        confidence = float(col.get("confidence", 0.0) or 0.0)
        if confidence >= threshold:
            continue
        out.append({
            "name": col["name"],
            "inferred_type": col.get("inferred_type"),
            "confidence": confidence,
            "sample_values": col.get("sample_values", []),
            "reason_codes": col.get("reason_codes", []),
        })
    return out


# ── Correction tracking ─────────────────────────────────────────────────────


def record_corrections(
    session: Dict[str, Any],
    updates: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Update the running correction counter on the session.

    A correction is any user-supplied ``user_type`` that disagrees with the
    inferred type, or any ``user_label`` / ``user_description`` /
    ``user_unit`` that differs from the inferred values.  We track raw
    counts per session so the team can monitor how often the rules need
    human help (Stage 2 acceptance metric).
    """
    metrics = session.setdefault("inference_metrics", {
        "total_updates": 0,
        "type_corrections": 0,
        "label_corrections": 0,
        "unit_corrections": 0,
    })

    by_name = {c["name"]: c for c in session.get("columns", [])}
    for update in updates:
        name = update.get("name")
        existing = by_name.get(name)
        if not existing:
            continue
        metrics["total_updates"] += 1

        new_type = update.get("user_type")
        if new_type and new_type != existing.get("inferred_type"):
            metrics["type_corrections"] += 1

        new_label = update.get("user_label")
        if new_label and new_label != existing.get("label"):
            metrics["label_corrections"] += 1

        new_unit = update.get("user_unit")
        if new_unit is not None and new_unit != existing.get("unit_guess"):
            metrics["unit_corrections"] += 1

    return metrics
