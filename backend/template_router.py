"""FastAPI router for template registry + dataset-scoped template assignment."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import yaml
from fastapi import APIRouter, HTTPException, Request

from template_engine import (
    conformance_to_issues,
    generate_experiment_csv,
    generate_starter_yaml,
    get_template,
    load_templates,
    save_user_template,
    suggest_from_paper_extraction,
    suggest_templates,
    template_summary,
    validate_against_template,
)

template_router = APIRouter(tags=["templates"])

_sessions: Dict[str, Any] = {}
_save_fn: Optional[Callable] = None
_load_fn: Optional[Callable] = None


def init_template_router(sessions: dict, save_fn: Callable, load_fn: Callable) -> None:
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
    s.setdefault("template_id", None)
    s.setdefault("template_candidates", [])
    s.setdefault("template_validation", [])
    return s


def _persist(dataset_id: str, session: dict) -> None:
    if _save_fn:
        _save_fn(dataset_id, session)


def _strip_template_issues(session: dict) -> None:
    session["issues"] = [
        i for i in session.get("issues", [])
        if i.get("category") != "template_compliance"
    ]


# ── Registry routes ────────────────────────────────────────────────────────

@template_router.get("/api/templates")
async def list_templates():
    templates = load_templates(force=True)
    builtin = [template_summary(t) for t in templates.values() if t.source == "builtin"]
    user = [template_summary(t) for t in templates.values() if t.source == "user"]
    return {"builtin": builtin, "user": user}


@template_router.get("/api/templates/registry/{tid}")
async def get_template_full(tid: str):
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    return tpl.to_dict()


@template_router.post("/api/templates")
async def upload_template(request: Request):
    raw = await request.body()
    if not raw:
        raise HTTPException(400, "Empty request body.")
    content_type = (request.headers.get("content-type") or "").lower()
    if "json" in content_type:
        source_format = "json"
    elif "yaml" in content_type or "yml" in content_type:
        source_format = "yaml"
    else:
        try:
            json.loads(raw)
            source_format = "json"
        except Exception:
            source_format = "yaml"
    try:
        tpl = save_user_template(raw.decode("utf-8"), source_format=source_format)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return template_summary(tpl)


@template_router.post("/api/templates/paper/suggestions")
async def paper_template_suggestions(request: Request):
    """Score all templates against a paper extraction payload (no dataset required)."""
    body = await request.json()
    extraction = body.get("extraction")
    additional_terms = body.get("additional_terms") or []
    if not extraction or not isinstance(extraction, dict):
        raise HTTPException(400, "Field 'extraction' (object) is required.")
    if not isinstance(additional_terms, list):
        raise HTTPException(400, "Field 'additional_terms' must be an array of strings when provided.")
    templates = load_templates()
    candidates = suggest_from_paper_extraction(extraction, templates, additional_terms=additional_terms)
    return {"candidates": candidates}


@template_router.post("/api/templates/paper/generate-csv")
async def generate_experiment_csv_endpoint(request: Request):
    """Generate a blank experiment CSV pre-populated with template columns + paper hints."""
    body = await request.json()
    tid = body.get("template_id")
    extraction = body.get("extraction") or {}
    include_field_ids = body.get("include_field_ids")
    if not tid:
        raise HTTPException(400, "Field 'template_id' is required.")
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    if include_field_ids is not None:
        if not isinstance(include_field_ids, list):
            raise HTTPException(400, "Field 'include_field_ids' must be an array of template field IDs.")
        valid_field_ids = {c.id for c in list(tpl.required_columns) + list(tpl.optional_columns)}
        selected = [str(fid) for fid in include_field_ids if str(fid) in valid_field_ids]
        if not selected:
            raise HTTPException(400, "No valid template fields selected for CSV export.")
        include_field_ids = selected
    csv_content = generate_experiment_csv(tpl, extraction, include_field_ids=include_field_ids)
    return {"csv": csv_content, "filename": f"{tid}-experiment-template.csv"}


@template_router.post("/api/templates/paper/suggest-terms")
async def suggest_terms_for_paper(request: Request):
    """Ask LLM for additional search terms to refine paper-template matching."""
    body = await request.json()
    extraction = body.get("extraction")
    current_terms = body.get("current_terms") or []
    if not extraction or not isinstance(extraction, dict):
        raise HTTPException(400, "Field 'extraction' (object) is required.")
    if not isinstance(current_terms, list):
        raise HTTPException(400, "Field 'current_terms' must be an array of strings when provided.")

    from llm_service import LLMUnavailable, call_haiku

    dataset_meta = extraction.get("dataset_metadata") or {}
    paper_summary = extraction.get("summary") or ""
    prompt_payload = {
        "title": dataset_meta.get("title"),
        "study_type": dataset_meta.get("study_type"),
        "species": dataset_meta.get("species"),
        "keywords": dataset_meta.get("keywords") or [],
        "summary": str(paper_summary)[:3000],
        "current_terms": [str(t).strip() for t in current_terms if str(t).strip()][:20],
    }
    tool = {
        "name": "suggest_additional_terms",
        "description": "Suggest concise additional search terms for template matching.",
        "input_schema": {
            "type": "object",
            "properties": {
                "terms": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["terms", "rationale"],
            "additionalProperties": False,
        },
    }
    try:
        llm_result = call_haiku(
            system_prompt=(
                "You help users find metadata/reporting templates for a study. "
                "Propose short domain terms (2-4 words each) that are likely to improve template retrieval."
            ),
            tool=tool,
            user_message=json.dumps(prompt_payload),
            max_tokens=512,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))

    terms = []
    seen = set()
    for raw in llm_result.get("terms") or []:
        term = str(raw or "").strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return {"terms": terms[:12], "rationale": llm_result.get("rationale") or ""}


@template_router.post("/api/templates/paper/generate-yaml")
async def generate_starter_yaml_endpoint(request: Request):
    """Generate a downloadable starter YAML from a template + paper extraction (no dataset required)."""
    body = await request.json()
    tid = body.get("template_id")
    extraction = body.get("extraction") or {}
    if not tid:
        raise HTTPException(400, "Field 'template_id' is required.")
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    return {"starter_yaml": generate_starter_yaml(tpl, extraction)}


@template_router.post("/api/templates/import-linkml")
async def import_linkml(request: Request):
    body = await request.json()
    linkml_yaml = body.get("linkml_yaml")
    target_class = body.get("target_class") or None
    save = bool(body.get("save_as_user_template", False))
    if not isinstance(linkml_yaml, str) or not linkml_yaml.strip():
        raise HTTPException(400, "Field 'linkml_yaml' is required and must be a non-empty string.")
    from linkml_import import parse_linkml_yaml, linkml_to_template
    try:
        parsed = parse_linkml_yaml(linkml_yaml)
        template_dict = linkml_to_template(parsed, target_class)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    saved_summary = None
    if save:
        try:
            tpl = save_user_template(yaml.safe_dump(template_dict, sort_keys=False), "yaml")
            saved_summary = template_summary(tpl)
        except ValueError as exc:
            raise HTTPException(400, f"Generated template rejected on save: {exc}")
    return {
        "template": template_dict,
        "saved": saved_summary,
        "as_yaml": yaml.safe_dump(template_dict, sort_keys=False, allow_unicode=True),
    }


# ── Dataset-scoped routes ──────────────────────────────────────────────────

@template_router.get("/api/{dataset_id}/template/suggestions")
async def template_suggestions(dataset_id: str):
    s = _require(dataset_id)
    templates = load_templates()
    candidates = suggest_templates(templates, s.get("columns", []), s.get("metadata", {}))
    auto_assigned: Optional[str] = None
    if candidates and candidates[0]["score"] >= 0.9 and not s.get("template_id"):
        tid = candidates[0]["id"]
        tpl = get_template(tid)
        if tpl is not None:
            report = validate_against_template(tpl, s.get("columns", []), s.get("metadata", {}))
            _strip_template_issues(s)
            s["template_id"] = tid
            s["template_validation"] = report
            s["template_candidates"] = candidates
            s["issues"].extend(conformance_to_issues(report, tid))
            _persist(dataset_id, s)
            auto_assigned = tid
    else:
        s["template_candidates"] = candidates
        _persist(dataset_id, s)
    return {"candidates": candidates, "auto_assigned": auto_assigned}


@template_router.post("/api/{dataset_id}/template/apply-from-paper")
async def apply_template_from_paper(dataset_id: str, request: Request):
    """Assign a template chosen from paper suggestions; returns conformance report."""
    body = await request.json()
    tid = body.get("template_id")
    if not tid:
        raise HTTPException(400, "Field 'template_id' is required.")
    s = _require(dataset_id)
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    report = validate_against_template(tpl, s.get("columns", []), s.get("metadata", {}))
    _strip_template_issues(s)
    s["template_id"] = tid
    s["template_validation"] = report
    s["issues"].extend(conformance_to_issues(report, tid))
    _persist(dataset_id, s)
    return {"template_id": tid, "conformance_report": report}


@template_router.post("/api/{dataset_id}/template/{tid}")
async def assign_template(dataset_id: str, tid: str):
    s = _require(dataset_id)
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    report = validate_against_template(tpl, s.get("columns", []), s.get("metadata", {}))
    _strip_template_issues(s)
    s["template_id"] = tid
    s["template_validation"] = report
    s["issues"].extend(conformance_to_issues(report, tid))
    _persist(dataset_id, s)
    return {"template_id": tid, "conformance_report": report}


@template_router.delete("/api/{dataset_id}/template")
async def unassign_template(dataset_id: str):
    s = _require(dataset_id)
    _strip_template_issues(s)
    s["template_id"] = None
    s["template_validation"] = []
    _persist(dataset_id, s)
    return {"template_id": None}


@template_router.get("/api/{dataset_id}/template/validation")
async def template_validation(dataset_id: str):
    s = _require(dataset_id)
    tid = s.get("template_id")
    if not tid:
        return {"template_id": None, "conformance_report": []}
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    report = validate_against_template(tpl, s.get("columns", []), s.get("metadata", {}))
    return {"template_id": tid, "conformance_report": report}
