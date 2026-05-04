"""
arrive_engine.py — ARRIVE 2.0 export generator.

Produces two Markdown documents from session data:
  1. arrive_study_plan.md  — pre-study plan template, pre-filled from session
  2. arrive_checklist.md   — author checklist table with auto-detected status

Both are bundled into arrive_guidelines.zip by generate_arrive_zip().
"""
from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, List


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


def _col_values(columns: List[Dict], inferred_type: str) -> str:
    """Return comma-joined column names matching an inferred_type."""
    return ", ".join(
        c.get("label") or c.get("name", "")
        for c in columns
        if c.get("inferred_type") == inferred_type
    )


def _sex_values(columns: List[Dict]) -> str:
    for c in columns:
        if c.get("name", "").lower() in ("sex", "gender"):
            vals = c.get("allowed_values") or c.get("sample_values") or []
            if vals:
                return ", ".join(str(v) for v in vals[:5])
    return ""


def _strain_values(columns: List[Dict]) -> str:
    for c in columns:
        if any(kw in c.get("name", "").lower() for kw in ("strain", "species", "genotype", "line")):
            vals = c.get("sample_values") or []
            unique = list(dict.fromkeys(str(v) for v in vals if v))[:5]
            return ", ".join(unique)
    return ""


def _detect_preclinical(columns: List[Dict]) -> bool:
    SIGNALS = {
        "animal_id", "animal", "mouse", "rat", "mice", "rats", "rabbit", "pig",
        "strain", "cage", "litter", "dose", "dosing", "treatment", "group",
        "body_weight", "bw", "organ_weight",
    }
    return bool({c.get("name", "").lower() for c in columns} & SIGNALS)


# ── Checklist status detection ────────────────────────────────────────────────

def _checklist_status(
    item_id: int,
    columns: List[Dict],
    metadata: Dict,
    import_info: Dict,
    table_structure: Dict,
    issues: List[Dict],
    vcg_results: Dict,
) -> str:
    """
    Returns one of: ✅ Reported | ⚠️ Partial | ❌ Missing
    based on heuristics applied to session data.
    """
    col_names = {c.get("name", "").lower() for c in columns}
    issue_ids = {i.get("id", "") for i in issues}
    measurements = [c for c in columns if c.get("inferred_type") == "measurement"]
    has_meta = lambda k: bool(metadata.get(k))

    if item_id == 1:  # Study design
        has_groups = any(kw in col_names for kw in ("group", "treatment", "dose", "cohort"))
        has_control = any(kw in col_names for kw in ("control", "vehicle", "placebo", "sham"))
        if has_groups and has_control:
            return "✅ Reported"
        if has_groups:
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 2:  # Sample size
        n_rows = import_info.get("n_rows", 0)
        has_justif = has_meta("protocol_reference")
        if n_rows >= 6 and has_justif:
            return "✅ Reported"
        if n_rows >= 3:
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 3:  # Inclusion / exclusion criteria
        has_excl = any(kw in col_names for kw in ("exclude", "excluded", "outlier", "dropout"))
        if has_excl:
            return "✅ Reported"
        if "arrive_missing_exclusion" not in issue_ids:
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 4:  # Randomisation
        has_rand = any(kw in col_names for kw in ("random", "randomis", "randomiz", "allocation"))
        if has_rand:
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 5:  # Blinding
        has_blind = any(kw in col_names for kw in ("blind", "blinded", "masked"))
        if has_blind:
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 6:  # Outcome measures
        if measurements:
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 7:  # Statistical methods
        has_stats = bool(vcg_results) or has_meta("protocol_reference")
        if has_stats:
            return "✅ Reported"
        return "⚠️ Partial"

    if item_id == 8:  # Experimental animals
        has_sex = "sex" in col_names or "gender" in col_names
        has_strain = any(kw in col_names for kw in ("strain", "species", "genotype"))
        if has_sex and has_strain:
            return "✅ Reported"
        if has_sex or has_strain:
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 9:  # Experimental procedures
        if has_meta("protocol_reference"):
            return "✅ Reported"
        return "⚠️ Partial"

    if item_id == 10:  # Results (summary stats)
        outcomes = vcg_results.get("reliability_breakdown", {}).get("per_endpoint", {})
        if outcomes:
            return "✅ Reported"
        if measurements:
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 11:  # Abstract
        if has_meta("description"):
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 12:  # Background
        if has_meta("description"):
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 13:  # Objectives
        if has_meta("description"):
            return "⚠️ Partial"
        return "❌ Missing"

    if item_id == 14:  # Ethical statement
        has_ethics = any(kw in col_names for kw in ("ethic", "iacuc", "approval", "license"))
        if has_ethics:
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 15:  # Housing and husbandry
        has_housing = any(kw in col_names for kw in ("cage", "housing", "light", "temperature", "humidity"))
        if has_housing:
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 16:  # Animal care and monitoring
        has_welfare = any(kw in col_names for kw in ("adverse", "humane", "welfare", "endpoint", "clinical"))
        if has_welfare:
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 17:  # Interpretation
        return "⚠️ Partial"

    if item_id == 18:  # Generalisability
        return "❌ Missing"

    if item_id == 19:  # Protocol registration
        if has_meta("protocol_reference"):
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 20:  # Data access
        if has_meta("base_uri") or has_meta("access_conditions"):
            return "✅ Reported"
        return "❌ Missing"

    if item_id == 21:  # Declaration of interests
        if has_meta("creator"):
            return "⚠️ Partial"
        return "❌ Missing"

    return "⚠️ Partial"


