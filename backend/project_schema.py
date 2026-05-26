"""Validated project schema contract for corpus-level scientific schemas.

The project schema is the internal contract between multi-paper ingestion,
expert HITL review, FAIR scoring, and VCG readiness. It is intentionally stored
as plain JSON-safe dictionaries so it can live inside the existing session JSON.
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_SCHEMA_VERSION = 1

SCHEMA_STATUSES = {"draft", "needs_review", "approved", "superseded"}
REVIEW_STATUSES = {"auto_accept", "needs_review", "must_ask", "reject", "approved"}
METADATA_SOURCES = {"expert", "paper", "dataset", "template", "llm", "rule", "unknown"}
COLUMN_ROLES = {
    "identifier",
    "treatment",
    "control",
    "outcome",
    "covariate",
    "time",
    "metadata",
    "exclude",
    "unknown",
}
VCG_ROLE_KEYS = {
    "subject_id",
    "treatment_col",
    "control_value",
    "treatment_value",
    "outcome_cols",
    "covariate_cols",
    "time_col",
    "exclude_cols",
}
VCG_COLUMN_ROLE_KEYS = {
    "subject_id",
    "treatment_col",
    "outcome_cols",
    "covariate_cols",
    "time_col",
    "exclude_cols",
}
VCG_LIST_ROLE_KEYS = {"outcome_cols", "covariate_cols", "exclude_cols"}


def DEFAULT_PROJECT_SCHEMA() -> Dict[str, Any]:
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": "project_consensus_schema",
        "status": "draft",
        "metadata_fields": {},
        "columns": [],
        "vcg_roles": {
            "subject_id": None,
            "treatment_col": None,
            "control_value": None,
            "treatment_value": None,
            "outcome_cols": [],
            "covariate_cols": [],
            "time_col": None,
            "exclude_cols": [],
        },
        "units": {},
        "controlled_values": {},
        "ontology_mappings": {},
        "vcg_readiness": {
            "ready": False,
            "blocking": [],
            "warnings": [],
            "score": None,
        },
        "evidence": [],
        "expert_decisions": [],
    }


def normalize_project_schema(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a normalized project schema from a full or legacy draft object."""
    if not isinstance(schema, dict):
        raise ValueError("project schema must be an object.")

    raw = deepcopy(schema)
    out = DEFAULT_PROJECT_SCHEMA()
    out["schema_version"] = PROJECT_SCHEMA_VERSION
    out["name"] = str(raw.get("name") or out["name"])
    out["status"] = _choice(raw.get("status"), SCHEMA_STATUSES, "draft")

    out["evidence"] = [
        _normalize_evidence(item, index)
        for index, item in enumerate(_as_list(raw.get("evidence")))
        if isinstance(item, dict)
    ]
    evidence_ids = {item["id"] for item in out["evidence"]}

    out["metadata_fields"] = _normalize_metadata_fields(
        raw.get("metadata_fields") or raw.get("metadata") or {},
        evidence_ids,
    )

    columns_raw = raw.get("columns")
    if columns_raw is None and "fields" in raw:
        columns_raw = raw.get("fields")
    out["columns"] = _normalize_columns(_as_list(columns_raw), evidence_ids)

    out["vcg_roles"] = _normalize_vcg_roles(raw.get("vcg_roles") or raw.get("column_roles") or {})
    _infer_vcg_roles_from_columns(out)

    out["units"] = _normalize_units(raw.get("units") or {}, evidence_ids)
    out["controlled_values"] = _normalize_controlled_values(raw.get("controlled_values") or {}, evidence_ids)
    out["ontology_mappings"] = _normalize_ontology_mappings(raw.get("ontology_mappings") or {}, evidence_ids)

    readiness = raw.get("vcg_readiness") if isinstance(raw.get("vcg_readiness"), dict) else {}
    out["vcg_readiness"] = {
        "ready": bool(readiness.get("ready", False)),
        "blocking": [str(x) for x in _as_list(readiness.get("blocking"))],
        "warnings": [str(x) for x in _as_list(readiness.get("warnings"))],
        "score": _optional_float(readiness.get("score")),
    }
    out["expert_decisions"] = [
        _json_safe(item)
        for item in _as_list(raw.get("expert_decisions"))
        if isinstance(item, dict)
    ]
    return out


