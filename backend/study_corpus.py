"""Session-scoped study corpus state for multi-paper ingestion.

The corpus is intentionally stored as plain dictionaries/lists under
``session["study_corpus"]`` so the existing SQLite session JSON layer can
persist it without custom encoders.
"""
from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional


STUDY_CORPUS_KEY = "study_corpus"
SOURCE_TYPES = {"pdf", "doi", "text"}
PAPER_STATUSES = {"pending", "loaded", "extracted", "failed", "archived"}
CANDIDATE_STATUSES = {"candidate", "accepted", "rejected", "superseded"}
DECISION_STATUSES = {"accepted", "rejected", "edited", "deferred"}


def DEFAULT_STUDY_CORPUS() -> Dict[str, Any]:
    return {
        "version": 1,
        "papers": [],
        "article_schema_candidates": [],
        "consensus_schema": None,
        "conflicts": [],
        "expert_decisions": [],
        "schema_versions": [],
    }


def ensure_study_corpus(session: Dict[str, Any]) -> Dict[str, Any]:
    """Return the corpus dict, creating/migrating missing JSON-safe fields."""
    corpus = session.get(STUDY_CORPUS_KEY)
    if not isinstance(corpus, dict):
        corpus = DEFAULT_STUDY_CORPUS()
        session[STUDY_CORPUS_KEY] = corpus

    default = DEFAULT_STUDY_CORPUS()
    corpus["version"] = int(corpus.get("version") or default["version"])
    for key, value in default.items():
        if key == "version":
            continue
        if key not in corpus:
            corpus[key] = deepcopy(value)
    return corpus


def get_study_corpus(session: Dict[str, Any]) -> Dict[str, Any]:
    """Return a detached corpus snapshot for API responses or tests."""
    return deepcopy(ensure_study_corpus(session))


