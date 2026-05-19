"""Template layer: load FAIR/reporting-standard templates, match against datasets, validate."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from jsonschema import Draft202012Validator, ValidationError

TEMPLATES_DIR = Path(__file__).parent / "templates"
USER_TEMPLATES_DIR = TEMPLATES_DIR / "user"


META_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id", "name", "version"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_-]*$"},
        "name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "identifier": {"type": "string"},
        "conforms_to": {"type": "array", "items": {"type": "string"}},
        "ontology": {
            "type": "object",
            "properties": {"iri": {"type": "string"}, "prefix": {"type": "string"}},
        },
        "required_columns": {"type": "array", "items": {"$ref": "#/$defs/column"}},
        "optional_columns": {"type": "array", "items": {"$ref": "#/$defs/column"}},
        "required_metadata": {"type": "array", "items": {"$ref": "#/$defs/metadata"}},
        "vcg_defaults": {"type": "object"},
        "predefined_analyses": {"type": "array"},
        "fair_bonus": {
            "type": "object",
            "properties": {
                "dimension": {"enum": ["F", "A", "I", "R"]},
                "max_points": {"type": "integer"},
            },
        },
    },
    "$defs": {
        "column": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "name_patterns": {"type": "array", "items": {"type": "string"}},
                "semantic_type": {"type": "string"},
                "role": {"enum": ["subject_id", "treatment", "outcome", "covariate", "time", "clustering_unit"]},
                "arrive_section": {"type": "string"},
                "unit_required": {"type": "boolean"},
                "unit_column": {"type": "string"},
                "required": {"type": "boolean"},
                "severity": {"enum": ["high", "medium", "low"]},
            },
        },
        "metadata": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "arrive_section": {"type": "string"},
                "severity": {"enum": ["high", "medium", "low"]},
            },
        },
    },
}


@dataclass
class RequiredColumn:
    id: str
    name_patterns: List[str] = field(default_factory=list)
    semantic_type: Optional[str] = None
    role: Optional[str] = None
    arrive_section: Optional[str] = None
    unit_required: bool = False
    unit_column: Optional[str] = None
    required: bool = True
    severity: str = "high"


@dataclass
class RequiredMetadata:
    id: str
    arrive_section: Optional[str] = None
    severity: str = "medium"


@dataclass
class VCGDefaults:
    treatment_col: Optional[str] = None
    control_value: Optional[str] = None
    treatment_value: Optional[str] = None
    outcome_cols_from: Any = None
    covariate_cols: List[str] = field(default_factory=list)
    clustering: Optional[str] = None
    method: str = "auto"


@dataclass
class PredefinedAnalysis:
    id: str
    type: str
    description: str = ""
    requires_columns: List[str] = field(default_factory=list)


@dataclass
class Template:
    id: str
    name: str
    version: str
    description: str = ""
    identifier: Optional[str] = None
    conforms_to: List[str] = field(default_factory=list)
    ontology: Dict[str, Any] = field(default_factory=dict)
    required_columns: List[RequiredColumn] = field(default_factory=list)
    optional_columns: List[RequiredColumn] = field(default_factory=list)
    required_metadata: List[RequiredMetadata] = field(default_factory=list)
    vcg_defaults: Optional[VCGDefaults] = None
    predefined_analyses: List[PredefinedAnalysis] = field(default_factory=list)
    fair_bonus: Optional[Dict[str, Any]] = None
    source: str = "builtin"

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        return out


_REGEX_META = re.compile(r"[\\\^\$\*\+\?\{\}\[\]\|\(\)]")


def _is_regex(pattern: str) -> bool:
    return bool(_REGEX_META.search(pattern))


def _validate_template_dict(data: Dict[str, Any]) -> None:
    validator = Draft202012Validator(META_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise ValueError(f"Template validation failed: {msg}")


def _build_column(d: Dict[str, Any], default_required: bool) -> RequiredColumn:
    sev_default = "high" if d.get("required", default_required) else "low"
    return RequiredColumn(
        id=d["id"],
        name_patterns=list(d.get("name_patterns") or []),
        semantic_type=d.get("semantic_type"),
        role=d.get("role"),
        arrive_section=d.get("arrive_section"),
        unit_required=bool(d.get("unit_required", False)),
        unit_column=d.get("unit_column"),
        required=bool(d.get("required", default_required)),
        severity=d.get("severity", sev_default),
    )


def _build_metadata(d: Dict[str, Any]) -> RequiredMetadata:
    return RequiredMetadata(
        id=d["id"],
        arrive_section=d.get("arrive_section"),
        severity=d.get("severity", "medium"),
    )


def _build_template(data: Dict[str, Any], source: str = "builtin") -> Template:
    vcg = data.get("vcg_defaults")
    vcg_obj = None
    if vcg:
        vcg_obj = VCGDefaults(
            treatment_col=vcg.get("treatment_col"),
            control_value=vcg.get("control_value"),
            treatment_value=vcg.get("treatment_value"),
            outcome_cols_from=vcg.get("outcome_cols_from"),
            covariate_cols=list(vcg.get("covariate_cols") or []),
            clustering=vcg.get("clustering"),
            method=vcg.get("method", "auto"),
        )
    analyses = [
        PredefinedAnalysis(
            id=a["id"],
            type=a.get("type", "report"),
            description=a.get("description", ""),
            requires_columns=list(a.get("requires_columns") or []),
        )
        for a in (data.get("predefined_analyses") or [])
    ]
    return Template(
        id=data["id"],
        name=data["name"],
        version=str(data["version"]),
        description=data.get("description", ""),
        identifier=data.get("identifier"),
        conforms_to=list(data.get("conforms_to") or []),
        ontology=dict(data.get("ontology") or {}),
        required_columns=[_build_column(c, True) for c in (data.get("required_columns") or [])],
        optional_columns=[_build_column(c, False) for c in (data.get("optional_columns") or [])],
        required_metadata=[_build_metadata(m) for m in (data.get("required_metadata") or [])],
        vcg_defaults=vcg_obj,
        predefined_analyses=analyses,
        fair_bonus=data.get("fair_bonus"),
        source=source,
    )


def _merge_parent(child: Template, parent: Template) -> Template:
    """Merge parent's required_columns/required_metadata into child, child wins on id collision."""
    child_col_ids = {c.id for c in child.required_columns}
    for pc in parent.required_columns:
        if pc.id not in child_col_ids:
            child.required_columns.append(pc)
    child_meta_ids = {m.id for m in child.required_metadata}
    for pm in parent.required_metadata:
        if pm.id not in child_meta_ids:
            child.required_metadata.append(pm)
    return child


