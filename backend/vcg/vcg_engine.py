import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from vcg.agents.ingestion_agent import DataIngestionAgent
from vcg.agents.standardization_agent import DataStandardizationAgent
from vcg.agents.vcg_bootstrap import BootstrapVCGAgent
from vcg.agents.vcg_synthetic import SyntheticVCGAgent
from vcg.agents.stats_agent import StatsAgent
from vcg.group_values import group_mask, visible_group_values
from vcg.utils.covariate_balance import compute_balance_report
from vcg.vcg_report import generate_vcg_report


def auto_select_method(n_control: int) -> str:
    return "bootstrap" if n_control >= 15 else "synthetic"


# ── Predefined template analyses ─────────────────────────────────────────────


def _arrive_completeness(
    template: Any,
    template_validation: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_standard: Dict[str, Dict[str, Any]] = {}
    for entry in template_validation:
        std = entry.get("standard") or "unknown"
        bucket = by_standard.setdefault(
            std, {"satisfied": 0, "missing": 0, "partial": 0}
        )
        status = entry.get("status")
        if status == "satisfied":
            bucket["satisfied"] += 1
        elif status == "partial":
            bucket["partial"] += 1
        else:
            bucket["missing"] += 1

    for std, b in by_standard.items():
        total = b["satisfied"] + b["missing"] + b["partial"]
        b["completeness_pct"] = round(100.0 * b["satisfied"] / total, 2) if total else 0.0

    essential_total = 10
    essential_satisfied = 0
    if template is not None:
        high_field_ids = {
            m.id for m in getattr(template, "required_metadata", []) or []
            if getattr(m, "severity", "") == "high"
        } | {
            c.id for c in getattr(template, "required_columns", []) or []
            if getattr(c, "severity", "") == "high"
        }
        for entry in template_validation:
            fid = entry.get("field_id")
            if fid in high_field_ids and entry.get("status") == "satisfied":
                essential_satisfied += 1
        if high_field_ids:
            essential_total = max(10, len(high_field_ids))
            essential_total = min(essential_total, len(high_field_ids))

    return {
        "by_standard": by_standard,
        "essential_10_satisfied": essential_satisfied,
        "essential_10_total": essential_total,
    }


def _interpret_icc(icc: float) -> str:
    if icc < 0.05:
        return "low"
    if icc < 0.20:
        return "moderate"
    return "high"


def _cage_effect_check(
    session: Dict[str, Any],
    requires_columns: List[str],
) -> Dict[str, Any]:
    df: Optional[pd.DataFrame] = session.get("df")
    if df is None:
        raise ValueError("Dataset DataFrame is not available.")

    vcg = session.get("vcg") or {}
    column_roles = vcg.get("column_roles") or {}

    cluster_col: Optional[str] = None
    outcome_col: Optional[str] = None

    for name in requires_columns or []:
        if name in df.columns:
            if cluster_col is None and any(
                tok in name.lower() for tok in ("cage", "cluster", "unit")
            ):
                cluster_col = name
            elif outcome_col is None and any(
                tok in name.lower() for tok in ("outcome", "measure", "value")
            ):
                outcome_col = name

    if cluster_col is None:
        for name in requires_columns or []:
            if name in df.columns and name != outcome_col:
                cluster_col = name
                break
    if outcome_col is None:
        outcomes = column_roles.get("outcome_cols") or []
        for nm in outcomes:
            if nm in df.columns:
                outcome_col = nm
                break

    if cluster_col is None or outcome_col is None:
        raise ValueError(
            f"Required columns for cage_effect_check not found in dataset "
            f"(needed cluster + outcome; got cluster={cluster_col}, outcome={outcome_col})."
        )

    work = df[[cluster_col, outcome_col]].copy()
    work[outcome_col] = pd.to_numeric(work[outcome_col], errors="coerce")
    work = work.dropna(subset=[outcome_col, cluster_col])

    if work.empty:
        raise ValueError("No non-null rows available for ICC calculation.")

    groups = [g[outcome_col].to_numpy() for _, g in work.groupby(cluster_col)]
    groups = [g for g in groups if len(g) > 0]
    n_clusters = len(groups)
    if n_clusters < 2:
        raise ValueError(
            f"Need at least 2 clusters for ICC; got {n_clusters}."
        )

    all_vals = np.concatenate(groups)
    grand_mean = float(np.mean(all_vals))
    ns = np.array([len(g) for g in groups], dtype=float)
    means = np.array([float(np.mean(g)) for g in groups])

    ss_between = float(np.sum(ns * (means - grand_mean) ** 2))
    ss_within = float(
        np.sum([float(np.sum((g - np.mean(g)) ** 2)) for g in groups])
    )

    df_between = n_clusters - 1
    df_within = int(np.sum(ns) - n_clusters)
    if df_within <= 0 or df_between <= 0:
        raise ValueError("Insufficient degrees of freedom for ICC calculation.")

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within

    k = float(np.mean(ns))
    denom = ms_between + (k - 1.0) * ms_within
    if denom <= 0:
        icc = 0.0
    else:
        icc = (ms_between - ms_within) / denom
    icc = float(max(0.0, min(1.0, icc)))

    interpretation = _interpret_icc(icc)
    warning = None
    if icc > 0.05:
        warning = (
            f"ICC={icc:.3f} on cluster '{cluster_col}' suggests pseudo-replication risk; "
            "effect-size estimates may be biased if clustering is ignored."
        )

    return {
        "icc": round(icc, 4),
        "interpretation": interpretation,
        "outcome_col": outcome_col,
        "cluster_col": cluster_col,
        "n_clusters": n_clusters,
        "warning": warning,
    }


def _run_template_analyses(
    session: Dict[str, Any],
    vcg_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Run a template's predefined analyses; failures are isolated per-analysis."""
    template_id = session.get("template_id")
    if not template_id:
        return []

    try:
        from template_engine import get_template
        template = get_template(template_id)
    except Exception:
        template = None
    if template is None or not getattr(template, "predefined_analyses", None):
        return []

    template_validation = session.get("template_validation") or []
    out: List[Dict[str, Any]] = []
    for analysis in template.predefined_analyses:
        entry: Dict[str, Any] = {
            "id": analysis.id,
            "type": analysis.type,
            "description": analysis.description,
            "status": "ok",
            "result": None,
            "error": None,
        }
        try:
            if analysis.type == "report" and analysis.id == "arrive_completeness":
                entry["result"] = _arrive_completeness(template, template_validation)
            elif analysis.type == "stat" and analysis.id == "cage_effect_check":
                entry["result"] = _cage_effect_check(session, analysis.requires_columns)
            else:
                entry["status"] = "error"
                entry["error"] = "Not yet implemented"
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
        out.append(entry)
    return out


def run_vcg_pipeline(
    dataset_id: str,
    session: Dict[str, Any],
    sessions_dict: Dict[str, Any],
    save_fn: Callable,
) -> None:
    """
    Runs the full VCG pipeline synchronously.
    Designed to be called via asyncio.to_thread from an async FastAPI route.
    Updates session["vcg"] in-place and calls save_fn when done.
    """
    vcg = session["vcg"]

    try:
        column_roles = vcg["column_roles"]
        vcg_config = vcg["vcg_config"]
        df: pd.DataFrame = session["df"]

        treatment_col = column_roles.get("treatment_col")
        control_value = column_roles.get("control_value")
        outcome_cols = column_roles.get("outcome_cols", [])
        covariate_cols = column_roles.get("covariate_cols", [])

        # ── Step 1: Ingestion ──────────────────────────────────────────────────
        ingestion = DataIngestionAgent().run(df, session["columns"], column_roles)
        if ingestion["blocking_issues"]:
            raise ValueError(f"Data ingestion failed: {'; '.join(ingestion['blocking_issues'])}")

        # Enforce suitability gate (n<6, zero variance, etc.)
        suitability = ingestion.get("suitability", {})
        suitability_blocks = suitability.get("blocking_issues", [])
        if suitability_blocks:
            msgs = [b["message"] for b in suitability_blocks]
            raise ValueError(f"Suitability gate failed: {'; '.join(msgs)}")

        n_control = ingestion["n_control"]

        # Extract real control group
        if treatment_col and control_value and treatment_col in df.columns:
            real_control_df = df[group_mask(df[treatment_col], control_value)].copy()
        else:
            real_control_df = df.copy()

        if real_control_df.empty:
            unique_vals = visible_group_values(df[treatment_col], 10) if treatment_col in df.columns else []
            raise ValueError(
                f"No rows matched control value '{control_value}' in column '{treatment_col}'. "
                f"Values present: {unique_vals}. "
                "Check for type mismatches (e.g. integer vs string) or spelling differences."
            )

        # ── Step 2: Standardisation ────────────────────────────────────────────
        std_result = DataStandardizationAgent().run(
            real_control_df, session["columns"], outcome_cols, covariate_cols
        )
        control_df = std_result["standardized_df"]

        # ── Step 3: VCG generation ─────────────────────────────────────────────
        method = vcg_config.get("method", "auto")
        if method == "auto":
            method = auto_select_method(n_control)

        if method == "bootstrap":
            bootstrap_agent = BootstrapVCGAgent()
            vcg_df = bootstrap_agent.run(control_df, outcome_cols, covariate_cols, vcg_config)
            method_diagnostics = bootstrap_agent.method_diagnostics
        else:
            synthetic_agent = SyntheticVCGAgent()
            vcg_df = synthetic_agent.run(control_df, outcome_cols, covariate_cols, vcg_config)
            method_diagnostics = synthetic_agent.method_diagnostics

        # ── Step 4: Statistics ─────────────────────────────────────────────────
        valid_outcomes = [c for c in outcome_cols if c in control_df.columns and c in vcg_df.columns]
        valid_covariates = [c for c in covariate_cols if c in control_df.columns and c in vcg_df.columns]

        stats_result = StatsAgent().run(
            real_control_df=control_df,
            vcg_df=vcg_df,
            outcome_cols=valid_outcomes,
            covariate_cols=valid_covariates,
            confidence_level=vcg_config.get("confidence_level", 0.95),
        )

        balance = compute_balance_report(control_df, vcg_df, valid_covariates, valid_outcomes)

        # ── Step 5: Report ─────────────────────────────────────────────────────
        report_md = generate_vcg_report(
            research_context=vcg["research_context"],
            column_roles=column_roles,
            vcg_config=vcg_config,
            balance_report=balance,
            stats_result=stats_result,
            n_real=len(control_df),
            n_vcg=len(vcg_df),
            method_used=method,
        )

        # ── Done ───────────────────────────────────────────────────────────────
        vcg["vcg_results"] = {
            "method_used": method,
            "n_subjects_real": len(control_df),
            "n_subjects_vcg": len(vcg_df),
            "vcg_csv": vcg_df.to_csv(index=False),
            "balance_report": balance,
            "diagnostic_plots": stats_result.get("diagnostic_plots", {}),
            "per_endpoint_plots": stats_result.get("per_endpoint_plots", {}),
            "reliability_score": stats_result.get("reliability_score", 0.0),
            "reliability_breakdown": stats_result.get("reliability_breakdown", {}),
            "method_diagnostics": method_diagnostics,
            "stat_report": report_md,
            "generated_at": datetime.now().isoformat(),
            "warnings": stats_result.get("warnings", []) + ingestion.get("suitability", {}).get("warnings", []),
        }

        try:
            template_analyses = _run_template_analyses(session, vcg["vcg_results"])
            if template_analyses:
                vcg["vcg_results"]["template_analyses"] = template_analyses
        except Exception:
            vcg["vcg_results"]["template_analyses"] = []

        vcg["vcg_status"] = "done"

    except Exception as exc:
        vcg["vcg_status"] = "failed"
        vcg["vcg_error"] = str(exc)

    finally:
        sessions_dict[dataset_id] = session
        if save_fn:
            try:
                save_fn(dataset_id, session)
            except Exception:
                pass
