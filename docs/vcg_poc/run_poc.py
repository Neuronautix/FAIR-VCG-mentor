"""
VCG proof-of-concept driver — rodent repeat-dose toxicology.

Drives the REAL backend pipeline (vcg.vcg_engine.run_vcg_pipeline) end-to-end on
the synthesized historical Vehicle-control pool, exactly the way the FastAPI app
would: it profiles the CSV with csv_profiler.profile_csv to build session["df"]
and session["columns"], configures ColumnRoles + VCGConfig, then runs the four
agents (ingestion -> standardization -> bootstrap -> stats).

No FastAPI server, no LLM key, no network required.

Outputs (docs/vcg_poc/outputs/):
    vcg_synthetic_controls.csv   the generated synthetic control cohort
    vcg_report.md                the Markdown statistical report
    poc_results.json             machine-readable summary (scores, balance, fidelity)

Run:  python docs/vcg_poc/run_poc.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
DATA = os.path.abspath(os.path.join(HERE, "..", "..", "test_data", "tox_historical_controls.csv"))
OUT_DIR = os.path.join(HERE, "outputs")
sys.path.insert(0, BACKEND)

from csv_profiler import profile_csv                       # noqa: E402
from vcg.context_model import (                            # noqa: E402
    DEFAULT_VCG_SESSION, roles_to_dict, config_to_dict,
    context_to_dict, ColumnRoles, VCGConfig, ResearchContext,
)
from vcg.vcg_engine import run_vcg_pipeline                 # noqa: E402

OUTCOMES = [
    "body_weight_end_g", "liver_weight_g", "kidney_weight_g",
    "alt_u_l", "ast_u_l", "creatinine_umol_l",
]
COVARIATES = ["sex", "strain"]


def build_session() -> dict:
    """Reproduce the session object the app builds on POST /api/upload."""
    with open(DATA, "rb") as fh:
        content = fh.read()
    result = profile_csv(content, "tox_historical_controls.csv")
    df = result.pop("df")
    result.pop("content", None)

    session: dict = {
        "dataset_id": "poc-tox-historical-controls",
        "columns": result["columns"],
        "df": df,
        "metadata": {},
    }

    # Configure the VCG sub-session: Vehicle is the control; 6 correlated
    # endpoints; sex & strain as covariates. Bootstrap is requested explicitly
    # (N=24 >= 15) so the Gaussian copula preserves inter-endpoint structure.
    vcg = DEFAULT_VCG_SESSION()
    vcg["column_roles"] = roles_to_dict(ColumnRoles(
        subject_id="animal_id",
        treatment_col="group",
        control_value="Vehicle",
        outcome_cols=OUTCOMES,
        covariate_cols=COVARIATES,
    ))
    vcg["vcg_config"] = config_to_dict(VCGConfig(
        method="bootstrap", n_synthetic=30, seed=42,
        bootstrap_iters=1000, confidence_level=0.95,
    ))
    vcg["research_context"] = context_to_dict(ResearchContext(
        domain="toxicology", study_type="dose_response",
        design="parallel_group", confirmed_by_user=True,
    ))
    session["vcg"] = vcg
    return session


def fidelity_table(real: pd.DataFrame, vcg: pd.DataFrame) -> list[dict]:
    """Per-endpoint real-vs-VCG mean/SD plus pooled correlation recovery."""
    rows = []
    for col in OUTCOMES:
        r = pd.to_numeric(real[col], errors="coerce").dropna()
        v = pd.to_numeric(vcg[col], errors="coerce").dropna()
        rows.append({
            "endpoint": col,
            "real_mean": round(float(r.mean()), 3),
            "real_sd": round(float(r.std(ddof=1)), 3),
            "vcg_mean": round(float(v.mean()), 3),
            "vcg_sd": round(float(v.std(ddof=1)), 3),
            "mean_pct_diff": round(100 * (v.mean() - r.mean()) / r.mean(), 2),
        })
    return rows


def correlation_recovery(real: pd.DataFrame, vcg: pd.DataFrame) -> dict:
    """Compare the Spearman correlation matrices (structure preservation)."""
    rc = real[OUTCOMES].apply(pd.to_numeric, errors="coerce").corr(method="spearman")
    vc = vcg[OUTCOMES].apply(pd.to_numeric, errors="coerce").corr(method="spearman")
    iu = np.triu_indices(len(OUTCOMES), k=1)
    diff = np.abs(rc.values[iu] - vc.values[iu])
    return {
        "mean_abs_corr_error": round(float(np.mean(diff)), 4),
        "max_abs_corr_error": round(float(np.max(diff)), 4),
        "real_corr": rc.round(3).to_dict(),
        "vcg_corr": vc.round(3).to_dict(),
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    session = build_session()

    saved = {}
    def save_fn(dataset_id, sess):
        saved["called"] = True

    run_vcg_pipeline("poc-tox-historical-controls", session, {}, save_fn)

    vcg = session["vcg"]
    status = vcg["vcg_status"]
    print(f"pipeline status: {status}")
    if status != "done":
        print(f"ERROR: {vcg.get('vcg_error')}")
        sys.exit(1)

    res = vcg["vcg_results"]
    vcg_df = pd.read_csv(__import__("io").StringIO(res["vcg_csv"]))
    real_control = session["df"][session["df"]["group"] == "Vehicle"].copy()

    # ── Write artifacts ──────────────────────────────────────────────────────
    vcg_df.to_csv(os.path.join(OUT_DIR, "vcg_synthetic_controls.csv"), index=False)
    with open(os.path.join(OUT_DIR, "vcg_report.md"), "w") as fh:
        fh.write(res["stat_report"])

    fid = fidelity_table(real_control, vcg_df)
    corr = correlation_recovery(real_control, vcg_df)

    summary = {
        "method_used": res["method_used"],
        "n_real_controls": res["n_subjects_real"],
        "n_vcg_controls": res["n_subjects_vcg"],
        "reliability_score": res["reliability_score"],
        "reliability_breakdown": res.get("reliability_breakdown", {}),
        "warnings": res.get("warnings", []),
        "per_endpoint_fidelity": fid,
        "correlation_recovery": {
            "mean_abs_corr_error": corr["mean_abs_corr_error"],
            "max_abs_corr_error": corr["max_abs_corr_error"],
        },
        "fitted_distributions": {
            k: v.get("dist_name") if isinstance(v, dict) else v
            for k, v in (res.get("method_diagnostics", {})
                         .get("fitted_distributions", {}) or {}).items()
        },
    }
    with open(os.path.join(OUT_DIR, "poc_results.json"), "w") as fh:
        json.dump({**summary, "correlation_detail": corr}, fh, indent=2)

    # ── Console report ───────────────────────────────────────────────────────
    print(f"\nmethod: {res['method_used']}   "
          f"real N={res['n_subjects_real']}  ->  VCG N={res['n_subjects_vcg']}")
    print(f"reliability score: {res['reliability_score']:.3f}")
    print("\nper-endpoint fidelity (real vs VCG):")
    print(f"{'endpoint':<20}{'real mean±sd':>22}{'vcg mean±sd':>22}{'Δmean%':>9}")
    for r in fid:
        real_cell = f"{r['real_mean']}±{r['real_sd']}"
        vcg_cell = f"{r['vcg_mean']}±{r['vcg_sd']}"
        print(f"{r['endpoint']:<20}{real_cell:>22}{vcg_cell:>22}{r['mean_pct_diff']:>9}")
    print(f"\ncorrelation-structure recovery: "
          f"mean |Δρ|={corr['mean_abs_corr_error']}, "
          f"max |Δρ|={corr['max_abs_corr_error']}")
    if summary["fitted_distributions"]:
        print("\nfitted marginals:")
        for k, v in summary["fitted_distributions"].items():
            print(f"  {k:<20} {v}")
    if res.get("warnings"):
        print("\nwarnings:")
        for w in res["warnings"]:
            print(f"  - {w}")
    print(f"\nartifacts written to {OUT_DIR}/")


if __name__ == "__main__":
    main()
