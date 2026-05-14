import asyncio
import os
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

vcg_router = APIRouter(prefix="/api/vcg", tags=["vcg"])


def _find_column_by_pattern(pattern: str, columns: List[Dict[str, Any]]) -> Optional[str]:
    """Case-insensitive substring match between pattern and each column['name']."""
    if not pattern:
        return None
    p = pattern.lower()
    for col in columns:
        name = str(col.get("name") or "")
        if p in name.lower():
            return name
    return None


def _apply_template_defaults(
    roles_dict: Dict[str, Any],
    template: Any,
    columns: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Overlay template.vcg_defaults onto the heuristic prefill dict.

    Adds `template_locked` (list of field names sourced from the template),
    `clustering_unit` + `clustering_warning` when clustering is declared,
    and may set `method` and `template_id`.
    """
    locked: List[str] = []
    column_roles = roles_dict.setdefault("column_roles", {})

    if template is None or template.vcg_defaults is None:
        roles_dict.setdefault("template_locked", [])
        return roles_dict

    defaults = template.vcg_defaults

    if defaults.treatment_col:
        resolved = _find_column_by_pattern(defaults.treatment_col, columns)
        if resolved:
            column_roles["treatment_col"] = resolved
            locked.append("treatment_col")

    if defaults.control_value:
        column_roles["control_value"] = defaults.control_value
        locked.append("control_value")

    if defaults.treatment_value:
        column_roles["treatment_value"] = defaults.treatment_value
        locked.append("treatment_value")

    outcome_spec = defaults.outcome_cols_from
    resolved_outcomes: List[str] = []
    if outcome_spec is not None:
        if isinstance(outcome_spec, list):
            for pat in outcome_spec:
                m = _find_column_by_pattern(str(pat), columns)
                if m and m not in resolved_outcomes:
                    resolved_outcomes.append(m)
        elif isinstance(outcome_spec, str):
            spec = outcome_spec.strip()
            if spec.lower() == "measurement":
                for col in columns:
                    if col.get("inferred_type") == "measurement":
                        nm = str(col.get("name"))
                        if nm and nm not in resolved_outcomes:
                            resolved_outcomes.append(nm)
            elif spec.lower().startswith("semantic_type:"):
                target = spec.split(":", 1)[1].strip().lower()
                for col in columns:
                    sem = str(col.get("semantic_type") or col.get("inferred_type") or "").lower()
                    if sem == target:
                        nm = str(col.get("name"))
                        if nm and nm not in resolved_outcomes:
                            resolved_outcomes.append(nm)
            else:
                m = _find_column_by_pattern(spec, columns)
                if m:
                    resolved_outcomes.append(m)
        if resolved_outcomes:
            column_roles["outcome_cols"] = resolved_outcomes
            locked.append("outcome_cols")

    if defaults.covariate_cols:
        existing = list(column_roles.get("covariate_cols") or [])
        merged = list(existing)
        for pat in defaults.covariate_cols:
            m = _find_column_by_pattern(str(pat), columns)
            if m and m not in merged:
                merged.append(m)
        column_roles["covariate_cols"] = merged
        locked.append("covariate_cols")

    if defaults.clustering:
        resolved_cluster = _find_column_by_pattern(defaults.clustering, columns) or defaults.clustering
        roles_dict["clustering_unit"] = resolved_cluster
        roles_dict["clustering_warning"] = (
            f"Template declares cage-level clustering on {resolved_cluster}. "
            "Consider modelling pseudo-replication; current VCG pipeline does not adjust for it."
        )

    if defaults.method:
        vcg_cfg = roles_dict.setdefault("vcg_config", {})
        vcg_cfg["method"] = defaults.method
        roles_dict["method"] = defaults.method

    roles_dict["template_locked"] = locked
    return roles_dict


def _use_llm_orchestrator() -> bool:
    """LLM orchestrator on by default when an API key is available."""
    from llm_service import llm_enabled
    flag = os.getenv("VCG_LLM_CHAT", "auto").lower()
    if flag in ("0", "off", "false"):
        return False
    if flag in ("1", "on", "true"):
        return True
    return llm_enabled()

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
    prefill = infer_column_roles(s["columns"], s["table_structure"], s["metadata"])
    template_id = s.get("template_id")
    if template_id:
        try:
            from template_engine import get_template
            tpl = get_template(template_id)
            if tpl is not None:
                _apply_template_defaults(prefill, tpl, s["columns"])
                prefill["template_id"] = template_id
        except Exception:
            prefill.setdefault("template_locked", [])
    else:
        prefill.setdefault("template_locked", [])
    return prefill


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

    if _use_llm_orchestrator():
        from vcg.llm_orchestrator import llm_turn
        from llm_service import LLMUnavailable
        from hitl import add_suggestion
        try:
            turn = await asyncio.to_thread(llm_turn, s, None)
        except LLMUnavailable:
            from vcg.orchestrator import VCGOrchestrator
            msg = VCGOrchestrator(s).start()
            _persist(dataset_id, s)
            return msg

        if turn.get("hitl_suggestion"):
            add_suggestion(s, **turn["hitl_suggestion"])
        _persist(dataset_id, s)
        return turn["agent_msg"]

    from vcg.orchestrator import VCGOrchestrator
    msg = VCGOrchestrator(s).start()
    _persist(dataset_id, s)
    return msg


@vcg_router.post("/{dataset_id}/chat/respond")
async def chat_respond(dataset_id: str, body: Dict[str, Any]):
    s = _require(dataset_id)
    _ensure_vcg(s)
    user_message = body.get("message", "")

    if _use_llm_orchestrator():
        from vcg.llm_orchestrator import llm_turn
        from llm_service import LLMUnavailable
        from hitl import add_suggestion
        try:
            turn = await asyncio.to_thread(llm_turn, s, user_message)
        except LLMUnavailable:
            from vcg.orchestrator import VCGOrchestrator
            msg = VCGOrchestrator(s).respond(user_message)
            _persist(dataset_id, s)
            return msg

        if turn.get("hitl_suggestion"):
            add_suggestion(s, **turn["hitl_suggestion"])
        _persist(dataset_id, s)
        return turn["agent_msg"]

    from vcg.orchestrator import VCGOrchestrator
    msg = VCGOrchestrator(s).respond(user_message)
    _persist(dataset_id, s)
    return msg


@vcg_router.get("/{dataset_id}/conversation")
async def get_conversation(dataset_id: str):
    s = _require(dataset_id)
    return {"conversation": s.get("vcg", {}).get("conversation", [])}


@vcg_router.post("/{dataset_id}/llm-suggest")
async def vcg_llm_suggest(dataset_id: str):
    """One-shot LLM proposal of column roles, queued as HITL suggestion."""
    s = _require(dataset_id)
    _ensure_vcg(s)
    from vcg.llm_orchestrator import llm_turn
    from llm_service import LLMUnavailable
    from hitl import add_suggestion
    try:
        # Inject a synthetic user prompt asking for a one-shot proposal.
        turn = await asyncio.to_thread(
            llm_turn, s,
            "Please propose the best VCG configuration you can from the column "
            "metadata. Be explicit about what you're unsure of. Set "
            "ready_to_build=true only if you have confidently identified "
            "treatment_col, control_value, and at least one outcome column.",
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))

    created = None
    if turn.get("hitl_suggestion"):
        created = add_suggestion(s, **turn["hitl_suggestion"])
    _persist(dataset_id, s)
    return {"agent_msg": turn["agent_msg"], "suggestion": created}


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