# ── Study Plan generator ──────────────────────────────────────────────────────

def generate_arrive_study_plan(
    import_info: Dict,
    columns: List[Dict],
    metadata: Dict,
    table_structure: Dict,
    vcg_results: Dict,
) -> bytes:
    """
    Returns bytes for arrive_study_plan.md, pre-filled with session data
    following the ARRIVE Study Plan template structure.
    """
    title = _v(metadata, "title", fallback="[Dataset title]")
    creator = _v(metadata, "creator", fallback="")
    protocol_ref = _v(metadata, "protocol_reference", fallback="")
    institution = _v(metadata, "institution", fallback="")
    date_created = _v(metadata, "date_created", fallback="")
    keywords = _v(metadata, "keywords", fallback="")
    description = _v(metadata, "description", fallback="")
    license_ = _v(metadata, "license", fallback="")

    n_rows = import_info.get("n_rows", 0)
    n_cols = import_info.get("n_columns", 0)

    species = _strain_values(columns)
    sex = _sex_values(columns)
    measurements = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "measurement"]
    covariates = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "biological_descriptor"]
    identifiers = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "identifier"]
    conditions = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "experimental_condition"]
    time_vars = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "time_variable"]

    vcg_method = vcg_results.get("method_used", "") if vcg_results else ""
    n_real = vcg_results.get("n_subjects_real", "") if vcg_results else ""
    n_vcg = vcg_results.get("n_subjects_vcg", "") if vcg_results else ""
    reliability = vcg_results.get("reliability_score", "") if vcg_results else ""

    table_shape = table_structure.get("table_shape", "").replace("_", " ")
    primary_entity = table_structure.get("primary_entity") or table_structure.get("row_represents") or ""

    vcg_section = ""
    if vcg_results:
        vcg_section = f"""
## Virtual Control Group (VCG)

| Field | Value |
|---|---|
| VCG method | {vcg_method} |
| Real control n | {n_real} |
| VCG synthetic n | {n_vcg} |
| Reliability score | {reliability} |

"""
        breakdown = vcg_results.get("reliability_breakdown", {}).get("per_endpoint", {})
        if breakdown:
            vcg_section += "### Per-endpoint statistics\n\n"
            vcg_section += "| Endpoint | Mean (real) | SD (real) | Mean (VCG) | SD (VCG) | Cohen's d | KS p-value | Verdict |\n"
            vcg_section += "|---|---|---|---|---|---|---|---|\n"
            for col, ep in breakdown.items():
                vcg_section += (
                    f"| {col} "
                    f"| {ep.get('mean_real', ''):.4g} "
                    f"| {ep.get('std_real', ''):.4g} "
                    f"| {ep.get('mean_vcg', ''):.4g} "
                    f"| {ep.get('std_vcg', ''):.4g} "
                    f"| {ep.get('cohens_d', '') if ep.get('cohens_d') is not None else '—'} "
                    f"| {ep.get('ks_pvalue', '') if ep.get('ks_pvalue') is not None else '—'} "
                    f"| {ep.get('interpretation', '')} |\n"
                )
            vcg_section += "\n"

    lines = [
        "# ARRIVE Study Plan",
        "",
        "> Generated from FAIR-VCG Mentor. Fill in or confirm every field before submission.",
        "> Fields detected automatically from the uploaded dataset are pre-filled.",
        "",
        "---",
        "",
        "## Study Details",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Study title | {title} |",
        f"| Grant code | |",
        f"| Start date | {date_created} |",
        f"| End date | |",
        f"| Project licence / permit number | |",
        f"| Project lead | {creator} |",
        f"| Protocol numbers | {protocol_ref} |",
        f"| Expected severity | |",
        f"| Institution | {institution} |",
        f"| Keywords | {keywords} |",
        "",
        "---",
        "",
        "## Experimental Animals",
        "",
        f"| Species/Strain | Sex | Age | Weight | Source | Number |",
        f"|---|---|---|---|---|---|",
        f"| {species} | {sex} | | | | {n_rows} |",
        "",
        "> **Detected covariates (biological descriptors):** "
        + (", ".join(covariates) if covariates else "_none detected_"),
        "> **Detected identifiers:** " + (", ".join(identifiers) if identifiers else "_none detected_"),
        "",
        "---",
        "",
        "## Experimental Procedures",
        "",
        "| Field | Details |",
        "|---|---|",
        f"| Procedures | {description[:200] if description else ''} |",
        f"| Surgical procedures | |",
        f"| Anaesthesia | |",
        f"| Analgesia | |",
        f"| Locations | |",
        f"| Acclimatisation period | |",
        f"| Protocol reference | {protocol_ref} |",
        "",
        "> **Experimental conditions detected:** "
        + (", ".join(conditions) if conditions else "_none detected_"),
        "> **Time variables detected:** "
        + (", ".join(time_vars) if time_vars else "_none detected_"),
        "",
        "---",
        "",
        "## Animal Care and Monitoring",
        "",
        "| Field | Details |",
        "|---|---|",
        "| Adverse events | |",
        "| Humane endpoints | |",
        "| Welfare monitoring | |",
        "| Clinical assessment form attached | |",
        "| Changes in housing and husbandry | |",
        "| Restrictions in veterinary care | |",
        "",
        "---",
        "",
        "## Risks",
        "",
        "| Field | Details |",
        "|---|---|",
        "| Emergency procedures | |",
        "| Potential risk to personnel | |",
        "",
        "---",
        "",
        "## Study Design and Sample Size",
        "",
        "| Field | Details |",
        "|---|---|",
        f"| Experimental groups | {', '.join(conditions) if conditions else ''} |",
        f"| Experimental unit | {primary_entity or 'individual animal'} |",
        f"| Table shape | {table_shape} |",
        f"| Total rows (dataset) | {n_rows} |",
        f"| Total columns | {n_cols} |",
        f"| Sample size per group | |",
        "| Justification for sample size | |",
        "| EDA diagram | |",
        "",
        "---",
        "",
        "## Inclusion and Exclusion Criteria",
        "",
        "| Field | Details |",
        "|---|---|",
        "| Inclusion criteria | |",
        "| Exclusion criteria | |",
        "| Expected attrition | |",
        "",
        "---",
        "",
        "## Randomisation and Blinding",
        "",
        "| Field | Details |",
        "|---|---|",
        "| Method of allocation to group | |",
        "| Strategy to minimise confounders | |",
        "| Blinding strategy | |",
        "",
        "---",
        "",
        "## Outcome Measures and Statistical Methods",
        "",
        f"| Field | Details |",
        f"|---|---|",
        f"| Outcome measures | {', '.join(measurements) if measurements else ''} |",
        f"| Primary outcome measure | {measurements[0] if measurements else ''} |",
        f"| License | {license_} |",
        "| Analysis plans | |",
        "",
    ]

    lines.append(vcg_section)

    lines += [
        "---",
        "",
        "## Sign Off",
        "",
        "| Role | Name | Declaration |",
        "|---|---|---|",
        f"| Primary responsible | {creator} | I confirm I am aware of my responsibilities as the primary responsible. |",
        "| Project lead | | I confirm I am aware of my responsibilities as a project lead/licence holder and this work is in line with the project. |",
        "",
        "---",
        "",
        "_This document was generated by [FAIR-VCG Mentor](https://github.com/dhuzard/FAIR-csv-mentor). "
        "Please review and complete all fields before submission._",
    ]

    return "\n".join(lines).encode("utf-8")


