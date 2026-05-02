import asyncio
from datetime import datetime
from typing import Any, Callable, Dict

import pandas as pd

from vcg.agents.ingestion_agent import DataIngestionAgent
from vcg.agents.standardization_agent import DataStandardizationAgent
from vcg.agents.vcg_bootstrap import BootstrapVCGAgent
from vcg.agents.vcg_synthetic import SyntheticVCGAgent
from vcg.agents.stats_agent import StatsAgent
from vcg.utils.covariate_balance import compute_balance_report
from vcg.vcg_report import generate_vcg_report


def auto_select_method(n_control: int) -> str:
    return "bootstrap" if n_control >= 15 else "synthetic"


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

        n_control = ingestion["n_control"]

        # Extract real control group
        if treatment_col and control_value and treatment_col in df.columns:
            real_control_df = df[df[treatment_col].astype(str) == str(control_value)].copy()
        else:
            real_control_df = df.copy()

        if real_control_df.empty:
            unique_vals = df[treatment_col].astype(str).unique().tolist()[:10] if treatment_col in df.columns else []
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
            vcg_df = BootstrapVCGAgent().run(control_df, outcome_cols, covariate_cols, vcg_config)
        else:
            vcg_df = SyntheticVCGAgent().run(control_df, outcome_cols, covariate_cols, vcg_config)

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
            "stat_report": report_md,
            "generated_at": datetime.now().isoformat(),
            "reliability_score": stats_result.get("reliability_score", 0.0),
            "warnings": stats_result.get("warnings", []),
        }
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
