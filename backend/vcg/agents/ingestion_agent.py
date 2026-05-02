import pandas as pd
from typing import Dict, List, Any


class DataIngestionAgent:
    """Validates data suitability for VCG generation."""

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
            }

        col_vals = df[treatment_col].astype(str)

        # Check control_value exists
        if not control_value:
            blocking_issues.append(
                "control_value is not specified. Cannot identify the control group."
            )
        elif control_value not in col_vals.values:
            blocking_issues.append(
                f"control_value '{control_value}' was not found in column '{treatment_col}'."
            )

        # Identify control and treatment subsets
        if control_value and control_value in col_vals.values:
            control_mask = col_vals == str(control_value)
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

        return {
            "suitability_score": round(suitability_score, 3),
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "n_control": n_control,
            "n_treatment": n_treatment,
            "available_methods": available_methods,
            "recommended_n_synthetic": recommended_n_synthetic,
        }
