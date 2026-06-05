from typing import List, Dict, Any, Optional

import pandas as pd

from vcg.constants import CONTROL_KEYWORDS as _CONTROL_KEYWORDS
from vcg.group_values import MISSING_GROUP_VALUE, group_mask, normalize_group_value, visible_group_values


def infer_column_roles(columns: List[Dict], table_structure: Dict, metadata: Dict) -> dict:
    """
    Returns a pre-populated wizard dict from profiler data.
    Logic:
    - subject_id: first column with inferred_type == "identifier"
    - treatment_col: first column with inferred_type == "experimental_condition"
    - control_value: if treatment_col found, scan sample_values for strings containing
      "vehicle", "ctrl", "control", "saline", "placebo", "sham", "wt", "wildtype" (case-insensitive)
    - treatment_value: first sample_value in treatment_col that is NOT control_value
    - outcome_cols: all columns with inferred_type == "measurement"
    - covariate_cols: columns with inferred_type in ("biological_descriptor",)
      e.g. sex, age, weight
    - time_col: table_structure["detected_time_vars"][0] if present, else None

    Returns dict matching ColumnRoles field names.
    Also returns "available_methods" list and "warnings" list.
    Full return shape:
    {
        "column_roles": {...},
        "vcg_config": {"method": "auto", "n_synthetic": n_control, "seed": 42, ...},
        "available_methods": ["bootstrap", "synthetic"],
        "warnings": [...]
    }
    where n_control = number of rows in the inferred control group (unknown without df, default 30)
    """
    warnings: List[str] = []

    # subject_id: first identifier column
    subject_id = None
    for col in columns:
        if col.get("inferred_type") == "identifier":
            subject_id = col["name"]
            break

    # treatment_col: first experimental_condition column
    treatment_col = None
    treatment_col_data = None
    for col in columns:
        if col.get("inferred_type") == "experimental_condition":
            treatment_col = col["name"]
            treatment_col_data = col
            break

    # control_value and treatment_value from sample_values of treatment_col
    control_value = None
    treatment_value = None
    if treatment_col_data is not None:
        sample_vals = treatment_col_data.get("sample_values", [])
        for v in sample_vals:
            v_str = str(v)
            if any(kw in v_str.lower() for kw in _CONTROL_KEYWORDS):
                control_value = v_str
                break
        # treatment_value = first sample value that is not control_value
        for v in sample_vals:
            v_str = str(v)
            if v_str != control_value:
                treatment_value = v_str
                break

    if treatment_col is None:
        warnings.append(
            "No treatment/group column was automatically detected. "
            "Please specify 'treatment_col' manually in the wizard."
        )

    if control_value is None and treatment_col is not None:
        warnings.append(
            f"Could not automatically detect the control group value in '{treatment_col}'. "
            "Please specify 'control_value' manually."
        )

    # outcome_cols: all measurement columns
    outcome_cols = [
        col["name"] for col in columns if col.get("inferred_type") == "measurement"
    ]
    if not outcome_cols:
        warnings.append(
            "No measurement columns were automatically detected. "
            "Please specify 'outcome_cols' manually."
        )

    # covariate_cols: biological_descriptor columns
    covariate_cols = [
        col["name"] for col in columns if col.get("inferred_type") == "biological_descriptor"
    ]

    # time_col: from table_structure
    time_col = None
    detected_time_vars = table_structure.get("detected_time_vars", [])
    if detected_time_vars:
        time_col = detected_time_vars[0]

    column_roles = {
        "subject_id": subject_id,
        "treatment_col": treatment_col,
        "treatment_value": treatment_value,
        "control_value": control_value,
        "outcome_cols": outcome_cols,
        "covariate_cols": covariate_cols,
        "time_col": time_col,
        "exclude_cols": [],
    }

    # Determine available methods - with unknown N, default to both
    available_methods = ["bootstrap", "synthetic"]

    vcg_config = {
        "method": "auto",
        "n_synthetic": 30,  # default; actual N computed after data filter
        "seed": 42,
        "bootstrap_iters": 1000,
        "confidence_level": 0.95,
    }

    return {
        "column_roles": column_roles,
        "vcg_config": vcg_config,
        "available_methods": available_methods,
        "warnings": warnings,
    }


def validate_wizard_payload(
    column_roles: dict,
    columns: List[Dict],
    df: pd.DataFrame,
) -> List[Dict[str, str]]:
    """
    Returns list of validation errors: [{"field": str, "message": str}].
    Empty list = valid.
    Checks:
    - treatment_col must exist in df.columns
    - treatment_value must appear in that column's actual values
    - control_value must appear in that column's actual values
    - outcome_cols must be non-empty
    - each outcome_col must be numeric (attempt pd.to_numeric)
    """
    errors: List[Dict[str, str]] = []

    treatment_col = column_roles.get("treatment_col")
    treatment_value = column_roles.get("treatment_value")
    control_value = column_roles.get("control_value")
    outcome_cols = column_roles.get("outcome_cols", [])

    if not treatment_col:
        errors.append({
            "field": "treatment_col",
            "message": "treatment_col is required but not specified.",
        })
    elif treatment_col not in df.columns:
        errors.append({
            "field": "treatment_col",
            "message": f"Column '{treatment_col}' does not exist in the dataset.",
        })
    else:
        series = df[treatment_col]
        col_vals = [str(v) for v in series.dropna().astype(str).unique().tolist()]

        treatment_value = normalize_group_value(treatment_value, series)
        control_value = normalize_group_value(control_value, series)

        if (
            treatment_value is not None
            and treatment_value != MISSING_GROUP_VALUE
            and treatment_value not in col_vals
        ):
            errors.append({
                "field": "treatment_value",
                "message": (
                    f"treatment_value '{treatment_value}' was not found in column "
                    f"'{treatment_col}'. Available values: {visible_group_values(series, 10)}"
                ),
            })

        if (
            control_value is not None
            and control_value != MISSING_GROUP_VALUE
            and control_value not in col_vals
        ):
            errors.append({
                "field": "control_value",
                "message": (
                    f"control_value '{control_value}' was not found in column "
                    f"'{treatment_col}'. Available values: {visible_group_values(series, 10)}"
                ),
            })

        if control_value is None or not group_mask(series, control_value).any():
            errors.append({
                "field": "control_value",
                "message": (
                    "control_value is required to identify the control group. "
                    f"Available values: {visible_group_values(series, 10)}"
                ),
            })

    if not outcome_cols:
        errors.append({
            "field": "outcome_cols",
            "message": "At least one outcome column must be specified.",
        })
    else:
        for oc in outcome_cols:
            if oc not in df.columns:
                errors.append({
                    "field": "outcome_cols",
                    "message": f"Outcome column '{oc}' does not exist in the dataset.",
                })
            else:
                numeric = pd.to_numeric(df[oc], errors="coerce")
                if numeric.notna().sum() == 0:
                    errors.append({
                        "field": "outcome_cols",
                        "message": (
                            f"Outcome column '{oc}' contains no numeric values. "
                            "Outcome columns must be numeric."
                        ),
                    })

    return errors
