"""FastAPI router for template registry + dataset-scoped template assignment."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import yaml
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from template_constants import MAX_ADDITIONAL_TERMS

from template_completion import (
    build_completion_report,
    fields_to_llm_prompt,
    fill_from_paper_extraction,
)
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

_DOC_MAX_BYTES = 20 * 1024 * 1024  # 20 MB cap for supplementary document upload
_LLM_BATCH_SIZE = 12

template_router = APIRouter(tags=["templates"])

_sessions: Dict[str, Any] = {}
_save_fn: Optional[Callable] = None
_load_fn: Optional[Callable] = None


def _sanitize_term_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(400, f"Field '{field_name}' must be an array of strings when provided.")
    terms: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            continue
        term = raw.strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= MAX_ADDITIONAL_TERMS:
            break
    return terms


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
    additional_terms = _sanitize_term_list(body.get("additional_terms"), "additional_terms")
    if not extraction or not isinstance(extraction, dict):
        raise HTTPException(400, "Field 'extraction' (object) is required.")
    templates = load_templates()
    candidates = suggest_from_paper_extraction(extraction, templates, additional_terms=additional_terms)
    return {"candidates": candidates, "max_additional_terms": MAX_ADDITIONAL_TERMS}


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
    current_terms = _sanitize_term_list(body.get("current_terms"), "current_terms")
    if not extraction or not isinstance(extraction, dict):
        raise HTTPException(400, "Field 'extraction' (object) is required.")

    from llm_service import LLMUnavailable, call_haiku

    dataset_meta = extraction.get("dataset_metadata") or {}
    paper_summary = extraction.get("summary") or ""
    prompt_payload = {
        "title": dataset_meta.get("title"),
        "study_type": dataset_meta.get("study_type"),
        "species": dataset_meta.get("species"),
        "keywords": dataset_meta.get("keywords") or [],
        "summary": str(paper_summary)[:3000],
        "current_terms": current_terms,
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
    return {
        "terms": terms[:MAX_ADDITIONAL_TERMS],
        "rationale": llm_result.get("rationale") or "",
        "max_additional_terms": MAX_ADDITIONAL_TERMS,
    }


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


# ── Template Fill workspace ────────────────────────────────────────────────

def _require_assigned_template(session: dict):
    """Return the loaded Template for the session, or raise 400/404."""
    tid = session.get("template_id")
    if not tid:
        raise HTTPException(400, "No template is assigned to this dataset.")
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, f"Template '{tid}' not found.")
    return tpl


def _refresh_conformance(session: dict, tpl) -> list[dict]:
    """Re-run validation, refresh template-derived issues, return the new report."""
    report = validate_against_template(tpl, session.get("columns", []), session.get("metadata", {}))
    _strip_template_issues(session)
    session["template_validation"] = report
    session["issues"].extend(conformance_to_issues(report, tpl.id))
    return report


@template_router.get("/api/{dataset_id}/template/completion")
async def template_completion(dataset_id: str):
    """Return the enriched completion report for the assigned template.

    The shape is documented in CLAUDE.md (Template Fill workspace) — the
    frontend reads ``totals``, ``by_severity``, ``by_section``, and ``fields``
    by name.
    """
    s = _require(dataset_id)
    tpl = _require_assigned_template(s)
    report = validate_against_template(tpl, s.get("columns", []), s.get("metadata", {}))
    s["template_validation"] = report
    completion = build_completion_report(
        tpl,
        s.get("metadata", {}) or {},
        s.get("columns", []) or [],
        s.get("paper_extraction"),
        report,
    )
    return completion


@template_router.post("/api/{dataset_id}/template/fill-from-paper")
async def template_fill_from_paper(dataset_id: str):
    """Bulk-fill missing template fields from session.paper_extraction.

    Writes the proposed values into ``session["metadata"]``, re-runs
    ``validate_against_template`` to refresh conformance + issues, persists
    the session, and returns the list of filled-field records plus the
    new completion report.
    """
    s = _require(dataset_id)
    tpl = _require_assigned_template(s)
    paper = s.get("paper_extraction")
    if not paper:
        raise HTTPException(
            400,
            "No paper extraction is attached to this dataset. Run /api/paper/extract first.",
        )
    current_md = s.get("metadata", {}) or {}
    new_md, filled = fill_from_paper_extraction(tpl, current_md, paper)
    s["metadata"] = new_md
    report = _refresh_conformance(s, tpl)
    _persist(dataset_id, s)
    completion = build_completion_report(tpl, new_md, s.get("columns", []) or [], paper, report)
    return {"filled": filled, "completion": completion}


@template_router.post("/api/{dataset_id}/template/llm-suggest")
async def template_llm_suggest(dataset_id: str, request: Request):
    """Ask the LLM to draft candidate values for missing/partial template fields.

    Body: ``{"field_ids": [...] | null}``. If ``field_ids`` is null or
    omitted, every missing/partial metadata field on the assigned template
    is considered. Calls are batched (at most ``_LLM_BATCH_SIZE`` fields
    per LLM round-trip).

    Returns ``{"suggestions": [{"field_id","value","rationale","confidence"}]}``.
    The endpoint does NOT mutate the session — the frontend reviews
    suggestions and applies accepted ones via PUT /api/metadata/{id}.
    """
    from llm_service import LLMUnavailable, call_haiku, llm_enabled

    if not llm_enabled():
        raise HTTPException(503, "LLM is disabled or unavailable.")

    s = _require(dataset_id)
    tpl = _require_assigned_template(s)

    try:
        body = await request.json()
    except Exception:
        body = {}
    requested_ids = body.get("field_ids") if isinstance(body, dict) else None
    if requested_ids is not None and not isinstance(requested_ids, list):
        raise HTTPException(400, "Field 'field_ids' must be an array of template field IDs or null.")

    metadata = s.get("metadata", {}) or {}
    columns = s.get("columns", []) or []
    paper_extraction = s.get("paper_extraction") or {}
    paper_summary = ""
    if isinstance(paper_extraction, dict):
        paper_summary = str(paper_extraction.get("summary") or "")[:3000]

    # Determine which fields we should draft.
    report = validate_against_template(tpl, columns, metadata)
    entries_by_id = {e["field_id"]: e for e in report if not e.get("is_column_field")}

    if requested_ids:
        requested_set = {str(fid) for fid in requested_ids if isinstance(fid, str)}
        candidate_ids = [req.id for req in tpl.required_metadata if req.id in requested_set]
    else:
        candidate_ids = [
            req.id
            for req in tpl.required_metadata
            if (entries_by_id.get(req.id, {}).get("status") or "missing") != "satisfied"
        ]

    if not candidate_ids:
        return {"suggestions": []}

    tool = {
        "name": "draft_template_fields",
        "description": (
            "Draft concise candidate metadata values for the requested research "
            "reporting fields. Each value must be at most two sentences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_id": {"type": "string"},
                            "value": {"type": "string"},
                            "rationale": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["field_id", "value", "rationale", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["fields"],
            "additionalProperties": False,
        },
    }
    system_prompt = (
        "You are drafting candidate metadata values for a research-reporting "
        "standard (ARRIVE 2.0 and/or PREPARE). Use the provided context "
        "(existing metadata, paper summary, related sibling fields) to write "
        "concise drafts. Every value MUST be at most two sentences and must "
        "be grounded in the context — if there is no supporting information, "
        "return an empty string with a low confidence score and explain why "
        "in the rationale. Confidence is a number between 0 and 1."
    )

    # Batched prompts: chunk candidate ids into groups of _LLM_BATCH_SIZE.
    suggestions: list[dict[str, Any]] = []
    by_id = {req.id: req for req in tpl.required_metadata}

    for start in range(0, len(candidate_ids), _LLM_BATCH_SIZE):
        batch_ids = candidate_ids[start : start + _LLM_BATCH_SIZE]
        prompts = fields_to_llm_prompt(tpl, batch_ids, metadata, columns, paper_summary)

        # Attach paper hints inline so the model sees them per-field.
        paper_arrive = paper_extraction.get("arrive") if isinstance(paper_extraction, dict) else {}
        paper_meta = paper_extraction.get("dataset_metadata") if isinstance(paper_extraction, dict) else {}
        from template_engine import _lookup_paper_value
        for payload in prompts:
            fid = payload["field_id"]
            try:
                val, _src, _status = _lookup_paper_value(fid, paper_arrive or {}, paper_meta or {})
            except Exception:
                val = None
            if val not in (None, "", [], {}):
                rendered = ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
                payload["paper_hint"] = rendered[:480]

        user_message = json.dumps(
            {
                "template_id": tpl.id,
                "template_name": tpl.name,
                "paper_summary": paper_summary,
                "fields": prompts,
            }
        )
        try:
            result = call_haiku(
                system_prompt=system_prompt,
                tool=tool,
                user_message=user_message,
                max_tokens=2048,
            )
        except LLMUnavailable as exc:
            raise HTTPException(503, str(exc))

        for item in result.get("fields") or []:
            fid = str(item.get("field_id") or "").strip()
            if not fid or fid not in by_id:
                continue
            value = str(item.get("value") or "").strip()
            rationale = str(item.get("rationale") or "").strip()
            try:
                confidence = float(item.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            suggestions.append(
                {
                    "field_id": fid,
                    "value": value,
                    "rationale": rationale,
                    "confidence": confidence,
                }
            )

    return {"suggestions": suggestions}


@template_router.post("/api/{dataset_id}/template/extract-from-document")
async def template_extract_from_document(dataset_id: str, file: UploadFile = File(...)):
    """Extract metadata from a supplementary document and propose template fills.

    Runs ``paper_extractor.extract_paper_metadata`` on the uploaded file
    (PDF, ≤ 20 MB), maps the result against the assigned template using
    the same field-lookup logic as ``fill_from_paper_extraction``, and
    returns the proposed fills as *suggestions only*. The session's
    canonical ``paper_extraction`` is left untouched — this endpoint is
    for supplementary documents that the user reviews before applying.
    """
    s = _require(dataset_id)
    tpl = _require_assigned_template(s)

    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(content) > _DOC_MAX_BYTES:
        raise HTTPException(
            413,
            f"Uploaded file is {len(content) // (1024 * 1024):.1f} MB; the limit is 20 MB.",
        )

    from paper_extractor import extract_paper_metadata

    try:
        extraction = extract_paper_metadata(content, file.filename or "document.pdf")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Document extraction failed: {exc}")

    # Map against the template using the same logic as fill_from_paper_extraction,
    # but DO NOT merge into session.metadata.
    _new_md, filled = fill_from_paper_extraction(tpl, {}, extraction)
    suggestions = [
        {
            "field_id": rec["field_id"],
            "value": rec["value"],
            "source": rec.get("source"),
            "arrive_section": rec.get("arrive_section"),
            "prepare_section": rec.get("prepare_section"),
            "severity": rec.get("severity"),
            "rationale": f"Extracted from supplementary document ({file.filename}).",
            "confidence": 0.7,
        }
        for rec in filled
    ]
    return {"suggestions": suggestions}