def _load_one(path: Path, source: str) -> Tuple[Dict[str, Any], Template]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Template {path} is not a mapping")
    _validate_template_dict(data)
    return data, _build_template(data, source=source)


_CACHE: Dict[str, Template] = {}


def load_templates(force: bool = False) -> Dict[str, Template]:
    """Load all builtin and user templates, resolve conforms_to chains."""
    global _CACHE
    if _CACHE and not force:
        return _CACHE

    raw: Dict[str, Tuple[Dict[str, Any], Template]] = {}

    if TEMPLATES_DIR.exists():
        for p in sorted(TEMPLATES_DIR.iterdir()):
            if p.is_dir():
                continue
            if p.suffix.lower() not in (".yaml", ".yml", ".json"):
                continue
            data, tpl = _load_one(p, source="builtin")
            raw[tpl.id] = (data, tpl)

    if USER_TEMPLATES_DIR.exists():
        for p in sorted(USER_TEMPLATES_DIR.iterdir()):
            if p.suffix.lower() not in (".yaml", ".yml", ".json"):
                continue
            data, tpl = _load_one(p, source="user")
            raw[tpl.id] = (data, tpl)

    resolved: Dict[str, Template] = {}

    def _resolve(tid: str, stack: Optional[set] = None) -> Template:
        stack = stack or set()
        if tid in resolved:
            return resolved[tid]
        if tid in stack:
            raise ValueError(f"Circular conforms_to involving '{tid}'")
        if tid not in raw:
            raise ValueError(f"Unknown parent template id '{tid}'")
        _, tpl = raw[tid]
        new_stack = stack | {tid}
        for parent_id in list(tpl.conforms_to):
            parent = _resolve(parent_id, new_stack)
            _merge_parent(tpl, parent)
        resolved[tid] = tpl
        return tpl

    for tid in list(raw.keys()):
        _resolve(tid)

    _CACHE = resolved
    return _CACHE


