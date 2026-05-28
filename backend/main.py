import json
import logging
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from csv_profiler import profile_csv
from entity_detector import detect_entity_structure
from export_engine import (
    generate_cleaned_csv,
    generate_data_dictionary,
    generate_fair_report_md,
    generate_arrive_report_md,
    generate_prepare_report_md,
)
from fair_engine import compute_fair_score, detect_issues
from template_store import (
    apply_template,
    load_template,
    low_confidence_columns,
    record_corrections,
    save_template,
)
from prepare_engine import generate_prepare_zip
from arrive_engine import generate_arrive_zip

app = FastAPI(title="FAIR CSV Mentor API", version="1.0.0")

from template_router import template_router, init_template_router  # noqa: E402
from template_engine import (  # noqa: E402
    conformance_to_issues,
    get_template,
    load_templates,
    suggest_templates,
    validate_against_template,
)

_cors_origins_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
)
_cors_origins = [o.strip() for o in _cors_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
_MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "32")) * 1024 * 1024
_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# In-memory session store (sessions are also persisted to SQLite)
sessions: Dict[str, Dict[str, Any]] = {}

# ── SQLite session persistence ───────────────────────────────────────────────

_DB_PATH = os.getenv("SESSION_DB", "sessions.db")


def _init_db() -> None:
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions "
            "(dataset_id TEXT PRIMARY KEY, session_json TEXT NOT NULL, "
            "original_bytes BLOB NOT NULL, updated_at REAL NOT NULL)"
        )


_init_db()


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "item"):   # numpy scalar
        return obj.item()
    if hasattr(obj, "tolist"):  # numpy array
        return obj.tolist()
    return str(obj)


def _save_session(dataset_id: str, session: Dict[str, Any]) -> None:
    data = {k: v for k, v in session.items() if k not in ("df", "original_bytes")}
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (dataset_id, session_json, original_bytes, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (dataset_id, json.dumps(data, default=_json_default), session["original_bytes"], time.time()),
        )


