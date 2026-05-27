"""
prepare_engine.py — PREPARE planning export generator.

Produces two Markdown documents from session data, complementing the ARRIVE
reporting export (arrive_engine.py):

  1. prepare_study_plan.md  — pre-study plan organised by the 15 PREPARE topics
  2. prepare_checklist.md   — compact table of all 38 PREPARE items with status

Both are bundled into prepare_study_plan.zip by generate_prepare_zip().

The PREPARE guidelines (Smith et al. 2018, Norecopa) cover planning *before*
the study; ARRIVE 2.0 covers reporting *after* the study. The recommended
workflow is PREPARE -> CARE -> SHARE -> FLAG.
"""
from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, List, Optional

from template_engine import get_template


# ── Helpers ───────────────────────────────────────────────────────────────────

def _v(d: dict, *keys: str, fallback: str = "") -> str:
    """Walk nested keys and return a string, falling back to `fallback`."""
    for key in keys:
        d = d.get(key) if isinstance(d, dict) else None
        if d is None:
            return fallback
    val = d
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x) or fallback
    return str(val).strip() if val else fallback


def _truncate(text: str, limit: int = 80) -> str:
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


# Concise planning prompts per PREPARE field id (drawn from PREPARE wording).
_PROMPTS: Dict[str, str] = {
    # Topic 1
    "prepare_clear_hypothesis": "State a clear, testable hypothesis or research question with the primary outcome it predicts.",
    "prepare_systematic_reviews": "Document any systematic reviews consulted (and gaps identified) to justify the new study.",
    "prepare_search_strategy": "Record the literature databases queried, search terms, dates, and inclusion criteria used.",
    "prepare_species_relevance": "Justify why the chosen species and model are the most appropriate for this question.",
    "prepare_reproducibility_translatability": "Describe how reproducibility and translatability to humans (or target species) will be assessed.",
    # Topic 2
    "prepare_legislation_compliance": "Confirm the project complies with all relevant national/EU legislation; list licence and protocol numbers.",
    "prepare_guidance_documents": "List the institutional or national guidance documents that govern the work.",
    # Topic 3
    "prepare_lay_summary": "Provide a non-technical lay summary suitable for ethics committees and the public.",
    "prepare_ethics_committee_dialogue": "Note the planned dialogue with the ethics or animal welfare body (timing, key questions).",
    "prepare_3rs_3ss": "Document how the 3Rs (Replacement, Reduction, Refinement) and 3Ss (Good Science, Sense, Sensibilities) are applied.",
    "prepare_preregistration_negative_results": "State whether the study will be pre-registered and how negative results will be reported.",
    "prepare_harm_benefit_assessment": "Summarise the harm-benefit assessment: anticipated suffering vs anticipated scientific or societal benefit.",
    "prepare_learning_objectives": "If the study has training or educational objectives, list them explicitly.",
    "prepare_severity_classification": "Assign the expected severity classification (non-recovery / mild / moderate / severe) per procedure.",
    "prepare_humane_endpoints": "Define humane endpoints: clinical signs, scoring, and the action to be taken at each threshold.",
    "prepare_death_endpoint_justification": "If death is an endpoint, justify why no earlier humane endpoint is possible.",
    # Topic 4
    "prepare_pilot_power_significance": "Document any pilot data, a-priori power calculation, chosen significance level, and analysis plan.",
    "prepare_experimental_unit": "Specify the experimental unit (animal, cage, litter) and the total n per group.",
    "prepare_randomisation_blinding_criteria": "Describe the randomisation method, blinding strategy, and inclusion/exclusion criteria.",
    # Topic 5
    "prepare_staff_meetings": "Plan kick-off and review meetings between scientists, facility staff, vets, and statisticians.",
    "prepare_project_timescale": "Record planned start and end dates and key milestones.",
    "prepare_cost_disclosure": "List the funding source(s), grant code(s), and per-animal cost where relevant.",
    "prepare_labour_division_plan": "Document who is responsible for each procedure and data collection step.",
    # Topic 6
    "prepare_facility_inspection": "Plan a facility inspection covering caging, environment, equipment, and SOP coverage.",
    "prepare_staffing_extra_risk": "Identify staffing implications and any extra biosafety / OHS risks introduced by the study.",
    # Topic 7
    "prepare_staff_competence": "Confirm all personnel have demonstrated competence for the procedures they will perform.",
    # Topic 8
    "prepare_risk_assessment": "Complete a written risk assessment covering chemicals, biological agents, and emergency procedures.",
    "prepare_project_stage_guidance": "Note any guidance specific to particular project stages (e.g. surgery, in-life, necropsy).",
    "prepare_containment_disposal": "Describe containment level, waste streams, and decontamination procedures.",
    # Topic 9
    "prepare_test_substance_info": "Record the test substance identity, batch, purity, vehicle, route, volume, frequency, and storage.",
    "prepare_procedure_feasibility": "Confirm procedures have been piloted or rehearsed to confirm feasibility.",
    # Topic 10
    "prepare_animal_characteristics": "Document species, strain, sex, age, weight range, supplier, and health status of the animals.",
    "prepare_avoid_surplus": "Plan breeding and ordering to avoid surplus animals (sex balance, sharing tissues).",
    # Topic 11
    "prepare_health_status_quarantine": "Specify quarantine duration, health screening panel, and ongoing monitoring frequency.",
    # Topic 12
    "prepare_specific_needs": "Document any species-specific housing, enrichment, social grouping, or dietary needs.",
    "prepare_acclimatisation_housing": "Specify the acclimatisation period, group size, cage density, light cycle, temperature, and humidity.",
    # Topic 13
    "prepare_refined_capture_marking": "Describe refined methods for capture, handling, identification, and marking.",
    "prepare_refined_substance_anaesthesia": "Document the anaesthesia, analgesia, surgical refinement, and recovery plan.",
    # Topic 14
    "prepare_killing_legislation": "Confirm killing methods comply with current legislation (e.g. Annex IV of EU 2010/63).",
    "prepare_killing_methods": "List the primary and confirmatory methods of killing, with operator and equipment.",
    "prepare_killer_competence": "Confirm the personnel performing humane killing have documented competence.",
    # Topic 15
    "prepare_necropsy_plan": "Plan necropsy: who performs it, organs collected, fixation, downstream analyses, and storage.",
}