# ── Author Checklist generator ────────────────────────────────────────────────

# Full ARRIVE 2.0 item catalogue (id, category, short_name, recommendation)
_ARRIVE_ITEMS = [
    # ── Essential 10 ──────────────────────────────────────────────────────────
    (1, "Essential 10", "Study design",
     "Provide brief details of study design including the groups being compared "
     "(including controls) and the experimental unit (e.g. a single animal, litter, or cage)."),
    (2, "Essential 10", "Sample size",
     "Specify the exact number of experimental units allocated to each group and the total number "
     "in each experiment. Explain how the sample size was decided, and provide details of any "
     "a priori sample size calculation."),
    (3, "Essential 10", "Inclusion and exclusion criteria",
     "Describe any criteria used for including and excluding animals (or experimental units) "
     "during the experiment, and data points during the analysis. Report any exclusions and explain why. "
     "Report the exact value of n in each group for each analysis."),
    (4, "Essential 10", "Randomisation",
     "State whether randomisation was used to allocate experimental units to groups. "
     "If done, provide the method used to generate the randomisation sequence. "
     "Describe the strategy used to minimise potential confounders."),
    (5, "Essential 10", "Blinding",
     "Describe who was aware of the group allocation at the different stages of the experiment "
     "(allocation, conduct, outcome assessment, and data analysis)."),
    (6, "Essential 10", "Outcome measures",
     "Clearly define all outcome measures assessed. For hypothesis-testing studies, specify the "
     "primary outcome measure used to determine the sample size."),
    (7, "Essential 10", "Statistical methods",
     "Provide details of the statistical methods used for each analysis, including software used. "
     "Describe any methods used to assess whether the data met the assumptions of the statistical "
     "approach, and what was done if the assumptions were not met."),
    (8, "Essential 10", "Experimental animals",
     "Provide species-appropriate details of the animals used, including species, strain and substrain, "
     "sex, age or developmental stage, and if relevant, weight. Provide further relevant information "
     "on provenance, health/immune status, genetic modification status, and any previous procedures."),
    (9, "Essential 10", "Experimental procedures",
     "For each experimental group, including controls, describe the procedures in enough detail to "
     "allow others to replicate them, including what was done, how and what was used, when and how "
     "often, where, and why."),
    (10, "Essential 10", "Results",
     "For each experiment conducted, report summary/descriptive statistics for each experimental group "
     "with a measure of variability where applicable (e.g. mean and SD, or median and range). "
     "If applicable, report the effect size with a confidence interval."),
    # ── Recommended Set ───────────────────────────────────────────────────────
    (11, "Recommended", "Abstract",
     "Provide an accurate summary of the research objectives, animal species, strain and sex, "
     "key methods, principal findings, and study conclusions."),
    (12, "Recommended", "Background",
     "Include sufficient scientific background to understand the rationale and context for the study, "
     "and explain the experimental approach. Explain how the animal species and model address the "
     "scientific objectives and, where appropriate, the relevance to human biology."),
    (13, "Recommended", "Objectives",
     "Clearly describe the research question, research objectives and, where appropriate, specific "
     "hypotheses being tested."),
    (14, "Recommended", "Ethical statement",
     "Provide the name of the ethical review committee or equivalent that has approved the use of "
     "animals in this study, and any relevant licence or protocol numbers. If ethical approval was "
     "not sought or granted, provide a justification."),
    (15, "Recommended", "Housing and husbandry",
     "Provide details of housing and husbandry conditions, including any environmental enrichment."),
    (16, "Recommended", "Animal care and monitoring",
     "Describe any interventions to reduce pain, suffering and distress. Report any expected or "
     "unexpected adverse events. Describe the humane endpoints established for the study, the signs "
     "that were monitored and the frequency of monitoring."),
    (17, "Recommended", "Interpretation / scientific implications",
     "Interpret the results, taking into account the study objectives and hypotheses, current theory "
     "and other relevant studies. Comment on the study limitations including potential sources of "
     "bias, limitations of the animal model, and imprecision associated with the results."),
    (18, "Recommended", "Generalisability / translation",
     "Comment on whether, and how, the findings of this study are likely to generalise to other "
     "species or experimental conditions, including any relevance to human biology where appropriate."),
    (19, "Recommended", "Protocol registration",
     "Provide a statement indicating whether a protocol (including the research question, key design "
     "features, and analysis plan) was prepared before the study, and if and where this protocol "
     "was registered."),
    (20, "Recommended", "Data access",
     "Provide a statement describing if and where study data are available."),
    (21, "Recommended", "Declaration of interests",
     "Declare any potential conflicts of interest, including financial and non-financial. "
     "List all funding sources and the role of the funder(s) in the design, analysis and reporting."),
]


