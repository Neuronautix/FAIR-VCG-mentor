import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional

from vcg.group_values import group_mask, normalize_group_value, visible_group_values


class DataIngestionAgent:
    """Validates data suitability for VCG generation."""

    def _check_suitability(
        self,
        control_df: pd.DataFrame,
        outcome_cols: List[str],
    ) -> Dict[str, Any]:
        """
        Checks statistical suitability of the control group for VCG generation.

        Returns:
            {
                "suitable": bool,
                "blocking_issues": [{"type": str, "endpoint": str|None, "message": str}],
                "warnings": [{"type": str, "endpoint": str|None, "message": str}],
            }
        """
        blocking_issues = []
        warnings = []

        n = len(control_df)

        # Block: too few subjects
        if n < 6:
            blocking_issues.append({
                "type": "insufficient_n",
                "endpoint": None,
                "message": (
                    f"Too few control subjects (n={n}). "
                    "Minimum 6 required for reliable VCG generation."
                ),
            })

        # Per-column checks
        for col in outcome_cols:
            if col not in control_df.columns:
                continue

            numeric = pd.to_numeric(control_df[col], errors="coerce").dropna()
            if len(numeric) == 0:
                continue

            values = numeric.values.astype(float)

            # Block: zero variance
            if float(np.std(values, ddof=0)) == 0.0:
                blocking_issues.append({
                    "type": "zero_variance",
                    "endpoint": col,
                    "message": (
                        f"Outcome column '{col}' has zero variance in control group."
                    ),
                })
                continue  # skip further checks for this column

            mean_val = float(np.mean(values))
            std_val = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0

            # Warning: high CV (> 80%)
            if mean_val != 0.0:
                cv = abs(std_val / mean_val) * 100.0
                if cv > 80.0:
                    warnings.append({
                        "type": "high_cv",
                        "endpoint": col,
                        "message": (
                            f"High coefficient of variation ({cv:.0f}%) in '{col}'. "
                            "VCG reliability may be limited."
                        ),
                    })

            # Warning: outliers with |z-score| > 3.5
            if std_val > 0:
                z_scores = np.abs((values - mean_val) / std_val)
                n_out = int(np.sum(z_scores > 3.5))
                if n_out > 0:
                    warnings.append({
                        "type": "outliers",
                        "endpoint": col,
                        "message": (
                            f"{n_out} potential outlier(s) detected in '{col}' (|z| > 3.5)."
                        ),
                    })

        suitable = len(blocking_issues) == 0
        return {
            "suitable": suitable,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
        }

    def run(
        self,
        df: pd.DataFrame,
        columns: List[Dict],
        column_roles: dict,
    ) -> Dict[str, Any]:
        """
        Returns {
            "suitability_score": float,  # 0-1
            "blocking_issues": List[str],   # must fix before proceeding
            "warnings": List[str],          # non-blocking
            "n_control": int,               # rows in control group
            "n_treatment": int,             # rows in treatment group
            "available_methods": List[str], # ["bootstrap", "synthetic"] based on N
            "recommended_n_synthetic": int, # min(3 * n_control, 150)
        }

        Blocking issues:
        - treatment_col not found in df
        - control_value not found in treatment_col values
        - n_control < 3
        - no numeric outcome columns

        Warnings:
        - n_control < 10: "Small control group (N={n}). VCG may have limited statistical power."
        - any outcome_col has missing_pct > 20%

        available_methods:
        - always include "synthetic"
        - include "bootstrap" if n_control >= 5

        suitability_score: 1.0 - 0.3*len(blocking_issues) - 0.1*len(warnings), clipped to [0,1]
        """
        blocking_issues: List[str] = []
        warnings: List[str] = []

        treatment_col = column_roles.get("treatment_col")
        control_value = column_roles.get("control_value")
        outcome_cols = column_roles.get("outcome_cols", [])

        # Check treatment_col exists in df
        if not treatment_col or treatment_col not in df.columns:
            blocking_issues.append(
                f"Treatment column '{treatment_col}' was not found in the dataset."
            )
            return {
                "suitability_score": 0.0,
                "blocking_issues": blocking_issues,
                "warnings": warnings,
                "n_control": 0,
                "n_treatment": 0,
                "available_methods": ["synthetic"],
                "recommended_n_synthetic": 30,
                "suitability": {
                    "suitable": False,
                    "blocking_issues": [],
                    "warnings": [],
                },
            }

        series = df[treatment_col]
        col_vals = series.astype(str)
        control_value = normalize_group_value(control_value, series)

        # Check control_value exists
        if not control_value:
            blocking_issues.append(
                "control_value is not specified. Cannot identify the control group."
            )
        elif not group_mask(series, control_value).any():
            blocking_issues.append(
                f"control_value '{control_value}' was not found in column '{treatment_col}'. "
                f"Available values: {visible_group_values(series, 10)}"
            )

        # Identify control and treatment subsets
        if control_value and group_mask(series, control_value).any():
            control_mask = group_mask(series, control_value)
            control_df = df[control_mask]
            treatment_df = df[~control_mask]
            n_control = len(control_df)
            n_treatment = len(treatment_df)
        else:
            n_control = 0
            n_treatment = 0

        # Check n_control >= 3
        if n_control < 3:
            blocking_issues.append(
                f"Control group has only {n_control} row(s). "
                "At least 3 control subjects are required to generate a VCG."
            )

        # Check numeric outcome columns
        valid_outcome_cols = []
        for oc in outcome_cols:
            if oc not in df.columns:
                blocking_issues.append(
                    f"Outcome column '{oc}' does not exist in the dataset."
                )
                continue
            numeric = pd.to_numeric(df[oc], errors="coerce")
            if numeric.notna().sum() == 0:
                blocking_issues.append(
                    f"Outcome column '{oc}' contains no numeric values."
                )
            else:
                valid_outcome_cols.append(oc)

        if not valid_outcome_cols and not blocking_issues:
            blocking_issues.append(
                "No valid numeric outcome columns found. "
                "Please specify at least one numeric outcome column."
            )

        # Warnings
        if 0 < n_control < 10:
            warnings.append(
                f"Small control group (N={n_control}). "
                "VCG may have limited statistical power."
            )

        # Check missing values in outcome columns
        col_dict = {c["name"]: c for c in columns}
        for oc in valid_outcome_cols:
            col_info = col_dict.get(oc, {})
            missing_pct = col_info.get("missing_pct", 0)
            if missing_pct == 0 and oc in df.columns:
                # Recompute from df if not in metadata
                missing_pct = (
                    pd.to_numeric(df[oc], errors="coerce").isna().sum()
                    / max(len(df), 1)
                    * 100
                )
            if missing_pct > 20:
                warnings.append(
                    f"Outcome column '{oc}' has {missing_pct:.1f}% missing values, "
                    "which may affect VCG quality."
                )

        # Available methods
        available_methods = ["synthetic"]
        if n_control >= 5:
            available_methods.append("bootstrap")

        # Recommended n_synthetic
        recommended_n_synthetic = min(3 * max(n_control, 1), 150)

        # Suitability score
        suitability_score = max(
            0.0,
            min(1.0, 1.0 - 0.3 * len(blocking_issues) - 0.1 * len(warnings)),
        )

        # Run deep suitability gate on the actual control subset
        if control_value and group_mask(series, control_value).any() and valid_outcome_cols:
            control_mask = group_mask(series, control_value)
            _control_df_for_suitability = df[control_mask]
            suitability = self._check_suitability(_control_df_for_suitability, valid_outcome_cols)
        else:
            suitability = {
                "suitable": False,
                "blocking_issues": [],
                "warnings": [],
            }

        return {
            "suitability_score": round(suitability_score, 3),
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "n_control": n_control,
            "n_treatment": n_treatment,
            "available_methods": available_methods,
            "recommended_n_synthetic": recommended_n_synthetic,
            "suitability": suitability,
        }