def _build_entry_index(template_validation: List[Dict]) -> Dict[str, Dict]:
    """Index template_validation entries by field_id (metadata fields only)."""
    out: Dict[str, Dict] = {}
    for entry in template_validation or []:
        if entry.get("is_column_field"):
            continue
        fid = entry.get("field_id")
        if fid:
            out[fid] = entry
    return out


def _resolve_value(
    field_id: str,
    crosswalk: List[str],
    metadata: Dict,
    entry: Optional[Dict],
) -> str:
    """Return a displayable value for a field, via direct metadata or crosswalk."""
    direct = metadata.get(field_id)
    if direct not in (None, "", [], {}):
        if isinstance(direct, list):
            return ", ".join(str(x) for x in direct if x)
        return str(direct).strip()
    # Try crosswalk fallbacks (in declared order)
    for other in crosswalk or []:
        v = metadata.get(other)
        if v not in (None, "", [], {}):
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v if x)
            return f"{str(v).strip()} (from ARRIVE: {other})"
    # Crosswalk satisfaction recorded in template_validation entry
    if entry and entry.get("status") == "satisfied":
        sat = entry.get("satisfied_by") or {}
        if sat.get("via_crosswalk"):
            other = sat.get("metadata")
            if other:
                v = metadata.get(other)
                if v not in (None, "", [], {}):
                    if isinstance(v, list):
                        v = ", ".join(str(x) for x in v if x)
                    return f"{str(v).strip()} (from ARRIVE: {other})"
    return ""