def generate_arrive_checklist(
    import_info: Dict,
    columns: List[Dict],
    metadata: Dict,
    table_structure: Dict,
    issues: List[Dict],
    vcg_results: Dict,
) -> bytes:
    """
    Returns bytes for arrive_checklist.md.
    Generates the full ARRIVE 2.0 author checklist table with auto-detected
    status and pre-filled section/line references where available.
    """
    title = _v(metadata, "title", fallback="[Dataset title]")
    creator = _v(metadata, "creator", fallback="")
    date_created = _v(metadata, "date_created", fallback="")
    protocol_ref = _v(metadata, "protocol_reference", fallback="")

    # Count statuses for summary
    statuses = []
    for item_id, category, name, rec in _ARRIVE_ITEMS:
        statuses.append(_checklist_status(
            item_id, columns, metadata, import_info, table_structure, issues, vcg_results
        ))

    n_reported = sum(1 for s in statuses if s.startswith("✅"))
    n_partial = sum(1 for s in statuses if s.startswith("⚠️"))
    n_missing = sum(1 for s in statuses if s.startswith("❌"))

    lines = [
        "# ARRIVE 2.0 Author Checklist",
        "",
        "> Generated by [FAIR-VCG Mentor](https://github.com/dhuzard/FAIR-csv-mentor).",
        "> Status is auto-detected from uploaded dataset and metadata. "
        "Review every item before submission.",
        "",
        f"**Dataset:** {title}  ",
        f"**Creator:** {creator}  ",
        f"**Date:** {date_created}  ",
        f"**Protocol:** {protocol_ref}  ",
        "",
        f"**Summary:** ✅ {n_reported} reported · ⚠️ {n_partial} partial · ❌ {n_missing} missing  ",
        "",
        "---",
        "",
        "## The ARRIVE Essential 10",
        "",
        "_These items are the basic minimum to include in a manuscript. Without this information, "
        "readers and reviewers cannot assess the reliability of the findings._",
        "",
        "| Item | Name | Recommendation | Status | Section / line number or reason for not reporting |",
        "|---|---|---|---|---|",
    ]

    for item_id, category, name, rec in _ARRIVE_ITEMS:
        if category != "Essential 10":
            continue
        status = _checklist_status(
            item_id, columns, metadata, import_info, table_structure, issues, vcg_results
        )
        # Build pre-filled reference where we can
        ref = _auto_reference(item_id, columns, metadata, import_info, table_structure, vcg_results)
        # Escape pipes in rec text for Markdown table
        rec_safe = rec.replace("|", "\\|")
        lines.append(f"| {item_id} | **{name}** | {rec_safe} | {status} | {ref} |")

    lines += [
        "",
        "---",
        "",
        "## The Recommended Set",
        "",
        "_These items complement the Essential 10 and add important context to the study. "
        "Reporting items in both sets represents best practice._",
        "",
        "| Item | Name | Recommendation | Status | Section / line number or reason for not reporting |",
        "|---|---|---|---|---|",
    ]

    for item_id, category, name, rec in _ARRIVE_ITEMS:
        if category != "Recommended":
            continue
        status = _checklist_status(
            item_id, columns, metadata, import_info, table_structure, issues, vcg_results
        )
        ref = _auto_reference(item_id, columns, metadata, import_info, table_structure, vcg_results)
        rec_safe = rec.replace("|", "\\|")
        lines.append(f"| {item_id} | **{name}** | {rec_safe} | {status} | {ref} |")

    lines += [
        "",
        "---",
        "",
        "## Action Items",
        "",
        "_Items flagged as missing or partial that should be addressed before submission:_",
        "",
    ]

    for idx, (item_id, category, name, rec) in enumerate(_ARRIVE_ITEMS):
        status = statuses[idx]
        if status.startswith("✅"):
            continue
        lines.append(f"- **Item {item_id} — {name}** ({status})")
        lines.append(f"  {rec}")
        lines.append("")

    lines += [
        "---",
        "",
        "_www.ARRIVEguidelines.org_",
        "",
        "_This checklist was generated by FAIR-VCG Mentor. "
        "Please review and complete all items before manuscript submission._",
    ]

    return "\n".join(lines).encode("utf-8")