def get_template(tid: str) -> Optional[Template]:
    return load_templates().get(tid)


def template_summary(tpl: Template) -> Dict[str, Any]:
    return {
        "id": tpl.id,
        "name": tpl.name,
        "version": tpl.version,
        "description": tpl.description,
        "source": tpl.source,
        "conforms_to": list(tpl.conforms_to),
    }


# ── Matching ───────────────────────────────────────────────────────────────

def _pattern_matches(pattern: str, value: str) -> bool:
    if not value:
        return False
    if _is_regex(pattern):
        try:
            return re.search(pattern, value, re.IGNORECASE) is not None
        except re.error:
            return pattern.lower() in value.lower()
    return pattern.lower() in value.lower()


def _find_matching_column(field_spec: RequiredColumn, columns_list: List[Dict[str, Any]]) -> Optional[str]:
    for col in columns_list:
        name = str(col.get("name") or "")
        for pat in field_spec.name_patterns:
            if _pattern_matches(pat, name):
                return name
    return None


def match_template(
    template: Template,
    columns_list: List[Dict[str, Any]],
    metadata_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Score how well a dataset matches a template."""
    matched_columns: Dict[str, str] = {}
    missing_columns: List[str] = []
    for field_spec in template.required_columns:
        m = _find_matching_column(field_spec, columns_list)
        if m:
            matched_columns[field_spec.id] = m
        else:
            missing_columns.append(field_spec.id)

    matched_metadata: List[str] = []
    missing_metadata: List[str] = []
    for meta in template.required_metadata:
        val = metadata_dict.get(meta.id)
        if val not in (None, "", [], {}):
            matched_metadata.append(meta.id)
        else:
            missing_metadata.append(meta.id)

    total_cols = len(template.required_columns)
    total_meta = len(template.required_metadata)

    if total_cols == 0 and total_meta == 0:
        score = 0.0
    elif total_cols == 0:
        score = len(matched_metadata) / total_meta
    elif total_meta == 0:
        score = len(matched_columns) / total_cols
    else:
        score = (len(matched_columns) / total_cols) * 0.7 + (len(matched_metadata) / total_meta) * 0.3

    reasons: List[str] = []
    if total_cols:
        reasons.append(f"{len(matched_columns)}/{total_cols} required columns matched")
    if total_meta:
        reasons.append(f"{len(matched_metadata)}/{total_meta} required metadata fields present")
    if missing_columns[:3]:
        reasons.append(f"missing columns: {', '.join(missing_columns[:3])}{'…' if len(missing_columns) > 3 else ''}")

    return {
        "score": round(score, 4),
        "reasons": reasons,
        "matched_columns": matched_columns,
        "missing_columns": missing_columns,
        "matched_metadata": matched_metadata,
        "missing_metadata": missing_metadata,
    }


def suggest_templates(
    all_templates: Dict[str, Template],
    columns_list: List[Dict[str, Any]],
    metadata_dict: Dict[str, Any],
    threshold: float = 0.1,
) -> List[Dict[str, Any]]:
    """Rank templates by match score; only return those above threshold."""
    out: List[Dict[str, Any]] = []
    for tid, tpl in all_templates.items():
        m = match_template(tpl, columns_list, metadata_dict)
        if m["score"] > threshold:
            out.append({
                "id": tid,
                "name": tpl.name,
                "score": m["score"],
                "reasons": m["reasons"],
            })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ── Validation ─────────────────────────────────────────────────────────────

def _column_unit_satisfied(col: Dict[str, Any]) -> bool:
    return bool(col.get("user_unit") or col.get("unit_guess"))


def _find_column_by_name(columns_list: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    name_lower = name.lower()
    for col in columns_list:
        if str(col.get("name") or "").lower() == name_lower:
            return col
    return None


def _ancestors(template: Template, all_templates: Dict[str, Template]) -> List[str]:
    out: List[str] = []
    seen = set()

    def _walk(tid: str) -> None:
        if tid in seen:
            return
        seen.add(tid)
        t = all_templates.get(tid)
        if not t:
            return
        for p in t.conforms_to:
            out.append(p)
            _walk(p)
    _walk(template.id)
    return out


def _standard_label(template: Template, field_arrive_section: Optional[str]) -> str:
    """Top-level standard label for a conformance row."""
    if field_arrive_section and "ARRIVE" in template.name.upper():
        return template.name.split()[0].upper()
    return template.name


def validate_against_template(
    template: Template,
    columns_list: List[Dict[str, Any]],
    metadata_dict: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Walk required_columns + required_metadata, produce conformance report."""
    report: List[Dict[str, Any]] = []
    standard = template.name

    for field_spec in template.required_columns:
        col_name = _find_matching_column(field_spec, columns_list)
        section = field_spec.arrive_section or ""
        status = "missing"
        satisfied_by: Optional[Dict[str, str]] = None
        if col_name:
            col = _find_column_by_name(columns_list, col_name)
            if field_spec.unit_required:
                unit_ok = False
                if col is not None and _column_unit_satisfied(col):
                    unit_ok = True
                if not unit_ok and field_spec.unit_column:
                    companion = _find_column_by_name(columns_list, field_spec.unit_column)
                    if companion is not None:
                        unit_ok = True
                status = "satisfied" if unit_ok else "partial"
            else:
                status = "satisfied"
            satisfied_by = {"column": col_name}
        report.append({
            "standard": standard,
            "section": section,
            "field_id": field_spec.id,
            "status": status,
            "satisfied_by": satisfied_by,
            "severity": field_spec.severity,
            "is_column_field": True,
        })

    for meta in template.required_metadata:
        val = metadata_dict.get(meta.id)
        if val not in (None, "", [], {}):
            status = "satisfied"
            satisfied_by = {"metadata": meta.id}
        else:
            status = "missing"
            satisfied_by = None
        report.append({
            "standard": standard,
            "section": meta.arrive_section or "",
            "field_id": meta.id,
            "status": status,
            "satisfied_by": satisfied_by,
            "severity": meta.severity,
            "is_column_field": False,
        })

    return report


def conformance_to_issues(
    conformance_report: List[Dict[str, Any]],
    template_id: str,
) -> List[Dict[str, Any]]:
    """Convert non-satisfied conformance entries into FAIR-engine Issue dicts."""
    issues: List[Dict[str, Any]] = []
    for entry in conformance_report:
        if entry["status"] == "satisfied":
            continue
        field_id = entry["field_id"]
        section = entry.get("section") or "(unspecified)"
        is_column = entry.get("is_column_field", False)
        column_name = None
        if is_column and entry.get("satisfied_by"):
            column_name = entry["satisfied_by"].get("column")
        if entry["status"] == "partial":
            problem = (
                f'Template field "{field_id}" ({section}) is partially satisfied: '
                f'matching column found but required unit information is missing.'
            )
            fix = (
                f'Add a unit guess or a companion unit column for "{column_name}", '
                f'or set user_unit on that column.'
            )
        else:
            if is_column:
                problem = (
                    f'Template field "{field_id}" ({section}) is missing: '
                    f'no column in the dataset matches the expected name patterns.'
                )
                fix = (
                    f'Add a column matching the "{field_id}" field as defined by the '
                    f'{entry["standard"]} template, or rename an existing column to match.'
                )
            else:
                problem = (
                    f'Template field "{field_id}" ({section}) is missing from dataset metadata.'
                )
                fix = (
                    f'Add the "{field_id}" field to your dataset metadata via the metadata wizard '
                    f'to comply with {entry["standard"]}.'
                )
        issues.append({
            "id": f"template_{template_id}_{field_id}",
            "severity": entry.get("severity", "medium"),
            "category": "template_compliance",
            "column": column_name,
            "problem": problem,
            "why_it_matters": (
                f'Compliance with {entry["standard"]} ({section}) is required for the dataset '
                f'to meet the chosen reporting standard. Missing fields reduce reusability '
                f'and reproducibility.'
            ),
            "suggested_fix": fix,
        })
    return issues


# ── Paper-based template suggestion ──────────────────────────────────────────

# Keys present in the paper extraction arrive dict
_PAPER_ARRIVE_KEYS = {
    "study_design", "sample_size", "inclusion_exclusion_criteria",
    "randomisation", "blinding", "outcome_measures", "statistical_methods",
    "experimental_animals", "housing_husbandry", "ethics_statement",
    "adverse_events", "interpretation",
}

# template field_id → (arrive_key | None, metadata_key | None)
# First match wins. arrive_key: look in extraction["arrive"][key].value
# metadata_key: look in extraction["dataset_metadata"][key]
_FIELD_LOOKUP: List[Tuple[str, Optional[str], Optional[str]]] = [
    ("study_title",                   None,                        "title"),
    ("primary_contact",               None,                        "creator"),
    ("species",                       None,                        "species"),
    ("grant_code",                    None,                        "funding_source"),
    ("protocol_numbers",              None,                        "protocol_reference"),
    ("study_context_of_use",          None,                        "description"),
    ("biological_context",            None,                        "species"),
    ("title",                         None,                        "title"),
    ("description",                   None,                        "description"),
    ("license",                       None,                        "license"),
    ("keywords",                      None,                        "keywords"),
    ("study_design",                  "study_design",              None),
    ("randomisation",                 "randomisation",             None),
    ("blinding",                      "blinding",                  None),
    ("outcome_measures",              "outcome_measures",          None),
    ("statistical_methods",           "statistical_methods",       None),
    ("adverse_events",                "adverse_events",            None),
    ("ethics_statement",              "ethics_statement",          None),
    ("interpretation",                "interpretation",            None),
    ("total_n",                       "sample_size",               None),
    ("housing_density",               "housing_husbandry",         None),
    ("procedures_description",        "study_design",              None),
    ("surgical_procedures",           "study_design",              None),
    ("experimental_animals",          "experimental_animals",      None),
    ("strain",                        "experimental_animals",      None),
    ("sex",                           "experimental_animals",      None),
    ("age",                           "experimental_animals",      None),
    ("weight",                        "experimental_animals",      None),
    ("anaesthesia",                   "experimental_animals",      None),
    ("supplier",                      "experimental_animals",      None),
    ("inclusion_exclusion_criteria",  "inclusion_exclusion_criteria", None),
    ("endpoints",                     "outcome_measures",          None),
    ("perturbations",                 None,                        "study_type"),
]
_FIELD_LOOKUP_MAP: Dict[str, Tuple[Optional[str], Optional[str]]] = {
    fid: (ak, mk) for fid, ak, mk in _FIELD_LOOKUP
}


def _lookup_paper_value(
    field_id: str,
    arrive: Dict[str, Any],
    meta: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], str]:
    """Return (value, source_path, status) for a template field_id."""
    # Check direct arrive key match first
    if field_id in _PAPER_ARRIVE_KEYS:
        f = arrive.get(field_id, {})
        val = f.get("value") if isinstance(f, dict) else None
        status = f.get("status", "missing") if isinstance(f, dict) else "missing"
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val) if val else None
        return val, f"arrive.{field_id}", status

    lookup = _FIELD_LOOKUP_MAP.get(field_id)
    if lookup:
        arrive_key, meta_key = lookup
        if arrive_key:
            f = arrive.get(arrive_key, {})
            val = f.get("value") if isinstance(f, dict) else None
            status = f.get("status", "missing") if isinstance(f, dict) else "missing"
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val) if val else None
            return val, f"arrive.{arrive_key}", status
        if meta_key:
            val = meta.get(meta_key)
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val) if val else None
            return val, f"dataset_metadata.{meta_key}", "found" if val else "missing"

    return None, None, "missing"