def _status_for(
    field_id: str,
    entry: Optional[Dict],
    metadata: Dict,
    crosswalk: List[str],
    has_prepare_template: bool,
) -> tuple[str, bool, Optional[str]]:
    """
    Return (status_label, via_crosswalk, via_field_id).
    Falls back to direct metadata lookup when no PREPARE template is assigned.
    """
    if entry is not None:
        status = entry.get("status", "missing")
        sat = entry.get("satisfied_by") or {}
        via_crosswalk = bool(sat.get("via_crosswalk"))
        via_field = sat.get("metadata") if via_crosswalk else None
        if status == "satisfied":
            return ("✅ Planned", via_crosswalk, via_field)
        if status == "partial":
            return ("⚠️ Partial", False, None)
        return ("❌ Missing", False, None)
    # No entry — fall back to raw metadata
    if metadata.get(field_id) not in (None, "", [], {}):
        return ("✅ Planned", False, None)
    for other in crosswalk or []:
        if metadata.get(other) not in (None, "", [], {}):
            return ("✅ Planned", True, other)
    return ("❌ Missing", False, None)


def _has_prepare_template(session_template_id: Optional[str]) -> bool:
    if not session_template_id:
        return False
    tid = str(session_template_id).lower()
    return "prepare" in tid


# ── Study Plan generator ──────────────────────────────────────────────────────

def generate_prepare_study_plan(
    metadata: Dict,
    columns: List[Dict],
    template_validation: List[Dict],
    session_template_id: Optional[str],
) -> bytes:
    """Pre-filled PREPARE planning document grouped by the 15 topics."""
    tpl = get_template("prepare-v1")
    title = _v(metadata, "title", fallback="[Study title]")
    creator = _v(metadata, "creator", fallback="")
    institution = _v(metadata, "institution", fallback="")
    date_created = _v(metadata, "date_created", fallback="")

    entries = _build_entry_index(template_validation)
    has_prepare = _has_prepare_template(session_template_id)

    lines: List[str] = [
        "# PREPARE Study Plan",
        "",
        "> Generated from FAIR-VCG Mentor. PREPARE (Smith et al. 2018, Norecopa) is a "
        "pre-study planning checklist that complements ARRIVE 2.0 reporting.",
        "> Recommended workflow: **PREPARE → CARE → SHARE → FLAG**.",
        "",
        f"**Study:** {title}  ",
        f"**Lead:** {creator}  ",
        f"**Institution:** {institution}  ",
        f"**Date drafted:** {date_created}  ",
        "",
        "---",
        "",
    ]

    if tpl is None:
        lines.append("> _PREPARE template (prepare-v1) is not loaded; nothing to render._")
        return "\n".join(lines).encode("utf-8")

    # Group required_metadata by prepare_section, preserve declaration order.
    grouped: Dict[str, List[Any]] = {}
    section_order: List[str] = []
    for meta in tpl.required_metadata:
        sec = meta.prepare_section or "Other"
        if sec not in grouped:
            grouped[sec] = []
            section_order.append(sec)
        grouped[sec].append(meta)

    for sec in section_order:
        lines.append(f"## {sec}")
        lines.append("")
        for meta in grouped[sec]:
            fid = meta.id
            entry = entries.get(fid)
            value = _resolve_value(fid, list(meta.crosswalk or []), metadata, entry)
            prompt = _PROMPTS.get(fid, "")
            pretty = fid.replace("prepare_", "").replace("_", " ").capitalize()
            lines.append(f"### {pretty}")
            lines.append("")
            if prompt:
                lines.append(f"_({prompt})_")
                lines.append("")
            if value:
                lines.append(value)
            else:
                lines.append("_(not yet filled)_")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines += [
        "## Sign Off",
        "",
        "| Role | Name | Declaration |",
        "|---|---|---|",
        f"| Primary responsible | {creator} | I confirm this PREPARE plan reflects the study as designed. |",
        "| Named Veterinary Surgeon | | I have reviewed humane endpoints and welfare aspects. |",
        "| Facility manager | | I confirm the facility can accommodate the planned work. |",
        "",
        "---",
        "",
        "_PREPARE: https://norecopa.no/PREPARE — generated by FAIR-VCG Mentor._",
        "",
    ]

    return "\n".join(lines).encode("utf-8")


# ── Checklist generator ──────────────────────────────────────────────────────

