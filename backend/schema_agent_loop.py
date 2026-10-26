"""
Planning helpers for scientific schema approval.

The functions here are deterministic utilities for the schema agent loop:
they classify draft questions by scientific impact and confidence, then
decide whether another user-facing HITL turn is required.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


QUESTION_DECISIONS = {"auto_accept", "needs_review", "must_ask", "reject"}

IMPACT_SCORE = {
    "none": 0.0,
    "low": 0.25,
    "minor": 0.25,
    "medium": 0.50,
    "moderate": 0.50,
    "high": 0.75,
    "critical": 1.00,
    "vcg_critical": 1.00,
}

VCG_CRITICAL_FIELDS = {
    "subject_id",
    "treatment_col",
    "treatment_value",
    "control_value",
    "outcome_cols",
    "time_col",
    "study_type",
    "design",
}

CATEGORY_IMPACT_BONUS = {
    "schema_conflict": 0.15,
    "vcg_assumption": 0.12,
    "unit_normalization": 0.10,
    "schema_field": 0.08,
    "ontology_mapping": 0.06,
    "corpus_schema_approval": 0.04,
}

RESOLVED_STATUSES = {"resolved", "approved", "applied", "accepted", "auto_accept"}


def rank_schema_questions(questions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rank candidate schema questions from most urgent to least urgent.

    Each returned item is a copy of the input question with:
      decision: auto_accept | needs_review | must_ask | reject
      priority: numeric score used for sorting
      scientific_impact_score: normalized 0..1 impact value

    Expected input is intentionally loose because upstream drafts can come from
    rules, LLM suggestions, or corpus-derived schemas.
    """
    ranked: List[Dict[str, Any]] = []
    for index, question in enumerate(questions):
        item = dict(question)
        confidence = _confidence(question.get("confidence"))
        impact = _impact_score(question)
        vcg_critical = _is_vcg_critical(question)
        resolved = is_question_resolved(question)
        decision = classify_schema_question(
            confidence=confidence,
            scientific_impact_score=impact,
            vcg_critical=vcg_critical,
            category=str(question.get("category") or ""),
            status=question.get("status"),
            resolved=resolved,
        )
        priority = _priority_score(decision, impact, confidence, vcg_critical)
        item.update({
            "decision": decision,
            "priority": priority,
            "scientific_impact_score": impact,
            "confidence": confidence,
            "vcg_critical": vcg_critical,
            "_rank_index": index,
        })
        ranked.append(item)

    ranked.sort(key=lambda q: (-q["priority"], -q["scientific_impact_score"], q["_rank_index"]))
    for item in ranked:
        item.pop("_rank_index", None)
    return ranked


def classify_schema_question(
    *,
    confidence: float,
    scientific_impact_score: float,
    vcg_critical: bool = False,
    category: str = "",
    status: Optional[str] = None,
    resolved: bool = False,
) -> str:
    """Classify one schema question into the HITL confidence semantics."""
    status_value = str(status or "").strip().lower()
    if status_value in {"rejected", "reject"}:
        return "reject"
    if resolved:
        return "auto_accept"
    if status_value in {"invalid", "stale"}:
        return "reject"
    if confidence < 0.20 and scientific_impact_score <= 0.35 and not vcg_critical:
        return "reject"
    if vcg_critical or category == "schema_conflict":
        return "must_ask"
    if scientific_impact_score >= 0.75 and confidence < 0.85:
        return "must_ask"
    if category == "corpus_schema_approval" and confidence < 0.90:
        return "must_ask"
    if confidence >= 0.90 and scientific_impact_score <= 0.50:
        return "auto_accept"
    return "needs_review"