def _build_field_mapping(tpl: Template, extraction: Dict[str, Any]) -> List[Dict[str, Any]]:
    arrive = extraction.get("arrive", {})
    meta = extraction.get("dataset_metadata", {})
    vcg_hints = extraction.get("vcg_hints", {})
    outcome_cols = list(vcg_hints.get("outcome_columns") or [])
    covariate_cols = list(vcg_hints.get("covariate_columns") or [])

    mapping: List[Dict[str, Any]] = []

    for req in tpl.required_metadata:
        val, source, status = _lookup_paper_value(req.id, arrive, meta)
        mapping.append({
            "field_id": req.id,
            "label": req.id.replace("_", " ").title(),
            "arrive_section": req.arrive_section or "",
            "value": val,
            "source": source,
            "status": "filled" if val else "missing",
            "severity": req.severity,
            "is_column": False,
        })

    for req in tpl.required_columns[:12]:
        val = None
        source = None
        for col in outcome_cols + covariate_cols:
            for pat in req.name_patterns:
                if _pattern_matches(pat, col):
                    val = col
                    source = "vcg_hints.outcome_columns"
                    break
            if val:
                break
        mapping.append({
            "field_id": req.id,
            "label": req.id.replace("_", " ").title(),
            "arrive_section": req.arrive_section or "",
            "value": val,
            "source": source,
            "status": "filled" if val else "missing",
            "severity": req.severity,
            "is_column": True,
        })

    return mapping