def _load_session(dataset_id: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(_DB_PATH) as conn:
        row = conn.execute(
            "SELECT session_json, original_bytes FROM sessions WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
    if not row:
        return None
    session = json.loads(row[0])
    original_bytes = row[1]
    session["original_bytes"] = original_bytes or b""
    # Assessment-only sessions have no CSV bytes — skip df reconstruction.
    if session.get("import_info", {}).get("assessment_only"):
        session["df"] = pd.DataFrame()
        return session
    if not original_bytes:
        logger.error("No original_bytes for dataset %s", dataset_id)
        return None
    filename = session.get("import_info", {}).get("filename", "data.csv")
    try:
        profile_result = profile_csv(original_bytes, filename)
        session["df"] = profile_result["df"]
    except Exception as exc:
        logger.error("Failed to reconstruct df for dataset %s: %s", dataset_id, exc)
        return None
    return session


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require(dataset_id: str) -> Dict[str, Any]:
    s = sessions.get(dataset_id)
    if not s:
        s = _load_session(dataset_id)
        if not s:
            raise HTTPException(404, "Dataset not found. Please upload your CSV again.")
        sessions[dataset_id] = s
    return s


def _prepare_exports(dataset_id: str) -> Dict[str, Any]:
    s = _require(dataset_id)
    if "fair_score" not in s:
        s["fair_score"] = compute_fair_score(
            s["import_info"], s["columns"], s["table_structure"], s["metadata"], s["issues"],
            template_validation=s.get("template_validation", []),
        )
    return s


# ── Error handler ─────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Suppress stack traces in production."""
    if _ENVIRONMENT == "production":
        logger.error("Unhandled error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred. Please try again."},
        )
    raise exc


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    # Enforce upload size limit
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File too large. Maximum allowed size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    filename = file.filename or "data.csv"

    # Enforce file type restriction
    import os as _os
    ext = _os.path.splitext(filename.lower())[1]
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            415,
            f"Unsupported file type '{ext}'. Only .csv, .xlsx, and .xls files are accepted.",
        )

    if filename.lower().endswith((".xlsx", ".xls")):
        try:
            import io as _io
            df_excel = pd.read_excel(_io.BytesIO(content))
            content = df_excel.to_csv(index=False).encode("utf-8")
            filename = filename.rsplit(".", 1)[0] + ".csv"
        except Exception as exc:
            raise HTTPException(400, f"Could not read Excel file: {exc}")

    try:
        result = profile_csv(content, filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    df = result.pop("df")
    result.pop("content")

    table_structure = detect_entity_structure(df, result["columns"])
    issues = detect_issues(result["import_info"], result["columns"], table_structure)

    # Check for duplicate IDs using actual data
    for id_col in table_structure["detected_identifiers"]:
        if id_col in df.columns and df[id_col].duplicated().any():
            dup_count = int(df[id_col].duplicated().sum())
            issues.append({
                "id": f"duplicate_ids_{id_col}",
                "severity": "medium",
                "category": "quality",
                "column": id_col,
                "problem": f'Column "{id_col}" has {dup_count} duplicate value(s).',
                "why_it_matters": (
                    "Duplicated identifiers may indicate repeated measures, data entry errors, "
                    "or an unintended merge. Without understanding why IDs repeat, data cannot "
                    "be reliably linked across datasets."
                ),
                "suggested_fix": (
                    "If this is repeated-measures data, document that in the metadata. "
                    "If IDs should be unique, investigate and correct the duplicates."
                ),
            })

    # Stage 2: auto-apply a previously confirmed mapping if the dataset
    # signature matches one we've already seen.
    signature = result["import_info"].get("signature")
    template = load_template(_DB_PATH, signature) if signature else None
    template_applied = 0
    if template:
        template_applied = apply_template(result["columns"], template["mappings"])

    dataset_id = str(uuid.uuid4())
    session = {
        "dataset_id": dataset_id,
        "import_info": result["import_info"],
        "columns": result["columns"],
        "table_structure": table_structure,
        "issues": issues,
        "metadata": {"base_uri": "https://your-lab.org"},
        "df": df,
        "original_bytes": content,
        "template_signature": signature,
        "template_applied": template_applied,
        "template_id": None,
        "template_candidates": [],
        "template_validation": [],
        "inference_metrics": {
            "total_updates": 0,
            "type_corrections": 0,
            "label_corrections": 0,
            "unit_corrections": 0,
        },
    }

    try:
        loaded = load_templates()
        candidates = suggest_templates(loaded, session["columns"], session["metadata"])
        session["template_candidates"] = candidates
        if candidates and candidates[0]["score"] >= 0.9:
            tid = candidates[0]["id"]
            tpl = get_template(tid)
            if tpl is not None:
                report = validate_against_template(tpl, session["columns"], session["metadata"])
                session["template_id"] = tid
                session["template_validation"] = report
                session["issues"].extend(conformance_to_issues(report, tid))
    except Exception as exc:
        logger.warning("Template auto-match failed for dataset %s: %s", dataset_id, exc)

    sessions[dataset_id] = session
    _save_session(dataset_id, sessions[dataset_id])

    return {
        "dataset_id": dataset_id,
        "import_info": result["import_info"],
        "columns": result["columns"],
        "table_structure": table_structure,
        "issues": session["issues"],
        "template_applied": template_applied,
        "template_id": session["template_id"],
        "template_candidates": session["template_candidates"],
        "low_confidence_columns": low_confidence_columns(result["columns"]),
    }


@app.get("/api/profile/{dataset_id}")
async def get_profile(dataset_id: str):
    s = _require(dataset_id)
    return {
        "import_info": s["import_info"],
        "columns": s["columns"],
        "table_structure": s["table_structure"],
    }


@app.get("/api/issues/{dataset_id}")
async def get_issues(dataset_id: str):
    s = _require(dataset_id)
    return {"issues": s["issues"]}


@app.put("/api/columns/{dataset_id}")
async def update_columns(dataset_id: str, column_updates: List[Dict[str, Any]]):
    s = _require(dataset_id)
    record_corrections(s, column_updates)
    updates_by_name = {u["name"]: u for u in column_updates}
    for col in s["columns"]:
        if col["name"] in updates_by_name:
            col.update(updates_by_name[col["name"]])

    # Invalidate cached score so it reflects the new column metadata.
    s.pop("fair_score", None)

    # Recompute issues after column edits
    s["issues"] = detect_issues(s["import_info"], s["columns"], s["table_structure"])
    _save_session(dataset_id, s)
    return {
        "columns": s["columns"],
        "issues": s["issues"],
        "low_confidence_columns": low_confidence_columns(s["columns"]),
        "inference_metrics": s.get("inference_metrics", {}),
    }


@app.get("/api/templates/{dataset_id}")
async def get_template_info(dataset_id: str):
    s = _require(dataset_id)
    signature = s.get("template_signature") or s.get("import_info", {}).get("signature")
    saved = load_template(_DB_PATH, signature) if signature else None
    return {
        "signature": signature,
        "exists": saved is not None,
        "applied": s.get("template_applied", 0),
        "source_filename": (saved or {}).get("source_filename"),
        "updated_at": (saved or {}).get("updated_at"),
        "low_confidence_columns": low_confidence_columns(s["columns"]),
        "inference_metrics": s.get("inference_metrics", {}),
    }


@app.post("/api/templates/{dataset_id}")
async def save_template_for_dataset(dataset_id: str):
    s = _require(dataset_id)
    signature = s.get("template_signature") or s.get("import_info", {}).get("signature")
    if not signature:
        raise HTTPException(400, "Dataset has no signature; cannot save template.")
    result = save_template(
        _DB_PATH,
        signature,
        s["columns"],
        source_filename=s.get("import_info", {}).get("filename"),
    )
    return result


@app.get("/api/metadata/{dataset_id}")
async def get_metadata(dataset_id: str):
    s = _require(dataset_id)
    return {"metadata": s["metadata"]}


@app.put("/api/metadata/{dataset_id}")
async def save_metadata(dataset_id: str, metadata: Dict[str, Any]):
    s = _require(dataset_id)
    s["metadata"].update(metadata)
    _save_session(dataset_id, s)
    return {"metadata": s["metadata"]}


@app.get("/api/fair-score/{dataset_id}")
async def get_fair_score(dataset_id: str):
    s = _require(dataset_id)
    score = compute_fair_score(
        s["import_info"], s["columns"], s["table_structure"], s["metadata"], s["issues"],
        template_validation=s.get("template_validation", []),
    )
    s["fair_score"] = score
    return score


# ── HITL (human-in-the-loop) suggestion queue ───────────────────────────────

@app.get("/api/llm/status")
async def llm_status():
    import openai_service
    anthropic_available = bool(os.getenv("ANTHROPIC_API_KEY"))
    openai_available = openai_service.is_configured()
    return {
        "enabled": anthropic_available or openai_available,
        "provider": "anthropic" if anthropic_available else ("openai" if openai_available else None),
        "model": openai_service.OPENAI_MODEL if openai_available else None,
    }


@app.get("/api/hitl/{dataset_id}/suggestions")
async def list_hitl(dataset_id: str, status: Optional[str] = None, category: Optional[str] = None):
    from hitl import list_suggestions
    s = _require(dataset_id)
    return {"suggestions": list_suggestions(s, status=status, category=category)}


@app.post("/api/hitl/{dataset_id}/suggestions/{suggestion_id}/approve")
async def approve_hitl(dataset_id: str, suggestion_id: str):
    from hitl import approve_and_apply
    s = _require(dataset_id)
    try:
        suggestion, result = approve_and_apply(s, suggestion_id)
    except KeyError:
        raise HTTPException(404, "Suggestion not found.")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _save_session(dataset_id, s)
    return {"suggestion": suggestion, "result": result}


@app.post("/api/hitl/{dataset_id}/suggestions/{suggestion_id}/reject")
async def reject_hitl(dataset_id: str, suggestion_id: str):
    from hitl import update_status
    s = _require(dataset_id)
    try:
        suggestion = update_status(s, suggestion_id, "rejected")
    except KeyError:
        raise HTTPException(404, "Suggestion not found.")
    _save_session(dataset_id, s)
    return {"suggestion": suggestion}


@app.put("/api/hitl/{dataset_id}/suggestions/{suggestion_id}")
async def edit_hitl(dataset_id: str, suggestion_id: str, body: Dict[str, Any]):
    from hitl import edit_payload
    s = _require(dataset_id)
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Body must include a 'payload' object.")
    try:
        suggestion = edit_payload(s, suggestion_id, payload)
    except KeyError:
        raise HTTPException(404, "Suggestion not found.")
    _save_session(dataset_id, s)
    return {"suggestion": suggestion}


# ── Vocabulary endpoints ────────────────────────────────────────────────────

@app.get("/api/vocabulary/{dataset_id}")
async def get_vocabulary(dataset_id: str):
    from vocabulary import ensure_vocabulary
    s = _require(dataset_id)
    return ensure_vocabulary(s)


@app.post("/api/vocabulary/{dataset_id}/validate")
async def validate_vocabulary(dataset_id: str):
    """Flip vocabulary.validated → True and bump version (HITL stale-marks older proposals)."""
    from vocabulary import validate
    from hitl import mark_stale_for_version
    s = _require(dataset_id)
    vocab = validate(s)
    marked = mark_stale_for_version(s, vocab["version"])
    _save_session(dataset_id, s)
    return {"vocabulary": vocab, "marked_stale": marked}


# ── Export endpoints ────────────────────────────────────────────────────────

@app.get("/api/export/{dataset_id}/cleaned-csv")
async def export_cleaned_csv(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_cleaned_csv(s["df"], s["columns"], s["metadata"])
    return Response(content.encode("utf-8") if isinstance(content, str) else content,
                    media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="cleaned_data.csv"'})


@app.get("/api/export/{dataset_id}/data-dictionary")
async def export_data_dictionary(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_data_dictionary(s["columns"], s["metadata"])
    return Response(content.encode("utf-8") if isinstance(content, str) else content,
                    media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="data_dictionary.csv"'})


@app.get("/api/export/{dataset_id}/fair-report")
async def export_fair_report(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_fair_report_md(s)
    return Response(content, media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="fair_readiness_report.md"'})


@app.get("/api/export/{dataset_id}/arrive-report")
async def export_arrive_report(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_arrive_report_md(s)
    return Response(content, media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="arrive_conformance_report.md"'})


@app.get("/api/export/{dataset_id}/prepare-report")
async def export_prepare_report(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_prepare_report_md(s)
    return Response(content, media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="prepare_readiness_report.md"'})


@app.get("/api/export/{dataset_id}/arrive")
async def export_arrive(dataset_id: str):
    s = _prepare_exports(dataset_id)
    zip_bytes = generate_arrive_zip(
        s["import_info"], s["columns"], s["metadata"],
        s["table_structure"], s["issues"], {},
    )
    return Response(zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="arrive_guidelines.zip"'})


@app.get("/api/export/{dataset_id}/prepare")
async def export_prepare(dataset_id: str):
    s = _prepare_exports(dataset_id)
    zip_bytes = generate_prepare_zip(
        s.get("metadata", {}),
        s.get("columns", []),
        s.get("template_validation", []),
        s.get("template_id"),
    )
    return Response(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="prepare_study_plan.zip"'},
    )


# Removed export formats return 404
@app.get("/api/export/{dataset_id}/{export_type}")
async def export_unsupported(dataset_id: str, export_type: str):
    supported = {"cleaned-csv", "data-dictionary", "fair-report", "arrive-report",
                 "prepare-report", "arrive", "prepare"}
    if export_type not in supported:
        raise HTTPException(404, f"Export type '{export_type}' is not available in this version.")
    raise HTTPException(500, "Unexpected routing error.")


# ── Paper import endpoints ──────────────────────────────────────────────────

@app.post("/api/paper/extract")
async def extract_paper(file: UploadFile = File(...)):
    from paper_extractor import extract_paper_metadata
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    filename = file.filename or "paper.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported. Please upload a PDF.")
    try:
        result = extract_paper_metadata(content, filename)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return result


@app.post("/api/paper/extract/stream")
async def stream_paper_extract(file: UploadFile = File(...)):
    import asyncio as _asyncio
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    filename = file.filename or "paper.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    async def generate():
        from paper_extractor import extract_paper_metadata
        yield f"data: {json.dumps({'type': 'status', 'message': 'Sending PDF to Claude…'})}\n\n"

        task = _asyncio.create_task(_asyncio.to_thread(extract_paper_metadata, content, filename))

        status_messages = [
            "Analysing paper structure…",
            "Extracting study metadata…",
            "Checking ARRIVE compliance…",
            "Finalising extraction…",
        ]
        idx = 0
        while True:
            try:
                result = await _asyncio.wait_for(_asyncio.shield(task), timeout=7.0)
                yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
                return
            except _asyncio.TimeoutError:
                msg = status_messages[idx % len(status_messages)]
                yield f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"
                idx += 1
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                return

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/paper/doi")
async def fetch_paper_by_doi(body: Dict[str, Any]):
    from doi_fetcher import fetch_doi_metadata
    doi = (body.get("doi") or "").strip()
    if not doi:
        raise HTTPException(400, "doi field is required")
    try:
        result = fetch_doi_metadata(doi)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return result


@app.put("/api/paper/{dataset_id}/extraction")
async def store_paper_extraction(dataset_id: str, body: Dict[str, Any]):
    s = _require(dataset_id)
    s["paper_extraction"] = body
    _save_session(dataset_id, s)
    return {"stored": True}


@app.get("/api/paper/{dataset_id}/extraction")
async def get_stored_paper_extraction(dataset_id: str):
    s = _require(dataset_id)
    stored = s.get("paper_extraction")
    if not stored:
        raise HTTPException(404, "No paper extraction stored for this dataset.")
    return stored


# ── Free-text protocol import ────────────────────────────────────────────────

@app.post("/api/import/free-text")
async def import_free_text(body: Dict[str, Any]):
    """Extract PREPARE/ARRIVE metadata from free text using available AI provider.

    Accepts plain text protocol notes or study plans. Never sends raw dataset rows.
    """
    import llm_service
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    if len(text) > 20000:
        raise HTTPException(400, "Text too long (max 20,000 characters)")

    if not llm_service.llm_enabled():
        raise HTTPException(400, "No AI provider configured. Add an OpenAI key in Settings.")

    from paper_extractor import extract_from_text
    try:
        result = extract_from_text(text)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    return result


# ── Assessment-only session (no CSV required) ────────────────────────────────

@app.post("/api/assessment-only/start")
async def start_assessment_only(body: Dict[str, Any]):
    """Start an ARRIVE/PREPARE assessment session without a dataset.

    Returns a dataset_id that can be used to fill ARRIVE/PREPARE templates and
    generate reports without uploading a CSV file.
    """
    dataset_id = str(uuid.uuid4())
    session: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "import_info": {
            "filename": body.get("title") or "No dataset",
            "n_rows": 0,
            "n_columns": 0,
            "encoding": None,
            "delimiter": None,
            "has_header": True,
            "empty_columns": [],
            "duplicate_columns": [],
            "malformed_rows": [],
            "assessment_only": True,
        },
        "columns": [],
        "table_structure": {
            "table_shape": "assessment_only",
            "row_represents": "n/a",
            "primary_entity": "n/a",
            "secondary_entity": None,
            "detected_identifiers": [],
            "detected_measurements": [],
            "detected_categoricals": [],
            "detected_time_vars": [],
        },
        "issues": [],
        "metadata": {
            "title": body.get("title") or "",
            "description": body.get("description") or "",
            "base_uri": "https://your-lab.org",
        },
        "original_bytes": b"",
        "template_id": None,
        "template_candidates": [],
        "template_validation": [],
        "template_signature": None,
        "template_applied": 0,
        "inference_metrics": {
            "total_updates": 0,
            "type_corrections": 0,
            "label_corrections": 0,
            "unit_corrections": 0,
        },
    }
    sessions[dataset_id] = session
    _save_session(dataset_id, session)
    return {"dataset_id": dataset_id, "assessment_only": True}


# ── Demo preload session ─────────────────────────────────────────────────────

@app.post("/api/demo/start")
async def start_demo():
    """Create a fully pre-filled demo session from Huzard et al. (2025).

    No API key required — all metadata is hardcoded from the publication.
    Includes a representative CSV dataset and ARRIVE-PREPARE crosswalk
    template pre-assigned and validated.
    """
    from demo_preload import DEMO_CSV, DEMO_FILENAME, DEMO_METADATA

    # Profile the sample CSV
    try:
        result = profile_csv(DEMO_CSV, DEMO_FILENAME)
    except Exception as exc:
        raise HTTPException(500, f"Demo CSV profiling failed: {exc}")

    df = result.pop("df")
    result.pop("content")

    table_structure = detect_entity_structure(df, result["columns"])
    issues = detect_issues(result["import_info"], result["columns"], table_structure)

    dataset_id = str(uuid.uuid4())
    session: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "import_info": {**result["import_info"], "demo": True},
        "columns": result["columns"],
        "table_structure": table_structure,
        "issues": issues,
        "metadata": {**DEMO_METADATA, "base_uri": "https://igf.cnrs.fr"},
        "df": df,
        "original_bytes": DEMO_CSV,
        "template_signature": None,
        "template_applied": 0,
        "template_id": None,
        "template_candidates": [],
        "template_validation": [],
        "inference_metrics": {"total_updates": 0, "type_corrections": 0,
                               "label_corrections": 0, "unit_corrections": 0},
    }

    # Auto-assign the ARRIVE-PREPARE crosswalk template
    try:
        tpl = get_template("arrive-prepare-crosswalk-v1")
        if tpl is not None:
            report = validate_against_template(tpl, session["columns"], session["metadata"])
            session["template_id"] = "arrive-prepare-crosswalk-v1"
            session["template_validation"] = report
            session["issues"].extend(conformance_to_issues(report, "arrive-prepare-crosswalk-v1"))
    except Exception as exc:
        logger.warning("Demo template assignment failed: %s", exc)

    sessions[dataset_id] = session
    _save_session(dataset_id, session)

    return {
        "dataset_id": dataset_id,
        "demo": True,
        "import_info": session["import_info"],
        "columns": session["columns"],
        "table_structure": table_structure,
        "issues": session["issues"],
        "template_id": session["template_id"],
        "template_candidates": session["template_candidates"],
        "low_confidence_columns": low_confidence_columns(result["columns"]),
    }


# ── OpenAI settings endpoints ────────────────────────────────────────────────

@app.post("/api/settings/openai-key")
async def store_openai_key(body: Dict[str, Any]):
    """Store OpenAI API key in memory only — never persisted to disk or DB."""
    import openai_service
    key = (body.get("api_key") or "").strip()
    if not key:
        raise HTTPException(400, "api_key field is required and must not be empty.")
    openai_service.set_key(key)
    return {"stored": True}


@app.get("/api/settings/openai-key/status")
async def openai_key_status():
    """Returns whether a key is configured and the model name — never the key itself."""
    import openai_service
    return openai_service.get_status()


@app.delete("/api/settings/openai-key")
async def clear_openai_key():
    """Remove the stored OpenAI API key from memory."""
    import openai_service
    openai_service.clear_key()
    return {"cleared": True}


@app.post("/api/settings/openai-key/test")
async def test_openai_key():
    """Test the stored OpenAI key with a minimal API call."""
    import openai_service
    if not openai_service.is_configured():
        raise HTTPException(400, "No OpenAI API key is configured. POST /api/settings/openai-key first.")
    result = openai_service.test_connection()
    return result


# ── AI suggestion endpoints ──────────────────────────────────────────────────

@app.post("/api/ai/suggest-metadata/{dataset_id}")
async def ai_suggest_metadata(dataset_id: str, request: Request):
    """Suggest dataset title/description improvements via OpenAI.

    ?preview=true returns what would be sent to OpenAI without calling the API.
    Never sends raw dataset rows — only title, description, and issue summaries.
    """
    import openai_service
    preview = request.query_params.get("preview", "").lower() in ("1", "true", "yes")

    if not openai_service.is_configured() and not preview:
        raise HTTPException(400, "OpenAI API key is not configured. Go to Settings to add your key.")

    s = _require(dataset_id)
    metadata = s.get("metadata", {})
    issues = s.get("issues", [])

    # Build the preview of what will be sent
    issue_summary = [
        {"category": i.get("category", ""), "severity": i.get("severity", ""), "problem": i.get("problem", "")}
        for i in issues[:10]
    ]
    sent_fields = {
        "title": metadata.get("title"),
        "description": metadata.get("description"),
        "issues_shown": len(issue_summary),
        "issue_summary": issue_summary,
    }

    if preview:
        return {
            "preview": {
                "sent_fields": sent_fields,
                "note": "Only dataset title, description, and issue category/severity/problem are sent. Raw data rows are never included.",
            }
        }

    try:
        suggestions = openai_service.suggest_dataset_metadata(
            metadata.get("title"),
            metadata.get("description"),
            issues,
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"suggestions": suggestions}


@app.post("/api/ai/suggest-columns/{dataset_id}")
async def ai_suggest_columns(dataset_id: str, request: Request):
    """Suggest column descriptions via OpenAI.

    Sends only column name, data type, and first 3 sample values.
    ?preview=true returns what would be sent without calling the API.
    """
    import openai_service
    preview = request.query_params.get("preview", "").lower() in ("1", "true", "yes")

    if not openai_service.is_configured() and not preview:
        raise HTTPException(400, "OpenAI API key is not configured. Go to Settings to add your key.")

    s = _require(dataset_id)
    columns = s.get("columns", [])

    # Only send name, type, first 3 sample values — never full rows
    column_samples = [
        {
            "name": col.get("name", ""),
            "data_type": col.get("data_type", ""),
            "sample_values": (col.get("sample_values") or [])[:3],
        }
        for col in columns
    ]

    if preview:
        return {
            "preview": {
                "sent_fields": column_samples,
                "note": "Only column name, data type, and first 3 sample values are sent per column. Full dataset rows are never included.",
            }
        }

    try:
        suggestions = openai_service.suggest_column_descriptions(column_samples)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"suggestions": suggestions}


@app.post("/api/ai/suggest-checklist/{dataset_id}")
async def ai_suggest_checklist(dataset_id: str, request: Request):
    """Generate a prioritised improvement checklist via OpenAI.

    Sends only FAIR score breakdown and issue categories — never raw data.
    ?preview=true returns what would be sent without calling the API.
    """
    import openai_service
    preview = request.query_params.get("preview", "").lower() in ("1", "true", "yes")

    if not openai_service.is_configured() and not preview:
        raise HTTPException(400, "OpenAI API key is not configured. Go to Settings to add your key.")

    s = _require(dataset_id)
    fair_score = s.get("fair_score") or compute_fair_score(
        s["import_info"], s["columns"], s["table_structure"], s["metadata"], s["issues"],
        template_validation=s.get("template_validation", []),
    )
    issues = s.get("issues", [])
    arrive_issues = [i for i in issues if i.get("category") == "template_compliance"
                     and "arrive" in (i.get("id") or "").lower()]
    prepare_issues = [i for i in issues if i.get("category") == "template_compliance"
                      and "prepare" in (i.get("id") or "").lower()]

    score_summary = {
        "total": fair_score.get("fair_score"),
        "findable": {"score": fair_score.get("findable", {}).get("score"), "max": fair_score.get("findable", {}).get("max_score")},
        "accessible": {"score": fair_score.get("accessible", {}).get("score"), "max": fair_score.get("accessible", {}).get("max_score")},
        "interoperable": {"score": fair_score.get("interoperable", {}).get("score"), "max": fair_score.get("interoperable", {}).get("max_score")},
        "reusable": {"score": fair_score.get("reusable", {}).get("score"), "max": fair_score.get("reusable", {}).get("max_score")},
    }
    arrive_summary = [{"field_id": i.get("id", ""), "severity": i.get("severity", "")} for i in arrive_issues[:10]]
    prepare_summary = [{"field_id": i.get("id", ""), "severity": i.get("severity", "")} for i in prepare_issues[:10]]

    if preview:
        return {
            "preview": {
                "sent_fields": {
                    "fair_score_breakdown": score_summary,
                    "arrive_gaps_shown": len(arrive_summary),
                    "prepare_gaps_shown": len(prepare_summary),
                },
                "note": "Only FAIR score breakdown and issue categories are sent. Raw data rows are never included.",
            }
        }

    try:
        checklist_md = openai_service.suggest_improvement_checklist(
            fair_score, arrive_issues, prepare_issues
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"checklist": checklist_md}


init_template_router(sessions, _save_session, _load_session)
app.include_router(template_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