def generate_prepare_checklist(
    metadata: Dict,
    columns: List[Dict],
    template_validation: List[Dict],
    session_template_id: Optional[str],
) -> bytes:
    """Compact 38-row PREPARE status table."""
    tpl = get_template("prepare-v1")
    entries = _build_entry_index(template_validation)
    has_prepare = _has_prepare_template(session_template_id)
    title = _v(metadata, "title", fallback="[Study title]")
    creator = _v(metadata, "creator", fallback="")
    date_created = _v(metadata, "date_created", fallback="")

    lines: List[str] = [
        "# PREPARE Planning Checklist",
        "",
        "> Generated by [FAIR-VCG Mentor](https://github.com/dhuzard/FAIR-csv-mentor). "
        "PREPARE (Smith et al. 2018) is a pre-study planning checklist (15 topics, 38 items) "
        "complementary to ARRIVE 2.0 reporting.",
        "",
        f"**Study:** {title}  ",
        f"**Lead:** {creator}  ",
        f"**Date:** {date_created}  ",
        "",
    ]

    if tpl is None:
        lines.append("> _PREPARE template (prepare-v1) is not loaded; nothing to render._")
        return "\n".join(lines).encode("utf-8")

    # Compute summary counts
    statuses: List[tuple[Any, str, bool, Optional[str]]] = []
    for meta in tpl.required_metadata:
        entry = entries.get(meta.id)
        status_label, via_crosswalk, via_field = _status_for(
            meta.id, entry, metadata, list(meta.crosswalk or []), has_prepare
        )
        statuses.append((meta, status_label, via_crosswalk, via_field))

    n_planned = sum(1 for _, s, _, _ in statuses if s.startswith("✅"))
    n_partial = sum(1 for _, s, _, _ in statuses if s.startswith("⚠️"))
    n_missing = sum(1 for _, s, _, _ in statuses if s.startswith("❌"))

    lines += [
        f"**Summary:** ✅ {n_planned} planned · ⚠️ {n_partial} partial · ❌ {n_missing} missing  ",
        "",
        "---",
        "",
        "| PREPARE topic | Item (field_id) | Status | Value |",
        "|---|---|---|---|",
    ]

    for meta, status_label, via_crosswalk, via_field in statuses:
        topic = _md_escape(meta.prepare_section or "")
        fid = meta.id
        status_cell = status_label
        if status_label.startswith("✅") and via_crosswalk and via_field:
            status_cell = f"{status_label} (via ARRIVE: {via_field})"
        value = _resolve_value(fid, list(meta.crosswalk or []), metadata, entries.get(fid))
        value_cell = _md_escape(_truncate(value, 80)) if value else ""
        lines.append(f"| {topic} | `{fid}` | {status_cell} | {value_cell} |")

    # Action items section
    lines += [
        "",
        "---",
        "",
        "## Action items",
        "",
        "_Items still missing or partial — address before the study starts:_",
        "",
    ]
    any_action = False
    for meta, status_label, _, _ in statuses:
        if status_label.startswith("✅"):
            continue
        any_action = True
        prompt = _PROMPTS.get(meta.id, "")
        lines.append(f"- **`{meta.id}`** ({_md_escape(meta.prepare_section or '')}) — {status_label}")
        if prompt:
            lines.append(f"  _{prompt}_")
    if not any_action:
        lines.append("_All 38 PREPARE items are planned. Ready to proceed._")
    lines += [
        "",
        "---",
        "",
        "_PREPARE: https://norecopa.no/PREPARE_",
        "",
    ]

    return "\n".join(lines).encode("utf-8")


# ── Zip bundler ──────────────────────────────────────────────────────────────

def generate_prepare_zip(
    metadata: Dict,
    columns: List,
    template_validation: List,
    session_template_id: Optional[str],
) -> bytes:
    """Zip containing prepare_study_plan.md and prepare_checklist.md."""
    metadata = metadata or {}
    columns = columns or []
    template_validation = template_validation or []
    study_plan = generate_prepare_study_plan(
        metadata, columns, template_validation, session_template_id
    )
    checklist = generate_prepare_checklist(
        metadata, columns, template_validation, session_template_id
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("prepare_study_plan.md", study_plan)
        zf.writestr("prepare_checklist.md", checklist)
    buf.seek(0)
    return buf.read()