def _score_template_from_paper(
    tpl: Template,
    arrive: Dict[str, Any],
    meta: Dict[str, Any],
    vcg_hints: Dict[str, Any],
) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    tid_lower = tpl.id.lower()
    keywords = [k.lower() for k in (meta.get("keywords") or [])]
    species = (meta.get("species") or "").lower()
    study_type = (meta.get("study_type") or "").lower()
    is_in_vivo = any(kw in species for kw in [
        "mus", "rat", "mouse", "rattus", "rabbit", "canis", "primate", "macaca",
    ])

    arrive_vals = [v for v in arrive.values() if isinstance(v, dict)]
    n_found = sum(1 for f in arrive_vals if f.get("status") in ("found", "inferred"))
    n_total = len(arrive_vals)

    if "arrive" in tid_lower:
        if n_total > 0:
            ratio = n_found / n_total
            score += ratio * 0.6
            if n_found > 0:
                reasons.append(f"{n_found}/{n_total} ARRIVE 2.0 fields extracted")
        if is_in_vivo:
            score += 0.25
            reasons.append(f"in vivo species: {meta.get('species', '')}")
    elif "mnms" in tid_lower:
        cage_kws = ["cage", "dvc", "homecage", "home cage", "group hous"]
        matched = [k for k in keywords if any(ck in k for ck in cage_kws)]
        if matched:
            score += 0.55
            reasons.append(f"cage/DVC keywords: {', '.join(matched[:2])}")
        if is_in_vivo:
            score += 0.1
    elif "namo" in tid_lower:
        nam_kws = ["nam", "in vitro", "assay", "dose-response", "dose response",
                   "ic50", "cell line", "organoid", "microphysiological"]
        matched = [k for k in keywords if any(nk in k for nk in nam_kws)]
        if matched:
            score += 0.55
            reasons.append(f"NAM/in vitro keywords: {', '.join(matched[:2])}")
        if not is_in_vivo and ("vitro" in study_type or "vitro" in " ".join(keywords)):
            score += 0.2
            reasons.append("non-in-vivo study type")

    # Metadata field coverage boost
    if tpl.required_metadata:
        filled = sum(
            1 for req in tpl.required_metadata
            if _lookup_paper_value(req.id, arrive, meta)[0] is not None
        )
        meta_ratio = filled / len(tpl.required_metadata)
        score = min(1.0, score + meta_ratio * 0.15)
        if filled > 0:
            reasons.append(f"{filled}/{len(tpl.required_metadata)} metadata fields available")

    return min(1.0, round(score, 4)), reasons


