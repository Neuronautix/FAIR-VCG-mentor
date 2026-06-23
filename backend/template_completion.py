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


# Mapping from PREPARE template field_id → extraction["prepare"][key].
# The paper_extractor emits 13 topic-level PREPARE keys but the template has
# 42 sub-items; multiple sub-items map back to the same extracted topic.
# Fields not listed here fall through to _lookup_paper_value (which handles
# ARRIVE-based crosswalks for the items that have one).
_PREPARE_HINT_MAP: Dict[str, str] = {
    # Topic 1: literature_searches
    "prepare_clear_hypothesis": "literature_searches",
    "prepare_systematic_reviews": "literature_searches",
    "prepare_search_strategy": "literature_searches",
    "prepare_species_relevance": "literature_searches",
    "prepare_reproducibility_translatability": "literature_searches",
    # Topic 2: legal_issues
    "prepare_legislation_compliance": "legal_issues",
    "prepare_guidance_documents": "legal_issues",
    # Topic 3: ethical issues — split across lay_summary, harm_benefit_assessment,
    # severity_classification, humane_endpoints
    "prepare_lay_summary": "lay_summary",
    "prepare_ethics_committee_dialogue": "lay_summary",
    "prepare_3rs_3ss": "harm_benefit_assessment",
    "prepare_preregistration_negative_results": "lay_summary",
    "prepare_harm_benefit_assessment": "harm_benefit_assessment",
    "prepare_learning_objectives": "lay_summary",
    "prepare_severity_classification": "severity_classification",
    "prepare_humane_endpoints": "humane_endpoints",
    "prepare_death_endpoint_justification": "humane_endpoints",
    # Topic 6: facility_evaluation
    "prepare_facility_inspection": "facility_evaluation",
    "prepare_staffing_extra_risk": "facility_evaluation",
    # Topic 7: education_training
    "prepare_staff_competence": "education_training",
    # Topic 8: health_risks_waste
    "prepare_risk_assessment": "health_risks_waste",
    "prepare_project_stage_guidance": "health_risks_waste",
    "prepare_containment_disposal": "health_risks_waste",
    # Topic 11: quarantine_health_monitoring
    "prepare_health_status_quarantine": "quarantine_health_monitoring",
    # Topic 12: housing_husbandry
    "prepare_specific_needs": "housing_husbandry",
    "prepare_acclimatisation_housing": "housing_husbandry",
    # Topic 14: humane_killing
    "prepare_killing_legislation": "humane_killing",
    "prepare_killing_methods": "humane_killing",
    "prepare_killer_competence": "humane_killing",
    # Topic 15: necropsy
    "prepare_necropsy_plan": "necropsy",
}


def _prepare_block_value(
    field_id: str,
    paper_extraction: Optional[Dict[str, Any]],
) -> Optional[Any]:
    """Pull a value from paper_extraction['prepare'] for a PREPARE field_id.

    The paper_extractor emits a top-level ``prepare`` block keyed by 13
    topic-level snake_case names (literature_searches, facility_evaluation,
    …). The PREPARE template has 42 sub-items, so multiple template
    field_ids share one extraction key — see ``_PREPARE_HINT_MAP``.
    Returns the extracted value (string) or None.
    """
    if not paper_extraction or not isinstance(paper_extraction, dict):
        return None
    prepare = paper_extraction.get("prepare") or {}
    if not isinstance(prepare, dict):
        return None
    key = _PREPARE_HINT_MAP.get(field_id)
    if not key:
        return None
    entry = prepare.get(key)
    if isinstance(entry, dict):
        val = entry.get("value")
    else:
        val = entry
    if val in (None, "", [], {}):
        return None
    return val



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
        val = None
    # Fallback: PREPARE-only fields aren't in _FIELD_LOOKUP/_PAPER_ARRIVE_KEYS;
    # consult the paper extractor's new top-level "prepare" block.
    if val in (None, "", [], {}):
        val = _prepare_block_value(field_id, paper_extraction)
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
            # PREPARE fields carry their planning prompt from the canonical
            # prompts table; other standards (e.g. EQIPD) carry the Core
            # Requirement text inline on the metadata spec as ``guidance``.
            prompt = PREPARE_PROMPTS.get(fid) or meta_spec.guidance

        paper_hint: Optional[str] = None
        if status != "satisfied":
            paper_hint = _paper_hint_for_field(fid, paper_extraction)

        field_record = {
            "field_id": fid,
            "label": fid.replace("_", " ").title(),
            "arrive_section": meta_spec.arrive_section,
            "prepare_section": meta_spec.prepare_section,
            "eqipd_section": meta_spec.eqipd_section,
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
            ("eqipd", meta_spec.eqipd_section),
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
            val, source = None, None
        if val in (None, "", [], {}):
            # Fallback for PREPARE-only fields via the new prepare block.
            prepare_val = _prepare_block_value(fid, paper_extraction)
            if prepare_val in (None, "", [], {}):
                continue
            val = prepare_val
            source = f"prepare.{_PREPARE_HINT_MAP.get(fid, '?')}"
        updated[fid] = val
        filled.append({
            "field_id": fid,
            "label": fid.replace("_", " ").title(),
            "value": _truncate(val),
            "source": source,
            "arrive_section": req.arrive_section,
            "prepare_section": req.prepare_section,
            "eqipd_section": req.eqipd_section,
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
            "eqipd_section": req.eqipd_section,
            "severity": req.severity,
            "prepare_prompt": PREPARE_PROMPTS.get(fid),
            # Inline guidance (e.g. an EQIPD Core Requirement) gives the model
            # the field's intent when there is no PREPARE planning prompt.
            "guidance": req.guidance,
            "context_keys": context_keys,
            "existing_values": existing_values,
            "paper_hint": paper_hint,
        })

    return payloads
