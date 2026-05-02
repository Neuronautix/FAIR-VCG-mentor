import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List


def standardised_mean_difference(s1: pd.Series, s2: pd.Series) -> float:
    """
    SMD = (mean1 - mean2) / pooled_std
    For categorical: use proportion difference / sqrt(p*(1-p))
    Returns absolute SMD.
    """
    # Attempt numeric interpretation first
    n1 = pd.to_numeric(s1, errors="coerce")
    n2 = pd.to_numeric(s2, errors="coerce")

    if n1.notna().sum() > 1 and n2.notna().sum() > 1:
        # Numeric SMD
        mean1 = n1.mean()
        mean2 = n2.mean()
        std1 = n1.std(ddof=1)
        std2 = n2.std(ddof=1)

        n_1 = n1.notna().sum()
        n_2 = n2.notna().sum()

        # Pooled standard deviation
        pooled_var = ((n_1 - 1) * std1 ** 2 + (n_2 - 1) * std2 ** 2) / (n_1 + n_2 - 2)
        pooled_std = np.sqrt(max(pooled_var, 1e-12))

        return abs((mean1 - mean2) / pooled_std)
    else:
        # Categorical: use proportion difference for the most common category
        combined = pd.concat([s1, s2], ignore_index=True)
        if combined.nunique() == 0:
            return 0.0

        most_common = combined.mode().iloc[0]
        p1 = (s1 == most_common).mean()
        p2 = (s2 == most_common).mean()
        p_pool = (p1 * len(s1) + p2 * len(s2)) / (len(s1) + len(s2))
        denom = np.sqrt(max(p_pool * (1 - p_pool), 1e-12))
        return abs((p1 - p2) / denom)


def compute_balance_report(
    df_real: pd.DataFrame,
    df_vcg: pd.DataFrame,
    covariate_cols: List[str],
    outcome_cols: List[str],
) -> dict:
    """
    Returns {
        "covariates": [{"col": str, "smd": float, "balance_label": "excellent"|"acceptable"|"poor"}, ...],
        "outcomes": [{"col": str, "mean_real": float, "sd_real": float,
                      "mean_vcg": float, "sd_vcg": float, "p_value": float}, ...]
    }
    balance_label: smd < 0.1 = "excellent", 0.1-0.25 = "acceptable", > 0.25 = "poor"
    p_value from scipy.stats.ttest_ind (two-sided).
    """
    covariate_report = []
    for col in covariate_cols:
        if col not in df_real.columns or col not in df_vcg.columns:
            continue

        s1 = df_real[col].dropna()
        s2 = df_vcg[col].dropna()

        if len(s1) == 0 or len(s2) == 0:
            continue

        smd = standardised_mean_difference(s1, s2)

        if smd < 0.1:
            label = "excellent"
        elif smd < 0.25:
            label = "acceptable"
        else:
            label = "poor"

        covariate_report.append({
            "col": col,
            "smd": round(float(smd), 4),
            "balance_label": label,
        })

    outcome_report = []
    for col in outcome_cols:
        if col not in df_real.columns or col not in df_vcg.columns:
            continue

        r_num = pd.to_numeric(df_real[col], errors="coerce").dropna()
        v_num = pd.to_numeric(df_vcg[col], errors="coerce").dropna()

        if len(r_num) < 2 or len(v_num) < 2:
            continue

        mean_real = float(r_num.mean())
        sd_real = float(r_num.std(ddof=1))
        mean_vcg = float(v_num.mean())
        sd_vcg = float(v_num.std(ddof=1))

        try:
            _, p_value = stats.ttest_ind(r_num.values, v_num.values, equal_var=False)
            p_value = float(p_value)
        except Exception:
            p_value = float("nan")

        outcome_report.append({
            "col": col,
            "mean_real": round(mean_real, 4),
            "sd_real": round(sd_real, 4),
            "mean_vcg": round(mean_vcg, 4),
            "sd_vcg": round(sd_vcg, 4),
            "p_value": round(p_value, 4) if not np.isnan(p_value) else None,
        })

    return {
        "covariates": covariate_report,
        "outcomes": outcome_report,
    }
