"""Per-field completion report + paper/LLM fill helpers for the Template Fill workspace.

Pure functions only — no FastAPI dependencies, no session globals. The
template router calls these to assemble responses for the Template Fill
workspace and to drive bulk-fill from paper extractions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from template_engine import (
    Template,
    _FIELD_LOOKUP_MAP,
    _lookup_paper_value,
    _PAPER_ARRIVE_KEYS,
)

# Reuse the canonical PREPARE prompts table from prepare_engine to avoid
# duplicating the 42 prompt strings in two places. The engine's _PROMPTS
# is keyed by template field_id (matches prepare-v1.yaml ids).
try:
    from prepare_engine import _PROMPTS as PREPARE_PROMPTS  # type: ignore
except Exception:  # pragma: no cover - defensive fallback
    PREPARE_PROMPTS: Dict[str, str] = {}


_MAX_VALUE_PREVIEW = 240


def _truncate(value: Any) -> Optional[str]:
    """Render a metadata value as a preview string, truncated to 240 chars."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        rendered = ", ".join(str(v) for v in value if v not in (None, ""))
    elif isinstance(value, dict):
        rendered = ", ".join(f"{k}={v}" for k, v in value.items())
    else:
        rendered = str(value)
    rendered = rendered.strip()
    if not rendered:
        return None
    if len(rendered) > _MAX_VALUE_PREVIEW:
        return rendered[: _MAX_VALUE_PREVIEW - 1].rstrip() + "…"
    return rendered


