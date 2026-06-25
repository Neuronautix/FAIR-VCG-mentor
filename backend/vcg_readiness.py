"""Deterministic VCG readiness assessment for normalized project schemas."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from project_schema import validate_project_schema


LOW_CONFIDENCE_THRESHOLD = 0.65
UNKNOWN_UNITS = {"", "unknown", "n/a", "na", "none", "pending", "?"}
REQUIRED_VCG_FIELDS = ("subject_id", "treatment_col", "control_value", "outcome_cols")


def assess_vcg_readiness(project_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Return VCG readiness consequences for a project schema contract.

    The output is deterministic and JSON-safe:
    ``ready`` is true when there are no blocking issues, ``score`` is 0-100,
    and each blocking/warning item has a matching scientist-facing consequence.
    """
    validation = validate_project_schema(project_schema)
    if validation.get("schema") is None:
        blocking = _dedupe([f"Project schema could not be normalized: {err}" for err in validation["errors"]])
        return _assessment(False, 0, blocking, [], _consequences_for_blocking(blocking))

    schema = validation["schema"]
    roles = schema["vcg_roles"]
    columns = {column["name"]: column for column in schema["columns"]}

    blocking: List[str] = []
    warnings: List[str] = []

    for field in REQUIRED_VCG_FIELDS:
        if _missing_role_value(roles.get(field)):
            blocking.append(f"Missing VCG-critical field: {field}.")

    for error in validation["errors"]:
        blocking.append(error)

    for warning in validation["warnings"]:
        if not warning.startswith("VCG-critical field missing:"):
            warnings.append(warning)

    if not roles.get("covariate_cols"):
        warnings.append("No covariate columns selected for VCG adjustment.")

    for outcome_col in roles.get("outcome_cols") or []:
        column = columns.get(outcome_col)
        if column is None:
            continue
        if _unknown_outcome_unit(schema, column):
            warnings.append(f"Outcome column '{outcome_col}' is missing a known unit.")

    for role_key, column_name in _critical_column_refs(roles):
        column = columns.get(column_name)
        if column is None:
            continue
        confidence = float(column.get("confidence", 0.0) or 0.0)
        if confidence < LOW_CONFIDENCE_THRESHOLD:
            warnings.append(
                f"VCG-critical column '{column_name}' for {role_key} has low confidence ({confidence:.2f})."
            )
        review_status = str(column.get("review_status") or "")
        if review_status in {"must_ask", "reject"}:
            warnings.append(
                f"VCG-critical column '{column_name}' for {role_key} has review status '{review_status}'."
            )
        if not _has_column_evidence(schema, column_name, column):
            warnings.append(f"VCG-critical column '{column_name}' for {role_key} has no evidence.")

    blocking = _dedupe(blocking)
    warnings = _dedupe(warnings)
    consequences = _consequences_for_blocking(blocking) + _consequences_for_warnings(warnings)
    ready = not blocking
    score = _score(blocking, warnings)
    return _assessment(ready, score, blocking, warnings, consequences)


def _assessment(
    ready: bool,
    score: int,
    blocking: List[str],
    warnings: List[str],
    consequences: List[str],
) -> Dict[str, Any]:
    return {
        "ready": ready,
        "score": max(0, min(100, int(score))),
        "blocking": blocking,
        "warnings": warnings,
        "consequences": _dedupe(consequences),
    }


def _missing_role_value(value: Any) -> bool:
    return value in (None, "", [])


def _critical_column_refs(roles: Dict[str, Any]) -> Iterable[Tuple[str, str]]:
    refs: List[Tuple[str, str]] = []
    for role_key in ("subject_id", "treatment_col", "time_col"):
        value = roles.get(role_key)
        if value:
            refs.append((role_key, str(value)))
    for role_key in ("outcome_cols", "covariate_cols"):
        for value in roles.get(role_key) or []:
            refs.append((role_key, str(value)))
    return refs


def _unknown_outcome_unit(schema: Dict[str, Any], column: Dict[str, Any]) -> bool:
    name = column["name"]
    unit = column.get("unit")
    unit_record = schema.get("units", {}).get(name) or {}
    canonical_unit = unit_record.get("canonical_unit")
    return _unknown_text(unit) and _unknown_text(canonical_unit)


def _unknown_text(value: Optional[Any]) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in UNKNOWN_UNITS


def _has_column_evidence(schema: Dict[str, Any], column_name: str, column: Dict[str, Any]) -> bool:
    evidence_ids = {str(item.get("id")) for item in schema.get("evidence") or [] if item.get("id")}
    column_refs = {str(item) for item in column.get("evidence") or []}
    if column_refs.intersection(evidence_ids):
        return True
    support_keys: Set[str] = {
        column_name,
        f"columns.{column_name}",
        f"column:{column_name}",
    }
    for evidence in schema.get("evidence") or []:
        if support_keys.intersection(str(item) for item in evidence.get("supports") or []):
            return True
    return False


def _score(blocking: List[str], warnings: List[str]) -> int:
    if blocking:
        return max(0, 100 - (30 * len(blocking)) - (5 * len(warnings)))
    return max(0, 100 - (7 * len(warnings)))


def _consequences_for_blocking(blocking: List[str]) -> List[str]:
    consequences: List[str] = []
    for item in blocking:
        text = item.lower()
        if "references unknown column" in text:
            consequences.append(
                "Invalid role references prevent VCG from mapping the scientific design onto dataset columns."
            )
        elif "subject_id" in text:
            consequences.append(
                "Without a subject identifier, VCG cannot preserve paired observations or animal-level structure."
            )
        elif "treatment_col" in text:
            consequences.append(
                "Without a treatment column, VCG cannot separate intervention and comparator groups."
            )
        elif "control_value" in text:
            consequences.append(
                "Without a control value, VCG cannot identify the reference arm for effect estimation."
            )
        elif "outcome_cols" in text:
            consequences.append(
                "Without outcome columns, VCG has no endpoint to model or compare."
            )
        else:
            consequences.append(
                "The project schema must validate before VCG readiness can be trusted."
            )
    return consequences


def _consequences_for_warnings(warnings: List[str]) -> List[str]:
    consequences: List[str] = []
    for item in warnings:
        text = item.lower()
        if "no covariate" in text:
            consequences.append(
                "Missing covariates may leave baseline imbalance unadjusted in VCG comparisons."
            )
        elif "missing a known unit" in text:
            consequences.append(
                "A missing unit prevents endpoint harmonization across studies and datasets."
            )
        elif "low confidence" in text or "review status" in text:
            consequences.append(
                "Unresolved VCG-critical column decisions should be reviewed before relying on generated comparisons."
            )
        elif "has no evidence" in text:
            consequences.append(
                "VCG-critical columns without evidence are harder for scientists to audit and defend."
            )
        elif "evidence" in text:
            consequences.append(
                "Broken evidence references weaken traceability from the schema back to source papers."
            )
        else:
            consequences.append(
                "Schema warnings reduce confidence in downstream VCG interpretation."
            )
    return consequences


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


__all__ = ["assess_vcg_readiness"]