def validate_project_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate a project schema.

    Returns ``{"ok": bool, "errors": [...], "warnings": [...], "schema": normalized}``.
    """
    errors: List[str] = []
    warnings: List[str] = []
    try:
        normalized = normalize_project_schema(schema)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "schema": None}

    column_names = [c["name"] for c in normalized["columns"]]
    duplicates = sorted({name for name in column_names if column_names.count(name) > 1})
    for name in duplicates:
        errors.append(f"Duplicate column definition: {name}")

    column_set = set(column_names)
    roles = normalized["vcg_roles"]
    for key in VCG_COLUMN_ROLE_KEYS:
        value = roles.get(key)
        values = value if key in VCG_LIST_ROLE_KEYS else ([value] if value else [])
        for col in values:
            if col not in column_set:
                errors.append(f"vcg_roles.{key} references unknown column '{col}'.")

    evidence_ids = {item["id"] for item in normalized["evidence"]}
    for path, refs in _iter_evidence_refs(normalized):
        for ref in refs:
            if ref not in evidence_ids:
                warnings.append(f"{path} references unknown evidence id '{ref}'.")

    required_vcg = ("subject_id", "treatment_col", "control_value", "outcome_cols")
    for key in required_vcg:
        value = roles.get(key)
        if value in (None, "", []):
            warnings.append(f"VCG-critical field missing: {key}.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "schema": normalized,
    }


def project_schema_vcg_roles(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Return normalized VCG role mapping suitable for the VCG wizard/session."""
    result = validate_project_schema(schema)
    if not result["ok"]:
        raise ValueError("; ".join(result["errors"]))
    roles = result["schema"]["vcg_roles"]
    return {key: deepcopy(roles[key]) for key in sorted(VCG_ROLE_KEYS)}


