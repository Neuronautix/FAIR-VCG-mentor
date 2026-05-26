"""FastAPI routes for session-scoped study corpus state."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException

from study_corpus import (
    add_article_schema_candidate,
    add_conflict,
    add_paper_source,
    add_schema_version,
    ensure_study_corpus,
    get_study_corpus,
    record_expert_decision,
    set_consensus_schema,
    update_paper_source,
)


_sessions: Dict[str, Any] = {}
_save_fn: Optional[Callable] = None
_load_fn: Optional[Callable] = None


def init_corpus_router(sessions: dict, save_fn: Callable, load_fn: Callable) -> None:
    global _sessions, _save_fn, _load_fn
    _sessions = sessions
    _save_fn = save_fn
    _load_fn = load_fn


def _require(dataset_id: str) -> dict:
    s = _sessions.get(dataset_id)
    if not s and _load_fn:
        s = _load_fn(dataset_id)
        if s:
            _sessions[dataset_id] = s
    if not s:
        raise HTTPException(404, "Dataset not found. Please upload your CSV again.")
    ensure_study_corpus(s)
    return s


def _persist(dataset_id: str, session: dict) -> None:
    if _save_fn:
        _save_fn(dataset_id, session)


def create_corpus_router(
    sessions: dict,
    save_fn: Optional[Callable] = None,
    load_fn: Optional[Callable] = None,
) -> APIRouter:
    """Create an isolated router instance for tests or deferred app wiring."""
    router = APIRouter(tags=["study-corpus"])

    def require(dataset_id: str) -> dict:
        s = sessions.get(dataset_id)
        if not s and load_fn:
            s = load_fn(dataset_id)
            if s:
                sessions[dataset_id] = s
        if not s:
            raise HTTPException(404, "Dataset not found. Please upload your CSV again.")
        ensure_study_corpus(s)
        return s

    def persist(dataset_id: str, session: dict) -> None:
        if save_fn:
            save_fn(dataset_id, session)

    _register_routes(router, require, persist)
    return router


corpus_router = APIRouter(tags=["study-corpus"])


def _register_routes(
    router: APIRouter,
    require_fn: Callable[[str], dict],
    persist_fn: Callable[[str, dict], None],
) -> None:
    @router.get("/api/{dataset_id}/study-corpus")
    async def read_study_corpus(dataset_id: str):
        return get_study_corpus(require_fn(dataset_id))

    @router.post("/api/{dataset_id}/study-corpus/papers")
    async def create_paper_source(dataset_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            paper = add_paper_source(
                s,
                source_type=body.get("source_type"),
                source_ref=body.get("source_ref"),
                title=body.get("title"),
                text=body.get("text"),
                status=body.get("status") or "pending",
                metadata=body.get("metadata"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return paper

    @router.patch("/api/{dataset_id}/study-corpus/papers/{paper_id}")
    async def patch_paper_source(dataset_id: str, paper_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            paper = update_paper_source(
                s,
                paper_id,
                title=body.get("title") if "title" in body else None,
                text=body.get("text") if "text" in body else None,
                status=body.get("status") if "status" in body else None,
                metadata=body.get("metadata") if "metadata" in body else None,
            )
        except KeyError:
            raise HTTPException(404, "Paper source not found.")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return paper

    @router.post("/api/{dataset_id}/study-corpus/schema-candidates")
    async def create_schema_candidate(dataset_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            candidate = add_article_schema_candidate(
                s,
                paper_id=body.get("paper_id"),
                schema=body.get("schema"),
                evidence_spans=body.get("evidence_spans") or [],
                source=body.get("source") or "manual",
                confidence=body.get("confidence"),
                status=body.get("status") or "candidate",
                notes=body.get("notes"),
            )
        except KeyError:
            raise HTTPException(404, "Paper source not found.")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return candidate

    @router.put("/api/{dataset_id}/study-corpus/consensus-schema")
    async def put_consensus_schema(dataset_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            consensus = set_consensus_schema(
                s,
                body.get("schema"),
                source=body.get("source") or "manual",
                based_on_candidate_ids=body.get("based_on_candidate_ids") or [],
                notes=body.get("notes"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return consensus

    @router.post("/api/{dataset_id}/study-corpus/conflicts")
    async def create_conflict(dataset_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            conflict = add_conflict(
                s,
                field=body.get("field"),
                candidate_ids=body.get("candidate_ids") or [],
                paper_ids=body.get("paper_ids") or [],
                values=body.get("values") or [],
                description=body.get("description"),
                status=body.get("status") or "open",
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return conflict

    @router.post("/api/{dataset_id}/study-corpus/expert-decisions")
    async def create_expert_decision(dataset_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            decision = record_expert_decision(
                s,
                target_type=body.get("target_type"),
                target_id=body.get("target_id"),
                decision=body.get("decision"),
                rationale=body.get("rationale"),
                payload=body.get("payload") or {},
                expert_id=body.get("expert_id"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return decision

    @router.post("/api/{dataset_id}/study-corpus/schema-versions")
    async def create_schema_version(dataset_id: str, body: Dict[str, Any]):
        s = require_fn(dataset_id)
        try:
            version = add_schema_version(
                s,
                schema=body.get("schema"),
                reason=body.get("reason") or "",
                source=body.get("source") or "manual",
                based_on_candidate_ids=body.get("based_on_candidate_ids") or [],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        persist_fn(dataset_id, s)
        return version

    @router.post("/api/{dataset_id}/study-corpus/schema-review")
    async def create_schema_review(dataset_id: str):
        s = require_fn(dataset_id)
        corpus = ensure_study_corpus(s)
        questions = _draft_schema_questions(corpus)

        from hitl import add_suggestions, list_suggestions
        from schema_agent_loop import rank_schema_questions, should_stop_schema_agent

        ranked = rank_schema_questions(questions)
        existing = {
            (item.get("category"), item.get("target"))
            for item in list_suggestions(s)
            if item.get("status") in {"pending", "edited"}
        }
        items = [
            _question_to_hitl_item(question)
            for question in ranked
            if question.get("decision") in {"must_ask", "needs_review"}
            and (question.get("category"), question.get("target")) not in existing
        ]
        created = add_suggestions(s, items)
        loop_state = should_stop_schema_agent(
            ranked,
            resolved_fields=_resolved_vcg_fields(corpus),
            iteration=int(corpus.get("agent_iteration") or 0),
            max_iterations=6,
        )
        corpus["agent_iteration"] = int(corpus.get("agent_iteration") or 0) + 1
        persist_fn(dataset_id, s)
        return {"created": created, "loop_state": loop_state}


_register_routes(corpus_router, _require, _persist)


def _draft_schema_questions(corpus: Dict[str, Any]) -> list[Dict[str, Any]]:
    questions: list[Dict[str, Any]] = []
    for conflict in corpus.get("conflicts") or []:
        if conflict.get("status") not in {"resolved", "accepted", "rejected"}:
            questions.append({
                "id": conflict.get("id"),
                "category": "schema_conflict",
                "target": conflict.get("field") or conflict.get("id"),
                "field": conflict.get("field"),
                "confidence": 0.6,
                "scientific_impact": "high",
                "status": conflict.get("status") or "open",
                "payload": {
                    "conflict": conflict.get("description") or f"Resolve {conflict.get('field')}",
                    "options": conflict.get("values") or conflict.get("candidate_ids") or ["review"],
                    "paper_ids": conflict.get("paper_ids") or [],
                    "candidate_ids": conflict.get("candidate_ids") or [],
                },
            })

    consensus = corpus.get("consensus_schema") or {}
    schema = consensus.get("schema") if isinstance(consensus, dict) else {}
    for role in ("subject_id", "treatment_col", "control_value", "outcome_cols"):
        if not _schema_has_field(schema or {}, role):
            questions.append({
                "id": f"missing_{role}",
                "category": "vcg_assumption",
                "target": role,
                "field": role,
                "confidence": 0.4,
                "scientific_impact": "vcg_critical",
                "vcg_critical": True,
                "payload": {
                    "role": role,
                    "assumption": f"Confirm the project schema field for {role}.",
                    "value": None,
                },
            })

    if schema:
        questions.append({
            "id": "consensus_schema_approval",
            "category": "corpus_schema_approval",
            "target": "consensus_schema",
            "field": "consensus_schema",
            "confidence": 0.75,
            "scientific_impact": "high",
            "payload": {
                "schema_id": "consensus_schema",
                "decision": "needs_review",
                "schema_name": "Project consensus schema",
            },
        })
    return questions


def _question_to_hitl_item(question: Dict[str, Any]) -> Dict[str, Any]:
    category = question.get("category") or "schema_field"
    target = question.get("target") or question.get("field") or "consensus_schema"
    decision = question.get("decision") or "needs_review"
    return {
        "category": category,
        "target": target,
        "source": "rule:schema-agent-loop",
        "title": _question_title(category, target, decision),
        "rationale": (
            "This schema decision affects scientific interpretation or downstream "
            "VCG readiness and needs expert review."
        ),
        "payload": question.get("payload") or {"field_name": target, "decision": decision},
        "confidence": float(question.get("confidence") or 0.0),
    }


def _question_title(category: str, target: str, decision: str) -> str:
    if category == "schema_conflict":
        return f"Resolve schema conflict: {target}"
    if category == "vcg_assumption":
        return f"Confirm VCG-critical field: {target}"
    if category == "corpus_schema_approval":
        return "Approve project consensus schema"
    return f"Review schema field: {target} ({decision})"


def _schema_has_field(schema: Dict[str, Any], field: str) -> bool:
    if field in schema:
        return True
    slots = schema.get("slots")
    if isinstance(slots, dict) and field in slots:
        return True
    if isinstance(slots, list) and field in slots:
        return True
    roles = schema.get("column_roles") or schema.get("vcg_defaults") or {}
    return isinstance(roles, dict) and bool(roles.get(field))


def _resolved_vcg_fields(corpus: Dict[str, Any]) -> set[str]:
    consensus = corpus.get("consensus_schema") or {}
    schema = consensus.get("schema") if isinstance(consensus, dict) else {}
    return {
        role
        for role in ("subject_id", "treatment_col", "control_value", "outcome_cols")
        if _schema_has_field(schema or {}, role)
    }
