import asyncio
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

vcg_router = APIRouter(prefix="/api/vcg", tags=["vcg"])

# Injected by main.py via init_vcg_router()
_sessions: Dict[str, Any] = {}
_save_fn: Optional[Callable] = None
_load_fn: Optional[Callable] = None


def init_vcg_router(sessions: dict, save_fn: Callable, load_fn: Callable) -> None:
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
    return s


def _ensure_vcg(session: dict) -> None:
    if "vcg" not in session:
        from vcg.context_model import DEFAULT_VCG_SESSION
        session["vcg"] = DEFAULT_VCG_SESSION()


def _persist(dataset_id: str, session: dict) -> None:
    if _save_fn:
        _save_fn(dataset_id, session)


# ── Wizard endpoints ────────────────────────────────────────────────────────

@vcg_router.get("/{dataset_id}/wizard-prefill")
async def wizard_prefill(dataset_id: str):
    s = _require(dataset_id)
    from vcg.vcg_wizard import infer_column_roles
    return infer_column_roles(s["columns"], s["table_structure"], s["metadata"])


@vcg_router.put("/{dataset_id}/wizard")
async def save_wizard(dataset_id: str, payload: Dict[str, Any]):
    s = _require(dataset_id)
    _ensure_vcg(s)
    from vcg.vcg_wizard import validate_wizard_payload

    for key in ("column_roles", "vcg_config", "research_context"):
        if key in payload:
            s["vcg"][key].update(payload[key])

    errors = validate_wizard_payload(s["vcg"]["column_roles"], s["columns"], s["df"])
    _persist(dataset_id, s)
    return {"vcg": s["vcg"], "validation_errors": errors}


# ── Chat / orchestrator endpoints ───────────────────────────────────────────

@vcg_router.post("/{dataset_id}/chat/start")
async def chat_start(dataset_id: str):
    s = _require(dataset_id)
    _ensure_vcg(s)
    from vcg.orchestrator import VCGOrchestrator
    msg = VCGOrchestrator(s).start()
    _persist(dataset_id, s)
    return msg


@vcg_router.post("/{dataset_id}/chat/respond")
async def chat_respond(dataset_id: str, body: Dict[str, Any]):
    s = _require(dataset_id)
    _ensure_vcg(s)
    user_message = body.get("message", "")
    from vcg.orchestrator import VCGOrchestrator
    msg = VCGOrchestrator(s).respond(user_message)
    _persist(dataset_id, s)
    return msg


@vcg_router.get("/{dataset_id}/conversation")
async def get_conversation(dataset_id: str):
    s = _require(dataset_id)
    return {"conversation": s.get("vcg", {}).get("conversation", [])}


# ── Generation endpoints ────────────────────────────────────────────────────

@vcg_router.get("/{dataset_id}/suitability")
async def get_suitability(dataset_id: str):
    """Pre-generation suitability check. Returns blocking issues and warnings."""
    s = _require(dataset_id)
    _ensure_vcg(s)
    if "df" not in s or s["df"] is None:
        raise HTTPException(400, "Dataset not loaded. Please upload your CSV again.")

    from vcg.agents.ingestion_agent import DataIngestionAgent
    column_roles = s["vcg"].get("column_roles", {})
    ingestion = DataIngestionAgent().run(s["df"], s["columns"], column_roles)
    suitability = ingestion.get("suitability", {"suitable": False, "blocking_issues": [], "warnings": []})
    return {
        "suitable": suitability.get("suitable", True) and not ingestion.get("blocking_issues"),
        "blocking_issues": ingestion.get("blocking_issues", []) + [
            b["message"] for b in suitability.get("blocking_issues", [])
        ],
        "warnings": [w["message"] for w in suitability.get("warnings", [])] + ingestion.get("warnings", []),
        "n_control": ingestion.get("n_control", 0),
        "available_methods": ingestion.get("available_methods", ["synthetic"]),
    }


@vcg_router.post("/{dataset_id}/generate")
async def generate(dataset_id: str):
    s = _require(dataset_id)
    _ensure_vcg(s)

    if s["vcg"]["vcg_status"] == "running":
        return {"vcg_status": "running", "message": "Already running"}

    s["vcg"]["vcg_status"] = "running"
    s["vcg"]["vcg_error"] = None
    _persist(dataset_id, s)

    from vcg.vcg_engine import run_vcg_pipeline

    async def _run():
        await asyncio.to_thread(run_vcg_pipeline, dataset_id, s, _sessions, _save_fn)

    asyncio.create_task(_run())
    return {"vcg_status": "running", "message": "VCG generation started"}


@vcg_router.get("/{dataset_id}/status")
async def get_status(dataset_id: str):
    s = _require(dataset_id)
    vcg = s.get("vcg", {})
    return {"vcg_status": vcg.get("vcg_status", "not_started"), "vcg_error": vcg.get("vcg_error")}


@vcg_router.get("/{dataset_id}/results")
async def get_results(dataset_id: str):
    s = _require(dataset_id)
    vcg = s.get("vcg", {})
    status = vcg.get("vcg_status", "not_started")
    if status != "done":
        raise HTTPException(400, f"VCG not ready. Status: {status}")
    results = {k: v for k, v in (vcg.get("vcg_results") or {}).items() if k != "vcg_csv"}
    return results


# ── Export endpoints ────────────────────────────────────────────────────────

@vcg_router.get("/{dataset_id}/export/vcg-csv")
async def export_vcg_csv(dataset_id: str):
    s = _require(dataset_id)
    csv_text = ((s.get("vcg") or {}).get("vcg_results") or {}).get("vcg_csv", "")
    if not csv_text:
        raise HTTPException(400, "No VCG CSV available. Run generation first.")
    return Response(
        csv_text.encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="virtual_control_group.csv"'},
    )


@vcg_router.get("/{dataset_id}/export/vcg-report")
async def export_vcg_report(dataset_id: str):
    s = _require(dataset_id)
    report = ((s.get("vcg") or {}).get("vcg_results") or {}).get("stat_report", "No report available.")
    return Response(
        report.encode(),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="vcg_statistical_report.md"'},
    )