def suggest_from_paper_extraction(
    extraction: Dict[str, Any],
    all_templates: Dict[str, "Template"],
    threshold: float = 0.05,
) -> List[Dict[str, Any]]:
    """Rank templates by match score against paper extraction signals."""
    arrive = extraction.get("arrive", {})
    meta = extraction.get("dataset_metadata", {})
    vcg_hints = extraction.get("vcg_hints", {})

    candidates: List[Dict[str, Any]] = []
    for tid, tpl in all_templates.items():
        score, reasons = _score_template_from_paper(tpl, arrive, meta, vcg_hints)
        if score >= threshold:
            candidates.append({
                "id": tid,
                "name": tpl.name,
                "version": tpl.version,
                "description": tpl.description,
                "score": score,
                "reasons": reasons,
                "field_mapping": _build_field_mapping(tpl, extraction),
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def generate_starter_yaml(tpl: "Template", extraction: Dict[str, Any]) -> str:
    """Generate a starter YAML for a new user template pre-filled with paper hints."""
    meta = extraction.get("dataset_metadata", {})
    vcg_hints = extraction.get("vcg_hints", {})

    title = meta.get("title") or ""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-") or "custom"
    new_id = f"{tpl.id}-{slug}"

    data: Dict[str, Any] = {
        "id": new_id,
        "name": f"{tpl.name} — {title[:60]}" if title else tpl.name,
        "version": "1.0",
        "description": (
            f"Starter template derived from '{tpl.name}'. "
            f"Based on paper: {title}. "
            "Customise required_columns and required_metadata before reuse."
        ),
        "conforms_to": [tpl.id],
    }

    if tpl.required_columns:
        data["required_columns"] = [
            {k: v for k, v in {
                "id": c.id,
                "name_patterns": c.name_patterns,
                "semantic_type": c.semantic_type,
                "role": c.role,
                "required": c.required,
                "severity": c.severity,
            }.items() if v is not None}
            for c in tpl.required_columns
        ]

    if tpl.required_metadata:
        data["required_metadata"] = [
            {k: v for k, v in {
                "id": m.id,
                "arrive_section": m.arrive_section,
                "severity": m.severity,
            }.items() if v is not None}
            for m in tpl.required_metadata
        ]

    vcg_data: Dict[str, Any] = {}
    base_vcg = tpl.vcg_defaults
    if base_vcg:
        vcg_data["method"] = base_vcg.method
        vcg_data["control_value"] = vcg_hints.get("control_group_label") or base_vcg.control_value
        vcg_data["treatment_value"] = vcg_hints.get("treatment_group_label") or base_vcg.treatment_value
        if vcg_hints.get("treatment_column_name"):
            vcg_data["treatment_col"] = vcg_hints["treatment_column_name"]
        if vcg_hints.get("outcome_columns"):
            vcg_data["outcome_cols_from"] = vcg_hints["outcome_columns"]
    elif vcg_hints.get("treatment_column_name"):
        vcg_data = {
            "method": "auto",
            "treatment_col": vcg_hints["treatment_column_name"],
            "control_value": vcg_hints.get("control_group_label"),
            "treatment_value": vcg_hints.get("treatment_group_label"),
            "outcome_cols_from": vcg_hints.get("outcome_columns") or [],
        }
    if vcg_data:
        data["vcg_defaults"] = {k: v for k, v in vcg_data.items() if v is not None}

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


# ── User template upload ───────────────────────────────────────────────────

def save_user_template(content: str, source_format: str) -> Template:
    """Validate then write a user template to backend/templates/user/."""
    fmt = source_format.lower()
    if fmt == "json":
        data = json.loads(content)
    elif fmt in ("yaml", "yml"):
        data = yaml.safe_load(content)
    else:
        raise ValueError(f"Unsupported source_format: {source_format}")

    if not isinstance(data, dict):
        raise ValueError("Template body must be a mapping/object.")

    _validate_template_dict(data)

    tid = data["id"]
    builtins = {
        p.stem for p in TEMPLATES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".yaml", ".yml", ".json")
    } if TEMPLATES_DIR.exists() else set()
    if tid in builtins:
        raise ValueError(f"Template id '{tid}' collides with a builtin template.")

    USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = USER_TEMPLATES_DIR / f"{tid}.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    load_templates(force=True)
    tpl = get_template(tid)
    if tpl is None:
        raise RuntimeError(f"Failed to reload saved template '{tid}'")
    return tpl
