from datetime import datetime
from typing import Dict, Any, List


def generate_vcg_report(
    research_context: Dict,
    column_roles: Dict,
    vcg_config: Dict,
    balance_report: Dict,
    stats_result: Dict,
    n_real: int,
    n_vcg: int,
    method_used: str,
) -> str:
    outcome_cols: List[str] = column_roles.get("outcome_cols", [])
    covariate_cols: List[str] = column_roles.get("covariate_cols", [])
    seed = vcg_config.get("seed", 42)
    domain = research_context.get("domain", "unknown")
    study_type = research_context.get("study_type", "unknown")
    control_label = column_roles.get("control_value", "control")
    reliability = stats_result.get("reliability_score", 0.0)

    try:
        import scipy
        scipy_ver = scipy.__version__
    except Exception:
        scipy_ver = "unknown"

    # Reliability interpretation
    if reliability >= 0.7:
        rel_label = "high"
        rel_note = "The VCG closely replicates the observed control distribution."
    elif reliability >= 0.5:
        rel_label = "moderate"
        rel_note = "The VCG provides a reasonable approximation. Review individual endpoint diagnostics."
    else:
        rel_label = "low"
        rel_note = "The VCG may not adequately replicate the control distribution. Consider collecting more historical data."

    method_descriptions = {
        "bootstrap": (
            "Parametric bootstrap with Gaussian copula. Marginal distributions were fitted per endpoint "
            "(Normal, Log-Normal, or Gamma selected via Shapiro-Wilk). The Gaussian copula preserves "
            "Spearman rank correlations between endpoints. Appropriate for N≥15."
        ),
        "synthetic": (
            "Parametric synthetic generation. Each endpoint was sampled independently from a "
            "fitted KDE (N≥15) or Normal distribution (N<15). Shapiro-Wilk was used to select "
            "Log-Normal for right-skewed positive-valued endpoints. Appropriate for small N."
        ),
        "auto": "Method was automatically selected based on sample size.",
    }
    method_desc = method_descriptions.get(method_used, method_used)

    # Build tables
    cov_rows = balance_report.get("covariates", [])
    cov_table = _md_table(
        ["Covariate", "SMD", "Assessment"],
        [[r["col"], f"{r['smd']:.3f}", r["balance_label"].title()] for r in cov_rows]
    ) if cov_rows else "_No covariates balanced._"

    out_rows = balance_report.get("outcomes", [])
    ks_pvals = stats_result.get("ks_pvalues", {})
    eff_sizes = stats_result.get("effect_sizes", {})
    outcome_table_rows = []
    for r in out_rows:
        col = r["col"]
        p = ks_pvals.get(col, float("nan"))
        d = eff_sizes.get(col, {}).get("cohens_d", float("nan"))
        interp = eff_sizes.get(col, {}).get("interpretation", "")
        p_str = f"{p:.3f}" if p == p else "N/A"
        d_str = f"{d:.3f}" if d == d else "N/A"
        outcome_table_rows.append([
            col,
            f"{r['mean_real']:.3g} ± {r['sd_real']:.3g}",
            f"{r['mean_vcg']:.3g} ± {r['sd_vcg']:.3g}",
            p_str,
            d_str,
            interp,
        ])
    outcome_table = _md_table(
        ["Endpoint", "Mean±SD (Real)", "Mean±SD (VCG)", "KS p-value", "Cohen's d", "Interpretation"],
        outcome_table_rows
    ) if outcome_table_rows else "_No outcome comparison available._"

    power_rows = stats_result.get("power_estimates", {})
    power_table_rows = [
        [col, f"{v.get('achieved_power', 0):.2f}", str(v.get("n_for_80pct", "N/A"))]
        for col, v in power_rows.items()
    ]
    power_table = _md_table(
        ["Endpoint", "Achieved Power", "N for 80% Power"],
        power_table_rows
    ) if power_table_rows else "_Power analysis not available._"

    warnings = stats_result.get("warnings", [])
    warnings_text = "\n".join(f"- {w}" for w in warnings) if warnings else "_None._"

    # Estimate animal reduction
    reduction = max(1, n_vcg // max(n_real, 1))
    mean_smd = sum(r["smd"] for r in cov_rows) / len(cov_rows) if cov_rows else 0.0

    report = f"""# Virtual Control Group — Statistical Report

> ⚠ **DISCLAIMER**: Virtual control groups are a methodological aid — not a substitute for
> randomised experimental controls. Results should be interpreted with caution and reviewed
> by a qualified statistician before use in regulatory submissions or publications.

---

## 1. Study Context

| Field | Value |
|---|---|
| Research domain | {domain} |
| Study type | {study_type} |
| Primary entity | {research_context.get("primary_entity", "entity")} |
| Control label | {control_label} |

---

## 2. Data Summary

- **Real control subjects**: N = {n_real}
- **Virtual control subjects**: N = {n_vcg}
- **Endpoints modelled**: {', '.join(f'`{c}`' for c in outcome_cols) or '_none_'}
- **Covariates balanced**: {', '.join(f'`{c}`' for c in covariate_cols) or '_none_'}

---

## 3. Generation Method

**Method used**: `{method_used}`

{method_desc}

**Random seed**: {seed} (fixed for reproducibility)

---

## 4. Covariate Balance

SMD < 0.1 = Excellent | 0.1–0.25 = Acceptable | > 0.25 = Poor

{cov_table}

---

## 5. Outcome Distribution Comparison

{outcome_table}

---

## 6. Statistical Power

{power_table}

---

## 7. Reliability Assessment

**Overall reliability score**: {reliability:.2f} / 1.00 ({rel_label.upper()})

{rel_note}

---

## 8. Warnings

{warnings_text}

---

## 9. Limitations

- VCG is derived from N={n_real} real control subjects; conclusions are limited by this sample size.
- Marginal distributions are fitted independently; complex multivariate relationships beyond pairwise correlations may not be fully captured (Phase 1 bootstrap) or at all (synthetic method).
- The generated dataset is intended to supplement, not replace, concurrent controls in primary efficacy analyses.
- External validity depends on the historical data being representative of the current experimental conditions (species, age, housing, handling).

---

## 10. Reproducibility

| Parameter | Value |
|---|---|
| Generated | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} |
| scipy version | {scipy_ver} |
| Method | {method_used} |
| Seed | {seed} |
| n_real | {n_real} |
| n_vcg | {n_vcg} |

---

## 11. 3Rs Justification Template

> Virtual controls were generated from **{n_real} historical {control_label} subjects** using
> **{method_used} sampling** (seed={seed}). The VCG demonstrates **{rel_label}** distributional
> similarity to the source population (KS tests: p > 0.05 for {_count_passing(ks_pvals)}/{len(ks_pvals)} endpoints;
> mean covariate SMD = {mean_smd:.3f}). This approach supports reduction of up to **{n_vcg} animals**
> in concurrent control groups, consistent with the 3Rs principles (Russell & Burch, 1959) and
> current guidance on the use of historical control data in non-clinical studies.
"""
    return report


def _md_table(headers: list, rows: list) -> str:
    if not rows:
        return ""
    sep = "|".join(["---"] * len(headers))
    header_row = " | ".join(headers)
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return f"| {header_row} |\n|{sep}|\n{body}"


def _count_passing(ks_pvals: dict) -> int:
    return sum(1 for p in ks_pvals.values() if p > 0.05)