def _normalize_metadata_fields(raw: Any, evidence_ids: set[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            field = value
            raw_value = field.get("value")
        else:
            field = {}
            raw_value = value
        out[str(key)] = {
            "value": _json_safe(raw_value),
            "required": bool(field.get("required", False)),
            "source": _choice(field.get("source"), METADATA_SOURCES, "unknown"),
            "ontology": _normalize_ontology(field.get("ontology")),
            "evidence": _evidence_refs(field.get("evidence")),
            "confidence": _confidence(field.get("confidence")),
            "review_status": _choice(field.get("review_status"), REVIEW_STATUSES, "needs_review"),
        }
    return out


def _normalize_columns(raw_columns: List[Any], evidence_ids: set[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in raw_columns:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("field") or item.get("column") or "").strip()
        if not name:
            continue
        controlled = item.get("controlled_values")
        if controlled is None:
            controlled = item.get("allowed_values")
        out.append({
            "name": name,
            "label": str(item.get("label") or item.get("title") or name),
            "description": item.get("description"),
            "semantic_type": str(item.get("semantic_type") or item.get("type") or "unknown"),
            "data_type": str(item.get("data_type") or item.get("datatype") or "unknown"),
            "unit": item.get("unit"),
            "required": bool(item.get("required", False)),
            "role": _choice(item.get("role"), COLUMN_ROLES, "unknown"),
            "controlled_values": [str(v) for v in _as_list(controlled)],
            "ontology": _normalize_ontology(item.get("ontology")),
            "evidence": _evidence_refs(item.get("evidence")),
            "confidence": _confidence(item.get("confidence")),
            "review_status": _choice(item.get("review_status"), REVIEW_STATUSES, "needs_review"),
        })
    return out


def _normalize_vcg_roles(raw: Any) -> Dict[str, Any]:
    out = deepcopy(DEFAULT_PROJECT_SCHEMA()["vcg_roles"])
    if not isinstance(raw, dict):
        return out
    for key in VCG_ROLE_KEYS:
        if key not in raw:
            continue
        if key in VCG_LIST_ROLE_KEYS:
            out[key] = [str(v) for v in _as_list(raw.get(key)) if str(v).strip()]
        else:
            value = raw.get(key)
            out[key] = None if value in (None, "") else str(value)
    return out


def _infer_vcg_roles_from_columns(schema: Dict[str, Any]) -> None:
    roles = schema["vcg_roles"]
    for col in schema["columns"]:
        name = col["name"]
        role = col.get("role")
        if role == "identifier" and not roles["subject_id"]:
            roles["subject_id"] = name
        elif role == "treatment" and not roles["treatment_col"]:
            roles["treatment_col"] = name
        elif role == "outcome" and name not in roles["outcome_cols"]:
            roles["outcome_cols"].append(name)
        elif role == "covariate" and name not in roles["covariate_cols"]:
            roles["covariate_cols"].append(name)
        elif role == "time" and not roles["time_col"]:
            roles["time_col"] = name
        elif role == "exclude" and name not in roles["exclude_cols"]:
            roles["exclude_cols"].append(name)


def _normalize_units(raw: Any, evidence_ids: set[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        item = value if isinstance(value, dict) else {"canonical_unit": value}
        canonical = item.get("canonical_unit") or item.get("unit") or item.get("target_unit")
        out[str(key)] = {
            "canonical_unit": None if canonical in (None, "") else str(canonical),
            "accepted_units": [str(v) for v in _as_list(item.get("accepted_units") or item.get("aliases"))],
            "conversion_required": bool(item.get("conversion_required", False)),
            "evidence": _evidence_refs(item.get("evidence")),
        }
    return out


def _normalize_controlled_values(raw: Any, evidence_ids: set[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        item = value if isinstance(value, dict) else {"canonical_values": value}
        aliases = item.get("aliases") if isinstance(item.get("aliases"), dict) else {}
        out[str(key)] = {
            "canonical_values": [str(v) for v in _as_list(item.get("canonical_values") or item.get("values"))],
            "aliases": {str(k): str(v) for k, v in aliases.items()},
            "evidence": _evidence_refs(item.get("evidence")),
        }
    return out


def _normalize_ontology_mappings(raw: Any, evidence_ids: set[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        item = value if isinstance(value, dict) else {"iri": value}
        item.setdefault("label", key)
        out[str(key)] = _normalize_ontology(item)
        out[str(key)]["confidence"] = _confidence(item.get("confidence"))
        out[str(key)]["evidence"] = _evidence_refs(item.get("evidence"))
    return out


def _normalize_ontology(raw: Any) -> Dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    return {
        "label": item.get("label") or item.get("term"),
        "iri": item.get("iri") or item.get("url"),
        "curie": item.get("curie") or item.get("ontology_id"),
        "source": item.get("source") or "pending",
    }


def _normalize_evidence(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    quote = raw.get("quote")
    if quote is None:
        quote = raw.get("text")
    return {
        "id": str(raw.get("id") or f"ev_{uuid.uuid4().hex}"),
        "paper_id": raw.get("paper_id"),
        "section": raw.get("section"),
        "quote": quote,
        "supports": [str(v) for v in _as_list(raw.get("supports"))],
        "confidence": _confidence(raw.get("confidence")),
    }


def _iter_evidence_refs(schema: Dict[str, Any]) -> Iterable[Tuple[str, List[str]]]:
    for key, field in schema["metadata_fields"].items():
        yield f"metadata_fields.{key}.evidence", field.get("evidence") or []
    for col in schema["columns"]:
        yield f"columns.{col['name']}.evidence", col.get("evidence") or []
    for key, unit in schema["units"].items():
        yield f"units.{key}.evidence", unit.get("evidence") or []
    for key, values in schema["controlled_values"].items():
        yield f"controlled_values.{key}.evidence", values.get("evidence") or []
    for key, ontology in schema["ontology_mappings"].items():
        yield f"ontology_mappings.{key}.evidence", ontology.get("evidence") or []


def _evidence_refs(value: Any) -> List[str]:
    refs: List[str] = []
    for item in _as_list(value):
        if isinstance(item, dict) and item.get("id"):
            refs.append(str(item["id"]))
        elif isinstance(item, str) and item.strip():
            refs.append(item.strip())
    return refs


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _choice(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return _confidence(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = [
    "DEFAULT_PROJECT_SCHEMA",
    "PROJECT_SCHEMA_VERSION",
    "VCG_ROLE_KEYS",
    "normalize_project_schema",
    "project_schema_vcg_roles",
    "validate_project_schema",
]
