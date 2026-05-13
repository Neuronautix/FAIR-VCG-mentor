import json
import logging
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from csv_profiler import profile_csv
from entity_detector import detect_entity_structure
from export_engine import (
    generate_cleaned_csv,
    generate_csvw,
    generate_data_dictionary,
    generate_fair_report,
    generate_frictionless,
    generate_jsonld,
    generate_rocrate_zip,
)
from fair_engine import compute_fair_score, detect_issues
from uri_suggester import suggest_uris
from arrive_engine import generate_arrive_zip
from template_store import (
    apply_template,
    load_template,
    low_confidence_columns,
    record_corrections,
    save_template,
)

app = FastAPI(title="FAIR CSV Mentor API", version="1.0.0")

from vcg.vcg_router import vcg_router, init_vcg_router  # noqa: E402

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
    session["original_bytes"] = original_bytes
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
            s["import_info"], s["columns"], s["table_structure"], s["metadata"], s["issues"]
        )
    if "uri_suggestions" not in s:
        s["uri_suggestions"] = suggest_uris(s["columns"], s["metadata"], s["import_info"])
    return s


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "data.csv"
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
    sessions[dataset_id] = {
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
        "inference_metrics": {
            "total_updates": 0,
            "type_corrections": 0,
            "label_corrections": 0,
            "unit_corrections": 0,
        },
    }
    _save_session(dataset_id, sessions[dataset_id])

    return {
        "dataset_id": dataset_id,
        "import_info": result["import_info"],
        "columns": result["columns"],
        "table_structure": table_structure,
        "issues": issues,
        "template_applied": template_applied,
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
    s.pop("uri_suggestions", None)

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
        s["import_info"], s["columns"], s["table_structure"], s["metadata"], s["issues"]
    )
    s["fair_score"] = score
    return score


@app.get("/api/fair-score/{dataset_id}/llm")
async def get_llm_fair_score(dataset_id: str):
    from llm_fair_scorer import run_llm_fair_score
    s = _require(dataset_id)
    arrive_data = s.get("metadata", {}).get("arrive")
    try:
        result = run_llm_fair_score(
            s["import_info"], s["columns"], s["metadata"], s["issues"], arrive_data
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("LLM FAIR score failed: %s", exc)
        raise HTTPException(503, "LLM assessment temporarily unavailable.")
    return result


@app.get("/api/uris/{dataset_id}")
async def get_uri_suggestions(dataset_id: str):
    s = _require(dataset_id)
    uris = suggest_uris(s["columns"], s["metadata"], s["import_info"])
    s["uri_suggestions"] = uris
    return uris


# ── Export endpoints ────────────────────────────────────────────────────────

@app.get("/api/export/{dataset_id}/cleaned-csv")
async def export_cleaned_csv(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_cleaned_csv(s["df"], s["columns"], s["metadata"])
    return Response(content, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="cleaned_data.csv"'})


@app.get("/api/export/{dataset_id}/data-dictionary")
async def export_data_dictionary(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_data_dictionary(s["columns"], s["metadata"])
    return Response(content, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="data_dictionary.csv"'})


@app.get("/api/export/{dataset_id}/frictionless")
async def export_frictionless(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_frictionless(s["df"], s["columns"], s["metadata"], s["import_info"])
    return Response(content, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="datapackage.json"'})


@app.get("/api/export/{dataset_id}/csvw")
async def export_csvw(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_csvw(s["columns"], s["metadata"], s["import_info"])
    return Response(content, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="csvw_metadata.json"'})


@app.get("/api/export/{dataset_id}/jsonld")
async def export_jsonld(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_jsonld(s["columns"], s["metadata"], s["import_info"], s["uri_suggestions"])
    return Response(content, media_type="application/ld+json",
                    headers={"Content-Disposition": 'attachment; filename="metadata.jsonld"'})


@app.get("/api/export/{dataset_id}/report")
async def export_report(dataset_id: str):
    s = _prepare_exports(dataset_id)
    content = generate_fair_report(
        s["import_info"], s["columns"], s["table_structure"],
        s["fair_score"], s["metadata"], s["issues"],
    )
    return Response(content, media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="fair_readiness_report.md"'})


@app.get("/api/export/{dataset_id}/rocrate")
async def export_rocrate(dataset_id: str):
    s = _prepare_exports(dataset_id)
    cleaned = generate_cleaned_csv(s["df"], s["columns"], s["metadata"])
    data_dict = generate_data_dictionary(s["columns"], s["metadata"])
    frictionless = generate_frictionless(s["df"], s["columns"], s["metadata"], s["import_info"])
    csvw = generate_csvw(s["columns"], s["metadata"], s["import_info"])
    jsonld = generate_jsonld(s["columns"], s["metadata"], s["import_info"], s["uri_suggestions"])
    report = generate_fair_report(
        s["import_info"], s["columns"], s["table_structure"],
        s["fair_score"], s["metadata"], s["issues"],
    )
    zip_bytes = generate_rocrate_zip(
        s["original_bytes"], cleaned, data_dict, frictionless, csvw, jsonld, report,
        s["metadata"], s["import_info"], s["uri_suggestions"],
    )
    return Response(zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="ro-crate.zip"'})


@app.get("/api/export/{dataset_id}/arrive")
async def export_arrive(dataset_id: str):
    s = _prepare_exports(dataset_id)
    vcg_results = (s.get("vcg") or {}).get("vcg_results") or {}
    # Strip large binary fields before passing to arrive engine
    vcg_safe = {k: v for k, v in vcg_results.items() if k not in ("vcg_csv", "diagnostic_plots", "per_endpoint_plots", "stat_report")}
    zip_bytes = generate_arrive_zip(
        s["import_info"], s["columns"], s["metadata"],
        s["table_structure"], s["issues"], vcg_safe,
    )
    return Response(zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="arrive_guidelines.zip"'})


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


init_vcg_router(sessions, _save_session, _load_session)
app.include_router(vcg_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