def should_stop_schema_agent(
    questions: Iterable[Dict[str, Any]],
    *,
    resolved_fields: Optional[Iterable[str]] = None,
    required_vcg_fields: Optional[Iterable[str]] = None,
    iteration: int = 0,
    max_iterations: int = 6,
) -> Dict[str, Any]:
    """
    Return a stopping decision for the schema agent loop.

    Stop when there are no unresolved must_ask questions and all VCG-critical
    fields are resolved. Also stop at the iteration cap to prevent loops.
    """
    questions_list = list(questions)
    ranked = rank_schema_questions(questions_list)
    unresolved_must_ask = [
        q for q in ranked
        if q["decision"] == "must_ask" and not is_question_resolved(q)
    ]

    required = set(required_vcg_fields or VCG_CRITICAL_FIELDS)
    required.update(_critical_fields_from_questions(questions_list))
    resolved = set(resolved_fields or [])
    resolved.update(_resolved_fields_from_questions(ranked))
    unresolved_vcg_fields = sorted(field for field in required if field not in resolved)

    if iteration >= max_iterations:
        return {
            "stop": True,
            "reason": "iteration_cap",
            "iteration": iteration,
            "max_iterations": max_iterations,
            "unresolved_must_ask": unresolved_must_ask,
            "unresolved_vcg_fields": unresolved_vcg_fields,
        }

    stop = not unresolved_must_ask and not unresolved_vcg_fields
    return {
        "stop": stop,
        "reason": "ready" if stop else "needs_questions",
        "iteration": iteration,
        "max_iterations": max_iterations,
        "unresolved_must_ask": unresolved_must_ask,
        "unresolved_vcg_fields": unresolved_vcg_fields,
    }


def is_question_resolved(question: Dict[str, Any]) -> bool:
    if bool(question.get("resolved")):
        return True
    status = str(question.get("status") or "").strip().lower()
    return status in RESOLVED_STATUSES


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _impact_score(question: Dict[str, Any]) -> float:
    raw = question.get("scientific_impact", question.get("impact"))
    if isinstance(raw, (int, float)):
        score = float(raw)
        if score > 1.0:
            score = score / 100.0
    else:
        score = IMPACT_SCORE.get(str(raw or "medium").strip().lower(), 0.50)
    category = str(question.get("category") or "")
    score += CATEGORY_IMPACT_BONUS.get(category, 0.0)
    if _is_vcg_critical(question):
        score = max(score, 0.90)
    return max(0.0, min(1.0, score))


def _is_vcg_critical(question: Dict[str, Any]) -> bool:
    if bool(question.get("vcg_critical") or question.get("required_for_vcg")):
        return True
    field = _question_field(question)
    return field in VCG_CRITICAL_FIELDS


def _priority_score(
    decision: str,
    impact: float,
    confidence: float,
    vcg_critical: bool,
) -> float:
    decision_weight = {
        "must_ask": 3.0,
        "needs_review": 2.0,
        "auto_accept": 1.0,
        "reject": 0.0,
    }[decision]
    uncertainty = 1.0 - confidence
    vcg_weight = 0.5 if vcg_critical else 0.0
    return round(decision_weight + impact + (uncertainty * 0.25) + vcg_weight, 6)


def _critical_fields_from_questions(questions: Sequence[Dict[str, Any]]) -> Set[str]:
    fields: Set[str] = set()
    for question in questions:
        if _is_vcg_critical(question):
            field = _question_field(question)
            if field:
                fields.add(field)
    return fields


def _resolved_fields_from_questions(questions: Sequence[Dict[str, Any]]) -> Set[str]:
    fields: Set[str] = set()
    for question in questions:
        if is_question_resolved(question) or question.get("decision") == "auto_accept":
            field = _question_field(question)
            if field:
                fields.add(field)
    return fields


def _question_field(question: Dict[str, Any]) -> str:
    for key in ("field", "field_name", "key", "target", "vcg_field", "role"):
        value = question.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    payload = question.get("payload")
    if isinstance(payload, dict):
        for key in ("field", "field_name", "key", "target", "vcg_field", "role"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


__all__ = [
    "QUESTION_DECISIONS",
    "VCG_CRITICAL_FIELDS",
    "classify_schema_question",
    "is_question_resolved",
    "rank_schema_questions",
    "should_stop_schema_agent",
]