def _auto_reference(
    item_id: int,
    columns: List[Dict],
    metadata: Dict,
    import_info: Dict,
    table_structure: Dict,
    vcg_results: Dict,
) -> str:
    """Generate a pre-filled reference string for each checklist item."""
    col_names = {c.get("name", "").lower() for c in columns}
    measurements = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "measurement"]
    conditions = [c.get("label") or c.get("name", "") for c in columns if c.get("inferred_type") == "experimental_condition"]

    if item_id == 1:
        groups = ", ".join(conditions) if conditions else ""
        entity = table_structure.get("primary_entity") or table_structure.get("row_represents") or "individual animal"
        return f"Groups: {groups}; unit: {entity}" if groups else f"Unit: {entity}"

    if item_id == 2:
        n = import_info.get("n_rows", "")
        ref = metadata.get("protocol_reference", "")
        return f"n={n} total rows; protocol: {ref}" if ref else f"n={n} total rows"

    if item_id == 3:
        has_excl = any(kw in col_names for kw in ("exclude", "excluded", "outlier"))
        return "Exclusion column detected in dataset" if has_excl else ""

    if item_id == 4:
        has_rand = any(kw in col_names for kw in ("random", "allocation"))
        return "Randomisation column detected" if has_rand else ""

    if item_id == 5:
        has_blind = any(kw in col_names for kw in ("blind", "masked"))
        return "Blinding column detected" if has_blind else ""

    if item_id == 6:
        return ", ".join(measurements[:5]) if measurements else ""

    if item_id == 7:
        if vcg_results:
            method = vcg_results.get("method_used", "")
            score = vcg_results.get("reliability_score", "")
            return f"VCG pipeline ({method}); reliability score={score}"
        ref = metadata.get("protocol_reference", "")
        return ref or ""

    if item_id == 8:
        species = _strain_values(columns)
        sex = _sex_values(columns)
        parts = []
        if species:
            parts.append(f"strain: {species}")
        if sex:
            parts.append(f"sex: {sex}")
        return "; ".join(parts) if parts else ""

    if item_id == 9:
        return metadata.get("protocol_reference", "")

    if item_id == 10:
        if vcg_results:
            breakdown = vcg_results.get("reliability_breakdown", {}).get("per_endpoint", {})
            if breakdown:
                return f"Summary stats for {len(breakdown)} endpoint(s) in VCG results section"
        return ""

    if item_id == 14:
        has_ethics = any(kw in col_names for kw in ("ethic", "iacuc", "approval"))
        return "Ethics column detected in dataset" if has_ethics else ""

    if item_id == 19:
        ref = metadata.get("protocol_reference", "")
        return f"Protocol: {ref}" if ref else ""

    if item_id == 20:
        uri = metadata.get("base_uri", "")
        return uri or ""

    return ""


# ── Zip bundler ───────────────────────────────────────────────────────────────

def generate_arrive_zip(
    import_info: Dict,
    columns: List[Dict],
    metadata: Dict,
    table_structure: Dict,
    issues: List[Dict],
    vcg_results: Dict,
) -> bytes:
    """
    Bundles arrive_study_plan.md and arrive_checklist.md into a zip archive.
    Returns bytes ready for streaming.
    """
    study_plan = generate_arrive_study_plan(
        import_info, columns, metadata, table_structure, vcg_results
    )
    checklist = generate_arrive_checklist(
        import_info, columns, metadata, table_structure, issues, vcg_results
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("arrive_study_plan.md", study_plan)
        zf.writestr("arrive_checklist.md", checklist)
    buf.seek(0)
    return buf.read()