def _conformance_index(conformance_report: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index conformance entries by field_id (metadata entries only)."""
    out: Dict[str, Dict[str, Any]] = {}
    for entry in conformance_report or []:
        if entry.get("is_column_field"):
            continue
        fid = entry.get("field_id")
        if fid:
            out[fid] = entry
    return out


def _paper_hint_for_field(
    field_id: str,
    paper_extraction: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Return what the paper extraction would propose for this field, if anything."""
    if not paper_extraction or not isinstance(paper_extraction, dict):
        return None
    arrive = paper_extraction.get("arrive") or {}
    meta = paper_extraction.get("dataset_metadata") or {}
    if not isinstance(arrive, dict):
        arrive = {}
    if not isinstance(meta, dict):
        meta = {}
    try:
        val, _source, _status = _lookup_paper_value(field_id, arrive, meta)
    except Exception:
        return None
    return _truncate(val)


def build_completion_report(
    template: Template,
    metadata: Dict[str, Any],
    columns: List[Dict[str, Any]],
    paper_extraction: Optional[Dict[str, Any]],
    conformance_report: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Enriched per-field completion report.

    Walks ``template.required_metadata`` and produces a structured report
    summarising satisfaction, severity, sectioning (ARRIVE + PREPARE),
    crosswalk auto-satisfaction, current values, and PREPARE planning
    prompts plus paper-extraction hints for missing fields.

    The shape is documented in ``CLAUDE.md`` under the Template Fill
    workspace — frontend reads keys verbatim, so do not rename.
    """
    metadata = metadata or {}
    entries_by_id = _conformance_index(conformance_report or [])

    fields_out: List[Dict[str, Any]] = []
    by_section_acc: Dict[Tuple[str, str], Dict[str, Any]] = {}

    totals = {
        "total": 0,
        "satisfied_direct": 0,
        "satisfied_via_crosswalk": 0,
        "partial": 0,
        "missing": 0,
    }
    by_severity: Dict[str, Dict[str, int]] = {
        "high": {"total": 0, "satisfied": 0, "missing": 0},
        "medium": {"total": 0, "satisfied": 0, "missing": 0},
        "low": {"total": 0, "satisfied": 0, "missing": 0},
    }

    for meta_spec in template.required_metadata:
        fid = meta_spec.id
        entry = entries_by_id.get(fid)
        status = (entry or {}).get("status") or "missing"
        satisfied_by = (entry or {}).get("satisfied_by") or None

        via_crosswalk = bool(
            isinstance(satisfied_by, dict) and satisfied_by.get("via_crosswalk")
        )
        satisfied_by_field: Optional[str] = None
        source: Optional[str] = None
        if status == "satisfied":
            if via_crosswalk:
                source = "crosswalk"
                if isinstance(satisfied_by, dict):
                    satisfied_by_field = satisfied_by.get("metadata") or None
            else:
                source = "direct"

        # Current value comes from the metadata dict; when satisfied via
        # crosswalk, prefer the sibling field's value so the UI can show
        # *what* satisfies this row.
        if status == "satisfied" and via_crosswalk and satisfied_by_field:
            raw_value = metadata.get(satisfied_by_field)
        else:
            raw_value = metadata.get(fid)
        value_preview = _truncate(raw_value)

        prompt: Optional[str] = None
        if status != "satisfied":
            prompt = PREPARE_PROMPTS.get(fid)

        paper_hint: Optional[str] = None
        if status != "satisfied":
            paper_hint = _paper_hint_for_field(fid, paper_extraction)

        field_record = {
            "field_id": fid,
            "label": fid.replace("_", " ").title(),
            "arrive_section": meta_spec.arrive_section,
            "prepare_section": meta_spec.prepare_section,
            "severity": meta_spec.severity,
            "status": status,
            "via_crosswalk": via_crosswalk,
            "satisfied_by_field": satisfied_by_field,
            "value": value_preview,
            "source": source,
            "is_column_field": False,
            "prompt": prompt,
            "paper_hint": paper_hint,
        }
        fields_out.append(field_record)

        # Aggregate totals
        totals["total"] += 1
        if status == "satisfied":
            if via_crosswalk:
                totals["satisfied_via_crosswalk"] += 1
            else:
                totals["satisfied_direct"] += 1
        elif status == "partial":
            totals["partial"] += 1
        else:
            totals["missing"] += 1

        sev_bucket = by_severity.get(meta_spec.severity)
        if sev_bucket is not None:
            sev_bucket["total"] += 1
            if status == "satisfied":
                sev_bucket["satisfied"] += 1
            else:
                sev_bucket["missing"] += 1

        # Aggregate by section — emit one row per (kind, label) pair the
        # field belongs to. A field can appear in both ARRIVE and PREPARE
        # sections when it is part of a crosswalk template.
        for kind, label in (
            ("arrive", meta_spec.arrive_section),
            ("prepare", meta_spec.prepare_section),
        ):
            if not label:
                continue
            key = (kind, label)
            bucket = by_section_acc.get(key)
            if bucket is None:
                bucket = {
                    "label": label,
                    "kind": kind,
                    "total": 0,
                    "satisfied": 0,
                    "fields": [],
                }
                by_section_acc[key] = bucket
            bucket["total"] += 1
            if status == "satisfied":
                bucket["satisfied"] += 1
            bucket["fields"].append(fid)

    # Preserve the order sections are first declared in the template.
    by_section = list(by_section_acc.values())

    return {
        "template_id": template.id,
        "template_name": template.name,
        "totals": totals,
        "by_severity": by_severity,
        "by_section": by_section,
        "fields": fields_out,
    }


def fill_from_paper_extraction(
    template: Template,
    metadata: Dict[str, Any],
    paper_extraction: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Bulk-fill missing template fields from a paper extraction.

    Returns ``(updated_metadata, filled_field_records)``.

    Only fills template ``required_metadata`` fields whose current value
    in ``metadata`` is empty AND for which the paper extraction provides
    a non-empty value. The returned ``filled_field_records`` carry enough
    information for the frontend to display "what was filled" — including
    the source path (e.g. ``arrive.outcome_measures``) and a truncated
    preview of the value.
    """
    updated = dict(metadata or {})
    filled: List[Dict[str, Any]] = []

    if not paper_extraction or not isinstance(paper_extraction, dict):
        return updated, filled

    arrive = paper_extraction.get("arrive") or {}
    meta = paper_extraction.get("dataset_metadata") or {}
    if not isinstance(arrive, dict):
        arrive = {}
    if not isinstance(meta, dict):
        meta = {}

    for req in template.required_metadata:
        fid = req.id
        existing = updated.get(fid)
        if existing not in (None, "", [], {}):
            continue
        try:
            val, source, _status = _lookup_paper_value(fid, arrive, meta)
        except Exception:
            continue
        if val in (None, "", [], {}):
            continue
        updated[fid] = val
        filled.append({
            "field_id": fid,
            "label": fid.replace("_", " ").title(),
            "value": _truncate(val),
            "source": source,
            "arrive_section": req.arrive_section,
            "prepare_section": req.prepare_section,
            "severity": req.severity,
        })

    return updated, filled


def fields_to_llm_prompt(
    template: Template,
    field_ids: List[str],
    metadata: Dict[str, Any],
    columns: List[Dict[str, Any]],
    paper_summary: str,
) -> List[Dict[str, Any]]:
    """Prepare per-field prompt payloads for an LLM call.

    Returns one payload dict per requested field, each containing the
    information the model needs to draft a candidate value:

    - ``field_id``     — template field id
    - ``label``        — human-readable label
    - ``arrive_section`` / ``prepare_section`` — section context
    - ``severity``     — high|medium|low
    - ``prepare_prompt`` — the PREPARE planning prompt for the field (if any)
    - ``context_keys`` — list of related sibling field_ids from the same
      template (e.g. crosswalk peers) whose existing values are likely
      relevant context for drafting this field
    - ``existing_values`` — {context_key: current_value} for any
      ``context_keys`` that already have a value in ``metadata``
    - ``paper_hint`` — the paper-extraction value for this field, if any

    The function is deterministic and side-effect free — the caller
    composes the actual model prompt from these payloads.
    """
    metadata = metadata or {}
    field_ids_set = list(field_ids or [])
    by_id = {req.id: req for req in template.required_metadata}

    payloads: List[Dict[str, Any]] = []
    for fid in field_ids_set:
        req = by_id.get(fid)
        if req is None:
            continue
        context_keys: List[str] = list(req.crosswalk or [])
        existing_values: Dict[str, Any] = {}
        for ck in context_keys:
            ck_val = metadata.get(ck)
            if ck_val not in (None, "", [], {}):
                existing_values[ck] = _truncate(ck_val)

        # paper hint: best-effort lookup using the same mapping the bulk-fill uses
        paper_hint: Optional[str] = None
        lookup = _FIELD_LOOKUP_MAP.get(fid)
        if lookup is not None or fid in _PAPER_ARRIVE_KEYS:
            # We intentionally don't pass the actual extraction here —
            # the caller is responsible for providing paper_summary. The
            # paper_hint slot remains None so this function stays
            # side-effect free and easy to test.
            paper_hint = None

        payloads.append({
            "field_id": fid,
            "label": fid.replace("_", " ").title(),
            "arrive_section": req.arrive_section,
            "prepare_section": req.prepare_section,
            "severity": req.severity,
            "prepare_prompt": PREPARE_PROMPTS.get(fid),
            "context_keys": context_keys,
            "existing_values": existing_values,
            "paper_hint": paper_hint,
        })

    return payloads