def add_paper_source(
    session: Dict[str, Any],
    *,
    source_type: str,
    source_ref: str,
    title: Optional[str] = None,
    text: Optional[str] = None,
    status: str = "pending",
    metadata: Optional[Dict[str, Any]] = None,
    paper_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a source paper to the corpus and return the stored paper entry."""
    source_type = str(source_type or "").strip().lower()
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of: {', '.join(sorted(SOURCE_TYPES))}")
    if not str(source_ref or "").strip():
        raise ValueError("source_ref is required.")
    if status not in PAPER_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(PAPER_STATUSES))}")
    if text is not None and not isinstance(text, str):
        raise ValueError("text must be a string when provided.")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object when provided.")

    corpus = ensure_study_corpus(session)
    paper = {
        "id": paper_id or _new_id("paper"),
        "source_type": source_type,
        "source_ref": str(source_ref).strip(),
        "title": title or str(source_ref).strip(),
        "text": text,
        "status": status,
        "metadata": _json_safe(metadata or {}),
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    corpus["papers"].append(paper)
    return paper


def update_paper_source(
    session: Dict[str, Any],
    paper_id: str,
    *,
    title: Optional[str] = None,
    text: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    paper = require_paper(session, paper_id)
    if title is not None:
        paper["title"] = title
    if text is not None:
        if not isinstance(text, str):
            raise ValueError("text must be a string.")
        paper["text"] = text
    if status is not None:
        if status not in PAPER_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(PAPER_STATUSES))}")
        paper["status"] = status
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object.")
        paper["metadata"] = _json_safe(metadata)
    paper["updated_at"] = time.time()
    return paper


def list_papers(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(ensure_study_corpus(session)["papers"])


def require_paper(session: Dict[str, Any], paper_id: str) -> Dict[str, Any]:
    for paper in ensure_study_corpus(session)["papers"]:
        if paper.get("id") == paper_id:
            return paper
    raise KeyError(paper_id)


def add_article_schema_candidate(
    session: Dict[str, Any],
    *,
    paper_id: str,
    schema: Dict[str, Any],
    evidence_spans: Optional[Iterable[Dict[str, Any]]] = None,
    source: str = "manual",
    confidence: Optional[float] = None,
    status: str = "candidate",
    candidate_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Store a schema candidate plus its evidence spans for one paper."""
    require_paper(session, paper_id)
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object.")
    if status not in CANDIDATE_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(CANDIDATE_STATUSES))}")

    spans = [_normalise_evidence_span(span, default_paper_id=paper_id) for span in (evidence_spans or [])]
    candidate = {
        "id": candidate_id or _new_id("schema_candidate"),
        "paper_id": paper_id,
        "schema": _json_safe(schema),
        "evidence_spans": spans,
        "source": source,
        "confidence": None if confidence is None else float(confidence),
        "status": status,
        "notes": notes,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    ensure_study_corpus(session)["article_schema_candidates"].append(candidate)
    return candidate


def list_article_schema_candidates(
    session: Dict[str, Any],
    *,
    paper_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    candidates = ensure_study_corpus(session)["article_schema_candidates"]
    if paper_id is not None:
        candidates = [c for c in candidates if c.get("paper_id") == paper_id]
    if status is not None:
        candidates = [c for c in candidates if c.get("status") == status]
    return list(candidates)


def set_consensus_schema(
    session: Dict[str, Any],
    schema: Dict[str, Any],
    *,
    source: str = "manual",
    based_on_candidate_ids: Optional[List[str]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object.")
    consensus = {
        "schema": _json_safe(schema),
        "source": source,
        "based_on_candidate_ids": list(based_on_candidate_ids or []),
        "notes": notes,
        "updated_at": time.time(),
    }
    ensure_study_corpus(session)["consensus_schema"] = consensus
    return consensus


def add_conflict(
    session: Dict[str, Any],
    *,
    field: str,
    candidate_ids: Optional[List[str]] = None,
    paper_ids: Optional[List[str]] = None,
    values: Optional[List[Any]] = None,
    description: Optional[str] = None,
    status: str = "open",
    conflict_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not field:
        raise ValueError("field is required.")
    conflict = {
        "id": conflict_id or _new_id("conflict"),
        "field": field,
        "candidate_ids": list(candidate_ids or []),
        "paper_ids": list(paper_ids or []),
        "values": _json_safe(list(values or [])),
        "description": description,
        "status": status,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    ensure_study_corpus(session)["conflicts"].append(conflict)
    return conflict


def record_expert_decision(
    session: Dict[str, Any],
    *,
    target_type: str,
    target_id: str,
    decision: str,
    rationale: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    expert_id: Optional[str] = None,
    decision_id: Optional[str] = None,
) -> Dict[str, Any]:
    if decision not in DECISION_STATUSES:
        raise ValueError(f"decision must be one of: {', '.join(sorted(DECISION_STATUSES))}")
    item = {
        "id": decision_id or _new_id("decision"),
        "target_type": target_type,
        "target_id": target_id,
        "decision": decision,
        "rationale": rationale,
        "payload": _json_safe(payload or {}),
        "expert_id": expert_id,
        "created_at": time.time(),
    }
    ensure_study_corpus(session)["expert_decisions"].append(item)
    return item


def add_schema_version(
    session: Dict[str, Any],
    *,
    schema: Dict[str, Any],
    reason: str,
    source: str = "manual",
    based_on_candidate_ids: Optional[List[str]] = None,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object.")
    corpus = ensure_study_corpus(session)
    version = {
        "id": version_id or _new_id("schema_version"),
        "version": len(corpus["schema_versions"]) + 1,
        "schema": _json_safe(schema),
        "reason": reason,
        "source": source,
        "based_on_candidate_ids": list(based_on_candidate_ids or []),
        "created_at": time.time(),
    }
    corpus["schema_versions"].append(version)
    return version


def _normalise_evidence_span(span: Dict[str, Any], *, default_paper_id: str) -> Dict[str, Any]:
    if not isinstance(span, dict):
        raise ValueError("Each evidence span must be an object.")
    start = span.get("start")
    end = span.get("end")
    out = {
        "paper_id": span.get("paper_id") or default_paper_id,
        "start": None if start is None else int(start),
        "end": None if end is None else int(end),
        "text": span.get("text"),
        "field": span.get("field"),
        "label": span.get("label"),
    }
    if out["start"] is not None and out["end"] is not None and out["end"] < out["start"]:
        raise ValueError("Evidence span end must be greater than or equal to start.")
    return out


def _json_safe(value: Any) -> Any:
    """Convert common non-JSON scalar/container values into plain Python data."""
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


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
